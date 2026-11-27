"""Portelyra-Leser bison: Cash-Belege (statement_reader_v1, Aufruf read).

Erzeugt aus dem bisherigen Kernmodul (rc.372) ohne Aenderung der Leselogik. Der Leser bekommt Dateiinhalt und
Dateinamen und liefert Kandidaten; er liest keine anderen Dateien, hat kein Netz und schreibt nichts.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from portelyra_reader_sdk_v1 import (
    CENT,
    ReaderError as CashStatementImportV1Error,
    TIME_ZONE,
    abort as _abort,
    cents as _cents,
    english_amount as _english_amount,
    cash_exchange_result as _exchange_result,
    cash_exchange_row as _exchange_row,
    named_rows as _named_rows,
    pdf_text as _pdf_text,
    plain as _plain,
    utc_stamp_to_local_date as _utc_stamp_to_local_date,
)


def _parse_bison_eur(source: bytes, file_name: str) -> dict[str, Any]:
    """Bison: Einzahlung, Auszahlung, Kauf und Verkauf in Euro; kein Saldo."""
    rows = _named_rows(source)
    if not rows or any(column not in rows[0] for column in ("Transaction type", "Eur (amount)", "Fee")):
        _abort("cash_statement_header_invalid")
    date_column = next((name for name in rows[0] if name.startswith("Date")), None)
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows, 1):
        kind = row.get("Transaction type", "")
        if kind not in ("Deposit", "Withdraw", "Buy", "Sell"):
            continue
        if kind in ("Deposit", "Withdraw") and row.get("Asset", "").strip().upper() not in ("", "EUR"):
            continue   # Coin-Ein- oder Auszahlung: gehoert zum Asset, nicht zum Euro-Konto (wie der Krypto-Leser)
        fee_text = row.get("Fee", "").strip()
        amount, fee = _english_amount(row.get("Eur (amount)")), (_english_amount(fee_text) if fee_text else Decimal("0"))
        if amount is None or fee is None or date_column is None:   # unlesbare Gebuehr: Grund statt stiller 0 (rc.379)
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        cash = {"Deposit": amount, "Withdraw": -amount, "Buy": -(amount + fee), "Sell": amount - fee}[kind]
        if cash == 0:   # Zeile ohne Euro-Bewegung: uebergehen wie bei Kraken; als Bewegung ueber 0 verwuerfe der Kern den ganzen Beleg (rc.379)
            continue
        text = f"{kind} {row.get('Asset', '')}".strip()
        local_date = _utc_stamp_to_local_date(row[date_column])
        if local_date is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        candidates.append(_exchange_row(ordinal, local_date, cash, text))
    return _exchange_result(candidates, diagnostics)


# Verrechnungskonto (#550, rc.434; Festlegung 18.11.2026: Monatssaldo als Saldo-Beleg): Die EUWAX fuehrt das Euro-Guthaben von Bison und
# stellt je Monat eine "Monatsuebersicht" (PDF) aus - Zeitraum mit Eroeffnungsbilanz und Abschlusssaldo, darunter je Buchung eine Zeile
# (Gegenpartei, Buchungs- und Valutadatum, Betrag mit Vorzeichen), gefolgt von Referenz, Beschreibung, IBAN/BIC. Ein Monat ohne Buchung
# bestaetigt nur den Saldo. Eroeffnung plus Buchungen muss den Abschluss ergeben, sonst ist der Beleg nicht sicher gelesen.
SETTLEMENT_PERIOD = re.compile(r"^(\d{2}\.\d{2}\.\d{4}) - (\d{2}\.\d{2}\.\d{4}) (-?[\d.]+,\d{2}) ?€ (-?[\d.]+,\d{2}) ?€$")
SETTLEMENT_BOOKING = re.compile(r"^(.*?) ?(\d{2}\.\d{2}\.\d{4}) (\d{2}\.\d{2}\.\d{4}) (-?[\d.]+,\d{2}) ?€$")
SETTLEMENT_HEAD = "Transaktion Buchungsdatum Valutadatum Wert"


def _settlement_day(text: str) -> str | None:
    try:
        return datetime.strptime(text, "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


def _settlement_amount(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _parse_bison_settlement(source: bytes, file_name: str) -> dict[str, Any]:
    lines = [" ".join(line.split()) for line in _pdf_text(source, file_name)]
    if not any(line.startswith("Monatsübersicht") for line in lines) or SETTLEMENT_HEAD not in lines:
        _abort("cash_statement_header_invalid")
    period = next((match for match in (SETTLEMENT_PERIOD.match(line) for line in lines) if match is not None), None)
    if period is None:
        _abort("cash_statement_header_invalid")
    first, last = _settlement_day(period.group(1)), _settlement_day(period.group(2))
    opening, closing = _settlement_amount(period.group(3)), _settlement_amount(period.group(4))
    if first is None or last is None or last < first or opening is None or closing is None:
        _abort("cash_statement_source_invalid")
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    values: list[Decimal] = []
    ordinal, pending, in_table = 0, None, False
    for line in lines:
        if line == SETTLEMENT_HEAD:
            in_table = True; continue
        if not in_table:
            continue
        if line.startswith("Sehr geehrte"):
            in_table = False; pending = None; continue
        booking = SETTLEMENT_BOOKING.match(line)
        if booking is not None and not line.startswith(("Referenz:", "Beschreibung:", "IBAN:")):
            ordinal += 1
            value, day = _settlement_amount(booking.group(4)), _settlement_day(booking.group(2))
            if value is None or day is None:   # unlesbar: Grund statt Schaetzung; die Saldoprobe unten haelt den Beleg dann an
                diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid" if value is None else "date_invalid"})
                pending = None; continue
            values.append(value)
            if value == 0:
                pending = None; continue
            pending = {"source_row_ordinal": ordinal, "local_date": day, "kind": "deposit" if value > 0 else "withdrawal",
                       "amount_decimal": _plain(abs(value)), "balance_after_decimal": None, "text": booking.group(1).strip() or "Buchung"}
            candidates.append(pending)
            continue
        if pending is not None and line.startswith("Beschreibung:"):
            description = line.split(":", 1)[1].strip()
            if description:
                pending["text"] = f"{pending['text']}: {description}"
    if not diagnostics and opening + sum(values, Decimal("0")) != closing:
        _abort("cash_statement_source_invalid")
    summary = {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(closing), "period_from": first,
               "period_to": last, "closing_as_of_date": last}
    return {"candidates": candidates, "diagnostics": diagnostics, "summary": summary}


READERS = {
    "bison_eur_v1": _parse_bison_eur,
    "bison_settlement_v1": _parse_bison_settlement,
}
