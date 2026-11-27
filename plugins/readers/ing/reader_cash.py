"""Portelyra-Leser ing: Cash-Belege (statement_reader_v1, Aufruf read).

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
    pdf_text as _pdf_text,
    plain as _plain,
)


# ING-DiBa Kontoauszug (Giro und Extra-Konto): "Alter Saldo"/"Neuer Saldo" im Kopf,
# je Buchung eine Zeile mit Buchungstag, Buchungsart und Betrag, meist gefolgt von
# einer Valuta-Zeile mit Verwendungszweck. Der Verwendungszweck kann selbst mit
# einem Betrag enden ("... Betrag 137,00"), und nicht jede Buchung hat eine
# Valuta-Zeile - eine Buchung erkennt man deshalb an ihrer Buchungsart.
ING_BALANCE = re.compile(r"^(?:.*\s)?(Alter|Neuer) Saldo\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})(?:\s+Euro)?$")

ING_DATE_LINE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+(.*)$")

# Hinter dem Betrag steht mitunter eine Fussnotenziffer ("-45,001").
ING_AMOUNT = re.compile(r"(?:^|\s)(-?\d{1,3}(?:\.\d{3})*,\d{2})\d?$")

ING_BOOKING_TYPES = ("lastschrift", "dauerauftrag", "ueberweisung", "überweisung", "gutschrift", "wertpapierkauf", "gehalt",
                     "wertpapiergutschrift", "echtzeitüberweisung", "echtzeitueberweisung", "entgelt", "zins/dividende",
                     "kapitalertragsteuer", "zinsertrag", "retoure", "abschluss", "abbuchung", "solidaritätszuschlag",
                     "solidaritaetszuschlag", "kirchensteuer", "storno", "rücküberweisung", "rueckueberweisung",
                     "bargeldeinzahlung", "einzahlung", "auszahlung", "umbuchung", "zinsgutschrift")

ING_INTEREST = ("zinsertrag", "zinsgutschrift", "habenzinsen")

def _parse_ing(source: bytes, file_name: str) -> dict[str, Any]:
    lines = [" ".join(line.split()) for line in _pdf_text(source, file_name)]
    summary: dict[str, Any] = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": None, "period_to": None}
    for line in lines:
        balance = ING_BALANCE.match(line)
        if balance is not None:
            key = "opening_balance_decimal" if balance.group(1) == "Alter" else "closing_balance_decimal"
            if summary[key] is None:
                summary[key] = _cents(balance.group(2))
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    ordinal = 0
    for line in lines:
        match = ING_DATE_LINE.match(line)
        if match is None:
            continue
        rest = match.group(2)
        amount = ING_AMOUNT.search(rest)
        if amount is None:
            continue
        text = rest[: amount.start()].strip()
        lowered = text.lower()
        # Valuta-Zeilen tragen den Verwendungszweck, nicht die Buchungsart.
        if text and not lowered.startswith(ING_BOOKING_TYPES):
            continue
        ordinal += 1
        value = _cents(amount.group(1))
        if value == 0:
            continue
        if value is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        try:
            local_date = datetime.strptime(match.group(1), "%d.%m.%Y").date().isoformat()
        except ValueError:   # kein Kalendertag ("25.72.2027"): ein Hinweis statt eines Absturzes (Selbsttest rc.379)
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        kind = "interest" if value > 0 and lowered.startswith(ING_INTEREST) else ("deposit" if value > 0 else "withdrawal")
        candidates.append({"source_row_ordinal": ordinal, "local_date": local_date,
                           "kind": kind, "amount_decimal": _plain(abs(value)), "balance_after_decimal": None, "text": text})
    if not candidates and summary["opening_balance_decimal"] is None:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    if days:
        summary["period_from"], summary["period_to"] = days[0], days[-1]
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}


READERS = {
    "ing_v1": _parse_ing,
}
