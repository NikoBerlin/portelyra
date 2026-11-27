"""Erzeuger erfundener ING-Belege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Wie die Referenz (c24): Aus einem Startwert entstehen erfundene Vorgaenge; aus ihnen baut der Erzeuger den Beleg im Format der ING
und - unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der Leser nur sich
selbst. Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Namen, Konto- und Depotnummern, ISIN, WKN, Ordernummern,
Betraege, Tage (2021-2024, damit "kein Buchungstag nach heute" auch mit dem Datum des Rechners gilt).

- ing_v1 (cash): Kontoauszug Giro oder Extra-Konto als PDF-Text (.txt, so wie pdftotext -layout ihn liefert). Buchungszeilen mit
  Buchungsart, Valuta-Zeilen mit Verwendungszweck (auch mit einem Betrag am Ende), Fussnotenziffer hinter dem Betrag,
  Tausenderpunkte, negativer Saldo, Seitenwechsel, Buchungen ueber 0,00 (gezaehlt, nicht gebucht) und ein Tag, den es nicht
  gibt (Hinweis statt Bewegung). Zinsen sind nur "Zinsertrag"/"Zinsgutschrift"; "Zins/Dividende" ist eine Einzahlung.
- ing_direkt_depot_v1 (securities): je Startwert ein Beleg des Direkt-Depots als PDF-Text: Kauf und Verkauf (Gebuehren je Art,
  Festpreisgeschaeft, Veraeusserungsgewinn oder -verlust), Dividende/Ertrag/Ausschuettung in EUR und in Fremdwaehrung (mit und
  ohne Quellensteuer), Splitmitteilung, Vorabpauschale in beiden Vorlagen (bis 2025 Betrag vorn, seit 2026 Rueckseite mit
  Zwoelftel-Kuerzung) und Belege, die einen Grund bekommen (Uebertrag, Steuerunterlage, Sammeluebersicht, unvollstaendig,
  thesaurierend, nicht in EUR, Vorabpauschale ueber Stueck x Wert, anderes Splitverhaeltnis, unbekannter Beleg).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
import random
from typing import Any

CENT = Decimal("0.01")
MONTH_NAMES = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _german(value: Decimal, places: int = 2) -> str:
    """1234.5 -> "1.234,50" (Tausenderpunkt, Dezimalkomma), negativ mit Minus vorn - wie die Belege der ING."""
    sign = "-" if value < 0 else ""
    text = f"{abs(value):.{places}f}"
    whole, _, fraction = text.partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:]); whole = whole[:-3]
    groups.insert(0, whole)
    return sign + ".".join(groups) + ("," + fraction if fraction else "")


def _day(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def _money(rng: random.Random, low: int, high: int) -> Decimal:
    """Betrag in Cent zwischen low und high (beide in Cent)."""
    return Decimal(rng.randrange(low, high)) / 100


# ---------------------------------------------------------------- ing_v1: Kontoauszug Giro und Extra-Konto
# (Buchungsart, Gegenpartei, Vorzeichen, Verwendungszweck der Valuta-Zeile oder None). "{n}" wird zu einer erfundenen Nummer, "{amount}"
# zum Betrag: Die ING schreibt ihn bei Lastschriften mitunter ans Ende des Verwendungszwecks ("... Betrag 137,00").
GIRO_BOOKINGS = (
    ("Lastschrift", "ERFUNDENE VERSICHERUNG", -1, "MNr. {n} RNR {n} Betrag {amount}"),
    ("Lastschrift", "Bargeldauszahlung VISA Card ERFUNDEN", -1, "AT"),
    ("Lastschrift", "Erfundene Stadtwerke", -1, "Abschlag Kundennummer {n}"),
    ("Gutschrift", "Erfundene Absenderin", 1, "Erstattung {n}"),
    ("Gehalt/Rente", "Erfundene Arbeitgeberin GmbH", 1, "Gehalt"),
    ("Dauerauftrag", "Erfundene Vermieterin", -1, "Miete Wohnung {n}"),
    ("Überweisung", "Erfundener Empfänger", -1, "Rechnung {n}"),
    ("Echtzeitüberweisung", "Erfundene Freundin", -1, None),
    ("Entgelt", "Kontoführung", -1, None),
    ("Retoure", "Erfundener Versandhandel", 1, "Rücksendung {n}"),
    ("Bargeldeinzahlung", "Erfundene Filiale", 1, None),
    ("Wertpapierkauf", "Direkt-Depot {n}", -1, None),
    ("Zins/Dividende", "ISIN US0000000001 ERFUNDENE AG", 1, None),
    ("Kapitalertragsteuer", "", -1, None),
)
EXTRA_BOOKINGS = (
    ("Umbuchung", "Girokonto {n}", 1, None),
    ("Umbuchung", "Girokonto {n}", -1, None),
    ("Gutschrift", "Erfundener Sparer", 1, "Sparrate"),
    ("Abbuchung", "Girokonto {n}", -1, None),
)
INTEREST = (("Zinsertrag", ""), ("Zinsgutschrift", ""))


def _cash(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    extra = rng.random() < 0.3
    year, month = rng.randrange(2021, 2025), rng.randrange(1, 13)
    first = date(year, month, 1)
    last = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    opening = _money(rng, 0, 2_000_000) - (0 if extra or rng.random() < 0.8 else Decimal("2500"))   # Giro auch im Dispo
    bookings = sorted(rng.sample(range(first.day, last.day + 1), rng.randrange(2, 18)))
    number = lambda: str(rng.randrange(10**5, 10**10))
    lines = ["ING-DiBa AG"]
    body: list[str] = []
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    balance = opening
    ordinal = 0
    for index, day_number in enumerate(bookings):
        day = first.replace(day=day_number)
        interest = (index == len(bookings) - 1 and rng.random() < 0.7) or rng.random() < 0.08
        if interest:
            kind_text, payee = rng.choice(INTEREST)
            sign, purpose = 1, f"Zinsen {_day(first)} - {_day(last)}" if rng.random() < 0.6 else None
            amount = _money(rng, 1, 30_000)
        else:
            kind_text, payee, sign, purpose = rng.choice(EXTRA_BOOKINGS if extra else GIRO_BOOKINGS)
            amount = _money(rng, 1, 400_000 if sign > 0 else 150_000)
        payee = payee.replace("{n}", number())
        special = rng.random()
        if special < 0.05:
            amount = Decimal("0")                        # Buchung ueber 0,00: gezaehlt, nicht gebucht
        value = amount * sign
        footnote = str(rng.randrange(1, 10)) if amount and special > 0.9 else ""   # Fussnotenziffer hinter dem Betrag
        booking_day = _day(day)
        invalid_day = 0.05 <= special < 0.075
        if invalid_day:                                  # ein Tag, den es nicht gibt: ein Hinweis statt einer Bewegung
            booking_day = f"{rng.choice(('30', '31'))}.02.{day.year}"
        text = " ".join(part for part in (kind_text, payee) if part)
        body.append(f"{booking_day}   {text}{' ' * rng.randrange(3, 40)}{_german(value)}{footnote}")
        if purpose is not None:
            valuta = day - timedelta(days=rng.choice((0, 0, 0, 1, 2, 3)))
            body.append(f"{_day(valuta)}   " + purpose.replace("{n}", number()).replace("{amount}", _german(amount)))
        if rng.random() < 0.08 and index < len(bookings) - 1:   # Seitenwechsel: Fuss und Kopf der naechsten Seite
            body += ["", f"Seite {rng.randrange(1, 3)} von 3", "ING-DiBa AG", "Buchung Buchung / Verwendungszweck Betrag (EUR)", "Valuta"]
        balance += value
        ordinal += 1
        if amount == 0:
            continue
        if invalid_day:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        kind = "interest" if interest else ("deposit" if sign > 0 else "withdrawal")
        candidates.append({"source_row_ordinal": ordinal, "local_date": day.isoformat(), "kind": kind, "amount_decimal": _plain(amount),
                           "balance_after_decimal": None, "text": text})
    if not candidates:   # mindestens eine Bewegung, sonst ist der Auszug kein Beleg dieses Formats
        day = last
        body.append(f"{_day(day)}   Zinsertrag{' ' * 30}0,01")
        balance += CENT
        ordinal += 1
        candidates.append({"source_row_ordinal": ordinal, "local_date": day.isoformat(), "kind": "interest", "amount_decimal": "0.01",
                           "balance_after_decimal": None, "text": "Zinsertrag"})
    euro = " Euro" if rng.random() < 0.8 else ""
    owner = rng.choice(("Erika Erfunden", "Max Mustermann-Erfunden", "Invented Owner", "Erfundene Eheleute"))
    lines += [f"{owner}{' ' * rng.randrange(4, 30)}Alter Saldo{' ' * rng.randrange(2, 20)}{_german(opening)}{euro}",
              f"{rng.randrange(10000, 99999)} Erfundenstadt{' ' * rng.randrange(4, 30)}Neuer Saldo{' ' * rng.randrange(2, 20)}{_german(balance)}{euro}",
              f"{'Extra-Konto' if extra else 'Girokonto'} Nummer {rng.randrange(10**9, 10**10)}",
              f"IBAN DE00 0000 0000 {rng.randrange(1000, 9999)} {rng.randrange(1000, 9999)} 00",
              f"Kontoauszug {MONTH_NAMES[month - 1]} {year}", "",
              "Buchung   Buchung / Verwendungszweck                                   Betrag (EUR)", "Valuta"]
    lines += body
    if rng.random() < 0.5:
        lines += ["", f"Neuer Saldo{' ' * 20}{_german(balance)}{euro}"]   # Endsaldo noch einmal am Ende: der erste zaehlt, beide gleich
    days = sorted(row["local_date"] for row in candidates)
    expected = {"candidates": candidates, "diagnostics": diagnostics,
                "summary": {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(balance),
                            "period_from": days[0], "period_to": days[-1]}}
    return {"file_name": f"ing-kontoauszug-erfunden-{seed}.txt", "content": ("\n".join(lines) + "\n").encode("utf-8"), "expected": expected}


# ---------------------------------------------------------------- ing_direkt_depot_v1: Belege des Direkt-Depots
NAMES = ("Erfundene Software AG", "Invented Equity Inc.", "Fantasie Industrie SE", "Erfundener Welt Fonds Acc", "Invented Dividend ETF Dist",
         "Musterbau Holding AG", "Erfundene Versorger plc")
VENUES = ("Xetra", "Tradegate", "gettex", "Direkthandel", "Frankfurt")
FEES = ("Provision", "Handelsplatzgebühr", "Fremde Spesen", "Fremdspesen", "Börsenentgelt", "Ausgabeaufschlag", "Transaktionsentgelt", "Maklercourtage")
GAP = "    "


def _isin(rng: random.Random) -> str:
    return f"{rng.choice(('US', 'DE', 'IE', 'LU', 'FR', 'NL'))}0000{rng.randrange(10**5):05d}{rng.randrange(10)}"


def _wkn(rng: random.Random) -> str:
    return "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789") for _ in range(6))


def _depot_head(rng: random.Random, depot: str) -> list[str]:
    return ["ING-DiBa AG · 60628 Frankfurt am Main", f"Direkt-Depot Nr.:{' ' * rng.randrange(4, 30)}{depot}", rng.choice(("Frau", "Herrn")),
            rng.choice(("Erika Erfunden", "Max Erfunden", "Invented Owner")), f"Erfundene Straße {rng.randrange(1, 99)}"]


def _security_candidate(kind: str, **fields: Any) -> dict[str, Any]:
    value = {"status": "candidate", "kind": kind, "profile": "ing", "isin": None, "security_name": None, "local_date": None, "local_time": None,
             "quantity": None, "unit_price": None, "gross_amount": None, "fee_amount": "0", "eligible_quantity": None, "order_ref": None,
             "depot_ref": None, "ex_date": None, "net_amount": None, "taxes_amount": None, "withholding_amount": None, "bank_gain": None,
             "fee_on_cash_statement": False, "currency": None, "valuta": None, "statement_checked": False}
    value.update(fields)
    return value


def _reason(code: str, depot: str | None) -> dict[str, Any]:
    return {"status": "not_importable", "reason_code": code, "reason": code, "depot_ref": depot}


def _quantity(rng: random.Random) -> Decimal:
    if rng.random() < 0.25:
        return Decimal(rng.randrange(1, 99_999)) / 10_000           # Bruchstuecke (Sparplan)
    return Decimal(rng.choice((rng.randrange(1, 60), rng.randrange(1, 2000))))


def _quantity_text(rng: random.Random, value: Decimal) -> str:
    return _german(value, 4) if value != value.to_integral_value() or rng.random() < 0.3 else _german(value, 2)


def _trade(rng: random.Random, depot: str, day: date, variant: str) -> tuple[list[str], dict[str, Any]]:
    buy = variant != "sell"
    isin, name = _isin(rng), rng.choice(NAMES)
    quantity = _quantity(rng)
    places = rng.choice((2, 2, 3, 4))
    price = Decimal(rng.randrange(100, 400_000)) / 100 if places == 2 else Decimal(rng.randrange(1000, 4_000_000)) / Decimal(10) ** places
    gross = (quantity * price).quantize(CENT, ROUND_HALF_UP)
    order = f"{rng.randrange(10**8, 10**9)}.{rng.randrange(1, 4):03d}"
    moment = f"{rng.randrange(8, 22):02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}"
    fees = [(label, _money(rng, 1, 2_500)) for label in rng.sample(FEES, rng.choice((0, 1, 1, 2, 2, 3)))]
    fee_total = sum((value for _label, value in fees), Decimal(0))
    currency = "USD" if variant == "not_eur" else "EUR"
    fixed = rng.random() < 0.15
    lines = [f"Wertpapierabrechnung{GAP}{'Kauf' if buy else 'Verkauf'}", f"Ordernummer{GAP}{order}", f"ISIN (WKN){GAP}{isin} ({_wkn(rng)})",
             f"Wertpapierbezeichnung{GAP}{name}", f"Nominale{GAP}Stück{GAP}{_quantity_text(rng, quantity)}",
             f"Kurs{' (Festpreisgeschäft)' if fixed else ''}{GAP}{currency}{GAP}{_german(price, places)}", f"Handelsplatz{GAP}{rng.choice(VENUES)}",
             f"Ausführungstag / -zeit{GAP}{_day(day)} um {moment} Uhr"]
    if variant != "incomplete":
        lines.append(f"Kurswert{GAP}{currency}{GAP}{_german(gross)}")
    for label, value in fees:
        lines.append(f"{label}{' 0,25 %' if label == 'Provision' and rng.random() < 0.3 else ''}{GAP}EUR{GAP}{_german(value)}")
    gain = None
    taxes = Decimal(0)
    if not buy:
        gain = _money(rng, 0, 200_000) * rng.choice((1, 1, -1))
        if gain >= 0:
            taxes = (gain * Decimal("0.26375")).quantize(CENT, ROUND_HALF_UP)
            lines += [f"Veräußerungsgewinn nach Differenzmethode{GAP}{_german(gain)} EUR"]
            if taxes:
                lines += [f"Kapitalertragsteuer 25,00 %{GAP}EUR{GAP}{_german((taxes / Decimal('1.055')).quantize(CENT))}",
                          f"Solidaritätszuschlag 5,50 %{GAP}EUR{GAP}{_german(taxes - (taxes / Decimal('1.055')).quantize(CENT))}"]
        else:   # Verlust: mal mit, mal ohne Minus vor dem Betrag - beides ist ein Verlust
            lines += [f"Veräußerungsverlust nach Differenzmethode{GAP}{_german(gain if rng.random() < 0.5 else -gain)} EUR"]
    net = gross + fee_total if buy else gross - fee_total - taxes
    has_net = rng.random() < 0.95
    if has_net:
        lines.append(f"Endbetrag zu Ihren {'Lasten' if buy else 'Gunsten'}{GAP}EUR{GAP}{_german(net)}")
    lines.append(f"Valuta{GAP}{_day(day + timedelta(days=2))}")
    if variant == "incomplete":
        return lines, _reason("incomplete", depot)
    if variant == "not_eur":
        return lines, _reason("not_eur", depot)
    return lines, _security_candidate("buy" if buy else "sell", isin=isin, security_name=name, local_date=day.isoformat(), local_time=moment,
                                      quantity=_plain(quantity), unit_price=_plain(price), gross_amount=_plain(gross), fee_amount=_plain(fee_total),
                                      net_amount=_plain(net) if has_net else None, order_ref=order, depot_ref=depot,
                                      bank_gain=_plain(gain) if gain is not None else None)


def _income(rng: random.Random, depot: str, day: date, variant: str) -> tuple[list[str], dict[str, Any]]:
    isin, name = _isin(rng), rng.choice(NAMES)
    quantity = _quantity(rng)
    title = rng.choice(("Dividendengutschrift", "Ertragsgutschrift", "Ausschüttung"))
    ex = day - timedelta(days=rng.randrange(1, 20))
    lines = [title, f"ISIN (WKN){GAP}{isin} ({_wkn(rng)})", f"Wertpapierbezeichnung{GAP}{name}", f"Nominale{GAP}{_quantity_text(rng, quantity)} Stück"]
    if variant == "accumulating":   # thesaurierend: kein Brutto, nur der zu versteuernde Gegenwert
        lines = ["Ertragsgutschrift"] + lines[1:] + [f"Zahltag{GAP}{_day(day)}", f"Zwischensumme{GAP}USD{GAP}0,00", f"Gesamtbetrag{GAP}EUR{GAP}0,00",
                                                     "Der Gegenwert ist als Ertrag zu versteuern."]
        return lines, _reason("accumulating_income", depot)
    rate_per_unit = Decimal(rng.randrange(1, 300)) / 100
    gross = (quantity * rate_per_unit).quantize(CENT, ROUND_HALF_UP) or CENT
    with_ex = rng.random() < 0.85
    if variant == "fx":
        currency = rng.choice(("USD", "USD", "CHF", "GBP"))
        fx = Decimal(rng.randrange(800_000, 1_400_000)) / 1_000_000
        gross_eur = (gross / fx).quantize(CENT, ROUND_HALF_UP)
        lines.append(f"Zins-/Dividendensatz{GAP}{_german(rate_per_unit)} {currency}")
        lines += [f"Ex-Tag{GAP}{_day(ex)}"] if with_ex else []
        lines += [f"Zahltag{GAP}{_day(day)}", f"Brutto{GAP}{currency}{GAP}{_german(gross)}"]
        withholding = None
        foreign = Decimal(0)
        if rng.random() < 0.7:
            foreign = (gross * Decimal("0.15")).quantize(CENT, ROUND_HALF_UP)
            withholding = (foreign / fx).quantize(CENT, ROUND_HALF_UP)
            lines.append(f"{rng.choice(('QuSt', 'Quellensteuer'))} 15,00 % (EUR {_german(withholding)}){GAP}{currency}{GAP}{_german(foreign)}")
        rest = ((gross - foreign) / fx).quantize(CENT, ROUND_HALF_UP)
        lines += [f"Zwischensumme{GAP}{currency}{GAP}{_german(gross - foreign)}", f"Umg. z. Dev.-Kurs ({_german(fx, 6)}){GAP}EUR{GAP}{_german(rest)}"]
        net = rest
    else:
        gross_eur, withholding = gross, None
        lines.append(f"Zins-/Dividendensatz{GAP}{_german(rate_per_unit)} EUR")
        lines += [f"Ex-Tag{GAP}{_day(ex)}"] if with_ex else []
        lines += [f"Zahltag{GAP}{_day(day)}", f"Brutto{GAP}EUR{GAP}{_german(gross)}"]
        net = gross
    if rng.random() < 0.6:
        tax = (net * Decimal("0.25")).quantize(CENT, ROUND_HALF_UP)
        soli = (tax * Decimal("0.055")).quantize(CENT, ROUND_HALF_UP)
        lines += [f"Kapitalertragsteuer 25,00 %{GAP}EUR{GAP}{_german(tax)}", f"Solidaritätszuschlag 5,50 %{GAP}EUR{GAP}{_german(soli)}"]
        net -= tax + soli
    lines += [f"Gesamtbetrag zu Ihren Gunsten{GAP}EUR{GAP}{_german(net)}", f"Valuta{GAP}{_day(day)}"]
    return lines, _security_candidate("dividend", isin=isin, security_name=name, local_date=day.isoformat(), eligible_quantity=_plain(quantity),
                                      gross_amount=_plain(gross_eur), ex_date=ex.isoformat() if with_ex else None,
                                      withholding_amount=_plain(withholding) if withholding is not None else None, net_amount=_plain(net), depot_ref=depot)


def _split(rng: random.Random, depot: str, day: date, variant: str) -> tuple[str, dict[str, Any]]:
    """Splitmitteilung als "Wertpapier Eingang" der Zusatzaktien; das Verhaeltnis nennt die Zusatzaktien je gehaltener Aktie."""
    isin, name = _isin(rng), rng.choice(NAMES)
    extra = rng.randrange(1, 10)
    held = Decimal(rng.randrange(1, 400))
    credited = held * extra
    record = day - timedelta(days=rng.randrange(1, 6))
    order = str(rng.randrange(10**9, 10**10))
    ratio = f"1:{extra}" if variant == "split" else rng.choice(("2:3", "3:1", "1:0", "4:1"))
    text = "\n".join([
        "ING-DiBa AG · 60628 Frankfurt am Main",
        f"{' ' * 54}Depotinhaber:{' ' * 24}Erika Erfunden",
        f"{' ' * 54}Direkt-Depot Nr.:{' ' * 20}{depot}",
        "Frau",
        f"Erika Erfunden{' ' * 40}Datum:{' ' * 31}{_day(day + timedelta(days=rng.randrange(0, 5)))}",
        f"Erfundene Straße 1{' ' * 36}Seite:{' ' * 31}1 von 1",
        "Wertpapier Eingang",
        "nachstehende Wertpapiere haben wir Ihrem Depot gutgeschrieben:",
        f"Nominale / Stück{' ' * 20}Wertpapier-Informationen{' ' * 32}Schlusstag{' ' * 16}Auftragsnummer",
        f"{_german(credited, 4)} Stück{' ' * rng.randrange(4, 24)}{name}{' ' * rng.randrange(4, 24)}{_day(day)}{' ' * rng.randrange(1, 8)}{order}",
        f"{' ' * 36}Registered Shares o.N.",
        f"{' ' * 36}ISIN (WKN):{' ' * 5}{isin} ({_wkn(rng)})",
        f"{' ' * 36}Girosammelverwahrung",
        f"{' ' * 36}Die Gesellschaft hat einen Aktiensplit durchgeführt. Wir haben Ihrem",
        f"{' ' * 36}Depot die Splitaktien eingebucht.",
        f"{' ' * 36}Die ursprünglichen Anschaffungskosten werden auf Ihre neue",
        f"{' ' * 36}Gesamtstückzahl aufgeteilt.",
        f"{' ' * 36}Das Splitverhältnis ist {ratio} auf Ihren Bestand vom {_day(record)}.",
    ]) + "\n"
    if variant != "split":   # Zusammenlegung, fehlender Satz: eine Bestandsveraenderung zum manuellen Erfassen
        return text, _reason("custody_change", depot)
    return text, _security_candidate("stock_split", isin=isin, security_name=name, local_date=day.isoformat(), record_date=record.isoformat(),
                                     ratio_numerator=str(extra + 1), ratio_denominator="1", credited_quantity=_plain(credited), order_ref=order,
                                     depot_ref=depot)


def _advance_lump_sum(rng: random.Random, depot: str, day: date, variant: str) -> tuple[list[str], dict[str, Any]]:
    """Vorabpauschale je Fonds: bis 2025 der Betrag vorn, seit 2026 vorn je Stueck und der Betrag hinten (hoechstens Stueck x Wert
    je Stueck, im Jahr erworbene Anteile um Zwoelftel gekuerzt). Zufluss Anfang Januar, Berechnungsjahr = Vorjahr."""
    isin, name = _isin(rng), rng.choice(NAMES[3:5] + ("Erfundener Anleihen Fonds Acc",))
    quantity = Decimal(rng.randrange(1, 900)) if rng.random() < 0.8 else Decimal(rng.randrange(1, 99_999)) / 1000
    paid = date(day.year, 1, rng.randrange(2, 6))
    with_ex, with_pay = (True, True) if rng.random() < 0.7 else rng.choice(((True, False), (False, True)))
    named = rng.random() < 0.7
    wkn = _wkn(rng)
    lines = ["Vorabpauschale", f"ISIN (WKN){GAP}{isin} ({wkn})"]
    lines += [f"Wertpapierbezeichnung{GAP}{name}"] if named else []
    lines.append(f"Nominale{GAP}{_quantity_text(rng, quantity)} Stück")
    days = ([f"Ex-Tag{GAP}{_day(paid)}"] if with_ex else []) + ([f"Zahltag{GAP}{_day(paid)}"] if with_pay else [])
    if variant in ("new", "inconsistent"):
        per_unit = Decimal(rng.randrange(1, 900_000)) / 10**7
        full = quantity * per_unit
        months = rng.choice((0, 0, 0, rng.randrange(1, 12)))
        amount = (full * (12 - months) / 12).quantize(CENT, ROUND_HALF_UP)
        if variant == "inconsistent":
            amount = full.quantize(CENT, ROUND_HALF_UP) + _money(rng, 2, 5_000)
        lines += [f"Vorabpauschale per Stück{GAP}{_german(per_unit, 8)} EUR", f"Vorabpauschale mit Teilfreist. per St.{GAP}{_german(per_unit * Decimal('0.7'), 8)} EUR"]
        lines += days + [f"Gesamtbetrag zu Ihren Gunsten{GAP}EUR{GAP}0,00", "Jahressteuerbescheinigung folgt.", "",
                         f"ISIN (WKN) {isin} ({wkn})", f"Vorabpauschale gem. § 18 InvStG{GAP}{_german(amount)} EUR",
                         f"KapSt-pflichtiger Kapitalertrag{GAP}EUR{GAP}0,00"]
        if variant == "inconsistent":
            return lines, _reason("advance_lump_sum_inconsistent", depot)
    else:
        amount = _money(rng, 1, 30_000)
        lines += days
        if variant == "missing":   # ohne ausgewiesenen Betrag wird nichts errechnet
            lines.append(f"Vorabpauschale per Stück{GAP}{_german(amount / quantity, 8)} EUR")
            return lines, _reason("incomplete", depot)
        lines.append(f"Vorabpauschale gem. § 18 InvStG{GAP}EUR{GAP}{_german(amount)}" if rng.random() < 0.5
                     else f"Vorabpauschale gem. § 18 InvStG{GAP}{_german(amount)} EUR")
        lines += [f"KapSt-pflichtiger Kapitalertrag{GAP}EUR{GAP}{_german(amount)}", f"Gesamtbetrag zu Ihren Gunsten{GAP}EUR{GAP}0,00"]
    return lines, _security_candidate("advance_lump_sum", isin=isin, security_name=name if named else None, local_date=paid.isoformat(),
                                      ex_date=paid.isoformat() if with_ex else None, eligible_quantity=_plain(quantity), gross_amount=_plain(amount),
                                      depot_ref=depot, calculation_year=paid.year - 1)


def _reason_document(rng: random.Random, depot: str, day: date, variant: str) -> tuple[list[str], dict[str, Any]]:
    isin = _isin(rng)
    if variant == "custody":
        title = rng.choice(("Übertrag Eingang", "Übertrag Ausgang", "Wertpapier Ausgang", "Wertpapier Eingang"))
        return [title, "nachstehende Wertpapiere haben wir Ihrem Depot gutgeschrieben:",
                f"{rng.randrange(1, 90)},00 Stück{GAP}{rng.choice(NAMES)}{GAP}{_day(day)}"], _reason("custody_change", depot)
    if variant == "tax":
        title = rng.choice((f"Jahressteuerbescheinigung {day.year}", f"Verlustbescheinigung {day.year}", f"Erträgnisaufstellung {day.year}"))
        return [title, f"für das Kalenderjahr {day.year}", f"Kapitalerträge{GAP}EUR{GAP}{_german(_money(rng, 0, 500_000))}"], _reason("tax_document", depot)
    if variant == "overview":   # mehrere Vorgaenge auf einem Beleg
        return [f"Wertpapierabrechnung{GAP}Kauf", f"Ordernummer{GAP}{rng.randrange(10**8, 10**9)}.001", f"ISIN (WKN){GAP}{isin} ({_wkn(rng)})",
                f"Ordernummer{GAP}{rng.randrange(10**8, 10**9)}.002", f"ISIN (WKN){GAP}{_isin(rng)} ({_wkn(rng)})"], _reason("overview", depot)
    title = rng.choice((f"Depotauszug per {_day(day)}", "Ex-post-Kosteninformation", "Kosteninformation zum Wertpapiergeschäft"))
    return [title, f"ISIN (WKN){GAP}{isin} ({_wkn(rng)})", f"Kurswert{GAP}EUR{GAP}{_german(_money(rng, 100, 900_000))}"], _reason("unknown_document", depot)


SECURITY_VARIANTS = (   # (Gewicht, Erzeuger, Variante)
    (16, _trade, "buy"), (12, _trade, "sell"), (2, _trade, "incomplete"), (2, _trade, "not_eur"),
    (9, _income, "eur"), (8, _income, "fx"), (2, _income, "accumulating"),
    (6, _split, "split"), (2, _split, "other_ratio"),
    (7, _advance_lump_sum, "old"), (7, _advance_lump_sum, "new"), (2, _advance_lump_sum, "inconsistent"), (2, _advance_lump_sum, "missing"),
    (2, _reason_document, "custody"), (2, _reason_document, "tax"), (2, _reason_document, "overview"), (2, _reason_document, "unknown"),
)


def _securities(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    depot = f"80{rng.randrange(10**7, 10**8)}"
    day = date(2021, 1, 4) + timedelta(days=rng.randrange(0, 365 * 4 - 10))
    _weight, build, variant = rng.choices(SECURITY_VARIANTS, weights=[item[0] for item in SECURITY_VARIANTS])[0]
    document, expected = build(rng, depot, day, variant)
    if isinstance(document, list):
        document = "\n".join(_depot_head(rng, depot) + document) + "\n"
    return {"file_name": f"ing-depot-erfunden-{seed}.txt", "content": document, "expected": expected}


GENERATORS = {"ing_v1": _cash, "ing_direkt_depot_v1": _securities}
