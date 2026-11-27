"""Erzeuger erfundener Revolut-Kontoauszuege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Buchungen auf Girokonto ("Current") und Sparkonto ("Deposit") in einer Datei, jedes mit
eigenem Saldoverlauf - wie der Export "All accounts". Daraus baut der Erzeuger die CSV und - unabhaengig vom Leser - das erwartete
Ergebnis je Konto. Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der Leser nur sich selbst. Gleicher Startwert, gleicher
Beleg. Alle Werte sind erfunden: Beschreibungen, Kartenendungen, Betraege, Tage und Uhrzeiten; die Tage liegen in 2021-2024.

Abgedeckt: Kartenzahlung (auch mit Gebuehr), Aufladung, Erstattung, Gebuehr, Umbuchungen zwischen Girokonto und Sparkonto, Zinsen
ohne Steuer, mit Steuer (Brutto im Ergebnis) und ganz von der Steuer aufgezehrt (Hinweis statt Buchung), nicht abgeschlossene
Zeilen (PENDING, REVERTED, DECLINED), fehlendes Abschlussdatum (dann zaehlt der Start), Abschluss am Folgetag, unlesbares Datum und
fehlender Saldo (je ein Hinweis), Beschreibungen mit Komma und Anfuehrungszeichen.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import io
import random
from typing import Any

HEADER = ["Type", "Product", "Started Date", "Completed Date", "Description", "Amount", "Fee", "Currency", "State", "Balance"]
PRODUCTS = ("Current", "Deposit")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
SHOPS = ("Erfundener Laden", "Fantasie Markt", "Beispiel Cafe, Filiale 3", "Muster Kiosk", "Erfundene Buchhandlung")


def _money(value: Decimal) -> str:
    """Revolut schreibt Punkt und zwei Stellen, ohne Tausendertrennung."""
    return f"{value:.2f}"


def _plain(amount: Decimal) -> str:
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _cents(rng: random.Random, low: int, high: int) -> Decimal:
    return Decimal(rng.randrange(low, high)) / 100


def _event(rng: random.Random, product: str, when: date, balance: Decimal) -> tuple[str, str, Decimal, Decimal]:
    """Eine erfundene Buchung: (Type, Description, Amount, Fee). Abgaenge nur, solange das Guthaben reicht."""
    if product == "Deposit":
        choice = rng.random()
        if choice < 0.45:
            amount = _cents(rng, 1, 500)
            fee = rng.choice([Decimal("0"), Decimal("0"), (amount * Decimal("0.26375")).quantize(Decimal("0.01")), amount])
            fee = min(fee, amount)
            return "Interest", f'Net interest paid to "Tagesgeld" for {MONTHS[when.month - 1]} {when.day}, {when.year}', amount, fee
        if choice < 0.75 or balance < 1:
            return "Transfer", "Savings Vault topup", _cents(rng, 100, 300_000), Decimal("0")
        return "Transfer", "Savings Vault withdrawal", -_cents(rng, 1, int(balance * 100) + 1), Decimal("0")
    choice = rng.random()
    if choice < 0.25 or balance < 50:
        return "Deposit", f"Top-up by *{rng.randrange(1000, 10000)}", _cents(rng, 1000, 200_000), Decimal("0")
    if choice < 0.55:
        fee = _cents(rng, 1, 200) if rng.random() < 0.2 else Decimal("0")
        return "Card Payment", rng.choice(SHOPS), -_cents(rng, 1, min(int(balance * 100) // 2, 40_000) + 2), fee
    if choice < 0.65:
        return "Card Refund", rng.choice(SHOPS), _cents(rng, 1, 10_000), Decimal("0")
    if choice < 0.72:
        return "Fee", "Erfundene Kontogebuehr", -_cents(rng, 1, 1_000), Decimal("0")
    if choice < 0.86:
        return "Transfer", "To EUR Savings", -_cents(rng, 1, int(balance * 100) // 2 + 2), Decimal("0")
    return "Transfer", "From EUR Savings", _cents(rng, 100, 50_000), Decimal("0")


def _document(seed: int) -> dict[str, Any]:
    """Ein erfundener Export mit beiden Konten und die Erwartung je Konto (Leser revolut_current_v1 und revolut_savings_v1)."""
    rng = random.Random(seed)
    moment = datetime(2021, 1, 1, 8, 0, 0) + timedelta(days=rng.randrange(0, 365 * 3), seconds=rng.randrange(0, 36_000))
    balance = {"Current": _cents(rng, 0, 500_000), "Deposit": _cents(rng, 0, 2_000_000)}
    rows: list[list[str]] = []
    expected = {product: {"candidates": [], "diagnostics": [], "opening": None} for product in PRODUCTS}

    def add(product: str, kind: str, description: str, amount: Decimal, fee: Decimal, special: str) -> None:
        nonlocal moment
        ordinal = len(rows) + 1
        started = moment
        completed = started + timedelta(seconds=rng.randrange(1, 600) if rng.random() < 0.85 else rng.randrange(3_600, 2 * 86_400))
        target = expected[product]
        state, completed_text, balance_text = "COMPLETED", completed.strftime("%Y-%m-%d %H:%M:%S"), ""
        if special in ("PENDING", "REVERTED", "DECLINED"):
            # Nicht abgeschlossen: kein Saldo, bei PENDING auch kein Abschluss. Bewegt nichts.
            state = special
            completed_text = "" if special == "PENDING" else completed_text
            target["diagnostics"].append({"source_row_ordinal": ordinal, "reason_code": "row_not_completed"})
        else:
            cash = amount - fee
            balance[product] += cash
            balance_text = _money(balance[product])
            local_day = completed.date()
            if special == "no_completed":     # ohne Abschlussdatum zaehlt der Start
                completed_text, local_day = "", started.date()
            if special == "date_invalid":
                completed_text = "erfunden"
                target["diagnostics"].append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"})
            elif special == "no_balance":
                balance_text = ""
                target["diagnostics"].append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"})
            elif cash == 0:
                # Zins, den die Steuer ganz aufzehrt: auf dem Konto bewegt sich nichts.
                target["diagnostics"].append({"source_row_ordinal": ordinal, "reason_code": "interest_fully_taxed",
                                              "gross_income_decimal": _plain(amount)})
            else:
                if target["opening"] is None:
                    target["opening"] = balance[product] - cash
                interest = kind == "Interest" and amount > 0
                candidate = {"source_row_ordinal": ordinal, "local_date": local_day.isoformat(),
                             "kind": "interest" if interest else ("deposit" if cash > 0 else "withdrawal"),
                             "amount_decimal": _plain(abs(cash)), "balance_after_decimal": _plain(balance[product]),
                             "text": " ".join(part for part in (kind, description) if part)}
                if interest and fee != 0:
                    candidate["gross_income_decimal"] = _plain(amount)
                target["candidates"].append(candidate)
        rows.append([kind, product, started.strftime("%Y-%m-%d %H:%M:%S"), completed_text, description, _money(amount), _money(fee),
                     "EUR", state, balance_text])
        moment = max(moment, completed) + timedelta(seconds=rng.randrange(60, 6 * 86_400))

    for _ in range(rng.randrange(2, 30)):
        product = "Current" if rng.random() < 0.55 else "Deposit"
        kind, description, amount, fee = _event(rng, product, moment.date(), balance[product])
        if rng.random() < 0.1:
            description = ""   # Revolut laesst die Beschreibung mitunter leer
        roll = rng.random()
        special = ("PENDING" if roll < 0.04 else "REVERTED" if roll < 0.06 else "DECLINED" if roll < 0.08 else
                   "no_completed" if roll < 0.10 else "date_invalid" if roll < 0.12 else "no_balance" if roll < 0.14 else "")
        add(product, kind, description, amount, fee, special)
    # Jedes Konto braucht mindestens eine Bewegung; sonst ist der Export fuer diesen Leser kein Beleg.
    for product in PRODUCTS:
        if not expected[product]["candidates"]:
            kind, description = ("Deposit", "Top-up by *4711") if product == "Current" else ("Transfer", "Savings Vault topup")
            add(product, kind, description, _cents(rng, 100, 100_000), Decimal("0"), "")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    results = {}
    for product, target in expected.items():
        days = sorted(row["local_date"] for row in target["candidates"])
        results[product] = {"candidates": target["candidates"], "diagnostics": target["diagnostics"],
                            "summary": {"opening_balance_decimal": _plain(target["opening"]),
                                        "closing_balance_decimal": target["candidates"][-1]["balance_after_decimal"],
                                        "period_from": days[0], "period_to": days[-1]}}
    return {"content": buffer.getvalue().encode("utf-8"), "expected": results}


def _current(seed: int) -> dict[str, Any]:
    made = _document(seed)
    return {"file_name": f"revolut-erfunden-{seed}.csv", "content": made["content"], "expected": made["expected"]["Current"]}


def _savings(seed: int) -> dict[str, Any]:
    made = _document(seed)
    return {"file_name": f"revolut-erfunden-{seed}.csv", "content": made["content"], "expected": made["expected"]["Deposit"]}


GENERATORS = {"revolut_current_v1": _current, "revolut_savings_v1": _savings}
