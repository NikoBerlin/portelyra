"""Leser der Vorlage: eine einfache CSV-Datei "Datum;Betrag;Text" (Bereich cash).

Was ein Leser darf und muss, steht in contracts/statement-reader-plugin/v1/README.md ("Mindestanforderungen"):
- nur die Standardbibliothek und das SDK importieren, kein Netz, keine anderen Dateien;
- Dezimalzahlen als exakter Text (SDK: plain), Betraege positiv, die Richtung steht in der Art;
- bei einem Beleg, der nicht passt oder beschaedigt ist, mit einem Code aus der festen Liste abbrechen (SDK: abort) - nie abstuerzen;
- Zeilen, die er nicht lesen kann, als Hinweis (diagnostics) mit Grund nennen statt sie still zu uebergehen.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from portelyra_reader_sdk_v1 import abort, german_amount, named_rows, plain

COLUMNS = ("Datum", "Betrag", "Text")


def _parse(source: bytes, file_name: str) -> dict[str, Any]:
    rows = named_rows(source)   # bricht bei beschaedigter Datei selbst mit einem Code ab
    if not rows or any(column not in rows[0] for column in COLUMNS):
        abort("cash_statement_header_invalid")
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows, 1):
        try:
            local_date = datetime.strptime(row.get("Datum", ""), "%d.%m.%Y").date().isoformat()
        except ValueError:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        value = german_amount(row.get("Betrag"))
        if value is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        if value == 0:
            continue
        text = row.get("Text", "")
        interest = value > 0 and "zins" in text.lower()
        candidates.append({"source_row_ordinal": ordinal, "local_date": local_date,
                           "kind": "interest" if interest else ("deposit" if value > 0 else "withdrawal"),
                           "amount_decimal": plain(abs(value)), "balance_after_decimal": None, "text": text})
    if not candidates:
        abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}


READERS = {"vorlage_csv_v1": _parse}
