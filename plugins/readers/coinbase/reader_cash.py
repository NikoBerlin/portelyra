"""Portelyra-Leser coinbase: Cash-Belege (statement_reader_v1, Aufruf read).

Erzeugt aus dem bisherigen Kernmodul (rc.372) ohne Aenderung der Leselogik. Der Leser bekommt Dateiinhalt und
Dateinamen und liefert Kandidaten; er liest keine anderen Dateien, hat kein Netz und schreibt nichts.
"""
from __future__ import annotations

from decimal import Decimal
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
    plain as _plain,
    utc_stamp_to_local_date as _utc_stamp_to_local_date,
)


def _amount(text: Any) -> Decimal | None:
    """Wie english_amount; eine Zahl, die kein Betrag sein kann (etwa "3e78" aus einem beschaedigten Beleg), ist nicht lesbar statt
    ein Absturz (Selbsttest rc.379: quantize im SDK wirft dann InvalidOperation)."""
    try:
        return _english_amount(text)
    except ArithmeticError:
        return None


def _local_date(stamp: str) -> str | None:
    """Wie utc_stamp_to_local_date; ein Zeitpunkt am Rand des Kalenders (9999-12-31 23:30 UTC) ist nicht lesbar statt ein Absturz."""
    try:
        return _utc_stamp_to_local_date(stamp)
    except (OverflowError, ValueError):
        return None


def _parse_coinbase_eur(source: bytes, file_name: str) -> dict[str, Any]:
    """Coinbase: das EUR-Wallet bewegen Verkaeufe gegen Euro und Kaeufe "using EUR-Wallet".
    Kaeufe per Karte beruehren das Wallet nicht; EURC ist ein Stablecoin, kein Euro-Guthaben."""
    lines = source.decode("utf-8-sig", errors="replace").splitlines()
    start = next((index for index, line in enumerate(lines) if "Transaction Type" in line), None)
    if start is None:
        _abort("cash_statement_header_invalid")
    try:
        rows = _named_rows("\n".join(lines[start:]).encode("utf-8"))
    except AttributeError:   # doppelte Spaltennamen und eine Zeile mit ueberzaehligen Feldern (beschaedigter Beleg): named_rows im SDK stolpert
        _abort("cash_statement_source_invalid")
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows, 1):
        kind, asset, notes = row.get("Transaction Type", ""), row.get("Asset", ""), row.get("Notes", "")
        total = _amount(row.get("Total (inclusive of fees and/or spread)"))
        if asset == "EUR" and kind in ("Deposit", "Withdrawal"):
            value = _amount(row.get("Quantity Transacted"))
            cash = None if value is None else (abs(value) if kind == "Deposit" else -abs(value))
        elif kind in ("Sell", "Advanced Trade Sell") and notes.endswith("EUR"):
            cash = total
        elif kind in ("Buy", "Advanced Trade Buy") and "EUR-Wallet" in notes:
            cash = None if total is None else -total
        else:
            continue
        if cash == 0:
            continue
        if cash is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        local_date = _local_date(row.get("Timestamp", ""))
        if local_date is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        candidates.append(_exchange_row(ordinal, local_date, cash, f"{kind} {asset}".strip()))
    return _exchange_result(candidates, diagnostics)


READERS = {
    "coinbase_eur_v1": _parse_coinbase_eur,
}
