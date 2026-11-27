"""Portelyra-Leser smartbroker_plus: Wertpapier- und Devisenbelege (statement_reader_v1, Aufruf read_text/detect/finish).

Erzeugt aus dem bisherigen Kernmodul (rc.373) ohne Aenderung der Leselogik. Der Leser bekommt den Text eines Belegs
(PDF-Text erzeugt der Kern) und liefert ein Ergebnis; Gruende tragen nur ihren Code, den Text setzt der Kern.
"""
from __future__ import annotations

from decimal import Decimal
from decimal import InvalidOperation
from decimal import ROUND_HALF_UP
import re
from typing import Any, Mapping

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
    csv_rows as _csv_rows,
    german_day as _day,
    find as _find,
    german_decimal as _german,
    is_information as _information,
    multi_result as _multi,
    plain as _plain,
    reason as _reason,
    signed_decimal as _signed,
    is_tax_document as _tax_document,
)


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

SMARTBROKER_COLUMNS = {"DEPOTNUMMER", "TRANSAKTIONSTYP", "ISIN", "NAME 1", "STÜCKE", "AUSFÜHRUNGSZEITPUNKT", "AUSFÜHRUNGSKURS", "HANDELSWÄHRUNG",
                       "KONTOWÄHRUNG", "ANLAGEBETRAG IN KONTOWÄHRUNG", "GEBÜHREN IN KONTOWÄHRUNG", "STEUERN IN KONTOWÄHRUNG",
                       "GESAMTBETRAG IN KONTOWÄHRUNG", "STATUS DER TRANSAKTION"}

def _parse_smartbroker_csv(rows: list[dict[str, str]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []; reasons: dict[str, int] = {}
    def skip(code: str) -> None: reasons[code] = reasons.get(code, 0) + 1
    for row in rows:
        status, kind = row["STATUS DER TRANSAKTION"], {"BUY": "buy", "SELL": "sell"}.get(row["TRANSAKTIONSTYP"])
        if status == "CANCELLED": skip("order_cancelled"); continue
        if status != "CONFIRMED": skip("preconfirmed"); continue
        if kind is None: skip("unknown_document"); continue
        if row["HANDELSWÄHRUNG"] != "EUR" or row["KONTOWÄHRUNG"] != "EUR": skip("not_eur"); continue
        stamp = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", row["AUSFÜHRUNGSZEITPUNKT"])
        isin = row["ISIN"] if re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", row["ISIN"]) else None
        try:
            quantity = abs(_german(row["STÜCKE"])); gross = abs(_german(row["ANLAGEBETRAG IN KONTOWÄHRUNG"]))
            price = _german(row["AUSFÜHRUNGSKURS"]) if row["AUSFÜHRUNGSKURS"] else (gross / quantity if quantity else None)
            fee = abs(_german(row["GEBÜHREN IN KONTOWÄHRUNG"] or "0")); taxes = abs(_german(row["STEUERN IN KONTOWÄHRUNG"] or "0"))
            total = abs(_german(row["GESAMTBETRAG IN KONTOWÄHRUNG"])) if row["GESAMTBETRAG IN KONTOWÄHRUNG"] else None
        except (InvalidOperation, ValueError, SecuritiesStatementImportV1Error):
            skip("incomplete"); continue
        if not (stamp and isin and quantity and price):
            skip("incomplete"); continue
        candidates.append(_candidate(kind, "smartbroker", isin=isin, security_name=row["NAME 1"] or None, local_date=stamp.group(1), local_time=stamp.group(2),
                                     quantity=_plain(quantity), unit_price=_plain(price), gross_amount=_plain(gross), fee_amount=_plain(fee),
                                     taxes_amount=_plain(taxes) if taxes else None, net_amount=_plain(total) if total is not None else None,
                                     depot_ref=row["DEPOTNUMMER"] or None))
    return _multi(candidates, reasons)

def _parse_smartbroker(text: str) -> dict[str, Any]:
    rows = _csv_rows(text, SMARTBROKER_COLUMNS)
    if rows is not None:
        return _parse_smartbroker_csv(rows)
    head = text[:3000]
    if "Smartbroker" not in head:
        return _reason("wrong_institution")
    if re.search(r"Devisengesch[äa]ft|Devisen-Neugesch|Ihr (?:Kauf|Verkauf) von [A-Z]{3}", text[:4000]):
        return _reason("fx_trade", depot_ref=_find(r"Depot-Nr\.:\s*(\d+)", text))
    if _tax_document(text):
        return _reason("tax_document")
    if _information(text):
        return _reason("information")
    return _parse_baader_for_scalable(text, "smartbroker")

def _detect_smartbroker(text: str) -> bool:
    return _csv_rows(text.split("\n", 1)[0], SMARTBROKER_COLUMNS) is not None or "Smartbroker" in text[:3000]

FX_PROFILE = "smartbroker_fx"

FX_PRICE = Decimal("1e-12")

FX_ORDER_TIME = (12, 0, 0)   # Ordnungszeit fuer Belege ohne Uhrzeit, wie bei Wertpapier-Abrechnungen ohne Uhrzeit

def _fx_statement(text: str) -> dict[str, Any] | None:
    head = re.search(r"Perioden-Kontoauszug:\s*([A-Z]{3})-Konto", text)
    if not head:
        return None
    currency = head.group(1)
    # Der erste Auszug nach der Kontoeroeffnung nennt den Anfangssaldo ohne Datum; ein Auszug ohne Bewegung nur einen Saldo.
    balances = [(_day(match.group(1)) if match.group(1) else None, _signed(match.group(2)))
                for match in re.finditer(r"Kontostand in " + currency + r" am\s+(?:(\d\d\.\d\d\.\d{4})\s+)?(-?" + NUM + r"-?)\s*$", text, re.MULTILINE)]
    lines = []
    for line in text.splitlines():
        # Buchungstag, Text, Valuta, Betrag; eine Belastung traegt ein nachgestelltes Minus
        match = re.match(r"^(\d\d\.\d\d\.\d{4})\s{2,}(.+?)\s{2,}(\d\d\.\d\d\.\d{4})\s+([\d.,]+)(\s*-)?\s*$", line)
        if match:
            amount = _german(match.group(4))
            signed = -amount if match.group(5) else amount
            text = match.group(2).strip()
            # Welche Vorgangsart die Zeile belegt, sagt das Institut: "Coupons" ist der Zufluss aus Dividende, sonst Kauf bei einer
            # Gutschrift, Verkauf bei einer Belastung. Ob jede Zeile ihren Beleg hat und der Auszug aufgeht, prueft der Kern.
            kinds = ["deposit"] if text.startswith("Coupons") else (["buy"] if signed > 0 else ["sell"])
            lines.append({"booked": _day(match.group(1)), "valuta": _day(match.group(3)), "text": text, "amount": signed, "kinds": kinds})
    if len(balances) == 1 and not lines:
        balances = balances * 2
    return {"currency": currency, "lines": lines, "start": balances[0] if len(balances) >= 2 else None, "end": balances[-1] if len(balances) >= 2 else None}

def _fx_receipt(text: str) -> dict[str, Any]:
    order = _find(r"Ihr (Kauf|Verkauf) von\s+([A-Z]{3})\s+(" + NUM + ")", text, group=0)
    against = re.search(r"Gegenwert\s+([A-Z]{3})\s+(" + NUM + ")", text)
    trade, valuta = _find(r"Abschlussdatum\s+(\d\d\.\d\d\.\d{4})", text), _find(r"Valuta\s+(\d\d\.\d\d\.\d{4})", text)
    if not (order and against and trade and valuta):
        return _reason("incomplete")
    side, first, first_amount = re.match(r"Ihr (Kauf|Verkauf) von\s+([A-Z]{3})\s+(" + NUM + ")", order).groups()
    # "Ihr Verkauf von EUR a, Gegenwert CHF b" kauft b CHF; "Ihr Kauf/Verkauf von USD a, Gegenwert EUR b" kauft/verkauft a USD
    if first == "EUR" and against.group(1) != "EUR":
        kind, currency, amount, eur = ("buy" if side == "Verkauf" else "sell"), against.group(1), _german(against.group(2)), _german(first_amount)
    elif against.group(1) == "EUR" and first != "EUR":
        kind, currency, amount, eur = ("buy" if side == "Kauf" else "sell"), first, _german(first_amount), _german(against.group(2))
    else:
        return _reason("incomplete")
    if not amount or not eur:
        return _reason("incomplete")
    return _candidate(kind, FX_PROFILE, currency=currency, security_name=f"{currency} · Devisen" + ("kauf" if kind == "buy" else "verkauf"),
                      local_date=_day(trade), valuta=_day(valuta), quantity=_plain(amount), unit_price=_plain((eur / amount).quantize(FX_PRICE, ROUND_HALF_UP)),
                      gross_amount=_plain(eur), order_ref=_find(r"Vorgangs-Nr\.:\s*(\S+)", text), depot_ref=currency)

def _fx_dividend(text: str) -> dict[str, Any]:
    credit = re.search(r"Zu Gunsten Konto\s+\S+\s+Valuta:\s*(\d\d\.\d\d\.\d{4})\s+([A-Z]{3})\s+(" + NUM + ")", text)
    if not credit:
        return _reason("incomplete")
    currency = credit.group(2)
    if currency == "EUR":
        return _reason("fx_eur_credit")
    rate = re.search(r"Umrechnungskurs:\s*EUR/([A-Z]{3})\s+(" + NUM + ")", text)
    if not rate or rate.group(1) != currency:
        return _reason("incomplete")
    amount = _german(credit.group(3))
    eur = (amount / _german(rate.group(2))).quantize(CENT, ROUND_HALF_UP)
    isin = _find(r"ISIN:\s*([A-Z]{2}[A-Z0-9]{9}\d)", text)
    # Die ISIN des ausschuettenden Papiers gehoert zur Identitaet: zwei Dividenden koennen am selben Tag gleich hoch sein.
    # Kennung ist die Vorgangsnummer der Dividendenabrechnung: Derselbe Beleg traegt die Dividende und den Zufluss (#458).
    return _candidate("deposit", FX_PROFILE, currency=currency, isin=isin, security_name=f"{currency} · Zufluss aus Dividende",
                      local_date=_day(credit.group(1)), valuta=_day(credit.group(1)), quantity=_plain(amount),
                      unit_price=_plain((eur / amount).quantize(FX_PRICE, ROUND_HALF_UP)), gross_amount=_plain(eur), depot_ref=currency,
                      order_ref=_find(r"Vorgangs-Nr\.:\s*(\d+)", text))

def _parse_smartbroker_fx(text: str) -> dict[str, Any]:
    if "Smartbroker" not in text[:3000] and "Baader Bank" not in text:
        return _reason("wrong_institution")
    statement = _fx_statement(text)
    if statement is not None:
        if statement["currency"] == "EUR":
            return _reason("cash_movement")
        if statement["start"] is None:
            return _reason("incomplete")
        return {"status": "statement", **statement}
    if re.search(r"Devisengesch[äa]ft", text[:4000]):
        return _fx_receipt(text)
    if "Dividendenabrechnung" in text or ("Ertrag" in text and "Ausschüttung" in text):
        return _fx_dividend(text)
    if _tax_document(text):
        return _reason("tax_document")
    return _reason("fx_not_fx")

def _detect_smartbroker_fx(text: str) -> bool:
    if re.search(r"Perioden-Kontoauszug:\s*[A-Z]{3}-Konto|Devisengesch[äa]ft", text[:4000]):
        return True
    # Dividende mit Gutschrift in Fremdwaehrung (#550, 0.3.4): Den Zufluss auf das Fremdwaehrungskonto liest dieser Leser, die Dividende
    # selbst der Wertpapier-Leser. Bis 0.3.3 erkannte er sie nicht und bekam sie nur, wenn man ihn ausdruecklich waehlte.
    if ("Smartbroker" in text[:3000] or "Baader Bank" in text) and ("Dividendenabrechnung" in text or ("Ertrag" in text and "Ausschüttung" in text)):
        credit = re.search(r"Zu Gunsten Konto\s+\S+\s+Valuta:\s*\d\d\.\d\d\.\d{4}\s+([A-Z]{3})\s", text)
        return bool(credit and credit.group(1) != "EUR" and re.search(r"Umrechnungskurs:\s*EUR/" + credit.group(1) + r"\b", text))
    return False

def _finish_smartbroker_fx(candidates: list[dict[str, Any]], statements: list[dict[str, Any]], row_reasons: list[dict[str, Any]]) -> None:
    """Ordnungszeit fuer Devisenbelege ohne Uhrzeit. Die Saldoprobe der Auszuege (Kette, Aufgehen, Beleg je Zeile) rechnet der
    Kern selbst (Festlegung 07.11.2026): Ein Plugin meldet seine eigenen Zahlen nie als geprueft."""
    # Kein Devisenbeleg nennt eine Uhrzeit. Der Kern ordnet Bestandsvorgaenge desselben Tages nur mit Zeit (ohne Uhrzeit verlangt er
    # einen Reihenfolgenachweis): 12:00 als Ordnungszeit, am selben Tag Zugaenge vor Abgaengen, je eine Sekunde spaeter. FIFO
    # verbraucht ohnehin zuerst den aeltesten Bestand; die Reihenfolge entscheidet nur, ob ein Verkauf am Zufluss-Tag gedeckt ist.
    days: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate["profile"] == FX_PROFILE:
            days.setdefault((candidate["currency"], candidate["local_date"]), []).append(candidate)
    for members in days.values():
        members.sort(key=lambda item: (item["kind"] == "sell", item["valuta"] or "", item.get("order_ref") or "", item["candidate_ordinal"]))
        for offset, candidate in enumerate(members):
            hour, minute, second = FX_ORDER_TIME
            candidate["local_time"] = f"{hour:02d}:{minute:02d}:{second + offset:02d}"


READERS = {
    "smartbroker_plus_v1": _parse_smartbroker,
    "smartbroker_plus_fx_v1": _parse_smartbroker_fx,
}

DETECTORS = {
    "smartbroker_plus_v1": _detect_smartbroker,
    "smartbroker_plus_fx_v1": _detect_smartbroker_fx,
}

FINISHERS = {
    "smartbroker_plus_fx_v1": _finish_smartbroker_fx,
}
