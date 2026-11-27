"""Das Institut als eigenes Stammdatum: Name, Art und seine Konten (#430).

Festlegung (12./13.10.2026): Das Institut ist die Oberklasse, Konten sind Unterinstanzen; ein Institut entsteht mit
seinem ersten Konto - ohne Konto ergibt es keinen Sinn. Freistellungsauftrag, Verlusttoepfe und Quellensteuer haengen am
Institut (`institution_tax_settings_v1`). Hier steht, was ein Institut ausserdem traegt: seine Art.

Welche Institute es gibt, sagen die Konten der Stammdaten (Angabe "Institut / Boerse"); ein Institut erkennt der Speicher
wie das Kontoformular an seinem Namen ohne Leerraum und Gross-/Kleinschreibung. Wie die anderen Angaben neben den
Stammdaten haengt der Speicher nur an; der gueltige Stand je Institut ist der juengste Eintrag. Beim Umbenennen eines
Instituts zieht seine Art mit. Buchungsbestand, FIFO und Bewertung beruehrt er nicht. Kein Providerzugriff, kein
Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sqlite3

from migrations.reference.institution_tax_settings_v1 import (
    InstitutionTaxSettingsV1Error, institution_key_v1, institution_tax_settings_scope_v1, known_institutions_v1,
)

AREA = "institution-master-v1"
STORE = "institution-master.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "institution_master_v1"
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
BATCH_LIMIT = 200
# Die Arten eines Instituts - die Kennung ist der Wert, der Name steht in der Oberflaeche.
KINDS = ("bank", "broker", "crypto_exchange", "wallet", "metal_custody", "other")
FAILURE_CODES = (
    "institution_master_confirmation_required",
    "institution_master_input_invalid",
    "institution_master_institution_unknown",
    "institution_master_store_invalid",
)
SCHEMA = (
    "CREATE TABLE institution_master_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE institution_master_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "institution_key TEXT NOT NULL CHECK(length(institution_key) BETWEEN 1 AND 120),"
    "institution_label TEXT NOT NULL CHECK(length(institution_label) BETWEEN 1 AND 120),"
    "kind TEXT CHECK(kind IS NULL OR kind IN ('bank','broker','crypto_exchange','wallet','metal_custody','other')),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX institution_master_entry_key ON institution_master_entry(institution_key, entry_id)",
    "CREATE TRIGGER institution_master_entry_no_update BEFORE UPDATE ON institution_master_entry "
    "BEGIN SELECT RAISE(ABORT, 'institution_master_entry_immutable'); END",
    "CREATE TRIGGER institution_master_entry_no_delete BEFORE DELETE ON institution_master_entry "
    "BEGIN SELECT RAISE(ABORT, 'institution_master_entry_immutable'); END",
    "CREATE VIEW current_institution_master AS SELECT entry.* FROM institution_master_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM institution_master_entry later WHERE later.institution_key = entry.institution_key)",
)


class InstitutionMasterV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def institution_master_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise InstitutionMasterV1Error(code if code in FAILURE_CODES else "institution_master_store_invalid")


def _scope(value):
    try:
        return institution_tax_settings_scope_v1(value)
    except InstitutionTaxSettingsV1Error:
        _abort("institution_master_input_invalid")


def _known(space, context) -> dict[str, dict]:
    try:
        return known_institutions_v1(space, context)
    except InstitutionTaxSettingsV1Error:
        _abort("institution_master_store_invalid")
        return {}


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("institution_master_store_invalid")
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
                connection.execute("INSERT INTO institution_master_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("institution_master_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM institution_master_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("institution_master_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("institution_master_store_invalid")
    return connection


def _current(connection) -> dict[str, dict]:
    rows = connection.execute("SELECT institution_key,institution_label,kind,recorded_at_utc FROM current_institution_master ORDER BY institution_key").fetchall()
    return {row["institution_key"]: dict(row) for row in rows}


def _append(connection, current, key, label, kind, recorded_at_utc) -> bool:
    before = current.get(key)
    if (before is None and kind is None) or (before is not None and before["kind"] == kind):
        return False
    row = {"institution_key": key, "institution_label": label, "kind": kind, "recorded_at_utc": recorded_at_utc}
    connection.execute("INSERT INTO institution_master_entry(institution_key,institution_label,kind,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?)",
                       (key, label, kind, recorded_at_utc, _fingerprint(row)))
    current[key] = row
    return True


def record_institution_kinds_v1(space, context_value, entries, recorded_at_utc, confirmed) -> dict:
    """Haengt je Institut seine Art an. Unveraendert schreibt nichts; ohne Art leert den Stand."""
    if confirmed is not True:
        _abort("institution_master_confirmation_required")
    context = _scope(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("institution_master_input_invalid")
    if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= BATCH_LIMIT:
        _abort("institution_master_input_invalid")
    wanted = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"institution_label", "kind"} or not isinstance(entry["institution_label"], str):
            _abort("institution_master_input_invalid")
        if entry["kind"] is not None and entry["kind"] not in KINDS:
            _abort("institution_master_input_invalid")
        key = institution_key_v1(" ".join(entry["institution_label"].split()))
        if not key:
            _abort("institution_master_input_invalid")
        wanted.append((key, entry["kind"]))
    if len({key for key, _ in wanted}) != len(wanted):
        _abort("institution_master_input_invalid")
    known = _known(space, context)
    if any(key not in known for key, _ in wanted):
        _abort("institution_master_institution_unknown")
    connection = _connect(space, context, True)
    written = unchanged = 0
    try:
        with connection:
            current = _current(connection)
            for key, kind in wanted:
                if _append(connection, current, key, known[key]["institution_label"], kind, recorded_at_utc):
                    written += 1
                else:
                    unchanged += 1
    except sqlite3.Error:
        _abort("institution_master_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "written_count": written, "unchanged_count": unchanged,
            "provider_access": False, "network_access": False, "canonical_write": False}


def rename_institution_master_v1(space, context_value, old_label, new_label, recorded_at_utc, confirmed) -> dict:
    """Zieht die Art eines umbenannten Instituts mit. Hat das Ziel schon eine Art, bleibt sie."""
    if confirmed is not True:
        _abort("institution_master_confirmation_required")
    context = _scope(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None or not isinstance(old_label, str) or not isinstance(new_label, str):
        _abort("institution_master_input_invalid")
    old_key, new_text = institution_key_v1(" ".join(old_label.split())), " ".join(new_label.split())
    new_key = institution_key_v1(new_text)
    if not old_key or not new_key or len(new_text) > 120:
        _abort("institution_master_input_invalid")
    result = {"contract_version": CONTRACT, "status": "unchanged", "moved": False, "kept": False,
              "provider_access": False, "network_access": False, "canonical_write": False}
    if old_key == new_key:
        return result
    probe = _connect(space, context, False)
    if probe is None:
        return result
    probe.close()
    connection = _connect(space, context, True)
    try:
        with connection:
            current = _current(connection)
            moving = current.get(old_key)
            if moving is None or moving["kind"] is None:
                return result
            target = current.get(new_key)
            kept = target is not None and target["kind"] is not None
            if not kept:
                _append(connection, current, new_key, new_text, moving["kind"], recorded_at_utc)
            _append(connection, current, old_key, moving["institution_label"], None, recorded_at_utc)
    except sqlite3.Error:
        _abort("institution_master_store_invalid")
    finally:
        connection.close()
    return {**result, "status": "renamed", "moved": not kept, "kept": kept}


def read_institution_master_v1(space, context_value) -> dict:
    """Die Institute der Stammdaten mit Art und Konten. Konten ohne Institutsangabe stehen nicht darin."""
    context = _scope(context_value)
    known = _known(space, context)
    connection = _connect(space, context, False)
    current: dict = {}
    if connection is not None:
        try:
            current = _current(connection)
        except sqlite3.Error:
            _abort("institution_master_store_invalid")
        finally:
            connection.close()
    canonical = Path(space) / "canonical.sqlite"
    try:
        db = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            accounts = db.execute("SELECT display_name,institution_label,status FROM account ORDER BY display_name").fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        _abort("institution_master_store_invalid")
    names: dict[str, list[str]] = {}
    for display_name, label, status in accounts:
        if status != "archived" and isinstance(label, str):
            names.setdefault(institution_key_v1(" ".join(label.split())), []).append(display_name)
    institutions = [{"institution_key": key, "institution_label": value["institution_label"], "kind": (current.get(key) or {}).get("kind"),
                     "active_account_count": value["active_account_count"], "account_labels": sorted(names.get(key, []), key=str.lower)}
                    for key, value in sorted(known.items(), key=lambda item: item[1]["institution_label"].lower()) if key]
    return {"contract_version": CONTRACT, "status": "ready", "kinds": list(KINDS), "institutions": institutions,
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "KINDS", "STORE", "InstitutionMasterV1Error", "institution_master_v1_error_codes", "read_institution_master_v1",
    "record_institution_kinds_v1", "rename_institution_master_v1",
]
