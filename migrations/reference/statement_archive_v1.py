"""Ablage fuer Original-Auszuege: Dateien einmal hinterlegt, Konten zugeordnet, je Monat ausgewiesen.

Festlegung (13.10.2026): Originale Kontoauszuege sollen im Programm
hinterlegt und wieder abgerufen werden koennen - bestaetigt anhand von Zeitraum,
Konto und Institut, oder als "nicht mehr vorhanden, manuell bestaetigt". Die
Vorgaben:

- beliebig viele Dateien je Konto, Zeitraum und Art;
- keine Kopien, nur um Zeitraeume sauber zu trennen: Eine Datei traegt ihren
  eigenen Zeitraum und wird einmal abgelegt;
- gearbeitet wird jahresweise, ausgewiesen wird monatsweise;
- nichts wird verlangt, was es nicht gibt: Die Art ist nur ein Merkmal der
  Datei; "offen" ist ein Monat nur, wenn das Konto dort Bewegungen hat und
  nichts ihn abdeckt; ein Konto laesst sich ganz ausnehmen;
- Institut als Oberklasse, Konten darunter: Ein Dokument traegt Haekchen an
  beliebigen Konten; war das ganze Institut gemeint, steht das dabei.

Die Ablage liegt neben den Stammdaten und dem Buchungsbestand und beruehrt
beide nicht. Die Eintraege haengen nur an; gueltig ist je Dokument der juengste
Stand. Die Datei selbst liegt unter ihrem Pruefwert - dieselbe Datei gibt es
nur einmal, und beim Abruf wird der Pruefwert nachgerechnet. Die Quelldatei
bleibt unveraendert, wo sie ist. Kein Providerzugriff, kein Netzzugriff, kein
kanonischer Write.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
from typing import Any

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference.desktop_cash_coverage_v1 import (
    STORE_AREA as CASH_AREA, STORE_NAME as CASH_STORE, DesktopCashCoverageV1Error, read_desktop_cash_coverage_exchange_projection_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error, _context, read_desktop_product_asset_activity_binding_v1,
)

AREA = "statement-archive-v1"
STORE = "statement-archive.sqlite"
FILES = "files"
SCHEMA_VERSION = 1
CONTRACT = "statement_archive_v1"
KINDS = ("account_statement", "securities_statement", "transaction_export", "tax_certificate", "income_statement", "advance_lump_sum",
         "confirmation", "other")
# Was einen Monat belegt (#536, Festlegung 04.11.2026): nur Auszuege, Exporte und Abrechnungen. Jahresdokumente (Jahressteuer-
# bescheinigung, Ertraegnisaufstellung, Vorabpauschale) und "Sonstiges" liegen in der Ablage und im ZIP, decken aber keinen Monat -
# bis rc.357 deckte etwa eine Jahressteuerbescheinigung alle zwoelf Monate ihrer Konten und verbarg so fehlende Auszuege.
MONTH_KINDS = ("account_statement", "securities_statement", "transaction_export", "confirmation")
YEAR_KINDS = ("tax_certificate", "income_statement", "advance_lump_sum")
FILE_STATUSES = ("unconfirmed", "confirmed")
STATUSES = (*FILE_STATUSES, "not_available", "withdrawn")
MONTH_STATUSES = ("confirmed", "unconfirmed", "not_available", "open", "no_movement", "not_expected", "closed", "inactive")
DAY = re.compile(r"(19|20)[0-9]{2}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])")
FOLDER_LIMIT = 1000
ACCOUNT_ID = re.compile(r"acc_[a-z0-9_]{4,60}")
DOCUMENT_REF = re.compile(r"sdoc_[a-f0-9]{32}")
MONTH = re.compile(r"(19|20)[0-9]{2}-(0[1-9]|1[0-2])")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
# Die Grenze je Datei im Backup (workers/reference/desktop_release_v1.MAX_FILE_BYTES): Groesser liesse sich der
# Datenraum nicht mehr sichern. Bis rc.275 waren es 64 MB, und die Datei wurde ganz in den Speicher gelesen.
MAX_FILE_BYTES = 1_000_000_000
CHUNK_BYTES = 1024 * 1024
NAME_LIMIT = 200
LABEL_LIMIT = 120
NOTE_LIMIT = 1000
ACCOUNT_LIMIT = 500
FAILURE_CODES = (
    "statement_archive_account_unknown",
    "statement_archive_confirmation_required",
    "statement_archive_document_unknown",
    "statement_archive_file_invalid",
    "statement_archive_file_removed",
    "statement_archive_file_too_large",
    "statement_archive_input_invalid",
    "statement_archive_store_invalid",
    "statement_intake_changed",
    "statement_intake_folder_invalid",
    "statement_intake_too_many_files",
)
_KIND_LIST = ",".join(f"'{kind}'" for kind in KINDS)
DOCUMENT_COLUMNS = ("entry_id", "document_ref", "file_sha256", "document_kind", "period_from", "period_to", "status", "institution_label",
                    "account_ids", "note", "recorded_at_utc", "entry_fingerprint")


def _document_table(name: str) -> str:
    return (
        f"CREATE TABLE {name}("
        "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, document_ref TEXT NOT NULL,"
        "file_sha256 TEXT REFERENCES statement_file(file_sha256),"
        f"document_kind TEXT NOT NULL CHECK(document_kind IN ({_KIND_LIST})),"
        "period_from TEXT NOT NULL CHECK(length(period_from) = 7), period_to TEXT NOT NULL CHECK(length(period_to) = 7 AND period_to >= period_from),"
        "status TEXT NOT NULL CHECK(status IN ('unconfirmed','confirmed','not_available','withdrawn')),"
        "institution_label TEXT CHECK(institution_label IS NULL OR length(institution_label) BETWEEN 1 AND 120),"
        "account_ids TEXT NOT NULL, note TEXT CHECK(note IS NULL OR length(note) BETWEEN 1 AND 1000),"
        "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL,"
        # Ein hinterlegtes Dokument traegt seine Datei, eine Erklaerung "nicht mehr vorhanden" traegt keine.
        "CHECK((status IN ('unconfirmed','confirmed') AND file_sha256 IS NOT NULL) OR (status = 'not_available' AND file_sha256 IS NULL) OR status = 'withdrawn')) STRICT")


DOCUMENT_INDEX = "CREATE INDEX statement_document_entry_ref ON statement_document_entry(document_ref, entry_id)"
DOCUMENT_TRIGGERS = tuple(f"CREATE TRIGGER statement_document_entry_no_{verb} BEFORE {verb.upper()} ON statement_document_entry "
                          "BEGIN SELECT RAISE(ABORT, 'statement_archive_immutable'); END" for verb in ("update", "delete"))
DOCUMENT_VIEW = ("CREATE VIEW current_statement_document AS SELECT entry.* FROM statement_document_entry entry "
                 "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM statement_document_entry later WHERE later.document_ref = entry.document_ref)")
SCHEMA = (
    "CREATE TABLE statement_archive_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE statement_file("
    "file_sha256 TEXT PRIMARY KEY CHECK(length(file_sha256) = 64 AND file_sha256 NOT GLOB '*[^a-f0-9]*'),"
    "original_name TEXT NOT NULL CHECK(length(original_name) BETWEEN 1 AND 200), size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),"
    "stored_at_utc TEXT NOT NULL) STRICT",
    _document_table("statement_document_entry"),
    DOCUMENT_INDEX,
    "CREATE TABLE statement_account_setting_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL, statements_expected INTEGER NOT NULL CHECK(statements_expected IN (0,1)),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX statement_account_setting_entry_account ON statement_account_setting_entry(account_id, entry_id)",
    *(f"CREATE TRIGGER {table}_no_{verb} BEFORE {verb.upper()} ON {table} BEGIN SELECT RAISE(ABORT, 'statement_archive_immutable'); END"
      for table in ("statement_file", "statement_account_setting_entry") for verb in ("update", "delete")),
    *DOCUMENT_TRIGGERS,
    DOCUMENT_VIEW,
    "CREATE VIEW current_statement_account_setting AS SELECT entry.* FROM statement_account_setting_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM statement_account_setting_entry later WHERE later.account_id = entry.account_id)",
)


# Seit rc.302 (#434): Eine Datei laesst sich endgueltig entfernen, wenn jedes Dokument, das sie traegt, zurueckgezogen ist. Der
# Eintrag haengt an (entfernt oder - beim erneuten Hinterlegen derselben Datei - wieder da); ein aelterer Speicher erhaelt die
# Tabelle beim ersten Schreiben.
FILE_EVENT_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS statement_file_event(entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "file_sha256 TEXT NOT NULL REFERENCES statement_file(file_sha256), event TEXT NOT NULL CHECK(event IN ('removed','restored')),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    *(f"CREATE TRIGGER IF NOT EXISTS statement_file_event_no_{verb} BEFORE {verb.upper()} ON statement_file_event "
      "BEGIN SELECT RAISE(ABORT, 'statement_archive_immutable'); END" for verb in ("update", "delete")),
    "CREATE VIEW IF NOT EXISTS current_statement_file_event AS SELECT entry.* FROM statement_file_event entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM statement_file_event later WHERE later.file_sha256 = entry.file_sha256)",
)


# Seit rc.317 (#513, Festlegung 25.10.2026): "Konto geschlossen seit ..." und der Belegordner des monatlichen Eingangs. Beides
# haengt an; ein aelterer Speicher erhaelt die Tabellen beim ersten Schreiben. Ein geschlossenes Konto erwartet ab dem Monat nach
# dem Tag keine Auszuege mehr; Buchungen und Belege davor bleiben, wie sie sind. Eine leere Angabe nimmt die Schliessung zurueck.
INTAKE_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS statement_account_closure_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,"
    "closed_on TEXT CHECK(closed_on IS NULL OR length(closed_on) = 10), recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TABLE IF NOT EXISTS statement_intake_setting_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "folder TEXT CHECK(folder IS NULL OR length(folder) BETWEEN 1 AND 1000), recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    *(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{verb} BEFORE {verb.upper()} ON {table} BEGIN SELECT RAISE(ABORT, 'statement_archive_immutable'); END"
      for table in ("statement_account_closure_entry", "statement_intake_setting_entry") for verb in ("update", "delete")),
    "CREATE VIEW IF NOT EXISTS current_statement_account_closure AS SELECT entry.* FROM statement_account_closure_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM statement_account_closure_entry later WHERE later.account_id = entry.account_id)",
)


# Seit rc.350 (#529 Punkt 1, Festlegung 31.10.2026): "Konto inaktiv seit ..." - ein Konto, das besteht, aber ruht. Anders als "geschlossen" voruebergehend: Ab dem Monat danach erwartet die Ablage keine Auszuege, Eingang und
# Importe bieten das Konto nicht an; Bestand und Buchungen bleiben. Eine leere Angabe aktiviert es wieder - dann sind die Monate
# seit dem Tag wieder offen, und die Ablage nennt, ab wann Auszuege nachzuladen sind. Haengt an wie die Schliessung.
INACTIVE_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS statement_account_inactive_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,"
    "inactive_since TEXT CHECK(inactive_since IS NULL OR length(inactive_since) = 10), recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    *(f"CREATE TRIGGER IF NOT EXISTS statement_account_inactive_entry_no_{verb} BEFORE {verb.upper()} ON statement_account_inactive_entry "
      "BEGIN SELECT RAISE(ABORT, 'statement_archive_immutable'); END" for verb in ("update", "delete")),
    "CREATE VIEW IF NOT EXISTS current_statement_account_inactive AS SELECT entry.* FROM statement_account_inactive_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM statement_account_inactive_entry later WHERE later.account_id = entry.account_id)",
)


class StatementArchiveV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def statement_archive_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise StatementArchiveV1Error(code if code in FAILURE_CODES else "statement_archive_store_invalid")


def statement_archive_scope_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("statement_archive_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("statement_archive_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("statement_archive_input_invalid")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _line(value, limit: int, *, nullable: bool = True):
    """Eine Zeile Text ohne Steuerzeichen; Leerraum zusammengezogen. Leer heisst: keine Angabe."""
    if value is None:
        if nullable:
            return None
        _abort("statement_archive_input_invalid")
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        _abort("statement_archive_input_invalid")
    text = " ".join(value.split())
    if not text:
        if nullable:
            return None
        _abort("statement_archive_input_invalid")
    if len(text) > limit:
        _abort("statement_archive_input_invalid")
    return text


def _month(value) -> str:
    if not isinstance(value, str) or MONTH.fullmatch(value) is None:
        _abort("statement_archive_input_invalid")
    return value


def _months(first: str, last: str) -> list[str]:
    year, month = int(first[:4]), int(first[5:])
    result = []
    while f"{year:04d}-{month:02d}" <= last:
        result.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return result


def _accounts(value) -> list[str]:
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= ACCOUNT_LIMIT:
        _abort("statement_archive_input_invalid")
    if any(not isinstance(item, str) or ACCOUNT_ID.fullmatch(item) is None for item in value) or len(set(value)) != len(value):
        _abort("statement_archive_input_invalid")
    return sorted(value)


def _utc(value) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("statement_archive_input_invalid")
    return value


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink() or (root / FILES).is_symlink():
        _abort("statement_archive_store_invalid")
    expected = (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create:
            return None
        (root / FILES).mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        settle_new_directory_v1(root / FILES)  # #568: neue Ordner der Ablage, auch ihre gocryptfs.diriv festschreiben
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO statement_archive_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("statement_archive_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM statement_archive_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("statement_archive_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("statement_archive_store_invalid")
    if create:
        try:
            with connection:
                for statement in (*FILE_EVENT_SCHEMA, *INTAKE_SCHEMA, *INACTIVE_SCHEMA):
                    connection.execute(statement)
            _widen_kinds(connection)
        except sqlite3.Error:
            connection.close()
            _abort("statement_archive_store_invalid")
    return connection


def _widen_kinds(connection) -> None:
    """Seit rc.358 (#536): Ein aelterer Speicher kennt nicht jede Art (die Vorabpauschale). SQLite aendert eine Pruefregel nur ueber
    eine neue Tabelle: Beim ersten Schreiben entsteht sie einmal mit genau denselben Eintraegen (Kennung, Reihenfolge, Pruefwerte),
    in einem Zug - bricht etwas ab, bleibt der alte Stand. Nichts wird umgedeutet; welche Art ein Dokument hat, aendert nur der
    Eigentuemer ("Art ändern")."""
    found = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='statement_document_entry'").fetchone()
    if found is None:
        raise sqlite3.DatabaseError("statement_document_entry missing")
    if all(f"'{kind}'" in found[0] for kind in KINDS):
        return
    columns = ",".join(DOCUMENT_COLUMNS)
    before = connection.execute("SELECT count(*),coalesce(max(entry_id),0) FROM statement_document_entry").fetchone()
    connection.execute("BEGIN IMMEDIATE")
    try:
        for statement in ("DROP VIEW current_statement_document", *(f"DROP TRIGGER statement_document_entry_no_{verb}" for verb in ("update", "delete")),
                          "DROP INDEX statement_document_entry_ref", _document_table("statement_document_entry_widened"),
                          f"INSERT INTO statement_document_entry_widened({columns}) SELECT {columns} FROM statement_document_entry ORDER BY entry_id",
                          "DROP TABLE statement_document_entry", "ALTER TABLE statement_document_entry_widened RENAME TO statement_document_entry",
                          DOCUMENT_INDEX, *DOCUMENT_TRIGGERS, DOCUMENT_VIEW):
            connection.execute(statement)
        after = connection.execute("SELECT count(*),coalesce(max(entry_id),0) FROM statement_document_entry").fetchone()
        sequence = connection.execute("SELECT seq FROM sqlite_sequence WHERE name='statement_document_entry'").fetchone()
        if tuple(after) != tuple(before) or (before[0] and (sequence is None or sequence[0] != before[1])):
            raise sqlite3.DatabaseError("statement_document_entry not carried over")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise


def _removed_files(connection) -> set[str]:
    """Die Pruefwerte der endgueltig entfernten Dateien; ein Speicher ohne die Tabelle hat keine."""
    if connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='statement_file_event'").fetchone()[0] != 1:
        return set()
    return {row[0] for row in connection.execute("SELECT file_sha256 FROM current_statement_file_event WHERE event='removed'")}


def _catalog_accounts(space, context) -> dict[str, dict[str, Any]]:
    """Die Konten der Stammdaten dieses Datenraums mit Bezeichnung, Art und Institutsangabe - gelesen, nicht veraendert."""
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("statement_archive_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("statement_archive_store_invalid")
            return {row["account_id"]: dict(row) for row in connection.execute(
                "SELECT account_id,display_name,account_type,institution_label,status FROM account")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
        return {}


def _document(row) -> dict[str, Any]:
    value = dict(row)
    value["account_ids"] = json.loads(value["account_ids"])
    return value


def _current_documents(connection) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        "SELECT d.document_ref,d.file_sha256,d.document_kind,d.period_from,d.period_to,d.status,d.institution_label,d.account_ids,d.note,"
        "d.recorded_at_utc,f.original_name,f.size_bytes,f.stored_at_utc FROM current_statement_document d "
        "LEFT JOIN statement_file f USING(file_sha256) ORDER BY d.period_from,d.document_ref").fetchall()
    removed = _removed_files(connection)
    documents = {row["document_ref"]: _document(row) for row in rows}
    for document in documents.values():
        document["file_removed"] = document["file_sha256"] in removed
    return documents


def _has_table(connection, name: str) -> bool:
    return connection.execute("SELECT count(*) FROM sqlite_master WHERE name=?", (name,)).fetchone()[0] == 1


def _closures(connection) -> dict[str, str]:
    """Je geschlossenem Konto der Tag; ein Speicher ohne die Tabelle kennt keine."""
    if not _has_table(connection, "current_statement_account_closure"):
        return {}
    return {row["account_id"]: row["closed_on"] for row in connection.execute(
        "SELECT account_id,closed_on FROM current_statement_account_closure") if row["closed_on"] is not None}


def _inactivity(connection) -> dict[str, dict[str, Any]]:
    """Je Konto mit Ruhe-Eintrag: seit wann es ruht (None, wenn wieder aktiv) und - nach dem Reaktivieren - seit wann es geruht
    hatte und an welchem Tag es wieder aktiviert wurde. Ein Speicher ohne die Tabelle kennt keine."""
    if not _has_table(connection, "statement_account_inactive_entry"):
        return {}
    states: dict[str, dict[str, Any]] = {}
    for row in connection.execute("SELECT account_id,inactive_since,recorded_at_utc FROM statement_account_inactive_entry ORDER BY entry_id"):
        state = states.setdefault(row["account_id"], {"inactive_since": None, "was_inactive_since": None, "reactivated_on": None})
        if row["inactive_since"] is not None:
            state.update(inactive_since=row["inactive_since"], was_inactive_since=None, reactivated_on=None)
        elif state["inactive_since"] is not None:
            state.update(was_inactive_since=state["inactive_since"], inactive_since=None, reactivated_on=row["recorded_at_utc"][:10])
    return states


def _inactive_since(connection) -> dict[str, str]:
    return {account: state["inactive_since"] for account, state in _inactivity(connection).items() if state["inactive_since"] is not None}


def _intake_folder(connection) -> str | None:
    if not _has_table(connection, "statement_intake_setting_entry"):
        return None
    row = connection.execute("SELECT folder FROM statement_intake_setting_entry ORDER BY entry_id DESC LIMIT 1").fetchone()
    return None if row is None else row["folder"]


def _settings(connection) -> dict[str, bool]:
    return {row["account_id"]: bool(row["statements_expected"]) for row in connection.execute(
        "SELECT account_id,statements_expected FROM current_statement_account_setting")}


def _append_document(connection, document_ref: str, values: dict[str, Any], recorded_at_utc: str) -> None:
    row = {"document_ref": document_ref, **values, "recorded_at_utc": recorded_at_utc}
    connection.execute(
        "INSERT INTO statement_document_entry(document_ref,file_sha256,document_kind,period_from,period_to,status,institution_label,account_ids,note,"
        "recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (document_ref, row["file_sha256"], row["document_kind"], row["period_from"], row["period_to"], row["status"], row["institution_label"],
         json.dumps(row["account_ids"], separators=(",", ":")), row["note"], recorded_at_utc, _fingerprint(row)))


def _placement(value, known: dict[str, dict[str, Any]], *, with_kind: bool) -> dict[str, Any]:
    """Wofuer ein Dokument gilt: Art, Zeitraum in Monaten, Konten und - wenn das ganze Institut gemeint ist - dessen Angabe."""
    fields = {"period_from", "period_to", "account_ids", "institution_label", "note"} | ({"document_kind"} if with_kind else set())
    if not isinstance(value, dict) or set(value) != fields:
        _abort("statement_archive_input_invalid")
    first, last = _month(value["period_from"]), _month(value["period_to"])
    if last < first or len(_months(first, last)) > 600:
        _abort("statement_archive_input_invalid")
    accounts = _accounts(value["account_ids"])
    if any(account not in known for account in accounts):
        _abort("statement_archive_account_unknown")
    kind = value["document_kind"] if with_kind else "account_statement"
    if kind not in KINDS:
        _abort("statement_archive_input_invalid")
    return {"document_kind": kind, "period_from": first, "period_to": last, "account_ids": accounts,
            "institution_label": _line(value["institution_label"], LABEL_LIMIT), "note": _line(value["note"], NOTE_LIMIT)}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _confirmed(confirmed) -> None:
    if confirmed is not True:
        _abort("statement_archive_confirmation_required")


def store_statement_document_v1(space, context_value, source_path, document, recorded_at_utc, confirmed, original_name=None) -> dict[str, Any]:
    """Hinterlegt eine Datei als Dokument. Die Quelle bleibt unveraendert; dieselbe Datei liegt in der Ablage nur einmal.

    `original_name` nennt den Dateinamen, wenn die Quelle ihn nicht traegt (ein Upload liegt unter einem Zwischennamen).
    """
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    known = _catalog_accounts(space, context)
    placement = _placement(document, known, with_kind=True)
    source = Path(source_path) if isinstance(source_path, (str, Path)) else None
    if source is None or source.is_symlink() or not source.is_file():
        _abort("statement_archive_file_invalid")
    if source.stat().st_size > MAX_FILE_BYTES:
        _abort("statement_archive_file_too_large")
    # Nur der Name, kein Pfad: Was vor dem letzten Trenner steht, gehoert nicht in die Ablage.
    raw_name = source.name if original_name is None else original_name
    if not isinstance(raw_name, str):
        _abort("statement_archive_input_invalid")
    name = _line(re.split(r"[\\/]", raw_name)[-1], NAME_LIMIT, nullable=False)
    connection = _connect(space, context, True)
    try:
        # In Stuecken kopiert und dabei gepruefsummt: Die Datei liegt nie ganz im Speicher, und der Pruefwert gehoert zu
        # genau den Bytes, die in der Ablage landen. Der Zwischenname beginnt mit einem Punkt und wird in jedem Fall
        # weggeraeumt - ein Rest wuerde das Backup anhalten ("unsettled").
        folder = Path(space) / AREA / FILES
        temporary = folder / f".incoming-{os.urandom(8).hex()}.tmp"
        digest, size = hashlib.sha256(), 0
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                try:
                    reader = source.open("rb")
                except OSError:
                    _abort("statement_archive_file_invalid")
                with reader:
                    for chunk in iter(lambda: reader.read(CHUNK_BYTES), b""):
                        size += len(chunk)
                        if size > MAX_FILE_BYTES:
                            _abort("statement_archive_file_too_large")
                        digest.update(chunk)
                        handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            digest = digest.hexdigest()
            target = folder / digest
            if not target.exists():
                os.replace(temporary, target)
            elif target.is_symlink() or _file_sha256(target) != digest:
                _abort("statement_archive_store_invalid")
        except OSError:
            _abort("statement_archive_store_invalid")
        finally:
            temporary.unlink(missing_ok=True)
        with connection:
            # Dieselbe Datei mit derselben Zuordnung ein zweites Mal hinterlegt: nichts Neues.
            for existing in _current_documents(connection).values():
                if existing["file_sha256"] == digest and existing["status"] in FILE_STATUSES and all(
                        existing[key] == placement[key] for key in placement):
                    return {"contract_version": CONTRACT, "status": "unchanged", "document_ref": existing["document_ref"], "file_sha256": digest,
                            "file_stored": False, "provider_access": False, "network_access": False, "canonical_write": False}
            stored = connection.execute("SELECT 1 FROM statement_file WHERE file_sha256=?", (digest,)).fetchone() is None
            if stored:
                connection.execute("INSERT INTO statement_file VALUES(?,?,?,?)", (digest, name, size, stamp))
            elif digest in _removed_files(connection):
                # Dieselbe Datei nach dem Entfernen erneut hinterlegt: Sie liegt wieder in der Ablage.
                connection.execute("INSERT INTO statement_file_event(file_sha256,event,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                                   (digest, "restored", stamp, _fingerprint({"file": digest, "event": "restored", "at": stamp})))
            count = connection.execute("SELECT count(*) FROM statement_document_entry").fetchone()[0]
            document_ref = "sdoc_" + _fingerprint({"file": digest, "placement": placement, "at": stamp, "n": count})[:32]
            _append_document(connection, document_ref, {**placement, "file_sha256": digest, "status": "unconfirmed"}, stamp)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "stored", "document_ref": document_ref, "file_sha256": digest, "file_stored": stored,
            "provider_access": False, "network_access": False, "canonical_write": False}


def declare_statements_unavailable_v1(space, context_value, declaration, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Erklaert fuer Konten und Monate: Auszug nicht mehr vorhanden, vom Eigentuemer bestaetigt. Ohne Datei."""
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    placement = _placement(declaration, _catalog_accounts(space, context), with_kind=False)
    connection = _connect(space, context, True)
    try:
        with connection:
            count = connection.execute("SELECT count(*) FROM statement_document_entry").fetchone()[0]
            document_ref = "sdoc_" + _fingerprint({"declaration": placement, "at": stamp, "n": count})[:32]
            _append_document(connection, document_ref, {**placement, "file_sha256": None, "status": "not_available"}, stamp)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "declared", "document_ref": document_ref,
            "provider_access": False, "network_access": False, "canonical_write": False}


def revise_statement_document_v1(space, context_value, document_ref, changes, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Neuer Stand eines Dokuments: Art, Zeitraum, Konten, Notiz oder Stand (bestaetigen, Bestaetigung zuruecknehmen, zurueckziehen)."""
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    allowed = {"document_kind", "period_from", "period_to", "account_ids", "institution_label", "note", "status"}
    if not isinstance(document_ref, str) or DOCUMENT_REF.fullmatch(document_ref) is None or not isinstance(changes, dict) or not changes or set(changes) - allowed:
        _abort("statement_archive_input_invalid")
    known = _catalog_accounts(space, context)
    connection = _connect(space, context, True)
    try:
        with connection:
            current = _current_documents(connection).get(document_ref)
            if current is None or current["status"] == "withdrawn":
                _abort("statement_archive_document_unknown")
            merged = {key: changes.get(key, current[key]) for key in ("document_kind", "period_from", "period_to", "account_ids", "institution_label", "note")}
            placement = _placement(merged, known, with_kind=True)
            status = changes.get("status", current["status"])
            has_file = current["file_sha256"] is not None
            # Bestaetigt wird nur, was eine Datei traegt; eine Erklaerung ohne Datei bleibt Erklaerung oder wird zurueckgezogen.
            if status not in STATUSES or (has_file and status == "not_available") or (not has_file and status in FILE_STATUSES):
                _abort("statement_archive_input_invalid")
            values = {**placement, "file_sha256": current["file_sha256"], "status": status}
            if all(values[key] == current[key] for key in values):
                return {"contract_version": CONTRACT, "status": "unchanged", "document_ref": document_ref,
                        "provider_access": False, "network_access": False, "canonical_write": False}
            _append_document(connection, document_ref, values, stamp)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "revised", "document_ref": document_ref,
            "provider_access": False, "network_access": False, "canonical_write": False}


def set_statement_account_expectation_v1(space, context_value, account_id, statements_expected, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Nimmt ein Konto aus der Lueckenanzeige ("hier gibt es keine Auszuege") oder wieder hinein."""
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    if not isinstance(account_id, str) or ACCOUNT_ID.fullmatch(account_id) is None or not isinstance(statements_expected, bool):
        _abort("statement_archive_input_invalid")
    if account_id not in _catalog_accounts(space, context):
        _abort("statement_archive_account_unknown")
    connection = _connect(space, context, True)
    try:
        with connection:
            if _settings(connection).get(account_id, True) == statements_expected:
                return {"contract_version": CONTRACT, "status": "unchanged", "provider_access": False, "network_access": False, "canonical_write": False}
            row = {"account_id": account_id, "statements_expected": statements_expected, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO statement_account_setting_entry(account_id,statements_expected,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                               (account_id, int(statements_expected), stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "provider_access": False, "network_access": False, "canonical_write": False}


def set_statement_account_closure_v1(space, context_value, account_id, closed_on, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Konto geschlossen seit einem Tag (#513) - oder mit None wieder offen. Ab dem Monat danach erwartet die Ablage keine Auszuege."""
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    if not isinstance(account_id, str) or ACCOUNT_ID.fullmatch(account_id) is None or not (closed_on is None or (isinstance(closed_on, str) and DAY.fullmatch(closed_on))):
        _abort("statement_archive_input_invalid")
    if account_id not in _catalog_accounts(space, context):
        _abort("statement_archive_account_unknown")
    connection = _connect(space, context, True)
    try:
        with connection:
            if _closures(connection).get(account_id) == closed_on:
                return {"contract_version": CONTRACT, "status": "unchanged", "provider_access": False, "network_access": False, "canonical_write": False}
            row = {"account_id": account_id, "closed_on": closed_on, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO statement_account_closure_entry(account_id,closed_on,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                               (account_id, closed_on, stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "provider_access": False, "network_access": False, "canonical_write": False}


def read_statement_account_closures_v1(space, context_value) -> dict[str, str]:
    """Je geschlossenem Konto der Tag (Kennung -> JJJJ-MM-TT); leer ohne Ablage."""
    context = statement_archive_scope_v1(context_value)
    connection = _connect(space, context, False)
    if connection is None:
        return {}
    try:
        return _closures(connection)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
        return {}
    finally:
        connection.close()


def set_statement_account_inactivity_v1(space, context_value, account_id, inactive_since, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Konto inaktiv seit einem Tag (#529 Punkt 1) - oder mit None wieder aktiv. Ein geschlossenes Konto ruht nicht; es ist zu."""
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    if not isinstance(account_id, str) or ACCOUNT_ID.fullmatch(account_id) is None or \
            not (inactive_since is None or (isinstance(inactive_since, str) and DAY.fullmatch(inactive_since))):
        _abort("statement_archive_input_invalid")
    if account_id not in _catalog_accounts(space, context):
        _abort("statement_archive_account_unknown")
    connection = _connect(space, context, True)
    try:
        with connection:
            if inactive_since is not None and account_id in _closures(connection):
                _abort("statement_archive_input_invalid")
            current = _inactivity(connection).get(account_id, {}).get("inactive_since")
            if current == inactive_since:
                return {"contract_version": CONTRACT, "status": "unchanged", "provider_access": False, "network_access": False, "canonical_write": False}
            row = {"account_id": account_id, "inactive_since": inactive_since, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO statement_account_inactive_entry(account_id,inactive_since,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                               (account_id, inactive_since, stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "provider_access": False, "network_access": False, "canonical_write": False}


def read_statement_account_states_v1(space, context_value) -> dict[str, dict[str, Any]]:
    """Je Konto mit Zustand: geschlossen seit, inaktiv seit und - wieder aktiv - seit wann es geruht hatte. Leer ohne Ablage.

    Fuer Eingang, Importe und Datenbasis: Ein ruhendes oder geschlossenes Konto wird dort nicht angeboten bzw. zugeklappt gezeigt.
    """
    context = statement_archive_scope_v1(context_value)
    connection = _connect(space, context, False)
    if connection is None:
        return {}
    try:
        closures = _closures(connection)
        inactivity = _inactivity(connection)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
        return {}
    finally:
        connection.close()
    states: dict[str, dict[str, Any]] = {}
    for account in sorted(set(closures) | set(inactivity)):
        state = inactivity.get(account, {})
        states[account] = {"closed_on": closures.get(account), "inactive_since": state.get("inactive_since"),
                           "was_inactive_since": state.get("was_inactive_since"), "reactivated_on": state.get("reactivated_on")}
    return states


def intake_folder_checked_v1(space, folder) -> str:
    """Ein Belegordner, wie ihn das Festlegen annimmt, aufgeloest: absolut, vorhanden, keine Verknuepfung, ausserhalb des Datenraums. Der
    Einrichtungsdialog (#572) prueft damit schon an der Frage; den Datenraum braucht es dafuer noch nicht, nur seinen Pfad."""
    if not isinstance(folder, str) or not 1 <= len(folder) <= FOLDER_LIMIT or "\x00" in folder:
        _abort("statement_archive_input_invalid")
    path = Path(folder)
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        _abort("statement_intake_folder_invalid")
    resolved = path.resolve()
    inside = Path(space).resolve()
    # Der Ordner liegt ausserhalb des Datenraums: Die Ablage im Datenraum ist das Ziel, nicht die Quelle.
    if resolved == inside or inside in resolved.parents or resolved in inside.parents:
        _abort("statement_intake_folder_invalid")
    return str(resolved)


def set_statement_intake_folder_v1(space, context_value, folder, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Der Belegordner des monatlichen Eingangs (#513): ein Ordner ausserhalb von Portelyra, nur gelesen. None nimmt ihn zurueck."""
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    if folder is not None:
        folder = intake_folder_checked_v1(space, folder)
    connection = _connect(space, context, True)
    try:
        with connection:
            if _intake_folder(connection) == folder:
                return {"contract_version": CONTRACT, "status": "unchanged", "folder": folder, "provider_access": False, "network_access": False, "canonical_write": False}
            row = {"folder": folder, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO statement_intake_setting_entry(folder,recorded_at_utc,entry_fingerprint) VALUES(?,?,?)", (folder, stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "folder": folder, "provider_access": False, "network_access": False, "canonical_write": False}


def read_statement_intake_folder_v1(space, context_value) -> str | None:
    context = statement_archive_scope_v1(context_value)
    connection = _connect(space, context, False)
    if connection is None:
        return None
    try:
        return _intake_folder(connection)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
        return None
    finally:
        connection.close()


def _known_files(space, context) -> dict[str, str]:
    """Je hinterlegter Datei, ob ein Dokument sie traegt ("filed"), nur zurueckgezogene ("withdrawn") oder sie entfernt ist ("removed")."""
    connection = _connect(space, context, False)
    if connection is None:
        return {}
    try:
        documents = _current_documents(connection)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
        return {}
    finally:
        connection.close()
    known: dict[str, str] = {}
    for document in documents.values():
        sha = document["file_sha256"]
        if sha is None:
            continue
        state = "removed" if document["file_removed"] else ("withdrawn" if document["status"] == "withdrawn" else "filed")
        if known.get(sha) != "filed":
            known[sha] = "filed" if state == "filed" else known.get(sha, state)
    return known


def _movement_months(space, context) -> dict[str, set[str]]:
    """Je Konto die Monate mit Bewegung: Buchungen des Bestands (beide Seiten eines Transfers) und Cash-Bewegungen samt Zinsen."""
    months: dict[str, set[str]] = {}

    def add(account, day):
        if account and isinstance(day, str) and len(day) >= 7:
            months.setdefault(account, set()).add(day[:7])

    try:
        binding = read_desktop_product_asset_activity_binding_v1(space, context)
        if binding.get("ledger_path"):
            connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
            try:
                for account, related, day in connection.execute("SELECT account_id,related_account_id,local_date FROM current_asset_activity_event"):
                    add(account, day)
                    add(related, day)
            finally:
                connection.close()
        cash = Path(space) / CASH_AREA / CASH_STORE
        if cash.exists():
            projection = read_desktop_cash_coverage_exchange_projection_v1(cash, context)
            for row in projection["cash_events"]:
                add(row["account_id"], row["local_date"])
                add(row["related_account_id"], row["local_date"])
            for row in projection["income_events"]:
                add(row["account_id"], row["local_date"])
    except (DesktopProductAssetActivityV1Error, DesktopCashCoverageV1Error, sqlite3.Error, KeyError, TypeError):
        _abort("statement_archive_store_invalid")
    return months


def _coverage(documents: dict[str, dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    """Je Konto und Monat, was ihn abdeckt: staerkster Stand, Zahl der Dokumente, ob eines am ganzen Institut haengt."""
    rank = {"confirmed": 3, "unconfirmed": 2, "not_available": 1}
    cells: dict[tuple[str, str], dict[str, Any]] = {}
    for document in documents.values():
        if document["status"] not in rank or document["document_kind"] not in MONTH_KINDS:
            continue
        for month in _months(document["period_from"], document["period_to"]):
            for account in document["account_ids"]:
                cell = cells.setdefault((account, month), {"status": document["status"], "document_count": 0, "via_institution": False})
                if rank[document["status"]] > rank[cell["status"]]:
                    cell["status"] = document["status"]
                cell["document_count"] += 1
                cell["via_institution"] = cell["via_institution"] or document["institution_label"] is not None
    return cells


def _year(value) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1990 <= value <= 2100:
        _abort("statement_archive_input_invalid")
    return value


def _month_cell(account: str, month: str, cells, movements, expected: bool, closed_on: str | None = None,
                inactive_since: str | None = None) -> dict[str, Any]:
    cell = cells.get((account, month))
    moved = month in movements.get(account, ())
    if cell is not None:
        status = cell["status"]
    elif closed_on is not None and month > closed_on[:7]:
        status = "closed"
    elif inactive_since is not None and month > inactive_since[:7]:
        status = "inactive"
    elif not expected:
        status = "not_expected"
    else:
        status = "open" if moved else "no_movement"
    return {"month": month, "status": status, "has_movement": moved, "document_count": 0 if cell is None else cell["document_count"],
            "via_institution": False if cell is None else cell["via_institution"]}


def read_statement_archive_overview_v1(space, context_value, year) -> dict[str, Any]:
    """Das Jahr auf einen Blick: Institute, darunter Konten mit zwoelf Monaten, und die Dokumente, die das Jahr beruehren.

    Gibt die Kennungen der Konten zurueck - fuer den Dienst, der sie der Auswahl der Oberflaeche zuordnet, nicht fuer die Oberflaeche.
    """
    context = statement_archive_scope_v1(context_value)
    return _overview(_year(year), *_overview_sources(space, context))


def _overview_sources(space, context) -> tuple[dict, dict, dict, dict, dict]:
    known = _catalog_accounts(space, context)
    connection = _connect(space, context, False)
    documents: dict[str, dict[str, Any]] = {}
    settings: dict[str, bool] = {}
    closures: dict[str, str] = {}
    inactivity: dict[str, dict[str, Any]] = {}
    if connection is not None:
        try:
            documents, settings, closures = _current_documents(connection), _settings(connection), _closures(connection)
            inactivity = _inactivity(connection)
        except sqlite3.Error:
            _abort("statement_archive_store_invalid")
        finally:
            connection.close()
    return known, documents, settings, _movement_months(space, context), closures, inactivity


def read_statement_archive_years_v1(space, context_value, years) -> list[dict[str, Any]]:
    """Mehrere Jahre auf einmal (Datenbasis, rc.314): dieselbe Uebersicht je Jahr, die Quellen nur einmal gelesen. Je Jahr las
    die Uebersicht Bestand und Cash-Bewegungen neu."""
    context = statement_archive_scope_v1(context_value)
    if not isinstance(years, (list, tuple)) or len(years) > 50:
        _abort("statement_archive_input_invalid")
    wanted = [_year(year) for year in years]
    sources = _overview_sources(space, context)
    return [_overview(year, *sources) for year in wanted]


def _overview(wanted: int, known, documents, settings, movements, closures=None, inactivity=None) -> dict[str, Any]:
    cells = _coverage(documents)
    months = [f"{wanted:04d}-{month:02d}" for month in range(1, 13)]
    institutions: dict[tuple[str, str], dict[str, Any]] = {}
    counts = {status: 0 for status in MONTH_STATUSES}
    for account_id, account in known.items():
        expected = settings.get(account_id, True)
        closed_on = (closures or {}).get(account_id)
        state = (inactivity or {}).get(account_id, {})
        inactive_since = state.get("inactive_since")
        row = [_month_cell(account_id, month, cells, movements, expected, closed_on, inactive_since) for month in months]
        # Ein archiviertes Konto steht nur da, wenn das Jahr etwas von ihm traegt; ein geschlossenes nur bis zu seinem Jahr.
        if (account["status"] != "active" or (closed_on is not None and int(closed_on[:4]) < wanted)) and \
                not any(cell["status"] not in ("no_movement", "not_expected", "closed", "inactive") for cell in row):
            continue
        label = account["institution_label"] or None
        group = institutions.setdefault(("1" if label is None else "0", (label or "").lower()), {"institution_label": label, "accounts": []})
        group["accounts"].append({"account_id": account_id, "account_label": account["display_name"], "account_type": account["account_type"],
                                  "statements_expected": expected, "closed_on": closed_on, "inactive_since": inactive_since,
                                  "was_inactive_since": state.get("was_inactive_since"), "reactivated_on": state.get("reactivated_on"),
                                  "months": row})
        for cell in row:
            counts[cell["status"]] += 1
    first, last = months[0], months[-1]
    touching = [document for document in documents.values()
                if document["status"] != "withdrawn" and document["period_from"] <= last and document["period_to"] >= first]
    ordered = [institutions[key] for key in sorted(institutions)]
    for group in ordered:
        group["accounts"].sort(key=lambda account: account["account_label"].lower())
    # Zurueckgezogen, aber mit Datei in der Ablage: Nur diese lassen sich endgueltig entfernen (#434).
    withdrawn = [document for document in documents.values()
                 if document["status"] == "withdrawn" and document["file_sha256"] is not None and not document["file_removed"]
                 and document["period_from"] <= last and document["period_to"] >= first]
    return {"contract_version": CONTRACT, "status": "ready", "year": wanted, "institutions": ordered,
            "documents": sorted(touching, key=lambda document: (document["period_from"], document["document_ref"])),
            "withdrawn_documents": sorted(withdrawn, key=lambda document: (document["period_from"], document["document_ref"])),
            "month_status_counts": counts, "orphan_account_count": len({account for document in documents.values() for account in document["account_ids"]} - set(known)),
            "provider_access": False, "network_access": False, "canonical_write": False}


def read_statement_year_evidence_v1(space, context_value, year, evidence=()) -> dict[str, Any]:
    """Was zu einem Jahr an Unterlagen da ist und was fehlt - mit Kennungen, fuer Rechenkerne.

    `evidence` nennt Konto-Monate ausserhalb des Jahres, an denen ein Beleg haengt: die Anschaffung eines im Jahr
    verbrauchten Lots und die Umschichtungen, die es trugen. Geliefert werden die Dokumente, die das Jahr beruehren
    oder einen dieser Monate abdecken (`relations` nennt, weshalb), die zwoelf Monate des Jahres je Konto und der
    Stand der genannten Monate. Liest nur; die Kennungen der Konten gehen nicht an die Oberflaeche.
    """
    context = statement_archive_scope_v1(context_value)
    wanted = _year(year)
    known = _catalog_accounts(space, context)
    if not isinstance(evidence, (list, tuple)) or len(evidence) > 20000:
        _abort("statement_archive_input_invalid")
    months = [f"{wanted:04d}-{month:02d}" for month in range(1, 13)]
    pairs: set[tuple[str, str]] = set()
    unknown = 0
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"account_id", "month"} or not isinstance(item["account_id"], str) or (
                ACCOUNT_ID.fullmatch(item["account_id"]) is None):
            _abort("statement_archive_input_invalid")
        month = _month(item["month"])
        if item["account_id"] not in known:
            unknown += 1
        elif month not in months:
            pairs.add((item["account_id"], month))
    connection = _connect(space, context, False)
    documents: dict[str, dict[str, Any]] = {}
    settings: dict[str, bool] = {}
    if connection is not None:
        try:
            documents, settings = _current_documents(connection), _settings(connection)
        except sqlite3.Error:
            _abort("statement_archive_store_invalid")
        finally:
            connection.close()
    movements = _movement_months(space, context)
    cells = _coverage(documents)
    chosen = []
    for document in documents.values():
        if document["status"] == "withdrawn":
            continue
        covered = set(_months(document["period_from"], document["period_to"]))
        # Anschaffung belegt nur, was einen Monat belegt (#536): eine Jahresbescheinigung des Anschaffungsjahres nicht.
        relations = (["tax_year"] if document["period_from"] <= months[-1] and document["period_to"] >= months[0] else []) + (
            ["acquisition"] if document["document_kind"] in MONTH_KINDS and any((account, month) in pairs for account in document["account_ids"]
                                                                                for month in covered) else [])
        if relations:
            chosen.append({**document, "relations": relations})
    return {
        "contract_version": CONTRACT, "status": "ready", "year": wanted,
        "accounts": {account_id: {"account_label": account["display_name"], "account_type": account["account_type"],
                                  "institution_label": account["institution_label"] or None, "account_status": account["status"],
                                  "statements_expected": settings.get(account_id, True)} for account_id, account in known.items()},
        "documents": sorted(chosen, key=lambda document: (document["period_from"], document["document_ref"])),
        "year_months": {account_id: [_month_cell(account_id, month, cells, movements, settings.get(account_id, True)) for month in months]
                        for account_id in known},
        # Ein Monat der Anschaffung traegt eine Buchung - er ist offen, solange ihn nichts abdeckt, auch auf einem ausgenommenen Konto nicht "ohne Bewegung".
        "evidence_months": [{"account_id": account, **_month_cell(account, month, cells, {account: {month}}, settings.get(account, True))}
                            for account, month in sorted(pairs)],
        "unknown_evidence_count": unknown, "provider_access": False, "network_access": False, "canonical_write": False}


def close_statement_year_v1(space, context_value, year, account_ids, declare_rest, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Schliesst ein Jahr fuer Konten ab: bestaetigt die hinterlegten Dateien und erklaert auf Wunsch die uebrigen offenen Monate als nicht mehr vorhanden."""
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    wanted = _year(year)
    accounts = _accounts(account_ids)
    if not isinstance(declare_rest, bool):
        _abort("statement_archive_input_invalid")
    known = _catalog_accounts(space, context)
    if any(account not in known for account in accounts):
        _abort("statement_archive_account_unknown")
    movements = _movement_months(space, context)
    months = [f"{wanted:04d}-{month:02d}" for month in range(1, 13)]
    connection = _connect(space, context, True)
    confirmed_count = declared = 0
    try:
        with connection:
            documents = _current_documents(connection)
            for document in documents.values():
                if document["status"] == "unconfirmed" and document["period_from"] <= months[-1] and document["period_to"] >= months[0] and (
                        set(document["account_ids"]) & set(accounts)):
                    values = {key: document[key] for key in ("file_sha256", "document_kind", "period_from", "period_to", "institution_label", "account_ids", "note")}
                    _append_document(connection, document["document_ref"], {**values, "status": "confirmed"}, stamp)
                    confirmed_count += 1
            if declare_rest:
                cells = _coverage(_current_documents(connection))
                settings = _settings(connection)
                for account in accounts:
                    if not settings.get(account, True):
                        continue
                    run: list[str] = []
                    for month in [*months, None]:
                        open_month = month is not None and (account, month) not in cells and month in movements.get(account, ())
                        if open_month:
                            run.append(month)
                            continue
                        if run:
                            # Je zusammenhaengender Luecke eine Erklaerung fuer genau dieses Konto.
                            count = connection.execute("SELECT count(*) FROM statement_document_entry").fetchone()[0]
                            placement = {"document_kind": "account_statement", "period_from": run[0], "period_to": run[-1], "account_ids": [account],
                                         "institution_label": None, "note": None}
                            ref = "sdoc_" + _fingerprint({"declaration": placement, "at": stamp, "n": count})[:32]
                            _append_document(connection, ref, {**placement, "file_sha256": None, "status": "not_available"}, stamp)
                            declared += 1
                            run = []
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "closed", "year": wanted, "confirmed_document_count": confirmed_count,
            "declared_gap_count": declared, "provider_access": False, "network_access": False, "canonical_write": False}


def read_statement_file_v1(space, context_value, document_ref) -> dict[str, Any]:
    """Die hinterlegte Datei eines Dokuments - mit nachgerechnetem Pruefwert. Liefert den Ort in der Ablage fuer den Abruf."""
    context = statement_archive_scope_v1(context_value)
    if not isinstance(document_ref, str) or DOCUMENT_REF.fullmatch(document_ref) is None:
        _abort("statement_archive_input_invalid")
    connection = _connect(space, context, False)
    if connection is None:
        _abort("statement_archive_document_unknown")
    try:
        document = _current_documents(connection).get(document_ref)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    if document is None or document["file_sha256"] is None or document["status"] == "withdrawn":
        _abort("statement_archive_document_unknown")
    if document["file_removed"]:
        _abort("statement_archive_file_removed")
    path = Path(space) / AREA / FILES / document["file_sha256"]
    if path.is_symlink() or not path.is_file() or _file_sha256(path) != document["file_sha256"]:
        _abort("statement_archive_file_invalid")
    return {"contract_version": CONTRACT, "status": "ready", "document_ref": document_ref, "path": str(path), "original_name": document["original_name"],
            "size_bytes": document["size_bytes"], "file_sha256": document["file_sha256"], "provider_access": False, "network_access": False,
            "canonical_write": False}


def list_statement_files_v1(space, context_value, account_ids, year_from, year_to, kinds=None) -> dict[str, Any]:
    """Die hinterlegten Dateien fuer Konten und Jahre - als Quelle der Importe (#434: "Leser lesen aus der Ablage").

    Je Datei einmal, mit Pruefwert und Ort in der Ablage; nur Dokumente mit Datei, nicht zurueckgezogen, mit einem der Konten und
    einem Zeitraum, der die Jahre beruehrt. Gelesen wird nur; der Pruefwert wird beim Abruf eines einzelnen Dokuments nachgerechnet.
    """
    context = statement_archive_scope_v1(context_value)
    accounts = set(_accounts(account_ids))
    # Nur bestimmte Arten (#434): Der Cash-Import nimmt Kontoauszuege und Exporte - eine Steuerbescheinigung am selben Konto
    # hielte sonst den ganzen Stapel an.
    if kinds is not None and (not isinstance(kinds, (list, tuple)) or not kinds or any(kind not in KINDS for kind in kinds)):
        _abort("statement_archive_input_invalid")
    wanted_kinds = set(KINDS if kinds is None else kinds)
    first_year, last_year = _year(year_from), _year(year_to)
    if last_year < first_year:
        _abort("statement_archive_input_invalid")
    first, last = f"{first_year:04d}-01", f"{last_year:04d}-12"
    connection = _connect(space, context, False)
    if connection is None:
        return {"contract_version": CONTRACT, "status": "ready", "files": [], "provider_access": False, "network_access": False, "canonical_write": False}
    try:
        documents = _current_documents(connection)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    files: dict[str, dict[str, Any]] = {}
    for document in sorted(documents.values(), key=lambda item: (item["period_from"], item["original_name"] or "", item["document_ref"])):
        if (document["file_sha256"] is None or document["status"] not in FILE_STATUSES or document["file_removed"] or document["document_kind"] not in wanted_kinds
                or not accounts & set(document["account_ids"]) or document["period_from"] > last or document["period_to"] < first):
            continue
        path = Path(space) / AREA / FILES / document["file_sha256"]
        if path.is_symlink() or not path.is_file():
            continue
        files.setdefault(document["file_sha256"], {"file_sha256": document["file_sha256"], "original_name": document["original_name"],
                                                   "document_kind": document["document_kind"], "period_from": document["period_from"],
                                                   "period_to": document["period_to"], "status": document["status"], "path": str(path)})
    return {"contract_version": CONTRACT, "status": "ready", "files": list(files.values()), "provider_access": False, "network_access": False,
            "canonical_write": False}


def remove_statement_file_v1(space, context_value, document_ref, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Entfernt die Datei eines zurueckgezogenen Dokuments endgueltig aus der Ablage (#434). Nur, wenn kein anderes Dokument sie noch
    traegt; die Eintraege der Dokumente bleiben, die Datei ist danach nicht mehr abrufbar. Laesst sich nicht rueckgaengig machen -
    ausser durch erneutes Hinterlegen derselben Datei."""
    _confirmed(confirmed)
    context = statement_archive_scope_v1(context_value)
    stamp = _utc(recorded_at_utc)
    if not isinstance(document_ref, str) or DOCUMENT_REF.fullmatch(document_ref) is None:
        _abort("statement_archive_input_invalid")
    connection = _connect(space, context, True)
    try:
        with connection:
            documents = _current_documents(connection)
            document = documents.get(document_ref)
            if document is None or document["file_sha256"] is None:
                _abort("statement_archive_document_unknown")
            digest = document["file_sha256"]
            if document["status"] != "withdrawn" or any(other["file_sha256"] == digest and other["status"] != "withdrawn" for other in documents.values()):
                _abort("statement_archive_input_invalid")
            if document["file_removed"]:
                return {"contract_version": CONTRACT, "status": "unchanged", "document_ref": document_ref,
                        "provider_access": False, "network_access": False, "canonical_write": False}
            connection.execute("INSERT INTO statement_file_event(file_sha256,event,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                               (digest, "removed", stamp, _fingerprint({"file": digest, "event": "removed", "at": stamp})))
            # Erst entfernen, dann festschreiben: Scheitert das Loeschen, bleibt auch der Eintrag aus.
            path = Path(space) / AREA / FILES / digest
            if path.is_symlink():
                _abort("statement_archive_store_invalid")
            path.unlink(missing_ok=True)
    except sqlite3.Error:
        _abort("statement_archive_store_invalid")
    except OSError:
        _abort("statement_archive_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "removed", "document_ref": document_ref,
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "KINDS", "MONTH_KINDS", "MONTH_STATUSES", "YEAR_KINDS", "STATUSES", "STORE", "StatementArchiveV1Error", "close_statement_year_v1",
    "declare_statements_unavailable_v1", "intake_folder_checked_v1", "list_statement_files_v1", "read_statement_archive_overview_v1",
    "read_statement_archive_years_v1", "read_statement_file_v1",
    "read_statement_year_evidence_v1", "remove_statement_file_v1", "revise_statement_document_v1",
    "set_statement_account_expectation_v1", "set_statement_account_inactivity_v1", "read_statement_account_states_v1", "statement_archive_scope_v1", "statement_archive_v1_error_codes", "store_statement_document_v1",
]
