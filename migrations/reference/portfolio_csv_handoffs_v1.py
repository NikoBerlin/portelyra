#!/usr/bin/env python3
"""Separate owner-confirmed domain handoffs for a staged Portfolio CSV bundle.

There is deliberately no multi-domain apply function. Catalog and coupled Transaction
facts have separate canonical transactions. Asset Activity is handed to the existing
persistent Draft writer. Cash Coverage is handed to the existing reviewed-candidate
boundary and never written by this module.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Callable, Mapping

from migrations.reference.desktop_activity_draft_v1 import (
    DesktopActivityDraftV1Error,
    create_or_reuse_tolerant_csv_activity_draft_v1,
)
from migrations.reference.desktop_cash_coverage_v1 import (
    DesktopCashCoverageV1Error,
    read_desktop_cash_coverage_reviewed_import_state_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _canonical_snapshot,
    _context_fingerprint as _product_context_fingerprint,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.portfolio_csv_exchange_v1 import (
    AREA,
    PortfolioCsvContextV1,
    PortfolioCsvExchangeV1Error,
    _context as _exchange_context,
    _context_fp,
    _owner_directory,
    _preview_portfolio_csv_import_v1,
    _regular_file,
    _sha,
)

CONTRACT_VERSION = 1
MAX_JSON_BYTES = 32_000_000
DOMAINS = ("catalog", "coupled_transaction", "asset_activity", "cash_coverage")
DOMAIN_RECORD_KINDS = {
    "catalog": frozenset({"portfolio", "account", "asset", "provider_mapping"}),
    "coupled_transaction": frozenset({"coupled_transaction", "coupled_posting"}),
    "asset_activity": frozenset({"asset_activity", "fifo_order_evidence"}),
    "cash_coverage": frozenset({"cash_coverage_period", "cash_event", "cash_interest_income", "cash_reconciliation"}),
}
STAGED = re.compile(r"^imp_[a-f0-9]{24}$")
HANDOFF_REF = re.compile(r"^portfolio_handoff_[a-f0-9]{32}$")
RECOVERY_REF = re.compile(r"^portfolio_handoff_recovery_[a-f0-9]{32}$")
CONFIRMATION_REF = re.compile(r"^pchc_[a-f0-9]{32}$")
RECOVERY_CONFIRMATION_REF = re.compile(r"^pchr_[a-f0-9]{32}$")
CANDIDATE_REF = re.compile(r"^portfolio_cash_candidate_[a-f0-9]{24}$")
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
SHA = re.compile(r"^[a-f0-9]{64}$")
FAILPOINTS = {None, "after_attempt", "after_first_effect", "after_effect", "after_receipt"}
FAILURE_CODES = frozenset({
    "portfolio_csv_handoff_context_invalid", "portfolio_csv_handoff_staged_import_invalid",
    "portfolio_csv_handoff_domain_invalid", "portfolio_csv_handoff_dependency_missing",
    "portfolio_csv_handoff_plan_stale", "portfolio_csv_handoff_confirmation_invalid",
    "portfolio_csv_handoff_confirmation_expired", "portfolio_csv_handoff_confirmation_consumed",
    "portfolio_csv_handoff_effect_conflict", "portfolio_csv_handoff_lock_unavailable",
    "portfolio_csv_handoff_write_failed", "portfolio_csv_handoff_recovery_missing",
    "portfolio_csv_handoff_recovery_invalid", "portfolio_csv_handoff_recovery_stale",
    "portfolio_csv_handoff_recovery_confirmation_invalid",
    "portfolio_csv_handoff_recovery_confirmation_consumed",
    "portfolio_csv_handoff_cash_candidate_invalid", "synthetic_portfolio_csv_handoff_failpoint",
})


class PortfolioCsvHandoffV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("portfolio_csv_handoff_error_unregistered")
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise PortfolioCsvHandoffV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        payload = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        _abort("portfolio_csv_handoff_staged_import_invalid")
    if len(payload) + 1 > MAX_JSON_BYTES:
        _abort("portfolio_csv_handoff_staged_import_invalid")
    return payload


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _utc(value: Any, code: str) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort(code)
    try:
        if datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            _abort(code)
    except ValueError:
        _abort(code)
    return value


def _context(value: Any) -> PortfolioCsvContextV1:
    try:
        return _exchange_context(value)
    except PortfolioCsvExchangeV1Error:
        _abort("portfolio_csv_handoff_context_invalid")


def _activity_context(context: PortfolioCsvContextV1) -> DesktopProductAssetActivityContextV1:
    return DesktopProductAssetActivityContextV1(
        context.tenant_id, context.user_id, context.data_space_id, context.actor_id, context.role
    )


def _handoff_owner_file(path: Path, code: str) -> Path:
    try:
        info = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError:
        _abort(code)
    if (not path.is_absolute() or path.is_symlink() or resolved != path or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_JSON_BYTES):
        _abort(code)
    return path


def _json_file(path: Path, code: str) -> dict[str, Any]:
    descriptor: int | None = None
    try:
        path = _handoff_owner_file(path, code)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > MAX_JSON_BYTES):
            _abort(code)
        raw = bytearray()
        while len(raw) <= MAX_JSON_BYTES:
            chunk = os.read(descriptor, min(1_048_576, MAX_JSON_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
        raw = bytes(raw)
        if len(raw) > MAX_JSON_BYTES or not raw.endswith(b"\n") or raw.count(b"\n") != 1:
            _abort(code)
        value = json.loads(raw[:-1].decode("utf-8"), parse_constant=lambda _: _abort(code))
    except PortfolioCsvHandoffV1Error:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, PortfolioCsvExchangeV1Error, ValueError):
        _abort(code)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(value, dict) or raw != _canonical(value) + b"\n":
        _abort(code)
    return value


def _write_new(path: Path, value: Mapping[str, Any]) -> None:
    payload = _canonical(value) + b"\n"
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload); handle.flush(); os.fchmod(handle.fileno(), 0o600); os.fsync(handle.fileno())
        parent = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except FileExistsError:
        _abort("portfolio_csv_handoff_confirmation_consumed")
    except OSError:
        _abort("portfolio_csv_handoff_write_failed")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _write_or_match(path: Path, value: Mapping[str, Any], mismatch_code: str) -> None:
    if path.exists() or path.is_symlink():
        if _json_file(path, mismatch_code) != dict(value):
            _abort(mismatch_code)
        return
    _write_new(path, value)


class _DirectoryLock:
    def __init__(self, parent: Path, name: str, code: str = "portfolio_csv_handoff_lock_unavailable"):
        self.path = parent / name
        self.code = code
        self.held = False

    def __enter__(self) -> "_DirectoryLock":
        if self.path.is_symlink():
            _abort(self.code)
        try:
            os.mkdir(self.path, 0o700); os.chmod(self.path, 0o700); self.held = True
        except FileExistsError:
            _abort(self.code)
        except OSError:
            _abort("portfolio_csv_handoff_write_failed")
        return self

    def __exit__(self, *_: object) -> None:
        if self.held:
            try:
                os.rmdir(self.path)
            except OSError:
                _abort("portfolio_csv_handoff_write_failed")
            self.held = False


def _directory(path: str | Path, code: str = "portfolio_csv_handoff_staged_import_invalid", *, create: bool = False) -> Path:
    try:
        return _owner_directory(path, create=create)
    except PortfolioCsvExchangeV1Error:
        _abort(code)


def _bound_data_space(path: str | Path, context: PortfolioCsvContextV1) -> Path:
    data_space = _directory(path)
    if data_space.name != context.data_space_id:
        _abort("portfolio_csv_handoff_context_invalid")
    return data_space


def _staged_import(data_space_path: str | Path, context: PortfolioCsvContextV1, staged_handle: str) -> tuple[Path, Any, dict[str, Any]]:
    if not isinstance(staged_handle, str) or STAGED.fullmatch(staged_handle) is None:
        _abort("portfolio_csv_handoff_staged_import_invalid")
    data_space = _bound_data_space(data_space_path, context)
    staged = _directory(data_space / AREA / "imports" / staged_handle)
    receipt = _json_file(staged / "import-receipt.json", "portfolio_csv_handoff_staged_import_invalid")
    required = {
        "contract_version", "status", "bundle_fingerprint", "domain_fingerprint", "target_context_fingerprint",
        "record_count", "catalog_apply", "coupled_transaction_apply", "asset_activity_apply", "cash_coverage_apply",
        "product_write", "provider_access", "network_access", "automatic_retry",
    }
    if (
        set(receipt) != required or receipt.get("contract_version") != 1
        or receipt.get("status") != "staged_lossless_ready_for_domain_handoffs"
        or receipt.get("target_context_fingerprint") != _context_fp(context)
        or receipt.get("product_write") is not False or receipt.get("provider_access") is not False
        or receipt.get("network_access") is not False or receipt.get("automatic_retry") is not False
    ):
        _abort("portfolio_csv_handoff_staged_import_invalid")
    try:
        plan = _preview_portfolio_csv_import_v1(staged / "bundle", staged_bundle_fingerprint=receipt["bundle_fingerprint"])
    except PortfolioCsvExchangeV1Error:
        _abort("portfolio_csv_handoff_staged_import_invalid")
    if len(plan.records) != receipt["record_count"] or plan.manifest["domain_fingerprint"] != receipt["domain_fingerprint"]:
        _abort("portfolio_csv_handoff_staged_import_invalid")
    return data_space, plan, receipt


def _records(plan: Any, domain: str) -> list[dict[str, Any]]:
    return [dict(row) for row in plan.records if row["record_kind"] in DOMAIN_RECORD_KINDS[domain]]


def _rows(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(query, parameters)]


def _canonical_connection(canonical_path: str | Path, context: PortfolioCsvContextV1, *, writable: bool = False) -> tuple[Path, sqlite3.Connection, dict[str, Any]]:
    try:
        snapshot = _canonical_snapshot(canonical_path, _activity_context(context))
    except DesktopProductAssetActivityV1Error:
        _abort("portfolio_csv_handoff_domain_invalid")
    path = Path(snapshot["path"])
    try:
        connection = sqlite3.connect(f"file:{path}?mode={'rw' if writable else 'ro'}", uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=0")
        if not writable:
            connection.execute("PRAGMA query_only=ON")
    except sqlite3.Error:
        _abort("portfolio_csv_handoff_domain_invalid")
    return path, connection, snapshot


def _strict_payload(record: Mapping[str, Any], expected: set[str]) -> dict[str, Any]:
    payload = record.get("payload")
    if not isinstance(payload, dict) or set(payload) != expected:
        _abort("portfolio_csv_handoff_domain_invalid")
    return dict(payload)


def _target_id(prefix: str, context: PortfolioCsvContextV1, bundle_fingerprint: str, source_ref: str) -> str:
    return prefix + _fingerprint({
        "contract": "portfolio_csv_target_identity_v1", "context": _context_fp(context),
        "bundle_fingerprint": bundle_fingerprint, "source_ref": source_ref,
    })[:24]


def _catalog_state(connection: sqlite3.Connection) -> str:
    body = {
        table: _rows(connection, f"SELECT * FROM {table} ORDER BY {identifier}")
        for table, identifier in (("portfolio", "portfolio_id"), ("account", "account_id"), ("asset", "asset_id"), ("provider_mapping", "mapping_id"))
    }
    body["audits"] = _rows(
        connection,
        "SELECT * FROM data_command_audit WHERE area_id IN ('portfolio_catalog','account_catalog','asset_catalog','provider_mapping') ORDER BY command_id",
    )
    return _fingerprint(body)


def _transaction_state(connection: sqlite3.Connection) -> str:
    return _fingerprint({
        "transactions": _rows(connection, "SELECT * FROM transaction_record ORDER BY transaction_id"),
        "postings": _rows(connection, "SELECT * FROM transaction_posting ORDER BY transaction_id,sequence_no,posting_id"),
        "seals": _rows(connection, "SELECT * FROM transaction_seal ORDER BY transaction_id"),
        "audits": _rows(connection, "SELECT * FROM data_command_audit WHERE area_id='transaction_ledger' ORDER BY command_id"),
    })


CATALOG_FIELDS = {
    "portfolio": ("portfolio_id", {"display_name", "base_currency", "status", "origin_type", "origin_ref", "created_at_utc", "updated_at_utc", "revision"}, "ptf_", "portfolio_id", "portfolio_catalog"),
    "asset": ("asset_id", {"display_name", "asset_type", "price_currency", "quantity_scale", "valuation_method", "isin", "status", "origin_type", "origin_ref", "created_at_utc", "updated_at_utc", "revision"}, "ast_", "asset_id", "asset_catalog"),
    "account": ("account_id", {"portfolio_id", "display_name", "account_type", "institution_label", "status", "origin_type", "origin_ref", "created_at_utc", "updated_at_utc", "revision"}, "acc_", "account_id", "account_catalog"),
    "provider_mapping": ("mapping_id", {"asset_id", "capability", "provider_id", "provider_symbol", "exchange_code", "mic_code", "provider_currency", "verification_status", "expert_only", "enabled", "verified_at_utc", "created_at_utc", "updated_at_utc", "revision"}, "map_", "mapping_id", "provider_mapping"),
}


def _matching_existing(existing: list[dict[str, Any]], id_field: str, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [row for row in existing if all(row.get(key) == value for key, value in payload.items() if key != id_field)]


def _catalog_effect(plan: Any, canonical_path: str | Path, context: PortfolioCsvContextV1) -> dict[str, Any]:
    path, connection, snapshot = _canonical_connection(canonical_path, context)
    try:
        existing = {kind: _rows(connection, f"SELECT * FROM {kind} ORDER BY {spec[3]}") for kind, spec in CATALOG_FIELDS.items()}
        existing_audit_ids = {row["command_id"] for row in _rows(connection, "SELECT command_id FROM data_command_audit")}
        before = _catalog_state(connection)
    finally:
        connection.close()
    records = _records(plan, "catalog")
    grouped = {kind: [row for row in records if row["record_kind"] == kind] for kind in CATALOG_FIELDS}
    mapping: dict[str, str] = {}
    expected: dict[str, list[dict[str, Any]]] = {kind: [] for kind in CATALOG_FIELDS}
    creates: dict[str, list[dict[str, Any]]] = {kind: [] for kind in CATALOG_FIELDS}
    for kind in ("portfolio", "asset", "account", "provider_mapping"):
        id_field, fields, prefix, _, _ = CATALOG_FIELDS[kind]
        for record in grouped[kind]:
            payload = _strict_payload(record, fields)
            for key in ("portfolio_id", "asset_id"):
                if key in payload:
                    if payload[key] not in mapping:
                        _abort("portfolio_csv_handoff_dependency_missing")
                    payload[key] = mapping[payload[key]]
            if kind == "provider_mapping" and str(payload.get("provider_id", "")).lower() == "fmp":
                _abort("portfolio_csv_handoff_domain_invalid")
            generated = _target_id(prefix, context, plan.bundle_fingerprint, record["record_ref"])
            generated_match = [row for row in existing[kind] if row[id_field] == generated]
            matches = _matching_existing(existing[kind], id_field, payload)
            if generated_match:
                if generated_match[0] not in matches:
                    _abort("portfolio_csv_handoff_effect_conflict")
                identifier = generated
            elif len(matches) == 1:
                identifier = matches[0][id_field]
            elif len(matches) > 1:
                _abort("portfolio_csv_handoff_effect_conflict")
            else:
                identifier = generated
            row = {id_field: identifier, **payload}
            mapping[record["record_ref"]] = identifier
            expected[kind].append(row)
            if not any(item[id_field] == identifier for item in existing[kind]):
                creates[kind].append(row)
    # Fail before the attempt on known canonical unique-key collisions.
    combined = {kind: existing[kind] + creates[kind] for kind in CATALOG_FIELDS}
    if len({row["display_name"].casefold() for row in combined["portfolio"]}) != len(combined["portfolio"]):
        _abort("portfolio_csv_handoff_effect_conflict")
    if len({(row["portfolio_id"], row["display_name"].casefold()) for row in combined["account"]}) != len(combined["account"]):
        _abort("portfolio_csv_handoff_effect_conflict")
    isins = [row["isin"] for row in combined["asset"] if row["isin"] is not None]
    if len(isins) != len(set(isins)):
        _abort("portfolio_csv_handoff_effect_conflict")
    provider_keys = [(row["asset_id"], row["capability"], row["provider_id"]) for row in combined["provider_mapping"]]
    if len(provider_keys) != len(set(provider_keys)):
        _abort("portfolio_csv_handoff_effect_conflict")
    for kind in ("portfolio", "account", "asset"):
        legacy_origins = [row["origin_ref"] for row in combined[kind] if row["origin_type"] == "legacy_import"]
        if len(legacy_origins) != len(set(legacy_origins)):
            _abort("portfolio_csv_handoff_effect_conflict")
    for kind, rows in creates.items():
        id_field, _, _, _, area_id = CATALOG_FIELDS[kind]
        for row in rows:
            source_refs = [source for source, target in mapping.items() if target == row[id_field]]
            if len(source_refs) != 1:
                _abort("portfolio_csv_handoff_effect_conflict")
            command_id = _audit_row("catalog", area_id, row[id_field], source_refs[0], _fingerprint(row), context, "1970-01-01T00:00:00Z")["command_id"]
            if command_id in existing_audit_ids:
                _abort("portfolio_csv_handoff_effect_conflict")
    return {
        "canonical_schema_version": snapshot["schema_version"], "target_state_fingerprint": before,
        "mapping": mapping, "expected": expected, "creates": creates,
        "source_record_fingerprint": _fingerprint([row["record_fingerprint"] for row in records]),
        "source_record_count": len(records), "create_count": sum(map(len, creates.values())),
        "reuse_count": len(records) - sum(map(len, creates.values())),
    }


def _catalog_receipt(staged: Path, context: PortfolioCsvContextV1) -> dict[str, Any]:
    receipt = _handoff_receipt(staged, "catalog", required=True)
    effect = receipt.get("effect")
    mapping = effect.get("mapping") if isinstance(effect, dict) else None
    expected = effect.get("expected") if isinstance(effect, dict) else None
    if (receipt.get("context_fingerprint") != _context_fp(context) or not isinstance(mapping, dict)
            or any(not isinstance(key, str) or not isinstance(value, str) for key, value in mapping.items())
            or not isinstance(expected, dict) or set(expected) != set(CATALOG_FIELDS)
            or any(not isinstance(expected[kind], list)
                   or any(not isinstance(row, dict) or set(row) != {CATALOG_FIELDS[kind][0], *CATALOG_FIELDS[kind][1]} for row in expected[kind])
                   for kind in CATALOG_FIELDS)):
        _abort("portfolio_csv_handoff_dependency_missing")
    canonical_path = receipt.get("canonical_path_binding")
    if canonical_path is not None:
        _abort("portfolio_csv_handoff_staged_import_invalid")
    return receipt


def _catalog_mapping(staged: Path, context: PortfolioCsvContextV1, canonical_path: str | Path, bundle_fingerprint: str) -> dict[str, str]:
    receipt = _catalog_receipt(staged, context)
    if receipt.get("bundle_fingerprint") != bundle_fingerprint:
        _abort("portfolio_csv_handoff_dependency_missing")
    mapping = dict(receipt["effect"]["mapping"])
    _, connection, _ = _canonical_connection(canonical_path, context)
    try:
        for table in CATALOG_FIELDS:
            identifier = CATALOG_FIELDS[table][0]
            for expected in receipt["effect"]["expected"][table]:
                found = connection.execute(f"SELECT * FROM {table} WHERE {identifier}=?", (expected[identifier],)).fetchone()
                if found is None or dict(found) != expected:
                    _abort("portfolio_csv_handoff_dependency_missing")
    finally:
        connection.close()
    return mapping


def _transaction_effect(plan: Any, staged: Path, canonical_path: str | Path, context: PortfolioCsvContextV1) -> dict[str, Any]:
    mapping = _catalog_mapping(staged, context, canonical_path, plan.bundle_fingerprint)
    _, connection, _ = _canonical_connection(canonical_path, context)
    try:
        before = _transaction_state(connection)
        existing_tx = _rows(connection, "SELECT * FROM transaction_record ORDER BY transaction_id")
        existing_postings = _rows(connection, "SELECT * FROM transaction_posting ORDER BY transaction_id,sequence_no,posting_id")
        existing_audit_ids = {row["command_id"] for row in _rows(connection, "SELECT command_id FROM data_command_audit")}
    finally:
        connection.close()
    records = _records(plan, "coupled_transaction")
    tx_records = [row for row in records if row["record_kind"] == "coupled_transaction"]
    posting_records = [row for row in records if row["record_kind"] == "coupled_posting"]
    tx_payload_fields = {"portfolio_id", "transaction_type", "record_action", "effective_at_utc", "local_date", "memo", "supersedes_transaction_id", "origin_type", "origin_ref", "created_at_utc", "seal"}
    posting_fields = {"transaction_id", "sequence_no", "account_id", "asset_id", "posting_role", "quantity_decimal", "unit_price_decimal", "price_currency", "valuation_amount_decimal", "valuation_currency", "memo"}
    transaction_mapping: dict[str, str] = {}
    pending = list(tx_records)
    expected_transactions: list[dict[str, Any]] = []
    new_transactions: list[dict[str, Any]] = []
    while pending:
        progress = False
        for record in list(pending):
            payload = _strict_payload(record, tx_payload_fields)
            seal = payload.pop("seal")
            predecessor = payload.get("supersedes_transaction_id")
            if predecessor is not None and predecessor not in transaction_mapping:
                continue
            if payload["portfolio_id"] not in mapping:
                _abort("portfolio_csv_handoff_dependency_missing")
            payload["portfolio_id"] = mapping[payload["portfolio_id"]]
            payload["supersedes_transaction_id"] = None if predecessor is None else transaction_mapping[predecessor]
            comparable = dict(payload)
            matches = [row for row in existing_tx if all(row.get(key) == value for key, value in comparable.items())]
            generated = _target_id("txn_", context, plan.bundle_fingerprint, record["record_ref"])
            generated_match = [row for row in existing_tx if row["transaction_id"] == generated]
            if generated_match:
                if generated_match[0] not in matches:
                    _abort("portfolio_csv_handoff_effect_conflict")
                identifier = generated_match[0]["transaction_id"]
            elif len(matches) == 1:
                identifier = matches[0]["transaction_id"]
            elif len(matches) > 1:
                _abort("portfolio_csv_handoff_effect_conflict")
            else:
                identifier = generated
            transaction_mapping[record["record_ref"]] = identifier
            row = {"transaction_id": identifier, **payload, "created_by_actor": context.actor_id}
            expected_transactions.append(row)
            if not any(item["transaction_id"] == identifier for item in existing_tx):
                if not isinstance(seal, dict) or set(seal) != {"sealed_at_utc", "posting_count", "content_fingerprint"} or not SHA.fullmatch(str(seal.get("content_fingerprint", ""))):
                    _abort("portfolio_csv_handoff_domain_invalid")
                new_transactions.append({"record": row, "source_seal": seal, "source_ref": record["record_ref"]})
            pending.remove(record); progress = True
        if not progress:
            _abort("portfolio_csv_handoff_domain_invalid")
    posting_mapping: dict[str, str] = {}
    expected_postings: list[dict[str, Any]] = []
    postings_by_tx: dict[str, list[dict[str, Any]]] = {}
    for record in posting_records:
        payload = _strict_payload(record, posting_fields)
        for key, references in (("transaction_id", transaction_mapping), ("account_id", mapping), ("asset_id", mapping)):
            if payload[key] not in references:
                _abort("portfolio_csv_handoff_dependency_missing")
            payload[key] = references[payload[key]]
        matches = [row for row in existing_postings if all(row.get(key) == value for key, value in payload.items())]
        generated = _target_id("pst_", context, plan.bundle_fingerprint, record["record_ref"])
        generated_match = [row for row in existing_postings if row["posting_id"] == generated]
        if generated_match:
            if generated_match[0] not in matches:
                _abort("portfolio_csv_handoff_effect_conflict")
            identifier = generated
        elif len(matches) == 1:
            identifier = matches[0]["posting_id"]
        elif len(matches) > 1:
            _abort("portfolio_csv_handoff_effect_conflict")
        else:
            identifier = generated
        posting_mapping[record["record_ref"]] = identifier
        row = {"posting_id": identifier, **payload}
        expected_postings.append(row); postings_by_tx.setdefault(row["transaction_id"], []).append(row)
    new_ids = {item["record"]["transaction_id"] for item in new_transactions}
    for item in new_transactions:
        row = item["record"]
        postings = sorted(postings_by_tx.get(row["transaction_id"], []), key=lambda value: (value["sequence_no"], value["posting_id"]))
        seal = item["source_seal"]
        if seal["posting_count"] != len(postings) or seal["sealed_at_utc"] != row["created_at_utc"] or (row["record_action"] == "book") != bool(postings):
            _abort("portfolio_csv_handoff_domain_invalid")
        content = _fingerprint({"transaction_content_version": 1, "record": row, "postings": postings})
        item["postings"] = postings
        item["seal"] = {"transaction_id": row["transaction_id"], "sealed_at_utc": row["created_at_utc"], "posting_count": len(postings), "content_fingerprint": content}
    if any(row["transaction_id"] not in new_ids and not any(item["posting_id"] == row["posting_id"] for item in existing_postings) for row in expected_postings):
        _abort("portfolio_csv_handoff_effect_conflict")
    combined_transactions = existing_tx + [item["record"] for item in new_transactions]
    legacy_origins = [row["origin_ref"] for row in combined_transactions if row["origin_type"] == "legacy_import"]
    if len(legacy_origins) != len(set(legacy_origins)):
        _abort("portfolio_csv_handoff_effect_conflict")
    combined_postings = existing_postings + [posting for item in new_transactions for posting in item["postings"]]
    posting_sequences = [(row["transaction_id"], row["sequence_no"]) for row in combined_postings]
    if len(posting_sequences) != len(set(posting_sequences)):
        _abort("portfolio_csv_handoff_effect_conflict")
    for item in new_transactions:
        command_id = _audit_row("transaction", "transaction_ledger", item["record"]["transaction_id"], item["source_ref"], item["seal"]["content_fingerprint"], context, "1970-01-01T00:00:00Z")["command_id"]
        if command_id in existing_audit_ids:
            _abort("portfolio_csv_handoff_effect_conflict")
    return {
        "target_state_fingerprint": before, "catalog_receipt_ref": _receipt_public_ref(_catalog_receipt(staged, context)),
        "transaction_mapping": transaction_mapping, "posting_mapping": posting_mapping,
        "expected_transactions": expected_transactions, "expected_postings": expected_postings,
        "new_transactions": new_transactions,
        "source_record_fingerprint": _fingerprint([row["record_fingerprint"] for row in records]),
        "source_record_count": len(records), "create_transaction_count": len(new_transactions),
        "reuse_transaction_count": len(tx_records) - len(new_transactions),
    }


def _draft_area(data_space: Path) -> Path:
    return data_space / "activity-drafts-v1"


def _draft_tree_state(data_space: Path) -> str:
    area = _draft_area(data_space)
    if not area.exists() and not area.is_symlink():
        return _fingerprint([])
    try:
        area = _directory(area, "portfolio_csv_handoff_effect_conflict")
        rows = []
        for path in sorted(area.rglob("*"), key=lambda item: item.relative_to(area).as_posix()):
            relative = path.relative_to(area).as_posix()
            if ".writer.lock" in relative:
                continue
            if path.is_symlink():
                _abort("portfolio_csv_handoff_effect_conflict")
            rows.append([relative, "directory" if path.is_dir() else hashlib.sha256(_regular_file(path).read_bytes()).hexdigest()])
        return _fingerprint(rows)
    except PortfolioCsvExchangeV1Error:
        _abort("portfolio_csv_handoff_effect_conflict")


def _bound_draft_event_ref(context: PortfolioCsvContextV1, source_fingerprint: str, ordinal: int) -> str:
    material = "|".join(("tolerant-csv-activity", _draft_context_fingerprint(context), source_fingerprint, str(ordinal)))
    return "evt_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _draft_context_fingerprint(context: PortfolioCsvContextV1) -> str:
    return _product_context_fingerprint(_activity_context(context))


def _activity_effect(plan: Any, staged: Path, canonical_path: str | Path, data_space: Path, context: PortfolioCsvContextV1) -> dict[str, Any]:
    mapping = _catalog_mapping(staged, context, canonical_path, plan.bundle_fingerprint)
    records = _records(plan, "asset_activity")
    events = sorted((row for row in records if row["record_kind"] == "asset_activity"), key=lambda row: row["record_ref"])
    fifo_rows = [row for row in records if row["record_kind"] == "fifo_order_evidence"]
    fifo_records = {row["event_ref"]: row for row in fifo_rows}
    if len(fifo_records) != len(fifo_rows):
        _abort("portfolio_csv_handoff_domain_invalid")
    event_fields = {
        "account_id", "related_account_id", "asset_id", "source_asset_id", "event_type", "event_time_evidence",
        "local_date", "local_time", "time_zone", "effective_at_utc", "original_acquired_time_evidence",
        "original_acquired_local_date", "original_acquired_local_time", "original_acquired_time_zone",
        "original_acquired_at_utc", "amount_input_mode", "basis_evidence_mode", "quantity_decimal",
        "eligible_quantity_decimal", "unit_price_decimal", "gross_amount_decimal", "monetary_fee_decimal",
        "asset_fee_quantity_decimal", "provided_basis_decimal", "movement_context_code", "basis_currency",
        "inventory_effect_code", "fifo_effect_code", "portfolio_quantity_change_decimal", "gross_economic_amount_decimal",
        "fifo_basis_created_decimal", "net_trade_proceeds_decimal", "gross_income_decimal", "distribution_value_decimal",
        "income_recognition_status", "outgoing_lot_receipt_required", "transfer_lot_carry_required",
        "original_acquisition_evidence_required", "cash_posting_created", "tax_classification_inferred",
        "provider_price_used", "memo", "origin_type", "source_row_fingerprint", "effect_fingerprint",
        "semantic_contract", "created_at_utc", "portfolio_id",
    }
    native_keys = {
        "event_type", "event_time_evidence", "local_date", "local_time", "time_zone", "effective_at_utc",
        "original_acquired_time_evidence", "original_acquired_local_date", "original_acquired_local_time",
        "original_acquired_time_zone", "original_acquired_at_utc", "amount_input_mode", "basis_evidence_mode",
        "quantity_decimal", "eligible_quantity_decimal", "unit_price_decimal", "gross_amount_decimal",
        "monetary_fee_decimal", "asset_fee_quantity_decimal", "provided_basis_decimal", "movement_context_code",
    }
    source_fingerprint = plan.bundle_fingerprint
    descriptors = []
    event_ref_by_source: dict[str, str] = {}
    for ordinal, record in enumerate(events, 1):
        payload = _strict_payload(record, event_fields)
        references = {}
        for source_key, target_key in (("account_id", "account_ref"), ("related_account_id", "related_account_ref"), ("asset_id", "asset_ref"), ("source_asset_id", "source_asset_ref")):
            source = payload[source_key]
            if source is not None and source not in mapping:
                _abort("portfolio_csv_handoff_dependency_missing")
            references[target_key] = None if source is None else mapping[source]
        if payload["portfolio_id"] not in mapping:
            _abort("portfolio_csv_handoff_dependency_missing")
        event = {key: payload[key] for key in native_keys} | references
        expected_event_ref = _bound_draft_event_ref(context, source_fingerprint, ordinal)
        event_ref_by_source[record["record_ref"]] = expected_event_ref
        auxiliary: dict[str, Any] = {"unclassified_fee_decimal": None, "unclassified_fee_resolution": "not_present"}
        fifo_record = fifo_records.get(record["record_ref"])
        if fifo_record is not None:
            fifo = _strict_payload(fifo_record, {"event_ref", "evidence_mode", "source_file_fingerprint", "source_row_ordinal", "owner_decision_fingerprint", "evidence_fingerprint"})
            if fifo["event_ref"] != record["record_ref"]:
                _abort("portfolio_csv_handoff_domain_invalid")
            fifo_body = {
                "event_ref": expected_event_ref, "evidence_mode": fifo["evidence_mode"],
                "source_file_fingerprint": fifo["source_file_fingerprint"], "source_row_ordinal": fifo["source_row_ordinal"],
                "owner_decision_fingerprint": fifo["owner_decision_fingerprint"],
            }
            auxiliary["fifo_order_evidence"] = {**fifo_body, "evidence_fingerprint": _fingerprint(fifo_body)}
        descriptors.append({
            "portfolio_id": mapping[payload["portfolio_id"]], "event": event,
            "source_binding": {"source_fingerprint": source_fingerprint, "source_row_ordinal": ordinal, "source_row_key": record["record_ref"]},
            "source_auxiliary": auxiliary, "expected_event_ref": expected_event_ref,
        })
    if set(fifo_records) - set(event_ref_by_source):
        _abort("portfolio_csv_handoff_domain_invalid")
    return {
        "target_state_fingerprint": _draft_tree_state(data_space), "catalog_receipt_ref": _receipt_public_ref(_catalog_receipt(staged, context)),
        "descriptors": descriptors, "source_record_fingerprint": _fingerprint([row["record_fingerprint"] for row in records]),
        "source_record_count": len(records), "draft_count": len(descriptors),
    }


def _cash_candidates(plan: Any, mapping: Mapping[str, str]) -> list[dict[str, Any]]:
    records = _records(plan, "cash_coverage")
    by_kind = {kind: [row for row in records if row["record_kind"] == kind] for kind in DOMAIN_RECORD_KINDS["cash_coverage"]}
    common = {"portfolio_id", "account_id", "cash_asset_id", "currency", "source_command_ref", "committed_at_utc"}
    required = {
        "cash_coverage_period": common | {"effective_from", "effective_to", "coverage_mode"},
        "cash_event": common | {"event_type", "related_account_id", "event_time_evidence", "local_date", "local_time", "time_zone", "effective_at_utc", "amount_decimal", "flow_classification"},
        "cash_interest_income": common | {"income_type", "local_date", "gross_income_decimal", "linked_cash_event_id"},
        "cash_reconciliation": common | {"as_of_date", "observed_balance_decimal", "evidence_fingerprint"},
    }
    normalized: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for kind, rows in by_kind.items():
        for record in rows:
            if record["record_ref"] in normalized:
                _abort("portfolio_csv_handoff_domain_invalid")
            payload = _strict_payload(record, required[kind])
            for key in ("portfolio_id", "account_id", "cash_asset_id", "related_account_id"):
                if key in payload and payload[key] is not None:
                    if payload[key] not in mapping:
                        _abort("portfolio_csv_handoff_dependency_missing")
                    payload[key] = mapping[payload[key]]
            normalized[record["record_ref"]] = (record, payload)
    consumed: set[str] = set()
    raw_candidates: list[dict[str, Any]] = []
    source_event_to_candidate: dict[str, str] = {}

    def add(record_refs: list[str], command: dict[str, Any], linked_source_event_ref: str | None = None) -> None:
        if len(set(record_refs)) != len(record_refs) or any(ref in consumed for ref in record_refs):
            _abort("portfolio_csv_handoff_domain_invalid")
        body = {"bundle_fingerprint": plan.bundle_fingerprint, "record_refs": sorted(record_refs), "mapped_command": command, "linked_source_event_ref": linked_source_event_ref}
        candidate_fp = _fingerprint(body)
        candidate = {
            "candidate_ref": "portfolio_cash_candidate_" + candidate_fp[:24],
            "source_candidate_fingerprint": candidate_fp, "record_refs": sorted(record_refs),
            "mapped_command": command, "linked_source_event_ref": linked_source_event_ref,
        }
        raw_candidates.append(candidate)
        for ref in record_refs:
            if normalized[ref][0]["record_kind"] == "cash_event":
                source_event_to_candidate[ref] = candidate_fp

    for period_record in by_kind["cash_coverage_period"]:
        ref = period_record["record_ref"]; payload = normalized[ref][1]
        command = {
            "action_type": "declare_coverage", "portfolio_id": payload["portfolio_id"], "account_id": payload["account_id"],
            "cash_asset_id": payload["cash_asset_id"], "effective_from": payload["effective_from"],
            "effective_to": payload["effective_to"], "coverage_mode": payload["coverage_mode"],
            "opening_balance_decimal": None, "opening_event_time_evidence": None, "opening_local_time": None,
            "opening_time_zone": None, "opening_effective_at_utc": None, "reconciliation_as_of_date": None,
            "observed_balance_decimal": None, "evidence_fingerprint": None,
        }
        group = payload["source_command_ref"]
        refs = [ref]
        if payload["coverage_mode"] == "complete_reconciled":
            identity = tuple(payload[key] for key in ("portfolio_id", "account_id", "cash_asset_id", "currency"))
            openings = [
                row for row in by_kind["cash_event"]
                if normalized[row["record_ref"]][1]["source_command_ref"] == group
                and normalized[row["record_ref"]][1]["event_type"] == "opening_balance"
                and tuple(normalized[row["record_ref"]][1][key] for key in ("portfolio_id", "account_id", "cash_asset_id", "currency")) == identity
            ]
            reconciliations = [
                row for row in by_kind["cash_reconciliation"]
                if normalized[row["record_ref"]][1]["source_command_ref"] == group
                and tuple(normalized[row["record_ref"]][1][key] for key in ("portfolio_id", "account_id", "cash_asset_id", "currency")) == identity
            ]
            if len(openings) != 1 or len(reconciliations) != 1:
                _abort("portfolio_csv_handoff_domain_invalid")
            opening = normalized[openings[0]["record_ref"]][1]; reconciliation = normalized[reconciliations[0]["record_ref"]][1]
            command.update(
                opening_balance_decimal=opening["amount_decimal"], opening_event_time_evidence=opening["event_time_evidence"],
                opening_local_time=opening["local_time"], opening_time_zone=opening["time_zone"],
                opening_effective_at_utc=opening["effective_at_utc"], reconciliation_as_of_date=reconciliation["as_of_date"],
                observed_balance_decimal=reconciliation["observed_balance_decimal"], evidence_fingerprint=reconciliation["evidence_fingerprint"],
            )
            refs += [openings[0]["record_ref"], reconciliations[0]["record_ref"]]
        add(refs, command); consumed.update(refs)
    for record in by_kind["cash_event"]:
        ref = record["record_ref"]
        if ref in consumed:
            continue
        payload = normalized[ref][1]
        add([ref], {
            "action_type": "record_cash_event", "portfolio_id": payload["portfolio_id"], "account_id": payload["account_id"],
            "cash_asset_id": payload["cash_asset_id"], "event_type": payload["event_type"],
            "related_account_id": payload["related_account_id"], "event_time_evidence": payload["event_time_evidence"],
            "local_date": payload["local_date"], "local_time": payload["local_time"], "time_zone": payload["time_zone"],
            "effective_at_utc": payload["effective_at_utc"], "amount_decimal": payload["amount_decimal"],
            "flow_classification": payload["flow_classification"],
        }); consumed.add(ref)
    for candidate in raw_candidates:
        for ref in candidate["record_refs"]:
            if normalized[ref][0]["record_kind"] == "cash_event":
                source_event_to_candidate[ref] = candidate["source_candidate_fingerprint"]
    for record in by_kind["cash_interest_income"]:
        ref = record["record_ref"]; payload = normalized[ref][1]
        linked = payload["linked_cash_event_id"]
        if linked is not None and linked not in source_event_to_candidate:
            _abort("portfolio_csv_handoff_domain_invalid")
        command = {
            "action_type": "record_interest_income", "portfolio_id": payload["portfolio_id"], "account_id": payload["account_id"],
            "cash_asset_id": payload["cash_asset_id"], "local_date": payload["local_date"],
            "gross_income_decimal": payload["gross_income_decimal"], "linked_cash_event_ref": None,
        }
        add([ref], command, linked); consumed.add(ref)
    for record in by_kind["cash_reconciliation"]:
        ref = record["record_ref"]
        if ref in consumed:
            continue
        payload = normalized[ref][1]
        add([ref], {
            "action_type": "record_reconciliation", "portfolio_id": payload["portfolio_id"], "account_id": payload["account_id"],
            "cash_asset_id": payload["cash_asset_id"], "as_of_date": payload["as_of_date"],
            "observed_balance_decimal": payload["observed_balance_decimal"], "evidence_fingerprint": payload["evidence_fingerprint"],
        }); consumed.add(ref)
    if consumed != set(normalized):
        _abort("portfolio_csv_handoff_domain_invalid")
    for candidate in raw_candidates:
        linked = candidate.pop("linked_source_event_ref")
        candidate["linked_source_candidate_fingerprint"] = None if linked is None else source_event_to_candidate[linked]
    raw_candidates.sort(key=lambda item: (item["mapped_command"]["action_type"], item["record_refs"]))
    return raw_candidates


def _cash_effect(plan: Any, staged: Path, canonical_path: str | Path, context: PortfolioCsvContextV1) -> dict[str, Any]:
    mapping = _catalog_mapping(staged, context, canonical_path, plan.bundle_fingerprint)
    candidates = _cash_candidates(plan, mapping)
    path = staged / "handoffs" / "cash_coverage" / "reviewed-candidates.json"
    current = "absent"
    if path.exists() or path.is_symlink():
        value = _json_file(path, "portfolio_csv_handoff_effect_conflict")
        current = _fingerprint(value)
    body = {
        "portfolio_csv_cash_candidate_bundle_version": 1, "status": "reviewed_candidates_staged",
        "context_fingerprint": _context_fp(context), "bundle_fingerprint": plan.bundle_fingerprint,
        "candidates": candidates, "cash_fact_write": False, "canonical_write": False,
        "asset_activity_write": False, "provider_access": False, "network_access": False,
    }
    body["candidate_bundle_fingerprint"] = _fingerprint(body)
    records = _records(plan, "cash_coverage")
    return {
        "target_state_fingerprint": _fingerprint(current), "catalog_receipt_ref": _receipt_public_ref(_catalog_receipt(staged, context)),
        "candidate_bundle": body, "source_record_fingerprint": _fingerprint([row["record_fingerprint"] for row in records]),
        "source_record_count": len(records), "candidate_count": len(candidates),
    }


def _require_identity_writes_allowed(data_space: Path, context: PortfolioCsvContextV1) -> None:
    try:
        binding = read_desktop_product_asset_activity_binding_v1(data_space, _activity_context(context))
    except DesktopProductAssetActivityV1Error:
        _abort("portfolio_csv_handoff_domain_invalid")
    if binding.get("status") != "absent":
        _abort("portfolio_csv_handoff_dependency_missing")


def _effect(domain: str, plan: Any, staged: Path, canonical_path: str | Path, data_space: Path, context: PortfolioCsvContextV1) -> dict[str, Any]:
    if domain == "catalog":
        effect = _catalog_effect(plan, canonical_path, context)
        create_count = effect["create_count"]
    elif domain == "coupled_transaction":
        effect = _transaction_effect(plan, staged, canonical_path, context)
        create_count = effect["create_transaction_count"]
    elif domain == "asset_activity":
        return _activity_effect(plan, staged, canonical_path, data_space, context)
    elif domain == "cash_coverage":
        return _cash_effect(plan, staged, canonical_path, context)
    else:
        _abort("portfolio_csv_handoff_domain_invalid")
    if create_count:
        _require_identity_writes_allowed(data_space, context)
    return effect


def _preview(domain: str, data_space_path: str | Path, canonical_path: str | Path, context_value: Any, staged_handle: str) -> dict[str, Any]:
    if domain not in DOMAINS:
        _abort("portfolio_csv_handoff_domain_invalid")
    context = _context(context_value)
    data_space, plan, _ = _staged_import(data_space_path, context, staged_handle)
    staged = data_space / AREA / "imports" / staged_handle
    effect = _effect(domain, plan, staged, canonical_path, data_space, context)
    body = {
        "portfolio_csv_handoff_preview_version": 1, "status": "ready_for_confirmation", "domain": domain,
        "staged_import_handle": staged_handle, "bundle_fingerprint": plan.bundle_fingerprint,
        "context_fingerprint": _context_fp(context), "effect": effect,
        "confirmation_required": True, "one_attempt_only": True, "automatic_retry": False,
    }
    trusted = {**body, "handoff_plan_fingerprint": _fingerprint(body)}
    handoff_ref = "portfolio_handoff_" + trusted["handoff_plan_fingerprint"][:32]
    public = {
        "portfolio_csv_handoff_public_preview_version": 1, "status": "ready_for_confirmation", "domain": domain,
        "handoff_ref": handoff_ref, "staged_import_handle": staged_handle,
        "source_record_count": effect["source_record_count"],
        "create_count": effect.get("create_count", effect.get("create_transaction_count", effect.get("draft_count", effect.get("candidate_count", 0)))),
        "reuse_count": effect.get("reuse_count", effect.get("reuse_transaction_count", 0)),
        "effect_type": {"catalog": "canonical_catalog_rows", "coupled_transaction": "canonical_transaction_rows", "asset_activity": "persistent_activity_drafts", "cash_coverage": "reviewed_cash_candidates"}[domain],
        "confirmation_required": True, "one_attempt_only": True, "automatic_retry": False,
        "canonical_write": domain in {"catalog", "coupled_transaction"}, "asset_activity_fact_write": False,
        "cash_fact_write": False, "provider_access": False, "network_access": False,
        "path_exposed": False, "context_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False,
    }
    return {"public_preview": public, "trusted_preview": trusted}


def preview_portfolio_csv_catalog_handoff_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, staged_handle: str) -> dict[str, Any]:
    return _preview("catalog", data_space_path, canonical_path, context_value, staged_handle)


def preview_portfolio_csv_transaction_handoff_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, staged_handle: str) -> dict[str, Any]:
    return _preview("coupled_transaction", data_space_path, canonical_path, context_value, staged_handle)


def preview_portfolio_csv_asset_activity_handoff_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, staged_handle: str) -> dict[str, Any]:
    return _preview("asset_activity", data_space_path, canonical_path, context_value, staged_handle)


def preview_portfolio_csv_cash_handoff_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, staged_handle: str) -> dict[str, Any]:
    return _preview("cash_coverage", data_space_path, canonical_path, context_value, staged_handle)


def build_portfolio_csv_handoff_confirmation_v1(trusted_preview: Mapping[str, Any], context_value: Any, confirmation_ref: str, issued_at_utc: str, expires_at_utc: str) -> dict[str, Any]:
    context = _context(context_value); issued = _utc(issued_at_utc, "portfolio_csv_handoff_confirmation_invalid"); expires = _utc(expires_at_utc, "portfolio_csv_handoff_confirmation_invalid")
    domain = trusted_preview.get("domain") if isinstance(trusted_preview, Mapping) else None
    if domain not in DOMAINS:
        _abort("portfolio_csv_handoff_confirmation_invalid")
    try:
        trusted = _trusted(trusted_preview, context, domain)
    except PortfolioCsvHandoffV1Error:
        _abort("portfolio_csv_handoff_confirmation_invalid")
    plan_fp = trusted["handoff_plan_fingerprint"]
    if not isinstance(confirmation_ref, str) or CONFIRMATION_REF.fullmatch(confirmation_ref) is None or issued > expires:
        _abort("portfolio_csv_handoff_confirmation_invalid")
    confirmation_body = {
        "portfolio_csv_handoff_confirmation_version": 1, "authorization_scope": "portfolio_csv_domain_handoff_once",
        "confirmation_ref": confirmation_ref, "domain": trusted_preview["domain"],
        "handoff_plan_fingerprint": plan_fp, "context_fingerprint": _context_fp(context),
        "issued_at_utc": issued, "expires_at_utc": expires, "confirmed": True,
        "automatic_retry_authorized": False, "other_domain_write_authorized": False,
    }
    return {**confirmation_body, "confirmation_fingerprint": _fingerprint(confirmation_body)}


def _verify_confirmation(value: Mapping[str, Any], trusted: Mapping[str, Any], context: PortfolioCsvContextV1, at: str, *, enforce_validity: bool = True) -> dict[str, Any]:
    required = {"portfolio_csv_handoff_confirmation_version", "authorization_scope", "confirmation_ref", "domain", "handoff_plan_fingerprint", "context_fingerprint", "issued_at_utc", "expires_at_utc", "confirmed", "automatic_retry_authorized", "other_domain_write_authorized", "confirmation_fingerprint"}
    if not isinstance(value, Mapping) or set(value) != required:
        _abort("portfolio_csv_handoff_confirmation_invalid")
    body = dict(value); fingerprint = body.pop("confirmation_fingerprint")
    if fingerprint != _fingerprint(body) or body["portfolio_csv_handoff_confirmation_version"] != 1 or body["authorization_scope"] != "portfolio_csv_domain_handoff_once" or body["domain"] != trusted.get("domain") or body["handoff_plan_fingerprint"] != trusted.get("handoff_plan_fingerprint") or body["context_fingerprint"] != _context_fp(context) or body["confirmed"] is not True or body["automatic_retry_authorized"] is not False or body["other_domain_write_authorized"] is not False or not isinstance(body["confirmation_ref"], str) or CONFIRMATION_REF.fullmatch(body["confirmation_ref"]) is None:
        _abort("portfolio_csv_handoff_confirmation_invalid")
    issued = _utc(body["issued_at_utc"], "portfolio_csv_handoff_confirmation_invalid"); expires = _utc(body["expires_at_utc"], "portfolio_csv_handoff_confirmation_invalid")
    if enforce_validity and not issued <= at <= expires:
        _abort("portfolio_csv_handoff_confirmation_expired")
    return {**body, "confirmation_fingerprint": fingerprint}


def _handoff_area(staged: Path, domain: str, *, create: bool) -> Path:
    root = staged / "handoffs"
    if create:
        root = _directory(root, "portfolio_csv_handoff_write_failed", create=True)
        return _directory(root / domain, "portfolio_csv_handoff_write_failed", create=True)
    return _directory(root / domain)


def _strict_attempt(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "portfolio_csv_handoff_attempt_version", "status", "context_fingerprint", "domain",
        "trusted_preview", "confirmation", "attempted_at_utc", "automatic_retry", "attempt_fingerprint",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        _abort("portfolio_csv_handoff_recovery_invalid")
    body = dict(value); fingerprint = body.pop("attempt_fingerprint")
    if (fingerprint != _fingerprint(body) or body["portfolio_csv_handoff_attempt_version"] != 1
            or body["status"] != "confirmation_consumed_before_domain_effect" or body["domain"] not in DOMAINS
            or body["automatic_retry"] is not False):
        _abort("portfolio_csv_handoff_recovery_invalid")
    _utc(body["attempted_at_utc"], "portfolio_csv_handoff_recovery_invalid")
    return dict(value)


def _handoff_receipt(staged: Path, domain: str, *, required: bool = False) -> dict[str, Any] | None:
    path = staged / "handoffs" / domain / "receipt.json"
    if not path.exists() and not path.is_symlink():
        if required:
            _abort("portfolio_csv_handoff_dependency_missing")
        return None
    value = _json_file(path, "portfolio_csv_handoff_effect_conflict")
    required_keys = {
        "portfolio_csv_handoff_receipt_version", "status", "domain", "context_fingerprint",
        "bundle_fingerprint", "handoff_plan_fingerprint", "confirmation_fingerprint",
        "recovery_confirmation_fingerprint", "attempt_fingerprint", "committed_at_utc",
        "created_count", "reused_count", "canonical_write", "candidate_only", "effect",
        "other_domain_write", "provider_access", "network_access", "receipt_fingerprint",
    }
    body = dict(value); fingerprint = body.pop("receipt_fingerprint", None)
    if (set(value) != required_keys or fingerprint != _fingerprint(body)
            or value.get("portfolio_csv_handoff_receipt_version") != 1 or value.get("domain") != domain
            or value.get("status") not in {"completed", "recovered_completed"}
            or not isinstance(value.get("context_fingerprint"), str) or SHA.fullmatch(value["context_fingerprint"]) is None
            or not isinstance(value.get("bundle_fingerprint"), str) or SHA.fullmatch(value["bundle_fingerprint"]) is None
            or not isinstance(value.get("handoff_plan_fingerprint"), str) or SHA.fullmatch(value["handoff_plan_fingerprint"]) is None
            or not isinstance(value.get("confirmation_fingerprint"), str) or SHA.fullmatch(value["confirmation_fingerprint"]) is None
            or not isinstance(value.get("attempt_fingerprint"), str) or SHA.fullmatch(value["attempt_fingerprint"]) is None
            or value.get("recovery_confirmation_fingerprint") is not None
               and (not isinstance(value["recovery_confirmation_fingerprint"], str) or SHA.fullmatch(value["recovery_confirmation_fingerprint"]) is None)
            or (value["status"] == "completed") != (value["recovery_confirmation_fingerprint"] is None)
            or not isinstance(value.get("created_count"), int) or isinstance(value["created_count"], bool) or value["created_count"] < 0
            or not isinstance(value.get("reused_count"), int) or isinstance(value["reused_count"], bool) or value["reused_count"] < 0
            or value.get("canonical_write") is not (domain in {"catalog", "coupled_transaction"} and value["created_count"] > 0)
            or value.get("candidate_only") is not (domain in {"asset_activity", "cash_coverage"})
            or not isinstance(value.get("effect"), dict)
            or value.get("other_domain_write") is not False or value.get("provider_access") is not False
            or value.get("network_access") is not False):
        _abort("portfolio_csv_handoff_effect_conflict")
    _utc(value.get("committed_at_utc"), "portfolio_csv_handoff_effect_conflict")
    return value


def _validate_receipt_binding(receipt: Mapping[str, Any], context: PortfolioCsvContextV1, bundle_fingerprint: str) -> None:
    if receipt.get("context_fingerprint") != _context_fp(context) or receipt.get("bundle_fingerprint") != bundle_fingerprint:
        _abort("portfolio_csv_handoff_effect_conflict")


def _receipt_public_ref(receipt: Mapping[str, Any]) -> str:
    return "portfolio_handoff_receipt_" + str(receipt["receipt_fingerprint"])[:24]


def _public_result(receipt: Mapping[str, Any], replay: bool = False) -> dict[str, Any]:
    effect = receipt["effect"]
    return {
        "portfolio_csv_handoff_result_version": 1, "status": "already_completed" if replay else receipt["status"],
        "domain": receipt["domain"], "receipt_ref": _receipt_public_ref(receipt),
        "source_record_count": effect["source_record_count"],
        "created_count": receipt["created_count"], "reused_count": receipt["reused_count"],
        "canonical_write": receipt["canonical_write"], "asset_activity_fact_write": False,
        "cash_fact_write": False, "candidate_only": receipt["candidate_only"],
        "provider_access": False, "network_access": False, "automatic_retry": False,
        "path_exposed": False, "context_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False,
    }


def _catalog_reconciliation(connection: sqlite3.Connection, effect: Mapping[str, Any], attempted_at: str, context: PortfolioCsvContextV1) -> str:
    expected_by_kind = effect.get("expected") if isinstance(effect, Mapping) else None
    creates_by_kind = effect.get("creates") if isinstance(effect, Mapping) else None
    mapping = effect.get("mapping") if isinstance(effect, Mapping) else None
    if (not isinstance(expected_by_kind, dict) or set(expected_by_kind) != set(CATALOG_FIELDS)
            or not isinstance(creates_by_kind, dict) or set(creates_by_kind) != set(CATALOG_FIELDS)
            or not isinstance(mapping, dict)):
        return "conflict"
    present = 0; total = 0
    for kind in CATALOG_FIELDS:
        rows = expected_by_kind[kind]
        creates = creates_by_kind[kind]
        if not isinstance(rows, list) or not isinstance(creates, list):
            return "conflict"
        identifier = CATALOG_FIELDS[kind][0]
        for expected in rows:
            total += 1
            row = connection.execute(f"SELECT * FROM {kind} WHERE {identifier}=?", (expected[identifier],)).fetchone()
            if row is not None:
                if dict(row) != expected:
                    return "conflict"
                present += 1
        for created in creates:
            total += 1
            source_refs = [source for source, target in mapping.items() if target == created[identifier]]
            if len(source_refs) != 1:
                return "conflict"
            audit = _audit_row("catalog", CATALOG_FIELDS[kind][4], created[identifier], source_refs[0], _fingerprint(created), context, attempted_at)
            row = connection.execute("SELECT * FROM data_command_audit WHERE command_id=?", (audit["command_id"],)).fetchone()
            if row is not None:
                if dict(row) != audit:
                    return "conflict"
                present += 1
    return "complete" if present == total else "absent" if present == 0 else "partial"


def _transaction_reconciliation(connection: sqlite3.Connection, effect: Mapping[str, Any], attempted_at: str, context: PortfolioCsvContextV1) -> str:
    expected_transactions = effect.get("expected_transactions") if isinstance(effect, Mapping) else None
    expected_postings = effect.get("expected_postings") if isinstance(effect, Mapping) else None
    new_transactions = effect.get("new_transactions") if isinstance(effect, Mapping) else None
    if not isinstance(expected_transactions, list) or not isinstance(expected_postings, list) or not isinstance(new_transactions, list):
        return "conflict"
    try:
        new_transaction_ids = {item["record"]["transaction_id"] for item in new_transactions}
    except (KeyError, TypeError):
        return "conflict"
    present = 0; total = len(expected_transactions) + len(expected_postings)
    for table, identifier, rows in (("transaction_record", "transaction_id", expected_transactions), ("transaction_posting", "posting_id", expected_postings)):
        for expected in rows:
            row = connection.execute(f"SELECT * FROM {table} WHERE {identifier}=?", (expected[identifier],)).fetchone()
            if row is not None:
                if table == "transaction_record" and expected["transaction_id"] not in new_transaction_ids:
                    comparable = dict(row); comparable.pop("created_by_actor", None)
                    expected_comparable = dict(expected); expected_comparable.pop("created_by_actor", None)
                    if comparable != expected_comparable:
                        return "conflict"
                elif dict(row) != expected:
                    return "conflict"
                present += 1
    for item in new_transactions:
        total += 2
        try:
            seal = item["seal"]
            record = item["record"]
            source_ref = item["source_ref"]
        except (KeyError, TypeError):
            return "conflict"
        seal_row = connection.execute("SELECT * FROM transaction_seal WHERE transaction_id=?", (seal["transaction_id"],)).fetchone()
        if seal_row is not None:
            if dict(seal_row) != seal:
                return "conflict"
            present += 1
        audit = _audit_row("transaction", "transaction_ledger", record["transaction_id"], source_ref, seal["content_fingerprint"], context, attempted_at)
        audit_row = connection.execute("SELECT * FROM data_command_audit WHERE command_id=?", (audit["command_id"],)).fetchone()
        if audit_row is not None:
            if dict(audit_row) != audit:
                return "conflict"
            present += 1
    return "complete" if present == total else "absent" if present == 0 else "partial"


def _activity_reconciliation(data_space: Path, context: PortfolioCsvContextV1, effect: Mapping[str, Any]) -> str:
    descriptors = effect.get("descriptors") if isinstance(effect, Mapping) else None
    if not isinstance(descriptors, list):
        return "conflict"
    area = _draft_area(data_space) / "drafts"
    if not descriptors:
        return "complete"
    if not area.exists() and not area.is_symlink():
        return "absent"
    try:
        area = _directory(area, "portfolio_csv_handoff_effect_conflict")
        found = 0
        expected = {(item["source_binding"]["source_fingerprint"], item["source_binding"]["source_row_ordinal"], item["source_binding"]["source_row_key"]): item for item in descriptors}
        if len(expected) != len(descriptors):
            return "conflict"
        seen: set[tuple[Any, Any, Any]] = set()
        for path in sorted(area.glob("adt_*.json")):
            value = _json_file(path, "portfolio_csv_handoff_effect_conflict")
            binding = value.get("source_binding")
            if not isinstance(binding, dict):
                continue
            key = (binding.get("source_fingerprint"), binding.get("source_row_ordinal"), binding.get("source_row_key"))
            if key in expected:
                if key in seen:
                    return "conflict"
                seen.add(key); item = expected[key]
                if value.get("portfolio_id") != item["portfolio_id"] or value.get("event") != {**item["event"], "event_ref": item["expected_event_ref"]} or value.get("source_auxiliary") != item["source_auxiliary"]:
                    return "conflict"
                found += 1
        return "complete" if found == len(expected) else "absent" if found == 0 else "partial"
    except PortfolioCsvExchangeV1Error:
        return "conflict"


def _cash_reconciliation(staged: Path, effect: Mapping[str, Any]) -> str:
    candidate_bundle = effect.get("candidate_bundle") if isinstance(effect, Mapping) else None
    if not isinstance(candidate_bundle, dict):
        return "conflict"
    path = staged / "handoffs" / "cash_coverage" / "reviewed-candidates.json"
    if not path.exists() and not path.is_symlink():
        return "absent"
    try:
        return "complete" if _json_file(path, "portfolio_csv_handoff_effect_conflict") == candidate_bundle else "conflict"
    except PortfolioCsvHandoffV1Error:
        return "conflict"


def _reconcile(domain: str, staged: Path, canonical_path: str | Path, data_space: Path, context: PortfolioCsvContextV1, effect: Mapping[str, Any], attempted_at: str) -> str:
    try:
        if domain in {"catalog", "coupled_transaction"}:
            _, connection, _ = _canonical_connection(canonical_path, context)
            try:
                return _catalog_reconciliation(connection, effect, attempted_at, context) if domain == "catalog" else _transaction_reconciliation(connection, effect, attempted_at, context)
            finally:
                connection.close()
        if domain == "asset_activity":
            return _activity_reconciliation(data_space, context, effect)
        return _cash_reconciliation(staged, effect)
    except (KeyError, TypeError, ValueError):
        return "conflict"


def _audit_row(domain: str, area_id: str, entity_id: str, source_ref: str, payload_fp: str, context: PortfolioCsvContextV1, attempted_at: str) -> dict[str, Any]:
    command_id = "cmd_pcsv_" + _fingerprint({"domain": domain, "context": _context_fp(context), "entity": entity_id, "source_ref": source_ref})[:40]
    return {"command_id": command_id, "area_id": area_id, "command_type": f"portfolio_csv_{domain}_handoff_v1", "entity_id": entity_id, "actor_id": context.actor_id, "committed_at_utc": attempted_at, "payload_fingerprint": payload_fp, "origin_type": "native", "origin_ref": None}


def _apply_catalog_effect(data_space: Path, canonical_path: str | Path, context: PortfolioCsvContextV1, effect: Mapping[str, Any], attempted_at: str, failpoint: str | None) -> tuple[int, int, dict[str, Any]]:
    if effect["create_count"]:
        _require_identity_writes_allowed(data_space, context)
    path, initial_connection, _ = _canonical_connection(canonical_path, context)
    initial_connection.close()
    with _DirectoryLock(data_space, "canonical.writer.lock"):
        if effect["create_count"]:
            _require_identity_writes_allowed(data_space, context)
        _, connection, _ = _canonical_connection(path, context, writable=effect["create_count"] > 0)
        try:
            if _catalog_state(connection) != effect["target_state_fingerprint"]:
                _abort("portfolio_csv_handoff_plan_stale")
            created = 0
            if effect["create_count"]:
                connection.execute("BEGIN IMMEDIATE")
                for kind in ("portfolio", "asset", "account", "provider_mapping"):
                    id_field, _, _, _, area_id = CATALOG_FIELDS[kind]
                    for row in effect["creates"][kind]:
                        columns = list(row)
                        connection.execute(f"INSERT INTO {kind} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(row[key] for key in columns))
                        audit = _audit_row("catalog", area_id, row[id_field], next(source for source, target in effect["mapping"].items() if target == row[id_field]), _fingerprint(row), context, attempted_at)
                        connection.execute("INSERT INTO data_command_audit(command_id,area_id,command_type,entity_id,actor_id,committed_at_utc,payload_fingerprint,origin_type,origin_ref) VALUES(?,?,?,?,?,?,?,?,?)", tuple(audit[key] for key in ("command_id","area_id","command_type","entity_id","actor_id","committed_at_utc","payload_fingerprint","origin_type","origin_ref")))
                        created += 1
                        if failpoint == "after_first_effect" and created == 1:
                            _abort("synthetic_portfolio_csv_handoff_failpoint")
                connection.commit()
        except PortfolioCsvHandoffV1Error:
            if connection.in_transaction: connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction: connection.rollback()
            _abort("portfolio_csv_handoff_write_failed")
        finally:
            connection.close()
    try:
        _canonical_snapshot(path, _activity_context(context))
    except DesktopProductAssetActivityV1Error:
        _abort("portfolio_csv_handoff_write_failed")
    return effect["create_count"], effect["reuse_count"], {"mapping": effect["mapping"], "expected": effect["expected"]}


def _apply_transaction_effect(data_space: Path, canonical_path: str | Path, context: PortfolioCsvContextV1, effect: Mapping[str, Any], attempted_at: str, failpoint: str | None) -> tuple[int, int, dict[str, Any]]:
    if effect["create_transaction_count"]:
        _require_identity_writes_allowed(data_space, context)
    path, initial_connection, _ = _canonical_connection(canonical_path, context)
    initial_connection.close()
    with _DirectoryLock(data_space, "canonical.writer.lock"):
        if effect["create_transaction_count"]:
            _require_identity_writes_allowed(data_space, context)
        _, connection, _ = _canonical_connection(path, context, writable=effect["create_transaction_count"] > 0)
        try:
            if _transaction_state(connection) != effect["target_state_fingerprint"]:
                _abort("portfolio_csv_handoff_plan_stale")
            created = 0
            if effect["create_transaction_count"]:
                connection.execute("BEGIN IMMEDIATE")
                for item in effect["new_transactions"]:
                    record = item["record"]; columns = list(record)
                    connection.execute(f"INSERT INTO transaction_record ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", tuple(record[key] for key in columns))
                    for posting in item["postings"]:
                        posting_columns = list(posting)
                        connection.execute(f"INSERT INTO transaction_posting ({','.join(posting_columns)}) VALUES ({','.join('?' for _ in posting_columns)})", tuple(posting[key] for key in posting_columns))
                    seal = item["seal"]; connection.execute("INSERT INTO transaction_seal(transaction_id,sealed_at_utc,posting_count,content_fingerprint) VALUES(?,?,?,?)", tuple(seal[key] for key in ("transaction_id","sealed_at_utc","posting_count","content_fingerprint")))
                    audit = _audit_row("transaction", "transaction_ledger", record["transaction_id"], item["source_ref"], seal["content_fingerprint"], context, attempted_at)
                    connection.execute("INSERT INTO data_command_audit(command_id,area_id,command_type,entity_id,actor_id,committed_at_utc,payload_fingerprint,origin_type,origin_ref) VALUES(?,?,?,?,?,?,?,?,?)", tuple(audit[key] for key in ("command_id","area_id","command_type","entity_id","actor_id","committed_at_utc","payload_fingerprint","origin_type","origin_ref")))
                    created += 1
                    if failpoint == "after_first_effect" and created == 1:
                        _abort("synthetic_portfolio_csv_handoff_failpoint")
                connection.commit()
        except PortfolioCsvHandoffV1Error:
            if connection.in_transaction: connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction: connection.rollback()
            _abort("portfolio_csv_handoff_write_failed")
        finally:
            connection.close()
    try:
        _canonical_snapshot(path, _activity_context(context))
    except DesktopProductAssetActivityV1Error:
        _abort("portfolio_csv_handoff_write_failed")
    return effect["create_transaction_count"], effect["reuse_transaction_count"], {"transaction_mapping": effect["transaction_mapping"], "posting_mapping": effect["posting_mapping"], "expected_transactions": effect["expected_transactions"], "expected_postings": effect["expected_postings"]}


def _apply_activity_effect(data_space: Path, context: PortfolioCsvContextV1, effect: Mapping[str, Any], attempted_at: str, failpoint: str | None) -> tuple[int, int, dict[str, Any]]:
    results = []
    for index, descriptor in enumerate(effect["descriptors"]):
        try:
            result = create_or_reuse_tolerant_csv_activity_draft_v1(
                data_space, _activity_context(context), descriptor["portfolio_id"], descriptor["event"],
                descriptor["source_binding"], descriptor["source_auxiliary"], attempted_at,
            )
        except DesktopActivityDraftV1Error:
            _abort("portfolio_csv_handoff_write_failed")
        trusted = result["trusted_draft"]
        if trusted.get("event", {}).get("event_ref") != descriptor["expected_event_ref"]:
            _abort("portfolio_csv_handoff_effect_conflict")
        results.append({"draft_ref": trusted["draft_ref"], "binding_fingerprint": trusted["source_binding"]["binding_fingerprint"]})
        if failpoint == "after_first_effect" and index == 0:
            _abort("synthetic_portfolio_csv_handoff_failpoint")
    return len(results), 0, {"drafts": results}


def _apply_cash_effect(staged: Path, effect: Mapping[str, Any]) -> tuple[int, int, dict[str, Any]]:
    path = staged / "handoffs" / "cash_coverage" / "reviewed-candidates.json"
    if path.exists() or path.is_symlink():
        if _json_file(path, "portfolio_csv_handoff_effect_conflict") != effect["candidate_bundle"]:
            _abort("portfolio_csv_handoff_effect_conflict")
    else:
        _write_new(path, effect["candidate_bundle"])
    return effect["candidate_count"], 0, {"candidate_bundle_fingerprint": effect["candidate_bundle"]["candidate_bundle_fingerprint"]}


def _apply_effect(domain: str, staged: Path, data_space: Path, canonical_path: str | Path, context: PortfolioCsvContextV1, effect: Mapping[str, Any], attempted_at: str, failpoint: str | None) -> tuple[int, int, dict[str, Any]]:
    if domain == "catalog": return _apply_catalog_effect(data_space, canonical_path, context, effect, attempted_at, failpoint)
    if domain == "coupled_transaction": return _apply_transaction_effect(data_space, canonical_path, context, effect, attempted_at, failpoint)
    if domain == "asset_activity": return _apply_activity_effect(data_space, context, effect, attempted_at, failpoint)
    if domain == "cash_coverage": return _apply_cash_effect(staged, effect)
    _abort("portfolio_csv_handoff_domain_invalid")


def _trusted(trusted: Mapping[str, Any], context: PortfolioCsvContextV1, domain: str) -> dict[str, Any]:
    required = {
        "portfolio_csv_handoff_preview_version", "status", "domain", "staged_import_handle",
        "bundle_fingerprint", "context_fingerprint", "effect", "confirmation_required",
        "one_attempt_only", "automatic_retry", "handoff_plan_fingerprint",
    }
    if not isinstance(trusted, Mapping) or set(trusted) != required:
        _abort("portfolio_csv_handoff_plan_stale")
    body = dict(trusted); fingerprint = body.pop("handoff_plan_fingerprint", None)
    if (fingerprint != _fingerprint(body) or trusted.get("portfolio_csv_handoff_preview_version") != 1
            or trusted.get("domain") != domain or trusted.get("context_fingerprint") != _context_fp(context)
            or trusted.get("status") != "ready_for_confirmation" or trusted.get("confirmation_required") is not True
            or trusted.get("one_attempt_only") is not True or trusted.get("automatic_retry") is not False):
        _abort("portfolio_csv_handoff_plan_stale")
    return dict(trusted)


def _validated_attempt(value: Mapping[str, Any], context: PortfolioCsvContextV1, domain: str, staged_handle: str) -> tuple[dict[str, Any], dict[str, Any]]:
    attempt = _strict_attempt(value)
    if attempt.get("context_fingerprint") != _context_fp(context) or attempt.get("domain") != domain:
        _abort("portfolio_csv_handoff_recovery_invalid")
    try:
        trusted = _trusted(attempt.get("trusted_preview"), context, domain)
        if trusted.get("staged_import_handle") != staged_handle:
            _abort("portfolio_csv_handoff_recovery_invalid")
        _verify_confirmation(attempt.get("confirmation"), trusted, context, attempt["attempted_at_utc"])
    except PortfolioCsvHandoffV1Error:
        _abort("portfolio_csv_handoff_recovery_invalid")
    return attempt, trusted


def _apply(domain: str, data_space_path: str | Path, canonical_path: str | Path, context_value: Any, trusted_preview: Mapping[str, Any], confirmation_value: Mapping[str, Any], applied_at_utc: str, *, failpoint: str | None = None) -> dict[str, Any]:
    if failpoint not in FAILPOINTS:
        _abort("portfolio_csv_handoff_domain_invalid")
    context = _context(context_value); applied = _utc(applied_at_utc, "portfolio_csv_handoff_confirmation_invalid")
    trusted = _trusted(trusted_preview, context, domain); confirmed = _verify_confirmation(confirmation_value, trusted, context, applied, enforce_validity=False)
    data_space, plan, _ = _staged_import(data_space_path, context, trusted["staged_import_handle"])
    staged = data_space / AREA / "imports" / trusted["staged_import_handle"]
    if plan.bundle_fingerprint != trusted["bundle_fingerprint"]:
        _abort("portfolio_csv_handoff_plan_stale")

    def validate_receipt_replay(receipt: Mapping[str, Any]) -> None:
        if (receipt.get("context_fingerprint") != _context_fp(context)
                or receipt.get("bundle_fingerprint") != trusted["bundle_fingerprint"]
                or receipt.get("handoff_plan_fingerprint") != trusted["handoff_plan_fingerprint"]
                or receipt.get("confirmation_fingerprint") != confirmed["confirmation_fingerprint"]):
            _abort("portfolio_csv_handoff_effect_conflict")

    receipt = _handoff_receipt(staged, domain)
    if receipt is not None:
        validate_receipt_replay(receipt)
        return _public_result(receipt, replay=True)
    if not confirmed["issued_at_utc"] <= applied <= confirmed["expires_at_utc"]:
        _abort("portfolio_csv_handoff_confirmation_expired")
    current = _effect(domain, plan, staged, canonical_path, data_space, context)
    if current != trusted["effect"]:
        _abort("portfolio_csv_handoff_plan_stale")
    area = _handoff_area(staged, domain, create=True)
    with _DirectoryLock(area, ".handoff.lock"):
        receipt = _handoff_receipt(staged, domain)
        if receipt is not None:
            validate_receipt_replay(receipt)
            return _public_result(receipt, replay=True)
        attempt_path = area / "attempt.json"
        if attempt_path.exists() or attempt_path.is_symlink():
            _abort("portfolio_csv_handoff_confirmation_consumed")
        current = _effect(domain, plan, staged, canonical_path, data_space, context)
        if current != trusted["effect"]:
            _abort("portfolio_csv_handoff_plan_stale")
        attempt_body = {
            "portfolio_csv_handoff_attempt_version": 1, "status": "confirmation_consumed_before_domain_effect",
            "context_fingerprint": _context_fp(context), "domain": domain, "trusted_preview": trusted,
            "confirmation": confirmed, "attempted_at_utc": applied, "automatic_retry": False,
        }
        attempt = {**attempt_body, "attempt_fingerprint": _fingerprint(attempt_body)}
        _write_new(attempt_path, attempt)
        if failpoint == "after_attempt":
            _abort("synthetic_portfolio_csv_handoff_failpoint")
        created, reused, result_effect = _apply_effect(domain, staged, data_space, canonical_path, context, trusted["effect"], applied, failpoint)
        if failpoint == "after_effect":
            _abort("synthetic_portfolio_csv_handoff_failpoint")
        receipt_body = {
            "portfolio_csv_handoff_receipt_version": 1, "status": "completed", "domain": domain,
            "context_fingerprint": _context_fp(context), "bundle_fingerprint": trusted["bundle_fingerprint"],
            "handoff_plan_fingerprint": trusted["handoff_plan_fingerprint"], "confirmation_fingerprint": confirmed["confirmation_fingerprint"],
            "recovery_confirmation_fingerprint": None, "attempt_fingerprint": attempt["attempt_fingerprint"],
            "committed_at_utc": applied, "created_count": created, "reused_count": reused,
            "canonical_write": domain in {"catalog", "coupled_transaction"} and created > 0,
            "candidate_only": domain in {"asset_activity", "cash_coverage"}, "effect": {**trusted["effect"], **result_effect},
            "other_domain_write": False, "provider_access": False, "network_access": False,
        }
        receipt = {**receipt_body, "receipt_fingerprint": _fingerprint(receipt_body)}
        _write_new(area / "receipt.json", receipt)
        if failpoint in {"after_receipt", "after_first_effect"}:
            _abort("synthetic_portfolio_csv_handoff_failpoint")
        return _public_result(receipt)


def apply_portfolio_csv_catalog_handoff_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, trusted_preview: Mapping[str, Any], confirmation_value: Mapping[str, Any], applied_at_utc: str, *, failpoint: str | None = None) -> dict[str, Any]:
    return _apply("catalog", data_space_path, canonical_path, context_value, trusted_preview, confirmation_value, applied_at_utc, failpoint=failpoint)


def apply_portfolio_csv_transaction_handoff_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, trusted_preview: Mapping[str, Any], confirmation_value: Mapping[str, Any], applied_at_utc: str, *, failpoint: str | None = None) -> dict[str, Any]:
    return _apply("coupled_transaction", data_space_path, canonical_path, context_value, trusted_preview, confirmation_value, applied_at_utc, failpoint=failpoint)


def apply_portfolio_csv_asset_activity_handoff_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, trusted_preview: Mapping[str, Any], confirmation_value: Mapping[str, Any], applied_at_utc: str, *, failpoint: str | None = None) -> dict[str, Any]:
    return _apply("asset_activity", data_space_path, canonical_path, context_value, trusted_preview, confirmation_value, applied_at_utc, failpoint=failpoint)


def apply_portfolio_csv_cash_handoff_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, trusted_preview: Mapping[str, Any], confirmation_value: Mapping[str, Any], applied_at_utc: str, *, failpoint: str | None = None) -> dict[str, Any]:
    return _apply("cash_coverage", data_space_path, canonical_path, context_value, trusted_preview, confirmation_value, applied_at_utc, failpoint=failpoint)


def read_portfolio_csv_staged_imports_v1(data_space_path: str | Path, context_value: Any) -> dict[str, Any]:
    context = _context(context_value); data_space = _bound_data_space(data_space_path, context); imports = data_space / AREA / "imports"
    if not imports.exists() and not imports.is_symlink():
        return {"portfolio_csv_staged_imports_version": 1, "status": "absent", "imports": [], "path_exposed": False, "context_exposed": False, "fingerprint_exposed": False}
    imports = _directory(imports); rows = []
    for staged in sorted(imports.iterdir(), key=lambda path: path.name):
        if staged.is_symlink() or not staged.is_dir() or STAGED.fullmatch(staged.name) is None:
            _abort("portfolio_csv_handoff_staged_import_invalid")
        _, plan, _ = _staged_import(data_space, context, staged.name)
        handoffs = {}
        for domain in DOMAINS:
            receipt = _handoff_receipt(staged, domain)
            attempt_path = staged / "handoffs" / domain / "attempt.json"
            if receipt is not None:
                _validate_receipt_binding(receipt, context, plan.bundle_fingerprint)
                handoffs[domain] = "completed"
            elif attempt_path.exists() or attempt_path.is_symlink():
                _, trusted_attempt = _validated_attempt(_json_file(attempt_path, "portfolio_csv_handoff_recovery_invalid"), context, domain, staged.name)
                if trusted_attempt.get("bundle_fingerprint") != plan.bundle_fingerprint:
                    _abort("portfolio_csv_handoff_recovery_invalid")
                handoffs[domain] = "recovery_required"
            else:
                handoffs[domain] = "pending"
        rows.append({
            "staged_import_handle": staged.name, "record_count": len(plan.records),
            "cash_coverage_status": plan.manifest["dimensions"]["cash_coverage"], "handoffs": handoffs,
        })
    return {"portfolio_csv_staged_imports_version": 1, "status": "available", "imports": rows, "path_exposed": False, "context_exposed": False, "fingerprint_exposed": False}


def read_portfolio_csv_handoff_recovery_candidates_v1(data_space_path: str | Path, context_value: Any) -> dict[str, Any]:
    context = _context(context_value); data_space = _bound_data_space(data_space_path, context); imports = data_space / AREA / "imports"
    if not imports.exists() and not imports.is_symlink():
        return {"portfolio_csv_handoff_recovery_candidates_version": 1, "status": "absent", "candidates": [], "path_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False}
    imports = _directory(imports); candidates = []
    for staged in sorted(imports.iterdir(), key=lambda path: path.name):
        if staged.is_symlink() or not staged.is_dir() or STAGED.fullmatch(staged.name) is None:
            _abort("portfolio_csv_handoff_staged_import_invalid")
        staged = _directory(staged)
        _, plan, _ = _staged_import(data_space, context, staged.name)
        for domain in DOMAINS:
            area = staged / "handoffs" / domain
            attempt_path = area / "attempt.json"
            if not attempt_path.exists() and not attempt_path.is_symlink():
                continue
            attempt, trusted_attempt = _validated_attempt(_json_file(attempt_path, "portfolio_csv_handoff_recovery_invalid"), context, domain, staged.name)
            if trusted_attempt.get("bundle_fingerprint") != plan.bundle_fingerprint:
                _abort("portfolio_csv_handoff_recovery_invalid")
            receipt = _handoff_receipt(staged, domain)
            if receipt is not None:
                _validate_receipt_binding(receipt, context, plan.bundle_fingerprint)
                continue
            recovery_ref = "portfolio_handoff_recovery_" + attempt["attempt_fingerprint"][:32]
            candidates.append({"recovery_ref": recovery_ref, "staged_import_handle": staged.name, "domain": domain, "attempted_at_utc": attempt["attempted_at_utc"], "recovery_reason": "confirmation_consumed_receipt_absent", "automatic_retry": False})
    return {"portfolio_csv_handoff_recovery_candidates_version": 1, "status": "available" if candidates else "absent", "candidates": candidates, "path_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False}


def _find_recovery(data_space: Path, recovery_ref: str) -> tuple[Path, str, dict[str, Any]]:
    if not isinstance(recovery_ref, str) or RECOVERY_REF.fullmatch(recovery_ref) is None:
        _abort("portfolio_csv_handoff_recovery_invalid")
    candidates = []
    imports = data_space / AREA / "imports"
    if imports.exists() or imports.is_symlink():
        for staged in _directory(imports).iterdir():
            if staged.is_symlink() or not staged.is_dir() or STAGED.fullmatch(staged.name) is None:
                _abort("portfolio_csv_handoff_staged_import_invalid")
            staged = _directory(staged)
            for domain in DOMAINS:
                path = staged / "handoffs" / domain / "attempt.json"
                if path.exists() or path.is_symlink():
                    attempt = _strict_attempt(_json_file(path, "portfolio_csv_handoff_recovery_invalid"))
                    if "portfolio_handoff_recovery_" + str(attempt.get("attempt_fingerprint", ""))[:32] == recovery_ref:
                        candidates.append((staged, domain, attempt))
    if len(candidates) != 1:
        _abort("portfolio_csv_handoff_recovery_missing")
    return candidates[0]


def preview_portfolio_csv_handoff_recovery_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, recovery_ref: str) -> dict[str, Any]:
    context = _context(context_value); data_space = _bound_data_space(data_space_path, context); staged, domain, attempt = _find_recovery(data_space, recovery_ref)
    if _handoff_receipt(staged, domain) is not None:
        _abort("portfolio_csv_handoff_recovery_missing")
    attempt, trusted = _validated_attempt(attempt, context, domain, staged.name)
    _, plan, _ = _staged_import(data_space, context, staged.name)
    if plan.bundle_fingerprint != trusted.get("bundle_fingerprint"):
        _abort("portfolio_csv_handoff_recovery_stale")
    effect_state = _reconcile(domain, staged, canonical_path, data_space, context, trusted["effect"], attempt["attempted_at_utc"])
    if effect_state == "conflict" or domain in {"catalog", "coupled_transaction"} and effect_state == "partial":
        _abort("portfolio_csv_handoff_effect_conflict")
    if effect_state == "absent" and _effect(domain, plan, staged, canonical_path, data_space, context) != trusted["effect"]:
        _abort("portfolio_csv_handoff_recovery_stale")
    body = {
        "portfolio_csv_handoff_recovery_preview_version": 1, "status": "ready_for_recovery_confirmation",
        "recovery_ref": recovery_ref, "domain": domain, "staged_import_handle": staged.name,
        "context_fingerprint": _context_fp(context), "attempt_fingerprint": attempt["attempt_fingerprint"],
        "handoff_plan_fingerprint": trusted["handoff_plan_fingerprint"], "effect_state": effect_state,
        "confirmation_required": True, "automatic_retry": False,
    }
    trusted_recovery = {**body, "recovery_plan_fingerprint": _fingerprint(body)}
    public = {
        "portfolio_csv_handoff_recovery_public_preview_version": 1, "status": "ready_for_recovery_confirmation",
        "recovery_ref": recovery_ref, "domain": domain, "staged_import_handle": staged.name,
        "effect_state": effect_state, "recovery_reason": "confirmation_consumed_receipt_absent",
        "confirmation_required": True, "automatic_retry": False,
        "canonical_write": domain in {"catalog", "coupled_transaction"} and effect_state != "complete",
        "asset_activity_fact_write": False, "cash_fact_write": False, "provider_access": False, "network_access": False,
        "path_exposed": False, "context_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False,
    }
    return {"public_preview": public, "trusted_preview": trusted_recovery}


def build_portfolio_csv_handoff_recovery_confirmation_v1(trusted_preview: Mapping[str, Any], context_value: Any, confirmation_ref: str, issued_at_utc: str, expires_at_utc: str) -> dict[str, Any]:
    context = _context(context_value); issued = _utc(issued_at_utc, "portfolio_csv_handoff_recovery_confirmation_invalid"); expires = _utc(expires_at_utc, "portfolio_csv_handoff_recovery_confirmation_invalid")
    required = {
        "portfolio_csv_handoff_recovery_preview_version", "status", "recovery_ref", "domain",
        "staged_import_handle", "context_fingerprint", "attempt_fingerprint",
        "handoff_plan_fingerprint", "effect_state", "confirmation_required", "automatic_retry",
        "recovery_plan_fingerprint",
    }
    body = dict(trusted_preview) if isinstance(trusted_preview, Mapping) else {}; plan_fp = body.pop("recovery_plan_fingerprint", None)
    if (not isinstance(trusted_preview, Mapping) or set(trusted_preview) != required
            or plan_fp != _fingerprint(body) or trusted_preview.get("portfolio_csv_handoff_recovery_preview_version") != 1
            or trusted_preview.get("status") != "ready_for_recovery_confirmation"
            or trusted_preview.get("domain") not in DOMAINS
            or trusted_preview.get("context_fingerprint") != _context_fp(context)
            or trusted_preview.get("confirmation_required") is not True
            or trusted_preview.get("automatic_retry") is not False
            or not isinstance(confirmation_ref, str) or RECOVERY_CONFIRMATION_REF.fullmatch(confirmation_ref) is None
            or issued > expires):
        _abort("portfolio_csv_handoff_recovery_confirmation_invalid")
    confirmation_body = {
        "portfolio_csv_handoff_recovery_confirmation_version": 1, "authorization_scope": "portfolio_csv_domain_handoff_recovery_once",
        "confirmation_ref": confirmation_ref, "recovery_ref": trusted_preview["recovery_ref"],
        "domain": trusted_preview["domain"], "recovery_plan_fingerprint": plan_fp,
        "context_fingerprint": _context_fp(context), "issued_at_utc": issued, "expires_at_utc": expires,
        "confirmed": True, "automatic_retry_authorized": False, "other_domain_write_authorized": False,
    }
    return {**confirmation_body, "recovery_confirmation_fingerprint": _fingerprint(confirmation_body)}


def _verify_recovery_confirmation(value: Mapping[str, Any], trusted: Mapping[str, Any], context: PortfolioCsvContextV1, at: str, *, enforce_validity: bool = True) -> dict[str, Any]:
    required = {"portfolio_csv_handoff_recovery_confirmation_version", "authorization_scope", "confirmation_ref", "recovery_ref", "domain", "recovery_plan_fingerprint", "context_fingerprint", "issued_at_utc", "expires_at_utc", "confirmed", "automatic_retry_authorized", "other_domain_write_authorized", "recovery_confirmation_fingerprint"}
    if not isinstance(value, Mapping) or set(value) != required:
        _abort("portfolio_csv_handoff_recovery_confirmation_invalid")
    body = dict(value); fingerprint = body.pop("recovery_confirmation_fingerprint")
    if fingerprint != _fingerprint(body) or body["portfolio_csv_handoff_recovery_confirmation_version"] != 1 or body["authorization_scope"] != "portfolio_csv_domain_handoff_recovery_once" or body["recovery_ref"] != trusted.get("recovery_ref") or body["domain"] != trusted.get("domain") or body["recovery_plan_fingerprint"] != trusted.get("recovery_plan_fingerprint") or body["context_fingerprint"] != _context_fp(context) or body["confirmed"] is not True or body["automatic_retry_authorized"] is not False or body["other_domain_write_authorized"] is not False or not isinstance(body["confirmation_ref"], str) or RECOVERY_CONFIRMATION_REF.fullmatch(body["confirmation_ref"]) is None:
        _abort("portfolio_csv_handoff_recovery_confirmation_invalid")
    issued = _utc(body["issued_at_utc"], "portfolio_csv_handoff_recovery_confirmation_invalid"); expires = _utc(body["expires_at_utc"], "portfolio_csv_handoff_recovery_confirmation_invalid")
    if enforce_validity and not issued <= at <= expires:
        _abort("portfolio_csv_handoff_recovery_confirmation_invalid")
    return {**body, "recovery_confirmation_fingerprint": fingerprint}


def apply_portfolio_csv_handoff_recovery_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, trusted_recovery_preview: Mapping[str, Any], recovery_confirmation_value: Mapping[str, Any], recovered_at_utc: str, *, failpoint: str | None = None) -> dict[str, Any]:
    if failpoint not in FAILPOINTS:
        _abort("portfolio_csv_handoff_recovery_invalid")
    context = _context(context_value); recovered = _utc(recovered_at_utc, "portfolio_csv_handoff_recovery_confirmation_invalid")
    recovery_required = {
        "portfolio_csv_handoff_recovery_preview_version", "status", "recovery_ref", "domain",
        "staged_import_handle", "context_fingerprint", "attempt_fingerprint",
        "handoff_plan_fingerprint", "effect_state", "confirmation_required", "automatic_retry",
        "recovery_plan_fingerprint",
    }
    body = dict(trusted_recovery_preview) if isinstance(trusted_recovery_preview, Mapping) else {}; recovery_plan_fp = body.pop("recovery_plan_fingerprint", None)
    if (not isinstance(trusted_recovery_preview, Mapping) or set(trusted_recovery_preview) != recovery_required or recovery_plan_fp != _fingerprint(body)
            or trusted_recovery_preview.get("portfolio_csv_handoff_recovery_preview_version") != 1
            or trusted_recovery_preview.get("status") != "ready_for_recovery_confirmation"
            or trusted_recovery_preview.get("context_fingerprint") != _context_fp(context)
            or trusted_recovery_preview.get("confirmation_required") is not True
            or trusted_recovery_preview.get("automatic_retry") is not False):
        _abort("portfolio_csv_handoff_recovery_invalid")
    confirmation = _verify_recovery_confirmation(recovery_confirmation_value, trusted_recovery_preview, context, recovered, enforce_validity=False)
    data_space = _bound_data_space(data_space_path, context)
    staged, domain, attempt = _find_recovery(data_space, trusted_recovery_preview["recovery_ref"])
    if domain != trusted_recovery_preview.get("domain") or staged.name != trusted_recovery_preview.get("staged_import_handle"):
        _abort("portfolio_csv_handoff_recovery_invalid")
    attempt, trusted = _validated_attempt(attempt, context, domain, staged.name)
    if (attempt.get("attempt_fingerprint") != trusted_recovery_preview.get("attempt_fingerprint")
            or trusted.get("handoff_plan_fingerprint") != trusted_recovery_preview.get("handoff_plan_fingerprint")):
        _abort("portfolio_csv_handoff_recovery_stale")
    _, current_plan, _ = _staged_import(data_space, context, staged.name)
    if current_plan.bundle_fingerprint != trusted.get("bundle_fingerprint"):
        _abort("portfolio_csv_handoff_recovery_stale")
    area = _handoff_area(staged, domain, create=False)

    def validate_receipt_replay(receipt: Mapping[str, Any]) -> None:
        if (receipt.get("context_fingerprint") != _context_fp(context)
                or receipt.get("bundle_fingerprint") != trusted["bundle_fingerprint"]
                or receipt.get("handoff_plan_fingerprint") != trusted["handoff_plan_fingerprint"]
                or receipt.get("attempt_fingerprint") != attempt["attempt_fingerprint"]
                or receipt.get("recovery_confirmation_fingerprint") != confirmation["recovery_confirmation_fingerprint"]):
            _abort("portfolio_csv_handoff_effect_conflict")

    receipt = _handoff_receipt(staged, domain)
    if receipt is not None:
        validate_receipt_replay(receipt)
        return _public_result(receipt, replay=True)
    if not confirmation["issued_at_utc"] <= recovered <= confirmation["expires_at_utc"]:
        _abort("portfolio_csv_handoff_recovery_confirmation_invalid")

    def reconcile_current(plan_value: Any) -> str:
        state = _reconcile(domain, staged, canonical_path, data_space, context, trusted["effect"], attempt["attempted_at_utc"])
        if state == "conflict" or domain in {"catalog", "coupled_transaction"} and state == "partial":
            _abort("portfolio_csv_handoff_effect_conflict")
        if state == "absent" and _effect(domain, plan_value, staged, canonical_path, data_space, context) != trusted["effect"]:
            _abort("portfolio_csv_handoff_recovery_stale")
        return state

    current_state = reconcile_current(current_plan)
    with _DirectoryLock(area, ".handoff.lock"):
        receipt = _handoff_receipt(staged, domain)
        if receipt is not None:
            validate_receipt_replay(receipt)
            return _public_result(receipt, replay=True)
        locked_attempt = _strict_attempt(_json_file(area / "attempt.json", "portfolio_csv_handoff_recovery_invalid"))
        if locked_attempt != attempt:
            _abort("portfolio_csv_handoff_recovery_stale")
        _, current_plan, _ = _staged_import(data_space, context, staged.name)
        if current_plan.bundle_fingerprint != trusted["bundle_fingerprint"]:
            _abort("portfolio_csv_handoff_recovery_stale")
        current_state = reconcile_current(current_plan)
        recovery_attempt_body = {
            "portfolio_csv_handoff_recovery_attempt_version": 1, "status": "recovery_confirmation_consumed",
            "context_fingerprint": _context_fp(context), "recovery_plan_fingerprint": recovery_plan_fp,
            "recovery_confirmation_fingerprint": confirmation["recovery_confirmation_fingerprint"], "attempted_at_utc": recovered,
        }
        recovery_attempt = {**recovery_attempt_body, "recovery_attempt_fingerprint": _fingerprint(recovery_attempt_body)}
        recovery_attempt_path = area / "recovery-attempt.json"
        _write_or_match(recovery_attempt_path, recovery_attempt, "portfolio_csv_handoff_recovery_confirmation_consumed")
        if failpoint == "after_attempt":
            _abort("synthetic_portfolio_csv_handoff_failpoint")
        if current_state != "complete":
            created, reused, result_effect = _apply_effect(domain, staged, data_space, canonical_path, context, trusted["effect"], attempt["attempted_at_utc"], failpoint)
        else:
            effect = trusted["effect"]
            created = effect.get("create_count", effect.get("create_transaction_count", effect.get("draft_count", effect.get("candidate_count", 0))))
            reused = effect.get("reuse_count", effect.get("reuse_transaction_count", 0)); result_effect = {}
        if failpoint == "after_effect":
            _abort("synthetic_portfolio_csv_handoff_failpoint")
        receipt_body = {
            "portfolio_csv_handoff_receipt_version": 1, "status": "recovered_completed", "domain": domain,
            "context_fingerprint": _context_fp(context), "bundle_fingerprint": trusted["bundle_fingerprint"],
            "handoff_plan_fingerprint": trusted["handoff_plan_fingerprint"],
            "confirmation_fingerprint": attempt["confirmation"]["confirmation_fingerprint"],
            "recovery_confirmation_fingerprint": confirmation["recovery_confirmation_fingerprint"],
            "attempt_fingerprint": attempt["attempt_fingerprint"], "committed_at_utc": attempt["attempted_at_utc"],
            "created_count": created, "reused_count": reused,
            "canonical_write": domain in {"catalog", "coupled_transaction"} and created > 0,
            "candidate_only": domain in {"asset_activity", "cash_coverage"}, "effect": {**trusted["effect"], **result_effect},
            "other_domain_write": False, "provider_access": False, "network_access": False,
        }
        receipt = {**receipt_body, "receipt_fingerprint": _fingerprint(receipt_body)}
        _write_new(area / "receipt.json", receipt)
        if failpoint in {"after_receipt", "after_first_effect"}:
            _abort("synthetic_portfolio_csv_handoff_failpoint")
        return _public_result(receipt)


def _strict_cash_candidate_bundle(value: Mapping[str, Any], context: PortfolioCsvContextV1, bundle_fingerprint: str) -> dict[str, Any]:
    required = {
        "portfolio_csv_cash_candidate_bundle_version", "status", "context_fingerprint",
        "bundle_fingerprint", "candidates", "cash_fact_write", "canonical_write",
        "asset_activity_write", "provider_access", "network_access", "candidate_bundle_fingerprint",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        _abort("portfolio_csv_handoff_cash_candidate_invalid")
    body = dict(value); fingerprint = body.pop("candidate_bundle_fingerprint")
    if (fingerprint != _fingerprint(body) or value["portfolio_csv_cash_candidate_bundle_version"] != 1
            or value["status"] != "reviewed_candidates_staged" or value["context_fingerprint"] != _context_fp(context)
            or value["bundle_fingerprint"] != bundle_fingerprint or not isinstance(value["candidates"], list)
            or value["cash_fact_write"] is not False or value["canonical_write"] is not False
            or value["asset_activity_write"] is not False or value["provider_access"] is not False
            or value["network_access"] is not False):
        _abort("portfolio_csv_handoff_cash_candidate_invalid")
    seen_refs: set[str] = set(); seen_fingerprints: set[str] = set()
    for candidate in value["candidates"]:
        fields = {"candidate_ref", "source_candidate_fingerprint", "record_refs", "mapped_command", "linked_source_candidate_fingerprint"}
        if (not isinstance(candidate, dict) or set(candidate) != fields
                or not isinstance(candidate["candidate_ref"], str) or CANDIDATE_REF.fullmatch(candidate["candidate_ref"]) is None
                or not isinstance(candidate["source_candidate_fingerprint"], str) or SHA.fullmatch(candidate["source_candidate_fingerprint"]) is None
                or candidate["candidate_ref"] in seen_refs or candidate["source_candidate_fingerprint"] in seen_fingerprints
                or not isinstance(candidate["record_refs"], list) or not candidate["record_refs"]
                or any(not isinstance(item, str) for item in candidate["record_refs"])
                or not isinstance(candidate["mapped_command"], dict)
                or candidate["linked_source_candidate_fingerprint"] is not None and (not isinstance(candidate["linked_source_candidate_fingerprint"], str) or SHA.fullmatch(candidate["linked_source_candidate_fingerprint"]) is None)):
            _abort("portfolio_csv_handoff_cash_candidate_invalid")
        seen_refs.add(candidate["candidate_ref"]); seen_fingerprints.add(candidate["source_candidate_fingerprint"])
    if any(candidate["linked_source_candidate_fingerprint"] is not None and candidate["linked_source_candidate_fingerprint"] not in seen_fingerprints for candidate in value["candidates"]):
        _abort("portfolio_csv_handoff_cash_candidate_invalid")
    return dict(value)


def read_portfolio_csv_cash_candidates_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, staged_handle: str) -> dict[str, Any]:
    context = _context(context_value); data_space, plan, _ = _staged_import(data_space_path, context, staged_handle); staged = data_space / AREA / "imports" / staged_handle
    _catalog_mapping(staged, context, canonical_path, plan.bundle_fingerprint)
    receipt = _handoff_receipt(staged, "cash_coverage", required=True); bundle = _strict_cash_candidate_bundle(_json_file(staged / "handoffs" / "cash_coverage" / "reviewed-candidates.json", "portfolio_csv_handoff_cash_candidate_invalid"), context, receipt["bundle_fingerprint"])
    receipt_effect = receipt.get("effect", {})
    expected_bundle_fingerprint = receipt_effect.get("candidate_bundle_fingerprint") or receipt_effect.get("candidate_bundle", {}).get("candidate_bundle_fingerprint")
    if bundle.get("candidate_bundle_fingerprint") != expected_bundle_fingerprint:
        _abort("portfolio_csv_handoff_cash_candidate_invalid")
    applied: set[str] = set(); store = data_space / "cash-coverage-v1" / "cash-coverage.sqlite"
    if store.exists() or store.is_symlink():
        try:
            import_state = read_desktop_cash_coverage_reviewed_import_state_v1(store, _activity_context(context))
            applied = set(import_state["applied_source_candidate_fingerprints"])
        except DesktopCashCoverageV1Error:
            _abort("portfolio_csv_handoff_cash_candidate_invalid")
    candidates = []
    for item in bundle["candidates"]:
        linked = item["linked_source_candidate_fingerprint"]
        status = "committed" if item["source_candidate_fingerprint"] in applied else "blocked_dependency" if linked is not None and linked not in applied else "ready_for_cash_review"
        candidates.append({"candidate_ref": item["candidate_ref"], "action_type": item["mapped_command"]["action_type"], "status": status, "linked_candidate_required": linked is not None})
    return {"portfolio_csv_cash_candidates_version": 1, "status": "available", "staged_import_handle": staged_handle, "candidates": candidates, "path_exposed": False, "context_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False}


def resolve_portfolio_csv_cash_candidate_v1(data_space_path: str | Path, canonical_path: str | Path, context_value: Any, staged_handle: str, candidate_ref: str) -> dict[str, Any]:
    if not isinstance(candidate_ref, str) or CANDIDATE_REF.fullmatch(candidate_ref) is None:
        _abort("portfolio_csv_handoff_cash_candidate_invalid")
    context = _context(context_value); data_space, plan, _ = _staged_import(data_space_path, context, staged_handle); staged = data_space / AREA / "imports" / staged_handle
    _catalog_mapping(staged, context, canonical_path, plan.bundle_fingerprint)
    receipt = _handoff_receipt(staged, "cash_coverage", required=True); bundle = _strict_cash_candidate_bundle(_json_file(staged / "handoffs" / "cash_coverage" / "reviewed-candidates.json", "portfolio_csv_handoff_cash_candidate_invalid"), context, receipt["bundle_fingerprint"])
    matches = [item for item in bundle.get("candidates", []) if item.get("candidate_ref") == candidate_ref]
    if len(matches) != 1:
        _abort("portfolio_csv_handoff_cash_candidate_invalid")
    item = matches[0]; command = dict(item["mapped_command"]); linked_fp = item["linked_source_candidate_fingerprint"]
    if linked_fp is not None:
        store = data_space / "cash-coverage-v1" / "cash-coverage.sqlite"
        if not store.exists() and not store.is_symlink():
            _abort("portfolio_csv_handoff_dependency_missing")
        try:
            import_state = read_desktop_cash_coverage_reviewed_import_state_v1(store, _activity_context(context))
        except DesktopCashCoverageV1Error:
            _abort("portfolio_csv_handoff_cash_candidate_invalid")
        refs = import_state["active_cash_event_refs_by_source_candidate_fingerprint"].get(linked_fp, [])
        if len(refs) != 1:
            _abort("portfolio_csv_handoff_dependency_missing")
        command["linked_cash_event_ref"] = refs[0]
    reviewed = {"reviewed_cash_coverage_candidate_version": 1, "source_candidate_fingerprint": item["source_candidate_fingerprint"], "mapped_command": command}
    return {"public_candidate": {"candidate_ref": candidate_ref, "action_type": command["action_type"], "status": "ready_for_cash_review", "confirmation_required": True, "cash_fact_write": False, "path_exposed": False, "internal_id_exposed": False, "fingerprint_exposed": False}, "trusted_candidate": reviewed}


__all__ = [
    "PortfolioCsvHandoffV1Error", "apply_portfolio_csv_asset_activity_handoff_v1",
    "apply_portfolio_csv_catalog_handoff_v1", "apply_portfolio_csv_cash_handoff_v1",
    "apply_portfolio_csv_handoff_recovery_v1", "apply_portfolio_csv_transaction_handoff_v1",
    "build_portfolio_csv_handoff_confirmation_v1", "build_portfolio_csv_handoff_recovery_confirmation_v1",
    "preview_portfolio_csv_asset_activity_handoff_v1", "preview_portfolio_csv_catalog_handoff_v1",
    "preview_portfolio_csv_cash_handoff_v1", "preview_portfolio_csv_handoff_recovery_v1",
    "preview_portfolio_csv_transaction_handoff_v1", "read_portfolio_csv_cash_candidates_v1",
    "read_portfolio_csv_handoff_recovery_candidates_v1", "read_portfolio_csv_staged_imports_v1",
    "resolve_portfolio_csv_cash_candidate_v1",
]
