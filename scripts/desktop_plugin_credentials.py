#!/usr/bin/env python3
"""CLI-Grenze fuer die Zugaenge der Plugins (#546, rc.389): JSON ueber stdin, eine JSON-Zeile auf stdout.

Werte eines Zugangs kommen nur ueber stdin (nie als Argument oder Umgebungsvariable) und verlassen dieses Skript nur in Richtung
Schluesselbund. Die Ausgabe nennt hoechstens die letzten vier Zeichen; Fehler tragen nur Codes, nie eine Meldung mit Inhalt.

keyring-status: ob der Schluesselbund nutzbar ist. overview: alle Zugaenge maskiert, mit Zustand.
create-preview / create-apply, replace-preview / replace-apply, hosts-preview / hosts-apply, delete-preview / delete-apply,
choice-preview / choice-apply: jede Aenderung an genau ihre Vorschau gebunden. check: ein Testabruf mit einem Zugang.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import plugin_credentials_v1 as credentials  # noqa: E402

CONTEXT_KEYS = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}
COMMANDS = {
    "overview": ((), lambda s, c, v: credentials.overview_v1(s, c)),
    "create-preview": (("plugin_kind", "plugin_id", "label", "values"),
                       lambda s, c, v: credentials.preview_create_v1(s, c, v["plugin_kind"], v["plugin_id"], v["label"], v["values"])),
    "create-apply": (("preview", "values", "confirmed"), lambda s, c, v: credentials.apply_create_v1(s, c, v["preview"], v["values"], v["confirmed"])),
    "replace-preview": (("credential_ref", "values"), lambda s, c, v: credentials.preview_replace_v1(s, c, v["credential_ref"], v["values"])),
    "replace-apply": (("preview", "values", "confirmed"), lambda s, c, v: credentials.apply_replace_v1(s, c, v["preview"], v["values"], v["confirmed"])),
    "hosts-preview": (("credential_ref",), lambda s, c, v: credentials.preview_confirm_hosts_v1(s, c, v["credential_ref"])),
    "hosts-apply": (("preview", "confirmed"), lambda s, c, v: credentials.apply_confirm_hosts_v1(s, c, v["preview"], v["confirmed"])),
    "delete-preview": (("credential_ref",), lambda s, c, v: credentials.preview_delete_v1(s, c, v["credential_ref"])),
    "delete-apply": (("preview", "confirmed"), lambda s, c, v: credentials.apply_delete_v1(s, c, v["preview"], v["confirmed"])),
    "choice-preview": (("provider_id", "credential_ref"), lambda s, c, v: credentials.preview_choice_v1(s, c, v["provider_id"], v["credential_ref"])),
    "choice-apply": (("preview", "confirmed"), lambda s, c, v: credentials.apply_choice_v1(s, c, v["preview"], v["confirmed"])),
    "check": (("credential_ref",), lambda s, c, v: credentials.check_v1(s, c, v["credential_ref"])),
}


def _emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        if command == "keyring-status":
            _emit({"status": "completed", "result": credentials.keyring_status_v1()})
            return 0
        if command not in COMMANDS:
            raise credentials.PluginCredentialsV1Error("plugin_credentials_input_invalid")
        extra, run = COMMANDS[command]
        value = json.loads(sys.stdin.read())
        if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *extra} or not isinstance(value["context"], dict) \
                or set(value["context"]) != CONTEXT_KEYS or not isinstance(value["data_space_path"], str):
            raise credentials.PluginCredentialsV1Error("plugin_credentials_input_invalid")
        result = run(value["data_space_path"], value["context"], value)
        _emit({"status": "completed", "result": result})
        return 0
    except BaseException as error:  # noqa: BLE001 - nur der Code verlaesst das Skript, nie eine Meldung
        code = getattr(error, "code", None)
        if not isinstance(code, str) or not (code.startswith("plugin_credentials_") or code.startswith("price_provider_")):
            code = "plugin_credentials_input_invalid" if isinstance(error, (ValueError, TypeError, KeyError)) else "plugin_credentials_store_invalid"
        _emit({"status": "blocked", "code": code})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
