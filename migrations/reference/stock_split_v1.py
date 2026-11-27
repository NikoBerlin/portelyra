"""Aktiensplits (#451, rc.370) - eine Kapitalmassnahme neben dem Buchungsbestand.

Ein Split ist ein eigenes Ereignis. Fachlich ist er keine
Veraeusserung: Die Anschaffungskosten verteilen sich auf die neuen Stuecke, der Anschaffungszeitpunkt bleibt. Ein
Reverse-Split (Zusammenlegung, etwa 1:10) folgt derselben Regel. Ein Spitzenausgleich in Geld ist ein Verkauf des Bruchteils
und wird als solcher gebucht.

Ein Eintrag nennt Asset, Stichtag (Ex-Tag), Verhaeltnis neu : alt und optional das Konto; ohne Konto gilt er fuer alle Konten.
Der FIFO-Kern teilt zu Beginn des Stichtags jedes offene Lot. Buchungen ab dem Stichtag stehen in neuen Stuecken, Buchungen
davor bleiben, wie im Beleg.

Warum neben dem Bestand und nicht als Buchungsart: Das Schema des Buchungsbestands kennt acht feste Arten (CHECK in jeder
Generation); eine neunte hiesse, jede Generation umzubauen. Der Speicher haengt nur an; je Kennung gilt der juengste Eintrag,
"removed" nimmt einen Split zurueck. Die Kennung folgt aus Asset, Konto und Stichtag - ein neuer Eintrag fuer denselben Tag
ersetzt das Verhaeltnis. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write. Ein Split aendert den FIFO-Stand; er
wird danach fortgeschrieben.
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

AREA = "stock-split-v1"
STORE = "stock-split.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "stock_split_v1"
ASSET_ID = re.compile(r"ast_[a-z0-9_]{4,60}")
ACCOUNT_ID = re.compile(r"acc_[a-z0-9_]{4,60}")
RATIO = re.compile(r"[1-9][0-9]{0,11}")
SPLIT_REF = re.compile(r"spl_[a-f0-9]{32}")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
NOTE_LIMIT = 200
FAILURE_CODES = (
    "stock_split_account_unknown",
    "stock_split_asset_unknown",
    "stock_split_confirmation_required",
    "stock_split_entry_unknown",
    "stock_split_input_invalid",
    "stock_split_store_invalid",
)
SCHEMA = (
    "CREATE TABLE stock_split_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE split_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, split_ref TEXT NOT NULL CHECK(length(split_ref) = 36),"
    " asset_id TEXT NOT NULL, account_id TEXT, effective_local_date TEXT NOT NULL CHECK(length(effective_local_date) = 10),"
    " ratio_numerator TEXT NOT NULL, ratio_denominator TEXT NOT NULL, note TEXT,"
    " status TEXT NOT NULL CHECK(status IN ('recorded','removed')), recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX split_entry_ref ON split_entry(split_ref, entry_id)",
    *(f"CREATE TRIGGER split_entry_no_{action} BEFORE {action.upper()} ON split_entry BEGIN SELECT RAISE(ABORT, 'split_entry_immutable'); END"
      for action in ("update", "delete")),
    "CREATE VIEW current_split_entry AS SELECT entry.* FROM split_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM split_entry later WHERE later.split_ref = entry.split_ref)",
)


class StockSplitV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def stock_split_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise StockSplitV1Error(code if code in FAILURE_CODES else "stock_split_store_invalid")


def stock_split_context_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("stock_split_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("stock_split_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("stock_split_input_invalid")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def split_ref_v1(asset_id: str, account_id: str | None, effective_local_date: str) -> str:
    """Die Kennung eines Splits: Asset, Konto (oder alle) und Stichtag. Ein neuer Eintrag fuer denselben Tag ersetzt den alten."""
    return "spl_" + _fingerprint({"asset_id": asset_id, "account_id": account_id, "effective_local_date": effective_local_date})[:32]


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("stock_split_store_invalid")
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
                connection.execute("INSERT INTO stock_split_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("stock_split_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM stock_split_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("stock_split_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("stock_split_store_invalid")
    return connection


def _catalog(space, context) -> tuple[dict[str, dict], dict[str, dict]]:
    """Assets und Konten der Stammdaten - gelesen, nicht veraendert."""
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("stock_split_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("stock_split_store_invalid")
            assets = {row[0]: {"label": row[1], "asset_type": row[2]} for row in connection.execute(
                "SELECT asset_id, display_name, asset_type FROM asset WHERE asset_type <> 'cash'")}
            accounts = {row[0]: {"label": row[1], "account_type": row[2]} for row in connection.execute(
                "SELECT account_id, display_name, account_type FROM account")}
            return assets, accounts
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("stock_split_store_invalid")
        return {}, {}


def _stamp(value) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("stock_split_input_invalid")
    return value


def _day(value) -> str:
    try:
        if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            _abort("stock_split_input_invalid")
    except ValueError:
        _abort("stock_split_input_invalid")
    return value


def _entry(space, context, asset_id, account_id, effective_local_date, ratio_numerator, ratio_denominator, note) -> dict:
    """Prueft einen Eintrag gegen die Stammdaten und gibt ihn in Kernform mit Kennung zurueck."""
    day = _day(effective_local_date)
    if (not isinstance(asset_id, str) or ASSET_ID.fullmatch(asset_id) is None
            or (account_id is not None and (not isinstance(account_id, str) or ACCOUNT_ID.fullmatch(account_id) is None))
            or not isinstance(ratio_numerator, str) or RATIO.fullmatch(ratio_numerator) is None
            or not isinstance(ratio_denominator, str) or RATIO.fullmatch(ratio_denominator) is None
            or ratio_numerator == ratio_denominator
            or (note is not None and (not isinstance(note, str) or len(note) > NOTE_LIMIT))):
        _abort("stock_split_input_invalid")
    assets, accounts = _catalog(space, context)
    if asset_id not in assets:
        _abort("stock_split_asset_unknown")
    if account_id is not None and account_id not in accounts:
        _abort("stock_split_account_unknown")
    return {"split_ref": split_ref_v1(asset_id, account_id, day), "asset_ref": asset_id, "account_ref": account_id,
            "effective_local_date": day, "ratio_numerator": ratio_numerator, "ratio_denominator": ratio_denominator,
            "note": note.strip() if isinstance(note, str) and note.strip() else None}


def _current(connection) -> list[dict]:
    rows = connection.execute("SELECT split_ref,asset_id,account_id,effective_local_date,ratio_numerator,ratio_denominator,note,status,"
                              "recorded_at_utc FROM current_split_entry ORDER BY effective_local_date,split_ref").fetchall()
    return [dict(row) for row in rows if row["status"] == "recorded"]


def _kernel(row: dict) -> dict:
    return {"split_ref": row["split_ref"], "asset_ref": row["asset_id"], "account_ref": row["account_id"],
            "effective_local_date": row["effective_local_date"], "ratio_numerator": row["ratio_numerator"],
            "ratio_denominator": row["ratio_denominator"]}


def splits_for_fifo_v1(space, context_value) -> list[dict]:
    """Die gueltigen Splits in der Form des FIFO-Kerns (`splits`), nach Stichtag und Kennung. Leer ohne Speicher."""
    context = stock_split_context_v1(context_value)
    connection = _connect(space, context, False)
    if connection is None:
        return []
    try:
        rows = _current(connection)
    except sqlite3.Error:
        _abort("stock_split_store_invalid")
    finally:
        connection.close()
    return [_kernel(row) for row in rows]


def candidate_splits_v1(space, context_value, asset_id, account_id, effective_local_date, ratio_numerator, ratio_denominator,
                        note=None, *, remove: bool = False) -> list[dict]:
    """Die Splits, wie sie nach dem Speichern gaelten - fuer die Vorschau; schreibt nichts. Prueft wie das Speichern."""
    context = stock_split_context_v1(context_value)
    if remove:
        entry = {"split_ref": split_ref_v1(asset_id, account_id, _day(effective_local_date))}
        if entry["split_ref"] not in {row["split_ref"] for row in splits_for_fifo_v1(space, context)}:
            _abort("stock_split_entry_unknown")
    else:
        entry = _entry(space, context, asset_id, account_id, effective_local_date, ratio_numerator, ratio_denominator, note)
    rows = [row for row in splits_for_fifo_v1(space, context) if row["split_ref"] != entry["split_ref"]]
    if not remove:
        rows.append({key: entry[key] for key in ("split_ref", "asset_ref", "account_ref", "effective_local_date", "ratio_numerator", "ratio_denominator")})
    return sorted(rows, key=lambda row: (row["effective_local_date"], row["split_ref"]))


def record_stock_split_v1(space, context_value, asset_id, account_id, effective_local_date, ratio_numerator, ratio_denominator,
                          note, recorded_at_utc, confirmed, *, remove: bool = False) -> dict:
    """Haengt einen Split an oder nimmt ihn zurueck (remove). Unveraendert schreibt nichts. Ob der FIFO-Kern ihn annimmt, prueft
    vorher die Vorschau (`preview_stock_splits_v2`); hier wird nur gegen die Stammdaten geprueft."""
    if confirmed is not True:
        _abort("stock_split_confirmation_required")
    context = stock_split_context_v1(context_value)
    stamp = _stamp(recorded_at_utc)
    if remove:
        day = _day(effective_local_date)
        entry = {"split_ref": split_ref_v1(asset_id, account_id, day), "asset_ref": asset_id, "account_ref": account_id,
                 "effective_local_date": day, "ratio_numerator": None, "ratio_denominator": None, "note": None}
    else:
        entry = _entry(space, context, asset_id, account_id, effective_local_date, ratio_numerator, ratio_denominator, note)
    connection = _connect(space, context, True)
    try:
        with connection:
            current = connection.execute("SELECT * FROM current_split_entry WHERE split_ref=?", (entry["split_ref"],)).fetchone()
            active = current is not None and current["status"] == "recorded"
            if remove:
                if not active:
                    _abort("stock_split_entry_unknown")
                values = (entry["split_ref"], current["asset_id"], current["account_id"], current["effective_local_date"],
                          current["ratio_numerator"], current["ratio_denominator"], current["note"], "removed")
            else:
                if active and (current["ratio_numerator"], current["ratio_denominator"], current["note"]) == (
                        entry["ratio_numerator"], entry["ratio_denominator"], entry["note"]):
                    return {"contract_version": CONTRACT, "status": "unchanged", "split_ref": entry["split_ref"], "provider_access": False,
                            "network_access": False, "canonical_write": False}
                values = (entry["split_ref"], entry["asset_ref"], entry["account_ref"], entry["effective_local_date"],
                          entry["ratio_numerator"], entry["ratio_denominator"], entry["note"], "recorded")
            body = dict(zip(("split_ref", "asset_id", "account_id", "effective_local_date", "ratio_numerator", "ratio_denominator", "note",
                             "status"), values), recorded_at_utc=stamp)
            connection.execute("INSERT INTO split_entry(split_ref,asset_id,account_id,effective_local_date,ratio_numerator,ratio_denominator,"
                               "note,status,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?)", (*values, stamp, _fingerprint(body)))
    except sqlite3.Error:
        _abort("stock_split_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "removed" if remove else "recorded", "split_ref": entry["split_ref"],
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_stock_splits_v1(space, context_value) -> dict:
    """Die gueltigen Splits mit Bezeichnungen und die Assets und Konten zur Auswahl."""
    context = stock_split_context_v1(context_value)
    connection = _connect(space, context, False)
    entries: list[dict] = []
    if connection is not None:
        try:
            entries = _current(connection)
        except sqlite3.Error:
            _abort("stock_split_store_invalid")
        finally:
            connection.close()
    assets, accounts = _catalog(space, context)
    rows = [{"split_ref": row["split_ref"], "asset_id": row["asset_id"], "asset_label": assets.get(row["asset_id"], {}).get("label"),
             "account_id": row["account_id"], "account_label": None if row["account_id"] is None else accounts.get(row["account_id"], {}).get("label"),
             "effective_local_date": row["effective_local_date"], "ratio_numerator": row["ratio_numerator"],
             "ratio_denominator": row["ratio_denominator"], "note": row["note"], "recorded_at_utc": row["recorded_at_utc"]} for row in entries]
    rows.sort(key=lambda row: ((row["asset_label"] or "").casefold(), row["effective_local_date"]))
    return {"contract_version": CONTRACT, "status": "ready", "entries": rows,
            "assets": [{"asset_id": asset, "label": meta["label"], "asset_type": meta["asset_type"]}
                       for asset, meta in sorted(assets.items(), key=lambda item: item[1]["label"].casefold())],
            "accounts": [{"account_id": account, "label": meta["label"], "account_type": meta["account_type"]}
                         for account, meta in sorted(accounts.items(), key=lambda item: item[1]["label"].casefold())],
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "CONTRACT", "FAILURE_CODES", "STORE", "StockSplitV1Error", "candidate_splits_v1", "read_stock_splits_v1", "record_stock_split_v1",
    "split_ref_v1", "splits_for_fifo_v1", "stock_split_context_v1", "stock_split_v1_error_codes",
]
