"""Steuerangaben je Institut und Jahr: Freistellungsauftrag, anrechenbare Quellensteuer, Verlusttoepfe zum Jahresbeginn.

Der Freibetrag gilt je Institut (ohne Eintrag 0 Euro), nicht global fuer das Jahr. Kapitalertraege rechnet das Regelmodul deshalb je auszahlender Stelle (§ 43a Abs. 3,
§ 44a Abs. 2 EStG): mit deren Freistellungsauftrag, deren Verlusttoepfen und der dort anrechenbaren Quellensteuer.
Diese Angaben liegen hier - je Institut, so wie es an den Konten steht, und je Steuerjahr.

Die Verlusttoepfe zum Jahresbeginn traegt nur ein, wer einen Stand vorgeben will, etwa aus der Verlustbescheinigung
eines Instituts. Ohne Eintrag schreibt die Jahresrechnung den Stand aus dem Vorjahr fort.

Wie Kontonummer und Auszugsablage liegt der Speicher neben den Stammdaten, nicht in ihnen: Eine Steuerangabe soll
weder Buchungsbestand noch FIFO noch Bewertung beruehren. Er haengt nur an; der gueltige Stand je Institut, Jahr und
Angabe ist der juengste Eintrag, ein Eintrag ohne Betrag leert ihn. Ein Institut erkennt der Speicher an seinem Namen
ohne Leerraum und Gross-/Kleinschreibung - wie das Kontoformular. Kein Providerzugriff, kein Netzzugriff, kein
kanonischer Write.
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

AREA = "institution-tax-settings-v1"
STORE = "institution-tax-settings.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "institution_tax_settings_v1"
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
AMOUNT = re.compile(r"[0-9]{1,10}(\.[0-9]{1,2})?")
LABEL_LIMIT = 120
BATCH_LIMIT = 500
FIRST_YEAR = 2000
LAST_YEAR = 2100
# Die Angaben, die das Regelmodul im Jahresmodus je Institut liest - dieselben Kennungen wie dort.
FIELDS = (
    "capital_income_allowance",
    "creditable_foreign_withholding_tax",
    "opening_equity_loss_carryforward",
    "opening_general_capital_loss_carryforward",
)
FAILURE_CODES = (
    "institution_tax_settings_confirmation_required",
    "institution_tax_settings_input_invalid",
    "institution_tax_settings_institution_unknown",
    "institution_tax_settings_store_invalid",
)
SCHEMA = (
    "CREATE TABLE institution_tax_settings_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE institution_tax_settings_entry("
    "entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "institution_key TEXT NOT NULL CHECK(length(institution_key) <= 120),"
    "institution_label TEXT NOT NULL CHECK(length(institution_label) <= 120),"
    "tax_year INTEGER NOT NULL CHECK(tax_year BETWEEN 2000 AND 2100),"
    "field_code TEXT NOT NULL CHECK(field_code IN ('capital_income_allowance','creditable_foreign_withholding_tax',"
    "'opening_equity_loss_carryforward','opening_general_capital_loss_carryforward')),"
    "amount_decimal TEXT CHECK(amount_decimal IS NULL OR length(amount_decimal) BETWEEN 1 AND 13),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX institution_tax_settings_entry_key ON institution_tax_settings_entry(institution_key, tax_year, field_code, entry_id)",
    "CREATE TRIGGER institution_tax_settings_entry_no_update BEFORE UPDATE ON institution_tax_settings_entry "
    "BEGIN SELECT RAISE(ABORT, 'institution_tax_settings_entry_immutable'); END",
    "CREATE TRIGGER institution_tax_settings_entry_no_delete BEFORE DELETE ON institution_tax_settings_entry "
    "BEGIN SELECT RAISE(ABORT, 'institution_tax_settings_entry_immutable'); END",
    "CREATE VIEW current_institution_tax_settings AS SELECT entry.* FROM institution_tax_settings_entry entry "
    "WHERE entry.entry_id = (SELECT max(later.entry_id) FROM institution_tax_settings_entry later "
    "WHERE later.institution_key = entry.institution_key AND later.tax_year = entry.tax_year AND later.field_code = entry.field_code)",
)


class InstitutionTaxSettingsV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def institution_tax_settings_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise InstitutionTaxSettingsV1Error(code if code in FAILURE_CODES else "institution_tax_settings_store_invalid")


def institution_tax_settings_scope_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("institution_tax_settings_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("institution_tax_settings_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("institution_tax_settings_input_invalid")


def institution_key_v1(label) -> str:
    """Der Schluessel eines Instituts: sein Name ohne Leerraum, klein geschrieben - wie im Kontoformular. Leer heisst: ohne Institut."""
    if label is None:
        return ""
    if not isinstance(label, str):
        _abort("institution_tax_settings_input_invalid")
    return "".join(label.split()).lower()


def _label(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        _abort("institution_tax_settings_input_invalid")
    text = " ".join(value.split())
    if len(text) > LABEL_LIMIT:
        _abort("institution_tax_settings_input_invalid")
    return text


def _amount(value):
    """Ein Betrag in Euro, nicht negativ, hoechstens zwei Nachkommastellen; Komma oder Punkt. Leer heisst: kein Eintrag."""
    if value is None:
        return None
    if not isinstance(value, str):
        _abort("institution_tax_settings_input_invalid")
    text = value.strip().replace(",", ".")
    if not text:
        return None
    if AMOUNT.fullmatch(text) is None:
        _abort("institution_tax_settings_input_invalid")
    try:
        number = Decimal(text)
    except InvalidOperation:
        _abort("institution_tax_settings_input_invalid")
    # Kanonisch: ohne fuehrende Nullen und ohne Nullen am Ende der Nachkommastellen - 200,00 und 200 sind dieselbe Angabe.
    normalized = format(number.normalize(), "f")
    return normalized if "." not in normalized else normalized.rstrip("0").rstrip(".")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("institution_tax_settings_store_invalid")
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
                connection.execute("INSERT INTO institution_tax_settings_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("institution_tax_settings_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM institution_tax_settings_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("institution_tax_settings_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("institution_tax_settings_store_invalid")
    return connection


def known_institutions_v1(space, context) -> dict[str, dict]:
    """Die Institute der Stammdaten - je Schluessel Name und Zahl der aktiven Konten. Gelesen, nicht veraendert.

    Konten ohne Institutsangabe stehen unter dem leeren Schluessel.
    """
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("institution_tax_settings_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("institution_tax_settings_store_invalid")
            rows = connection.execute("SELECT institution_label,status FROM account ORDER BY account_id").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("institution_tax_settings_store_invalid")
        return {}
    known: dict[str, dict] = {}
    for label, status in rows:
        text = " ".join(label.split()) if isinstance(label, str) else ""
        entry = known.setdefault(institution_key_v1(text), {"institution_label": text, "active_account_count": 0, "account_count": 0})
        entry["account_count"] += 1
        if status != "archived":
            entry["active_account_count"] += 1
    return known


def account_institution_keys_v1(space, context_value) -> dict[str, str]:
    """Je Konto der Stammdaten der Schluessel seines Instituts - leer fuer Konten ohne Institutsangabe. Gelesen, nicht veraendert."""
    context = institution_tax_settings_scope_v1(context_value)
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("institution_tax_settings_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("institution_tax_settings_store_invalid")
            rows = connection.execute("SELECT account_id,institution_label FROM account ORDER BY account_id").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("institution_tax_settings_store_invalid")
        return {}
    return {account_id: institution_key_v1(" ".join(label.split()) if isinstance(label, str) else "") for account_id, label in rows}


def _current(connection) -> dict[tuple[str, int, str], dict]:
    rows = connection.execute(
        "SELECT institution_key,institution_label,tax_year,field_code,amount_decimal,recorded_at_utc FROM current_institution_tax_settings "
        "ORDER BY institution_key,tax_year,field_code").fetchall()
    return {(row["institution_key"], row["tax_year"], row["field_code"]): dict(row) for row in rows}


def _normalized(entries) -> list[dict]:
    if not isinstance(entries, (list, tuple)) or not 1 <= len(entries) <= BATCH_LIMIT:
        _abort("institution_tax_settings_input_invalid")
    result = []
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"institution_label", "tax_year", "field_code", "amount_decimal"}:
            _abort("institution_tax_settings_input_invalid")
        year = entry["tax_year"]
        if isinstance(year, bool) or not isinstance(year, int) or not FIRST_YEAR <= year <= LAST_YEAR or entry["field_code"] not in FIELDS:
            _abort("institution_tax_settings_input_invalid")
        label = _label(entry["institution_label"])
        result.append({"institution_key": institution_key_v1(label), "institution_label": label, "tax_year": year,
                       "field_code": entry["field_code"], "amount_decimal": _amount(entry["amount_decimal"])})
    if len({(entry["institution_key"], entry["tax_year"], entry["field_code"]) for entry in result}) != len(result):
        _abort("institution_tax_settings_input_invalid")
    return result


def _append(connection, current, wanted, recorded_at_utc) -> tuple[int, int]:
    written = unchanged = 0
    for entry in wanted:
        before = current.get((entry["institution_key"], entry["tax_year"], entry["field_code"]))
        if (before is None and entry["amount_decimal"] is None) or (
                before is not None and before["amount_decimal"] == entry["amount_decimal"]):
            unchanged += 1
            continue
        row = {**entry, "recorded_at_utc": recorded_at_utc}
        connection.execute(
            "INSERT INTO institution_tax_settings_entry(institution_key,institution_label,tax_year,field_code,amount_decimal,recorded_at_utc,"
            "entry_fingerprint) VALUES(?,?,?,?,?,?,?)",
            (row["institution_key"], row["institution_label"], row["tax_year"], row["field_code"], row["amount_decimal"],
             row["recorded_at_utc"], _fingerprint(row)))
        current[(entry["institution_key"], entry["tax_year"], entry["field_code"])] = row
        written += 1
    return written, unchanged


def _receipt(status: str, written: int, unchanged: int, **extra) -> dict:
    return {"contract_version": CONTRACT, "status": status, "written_count": written, "unchanged_count": unchanged, **extra,
            "provider_access": False, "network_access": False, "canonical_write": False}


def record_institution_tax_settings_v1(space, context_value, entries, recorded_at_utc, confirmed) -> dict:
    """Haengt je Institut, Jahr und Angabe den neuen Stand an. Unveraenderte Angaben schreiben nichts."""
    if confirmed is not True:
        _abort("institution_tax_settings_confirmation_required")
    context = institution_tax_settings_scope_v1(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("institution_tax_settings_input_invalid")
    wanted = _normalized(entries)
    known = known_institutions_v1(space, context)
    if any(entry["institution_key"] not in known for entry in wanted):
        _abort("institution_tax_settings_institution_unknown")
    # Gespeichert wird in der Schreibweise der Stammdaten.
    for entry in wanted:
        entry["institution_label"] = known[entry["institution_key"]]["institution_label"]
    connection = _connect(space, context, True)
    try:
        with connection:
            written, unchanged = _append(connection, _current(connection), wanted, recorded_at_utc)
    except sqlite3.Error:
        _abort("institution_tax_settings_store_invalid")
    finally:
        connection.close()
    return _receipt("recorded", written, unchanged)


def rename_institution_tax_settings_v1(space, context_value, old_label, new_label, recorded_at_utc, confirmed) -> dict:
    """Zieht die Angaben eines umbenannten Instituts unter den neuen Namen um.

    Gibt es den neuen Namen schon (zwei Institute werden eins), bleiben dessen Angaben stehen; nur was dort fehlt, kommt
    hinzu. Was nicht umziehen konnte, wird gezaehlt. Der alte Name verliert seine Angaben.
    """
    if confirmed is not True:
        _abort("institution_tax_settings_confirmation_required")
    context = institution_tax_settings_scope_v1(context_value)
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("institution_tax_settings_input_invalid")
    old_key = institution_key_v1(_label(old_label))
    new_text = _label(new_label)
    new_key = institution_key_v1(new_text)
    if not old_key or not new_key:
        _abort("institution_tax_settings_input_invalid")
    if old_key == new_key:
        return _receipt("unchanged", 0, 0, kept_count=0)
    connection = _connect(space, context, False)
    if connection is None:
        return _receipt("unchanged", 0, 0, kept_count=0)
    connection.close()
    connection = _connect(space, context, True)
    try:
        with connection:
            current = _current(connection)
            moving = [row for (key, _, _), row in current.items() if key == old_key and row["amount_decimal"] is not None]
            moved, kept = [], 0
            for row in moving:
                target = current.get((new_key, row["tax_year"], row["field_code"]))
                if target is not None and target["amount_decimal"] is not None:
                    kept += 1
                    continue
                moved.append({"institution_key": new_key, "institution_label": new_text, "tax_year": row["tax_year"],
                              "field_code": row["field_code"], "amount_decimal": row["amount_decimal"]})
            cleared = [{"institution_key": old_key, "institution_label": row["institution_label"], "tax_year": row["tax_year"],
                        "field_code": row["field_code"], "amount_decimal": None} for row in moving]
            written, _ = _append(connection, current, moved + cleared, recorded_at_utc)
    except sqlite3.Error:
        _abort("institution_tax_settings_store_invalid")
    finally:
        connection.close()
    return _receipt("renamed" if moving else "unchanged", written, 0, moved_count=len(moved), kept_count=kept)


def read_institution_tax_settings_v1(space, context_value) -> dict:
    """Gueltiger Stand je Institut, Jahr und Angabe, dazu die Institute der Stammdaten.

    Angaben zu einem Institut, das an keinem Konto mehr steht, werden mitgeliefert und als verwaist gekennzeichnet.
    """
    context = institution_tax_settings_scope_v1(context_value)
    known = known_institutions_v1(space, context)
    connection = _connect(space, context, False)
    current: dict = {}
    if connection is not None:
        try:
            current = _current(connection)
        except sqlite3.Error:
            _abort("institution_tax_settings_store_invalid")
        finally:
            connection.close()
    settings = [{"institution_key": key, "institution_label": known[key]["institution_label"] if key in known else row["institution_label"],
                 "tax_year": year, "field_code": field, "amount_decimal": row["amount_decimal"], "recorded_at_utc": row["recorded_at_utc"],
                 "orphaned": key not in known}
                for (key, year, field), row in sorted(current.items()) if row["amount_decimal"] is not None]
    institutions = [{"institution_key": key, **value} for key, value in sorted(known.items(), key=lambda item: (item[0] == "", item[1]["institution_label"].lower()))]
    return {"contract_version": CONTRACT, "status": "ready", "fields": list(FIELDS), "institutions": institutions, "settings": settings,
            "orphan_count": sum(1 for row in settings if row["orphaned"]),
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "FIELDS", "STORE", "InstitutionTaxSettingsV1Error", "account_institution_keys_v1", "institution_key_v1",
    "institution_tax_settings_scope_v1", "institution_tax_settings_v1_error_codes", "known_institutions_v1",
    "read_institution_tax_settings_v1", "record_institution_tax_settings_v1", "rename_institution_tax_settings_v1",
]
