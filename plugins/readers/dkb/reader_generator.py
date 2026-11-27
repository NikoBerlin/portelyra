"""Erzeuger erfundener DKB-Belege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Buchungen samt Salden; daraus baut der Erzeuger den Beleg im Format des Instituts und -
unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der Leser nur sich selbst.
Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Namen, Kontonummern, IBAN, Verwendungszwecke, Betraege, Tage; die Tage
liegen in 2021-2024.

- Kontoauszug (Text, wie pdftotext ihn liefert): alte Vorlage (Tag ohne Jahr, Spalten Belastung und Gutschrift, Salden mit H/S,
  auch ueber den Jahreswechsel; Gutschriften mal rechts, mal knapp links der Spaltenueberschrift - die Saldokette entscheidet) und
  neue Vorlage (volles Datum, Soll mit Minus, Kontostand am Vortag und am Ende); Zinsen, Sollzinsen, Folgezeilen, Buchungen ueber
  0,00, Gutschrift in der Soll-Spalte (Hinweis), Seitenumbruch, Auszug ohne Bewegung (nur Salden).
- Umsatzliste (CSV): Vorspann mit Zeitraum und Kontostand; Ein- und Ausgaenge, Quartalsabrechnungen mit Bruttozins und
  "Kontostand am" (auch am Folgetag gebucht, auch ueber 0,00), Zeitraum eines Vorjahres (Kontostand vom Exporttag zaehlt dann
  nicht), vorgemerkte Zeilen ohne Buchungstag, unlesbares Datum oder fehlender Betrag (Hinweis), fehlende Zeile (Stuetzpunkt geht
  nicht auf), kurze Betraege ("-2.000", "12,5"), lange Verwendungszwecke (auf 120 Zeichen gekuerzt), mehrfacher Leerraum.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import random
from typing import Any

NAMES = ("Erika Erfunden", "Max Beispiel", "Invented Owner", "Petra Fantasie", "Jonas Muster")
FIRMS = ("Erfundener Versorger", "Fantasie Markt", "Beispiel Versicherung", "Muster Miete GbR", "Erfundene Firma", "Online Shop Erfunden")
CENT = Decimal("0.01")


def _plain(amount: Decimal) -> str:
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _german(amount: Decimal, compact: bool = False) -> str:
    """1234.5 -> "1.234,50" (oder kurz "1.234,5", ganze Euro "2.000"), negativ mit Minus vorn."""
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount):.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:]); whole = whole[:-3]
    groups.insert(0, whole)
    if compact:
        cents = cents.rstrip("0")
    return f"{sign}{'.'.join(groups)}" + (f",{cents}" if cents else "")


def _cents(rng: random.Random, low: int, high: int) -> Decimal:
    return Decimal(rng.randrange(low, high)) / 100


def _right(prefix: str, amount: str, end: int) -> str:
    """Betrag rechtsbuendig bis zur Spalte ``end`` wie im Layout von pdftotext."""
    return prefix + " " * max(1, end - len(amount) - len(prefix)) + amount


# ---------------------------------------------------------------- Kontoauszug (Text)
OLD_HEADER = " Bu.Tag         Wert          Wir haben für Sie gebucht                                   Belastung in EUR   Gutschrift in EUR"
NEW_HEADER = "Datum       Erläuterung                                           Betrag Soll EUR   Betrag Haben EUR"
# (Text, Vorzeichen); Zinsen erkennt der Leser an "zinsen" usw., aber nur bei Gutschriften.
STATEMENT_TEXTS = (
    ("Zahlungseingang", 1), ("Gutschrift", 1), ("Habenzinsen", 1), ("Zinsertrag", 1), ("Zinsgutschrift", 1), ("Abschluss", 1),
    ("Lastschrift", -1), ("Kartenzahlung", -1), ("Überweisung", -1), ("Dauerauftrag", -1), ("Bargeldauszahlung", -1),
    ("Sollzinsen", -1), ("Kapitalertragsteuer", -1),
)
INTEREST = ("zinsen", "zinsertrag", "zinsgutschrift", "habenzinsen")


def _statement_bookings(rng: random.Random, first: date, last: date, new: bool) -> list[dict[str, Any]]:
    bookings = []
    count = 0 if rng.random() < 0.06 else rng.randrange(1, 22)   # ein Auszug ohne Bewegung traegt nur die Salden
    days = sorted(first + timedelta(days=rng.randrange(0, (last - first).days + 1)) for _ in range(count))
    for day in days:
        text, sign = rng.choice(STATEMENT_TEXTS)
        if text in ("Lastschrift", "Kartenzahlung", "Überweisung", "Dauerauftrag", "Zahlungseingang", "Gutschrift") and (new or rng.random() < 0.5):
            text = f"{text} {rng.choice(FIRMS if sign < 0 else NAMES)}"
        amount = (_cents(rng, 1, 5_000_000) if rng.random() < 0.1 else _cents(rng, 1, 250_000)) * sign
        roll = rng.random()
        special = "zero" if roll < 0.04 else ("wrong_column" if new and sign > 0 and roll < 0.10 else "")
        if special == "zero":
            amount = Decimal("0")
        follow = [] if rng.random() < 0.5 else [rng.choice(("Erfundener Verwendungszweck", "Rechnung 0815 Erfunden", "Mandat ERF-0001"))]
        bookings.append({"day": day, "text": text, "amount": amount, "special": special, "follow": follow})
    return bookings


def _old_statement(rng: random.Random) -> dict[str, Any]:
    start = date(2021, 1, 1) + timedelta(days=rng.randrange(0, 880))
    end = start + timedelta(days=rng.randrange(27, 35))
    opening = _cents(rng, -50_000, 2_000_000)
    bookings = _statement_bookings(rng, start, end, new=False)
    closing = opening + sum((item["amount"] for item in bookings), Decimal("0"))
    debit_end = OLD_HEADER.find("Belastung in EUR") + len("Belastung in EUR") - rng.randrange(0, 2)
    # Gutschriften enden je Beleg rechts der Ueberschrift oder knapp links davon (#467); die Saldokette entscheidet dann.
    credit_column = OLD_HEADER.find("Gutschrift in EUR")
    credit_end = rng.choice((credit_column + 17, credit_column + 18, credit_column + 18, credit_column - 1, credit_column - 2))
    balance = lambda label, value: f"{label} KONTOSTAND{' ' * 36}{_german(abs(value))} {'S' if value < 0 else 'H'} EUR"
    lines = ["Deutsche Kreditbank, Erfundene Straße 1, 00000 Berlin", "", rng.choice(NAMES), "", "DKB-Cash", "",
             f"Kontoauszug Nummer {rng.randrange(1, 13):03d} / {end.year} vom {start:%d.%m.%Y} bis {end:%d.%m.%Y}",
             f"Kontonummer {rng.randrange(10**9, 10**10)} / IBAN DE00 {rng.randrange(1000, 10000)} {rng.randrange(1000, 10000)} "
             f"{rng.randrange(1000, 10000)} {rng.randrange(1000, 10000)} {rng.randrange(10, 100)}",
             OLD_HEADER, ""]
    opening_first = rng.random() < 0.6
    if opening_first:
        lines.append(balance("ALTER", opening))
    candidates = []
    for index, item in enumerate(bookings):
        if index and rng.random() < 0.05:   # Seitenumbruch: Kopf wiederholt
            lines.extend(["", "Blatt 2", OLD_HEADER, ""])
        value_day = item["day"] + timedelta(days=rng.choice((0, 0, 0, 1, 2)))
        end_column = credit_end if item["amount"] >= 0 else debit_end
        lines.append(_right(f" {item['day']:%d.%m.}        {value_day:%d.%m.}        {item['text']}", _german(abs(item["amount"])), end_column))
        lines.extend(f"{' ' * 29}{line}" for line in item["follow"])
        if item["amount"] != 0:
            interest = item["amount"] > 0 and any(marker in item["text"].lower() for marker in INTEREST)
            candidates.append({"source_row_ordinal": len(candidates) + 1, "local_date": item["day"].isoformat(),
                               "kind": "interest" if interest else ("deposit" if item["amount"] > 0 else "withdrawal"),
                               "amount_decimal": _plain(abs(item["amount"])), "balance_after_decimal": None, "text": item["text"]})
    if not opening_first:
        lines.append(balance("ALTER", opening))
    lines.append(balance("NEUER", closing))
    expected = {"candidates": candidates, "diagnostics": [],
                "summary": {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(closing),
                            "period_from": start.isoformat(), "period_to": end.isoformat(), "closing_as_of_date": end.isoformat()}}
    return {"lines": lines, "expected": expected}


def _new_statement(rng: random.Random) -> dict[str, Any]:
    before = date(2023, 6, 1) + timedelta(days=rng.randrange(0, 540))   # Kontostand am Ende des Vorauszugs
    end = before + timedelta(days=rng.randrange(27, 34))
    first = before + timedelta(days=1)
    opening = _cents(rng, -50_000, 2_000_000)
    bookings = _statement_bookings(rng, first, end, new=True)
    closing = opening + sum((item["amount"] for item in bookings), Decimal("0"))
    credit_column = NEW_HEADER.find("Betrag Haben EUR")
    debit_end, credit_end = NEW_HEADER.find("Betrag Soll EUR") + len("Betrag Soll EUR"), credit_column + len("Betrag Haben EUR")
    number = rng.randrange(2, 13)
    lines = ["Deutsche Kreditbank AG", rng.choice(NAMES), "", f"Kontoauszug {number}/{end.year}{' ' * 40}Seite 1 von 1",
             f"IBAN DE00 {rng.randrange(1000, 10000)} {rng.randrange(1000, 10000)} {rng.randrange(1000, 10000)} {rng.randrange(1000, 10000)} {rng.randrange(10, 100)}"]
    if rng.random() < 0.5:   # manche Auszuege nennen den Zeitraum zusaetzlich im Kopf
        lines.append(f"Kontoauszug Nummer {number:03d} / {end.year} vom {first:%d.%m.%Y} bis {end:%d.%m.%Y}")
    lines += ["", NEW_HEADER, _right(f"{' ' * 12}Kontostand am {before:%d.%m.%Y}, Auszug Nr. {number - 1}", _german(opening), credit_end)]
    candidates, diagnostics = [], []
    for item in bookings:
        amount = item["amount"]
        # Soll mit Minus in der Soll-Spalte, Haben in der Haben-Spalte; eine Gutschrift in der Soll-Spalte wird gemeldet.
        end_column = debit_end if amount < 0 or item["special"] == "wrong_column" else credit_end
        lines.append(_right(f"{item['day']:%d.%m.%Y}  {item['text']}", _german(amount), end_column))
        lines.extend(f"{' ' * 12}{line}" for line in item["follow"])
        if item["special"] == "wrong_column":
            diagnostics.append({"source_row_ordinal": len(candidates) + 1, "reason_code": "column_sign_mismatch"})
        elif amount != 0:
            interest = amount > 0 and any(marker in item["text"].lower() for marker in INTEREST)
            candidates.append({"source_row_ordinal": len(candidates) + 1, "local_date": item["day"].isoformat(),
                               "kind": "interest" if interest else ("deposit" if amount > 0 else "withdrawal"),
                               "amount_decimal": _plain(abs(amount)), "balance_after_decimal": None, "text": item["text"]})
    lines.append(_right(f"{' ' * 12}Kontostand am {end:%d.%m.%Y} um {rng.randrange(0, 24):02d}:{rng.randrange(0, 60):02d} Uhr",
                        _german(closing), credit_end))
    expected = {"candidates": candidates, "diagnostics": diagnostics,
                "summary": {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(closing),
                            "period_from": first.isoformat(), "period_to": end.isoformat(), "closing_as_of_date": end.isoformat()}}
    return {"lines": lines, "expected": expected}


def _kontoauszug(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    made = _new_statement(rng) if rng.random() < 0.5 else _old_statement(rng)
    return {"file_name": f"dkb-kontoauszug-erfunden-{seed}.txt", "content": ("\n".join(made["lines"]) + "\n").encode("utf-8"),
            "expected": made["expected"]}


# ---------------------------------------------------------------- Umsatzliste (CSV)
CSV_HEADER = ["Buchungsdatum", "Wertstellung", "Status", "Zahlungspflichtige*r", "Zahlungsempfänger*in", "Verwendungszweck", "Umsatztyp",
              "IBAN", "Betrag (€)", "Gläubiger-ID", "Mandatsreferenz", "Kundenreferenz"]
# Verwendungszwecke je Richtung (Eingang, Ausgang); mehrfacher Leerraum wie im Export.
PURPOSES = {1: ("Umbuchung", "Erstattung Erfunden", "Gehalt Fantasie GmbH", "Gutschrift  Erfundene Firma  Bonus"),
            -1: ("Erfundene Rechnung 2023-0815", "Miete Erfundene Wohnung", "Umbuchung", "Einkauf  Fantasie Markt  Filiale 12",
                 "Beitrag Erfundener Verein")}


def _quoted(row: list[str]) -> str:
    return ";".join('"' + value.replace('"', '""') + '"' for value in row)


def _umsatzliste(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    owner = rng.choice(NAMES)
    compact = rng.random() < 0.6          # DKB schreibt Betraege kurz: "-2.000", "12,5"
    current = rng.random() < 0.7          # sonst Zeitraum eines Vorjahres, exportiert im Folgejahr
    if current:
        period_to = date(2021, 6, 1) + timedelta(days=rng.randrange(0, 1300))
        period_from = max(date(2021, 1, 1), period_to - timedelta(days=rng.randrange(20, 400)))
        export_day = period_to
    else:
        year = rng.randrange(2021, 2024)
        period_from, period_to = date(year, 1, 1), date(year, 12, 31)
        export_day = date(year + 1, 1, 1) + timedelta(days=rng.randrange(0, 300))
    span = (period_to - period_from).days
    opening = _cents(rng, 0, 3_000_000)
    # Wahre Bewegungen: (Tag, Betrag, Zeile); die Abrechnungen tragen den Stuetzpunkt "Kontostand am".
    events: list[dict[str, Any]] = []
    for _ in range(rng.randrange(1, 25)):
        day = period_from + timedelta(days=rng.randrange(0, span + 1))
        sign = rng.choice((1, -1))
        amount = (Decimal(rng.randrange(1, 60)) * 100 if rng.random() < 0.15 else _cents(rng, 1, 400_000)) * sign
        purpose = rng.choice(PURPOSES[sign])
        if rng.random() < 0.1:
            purpose = " ".join([purpose] + [f"Erfundene Angabe {rng.randrange(10**5, 10**6)}" for _ in range(rng.randrange(4, 9))])
        party = rng.choice(tuple(name for name in FIRMS + NAMES if name != owner))
        events.append({"day": day, "amount": amount, "purpose": purpose,
                       "payer": party if sign > 0 else owner, "payee": owner if sign > 0 else party, "settlement": None})
    tagesgeld = rng.random() < 0.6
    if tagesgeld or rng.random() < 0.3:
        for year in range(period_from.year - 1, period_to.year + 1):
            for month, last in ((3, 31), (6, 30), (9, 30), (12, 31)):
                as_of = date(year, month, last)
                carrier = as_of + timedelta(days=rng.choice((0, 0, 1)))
                if not period_from <= carrier <= period_to:
                    continue
                gross = Decimal("0") if rng.random() < 0.1 else _cents(rng, 1, 6_000)
                tax = Decimal("0") if rng.random() < 0.4 else (gross * Decimal("0.25")).quantize(CENT)
                soli = (tax * Decimal("0.055")).quantize(CENT)
                events.append({"day": carrier, "amount": gross - tax - soli, "payer": "DKB AG", "payee": owner,
                               "settlement": {"as_of": as_of, "gross": gross, "tax": tax, "soli": soli,
                                              "start": date(year, month - 2, 1)}})
    events.sort(key=lambda item: (item["day"], rng.random()), reverse=True)   # neueste zuerst, wie die DKB
    # Eine fehlende Zeile: die Salden des Belegs kennen sie, die Liste nicht (Stuetzpunkte gehen dann nicht auf).
    regular = [index for index, item in enumerate(events) if item["settlement"] is None]
    omitted = rng.choice(regular) if len(regular) > 1 and rng.random() < 0.12 else None
    true_balance = lambda day, carrier: opening + sum((item["amount"] for item in events if item["day"] <= day and item is not carrier),
                                                      Decimal("0"))
    rows: list[list[str]] = []
    candidates, diagnostics, checkpoints, listed = [], [], [], []
    for _ in range(rng.choice((0, 0, 0, 1, 2))):   # vorgemerkt, noch ohne Buchungstag: wird uebergangen
        rows.append(["", (period_to - timedelta(days=rng.randrange(0, 3))).strftime("%d.%m.%y"), "Vorgemerkt", owner, rng.choice(FIRMS),
                     "Erfundene Vormerkung", "Ausgang", "", _german(-_cents(rng, 100, 20_000), compact), "", "", ""])
    for index, item in enumerate(events):
        if index == omitted:
            continue
        if rng.random() < 0.04:            # unlesbare Zeile mit Hinweis; sie bewegt nichts
            bad_date = rng.random() < 0.5
            rows.append(["31.02." + item["day"].strftime("%y") if bad_date else item["day"].strftime("%d.%m.%y"), "", "Gebucht",
                         owner, rng.choice(FIRMS), "Erfundene Stornozeile", "Ausgang", "", "" if not bad_date else "-1", "", "", ""])
            diagnostics.append({"source_row_ordinal": len(rows), "reason_code": "date_invalid" if bad_date else "amount_invalid"})
        amount, purpose = item["amount"], item.get("purpose", "")
        settlement = item["settlement"]
        if settlement is not None:
            balance = true_balance(settlement["as_of"], item)
            purpose = (f"Abrechnungszeitraum vom {settlement['start']:%d.%m.%Y} bis {settlement['as_of']:%d.%m.%Y} "
                       f"Zinsen für Guthaben {_german(settlement['gross'])}+ Abgeltungsteuer {_german(settlement['tax'])}- "
                       f"Solidaritätszuschlag {_german(settlement['soli'])}- "
                       f"Kontostand am {settlement['as_of']:%d.%m.%Y} {_german(abs(balance))} {'-' if balance < 0 else '+'}")
            checkpoints.append({"as_of": settlement["as_of"], "carrier": item})
        value_day = item["day"] + timedelta(days=rng.choice((0, 0, 0, 1)))
        rows.append([item["day"].strftime("%d.%m.%y"), value_day.strftime("%d.%m.%y"), "Gebucht", item["payer"], item["payee"], purpose,
                     "Eingang" if amount >= 0 else "Ausgang", "" if settlement else f"DE00{rng.randrange(10**17, 10**18)}",
                     _german(amount, compact), "", "", ""])
        if amount == 0:
            continue
        listed.append(item)
        collapsed = " ".join(purpose.split())
        counterparty = item["payee"] if amount < 0 else item["payer"]
        candidate = {"source_row_ordinal": len(rows), "local_date": item["day"].isoformat(),
                     "kind": "interest" if amount > 0 and settlement is not None else ("deposit" if amount > 0 else "withdrawal"),
                     "amount_decimal": _plain(abs(amount)), "balance_after_decimal": None,
                     "text": " ".join(part for part in (counterparty, collapsed[:120]) if part)}
        if candidate["kind"] == "interest" and settlement["gross"] != amount:
            candidate["gross_income_decimal"] = _plain(settlement["gross"])
        candidates.append(candidate)
    # Anfangssaldo, wie er sich aus dem Beleg ergibt: aus dem Kontostand am Exporttag, wenn der Zeitraum bis dahin reicht, sonst aus
    # dem letzten Stuetzpunkt der Liste. Fehlt eine Zeile, verschiebt er sich um ihren Betrag, soweit der Anker sie schon enthaelt.
    missing = lambda day: events[omitted]["amount"] if omitted is not None and events[omitted]["day"] <= day else Decimal("0")
    closing_true = opening + sum((item["amount"] for item in events), Decimal("0"))
    others = list(checkpoints)
    if current:
        derived = opening + (events[omitted]["amount"] if omitted is not None else Decimal("0"))
    elif checkpoints:
        derived = opening + missing(checkpoints[-1]["as_of"])
        others = checkpoints[:-1]
    else:
        derived, others = None, []
    proven = derived is not None
    for point in others:
        if opening + missing(point["as_of"]) != derived:
            proven = False
            diagnostics.append({"source_row_ordinal": 0, "reason_code": "balance_checkpoint_mismatch", "as_of_date": point["as_of"].isoformat()})
    anchors = (1 + len(others)) if derived is not None else 0
    export_balance = closing_true if current else _cents(rng, 0, 3_000_000)
    lines = [_quoted(["Tagesgeld" if tagesgeld else "Girokonto", f"DE00{rng.randrange(10**17, 10**18)}"]),
             _quoted(["Zeitraum:", f"{period_from:%d.%m.%Y} - {period_to:%d.%m.%Y}"]),
             _quoted([f"Kontostand vom {export_day:%d.%m.%Y}:", f"{_german(export_balance, compact)} €"]), '""', _quoted(CSV_HEADER)]
    lines += [_quoted(row) for row in rows]
    expected = {"candidates": candidates, "diagnostics": diagnostics,
                "balance_proof": proven and anchors >= 2, "balance_anchor_only": proven and anchors == 1,
                "summary": {"opening_balance_decimal": None if derived is None else _plain(derived),
                            "closing_balance_decimal": None if derived is None else _plain(derived + sum((item["amount"] for item in listed), Decimal("0"))),
                            "period_from": period_from.isoformat(), "period_to": period_to.isoformat()}}
    return {"file_name": f"dkb-umsatzliste-erfunden-{seed}.csv", "content": ("﻿" + "\n".join(lines) + "\n").encode("utf-8"),
            "expected": expected}


GENERATORS = {"dkb_kontoauszug_v1": _kontoauszug, "dkb_umsatzliste_v1": _umsatzliste}
