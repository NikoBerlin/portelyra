"""Gehoert ein Cash-Konto zur Anlage? Die Grenze, an der die Rendite externe Zu- und Abfluesse misst (#481).

Festlegung (20.10.2026): Girokonten, auf die Gehalt und sonstige Einnahmen fliessen, liegen ausserhalb der Anlage;
Tagesgeld-, Verrechnungs- und Depotkonten und Wallets liegen innerhalb. Festgelegt wird das je Konto, nicht je Umsatz:
Eine Ueberweisung vom Giro aufs Tagesgeld ist aus Sicht der Anlage eine Einlage, gleich woher das Geld vorher kam.

Die Angabe ist eine Sicht auf den Bestand, keine Wirtschaftstatsache. Sie liegt deshalb wie die Kontonummer neben den
Stammdaten (account_reference_v1): Buchungsbestand, FIFO und Bewertung beruehrt sie nicht. Der Speicher haengt nur an;
der gueltige Stand je Konto ist der juengste Eintrag, ein Eintrag ohne Wert leert ihn. Ein Konto ohne Angabe zaehlt zur
Anlage - die Rechnung nimmt nichts heimlich heraus; die Anzeige nennt, wie viele Konten noch keine Angabe tragen.
Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sqlite3

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error, _context,
)

AREA = "investment-scope-v1"
STORE = "investment-scope.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "investment_scope_v1"
ACCOUNT_ID = re.compile(r"acc_[a-z0-9_]{4,60}")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
BATCH_LIMIT = 500
# Konten, deren Saldo im Cash zaehlt; nur sie stehen zur Wahl.
CASH_ACCOUNT_TYPES = ("cash", "bank")
FAILURE_CODES = (
    "investment_scope_account_unknown",
    "investment_scope_confirmation_required",
    "investment_scope_input_invalid",
    "investment_scope_store_invalid",
)
SCHEMA = (
    "CREATE TABLE investment_scope_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE investment_scope_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,"
    "in_investment INTEGER CHECK(in_investment IS NULL OR in_investment IN (0, 1)),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX investment_scope_entry_account ON investment_scope_entry(account_id, entry_id)",
    "CREATE TRIGGER investment_scope_entry_no_update BEFORE UPDATE ON investment_scope_entry "
    "BEGIN SELECT RAISE(ABORT, 'investment_scope_entry_immutable'); END",
    "CREATE TRIGGER investment_scope_entry_no_delete BEFORE DELETE ON investment_scope_entry "
    "BEGIN SELECT RAISE(ABORT, 'investment_scope_entry_immutable'); END",
    "CREATE VIEW current_investment_scope AS SELECT entry.* FROM investment_scope_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM investment_scope_entry later WHERE later.account_id = entry.account_id)",
)


class InvestmentScopeV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def investment_scope_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise InvestmentScopeV1Error(code if code in FAILURE_CODES else "investment_scope_store_invalid")


def investment_scope_context_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("investment_scope_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("investment_scope_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("investment_scope_input_invalid")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("investment_scope_store_invalid")
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
                connection.execute("INSERT INTO investment_scope_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("investment_scope_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM investment_scope_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("investment_scope_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("investment_scope_store_invalid")
    return connection


def _catalog(space, context) -> dict[str, dict]:
    """Die Konten der Stammdaten dieses Datenraums mit Bezeichnung, Art und Institut - gelesen, nicht veraendert."""
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("investment_scope_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("investment_scope_store_invalid")
            return {row[0]: {"label": row[1], "account_type": row[2], "institution": row[3]} for row in connection.execute(
                "SELECT account_id, display_name, account_type, institution_label FROM account")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("investment_scope_store_invalid")
        return {}


def _known_accounts(space, context) -> set[str]:
    return set(_catalog(space, context))


def _current(connection) -> dict[str, dict]:
    rows = connection.execute("SELECT account_id,in_investment,recorded_at_utc FROM current_investment_scope ORDER BY account_id").fetchall()
    return {row["account_id"]: dict(row) for row in rows}


def _normalized(entries) -> list[dict]:
    if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= BATCH_LIMIT:
        _abort("investment_scope_input_invalid")
    result = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"account_id", "in_investment"}:
            _abort("investment_scope_input_invalid")
        if not isinstance(entry["account_id"], str) or ACCOUNT_ID.fullmatch(entry["account_id"]) is None:
            _abort("investment_scope_input_invalid")
        if entry["in_investment"] is not None and not isinstance(entry["in_investment"], bool):
            _abort("investment_scope_input_invalid")
        result.append({"account_id": entry["account_id"], "in_investment": entry["in_investment"]})
    if len({entry["account_id"] for entry in result}) != len(result):
        _abort("investment_scope_input_invalid")
    return result


def record_investment_scope_v1(space, context_value, entries, recorded_at_utc, confirmed) -> dict:
    """Haengt je Konto den neuen Stand an. Unveraenderte Angaben schreiben nichts; ein Eintrag ohne Wert leert den Stand."""
    if confirmed is not True:
        _abort("investment_scope_confirmation_required")
    context = investment_scope_context_v1(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("investment_scope_input_invalid")
    wanted = _normalized(entries)
    known = _known_accounts(space, context)
    if any(entry["account_id"] not in known for entry in wanted):
        _abort("investment_scope_account_unknown")
    connection = _connect(space, context, True)
    written = unchanged = 0
    try:
        with connection:
            current = _current(connection)
            for entry in wanted:
                value = None if entry["in_investment"] is None else int(entry["in_investment"])
                before = current.get(entry["account_id"])
                if (before is None and value is None) or (before is not None and before["in_investment"] == value):
                    unchanged += 1
                    continue
                row = {"account_id": entry["account_id"], "in_investment": value, "recorded_at_utc": recorded_at_utc}
                connection.execute(
                    "INSERT INTO investment_scope_entry(account_id,in_investment,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                    (row["account_id"], row["in_investment"], row["recorded_at_utc"], _fingerprint(row)))
                written += 1
    except sqlite3.Error:
        _abort("investment_scope_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "written_count": written, "unchanged_count": unchanged,
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_investment_scope_v1(space, context_value) -> dict:
    """Gueltiger Stand je Konto (True: zur Anlage, False: ausserhalb). 'accounts' traegt nur festgelegte Konten; Angaben zu
    Konten, die es nicht mehr gibt, werden gezaehlt, nicht geliefert. 'cash_accounts' listet alle Cash-Konten der
    Stammdaten zur Wahl, mit ihrem Stand (None: noch nicht festgelegt)."""
    context = investment_scope_context_v1(context_value)
    connection = _connect(space, context, False)
    base = {"contract_version": CONTRACT, "status": "ready", "provider_access": False, "network_access": False, "canonical_write": False}
    current = {}
    if connection is not None:
        try:
            current = _current(connection)
        except sqlite3.Error:
            _abort("investment_scope_store_invalid")
        finally:
            connection.close()
    catalog = _catalog(space, context)
    filled = {account: row for account, row in current.items() if row["in_investment"] is not None}
    live = {account: {"in_investment": bool(row["in_investment"]), "recorded_at_utc": row["recorded_at_utc"]}
            for account, row in filled.items() if account in catalog}
    choices = [{"account_id": account, "label": meta["label"], "institution": meta["institution"], "account_type": meta["account_type"],
                "in_investment": live[account]["in_investment"] if account in live else None,
                "recorded_at_utc": live[account]["recorded_at_utc"] if account in live else None}
               for account, meta in sorted(catalog.items(), key=lambda item: ((item[1]["institution"] or "").lower(), item[1]["label"].lower()))
               if meta["account_type"] in CASH_ACCOUNT_TYPES]
    return {**base, "set_count": len(live), "orphan_count": len(filled) - len(live), "accounts": live, "cash_accounts": choices}


__all__ = [
    "AREA", "FAILURE_CODES", "STORE", "InvestmentScopeV1Error", "investment_scope_context_v1", "investment_scope_v1_error_codes",
    "read_investment_scope_v1", "record_investment_scope_v1",
]
