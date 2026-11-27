"""Pure explicit Cash coverage and balance semantics for ADR-100.

Cash balance events and Interest income remain orthogonal. Coverage is declared per
Account period and is never inferred from the presence or absence of rows.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONTRACT_VERSION = 1
COVERAGE_MODES = frozenset({"not_tracked", "income_only", "partial", "complete_reconciled"})
CASH_EVENT_TYPES = frozenset({"opening_balance", "deposit", "withdrawal", "transfer"})
FLOW_CLASSIFICATIONS = frozenset(
    {
        "not_applicable",
        "unclassified",
        "external_contribution",
        "external_withdrawal",
        "internal_unlinked",
        "investment_settlement",
        "income_receipt",
        "fee_or_tax_payment",
    }
)
FAILURE_CODES = frozenset(
    {
        "cash_coverage_account_invalid",
        "cash_coverage_amount_invalid",
        "cash_coverage_boundary_failed",
        "cash_coverage_complete_opening_required",
        "cash_coverage_complete_reconciliation_required",
        "cash_coverage_event_duplicate",
        "cash_coverage_event_outside_period",
        "cash_coverage_flow_classification_invalid",
        "cash_coverage_income_invalid",
        "cash_coverage_input_invalid",
        "cash_coverage_mode_invalid",
        "cash_coverage_period_overlap",
        "cash_coverage_reconciliation_mismatch",
        "cash_coverage_time_invalid",
        "cash_coverage_transfer_invalid",
    }
)
_REF = re.compile(r"[a-z]{2,8}_[a-f0-9]{16,64}")
_CURRENCY = re.compile(r"[A-Z]{3}")
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?")
_POSITIVE_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_LOCAL_TIME = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d")
_TIME_ZONE = re.compile(r"[A-Za-z0-9._+/-]{1,80}")


class CashCoverageV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("cash_coverage_error_code_unregistered")
        self.code = code
        super().__init__(code)


def cash_coverage_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise CashCoverageV1Error(code)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_keys(value: Any, keys: set[str], code: str = "cash_coverage_input_invalid") -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _abort(code)
    return value


def _ref(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        _abort("cash_coverage_input_invalid")
    return value


def _currency(value: Any) -> str:
    if not isinstance(value, str) or _CURRENCY.fullmatch(value) is None:
        _abort("cash_coverage_input_invalid")
    return value


def _date(value: Any, *, nullable: bool = False) -> date | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        _abort("cash_coverage_time_invalid")
    try:
        result = date.fromisoformat(value)
    except ValueError:
        _abort("cash_coverage_time_invalid")
    if result.isoformat() != value:
        _abort("cash_coverage_time_invalid")
    return result


def _utc(value: Any) -> str:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("cash_coverage_time_invalid")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _abort("cash_coverage_time_invalid")
    return value


def _time_evidence(
    mode: Any,
    local_date: date,
    local_time: Any,
    time_zone: Any,
    effective_at_utc: str,
) -> tuple[str, str | None, str | None]:
    if mode == "utc_only_legacy":
        if local_time is not None or time_zone is not None:
            _abort("cash_coverage_time_invalid")
        return mode, None, None
    if (
        mode != "exact_local_zone"
        or not isinstance(local_time, str)
        or _LOCAL_TIME.fullmatch(local_time) is None
        or not isinstance(time_zone, str)
        or _TIME_ZONE.fullmatch(time_zone) is None
    ):
        _abort("cash_coverage_time_invalid")
    try:
        zone = ZoneInfo(time_zone)
        naive = datetime.strptime(
            f"{local_date.isoformat()}T{local_time}", "%Y-%m-%dT%H:%M:%S"
        )
    except (ValueError, ZoneInfoNotFoundError):
        _abort("cash_coverage_time_invalid")
    candidates: set[str] = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        utc_value = aware.astimezone(timezone.utc)
        if utc_value.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc_value.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if effective_at_utc not in candidates:
        _abort("cash_coverage_time_invalid")
    return mode, local_time, time_zone


def _decimal(value: Any, *, positive: bool = False) -> Decimal:
    pattern = _POSITIVE_DECIMAL if positive else _DECIMAL
    if not isinstance(value, str) or pattern.fullmatch(value) is None or len(value) > 80:
        _abort("cash_coverage_amount_invalid")
    try:
        result = Decimal(value)
    except InvalidOperation:
        _abort("cash_coverage_amount_invalid")
    if not result.is_finite() or value == "-0" or (positive and result <= 0):
        _abort("cash_coverage_amount_invalid")
    return result


def _canonical(value: Decimal) -> str:
    if value == 0:
        return "0"
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result


def _sum(values: list[Decimal]) -> Decimal:
    with localcontext() as context:
        context.prec = 240
        return sum(values, Decimal(0))


def _catalog(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = payload.get("accounts")
    if not isinstance(items, list) or not items:
        _abort("cash_coverage_input_invalid")
    accounts: dict[str, dict[str, Any]] = {}
    for item in items:
        row = _exact_keys(item, {"account_ref", "cash_asset_ref", "currency"})
        account_ref = _ref(row["account_ref"])
        cash_asset_ref = _ref(row["cash_asset_ref"])
        currency = _currency(row["currency"])
        if account_ref in accounts:
            _abort("cash_coverage_account_invalid")
        accounts[account_ref] = {
            "account_ref": account_ref,
            "cash_asset_ref": cash_asset_ref,
            "currency": currency,
        }
    return accounts


def _periods(payload: dict[str, Any], accounts: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    items = payload.get("coverage_periods")
    if not isinstance(items, list) or not items:
        _abort("cash_coverage_input_invalid")
    periods: list[dict[str, Any]] = []
    by_account: dict[str, list[dict[str, Any]]] = {account_ref: [] for account_ref in accounts}
    seen_refs: set[str] = set()
    for item in items:
        row = _exact_keys(item, {"coverage_ref", "account_ref", "effective_from", "effective_to", "coverage_mode"})
        coverage_ref = _ref(row["coverage_ref"])
        account_ref = _ref(row["account_ref"])
        if coverage_ref in seen_refs or account_ref not in accounts:
            _abort("cash_coverage_account_invalid")
        seen_refs.add(coverage_ref)
        effective_from = _date(row["effective_from"])
        effective_to = _date(row["effective_to"], nullable=True)
        mode = row["coverage_mode"]
        if mode not in COVERAGE_MODES:
            _abort("cash_coverage_mode_invalid")
        if effective_to is not None and effective_to < effective_from:
            _abort("cash_coverage_time_invalid")
        period = {
            "coverage_ref": coverage_ref,
            "account_ref": account_ref,
            "effective_from": effective_from,
            "effective_to": effective_to,
            "coverage_mode": mode,
        }
        periods.append(period)
        by_account[account_ref].append(period)
    if any(not rows for rows in by_account.values()):
        _abort("cash_coverage_account_invalid")
    for account_ref, rows in by_account.items():
        rows.sort(key=lambda row: (row["effective_from"], row["coverage_ref"]))
        for left, right in zip(rows, rows[1:]):
            if left["effective_to"] is None or right["effective_from"] <= left["effective_to"]:
                _abort("cash_coverage_period_overlap")
    periods.sort(key=lambda row: (row["account_ref"], row["effective_from"], row["coverage_ref"]))
    return periods, by_account


def _find_period(by_account: dict[str, list[dict[str, Any]]], account_ref: str, local_date: date) -> dict[str, Any]:
    matches = [
        row
        for row in by_account.get(account_ref, [])
        if row["effective_from"] <= local_date and (row["effective_to"] is None or local_date <= row["effective_to"])
    ]
    if len(matches) != 1:
        _abort("cash_coverage_event_outside_period")
    return matches[0]


def _events(
    payload: dict[str, Any],
    accounts: dict[str, dict[str, Any]],
    by_account: dict[str, list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    items = payload.get("cash_events")
    if not isinstance(items, list):
        _abort("cash_coverage_input_invalid")
    events: list[dict[str, Any]] = []
    indexed: dict[str, dict[str, Any]] = {}
    for item in items:
        row = _exact_keys(
            item,
            {
                "cash_event_ref",
                "event_type",
                "account_ref",
                "related_account_ref",
                "cash_asset_ref",
                "event_time_evidence",
                "local_date",
                "local_time",
                "time_zone",
                "effective_at_utc",
                "amount_decimal",
                "flow_classification",
            },
        )
        event_ref = _ref(row["cash_event_ref"])
        if event_ref in indexed:
            _abort("cash_coverage_event_duplicate")
        event_type = row["event_type"]
        if event_type not in CASH_EVENT_TYPES:
            _abort("cash_coverage_input_invalid")
        account_ref = _ref(row["account_ref"])
        related_account_ref = _ref(row["related_account_ref"], nullable=True)
        cash_asset_ref = _ref(row["cash_asset_ref"])
        account = accounts.get(account_ref)
        local_date = _date(row["local_date"])
        effective_at_utc = _utc(row["effective_at_utc"])
        time_evidence, local_time, time_zone = _time_evidence(
            row["event_time_evidence"], local_date, row["local_time"],
            row["time_zone"], effective_at_utc,
        )
        classification = row["flow_classification"]
        if classification not in FLOW_CLASSIFICATIONS:
            _abort("cash_coverage_flow_classification_invalid")
        if account is None or account["cash_asset_ref"] != cash_asset_ref:
            _abort("cash_coverage_account_invalid")
        period = _find_period(by_account, account_ref, local_date)
        if period["coverage_mode"] not in {"partial", "complete_reconciled"}:
            _abort("cash_coverage_mode_invalid")
        amount = _decimal(row["amount_decimal"], positive=event_type != "opening_balance")
        if event_type == "transfer":
            related = accounts.get(related_account_ref)
            if (
                related is None
                or related_account_ref == account_ref
                or related["cash_asset_ref"] != cash_asset_ref
                or related["currency"] != account["currency"]
                or classification != "not_applicable"
            ):
                _abort("cash_coverage_transfer_invalid")
            destination_period = _find_period(by_account, related_account_ref, local_date)
            if destination_period["coverage_mode"] not in {"partial", "complete_reconciled"}:
                _abort("cash_coverage_mode_invalid")
        elif related_account_ref is not None:
            _abort("cash_coverage_transfer_invalid")
        if event_type == "opening_balance":
            if classification != "not_applicable":
                _abort("cash_coverage_flow_classification_invalid")
        elif event_type == "deposit":
            if classification not in {"unclassified", "external_contribution", "internal_unlinked", "investment_settlement", "income_receipt"}:
                _abort("cash_coverage_flow_classification_invalid")
        elif event_type == "withdrawal":
            if classification not in {"unclassified", "external_withdrawal", "internal_unlinked", "investment_settlement", "fee_or_tax_payment"}:
                _abort("cash_coverage_flow_classification_invalid")
        event = {
            "cash_event_ref": event_ref,
            "event_type": event_type,
            "account_ref": account_ref,
            "related_account_ref": related_account_ref,
            "cash_asset_ref": cash_asset_ref,
            "event_time_evidence": time_evidence,
            "local_date": local_date,
            "local_time": local_time,
            "time_zone": time_zone,
            "effective_at_utc": effective_at_utc,
            "amount": amount,
            "flow_classification": classification,
        }
        events.append(event)
        indexed[event_ref] = event
    events.sort(key=lambda row: (row["effective_at_utc"], row["cash_event_ref"]))
    return events, indexed


def _incomes(
    payload: dict[str, Any],
    accounts: dict[str, dict[str, Any]],
    by_account: dict[str, list[dict[str, Any]]],
    cash_events: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items = payload.get("income_events")
    if not isinstance(items, list):
        _abort("cash_coverage_input_invalid")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        row = _exact_keys(
            item,
            {
                "income_event_ref",
                "income_type",
                "account_ref",
                "cash_asset_ref",
                "local_date",
                "gross_income_decimal",
                "linked_cash_event_ref",
            },
        )
        income_ref = _ref(row["income_event_ref"])
        account_ref = _ref(row["account_ref"])
        asset_ref = _ref(row["cash_asset_ref"])
        local_date = _date(row["local_date"])
        link_ref = _ref(row["linked_cash_event_ref"], nullable=True)
        if income_ref in seen or row["income_type"] != "interest":
            _abort("cash_coverage_income_invalid")
        seen.add(income_ref)
        account = accounts.get(account_ref)
        if account is None or account["cash_asset_ref"] != asset_ref:
            _abort("cash_coverage_income_invalid")
        period = _find_period(by_account, account_ref, local_date)
        if period["coverage_mode"] == "not_tracked":
            _abort("cash_coverage_mode_invalid")
        gross = _decimal(row["gross_income_decimal"], positive=True)
        if link_ref is not None:
            linked = cash_events.get(link_ref)
            if (
                linked is None
                or linked["event_type"] != "deposit"
                or linked["account_ref"] != account_ref
                or linked["cash_asset_ref"] != asset_ref
            ):
                _abort("cash_coverage_income_invalid")
        result.append(
            {
                "income_event_ref": income_ref,
                "account_ref": account_ref,
                "cash_asset_ref": asset_ref,
                "local_date": local_date,
                "gross_income": gross,
                "linked_cash_event_ref": link_ref,
            }
        )
    result.sort(key=lambda row: (row["local_date"], row["income_event_ref"]))
    return result


def _reconciliations(
    payload: dict[str, Any],
    accounts: dict[str, dict[str, Any]],
    by_account: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    items = payload.get("reconciliations")
    if not isinstance(items, list):
        _abort("cash_coverage_input_invalid")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        row = _exact_keys(
            item,
            {"reconciliation_ref", "account_ref", "cash_asset_ref", "as_of_date", "observed_balance_decimal", "evidence_ref"},
        )
        reconciliation_ref = _ref(row["reconciliation_ref"])
        account_ref = _ref(row["account_ref"])
        asset_ref = _ref(row["cash_asset_ref"])
        evidence_ref = _ref(row["evidence_ref"])
        as_of_date = _date(row["as_of_date"])
        if reconciliation_ref in seen:
            _abort("cash_coverage_input_invalid")
        seen.add(reconciliation_ref)
        account = accounts.get(account_ref)
        if account is None or account["cash_asset_ref"] != asset_ref:
            _abort("cash_coverage_account_invalid")
        period = _find_period(by_account, account_ref, as_of_date)
        if period["coverage_mode"] != "complete_reconciled":
            _abort("cash_coverage_mode_invalid")
        result.append(
            {
                "reconciliation_ref": reconciliation_ref,
                "account_ref": account_ref,
                "cash_asset_ref": asset_ref,
                "as_of_date": as_of_date,
                "observed_balance": _decimal(row["observed_balance_decimal"]),
                "evidence_ref": evidence_ref,
            }
        )
    result.sort(key=lambda row: (row["account_ref"], row["as_of_date"], row["reconciliation_ref"]))
    return result


def _event_delta_for_account(event: dict[str, Any], account_ref: str) -> Decimal:
    if event["event_type"] == "opening_balance":
        return event["amount"] if event["account_ref"] == account_ref else Decimal(0)
    if event["event_type"] == "deposit":
        return event["amount"] if event["account_ref"] == account_ref else Decimal(0)
    if event["event_type"] == "withdrawal":
        return -event["amount"] if event["account_ref"] == account_ref else Decimal(0)
    if event["event_type"] == "transfer":
        if event["account_ref"] == account_ref:
            return -event["amount"]
        if event["related_account_ref"] == account_ref:
            return event["amount"]
    return Decimal(0)


def _validate_impl(payload: Any) -> dict[str, Any]:
    value = _exact_keys(payload, {"cash_coverage_version", "accounts", "coverage_periods", "cash_events", "income_events", "reconciliations"})
    if value["cash_coverage_version"] != CONTRACT_VERSION:
        _abort("cash_coverage_input_invalid")
    accounts = _catalog(value)
    periods, by_account = _periods(value, accounts)
    events, event_index = _events(value, accounts, by_account)
    incomes = _incomes(value, accounts, by_account, event_index)
    reconciliations = _reconciliations(value, accounts, by_account)
    period_results: list[dict[str, Any]] = []
    for period in periods:
        account_ref = period["account_ref"]
        from_date = period["effective_from"]
        to_date = period["effective_to"]
        period_events = [
            event
            for event in events
            if (event["account_ref"] == account_ref or event["related_account_ref"] == account_ref)
            and from_date <= event["local_date"]
            and (to_date is None or event["local_date"] <= to_date)
        ]
        period_incomes = [
            income
            for income in incomes
            if income["account_ref"] == account_ref
            and from_date <= income["local_date"]
            and (to_date is None or income["local_date"] <= to_date)
        ]
        openings = [event for event in period_events if event["event_type"] == "opening_balance" and event["account_ref"] == account_ref]
        mode = period["coverage_mode"]
        if mode in {"not_tracked", "income_only"} and period_events:
            _abort("cash_coverage_mode_invalid")
        if mode == "not_tracked" and period_incomes:
            _abort("cash_coverage_mode_invalid")
        if len(openings) > 1:
            _abort("cash_coverage_complete_opening_required")
        if openings and openings[0]["local_date"] != from_date:
            _abort("cash_coverage_complete_opening_required")
        period_reconciliations = [
            item
            for item in reconciliations
            if item["account_ref"] == account_ref
            and from_date <= item["as_of_date"]
            and (to_date is None or item["as_of_date"] <= to_date)
        ]
        opening_balance: Decimal | None = openings[0]["amount"] if openings else None
        computed_balance: Decimal | None = None
        observed_balance: Decimal | None = None
        as_of_date: date | None = None
        if mode == "complete_reconciled":
            if len(openings) != 1:
                _abort("cash_coverage_complete_opening_required")
            if not period_reconciliations:
                _abort("cash_coverage_complete_reconciliation_required")
            latest = period_reconciliations[-1]
            as_of_date = latest["as_of_date"]
            if to_date is not None and as_of_date != to_date:
                _abort("cash_coverage_complete_reconciliation_required")
            for reconciliation in period_reconciliations:
                reconciliation_events = [
                    event for event in period_events if event["local_date"] <= reconciliation["as_of_date"]
                ]
                reconciliation_balance = _sum(
                    [_event_delta_for_account(event, account_ref) for event in reconciliation_events]
                )
                if reconciliation_balance != reconciliation["observed_balance"]:
                    _abort("cash_coverage_reconciliation_mismatch")
            observed_balance = latest["observed_balance"]
            relevant = [event for event in period_events if event["local_date"] <= as_of_date]
            computed_balance = _sum([_event_delta_for_account(event, account_ref) for event in relevant])
            balance_status = "complete_reconciled"
        elif mode == "partial":
            as_of_date = max((event["local_date"] for event in period_events), default=to_date or from_date)
            if opening_balance is None:
                balance_status = "partial_delta_only"
            else:
                computed_balance = _sum([_event_delta_for_account(event, account_ref) for event in period_events])
                balance_status = "indicative_balance"
        else:
            balance_status = "not_tracked"
        movement_delta = _sum(
            [
                _event_delta_for_account(event, account_ref)
                for event in period_events
                if event["event_type"] != "opening_balance"
            ]
        )
        gross_income = _sum([income["gross_income"] for income in period_incomes])
        result = {
            "coverage_ref": period["coverage_ref"],
            "account_ref": account_ref,
            "cash_asset_ref": accounts[account_ref]["cash_asset_ref"],
            "currency": accounts[account_ref]["currency"],
            "effective_from": from_date.isoformat(),
            "effective_to": None if to_date is None else to_date.isoformat(),
            "coverage_mode": mode,
            "balance_status": balance_status,
            "as_of_date": None if as_of_date is None else as_of_date.isoformat(),
            "opening_balance_decimal": None if opening_balance is None else _canonical(opening_balance),
            "cash_movement_delta_decimal": _canonical(movement_delta),
            "computed_balance_decimal": None if computed_balance is None else _canonical(computed_balance),
            "observed_balance_decimal": None if observed_balance is None else _canonical(observed_balance),
            "cash_event_count": len(period_events),
            "income_event_count": len(period_incomes),
            "gross_interest_income_decimal": _canonical(gross_income),
            "income_cash_balance_effect_created": False,
            "completeness_inferred": False,
        }
        result["period_fingerprint"] = _fingerprint(result)
        period_results.append(result)
    transfer_events = [event for event in events if event["event_type"] == "transfer"]
    result = {
        "cash_coverage_version": CONTRACT_VERSION,
        "projection_status": "coverage_preview_completed",
        "period_count": len(period_results),
        "periods": period_results,
        "cash_event_count": len(events),
        "income_event_count": len(incomes),
        "linked_income_event_count": sum(item["linked_cash_event_ref"] is not None for item in incomes),
        "internal_transfer_count": len(transfer_events),
        "internal_transfer_portfolio_net_change_decimal": "0",
        "income_cash_balance_effect_created": False,
        "cash_guv_from_balance_events_created": False,
        "external_counter_accounts_created": False,
        "full_double_entry_created": False,
        "coverage_inferred": False,
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "private_data_access": False,
    }
    result["preview_fingerprint"] = _fingerprint(result)
    return result


def validate_cash_coverage_v1(payload: Any) -> dict[str, Any]:
    try:
        return _validate_impl(payload)
    except CashCoverageV1Error:
        raise
    except Exception:
        raise CashCoverageV1Error("cash_coverage_boundary_failed") from None


__all__ = [
    "CashCoverageV1Error",
    "cash_coverage_v1_error_codes",
    "validate_cash_coverage_v1",
]
