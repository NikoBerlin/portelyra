"""Create-only, lossless Cash authority migration from schema 2900 to 2901."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
from typing import Any, Mapping
from urllib.parse import quote

from migrations.reference.desktop_cash_coverage_v1 import (
    SCHEMA_PATH,
    SCHEMA_VERSION,
    STORE_AREA,
    STORE_NAME,
    DesktopCashCoverageV1Error,
    _abort,
    _canonical,
    _catalog,
    _context_fingerprint,
    _current_payload,
    _expected_schema,
    _legacy_fact_projection,
    _open_store,
    _owner_directory,
    _owner_file,
    _rows_as_dicts,
    _semantic,
    _sha,
    _sha_file,
    _store_path,
    _utc,
    _validate_store,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _context,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE_SCHEMA = ROOT / "contracts" / "cash-coverage" / "v1" / "schema-2900.sql"
SOURCE_VERSION = 2900
CONFIRMATION_PREFIX = "ccmc_"
RECOVERY_CONFIRMATION_PREFIX = "ccmr_"
MAX_JSON_BYTES = 32_000_000
MIGRATION_FAILPOINTS = {None, "after_attempt", "after_target_build", "after_publish"}


@dataclass(frozen=True)
class CashCoverageStoreMigrationResultV1:
    status: str
    source_schema_version: int
    target_schema_version: int
    period_count: int
    cash_event_count: int
    income_event_count: int
    reconciliation_count: int
    predecessor_fact_bytes_preserved: bool
    legacy_time_evidence: str
    source_mutated: bool = False
    canonical_write: bool = False
    asset_activity_write: bool = False
    provider_access: bool = False
    network_access: bool = False


_EXPECTED_SOURCE_SCHEMA: tuple[tuple[Any, ...], ...] | None = None


def _source_signature(connection: sqlite3.Connection) -> tuple[tuple[Any, ...], ...]:
    return tuple(tuple(row) for row in connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type,name"
    ))


def _expected_source_schema() -> tuple[tuple[Any, ...], ...]:
    global _EXPECTED_SOURCE_SCHEMA
    if _EXPECTED_SOURCE_SCHEMA is None:
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(SOURCE_SCHEMA.read_text(encoding="utf-8"))
            _EXPECTED_SOURCE_SCHEMA = _source_signature(connection)
        except (OSError, sqlite3.Error):
            _abort("desktop_cash_coverage_migration_source_invalid")
        finally:
            connection.close()
    return _EXPECTED_SOURCE_SCHEMA


def _source_file(path_value: str | Path) -> Path:
    try:
        path = _owner_file(path_value, "desktop_cash_coverage_migration_source_invalid")
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_migration_source_invalid")
    if any(Path(str(path) + suffix).exists() for suffix in ("-journal", "-wal", "-shm")):
        _abort("desktop_cash_coverage_migration_source_invalid")
    return path


def _open_source(path_value: str | Path, context: DesktopProductAssetActivityContextV1) -> tuple[Path, sqlite3.Connection]:
    path = _source_file(path_value)
    connection: sqlite3.Connection | None = None
    try:
        uri = f"file:{quote(str(path))}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM cash_coverage_store_binding WHERE singleton_id=1"
        ).fetchall()
        if (
            connection.execute("PRAGMA user_version").fetchone()[0] != SOURCE_VERSION
            or _source_signature(connection) != _expected_source_schema()
            or len(binding) != 1
            or tuple(binding[0]) != (SOURCE_VERSION, context.tenant_id, context.user_id, context.data_space_id)
            or connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _abort("desktop_cash_coverage_migration_source_invalid")
        return path, connection
    except DesktopCashCoverageV1Error:
        if connection is not None:
            connection.close()
        raise
    except sqlite3.Error:
        if connection is not None:
            connection.close()
        _abort("desktop_cash_coverage_migration_source_invalid")


def _normalized_source_facts(connection: sqlite3.Connection) -> dict[str, Any]:
    events = _rows_as_dicts(connection, "SELECT * FROM cash_coverage_event ORDER BY cash_event_id")
    normalized_events = []
    for event in events:
        normalized_events.append({
            "cash_event_id": event["cash_event_id"], "event_type": event["event_type"],
            "portfolio_id": event["portfolio_id"], "account_id": event["account_id"],
            "related_account_id": event["related_account_id"], "cash_asset_id": event["cash_asset_id"],
            "currency": event["currency"], "event_time_evidence": "utc_only_legacy",
            "local_date": event["local_date"], "local_time": None, "time_zone": None,
            "effective_at_utc": event["effective_at_utc"], "amount_decimal": event["amount_decimal"],
            "flow_classification": event["flow_classification"], "command_id": event["command_id"],
            "committed_at_utc": event["committed_at_utc"],
        })
    return {
        "periods": _rows_as_dicts(connection, "SELECT * FROM cash_coverage_period ORDER BY coverage_id"),
        "cash_events": normalized_events,
        "income_events": _rows_as_dicts(connection, "SELECT * FROM cash_income_event ORDER BY income_event_id"),
        "reconciliations": _rows_as_dicts(connection, "SELECT * FROM cash_coverage_reconciliation ORDER BY reconciliation_id"),
    }


def _source_material(path_value: str | Path, context: DesktopProductAssetActivityContextV1) -> tuple[Path, sqlite3.Connection, dict[str, Any]]:
    path, connection = _open_source(path_value, context)
    source_fingerprint = _sha_file(path)
    facts = _normalized_source_facts(connection)
    attempts = _rows_as_dicts(connection, "SELECT * FROM cash_coverage_confirmation_attempt ORDER BY confirmation_fingerprint")
    commands = _rows_as_dicts(connection, "SELECT * FROM cash_coverage_command_receipt ORDER BY command_id")
    binding = dict(connection.execute("SELECT * FROM cash_coverage_store_binding WHERE singleton_id=1").fetchone())
    material = {
        "source_store_fingerprint": source_fingerprint,
        "binding": binding,
        "attempts": attempts,
        "commands": commands,
        "facts": facts,
        "legacy_attempt_set_fingerprint": _sha(attempts),
        "legacy_command_set_fingerprint": _sha(commands),
        "fact_projection_fingerprint": _sha(facts),
        "counts": {key: len(facts[key]) for key in ("periods", "cash_events", "income_events", "reconciliations")},
    }
    return path, connection, material


def preview_cash_coverage_store_migration_v2900_to_v2901(
    source_store_path: str | Path,
    target_data_space_path: str | Path,
    canonical_path: str | Path,
    context_value: Any,
) -> dict[str, Any]:
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    _, snapshot, catalog = _catalog(canonical_path, context)
    target_space = _owner_directory(target_data_space_path)
    target = _store_path(target_space)
    if target.exists() or target.is_symlink():
        _abort("desktop_cash_coverage_migration_target_exists")
    source, connection, material = _source_material(source_store_path, context)
    try:
        # Validate all old facts against the current catalog without changing their values.
        memory = sqlite3.connect(":memory:")
        memory.row_factory = sqlite3.Row
        try:
            memory.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            _copy_material(memory, material, confirmation_fingerprint="0" * 64, plan_fingerprint="0" * 64, migrated_at_utc="2000-01-01T00:00:00Z")
            _semantic(_current_payload(memory, catalog))
        finally:
            memory.close()
        trusted_body = {
            "cash_coverage_store_migration_preview_version": 1,
            "status": "ready_for_migration_confirmation",
            "source_schema_version": SOURCE_VERSION, "target_schema_version": SCHEMA_VERSION,
            "context_fingerprint": _context_fingerprint(context),
            "canonical_fingerprint": snapshot["source_fingerprint"],
            "source_store_fingerprint": material["source_store_fingerprint"],
            "legacy_attempt_set_fingerprint": material["legacy_attempt_set_fingerprint"],
            "legacy_command_set_fingerprint": material["legacy_command_set_fingerprint"],
            "fact_projection_fingerprint": material["fact_projection_fingerprint"],
            "period_count": material["counts"]["periods"],
            "cash_event_count": material["counts"]["cash_events"],
            "income_event_count": material["counts"]["income_events"],
            "reconciliation_count": material["counts"]["reconciliations"],
            "legacy_event_time_evidence": "utc_only_legacy",
            "source_read_only": True, "target_create_only": True,
            "confirmation_required": True,
        }
        trusted = {**trusted_body, "migration_plan_fingerprint": _sha(trusted_body)}
        public = {
            "cash_coverage_store_migration_public_preview_version": 1,
            "status": "ready_for_migration_confirmation",
            "source_schema_version": SOURCE_VERSION, "target_schema_version": SCHEMA_VERSION,
            "period_count": trusted["period_count"], "cash_event_count": trusted["cash_event_count"],
            "income_event_count": trusted["income_event_count"], "reconciliation_count": trusted["reconciliation_count"],
            "legacy_event_time_evidence": "utc_only_legacy", "source_read_only": True,
            "target_create_only": True, "confirmation_required": True,
            "path_exposed": False, "identity_exposed": False, "fingerprint_exposed": False,
            "canonical_write": False, "asset_activity_write": False,
            "provider_access": False, "network_access": False,
        }
        if _sha_file(source) != material["source_store_fingerprint"]:
            _abort("desktop_cash_coverage_migration_source_changed")
        return {"public_preview": public, "trusted_preview": trusted}
    finally:
        connection.close()


def build_cash_coverage_store_migration_confirmation_v1(
    trusted_preview: Mapping[str, Any],
    context_value: Any,
    confirmation_ref: str,
    issued_at_utc: str,
    expires_at_utc: str,
) -> dict[str, Any]:
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    issued = _utc(issued_at_utc, "desktop_cash_coverage_migration_confirmation_invalid")
    expires = _utc(expires_at_utc, "desktop_cash_coverage_migration_confirmation_invalid")
    body_without_fp = dict(trusted_preview) if isinstance(trusted_preview, Mapping) else {}
    plan = body_without_fp.pop("migration_plan_fingerprint", None)
    if (
        plan != _sha(body_without_fp)
        or trusted_preview.get("status") != "ready_for_migration_confirmation"
        or trusted_preview.get("context_fingerprint") != _context_fingerprint(context)
        or not isinstance(confirmation_ref, str)
        or len(confirmation_ref) != 37
        or not confirmation_ref.startswith(CONFIRMATION_PREFIX)
        or any(character not in "0123456789abcdef" for character in confirmation_ref[5:])
        or expires < issued
    ):
        _abort("desktop_cash_coverage_migration_confirmation_invalid")
    body = {
        "cash_coverage_store_migration_confirmation_version": 1,
        "authorization_scope": "cash_coverage_store_migration_once",
        "confirmation_ref": confirmation_ref, "migration_plan_fingerprint": plan,
        "context_fingerprint": _context_fingerprint(context),
        "issued_at_utc": issued, "expires_at_utc": expires, "confirmed": True,
        "source_mutation_authorized": False, "target_overwrite_authorized": False,
    }
    return {**body, "confirmation_fingerprint": _sha(body)}


def _copy_rows(connection: sqlite3.Connection, table: str, rows: list[dict[str, Any]], columns: tuple[str, ...]) -> None:
    if not rows:
        return
    placeholders = ",".join("?" for _ in columns)
    names = ",".join(columns)
    connection.executemany(
        f"INSERT INTO {table}({names}) VALUES({placeholders})",
        [tuple(row[column] for column in columns) for row in rows],
    )


def _copy_material(
    connection: sqlite3.Connection,
    material: dict[str, Any],
    *,
    confirmation_fingerprint: str,
    plan_fingerprint: str,
    migrated_at_utc: str,
    recovery_confirmation_fingerprint: str | None = None,
    recovery_plan_fingerprint: str | None = None,
) -> dict[str, Any]:
    binding = material["binding"]
    connection.execute(
        "INSERT INTO cash_coverage_store_binding VALUES(1,?,?,?,?,?)",
        (SCHEMA_VERSION, binding["tenant_id"], binding["user_id"], binding["data_space_id"], binding["created_at_utc"]),
    )
    _copy_rows(connection, "cash_coverage_confirmation_attempt", material["attempts"], ("confirmation_fingerprint", "request_ref", "preview_fingerprint", "attempted_at_utc", "attempt_status"))
    _copy_rows(connection, "cash_coverage_command_receipt", material["commands"], ("command_id", "request_ref", "writer_area", "action_type", "actor_id", "payload_fingerprint", "canonical_fingerprint", "confirmation_fingerprint", "committed_at_utc"))
    _copy_rows(connection, "cash_coverage_period", material["facts"]["periods"], ("coverage_id", "portfolio_id", "account_id", "cash_asset_id", "currency", "effective_from", "effective_to", "coverage_mode", "command_id", "committed_at_utc"))
    _copy_rows(connection, "cash_coverage_event", material["facts"]["cash_events"], ("cash_event_id", "event_type", "portfolio_id", "account_id", "related_account_id", "cash_asset_id", "currency", "event_time_evidence", "local_date", "local_time", "time_zone", "effective_at_utc", "amount_decimal", "flow_classification", "command_id", "committed_at_utc"))
    _copy_rows(connection, "cash_income_event", material["facts"]["income_events"], ("income_event_id", "income_type", "portfolio_id", "account_id", "cash_asset_id", "currency", "local_date", "gross_income_decimal", "linked_cash_event_id", "command_id", "committed_at_utc"))
    _copy_rows(connection, "cash_coverage_reconciliation", material["facts"]["reconciliations"], ("reconciliation_id", "portfolio_id", "account_id", "cash_asset_id", "currency", "as_of_date", "observed_balance_decimal", "evidence_fingerprint", "command_id", "committed_at_utc"))
    if recovery_confirmation_fingerprint is not None:
        if recovery_plan_fingerprint is None:
            _abort("desktop_cash_coverage_migration_failed")
        connection.execute(
            "INSERT INTO cash_coverage_schema_migration_recovery_attempt VALUES(?,?,?,?,?,?)",
            (recovery_confirmation_fingerprint, confirmation_fingerprint, plan_fingerprint,
             recovery_plan_fingerprint, migrated_at_utc, "attempted"),
        )
    migration_body = {
        "singleton_id": 1,
        "migration_id": "ccm_" + _sha({"source": material["source_store_fingerprint"], "plan": plan_fingerprint})[:32],
        "source_schema_version": SOURCE_VERSION, "target_schema_version": SCHEMA_VERSION,
        "source_store_fingerprint": material["source_store_fingerprint"],
        "migration_plan_fingerprint": plan_fingerprint,
        "legacy_attempt_set_fingerprint": material["legacy_attempt_set_fingerprint"],
        "legacy_command_set_fingerprint": material["legacy_command_set_fingerprint"],
        "source_fact_projection_fingerprint": material["fact_projection_fingerprint"],
        "target_fact_projection_fingerprint": material["fact_projection_fingerprint"],
        "period_count": material["counts"]["periods"], "cash_event_count": material["counts"]["cash_events"],
        "income_event_count": material["counts"]["income_events"], "reconciliation_count": material["counts"]["reconciliations"],
        "migrated_at_utc": migrated_at_utc, "confirmation_fingerprint": confirmation_fingerprint,
        "recovery_confirmation_fingerprint": recovery_confirmation_fingerprint,
    }
    receipt = {**migration_body, "receipt_fingerprint": _sha(migration_body)}
    columns = tuple(receipt)
    connection.execute(
        f"INSERT INTO cash_coverage_schema_migration_receipt({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
        tuple(receipt[column] for column in columns),
    )
    return receipt


def _attempt_path(area: Path, confirmation_fingerprint: str) -> Path:
    return area / f".migration-{confirmation_fingerprint}.attempt.json"


def _consume_confirmation(area: Path, confirmation: Mapping[str, Any], migrated_at_utc: str) -> None:
    payload = _canonical({
        "cash_coverage_store_migration_attempt_version": 1,
        "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
        "migration_plan_fingerprint": confirmation["migration_plan_fingerprint"],
        "attempted_at_utc": migrated_at_utc, "attempt_status": "attempted",
    }) + b"\n"
    if len(payload) > MAX_JSON_BYTES:
        _abort("desktop_cash_coverage_migration_confirmation_invalid")
    path = _attempt_path(area, confirmation["confirmation_fingerprint"])
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.geteuid():
            _abort("desktop_cash_coverage_migration_failed")
    except FileExistsError:
        _abort("desktop_cash_coverage_migration_confirmation_consumed")
    except DesktopCashCoverageV1Error:
        raise
    except OSError:
        _abort("desktop_cash_coverage_migration_failed")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    directory = os.open(area, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _strict_attempt(path: Path, code: str) -> dict[str, Any]:
    owner_path = _owner_file(path, code)
    descriptor: int | None = None
    try:
        descriptor = os.open(owner_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.geteuid():
            _abort(code)
        chunks: list[bytes] = []
        remaining = MAX_JSON_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
    except DesktopCashCoverageV1Error:
        raise
    except OSError:
        _abort(code)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not raw or len(raw) > MAX_JSON_BYTES or not raw.endswith(b"\n"):
        _abort(code)

    def reject_constant(_: str) -> None:
        raise ValueError("non_finite")

    def closed_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate")
            result[key] = item
        return result

    try:
        value = json.loads(raw[:-1].decode("utf-8"), parse_constant=reject_constant, object_pairs_hook=closed_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _abort(code)
    if not isinstance(value, dict) or raw != _canonical(value) + b"\n":
        _abort(code)
    return value


def _original_attempt(area: Path, confirmation: Mapping[str, Any], plan_fingerprint: str) -> dict[str, Any]:
    value = _strict_attempt(_attempt_path(area, confirmation["confirmation_fingerprint"]), "desktop_cash_coverage_migration_recovery_invalid")
    if set(value) != {
        "cash_coverage_store_migration_attempt_version", "confirmation_fingerprint",
        "migration_plan_fingerprint", "attempted_at_utc", "attempt_status",
    } or value != {
        "cash_coverage_store_migration_attempt_version": 1,
        "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
        "migration_plan_fingerprint": plan_fingerprint,
        "attempted_at_utc": value.get("attempted_at_utc"),
        "attempt_status": "attempted",
    }:
        _abort("desktop_cash_coverage_migration_recovery_invalid")
    _utc(value["attempted_at_utc"], "desktop_cash_coverage_migration_recovery_invalid")
    return value


def _migration_recovery_attempt_path(area: Path, confirmation_fingerprint: str) -> Path:
    return area / f".migration-recovery-{confirmation_fingerprint}.attempt.json"


def _consume_migration_recovery_confirmation(
    area: Path, confirmation: Mapping[str, Any], original_confirmation_fingerprint: str,
    plan_fingerprint: str, attempted_at_utc: str,
) -> None:
    value = {
        "cash_coverage_store_migration_recovery_attempt_version": 1,
        "recovery_confirmation_fingerprint": confirmation["recovery_confirmation_fingerprint"],
        "original_confirmation_fingerprint": original_confirmation_fingerprint,
        "migration_plan_fingerprint": plan_fingerprint,
        "recovery_plan_fingerprint": confirmation["recovery_plan_fingerprint"],
        "attempted_at_utc": attempted_at_utc, "attempt_status": "attempted",
    }
    payload = _canonical(value) + b"\n"
    path = _migration_recovery_attempt_path(area, confirmation["recovery_confirmation_fingerprint"])
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        offset = 0
        while offset < len(payload):
            offset += os.write(descriptor, payload[offset:])
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.geteuid():
            _abort("desktop_cash_coverage_migration_failed")
    except FileExistsError:
        existing = _strict_attempt(path, "desktop_cash_coverage_migration_recovery_confirmation_consumed")
        if existing != value:
            _abort("desktop_cash_coverage_migration_recovery_confirmation_consumed")
        return
    except DesktopCashCoverageV1Error:
        raise
    except OSError:
        _abort("desktop_cash_coverage_migration_failed")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    directory = os.open(area, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _verify_confirmation(
    value: Mapping[str, Any],
    trusted: Mapping[str, Any],
    context: DesktopProductAssetActivityContextV1,
    migrated: str,
    *,
    enforce_window: bool = True,
) -> dict[str, Any]:
    fields = {
        "cash_coverage_store_migration_confirmation_version", "authorization_scope", "confirmation_ref",
        "migration_plan_fingerprint", "context_fingerprint", "issued_at_utc", "expires_at_utc", "confirmed",
        "source_mutation_authorized", "target_overwrite_authorized", "confirmation_fingerprint",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        _abort("desktop_cash_coverage_migration_confirmation_invalid")
    result = dict(value)
    fingerprint = result.pop("confirmation_fingerprint")
    if (
        fingerprint != _sha(result)
        or result["cash_coverage_store_migration_confirmation_version"] != 1
        or result["authorization_scope"] != "cash_coverage_store_migration_once"
        or result["migration_plan_fingerprint"] != trusted.get("migration_plan_fingerprint")
        or result["context_fingerprint"] != _context_fingerprint(context)
        or not isinstance(result["confirmation_ref"], str)
        or len(result["confirmation_ref"]) != 37
        or not result["confirmation_ref"].startswith(CONFIRMATION_PREFIX)
        or any(character not in "0123456789abcdef" for character in result["confirmation_ref"][5:])
        or result["confirmed"] is not True
        or result["source_mutation_authorized"] is not False
        or result["target_overwrite_authorized"] is not False
    ):
        _abort("desktop_cash_coverage_migration_confirmation_invalid")
    issued = _utc(result["issued_at_utc"], "desktop_cash_coverage_migration_confirmation_invalid")
    expires = _utc(result["expires_at_utc"], "desktop_cash_coverage_migration_confirmation_invalid")
    if enforce_window and (migrated < issued or migrated > expires):
        _abort("desktop_cash_coverage_migration_confirmation_invalid")
    return {**result, "confirmation_fingerprint": fingerprint}


def preview_cash_coverage_store_migration_recovery_v1(
    source_store_path: str | Path, target_data_space_path: str | Path, canonical_path: str | Path,
    context_value: Any, trusted_preview: Mapping[str, Any], original_confirmation_value: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    trusted_body = dict(trusted_preview) if isinstance(trusted_preview, Mapping) else {}
    plan_fingerprint = trusted_body.pop("migration_plan_fingerprint", None)
    if plan_fingerprint != _sha(trusted_body) or trusted_preview.get("context_fingerprint") != _context_fingerprint(context):
        _abort("desktop_cash_coverage_migration_recovery_invalid")
    original = _verify_confirmation(
        original_confirmation_value, trusted_preview, context, "2000-01-01T00:00:00Z", enforce_window=False
    )
    target_space = _owner_directory(target_data_space_path)
    target = _store_path(target_space)
    existing = _existing_target_result(target, context, trusted_preview, original)
    if existing is not None:
        return {
            "public_preview": {
                "cash_coverage_store_migration_recovery_public_preview_version": 1,
                "status": "already_migrated", "recovery_ref": "ccmrec_" + _sha({"plan": plan_fingerprint})[:32],
                "source_schema_version": SOURCE_VERSION, "target_schema_version": SCHEMA_VERSION,
                "recovery_reason": "target_receipt_already_matches",
                "confirmation_required": False, "automatic_retry": False, "target_write_required": False,
                "path_exposed": False, "identity_exposed": False, "fingerprint_exposed": False,
                "canonical_write": False, "asset_activity_write": False, "provider_access": False, "network_access": False,
            },
            "trusted_preview": None,
        }
    area = _owner_directory(target_space / STORE_AREA)
    attempt = _original_attempt(area, original, plan_fingerprint)
    current = preview_cash_coverage_store_migration_v2900_to_v2901(
        source_store_path, target_space, canonical_path, context
    )
    if current["trusted_preview"] != dict(trusted_preview):
        _abort("desktop_cash_coverage_migration_source_changed")
    recovery_ref = "ccmrec_" + _sha({
        "confirmation": original["confirmation_fingerprint"], "attempt": attempt,
        "plan": plan_fingerprint,
    })[:32]
    trusted_recovery_body = {
        "cash_coverage_store_migration_recovery_preview_version": 1,
        "status": "ready_for_migration_recovery_confirmation", "recovery_ref": recovery_ref,
        "source_schema_version": SOURCE_VERSION, "target_schema_version": SCHEMA_VERSION,
        "context_fingerprint": _context_fingerprint(context),
        "canonical_fingerprint": trusted_preview["canonical_fingerprint"],
        "source_store_fingerprint": trusted_preview["source_store_fingerprint"],
        "migration_plan_fingerprint": plan_fingerprint,
        "original_confirmation_fingerprint": original["confirmation_fingerprint"],
        "original_attempted_at_utc": attempt["attempted_at_utc"],
        "recovery_reason": "confirmation_consumed_target_absent",
        "confirmation_required": True, "automatic_retry": False, "target_create_only": True,
    }
    trusted_recovery = {
        **trusted_recovery_body,
        "recovery_plan_fingerprint": _sha(trusted_recovery_body),
    }
    public = {
        "cash_coverage_store_migration_recovery_public_preview_version": 1,
        "status": "ready_for_migration_recovery_confirmation", "recovery_ref": recovery_ref,
        "source_schema_version": SOURCE_VERSION, "target_schema_version": SCHEMA_VERSION,
        "recovery_reason": "confirmation_consumed_target_absent",
        "confirmation_required": True, "automatic_retry": False, "target_write_required": True,
        "path_exposed": False, "identity_exposed": False, "fingerprint_exposed": False,
        "canonical_write": False, "asset_activity_write": False, "provider_access": False, "network_access": False,
    }
    return {"public_preview": public, "trusted_preview": trusted_recovery}


def build_cash_coverage_store_migration_recovery_confirmation_v1(
    trusted_recovery_preview: Mapping[str, Any], context_value: Any, confirmation_ref: str,
    issued_at_utc: str, expires_at_utc: str,
) -> dict[str, Any]:
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    issued = _utc(issued_at_utc, "desktop_cash_coverage_migration_recovery_confirmation_invalid")
    expires = _utc(expires_at_utc, "desktop_cash_coverage_migration_recovery_confirmation_invalid")
    body = dict(trusted_recovery_preview) if isinstance(trusted_recovery_preview, Mapping) else {}
    recovery_plan = body.pop("recovery_plan_fingerprint", None)
    if (
        recovery_plan != _sha(body)
        or trusted_recovery_preview.get("status") != "ready_for_migration_recovery_confirmation"
        or trusted_recovery_preview.get("context_fingerprint") != _context_fingerprint(context)
        or not isinstance(confirmation_ref, str) or len(confirmation_ref) != 37
        or not confirmation_ref.startswith(RECOVERY_CONFIRMATION_PREFIX)
        or any(character not in "0123456789abcdef" for character in confirmation_ref[5:])
        or expires < issued
    ):
        _abort("desktop_cash_coverage_migration_recovery_confirmation_invalid")
    confirmation_body = {
        "cash_coverage_store_migration_recovery_confirmation_version": 1,
        "authorization_scope": "cash_coverage_store_migration_recovery_once",
        "confirmation_ref": confirmation_ref, "recovery_ref": trusted_recovery_preview["recovery_ref"],
        "migration_plan_fingerprint": trusted_recovery_preview["migration_plan_fingerprint"],
        "recovery_plan_fingerprint": recovery_plan,
        "original_confirmation_fingerprint": trusted_recovery_preview["original_confirmation_fingerprint"],
        "context_fingerprint": _context_fingerprint(context), "issued_at_utc": issued,
        "expires_at_utc": expires, "confirmed": True, "automatic_retry_authorized": False,
        "source_mutation_authorized": False, "target_overwrite_authorized": False,
    }
    return {**confirmation_body, "recovery_confirmation_fingerprint": _sha(confirmation_body)}


def _verify_migration_recovery_confirmation(
    value: Mapping[str, Any], trusted_recovery: Mapping[str, Any], context: DesktopProductAssetActivityContextV1,
    recovered_at_utc: str, *, enforce_window: bool = True,
) -> dict[str, Any]:
    fields = {
        "cash_coverage_store_migration_recovery_confirmation_version", "authorization_scope", "confirmation_ref",
        "recovery_ref", "migration_plan_fingerprint", "recovery_plan_fingerprint",
        "original_confirmation_fingerprint", "context_fingerprint", "issued_at_utc", "expires_at_utc",
        "confirmed", "automatic_retry_authorized", "source_mutation_authorized", "target_overwrite_authorized",
        "recovery_confirmation_fingerprint",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        _abort("desktop_cash_coverage_migration_recovery_confirmation_invalid")
    body = dict(value); fingerprint = body.pop("recovery_confirmation_fingerprint")
    if (
        fingerprint != _sha(body)
        or body["cash_coverage_store_migration_recovery_confirmation_version"] != 1
        or body["authorization_scope"] != "cash_coverage_store_migration_recovery_once"
        or body["recovery_ref"] != trusted_recovery.get("recovery_ref")
        or body["migration_plan_fingerprint"] != trusted_recovery.get("migration_plan_fingerprint")
        or body["recovery_plan_fingerprint"] != trusted_recovery.get("recovery_plan_fingerprint")
        or body["original_confirmation_fingerprint"] != trusted_recovery.get("original_confirmation_fingerprint")
        or body["context_fingerprint"] != _context_fingerprint(context)
        or not isinstance(body["confirmation_ref"], str) or len(body["confirmation_ref"]) != 37
        or not body["confirmation_ref"].startswith(RECOVERY_CONFIRMATION_PREFIX)
        or any(character not in "0123456789abcdef" for character in body["confirmation_ref"][5:])
        or body["confirmed"] is not True or body["automatic_retry_authorized"] is not False
        or body["source_mutation_authorized"] is not False or body["target_overwrite_authorized"] is not False
    ):
        _abort("desktop_cash_coverage_migration_recovery_confirmation_invalid")
    issued = _utc(body["issued_at_utc"], "desktop_cash_coverage_migration_recovery_confirmation_invalid")
    expires = _utc(body["expires_at_utc"], "desktop_cash_coverage_migration_recovery_confirmation_invalid")
    if enforce_window and (recovered_at_utc < issued or recovered_at_utc > expires):
        _abort("desktop_cash_coverage_migration_recovery_confirmation_invalid")
    return {**body, "recovery_confirmation_fingerprint": fingerprint}


def _existing_target_result(target: Path, context: DesktopProductAssetActivityContextV1, trusted: Mapping[str, Any], confirmation: Mapping[str, Any], recovery_confirmation: Mapping[str, Any] | None = None) -> CashCoverageStoreMigrationResultV1 | None:
    if not target.exists():
        return None
    try:
        connection = _open_store(target, context, read_only=True)
    except DesktopCashCoverageV1Error:
        _abort("desktop_cash_coverage_migration_target_exists")
    try:
        row = connection.execute("SELECT * FROM cash_coverage_schema_migration_receipt WHERE singleton_id=1").fetchone()
        expected_recovery = None if recovery_confirmation is None else recovery_confirmation.get("recovery_confirmation_fingerprint")
        if (row is None or row["migration_plan_fingerprint"] != trusted.get("migration_plan_fingerprint")
                or row["confirmation_fingerprint"] != confirmation.get("confirmation_fingerprint")
                or (recovery_confirmation is not None and row["recovery_confirmation_fingerprint"] != expected_recovery)):
            _abort("desktop_cash_coverage_migration_target_exists")
        return CashCoverageStoreMigrationResultV1(
            "already_migrated", SOURCE_VERSION, SCHEMA_VERSION,
            row["period_count"], row["cash_event_count"], row["income_event_count"], row["reconciliation_count"],
            True, "utc_only_legacy",
        )
    finally:
        connection.close()


def apply_cash_coverage_store_migration_v2900_to_v2901(
    source_store_path: str | Path,
    target_data_space_path: str | Path,
    canonical_path: str | Path,
    context_value: Any,
    trusted_preview: Mapping[str, Any],
    confirmation_value: Mapping[str, Any],
    migrated_at_utc: str,
    *, failpoint: str | None = None,
) -> CashCoverageStoreMigrationResultV1:
    migrated = _utc(migrated_at_utc, "desktop_cash_coverage_migration_confirmation_invalid")
    if failpoint not in MIGRATION_FAILPOINTS:
        _abort("desktop_cash_coverage_input_invalid")
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    if not isinstance(trusted_preview, Mapping) or not isinstance(confirmation_value, Mapping):
        _abort("desktop_cash_coverage_migration_confirmation_invalid")
    trusted_body = dict(trusted_preview)
    plan_fingerprint = trusted_body.pop("migration_plan_fingerprint", None)
    if plan_fingerprint != _sha(trusted_body) or trusted_preview.get("context_fingerprint") != _context_fingerprint(context):
        _abort("desktop_cash_coverage_migration_confirmation_invalid")
    target_space = _owner_directory(target_data_space_path)
    target = _store_path(target_space)
    confirmed = _verify_confirmation(
        confirmation_value, trusted_preview, context, migrated, enforce_window=False
    )
    replay = _existing_target_result(target, context, trusted_preview, confirmed)
    if replay is not None:
        return replay
    confirmed = _verify_confirmation(confirmation_value, trusted_preview, context, migrated)
    preview_now = preview_cash_coverage_store_migration_v2900_to_v2901(source_store_path, target_space, canonical_path, context)
    if preview_now["trusted_preview"] != dict(trusted_preview):
        _abort("desktop_cash_coverage_migration_source_changed")
    source, source_connection, material = _source_material(source_store_path, context)
    area = _owner_directory(target_space / STORE_AREA, create=True)
    if target.exists() or target.is_symlink():
        source_connection.close()
        _abort("desktop_cash_coverage_migration_target_exists")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{STORE_NAME}.migration-", dir=area)
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink()
    try:
        previous = os.umask(0o077)
        try:
            target_connection = sqlite3.connect(temporary)
        finally:
            os.umask(previous)
        target_connection.row_factory = sqlite3.Row
        try:
            target_connection.execute("PRAGMA foreign_keys=ON")
            target_connection.execute("PRAGMA journal_mode=DELETE")
            target_connection.execute("PRAGMA synchronous=FULL")
            target_connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            target_connection.execute("BEGIN IMMEDIATE")
            _copy_material(
                target_connection, material,
                confirmation_fingerprint=confirmed["confirmation_fingerprint"],
                plan_fingerprint=plan_fingerprint,
                migrated_at_utc=migrated,
            )
            target_connection.commit()
            _validate_store(target_connection, context)
            _, _, catalog = _catalog(canonical_path, context)
            _semantic(_current_payload(target_connection, catalog))
            target_legacy_commands = {
                row["command_id"] for row in target_connection.execute(
                    "SELECT receipt.command_id FROM cash_coverage_command_receipt receipt LEFT JOIN cash_coverage_command_provenance provenance USING(command_id) WHERE provenance.command_id IS NULL"
                )
            }
            if _sha(_legacy_fact_projection(target_connection, target_legacy_commands)) != material["fact_projection_fingerprint"]:
                _abort("desktop_cash_coverage_migration_failed")
        finally:
            target_connection.close()
        if _sha_file(source) != material["source_store_fingerprint"]:
            _abort("desktop_cash_coverage_migration_source_changed")
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        if failpoint == "after_target_build":
            _abort("synthetic_desktop_cash_coverage_failpoint")
        _consume_confirmation(area, confirmed, migrated)
        if failpoint == "after_attempt":
            _abort("synthetic_desktop_cash_coverage_failpoint")
        try:
            os.link(temporary, target)
        except FileExistsError:
            _abort("desktop_cash_coverage_migration_target_exists")
        os.chmod(target, 0o600)
        directory = os.open(area, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if failpoint == "after_publish":
            _abort("synthetic_desktop_cash_coverage_failpoint")
        return CashCoverageStoreMigrationResultV1(
            "migrated", SOURCE_VERSION, SCHEMA_VERSION,
            material["counts"]["periods"], material["counts"]["cash_events"],
            material["counts"]["income_events"], material["counts"]["reconciliations"],
            True, "utc_only_legacy",
        )
    except DesktopCashCoverageV1Error:
        raise
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
        _abort("desktop_cash_coverage_migration_failed")
    finally:
        source_connection.close()
        temporary.unlink(missing_ok=True)


def apply_cash_coverage_store_migration_recovery_v1(
    source_store_path: str | Path, target_data_space_path: str | Path, canonical_path: str | Path,
    context_value: Any, trusted_preview: Mapping[str, Any], original_confirmation_value: Mapping[str, Any],
    trusted_recovery_preview: Mapping[str, Any], recovery_confirmation_value: Mapping[str, Any],
    recovered_at_utc: str, *, failpoint: str | None = None,
) -> CashCoverageStoreMigrationResultV1:
    recovered = _utc(recovered_at_utc, "desktop_cash_coverage_migration_recovery_confirmation_invalid")
    if failpoint not in MIGRATION_FAILPOINTS:
        _abort("desktop_cash_coverage_input_invalid")
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("desktop_cash_coverage_context_invalid")
    trusted_body = dict(trusted_preview) if isinstance(trusted_preview, Mapping) else {}
    plan_fingerprint = trusted_body.pop("migration_plan_fingerprint", None)
    recovery_body = dict(trusted_recovery_preview) if isinstance(trusted_recovery_preview, Mapping) else {}
    recovery_plan_fingerprint = recovery_body.pop("recovery_plan_fingerprint", None)
    if (
        plan_fingerprint != _sha(trusted_body)
        or recovery_plan_fingerprint != _sha(recovery_body)
        or trusted_preview.get("context_fingerprint") != _context_fingerprint(context)
        or trusted_recovery_preview.get("context_fingerprint") != _context_fingerprint(context)
        or trusted_recovery_preview.get("migration_plan_fingerprint") != plan_fingerprint
    ):
        _abort("desktop_cash_coverage_migration_recovery_invalid")
    original = _verify_confirmation(
        original_confirmation_value, trusted_preview, context, recovered, enforce_window=False
    )
    if trusted_recovery_preview.get("original_confirmation_fingerprint") != original["confirmation_fingerprint"]:
        _abort("desktop_cash_coverage_migration_recovery_invalid")
    recovery_confirmation = _verify_migration_recovery_confirmation(
        recovery_confirmation_value, trusted_recovery_preview, context, recovered, enforce_window=False
    )
    target_space = _owner_directory(target_data_space_path)
    target = _store_path(target_space)
    replay = _existing_target_result(target, context, trusted_preview, original, recovery_confirmation)
    if replay is not None:
        return replay
    recovery_confirmation = _verify_migration_recovery_confirmation(
        recovery_confirmation_value, trusted_recovery_preview, context, recovered
    )
    area = _owner_directory(target_space / STORE_AREA)
    _original_attempt(area, original, plan_fingerprint)
    current_recovery = preview_cash_coverage_store_migration_recovery_v1(
        source_store_path, target_space, canonical_path, context, trusted_preview, original
    )
    if current_recovery["trusted_preview"] != dict(trusted_recovery_preview):
        _abort("desktop_cash_coverage_migration_recovery_stale")
    source, source_connection, material = _source_material(source_store_path, context)
    if target.exists() or target.is_symlink():
        source_connection.close()
        _abort("desktop_cash_coverage_migration_target_exists")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{STORE_NAME}.migration-recovery-", dir=area)
    os.close(descriptor); temporary = Path(temporary_name); temporary.unlink()
    try:
        previous = os.umask(0o077)
        try:
            target_connection = sqlite3.connect(temporary)
        finally:
            os.umask(previous)
        target_connection.row_factory = sqlite3.Row
        try:
            target_connection.execute("PRAGMA foreign_keys=ON")
            target_connection.execute("PRAGMA journal_mode=DELETE")
            target_connection.execute("PRAGMA synchronous=FULL")
            target_connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            target_connection.execute("BEGIN IMMEDIATE")
            _copy_material(
                target_connection, material,
                confirmation_fingerprint=original["confirmation_fingerprint"],
                plan_fingerprint=plan_fingerprint, migrated_at_utc=recovered,
                recovery_confirmation_fingerprint=recovery_confirmation["recovery_confirmation_fingerprint"],
                recovery_plan_fingerprint=recovery_plan_fingerprint,
            )
            target_connection.commit()
            _validate_store(target_connection, context)
            _, _, catalog = _catalog(canonical_path, context)
            _semantic(_current_payload(target_connection, catalog))
            target_legacy_commands = {
                row["command_id"] for row in target_connection.execute(
                    "SELECT receipt.command_id FROM cash_coverage_command_receipt receipt LEFT JOIN cash_coverage_command_provenance provenance USING(command_id) WHERE provenance.command_id IS NULL"
                )
            }
            if _sha(_legacy_fact_projection(target_connection, target_legacy_commands)) != material["fact_projection_fingerprint"]:
                _abort("desktop_cash_coverage_migration_failed")
        finally:
            target_connection.close()
        if _sha_file(source) != material["source_store_fingerprint"]:
            _abort("desktop_cash_coverage_migration_source_changed")
        os.chmod(temporary, 0o600)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        if failpoint == "after_target_build":
            _abort("synthetic_desktop_cash_coverage_failpoint")
        _consume_migration_recovery_confirmation(
            area, recovery_confirmation, original["confirmation_fingerprint"], plan_fingerprint, recovered
        )
        if failpoint == "after_attempt":
            _abort("synthetic_desktop_cash_coverage_failpoint")
        try:
            os.link(temporary, target)
        except FileExistsError:
            _abort("desktop_cash_coverage_migration_target_exists")
        os.chmod(target, 0o600)
        directory = os.open(area, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        if failpoint == "after_publish":
            _abort("synthetic_desktop_cash_coverage_failpoint")
        return CashCoverageStoreMigrationResultV1(
            "recovered_migrated", SOURCE_VERSION, SCHEMA_VERSION,
            material["counts"]["periods"], material["counts"]["cash_events"],
            material["counts"]["income_events"], material["counts"]["reconciliations"],
            True, "utc_only_legacy",
        )
    except DesktopCashCoverageV1Error:
        raise
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
        _abort("desktop_cash_coverage_migration_failed")
    finally:
        source_connection.close()
        temporary.unlink(missing_ok=True)


__all__ = [
    "CashCoverageStoreMigrationResultV1",
    "apply_cash_coverage_store_migration_recovery_v1",
    "apply_cash_coverage_store_migration_v2900_to_v2901",
    "build_cash_coverage_store_migration_confirmation_v1",
    "build_cash_coverage_store_migration_recovery_confirmation_v1",
    "preview_cash_coverage_store_migration_recovery_v1",
    "preview_cash_coverage_store_migration_v2900_to_v2901",
]
