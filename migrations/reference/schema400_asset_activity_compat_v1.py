"""Additive schema-400 Asset Activity compatibility and canonical command v1.

The migration preserves every existing schema-400 Transaction byte as its original
fact and adds a separate immutable Asset Activity event area at schema 401. Before
the first Event, ADR-129's marked erratum aligns net Sale proceeds with the signed
exact-Decimal contract without modifying protected schema-401 bytes. The command
validates ADR-100 semantics, binds a fresh one-use confirmation and writes
only the new area. It has no source discovery, Cash settlement, Provider, Worker or
private-data capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any
from urllib.parse import quote

from migrations.reference.asset_activity_v1 import (
    AssetActivityV1Error,
    validate_asset_activity_v1,
)
from migrations.reference.legacy_per_asset_trade_planner_v1 import (
    LegacyPerAssetTradePlannerV1Error,
    plan_legacy_per_asset_trade_v1,
)

CONTRACT_VERSION = 1
SOURCE_SCHEMA_VERSION = 400
TARGET_SCHEMA_VERSION = 401
ALLOWED_ROLES = frozenset({"desktop_owner", "data_admin"})
ALLOWED_FAILPOINTS = frozenset({None, "after_receipt", "after_events", "before_commit"})
ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT / "contracts" / "portfolio-ledger" / "v1.1" / "add-asset-activity-v1.sql"
SIGNED_NET_PROCEEDS_PATCH_PATH = ROOT / "contracts" / "portfolio-ledger" / "v1.1" / "patch-signed-net-trade-proceeds-v1.sql"
FAILURE_CODES = frozenset(
    {
        "schema400_asset_activity_boundary_failed",
        "schema400_asset_activity_catalog_invalid",
        "schema400_asset_activity_confirmation_consumed",
        "schema400_asset_activity_confirmation_duplicate",
        "schema400_asset_activity_confirmation_expired",
        "schema400_asset_activity_confirmation_invalid",
        "schema400_asset_activity_confirmation_missing",
        "schema400_asset_activity_confirmation_not_authorized",
        "schema400_asset_activity_confirmation_scope_mismatch",
        "schema400_asset_activity_context_invalid",
        "schema400_asset_activity_input_invalid",
        "schema400_asset_activity_integrity_invalid",
        "schema400_asset_activity_migration_failed",
        "schema400_asset_activity_plan_invalid",
        "schema400_asset_activity_plan_not_ready",
        "schema400_asset_activity_reconciliation_mismatch",
        "schema400_asset_activity_role_not_authorized",
        "schema400_asset_activity_schema_unsupported",
        "schema400_asset_activity_source_stale",
        "schema400_asset_activity_transaction_failed",
        "synthetic_schema400_asset_activity_failpoint",
    }
)
_REF = re.compile(r"[a-z]{2,8}_[a-z0-9]{4,60}")
_SHA = re.compile(r"[a-f0-9]{64}")
_CHALLENGE = re.compile(r"sac_[a-f0-9]{16,64}")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


class Schema400AssetActivityCompatV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("schema400_asset_activity_error_code_unregistered")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Schema400AssetActivityContextV1:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str
    role: str


@dataclass(frozen=True)
class Schema400AssetActivityResultV1:
    status: str
    command_id: str
    event_count: int
    confirmation_fingerprint: str
    committed_at_utc: str
    canonical_write: bool
    cash_posting_count: int = 0


class OneUseSchema400AssetActivityAuthorizerV1:
    def __init__(self) -> None:
        self._registered: dict[str, str] = {}
        self._consumed: set[str] = set()

    def register(self, confirmation: dict[str, Any]) -> None:
        challenge = confirmation.get("challenge_id") if isinstance(confirmation, dict) else None
        fingerprint = confirmation.get("confirmation_fingerprint") if isinstance(confirmation, dict) else None
        if not isinstance(challenge, str) or _CHALLENGE.fullmatch(challenge) is None or not isinstance(fingerprint, str) or _SHA.fullmatch(fingerprint) is None:
            _abort("schema400_asset_activity_confirmation_invalid")
        if challenge in self._registered:
            _abort("schema400_asset_activity_confirmation_duplicate")
        self._registered[challenge] = fingerprint

    def consume(self, challenge: str, fingerprint: str) -> None:
        if self._registered.get(challenge) != fingerprint:
            _abort("schema400_asset_activity_confirmation_not_authorized")
        if challenge in self._consumed:
            _abort("schema400_asset_activity_confirmation_consumed")
        self._consumed.add(challenge)

    def is_consumed(self, challenge: str) -> bool:
        return challenge in self._consumed


def schema400_asset_activity_compat_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise Schema400AssetActivityCompatV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except Exception:
        _abort("schema400_asset_activity_input_invalid")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _utc(value: Any, code: str) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort(code)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort(code)


def _context(value: Any) -> Schema400AssetActivityContextV1:
    if not isinstance(value, Schema400AssetActivityContextV1):
        _abort("schema400_asset_activity_context_invalid")
    values = (value.tenant_id, value.user_id, value.data_space_id, value.actor_id)
    if any(not isinstance(item, str) or not 3 <= len(item) <= 80 or re.fullmatch(r"[A-Za-z0-9_-]+", item) is None for item in values):
        _abort("schema400_asset_activity_context_invalid")
    if value.role not in ALLOWED_ROLES:
        _abort("schema400_asset_activity_role_not_authorized")
    return value


def _context_fingerprint(value: Schema400AssetActivityContextV1) -> str:
    return _fingerprint(
        {
            "contract_version": CONTRACT_VERSION,
            "tenant_id": value.tenant_id,
            "user_id": value.user_id,
            "data_space_id": value.data_space_id,
            "actor_id": value.actor_id,
            "role": value.role,
        }
    )


def _regular_database(path_value: Any) -> Path:
    if not isinstance(path_value, (str, Path)):
        _abort("schema400_asset_activity_schema_unsupported")
    path = Path(path_value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        _abort("schema400_asset_activity_schema_unsupported")
    current = path
    while current.parent != current:
        if current.is_symlink():
            _abort("schema400_asset_activity_schema_unsupported")
        current = current.parent
    try:
        resolved = path.resolve(strict=True)
        metadata = path.stat(follow_symlinks=False)
    except OSError:
        _abort("schema400_asset_activity_schema_unsupported")
    if (
        resolved != path
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
    ):
        _abort("schema400_asset_activity_schema_unsupported")
    return resolved


def _uri(path: Path, mode: str, *, immutable: bool = False) -> str:
    suffix = "&immutable=1" if immutable else ""
    return f"file:{quote(str(path))}?mode={mode}{suffix}"


def _connect(path: Path, *, writable: bool) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(_uri(path, "rw" if writable else "ro", immutable=not writable), uri=True)
        connection.execute("PRAGMA foreign_keys=ON")
        connection.row_factory = sqlite3.Row
        if not writable:
            connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error:
        _abort("schema400_asset_activity_schema_unsupported")


def _validate_binding(connection: sqlite3.Connection, context: Schema400AssetActivityContextV1, allowed_versions: set[int]) -> int:
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM ledger_store_binding WHERE singleton_id=1"
        ).fetchall()
    except sqlite3.Error:
        _abort("schema400_asset_activity_schema_unsupported")
    if version not in allowed_versions or len(binding) != 1 or binding[0][0] != version:
        _abort("schema400_asset_activity_schema_unsupported")
    if tuple(binding[0][1:]) != (context.tenant_id, context.user_id, context.data_space_id):
        _abort("schema400_asset_activity_context_invalid")
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
        _abort("schema400_asset_activity_integrity_invalid")
    return version


def _catalog(connection: sqlite3.Connection, portfolio_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(portfolio_id, str) or _REF.fullmatch(portfolio_id) is None or not portfolio_id.startswith("ptf_"):
        _abort("schema400_asset_activity_input_invalid")
    portfolio = connection.execute(
        "SELECT entity.portfolio_id,revision.base_currency,revision.status FROM portfolio_entity entity JOIN current_portfolio_revision revision USING(portfolio_id) WHERE entity.portfolio_id=?",
        (portfolio_id,),
    ).fetchall()
    if len(portfolio) != 1 or portfolio[0]["status"] != "active":
        _abort("schema400_asset_activity_catalog_invalid")
    accounts = {
        row["account_id"]: {"account_ref": row["account_id"], "account_type": row["account_type"]}
        for row in connection.execute(
            "SELECT entity.account_id,revision.account_type,revision.status FROM account_entity entity JOIN current_account_revision revision USING(account_id) WHERE entity.portfolio_id=?",
            (portfolio_id,),
        )
        if row["status"] == "active" and row["account_type"] in {"securities", "crypto_wallet", "other"}
    }
    assets = {
        row["asset_id"]: {"asset_ref": row["asset_id"], "asset_type": row["asset_type"], "quantity_scale": row["quantity_scale"]}
        for row in connection.execute(
            "SELECT asset_id,asset_type,quantity_scale,status FROM current_asset_revision"
        )
        if row["status"] == "active" and row["asset_type"] != "cash" and row["quantity_scale"] is not None
    }
    if not accounts or not assets:
        _abort("schema400_asset_activity_catalog_invalid")
    return dict(portfolio[0]), accounts, assets


def _catalog_fingerprint(
    portfolio: dict[str, Any],
    accounts: dict[str, dict[str, Any]],
    assets: dict[str, dict[str, Any]],
) -> str:
    return _fingerprint(
        {
            "portfolio": portfolio,
            "accounts": [accounts[key] for key in sorted(accounts)],
            "assets": [assets[key] for key in sorted(assets)],
        }
    )


def _transaction_statements(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8")
    for line in (
        "PRAGMA foreign_keys = OFF;\n",
        "PRAGMA legacy_alter_table = ON;\n",
        "BEGIN IMMEDIATE;\n",
        "COMMIT;\n",
        "PRAGMA legacy_alter_table = OFF;\n",
        "PRAGMA foreign_keys = ON;\n",
    ):
        text = text.replace(line, "")
    statements: list[str] = []
    buffer = ""
    for line in text.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""
    if buffer.strip():
        _abort("schema400_asset_activity_migration_failed")
    return tuple(statements)


def _migration_statements() -> tuple[str, ...]:
    return _transaction_statements(MIGRATION_PATH)


def _signed_net_proceeds_patch_statements() -> tuple[str, ...]:
    return _transaction_statements(SIGNED_NET_PROCEEDS_PATCH_PATH)


def _apply_migration_in_transaction(connection: sqlite3.Connection) -> None:
    if not connection.in_transaction:
        _abort("schema400_asset_activity_migration_failed")
    try:
        for statement in (*_migration_statements(), *_signed_net_proceeds_patch_statements()):
            connection.execute(statement)
    except sqlite3.Error:
        _abort("schema400_asset_activity_migration_failed")


def _event_refs(value: Any) -> list[str]:
    if not isinstance(value, list) or not value:
        _abort("schema400_asset_activity_input_invalid")
    refs = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("event_ref"), str):
            _abort("schema400_asset_activity_input_invalid")
        refs.append(item["event_ref"])
    if len(refs) != len(set(refs)):
        _abort("schema400_asset_activity_input_invalid")
    return refs


def validate_per_asset_plan_for_schema400_cutover_v1(
    plan: Any,
    *,
    target_asset_id: str,
    selected_account_ids: set[str] | frozenset[str],
) -> dict[str, Any]:
    """Revalidate one complete Planner/FIFO candidate for canonical cutover.

    The full Plan is trusted server-side input; this helper has no source-reader or
    target-write capability. It binds every row/event/effect, exact source lineage,
    selected custody scope and the complete FIFO reconciliation fingerprint.
    """

    if not isinstance(plan, dict):
        _abort("schema400_asset_activity_plan_invalid")
    body = dict(plan)
    supplied_plan_fingerprint = body.pop("plan_fingerprint", None)
    fifo = plan.get("fifo_reconciliation")
    rows = plan.get("rows")
    if (
        not isinstance(supplied_plan_fingerprint, str)
        or _SHA.fullmatch(supplied_plan_fingerprint) is None
        or supplied_plan_fingerprint != _fingerprint(body)
        or plan.get("per_asset_trade_plan_version") != 1
        or plan.get("plan_status") not in {"ready_for_sandbox_apply", "ready_for_sandbox_apply_with_incomplete_basis"}
        or not isinstance(rows, list)
        or not rows
        or plan.get("source_row_count") != len(rows)
        or plan.get("ready_row_count") != len(rows)
        or plan.get("decision_required_row_count") != 0
        or plan.get("blocked_row_count") != 0
        or plan.get("source_row_disposition_complete") is not True
        or plan.get("fifo_full_oracle_executed") is not True
        or not isinstance(fifo, dict)
        or plan.get("automatic_cash_posting_count") != 0
        or plan.get("canonical_write") is not False
        or plan.get("provider_access") is not False
        or plan.get("network_access") is not False
        or plan.get("tax_classification_inferred") is not False
        or plan.get("rounding_performed") is not False
        or plan.get("target_asset_ref") != target_asset_id
        or not isinstance(selected_account_ids, (set, frozenset))
        or not selected_account_ids
    ):
        _abort("schema400_asset_activity_plan_not_ready")
    event_refs: set[str] = set()
    row_refs: set[str] = set()
    ordinals: set[int] = set()
    source_fingerprints: dict[str, str] = {}
    memos: dict[str, str | None] = {}
    events: list[dict[str, Any]] = []
    supplied_effects: list[dict[str, Any]] = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("disposition") != "ready"
            or row.get("decision_codes") != []
            or row.get("blocker_codes") != []
            or row.get("cash_posting_created") is not False
            or not isinstance(row.get("source_row_ref"), str)
            or not isinstance(row.get("source_row_ordinal"), int)
            or isinstance(row.get("source_row_ordinal"), bool)
            or row["source_row_ordinal"] <= 0
            or not isinstance(row.get("source_row_fingerprint"), str)
            or _SHA.fullmatch(row["source_row_fingerprint"]) is None
            or not isinstance(row.get("activity_event"), dict)
            or not isinstance(row.get("activity_effect"), dict)
            or row["activity_effect"].get("cash_posting_created") is not False
            or row["activity_effect"].get("provider_price_used") is not False
            or row["activity_effect"].get("tax_classification_inferred") is not False
            or row["activity_event"].get("asset_ref") != target_asset_id
            or row["activity_event"].get("account_ref") not in selected_account_ids
            or (
                row["activity_event"].get("related_account_ref") is not None
                and row["activity_event"].get("related_account_ref") not in selected_account_ids
            )
            or (row.get("memo") is not None and (not isinstance(row["memo"], str) or len(row["memo"]) > 4000))
        ):
            _abort("schema400_asset_activity_plan_invalid")
        event_ref = row["activity_event"].get("event_ref")
        if (
            not isinstance(event_ref, str)
            or event_ref in event_refs
            or row["source_row_ref"] in row_refs
            or row["source_row_ordinal"] in ordinals
        ):
            _abort("schema400_asset_activity_plan_invalid")
        event_refs.add(event_ref)
        row_refs.add(row["source_row_ref"])
        ordinals.add(row["source_row_ordinal"])
        expected_event_ref = "evt_" + row["source_row_fingerprint"][:32]
        if event_ref != expected_event_ref:
            _abort("schema400_asset_activity_plan_invalid")
        source_fingerprints[event_ref] = row["source_row_fingerprint"]
        memos[event_ref] = row.get("memo")
        events.append(row["activity_event"])
        supplied_effects.append(row["activity_effect"])
    if ordinals != set(range(1, len(rows) + 1)):
        _abort("schema400_asset_activity_plan_invalid")
    try:
        activity_preview = validate_asset_activity_v1(
            {
                "asset_activity_version": 1,
                "basis_currency": plan.get("basis_currency"),
                "accounts": [
                    {"account_ref": account_id, "account_type": "other"}
                    for account_id in sorted(selected_account_ids)
                ],
                "assets": [
                    {"asset_ref": target_asset_id, "asset_type": "crypto", "quantity_scale": 24}
                ],
                "events": events,
            }
        )
    except AssetActivityV1Error:
        _abort("schema400_asset_activity_plan_invalid")
    # The standalone revalidation above deliberately uses only permissive selected
    # scope. Canonical Preview below revalidates the exact current Account/Asset types.
    if activity_preview["event_effects"] != supplied_effects:
        _abort("schema400_asset_activity_reconciliation_mismatch")
    fifo_body = dict(fifo)
    supplied_fifo_fingerprint = fifo_body.pop("fifo_reconciliation_fingerprint", None)
    if (
        not isinstance(supplied_fifo_fingerprint, str)
        or _SHA.fullmatch(supplied_fifo_fingerprint) is None
        or supplied_fifo_fingerprint != _fingerprint(fifo_body)
        or fifo.get("fifo_status") not in {"completed", "completed_with_missing_basis"}
        or fifo.get("cash_posting_count") != 0
        or fifo.get("synthetic_cash_posting_created") is not False
        or fifo.get("provider_price_used") is not False
        or fifo.get("tax_classification_inferred") is not False
        or len(fifo.get("event_evidence", [])) != len(rows)
        or {item.get("source_row_ref") for item in fifo.get("event_evidence", [])} != row_refs
    ):
        _abort("schema400_asset_activity_reconciliation_mismatch")
    return {
        "events": events,
        "source_row_fingerprints": source_fingerprints,
        "memos": memos,
        "plan_fingerprint": supplied_plan_fingerprint,
        "projection_fingerprint": plan.get("projection_fingerprint"),
        "source_asset_link_fingerprint": plan.get("source_asset_link_fingerprint"),
        "fifo_reconciliation_fingerprint": supplied_fifo_fingerprint,
        "source_row_count": len(rows),
    }


def preview_schema400_asset_activity_v1(
    database_path: str | Path,
    context: Schema400AssetActivityContextV1,
    portfolio_id: str,
    events: Any,
    *,
    cutover_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        runtime = _context(context)
        path = _regular_database(database_path)
        source_fingerprint = _sha_file(path)
        connection = _connect(path, writable=False)
        try:
            version = _validate_binding(connection, runtime, {SOURCE_SCHEMA_VERSION, TARGET_SCHEMA_VERSION})
            portfolio, accounts, assets = _catalog(connection, portfolio_id)
            activity = {
                "asset_activity_version": 1,
                "basis_currency": portfolio["base_currency"],
                "accounts": list(accounts.values()),
                "assets": list(assets.values()),
                "events": events,
            }
            preview = validate_asset_activity_v1(activity)
            refs = _event_refs(events)
            existing = set()
            if version == TARGET_SCHEMA_VERSION:
                existing = {
                    row[0]
                    for row in connection.execute(
                        "SELECT event_ref FROM asset_activity_event WHERE event_ref IN (%s)" % ",".join("?" for _ in refs),
                        refs,
                    )
                }
            if existing:
                _abort("schema400_asset_activity_input_invalid")
            transaction_count = connection.execute("SELECT count(*) FROM transaction_fact").fetchone()[0]
            transaction_fingerprint = _fingerprint(
                [
                    dict(row)
                    for row in connection.execute(
                        "SELECT * FROM transaction_fact ORDER BY transaction_id"
                    )
                ]
            )
        finally:
            connection.close()
        cutover = None
        if cutover_evidence is not None:
            expected_cutover_keys = {
                "plan_fingerprint", "projection_fingerprint", "source_asset_link_fingerprint",
                "fifo_reconciliation_fingerprint", "source_row_count",
            }
            if (
                not isinstance(cutover_evidence, dict)
                or set(cutover_evidence) != expected_cutover_keys
                or any(
                    not isinstance(cutover_evidence[key], str)
                    or _SHA.fullmatch(cutover_evidence[key]) is None
                    for key in expected_cutover_keys - {"source_row_count"}
                )
                or not isinstance(cutover_evidence["source_row_count"], int)
                or isinstance(cutover_evidence["source_row_count"], bool)
                or cutover_evidence["source_row_count"] != preview["event_count"]
            ):
                _abort("schema400_asset_activity_plan_invalid")
            cutover = dict(cutover_evidence)
        payload = {
            "schema_version": version,
            "context_fingerprint": _context_fingerprint(runtime),
            "portfolio_ref": portfolio_id,
            "source_fingerprint": source_fingerprint,
            "catalog_fingerprint": _catalog_fingerprint(portfolio, accounts, assets),
            "transaction_count": transaction_count,
            "source_set_fingerprint": transaction_fingerprint,
            "event_count": preview["event_count"],
            "event_effects": preview["event_effects"],
            "cutover_evidence": cutover,
            "cash_posting_count": preview["cash_posting_count"],
            "provider_price_use_count": preview["provider_price_use_count"],
            "tax_classification_inference_count": preview["tax_classification_inference_count"],
            "canonical_write": False,
            "cutover_performed": False,
            "provider_access": False,
            "network_access": False,
            "private_data_access": False,
            "source_mutation_count": 0,
        }
        payload["preview_fingerprint"] = _fingerprint(payload)
        return payload
    except Schema400AssetActivityCompatV1Error:
        raise
    except AssetActivityV1Error:
        _abort("schema400_asset_activity_input_invalid")
    except Exception:
        raise Schema400AssetActivityCompatV1Error("schema400_asset_activity_boundary_failed") from None


def build_schema400_asset_activity_confirmation_v1(
    preview: Any,
    context: Schema400AssetActivityContextV1,
    challenge_id: str,
    issued_at_utc: str,
    confirmed_at_utc: str,
    expires_at_utc: str,
) -> dict[str, Any]:
    runtime = _context(context)
    if not isinstance(preview, dict) or preview.get("preview_fingerprint") != _fingerprint({key: value for key, value in preview.items() if key != "preview_fingerprint"}):
        _abort("schema400_asset_activity_confirmation_invalid")
    if not isinstance(challenge_id, str) or _CHALLENGE.fullmatch(challenge_id) is None:
        _abort("schema400_asset_activity_confirmation_invalid")
    issued = _utc(issued_at_utc, "schema400_asset_activity_confirmation_invalid")
    confirmed = _utc(confirmed_at_utc, "schema400_asset_activity_confirmation_invalid")
    expires = _utc(expires_at_utc, "schema400_asset_activity_confirmation_invalid")
    if not issued <= confirmed <= expires or (expires - issued).total_seconds() > 600:
        _abort("schema400_asset_activity_confirmation_expired")
    body = {
        "confirmation_contract_version": CONTRACT_VERSION,
        "challenge_id": challenge_id,
        "context_fingerprint": _context_fingerprint(runtime),
        "portfolio_ref": preview["portfolio_ref"],
        "source_fingerprint": preview["source_fingerprint"],
        "catalog_fingerprint": preview["catalog_fingerprint"],
        "source_set_fingerprint": preview["source_set_fingerprint"],
        "transaction_count": preview["transaction_count"],
        "event_count": preview["event_count"],
        "cutover_evidence": preview["cutover_evidence"],
        "preview_fingerprint": preview["preview_fingerprint"],
        "issued_at_utc": issued_at_utc,
        "confirmed_at_utc": confirmed_at_utc,
        "expires_at_utc": expires_at_utc,
    }
    return {**body, "confirmation_fingerprint": _fingerprint(body)}


def _confirmation(
    value: Any,
    preview: dict[str, Any],
    context: Schema400AssetActivityContextV1,
    authorizer: OneUseSchema400AssetActivityAuthorizerV1,
    now_utc: str,
) -> dict[str, Any]:
    if value is None:
        _abort("schema400_asset_activity_confirmation_missing")
    keys = {
        "confirmation_contract_version", "challenge_id", "context_fingerprint", "portfolio_ref",
        "source_fingerprint", "catalog_fingerprint", "source_set_fingerprint", "transaction_count", "event_count",
        "cutover_evidence", "preview_fingerprint", "issued_at_utc", "confirmed_at_utc", "expires_at_utc",
        "confirmation_fingerprint",
    }
    if not isinstance(value, dict) or set(value) != keys:
        _abort("schema400_asset_activity_confirmation_invalid")
    body = {key: item for key, item in value.items() if key != "confirmation_fingerprint"}
    if value["confirmation_fingerprint"] != _fingerprint(body):
        _abort("schema400_asset_activity_confirmation_invalid")
    expected = {
        "confirmation_contract_version": CONTRACT_VERSION,
        "context_fingerprint": _context_fingerprint(context),
        "portfolio_ref": preview["portfolio_ref"],
        "source_fingerprint": preview["source_fingerprint"],
        "catalog_fingerprint": preview["catalog_fingerprint"],
        "source_set_fingerprint": preview["source_set_fingerprint"],
        "transaction_count": preview["transaction_count"],
        "event_count": preview["event_count"],
        "cutover_evidence": preview["cutover_evidence"],
        "preview_fingerprint": preview["preview_fingerprint"],
    }
    if any(value[key] != expected_value for key, expected_value in expected.items()):
        _abort("schema400_asset_activity_confirmation_scope_mismatch")
    issued = _utc(value["issued_at_utc"], "schema400_asset_activity_confirmation_invalid")
    confirmed = _utc(value["confirmed_at_utc"], "schema400_asset_activity_confirmation_invalid")
    expires = _utc(value["expires_at_utc"], "schema400_asset_activity_confirmation_invalid")
    now = _utc(now_utc, "schema400_asset_activity_confirmation_invalid")
    if not issued <= confirmed <= now <= expires or (expires - issued).total_seconds() > 600:
        _abort("schema400_asset_activity_confirmation_expired")
    if not isinstance(authorizer, OneUseSchema400AssetActivityAuthorizerV1):
        _abort("schema400_asset_activity_confirmation_not_authorized")
    return value


def migrate_schema400_asset_activity_v1(
    database_path: str | Path,
    context: Schema400AssetActivityContextV1,
) -> str:
    runtime = _context(context)
    path = _regular_database(database_path)
    connection = _connect(path, writable=True)
    close_needed = True
    try:
        version = _validate_binding(connection, runtime, {SOURCE_SCHEMA_VERSION, TARGET_SCHEMA_VERSION})
        patch_present = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='asset_activity_schema_patch'"
        ).fetchone() is not None
        if version == TARGET_SCHEMA_VERSION and patch_present:
            return "already_migrated"
        if version == TARGET_SCHEMA_VERSION and connection.execute(
            "SELECT count(*) FROM asset_activity_event"
        ).fetchone()[0] != 0:
            _abort("schema400_asset_activity_schema_unsupported")
        transaction_before = [dict(row) for row in connection.execute("SELECT * FROM transaction_fact ORDER BY transaction_id")]
        connection.close()
        close_needed = False
        connection = sqlite3.connect(_uri(path, "rw"), uri=True, isolation_level=None)
        close_needed = True
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        if version == SOURCE_SCHEMA_VERSION:
            connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
        connection.executescript(SIGNED_NET_PROCEEDS_PATCH_PATH.read_text(encoding="utf-8"))
        _validate_binding(connection, runtime, {TARGET_SCHEMA_VERSION})
        if connection.execute(
            "SELECT patch_name FROM asset_activity_schema_patch WHERE singleton_id=1"
        ).fetchone()[0] != "signed_net_trade_proceeds_v1":
            _abort("schema400_asset_activity_migration_failed")
        transaction_after = [dict(row) for row in connection.execute("SELECT * FROM transaction_fact ORDER BY transaction_id")]
        if transaction_after != transaction_before or connection.execute("SELECT count(*) FROM asset_activity_event").fetchone()[0] != 0:
            _abort("schema400_asset_activity_integrity_invalid")
        return "migrated"
    except Schema400AssetActivityCompatV1Error:
        raise
    except sqlite3.Error:
        raise Schema400AssetActivityCompatV1Error("schema400_asset_activity_migration_failed") from None
    finally:
        if close_needed:
            try:
                connection.close()
            except Exception:
                pass
        if not path.exists():
            _abort("schema400_asset_activity_migration_failed")


def _command_id(context: Schema400AssetActivityContextV1, preview_fingerprint: str) -> str:
    return "cmd_asset_" + _fingerprint(
        {"contract_version": CONTRACT_VERSION, "context": _context_fingerprint(context), "preview_fingerprint": preview_fingerprint}
    )[:48]


def _asset_activity_receipt_fingerprint(
    command_id: str,
    action_type: str,
    preview: dict[str, Any],
    confirmation_fingerprint: str,
    committed_at_utc: str,
) -> str:
    return _fingerprint(
        {
            "contract_version": CONTRACT_VERSION,
            "command_id": command_id,
            "action_type": action_type,
            "preview_fingerprint": preview["preview_fingerprint"],
            "confirmation_fingerprint": confirmation_fingerprint,
            "event_count": preview["event_count"],
            "cutover_evidence": preview["cutover_evidence"],
            "committed_at_utc": committed_at_utc,
            "cash_posting_count": 0,
        }
    )


def _event_payload(event: dict[str, Any], effect: dict[str, Any], portfolio_id: str, command_id: str, committed_at_utc: str, origin_type: str, source_row_fingerprint: str | None, memo: str | None) -> tuple[Any, ...]:
    return (
        event["event_ref"], portfolio_id, event["account_ref"], event["related_account_ref"], event["asset_ref"],
        event["source_asset_ref"], event["event_type"], event["event_time_evidence"], event["local_date"],
        event["local_time"], event["time_zone"], event["effective_at_utc"], event["original_acquired_time_evidence"],
        event["original_acquired_local_date"], event["original_acquired_local_time"], event["original_acquired_time_zone"],
        event["original_acquired_at_utc"], event["amount_input_mode"], event["basis_evidence_mode"], event["quantity_decimal"],
        event["eligible_quantity_decimal"], event["unit_price_decimal"], event["gross_amount_decimal"], event["monetary_fee_decimal"],
        event["asset_fee_quantity_decimal"], event["provided_basis_decimal"], event["movement_context_code"], effect["basis_currency"],
        effect["inventory_effect_code"], effect["fifo_effect_code"], effect["portfolio_quantity_change_decimal"],
        effect["gross_economic_amount_decimal"], effect["fifo_basis_created_decimal"], effect["net_trade_proceeds_decimal"],
        effect["gross_income_decimal"], effect["distribution_value_decimal"], effect["income_recognition_status"],
        int(effect["outgoing_lot_receipt_required"]), int(effect["transfer_lot_carry_required"]),
        int(effect["original_acquisition_evidence_required"]), 0, 0, 0, memo, origin_type, source_row_fingerprint,
        effect["effect_fingerprint"], "asset_activity_v1", command_id, committed_at_utc,
    )


def apply_schema400_asset_activity_v1(
    database_path: str | Path,
    context: Schema400AssetActivityContextV1,
    portfolio_id: str,
    events: Any,
    confirmation: Any,
    authorizer: OneUseSchema400AssetActivityAuthorizerV1,
    committed_at_utc: str,
    *,
    origin_type: str = "native",
    source_row_fingerprints: dict[str, str] | None = None,
    memos: dict[str, str | None] | None = None,
    action_type: str = "asset_activity_create_v1",
    failpoint: str | None = None,
    cutover_evidence: dict[str, Any] | None = None,
    expected_existing_result: Schema400AssetActivityResultV1 | None = None,
) -> Schema400AssetActivityResultV1:
    try:
        runtime = _context(context)
        if failpoint not in ALLOWED_FAILPOINTS or origin_type not in {"native", "legacy_conversion"} or action_type not in {"asset_activity_create_v1", "per_asset_legacy_cutover_v1"}:
            _abort("schema400_asset_activity_input_invalid")
        source_rows = {} if source_row_fingerprints is None else source_row_fingerprints
        memo_values = {} if memos is None else memos
        if (
            isinstance(confirmation, dict)
            and isinstance(authorizer, OneUseSchema400AssetActivityAuthorizerV1)
            and isinstance(confirmation.get("challenge_id"), str)
            and authorizer.is_consumed(confirmation["challenge_id"])
            and expected_existing_result is None
        ):
            _abort("schema400_asset_activity_confirmation_consumed")
        refs = _event_refs(events)
        if set(source_rows) - set(refs) or set(memo_values) - set(refs):
            _abort("schema400_asset_activity_input_invalid")
        if origin_type == "native" and source_rows:
            _abort("schema400_asset_activity_input_invalid")
        if origin_type == "legacy_conversion" and set(source_rows) != set(refs):
            _abort("schema400_asset_activity_input_invalid")
        if any(not isinstance(value, str) or _SHA.fullmatch(value) is None for value in source_rows.values()):
            _abort("schema400_asset_activity_input_invalid")
        if any(value is not None and (not isinstance(value, str) or len(value) > 4000) for value in memo_values.values()):
            _abort("schema400_asset_activity_input_invalid")
        _utc(committed_at_utc, "schema400_asset_activity_input_invalid")
        path = _regular_database(database_path)
        if isinstance(expected_existing_result, Schema400AssetActivityResultV1):
            if not isinstance(confirmation, dict):
                _abort("schema400_asset_activity_confirmation_invalid")
            recovery_preview = {
                "portfolio_ref": confirmation.get("portfolio_ref"),
                "source_fingerprint": confirmation.get("source_fingerprint"),
                "catalog_fingerprint": confirmation.get("catalog_fingerprint"),
                "source_set_fingerprint": confirmation.get("source_set_fingerprint"),
                "transaction_count": confirmation.get("transaction_count"),
                "event_count": confirmation.get("event_count"),
                "cutover_evidence": confirmation.get("cutover_evidence"),
                "preview_fingerprint": confirmation.get("preview_fingerprint"),
            }
            validated_confirmation = _confirmation(
                confirmation, recovery_preview, runtime, authorizer, committed_at_utc
            )
            command_id = _command_id(runtime, validated_confirmation["preview_fingerprint"])
            connection = _connect(path, writable=False)
            try:
                _validate_binding(connection, runtime, {TARGET_SCHEMA_VERSION})
                portfolio, accounts, assets = _catalog(connection, portfolio_id)
                if _catalog_fingerprint(portfolio, accounts, assets) != validated_confirmation["catalog_fingerprint"]:
                    _abort("schema400_asset_activity_source_stale")
                activity_preview = validate_asset_activity_v1(
                    {
                        "asset_activity_version": 1,
                        "basis_currency": portfolio["base_currency"],
                        "accounts": list(accounts.values()),
                        "assets": list(assets.values()),
                        "events": events,
                    }
                )
                transactions = [dict(row) for row in connection.execute("SELECT * FROM transaction_fact ORDER BY transaction_id")]
                receipt = connection.execute(
                    "SELECT action_type,payload_fingerprint,confirmation_fingerprint,committed_at_utc FROM ledger_command_receipt WHERE command_id=?",
                    (command_id,),
                ).fetchone()
                activity_receipt = connection.execute(
                    "SELECT action_type,preview_fingerprint,confirmation_fingerprint,event_count,plan_fingerprint,projection_fingerprint,source_asset_link_fingerprint,fifo_reconciliation_fingerprint,source_row_count,receipt_fingerprint,committed_at_utc FROM asset_activity_command_receipt WHERE command_id=?",
                    (command_id,),
                ).fetchone()
                stored_events = [
                    dict(row)
                    for row in connection.execute(
                        "SELECT event_ref,effect_fingerprint,origin_type,source_row_fingerprint,memo FROM asset_activity_event WHERE command_id=? ORDER BY event_ref",
                        (command_id,),
                    )
                ]
            finally:
                connection.close()
            effects = {item["event_ref"]: item["effect_fingerprint"] for item in activity_preview["event_effects"]}
            expected_events = [
                {
                    "event_ref": event_ref,
                    "effect_fingerprint": effects[event_ref],
                    "origin_type": origin_type,
                    "source_row_fingerprint": source_rows.get(event_ref),
                    "memo": memo_values.get(event_ref),
                }
                for event_ref in sorted(refs)
            ]
            receipt_expected = (
                action_type,
                validated_confirmation["preview_fingerprint"],
                validated_confirmation["confirmation_fingerprint"],
                committed_at_utc,
            )
            cutover = validated_confirmation["cutover_evidence"]
            expected_activity_receipt = (
                action_type,
                validated_confirmation["preview_fingerprint"],
                validated_confirmation["confirmation_fingerprint"],
                len(refs),
                None if cutover is None else cutover["plan_fingerprint"],
                None if cutover is None else cutover["projection_fingerprint"],
                None if cutover is None else cutover["source_asset_link_fingerprint"],
                None if cutover is None else cutover["fifo_reconciliation_fingerprint"],
                None if cutover is None else cutover["source_row_count"],
                None,
                committed_at_utc,
            )
            recovery_preview = dict(recovery_preview)
            expected_receipt_fingerprint = _asset_activity_receipt_fingerprint(
                command_id,
                action_type,
                recovery_preview,
                validated_confirmation["confirmation_fingerprint"],
                committed_at_utc,
            )
            expected_activity_receipt = (
                *expected_activity_receipt[:9], expected_receipt_fingerprint, expected_activity_receipt[10]
            )
            result_matches = (
                expected_existing_result.command_id == command_id
                and expected_existing_result.event_count == len(refs)
                and expected_existing_result.confirmation_fingerprint == validated_confirmation["confirmation_fingerprint"]
                and expected_existing_result.committed_at_utc == committed_at_utc
                and expected_existing_result.canonical_write is True
                and expected_existing_result.cash_posting_count == 0
            )
            if (
                len(transactions) != validated_confirmation["transaction_count"]
                or _fingerprint(transactions) != validated_confirmation["source_set_fingerprint"]
                or receipt is None
                or tuple(receipt) != receipt_expected
                or activity_receipt is None
                or tuple(activity_receipt) != expected_activity_receipt
                or stored_events != expected_events
                or not result_matches
            ):
                _abort("schema400_asset_activity_source_stale")
            authorizer.consume(
                validated_confirmation["challenge_id"],
                validated_confirmation["confirmation_fingerprint"],
            )
            return Schema400AssetActivityResultV1(
                "already_committed",
                command_id,
                len(refs),
                validated_confirmation["confirmation_fingerprint"],
                committed_at_utc,
                True,
            )
        preview = preview_schema400_asset_activity_v1(
            database_path,
            runtime,
            portfolio_id,
            events,
            cutover_evidence=cutover_evidence,
        )
        validated_confirmation = _confirmation(confirmation, preview, runtime, authorizer, committed_at_utc)
        if preview["source_fingerprint"] != _sha_file(path):
            _abort("schema400_asset_activity_source_stale")
        connection = _connect(path, writable=True)
        command_id = _command_id(runtime, preview["preview_fingerprint"])
        began = False
        try:
            connection.execute("PRAGMA legacy_alter_table=ON")
            connection.execute("BEGIN IMMEDIATE")
            began = True
            current_version = _validate_binding(connection, runtime, {SOURCE_SCHEMA_VERSION, TARGET_SCHEMA_VERSION})
            if _sha_file(path) != preview["source_fingerprint"]:
                _abort("schema400_asset_activity_source_stale")
            current_portfolio, current_accounts, current_assets = _catalog(connection, portfolio_id)
            if _catalog_fingerprint(current_portfolio, current_accounts, current_assets) != preview["catalog_fingerprint"]:
                _abort("schema400_asset_activity_source_stale")
            current_transactions = [dict(row) for row in connection.execute("SELECT * FROM transaction_fact ORDER BY transaction_id")]
            if len(current_transactions) != preview["transaction_count"] or _fingerprint(current_transactions) != preview["source_set_fingerprint"]:
                _abort("schema400_asset_activity_source_stale")
            if current_version == SOURCE_SCHEMA_VERSION:
                _apply_migration_in_transaction(connection)
                _validate_binding(connection, runtime, {TARGET_SCHEMA_VERSION})
            existing = connection.execute(
                "SELECT action_type,payload_fingerprint,confirmation_fingerprint,committed_at_utc FROM ledger_command_receipt WHERE command_id=?",
                (command_id,),
            ).fetchone()
            if existing is not None:
                expected = (action_type, preview["preview_fingerprint"], validated_confirmation["confirmation_fingerprint"], committed_at_utc)
                count = connection.execute("SELECT count(*) FROM asset_activity_event WHERE command_id=?", (command_id,)).fetchone()[0]
                if tuple(existing) == expected and count == preview["event_count"]:
                    _abort("schema400_asset_activity_confirmation_consumed")
                _abort("schema400_asset_activity_source_stale")
            authorizer.consume(validated_confirmation["challenge_id"], validated_confirmation["confirmation_fingerprint"])
            connection.execute(
                "INSERT INTO ledger_command_receipt VALUES (?, 'data_app', ?, ?, ?, ?, ?)",
                (command_id, action_type, runtime.actor_id, preview["preview_fingerprint"], validated_confirmation["confirmation_fingerprint"], committed_at_utc),
            )
            if failpoint == "after_receipt":
                _abort("synthetic_schema400_asset_activity_failpoint")
            effects = {item["event_ref"]: item for item in preview["event_effects"]}
            insert_sql = "INSERT INTO asset_activity_event VALUES (%s)" % ",".join("?" for _ in range(50))
            for event in events:
                connection.execute(
                    insert_sql,
                    _event_payload(event, effects[event["event_ref"]], portfolio_id, command_id, committed_at_utc, origin_type, source_rows.get(event["event_ref"]), memo_values.get(event["event_ref"])),
                )
            if failpoint == "after_events":
                _abort("synthetic_schema400_asset_activity_failpoint")
            cutover = preview["cutover_evidence"]
            connection.execute(
                "INSERT INTO asset_activity_command_receipt VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    command_id,
                    action_type,
                    preview["preview_fingerprint"],
                    validated_confirmation["confirmation_fingerprint"],
                    preview["event_count"],
                    None if cutover is None else cutover["plan_fingerprint"],
                    None if cutover is None else cutover["projection_fingerprint"],
                    None if cutover is None else cutover["source_asset_link_fingerprint"],
                    None if cutover is None else cutover["fifo_reconciliation_fingerprint"],
                    None if cutover is None else cutover["source_row_count"],
                    _asset_activity_receipt_fingerprint(
                        command_id,
                        action_type,
                        preview,
                        validated_confirmation["confirmation_fingerprint"],
                        committed_at_utc,
                    ),
                    committed_at_utc,
                ),
            )
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
                _abort("schema400_asset_activity_integrity_invalid")
            if failpoint == "before_commit":
                _abort("synthetic_schema400_asset_activity_failpoint")
            connection.execute("COMMIT")
            began = False
            return Schema400AssetActivityResultV1("committed", command_id, preview["event_count"], validated_confirmation["confirmation_fingerprint"], committed_at_utc, True)
        except Schema400AssetActivityCompatV1Error:
            if began:
                connection.execute("ROLLBACK")
            raise
        except sqlite3.Error:
            if began:
                connection.execute("ROLLBACK")
            _abort("schema400_asset_activity_transaction_failed")
        finally:
            try:
                if not connection.in_transaction:
                    connection.execute("PRAGMA legacy_alter_table=OFF")
            except sqlite3.Error:
                pass
            connection.close()
    except Schema400AssetActivityCompatV1Error:
        raise
    except Exception:
        raise Schema400AssetActivityCompatV1Error("schema400_asset_activity_boundary_failed") from None



def recompute_per_asset_plan_schema400_cutover_v1(
    projection: Any,
    review: Any,
    expected_plan_fingerprint: str,
) -> dict[str, Any]:
    """Recompute a Planner result immediately before canonical Preview/Apply."""

    if (
        not isinstance(expected_plan_fingerprint, str)
        or _SHA.fullmatch(expected_plan_fingerprint) is None
    ):
        _abort("schema400_asset_activity_plan_invalid")
    try:
        plan = plan_legacy_per_asset_trade_v1(projection, review)
    except LegacyPerAssetTradePlannerV1Error:
        _abort("schema400_asset_activity_plan_invalid")
    if (
        not isinstance(projection, dict)
        or plan.get("projection_fingerprint") != projection.get("projection_fingerprint")
    ):
        _abort("schema400_asset_activity_source_stale")
    if plan.get("plan_fingerprint") != expected_plan_fingerprint:
        _abort("schema400_asset_activity_source_stale")
    return plan


def preview_recomputed_per_asset_schema400_cutover_v1(
    database_path: str | Path,
    context: Schema400AssetActivityContextV1,
    portfolio_id: str,
    projection: Any,
    review: Any,
    expected_plan_fingerprint: str,
) -> dict[str, Any]:
    plan = recompute_per_asset_plan_schema400_cutover_v1(
        projection, review, expected_plan_fingerprint
    )
    return preview_per_asset_plan_schema400_cutover_v1(
        database_path, context, portfolio_id, plan
    )


def apply_recomputed_per_asset_schema400_cutover_v1(
    database_path: str | Path,
    context: Schema400AssetActivityContextV1,
    portfolio_id: str,
    projection: Any,
    review: Any,
    expected_plan_fingerprint: str,
    confirmation: Any,
    authorizer: OneUseSchema400AssetActivityAuthorizerV1,
    committed_at_utc: str,
    *,
    failpoint: str | None = None,
    expected_existing_result: Schema400AssetActivityResultV1 | None = None,
) -> Schema400AssetActivityResultV1:
    plan = recompute_per_asset_plan_schema400_cutover_v1(
        projection, review, expected_plan_fingerprint
    )
    return apply_per_asset_plan_schema400_cutover_v1(
        database_path, context, portfolio_id, plan, confirmation, authorizer,
        committed_at_utc, failpoint=failpoint,
        expected_existing_result=expected_existing_result,
    )


def preview_per_asset_plan_schema400_cutover_v1(
    database_path: str | Path,
    context: Schema400AssetActivityContextV1,
    portfolio_id: str,
    plan: Any,
) -> dict[str, Any]:
    """Create the canonical Preview from one complete server-owned Planner result."""

    runtime = _context(context)
    path = _regular_database(database_path)
    connection = _connect(path, writable=False)
    try:
        _validate_binding(connection, runtime, {SOURCE_SCHEMA_VERSION, TARGET_SCHEMA_VERSION})
        _, account_catalog, asset_catalog = _catalog(connection, portfolio_id)
    finally:
        connection.close()
    target_asset = plan.get("target_asset_ref") if isinstance(plan, dict) else None
    if target_asset not in asset_catalog:
        _abort("schema400_asset_activity_catalog_invalid")
    selected_accounts = {
        row.get("activity_event", {}).get("account_ref")
        for row in plan.get("rows", [])
        if isinstance(row, dict)
    } | {
        row.get("activity_event", {}).get("related_account_ref")
        for row in plan.get("rows", [])
        if isinstance(row, dict)
    }
    selected_accounts.discard(None)
    if not selected_accounts or not selected_accounts <= set(account_catalog):
        _abort("schema400_asset_activity_catalog_invalid")
    cutover = validate_per_asset_plan_for_schema400_cutover_v1(
        plan,
        target_asset_id=target_asset,
        selected_account_ids=frozenset(selected_accounts),
    )
    evidence = {
        key: cutover[key]
        for key in (
            "plan_fingerprint", "projection_fingerprint", "source_asset_link_fingerprint",
            "fifo_reconciliation_fingerprint", "source_row_count",
        )
    }
    preview = preview_schema400_asset_activity_v1(
        path,
        runtime,
        portfolio_id,
        cutover["events"],
        cutover_evidence=evidence,
    )
    # The current canonical catalog must reproduce every planner effect exactly.
    expected_effects = [row["activity_effect"] for row in plan["rows"]]
    if preview["event_effects"] != expected_effects:
        _abort("schema400_asset_activity_reconciliation_mismatch")
    return preview


def apply_per_asset_plan_schema400_cutover_v1(
    database_path: str | Path,
    context: Schema400AssetActivityContextV1,
    portfolio_id: str,
    plan: Any,
    confirmation: Any,
    authorizer: OneUseSchema400AssetActivityAuthorizerV1,
    committed_at_utc: str,
    *,
    failpoint: str | None = None,
    expected_existing_result: Schema400AssetActivityResultV1 | None = None,
) -> Schema400AssetActivityResultV1:
    """Atomically cut one complete per-Asset Plan into schema 401.

    The caller must recompute the Plan from its separately authorized Source and
    Review immediately before this function. This boundary deliberately accepts no
    Source path or browser-supplied identifier.
    """

    preview = preview_per_asset_plan_schema400_cutover_v1(
        database_path, context, portfolio_id, plan
    )
    cutover = validate_per_asset_plan_for_schema400_cutover_v1(
        plan,
        target_asset_id=plan["target_asset_ref"],
        selected_account_ids=frozenset(
            account_ref
            for row in plan["rows"]
            for account_ref in (
                row["activity_event"]["account_ref"],
                row["activity_event"]["related_account_ref"],
            )
            if account_ref is not None
        ),
    )
    evidence = preview["cutover_evidence"]
    return apply_schema400_asset_activity_v1(
        database_path,
        context,
        portfolio_id,
        cutover["events"],
        confirmation,
        authorizer,
        committed_at_utc,
        origin_type="legacy_conversion",
        source_row_fingerprints=cutover["source_row_fingerprints"],
        memos=cutover["memos"],
        action_type="per_asset_legacy_cutover_v1",
        failpoint=failpoint,
        cutover_evidence=evidence,
        expected_existing_result=expected_existing_result,
    )


__all__ = [
    "OneUseSchema400AssetActivityAuthorizerV1",
    "Schema400AssetActivityCompatV1Error",
    "Schema400AssetActivityContextV1",
    "Schema400AssetActivityResultV1",
    "apply_per_asset_plan_schema400_cutover_v1",
    "apply_recomputed_per_asset_schema400_cutover_v1",
    "apply_schema400_asset_activity_v1",
    "build_schema400_asset_activity_confirmation_v1",
    "migrate_schema400_asset_activity_v1",
    "preview_per_asset_plan_schema400_cutover_v1",
    "preview_recomputed_per_asset_schema400_cutover_v1",
    "recompute_per_asset_plan_schema400_cutover_v1",
    "preview_schema400_asset_activity_v1",
    "schema400_asset_activity_compat_v1_error_codes",
    "validate_per_asset_plan_for_schema400_cutover_v1",
]
