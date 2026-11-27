#!/usr/bin/env python3
"""CLI-Grenze fuer die Einstellungen der Analyse: Vergleichsindizes (#482, #502) und eigene Asset-Gruppen (#483) - JSON ueber stdin/stdout."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.analysis_settings_v1 import (  # noqa: E402
    AnalysisSettingsV1Error, read_analysis_settings_v1, record_asset_group_v1, record_benchmark_index_v1, remove_asset_group_v1,
    remove_benchmark_index_v1,
)


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise AnalysisSettingsV1Error("analysis_settings_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command == "read":
            space, context = _expect(value)
            result = read_analysis_settings_v1(space, context)
        elif command == "record-index":
            space, context = _expect(value, "index_key", "label", "components", "recorded_at_utc", "confirmed")
            result = record_benchmark_index_v1(space, context, value["index_key"], value["label"], value["components"],
                                               value["recorded_at_utc"], value["confirmed"])
        elif command == "remove-index":
            space, context = _expect(value, "index_key", "recorded_at_utc", "confirmed")
            result = remove_benchmark_index_v1(space, context, value["index_key"], value["recorded_at_utc"], value["confirmed"])
        elif command == "record-group":
            space, context = _expect(value, "group_key", "label", "partition", "members", "recorded_at_utc", "confirmed")
            result = record_asset_group_v1(space, context, value["group_key"], value["label"], value["partition"], value["members"],
                                           value["recorded_at_utc"], value["confirmed"])
        elif command == "remove-group":
            space, context = _expect(value, "group_key", "recorded_at_utc", "confirmed")
            result = remove_asset_group_v1(space, context, value["group_key"], value["recorded_at_utc"], value["confirmed"])
        else:
            raise AnalysisSettingsV1Error("analysis_settings_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (AnalysisSettingsV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "analysis_settings_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
