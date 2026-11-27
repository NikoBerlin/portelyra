#!/usr/bin/env python3
"""CLI-Grenze fuer die Rechenblaetter je Ereignis (JSON ueber stdin/stdout). `build` liest nur."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from workers.reference.tax_event_sheet_v1 import (  # noqa: E402
    TaxEventSheetV1Error, build_tax_event_sheets_v1, render_tax_event_sheet_csv_v1,
)


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        expected = {"context", "data_space_path", "tax_year", "asset_types", "generated_at_utc"}
        if command != "build" or not isinstance(value, dict) or set(value) - {"selection"} != expected:
            raise TaxEventSheetV1Error("tax_event_sheet_input_invalid")
        generated = value["generated_at_utc"]
        if not isinstance(generated, str) or len(generated) != 20 or not generated.endswith("Z"):
            raise TaxEventSheetV1Error("tax_event_sheet_input_invalid")
        model = build_tax_event_sheets_v1(Path(value["data_space_path"]), value["context"], value["tax_year"], value["asset_types"],
                                          selection=value.get("selection"))
        result = {"model": model, "csv": render_tax_event_sheet_csv_v1(model, generated)}
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (TaxEventSheetV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "tax_event_sheet_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
