"""Build one browser-redactable Market Analysis Artifact v1 from completed valuations."""
from __future__ import annotations

from datetime import date, datetime
from fractions import Fraction
import csv
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from migrations.reference.legacy_import_data_command_v1 import fingerprint
from migrations.reference.unrealized_valuation_v1 import (
    ValuationContext,
    UnrealizedValuationBlocked,
    validate_unrealized_valuation_artifact_v1,
)

ROOT = Path(__file__).resolve().parents[2]
METRICS = ROOT / "contracts" / "market-analysis" / "v1" / "metric-definitions.csv"
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_REF = re.compile(r"^[a-z][a-z0-9]{2}_[a-f0-9]{24,32}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_CONTEXT = re.compile(r"^[A-Za-z0-9_-]{3,80}$")
_METRIC_FIELDS = {
    "market_value": "market_value_decimal",
    "fifo_cost": "fifo_cost_decimal",
    "unrealized_gross_gain": "unrealized_gross_gain_decimal",
    "projected_tax": "projected_tax_decimal",
    "liquidation_fee": "liquidation_fee_decimal",
    "net_liquidation": "net_liquidation_decimal",
}
MARKET_ANALYSIS_ERROR_CODES = frozenset({
    "market_analysis_context_invalid", "market_analysis_input_invalid", "market_analysis_source_incomplete",
    "market_analysis_source_invalid", "market_analysis_source_conflict", "market_analysis_currency_mismatch",
    "market_analysis_decimal_invalid", "market_analysis_reconciliation_failed",
})
_DISPLAY_ITEM_FIELDS = {
    "market_value": "display_market_value_decimal",
    "fifo_cost": "display_fifo_cost_decimal",
    "unrealized_gross_gain": "display_unrealized_gross_gain_decimal",
    "projected_tax": "display_projected_tax_decimal",
    "liquidation_fee": "display_liquidation_fee_decimal",
    "net_liquidation": "display_net_liquidation_decimal",
}


class MarketAnalysisBlocked(ValueError):
    def __init__(self, code: str):
        if code not in MARKET_ANALYSIS_ERROR_CODES:
            raise ValueError("market_analysis_error_code_unregistered")
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise MarketAnalysisBlocked(code)


def _ref(value: Any) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        _abort("market_analysis_input_invalid")
    return value


def _sha(value: Any) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        _abort("market_analysis_input_invalid")
    return value


def _utc(value: Any) -> str:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("market_analysis_input_invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _abort("market_analysis_input_invalid")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _abort("market_analysis_input_invalid")
    return value


def _date(value: Any) -> str:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        _abort("market_analysis_input_invalid")
    try:
        date.fromisoformat(value)
    except ValueError:
        _abort("market_analysis_input_invalid")
    return value


def _decimal(value: Any, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > 80 or value == "-0" or _DECIMAL.fullmatch(value) is None:
        _abort("market_analysis_decimal_invalid")
    return value


def _fraction(value: str) -> Fraction:
    _decimal(value)
    negative = value.startswith("-")
    raw = value[1:] if negative else value
    whole, dot, fractional = raw.partition(".")
    result = Fraction(int(whole + fractional), 10 ** len(fractional)) if dot else Fraction(int(whole), 1)
    return -result if negative else result


def _decimal_text(value: Fraction) -> str:
    if value == 0:
        return "0"
    denominator = value.denominator
    scale = 0
    while denominator % 2 == 0:
        denominator //= 2; scale += 1
    while denominator % 5 == 0:
        denominator //= 5; scale += 1
    if denominator != 1:
        _abort("market_analysis_reconciliation_failed")
    numerator = abs(value.numerator) * (10 ** scale // value.denominator)
    text = str(numerator).rjust(scale + 1, "0")
    result = text if scale == 0 else text[:-scale] + "." + text[-scale:]
    result = result.rstrip("0").rstrip(".")
    if value < 0:
        result = "-" + result
    return _decimal(result)


def _round_fraction(value: Fraction) -> int:
    sign = -1 if value < 0 else 1
    absolute = abs(value)
    quotient, remainder = divmod(absolute.numerator, absolute.denominator)
    doubled = remainder * 2
    if doubled > absolute.denominator or (doubled == absolute.denominator and quotient % 2):
        quotient += 1
    return sign * quotient


def _id(prefix: str, value: Any) -> str:
    return f"{prefix}_{fingerprint(value)[:32]}"


def _metric_definitions() -> list[dict[str, str]]:
    try:
        with METRICS.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle, strict=True))
    except Exception:
        _abort("market_analysis_input_invalid")
    fields = {"metric_code", "domain", "formula_code", "value_semantics", "aggregation_policy", "unit_kind"}
    if len(rows) != 9 or any(set(row) != fields for row in rows):
        _abort("market_analysis_input_invalid")
    return rows


def _source_models(
    models: Sequence[Mapping[str, Any]], context: ValuationContext, portfolio_ref: str,
) -> list[dict[str, Any]]:
    if not isinstance(models, Sequence) or isinstance(models, (str, bytes)) or not models:
        _abort("market_analysis_source_incomplete")
    result: list[dict[str, Any]] = []
    observed_dates: set[str] = set()
    observed_refs: set[str] = set()
    expected = {"source_status", "completed_at_utc", "artifact"}
    for model in models:
        if not isinstance(model, Mapping) or set(model) != expected or model.get("source_status") not in {"completed", "stale"}:
            _abort("market_analysis_source_incomplete")
        artifact = model.get("artifact")
        try:
            validate_unrealized_valuation_artifact_v1(artifact, context)
        except UnrealizedValuationBlocked:
            _abort("market_analysis_source_invalid")
        if artifact.get("portfolio_ref") != portfolio_ref:
            _abort("market_analysis_source_invalid")
        completed = _utc(model.get("completed_at_utc"))
        if completed[:10] < artifact["as_of_date"]:
            _abort("market_analysis_source_invalid")
        as_of = _date(artifact["as_of_date"])
        snapshot_ref = _ref(artifact["snapshot_ref"])
        if as_of in observed_dates or snapshot_ref in observed_refs:
            _abort("market_analysis_source_conflict")
        observed_dates.add(as_of); observed_refs.add(snapshot_ref)
        result.append({
            "source_status": model["source_status"], "snapshot_ref": snapshot_ref,
            "snapshot_status": artifact["status"], "as_of_date": as_of,
            "completed_at_utc": completed, "artifact_fingerprint": _sha(artifact["artifact_fingerprint"]),
            "row_set_fingerprint": _sha(artifact["row_set_fingerprint"]),
            "tax_plugin_status": artifact["tax_plugin"]["status"], "tax_plugin_id": artifact["tax_plugin"]["plugin_id"],
            "tax_plugin_version": artifact["tax_plugin"]["plugin_version"], "tax_rules_fingerprint": artifact["tax_plugin"]["rules_fingerprint"],
            "artifact": artifact,
        })
    result.sort(key=lambda row: (row["as_of_date"], row["completed_at_utc"], row["snapshot_ref"]))
    target = result[0]["artifact"]["target_currency"]
    if any(row["artifact"]["target_currency"] != target for row in result):
        _abort("market_analysis_currency_mismatch")
    return result


def _portfolio_history(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for source in sources:
        artifact = source["artifact"]; summary = artifact["summary"]
        market_dates = [row["price_date"] for row in artifact["items"] if row["price_status"] in {"completed", "stale_price"}]
        ages = [row["price_age_days"] for row in artifact["items"] if row["price_age_days"] is not None]
        result.append({
            "as_of_date": artifact["as_of_date"], "snapshot_ref": artifact["snapshot_ref"],
            "source_status": source["source_status"], "snapshot_status": artifact["status"],
            "target_currency": artifact["target_currency"], "last_covered_market_date": max(market_dates) if market_dates else None,
            "max_price_age_days": max(ages) if ages else None,
            "position_count": summary["position_count"], "completed_position_count": summary["completed_position_count"],
            "partial_position_count": summary["partial_position_count"], "blocked_position_count": summary["blocked_position_count"],
            **{field: _decimal(summary[field], True) for field in _METRIC_FIELDS.values()},
        })
    return result


def _account_history(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for source in sources:
        artifact = source["artifact"]
        for account in artifact["account_summaries"]:
            result.append({
                "as_of_date": artifact["as_of_date"], "snapshot_ref": artifact["snapshot_ref"],
                "account_ref": account["account_ref"], "source_status": source["source_status"],
                "aggregation_status": account["aggregation_status"], "target_currency": account["target_currency"],
                "position_count": account["position_count"], "completed_position_count": account["completed_position_count"],
                "partial_position_count": account["partial_position_count"], "blocked_position_count": account["blocked_position_count"],
                **{field: _decimal(account[field], True) for field in _METRIC_FIELDS.values()},
            })
    return sorted(result, key=lambda row: (row["account_ref"], row["as_of_date"]))


def _position_history(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for source in sources:
        artifact = source["artifact"]
        for item in artifact["items"]:
            result.append({
                "as_of_date": artifact["as_of_date"], "snapshot_ref": artifact["snapshot_ref"],
                "position_ref": item["position_ref"], "account_ref": item["account_ref"], "asset_ref": item["asset_ref"],
                "source_status": source["source_status"], "position_status": item["position_status"],
                "price_status": item["price_status"], "tax_status": item["tax_status"], "fx_status": item["fx_status"],
                "market_currency": item["market_currency"], "basis_currency": item["basis_currency"],
                "target_currency": item["target_currency"], "market_local_date": item["price_date"] if item["price_status"] in {"completed", "stale_price"} else None,
                "price_age_days": item["price_age_days"], "quantity_decimal": _decimal(item["remaining_quantity_decimal"]),
                "market_price_decimal": _decimal(item["market_price_decimal"], True),
                **{field + "_decimal": _decimal(item[source_field], True) for field, source_field in _DISPLAY_ITEM_FIELDS.items()},
                "failure_codes": list(item["failure_codes"]),
            })
    return sorted(result, key=lambda row: (row["position_ref"], row["as_of_date"]))


def _freshness(latest: Mapping[str, Any], history: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    artifact = latest["artifact"]
    result = []
    for item in artifact["items"]:
        observed_dates = [row["market_local_date"] for row in history if row["position_ref"] == item["position_ref"] and row["market_local_date"] is not None and row["market_price_decimal"] is not None]
        last_covered = max(observed_dates) if observed_dates else None
        derived_age = None if last_covered is None else (date.fromisoformat(artifact["as_of_date"]) - date.fromisoformat(last_covered)).days
        if item["price_status"] == "completed":
            freshness = "current" if item["price_age_days"] == 0 else "prior_observation"
        elif item["price_status"] == "stale_price":
            freshness = "stale"
        else:
            freshness = "missing"
        result.append({
            "position_ref": item["position_ref"], "account_ref": item["account_ref"], "asset_ref": item["asset_ref"],
            "as_of_date": artifact["as_of_date"], "last_covered_market_date": last_covered,
            "price_age_days": item["price_age_days"] if item["price_age_days"] is not None else derived_age, "freshness_status": freshness,
            "position_status": item["position_status"], "price_status": item["price_status"],
            "tax_status": item["tax_status"], "fx_status": item["fx_status"],
            "market_currency": item["market_currency"], "target_currency": item["target_currency"],
            "failure_codes": list(item["failure_codes"]),
        })
    return sorted(result, key=lambda row: row["position_ref"])


def _allocation(latest: Mapping[str, Any]) -> list[dict[str, Any]]:
    artifact = latest["artifact"]
    raw: list[dict[str, Any]] = []
    for account in artifact["account_summaries"]:
        raw.append({"scope_kind": "account", "scope_ref": account["account_ref"], "account_ref": account["account_ref"], "position_ref": None, "value_decimal": account["market_value_decimal"], "value_status": account["aggregation_status"]})
    for item in artifact["items"]:
        raw.append({"scope_kind": "position", "scope_ref": item["position_ref"], "account_ref": item["account_ref"], "position_ref": item["position_ref"], "value_decimal": item["display_market_value_decimal"], "value_status": item["position_status"]})
    result = []
    for kind in ("account", "position"):
        rows = [row for row in raw if row["scope_kind"] == kind]
        available_rows = [row for row in rows if row["value_decimal"] is not None]
        available = [_fraction(row["value_decimal"]) for row in available_rows]
        denominator = sum(available, Fraction(0))
        shares: dict[str, int] = {}
        if denominator > 0:
            exact = {row["scope_ref"]: _fraction(row["value_decimal"]) * 10000 / denominator for row in available_rows}
            shares = {scope_ref: value.numerator // value.denominator for scope_ref, value in exact.items()}
            residual = 10000 - sum(shares.values())
            ranking = sorted(exact, key=lambda scope_ref: (-(exact[scope_ref] - shares[scope_ref]), scope_ref))
            for scope_ref in ranking[:residual]:
                shares[scope_ref] += 1
        for row in rows:
            value = _decimal(row["value_decimal"], True)
            share = shares.get(row["scope_ref"])
            result.append({
                **row, "as_of_date": artifact["as_of_date"], "currency": artifact["target_currency"],
                "denominator_decimal": _decimal_text(denominator) if denominator > 0 else None,
                "share_basis_points": share,
                "allocation_status": "completed" if share is not None and len(available) == len(rows) else "partial" if share is not None else "unavailable",
            })
    return sorted(result, key=lambda row: (row["scope_kind"], row["scope_ref"]))


def _point_status(row: Mapping[str, Any], value: str | None) -> str:
    if value is None:
        return "blocked" if row.get("snapshot_status") == "blocked" or row.get("position_status") == "blocked" else "unavailable"
    if row.get("source_status") == "stale":
        return "stale"
    return "completed"


def _plot_series(
    portfolio: Sequence[Mapping[str, Any]], accounts: Sequence[Mapping[str, Any]],
    positions: Sequence[Mapping[str, Any]], portfolio_ref: str,
) -> list[dict[str, Any]]:
    groups: list[tuple[str, str, str, str, list[tuple[str, str, Sequence[Mapping[str, Any]]]]]] = []
    target = portfolio[0]["target_currency"]
    groups.append(("portfolio_valuation_history", "portfolio", portfolio_ref, target, [(metric, _METRIC_FIELDS[metric], portfolio) for metric in ("market_value", "fifo_cost", "unrealized_gross_gain", "net_liquidation")]))
    groups.append(("projected_liquidation_cost_history", "portfolio", portfolio_ref, target, [(metric, _METRIC_FIELDS[metric], portfolio) for metric in ("projected_tax", "liquidation_fee")]))
    for account_ref in sorted({row["account_ref"] for row in accounts}):
        rows = [row for row in accounts if row["account_ref"] == account_ref]
        groups.append(("account_valuation_history", "account", account_ref, target, [(metric, _METRIC_FIELDS[metric], rows) for metric in ("market_value", "net_liquidation")]))
    for position_ref in sorted({row["position_ref"] for row in positions}):
        rows = [row for row in positions if row["position_ref"] == position_ref]
        groups.append(("position_valuation_history", "position", position_ref, target, [(metric, metric + "_decimal", rows) for metric in ("market_value", "fifo_cost", "unrealized_gross_gain", "net_liquidation")]))
        groups.append(("position_price_history", "position", position_ref, rows[0]["market_currency"], [("market_price", "market_price_decimal", rows)]))
        groups.append(("position_quantity_history", "position", position_ref, "UNIT", [("position_quantity", "quantity_decimal", rows)]))
    result = []
    for plot_code, scope_kind, scope_ref, currency, specifications in groups:
        all_values = [_fraction(row[field]) for _, field, rows in specifications for row in rows if row[field] is not None]
        minimum = min(all_values + [Fraction(0)]) if all_values else Fraction(0)
        maximum = max(all_values + [Fraction(0)]) if all_values else Fraction(0)
        span = maximum - minimum
        zero_y = 500 if span == 0 else 9500 - _round_fraction((Fraction(0) - minimum) * 9000 / span)
        for metric, field, rows in specifications:
            points = []
            first_day = date.fromisoformat(rows[0]["as_of_date"]); last_day = date.fromisoformat(rows[-1]["as_of_date"]); day_span = (last_day - first_day).days
            for row in rows:
                value = _decimal(row[field], True)
                elapsed_days = (date.fromisoformat(row["as_of_date"]) - first_day).days
                x = 5000 if day_span == 0 else 500 + _round_fraction(Fraction(elapsed_days * 9000, day_span))
                y = None if value is None else 5000 if span == 0 else 9500 - _round_fraction((_fraction(value) - minimum) * 9000 / span)
                points.append({
                    "point_ref": _id("map", [plot_code, scope_ref, metric, row["as_of_date"], row["snapshot_ref"]]),
                    "period_label": row["as_of_date"], "x_basis_points": x, "y_basis_points": y,
                    "value_decimal": value, "point_status": _point_status(row, value),
                    "source_snapshot_ref": row["snapshot_ref"],
                })
            statuses = {point["point_status"] for point in points}
            series_status = "unavailable" if not points or all(point["value_decimal"] is None for point in points) else "stale" if "stale" in statuses else "partial" if statuses & {"blocked", "unavailable"} else "completed"
            result.append({
                "series_ref": _id("mas", [plot_code, scope_ref, metric, [point["point_ref"] for point in points]]),
                "plot_code": plot_code, "metric_code": metric, "currency": currency,
                "scope_kind": scope_kind, "scope_ref": scope_ref, "series_status": series_status,
                "zero_line_y_basis_points": zero_y, "points": points,
            })
    return result


def build_market_analysis_artifact_v1(
    *, valuation_read_models: Sequence[Mapping[str, Any]], tenant_id: str, user_id: str,
    data_space_id: str, portfolio_ref: str, portfolio_label: str, completed_at_utc: str,
) -> dict[str, Any]:
    if not all(isinstance(value, str) and _CONTEXT.fullmatch(value) for value in (tenant_id, user_id)) or not isinstance(data_space_id, str) or not data_space_id.startswith("sbx_") or _CONTEXT.fullmatch(data_space_id) is None:
        _abort("market_analysis_context_invalid")
    context = ValuationContext(tenant_id, user_id, data_space_id, "market_analysis_worker", "analysis_worker")
    portfolio_ref = _ref(portfolio_ref); completed_at_utc = _utc(completed_at_utc)
    if not isinstance(portfolio_label, str) or not 1 <= len(portfolio_label) <= 160 or any(ord(char) < 32 for char in portfolio_label):
        _abort("market_analysis_input_invalid")
    sources = _source_models(valuation_read_models, context, portfolio_ref)
    latest = sources[-1]
    if completed_at_utc < latest["completed_at_utc"]:
        _abort("market_analysis_input_invalid")
    portfolio = _portfolio_history(sources); accounts = _account_history(sources); positions = _position_history(sources)
    freshness = _freshness(latest, positions); allocation = _allocation(latest)
    plots = _plot_series(portfolio, accounts, positions, portfolio_ref)
    latest_status = latest["artifact"]["status"]
    projection_status = "stale" if latest["source_status"] == "stale" else "completed" if latest_status == "completed" else "partial"
    source_rows = [{key: row[key] for key in ("source_status", "snapshot_ref", "snapshot_status", "as_of_date", "completed_at_utc", "artifact_fingerprint", "row_set_fingerprint", "tax_plugin_status", "tax_plugin_id", "tax_plugin_version", "tax_rules_fingerprint")} for row in sources]
    tax = latest["artifact"]["tax_plugin"]
    payload = {
        "market_analysis_artifact_version": 1, "market_analysis_artifact_id": _id("maa", [portfolio_ref, source_rows, plots]),
        "status": "completed", "projection_status": projection_status,
        "tenant_id": tenant_id, "user_id": user_id, "data_space_id": data_space_id,
        "portfolio_ref": portfolio_ref, "portfolio_label": portfolio_label,
        "target_currency": latest["artifact"]["target_currency"], "history_start_date": sources[0]["as_of_date"],
        "analysis_cutoff_date": latest["as_of_date"], "completed_at_utc": completed_at_utc,
        "source_snapshots": source_rows, "latest_snapshot_ref": latest["snapshot_ref"],
        "tax_plugin": {key: tax[key] for key in ("status", "plugin_id", "plugin_version", "rules_fingerprint", "manifest_fingerprint", "disclaimer_codes")},
        "metric_definitions": _metric_definitions(), "portfolio_history": portfolio,
        "account_history": accounts, "position_history": positions, "freshness": freshness,
        "allocation": allocation, "plot_series": plots,
        "disclaimers": ["market_based_unrealized_only_no_realized_total", "tax_projection_not_legal_advice_or_filing", "no_forecast_or_technical_signal"],
        "boundaries": {
            "provider_access": False, "network_access": False, "valuation_started": False,
            "tax_calculation_started": False, "fx_conversion_started": False,
            "trade_metric_composition": False, "forecasting": False, "technical_analysis": False,
            "alarm_eligibility": False, "notification_eligibility": False,
            "app_side_calculation": False, "canonical_write": False,
        },
    }
    payload["artifact_fingerprint"] = fingerprint(payload)
    return payload
