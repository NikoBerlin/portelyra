#!/usr/bin/env python3
"""CLI-Grenze fuer die FIFO-Wallet aus mehreren Konten (#508) - JSON ueber stdin/stdout.

entries: nur die Zuordnungen (fuer die Kontenliste, ohne Lot-Spur). read: die Zuordnungen, die Krypto-Konten je Institut und als Hinweis die Verkaeufe, waehrend derselbe Coin auf einem anderen,
nicht zugeordneten Konto desselben Instituts lag (Festlegung 23.10.2026: nur ohne Zuordnung). preview: dieselbe Rechnung mit der
angefragten Zuordnung - welche Verkaeufe sich aendern und um wie viel je Jahr. record: speichert die Zuordnung. Nach dem
Speichern schreibt die Data-App den FIFO-Stand fort und veroeffentlicht die Tageshistorie neu.
"""
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.exact_amount_v1 import amount_text_v1  # noqa: E402
from migrations.reference.fifo_wallet_v1 import (  # noqa: E402
    FifoWalletV1Error, candidate_fifo_wallets_v1, fifo_wallet_context_v1, read_fifo_wallets_v1, record_fifo_wallet_v1,
)
from workers.reference.asset_activity_realized_state_v2 import (  # noqa: E402
    AssetActivityRealizedStateV2Error, preview_fifo_wallets_v2, read_asset_activity_realized_lot_trace_v2,
)


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise FifoWalletV1Error("fifo_wallet_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def _amount(value):
    if not isinstance(value, dict):
        return None
    if value.get("decimal") is not None:
        return Fraction(value["decimal"])
    if value.get("numerator_integer") is not None and value.get("denominator_integer") is not None:
        return Fraction(int(value["numerator_integer"]), int(value["denominator_integer"]))
    return None


def _shared_sales(worlds, accounts, wallets):
    """Verkaeufe, waehrend derselbe Coin auf einem anderen Krypto-Konto desselben Instituts lag, das nicht zur Wallet gehoert."""
    institution = {row["account_id"]: (row["institution"] or "").casefold() for row in accounts}
    wallet = lambda account: wallets.get(account, account)
    rows = []
    for world in worlds:
        dates = {event["event_ref"]: event["local_date"] for event in world["asset_activity"]["events"]}
        held: dict[str, Fraction] = {}
        for row in world["result"]["event_results"]:
            account = row["account_ref"]
            if row["event_type"] == "sell" and institution.get(account):
                others = sorted(other for other, quantity in held.items() if quantity > 0 and other != account
                                and institution.get(other) == institution[account] and wallet(other) != wallet(account))
                if others:
                    rows.append({"local_date": dates.get(row["event_ref"]), "asset_id": row["asset_ref"], "account_id": account,
                                 "other_account_ids": others})
            held[account] = Fraction(row["custody_quantity_after_decimal"] or "0")
            if row["related_account_ref"] is not None and row["destination_custody_quantity_after_decimal"] is not None:
                held[row["related_account_ref"]] = Fraction(row["destination_custody_quantity_after_decimal"])
    rows.sort(key=lambda item: (item["local_date"] or "", item["asset_id"], item["account_id"]))
    return rows


def read(space, context):
    result = read_fifo_wallets_v1(space, context)
    wallets = {row["account_id"]: row["wallet_account_id"] for row in result["entries"]}
    try:
        trace = read_asset_activity_realized_lot_trace_v2(space, fifo_wallet_context_v1(context))
    except AssetActivityRealizedStateV2Error:
        trace = {"freshness": "unavailable", "worlds": []}
    result["shared_sales"] = _shared_sales(trace["worlds"], result["accounts"], wallets)
    result["fifo_freshness"] = trace["freshness"]
    return result


def preview(space, context, account_id, wallet_account_id):
    checked = fifo_wallet_context_v1(context)
    candidate = candidate_fifo_wallets_v1(space, checked, account_id, wallet_account_id)
    try:
        worlds = preview_fifo_wallets_v2(space, checked, candidate)["worlds"]
    except AssetActivityRealizedStateV2Error as error:
        raise FifoWalletV1Error("fifo_wallet_preview_failed") from error
    years: dict[str, dict] = {}
    changed = 0
    for world in worlds:
        dates = {event["event_ref"]: event["local_date"] for event in world["asset_activity"]["events"]}
        before = {row["event_ref"]: row for row in world["current"]["result"]["event_results"]}
        for row in world["candidate"]["result"]["event_results"]:
            if row["event_type"] != "sell":
                continue
            old, new = _amount(before[row["event_ref"]]["realized_gain"]), _amount(row["realized_gain"])
            year = years.setdefault(dates[row["event_ref"]][:4], {"sales": 0, "changed": 0, "delta": Fraction(0)})
            year["sales"] += 1
            if old != new and old is not None and new is not None:
                year["changed"] += 1; year["delta"] += new - old; changed += 1
    return {"contract_version": "fifo_wallet_v1", "status": "previewed", "world_count": len(worlds), "changed_sales": changed,
            "years": [{"year": int(year), "sales": row["sales"], "changed": row["changed"], "realized_delta": amount_text_v1(row["delta"])}
                      for year, row in sorted(years.items())],
            "provider_access": False, "network_access": False, "canonical_write": False}


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command == "entries":
            space, context = _expect(value)
            result = {key: read_fifo_wallets_v1(space, context)[key] for key in ("contract_version", "status", "entries")}
        elif command == "read":
            space, context = _expect(value)
            result = read(space, context)
        elif command == "preview":
            space, context = _expect(value, "account_id", "wallet_account_id")
            result = preview(space, context, value["account_id"], value["wallet_account_id"])
        elif command == "record":
            space, context = _expect(value, "account_id", "wallet_account_id", "recorded_at_utc", "confirmed")
            result = record_fifo_wallet_v1(space, context, value["account_id"], value["wallet_account_id"], value["recorded_at_utc"],
                                           value["confirmed"])
        else:
            raise FifoWalletV1Error("fifo_wallet_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (FifoWalletV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "fifo_wallet_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
