"""Browser-safe Asset Activity view over completed FIFO-v2 state.

Canonical schema-401 Events remain fact authority.  This reader never calculates or
materializes FIFO: it joins labels and Event facts only to an already completed,
fresh schema-3100 FIFO-v2 artifact.  Coupled schema-400 Transactions stay on their
separate correction/history surface and never enter this Asset Activity FIFO world.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _abort,
    _context,
    _read_connection,
    read_desktop_product_asset_activity_binding_v1,
)
from workers.reference import asset_activity_realized_state_v2 as state_v2

CONTRACT_VERSION = 2
FIFO_VERSION = 2


def _exact_display(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        _abort("desktop_asset_activity_fifo_invalid")
    status = value.get("exactness_status")
    if status == "exact_decimal":
        result = value.get("decimal")
        if not isinstance(result, str):
            _abort("desktop_asset_activity_fifo_invalid")
        return result
    if status == "exact_ratio":
        numerator = value.get("numerator_integer")
        denominator = value.get("denominator_integer")
        if not isinstance(numerator, str) or not isinstance(denominator, str):
            _abort("desktop_asset_activity_fifo_invalid")
        return numerator + "/" + denominator
    if status in {"basis_missing", "not_applicable"}:
        return None
    _abort("desktop_asset_activity_fifo_invalid")


def _completed_fifo_state(
    data_space: Path,
    context: DesktopProductAssetActivityContextV1,
    binding: Mapping[str, Any],
) -> tuple[str, bool, dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]], dict[tuple[str, str, str], dict[str, Any]]]:
    # Lesemodell, aktueller Stand und Artefakte aus einem einzigen Oeffnen: Jedes
    # Oeffnen prueft den ganzen Speicher, und zwei davon kosteten je Aufruf rund
    # eine Sekunde zusaetzlich.
    try:
        public, current, artifacts = state_v2._read_public_with_current(data_space, context)
    except state_v2.AssetActivityRealizedStateV2Error:
        _abort("desktop_asset_activity_fifo_invalid")
    freshness = public["freshness"]
    verified = bool(public.get("full_rebuild_verified", False))
    if public["status"] != "available" or freshness != "fresh":
        return freshness, verified, {}, {}, {}
    if (
        current is None
        or current["source_generation_ref"] != binding["generation_ref"]
        or current["source_activity_set_fingerprint"] != binding["activity_set_fingerprint"]
    ):
        return "stale", False, {}, {}, {}
    event_results: dict[str, dict[str, Any]] = {}
    asset_positions: dict[tuple[str, str], dict[str, Any]] = {}
    custody_positions: dict[tuple[str, str, str], dict[str, Any]] = {}
    for artifact in artifacts.values():
        portfolio_ref = artifact["portfolio_ref"]
        try:
            result = json.loads(artifact["result_json"])
        except Exception:
            _abort("desktop_asset_activity_fifo_invalid")
        if (
            not isinstance(result, dict)
            or result.get("realized_fifo_version") != FIFO_VERSION
            or result.get("status") != "completed"
            or result.get("result_fingerprint") != artifact["result_fingerprint"]
        ):
            _abort("desktop_asset_activity_fifo_invalid")
        for row in result["event_results"]:
            ref = row["event_ref"]
            if ref in event_results:
                _abort("desktop_asset_activity_fifo_invalid")
            event_results[ref] = row
        world_asset_ref = artifact["asset_ref"]
        world_positions = [row for row in result["asset_positions"] if row["asset_ref"] == world_asset_ref]
        if len(world_positions) != 1:
            _abort("desktop_asset_activity_fifo_invalid")
        key = (portfolio_ref, world_asset_ref)
        if key in asset_positions:
            _abort("desktop_asset_activity_fifo_invalid")
        asset_positions[key] = world_positions[0]
        for row in result["custody_positions"]:
            if row["asset_ref"] != world_asset_ref:
                continue
            key = (portfolio_ref, row["account_ref"], row["asset_ref"])
            if key in custody_positions:
                _abort("desktop_asset_activity_fifo_invalid")
            custody_positions[key] = row
    return freshness, verified, event_results, asset_positions, custody_positions


def read_desktop_product_asset_activity_view_v2(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    """Read facts plus an already completed FIFO-v2 artifact without starting work."""
    context = _context(context_value)
    data_space = Path(data_space_path)
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    empty = {
        "product_asset_activity_read_model_version": CONTRACT_VERSION,
        "status": "absent",
        "ledger_schema_version": None,
        "fifo_version": FIFO_VERSION,
        "fifo_world_dimension": "portfolio_asset",
        "custody_dimension": "portfolio_account_asset",
        "fifo_state": "unavailable",
        "full_rebuild_verified": False,
        "portfolio_count": 0,
        "event_count": 0,
        "position_count": 0,
        "custody_position_count": 0,
        "semantic_sources": [],
        "portfolios": [],
        "coupled_transaction_facts_included": False,
        "calculation_started": False,
        "provider_access": False,
        "network_access": False,
        "canonical_write": False,
        "path_exposed": False,
        "internal_id_exposed": False,
    }
    if binding["status"] == "absent":
        return empty
    ledger = Path(binding["ledger_path"])
    connection = _read_connection(ledger)
    try:
        portfolios = [dict(row) for row in connection.execute(
            "SELECT entity.portfolio_id,revision.display_name FROM portfolio_entity entity "
            "JOIN current_portfolio_revision revision USING(portfolio_id) "
            "WHERE revision.status='active' ORDER BY revision.display_name,entity.portfolio_id"
        )]
        accounts = {row["account_id"]: dict(row) for row in connection.execute(
            "SELECT entity.account_id,entity.portfolio_id,revision.display_name FROM account_entity entity "
            "JOIN current_account_revision revision USING(account_id) WHERE revision.status='active'"
        )}
        assets = {row["asset_id"]: dict(row) for row in connection.execute(
            "SELECT entity.asset_id,revision.display_name,revision.asset_type FROM asset_entity entity "
            "JOIN current_asset_revision revision USING(asset_id) WHERE revision.status='active'"
        )}
        events = [dict(row) for row in connection.execute(
            "SELECT * FROM current_asset_activity_event "
            "ORDER BY portfolio_id,local_date,COALESCE(effective_at_utc,''),event_ref"
        )]
    except sqlite3.Error:
        _abort("desktop_asset_activity_ledger_invalid")
    finally:
        connection.close()
    freshness, verified, fifo_events, fifo_assets, fifo_custody = _completed_fifo_state(
        data_space, context, binding
    )
    fresh = freshness == "fresh"
    event_refs = {row["event_ref"] for row in events}
    if fresh and set(fifo_events) != event_refs:
        _abort("desktop_asset_activity_fifo_invalid")
    portfolio_models: list[dict[str, Any]] = []
    total_positions = 0
    total_custody = 0
    for ordinal, portfolio in enumerate(portfolios, 1):
        portfolio_events = [row for row in events if row["portfolio_id"] == portfolio["portfolio_id"]]
        asset_refs = {row["asset_id"] for row in portfolio_events}
        history = []
        for row in reversed(portfolio_events):
            fifo = fifo_events.get(row["event_ref"])
            calculation_status = "fresh_completed" if fifo is not None else freshness
            history.append({
                "local_date": row["local_date"],
                "effective_at_utc": row["effective_at_utc"],
                "event_time_evidence": row["event_time_evidence"],
                "event_type": row["event_type"],
                "account_label": accounts[row["account_id"]]["display_name"],
                "related_account_label": None if row["related_account_id"] is None else accounts[row["related_account_id"]]["display_name"],
                "asset_label": assets[row["asset_id"]]["display_name"],
                "asset_type": assets[row["asset_id"]]["asset_type"],
                "currency": row["basis_currency"],
                "quantity_decimal": row["quantity_decimal"],
                "amount_decimal": row["gross_economic_amount_decimal"],
                "fee_decimal": row["monetary_fee_decimal"],
                "asset_fee_quantity_decimal": row["asset_fee_quantity_decimal"],
                "basis_added": None if fifo is None else _exact_display(fifo["basis_added"]),
                "basis_consumed": None if fifo is None else _exact_display(fifo["basis_consumed"]),
                "gross_proceeds_decimal": row["net_trade_proceeds_decimal"],
                "realized_gain": None if fifo is None else _exact_display(fifo["realized_gain"]),
                "gross_income_decimal": row["gross_income_decimal"],
                "distribution_value_decimal": row["distribution_value_decimal"],
                "cash_balance_delta_decimal": "0",
                "semantic_contract": "asset_activity_v1",
                "automatic_cash_posting_state": "none_created",
                "fifo_authority": "semantic_realized_fifo_v2",
                "calculation_status": calculation_status,
            })
        positions = []
        custody = []
        if fresh:
            currency_by_asset = {
                ref: next(iter({row["basis_currency"] for row in portfolio_events if row["asset_id"] == ref}))
                for ref in asset_refs
            }
            for ref in sorted(asset_refs):
                row = fifo_assets.get((portfolio["portfolio_id"], ref))
                if row is None:
                    _abort("desktop_asset_activity_fifo_invalid")
                positions.append({
                    "asset_label": assets[ref]["display_name"],
                    "asset_type": row["asset_type"],
                    "currency": currency_by_asset[ref],
                    "remaining_quantity_decimal": row["remaining_quantity_decimal"],
                    "remaining_fifo_basis": _exact_display(row["remaining_fifo_basis"]),
                    "cost_average": _exact_display(row["cost_average"]),
                    "realized_gross_proceeds": _exact_display(row["realized_gross_proceeds"]),
                    "realized_fifo_basis": _exact_display(row["realized_fifo_basis"]),
                    "realized_gain_before_tax": _exact_display(row["realized_gain"]),
                    "gross_income": _exact_display(row["gross_income"]),
                    "monetary_fees": _exact_display(row["monetary_fees"]),
                    "fifo_world": "portfolio_asset",
                })
            for (portfolio_ref, account_ref, asset_ref), row in sorted(fifo_custody.items()):
                if portfolio_ref != portfolio["portfolio_id"] or asset_ref not in asset_refs:
                    continue
                custody.append({
                    "account_label": accounts[account_ref]["display_name"],
                    "asset_label": assets[asset_ref]["display_name"],
                    "asset_type": assets[asset_ref]["asset_type"],
                    "remaining_quantity_decimal": row["remaining_quantity_decimal"],
                    "custody_dimension": "portfolio_account_asset",
                })
        total_positions += len(positions)
        total_custody += len(custody)
        portfolio_models.append({
            "portfolio_ordinal": ordinal,
            "portfolio_label": portfolio["display_name"],
            "positions": positions,
            "custody_positions": custody,
            "events_newest_first": history,
        })
    final_binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if (
        final_binding.get("status") != "available"
        or final_binding.get("generation_ref") != binding["generation_ref"]
        or final_binding.get("ledger_fingerprint") != binding["ledger_fingerprint"]
        or final_binding.get("activity_set_fingerprint") != binding["activity_set_fingerprint"]
    ):
        _abort("desktop_asset_activity_generation_conflict")
    projected = len(events) if fresh else 0
    return {
        **empty,
        "status": "available",
        "ledger_schema_version": 401,
        "fifo_state": freshness,
        "full_rebuild_verified": verified,
        "portfolio_count": len(portfolio_models),
        "event_count": len(events),
        "position_count": total_positions,
        "custody_position_count": total_custody,
        "semantic_sources": [{
            "semantic_contract": "asset_activity_v1",
            "source_event_count": len(events),
            "projected_event_count": projected,
            "coupled_transaction_fact": False,
            "automatic_cash_posting_state": "none_created",
            "fifo_authority": "semantic_realized_fifo_v2",
        }],
        "portfolios": portfolio_models,
    }


__all__ = ["read_desktop_product_asset_activity_view_v2"]
