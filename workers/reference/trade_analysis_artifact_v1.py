"""Build one exact provider-free Trade-based Analysis Artifact v1."""
from __future__ import annotations

import calendar
import csv
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from migrations.reference.legacy_import_data_command_v1 import fingerprint

ROOT = Path(__file__).resolve().parents[2]
METRICS = ROOT / "contracts" / "trade-analysis" / "v1" / "metric-definitions.csv"
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_REF = re.compile(r"^[a-z][a-z0-9]{2}_[a-f0-9]{24,32}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_CONTEXT = re.compile(r"^[A-Za-z0-9_-]{3,80}$")
_FORBIDDEN = {
    "tenant_id", "user_id", "data_space_id", "context_binding_fingerprint",
    "database_path", "internal_id", "plugin_input_fingerprint",
    "plugin_output_fingerprint", "evidence_artifact_fingerprint",
}
_SEMANTIC_CONTRACTS = {"portfolio_ledger_v1_transaction_fact", "asset_activity_v1"}


class TradeAnalysisBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise TradeAnalysisBlocked(code)


def _ref(value: Any) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        _abort("trade_analysis_input_invalid")
    return value


def _utc(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("trade_analysis_input_invalid")
    return value


def _date(value: Any) -> str:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        _abort("trade_analysis_input_invalid")
    return value


def _decimal(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str) or len(value) > 80 or
        _DECIMAL.fullmatch(value) is None or value == "-0"
    ):
        _abort("trade_analysis_decimal_invalid")
    return value


def _d(value: str) -> Decimal:
    _decimal(value)
    try:
        with localcontext() as context:
            context.prec = 240
            return Decimal(value)
    except InvalidOperation:
        _abort("trade_analysis_decimal_invalid")


def _text(value: Decimal) -> str:
    if value == 0:
        return "0"
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    if result == "-0":
        return "0"
    if _DECIMAL.fullmatch(result) is None:
        _abort("trade_analysis_decimal_invalid")
    return result


def _sha_ref(prefix: str, value: Any) -> str:
    return f"{prefix}_{fingerprint(value)[:32]}"


def _artifact(model: Any, kind: str) -> tuple[str, Mapping[str, Any]]:
    if not isinstance(model, Mapping) or model.get("status") not in {"completed", "stale"} or not isinstance(model.get("artifact"), Mapping):
        _abort("trade_analysis_source_incomplete")
    artifact = model["artifact"]
    if kind == "realized" and not isinstance(model.get("tables"), Mapping):
        _abort("trade_analysis_source_incomplete")
    if kind != "realized" and not isinstance(model.get("rows"), list):
        _abort("trade_analysis_source_incomplete")
    return str(model["status"]), artifact


def _no_forbidden_rows(rows: Sequence[Mapping[str, Any]]) -> None:
    for row in rows:
        if not isinstance(row, Mapping) or _FORBIDDEN & set(row):
            _abort("trade_analysis_internal_exposure")


def _load_metric_definitions() -> list[dict[str, str]]:
    with METRICS.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, strict=True))
    expected = {"metric_code", "domain", "formula_code", "value_semantics", "aggregation_policy", "tax_scope"}
    if len(rows) != 18 or any(set(row) != expected for row in rows):
        _abort("trade_analysis_input_invalid")
    return rows


def _source(realized_model: Mapping[str, Any], event_model: Mapping[str, Any] | None, annual_models: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    realized_status, realized = _artifact(realized_model, "realized")
    semantic_bindings = realized.get("semantic_source_bindings")
    semantic_fingerprint = realized.get("semantic_binding_fingerprint")
    if not isinstance(semantic_bindings, list) or not semantic_bindings or not isinstance(semantic_fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", semantic_fingerprint):
        _abort("trade_analysis_input_invalid")
    contracts = [row.get("semantic_contract") for row in semantic_bindings if isinstance(row, Mapping)]
    if len(contracts) != len(set(contracts)) or not set(contracts) <= _SEMANTIC_CONTRACTS:
        _abort("trade_analysis_input_invalid")
    realized_source = {
        "status": realized_status,
        "artifact_ref": _ref(realized.get("artifact_ref")),
        "algorithm_version": realized.get("algorithm_version"),
        "row_set_fingerprint": realized.get("row_set_fingerprint"),
        "evidence_cutoff_at_utc": _utc(realized.get("evidence_cutoff_at_utc")),
        "completed_at_utc": _utc(realized.get("completed_at_utc")),
        "semantic_source_bindings": semantic_bindings,
        "semantic_binding_fingerprint": semantic_fingerprint,
    }
    if not isinstance(realized_source["algorithm_version"], str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{2,79}", realized_source["algorithm_version"]):
        _abort("trade_analysis_input_invalid")
    for key in ("row_set_fingerprint",):
        if not isinstance(realized_source[key], str) or not re.fullmatch(r"[a-f0-9]{64}", realized_source[key]):
            _abort("trade_analysis_input_invalid")
    event_source = None
    if event_model is not None:
        event_status, event = _artifact(event_model, "event")
        if event.get("projection_mode") != "realized_event" or event.get("tax_year") is not None:
            _abort("trade_analysis_source_mismatch")
        event_source = {
            "status": event_status,
            "artifact_ref": _ref(event.get("artifact_ref")),
            "source_artifact_ref": _ref(event.get("source_artifact_ref")),
            "plugin_id": event.get("plugin_id"), "plugin_version": event.get("plugin_version"),
            "rules_fingerprint": event.get("rules_fingerprint"), "row_set_fingerprint": event.get("row_set_fingerprint"),
            "semantic_binding_fingerprint": event.get("semantic_binding_fingerprint"),
            "readiness_status": event.get("readiness_status"), "completed_at_utc": _utc(event.get("completed_at_utc")),
        }
        if (event_source["source_artifact_ref"] != realized_source["artifact_ref"] or
            event.get("semantic_source_bindings") != semantic_bindings or
            event.get("semantic_binding_fingerprint") != semantic_fingerprint):
            _abort("trade_analysis_source_mismatch")
        if event_source["readiness_status"] not in {"complete", "partial_blocked"}:
            _abort("trade_analysis_input_invalid")
        for key in ("plugin_id", "plugin_version"):
            if not isinstance(event_source[key], str) or not event_source[key]:
                _abort("trade_analysis_input_invalid")
        for key in ("rules_fingerprint", "row_set_fingerprint", "semantic_binding_fingerprint"):
            if not isinstance(event_source[key], str) or not re.fullmatch(r"[a-f0-9]{64}", event_source[key]):
                _abort("trade_analysis_input_invalid")
    annual_sources = []
    observed_years: set[int] = set()
    for model in annual_models:
        annual_status, annual = _artifact(model, "annual")
        year = annual.get("tax_year")
        if not isinstance(year, int) or not 1900 <= year <= 9999 or year in observed_years:
            _abort("trade_analysis_input_invalid")
        observed_years.add(year)
        if annual.get("projection_mode") != "realized_annual":
            _abort("trade_analysis_source_mismatch")
        source = {
            "status": annual_status, "artifact_ref": _ref(annual.get("artifact_ref")),
            "source_artifact_ref": _ref(annual.get("source_artifact_ref")), "tax_year": year,
            "plugin_id": annual.get("plugin_id"), "plugin_version": annual.get("plugin_version"),
            "rules_fingerprint": annual.get("rules_fingerprint"), "row_set_fingerprint": annual.get("row_set_fingerprint"),
            "semantic_binding_fingerprint": annual.get("semantic_binding_fingerprint"),
            "readiness_status": annual.get("readiness_status"), "completed_at_utc": _utc(annual.get("completed_at_utc")),
        }
        if (event_source is None or source["source_artifact_ref"] != event_source["artifact_ref"] or
            annual.get("semantic_source_bindings") != semantic_bindings or
            annual.get("semantic_binding_fingerprint") != semantic_fingerprint):
            _abort("trade_analysis_source_mismatch")
        if source["readiness_status"] not in {"complete", "partial_blocked"}:
            _abort("trade_analysis_input_invalid")
        for key in ("plugin_id", "plugin_version"):
            if not isinstance(source[key], str) or not source[key]:
                _abort("trade_analysis_input_invalid")
        for key in ("rules_fingerprint", "row_set_fingerprint", "semantic_binding_fingerprint"):
            if not isinstance(source[key], str) or not re.fullmatch(r"[a-f0-9]{64}", source[key]):
                _abort("trade_analysis_input_invalid")
        annual_sources.append(source)
    return {"realized": realized_source, "event_tax": event_source, "annual_tax": sorted(annual_sources, key=lambda row: row["tax_year"])}


def _timeline(realized_model: Mapping[str, Any], event_model: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    tables = realized_model["tables"]
    fifo_rows = tables.get("event-results.csv")
    if not isinstance(fifo_rows, list):
        _abort("trade_analysis_source_incomplete")
    _no_forbidden_rows(fifo_rows)
    tax_by_event: dict[str, Mapping[str, Any]] = {}
    event_status = None
    if event_model is not None:
        event_status = event_model["status"]
        event_artifact = event_model["artifact"]
        _no_forbidden_rows(event_model["rows"])
        for row in event_model["rows"]:
            event_ref = _ref(row.get("event_ref"))
            if event_ref in tax_by_event:
                _abort("trade_analysis_input_invalid")
            tax_by_event[event_ref] = row
        if set(tax_by_event) != {_ref(row.get("event_ref")) for row in fifo_rows}:
            _abort("trade_analysis_source_mismatch")
    result = []
    seen: set[str] = set()
    for raw in fifo_rows:
        event_ref = _ref(raw.get("event_ref"))
        if event_ref in seen:
            _abort("trade_analysis_input_invalid")
        seen.add(event_ref)
        tax = tax_by_event.get(event_ref)
        fifo_status = raw.get("projection_status")
        if not isinstance(fifo_status, str) or not fifo_status:
            _abort("trade_analysis_input_invalid")
        related = raw.get("related_account_ref") or None
        if related is not None:
            related = _ref(related)
        amount = raw.get("amount_decimal") or None
        fee = raw.get("fee_decimal") or "0"
        gross_proceeds = raw.get("gross_proceeds_decimal") or "0"
        gross_gain = raw.get("realized_gross_gain_decimal") or "0"
        gross_income = raw.get("gross_income_decimal") or "0"
        cash_delta = raw.get("cash_balance_delta_decimal") or "0"
        tax_status = "unavailable"
        tax_bucket = projected_tax = projected_net = failure = None
        if tax is not None:
            if tax.get("tax_year") != int(str(raw.get("local_date"))[:4]) or tax.get("plugin_id") != event_artifact.get("plugin_id") or tax.get("plugin_version") != event_artifact.get("plugin_version") or tax.get("rules_fingerprint") != event_artifact.get("rules_fingerprint") or tax.get("disclaimer_code") != "model_projection_not_legal_advice":
                _abort("trade_analysis_source_mismatch")
            factual_pairs = {
                "effective_at_utc": raw.get("effective_at_utc"), "local_date": raw.get("local_date"),
                "event_type": raw.get("event_type"), "account_ref": raw.get("account_ref"),
                "asset_ref": raw.get("asset_ref"), "currency": raw.get("currency"),
                "gross_proceeds_decimal": gross_proceeds, "realized_gross_gain_decimal": gross_gain,
                "gross_income_decimal": gross_income, "fee_decimal": fee,
            }
            if any(tax.get(key) != value for key, value in factual_pairs.items()):
                _abort("trade_analysis_source_mismatch")
            if tax.get("projection_status") == "completed":
                tax_status = "stale" if event_status == "stale" else "completed"
                tax_bucket = tax.get("tax_bucket")
                projected_tax = _decimal(tax.get("projected_event_tax_decimal"))
                projected_net = _decimal(tax.get("projected_net_gain_decimal"))
            elif tax.get("projection_status") == "blocked":
                tax_status = "blocked"; failure = tax.get("failure_code")
                if not isinstance(failure, str) or not failure:
                    _abort("trade_analysis_input_invalid")
            else:
                _abort("trade_analysis_input_invalid")
        row = {
            "event_ref": event_ref, "effective_at_utc": _utc(raw.get("effective_at_utc"), nullable=True),
            "local_date": _date(raw.get("local_date")), "event_type": raw.get("event_type"),
            "account_ref": _ref(raw.get("account_ref")), "related_account_ref": related,
            "asset_ref": _ref(raw.get("asset_ref")), "asset_type": raw.get("asset_type"),
            "currency": raw.get("currency"), "quantity_decimal": _decimal(raw.get("quantity_decimal"), nullable=True),
            "amount_decimal": _decimal(amount, nullable=True), "fee_decimal": _decimal(fee),
            "gross_proceeds_decimal": _decimal(gross_proceeds), "realized_gross_gain_decimal": _decimal(gross_gain),
            "gross_income_decimal": _decimal(gross_income), "cash_balance_delta_decimal": _decimal(cash_delta),
            "fifo_projection_status": fifo_status, "semantic_contract": raw.get("semantic_contract", "portfolio_ledger_v1_transaction_fact"),
            "coupled_transaction_fact": raw.get("coupled_transaction_fact", "1") == "1",
            "automatic_cash_posting_created": None if raw.get("automatic_cash_posting_created") is None else raw.get("automatic_cash_posting_created") == "1",
            "tax_bucket": tax_bucket,
            "projected_event_tax_decimal": projected_tax, "projected_event_net_gain_decimal": projected_net,
            "event_tax_status": tax_status, "event_tax_failure_code": failure,
        }
        if row["event_type"] not in {"buy", "sell", "deposit", "withdrawal", "transfer", "dividend", "stock_dividend", "interest", "reward", "fee", "adjustment", "other"}:
            _abort("trade_analysis_input_invalid")
        if row["semantic_contract"] not in _SEMANTIC_CONTRACTS or (row["semantic_contract"] == "asset_activity_v1" and (row["coupled_transaction_fact"] or row["automatic_cash_posting_created"] is not False)) or (row["semantic_contract"] == "portfolio_ledger_v1_transaction_fact" and (not row["coupled_transaction_fact"] or row["automatic_cash_posting_created"] is not None)):
            _abort("trade_analysis_input_invalid")
        if not isinstance(row["asset_type"], str) or not row["asset_type"] or not isinstance(row["currency"], str) or re.fullmatch(r"[A-Z]{3}", row["currency"]) is None:
            _abort("trade_analysis_input_invalid")
        result.append(row)
    return sorted(result, key=lambda row: (row["local_date"], row["effective_at_utc"] is not None, row["effective_at_utc"] or "", row["event_ref"]))


def _positions(realized_model: Mapping[str, Any]) -> list[dict[str, Any]]:
    tables = realized_model["tables"]
    summaries = tables.get("position-summary.csv"); history = tables.get("position-history.csv")
    if not isinstance(summaries, list) or not isinstance(history, list):
        _abort("trade_analysis_source_incomplete")
    _no_forbidden_rows(summaries); _no_forbidden_rows(history)
    position_refs: dict[tuple[str, str], str] = {}
    for row in summaries:
        key = (_ref(row.get("account_ref")), _ref(row.get("asset_ref")))
        value = _ref(row.get("position_ref"))
        if key in position_refs and position_refs[key] != value:
            _abort("trade_analysis_input_invalid")
        position_refs[key] = value
    result = []
    for raw in history:
        account = _ref(raw.get("account_ref")); asset = _ref(raw.get("asset_ref")); key = (account, asset)
        if key not in position_refs:
            _abort("trade_analysis_source_mismatch")
        currency = raw.get("currency")
        if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None:
            _abort("trade_analysis_input_invalid")
        try: sequence = int(raw.get("history_sequence"))
        except (TypeError, ValueError): _abort("trade_analysis_input_invalid")
        result.append({
            "history_sequence": sequence, "event_ref": _ref(raw.get("event_ref")),
            "effective_at_utc": _utc(raw.get("effective_at_utc"), nullable=True), "position_ref": position_refs[key],
            "account_ref": account, "asset_ref": asset, "currency": currency,
            "position_quantity_decimal": _decimal(raw.get("position_quantity_decimal")),
            "fifo_cost_balance_decimal": _decimal(raw.get("fifo_cost_balance_decimal")),
            "cumulative_realized_gross_gain_decimal": _decimal(raw.get("cumulative_realized_gross_gain_decimal")),
            "cumulative_gross_income_decimal": _decimal(raw.get("cumulative_gross_income_decimal")),
            "cash_balance_decimal": _decimal(raw.get("cash_balance_decimal")),
        })
    return sorted(result, key=lambda row: (row["effective_at_utc"] is not None, row["effective_at_utc"] or "", row["history_sequence"], row["position_ref"]))


def _periods(timeline: Sequence[Mapping[str, Any]], event_source_status: str | None) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for event in timeline:
        month = event["local_date"][:7]; key = (event["currency"], month)
        row = grouped.setdefault(key, {
            "event_count": 0, "realized": Decimal(0), "income": Decimal(0), "fee": Decimal(0),
            "deposit": Decimal(0), "withdrawal": Decimal(0), "transfer": Decimal(0),
            "tax": Decimal(0), "net": Decimal(0), "tax_complete": True, "refs": [],
        })
        row["event_count"] += 1; row["refs"].append(event["event_ref"])
        row["realized"] += _d(event["realized_gross_gain_decimal"]); row["income"] += _d(event["gross_income_decimal"]); row["fee"] += _d(event["fee_decimal"])
        amount = _d(event["amount_decimal"] or "0")
        if event["event_type"] == "deposit": row["deposit"] += amount
        elif event["event_type"] == "withdrawal": row["withdrawal"] += amount
        elif event["event_type"] == "transfer": row["transfer"] += amount
        if event["event_tax_status"] in {"completed", "stale"}:
            row["tax"] += _d(event["projected_event_tax_decimal"]); row["net"] += _d(event["projected_event_net_gain_decimal"])
        else: row["tax_complete"] = False
    result = []
    cumulative: dict[str, dict[str, Decimal | None]] = {}
    for (currency, month), raw in sorted(grouped.items()):
        year, month_value = map(int, month.split("-")); end = calendar.monthrange(year, month_value)[1]
        cum = cumulative.setdefault(currency, {key: Decimal(0) for key in ("realized", "income", "fee", "deposit", "withdrawal", "transfer", "tax", "net")})
        for key in ("realized", "income", "fee", "deposit", "withdrawal", "transfer"): cum[key] += raw[key]
        if raw["tax_complete"] and cum["tax"] is not None:
            cum["tax"] += raw["tax"]; cum["net"] += raw["net"]
        else: cum["tax"] = None; cum["net"] = None
        tax_status = "unavailable" if event_source_status is None else "stale" if event_source_status == "stale" else "completed" if raw["tax_complete"] else "partial_blocked"
        result.append({
            "period_start": f"{month}-01", "period_end": f"{month}-{end:02d}", "period_granularity": "month",
            "currency": currency, "event_count": raw["event_count"],
            "realized_gross_gain_decimal": _text(raw["realized"]), "gross_income_decimal": _text(raw["income"]),
            "fee_total_decimal": _text(raw["fee"]), "deposit_decimal": _text(raw["deposit"]),
            "withdrawal_decimal": _text(raw["withdrawal"]), "transfer_decimal": _text(raw["transfer"]),
            "projected_event_tax_decimal": _text(raw["tax"]) if raw["tax_complete"] else None,
            "projected_event_net_gain_decimal": _text(raw["net"]) if raw["tax_complete"] else None,
            "event_tax_status": tax_status,
            "cumulative_realized_gross_gain_decimal": _text(cum["realized"]),
            "cumulative_gross_income_decimal": _text(cum["income"]), "cumulative_fee_total_decimal": _text(cum["fee"]),
            "cumulative_deposit_decimal": _text(cum["deposit"]), "cumulative_withdrawal_decimal": _text(cum["withdrawal"]),
            "cumulative_transfer_decimal": _text(cum["transfer"]),
            "cumulative_projected_event_tax_decimal": _text(cum["tax"]) if cum["tax"] is not None else None,
            "cumulative_projected_event_net_gain_decimal": _text(cum["net"]) if cum["net"] is not None else None,
            "source_event_refs": sorted(set(raw["refs"])),
        })
    return result


def _annual(annual_models: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for model in annual_models:
        stale = model["status"] == "stale"; artifact = model["artifact"]; _no_forbidden_rows(model["rows"])
        for raw in model["rows"]:
            status = raw.get("projection_status")
            if status not in {"completed", "blocked"}: _abort("trade_analysis_input_invalid")
            if raw.get("tax_year") != artifact.get("tax_year") or raw.get("plugin_id") != artifact.get("plugin_id") or raw.get("plugin_version") != artifact.get("plugin_version") or raw.get("rules_fingerprint") != artifact.get("rules_fingerprint") or raw.get("disclaimer_code") != "model_projection_not_legal_advice":
                _abort("trade_analysis_source_mismatch")
            result.append({
                "tax_year": raw.get("tax_year"), "row_type": raw.get("row_type"), "tax_bucket": raw.get("tax_bucket"),
                "currency": raw.get("currency"), "positive_contribution_decimal": _decimal(raw.get("positive_contribution_decimal")),
                "negative_contribution_decimal": _decimal(raw.get("negative_contribution_decimal")),
                "net_contribution_decimal": _decimal(raw.get("net_contribution_decimal")),
                "closing_loss_carryforward_decimal": _decimal(raw.get("closing_loss_carryforward_decimal")),
                "allowance_used_decimal": _decimal(raw.get("allowance_used_decimal")),
                "withholding_credit_decimal": _decimal(raw.get("withholding_credit_decimal")),
                "projected_annual_tax_decimal": _decimal(raw.get("projected_annual_tax_decimal"), nullable=True),
                "projected_annual_net_gain_decimal": _decimal(raw.get("projected_net_gain_decimal"), nullable=True),
                "defaulted_parameter_codes": raw.get("defaulted_parameter_codes"),
                "projection_status": "stale" if stale and status == "completed" else status,
                "failure_code": raw.get("failure_code"), "disclaimer_code": raw.get("disclaimer_code"),
            })
    for row in result:
        if not isinstance(row["tax_year"], int) or row["row_type"] not in {"bucket", "summary"} or not isinstance(row["tax_bucket"], str) or not isinstance(row["currency"], str) or re.fullmatch(r"[A-Z]{3}", row["currency"]) is None or not isinstance(row["defaulted_parameter_codes"], str) or row["disclaimer_code"] != "model_projection_not_legal_advice":
            _abort("trade_analysis_input_invalid")
        positive = _d(row["positive_contribution_decimal"]); negative = _d(row["negative_contribution_decimal"]); net = _d(row["net_contribution_decimal"])
        if positive < 0 or negative > 0 or net != positive + negative:
            _abort("trade_analysis_reconciliation_failed")
        if row["projection_status"] in {"completed", "stale"}:
            if row["projected_annual_tax_decimal"] is None or row["projected_annual_net_gain_decimal"] is None:
                _abort("trade_analysis_source_incomplete")
            if _d(row["projected_annual_tax_decimal"]) < 0:
                _abort("trade_analysis_reconciliation_failed")
        if row["projection_status"] == "blocked" and (row["projected_annual_tax_decimal"] is not None or row["projected_annual_net_gain_decimal"] is not None):
            _abort("trade_analysis_reconciliation_failed")
    for key in {(row["tax_year"], row["currency"]) for row in result}:
        scoped = [row for row in result if (row["tax_year"], row["currency"]) == key]
        summaries = [row for row in scoped if row["row_type"] == "summary"]; buckets = [row for row in scoped if row["row_type"] == "bucket"]
        if len(summaries) != 1:
            _abort("trade_analysis_input_invalid")
        for field in ("positive_contribution_decimal", "negative_contribution_decimal", "net_contribution_decimal"):
            if _d(summaries[0][field]) != sum((_d(row[field]) for row in buckets), Decimal(0)):
                _abort("trade_analysis_reconciliation_failed")
    return sorted(result, key=lambda row: (row["tax_year"], row["currency"], row["row_type"], row["tax_bucket"]))


def _currency_metrics(realized_model: Mapping[str, Any], timeline: Sequence[Mapping[str, Any]], event_status: str | None) -> list[dict[str, Any]]:
    summaries = realized_model["tables"].get("currency-summary.csv"); positions = realized_model["tables"].get("position-summary.csv")
    if not isinstance(summaries, list) or not isinstance(positions, list): _abort("trade_analysis_source_incomplete")
    result = []
    for raw in summaries:
        currency = raw.get("currency"); events = [row for row in timeline if row["currency"] == currency]
        tax_complete = event_status is not None and all(row["event_tax_status"] in {"completed", "stale"} for row in events)
        source_totals = {
            "realized_gross_proceeds_decimal": sum((_d(row["gross_proceeds_decimal"]) for row in events), Decimal(0)),
            "realized_gross_gain_decimal": sum((_d(row["realized_gross_gain_decimal"]) for row in events), Decimal(0)),
            "gross_income_decimal": sum((_d(row["gross_income_decimal"]) for row in events), Decimal(0)),
            "fee_total_decimal": sum((_d(row["fee_decimal"]) for row in events), Decimal(0)),
            "cash_balance_decimal": sum((_d(row["cash_balance_delta_decimal"]) for row in events), Decimal(0)),
            "realized_fifo_cost_decimal": sum((_d(row.get("realized_fifo_cost_decimal") or "0") for row in positions if row.get("currency") == currency), Decimal(0)),
        }
        for field, expected in source_totals.items():
            if _d(raw.get(field)) != expected:
                _abort("trade_analysis_reconciliation_failed")
        status = "unavailable" if event_status is None else "stale" if event_status == "stale" else "completed" if tax_complete else "partial_blocked"
        result.append({
            "currency": currency, "position_count": sum(1 for row in positions if row.get("currency") == currency), "event_count": len(events),
            "remaining_fifo_cost_decimal": _text(sum((_d(row.get("remaining_fifo_cost_decimal") or "0") for row in positions if row.get("currency") == currency), Decimal(0))),
            "realized_gross_proceeds_decimal": _decimal(raw.get("realized_gross_proceeds_decimal")),
            "realized_fifo_cost_decimal": _decimal(raw.get("realized_fifo_cost_decimal")),
            "realized_gross_gain_decimal": _decimal(raw.get("realized_gross_gain_decimal")),
            "gross_income_decimal": _decimal(raw.get("gross_income_decimal")), "fee_total_decimal": _decimal(raw.get("fee_total_decimal")),
            "cash_balance_decimal": _decimal(raw.get("cash_balance_decimal")),
            "projected_event_tax_decimal": _text(sum((_d(row["projected_event_tax_decimal"]) for row in events), Decimal(0))) if tax_complete else None,
            "projected_event_net_gain_decimal": _text(sum((_d(row["projected_event_net_gain_decimal"]) for row in events), Decimal(0))) if tax_complete else None,
            "event_tax_status": status, "cross_currency_aggregation": "not_performed_without_fx",
        })
    return sorted(result, key=lambda row: row["currency"])


def _point(label: str, value: str | None, status: str, refs: Sequence[str], seed: Any) -> dict[str, Any]:
    return {"point_ref": _sha_ref("tap", seed), "period_label": label, "x_basis_points": None, "y_basis_points": None, "value_decimal": value, "point_status": status, "source_refs": sorted(set(refs))}


def _plots(portfolio_ref: str, periods: Sequence[Mapping[str, Any]], positions: Sequence[Mapping[str, Any]], annual: Sequence[Mapping[str, Any]], source: Mapping[str, Any]) -> list[dict[str, Any]]:
    plots: list[dict[str, Any]] = []
    period_specs = (
        ("realized_gross_gain_history", "periodic_realized_gross_gain", "realized_gross_gain_decimal", "none"),
        ("income_history", "periodic_gross_income", "gross_income_decimal", "none"),
        ("fee_history", "periodic_fee_total", "fee_total_decimal", "none"),
        ("cash_movement_history", "deposit", "deposit_decimal", "none"),
        ("cash_movement_history", "withdrawal", "withdrawal_decimal", "none"),
        ("cash_movement_history", "transfer", "transfer_decimal", "none"),
        ("projected_event_net_history", "projected_event_net_gain", "projected_event_net_gain_decimal", "event"),
    )
    for currency in sorted({row["currency"] for row in periods}):
        rows = [row for row in periods if row["currency"] == currency]
        for plot_code, metric, field, tax_scope in period_specs:
            status = "stale" if source["realized"]["status"] == "stale" or source["event_tax"] is not None and source["event_tax"]["status"] == "stale" and tax_scope == "event" else "partial_blocked" if any(row["event_tax_status"] == "partial_blocked" for row in rows) and tax_scope == "event" else "unavailable" if all(row[field] is None for row in rows) else "completed"
            points = [_point(row["period_start"][:7], row[field], "stale" if status == "stale" and row[field] is not None else "blocked" if status == "partial_blocked" and row[field] is None else "unavailable" if row[field] is None else "completed", row["source_event_refs"], [plot_code, metric, currency, row["period_start"]]) for row in rows]
            plots.append({"plot_code": plot_code, "metric_code": metric, "currency": currency, "scope_ref": portfolio_ref, "tax_scope": tax_scope, "series_status": status, "zero_line_y_basis_points": None, "points": points})
    position_specs = (
        ("position_fifo_cost_history", "remaining_fifo_cost", "fifo_cost_balance_decimal"),
        ("position_quantity_history", "position_quantity", "position_quantity_decimal"),
        ("position_cash_balance_history", "cash_balance", "cash_balance_decimal"),
    )
    for position_ref in sorted({row["position_ref"] for row in positions}):
        rows = [row for row in positions if row["position_ref"] == position_ref]
        currency = rows[0]["currency"]
        for plot_code, metric, field in position_specs:
            status = "stale" if source["realized"]["status"] == "stale" else "completed"
            points = [_point(row["effective_at_utc"], row[field], "stale" if status == "stale" else "completed", [row["event_ref"]], [plot_code, position_ref, row["event_ref"]]) for row in rows]
            plots.append({"plot_code": plot_code, "metric_code": metric, "currency": currency, "scope_ref": position_ref, "tax_scope": "none", "series_status": status, "zero_line_y_basis_points": None, "points": points})
    annual_source_by_year = {row["tax_year"]: row for row in source["annual_tax"]}
    for currency in sorted({row["currency"] for row in annual if row["row_type"] == "summary"}):
        rows = [row for row in annual if row["row_type"] == "summary" and row["currency"] == currency]
        for plot_code, metric, field in (("annual_tax_history", "annual_tax", "projected_annual_tax_decimal"), ("annual_net_gain_history", "annual_net_gain", "projected_annual_net_gain_decimal")):
            points = []
            for row in rows:
                status = "stale" if row["projection_status"] == "stale" else "blocked" if row["projection_status"] == "blocked" else "completed"
                points.append(_point(str(row["tax_year"]), row[field], status, [annual_source_by_year[row["tax_year"]]["artifact_ref"]], [plot_code, currency, row["tax_year"]]))
            series_status = "stale" if any(point["point_status"] == "stale" for point in points) else "partial_blocked" if any(point["point_status"] == "blocked" for point in points) else "unavailable" if not points else "completed"
            plots.append({"plot_code": plot_code, "metric_code": metric, "currency": currency, "scope_ref": portfolio_ref, "tax_scope": "annual", "series_status": series_status, "zero_line_y_basis_points": None, "points": points})
    # Scale every visual plot/currency group together. Exact tooltip values remain untouched.
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for series in plots: groups.setdefault((series["plot_code"], series["currency"]), []).append(series)
    for group in groups.values():
        values = [_d(point["value_decimal"]) for series in group for point in series["points"] if point["value_decimal"] is not None]
        low = min(values + [Decimal(0)]) if values else Decimal(0); high = max(values + [Decimal(0)]) if values else Decimal(0)
        edge = Decimal(500); span = Decimal(9000)
        zero = 5000 if low == high else int(edge + (high / (high - low)) * span)
        for series in group:
            count = len(series["points"])
            series["zero_line_y_basis_points"] = zero if values else None
            for index, point in enumerate(series["points"]):
                point["x_basis_points"] = 5000 if count == 1 else int(edge + Decimal(index) * span / Decimal(count - 1))
                if point["value_decimal"] is not None:
                    point["y_basis_points"] = 5000 if low == high else int(edge + (high - _d(point["value_decimal"])) * span / (high - low))
            series["series_ref"] = _sha_ref("tas", {key: series[key] for key in ("plot_code", "metric_code", "currency", "scope_ref", "tax_scope")})
    return sorted(plots, key=lambda row: (row["plot_code"], row["currency"], row["metric_code"], row["scope_ref"]))


def _extra_contributions(values: Sequence[Mapping[str, Any]]) -> dict[tuple[int, str], Decimal]:
    """Jahresposten ohne FIFO-Ereignis (Zinsen der Cash-Konten, Vorabpauschalen samt Minderung beim Verkauf): die Jahresrechnung
    rechnet sie mit, die Ereignisprojektion nicht. Je Steuerjahr und Waehrung eine Summe."""
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        _abort("trade_analysis_input_invalid")
    result: dict[tuple[int, str], Decimal] = {}
    for value in values:
        if not isinstance(value, Mapping) or set(value) != {"tax_year", "currency", "amount_decimal"} or not isinstance(value["tax_year"], int) \
                or isinstance(value["tax_year"], bool) or not isinstance(value["currency"], str) or re.fullmatch(r"[A-Z]{3}", value["currency"]) is None:
            _abort("trade_analysis_input_invalid")
        key = (value["tax_year"], value["currency"])
        if key in result:
            _abort("trade_analysis_input_invalid")
        result[key] = _d(_decimal(value["amount_decimal"]))
    return result


def _build_trade_analysis_artifact_v1(*, realized_read_model: Mapping[str, Any], event_tax_read_model: Mapping[str, Any] | None, annual_tax_read_models: Sequence[Mapping[str, Any]], tenant_id: str, user_id: str, data_space_id: str, portfolio_label: str, completed_at_utc: str,
                                      annual_extra_contributions: Sequence[Mapping[str, Any]] = (), event_tax_selected: bool = True) -> dict[str, Any]:
    # Ohne gewaehltes Steuermodul (#564, rc.406) fehlt das Ereignis-Steuermodell gewollt: kein Grund fuer "partial". Die Zeilen bleiben
    # "unavailable" (es wurde keine Steuer gerechnet), der Stand der Analyse ist abgeschlossen. Gewaehlt, aber fehlend bleibt "partial".
    if not event_tax_selected and (event_tax_read_model is not None or annual_tax_read_models):
        _abort("trade_analysis_input_invalid")
    if not all(isinstance(value, str) and _CONTEXT.fullmatch(value) and len(value) <= 64 for value in (tenant_id, user_id, data_space_id)) or re.fullmatch(r"sbx_[a-z0-9_]{4,60}", data_space_id) is None:
        _abort("trade_analysis_context_invalid")
    if not isinstance(portfolio_label, str) or not 1 <= len(portfolio_label.encode("utf-8")) <= 160 or re.search(r"[\x00-\x1f\x7f]", portfolio_label):
        _abort("trade_analysis_input_invalid")
    if not isinstance(annual_tax_read_models, Sequence) or isinstance(annual_tax_read_models, (str, bytes)):
        _abort("trade_analysis_input_invalid")
    completed = _utc(completed_at_utc)
    source = _source(realized_read_model, event_tax_read_model, annual_tax_read_models)
    source_completion_times = [source["realized"]["completed_at_utc"]]
    if source["event_tax"] is not None: source_completion_times.append(source["event_tax"]["completed_at_utc"])
    source_completion_times.extend(row["completed_at_utc"] for row in source["annual_tax"])
    if any(value > completed for value in source_completion_times):
        _abort("trade_analysis_input_invalid")
    realized_artifact = realized_read_model["artifact"]; portfolio_ref = _ref(realized_artifact.get("portfolio_ref"))
    if event_tax_read_model is not None and event_tax_read_model["artifact"].get("portfolio_ref") != portfolio_ref:
        _abort("trade_analysis_source_mismatch")
    if any(model["artifact"].get("portfolio_ref") != portfolio_ref for model in annual_tax_read_models):
        _abort("trade_analysis_source_mismatch")
    timeline = _timeline(realized_read_model, event_tax_read_model)
    positions = _positions(realized_read_model)
    annual = _annual(annual_tax_read_models)
    extra = _extra_contributions(annual_extra_contributions)
    for row in annual:
        if row["row_type"] != "summary" or row["projection_status"] == "blocked":
            continue
        scoped = [event for event in timeline if int(event["local_date"][:4]) == row["tax_year"] and event["currency"] == row["currency"]]
        if all(event["event_tax_status"] in {"completed", "stale"} for event in scoped):
            economic_gain = sum((_d(event["realized_gross_gain_decimal"]) + _d(event["gross_income_decimal"]) for event in scoped), Decimal(0))
            economic_gain += extra.get((row["tax_year"], row["currency"]), Decimal(0))   # Zinsen, Vorabpauschalen (rc.262/rc.263)
            if _d(row["projected_annual_net_gain_decimal"]) != economic_gain - _d(row["projected_annual_tax_decimal"]):
                _abort("trade_analysis_reconciliation_failed")
    periods = _periods(timeline, None if event_tax_read_model is None else event_tax_read_model["status"])
    currency_metrics = _currency_metrics(realized_read_model, timeline, None if event_tax_read_model is None else event_tax_read_model["status"])
    event_scopes = {(int(row["local_date"][:4]), row["currency"]) for row in timeline}
    annual_scopes = {(row["tax_year"], row["currency"]) for row in annual if row["row_type"] == "summary" and row["projection_status"] in {"completed", "stale"}}
    stale = source["realized"]["status"] == "stale" or source["event_tax"] is not None and source["event_tax"]["status"] == "stale" or any(row["status"] == "stale" for row in source["annual_tax"])
    partial = event_tax_selected and (source["event_tax"] is None or source["event_tax"]["readiness_status"] == "partial_blocked" or not event_scopes.issubset(annual_scopes))
    projection_status = "stale" if stale else "partial" if partial else "completed"
    currencies = sorted({row["currency"] for row in timeline} | {row["currency"] for row in annual})
    body = {
        "trade_analysis_artifact_version": 1,
        "trade_analysis_artifact_id": _sha_ref("taa", {"portfolio_ref": portfolio_ref, "source": source, "completed_at_utc": completed}),
        "status": "completed", "projection_status": projection_status,
        "tenant_id": tenant_id, "user_id": user_id, "data_space_id": data_space_id,
        "portfolio_ref": portfolio_ref, "portfolio_label": portfolio_label,
        "analysis_cutoff_at_utc": source["realized"]["evidence_cutoff_at_utc"], "completed_at_utc": completed,
        "currency_status": "empty" if not currencies else "single_currency" if len(currencies) == 1 else "native_currency_slices",
        "source": source, "metric_definitions": _load_metric_definitions(),
        "currency_metrics": currency_metrics, "event_timeline": timeline, "position_history": positions,
        "period_series": periods, "annual_tax": annual,
        "plot_series": _plots(portfolio_ref, periods, positions, annual, source),
        "disclaimers": ["trade_based_no_market_values", "event_tax_is_not_annual_tax", "tax_projection_not_legal_advice_or_filing"],
        "market_status": "unavailable_m4_required",
        "boundaries": {key: False for key in ("provider_access", "network_access", "market_calculation", "unrealized_calculation", "forecasting", "technical_analysis", "ai_inference", "alarm_eligibility", "notification_eligibility", "app_side_calculation", "canonical_write")},
    }
    if completed < body["analysis_cutoff_at_utc"]:
        _abort("trade_analysis_input_invalid")
    body["artifact_fingerprint"] = fingerprint(body)
    return body


def build_trade_analysis_artifact_v1(*, realized_read_model: Mapping[str, Any], event_tax_read_model: Mapping[str, Any] | None, annual_tax_read_models: Sequence[Mapping[str, Any]], tenant_id: str, user_id: str, data_space_id: str, portfolio_label: str, completed_at_utc: str,
                                     annual_extra_contributions: Sequence[Mapping[str, Any]] = (), event_tax_selected: bool = True) -> dict[str, Any]:
    # Canonical Decimal text is limited to 80 characters. Precision 240 therefore
    # preserves every operation for any in-memory row count this Worker can hold.
    with localcontext() as context:
        context.prec = 240
        return _build_trade_analysis_artifact_v1(
            realized_read_model=realized_read_model,
            event_tax_read_model=event_tax_read_model,
            annual_tax_read_models=annual_tax_read_models,
            tenant_id=tenant_id,
            user_id=user_id,
            data_space_id=data_space_id,
            portfolio_label=portfolio_label,
            completed_at_utc=completed_at_utc,
            annual_extra_contributions=annual_extra_contributions,
            event_tax_selected=event_tax_selected,
        )
