"""Portelyra-Leser ing: Wertpapier- und Devisenbelege (statement_reader_v1, Aufruf read_text/detect/finish).

Erzeugt aus dem bisherigen Kernmodul (rc.373) ohne Aenderung der Leselogik. Der Leser bekommt den Text eines Belegs
(PDF-Text erzeugt der Kern) und liefert ein Ergebnis; Gruende tragen nur ihren Code, den Text setzt der Kern.
"""
from __future__ import annotations

from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from decimal import ROUND_HALF_UP
import re
from typing import Any, Sequence

from portelyra_reader_sdk_v1 import (
    CENT,
    CUR,
    NUM,
    REASONS,
    ReaderError as SecuritiesStatementImportV1Error,
    TAX_DOCUMENT,
    abort as _abort,
    candidate as _candidate,
    german_day as _german_day,
    find as _find,
    german_decimal as _german,
    plain as _plain,
    reason as _reason,
    is_tax_document as _tax_document,
)


class _Unreadable(Exception):
    """Ein Tag oder eine Uhrzeit im Beleg gibt es nicht (beschaedigter Beleg); der Beleg bekommt einen Grund (rc.379)."""


def _day(text: str) -> str:
    """TT.MM.JJJJ als ISO-Tag wie german_day des SDK, aber nur fuer einen echten Kalendertag. Sonst _Unreadable statt eines
    Absturzes oder eines ungueltigen Tags im Ergebnis (Selbsttest rc.379: gekippte Bytes, "2027-01-V4")."""
    if not re.fullmatch(r"\d\d\.\d\d\.\d{4}", text or ""):
        raise _Unreadable(text)
    try:   # vor dem SDK pruefen: german_day bricht bei einem unmoeglichen Tag den ganzen Beleg ab, hier bekommt er einen Grund
        datetime.strptime(text, "%d.%m.%Y")
    except ValueError:
        raise _Unreadable(text) from None
    return _german_day(text)

def _time(text: str) -> str:
    """hh:mm:ss nur als echte Uhrzeit; die Nachbearbeitung rechnet mit ihr."""
    try:
        datetime.strptime(text, "%H:%M:%S")
    except ValueError:
        raise _Unreadable(text) from None
    return text

def _lines(text: str) -> list[str]:
    return [re.sub(r"\s{2,}", " | ", line.strip()) for line in text.splitlines() if line.strip()]

def _ing_value(lines: Sequence[str], label: str) -> tuple[str, Decimal] | None:
    for line in lines:
        match = re.match(r"^" + label + r"(?: [^|]*)? \| (" + CUR + r") \| (" + NUM + r")$", line)
        if match:
            return match.group(1), _german(match.group(2))
    return None

def _ing_text(lines: Sequence[str], label: str) -> str | None:
    for line in lines:
        match = re.match(r"^" + label + r" \| (.+)$", line)
        if match:
            return match.group(1).strip()
    return None

def _parse_ing(text: str) -> dict[str, Any]:
    """Ein beschaedigter Beleg (Tag oder Uhrzeit, die es nicht gibt; Stueckzahl oder Kurs negativ) bekommt einen Grund statt
    eines Absturzes oder eines ungueltig geformten Vorgangs (Selbsttest rc.379). Gueltige Belege laufen unveraendert durch."""
    try:
        result = _parse_ing_document(text)
    except _Unreadable:
        return _reason("incomplete", depot_ref=_find(r"Direkt-Depot Nr\.:\s*\|?\s*(\d+)", text))
    if result.get("status") == "candidate" and any((result.get(key) or "").startswith("-") for key in ("quantity", "unit_price")):
        return _reason("incomplete", depot_ref=result.get("depot_ref"))
    return result

def _parse_ing_document(text: str) -> dict[str, Any]:
    if "ING-DiBa" not in text[:4000] and "Direkt-Depot" not in text[:4000]:
        return _reason("wrong_institution")
    lines = _lines(text)
    joined = "\n".join(lines)
    depot = _find(r"Direkt-Depot Nr\.:\s*\|?\s*(\d+)", text)
    if len(set(re.findall(r"Ordernummer \| (\S+)", joined))) > 1 or len(set(re.findall(r"ISIN \(WKN\)\s*\|?\s*([A-Z]{2}[A-Z0-9]{9}\d)", text))) > 1:
        return _reason("overview", depot_ref=depot)
    head = " ".join(lines[:15])
    isin = _find(r"ISIN \(WKN\)\s*\|?\s*([A-Z]{2}[A-Z0-9]{9}\d)", text)
    name = _ing_text(lines, "Wertpapierbezeichnung")
    if "Wertpapier Eingang" in head and "Aktiensplit" in joined:
        return _ing_stock_split(text, depot)
    if re.search(r"Wertpapier Eingang|Wertpapier Ausgang|Übertrag Eingang|Übertrag Ausgang", head):
        return _reason("custody_change", depot_ref=depot)
    if "Vorabpauschale" in head:
        return _ing_advance_lump_sum(lines, joined, depot, isin, name)
    if _tax_document(text):
        return _reason("tax_document", depot_ref=depot)
    trade = re.search(r"Wertpapierabrechnung \| (Kauf|Verkauf)", head)
    if trade:
        quantity = _find(r"Nominale \| Stück \| (" + NUM + ")", joined)
        price = _ing_value(lines, r"Kurs(?: \(Festpreisgeschäft\))?")
        gross = _ing_value(lines, "Kurswert")
        executed = re.search(r"Ausführungstag / -zeit \| (\d\d\.\d\d\.\d{4}) um (\d\d:\d\d:\d\d)", joined)
        if not (isin and quantity and price and gross and executed):
            return _reason("incomplete", depot_ref=depot)
        if price[0] != "EUR" or gross[0] != "EUR":
            return _reason("not_eur", depot_ref=depot)
        fee = Decimal(0)
        for label in ("Provision", "Handelsplatzgebühr", "Fremde Spesen", "Fremdspesen", "Börsenentgelt", "Ausgabeaufschlag", "Transaktionsentgelt", "Maklercourtage"):
            value = _ing_value(lines, label)
            if value:
                fee += value[1]
        net = _ing_value(lines, r"Endbetrag zu Ihren (?:Lasten|Gunsten)")
        gain = re.search(r"Veräußerungs(gewinn|verlust) nach Differenzmethode \| (" + NUM + r") EUR", joined)
        bank_gain = None
        if gain:
            bank_gain = _german(gain.group(2).lstrip("-")) * (-1 if gain.group(1) == "verlust" or gain.group(2).startswith("-") else 1)
        return _candidate("buy" if trade.group(1) == "Kauf" else "sell", "ing", isin=isin, security_name=name, local_date=_day(executed.group(1)),
                          local_time=_time(executed.group(2)), quantity=_plain(_german(quantity)), unit_price=_plain(price[1]),
                          gross_amount=_plain(gross[1]), fee_amount=_plain(fee), net_amount=_plain(net[1]) if net else None,
                          order_ref=_ing_text(lines, "Ordernummer"), depot_ref=depot, bank_gain=_plain(bank_gain) if bank_gain is not None else None)
    if re.search(r"Ertragsgutschrift|Dividendengutschrift|Zinsgutschrift|Ausschüttung", head):
        quantity = _find(r"Nominale \| (" + NUM + r") Stück", joined)
        pay = _ing_text(lines, "Zahltag")
        gross = _ing_value(lines, "Brutto")
        if gross is None and "Der Gegenwert ist als Ertrag zu versteuern" in text:
            return _reason("accumulating_income", depot_ref=depot)
        if not (isin and quantity and pay and gross):
            return _reason("incomplete", depot_ref=depot)
        gross_eur = gross[1]
        if gross[0] != "EUR":
            # Fremdwaehrung: Brutto in EUR = Brutto / Devisenkurs, auf zwei Stellen. Nach der Quellensteuer steht auf dem
            # Beleg nur noch der Netto-Gegenwert; ohne Quellensteuer ist der Gegenwert zugleich das Brutto.
            rate = _find(r"Umg\. z\. Dev\.-Kurs \((" + NUM + r")\)", joined)
            if rate is None or _german(rate) == 0:   # Kurs 0 nur in einem beschaedigten Beleg
                return _reason("incomplete", depot_ref=depot)
            gross_eur = (gross[1] / _german(rate)).quantize(CENT, ROUND_HALF_UP)
        withholding = None
        for line in lines:
            match = re.match(r"^(?:QuSt|Quellensteuer)[^|]*\(EUR (" + NUM + r")\)", line)
            if match:
                withholding = _german(match.group(1))
        net = _ing_value(lines, "Gesamtbetrag zu Ihren Gunsten")
        ex = _ing_text(lines, "Ex-Tag")
        return _candidate("dividend", "ing", isin=isin, security_name=name, local_date=_day(pay), eligible_quantity=_plain(_german(quantity)),
                          gross_amount=_plain(gross_eur), ex_date=_day(ex) if ex else None,
                          withholding_amount=_plain(withholding) if withholding is not None else None,
                          net_amount=_plain(net[1]) if net else None, depot_ref=depot)
    return _reason("unknown_document", depot_ref=depot)

ING_SPLIT_RATIO = re.compile(r"Splitverhältnis ist\s+(\d+)\s*:\s*(\d+)\s+auf Ihren Bestand vom\s+(\d\d\.\d\d\.\d{4})")

ING_SPLIT_ROW = re.compile(r"^\s*(" + NUM + r") Stück\s{2,}(.+?)\s{2,}(\d\d\.\d\d\.\d{4})\s+(\d+)\s*$", re.M)

def _ing_stock_split(text: str, depot: str | None) -> dict[str, Any]:
    """Splitmitteilung der ING (#451, rc.372): "Wertpapier Eingang" der Splitaktien.

    Die ING nennt das Verhaeltnis als Zusatzaktien je gehaltener Aktie: "1:2" heisst je Aktie zwei dazu, also neu : alt = 3 : 1;
    eingebucht werden nur die Zusatzaktien. Stichtag ist der Schlusstag der Einbuchung (erster Tag in neuen Stuecken), der
    Bestand dazu der vom genannten Tag. Zusatzaktien = 2 x Bestand bei "1:2". Andere Formen
    (etwa eine Zusammenlegung) bleiben eine Bestandsveraenderung zum manuellen Erfassen.
    """
    ratio = ING_SPLIT_RATIO.search(text)
    row = ING_SPLIT_ROW.search(text)
    isin = _find(r"ISIN \(WKN\):?\s*\|?\s*([A-Z]{2}[A-Z0-9]{9}\d)", text)
    if ratio is None or row is None or isin is None or ratio.group(1) != "1" or int(ratio.group(2)) < 1 or _german(row.group(1)) <= 0:
        return _reason("custody_change", depot_ref=depot)
    return _candidate("stock_split", "ing", isin=isin, security_name=row.group(2).strip(), local_date=_day(row.group(3)),
                      record_date=_day(ratio.group(3)), ratio_numerator=str(int(ratio.group(2)) + 1), ratio_denominator="1",
                      credited_quantity=_plain(_german(row.group(1))), order_ref=row.group(4), depot_ref=depot)

def _ing_advance_lump_sum(lines: Sequence[str], joined: str, depot: str | None, isin: str | None, name: str | None) -> dict[str, Any]:
    """Vorabpauschale je Fonds (#460): Betrag vor Teilfreistellung, Berechnungsjahr = Jahr des Ex-Tags - 1 (Zufluss am ersten
    Werktag des Folgejahres, § 18 Abs. 3 InvStG).

    ING hat die Vorlage gewechselt: Bis 2025 steht der Betrag vorn ("| EUR | 0,31", teils "| 0,31 EUR"), seit 2026 vorn nur
    der Wert je Stueck und der Gesamtbetrag auf der Rueckseite. Der Gesamtbetrag ist hoechstens Stueck x Wert je Stueck:
    Anteile, die im Jahr erworben wurden, kuerzt die Bank um ein Zwoelftel je vollem Monat vor dem Erwerb (§ 18 Abs. 2
    InvStG). Liegt er darueber, hat sich die Vorlage wieder geaendert, und der Beleg bekommt einen Grund statt einer Zahl.
    Ohne ausgewiesenen Gesamtbetrag wird nichts errechnet - der Wert je Stueck allein kennt die Kuerzung nicht."""
    quantity = _find(r"Nominale \| (" + NUM + r") Stück", joined)
    ex, pay = _ing_text(lines, "Ex-Tag"), _ing_text(lines, "Zahltag")
    total = _ing_value(lines, r"Vorabpauschale gem\. § 18 InvStG")
    amount = total[1] if total and total[0] == "EUR" else None
    if amount is None:
        found = _find(r"^Vorabpauschale gem\. § 18 InvStG \| (" + NUM + r") EUR$", joined, re.M)
        amount = _german(found) if found else None
    per_unit = _find(r"^Vorabpauschale per Stück \| (" + NUM + r") EUR$", joined, re.M)
    day = ex or pay
    if not (isin and quantity and day and amount is not None and re.fullmatch(r"\d\d\.\d\d\.\d{4}", day)):
        return _reason("incomplete", depot_ref=depot)
    if per_unit and amount > _german(per_unit) * _german(quantity) + CENT:
        return _reason("advance_lump_sum_inconsistent", depot_ref=depot)
    return _candidate("advance_lump_sum", "ing", isin=isin, security_name=name, local_date=_day(pay or day), ex_date=_day(ex) if ex else None,
                      eligible_quantity=_plain(_german(quantity)), gross_amount=_plain(amount), depot_ref=depot, calculation_year=int(day[-4:]) - 1)

def _detect_ing(text: str) -> bool:
    return "ING-DiBa" in text[:4000] and "Direkt-Depot" in text[:4000]

def _ing_order_number(order_ref: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", order_ref))

def _finish_ing(candidates: list[dict[str, Any]], statements: list[dict[str, Any]], row_reasons: list[dict[str, Any]]) -> None:
    """Kaeufe desselben Papiers am selben Tag ordnet ING nach der Ordernummer, nicht nach der Ausfuehrungszeit (#469).

    ING verbraucht die Lots in der Reihenfolge der Auftragserteilung. Laeuft die Ausfuehrung anders herum, weichen die Gewinne
    spaeterer Verkaeufe sonst vom Beleg ab (eine Order mit kleinerer Nummer kann spaeter ausgefuehrt sein). Festlegung:
    nach Ordernummer. Die Ordnungszeit des frueheren Auftrags rueckt deshalb eine Sekunde vor den
    naechsten; die Ausfuehrungszeit bleibt am Kandidaten stehen. Die Regel gilt nur innerhalb eines Tages.
    """
    days: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate["profile"] == "ing" and candidate["kind"] == "buy" and candidate.get("local_time") and candidate.get("order_ref"):
            days.setdefault((candidate.get("depot_ref"), candidate["isin"], candidate["local_date"]), []).append(candidate)
    for members in days.values():
        members.sort(key=lambda item: _ing_order_number(item["order_ref"]))
        for earlier, later in reversed(list(zip(members, members[1:]))):
            if earlier["local_time"] < later["local_time"]:
                continue
            moved = datetime.strptime(later["local_time"], "%H:%M:%S") - timedelta(seconds=1)
            if moved.day != 1:
                continue
            earlier["executed_local_time"] = earlier["local_time"]
            earlier["local_time"] = moved.strftime("%H:%M:%S")


READERS = {
    "ing_direkt_depot_v1": _parse_ing,
}

DETECTORS = {
    "ing_direkt_depot_v1": _detect_ing,
}

FINISHERS = {
    "ing_direkt_depot_v1": _finish_ing,
}
