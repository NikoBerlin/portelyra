"""Kontonummer zu einem Konto: IBAN, Depotnummer, Kundennummer oder - bei einem Wallet - die eigene Adresse.

Festlegung (13.10.2026): ein weiteres Attribut am Konto - nicht am
Institut -, in das die Kontonummer eingetragen wird und das spaeter durchsuchbar
ist. Die Angabe ist Nachweis, keine Wirtschaftstatsache. Sie liegt deshalb neben
den Stammdaten und nicht in ihnen: Jeder Schreibzugriff auf die Stammdatendatei
bewegt deren Abdruck, dem der Buchungsbestand folgt; eine nachgetragene
Kontonummer soll weder Buchungsbestand noch FIFO noch Bewertung beruehren.

Der Speicher haengt nur an; der gueltige Stand je Konto ist der juengste
Eintrag. Ein Eintrag ohne Wert leert den Stand. Kein Providerzugriff, kein
Netzzugriff, kein kanonischer Write.
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

AREA = "account-reference-v1"
STORE = "account-reference.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "account_reference_v1"
ACCOUNT_ID = re.compile(r"acc_[a-z0-9_]{4,60}")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
NUMBER_LIMIT = 120
BATCH_LIMIT = 500
FAILURE_CODES = (
    "account_reference_account_unknown",
    "account_reference_confirmation_required",
    "account_reference_input_invalid",
    "account_reference_store_invalid",
)
SCHEMA = (
    "CREATE TABLE account_reference_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE account_reference_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,"
    "account_number TEXT CHECK(account_number IS NULL OR length(account_number) BETWEEN 1 AND 120),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX account_reference_entry_account ON account_reference_entry(account_id, entry_id)",
    "CREATE TRIGGER account_reference_entry_no_update BEFORE UPDATE ON account_reference_entry "
    "BEGIN SELECT RAISE(ABORT, 'account_reference_entry_immutable'); END",
    "CREATE TRIGGER account_reference_entry_no_delete BEFORE DELETE ON account_reference_entry "
    "BEGIN SELECT RAISE(ABORT, 'account_reference_entry_immutable'); END",
    "CREATE VIEW current_account_reference AS SELECT entry.* FROM account_reference_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM account_reference_entry later WHERE later.account_id = entry.account_id)",
)


class AccountReferenceV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def account_reference_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise AccountReferenceV1Error(code if code in FAILURE_CODES else "account_reference_store_invalid")


def account_reference_scope_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("account_reference_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("account_reference_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("account_reference_input_invalid")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _number(value):
    """Die Kontonummer, wie sie auf dem Auszug steht: eine Zeile, Leerraum zusammengezogen. Ein leerer Wert heisst: keine Angabe."""
    if value is None:
        return None
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        _abort("account_reference_input_invalid")
    text = " ".join(value.split())
    if not text:
        return None
    if len(text) > NUMBER_LIMIT:
        _abort("account_reference_input_invalid")
    return text


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("account_reference_store_invalid")
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
                connection.execute("INSERT INTO account_reference_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("account_reference_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM account_reference_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("account_reference_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("account_reference_store_invalid")
    return connection


def _known_accounts(space, context) -> set[str]:
    """Die Konten der Stammdaten dieses Datenraums - gelesen, nicht veraendert."""
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("account_reference_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("account_reference_store_invalid")
            return {row[0] for row in connection.execute("SELECT account_id FROM account")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("account_reference_store_invalid")
        return set()


def _current(connection) -> dict[str, dict]:
    rows = connection.execute(
        "SELECT account_id,account_number,recorded_at_utc FROM current_account_reference ORDER BY account_id").fetchall()
    return {row["account_id"]: dict(row) for row in rows}


def _normalized(entries) -> list[dict]:
    if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= BATCH_LIMIT:
        _abort("account_reference_input_invalid")
    result = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"account_id", "account_number"}:
            _abort("account_reference_input_invalid")
        if not isinstance(entry["account_id"], str) or ACCOUNT_ID.fullmatch(entry["account_id"]) is None:
            _abort("account_reference_input_invalid")
        result.append({"account_id": entry["account_id"], "account_number": _number(entry["account_number"])})
    if len({entry["account_id"] for entry in result}) != len(result):
        _abort("account_reference_input_invalid")
    return result


def record_account_references_v1(space, context_value, entries, recorded_at_utc, confirmed) -> dict:
    """Haengt je Konto den neuen Stand an. Unveraenderte Angaben schreiben nichts; ein Eintrag ohne Wert leert den Stand."""
    if confirmed is not True:
        _abort("account_reference_confirmation_required")
    context = account_reference_scope_v1(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("account_reference_input_invalid")
    wanted = _normalized(entries)
    known = _known_accounts(space, context)
    if any(entry["account_id"] not in known for entry in wanted):
        _abort("account_reference_account_unknown")
    connection = _connect(space, context, True)
    written = unchanged = 0
    try:
        with connection:
            current = _current(connection)
            for entry in wanted:
                before = current.get(entry["account_id"])
                if (before is None and entry["account_number"] is None) or (
                        before is not None and before["account_number"] == entry["account_number"]):
                    unchanged += 1
                    continue
                row = {**entry, "recorded_at_utc": recorded_at_utc}
                connection.execute(
                    "INSERT INTO account_reference_entry(account_id,account_number,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                    (row["account_id"], row["account_number"], row["recorded_at_utc"], _fingerprint(row)))
                written += 1
    except sqlite3.Error:
        _abort("account_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "written_count": written, "unchanged_count": unchanged,
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_account_references_v1(space, context_value) -> dict:
    """Gueltiger Stand je Konto. Angaben zu Konten, die es nicht mehr gibt, werden gezaehlt, nicht geliefert."""
    context = account_reference_scope_v1(context_value)
    connection = _connect(space, context, False)
    if connection is None:
        return {"contract_version": CONTRACT, "status": "ready", "reference_count": 0, "orphan_count": 0, "references": {},
                "provider_access": False, "network_access": False, "canonical_write": False}
    try:
        current = _current(connection)
    except sqlite3.Error:
        _abort("account_reference_store_invalid")
    finally:
        connection.close()
    known = _known_accounts(space, context)
    filled = {account: row for account, row in current.items() if row["account_number"] is not None}
    live = {account: {"account_number": row["account_number"], "recorded_at_utc": row["recorded_at_utc"]}
            for account, row in filled.items() if account in known}
    return {"contract_version": CONTRACT, "status": "ready", "reference_count": len(live), "orphan_count": len(filled) - len(live),
            "references": live, "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "STORE", "AccountReferenceV1Error", "account_reference_scope_v1", "account_reference_v1_error_codes",
    "read_account_references_v1", "record_account_references_v1",
]
