"""Belegangaben zu einer Buchung: Transaktions-ID, Adresse der Gegenseite, Notiz.

Die Angaben sind Nachweis, keine Wirtschaftstatsache. Sie liegen deshalb neben
dem Buchungsbestand und nicht in ihm: Eine nachgetragene Kennung aendert weder
Bestand noch FIFO noch Bewertung und darf deren Abdruecke nicht bewegen. Der
Speicher haengt nur an; der gueltige Stand je Buchung ist der juengste Eintrag.
Eine Korrektur legt die Buchung unter neuem Schluessel an - ihre Angaben werden
ausdruecklich auf den Nachfolger uebertragen. Kein Providerzugriff, kein
Netzzugriff, kein kanonischer Write.

Daneben, in eigener Datei desselben Bereichs, steht der Wert eines Abgangs in
EUR, wie ihn der Nutzer angibt. Ein Abgang traegt im
Buchungsbestand keinen Erloes; der Wert sagt, wieviel abgegangen ist. Er haengt
an derselben Buchung, aendert Bestand und FIFO ebenso wenig und zieht bei einer
Korrektur mit. Die eigene Datei laesst den Speicher der Belegangaben
unveraendert: Ein frueherer Programmstand liest ihn weiter.

Seit #459 (04.11.2026) in einer dritten Datei: der steuerpflichtige Betrag eines Verkaufs oder einer Dividende laut Beleg der
Bank (nach Teilfreistellung, vor Freistellungsauftrag und Verlustverrechnung), etwa aus der Ertraegnisaufstellung. Das
Regelmodul nimmt ihn statt der eigenen Rechnung; die Steuer rechnet es weiter selbst. Auch er zieht bei einer Korrektur mit.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sqlite3

from migrations.reference.desktop_product_asset_activity_v1 import (
    CORRECTION_RECEIPT_NAME, GENERATION, LEDGER_NAME, MANIFEST_NAME, PRODUCT_AREA,
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error, _context, _correction_receipt_for_generation,
    read_desktop_product_asset_activity_binding_v1,
)

AREA = "asset-activity-reference-v1"
STORE = "asset-activity-reference.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "asset_activity_reference_v1"
ORIGINS = ("owner_entered", "legacy_comment", "statement_source", "carried_from_correction")
FIELDS = ("transaction_id", "counterparty_address", "note")
EVENT_REF = re.compile(r"evt_[a-z0-9_]{4,60}")
# Kennung und Adresse sind ein zusammenhaengendes Zeichen-Token; Freitext gehoert in die Notiz.
TOKEN = re.compile(r"[!-~]{1,200}")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
NOTE_LIMIT = 4000
BATCH_LIMIT = 5000
VALUE_STORE = "activity-disposal-value.sqlite"
VALUE_SCHEMA_VERSION = 1
VALUE_ORIGINS = ("owner_entered", "carried_from_correction")
# Ein Betrag in EUR ohne Vorzeichen; null ist eine Aussage (abgegangen ohne Gegenwert).
VALUE = re.compile(r"(0|[1-9][0-9]{0,11})(\.[0-9]{1,8})?")
VALUE_EVENT_TYPE = "withdrawal"
TAXABLE_STORE = "activity-taxable-document.sqlite"
TAXABLE_SCHEMA_VERSION = 1
TAXABLE_ORIGINS = ("document_import", "carried_from_correction")
# Ein Betrag in EUR mit Vorzeichen: ein Verlust ist negativ.
TAXABLE = re.compile(r"-?(0|[1-9][0-9]{0,11})(\.[0-9]{1,8})?")
TAXABLE_EVENT_TYPES = ("sell", "dividend")
SHA256 = re.compile(r"[a-f0-9]{64}")
FAILURE_CODES = (
    "activity_reference_confirmation_required",
    "activity_reference_event_unknown",
    "activity_reference_input_invalid",
    "activity_reference_store_invalid",
    "activity_reference_value_not_applicable",
)
SCHEMA = (
    "CREATE TABLE activity_reference_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE activity_reference_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, event_ref TEXT NOT NULL,"
    "transaction_id TEXT CHECK(transaction_id IS NULL OR length(transaction_id) BETWEEN 1 AND 200),"
    "counterparty_address TEXT CHECK(counterparty_address IS NULL OR length(counterparty_address) BETWEEN 1 AND 200),"
    "note TEXT CHECK(note IS NULL OR length(note) BETWEEN 1 AND 4000),"
    "origin TEXT NOT NULL CHECK(origin IN ('owner_entered','legacy_comment','statement_source','carried_from_correction')),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX activity_reference_entry_event ON activity_reference_entry(event_ref, entry_id)",
    "CREATE TRIGGER activity_reference_entry_no_update BEFORE UPDATE ON activity_reference_entry "
    "BEGIN SELECT RAISE(ABORT, 'activity_reference_entry_immutable'); END",
    "CREATE TRIGGER activity_reference_entry_no_delete BEFORE DELETE ON activity_reference_entry "
    "BEGIN SELECT RAISE(ABORT, 'activity_reference_entry_immutable'); END",
    "CREATE VIEW current_activity_reference AS SELECT entry.* FROM activity_reference_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM activity_reference_entry later WHERE later.event_ref = entry.event_ref)",
)


VALUE_SCHEMA = (
    "CREATE TABLE disposal_value_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE disposal_value_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, event_ref TEXT NOT NULL,"
    "value_eur_decimal TEXT CHECK(value_eur_decimal IS NULL OR length(value_eur_decimal) BETWEEN 1 AND 21),"
    "origin TEXT NOT NULL CHECK(origin IN ('owner_entered','carried_from_correction')),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX disposal_value_entry_event ON disposal_value_entry(event_ref, entry_id)",
    "CREATE TRIGGER disposal_value_entry_no_update BEFORE UPDATE ON disposal_value_entry "
    "BEGIN SELECT RAISE(ABORT, 'disposal_value_entry_immutable'); END",
    "CREATE TRIGGER disposal_value_entry_no_delete BEFORE DELETE ON disposal_value_entry "
    "BEGIN SELECT RAISE(ABORT, 'disposal_value_entry_immutable'); END",
    "CREATE VIEW current_disposal_value AS SELECT entry.* FROM disposal_value_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM disposal_value_entry later WHERE later.event_ref = entry.event_ref)",
)
TAXABLE_SCHEMA = (
    "CREATE TABLE taxable_document_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE taxable_document_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, event_ref TEXT NOT NULL,"
    "taxable_eur_decimal TEXT NOT NULL CHECK(length(taxable_eur_decimal) BETWEEN 1 AND 22),"
    "document_label TEXT NOT NULL CHECK(length(document_label) BETWEEN 1 AND 200),"
    "document_sha256 TEXT NOT NULL CHECK(length(document_sha256) = 64),"
    "origin TEXT NOT NULL CHECK(origin IN ('document_import','carried_from_correction')),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX taxable_document_entry_event ON taxable_document_entry(event_ref, entry_id)",
    "CREATE TRIGGER taxable_document_entry_no_update BEFORE UPDATE ON taxable_document_entry "
    "BEGIN SELECT RAISE(ABORT, 'taxable_document_entry_immutable'); END",
    "CREATE TRIGGER taxable_document_entry_no_delete BEFORE DELETE ON taxable_document_entry "
    "BEGIN SELECT RAISE(ABORT, 'taxable_document_entry_immutable'); END",
    "CREATE VIEW current_taxable_document AS SELECT entry.* FROM taxable_document_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM taxable_document_entry later WHERE later.event_ref = entry.event_ref)",
)
# Herkunft je Buchung (rc.378, #486): welcher Leser (Plugin, Version, Pruefsumme des Codes) eine Buchung aus einem Beleg erzeugt hat.
# Schluessel je Art: asset_event = Buchung (event_ref), cash_command = Cash-Befehl (source_candidate_fingerprint), taxable_document =
# Betrag laut Beleg an einer Buchung (event_ref), advance_lump_sum = Vorabpauschale (sha256 aus Asset, Konto, Jahr), stock_split =
# Split (split_ref). Eine Buchung kann mehrere Leser haben (Transfer aus zwei Exporten).
# Zwei Schritte, damit ein Rollout zwischen Lesen und Buchen nicht den neueren Leser eintraegt und auch ein fortgesetzter Import seine
# Herkunft bekommt: beim Vorbereiten die Absicht (reader_provenance_intent, die Buchung gibt es noch nicht), nach jedem Buchen der
# Abgleich (reconcile_reader_provenance_v1): Was gebucht ist und noch keine Herkunft traegt, bekommt die seiner Absicht.
PROVENANCE_STORE = "activity-reader-provenance.sqlite"
PROVENANCE_SCHEMA_VERSION = 1
PROVENANCE_KINDS = ("asset_event", "cash_command", "taxable_document", "advance_lump_sum", "stock_split")
PROVENANCE_EVENT_KINDS = ("asset_event", "taxable_document")
PROVENANCE_ORIGINS = ("statement_import", "carried_from_correction")
PROVENANCE_READER_KEYS = ("plugin_id", "reader_id", "domain", "plugin_version", "code_sha256")
PROVENANCE_PLUGIN = re.compile(r"[a-z][a-z0-9_]{1,40}")
PROVENANCE_READER = re.compile(r"[a-z][a-z0-9_]{2,60}_v[0-9]+")
PROVENANCE_DOMAIN = re.compile(r"[a-z][a-z_]{1,30}")
PROVENANCE_VERSION = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+-]{0,39}")
PROVENANCE_KEY = re.compile(r"(evt_[a-z0-9_]{4,60}|[a-f0-9]{64}|spl_[a-f0-9]{32})")
PROVENANCE_KEY_OF_KIND = {"asset_event": EVENT_REF, "taxable_document": EVENT_REF, "cash_command": SHA256, "advance_lump_sum": SHA256,
                          "stock_split": re.compile(r"spl_[a-f0-9]{32}")}
PROVENANCE_SCHEMA = (
    "CREATE TABLE reader_provenance_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE reader_provenance_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "booking_kind TEXT NOT NULL CHECK(booking_kind IN ('asset_event','cash_command','taxable_document','advance_lump_sum','stock_split')),"
    "booking_key TEXT NOT NULL CHECK(length(booking_key) BETWEEN 8 AND 80),"
    "readers_json TEXT NOT NULL CHECK(length(readers_json) BETWEEN 2 AND 4000),"
    "origin TEXT NOT NULL CHECK(origin IN ('statement_import','carried_from_correction')),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TABLE reader_provenance_intent("
    "intent_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "booking_kind TEXT NOT NULL CHECK(booking_kind IN ('asset_event')),"
    "booking_key TEXT NOT NULL CHECK(length(booking_key) BETWEEN 8 AND 80),"
    "readers_json TEXT NOT NULL CHECK(length(readers_json) BETWEEN 2 AND 4000),"
    "recorded_at_utc TEXT NOT NULL, intent_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX reader_provenance_intent_key ON reader_provenance_intent(booking_kind, booking_key, intent_id)",
    "CREATE TRIGGER reader_provenance_intent_no_update BEFORE UPDATE ON reader_provenance_intent "
    "BEGIN SELECT RAISE(ABORT, 'reader_provenance_intent_immutable'); END",
    "CREATE TRIGGER reader_provenance_intent_no_delete BEFORE DELETE ON reader_provenance_intent "
    "BEGIN SELECT RAISE(ABORT, 'reader_provenance_intent_immutable'); END",
    "CREATE VIEW current_reader_provenance_intent AS SELECT intent.* FROM reader_provenance_intent intent "
    "WHERE intent.intent_id = (SELECT max(later.intent_id) FROM reader_provenance_intent later "
    "WHERE later.booking_kind = intent.booking_kind AND later.booking_key = intent.booking_key)",
    "CREATE INDEX reader_provenance_entry_key ON reader_provenance_entry(booking_kind, booking_key, entry_id)",
    "CREATE TRIGGER reader_provenance_entry_no_update BEFORE UPDATE ON reader_provenance_entry "
    "BEGIN SELECT RAISE(ABORT, 'reader_provenance_entry_immutable'); END",
    "CREATE TRIGGER reader_provenance_entry_no_delete BEFORE DELETE ON reader_provenance_entry "
    "BEGIN SELECT RAISE(ABORT, 'reader_provenance_entry_immutable'); END",
    "CREATE VIEW current_reader_provenance AS SELECT entry.* FROM reader_provenance_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM reader_provenance_entry later "
    "WHERE later.booking_kind = entry.booking_kind AND later.booking_key = entry.booking_key)",
)
PROVENANCE_LAYOUT = (PROVENANCE_STORE, PROVENANCE_SCHEMA_VERSION, PROVENANCE_SCHEMA, "reader_provenance_binding")
# Pruefstand je Portfolio (rc.380, #486; Festlegungen vom 09.11.2026): Ein Leser gilt in einem Portfolio als "an Ihren
# Belegen geprueft", sobald der Eigentuemer eine Buchung mit genau diesem Plugin-Code ausdruecklich bestaetigt hat. Version = Pruefsumme
# ueber die eigenen Dateien des Plugins (Einstieg, Module); eine geaenderte Hilfsbibliothek (SDK, Host) ist nur ein Hinweis. In Datenraeumen
# aus der Zeit vor rc.380 gelten die mitgelieferten Leser ueber einen einmaligen Eintrag "Bestand bis rc.379" als geprueft. Nur anhaengend.
CHECK_STORE = "activity-reader-checks.sqlite"
CHECK_SCHEMA_VERSION = 1
CHECK_ORIGINS = ("confirmed_import", "existing_data_space")
CHECK_READER_KEYS = ("plugin_id", "reader_id", "domain", "plugin_version", "plugin_code_sha256", "shared_code_sha256")
CHECK_PORTFOLIO = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
CHECK_ACTOR = re.compile(r"[A-Za-z0-9_.:-]{1,80}")
CHECK_SCHEMA = (
    "CREATE TABLE reader_check_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE reader_check_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "portfolio_id TEXT NOT NULL CHECK(length(portfolio_id) BETWEEN 1 AND 80),"
    "plugin_id TEXT NOT NULL CHECK(length(plugin_id) BETWEEN 2 AND 41),"
    "reader_id TEXT NOT NULL CHECK(length(reader_id) BETWEEN 3 AND 64),"
    "domain TEXT NOT NULL CHECK(length(domain) BETWEEN 2 AND 31),"
    "plugin_version TEXT NOT NULL CHECK(length(plugin_version) BETWEEN 1 AND 40),"
    "plugin_code_sha256 TEXT NOT NULL CHECK(length(plugin_code_sha256) = 64),"
    "shared_code_sha256 TEXT NOT NULL CHECK(length(shared_code_sha256) IN (0, 64)),"
    "origin TEXT NOT NULL CHECK(origin IN ('confirmed_import','existing_data_space')),"
    "document_count INTEGER CHECK(document_count IS NULL OR document_count >= 0),"
    "booking_count INTEGER CHECK(booking_count IS NULL OR booking_count >= 0),"
    "actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX reader_check_entry_key ON reader_check_entry(portfolio_id, plugin_id, reader_id, domain, entry_id)",
    "CREATE TRIGGER reader_check_entry_no_update BEFORE UPDATE ON reader_check_entry "
    "BEGIN SELECT RAISE(ABORT, 'reader_check_entry_immutable'); END",
    "CREATE TRIGGER reader_check_entry_no_delete BEFORE DELETE ON reader_check_entry "
    "BEGIN SELECT RAISE(ABORT, 'reader_check_entry_immutable'); END",
)
CHECK_LAYOUT = (CHECK_STORE, CHECK_SCHEMA_VERSION, CHECK_SCHEMA, "reader_check_binding")
REFERENCE_LAYOUT = (STORE, SCHEMA_VERSION, SCHEMA, "activity_reference_binding")
VALUE_LAYOUT = (VALUE_STORE, VALUE_SCHEMA_VERSION, VALUE_SCHEMA, "disposal_value_binding")
TAXABLE_LAYOUT = (TAXABLE_STORE, TAXABLE_SCHEMA_VERSION, TAXABLE_SCHEMA, "taxable_document_binding")


class AssetActivityReferenceV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def asset_activity_reference_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise AssetActivityReferenceV1Error(code if code in FAILURE_CODES else "activity_reference_store_invalid")


def _scope(value):
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("activity_reference_input_invalid")


def activity_reference_scope_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("activity_reference_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("activity_reference_input_invalid")
    return _scope(value)


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _token(value):
    if value is None:
        return None
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        _abort("activity_reference_input_invalid")
    return value


def _note(value):
    if value is None:
        return None
    if not isinstance(value, str):
        _abort("activity_reference_input_invalid")
    text = value.strip()
    if not text or len(text) > NOTE_LIMIT or any(ord(char) < 32 or ord(char) == 127 for char in text):
        _abort("activity_reference_input_invalid")
    return text


def _connect(space, context, create: bool, layout=REFERENCE_LAYOUT):
    name, schema_version, schema, binding_table = layout
    root = Path(space) / AREA
    store = root / name
    if root.is_symlink() or store.is_symlink():
        _abort("activity_reference_store_invalid")
    expected = (schema_version, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in schema:
                    connection.execute(statement)
                connection.execute(f"INSERT INTO {binding_table} VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {schema_version}")
        except sqlite3.Error:
            connection.close()
            _abort("activity_reference_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            f"SELECT schema_version,tenant_id,user_id,data_space_id FROM {binding_table} WHERE singleton_id=1"
        ).fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("activity_reference_store_invalid")
    if version != schema_version or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("activity_reference_store_invalid")
    return connection


def _current(connection, event_refs=None) -> dict[str, dict]:
    rows = connection.execute(
        "SELECT event_ref,transaction_id,counterparty_address,note,origin,recorded_at_utc FROM current_activity_reference ORDER BY event_ref"
    ).fetchall()
    wanted = None if event_refs is None else set(event_refs)
    return {row["event_ref"]: dict(row) for row in rows if wanted is None or row["event_ref"] in wanted}


def _ledger_event_types(space, context) -> dict[str, str]:
    try:
        binding = read_desktop_product_asset_activity_binding_v1(space, context)
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        try:
            return {row[0]: row[1] for row in connection.execute("SELECT event_ref,event_type FROM current_asset_activity_event")}
        finally:
            connection.close()
    except (DesktopProductAssetActivityV1Error, sqlite3.Error, KeyError, TypeError):
        _abort("activity_reference_store_invalid")
        return {}


def _ledger_event_refs(space, context) -> set[str]:
    return set(_ledger_event_types(space, context))


def _normalized(entries) -> list[dict]:
    if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= BATCH_LIMIT:
        _abort("activity_reference_input_invalid")
    result = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"event_ref", *FIELDS}:
            _abort("activity_reference_input_invalid")
        if not isinstance(entry["event_ref"], str) or EVENT_REF.fullmatch(entry["event_ref"]) is None:
            _abort("activity_reference_input_invalid")
        result.append({
            "event_ref": entry["event_ref"], "transaction_id": _token(entry["transaction_id"]),
            "counterparty_address": _token(entry["counterparty_address"]), "note": _note(entry["note"]),
        })
    if len({entry["event_ref"] for entry in result}) != len(result):
        _abort("activity_reference_input_invalid")
    return result


def record_activity_references_v1(space, context_value, entries, origin, recorded_at_utc, confirmed) -> dict:
    """Haengt je Buchung den neuen Stand an. Unveraenderte Angaben schreiben nichts; ein Eintrag ohne Werte leert den Stand."""
    if confirmed is not True:
        _abort("activity_reference_confirmation_required")
    context = activity_reference_scope_v1(context_value)
    if origin not in ORIGINS or not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("activity_reference_input_invalid")
    wanted = _normalized(entries)
    known = _ledger_event_refs(space, context)
    if any(entry["event_ref"] not in known for entry in wanted):
        _abort("activity_reference_event_unknown")
    connection = _connect(space, context, True)
    written = unchanged = 0
    try:
        with connection:
            current = _current(connection, [entry["event_ref"] for entry in wanted])
            for entry in wanted:
                before = current.get(entry["event_ref"])
                values = tuple(entry[field] for field in FIELDS)
                if (before is None and values == (None, None, None)) or (
                        before is not None and tuple(before[field] for field in FIELDS) == values):
                    unchanged += 1
                    continue
                row = {**entry, "origin": origin, "recorded_at_utc": recorded_at_utc}
                connection.execute(
                    "INSERT INTO activity_reference_entry(event_ref,transaction_id,counterparty_address,note,origin,recorded_at_utc,entry_fingerprint)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (*(row[name] for name in ("event_ref", *FIELDS, "origin", "recorded_at_utc")), _fingerprint(row)))
                written += 1
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "written_count": written, "unchanged_count": unchanged,
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_activity_references_v1(space, context_value, event_refs=None) -> dict:
    """Gueltiger Stand je Buchung. Angaben zu Buchungen, die es nicht mehr gibt, werden gezaehlt, nicht geliefert."""
    context = activity_reference_scope_v1(context_value)
    if event_refs is not None and (
            not isinstance(event_refs, (list, tuple))
            or any(not isinstance(ref, str) or EVENT_REF.fullmatch(ref) is None for ref in event_refs)):
        _abort("activity_reference_input_invalid")
    connection = _connect(space, context, False)
    if connection is None:
        return {"contract_version": CONTRACT, "status": "ready", "reference_count": 0, "orphan_count": 0, "references": {},
                "provider_access": False, "network_access": False, "canonical_write": False}
    try:
        current = _current(connection, event_refs)
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    known = _ledger_event_refs(space, context)
    filled = {ref: row for ref, row in current.items() if any(row[field] is not None for field in FIELDS)}
    live = {ref: {key: row[key] for key in (*FIELDS, "origin", "recorded_at_utc")} for ref, row in filled.items() if ref in known}
    return {"contract_version": CONTRACT, "status": "ready", "reference_count": len(live), "orphan_count": len(filled) - len(live),
            "references": live, "provider_access": False, "network_access": False, "canonical_write": False}


def _current_values(connection, event_refs=None) -> dict[str, dict]:
    rows = connection.execute(
        "SELECT event_ref,value_eur_decimal,origin,recorded_at_utc FROM current_disposal_value ORDER BY event_ref").fetchall()
    wanted = None if event_refs is None else set(event_refs)
    return {row["event_ref"]: dict(row) for row in rows if wanted is None or row["event_ref"] in wanted}


def _write_disposal_value(space, context, event_ref, value, origin, recorded_at_utc) -> int:
    connection = _connect(space, context, True, VALUE_LAYOUT)
    try:
        with connection:
            before = _current_values(connection, [event_ref]).get(event_ref)
            if (before["value_eur_decimal"] if before is not None else None) == value:
                return 0
            row = {"event_ref": event_ref, "value_eur_decimal": value, "origin": origin, "recorded_at_utc": recorded_at_utc}
            connection.execute(
                "INSERT INTO disposal_value_entry(event_ref,value_eur_decimal,origin,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?)",
                (event_ref, value, origin, recorded_at_utc, _fingerprint(row)))
            return 1
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
        return 0
    finally:
        connection.close()


def record_activity_disposal_value_v1(space, context_value, event_ref, value_eur_decimal, recorded_at_utc, confirmed) -> dict:
    """Haengt den Wert eines Abgangs in EUR an. Ohne Wert (None) wird der Stand geleert; nur ein Abgang traegt einen Wert."""
    if confirmed is not True:
        _abort("activity_reference_confirmation_required")
    context = activity_reference_scope_v1(context_value)
    if (not isinstance(event_ref, str) or EVENT_REF.fullmatch(event_ref) is None
            or not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None
            or not (value_eur_decimal is None or (isinstance(value_eur_decimal, str) and VALUE.fullmatch(value_eur_decimal) is not None))):
        _abort("activity_reference_input_invalid")
    event_type = _ledger_event_types(space, context).get(event_ref)
    if event_type is None:
        _abort("activity_reference_event_unknown")
    if event_type != VALUE_EVENT_TYPE:
        _abort("activity_reference_value_not_applicable")
    written = _write_disposal_value(space, context, event_ref, value_eur_decimal, "owner_entered", recorded_at_utc)
    return {"contract_version": CONTRACT, "status": "recorded", "written_count": written, "unchanged_count": 1 - written,
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_activity_disposal_values_v1(space, context_value) -> dict:
    """Gueltiger Wert je Abgang. Werte zu Buchungen, die es nicht mehr gibt oder die kein Abgang sind, werden gezaehlt, nicht geliefert."""
    context = activity_reference_scope_v1(context_value)
    connection = _connect(space, context, False, VALUE_LAYOUT)
    if connection is None:
        return {"contract_version": CONTRACT, "status": "ready", "value_count": 0, "orphan_count": 0, "values": {},
                "provider_access": False, "network_access": False, "canonical_write": False}
    try:
        current = _current_values(connection)
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    types = _ledger_event_types(space, context)
    filled = {ref: row for ref, row in current.items() if row["value_eur_decimal"] is not None}
    live = {ref: {key: row[key] for key in ("value_eur_decimal", "origin", "recorded_at_utc")}
            for ref, row in filled.items() if types.get(ref) == VALUE_EVENT_TYPE}
    return {"contract_version": CONTRACT, "status": "ready", "value_count": len(live), "orphan_count": len(filled) - len(live),
            "values": live, "provider_access": False, "network_access": False, "canonical_write": False}


def _carry_disposal_value(space, context, predecessor_event_ref, successor_event_ref, recorded_at_utc) -> int:
    connection = _connect(space, context, False, VALUE_LAYOUT)
    if connection is None:
        return 0
    try:
        current = _current_values(connection, [predecessor_event_ref, successor_event_ref])
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    source = current.get(predecessor_event_ref)
    target = current.get(successor_event_ref)
    if source is None or source["value_eur_decimal"] is None or (target is not None and target["value_eur_decimal"] is not None):
        return 0
    # Wird aus dem Abgang durch die Korrektur eine andere Buchungsart, gehoert der Wert nicht mehr dazu.
    if _ledger_event_types(space, context).get(successor_event_ref) != VALUE_EVENT_TYPE:
        return 0
    return _write_disposal_value(space, context, successor_event_ref, source["value_eur_decimal"], "carried_from_correction", recorded_at_utc)


def _current_taxable(connection, event_refs=None) -> dict[str, dict]:
    rows = connection.execute(
        "SELECT event_ref,taxable_eur_decimal,document_label,document_sha256,origin,recorded_at_utc FROM current_taxable_document ORDER BY event_ref").fetchall()
    return {row["event_ref"]: dict(row) for row in rows if event_refs is None or row["event_ref"] in event_refs}


def record_activity_taxable_documents_v1(space, context_value, entries, recorded_at_utc, confirmed) -> dict:
    """Haengt steuerpflichtige Betraege laut Beleg an (#459): je Eintrag Buchung, Betrag in EUR, Beleg und dessen Pruefwert.

    Nur Verkaeufe und Dividenden; der Betrag ist der Kapitalertrag laut Beleg nach Teilfreistellung, vor Freistellungsauftrag
    und Verlustverrechnung. Ein gleicher Betrag aus demselben Beleg schreibt nichts.
    """
    context = activity_reference_scope_v1(context_value)
    if confirmed is not True:
        _abort("activity_reference_confirmation_required")
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("activity_reference_input_invalid")
    if not isinstance(entries, list) or not entries or len(entries) > BATCH_LIMIT:
        _abort("activity_reference_input_invalid")
    types = _ledger_event_types(space, context)
    checked = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"event_ref", "taxable_eur_decimal", "document_label", "document_sha256"}:
            _abort("activity_reference_input_invalid")
        ref, value, label, digest = entry["event_ref"], entry["taxable_eur_decimal"], entry["document_label"], entry["document_sha256"]
        if not isinstance(ref, str) or EVENT_REF.fullmatch(ref) is None or not isinstance(value, str) or TAXABLE.fullmatch(value) is None \
                or not isinstance(label, str) or not 1 <= len(label.strip()) <= 200 or not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
            _abort("activity_reference_input_invalid")
        if ref not in types:
            _abort("activity_reference_event_unknown")
        if types[ref] not in TAXABLE_EVENT_TYPES:
            _abort("activity_reference_value_not_applicable")
        checked.append((ref, "0" if value in ("-0",) else value, label.strip(), digest))
    if len({ref for ref, *_ in checked}) != len(checked):
        _abort("activity_reference_input_invalid")
    connection = _connect(space, context, True, TAXABLE_LAYOUT)
    written = 0
    try:
        current = _current_taxable(connection)
        with connection:
            for ref, value, label, digest in checked:
                previous = current.get(ref)
                if previous is not None and previous["taxable_eur_decimal"] == value and previous["document_sha256"] == digest:
                    continue
                body = {"event_ref": ref, "taxable_eur_decimal": value, "document_label": label, "document_sha256": digest,
                        "origin": "document_import", "recorded_at_utc": recorded_at_utc}
                connection.execute(
                    "INSERT INTO taxable_document_entry(event_ref,taxable_eur_decimal,document_label,document_sha256,origin,recorded_at_utc,entry_fingerprint)"
                    " VALUES(?,?,?,?,?,?,?)", (ref, value, label, digest, "document_import", recorded_at_utc, _fingerprint(body)))
                written += 1
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "written_count": written, "canonical_write": False}


def read_activity_taxable_documents_v1(space, context_value, event_refs=None) -> dict:
    """Je Buchung der juengste steuerpflichtige Betrag laut Beleg; ohne Speicher keiner."""
    context = activity_reference_scope_v1(context_value)
    connection = _connect(space, context, False, TAXABLE_LAYOUT)
    if connection is None:
        return {"contract_version": CONTRACT, "values": {}, "canonical_write": False}
    try:
        values = _current_taxable(connection, None if event_refs is None else set(event_refs))
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "values": values, "canonical_write": False}


def _carry_taxable_document(space, context, predecessor_event_ref, successor_event_ref, recorded_at_utc) -> int:
    # Ohne Speicher gibt es nichts mitzuziehen; mit ihm wird schreibend geoeffnet.
    if not (Path(space) / AREA / TAXABLE_STORE).exists():
        return 0
    connection = _connect(space, context, True, TAXABLE_LAYOUT)
    try:
        current = _current_taxable(connection, {predecessor_event_ref, successor_event_ref})
        source = current.get(predecessor_event_ref)
        if source is None or successor_event_ref in current:
            return 0
        body = {"event_ref": successor_event_ref, "taxable_eur_decimal": source["taxable_eur_decimal"], "document_label": source["document_label"],
                "document_sha256": source["document_sha256"], "origin": "carried_from_correction", "recorded_at_utc": recorded_at_utc}
        with connection:
            connection.execute(
                "INSERT INTO taxable_document_entry(event_ref,taxable_eur_decimal,document_label,document_sha256,origin,recorded_at_utc,entry_fingerprint)"
                " VALUES(?,?,?,?,?,?,?)", (successor_event_ref, source["taxable_eur_decimal"], source["document_label"], source["document_sha256"],
                                          "carried_from_correction", recorded_at_utc, _fingerprint(body)))
        return 1
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()


def _reader_entry_valid(reader) -> bool:
    return (isinstance(reader, dict) and set(reader) == set(PROVENANCE_READER_KEYS)
            and all(isinstance(reader[key], str) for key in PROVENANCE_READER_KEYS)
            and PROVENANCE_PLUGIN.fullmatch(reader["plugin_id"]) is not None and PROVENANCE_READER.fullmatch(reader["reader_id"]) is not None
            and PROVENANCE_DOMAIN.fullmatch(reader["domain"]) is not None and PROVENANCE_VERSION.fullmatch(reader["plugin_version"]) is not None
            and SHA256.fullmatch(reader["code_sha256"]) is not None)


def _readers_json(readers) -> str:
    """Leser einer Buchung, sortiert und ohne Doppel; jede Angabe streng geprueft."""
    if not isinstance(readers, list) or not 1 <= len(readers) <= 8 or not all(_reader_entry_valid(reader) for reader in readers):
        _abort("activity_reference_input_invalid")
    unique = sorted({json.dumps(reader, sort_keys=True, separators=(",", ":")) for reader in readers})
    return "[" + ",".join(unique) + "]"


def _current_provenance(connection, kind=None, keys=None) -> dict[tuple[str, str], dict]:
    rows = connection.execute(
        "SELECT booking_kind,booking_key,readers_json,origin,recorded_at_utc FROM current_reader_provenance ORDER BY booking_kind,booking_key").fetchall()
    found = {}
    for row in rows:
        if (kind is None or row["booking_kind"] == kind) and (keys is None or row["booking_key"] in keys):
            found[(row["booking_kind"], row["booking_key"])] = {"readers": json.loads(row["readers_json"]), "origin": row["origin"],
                                                                "recorded_at_utc": row["recorded_at_utc"], "readers_json": row["readers_json"]}
    return found


def _write_provenance(connection, rows, origin, recorded_at_utc) -> int:
    current = _current_provenance(connection)
    written = 0
    with connection:
        for kind, key, readers_json in rows:
            previous = current.get((kind, key))
            if previous is not None and previous["readers_json"] == readers_json:
                continue
            body = {"booking_kind": kind, "booking_key": key, "readers_json": readers_json, "origin": origin, "recorded_at_utc": recorded_at_utc}
            connection.execute(
                "INSERT INTO reader_provenance_entry(booking_kind,booking_key,readers_json,origin,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?)",
                (kind, key, readers_json, origin, recorded_at_utc, _fingerprint(body)))
            written += 1
    return written


def record_reader_provenance_v1(space, context_value, entries, recorded_at_utc) -> dict:
    """Haelt fest, welcher Leser eine Buchung erzeugt hat (rc.378, #486): je Eintrag Art, Schluessel und Leser
    ({plugin_id, reader_id, domain, plugin_version, code_sha256}). Laeuft nach dem Buchen; gleiche Angaben schreiben nichts.
    Eine Buchung (asset_event, taxable_document) muss im Buchungsbestand stehen."""
    context = activity_reference_scope_v1(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("activity_reference_input_invalid")
    if not isinstance(entries, list) or len(entries) > BATCH_LIMIT:
        _abort("activity_reference_input_invalid")
    if not entries:
        return {"contract_version": CONTRACT, "status": "nothing_to_record", "written_count": 0, "canonical_write": False}
    rows = _provenance_rows(entries, PROVENANCE_KINDS)
    events = {key for kind, key, _readers in rows if kind in PROVENANCE_EVENT_KINDS}
    if events and not events <= _ledger_event_refs(space, context):
        _abort("activity_reference_event_unknown")
    connection = _connect(space, context, True, PROVENANCE_LAYOUT)
    try:
        written = _write_provenance(connection, rows, "statement_import", recorded_at_utc)
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded" if written else "nothing_to_record", "written_count": written, "canonical_write": False}


def _provenance_rows(entries, kinds) -> list[tuple[str, str, str]]:
    rows = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"booking_kind", "booking_key", "readers"} or entry["booking_kind"] not in kinds \
                or not isinstance(entry["booking_key"], str) or PROVENANCE_KEY_OF_KIND[entry["booking_kind"]].fullmatch(entry["booking_key"]) is None:
            _abort("activity_reference_input_invalid")
        rows.append((entry["booking_kind"], entry["booking_key"], _readers_json(entry["readers"])))
    if len({(kind, key) for kind, key, _readers in rows}) != len(rows):
        _abort("activity_reference_input_invalid")
    return rows


def advance_lump_sum_provenance_key_v1(asset_id: str, account_id: str, calculation_year: int) -> str:
    """Schluessel einer Vorabpauschale in der Herkunft: sha256 aus Asset, Konto und Jahr (wie der Speicher sie fuehrt)."""
    return hashlib.sha256(json.dumps([asset_id, account_id, int(calculation_year)], separators=(",", ":")).encode("utf-8")).hexdigest()


def record_reader_provenance_intents_v1(space, context_value, entries, recorded_at_utc) -> dict:
    """Beim Vorbereiten einer Buchung (CSV-Plan, Reward-Entwurf): die Leser, die gerade gelesen haben, als Absicht - die Buchung gibt
    es noch nicht. reconcile_reader_provenance_v1 uebernimmt sie nach dem Buchen. Gleiche Absicht schreibt nichts."""
    context = activity_reference_scope_v1(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None or not isinstance(entries, list) or len(entries) > BATCH_LIMIT:
        _abort("activity_reference_input_invalid")
    if not entries:
        return {"contract_version": CONTRACT, "status": "nothing_to_record", "written_count": 0, "canonical_write": False}
    rows = _provenance_rows(entries, ("asset_event",))
    connection = _connect(space, context, True, PROVENANCE_LAYOUT)
    written = 0
    try:
        current = {(row["booking_kind"], row["booking_key"]): row["readers_json"]
                   for row in connection.execute("SELECT booking_kind,booking_key,readers_json FROM current_reader_provenance_intent")}
        with connection:
            for kind, key, readers_json in rows:
                if current.get((kind, key)) == readers_json:
                    continue
                body = {"booking_kind": kind, "booking_key": key, "readers_json": readers_json, "recorded_at_utc": recorded_at_utc}
                connection.execute("INSERT INTO reader_provenance_intent(booking_kind,booking_key,readers_json,recorded_at_utc,intent_fingerprint) VALUES(?,?,?,?,?)",
                                   (kind, key, readers_json, recorded_at_utc, _fingerprint(body)))
                written += 1
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded" if written else "nothing_to_record", "written_count": written, "canonical_write": False}


def reconcile_reader_provenance_v1(space, context_value, recorded_at_utc, event_refs=None) -> dict:
    """Nach jedem Buchen (auch einem fortgesetzten Import): Gebuchte Vorgaenge mit einer Absicht, aber ohne Herkunft, bekommen die Leser
    ihrer Absicht. Eine schon festgehaltene Herkunft bleibt. Ohne Speicher gibt es nichts abzugleichen."""
    context = activity_reference_scope_v1(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("activity_reference_input_invalid")
    if not (Path(space) / AREA / PROVENANCE_STORE).exists():
        return {"contract_version": CONTRACT, "status": "nothing_to_record", "written_count": 0, "pending_count": 0, "canonical_write": False}
    wanted = None if event_refs is None else set(event_refs)
    connection = _connect(space, context, True, PROVENANCE_LAYOUT)
    try:
        intents = [(row["booking_kind"], row["booking_key"], row["readers_json"]) for row in connection.execute(
            "SELECT booking_kind,booking_key,readers_json FROM current_reader_provenance_intent ORDER BY booking_key")
            if wanted is None or row["booking_key"] in wanted]
        done = _current_provenance(connection, "asset_event")
        open_intents = [(kind, key, readers) for kind, key, readers in intents if (kind, key) not in done]
        # Ohne Buchungsbestand ist noch nichts gebucht: alle Absichten bleiben offen.
        absent = read_desktop_product_asset_activity_binding_v1(space, context).get("status") == "absent"
        booked = _ledger_event_refs(space, context) if open_intents and not absent else set()
        rows = [(kind, key, readers) for kind, key, readers in open_intents if key in booked]
        written = _write_provenance(connection, rows, "statement_import", recorded_at_utc) if rows else 0
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded" if written else "nothing_to_record", "written_count": written,
            "pending_count": len(open_intents) - len(rows), "canonical_write": False}


def read_reader_provenance_v1(space, context_value, booking_kind=None, booking_keys=None) -> dict:
    """Je Buchung die Leser, die sie erzeugt haben (juengster Stand); ohne Speicher keine. Schluessel "<Art>:<Schluessel>"."""
    context = activity_reference_scope_v1(context_value)
    if booking_kind is not None and booking_kind not in PROVENANCE_KINDS:
        _abort("activity_reference_input_invalid")
    connection = _connect(space, context, False, PROVENANCE_LAYOUT)
    if connection is None:
        return {"contract_version": CONTRACT, "provenance": {}, "canonical_write": False}
    try:
        found = _current_provenance(connection, booking_kind, None if booking_keys is None else set(booking_keys))
    except (sqlite3.Error, ValueError):
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "canonical_write": False,
            "provenance": {f"{kind}:{key}": {key_name: value[key_name] for key_name in ("readers", "origin", "recorded_at_utc")} for (kind, key), value in found.items()}}


def _carry_provenance(space, context, predecessor_event_ref, successor_event_ref, recorded_at_utc) -> int:
    """Die Herkunft einer korrigierten Buchung zieht mit (Art asset_event und taxable_document), als "carried_from_correction"."""
    if not (Path(space) / AREA / PROVENANCE_STORE).exists():
        return 0
    connection = _connect(space, context, True, PROVENANCE_LAYOUT)
    try:
        current = _current_provenance(connection, None, {predecessor_event_ref, successor_event_ref})
        rows = [(kind, successor_event_ref, current[(kind, predecessor_event_ref)]["readers_json"]) for kind in ("asset_event", "taxable_document")
                if (kind, predecessor_event_ref) in current and (kind, successor_event_ref) not in current]
        return _write_provenance(connection, rows, "carried_from_correction", recorded_at_utc) if rows else 0
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()


def _check_reader_valid(reader) -> bool:
    return (isinstance(reader, dict) and set(reader) == set(CHECK_READER_KEYS) and all(isinstance(reader[key], str) for key in CHECK_READER_KEYS)
            and PROVENANCE_PLUGIN.fullmatch(reader["plugin_id"]) is not None and PROVENANCE_READER.fullmatch(reader["reader_id"]) is not None
            and PROVENANCE_DOMAIN.fullmatch(reader["domain"]) is not None and PROVENANCE_VERSION.fullmatch(reader["plugin_version"]) is not None
            and SHA256.fullmatch(reader["plugin_code_sha256"]) is not None
            and (reader["shared_code_sha256"] == "" or SHA256.fullmatch(reader["shared_code_sha256"]) is not None))


def _check_inputs(portfolio_id, readers) -> list[dict]:
    if not isinstance(portfolio_id, str) or CHECK_PORTFOLIO.fullmatch(portfolio_id) is None or not isinstance(readers, list) \
            or not 1 <= len(readers) <= 200 or not all(_check_reader_valid(reader) for reader in readers):
        _abort("activity_reference_input_invalid")
    unique = {(reader["plugin_id"], reader["reader_id"], reader["domain"]): reader for reader in readers}
    return list(unique.values())


def _check_entries(connection, portfolio_id) -> list[dict]:
    return [dict(row) for row in connection.execute(
        "SELECT entry_id,plugin_id,reader_id,domain,plugin_version,plugin_code_sha256,shared_code_sha256,origin,document_count,booking_count,"
        "actor_id,recorded_at_utc FROM reader_check_entry WHERE portfolio_id=? ORDER BY entry_id", (portfolio_id,))]


def read_reader_checks_v1(space, context_value, portfolio_id, readers) -> dict:
    """Pruefstand je Leser im Portfolio (rc.380): "checked", wenn ein Eintrag genau diesen Plugin-Code traegt. Dazu der Eintrag, ob sich die
    Hilfsbibliothek seither geaendert hat (nur Hinweis), und die zuletzt gepruefte andere Version (fuer "neue Version seit ...")."""
    context = activity_reference_scope_v1(context_value)
    wanted = _check_inputs(portfolio_id, readers)
    connection = _connect(space, context, False, CHECK_LAYOUT)
    entries: list[dict] = []
    if connection is not None:
        try:
            entries = _check_entries(connection, portfolio_id)
        except sqlite3.Error:
            _abort("activity_reference_store_invalid")
        finally:
            connection.close()
    result = []
    for reader in wanted:
        same = [entry for entry in entries if (entry["plugin_id"], entry["reader_id"], entry["domain"]) == (reader["plugin_id"], reader["reader_id"], reader["domain"])]
        match = next((entry for entry in reversed(same) if entry["plugin_code_sha256"] == reader["plugin_code_sha256"]), None)
        previous = next((entry for entry in reversed(same) if entry["plugin_code_sha256"] != reader["plugin_code_sha256"]), None)
        result.append({**reader, "status": "checked" if match else "unchecked",
                       "checked": None if match is None else {key: match[key] for key in ("origin", "recorded_at_utc", "plugin_version", "document_count", "booking_count")},
                       "shared_changed": bool(match and reader["shared_code_sha256"] and match["shared_code_sha256"] != reader["shared_code_sha256"]),
                       "previous": None if previous is None or match is not None else {key: previous[key] for key in ("plugin_version", "recorded_at_utc", "origin")}})
    return {"contract_version": CONTRACT, "portfolio_id": portfolio_id, "store_present": connection is not None, "entry_count": len(entries),
            "readers": result, "canonical_write": False}


def record_reader_checks_v1(space, context_value, portfolio_id, readers, origin, recorded_at_utc, document_count=None, booking_count=None) -> dict:
    """Haelt fest, dass der Eigentuemer diese Leser (genau dieser Plugin-Code) im Portfolio an seinen Belegen bestaetigt hat. Schon
    gepruefter Code schreibt nichts. "existing_data_space" nur einmal, solange noch kein Eintrag besteht (Bestand bis rc.379)."""
    context = activity_reference_scope_v1(context_value)
    wanted = _check_inputs(portfolio_id, readers)
    if origin not in CHECK_ORIGINS or not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None \
            or CHECK_ACTOR.fullmatch(str(context.actor_id)) is None \
            or any(value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0) for value in (document_count, booking_count)):
        _abort("activity_reference_input_invalid")
    connection = _connect(space, context, True, CHECK_LAYOUT)
    written = 0
    try:
        entries = _check_entries(connection, portfolio_id)
        if origin == "existing_data_space" and entries:
            return {"contract_version": CONTRACT, "status": "nothing_to_record", "written_count": 0, "canonical_write": False}
        done = {(entry["plugin_id"], entry["reader_id"], entry["domain"], entry["plugin_code_sha256"]) for entry in entries}
        with connection:
            for reader in wanted:
                if (reader["plugin_id"], reader["reader_id"], reader["domain"], reader["plugin_code_sha256"]) in done:
                    continue
                body = {"portfolio_id": portfolio_id, **reader, "origin": origin, "document_count": document_count, "booking_count": booking_count,
                        "actor_id": context.actor_id, "recorded_at_utc": recorded_at_utc}
                connection.execute(
                    "INSERT INTO reader_check_entry(portfolio_id,plugin_id,reader_id,domain,plugin_version,plugin_code_sha256,shared_code_sha256,origin,"
                    "document_count,booking_count,actor_id,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (portfolio_id, reader["plugin_id"], reader["reader_id"], reader["domain"], reader["plugin_version"], reader["plugin_code_sha256"],
                     reader["shared_code_sha256"], origin, document_count, booking_count, context.actor_id, recorded_at_utc, _fingerprint(body)))
                written += 1
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded" if written else "nothing_to_record", "written_count": written, "canonical_write": False}


def reader_check_store_present_v1(space) -> bool:
    return (Path(space) / AREA / CHECK_STORE).exists()


def ensure_reader_check_store_v1(space, context_value) -> bool:
    """Legt den Speicher leer an (erster Kontakt eines Datenraums mit rc.380); True, wenn er neu ist."""
    context = activity_reference_scope_v1(context_value)
    if reader_check_store_present_v1(space):
        return False
    connection = _connect(space, context, True, CHECK_LAYOUT)
    connection.close()
    return True


def list_reader_checks_v1(space, context_value) -> dict:
    """Alle Pruefstand-Eintraege des Datenraums (fuer die Verwaltung der Leser); ohne Speicher keine."""
    context = activity_reference_scope_v1(context_value)
    connection = _connect(space, context, False, CHECK_LAYOUT)
    if connection is None:
        return {"contract_version": CONTRACT, "entries": [], "canonical_write": False}
    try:
        rows = [dict(row) for row in connection.execute(
            "SELECT entry_id,portfolio_id,plugin_id,reader_id,domain,plugin_version,plugin_code_sha256,shared_code_sha256,origin,document_count,"
            "booking_count,actor_id,recorded_at_utc FROM reader_check_entry ORDER BY entry_id")]
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "entries": rows, "canonical_write": False}


def _carry_reference(space, context, predecessor_event_ref, successor_event_ref, recorded_at_utc) -> int:
    connection = _connect(space, context, False)
    if connection is None:
        return 0
    try:
        current = _current(connection, [predecessor_event_ref, successor_event_ref])
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    source = current.get(predecessor_event_ref)
    target = current.get(successor_event_ref)
    if source is None or all(source[field] is None for field in FIELDS) or (
            target is not None and any(target[field] is not None for field in FIELDS)):
        return 0
    return record_activity_references_v1(
        space, context, [{"event_ref": successor_event_ref, **{field: source[field] for field in FIELDS}}],
        "carried_from_correction", recorded_at_utc, True)["written_count"]


def carry_activity_reference_v1(space, context_value, predecessor_event_ref, successor_event_ref, recorded_at_utc) -> dict:
    """Uebertraegt Belegangaben und Abgangswert einer korrigierten Buchung auf ihren Nachfolger, sofern dieser noch keine traegt."""
    context = activity_reference_scope_v1(context_value)
    for ref in (predecessor_event_ref, successor_event_ref):
        if not isinstance(ref, str) or EVENT_REF.fullmatch(ref) is None:
            _abort("activity_reference_input_invalid")
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("activity_reference_input_invalid")
    written = _carry_reference(space, context, predecessor_event_ref, successor_event_ref, recorded_at_utc)
    value_written = _carry_disposal_value(space, context, predecessor_event_ref, successor_event_ref, recorded_at_utc)
    # Der Betrag laut Beleg (#459) zieht ebenso mit; er zaehlt zu den Werten der Buchung.
    value_written += _carry_taxable_document(space, context, predecessor_event_ref, successor_event_ref, recorded_at_utc)
    # Die Herkunft (rc.378) zieht ebenso mit: Auch die korrigierte Buchung stammt urspruenglich aus diesem Leser.
    provenance_written = _carry_provenance(space, context, predecessor_event_ref, successor_event_ref, recorded_at_utc)
    return {"contract_version": CONTRACT, "status": "carried" if written + value_written + provenance_written else "nothing_to_carry",
            "written_count": written, "value_written_count": value_written, "provenance_written_count": provenance_written}


# Storno und Wiederimport (#439): Gleich ist eine neue Buchung einer stornierten, wenn diese Merkmale uebereinstimmen.
VOID_IDENTITY = ("portfolio_id", "account_id", "related_account_id", "asset_id", "event_type", "quantity_decimal", "local_date", "local_time")


def _without_accounts(identity: tuple) -> tuple:
    """Die Merkmale ohne Konto und Gegenkonto (Stellen in VOID_IDENTITY)."""
    return tuple(value for name, value in zip(VOID_IDENTITY, identity) if name not in ("account_id", "related_account_id"))


def _ledger_identities(space, context) -> dict[str, tuple]:
    try:
        binding = read_desktop_product_asset_activity_binding_v1(space, context)
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        try:
            return {row[0]: tuple(row[1:]) for row in connection.execute(
                "SELECT event_ref," + ",".join(VOID_IDENTITY) + " FROM current_asset_activity_event")}
        finally:
            connection.close()
    except (DesktopProductAssetActivityV1Error, sqlite3.Error, KeyError, TypeError):
        _abort("activity_reference_store_invalid")
        return {}


def _voided_identities(space, context, wanted: set[str]) -> dict[str, tuple]:
    """Merkmale stornierter Buchungen: Ihr Wortlaut steht im Vorgaenger der Storno-Quittung (predecessor_preserved).
    Gelesen werden nur Quittungen und die Vorgaenger-Generationen, die eine der gesuchten Buchungen nennen."""
    generations = Path(space) / PRODUCT_AREA / "generations"
    if not wanted or not generations.is_dir():
        return {}
    priors: dict[str, set[str]] = {}
    try:
        for child in sorted(generations.iterdir()):
            if GENERATION.fullmatch(child.name) is None or not (child / CORRECTION_RECEIPT_NAME).is_file():
                continue
            manifest = json.loads((child / MANIFEST_NAME).read_text(encoding="utf-8"))
            receipt = _correction_receipt_for_generation(child, context, manifest)
            if receipt is None or receipt["action_type"] != "void":
                continue
            for row in receipt.get("batch_predecessors", [{"event_ref": receipt["predecessor_event_ref"]}]):
                if row["event_ref"] in wanted:
                    priors.setdefault(receipt["prior_generation_ref"], set()).add(row["event_ref"])
        found: dict[str, tuple] = {}
        for prior, refs in sorted(priors.items()):
            connection = sqlite3.connect(f"file:{generations / prior / LEDGER_NAME}?mode=ro", uri=True)
            try:
                marks = ",".join("?" * len(refs))
                for row in connection.execute("SELECT event_ref," + ",".join(VOID_IDENTITY) + f" FROM asset_activity_event WHERE event_ref IN ({marks})", sorted(refs)):
                    found[row[0]] = tuple(row[1:])
            finally:
                connection.close()
        return found
    except (OSError, ValueError, sqlite3.Error, KeyError, TypeError, DesktopProductAssetActivityV1Error):
        _abort("activity_reference_store_invalid")
        return {}


def carry_activity_references_from_voided_v1(space, context_value, event_refs, recorded_at_utc) -> dict:
    """Storno und Wiederimport (#439): Eine neu gebuchte Buchung, die einer stornierten in Portfolio, Konto, Gegenkonto, Asset,
    Art, Menge, Tag und Uhrzeit gleicht, uebernimmt deren Belegangaben und den Wert des Abgangs. Nur wenn beide Seiten eindeutig
    sind und die neue Buchung noch nichts traegt; sonst bleibt alles, wie es ist. Herkunft "von der korrigierten Buchung"."""
    context = activity_reference_scope_v1(context_value)
    if (not isinstance(event_refs, (list, tuple)) or len(event_refs) > BATCH_LIMIT
            or any(not isinstance(ref, str) or EVENT_REF.fullmatch(ref) is None for ref in event_refs)
            or not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None):
        _abort("activity_reference_input_invalid")
    nothing = {"contract_version": CONTRACT, "status": "nothing_to_carry", "written_count": 0, "value_written_count": 0}
    connection = _connect(space, context, False)
    if connection is None or not event_refs:
        if connection is not None:
            connection.close()
        return nothing
    try:
        current = _current(connection)
    except sqlite3.Error:
        _abort("activity_reference_store_invalid")
    finally:
        connection.close()
    live = _ledger_identities(space, context)
    orphans = {ref: row for ref, row in current.items() if ref not in live and any(row[field] is not None for field in FIELDS)}
    if not orphans:
        return nothing
    voided = _voided_identities(space, context, set(orphans))
    olds: dict[tuple, list[str]] = {}
    loose_olds: dict[tuple, list[str]] = {}
    for ref, identity in voided.items():
        olds.setdefault(identity, []).append(ref)
        loose_olds.setdefault(_without_accounts(identity), []).append(ref)
    targets = [ref for ref in dict.fromkeys(event_refs) if ref in live]
    alike: dict[tuple, int] = {}
    loose_alike: dict[tuple, int] = {}
    for ref in targets:
        alike[live[ref]] = alike.get(live[ref], 0) + 1
        loose_alike[_without_accounts(live[ref])] = loose_alike.get(_without_accounts(live[ref]), 0) + 1
    entries, pairs = [], []
    for ref in targets:
        sources = olds.get(live[ref], [])
        unique = alike[live[ref]] == 1
        # Storno und Neueinlesen auf ein anderes Konto (#509: Rewards vom Haupt- aufs Staking-Konto): Gleicht keine stornierte
        # Buchung samt Konto, zaehlt eine, die bis auf Konto und Gegenkonto gleicht - nur wenn sie auf beiden Seiten die einzige ist.
        if not sources:
            loose = _without_accounts(live[ref])
            sources = loose_olds.get(loose, [])
            unique = loose_alike[loose] == 1
        values = {tuple(orphans[source][field] for field in FIELDS) for source in sources}
        # Mehrfach storniert und neu gebucht: dieselben Angaben an mehreren Vorgaengern zaehlen als eine.
        if not unique or len(values) != 1:
            continue
        pairs.append((sorted(sources)[-1], ref))
        # Nur leere Felder: Was die Quelle beim Wiederimport schon eingetragen hat, bleibt. So ist die Reihenfolge gleichgueltig.
        before = current.get(ref) or {}
        merged = {field: before.get(field) if before.get(field) is not None else value for field, value in zip(FIELDS, next(iter(values)))}
        if any(merged[field] != before.get(field) for field in FIELDS):
            entries.append({"event_ref": ref, **merged})
    written = record_activity_references_v1(space, context, entries, "carried_from_correction", recorded_at_utc, True)["written_count"] if entries else 0
    value_written = sum(_carry_disposal_value(space, context, source, target, recorded_at_utc) for source, target in pairs)
    value_written += sum(_carry_taxable_document(space, context, source, target, recorded_at_utc) for source, target in pairs)
    return {"contract_version": CONTRACT, "status": "carried" if written + value_written else "nothing_to_carry",
            "written_count": written, "value_written_count": value_written}


__all__ = [
    "AssetActivityReferenceV1Error", "FAILURE_CODES", "FIELDS", "ORIGINS", "VOID_IDENTITY", "activity_reference_scope_v1",
    "asset_activity_reference_v1_error_codes", "carry_activity_references_from_voided_v1",
    "carry_activity_reference_v1", "read_activity_disposal_values_v1", "read_activity_references_v1", "read_activity_taxable_documents_v1",
    "record_activity_disposal_value_v1", "record_activity_references_v1", "record_activity_taxable_documents_v1",
    "ensure_reader_check_store_v1", "list_reader_checks_v1", "read_reader_checks_v1", "reader_check_store_present_v1", "record_reader_checks_v1",
]
