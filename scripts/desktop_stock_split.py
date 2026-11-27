#!/usr/bin/env python3
"""CLI-Grenze fuer Aktiensplits (#451) - JSON ueber stdin/stdout.

read: die gueltigen Splits, die Assets und Konten. preview: der FIFO-Stand einmal mit und einmal mit dem angefragten Split - die
Menge vorher und nachher und ob der Kern ihn annimmt. record: speichert den Split; remove nimmt ihn zurueck. Nach dem Speichern
schreibt die Data-App den FIFO-Stand fort und veroeffentlicht die Tageshistorie neu.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.stock_split_v1 import (  # noqa: E402
    StockSplitV1Error, candidate_splits_v1, read_stock_splits_v1, record_stock_split_v1, split_ref_v1, stock_split_context_v1,
)
from workers.reference.asset_activity_realized_state_v2 import (  # noqa: E402
    AssetActivityRealizedStateV2Error, preview_stock_splits_v2,
)

# Fehlercodes des Kerns, die die Vorschau in Worten nennt; alles andere heisst "nicht moeglich".
KERNEL_REASONS = {
    "semantic_realized_fifo_v2_split_inexact": "split_inexact",
    "semantic_realized_fifo_v2_inventory_insufficient": "inventory_insufficient",
    "semantic_realized_fifo_v2_custody_inventory_insufficient": "inventory_insufficient",
    "semantic_realized_fifo_v2_input_invalid": "split_invalid",
}


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise StockSplitV1Error("stock_split_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def preview(space, context, asset_id, account_id, effective_local_date, ratio_numerator, ratio_denominator, remove=False):
    checked = stock_split_context_v1(context)
    candidate = candidate_splits_v1(space, checked, asset_id, account_id, effective_local_date, ratio_numerator, ratio_denominator,
                                    remove=remove)
    ref = split_ref_v1(asset_id, account_id, effective_local_date)
    try:
        worlds = preview_stock_splits_v2(space, checked, candidate)["worlds"]
    except AssetActivityRealizedStateV2Error as error:
        raise StockSplitV1Error("stock_split_store_invalid") from error
    rows, blocked = [], None
    for world in worlds:
        if world["failure_code"] is not None:
            blocked = KERNEL_REASONS.get(world["failure_code"], "split_invalid")
            continue
        asset = world["asset_ref"]
        before = next((row["remaining_quantity_decimal"] for row in world["current"]["asset_positions"] if row["asset_ref"] == asset), None)
        after = next((row["remaining_quantity_decimal"] for row in world["candidate"]["asset_positions"] if row["asset_ref"] == asset), None)
        step = next((row for row in world["candidate"].get("split_results", []) if row["split_ref"] == ref), None)
        rows.append({"asset_id": asset, "quantity_now": before, "quantity_after": after,
                     "quantity_before_split": None if step is None else step["asset_quantity_before_decimal"],
                     "quantity_after_split": None if step is None else step["asset_quantity_after_decimal"]})
    return {"contract_version": "stock_split_v1", "status": "blocked" if blocked else "previewed", "reason": blocked,
            "split_ref": ref, "worlds": rows, "provider_access": False, "network_access": False, "canonical_write": False}


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        fields = ("asset_id", "account_id", "effective_local_date", "ratio_numerator", "ratio_denominator")
        if command == "read":
            space, context = _expect(value)
            result = read_stock_splits_v1(space, context)
        elif command == "preview":
            space, context = _expect(value, *fields, "remove")
            result = preview(space, context, *(value[name] for name in fields), remove=value["remove"] is True)
        elif command == "record":
            space, context = _expect(value, *fields, "note", "recorded_at_utc", "confirmed")
            result = record_stock_split_v1(space, context, *(value[name] for name in fields), value["note"], value["recorded_at_utc"],
                                           value["confirmed"])
        elif command == "remove":
            space, context = _expect(value, "asset_id", "account_id", "effective_local_date", "recorded_at_utc", "confirmed")
            result = record_stock_split_v1(space, context, value["asset_id"], value["account_id"], value["effective_local_date"], None, None,
                                           None, value["recorded_at_utc"], value["confirmed"], remove=True)
        else:
            raise StockSplitV1Error("stock_split_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (StockSplitV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "stock_split_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
