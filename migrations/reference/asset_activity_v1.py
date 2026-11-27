"""Pure Asset-centric event candidate normalization for ADR-100.

This evaluator validates event-specific amount, basis, custody and time evidence and
produces exact effect descriptors. It does not persist events or perform the full
FIFO projection; Realized FIFO remains the authoritative lot oracle.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib
import json
import re
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONTRACT_VERSION = 1
SUPPORTED_EVENT_TYPES = frozenset(
    {"buy", "sell", "dividend", "stock_dividend", "reward", "deposit", "withdrawal", "transfer"}
)
SUPPORTED_ASSET_TYPES = frozenset(
    {"equity", "etf", "fund", "bond", "derivative", "crypto", "commodity", "fx", "index", "other"}
)
SUPPORTED_ACCOUNT_TYPES = frozenset({"securities", "crypto_wallet", "other"})
AMOUNT_INPUT_MODES = frozenset({"quantity_unit_price", "gross_total", "not_applicable"})
BASIS_EVIDENCE_MODES = frozenset(
    {"derived_trade", "valuation_confirmed_as_basis", "provided_basis", "basis_missing", "not_applicable"}
)
TIME_EVIDENCE_MODES = frozenset({"exact", "date_only"})
ORIGINAL_TIME_EVIDENCE_MODES = frozenset({"exact", "date_only", "not_applicable"})
MOVEMENT_CONTEXT_CODES = frozenset(
    {"not_applicable", "unclassified", "gift", "inheritance", "debt_settlement", "donation", "payment", "custody_exit", "other"}
)
FAILURE_CODES = frozenset(
    {
        "asset_activity_account_invalid",
        "asset_activity_amount_invalid",
        "asset_activity_asset_invalid",
        "asset_activity_basis_invalid",
        "asset_activity_boundary_failed",
        "asset_activity_event_duplicate",
        "asset_activity_event_type_invalid",
        "asset_activity_input_invalid",
        "asset_activity_inventory_effect_invalid",
        "asset_activity_movement_context_invalid",
        "asset_activity_time_invalid",
    }
)
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?")
_SIGNED_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?")
_REF = re.compile(r"[a-z]{2,8}_[a-f0-9]{16,64}")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
_LOCAL_TIME = re.compile(r"\d{2}:\d{2}:\d{2}")


class AssetActivityV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("asset_activity_error_code_unregistered")
        self.code = code
        super().__init__(code)


def asset_activity_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise AssetActivityV1Error(code)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _exact_keys(value: Any, keys: set[str], code: str = "asset_activity_input_invalid") -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        _abort(code)
    return value


def _ref(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        _abort("asset_activity_input_invalid")
    return value


def _decimal(value: Any, *, nullable: bool = False, positive: bool = False) -> Decimal | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _DECIMAL.fullmatch(value) is None or len(value) > 80:
        _abort("asset_activity_amount_invalid")
    try:
        result = Decimal(value)
    except InvalidOperation:
        _abort("asset_activity_amount_invalid")
    if not result.is_finite() or (positive and result <= 0):
        _abort("asset_activity_amount_invalid")
    return result


def _decimal_scale(value: Any) -> int:
    if value is None:
        return 0
    return len(str(value).partition(".")[2])


def _canonical(value: Decimal) -> str:
    if value == 0:
        return "0"
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    if result == "-0":
        return "0"
    if _SIGNED_DECIMAL.fullmatch(result) is None:
        _abort("asset_activity_amount_invalid")
    return result


def _multiply(left: Decimal, right: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 240
        return left * right


def _add(*values: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 240
        return sum(values, Decimal(0))


def _parse_date(value: Any) -> date:
    if not isinstance(value, str):
        _abort("asset_activity_time_invalid")
    try:
        result = date.fromisoformat(value)
    except ValueError:
        _abort("asset_activity_time_invalid")
    if result.isoformat() != value:
        _abort("asset_activity_time_invalid")
    return result


def _parse_local_time(value: Any) -> time:
    if not isinstance(value, str) or _LOCAL_TIME.fullmatch(value) is None:
        _abort("asset_activity_time_invalid")
    try:
        result = time.fromisoformat(value)
    except ValueError:
        _abort("asset_activity_time_invalid")
    if result.strftime("%H:%M:%S") != value:
        _abort("asset_activity_time_invalid")
    return result


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("asset_activity_time_invalid")
    try:
        result = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort("asset_activity_time_invalid")
    return result


def _zone(value: Any) -> ZoneInfo:
    if not isinstance(value, str) or not value or len(value) > 80:
        _abort("asset_activity_time_invalid")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        _abort("asset_activity_time_invalid")


def _unique_local_utc(local_date: date, local_time: time, zone: ZoneInfo) -> datetime:
    naive = datetime.combine(local_date, local_time)
    candidates: set[datetime] = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        candidate = aware.astimezone(timezone.utc)
        if candidate.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(candidate)
    if len(candidates) != 1:
        _abort("asset_activity_time_invalid")
    return next(iter(candidates))


def _time_evidence(
    local_date_value: Any,
    local_time_value: Any,
    zone_value: Any,
    utc_value: Any,
    evidence_mode: Any,
    *,
    original: bool = False,
) -> tuple[date | None, datetime | None]:
    allowed = ORIGINAL_TIME_EVIDENCE_MODES if original else TIME_EVIDENCE_MODES
    if evidence_mode not in allowed:
        _abort("asset_activity_time_invalid")
    if evidence_mode == "not_applicable":
        if any(value is not None for value in (local_date_value, local_time_value, zone_value, utc_value)):
            _abort("asset_activity_time_invalid")
        return None, None
    local_date = _parse_date(local_date_value)
    zone = _zone(zone_value)
    if evidence_mode == "date_only":
        if local_time_value is not None or utc_value is not None:
            _abort("asset_activity_time_invalid")
        return local_date, None
    local_time = _parse_local_time(local_time_value)
    utc = _parse_utc(utc_value)
    if _unique_local_utc(local_date, local_time, zone) != utc:
        _abort("asset_activity_time_invalid")
    return local_date, utc


def _catalog(payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    accounts_value = payload.get("accounts")
    assets_value = payload.get("assets")
    if not isinstance(accounts_value, list) or not accounts_value or not isinstance(assets_value, list) or not assets_value:
        _abort("asset_activity_input_invalid")
    accounts: dict[str, dict[str, Any]] = {}
    for item in accounts_value:
        row = _exact_keys(item, {"account_ref", "account_type"})
        account_ref = _ref(row["account_ref"])
        if row["account_type"] not in SUPPORTED_ACCOUNT_TYPES or account_ref in accounts:
            _abort("asset_activity_account_invalid")
        accounts[account_ref] = row
    assets: dict[str, dict[str, Any]] = {}
    for item in assets_value:
        row = _exact_keys(item, {"asset_ref", "asset_type", "quantity_scale"})
        asset_ref = _ref(row["asset_ref"])
        scale = row["quantity_scale"]
        if (
            row["asset_type"] not in SUPPORTED_ASSET_TYPES
            or isinstance(scale, bool)
            or not isinstance(scale, int)
            or not 0 <= scale <= 24
            or asset_ref in assets
        ):
            _abort("asset_activity_asset_invalid")
        assets[asset_ref] = row
    return accounts, assets


def _account_asset_compatible(account_type: str, asset_type: str) -> bool:
    if asset_type == "crypto":
        return account_type in {"crypto_wallet", "securities", "other"}
    return account_type in {"securities", "other"}


def _all_null(event: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return all(event[field] is None for field in fields)


def _normalize_event(
    event: Any,
    accounts: dict[str, dict[str, Any]],
    assets: dict[str, dict[str, Any]],
    basis_currency: str,
) -> dict[str, Any]:
    keys = {
        "event_ref",
        "event_type",
        "account_ref",
        "related_account_ref",
        "asset_ref",
        "source_asset_ref",
        "event_time_evidence",
        "local_date",
        "local_time",
        "time_zone",
        "effective_at_utc",
        "original_acquired_time_evidence",
        "original_acquired_local_date",
        "original_acquired_local_time",
        "original_acquired_time_zone",
        "original_acquired_at_utc",
        "amount_input_mode",
        "basis_evidence_mode",
        "quantity_decimal",
        "eligible_quantity_decimal",
        "unit_price_decimal",
        "gross_amount_decimal",
        "monetary_fee_decimal",
        "asset_fee_quantity_decimal",
        "provided_basis_decimal",
        "movement_context_code",
    }
    row = _exact_keys(event, keys)
    event_ref = _ref(row["event_ref"])
    event_type = row["event_type"]
    if event_type not in SUPPORTED_EVENT_TYPES:
        _abort("asset_activity_event_type_invalid")
    account_ref = _ref(row["account_ref"])
    related_account_ref = _ref(row["related_account_ref"], nullable=True)
    asset_ref = _ref(row["asset_ref"])
    source_asset_ref = _ref(row["source_asset_ref"], nullable=True)
    account = accounts.get(account_ref)
    asset = assets.get(asset_ref)
    if account is None or asset is None:
        _abort("asset_activity_input_invalid")
    if not _account_asset_compatible(account["account_type"], asset["asset_type"]):
        _abort("asset_activity_account_invalid")
    if event_type == "transfer":
        related = accounts.get(related_account_ref)
        if related is None or related_account_ref == account_ref or not _account_asset_compatible(related["account_type"], asset["asset_type"]):
            _abort("asset_activity_account_invalid")
    elif related_account_ref is not None:
        _abort("asset_activity_account_invalid")
    if event_type == "stock_dividend":
        source_asset = assets.get(source_asset_ref)
        if source_asset is None:
            _abort("asset_activity_asset_invalid")
    elif source_asset_ref is not None:
        _abort("asset_activity_asset_invalid")

    movement_date, movement_utc = _time_evidence(
        row["local_date"],
        row["local_time"],
        row["time_zone"],
        row["effective_at_utc"],
        row["event_time_evidence"],
    )
    original_date, original_utc = _time_evidence(
        row["original_acquired_local_date"],
        row["original_acquired_local_time"],
        row["original_acquired_time_zone"],
        row["original_acquired_at_utc"],
        row["original_acquired_time_evidence"],
        original=True,
    )
    if event_type == "deposit":
        if row["original_acquired_time_evidence"] == "not_applicable" or original_date is None:
            _abort("asset_activity_time_invalid")
        if original_date > movement_date or (original_utc is not None and movement_utc is not None and original_utc > movement_utc):
            _abort("asset_activity_time_invalid")
    elif row["original_acquired_time_evidence"] != "not_applicable":
        _abort("asset_activity_time_invalid")

    amount_mode = row["amount_input_mode"]
    basis_mode = row["basis_evidence_mode"]
    movement_context = row["movement_context_code"]
    if amount_mode not in AMOUNT_INPUT_MODES or basis_mode not in BASIS_EVIDENCE_MODES:
        _abort("asset_activity_input_invalid")
    if movement_context not in MOVEMENT_CONTEXT_CODES:
        _abort("asset_activity_movement_context_invalid")
    if event_type in {"deposit", "withdrawal"}:
        if movement_context == "not_applicable":
            _abort("asset_activity_movement_context_invalid")
    elif movement_context != "not_applicable":
        _abort("asset_activity_movement_context_invalid")

    quantity = _decimal(row["quantity_decimal"], nullable=True, positive=True)
    eligible_quantity = _decimal(row["eligible_quantity_decimal"], nullable=True, positive=True)
    unit_price = _decimal(row["unit_price_decimal"], nullable=True, positive=True)
    supplied_gross = _decimal(row["gross_amount_decimal"], nullable=True, positive=True)
    monetary_fee = _decimal(row["monetary_fee_decimal"], nullable=True, positive=True)
    asset_fee = _decimal(row["asset_fee_quantity_decimal"], nullable=True, positive=True)
    provided_basis = _decimal(row["provided_basis_decimal"], nullable=True, positive=True)
    if any(
        _decimal_scale(row[field]) > asset["quantity_scale"]
        for field in ("quantity_decimal", "asset_fee_quantity_decimal")
        if row[field] is not None
    ):
        _abort("asset_activity_amount_invalid")
    if eligible_quantity is not None and _decimal_scale(row["eligible_quantity_decimal"]) > asset["quantity_scale"]:
        _abort("asset_activity_amount_invalid")

    gross: Decimal | None = None
    if amount_mode == "quantity_unit_price":
        if event_type == "dividend":
            amount_quantity = eligible_quantity
        elif event_type == "reward" and quantity is not None:
            amount_quantity = _add(quantity, -(asset_fee or Decimal(0)))
        else:
            amount_quantity = quantity
        if amount_quantity is None or unit_price is None or supplied_gross is not None:
            _abort("asset_activity_amount_invalid")
        gross = _multiply(amount_quantity, unit_price)
    elif amount_mode == "gross_total":
        if supplied_gross is None or unit_price is not None:
            _abort("asset_activity_amount_invalid")
        gross = supplied_gross
    elif any(value is not None for value in (unit_price, supplied_gross)):
        _abort("asset_activity_amount_invalid")

    inventory_effect: str
    fifo_effect: str
    quantity_change = Decimal(0)
    basis_created: Decimal | None = None
    trade_proceeds: Decimal | None = None
    gross_income: Decimal | None = None
    distribution_value: Decimal | None = None
    income_status = "not_applicable"
    outgoing_receipt = False
    transfer_carry = False
    original_required = False

    if event_type == "buy":
        if amount_mode != "quantity_unit_price" or basis_mode != "derived_trade" or eligible_quantity is not None or asset_fee is not None or provided_basis is not None:
            _abort("asset_activity_input_invalid")
        inventory_effect, fifo_effect = "increase", "create_lot"
        quantity_change = quantity
        basis_created = _add(gross, monetary_fee or Decimal(0))
    elif event_type == "sell":
        if amount_mode != "quantity_unit_price" or basis_mode != "not_applicable" or eligible_quantity is not None or asset_fee is not None or provided_basis is not None:
            _abort("asset_activity_input_invalid")
        inventory_effect, fifo_effect = "decrease", "consume_fifo"
        quantity_change = -quantity
        trade_proceeds = _add(gross, -(monetary_fee or Decimal(0)))
    elif event_type == "dividend":
        if basis_mode != "not_applicable" or quantity is not None or monetary_fee is not None or asset_fee is not None or provided_basis is not None:
            _abort("asset_activity_input_invalid")
        if amount_mode == "quantity_unit_price":
            if eligible_quantity is None:
                _abort("asset_activity_amount_invalid")
        elif amount_mode == "gross_total":
            if eligible_quantity is not None and eligible_quantity <= 0:
                _abort("asset_activity_amount_invalid")
        else:
            _abort("asset_activity_amount_invalid")
        inventory_effect, fifo_effect = "none", "none"
        gross_income = gross
        income_status = "recognized_dividend_income"
    elif event_type == "stock_dividend":
        if amount_mode != "quantity_unit_price" or basis_mode not in {"valuation_confirmed_as_basis", "provided_basis", "basis_missing"} or eligible_quantity is not None or monetary_fee is not None or asset_fee is not None:
            _abort("asset_activity_input_invalid")
        if basis_mode == "valuation_confirmed_as_basis":
            if provided_basis is not None:
                _abort("asset_activity_basis_invalid")
            basis_created = gross
        elif basis_mode == "provided_basis":
            if provided_basis is None:
                _abort("asset_activity_basis_invalid")
            basis_created = provided_basis
        elif provided_basis is not None:
            _abort("asset_activity_basis_invalid")
        inventory_effect, fifo_effect = "increase", "create_lot"
        quantity_change = quantity
        distribution_value = gross
        income_status = "tax_classification_required"
    elif event_type == "reward":
        if amount_mode not in {"quantity_unit_price", "gross_total"} or basis_mode not in {"valuation_confirmed_as_basis", "provided_basis", "basis_missing"} or eligible_quantity is not None or monetary_fee is not None:
            _abort("asset_activity_input_invalid")
        if asset["asset_type"] != "crypto":
            _abort("asset_activity_asset_invalid")
        if asset_fee is not None and asset_fee >= quantity:
            _abort("asset_activity_inventory_effect_invalid")
        if basis_mode == "valuation_confirmed_as_basis":
            if provided_basis is not None:
                _abort("asset_activity_basis_invalid")
            basis_created = gross
        elif basis_mode == "provided_basis":
            if provided_basis is None:
                _abort("asset_activity_basis_invalid")
            basis_created = provided_basis
        elif provided_basis is not None:
            _abort("asset_activity_basis_invalid")
        inventory_effect, fifo_effect = "increase", "create_lot_then_consume_fee"
        quantity_change = _add(quantity, -(asset_fee or Decimal(0)))
        gross_income = gross
        income_status = "recognized_reward_income"
    elif event_type == "deposit":
        if quantity is None or eligible_quantity is not None or monetary_fee is not None or asset_fee is not None or basis_mode not in {"provided_basis", "basis_missing"}:
            _abort("asset_activity_input_invalid")
        if basis_mode == "basis_missing":
            if amount_mode != "not_applicable" or provided_basis is not None:
                _abort("asset_activity_basis_invalid")
        else:
            if amount_mode == "quantity_unit_price":
                if provided_basis is not None:
                    _abort("asset_activity_basis_invalid")
                basis_created = gross
            elif amount_mode == "gross_total":
                if provided_basis is not None or gross is None:
                    _abort("asset_activity_basis_invalid")
                basis_created = gross
            elif amount_mode == "not_applicable" and provided_basis is not None:
                basis_created = provided_basis
            else:
                _abort("asset_activity_basis_invalid")
        inventory_effect, fifo_effect = "increase", "create_carried_lot"
        quantity_change = quantity
        original_required = True
    elif event_type == "withdrawal":
        if amount_mode != "not_applicable" or basis_mode != "not_applicable" or quantity is None or eligible_quantity is not None or monetary_fee is not None or provided_basis is not None:
            _abort("asset_activity_input_invalid")
        inventory_effect, fifo_effect = "decrease", "consume_fifo_and_emit_receipt"
        quantity_change = -_add(quantity, asset_fee or Decimal(0))
        outgoing_receipt = True
    else:
        if amount_mode != "not_applicable" or basis_mode != "not_applicable" or quantity is None or eligible_quantity is not None or provided_basis is not None:
            _abort("asset_activity_input_invalid")
        inventory_effect, fifo_effect = ("decrease" if asset_fee is not None else "preserve"), "carry_lots_then_consume_fee"
        quantity_change = -(asset_fee or Decimal(0))
        transfer_carry = True

    effect = {
        "event_ref": event_ref,
        "event_type": event_type,
        "account_ref": account_ref,
        "related_account_ref": related_account_ref,
        "asset_ref": asset_ref,
        "source_asset_ref": source_asset_ref,
        "event_time_evidence": row["event_time_evidence"],
        "original_acquired_time_evidence": row["original_acquired_time_evidence"],
        "amount_input_mode": amount_mode,
        "basis_evidence_mode": basis_mode,
        "movement_context_code": movement_context,
        "inventory_effect_code": inventory_effect,
        "fifo_effect_code": fifo_effect,
        "portfolio_quantity_change_decimal": _canonical(quantity_change),
        "gross_economic_amount_decimal": None if gross is None else _canonical(gross),
        "fifo_basis_created_decimal": None if basis_created is None else _canonical(basis_created),
        "net_trade_proceeds_decimal": None if trade_proceeds is None else _canonical(trade_proceeds),
        "gross_income_decimal": None if gross_income is None else _canonical(gross_income),
        "distribution_value_decimal": None if distribution_value is None else _canonical(distribution_value),
        "income_recognition_status": income_status,
        "monetary_fee_decimal": None if monetary_fee is None else _canonical(monetary_fee),
        "asset_fee_quantity_decimal": None if asset_fee is None else _canonical(asset_fee),
        "outgoing_lot_receipt_required": outgoing_receipt,
        "transfer_lot_carry_required": transfer_carry,
        "original_acquisition_evidence_required": original_required,
        "cash_posting_created": False,
        "tax_classification_inferred": False,
        "provider_price_used": False,
        "basis_currency": basis_currency,
    }
    effect["effect_fingerprint"] = _fingerprint(effect)
    return effect


def _validate_impl(payload: Any) -> dict[str, Any]:
    value = _exact_keys(payload, {"asset_activity_version", "basis_currency", "accounts", "assets", "events"})
    if value["asset_activity_version"] != CONTRACT_VERSION:
        _abort("asset_activity_input_invalid")
    basis_currency = value["basis_currency"]
    if not isinstance(basis_currency, str) or re.fullmatch(r"[A-Z]{3}", basis_currency) is None:
        _abort("asset_activity_input_invalid")
    accounts, assets = _catalog(value)
    events_value = value["events"]
    if not isinstance(events_value, list) or not events_value:
        _abort("asset_activity_input_invalid")
    events: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in events_value:
        effect = _normalize_event(item, accounts, assets, basis_currency)
        if effect["event_ref"] in seen:
            _abort("asset_activity_event_duplicate")
        seen.add(effect["event_ref"])
        events.append(effect)
    result = {
        "asset_activity_version": CONTRACT_VERSION,
        "projection_status": "semantic_preview_completed",
        "event_count": len(events),
        "event_effects": events,
        "cash_posting_count": 0,
        "provider_price_use_count": 0,
        "tax_classification_inference_count": 0,
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "private_data_access": False,
    }
    result["preview_fingerprint"] = _fingerprint(result)
    return result


def validate_asset_activity_v1(payload: Any) -> dict[str, Any]:
    try:
        return _validate_impl(payload)
    except AssetActivityV1Error:
        raise
    except Exception:
        raise AssetActivityV1Error("asset_activity_boundary_failed") from None


def _fraction_from_decimal(value: Any) -> Fraction:
    decimal = _decimal(value, positive=True)
    return Fraction(decimal)


def _fraction_decimal_required(value: Fraction) -> str:
    result = _terminating_fraction(value)
    if result is None:
        _abort("asset_activity_amount_invalid")
    return result


def _terminating_fraction(value: Fraction) -> str | None:
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    if denominator != 1:
        return None
    precision = max(len(str(abs(value.numerator))), len(str(value.denominator))) + 20
    with localcontext() as context:
        context.prec = precision
        return _canonical(Decimal(value.numerator) / Decimal(value.denominator))


def fifo_cost_average_evidence_v1(remaining_lots: Any) -> dict[str, Any]:
    try:
        if not isinstance(remaining_lots, list):
            _abort("asset_activity_input_invalid")
        quantity = Fraction(0)
        basis = Fraction(0)
        basis_missing = False
        for item in remaining_lots:
            row = _exact_keys(item, {"quantity_decimal", "basis_decimal", "basis_status"})
            lot_quantity = _fraction_from_decimal(row["quantity_decimal"])
            quantity += lot_quantity
            if row["basis_status"] == "basis_missing":
                if row["basis_decimal"] is not None:
                    _abort("asset_activity_basis_invalid")
                basis_missing = True
            elif row["basis_status"] == "completed":
                basis += _fraction_from_decimal(row["basis_decimal"])
            else:
                _abort("asset_activity_basis_invalid")
        if quantity == 0:
            result = {
                "cost_average_status": "empty_position",
                "remaining_quantity_decimal": "0",
                "remaining_fifo_basis_decimal": "0",
                "cost_average_decimal": None,
                "cost_average_numerator_integer": None,
                "cost_average_denominator_integer": None,
            }
        elif basis_missing:
            result = {
                "cost_average_status": "basis_missing",
                "remaining_quantity_decimal": _terminating_fraction(quantity),
                "remaining_fifo_basis_decimal": None,
                "cost_average_decimal": None,
                "cost_average_numerator_integer": None,
                "cost_average_denominator_integer": None,
            }
        else:
            average = basis / quantity
            decimal_average = _terminating_fraction(average)
            result = {
                "cost_average_status": "exact_decimal" if decimal_average is not None else "exact_ratio",
                "remaining_quantity_decimal": _terminating_fraction(quantity),
                "remaining_fifo_basis_decimal": _terminating_fraction(basis),
                "cost_average_decimal": decimal_average,
                "cost_average_numerator_integer": str(average.numerator),
                "cost_average_denominator_integer": str(average.denominator),
            }
            if result["remaining_quantity_decimal"] is None or result["remaining_fifo_basis_decimal"] is None:
                _abort("asset_activity_amount_invalid")
        result["cost_average_fingerprint"] = _fingerprint(result)
        return result
    except AssetActivityV1Error:
        raise
    except Exception:
        raise AssetActivityV1Error("asset_activity_boundary_failed") from None


def fifo_cost_average_after_sale_v1(open_lots: Any, sell_quantity_decimal: Any) -> dict[str, Any]:
    """Focused FIFO/Cost-Average proof; the full Realized FIFO oracle remains authoritative."""
    try:
        if not isinstance(open_lots, list) or not open_lots:
            _abort("asset_activity_input_invalid")
        normalized: list[dict[str, Fraction]] = []
        for item in open_lots:
            row = _exact_keys(item, {"quantity_decimal", "basis_decimal", "basis_status"})
            if row["basis_status"] != "completed" or row["basis_decimal"] is None:
                _abort("asset_activity_basis_invalid")
            normalized.append(
                {
                    "quantity": _fraction_from_decimal(row["quantity_decimal"]),
                    "basis": _fraction_from_decimal(row["basis_decimal"]),
                }
            )
        before = fifo_cost_average_evidence_v1(open_lots)
        sell_quantity = _fraction_from_decimal(sell_quantity_decimal)
        remaining_to_sell = sell_quantity
        consumed_basis = Fraction(0)
        for lot in normalized:
            if remaining_to_sell == 0:
                break
            take = min(lot["quantity"], remaining_to_sell)
            basis_take = lot["basis"] * take / lot["quantity"]
            lot["quantity"] -= take
            lot["basis"] -= basis_take
            remaining_to_sell -= take
            consumed_basis += basis_take
        if remaining_to_sell != 0:
            _abort("asset_activity_inventory_effect_invalid")
        remaining_lots = [
            {
                "quantity_decimal": _fraction_decimal_required(lot["quantity"]),
                "basis_decimal": _fraction_decimal_required(lot["basis"]),
                "basis_status": "completed",
            }
            for lot in normalized
            if lot["quantity"] != 0
        ]
        after = fifo_cost_average_evidence_v1(remaining_lots)
        result = {
            "fifo_applied": True,
            "sold_quantity_decimal": _fraction_decimal_required(sell_quantity),
            "consumed_fifo_basis_decimal": _fraction_decimal_required(consumed_basis),
            "before": before,
            "after": after,
        }
        result["fifo_cost_average_fingerprint"] = _fingerprint(result)
        return result
    except AssetActivityV1Error:
        raise
    except Exception:
        raise AssetActivityV1Error("asset_activity_boundary_failed") from None


__all__ = [
    "AssetActivityV1Error",
    "asset_activity_v1_error_codes",
    "fifo_cost_average_after_sale_v1",
    "fifo_cost_average_evidence_v1",
    "validate_asset_activity_v1",
]
