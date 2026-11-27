"""Erzeuger der Vorlage fuer den Selbsttest (Stufe 3).

Aus dem Startwert entstehen erfundene Buchungen; daraus baut der Erzeuger den Beleg und - unabhaengig vom Leser - das erwartete
Ergebnis. Den Leser ruft er nie auf. Gleicher Startwert, gleicher Beleg. Tage in der Vergangenheit (2021-2024), alle Werte erfunden.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import random
from typing import Any

TEXTS = ("Zinsgutschrift", "Einzahlung Erfunden", "Auszahlung Erfunden", "Überweisung an Erfundene GmbH")


def _german(amount: Decimal) -> str:
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount):.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:]); whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}{'.'.join(groups)},{cents}"


def _plain(amount: Decimal) -> str:
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _generate(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    day = date(2021, 1, 1) + timedelta(days=rng.randrange(0, 365 * 3))
    lines, candidates, diagnostics = ["Datum;Betrag;Text"], [], []
    for ordinal in range(1, rng.randrange(2, 20) + 1):
        day += timedelta(days=rng.randrange(0, 10))
        text = rng.choice(TEXTS)
        sign = 1 if text.startswith(("Zins", "Einzahlung")) else -1
        amount = Decimal(rng.randrange(1, 500_000)) / 100 * sign
        if rng.random() < 0.08:   # ein unlesbares Datum: Hinweis statt Bewegung
            lines.append(f"erfunden;{_german(amount)};{text}")
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"})
            continue
        lines.append(f"{day.strftime('%d.%m.%Y')};{_german(amount)};{text}")
        interest = amount > 0 and "zins" in text.lower()
        candidates.append({"source_row_ordinal": ordinal, "local_date": day.isoformat(),
                           "kind": "interest" if interest else ("deposit" if amount > 0 else "withdrawal"),
                           "amount_decimal": _plain(abs(amount)), "balance_after_decimal": None, "text": text})
    if not candidates:
        day += timedelta(days=1)
        lines.append(f"{day.strftime('%d.%m.%Y')};0,01;Zinsgutschrift")
        candidates.append({"source_row_ordinal": len(lines) - 1, "local_date": day.isoformat(), "kind": "interest", "amount_decimal": "0.01",
                           "balance_after_decimal": None, "text": "Zinsgutschrift"})
    days = sorted(row["local_date"] for row in candidates)
    return {"file_name": f"vorlage-{seed}.csv", "content": ("\n".join(lines) + "\n").encode("utf-8"),
            "expected": {"candidates": candidates, "diagnostics": diagnostics,
                         "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}}


GENERATORS = {"vorlage_csv_v1": _generate}
