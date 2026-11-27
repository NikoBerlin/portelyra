#!/usr/bin/env python3
"""CLI-Grenze des Umfangs je Portfolio (#542, rc.395): JSON ueber stdin, eine JSON-Zeile auf stdout.

catalog: Klassen, Bausteine und Vorschlaege mit Texten.
read: je Portfolio der Umfang (eingerichtet oder nicht) und was im Datenraum laeuft; legt beim ersten Kontakt den Bestandseintrag an.
preview / apply: eine neue Fassung mit Vorschau (Umfang danach, Folgen je Aenderung) und Einmalbestaetigung.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import portfolio_configuration_v1 as configuration  # noqa: E402

CONTEXT_KEYS = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}
COMMANDS = {
    "catalog": ((), lambda s, c, v: configuration.catalog_v1()),
    "read": ((), lambda s, c, v: _read_and_publish_first(s, c)),
    # whole_history (optional, rc.395): Marktdaten ab- oder zuschalten ab dem ersten Tag statt ab heute.
    "preview": (("portfolio_id", "configuration", "origin"), lambda s, c, v: configuration.preview_v1(
        s, c, v["portfolio_id"], v["configuration"], v["origin"], whole_history=v.get("whole_history", False))),
    "apply": (("preview", "confirmed"), lambda s, c, v: _apply_and_publish(s, c, v)),
}


def _publish(space, context, stamp):
    from workers.reference.display_settings_publication_v1 import DisplaySettingsPublicationV1Error, publish_display_settings_v1
    try:
        return publish_display_settings_v1(space, context, stamp).get("status")
    except DisplaySettingsPublicationV1Error:
        return "failed"


def _read_and_publish_first(space, context):
    """Lesen; legt der erste Kontakt den Bestandseintrag an, werden die Einstellungen der Anzeige-Apps gleich mit veroeffentlicht -
    sonst nennte die Data-App den Umfang schon, die Anzeige-Apps erst nach der ersten Aenderung."""
    created = configuration.ensure_baseline_v1(space, context) != "present"
    result = configuration.read_v1(space, context)
    if created:
        from datetime import datetime, timezone
        result["display_settings"] = _publish(space, context, datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ"))
    return result


def _apply_and_publish(space, context, value):
    """Uebernehmen, danach die Einstellungen der Anzeige-Apps neu veroeffentlichen (der Umfang steht darin, #542)."""
    result = configuration.apply_v1(space, context, value["preview"], value["confirmed"])
    from workers.reference.display_settings_publication_v1 import DisplaySettingsPublicationV1Error, publish_display_settings_v1
    try:
        published = publish_display_settings_v1(space, context, result["recorded_at_utc"])
        result["display_settings"] = published.get("status")
    except DisplaySettingsPublicationV1Error:
        result["display_settings"] = "failed"
    return result


def _emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        if command not in COMMANDS:
            raise configuration.PortfolioConfigurationV1Error("portfolio_configuration_input_invalid")
        extra, run = COMMANDS[command]
        value = json.loads(sys.stdin.read())
        optional = {"whole_history"} if command == "preview" else set()
        if not isinstance(value, dict) or not ({"context", "data_space_path", *extra} <= set(value) <= {"context", "data_space_path", *extra, *optional}) \
                or not isinstance(value["context"], dict) \
                or set(value["context"]) != CONTEXT_KEYS or not isinstance(value["data_space_path"], str):
            raise configuration.PortfolioConfigurationV1Error("portfolio_configuration_input_invalid")
        _emit({"status": "completed", "result": run(value["data_space_path"], value["context"], value)})
        return 0
    except (RuntimeError, OSError, KeyError, TypeError, ValueError, sqlite3.Error) as error:
        code = getattr(error, "code", None)
        if not isinstance(code, str) or not code.startswith("portfolio_configuration_"):
            code = "portfolio_configuration_input_invalid" if isinstance(error, (ValueError, TypeError, KeyError)) else "portfolio_configuration_store_invalid"
        _emit({"status": "blocked", "code": code})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
