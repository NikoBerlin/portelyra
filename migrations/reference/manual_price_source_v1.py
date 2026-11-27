"""Owner-entered prices as a provider-free valuation source.

Ein handgepflegter Kurs ist eine Eigentuemerangabe, kein Marktkurs. Er wird
ausdruecklich bestaetigt eingetragen, unveraendert gespeichert und in der
Bewertung als Ersatzwert gekennzeichnet. Luecken sind erlaubt: Die Bewertung
schreibt den zuletzt eingetragenen Wert fort. Kein Providerzugriff, kein
Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import json
import re
import sqlite3

from migrations.reference.trade_price_reference_v1 import read_asset_configuration

AREA = "manual-market-prices-v1"
STORE = "manual-market-prices.sqlite"
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
CURRENCY = re.compile(r"[A-Z]{3}")
FAILURE_CODES = (
    "manual_price_confirmation_required",
    "manual_price_input_invalid",
    "manual_price_store_invalid",
)


class ManualPriceError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise ManualPriceError(code if code in FAILURE_CODES else "manual_price_store_invalid")


def _day(value) -> str:
    if not isinstance(value, str) or DATE.fullmatch(value) is None:
        _abort("manual_price_input_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _abort("manual_price_input_invalid")
    if parsed.isoformat() != value:
        _abort("manual_price_input_invalid")
    return value


def _amount(value) -> str:
    if not isinstance(value, str) or not value.strip():
        _abort("manual_price_input_invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _abort("manual_price_input_invalid")
        return ""
    if not parsed.is_finite() or parsed <= 0:
        _abort("manual_price_input_invalid")
    return value.strip()


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _connect(space, create: bool) -> sqlite3.Connection:
    root = Path(space) / AREA
    store = root / STORE
    if not store.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if store.is_symlink() or root.is_symlink():
        _abort("manual_price_store_invalid")
    connection = sqlite3.connect(store)
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE IF NOT EXISTS manual_price_entry("
        "asset_id TEXT NOT NULL, price_date TEXT NOT NULL, value_decimal TEXT NOT NULL,"
        "currency TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL,"
        "PRIMARY KEY(asset_id, price_date))"
    )
    store.chmod(0o600)
    return connection


def append_manual_price_v1(space, context, asset_id, price_date, value, currency, recorded_at_utc, confirmed):
    """Traegt genau einen bestaetigten Kurs ein; ein zweiter Eintrag zum selben Tag ersetzt ihn."""
    if confirmed is not True:
        _abort("manual_price_confirmation_required")
    asset, _snapshot = read_asset_configuration(space, context, asset_id, "manual")
    day = _day(price_date)
    amount = _amount(value)
    if not isinstance(currency, str) or CURRENCY.fullmatch(currency) is None:
        _abort("manual_price_input_invalid")
    if currency != asset["price_currency"]:
        _abort("manual_price_input_invalid")
    if not isinstance(recorded_at_utc, str) or not recorded_at_utc.endswith("Z"):
        _abort("manual_price_input_invalid")
    entry = {"asset_id": asset_id, "price_date": day, "value_decimal": amount,
             "currency": currency, "recorded_at_utc": recorded_at_utc}
    entry["entry_fingerprint"] = _fingerprint(entry)
    connection = _connect(space, True)
    try:
        connection.execute(
            "INSERT INTO manual_price_entry(asset_id,price_date,value_decimal,currency,recorded_at_utc,entry_fingerprint)"
            " VALUES(?,?,?,?,?,?) ON CONFLICT(asset_id,price_date) DO UPDATE SET"
            " value_decimal=excluded.value_decimal, currency=excluded.currency,"
            " recorded_at_utc=excluded.recorded_at_utc, entry_fingerprint=excluded.entry_fingerprint",
            (asset_id, day, amount, currency, recorded_at_utc, entry["entry_fingerprint"]))
        connection.commit()
    finally:
        connection.close()
    return {"contract_version": "manual_price_source_v1", "status": "recorded", **entry,
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_manual_entries_v1(space, context, asset_id):
    """Alle eingetragenen Kurse eines Assets, aelteste zuerst."""
    read_asset_configuration(space, context, asset_id, "manual")
    connection = _connect(space, False)
    if connection is None:
        return {"contract_version": "manual_price_source_v1", "status": "ready", "entry_count": 0, "entries": [],
                "provider_access": False, "network_access": False, "canonical_write": False}
    try:
        rows = [dict(r) for r in connection.execute(
            "SELECT price_date,value_decimal,currency,recorded_at_utc FROM manual_price_entry"
            " WHERE asset_id=? ORDER BY price_date", (asset_id,))]
    finally:
        connection.close()
    return {"contract_version": "manual_price_source_v1", "status": "ready", "entry_count": len(rows), "entries": rows,
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_manual_source(space, ctx, asset_id, start, end):
    """Tageszeilen im Format der Trade-Preisquelle: eingetragene Tage beobachtet, sonst Luecke."""
    asset, snapshot = read_asset_configuration(space, ctx, asset_id, "manual")
    entries = {row["price_date"]: row for row in read_manual_entries_v1(space, ctx, asset_id)["entries"]}
    rows = []
    barriers = {}
    cursor = date.fromisoformat(_day(start))
    last = date.fromisoformat(_day(end))
    while cursor <= last:
        day = cursor.isoformat()
        entry = entries.get(day)
        if entry is not None and entry["currency"] != asset["price_currency"]:
            barriers[day] = "manual_price_currency_conflict"
            entry = None
        rows.append({"date": day, "status": "observed" if entry is not None else "source_gap",
                     "value": None if entry is None else entry["value_decimal"]})
        cursor += timedelta(days=1)
    return {"source_kind": "owner_recorded_manual_price", "quote_currency": asset["price_currency"],
            "rows": rows, "barriers": barriers, "entry_count": len(entries),
            "canonical_fingerprint": snapshot["source_fingerprint"], "provider_access": False}


__all__ = ["ManualPriceError", "append_manual_price_v1", "read_manual_entries_v1", "read_manual_source", "FAILURE_CODES"]
