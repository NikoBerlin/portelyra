"""Portelyra-Leser kraken: Cash-Belege (statement_reader_v1, Aufruf read).

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


def _parse_kraken_eur(source: bytes, file_name: str) -> dict[str, Any]:
    """Kraken Ledger: je Zeile Betrag, Gebuehr und laufender Saldo des Assets."""
    rows = _named_rows(source)
    if not rows or any(column not in rows[0] for column in ("time", "type", "asset", "amount", "fee", "balance")):
        _abort("cash_statement_header_invalid")
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    opening = closing = None
    for ordinal, row in enumerate(rows, 1):
        if row.get("asset") not in ("EUR", "ZEUR"):
            continue
        fee_text = (row.get("fee") or "").strip()   # unlesbare Gebuehr (etwa mehr als zwei Nachkommastellen): Grund statt stiller 0 (rc.379)
        amount, fee, balance = _english_amount(row.get("amount")), (_english_amount(fee_text) if fee_text else Decimal("0")), _english_amount(row.get("balance"))
        if amount is None or fee is None or balance is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        cash = amount - fee
        if opening is None:
            opening = balance - cash
        closing = balance
        if cash == 0:
            continue
        local_date = _utc_stamp_to_local_date(row.get("time", ""))
        if local_date is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        candidates.append(_exchange_row(ordinal, local_date, cash, f"{row.get('type', '')} {row.get('subtype', '')}".strip(), balance))
    return _exchange_result(candidates, diagnostics, opening, closing)


READERS = {
    "kraken_eur_v1": _parse_kraken_eur,
}
