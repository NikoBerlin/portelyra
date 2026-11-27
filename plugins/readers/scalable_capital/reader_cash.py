"""Portelyra-Leser scalable_capital: Cash-Belege (statement_reader_v1, Aufruf read).

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


# Nur Zinsen sind ein eigener Ertrag. Alles andere - Steuern, Gebuehren,
# Wertpapierabrechnungen, Ausschuettungen - wirkt allein auf den Saldo, und das
# Vorzeichen entscheidet: Steuern werden auch erstattet und stehen dann positiv
# im Auszug.
SCALABLE_INTEREST = ("erhaltene zinsen", "zinsgutschrift")

def _iso_day(text: str) -> str:
    """TT.MM.JJJJ als ISO-Tag. Einen unmoeglichen Tag (etwa 32.09. in einer beschaedigten Datei, gefunden im Selbsttest rc.379)
    weist der Leser mit Grund ab, statt abzustuerzen; fuer jeden gueltigen Auszug bleibt das Ergebnis gleich."""
    try:
        return datetime.strptime(text, "%d.%m.%Y").date().isoformat()
    except ValueError:
        _abort("cash_statement_source_invalid")

def _parse_scalable_tagesgeld(source: bytes, file_name: str) -> dict[str, Any]:
    lines = _pdf_text(source, file_name)
    amount = r"([+-]?\d{1,3}(?:\.\d{3})*,\d{2})\s*EUR"
    summary: dict[str, Any] = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": None, "period_to": None}
    balances: list[tuple[str, Decimal]] = []
    for line in lines:
        period = re.search(r"Zeitraum\s+(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})", line)
        if period:
            summary["period_from"], summary["period_to"] = (_iso_day(item) for item in period.groups())
        balance = re.search(r"Kontostand am\s+(\d{2}\.\d{2}\.\d{4})\s+" + amount, line)
        if balance:
            value = _cents(balance.group(2))
            if value is not None:
                balances.append((_iso_day(balance.group(1)), value))
    if len(balances) >= 2:
        ordered = sorted(balances, key=lambda item: item[0])
        summary["opening_balance_decimal"] = ordered[0][1]
        summary["closing_balance_decimal"] = ordered[-1][1]
        summary["period_from"] = summary["period_from"] or ordered[0][0]
        summary["period_to"] = summary["period_to"] or ordered[-1][0]
        # Der Endsaldo gilt an dem Tag, der neben ihm steht - nicht am Tag der
        # letzten Bewegung. Ohne diese Angabe setzte der Import den Abstimmpunkt
        # auf die letzte Bewegung und verschenkte die Tage bis zum Auszugsende
        # (#417).
        summary["closing_as_of_date"] = ordered[-1][0]
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    booking = re.compile(r"^\s*(\d{2}\.\d{2}\.\d{4})\s+(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+" + amount + r"\s*$")
    ordinal = 0
    for line in lines:
        match = booking.match(line)
        if match is None:
            continue
        ordinal += 1
        booked, value_date, text, raw = match.groups()
        value = _cents(raw.replace("+", ""))
        if value == 0:
            continue
        if value is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        lowered = text.lower()
        if value > 0 and any(marker in lowered for marker in SCALABLE_INTEREST):
            kind = "interest"
        else:
            kind = "deposit" if value > 0 else "withdrawal"
        booked_day = _iso_day(booked)
        candidate = {"source_row_ordinal": ordinal, "local_date": booked_day,
                     "kind": kind, "amount_decimal": _plain(abs(value)), "balance_after_decimal": None, "text": text.strip()}
        # Der Zins des vierten Quartals wird am 01.01. gebucht und auf den 31.12.
        # wertgestellt; steuerlich gehoert er ins alte Jahr (#465).
        # Der Geldfluss bleibt am Buchungstag - sonst verliert die Saldokette den
        # Tag -, nur der Ertrag folgt der Wertstellung.
        if kind == "interest":
            value_day = _iso_day(value_date)
            if value_day != booked_day:
                candidate["value_date"] = value_day
        candidates.append(candidate)
    # Ein Auszug nennt seinen Kontostand (rc.322). Eine Dividendenabrechnung von Scalable ("Wertpapierereignisse") hat eine Zeile
    # wie eine Buchung, aber keinen Kontostand; als Auszug gelesen wuerde sie im Eingang dem Verrechnungskonto zugeordnet (Abrechnungen ohne,
    # Auszuege mit "Kontostand am").
    if not balances:
        _abort("cash_statement_header_invalid")
    if not candidates:
        # Ein Monat ohne Bewegung ist ein Saldo-Anker, kein Fehler (#440, Festlegung 03.10.2026): Der Auszug sagt "Keine
        # Kontobewegungen in diesem Zeitraum" und nennt denselben Kontostand am Anfang und am Ende. Sonst bleibt es beim
        # Abbruch - ein Auszug ohne Buchungszeilen und ohne diesen Satz ist keiner dieser Vorlage.
        quiet = any("keine kontobewegungen" in line.lower() for line in lines)
        if not quiet or not balances or len({value for _day, value in balances}) != 1:
            _abort("cash_statement_header_invalid")
        day = max(item[0] for item in balances)
        summary["opening_balance_decimal"] = summary["closing_balance_decimal"] = balances[0][1]
        summary["period_from"] = summary["period_from"] or min(item[0] for item in balances)
        summary["period_to"] = summary["period_to"] or day
        summary["closing_as_of_date"] = max(day, summary["period_to"])
    # "Kontostand am <Periodenbeginn>" war bis September 2026 der Stand am Ende jenes Tages: Die Buchungen des ersten Tages steckten
    # schon darin und muessen wieder heraus. Seit Oktober 2026 ist es der Stand davor. Abgezogen wird deshalb nur,
    # wenn der Auszug sonst nicht aufgeht.
    if isinstance(summary["opening_balance_decimal"], Decimal) and summary["period_from"]:
        signed = lambda row: Decimal(row["amount_decimal"]) * (-1 if row["kind"] == "withdrawal" else 1)
        first_day = sum((signed(row) for row in candidates if row["local_date"] == summary["period_from"]), Decimal("0"))
        whole = sum((signed(row) for row in candidates), Decimal("0"))
        closes_as_is = isinstance(summary["closing_balance_decimal"], Decimal) and \
            summary["opening_balance_decimal"] + whole == summary["closing_balance_decimal"]
        if not closes_as_is:
            summary["opening_balance_decimal"] = (summary["opening_balance_decimal"] - first_day).quantize(Decimal("0.01"))
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}


READERS = {
    "scalable_tagesgeld_v1": _parse_scalable_tagesgeld,
    "scalable_broker_v1": _parse_scalable_tagesgeld,
}
