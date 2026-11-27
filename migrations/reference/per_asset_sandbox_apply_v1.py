"""Data-owned immutable sandbox application for a ready per-Asset Trade plan.

This boundary consumes a one-use confirmation and publishes one new owner-only
staging bundle. It intentionally does not open or mutate canonical storage. The
bundle is a rebuild/cutover candidate with exact Asset Activity and FIFO evidence.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tempfile
from typing import Any

from migrations.reference.legacy_per_asset_trade_planner_v1 import (
    LegacyPerAssetTradePlannerV1Error,
    plan_legacy_per_asset_trade_v1,
)

CONTRACT_VERSION = 1
SCHEMA_VERSION = 11901
ALLOWED_ROLES = frozenset({"desktop_owner", "data_admin"})
ALLOWED_FAILPOINTS = frozenset({None, "after_schema", "after_rows", "after_reconciliation", "after_manifest", "after_success", "after_publish"})
FAILURE_CODES = frozenset(
    {
        "per_asset_sandbox_apply_boundary_failed",
        "per_asset_sandbox_apply_confirmation_consumed",
        "per_asset_sandbox_apply_confirmation_duplicate",
        "per_asset_sandbox_apply_confirmation_expired",
        "per_asset_sandbox_apply_confirmation_invalid",
        "per_asset_sandbox_apply_confirmation_missing",
        "per_asset_sandbox_apply_confirmation_not_authorized",
        "per_asset_sandbox_apply_confirmation_scope_mismatch",
        "per_asset_sandbox_apply_context_invalid",
        "per_asset_sandbox_apply_integrity_invalid",
        "per_asset_sandbox_apply_plan_invalid",
        "per_asset_sandbox_apply_plan_not_ready",
        "per_asset_sandbox_apply_role_not_authorized",
        "per_asset_sandbox_apply_target_conflict",
        "per_asset_sandbox_apply_target_invalid",
        "per_asset_sandbox_apply_write_failed",
        "synthetic_per_asset_sandbox_apply_failpoint",
    }
)
_REF = re.compile(r"[a-z]{2,8}_[a-f0-9]{16,64}")
_SHA = re.compile(r"[a-f0-9]{64}")
_CHALLENGE = re.compile(r"pac_[a-f0-9]{16,64}")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_SAFE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,119}")


class PerAssetSandboxApplyV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("per_asset_sandbox_apply_error_code_unregistered")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PerAssetSandboxContextV1:
    tenant_ref: str
    user_ref: str
    data_space_ref: str
    actor_ref: str
    role: str


@dataclass(frozen=True)
class PerAssetSandboxTargetCapabilityV1:
    root: Path
    bundle_name: str
    context_fingerprint: str


@dataclass(frozen=True)
class PerAssetSandboxApplyResultV1:
    status: str
    bundle_ref: str
    plan_fingerprint: str
    receipt_fingerprint: str
    output_created: bool
    canonical_write: bool = False


class OneUsePerAssetSandboxAuthorizerV1:
    def __init__(self) -> None:
        self._registered: dict[str, str] = {}
        self._consumed: set[str] = set()

    def register(self, confirmation: dict[str, Any]) -> None:
        if not isinstance(confirmation, dict):
            _abort("per_asset_sandbox_apply_confirmation_invalid")
        challenge = confirmation.get("challenge_id")
        fingerprint = confirmation.get("confirmation_fingerprint")
        if not isinstance(challenge, str) or _CHALLENGE.fullmatch(challenge) is None or not isinstance(fingerprint, str) or _SHA.fullmatch(fingerprint) is None:
            _abort("per_asset_sandbox_apply_confirmation_invalid")
        if challenge in self._registered:
            _abort("per_asset_sandbox_apply_confirmation_duplicate")
        self._registered[challenge] = fingerprint

    def consume(self, challenge: str, fingerprint: str) -> None:
        expected = self._registered.get(challenge)
        if expected is None or expected != fingerprint:
            _abort("per_asset_sandbox_apply_confirmation_not_authorized")
        if challenge in self._consumed:
            _abort("per_asset_sandbox_apply_confirmation_consumed")
        self._consumed.add(challenge)

    def is_consumed(self, challenge: str) -> bool:
        return challenge in self._consumed


def per_asset_sandbox_apply_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise PerAssetSandboxApplyV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except Exception:
        _abort("per_asset_sandbox_apply_plan_invalid")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort(code)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort(code)


def _context(context: Any) -> PerAssetSandboxContextV1:
    if not isinstance(context, PerAssetSandboxContextV1):
        _abort("per_asset_sandbox_apply_context_invalid")
    if any(not isinstance(value, str) or _REF.fullmatch(value) is None for value in (context.tenant_ref, context.user_ref, context.data_space_ref, context.actor_ref)):
        _abort("per_asset_sandbox_apply_context_invalid")
    if context.role not in ALLOWED_ROLES:
        _abort("per_asset_sandbox_apply_role_not_authorized")
    return context


def _context_fingerprint(context: PerAssetSandboxContextV1) -> str:
    return _fingerprint(
        {
            "capability_kind": "per_asset_sandbox_target_v1",
            "tenant_ref": context.tenant_ref,
            "user_ref": context.user_ref,
            "data_space_ref": context.data_space_ref,
            "actor_ref": context.actor_ref,
            "role": context.role,
        }
    )


def _existing_owner_root(root_value: Any) -> Path:
    if not isinstance(root_value, Path) or not root_value.is_absolute():
        _abort("per_asset_sandbox_apply_target_invalid")
    current = root_value
    while True:
        if current.is_symlink():
            _abort("per_asset_sandbox_apply_target_invalid")
        if current.parent == current:
            break
        current = current.parent
    try:
        root = root_value.resolve(strict=True)
        metadata = root.stat(follow_symlinks=False)
    except OSError:
        _abort("per_asset_sandbox_apply_target_invalid")
    if (
        not root.is_dir()
        or root.is_symlink()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.geteuid()
    ):
        _abort("per_asset_sandbox_apply_target_invalid")
    return root


def new_per_asset_sandbox_target_capability_v1(
    root: Path,
    bundle_name: str,
    context: PerAssetSandboxContextV1,
) -> PerAssetSandboxTargetCapabilityV1:
    runtime = _context(context)
    owner_root = _existing_owner_root(root)
    if not isinstance(bundle_name, str) or _SAFE_NAME.fullmatch(bundle_name) is None:
        _abort("per_asset_sandbox_apply_target_invalid")
    return PerAssetSandboxTargetCapabilityV1(
        owner_root,
        bundle_name,
        _context_fingerprint(runtime),
    )


def _target_capability(
    capability: Any,
    context: PerAssetSandboxContextV1,
) -> tuple[Path, Path]:
    if not isinstance(capability, PerAssetSandboxTargetCapabilityV1):
        _abort("per_asset_sandbox_apply_target_invalid")
    rebuilt = new_per_asset_sandbox_target_capability_v1(
        capability.root,
        capability.bundle_name,
        context,
    )
    if rebuilt != capability:
        _abort("per_asset_sandbox_apply_target_invalid")
    return capability.root / capability.bundle_name, capability.root


def _plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        _abort("per_asset_sandbox_apply_plan_invalid")
    body = dict(plan)
    fingerprint = body.pop("plan_fingerprint", None)
    if (
        not isinstance(fingerprint, str)
        or _SHA.fullmatch(fingerprint) is None
        or fingerprint != _fingerprint(body)
        or plan.get("per_asset_trade_plan_version") != 1
        or plan.get("plan_status") not in {"ready_for_sandbox_apply", "ready_for_sandbox_apply_with_incomplete_basis"}
        or plan.get("source_row_count") != plan.get("ready_row_count")
        or plan.get("decision_required_row_count") != 0
        or plan.get("blocked_row_count") != 0
        or plan.get("source_row_disposition_complete") is not True
        or plan.get("fifo_full_oracle_executed") is not True
        or not isinstance(plan.get("fifo_reconciliation"), dict)
        or plan.get("automatic_cash_posting_count") != 0
        or plan.get("canonical_write") is not False
        or plan.get("provider_access") is not False
        or plan.get("network_access") is not False
    ):
        _abort("per_asset_sandbox_apply_plan_not_ready")
    rows = plan.get("rows")
    if not isinstance(rows, list) or not rows or any(
        not isinstance(row, dict)
        or row.get("disposition") != "ready"
        or not isinstance(row.get("activity_event"), dict)
        or not isinstance(row.get("activity_effect"), dict)
        or row.get("cash_posting_created") is not False
        or row["activity_effect"].get("cash_posting_created") is not False
        for row in rows
    ):
        _abort("per_asset_sandbox_apply_plan_not_ready")
    fifo = plan["fifo_reconciliation"]
    fifo_body = dict(fifo)
    fifo_fp = fifo_body.pop("fifo_reconciliation_fingerprint", None)
    if (
        fifo_fp != _fingerprint(fifo_body)
        or fifo.get("cash_posting_count") != 0
        or fifo.get("synthetic_cash_posting_created") is not False
        or fifo.get("provider_price_used") is not False
        or fifo.get("tax_classification_inferred") is not False
    ):
        _abort("per_asset_sandbox_apply_plan_invalid")
    return plan


def build_per_asset_sandbox_confirmation_v1(
    plan: Any,
    context: PerAssetSandboxContextV1,
    challenge_id: str,
    issued_at_utc: str,
    confirmed_at_utc: str,
    expires_at_utc: str,
) -> dict[str, Any]:
    validated = _plan(plan)
    runtime = _context(context)
    if not isinstance(challenge_id, str) or _CHALLENGE.fullmatch(challenge_id) is None:
        _abort("per_asset_sandbox_apply_confirmation_invalid")
    issued = _utc(issued_at_utc, "per_asset_sandbox_apply_confirmation_invalid")
    confirmed = _utc(confirmed_at_utc, "per_asset_sandbox_apply_confirmation_invalid")
    expires = _utc(expires_at_utc, "per_asset_sandbox_apply_confirmation_invalid")
    if not (issued <= confirmed <= expires) or (expires - issued).total_seconds() > 600:
        _abort("per_asset_sandbox_apply_confirmation_expired")
    payload = {
        "per_asset_sandbox_confirmation_version": 1,
        "challenge_id": challenge_id,
        "tenant_ref": runtime.tenant_ref,
        "user_ref": runtime.user_ref,
        "data_space_ref": runtime.data_space_ref,
        "actor_ref": runtime.actor_ref,
        "role": runtime.role,
        "plan_fingerprint": validated["plan_fingerprint"],
        "projection_fingerprint": validated["projection_fingerprint"],
        "source_asset_link_fingerprint": validated["source_asset_link_fingerprint"],
        "target_asset_ref": validated["target_asset_ref"],
        "source_row_count": validated["source_row_count"],
        "fifo_reconciliation_fingerprint": validated["fifo_reconciliation"]["fifo_reconciliation_fingerprint"],
        "issued_at_utc": issued_at_utc,
        "confirmed_at_utc": confirmed_at_utc,
        "expires_at_utc": expires_at_utc,
    }
    return {**payload, "confirmation_fingerprint": _fingerprint(payload)}


def _confirmation(
    confirmation: Any,
    plan: dict[str, Any],
    context: PerAssetSandboxContextV1,
    authorizer: OneUsePerAssetSandboxAuthorizerV1,
    now_utc: str,
) -> dict[str, Any]:
    if confirmation is None:
        _abort("per_asset_sandbox_apply_confirmation_missing")
    if not isinstance(confirmation, dict):
        _abort("per_asset_sandbox_apply_confirmation_invalid")
    expected_keys = {
        "per_asset_sandbox_confirmation_version", "challenge_id", "tenant_ref", "user_ref", "data_space_ref",
        "actor_ref", "role", "plan_fingerprint", "projection_fingerprint", "source_asset_link_fingerprint",
        "target_asset_ref", "source_row_count", "fifo_reconciliation_fingerprint", "issued_at_utc", "confirmed_at_utc",
        "expires_at_utc", "confirmation_fingerprint",
    }
    if set(confirmation) != expected_keys:
        _abort("per_asset_sandbox_apply_confirmation_invalid")
    body = {key: value for key, value in confirmation.items() if key != "confirmation_fingerprint"}
    if confirmation.get("confirmation_fingerprint") != _fingerprint(body):
        _abort("per_asset_sandbox_apply_confirmation_invalid")
    expected = {
        "per_asset_sandbox_confirmation_version": 1,
        "tenant_ref": context.tenant_ref, "user_ref": context.user_ref, "data_space_ref": context.data_space_ref,
        "actor_ref": context.actor_ref, "role": context.role, "plan_fingerprint": plan["plan_fingerprint"],
        "projection_fingerprint": plan["projection_fingerprint"], "source_asset_link_fingerprint": plan["source_asset_link_fingerprint"],
        "target_asset_ref": plan["target_asset_ref"], "source_row_count": plan["source_row_count"],
        "fifo_reconciliation_fingerprint": plan["fifo_reconciliation"]["fifo_reconciliation_fingerprint"],
    }
    if any(confirmation.get(key) != value for key, value in expected.items()):
        _abort("per_asset_sandbox_apply_confirmation_scope_mismatch")
    issued = _utc(confirmation["issued_at_utc"], "per_asset_sandbox_apply_confirmation_invalid")
    confirmed = _utc(confirmation["confirmed_at_utc"], "per_asset_sandbox_apply_confirmation_invalid")
    expires = _utc(confirmation["expires_at_utc"], "per_asset_sandbox_apply_confirmation_invalid")
    now = _utc(now_utc, "per_asset_sandbox_apply_confirmation_invalid")
    if not (issued <= confirmed <= now <= expires) or (expires - issued).total_seconds() > 600:
        _abort("per_asset_sandbox_apply_confirmation_expired")
    if not isinstance(authorizer, OneUsePerAssetSandboxAuthorizerV1):
        _abort("per_asset_sandbox_apply_confirmation_not_authorized")
    return confirmation


def _bundle_ref(plan: dict[str, Any], context: PerAssetSandboxContextV1) -> str:
    return "pas_" + hashlib.sha256(
        ("per-asset-sandbox-v1\0" + context.tenant_ref + "\0" + context.user_ref + "\0" + context.data_space_ref + "\0" + plan["plan_fingerprint"]).encode("ascii")
    ).hexdigest()[:32]


def _command_ref(plan: dict[str, Any], context: PerAssetSandboxContextV1) -> str:
    return "cmd_" + hashlib.sha256(
        ("per-asset-sandbox-apply-v1\0" + context.actor_ref + "\0" + context.data_space_ref + "\0" + plan["plan_fingerprint"]).encode("ascii")
    ).hexdigest()[:32]


def _write(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except Exception:
        _abort("per_asset_sandbox_apply_write_failed")


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except Exception:
        _abort("per_asset_sandbox_apply_write_failed")


def _rename_noreplace(source: Path, destination: Path) -> None:
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        _abort("per_asset_sandbox_apply_write_failed")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)
    if result == 0:
        return
    number = ctypes.get_errno()
    if number in {errno.EEXIST, errno.ENOTEMPTY}:
        _abort("per_asset_sandbox_apply_target_conflict")
    _abort("per_asset_sandbox_apply_write_failed")


def _schema_sql() -> str:
    return """
PRAGMA foreign_keys=ON;
PRAGMA user_version=11901;
CREATE TABLE sandbox_binding(
 singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1), schema_version INTEGER NOT NULL CHECK(schema_version=11901),
 contract_version INTEGER NOT NULL CHECK(contract_version=1), tenant_ref TEXT NOT NULL, user_ref TEXT NOT NULL,
 data_space_ref TEXT NOT NULL, target_asset_ref TEXT NOT NULL, plan_fingerprint TEXT NOT NULL UNIQUE,
 projection_fingerprint TEXT NOT NULL, source_asset_link_fingerprint TEXT NOT NULL, command_ref TEXT NOT NULL UNIQUE,
 confirmation_fingerprint TEXT NOT NULL, applied_at_utc TEXT NOT NULL
) STRICT;
CREATE TABLE staged_asset_event(
 source_row_ref TEXT PRIMARY KEY, source_row_ordinal INTEGER NOT NULL UNIQUE CHECK(source_row_ordinal>0),
 source_row_fingerprint TEXT NOT NULL UNIQUE, event_ref TEXT NOT NULL UNIQUE, event_type TEXT NOT NULL,
 account_ref TEXT NOT NULL, related_account_ref TEXT, asset_ref TEXT NOT NULL, local_date TEXT NOT NULL,
 local_time TEXT, time_zone TEXT NOT NULL, effective_at_utc TEXT, event_json TEXT NOT NULL,
 effect_json TEXT NOT NULL, memo TEXT, cash_posting_created INTEGER NOT NULL CHECK(cash_posting_created=0)
) STRICT;
CREATE TABLE staged_fifo_reconciliation(
 singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1), fifo_status TEXT NOT NULL,
 fifo_reconciliation_fingerprint TEXT NOT NULL UNIQUE, reconciliation_json TEXT NOT NULL,
 cash_posting_count INTEGER NOT NULL CHECK(cash_posting_count=0), provider_price_used INTEGER NOT NULL CHECK(provider_price_used=0),
 tax_classification_inferred INTEGER NOT NULL CHECK(tax_classification_inferred=0)
) STRICT;
CREATE TABLE sandbox_apply_receipt(
 singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1), bundle_ref TEXT NOT NULL UNIQUE, command_ref TEXT NOT NULL UNIQUE,
 plan_fingerprint TEXT NOT NULL UNIQUE, confirmation_fingerprint TEXT NOT NULL UNIQUE, source_row_count INTEGER NOT NULL CHECK(source_row_count>0),
 receipt_fingerprint TEXT NOT NULL UNIQUE, applied_at_utc TEXT NOT NULL, canonical_write INTEGER NOT NULL CHECK(canonical_write=0),
 sandbox_only INTEGER NOT NULL CHECK(sandbox_only=1)
) STRICT;
CREATE TRIGGER sandbox_binding_no_update BEFORE UPDATE ON sandbox_binding BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER sandbox_binding_no_delete BEFORE DELETE ON sandbox_binding BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER staged_asset_event_no_update BEFORE UPDATE ON staged_asset_event BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER staged_asset_event_no_delete BEFORE DELETE ON staged_asset_event BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER staged_fifo_reconciliation_no_update BEFORE UPDATE ON staged_fifo_reconciliation BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER staged_fifo_reconciliation_no_delete BEFORE DELETE ON staged_fifo_reconciliation BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER sandbox_apply_receipt_no_update BEFORE UPDATE ON sandbox_apply_receipt BEGIN SELECT RAISE(ABORT,'immutable'); END;
CREATE TRIGGER sandbox_apply_receipt_no_delete BEFORE DELETE ON sandbox_apply_receipt BEGIN SELECT RAISE(ABORT,'immutable'); END;
"""


def _receipt_payload(
    plan: dict[str, Any], context: PerAssetSandboxContextV1, confirmation: dict[str, Any], applied_at_utc: str
) -> dict[str, Any]:
    return {
        "per_asset_sandbox_apply_version": 1,
        "bundle_ref": _bundle_ref(plan, context),
        "command_ref": _command_ref(plan, context),
        "tenant_ref": context.tenant_ref,
        "user_ref": context.user_ref,
        "data_space_ref": context.data_space_ref,
        "actor_ref": context.actor_ref,
        "target_asset_ref": plan["target_asset_ref"],
        "plan_fingerprint": plan["plan_fingerprint"],
        "projection_fingerprint": plan["projection_fingerprint"],
        "source_asset_link_fingerprint": plan["source_asset_link_fingerprint"],
        "fifo_reconciliation_fingerprint": plan["fifo_reconciliation"]["fifo_reconciliation_fingerprint"],
        "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
        "source_row_count": plan["source_row_count"],
        "applied_at_utc": applied_at_utc,
        "sandbox_only": True,
        "canonical_write": False,
        "automatic_cash_posting_count": 0,
        "cutover_performed": False,
    }


def _manifest_payload(plan: dict[str, Any], receipt: dict[str, Any], database_bytes: bytes) -> dict[str, Any]:
    body = {
        "per_asset_sandbox_bundle_version": 1,
        "bundle_ref": receipt["bundle_ref"],
        "schema_version": SCHEMA_VERSION,
        "plan_fingerprint": plan["plan_fingerprint"],
        "fifo_reconciliation_fingerprint": plan["fifo_reconciliation"]["fifo_reconciliation_fingerprint"],
        "receipt_fingerprint": receipt["receipt_fingerprint"],
        "source_row_count": plan["source_row_count"],
        "files": [
            {"file_name": "sandbox-staging.sqlite", "byte_count": len(database_bytes), "sha256": _sha_bytes(database_bytes)},
            {"file_name": "receipt.json", "byte_count": len(_canonical(receipt)) + 1, "sha256": _sha_bytes(_canonical(receipt) + b"\n")},
        ],
        "owner_only": True,
        "sandbox_only": True,
        "canonical_write": False,
        "cutover_performed": False,
    }
    return {**body, "bundle_manifest_fingerprint": _fingerprint(body)}


def _materialize_database(
    path: Path, plan: dict[str, Any], context: PerAssetSandboxContextV1, confirmation: dict[str, Any], receipt: dict[str, Any], applied_at_utc: str, failpoint: str | None
) -> None:
    connection: sqlite3.Connection | None = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        connection = sqlite3.connect(path)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(_schema_sql())
        if failpoint == "after_schema":
            _abort("synthetic_per_asset_sandbox_apply_failpoint")
        connection.execute(
            "INSERT INTO sandbox_binding VALUES (1,11901,1,?,?,?,?,?,?,?,?,?,?)",
            (
                context.tenant_ref, context.user_ref, context.data_space_ref, plan["target_asset_ref"], plan["plan_fingerprint"],
                plan["projection_fingerprint"], plan["source_asset_link_fingerprint"], receipt["command_ref"],
                confirmation["confirmation_fingerprint"], applied_at_utc,
            ),
        )
        for row in sorted(plan["rows"], key=lambda item: item["source_row_ordinal"]):
            event = row["activity_event"]
            connection.execute(
                "INSERT INTO staged_asset_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                (
                    row["source_row_ref"], row["source_row_ordinal"], row["source_row_fingerprint"], event["event_ref"],
                    event["event_type"], event["account_ref"], event["related_account_ref"], event["asset_ref"],
                    event["local_date"], event["local_time"], event["time_zone"], event["effective_at_utc"],
                    _canonical(event).decode("ascii"), _canonical(row["activity_effect"]).decode("ascii"), row["memo"],
                ),
            )
        if failpoint == "after_rows":
            _abort("synthetic_per_asset_sandbox_apply_failpoint")
        fifo = plan["fifo_reconciliation"]
        connection.execute(
            "INSERT INTO staged_fifo_reconciliation VALUES (1,?,?,?,0,0,0)",
            (fifo["fifo_status"], fifo["fifo_reconciliation_fingerprint"], _canonical(fifo).decode("ascii")),
        )
        if failpoint == "after_reconciliation":
            _abort("synthetic_per_asset_sandbox_apply_failpoint")
        connection.execute(
            "INSERT INTO sandbox_apply_receipt VALUES (1,?,?,?,?,?,?,?,0,1)",
            (
                receipt["bundle_ref"], receipt["command_ref"], plan["plan_fingerprint"], confirmation["confirmation_fingerprint"],
                plan["source_row_count"], receipt["receipt_fingerprint"], applied_at_utc,
            ),
        )
        if connection.execute("PRAGMA foreign_key_check").fetchall() or connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            _abort("per_asset_sandbox_apply_integrity_invalid")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.close()
        os.chmod(path, 0o600)
        with path.open("rb") as handle:
            os.fsync(handle.fileno())
    except PerAssetSandboxApplyV1Error:
        try:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            if connection is not None:
                connection.close()
        except Exception:
            pass
        raise
    except Exception:
        try:
            if connection is not None and connection.in_transaction:
                connection.rollback()
            if connection is not None:
                connection.close()
        except Exception:
            pass
        _abort("per_asset_sandbox_apply_write_failed")


def _validate_bundle(path: Path, expected_context: PerAssetSandboxContextV1 | None = None) -> dict[str, Any]:
    try:
        if not path.is_absolute() or path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
            _abort("per_asset_sandbox_apply_integrity_invalid")
        children = {item.name for item in path.iterdir()}
        if children != {"SUCCESS", "bundle-manifest.json", "receipt.json", "sandbox-staging.sqlite"} or any(item.is_symlink() for item in path.iterdir()):
            _abort("per_asset_sandbox_apply_integrity_invalid")
        values: dict[str, Any] = {}
        for name in ("receipt.json", "bundle-manifest.json", "SUCCESS"):
            raw = (path / name).read_bytes()
            value = json.loads(raw.decode("utf-8", errors="strict"))
            if raw != _canonical(value) + b"\n" or stat.S_IMODE((path / name).stat().st_mode) != 0o600:
                _abort("per_asset_sandbox_apply_integrity_invalid")
            values[name] = value
        receipt = values["receipt.json"]
        receipt_body = {key: value for key, value in receipt.items() if key != "receipt_fingerprint"}
        if receipt.get("receipt_fingerprint") != _fingerprint(receipt_body):
            _abort("per_asset_sandbox_apply_integrity_invalid")
        database = path / "sandbox-staging.sqlite"
        database_bytes = database.read_bytes()
        if stat.S_IMODE(database.stat().st_mode) != 0o600:
            _abort("per_asset_sandbox_apply_integrity_invalid")
        manifest = values["bundle-manifest.json"]
        manifest_body = {key: value for key, value in manifest.items() if key != "bundle_manifest_fingerprint"}
        expected_files = [
            {"file_name": "sandbox-staging.sqlite", "byte_count": len(database_bytes), "sha256": _sha_bytes(database_bytes)},
            {"file_name": "receipt.json", "byte_count": len(_canonical(receipt)) + 1, "sha256": _sha_bytes(_canonical(receipt) + b"\n")},
        ]
        if manifest.get("bundle_manifest_fingerprint") != _fingerprint(manifest_body) or manifest.get("files") != expected_files:
            _abort("per_asset_sandbox_apply_integrity_invalid")
        if values["SUCCESS"] != {
            "per_asset_sandbox_bundle_version": 1,
            "bundle_ref": receipt["bundle_ref"],
            "bundle_manifest_fingerprint": manifest["bundle_manifest_fingerprint"],
        }:
            _abort("per_asset_sandbox_apply_integrity_invalid")
        connection = sqlite3.connect(f"file:{database.resolve(strict=True)}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only=ON")
        if connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION or connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
            _abort("per_asset_sandbox_apply_integrity_invalid")
        binding = connection.execute(
            "SELECT tenant_ref,user_ref,data_space_ref,target_asset_ref,plan_fingerprint,command_ref,confirmation_fingerprint FROM sandbox_binding"
        ).fetchall()
        counts = connection.execute("SELECT count(*) FROM staged_asset_event").fetchone()[0]
        stored_receipt = connection.execute("SELECT bundle_ref,command_ref,plan_fingerprint,confirmation_fingerprint,source_row_count,receipt_fingerprint,canonical_write,sandbox_only FROM sandbox_apply_receipt").fetchall()
        connection.close()
        if len(binding) != 1 or len(stored_receipt) != 1 or counts != receipt["source_row_count"]:
            _abort("per_asset_sandbox_apply_integrity_invalid")
        if binding[0] != (
            receipt["tenant_ref"], receipt["user_ref"], receipt["data_space_ref"], receipt["target_asset_ref"], receipt["plan_fingerprint"],
            receipt["command_ref"], receipt["confirmation_fingerprint"],
        ) or stored_receipt[0] != (
            receipt["bundle_ref"], receipt["command_ref"], receipt["plan_fingerprint"], receipt["confirmation_fingerprint"],
            receipt["source_row_count"], receipt["receipt_fingerprint"], 0, 1,
        ):
            _abort("per_asset_sandbox_apply_integrity_invalid")
        if expected_context is not None and (receipt["tenant_ref"], receipt["user_ref"], receipt["data_space_ref"], receipt["actor_ref"]) != (
            expected_context.tenant_ref, expected_context.user_ref, expected_context.data_space_ref, expected_context.actor_ref,
        ):
            _abort("per_asset_sandbox_apply_target_conflict")
        return receipt
    except PerAssetSandboxApplyV1Error:
        raise
    except Exception:
        _abort("per_asset_sandbox_apply_integrity_invalid")


def validate_per_asset_sandbox_bundle_v1(path_value: Any) -> dict[str, Any]:
    try:
        if not isinstance(path_value, (str, os.PathLike)):
            _abort("per_asset_sandbox_apply_target_invalid")
        return _validate_bundle(Path(path_value))
    except PerAssetSandboxApplyV1Error:
        raise
    except Exception:
        raise PerAssetSandboxApplyV1Error("per_asset_sandbox_apply_boundary_failed") from None


def apply_per_asset_plan_to_sandbox_v1(
    projection: Any,
    review: Any,
    expected_plan_fingerprint: str,
    context: PerAssetSandboxContextV1,
    confirmation: Any,
    authorizer: OneUsePerAssetSandboxAuthorizerV1,
    target_capability: PerAssetSandboxTargetCapabilityV1,
    applied_at_utc: str,
    *,
    failpoint: str | None = None,
) -> PerAssetSandboxApplyResultV1:
    stage: Path | None = None
    published = False
    try:
        if failpoint not in ALLOWED_FAILPOINTS:
            _abort("per_asset_sandbox_apply_plan_invalid")
        runtime = _context(context)
        try:
            recomputed = plan_legacy_per_asset_trade_v1(projection, review)
        except LegacyPerAssetTradePlannerV1Error:
            _abort("per_asset_sandbox_apply_plan_invalid")
        plan = _plan(recomputed)
        if not isinstance(expected_plan_fingerprint, str) or expected_plan_fingerprint != plan["plan_fingerprint"]:
            _abort("per_asset_sandbox_apply_plan_invalid")
        requested_target, parent = _target_capability(target_capability, runtime)
        if requested_target.is_absolute() and not requested_target.is_symlink() and requested_target.is_dir():
            try:
                existing_receipt = _validate_bundle(requested_target, runtime)
            except PerAssetSandboxApplyV1Error as error:
                if error.code == "per_asset_sandbox_apply_target_conflict":
                    raise
                _abort("per_asset_sandbox_apply_target_conflict")
            if existing_receipt.get("plan_fingerprint") == plan["plan_fingerprint"]:
                return PerAssetSandboxApplyResultV1(
                    "already_created", existing_receipt["bundle_ref"], plan["plan_fingerprint"],
                    existing_receipt["receipt_fingerprint"], False,
                )
            _abort("per_asset_sandbox_apply_target_conflict")
        target = requested_target
        if target.exists() or target.is_symlink():
            _abort("per_asset_sandbox_apply_target_conflict")
        validated_confirmation = _confirmation(confirmation, plan, runtime, authorizer, applied_at_utc)
        # Confirmation is consumed before any filesystem write. A failed attempt needs
        # a newly reviewed confirmation and never retries automatically.
        authorizer.consume(validated_confirmation["challenge_id"], validated_confirmation["confirmation_fingerprint"])
        receipt_body = _receipt_payload(plan, runtime, validated_confirmation, applied_at_utc)
        receipt = {**receipt_body, "receipt_fingerprint": _fingerprint(receipt_body)}
        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.incoming-", dir=parent))
        os.chmod(stage, 0o700)
        database = stage / "sandbox-staging.sqlite"
        _materialize_database(database, plan, runtime, validated_confirmation, receipt, applied_at_utc, failpoint)
        if failpoint == "after_schema" or failpoint == "after_rows" or failpoint == "after_reconciliation":
            _abort("synthetic_per_asset_sandbox_apply_failpoint")
        database_bytes = database.read_bytes()
        _write(stage / "receipt.json", _canonical(receipt) + b"\n")
        manifest = _manifest_payload(plan, receipt, database_bytes)
        _write(stage / "bundle-manifest.json", _canonical(manifest) + b"\n")
        if failpoint == "after_manifest":
            _abort("synthetic_per_asset_sandbox_apply_failpoint")
        success = {
            "per_asset_sandbox_bundle_version": 1,
            "bundle_ref": receipt["bundle_ref"],
            "bundle_manifest_fingerprint": manifest["bundle_manifest_fingerprint"],
        }
        _write(stage / "SUCCESS", _canonical(success) + b"\n")
        if failpoint == "after_success":
            _abort("synthetic_per_asset_sandbox_apply_failpoint")
        _fsync_directory(stage)
        _rename_noreplace(stage, target)
        published = True
        _fsync_directory(parent)
        if failpoint == "after_publish":
            _abort("synthetic_per_asset_sandbox_apply_failpoint")
        _validate_bundle(target, runtime)
        return PerAssetSandboxApplyResultV1(
            "created", receipt["bundle_ref"], plan["plan_fingerprint"], receipt["receipt_fingerprint"], True
        )
    except PerAssetSandboxApplyV1Error:
        raise
    except Exception:
        raise PerAssetSandboxApplyV1Error("per_asset_sandbox_apply_boundary_failed") from None
    finally:
        if stage is not None and not published and stage.exists():
            try:
                shutil.rmtree(stage)
                _fsync_directory(stage.parent)
            except Exception:
                pass


__all__ = [
    "OneUsePerAssetSandboxAuthorizerV1",
    "PerAssetSandboxApplyResultV1",
    "PerAssetSandboxApplyV1Error",
    "PerAssetSandboxContextV1",
    "PerAssetSandboxTargetCapabilityV1",
    "apply_per_asset_plan_to_sandbox_v1",
    "build_per_asset_sandbox_confirmation_v1",
    "new_per_asset_sandbox_target_capability_v1",
    "per_asset_sandbox_apply_v1_error_codes",
    "validate_per_asset_sandbox_bundle_v1",
]
