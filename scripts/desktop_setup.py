#!/usr/bin/env python3
"""CLI-Grenze des Einrichtungsdialogs (#555): JSON ueber stdin, eine JSON-Zeile auf stdout.

questions: Fragen, Auswahlwerte und Vorgaben.
status: ob der Dialog beim Start erscheint (home, data_space_present).
draft-read / draft-write: der Entwurf ohne Wirkung im Home.
applicable: welche Fragen gestellt werden (Kurse nur mit Marktdaten, Zeitplan nur mit Kursanbieter).
plan / confirm: die Schritte aus Antworten und Stand; confirm bindet die Bestaetigung an den gezeigten Abdruck.
mark: uebernommen oder uebersprungen.
folder-check: ob ein Ordner als Belegordner taugt (#572), mit derselben Regel wie das Festlegen im Eingang.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import desktop_setup_v1 as setup  # noqa: E402

COMMANDS = {
    "questions": ((), (), lambda v: setup.questions_v1()),
    "status": (("home", "data_space_present"), (), lambda v: setup.status_v1(v["home"], v["data_space_present"])),
    "draft-read": (("home",), (), lambda v: {"draft": setup.draft_read_v1(v["home"])}),
    "draft-write": (("home", "answers", "position"), (), lambda v: setup.draft_write_v1(v["home"], v["answers"], v["position"])),
    "plan": (("answers", "current"), (), lambda v: setup.plan_v1(v["answers"], v["current"])),
    "applicable": (("answers",), (), lambda v: setup.applicable_v1(v["answers"])),
    "confirm": (("answers", "current", "plan_fingerprint", "confirmed"), (),
                lambda v: setup.confirm_v1(v["answers"], v["current"], v["plan_fingerprint"], v["confirmed"])),
    "mark": (("home", "status"), ("plan_fingerprint", "results"),
             lambda v: setup.mark_v1(v["home"], v["status"], v.get("plan_fingerprint"), v.get("results"))),
    "folder-check": (("folder", "data_space_path"), (), lambda v: setup.folder_check_v1(v["folder"], v["data_space_path"])),
}


def _emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        if command not in COMMANDS:
            raise setup.DesktopSetupV1Error("desktop_setup_input_invalid")
        required, optional, run = COMMANDS[command]
        value = json.loads(sys.stdin.read() or "{}")
        if not isinstance(value, dict) or not (set(required) <= set(value) <= {*required, *optional}):
            raise setup.DesktopSetupV1Error("desktop_setup_input_invalid")
        _emit({"status": "completed", "result": run(value)})
        return 0
    except (RuntimeError, OSError, KeyError, TypeError, ValueError) as error:
        code = getattr(error, "code", None)
        if not isinstance(code, str) or not code.startswith("desktop_setup_"):
            code = "desktop_setup_input_invalid" if isinstance(error, (ValueError, TypeError, KeyError)) else "desktop_setup_state_invalid"
        _emit({"status": "blocked", "code": code})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
