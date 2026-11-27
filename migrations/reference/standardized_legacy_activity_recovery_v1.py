"""Read-only recovery planning for standardized Legacy ActivityDraft rows.

The planner binds one exact tolerant CSV, its persisted Drafts and the original
read-only Legacy transaction files. It derives only two accepted standard rules:
non-applicable auxiliary fields and same-Asset crypto movement fees. Equal exact
source timestamps remain blocked unless the explicit owner-confirmed source-row
policy can be sealed from one unchanged source file.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from migrations.reference.desktop_activity_draft_v1 import (
    list_desktop_activity_drafts_v1,
    read_desktop_activity_draft_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    NATIVE_EVENT_KEYS,
    DesktopProductAssetActivityContextV1,
    _context,
    _context_fingerprint,
    apply_desktop_native_asset_activity_v1,
    preview_desktop_native_asset_activity_v1,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.redundant_asset_activity_csv_v1 import (
    LEGACY_TRANSACTION_HEADERS,
    _directory,
    _directory_identity,
    _fingerprint,
    _parse_table,
    _read_file,
    _sha,
    _source_ref,
    _standard_crypto_asset_fee,
    _transaction_files,
    inspect_redundant_activity_csv_v1,
)
from workers.reference.semantic_realized_fifo_v2 import (
    SemanticRealizedFifoV2Error,
    build_owner_confirmed_source_row_order_evidence_v1,
)

CONTRACT_VERSION = 1
OWNER_POLICY = "JA_SOURCE_ROW_ORDER_IST_VERBINDLICHE_FIFO_REIHENFOLGE"
FAILURE_CODES = frozenset({
    "standardized_legacy_activity_recovery_boundary_invalid",
    "standardized_legacy_activity_recovery_context_invalid",
    "standardized_legacy_activity_recovery_draft_invalid",
    "standardized_legacy_activity_recovery_input_invalid",
    "standardized_legacy_activity_recovery_source_changed",
    "standardized_legacy_activity_recovery_source_invalid",
})
_ORIGINAL_NOT_APPLICABLE = frozenset({
    "buy", "sell", "dividend", "stock_dividend", "reward", "withdrawal", "transfer",
})
_MOVEMENT_NOT_APPLICABLE = frozenset({
    "buy", "sell", "dividend", "stock_dividend", "reward", "transfer",
})


class StandardizedLegacyActivityRecoveryV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("standardized_legacy_activity_recovery_error_unregistered")
        self.code = code
        super().__init__(code)


def standardized_legacy_activity_recovery_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise StandardizedLegacyActivityRecoveryV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        _abort("standardized_legacy_activity_recovery_input_invalid")


def _seal(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _legacy_rows(transaction_root_path: str | Path) -> tuple[dict[str, dict[str, Any]], str]:
    try:
        root, root_identity = _directory(transaction_root_path)
        paths, directory_identities = _transaction_files(root)
    except Exception:
        _abort("standardized_legacy_activity_recovery_source_invalid")
    result: dict[str, dict[str, Any]] = {}
    file_identities: list[tuple[Path, tuple[int, int, int, int, int]]] = []
    source_set: list[dict[str, Any]] = []
    try:
        for path in paths:
            _, content, identity = _read_file(path)
            file_identities.append((path, identity))
            _, records = _parse_table(content, LEGACY_TRANSACTION_HEADERS)
            file_fingerprint = _sha(content)
            source_set.append({
                "relative_path_fingerprint": _sha(
                    path.relative_to(root).as_posix().encode("utf-8")
                ),
                "source_file_fingerprint": file_fingerprint,
                "source_row_count": len(records),
            })
            for ordinal, values in enumerate(records, 1):
                reference = _source_ref({
                    "file": file_fingerprint, "ordinal": ordinal, "row": values,
                })
                if reference in result:
                    _abort("standardized_legacy_activity_recovery_source_invalid")
                result[reference] = {
                    "source_file_fingerprint": file_fingerprint,
                    "source_row_ordinal": ordinal,
                    "values": values,
                }
        if _directory_identity(root) != root_identity:
            _abort("standardized_legacy_activity_recovery_source_changed")
        for path, identity in file_identities:
            if _read_file(path)[2] != identity:
                _abort("standardized_legacy_activity_recovery_source_changed")
        for directory, identity in directory_identities:
            if _directory_identity(directory) != identity:
                _abort("standardized_legacy_activity_recovery_source_changed")
    except StandardizedLegacyActivityRecoveryV1Error:
        raise
    except Exception:
        _abort("standardized_legacy_activity_recovery_source_invalid")
    source_set.sort(key=lambda row: row["relative_path_fingerprint"])
    return result, _fingerprint(source_set)


def _not_applicable_patch(event: Mapping[str, Any]) -> dict[str, Any]:
    event_type = event.get("event_type")
    patch: dict[str, Any] = {}
    if event_type in _ORIGINAL_NOT_APPLICABLE:
        expected = {
            "original_acquired_time_evidence": "not_applicable",
            "original_acquired_local_date": None,
            "original_acquired_local_time": None,
            "original_acquired_time_zone": None,
            "original_acquired_at_utc": None,
        }
        for field, value in expected.items():
            if field not in event:
                patch[field] = value
            elif event[field] != value:
                _abort("standardized_legacy_activity_recovery_draft_invalid")
    if event_type in _MOVEMENT_NOT_APPLICABLE:
        if "movement_context_code" not in event:
            patch["movement_context_code"] = "not_applicable"
        elif event["movement_context_code"] != "not_applicable":
            _abort("standardized_legacy_activity_recovery_draft_invalid")
    return patch


def _exact_nonzero_decimal(value: Any) -> str:
    if not isinstance(value, str):
        _abort("standardized_legacy_activity_recovery_draft_invalid")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _abort("standardized_legacy_activity_recovery_draft_invalid")
    if not parsed.is_finite() or parsed <= 0:
        _abort("standardized_legacy_activity_recovery_draft_invalid")
    return value


def _validate_private_plan(
    value: Any, context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _abort("standardized_legacy_activity_recovery_input_invalid")
    plan = dict(value)
    fingerprint = plan.pop("plan_fingerprint", None)
    if (
        plan.get("standardized_legacy_activity_recovery_plan_version") != CONTRACT_VERSION
        or plan.get("context_fingerprint") != _context_fingerprint(context)
        or plan.get("owner_policy") != OWNER_POLICY
        or not isinstance(plan.get("operations"), list)
        or plan.get("draft_count") != len(plan["operations"])
        or fingerprint != _seal(plan)
    ):
        _abort("standardized_legacy_activity_recovery_input_invalid")
    return dict(value)


def prepare_standardized_legacy_activity_recovery_v1(
    activity_csv_path: str | Path,
    transaction_root_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    owner_policy: str,
) -> dict[str, Any]:
    """Return one private immutable plan plus a privacy-safe public summary."""
    try:
        context = _context(context_value)
    except Exception:
        _abort("standardized_legacy_activity_recovery_context_invalid")
    if owner_policy != OWNER_POLICY:
        _abort("standardized_legacy_activity_recovery_input_invalid")
    try:
        inspection = inspect_redundant_activity_csv_v1(activity_csv_path)
        legacy_by_reference, legacy_source_set_fingerprint = _legacy_rows(
            transaction_root_path
        )
        listed = list_desktop_activity_drafts_v1(data_space_path, context)
    except StandardizedLegacyActivityRecoveryV1Error:
        raise
    except Exception:
        _abort("standardized_legacy_activity_recovery_boundary_invalid")
    trusted_rows = inspection.get("trusted_rows")
    source_fingerprint = inspection.get("source_fingerprint")
    draft_refs = listed.get("trusted_list", {}).get("draft_refs")
    if (
        not isinstance(trusted_rows, list)
        or not isinstance(source_fingerprint, str)
        or not isinstance(draft_refs, list)
    ):
        _abort("standardized_legacy_activity_recovery_source_invalid")
    rows_by_ordinal = {index: row for index, row in enumerate(trusted_rows, 1)}
    activity_ordinals = {
        index for index, row in rows_by_ordinal.items() if row.get("row_kind") == "activity"
    }
    operations: list[dict[str, Any]] = []
    projected_events: list[dict[str, Any]] = []
    projected_source_rows: dict[str, dict[str, Any]] = {}
    seen_ordinals: set[int] = set()
    fee_resolution_count = 0
    defaulted_draft_count = 0
    for draft_ref in draft_refs:
        try:
            draft = read_desktop_activity_draft_v1(
                data_space_path, context, draft_ref
            )["trusted_draft"]
        except Exception:
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        binding = draft.get("source_binding")
        auxiliary = draft.get("source_auxiliary")
        event = draft.get("event")
        if (
            draft.get("origin_type") != "tolerant_csv"
            or draft.get("action_type") != "create"
            or draft.get("draft_state") in {"applying", "committed"}
            or not isinstance(binding, Mapping)
            or not isinstance(auxiliary, Mapping)
            or not isinstance(event, Mapping)
            or binding.get("source_fingerprint") != source_fingerprint
        ):
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        ordinal = binding.get("source_row_ordinal")
        row = rows_by_ordinal.get(ordinal)
        if (
            isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or ordinal in seen_ordinals
            or ordinal not in activity_ordinals
            or not isinstance(row, Mapping)
            or row.get("row_key") != binding.get("source_row_key")
            or row.get("source_reference") not in legacy_by_reference
            or row.get("event_type") != event.get("event_type")
        ):
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        seen_ordinals.add(ordinal)
        legacy = legacy_by_reference[row["source_reference"]]
        patch = _not_applicable_patch(event)
        if patch:
            defaulted_draft_count += 1
        projected = {**event, **patch}
        fee_resolution = None
        resolution = auxiliary.get("unclassified_fee_resolution")
        source_fee = auxiliary.get("unclassified_fee_decimal")
        if resolution == "unresolved":
            fee = _exact_nonzero_decimal(source_fee)
            if (
                row.get("unclassified_fee_decimal") != fee
                or not _standard_crypto_asset_fee(
                    legacy["values"].get("Depot", ""), event.get("event_type")
                )
            ):
                _abort("standardized_legacy_activity_recovery_draft_invalid")
            projected["monetary_fee_decimal"] = None
            projected["asset_fee_quantity_decimal"] = fee
            fee_resolution = "asset_fee_quantity"
            fee_resolution_count += 1
        elif resolution == "asset_fee_quantity":
            fee = _exact_nonzero_decimal(source_fee)
            if projected.get("asset_fee_quantity_decimal") != fee or projected.get("monetary_fee_decimal") is not None:
                _abort("standardized_legacy_activity_recovery_draft_invalid")
        elif resolution not in {"not_present", "monetary_fee", "zero_no_fee"}:
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        if set(projected) != NATIVE_EVENT_KEYS:
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        event_ref = projected["event_ref"]
        projected_events.append(projected)
        projected_source_rows[event_ref] = {
            "source_file_fingerprint": legacy["source_file_fingerprint"],
            "source_row_ordinal": legacy["source_row_ordinal"],
        }
        operations.append({
            "draft_ref": draft_ref,
            "expected_revision": draft["revision"],
            "draft_fingerprint": draft["draft_fingerprint"],
            "source_row_ordinal": ordinal,
            "event_patch": patch,
            "fee_resolution": fee_resolution,
            "fifo_order_evidence": None,
        })
    if seen_ordinals != activity_ordinals or len(operations) != len(activity_ordinals):
        _abort("standardized_legacy_activity_recovery_draft_invalid")
    ordered = sorted(
        zip(operations, projected_events), key=lambda item: item[0]["source_row_ordinal"]
    )
    operations = [item[0] for item in ordered]
    projected_events = [item[1] for item in ordered]
    try:
        order_evidence = build_owner_confirmed_source_row_order_evidence_v1(
            projected_events, projected_source_rows
        )
    except SemanticRealizedFifoV2Error:
        _abort("standardized_legacy_activity_recovery_draft_invalid")
    evidence_by_ref = {row["event_ref"]: row for row in order_evidence}
    for operation, event in zip(operations, projected_events):
        operation["fifo_order_evidence"] = evidence_by_ref.get(event["event_ref"])
    sequenced = sorted(
        zip(operations, projected_events),
        key=lambda item: (
            item[1]["local_date"], item[1]["effective_at_utc"] is not None,
            item[1]["effective_at_utc"] or "",
            0 if item[0]["fifo_order_evidence"] is not None else 1,
            0 if item[0]["fifo_order_evidence"] is None
            else item[0]["fifo_order_evidence"]["source_row_ordinal"],
            item[1]["event_ref"],
        ),
    )
    operations = [item[0] for item in sequenced]
    projected_events = [item[1] for item in sequenced]
    collision_groups = {
        row["owner_decision_fingerprint"] for row in order_evidence
    }
    plan_body = {
        "standardized_legacy_activity_recovery_plan_version": CONTRACT_VERSION,
        "context_fingerprint": _context_fingerprint(context),
        "owner_policy": OWNER_POLICY,
        "activity_csv_fingerprint": source_fingerprint,
        "legacy_source_set_fingerprint": legacy_source_set_fingerprint,
        "draft_count": len(operations),
        "operations": operations,
    }
    private_plan = {**plan_body, "plan_fingerprint": _seal(plan_body)}
    public_summary = {
        "standardized_legacy_activity_recovery_public_version": CONTRACT_VERSION,
        "status": "ready_for_separate_draft_recovery",
        "draft_count": len(operations),
        "not_applicable_draft_count": defaulted_draft_count,
        "asset_fee_resolution_count": fee_resolution_count,
        "fifo_order_evidence_row_count": len(order_evidence),
        "fifo_order_evidence_group_count": len(collision_groups),
        "unresolved_rule_count": 0,
        "draft_write": False,
        "canonical_write": False,
        "cash_posting_count": 0,
        "provider_access": False,
        "network_access": False,
        "path_exposed": False,
        "raw_value_exposed": False,
        "internal_id_exposed": False,
        "fingerprint_exposed": False,
    }
    return {"public_summary": public_summary, "private_plan": private_plan}


def simulate_standardized_legacy_activity_recovery_v1(
    private_plan_value: Mapping[str, Any],
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    """Run the complete planned sequence in an automatically removed Product sandbox."""
    try:
        context = _context(context_value)
    except Exception:
        _abort("standardized_legacy_activity_recovery_context_invalid")
    plan = _validate_private_plan(private_plan_value, context)
    canonical = Path(canonical_path)
    if not canonical.is_absolute() or canonical.is_symlink() or not canonical.is_file():
        _abort("standardized_legacy_activity_recovery_boundary_invalid")
    canonical_before = hashlib.sha256(canonical.read_bytes()).hexdigest()
    projected: list[tuple[dict[str, Any], dict[str, Any] | None, str]] = []
    for operation in plan["operations"]:
        if not isinstance(operation, Mapping):
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        try:
            draft = read_desktop_activity_draft_v1(
                data_space_path, context, operation["draft_ref"]
            )["trusted_draft"]
        except Exception:
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        if (
            draft.get("revision") != operation.get("expected_revision")
            or draft.get("draft_fingerprint") != operation.get("draft_fingerprint")
            or not isinstance(operation.get("event_patch"), Mapping)
        ):
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        event = {**draft["event"], **operation["event_patch"]}
        if operation.get("fee_resolution") == "asset_fee_quantity":
            fee = _exact_nonzero_decimal(
                draft["source_auxiliary"].get("unclassified_fee_decimal")
            )
            event["monetary_fee_decimal"] = None
            event["asset_fee_quantity_decimal"] = fee
        elif operation.get("fee_resolution") is not None:
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        if set(event) != NATIVE_EVENT_KEYS:
            _abort("standardized_legacy_activity_recovery_draft_invalid")
        projected.append((event, operation.get("fifo_order_evidence"), draft["portfolio_id"]))
    try:
        with tempfile.TemporaryDirectory(prefix="portelyra-standard-recovery-simulation-") as temporary:
            sandbox = Path(temporary)
            os.chmod(sandbox, 0o700)
            sandbox_data_space = sandbox / "data-space"
            sandbox_data_space.mkdir(mode=0o700)
            sandbox_canonical = sandbox_data_space / "canonical.sqlite"
            shutil.copyfile(canonical, sandbox_canonical)
            os.chmod(sandbox_canonical, 0o600)
            committed_base = datetime(2090, 1, 1, tzinfo=timezone.utc)
            for index, (event, evidence, portfolio_id) in enumerate(projected):
                preview = preview_desktop_native_asset_activity_v1(
                    sandbox_canonical, sandbox_data_space, context, portfolio_id, [event],
                    fifo_order_evidence_value=evidence,
                )
                committed = (committed_base + timedelta(seconds=index)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                result = apply_desktop_native_asset_activity_v1(
                    sandbox_canonical, sandbox_data_space, context, portfolio_id, [event],
                    preview["preview_fingerprint"], committed,
                    fifo_order_evidence_value=evidence,
                )
                if result.status != "committed":
                    _abort("standardized_legacy_activity_recovery_draft_invalid")
            binding = read_desktop_product_asset_activity_binding_v1(
                sandbox_data_space, context
            )
            if binding.get("asset_activity_event_count") != len(projected):
                _abort("standardized_legacy_activity_recovery_draft_invalid")
    except StandardizedLegacyActivityRecoveryV1Error:
        raise
    except Exception:
        _abort("standardized_legacy_activity_recovery_draft_invalid")
    if hashlib.sha256(canonical.read_bytes()).hexdigest() != canonical_before:
        _abort("standardized_legacy_activity_recovery_source_changed")
    return {
        "standardized_legacy_activity_recovery_simulation_version": CONTRACT_VERSION,
        "status": "complete_sequence_ready",
        "simulated_event_count": len(projected),
        "blocked_event_count": 0,
        "source_timestamp_changed_count": 0,
        "draft_write": False,
        "canonical_write": False,
        "cash_posting_count": 0,
        "provider_access": False,
        "network_access": False,
        "sandbox_retained": False,
        "path_exposed": False,
        "raw_value_exposed": False,
        "internal_id_exposed": False,
        "fingerprint_exposed": False,
    }


__all__ = [
    "OWNER_POLICY",
    "StandardizedLegacyActivityRecoveryV1Error",
    "prepare_standardized_legacy_activity_recovery_v1",
    "simulate_standardized_legacy_activity_recovery_v1",
    "standardized_legacy_activity_recovery_v1_error_codes",
]
