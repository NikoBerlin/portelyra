"""Vorabpauschale je Fonds, Konto und Jahr - als eigene Buchung mit dem Betrag der Bank (#431).

Festlegung (13.10.2026, per Auswahl): Die Vorabpauschale wird je Fonds und Konto als eigene Buchung mit dem
Betrag der Bank gefuehrt; sie laeuft an den Lots mit und mindert den Gewinn beim Verkauf.

Die Buchung liegt neben dem Buchungsbestand, nicht in ihm: Seine Ereignisarten sind im Schema festgeschrieben, und eine
neue Art haette Buchungsbestand und FIFO-Kern umgebaut. Was die Vorabpauschale steuerlich bewirkt, rechnen Report,
Rechenblatt, Jahresrechnung und Abschluss beim Lesen (`workers/reference/advance_lump_sum_v1.py`):

- Sie gilt am ersten Werktag des Folgejahres als zugeflossen (§ 18 Abs. 3 InvStG) - ein Kapitalertrag des Folgejahres,
  mit der Teilfreistellung des Fonds (§ 20 InvStG).
- Sie verteilt sich auf die Lots, die am 31.12. des Jahres auf dem Konto liegen; im Erwerbsjahr um ein Zwoelftel je
  vollem Monat vor dem Erwerbsmonat gekuerzt (§ 18 Abs. 2 InvStG).
- Beim Verkauf mindert sie den Gewinn in voller Hoehe, ungeachtet der Teilfreistellung (§ 19 Abs. 1 Satz 3 InvStG).

Der Speicher haengt nur an; der gueltige Stand je Fonds, Konto und Jahr ist der juengste Eintrag, ein Eintrag ohne
Betrag leert ihn. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import json
import re
import sqlite3

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error, _context,
)

AREA = "advance-lump-sum-v1"
STORE = "advance-lump-sum.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "advance_lump_sum_v1"
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
AMOUNT = re.compile(r"[0-9]{1,10}(\.[0-9]{1,2})?")
ASSET_ID = re.compile(r"ast_[a-z0-9_]{4,60}")
ACCOUNT_ID = re.compile(r"acc_[a-z0-9_]{4,60}")
FIRST_YEAR = 2018
BATCH_LIMIT = 500
FAILURE_CODES = (
    "advance_lump_sum_confirmation_required",
    "advance_lump_sum_input_invalid",
    "advance_lump_sum_not_a_fund",
    "advance_lump_sum_store_invalid",
)
SCHEMA = (
    "CREATE TABLE advance_lump_sum_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE advance_lump_sum_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL, account_id TEXT NOT NULL,"
    "calculation_year INTEGER NOT NULL CHECK(calculation_year BETWEEN 2018 AND 2100),"
    "amount_decimal TEXT CHECK(amount_decimal IS NULL OR length(amount_decimal) BETWEEN 1 AND 13),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX advance_lump_sum_entry_key ON advance_lump_sum_entry(asset_id, account_id, calculation_year, entry_id)",
    "CREATE TRIGGER advance_lump_sum_entry_no_update BEFORE UPDATE ON advance_lump_sum_entry "
    "BEGIN SELECT RAISE(ABORT, 'advance_lump_sum_entry_immutable'); END",
    "CREATE TRIGGER advance_lump_sum_entry_no_delete BEFORE DELETE ON advance_lump_sum_entry "
    "BEGIN SELECT RAISE(ABORT, 'advance_lump_sum_entry_immutable'); END",
    "CREATE VIEW current_advance_lump_sum AS SELECT entry.* FROM advance_lump_sum_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM advance_lump_sum_entry later "
    "WHERE later.asset_id = entry.asset_id AND later.account_id = entry.account_id AND later.calculation_year = entry.calculation_year)",
)


class AdvanceLumpSumV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def advance_lump_sum_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise AdvanceLumpSumV1Error(code if code in FAILURE_CODES else "advance_lump_sum_store_invalid")


def advance_lump_sum_scope_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("advance_lump_sum_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("advance_lump_sum_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("advance_lump_sum_input_invalid")


def _amount(value):
    """Betrag der Bank in Euro, nicht negativ, hoechstens zwei Nachkommastellen; Komma oder Punkt. Leer heisst: keine Buchung."""
    if value is None:
        return None
    if not isinstance(value, str):
        _abort("advance_lump_sum_input_invalid")
    text = value.strip().replace(",", ".")
    if not text:
        return None
    if AMOUNT.fullmatch(text) is None:
        _abort("advance_lump_sum_input_invalid")
    try:
        number = Decimal(text)
    except InvalidOperation:
        _abort("advance_lump_sum_input_invalid")
    normalized = format(number.normalize(), "f")
    return normalized if "." not in normalized else normalized.rstrip("0").rstrip(".")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("advance_lump_sum_store_invalid")
    expected = (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO advance_lump_sum_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("advance_lump_sum_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM advance_lump_sum_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("advance_lump_sum_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("advance_lump_sum_store_invalid")
    return connection


def _catalog(space, context) -> tuple[dict[str, dict], set[str]]:
    """Fonds und Konten der Stammdaten - gelesen, nicht veraendert."""
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("advance_lump_sum_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("advance_lump_sum_store_invalid")
            assets = {row[0]: {"asset_type": row[1]} for row in connection.execute("SELECT asset_id,asset_type FROM asset")}
            accounts = {row[0] for row in connection.execute("SELECT account_id FROM account")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("advance_lump_sum_store_invalid")
        return {}, set()
    return assets, accounts


def _current(connection) -> dict[tuple[str, str, int], dict]:
    rows = connection.execute("SELECT asset_id,account_id,calculation_year,amount_decimal,recorded_at_utc FROM current_advance_lump_sum").fetchall()
    return {(row["asset_id"], row["account_id"], row["calculation_year"]): dict(row) for row in rows}


def record_advance_lump_sums_v1(space, context_value, entries, recorded_at_utc, confirmed) -> dict:
    """Haengt je Fonds, Konto und Jahr den Betrag der Bank an. Unveraendert schreibt nichts; ohne Betrag leert den Stand."""
    if confirmed is not True:
        _abort("advance_lump_sum_confirmation_required")
    context = advance_lump_sum_scope_v1(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("advance_lump_sum_input_invalid")
    if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= BATCH_LIMIT:
        _abort("advance_lump_sum_input_invalid")
    wanted = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"asset_id", "account_id", "calculation_year", "amount_decimal"}:
            _abort("advance_lump_sum_input_invalid")
        year = entry["calculation_year"]
        if (not isinstance(entry["asset_id"], str) or ASSET_ID.fullmatch(entry["asset_id"]) is None or not isinstance(entry["account_id"], str)
                or ACCOUNT_ID.fullmatch(entry["account_id"]) is None or isinstance(year, bool) or not isinstance(year, int) or not FIRST_YEAR <= year <= 2100):
            _abort("advance_lump_sum_input_invalid")
        wanted.append({"asset_id": entry["asset_id"], "account_id": entry["account_id"], "calculation_year": year,
                       "amount_decimal": _amount(entry["amount_decimal"])})
    if len({(row["asset_id"], row["account_id"], row["calculation_year"]) for row in wanted}) != len(wanted):
        _abort("advance_lump_sum_input_invalid")
    assets, accounts = _catalog(space, context)
    for row in wanted:
        if row["account_id"] not in accounts or row["asset_id"] not in assets:
            _abort("advance_lump_sum_input_invalid")
        # Eine Vorabpauschale gibt es nur bei Investmentfonds.
        if assets[row["asset_id"]]["asset_type"] not in ("fund", "etf"):  # ETF ist ein Investmentfonds (#447)
            _abort("advance_lump_sum_not_a_fund")
    connection = _connect(space, context, True)
    written = unchanged = 0
    try:
        with connection:
            current = _current(connection)
            for row in wanted:
                before = current.get((row["asset_id"], row["account_id"], row["calculation_year"]))
                if (before is None and row["amount_decimal"] is None) or (before is not None and before["amount_decimal"] == row["amount_decimal"]):
                    unchanged += 1
                    continue
                stamped = {**row, "recorded_at_utc": recorded_at_utc}
                connection.execute(
                    "INSERT INTO advance_lump_sum_entry(asset_id,account_id,calculation_year,amount_decimal,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?)",
                    (row["asset_id"], row["account_id"], row["calculation_year"], row["amount_decimal"], recorded_at_utc, _fingerprint(stamped)))
                written += 1
    except sqlite3.Error:
        _abort("advance_lump_sum_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "written_count": written, "unchanged_count": unchanged,
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_advance_lump_sums_v1(space, context_value) -> dict:
    """Die gueltigen Buchungen - mit den Kennungen des Bestands, fuer Rechenkerne. Wer sie liest, gibt die Kennungen nicht weiter."""
    context = advance_lump_sum_scope_v1(context_value)
    connection = _connect(space, context, False)
    if connection is None:
        return {"contract_version": CONTRACT, "status": "ready", "bookings": [], "provider_access": False, "network_access": False, "canonical_write": False}
    try:
        current = _current(connection)
    except sqlite3.Error:
        _abort("advance_lump_sum_store_invalid")
    finally:
        connection.close()
    bookings = [{"asset_id": asset, "account_id": account, "calculation_year": year, "amount_decimal": row["amount_decimal"],
                 "recorded_at_utc": row["recorded_at_utc"]}
                for (asset, account, year), row in sorted(current.items()) if row["amount_decimal"] is not None]
    return {"contract_version": CONTRACT, "status": "ready", "bookings": bookings, "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "STORE", "AdvanceLumpSumV1Error", "advance_lump_sum_scope_v1", "advance_lump_sum_v1_error_codes",
    "read_advance_lump_sums_v1", "record_advance_lump_sums_v1",
]
