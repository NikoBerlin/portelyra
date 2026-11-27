"""Portelyra-Leser baader: Cash-Belege (statement_reader_v1, Aufruf read).

Erzeugt aus dem bisherigen Kernmodul (rc.372) ohne Aenderung der Leselogik. Der Leser bekommt Dateiinhalt und
Dateinamen und liefert Kandidaten; er liest keine anderen Dateien, hat kein Netz und schreibt nichts.
"""
from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
import re
from typing import Any

from portelyra_reader_sdk_v1 import (
    CENT,
    ReaderError as CashStatementImportV1Error,
    abort as _abort,
    cents as _cents,
    pdf_text as _pdf_text,
    plain as _plain,
)


# Baader Bank "Perioden-Kontoauszug": Belastung und Gutschrift stehen in zwei
# Spalten, ein nachgestelltes "-" markiert die Belastung. Dieselbe Vorlage
# liefern Smartbroker+ und Scalable-Depots aus der Baader-Zeit.
BAADER_INTEREST = ("habenzinsen", "zinsgutschrift", "erhaltene zinsen", "rechnungsabschluss")

BAADER_NOT_INTEREST = ("storno",)

BAADER_AMOUNT = r"(\d{1,3}(?:\.\d{3})*,\d{2})(\s*-)?"

BAADER_BALANCE = re.compile(r"^Kontostand in EUR am(?:\s+(\d{2}\.\d{2}\.\d{4}))?\s+" + BAADER_AMOUNT + r"$")

BAADER_BOOKING = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+(\d{2}\.\d{2}\.\d{4})\s+" + BAADER_AMOUNT + r"$")


def _day(text: str) -> str | None:
    """TT.MM.JJJJ als ISO-Datum; None fuer einen Tag, den es nicht gibt (beschaedigter Beleg, Selbsttest rc.379)."""
    try:
        return datetime.strptime(text, "%d.%m.%Y").date().isoformat()
    except ValueError:
        return None


def _parse_baader_perioden(source: bytes, file_name: str) -> dict[str, Any]:
    lines = [" ".join(line.split()) for line in _pdf_text(source, file_name)]
    summary: dict[str, Any] = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": None, "period_to": None}
    signed = lambda text, minus: None if _cents(text) is None else (-_cents(text) if minus else _cents(text))
    dated: list[tuple[str, Decimal]] = []
    undated: list[Decimal] = []
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    ordinal = 0
    for line in lines:
        balance = BAADER_BALANCE.match(line)
        if balance is not None:
            value = signed(balance.group(2), bool(balance.group(3)))
            if value is None:
                continue
            if balance.group(1) is None:
                undated.append(value)
            else:
                day = _day(balance.group(1))
                if day is None:   # Saldo an einem Tag, den es nicht gibt: Zeitraum und Saldenkette waeren geraten
                    _abort("cash_statement_source_invalid")
                dated.append((day, value))
            continue
        booking = BAADER_BOOKING.match(line)
        if booking is None:
            continue
        ordinal += 1
        value = signed(booking.group(4), bool(booking.group(5)))
        if value == 0:
            continue
        if value is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        local_date = _day(booking.group(1))
        if local_date is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        text = booking.group(2).strip()
        lowered = text.lower()
        is_interest = value > 0 and any(marker in lowered for marker in BAADER_INTEREST) and not lowered.startswith(BAADER_NOT_INTEREST)
        kind = "interest" if is_interest else ("deposit" if value > 0 else "withdrawal")
        candidates.append({"source_row_ordinal": ordinal, "local_date": local_date,
                           "kind": kind, "amount_decimal": _plain(abs(value)), "balance_after_decimal": None, "text": text})
    if not candidates and not dated and not undated:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    if len(dated) >= 2:
        ordered = sorted(dated, key=lambda item: item[0])
        # Die erste Saldozeile datiert auf den Tag vor dem Zeitraum, die letzte auf dessen Ende.
        summary["opening_balance_decimal"] = ordered[0][1]
        summary["closing_balance_decimal"] = ordered[-1][1]
        summary["period_from"] = (date.fromisoformat(ordered[0][0]) + timedelta(days=1)).isoformat()
        summary["period_to"] = ordered[-1][0]
        summary["closing_as_of_date"] = ordered[-1][0]
    elif undated and dated:
        # Erstauszug eines Kontos: der Anfangssaldo steht ohne Datum.
        summary["opening_balance_decimal"] = undated[0]
        summary["closing_balance_decimal"] = dated[-1][1]
        summary["period_from"] = days[0] if days else dated[-1][0]
        summary["period_to"] = dated[-1][0]
        summary["closing_as_of_date"] = dated[-1][0]
    elif len(dated) == 1 and not candidates:
        # "Es wurden keine Transaktionen vorgenommen": der Auszug bestaetigt nur den Saldo.
        summary["opening_balance_decimal"] = summary["closing_balance_decimal"] = dated[0][1]
        summary["period_from"] = summary["period_to"] = dated[0][0]
        summary["closing_as_of_date"] = dated[0][0]
    if summary["period_from"] is None and days:
        summary["period_from"], summary["period_to"] = days[0], days[-1]
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}


READERS = {
    "baader_perioden_v1": _parse_baader_perioden,
}
