"""Wertermittlung je Wallet und Coin fuer Kryptowerte (rc.294) - die Wahl des Eigentuemers neben den Stammdaten.

BMF-Schreiben vom 06.03.2025, Rn. 61/62 (im Wortlaut gelesen 21.10.2026): Ist eine Einzelbetrachtung nicht moeglich, gelten
fuer die Haltefrist die zuerst angeschafften Kryptowerte als veraeussert; fuer die Wertermittlung gilt die
Durchschnittsmethode, vereinfachend FIFO. Die Betrachtung ist walletbezogen, die gewaehlte Methode ist bis zur vollstaendigen
Veraeusserung aller Kryptowerte einer Handelsbezeichnung in der Wallet beizubehalten; danach besteht ein neues Wahlrecht.

Festlegung (21.10.2026): Vorgabe ist FIFO walletbezogen; die Durchschnittsmethode ist eine Wahl je Asset und Wallet,
nur fuer Kryptowerte; LIFO bietet das Schreiben nicht an; ein Wechsel nur nach vollstaendiger Veraeusserung in der Wallet.

Ein Eintrag nennt Asset, Konto, Methode und "gueltig ab". Er ist nicht jahresbezogen: Der FIFO-Kern waehlt die Methode, wenn
die Wallet leer war und wieder befuellt wird - die zuletzt gueltig gewordene Wahl. Ein Eintrag mitten in einem Bestand wirkt
deshalb erst nach dessen vollstaendiger Veraeusserung. Der Speicher haengt nur an; je Asset, Konto und Tag gilt der
juengste Eintrag, ein Eintrag ohne Methode nimmt die Wahl dieses Tages zurueck. Kein Providerzugriff, kein Netzzugriff,
kein kanonischer Write. Die Wahl aendert den FIFO-Stand; er wird danach fortgeschrieben.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import hashlib
import json
import re
import sqlite3

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error, _context,
)

AREA = "crypto-valuation-method-v1"
STORE = "crypto-valuation-method.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "crypto_valuation_method_v1"
METHODS = ("fifo", "average")
ASSET_ID = re.compile(r"ast_[a-z0-9_]{4,60}")
ACCOUNT_ID = re.compile(r"acc_[a-z0-9_]{4,60}")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
FAILURE_CODES = (
    "crypto_valuation_method_account_unknown",
    "crypto_valuation_method_asset_not_crypto",
    "crypto_valuation_method_asset_unknown",
    "crypto_valuation_method_confirmation_required",
    "crypto_valuation_method_entry_unknown",
    "crypto_valuation_method_input_invalid",
    "crypto_valuation_method_preview_failed",
    "crypto_valuation_method_store_invalid",
)
SCHEMA = (
    "CREATE TABLE crypto_valuation_method_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE method_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL, account_id TEXT NOT NULL,"
    " valid_from_local_date TEXT NOT NULL, method TEXT CHECK(method IS NULL OR method IN ('fifo','average')),"
    " recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX method_entry_key ON method_entry(asset_id, account_id, valid_from_local_date, entry_id)",
    *(f"CREATE TRIGGER method_entry_no_{action} BEFORE {action.upper()} ON method_entry BEGIN SELECT RAISE(ABORT, 'method_entry_immutable'); END"
      for action in ("update", "delete")),
    "CREATE VIEW current_method_entry AS SELECT entry.* FROM method_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM method_entry later WHERE later.asset_id = entry.asset_id AND later.account_id = entry.account_id"
    " AND later.valid_from_local_date = entry.valid_from_local_date)",
)


class CryptoValuationMethodV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def crypto_valuation_method_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise CryptoValuationMethodV1Error(code if code in FAILURE_CODES else "crypto_valuation_method_store_invalid")


def crypto_valuation_method_context_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("crypto_valuation_method_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("crypto_valuation_method_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("crypto_valuation_method_input_invalid")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("crypto_valuation_method_store_invalid")
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
                connection.execute("INSERT INTO crypto_valuation_method_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("crypto_valuation_method_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM crypto_valuation_method_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("crypto_valuation_method_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("crypto_valuation_method_store_invalid")
    return connection


def _catalog(space, context) -> tuple[dict[str, dict], dict[str, dict]]:
    """Assets und Konten der Stammdaten - gelesen, nicht veraendert."""
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("crypto_valuation_method_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("crypto_valuation_method_store_invalid")
            assets = {row[0]: {"label": row[1], "asset_type": row[2]} for row in connection.execute(
                "SELECT asset_id, display_name, asset_type FROM asset WHERE asset_type <> 'cash'")}
            accounts = {row[0]: {"label": row[1], "account_type": row[2]} for row in connection.execute(
                "SELECT account_id, display_name, account_type FROM account")}
            return assets, accounts
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("crypto_valuation_method_store_invalid")
        return {}, {}


def _stamp(value) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("crypto_valuation_method_input_invalid")
    return value


def _day(value) -> str:
    try:
        if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            _abort("crypto_valuation_method_input_invalid")
    except ValueError:
        _abort("crypto_valuation_method_input_invalid")
    return value


def _current(connection) -> list[dict]:
    rows = connection.execute("SELECT asset_id,account_id,valid_from_local_date,method,recorded_at_utc FROM current_method_entry "
                              "ORDER BY asset_id,account_id,valid_from_local_date").fetchall()
    return [dict(row) for row in rows if row["method"] is not None]


def record_crypto_valuation_method_v1(space, context_value, asset_id, account_id, method, valid_from_local_date,
                                       recorded_at_utc, confirmed) -> dict:
    """Haengt eine Wahl an: Methode ab einem Tag fuer ein Krypto-Asset auf einem Konto. method None nimmt die Wahl dieses
    Tages zurueck. Unveraendert schreibt nichts."""
    if confirmed is not True:
        _abort("crypto_valuation_method_confirmation_required")
    context = crypto_valuation_method_context_v1(context_value)
    stamp = _stamp(recorded_at_utc)
    day = _day(valid_from_local_date)
    if not isinstance(asset_id, str) or ASSET_ID.fullmatch(asset_id) is None or not isinstance(account_id, str) or ACCOUNT_ID.fullmatch(account_id) is None:
        _abort("crypto_valuation_method_input_invalid")
    if method is not None and method not in METHODS:
        _abort("crypto_valuation_method_input_invalid")
    assets, accounts = _catalog(space, context)
    if asset_id not in assets:
        _abort("crypto_valuation_method_asset_unknown")
    if assets[asset_id]["asset_type"] != "crypto":
        _abort("crypto_valuation_method_asset_not_crypto")
    if account_id not in accounts:
        _abort("crypto_valuation_method_account_unknown")
    connection = _connect(space, context, True)
    try:
        with connection:
            current = connection.execute(
                "SELECT method FROM current_method_entry WHERE asset_id=? AND account_id=? AND valid_from_local_date=?",
                (asset_id, account_id, day)).fetchone()
            if (current is None and method is None) or (current is not None and current["method"] == method):
                if current is None and method is None:
                    _abort("crypto_valuation_method_entry_unknown")
                return {"contract_version": CONTRACT, "status": "unchanged", "provider_access": False, "network_access": False, "canonical_write": False}
            row = {"asset_id": asset_id, "account_id": account_id, "valid_from_local_date": day, "method": method, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO method_entry(asset_id,account_id,valid_from_local_date,method,recorded_at_utc,entry_fingerprint) "
                               "VALUES(?,?,?,?,?,?)", (asset_id, account_id, day, method, stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("crypto_valuation_method_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded" if method is not None else "removed", "provider_access": False,
            "network_access": False, "canonical_write": False}


def candidate_methods_v1(space, context_value, asset_id, account_id, method, valid_from_local_date) -> list[dict]:
    """Die Wahlen, wie sie nach dem Speichern dieses Eintrags gaelten - fuer die Vorschau; schreibt nichts. Prueft wie das
    Speichern."""
    context = crypto_valuation_method_context_v1(context_value)
    day = _day(valid_from_local_date)
    if not isinstance(asset_id, str) or ASSET_ID.fullmatch(asset_id) is None or not isinstance(account_id, str) or ACCOUNT_ID.fullmatch(account_id) is None:
        _abort("crypto_valuation_method_input_invalid")
    if method is not None and method not in METHODS:
        _abort("crypto_valuation_method_input_invalid")
    assets, accounts = _catalog(space, context)
    if asset_id not in assets:
        _abort("crypto_valuation_method_asset_unknown")
    if assets[asset_id]["asset_type"] != "crypto":
        _abort("crypto_valuation_method_asset_not_crypto")
    if account_id not in accounts:
        _abort("crypto_valuation_method_account_unknown")
    rows = [row for row in valuation_methods_for_fifo_v1(space, context)
            if (row["asset_ref"], row["account_ref"], row["valid_from_local_date"]) != (asset_id, account_id, day)]
    if method is not None:
        rows.append({"account_ref": account_id, "asset_ref": asset_id, "method": method, "valid_from_local_date": day})
    return sorted(rows, key=lambda row: (row["asset_ref"], row["account_ref"], row["valid_from_local_date"]))


def valuation_methods_for_fifo_v1(space, context_value) -> list[dict]:
    """Die gueltigen Wahlen in der Form des FIFO-Kerns (`valuation_methods`), sortiert. Leer ohne Speicher."""
    context = crypto_valuation_method_context_v1(context_value)
    connection = _connect(space, context, False)
    if connection is None:
        return []
    try:
        rows = _current(connection)
    except sqlite3.Error:
        _abort("crypto_valuation_method_store_invalid")
    finally:
        connection.close()
    return [{"account_ref": row["account_id"], "asset_ref": row["asset_id"], "method": row["method"],
             "valid_from_local_date": row["valid_from_local_date"]} for row in rows]


def read_crypto_valuation_methods_v1(space, context_value) -> dict:
    """Die Wahlen mit Bezeichnungen und die Krypto-Assets und Konten zur Auswahl."""
    context = crypto_valuation_method_context_v1(context_value)
    connection = _connect(space, context, False)
    entries: list[dict] = []
    if connection is not None:
        try:
            entries = _current(connection)
        except sqlite3.Error:
            _abort("crypto_valuation_method_store_invalid")
        finally:
            connection.close()
    assets, accounts = _catalog(space, context)
    rows = [{"asset_id": row["asset_id"], "asset_label": assets.get(row["asset_id"], {}).get("label"),
             "account_id": row["account_id"], "account_label": accounts.get(row["account_id"], {}).get("label"),
             "method": row["method"], "valid_from_local_date": row["valid_from_local_date"], "recorded_at_utc": row["recorded_at_utc"]}
            for row in entries]
    rows.sort(key=lambda row: ((row["asset_label"] or "").casefold(), (row["account_label"] or "").casefold(), row["valid_from_local_date"]))
    return {"contract_version": CONTRACT, "status": "ready", "entries": rows,
            "assets": [{"asset_id": asset, "label": meta["label"]} for asset, meta in sorted(assets.items(), key=lambda item: item[1]["label"].casefold())
                       if meta["asset_type"] == "crypto"],
            "accounts": [{"account_id": account, "label": meta["label"], "account_type": meta["account_type"]}
                         for account, meta in sorted(accounts.items(), key=lambda item: item[1]["label"].casefold())],
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "METHODS", "STORE", "CryptoValuationMethodV1Error", "candidate_methods_v1", "crypto_valuation_method_context_v1",
    "crypto_valuation_method_v1_error_codes", "read_crypto_valuation_methods_v1", "record_crypto_valuation_method_v1",
    "valuation_methods_for_fifo_v1",
]
