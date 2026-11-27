"""Veranlagungsart je Steuerjahr (#498): einzeln oder zusammen - neben dem Steuerspeicher, nicht im Regelmodul.

Festlegung (21.10.2026): Der Freibetrag soll sich aendern lassen, wenn man verheiratet ist und gemeinsam veranlagt wird.
Die Veranlagungsart bestimmt den Sparer-Pauschbetrag (§ 20 Abs. 9 EStG: 1.000 Euro, bei Zusammenveranlagung 2.000 Euro; die
Werte je Jahr fuehrt das Modul). Sie ist hier gespeichert und nicht als Parameter des Moduls, weil ein neuer Parameter das
Modul selbst aendern wuerde - und jede Aenderung am Modul verlangt, es in "4. Steuer" neu zu uebernehmen. Die Anzeige und die
Pruefung der Freistellungsauftraege nutzen sie; die Jahresrechnung rechnet weiter mit den eingetragenen
Freistellungsauftraegen.

Seit rc.300 (#501, Festlegung 21.10.2026) dazu je Jahr, ob das Portfolio zur Veranlagung zaehlt. Ein Muster- oder
Fremdportfolio zaehlt nicht: Jahresrechnung und Netto-Sicht rechnen dann keine Steuer und sagen das. Ohne Angabe zaehlt es.
Die Tabelle kam mit rc.300 hinzu; ein aelterer Speicher erhaelt sie beim ersten Schreiben (nur ergaenzt, nichts geaendert).

Nur anhaengend; je Jahr gilt der juengste Eintrag. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sqlite3

STORE = "tax-assessment.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "tax_assessment_v1"
ASSESSMENTS = ("single", "joint")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
FAILURE_CODES = ("tax_assessment_confirmation_required", "tax_assessment_input_invalid", "tax_assessment_store_invalid")
SCHEMA = (
    "CREATE TABLE tax_assessment_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL"
    " CHECK(schema_version = 1), tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE assessment_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, tax_year INTEGER NOT NULL CHECK(tax_year BETWEEN 1900 AND 9999),"
    " assessment TEXT NOT NULL CHECK(assessment IN ('single','joint')), recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    *(f"CREATE TRIGGER assessment_entry_no_{action} BEFORE {action.upper()} ON assessment_entry BEGIN SELECT RAISE(ABORT, 'assessment_entry_immutable'); END"
      for action in ("update", "delete")),
    "CREATE VIEW current_assessment AS SELECT entry.* FROM assessment_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM assessment_entry later WHERE later.tax_year = entry.tax_year)",
)
# Seit rc.300 (#501): ob das Portfolio im Jahr zur Veranlagung zaehlt.
SCOPE_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS portfolio_scope_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, tax_year INTEGER NOT NULL"
    " CHECK(tax_year BETWEEN 1900 AND 9999), counts INTEGER NOT NULL CHECK(counts IN (0,1)), recorded_at_utc TEXT NOT NULL,"
    " entry_fingerprint TEXT NOT NULL) STRICT",
    *(f"CREATE TRIGGER IF NOT EXISTS portfolio_scope_entry_no_{action} BEFORE {action.upper()} ON portfolio_scope_entry BEGIN "
      f"SELECT RAISE(ABORT, 'portfolio_scope_entry_immutable'); END" for action in ("update", "delete")),
    "CREATE VIEW IF NOT EXISTS current_portfolio_scope AS SELECT entry.* FROM portfolio_scope_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM portfolio_scope_entry later WHERE later.tax_year = entry.tax_year)",
)


class TaxAssessmentV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise TaxAssessmentV1Error(code if code in FAILURE_CODES else "tax_assessment_store_invalid")


def _binding(ctx) -> tuple[int, str, str, str]:
    values = (getattr(ctx, "tenant_id", None), getattr(ctx, "user_id", None), getattr(ctx, "data_space_id", None))
    if not all(isinstance(value, str) and value for value in values):
        _abort("tax_assessment_input_invalid")
    return (SCHEMA_VERSION, *values)


def _connect(tax_ui_dir, ctx, create: bool):
    root = Path(tax_ui_dir)
    store = root / STORE
    if root.is_symlink() or store.is_symlink() or not root.is_dir():
        _abort("tax_assessment_store_invalid")
    expected = _binding(ctx)
    if not store.exists():
        if not create:
            return None
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in (*SCHEMA, *SCOPE_SCHEMA):
                    connection.execute(statement)
                connection.execute("INSERT INTO tax_assessment_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("tax_assessment_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM tax_assessment_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("tax_assessment_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("tax_assessment_store_invalid")
    if create:
        try:
            with connection:
                for statement in SCOPE_SCHEMA:
                    connection.execute(statement)
        except sqlite3.Error:
            connection.close()
            _abort("tax_assessment_store_invalid")
    return connection


def read_tax_assessments_v1(tax_ui_dir, ctx) -> dict[int, str]:
    """Je Steuerjahr die gueltige Veranlagungsart; leer ohne Speicher."""
    connection = _connect(tax_ui_dir, ctx, False)
    if connection is None:
        return {}
    try:
        return {int(row["tax_year"]): row["assessment"] for row in connection.execute("SELECT tax_year, assessment FROM current_assessment")}
    except sqlite3.Error:
        _abort("tax_assessment_store_invalid")
        return {}
    finally:
        connection.close()


def record_tax_assessment_v1(tax_ui_dir, ctx, tax_year, assessment, recorded_at_utc, confirmed) -> dict:
    """Haengt die Veranlagungsart eines Jahres an; unveraendert schreibt nichts."""
    if confirmed is not True:
        _abort("tax_assessment_confirmation_required")
    if isinstance(tax_year, bool) or not isinstance(tax_year, int) or not 1900 <= tax_year <= 9999 or assessment not in ASSESSMENTS:
        _abort("tax_assessment_input_invalid")
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("tax_assessment_input_invalid")
    connection = _connect(tax_ui_dir, ctx, True)
    try:
        with connection:
            current = connection.execute("SELECT assessment FROM current_assessment WHERE tax_year=?", (tax_year,)).fetchone()
            if current is not None and current["assessment"] == assessment:
                return {"contract_version": CONTRACT, "status": "unchanged", "canonical_write": False}
            body = {"tax_year": tax_year, "assessment": assessment, "recorded_at_utc": recorded_at_utc}
            fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            connection.execute("INSERT INTO assessment_entry(tax_year,assessment,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                               (tax_year, assessment, recorded_at_utc, fingerprint))
    except sqlite3.Error:
        _abort("tax_assessment_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "canonical_write": False}


def read_tax_portfolio_scope_v1(tax_ui_dir, ctx) -> dict[int, bool]:
    """Je Steuerjahr, ob das Portfolio zur Veranlagung zaehlt - nur Jahre mit Angabe; ohne Angabe zaehlt es."""
    connection = _connect(tax_ui_dir, ctx, False)
    if connection is None:
        return {}
    try:
        if connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='portfolio_scope_entry'").fetchone()[0] != 1:
            return {}
        return {int(row["tax_year"]): bool(row["counts"]) for row in connection.execute("SELECT tax_year, counts FROM current_portfolio_scope")}
    except sqlite3.Error:
        _abort("tax_assessment_store_invalid")
        return {}
    finally:
        connection.close()


def not_assessed_years_v1(tax_ui_dir, ctx) -> set[int]:
    """Die Jahre, in denen das Portfolio nicht zur Veranlagung zaehlt; ohne Speicher keine."""
    try:
        return {year for year, counts in read_tax_portfolio_scope_v1(tax_ui_dir, ctx).items() if not counts}
    except TaxAssessmentV1Error:
        return set()


def record_tax_portfolio_scope_v1(tax_ui_dir, ctx, tax_year, counts, recorded_at_utc, confirmed) -> dict:
    """Haengt an, ob das Portfolio im Jahr zur Veranlagung zaehlt; unveraendert schreibt nichts."""
    if confirmed is not True:
        _abort("tax_assessment_confirmation_required")
    if isinstance(tax_year, bool) or not isinstance(tax_year, int) or not 1900 <= tax_year <= 9999 or not isinstance(counts, bool):
        _abort("tax_assessment_input_invalid")
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("tax_assessment_input_invalid")
    connection = _connect(tax_ui_dir, ctx, True)
    try:
        with connection:
            current = connection.execute("SELECT counts FROM current_portfolio_scope WHERE tax_year=?", (tax_year,)).fetchone()
            if (current is None and counts) or (current is not None and bool(current["counts"]) == counts):
                return {"contract_version": CONTRACT, "status": "unchanged", "canonical_write": False}
            body = {"tax_year": tax_year, "counts": counts, "recorded_at_utc": recorded_at_utc}
            fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            connection.execute("INSERT INTO portfolio_scope_entry(tax_year,counts,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                               (tax_year, int(counts), recorded_at_utc, fingerprint))
    except sqlite3.Error:
        _abort("tax_assessment_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "canonical_write": False}


__all__ = ["ASSESSMENTS", "FAILURE_CODES", "STORE", "TaxAssessmentV1Error", "not_assessed_years_v1", "read_tax_assessments_v1",
           "read_tax_portfolio_scope_v1", "record_tax_assessment_v1", "record_tax_portfolio_scope_v1"]
