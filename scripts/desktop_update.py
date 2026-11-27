#!/usr/bin/env python3
"""CLI-Grenze der Update-Suche (#562): JSON ueber stdin, eine JSON-Zeile auf stdout.

check: eine Abfrage der Release-Liste (home, running, trigger "click" oder "daily"); das Ergebnis steht danach in update-status.json.
due: ob die taegliche Suche faellig ist (nur mit Zustimmung, hoechstens einmal am Tag).
status: das zuletzt gespeicherte Ergebnis, ohne Netz.
download: das Archiv der zuletzt gefundenen Version herunterladen und pruefen (Groesse, digest); die Signatur prueft release-check.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import desktop_update_v1 as update  # noqa: E402

COMMANDS = {
    "check": (("home", "running", "trigger"), (), lambda v: update.check_v1(v["home"], v["running"], v["trigger"])),
    "due": (("home",), (), lambda v: update.due_v1(v["home"])),
    "status": (("home",), (), lambda v: {"status": update.status_read_v1(v["home"])}),
    "download": (("home", "version", "running"), (), lambda v: update.download_v1(v["home"], v["version"], v["running"])),
}


def _emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        if command not in COMMANDS:
            raise update.DesktopUpdateV1Error("desktop_update_input_invalid")
        required, optional, run = COMMANDS[command]
        value = json.loads(sys.stdin.read() or "{}")
        if not isinstance(value, dict) or not (set(required) <= set(value) <= {*required, *optional}):
            raise update.DesktopUpdateV1Error("desktop_update_input_invalid")
        _emit({"status": "completed", "result": run(value)})
        return 0
    except (RuntimeError, OSError, KeyError, TypeError, ValueError) as error:
        code = getattr(error, "code", None)
        if not isinstance(code, str) or code not in update.FAILURE_CODES:
            code = "desktop_update_input_invalid" if isinstance(error, (ValueError, TypeError, KeyError)) else "desktop_update_state_invalid"
        _emit({"status": "blocked", "code": code})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
