"""Leser der Baader-Ertraegnisaufstellung (statement_reader_v1, Bereich income_statement, rc.377).

Unveraendert aus dem bisherigen Steuerbeleg-Import (tax_document_import_v1, #459/#465). Liest den Text der Aufstellung (pdftotext
erzeugt der Kern) und zerlegt ihn in Posten: Art, ISIN, Stueck, Valuta und Zufluss, Kapitalertrag und Anteil an Zeile 7, dazu
Zeile 7 des Summennachweises. Rechnet nichts; die Summe der Posten, den Abgleich mit Zeile 7 und alles Weitere uebernimmt der Kern."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from typing import Any

from portelyra_reader_sdk_v1 import abort

_AMOUNT = re.compile(r"EUR\s+(\d{1,3}(?:\.\d{3})*,\d{2})(\s+-)?\s*$")
_START = re.compile(r"^(\S.*?)\s{2,}(Veräußerung|Dividendenzahlung|Ausschüttung|Ertragsthesaurierung|Zinszahlung.*?|Sollzinsen.*?)\s{2,}.*Transaktion:\s*$")
_LINE7 = "Höhe der Kapitalerträge nach Verlustverrechnung"
_SECTIONS = {
    "Zinserträge aus Kontoguthaben": "interest",
    "Kreditzinsen und Kreditprovisionen": "ignored",
}
# Die Zeile je Posten, die den Kapitalertrag vor Freistellung und Verlustverrechnung traegt.
_PRIMARY = (
    "Gewinn / Verlust aus Aktienveräußerungen",
    "Gewinn / Verlust aus Wertpapierveräußerungen (ohne Aktien)",
    "Ausländische Dividenden und andere laufende Erträge aus Aktien",
    "Inländische Dividenden und andere laufende Erträge aus Aktien",
    "Zinserträge aus Kontoguthaben",
)
_FUND_PREFIX = ("Veräußerung von Investmentfonds", "Ausschüttungen von Investmentfonds", "Investmentfonds")
_EXEMPTION_PREFIX = "Abzüglich / zuzüglich Teilfreistellung"
_TAX_LINE = re.compile(r"^[\d,]+% (Kapitalertragsteuer|Solidaritätszuschlag|Kirchensteuer)")


def _number(text: str, minus: Any) -> Decimal:
    value = Decimal(text.replace(".", "").replace(",", "."))
    return -value if minus else value


def _iso(day: str | None) -> str | None:
    """TT.MM.JJJJ als ISO-Datum; None auch fuer einen Tag, den es nicht gibt (beschaedigter Beleg, Selbsttest rc.379)."""
    if not day or not re.fullmatch(r"\d\d\.\d\d\.\d{4}", day):
        return None
    iso = f"{day[6:10]}-{day[3:5]}-{day[0:2]}"
    try:
        date.fromisoformat(iso)
    except ValueError:
        return None
    return iso


def _read_income(text: str, file_name: str) -> dict[str, Any]:
    """Zerlegt den Text einer Baader-Ertraegnisaufstellung in Posten. Rechnet nichts, liest nur ab.

    Je Posten: Art (sale, dividend, interest; fund, wenn eine Teilfreistellung dabeisteht; ignored fuer Kreditzinsen; unclear,
    wenn die Zeile des Kapitalertrags nicht eindeutig ist), ISIN, Stueck, Valuta und steuerlicher Zufluss, der Kapitalertrag
    ("taxable") und sein Anteil an Zeile 7. Dazu Zeile 7 des Summennachweises und ob die Einzelposten sie ergeben.
    """
    if not isinstance(text, str) or "Erträgnisaufstellung" not in text or "Einzelnachweis der Kapitalerträge" not in text:
        abort("tax_document_source_invalid")
    year = None; summary_line7 = None; in_summary = False; section = None; current = None
    postings: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if year is None and (m := re.search(r"für den Zeitraum vom 01\.01\.(\d{4}) bis 31\.12\.\1", line)):
            year = int(m.group(1))
        if stripped.startswith("Summennachweis der Kapitalerträge"):
            in_summary = True; current = None; continue
        if stripped.startswith("Einzelnachweis der Kapitalerträge"):
            in_summary = False; continue
        if in_summary:
            if stripped.startswith(_LINE7) and summary_line7 is None and (m := _AMOUNT.search(line)):
                summary_line7 = _number(m.group(1), m.group(2))
            continue
        if stripped in _SECTIONS or stripped.startswith(("Laufende Erträge", "Veräußerungen im Sinne")):
            section = stripped; current = None; continue
        if stripped.startswith("Summe"):
            current = None; continue
        if (m := _START.match(line)):
            current = {"ordinal": len(postings) + 1, "name": m.group(1).strip(), "kind_text": m.group(2).strip(), "section": section,
                       "amounts": {}, "isin": None, "quantity": None, "value_date": None, "inflow_date": None, "depot": None,
                       "fund": False, "replacement_base": False, "taxes": Decimal(0), "_depot_next": False}
            if section == "Zinserträge aus Kontoguthaben" and re.fullmatch(r"\d{6,14}", current["name"]):
                current["depot"] = current["name"]
            postings.append(current); continue
        if current is None:
            continue
        if current["_depot_next"] and re.fullmatch(r"[0-9-]{6,20}", stripped):
            current["depot"] = stripped; current["_depot_next"] = False
        if stripped.endswith("Depotnummer:"):
            current["_depot_next"] = True
        if (m := re.search(r"ISIN: ([A-Z]{2}[A-Z0-9]{9}[0-9])", line)):
            current["isin"] = m.group(1)
        if (m := re.search(r"\bSTK\s+([\d.,]+)", line)):
            current["quantity"] = m.group(1)
        if (m := re.search(r"Zufluss: (\d\d\.\d\d\.\d{4}) / (\d\d\.\d\d\.\d{4})", line)):
            current["value_date"], current["inflow_date"] = _iso(m.group(1)), _iso(m.group(2))
        if "Ersatzbemessungsgrundlage" in line:
            current["replacement_base"] = True
        if (m := _AMOUNT.search(line)):
            label = re.split(r"\s{2,}", stripped)[0]
            value = _number(m.group(1), m.group(2))
            if label.startswith(_EXEMPTION_PREFIX):
                current["fund"] = True
            if _TAX_LINE.match(label):
                current["taxes"] += value
            current["amounts"].setdefault(label, value)
    for item in postings:
        item.pop("_depot_next", None)
        amounts = item["amounts"]
        line7 = amounts.get(_LINE7)
        primary = [label for label in _PRIMARY if label in amounts]
        fund_lines = [label for label in amounts if label.startswith(_FUND_PREFIX)]
        exemption = [label for label in amounts if label.startswith(_EXEMPTION_PREFIX)]
        if item["section"] == "Kreditzinsen und Kreditprovisionen" or item["kind_text"].startswith("Sollzinsen"):
            kind, taxable = "ignored", None
        elif item["fund"] and len(fund_lines) == 1 and len(exemption) == 1:
            kind, taxable = "fund", amounts[fund_lines[0]] + amounts[exemption[0]]
        elif len(primary) == 1 and not item["fund"]:
            label = primary[0]
            kind = "interest" if label == "Zinserträge aus Kontoguthaben" else "sale" if label.startswith("Gewinn / Verlust") else "dividend"
            taxable = amounts[label]
        else:
            kind, taxable = "unclear", None
        # Der uebernommene Betrag muss der Anteil des Postens an Zeile 7 sein - sonst ist die Zeile nicht eindeutig.
        if taxable is not None and line7 is not None and taxable != line7:
            kind, taxable = "unclear", None
        item.update(kind=kind, taxable=taxable, line7=line7)
    # Summe der Posten und Abgleich mit Zeile 7 rechnet der Kern selbst nach.
    return {"tax_year": year, "postings": postings, "summary_line7": summary_line7}


def _detect_income(text: str) -> bool:
    return "Erträgnisaufstellung" in text and "Einzelnachweis der Kapitalerträge" in text


READERS = {"baader_income_statement_v1": _read_income}
DETECTORS = {"baader_income_statement_v1": _detect_income}
