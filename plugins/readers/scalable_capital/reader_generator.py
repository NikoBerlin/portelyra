"""Erzeuger erfundener Scalable-Belege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Wie die Referenz (c24): Aus einem Startwert entstehen erfundene Vorgaenge; aus ihnen baut der Erzeuger den Beleg im Format des
Instituts und - unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der Leser nur
sich selbst. Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Namen, IBAN, Depot- und Ordernummern, ISIN, Betraege, Tage.

Abgedeckt:
- Monatsauszug Tagesgeld und Verrechnungskonto (Text, wie ihn der Kern aus dem PDF erzeugt): Zinsen, auch mit Wertstellung am Vortag
  (Zins des Quartals am 01.01. auf den 31.12.), Storno einer Zinsgutschrift, Ein- und Auszahlungen, Wertpapier-, Gebuehren- und
  Steuerbuchungen, Steuererstattung, Zeilen ohne Betrag, Seitenumbruch, Konto im Monat eroeffnet, Monat ohne Bewegung; Anfangsstand
  der alten Vorlage (Stand nach dem ersten Tag) und der neuen (Stand davor) und ein Auszug, der nicht aufgeht.
- Wertpapierbelege (PDF-Text): Kauf und Verkauf der Scalable Capital GmbH und Bank mit Ordergebuehr, Finanztransaktionssteuer,
  Fremdkostenzuschlag, Steuern und Gewinn; Dividende und Ausschuettung in EUR und Fremdwaehrung mit Quellensteuer; Vorabpauschale in
  drei Vorlagen fuer das Jahr, mit und ohne Kontobewegung, Rundung um einen Cent und drei Widersprueche; Abrechnungen der Baader Bank
  fuer Scalable (Kauf, Verkauf, Teilausfuehrungen, ohne Ausfuehrungsdetails, Dividende in Fremdwaehrung). Gruende: Fremdwaehrung,
  Sammelabrechnung, Pflichtangaben fehlen, Bestandsveraenderung, Steuerunterlage, Information, unbekannte Belegart, anderes Institut.

Die Tage liegen in der Vergangenheit (2021-2024), damit der Beleg auch die Regel "kein Buchungstag nach heute" erfuellt, wenn der
Selbsttest vor einer Installation mit dem Datum des Rechners laeuft.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Any, Callable

CENT = Decimal("0.01")
SCALABLE = (("Scalable Capital GmbH", "scalable_capital"), ("Scalable Capital Bank GmbH", "scalable_bank"))
ADDRESS = " • Seitzstraße 8e • 80538 München • Deutschland"
BAADER = "Baader Bank AG Weihenstephaner Straße 4 85716 Unterschleißheim"
CUSTOMERS = ("Erika Musterfrau", "Max Mustermann", "Paula Beispiel", "Jonas Erfunden", "Lea Fantasie")
STREETS = ("Musterweg 1", "Beispielstraße 23", "Erfundene Allee 7", "Am Testhang 12")
NAMES = ("Invented Equity Fund (Acc)", "Erfundene Industrie AG", "Beispiel Technologie Inc.", "Muster Welt ETF", "Fantasia Energy Corp.",
         "Testland Versorger SE", "Imaginary Pharma plc", "Phantasie Global Small Cap ETF (Dist)")
FUNDS = ("Muster Welt ETF Acc", "Invented Fund Acc", "Erfundener Schwellenländer ETF", "Beispiel Anleihen ETF Dist")
COUNTRIES = ("US", "DE", "IE", "LU", "FR", "NL")
FOREIGN = ("USD", "USD", "CHF", "GBP", "DKK", "CAD")


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


def _time(rng: random.Random) -> str:
    return f"{rng.randrange(8, 22):02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}"


def _isin(rng: random.Random) -> str:
    return f"{rng.choice(COUNTRIES)}0000{rng.randrange(10**5):05d}{rng.randrange(10)}"


def _quantity(rng: random.Random, whole_only: bool = False) -> Decimal:
    """Stueckzahl: ganz (mit zwei Nullen gedruckt, wie Scalable) oder ein Bruchteil aus einem Sparplan."""
    if whole_only or rng.random() < 0.6:
        return Decimal(rng.randrange(1, 301)).quantize(CENT)
    return Decimal(rng.randrange(500, 100_000)).scaleb(-3)


def _price(rng: random.Random) -> Decimal:
    if rng.random() < 0.7:
        return Decimal(rng.randrange(1000, 500_000)).scaleb(-2)
    return Decimal(rng.randrange(100_000, 5_000_000)).scaleb(-4)


def _iban(rng: random.Random) -> str:
    return f"DE{rng.randrange(10, 100)}0000{rng.randrange(10**13, 10**14)}"


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


# ---------------------------------------------------------------- Monatsauszug Tagesgeld und Verrechnungskonto (cash)
INTEREST_TEXTS = ("Erhaltene Zinsen", "Zinsgutschrift")
SAVINGS_TEXTS = (("Überweisung", 1), ("Einzahlung", 1), ("Gutschrift Erika Musterfrau", 1), ("Auszahlung", -1),
                 ("Überweisung auf Referenzkonto", -1), ("Steuern auf Zinsen", -1))
BROKER_TEXTS = SAVINGS_TEXTS + (("Kauf {name}", -1), ("Verkauf {name}", 1), ("Ausschüttung {name}", 1), ("Sparplan {name}", -1),
                                ("Ordergebühr", -1), ("Steuern", -1), ("Steuererstattung", 1))


def _cash_statement(seed: int, broker: bool) -> dict[str, Any]:
    rng = random.Random(seed)
    year, month = rng.randrange(2021, 2025), rng.randrange(1, 13)
    period_from, period_to = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    if rng.random() < 0.1:   # Konto im Monat eroeffnet: der Zeitraum beginnt spaeter
        period_from += timedelta(days=rng.randrange(1, 15))
    # Vorlage: "new" nennt am Periodenbeginn den Stand davor (seit Oktober 2026), "old" den Stand nach dem ersten Tag (bis September
    # 2026); "broken" geht nicht auf; "quiet" ist ein Monat ohne Bewegung.
    scenario = rng.choices(("new", "old", "quiet", "broken"), weights=(40, 40, 12, 8))[0]
    opening = _money(rng, 0, 3_000_000)
    balance = opening
    rows: list[tuple[date, date, str, Decimal, str | None]] = []   # Buchung, Wertstellung, Text, Betrag mit Vorzeichen, Art
    if scenario != "quiet":
        span = (period_to - period_from).days
        days = sorted(period_from + timedelta(days=rng.randrange(span + 1)) for _ in range(rng.randrange(1, 16)))
        if rng.random() < 0.5:
            days[0] = period_from
        names = NAMES if broker else ("",)
        for booked in days:
            roll = rng.random()
            valued = booked
            if roll < 0.04:                      # Zeile ohne Betrag: wird gezaehlt, bucht aber nichts
                rows.append((booked, valued, rng.choice(INTEREST_TEXTS), Decimal("0.00"), None)); continue
            if roll < 0.30:                      # Zinsen, oft am Monatsersten auf den letzten Tag davor wertgestellt
                if rng.random() < 0.5:
                    valued = booked - timedelta(days=1)
                amount = _money(rng, 1, 15_000)
                rows.append((booked, valued, rng.choice(INTEREST_TEXTS), amount, "interest")); balance += amount; continue
            text, sign = rng.choice(BROKER_TEXTS if broker else SAVINGS_TEXTS)
            if roll < 0.33:                      # Storno einer Zinsgutschrift: negativ, also kein Ertrag
                text, sign = "Storno Zinsgutschrift", -1
            text = text.format(name=rng.choice(names))
            amount = _money(rng, 1, 2_000_000)
            if sign < 0:                         # Abbuchungen nur aus dem Guthaben: ein Teil davon, selten alles
                amount = balance if rng.random() < 0.05 else (balance * rng.randrange(1, 60) / 100).quantize(CENT, ROUND_HALF_UP)
                if amount <= 0:                  # nichts mehr auf dem Konto: eine Einzahlung statt der Abbuchung
                    text, sign, amount = "Einzahlung", 1, _money(rng, 100, 500_000)
            if rng.random() < 0.2:
                valued = booked + timedelta(days=1)
            rows.append((booked, valued, text, amount * sign, "deposit" if sign > 0 else "withdrawal"))
            balance += amount * sign
        if all(kind is None for *_rest, kind in rows):
            amount = _money(rng, 1, 15_000)
            rows.append((period_to, period_to, "Erhaltene Zinsen", amount, "interest")); balance += amount
    first_day = sum((amount for booked, _valued, _text, amount, _kind in rows if booked == period_from), Decimal("0.00"))
    closing = balance
    printed_opening = opening + first_day if scenario == "old" else opening
    printed_closing = closing + _money(rng, 1, 50_000) if scenario == "broken" else closing
    # Geht der Auszug so nicht auf, liest der Leser die alte Vorlage und zieht den ersten Tag ab.
    expected_opening = opening - first_day if scenario == "broken" else opening

    bank = "Scalable Capital Bank GmbH" + (ADDRESS if rng.random() < 0.5 else "")
    head = [bank, "", "Kontoauszug", f"Zeitraum {_day(period_from)} - {_day(period_to)}"]
    columns = ["Buchung            Wertstellung          Beschreibung                       Betrag", ""]
    iban = _iban(rng)
    lines = head + ["", f"Auszug Nr.                               {month}",
                    f"{'Verrechnungskonto' if broker else 'Tagesgeldkonto'}                        {iban[:4]} {iban[4:8]} (TESTDEFFXXX)",
                    f"Kontostand am {_day(period_from)}            {_german(printed_opening)} EUR",
                    f"Kontostand am {_day(period_to)}            {_german(printed_closing)} EUR", ""] + columns
    if scenario == "quiet":
        lines += ["Keine Kontobewegungen in diesem Zeitraum.", ""]
    candidates: list[dict[str, Any]] = []
    for ordinal, (booked, valued, text, amount, kind) in enumerate(rows, 1):
        if ordinal == 9:                         # Seitenumbruch: Kopf und Spalten wiederholt
            lines += head + ["Seite 2", ""] + columns
        lines += [f"{_day(booked)}        {_day(valued)}            {text}            {'-' if amount < 0 else '+'}{_german(abs(amount))} EUR", ""]
        if kind is None:
            continue
        candidate = {"source_row_ordinal": ordinal, "local_date": booked.isoformat(), "kind": kind, "amount_decimal": _plain(abs(amount)),
                     "balance_after_decimal": None, "text": text}
        if kind == "interest" and valued != booked:   # der Ertrag folgt der Wertstellung, der Geldfluss bleibt am Buchungstag
            candidate["value_date"] = valued.isoformat()
        candidates.append(candidate)
    if not broker or rng.random() < 0.5:
        lines += head + ["", "Verteilung Ihrer Einlagen", f"Erfundener Geldmarktfonds (dist.)        {_german(printed_closing)} EUR",
                         f"                              Kontostand        {_german(printed_closing)} EUR"]
    expected = {"candidates": candidates, "diagnostics": [],
                "summary": {"opening_balance_decimal": _plain(expected_opening), "closing_balance_decimal": _plain(printed_closing),
                            "period_from": period_from.isoformat(), "period_to": period_to.isoformat(),
                            "closing_as_of_date": period_to.isoformat()}}
    name = "verrechnung" if broker else "tagesgeld"
    return {"file_name": f"scalable-{name}-erfunden-{seed}.txt", "content": ("\n".join(lines) + "\n").encode("utf-8"), "expected": expected}


# ---------------------------------------------------------------- Wertpapierbelege der Scalable Capital GmbH und Bank
def _scalable_head(rng: random.Random, issuer: str, day: date) -> list[str]:
    return [issuer + ADDRESS, rng.choice(CUSTOMERS), f"{rng.choice(STREETS)}{_pad(70)}Datum     {_day(day)}"]


def _scalable_trade(rng: random.Random, variant: str = "ok") -> tuple[list[str], dict[str, Any]]:
    """Kauf oder Verkauf; Varianten: Kurs in Fremdwaehrung, ohne Ausfuehrungszeile, Sammelabrechnung mit zwei Papieren."""
    issuer, profile = rng.choice(SCALABLE)
    side = rng.choice(("Kauf", "Verkauf"))
    day, clock = _business_day(rng), _time(rng)
    depot = str(rng.randrange(10**9, 10**10))
    order = "SCAL" + "".join(rng.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(rng.randrange(6, 11)))
    positions: list[tuple[str, str, Decimal, Decimal, Decimal]] = []
    while len(positions) < (2 if variant == "overview" else 1):
        isin, quantity, price = _isin(rng), _quantity(rng), _price(rng)
        if all(isin != item[0] for item in positions):   # eine Sammelabrechnung nennt verschiedene Papiere
            positions.append((isin, rng.choice(NAMES), quantity, price, (quantity * price).quantize(CENT, ROUND_HALF_UP)))
    lines = _scalable_head(rng, issuer, day) + ["Wertpapierabrechnung", "für Kundenauftrag",
             f"Typ                         {rng.choice(('LIMIT', 'MARKET', 'SPARPLAN'))}                                    Order               {order}"]
    if variant != "incomplete":
        lines.append(f"Ausführung                  {_day(day)} {clock}                                   Geschäft            {rng.randrange(1000, 9999)}P{rng.randrange(10, 99)}XY")
    lines += [f"Ausführungsplatz            {rng.choice(('EIX', 'XETRA', 'GETTEX'))}                                      Lagerland           {rng.choice(('Deutschland', 'Luxemburg'))}",
              f"Depot                       {depot}                               Verwahrart          Wertpapierrechnung",
              "Typ       Wertpapier                                                         Anzahl              Kurs        Betrag"]
    currency = "USD" if variant == "not_eur" else "EUR"
    for isin, name, quantity, price, gross in positions:
        lines += [f"{side}      {name}                                       {_german(quantity)} Stk.        {_german(price)} {currency}    {_german(gross)} EUR",
                  f"          {isin}"]
    isin, name, quantity, price, gross = positions[0]
    fees: list[tuple[str, Decimal]] = []
    if rng.random() < 0.85:
        fees.append(("Ordergebühren", rng.choice((Decimal("0.99"), Decimal("0.99"), Decimal("0.00"), Decimal("1.99")))))
    if side == "Kauf" and rng.random() < 0.12:
        fees.append(("Finanztransaktionssteuer", (gross * Decimal("0.003")).quantize(CENT, ROUND_HALF_UP)))
    if rng.random() < 0.08:
        fees.append(("Fremdkostenzuschlag", _money(rng, 50, 200)))
    for label, value in fees:
        lines.append(f"{_pad(87 - len(label))}{label}      {'+' if side == 'Kauf' else '-'}{_german(value)} EUR")
    fee = sum((value for _label, value in fees), Decimal("0.00"))
    taxes = (gross * Decimal(rng.randrange(1, 500)) / 10_000).quantize(CENT, ROUND_HALF_UP) if side == "Verkauf" and rng.random() < 0.4 else Decimal("0.00")
    if taxes:
        lines.append(f"{_pad(93)}Steuern    -{_german(taxes)} EUR")
    total = gross + fee if side == "Kauf" else gross - fee - taxes
    label = rng.choice(("Total",) + (("Belastung",) if side == "Kauf" else ("Gutschrift",)) * 5)
    lines.append(f"{_pad(83)}{label}   {_german(total)} EUR")
    lines.append(f"Der Betrag wird mit dem Verrechnungskonto {_iban(rng)} (Valuta: {_day(day + timedelta(days=2))}) verrechnet.")
    gain = None
    if side == "Verkauf" and rng.random() < 0.8:
        gain = _money(rng, -200_000, 400_000)
        caption = "Gewinn oder Verlust" if gain < 0 or rng.random() < 0.3 else "Gewinn"
        lines += ["Wertpapierabrechnung", "Ermittlung steuerrelevanter Erträge", "Typ                                                 Betrag",
                  f"{caption}{_pad(80)}{_german(gain)} EUR"]
    if variant in ("not_eur", "incomplete", "overview"):
        return lines, _reason(variant, depot_ref=depot)
    return lines, _candidate("buy" if side == "Kauf" else "sell", profile, isin=isin, security_name=name, local_date=day.isoformat(),
                             local_time=clock, quantity=_plain(quantity), unit_price=_plain(price), gross_amount=_plain(gross),
                             fee_amount=_plain(fee), net_amount=_plain(total), order_ref=order, depot_ref=depot,
                             bank_gain=_plain(gain) if gain is not None else None)


def _scalable_dividend(rng: random.Random, variant: str = "ok") -> tuple[list[str], dict[str, Any]]:
    """Dividende oder Ausschuettung; Kontobewegung in EUR, Betrag je Stueck in EUR oder Fremdwaehrung mit Kurs."""
    issuer, profile = rng.choice(SCALABLE)
    booked = _business_day(rng, date(2021, 2, 1), 1420)
    valued = booked - timedelta(days=rng.randrange(0, 4))
    ex = booked - timedelta(days=rng.randrange(5, 30))
    currency = rng.choice(("EUR", "EUR") + FOREIGN)
    quantity = _quantity(rng)
    per_unit = Decimal(rng.randrange(5, 500)).scaleb(-2) if rng.random() < 0.8 else Decimal(rng.randrange(500, 50_000)).scaleb(-4)
    rate = Decimal(rng.randrange(8000, 15_000)).scaleb(-4)
    gross = (quantity * per_unit / (rate if currency != "EUR" else 1)).quantize(CENT, ROUND_HALF_UP)
    withholding = (gross * Decimal("0.15")).quantize(CENT, ROUND_HALF_UP) if rng.random() < (0.8 if currency != "EUR" else 0.1) else None
    taxes = ((gross - (withholding or 0)) * rng.choice((Decimal("0"), Decimal("0.26375")))).quantize(CENT, ROUND_HALF_UP)
    net = gross - (withholding or 0) - taxes
    isin, name = _isin(rng), rng.choice(NAMES)
    with_ex = rng.random() < 0.9
    lines = [issuer + ADDRESS, f"{rng.choice(CUSTOMERS)}{_pad(75)}Datum         {_day(booked)}", rng.choice(("Dividende", "Ausschüttung")),
             f"Für {_day(date(booked.year, 1, 1))} - {_day(date(booked.year, 12, 31))}", f"Berechtigtes Wertpapier             {name}",
             f"ISIN                                {isin}"]
    if variant != "incomplete":
        lines.append(f"Berechtigte Anzahl                  {_german(quantity)}")
    if with_ex:
        lines.append(f"Ex Tag                              {_day(ex)}")
    lines += [f"Verrechnungskonto                   {_iban(rng)}", "Kontobewegung",
              "Buchung         Wertstellung         Typ                                                           Betrag / Stk.       Berechtigte Anzahl           Gesamt",
              f"{_day(booked)} {_day(valued)}                Gutschrift                                                           {_german(per_unit)} {currency}                           {_german(quantity)}     {_german(gross)} EUR"]
    if currency != "EUR":
        lines.append(f"{_pad(98)}{currency} / EUR {_german(rate)}")
    if withholding is not None:
        lines.append(f"{_pad(103)}Ausländische Quellensteuer               -{_german(withholding)} EUR")
    if taxes:
        lines.append(f"{_pad(110)}Kapitalertragsteuer               -{_german(taxes)} EUR")
    lines.append(f"{_pad(120)}Gesamtbetrag             {_german(net)} EUR")
    if variant == "incomplete":
        return lines, _reason("incomplete", depot_ref=None)
    return lines, _candidate("dividend", profile, isin=isin, security_name=name, local_date=booked.isoformat(), eligible_quantity=_plain(quantity),
                             gross_amount=_plain(gross), ex_date=ex.isoformat() if with_ex else None,
                             withholding_amount=_plain(withholding) if withholding is not None else None, net_amount=_plain(net))


def _scalable_advance_lump_sum(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    """Vorabpauschale je Fonds: vorn die Kontobewegung, hinten die Ermittlung. Der Betrag muss vorn und hinten gleich sein und
    "Zu versteuern" der Betrag ohne die Teilfreistellung (auf einen Cent); sonst ein Grund statt einer Zahl."""
    issuer, profile = rng.choice(SCALABLE)
    variant = rng.choices(("ok", "rounding", "front_back", "taxable", "relevant_year", "no_movement"), weights=(50, 10, 10, 10, 6, 14))[0]
    year = rng.randrange(2021, 2024)              # angefallen; der Zufluss gilt am ersten Werktag des Folgejahres
    ex = date(year + 1, 1, rng.randrange(2, 5))
    booked = ex + timedelta(days=1)
    quantity = _quantity(rng)
    amount = _money(rng, 1, 20_000)
    free = rng.choice((30, 30, 30, 15, 0, 60))
    taxable = (amount * (100 - free) / 100).quantize(CENT, ROUND_HALF_UP)
    taxes = (taxable * Decimal("0.26375")).quantize(CENT, ROUND_HALF_UP) if rng.random() < 0.6 else Decimal("0.00")
    printed_taxable = taxable + (CENT if variant == "rounding" else _money(rng, 2, 100) if variant == "taxable" else 0)
    back = amount + _money(rng, 1, 500) if variant == "front_back" else amount
    relevant = year + 2 if variant == "relevant_year" else year + 1
    layout = "two_lines" if variant == "relevant_year" else rng.choice(("two_lines", "two_lines", "one_line", "none"))
    show_relevant = variant == "relevant_year" or rng.random() < 0.8
    movement = variant != "no_movement"
    burden = rng.random() < 0.7
    isin, fund = _isin(rng), rng.choice(FUNDS)
    lines = [issuer + ADDRESS, "", "Vorabpauschale", f"für {fund} ({isin})",
             f"Berechtigte Anzahl            {_german(quantity)}" + (f"{_pad(52)}Angefallen im" if layout == "two_lines" else "")]
    if layout == "two_lines":
        lines += [f"{_pad(84)}{year}", f"Ex-Tag                        {_day(ex)}{_pad(44)}Kalenderjahr"]
    else:
        lines.append(f"Ex-Tag                        {_day(ex)}")
    if layout == "one_line":
        lines.append(f"Angefallen im Kalenderjahr    {year}")
    if show_relevant:
        lines.append(f"{_pad(84)}Relevant für Steuerjahr    {relevant}")
    if movement:
        lines += ["Kontobewegung", "Buchung         Wertstellung          Typ                 Vorabpauschale          Steuern",
                  f"{_day(booked)} {_day(booked)}                 Steuerabbuchung     {_german(amount)} EUR             {_german(taxes)} EUR"]
    if burden:
        lines.append(f"Steuerbelastung          {_german(taxes)} EUR")
    lines += ["", "Vorabpauschale", "Ermittlung steuerrelevante Erträge",
              "Typ                                                        Anmerkung                                          Betrag",
              f"Gewinn oder Verlust{_pad(91)}{_german(back)}",
              f"Teilfreistellung                                           {free} %{_pad(47)}-{_german(amount - taxable)}",
              f"Zu versteuern    {_german(printed_taxable)} EUR",
              f"Kapitalertragsteuer{_pad(91)}{_german((taxes * 100 / Decimal('105.5')).quantize(CENT, ROUND_HALF_UP))}"]
    if variant in ("front_back", "taxable", "relevant_year"):
        return lines, _reason("advance_lump_sum_inconsistent", depot_ref=None)
    taxes_amount = _plain(taxes) if movement or burden else None
    return lines, _candidate("advance_lump_sum", profile, isin=isin, security_name=fund, local_date=ex.isoformat(), ex_date=ex.isoformat(),
                             eligible_quantity=_plain(quantity), gross_amount=_plain(amount), depot_ref=None, calculation_year=year,
                             taxes_amount=taxes_amount)


# ---------------------------------------------------------------- Abrechnungen der Baader Bank fuer Scalable
def _baader_head(rng: random.Random, right: str, depot: str | None, reference: str) -> list[str]:
    lines = [f"{BAADER}{_pad(37)}{right}".rstrip(), f"{_pad(99)}Seite 1/1", f"{_pad(99)}Stamm-Nr.: {rng.randrange(1000, 9999)} Portfolio: 1"]
    if depot:
        lines.append(f"{_pad(99)}Depot-Nr.: {depot}")
    return lines + [f"{_pad(99)}Vorgangs-Nr.: {reference}"]


def _baader_right(rng: random.Random) -> str:
    """Kopf rechts: fuer Scalable abgerechnet, oder (spaete Belege nach dem Wechsel von Scalable zur eigenen Bank) nur Baader."""
    return rng.choice(("Scalable Capital GmbH", "Scalable Capital GmbH", "Scalable Capital Bank GmbH", ""))


def _baader_trade(rng: random.Random, right: str, profile: str, variant: str = "ok") -> tuple[list[str], dict[str, Any]]:
    """Kauf oder Verkauf mit 0 bis 3 Ausfuehrungen (Teilausfuehrungen); Datum und Zeit nennt die erste, ohne Details gilt der
    Auftragstag. Gebuehren stehen einzeln, beim Verkauf mit nachgestelltem Minus."""
    side = rng.choice(("Kauf", "Verkauf"))
    day = _business_day(rng)
    ordered = day - timedelta(days=rng.choice((0, 0, 0, 1, 3)))
    depot = f"99{rng.randrange(10**7, 10**8)}" if rng.random() < 0.95 else None
    reference = str(rng.randrange(10**8, 10**9))
    whole = rng.random() < 0.8
    quantity = Decimal(rng.randrange(1, 400)) if whole else Decimal(rng.randrange(5000, 500_000)).scaleb(-3)
    price = _price(rng)
    isin, name = _isin(rng), rng.choice(NAMES)
    gross = (quantity * price).quantize(CENT, ROUND_HALF_UP)
    venue = rng.choice(("GETTEX - MM Munich", "XETRA", "Tradegate"))
    fees: list[tuple[str, Decimal]] = []
    for label in ("Provision", "Börsenentgelt", "Fremde Spesen", "Transaktionsentgelt", "Fremdkostenzuschlag"):
        if rng.random() < 0.15:
            fees.append((label, _money(rng, 1, 600)))
    taxes = (gross * Decimal(rng.randrange(1, 300)) / 10_000).quantize(CENT, ROUND_HALF_UP) if side == "Verkauf" and rng.random() < 0.3 else Decimal("0.00")
    if side == "Verkauf" and sum((value for _label, value in fees), taxes) >= gross:
        fees = []                                # kleiner Verkauf: keine Gebuehr, die den Erloes uebersteigt
    fee = sum((value for _label, value in fees), Decimal("0.00"))
    net = gross + fee if side == "Kauf" else gross - fee - taxes
    executions: list[tuple[Decimal, str]] = []
    if variant != "no_details":
        parts = rng.randrange(1, 4) if whole and quantity >= 3 else 1
        cuts = sorted(rng.sample(range(1, int(quantity)), parts - 1)) if parts > 1 else []
        bounds = [0] + cuts + [quantity]
        start = rng.randrange(8 * 3600, 20 * 3600)
        for index in range(parts):
            moment = start + index * rng.randrange(1, 90)
            executions.append((Decimal(bounds[index + 1]) - Decimal(bounds[index]), f"{moment // 3600:02d}:{moment // 60 % 60:02d}:{moment % 60:02d}"))
    currency = "USD" if variant == "not_eur" else "EUR"
    lines = _baader_head(rng, right, depot, reference) + [f"Wertpapierabrechnung: {side}",
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
    lines.append("Dieser Beleg wird maschinell erstellt und daher nicht unterschrieben.")
    if variant == "not_eur":
        return lines, _reason("not_eur", depot_ref=depot)
    local_date, local_time = (day, executions[0][1]) if executions else (ordered, None)
    return lines, _candidate("buy" if side == "Kauf" else "sell", profile, isin=isin, security_name=name, local_date=local_date.isoformat(),
                             local_time=local_time, quantity=_plain(quantity), unit_price=_plain(price), gross_amount=_plain(gross),
                             fee_amount=_plain(fee), net_amount=_plain(net) if with_net else None, order_ref=reference, depot_ref=depot,
                             fee_on_cash_statement=fee == 0)


def _baader_dividend(rng: random.Random, right: str, profile: str, credit_foreign: bool = False,
                     variant: str = "ok") -> tuple[list[str], dict[str, Any]]:
    """Dividendenabrechnung oder Ausschuettung; Brutto in EUR oder Fremdwaehrung (EUR-Wert ueber den Umrechnungskurs des Belegs),
    Quellensteuer, Gutschrift in EUR (oder in der Fremdwaehrung, dann ohne EUR-Netto)."""
    depot = f"99{rng.randrange(10**7, 10**8)}" if rng.random() < 0.7 else None
    reference = str(rng.randrange(10**8, 10**9))
    pay = _business_day(rng, date(2021, 2, 1), 1420)
    ex = pay - timedelta(days=rng.randrange(3, 30))
    currency = "USD" if credit_foreign else rng.choice(("EUR",) + FOREIGN)
    quantity = Decimal(rng.randrange(1, 500)) if rng.random() < 0.8 else Decimal(rng.randrange(500, 50_000)).scaleb(-3)
    per_unit = Decimal(rng.randrange(5, 400)).scaleb(-2)
    rate = Decimal(rng.randrange(8_000_000, 15_000_000)).scaleb(-7)
    gross_fx = (quantity * per_unit).quantize(CENT, ROUND_HALF_UP)
    to_eur = lambda value: (value / (rate if currency != "EUR" else 1)).quantize(CENT, ROUND_HALF_UP)
    withholding_fx = (gross_fx * Decimal("0.15")).quantize(CENT, ROUND_HALF_UP) if rng.random() < (0.8 if currency != "EUR" else 0.15) else None
    kest = ((to_eur(gross_fx) - (to_eur(withholding_fx) if withholding_fx is not None else 0)) * rng.choice((Decimal("0"), Decimal("0.1")))).quantize(CENT, ROUND_HALF_UP)
    credit_currency = currency if credit_foreign else "EUR"
    credit = gross_fx - (withholding_fx or 0) if credit_foreign else to_eur(gross_fx) - (to_eur(withholding_fx) if withholding_fx is not None else 0) - kest
    isin, name = _isin(rng), rng.choice(NAMES)
    with_ex = rng.random() < 0.9
    lines = [f"{BAADER}{_pad(35)}{right}".rstrip()] + ([f"{_pad(97)}Depot-Nr.: {depot}"] if depot else []) + [f"{_pad(97)}Vorgangs-Nr.: {reference}"]
    lines.append(rng.choice(("Dividendenabrechnung", "Dividendenabrechnung", "Ausschüttung")))
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
    return lines, _candidate("dividend", profile, isin=isin, security_name=name, local_date=pay.isoformat(), eligible_quantity=_plain(quantity),
                             gross_amount=_plain(to_eur(gross_fx)), ex_date=ex.isoformat() if with_ex else None,
                             withholding_amount=_plain(to_eur(withholding_fx)) if withholding_fx is not None else None,
                             net_amount=_plain(credit) if credit_currency == "EUR" else None, order_ref=reference, depot_ref=depot)


# ---------------------------------------------------------------- Belege mit Grund
def _custody(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    depot = str(rng.randrange(10**9, 10**10))
    if rng.random() < 0.5:   # Scalable: Ein-/Auslieferung, Uebertrag, Kapitalmassnahme
        issuer, _profile = rng.choice(SCALABLE)
        lines = _scalable_head(rng, issuer, _business_day(rng)) + [rng.choice(("Depoteinlieferung", "Depotauslieferung", "Depotübertrag", "Kapitalmaßnahme")),
                 f"in Depot {depot}", f"{rng.choice(NAMES)}    {_german(_quantity(rng))} Stk.", f"          {_isin(rng)}"]
        return lines, _reason("custody_change", depot_ref=depot)
    baader_depot = f"99{rng.randrange(10**7, 10**8)}"
    lines = _baader_head(rng, _baader_right(rng), baader_depot, str(rng.randrange(10**8, 10**9))) + [
        rng.choice(("Depoteinlieferung", "Depotauslieferung", "Kapitalmaßnahme: Split")), f"Nominale     ISIN: {_isin(rng)}",
        f"STK {rng.randrange(1, 300)}      {rng.choice(NAMES)}"]
    return lines, _reason("custody_change", depot_ref=baader_depot)


def _tax(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    if rng.random() < 0.5:
        issuer, _profile = rng.choice(SCALABLE)
        lines = _scalable_head(rng, issuer, _business_day(rng)) + ["Steuerneuberechnung", "Grund für die Neuberechnung    Änderung der Bemessungsgrundlage",
                 f"Depot                       {rng.randrange(10**9, 10**10)}", f"Erstattung    {_german(_money(rng, 1, 50_000))} EUR"]
    else:
        lines = _baader_head(rng, _baader_right(rng), f"99{rng.randrange(10**7, 10**8)}", str(rng.randrange(10**8, 10**9))) + [
            f"{rng.choice(('Jahressteuerbescheinigung', 'Verlustbescheinigung'))} {rng.randrange(2021, 2024)}", "für Privatkonten und/oder -depots",
            f"Höhe der Kapitalerträge    EUR    {_german(_money(rng, 1, 500_000))}"]
    return lines, _reason("tax_document")


def _information(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    title = rng.choice(("Depotauszug", "Kosteninformation", "Ex-post-Kosteninformation", "Quartalsaufstellung"))
    if rng.random() < 0.5:
        issuer, _profile = rng.choice(SCALABLE)
        lines = _scalable_head(rng, issuer, _business_day(rng)) + [f"{title} zum {_day(date(rng.randrange(2021, 2025), 12, 31))}"]
    else:
        lines = _baader_head(rng, _baader_right(rng), f"99{rng.randrange(10**7, 10**8)}", str(rng.randrange(10**8, 10**9))) + [title]
    for _ in range(rng.randrange(1, 5)):
        lines.append(f"{rng.choice(NAMES)}    {_german(_quantity(rng))} Stk.    {_german(_money(rng, 100, 1_000_000))} EUR")
    return lines, _reason("information")


def _unknown(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    if rng.random() < 0.5:   # Scalable: Bestaetigung ohne Abrechnung
        issuer, _profile = rng.choice(SCALABLE)
        depot = str(rng.randrange(10**9, 10**10))
        lines = _scalable_head(rng, issuer, _business_day(rng)) + ["Bestätigung Ihrer Sparplanänderung",
                 f"Depot                       {depot}", f"Neue Sparrate    {_german(_money(rng, 2500, 100_000))} EUR"]
        return lines, _reason("unknown_document", depot_ref=depot)
    depot = f"99{rng.randrange(10**7, 10**8)}"
    lines = _baader_head(rng, _baader_right(rng), depot, str(rng.randrange(10**8, 10**9))) + ["Wertpapierabrechnung: Rückzahlung",
             f"Nominale       ISIN: {_isin(rng)}       Kurs", f"STK {rng.randrange(1, 100)}       {rng.choice(NAMES)}       EUR       100,00"]
    return lines, _reason("unknown_document", depot_ref=depot)


def _wrong_institution(rng: random.Random) -> tuple[list[str], dict[str, Any]]:
    """Baader rechnet auch fuer Smartbroker ab; diese Belege liest der Smartbroker-Leser."""
    lines, _expected = _baader_dividend(rng, "Smartbroker AG", "smartbroker")
    return lines, _reason("wrong_institution")


SECURITIES: tuple[tuple[str, int, Callable[[random.Random], tuple[list[str], dict[str, Any]]]], ...] = (
    ("trade", 18, _scalable_trade),
    ("trade_not_eur", 3, lambda rng: _scalable_trade(rng, "not_eur")),
    ("trade_incomplete", 2, lambda rng: _scalable_trade(rng, "incomplete")),
    ("trade_overview", 3, lambda rng: _scalable_trade(rng, "overview")),
    ("dividend", 13, _scalable_dividend),
    ("dividend_incomplete", 2, lambda rng: _scalable_dividend(rng, "incomplete")),
    ("advance_lump_sum", 12, _scalable_advance_lump_sum),
    ("baader_trade", 11, lambda rng: _baader_trade(rng, _baader_right(rng), "baader_scalable")),
    ("baader_trade_no_details", 2, lambda rng: _baader_trade(rng, _baader_right(rng), "baader_scalable", "no_details")),
    ("baader_trade_not_eur", 2, lambda rng: _baader_trade(rng, _baader_right(rng), "baader_scalable", "not_eur")),
    ("baader_dividend", 9, lambda rng: _baader_dividend(rng, _baader_right(rng), "baader_scalable")),
    ("baader_dividend_incomplete", 2, lambda rng: _baader_dividend(rng, _baader_right(rng), "baader_scalable", variant="incomplete")),
    ("custody", 4, _custody),
    ("tax", 4, _tax),
    ("information", 4, _information),
    ("unknown", 3, _unknown),
    ("wrong_institution", 3, _wrong_institution),
)


def _securities(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    name, _weight, build = rng.choices(SECURITIES, weights=[weight for _name, weight, _build in SECURITIES])[0]
    lines, expected = build(rng)
    return {"file_name": f"scalable-{name.replace('_', '-')}-erfunden-{seed}.txt", "content": "\n".join(lines) + "\n", "expected": expected}


GENERATORS = {
    "scalable_tagesgeld_v1": lambda seed: _cash_statement(seed, broker=False),
    "scalable_broker_v1": lambda seed: _cash_statement(seed, broker=True),
    "scalable_capital_v1": _securities,
}
