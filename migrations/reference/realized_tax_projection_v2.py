#!/usr/bin/env python3
"""Additive validators for German Tax Model v2 Event and Annual candidates."""
from __future__ import annotations

from typing import Any

from migrations.reference import realized_tax_projection_v1 as base
from migrations.reference.tax_model_plugin_v1 import TaxPluginRunResult, TaxPluginSelection
from migrations.reference.tax_model_plugin_v2 import TaxPluginV2RunResult

V2_FIELDS = {"model_fingerprint", "parameter_fingerprint"}
# tax_year_rules_missing: Das Modul fuehrt fuer das Jahr des Ereignisses keinen
# Rechtsstand. Die Zeile bleibt ohne Steuerzahl und sagt es; der Lauf geht weiter.
# tax_fund_old_investment_tax_act (#496): Fonds vor 2018 oder Altanteile - altes Investmentsteuergesetz, nicht abgebildet.
V2_FAILURES = {"church_tax_applicability_required", "church_tax_rate_required", "tax_year_rules_missing", "tax_fund_old_investment_tax_act"}


class RealizedTaxV2Blocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _abort() -> None:
    raise RealizedTaxV2Blocked("realized_tax_plugin_output_invalid")


def _base_result(result: TaxPluginV2RunResult, rows: list[dict[str, Any]]) -> TaxPluginRunResult:
    stripped = []
    for raw in rows:
        row = dict(raw)
        if row.pop("model_fingerprint", None) != result.model_fingerprint or row.pop("parameter_fingerprint", None) != result.parameter_fingerprint:
            _abort()
        stripped.append(row)
    return TaxPluginRunResult(
        result.run_ref, result.plugin_id, result.plugin_version, result.rules_fingerprint,
        result.projection_mode, result.input_fingerprint, result.output_fingerprint,
        tuple(stripped), result.reconciliation, result.disclaimer_codes,
    )


def _selection(selection: TaxPluginSelection, result: TaxPluginV2RunResult) -> TaxPluginSelection:
    if not isinstance(selection, TaxPluginSelection):
        _abort()
    if (selection.plugin_id, selection.plugin_version, selection.rules_fingerprint) != (result.plugin_id, result.plugin_version, result.rules_fingerprint):
        _abort()
    return selection


def validate_event_tax_candidate_v2(result: TaxPluginV2RunResult, bound_input: dict[str, Any], selection: TaxPluginSelection) -> list[dict[str, Any]]:
    if not isinstance(result, TaxPluginV2RunResult) or result.projection_mode != "realized_event":
        _abort()
    rows = [dict(row) for row in result.rows]
    blocked = [row for row in rows if row.get("failure_code") in V2_FAILURES]
    for row in blocked:
        row["failure_code"] = "tax_rate_required"
    base.validate_event_tax_candidate_v1(_base_result(result, rows), bound_input, _selection(selection, result))
    return [dict(row) for row in result.rows]


def validate_annual_tax_candidate_v2(result: TaxPluginV2RunResult, bound_input: dict[str, Any], selection: TaxPluginSelection, tax_year: int) -> list[dict[str, Any]]:
    if not isinstance(result, TaxPluginV2RunResult) or result.projection_mode != "realized_annual":
        _abort()
    rows = [dict(row) for row in result.rows]
    for row in rows:
        if row.get("failure_code") in V2_FAILURES:
            row["failure_code"] = "tax_rate_required"
    base.validate_annual_tax_candidate_v1(_base_result(result, rows), bound_input, _selection(selection, result), tax_year)
    return [dict(row) for row in result.rows]


__all__ = ["RealizedTaxV2Blocked", "validate_annual_tax_candidate_v2", "validate_event_tax_candidate_v2"]
