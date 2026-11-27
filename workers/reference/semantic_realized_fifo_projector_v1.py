"""Pure exact projector used by semantic_realized_fifo_v1.

This module deliberately has no SQLite or publication capability.  It preserves the
semantic contract on every event/movement/history row and never derives Cash for an
Asset Activity event.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Iterable, Mapping, Sequence

from workers.reference.semantic_realized_fifo_v1 import (
    ACTIVITY,
    OLD,
    TABLE_COLUMNS,
    Lot,
    Metric,
    abort,
    amount,
    consume,
    coverage,
    decimal_text,
    public_ref,
)


def _zero() -> Fraction:
    return Fraction(0)


def _metric(
    metrics: dict[tuple[str, str, str], Metric],
    account_id: str,
    asset_id: str,
    currency: str,
    semantic: str,
) -> Metric:
    key = (account_id, asset_id, currency)
    value = metrics.setdefault(key, Metric(account_id, asset_id, currency))
    value.semantics.add(semantic)
    return value


def _position(
    lots: Mapping[tuple[str, str], list[Lot]], metric: Metric, asset_type: str
) -> tuple[Fraction, Fraction]:
    if asset_type == "cash":
        return metric.cash, _zero()
    entries = [
        lot
        for lot in lots.get((metric.account_id, metric.asset_id), [])
        if lot.currency == metric.currency
    ]
    if any(lot.cost is None for lot in entries):
        return sum((lot.quantity for lot in entries), _zero()), None
    return (
        sum((lot.quantity for lot in entries), _zero()),
        sum((lot.cost for lot in entries if lot.cost is not None), _zero()),
    )


def _contracts_for_position(
    value: Metric, lots: Mapping[tuple[str, str], list[Lot]]
) -> set[str]:
    result = set(value.semantics)
    result.update(
        lot.acquisition_semantic_contract
        for lot in lots.get((value.account_id, value.asset_id), [])
        if lot.currency == value.currency
    )
    return result


def _validate_inventory_currency(
    currencies: dict[tuple[str, str], str], account: str, asset: str, currency: str
) -> None:
    key = (account, asset)
    existing = currencies.get(key)
    if existing is not None and existing != currency:
        abort("semantic_realized_fifo_currency_mismatch")
    currencies.setdefault(key, currency)


def _validate_cash_currency(currencies: dict[str, str], asset: str, currency: str) -> None:
    existing = currencies.get(asset)
    if existing is not None and existing != currency:
        abort("semantic_realized_fifo_currency_mismatch")
    currencies.setdefault(asset, currency)


def project_events(
    events: Sequence[Mapping[str, Any]],
    accounts: Mapping[str, Mapping[str, Any]],
    assets: Mapping[str, Mapping[str, Any]],
    context_fp: str,
) -> dict[str, list[dict[str, Any]]]:
    lots: dict[tuple[str, str], list[Lot]] = {}
    metrics: dict[tuple[str, str, str], Metric] = {}
    inventory_currencies: dict[tuple[str, str], str] = {}
    cash_currencies: dict[str, str] = {}
    segment_counters: dict[str, int] = {}
    event_rows: list[dict[str, Any]] = []
    movement_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []

    def ref(prefix: str, internal: str) -> str:
        return public_ref(prefix, context_fp, internal)

    def next_segment(origin: str, account: str) -> str:
        segment_counters[origin] = segment_counters.get(origin, 0) + 1
        return ref("lsg_", f"{origin}|{account}|{segment_counters[origin]}")

    def add_lot(
        event: Mapping[str, Any], event_ref: str, account: str, quantity: Fraction,
        cost: Fraction | None, acquired_date: str, acquired_utc: str | None,
    ) -> Lot:
        origin = ref("lot_", f"{event['semantic_contract']}|{event['fact_ref']}")
        order = (
            acquired_date,
            acquired_utc is not None,
            acquired_utc or "",
            event["semantic_contract"],
            event["fact_ref"],
        )
        current = lots.setdefault((account, event["asset_id"]), [])
        for existing in current:
            if existing.acquisition_local_date != acquired_date:
                continue
            if existing.acquisition_effective_at_utc is None or acquired_utc is None:
                abort("semantic_realized_fifo_order_evidence_required")
            if existing.acquisition_effective_at_utc == acquired_utc and ACTIVITY in {
                existing.acquisition_semantic_contract,
                event["semantic_contract"],
            }:
                abort("semantic_realized_fifo_order_evidence_required")
        lot = Lot(
            origin, next_segment(origin, account), event_ref,
            event["semantic_contract"], acquired_utc, acquired_date, order,
            event["asset_id"], event["currency"], quantity, cost,
        )
        current.append(lot)
        return lot

    def add_movement(
        event: Mapping[str, Any], event_ref: str, movement_type: str, lot: Lot,
        quantity: Fraction, cost: Fraction | None, source: str | None, destination: str | None,
    ) -> None:
        movement_rows.append(
            {
                "movement_sequence": str(len(movement_rows) + 1),
                "event_ref": event_ref,
                "movement_type": movement_type,
                "origin_lot_ref": lot.origin_ref,
                "lot_segment_ref": lot.segment_ref,
                "source_account_ref": None if source is None else ref("afr_", source),
                "destination_account_ref": None if destination is None else ref("afr_", destination),
                "asset_ref": ref("asf_", lot.asset_id),
                "currency": lot.currency,
                "quantity_decimal": decimal_text(quantity),
                "fifo_cost_decimal": None if cost is None else decimal_text(cost),
                "acquisition_event_ref": lot.acquisition_event_ref,
                "acquisition_effective_at_utc": lot.acquisition_effective_at_utc,
                "acquisition_local_date": lot.acquisition_local_date,
                "semantic_contract": event["semantic_contract"],
            }
        )

    def add_history(event: Mapping[str, Any], event_ref: str, account: str) -> None:
        value = _metric(
            metrics, account, event["asset_id"], event["currency"],
            event["semantic_contract"],
        )
        quantity, cost = _position(lots, value, assets[event["asset_id"]]["asset_type"])
        history_rows.append(
            {
                "history_sequence": str(len(history_rows) + 1),
                "event_ref": event_ref,
                "effective_at_utc": event["effective_at_utc"],
                "local_date": event["local_date"],
                "event_time_evidence": event["event_time_evidence"],
                "account_ref": ref("afr_", account),
                "asset_ref": ref("asf_", event["asset_id"]),
                "currency": event["currency"],
                "position_quantity_decimal": decimal_text(quantity),
                "fifo_cost_balance_decimal": None if cost is None else decimal_text(cost),
                "cumulative_realized_gross_gain_decimal": decimal_text(value.realized),
                "cumulative_gross_income_decimal": decimal_text(value.income),
                "cash_balance_decimal": decimal_text(value.cash),
                "semantic_contract": event["semantic_contract"],
            }
        )

    for event_index, event in enumerate(events, 1):
        event_type = event["event_type"]
        account = event["account_id"]
        related = event["related_account_id"]
        asset_id = event["asset_id"]
        asset_type = assets[asset_id]["asset_type"]
        semantic = event["semantic_contract"]
        currency = event["currency"]
        quantity = event["quantity"]
        raw_amount = amount(event)
        monetary_fee = event["monetary_fee"]
        asset_fee = event["asset_fee"]
        if event_type in {"adjustment", "other"}:
            abort("semantic_realized_fifo_event_unsupported")
        if semantic == ACTIVITY and asset_type == "cash":
            abort("semantic_realized_fifo_cash_event_invalid")
        if event_type == "reward" and asset_type != "crypto":
            abort("semantic_realized_fifo_cash_event_invalid")

        value = _metric(metrics, account, asset_id, currency, semantic)
        event_ref = ref("evr_", f"{semantic}|{event['fact_ref']}")
        basis_added = _zero()
        basis_consumed = _zero()
        proceeds = _zero()
        realized = _zero()
        income = _zero()
        distribution = event["distribution_value"] or _zero()
        cash_delta = _zero()
        holding_effect = "no_holding_change"
        history_accounts = [account]

        if asset_type == "cash":
            _validate_cash_currency(cash_currencies, asset_id, currency)
            if semantic != OLD or event_type not in {
                "deposit", "withdrawal", "transfer", "interest", "fee"
            } or raw_amount is None:
                abort("semantic_realized_fifo_cash_event_invalid")
            if event_type == "deposit":
                cash_delta = raw_amount - monetary_fee
                value.cash += cash_delta
                holding_effect = "cash_balance_change"
            elif event_type == "withdrawal":
                cash_delta = -(raw_amount + monetary_fee)
                value.cash += cash_delta
                holding_effect = "cash_balance_change"
            elif event_type == "transfer":
                if related is None or related == account:
                    abort("semantic_realized_fifo_source_invalid")
                destination = _metric(metrics, related, asset_id, currency, semantic)
                value.cash -= raw_amount + monetary_fee
                destination.cash += raw_amount
                cash_delta = -monetary_fee
                history_accounts.append(related)
                holding_effect = "transferred"
            elif event_type == "interest":
                income = raw_amount
                value.income += income
            else:
                if monetary_fee:
                    abort("semantic_realized_fifo_source_invalid")
                monetary_fee = raw_amount
                cash_delta = -raw_amount
                value.cash += cash_delta
                holding_effect = "cash_balance_change"
            value.fees += monetary_fee
        else:
            if event_type == "interest":
                abort("semantic_realized_fifo_cash_event_invalid")
            if event_type in {
                "buy", "sell", "deposit", "withdrawal", "transfer", "reward", "fee",
                "stock_dividend",
            }:
                _validate_inventory_currency(
                    inventory_currencies, account, asset_id, currency
                )
            if event_type == "transfer" and related is not None:
                _validate_inventory_currency(
                    inventory_currencies, related, asset_id, currency
                )

            if event_type in {"buy", "stock_dividend", "reward", "deposit"}:
                if quantity is None:
                    abort("semantic_realized_fifo_source_invalid")
                if semantic == ACTIVITY:
                    lot_basis = event["basis_created"]
                elif event_type == "buy":
                    if raw_amount is None:
                        abort("semantic_realized_fifo_source_invalid")
                    lot_basis = raw_amount + monetary_fee
                else:
                    lot_basis = raw_amount
                if lot_basis is None and not (
                    semantic == ACTIVITY
                    and event_type in {"stock_dividend", "reward", "deposit"}
                    and event["basis_missing"]
                ):
                    abort("semantic_realized_fifo_source_invalid")
                if event_type == "deposit" and semantic == ACTIVITY:
                    acquired_date = event["original_date"]
                    acquired_utc = event["original_utc"]
                else:
                    acquired_date = event["local_date"]
                    acquired_utc = event["effective_at_utc"]
                if acquired_date is None:
                    abort("semantic_realized_fifo_source_invalid")
                lot = add_lot(
                    event, event_ref, account, quantity, lot_basis,
                    acquired_date, acquired_utc,
                )
                if lot_basis is not None:
                    basis_added = lot_basis
                movement_type = {
                    "buy": "buy_acquisition",
                    "stock_dividend": "stock_dividend_acquisition",
                    "reward": "reward_acquisition",
                    "deposit": "provided_basis_deposit",
                }[event_type]
                add_movement(
                    event, event_ref, movement_type, lot, quantity, lot_basis,
                    None, account,
                )
                if event_type == "reward":
                    income = event["gross_income"] if semantic == ACTIVITY else raw_amount
                    if income is None:
                        abort("semantic_realized_fifo_source_invalid")
                    value.income += income
                if asset_fee:
                    for consumed_lot, take, cost in consume(
                        lots, account, asset_id, asset_fee
                    ):
                        if cost is not None:
                            basis_consumed += cost
                        add_movement(
                            event, event_ref, "asset_fee_consumption",
                            consumed_lot, take, cost, account, None,
                        )
                holding_effect = "acquired"

            elif event_type in {"sell", "withdrawal", "fee"}:
                if quantity is None:
                    abort("semantic_realized_fifo_source_invalid")
                principal_basis_complete = True
                for consumed_lot, take, cost in consume(
                    lots, account, asset_id, quantity
                ):
                    if cost is None:
                        principal_basis_complete = False
                    else:
                        basis_consumed += cost
                    add_movement(
                        event, event_ref,
                        "sell_consumption" if event_type == "sell" else
                        "withdrawal_consumption" if event_type == "withdrawal" else
                        "asset_fee_consumption",
                        consumed_lot, take, cost, account, None,
                    )
                if event_type == "sell":
                    if not principal_basis_complete:
                        abort("semantic_realized_fifo_basis_missing")
                    proceeds_value = (
                        event["net_proceeds"]
                        if semantic == ACTIVITY
                        else None if raw_amount is None else raw_amount - monetary_fee
                    )
                    if proceeds_value is None:
                        abort("semantic_realized_fifo_source_invalid")
                    proceeds = proceeds_value
                    realized = proceeds - basis_consumed
                    value.proceeds += proceeds
                    value.basis += basis_consumed
                    value.realized += realized
                elif event_type == "fee":
                    if semantic != OLD or raw_amount is None or monetary_fee:
                        abort("semantic_realized_fifo_source_invalid")
                    monetary_fee = raw_amount
                if event_type == "withdrawal" and asset_fee:
                    for consumed_lot, take, cost in consume(
                        lots, account, asset_id, asset_fee
                    ):
                        if cost is not None:
                            basis_consumed += cost
                        add_movement(
                            event, event_ref, "asset_fee_consumption",
                            consumed_lot, take, cost, account, None,
                        )
                holding_effect = "consumed"

            elif event_type == "transfer":
                if quantity is None or related is None or related == account:
                    abort("semantic_realized_fifo_source_invalid")
                chunks = consume(lots, account, asset_id, quantity)
                destination_lots = lots.setdefault((related, asset_id), [])
                for source_lot, take, cost in chunks:
                    moved = Lot(
                        source_lot.origin_ref,
                        next_segment(source_lot.origin_ref, related),
                        source_lot.acquisition_event_ref,
                        source_lot.acquisition_semantic_contract,
                        source_lot.acquisition_effective_at_utc,
                        source_lot.acquisition_local_date,
                        source_lot.order,
                        source_lot.asset_id,
                        source_lot.currency,
                        take,
                        cost,
                    )
                    destination_lots.append(moved)
                    add_movement(
                        event, event_ref, "internal_transfer", moved,
                        take, cost, account, related,
                    )
                if asset_fee:
                    for consumed_lot, take, cost in consume(
                        lots, account, asset_id, asset_fee
                    ):
                        if cost is not None:
                            basis_consumed += cost
                        add_movement(
                            event, event_ref, "asset_fee_consumption",
                            consumed_lot, take, cost, account, None,
                        )
                _metric(metrics, related, asset_id, currency, semantic)
                history_accounts.append(related)
                holding_effect = "transferred"

            elif event_type == "dividend":
                income = event["gross_income"] if semantic == ACTIVITY else raw_amount
                if income is None:
                    abort("semantic_realized_fifo_source_invalid")
                value.income += income
            else:
                abort("semantic_realized_fifo_event_unsupported")
            value.fees += monetary_fee

        displayed_amount = raw_amount
        if displayed_amount is None:
            displayed_amount = (
                event["gross_income"] or event["distribution_value"]
                or event["basis_created"]
            )
        event_rows.append(
            {
                "event_sequence": str(event_index),
                "event_ref": event_ref,
                "effective_at_utc": event["effective_at_utc"],
                "local_date": event["local_date"],
                "event_time_evidence": event["event_time_evidence"],
                "event_type": event_type,
                "account_ref": ref("afr_", account),
                "related_account_ref": None if related is None else ref("afr_", related),
                "asset_ref": ref("asf_", asset_id),
                "asset_type": asset_type,
                "currency": currency,
                "quantity_decimal": None if quantity is None else decimal_text(quantity),
                "amount_decimal": None if displayed_amount is None else decimal_text(displayed_amount),
                "fee_decimal": None if monetary_fee == 0 else decimal_text(monetary_fee),
                "asset_fee_quantity_decimal": None if asset_fee == 0 else decimal_text(asset_fee),
                "basis_added_decimal": decimal_text(basis_added),
                "basis_consumed_decimal": decimal_text(basis_consumed),
                "gross_proceeds_decimal": decimal_text(proceeds),
                "realized_gross_gain_decimal": decimal_text(realized),
                "gross_income_decimal": decimal_text(income),
                "distribution_value_decimal": decimal_text(distribution),
                "cash_balance_delta_decimal": decimal_text(cash_delta),
                "holding_effect": holding_effect,
                "projection_status": "completed",
                "semantic_contract": semantic,
                "coupled_transaction_fact": event["coupled_transaction_fact"],
                "automatic_cash_posting_created": event["automatic_cash_posting_created"],
            }
        )
        for history_account in history_accounts:
            add_history(event, event_ref, history_account)

    remaining_rows: list[dict[str, Any]] = []
    for (account, asset_id), entries in sorted(lots.items()):
        for lot in sorted(entries, key=lambda item: (item.order, item.segment_ref)):
            remaining_rows.append(
                {
                    "position_ref": ref("pos_", f"{account}|{asset_id}|{lot.currency}"),
                    "account_ref": ref("afr_", account),
                    "asset_ref": ref("asf_", asset_id),
                    "asset_type": assets[asset_id]["asset_type"],
                    "currency": lot.currency,
                    "origin_lot_ref": lot.origin_ref,
                    "lot_segment_ref": lot.segment_ref,
                    "acquisition_event_ref": lot.acquisition_event_ref,
                    "acquisition_effective_at_utc": lot.acquisition_effective_at_utc,
                    "acquisition_local_date": lot.acquisition_local_date,
                    "remaining_quantity_decimal": decimal_text(lot.quantity),
                    "remaining_fifo_cost_decimal": None if lot.cost is None else decimal_text(lot.cost),
                    "acquisition_semantic_contract": lot.acquisition_semantic_contract,
                }
            )

    summary_rows: list[dict[str, Any]] = []
    for key in sorted(metrics):
        value = metrics[key]
        quantity, cost = _position(lots, value, assets[value.asset_id]["asset_type"])
        summary_rows.append(
            {
                "position_ref": ref(
                    "pos_", f"{value.account_id}|{value.asset_id}|{value.currency}"
                ),
                "account_ref": ref("afr_", value.account_id),
                "asset_ref": ref("asf_", value.asset_id),
                "asset_type": assets[value.asset_id]["asset_type"],
                "currency": value.currency,
                "remaining_quantity_decimal": decimal_text(quantity),
                "remaining_fifo_cost_decimal": None if cost is None else decimal_text(cost),
                "realized_gross_proceeds_decimal": decimal_text(value.proceeds),
                "realized_fifo_cost_decimal": decimal_text(value.basis),
                "realized_gross_gain_decimal": decimal_text(value.realized),
                "gross_income_decimal": decimal_text(value.income),
                "fee_total_decimal": decimal_text(value.fees),
                "cash_balance_decimal": decimal_text(value.cash),
                "semantic_contract_coverage": coverage(
                    _contracts_for_position(value, lots)
                ),
            }
        )

    currency_rows: list[dict[str, Any]] = []
    for currency in sorted({value.currency for value in metrics.values()}):
        scoped = [value for value in metrics.values() if value.currency == currency]
        semantic_values: set[str] = set()
        for value in scoped:
            semantic_values.update(_contracts_for_position(value, lots))
        currency_rows.append(
            {
                "currency": currency,
                "realized_gross_proceeds_decimal": decimal_text(
                    sum((value.proceeds for value in scoped), _zero())
                ),
                "realized_fifo_cost_decimal": decimal_text(
                    sum((value.basis for value in scoped), _zero())
                ),
                "realized_gross_gain_decimal": decimal_text(
                    sum((value.realized for value in scoped), _zero())
                ),
                "gross_income_decimal": decimal_text(
                    sum((value.income for value in scoped), _zero())
                ),
                "fee_total_decimal": decimal_text(
                    sum((value.fees for value in scoped), _zero())
                ),
                "cash_balance_decimal": decimal_text(
                    sum((value.cash for value in scoped), _zero())
                ),
                "cross_currency_aggregation": "not_applied",
                "semantic_contract_coverage": coverage(semantic_values),
            }
        )

    result = {
        "event-results.csv": event_rows,
        "lot-movements.csv": movement_rows,
        "remaining-lots.csv": remaining_rows,
        "position-history.csv": history_rows,
        "position-summary.csv": summary_rows,
        "currency-summary.csv": currency_rows,
    }
    if set(result) != set(TABLE_COLUMNS):
        abort("semantic_realized_fifo_boundary_failed")
    return result
