#!/usr/bin/env python3
"""CLI-Grenze fuer die Vorabpauschale je Fonds, Konto und Jahr (JSON ueber stdin/stdout)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.advance_lump_sum_v1 import AdvanceLumpSumV1Error  # noqa: E402
from workers.reference.advance_lump_sum_v1 import (  # noqa: E402
    AdvanceLumpSumOverviewV1Error, advance_lump_sum_gaps_v1, advance_lump_sum_overview_v1, record_advance_lump_sums_by_token_v1,
)


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise AdvanceLumpSumOverviewV1Error("advance_lump_sum_overview_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command == "overview":
            space, context = _expect(value, "calculation_year")
            result = advance_lump_sum_overview_v1(space, context, value["calculation_year"])
        elif command == "gaps":
            space, context = _expect(value, "last_calculation_year")
            result = advance_lump_sum_gaps_v1(space, context, value["last_calculation_year"])
        elif command == "record":
            space, context = _expect(value, "calculation_year", "entries", "recorded_at_utc", "confirmed")
            result = record_advance_lump_sums_by_token_v1(space, context, value["calculation_year"], value["entries"], value["recorded_at_utc"],
                                                          value["confirmed"])
        else:
            raise AdvanceLumpSumOverviewV1Error("advance_lump_sum_overview_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (AdvanceLumpSumOverviewV1Error, AdvanceLumpSumV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "advance_lump_sum_overview_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
