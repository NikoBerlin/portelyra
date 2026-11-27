#!/usr/bin/env python3
"""CLI-Grenze fuer die Wertermittlung je Wallet und Coin (rc.294) - JSON ueber stdin/stdout.

read: die Wahlen mit den Abschnitten je Wallet aus dem FIFO-Stand; preview: dieselbe Rechnung mit der angefragten Wahl - welche
Verkaeufe der Wallet sich aendern und um wie viel je Jahr; record: speichert die Wahl. Nach dem Speichern schreibt die Data-App
den FIFO-Stand fort und veroeffentlicht die Tageshistorie neu.
"""
import json
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.crypto_valuation_method_v1 import (  # noqa: E402
    CryptoValuationMethodV1Error, candidate_methods_v1, crypto_valuation_method_context_v1, read_crypto_valuation_methods_v1,
    record_crypto_valuation_method_v1, valuation_methods_for_fifo_v1,
)
from migrations.reference.exact_amount_v1 import amount_text_v1  # noqa: E402
from workers.reference.asset_activity_realized_state_v2 import (  # noqa: E402
    AssetActivityRealizedStateV2Error, preview_valuation_methods_v2, read_asset_activity_realized_lot_trace_v2,
)


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise CryptoValuationMethodV1Error("crypto_valuation_method_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def _amount(value):
    if not isinstance(value, dict):
        return None
    if value.get("decimal") is not None:
        return Fraction(value["decimal"])
    if value.get("numerator_integer") is not None and value.get("denominator_integer") is not None:
        return Fraction(int(value["numerator_integer"]), int(value["denominator_integer"]))
    return None


def _segments(trace_worlds, wallets):
    rows = []
    for world in trace_worlds:
        for segment in world.get("wallet_segments", []):
            if (segment["asset_ref"], segment["account_ref"]) in wallets:
                rows.append({"asset_id": segment["asset_ref"], "account_id": segment["account_ref"], "start_local_date": segment["start_local_date"],
                             "method": segment["method"]})
    return rows


def read(space, context):
    """Die Wahlen, die Abschnitte ihrer Wallets und je Coin die Konten, auf denen er je lag (fuer die Auswahl)."""
    result = read_crypto_valuation_methods_v1(space, context)
    wallets = {(row["asset_id"], row["account_id"]) for row in result["entries"]}
    try:
        trace = read_asset_activity_realized_lot_trace_v2(space, crypto_valuation_method_context_v1(context))
    except AssetActivityRealizedStateV2Error:
        trace = {"freshness": "unavailable", "worlds": []}
    coins = {row["asset_id"] for row in result["assets"]}
    held = sorted({(segment["asset_ref"], segment["account_ref"]) for world in trace["worlds"] for segment in world.get("wallet_segments", [])
                   if segment["asset_ref"] in coins})
    result["segments"] = _segments(trace["worlds"], wallets)
    result["fifo_freshness"] = trace["freshness"]
    result["wallets"] = [{"asset_id": asset, "account_id": account} for asset, account in held]
    return result


def preview(space, context, asset_id, account_id, method, valid_from):
    checked = crypto_valuation_method_context_v1(context)
    candidate = candidate_methods_v1(space, checked, asset_id, account_id, method, valid_from)
    try:
        worlds = preview_valuation_methods_v2(space, checked, asset_id, candidate)["worlds"]
    except AssetActivityRealizedStateV2Error as error:
        raise CryptoValuationMethodV1Error("crypto_valuation_method_preview_failed") from error
    years: dict[str, dict] = {}
    changed = 0
    for world in worlds:
        dates = {event["event_ref"]: event["local_date"] for event in world["asset_activity"]["events"]}
        before = {row["event_ref"]: row for row in world["current"]["result"]["event_results"]}
        for row in world["candidate"]["result"]["event_results"]:
            if row["event_type"] != "sell" or row["account_ref"] != account_id:
                continue
            old, new = _amount(before[row["event_ref"]]["realized_gain"]), _amount(row["realized_gain"])
            year = years.setdefault(dates[row["event_ref"]][:4], {"sales": 0, "changed": 0, "delta": Fraction(0)})
            year["sales"] += 1
            if old != new and old is not None and new is not None:
                year["changed"] += 1; year["delta"] += new - old; changed += 1
    wallet = {(asset_id, account_id)}
    return {"contract_version": "crypto_valuation_method_v1", "status": "previewed",
            "segments_current": _segments([world["current"] for world in worlds], wallet),
            "segments_candidate": _segments([world["candidate"] for world in worlds], wallet),
            "changed_sales": changed,
            "years": [{"year": int(year), "sales": row["sales"], "changed": row["changed"], "realized_delta": amount_text_v1(row["delta"])}
                      for year, row in sorted(years.items())],
            "provider_access": False, "network_access": False, "canonical_write": False}


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command == "read":
            space, context = _expect(value)
            result = read(space, context)
        elif command == "preview":
            space, context = _expect(value, "asset_id", "account_id", "method", "valid_from_local_date")
            result = preview(space, context, value["asset_id"], value["account_id"], value["method"], value["valid_from_local_date"])
        elif command == "record":
            space, context = _expect(value, "asset_id", "account_id", "method", "valid_from_local_date", "recorded_at_utc", "confirmed")
            result = record_crypto_valuation_method_v1(space, context, value["asset_id"], value["account_id"], value["method"],
                                                       value["valid_from_local_date"], value["recorded_at_utc"], value["confirmed"])
        else:
            raise CryptoValuationMethodV1Error("crypto_valuation_method_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (CryptoValuationMethodV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "crypto_valuation_method_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
