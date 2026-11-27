"""Erzeuger erfundener C24-Exporte fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Referenz fuer alle Erzeuger: Aus einem Startwert entstehen erfundene Buchungen; aus ihnen baut der Erzeuger den Beleg im Format
des Instituts und - unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der
Leser nur sich selbst. Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Namen, Kontonummern, Betraege, Tage.

Die Tage liegen in der Vergangenheit (2021-2024), damit der Beleg auch die Regel "kein Buchungstag nach heute" erfuellt, wenn der
Selbsttest vor einer Installation mit dem Datum des Rechners laeuft.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import random
from typing import Any

HEADER = ["Transaktionstyp", "Buchungsdatum", "Karteneinsatz", "Betrag", "Zahlungsempfänger", "IBAN", "BIC", "Verwendungszweck",
          "Beschreibung", "Kontonummer", "Kontoname", "Kategorie", "Unterkategorie", "Bargeldabhebung"]
# (Transaktionstyp, Zahlungsempfaenger, Verwendungszweck, Kategorie, Unterkategorie, Vorzeichen)
KINDS = (
    ("Zinszahlung", "C24 Bank", "", "Einkommen", "Kapitalerträge", 1),
    ("Pocket-Umbuchung", "C24 Smartkonto", "Umbuchung", "Umbuchung", "Umbuchung", 1),
    ("Pocket-Umbuchung", "C24 Smartkonto", "Umbuchung", "Umbuchung", "Umbuchung", -1),
    ("Überweisung", "Erfundene Empfängerin", "Erfundener Zweck", "Sonstiges", "Sonstiges", -1),
    ("Gutschrift", "Erfundener Absender", "Erfundene Erstattung", "Einkommen", "Sonstiges", 1),
)


def _german(amount: Decimal) -> str:
    """1200.43 -> "1.200,43 €", negativ mit Minus vorn - wie der C24-Export."""
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount):.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:]); whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}{'.'.join(groups)},{cents} €"


def _plain(amount: Decimal) -> str:
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _generate(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    start = date(2021, 1, 1) + timedelta(days=rng.randrange(0, 365 * 3))
    account_number = f"99{rng.randrange(10**7, 10**8)}"
    account_name = rng.choice(["Tagesgeld", "Smartkonto", "Pocket Erfunden"])
    rows: list[list[str]] = []
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    day = start
    for ordinal in range(1, rng.randrange(3, 25) + 1):
        day += timedelta(days=rng.randrange(0, 12))
        kind_text, payee, purpose, category, subcategory, sign = rng.choice(KINDS)
        amount = Decimal(rng.randrange(1, 300_000)) / 100 * sign
        special = rng.random()
        booking_day = day.strftime("%d.%m.%Y")
        if special < 0.05:                     # Buchung ohne Betrag (C24 fuehrt sie): wird uebergangen
            amount = Decimal("0")
        elif special < 0.10:                   # unlesbares Datum: ein Hinweis statt einer Bewegung
            booking_day = "erfunden"
        rows.append([kind_text, booking_day, "", _german(amount), payee, "", "", purpose, "", account_number, account_name, category, subcategory, ""])
        if booking_day == "erfunden":
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        if amount == 0:
            continue
        interest = amount > 0 and ("zinszahlung" in kind_text.lower() or (category.lower() == "einkommen" and "kapitalertr" in subcategory.lower()))
        text = " ".join(part for part in (kind_text, payee, purpose) if part).strip()
        candidates.append({"source_row_ordinal": ordinal, "local_date": day.isoformat(),
                           "kind": "interest" if interest else ("deposit" if amount > 0 else "withdrawal"),
                           "amount_decimal": _plain(abs(amount)), "balance_after_decimal": None, "text": text})
    if not candidates:   # mindestens eine Bewegung: sonst ist der Export kein Beleg dieses Formats
        day += timedelta(days=1)
        rows.append(["Zinszahlung", day.strftime("%d.%m.%Y"), "", _german(Decimal("0.01")), "C24 Bank", "", "", "", "", account_number,
                     account_name, "Einkommen", "Kapitalerträge", ""])
        candidates.append({"source_row_ordinal": len(rows), "local_date": day.isoformat(), "kind": "interest", "amount_decimal": "0.01",
                           "balance_after_decimal": None, "text": "Zinszahlung C24 Bank"})
    lines = [";".join(HEADER)] + [";".join(row) for row in rows]
    days = sorted(row["local_date"] for row in candidates)
    expected = {"candidates": candidates, "diagnostics": diagnostics,
                "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}
    return {"file_name": f"c24-erfunden-{seed}.csv", "content": ("﻿" + "\n".join(lines) + "\n").encode("utf-8"), "expected": expected}


GENERATORS = {"c24_transactions_v1": _generate}
