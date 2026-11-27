"""Portelyra-Leser trade_republic: Cash-Belege (statement_reader_v1, Aufruf read).

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
    english_amount as _english_amount,
    named_rows as _named_rows,
    pdf_text as _pdf_text,
    plain as _plain,
)


# Trade Republic "Kontoauszug": ein einziges PDF ueber die ganze Historie. Tag,
# Monat und Jahr stehen auf drei verschiedenen Zeilen, die Betragszeile fuehrt
# Bewegung und laufenden Saldo. Das Vorzeichen steht nirgends - es ergibt sich
# aus der Saldoaenderung, die zugleich jede Zeile prueft.
TRADE_REPUBLIC_MONTHS = {"jan": 1, "feb": 2, "mar": 3, "mär": 3, "apr": 4, "mai": 5, "jun": 6,
                         "jul": 7, "aug": 8, "sep": 9, "okt": 10, "nov": 11, "dez": 12}

TRADE_REPUBLIC_AMOUNT = re.compile(r"(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*€")

TRADE_REPUBLIC_DAY = re.compile(r"^(\d{1,2})(?:\s|$)")

TRADE_REPUBLIC_YEAR = re.compile(r"^(20\d{2})(?:\s|$)")

TRADE_REPUBLIC_SUMMARY = re.compile(r"^Cashkonto\b")

def _trade_republic_month(token: str) -> int | None:
    return TRADE_REPUBLIC_MONTHS.get(token.strip(".").lower()[:3])

def _parse_trade_republic(source: bytes, file_name: str) -> dict[str, Any]:
    document = [" ".join(line.split()) for line in _pdf_text(source, file_name)]
    # Hinter dem Cash-Umsatz stehen weitere Tabellen (Geldmarktfonds im
    # Treuhandkonto). Ihre Zeilen tragen eigene Betraege und gehoeren nicht zum
    # Konto, deshalb endet die Auswertung an der naechsten Abschnittsueberschrift.
    start = next((index + 1 for index, line in enumerate(document) if line == "UMSATZÜBERSICHT"), 0)
    stop = next((index for index, line in enumerate(document[start:], start)
                 if line.startswith(("TREUHANDKONTEN", "GELDMARKTFONDS", "TRANSAKTIONSÜBERSICHT", "DEPOTÜBERSICHT", "WERTPAPIERÜBERSICHT"))), len(document))
    lines = document[start:stop]
    summary: dict[str, Any] = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": None, "period_to": None}
    for line in document:
        if TRADE_REPUBLIC_SUMMARY.match(line):
            totals = TRADE_REPUBLIC_AMOUNT.findall(line)
            if len(totals) == 4:
                summary["opening_balance_decimal"] = _cents(totals[0])
                summary["closing_balance_decimal"] = _cents(totals[3])
            break
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    running = summary["opening_balance_decimal"]
    ordinal = 0
    for index, line in enumerate(lines):
        if TRADE_REPUBLIC_SUMMARY.match(line):
            continue
        amounts = TRADE_REPUBLIC_AMOUNT.findall(line)
        if len(amounts) < 2:
            continue
        ordinal += 1
        # Der Saldo steht immer ganz rechts; davor die Bewegung. Eine Beschreibung
        # kann eigene Betraege enthalten ("ATM fee: 1,00 €"), deshalb die letzten beiden.
        amount, balance = _cents(amounts[-2]), _cents(amounts[-1])
        first = line.split(" ")[0] if line else ""
        month = _trade_republic_month(first)
        day = year = None
        for back in range(index, max(index - 8, -1), -1):
            candidate_line = lines[back]
            if month is None:
                head = candidate_line.split(" ")[0] if candidate_line else ""
                found = _trade_republic_month(head)
                if found is None and len(candidate_line.split(" ")) > 1:
                    found = _trade_republic_month(candidate_line.split(" ")[1])
                if found is not None:
                    month = found
            match = TRADE_REPUBLIC_DAY.match(candidate_line)
            if match is not None and TRADE_REPUBLIC_YEAR.match(candidate_line) is None:
                day = int(match.group(1)); break
        for ahead in range(index + 1, min(index + 5, len(lines))):
            match = TRADE_REPUBLIC_YEAR.match(lines[ahead])
            if match is not None:
                year = int(match.group(1)); break
        if amount is None or balance is None or day is None or month is None or year is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "row_unreadable"}); continue
        try:
            local_date = date(year, month, day).isoformat()
        except ValueError:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        # Die Saldoaenderung liefert das Vorzeichen und prueft zugleich den Betrag.
        step_matches = running is None or abs(balance - running) == abs(amount)
        sign = 1 if running is None or balance >= running else -1
        # Auch eine unstimmige Zeile setzt den Saldo neu, sonst schleppt ein
        # einzelner Lesefehler den Rest des Auszugs mit sich.
        running = balance
        if not step_matches:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "balance_step_mismatch"}); continue
        # Eine Bewegung ueber 0,00 EUR gibt es nicht; sie wird gemeldet statt gebucht. Ohne Anfangssaldo (oder bei
        # unveraendertem Saldo) besteht sie die Saldoprobe, ein Kandidat ueber 0 waere aber ungueltig (Selbsttest rc.379:
        # gekippte Bytes im Kopf und im Betrag).
        if amount == 0:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        # Nur ein wirklich erkannter Monat am Zeilenanfang wird entfernt; sonst
        # stuende dort die Buchungsart, und genau die entscheidet ueber den Ertrag.
        text = line[len(first):].strip() if _trade_republic_month(first) is not None else line
        text = TRADE_REPUBLIC_AMOUNT.sub("", text).strip()
        kind = "interest" if sign > 0 and text.lower().startswith("zinsen") else ("deposit" if sign > 0 else "withdrawal")
        # Die Richtung steht in der Art; der Betrag ist immer der Saldoschritt ohne Vorzeichen (die Saldoprobe vergleicht
        # ebenso). Ein Minus vor der Bewegung kennt der Auszug nicht, er kaeme nur aus einem beschaedigten Beleg.
        candidates.append({"source_row_ordinal": ordinal, "local_date": local_date, "kind": kind,
                           "amount_decimal": _plain(abs(amount)), "balance_after_decimal": _plain(balance), "text": text})
    if not candidates:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    summary["period_from"], summary["period_to"] = days[0], days[-1]
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}

TRADE_REPUBLIC_EXPORT_COLUMNS = ("date", "type", "amount", "fee", "tax", "currency", "description")

def _parse_trade_republic_export(source: bytes, file_name: str) -> dict[str, Any]:
    """Trade Republic "transactions" CSV-Export: Ertrag brutto, Steuer in eigener Spalte (#465).

    Der Monatsauszug nennt nur den Betrag, der aufs Konto kam - bei Zinsen also
    nach einbehaltener Kapitalertragsteuer. Dieser Export fuehrt `amount` brutto
    und `tax` getrennt; nur so rechnet der allgemeine Topf
    wie die Bank. Der Kontofluss ist `amount + fee + tax` (Gebuehr und Steuer stehen
    negativ, eine Steuererstattung positiv).

    Der Export traegt keinen Saldo, beweist also keine Vollstaendigkeit; die
    Abdeckung bleibt `partial` beziehungsweise die bestehende Periode.
    """
    try:
        rows = _named_rows(source)
    except (AttributeError, TypeError):
        # named_rows des SDK stolpert ueber doppelte Spaltennamen mit ueberzaehligen Feldern (Selbsttest rc.379: Fremdzeile vor
        # der Kopfzeile); ein echter Export hat eindeutige Spalten.
        _abort("cash_statement_source_invalid")
    if not rows or any(column not in rows[0] for column in TRADE_REPUBLIC_EXPORT_COLUMNS):
        _abort("cash_statement_header_invalid")
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows, 1):
        currency = (row.get("currency") or "").strip()
        try:
            parts = [_english_amount(row.get(column)) for column in ("amount", "fee", "tax")]
        except ArithmeticError:   # "-4e38": cents des SDK rundet so grosse Zahlen nicht auf den Cent (Selbsttest rc.379)
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        raw = [(row.get(column) or "").strip() for column in ("amount", "fee", "tax")]
        if any(value is None and text for value, text in zip(parts, raw)):
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        amount, fee, tax = (value or Decimal("0") for value in parts)
        flow = amount + fee + tax
        if flow == 0 and amount == 0:
            # Einbuchung ohne Geldbewegung (FREE_RECEIPT) - kein Cash-Ereignis.
            continue
        if currency not in ("", "EUR"):
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "currency_unsupported"}); continue
        try:
            local_date = datetime.strptime((row.get("date") or "")[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        interest = (row.get("type") or "").strip().upper() == "INTEREST_PAYMENT" and amount > 0
        if interest and flow == 0:
            # Die Steuer zehrt den Zins ganz auf: auf dem Konto bewegt sich nichts,
            # ein Cash-Ereignis ueber 0 gibt es nicht. Wird gemeldet.
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "interest_fully_taxed",
                                "gross_income_decimal": _plain(amount)}); continue
        if flow == 0:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        candidate = {"source_row_ordinal": ordinal, "local_date": local_date,
                     "kind": "interest" if interest else ("deposit" if flow > 0 else "withdrawal"),
                     "amount_decimal": _plain(abs(flow)), "balance_after_decimal": None,
                     "text": " ".join(part for part in ((row.get("type") or "").strip(), (row.get("description") or "").strip()) if part)}
        if interest and amount != flow:
            candidate["gross_income_decimal"] = _plain(amount)
        candidates.append(candidate)
    if not candidates:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None,
                        "period_from": days[0], "period_to": days[-1]}}


READERS = {
    "trade_republic_v1": _parse_trade_republic,
    "trade_republic_transactions_v1": _parse_trade_republic_export,
}
