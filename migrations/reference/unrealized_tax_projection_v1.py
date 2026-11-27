#!/usr/bin/env python3
"""Die hypothetische Liquidation: Eingabe und Prüfung der Projektion je Position.

Der Abschluss rechnete `net_liquidation = market_value − liquidation_fee −
projected_tax` bereits — nur den Erzeuger von `projected_unrealized_tax_decimal`
gab es nicht, und jede Position trug `tax_projection_unavailable` (#367 Schritt 2).

Die Eingabe kommt aus der **bereits gerechneten Bewertung**, nicht aus dem
FIFO-Stand: Nur dort steht der unrealisierte Gewinn in Basiswährung und mit
aufgelöster Umrechnung, und `unrealized_valuation_v1` vergleicht die Zahl der
Steuerzeile anschließend mit seiner eigenen. Beide müssen deshalb dieselbe sein,
nicht nur ungefähr.

Die Haltedauer stammt aus den verbliebenen FIFO-Losen: Für privates
Veräußerungsgut ist nur der Teil steuerbar, der die Jahresfrist noch nicht
überschritten hat.

Ohne Provider, ohne Netz, ohne Schreibzugriff auf kanonische Daten.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from migrations.reference.tax_model_plugin_v1 import (
    TaxPluginSelection,
    abort,
    new_tax_plugin_bound_input_v1,
    sha,
)

ROW_FIELDS = (
    "position_ref", "asset_ref", "account_ref", "currency", "market_value_decimal",
    "fifo_cost_decimal", "unrealized_gross_gain_decimal", "liquidation_fee_decimal",
    "remaining_lots",
)
LOT_FIELDS = ("quantity_decimal", "fifo_cost_decimal", "acquisition_local_date")
RESULT_FIELDS = (
    "position_ref", "currency", "unrealized_gross_gain_decimal",
    "projected_unrealized_tax_decimal", "projection_status", "failure_code",
)


def prepare_unrealized_tax_plugin_input_v1(
    valuation: Mapping[str, Any], remaining_lots: Sequence[Mapping[str, Any]],
    selection: TaxPluginSelection, classifications: Sequence[Mapping[str, Any]],
    parameters: Sequence[Mapping[str, Any]], *, asset_ref_of: Mapping[str, str],
) -> dict[str, Any]:
    """Die gebundene Eingabe je Position aus einer gerechneten Bewertung.

    `asset_ref_of` bildet die Positionskennung der Bewertung auf die
    Assetkennung des FIFO-Raums ab - die Klassifikationen stehen in diesem Raum,
    die Bewertung führt eigene, verschleierte Kennungen.

    Positionen ohne Marktwert kommen nicht mit: Wo kein Gewinn feststeht, ist
    auch keine Steuer zu schätzen. Der Abschluss führt sie weiter als blockiert.
    """
    if not isinstance(valuation, Mapping) or not isinstance(valuation.get("items"), list):
        abort("tax_plugin_input_invalid")
    if not isinstance(selection, TaxPluginSelection) or selection.projection_mode != "unrealized_snapshot":
        abort("tax_plugin_selection_mismatch")
    lots: dict[str, list[dict[str, str]]] = {}
    for lot in remaining_lots:
        try:
            position = lot["position_ref"]
            entry = {
                "quantity_decimal": lot["remaining_quantity_decimal"],
                "fifo_cost_decimal": lot["remaining_fifo_cost_decimal"],
                "acquisition_local_date": lot["acquisition_local_date"],
            }
        except KeyError:
            abort("tax_plugin_input_invalid")
        if any(entry[key] is None for key in LOT_FIELDS):
            continue
        lots.setdefault(position, []).append(entry)
    rows = []
    for item in valuation["items"]:
        if item.get("market_value_decimal") is None or item.get("unrealized_gross_gain_decimal") is None:
            continue
        asset = asset_ref_of.get(item["position_ref"])
        if asset is None:
            continue
        rows.append({
            "position_ref": item["position_ref"], "asset_ref": asset,
            "account_ref": item["account_ref"], "currency": item["basis_currency"],
            "market_value_decimal": item["market_value_decimal"],
            "fifo_cost_decimal": item["fifo_cost_decimal"],
            "unrealized_gross_gain_decimal": item["unrealized_gross_gain_decimal"],
            "liquidation_fee_decimal": item.get("liquidation_fee_decimal"),
            # Die Lose je Position; fehlen sie, entscheidet das Modul, ob es
            # darauf ankommt - nur privates Veraeusserungsgut braucht sie.
            "remaining_lots": lots.get(item["position_ref"], []),
        })
    rows.sort(key=lambda row: row["position_ref"])
    bound = new_tax_plugin_bound_input_v1(
        projection_mode="unrealized_snapshot", portfolio_ref=valuation["portfolio_ref"],
        source_artifact_ref=valuation["snapshot_ref"], cutoff=valuation["as_of_date"],
        rows=rows, classifications=list(classifications), parameters=list(parameters),
    )
    return bound


def validate_unrealized_tax_candidate_v1(
    result: Any, bound: Mapping[str, Any], selection: TaxPluginSelection,
) -> list[dict[str, Any]]:
    """Prüft die Modulausgabe und liefert die Zeilen des Steuerartefakts.

    Geprüft wird, dass das Modul genau die vorgelegten Positionen beantwortet
    und den unrealisierten Gewinn unverändert zurückgibt - sonst rechnete es
    gegen andere Zahlen als die Bewertung, und der Abschluss würde es später
    ohnehin abweisen.
    """
    rows = getattr(result, "rows", None)
    if rows is None and isinstance(result, Mapping):
        rows = result.get("rows")
    # Die Schnittstelle liefert ein Tupel, nicht eine Liste.
    if not isinstance(rows, (list, tuple)):
        abort("tax_plugin_output_invalid")
    expected = {row["position_ref"]: row for row in bound["rows"]}
    seen: set[str] = set()
    projected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            abort("tax_plugin_output_invalid")
        position = row.get("position_ref")
        source = expected.get(position)
        if source is None or position in seen:
            abort("tax_plugin_output_invalid")
        seen.add(position)
        if row.get("currency") != source["currency"]:
            abort("tax_plugin_output_invalid")
        if row.get("unrealized_gross_gain_decimal") != source["unrealized_gross_gain_decimal"]:
            abort("tax_plugin_output_invalid")
        status = row.get("projection_status")
        if status not in {"completed", "blocked"}:
            abort("tax_plugin_output_invalid")
        tax = row.get("projected_unrealized_tax_decimal")
        failure = row.get("failure_code")
        if status == "completed" and (tax is None or failure is not None):
            abort("tax_plugin_output_invalid")
        if status == "blocked" and (tax is not None or not isinstance(failure, str)):
            abort("tax_plugin_output_invalid")
        projected.append({
            "position_ref": position, "currency": source["currency"],
            "unrealized_gross_gain_decimal": source["unrealized_gross_gain_decimal"],
            "projected_unrealized_tax_decimal": tax,
            "projection_status": status, "failure_code": failure,
        })
    if seen != set(expected):
        abort("tax_plugin_output_invalid")
    projected.sort(key=lambda row: row["position_ref"])
    return projected


def unrealized_tax_projection_v1_fingerprint() -> str:
    """Bindet Feldlisten und Modus an einen Wert, damit Abweichungen auffallen."""
    return sha({"contract": "unrealized_tax_projection_v1", "rows": list(ROW_FIELDS),
                "lots": list(LOT_FIELDS), "result": list(RESULT_FIELDS)})
