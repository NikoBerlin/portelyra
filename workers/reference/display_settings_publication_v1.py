"""Anzeige-Einstellungen veroeffentlichen (#500): Nachkommastellen und farbige Hinterlegung fuer Cockpit, Steuer und Analyse.

Die anzeigenden Apps lesen keinen Speicher, nur veroeffentlichte Artefakte. Deshalb geht die Wahl aus dem Reiter "Einstellungen"
der Data-App als kleines Artefakt in den Bereich `display_settings`. Veroeffentlicht wird nur, wenn sich der Inhalt gegenueber
dem geltenden Stand aendert. Die Laufkennung enthaelt den Zeitpunkt: Wer von "aus" auf "an" und zurueck schaltet, bekommt
wieder einen neuen geltenden Lauf, statt an einem frueheren gleichen Inhalt haengen zu bleiben.

Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from migrations.reference.legacy_import_data_command_v1 import fingerprint
from migrations.reference.user_settings_v1 import UserSettingsV1Error, drawdown_zones_v1, history_lines_v1, read_user_settings_v1, small_holdings_threshold_v1, user_settings_context_v1

AREA_ID = "display_settings"
WRITER_ID = "desktop_display_settings_worker"
WRITER_ROLE = "display_settings_worker"
ARTIFACT_CONTRACT = "display_settings_v1"
VERSION = 1


class DisplaySettingsPublicationV1Error(RuntimeError):
    CODES = frozenset({"display_settings_publication_input_invalid", "display_settings_publication_failed"})

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in self.CODES else "display_settings_publication_failed"


def _abort(code: str) -> None:
    raise DisplaySettingsPublicationV1Error(code)


def _portfolio_scope(space) -> dict[str, Any] | None:
    """Umfang je Portfolio und was im Datenraum laeuft; ohne Speicher (vor dem ersten Kontakt) kein Feld - dann gilt alles wie bisher."""
    from migrations.reference import portfolio_configuration_v1 as configuration
    try:
        value = configuration.space_configuration_v1(space)
    except configuration.PortfolioConfigurationV1Error:
        _abort("display_settings_publication_failed")
    if not value["store_present"]:
        return None
    return {"effective_scope_text": value["effective_scope_text"], "modules": dict(value["effective"]["modules"]),
            "classes": list(value["effective"]["classes"]), "valuation_without_market": value["effective"]["valuation_without_market"],
            "portfolios": [{"label": item["label"], "status": item["status"], "configured": item["configured"], "scope_text": item["scope_text"]}
                           for _, item in sorted(value["portfolios"].items())][:50]}


def build_display_settings_artifact_v1(space, context_value, completed_at_utc: str) -> dict[str, Any]:
    context = user_settings_context_v1(context_value)
    settings = read_user_settings_v1(space, context)["settings"]
    body = {
        "display_settings_version": VERSION, "status": "completed",
        "tenant_id": context.tenant_id, "user_id": context.user_id, "data_space_id": context.data_space_id,
        "amount_decimals": int(settings["amount_decimals"]), "tint": settings["tint"] == "on",
        # Rueckgangszonen der Analyse (#506); seit rc.305, aeltere Artefakte tragen das Feld nicht.
        "drawdown_zones": drawdown_zones_v1(settings.get("drawdown_zones", "")),
        # Seit rc.309 (#492, Festlegung 23.10.2026): Expertenschalter fuer das Cockpit, Standard-Zeitraum der Analyse.
        "expert_tools": settings.get("expert_tools", "off") == "on",
        "analysis_period": settings.get("analysis_period", "all"),
        # Seit 0.2.0-rc.353 (#531 Punkt 2): Linien und Kennwerte des Portfolio-Verlaufs beim Oeffnen.
        "history_lines": history_lines_v1(settings.get("history_lines", "")),
        # Seit 0.2.0-rc.360 (#534): Grenze fuer Kleinstbestaende in Euro, exakter Dezimaltext.
        "small_holdings_threshold_decimal": small_holdings_threshold_v1(settings.get("small_holdings_threshold", "1")),
        "provider_access": False, "network_access": False, "canonical_write": False,
    }
    # Seit rc.395 (#542): der Umfang je Portfolio, damit die Anzeige-Apps ihn nennen und abgeschaltete Bausteine als solche zeigen.
    scope = _portfolio_scope(space)
    if scope is not None:
        body["portfolio_scope"] = scope
    content = fingerprint(body)
    artifact = {**body, "display_settings_id": "dsp_" + content[:32], "content_fingerprint": content, "completed_at_utc": completed_at_utc}
    artifact["artifact_fingerprint"] = fingerprint(artifact)
    return artifact


def _current_content(area: Path) -> str | None:
    try:
        run_id = json.loads((area / "latest.json").read_text(encoding="utf-8")).get("run_id")
        if not isinstance(run_id, str) or "/" in run_id or not run_id.startswith("run_"):
            return None
        return json.loads((area / "runs" / run_id / "artifact.json").read_text(encoding="utf-8")).get("content_fingerprint")
    except (OSError, ValueError, AttributeError):
        return None


def publish_display_settings_v1(space, context_value, published_at_utc: str, artifacts_root=None) -> dict[str, Any]:
    """Veroeffentlicht die Anzeige-Einstellungen, wenn sie sich gegenueber dem geltenden Stand geaendert haben."""
    import re
    if not isinstance(published_at_utc, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", published_at_utc) is None:
        _abort("display_settings_publication_input_invalid")
    try:
        context = user_settings_context_v1(context_value)
        artifact = build_display_settings_artifact_v1(space, context, published_at_utc)
    except UserSettingsV1Error:
        _abort("display_settings_publication_failed")
    root = Path(artifacts_root) if artifacts_root is not None else Path(space) / "artifacts"
    area = root / AREA_ID
    result = {"display_settings_publication_version": VERSION, "amount_decimals": artifact["amount_decimals"], "tint": artifact["tint"],
              "provider_access": False, "network_access": False, "canonical_write": False}
    if _current_content(area) == artifact["content_fingerprint"]:
        return {**result, "status": "already_published"}
    for directory in (root, area):
        if directory.is_symlink():
            _abort("display_settings_publication_failed")
        if not directory.exists():
            directory.mkdir(mode=0o700, parents=True)
        os.chmod(directory, 0o700)
    from workers.reference.run_publication_v1 import PublicationRuntimeContext, RunPublicationError, publish_completed_run_v1
    runtime = PublicationRuntimeContext(context.tenant_id, context.user_id, context.data_space_id, AREA_ID, WRITER_ID, WRITER_ROLE)
    run_id = "run_" + fingerprint({"content": artifact["content_fingerprint"], "published_at_utc": published_at_utc})[:32]
    try:
        published = publish_completed_run_v1(area, runtime, run_id, artifact, published_at_utc)
    except RunPublicationError:
        _abort("display_settings_publication_failed")
    return {**result, "status": published.status}


__all__ = ["AREA_ID", "ARTIFACT_CONTRACT", "DisplaySettingsPublicationV1Error", "WRITER_ROLE", "build_display_settings_artifact_v1",
           "publish_display_settings_v1"]
