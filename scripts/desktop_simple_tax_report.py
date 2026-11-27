#!/usr/bin/env python3
"""CLI-Grenze fuer den einfachen Steuerreport (JSON ueber stdin/stdout).

`build` und `notes-read` lesen nur. `notes-save` schreibt die festen Hinweise zum Report -
ausdruecklich bestaetigt und nicht aus der Tax-Oberflaeche, die nur liest.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.simple_tax_report_notes_v1 import (  # noqa: E402
    SimpleTaxReportNotesV1Error, read_simple_tax_report_notes_v1, save_simple_tax_report_notes_v1,
)
from workers.reference.simple_tax_report_v1 import (  # noqa: E402
    SimpleTaxReportV1Error, build_simple_tax_report_v1, render_simple_tax_report_csv_v1, simple_tax_report_choices_v1,
    simple_tax_report_method_lines_v1,
)


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command in ("notes-read", "notes-save"):
            wanted = {"context", "data_space_path"} | ({"notes", "recorded_at_utc", "confirmed"} if command == "notes-save" else set())
            if not isinstance(value, dict) or set(value) != wanted:
                raise SimpleTaxReportNotesV1Error("simple_tax_report_notes_input_invalid")
            result = read_simple_tax_report_notes_v1(Path(value["data_space_path"]), value["context"]) if command == "notes-read" else (
                save_simple_tax_report_notes_v1(Path(value["data_space_path"]), value["context"], value["notes"], value["recorded_at_utc"], value["confirmed"]))
            print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            return 0
        if command == "choices":
            if not isinstance(value, dict) or set(value) != {"context", "data_space_path", "asset_types"}:
                raise SimpleTaxReportV1Error("simple_tax_report_input_invalid")
            result = simple_tax_report_choices_v1(Path(value["data_space_path"]), value["context"], value["asset_types"])
            print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
            return 0
        expected = {"context", "data_space_path", "tax_year", "asset_types", "notes", "generated_at_utc"}
        if command != "build" or not isinstance(value, dict) or set(value) - {"selection"} != expected:
            raise SimpleTaxReportV1Error("simple_tax_report_input_invalid")
        notes = value["notes"]
        generated = value["generated_at_utc"]
        if not isinstance(notes, list) or any(not isinstance(note, str) or len(note) > 2000 for note in notes) or len(notes) > 20 or (
                not isinstance(generated, str) or len(generated) != 20 or not generated.endswith("Z")):
            raise SimpleTaxReportV1Error("simple_tax_report_input_invalid")
        model = build_simple_tax_report_v1(Path(value["data_space_path"]), value["context"], value["tax_year"], value["asset_types"],
                                           value.get("selection"))
        result = {"model": model, "method_lines": simple_tax_report_method_lines_v1(model),
                  "csv": render_simple_tax_report_csv_v1(model, generated, notes)}
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (SimpleTaxReportV1Error, SimpleTaxReportNotesV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "simple_tax_report_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
