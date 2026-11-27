"""Portelyra-Leser bondora: Cash-Belege (statement_reader_v1, Aufruf read).

Erzeugt aus dem bisherigen Kernmodul (rc.372) ohne Aenderung der Leselogik. Der Leser bekommt Dateiinhalt und
Dateinamen und liefert Kandidaten; er liest keine anderen Dateien, hat kein Netz und schreibt nichts.
"""
from __future__ import annotations

from datetime import date
from datetime import datetime
from decimal import Decimal
import re
from typing import Any

from portelyra_reader_sdk_v1 import (
    CENT,
    ReaderError as CashStatementImportV1Error,
    abort as _abort,
    cents as _cents,
    delimited_rows as _delimited_rows,
    plain as _plain,
    xlsx_rows as _xlsx_rows,
)


# ---------------------------------------------------------------- Bondora adapter
def _parse_bondora(source: bytes, file_name: str) -> dict[str, Any]:
    rows = _xlsx_rows(source) if file_name.lower().endswith(".xlsx") else _delimited_rows(source)
    normalized = lambda value: re.sub(r"[^a-zäöü]", "", str(value).lower())
    header_index = next((index for index, row in enumerate(rows) if {"datum", "zahlungsart"} <= {normalized(cell) for cell in row}
                         or {"date", "paymenttype"} <= {normalized(cell) for cell in row}), None)
    if header_index is None:
        _abort("cash_statement_header_invalid")
    header = [normalized(cell) for cell in rows[header_index]]
    column = lambda *names: next((header.index(name) for name in names if name in header), None)
    c_date, c_type = column("datum", "date"), column("zahlungsart", "paymenttype")
    c_in, c_out, c_balance = column("eingänge", "eingaenge", "in"), column("ausgänge", "ausgaenge", "out"), column("guthaben", "balance", "saldo")
    if c_in is None and c_out is None:
        _abort("cash_statement_header_invalid")
    summary: dict[str, Any] = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": None, "period_to": None}
    for row in rows[:header_index]:
        cells = [str(cell).strip() for cell in row]
        for index, cell in enumerate(cells):
            match = re.fullmatch(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})", cell)
            if match:
                summary["period_from"], summary["period_to"] = (datetime.strptime(item, "%d.%m.%Y").date().isoformat() for item in match.groups())
            label = normalized(cell)
            following = next((item for item in cells[index + 1:] if item), None)
            if label in {"zubeginn", "openingbalance", "anfangssaldo"}:
                summary["opening_balance_decimal"] = _cents(following)
            elif label in {"ergebnis", "closingbalance", "endsaldo"}:
                summary["closing_balance_decimal"] = _cents(following)
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows[header_index + 1:], 1):
        cell = lambda index: str(row[index]).strip() if index is not None and index < len(row) else ""
        if not any(str(item).strip() for item in row):
            continue
        text = cell(c_type)
        try:
            local_date = datetime.strptime(cell(c_date), "%d.%m.%Y").date().isoformat()
        except ValueError:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        inflow, outflow, balance = _cents(cell(c_in)), _cents(cell(c_out)), _cents(cell(c_balance))
        # Eingaenge und Ausgaenge stehen ohne Vorzeichen. Ein Minus ist ein anderes Format
        # oder ein beschaedigter Beleg: Grund statt Absturz oder negativem Betrag (Selbsttest rc.379).
        if (inflow is not None and inflow < 0) or (outflow is not None and outflow < 0):
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        if (inflow is None or inflow == 0) == (outflow is None or outflow == 0):
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        if inflow is not None and inflow > 0:
            kind = "interest" if "zins" in text.lower() or "interest" in text.lower() else "deposit"
            amount = inflow
        else:
            kind = "withdrawal"; amount = outflow
        candidates.append({"source_row_ordinal": ordinal, "local_date": local_date, "kind": kind, "amount_decimal": _plain(amount),
                           "balance_after_decimal": None if balance is None else _plain(balance), "text": text})
    return {"candidates": candidates, "diagnostics": diagnostics, "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}


READERS = {
    "bondora_go_grow_v1": _parse_bondora,
}
