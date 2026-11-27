"""Erzeuger erfundener Bondora-Go-&-Grow-Kontoauszuege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Buchungen samt Guthaben; daraus baut der Erzeuger den Kontoauszug als xlsx (nur
Standardbibliothek: zipfile und XML, unkomprimiert wie der Export, damit die Erkennungsregeln die Zellinhalte sehen) oder als CSV und
- unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf, sonst bestaetigte der Leser nur sich selbst.
Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Namen, Betraege, Tage; die Tage liegen in 2021-2024.

Abgedeckt: Einzahlung, taegliche Zinsen, Abhebung; Kopf mit Zeitraum, "Zu Beginn"/"Ergebnis" (oder englisch, oder
Anfangs-/Endsaldo), nur Zeitraum oder gar kein Kopf; Spalten deutsch oder englisch; Zellen als Inline-Text, gemeinsame Zeichenketten
oder Zahl; Gleitkomma-Rauschen (0.30000000000000004); Komma oder Punkt; Leerzeile in der Liste, Zins ueber 0,00 und Summenzeile
(je ein Hinweis bzw. uebergangen). Ein Teil der Startwerte liefert CSV (Semikolon oder Komma) statt xlsx.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal
import io
import random
from typing import Any
from xml.sax.saxutils import escape
import zipfile

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE = "http://schemas.openxmlformats.org/package/2006/relationships"
OWNERS = ("Invented Owner", "Erika Erfunden", "Max Beispiel", "Petra Fantasie")
# Sprache: Kopfzeile, Zahlungsarten (Einzahlung, Zinsen, Abhebung), Beschriftungen des Kopfes
LANGUAGES = {
    "de": {"header": ("Datum", "Zahlungsart", "Eingänge", "Ausgänge", "Guthaben"),
           "kinds": ("SEPA-Banküberweisung", "Go & Grow Zinsen", "Abhebung"), "summary": "Zusammenfassung", "goals": "Alle Ziele",
           "labels": (("Zu Beginn", "Ergebnis"), ("Anfangssaldo", "Endsaldo")), "sums": ("Einzahlungen", "Auszahlungen"), "total": "Summe"},
    "en": {"header": ("Date", "Payment type", "In", "Out", "Balance"),
           "kinds": ("SEPA bank transfer", "Go & Grow interest", "Withdrawal"), "summary": "Summary", "goals": "All goals",
           "labels": (("Opening balance", "Closing balance"),), "sums": ("Deposits", "Withdrawals"), "total": "Total"},
}


def _plain(amount: Decimal) -> str:
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _column(index: int) -> str:
    return "ABCDEFGHIJ"[index]


def _xlsx(rows: list[list[Any]], shared: bool) -> bytes:
    """Gueltige xlsx-Datei: Pakettypen, Beziehungen, Arbeitsmappe, ein Blatt, auf Wunsch gemeinsame Zeichenketten. Zellen sind
    None (leer), ("s", Text) oder ("n", Zahl als Text); eine leere Liste ist eine Leerzeile."""
    strings: list[str] = []
    body = []
    for number, row in enumerate(rows, 1):
        cells = []
        for index, cell in enumerate(row):
            if cell is None:
                continue
            kind, value = cell
            reference = f"{_column(index)}{number}"
            if kind == "n":
                cells.append(f'<c r="{reference}" t="n"><v>{value}</v></c>')
            elif shared:
                if value not in strings:
                    strings.append(value)
                cells.append(f'<c r="{reference}" t="s"><v>{strings.index(value)}</v></c>')
            else:
                cells.append(f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{escape(value)}</t></is></c>')
        body.append(f'<row r="{number}">{"".join(cells)}</row>' if cells else f'<row r="{number}"/>')
    head = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    parts = {
        "[Content_Types].xml": head + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        + ('<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
           if shared else "") + "</Types>",
        "_rels/.rels": head + f'<Relationships xmlns="{PACKAGE}"><Relationship Id="rId1" Type="{RELATIONS}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": head + f'<workbook xmlns="{MAIN}" xmlns:r="{RELATIONS}"><sheets><sheet name="Kontoauszug" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": head + f'<Relationships xmlns="{PACKAGE}"><Relationship Id="rId1" Type="{RELATIONS}/worksheet" Target="worksheets/sheet1.xml"/>'
        + (f'<Relationship Id="rId2" Type="{RELATIONS}/sharedStrings" Target="sharedStrings.xml"/>' if shared else "") + "</Relationships>",
        "xl/worksheets/sheet1.xml": head + f'<worksheet xmlns="{MAIN}"><sheetData>{"".join(body)}</sheetData></worksheet>',
    }
    if shared:
        parts["xl/sharedStrings.xml"] = head + f'<sst xmlns="{MAIN}" count="{len(strings)}" uniqueCount="{len(strings)}">' + "".join(
            f'<si><t xml:space="preserve">{escape(value)}</t></si>' for value in strings) + "</sst>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name, text in parts.items():
            info = zipfile.ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))   # feste Zeit: gleicher Startwert, gleiche Bytes
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, text.encode("utf-8"))
    return buffer.getvalue()


def _generate(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    language = LANGUAGES["de" if rng.random() < 0.7 else "en"]
    as_csv = rng.random() < 0.2
    comma = rng.random() < 0.5 if as_csv else rng.random() < 0.15   # Dezimalkomma "1.000,50" statt "1000.50"
    numbers = not as_csv and rng.random() < 0.4                     # Betraege als Zahlzellen statt als Text
    shared = not as_csv and rng.random() < 0.4

    def money(value: Decimal, noisy: bool = False) -> str:
        if noisy and not comma:   # Tabellen speichern Cent als Gleitkommazahl: 0.30000000000000004, 999.99999999999
            return format(value + rng.choice((Decimal("1E-12"), Decimal("4E-17"), -Decimal("1E-11"))), "f")
        if not comma:
            return f"{value:.2f}"
        whole, cents = f"{value:.2f}".split(".")
        groups = []
        while len(whole) > 3:
            groups.insert(0, whole[-3:]); whole = whole[:-3]
        groups.insert(0, whole)
        return f"{'.'.join(groups)},{cents}"

    cell = lambda value: ("n", value) if numbers and not comma else ("s", value)
    text = lambda value: ("s", value)
    start = date(2021, 1, 1) + timedelta(days=rng.randrange(0, 1300))
    opening = Decimal(rng.randrange(0, 300_000)) / 100 if rng.random() < 0.7 else Decimal("0")
    balance = opening
    deposit, interest, withdrawal = language["kinds"]
    data: list[list[Any]] = []
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    day = start
    total_in = total_out = Decimal("0")
    for number in range(rng.randrange(1, 60)):
        if number:
            day += timedelta(days=rng.choice((0, 1, 1, 1, 2)))
        roll = rng.random()
        if number and roll < 0.03:
            data.append([]); continue                       # Leerzeile: uebergangen, zaehlt aber als Zeile
        if roll < 0.12 or number == 0 and balance < 10:
            kind, inflow, outflow = deposit, Decimal(rng.randrange(1_000, 500_000)) / 100, None
        elif roll < 0.2 and balance > 1:
            kind, inflow, outflow = withdrawal, None, Decimal(rng.randrange(1, int(balance * 100) + 1)) / 100
        else:
            kind, inflow, outflow = interest, (balance * Decimal("0.0002")).quantize(Decimal("0.01")), None
        noisy = rng.random() < 0.2
        ordinal = len(data) + 1
        if inflow is not None and inflow == 0:              # Zins ueber 0,00: weder Eingang noch Ausgang - ein Hinweis
            data.append([text(day.strftime("%d.%m.%Y")), text(kind), cell(money(inflow)), text(""), cell(money(balance))])
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        balance += (inflow or Decimal("0")) - (outflow or Decimal("0"))
        total_in += inflow or Decimal("0")
        total_out += outflow or Decimal("0")
        data.append([text(day.strftime("%d.%m.%Y")), text(kind),
                     cell(money(inflow, noisy)) if inflow is not None else text(""),
                     cell(money(outflow, noisy)) if outflow is not None else text(""), cell(money(balance, noisy))])
        is_interest = inflow is not None and ("zins" in kind.lower() or "interest" in kind.lower())
        candidates.append({"source_row_ordinal": ordinal, "local_date": day.isoformat(),
                           "kind": "interest" if is_interest else ("deposit" if inflow is not None else "withdrawal"),
                           "amount_decimal": _plain(inflow if inflow is not None else outflow), "balance_after_decimal": _plain(balance),
                           "text": kind})
    if rng.random() < 0.15:                                 # Summenzeile am Ende: kein Datum - ein Hinweis
        data.append([text(language["total"]), text(""), cell(money(total_in)), cell(money(total_out)), text("")])
        diagnostics.append({"source_row_ordinal": len(data), "reason_code": "date_invalid"})
    end = day + timedelta(days=rng.randrange(0, 5))
    head_kind = rng.choice(("full", "full", "full", "full", "period", "none"))
    opening_label, closing_label = rng.choice(language["labels"])
    period = f"{start:%d.%m.%Y}{rng.choice(('-', ' - '))}{end:%d.%m.%Y}"
    rows: list[list[Any]] = []
    if head_kind == "full":
        rows = [[text(rng.choice(OWNERS)), None, None, text(language["summary"])],
                [text(period), None, None, text(opening_label), cell(money(opening))],
                [None, None, None, text(language["sums"][0]), cell(money(total_in))],
                [None, None, None, text(language["sums"][1]), cell(money(total_out))],
                [None, None, None, text(closing_label), cell(money(balance))],
                [text(language["goals"])]]
    elif head_kind == "period":
        rows = [[text(rng.choice(OWNERS))], [text(period)], [text(language["goals"])]]
    rows.append([text(name) for name in language["header"]])
    rows.extend(data)
    summary = {"opening_balance_decimal": _plain(opening) if head_kind == "full" else None,
               "closing_balance_decimal": _plain(balance) if head_kind == "full" else None,
               "period_from": start.isoformat() if head_kind != "none" else None, "period_to": end.isoformat() if head_kind != "none" else None}
    expected = {"candidates": candidates, "diagnostics": diagnostics, "summary": summary}
    if as_csv:
        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";" if comma else ",", lineterminator=rng.choice(("\n", "\r\n")))
        writer.writerows([["" if item is None else item[1] for item in row] for row in rows])
        content = (("﻿" if rng.random() < 0.5 else "") + buffer.getvalue()).encode("utf-8")
        return {"file_name": f"bondora-erfunden-{seed}.csv", "content": content, "expected": expected}
    return {"file_name": f"bondora-erfunden-{seed}.xlsx", "content": _xlsx(rows, shared), "expected": expected}


GENERATORS = {"bondora_go_grow_v1": _generate}
