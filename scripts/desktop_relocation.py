#!/usr/bin/env python3
"""CLI-Grenze fuer den Ursprungsort nach einem Restore an einen anderen Ort (#493): JSON ueber stdin, eine JSON-Zeile auf stdout.

Eingabe: {"data_space_path": <Datenraum>, "confirmed": true, "origin": <frueherer Datenraum oder null>}. Ohne `origin` sucht der Kern den
frueheren Ort in den Auftraegen des Run Centers; vermerkt wird nur, was gegen die gespeicherten Bindungen geprueft ist.

`status` (nur lesend, #556): {"data_space_path": <Datenraum>} -> ob der Datenraum hier gebunden ist und welche Speicher sonst abweisen.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import data_space_relocation_v1 as relocation  # noqa: E402


def main() -> int:
    try:
        value = json.loads(sys.stdin.read())
        if sys.argv[1:] == ["status"]:
            if not isinstance(value, dict) or set(value) != {"data_space_path"} or not isinstance(value["data_space_path"], str):
                raise relocation.DataSpaceRelocationV1Error("data_space_relocation_input_invalid")
            print(json.dumps({"status": "completed", "result": relocation.status_v1(value["data_space_path"])}, sort_keys=True, ensure_ascii=False))
            return 0
        if sys.argv[1:]:
            raise relocation.DataSpaceRelocationV1Error("data_space_relocation_input_invalid")
        if not isinstance(value, dict) or not {"data_space_path", "confirmed"} <= set(value) <= {"data_space_path", "confirmed", "origin"} \
                or not isinstance(value["data_space_path"], str) or not (value.get("origin") is None or isinstance(value["origin"], str)):
            raise relocation.DataSpaceRelocationV1Error("data_space_relocation_input_invalid")
        result = relocation.relocate_v1(value["data_space_path"], value["confirmed"], value.get("origin"))
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True))
        return 0
    except relocation.DataSpaceRelocationV1Error as error:
        print(json.dumps({"status": "blocked", "code": error.code}, sort_keys=True))
        return 2
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "blocked", "code": "data_space_relocation_input_invalid"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
