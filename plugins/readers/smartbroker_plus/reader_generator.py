"""Erzeuger erfundener Smartbroker+-Belege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Wie die Referenz (c24): Aus einem Startwert entstehen erfundene Vorgaenge; aus ihnen baut der Erzeuger den Beleg im Format des
Instituts und - unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der Leser nur
sich selbst. Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Namen, Kunden-, Depot-, Konto- und Vorgangsnummern, ISIN,
Betraege, Tage.

Abgedeckt:
- Wertpapiere: CSV-Export der Transaktionen (Kauf und Verkauf, auch Bruchstuecke, Kurs fehlt und folgt aus Betrag und Stuecken,
  Gebuehren und Steuern mit und ohne Vorzeichen, Gesamtbetrag leer, Zeit mit Leerzeichen oder "T", mit und ohne BOM, CRLF; Zeilen mit
  Grund: storniert, vorlaeufig, andere Transaktionsart, Fremdwaehrung, Pflichtangaben fehlen) sowie Abrechnungen der Baader Bank fuer
  Smartbroker als PDF-Text (Dividende mit Gutschrift in EUR oder Fremdwaehrung, Quellensteuer, Kauf und Verkauf mit Teilausfuehrungen
  und Gebuehren). Gruende: Devisengeschaeft, Steuerunterlage, Information, Bestandsveraenderung, Fremdwaehrung, Pflichtangaben fehlen,
  unbekannte Belegart.
- Devisen: Perioden-Kontoauszuege der Fremdwaehrungskonten (Coupons, Devisenkauf und -verkauf mit nachgestelltem Minus, Folgezeilen,
  Monat ohne Bewegung mit einem oder zwei Salden, erster Auszug ohne Datum am Anfangssaldo; EUR-Konto und Auszug ohne Endsaldo mit
  Grund), Devisenbelege (Kauf und Verkauf, die Waehrung vorn oder als Gegenwert; ohne Valuta mit Grund) und seit 1.2.0 (#550)
  Dividendenabrechnungen mit Gutschrift in Fremdwaehrung (Zufluss aus Ertrag, EUR-Wert ueber den Umrechnungskurs des Belegs).

Die Tage liegen in der Vergangenheit (2021-2024), damit der Beleg auch die Regel "kein Buchungstag nach heute" erfuellt, wenn der
Selbsttest vor einer Installation mit dem Datum des Rechners laeuft.
"""
from __future__ import annotations

import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import io
import random
from typing import Any, Callable

CENT = Decimal("0.01")
FX_PRICE = Decimal("1e-12")
BAADER = "Baader Bank AG Weihenstephaner Straße 4 85716 Unterschleißheim"
NAMES = ("Invented Equity Fund", "Erfundene Industrie AG", "Beispiel Technologie Inc.", "Muster Welt ETF", "Fantasia Energy Corp.",
         "Testland Versorger SE", "Imaginary Pharma plc", "Phantasie Global Small Cap ETF")
COUNTRIES = ("US", "DE", "IE", "LU", "FR", "NL")
FOREIGN = ("USD", "USD", "USD", "CHF", "GBP", "CAD", "DKK")
SB_HEADER = ["DATUM", "KUNDENNUMMER", "DEPOTNUMMER", "TRANSAKTIONSTYP", "ISIN", "WKN", "KÜRZEL", "NAME 1", "NAME 2", "ASSETKLASSE", "STÜCKE",
             "HANDELSDATUM", "KONTOWÄHRUNG", "VALUTADATUM", "AUSFÜHRUNGSZEITPUNKT", "AUSFÜHRUNGSKURS", "HANDELSWÄHRUNG",
             "ANLAGEBETRAG IN KONTOWÄHRUNG", "GEBÜHREN IN KONTOWÄHRUNG", "STEUERN IN KONTOWÄHRUNG", "ZINSEN IN KONTOWÄHRUNG",
             "GESAMTBETRAG IN KONTOWÄHRUNG", "BÖRSE", "STATUS DER TRANSAKTION"]


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _german(value: Decimal) -> str:
    """Deutsches Zahlformat mit Tausenderpunkt und so vielen Nachkommastellen, wie der Wert traegt: 1234.50 -> "1.234,50"."""
    sign = "-" if value < 0 else ""
    whole, _, fraction = format(abs(value), "f").partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:]); whole = whole[:-3]
    groups.insert(0, whole)
    return sign + ".".join(groups) + ("," + fraction if fraction else "")


def _csv_number(value: Decimal) -> str:
    """Zahl im CSV-Export: Dezimalkomma, ohne Tausenderpunkt ("12,345", "-1")."""
    return format(value, "f").replace(".", ",")


def _money(rng: random.Random, low: int, high: int) -> Decimal:
    """Betrag in Cent aus [low, high) mit zwei Nachkommastellen."""
    return Decimal(rng.randrange(low, high)).scaleb(-2)


def _day(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _business_day(rng: random.Random, first: date = date(2021, 1, 4), days: int = 1440) -> date:
    value = first + timedelta(days=rng.randrange(days))
    while value.weekday() >= 5:
        value += timedelta(days=1)
    return value


def _clock(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def _isin(rng: random.Random) -> str:
    return f"{rng.choice(COUNTRIES)}0000{rng.randrange(10**5):05d}{rng.randrange(10)}"


def _price(rng: random.Random) -> Decimal:
    if rng.random() < 0.7:
        return Decimal(rng.randrange(1000, 500_000)).scaleb(-2)
    return Decimal(rng.randrange(100_000, 5_000_000)).scaleb(-4)


def _pad(width: int) -> str:
    return " " * width


def _candidate(kind: str, profile: str, **fields: Any) -> dict[str, Any]:
    """Ergebnisform eines Vorgangs (securities-result.schema.json): alle Felder, nicht genannte leer."""
    value = {"status": "candidate", "kind": kind, "profile": profile, "isin": None, "security_name": None, "local_date": None,
             "local_time": None, "quantity": None, "unit_price": None, "gross_amount": None, "fee_amount": "0", "eligible_quantity": None,
             "order_ref": None, "depot_ref": None, "ex_date": None, "net_amount": None, "taxes_amount": None, "withholding_amount": None,
             "bank_gain": None, "fee_on_cash_statement": False, "currency": None, "valuta": None, "statement_checked": False}
    value.update(fields)
    return value


def _reason(code: str, **fields: Any) -> dict[str, Any]:
    """Grund ohne Text: den Text setzt der Kern (der Leser traegt den Code auch als Text)."""
    return {"status": "not_importable", "reason_code": code, "reason": code, **fields}


def _head(depot: str | None, reference: str) -> list[str]:
    """Kopf der Baader-Belege fuer Smartbroker (Devisenbelege und Auszuege nennen kein Depot)."""
    return [f"{BAADER}{_pad(35)}Smartbroker AG"] + ([f"{_pad(97)}Depot-Nr.: {depot}"] if depot else []) + [f"{_pad(97)}Vorgangs-Nr.: {reference}"]


def _depot(rng: random.Random, share: float = 0.7) -> str | None:
    return f"99{rng.randrange(10**7, 10**8)}" if rng.random() < share else None


# ---------------------------------------------------------------- Wertpapiere: CSV-Export
def _export(rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    customer, depot = str(rng.randrange(10**6, 10**7)), f"99{rng.randrange(10**7, 10**8)}"
    day = _business_day(rng, days=1240)          # hoechstens 24 Zeilen zu je 8 Tagen: der Export endet 2024
    rows: list[dict[str, str]] = []
    candidates: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    for _ in range(rng.randrange(1, 25)):
        day += timedelta(days=rng.randrange(0, 9))
        moment = rng.randrange(8 * 3600, 22 * 3600)
        side = rng.choice(("BUY", "SELL"))
        isin, name = _isin(rng), rng.choice(NAMES)
        whole = rng.random() < 0.7
        quantity = Decimal(rng.randrange(1, 300)) if whole else Decimal(rng.randrange(100, 100_000)).scaleb(-3)
        price = _money(rng, 100, 300_000) if whole and rng.random() < 0.5 else _price(rng)
        gross = (quantity * price).quantize(CENT, ROUND_HALF_UP)
        fee = rng.choice((Decimal("0"), Decimal("0"), Decimal("1"), Decimal("4"), _money(rng, 1, 1000)))
        taxes = (gross * Decimal(rng.randrange(1, 300)) / 10_000).quantize(CENT, ROUND_HALF_UP) if side == "SELL" and rng.random() < 0.3 else Decimal("0")
        if side == "SELL" and fee + taxes >= gross:
            fee = Decimal("0")                   # kleiner Verkauf: keine Gebuehr, die den Erloes uebersteigt
        total = gross + fee if side == "BUY" else gross - fee - taxes
        stamp = f"{day.isoformat()}{rng.choice((' ', 'T'))}{_clock(moment)}"
        signed = -1 if side == "SELL" and rng.random() < 0.5 else 1   # Abgaenge stehen teils mit Minus im Export
        row = {"DATUM": f"{day.isoformat()} {_clock(moment)}", "KUNDENNUMMER": customer, "DEPOTNUMMER": depot, "TRANSAKTIONSTYP": side,
               "ISIN": isin, "WKN": "000000", "KÜRZEL": "INV", "NAME 1": name, "NAME 2": "", "ASSETKLASSE": rng.choice(("STOCK", "ETF", "FUND")),
               "STÜCKE": _csv_number(quantity * signed), "HANDELSDATUM": day.isoformat(), "KONTOWÄHRUNG": "EUR",
               "VALUTADATUM": (day + timedelta(days=2)).isoformat(), "AUSFÜHRUNGSZEITPUNKT": stamp, "AUSFÜHRUNGSKURS": _csv_number(price),
               "HANDELSWÄHRUNG": "EUR", "ANLAGEBETRAG IN KONTOWÄHRUNG": _csv_number(gross * signed),
               "GEBÜHREN IN KONTOWÄHRUNG": rng.choice((_csv_number(fee), _csv_number(-fee))) if fee or rng.random() < 0.7 else "",
               "STEUERN IN KONTOWÄHRUNG": _csv_number(-taxes) if taxes else rng.choice(("0", "")), "ZINSEN IN KONTOWÄHRUNG": "0",
               "GESAMTBETRAG IN KONTOWÄHRUNG": _csv_number(total * signed), "BÖRSE": rng.choice(("GETTEX", "XETRA", "LS")),
               "STATUS DER TRANSAKTION": "CONFIRMED"}
        roll = rng.random()
        reason = None
        if roll < 0.06:
            row["STATUS DER TRANSAKTION"] = "CANCELLED"; reason = "order_cancelled"
            if rng.random() < 0.5:   # nie ausgefuehrt: ohne Kurs, Betrag und Zeit
                row.update({"AUSFÜHRUNGSZEITPUNKT": "", "AUSFÜHRUNGSKURS": "", "ANLAGEBETRAG IN KONTOWÄHRUNG": "", "GESAMTBETRAG IN KONTOWÄHRUNG": ""})
        elif roll < 0.12:
            row["STATUS DER TRANSAKTION"] = "PRECONFIRMED"; reason = "preconfirmed"
        elif roll < 0.16:
            row["TRANSAKTIONSTYP"] = rng.choice(("TRANSFER_IN", "TRANSFER_OUT", "CORPORATE_ACTION")); reason = "unknown_document"
        elif roll < 0.21:
            row[rng.choice(("HANDELSWÄHRUNG", "KONTOWÄHRUNG"))] = rng.choice(FOREIGN); reason = "not_eur"
        elif roll < 0.29:                        # Pflichtangaben fehlen oder sind nicht lesbar
            field = rng.choice(("ISIN", "STÜCKE", "STÜCKE_0", "AUSFÜHRUNGSZEITPUNKT", "ANLAGEBETRAG IN KONTOWÄHRUNG", "AUSFÜHRUNGSKURS_0"))
            row.update({"ISIN": {"ISIN": ""}, "STÜCKE": {"STÜCKE": ""}, "STÜCKE_0": {"STÜCKE": "0"}, "AUSFÜHRUNGSZEITPUNKT": {"AUSFÜHRUNGSZEITPUNKT": "unbekannt"},
                        "ANLAGEBETRAG IN KONTOWÄHRUNG": {"ANLAGEBETRAG IN KONTOWÄHRUNG": ""}, "AUSFÜHRUNGSKURS_0": {"AUSFÜHRUNGSKURS": "0"}}[field])
            reason = "incomplete"
        rows.append(row)
        if reason:
            reasons[reason] = reasons.get(reason, 0) + 1; continue
        if whole and price == price.quantize(CENT) and rng.random() < 0.15:
            row["AUSFÜHRUNGSKURS"] = ""         # ohne Kurs: Betrag / Stuecke (hier genau)
        if rng.random() < 0.08:
            row["GESAMTBETRAG IN KONTOWÄHRUNG"] = ""
        if rng.random() < 0.05:
            row["NAME 1"] = ""
        candidates.append(_candidate("buy" if side == "BUY" else "sell", "smartbroker", isin=isin, security_name=row["NAME 1"] or None,
                                     local_date=day.isoformat(), local_time=_clock(moment), quantity=_plain(quantity), unit_price=_plain(price),
                                     gross_amount=_plain(gross), fee_amount=_plain(fee), taxes_amount=_plain(taxes) if taxes else None,
                                     net_amount=_plain(total) if row["GESAMTBETRAG IN KONTOWÄHRUNG"] else None, depot_ref=depot))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=SB_HEADER, lineterminator=rng.choice(("\n", "\r\n")))
    writer.writeheader(); writer.writerows(rows)
    text = ("﻿" if rng.random() < 0.3 else "") + out.getvalue()
    return "csv", text, {"status": "multi", "candidates": candidates, "row_reasons": reasons}


# ---------------------------------------------------------------- Wertpapiere: Abrechnungen der Baader Bank fuer Smartbroker
def _dividend(rng: random.Random, variant: str = "ok", foreign: bool = False) -> tuple[list[str], dict[str, Any]]:
    """Dividendenabrechnung oder Ausschuettung; Brutto in EUR oder Fremdwaehrung (EUR-Wert ueber den Umrechnungskurs des Belegs),
    Quellensteuer, Gutschrift auf dem EUR-Konto oder dem Fremdwaehrungskonto (dann ohne EUR-Netto). Mit `foreign` (#550) immer mit
    Gutschrift in Fremdwaehrung und mit dem Ergebnis des Devisen-Lesers: der Zufluss auf das Fremdwaehrungskonto. Ohne `foreign` zieht
    der Erzeuger dieselben Zufallszahlen wie bis 1.1.0."""
    depot, reference = _depot(rng), str(rng.randrange(10**8, 10**9))
    pay = _business_day(rng, date(2021, 2, 1), 1420)
    ex = pay - timedelta(days=rng.randrange(3, 30))
    currency = rng.choice(FOREIGN) if foreign else rng.choice(("EUR",) + FOREIGN)
    credit_foreign = True if foreign else currency != "EUR" and rng.random() < 0.6
    quantity = Decimal(rng.randrange(1, 500)) if rng.random() < 0.8 else Decimal(rng.randrange(500, 50_000)).scaleb(-3)
    per_unit = Decimal(rng.randrange(5, 400)).scaleb(-2)
    rate = Decimal(rng.randrange(8_000_000, 15_000_000)).scaleb(-7)
    gross_fx = (quantity * per_unit).quantize(CENT, ROUND_HALF_UP)
    to_eur = lambda value: (value / (rate if currency != "EUR" else 1)).quantize(CENT, ROUND_HALF_UP)
    withholding_fx = (gross_fx * Decimal("0.15")).quantize(CENT, ROUND_HALF_UP) if rng.random() < (0.8 if currency != "EUR" else 0.15) else None
    withholding_eur = to_eur(withholding_fx) if withholding_fx is not None else Decimal("0")
    kest = ((to_eur(gross_fx) - withholding_eur) * rng.choice((Decimal("0"), Decimal("0.1")))).quantize(CENT, ROUND_HALF_UP)
    credit_currency = currency if credit_foreign else "EUR"
    credit = gross_fx - (withholding_fx or 0) if credit_foreign else to_eur(gross_fx) - withholding_eur - kest
    isin, name = _isin(rng), rng.choice(NAMES)
    with_ex = rng.random() < 0.9
    # Mit Gutschrift in Fremdwaehrung immer „Dividendenabrechnung“: An diesem Titel erkennt der Devisen-Leser die Dividende (#550).
    title = "Dividendenabrechnung" if foreign else rng.choice(("Dividendenabrechnung", "Dividendenabrechnung", "Ausschüttung"))
    lines = _head(depot, reference) + [title]
    if with_ex:
        lines.append(f"Ex-Tag: {_day(ex)}")
    lines += [f"Nominale                                   ISIN: {isin}     WKN: 000000                                Ausschüttung",
              f"STK {_german(quantity)}                                      {name}                                         {currency} {_german(per_unit)} p.STK"]
    if variant != "incomplete":
        lines.append(f"Zahltag:                                   {_day(pay)}")
    if currency != "EUR":
        lines.append(f"Umrechnungskurs:                           EUR/{currency} {_german(rate)}")
    lines.append(f"Bruttobetrag{_pad(97)}{currency}                                 {_german(gross_fx)}")
    if withholding_fx is not None:
        prefix = {"USD": "US-", "CHF": "CH-", "CAD": "CA-", "DKK": "DK-"}.get(currency, "")
        lines.append(f"{prefix}Quellensteuer{_pad(96 - len(prefix))}{currency}                                 {_german(withholding_fx)} -")
    if kest:
        lines.append(f"Kapitalertragsteuer{_pad(90)}EUR                                 {_german(kest)} -")
    lines.append(f"Zu Gunsten Konto {rng.randrange(10**9, 10**10)}{_pad(49)}Valuta: {_day(pay)}               {credit_currency}                                 {_german(credit)}")
    if variant == "incomplete":
        return lines, _reason("incomplete", depot_ref=depot)
    if foreign:
        eur = (credit / rate).quantize(CENT, ROUND_HALF_UP)
        return lines, _candidate("deposit", "smartbroker_fx", currency=currency, isin=isin, security_name=f"{currency} · Zufluss aus Dividende",
                                 local_date=pay.isoformat(), valuta=pay.isoformat(), quantity=_plain(credit),
                                 unit_price=_plain((eur / credit).quantize(FX_PRICE, ROUND_HALF_UP)), gross_amount=_plain(eur),
                                 depot_ref=currency, order_ref=reference)
    return lines, _candidate("dividend", "smartbroker", isin=isin, security_name=name, local_date=pay.isoformat(), eligible_quantity=_plain(quantity),
                             gross_amount=_plain(to_eur(gross_fx)), ex_date=ex.isoformat() if with_ex else None,
                             withholding_amount=_plain(withholding_eur) if withholding_fx is not None else None,
                             net_amount=_plain(credit) if credit_currency == "EUR" else None, order_ref=reference, depot_ref=depot)


def _trade(rng: random.Random, variant: str = "ok") -> tuple[list[str], dict[str, Any]]:
    """Kauf oder Verkauf mit 0 bis 3 Ausfuehrungen (Teilausfuehrungen); Datum und Zeit nennt die erste, ohne Details gilt der
    Auftragstag. Gebuehren stehen einzeln, beim Verkauf mit nachgestelltem Minus."""
    side = rng.choice(("Kauf", "Verkauf"))
    day = _business_day(rng)
    ordered = day - timedelta(days=rng.choice((0, 0, 0, 1, 3)))
    depot, reference = _depot(rng, 0.95), str(rng.randrange(10**8, 10**9))
    whole = rng.random() < 0.8
    quantity = Decimal(rng.randrange(1, 400)) if whole else Decimal(rng.randrange(5000, 500_000)).scaleb(-3)
    price = _price(rng)
    isin, name = _isin(rng), rng.choice(NAMES)
    gross = (quantity * price).quantize(CENT, ROUND_HALF_UP)
    venue = rng.choice(("GETTEX - MM Munich", "XETRA", "Tradegate"))
    fees: list[tuple[str, Decimal]] = []
    if rng.random() < 0.5:
        fees.append(("Provision", rng.choice((Decimal("4.00"), Decimal("0.00"), _money(rng, 1, 1000)))))
    for label in ("Börsenentgelt", "Fremde Spesen", "Transaktionsentgelt", "Ordergebühr"):
        if rng.random() < 0.12:
            fees.append((label, _money(rng, 1, 600)))
    taxes = (gross * Decimal(rng.randrange(1, 300)) / 10_000).quantize(CENT, ROUND_HALF_UP) if side == "Verkauf" and rng.random() < 0.3 else Decimal("0.00")
    if side == "Verkauf" and sum((value for _label, value in fees), taxes) >= gross:
        fees = []                                # kleiner Verkauf: keine Gebuehr, die den Erloes uebersteigt
    fee = sum((value for _label, value in fees), Decimal("0.00"))
    net = gross + fee if side == "Kauf" else gross - fee - taxes
    currency = rng.choice(FOREIGN) if variant == "not_eur" else "EUR"
    executions: list[tuple[Decimal, str]] = []
    if variant != "no_details":
        parts = rng.randrange(1, 4) if whole and quantity >= 3 else 1
        bounds = [0] + (sorted(rng.sample(range(1, int(quantity)), parts - 1)) if parts > 1 else []) + [quantity]
        start = rng.randrange(8 * 3600, 20 * 3600)
        for index in range(parts):
            executions.append((Decimal(bounds[index + 1]) - Decimal(bounds[index]), _clock(start + index * rng.randrange(1, 90))))
    lines = _head(depot, reference) + [f"Wertpapierabrechnung: {side}",
             f"Auftragsdatum: {_day(ordered)}                        Ausführungsplatz: {venue}",
             f"Nominale                                         ISIN: {isin}                     WKN: 000000                          Kurs",
             f"STK {_german(quantity)}                                            {name}{_pad(40)}{currency}                            {_german(price)}",
             f"Kurswert{_pad(117)}EUR                           {_german(gross)}"]
    for label, value in fees:
        lines.append(f"{label}{_pad(125 - len(label))}EUR                           {_german(value)}{' -' if side == 'Verkauf' else ''}")
    if taxes:
        lines.append(f"Kapitalertragsteuer{_pad(106)}EUR                           {_german(taxes)} -")
    with_net = rng.random() < 0.95
    if with_net:
        lines.append(f"Zu {'Lasten' if side == 'Kauf' else 'Gunsten'} Konto {rng.randrange(10**9, 10**10)}{_pad(59)}Valuta: {_day(day + timedelta(days=2))}"
                     f"                      EUR                           {_german(net)}")
    if executions:
        lines.append("Details zur Ausführung:" + _pad(103) + "Handels-                  Handels-")
        for part, clock in executions:
            lines.append(f"STK {_german(part)}                                {currency}                   {_german(price)}           {venue}{_pad(32)}"
                         f"{_day(day)}                {clock}:{rng.randrange(1000):03d}")
    if variant == "not_eur":
        return lines, _reason("not_eur", depot_ref=depot)
    local_date, local_time = (day, executions[0][1]) if executions else (ordered, None)
    return lines, _candidate("buy" if side == "Kauf" else "sell", "smartbroker", isin=isin, security_name=name, local_date=local_date.isoformat(),
                             local_time=local_time, quantity=_plain(quantity), unit_price=_plain(price), gross_amount=_plain(gross),
                             fee_amount=_plain(fee), net_amount=_plain(net) if with_net else None, order_ref=reference, depot_ref=depot,
                             fee_on_cash_statement=fee == 0)


def _fx_trade_reason(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    """Ein Devisenbeleg liest der Devisen-Leser; der Wertpapier-Leser nennt den Grund."""
    lines, _expected = _fx_receipt(rng)
    depot = _depot(rng, 0.4)
    if depot:
        lines.insert(1, f"{_pad(97)}Depot-Nr.: {depot}")
    return lines, _reason("fx_trade", depot_ref=depot)


def _tax(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    lines = _head(_depot(rng), str(rng.randrange(10**8, 10**9))) + [
        f"{rng.choice(('Jahressteuerbescheinigung', 'Verlustbescheinigung', 'Erträgnisaufstellung'))} {rng.randrange(2021, 2024)}",
        "für Privatkonten und/oder -depots", f"Höhe der Kapitalerträge    EUR    {_german(_money(rng, 1, 500_000))}"]
    return lines, _reason("tax_document")


def _information(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    lines = _head(_depot(rng), str(rng.randrange(10**8, 10**9))) + [
        f"{rng.choice(('Depotauszug', 'Ex-post-Kosteninformation', 'Quartalsaufstellung'))} per {_day(date(rng.randrange(2021, 2025), 12, 31))}"]
    for _ in range(rng.randrange(1, 5)):
        lines.append(f"STK {rng.randrange(1, 300)}    {rng.choice(NAMES)}    EUR    {_german(_money(rng, 100, 1_000_000))}")
    return lines, _reason("information")


def _custody(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    depot = _depot(rng, 0.9)
    lines = _head(depot, str(rng.randrange(10**8, 10**9))) + [rng.choice(("Depoteinlieferung", "Depotauslieferung", "Kapitalmaßnahme: Split")),
             f"Nominale     ISIN: {_isin(rng)}", f"STK {rng.randrange(1, 300)}      {rng.choice(NAMES)}"]
    return lines, _reason("custody_change", depot_ref=depot)


def _unknown(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    depot = _depot(rng, 0.9)
    lines = _head(depot, str(rng.randrange(10**8, 10**9))) + ["Wertpapierabrechnung: Rückzahlung",
             f"Nominale       ISIN: {_isin(rng)}       Kurs", f"STK {rng.randrange(1, 100)}       {rng.choice(NAMES)}       EUR       100,00"]
    return lines, _reason("unknown_document", depot_ref=depot)


SECURITIES: tuple[tuple[str, int, Callable[[random.Random], tuple[list[str], dict[str, Any]]]], ...] = (
    ("dividend", 17, _dividend),
    ("dividend_incomplete", 3, lambda rng: _dividend(rng, "incomplete")),
    ("trade", 11, _trade),
    ("trade_no_details", 2, lambda rng: _trade(rng, "no_details")),
    ("trade_not_eur", 3, lambda rng: _trade(rng, "not_eur")),
    ("fx_trade", 6, _fx_trade_reason),
    ("tax", 4, _tax),
    ("information", 4, _information),
    ("custody", 4, _custody),
    ("unknown", 4, _unknown),
)


def _securities(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    if rng.random() < 0.42:
        _kind, text, expected = _export(rng)
        return {"file_name": f"smartbroker-export-erfunden-{seed}.csv", "content": text, "expected": expected}
    name, _weight, build = rng.choices(SECURITIES, weights=[weight for _name, weight, _build in SECURITIES])[0]
    lines, expected = build(rng)
    return {"file_name": f"smartbroker-{name.replace('_', '-')}-erfunden-{seed}.txt", "content": "\n".join(lines) + "\n", "expected": expected}


# ---------------------------------------------------------------- Devisen: Perioden-Kontoauszuege und Devisenbelege
def _fx_receipt(rng: random.Random, variant: str = "ok") -> tuple[list[str], dict[str, Any]]:
    """Devisenbeleg: "Ihr Kauf/Verkauf von USD a, Gegenwert EUR b" kauft/verkauft a USD; "Ihr Verkauf/Kauf von EUR b, Gegenwert CHF a"
    kauft/verkauft a CHF. Kurs = EUR-Gegenwert / Fremdwaehrungsbetrag, Datum = Abschlussdatum."""
    currency = rng.choice(FOREIGN)
    buy = rng.random() < 0.5
    amount = _money(rng, 100, 2_000_000)
    eur = (amount * Decimal(rng.randrange(6000, 14_000)) / 10_000).quantize(CENT, ROUND_HALF_UP)
    trade = _business_day(rng, days=1435)
    valuta = trade + timedelta(days=2)
    reference = f"D1{rng.randrange(10**7, 10**8)}"
    if rng.random() < 0.5:                       # Waehrung vorn
        side, first, first_amount, against, against_amount = ("Kauf" if buy else "Verkauf"), currency, amount, "EUR", eur
    else:                                        # EUR vorn: EUR verkauft heisst Waehrung gekauft
        side, first, first_amount, against, against_amount = ("Verkauf" if buy else "Kauf"), "EUR", eur, currency, amount
    lines = _head(None, reference) + ["Devisengeschäft", f"Ihr {side}", f"Abschlussdatum{_pad(51)}{_day(trade)}",
             f"Ihr {side} von{_pad(50)}{first} {_german(first_amount)}", f"Gegenwert{_pad(56)}{against} {_german(against_amount)}",
             f"Kurs{_pad(61)}{_german((amount / eur).quantize(Decimal('0.0001'), ROUND_HALF_UP))}"]
    if variant != "incomplete":
        lines.append(f"Valuta{_pad(59)}{_day(valuta)}")
    lines += ["Bemerkungen:", f"IHR DEVISEN{side.upper()} {first}{against}"]
    if variant == "incomplete":
        return lines, _reason("incomplete")
    return lines, _candidate("buy" if buy else "sell", "smartbroker_fx", currency=currency,
                             security_name=f"{currency} · Devisen" + ("kauf" if buy else "verkauf"), local_date=trade.isoformat(),
                             valuta=valuta.isoformat(), quantity=_plain(amount), unit_price=_plain((eur / amount).quantize(FX_PRICE, ROUND_HALF_UP)),
                             gross_amount=_plain(eur), order_ref=reference, depot_ref=currency)


def _fx_statement(rng: random.Random, variant: str = "ok") -> tuple[list[str], dict[str, Any]]:
    """Perioden-Kontoauszug eines Fremdwaehrungskontos. Je Zeile Buchungstag, Vorgang, Valuta, Betrag (Belastung mit nachgestelltem
    Minus) und eine Folgezeile; "Coupons" belegt einen Zufluss aus Dividende, sonst Kauf (Gutschrift) oder Verkauf (Belastung)."""
    currency = "EUR" if variant == "eur" else rng.choice(FOREIGN)
    month_index = rng.randrange(1, 48)            # Februar 2021 bis Dezember 2024
    year, month = 2021 + month_index // 12, month_index % 12 + 1
    start_day, end_day = date(year, month, 1) - timedelta(days=1), date(year, month, calendar.monthrange(year, month)[1])
    opening = variant == "opening"                # erster Auszug nach der Kontoeroeffnung: Anfangssaldo ohne Datum
    balance = Decimal("0.00") if opening else _money(rng, 0, 500_000) if rng.random() < 0.8 else Decimal("0.00")
    start = balance
    entries: list[tuple[date, date, str, Decimal, str]] = []
    if variant not in ("quiet", "quiet_two"):
        for booked in sorted(start_day + timedelta(days=rng.randrange(1, end_day.day + 1)) for _ in range(rng.randrange(1, 9))):
            roll = rng.random()
            if roll < 0.45 or (roll >= 0.75 and balance <= 0):
                label, amount, detail = "Coupons/Dividende", _money(rng, 1, 50_000), f"STK {rng.randrange(1, 500)} ISIN {_isin(rng)}"
                valued = booked - timedelta(days=rng.randrange(0, 3))
            elif roll < 0.75:
                label, amount, detail = "Devisenkassageschäft", _money(rng, 100, 1_000_000), f"Vorgangs-Nr.: D1{rng.randrange(10**7, 10**8)}"
                valued = booked
            else:
                share = Decimal(1) if rng.random() < 0.3 else Decimal(rng.randrange(1, 100)) / 100
                label, amount, detail = "Devisenkassageschäft", -(balance * share).quantize(CENT, ROUND_HALF_UP), f"Vorgangs-Nr.: D1{rng.randrange(10**7, 10**8)}"
                valued = booked
                if amount == 0:
                    continue
            entries.append((booked, valued, label, amount, detail))
            balance += amount
    lines = _head(None, "000") + [f"{_pad(35)}Perioden-Kontoauszug: {currency}-Konto", f"Periodenauszugs-Nr. {month}",
             f"Buchungstag   Vorgang                                Valuta          Betrag in {currency}", ""]
    single = variant == "quiet" or (variant != "quiet_two" and not entries)   # ohne Bewegung: ein Saldo
    if not single:
        lines.append(f"Kontostand in {currency} am {'' if opening else _day(start_day) + ' '}{_pad(60)}{_german(start)}")
    expected_lines = []
    for booked, valued, label, amount, detail in entries:
        lines += [f"{_day(booked)}               {label}{_pad(52)}{_day(valued)}               {_german(abs(amount))}{' -' if amount < 0 else ''}",
                  f"{_pad(25)}{detail}", ""]
        kinds = ["deposit"] if label.startswith("Coupons") else (["buy"] if amount > 0 else ["sell"])
        expected_lines.append({"booked": booked.isoformat(), "valuta": valued.isoformat(), "text": label, "amount": amount, "kinds": kinds})
    if variant != "no_end":
        lines.append(f"Kontostand in {currency} am {_day(end_day)}{_pad(60)}{_german(balance)}")
    if currency == "EUR":
        return lines, _reason("cash_movement")
    if variant == "no_end":                      # Auszug ohne Endsaldo (Seite fehlt): kein Saldo-Anker
        return lines, _reason("incomplete")
    if single:
        anchor = [end_day.isoformat(), balance]
        return lines, {"status": "statement", "currency": currency, "lines": [], "start": anchor, "end": anchor}
    return lines, {"status": "statement", "currency": currency, "lines": expected_lines,
                   "start": [None if opening else start_day.isoformat(), start], "end": [end_day.isoformat(), balance]}


FX: tuple[tuple[str, int, Callable[[random.Random], tuple[list[str], dict[str, Any]]]], ...] = (
    ("statement", 34, _fx_statement),
    ("statement_quiet", 8, lambda rng: _fx_statement(rng, "quiet")),
    ("statement_quiet_two", 4, lambda rng: _fx_statement(rng, "quiet_two")),
    ("statement_opening", 7, lambda rng: _fx_statement(rng, "opening")),
    ("statement_eur", 4, lambda rng: _fx_statement(rng, "eur")),
    ("statement_no_end", 3, lambda rng: _fx_statement(rng, "no_end")),
    ("receipt", 36, _fx_receipt),
    ("receipt_incomplete", 4, lambda rng: _fx_receipt(rng, "incomplete")),
    ("dividend", 12, lambda rng: _dividend(rng, foreign=True)),
)


def _fx(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    name, _weight, build = rng.choices(FX, weights=[weight for _name, weight, _build in FX])[0]
    lines, expected = build(rng)
    return {"file_name": f"smartbroker-devisen-{name.replace('_', '-')}-erfunden-{seed}.txt", "content": "\n".join(lines) + "\n",
            "expected": expected}


GENERATORS = {
    "smartbroker_plus_v1": _securities,
    "smartbroker_plus_fx_v1": _fx,
}
