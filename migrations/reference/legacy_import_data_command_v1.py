"""Executable reference oracle for Legacy Import Data Command v1.

This module is contract evidence, not production application runtime. It uses only
in-memory-capable sqlite3 connections and never opens source files or networks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
import sqlite3
import unicodedata
from typing import Any, Callable

from .transaction_semantics_v1 import (
    TransactionSemanticsError,
    validate_candidate_transaction_semantics,
)

CANONICAL_SCHEMA_VERSION = 201
STAGING_SCHEMA_VERSION = 1001
COMMAND_CONTRACT_VERSION = 1
CONFIRMATION_CONTRACT_VERSION = 1
EXPECTED_STAGING_SCHEMA_FINGERPRINT = "faee80169fdd043972ef1058c311ca4203794e534f79869934b5f13dee30fc86"
EXPECTED_STAGING_CATALOG_FINGERPRINT = "0b1849fdc38c01685afa543263240ac8691084847e15197b13af731fbe64ce5d"
EXPECTED_CANONICAL_SCHEMA_FINGERPRINT = "092c8af40530258df6c4bc9760612b843ffc7fa86bb2a9854bfd16b157bab7c0"
ALLOWED_ROLES = frozenset({"owner", "data_admin", "desktop_owner"})
FAILURE_CODES = frozenset(
    {
        "fingerprint_float_forbidden",
        "fingerprint_unicode_not_nfc",
        "fingerprint_control_character_forbidden",
        "fingerprint_key_invalid",
        "fingerprint_value_type_invalid",
        "runtime_role_not_authorized",
        "runtime_context_invalid",
        "staging_connection_in_transaction",
        "staging_query_only_not_enforced",
        "staging_schema_version_mismatch",
        "staging_contract_schema_mismatch",
        "staging_contract_catalog_mismatch",
        "staging_foreign_key_invalid",
        "staging_integrity_invalid",
        "staging_run_count_invalid",
        "staging_seal_count_invalid",
        "productive_import_not_enabled",
        "staging_runtime_context_mismatch",
        "staging_not_ready",
        "staging_gate_missing",
        "staging_gate_closed",
        "staging_fingerprint_mismatch",
        "transaction_semantics_invalid",
        "canonical_schema_version_mismatch",
        "canonical_contract_schema_mismatch",
        "canonical_store_binding_missing",
        "canonical_runtime_context_mismatch",
        "canonical_foreign_keys_disabled",
        "canonical_connection_query_only",
        "canonical_foreign_key_invalid",
        "idempotency_conflict",
        "target_sandbox_not_empty",
        "confirmation_missing",
        "confirmation_invalid",
        "confirmation_challenge_duplicate",
        "confirmation_not_authorized",
        "confirmation_already_consumed",
        "confirmation_time_invalid",
        "confirmation_fingerprint_mismatch",
        "confirmation_scope_mismatch",
        "confirmation_expired_or_time_invalid",
        "confirmation_validity_window_exceeded",
        "canonical_connection_already_in_transaction",
        "command_preflight_failed",
        "candidate_portfolio_count_invalid",
        "canonical_integrity_invalid",
        "canonical_transaction_failed",
        "synthetic_failpoint",
    }
)


class DataCommandError(RuntimeError):
    """Fail-closed error carrying only a fixed privacy-safe code."""

    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("unregistered_data_command_error_code")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RuntimeContext:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str
    role: str


@dataclass(frozen=True)
class CommandResult:
    status: str
    command_id: str
    candidate_fingerprint: str
    import_receipt_id: str | None
    counts: dict[str, int]


class OneUseConfirmationAuthorizer:
    """Synthetic one-use control-plane oracle used by contract tests only."""

    def __init__(self) -> None:
        self._registered: dict[str, str] = {}
        self._consumed: set[str] = set()

    def register(self, confirmation: dict[str, Any]) -> None:
        challenge_id = confirmation.get("challenge_id")
        fingerprint = confirmation.get("confirmation_fingerprint")
        if not _is_identifier(challenge_id, "cfm_") or not _is_sha256(fingerprint):
            raise DataCommandError("confirmation_invalid")
        if challenge_id in self._registered:
            raise DataCommandError("confirmation_challenge_duplicate")
        self._registered[challenge_id] = fingerprint

    def consume(self, challenge_id: str, fingerprint: str) -> None:
        expected = self._registered.get(challenge_id)
        if expected is None or expected != fingerprint:
            raise DataCommandError("confirmation_not_authorized")
        if challenge_id in self._consumed:
            raise DataCommandError("confirmation_already_consumed")
        self._consumed.add(challenge_id)

    def is_consumed(self, challenge_id: str) -> bool:
        return challenge_id in self._consumed


@dataclass(frozen=True)
class ValidatedStaging:
    run: dict[str, Any]
    seal: dict[str, Any]
    candidate_manifest: dict[str, Any]
    artifact_manifest: dict[str, Any]
    candidate_fingerprint: str
    artifact_fingerprint: str
    counts: dict[str, int]


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _is_identifier(value: Any, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(prefix)
        and 8 <= len(value) <= 64
        and re.fullmatch(r"[a-z0-9_]+", value) is not None
    )


def _validate_canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        raise DataCommandError("fingerprint_float_forbidden")
    if isinstance(value, str):
        if value != unicodedata.normalize("NFC", value):
            raise DataCommandError("fingerprint_unicode_not_nfc")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise DataCommandError("fingerprint_control_character_forbidden")
        return value
    if isinstance(value, list):
        return [_validate_canonical_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) and key.isascii() for key in value):
            raise DataCommandError("fingerprint_key_invalid")
        return {key: _validate_canonical_value(value[key]) for key in sorted(value)}
    raise DataCommandError("fingerprint_value_type_invalid")


def canonical_json_bytes(value: Any) -> bytes:
    normalized = _validate_canonical_value(value)
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _fetch_dicts(connection: sqlite3.Connection, sql: str, values: tuple = ()) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, values)
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_exactly_one(
    connection: sqlite3.Connection,
    sql: str,
    code: str,
    values: tuple = (),
) -> dict[str, Any]:
    rows = _fetch_dicts(connection, sql, values)
    if len(rows) != 1:
        raise DataCommandError(code)
    return rows[0]


def build_candidate_manifest(staging: sqlite3.Connection) -> dict[str, Any]:
    run = _fetch_exactly_one(staging, "SELECT * FROM import_run", "staging_run_count_invalid")
    run_id = run["import_run_id"]
    portfolios = _fetch_dicts(
        staging,
        """
        SELECT staged_portfolio_id, display_name, base_currency
        FROM staged_portfolio WHERE import_run_id=? ORDER BY staged_portfolio_id
        """,
        (run_id,),
    )
    accounts = _fetch_dicts(
        staging,
        """
        SELECT staged_account_id, staged_portfolio_id, display_name, account_type
        FROM staged_account WHERE import_run_id=? ORDER BY staged_account_id
        """,
        (run_id,),
    )
    assets = _fetch_dicts(
        staging,
        """
        SELECT staged_asset_id, display_name, asset_type, price_currency,
               quantity_scale, valuation_method, isin
        FROM staged_asset WHERE import_run_id=? ORDER BY staged_asset_id
        """,
        (run_id,),
    )
    transactions = _fetch_dicts(
        staging,
        """
        SELECT staged_transaction_id, staged_portfolio_id, transaction_type,
               effective_at_utc, local_date
        FROM staged_transaction WHERE import_run_id=? ORDER BY staged_transaction_id
        """,
        (run_id,),
    )
    postings = _fetch_dicts(
        staging,
        """
        SELECT staged_posting_id, staged_transaction_id, sequence_no, staged_account_id,
               staged_asset_id, posting_role, quantity_decimal, unit_price_decimal,
               price_currency, valuation_amount_decimal, valuation_currency
        FROM staged_posting WHERE import_run_id=?
        ORDER BY staged_transaction_id, sequence_no, staged_posting_id
        """,
        (run_id,),
    )
    counts = {
        "portfolio_count": len(portfolios),
        "account_count": len(accounts),
        "asset_count": len(assets),
        "transaction_count": len(transactions),
        "posting_count": len(postings),
    }
    manifest = {
        "candidate_contract_version": COMMAND_CONTRACT_VERSION,
        "source_contract_version": run["contract_version"],
        "staging_schema_version": STAGING_SCHEMA_VERSION,
        "source_import_run_id": run_id,
        "source_set_fingerprint": run["source_set_fingerprint"],
        "parser_bundle_fingerprint": run["parser_bundle_fingerprint"],
        "tenant_id": run["tenant_id"],
        "user_id": run["user_id"],
        "sandbox_id": run["sandbox_id"],
        "counts": counts,
        "portfolios": portfolios,
        "accounts": accounts,
        "assets": assets,
        "transactions": transactions,
        "postings": postings,
    }
    canonical_json_bytes(manifest)
    return manifest


def sqlite_master_contract_fingerprint(connection: sqlite3.Connection) -> str:
    objects = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL
        ORDER BY type, name
        """
    ).fetchall()
    digest = hashlib.sha256()
    for row in objects:
        for value in row:
            encoded = value.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
    return digest.hexdigest()


def staging_contract_schema_fingerprint(staging: sqlite3.Connection) -> str:
    return sqlite_master_contract_fingerprint(staging)


def staging_contract_catalogs(staging: sqlite3.Connection) -> dict[str, Any]:
    return {
        "schema_contract": _fetch_dicts(
            staging,
            """
            SELECT schema_id, source_kind, header_fingerprint, status, projection_id,
                   fixture_only, legacy_read_only_enabled, provenance
            FROM schema_contract ORDER BY schema_id
            """,
        ),
        "diagnostic_catalog": _fetch_dicts(
            staging,
            """
            SELECT diagnostic_code, default_severity, scope, publish_blocking,
                   safe_description
            FROM diagnostic_catalog ORDER BY diagnostic_code
            """,
        ),
        "reconciliation_requirements": _fetch_dicts(
            staging,
            """
            SELECT requirement_id, applicability, gate_level, dimension_contract,
                   safe_description
            FROM reconciliation_requirement ORDER BY requirement_id
            """,
        ),
    }


def staging_contract_catalog_fingerprint(staging: sqlite3.Connection) -> str:
    return fingerprint(staging_contract_catalogs(staging))


def build_artifact_manifest(staging: sqlite3.Connection, candidate_fingerprint: str) -> dict[str, Any]:
    run = _fetch_exactly_one(staging, "SELECT * FROM import_run", "staging_run_count_invalid")
    run_id = run["import_run_id"]
    run_evidence_keys = (
        "import_run_id",
        "contract_version",
        "import_profile",
        "execution_mode",
        "tenant_id",
        "user_id",
        "sandbox_id",
        "source_root_token",
        "source_set_fingerprint",
        "parser_bundle_fingerprint",
        "file_limit",
        "total_byte_limit",
        "total_row_limit",
        "started_at_utc",
    )
    catalogs = staging_contract_catalogs(staging)
    manifest = {
        "artifact_contract_version": COMMAND_CONTRACT_VERSION,
        "candidate_fingerprint": candidate_fingerprint,
        "staging_contract_schema_fingerprint": staging_contract_schema_fingerprint(staging),
        "staging_contract_catalog_fingerprint": fingerprint(catalogs),
        "run": {key: run[key] for key in run_evidence_keys},
        **catalogs,
        "source_files": _fetch_dicts(
            staging,
            """
            SELECT source_file_id, source_alias, source_kind, schema_id, parser_status,
                   byte_size, data_row_count, header_fingerprint,
                   content_fingerprint_before, content_fingerprint_after
            FROM source_file WHERE import_run_id=? ORDER BY source_file_id
            """,
            (run_id,),
        ),
        "source_rows": _fetch_dicts(
            staging,
            """
            SELECT source_row_id, source_file_id, data_row_ordinal,
                   source_row_fingerprint, disposition
            FROM source_row WHERE import_run_id=? ORDER BY source_file_id, data_row_ordinal
            """,
            (run_id,),
        ),
        "source_row_mappings": _fetch_dicts(
            staging,
            """
            SELECT source_row_mapping_id, source_row_id, entity_kind,
                   staged_portfolio_id, staged_account_id, staged_asset_id,
                   staged_transaction_id
            FROM source_row_mapping WHERE import_run_id=? ORDER BY source_row_mapping_id
            """,
            (run_id,),
        ),
        "diagnostics": _fetch_dicts(
            staging,
            """
            SELECT diagnostic_id, diagnostic_code, source_file_id, source_row_id,
                   entity_kind, entity_ref, field_key, safe_detail_code,
                   evidence_fingerprint
            FROM import_diagnostic WHERE import_run_id=? ORDER BY diagnostic_id
            """,
            (run_id,),
        ),
        "reconciliation_results": _fetch_dicts(
            staging,
            """
            SELECT reconciliation_result_id, requirement_id, is_summary,
                   dimension_kind, dimension_ref, applicable, status, reason_code,
                   evidence_fingerprint
            FROM reconciliation_result WHERE import_run_id=?
            ORDER BY requirement_id, is_summary DESC, dimension_kind, dimension_ref,
                     reconciliation_result_id
            """,
            (run_id,),
        ),
        "reconciliation_metrics": _fetch_dicts(
            staging,
            """
            SELECT metric.reconciliation_metric_id, metric.reconciliation_result_id,
                   metric.metric_kind, metric.expected_value, metric.actual_value,
                   metric.difference_decimal, metric.tolerance_decimal
            FROM reconciliation_metric metric
            JOIN reconciliation_result result
              ON result.reconciliation_result_id = metric.reconciliation_result_id
            WHERE result.import_run_id=?
            ORDER BY metric.reconciliation_result_id, metric.reconciliation_metric_id
            """,
            (run_id,),
        ),
        "gate": _fetch_exactly_one(
            staging,
            "SELECT * FROM reconciliation_gate WHERE import_run_id=?",
            "staging_gate_missing",
            (run_id,),
        ),
    }
    canonical_json_bytes(manifest)
    return manifest


def compute_staging_fingerprints(staging: sqlite3.Connection) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    candidate_manifest = build_candidate_manifest(staging)
    candidate_fingerprint = fingerprint(candidate_manifest)
    artifact_manifest = build_artifact_manifest(staging, candidate_fingerprint)
    artifact_fingerprint = fingerprint(artifact_manifest)
    return candidate_manifest, artifact_manifest, candidate_fingerprint, artifact_fingerprint


def _validate_runtime(runtime: RuntimeContext) -> None:
    if runtime.role not in ALLOWED_ROLES:
        raise DataCommandError("runtime_role_not_authorized")
    for value, prefix in ((runtime.data_space_id, "sbx_"),):
        if not _is_identifier(value, prefix):
            raise DataCommandError("runtime_context_invalid")
    for value in (runtime.tenant_id, runtime.user_id, runtime.actor_id):
        if not isinstance(value, str) or not (3 <= len(value) <= 80) or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
            raise DataCommandError("runtime_context_invalid")


def _validate_sealed_staging_snapshot(
    staging: sqlite3.Connection,
    runtime: RuntimeContext,
) -> ValidatedStaging:
    if staging.execute("PRAGMA user_version").fetchone()[0] != STAGING_SCHEMA_VERSION:
        raise DataCommandError("staging_schema_version_mismatch")
    if staging_contract_schema_fingerprint(staging) != EXPECTED_STAGING_SCHEMA_FINGERPRINT:
        raise DataCommandError("staging_contract_schema_mismatch")
    if staging_contract_catalog_fingerprint(staging) != EXPECTED_STAGING_CATALOG_FINGERPRINT:
        raise DataCommandError("staging_contract_catalog_mismatch")
    if staging.execute("PRAGMA foreign_key_check").fetchall():
        raise DataCommandError("staging_foreign_key_invalid")
    if staging.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise DataCommandError("staging_integrity_invalid")
    run = _fetch_exactly_one(staging, "SELECT * FROM import_run", "staging_run_count_invalid")
    seal = _fetch_exactly_one(staging, "SELECT * FROM import_seal", "staging_seal_count_invalid")
    if run["execution_mode"] != "fixture":
        raise DataCommandError("productive_import_not_enabled")
    if (
        run["tenant_id"] != runtime.tenant_id
        or run["user_id"] != runtime.user_id
        or run["sandbox_id"] != runtime.data_space_id
    ):
        raise DataCommandError("staging_runtime_context_mismatch")
    if seal["import_run_id"] != run["import_run_id"] or seal["outcome"] != "ready_for_confirmation":
        raise DataCommandError("staging_not_ready")
    gate = _fetch_exactly_one(
        staging,
        "SELECT * FROM reconciliation_gate WHERE import_run_id=?",
        "staging_gate_missing",
        (run["import_run_id"],),
    )
    if gate["ready_for_confirmation"] != 1:
        raise DataCommandError("staging_gate_closed")
    candidate_manifest, artifact_manifest, candidate_fingerprint, artifact_fingerprint = compute_staging_fingerprints(staging)
    if seal["candidate_fingerprint"] != candidate_fingerprint or seal["artifact_fingerprint"] != artifact_fingerprint:
        raise DataCommandError("staging_fingerprint_mismatch")
    return ValidatedStaging(
        run=run,
        seal=seal,
        candidate_manifest=candidate_manifest,
        artifact_manifest=artifact_manifest,
        candidate_fingerprint=candidate_fingerprint,
        artifact_fingerprint=artifact_fingerprint,
        counts=dict(candidate_manifest["counts"]),
    )


def validate_sealed_staging(staging: sqlite3.Connection, runtime: RuntimeContext) -> ValidatedStaging:
    _validate_runtime(runtime)
    if staging.in_transaction:
        raise DataCommandError("staging_connection_in_transaction")
    staging.execute("PRAGMA query_only = ON")
    if staging.execute("PRAGMA query_only").fetchone()[0] != 1:
        raise DataCommandError("staging_query_only_not_enforced")
    staging.execute("BEGIN")
    try:
        return _validate_sealed_staging_snapshot(staging, runtime)
    finally:
        if staging.in_transaction:
            staging.rollback()


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value) is None:
        raise DataCommandError("confirmation_time_invalid")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        raise DataCommandError("confirmation_time_invalid") from None


def build_confirmation(
    validated: ValidatedStaging,
    runtime: RuntimeContext,
    challenge_id: str,
    issued_at_utc: str,
    confirmed_at_utc: str,
    expires_at_utc: str,
) -> dict[str, Any]:
    payload = {
        "confirmation_contract_version": CONFIRMATION_CONTRACT_VERSION,
        "challenge_id": challenge_id,
        "tenant_id": runtime.tenant_id,
        "user_id": runtime.user_id,
        "data_space_id": runtime.data_space_id,
        "actor_id": runtime.actor_id,
        "role": runtime.role,
        "source_import_run_id": validated.run["import_run_id"],
        "source_set_fingerprint": validated.run["source_set_fingerprint"],
        "parser_bundle_fingerprint": validated.run["parser_bundle_fingerprint"],
        "staging_artifact_fingerprint": validated.artifact_fingerprint,
        "candidate_fingerprint": validated.candidate_fingerprint,
        "counts": dict(validated.counts),
        "issued_at_utc": issued_at_utc,
        "confirmed_at_utc": confirmed_at_utc,
        "expires_at_utc": expires_at_utc,
    }
    confirmation = dict(payload)
    confirmation["confirmation_fingerprint"] = fingerprint(payload)
    return confirmation


def _validate_confirmation(
    confirmation: dict[str, Any],
    validated: ValidatedStaging,
    runtime: RuntimeContext,
    now_utc: str,
) -> None:
    expected_keys = {
        "confirmation_contract_version",
        "challenge_id",
        "tenant_id",
        "user_id",
        "data_space_id",
        "actor_id",
        "role",
        "source_import_run_id",
        "source_set_fingerprint",
        "parser_bundle_fingerprint",
        "staging_artifact_fingerprint",
        "candidate_fingerprint",
        "counts",
        "issued_at_utc",
        "confirmed_at_utc",
        "expires_at_utc",
        "confirmation_fingerprint",
    }
    if not isinstance(confirmation, dict) or set(confirmation) != expected_keys:
        raise DataCommandError("confirmation_invalid")
    if not _is_identifier(confirmation["challenge_id"], "cfm_"):
        raise DataCommandError("confirmation_invalid")
    payload = {key: confirmation[key] for key in confirmation if key != "confirmation_fingerprint"}
    if fingerprint(payload) != confirmation["confirmation_fingerprint"]:
        raise DataCommandError("confirmation_fingerprint_mismatch")
    expected = {
        "confirmation_contract_version": CONFIRMATION_CONTRACT_VERSION,
        "tenant_id": runtime.tenant_id,
        "user_id": runtime.user_id,
        "data_space_id": runtime.data_space_id,
        "actor_id": runtime.actor_id,
        "role": runtime.role,
        "source_import_run_id": validated.run["import_run_id"],
        "source_set_fingerprint": validated.run["source_set_fingerprint"],
        "parser_bundle_fingerprint": validated.run["parser_bundle_fingerprint"],
        "staging_artifact_fingerprint": validated.artifact_fingerprint,
        "candidate_fingerprint": validated.candidate_fingerprint,
        "counts": validated.counts,
    }
    for key, value in expected.items():
        if confirmation[key] != value:
            raise DataCommandError("confirmation_scope_mismatch")
    issued = _parse_utc(confirmation["issued_at_utc"])
    confirmed = _parse_utc(confirmation["confirmed_at_utc"])
    expires = _parse_utc(confirmation["expires_at_utc"])
    now = _parse_utc(now_utc)
    if not (issued <= confirmed <= now <= expires):
        raise DataCommandError("confirmation_expired_or_time_invalid")
    if (expires - issued).total_seconds() > 600:
        raise DataCommandError("confirmation_validity_window_exceeded")


def command_id_for(runtime: RuntimeContext, source_set_fingerprint: str, candidate_fingerprint: str) -> str:
    material = "\0".join(
        (
            "legacy-import-command-v1",
            runtime.tenant_id,
            runtime.user_id,
            runtime.data_space_id,
            source_set_fingerprint,
            candidate_fingerprint,
        )
    ).encode("utf-8")
    return "cmd_import_" + hashlib.sha256(material).hexdigest()[:52]


def _validate_canonical_context(canonical: sqlite3.Connection, runtime: RuntimeContext) -> None:
    if canonical.execute("PRAGMA user_version").fetchone()[0] != CANONICAL_SCHEMA_VERSION:
        raise DataCommandError("canonical_schema_version_mismatch")
    if sqlite_master_contract_fingerprint(canonical) != EXPECTED_CANONICAL_SCHEMA_FINGERPRINT:
        raise DataCommandError("canonical_contract_schema_mismatch")
    binding = _fetch_exactly_one(canonical, "SELECT * FROM store_binding", "canonical_store_binding_missing")
    if (
        binding["schema_version"] != CANONICAL_SCHEMA_VERSION
        or binding["tenant_id"] != runtime.tenant_id
        or binding["user_id"] != runtime.user_id
        or binding["data_space_id"] != runtime.data_space_id
    ):
        raise DataCommandError("canonical_runtime_context_mismatch")
    if canonical.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        raise DataCommandError("canonical_foreign_keys_disabled")
    if canonical.execute("PRAGMA query_only").fetchone()[0] != 0:
        raise DataCommandError("canonical_connection_query_only")
    if canonical.execute("PRAGMA foreign_key_check").fetchall():
        raise DataCommandError("canonical_foreign_key_invalid")


def receipt_row_fingerprint_valid(receipt: dict[str, Any], runtime: RuntimeContext) -> bool:
    payload_keys = (
        "command_id",
        "tenant_id",
        "user_id",
        "target_sandbox_id",
        "target_portfolio_id",
        "source_contract_version",
        "staging_schema_version",
        "canonical_schema_version",
        "source_import_run_id",
        "source_set_fingerprint",
        "parser_bundle_fingerprint",
        "staging_artifact_fingerprint",
        "candidate_fingerprint",
        "confirmation_fingerprint",
        "origin_ref_namespace",
        "portfolio_count",
        "account_count",
        "asset_count",
        "transaction_count",
        "posting_count",
        "actor_id",
        "committed_at_utc",
    )
    payload = {key: receipt[key] for key in payload_keys}
    expected_fingerprint = fingerprint(payload)
    expected_command_id = command_id_for(
        runtime,
        receipt["source_set_fingerprint"],
        receipt["candidate_fingerprint"],
    )
    return (
        receipt["receipt_fingerprint"] == expected_fingerprint
        and receipt["import_receipt_id"] == "irc_" + expected_fingerprint[:32]
        and receipt["command_id"] == expected_command_id
        and receipt["origin_ref_namespace"] == f"lir_{receipt['candidate_fingerprint'][:24]}_"
    )


def _preflight(canonical: sqlite3.Connection, validated: ValidatedStaging, runtime: RuntimeContext) -> tuple[str, str | None]:
    rows = _fetch_dicts(
        canonical,
        """
        SELECT * FROM canonical_import_receipt
        WHERE source_set_fingerprint=? OR candidate_fingerprint=?
        ORDER BY import_receipt_id
        """,
        (validated.run["source_set_fingerprint"], validated.candidate_fingerprint),
    )
    if not rows:
        return "new_candidate", None
    if len(rows) == 1:
        receipt = rows[0]
        exact = (
            receipt["source_import_run_id"] == validated.run["import_run_id"]
            and receipt["source_set_fingerprint"] == validated.run["source_set_fingerprint"]
            and receipt["parser_bundle_fingerprint"] == validated.run["parser_bundle_fingerprint"]
            and receipt["staging_artifact_fingerprint"] == validated.artifact_fingerprint
            and receipt["candidate_fingerprint"] == validated.candidate_fingerprint
            and receipt["tenant_id"] == runtime.tenant_id
            and receipt["user_id"] == runtime.user_id
            and receipt["target_sandbox_id"] == runtime.data_space_id
            and receipt["source_contract_version"] == validated.run["contract_version"]
            and receipt["staging_schema_version"] == STAGING_SCHEMA_VERSION
            and receipt["canonical_schema_version"] == CANONICAL_SCHEMA_VERSION
            and all(receipt[key] == value for key, value in validated.counts.items())
            and receipt_row_fingerprint_valid(receipt, runtime)
        )
        audit_matches = canonical.execute(
            """
            SELECT count(*) FROM data_command_audit
            WHERE command_id=?
              AND area_id='canonical_import_receipt'
              AND command_type='legacy_import_commit_v1'
              AND entity_id=?
              AND actor_id=?
              AND committed_at_utc=?
              AND payload_fingerprint=?
              AND origin_type='legacy_import'
              AND origin_ref=?
            """,
            (
                receipt["command_id"],
                receipt["target_portfolio_id"],
                receipt["actor_id"],
                receipt["committed_at_utc"],
                receipt["candidate_fingerprint"],
                receipt["source_import_run_id"],
            ),
        ).fetchone()[0]
        if exact and audit_matches == 1:
            return "already_imported", receipt["import_receipt_id"]
    return "idempotency_conflict", None


def _target_is_empty(canonical: sqlite3.Connection) -> bool:
    tables = (
        "portfolio",
        "account",
        "asset",
        "provider_mapping",
        "transaction_record",
        "transaction_posting",
        "transaction_seal",
        "data_command_audit",
        "canonical_import_receipt",
    )
    return all(canonical.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0 for table in tables)


def _deterministic_id(prefix: str, candidate_fingerprint: str, kind: str, staged_id: str) -> str:
    digest = hashlib.sha256(f"{candidate_fingerprint}\0{kind}\0{staged_id}".encode("utf-8")).hexdigest()
    return prefix + digest[:24]


def _origin_ref(namespace: str, kind: str, staged_id: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{staged_id}".encode("utf-8")).hexdigest()[:20]
    return f"{namespace}{kind}_{digest}"


def _insert_candidate(
    canonical: sqlite3.Connection,
    validated: ValidatedStaging,
    runtime: RuntimeContext,
    committed_at_utc: str,
) -> tuple[dict[str, dict[str, str]], str]:
    manifest = validated.candidate_manifest
    candidate_fp = validated.candidate_fingerprint
    namespace = f"lir_{candidate_fp[:24]}_"
    mappings: dict[str, dict[str, str]] = {
        "portfolio": {},
        "account": {},
        "asset": {},
        "transaction": {},
        "posting": {},
    }
    for item in manifest["portfolios"]:
        staged_id = item["staged_portfolio_id"]
        canonical_id = _deterministic_id("ptf_", candidate_fp, "portfolio", staged_id)
        mappings["portfolio"][staged_id] = canonical_id
        canonical.execute(
            """
            INSERT INTO portfolio
            (portfolio_id, display_name, base_currency, origin_type, origin_ref,
             created_at_utc, updated_at_utc)
            VALUES (?, ?, ?, 'legacy_import', ?, ?, ?)
            """,
            (
                canonical_id,
                item["display_name"],
                item["base_currency"],
                _origin_ref(namespace, "ptf", staged_id),
                committed_at_utc,
                committed_at_utc,
            ),
        )
    for item in manifest["accounts"]:
        staged_id = item["staged_account_id"]
        canonical_id = _deterministic_id("acc_", candidate_fp, "account", staged_id)
        mappings["account"][staged_id] = canonical_id
        canonical.execute(
            """
            INSERT INTO account
            (account_id, portfolio_id, display_name, account_type, origin_type,
             origin_ref, created_at_utc, updated_at_utc)
            VALUES (?, ?, ?, ?, 'legacy_import', ?, ?, ?)
            """,
            (
                canonical_id,
                mappings["portfolio"][item["staged_portfolio_id"]],
                item["display_name"],
                item["account_type"],
                _origin_ref(namespace, "acc", staged_id),
                committed_at_utc,
                committed_at_utc,
            ),
        )
    for item in manifest["assets"]:
        staged_id = item["staged_asset_id"]
        canonical_id = _deterministic_id("ast_", candidate_fp, "asset", staged_id)
        mappings["asset"][staged_id] = canonical_id
        canonical.execute(
            """
            INSERT INTO asset
            (asset_id, display_name, asset_type, price_currency, quantity_scale,
             valuation_method, isin, origin_type, origin_ref, created_at_utc,
             updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'legacy_import', ?, ?, ?)
            """,
            (
                canonical_id,
                item["display_name"],
                item["asset_type"],
                item["price_currency"],
                item["quantity_scale"],
                item["valuation_method"],
                item["isin"],
                _origin_ref(namespace, "ast", staged_id),
                committed_at_utc,
                committed_at_utc,
            ),
        )
    postings_by_transaction: dict[str, list[dict[str, Any]]] = {}
    for posting in manifest["postings"]:
        postings_by_transaction.setdefault(posting["staged_transaction_id"], []).append(posting)
    for item in manifest["transactions"]:
        staged_id = item["staged_transaction_id"]
        canonical_id = _deterministic_id("txn_", candidate_fp, "transaction", staged_id)
        mappings["transaction"][staged_id] = canonical_id
        canonical.execute(
            """
            INSERT INTO transaction_record
            (transaction_id, portfolio_id, transaction_type, record_action,
             effective_at_utc, local_date, origin_type, origin_ref,
             created_at_utc, created_by_actor)
            VALUES (?, ?, ?, 'book', ?, ?, 'legacy_import', ?, ?, ?)
            """,
            (
                canonical_id,
                mappings["portfolio"][item["staged_portfolio_id"]],
                item["transaction_type"],
                item["effective_at_utc"],
                item["local_date"],
                _origin_ref(namespace, "txn", staged_id),
                committed_at_utc,
                runtime.actor_id,
            ),
        )
        canonical_posting_manifest: list[dict[str, Any]] = []
        for posting in postings_by_transaction.get(staged_id, []):
            staged_posting_id = posting["staged_posting_id"]
            posting_id = _deterministic_id("pst_", candidate_fp, "posting", staged_posting_id)
            mappings["posting"][staged_posting_id] = posting_id
            posting_values = (
                posting_id,
                canonical_id,
                posting["sequence_no"],
                mappings["account"][posting["staged_account_id"]],
                mappings["asset"][posting["staged_asset_id"]],
                posting["posting_role"],
                posting["quantity_decimal"],
                posting["unit_price_decimal"],
                posting["price_currency"],
                posting["valuation_amount_decimal"],
                posting["valuation_currency"],
            )
            canonical.execute(
                """
                INSERT INTO transaction_posting
                (posting_id, transaction_id, sequence_no, account_id, asset_id,
                 posting_role, quantity_decimal, unit_price_decimal, price_currency,
                 valuation_amount_decimal, valuation_currency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                posting_values,
            )
            canonical_posting_manifest.append(
                {
                    "posting_id": posting_id,
                    "sequence_no": posting["sequence_no"],
                    "account_id": mappings["account"][posting["staged_account_id"]],
                    "asset_id": mappings["asset"][posting["staged_asset_id"]],
                    "posting_role": posting["posting_role"],
                    "quantity_decimal": posting["quantity_decimal"],
                    "unit_price_decimal": posting["unit_price_decimal"],
                    "price_currency": posting["price_currency"],
                    "valuation_amount_decimal": posting["valuation_amount_decimal"],
                    "valuation_currency": posting["valuation_currency"],
                }
            )
        transaction_content = {
            "transaction_id": canonical_id,
            "portfolio_id": mappings["portfolio"][item["staged_portfolio_id"]],
            "transaction_type": item["transaction_type"],
            "effective_at_utc": item["effective_at_utc"],
            "local_date": item["local_date"],
            "postings": canonical_posting_manifest,
        }
        canonical.execute(
            "INSERT INTO transaction_seal VALUES (?, ?, ?, ?)",
            (canonical_id, committed_at_utc, len(canonical_posting_manifest), fingerprint(transaction_content)),
        )
    if len(mappings["portfolio"]) != 1:
        raise DataCommandError("candidate_portfolio_count_invalid")
    target_portfolio_id = next(iter(mappings["portfolio"].values()))
    return mappings, target_portfolio_id


def dry_run_candidate_projection(
    candidate_manifest: dict[str, Any],
    candidate_fingerprint: str,
    runtime: RuntimeContext,
    committed_at_utc: str,
    canonical_v2_sql: str,
    canonical_v2_1_migration_sql: str,
) -> None:
    """Validate a candidate against a throwaway in-memory canonical store."""

    validate_candidate_transaction_semantics(candidate_manifest)
    counts = {
        "portfolio_count": len(candidate_manifest["portfolios"]),
        "account_count": len(candidate_manifest["accounts"]),
        "asset_count": len(candidate_manifest["assets"]),
        "transaction_count": len(candidate_manifest["transactions"]),
        "posting_count": len(candidate_manifest["postings"]),
    }
    validated = ValidatedStaging(
        run={},
        seal={},
        candidate_manifest=candidate_manifest,
        artifact_manifest={},
        candidate_fingerprint=candidate_fingerprint,
        artifact_fingerprint="0" * 64,
        counts=counts,
    )
    canonical = sqlite3.connect(":memory:")
    try:
        canonical.executescript(canonical_v2_sql)
        canonical.executescript(canonical_v2_1_migration_sql)
        canonical.execute(
            "INSERT INTO store_binding VALUES (1, 201, ?, ?, ?, ?)",
            (runtime.tenant_id, runtime.user_id, runtime.data_space_id, committed_at_utc),
        )
        canonical.commit()
        _validate_canonical_context(canonical, runtime)
        _insert_candidate(canonical, validated, runtime, committed_at_utc)
        if canonical.execute("PRAGMA foreign_key_check").fetchall():
            raise DataCommandError("canonical_foreign_key_invalid")
        if canonical.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DataCommandError("canonical_integrity_invalid")
        if canonical.execute("SELECT count(*) FROM current_transaction").fetchone()[0] != counts["transaction_count"]:
            raise DataCommandError("canonical_transaction_failed")
        if canonical.execute("SELECT count(*) FROM current_transaction_posting").fetchone()[0] != counts["posting_count"]:
            raise DataCommandError("canonical_transaction_failed")
    except DataCommandError:
        raise
    except Exception:
        raise DataCommandError("canonical_transaction_failed") from None
    finally:
        if canonical.in_transaction:
            canonical.rollback()
        canonical.close()


def _receipt_payload(
    validated: ValidatedStaging,
    runtime: RuntimeContext,
    command_id: str,
    target_portfolio_id: str,
    confirmation_fingerprint: str,
    committed_at_utc: str,
) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "tenant_id": runtime.tenant_id,
        "user_id": runtime.user_id,
        "target_sandbox_id": runtime.data_space_id,
        "target_portfolio_id": target_portfolio_id,
        "source_contract_version": validated.run["contract_version"],
        "staging_schema_version": STAGING_SCHEMA_VERSION,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
        "source_import_run_id": validated.run["import_run_id"],
        "source_set_fingerprint": validated.run["source_set_fingerprint"],
        "parser_bundle_fingerprint": validated.run["parser_bundle_fingerprint"],
        "staging_artifact_fingerprint": validated.artifact_fingerprint,
        "candidate_fingerprint": validated.candidate_fingerprint,
        "confirmation_fingerprint": confirmation_fingerprint,
        "origin_ref_namespace": f"lir_{validated.candidate_fingerprint[:24]}_",
        **validated.counts,
        "actor_id": runtime.actor_id,
        "committed_at_utc": committed_at_utc,
    }


def _execute_synthetic_import_impl(
    staging: sqlite3.Connection,
    canonical: sqlite3.Connection,
    runtime: RuntimeContext,
    confirmation: dict[str, Any] | None,
    authorizer: OneUseConfirmationAuthorizer,
    now_utc: str,
    before_receipt_hook: Callable[[], None] | None = None,
) -> CommandResult:
    validated = validate_sealed_staging(staging, runtime)
    try:
        validate_candidate_transaction_semantics(validated.candidate_manifest)
    except TransactionSemanticsError:
        raise DataCommandError("transaction_semantics_invalid") from None
    _validate_canonical_context(canonical, runtime)
    command_id = command_id_for(runtime, validated.run["source_set_fingerprint"], validated.candidate_fingerprint)
    status, receipt_id = _preflight(canonical, validated, runtime)
    if status == "already_imported":
        return CommandResult(status, command_id, validated.candidate_fingerprint, receipt_id, validated.counts)
    if status != "new_candidate":
        raise DataCommandError("idempotency_conflict")
    if not _target_is_empty(canonical):
        raise DataCommandError("target_sandbox_not_empty")
    if canonical.in_transaction:
        raise DataCommandError("canonical_connection_already_in_transaction")
    if confirmation is None:
        raise DataCommandError("confirmation_missing")
    _validate_confirmation(confirmation, validated, runtime, now_utc)
    authorizer.consume(confirmation["challenge_id"], confirmation["confirmation_fingerprint"])
    try:
        canonical.execute("BEGIN IMMEDIATE")
        _validate_canonical_context(canonical, runtime)
        locked_status, locked_receipt_id = _preflight(canonical, validated, runtime)
        if locked_status == "already_imported":
            canonical.rollback()
            return CommandResult(
                "already_imported",
                command_id,
                validated.candidate_fingerprint,
                locked_receipt_id,
                validated.counts,
            )
        if locked_status != "new_candidate":
            raise DataCommandError("idempotency_conflict")
        if not _target_is_empty(canonical):
            raise DataCommandError("target_sandbox_not_empty")
        _, target_portfolio_id = _insert_candidate(canonical, validated, runtime, now_utc)
        if before_receipt_hook is not None:
            before_receipt_hook()
        canonical.execute(
            """
            INSERT INTO data_command_audit
            (command_id, area_id, command_type, entity_id, actor_id,
             committed_at_utc, payload_fingerprint, origin_type, origin_ref)
            VALUES (?, 'canonical_import_receipt', 'legacy_import_commit_v1', ?, ?, ?, ?,
                    'legacy_import', ?)
            """,
            (
                command_id,
                target_portfolio_id,
                runtime.actor_id,
                now_utc,
                validated.candidate_fingerprint,
                validated.run["import_run_id"],
            ),
        )
        receipt_payload = _receipt_payload(
            validated,
            runtime,
            command_id,
            target_portfolio_id,
            confirmation["confirmation_fingerprint"],
            now_utc,
        )
        receipt_fingerprint = fingerprint(receipt_payload)
        import_receipt_id = "irc_" + receipt_fingerprint[:32]
        canonical.execute(
            """
            INSERT INTO canonical_import_receipt
            (import_receipt_id, command_id, tenant_id, user_id, target_sandbox_id,
             target_portfolio_id, source_contract_version, staging_schema_version,
             canonical_schema_version, source_import_run_id, source_set_fingerprint,
             parser_bundle_fingerprint, staging_artifact_fingerprint,
             candidate_fingerprint, confirmation_fingerprint, origin_ref_namespace,
             portfolio_count, account_count, asset_count, transaction_count,
             posting_count, actor_id, committed_at_utc, receipt_fingerprint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_receipt_id,
                receipt_payload["command_id"],
                receipt_payload["tenant_id"],
                receipt_payload["user_id"],
                receipt_payload["target_sandbox_id"],
                receipt_payload["target_portfolio_id"],
                receipt_payload["source_contract_version"],
                receipt_payload["staging_schema_version"],
                receipt_payload["canonical_schema_version"],
                receipt_payload["source_import_run_id"],
                receipt_payload["source_set_fingerprint"],
                receipt_payload["parser_bundle_fingerprint"],
                receipt_payload["staging_artifact_fingerprint"],
                receipt_payload["candidate_fingerprint"],
                receipt_payload["confirmation_fingerprint"],
                receipt_payload["origin_ref_namespace"],
                receipt_payload["portfolio_count"],
                receipt_payload["account_count"],
                receipt_payload["asset_count"],
                receipt_payload["transaction_count"],
                receipt_payload["posting_count"],
                receipt_payload["actor_id"],
                receipt_payload["committed_at_utc"],
                receipt_fingerprint,
            ),
        )
        if canonical.execute("PRAGMA foreign_key_check").fetchall():
            raise DataCommandError("canonical_foreign_key_invalid")
        if canonical.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise DataCommandError("canonical_integrity_invalid")
        canonical.commit()
        return CommandResult(
            "committed",
            command_id,
            validated.candidate_fingerprint,
            import_receipt_id,
            validated.counts,
        )
    except Exception as error:
        if canonical.in_transaction:
            canonical.rollback()
        if isinstance(error, DataCommandError):
            raise
        raise DataCommandError("canonical_transaction_failed") from None


def execute_synthetic_import(
    staging: sqlite3.Connection,
    canonical: sqlite3.Connection,
    runtime: RuntimeContext,
    confirmation: dict[str, Any] | None,
    authorizer: OneUseConfirmationAuthorizer,
    now_utc: str,
    before_receipt_hook: Callable[[], None] | None = None,
) -> CommandResult:
    try:
        return _execute_synthetic_import_impl(
            staging,
            canonical,
            runtime,
            confirmation,
            authorizer,
            now_utc,
            before_receipt_hook,
        )
    except DataCommandError:
        raise
    except Exception:
        raise DataCommandError("command_preflight_failed") from None
