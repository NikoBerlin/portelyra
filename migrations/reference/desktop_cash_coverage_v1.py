"""Owner-only immutable Cash Coverage commands and review handoff.

The schema-2901 point revision belongs to the schema-2900 Cash authority family. It
keeps every prior fact row immutable, adds explicit fact supersession/void lineage,
and gives manual and reviewed-import input the same Preview -> one-use Confirmation
-> Apply boundary. Recovery always requires a distinct one-use authority.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from typing import Any, Mapping
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from migrations.reference.cash_coverage_v1 import CashCoverageV1Error, validate_cash_coverage_v1
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _canonical_snapshot,
    _context,
    _context_fingerprint,
    _owner_directory,
    _owner_file,
    _sha_file,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "contracts" / "cash-coverage" / "v1" / "schema.sql"
SCHEMA_VERSION = 2901
STORE_AREA = "cash-coverage-v1"
STORE_NAME = "cash-coverage.sqlite"
LOCK_NAME = "writer.lock"
CANONICAL_LOCK_NAME = "canonical.writer.lock"
CONTRACT_VERSION = "desktop_cash_coverage_v1"
REGULAR_ACTIONS = frozenset({"declare_coverage", "record_cash_event", "record_interest_income", "record_reconciliation"})
REVISION_ACTIONS = frozenset({"correct", "supersede", "void"})
ACTION_TYPES = REGULAR_ACTIONS | REVISION_ACTIONS
INPUT_MODES = frozenset({"manual_entry", "reviewed_import"})
COVERAGE_MODES = frozenset({"not_tracked", "income_only", "partial", "complete_reconciled"})
EVENT_TYPES = frozenset({"opening_balance", "deposit", "withdrawal", "transfer"})
FLOW_CLASSIFICATIONS = frozenset({"not_applicable", "unclassified", "external_contribution", "external_withdrawal", "internal_unlinked", "investment_settlement", "income_receipt", "fee_or_tax_payment"})
FACT_TABLES = {
    "coverage_period": ("cash_coverage_period", "coverage_id"),
    "cash_event": ("cash_coverage_event", "cash_event_id"),
    "income_event": ("cash_income_event", "income_event_id"),
    "reconciliation": ("cash_coverage_reconciliation", "reconciliation_id"),
}
REQUEST = re.compile(r"^ccrq_[a-f0-9]{32}$")
CONFIRMATION = re.compile(r"^cccf_[a-f0-9]{32}$")
RECOVERY_CONFIRMATION = re.compile(r"^ccrc_[a-f0-9]{32}$")
RECOVERY_REF = re.compile(r"^cash_recovery_[a-f0-9]{32}$")
RECORD_REF = re.compile(r"^cash_record_[a-f0-9]{32}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
LOCAL_TIME = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$")
ZONE = re.compile(r"^[A-Za-z0-9._+/-]{1,80}$")
DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
POSITIVE_DECIMAL = re.compile(r"^(?:[1-9][0-9]*(?:\.[0-9]*[1-9])?|0\.[0-9]*[1-9])$")
FAILPOINTS = frozenset({None, "after_attempt", "after_receipt", "after_fact", "after_commit"})
# Nachweisarten einer Abstimmung, die keine Belegdatei tragen (#417, #419). Der
# Von Hand tippt niemand einen SHA-256-Code ein. Statt eines Ersatzhashs wird der Abdruck aus den
# Feldern der Abstimmung selbst gebildet - damit laesst sich die Art aus dem
# gespeicherten Fakt nachrechnen, ohne neue Spalte und ohne zweite Ablage.
#
#   owner_sighted                   - Saldo vom Eigentuemer online gesichtet;
#                                     ein zweiter Beleg, nur aus anderer Quelle
#   owner_asserted_without_balance  - Vollstaendigkeit erklaert, ohne dass ein
#                                     Saldo zu bekommen war; der gespeicherte
#                                     Saldo ist dann der errechnete
#
# Jeder andere Abdruck gilt als "document": Belegdatei oder Importnachweis.
EVIDENCE_KINDS = ("owner_sighted", "owner_asserted_without_balance")

FAILURE_CODES = frozenset({
    "desktop_cash_coverage_input_invalid", "desktop_cash_coverage_context_invalid",
    "desktop_cash_coverage_canonical_invalid", "desktop_cash_coverage_canonical_changed",
    "desktop_cash_coverage_store_invalid", "desktop_cash_coverage_store_exists",
    "desktop_cash_coverage_store_upgrade_required", "desktop_cash_coverage_lock_unavailable",
    "desktop_cash_coverage_catalog_invalid", "desktop_cash_coverage_period_overlap",
    "desktop_cash_coverage_mode_invalid", "desktop_cash_coverage_event_outside_period",
    "desktop_cash_coverage_reconciliation_mismatch", "desktop_cash_coverage_preview_stale",
    "desktop_cash_coverage_confirmation_missing", "desktop_cash_coverage_confirmation_invalid",
    "desktop_cash_coverage_confirmation_expired", "desktop_cash_coverage_confirmation_consumed",
    "desktop_cash_coverage_command_conflict", "desktop_cash_coverage_predecessor_missing",
    "desktop_cash_coverage_predecessor_conflict", "desktop_cash_coverage_revision_invalid",
    "desktop_cash_coverage_receipt_invalid", "desktop_cash_coverage_recovery_missing",
    "desktop_cash_coverage_recovery_invalid", "desktop_cash_coverage_recovery_stale",
    "desktop_cash_coverage_recovery_confirmation_consumed", "desktop_cash_coverage_write_failed",
    "desktop_cash_coverage_migration_source_invalid", "desktop_cash_coverage_migration_source_changed",
    "desktop_cash_coverage_migration_target_exists", "desktop_cash_coverage_migration_confirmation_invalid",
    "desktop_cash_coverage_migration_confirmation_consumed", "desktop_cash_coverage_migration_failed",
    "desktop_cash_coverage_migration_recovery_invalid", "desktop_cash_coverage_migration_recovery_missing",
    "desktop_cash_coverage_migration_recovery_stale",
    "desktop_cash_coverage_migration_recovery_confirmation_invalid",
    "desktop_cash_coverage_migration_recovery_confirmation_consumed",
    "synthetic_desktop_cash_coverage_failpoint", "desktop_cash_coverage_boundary_failed",
})


class DesktopCashCoverageV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("desktop_cash_coverage_error_code_unregistered")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DesktopCashCoverageResultV1:
    status: str
    action_type: str
    operation_type: str
    command_ref: str
    receipt_ref: str
    schema_version: int
    period_count: int
    cash_event_count: int
    income_event_count: int
    reconciliation_count: int
    revision_count: int
    predecessor_preserved: bool
    input_mode: str
    canonical_write: bool = False
    asset_activity_write: bool = False
    provider_access: bool = False
    network_access: bool = False


def desktop_cash_coverage_error_codes_v1() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise DesktopCashCoverageV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except Exception:
        _abort("desktop_cash_coverage_input_invalid")


def _sha(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _recovery_ref(confirmation_fingerprint: str) -> str:
    return "cash_recovery_" + _sha({"cash_coverage_recovery": confirmation_fingerprint})[:32]


def _utc(value: Any, code: str = "desktop_cash_coverage_input_invalid") -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort(code)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _abort(code)
    return value


def _date(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _abort("desktop_cash_coverage_input_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _abort("desktop_cash_coverage_input_invalid")
    if parsed.isoformat() != value:
        _abort("desktop_cash_coverage_input_invalid")
    return value


def _decimal(value: Any, *, positive: bool = False) -> str:
    pattern = POSITIVE_DECIMAL if positive else DECIMAL
    if not isinstance(value, str) or len(value) > 80 or pattern.fullmatch(value) is None or value == "-0":
        _abort("desktop_cash_coverage_input_invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _abort("desktop_cash_coverage_input_invalid")
    if not parsed.is_finite() or positive and parsed <= 0:
        _abort("desktop_cash_coverage_input_invalid")
    return value


def _fingerprint(value: Any, code: str = "desktop_cash_coverage_input_invalid") -> str:
    if not isinstance(value, str) or SHA.fullmatch(value) is None:
        _abort(code)
    return value


def desktop_cash_evidence_fingerprint_v1(
    kind: Any, portfolio_id: Any, account_id: Any, cash_asset_id: Any, as_of_date: Any, observed_balance_decimal: Any,
) -> str:
    """Abdruck eines Nachweises ohne Belegdatei, gebildet aus der Abstimmung selbst."""
    if kind not in EVIDENCE_KINDS or not all(isinstance(item, str) and item for item in (portfolio_id, account_id, cash_asset_id)):
        _abort("desktop_cash_coverage_input_invalid")
    return _sha({
        "desktop_cash_evidence_version": 1, "evidence_kind": kind, "portfolio_id": portfolio_id,
        "account_id": account_id, "cash_asset_id": cash_asset_id, "as_of_date": _date(as_of_date),
        "observed_balance_decimal": _decimal(observed_balance_decimal),
    })


def desktop_cash_evidence_kind_v1(reconciliation: Mapping[str, Any]) -> str:
    """Die Nachweisart einer gespeicherten Abstimmung, nachgerechnet aus ihren Feldern."""
    for kind in EVIDENCE_KINDS:
        if reconciliation["evidence_fingerprint"] == desktop_cash_evidence_fingerprint_v1(
            kind, reconciliation["portfolio_id"], reconciliation["account_id"], reconciliation["cash_asset_id"],
            reconciliation["as_of_date"], reconciliation["observed_balance_decimal"],
        ):
            return kind
    return "document"


def _strict(value: Any, keys: set[str], code: str = "desktop_cash_coverage_input_invalid") -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        _abort(code)
    return dict(value)


def _exact_local_time(local_date: str, local_time: Any, time_zone: Any, effective_at_utc: Any) -> tuple[str, str, str, str]:
    local_date = _date(local_date)  # type: ignore[assignment]
    effective = _utc(effective_at_utc)
    if not isinstance(local_time, str) or LOCAL_TIME.fullmatch(local_time) is None or not isinstance(time_zone, str) or ZONE.fullmatch(time_zone) is None:
        _abort("desktop_cash_coverage_input_invalid")
    try:
        zone = ZoneInfo(time_zone)
        naive = datetime.strptime(f"{local_date}T{local_time}", "%Y-%m-%dT%H:%M:%S")
    except (ValueError, ZoneInfoNotFoundError):
        _abort("desktop_cash_coverage_input_invalid")
    candidates: set[str] = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        utc_value = aware.astimezone(timezone.utc)
        if utc_value.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc_value.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if effective not in candidates:
        _abort("desktop_cash_coverage_input_invalid")
    return local_date, local_time, time_zone, effective


def _schema_signature(connection: sqlite3.Connection) -> tuple[tuple[Any, ...], ...]:
    return tuple(tuple(row) for row in connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type,name"
    ))


_EXPECTED_SCHEMA: tuple[tuple[Any, ...], ...] | None = None


def _expected_schema() -> tuple[tuple[Any, ...], ...]:
    global _EXPECTED_SCHEMA
    if _EXPECTED_SCHEMA is None:
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            _EXPECTED_SCHEMA = _schema_signature(connection)
        except (OSError, sqlite3.Error):
            _abort("desktop_cash_coverage_store_invalid")
        finally:
            connection.close()
    return _EXPECTED_SCHEMA


def _store_path(data_space: Path) -> Path:
    return data_space / STORE_AREA / STORE_NAME


def _store_uri(path: Path, mode: str, immutable: bool = False) -> str:
    return f"file:{quote(str(path))}?mode={mode}{'&immutable=1' if immutable else ''}"


def _rows_as_dicts(connection: sqlite3.Connection, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(sql, parameters).fetchall()]


def _legacy_fact_projection(connection: sqlite3.Connection, command_ids: set[str]) -> dict[str, Any]:
    if not command_ids:
        return {"periods": [], "cash_events": [], "income_events": [], "reconciliations": []}
    placeholders = ",".join("?" for _ in command_ids)
    parameters = tuple(sorted(command_ids))
    return {
        "periods": _rows_as_dicts(connection, f"SELECT * FROM cash_coverage_period WHERE command_id IN ({placeholders}) ORDER BY coverage_id", parameters),
        "cash_events": _rows_as_dicts(connection, f"SELECT * FROM cash_coverage_event WHERE command_id IN ({placeholders}) ORDER BY cash_event_id", parameters),
        "income_events": _rows_as_dicts(connection, f"SELECT * FROM cash_income_event WHERE command_id IN ({placeholders}) ORDER BY income_event_id", parameters),
        "reconciliations": _rows_as_dicts(connection, f"SELECT * FROM cash_coverage_reconciliation WHERE command_id IN ({placeholders}) ORDER BY reconciliation_id", parameters),
    }


def _validate_migration_state(connection: sqlite3.Connection) -> None:
    missing_attempts = _rows_as_dicts(connection,
        "SELECT attempt.* FROM cash_coverage_confirmation_attempt attempt LEFT JOIN cash_coverage_attempt_evidence evidence USING(confirmation_fingerprint) WHERE evidence.confirmation_fingerprint IS NULL ORDER BY attempt.confirmation_fingerprint"
    )
    missing_commands = _rows_as_dicts(connection,
        "SELECT receipt.* FROM cash_coverage_command_receipt receipt LEFT JOIN cash_coverage_command_provenance provenance USING(command_id) WHERE provenance.command_id IS NULL ORDER BY receipt.command_id"
    )
    migrations = connection.execute("SELECT * FROM cash_coverage_schema_migration_receipt").fetchall()
    migration_recoveries = connection.execute(
        "SELECT * FROM cash_coverage_schema_migration_recovery_attempt ORDER BY recovery_confirmation_fingerprint"
    ).fetchall()
    if not migrations:
        if missing_attempts or missing_commands or migration_recoveries:
            _abort("desktop_cash_coverage_store_invalid")
        return
    if len(migrations) != 1:
        _abort("desktop_cash_coverage_store_invalid")
    migration = migrations[0]
    migration_body = {key: migration[key] for key in migration.keys() if key != "receipt_fingerprint"}
    expected_recovery_fingerprint = migration["recovery_confirmation_fingerprint"]
    if (
        migration["receipt_fingerprint"] != _sha(migration_body)
        or (expected_recovery_fingerprint is None and migration_recoveries)
        or (expected_recovery_fingerprint is not None and (
            len(migration_recoveries) != 1
            or migration_recoveries[0]["recovery_confirmation_fingerprint"] != expected_recovery_fingerprint
            or migration_recoveries[0]["original_confirmation_fingerprint"] != migration["confirmation_fingerprint"]
            or migration_recoveries[0]["migration_plan_fingerprint"] != migration["migration_plan_fingerprint"]
        ))
    ):
        _abort("desktop_cash_coverage_store_invalid")
    command_ids = {row["command_id"] for row in missing_commands}
    facts = _legacy_fact_projection(connection, command_ids)
    counts = tuple(len(facts[key]) for key in ("periods", "cash_events", "income_events", "reconciliations"))
    if (
        migration["legacy_attempt_set_fingerprint"] != _sha(missing_attempts)
        or migration["legacy_command_set_fingerprint"] != _sha(missing_commands)
        or migration["target_fact_projection_fingerprint"] != _sha(facts)
        or counts != tuple(migration[key] for key in ("period_count", "cash_event_count", "income_event_count", "reconciliation_count"))
    ):
        _abort("desktop_cash_coverage_store_invalid")


def _validate_provenance(connection: sqlite3.Connection) -> None:
    for provenance in connection.execute("SELECT * FROM cash_coverage_command_provenance ORDER BY command_id"):
        body = {key: provenance[key] for key in provenance.keys() if key != "receipt_fingerprint"}
        if provenance["receipt_fingerprint"] != _sha(body):
            _abort("desktop_cash_coverage_store_invalid")
        receipt = connection.execute(
            "SELECT action_type FROM cash_coverage_command_receipt WHERE command_id=?", (provenance["command_id"],)
        ).fetchone()
        lineages = connection.execute(
            "SELECT predecessor_kind,predecessor_fact_id FROM cash_coverage_fact_supersession WHERE command_id=?",
            (provenance["command_id"],),
        ).fetchall()
        if provenance["operation_type"] == "create":
            if receipt is None or receipt[0] == "revise_cash_coverage" or lineages:
                _abort("desktop_cash_coverage_store_invalid")
            continue
        predecessor_commands: set[str] = set()
        for lineage in lineages:
            table, identifier = FACT_TABLES[lineage["predecessor_kind"]]
            row = connection.execute(
                f"SELECT command_id FROM {table} WHERE {identifier}=?", (lineage["predecessor_fact_id"],)
            ).fetchone()
            if row is None:
                _abort("desktop_cash_coverage_store_invalid")
            predecessor_commands.add(row[0])
        if (
            receipt is None or receipt[0] != "revise_cash_coverage" or not predecessor_commands
            or provenance["predecessor_set_fingerprint"] != _sha(sorted(predecessor_commands))
            or provenance["predecessor_command_id"] != (next(iter(predecessor_commands)) if len(predecessor_commands) == 1 else None)
        ):
            _abort("desktop_cash_coverage_store_invalid")


def _validate_store(connection: sqlite3.Connection, context: DesktopProductAssetActivityContextV1) -> None:
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 2900:
            _abort("desktop_cash_coverage_store_upgrade_required")
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM cash_coverage_store_binding WHERE singleton_id=1"
        ).fetchall()
        if (
            version != SCHEMA_VERSION or _schema_signature(connection) != _expected_schema() or len(binding) != 1
            or tuple(binding[0]) != (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
            or connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _abort("desktop_cash_coverage_store_invalid")
        _validate_supersession_lineage(connection)
        _validate_migration_state(connection)
        _validate_provenance(connection)
    except DesktopCashCoverageV1Error:
        raise
    except sqlite3.Error:
        _abort("desktop_cash_coverage_store_invalid")


def _open_store(path: Path, context: DesktopProductAssetActivityContextV1, *, read_only: bool) -> sqlite3.Connection:
    store = _owner_file(path, "desktop_cash_coverage_store_invalid")
    if any(Path(str(store) + suffix).exists() for suffix in ("-journal", "-wal", "-shm")):
        _abort("desktop_cash_coverage_store_invalid")
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(_store_uri(store, "ro" if read_only else "rw", immutable=read_only), uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=0")
        if read_only:
            connection.execute("PRAGMA query_only=ON")
        _validate_store(connection, context)
        return connection
    except DesktopCashCoverageV1Error:
        if connection is not None:
            connection.close()
        raise
    except sqlite3.Error:
        if connection is not None:
            connection.close()
        _abort("desktop_cash_coverage_store_invalid")


def _create_store(path: Path, context: DesktopProductAssetActivityContextV1, created_at_utc: str) -> None:
    area = _owner_directory(path.parent, create=True)
    if path.exists() or path.is_symlink():
        _abort("desktop_cash_coverage_store_exists")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=area)
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        previous = os.umask(0o077)
        try:
            connection = sqlite3.connect(temporary)
        finally:
            os.umask(previous)
        try:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=FULL")
            connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO cash_coverage_store_binding VALUES(1,?,?,?,?,?)",
                (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id, created_at_utc),
            )
            connection.commit()
            _validate_store(connection, context)
        finally:
            connection.close()
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            _abort("desktop_cash_coverage_store_exists")
        os.chmod(path, 0o600)
        directory = os.open(area, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except DesktopCashCoverageV1Error:
        raise
    except Exception:
        _abort("desktop_cash_coverage_write_failed")
    finally:
        temporary.unlink(missing_ok=True)


class _WriterLock:
    def __init__(self, area: Path):
        self.area = _owner_directory(area, create=True)
        self.descriptor: int | None = None

    def __enter__(self) -> "_WriterLock":
        path = self.area / LOCK_NAME
        try:
            self.descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            metadata = os.fstat(self.descriptor)
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.geteuid():
                _abort("desktop_cash_coverage_store_invalid")
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self
        except BlockingIOError:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            _abort("desktop_cash_coverage_lock_unavailable")
        except DesktopCashCoverageV1Error:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            raise
        except OSError:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            _abort("desktop_cash_coverage_store_invalid")

    def __exit__(self, *_: object) -> None:
        if self.descriptor is not None:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            os.close(self.descriptor)
            self.descriptor = None


class _CanonicalBarrier:
    def __init__(self, data_space: Path):
        self.path = data_space / CANONICAL_LOCK_NAME
        self.held = False

    def __enter__(self) -> "_CanonicalBarrier":
        if self.path.is_symlink():
            _abort("desktop_cash_coverage_canonical_invalid")
        try:
            os.mkdir(self.path, 0o700)
            os.chmod(self.path, 0o700)
            self.held = True
        except FileExistsError:
            _abort("desktop_cash_coverage_lock_unavailable")
        except OSError:
            _abort("desktop_cash_coverage_store_invalid")
        return self

    def __exit__(self, *_: object) -> None:
        if self.held:
            try:
                os.rmdir(self.path)
            except OSError:
                _abort("desktop_cash_coverage_store_invalid")
            self.held = False


def _catalog(canonical_path: str | Path, context_value: Any) -> tuple[DesktopProductAssetActivityContextV1, dict[str, Any], dict[str, Any]]:
    try:
        context = _context(context_value)
        snapshot = _canonical_snapshot(canonical_path, context)
    except DesktopProductAssetActivityV1Error as error:
        if error.code == "desktop_asset_activity_context_invalid":
            _abort("desktop_cash_coverage_context_invalid")
        _abort("desktop_cash_coverage_canonical_invalid")
    portfolios = {row["portfolio_id"]: row for row in snapshot["portfolios"] if row["status"] == "active"}
    accounts = {row["account_id"]: row for row in snapshot["accounts"] if row["status"] == "active" and row["account_type"] in {"cash", "bank", "securities", "other"}}
    assets = {row["asset_id"]: row for row in snapshot["assets"] if row["status"] == "active" and row["asset_type"] == "cash" and row["valuation_method"] == "unit_value" and re.fullmatch(r"[A-Z]{3}", row["price_currency"] or "")}
    if not portfolios or not accounts or not assets:
        _abort("desktop_cash_coverage_catalog_invalid")
    return context, snapshot, {"portfolios": portfolios, "accounts": accounts, "assets": assets}


def read_desktop_cash_coverage_catalog_v1(canonical_path: str | Path, context_value: Any) -> dict[str, Any]:
    _, _, catalog = _catalog(canonical_path, context_value)
    return {
        "cash_coverage_catalog_version": 1, "status": "ready",
        "portfolios": [{"portfolio_id": row["portfolio_id"], "label": row["display_name"], "base_currency": row["base_currency"]} for row in catalog["portfolios"].values()],
        "accounts": [{"account_id": row["account_id"], "portfolio_id": row["portfolio_id"], "label": row["display_name"], "account_type": row["account_type"]} for row in catalog["accounts"].values()],
        "cash_assets": [{"asset_id": row["asset_id"], "label": row["display_name"], "currency": row["price_currency"]} for row in catalog["assets"].values()],
        "canonical_ids_exposed": True, "path_exposed": False, "canonical_write": False,
        "provider_access": False, "network_access": False,
    }


def _scope(command: Mapping[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    portfolio_id = command.get("portfolio_id")
    account_id = command.get("account_id")
    cash_asset_id = command.get("cash_asset_id")
    if not all(isinstance(value, str) for value in (portfolio_id, account_id, cash_asset_id)):
        _abort("desktop_cash_coverage_input_invalid")
    portfolio = catalog["portfolios"].get(portfolio_id)
    account = catalog["accounts"].get(account_id)
    asset = catalog["assets"].get(cash_asset_id)
    if portfolio is None or account is None or asset is None or account["portfolio_id"] != portfolio_id:
        _abort("desktop_cash_coverage_catalog_invalid")
    return {"portfolio_id": portfolio_id, "account_id": account_id, "cash_asset_id": cash_asset_id, "currency": asset["price_currency"]}


def _metadata(value: Mapping[str, Any]) -> tuple[str, str | None]:
    mode = value.get("input_mode")
    source = value.get("source_candidate_fingerprint")
    if mode not in INPUT_MODES:
        _abort("desktop_cash_coverage_input_invalid")
    if mode == "manual_entry":
        if source is not None:
            _abort("desktop_cash_coverage_input_invalid")
    else:
        source = _fingerprint(source)
    return mode, source


def _regular_fields(action: str, *, nested: bool) -> set[str]:
    common = {"action_type", "portfolio_id", "account_id", "cash_asset_id"}
    if not nested:
        common |= {"request_ref", "input_mode", "source_candidate_fingerprint"}
    return {
        "declare_coverage": common | {"effective_from", "effective_to", "coverage_mode", "opening_balance_decimal", "opening_event_time_evidence", "opening_local_time", "opening_time_zone", "opening_effective_at_utc", "reconciliation_as_of_date", "observed_balance_decimal", "evidence_fingerprint"},
        "record_cash_event": common | {"event_type", "related_account_id", "event_time_evidence", "local_date", "local_time", "time_zone", "effective_at_utc", "amount_decimal", "flow_classification"},
        "record_interest_income": common | {"local_date", "gross_income_decimal", "linked_cash_event_ref"},
        "record_reconciliation": common | {"as_of_date", "observed_balance_decimal", "evidence_fingerprint"},
    }[action]


def _regular_command(value: Any, catalog: dict[str, Any], *, nested: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("action_type") not in REGULAR_ACTIONS:
        _abort("desktop_cash_coverage_input_invalid")
    action = value["action_type"]
    result = _strict(value, _regular_fields(action, nested=nested))
    result.update(_scope(result, catalog))
    if action == "declare_coverage":
        result["effective_from"] = _date(result["effective_from"])
        result["effective_to"] = _date(result["effective_to"], nullable=True)
        if result["coverage_mode"] not in COVERAGE_MODES or result["effective_to"] is not None and result["effective_to"] < result["effective_from"]:
            _abort("desktop_cash_coverage_mode_invalid")
        complete = result["coverage_mode"] == "complete_reconciled"
        if complete:
            result["opening_balance_decimal"] = _decimal(result["opening_balance_decimal"])
            if result["opening_event_time_evidence"] != "exact_local_zone":
                _abort("desktop_cash_coverage_input_invalid")
            _, result["opening_local_time"], result["opening_time_zone"], result["opening_effective_at_utc"] = _exact_local_time(
                result["effective_from"], result["opening_local_time"], result["opening_time_zone"], result["opening_effective_at_utc"]
            )
            result["reconciliation_as_of_date"] = _date(result["reconciliation_as_of_date"])
            result["observed_balance_decimal"] = _decimal(result["observed_balance_decimal"])
            result["evidence_fingerprint"] = _fingerprint(result["evidence_fingerprint"])
            if result["reconciliation_as_of_date"] < result["effective_from"] or result["effective_to"] is not None and result["reconciliation_as_of_date"] != result["effective_to"]:
                _abort("desktop_cash_coverage_input_invalid")
        elif any(result[field] is not None for field in ("opening_balance_decimal", "opening_event_time_evidence", "opening_local_time", "opening_time_zone", "opening_effective_at_utc", "reconciliation_as_of_date", "observed_balance_decimal", "evidence_fingerprint")):
            _abort("desktop_cash_coverage_input_invalid")
    elif action == "record_cash_event":
        if result["event_time_evidence"] != "exact_local_zone":
            _abort("desktop_cash_coverage_input_invalid")
        result["local_date"], result["local_time"], result["time_zone"], result["effective_at_utc"] = _exact_local_time(
            result["local_date"], result["local_time"], result["time_zone"], result["effective_at_utc"]
        )
        if result["event_type"] not in EVENT_TYPES or result["flow_classification"] not in FLOW_CLASSIFICATIONS:
            _abort("desktop_cash_coverage_input_invalid")
        result["amount_decimal"] = _decimal(result["amount_decimal"], positive=result["event_type"] != "opening_balance")
        related = result["related_account_id"]
        if result["event_type"] == "transfer":
            if not isinstance(related, str) or related == result["account_id"] or related not in catalog["accounts"] or catalog["accounts"][related]["portfolio_id"] != result["portfolio_id"] or result["flow_classification"] != "not_applicable":
                _abort("desktop_cash_coverage_catalog_invalid")
        elif related is not None:
            _abort("desktop_cash_coverage_input_invalid")
    elif action == "record_interest_income":
        result["local_date"] = _date(result["local_date"])
        result["gross_income_decimal"] = _decimal(result["gross_income_decimal"], positive=True)
        linked = result["linked_cash_event_ref"]
        if linked is not None and (not isinstance(linked, str) or re.fullmatch(r"^cash_event_[0-9]{4}$", linked) is None):
            _abort("desktop_cash_coverage_input_invalid")
    else:
        result["as_of_date"] = _date(result["as_of_date"])
        result["observed_balance_decimal"] = _decimal(result["observed_balance_decimal"])
        result["evidence_fingerprint"] = _fingerprint(result["evidence_fingerprint"])
    return result


def _active_facts_for_command(connection: sqlite3.Connection, command_id: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for kind, (table, identifier) in FACT_TABLES.items():
        rows = connection.execute(
            f"SELECT fact.{identifier} FROM {table} fact WHERE fact.command_id=? AND NOT EXISTS (SELECT 1 FROM cash_coverage_fact_supersession s WHERE s.predecessor_kind=? AND s.predecessor_fact_id=fact.{identifier}) ORDER BY fact.{identifier}",
            (command_id, kind),
        ).fetchall()
        result.extend((kind, row[0]) for row in rows)
    return result


def _all_facts_for_command(connection: sqlite3.Connection, command_id: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for kind, (table, identifier) in FACT_TABLES.items():
        result.extend(
            (kind, row[0])
            for row in connection.execute(
                f"SELECT {identifier} FROM {table} WHERE command_id=? ORDER BY {identifier}",
                (command_id,),
            )
        )
    return result


def _validate_supersession_lineage(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT * FROM cash_coverage_fact_supersession ORDER BY committed_at_utc,supersession_id"
    ).fetchall()
    by_command: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        predecessor_table, predecessor_id = FACT_TABLES[row["predecessor_kind"]]
        predecessor = connection.execute(
            f"SELECT command_id FROM {predecessor_table} WHERE {predecessor_id}=?",
            (row["predecessor_fact_id"],),
        ).fetchone()
        if predecessor is None or predecessor["command_id"] == row["command_id"]:
            _abort("desktop_cash_coverage_store_invalid")
        if row["revision_action"] == "void":
            if row["replacement_kind"] is not None or row["replacement_fact_id"] is not None:
                _abort("desktop_cash_coverage_store_invalid")
        else:
            if row["replacement_kind"] != row["predecessor_kind"] or row["replacement_fact_id"] is None:
                _abort("desktop_cash_coverage_store_invalid")
            replacement_table, replacement_id = FACT_TABLES[row["replacement_kind"]]
            replacement = connection.execute(
                f"SELECT * FROM {replacement_table} WHERE {replacement_id}=?",
                (row["replacement_fact_id"],),
            ).fetchone()
            if replacement is None or replacement["command_id"] != row["command_id"]:
                _abort("desktop_cash_coverage_store_invalid")
            if row["revision_action"] == "correct":
                predecessor_fact = connection.execute(
                    f"SELECT * FROM {predecessor_table} WHERE {predecessor_id}=?",
                    (row["predecessor_fact_id"],),
                ).fetchone()
                identity_fields = ["portfolio_id", "account_id", "cash_asset_id", "currency"]
                if row["predecessor_kind"] == "cash_event":
                    identity_fields.append("event_type")
                elif row["predecessor_kind"] == "interest_income":
                    identity_fields.append("income_type")
                if predecessor_fact is None or any(predecessor_fact[field] != replacement[field] for field in identity_fields):
                    _abort("desktop_cash_coverage_predecessor_conflict")
        by_command.setdefault(row["command_id"], []).append(row)
    for command_id, command_rows in by_command.items():
        predecessor_commands = set()
        replacement_facts = set()
        for row in command_rows:
            table, identifier = FACT_TABLES[row["predecessor_kind"]]
            predecessor_commands.add(connection.execute(
                f"SELECT command_id FROM {table} WHERE {identifier}=?", (row["predecessor_fact_id"],)
            ).fetchone()[0])
            if row["replacement_fact_id"] is not None:
                replacement_facts.add((row["replacement_kind"], row["replacement_fact_id"]))
        created_facts = set(_all_facts_for_command(connection, command_id))
        if not predecessor_commands or not replacement_facts <= created_facts:
            _abort("desktop_cash_coverage_store_invalid")
        if replacement_facts != created_facts and not _upgrade_surplus_valid(connection, command_rows, created_facts - replacement_facts):
            _abort("desktop_cash_coverage_store_invalid")
        receipt = connection.execute("SELECT action_type FROM cash_coverage_command_receipt WHERE command_id=?", (command_id,)).fetchone()
        if receipt is None or receipt[0] != "revise_cash_coverage":
            _abort("desktop_cash_coverage_store_invalid")


def _upgrade_surplus_valid(
    connection: sqlite3.Connection, command_rows: list[sqlite3.Row], surplus: set[tuple[str, str]],
) -> bool:
    """Fakten einer Revision ohne Linie sind nur bei der Anhebung eines Zeitraums erlaubt.

    Gegenstueck zu `_coverage_upgrade`, geprueft am Speicher statt am Kommando:
    Die Revision loest genau einen nicht abgestimmten Zeitraum durch einen
    abgestimmten desselben Kontos und Beginns ab, und was ohne Vorgaenger entstand,
    ist dessen Eroeffnung am ersten Tag und eine Abstimmung desselben Kontos.
    """
    periods = [row for row in command_rows if row["predecessor_kind"] == "coverage_period"]
    if len(periods) != 1 or periods[0]["revision_action"] != "supersede":
        return False
    before = connection.execute("SELECT * FROM cash_coverage_period WHERE coverage_id=?", (periods[0]["predecessor_fact_id"],)).fetchone()
    after = connection.execute("SELECT * FROM cash_coverage_period WHERE coverage_id=?", (periods[0]["replacement_fact_id"],)).fetchone()
    if (
        before is None or after is None or before["coverage_mode"] == "complete_reconciled"
        or after["coverage_mode"] != "complete_reconciled"
        or any(before[field] != after[field] for field in ("portfolio_id", "account_id", "cash_asset_id", "effective_from", "effective_to"))
    ):
        return False
    kinds = Counter(kind for kind, _ in surplus)
    if not kinds or kinds - Counter({"cash_event": 1, "reconciliation": 1}):
        return False
    for kind, identifier in surplus:
        table, column = FACT_TABLES[kind]
        fact = connection.execute(f"SELECT * FROM {table} WHERE {column}=?", (identifier,)).fetchone()
        if fact is None or fact["account_id"] != after["account_id"] or fact["cash_asset_id"] != after["cash_asset_id"]:
            return False
        if kind == "cash_event" and (fact["event_type"] != "opening_balance" or fact["local_date"] != after["effective_from"]):
            return False
    return True


def _active_facts_by_command(connection: sqlite3.Connection) -> dict[str, list[tuple[str, str]]]:
    """Die aktiven Fakten aller Kommandos in vier Abfragen - eine je Faktentabelle.

    Dieselbe Auskunft wie `_active_facts_for_command`, nur fuer alle Kommandos auf
    einmal. Die Faktentabellen tragen keinen Index auf `command_id`; je Kommando
    einzeln gefragt, liest jede Abfrage die ganze Tabelle. Bei vielen Belegen und
    Cash-Ereignissen waren das viele Millionen gelesene Zeilen bei jedem Sitzungsstart.

    Reihenfolge je Kommando wie dort: erst nach Faktenart in der Folge von
    FACT_TABLES, dann nach Kennung. `facts[0]` ist der Primaerfakt eines Belegs.
    """
    result: dict[str, list[tuple[str, str]]] = {}
    for kind, (table, identifier) in FACT_TABLES.items():
        for command_id, fact_id in connection.execute(
            f"SELECT fact.command_id,fact.{identifier} FROM {table} fact WHERE NOT EXISTS (SELECT 1 FROM cash_coverage_fact_supersession s WHERE s.predecessor_kind=? AND s.predecessor_fact_id=fact.{identifier}) ORDER BY fact.command_id,fact.{identifier}",
            (kind,),
        ):
            result.setdefault(command_id, []).append((kind, fact_id))
    return result


def _active_command_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    facts_by_command = _active_facts_by_command(connection)
    rows = []
    for receipt in connection.execute("SELECT * FROM cash_coverage_command_receipt ORDER BY committed_at_utc,command_id"):
        facts = facts_by_command.get(receipt["command_id"])
        if facts:
            rows.append({"receipt": dict(receipt), "facts": facts})
    return rows


def _record_map(connection: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    return {
        "cash_record_" + _sha({"command_id": row["receipt"]["command_id"]})[:32]: row
        for row in _active_command_rows(connection)
    }


def _resolve_predecessor(connection: sqlite3.Connection, predecessor_ref: Any) -> dict[str, Any]:
    if not isinstance(predecessor_ref, str) or RECORD_REF.fullmatch(predecessor_ref) is None:
        _abort("desktop_cash_coverage_revision_invalid")
    row = _record_map(connection).get(predecessor_ref)
    if row is None:
        _abort("desktop_cash_coverage_predecessor_missing")
    return row


def _command(value: Any, catalog: dict[str, Any], connection: sqlite3.Connection | None = None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or value.get("action_type") not in ACTION_TYPES:
        _abort("desktop_cash_coverage_input_invalid")
    action = value["action_type"]
    if action in REGULAR_ACTIONS:
        result = _regular_command(value, catalog, nested=False)
        if not isinstance(result["request_ref"], str) or REQUEST.fullmatch(result["request_ref"]) is None:
            _abort("desktop_cash_coverage_input_invalid")
        mode, source = _metadata(result)
        result["input_mode"] = mode
        result["source_candidate_fingerprint"] = source
        result["operation_type"] = "create"
        result["fact_action_type"] = action
        return result
    result = _strict(value, {"action_type", "request_ref", "input_mode", "source_candidate_fingerprint", "predecessor_refs", "replacements"})
    if not isinstance(result["request_ref"], str) or REQUEST.fullmatch(result["request_ref"]) is None or connection is None:
        _abort("desktop_cash_coverage_revision_invalid")
    refs = result["predecessor_refs"]
    replacements_value = result["replacements"]
    if not isinstance(refs, list) or not refs or len(refs) > 100 or len(set(refs)) != len(refs) or not isinstance(replacements_value, list) or len(replacements_value) > 100:
        _abort("desktop_cash_coverage_revision_invalid")
    mode, source = _metadata(result)
    predecessors = [_resolve_predecessor(connection, ref) for ref in refs]
    predecessor_ids = [row["receipt"]["command_id"] for row in predecessors]
    if len(set(predecessor_ids)) != len(predecessor_ids):
        _abort("desktop_cash_coverage_revision_invalid")
    predecessor_facts = [fact for row in predecessors for fact in row["facts"]]
    if action == "void":
        if replacements_value:
            _abort("desktop_cash_coverage_revision_invalid")
        replacements: list[dict[str, Any]] = []
    else:
        if not replacements_value:
            _abort("desktop_cash_coverage_revision_invalid")
        replacements = [_regular_command(item, catalog, nested=True) for item in replacements_value]
        expected = Counter(kind for kind, _ in predecessor_facts)
        actual = Counter()
        for replacement in replacements:
            for kind in _regular_fact_kinds(replacement):
                actual[kind] += 1
        if actual != expected:
            if not _coverage_upgrade(connection, action, predecessor_facts, replacements, expected, actual):
                _abort("desktop_cash_coverage_revision_invalid")
            result["coverage_upgrade"] = True
    result.update(
        input_mode=mode, source_candidate_fingerprint=source,
        predecessor_command_ids=predecessor_ids,
        predecessor_command_id=predecessor_ids[0] if len(predecessor_ids) == 1 else None,
        predecessor_set_fingerprint=_sha(sorted(predecessor_ids)),
        predecessor_components=predecessors, predecessor_facts=predecessor_facts,
        fact_action_type="revise_cash_coverage", replacements=replacements,
        operation_type=action,
    )
    return result


def _coverage_upgrade(
    connection: sqlite3.Connection, action: str, predecessor_facts: list[tuple[str, str]],
    replacements: list[dict[str, Any]], expected: Counter, actual: Counter,
) -> bool:
    """Die eine Ersetzung, die mehr Fakten erzeugt, als sie abloest (#417).

    Ein nicht abgestimmter Zeitraum wird ausdruecklich durch einen abgestimmten
    ersetzt. Jede `complete_reconciled`-Erklaerung traegt Eroeffnung und Abstimmung
    in sich; der Vorgaenger hatte keine. Die Regel "gleich viele Fakten je Art"
    schloss das aus, und `record_reconciliation` verlangt umgekehrt einen schon
    abgestimmten Zeitraum - ein Zirkel, in dem ein online gepruefter Saldo nicht
    festzuhalten war.

    Eng gefasst: genau ein `supersede`, genau ein Zeitraum als Vorgaenger, der
    nicht schon abgestimmt ist, dasselbe Konto, derselbe Beginn, dasselbe Ende.
    Eine bereits gebuchte Eroeffnung des Vorgaengers muss mit abgeloest werden.
    Alles andere bleibt bei der alten Regel.
    """
    if action != "supersede" or len(replacements) != 1:
        return False
    replacement = replacements[0]
    if replacement["action_type"] != "declare_coverage" or replacement["coverage_mode"] != "complete_reconciled":
        return False
    periods = [identifier for kind, identifier in predecessor_facts if kind == "coverage_period"]
    openings = [identifier for kind, identifier in predecessor_facts if kind == "cash_event"]
    if len(periods) != 1 or len(openings) > 1 or len(predecessor_facts) != len(periods) + len(openings):
        return False
    period = connection.execute("SELECT * FROM cash_coverage_period WHERE coverage_id=?", (periods[0],)).fetchone()
    if (
        period is None or period["coverage_mode"] == "complete_reconciled"
        or any(period[field] != replacement[field] for field in ("portfolio_id", "account_id", "cash_asset_id", "effective_from", "effective_to"))
    ):
        return False
    booked_openings = [
        row["cash_event_id"] for row in _active_rows(connection, "cash_event", "effective_at_utc,cash_event_id")
        if row["event_type"] == "opening_balance" and row["account_id"] == period["account_id"]
        and row["local_date"] >= period["effective_from"] and (period["effective_to"] is None or row["local_date"] <= period["effective_to"])
    ]
    # Eine vorhandene Eroeffnung bliebe sonst neben der neuen stehen.
    if sorted(booked_openings) != sorted(openings):
        return False
    surplus = actual - expected
    return not (expected - actual) and surplus == Counter({"reconciliation": 1, **({} if openings else {"cash_event": 1})})


def _superseded(connection: sqlite3.Connection, kind: str) -> set[str]:
    return {row[0] for row in connection.execute("SELECT predecessor_fact_id FROM cash_coverage_fact_supersession WHERE predecessor_kind=?", (kind,))}


def _follow_cash_event(connection: sqlite3.Connection, identifier: str) -> str:
    seen = set()
    current = identifier
    while current not in seen:
        seen.add(current)
        row = connection.execute(
            "SELECT replacement_fact_id FROM cash_coverage_fact_supersession WHERE predecessor_kind='cash_event' AND predecessor_fact_id=?",
            (current,),
        ).fetchone()
        if row is None:
            return current
        if row[0] is None:
            return identifier
        current = row[0]
    _abort("desktop_cash_coverage_store_invalid")


def _active_rows(connection: sqlite3.Connection, kind: str, order: str) -> list[sqlite3.Row]:
    table, identifier = FACT_TABLES[kind]
    return connection.execute(
        f"SELECT fact.* FROM {table} fact WHERE NOT EXISTS (SELECT 1 FROM cash_coverage_fact_supersession s WHERE s.predecessor_kind=? AND s.predecessor_fact_id=fact.{identifier}) ORDER BY {order}",
        (kind,),
    ).fetchall()


def _current_payload(connection: sqlite3.Connection, catalog: dict[str, Any]) -> dict[str, Any]:
    periods = _active_rows(connection, "coverage_period", "account_id,effective_from,coverage_id")
    cash_events = _active_rows(connection, "cash_event", "effective_at_utc,cash_event_id")
    incomes = _active_rows(connection, "income_event", "local_date,income_event_id")
    reconciliations = _active_rows(connection, "reconciliation", "account_id,as_of_date,reconciliation_id")
    known_accounts = set(catalog.get("accounts", {}))
    known_assets = set(catalog.get("assets", {}))
    if catalog:
        for row in [*periods, *cash_events, *incomes, *reconciliations]:
            if row["account_id"] not in known_accounts or row["cash_asset_id"] not in known_assets or catalog["assets"][row["cash_asset_id"]]["price_currency"] != row["currency"] or catalog["accounts"][row["account_id"]]["portfolio_id"] != row["portfolio_id"]:
                _abort("desktop_cash_coverage_catalog_invalid")
    accounts = sorted({(row["account_id"], row["cash_asset_id"], row["currency"]) for row in periods})
    return {
        "cash_coverage_version": 1,
        "accounts": [{"account_ref": account, "cash_asset_ref": asset, "currency": currency} for account, asset, currency in accounts],
        "coverage_periods": [{"coverage_ref": row["coverage_id"], "account_ref": row["account_id"], "effective_from": row["effective_from"], "effective_to": row["effective_to"], "coverage_mode": row["coverage_mode"]} for row in periods],
        "cash_events": [{"cash_event_ref": row["cash_event_id"], "event_type": row["event_type"], "account_ref": row["account_id"], "related_account_ref": row["related_account_id"], "cash_asset_ref": row["cash_asset_id"], "event_time_evidence": row["event_time_evidence"], "local_date": row["local_date"], "local_time": row["local_time"], "time_zone": row["time_zone"], "effective_at_utc": row["effective_at_utc"], "amount_decimal": row["amount_decimal"], "flow_classification": row["flow_classification"]} for row in cash_events],
        "income_events": [{"income_event_ref": row["income_event_id"], "income_type": "interest", "account_ref": row["account_id"], "cash_asset_ref": row["cash_asset_id"], "local_date": row["local_date"], "gross_income_decimal": row["gross_income_decimal"], "linked_cash_event_ref": None if row["linked_cash_event_id"] is None else _follow_cash_event(connection, row["linked_cash_event_id"])} for row in incomes],
        "reconciliations": [{"reconciliation_ref": row["reconciliation_id"], "account_ref": row["account_id"], "cash_asset_ref": row["cash_asset_id"], "as_of_date": row["as_of_date"], "observed_balance_decimal": row["observed_balance_decimal"], "evidence_ref": "evd_" + row["evidence_fingerprint"][:32]} for row in reconciliations],
    }


def _empty_projection() -> dict[str, Any]:
    body = {
        "cash_coverage_version": 1, "projection_status": "coverage_preview_completed", "period_count": 0,
        "periods": [], "cash_event_count": 0, "income_event_count": 0, "linked_income_event_count": 0,
        "internal_transfer_count": 0, "internal_transfer_portfolio_net_change_decimal": "0",
        "income_cash_balance_effect_created": False, "cash_guv_from_balance_events_created": False,
        "external_counter_accounts_created": False, "full_double_entry_created": False,
        "coverage_inferred": False, "canonical_write": False, "provider_access": False,
        "network_access": False, "private_data_access": False,
    }
    return {**body, "preview_fingerprint": _sha(body)}


def _semantic(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload["coverage_periods"]:
        if any(payload[key] for key in ("accounts", "cash_events", "income_events", "reconciliations")):
            _abort("desktop_cash_coverage_event_outside_period")
        return _empty_projection()
    return validate_cash_coverage_v1(payload)


def _next_id(connection: sqlite3.Connection, table: str, prefix: str) -> str:
    count = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] + 1
    return f"{prefix}_{_sha({'contract': CONTRACT_VERSION, 'table': table, 'sequence': count})[:32]}"


def _period_for(connection: sqlite3.Connection, account_id: str, local_date: str) -> sqlite3.Row:
    rows = connection.execute(
        "SELECT period.* FROM cash_coverage_period period WHERE period.account_id=? AND period.effective_from<=? AND (period.effective_to IS NULL OR period.effective_to>=?) AND NOT EXISTS (SELECT 1 FROM cash_coverage_fact_supersession s WHERE s.predecessor_kind='coverage_period' AND s.predecessor_fact_id=period.coverage_id)",
        (account_id, local_date, local_date),
    ).fetchall()
    if len(rows) != 1:
        _abort("desktop_cash_coverage_event_outside_period")
    return rows[0]


def _event_ref_map(connection: sqlite3.Connection) -> dict[str, str]:
    rows = _active_rows(connection, "cash_event", "effective_at_utc,cash_event_id")
    return {f"cash_event_{index:04d}": row["cash_event_id"] for index, row in enumerate(rows, 1)}


def _linked_event_id(connection: sqlite3.Connection, public_ref: str | None) -> str | None:
    if public_ref is None:
        return None
    mapping = _event_ref_map(connection)
    if public_ref not in mapping:
        _abort("desktop_cash_coverage_input_invalid")
    return mapping[public_ref]


def _regular_fact_kinds(command: Mapping[str, Any]) -> tuple[str, ...]:
    action = command["action_type"]
    if action == "declare_coverage":
        return ("coverage_period", "cash_event", "reconciliation") if command["coverage_mode"] == "complete_reconciled" else ("coverage_period",)
    return {
        "record_cash_event": ("cash_event",),
        "record_interest_income": ("income_event",),
        "record_reconciliation": ("reconciliation",),
    }[action]


def _plan_regular_fact_ids(
    connection: sqlite3.Connection,
    command: Mapping[str, Any],
    reserved: dict[str, int] | None = None,
) -> dict[str, str]:
    reserved = {} if reserved is None else reserved
    details = {
        "coverage_period": ("cash_coverage_period", "cvg"),
        "cash_event": ("cash_coverage_event", "csh"),
        "income_event": ("cash_income_event", "inc"),
        "reconciliation": ("cash_coverage_reconciliation", "rec"),
    }
    planned: dict[str, str] = {}
    for kind in _regular_fact_kinds(command):
        table, prefix = details[kind]
        sequence = connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] + reserved.get(kind, 0) + 1
        planned[kind] = f"{prefix}_{_sha({'contract': CONTRACT_VERSION, 'table': table, 'sequence': sequence})[:32]}"
        reserved[kind] = reserved.get(kind, 0) + 1
    return planned


def _apply_regular(
    connection: sqlite3.Connection,
    command: dict[str, Any],
    command_id: str,
    committed: str,
    planned: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    action = command["action_type"]
    planned = _plan_regular_fact_ids(connection, command) if planned is None else planned
    created: list[tuple[str, str]] = []
    if action == "declare_coverage":
        coverage_id = planned["coverage_period"]
        connection.execute("INSERT INTO cash_coverage_period VALUES(?,?,?,?,?,?,?,?,?,?)", (
            coverage_id, command["portfolio_id"], command["account_id"], command["cash_asset_id"], command["currency"], command["effective_from"], command["effective_to"], command["coverage_mode"], command_id, committed,
        ))
        created.append(("coverage_period", coverage_id))
        if command["coverage_mode"] == "complete_reconciled":
            event_id = planned["cash_event"]
            connection.execute("INSERT INTO cash_coverage_event VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                event_id, "opening_balance", command["portfolio_id"], command["account_id"], None, command["cash_asset_id"], command["currency"], command["opening_event_time_evidence"], command["effective_from"], command["opening_local_time"], command["opening_time_zone"], command["opening_effective_at_utc"], command["opening_balance_decimal"], "not_applicable", command_id, committed,
            ))
            created.append(("cash_event", event_id))
            reconciliation_id = planned["reconciliation"]
            connection.execute("INSERT INTO cash_coverage_reconciliation VALUES(?,?,?,?,?,?,?,?,?,?)", (
                reconciliation_id, command["portfolio_id"], command["account_id"], command["cash_asset_id"], command["currency"], command["reconciliation_as_of_date"], command["observed_balance_decimal"], command["evidence_fingerprint"], command_id, committed,
            ))
            created.append(("reconciliation", reconciliation_id))
    elif action == "record_cash_event":
        period = _period_for(connection, command["account_id"], command["local_date"])
        if period["cash_asset_id"] != command["cash_asset_id"] or period["coverage_mode"] not in {"partial", "complete_reconciled"}:
            _abort("desktop_cash_coverage_mode_invalid")
        if command["event_type"] == "transfer":
            related = _period_for(connection, command["related_account_id"], command["local_date"])
            if related["cash_asset_id"] != command["cash_asset_id"] or related["currency"] != command["currency"] or related["coverage_mode"] not in {"partial", "complete_reconciled"}:
                _abort("desktop_cash_coverage_mode_invalid")
        identifier = planned["cash_event"]
        connection.execute("INSERT INTO cash_coverage_event VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            identifier, command["event_type"], command["portfolio_id"], command["account_id"], command["related_account_id"], command["cash_asset_id"], command["currency"], command["event_time_evidence"], command["local_date"], command["local_time"], command["time_zone"], command["effective_at_utc"], command["amount_decimal"], command["flow_classification"], command_id, committed,
        ))
        created.append(("cash_event", identifier))
    elif action == "record_interest_income":
        period = _period_for(connection, command["account_id"], command["local_date"])
        if period["cash_asset_id"] != command["cash_asset_id"] or period["coverage_mode"] == "not_tracked":
            _abort("desktop_cash_coverage_mode_invalid")
        linked = _linked_event_id(connection, command["linked_cash_event_ref"])
        if linked is not None:
            row = connection.execute("SELECT * FROM cash_coverage_event WHERE cash_event_id=?", (linked,)).fetchone()
            if row is None or row["event_type"] != "deposit" or row["account_id"] != command["account_id"] or row["cash_asset_id"] != command["cash_asset_id"]:
                _abort("desktop_cash_coverage_input_invalid")
        identifier = planned["income_event"]
        connection.execute("INSERT INTO cash_income_event VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
            identifier, "interest", command["portfolio_id"], command["account_id"], command["cash_asset_id"], command["currency"], command["local_date"], command["gross_income_decimal"], linked, command_id, committed,
        ))
        created.append(("income_event", identifier))
    else:
        period = _period_for(connection, command["account_id"], command["as_of_date"])
        if period["cash_asset_id"] != command["cash_asset_id"] or period["coverage_mode"] != "complete_reconciled":
            _abort("desktop_cash_coverage_mode_invalid")
        identifier = planned["reconciliation"]
        connection.execute("INSERT INTO cash_coverage_reconciliation VALUES(?,?,?,?,?,?,?,?,?,?)", (
            identifier, command["portfolio_id"], command["account_id"], command["cash_asset_id"], command["currency"], command["as_of_date"], command["observed_balance_decimal"], command["evidence_fingerprint"], command_id, committed,
        ))
        created.append(("reconciliation", identifier))
    return created


def _apply_candidate(connection: sqlite3.Connection, command: dict[str, Any], command_id: str, committed: str) -> list[tuple[str, str]]:
    if command["operation_type"] == "create":
        return _apply_regular(connection, command, command_id, committed)
    predecessor_facts = list(command["predecessor_facts"])
    for component in command["predecessor_components"]:
        if _active_facts_for_command(connection, component["receipt"]["command_id"]) != component["facts"]:
            _abort("desktop_cash_coverage_predecessor_conflict")
    replacement_facts: list[tuple[str, str]] = []
    if command["replacements"]:
        priority = {"declare_coverage": 0, "record_cash_event": 1, "record_interest_income": 2, "record_reconciliation": 3}
        replacements = sorted(command["replacements"], key=lambda item: priority[item["action_type"]])
        reserved: dict[str, int] = {}
        plans = [_plan_regular_fact_ids(connection, replacement, reserved) for replacement in replacements]
        planned_by_kind: dict[str, list[str]] = {}
        for plan in plans:
            for kind, identifier in plan.items():
                planned_by_kind.setdefault(kind, []).append(identifier)
        predecessor_by_kind: dict[str, list[str]] = {}
        for kind, identifier in predecessor_facts:
            predecessor_by_kind.setdefault(kind, []).append(identifier)
        predecessor_counts = Counter({kind: len(ids) for kind, ids in predecessor_by_kind.items()})
        planned_counts = Counter({kind: len(ids) for kind, ids in planned_by_kind.items()})
        # Bei der Anhebung eines Zeitraums entstehen Eroeffnung und Abstimmung neu;
        # sie haben keinen Vorgaenger und darum keine Linie. Jede abgeloeste Art
        # muss trotzdem eins zu eins ersetzt werden.
        if predecessor_counts != planned_counts and not (
            command.get("coverage_upgrade") is True
            and all(planned_counts[kind] == count for kind, count in predecessor_counts.items())
        ):
            _abort("desktop_cash_coverage_revision_invalid")
        # Lineage is inserted first so replacement periods can overlap their retired
        # predecessors. The still-open transaction is accepted only after every planned
        # replacement exists and the complete lineage graph validates.
        for kind in sorted(predecessor_by_kind):
            for predecessor_id, replacement_id in zip(sorted(predecessor_by_kind[kind]), planned_by_kind[kind]):
                supersession_id = _next_id(connection, "cash_coverage_fact_supersession", "css")
                connection.execute("INSERT INTO cash_coverage_fact_supersession VALUES(?,?,?,?,?,?,?,?)", (
                    supersession_id, kind, predecessor_id, kind, replacement_id,
                    command["operation_type"], command_id, committed,
                ))
        for replacement, plan in zip(replacements, plans):
            replacement_facts.extend(_apply_regular(connection, replacement, command_id, committed, plan))
    else:
        for kind, identifier in predecessor_facts:
            supersession_id = _next_id(connection, "cash_coverage_fact_supersession", "css")
            connection.execute("INSERT INTO cash_coverage_fact_supersession VALUES(?,?,?,?,?,?,?,?)", (
                supersession_id, kind, identifier, None, None, "void", command_id, committed,
            ))
    return replacement_facts


def _summary(projection: Mapping[str, Any]) -> dict[str, Any]:
    return {key: projection[key] for key in ("period_count", "cash_event_count", "income_event_count", "linked_income_event_count", "internal_transfer_count", "internal_transfer_portfolio_net_change_decimal")}


def _preview(connection: sqlite3.Connection, raw_command: Mapping[str, Any], command: dict[str, Any], context: DesktopProductAssetActivityContextV1, canonical_fingerprint: str, committed: str = "2000-01-01T00:00:00Z") -> dict[str, Any]:
    before_payload = _current_payload(connection, {})
    before_state = _sha(before_payload)
    before_projection = _semantic(before_payload)
    try:
        connection.execute("SAVEPOINT preview")
        command_id = "ccmd_" + _sha({"request": command["request_ref"], "preview": True})[:32]
        fake_confirmation = _sha({"request": command["request_ref"], "preview": True})
        connection.execute("INSERT INTO cash_coverage_confirmation_attempt VALUES(?,?,?,?,?)", (fake_confirmation, command["request_ref"], fake_confirmation, committed, "attempted"))
        connection.execute("INSERT INTO cash_coverage_command_receipt VALUES(?,?,?,?,?,?,?,?,?)", (command_id, command["request_ref"], "data_app", command["fact_action_type"], context.actor_id, _sha(raw_command), canonical_fingerprint, fake_confirmation, committed))
        _apply_candidate(connection, command, command_id, committed)
        _validate_supersession_lineage(connection)
        after_payload = _current_payload(connection, {})
        after_projection = _semantic(after_payload)
        after_state = _sha(after_payload)
    except sqlite3.IntegrityError as error:
        message = str(error)
        if "cash_coverage_period_overlap" in message:
            _abort("desktop_cash_coverage_period_overlap")
        if "UNIQUE constraint failed" in message:
            _abort("desktop_cash_coverage_predecessor_conflict")
        _abort("desktop_cash_coverage_input_invalid")
    except CashCoverageV1Error as error:
        mapping = {
            "cash_coverage_period_overlap": "desktop_cash_coverage_period_overlap",
            "cash_coverage_mode_invalid": "desktop_cash_coverage_mode_invalid",
            "cash_coverage_event_outside_period": "desktop_cash_coverage_event_outside_period",
            "cash_coverage_reconciliation_mismatch": "desktop_cash_coverage_reconciliation_mismatch",
            "cash_coverage_complete_opening_required": "desktop_cash_coverage_mode_invalid",
            "cash_coverage_complete_reconciliation_required": "desktop_cash_coverage_mode_invalid",
        }
        _abort(mapping.get(error.code, "desktop_cash_coverage_input_invalid"))
    finally:
        try:
            connection.execute("ROLLBACK TO preview")
            connection.execute("RELEASE preview")
        except sqlite3.Error:
            pass
    body = {
        "desktop_cash_coverage_preview_version": 2, "status": "ready_for_confirmation",
        "action_type": raw_command["action_type"], "fact_action_type": command["fact_action_type"],
        "operation_type": command["operation_type"], "input_mode": command["input_mode"],
        "request_ref": command["request_ref"], "canonical_fingerprint": canonical_fingerprint,
        "cash_coverage_state_fingerprint": before_state, "command": dict(raw_command),
        "projection_before": before_projection, "projection": after_projection,
        "reconciliation": {
            "before_state_fingerprint": before_state, "after_state_fingerprint": after_state,
            "before": _summary(before_projection), "after": _summary(after_projection),
            "predecessor_fact_count": len(command.get("predecessor_facts", [])),
            "predecessor_preserved": True,
        },
        "confirmation_required": True, "one_attempt_only": True,
        "canonical_write": False, "asset_activity_write": False, "provider_access": False,
        "network_access": False, "private_data_access": False,
    }
    return {**body, "preview_fingerprint": _sha(body)}


def _preview_copy(connection: sqlite3.Connection, raw_command: Mapping[str, Any], catalog: dict[str, Any], context: DesktopProductAssetActivityContextV1, canonical_fingerprint: str) -> dict[str, Any]:
    memory = sqlite3.connect(":memory:")
    memory.row_factory = sqlite3.Row
    try:
        connection.backup(memory)
        memory.execute("PRAGMA foreign_keys=ON")
        command = _command(raw_command, catalog, memory)
        return _preview(memory, raw_command, command, context, canonical_fingerprint)
    except DesktopCashCoverageV1Error:
        raise
    except sqlite3.Error:
        _abort("desktop_cash_coverage_store_invalid")
    finally:
        memory.close()


def _preview_without_store(data_space: Path, context: DesktopProductAssetActivityContextV1, catalog: dict[str, Any], canonical_fingerprint: str, created_at_utc: str, raw_command: Mapping[str, Any]) -> dict[str, Any]:
    del data_space  # Preview must not materialize even a temporary authority in the data space.
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO cash_coverage_store_binding VALUES(1,?,?,?,?,?)",
            (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id, created_at_utc),
        )
        command = _command(raw_command, catalog, connection)
        return _preview(connection, raw_command, command, context, canonical_fingerprint)
    except DesktopCashCoverageV1Error:
        raise
    except (OSError, sqlite3.Error):
        _abort("desktop_cash_coverage_store_invalid")
    finally:
        connection.close()


def preview_desktop_cash_coverage_command_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, command_value: Any) -> dict[str, Any]:
    try:
        context, snapshot, catalog = _catalog(canonical_path, context_value)
        data_space = _owner_directory(data_space_path)
        if not isinstance(command_value, Mapping):
            _abort("desktop_cash_coverage_input_invalid")
        store = _store_path(data_space)
        if not store.exists():
            if command_value.get("action_type") != "declare_coverage":
                _abort("desktop_cash_coverage_store_invalid")
            return _preview_without_store(data_space, context, catalog, snapshot["source_fingerprint"], snapshot["created_at_utc"], command_value)
        connection = _open_store(store, context, read_only=True)
        try:
            return _preview_copy(connection, command_value, catalog, context, snapshot["source_fingerprint"])
        finally:
            connection.close()
    except DesktopCashCoverageV1Error:
        raise
    except Exception as error:
        raise DesktopCashCoverageV1Error("desktop_cash_coverage_boundary_failed") from error


def preview_desktop_reviewed_cash_coverage_candidate_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, reviewed_value: Any, request_ref: str) -> dict[str, Any]:
    reviewed = _strict(reviewed_value, {"reviewed_cash_coverage_candidate_version", "source_candidate_fingerprint", "mapped_command"})
    if reviewed["reviewed_cash_coverage_candidate_version"] != 1:
        _abort("desktop_cash_coverage_input_invalid")
    source = _fingerprint(reviewed["source_candidate_fingerprint"])
    if not isinstance(reviewed["mapped_command"], Mapping):
        _abort("desktop_cash_coverage_input_invalid")
    command = {**dict(reviewed["mapped_command"]), "request_ref": request_ref, "input_mode": "reviewed_import", "source_candidate_fingerprint": source}
    return preview_desktop_cash_coverage_command_v1(canonical_path, data_space_path, context_value, command)


def build_desktop_cash_coverage_confirmation_v1(preview: Mapping[str, Any], context_value: Any, confirmation_ref: str, issued_at_utc: str, expires_at_utc: str) -> dict[str, Any]:
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    issued = _utc(issued_at_utc, "desktop_cash_coverage_confirmation_invalid")
    expires = _utc(expires_at_utc, "desktop_cash_coverage_confirmation_invalid")
    if not isinstance(preview, Mapping) or preview.get("status") != "ready_for_confirmation" or preview.get("desktop_cash_coverage_preview_version") != 2 or not isinstance(confirmation_ref, str) or CONFIRMATION.fullmatch(confirmation_ref) is None or expires < issued:
        _abort("desktop_cash_coverage_confirmation_invalid")
    body = {
        "desktop_cash_coverage_confirmation_version": 1, "authorization_scope": "desktop_cash_coverage_command_once",
        "confirmation_ref": confirmation_ref, "request_ref": preview.get("request_ref"),
        "preview_fingerprint": preview.get("preview_fingerprint"), "context_fingerprint": _context_fingerprint(context),
        "issued_at_utc": issued, "expires_at_utc": expires, "confirmed": True,
        "canonical_write_authorized": False, "asset_activity_write_authorized": False,
        "provider_access_authorized": False, "network_access_authorized": False,
    }
    return {**body, "confirmation_fingerprint": _sha(body)}


def _verify_confirmation(value: Any, preview: Mapping[str, Any], context: DesktopProductAssetActivityContextV1, now: str) -> dict[str, Any]:
    if value is None:
        _abort("desktop_cash_coverage_confirmation_missing")
    fields = {"desktop_cash_coverage_confirmation_version", "authorization_scope", "confirmation_ref", "request_ref", "preview_fingerprint", "context_fingerprint", "issued_at_utc", "expires_at_utc", "confirmed", "canonical_write_authorized", "asset_activity_write_authorized", "provider_access_authorized", "network_access_authorized", "confirmation_fingerprint"}
    if not isinstance(value, Mapping) or set(value) != fields:
        _abort("desktop_cash_coverage_confirmation_invalid")
    result = dict(value)
    fingerprint = result.pop("confirmation_fingerprint")
    if not isinstance(fingerprint, str) or SHA.fullmatch(fingerprint) is None or fingerprint != _sha(result) or result["desktop_cash_coverage_confirmation_version"] != 1 or result["authorization_scope"] != "desktop_cash_coverage_command_once" or result["request_ref"] != preview["request_ref"] or result["preview_fingerprint"] != preview["preview_fingerprint"] or result["context_fingerprint"] != _context_fingerprint(context) or result["confirmed"] is not True or any(result[key] is not False for key in ("canonical_write_authorized", "asset_activity_write_authorized", "provider_access_authorized", "network_access_authorized")):
        _abort("desktop_cash_coverage_confirmation_invalid")
    if not isinstance(result["confirmation_ref"], str) or CONFIRMATION.fullmatch(result["confirmation_ref"]) is None:
        _abort("desktop_cash_coverage_confirmation_invalid")
    issued = _utc(result["issued_at_utc"], "desktop_cash_coverage_confirmation_invalid")
    expires = _utc(result["expires_at_utc"], "desktop_cash_coverage_confirmation_invalid")
    if now < issued or now > expires:
        _abort("desktop_cash_coverage_confirmation_expired")
    return {**result, "confirmation_fingerprint": fingerprint}


def _counts(connection: sqlite3.Connection) -> tuple[int, int, int, int]:
    return tuple(len(_active_rows(connection, kind, identifier)) for kind, (_, identifier) in FACT_TABLES.items())  # type: ignore[return-value]


def _revision_count(connection: sqlite3.Connection) -> int:
    return connection.execute("SELECT count(DISTINCT command_id) FROM cash_coverage_fact_supersession").fetchone()[0]


def _receipt_ref(receipt_fingerprint: str) -> str:
    return "cash_receipt_" + receipt_fingerprint[:24]


def _result(connection: sqlite3.Connection, receipt: Mapping[str, Any], provenance: Mapping[str, Any], status: str) -> DesktopCashCoverageResultV1:
    counts = _counts(connection)
    action_type = provenance["operation_type"] if receipt["action_type"] == "revise_cash_coverage" else receipt["action_type"]
    return DesktopCashCoverageResultV1(
        status, action_type, provenance["operation_type"],
        "cash_command_" + _sha({"request": receipt["request_ref"]})[:16],
        _receipt_ref(provenance["receipt_fingerprint"]), SCHEMA_VERSION,
        *counts, _revision_count(connection), True, provenance["input_mode"],
    )


def _existing_result(connection: sqlite3.Connection, raw_command: Mapping[str, Any], confirmation: Mapping[str, Any] | None) -> DesktopCashCoverageResultV1 | None:
    request_ref = raw_command.get("request_ref")
    if not isinstance(request_ref, str):
        return None
    row = connection.execute("SELECT * FROM cash_coverage_command_receipt WHERE request_ref=?", (request_ref,)).fetchone()
    if row is None:
        return None
    if row["payload_fingerprint"] != _sha(raw_command) or not isinstance(confirmation, Mapping) or row["confirmation_fingerprint"] != confirmation.get("confirmation_fingerprint"):
        _abort("desktop_cash_coverage_command_conflict")
    provenance = connection.execute("SELECT * FROM cash_coverage_command_provenance WHERE command_id=?", (row["command_id"],)).fetchone()
    if provenance is None:
        if connection.execute("SELECT 1 FROM cash_coverage_schema_migration_receipt WHERE singleton_id=1").fetchone() is None:
            _abort("desktop_cash_coverage_receipt_invalid")
        legacy = {
            "operation_type": "create", "input_mode": "migrated_schema2900",
            "receipt_fingerprint": _sha({"legacy_command_receipt": dict(row)}),
        }
        return _result(connection, dict(row), legacy, "already_committed")
    body = {key: provenance[key] for key in provenance.keys() if key != "receipt_fingerprint"}
    if provenance["receipt_fingerprint"] != _sha(body):
        _abort("desktop_cash_coverage_receipt_invalid")
    return _result(connection, dict(row), dict(provenance), "already_committed")


def _insert_attempt(connection: sqlite3.Connection, raw_command: Mapping[str, Any], command: Mapping[str, Any], confirmation: Mapping[str, Any], preview: Mapping[str, Any], context: DesktopProductAssetActivityContextV1, canonical_fingerprint: str, at: str) -> None:
    connection.execute("INSERT INTO cash_coverage_confirmation_attempt VALUES(?,?,?,?,?)", (confirmation["confirmation_fingerprint"], command["request_ref"], preview["preview_fingerprint"], at, "attempted"))
    connection.execute("INSERT INTO cash_coverage_attempt_evidence VALUES(?,?,?,?,?,?,?,?,?)", (
        confirmation["confirmation_fingerprint"], _context_fingerprint(context), command["input_mode"], command["source_candidate_fingerprint"],
        _canonical(raw_command).decode("utf-8"), _sha(raw_command), _canonical(confirmation).decode("utf-8"), canonical_fingerprint, at,
    ))


def _commit_after_attempt(connection: sqlite3.Connection, raw_command: Mapping[str, Any], command: dict[str, Any], confirmed: Mapping[str, Any], preview: Mapping[str, Any], context: DesktopProductAssetActivityContextV1, canonical_fingerprint: str, committed: str, data_space: Path, canonical_path: Path, recovery_confirmation_fingerprint: str | None, failpoint: str | None, recovery_attempt: tuple[str, str, str, str, str] | None = None) -> DesktopCashCoverageResultV1:
    preview_now = _preview_copy(connection, raw_command, _catalog(canonical_path, context)[2], context, canonical_fingerprint)
    if preview_now["preview_fingerprint"] != preview["preview_fingerprint"]:
        _abort("desktop_cash_coverage_preview_stale")
    before_state = preview_now["cash_coverage_state_fingerprint"]
    connection.execute("BEGIN IMMEDIATE")
    if recovery_attempt is not None:
        connection.execute("INSERT INTO cash_coverage_recovery_attempt VALUES(?,?,?,?,?)", recovery_attempt)
        if failpoint == "after_attempt":
            _abort("synthetic_desktop_cash_coverage_failpoint")
    command_id = "ccmd_" + _sha({"confirmation": confirmed["confirmation_fingerprint"], "request": command["request_ref"]})[:32]
    connection.execute("INSERT INTO cash_coverage_command_receipt VALUES(?,?,?,?,?,?,?,?,?)", (
        command_id, command["request_ref"], "data_app", command["fact_action_type"], context.actor_id,
        _sha(raw_command), canonical_fingerprint, confirmed["confirmation_fingerprint"], committed,
    ))
    if failpoint == "after_receipt":
        _abort("synthetic_desktop_cash_coverage_failpoint")
    _apply_candidate(connection, command, command_id, committed)
    _validate_supersession_lineage(connection)
    if failpoint == "after_fact":
        _abort("synthetic_desktop_cash_coverage_failpoint")
    after_payload = _current_payload(connection, _catalog(canonical_path, context)[2])
    _semantic(after_payload)
    after_state = _sha(after_payload)
    provenance_body = {
        "command_id": command_id, "operation_type": command["operation_type"], "input_mode": command["input_mode"],
        "source_candidate_fingerprint": command["source_candidate_fingerprint"],
        "predecessor_command_id": command.get("predecessor_command_id"),
        "predecessor_set_fingerprint": command.get("predecessor_set_fingerprint"),
        "before_state_fingerprint": before_state, "after_state_fingerprint": after_state,
        "recovery_confirmation_fingerprint": recovery_confirmation_fingerprint,
        "predecessor_preserved": 1,
    }
    provenance = {**provenance_body, "receipt_fingerprint": _sha(provenance_body)}
    connection.execute("INSERT INTO cash_coverage_command_provenance VALUES(?,?,?,?,?,?,?,?,?,?,?)", tuple(provenance[key] for key in ("command_id", "operation_type", "input_mode", "source_candidate_fingerprint", "predecessor_command_id", "predecessor_set_fingerprint", "before_state_fingerprint", "after_state_fingerprint", "recovery_confirmation_fingerprint", "predecessor_preserved", "receipt_fingerprint")))
    _validate_provenance(connection)
    with _CanonicalBarrier(data_space):
        if _sha_file(canonical_path) != canonical_fingerprint:
            _abort("desktop_cash_coverage_canonical_changed")
        connection.commit()
    os.chmod(_store_path(data_space), 0o600)
    result = _result(connection, {"action_type": command["fact_action_type"], "request_ref": command["request_ref"]}, provenance, "recovered_committed" if recovery_confirmation_fingerprint else "committed")
    if failpoint == "after_commit":
        _abort("synthetic_desktop_cash_coverage_failpoint")
    return result


def apply_desktop_cash_coverage_command_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, command_value: Any, confirmation: Mapping[str, Any] | None, committed_at_utc: str, *, failpoint: str | None = None) -> DesktopCashCoverageResultV1:
    committed = _utc(committed_at_utc)
    if failpoint not in FAILPOINTS or not isinstance(command_value, Mapping):
        _abort("desktop_cash_coverage_input_invalid")
    context, initial, catalog = _catalog(canonical_path, context_value)
    canonical = Path(initial["path"])
    data_space = _owner_directory(data_space_path)
    area = _owner_directory(data_space / STORE_AREA, create=True)
    store = _store_path(data_space)
    with _WriterLock(area):
        with _CanonicalBarrier(data_space):
            if _sha_file(canonical) != initial["source_fingerprint"]:
                _abort("desktop_cash_coverage_canonical_changed")
            if not store.exists():
                if command_value.get("action_type") != "declare_coverage":
                    _abort("desktop_cash_coverage_store_invalid")
                _create_store(store, context, initial["created_at_utc"])
        connection = _open_store(store, context, read_only=False)
        try:
            replay = _existing_result(connection, command_value, confirmation)
            if replay is not None:
                return replay
            command = _command(command_value, catalog, connection)
            attempted = connection.execute("SELECT 1 FROM cash_coverage_confirmation_attempt WHERE request_ref=?", (command["request_ref"],)).fetchone()
            if attempted:
                evidence = connection.execute(
                    "SELECT command_payload_fingerprint FROM cash_coverage_attempt_evidence evidence JOIN cash_coverage_confirmation_attempt attempt USING(confirmation_fingerprint) WHERE attempt.request_ref=?",
                    (command["request_ref"],),
                ).fetchone()
                if evidence is not None and evidence[0] != _sha(command_value):
                    _abort("desktop_cash_coverage_command_conflict")
                _abort("desktop_cash_coverage_confirmation_consumed")
            preview = _preview_copy(connection, command_value, catalog, context, initial["source_fingerprint"])
            if isinstance(confirmation, Mapping) and confirmation.get("request_ref") == command["request_ref"] and confirmation.get("preview_fingerprint") != preview["preview_fingerprint"]:
                _abort("desktop_cash_coverage_preview_stale")
            confirmed = _verify_confirmation(confirmation, preview, context, committed)
            connection.execute("BEGIN IMMEDIATE")
            _insert_attempt(connection, command_value, command, confirmed, preview, context, initial["source_fingerprint"], committed)
            connection.commit()
            if failpoint == "after_attempt":
                _abort("synthetic_desktop_cash_coverage_failpoint")
            command = _command(command_value, catalog, connection)
            return _commit_after_attempt(connection, command_value, command, confirmed, preview, context, initial["source_fingerprint"], committed, data_space, canonical, None, failpoint)
        except DesktopCashCoverageV1Error:
            if connection.in_transaction:
                connection.rollback()
            raise
        except (CashCoverageV1Error, sqlite3.Error):
            if connection.in_transaction:
                connection.rollback()
            _abort("desktop_cash_coverage_write_failed")
        finally:
            connection.close()


def _candidate_action_types(connection: sqlite3.Connection, receipt: Mapping[str, Any]) -> list[str]:
    if receipt["action_type"] in REGULAR_ACTIONS:
        return [receipt["action_type"]]
    evidence = connection.execute(
        "SELECT evidence.command_payload_json FROM cash_coverage_attempt_evidence evidence WHERE evidence.confirmation_fingerprint=?",
        (receipt["confirmation_fingerprint"],),
    ).fetchone()
    if evidence is None:
        _abort("desktop_cash_coverage_store_invalid")
    try:
        payload = json.loads(evidence[0])
    except json.JSONDecodeError:
        _abort("desktop_cash_coverage_store_invalid")
    actions = [item.get("action_type") for item in payload.get("replacements", [])] if isinstance(payload, dict) else []
    if not actions or any(action not in REGULAR_ACTIONS for action in actions):
        _abort("desktop_cash_coverage_store_invalid")
    return actions


def _public_candidate(connection: sqlite3.Connection, row: dict[str, Any], record_ref: str, catalog: dict[str, Any]) -> dict[str, Any]:
    receipt = row["receipt"]
    facts = row["facts"]
    primary_kind, primary_id = facts[0]
    table, identifier = FACT_TABLES[primary_kind]
    fact = connection.execute(f"SELECT * FROM {table} WHERE {identifier}=?", (primary_id,)).fetchone()
    if fact is None:
        _abort("desktop_cash_coverage_store_invalid")
    return {
        "record_ref": record_ref, "fact_action_type": receipt["action_type"],
        "replacement_action_types": _candidate_action_types(connection, receipt), "fact_kind": primary_kind,
        "account_label": catalog["accounts"][fact["account_id"]]["display_name"],
        "cash_asset_label": catalog["assets"][fact["cash_asset_id"]]["display_name"],
        "effective_date": fact["effective_from"] if primary_kind == "coverage_period" else fact["local_date"] if primary_kind in {"cash_event", "income_event"} else fact["as_of_date"],
        "fact_count": len(facts), "predecessor_preserved_on_revision": True,
    }


def read_desktop_cash_coverage_revision_candidates_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any) -> dict[str, Any]:
    context, _, catalog = _catalog(canonical_path, context_value)
    data_space = _owner_directory(data_space_path)
    store = _store_path(data_space)
    if not store.exists():
        return {"desktop_cash_coverage_revision_candidates_version": 1, "status": "absent", "candidates": [], "path_exposed": False, "internal_id_exposed": False}
    connection = _open_store(store, context, read_only=True)
    try:
        candidates = [_public_candidate(connection, row, ref, catalog) for ref, row in _record_map(connection).items()]
        return {"desktop_cash_coverage_revision_candidates_version": 1, "status": "available", "candidates": candidates, "path_exposed": False, "internal_id_exposed": False}
    finally:
        connection.close()


def read_desktop_cash_coverage_recovery_candidates_v1(data_space_path: str | Path, context_value: Any) -> dict[str, Any]:
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    data_space = _owner_directory(data_space_path)
    store = _store_path(data_space)
    if not store.exists():
        return {"desktop_cash_coverage_recovery_candidates_version": 1, "status": "absent", "candidates": [], "path_exposed": False, "internal_id_exposed": False}
    connection = _open_store(store, context, read_only=True)
    try:
        rows = connection.execute(
            "SELECT attempt.confirmation_fingerprint,attempt.request_ref,attempt.attempted_at_utc,evidence.input_mode,evidence.command_payload_json,evidence.command_payload_fingerprint FROM cash_coverage_confirmation_attempt attempt JOIN cash_coverage_attempt_evidence evidence USING(confirmation_fingerprint) LEFT JOIN cash_coverage_command_receipt receipt USING(confirmation_fingerprint) LEFT JOIN cash_coverage_recovery_attempt recovery ON recovery.original_confirmation_fingerprint=attempt.confirmation_fingerprint WHERE receipt.command_id IS NULL AND recovery.recovery_confirmation_fingerprint IS NULL ORDER BY attempt.attempted_at_utc,attempt.confirmation_fingerprint"
        ).fetchall()
        candidates = []
        for row in rows:
            try:
                command = json.loads(row["command_payload_json"])
            except json.JSONDecodeError:
                _abort("desktop_cash_coverage_store_invalid")
            if not isinstance(command, dict) or _canonical(command).decode() != row["command_payload_json"] or _sha(command) != row["command_payload_fingerprint"]:
                _abort("desktop_cash_coverage_store_invalid")
            action = command.get("action_type")
            if action not in ACTION_TYPES:
                _abort("desktop_cash_coverage_store_invalid")
            candidates.append({
                "recovery_ref": _recovery_ref(row["confirmation_fingerprint"]),
                "attempted_at_utc": row["attempted_at_utc"], "input_mode": row["input_mode"], "action_type": action,
                "operation_type": action if action in REVISION_ACTIONS else "create",
                "recovery_reason": "attempt_consumed_receipt_absent",
            })
        return {"desktop_cash_coverage_recovery_candidates_version": 1, "status": "available", "candidates": candidates, "path_exposed": False, "internal_id_exposed": False}
    finally:
        connection.close()


def _recovery_evidence(connection: sqlite3.Connection, recovery_ref: str) -> tuple[sqlite3.Row, dict[str, Any], dict[str, Any]]:
    if not isinstance(recovery_ref, str) or RECOVERY_REF.fullmatch(recovery_ref) is None:
        _abort("desktop_cash_coverage_recovery_invalid")
    rows = [row for row in connection.execute(
        "SELECT attempt.*,evidence.* FROM cash_coverage_confirmation_attempt attempt JOIN cash_coverage_attempt_evidence evidence USING(confirmation_fingerprint) LEFT JOIN cash_coverage_command_receipt receipt USING(confirmation_fingerprint) WHERE receipt.command_id IS NULL ORDER BY attempt.confirmation_fingerprint"
    ).fetchall() if _recovery_ref(row["confirmation_fingerprint"]) == recovery_ref]
    if len(rows) != 1:
        _abort("desktop_cash_coverage_recovery_missing")
    row = rows[0]
    if connection.execute("SELECT 1 FROM cash_coverage_recovery_attempt WHERE original_confirmation_fingerprint=?", (row["confirmation_fingerprint"],)).fetchone():
        _abort("desktop_cash_coverage_recovery_confirmation_consumed")
    try:
        command = json.loads(row["command_payload_json"])
        confirmation = json.loads(row["confirmation_payload_json"])
    except json.JSONDecodeError:
        _abort("desktop_cash_coverage_recovery_invalid")
    if _canonical(command).decode() != row["command_payload_json"] or _sha(command) != row["command_payload_fingerprint"] or _canonical(confirmation).decode() != row["confirmation_payload_json"] or confirmation.get("confirmation_fingerprint") != row["confirmation_fingerprint"]:
        _abort("desktop_cash_coverage_recovery_invalid")
    return row, command, confirmation


def preview_desktop_cash_coverage_recovery_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, recovery_ref: str) -> dict[str, Any]:
    context, snapshot, catalog = _catalog(canonical_path, context_value)
    data_space = _owner_directory(data_space_path)
    connection = _open_store(_store_path(data_space), context, read_only=True)
    try:
        evidence, command, original_confirmation = _recovery_evidence(connection, recovery_ref)
        if evidence["context_fingerprint"] != _context_fingerprint(context) or evidence["canonical_fingerprint"] != snapshot["source_fingerprint"]:
            _abort("desktop_cash_coverage_recovery_stale")
        preview = _preview_copy(connection, command, catalog, context, snapshot["source_fingerprint"])
        if preview["preview_fingerprint"] != evidence["preview_fingerprint"]:
            _abort("desktop_cash_coverage_recovery_stale")
        trusted_body = {
            "desktop_cash_coverage_recovery_preview_version": 1, "status": "ready_for_recovery_confirmation",
            "recovery_ref": recovery_ref, "context_fingerprint": _context_fingerprint(context),
            "original_confirmation_fingerprint": evidence["confirmation_fingerprint"],
            "command": command, "original_confirmation": original_confirmation,
            "command_preview": preview, "canonical_fingerprint": snapshot["source_fingerprint"],
            "recovery_confirmation_required": True, "automatic_retry": False,
        }
        trusted = {**trusted_body, "recovery_plan_fingerprint": _sha(trusted_body)}
        public = {
            "desktop_cash_coverage_recovery_public_preview_version": 1, "status": "ready_for_recovery_confirmation",
            "recovery_ref": recovery_ref, "action_type": preview["action_type"], "operation_type": preview["operation_type"],
            "input_mode": preview["input_mode"], "before": preview["reconciliation"]["before"], "after": preview["reconciliation"]["after"],
            "recovery_reason": "attempt_consumed_receipt_absent",
            "recovery_confirmation_required": True, "automatic_retry": False, "canonical_write": False,
            "asset_activity_write": False, "provider_access": False, "network_access": False,
            "path_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False,
        }
        return {"public_preview": public, "trusted_preview": trusted}
    finally:
        connection.close()


def build_desktop_cash_coverage_recovery_confirmation_v1(trusted_preview: Mapping[str, Any], context_value: Any, confirmation_ref: str, issued_at_utc: str, expires_at_utc: str) -> dict[str, Any]:
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    issued = _utc(issued_at_utc, "desktop_cash_coverage_recovery_invalid")
    expires = _utc(expires_at_utc, "desktop_cash_coverage_recovery_invalid")
    if not isinstance(trusted_preview, Mapping) or trusted_preview.get("status") != "ready_for_recovery_confirmation" or not isinstance(confirmation_ref, str) or RECOVERY_CONFIRMATION.fullmatch(confirmation_ref) is None or issued > expires:
        _abort("desktop_cash_coverage_recovery_invalid")
    body = {
        "desktop_cash_coverage_recovery_confirmation_version": 1,
        "authorization_scope": "desktop_cash_coverage_recovery_once",
        "confirmation_ref": confirmation_ref, "recovery_ref": trusted_preview.get("recovery_ref"),
        "recovery_plan_fingerprint": trusted_preview.get("recovery_plan_fingerprint"),
        "context_fingerprint": _context_fingerprint(context), "issued_at_utc": issued,
        "expires_at_utc": expires, "confirmed": True, "automatic_retry_authorized": False,
    }
    return {**body, "recovery_confirmation_fingerprint": _sha(body)}


def apply_desktop_cash_coverage_recovery_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, trusted_preview: Mapping[str, Any], recovery_confirmation: Mapping[str, Any], recovered_at_utc: str, *, failpoint: str | None = None) -> DesktopCashCoverageResultV1:
    recovered = _utc(recovered_at_utc, "desktop_cash_coverage_recovery_invalid")
    if failpoint not in FAILPOINTS or not isinstance(trusted_preview, Mapping) or not isinstance(recovery_confirmation, Mapping):
        _abort("desktop_cash_coverage_recovery_invalid")
    context, snapshot, catalog = _catalog(canonical_path, context_value)
    trusted_body = dict(trusted_preview)
    plan_fp = trusted_body.pop("recovery_plan_fingerprint", None)
    if plan_fp != _sha(trusted_body) or trusted_preview.get("context_fingerprint") != _context_fingerprint(context):
        _abort("desktop_cash_coverage_recovery_invalid")
    confirmation_body = dict(recovery_confirmation)
    recovery_fp = confirmation_body.pop("recovery_confirmation_fingerprint", None)
    if recovery_fp != _sha(confirmation_body) or recovery_confirmation.get("authorization_scope") != "desktop_cash_coverage_recovery_once" or recovery_confirmation.get("recovery_plan_fingerprint") != plan_fp or recovery_confirmation.get("context_fingerprint") != _context_fingerprint(context) or recovery_confirmation.get("confirmed") is not True or recovery_confirmation.get("automatic_retry_authorized") is not False or recovered < recovery_confirmation.get("issued_at_utc", "") or recovered > recovery_confirmation.get("expires_at_utc", ""):
        _abort("desktop_cash_coverage_recovery_invalid")
    data_space = _owner_directory(data_space_path)
    canonical = Path(snapshot["path"])
    area = _owner_directory(data_space / STORE_AREA)
    with _WriterLock(area):
        connection = _open_store(_store_path(data_space), context, read_only=False)
        try:
            replay = _existing_result(connection, trusted_preview["command"], trusted_preview["original_confirmation"])
            if replay is not None:
                return replay
            evidence, command_value, original_confirmation = _recovery_evidence(connection, trusted_preview["recovery_ref"])
            if evidence["confirmation_fingerprint"] != trusted_preview.get("original_confirmation_fingerprint") or command_value != trusted_preview.get("command") or original_confirmation != trusted_preview.get("original_confirmation") or evidence["canonical_fingerprint"] != snapshot["source_fingerprint"]:
                _abort("desktop_cash_coverage_recovery_stale")
            preview = _preview_copy(connection, command_value, catalog, context, snapshot["source_fingerprint"])
            if preview != trusted_preview.get("command_preview"):
                _abort("desktop_cash_coverage_recovery_stale")
            command = _command(command_value, catalog, connection)
            recovery_attempt = (recovery_fp, evidence["confirmation_fingerprint"], plan_fp, recovered, "attempted")
            return _commit_after_attempt(connection, command_value, command, original_confirmation, preview, context, snapshot["source_fingerprint"], recovered, data_space, canonical, recovery_fp, failpoint, recovery_attempt)
        except DesktopCashCoverageV1Error:
            if connection.in_transaction:
                connection.rollback()
            raise
        except (CashCoverageV1Error, sqlite3.Error):
            if connection.in_transaction:
                connection.rollback()
            _abort("desktop_cash_coverage_write_failed")
        finally:
            connection.close()


def _history(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT receipt.*,provenance.operation_type,provenance.input_mode,provenance.predecessor_preserved,provenance.receipt_fingerprint FROM cash_coverage_command_receipt receipt LEFT JOIN cash_coverage_command_provenance provenance USING(command_id) ORDER BY receipt.committed_at_utc DESC,receipt.command_id DESC"
    ).fetchall()
    result = []
    for row in rows:
        legacy = row["receipt_fingerprint"] is None
        fingerprint = _sha({"legacy_command_receipt": {key: row[key] for key in ("command_id", "request_ref", "writer_area", "action_type", "actor_id", "payload_fingerprint", "canonical_fingerprint", "confirmation_fingerprint", "committed_at_utc")}}) if legacy else row["receipt_fingerprint"]
        operation_type = "create" if legacy else row["operation_type"]
        action_type = operation_type if row["action_type"] == "revise_cash_coverage" else row["action_type"]
        result.append({
            "receipt_ref": _receipt_ref(fingerprint), "action_type": action_type,
            "operation_type": operation_type,
            "input_mode": "migrated_schema2900" if legacy else row["input_mode"],
            "committed_at_utc": row["committed_at_utc"],
            "predecessor_preserved": True if legacy else bool(row["predecessor_preserved"]),
        })
    return result


def read_desktop_cash_coverage_exchange_projection_v1(store_path: str | Path, context_value: Any) -> dict[str, Any]:
    """Return the complete active schema-2901 projection to a trusted exchange caller."""
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    connection = _open_store(Path(store_path), context, read_only=True)
    try:
        return {
            "desktop_cash_coverage_exchange_projection_version": 1,
            "schema_version": SCHEMA_VERSION,
            "coverage_periods": [dict(row) for row in _active_rows(connection, "coverage_period", "effective_from,coverage_id")],
            "cash_events": [dict(row) for row in _active_rows(connection, "cash_event", "effective_at_utc,cash_event_id")],
            # Der Record-Ref seines Kommandos macht einen Ertrag revidierbar, ohne dass
            # der Aufrufer die Ref-Bildung nachbaut: eine Brutto-Korrektur nach einem
            # Auszug braucht genau diesen Vorgaenger (#465).
            "income_events": [dict(row) | {"record_ref": "cash_record_" + _sha({"command_id": row["command_id"]})[:32]}
                              for row in _active_rows(connection, "income_event", "local_date,income_event_id")],
            "reconciliations": [dict(row) for row in _active_rows(connection, "reconciliation", "as_of_date,reconciliation_id")],
        }
    except (CashCoverageV1Error, sqlite3.Error):
        _abort("desktop_cash_coverage_store_invalid")
    finally:
        connection.close()


def read_desktop_cash_coverage_reviewed_import_state_v1(store_path: str | Path, context_value: Any) -> dict[str, Any]:
    """Expose reviewed-candidate commit state without exposing internal Cash fact IDs."""
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    connection = _open_store(Path(store_path), context, read_only=True)
    try:
        applied = sorted({row[0] for row in connection.execute(
            "SELECT source_candidate_fingerprint FROM cash_coverage_command_provenance WHERE source_candidate_fingerprint IS NOT NULL"
        )})
        event_refs = _event_ref_map(connection)
        rows = connection.execute(
            "SELECT provenance.source_candidate_fingerprint,event.cash_event_id "
            "FROM cash_coverage_event event JOIN cash_coverage_command_provenance provenance USING(command_id) "
            "WHERE provenance.source_candidate_fingerprint IS NOT NULL AND NOT EXISTS ("
            "SELECT 1 FROM cash_coverage_fact_supersession supersession "
            "WHERE supersession.predecessor_kind='cash_event' AND supersession.predecessor_fact_id=event.cash_event_id) "
            "ORDER BY event.effective_at_utc,event.cash_event_id"
        ).fetchall()
        events_by_candidate: dict[str, list[str]] = {}
        for row in rows:
            events_by_candidate.setdefault(row["source_candidate_fingerprint"], []).append(
                next(public for public, identifier in event_refs.items() if identifier == row["cash_event_id"])
            )
        return {
            "desktop_cash_coverage_reviewed_import_state_version": 1,
            "schema_version": SCHEMA_VERSION,
            "applied_source_candidate_fingerprints": applied,
            "active_cash_event_refs_by_source_candidate_fingerprint": events_by_candidate,
        }
    except (CashCoverageV1Error, sqlite3.Error, StopIteration):
        _abort("desktop_cash_coverage_store_invalid")
    finally:
        connection.close()


def read_desktop_cash_coverage_view_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any) -> dict[str, Any]:
    context, _, catalog = _catalog(canonical_path, context_value)
    data_space = _owner_directory(data_space_path)
    store = _store_path(data_space)
    common = {"coverage_inferred": False, "canonical_write": False, "asset_activity_write": False, "provider_access": False, "network_access": False, "path_exposed": False, "context_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False}
    if not store.exists():
        return {"desktop_cash_coverage_read_model_version": 2, "status": "absent", "schema_version": None, "period_count": 0, "cash_event_count": 0, "income_event_count": 0, "reconciliation_count": 0, "revision_count": 0, "receipt_count": 0, "cash_coverage_state": "separate_not_read", "periods": [], "cash_history": [], "income_history": [], "receipt_history": [], **common}
    connection = _open_store(store, context, read_only=True)
    try:
        payload = _current_payload(connection, catalog)
        semantic = _semantic(payload)
        account_labels = {key: row["display_name"] for key, row in catalog["accounts"].items()}
        asset_labels = {key: row["display_name"] for key, row in catalog["assets"].items()}
        periods = [{key: row[key] for key in ("currency", "effective_from", "effective_to", "coverage_mode", "balance_status", "as_of_date", "opening_balance_decimal", "cash_movement_delta_decimal", "computed_balance_decimal", "observed_balance_decimal", "cash_event_count", "income_event_count", "gross_interest_income_decimal", "income_cash_balance_effect_created", "completeness_inferred")} | {"account_label": account_labels[row["account_ref"]], "cash_asset_label": asset_labels[row["cash_asset_ref"]]} for row in semantic["periods"]]
        cash_rows = []
        event_refs = {identifier: public_ref for public_ref, identifier in _event_ref_map(connection).items()}
        for row in reversed(_active_rows(connection, "cash_event", "effective_at_utc,cash_event_id")):
            cash_rows.append({"cash_event_ref": event_refs[row["cash_event_id"]], "event_type": row["event_type"], "account_label": account_labels[row["account_id"]], "related_account_label": None if row["related_account_id"] is None else account_labels[row["related_account_id"]], "cash_asset_label": asset_labels[row["cash_asset_id"]], "currency": row["currency"], "event_time_evidence": row["event_time_evidence"], "local_date": row["local_date"], "local_time": row["local_time"], "time_zone": row["time_zone"], "effective_at_utc": row["effective_at_utc"], "amount_decimal": row["amount_decimal"], "flow_classification": row["flow_classification"]})
        income_rows = [{"income_type": "interest", "account_label": account_labels[row["account_id"]], "cash_asset_label": asset_labels[row["cash_asset_id"]], "currency": row["currency"], "local_date": row["local_date"], "gross_income_decimal": row["gross_income_decimal"], "linked_cash_event": row["linked_cash_event_id"] is not None, "cash_balance_effect_created": False} for row in reversed(_active_rows(connection, "income_event", "local_date,income_event_id"))]
        counts = _counts(connection)
        history = _history(connection)
        return {"desktop_cash_coverage_read_model_version": 2, "status": "available", "schema_version": SCHEMA_VERSION, "period_count": counts[0], "cash_event_count": counts[1], "income_event_count": counts[2], "reconciliation_count": counts[3], "revision_count": _revision_count(connection), "receipt_count": len(history), "cash_coverage_state": "separate_not_read", "periods": periods, "cash_history": cash_rows, "income_history": income_rows, "receipt_history": history, **common}
    except CashCoverageV1Error:
        _abort("desktop_cash_coverage_store_invalid")
    finally:
        connection.close()


def apply_desktop_cash_coverage_reviewed_batch_v1(
    canonical_path: str | Path, data_space_path: str | Path, context_value: Any,
    reviewed_items: Any, confirmed_by_owner_at_utc: str, committed_at_utc: str,
) -> dict[str, Any]:
    """Applies many reviewed import candidates in one transaction (#184, linear booking).

    The single-command path previews, confirms and applies each command and validates the
    complete ledger several times per command, so a statement with thousands of movements
    grew quadratically. Here every command still gets its own attempt, evidence, receipt,
    facts and provenance, but the complete ledger is validated once after the last command.
    If that validation fails, nothing of the batch is committed. The owner confirmed the
    batch once in the Data app; ``confirmed_by_owner_at_utc`` records that moment. Before
    and after state fingerprints in the provenance refer to the batch as a whole.
    """
    committed = _utc(committed_at_utc)
    confirmed_at = _utc(confirmed_by_owner_at_utc)
    if not isinstance(reviewed_items, list) or not reviewed_items or len(reviewed_items) > 5000:
        _abort("desktop_cash_coverage_input_invalid")
    raw_commands: list[dict[str, Any]] = []
    for item in reviewed_items:
        entry = _strict(item, {"reviewed", "request_ref"})
        reviewed = _strict(entry["reviewed"], {"reviewed_cash_coverage_candidate_version", "source_candidate_fingerprint", "mapped_command"})
        if reviewed["reviewed_cash_coverage_candidate_version"] != 1 or not isinstance(reviewed["mapped_command"], Mapping):
            _abort("desktop_cash_coverage_input_invalid")
        if not isinstance(entry["request_ref"], str) or REQUEST.fullmatch(entry["request_ref"]) is None:
            _abort("desktop_cash_coverage_input_invalid")
        if reviewed["mapped_command"].get("action_type") not in REGULAR_ACTIONS:
            _abort("desktop_cash_coverage_input_invalid")
        raw_commands.append({**dict(reviewed["mapped_command"]), "request_ref": entry["request_ref"], "input_mode": "reviewed_import",
                             "source_candidate_fingerprint": _fingerprint(reviewed["source_candidate_fingerprint"])})
    return _commit_batch(canonical_path, data_space_path, context_value, raw_commands, confirmed_at, committed)


def _commit_batch(
    canonical_path: str | Path, data_space_path: str | Path, context_value: Any,
    raw_commands: list[dict[str, Any]], confirmed_at: str, committed: str,
) -> dict[str, Any]:
    """Der gemeinsame Schreibweg eines Stapels: geprueft importiert oder von Hand."""
    if len({command["request_ref"] for command in raw_commands}) != len(raw_commands):
        _abort("desktop_cash_coverage_input_invalid")
    context, initial, catalog = _catalog(canonical_path, context_value)
    canonical = Path(initial["path"])
    data_space = _owner_directory(data_space_path)
    area = _owner_directory(data_space / STORE_AREA, create=True)
    store = _store_path(data_space)
    with _WriterLock(area):
        with _CanonicalBarrier(data_space):
            if _sha_file(canonical) != initial["source_fingerprint"]:
                _abort("desktop_cash_coverage_canonical_changed")
            if not store.exists():
                if raw_commands[0].get("action_type") != "declare_coverage":
                    _abort("desktop_cash_coverage_store_invalid")
                _create_store(store, context, initial["created_at_utc"])
        connection = _open_store(store, context, read_only=False)
        try:
            before_payload = _current_payload(connection, catalog)
            before_state = _sha(before_payload)
            batch_fingerprint = _sha({"batch": [_sha(command) for command in raw_commands], "before": before_state,
                                      "context": _context_fingerprint(context), "confirmed_at": confirmed_at})
            applied: list[tuple[str, dict[str, Any]]] = []
            replayed = 0
            connection.execute("BEGIN IMMEDIATE")
            for raw in raw_commands:
                existing = connection.execute("SELECT payload_fingerprint FROM cash_coverage_command_receipt WHERE request_ref=?", (raw["request_ref"],)).fetchone()
                if existing is not None:
                    if existing[0] != _sha(raw):
                        _abort("desktop_cash_coverage_command_conflict")
                    replayed += 1
                    continue
                command = _command(raw, catalog, connection)
                confirmation = {"desktop_cash_coverage_batch_confirmation_version": 1, "batch_fingerprint": batch_fingerprint,
                                "request_ref": raw["request_ref"], "actor_id": context.actor_id, "confirmed_at_utc": confirmed_at}
                confirmation["confirmation_fingerprint"] = _sha(confirmation)
                preview_fingerprint = _sha({"batch_preview": batch_fingerprint, "request_ref": raw["request_ref"]})
                _insert_attempt(connection, raw, command, confirmation, {"preview_fingerprint": preview_fingerprint}, context, initial["source_fingerprint"], committed)
                command_id = "ccmd_" + _sha({"confirmation": confirmation["confirmation_fingerprint"], "request": raw["request_ref"]})[:32]
                connection.execute("INSERT INTO cash_coverage_command_receipt VALUES(?,?,?,?,?,?,?,?,?)", (
                    command_id, raw["request_ref"], "data_app", command["fact_action_type"], context.actor_id,
                    _sha(raw), initial["source_fingerprint"], confirmation["confirmation_fingerprint"], committed,
                ))
                _apply_candidate(connection, command, command_id, committed)
                applied.append((command_id, command))
            # One validation of the complete ledger for the whole batch.
            _validate_supersession_lineage(connection)
            after_payload = _current_payload(connection, catalog)
            _semantic(after_payload)
            after_state = _sha(after_payload)
            for command_id, command in applied:
                body = {
                    "command_id": command_id, "operation_type": command["operation_type"], "input_mode": command["input_mode"],
                    "source_candidate_fingerprint": command["source_candidate_fingerprint"],
                    "predecessor_command_id": None, "predecessor_set_fingerprint": None,
                    "before_state_fingerprint": before_state, "after_state_fingerprint": after_state,
                    "recovery_confirmation_fingerprint": None, "predecessor_preserved": 1,
                }
                provenance = {**body, "receipt_fingerprint": _sha(body)}
                connection.execute("INSERT INTO cash_coverage_command_provenance VALUES(?,?,?,?,?,?,?,?,?,?,?)", tuple(provenance[key] for key in (
                    "command_id", "operation_type", "input_mode", "source_candidate_fingerprint", "predecessor_command_id",
                    "predecessor_set_fingerprint", "before_state_fingerprint", "after_state_fingerprint",
                    "recovery_confirmation_fingerprint", "predecessor_preserved", "receipt_fingerprint")))
            _validate_provenance(connection)
            with _CanonicalBarrier(data_space):
                if _sha_file(canonical) != initial["source_fingerprint"]:
                    _abort("desktop_cash_coverage_canonical_changed")
                connection.commit()
            os.chmod(store, 0o600)
            return {"desktop_cash_coverage_batch_version": 1, "status": "committed", "applied_command_count": len(applied),
                    "replayed_command_count": replayed, "batch_fingerprint": batch_fingerprint,
                    "before_state_fingerprint": before_state, "after_state_fingerprint": after_state}
        except DesktopCashCoverageV1Error:
            if connection.in_transaction:
                connection.rollback()
            raise
        except (CashCoverageV1Error, sqlite3.Error):
            if connection.in_transaction:
                connection.rollback()
            _abort("desktop_cash_coverage_write_failed")
        finally:
            connection.close()


def _manual_batch_commands(commands: Any) -> list[dict[str, Any]]:
    """Ein kleiner Stapel regulaerer Handkommandos, die zusammen gelten sollen.

    Eine Zinsgutschrift sind zwei Fakten (Cash-Ereignis und Zins-Income), und eine
    erste Buchung auf einem Konto ohne Abdeckungszeitraum braucht dessen Erklaerung
    dazu. Einzeln bestaetigt waeren das zwei oder drei Vorgaenge fuer eine Buchung -
    und nach dem ersten ein Zwischenstand, den niemand gemeint hat (#419).
    """
    if not isinstance(commands, list) or not commands or len(commands) > 5:
        _abort("desktop_cash_coverage_input_invalid")
    result: list[dict[str, Any]] = []
    for item in commands:
        if not isinstance(item, Mapping) or item.get("action_type") not in REGULAR_ACTIONS:
            _abort("desktop_cash_coverage_input_invalid")
        if item.get("input_mode") != "manual_entry" or item.get("source_candidate_fingerprint") is not None:
            _abort("desktop_cash_coverage_input_invalid")
        if not isinstance(item.get("request_ref"), str) or REQUEST.fullmatch(item["request_ref"]) is None:
            _abort("desktop_cash_coverage_input_invalid")
        result.append(dict(item))
    if len({command["request_ref"] for command in result}) != len(result):
        _abort("desktop_cash_coverage_input_invalid")
    return result


def preview_desktop_cash_coverage_manual_batch_v1(
    canonical_path: str | Path, data_space_path: str | Path, context_value: Any, commands: Any,
) -> dict[str, Any]:
    """Was ein Handstapel aendern wuerde - gerechnet an einer Kopie im Speicher."""
    raw_commands = _manual_batch_commands(commands)
    try:
        context, snapshot, catalog = _catalog(canonical_path, context_value)
        data_space = _owner_directory(data_space_path)
        store = _store_path(data_space)
        memory = sqlite3.connect(":memory:", isolation_level=None)
        memory.row_factory = sqlite3.Row
        try:
            if store.exists():
                connection = _open_store(store, context, read_only=True)
                try:
                    connection.backup(memory)
                finally:
                    connection.close()
            else:
                if raw_commands[0]["action_type"] != "declare_coverage":
                    _abort("desktop_cash_coverage_store_invalid")
                memory.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
                memory.execute(
                    "INSERT INTO cash_coverage_store_binding VALUES(1,?,?,?,?,?)",
                    (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id, snapshot["created_at_utc"]),
                )
            memory.execute("PRAGMA foreign_keys=ON")
            before_payload = _current_payload(memory, {})
            before_state = _sha(before_payload)
            before_projection = _semantic(before_payload)
            committed = "2000-01-01T00:00:00Z"
            try:
                for raw in raw_commands:
                    if memory.execute("SELECT 1 FROM cash_coverage_command_receipt WHERE request_ref=?", (raw["request_ref"],)).fetchone() is not None:
                        _abort("desktop_cash_coverage_command_conflict")
                    command = _command(raw, catalog, memory)
                    marker = _sha({"request": raw["request_ref"], "preview": True})
                    memory.execute("INSERT INTO cash_coverage_confirmation_attempt VALUES(?,?,?,?,?)", (marker, raw["request_ref"], marker, committed, "attempted"))
                    command_id = "ccmd_" + marker[:32]
                    memory.execute("INSERT INTO cash_coverage_command_receipt VALUES(?,?,?,?,?,?,?,?,?)", (
                        command_id, raw["request_ref"], "data_app", command["fact_action_type"], context.actor_id,
                        _sha(raw), snapshot["source_fingerprint"], marker, committed,
                    ))
                    _apply_candidate(memory, command, command_id, committed)
                _validate_supersession_lineage(memory)
                after_projection = _semantic(_current_payload(memory, {}))
            except sqlite3.IntegrityError as error:
                _abort("desktop_cash_coverage_period_overlap" if "cash_coverage_period_overlap" in str(error) else "desktop_cash_coverage_input_invalid")
            except CashCoverageV1Error as error:
                _abort({
                    "cash_coverage_period_overlap": "desktop_cash_coverage_period_overlap",
                    "cash_coverage_mode_invalid": "desktop_cash_coverage_mode_invalid",
                    "cash_coverage_event_outside_period": "desktop_cash_coverage_event_outside_period",
                    "cash_coverage_reconciliation_mismatch": "desktop_cash_coverage_reconciliation_mismatch",
                    "cash_coverage_complete_opening_required": "desktop_cash_coverage_mode_invalid",
                    "cash_coverage_complete_reconciliation_required": "desktop_cash_coverage_mode_invalid",
                }.get(error.code, "desktop_cash_coverage_input_invalid"))
        finally:
            memory.close()
        body = {
            "desktop_cash_coverage_batch_preview_version": 1, "status": "ready_for_confirmation",
            "input_mode": "manual_entry", "command_count": len(raw_commands), "commands": raw_commands,
            "canonical_fingerprint": snapshot["source_fingerprint"], "cash_coverage_state_fingerprint": before_state,
            "projection_before": before_projection, "projection": after_projection,
            "confirmation_required": True, "one_attempt_only": True,
            "canonical_write": False, "asset_activity_write": False, "provider_access": False,
            "network_access": False, "private_data_access": False,
        }
        return {**body, "preview_fingerprint": _sha(body)}
    except DesktopCashCoverageV1Error:
        raise
    except Exception as error:
        raise DesktopCashCoverageV1Error("desktop_cash_coverage_boundary_failed") from error


def apply_desktop_cash_coverage_manual_batch_v1(
    canonical_path: str | Path, data_space_path: str | Path, context_value: Any, commands: Any,
    preview_fingerprint: Any, confirmed_by_owner_at_utc: str, committed_at_utc: str,
) -> dict[str, Any]:
    """Genau den vorab gezeigten Handstapel schreiben - ganz oder gar nicht."""
    committed = _utc(committed_at_utc)
    confirmed_at = _utc(confirmed_by_owner_at_utc)
    raw_commands = _manual_batch_commands(commands)
    if not isinstance(preview_fingerprint, str) or SHA.fullmatch(preview_fingerprint) is None:
        _abort("desktop_cash_coverage_confirmation_missing")
    # Ein bereits vollstaendig geschriebener Stapel wird vorgefunden, nicht wiederholt.
    try:
        context, _, _ = _catalog(canonical_path, context_value)
        store = _store_path(_owner_directory(data_space_path))
    except DesktopCashCoverageV1Error:
        raise
    already = 0
    if store.exists():
        connection = _open_store(store, context, read_only=True)
        try:
            for raw in raw_commands:
                existing = connection.execute("SELECT payload_fingerprint FROM cash_coverage_command_receipt WHERE request_ref=?", (raw["request_ref"],)).fetchone()
                if existing is not None:
                    if existing[0] != _sha(raw):
                        _abort("desktop_cash_coverage_command_conflict")
                    already += 1
        finally:
            connection.close()
    if already == len(raw_commands):
        return {"desktop_cash_coverage_batch_version": 1, "status": "already_committed", "applied_command_count": 0,
                "replayed_command_count": already, "batch_fingerprint": None,
                "before_state_fingerprint": None, "after_state_fingerprint": None}
    if already:
        # Ein Stapel wird in einer Transaktion geschrieben; ein Teil davon im
        # Speicher heisst, dass die Anforderungen anderswo schon verwendet wurden.
        _abort("desktop_cash_coverage_command_conflict")
    preview = preview_desktop_cash_coverage_manual_batch_v1(canonical_path, data_space_path, context_value, raw_commands)
    if preview["preview_fingerprint"] != preview_fingerprint:
        _abort("desktop_cash_coverage_preview_stale")
    return _commit_batch(canonical_path, data_space_path, context_value, raw_commands, confirmed_at, committed)


__all__ = [
    "DesktopCashCoverageResultV1", "DesktopCashCoverageV1Error",
    "apply_desktop_cash_coverage_manual_batch_v1", "preview_desktop_cash_coverage_manual_batch_v1",
    "desktop_cash_evidence_fingerprint_v1", "desktop_cash_evidence_kind_v1",
    "apply_desktop_cash_coverage_command_v1", "apply_desktop_cash_coverage_recovery_v1",
    "apply_desktop_cash_coverage_reviewed_batch_v1",
    "build_desktop_cash_coverage_confirmation_v1", "build_desktop_cash_coverage_recovery_confirmation_v1",
    "desktop_cash_coverage_error_codes_v1", "preview_desktop_cash_coverage_command_v1",
    "preview_desktop_cash_coverage_recovery_v1", "preview_desktop_reviewed_cash_coverage_candidate_v1",
    "read_desktop_cash_coverage_catalog_v1", "read_desktop_cash_coverage_exchange_projection_v1",
    "read_desktop_cash_coverage_recovery_candidates_v1", "read_desktop_cash_coverage_reviewed_import_state_v1",
    "read_desktop_cash_coverage_revision_candidates_v1", "read_desktop_cash_coverage_view_v1",
]
