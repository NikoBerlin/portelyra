"""Erzeuger erfundener Baader-Belege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Zwei Leser, je ein Erzeuger: der Perioden-Kontoauszug (Bereich cash; der Text, wie ihn pdftotext liefert, als .txt in Bytes) und die
Ertraegnisaufstellung (Bereich income_statement; der Text wie aus pdftotext -layout). Aus einem Startwert entstehen erfundene
Vorgaenge; aus ihnen baut der Erzeuger den Beleg in der Vorlage der Baader Bank und - unabhaengig vom Leser - das erwartete Ergebnis.
Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der Leser nur sich selbst. Gleicher Startwert, gleicher Beleg. Alle Werte sind
erfunden: Namen, Konto- und Depotnummern, ISIN, Vorgangs- und Transaktionsnummern, Betraege, Tage.

Die Tage liegen in der Vergangenheit (2021-2024), damit der Beleg auch die Regel "kein Buchungstag nach heute" erfuellt, wenn der
Selbsttest vor einer Installation mit dem Datum des Rechners laeuft.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import random
from typing import Any


def _german(cents: int) -> str:
    """123456 -> "1.234,56" wie in den Belegen der Baader Bank; die Belastung kennzeichnet der Aufrufer (nachgestelltes "-")."""
    whole, rest = divmod(abs(cents), 100)
    return f"{whole:,}".replace(",", ".") + f",{rest:02d}"


def _signed(cents: int) -> str:
    return _german(cents) + (" -" if cents < 0 else "")


def _plain(cents: int) -> str:
    """Betrag in Cent als Dezimaltext des Bereichs cash: ohne Nullen am Ende, 1250 -> "12.5", 10000 -> "100"."""
    text = format(Decimal(cents).scaleb(-2).normalize(), "f")
    return "0" if text in ("-0", "") else text


def _exact(cents: int) -> Decimal:
    """Betrag in Cent als Dezimalzahl mit zwei Stellen, so wie die Aufstellung ihn druckt: 400 -> Decimal("4.00")."""
    return Decimal(cents).scaleb(-2)


def _dmy(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def _person(rng: random.Random) -> list[str]:
    return [f"{rng.choice(('Erika', 'Max', 'Lena', 'Jonas', 'Mira'))} {rng.choice(('Erfunden', 'Mustermann', 'Beispiel', 'Fantasie'))}",
            f"Erfundene Straße {rng.randrange(1, 120)}", f"0{rng.randrange(1000, 9999)} Musterstadt"]


# ---------------------------------------------------------------- Perioden-Kontoauszug (Bereich cash)
# (Erlaeuterung, Vorzeichen, erwartete Art, Betragsrahmen in Cent, Gewicht). Zins ist nach der Vorlage nur eine Gutschrift mit
# Habenzinsen, Zinsgutschrift, erhaltenen Zinsen oder Rechnungsabschluss - nie ein Storno, nie eine Belastung; alles andere ist Ein-
# oder Auszahlung nach dem Vorzeichen.
CASH_OPERATIONS = (
    ("Kauf", -1, "withdrawal", (500, 2_500_000), 10),
    ("Verkauf", 1, "deposit", (500, 2_500_000), 6),
    ("Überweisung", 1, "deposit", (1_000, 1_000_000), 5),
    ("Lastschrift", 1, "deposit", (2_500, 100_000), 3),
    ("Auszahlung", -1, "withdrawal", (1_000, 500_000), 3),
    ("Dividende", 1, "deposit", (1, 80_000), 5),
    ("Kupon", 1, "deposit", (1, 80_000), 2),
    ("Steuern", -1, "withdrawal", (1, 30_000), 2),
    ("Steuerausgleich", 1, "deposit", (1, 30_000), 2),
    ("Ordergebühr", -1, "withdrawal", (99, 1_500), 2),
    ("Habenzinsen", 1, "interest", (1, 25_000), 3),
    ("Zinsgutschrift", 1, "interest", (1, 25_000), 2),
    ("Erhaltene Zinsen", 1, "interest", (1, 25_000), 1),
    ("Rechnungsabschluss", 1, "interest", (1, 25_000), 2),
    ("Rechnungsabschluss", -1, "withdrawal", (1, 3_000), 1),        # Sollzinsen im Abschluss: Belastung, kein Zins
    ("Storno Habenzinsen", -1, "withdrawal", (1, 25_000), 1),
    ("Storno Rechnungsabschluss", 1, "deposit", (1, 3_000), 1),     # Storno einer Belastung: Gutschrift, aber kein Zins
    ("Sollzinsen", -1, "withdrawal", (1, 3_000), 1),
)
# Buchungen ohne Betrag fuehrt die Bank mit; sie zaehlen als Zeile, werden aber keine Bewegung.
CASH_WITHOUT_AMOUNT = ("Kapitalmaßnahme", "Depotübertrag")
SECURITY_TEXTS = ("Kauf", "Verkauf", "Dividende", "Kupon")
COLUMNS = "Buchungstag              Erläuterungen                    Valuta           Belastung        Gutschrift"


def _booking_line(day: date, text: str, valuta: date, cents: int) -> str:
    """Belastung in der vorletzten Spalte mit nachgestelltem "-", Gutschrift in der letzten."""
    head = f"{_dmy(day):<25}{text:<31} {_dmy(valuta)}"
    return head + (_signed(cents).rjust(26) if cents < 0 else _german(cents).rjust(44))


def _balance_line(day: date | None, cents: int) -> str:
    label = "Kontostand in EUR am" + (f" {_dmy(day)}" if day is not None else "")
    return f"{label:<71}{_signed(cents)}"


def _generate_perioden(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    month = rng.randrange(0, 45)                                   # Januar 2021 bis September 2024
    start = date(2021 + month // 12, month % 12 + 1, 1)
    after = month + rng.choice((1, 1, 1, 1, 2, 3))                 # meist ein Monat, sonst zwei oder ein Quartal
    end = date(2021 + after // 12, after % 12 + 1, 1) - timedelta(days=1)
    chance = rng.random()
    variant = "first" if chance < 0.08 else "empty" if chance < 0.16 else "regular"
    if variant == "first":                                         # Erstauszug: Anfangssaldo ohne Datum, meist null
        opening = 0 if rng.random() < 0.7 else rng.randrange(1, 500_000)
    else:
        opening = -rng.randrange(1, 100_000) if rng.random() < 0.05 else rng.randrange(0, 5_000_000)
    count = 0 if variant == "empty" else rng.randrange(0, 11) if variant == "first" else rng.randrange(1, 30)
    days = sorted(start + timedelta(days=rng.randrange((end - start).days + 1)) for _ in range(count))
    weights = [operation[4] for operation in CASH_OPERATIONS]
    bookings: list[tuple[date, str, int, str]] = []                # Tag, Erlaeuterung, Betrag in Cent mit Vorzeichen, Art
    for day in days:
        if rng.random() < 0.05:
            bookings.append((day, rng.choice(CASH_WITHOUT_AMOUNT), 0, "")); continue
        text, sign, kind, (low, high), _weight = rng.choices(CASH_OPERATIONS, weights=weights)[0]
        bookings.append((day, text, sign * rng.randrange(low, high + 1), kind))
    closing = opening + sum(cents for _day, _text, cents, _kind in bookings)

    lines = ["Baader Bank AG", "", *_person(rng), "", "Perioden-Kontoauszug: EUR-Konto",
             f"Periodenauszugs-Nr. {rng.randrange(1, 1000):06d}", f"Kontonummer: {rng.randrange(10**9, 10**10)}",
             f"Zeitraum: {_dmy(start)} - {_dmy(end)}", "", COLUMNS]
    if variant == "regular":
        lines.append(_balance_line(start - timedelta(days=1), opening))
    elif variant == "first":
        lines.append(_balance_line(None, opening))
    else:
        lines.append("Es wurden keine Transaktionen vorgenommen.")
    for index, (day, text, cents, _kind) in enumerate(bookings, 1):
        lines.append(_booking_line(day, text, min(day + timedelta(days=rng.choice((0, 0, 0, 1, 2))), end), cents))
        lines.append(f"Vorgangs-Nr.: D{rng.randrange(10**7, 10**8)}")
        if text in SECURITY_TEXTS:
            lines.append(f"{rng.choice(('Erfundene Aktie AG', 'Muster Welt-ETF', 'Beispiel Anleihe 2029'))}"
                         f"   ISIN: DE00000{rng.randrange(10_000):04d}{rng.randrange(10)}   STK {rng.randrange(1, 400)}")
        if index % 14 == 0 and index < len(bookings):              # Seitenwechsel: pdftotext -nopgbrk reiht die Seiten aneinander
            lines += ["", f"Seite {index // 14}", "", "Baader Bank AG", COLUMNS]
    lines.append(_balance_line(end, closing))
    lines += ["", "Bitte prüfen Sie die Buchungen. Einwendungen sind innerhalb von sechs Wochen zu erheben."]

    candidates = [{"source_row_ordinal": ordinal, "local_date": day.isoformat(), "kind": kind, "amount_decimal": _plain(abs(cents)),
                   "balance_after_decimal": None, "text": text}
                  for ordinal, (day, text, cents, kind) in enumerate(bookings, 1) if cents != 0]
    if variant == "regular":       # erste Saldozeile am Tag vor dem Zeitraum, letzte an dessen Ende
        summary = {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(closing),
                   "period_from": start.isoformat(), "period_to": end.isoformat(), "closing_as_of_date": end.isoformat()}
    elif variant == "first":       # ohne Anfangsdatum beginnt der Zeitraum mit der ersten Bewegung
        summary = {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(closing),
                   "period_from": min((row["local_date"] for row in candidates), default=end.isoformat()),
                   "period_to": end.isoformat(), "closing_as_of_date": end.isoformat()}
    else:                          # ohne Transaktionen bestaetigt der Auszug nur den Saldo an einem Tag
        summary = {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(opening),
                   "period_from": end.isoformat(), "period_to": end.isoformat(), "closing_as_of_date": end.isoformat()}
    expected = {"candidates": candidates, "diagnostics": [], "summary": summary}
    content = "\n".join(lines) + "\n"
    return {"file_name": f"baader-perioden-erfunden-{seed}.txt", "content": content.encode("utf-8"), "expected": expected}


# ---------------------------------------------------------------- Ertraegnisaufstellung (Bereich income_statement)
LINE7 = "Höhe der Kapitalerträge nach Verlustverrechnung"
LINE7_NOTE = "(Zeile 7 Anlage KAP)"
SECTION_INTEREST = "Zinserträge aus Kontoguthaben"
SECTION_FOREIGN = "Laufende Erträge aus Aktien und aktienähnlichen Wertpapieren Ausland"
SECTION_DOMESTIC = "Laufende Erträge aus Aktien und aktienähnlichen Wertpapieren Inland"
SECTION_FUNDS = "Laufende Erträge aus Investmentfonds"
SECTION_SALES = "Veräußerungen im Sinne des § 20 Abs. 2 EStG"
SECTION_CREDIT = "Kreditzinsen und Kreditprovisionen"
SECTIONS = (SECTION_INTEREST, SECTION_FOREIGN, SECTION_DOMESTIC, SECTION_FUNDS, SECTION_SALES, SECTION_CREDIT)
SECTION_TOTALS = {SECTION_SALES: "Gewinne / Verluste im Sinne des § 20 Abs. 2 EStG"}
INTEREST = "Zinserträge aus Kontoguthaben"
DIVIDEND_FOREIGN = "Ausländische Dividenden und andere laufende Erträge aus Aktien"
DIVIDEND_DOMESTIC = "Inländische Dividenden und andere laufende Erträge aus Aktien"
SALE_SHARES = "Gewinn / Verlust aus Aktienveräußerungen"
SALE_OTHER = "Gewinn / Verlust aus Wertpapierveräußerungen (ohne Aktien)"
FUND_SALE = "Veräußerung von Investmentfonds: Gewinn / Verlust seit Kauf bzw. letzter fiktiven Veräußerung"
FUND_DISTRIBUTION = "Ausschüttungen von Investmentfonds"
FUND_LUMP_SUM = "Investmentfonds: Vorabpauschale"
EXEMPTION = "Abzüglich / zuzüglich Teilfreistellung"
WITHHOLDING = "Anrechenbare ausländische Quellensteuer"
CREDIT = "Sollzinsen, Verwahrentgelt"
# Art des Postens -> (Abschnitt, Gewicht). Die unklaren Arten sind Posten, deren Kapitalertrag nicht eindeutig einer Zeile zuzuordnen
# ist: Anteil an Zeile 7 weicht ab, zwei Ertragszeilen, Fonds ohne Teilfreistellung, zwei Fondszeilen.
POSTING_KINDS = {
    "interest": (SECTION_INTEREST, 6), "dividend_foreign": (SECTION_FOREIGN, 7), "dividend_domestic": (SECTION_DOMESTIC, 4),
    "fund_distribution": (SECTION_FUNDS, 4), "fund_lump_sum": (SECTION_FUNDS, 3), "unclear_no_exemption": (SECTION_FUNDS, 1),
    "unclear_two_fund_lines": (SECTION_FUNDS, 1), "sale_shares": (SECTION_SALES, 7), "sale_other": (SECTION_SALES, 3),
    "fund_sale": (SECTION_SALES, 4), "unclear_line7_differs": (SECTION_SALES, 1), "unclear_two_lines": (SECTION_SALES, 1),
    "credit": (SECTION_CREDIT, 3),
}
SHARE_NAMES = ("Erfundene Aktie AG", "Muster Maschinenbau AG", "Beispiel Pharma SE", "Fantasie Robotik Inc.", "Erfundene Energie plc",
               "Muster Logistik N.V.", "Erfundene Dividenden Inc.")
FUND_NAMES = ("Erfundener Welt-Fonds", "Muster Dividenden ETF", "Beispiel Immobilienfonds", "Fantasie Schwellenländer ETF",
              "Erfundener Mischfonds")
OTHER_NAMES = ("Erfundene Anleihe 2,500% 2029", "Muster Discount-Zertifikat", "Beispiel Optionsschein Call", "Fantasie Bonus-Zertifikat")


def _isin(rng: random.Random, country: str) -> str:
    return f"{country}00000{rng.randrange(10_000):04d}{rng.randrange(10)}"


def _quantity(rng: random.Random) -> str:
    chance = rng.random()
    if chance < 0.6:
        return str(rng.randrange(1, 1000))
    if chance < 0.9:
        return f"{rng.randrange(0, 100)},{rng.randrange(1, 10_000):04d}"
    return f"{rng.randrange(1, 10)}.{rng.randrange(0, 1000):03d}"


def _within(year: int, day: date) -> date:
    return min(max(day, date(year, 1, 1)), date(year, 12, 31))


def _taxes(rng: random.Random, base: int) -> list[tuple[str, int, str]]:
    """Einbehaltene (bei Verlust erstattete) Steuern eines Postens: Kapitalertragsteuer, Solidaritaetszuschlag, Kirchensteuer."""
    if base == 0 or rng.random() < 0.45:
        return []
    church = rng.choice((0, 0, 8, 9))
    rate = {0: 2500, 8: 2445, 9: 2451}[church]
    sign = 1 if base > 0 else -1
    tax = (abs(base) * rate + 5000) // 10000
    rows = [(f"{rate // 100},{rate % 100:02d}% Kapitalertragsteuer", sign * tax, "(Zeile 37 Anlage KAP)"),
            ("5,50% Solidaritätszuschlag", sign * ((tax * 55 + 500) // 1000), "(Zeile 38 Anlage KAP)")]
    if church:
        rows.append((f"{church},00% Kirchensteuer", sign * ((tax * church + 50) // 100), "(Zeile 39 Anlage KAP)"))
    return rows


def _fund_lines(rng: random.Random, label: str, gross: int) -> tuple[list[tuple[str, int, str]], int]:
    """Fondsertrag und Teilfreistellung mit umgekehrtem Vorzeichen; der Anteil an Zeile 7 ist die Summe."""
    rate = rng.choice((30, 30, 30, 15, 60, 80))
    exemption = -((abs(gross) * rate + 50) // 100) * (1 if gross > 0 else -1)
    return [(label, gross, ""), (f"{EXEMPTION} {rate}%", exemption, "")], gross + exemption


def _posting(rng: random.Random, kind: str, year: int, account: str, depot: str) -> dict[str, Any]:
    """Ein erfundener Posten: was die Aufstellung druckt und was der Leser daraus liefern muss (Art, Kapitalertrag, Zeile 7)."""
    day = date(year, 1, 1) + timedelta(days=rng.randrange(365))
    item: dict[str, Any] = {"kind": kind, "section": POSTING_KINDS[kind][0], "name": rng.choice(SHARE_NAMES), "kind_text": "Veräußerung",
                            "isin": None, "quantity": None, "valuta": day, "inflow": day, "depot": depot, "with_depot": True,
                            "replacement_base": False, "lines": [], "line7": None, "result": kind, "taxable": None}
    gain = rng.randrange(1, 500_000) if rng.random() < 0.65 else -rng.randrange(1, 300_000)
    if kind in ("interest", "credit"):                  # Kontozinsen zum Quartalsende, auf das Konto gebucht
        quarter = rng.randrange(4)
        end = date(year, 3 * quarter + 4, 1) - timedelta(days=1) if quarter < 3 else date(year, 12, 31)
        item.update(name=account, valuta=end, inflow=end)
    else:
        item["inflow"] = _within(year, day - timedelta(days=rng.choice((0, 0, 0, 1, 2))))
    if kind == "interest":
        amount = rng.randrange(1, 50_000)
        # Ohne Depotnummer nennt der Abschnitt der Kontozinsen nur das Konto; dann gilt es als Depot.
        item.update(kind_text="Zinszahlung Kontokorrent- / Sparkonten", with_depot=rng.random() < 0.7, lines=[(INTEREST, amount, "")],
                    line7=amount, taxable=amount)
        if not item["with_depot"]:
            item["depot"] = account
    elif kind == "credit":
        item.update(kind_text=rng.choice(("Sollzinsen / Verwahrentgelt", "Sollzinsen Kontokorrent")), lines=[(CREDIT, -rng.randrange(1, 5_000), "")],
                    result="ignored")
    elif kind in ("dividend_foreign", "dividend_domestic"):
        foreign = kind == "dividend_foreign"
        amount = rng.randrange(1, 100_000)
        item.update(kind_text="Dividendenzahlung", isin=_isin(rng, rng.choice(("US", "IE", "NL", "FR")) if foreign else "DE"),
                    quantity=_quantity(rng), lines=[(DIVIDEND_FOREIGN if foreign else DIVIDEND_DOMESTIC, amount, "")], line7=amount,
                    taxable=amount, result="dividend")
        if foreign and rng.random() < 0.5:
            item["lines"].append((WITHHOLDING, (amount * 15 + 50) // 100, "(Zeile 41 Anlage KAP)"))
    elif kind in ("fund_distribution", "fund_lump_sum", "unclear_no_exemption", "unclear_two_fund_lines"):
        amount = rng.randrange(1, 50_000)
        label = FUND_LUMP_SUM if kind == "fund_lump_sum" else FUND_DISTRIBUTION
        item.update(name=rng.choice(FUND_NAMES), kind_text="Ertragsthesaurierung" if kind == "fund_lump_sum" else "Ausschüttung",
                    isin=_isin(rng, rng.choice(("IE", "LU", "DE"))), quantity=_quantity(rng))
        if kind == "unclear_no_exemption":              # keine Teilfreistellung gedruckt: kein Fonds-, kein Aktienertrag
            item.update(lines=[(label, amount, "")], line7=amount, result="unclear")
        elif kind == "unclear_two_fund_lines":          # Ausschuettung und Vorabpauschale in einem Posten
            lump = rng.randrange(1, 20_000)
            lines, share = _fund_lines(rng, label, amount + lump)
            item.update(lines=[(label, amount, ""), (FUND_LUMP_SUM, lump, ""), lines[1]], line7=share, result="unclear")
        else:
            lines, share = _fund_lines(rng, label, amount)
            item.update(lines=lines, line7=share, taxable=share, result="fund")
    elif kind == "fund_sale":
        lines, share = _fund_lines(rng, FUND_SALE, gain)
        item.update(name=rng.choice(FUND_NAMES), isin=_isin(rng, rng.choice(("IE", "LU"))), quantity=_quantity(rng), lines=lines,
                    line7=share, taxable=share, result="fund")
    elif kind in ("sale_shares", "sale_other"):
        shares = kind == "sale_shares"
        item.update(name=rng.choice(SHARE_NAMES if shares else OTHER_NAMES), isin=_isin(rng, rng.choice(("US", "DE", "NL")) if shares else "DE"),
                    quantity=_quantity(rng), lines=[(SALE_SHARES if shares else SALE_OTHER, gain, "")], line7=gain, taxable=gain, result="sale")
        item["replacement_base"] = not shares and rng.random() < 0.3
    elif kind == "unclear_line7_differs":               # Anteil an Zeile 7 weicht vom Kapitalertrag des Postens ab
        offset = rng.choice((-1, 1)) * rng.randrange(1, 50_000)
        item.update(isin=_isin(rng, "DE"), quantity=_quantity(rng), lines=[(SALE_SHARES, gain, "")], line7=gain + offset, result="unclear")
    elif kind == "unclear_two_lines":                   # zwei Ertragszeilen in einem Posten
        other = rng.randrange(1, 100_000) * rng.choice((-1, 1))
        item.update(isin=_isin(rng, "DE"), quantity=_quantity(rng), lines=[(SALE_SHARES, gain, ""), (SALE_OTHER, other, "")],
                    line7=gain + other, result="unclear")
    if item["line7"] is not None:
        item["lines"].append((LINE7, item["line7"], LINE7_NOTE))
    item["taxes"] = _taxes(rng, item["line7"]) if kind != "credit" and item["line7"] is not None else []
    item["lines"] += item["taxes"]
    return item


def _amount_line(label: str, cents: int, note: str, gap: str) -> str:
    return f"{label}{gap}{note + ' ' if note else ''}EUR{' ' * 18}{_signed(cents)}"


def _generate_income(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    year = rng.randrange(2021, 2025)
    gap = " " * rng.randrange(8, 41)                    # Spaltenabstand wie aus pdftotext -layout, je Beleg anders
    pad = " " * 120
    account = str(rng.randrange(10**9, 10**10))
    depot = f"{rng.randrange(10**6, 10**7)}-{rng.randrange(1, 4):03d}"
    kinds = list(POSTING_KINDS)
    weights = [POSTING_KINDS[kind][1] for kind in kinds]
    drawn = [_posting(rng, kind, year, account, depot) for kind in rng.choices(kinds, weights=weights, k=rng.randrange(1, 16))]
    period = f"für den Zeitraum vom 01.01.{year} bis 31.12.{year}"
    total = sum(item["line7"] for item in drawn if item["line7"] is not None)
    current = sum(item["line7"] for item in drawn if item["line7"] is not None and item["section"] != SECTION_SALES and item["line7"] > 0)
    withheld = sum(cents for item in drawn for label, cents, _note in item["taxes"] if "Kapitalertragsteuer" in label)
    lines = ["Baader Bank AG", "", *_person(rng), "", f"{pad}Datum: {_dmy(date(year + 1, 2, rng.randrange(1, 28)))}", "",
             "Erträgnisaufstellung", "", "Sehr geehrte Kundin, sehr geehrter Kunde,",
             f"anbei erhalten Sie die Erträgnisaufstellung {period} für Ihre Konten", "",
             f"Summennachweis der Kapitalerträge {period}",
             _amount_line("Positive laufende Erträge im Sinne des § 20 Abs. 1 EStG", current, "", gap),
             _amount_line(LINE7, total, LINE7_NOTE, gap),
             _amount_line("Kapitalertragsteuer", withheld, "(Zeile 37 Anlage KAP)", gap), "",
             f"Einzelnachweis der Kapitalerträge {period}"]
    postings: list[dict[str, Any]] = []
    for section in SECTIONS:
        chosen = sorted((item for item in drawn if item["section"] == section), key=lambda item: item["valuta"])
        if not chosen:
            continue
        lines.append(section)
        for item in chosen:
            lines.append(f"{item['name']}{gap}{item['kind_text']}{gap}Transaktion:")
            lines.append(f"{pad}WWUM {rng.randrange(10**10, 10**11)}")
            if item["with_depot"]:
                lines += [f"{pad}Depotnummer:", f"{pad}{item['depot']}"]
            if item["isin"] is not None:
                lines.append(f"ISIN: {item['isin']}/EUR{gap}Nennwert/Stück{gap}STK{' ' * 20}{item['quantity']}")
            lines += [f"Valuta/steuerl. Zufluss: {_dmy(item['valuta'])} / {_dmy(item['inflow'])}", ""]
            lines += [_amount_line(label, cents, note, gap) for label, cents, note in item["lines"]]
            if item["replacement_base"]:
                lines.append("Hinweis: Ermittlung nach Ersatzbemessungsgrundlage (30% des Veräußerungserlöses)")
            lines += ["", ""]
            if len(postings) % 5 == 4:                  # Seitenwechsel zwischen zwei Posten
                lines += [f"Seite {len(postings) // 5 + 2}", f"Baader Bank AG · Erträgnisaufstellung {year}", ""]
            taxes = Decimal(0)
            for _label, cents, _note in item["taxes"]:
                taxes += _exact(cents)
            postings.append({"ordinal": len(postings) + 1, "name": item["name"], "kind_text": item["kind_text"], "section": section,
                             "amounts": {label: _exact(cents) for label, cents, _note in item["lines"]}, "isin": item["isin"],
                             "quantity": item["quantity"], "value_date": item["valuta"].isoformat(), "inflow_date": item["inflow"].isoformat(),
                             "depot": item["depot"], "fund": any(label.startswith(EXEMPTION) for label, _cents, _note in item["lines"]),
                             "replacement_base": item["replacement_base"], "taxes": taxes, "kind": item["result"],
                             "taxable": None if item["taxable"] is None else _exact(item["taxable"]),
                             "line7": None if item["line7"] is None else _exact(item["line7"])})
        if section != SECTION_CREDIT:
            share = sum(item["line7"] for item in chosen if item["line7"] is not None)
            lines += [f"Summe{gap}{section}",
                      _amount_line(SECTION_TOTALS.get(section, "Positive laufende Erträge im Sinne des § 20 Abs. 1 EStG"), share, "", gap), ""]
    lines += ["", "Diese Aufstellung wurde maschinell erstellt und ist ohne Unterschrift gültig."]
    expected = {"tax_year": year, "summary_line7": _exact(total), "postings": postings}
    return {"file_name": f"baader-ertraegnis-erfunden-{seed}.txt", "content": "\n".join(lines) + "\n", "expected": expected}


GENERATORS = {"baader_perioden_v1": _generate_perioden, "baader_income_statement_v1": _generate_income}
