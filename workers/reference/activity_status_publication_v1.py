"""Stand der Aktualisierung fuer alle Apps (#540): was laeuft, seit wann, wie weit - was zuletzt fertig wurde, was als Naechstes kommt.

Cockpit, Steuer und Analyse lesen keinen Speicher, nur Veroeffentlichtes. Der Hintergrundlauf (scripts/desktop_refresh_all.R)
veroeffentlicht deshalb diesen kleinen Stand: beim Start, bei jedem Schrittwechsel, alle paar Assets und am Ende. Gebildet wird er
in R aus Sperre, Stand und Zeitplan (apps/shared/desktop_activity_v1.R) - dieselbe Form zeigt die Data-App direkt.

Veroeffentlicht wird nur, wenn sich der Inhalt aendert; die verstrichene Zeit und die Restzeit zaehlt der Browser selbst, den
naechsten Termin rechnet er aus den Uhrzeiten (sonst stuende nach einem verpassten Termin ein vergangener da). Aeltere Laeufe
werden aufgeraeumt, der geltende bleibt. Keine Kennungen des Bestands, kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from migrations.reference.legacy_import_data_command_v1 import fingerprint

AREA_ID = "activity_status"
WRITER_ID = "desktop_activity_status_worker"
WRITER_ROLE = "activity_status_worker"
ARTIFACT_CONTRACT = "activity_status_v1"
VERSION = 1
KEEP_RUNS = 5
KINDS = ("refresh", "moment", "sweep", "names", "maintenance", "other")
ORIGINS = ("app", "timer", "other")
TONES = ("positive", "neutral", "warning", "error")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_TIME = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


class ActivityStatusPublicationV1Error(RuntimeError):
    CODES = frozenset({"activity_status_input_invalid", "activity_status_publication_failed", "activity_status_read_failed"})

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in self.CODES else "activity_status_publication_failed"


def _abort(code: str) -> None:
    raise ActivityStatusPublicationV1Error(code)


def _utc(value: Any, optional: bool = True) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("activity_status_input_invalid")
    return value


def _count(value: Any, optional: bool = True) -> int | None:
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000_000:
        _abort("activity_status_input_invalid")
    return value


def _text(value: Any, limit: int = 200, optional: bool = True) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not 0 < len(value) <= limit or any(ord(char) < 32 for char in value):
        _abort("activity_status_input_invalid")
    return value


def _running(value: Any) -> dict[str, Any]:
    keys = {"kind", "origin", "started_at_utc", "step_label", "step_position", "step_count", "done", "total", "expected_end_utc"}
    if not isinstance(value, dict) or set(value) != keys or value["kind"] not in KINDS or value["origin"] not in ORIGINS:
        _abort("activity_status_input_invalid")
    row = {"kind": value["kind"], "origin": value["origin"], "started_at_utc": _utc(value["started_at_utc"]),
           "step_label": _text(value["step_label"], 80), "step_position": _count(value["step_position"]), "step_count": _count(value["step_count"]),
           "done": _count(value["done"]), "total": _count(value["total"]), "expected_end_utc": _utc(value["expected_end_utc"])}
    if (row["done"] is None) != (row["total"] is None) or (row["total"] is not None and row["done"] > row["total"]) \
            or (row["step_position"] is None) != (row["step_count"] is None) \
            or (row["step_count"] is not None and not 1 <= row["step_position"] <= row["step_count"]):
        _abort("activity_status_input_invalid")
    return row


def _last(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"finished_at_utc", "title", "tone", "seconds"} or value["tone"] not in TONES:
        _abort("activity_status_input_invalid")
    return {"finished_at_utc": _utc(value["finished_at_utc"], False), "title": _text(value["title"], 120, False), "tone": value["tone"],
            "seconds": _count(value["seconds"])}


def _next(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"enabled", "times"} or not isinstance(value["enabled"], bool) \
            or not isinstance(value["times"], list) or len(value["times"]) > 6 \
            or not all(isinstance(item, str) and _TIME.fullmatch(item) for item in value["times"]) or len(set(value["times"])) != len(value["times"]):
        _abort("activity_status_input_invalid")
    return {"enabled": value["enabled"], "times": sorted(value["times"])}


def activity_status_body_v1(status: Any) -> dict[str, Any]:
    """Prueft die Form aus R und gibt sie in fester Reihenfolge zurueck."""
    if not isinstance(status, dict) or set(status) != {"running", "last", "next"} or not isinstance(status["running"], list) \
            or len(status["running"]) > 5 or not isinstance(status["last"], dict) or set(status["last"]) != {"refresh", "moment"} \
            or not isinstance(status["next"], dict) or set(status["next"]) != {"refresh", "moment"}:
        _abort("activity_status_input_invalid")
    return {"running": [_running(row) for row in status["running"]],
            "last": {kind: _last(status["last"][kind]) for kind in ("refresh", "moment")},
            "next": {kind: _next(status["next"][kind]) for kind in ("refresh", "moment")}}


def build_activity_status_artifact_v1(context: dict[str, str], status: Any, completed_at_utc: str) -> dict[str, Any]:
    body = {"activity_status_version": VERSION, "status": "completed", "tenant_id": context["tenant_id"], "user_id": context["user_id"],
            "data_space_id": context["data_space_id"], **activity_status_body_v1(status),
            "provider_access": False, "network_access": False, "canonical_write": False}
    content = fingerprint(body)
    artifact = {**body, "activity_status_id": "act_" + content[:32], "content_fingerprint": content, "completed_at_utc": _utc(completed_at_utc, False)}
    artifact["artifact_fingerprint"] = fingerprint(artifact)
    return artifact


def _context(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or not all(isinstance(value.get(key), str) and value.get(key) for key in ("tenant_id", "user_id", "data_space_id")):
        _abort("activity_status_input_invalid")
    return {key: value[key] for key in ("tenant_id", "user_id", "data_space_id")}


def _current(area: Path) -> dict[str, Any] | None:
    try:
        run_id = json.loads((area / "latest.json").read_text(encoding="utf-8")).get("run_id")
        if not isinstance(run_id, str) or "/" in run_id or not run_id.startswith("run_"):
            return None
        return json.loads((area / "runs" / run_id / "artifact.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return None


def _prune(area: Path, keep_run: str) -> int:
    runs = area / "runs"
    if not runs.is_dir() or runs.is_symlink():
        return 0
    candidates = sorted((entry for entry in runs.iterdir() if entry.is_dir() and not entry.is_symlink()
                         and re.fullmatch(r"run_[a-z0-9_]{4,72}", entry.name)), key=lambda entry: entry.stat().st_mtime, reverse=True)
    removed = 0
    for entry in candidates[KEEP_RUNS:]:
        if entry.name != keep_run:
            shutil.rmtree(entry); removed += 1
    return removed


def publish_activity_status_v1(space, context_value, status, published_at_utc: str, artifacts_root=None) -> dict[str, Any]:
    """Veroeffentlicht den Stand, wenn sich der Inhalt gegenueber dem geltenden geaendert hat."""
    context = _context(context_value)
    artifact = build_activity_status_artifact_v1(context, status, published_at_utc)
    root = Path(artifacts_root) if artifacts_root is not None else Path(space) / "artifacts"
    area = root / AREA_ID
    current = _current(area)
    if isinstance(current, dict) and current.get("content_fingerprint") == artifact["content_fingerprint"]:
        return {"activity_status_publication_version": VERSION, "status": "already_published", "canonical_write": False}
    for directory in (root, area):
        if directory.is_symlink():
            _abort("activity_status_publication_failed")
        if not directory.exists():
            directory.mkdir(mode=0o700, parents=True)
        os.chmod(directory, 0o700)
    from workers.reference.run_publication_v1 import PublicationRuntimeContext, RunPublicationError, publish_completed_run_v1
    runtime = PublicationRuntimeContext(context["tenant_id"], context["user_id"], context["data_space_id"], AREA_ID, WRITER_ID, WRITER_ROLE)
    run_id = "run_" + fingerprint({"content": artifact["content_fingerprint"], "published_at_utc": published_at_utc})[:32]
    try:
        published = publish_completed_run_v1(area, runtime, run_id, artifact, published_at_utc)
    except RunPublicationError:
        _abort("activity_status_publication_failed")
    return {"activity_status_publication_version": VERSION, "status": published.status, "pruned_run_count": _prune(area, run_id),
            "canonical_write": False}


READ_ROLES = ("viewer", "tax_viewer", "analysis_viewer", "desktop_owner")


def read_activity_status_v1(space, context_value, artifacts_root=None, role: str = "desktop_owner") -> dict[str, Any]:
    """Der zuletzt veroeffentlichte Stand, geprueft; ohne Veroeffentlichung `absent`. Liest nur, mit der Rolle der App."""
    context = _context(context_value)
    if role not in READ_ROLES:
        _abort("activity_status_input_invalid")
    root = Path(artifacts_root) if artifacts_root is not None else Path(space) / "artifacts"
    area = root / AREA_ID
    if not area.is_dir():
        return {"status": "absent"}
    from apps.reference.latest_run_reader_v1 import LatestRunReaderContext, LatestRunReaderError, read_latest_completed_run_v1
    runtime = LatestRunReaderContext(context["tenant_id"], context["user_id"], context["data_space_id"], AREA_ID, role)
    try:
        artifact = read_latest_completed_run_v1(area, runtime)
    except LatestRunReaderError as error:
        if getattr(error, "code", "") in {"latest_run_reader_no_latest", "run_publication_no_latest"}:
            return {"status": "absent"}
        _abort("activity_status_read_failed")
    body = {key: value for key, value in artifact.items() if key not in ("activity_status_id", "content_fingerprint", "completed_at_utc", "artifact_fingerprint")}
    if artifact.get("activity_status_version") != VERSION or {key: body.get(key) for key in ("tenant_id", "user_id", "data_space_id")} != context \
            or fingerprint(body) != artifact.get("content_fingerprint") \
            or fingerprint({key: value for key, value in artifact.items() if key != "artifact_fingerprint"}) != artifact.get("artifact_fingerprint"):
        _abort("activity_status_read_failed")
    checked = activity_status_body_v1({key: artifact.get(key) for key in ("running", "last", "next")})
    return {"status": "available", "published_at_utc": artifact["completed_at_utc"], **checked}


__all__ = ["AREA_ID", "ARTIFACT_CONTRACT", "ActivityStatusPublicationV1Error", "READ_ROLES", "WRITER_ROLE", "activity_status_body_v1",
           "build_activity_status_artifact_v1", "publish_activity_status_v1", "read_activity_status_v1"]
