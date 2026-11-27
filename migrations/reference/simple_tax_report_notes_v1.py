"""Feste Hinweise zum einfachen Steuerreport: Saetze, die auf jedem Report stehen sollen.

Ein Report braucht Angaben, die nicht aus den Buchungen folgen - etwa dass frueher
nach einer anderen Methode erklaert wurde. Solche Saetze
wurden bisher je Report getippt und konnten fehlen. Sie liegen deshalb im
Datenraum, nur anhaengend; gueltig ist der juengste Stand. Der Report selbst
liest sie nur: Die Tax-Oberflaeche belegt ihr Anmerkungsfeld damit vor.
Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sqlite3

from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, activity_reference_scope_v1

AREA = "simple-tax-report-v1"
STORE = "report-notes.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "simple_tax_report_notes_v1"
NOTE_LIMIT = 2000
NOTE_COUNT_LIMIT = 20
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
FAILURE_CODES = (
    "simple_tax_report_notes_confirmation_required",
    "simple_tax_report_notes_input_invalid",
    "simple_tax_report_notes_store_invalid",
)
SCHEMA = (
    "CREATE TABLE report_notes_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE report_notes_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, notes_json TEXT NOT NULL CHECK(length(notes_json) BETWEEN 2 AND 60000),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TRIGGER report_notes_entry_no_update BEFORE UPDATE ON report_notes_entry "
    "BEGIN SELECT RAISE(ABORT, 'report_notes_entry_immutable'); END",
    "CREATE TRIGGER report_notes_entry_no_delete BEFORE DELETE ON report_notes_entry "
    "BEGIN SELECT RAISE(ABORT, 'report_notes_entry_immutable'); END",
    "CREATE VIEW current_report_notes AS SELECT entry.* FROM report_notes_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM report_notes_entry later)",
)


class SimpleTaxReportNotesV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def simple_tax_report_notes_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise SimpleTaxReportNotesV1Error(code if code in FAILURE_CODES else "simple_tax_report_notes_store_invalid")


def _scope(value):
    try:
        return activity_reference_scope_v1(value)
    except AssetActivityReferenceV1Error:
        _abort("simple_tax_report_notes_input_invalid")


def _notes(value) -> list[str]:
    """Ein Hinweis ist eine Zeile Text; Leerraum am Rand faellt weg, leere Zeilen gibt es nicht."""
    if not isinstance(value, (list, tuple)) or len(value) > NOTE_COUNT_LIMIT:
        _abort("simple_tax_report_notes_input_invalid")
    result = []
    for note in value:
        if not isinstance(note, str):
            _abort("simple_tax_report_notes_input_invalid")
        text = note.strip()
        if not text or len(text) > NOTE_LIMIT or any(ord(char) < 32 or ord(char) == 127 for char in text):
            _abort("simple_tax_report_notes_input_invalid")
        result.append(text)
    return result


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if not Path(space).is_dir() or root.is_symlink() or store.is_symlink():
        _abort("simple_tax_report_notes_store_invalid")
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
                connection.execute("INSERT INTO report_notes_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("simple_tax_report_notes_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM report_notes_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("simple_tax_report_notes_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("simple_tax_report_notes_store_invalid")
    return connection


def _current(connection) -> tuple[list[str], str | None]:
    row = connection.execute("SELECT notes_json,recorded_at_utc FROM current_report_notes").fetchone()
    if row is None:
        return [], None
    try:
        notes = json.loads(row[0])
    except (TypeError, ValueError):
        _abort("simple_tax_report_notes_store_invalid")
    if not isinstance(notes, list) or len(notes) > NOTE_COUNT_LIMIT or any(
            not isinstance(note, str) or not note or len(note) > NOTE_LIMIT for note in notes):
        _abort("simple_tax_report_notes_store_invalid")
    return notes, row[1]


def read_simple_tax_report_notes_v1(space, context_value) -> dict:
    """Die gueltigen Hinweise in ihrer Reihenfolge. Ohne Speicher gibt es keine - und es wird keiner angelegt."""
    context = _scope(context_value)
    connection = _connect(space, context, False)
    notes: list[str] = []
    recorded = None
    if connection is not None:
        try:
            notes, recorded = _current(connection)
        except sqlite3.Error:
            _abort("simple_tax_report_notes_store_invalid")
        finally:
            connection.close()
    return {"contract_version": CONTRACT, "status": "ready", "notes": notes, "recorded_at_utc": recorded,
            "provider_access": False, "network_access": False, "canonical_write": False}


def save_simple_tax_report_notes_v1(space, context_value, notes, recorded_at_utc, confirmed) -> dict:
    """Haengt den neuen Stand an. Unveraenderte Hinweise schreiben nichts; eine leere Liste nimmt alle zurueck."""
    if confirmed is not True:
        _abort("simple_tax_report_notes_confirmation_required")
    context = _scope(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("simple_tax_report_notes_input_invalid")
    wanted = _notes(notes)
    existing = _connect(space, context, False)
    if existing is None and not wanted:
        return {"contract_version": CONTRACT, "status": "recorded", "written_count": 0, "note_count": 0,
                "provider_access": False, "network_access": False, "canonical_write": False}
    if existing is not None:
        existing.close()
    connection = _connect(space, context, True)
    written = 0
    try:
        with connection:
            if _current(connection)[0] != wanted:
                text = json.dumps(wanted, ensure_ascii=False, separators=(",", ":"))
                fingerprint = hashlib.sha256(json.dumps(
                    {"notes": wanted, "recorded_at_utc": recorded_at_utc}, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False).encode("utf-8")).hexdigest()
                connection.execute("INSERT INTO report_notes_entry(notes_json,recorded_at_utc,entry_fingerprint) VALUES(?,?,?)",
                                   (text, recorded_at_utc, fingerprint))
                written = 1
    except sqlite3.Error:
        _abort("simple_tax_report_notes_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "written_count": written, "note_count": len(wanted),
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "STORE", "SimpleTaxReportNotesV1Error", "read_simple_tax_report_notes_v1",
    "save_simple_tax_report_notes_v1", "simple_tax_report_notes_v1_error_codes",
]
