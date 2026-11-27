"""Portelyra-Leser revolut: Cash-Belege (statement_reader_v1, Aufruf read).

Erzeugt aus dem bisherigen Kernmodul (rc.372) ohne Aenderung der Leselogik. Der Leser bekommt Dateiinhalt und
Dateinamen und liefert Kandidaten; er liest keine anderen Dateien, hat kein Netz und schreibt nichts.
"""
from __future__ import annotations

from datetime import date
from datetime import datetime
from decimal import Decimal
from typing import Any

from portelyra_reader_sdk_v1 import (
    CENT,
    ReaderError as CashStatementImportV1Error,
    abort as _abort,
    cents as _cents,
    english_amount as _english_amount,
    named_rows as _named_rows,
    plain as _plain,
)


# Revolut fuehrt Girokonto ("Current") und Sparkonto ("Deposit") in einer Datei, jedes
# mit eigenem Saldoverlauf. Bei Zinsen ist "Amount" der Bruttozins und "Fee" die gleich
# einbehaltene Steuer; auf dem Konto landet die Differenz (Festlegung 19.09.2026).
REVOLUT_COLUMNS = ("Type", "Product", "Completed Date", "Amount", "Fee", "Balance")

def _parse_revolut(source: bytes, file_name: str, product: str) -> dict[str, Any]:
    try:
        rows = _named_rows(source)
    except AttributeError:
        # Eine Zeile mit mehr Feldern als die Kopfzeile (Selbsttest rc.379: eingeschobene Fremdzeile) traegt im SDK eine Liste
        # statt eines Textes. Der Export ist dann beschaedigt und wird mit Grund abgewiesen statt abzustuerzen.
        _abort("cash_statement_source_invalid")
    if not rows or any(column not in rows[0] for column in REVOLUT_COLUMNS):
        _abort("cash_statement_header_invalid")
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    opening = None
    for ordinal, row in enumerate(rows, 1):
        if row.get("Product") != product:
            continue
        if row.get("State") not in (None, "", "COMPLETED"):
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "row_not_completed"}); continue
        amount, fee, balance = _english_amount(row.get("Amount")), _english_amount(row.get("Fee")) or Decimal("0"), _english_amount(row.get("Balance"))
        stamp = (row.get("Completed Date") or row.get("Started Date") or "")[:10]
        try:
            local_date = datetime.strptime(stamp, "%Y-%m-%d").date().isoformat()
        except ValueError:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        if amount is None or balance is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        cash = amount - fee
        if cash == 0:
            # Zins, von dem die Steuer den ganzen Betrag aufzehrt: auf dem Konto bewegt
            # sich nichts, ein Cash-Ereignis ueber 0 gibt es nicht. Wird gemeldet.
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "interest_fully_taxed",
                                "gross_income_decimal": _plain(amount)}); continue
        if opening is None:
            opening = balance - cash
        interest = row.get("Type") == "Interest" and amount > 0
        candidate = {"source_row_ordinal": ordinal, "local_date": local_date,
                     "kind": "interest" if interest else ("deposit" if cash > 0 else "withdrawal"),
                     "amount_decimal": _plain(abs(cash)), "balance_after_decimal": _plain(balance),
                     "text": " ".join(part for part in (row.get("Type", ""), row.get("Description", "")) if part).strip()}
        if interest and fee != 0:
            # Der Ertrag ist brutto, auf dem Konto landet der Betrag nach Steuer.
            candidate["gross_income_decimal"] = _plain(amount)
        candidates.append(candidate)
    if not candidates:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    summary = {"opening_balance_decimal": opening, "closing_balance_decimal": _cents(candidates[-1]["balance_after_decimal"]),
               "period_from": days[0], "period_to": days[-1]}
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}

def _parse_revolut_current(source: bytes, file_name: str) -> dict[str, Any]:
    return _parse_revolut(source, file_name, "Current")

def _parse_revolut_savings(source: bytes, file_name: str) -> dict[str, Any]:
    return _parse_revolut(source, file_name, "Deposit")


READERS = {
    "revolut_current_v1": _parse_revolut_current,
    "revolut_savings_v1": _parse_revolut_savings,
}
