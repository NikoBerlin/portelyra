"""Jahresrechnung: die voraussichtliche Steuer eines Jahres mit Verrechnung, Freigrenzen, Freistellung und Verlustvortraegen.

Neben dem Rechenblatt je Ereignis zeigt die Jahresrechnung (#429) das Ergebnis
brutto, voraussichtliche Gesamtsteuer, Netto, dazu Verbrauch und Verrechnung der Verlusttoepfe und die Vortraege. Ziel:
Die Abrechnung eines Instituts stimmt damit ueberein. Der Freibetrag gilt je Institut, ohne Eintrag 0 Euro;
die Freigrenzen gelten uebergreifend.

Die Jahresrechnung rechnet nichts selbst, was das Regelmodul rechnet:

- Die Ereignisse und ihr steuerpflichtiger Betrag sind die der Rechenblaetter (`tax_event_sheet_v1`) - derselbe
  Lot-Nachweis, dieselben Zinsen der Cash-Konten, dieselbe Zeile des Regelmoduls je Ereignis.
- Das Jahr rechnet das Regelmodul im Jahresmodus: Kapitalertraege je Institut (Verrechnung, Verlusttopf,
  Freistellungsauftrag, Quellensteuer), private Veraeusserungsgeschaefte und sonstige Einkuenfte ueber alle Institute
  (Saldo, Freigrenze, Vortrag).
- Die Verlusttoepfe zum Jahresbeginn sind eingetragen (Data, Steuerangaben je Institut bzw. je Jahr) oder der Stand zum
  Ende des Vorjahres. Deshalb rechnet sie jedes Jahr ab 2020 bis zum gewaehlten nacheinander.

Liest nur. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write. Modellrechnung, keine Rechtsberatung.
"""

from __future__ import annotations

from fractions import Fraction
import io
import re
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, activity_reference_scope_v1
from migrations.reference.institution_tax_settings_v1 import (
    InstitutionTaxSettingsV1Error, institution_key_v1, read_institution_tax_settings_v1,
)
from migrations.reference.realized_tax_projection_v1 import RealizedTaxBlocked
from migrations.reference.realized_tax_projection_v2 import RealizedTaxV2Blocked, validate_annual_tax_candidate_v2
from migrations.reference.tax_model_plugin_v1 import (
    TaxPluginBlocked, TaxPluginSelection, new_tax_plugin_bound_input_v1, sha, tax_plugin_manifest_v1,
)
from migrations.reference.tax_model_plugin_v2 import TaxPluginV2Blocked, run_tax_model_plugin_v2
from workers.reference.tax_annual_chain_v1 import (
    CAPITAL_BUCKETS, FIRST_YEAR, OPENING_CODES, PARTIAL_FIRST_YEAR, PERSONAL_BUCKETS, annual_parameters_v1, closing_totals_v1, empty_chain_v1, entered_by_year_v1,
    keyed_v1, next_chain_v1,
)
from workers.reference.tax_event_sheet_v1 import (
    ASSET_TYPES, PLUGIN_ID, TaxEventSheetV1Error, _cents, _configuration, _fraction, _text, build_tax_event_sheets_v1,
)

CONTRACT = "tax_annual_statement_v1"
TIMEOUT_SECONDS = 120
FAILURE_CODES = ("tax_annual_statement_input_invalid", "tax_annual_statement_source_invalid")
BUCKET_LABELS = {
    "capital_equity": "Kapitalerträge – Aktien", "capital_general": "Kapitalerträge – allgemein",
    "private_disposal": "Private Veräußerungsgeschäfte (§ 23 EStG)", "other_income": "Sonstige Einkünfte (§ 22 Nr. 3 EStG)",
}
NO_INSTITUTION = "ohne Institutsangabe"
METHOD_LINES = (
    "Kapitalerträge je Institut: Zuerst gleicht sich das Jahr aus – Aktienverluste nur mit Aktiengewinnen, alle anderen Verluste mit allen "
    "Kapitalerträgen –, dann mindert der Verlusttopf des Instituts, zuletzt der Freistellungsauftrag dort. Anrechenbare Quellensteuer mindert "
    "die Steuer des Instituts, höchstens bis null (§ 20 Abs. 6 und 9, § 43a Abs. 3, § 44a Abs. 2, § 32d Abs. 5 EStG).",
    "Private Veräußerungsgeschäfte und sonstige Einkünfte über alle Institute: Gewinne und Verluste des Jahres werden saldiert. Liegt der Saldo "
    "unter der Freigrenze, bleibt er steuerfrei und der Verlustvortrag unberührt; ab der Freigrenze mindert ihn der Vortrag, und der Rest ist "
    "steuerpflichtig (§ 23 Abs. 3, § 22 Nr. 3 EStG).",
    "Verlusttöpfe zum Jahresbeginn: eingetragen in Daten → „4. Steuer“, sonst der Stand zum Ende des Vorjahres. Die Kette beginnt 2020.",
    "Steuer: Satz des Jahres auf den steuerpflichtigen Betrag, darauf Solidaritätszuschlag und, wo eingetragen, Kirchensteuer als Zuschlag.",
    "Nicht abgebildet: Verlustrücktrag in das Vorjahr, Günstigerprüfung, Zusammenveranlagung, die Ermäßigung der Kirchensteuer bei der "
    "Abgeltungsteuer und die Freigrenze des Solidaritätszuschlags. Modellrechnung, keine Rechtsberatung.",
)


class TaxAnnualStatementV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def tax_annual_statement_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise TaxAnnualStatementV1Error(code if code in FAILURE_CODES else "tax_annual_statement_source_invalid")


def _run_annual(configuration: Mapping[str, Any], rows: list[dict[str, Any]], parameters: list[dict[str, Any]],
                tax_year: int) -> tuple[list[dict], dict]:
    """Laesst das Regelmodul das Jahr rechnen und gibt seine Zeilen und seinen Pruefteil zurueck. Dieselbe Fassung wie die Rechenblaetter
    des Portfolios (#486 Schritt 2; wie im Abschluss rechnen Ereignis und Jahr mit einem Modul)."""
    module = configuration.get("module") or {}
    manifest = module.get("manifest") or tax_plugin_manifest_v1(PLUGIN_ID)
    portfolio_ref = configuration["portfolio_ref"]
    selection_ref = "tsr_" + sha({"annual_statement": portfolio_ref, "year": tax_year})[:32]
    selection = TaxPluginSelection(selection_ref, 1, sha({"selection": selection_ref}), portfolio_ref, "realized_annual", manifest.plugin_id,
                                   manifest.plugin_version, manifest.rules_fingerprint, manifest.manifest_fingerprint, manifest.effective_from, "active")
    bound = new_tax_plugin_bound_input_v1(
        projection_mode="realized_annual", portfolio_ref=portfolio_ref,
        source_artifact_ref="tar_" + sha({"annual_rows": [row["event_ref"] for row in rows], "year": tax_year})[:32],
        cutoff=str(tax_year), rows=rows, classifications=[], parameters=parameters)
    result = run_tax_model_plugin_v2(bound_input=bound, context=configuration["context"], selection=selection, timeout_seconds=TIMEOUT_SECONDS,
                                     plugin_root=module.get("root"))
    return validate_annual_tax_candidate_v2(result, bound, selection, tax_year), dict(result.reconciliation)


def _amount(value: Any) -> Fraction:
    return Fraction(0) if value is None else Fraction(str(value))


def build_tax_annual_statement_v1(
    data_space_path: str | Path, context_value: Any, tax_year: int,
    sheet_builder: Callable[..., dict[str, Any]] | None = None,
    annual_runner: Callable[[Mapping[str, Any], list[dict], list[dict], int], tuple[list[dict], dict]] | None = None,
) -> dict[str, Any]:
    """Die Jahresrechnung eines Steuerjahres, mit allen Jahren ab 2020 davor fuer die Vortraege. Liest nur.

    Fuer 2016-2019 (#496) rechnet sie ab 2016 - nur in Grundzuegen und ausdruecklich nicht vollstaendig ('partial'); ab 2020
    bleibt die Kette, wie sie ist, damit sich an diesen Jahren nichts aendert."""
    if isinstance(tax_year, bool) or not isinstance(tax_year, int) or not PARTIAL_FIRST_YEAR <= tax_year <= 2100:
        _abort("tax_annual_statement_input_invalid")
    first_year = FIRST_YEAR if tax_year >= FIRST_YEAR else PARTIAL_FIRST_YEAR
    space = Path(data_space_path)
    try:
        scope = activity_reference_scope_v1(context_value)
        settings = read_institution_tax_settings_v1(space, context_value)
    except (AssetActivityReferenceV1Error, InstitutionTaxSettingsV1Error) as error:
        _abort("tax_annual_statement_input_invalid" if error.code.endswith("_input_invalid") else "tax_annual_statement_source_invalid")
    labels = {row["institution_key"]: row["institution_label"] for row in settings["institutions"]}
    entered_all = entered_by_year_v1(settings)
    # Zaehlt das Portfolio in einem Jahr nicht zur Veranlagung (#501), rechnet die Jahresrechnung es nicht; die Toepfe laufen
    # unveraendert weiter.
    from migrations.reference.tax_assessment_v1 import not_assessed_years_v1
    not_assessed = not_assessed_years_v1(space / "tax-ui", scope)
    base = {
        "contract_version": CONTRACT, "tax_year": tax_year, "first_year": first_year, "partial": tax_year < FIRST_YEAR,
        "method_lines": list(METHOD_LINES),
        "provider_access": False, "network_access": False, "canonical_write": False, "legal_advice": False,
    }
    chain = empty_chain_v1()
    years: list[dict[str, Any]] = []
    configuration: Mapping[str, Any] | None = None
    last_portfolios: list[str] = []
    statement = None
    for year in range(first_year, tax_year + 1):
        if year in not_assessed:
            years.append({"tax_year": year, "status": "not_assessed", "event_count": 0, "open_count": 0, "failure_code": None,
                          "projected_annual_tax": None, "closing": closing_totals_v1(chain) if chain["institutions"] or chain["personal"] else None})
            if year == tax_year:
                return {**base, "status": "not_assessed", "failed_year": year, "years": years, "statement": None}
            continue
        try:
            model = (sheet_builder or build_tax_event_sheets_v1)(space, context_value, year, list(ASSET_TYPES), keep_module_rows=True)
        except TaxEventSheetV1Error as error:
            _abort("tax_annual_statement_input_invalid" if error.code == "tax_event_sheet_input_invalid" else "tax_annual_statement_source_invalid")
        if model["status"] != "ready":
            return {**base, "status": model["status"], "failed_year": year, "years": years, "statement": None}
        sheets = model["sheets"]
        included = [sheet for sheet in sheets if sheet["calculation"]["status"] == "calculated" and isinstance(sheet.get("module_row"), dict)
                    and sheet["module_row"]["projection_status"] == "completed"]
        open_sheets = [sheet for sheet in sheets if sheet["calculation"]["status"] == "not_calculated"]
        # Ein Jahr ohne Ereignisse rechnet mit den Angaben des Portfolios von zuvor - seine Toepfe laufen weiter.
        portfolios = sorted({sheet["portfolio_id"] for sheet in sheets if sheet.get("portfolio_id")}) or last_portfolios
        last_portfolios = portfolios
        configurations = []
        for portfolio_id in portfolios:
            current = _configuration(space, scope, portfolio_id, year)
            if current["status"] != "ready":
                return {**base, "status": "settings_" + ("absent" if current["status"] == "tax_settings_absent" else "unreadable"),
                        "failed_year": year, "years": years, "statement": None}
            configurations.append(current)
        # Mehrere Portfolios rechnen gemeinsam nur mit denselben Angaben; sonst waere unklar, welche gelten.
        if len({repr(sorted((row["parameter_code"], str(row.get("rate_decimal")), str(row.get("amount_decimal")), str(row.get("applicability_value")))
                            for row in current["parameters"] if row["tax_year"] == year)) for current in configurations}) > 1:
            return {**base, "status": "settings_differ_between_portfolios", "failed_year": year, "years": years, "statement": None}
        configuration = configurations[0] if configurations else None
        entered = entered_all.get(year, {})
        if configuration is None:
            # Vor dem ersten Ereignis gibt es nichts zu rechnen; eingetragene Toepfe gehen in das naechste Jahr.
            for (key, code), value in entered.items():
                for bucket in CAPITAL_BUCKETS:
                    if code == OPENING_CODES[bucket]:
                        chain["institutions"].setdefault(key, {})[bucket] = _amount(value)
            years.append({"tax_year": year, "status": "no_events", "event_count": 0, "open_count": 0, "failure_code": None,
                          "projected_annual_tax": None, "closing": None})
            continue
        parameters, origin = annual_parameters_v1(configuration["parameters"], year, entered, chain)
        rows = [{**sheet["module_row"], "institution_key": institution_key_v1(sheet["event"].get("institution_label") or "")} for sheet in included]
        try:
            annual_rows, reconciliation = (annual_runner or _run_annual)(configuration, rows, parameters, year)
        except (TaxPluginV2Blocked, TaxPluginBlocked, RealizedTaxV2Blocked, RealizedTaxBlocked):
            _abort("tax_annual_statement_source_invalid")
        detail = reconciliation.get("annual_detail")
        summary = next((row for row in annual_rows if row["row_type"] == "summary"), None)
        # Ein Jahr ohne Ereignisse und ohne Werte je Institut rechnet das Modul im Ganzen - es gibt dann kein Institut zu zeigen.
        keyed = keyed_v1(rows, parameters)
        if not isinstance(detail, dict) or summary is None or (keyed and detail.get("institution_grouping") is not True):
            _abort("tax_annual_statement_source_invalid")
        if not keyed:
            detail = {**detail, "institutions": []}
        chain = next_chain_v1(detail, keyed)
        closing = closing_totals_v1(chain)
        years.append({"tax_year": year, "status": summary["projection_status"], "failure_code": summary["failure_code"],
                      "event_count": len(included), "open_count": len(open_sheets),
                      "projected_annual_tax": summary["projected_annual_tax_decimal"], "closing": closing})
        if year == tax_year:
            statement = _statement(year, sheets, included, open_sheets, summary, detail, reconciliation, origin, labels)
    if statement is None:
        return {**base, "status": "ready", "years": years, "statement": None}
    return {**base, "status": "ready", "years": years, "statement": statement}


def _statement(year: int, sheets: Sequence[Mapping[str, Any]], included: Sequence[Mapping[str, Any]], open_sheets: Sequence[Mapping[str, Any]],
               summary: Mapping[str, Any], detail: Mapping[str, Any], reconciliation: Mapping[str, Any], origin: Mapping[str, Any],
               labels: Mapping[str, str]) -> dict[str, Any]:
    """Die Rechnung des gewaehlten Jahres zum Zeigen: je Institut, je persoenlichem Topf, insgesamt und die Ereignisse dahinter."""
    shown: dict[str, str] = dict(labels)
    for sheet in sheets:
        label = sheet["event"].get("institution_label") or ""
        shown.setdefault(institution_key_v1(label), label)
    counts: dict[str, int] = {}
    for sheet in included:
        if sheet["calculation"]["tax_bucket"] in CAPITAL_BUCKETS:
            key = institution_key_v1(sheet["event"].get("institution_label") or "")
            counts[key] = counts.get(key, 0) + 1
    institutions = []
    for entry in detail["institutions"]:
        key = entry["institution_key"]
        taxes = [entry[bucket]["projected_annual_tax_decimal"] for bucket in CAPITAL_BUCKETS]
        institutions.append({
            "institution_key": key, "institution_label": shown.get(key) or NO_INSTITUTION, "event_count": counts.get(key, 0),
            "allowance_available": entry["allowance_available_decimal"], "withholding_available": entry["withholding_available_decimal"],
            "opening_origin": dict(origin["institutions"].get(key, {bucket: "none" for bucket in CAPITAL_BUCKETS})),
            "capital_equity": entry["capital_equity"], "capital_general": entry["capital_general"],
            # Die Summen beider Toepfe, exakt - damit Anzeige und Tabelle dieselbe Zahl runden.
            **{name: _text(_amount(entry["capital_equity"][field]) + _amount(entry["capital_general"][field]))
               for name, field in (("taxable_base", "taxable_base_decimal"), ("allowance_used", "allowance_used_decimal"),
                                   ("withholding_credit", "withholding_credit_decimal"))},
            "projected_tax": None if None in taxes else _text(sum((_amount(value) for value in taxes), Fraction(0))),
        })
    institutions.sort(key=lambda row: (row["institution_key"] == "", row["institution_label"].lower()))
    economic = sum((_amount(sheet["module_row"]["realized_gross_gain_decimal"]) + _amount(sheet["module_row"]["gross_income_decimal"]) for sheet in included), Fraction(0))
    tax = summary["projected_annual_tax_decimal"]
    rule = next((entry for entry in reconciliation.get("year_rules") or [] if entry.get("tax_year") == year), None)
    rates = {value["value_code"]: {"value": value["value_decimal"], "origin": value["value_origin"]} for value in (rule or {}).get("values", [])}
    taken = {sheet["sheet_no"] for sheet in included}
    events = []
    for sheet in sheets:
        calculation = sheet["calculation"]
        if calculation["status"] == "not_taxable":
            continue
        event = sheet["event"]
        events.append({
            "sheet_no": sheet["sheet_no"], "local_date": event["local_date"], "institution_label": event.get("institution_label") or NO_INSTITUTION,
            "account_label": event["account_label"], "asset_label": event["asset_label"], "event_type_label": sheet["event_type_label"],
            "tax_bucket_label": calculation.get("tax_bucket_label"), "taxable_amount": calculation.get("taxable_amount"),
            "economic_amount": sheet["economic_amount"], "included": sheet["sheet_no"] in taken, "reason_text": calculation.get("reason_text"),
        })
    return {
        "tax_year": year, "projection_status": summary["projection_status"], "failure_code": summary["failure_code"],
        "event_count": len(included), "open_count": len(open_sheets),
        "economic_amount": _text(economic), "projected_annual_tax": tax,
        "projected_net": None if tax is None else _text(economic - _amount(tax)),
        "taxable_net": summary["net_contribution_decimal"], "withholding_credit": summary["withholding_credit_decimal"],
        "allowance_available": summary["allowance_available_decimal"], "allowance_used": summary["allowance_used_decimal"],
        "institutions": institutions,
        "personal": [{"tax_bucket": bucket, "tax_bucket_label": BUCKET_LABELS[bucket], "opening_origin": origin.get(bucket, "none"), **detail[bucket]}
                     for bucket in PERSONAL_BUCKETS],
        "church_tax_applicability": (rule or {}).get("church_tax_applicability"), "rates": rates,
        "events": events,
    }


# --- Tabelle -------------------------------------------------------------------------------------------------------
_ORIGIN_TEXT = {"entered": "eingetragen", "carried": "aus dem Vorjahr", "none": "–"}
_STATUS_TEXT = {"completed": "gerechnet", "blocked": "ohne Steuerzahl", "no_events": "keine Ereignisse"}


def _comma(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace(".", ",")


def _money(value: Any) -> str:
    return "" if value is None else _comma(_cents(_fraction(value)))


def _safe(text: Any) -> str:
    """Text, den eine Tabellenkalkulation nicht als Formel liest. Ein Betrag bleibt ein Betrag - auch ein negativer."""
    value = "" if text is None else str(text)
    if re.fullmatch(r"-?[0-9]+(,[0-9]+)?", value):
        return value
    if value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        value = "'" + value
    return value


def render_tax_annual_statement_csv_v1(model: Mapping[str, Any], generated_at_utc: str) -> str:
    """Die Jahresrechnung als Tabelle: Semikolon, Dezimalkomma, Beträge auf Cent, ISO-Datum - Abschnitt für Abschnitt."""
    import csv
    if not isinstance(model, Mapping) or model.get("contract_version") != CONTRACT or model.get("status") != "ready" or model.get("statement") is None:
        _abort("tax_annual_statement_input_invalid")
    statement = model["statement"]
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    row = lambda *values: writer.writerow([_safe(value) for value in values])  # noqa: E731
    row("Jahresrechnung", statement["tax_year"])
    row("Erstellt (UTC)", generated_at_utc)
    row("Stand", _STATUS_TEXT.get(statement["projection_status"], statement["projection_status"]))
    row("Ereignisse gerechnet", statement["event_count"])
    row("Ereignisse ohne Steuerzahl (nicht enthalten)", statement["open_count"])
    row()
    row("Überblick", "Betrag in EUR")
    row("Ergebnis brutto (Gewinne und Erträge abzüglich Verluste)", _money(statement["economic_amount"]))
    row("Voraussichtliche Steuer", _money(statement["projected_annual_tax"]))
    row("Voraussichtlich netto", _money(statement["projected_net"]))
    row("Angerechnete Quellensteuer", _money(statement["withholding_credit"]))
    row("Freistellungsaufträge genutzt / eingetragen", f"{_money(statement['allowance_used'])} / {_money(statement['allowance_available'])}")
    row()
    row("Kapitalerträge je Institut", "Ereignisse", "Aktien Gewinne", "Aktien Verluste", "Allgemein Erträge", "Allgemein Verluste",
        "Verlusttopf Aktien zum 1.1.", "Herkunft", "Verlusttopf allgemein zum 1.1.", "Herkunft", "Verrechnet Aktien", "Verrechnet allgemein",
        "Freistellungsauftrag", "davon genutzt", "steuerpflichtig", "Quellensteuer angerechnet", "Steuer",
        "Verlusttopf Aktien zum 31.12.", "Verlusttopf allgemein zum 31.12.")
    for entry in statement["institutions"]:
        equity, general = entry["capital_equity"], entry["capital_general"]
        row(entry["institution_label"], entry["event_count"], _money(equity["positive_contribution_decimal"]), _money(equity["negative_contribution_decimal"]),
            _money(general["positive_contribution_decimal"]), _money(general["negative_contribution_decimal"]),
            _money(equity["opening_loss_carryforward_decimal"]), _ORIGIN_TEXT[entry["opening_origin"].get("capital_equity", "none")],
            _money(general["opening_loss_carryforward_decimal"]), _ORIGIN_TEXT[entry["opening_origin"].get("capital_general", "none")],
            _money(equity["used_loss_decimal"]), _money(general["used_loss_decimal"]), _money(entry["allowance_available"]), _money(entry["allowance_used"]),
            _money(entry["taxable_base"]), _money(entry["withholding_credit"]), _money(entry["projected_tax"]),
            _money(equity["closing_loss_carryforward_decimal"]), _money(general["closing_loss_carryforward_decimal"]))
    row()
    row("Über alle Institute", "Gewinne", "Verluste", "Saldo", "Freigrenze", "Verlustvortrag zum 1.1.", "Herkunft", "verrechnet",
        "steuerpflichtig", "Steuer", "Verlustvortrag zum 31.12.")
    for entry in statement["personal"]:
        row(entry["tax_bucket_label"], _money(entry["positive_contribution_decimal"]), _money(entry["negative_contribution_decimal"]),
            _money(entry["net_contribution_decimal"]), _money(entry["exemption_threshold_decimal"]), _money(entry["opening_loss_carryforward_decimal"]),
            _ORIGIN_TEXT[entry["opening_origin"]], _money(entry["used_loss_decimal"]), _money(entry["taxable_base_decimal"]),
            _money(entry["projected_annual_tax_decimal"]), _money(entry["closing_loss_carryforward_decimal"]))
    row()
    row("Sätze des Jahres", "Wert", "Herkunft")
    for code, label in (("capital_income_tax_rate", "Abgeltungsteuersatz in %"), ("personal_income_tax_rate", "Persönlicher Steuersatz in %"),
                        ("solidarity_surcharge_rate", "Solidaritätszuschlag in %"), ("church_tax_rate", "Kirchensteuersatz in %")):
        value = statement["rates"].get(code) or {}
        row(label, _comma(value.get("value")), {"user_parameter": "eigene Angabe", "module_year_value": "Rechtsstand des Regelmoduls"}.get(value.get("origin"), "–"))
    row()
    row("Jahre der Kette", "Stand", "Ereignisse", "ohne Steuerzahl", "Steuer", "Topf Aktien zum 31.12.", "Topf allgemein zum 31.12.",
        "Private Veräußerungen zum 31.12.", "Sonstige Einkünfte zum 31.12.")
    for entry in model["years"]:
        closing = entry["closing"] or {}
        row(entry["tax_year"], _STATUS_TEXT.get(entry["status"], entry["status"]), entry["event_count"], entry["open_count"], _money(entry["projected_annual_tax"]),
            _money(closing.get("capital_equity")), _money(closing.get("capital_general")), _money(closing.get("private_disposal")), _money(closing.get("other_income")))
    row()
    row("Ereignisse des Jahres", "Datum", "Institut", "Konto", "Vermögenswert", "Art", "Topf", "steuerpflichtig", "Gewinn bzw. Ertrag", "in der Rechnung", "Grund")
    for event in statement["events"]:
        row(f"Blatt {event['sheet_no']}", event["local_date"], event["institution_label"], event["account_label"], event["asset_label"],
            event["event_type_label"], event["tax_bucket_label"] or "", _money(event["taxable_amount"]), _money(event["economic_amount"]),
            "ja" if event["included"] else "nein", event["reason_text"] or "")
    row()
    for line in model["method_lines"]:
        row("Methode", line)
    return out.getvalue()


__all__ = [
    "CONTRACT", "FAILURE_CODES", "TaxAnnualStatementV1Error", "build_tax_annual_statement_v1", "render_tax_annual_statement_csv_v1",
    "tax_annual_statement_v1_error_codes",
]
