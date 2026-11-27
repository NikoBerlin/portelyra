"""Portelyra-Leser c24: Cash-Belege (statement_reader_v1, Aufruf read).

Erzeugt aus dem bisherigen Kernmodul (rc.372) ohne Aenderung der Leselogik. Der Leser bekommt Dateiinhalt und
Dateinamen und liefert Kandidaten; er liest keine anderen Dateien, hat kein Netz und schreibt nichts.
"""
from __future__ import annotations

from datetime import date
from datetime import datetime
from typing import Any

from portelyra_reader_sdk_v1 import (
    CENT,
    ReaderError as CashStatementImportV1Error,
    abort as _abort,
    cents as _cents,
    german_amount as _german_amount,
    named_rows as _named_rows,
    plain as _plain,
)


# C24 exportiert eine Datei je Konto ohne Saldospalte: die Abdeckung bleibt deshalb
# "teilweise erfasst", solange kein Auszug den Saldo belegt.
C24_COLUMNS = ("Transaktionstyp", "Buchungsdatum", "Betrag")

def _parse_c24(source: bytes, file_name: str) -> dict[str, Any]:
    rows = _named_rows(source)
    if not rows or any(column not in rows[0] for column in C24_COLUMNS):
        _abort("cash_statement_header_invalid")
    # Ein Export ueber "Alle Konten" mischt Giro und Tagesgeld; die "Kontonummer" ist bei beiden gleich, nur "Kontoname" trennt sie.
    # Gelesen wird je Konto - eine gemischte Datei bucht nichts (#523: sonst landen Tagesgeld-Bewegungen im Giro).
    if len({(row.get("Kontoname") or "").strip() for row in rows} - {""}) > 1:
        _abort("cash_statement_multiple_accounts")
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows, 1):
        value = _german_amount(row.get("Betrag"))
        try:
            local_date = datetime.strptime(row.get("Buchungsdatum", ""), "%d.%m.%Y").date().isoformat()
        except ValueError:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        if value == 0:
            continue
        if value is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        kind_text = row.get("Transaktionstyp", "")
        # Zinsen stehen als eigener Transaktionstyp und zusaetzlich als Einkommen/Kapitalertraege.
        interest = value > 0 and ("zinszahlung" in kind_text.lower()
                                  or (row.get("Kategorie", "").lower() == "einkommen" and "kapitalertr" in row.get("Unterkategorie", "").lower()))
        text = " ".join(part for part in (kind_text, row.get("Zahlungsempfänger", ""), row.get("Verwendungszweck", "")) if part).strip()
        candidates.append({"source_row_ordinal": ordinal, "local_date": local_date,
                           "kind": "interest" if interest else ("deposit" if value > 0 else "withdrawal"),
                           "amount_decimal": _plain(abs(value)), "balance_after_decimal": None, "text": text})
    if not candidates:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}


READERS = {
    "c24_transactions_v1": _parse_c24,
}
