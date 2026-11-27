#!/usr/bin/env python3
"""CLI-Grenze fuer Belegangaben zu Buchungen (JSON ueber stdin/stdout)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.asset_activity_reference_v1 import (  # noqa: E402
    AssetActivityReferenceV1Error, carry_activity_reference_v1, read_activity_disposal_values_v1, read_activity_references_v1,
    record_activity_disposal_value_v1, record_activity_references_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityV1Error  # noqa: E402
from migrations.reference.legacy_activity_reference_backfill_v1 import (  # noqa: E402
    apply_legacy_activity_reference_backfill_v1, plan_legacy_activity_reference_backfill_v1,
)
from migrations.reference.statement_activity_reference_backfill_v1 import (  # noqa: E402
    apply_statement_activity_reference_backfill_v1, plan_statement_activity_reference_backfill_v1,
)


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise AssetActivityReferenceV1Error("activity_reference_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command == "read":
            space, context = _expect(value, "event_refs")
            result = read_activity_references_v1(space, context, value["event_refs"])
        elif command == "record":
            space, context = _expect(value, "entries", "recorded_at_utc", "confirmed")
            result = record_activity_references_v1(space, context, value["entries"], "owner_entered", value["recorded_at_utc"], value["confirmed"])
        elif command == "value-read":
            space, context = _expect(value)
            result = read_activity_disposal_values_v1(space, context)
        elif command == "value-record":
            space, context = _expect(value, "event_ref", "value_eur_decimal", "recorded_at_utc", "confirmed")
            result = record_activity_disposal_value_v1(space, context, value["event_ref"], value["value_eur_decimal"], value["recorded_at_utc"], value["confirmed"])
        elif command == "carry":
            space, context = _expect(value, "predecessor_event_ref", "successor_event_ref", "recorded_at_utc")
            result = carry_activity_reference_v1(space, context, value["predecessor_event_ref"], value["successor_event_ref"], value["recorded_at_utc"])
        elif command == "legacy-plan":
            space, context = _expect(value, "legacy_transaction_root")
            plan = plan_legacy_activity_reference_backfill_v1(space, context, value["legacy_transaction_root"])
            # Die Angaben selbst bleiben im Prozess; nach aussen gehen nur Zaehler.
            result = {key: plan[key] for key in plan if key != "entries"}
        elif command == "legacy-apply":
            space, context = _expect(value, "legacy_transaction_root", "recorded_at_utc", "confirmed")
            result = apply_legacy_activity_reference_backfill_v1(space, context, value["legacy_transaction_root"], value["recorded_at_utc"], value["confirmed"])
        elif command == "statement-plan":
            space, context = _expect(value, "statement_root")
            plan = plan_statement_activity_reference_backfill_v1(space, context, value["statement_root"])
            result = {key: plan[key] for key in plan if key != "entries"}
        elif command == "statement-apply":
            space, context = _expect(value, "statement_root", "recorded_at_utc", "confirmed")
            result = apply_statement_activity_reference_backfill_v1(space, context, value["statement_root"], value["recorded_at_utc"], value["confirmed"])
        else:
            raise AssetActivityReferenceV1Error("activity_reference_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (AssetActivityReferenceV1Error, DesktopProductAssetActivityV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "activity_reference_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
