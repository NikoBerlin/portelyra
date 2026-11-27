"""Rechenblatt je steuerlich relevantem Ereignis.

Festlegung (12.10.2026): Bei jedem steuerpflichtigen Ereignis soll eine
exakte Rechnung stehen, wie der Netto-Betrag zustande kaeme - mit der
Anschaffungsseite (Menge, Kaufpreis, Gebuehr, Datum, Konto, Kennung), der
angewandten Regel, dem Topf und der Haltefrist, so transparent und
informativ wie moeglich.

Das Blatt rechnet nichts selbst aus, was schon gerechnet ist:

- Vorgang, Lots, Haltedauer und Wert kommen aus dem einfachen Steuerreport
  (`simple_tax_report_v1`) - derselbe Lot-Nachweis wie dort.
- Steuerpflichtiger Betrag und Steuer kommen aus dem gewaehlten Regelmodul, mit
  dem Rechtsstand des Jahres und den gepflegten Steuereinstellungen. Das Blatt
  zerlegt die Steuer in ihre Schritte und prueft, dass die Schritte die Zahl
  des Moduls ergeben; sonst wird es nicht ausgegeben.

Je Ereignis gilt die konservative Sicht: keine Freigrenze, kein Freibetrag,
keine Verlustverrechnung; ein Verlust traegt die Steuer null. Die Jahresrechnung
ist etwas anderes und steht nicht hier.

Zinsen der Cash-Konten kommen
aus dem Cash-Speicher, nicht aus dem Buchungsbestand: je Zinsbuchung ein Blatt,
ohne Anschaffungsseite. Dazu fasst das Modell die Blaetter zusammen - je Institut
und Konto, je Topf und insgesamt. Auch das sind Summen der Ereignisse, keine
Jahresrechnung: Verrechnung, Freigrenzen und Verlustvortraege stehen dort nicht.

Liest nur. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
Keine Rechtsberatung.
"""

from __future__ import annotations

import csv
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, activity_reference_scope_v1, read_activity_taxable_documents_v1
from migrations.reference.realized_tax_projection_v1 import RealizedTaxBlocked
from migrations.reference.realized_tax_projection_v2 import RealizedTaxV2Blocked, validate_event_tax_candidate_v2
from migrations.reference.tax_model_plugin_v1 import (
    PLUGIN_ROOT, TaxPluginBlocked, TaxPluginContext, TaxPluginSelection, new_tax_plugin_bound_input_v1, sha, tax_plugin_manifest_v1,
)
from migrations.reference.tax_model_plugin_v2 import TaxPluginV2Blocked, run_tax_model_plugin_v2
from migrations.reference.tax_ui_workspace_v1 import TaxUiBlocked, tax_ui_authorized_product_catalog_v1, tax_ui_projection_inputs_v1
from workers.reference.semantic_realized_fifo_v1 import context_values as semantic_context_values, public_ref as semantic_public_ref
from workers.reference.simple_tax_report_v1 import _selection as report_selection
from workers.reference.simple_tax_report_v1 import (
    ASSET_TYPES as LEDGER_ASSET_TYPES, SimpleTaxReportV1Error, build_simple_tax_report_with_keys_v1, simple_tax_report_interest_rows_v1,
    simple_tax_report_value_source_label_v1,
)

CONTRACT = "tax_event_sheet_v1"
PLUGIN_ID = "tax_de_personal_income_tax_projection_v2"
ACTOR = "tax_event_sheet"
TIMEOUT_SECONDS = 240
FAILURE_CODES = ("tax_event_sheet_input_invalid", "tax_event_sheet_source_invalid")
# Zinsen liegen im Cash-Speicher und tragen keine Lots: eine eigene Auswahl neben den Assetklassen des Buchungsbestands.
CASH_TYPE = "cash"
ASSET_TYPES = (*LEDGER_ASSET_TYPES, CASH_TYPE)

_BUCKET_LABELS = {
    "private_disposal": "Private Veräußerungsgeschäfte",
    "other_income": "Sonstige Einkünfte",
    "capital_equity": "Kapitalerträge – Aktien",
    "capital_general": "Kapitalerträge – allgemein",
}
# Was vom Gewinn bzw. Ertrag nicht besteuert wird, nach Grund (#582), in dieser Reihenfolge unter den Toepfen. Zusammen mit den
# steuerpflichtigen Betraegen ergibt es den Gewinn bzw. Ertrag aller Blaetter; "ohne Steuerzahl" sind Blaetter, die noch keine Rechnung tragen.
_UNTAXED_LABELS = {
    "holding_period_expired": "steuerfrei – Jahresfrist abgelaufen",
    "partial_exemption": "steuerfrei – Teilfreistellung",
    "advance_lump_sum_credited": "angerechnete Vorabpauschalen (schon versteuert)",
    "rounding": "Rundung auf Cent",
    "document_difference": "Abweichung zur Abrechnung der Bank",
    "other": "nicht steuerpflichtiger Anteil",
    "not_calculated": "ohne Steuerzahl",
}
_TYPE_LABELS = {"sell": "Verkauf", "withdrawal": "Abgang", "reward": "Reward", "dividend": "Dividende", "interest": "Zins", "advance_lump_sum": "Vorabpauschale"}
# Die Vorabpauschale ist fuers Regelmodul ein Ertrag des Fonds wie eine Ausschuettung - mit derselben Teilfreistellung (§ 20 InvStG).
_MODULE_TYPES = {"advance_lump_sum": "dividend"}
_ORIGIN_LABELS = {"user_parameter": "eigene Angabe für {year}", "module_year_value": "Rechtsstand {year} des Regelmoduls"}
# Warum ein Blatt keine Steuerzahl traegt - in Worten, mit dem Ort, an dem es zu beheben ist.
_REASONS = {
    "tax_settings_absent": "Die Steuereinstellungen sind noch nicht eingerichtet (Daten → „4. Steuer“).",
    "tax_settings_unreadable": "Die Steuereinstellungen ließen sich nicht lesen.",
    "tax_module_unavailable": "Das Regelmodul ließ sich nicht ausführen.",
    "tax_year_rules_missing": "Das Regelmodul führt für {year} keinen Rechtsstand – es gibt keine Steuerzahl.",
    "tax_classification_required": "Für dieses Asset gilt in {year} keine steuerliche Einordnung (Daten → „4. Steuer“ → Vorgabe je Asset-Typ, „Gültig ab Jahr“).",
    "tax_classification_invalid": "Die steuerliche Einordnung des Assets lässt diesen Vorgang nicht zu.",
    "tax_holding_evidence_required": "Dem Vorgang fehlen die verbrauchten Lots.",
    "tax_fund_old_investment_tax_act": "Fonds vor 2018 oder Anteile von vor 2018 (altes Investmentsteuergesetz, fiktiver Verkauf zum 31.12.2017): bildet das Regelmodul nicht ab – keine Steuerzahl.",
    "tax_rate_required": "Für {year} ist kein persönlicher Steuersatz eingetragen (Daten → „4. Steuer“ → „Steuerangaben je Jahr“).",
    "church_tax_applicability_required": "Für {year} fehlt die Angabe, ob Kirchensteuer anfällt (Daten → „4. Steuer“ → „Steuerangaben je Jahr“).",
    "church_tax_rate_required": "Kirchensteuer ist für {year} als anwendbar eingetragen, der Satz fehlt.",
    "disposal_value_missing": "Der Abgang trägt keinen Wert – weder eingetragen noch ein Kurs für den Tag. Ohne Wert gibt es keinen Gewinn und keine Steuerzahl.",
    "basis_missing": "Mindestens einem verbrauchten Lot fehlen die Anschaffungskosten.",
    "interest_currency_unsupported": "Der Zinsertrag ist nicht in EUR gebucht – ohne Umrechnung gibt es keine Steuerzahl.",
}


class TaxEventSheetV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def tax_event_sheet_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise TaxEventSheetV1Error(code if code in FAILURE_CODES else "tax_event_sheet_source_invalid")


def _fraction(text: Any) -> Fraction | None:
    return None if text is None else Fraction(str(text))


def _text(value: Fraction | None) -> str | None:
    """Exakter Dezimaltext; die Zahlen des Blatts enden alle als Dezimalzahl."""
    if value is None:
        return None
    with localcontext() as exact:
        exact.prec = 200
        text = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _cents(value: Fraction | None) -> str | None:
    if value is None:
        return None
    with localcontext() as exact:
        exact.prec = 200
        return format((Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal("0.01"), rounding="ROUND_HALF_UP"), "f")


def _table(plugin_root: Path, name: str) -> list[dict[str, str]]:
    with (plugin_root / PLUGIN_ID / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _rules(plugin_root: Path) -> dict[str, Any]:
    """Regeln, Fundstellen und Jahreswerte des Moduls - an sein Manifest gebunden gelesen."""
    citations = {row["legal_reference_code"]: row["citation"] for row in _table(plugin_root, "legal-references.csv")}
    rules = {(row["event_type"], row["classification_code"]): row for row in _table(plugin_root, "rule-matrix.csv")
             if row["projection_mode"] == "realized_event" and not row["rule_code"].startswith("church_tax_")}
    year_references = {(int(row["tax_year"]), row["value_code"]): row["legal_reference_code"] for row in _table(plugin_root, "annual-legal-values.csv")}
    parameter_references = {row["parameter_code"]: row["legal_reference_code"] for row in _table(plugin_root, "parameter-definitions.csv")
                            if row["projection_mode"] == "realized_event"}
    return {"citations": citations, "rules": rules, "year_references": year_references, "parameter_references": parameter_references}


def _configuration(space: Path, scope: Any, portfolio_id: str, tax_year: int) -> dict[str, Any]:
    """Einordnungen und Parameter des Jahres aus dem Steuerspeicher - gelesen wie fuer den Abschluss."""
    store = space / "tax-ui" / "tax-policy.sqlite"
    if not store.is_file() or store.is_symlink():
        return {"status": "tax_settings_absent"}
    context = TaxPluginContext(scope.tenant_id, scope.user_id, scope.data_space_id, ACTOR)
    try:
        _, _, _, fingerprint = semantic_context_values({"tenant_id": scope.tenant_id, "user_id": scope.user_id, "data_space_id": scope.data_space_id})
        portfolio_ref = semantic_public_ref("pfr_", fingerprint, portfolio_id)
        catalog = tax_ui_authorized_product_catalog_v1(space, context)
        inputs = tax_ui_projection_inputs_v1(store, context, portfolio_ref, tax_year, catalog)
    except (TaxUiBlocked, TaxPluginBlocked, OSError, ValueError, KeyError, TypeError):
        return {"status": "tax_settings_unreadable"}
    parameters = []
    for row in inputs["parameters"]:
        if row.get("applicability_value") is not None:
            parameters.append({"tax_year": row["tax_year"], "parameter_code": row["parameter_code"], "applicability_value": row["applicability_value"]})
        else:
            parameters.append({"tax_year": row["tax_year"], "parameter_code": row["parameter_code"],
                               "rate_decimal": row["rate_decimal"], "amount_decimal": row["amount_decimal"]})
    classifications = [{
        "asset_ref": row["asset_ref"], "classification_code": row["classification_code"], "tax_bucket": row["tax_bucket"],
        "partial_exemption_rate_decimal": row["partial_exemption_rate_decimal"] or "0",
        "effective_from_year": row["effective_from_year"], "effective_to_year": row["effective_to_year"],
    } for row in inputs["classifications"]]
    return {"status": "ready", "context": context, "fingerprint": fingerprint, "portfolio_ref": portfolio_ref,
            "classifications": classifications, "parameters": parameters, "module": _module_for(space, context, portfolio_ref)}


def _module_for(space: Path, context: Any, portfolio_ref: str) -> dict[str, Any]:
    """Die Fassung des Moduls 2 fuer die Rechenblaetter dieses Portfolios (#486 Schritt 2): die Auswahl fuer "realized_event", die heute
    gilt. Ohne Auswahl, bei fehlender Fassung oder einem anderen Modul (das Vergleichsmodell 1) die mitgelieferte Fassung 2 - so rechneten
    die Blaetter bis rc.420 immer. `root` ist der Ordner ueber dem Modulordner (None = mitgeliefert)."""
    from datetime import datetime, timezone
    from migrations.reference.tax_module_catalog_v1 import TaxModuleCatalogBlocked, resolve_tax_module_v1, tax_module_manifest_v1
    try:
        resolved = resolve_tax_module_v1(space, context, portfolio_ref, "realized_event", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    except (TaxModuleCatalogBlocked, TaxPluginBlocked):
        resolved = {"status": "no_selection", "entry": None}
    entry = resolved.get("entry")
    if resolved["status"] == "selected" and entry["plugin_id"] == PLUGIN_ID and entry["origin"] == "data_space":
        try:
            return {"manifest": tax_module_manifest_v1(entry), "root": Path(entry["plugin_root"])}
        except TaxPluginBlocked:
            pass
    return {"manifest": None, "root": None}


def _interest_items(space: Path, scope: Any, tax_year: int) -> list[dict[str, Any]]:
    """Die Zinsertraege der Cash-Konten im Steuerjahr - dieselben Zeilen wie im einfachen Steuerreport.

    Ohne Cash-Speicher gibt es keine Zinsen und keinen Fehler. Die Zeilen sind geformt wie die Ertraege des einfachen
    Steuerreports, damit Blatt, Tabelle und Regelmodul sie gleich behandeln; Stueckzahl und Kennung kennt ein Zins nicht.
    """
    try:
        rows = simple_tax_report_interest_rows_v1(space, scope, tax_year)
    except SimpleTaxReportV1Error:
        _abort("tax_event_sheet_source_invalid")
    return [{
        **{name: row[name] for name in ("asset_label", "asset_type", "account_label", "institution_label", "local_date", "event_sequence",
                                        "income_type", "currency", "source_key")},
        # Ein Zins traegt nur den Tag; das Regelmodul liest die Uhrzeit nicht aus.
        "local_time": None, "time_zone": None, "transaction_id": None, "counterparty_address": None, "note": None,
        "quantity": None, "fee_quantity": None, "net_quantity": None, "value_per_unit": None,
        "gross_income": _text(row["gross_income"]), "gross_income_rounded": _cents(row["gross_income"]),
    } for row in rows]


def _run_module(configuration: Mapping[str, Any], rows: list[dict[str, Any]], tax_year: int) -> tuple[dict[str, dict], list[dict]]:
    """Laesst das Regelmodul ueber die Ereignisse laufen und gibt seine Zeilen und die Jahreswerte zurueck."""
    module = configuration.get("module") or {}
    manifest = module.get("manifest") or tax_plugin_manifest_v1(PLUGIN_ID)
    portfolio_ref = configuration["portfolio_ref"]
    selection_ref = "tsr_" + sha({"sheet": portfolio_ref, "year": tax_year})[:32]
    selection = TaxPluginSelection(selection_ref, 1, sha({"selection": selection_ref}), portfolio_ref, "realized_event", manifest.plugin_id,
                                   manifest.plugin_version, manifest.rules_fingerprint, manifest.manifest_fingerprint, manifest.effective_from, "active")
    bound = new_tax_plugin_bound_input_v1(
        projection_mode="realized_event", portfolio_ref=portfolio_ref,
        source_artifact_ref="rar_" + sha({"sheet_rows": [row["event_ref"] for row in rows], "year": tax_year})[:32],
        cutoff=f"{tax_year:04d}-12-31T23:59:59Z", rows=rows, classifications=configuration["classifications"], parameters=configuration["parameters"])
    result = run_tax_model_plugin_v2(bound_input=bound, context=configuration["context"], selection=selection, timeout_seconds=TIMEOUT_SECONDS,
                                     plugin_root=module.get("root"))
    validated = validate_event_tax_candidate_v2(result, bound, selection)
    return {row["event_ref"]: row for row in validated}, list(result.reconciliation.get("year_rules") or [])


def _advance_items(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Die Vorabpauschalen, die im Jahr zufliessen - geformt wie die Ertraege des Reports (#431)."""
    return [{
        **{name: row[name] for name in ("asset_label", "asset_type", "account_label", "institution_label", "local_date", "currency", "source_key", "calculation_year")},
        "event_sequence": index, "income_type": "advance_lump_sum", "local_time": None, "time_zone": None, "transaction_id": None,
        "counterparty_address": None, "note": None, "quantity": None, "fee_quantity": None, "net_quantity": None, "value_per_unit": None,
        "gross_income": row["advance_lump_sum_amount"], "gross_income_rounded": row["advance_lump_sum_amount_rounded"],
    } for index, row in enumerate(rows, 1)]


def _module_row(item: Mapping[str, Any], event_type: str, asset_ref: str, opaque: str) -> dict[str, Any]:
    key = item["source_key"]
    row = {
        "event_ref": opaque, "effective_at_utc": key["effective_at_utc"], "local_date": item["local_date"], "event_type": event_type,
        "account_ref": "afr_" + hashlib.sha256(str(key["account_ref"]).encode("utf-8")).hexdigest()[:32], "asset_ref": asset_ref,
        "asset_type": item["asset_type"], "currency": "EUR", "quantity_decimal": item["quantity"] or "0", "gross_proceeds_decimal": "0",
        "realized_gross_gain_decimal": "0", "gross_income_decimal": "0", "fee_decimal": "0", "fifo_allocations": [],
    }
    if event_type == "sell":
        # Der Erloes nach Gebuehr und die Lots mit ihren Anschaffungskosten - dieselben Zahlen wie im Lot-Nachweis.
        row["gross_proceeds_decimal"] = item["net_proceeds"]
        # Angesetzte Vorabpauschalen mindern den Gewinn eines Fondsverkaufs (§ 19 Abs. 1 Satz 3 InvStG).
        row["realized_gross_gain_decimal"] = item.get("gain_after_advance_lump_sum") or item["gain"]
        row["fifo_allocations"] = [{
            "quantity_decimal": lot["quantity"], "fifo_cost_decimal": lot["basis"],
            "acquisition_event_ref": "evr_" + hashlib.sha256(f"{opaque}|{index}".encode("utf-8")).hexdigest()[:32],
            "acquisition_effective_at_utc": lot["acquisition_local_date"] + "T00:00:00Z", "acquisition_local_date": lot["acquisition_local_date"],
        } for index, lot in enumerate(item["lots"])]
    else:
        row["gross_income_decimal"] = item["gross_income"]
    return row


def _public(item: Mapping[str, Any]) -> dict[str, Any]:
    """Der Vorgang ohne die Schluessel des Bestands und ohne interne Angaben (Beleg des steuerpflichtigen Betrags, #459)."""
    return {name: value for name, value in item.items() if name != "source_key" and not name.startswith("_")}


def _calculation(item: Mapping[str, Any], kind: str, module: Mapping[str, Any] | None, year_rule: Mapping[str, Any] | None,
                 rules: Mapping[str, Any], tax_year: int, blocked_reason: str | None) -> dict[str, Any]:
    """Die Steuerrechnung eines Ereignisses in Schritten - oder der Grund, warum es keine gibt."""
    def reason(code: str) -> dict[str, Any]:
        return {"status": "not_calculated", "reason_code": code, "reason_text": _REASONS.get(code, "Keine Steuerzahl.").format(year=tax_year)}

    if blocked_reason is not None:
        return reason(blocked_reason)
    if module is None:
        return reason("tax_module_unavailable")
    if module["projection_status"] != "completed":
        return reason(module["failure_code"] or "tax_module_unavailable")
    bucket = module["tax_bucket"]
    event_type = "sell" if kind == "disposal" else _MODULE_TYPES.get(item["income_type"], item["income_type"])
    rule = rules["rules"].get((event_type, module["classification_code"])) or {}
    taxable = _fraction(module["taxable_contribution_decimal"])
    tax_total = _fraction(module["projected_event_tax_decimal"])
    economic = _fraction(item["gain"] if kind == "disposal" else item["gross_income"])
    values = {entry["value_code"]: entry for entry in (year_rule or {}).get("values", [])}
    rate_code = "capital_income_tax_rate" if bucket in ("capital_equity", "capital_general") else "personal_income_tax_rate"

    def origin(code: str) -> str | None:
        label = _ORIGIN_LABELS.get((values.get(code) or {}).get("value_origin"))
        return None if label is None else label.format(year=tax_year)

    def reference(code: str) -> str | None:
        ref = rules["year_references"].get((tax_year, code)) or rules["parameter_references"].get(code)
        return rules["citations"].get(ref)

    steps: list[dict[str, Any]] = []
    if taxable is not None and taxable > 0:
        rate = _fraction((values.get(rate_code) or {}).get("value_decimal"))
        solidarity_rate = _fraction((values.get("solidarity_surcharge_rate") or {}).get("value_decimal"))
        church_applies = (year_rule or {}).get("church_tax_applicability") == "applicable"
        church_rate = _fraction((values.get("church_tax_rate") or {}).get("value_decimal")) if church_applies else None
        if rate is None or solidarity_rate is None or (church_applies and church_rate is None):
            _abort("tax_event_sheet_source_invalid")
        income_tax = taxable * rate / 100
        solidarity = income_tax * solidarity_rate / 100
        church = income_tax * church_rate / 100 if church_applies else Fraction(0)
        steps = [
            {"step_code": "income_tax", "label": "Einkommensteuer", "base_label": "steuerpflichtiger Betrag", "base": taxable, "rate_percent": rate,
             "rate_origin": origin(rate_code), "legal_citation": reference(rate_code), "amount": income_tax},
            {"step_code": "solidarity_surcharge", "label": "Solidaritätszuschlag", "base_label": "Einkommensteuer", "base": income_tax,
             "rate_percent": solidarity_rate, "rate_origin": origin("solidarity_surcharge_rate"), "legal_citation": reference("solidarity_surcharge_rate"),
             "amount": solidarity},
            {"step_code": "church_tax", "label": "Kirchensteuer", "base_label": "Einkommensteuer", "base": income_tax if church_applies else None,
             "rate_percent": church_rate, "rate_origin": origin("church_tax_rate") if church_applies else f"für {tax_year} als nicht anwendbar eingetragen",
             "legal_citation": None, "amount": church},
        ]
        # Die Schritte muessen die Zahl des Moduls ergeben. Das Modul schneidet nur einen periodischen Anteil ab;
        # die Steuer darauf rechnet es exakt - also gilt Gleichheit, keine Naeherung.
        if income_tax + solidarity + church != tax_total:
            _abort("tax_event_sheet_source_invalid")
    elif tax_total != 0:
        _abort("tax_event_sheet_source_invalid")
    if kind == "disposal":
        inside = sum((_fraction(lot["gain"]) for lot in item["lots"] if lot["within_holding_period"] and lot["gain"] is not None), Fraction(0))
        if bucket == "private_disposal":
            # Derselbe Betrag wie die Summe der Lot-Gewinne in der Frist; ein periodischer Anteil ist auf zwoelf Stellen abgeschnitten.
            if abs(taxable - inside) > Fraction(1, 10 ** 9):
                _abort("tax_event_sheet_source_invalid")
            explanation = ("Summe der Gewinne der Lots, die innerhalb der Jahresfrist veräußert wurden. Lots außerhalb der Frist bleiben außer Ansatz."
                           + (" Ein negativer Betrag trägt je Ereignis die Steuer null." if taxable < 0 else ""))
        else:
            advance = _fraction(item.get("advance_lump_sum_deduction"))
            explanation = "Gewinn des Vorgangs (Erlös nach Gebühr abzüglich Anschaffungskosten)" + (
                "" if not advance else f", abzüglich angesetzter Vorabpauschalen von {_cents(advance).replace('.', ',')} € (§ 19 Abs. 1 Satz 3 InvStG)") + (
                "" if module["partial_exemption_rate_decimal"] in (None, "0") else f", nach Teilfreistellung von {module['partial_exemption_rate_decimal']} %") + "."
    elif item["income_type"] == "interest":
        explanation = "Zinsertrag brutto, wie er am Cash-Konto gebucht ist."
    elif item["income_type"] == "advance_lump_sum":
        explanation = (f"Vorabpauschale für {item['calculation_year']} laut Bank, zugeflossen am ersten Werktag des Jahres (§ 18 Abs. 3 InvStG)" + (
            "" if module["partial_exemption_rate_decimal"] in (None, "0") else f", nach Teilfreistellung von {module['partial_exemption_rate_decimal']} %") + ".")
    else:
        explanation = "Bruttoertrag bei Zufluss (Wert der zugegangenen Menge nach Gebühr)."
    # Kapitalertraege rundet das Modul je Ereignis kaufmaennisch auf Cent, wie die Institute je Abrechnung (#459).
    document = item.get("_document") if bucket in ("capital_equity", "capital_general") else None
    used = document is not None and taxable == _fraction(document["taxable_eur_decimal"])
    if used:
        explanation += f" Übernommen aus dem Beleg: {document['document_label']} (Kapitalertrag vor Freistellungsauftrag und Verlustverrechnung)."
    elif document is not None:
        explanation += (f" Der Betrag laut Beleg ({document['document_label']}: {document['taxable_eur_decimal'].replace('.', ',')} €) weicht um mehr als 1 € "
                        "von der eigenen Rechnung ab – es gilt die eigene Rechnung. Die Erträgnisaufstellung bitte erneut prüfen (etwa nach einer Korrektur der Buchung).")
    if not used and bucket in ("capital_equity", "capital_general") and (kind == "disposal" or module["partial_exemption_rate_decimal"] not in (None, "0")):
        explanation += " Auf Cent gerundet wie in der Abrechnung der Bank (berechnet, nicht aus dem Beleg übernommen)."
    # Was vom Gewinn bzw. Ertrag nicht besteuert wird, nach Grund (#582); mit dem steuerpflichtigen Betrag zusammen genau der Gewinn bzw.
    # Ertrag des Blatts. Private Veraeusserung: Lots nach Ablauf der Jahresfrist. Kapitalertraege: angerechnete Vorabpauschalen, dann die
    # Teilfreistellung auf den Rest, was bleibt ist die Rundung auf Cent (oder die Abweichung zum uebernommenen Beleg).
    untaxed: list[dict[str, Any]] = []
    if economic is not None and taxable is not None:
        rest = economic - taxable
        if bucket == "private_disposal" and kind == "disposal":
            untaxed.append({"untaxed_code": "holding_period_expired", "amount": rest})
            rest = Fraction(0)
        elif bucket in ("capital_equity", "capital_general"):
            credited = _fraction(item.get("advance_lump_sum_deduction")) if kind == "disposal" else None
            if credited:
                untaxed.append({"untaxed_code": "advance_lump_sum_credited", "amount": credited})
                rest -= credited
            exemption_rate = _fraction(module["partial_exemption_rate_decimal"])
            if exemption_rate:
                exempt = (economic - (credited or 0)) * exemption_rate / 100
                untaxed.append({"untaxed_code": "partial_exemption", "amount": exempt})
                rest -= exempt
            untaxed.append({"untaxed_code": "document_difference" if used else "rounding", "amount": rest})
            rest = Fraction(0)
        untaxed.append({"untaxed_code": "other", "amount": rest})
        untaxed = [part for part in untaxed if part["amount"] != 0]
    return {
        "status": "calculated", "reason_code": None, "reason_text": None, "tax_year": tax_year,
        "rule_code": rule.get("rule_code"), "legal_citation": rules["citations"].get(rule.get("legal_reference_code")),
        "classification_code": module["classification_code"], "tax_bucket": bucket, "tax_bucket_label": _BUCKET_LABELS.get(bucket, bucket),
        "taxable_amount": taxable, "taxable_explanation": explanation, "steps": steps, "tax_total": tax_total,
        # Woher der steuerpflichtige Betrag stammt (#459): aus dem Beleg der Bank oder aus der eigenen Rechnung.
        "taxable_source": "document" if used else ("document_outdated" if document is not None else "computed"),
        "taxable_document_label": document["document_label"] if document is not None else None,
        "economic_amount": economic, "net_after_tax": None if economic is None else economic - tax_total,
        "untaxed_parts": untaxed,
        "plugin_id": module["plugin_id"], "plugin_version": module["plugin_version"],
    }


_AMOUNT_KEYS = frozenset({"taxable_amount", "tax_total", "economic_amount", "net_after_tax", "base", "amount", "event_tax_sum",
                          "positive_taxable_amount", "negative_taxable_amount", "positive_amount", "negative_amount"})


def _plain(value: Any, key: str | None = None) -> Any:
    if isinstance(value, Fraction):
        return _text(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for name, item in value.items():
            result[name] = _plain(item, name)
            if name in _AMOUNT_KEYS and (isinstance(item, Fraction) or item is None):
                result[name + "_rounded"] = _cents(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_plain(item, key) for item in value]
    return value


def build_tax_event_sheets_v1(
    data_space_path: str | Path, context_value: Any, tax_year: int, asset_types: Sequence[str] = ("crypto",),
    module_runner: Callable[[Mapping[str, Any], list[dict[str, Any]], int], tuple[dict[str, dict], list[dict]]] | None = None,
    keep_module_rows: bool = False,
    selection: Any = None,
    keep_source_keys: bool = False,
    use_documents: bool = True,
) -> dict[str, Any]:
    """Die Rechenblaetter eines Steuerjahres. Liest nur.

    `use_documents` (#459): Betraege laut Beleg (etwa aus der Ertraegnisaufstellung) gehen ans Regelmodul. Ohne sie rechnet das
    Blatt nur selbst - so vergleicht der Leser der Aufstellung die Bank mit der eigenen Rechnung.

    `keep_module_rows` haengt an jedes Blatt die Zeile des Regelmoduls und das Portfolio an - fuer die Jahresrechnung,
    die aus genau diesen Zeilen rechnet. Die Tabelle der Blaetter zeigt sie nicht.

    `keep_source_keys` haengt die Schluessel des Bestands an (Buchung, Asset, Konto) - nur fuer Rechenkerne wie die
    Netto-Sicht der Tageshistorie, die die Steuer je Ereignis ihrer Buchung zuordnen. Sie gehen nicht an die Oberflaeche.
    """
    if isinstance(tax_year, bool) or not isinstance(tax_year, int) or not 2000 <= tax_year <= 2100:
        _abort("tax_event_sheet_input_invalid")
    if isinstance(asset_types, (str, bytes)) or not isinstance(asset_types, Sequence) or not asset_types or any(
            kind not in ASSET_TYPES for kind in asset_types) or len(set(asset_types)) != len(asset_types):
        _abort("tax_event_sheet_input_invalid")
    ledger_types = [kind for kind in asset_types if kind != CASH_TYPE]
    space = Path(data_space_path)
    try:
        scope = activity_reference_scope_v1(context_value)
        # Ohne Assetklasse des Buchungsbestands braucht es keinen Lot-Nachweis - und keinen FIFO-Stand.
        # Eine Auswahl einzelner Konten oder Vermoegenswerte (#433) gilt wie im Report - fuer Vorgaenge und Zinsen.
        report = build_simple_tax_report_with_keys_v1(data_space_path, context_value, tax_year, ledger_types, selection) if ledger_types else {
            "status": "ready", "fifo_state_status": None, "fifo_state_freshness": None, "disposals": [], "gratuitous_transfers": [], "income": []}
    except AssetActivityReferenceV1Error:
        _abort("tax_event_sheet_input_invalid")
    except SimpleTaxReportV1Error as error:
        _abort("tax_event_sheet_input_invalid" if error.code == "simple_tax_report_input_invalid" else "tax_event_sheet_source_invalid")
    if not ledger_types and (not space.is_dir() or space.is_symlink()):
        _abort("tax_event_sheet_source_invalid")
    base = {
        "contract_version": CONTRACT, "tax_year": tax_year, "asset_types": sorted(asset_types),
        "fifo_state_status": report["fifo_state_status"], "fifo_state_freshness": report["fifo_state_freshness"],
        "method": {"event_view": "conservative_no_threshold_no_allowance_no_loss_offset", "negative_event_tax": "zero",
                   "lot_evidence": "simple_tax_report_v1", "tax_source": PLUGIN_ID, "event_tax_is_annual_tax": False, "legal_advice": False},
        "provider_access": False, "network_access": False, "canonical_write": False,
    }
    if report["status"] != "ready":
        return _plain({**base, "status": report["status"], "settings_status": None, "sheets": [], "summary": _summary([]), "breakdown": _breakdown([])})
    try:
        rules = _rules(PLUGIN_ROOT)
    except (OSError, KeyError, ValueError):
        _abort("tax_event_sheet_source_invalid")
    interest = _interest_items(space, scope, tax_year) if CASH_TYPE in asset_types else []
    if selection is not None and interest:
        try:
            chosen_accounts, chosen_assets, _ = report_selection(space, scope, selection)
        except SimpleTaxReportV1Error:
            _abort("tax_event_sheet_input_invalid")
        if chosen_accounts is not None:
            interest = [item for item in interest if item["source_key"]["account_ref"] in chosen_accounts]
        elif chosen_assets is not None:
            interest = []
    entries: list[dict[str, Any]] = []
    try:
        documents = read_activity_taxable_documents_v1(space, scope)["values"] if use_documents else {}
    except AssetActivityReferenceV1Error:
        _abort("tax_event_sheet_source_invalid")
    advance = _advance_items(report.get("advance_lump_sums") or [])
    for kind, items in (("disposal", report["disposals"]), ("gratuitous_transfer", report["gratuitous_transfers"]), ("income", [*report["income"], *interest, *advance])):
        for item in items:
            entries.append({"kind": kind, "item": item, "portfolio_id": item["source_key"]["portfolio_id"]})
    entries.sort(key=lambda entry: (entry["item"]["local_date"], entry["item"]["local_time"] or "", entry["item"]["asset_label"], entry["item"]["event_sequence"]))
    settings_status = "ready"
    module_rows: dict[int, dict] = {}
    year_rule_of: dict[int, Mapping[str, Any] | None] = {}
    blocked: dict[int, str] = {}
    rules_of: dict[str, dict[str, Any]] = {}   # Regeltabellen der Fassung je Portfolio (#486 Schritt 2)
    for portfolio_id in sorted({entry["portfolio_id"] for entry in entries}):
        configuration = _configuration(space, scope, portfolio_id, tax_year)
        chosen = [index for index, entry in enumerate(entries) if entry["portfolio_id"] == portfolio_id and entry["kind"] != "gratuitous_transfer"]
        if configuration["status"] == "ready" and (configuration.get("module") or {}).get("root") is not None:
            try:
                rules_of[portfolio_id] = _rules(configuration["module"]["root"])
            except (OSError, KeyError, ValueError):
                _abort("tax_event_sheet_source_invalid")
        if configuration["status"] != "ready":
            settings_status = configuration["status"]
            for index in chosen:
                blocked[index] = configuration["status"]
            continue
        rows = []
        for index in chosen:
            entry = entries[index]; item = entry["item"]
            if entry["kind"] == "disposal" and item["gain"] is None:
                blocked[index] = "disposal_value_missing" if item["net_proceeds"] is None else "basis_missing"
                continue
            if item.get("currency", "EUR") != "EUR":
                blocked[index] = "interest_currency_unsupported"
                continue
            opaque = "evr_" + hashlib.sha256(f"{item['source_key']['event_ref']}|{index}".encode("utf-8")).hexdigest()[:32]
            asset_ref = semantic_public_ref("asf_", configuration["fingerprint"], item["source_key"]["asset_id"])
            module_type = "sell" if entry["kind"] == "disposal" else _MODULE_TYPES.get(item["income_type"], item["income_type"])
            row = _module_row(item, module_type, asset_ref, opaque)
            document = documents.get(item["source_key"]["event_ref"]) if module_type in ("sell", "dividend") and item.get("income_type") != "advance_lump_sum" else None
            if document is not None:
                row["document_taxable_decimal"] = document["taxable_eur_decimal"]
                item = {**item, "_document": document}; entries[index] = {**entry, "item": item}
            rows.append((index, row))
        if not rows:
            continue
        try:
            answered, rule_values = (module_runner or _run_module)(configuration, [row for _, row in rows], tax_year)
        except (TaxPluginV2Blocked, TaxPluginBlocked, RealizedTaxV2Blocked, RealizedTaxBlocked):
            for index, _ in rows:
                blocked[index] = "tax_module_unavailable"
            continue
        year_rule = next((entry for entry in rule_values if entry.get("tax_year") == tax_year), None)
        for index, row in rows:
            if row["event_ref"] not in answered:
                _abort("tax_event_sheet_source_invalid")
            module_rows[index] = answered[row["event_ref"]]
            year_rule_of[index] = year_rule
    sheets = []
    for index, entry in enumerate(entries):
        item = entry["item"]; kind = entry["kind"]
        if kind == "gratuitous_transfer":
            calculation = {"status": "not_taxable", "reason_code": "gratuitous_transfer",
                           "reason_text": "Unentgeltliche Übertragung – keine Veräußerung, nicht steuerpflichtig. Es wird kein Gewinn gebildet."}
        else:
            calculation = _calculation(item, kind, module_rows.get(index), year_rule_of.get(index), rules_of.get(entry["portfolio_id"], rules), tax_year,
                                       blocked.get(index))
        event_type = item["disposal_type"] if kind != "income" else item["income_type"]
        treatment = item.get("treatment_label") or (
            None if kind != "income" else "Zinsertrag – Kapitalertrag" if event_type == "interest"
            else "Vorabpauschale – Kapitalertrag aus Investmentfonds" if event_type == "advance_lump_sum"
            else "Ertrag – sonstige Einkünfte oder Kapitalertrag je nach Einordnung")
        extra = {"module_row": module_rows.get(index), "portfolio_id": entry["portfolio_id"]} if keep_module_rows else {}
        if keep_source_keys:
            extra["source_key"] = dict(item["source_key"])
        sheets.append({
            **extra,
            "sheet_no": index + 1, "event_kind": kind, "event_type": event_type, "event_type_label": _TYPE_LABELS.get(event_type, event_type),
            "treatment_label": treatment,
            "value_source_label": simple_tax_report_value_source_label_v1(item) if kind != "income" else None,
            # Gewinn bzw. Ertrag des Vorgangs steht auch dann da, wenn dem Blatt die Steuerzahl fehlt; die Schenkung bildet keinen.
            "economic_amount": None if kind == "gratuitous_transfer" else _fraction(item["gain"] if kind == "disposal" else item["gross_income"]),
            "event": _public(item), "calculation": calculation,
        })
    return _plain({**base, "status": "ready", "settings_status": settings_status, "sheets": sheets, "summary": _summary(sheets),
                   "breakdown": _breakdown(sheets)})


def _breakdown(sheets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Die Blaetter zusammengefasst: je Institut und Konto, je Institut, je Topf und insgesamt.

    Summen der Ereignisse, nichts darueber hinaus: keine Verrechnung von Verlusten, keine Freigrenze, kein Freibetrag.
    "Institut" ist die Institutsangabe des Kontos aus den Stammdaten; Konten mit derselben Angabe bilden ein Institut.
    Fehlt einem Blatt der Gruppe die Steuerzahl, traegt die Gruppe kein Netto - eine Teilsumme saehe aus wie das Ganze.
    """
    def empty() -> dict[str, Any]:
        return {"sheet_count": 0, "calculated_count": 0, "not_taxable_count": 0, "not_calculated_count": 0,
                "economic_amount": Fraction(0), "taxable_amount": Fraction(0), "tax_total": Fraction(0), "net_after_tax": None}

    def add(row: dict[str, Any], sheet: Mapping[str, Any]) -> None:
        calculation = sheet["calculation"]
        row["sheet_count"] += 1
        row[{"calculated": "calculated_count", "not_taxable": "not_taxable_count"}.get(calculation["status"], "not_calculated_count")] += 1
        row["economic_amount"] += sheet["economic_amount"] or Fraction(0)
        if calculation["status"] == "calculated":
            row["taxable_amount"] += calculation["taxable_amount"]
            row["tax_total"] += calculation["tax_total"]

    def closed(row: dict[str, Any]) -> dict[str, Any]:
        row["net_after_tax"] = row["economic_amount"] - row["tax_total"] if row["not_calculated_count"] == 0 else None
        return row

    accounts: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    institutions: dict[tuple[str, str], dict[str, Any]] = {}
    buckets: dict[str, dict[str, Any]] = {}
    untaxed: dict[str, dict[str, Any]] = {}

    def add_untaxed(code: str, amount: Fraction) -> None:
        row = untaxed.setdefault(code, {"untaxed_code": code, "untaxed_label": _UNTAXED_LABELS[code], "sheet_count": 0,
                                        "positive_amount": Fraction(0), "negative_amount": Fraction(0), "amount": Fraction(0)})
        row["sheet_count"] += 1
        row["positive_amount" if amount > 0 else "negative_amount"] += amount
        row["amount"] += amount

    total = empty()
    for sheet in sheets:
        event = sheet["event"]; calculation = sheet["calculation"]
        # Eine leere Angabe ist keine Angabe. Sortiert wird nach der Angabe; Konten ohne Angabe stehen am Ende.
        institution = event.get("institution_label") or None
        key = ("1" if institution is None else "0", institution or "")
        add(accounts.setdefault((*key, event["account_label"], ""), {"institution_label": institution, "account_label": event["account_label"], **empty()}), sheet)
        add(institutions.setdefault(key, {"institution_label": institution, "account_labels": set(), **empty()}), sheet)
        institutions[key]["account_labels"].add(event["account_label"])
        add(total, sheet)
        if calculation["status"] == "calculated":
            bucket = buckets.setdefault(calculation["tax_bucket"], {
                "tax_bucket": calculation["tax_bucket"], "tax_bucket_label": calculation["tax_bucket_label"], "sheet_count": 0,
                "positive_taxable_amount": Fraction(0), "negative_taxable_amount": Fraction(0), "taxable_amount": Fraction(0), "tax_total": Fraction(0)})
            taxable = calculation["taxable_amount"]
            bucket["sheet_count"] += 1
            bucket["positive_taxable_amount" if taxable > 0 else "negative_taxable_amount"] += taxable
            bucket["taxable_amount"] += taxable
            bucket["tax_total"] += calculation["tax_total"]
            for part in calculation.get("untaxed_parts") or []:
                add_untaxed(part["untaxed_code"], part["amount"])
        elif calculation["status"] == "not_calculated" and sheet["economic_amount"] is not None:
            add_untaxed("not_calculated", sheet["economic_amount"])
    by_institution = []
    for key in sorted(institutions):
        row = closed(institutions[key])
        account_count = len(row.pop("account_labels"))
        by_institution.append({**row, "account_count": account_count})
    return {
        "institution_source": "account_institution_label", "offsetting_applied": False,
        "by_account": [closed(accounts[key]) for key in sorted(accounts)],
        "by_institution": by_institution,
        "by_bucket": [buckets[key] for key in sorted(buckets)],
        # Was nicht besteuert wird, nach Grund (#582): steuerpflichtige Toepfe plus diese Zeilen ergeben den Gewinn bzw. Ertrag der Gesamtzeile.
        "by_untaxed": [untaxed[code] for code in _UNTAXED_LABELS if code in untaxed],
        "total": closed(total),
    }


def _summary(sheets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    calculated = [sheet for sheet in sheets if sheet["calculation"]["status"] == "calculated"]
    reasons: dict[str, int] = {}
    for sheet in sheets:
        if sheet["calculation"]["status"] == "not_calculated":
            reasons[sheet["calculation"]["reason_code"]] = reasons.get(sheet["calculation"]["reason_code"], 0) + 1
    return {
        "sheet_count": len(sheets), "calculated_count": len(calculated),
        "not_taxable_count": sum(1 for sheet in sheets if sheet["calculation"]["status"] == "not_taxable"),
        "not_calculated_count": sum(reasons.values()), "not_calculated_reasons": dict(sorted(reasons.items())),
        "with_tax_count": sum(1 for sheet in calculated if sheet["calculation"]["tax_total"] != 0),
        # Die Summe der Ereignissteuern ist keine Jahressteuer: ohne Freigrenzen, ohne Verrechnung.
        "event_tax_sum": sum((sheet["calculation"]["tax_total"] for sheet in calculated), Fraction(0)),
        "event_tax_sum_is_annual_tax": False,
    }


def render_tax_event_sheet_csv_v1(model: Mapping[str, Any], generated_at_utc: str) -> str:
    """Die Uebersicht der Blaetter als Tabelle: Semikolon, Dezimalkomma, ISO-Datum - eine Zeile je Ereignis."""
    import io
    if not isinstance(model, Mapping) or model.get("contract_version") != CONTRACT:
        _abort("tax_event_sheet_input_invalid")

    def comma(text: Any) -> str:
        return "" if text is None else str(text).replace(".", ",")

    def safe(text: Any) -> str:
        value = "" if text is None else str(text).replace("\r", " ").replace("\n", " ")
        return "'" + value if value[:1] in ("=", "+", "-", "@") else value

    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow([f"Rechenblätter {model['tax_year']} – Steuer je Ereignis (konservativ: ohne Freigrenze, ohne Freibetrag, ohne Verlustverrechnung)"])
    writer.writerow(["Erstellt (UTC)", generated_at_utc])
    writer.writerow(["Hinweis", "Modellrechnung nach dem gewählten Regelmodul, keine Rechtsberatung. Die Summe der Ereignissteuern ist keine Jahressteuer."])
    writer.writerow([])
    writer.writerow(["Blatt", "Datum", "Uhrzeit", "Art", "Einordnung", "Vermögenswert", "Konto", "Institut", "Stückzahl", "Erlös bzw. Ertrag", "Anschaffungskosten",
                     "Gewinn bzw. Ertrag", "Topf", "Regel (Fundstelle)", "steuerpflichtiger Betrag", "Einkommensteuer", "Solidaritätszuschlag",
                     "Kirchensteuer", "Steuer gesamt", "Netto nach Steuer", "Stand", "Grund", "Transaktions-ID"])
    for sheet in model["sheets"]:
        event = sheet["event"]; calculation = sheet["calculation"]
        steps = {step["step_code"]: step for step in calculation.get("steps") or []}
        writer.writerow([
            sheet["sheet_no"], event["local_date"], event["local_time"] or "", sheet["event_type_label"], safe(sheet["treatment_label"]),
            safe(event["asset_label"]), safe(event["account_label"]), safe(event.get("institution_label")), comma(event["quantity"]),
            comma(event.get("net_proceeds_rounded") if sheet["event_kind"] != "income" else event.get("gross_income_rounded")),
            comma(event.get("basis_rounded")), comma(sheet.get("economic_amount_rounded")), calculation.get("tax_bucket_label") or "",
            safe(calculation.get("legal_citation")), comma(calculation.get("taxable_amount_rounded")),
            comma((steps.get("income_tax") or {}).get("amount_rounded")), comma((steps.get("solidarity_surcharge") or {}).get("amount_rounded")),
            comma((steps.get("church_tax") or {}).get("amount_rounded")), comma(calculation.get("tax_total_rounded")),
            comma(calculation.get("net_after_tax_rounded")),
            {"calculated": "gerechnet", "not_taxable": "nicht steuerpflichtig", "not_calculated": "keine Steuerzahl"}[calculation["status"]],
            safe(calculation.get("reason_text")), safe(event.get("transaction_id"))])
    breakdown = model.get("breakdown") or {}
    if model["sheets"] and breakdown:
        def sums(row: Mapping[str, Any]) -> list[Any]:
            return [row["sheet_count"], row["not_calculated_count"], comma(row["economic_amount_rounded"]), comma(row["taxable_amount_rounded"]),
                    comma(row["tax_total_rounded"]), comma(row["net_after_tax_rounded"])]

        head = ["Ereignisse", "davon ohne Steuerzahl", "Gewinn bzw. Ertrag", "steuerpflichtiger Betrag", "Steuer je Ereignis", "Netto nach Steuer"]
        writer.writerow([])
        writer.writerow(["Aufschlüsselung nach Institut und Konto (Summen der Ereignisse, ohne Verrechnung; Institut = Institutsangabe des Kontos)"])
        writer.writerow(["Institut", "Konto", *head])
        for row in breakdown["by_account"]:
            writer.writerow([safe(row["institution_label"]) or "ohne Institutsangabe", safe(row["account_label"]), *sums(row)])
        writer.writerow([])
        writer.writerow(["Summe je Institut"])
        writer.writerow(["Institut", "Konten", *head])
        for row in breakdown["by_institution"]:
            writer.writerow([safe(row["institution_label"]) or "ohne Institutsangabe", row["account_count"], *sums(row)])
        writer.writerow([])
        writer.writerow(["Töpfe (Summen der gerechneten Ereignisse; Verluste sind nicht verrechnet), darunter was nicht besteuert wird – "
                         "zusammen der Gewinn bzw. Ertrag"])
        writer.writerow(["Topf", "Ereignisse", "positive Beträge", "negative Beträge", "Saldo", "Steuer je Ereignis"])
        for row in breakdown["by_bucket"]:
            writer.writerow([row["tax_bucket_label"], row["sheet_count"], comma(row["positive_taxable_amount_rounded"]),
                             comma(row["negative_taxable_amount_rounded"]), comma(row["taxable_amount_rounded"]), comma(row["tax_total_rounded"])])
        for row in breakdown.get("by_untaxed") or []:
            writer.writerow([row["untaxed_label"], row["sheet_count"], comma(row["positive_amount_rounded"]), comma(row["negative_amount_rounded"]),
                             comma(row["amount_rounded"]), "" if row["untaxed_code"] == "not_calculated" else "0,00"])
        writer.writerow(["Summe: Gewinn bzw. Ertrag", "", "", "", comma(breakdown["total"]["economic_amount_rounded"]),
                         comma(breakdown["total"]["tax_total_rounded"])])
        writer.writerow([])
        writer.writerow(["Gesamt", "", *sums(breakdown["total"])])
    return "\ufeff" + out.getvalue()


__all__ = [
    "ASSET_TYPES", "FAILURE_CODES", "TaxEventSheetV1Error", "build_tax_event_sheets_v1", "render_tax_event_sheet_csv_v1", "tax_event_sheet_v1_error_codes",
]
