"""Erzeuger erfundener CHECK24-Buchungslisten fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Buchungen des Geldanlagecenters; daraus baut der Erzeuger den Browserdruck als Text (wie
pdftotext ihn liefert, Dateiname .txt) und - unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf,
sonst bestaetigte der Leser nur sich selbst. Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Banken, Kennungen,
Betraege, Tage; die Tage liegen in 2021-2024.

Abgedeckt: Zinsbuchung, Zinsgutschrift, Habenzinsen, negative Zinsen, Steuerabzuege, Veranlagung, Einzahlung, Auszahlung mit
Folgezeile ("Anlagekonto"), Buchung ueber 0,00 EUR (wird uebergangen), Buchung ohne Datum (Hinweis), Jahres- und Monatszeilen,
Seitenkopf und -fuss auch zwischen Betrag und Datum, Leerzeilen, Tausendertrennung. Die Liste steht wie im Druck, neueste zuerst.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import random
from typing import Any

MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember")
BANKS = ("Erfundene Bank", "Fantasie Sparkasse", "Beispielbank AG", "Muster Kreditinstitut")
TAXES = ("Steuerabzug - Kapitalertragsteuer", "Steuerabzug - Solidaritätszuschlag", "Steuerabzug - Kirchensteuer")


def _german(amount: Decimal) -> str:
    """96.4 -> "+96,40 €", -4200.75 -> "-4.200,75 €": Vorzeichen immer, Punkt als Tausendertrennung."""
    sign = "-" if amount < 0 else "+"
    whole, cents = f"{abs(amount):.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:]); whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}{'.'.join(groups)},{cents} €"


def _plain(amount: Decimal) -> str:
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _bookings(rng: random.Random, first: bool) -> list[tuple[str, list[str], Decimal]]:
    """Eine erfundene Buchung oder eine Zinsbuchung samt Steuerabzuegen: je (Beschreibung, Folgezeilen, Betrag)."""
    cents = lambda low, high: Decimal(rng.randrange(low, high)) / 100
    choice = rng.random()
    if choice < 0.4:
        interest = cents(1, 50_000)
        marker = rng.choice(("Zinsbuchung", "Zinsbuchung", "Zinsgutschrift", "Habenzinsen"))
        if not first and rng.random() < 0.05:
            return [(marker, [], -cents(1, 500))]           # negative Zinsen (2021): eine Abbuchung
        rows = [(marker, [], interest)]
        if rng.random() < 0.7:
            tax = (interest * Decimal("0.25")).quantize(Decimal("0.01"))
            rows.append((TAXES[0], [], -tax))
            rows.append((TAXES[1], [], -(tax * Decimal("0.055")).quantize(Decimal("0.01")) or -Decimal("0.01")))
            if rng.random() < 0.3:
                rows.append((TAXES[2], [], -(tax * Decimal("0.08")).quantize(Decimal("0.01")) or -Decimal("0.01")))
        return rows
    if choice < 0.6:
        return [(rng.choice(("Veranlagung", "Einzahlung")), [], cents(10_000, 5_000_000))]
    if choice < 0.8:
        return [(f"Auszahlung von {rng.choice(BANKS)} auf Ihr CHECK24", ["Anlagekonto"], -cents(1_000, 3_000_000))]
    if choice < 0.9:
        return [("Auszahlung an Ihr Referenzkonto", [], -cents(100, 1_000_000))]
    return [("Gutschrift Prämie", ["Erfundene Aktion"], cents(500, 10_000))]


def _generate(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    day = date(2023, 1, 1) + timedelta(days=rng.randrange(0, 700))
    printed = min(day + timedelta(days=rng.randrange(1, 60)), date(2024, 12, 31))
    stamp = f"{printed.month}/{printed.day}/{printed.strftime('%y')}, {rng.randrange(1, 13)}:{rng.randrange(0, 60):02d} {rng.choice(('AM', 'PM'))}"
    page_head = f"{stamp} (1) Geldanlagecenter | CHECK24"
    investment = f"{rng.randrange(10**7, 10**8)}"
    body: list[str] = []
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    ordinal = 0
    year = month = None
    for number in range(rng.randrange(1, 18)):
        if number:
            day -= timedelta(days=rng.randrange(0, 40))
        if day.year != year:
            year, month = day.year, None
            body.append(str(year))
        if day.month != month:
            month = day.month
            body.append(MONTHS[month - 1])
        for description, follow, amount in _bookings(rng, number == 0):
            special = "" if number == 0 else rng.choice([""] * 18 + ["zero", "no_date"])
            if special == "zero":
                amount = Decimal("0")
            ordinal += 1
            body.append(f"{description} {_german(amount)}")
            body.extend(follow)
            if special == "no_date":     # noch ohne Datum (etwa vorgemerkt): ein Hinweis statt einer Bewegung
                diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_missing"}); continue
            body.append(day.strftime("%d.%m.%Y"))
            if amount != 0:
                text = " ".join([description, *follow])
                interest = amount > 0 and text.lower().startswith(("zinsbuchung", "zinsgutschrift", "habenzinsen"))
                candidates.append({"source_row_ordinal": ordinal, "local_date": day.isoformat(),
                                   "kind": "interest" if interest else ("deposit" if amount > 0 else "withdrawal"),
                                   "amount_decimal": _plain(abs(amount)), "balance_after_decimal": None, "text": text})
            if rng.random() < 0.1:
                body.append("")
    # Seiten: Kopf je Seite, Fuss mit Adresse und Seitenzahl; ein Umbruch faellt auch zwischen Betrag und Datum.
    size = rng.randrange(12, 40)
    pages = [body[index:index + size] for index in range(0, len(body), size)] or [[]]
    lines = [page_head, "Zurück", "Transaktionen Ihrer Anlage"]
    for number, page in enumerate(pages, 1):
        if number > 1:
            lines.append(page_head)
        lines.extend(page)
        lines.append(f"https://geldanlage.check24.de/ga-center/investment/{investment}/bookings {number}/{len(pages)}")
    days = sorted(row["local_date"] for row in candidates)
    expected = {"candidates": candidates, "diagnostics": diagnostics,
                "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}
    return {"file_name": f"check24-erfunden-{seed}.txt", "content": ("\n".join(lines) + "\n").encode("utf-8"), "expected": expected}


GENERATORS = {"check24_geldanlage_v1": _generate}
