"""Portelyra-Leser check24: Cash-Belege (statement_reader_v1, Aufruf read).

Erzeugt aus dem bisherigen Kernmodul (rc.372) ohne Aenderung der Leselogik. Der Leser bekommt Dateiinhalt und
Dateinamen und liefert Kandidaten; er liest keine anderen Dateien, hat kein Netz und schreibt nichts.
"""
from __future__ import annotations

from datetime import date
from datetime import datetime
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


# CHECK24 Geldanlagecenter: die Buchungsliste als Browserdruck. Jede Buchung steht
# als Beschreibung mit Vorzeichenbetrag, ggf. einer Folgezeile, und darunter dem
# Datum; Monats- und Jahreszeilen gliedern die Liste. Ein Saldo wird nicht gedruckt.
CHECK24_AMOUNT = re.compile(r"^(.*?)\s+([+-]\d{1,3}(?:\.\d{3})*,\d{2})\s*€$")

CHECK24_DATE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})$")

CHECK24_INTEREST = ("zinsbuchung", "zinsgutschrift", "habenzinsen")

def _day(text: str) -> str:
    """Datum der Buchung. Ein unmoegliches Datum (Selbsttest rc.379: gekippte Ziffern, etwa 32.12.) weist den Beleg mit Grund ab
    statt abzustuerzen; gueltige Daten liest es wie bisher."""
    try:
        return datetime.strptime(text, "%d.%m.%Y").date().isoformat()
    except ValueError:
        _abort("cash_statement_source_invalid")

def _parse_check24(source: bytes, file_name: str) -> dict[str, Any]:
    lines = [" ".join(line.split()) for line in _pdf_text(source, file_name)]
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    ordinal = 0
    for line in lines:
        amount = CHECK24_AMOUNT.match(line)
        if amount is not None:
            if pending is not None:
                diagnostics.append({"source_row_ordinal": pending["ordinal"], "reason_code": "date_missing"})
            ordinal += 1
            pending = {"ordinal": ordinal, "text": amount.group(1).strip(), "value": _cents(amount.group(2))}
            continue
        if pending is None:
            continue
        stamp = CHECK24_DATE.match(line)
        if stamp is None:
            # Folgezeile der Beschreibung ("Anlagekonto"), Seitenfuss oder -kopf.
            if line and not line.startswith(("http", "Zurück")) and "Geldanlagecenter" not in line:
                pending["text"] = f"{pending['text']} {line}".strip()
            continue
        value = pending["value"]
        if value is None:
            diagnostics.append({"source_row_ordinal": pending["ordinal"], "reason_code": "amount_invalid"})
        elif value == 0:
            pass
        else:
            lowered = pending["text"].lower()
            kind = "interest" if value > 0 and lowered.startswith(CHECK24_INTEREST) else ("deposit" if value > 0 else "withdrawal")
            candidates.append({"source_row_ordinal": pending["ordinal"], "local_date": _day(stamp.group(1)),
                               "kind": kind, "amount_decimal": _plain(abs(value)), "balance_after_decimal": None, "text": pending["text"]})
        pending = None
    if pending is not None:
        diagnostics.append({"source_row_ordinal": pending["ordinal"], "reason_code": "date_missing"})
    if not candidates:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}


READERS = {
    "check24_geldanlage_v1": _parse_check24,
}
