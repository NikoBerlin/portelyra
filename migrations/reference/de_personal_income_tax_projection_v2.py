#!/usr/bin/env python3
"""Completed-report binding for the optional German reference Tax model v2."""
from __future__ import annotations

from typing import Any, Mapping

from migrations.reference.tax_model_plugin_v2 import TaxPluginV2RunResult


class DePersonalIncomeTaxV2Blocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise DePersonalIncomeTaxV2Blocked(code)


def completed_de_personal_income_tax_projection_v2(result: TaxPluginV2RunResult) -> dict[str, Any]:
    """Bind immutable model/rule/parameter fingerprints and permanent disclaimers."""

    if (
        not isinstance(result, TaxPluginV2RunResult)
        or result.plugin_id != "tax_de_personal_income_tax_projection_v2"
        # Jede Fassung des Moduls 2 (#486 Schritt 2): gleiche Schnittstelle, die Version nennt die Fassung.
        or not isinstance(result.plugin_version, str) or not result.plugin_version.startswith("2.")
        or result.projection_mode not in {"realized_event", "realized_annual"}
    ):
        _abort("de_personal_income_tax_v2_result_invalid")
    required_disclaimers = {
        "model_projection_not_legal_advice",
        "reference_model_no_automatic_legal_update",
        "church_tax_user_confirmation_only",
    }
    if not required_disclaimers <= set(result.disclaimer_codes):
        _abort("de_personal_income_tax_v2_result_invalid")
    reconciliation = dict(result.reconciliation)
    if (
        reconciliation.get("event_tax_is_annual_tax") is not False
        or reconciliation.get("church_tax_basis") != "projected_income_tax"
        or reconciliation.get("church_tax_identity_inference") is not False
    ):
        _abort("de_personal_income_tax_v2_result_invalid")
    rows = [dict(row) for row in result.rows]
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or row.get("model_fingerprint") != result.model_fingerprint
            or row.get("rules_fingerprint") != result.rules_fingerprint
            or row.get("parameter_fingerprint") != result.parameter_fingerprint
            or row.get("disclaimer_code") != "model_projection_not_legal_advice"
        ):
            _abort("de_personal_income_tax_v2_result_invalid")
    return {
        "contract_version": "de_personal_income_tax_completed_projection_v2",
        "status": "completed",
        "projection_mode": result.projection_mode,
        "plugin_id": result.plugin_id,
        "plugin_version": result.plugin_version,
        "model_fingerprint": result.model_fingerprint,
        "rules_fingerprint": result.rules_fingerprint,
        "parameter_fingerprint": result.parameter_fingerprint,
        "rows": rows,
        "reconciliation": reconciliation,
        "disclaimer_codes": list(result.disclaimer_codes),
        "provider_access": False,
        "network_access": False,
        "filing_evidence": False,
    }


__all__ = [
    "DePersonalIncomeTaxV2Blocked",
    "completed_de_personal_income_tax_projection_v2",
]
