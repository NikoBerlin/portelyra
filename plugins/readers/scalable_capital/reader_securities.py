"""Portelyra-Leser scalable_capital: Wertpapier- und Devisenbelege (statement_reader_v1, Aufruf read_text/detect/finish).

Erzeugt aus dem bisherigen Kernmodul (rc.373) ohne Aenderung der Leselogik. Der Leser bekommt den Text eines Belegs
(PDF-Text erzeugt der Kern) und liefert ein Ergebnis; Gruende tragen nur ihren Code, den Text setzt der Kern.
"""
from __future__ import annotations

from decimal import Decimal
from decimal import ROUND_HALF_UP
import re
from typing import Any

from portelyra_reader_sdk_v1 import (
    CENT,
    CUR,
    INFORMATION,
    NUM,
    REASONS,
    ReaderError as SecuritiesStatementImportV1Error,
    TAX_DOCUMENT,
    abort as _abort,
    candidate as _candidate,
    german_day as _day,
    find as _find,
    german_decimal as _german,
    is_information as _information,
    plain as _plain,
    reason as _reason,
    signed_decimal as _signed,
    is_tax_document as _tax_document,
)


def _scalable_issuer(text: str) -> str | None:
    """Baader rechnete fuer Scalable ab (beide im Kopf); spaete Baader-Belege nach dem Wechsel von Scalable zur eigenen Bank nennen nur Baader."""
    head = text[:3000]
    if "Smartbroker" in head:
        return None  # Baader rechnet auch fuer Smartbroker ab; das liest der Smartbroker-Leser
    if "Baader Bank" in head and "Scalable Capital" in head:
        return "baader_scalable"
    if "Scalable Capital Bank GmbH" in head:
        return "scalable_bank"
    if "Scalable Capital GmbH" in head:
        return "scalable_capital"
    if "baaderbank.de" in head or "Baader Bank" in text:
        return "baader_scalable"
    return None

def _parse_baader_for_scalable(text: str, profile: str = "baader_scalable") -> dict[str, Any]:
    depot = _find(r"Depot-Nr\.:\s*(\d+)", text)
    if re.search(r"Depotauslieferung|Depoteinlieferung|Auslieferung|Einlieferung|Kapitalmaßnahme|Split", text[:2500]):
        return _reason("custody_change", depot_ref=depot)
    isin = _find(r"ISIN:\s*([A-Z]{2}[A-Z0-9]{9}\d)", text)
    nominal = re.search(r"^\s*STK\s+(" + NUM + r")\s{2,}(.+?)\s{2,}(" + CUR + r")\s+(" + NUM + r")", text, re.M)
    if "Dividendenabrechnung" in text or ("Ausschüttung" in text[:2500] and "Wertpapierabrechnung" not in text):
        gross_match = re.search(r"^\s*Bruttobetrag\s+(" + CUR + r")\s+(" + NUM + ")", text, re.M)
        pay = _find(r"Zahltag:\s*(\d\d\.\d\d\.\d{4})", text)
        if not (isin and nominal and gross_match and pay):
            return _reason("incomplete", depot_ref=depot)
        # Fremdwaehrung: EUR-Brutto = Bruttobetrag / Umrechnungskurs (so steht es als Bemessungsgrundlage im Beleg)
        rate = Decimal(1)
        if gross_match.group(1) != "EUR":
            fx = re.search(r"Umrechnungskurs:\s*EUR/" + gross_match.group(1) + r"\s+(" + NUM + ")", text)
            if fx is None:
                return _reason("incomplete", depot_ref=depot)
            rate = _german(fx.group(1))
        gross = _plain((_german(gross_match.group(2)) / rate).quantize(CENT, ROUND_HALF_UP))
        withholding_match = re.search(r"^\s*(?:[A-Z]{2}-)?Quellensteuer\s+(" + CUR + r")\s+(" + NUM + r"\s*-?)", text, re.M)
        withholding = _plain((abs(_signed(withholding_match.group(2))) / (rate if withholding_match.group(1) != "EUR" else Decimal(1))).quantize(CENT, ROUND_HALF_UP)) if withholding_match else None
        net = _find(r"Zu Gunsten Konto\s+\S+\s+Valuta:\s*\d\d\.\d\d\.\d{4}\s+EUR\s+(" + NUM + ")", text)
        ex = _find(r"Ex-Tag:\s*(\d\d\.\d\d\.\d{4})", text)
        return _candidate("dividend", profile, isin=isin, security_name=nominal.group(2).strip(), local_date=_day(pay),
                          eligible_quantity=_plain(_german(nominal.group(1))), gross_amount=gross,
                          ex_date=_day(ex) if ex else None, withholding_amount=withholding,
                          net_amount=_plain(_german(net)) if net else None, order_ref=_find(r"Vorgangs-Nr\.:\s*(\d+)", text), depot_ref=depot)
    kind = _find(r"Wertpapierabrechnung:\s*(Kauf|Verkauf)", text)
    if kind is None:
        return _reason("unknown_document", depot_ref=depot)
    if not (isin and nominal):
        return _reason("incomplete", depot_ref=depot)
    if nominal.group(3) != "EUR":
        return _reason("not_eur", depot_ref=depot)
    gross = _find(r"^\s*Kurswert\s+EUR\s+(" + NUM + ")", text, re.M)
    executed = re.search(r"STK\s+" + NUM + r"\s+" + CUR + r"\s+" + NUM + r"\s+.+?\s(\d\d\.\d\d\.\d{4})\s+(\d\d:\d\d:\d\d)", text)
    local_date = _day(executed.group(1)) if executed else (_day(_find(r"Auftragsdatum:\s*(\d\d\.\d\d\.\d{4})", text)) if _find(r"Auftragsdatum:\s*(\d\d\.\d\d\.\d{4})", text) else None)
    if not (gross and local_date):
        return _reason("incomplete", depot_ref=depot)
    fee = Decimal(0)
    for label in ("Provision", "Fremde Spesen", "Börsenentgelt", "Fremdkostenzuschlag", "Ordergebühr", "Transaktionsentgelt"):
        value = _find(r"^\s*" + label + r"\s+EUR\s+(" + NUM + r"\s*-?)", text, re.M)
        if value:
            fee += abs(_signed(value))
    net = _find(r"Zu (?:Lasten|Gunsten) Konto\s+\S+\s+Valuta:\s*\d\d\.\d\d\.\d{4}\s+EUR\s+(" + NUM + ")", text)
    return _candidate("buy" if kind == "Kauf" else "sell", profile, isin=isin, security_name=nominal.group(2).strip(), local_date=local_date,
                      local_time=executed.group(2) if executed else None, quantity=_plain(_german(nominal.group(1))),
                      unit_price=_plain(_german(nominal.group(4))), gross_amount=_plain(_german(gross)), fee_amount=_plain(fee),
                      net_amount=_plain(_german(net)) if net else None, order_ref=_find(r"Vorgangs-Nr\.:\s*(\d+)", text), depot_ref=depot,
                      fee_on_cash_statement=fee == 0)

def _scalable_advance_lump_sum(text: str, depot: str | None, profile: str) -> dict[str, Any]:
    """Vorabpauschale je Fonds bei Scalable (rc.352, wie ING seit #460): Betrag vor Teilfreistellung.

    Vorn steht er in der Kontobewegung (Spalte „Vorabpauschale“ neben „Steuern“), auf der Rueckseite als „Gewinn oder Verlust“;
    beide muessen gleich sein, und „Zu versteuern“ muss der Betrag ohne die Teilfreistellung sein - sonst hat sich die Vorlage
    geaendert, und der Beleg bekommt einen Grund statt einer Zahl. Berechnungsjahr ist „Angefallen im Kalenderjahr“ (sonst
    „Relevant für Steuerjahr“ - 1), das Datum der Ex-Tag: der Zufluss am ersten Werktag des Folgejahres (§ 18 Abs. 3 InvStG).
    Der Beleg nennt keine Depotnummer; er erbt das einzige Depot desselben Ausstellers, wie eine Dividende."""
    isin = _find(r"^\s*für\s+.*\(([A-Z]{2}[A-Z0-9]{9}\d)\)\s*$", text, re.M)
    name = _find(r"^\s*für\s+(.+?)\s+\([A-Z]{2}[A-Z0-9]{9}\d\)\s*$", text, re.M)
    quantity = _find(r"Berechtigte Anzahl\s+(" + NUM + r")", text)
    ex = _find(r"Ex-Tag\s+(\d\d\.\d\d\.\d{4})", text)
    accrued = _find(r"Angefallen im\s*(?:Kalenderjahr)?\s*\n\s*(\d{4})\s*$", text, re.M) or _find(r"Angefallen im Kalenderjahr\s+(\d{4})", text)
    relevant = _find(r"Relevant für Steuerjahr\s+(\d{4})", text)
    movement = re.search(r"^\s*(\d\d\.\d\d\.\d{4})\s+\d\d\.\d\d\.\d{4}\s+\S.*?\s(" + NUM + r")\s*EUR\s+(" + NUM + r")\s*EUR\s*$", text, re.M)
    gain = _find(r"^\s*Gewinn oder Verlust\s+(" + NUM + r")", text, re.M)
    free = _find(r"^\s*Teilfreistellung\s+(\d+(?:,\d+)?)\s*%", text, re.M)
    taxable = _find(r"^\s*Zu versteuern\s+(" + NUM + r")", text, re.M)
    burden = _find(r"^\s*Steuerbelastung\s+(" + NUM + r")\s*EUR", text, re.M)
    amounts = {_german(value) for value in ((movement.group(2) if movement else None), gain) if value is not None}
    day = ex or (movement.group(1) if movement else None)
    year = int(accrued) if accrued else int(relevant) - 1 if relevant else int(ex[-4:]) - 1 if ex else None
    if not (isin and quantity and day and year and amounts):
        return _reason("incomplete", depot_ref=depot)
    amount = next(iter(amounts))
    if len(amounts) > 1 or amount < 0 or (relevant and int(relevant) != year + 1):
        return _reason("advance_lump_sum_inconsistent", depot_ref=depot)
    if free is not None and taxable is not None:
        expected = (amount * (Decimal(100) - _german(free)) / Decimal(100)).quantize(CENT, ROUND_HALF_UP)
        if abs(expected - _german(taxable)) > CENT:
            return _reason("advance_lump_sum_inconsistent", depot_ref=depot)
    taxes = movement.group(3) if movement else burden
    return _candidate("advance_lump_sum", profile, isin=isin, security_name=name, local_date=_day(day), ex_date=_day(ex) if ex else None,
                      eligible_quantity=_plain(_german(quantity)), gross_amount=_plain(amount), depot_ref=depot, calculation_year=year,
                      taxes_amount=_plain(abs(_german(taxes))) if taxes else None)

def _parse_scalable_capital(text: str, profile: str) -> dict[str, Any]:
    depot = _find(r"^\s*Depot\s+(\d+)", text, re.M) or _find(r"in Depot\s+(\d+)", text)
    if re.search(r"^Depoteinlieferung|^Depotauslieferung|^Depotübertrag|^Kapitalmaßnahme|^Split", text, re.M):
        return _reason("custody_change", depot_ref=depot)
    if re.search(r"^\s*Vorabpauschale\s*$", text, re.M):
        return _scalable_advance_lump_sum(text, depot, profile)
    if re.search(r"^Steuerneuberechnung\s*$", text, re.M):
        return _reason("tax_document", depot_ref=depot)
    if re.search(r"^(?:Dividende|Ausschüttung)\s*$", text, re.M):
        isin = _find(r"^ISIN\s+([A-Z]{2}[A-Z0-9]{9}\d)", text, re.M)
        quantity = _find(r"^Berechtigte Anzahl\s+(" + NUM + ")", text, re.M)
        row = re.search(r"^(\d\d\.\d\d\.\d{4})\s+(\d\d\.\d\d\.\d{4})\s+Gutschrift\s+(" + NUM + r") (" + CUR + r")\s+(" + NUM + r")\s+(" + NUM + r") EUR", text, re.M)
        if not (isin and quantity and row):
            return _reason("incomplete", depot_ref=depot)
        withholding = _find(r"Ausländische Quellensteuer\s+(" + NUM + r") EUR", text)
        net = _find(r"Gesamtbetrag\s+(" + NUM + r") EUR", text)
        ex = _find(r"^Ex Tag\s+(\d\d\.\d\d\.\d{4})", text, re.M)
        return _candidate("dividend", profile, isin=isin, security_name=_find(r"^Berechtigtes Wertpapier\s+(.+?)\s*$", text, re.M),
                          local_date=_day(row.group(1)), eligible_quantity=_plain(_german(quantity)), gross_amount=_plain(_german(row.group(6))),
                          ex_date=_day(ex) if ex else None, withholding_amount=_plain(abs(_signed(withholding))) if withholding else None,
                          net_amount=_plain(_german(net)) if net else None, depot_ref=depot)
    if len(set(re.findall(r"^\s+([A-Z]{2}[A-Z0-9]{9}\d)\s*$", text, re.M))) > 1:
        return _reason("overview", depot_ref=depot)
    trade = re.search(r"^(Kauf|Verkauf)\s{2,}(.+?)\s{2,}(" + NUM + r") Stk\.\s+(" + NUM + r") (" + CUR + r")\s+(" + NUM + r") EUR\s*\n\s+([A-Z]{2}[A-Z0-9]{9}\d)", text, re.M)
    if trade is None:
        return _reason("unknown_document", depot_ref=depot)
    if trade.group(5) != "EUR":
        return _reason("not_eur", depot_ref=depot)
    executed = re.search(r"Ausführung\s+(\d\d\.\d\d\.\d{4})\s+(\d\d:\d\d:\d\d)", text)
    if executed is None:
        return _reason("incomplete", depot_ref=depot)
    fee = Decimal(0)
    for label in ("Ordergebühren", "Finanztransaktionssteuer", "Fremdkostenzuschlag"):
        value = _find(label + r"\s+(" + NUM.replace("-?", "[+-]?") + r") EUR", text)
        if value:
            fee += abs(_signed(value))
    total = _find(r"^\s+(?:Total|Belastung|Gutschrift)\s+(" + NUM + r") EUR", text, re.M)
    gain = _find(r"^Gewinn(?: oder Verlust)?\s.*?(" + NUM.replace("-?", "[+-]?") + r") EUR\s*$", text, re.M)
    return _candidate("buy" if trade.group(1) == "Kauf" else "sell", profile, isin=trade.group(7), security_name=trade.group(2).strip(),
                      local_date=_day(executed.group(1)), local_time=executed.group(2), quantity=_plain(_german(trade.group(3))),
                      unit_price=_plain(_german(trade.group(4))), gross_amount=_plain(_german(trade.group(6))), fee_amount=_plain(fee),
                      net_amount=_plain(_german(total)) if total else None, order_ref=_find(r"Order\s+(SCAL\w+)", text), depot_ref=depot,
                      bank_gain=_plain(_signed(gain)) if gain else None)

def _parse_scalable(text: str) -> dict[str, Any]:
    issuer = _scalable_issuer(text)
    if issuer is None:
        return _reason("wrong_institution")
    if _tax_document(text):
        return _reason("tax_document")
    if _information(text):
        return _reason("information")
    if issuer == "baader_scalable":
        return _parse_baader_for_scalable(text)
    return _parse_scalable_capital(text, issuer)

def _detect_scalable(text: str) -> bool:
    return _scalable_issuer(text) is not None


READERS = {
    "scalable_capital_v1": _parse_scalable,
}

DETECTORS = {
    "scalable_capital_v1": _detect_scalable,
}

FINISHERS = {
}
