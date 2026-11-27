"""Portelyra-Leser dkb: Cash-Belege (statement_reader_v1, Aufruf read).

Erzeugt aus dem bisherigen Kernmodul (rc.372) ohne Aenderung der Leselogik. Der Leser bekommt Dateiinhalt und
Dateinamen und liefert Kandidaten; er liest keine anderen Dateien, hat kein Netz und schreibt nichts.
"""
from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
import csv
import io
import re
from typing import Any

from portelyra_reader_sdk_v1 import (
    CENT,
    ReaderError as CashStatementImportV1Error,
    abort as _abort,
    cents as _cents,
    german_amount as _german_amount,
    pdf_text as _pdf_text,
    plain as _plain,
)


# DKB "Kontoauszug" als PDF, zwei Vorlagen (#465/#467). Aeltere Vorlage:
# Buchungstag und Wertstellung ohne Jahr, der Betrag steht vorzeichenlos in der
# Spalte Belastung oder Gutschrift - allein die Spalte entscheidet. Neuere Vorlage:
# volles Datum, Soll mit Minus. Beide Vorlagen tragen Anfangs- und Endsaldo, der
# Stapel prueft die Kette daraus.
DKB_PDF_PERIOD = re.compile(r"Kontoauszug Nummer\s+\d+\s*/\s*\d{4}\s+vom\s+(\d{2}\.\d{2}\.\d{4})\s+bis\s+(\d{2}\.\d{2}\.\d{4})")

DKB_PDF_OLD_BALANCE = re.compile(r"^(ALTER|NEUER) KONTOSTAND\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s*([HS])\s*EUR")

DKB_PDF_OLD_BOOKING = re.compile(r"^\s*(\d{2}\.\d{2})\.\s+(\d{2}\.\d{2})\.\s+(.+?)\s+(\d{1,3}(?:\.\d{3})*,\d{2})\s*$")

DKB_PDF_NEW_OPENING = re.compile(r"Kontostand am (\d{2}\.\d{2}\.\d{4}), Auszug Nr\.\s*\d+\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$")

DKB_PDF_NEW_CLOSING = re.compile(r"Kontostand am (\d{2}\.\d{2}\.\d{4}) um \d{2}:\d{2} Uhr\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$")

DKB_PDF_NEW_BOOKING = re.compile(r"^\s*(\d{2}\.\d{2}\.\d{4})\s+(.+?)\s+(-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$")

DKB_PDF_INTEREST = ("zinsen", "zinsertrag", "zinsgutschrift", "habenzinsen")

def _date(text: str) -> date:
    """Datum aus Kopf, Saldozeile oder Buchung. Ein unmoegliches Datum (Selbsttest rc.379: gekippte Ziffern, etwa 01.37.) weist den
    Beleg mit Grund ab statt abzustuerzen; gueltige Daten liest es wie bisher."""
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        _abort("cash_statement_source_invalid")

def _dkb_pdf_year(day_month: str, period_from: str, period_to: str) -> str:
    """Das alte Format nennt nur Tag und Monat; das Jahr steht im Auszugskopf.

    Laeuft ein Auszug ueber den Jahreswechsel, gilt: Ein
    Monat vor dem Startmonat gehoert dann in das Jahr des Auszugsendes.
    """
    day, month = day_month.split(".")
    start, end = date.fromisoformat(period_from), date.fromisoformat(period_to)
    year = start.year if int(month) >= start.month or start.year == end.year else end.year
    try:   # ein unmoeglicher Tag (31.02.) ergaebe sonst ein ungueltiges Datum im Ergebnis (Selbsttest rc.379)
        return date(year, int(month), int(day)).isoformat()
    except ValueError:
        _abort("cash_statement_source_invalid")

def _dkb_old_sign(rows: list[tuple[Decimal, int]], credit_column: int, opening: Decimal | None, closing: Decimal | None) -> int:
    """Welche Spalte traegt die Gutschrift? Die Saldokette des Auszugs entscheidet.

    Die Spaltenpositionen stehen im Auszug nicht fest: Gutschriftbetraege enden je
    Beleg mal rechts, mal links der Spaltenueberschrift,
    sodass eine feste Grenze aus dem Kopf grosse Gutschriften als Belastung lesen
    koennte - der Saldo ginge dann um den doppelten Betrag nicht auf. Geprueft
    werden deshalb die Grenze aus dem Kopf und die Mitten zwischen den
    tatsaechlichen Endpositionen; es gilt die erste, die ALTER + Bewegungen = NEUER
    erfuellt, und bei gleichem Beleg die dem Kopf naechste (#467).
    """
    if opening is None or closing is None or not rows:
        return credit_column
    ends = sorted({end for _value, end in rows})
    borders = [credit_column] + [(left + right) // 2 for left, right in zip(ends, ends[1:])] + [min(ends) - 1, max(ends)]
    for border in sorted(set(borders), key=lambda value: abs(value - credit_column)):
        total = sum(value if end > border else -value for value, end in rows)
        if opening + total == closing:
            return border
    return credit_column

def _parse_dkb_kontoauszug(source: bytes, file_name: str) -> dict[str, Any]:
    """DKB Girokonto-Kontoauszug (PDF), alte und neue Vorlage."""
    lines = [line.rstrip() for line in _pdf_text(source, file_name)]
    header = next((line for line in lines if "Belastung in EUR" in line or "Betrag Haben EUR" in line), None)
    if header is None:
        _abort("cash_statement_header_invalid")
    old = "Belastung in EUR" in header
    credit_column = header.find("Gutschrift in EUR" if old else "Betrag Haben EUR")
    summary: dict[str, Any] = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": None, "period_to": None}
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    period_from = period_to = None
    for line in lines:
        period = DKB_PDF_PERIOD.search(line)
        if period:
            period_from, period_to = (_date(item).isoformat() for item in period.groups())
            summary["period_from"], summary["period_to"] = period_from, period_to
    raw_rows: list[tuple[Decimal, int, str, str]] = []  # Betrag, Endposition, Tag, Text
    for line in lines:
        if old:
            balance = DKB_PDF_OLD_BALANCE.match(line.strip())
            if balance is not None:
                value = _cents(balance.group(2))
                if value is None:
                    continue
                if balance.group(3) == "S":
                    value = -value
                if balance.group(1) == "ALTER" and summary["opening_balance_decimal"] is None:
                    summary["opening_balance_decimal"] = value
                elif balance.group(1) == "NEUER":
                    summary["closing_balance_decimal"] = value
                    summary["closing_as_of_date"] = period_to
                continue
            booking = DKB_PDF_OLD_BOOKING.match(line)
            if booking is None or period_from is None:
                continue
            raw, text = booking.group(4), booking.group(3).strip()
            value = _german_amount(raw)
            if value is None:
                diagnostics.append({"source_row_ordinal": len(raw_rows) + 1, "reason_code": "amount_invalid"}); continue
            if value != 0:
                raw_rows.append((value, line.rindex(raw) + len(raw), _dkb_pdf_year(booking.group(1), period_from, period_to), text))
            continue
        opening = DKB_PDF_NEW_OPENING.search(line)
        if opening is not None:
            if summary["opening_balance_decimal"] is None:
                summary["opening_balance_decimal"] = _cents(opening.group(2))
                # "Kontostand am X, Auszug Nr. N" ist der Schlusssaldo des Vorauszugs und
                # gilt am Ende dieses Tages; der Zeitraum beginnt deshalb am Tag danach.
                # Eine Bewegung am Saldotag selbst gibt es nicht.
                summary["period_from"] = (_date(opening.group(1)) + timedelta(days=1)).isoformat()
            continue
        closing = DKB_PDF_NEW_CLOSING.search(line)
        if closing is not None:
            summary["closing_balance_decimal"] = _cents(closing.group(2))
            summary["period_to"] = summary["closing_as_of_date"] = _date(closing.group(1)).isoformat()
            continue
        booking = DKB_PDF_NEW_BOOKING.match(line)
        if booking is None:
            continue
        raw, text = booking.group(3), booking.group(2).strip()
        value = _german_amount(raw)
        if value is None:
            diagnostics.append({"source_row_ordinal": len(raw_rows) + 1, "reason_code": "amount_invalid"}); continue
        # Die neue Vorlage traegt das Minus; die Spalte ist nur die Gegenprobe.
        if value > 0 and line.rindex(raw) + len(raw) <= credit_column:
            diagnostics.append({"source_row_ordinal": len(raw_rows) + 1, "reason_code": "column_sign_mismatch"}); continue
        if value != 0:
            raw_rows.append((value, line.rindex(raw) + len(raw),
                             _date(booking.group(1)).isoformat(), text))
    opening_value = summary["opening_balance_decimal"]
    closing_value = summary["closing_balance_decimal"]
    border = _dkb_old_sign([(value, end) for value, end, _day, _text in raw_rows], credit_column,
                           opening_value, closing_value) if old else credit_column
    for ordinal, (value, end, local_date, text) in enumerate(raw_rows, 1):
        signed = value if not old else (value if end > border else -value)
        lowered = text.lower()
        interest = signed > 0 and any(marker in lowered for marker in DKB_PDF_INTEREST)
        candidates.append({"source_row_ordinal": ordinal, "local_date": local_date,
                           "kind": "interest" if interest else ("deposit" if signed > 0 else "withdrawal"),
                           "amount_decimal": _plain(abs(signed)), "balance_after_decimal": None, "text": text})
    if not candidates and summary["closing_balance_decimal"] is None:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    if summary["period_from"] is None and days:
        summary["period_from"], summary["period_to"] = days[0], days[-1]
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}

# DKB Umsatzliste (Giro und Tagesgeld): je Jahr eine CSV mit Zeitraum und dem
# Kontostand am Exporttag. Jede Quartalsabrechnung nennt ausserdem "Kontostand am
# <Tag>" - den Saldo am Ende dieses Tages ohne die Abrechnung selbst. Diese
# Stuetzpunkte belegen die Vollstaendigkeit. Auf dem Tagesgeld ist der Betrag der
# Abrechnung netto; "Zinsen fuer Guthaben 12,34+" im Text ist der Bruttozins.
DKB_PERIOD = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s*-\s*(\d{2}\.\d{2}\.\d{4})")

DKB_EXPORT_BALANCE = re.compile(r"Kontostand vom (\d{2}\.\d{2}\.\d{4}):?\s*(-?[\d.]+(?:,\d{1,2})?)")

DKB_CHECKPOINT = re.compile(r"Kontostand am (\d{2}\.\d{2}\.\d{4}) ([\d.]+,\d{2}) ([+-])")

DKB_GROSS_INTEREST = re.compile(r"Zinsen für Guthaben ([\d.]+,\d{2})\+")

def _parse_dkb(source: bytes, file_name: str) -> dict[str, Any]:
    text = source.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    header_index = next((index for index, line in enumerate(lines) if line.startswith('"Buchungsdatum"')), None)
    if header_index is None:
        _abort("cash_statement_header_invalid")
    preamble = " ".join(" ".join(line.replace('"', " ").replace(";", " ").split()) for line in lines[:header_index])
    period = DKB_PERIOD.search(preamble)
    export = DKB_EXPORT_BALANCE.search(preamble)
    try:
        rows = list(csv.reader(io.StringIO("\n".join(lines[header_index:])), delimiter=";"))
    except csv.Error:   # etwa ein Nullbyte in einer beschaedigten Datei (Selbsttest rc.379)
        _abort("cash_statement_source_invalid")
    header = rows[0]
    # Alle Pflichtspalten vorab (Selbsttest rc.379: eine beschaedigte Kopfzeile wies sonst mit Absturz statt mit Grund ab).
    if any(column not in header for column in ("Betrag (€)", "Verwendungszweck", "Zahlungspflichtige*r", "Zahlungsempfänger*in")):
        _abort("cash_statement_header_invalid")
    c_amount, c_purpose = header.index("Betrag (€)"), header.index("Verwendungszweck")
    c_payer, c_payee = header.index("Zahlungspflichtige*r"), header.index("Zahlungsempfänger*in")
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    checkpoints: list[tuple[str, Decimal, str, Decimal]] = []
    movements: list[tuple[str, Decimal]] = []
    for ordinal, row in enumerate(rows[1:], 1):
        if len(row) <= c_amount or not row[0].strip():
            continue
        try:
            local_date = datetime.strptime(row[0].strip(), "%d.%m.%y").date().isoformat()
        except ValueError:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        value = _german_amount(row[c_amount])
        purpose = " ".join(row[c_purpose].split())
        if value is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        for point in DKB_CHECKPOINT.finditer(purpose):
            signed = _german_amount(point.group(2)) * (1 if point.group(3) == "+" else -1)
            checkpoints.append((_date(point.group(1)).isoformat(), signed, local_date, value))
        if value == 0:
            continue
        movements.append((local_date, value))
        gross = DKB_GROSS_INTEREST.search(purpose)
        counterparty = row[c_payee] if value < 0 else row[c_payer]
        candidate = {"source_row_ordinal": ordinal, "local_date": local_date,
                     "kind": "interest" if value > 0 and gross is not None else ("deposit" if value > 0 else "withdrawal"),
                     "amount_decimal": _plain(abs(value)), "balance_after_decimal": None,
                     "text": " ".join(part for part in (counterparty.strip(), purpose[:120]) if part)}
        if candidate["kind"] == "interest" and _german_amount(gross.group(1)) != value:
            candidate["gross_income_decimal"] = _plain(_german_amount(gross.group(1)))
        candidates.append(candidate)
    summary: dict[str, Any] = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": None, "period_to": None}
    if period is not None:
        summary["period_from"], summary["period_to"] = (_date(item).isoformat() for item in period.groups())
    total = sum((value for _day, value in movements), Decimal("0"))
    # Saldo am Ende eines Tages, ohne die Abrechnung, die diesen Stuetzpunkt traegt.
    balance_through = lambda opening, day, carrier_day, carrier_value: opening + sum(
        (value for moved, value in movements if moved <= day), Decimal("0")) - (carrier_value if carrier_day <= day else Decimal("0"))
    anchors = 0
    opening: Decimal | None = None
    if export is not None and summary["period_to"] is not None and summary["period_to"] >= _date(export.group(1)).isoformat():
        export_balance = _german_amount(export.group(2))
        if export_balance is None:   # nur Punkte statt Ziffern (Selbsttest rc.379): beschaedigt, mit Grund abweisen
            _abort("cash_statement_source_invalid")
        opening = export_balance - total; anchors += 1
    elif checkpoints:
        day, value, carrier_day, carrier_value = checkpoints[-1]
        opening = value - balance_through(Decimal("0"), day, carrier_day, carrier_value); anchors += 1
        checkpoints = checkpoints[:-1]
    proven = opening is not None
    for day, value, carrier_day, carrier_value in checkpoints:
        anchors += 1
        if balance_through(opening, day, carrier_day, carrier_value) != value:
            proven = False
            diagnostics.append({"source_row_ordinal": 0, "reason_code": "balance_checkpoint_mismatch", "as_of_date": day})
    if opening is not None:
        summary["opening_balance_decimal"] = opening
        summary["closing_balance_decimal"] = opening + total
    if not candidates and opening is None:
        _abort("cash_statement_header_invalid")
    if summary["period_from"] is None and candidates:
        days = sorted(row["local_date"] for row in candidates)
        summary["period_from"], summary["period_to"] = days[0], days[-1]
    return {"candidates": candidates, "diagnostics": diagnostics,
            # Ein einzelner Saldo beweist nichts: Anfang und Ende sind dann nur abgeleitet.
            # Im Ordner kann ihn die Kette zum bewiesenen Vorgaenger tragen.
            "balance_proof": proven and anchors >= 2, "balance_anchor_only": proven and anchors == 1,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}


READERS = {
    "dkb_kontoauszug_v1": _parse_dkb_kontoauszug,
    "dkb_umsatzliste_v1": _parse_dkb,
}
