#!/usr/bin/env python3
"""Trusted JSON-stdin bridge for the synthetic per-Asset planner and sandbox apply.

The browser never invokes this script or supplies paths/context/fingerprints. A local
R adapter owns all capabilities and sends exact server-side payloads through stdin.
Stdout contains one JSON value and no source values on failure.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from dataclasses import asdict
import hashlib
import json
import secrets
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations.reference.legacy_asset_companion_v1 import (  # noqa: E402
    LegacyAssetCompanionV1Error,
    read_legacy_asset_companion_v1,
    review_legacy_asset_companion_v1,
)
from migrations.reference.legacy_per_asset_trade_planner_v1 import (  # noqa: E402
    LegacyPerAssetTradePlannerV1Error,
    plan_legacy_per_asset_trade_v1,
    read_legacy_per_asset_trade_v1,
)
from migrations.reference.desktop_cash_coverage_v1 import (  # noqa: E402
    DesktopCashCoverageV1Error,
    apply_desktop_cash_coverage_command_v1,
    apply_desktop_cash_coverage_recovery_v1,
    build_desktop_cash_coverage_confirmation_v1,
    build_desktop_cash_coverage_recovery_confirmation_v1,
    preview_desktop_cash_coverage_command_v1,
    preview_desktop_cash_coverage_recovery_v1,
    preview_desktop_reviewed_cash_coverage_candidate_v1,
    read_desktop_cash_coverage_catalog_v1,
    read_desktop_cash_coverage_recovery_candidates_v1,
    read_desktop_cash_coverage_revision_candidates_v1,
    read_desktop_cash_coverage_view_v1,
)
from migrations.reference.cash_statement_import_v1 import CashStatementImportV1Error  # noqa: E402
from migrations.reference.securities_statement_import_v1 import SecuritiesStatementImportV1Error  # noqa: E402
from migrations.reference.statement_reader_checks_v1 import StatementReaderCheckV1Error  # noqa: E402
from migrations.reference.generic_statement_import_v1 import GenericStatementImportV1Error  # noqa: E402
from migrations.reference.asset_activity_csv_import_v1 import (  # noqa: E402
    AssetActivityCsvImportV1Error,
    apply_asset_activity_csv_import_v1,
    build_asset_activity_csv_confirmation_v1,
    export_asset_activity_csv_v1,
    inspect_asset_activity_csv_v1,
    list_resumable_asset_activity_csv_imports_v1,
    preview_asset_activity_csv_import_v1,
    resume_asset_activity_csv_import_v1,
)
from migrations.reference.desktop_asset_activity_correction_v1 import (  # noqa: E402
    DesktopAssetActivityCorrectionV1Error,
    apply_desktop_asset_activity_correction_v1,
    build_desktop_asset_activity_correction_confirmation_v1,
    preview_desktop_asset_activity_correction_v1,
    read_desktop_asset_activity_correction_candidates_v1,
    read_desktop_asset_activity_correction_history_v1,
)
from migrations.reference.redundant_asset_activity_csv_v1 import (  # noqa: E402
    RedundantAssetActivityCsvV1Error,
    inspect_redundant_activity_csv_v1,
)
from migrations.reference.desktop_activity_block_reason_v1 import explain_desktop_activity_draft_block_v1  # noqa: E402
from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, carry_activity_reference_v1, carry_activity_references_from_voided_v1
from migrations.reference.desktop_activity_draft_v1 import (  # noqa: E402
    DesktopActivityDraftV1Error,
    apply_desktop_activity_draft_mixed_source_retirement_v1,
    apply_desktop_activity_draft_source_supersession_v1,
    build_desktop_activity_draft_mixed_source_retirement_confirmation_v1,
    build_desktop_activity_draft_source_supersession_confirmation_v1,
    preview_desktop_activity_draft_mixed_source_retirement_v1,
    preview_desktop_activity_draft_source_supersession_v1,
    apply_desktop_activity_draft_v1,
    bind_desktop_activity_draft_fifo_order_evidence_v1,
    bind_desktop_activity_draft_fifo_order_group_v1,
    build_desktop_activity_draft_confirmation_v1,
    build_desktop_activity_draft_recovery_confirmation_v2,
    create_desktop_activity_draft_v1,
    create_or_reuse_tolerant_csv_activity_draft_v1,
    list_desktop_activity_drafts_v1,
    list_desktop_activity_mapping_profiles_v1,
    read_desktop_activity_draft_v1,
    read_desktop_activity_mapping_profile_v1,
    resolve_desktop_activity_draft_unclassified_fee_v1,
    resume_desktop_activity_draft_v1,
    save_desktop_activity_mapping_profile_v1,
    update_desktop_activity_draft_v1,
    shift_desktop_activity_draft_past_booked_second_v1,
    validate_desktop_activity_draft_v1,
)
from migrations.reference.standardized_legacy_activity_recovery_v1 import (  # noqa: E402
    StandardizedLegacyActivityRecoveryV1Error,
    prepare_standardized_legacy_activity_recovery_v1,
    simulate_standardized_legacy_activity_recovery_v1,
)
from migrations.reference.desktop_asset_quantity_scale_revision_v1 import (  # noqa: E402
    DesktopAssetQuantityScaleRevisionV1Error,
    begin_desktop_asset_quantity_scale_revision_v1,
    build_desktop_asset_quantity_scale_confirmation_v1,
    finalize_desktop_asset_quantity_scale_revision_v1,
    list_pending_desktop_asset_quantity_scale_revisions_v1,
    preview_desktop_asset_quantity_scale_revision_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (  # noqa: E402
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    apply_desktop_asset_activity_generation_retention_v1,
    apply_desktop_asset_activity_republication_v1,
    read_desktop_asset_activity_generation_retention_plan_v1,
    apply_desktop_native_asset_activity_v1,
    apply_desktop_product_per_asset_cutover_v1,
    preview_desktop_native_asset_activity_v1,
    preview_desktop_product_per_asset_cutover_v1,
    read_desktop_product_per_asset_catalog_v1,
    resolve_desktop_product_per_asset_scope_v1,
    read_desktop_product_asset_activity_binding_v1,
    resolve_desktop_asset_activity_time_v1,
)
from migrations.reference.desktop_product_asset_activity_view_v5 import (  # noqa: E402
    read_desktop_product_asset_activity_view_v5,
)
from workers.reference.portfolio_operational_readiness_v1 import (  # noqa: E402
    PortfolioOperationalReadinessV1Error,
    read_portfolio_operational_readiness_v1,
)
from workers.reference.asset_activity_realized_state_v2 import (  # noqa: E402
    AssetActivityRealizedStateV2Error,
    materialize_asset_activity_realized_state_v2,
    read_asset_activity_realized_state_v2,
    verify_asset_activity_realized_state_full_rebuild_v2,
)
from migrations.reference.per_asset_sandbox_apply_v1 import (  # noqa: E402
    OneUsePerAssetSandboxAuthorizerV1,
    PerAssetSandboxApplyV1Error,
    PerAssetSandboxContextV1,
    apply_per_asset_plan_to_sandbox_v1,
    build_per_asset_sandbox_confirmation_v1,
    new_per_asset_sandbox_target_capability_v1,
)


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")))


def payload() -> dict[str, Any]:
    value = json.load(sys.stdin)
    if not isinstance(value, dict):
        raise ValueError
    if isinstance(value.get("data_space_path"), str):   # installierte Leser-Plugins dieses Datenraums mitladen (rc.381, #486)
        from migrations.reference.statement_reader_plugins_v1 import use_data_space_plugins_v1
        use_data_space_plugins_v1(value["data_space_path"])
    return value


def context(value: dict[str, Any]) -> PerAssetSandboxContextV1:
    expected = {"tenant_ref", "user_ref", "data_space_ref", "actor_ref", "role"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError
    return PerAssetSandboxContextV1(**value)


def product_context(value: dict[str, Any]) -> DesktopProductAssetActivityContextV1:
    expected = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError
    return DesktopProductAssetActivityContextV1(**value)


SYNTHETIC_FIXTURE_ROOT = ROOT / "fixtures" / "product" / "legacy-per-asset-review-v1"
SYNTHETIC_TRADE_SOURCE = SYNTHETIC_FIXTURE_ROOT / "invented_asset_trades.csv"
SYNTHETIC_COMPANION_SOURCE = SYNTHETIC_FIXTURE_ROOT / "invented_assets.csv"
SYNTHETIC_ASSET_ID = "SYN_ASSET_ALPHA"


def synthetic_sources() -> tuple[dict[str, Any], dict[str, Any]]:
    projection = read_legacy_per_asset_trade_v1(SYNTHETIC_TRADE_SOURCE)
    companion = read_legacy_asset_companion_v1(
        SYNTHETIC_COMPANION_SOURCE, SYNTHETIC_ASSET_ID
    )
    return projection, companion


def open_command(value: dict[str, Any]) -> dict[str, Any]:
    if value:
        raise ValueError
    projection, companion_projection = synthetic_sources()
    return {"status": "opened", "projection": projection, "companion_projection": companion_projection}


def plan_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"projection", "review", "companion_projection", "companion_review"}
    if set(value) != expected:
        raise ValueError
    expected_projection, expected_companion = synthetic_sources()
    if value["projection"] != expected_projection:
        raise ValueError
    if value["companion_projection"] is not None and value["companion_projection"] != expected_companion:
        raise ValueError
    review = dict(value["review"])
    companion = None
    if value["companion_projection"] is not None:
        companion = review_legacy_asset_companion_v1(
            expected_companion, value["companion_review"]
        )
    review["companion_review"] = companion
    plan = plan_legacy_per_asset_trade_v1(value["projection"], review)
    return {"status": "planned", "plan": plan, "review": review}


def apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "projection", "review", "expected_plan_fingerprint", "context", "target_root",
        "bundle_name", "challenge_id", "issued_at_utc", "confirmed_at_utc",
        "expires_at_utc", "applied_at_utc",
    }
    if set(value) != expected:
        raise ValueError
    expected_projection, _ = synthetic_sources()
    if value["projection"] != expected_projection:
        raise ValueError
    runtime = context(value["context"])
    plan = plan_legacy_per_asset_trade_v1(expected_projection, value["review"])
    confirmation = build_per_asset_sandbox_confirmation_v1(
        plan, runtime, value["challenge_id"], value["issued_at_utc"],
        value["confirmed_at_utc"], value["expires_at_utc"],
    )
    authorizer = OneUsePerAssetSandboxAuthorizerV1()
    authorizer.register(confirmation)
    capability = new_per_asset_sandbox_target_capability_v1(
        Path(value["target_root"]), value["bundle_name"], runtime
    )
    result = apply_per_asset_plan_to_sandbox_v1(
        expected_projection, value["review"], value["expected_plan_fingerprint"],
        runtime, confirmation, authorizer, capability, value["applied_at_utc"],
    )
    return {"status": "applied", "result": asdict(result)}


def product_binding_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path"}
    if set(value) != expected:
        raise ValueError
    runtime = product_context(value["context"])
    binding = read_desktop_product_asset_activity_binding_v1(
        Path(value["data_space_path"]), runtime
    )
    return {"status": "product_binding_read", "binding": binding}


def product_republish_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "committed_at_utc"}
    if set(value) != expected:
        raise ValueError
    runtime = product_context(value["context"])
    # Eine unterbrochene Skalenanpassung hat die Stammdaten schon geschrieben und
    # wartet auf ihre eigene Generation samt Quittung. Eine Neuveroeffentlichung
    # davor naehme ihr die Vorgaengergeneration, auf die ihr Plan sich bezieht.
    pending = list_pending_desktop_asset_quantity_scale_revisions_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]), runtime
    )
    if pending["candidates"]:
        raise DesktopAssetQuantityScaleRevisionV1Error("asset_quantity_scale_attempt_conflict")
    result = apply_desktop_asset_activity_republication_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]), runtime,
        value["committed_at_utc"],
    )
    return {"status": "product_republished", "result": result}


def product_activity_view_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path"}
    if set(value) != expected:
        raise ValueError
    runtime = product_context(value["context"])
    view = read_desktop_product_asset_activity_view_v5(
        Path(value["canonical_path"]), Path(value["data_space_path"]), runtime
    )
    return {"status": "product_activity_view_read", "view": view}


def product_catalog_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path"}
    if set(value) != expected:
        raise ValueError
    runtime = product_context(value["context"])
    catalog = read_desktop_product_per_asset_catalog_v1(Path(value["canonical_path"]), runtime)
    return {"status": "product_catalog_read", "catalog": catalog}


def product_scope(value: dict[str, Any]) -> tuple[DesktopProductAssetActivityContextV1, dict[str, Any]]:
    runtime = product_context(value["context"])
    scope = resolve_desktop_product_per_asset_scope_v1(
        Path(value["canonical_path"]), runtime,
        value["target_asset_id"], value["selected_account_ids"],
    )
    return runtime, scope


def product_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "projection", "review", "expected_plan_fingerprint", "context",
        "canonical_path", "data_space_path", "target_asset_id", "selected_account_ids",
    }
    if set(value) != expected:
        raise ValueError
    runtime, scope = product_scope(value)
    if value["review"].get("target_asset", {}).get("asset_ref") != scope["target_asset_id"]:
        raise ValueError
    preview = preview_desktop_product_per_asset_cutover_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]), runtime,
        scope["portfolio_id"], value["projection"], value["review"],
        value["expected_plan_fingerprint"],
    )
    return {"status": "product_previewed", "preview": preview}


def native_activity_time_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"local_date", "local_time", "time_zone"}
    if set(value) != expected:
        raise ValueError
    resolved = resolve_desktop_asset_activity_time_v1(
        value["local_date"], value["local_time"], value["time_zone"]
    )
    return {"status": "native_activity_time_resolved", "resolved": resolved}


def native_activity_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "context", "canonical_path", "data_space_path", "portfolio_id", "events",
    }
    if set(value) != expected:
        raise ValueError
    preview = preview_desktop_native_asset_activity_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["portfolio_id"], value["events"],
    )
    return {"status": "native_activity_previewed", "preview": preview}


def native_activity_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "context", "canonical_path", "data_space_path", "portfolio_id", "events",
        "expected_preview_fingerprint", "committed_at_utc",
    }
    if set(value) != expected:
        raise ValueError
    result = apply_desktop_native_asset_activity_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["portfolio_id"], value["events"],
        value["expected_preview_fingerprint"], value["committed_at_utc"],
    )
    output = asdict(result)
    output["semantic_contracts"] = list(output["semantic_contracts"])
    return {"status": "native_activity_applied", "result": output}


def redundant_activity_inspect_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"source_path"}: raise ValueError
    result = inspect_redundant_activity_csv_v1(Path(value["source_path"]))
    return {"status": "redundant_activity_inspected", "inspection": result}


def activity_draft_create_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "portfolio_id", "origin_type", "action_type", "event_fields", "created_at_utc", "predecessor_event_ref"}
    if set(value) != expected: raise ValueError
    event_fields = value["event_fields"]
    if value["action_type"] == "void" and event_fields == []:
        event_fields = {}
    result = create_desktop_activity_draft_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
        value["portfolio_id"], value["origin_type"], value["action_type"],
        event_fields, value["created_at_utc"],
        predecessor_event_ref=value["predecessor_event_ref"],
    )
    return {"status": "activity_draft_created", "draft": result}


def activity_draft_create_or_reuse_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "portfolio_id", "event_fields", "source_binding", "source_auxiliary", "created_at_utc"}
    if set(value) != expected: raise ValueError
    result = create_or_reuse_tolerant_csv_activity_draft_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
        value["portfolio_id"], value["event_fields"], value["source_binding"],
        value["source_auxiliary"], value["created_at_utc"],
    )
    return {"status": "activity_draft_created_or_reused", "draft": result,
            "provenance_intent_status": reward_provenance_intent(value, result)}


def reward_provenance_intent(value: dict[str, Any], result: Any) -> str:
    """Herkunft je Buchung (rc.378): Ein Reward-Entwurf haelt den Leser fest, der den Export gerade gelesen hat (Absicht); beim Buchen
    uebernimmt der Abgleich sie. So traegt auch ein Entwurf, der erst nach einem Rollout gebucht wird, den Leser seiner Vorschau."""
    from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, record_reader_provenance_intents_v1
    from migrations.reference.statement_reader_plugins_v1 import StatementReaderBlocked, reader_identity_v1, reward_reader_ids_v1
    evidence = (value.get("source_auxiliary") or {}).get("valuation_evidence") if isinstance(value.get("source_auxiliary"), dict) else None
    adapter_id = evidence.get("adapter_id") if isinstance(evidence, dict) else None
    draft = result.get("trusted_draft") if isinstance(result, dict) else None
    event_ref = (draft or {}).get("event", {}).get("event_ref") if isinstance(draft, dict) else None
    if adapter_id not in reward_reader_ids_v1() or not isinstance(event_ref, str):
        return "not_applicable"
    try:
        identity = reader_identity_v1(adapter_id, "reward")
        record_reader_provenance_intents_v1(Path(value["data_space_path"]), product_context(value["context"]),
                                            [{"booking_kind": "asset_event", "booking_key": event_ref, "readers": [identity]}], value["created_at_utc"])
    except (AssetActivityReferenceV1Error, StatementReaderBlocked) as error:
        return "failed:" + error.code
    return "recorded"


def activity_draft_shift_second_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "draft_ref", "expected_revision", "updated_at_utc"}
    if set(value) != expected: raise ValueError
    result = shift_desktop_activity_draft_past_booked_second_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
        value["draft_ref"], value["expected_revision"], value["updated_at_utc"],
    )
    return {"status": "activity_draft_shift_checked", "draft": {"public_draft": result["public_draft"], "trusted_draft": result["trusted_draft"]},
            "shift_status": result["status"], "shift_seconds": result["shift_seconds"]}


def activity_draft_update_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "draft_ref", "expected_revision", "event_patch", "remove_fields", "updated_at_utc"}
    if set(value) != expected: raise ValueError
    event_patch = value["event_patch"]
    if event_patch == []:
        event_patch = {}
    if not isinstance(event_patch, dict):
        raise ValueError
    result = update_desktop_activity_draft_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
        value["draft_ref"], value["expected_revision"], event_patch,
        value["remove_fields"], value["updated_at_utc"],
    )
    return {"status": "activity_draft_updated", "draft": result}


def activity_draft_resolve_fee_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "draft_ref", "expected_revision", "resolution", "updated_at_utc"}
    if set(value) != expected: raise ValueError
    result = resolve_desktop_activity_draft_unclassified_fee_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
        value["draft_ref"], value["expected_revision"], value["resolution"],
        value["updated_at_utc"],
    )
    return {"status": "activity_draft_fee_resolved", "draft": result}


def activity_draft_bind_fifo_order_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "draft_ref", "expected_revision", "fifo_order_evidence", "updated_at_utc"}
    if set(value) != expected: raise ValueError
    result = bind_desktop_activity_draft_fifo_order_evidence_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
        value["draft_ref"], value["expected_revision"], value["fifo_order_evidence"],
        value["updated_at_utc"],
    )
    return {"status": "activity_draft_fifo_order_bound", "draft": result}


def activity_draft_bind_fifo_order_group_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "draft_ref", "expected_revision", "peer_draft_refs", "updated_at_utc"}
    if set(value) != expected: raise ValueError
    result = bind_desktop_activity_draft_fifo_order_group_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
        value["draft_ref"], value["expected_revision"], value["peer_draft_refs"],
        value["updated_at_utc"],
    )
    return {"status": "activity_draft_fifo_order_group_bound", "draft": result}


def activity_draft_standard_recovery_prepare_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "activity_csv_path", "transaction_root_path", "data_space_path", "owner_policy"}
    if set(value) != expected: raise ValueError
    result = prepare_standardized_legacy_activity_recovery_v1(
        Path(value["activity_csv_path"]), Path(value["transaction_root_path"]),
        Path(value["data_space_path"]), product_context(value["context"]),
        value["owner_policy"],
    )
    return {"status": "activity_draft_standard_recovery_prepared", **result}


def activity_draft_standard_recovery_simulate_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "private_plan", "canonical_path", "data_space_path"}
    if set(value) != expected: raise ValueError
    result = simulate_standardized_legacy_activity_recovery_v1(
        value["private_plan"], Path(value["canonical_path"]),
        Path(value["data_space_path"]), product_context(value["context"]),
    )
    return {"status": "activity_draft_standard_recovery_simulated", "simulation": result}


def activity_draft_read_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path", "draft_ref"}: raise ValueError
    result = read_desktop_activity_draft_v1(
        Path(value["data_space_path"]), product_context(value["context"]), value["draft_ref"]
    )
    return {"status": "activity_draft_read", "draft": result}


def activity_draft_explain_command(value: dict[str, Any]) -> dict[str, Any]:
    """Der Grund blockierter Entwuerfe - nur lesend, mehrere Entwuerfe in einem Aufruf (#420)."""
    if set(value) != {"context", "canonical_path", "data_space_path", "draft_refs"}: raise ValueError
    refs = value["draft_refs"]
    if not isinstance(refs, list) or not 1 <= len(refs) <= 200 or len(set(refs)) != len(refs): raise ValueError
    runtime = product_context(value["context"])
    return {"status": "activity_draft_explained", "explanations": [
        explain_desktop_activity_draft_block_v1(
            Path(value["canonical_path"]), Path(value["data_space_path"]), runtime, draft_ref,
        ) for draft_ref in refs
    ]}


def activity_draft_validate_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "draft_ref", "expected_revision", "validated_at_utc"}
    if set(value) != expected: raise ValueError
    result = validate_desktop_activity_draft_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["draft_ref"],
        value["expected_revision"], value["validated_at_utc"],
    )
    return {"status": "activity_draft_validated", "draft": result}


def activity_draft_confirmation_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "trusted_draft", "challenge_ref", "issued_at_utc", "confirmed_at_utc", "expires_at_utc"}
    draft = value.get('trusted_draft', {})
    if draft.get('activity_draft_version') == 2 and draft.get('draft_state') == 'applying':
        if set(value) != expected | {'data_space_path'}: raise ValueError
        result = build_desktop_activity_draft_recovery_confirmation_v2(
            Path(value['data_space_path']), product_context(value['context']), draft['draft_ref'],
            value['challenge_ref'], value['issued_at_utc'], value['confirmed_at_utc'], value['expires_at_utc'])
        if result['draft_revision'] != draft['revision'] or result['validation_fingerprint'] != draft['validation']['validation_fingerprint']:
            raise ValueError
        return {'status': 'activity_draft_confirmation_built', 'confirmation': result}
    if set(value) != expected: raise ValueError
    result = build_desktop_activity_draft_confirmation_v1(
        value["trusted_draft"], product_context(value["context"]), value["challenge_ref"],
        value["issued_at_utc"], value["confirmed_at_utc"], value["expires_at_utc"],
    )
    return {"status": "activity_draft_confirmation_built", "confirmation": result}


def activity_draft_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "draft_ref", "confirmation", "committed_at_utc"}
    if set(value) != expected: raise ValueError
    result = apply_desktop_activity_draft_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["draft_ref"], value["confirmation"],
        value["committed_at_utc"],
    )
    return {"status": "activity_draft_applied", "result": result,
            "reference_carry_status": carry_reference_after_correction(value, result),
            "provenance_status": reconcile_provenance_after_draft(value, result)}


def reconcile_provenance_after_draft(value: dict[str, Any], result: Any) -> str:
    """Nach dem Buchen eines Entwurfs: Hat er eine Absicht (Reward-Import), bekommt die Buchung ihre Herkunft. Gebucht ist schon -
    ein Fehler wird gemeldet, die Buchung bleibt."""
    from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, reconcile_reader_provenance_v1
    draft = result.get("trusted_draft") if isinstance(result, dict) else None
    event_ref = (draft or {}).get("event", {}).get("event_ref") if isinstance(draft, dict) else None
    if not isinstance(draft, dict) or draft.get("draft_state") != "committed" or not isinstance(event_ref, str):
        return "not_applicable"
    try:
        reconciled = reconcile_reader_provenance_v1(Path(value["data_space_path"]), product_context(value["context"]), value["committed_at_utc"], [event_ref])
    except AssetActivityReferenceV1Error as error:
        return "failed:" + error.code
    return "recorded" if reconciled["written_count"] else "not_applicable"


def carry_reference_after_correction(value: dict[str, Any], result: Any) -> str:
    """Eine Korrektur legt die Buchung unter neuem Schluessel an; ihre Belegangaben ziehen mit.

    Die Korrektur ist an dieser Stelle gebucht. Scheitert der Uebertrag, bleibt sie
    gebucht - gemeldet wird der Zustand, damit die Oberflaeche ihn nennen kann.
    Eine Neuanlage aus einem Entwurf (etwa ein Reward-Import nach einem Storno) uebernimmt
    die Angaben einer gleichen stornierten Buchung (#439).
    """
    draft = result.get("trusted_draft") if isinstance(result, dict) else None
    if not isinstance(draft, dict) or draft.get("draft_state") != "committed":
        return "not_applicable"
    predecessor, event = draft.get("predecessor_event_ref"), draft.get("event")
    if not isinstance(event, dict) or not isinstance(event.get("event_ref"), str):
        return "not_applicable"
    if draft.get("action_type") == "create":
        return carry_reference_after_reimport(value, [event["event_ref"]], value["committed_at_utc"])
    if draft.get("action_type") != "correct":
        return "not_applicable"
    return carry_reference_between(value, predecessor, event["event_ref"], value["committed_at_utc"])


def carry_reference_between(value: dict[str, Any], predecessor: Any, successor: Any, at: str) -> str:
    if not isinstance(predecessor, str) or not isinstance(successor, str):
        return "not_applicable"
    try:
        return carry_activity_reference_v1(Path(value["data_space_path"]), product_context(value["context"]), predecessor, successor, at)["status"]
    except (AssetActivityReferenceV1Error, DesktopProductAssetActivityV1Error, OSError):
        return "failed"


def carry_reference_after_reimport(value: dict[str, Any], event_refs: list[str], at: str) -> str:
    """Storno und Wiederimport (#439): Eine neu gebuchte Buchung, die einer stornierten gleicht, uebernimmt deren Angaben.
    Die Buchung steht an dieser Stelle; scheitert der Uebertrag, wird nur der Zustand gemeldet."""
    if not event_refs:
        return "not_applicable"
    try:
        return carry_activity_references_from_voided_v1(Path(value["data_space_path"]), product_context(value["context"]), event_refs, at)["status"]
    except (AssetActivityReferenceV1Error, DesktopProductAssetActivityV1Error, OSError):
        return "failed"


def activity_draft_resume_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path", "draft_ref"}: raise ValueError
    result = resume_desktop_activity_draft_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["draft_ref"],
    )
    return {"status": "activity_draft_resumed", "result": result}


def activity_draft_retire_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    """Einen erledigten Reward-Lauf stilllegen (#520): Seine Rewards sind in einem anderen Lauf gebucht. Ohne eigene Buchung loest
    der Ersatzlauf ihn ab (supersession), mit eigenen Buchungen bleiben diese erhalten (mixed-source retirement). Liest nur."""
    if set(value) != {"context", "data_space_path", "source_fingerprint", "replacement_source_fingerprint", "expected_draft_count",
                      "expected_committed_draft_count", "previewed_at_utc"}: raise ValueError
    committed = value["expected_committed_draft_count"]
    if not isinstance(committed, int) or isinstance(committed, bool) or committed < 0: raise ValueError
    mode = "supersession" if committed == 0 else "mixed_source_retirement"
    # Beide Verfahren des Kerns verlangen einen Ersatz ohne eigene Entwuerfe - sie sind fuer "erst ersetzen, dann neu einlesen"
    # gebaut. Der deckende Lauf hat aber schon Entwuerfe. Als Ersatz steht deshalb eine Markierung "erledigt, gebucht in Lauf X",
    # eindeutig aus beiden Quellen gebildet; der Kern vermerkt den Ersatz nur und nutzt ihn sonst nicht.
    # Ersatz gleich Quelle heisst: Der Eigentuemer bestaetigt, die restlichen Rewards von Hand gebucht zu haben.
    kind = "portelyra_retired_by_owner_v1" if value["replacement_source_fingerprint"] == value["source_fingerprint"] else "portelyra_retired_as_booked_v1"
    marker = hashlib.sha256((kind + ":" + value["source_fingerprint"] + ":"
                             + value["replacement_source_fingerprint"]).encode("utf-8")).hexdigest()
    args = (Path(value["data_space_path"]), product_context(value["context"]), value["source_fingerprint"],
            marker, value["expected_draft_count"])
    preview = (preview_desktop_activity_draft_source_supersession_v1(*args, value["previewed_at_utc"]) if mode == "supersession"
               else preview_desktop_activity_draft_mixed_source_retirement_v1(*args, committed, value["previewed_at_utc"]))
    # Der vertrauliche Teil reist als unveraenderte Zeichenkette durch R; eine JSON-Umwandlung dort koennte den Pruefwert brechen.
    return {"status": "activity_draft_retire_previewed", "mode": mode, "public_preview": preview["public_preview"],
            "trusted_preview_token": json.dumps(preview["trusted_preview"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)}


def activity_draft_retire_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    """Wendet die gezeigte Vorschau an. Die Bestaetigung entsteht erst hier, auf den ausdruecklichen Klick des Eigentuemers, und gilt
    zehn Minuten fuer genau diese Vorschau."""
    if set(value) != {"context", "data_space_path", "mode", "trusted_preview_token", "confirmed_at_utc"}: raise ValueError
    if value["mode"] not in ("supersession", "mixed_source_retirement") or not isinstance(value["trusted_preview_token"], str): raise ValueError
    trusted = json.loads(value["trusted_preview_token"])
    context = product_context(value["context"])
    at = value["confirmed_at_utc"]
    expires = (datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ") + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    challenge = "ads_" + secrets.token_hex(16)
    if value["mode"] == "supersession":
        confirmation = build_desktop_activity_draft_source_supersession_confirmation_v1(trusted, context, challenge, at, at, expires)
        result = apply_desktop_activity_draft_source_supersession_v1(Path(value["data_space_path"]), context, trusted, confirmation, at)
    else:
        confirmation = build_desktop_activity_draft_mixed_source_retirement_confirmation_v1(trusted, context, challenge, at, at, expires)
        result = apply_desktop_activity_draft_mixed_source_retirement_v1(Path(value["data_space_path"]), context, trusted, confirmation, at)
    return {"status": "activity_draft_retired", "mode": value["mode"], "result": result}


def activity_draft_list_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path"}: raise ValueError
    result = list_desktop_activity_drafts_v1(
        Path(value["data_space_path"]), product_context(value["context"])
    )
    return {"status": "activity_draft_listed", "drafts": result}


def activity_mapping_profile_save_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "profile_label", "is_standard", "default_portfolio_id", "default_account_id", "portfolio_mappings", "account_mappings", "asset_mappings", "saved_at_utc"}
    if set(value) != expected: raise ValueError
    result = save_desktop_activity_mapping_profile_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
        value["profile_label"], value["is_standard"], value["default_portfolio_id"],
        value["default_account_id"], value["portfolio_mappings"],
        value["account_mappings"], value["asset_mappings"], value["saved_at_utc"],
    )
    return {"status": "activity_mapping_profile_saved", "profile": result}


def activity_mapping_profile_list_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path"}: raise ValueError
    result = list_desktop_activity_mapping_profiles_v1(
        Path(value["data_space_path"]), product_context(value["context"]),
    )
    return {"status": "activity_mapping_profiles_listed", "profiles": result}


def activity_mapping_profile_read_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path", "profile_ref"}: raise ValueError
    result = read_desktop_activity_mapping_profile_v1(
        Path(value["data_space_path"]), product_context(value["context"]), value["profile_ref"],
    )
    return {"status": "activity_mapping_profile_read", "profile": result}


def activity_csv_inspect_command(value: dict[str, Any]) -> dict[str, Any]:
    expected={"context","canonical_path","data_space_path","source_path","portfolio_id"}
    if set(value)!=expected: raise ValueError
    result=inspect_asset_activity_csv_v1(Path(value["source_path"]),Path(value["canonical_path"]),Path(value["data_space_path"]),product_context(value["context"]),value["portfolio_id"])
    return {"status":"activity_csv_inspected","inspection":result}


def activity_csv_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    expected={"context","canonical_path","data_space_path","trusted_inspection","mapping_selection","previewed_at_utc"}
    if set(value)!=expected: raise ValueError
    result=preview_asset_activity_csv_import_v1(value["trusted_inspection"],value["mapping_selection"],Path(value["canonical_path"]),Path(value["data_space_path"]),product_context(value["context"]),value["previewed_at_utc"])
    return {"status":"activity_csv_previewed","preview":result}


def activity_csv_confirmation_command(value: dict[str, Any]) -> dict[str, Any]:
    expected={"context","trusted_plan","challenge_ref","issued_at_utc","expires_at_utc"}
    if set(value)!=expected: raise ValueError
    result=build_asset_activity_csv_confirmation_v1(value["trusted_plan"],product_context(value["context"]),value["challenge_ref"],value["issued_at_utc"],value["expires_at_utc"])
    return {"status":"activity_csv_confirmation_built","confirmation":result}


def activity_csv_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected={"context","canonical_path","data_space_path","trusted_plan","confirmation","applied_at_utc"}
    if set(value)!=expected: raise ValueError
    result=apply_asset_activity_csv_import_v1(Path(value["canonical_path"]),Path(value["data_space_path"]),product_context(value["context"]),value["trusted_plan"],value["confirmation"],value["applied_at_utc"])
    refs=[row["event"]["event_ref"] for row in value["trusted_plan"].get("rows",[]) if isinstance(row,dict) and isinstance(row.get("event"),dict)]
    return {"status":"activity_csv_applied","result":asdict(result),"reference_carry_status":carry_reference_after_reimport(value,refs,value["applied_at_utc"])}


def _cash_statement_parsed(value: dict[str, Any]) -> dict[str, Any]:
    # Ein Auszug oder ein ganzer Ordner: mehrere Dateien werden als ein Stapel gelesen.
    from migrations.reference.cash_statement_import_v1 import parse_cash_statement_set_v1
    paths = value["source_path"] if isinstance(value["source_path"], list) else [value["source_path"]]
    names = value["file_name"] if isinstance(value["file_name"], list) else [value["file_name"]]
    if len(paths) != len(names) or not paths:
        raise ValueError
    sources = []
    for item, name in zip(paths, names):
        source = Path(item)
        if not source.is_file() or source.is_symlink():
            raise ValueError
        sources.append((source.read_bytes(), name))
    parsed = parse_cash_statement_set_v1(value["adapter_id"], sources)
    confirmed = value.get("confirmed_balance")
    if confirmed is None:
        return parsed
    # Vom Eigentuemer bestaetigter Saldo am Stichtag: zweiter Beleg fuer Exporte ohne Saldo.
    from migrations.reference.cash_statement_import_v1 import confirm_cash_statement_balance_v1
    if not isinstance(confirmed, dict) or set(confirmed) != {"as_of_date", "balance_decimal"}:
        raise ValueError
    return confirm_cash_statement_balance_v1(parsed, confirmed["as_of_date"], confirmed["balance_decimal"])


def cash_statement_detect_command(value: dict[str, Any]) -> dict[str, Any]:
    # Nur ein Vorschlag, wenn die gewaehlte Quelle die Dateien nicht lesen kann.
    if set(value) != {"source_path", "file_name"}: raise ValueError
    from migrations.reference.cash_statement_import_v1 import detect_cash_statement_adapters_v1
    paths = value["source_path"] if isinstance(value["source_path"], list) else [value["source_path"]]
    names = value["file_name"] if isinstance(value["file_name"], list) else [value["file_name"]]
    if len(paths) != len(names) or not paths:
        raise ValueError
    sources = []
    for item, name in zip(paths, names):
        source = Path(item)
        if not source.is_file() or source.is_symlink():
            raise ValueError
        sources.append((source.read_bytes(), name))
    return {"status": "cash_statement_detected", "matches": detect_cash_statement_adapters_v1(sources)}


def _securities_statement_sources(value: dict[str, Any]) -> list[tuple[bytes, str]]:
    paths = value["source_path"] if isinstance(value["source_path"], list) else [value["source_path"]]
    names = value["file_name"] if isinstance(value["file_name"], list) else [value["file_name"]]
    if len(paths) != len(names) or not paths:
        raise ValueError
    sources = []
    for item, name in zip(paths, names):
        source = Path(item)
        if not source.is_file() or source.is_symlink():
            raise ValueError
        sources.append((source.read_bytes(), name))
    return sources


def securities_statement_adapters_command(value: dict[str, Any]) -> dict[str, Any]:
    from migrations.reference.securities_statement_import_v1 import list_securities_statement_adapters_v1
    return {"status": "securities_statement_adapters_listed", "adapters": list_securities_statement_adapters_v1()}


def securities_statement_review_command(value: dict[str, Any]) -> dict[str, Any]:
    # Lesen, Kontovorschlag je Depot und Pruefung gegen den Bestand in einem Aufruf: Die Belege werden nur einmal in Text
    # verwandelt. depot_accounts: Depot-Handle -> account_id; fehlt ein Depot, gilt der Vorschlag (sofern eindeutig).
    # window (#462): betrachteter Zeitraum {mode, from, through}; was ausserhalb liegt, wird nur gezaehlt.
    # scope_skip (#551): Vorgaenge einer im Portfolio nicht gewaehlten Klasse ueberspringen (bewusste Wahl, Teil des Fingerabdrucks).
    required = {"context", "canonical_path", "data_space_path", "adapter_id", "source_path", "file_name", "depot_accounts", "window"}
    if not required <= set(value) <= required | {"scope_skip"} or not isinstance(value.get("scope_skip", False), bool): raise ValueError
    from migrations.reference.securities_statement_import_v1 import (
        detect_securities_statement_adapters_v1, parse_securities_statement_set_v1, review_securities_statement_import_v1,
        suggest_securities_statement_accounts_v1,
    )
    sources = _securities_statement_sources(value)
    adapter_id = value["adapter_id"]
    # Ausblenden (Festlegung 09.11.2026): Nur Plugins, die in mindestens einem Portfolio aktiv sind - "Automatisch erkennen" nimmt keine anderen,
    # Krypto-Dateien einer nicht aktiven Boerse stehen mit Grund unter "Dateien ohne Buchung".
    from migrations.reference.crypto_statement_import_v1 import set_inactive_crypto_readers_v1
    from migrations.reference.statement_reader_admin_v1 import offered_readers_v1
    from migrations.reference.statement_reader_plugins_v1 import reader_specs_v1
    offered = {item["reader_id"] for item in offered_readers_v1(Path(value["data_space_path"]), product_context(value["context"]))["readers"]}
    set_inactive_crypto_readers_v1({spec.reader_id for spec in reader_specs_v1("crypto")} - offered)
    if adapter_id == "auto":
        detected = detect_securities_statement_adapters_v1(sources, ("securities", "crypto"))
        matches = [item for item in detected if item["adapter_id"] in offered or item["adapter_id"] in ("crypto_exports_v1", "generic_securities_v1", "generic_crypto_v1")]
        if not matches:
            # Erkannt, aber nicht aktiv (rc.440, Endabnahme 19.11.2026): nennen statt „keine passenden Belege“, damit der Nutzer den Leser
            # im Reiter „Leser“ aktivieren kann. Nur Name und Kennung des Lesers, nichts aus den Belegen.
            inactive = [{"adapter_id": item["adapter_id"], "label": item["label"]} for item in detected if item["adapter_id"] not in offered]
            return {"status": "securities_statement_reviewed", "review": None, "suggestion": None, "account_refs": {}, "depot_accounts": {}, "trusted_review_token": None,
                    "inactive_matches": inactive}
        adapter_id = max(matches, key=lambda item: item["matching_documents"])["adapter_id"]
    context = product_context(value["context"])
    # Der experimentelle generische Leser (#514) nimmt die gespeicherten Profile des Datenraums.
    options = None
    if adapter_id in ("generic_securities_v1", "generic_crypto_v1"):
        from migrations.reference.generic_statement_import_v1 import read_generic_profiles_v1
        options = {"profiles": read_generic_profiles_v1(Path(value["data_space_path"]))}
    parsed = parse_securities_statement_set_v1(adapter_id, sources, options)
    suggestion = suggest_securities_statement_accounts_v1(Path(value["canonical_path"]), context, parsed)
    chosen = value["depot_accounts"] if isinstance(value["depot_accounts"], dict) else {}
    mapping = {}
    for depot in suggestion["public"]["depots"]:
        account_id = chosen.get(depot["depot_handle"])
        if account_id is None and depot["suggested_account_ref"]:
            account_id = suggestion["trusted_account_refs"][depot["suggested_account_ref"]]
        if account_id:
            mapping[depot["depot_handle"]] = account_id
    review = review_securities_statement_import_v1(Path(value["canonical_path"]), Path(value["data_space_path"]), context, parsed, mapping, value["window"],
                                                   value.get("scope_skip", False))
    # Pruefstand (rc.380): Leser aller neuen Vorgaenge, Vorabpauschalen und Splits dieser Vorschau.
    readers, accounts, pairs = _trusted_readers(review["trusted_review"], "all")
    # Saldoprobe gibt es hier nur fuer Devisen-Kontoauszuege (Saldo-Anker); Abrechnungen und Exporte nennen keinen Saldo.
    check = _reader_check_view(Path(value["data_space_path"]), context, readers, accounts, bool(parsed.get("statement_count")), pairs) if readers else None
    # Der vertrauliche Teil reist als unveraenderte Zeichenkette durch R: eine JSON-Umwandlung dort koennte leere Werte
    # anders schreiben und den Pruefwert brechen.
    return {"status": "securities_statement_reviewed", "review": review["public_review"], "suggestion": suggestion["public"],
            "account_refs": suggestion["trusted_account_refs"], "depot_accounts": mapping, "reader_check": check,
            "trusted_review_token": json.dumps(review["trusted_review"], sort_keys=True, separators=(",", ":"), ensure_ascii=False)}


def generic_statement_propose_command(value: dict[str, Any]) -> dict[str, Any]:
    """Experimenteller generischer Leser (#514): je Format der gewaehlten Dateien der Vorschlag und ein gespeichertes Profil."""
    if set(value) != {"context", "data_space_path", "source_path", "file_name"}: raise ValueError
    product_context(value["context"])
    from migrations.reference.generic_statement_import_v1 import FIELD_LABELS, FIELDS, KIND_LABELS, propose_profile_v1, read_generic_profiles_v1
    from migrations.reference.securities_statement_import_v1 import _text
    profiles = read_generic_profiles_v1(Path(value["data_space_path"]))
    formats: dict[str, dict[str, Any]] = {}
    unreadable = 0
    for source, name in _securities_statement_sources(value):
        proposal = propose_profile_v1(_text(source, name), name) if name.lower().endswith((".csv", ".txt")) else None
        if proposal is None:
            unreadable += 1; continue
        known = formats.get(proposal["signature"])
        if known is not None:
            known["file_count"] += 1; continue
        formats[proposal["signature"]] = {**proposal, "saved": profiles.get(proposal["signature"]), "file_count": 1}
    return {"status": "generic_statement_proposed", "formats": list(formats.values()), "unreadable_count": unreadable,
            "fields": [{"field": field, "label": FIELD_LABELS[field]} for field in FIELDS],
            "kinds": [{"kind": kind, "label": label} for kind, label in KIND_LABELS.items()]}


def generic_statement_profile_save_command(value: dict[str, Any]) -> dict[str, Any]:
    """Ein Profil je Format speichern (#514): nur im Datenraum, nach Bestaetigung."""
    if set(value) != {"context", "data_space_path", "signature", "profile", "confirmed"}: raise ValueError
    product_context(value["context"])
    from migrations.reference.generic_statement_import_v1 import save_generic_profile_v1
    result = save_generic_profile_v1(Path(value["data_space_path"]), value["signature"], value["profile"], value["confirmed"] is True)
    return {**result, "status": "generic_statement_profile_saved"}


def securities_statement_csv_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path", "trusted_review_token", "target_path", "reader_check_acknowledged"} \
            or not isinstance(value["trusted_review_token"], str) or not isinstance(value["reader_check_acknowledged"], bool): raise ValueError
    from migrations.reference import statement_reader_checks_v1 as reader_checks
    from migrations.reference.securities_statement_import_v1 import build_securities_statement_csv_v1, record_statement_reader_intents_v1
    trusted = json.loads(value["trusted_review_token"])
    # Pruefstand (rc.380): Der Buchungsplan entsteht nur, wenn jeder Leser geprueft oder ausdruecklich bestaetigt ist.
    readers, accounts, pairs = _trusted_readers(trusted, "candidates")
    if readers:
        reader_checks.require_reader_checks_v1(Path(value["data_space_path"]), product_context(value["context"]), readers, value["reader_check_acknowledged"], accounts,
                                               reader_accounts=pairs)
    content = build_securities_statement_csv_v1(Path(value["canonical_path"]), product_context(value["context"]), trusted)
    # Herkunft je Buchung (rc.378): die Leser jedes neuen Vorgangs als Absicht, bevor gebucht wird - auch ein fortgesetzter Import findet sie.
    intents = record_statement_reader_intents_v1(Path(value["data_space_path"]), product_context(value["context"]), trusted,
                                                 datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    target = Path(value["target_path"])
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise ValueError
    with target.open("xb") as handle:
        handle.write(content)
    target.chmod(0o600)
    return {"status": "securities_statement_csv_written", "row_count": content.decode("utf-8").count("\n") - 1, "provenance_intent_count": intents["intent_count"]}


def securities_statement_confirm_command(value: dict[str, Any]) -> dict[str, Any]:
    """Nach dem Buchen: Pruefstand des Lesers im Datenraum fortschreiben (nur bei vollstaendig gebuchter Pruefung)."""
    if set(value) != {"context", "data_space_path", "trusted_review_token", "created_event_count", "confirmed_at_utc", "reader_check_acknowledged"} \
            or not isinstance(value["trusted_review_token"], str) or not isinstance(value["reader_check_acknowledged"], bool): raise ValueError
    from migrations.reference.securities_statement_import_v1 import (
        record_securities_statement_confirmation_v1, record_statement_import_references_v1, record_statement_reader_provenance_v1,
    )
    context = product_context(value["context"])
    trusted = json.loads(value["trusted_review_token"])
    # Herkunft je Buchung (rc.378) zuerst: Sie haengt nicht davon ab, ob die Pruefung vollstaendig gebucht wurde.
    provenance = record_statement_reader_provenance_v1(Path(value["data_space_path"]), context, trusted, value["confirmed_at_utc"])
    result = record_securities_statement_confirmation_v1(Path(value["data_space_path"]), trusted, value["created_event_count"], value["confirmed_at_utc"])
    # Kennungen der gebuchten Vorgaenge in den Beleg-Speicher (#458): Transaktions-ID, Hash, Order- oder Vorgangsnummer
    references = record_statement_import_references_v1(Path(value["data_space_path"]), context, trusted, value["confirmed_at_utc"])
    # Pruefstand (rc.380): nach dem Buchen fuer genau diesen Plugin-Code festhalten (nur wenn etwas gebucht wurde).
    readers, accounts, pairs = _trusted_readers(trusted, "candidates")
    created = int(value["created_event_count"])
    reader_check = _record_reader_checks(Path(value["data_space_path"]), context, readers, value["reader_check_acknowledged"], accounts,
                                         value["confirmed_at_utc"], None, created, pairs) if readers and created > 0 else 0
    return {"status": "securities_statement_confirmation_recorded", **result, "references_recorded": references["recorded_count"],
            "provenance_recorded": provenance["recorded_count"], "provenance_pending": provenance["pending_count"], "reader_check_recorded": reader_check}


def securities_statement_references_command(value: dict[str, Any]) -> dict[str, Any]:
    """Kennungen gebuchter Vorgaenge aus den Belegen nachtragen (#458 Teil 3, #439), nur nach Bestaetigung."""
    if set(value) != {"context", "data_space_path", "trusted_review_token", "recorded_at_utc", "confirmed"} or not isinstance(value["trusted_review_token"], str): raise ValueError
    from migrations.reference.securities_statement_import_v1 import record_statement_reference_backfill_v1
    result = record_statement_reference_backfill_v1(Path(value["data_space_path"]), product_context(value["context"]), json.loads(value["trusted_review_token"]),
                                                    value["recorded_at_utc"], value["confirmed"] is True)
    return {"status": "securities_statement_references_recorded", **result}


def securities_statement_advance_lump_sums_command(value: dict[str, Any]) -> dict[str, Any]:
    """Vorabpauschalen der Belege in ihren Speicher (#460): die fehlenden, die abweichenden nur auf ausdruecklichen Wunsch."""
    if set(value) != {"context", "data_space_path", "trusted_review_token", "replace_differing", "recorded_at_utc", "confirmed", "reader_check_acknowledged"} \
            or not isinstance(value["trusted_review_token"], str) or not isinstance(value["reader_check_acknowledged"], bool): raise ValueError
    from migrations.reference import statement_reader_checks_v1 as reader_checks
    from migrations.reference.securities_statement_import_v1 import record_securities_statement_advance_lump_sums_v1
    trusted, context, space = json.loads(value["trusted_review_token"]), product_context(value["context"]), Path(value["data_space_path"])
    readers, accounts, pairs = _trusted_readers(trusted, "advance")
    if readers:   # Pruefstand (rc.380), je Leser nur die Portfolios seiner Konten (rc.381)
        reader_checks.require_reader_checks_v1(space, context, readers, value["reader_check_acknowledged"], accounts, reader_accounts=pairs)
    result = record_securities_statement_advance_lump_sums_v1(space, context, trusted, value["replace_differing"], value["recorded_at_utc"], value["confirmed"])
    written = int(result.get("written_count") or 0)
    check = _record_reader_checks(space, context, readers, value["reader_check_acknowledged"], accounts, value["recorded_at_utc"], None, written, pairs) \
        if readers and written > 0 else 0
    return {"status": "securities_statement_advance_lump_sums_recorded", **result, "reader_check_recorded": check}


def securities_statement_stock_splits_command(value: dict[str, Any]) -> dict[str, Any]:
    """Splits der Mitteilungen uebernehmen und split-bereinigt gebuchte Vorgaenge auf die Belegstuecke umstellen (#451, rc.372)."""
    if set(value) != {"context", "canonical_path", "data_space_path", "trusted_review_token", "recorded_at_utc", "confirmed", "reader_check_acknowledged"} or \
            not isinstance(value["trusted_review_token"], str) or not isinstance(value["reader_check_acknowledged"], bool): raise ValueError
    from migrations.reference import statement_reader_checks_v1 as reader_checks
    from migrations.reference.securities_statement_import_v1 import record_securities_statement_stock_splits_v1
    trusted, context, space = json.loads(value["trusted_review_token"]), product_context(value["context"]), Path(value["data_space_path"])
    readers, accounts, pairs = _trusted_readers(trusted, "splits")
    if readers:   # Pruefstand (rc.380), je Leser nur die Portfolios seiner Konten (rc.381)
        reader_checks.require_reader_checks_v1(space, context, readers, value["reader_check_acknowledged"], accounts, reader_accounts=pairs)
    result = record_securities_statement_stock_splits_v1(Path(value["canonical_path"]), space, context, trusted, value["recorded_at_utc"], value["confirmed"])
    recorded = int(result.get("recorded_split_count") or 0)
    check = _record_reader_checks(space, context, readers, value["reader_check_acknowledged"], accounts, value["recorded_at_utc"], None, recorded, pairs) \
        if readers and recorded > 0 else 0
    return {"status": "securities_statement_stock_splits_recorded", **result, "reader_check_recorded": check}


def cash_statement_adapters_command(value: dict[str, Any]) -> dict[str, Any]:
    from migrations.reference.cash_statement_import_v1 import list_cash_statement_adapters_v1
    return {"status": "cash_statement_adapters_listed", "adapters": list_cash_statement_adapters_v1()}


def _reader_check_view(space, context, readers, account_ids, balance_checked=None, reader_accounts=None) -> dict[str, Any]:
    """Pruefstand der Leser fuer die Vorschau (rc.380): Stand, Texte und ob das Buchen eine ausdrueckliche Bestaetigung braucht. Laesst er
    sich nicht ermitteln, nennt die Vorschau den Grund, und das Buchen verlangt die Bestaetigung (schliesst nicht still auf).
    balance_checked: ob der Beleg einen Saldo nennt, den der Kern nachrechnet; ohne ihn warnt die Vorschau deutlich (07.11.2026)."""
    from migrations.reference import statement_reader_checks_v1 as reader_checks
    try:
        return {"status": "ready", **reader_checks.reader_checks_v1(space, context, readers, account_ids or None, balance_checked=balance_checked,
                                                                    reader_accounts=reader_accounts)}
    except (StatementReaderCheckV1Error, AssetActivityReferenceV1Error) as error:
        return {"status": "unavailable", "code": error.code, "acknowledgment_required": True, "notes": [], "hints": [], "readers": [],
                "balance_checked": balance_checked, "balance_warning": reader_checks.BALANCE_WARNING if balance_checked is False else None}


def _record_reader_checks(space, context, readers, acknowledged, account_ids, recorded_at_utc, document_count, booking_count, reader_accounts=None):
    """Nach dem Buchen den Pruefstand festhalten; scheitert das, bleibt die Buchung stehen und die Meldung sagt es ("failed:<code>")."""
    from migrations.reference import statement_reader_checks_v1 as reader_checks
    try:
        return reader_checks.confirm_reader_checks_v1(space, context, readers, acknowledged, account_ids or None, recorded_at_utc,
                                                      document_count, booking_count, reader_accounts=reader_accounts)["recorded_count"]
    except StatementReaderCheckV1Error as error:
        return "failed:" + error.code


def _trusted_readers(trusted: dict[str, Any], part: str) -> tuple[list[dict[str, Any]], list[str], list[tuple[dict[str, Any], list[str]]]]:
    """Leser und Konten einer geprueften Wertpapier-/Krypto-Vorschau (rc.380): neue Vorgaenge, Vorabpauschalen oder Splits. Dazu je Leser die
    Konten, in die er bucht (Portfolios getrennt, rc.381)."""
    readers: list[dict[str, Any]] = []
    accounts: list[Any] = []
    pairs: list[tuple[dict[str, Any], list[str]]] = []
    def take(found, account):
        for reader in found or []:
            readers.append(reader)
            if isinstance(account, str) and account:
                pairs.append((reader, [account]))
        accounts.append(account)
    if part in ("candidates", "all"):
        for candidate in trusted.get("new_candidates") or []:
            take(candidate.get("readers"), candidate.get("account_id"))
    if part in ("advance", "all"):
        from migrations.reference.asset_activity_reference_v1 import advance_lump_sum_provenance_key_v1
        by_key = trusted.get("advance_lump_sum_readers") or {}
        for entry in list(trusted.get("new_advance_lump_sums") or []) + list(trusted.get("differing_advance_lump_sums") or []):
            key = advance_lump_sum_provenance_key_v1(entry.get("asset_id"), entry.get("account_id"), entry.get("calculation_year")) \
                if entry.get("asset_id") and entry.get("account_id") and entry.get("calculation_year") is not None else None
            take(by_key.get(key) if key else None, entry.get("account_id"))
        for item in by_key.values():   # Leser ohne zuordenbaren Eintrag zaehlen fuer alle Portfolios der Vorschau
            readers += [reader for reader in item or [] if reader not in readers]
    if part in ("splits", "all"):
        for split in trusted.get("new_stock_splits") or []:
            take(split.get("readers"), split.get("account_id"))
    return readers, sorted({account for account in accounts if isinstance(account, str) and account}), pairs


def _reader_pairs(pairs: Any) -> list[dict[str, str]]:
    """Leser als [{reader_id, domain}] -> Herkunft-Kennungen der installierten Plugins (Pruefstand, rc.380)."""
    from migrations.reference.statement_reader_plugins_v1 import StatementReaderBlocked, reader_identity_v1
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= 50 or not all(isinstance(item, dict) and set(item) == {"reader_id", "domain"}
                                                                         and all(isinstance(item[key], str) for key in item) for item in pairs):
        raise StatementReaderCheckV1Error("statement_reader_check_input_invalid")
    try:
        return [reader_identity_v1(item["reader_id"], item["domain"]) for item in pairs]
    except StatementReaderBlocked:
        raise StatementReaderCheckV1Error("statement_reader_check_input_invalid") from None


def _account_list(value: Any) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value): raise ValueError
    return list(value)


def statement_reader_offered_command(value: dict[str, Any]) -> dict[str, Any]:
    """Was die Import-Karten anbieten (rc.381, ausblenden): Leser der Plugins, die in mindestens einem Portfolio aktiv sind, mit Bezeichnung."""
    if set(value) != {"context", "data_space_path"}: raise ValueError
    from migrations.reference.statement_reader_admin_v1 import StatementReaderAdminV1Error, offered_readers_v1
    from migrations.reference.statement_reader_plugins_v1 import reader_spec_v1
    try:
        offered = offered_readers_v1(Path(value["data_space_path"]), product_context(value["context"]))
    except StatementReaderAdminV1Error as error:
        raise StatementReaderCheckV1Error("statement_reader_check_store_invalid") from error
    readers = []
    for item in offered["readers"]:
        spec = reader_spec_v1(item["reader_id"], item["domain"])
        readers.append({**item, "label": spec.label if spec else item["reader_id"], "institution": spec.institution if spec else "",
                        "origin": spec.origin if spec else "shipped"})
    return {"status": "statement_reader_offered_read", "plugin_ids": offered["plugin_ids"], "readers": readers}


def statement_reader_check_command(value: dict[str, Any]) -> dict[str, Any]:
    """Pruefstand der Leser eines Imports (rc.380), fuer Ablaeufe ohne eigenen Vorschau-Befehl (Rewards). Schreibt nur den einmaligen
    Bestandseintrag in einem Datenraum aus der Zeit vor rc.380."""
    if set(value) != {"context", "data_space_path", "readers", "account_ids", "balance_checked"} or value["balance_checked"] not in (True, False, None): raise ValueError
    check = _reader_check_view(Path(value["data_space_path"]), product_context(value["context"]), _reader_pairs(value["readers"]),
                               _account_list(value["account_ids"]), value["balance_checked"])
    return {"status": "statement_reader_check_read", "reader_check": check}


def statement_reader_check_confirm_command(value: dict[str, Any]) -> dict[str, Any]:
    """Vor dem Buchen pruefen (phase "require": ungepruefter Leser ohne Bestaetigung bricht ab) oder nach dem Buchen festhalten ("record")."""
    expected = {"context", "data_space_path", "readers", "account_ids", "acknowledged", "phase", "recorded_at_utc", "document_count", "booking_count"}
    if set(value) != expected or value["phase"] not in ("require", "record") or not isinstance(value["acknowledged"], bool) \
            or any(item is not None and (not isinstance(item, int) or isinstance(item, bool) or item < 0) for item in (value["document_count"], value["booking_count"])): raise ValueError
    from migrations.reference import statement_reader_checks_v1 as reader_checks
    space, context = Path(value["data_space_path"]), product_context(value["context"])
    readers, accounts = _reader_pairs(value["readers"]), _account_list(value["account_ids"])
    if value["phase"] == "require":
        reader_checks.require_reader_checks_v1(space, context, readers, value["acknowledged"], accounts or None)
        return {"status": "statement_reader_check_confirmed", "reader_check_recorded": 0}
    return {"status": "statement_reader_check_confirmed",
            "reader_check_recorded": _record_reader_checks(space, context, readers, value["acknowledged"], accounts, value["recorded_at_utc"],
                                                           value["document_count"], value["booking_count"])}


def _cash_reader(adapter_id: str) -> list[dict[str, str]]:
    from migrations.reference.statement_reader_plugins_v1 import reader_identity_v1
    return [reader_identity_v1(adapter_id, "cash")]


def cash_statement_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path", "adapter_id", "source_path", "file_name", "account_id", "confirmed_balance"}: raise ValueError
    from migrations.reference.cash_statement_import_v1 import preview_cash_statement_import_v1
    parsed = _cash_statement_parsed(value)
    context = product_context(value["context"])
    preview = preview_cash_statement_import_v1(Path(value["data_space_path"]), context, parsed, value["account_id"])
    summary = parsed.get("summary") or {}
    balanced = bool(parsed.get("balance_consistent")) and (summary.get("closing_balance_decimal") is not None or summary.get("opening_balance_decimal") is not None)
    check = _reader_check_view(Path(value["data_space_path"]), context, _cash_reader(parsed["adapter_id"]), [value["account_id"]], balanced)
    return {"status": "cash_statement_previewed", "preview": {**preview, "diagnostics": parsed["diagnostics"], "adapter_id": parsed["adapter_id"], "reader_check": check}}


def cash_statement_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "adapter_id", "source_path", "file_name", "scope", "applied_at_utc", "include_text", "max_commands",
                "confirmed_balance", "reader_check_acknowledged"}
    if set(value) != expected or not isinstance(value["reader_check_acknowledged"], bool): raise ValueError
    from migrations.reference import statement_reader_checks_v1 as reader_checks
    from migrations.reference.cash_statement_import_v1 import apply_cash_statement_import_v1
    parsed = _cash_statement_parsed(value)
    context, space = product_context(value["context"]), Path(value["data_space_path"])
    # Pruefstand (rc.380): ein Leser, der in diesem Portfolio noch nicht an Ihren Belegen geprueft ist, bucht nur mit ausdruecklicher Bestaetigung.
    readers, accounts = _cash_reader(parsed["adapter_id"]), [value["scope"]["account_id"]]
    reader_checks.require_reader_checks_v1(space, context, readers, value["reader_check_acknowledged"], accounts)
    result = apply_cash_statement_import_v1(Path(value["canonical_path"]), space, context, parsed,
                                            value["scope"], value["applied_at_utc"], include_text=bool(value["include_text"]), max_commands=int(value["max_commands"]))
    if result.get("status") != "in_progress":   # nach dem letzten Schritt festhalten, fuer genau diesen Plugin-Code
        files = value["file_name"] if isinstance(value["file_name"], list) else [value["file_name"]]
        result = {**result, "reader_check_recorded": _record_reader_checks(space, context, readers, value["reader_check_acknowledged"], accounts,
                                                                           value["applied_at_utc"], len(files), int(result.get("total_command_count") or 0))}
    return {"status": "cash_statement_applied", "result": result}


def cash_statement_gross_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    # consider_from (#462): Brutto-Vorschlaege erst ab diesem Tag; "" = alle.
    expected = {"context", "data_space_path", "adapter_id", "source_path", "file_name", "account_id", "confirmed_balance", "consider_from"}
    if set(value) != expected: raise ValueError
    from migrations.reference.cash_statement_import_v1 import preview_cash_statement_gross_interest_corrections_v1
    parsed = _cash_statement_parsed(value)
    correction = preview_cash_statement_gross_interest_corrections_v1(Path(value["data_space_path"]), product_context(value["context"]), parsed, value["account_id"],
                                                                      value["consider_from"] or None)
    return {"status": "cash_statement_gross_previewed", "correction": correction}


def cash_statement_gross_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "adapter_id", "source_path", "file_name", "scope", "applied_at_utc", "max_corrections", "confirmed_balance", "consider_from"}
    if set(value) != expected: raise ValueError
    from migrations.reference.cash_statement_import_v1 import apply_cash_statement_gross_interest_corrections_v1
    parsed = _cash_statement_parsed(value)
    result = apply_cash_statement_gross_interest_corrections_v1(Path(value["canonical_path"]), Path(value["data_space_path"]), product_context(value["context"]),
                                                                parsed, value["scope"], value["applied_at_utc"], max_corrections=int(value["max_corrections"]),
                                                                consider_from=value["consider_from"] or None)
    return {"status": "cash_statement_gross_applied", "result": result}


def booked_latest_dates_command(value: dict[str, Any]) -> dict[str, Any]:
    """Juengstes gebuchtes Datum je Institut fuer eine Buchungsart - Vorbelegung "ab dem letzten Import" (#462). Liest nur."""
    if set(value) != {"context", "canonical_path", "data_space_path", "event_type"}: raise ValueError
    from migrations.reference.securities_statement_import_v1 import latest_booked_dates_v1
    return {"status": "booked_latest_dates_read",
            "latest": latest_booked_dates_v1(Path(value["canonical_path"]), Path(value["data_space_path"]), product_context(value["context"]), value["event_type"])}


def reward_account_suggest_command(value: dict[str, Any]) -> dict[str, Any]:
    """Kontovorschlag je Coin fuer den Reward-Import (rc.343). Liest nur."""
    if set(value) != {"context", "canonical_path", "data_space_path", "adapter_id", "asset_ids"}: raise ValueError
    from migrations.reference.securities_statement_import_v1 import suggest_reward_accounts_v1
    return {"status": "reward_accounts_suggested",
            "accounts": suggest_reward_accounts_v1(Path(value["canonical_path"]), Path(value["data_space_path"]), product_context(value["context"]),
                                                   value["adapter_id"], value["asset_ids"])}


def cash_movements_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path", "account_id"}: raise ValueError
    from migrations.reference.cash_statement_import_v1 import list_cash_movements_v1
    return {"status": "cash_movements_listed", "movements": list_cash_movements_v1(Path(value["data_space_path"]), product_context(value["context"]), value["account_id"])}


def reward_references_record_command(value: dict[str, Any]) -> dict[str, Any]:
    """Kennung der Boerse an gebuchten Rewards nachtragen (rc.345): aus den uebergebenen Dateien und allen Dateien der Ablage.
    Nach dem Buchen aufgerufen; die Buchung steht dann schon, ein Fehler hier aendert an ihr nichts."""
    if set(value) != {"context", "data_space_path", "adapter_id", "source_paths", "recorded_at_utc"} or not isinstance(value["source_paths"], list): raise ValueError
    from migrations.reference.statement_reader_plugins_v1 import reward_reader_has_row_ids_v1
    from migrations.reference.statement_reward_references_v1 import record_reward_statement_references_v1
    from migrations.reference.statement_archive_v1 import list_statement_files_v1
    context = product_context(value["context"]); space = Path(value["data_space_path"])
    sources: list[bytes] = []
    paths = [Path(item) for item in value["source_paths"] if isinstance(item, str) and item]
    if reward_reader_has_row_ids_v1(value["adapter_id"]):
        from migrations.reference.desktop_product_asset_activity_v1 import read_desktop_product_per_asset_catalog_v1
        accounts = [row["account_id"] for row in read_desktop_product_per_asset_catalog_v1(space / "canonical.sqlite", context)["accounts"]]
        if accounts:
            listed = list_statement_files_v1(space, value["context"], accounts, 2009, datetime.now().year + 1)["files"]
            paths += [Path(item["path"]) for item in listed]
    seen: set[str] = set()
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 32_000_000:
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        # Nur Textdateien (CSV); PDF und ZIP koennen keine Reward-Zeilen tragen.
        if digest in seen or data[:4] in (b"%PDF", b"PK\x03\x04"):
            continue
        seen.add(digest); sources.append(data)
        if len(sources) >= 256:
            break
    result = record_reward_statement_references_v1(space, context, value["adapter_id"], sources, value["recorded_at_utc"])
    return {"status": "reward_references_recorded", "references": {**result, "source_count": len(sources)}}


def reward_booked_match_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value)!={"context","data_space_path","candidates"}: raise ValueError
    from migrations.reference.statement_reward_booked_match_v1 import match_booked_statement_rewards_v1
    result=match_booked_statement_rewards_v1(Path(value["data_space_path"]),product_context(value["context"]),value["candidates"])
    return {"status":"reward_booked_matched","match":result}


def asset_maintenance_state_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value)!={"context","data_space_path","as_of_date"}: raise ValueError
    from migrations.reference.asset_maintenance_state_v1 import read_asset_maintenance_state_v1
    result=read_asset_maintenance_state_v1(Path(value["data_space_path"]),value["context"],value["as_of_date"])
    return {"status":"asset_maintenance_state_read","state":result}


def asset_maintenance_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value)!={"context","data_space_path","request","as_of_date"}: raise ValueError
    from migrations.reference.asset_maintenance_state_v1 import preview_asset_maintenance_declaration_v1
    result=preview_asset_maintenance_declaration_v1(Path(value["data_space_path"]),value["context"],value["request"],value["as_of_date"])
    return {"status":"asset_maintenance_declaration_previewed","preview":result}


def asset_maintenance_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected={"context","data_space_path","request","as_of_date","preview_fingerprint","declared_at_utc","confirmed"}
    if set(value)!=expected: raise ValueError
    from migrations.reference.asset_maintenance_state_v1 import apply_asset_maintenance_declaration_v1
    result=apply_asset_maintenance_declaration_v1(
        Path(value["data_space_path"]),value["context"],value["request"],value["as_of_date"],
        value["preview_fingerprint"],value["declared_at_utc"],value["confirmed"])
    return {"status":"asset_maintenance_declaration_applied","result":result}


def asset_maintenance_runs_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value)!={"context","data_space_path"}: raise ValueError
    from migrations.reference.asset_maintenance_state_v1 import read_asset_maintenance_runs_v1
    result=read_asset_maintenance_runs_v1(Path(value["data_space_path"]),value["context"])
    return {"status":"asset_maintenance_runs_read","runs":result}


def activity_csv_export_command(value: dict[str, Any]) -> dict[str, Any]:
    expected={"context","canonical_path","data_space_path","portfolio_id","asset_id","exported_at_utc"}
    if set(value)!=expected: raise ValueError
    result=export_asset_activity_csv_v1(Path(value["canonical_path"]),Path(value["data_space_path"]),product_context(value["context"]),value["portfolio_id"],value["asset_id"],value["exported_at_utc"])
    return {"status":"activity_csv_exported","export":result}


def activity_csv_resumable_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value)!={"context","data_space_path"}: raise ValueError
    result=list_resumable_asset_activity_csv_imports_v1(Path(value["data_space_path"]),product_context(value["context"]))
    return {"status":"activity_csv_resumable_read","resumable":result}


def activity_csv_resume_command(value: dict[str, Any]) -> dict[str, Any]:
    expected={"context","canonical_path","data_space_path","plan_fingerprint"}
    if set(value)!=expected: raise ValueError
    result=resume_asset_activity_csv_import_v1(Path(value["canonical_path"]),Path(value["data_space_path"]),product_context(value["context"]),value["plan_fingerprint"])
    return {"status":"activity_csv_resumed","result":asdict(result)}


def generation_retention_plan_command(value: dict[str, Any]) -> dict[str, Any]:
    """Speicher aufraeumen (#438): welche Generationen des Buchungsbestands nur Zwischenstaende sind. Nur lesen."""
    if set(value) != {"context", "data_space_path"}: raise ValueError
    plan = read_desktop_asset_activity_generation_retention_plan_v1(Path(value["data_space_path"]), product_context(value["context"]))
    keys = ("status", "generation_count", "kept_generation_count", "receipt_generation_count", "preserved_predecessor_count",
            "removed_generation_count", "kept_byte_count", "removed_byte_count", "plan_fingerprint")
    return {"status": "generation_retention_planned", "plan": {key: plan.get(key) for key in keys}}


def generation_retention_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    """Genau den bestaetigten Plan ausfuehren; unter der Schreibsperre neu erhoben (#438)."""
    if set(value) != {"context", "data_space_path", "plan_fingerprint", "confirmed", "applied_at_utc"}: raise ValueError
    receipt = apply_desktop_asset_activity_generation_retention_v1(Path(value["data_space_path"]), product_context(value["context"]),
                                                                   value["plan_fingerprint"], value["confirmed"], value["applied_at_utc"])
    keys = ("applied_at_utc", "kept_generation_count", "removed_generation_count", "removed_byte_count")
    return {"status": "generation_retention_applied", "receipt": {key: receipt.get(key) for key in keys}}


def activity_correction_candidates_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path"}: raise ValueError
    candidates = read_desktop_asset_activity_correction_candidates_v1(Path(value["data_space_path"]), product_context(value["context"]))
    return {"status": "activity_correction_candidates_read", "candidates": candidates}


def activity_correction_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "predecessor_event_ref", "replacement_event", "previewed_at_utc"}
    if set(value) != expected: raise ValueError
    preview = preview_desktop_asset_activity_correction_v1(Path(value["canonical_path"]), Path(value["data_space_path"]), product_context(value["context"]), value["predecessor_event_ref"], value["replacement_event"], value["previewed_at_utc"])
    return {"status": "activity_correction_previewed", "preview": preview}


def activity_correction_confirmation_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "trusted_preview", "challenge_ref", "issued_at_utc", "confirmed_at_utc", "expires_at_utc"}
    if set(value) != expected: raise ValueError
    confirmation = build_desktop_asset_activity_correction_confirmation_v1(value["trusted_preview"], product_context(value["context"]), value["challenge_ref"], value["issued_at_utc"], value["confirmed_at_utc"], value["expires_at_utc"])
    return {"status": "activity_correction_confirmation_built", "confirmation": confirmation}


def activity_correction_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "trusted_preview", "confirmation", "committed_at_utc"}
    if set(value) != expected: raise ValueError
    result = apply_desktop_asset_activity_correction_v1(Path(value["canonical_path"]), Path(value["data_space_path"]), product_context(value["context"]), value["trusted_preview"], value["confirmation"], value["committed_at_utc"])
    # Die Korrektur aus der Buchungsmaske nimmt die Belegangaben mit wie die aus einem Entwurf (#439; bisher nur dort).
    preview, carry = value["trusted_preview"], "not_applicable"
    if result.action_type == "correct" and isinstance(preview.get("replacement_event"), dict):
        carry = carry_reference_between(value, preview.get("predecessor_event_ref"), preview["replacement_event"].get("event_ref"), value["committed_at_utc"])
    return {"status": "activity_correction_applied", "result": asdict(result), "reference_carry_status": carry}


def activity_correction_history_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path"}: raise ValueError
    history = read_desktop_asset_activity_correction_history_v1(Path(value["data_space_path"]), product_context(value["context"]))
    return {"status": "activity_correction_history_read", "history": history}


def quantity_scale_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "asset_id", "quantity_values", "previewed_at_utc"}
    if set(value) != expected: raise ValueError
    preview = preview_desktop_asset_quantity_scale_revision_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["asset_id"], value["quantity_values"],
        value["previewed_at_utc"],
    )
    return {"status": "quantity_scale_previewed", "preview": preview}


def quantity_scale_confirmation_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "trusted_preview", "challenge_ref", "issued_at_utc", "confirmed_at_utc", "expires_at_utc"}
    if set(value) != expected: raise ValueError
    confirmation = build_desktop_asset_quantity_scale_confirmation_v1(
        value["trusted_preview"], product_context(value["context"]), value["challenge_ref"],
        value["issued_at_utc"], value["confirmed_at_utc"], value["expires_at_utc"],
    )
    return {"status": "quantity_scale_confirmation_built", "confirmation": confirmation}


def quantity_scale_begin_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "trusted_preview", "confirmation", "committed_at_utc"}
    if set(value) != expected: raise ValueError
    result = begin_desktop_asset_quantity_scale_revision_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["trusted_preview"], value["confirmation"],
        value["committed_at_utc"],
    )
    return {"status": "quantity_scale_begun", "result": result}


def quantity_scale_finalize_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "plan_fingerprint"}
    if set(value) != expected: raise ValueError
    result = finalize_desktop_asset_quantity_scale_revision_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["plan_fingerprint"],
    )
    return {"status": "quantity_scale_finalized", "result": asdict(result)}


def quantity_scale_pending_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path"}
    if set(value) != expected: raise ValueError
    pending = list_pending_desktop_asset_quantity_scale_revisions_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]),
    )
    return {"status": "quantity_scale_pending_read", "pending": pending}


def realized_state_materialize_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "data_space_path", "request_mode", "requested_at_utc", "portfolio_completeness"}
    if set(value) != expected: raise ValueError
    result = materialize_asset_activity_realized_state_v2(Path(value["data_space_path"]), product_context(value["context"]), value["request_mode"], value["requested_at_utc"], value["portfolio_completeness"])
    return {"status": "realized_state_materialized", "result": asdict(result)}


def realized_state_read_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path"}: raise ValueError
    model = read_asset_activity_realized_state_v2(Path(value["data_space_path"]), product_context(value["context"]))
    return {"status": "realized_state_read", "model": model}


def realized_state_verify_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path"}: raise ValueError
    result = verify_asset_activity_realized_state_full_rebuild_v2(Path(value["data_space_path"]), product_context(value["context"]))
    return {"status": "realized_state_verified", "result": result}


def portfolio_readiness_read_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value)!={"context","canonical_path","data_space_path"}: raise ValueError
    model=read_portfolio_operational_readiness_v1(Path(value["canonical_path"]),Path(value["data_space_path"]),product_context(value["context"]))
    return {"status":"portfolio_readiness_read","model":model}


def cash_coverage_catalog_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path"}:
        raise ValueError
    catalog = read_desktop_cash_coverage_catalog_v1(
        Path(value["canonical_path"]), product_context(value["context"])
    )
    return {"status": "cash_coverage_catalog_read", "catalog": catalog}


def cash_coverage_view_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path"}:
        raise ValueError
    view = read_desktop_cash_coverage_view_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]),
    )
    return {"status": "cash_coverage_view_read", "view": view}


def cash_coverage_revision_candidates_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path"}:
        raise ValueError
    candidates = read_desktop_cash_coverage_revision_candidates_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]),
    )
    return {"status": "cash_coverage_revision_candidates_read", "candidates": candidates}


def cash_coverage_recovery_candidates_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "data_space_path"}:
        raise ValueError
    candidates = read_desktop_cash_coverage_recovery_candidates_v1(
        Path(value["data_space_path"]), product_context(value["context"])
    )
    return {"status": "cash_coverage_recovery_candidates_read", "candidates": candidates}


def cash_coverage_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path", "command"}:
        raise ValueError
    preview = preview_desktop_cash_coverage_command_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["command"],
    )
    return {"status": "cash_coverage_previewed", "preview": preview}


def cash_coverage_reviewed_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path", "reviewed_candidate", "request_ref"}:
        raise ValueError
    preview = preview_desktop_reviewed_cash_coverage_candidate_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["reviewed_candidate"], value["request_ref"],
    )
    return {"status": "cash_coverage_reviewed_previewed", "preview": preview}


def cash_coverage_confirmation_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "preview", "confirmation_ref", "issued_at_utc", "expires_at_utc"}
    if set(value) != expected:
        raise ValueError
    confirmation = build_desktop_cash_coverage_confirmation_v1(
        value["preview"], product_context(value["context"]), value["confirmation_ref"],
        value["issued_at_utc"], value["expires_at_utc"],
    )
    return {"status": "cash_coverage_confirmation_built", "confirmation": confirmation}


def cash_coverage_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "command", "confirmation", "committed_at_utc"}
    if set(value) != expected:
        raise ValueError
    result = apply_desktop_cash_coverage_command_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["command"], value["confirmation"],
        value["committed_at_utc"],
    )
    return {"status": "cash_coverage_applied", "result": asdict(result)}


def cash_check_balance_prepare_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path", "request"}:
        raise ValueError
    from migrations.reference.desktop_cash_manual_v1 import prepare_desktop_cash_check_balance_v1
    prepared = prepare_desktop_cash_check_balance_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["request"],
    )
    return {"status": "cash_check_balance_prepared", "prepared": prepared}


def cash_manual_booking_prepare_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path", "request"}:
        raise ValueError
    from migrations.reference.desktop_cash_manual_v1 import prepare_desktop_cash_manual_booking_v1
    prepared = prepare_desktop_cash_manual_booking_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["request"],
    )
    return {"status": "cash_manual_booking_prepared", "prepared": prepared}


def cash_manual_batch_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "commands", "preview_fingerprint", "confirmed_by_owner_at_utc", "committed_at_utc"}
    if set(value) != expected:
        raise ValueError
    from migrations.reference.desktop_cash_coverage_v1 import apply_desktop_cash_coverage_manual_batch_v1
    result = apply_desktop_cash_coverage_manual_batch_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]), product_context(value["context"]),
        value["commands"], value["preview_fingerprint"], value["confirmed_by_owner_at_utc"], value["committed_at_utc"],
    )
    return {"status": "cash_manual_batch_applied", "result": result}


def cash_evidence_overview_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path", "as_of_date"}:
        raise ValueError
    from migrations.reference.desktop_cash_manual_v1 import read_desktop_cash_evidence_overview_v1
    overview = read_desktop_cash_evidence_overview_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["as_of_date"],
    )
    return {"status": "cash_evidence_overview_read", "overview": overview}


def cash_coverage_recovery_preview_command(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"context", "canonical_path", "data_space_path", "recovery_ref"}:
        raise ValueError
    preview = preview_desktop_cash_coverage_recovery_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["recovery_ref"],
    )
    return {"status": "cash_coverage_recovery_previewed", "recovery": preview}


def cash_coverage_recovery_confirmation_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "trusted_preview", "confirmation_ref", "issued_at_utc", "expires_at_utc"}
    if set(value) != expected:
        raise ValueError
    confirmation = build_desktop_cash_coverage_recovery_confirmation_v1(
        value["trusted_preview"], product_context(value["context"]), value["confirmation_ref"],
        value["issued_at_utc"], value["expires_at_utc"],
    )
    return {"status": "cash_coverage_recovery_confirmation_built", "confirmation": confirmation}


def cash_coverage_recovery_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {"context", "canonical_path", "data_space_path", "trusted_preview", "recovery_confirmation", "recovered_at_utc"}
    if set(value) != expected:
        raise ValueError
    result = apply_desktop_cash_coverage_recovery_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]),
        product_context(value["context"]), value["trusted_preview"],
        value["recovery_confirmation"], value["recovered_at_utc"],
    )
    return {"status": "cash_coverage_recovery_applied", "result": asdict(result)}


def product_apply_command(value: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "projection", "review", "expected_plan_fingerprint", "expected_preview_fingerprint",
        "context", "canonical_path", "data_space_path", "target_asset_id",
        "selected_account_ids", "committed_at_utc",
    }
    if set(value) != expected:
        raise ValueError
    runtime, scope = product_scope(value)
    if value["review"].get("target_asset", {}).get("asset_ref") != scope["target_asset_id"]:
        raise ValueError
    result = apply_desktop_product_per_asset_cutover_v1(
        Path(value["canonical_path"]), Path(value["data_space_path"]), runtime,
        scope["portfolio_id"], value["projection"], value["review"],
        value["expected_plan_fingerprint"], value["expected_preview_fingerprint"],
        value["committed_at_utc"],
    )
    output = asdict(result)
    output["semantic_contracts"] = list(output["semantic_contracts"])
    return {"status": "product_applied", "result": output}


def main() -> int:
    parser = argparse.ArgumentParser(description="Portelyra per-Asset local review bridge")
    parser.add_argument("command", choices=("open", "plan", "apply", "product-binding", "product-activity-view", "product-catalog", "product-preview", "product-apply", "product-republish", "native-activity-time", "native-activity-preview", "native-activity-apply", "redundant-activity-inspect", "activity-draft-create", "activity-draft-create-or-reuse", "activity-draft-update", "activity-draft-shift-second", "activity-draft-resolve-fee", "activity-draft-bind-fifo-order", "activity-draft-bind-fifo-order-group", "activity-draft-standard-recovery-prepare", "activity-draft-standard-recovery-simulate", "activity-draft-read", "activity-draft-explain", "activity-draft-validate", "activity-draft-confirmation", "activity-draft-apply", "activity-draft-resume", "activity-draft-list", "activity-draft-retire-preview", "activity-draft-retire-apply", "activity-mapping-profile-save", "activity-mapping-profile-list", "activity-mapping-profile-read", "activity-csv-inspect", "activity-csv-preview", "activity-csv-confirmation", "activity-csv-apply", "activity-csv-resumable", "activity-csv-resume", "activity-csv-export", "reward-booked-match", "reward-references-record", "asset-maintenance-state", "asset-maintenance-preview", "asset-maintenance-apply", "asset-maintenance-runs", "cash-statement-adapters", "cash-statement-detect", "securities-statement-adapters", "securities-statement-review", "securities-statement-csv", "securities-statement-confirm", "securities-statement-advance-lump-sums", "securities-statement-stock-splits", "securities-statement-references", "generic-statement-propose", "generic-statement-profile-save", "booked-latest-dates", "reward-account-suggest", "cash-statement-preview", "cash-statement-apply", "cash-statement-gross-preview", "cash-statement-gross-apply", "cash-movements", "activity-correction-candidates", "generation-retention-plan", "generation-retention-apply", "activity-correction-preview", "activity-correction-confirmation", "activity-correction-apply", "activity-correction-history", "quantity-scale-preview", "quantity-scale-confirmation", "quantity-scale-begin", "quantity-scale-finalize", "quantity-scale-pending", "realized-state-materialize", "realized-state-read", "realized-state-verify", "portfolio-readiness-read", "cash-coverage-catalog", "cash-coverage-view", "cash-coverage-revision-candidates", "cash-coverage-recovery-candidates", "cash-coverage-preview", "cash-coverage-reviewed-preview", "cash-coverage-confirmation", "cash-coverage-apply", "cash-check-balance-prepare", "cash-manual-booking-prepare", "cash-manual-batch-apply", "cash-evidence-overview", "cash-coverage-recovery-preview", "cash-coverage-recovery-confirmation", "cash-coverage-recovery-apply", "statement-reader-check", "statement-reader-check-confirm", "statement-reader-offered"))
    arguments = parser.parse_args()
    try:
        value = payload()
        output = {
            "open": open_command,
            "plan": plan_command,
            "apply": apply_command,
            "product-binding": product_binding_command,
            "product-activity-view": product_activity_view_command,
            "product-catalog": product_catalog_command,
            "product-preview": product_preview_command,
            "product-apply": product_apply_command,
            "product-republish": product_republish_command,
            "native-activity-time": native_activity_time_command,
            "native-activity-preview": native_activity_preview_command,
            "native-activity-apply": native_activity_apply_command,
            "redundant-activity-inspect": redundant_activity_inspect_command,
            "activity-draft-create": activity_draft_create_command,
            "activity-draft-create-or-reuse": activity_draft_create_or_reuse_command,
            "activity-draft-update": activity_draft_update_command,
            "activity-draft-shift-second": activity_draft_shift_second_command,
            "activity-draft-resolve-fee": activity_draft_resolve_fee_command,
            "activity-draft-bind-fifo-order": activity_draft_bind_fifo_order_command,
            "activity-draft-bind-fifo-order-group": activity_draft_bind_fifo_order_group_command,
            "activity-draft-standard-recovery-prepare": activity_draft_standard_recovery_prepare_command,
            "activity-draft-standard-recovery-simulate": activity_draft_standard_recovery_simulate_command,
            "activity-draft-read": activity_draft_read_command,
            "activity-draft-explain": activity_draft_explain_command,
            "activity-draft-validate": activity_draft_validate_command,
            "activity-draft-confirmation": activity_draft_confirmation_command,
            "activity-draft-apply": activity_draft_apply_command,
            "activity-draft-resume": activity_draft_resume_command,
            "activity-draft-list": activity_draft_list_command,
            "activity-draft-retire-preview": activity_draft_retire_preview_command,
            "activity-draft-retire-apply": activity_draft_retire_apply_command,
            "activity-mapping-profile-save": activity_mapping_profile_save_command,
            "activity-mapping-profile-list": activity_mapping_profile_list_command,
            "activity-mapping-profile-read": activity_mapping_profile_read_command,
            "activity-csv-inspect": activity_csv_inspect_command,
            "activity-csv-preview": activity_csv_preview_command,
            "activity-csv-confirmation": activity_csv_confirmation_command,
            "activity-csv-apply": activity_csv_apply_command,
            "activity-csv-resumable": activity_csv_resumable_command,
            "activity-csv-resume": activity_csv_resume_command,
            "activity-csv-export": activity_csv_export_command,
            "reward-booked-match": reward_booked_match_command,
            "reward-references-record": reward_references_record_command,
            "asset-maintenance-state": asset_maintenance_state_command,
            "asset-maintenance-preview": asset_maintenance_preview_command,
            "asset-maintenance-apply": asset_maintenance_apply_command,
            "asset-maintenance-runs": asset_maintenance_runs_command,
            "cash-statement-adapters": cash_statement_adapters_command,
            "cash-statement-detect": cash_statement_detect_command,
            "cash-statement-preview": cash_statement_preview_command,
            "securities-statement-adapters": securities_statement_adapters_command,
            "securities-statement-review": securities_statement_review_command,
            "securities-statement-csv": securities_statement_csv_command,
            "securities-statement-confirm": securities_statement_confirm_command,
            "securities-statement-advance-lump-sums": securities_statement_advance_lump_sums_command,
            "securities-statement-stock-splits": securities_statement_stock_splits_command,
            "securities-statement-references": securities_statement_references_command,
            "generic-statement-propose": generic_statement_propose_command,
            "generic-statement-profile-save": generic_statement_profile_save_command,
            "booked-latest-dates": booked_latest_dates_command,
            "reward-account-suggest": reward_account_suggest_command,
            "cash-statement-apply": cash_statement_apply_command,
            "cash-statement-gross-preview": cash_statement_gross_preview_command,
            "cash-statement-gross-apply": cash_statement_gross_apply_command,
            "cash-movements": cash_movements_command,
            "activity-correction-candidates": activity_correction_candidates_command,
            "generation-retention-plan": generation_retention_plan_command,
            "generation-retention-apply": generation_retention_apply_command,
            "activity-correction-preview": activity_correction_preview_command,
            "activity-correction-confirmation": activity_correction_confirmation_command,
            "activity-correction-apply": activity_correction_apply_command,
            "activity-correction-history": activity_correction_history_command,
            "quantity-scale-preview": quantity_scale_preview_command,
            "quantity-scale-confirmation": quantity_scale_confirmation_command,
            "quantity-scale-begin": quantity_scale_begin_command,
            "quantity-scale-finalize": quantity_scale_finalize_command,
            "quantity-scale-pending": quantity_scale_pending_command,
            "realized-state-materialize": realized_state_materialize_command,
            "realized-state-read": realized_state_read_command,
            "realized-state-verify": realized_state_verify_command,
            "portfolio-readiness-read": portfolio_readiness_read_command,
            "cash-coverage-catalog": cash_coverage_catalog_command,
            "cash-coverage-view": cash_coverage_view_command,
            "cash-coverage-revision-candidates": cash_coverage_revision_candidates_command,
            "cash-coverage-recovery-candidates": cash_coverage_recovery_candidates_command,
            "cash-coverage-preview": cash_coverage_preview_command,
            "cash-coverage-reviewed-preview": cash_coverage_reviewed_preview_command,
            "cash-coverage-confirmation": cash_coverage_confirmation_command,
            "cash-coverage-apply": cash_coverage_apply_command,
            "cash-check-balance-prepare": cash_check_balance_prepare_command,
            "cash-manual-booking-prepare": cash_manual_booking_prepare_command,
            "cash-manual-batch-apply": cash_manual_batch_apply_command,
            "cash-evidence-overview": cash_evidence_overview_command,
            "cash-coverage-recovery-preview": cash_coverage_recovery_preview_command,
            "cash-coverage-recovery-confirmation": cash_coverage_recovery_confirmation_command,
            "cash-coverage-recovery-apply": cash_coverage_recovery_apply_command,
            "statement-reader-check": statement_reader_check_command,
            "statement-reader-offered": statement_reader_offered_command,
            "statement-reader-check-confirm": statement_reader_check_confirm_command,
        }[arguments.command](value)
        emit(output)
        return 0
    except (LegacyAssetCompanionV1Error, LegacyPerAssetTradePlannerV1Error, PerAssetSandboxApplyV1Error, DesktopProductAssetActivityV1Error, DesktopAssetActivityCorrectionV1Error, DesktopAssetQuantityScaleRevisionV1Error, DesktopActivityDraftV1Error, RedundantAssetActivityCsvV1Error, AssetActivityCsvImportV1Error, AssetActivityRealizedStateV2Error, PortfolioOperationalReadinessV1Error, DesktopCashCoverageV1Error, StandardizedLegacyActivityRecoveryV1Error, CashStatementImportV1Error, SecuritiesStatementImportV1Error, GenericStatementImportV1Error, StatementReaderCheckV1Error) as error:
        emit({"status": "blocked", "code": error.code})
        return 2
    except Exception:
        emit({"status": "failed", "code": "per_asset_review_bridge_failed"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
