#!/usr/bin/env python3
"""CLI-Grenze fuer die Unterlagen eines Steuerjahres (JSON ueber stdin/stdout).

`build` liest den Datenraum und schreibt genau eine Datei: das Archiv am genannten Ort ausserhalb des Datenraums.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from workers.reference.tax_year_documents_v1 import TaxYearDocumentsV1Error, build_tax_year_documents_v1  # noqa: E402


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        expected = {"context", "data_space_path", "tax_year", "asset_types", "scope", "attachments", "target_path", "generated_at_utc"}
        if command != "build" or not isinstance(value, dict) or set(value) != expected:
            raise TaxYearDocumentsV1Error("tax_year_documents_input_invalid")
        result = build_tax_year_documents_v1(
            Path(value["data_space_path"]), value["context"], value["tax_year"], value["asset_types"], value["scope"], value["attachments"],
            value["target_path"], value["generated_at_utc"])
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (TaxYearDocumentsV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "tax_year_documents_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
