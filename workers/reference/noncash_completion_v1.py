"""Pure Non-Cash completion proof without external data access."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


class NoncashCompletionV1Error(RuntimeError):
    CODES = {
        "noncash_completion_boundary_failed",
        "noncash_completion_closure_receipt_invalid",
        "noncash_completion_dimension_invalid",
        "noncash_completion_importer_registry_invalid",
        "noncash_completion_input_invalid",
    }

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("noncash_completion_error_code_unregistered")
        self.code = code
        super().__init__(code)


_SHA256 = re.compile(r"[a-f0-9]{64}")
_UTC_SECOND = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")

FACT_DIMENSIONS = (
    "legacy_lineage_closure",
    "canonical_activity",
    "fifo_v2",
)
CAPABILITY_DIMENSIONS = (
    "future_importer_protocol",
    "manual_provider_policy",
    "staged_market_review",
    "explicit_fx_policy",
    "manual_tax_policy",
    "incremental_invalidation",
)
DATA_DIMENSIONS = (
    "daily_market_history",
    "fx_history",
    "realized_tax_projection",
    "unrealized_valuation",
    "analysis_artifact",
)
DIMENSION_ORDER = FACT_DIMENSIONS + CAPABILITY_DIMENSIONS + DATA_DIMENSIONS
DIMENSION_STATUSES = {"unavailable", "partial", "stale", "complete", "blocked", "not_applicable"}

_EXPECTED_IMPORTER_SLOTS = {
    "noncash_trade_activity": ("buy", "sell"),
    "noncash_distribution_activity": ("dividend", "stock_dividend"),
    "noncash_reward_activity": ("reward",),
    "noncash_staking_reward_activity": ("reward",),
    "noncash_airdrop_activity": ("reward",),
    "noncash_movement_activity": ("deposit", "withdrawal", "transfer"),
}
_EXPECTED_IMPORTER_ENTRYPOINTS = {
    slot: f"plugins/importers/{slot}_v1/plugin.py"
    for slot in _EXPECTED_IMPORTER_SLOTS
}
_IMPORTER_FIELDS = {
    "slot_code",
    "candidate_domain",
    "event_types",
    "registry_state",
    "executable_entrypoint",
    "default_activation",
    "bound_source_read",
    "provider_access",
    "network_access",
    "canonical_write",
    "tax_write",
    "cash_write",
    "private_owner_uat_required",
    "notes",
}
_CLOSURE_FIELDS = {
    "noncash_closure_receipt_version",
    "status",
    "scope_kind",
    "closure_created_at_utc",
    "legacy_source_freeze_fingerprint",
    "legacy_delta_fingerprint",
    "terminal_disposition_policy_fingerprint",
    "terminal_disposition_fingerprint",
    "canonical_activity_fingerprint",
    "fifo_full_rebuild_fingerprint",
    "lineage_disposition_counts",
    "legacy_source_read_only",
    "source_bytes_unchanged",
    "cash_included",
    "canonical_write",
    "provider_access",
    "network_access",
    "tax_projection_started",
    "complete_portfolio_claim_authorized",
    "receipt_fingerprint",
}


def _abort(code: str) -> None:
    raise NoncashCompletionV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        _abort("noncash_completion_boundary_failed")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_utc_second(value: Any) -> bool:
    if not isinstance(value, str) or _UTC_SECOND.fullmatch(value) is None:
        return False
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") == value
    except ValueError:
        return False


def noncash_completion_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(NoncashCompletionV1Error.CODES))


def validate_noncash_closure_receipt_v1(
    receipt: Any,
    *,
    expected_terminal_disposition_policy_fingerprint: str,
) -> dict[str, Any]:
    """Validate a value-free, additive factual closure receipt in memory."""

    if (
        not isinstance(expected_terminal_disposition_policy_fingerprint, str)
        or _SHA256.fullmatch(expected_terminal_disposition_policy_fingerprint) is None
    ):
        _abort("noncash_completion_closure_receipt_invalid")
    if not isinstance(receipt, dict) or set(receipt) != _CLOSURE_FIELDS:
        _abort("noncash_completion_closure_receipt_invalid")
    body = dict(receipt)
    supplied_fingerprint = body.pop("receipt_fingerprint")
    fingerprints = (
        "legacy_source_freeze_fingerprint",
        "legacy_delta_fingerprint",
        "terminal_disposition_policy_fingerprint",
        "terminal_disposition_fingerprint",
        "canonical_activity_fingerprint",
        "fifo_full_rebuild_fingerprint",
    )
    counts = receipt.get("lineage_disposition_counts")
    expected_count_fields = {
        "all_lineages",
        "canonical_lineages",
        "terminally_excluded_lineages",
        "unresolved_lineages",
    }
    if (
        receipt.get("noncash_closure_receipt_version") != 1
        or receipt.get("status") != "completed_noncash_scope"
        or receipt.get("scope_kind") != "noncash"
        or not _is_utc_second(receipt.get("closure_created_at_utc"))
        or any(
            not isinstance(receipt.get(key), str) or _SHA256.fullmatch(receipt[key]) is None
            for key in fingerprints
        )
        or receipt.get("terminal_disposition_policy_fingerprint") != expected_terminal_disposition_policy_fingerprint
        or not isinstance(counts, dict)
        or set(counts) != expected_count_fields
        or any(
            not isinstance(counts[key], int) or isinstance(counts[key], bool) or counts[key] < 0
            for key in expected_count_fields
        )
        or counts["all_lineages"] <= 0
        or counts["unresolved_lineages"] != 0
        or counts["all_lineages"] != counts["canonical_lineages"] + counts["terminally_excluded_lineages"]
        or receipt.get("legacy_source_read_only") is not True
        or receipt.get("source_bytes_unchanged") is not True
        or receipt.get("cash_included") is not False
        or receipt.get("canonical_write") is not False
        or receipt.get("provider_access") is not False
        or receipt.get("network_access") is not False
        or receipt.get("tax_projection_started") is not False
        or receipt.get("complete_portfolio_claim_authorized") is not False
        or not isinstance(supplied_fingerprint, str)
        or _SHA256.fullmatch(supplied_fingerprint) is None
        or supplied_fingerprint != _fingerprint(body)
    ):
        _abort("noncash_completion_closure_receipt_invalid")
    return json.loads(_canonical(receipt).decode("utf-8"))


def validate_noncash_importer_registry_v1(rows: Any) -> dict[str, Any]:
    """Validate six executable, synthetic-validated, still-disabled adapter slots."""

    if (
        not isinstance(rows, Sequence)
        or isinstance(rows, (str, bytes))
        or len(rows) != len(_EXPECTED_IMPORTER_SLOTS)
    ):
        _abort("noncash_completion_importer_registry_invalid")
    observed: dict[str, tuple[str, ...]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != _IMPORTER_FIELDS:
            _abort("noncash_completion_importer_registry_invalid")
        slot = row.get("slot_code")
        raw_events = row.get("event_types")
        if not isinstance(slot, str) or slot in observed or not isinstance(raw_events, str):
            _abort("noncash_completion_importer_registry_invalid")
        events = tuple(raw_events.split("|"))
        if (
            slot not in _EXPECTED_IMPORTER_SLOTS
            or events != _EXPECTED_IMPORTER_SLOTS[slot]
            or row.get("candidate_domain") != "asset_activity"
            or row.get("registry_state") != "synthetic_validated_disabled"
            or row.get("executable_entrypoint") != _EXPECTED_IMPORTER_ENTRYPOINTS[slot]
            or row.get("default_activation") != "disabled"
            or row.get("bound_source_read") != "yes"
            or any(
                row.get(field) != "no"
                for field in (
                    "provider_access",
                    "network_access",
                    "canonical_write",
                    "tax_write",
                    "cash_write",
                )
            )
            or row.get("private_owner_uat_required") != "yes"
            or not isinstance(row.get("notes"), str)
            or not row["notes"]
        ):
            _abort("noncash_completion_importer_registry_invalid")
        observed[slot] = events
    if observed != _EXPECTED_IMPORTER_SLOTS:
        _abort("noncash_completion_importer_registry_invalid")
    count = len(observed)
    return {
        "importer_registry_version": 1,
        "status": "synthetic_validated_disabled",
        "slot_count": count,
        "reward_slot_present": True,
        "concrete_importer_count": count,
        "executable_entrypoint_count": count,
        "synthetic_validated_count": count,
        "owner_accepted_count": 0,
        "enabled_count": 0,
        "bound_source_read": True,
        "default_activation": "disabled",
        "private_owner_uat_required": True,
        "provider_access": False,
        "network_access": False,
        "canonical_write": False,
        "tax_write": False,
        "cash_write": False,
    }


def validate_noncash_importer_placeholders_v1(rows: Any) -> dict[str, Any]:
    """Compatibility alias for callers of the former placeholder validator."""

    return validate_noncash_importer_registry_v1(rows)


def _aggregate(statuses: Sequence[str], *, complete_name: str) -> str:
    if "blocked" in statuses:
        return "blocked"
    if "stale" in statuses:
        return "stale"
    if all(status == "complete" for status in statuses):
        return complete_name
    if any(status in {"complete", "partial", "not_applicable"} for status in statuses):
        return "partial"
    return "unavailable"


def _analysis_aggregate(statuses: Sequence[str]) -> str:
    if "blocked" in statuses:
        return "blocked"
    if "stale" in statuses:
        return "stale"
    applicable = [status for status in statuses if status != "not_applicable"]
    if all(status == "complete" for status in applicable):
        return "complete"
    if any(status in {"complete", "partial"} for status in applicable):
        return "partial"
    return "unavailable"


def build_noncash_completion_read_model_v1(
    dimension_statuses: Any,
    importer_registry_summary: Any,
) -> dict[str, Any]:
    """Build a browser-safe dimensional Non-Cash readiness model."""

    count = len(_EXPECTED_IMPORTER_SLOTS)
    expected_registry = {
        "importer_registry_version": 1,
        "status": "synthetic_validated_disabled",
        "slot_count": count,
        "reward_slot_present": True,
        "concrete_importer_count": count,
        "executable_entrypoint_count": count,
        "synthetic_validated_count": count,
        "owner_accepted_count": 0,
        "enabled_count": 0,
        "bound_source_read": True,
        "default_activation": "disabled",
        "private_owner_uat_required": True,
        "provider_access": False,
        "network_access": False,
        "canonical_write": False,
        "tax_write": False,
        "cash_write": False,
    }
    if (
        not isinstance(dimension_statuses, Mapping)
        or set(dimension_statuses) != set(DIMENSION_ORDER)
    ):
        _abort("noncash_completion_input_invalid")
    if (
        not isinstance(importer_registry_summary, Mapping)
        or dict(importer_registry_summary) != expected_registry
    ):
        _abort("noncash_completion_importer_registry_invalid")
    normalized: dict[str, str] = {}
    for code in DIMENSION_ORDER:
        status = dimension_statuses.get(code)
        if not isinstance(status, str) or status not in DIMENSION_STATUSES:
            _abort("noncash_completion_dimension_invalid")
        if code in FACT_DIMENSIONS + CAPABILITY_DIMENSIONS and status == "not_applicable":
            _abort("noncash_completion_dimension_invalid")
        normalized[code] = status

    fact_status = _aggregate([normalized[code] for code in FACT_DIMENSIONS], complete_name="complete")
    capability_status = _aggregate(
        [normalized[code] for code in CAPABILITY_DIMENSIONS],
        complete_name="prepared",
    )
    analysis_status = _analysis_aggregate([normalized[code] for code in DATA_DIMENSIONS])
    fact_complete = fact_status == "complete"
    capability_ready = capability_status == "prepared"
    analysis_ready = fact_complete and capability_ready and analysis_status == "complete"
    dimensions = [
        {
            "dimension_code": code,
            "status": normalized[code],
            "reason_code": f"{code}_{normalized[code]}",
        }
        for code in DIMENSION_ORDER
    ]
    return {
        "noncash_completion_version": 1,
        "status": "available",
        "scope_kind": "noncash",
        "fact_scope_status": fact_status,
        "enrichment_capability_status": capability_status,
        "analysis_data_status": analysis_status,
        "importer_preparation_status": "synthetic_validated_disabled",
        "concrete_importer_coverage_status": "implemented_owner_uat_pending",
        "dimensions": dimensions,
        "noncash_fact_scope_complete": fact_complete,
        "noncash_enrichment_capability_ready": capability_ready,
        "noncash_foundation_ready": fact_complete and capability_ready,
        "noncash_analysis_data_ready": analysis_ready,
        "future_importer_protocol_ready": normalized["future_importer_protocol"] == "complete",
        "manual_provider_maintenance_supported": (
            normalized["manual_provider_policy"] == "complete"
            and normalized["staged_market_review"] == "complete"
        ),
        "manual_tax_maintenance_supported": normalized["manual_tax_policy"] == "complete",
        "cash_included": False,
        "complete_portfolio_claim_authorized": False,
        "display_started_worker": False,
        "importer_started": False,
        "provider_access": False,
        "network_access": False,
        "canonical_write": False,
        "tax_write": False,
        "path_exposed": False,
        "context_exposed": False,
        "internal_id_exposed": False,
    }


__all__ = [
    "CAPABILITY_DIMENSIONS",
    "DATA_DIMENSIONS",
    "DIMENSION_ORDER",
    "FACT_DIMENSIONS",
    "NoncashCompletionV1Error",
    "build_noncash_completion_read_model_v1",
    "noncash_completion_v1_error_codes",
    "validate_noncash_closure_receipt_v1",
    "validate_noncash_importer_placeholders_v1",
    "validate_noncash_importer_registry_v1",
]
