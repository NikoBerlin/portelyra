"""Owner-local one-read Statement structural-profiler UAT v1.

This boundary reuses ADR-163's reviewed file-descriptor safety primitives, but
binds the read to ADR-164's structural profiler rather than to a business
adapter profile. Private headers and semantic values are shown only through a
caller-provided local review provider and are never persisted or returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Callable

from migrations.reference.desktop_statement_source_profiler_v1 import (
    DesktopStatementSourceProfilerError,
    inspect_statement_source_bytes_v1,
)
from migrations.reference.statement_import_owner_uat_v1 import (
    StatementImportOwnerUATError,
    _canonical,
    _fingerprint,
    _fsync_directory,
    _parse_utc,
    _read_exact_json,
    _secure_read_once,
    _select_snapshot,
    _utc_text,
    _validate_owner_directory,
    _write_once,
    derive_statement_import_owner_uat_runtime_v1,
)

ROOT = Path(__file__).resolve().parents[2]
PROFILER_CONTRACT = ROOT / "contracts/desktop-statement-source-profiler/v1"
EVIDENCE_DIRECTORY = "statement_source_profiler_owner_uat_v1"
AUTHORIZATION_SECONDS = 300
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NONCE = re.compile(r"[0-9a-f]{32}")
FAILURE_CODES = frozenset(
    {
        "statement_source_profiler_owner_uat_authorization_expired",
        "statement_source_profiler_owner_uat_authorization_invalid",
        "statement_source_profiler_owner_uat_boundary_failed",
        "statement_source_profiler_owner_uat_evidence_exists",
        "statement_source_profiler_owner_uat_evidence_invalid",
        "statement_source_profiler_owner_uat_evidence_recovery_required",
        "statement_source_profiler_owner_uat_execution_not_authorized",
        "statement_source_profiler_owner_uat_input_invalid",
        "statement_source_profiler_owner_uat_profiler_invalid",
        "statement_source_profiler_owner_uat_review_cancelled",
        "statement_source_profiler_owner_uat_review_invalid",
        "statement_source_profiler_owner_uat_selection_cancelled",
        "statement_source_profiler_owner_uat_source_bundle_invalid",
        "statement_source_profiler_owner_uat_source_changed",
        "statement_source_profiler_owner_uat_source_invalid",
    }
)


class StatementSourceProfilerOwnerUATError(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            code = "statement_source_profiler_owner_uat_boundary_failed"
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise StatementSourceProfilerOwnerUATError(code)


def _map_owner_error(error: StatementImportOwnerUATError) -> None:
    mapping = {
        "statement_import_owner_uat_source_changed": "statement_source_profiler_owner_uat_source_changed",
        "statement_import_owner_uat_source_invalid": "statement_source_profiler_owner_uat_source_invalid",
        "statement_import_owner_uat_input_invalid": "statement_source_profiler_owner_uat_input_invalid",
        "statement_import_owner_uat_evidence_exists": "statement_source_profiler_owner_uat_evidence_exists",
        "statement_import_owner_uat_evidence_recovery_required": "statement_source_profiler_owner_uat_evidence_recovery_required",
    }
    _fail(mapping.get(error.code, "statement_source_profiler_owner_uat_evidence_invalid"))


def _profiler_binding() -> tuple[str, str]:
    manifest = PROFILER_CONTRACT / "source-fingerprints.csv"
    aliases = PROFILER_CONTRACT / "header-role-aliases.csv"
    try:
        raw = manifest.read_bytes()
        reader = csv.DictReader(raw.decode("utf-8", errors="strict").splitlines())
        if reader.fieldnames != ["source_id", "path", "sha256"]:
            raise ValueError("header")
        rows = list(reader)
        if not rows or [row["source_id"] for row in rows] != sorted(row["source_id"] for row in rows):
            raise ValueError("rows")
        for row in rows:
            path = ROOT / row["path"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("hash")
        return hashlib.sha256(raw).hexdigest(), hashlib.sha256(aliases.read_bytes()).hexdigest()
    except (OSError, UnicodeDecodeError, ValueError, KeyError):
        _fail("statement_source_profiler_owner_uat_profiler_invalid")


def derive_statement_source_profiler_owner_uat_runtime_v1(desktop_home: Path) -> tuple[Path, str]:
    try:
        old_root, context_binding = derive_statement_import_owner_uat_runtime_v1(desktop_home)
    except StatementImportOwnerUATError as error:
        _map_owner_error(error)
    return old_root.parent / EVIDENCE_DIRECTORY, context_binding


def _read_evidence(path: Path) -> dict[str, Any]:
    try:
        value, _raw = _read_exact_json(path)
        return value
    except StatementImportOwnerUATError:
        _fail("statement_source_profiler_owner_uat_evidence_invalid")


def _write_evidence(directory: Path, name: str, value: dict[str, Any]) -> None:
    try:
        _write_once(directory / name, value)
        _fsync_directory(directory)
    except StatementImportOwnerUATError as error:
        _map_owner_error(error)


def _validate_fingerprint(value: dict[str, Any], field: str) -> None:
    actual = value.get(field)
    if not isinstance(actual, str) or _SHA256.fullmatch(actual) is None or actual != _fingerprint({k: v for k, v in value.items() if k != field}):
        _fail("statement_source_profiler_owner_uat_evidence_invalid")


def _validate_history(root: Path, context_binding: str, profiler_binding: str, aliases_sha: str) -> None:
    attempt_keys = {
        "activation_authorized", "alias_registry_sha256", "attempt_fingerprint", "attempt_status",
        "automatic_retry_authorized", "canonical_write_authorized", "confirmed_at_utc",
        "context_binding_sha256", "expires_at_utc", "issued_at_utc", "one_use_authorization_sha256",
        "private_values_local_only_acknowledged", "profiler_binding_sha256", "provider_access_authorized",
        "selection_binding_sha256", "source_path_retained", "source_read_once_authorized", "status", "version",
    }
    failure_keys = {
        "activation_authorized", "attempt_fingerprint", "automatic_retry", "canonical_write", "cash_write",
        "failure_code", "failure_fingerprint", "network_access", "private_values_published",
        "profile_revision_created", "provider_access", "route_rules_created", "source_path_retained",
        "source_read_attempted", "source_read_completed", "status", "tax_write", "time_zone_inferred", "version",
    }
    receipt_keys = {
        "activation_authorized", "alias_registry_sha256", "attempt_fingerprint", "automatic_retry",
        "canonical_write", "cash_write", "completed_at_utc", "context_binding_sha256", "header_sha256",
        "network_access", "private_review_sha256", "private_source_read", "private_values_published",
        "profile_revision_created", "profiler_binding_sha256", "provider_access", "receipt_fingerprint",
        "route_rules_created", "row_count", "selection_binding_sha256", "semantic_tuple_evidence",
        "silent_drop_count", "source_bytes_sha256", "source_path_retained", "source_read_attempt_count",
        "status", "structural_ready", "tax_write", "time_zone_inferred", "version",
    }
    negative = {
        "activation_authorized", "automatic_retry", "canonical_write", "cash_write", "network_access",
        "private_values_published", "profile_revision_created", "provider_access", "route_rules_created",
        "source_path_retained", "tax_write", "time_zone_inferred",
    }
    try:
        directories = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError:
        _fail("statement_source_profiler_owner_uat_evidence_invalid")
    for directory in directories:
        if re.fullmatch(r"profile_uat_[0-9a-f]{32}", directory.name) is None:
            _fail("statement_source_profiler_owner_uat_evidence_invalid")
        try:
            _validate_owner_directory(directory, create=False)
        except StatementImportOwnerUATError as error:
            _map_owner_error(error)
        names = sorted(path.name for path in directory.iterdir())
        if names == ["authorization-attempt.json"]:
            _fail("statement_source_profiler_owner_uat_evidence_recovery_required")
        if names not in (["authorization-attempt.json", "uat-failure.json"], ["authorization-attempt.json", "uat-receipt.json"]):
            _fail("statement_source_profiler_owner_uat_evidence_invalid")
        attempt = _read_evidence(directory / "authorization-attempt.json")
        _validate_fingerprint(attempt, "attempt_fingerprint")
        if (
            set(attempt) != attempt_keys
            or attempt.get("version") != 1
            or attempt.get("status") != "authorization_consumed_before_source_read"
            or attempt.get("attempt_status") != "authorization_consumed_before_source_read"
            or attempt.get("context_binding_sha256") != context_binding
            or attempt.get("profiler_binding_sha256") != profiler_binding
            or attempt.get("alias_registry_sha256") != aliases_sha
            or attempt.get("source_path_retained") is not False
            or attempt.get("source_read_once_authorized") is not True
            or attempt.get("private_values_local_only_acknowledged") is not True
            or any(attempt.get(key) is not False for key in ("activation_authorized", "automatic_retry_authorized", "canonical_write_authorized", "provider_access_authorized"))
        ):
            _fail("statement_source_profiler_owner_uat_evidence_invalid")
        try:
            issued = _parse_utc(attempt["issued_at_utc"])
            confirmed = _parse_utc(attempt["confirmed_at_utc"])
            expires = _parse_utc(attempt["expires_at_utc"])
        except StatementImportOwnerUATError:
            _fail("statement_source_profiler_owner_uat_evidence_invalid")
        if not issued <= confirmed <= expires or expires - issued != timedelta(seconds=AUTHORIZATION_SECONDS):
            _fail("statement_source_profiler_owner_uat_evidence_invalid")
        terminal = _read_evidence(directory / names[1])
        field = "failure_fingerprint" if names[1] == "uat-failure.json" else "receipt_fingerprint"
        _validate_fingerprint(terminal, field)
        if terminal.get("attempt_fingerprint") != attempt["attempt_fingerprint"] or any(terminal.get(key) is not False for key in negative):
            _fail("statement_source_profiler_owner_uat_evidence_invalid")
        if names[1] == "uat-failure.json":
            if (
                set(terminal) != failure_keys
                or terminal.get("version") != 1
                or terminal.get("status") != "terminal_failure_new_authorization_required"
                or terminal.get("failure_code") not in FAILURE_CODES
                or not isinstance(terminal.get("source_read_attempted"), bool)
                or not isinstance(terminal.get("source_read_completed"), bool)
                or terminal.get("source_read_completed") is True and terminal.get("source_read_attempted") is not True
            ):
                _fail("statement_source_profiler_owner_uat_evidence_invalid")
        elif (
            set(terminal) != receipt_keys
            or terminal.get("version") != 1
            or terminal.get("status") not in {"owner_profile_observed_disabled", "owner_profile_rejected_disabled"}
            or terminal.get("context_binding_sha256") != context_binding
            or terminal.get("profiler_binding_sha256") != profiler_binding
            or terminal.get("alias_registry_sha256") != aliases_sha
            or terminal.get("selection_binding_sha256") != attempt["selection_binding_sha256"]
            or terminal.get("private_source_read") is not True
            or terminal.get("source_read_attempt_count") != 1
            or terminal.get("silent_drop_count") != 0
            or not isinstance(terminal.get("structural_ready"), bool)
            or not isinstance(terminal.get("row_count"), int)
            or terminal.get("row_count") < 1
            or not isinstance(terminal.get("semantic_tuple_evidence"), list)
            or any(set(item) != {"row_count", "tuple_sha256"} or not isinstance(item["row_count"], int) or item["row_count"] < 1 or not isinstance(item["tuple_sha256"], str) or _SHA256.fullmatch(item["tuple_sha256"]) is None for item in terminal["semantic_tuple_evidence"])
        ):
            _fail("statement_source_profiler_owner_uat_evidence_invalid")


@dataclass(frozen=True)
class StatementSourceProfilerOwnerUATResultV1:
    status: str
    structural_ready: bool

    def public_projection(self) -> dict[str, Any]:
        return {
            "activation_authorized": False,
            "automatic_retry": False,
            "candidate_handoff_available": False,
            "canonical_write": False,
            "cash_write": False,
            "network_access": False,
            "owner_evidence_created": True,
            "private_source_read": True,
            "private_values_published": False,
            "profile_revision_created": False,
            "provider_access": False,
            "route_rules_created": False,
            "source_path_exposed": False,
            "source_read_attempt_count": 1,
            "statement_source_profiler_owner_uat_public_result_version": 1,
            "status": self.status,
            "structural_ready": self.structural_ready,
            "tax_write": False,
            "time_zone_inferred": False,
        }


def run_statement_source_profiler_owner_uat_v1(
    evidence_root: Path,
    context_binding_sha256: str,
    *,
    selection_provider: Callable[[], Any],
    authorization_provider: Callable[[dict[str, Any]], Any],
    review_provider: Callable[[dict[str, Any]], Any],
    inspection_provider: Callable[[bytes], Any] | None = None,
    now_provider: Callable[[], datetime] | None = None,
    nonce_provider: Callable[[], str] | None = None,
) -> StatementSourceProfilerOwnerUATResultV1:
    previous_umask = os.umask(0o077)
    attempt_directory: Path | None = None
    attempt: dict[str, Any] | None = None
    source_read_attempted = False
    source_read_completed = False
    try:
        root = Path(evidence_root)
        if not root.is_absolute() or _SHA256.fullmatch(context_binding_sha256 or "") is None:
            _fail("statement_source_profiler_owner_uat_input_invalid")
        profiler_binding, aliases_sha = _profiler_binding()
        try:
            if root.exists():
                _validate_owner_directory(root, create=False)
                _validate_history(root, context_binding_sha256, profiler_binding, aliases_sha)
            else:
                _validate_owner_directory(root, create=True)
                _fsync_directory(root.parent)
        except StatementImportOwnerUATError as error:
            _map_owner_error(error)
        selected = selection_provider()
        if selected is None:
            _fail("statement_source_profiler_owner_uat_selection_cancelled")
        try:
            snapshot = _select_snapshot(selected, context_binding_sha256, profiler_binding)
        except StatementImportOwnerUATError as error:
            _map_owner_error(error)
        clock = now_provider or (lambda: datetime.now(timezone.utc).replace(microsecond=0))
        nonce_factory = nonce_provider or (lambda: secrets.token_hex(16))
        issued = clock()
        nonce = nonce_factory()
        if _NONCE.fullmatch(nonce) is None:
            _fail("statement_source_profiler_owner_uat_boundary_failed")
        preview = {
            "alias_registry_sha256": aliases_sha,
            "authorization_id": "spu_" + nonce,
            "context_binding_sha256": context_binding_sha256,
            "expires_at_utc": _utc_text(issued + timedelta(seconds=AUTHORIZATION_SECONDS)),
            "issued_at_utc": _utc_text(issued),
            "profiler_binding_sha256": profiler_binding,
            "selection_binding_sha256": snapshot.selection_binding_sha256,
            "source_path_exposed": False,
            "source_read_count": 1,
        }
        authorization = authorization_provider(dict(preview))
        confirmed = clock()
        required = {
            "activation_authorized", "authorization_id", "automatic_retry_authorized",
            "canonical_write_authorized", "context_binding_sha256", "private_values_local_only_acknowledged",
            "profiler_binding_sha256", "provider_access_authorized", "selection_binding_sha256",
            "source_read_once_authorized",
        }
        if not isinstance(authorization, dict) or set(authorization) != required:
            _fail("statement_source_profiler_owner_uat_authorization_invalid")
        if any(authorization.get(key) != preview.get(key) for key in ("authorization_id", "context_binding_sha256", "profiler_binding_sha256", "selection_binding_sha256")):
            _fail("statement_source_profiler_owner_uat_authorization_invalid")
        if authorization.get("source_read_once_authorized") is not True or authorization.get("private_values_local_only_acknowledged") is not True or any(authorization.get(key) is not False for key in ("activation_authorized", "automatic_retry_authorized", "canonical_write_authorized", "provider_access_authorized")):
            _fail("statement_source_profiler_owner_uat_authorization_invalid")
        if confirmed < _parse_utc(preview["issued_at_utc"]) or confirmed > _parse_utc(preview["expires_at_utc"]):
            _fail("statement_source_profiler_owner_uat_authorization_expired")
        attempt_directory = root / ("profile_uat_" + nonce)
        try:
            _validate_owner_directory(attempt_directory, create=True)
        except StatementImportOwnerUATError as error:
            _map_owner_error(error)
        attempt = {
            "activation_authorized": False,
            "alias_registry_sha256": aliases_sha,
            "attempt_status": "authorization_consumed_before_source_read",
            "automatic_retry_authorized": False,
            "canonical_write_authorized": False,
            "confirmed_at_utc": _utc_text(confirmed),
            "context_binding_sha256": context_binding_sha256,
            "expires_at_utc": preview["expires_at_utc"],
            "issued_at_utc": preview["issued_at_utc"],
            "one_use_authorization_sha256": hashlib.sha256(authorization["authorization_id"].encode("ascii")).hexdigest(),
            "private_values_local_only_acknowledged": True,
            "profiler_binding_sha256": profiler_binding,
            "provider_access_authorized": False,
            "selection_binding_sha256": snapshot.selection_binding_sha256,
            "source_path_retained": False,
            "source_read_once_authorized": True,
            "status": "authorization_consumed_before_source_read",
            "version": 1,
        }
        attempt["attempt_fingerprint"] = _fingerprint(attempt)
        _write_evidence(attempt_directory, "authorization-attempt.json", attempt)
        source_read_attempted = True
        try:
            source_bytes = _secure_read_once(snapshot)
        except StatementImportOwnerUATError as error:
            _map_owner_error(error)
        source_read_completed = True
        try:
            inspection = (inspection_provider or (lambda value: inspect_statement_source_bytes_v1(value, institution_hint="kraken")))(source_bytes)
            if not hasattr(inspection, "private_review") or not callable(getattr(inspection, "public_projection", None)):
                raise ValueError("inspection_shape")
        except Exception:
            _fail("statement_source_profiler_owner_uat_profiler_invalid")
        private_review = dict(inspection.private_review)
        review_binding = hashlib.sha256(_canonical(private_review)).hexdigest()
        private_review["review_binding_sha256"] = review_binding
        decision = review_provider(private_review)
        if decision is None:
            _fail("statement_source_profiler_owner_uat_review_cancelled")
        if not isinstance(decision, dict) or set(decision) != {"decision", "no_activation_acknowledged", "private_values_local_only_acknowledged", "review_binding_sha256"}:
            _fail("statement_source_profiler_owner_uat_review_invalid")
        if decision.get("decision") not in {"observe_disabled", "reject_disabled"} or decision.get("review_binding_sha256") != review_binding or decision.get("no_activation_acknowledged") is not True or decision.get("private_values_local_only_acknowledged") is not True:
            _fail("statement_source_profiler_owner_uat_review_invalid")
        public = inspection.public_projection()
        status = "owner_profile_observed_disabled" if decision["decision"] == "observe_disabled" else "owner_profile_rejected_disabled"
        semantic_evidence = []
        for item in inspection.private_review["semantic_route_tuples"]:
            semantic_evidence.append({"row_count": item["row_count"], "tuple_sha256": hashlib.sha256(_canonical(item)).hexdigest()})
        receipt = {
            "activation_authorized": False,
            "alias_registry_sha256": aliases_sha,
            "attempt_fingerprint": attempt["attempt_fingerprint"],
            "automatic_retry": False,
            "canonical_write": False,
            "cash_write": False,
            "completed_at_utc": _utc_text(clock()),
            "context_binding_sha256": context_binding_sha256,
            "header_sha256": hashlib.sha256(_canonical([item["raw_header"] for item in inspection.private_review["column_dispositions"]])).hexdigest(),
            "network_access": False,
            "private_review_sha256": review_binding,
            "private_source_read": True,
            "private_values_published": False,
            "profile_revision_created": False,
            "profiler_binding_sha256": profiler_binding,
            "provider_access": False,
            "route_rules_created": False,
            "row_count": public["row_count"],
            "selection_binding_sha256": snapshot.selection_binding_sha256,
            "semantic_tuple_evidence": semantic_evidence,
            "silent_drop_count": public["silent_drop_count"],
            "source_bytes_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "source_path_retained": False,
            "source_read_attempt_count": 1,
            "status": status,
            "structural_ready": public["status"] == "ready_for_owner_semantic_review",
            "tax_write": False,
            "time_zone_inferred": False,
            "version": 1,
        }
        receipt["receipt_fingerprint"] = _fingerprint(receipt)
        _write_evidence(attempt_directory, "uat-receipt.json", receipt)
        return StatementSourceProfilerOwnerUATResultV1(status, receipt["structural_ready"])
    except StatementSourceProfilerOwnerUATError as error:
        if attempt_directory is not None and attempt is not None:
            failure = {
                "activation_authorized": False,
                "attempt_fingerprint": attempt["attempt_fingerprint"],
                "automatic_retry": False,
                "canonical_write": False,
                "cash_write": False,
                "failure_code": error.code,
                "network_access": False,
                "private_values_published": False,
                "profile_revision_created": False,
                "provider_access": False,
                "route_rules_created": False,
                "source_path_retained": False,
                "source_read_attempted": source_read_attempted,
                "source_read_completed": source_read_completed,
                "status": "terminal_failure_new_authorization_required",
                "tax_write": False,
                "time_zone_inferred": False,
                "version": 1,
            }
            failure["failure_fingerprint"] = _fingerprint(failure)
            _write_evidence(attempt_directory, "uat-failure.json", failure)
        raise
    except Exception as error:
        raise StatementSourceProfilerOwnerUATError("statement_source_profiler_owner_uat_boundary_failed") from error
    finally:
        os.umask(previous_umask)


__all__ = [
    "StatementSourceProfilerOwnerUATError",
    "StatementSourceProfilerOwnerUATResultV1",
    "derive_statement_source_profiler_owner_uat_runtime_v1",
    "run_statement_source_profiler_owner_uat_v1",
]
