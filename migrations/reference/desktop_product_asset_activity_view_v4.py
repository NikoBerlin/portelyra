"""Identity-bearing browser-safe Asset/Account Activity view.

Canonical schema-401 Events remain fact authority. This reader never calculates or
materializes FIFO. It binds every public Activity row to the same ephemeral
``activity_asset_*`` and ``activity_account_*`` reference order as the current
trusted Product catalog while canonical IDs remain inside this server boundary.
Presentation labels are not identity and may legitimately repeat.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    _abort,
    _canonical_snapshot,
    _context,
    _read_connection,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.desktop_product_asset_activity_view_v2 import (
    _completed_fifo_state,
    _exact_display,
)

CONTRACT_VERSION = 4
FIFO_VERSION = 2
ASSET_REF_SCHEME = "activity_catalog_ephemeral_v1"
ACCOUNT_REF_SCHEME = "activity_account_ephemeral_v1"
IDENTITY_BRIDGE = "server_bound_not_label"
SUPPORTED_ASSET_DOMAINS = ("noncash",)
ALLOWED_ACCOUNT_TYPES = {"securities", "crypto_wallet", "other"}


def _browser_catalogs(
    canonical_path: str | Path,
    context: DesktopProductAssetActivityContextV1,
) -> tuple[str, dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Resolve canonical IDs to public refs without returning an internal ID."""
    snapshot = _canonical_snapshot(canonical_path, context)
    active_assets = [
        row for row in snapshot["assets"]
        if row["status"] == "active" and row["asset_type"] != "cash"
    ]
    active_accounts = [
        row for row in snapshot["accounts"]
        if row["status"] == "active" and row["account_type"] in ALLOWED_ACCOUNT_TYPES
    ]
    if not active_assets or not active_accounts:
        _abort("desktop_asset_activity_source_invalid")
    assets_by_id: dict[str, dict[str, str]] = {}
    for ordinal, row in enumerate(active_assets, 1):
        asset_id = row["asset_id"]
        if asset_id in assets_by_id:
            _abort("desktop_asset_activity_canonical_invalid")
        assets_by_id[asset_id] = {
            "asset_ref": f"activity_asset_{ordinal:04d}",
            "asset_label": row["display_name"],
            "asset_type": row["asset_type"],
        }
    accounts_by_id: dict[str, dict[str, str]] = {}
    for ordinal, row in enumerate(active_accounts, 1):
        account_id = row["account_id"]
        if account_id in accounts_by_id:
            _abort("desktop_asset_activity_canonical_invalid")
        accounts_by_id[account_id] = {
            "account_ref": f"activity_account_{ordinal:04d}",
            "account_label": row["display_name"],
            "account_type": row["account_type"],
            "portfolio_id": row["portfolio_id"],
        }
    return snapshot["source_fingerprint"], assets_by_id, accounts_by_id


def _public_asset(
    internal_asset_id: Any,
    ledger_assets: Mapping[str, Mapping[str, Any]],
    browser_assets: Mapping[str, Mapping[str, str]],
) -> Mapping[str, str]:
    if not isinstance(internal_asset_id, str):
        _abort("desktop_asset_activity_ledger_invalid")
    public = browser_assets.get(internal_asset_id)
    ledger = ledger_assets.get(internal_asset_id)
    if public is None or ledger is None or ledger.get("asset_type") != public["asset_type"]:
        _abort("desktop_asset_activity_source_invalid")
    return public


def _public_account(
    internal_account_id: Any,
    ledger_accounts: Mapping[str, Mapping[str, Any]],
    browser_accounts: Mapping[str, Mapping[str, str]],
    portfolio_id: str,
) -> Mapping[str, str]:
    if not isinstance(internal_account_id, str):
        _abort("desktop_asset_activity_ledger_invalid")
    public = browser_accounts.get(internal_account_id)
    ledger = ledger_accounts.get(internal_account_id)
    if (
        public is None
        or ledger is None
        or ledger.get("portfolio_id") != portfolio_id
        or public.get("portfolio_id") != portfolio_id
        or ledger.get("account_type") != public.get("account_type")
    ):
        _abort("desktop_asset_activity_source_invalid")
    return public


def read_desktop_product_asset_activity_view_v4(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    """Read completed facts by browser refs without exposing identity authority."""
    context = _context(context_value)
    canonical_fingerprint, browser_assets, browser_accounts = _browser_catalogs(
        canonical_path, context
    )
    data_space = Path(data_space_path)
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    empty = {
        "product_asset_activity_read_model_version": CONTRACT_VERSION,
        "status": "absent",
        "ledger_schema_version": None,
        "fifo_version": FIFO_VERSION,
        "fifo_world_dimension": "portfolio_asset",
        "custody_dimension": "portfolio_account_asset",
        "asset_ref_scheme": ASSET_REF_SCHEME,
        "asset_identity_bridge": IDENTITY_BRIDGE,
        "duplicate_labels_supported": True,
        "account_ref_scheme": ACCOUNT_REF_SCHEME,
        "account_identity_bridge": IDENTITY_BRIDGE,
        "duplicate_account_labels_supported": True,
        "supported_asset_domains": list(SUPPORTED_ASSET_DOMAINS),
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
        final_fingerprint, final_assets, final_accounts = _browser_catalogs(canonical_path, context)
        if (
            final_fingerprint != canonical_fingerprint
            or final_assets != browser_assets
            or final_accounts != browser_accounts
        ):
            _abort("desktop_asset_activity_canonical_changed")
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
            "SELECT entity.account_id,entity.portfolio_id,revision.display_name,revision.account_type "
            "FROM account_entity entity JOIN current_account_revision revision USING(account_id) "
            "WHERE revision.status='active'"
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
        asset_ids = {row["asset_id"] for row in portfolio_events}
        history = []
        for row in reversed(portfolio_events):
            public_asset = _public_asset(row["asset_id"], assets, browser_assets)
            public_account = _public_account(
                row["account_id"], accounts, browser_accounts, portfolio["portfolio_id"]
            )
            related_account = None if row["related_account_id"] is None else _public_account(
                row["related_account_id"], accounts, browser_accounts, portfolio["portfolio_id"]
            )
            fifo = fifo_events.get(row["event_ref"])
            calculation_status = "fresh_completed" if fifo is not None else freshness
            history.append({
                "local_date": row["local_date"],
                "effective_at_utc": row["effective_at_utc"],
                "event_time_evidence": row["event_time_evidence"],
                "event_type": row["event_type"],
                "account_ref": public_account["account_ref"],
                "account_label": public_account["account_label"],
                "related_account_ref": None if related_account is None else related_account["account_ref"],
                "related_account_label": None if related_account is None else related_account["account_label"],
                "asset_ref": public_asset["asset_ref"],
                "asset_label": public_asset["asset_label"],
                "asset_type": public_asset["asset_type"],
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
                asset_id: next(iter({
                    row["basis_currency"] for row in portfolio_events if row["asset_id"] == asset_id
                }))
                for asset_id in asset_ids
            }
            for asset_id in sorted(asset_ids):
                public_asset = _public_asset(asset_id, assets, browser_assets)
                row = fifo_assets.get((portfolio["portfolio_id"], asset_id))
                if row is None or row.get("asset_type") != public_asset["asset_type"]:
                    _abort("desktop_asset_activity_fifo_invalid")
                positions.append({
                    "asset_ref": public_asset["asset_ref"],
                    "asset_label": public_asset["asset_label"],
                    "asset_type": public_asset["asset_type"],
                    "currency": currency_by_asset[asset_id],
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
            for (portfolio_id, account_id, asset_id), row in sorted(fifo_custody.items()):
                if portfolio_id != portfolio["portfolio_id"] or asset_id not in asset_ids:
                    continue
                public_asset = _public_asset(asset_id, assets, browser_assets)
                public_account = _public_account(
                    account_id, accounts, browser_accounts, portfolio["portfolio_id"]
                )
                custody.append({
                    "account_ref": public_account["account_ref"],
                    "account_label": public_account["account_label"],
                    "asset_ref": public_asset["asset_ref"],
                    "asset_label": public_asset["asset_label"],
                    "asset_type": public_asset["asset_type"],
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
    final_canonical_fingerprint, final_browser_assets, final_browser_accounts = _browser_catalogs(
        canonical_path, context
    )
    if (
        final_binding.get("status") != "available"
        or final_binding.get("generation_ref") != binding["generation_ref"]
        or final_binding.get("ledger_fingerprint") != binding["ledger_fingerprint"]
        or final_binding.get("activity_set_fingerprint") != binding["activity_set_fingerprint"]
        or final_canonical_fingerprint != canonical_fingerprint
        or final_browser_assets != browser_assets
        or final_browser_accounts != browser_accounts
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


__all__ = ["read_desktop_product_asset_activity_view_v4"]
