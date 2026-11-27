"""Portelyra-Leser bsdex: Euro-Guthaben (statement_reader_v1, Aufruf read/combine_documents).

Erzeugt aus dem bisherigen Kernmodul (rc.375) ohne Aenderung der Leselogik. Der Stapel liest Export und Jahreshistorie
zusammen (je Order auf den Cent); die Funktionen der Zuordnung nutzt auch der Krypto-Teil dieses Plugins.
"""
from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation
from zoneinfo import ZoneInfo
import csv
import hashlib
import io
import re
from typing import Any, Mapping, Sequence

from portelyra_reader_sdk_v1 import (
    CENT,
    ReaderError as CashStatementImportV1Error,
    TIME_ZONE,
    abort as _abort,
    cash_exchange_result as _exchange_result,
    cash_exchange_row as _exchange_row,
    german_amount as _german_amount,
    named_rows as _named_rows,
    plain as _plain,
)


# BSDEX (rc.325): Euro-Guthaben je Order, auf den Cent. Eine Limit-Order wird oft in mehreren Teilen ausgefuehrt, und BSDEX bucht
# jede Ausfuehrung einzeln gerundet ab; der Export "Transaktionen" nennt je Order nur "Gefüllt" und "Transaktionsentgelt" und rundet
# einmal. Die "Transaktionshistorie" je Jahr nennt jede Ausfuehrung mit Euro-Betrag und Gebuehr, aber keine Order. Gebucht wird je
# Order (keine Teilbuchungen), der Betrag ist die Summe ihrer
# Ausfuehrungen samt Gebuehren, je Ausfuehrungstag (rc.327).
BSDEX_EXPORT_HEAD = ["Transaktionstyp", "Kryptowährung", "Betrag"]

BSDEX_EXPORT_COLUMNS = ("Betrag", "Seite", "Gefüllt", "Ausgeführter Gesamtbetrag", "Status", "Transaktionsentgelt", "Erstellt", "Finalisiert am")

# Der Export enthaelt alle Typen und Zustaende (rc.326): Es zaehlt nur, was ausgefuehrt ist. Eine Order ohne
# ausgefuehrte Menge (storniert oder offen) spielt keine Rolle; eine stornierte mit Teilausfuehrung zaehlt mit diesem Teil (Ende =
# "Storniert"); eine noch offene mit Teilausfuehrung wartet auf ihren Abschluss. "Bestellstatus" und "Storniert" fehlen aelteren Exporten.
BSDEX_EXPORT_OPTIONAL = ("Bestellstatus", "Storniert")

BSDEX_OPEN = "Offen"

BSDEX_HISTORY_COLUMNS = ("ID", "Typ", "Ausführung", "eingehender Betrag", "eingehendes Asset", "ausgehender Betrag", "ausgehendes Asset",
                         "Transaktionsentgelt", "Entgeltwährung")

BSDEX_SIDES = {"Kaufen": "buy", "Verkaufen": "sell"}

BSDEX_LABELS = {"buy": "Kauf", "sell": "Verkauf", "deposit": "Einzahlung", "withdrawal": "Auszahlung"}

# Der Export nennt Minuten in Berlin, die Historie Sekunden in UTC: eine Ausfuehrung gehoert zu einer Order, wenn sie zwischen
# "Erstellt" und "Finalisiert am" liegt, mit zwei Minuten Spiel an beiden Enden.
BSDEX_WINDOW = timedelta(minutes=2)

BSDEX_OPEN_UNTIL = datetime(9999, 12, 31, tzinfo=ZoneInfo("UTC"))   # eine offene Order nimmt alle spaeteren Ausfuehrungen in Betracht

BSDEX_SEARCH_STEPS = 200_000

def _bsdex_quantity(text: str) -> Decimal | None:
    """Coin-Menge im Export ("12,5 XRP", "1.234,5 XRP"): volle Stellen, nicht auf Cent gerundet."""
    raw = re.sub(r"[^\d,.\-]", "", text or "")
    if not raw:
        return None
    try:
        return Decimal(raw.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None

def _bsdex_berlin(text: str) -> datetime | None:
    try:
        return datetime.strptime((text or "").strip(), "%d.%m.%Y, %H:%M").replace(tzinfo=ZoneInfo(TIME_ZONE))
    except ValueError:
        return None

def _bsdex_export(source: bytes, file_name: str) -> dict[str, Any] | None:
    """Export "Transaktionen": ausgefuehrte Limit-Orders und Euro-Ein- und -Auszahlungen; None, wenn die Datei keiner ist."""
    try:
        rows = list(csv.reader(io.StringIO(source.decode("utf-8-sig", errors="replace"))))
    except csv.Error:   # beschaedigte Datei, etwa ein Zeilenumbruch mitten im Feld (Selbsttest rc.379): kein Export
        return None
    if not rows or [cell.strip().lstrip("﻿") for cell in rows[0][:3]] != BSDEX_EXPORT_HEAD:
        return None
    header = [cell.strip().lstrip("﻿") for cell in rows[0]]
    if any(name not in header for name in BSDEX_EXPORT_COLUMNS):
        return None
    index = {name: header.index(name) for name in BSDEX_EXPORT_COLUMNS + BSDEX_EXPORT_OPTIONAL if name in header}   # doppelte Spaltennamen: die erste zaehlt
    orders: list[dict[str, Any]] = []
    flows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows[1:], 1):
        if not row or len(row) < 13:
            continue
        cell = lambda name: row[index[name]].strip() if name in index and index[name] < len(row) else ""
        kind, coin = row[0].strip(), row[1].strip()
        side = BSDEX_SIDES.get(cell("Seite"))
        quantity = _bsdex_quantity(cell("Ausgeführter Gesamtbetrag")) if side is not None else None
        is_order = side is not None and (quantity is None or quantity > 0)   # jede Orderart (Limit, Market, Stop) mit ausgefuehrter Menge
        is_flow = side is None and kind in ("Einzahlungen", "Einzahlung", "Auszahlung") and coin == ""
        if not is_order and not is_flow:
            continue
        created = _bsdex_berlin(cell("Erstellt"))
        finished = _bsdex_berlin(cell("Finalisiert am")) or (_bsdex_berlin(cell("Storniert")) if is_order else None)
        is_open = is_order and (cell("Bestellstatus") == BSDEX_OPEN if "Bestellstatus" in index else cell("Status") != "Ausgeführt" and finished is None)
        moment = finished or created
        if moment is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid", "file_name": file_name}); continue
        if is_flow:
            value = _german_amount(cell("Betrag"))
            if value is None:
                diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid", "file_name": file_name}); continue
            flows.append({"ordinal": ordinal, "file_name": file_name, "local_date": moment.date().isoformat(),
                          "cash": -value if kind == "Auszahlung" else value, "label": "Auszahlung" if kind == "Auszahlung" else "Einzahlung",
                          "key": (kind, _plain(value), cell("Erstellt"), cell("Finalisiert am"))})
            continue
        filled, fee = _german_amount(cell("Gefüllt")), _german_amount(cell("Transaktionsentgelt")) or Decimal("0")
        if filled is None or quantity is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid", "file_name": file_name}); continue
        unit = re.search(r"([A-Za-z]{2,10})\s*$", cell("Ausgeführter Gesamtbetrag").replace("\xa0", " "))
        orders.append({"ordinal": ordinal, "file_name": file_name, "side": side, "coin": coin, "unit": unit.group(1) if unit else coin,
                       "quantity": quantity, "filled": filled, "fee": fee, "open": is_open, "identity": (side, coin, cell("Erstellt"), cell("Betrag")),
                       "from": (created or moment).astimezone(ZoneInfo("UTC")) - BSDEX_WINDOW,
                       "to": BSDEX_OPEN_UNTIL if is_open else moment.astimezone(ZoneInfo("UTC")) + BSDEX_WINDOW,
                       "local_date": (created or moment).date().isoformat() if is_open else moment.date().isoformat(),
                       "key": (side, coin, _plain(quantity), _plain(filled), _plain(fee), cell("Erstellt"), cell("Finalisiert am") or cell("Storniert"),
                               "open" if is_open else "closed")})
    return {"orders": orders, "flows": flows, "diagnostics": diagnostics}

def _bsdex_history(source: bytes, file_name: str) -> dict[str, Any] | None:
    """Transaktionshistorie je Jahr: Ausfuehrungen (Kauf, Verkauf) und Euro-Bewegungen sonst; None, wenn die Datei keine ist.
    "Ausführung" steht in UTC; Kauf kostet Betrag + Gebuehr, Verkauf bringt Betrag - Gebuehr. Eine Euro-Gebuehr an einem
    Coin-Ausgang mindert das Guthaben ebenso."""
    try:
        rows = _named_rows(source)
    except CashStatementImportV1Error:
        return None
    if not rows or any(column not in rows[0] for column in BSDEX_HISTORY_COLUMNS):
        return None
    fills: list[dict[str, Any]] = []
    flows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows, 1):
        kind = row["Typ"].strip().lower()
        incoming, outgoing = row["eingehendes Asset"].strip(), row["ausgehendes Asset"].strip()
        try:
            moment = datetime.strptime(row["Ausführung"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC"))
        except ValueError:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid", "file_name": file_name}); continue
        try:
            fee = Decimal(row["Transaktionsentgelt"]) if row["Transaktionsentgelt"] and row["Entgeltwährung"] == "EUR" else Decimal("0")
            amount_in = Decimal(row["eingehender Betrag"]) if row["eingehender Betrag"] else Decimal("0")
            amount_out = Decimal(row["ausgehender Betrag"]) if row["ausgehender Betrag"] else Decimal("0")
        except InvalidOperation:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid", "file_name": file_name}); continue
        if not all(value.is_finite() and value >= 0 for value in (fee, amount_in, amount_out)):
            # Die Richtung steht in der Spalte, ein Betrag ist nie negativ; "NaN" oder ein Minus heisst: Zahl nicht lesbar (Selbsttest
            # rc.379, gekippte Bytes - sonst Absturz beim Vergleich oder ein Beleg, den der Kern verwirft).
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid", "file_name": file_name}); continue
        identity = row["ID"].strip() or f"{file_name}:{ordinal}"
        if kind in ("buy", "sell") and (outgoing if kind == "buy" else incoming) == "EUR":
            buy = kind == "buy"
            fills.append({"id": identity, "ordinal": ordinal, "file_name": file_name, "side": kind, "asset": incoming if buy else outgoing,
                          "quantity": amount_in if buy else amount_out, "eur": amount_out if buy else amount_in, "fee": fee, "at": moment})
            continue
        cash = (amount_in if incoming == "EUR" else Decimal("0")) - (amount_out if outgoing == "EUR" else Decimal("0")) - fee
        if cash == 0:
            continue
        coin = next((asset for asset in (incoming, outgoing) if asset and asset != "EUR"), "")
        label = BSDEX_LABELS.get(kind, kind) if (incoming == "EUR" or outgoing == "EUR") else " ".join(part for part in ("Gebühr", coin) if part)
        flows.append({"id": identity, "ordinal": ordinal, "file_name": file_name, "at": moment, "cash": cash, "label": label})
    return {"fills": fills, "flows": flows, "diagnostics": diagnostics}

def _bsdex_pick(order: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]] | None:
    """Welche Ausfuehrungen ergeben die Menge der Order? Ueberlappen Orders zeitlich (mehrere Verkaeufe am selben Vormittag),
    entscheidet die Summe. Eine Wahl gilt nur, wenn ihr Euro-Betrag zu "Gefüllt" passt (je Ausfuehrung hoechstens 1 ct Rundung)."""
    return _bsdex_search(order, candidates)[0]

def _bsdex_search(order: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]], check_amount: bool = True) -> tuple[list[Mapping[str, Any]] | None, bool]:
    """Die Suche hinter _bsdex_pick; zurueck kommen die Wahl und ob die Suche an ihrer Schrittgrenze endete. Ohne `check_amount`
    zaehlt nur die Menge - so erkennt bsdex_unassigned_reason_v1, dass die Menge aufgeht und nur der Betrag nicht."""
    pool = sorted(candidates, key=lambda fill: (fill["at"], fill["id"]))
    target, steps = order["quantity"], [0]
    suffix = [Decimal("0")] * (len(pool) + 1)
    for position in range(len(pool) - 1, -1, -1):
        suffix[position] = suffix[position + 1] + pool[position]["quantity"]

    def plausible(chosen: Sequence[Mapping[str, Any]]) -> bool:
        return len({fill["asset"] for fill in chosen}) == 1 and (
            not check_amount or abs(sum(fill["eur"] for fill in chosen) - order["filled"]) <= CENT * len(chosen))

    def search(position: int, chosen: list[Mapping[str, Any]], total: Decimal) -> list[Mapping[str, Any]] | None:
        steps[0] += 1
        if steps[0] > BSDEX_SEARCH_STEPS:
            return None
        if total == target:
            return list(chosen) if plausible(chosen) else None
        if position == len(pool) or total > target or total + suffix[position] < target:
            return None
        chosen.append(pool[position])
        found = search(position + 1, chosen, total + pool[position]["quantity"])
        chosen.pop()
        return found if found is not None else search(position + 1, chosen, total)

    found = search(0, [], Decimal("0"))
    return found, steps[0] > BSDEX_SEARCH_STEPS

def bsdex_history_coverage_v1(moments: Sequence[datetime]) -> dict[int, datetime]:
    """Je Jahr der letzte Zeitpunkt, den die Transaktionshistorien nennen. BSDEX teilt die Historie nach Jahren in UTC (eine
    Ausfuehrung um 00:30 Uhr am Neujahrstag in Berlin steht in der Historie des Vorjahres)."""
    coverage: dict[int, datetime] = {}
    for moment in moments:
        year = moment.astimezone(ZoneInfo("UTC")).year
        coverage[year] = max(coverage.get(year, moment), moment)
    return coverage

def bsdex_missing_reason_v1(start: datetime, end: datetime, coverage: Mapping[int, datetime]) -> dict[str, Any] | None:
    """Fehlt die Historie des Jahres (in UTC, nach dem Ende des Vorgangs), oder endet sie, bevor er begann? Sonst None."""
    berlin = ZoneInfo(TIME_ZONE)
    year = end.astimezone(ZoneInfo("UTC")).year
    if year not in coverage:
        return {"reason": "history_missing", "year": year}
    if start > coverage[year]:
        return {"reason": "history_outdated", "until": coverage[year].astimezone(berlin).date().isoformat()}
    return None

def bsdex_unassigned_reason_v1(order: Mapping[str, Any], fills: Sequence[Mapping[str, Any]], used: set[str],
                               coverage: Mapping[int, datetime]) -> dict[str, Any]:
    """Warum eine abgeschlossene Order keine Ausfuehrungen bekam, so genau wie moeglich (Festlegung 08.11.2026: den Grund immer
    zeigen, Transparenz ist ein Qualitaetsmerkmal). Der Reihe nach:
    - history_missing: keine Transaktionshistorie fuer das Jahr der Order;
    - history_outdated: die Historie endet, bevor die Order angelegt wurde;
    - no_executions: die Historie deckt den Tag ab, im Zeitraum der Order liegt aber keine freie Ausfuehrung ihrer Richtung;
    - amount_differs: freie Ausfuehrungen ergeben genau ihre Menge, aber nicht ihren Kurswert (mit Kurswert und Gebuehr dieser
      Ausfuehrungen);
    - ambiguous: zu viele Moeglichkeiten, die Suche endete an ihrer Grenze;
    - quantity_differs: Ausfuehrungen im Zeitraum, ihre Menge geht aber nicht auf.
    `used` sind die Ausfuehrungen, die schon anderen Orders gehoeren."""
    late = bsdex_missing_reason_v1(order["from"], order["to"] - BSDEX_WINDOW, coverage)
    if late is not None:
        return late
    pool = [fill for fill in fills if fill["id"] not in used and fill["side"] == order["side"] and order["from"] <= fill["at"] <= order["to"]]
    if not pool:
        return {"reason": "no_executions"}
    found, exhausted = _bsdex_search(order, pool, check_amount=False)
    if found is not None:
        return {"reason": "amount_differs", "eur": sum((fill["eur"] for fill in found), Decimal("0")), "fee": sum((fill["fee"] for fill in found), Decimal("0"))}
    return {"reason": "ambiguous" if exhausted else "quantity_differs"}

def bsdex_assign_executions_v1(orders: Sequence[Mapping[str, Any]], fills: Sequence[Mapping[str, Any]]) -> dict[int, list[Mapping[str, Any]]]:
    """Je Order (Position in `orders`) ihre Ausfuehrungen; fehlt die Zuordnung, fehlt die Position. Orders brauchen "side", "quantity",
    "filled", "from" und "to" (UTC), Ausfuehrungen "id", "side", "asset", "quantity", "eur" und "at". Cash-Import und Krypto-Leser
    rufen dieselbe Funktion: Dieselbe Order bekommt in beiden dieselben Ausfuehrungen, auch wenn sich Orders ueberlappen."""
    used: set[str] = set()
    assigned: dict[int, list[Mapping[str, Any]]] = {}
    for position in sorted(range(len(orders)), key=lambda index: (orders[index]["to"], orders[index]["from"], index)):
        order = orders[position]
        pool = [fill for fill in fills if fill["id"] not in used and fill["side"] == order["side"] and order["from"] <= fill["at"] <= order["to"]]
        chosen = _bsdex_pick(order, pool) if pool else None
        if chosen is not None:
            used.update(fill["id"] for fill in chosen)
            assigned[position] = list(chosen)
    return assigned

def bsdex_execution_days_v1(fills: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    """Die Ausfuehrungen einer Order je Kalendertag in Berlin. Gebucht wird je Order und Tag (Festlegung 26.10.2026): Steuerlich ist
    jeder ausgefuehrte Teil ein eigenes Geschaeft mit eigenem Datum; Steuerjahr und Ein-Jahres-Frist zaehlen nach Tagen, innerhalb
    eines Tages aendert die Zusammenfassung daran nichts."""
    days: dict[str, list[Mapping[str, Any]]] = {}
    for fill in sorted(fills, key=lambda fill: (fill["at"], fill["id"])):
        days.setdefault(fill["at"].astimezone(ZoneInfo(TIME_ZONE)).date().isoformat(), []).append(fill)
    return days

def bsdex_history_executions_v1(source: bytes, file_name: str) -> list[dict[str, Any]] | None:
    """Die Ausfuehrungen einer BSDEX-Transaktionshistorie, oder None, wenn die Datei keine ist."""
    history = _bsdex_history(source, file_name)
    return None if history is None else history["fills"]

# Luecken des Stapels fuer eine Order bzw. Euro-Bewegung ohne Beleg in der Historie (Text in der Data-App).
BSDEX_GAP_REASONS = {"history_missing": "bsdex_history_missing", "history_outdated": "bsdex_history_outdated", "no_executions": "bsdex_executions_missing",
                     "quantity_differs": "bsdex_execution_quantity_differs", "amount_differs": "bsdex_execution_amount_differs",
                     "ambiguous": "bsdex_executions_ambiguous", "flows_missing": "bsdex_flows_missing"}

def _bsdex_gaps(entries: Sequence[tuple[Mapping[str, Any], str, str, Mapping[str, Any] | None]]) -> list[dict[str, Any]]:
    """Je Grund eine Luecke (fehlt die Historie: je Jahr), mit der Zahl der Orders und Euro-Bewegungen und der ersten betroffenen.
    Ist die erste eine Order, nennt die Luecke Richtung, Coin, Menge und die Betraege aus Export und - wo sie die Menge ergeben -
    Historie. Eintrag: (Grund, Datei, Tag, Order oder None)."""
    grouped: dict[tuple[Any, ...], list[tuple[Mapping[str, Any], str, str, Mapping[str, Any] | None]]] = {}
    for entry in entries:
        why = entry[0]
        grouped.setdefault((BSDEX_GAP_REASONS[why["reason"]], why.get("year"), why.get("until")), []).append(entry)
    gaps = []
    for (reason, year, until), items in grouped.items():
        why, file_name, local_date, order = min(items, key=lambda item: (item[2], item[3] is None, item[1]))
        gap = {"reason": reason, "file_name": file_name, "period_from": local_date,
               "order_count": sum(1 for item in items if item[3] is not None), "flow_count": sum(1 for item in items if item[3] is None)}
        if year is not None:
            gap["year"] = year
        if until is not None:
            gap["history_until"] = until
        if order is not None:
            euro = lambda value: format(value.quantize(CENT) if value.as_tuple().exponent >= -2 else value, "f")   # 85,1 -> 85.10
            gap.update({"side": order["side"], "asset": order["unit"], "quantity_decimal": _plain(order["quantity"]),
                        "export_amount_decimal": euro(order["filled"]), "export_fee_decimal": euro(order["fee"])})
            if "eur" in why:
                gap.update({"executions_amount_decimal": euro(why["eur"]), "executions_fee_decimal": euro(why["fee"])})
        gaps.append(gap)
    return gaps

def _bsdex_movements(sources: Sequence[tuple[bytes, str]], require_evidence: bool) -> dict[str, Any]:
    """Liest Exporte und Jahreshistorien zusammen. Mehrfach abgelegte Dateien (jeder Export reicht bis zum Kontobeginn, die Historie
    des laufenden Jahres kommt jeden Monat neu) zaehlen jede Bewegung einmal: Ausfuehrungen nach ihrer Kennung, Orders nach ihren
    Angaben. Mit `require_evidence` (der ganze Stapel) wird nichts geschaetzt: Eine Order ohne ihre Ausfuehrungen und eine
    Ausfuehrung ohne ihre Order halten den Stapel an und stehen in der Vorschau. Ohne (eine einzelne Datei, etwa fuer den Vorschlag
    beim Ablegen) gilt der Export je Order und die Historie je Tag und Coin. Eine noch offene Order mit Teilausfuehrungen haelt
    nichts an: Ihre Ausfuehrungen warten, bis sie abgeschlossen ist, und stehen bis dahin als zurueckgehalten in der Vorschau."""
    exports: list[tuple[str, dict[str, Any]]] = []
    histories: list[tuple[str, dict[str, Any]]] = []
    files: list[dict[str, Any]] = []
    unreadable: list[str] = []
    seen: dict[str, str] = {}
    for data, name in sources:
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            files.append({"file_name": name, "status": "duplicate", "row_count": 0, "period_from": None, "period_to": None}); continue
        history = _bsdex_history(data, name)
        export = None if history is not None else _bsdex_export(data, name)
        if history is None and export is None:
            unreadable.append(name); continue
        seen[digest] = name
        (histories if history is not None else exports).append((name, history if history is not None else export))
    if not exports and not histories:
        _abort("cash_statement_header_invalid")
    diagnostics = [item for _name, part in exports + histories for item in part["diagnostics"]]
    # Orders und Euro-Bewegungen des Exports: je Angabe so oft, wie sie in einer Datei hoechstens vorkommt.
    def union(parts: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
        merged: dict[Any, list[dict[str, Any]]] = {}
        for items in parts:
            grouped: dict[Any, list[dict[str, Any]]] = {}
            for item in items:
                grouped.setdefault(item["key"], []).append(item)
            for key, same in grouped.items():
                if len(same) > len(merged.get(key, [])):
                    merged[key] = same
        return sorted((item for same in merged.values() for item in same), key=lambda item: (item["local_date"], item["file_name"], item["ordinal"]))
    orders = union([part["orders"] for _name, part in exports])
    # Dieselbe Order in mehreren Exporten: offen in einem aelteren, abgeschlossen in einem neueren - dann zaehlt der Abschluss; offen
    # in mehreren, dann der weiteste Stand.
    finished = {order["identity"] for order in orders if not order["open"]}
    still_open: dict[Any, dict[str, Any]] = {}
    for order in orders:
        if order["open"] and order["identity"] not in finished and (
                order["identity"] not in still_open or order["quantity"] > still_open[order["identity"]]["quantity"]):
            still_open[order["identity"]] = order
    pending = sorted(still_open.values(), key=lambda order: (order["from"], order["file_name"], order["ordinal"]))
    orders = [order for order in orders if not order["open"]]
    export_flows = union([part["flows"] for _name, part in exports])
    fills = list({fill["id"]: fill for _name, part in histories for fill in part["fills"]}.values())
    history_flows = list({flow["id"]: flow for _name, part in histories for flow in part["flows"]}.values())
    berlin = ZoneInfo(TIME_ZONE)
    candidates: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    assigned = bsdex_assign_executions_v1(orders, fills)
    used = {fill["id"] for chosen in assigned.values() for fill in chosen}
    missing_entries: list[tuple[Mapping[str, Any], str, str, Mapping[str, Any] | None]] = []
    unmatched_orders = [order for position, order in enumerate(orders) if position not in assigned]
    # Offene Orders mit Teilausfuehrung: zuerst genau ihre Menge (Historie und Export vom selben Tag); was danach von ihrem Coin in
    # ihrer Richtung noch uebrig ist, gehoert zur zuletzt angelegten offenen davor (die Historie ist neuer als der Export). Gebucht
    # wird davon nichts, also auch nichts Falsches; die Vorschau nennt es.
    holding: list[tuple[dict[str, Any], list[Mapping[str, Any]]]] = []
    for order in pending:
        pool = [fill for fill in fills if fill["id"] not in used and fill["side"] == order["side"] and fill["asset"] == order["unit"]
                and fill["at"] >= order["from"]]
        chosen = list((_bsdex_pick(order, pool) if pool else None) or [])
        used.update(fill["id"] for fill in chosen)
        holding.append((order, chosen))
    for fill in sorted(fills, key=lambda fill: (fill["at"], fill["id"])):
        owners = [chosen for order, chosen in holding if fill["id"] not in used and order["side"] == fill["side"] and order["unit"] == fill["asset"]
                  and order["from"] <= fill["at"]]
        if owners:
            owners[-1].append(fill); used.add(fill["id"])
    held_back: list[dict[str, Any]] = []
    for order, chosen in holding:
        eur, fee = sum((fill["eur"] for fill in chosen), Decimal("0")), sum((fill["fee"] for fill in chosen), Decimal("0"))
        held_back.append({"side": order["side"], "asset": order["unit"], "since": order["local_date"], "execution_count": len(chosen),
                          "amount_decimal": _plain(-(eur + fee) if order["side"] == "buy" else eur - fee), "file_name": order["file_name"]})
    for position, order in enumerate(orders):
        chosen = assigned.get(position)
        if chosen is None:
            continue
        # Je Order und Ausfuehrungstag eine Bewegung (rc.327): Steuerjahr und Ein-Jahres-Frist zaehlen nach dem Tag jedes Teils.
        for day, group in sorted(bsdex_execution_days_v1(chosen).items()):
            last = max(group, key=lambda fill: fill["at"])
            eur, fee = sum(fill["eur"] for fill in group), sum(fill["fee"] for fill in group)
            cash = -(eur + fee) if order["side"] == "buy" else eur - fee
            candidates.append({**_exchange_row(last["ordinal"], day, cash, f"{BSDEX_LABELS[order['side']]} {last['asset']}"),
                               "source_file_name": last["file_name"]})
    loose = [fill for fill in fills if fill["id"] not in used]
    if not require_evidence:
        # Eine Datei allein: der Export je Order wie angegeben, die Historie je Tag, Coin und Richtung.
        for order in unmatched_orders:   # abgeschlossene; offene warten auch hier
            cash = -(order["filled"] + order["fee"]) if order["side"] == "buy" else order["filled"] - order["fee"]
            candidates.append({**_exchange_row(order["ordinal"], order["local_date"], cash, f"{BSDEX_LABELS[order['side']]} {order['coin']}"),
                               "source_file_name": order["file_name"]})
        days: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        for fill in loose:
            days.setdefault((fill["at"].astimezone(berlin).date().isoformat(), fill["side"], fill["asset"]), []).append(fill)
        for (day, side, asset), group in sorted(days.items()):
            eur, fee = sum(fill["eur"] for fill in group), sum(fill["fee"] for fill in group)
            candidates.append({**_exchange_row(group[0]["ordinal"], day, -(eur + fee) if side == "buy" else eur - fee, f"{BSDEX_LABELS[side]} {asset}"),
                               "source_file_name": group[0]["file_name"]})
    else:
        # Je Grund eine Luecke (Festlegung 08.11.2026: den Grund immer so genau wie moeglich), siehe _bsdex_gaps.
        coverage = bsdex_history_coverage_v1([item["at"] for item in fills + history_flows])
        missing_entries.extend((bsdex_unassigned_reason_v1(order, fills, used, coverage), order["file_name"], order["local_date"], order)
                               for order in unmatched_orders)
        if loose:
            first = min(loose, key=lambda fill: fill["at"])
            gaps.append({"reason": "bsdex_orders_missing", "file_name": first["file_name"],
                         "period_from": first["at"].astimezone(berlin).date().isoformat(), "execution_count": len(loose)})
    # Euro-Ein- und -Auszahlungen: aus der Historie, wo es sie gibt; sonst aus dem Export.
    if histories:
        for flow in history_flows:
            candidates.append({**_exchange_row(flow["ordinal"], flow["at"].astimezone(berlin).date().isoformat(), flow["cash"], flow["label"]),
                               "source_file_name": flow["file_name"]})
        if require_evidence:
            booked = {}
            for flow in history_flows:
                key = (flow["at"].astimezone(berlin).date().isoformat(), flow["cash"])
                booked[key] = booked.get(key, 0) + 1
            missing = []
            for flow in export_flows:
                key = (flow["local_date"], flow["cash"])
                if booked.get(key, 0) > 0:
                    booked[key] -= 1
                else:
                    missing.append(flow)
            coverage = bsdex_history_coverage_v1([item["at"] for item in fills + history_flows])
            for flow in missing:   # ohne Uhrzeit im Export: der ganze Tag muss in der Historie liegen
                moment = datetime.fromisoformat(flow["local_date"]).replace(hour=23, minute=59, second=59, tzinfo=berlin)
                why = bsdex_missing_reason_v1(moment, moment, coverage) or {"reason": "flows_missing"}
                missing_entries.append((why, flow["file_name"], flow["local_date"], None))
    else:
        for flow in export_flows:
            candidates.append({**_exchange_row(flow["ordinal"], flow["local_date"], flow["cash"], flow["label"]), "source_file_name": flow["file_name"]})
    # Eine Bewegung ueber 0 EUR bewegt nichts, und der Kern verwuerfe mit ihr den ganzen Beleg. Sie entsteht nur aus einem
    # beschaedigten Beleg (Selbsttest rc.379: Ziffer im Coin-Kuerzel einer Order ohne Ausfuehrung, "0 ET2", ergibt Menge 2 zu 0 EUR).
    candidates = [row for row in candidates if row["amount_decimal"] != "0"]
    if not candidates and not gaps:
        _abort("cash_statement_header_invalid")
    for name, part in histories:
        days = sorted(item["at"].astimezone(berlin).date().isoformat() for item in part["fills"] + part["flows"])
        files.append({"file_name": name, "status": "used", "row_count": len(part["fills"]) + len(part["flows"]),
                      "period_from": days[0] if days else None, "period_to": days[-1] if days else None})
    for name, part in exports:
        days = sorted(item["local_date"] for item in part["orders"] + part["flows"])
        files.append({"file_name": name, "status": "orders_for_grouping" if histories else "used", "row_count": len(part["orders"]) + len(part["flows"]),
                      "period_from": days[0] if days else None, "period_to": days[-1] if days else None})
    gaps.extend(_bsdex_gaps(missing_entries))
    gaps.sort(key=lambda gap: gap["period_from"])
    return {"candidates": candidates, "diagnostics": diagnostics, "files": files, "unreadable": unreadable, "chain_gaps": gaps,
            "held_back": held_back,
            "evidence": {"orders": len(orders), "executions": len(fills), "orders_from_executions": len(orders) - len(unmatched_orders),
                         "orders_open": len(pending)}}

def _parse_bsdex_eur(source: bytes, file_name: str) -> dict[str, Any]:
    """Eine BSDEX-Datei allein (Vorschlag beim Ablegen, Erkennung): Export je Order, Historie je Tag; der Stapel liest beide genau."""
    combined = _bsdex_movements([(source, file_name)], require_evidence=False)
    if combined["unreadable"] or not combined["candidates"]:
        _abort("cash_statement_header_invalid")
    for row in combined["candidates"]:
        row.pop("source_file_name", None)
    # Der Dateiname gehoert nur zum Stapel; im Ergebnis einer Datei verwarf er sonst das Ganze (Selbsttest rc.379).
    diagnostics = [{key: value for key, value in row.items() if key != "file_name"} for row in combined["diagnostics"]]
    return _exchange_result(combined["candidates"], diagnostics)


READERS = {"bsdex_eur_v1": _parse_bsdex_eur}
COMBINERS = {"bsdex_eur_v1": lambda documents: _bsdex_movements(documents, require_evidence=True)}
