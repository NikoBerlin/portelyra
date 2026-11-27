"""Executable reference oracle for Transaction Semantics v1.

This module is newly implemented contract evidence. It does not contain copied
Legacy code, open files, access networks, or write databases.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import hashlib
import json
import re
from typing import Any

TRANSACTION_SEMANTICS_VERSION = 1
TRANSACTION_PROFILE = "buy_sell_fee_tax_base_currency_v1"
SUPPORTED_TRANSACTION_TYPES = frozenset({"buy", "sell"})
SEMANTICS_FAILURE_CODES = frozenset(
    {
        "transaction_semantics_input_invalid",
        "transaction_semantics_decimal_invalid",
        "transaction_semantics_decimal_too_long",
        "transaction_semantics_quantity_scale_exceeded",
        "transaction_semantics_date_invalid",
        "transaction_semantics_entity_duplicate",
        "transaction_semantics_reference_missing",
        "transaction_semantics_portfolio_mismatch",
        "transaction_semantics_type_unsupported",
        "transaction_semantics_posting_sequence_invalid",
        "transaction_semantics_role_cardinality_invalid",
        "transaction_semantics_role_order_invalid",
        "transaction_semantics_account_invalid",
        "transaction_semantics_asset_invalid",
        "transaction_semantics_sign_invalid",
        "transaction_semantics_price_invalid",
        "transaction_semantics_currency_invalid",
        "transaction_semantics_valuation_invalid",
        "transaction_semantics_gross_balance_invalid",
        "transaction_semantics_buy_tax_forbidden",
        "transaction_semantics_fifo_inventory_insufficient",
        "transaction_semantics_rounding_policy_required",
        "transaction_semantics_boundary_failed",
    }
)

_CANONICAL_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?")
_UTC_SECOND = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_LOCAL_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class TransactionSemanticsError(RuntimeError):
    """Fail-closed error carrying only a registered privacy-safe code."""

    def __init__(self, code: str):
        if code not in SEMANTICS_FAILURE_CODES:
            raise ValueError("unregistered_transaction_semantics_error_code")
        super().__init__(code)
        self.code = code


def _decimal_fraction(value: Any, *, allow_zero: bool = True, positive_only: bool = False) -> Fraction:
    if not isinstance(value, str) or len(value) > 80 or _CANONICAL_DECIMAL.fullmatch(value) is None:
        raise TransactionSemanticsError("transaction_semantics_decimal_invalid")
    if value == "-0":
        raise TransactionSemanticsError("transaction_semantics_decimal_invalid")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation:
        raise TransactionSemanticsError("transaction_semantics_decimal_invalid") from None
    if not allow_zero and decimal_value == 0:
        raise TransactionSemanticsError("transaction_semantics_decimal_invalid")
    if positive_only and decimal_value <= 0:
        raise TransactionSemanticsError("transaction_semantics_price_invalid")
    return Fraction(decimal_value)


def decimal_fraction(value: Any, *, allow_zero: bool = True, positive_only: bool = False) -> Fraction:
    """Public exact-decimal adapter for downstream contract oracles."""

    return _decimal_fraction(value, allow_zero=allow_zero, positive_only=positive_only)


def canonical_fraction(value: Fraction) -> str:
    """Public exact rational-to-canonical-decimal adapter."""

    return _canonical_fraction(value)


def _decimal_scale(value: str) -> int:
    return len(value.partition(".")[2])


def _canonical_fraction(value: Fraction) -> str:
    if value == 0:
        return "0"
    denominator = value.denominator
    twos = 0
    fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        raise TransactionSemanticsError("transaction_semantics_rounding_policy_required")
    scale = max(twos, fives)
    scaled = value.numerator * (2 ** (scale - twos)) * (5 ** (scale - fives))
    sign = "-" if scaled < 0 else ""
    digits = str(abs(scaled))
    if scale:
        digits = digits.zfill(scale + 1)
        digits = digits[:-scale] + "." + digits[-scale:]
        digits = digits.rstrip("0").rstrip(".")
    result = sign + digits
    if len(result) > 80:
        raise TransactionSemanticsError("transaction_semantics_decimal_too_long")
    return result


def _parse_dates(effective_at_utc: Any, local_date: Any) -> None:
    if not isinstance(effective_at_utc, str) or _UTC_SECOND.fullmatch(effective_at_utc) is None:
        raise TransactionSemanticsError("transaction_semantics_date_invalid")
    if not isinstance(local_date, str) or _LOCAL_DATE.fullmatch(local_date) is None:
        raise TransactionSemanticsError("transaction_semantics_date_invalid")
    try:
        datetime.strptime(effective_at_utc, "%Y-%m-%dT%H:%M:%SZ")
        datetime.strptime(local_date, "%Y-%m-%d")
    except ValueError:
        raise TransactionSemanticsError("transaction_semantics_date_invalid") from None


def _index_unique(rows: Any, key: str) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list) or not all(isinstance(row, dict) and isinstance(row.get(key), str) for row in rows):
        raise TransactionSemanticsError("transaction_semantics_input_invalid")
    result = {row[key]: row for row in rows}
    if len(result) != len(rows):
        raise TransactionSemanticsError("transaction_semantics_entity_duplicate")
    return result


def _role_posting(postings_by_role: dict[str, list[dict[str, Any]]], role: str, minimum: int, maximum: int) -> dict[str, Any] | None:
    rows = postings_by_role.get(role, [])
    if not minimum <= len(rows) <= maximum:
        raise TransactionSemanticsError("transaction_semantics_role_cardinality_invalid")
    return rows[0] if rows else None


def _require_keys(row: dict[str, Any], keys: tuple[str, ...]) -> None:
    if not all(key in row for key in keys):
        raise TransactionSemanticsError("transaction_semantics_input_invalid")


def _cash_value(
    posting: dict[str, Any],
    account: dict[str, Any],
    asset: dict[str, Any],
    settlement_currency: str,
) -> Fraction:
    if account.get("account_type") not in {"cash", "bank"}:
        raise TransactionSemanticsError("transaction_semantics_account_invalid")
    if asset.get("asset_type") != "cash" or asset.get("valuation_method") != "unit_value":
        raise TransactionSemanticsError("transaction_semantics_asset_invalid")
    if asset.get("price_currency") != settlement_currency:
        raise TransactionSemanticsError("transaction_semantics_currency_invalid")
    if posting.get("unit_price_decimal") is not None or posting.get("price_currency") is not None:
        raise TransactionSemanticsError("transaction_semantics_price_invalid")
    if posting.get("valuation_currency") != settlement_currency:
        raise TransactionSemanticsError("transaction_semantics_currency_invalid")
    quantity = _decimal_fraction(posting.get("quantity_decimal"), allow_zero=False)
    valuation = _decimal_fraction(posting.get("valuation_amount_decimal"))
    if quantity != valuation:
        raise TransactionSemanticsError("transaction_semantics_valuation_invalid")
    if _decimal_scale(posting["quantity_decimal"]) > int(asset.get("quantity_scale", -1)):
        raise TransactionSemanticsError("transaction_semantics_quantity_scale_exceeded")
    return quantity


def _fingerprint_evidence(evidence: dict[str, Any]) -> str:
    payload = json.dumps(evidence, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_candidate_transaction_semantics_impl(candidate: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise TransactionSemanticsError("transaction_semantics_input_invalid")
    for key in ("portfolios", "accounts", "assets", "transactions", "postings"):
        if key not in candidate:
            raise TransactionSemanticsError("transaction_semantics_input_invalid")

    portfolios = _index_unique(candidate["portfolios"], "staged_portfolio_id")
    accounts = _index_unique(candidate["accounts"], "staged_account_id")
    assets = _index_unique(candidate["assets"], "staged_asset_id")
    transactions = _index_unique(candidate["transactions"], "staged_transaction_id")
    postings = _index_unique(candidate["postings"], "staged_posting_id")
    if len(portfolios) != 1 or not transactions:
        raise TransactionSemanticsError("transaction_semantics_input_invalid")

    postings_by_transaction: dict[str, list[dict[str, Any]]] = {transaction_id: [] for transaction_id in transactions}
    for posting in postings.values():
        transaction_id = posting.get("staged_transaction_id")
        if transaction_id not in transactions:
            raise TransactionSemanticsError("transaction_semantics_reference_missing")
        postings_by_transaction[transaction_id].append(posting)

    ordered_transactions = sorted(
        transactions.values(),
        key=lambda row: (str(row.get("effective_at_utc", "")), str(row.get("staged_transaction_id", ""))),
    )
    fifo_lots: dict[tuple[str, str, str], list[dict[str, Fraction]]] = {}
    transaction_evidence: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Fraction]] = {}

    transaction_keys = (
        "staged_transaction_id",
        "staged_portfolio_id",
        "transaction_type",
        "effective_at_utc",
        "local_date",
    )
    posting_keys = (
        "staged_posting_id",
        "staged_transaction_id",
        "sequence_no",
        "staged_account_id",
        "staged_asset_id",
        "posting_role",
        "quantity_decimal",
        "unit_price_decimal",
        "price_currency",
        "valuation_amount_decimal",
        "valuation_currency",
    )

    for transaction in ordered_transactions:
        _require_keys(transaction, transaction_keys)
        transaction_type = transaction["transaction_type"]
        if transaction_type not in SUPPORTED_TRANSACTION_TYPES:
            raise TransactionSemanticsError("transaction_semantics_type_unsupported")
        _parse_dates(transaction["effective_at_utc"], transaction["local_date"])
        portfolio = portfolios.get(transaction["staged_portfolio_id"])
        if portfolio is None:
            raise TransactionSemanticsError("transaction_semantics_reference_missing")
        settlement_currency = portfolio.get("base_currency")
        if not isinstance(settlement_currency, str) or re.fullmatch(r"[A-Z]{3}", settlement_currency) is None:
            raise TransactionSemanticsError("transaction_semantics_currency_invalid")

        transaction_postings = postings_by_transaction[transaction["staged_transaction_id"]]
        if not transaction_postings:
            raise TransactionSemanticsError("transaction_semantics_role_cardinality_invalid")
        for posting in transaction_postings:
            _require_keys(posting, posting_keys)
        try:
            transaction_postings.sort(key=lambda row: int(row["sequence_no"]))
        except (TypeError, ValueError):
            raise TransactionSemanticsError("transaction_semantics_posting_sequence_invalid") from None
        sequences = [row["sequence_no"] for row in transaction_postings]
        if sequences != list(range(1, len(transaction_postings) + 1)):
            raise TransactionSemanticsError("transaction_semantics_posting_sequence_invalid")

        postings_by_role: dict[str, list[dict[str, Any]]] = {}
        for posting in transaction_postings:
            role = posting["posting_role"]
            postings_by_role.setdefault(role, []).append(posting)
        allowed_roles = {"asset", "cash", "fee", "tax"}
        if set(postings_by_role) - allowed_roles:
            raise TransactionSemanticsError("transaction_semantics_role_cardinality_invalid")
        asset_posting = _role_posting(postings_by_role, "asset", 1, 1)
        cash_posting = _role_posting(postings_by_role, "cash", 1, 1)
        fee_posting = _role_posting(postings_by_role, "fee", 0, 1)
        tax_posting = _role_posting(postings_by_role, "tax", 0, 1)
        if transaction_type == "buy" and tax_posting is not None:
            raise TransactionSemanticsError("transaction_semantics_buy_tax_forbidden")
        expected_roles = ["asset", "cash"] + (["fee"] if fee_posting else []) + (["tax"] if tax_posting else [])
        if [row["posting_role"] for row in transaction_postings] != expected_roles:
            raise TransactionSemanticsError("transaction_semantics_role_order_invalid")
        assert asset_posting is not None and cash_posting is not None

        account = accounts.get(asset_posting["staged_account_id"])
        traded_asset = assets.get(asset_posting["staged_asset_id"])
        cash_account = accounts.get(cash_posting["staged_account_id"])
        cash_asset = assets.get(cash_posting["staged_asset_id"])
        if account is None or traded_asset is None or cash_account is None or cash_asset is None:
            raise TransactionSemanticsError("transaction_semantics_reference_missing")
        if account.get("staged_portfolio_id") != transaction["staged_portfolio_id"] or cash_account.get("staged_portfolio_id") != transaction["staged_portfolio_id"]:
            raise TransactionSemanticsError("transaction_semantics_portfolio_mismatch")
        if account.get("account_type") not in {"securities", "crypto_wallet"}:
            raise TransactionSemanticsError("transaction_semantics_account_invalid")
        if traded_asset.get("asset_type") == "cash":
            raise TransactionSemanticsError("transaction_semantics_asset_invalid")
        if traded_asset.get("price_currency") != settlement_currency:
            raise TransactionSemanticsError("transaction_semantics_currency_invalid")

        asset_quantity = _decimal_fraction(asset_posting["quantity_decimal"], allow_zero=False)
        if _decimal_scale(asset_posting["quantity_decimal"]) > int(traded_asset.get("quantity_scale", -1)):
            raise TransactionSemanticsError("transaction_semantics_quantity_scale_exceeded")
        if (transaction_type == "buy" and asset_quantity <= 0) or (transaction_type == "sell" and asset_quantity >= 0):
            raise TransactionSemanticsError("transaction_semantics_sign_invalid")
        unit_price = _decimal_fraction(asset_posting["unit_price_decimal"], positive_only=True)
        if asset_posting["price_currency"] != settlement_currency or asset_posting["valuation_currency"] != settlement_currency:
            raise TransactionSemanticsError("transaction_semantics_currency_invalid")
        asset_valuation = _decimal_fraction(asset_posting["valuation_amount_decimal"])
        if asset_valuation != asset_quantity * unit_price:
            raise TransactionSemanticsError("transaction_semantics_valuation_invalid")

        gross_cashflow = _cash_value(cash_posting, cash_account, cash_asset, settlement_currency)
        if gross_cashflow != -asset_valuation:
            raise TransactionSemanticsError("transaction_semantics_gross_balance_invalid")

        fee_cashflow = Fraction(0)
        if fee_posting is not None:
            fee_account = accounts.get(fee_posting["staged_account_id"])
            fee_asset = assets.get(fee_posting["staged_asset_id"])
            if fee_account is None or fee_asset is None:
                raise TransactionSemanticsError("transaction_semantics_reference_missing")
            if fee_posting["staged_account_id"] != cash_posting["staged_account_id"] or fee_posting["staged_asset_id"] != cash_posting["staged_asset_id"]:
                raise TransactionSemanticsError("transaction_semantics_account_invalid")
            fee_cashflow = _cash_value(fee_posting, fee_account, fee_asset, settlement_currency)
            if fee_cashflow >= 0:
                raise TransactionSemanticsError("transaction_semantics_sign_invalid")

        tax_cashflow = Fraction(0)
        if tax_posting is not None:
            tax_account = accounts.get(tax_posting["staged_account_id"])
            tax_asset = assets.get(tax_posting["staged_asset_id"])
            if tax_account is None or tax_asset is None:
                raise TransactionSemanticsError("transaction_semantics_reference_missing")
            if tax_posting["staged_account_id"] != cash_posting["staged_account_id"] or tax_posting["staged_asset_id"] != cash_posting["staged_asset_id"]:
                raise TransactionSemanticsError("transaction_semantics_account_invalid")
            tax_cashflow = _cash_value(tax_posting, tax_account, tax_asset, settlement_currency)
            if tax_cashflow >= 0:
                raise TransactionSemanticsError("transaction_semantics_sign_invalid")

        net_cashflow = gross_cashflow + fee_cashflow + tax_cashflow
        lot_key = (transaction["staged_portfolio_id"], asset_posting["staged_account_id"], asset_posting["staged_asset_id"])
        acquisition_cost_added: Fraction | None = None
        fifo_cost_consumed: Fraction | None = None
        realized_gain_pre_tax: Fraction | None = None
        realized_gain_after_tax_cash: Fraction | None = None
        if transaction_type == "buy":
            acquisition_cost_added = -gross_cashflow - fee_cashflow
            fifo_lots.setdefault(lot_key, []).append({"quantity": asset_quantity, "cost": acquisition_cost_added})
        else:
            remaining_to_dispose = -asset_quantity
            fifo_cost_consumed = Fraction(0)
            lots = fifo_lots.setdefault(lot_key, [])
            while remaining_to_dispose > 0:
                if not lots:
                    raise TransactionSemanticsError("transaction_semantics_fifo_inventory_insufficient")
                lot = lots[0]
                consumed_quantity = min(remaining_to_dispose, lot["quantity"])
                consumed_cost = lot["cost"] * consumed_quantity / lot["quantity"]
                fifo_cost_consumed += consumed_cost
                lot["quantity"] -= consumed_quantity
                lot["cost"] -= consumed_cost
                remaining_to_dispose -= consumed_quantity
                if lot["quantity"] == 0:
                    lots.pop(0)
            proceeds_after_fee = gross_cashflow + fee_cashflow
            realized_gain_pre_tax = proceeds_after_fee - fifo_cost_consumed
            realized_gain_after_tax_cash = realized_gain_pre_tax + tax_cashflow

        per_currency = totals.setdefault(
            settlement_currency,
            {
                "gross_cashflow": Fraction(0),
                "fees": Fraction(0),
                "taxes": Fraction(0),
                "net_cashflow": Fraction(0),
                "acquisition_cost_added": Fraction(0),
                "fifo_cost_consumed": Fraction(0),
                "realized_gain_pre_tax": Fraction(0),
                "realized_gain_after_tax_cash": Fraction(0),
            },
        )
        per_currency["gross_cashflow"] += gross_cashflow
        per_currency["fees"] += fee_cashflow
        per_currency["taxes"] += tax_cashflow
        per_currency["net_cashflow"] += net_cashflow
        per_currency["acquisition_cost_added"] += acquisition_cost_added or Fraction(0)
        per_currency["fifo_cost_consumed"] += fifo_cost_consumed or Fraction(0)
        per_currency["realized_gain_pre_tax"] += realized_gain_pre_tax or Fraction(0)
        per_currency["realized_gain_after_tax_cash"] += realized_gain_after_tax_cash or Fraction(0)

        transaction_evidence.append(
            {
                "transaction_id": transaction["staged_transaction_id"],
                "transaction_type": transaction_type,
                "account_id": asset_posting["staged_account_id"],
                "asset_id": asset_posting["staged_asset_id"],
                "settlement_currency": settlement_currency,
                "asset_quantity_decimal": _canonical_fraction(asset_quantity),
                "gross_trade_amount_decimal": _canonical_fraction(abs(asset_valuation)),
                "gross_cashflow_decimal": _canonical_fraction(gross_cashflow),
                "fee_cashflow_decimal": _canonical_fraction(fee_cashflow),
                "tax_cashflow_decimal": _canonical_fraction(tax_cashflow),
                "net_cashflow_decimal": _canonical_fraction(net_cashflow),
                "acquisition_cost_added_decimal": None if acquisition_cost_added is None else _canonical_fraction(acquisition_cost_added),
                "fifo_cost_consumed_decimal": None if fifo_cost_consumed is None else _canonical_fraction(fifo_cost_consumed),
                "realized_gain_pre_tax_decimal": None if realized_gain_pre_tax is None else _canonical_fraction(realized_gain_pre_tax),
                "realized_gain_after_tax_cash_decimal": None if realized_gain_after_tax_cash is None else _canonical_fraction(realized_gain_after_tax_cash),
            }
        )

    position_evidence: list[dict[str, Any]] = []
    for (portfolio_id, account_id, asset_id), lots in sorted(fifo_lots.items()):
        remaining_quantity = sum((lot["quantity"] for lot in lots), Fraction(0))
        remaining_cost = sum((lot["cost"] for lot in lots), Fraction(0))
        if remaining_quantity:
            position_evidence.append(
                {
                    "portfolio_id": portfolio_id,
                    "account_id": account_id,
                    "asset_id": asset_id,
                    "remaining_quantity_decimal": _canonical_fraction(remaining_quantity),
                    "remaining_fifo_cost_decimal": _canonical_fraction(remaining_cost),
                }
            )

    totals_evidence = [
        {
            "currency": currency,
            "gross_cashflow_decimal": _canonical_fraction(values["gross_cashflow"]),
            "fee_cashflow_decimal": _canonical_fraction(values["fees"]),
            "tax_cashflow_decimal": _canonical_fraction(values["taxes"]),
            "net_cashflow_decimal": _canonical_fraction(values["net_cashflow"]),
            "acquisition_cost_added_decimal": _canonical_fraction(values["acquisition_cost_added"]),
            "fifo_cost_consumed_decimal": _canonical_fraction(values["fifo_cost_consumed"]),
            "realized_gain_pre_tax_decimal": _canonical_fraction(values["realized_gain_pre_tax"]),
            "realized_gain_after_tax_cash_decimal": _canonical_fraction(values["realized_gain_after_tax_cash"]),
        }
        for currency, values in sorted(totals.items())
    ]
    evidence = {
        "transaction_semantics_version": TRANSACTION_SEMANTICS_VERSION,
        "profile": TRANSACTION_PROFILE,
        "transaction_count": len(transaction_evidence),
        "posting_count": len(postings),
        "transactions": transaction_evidence,
        "positions": position_evidence,
        "totals_by_currency": totals_evidence,
    }
    evidence["evidence_fingerprint"] = _fingerprint_evidence(evidence)
    return evidence


def validate_candidate_transaction_semantics(candidate: dict[str, Any]) -> dict[str, Any]:
    """Validate and derive exact Buy/Sell/Fee/Tax/FIFO evidence."""

    try:
        return _validate_candidate_transaction_semantics_impl(candidate)
    except TransactionSemanticsError:
        raise
    except Exception:
        raise TransactionSemanticsError("transaction_semantics_boundary_failed") from None
