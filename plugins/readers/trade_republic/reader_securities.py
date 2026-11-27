"""Portelyra-Leser trade_republic: Wertpapier- und Devisenbelege (statement_reader_v1, Aufruf read_text/detect/finish).

Erzeugt aus dem bisherigen Kernmodul (rc.373) ohne Aenderung der Leselogik. Der Leser bekommt den Text eines Belegs
(PDF-Text erzeugt der Kern) und liefert ein Ergebnis; Gruende tragen nur ihren Code, den Text setzt der Kern.
"""
from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation
from decimal import ROUND_HALF_UP
from zoneinfo import ZoneInfo
import re
from typing import Any

from portelyra_reader_sdk_v1 import (
    CENT,
    REASONS,
    TAX_DOCUMENT,
    TIME_ZONE,
    candidate as _candidate,
    csv_rows as _csv_rows,
    multi_result as _multi,
    plain as _plain,
    reason as _reason,
    json_sha256 as _sha,
    is_tax_document as _tax_document,
)


TRADE_REPUBLIC_COLUMNS = {"datetime", "date", "category", "type", "name", "symbol", "shares", "price", "amount", "fee", "tax", "currency", "transaction_id"}

BERLIN = ZoneInfo(TIME_ZONE)

TRADE_REPUBLIC_CASH = {"INTEREST_PAYMENT", "CUSTOMER_INBOUND", "CUSTOMER_OUTBOUND_REQUEST", "CUSTOMER_INBOUND_REQUEST", "CUSTOMER_OUTBOUND",
                       "CARD_TRANSACTION", "CARD_ORDERING_FEE", "CARD_REFUND", "TRANSFER_INBOUND", "TRANSFER_OUTBOUND", "BONUS"}

def _usable(*values: Decimal | None) -> bool:
    """Endliche Zahlen in ueblicher Groesse. "NaN", "Infinity" oder ein Exponent jenseits jeder Stueckzahl ("42E756600") kommen nur
    aus einem beschaedigten Export (Selbsttest rc.379) und ergaeben sonst einen Absturz oder ein ungueltiges Ergebnis."""
    return all(value is None or (value.is_finite() and value.adjusted() < 15) for value in values)

def _parse_trade_republic_csv(rows: list[dict[str, str]]) -> dict[str, Any]:
    reasons: dict[str, int] = {}
    def skip(code: str, count: int = 1) -> None: reasons[code] = reasons.get(code, 0) + count
    trades: list[dict[str, Any]] = []; dividends: list[dict[str, Any]] = []; earnings: list[dict[str, Any]] = []
    for position, row in enumerate(rows):
        category, kind = row["category"], row["type"]
        try:
            moment = datetime.fromisoformat(row["datetime"].replace("Z", "+00:00"))
        except ValueError:
            skip("incomplete"); continue
        local = moment.astimezone(BERLIN) if moment.tzinfo else moment.replace(tzinfo=ZoneInfo("UTC")).astimezone(BERLIN)
        isin = row["symbol"] if re.match(r"^[A-Z]{2}[A-Z0-9]{9}\d$", row["symbol"] or "") else None
        if kind == "EARNINGS":
            try:
                tax = abs(Decimal(row["tax"])) if row["tax"] else None
            except InvalidOperation:
                skip("incomplete"); continue
            if not isin or not _usable(tax):
                skip("incomplete"); continue
            earnings.append({"isin": isin, "name": row["name"] or None, "date": local.date().isoformat(), "tax": tax, "ref": row["transaction_id"][:36]})
            continue
        if kind == "TAX_OPTIMIZATION": skip("tax_document"); continue
        if kind.startswith("IPO"): skip("ipo"); continue
        if category == "TRADING" and kind in ("BUY", "SELL"):
            if not (row["amount"] and row["price"]):
                skip("ipo" if kind == "BUY" else "incomplete"); continue   # Zuteilung einer Zeichnung: Kauf ohne Betrag
            if (row["currency"] or "EUR") != "EUR": skip("not_eur"); continue
            try:
                quantity, price, fee = abs(Decimal(row["shares"])), Decimal(row["price"]), abs(Decimal(row["fee"] or "0"))
            except InvalidOperation:
                skip("incomplete"); continue
            if not _usable(quantity, price, fee) or price < 0:   # ein negativer Kurs nur in einem beschaedigten Export
                skip("incomplete"); continue
            if not (isin and quantity):
                skip("incomplete"); continue
            trades.append({"kind": kind.lower(), "isin": isin, "name": row["name"] or None, "local": local, "quantity": quantity,
                           "price": price, "fee": fee, "ref": row["transaction_id"][:36], "moment": moment, "position": position})
            continue
        if kind == "DIVIDEND":
            try:
                amount = Decimal(row["amount"]); shares = abs(Decimal(row["shares"])) if row["shares"] else None
            except InvalidOperation:
                skip("incomplete"); continue
            if not _usable(amount, shares):
                skip("incomplete"); continue
            if (row["currency"] or "EUR") != "EUR": skip("not_eur"); continue
            try:
                tax = abs(Decimal(row["tax"])) if row["tax"] else None
            except InvalidOperation:   # unlesbare Steuer: ein Grund statt eines Absturzes (Selbsttest rc.379)
                skip("incomplete"); continue
            if not _usable(tax):
                skip("incomplete"); continue
            dividends.append({"isin": isin, "name": row["name"] or None, "date": local.date().isoformat(), "amount": amount, "shares": shares,
                              "tax": tax, "ref": row["transaction_id"][:36]})
            continue
        if category == "CASH" or kind in TRADE_REPUBLIC_CASH: skip("cash_movement"); continue
        if kind in ("DELIVERY", "FREE_RECEIPT", "FREE_DELIVERY", "TRANSFER"): skip("custody_change"); continue
        skip("unknown_document")
    candidates = []
    for item in trades:
        candidates.append(_candidate(item["kind"], "trade_republic", isin=item["isin"], security_name=item["name"], local_date=item["local"].date().isoformat(),
                                     local_time=item["local"].strftime("%H:%M:%S"), quantity=_plain(item["quantity"]), unit_price=_plain(item["price"]),
                                     gross_amount=_plain((item["quantity"] * item["price"]).quantize(CENT, ROUND_HALF_UP)), fee_amount=_plain(item["fee"]),
                                     order_ref=item["ref"], executed_at_utc=(item["moment"] if item["moment"].tzinfo else item["moment"].replace(tzinfo=ZoneInfo("UTC"))).astimezone(ZoneInfo("UTC")).isoformat(timespec="microseconds"),
                                     export_position=item["position"]))
    # Gutschrift und Rueckbuchung derselben Dividende am selben Tag heben sich auf
    reversed_refs = set()
    for negative in [item for item in dividends if item["amount"] < 0]:
        positive = next((item for item in dividends if item["ref"] not in reversed_refs and item["amount"] == -negative["amount"]
                         and item["isin"] == negative["isin"] and item["date"] == negative["date"]), None)
        reversed_refs.add(negative["ref"])
        if positive: reversed_refs.add(positive["ref"]); skip("dividend_reversed", 2)
        else: skip("dividend_reversed")
    for item in dividends:
        if item["ref"] in reversed_refs: continue
        if not (item["isin"] and item["shares"] and item["amount"] > 0): skip("incomplete"); continue
        candidates.append(_candidate("dividend", "trade_republic", isin=item["isin"], security_name=item["name"], local_date=item["date"],
                                     eligible_quantity=_plain(item["shares"]), gross_amount=_plain(item["amount"]),
                                     taxes_amount=_plain(item["tax"]) if item["tax"] else None, order_ref=item["ref"]))
    for item in earnings:   # Zufluss im Folgejahr des Berechnungsjahres (Buchung meist Januar/Februar)
        candidates.append(_candidate("advance_lump_sum", "trade_republic", isin=item["isin"], security_name=item["name"], local_date=item["date"],
                                     taxes_amount=_plain(item["tax"]) if item["tax"] is not None else None, order_ref=item["ref"],
                                     calculation_year=int(item["date"][:4]) - 1))
    return _multi(candidates, reasons)

def _parse_trade_republic(text: str) -> dict[str, Any]:
    rows = _csv_rows(text, TRADE_REPUBLIC_COLUMNS)
    if rows is not None:
        return _parse_trade_republic_csv(rows)
    if "Trade Republic" not in text[:4000]:
        return _reason("wrong_institution")
    if _tax_document(text) or re.search(r"Jahressteuerbescheinigung|Steuerbescheinigung", text[:4000]):
        return _reason("tax_document")
    return _reason("information")

def _detect_trade_republic(text: str) -> bool:
    return _csv_rows(text.split("\n", 1)[0], TRADE_REPUBLIC_COLUMNS) is not None or "Trade Republic Bank" in text[:4000]

def _finish_trade_republic(candidates: list[dict[str, Any]], statements: list[dict[str, Any]], row_reasons: list[dict[str, Any]]) -> None:
    """Teilausfuehrungen getrennt in der Reihenfolge der Bank (#471).

    Trade Republic fuehrt einen Kauf nach Betrag als ganze Stuecke (mit der Ordergebuehr) und einen Bruchteil (ohne) in
    derselben Sekunde und verbraucht beim Verkauf beide Teile getrennt, in der Reihenfolge der Ausfuehrung. Als eine Buchung
    verteilt Portelyra die Gebuehr anteilig; liegt die FIFO-Grenze eines Verkaufs im Kauf, verschiebt sich Gewinn zwischen den
    Jahren (wie bei der Bank). Die Reihenfolge folgt den
    Millisekunden des Exports, bei gleicher Zeit der Zeilenfolge der Datei. Zwei Buchungen desselben Papiers in derselben
    Sekunde lassen sich im FIFO nicht ordnen: Die frueheren Teile ruecken je eine Sekunde vor, die Ausfuehrungszeit bleibt
    am Kandidaten stehen."""
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate["profile"] == "trade_republic" and candidate["kind"] in ("buy", "sell") and candidate.get("local_time"):
            key = (candidate.get("depot_ref"), candidate["isin"], candidate["kind"], candidate["local_date"], candidate["local_time"], candidate["unit_price"])
            groups.setdefault(key, []).append(candidate)
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda item: (item.get("executed_at_utc") or "", item.get("export_position", 0)))
        group = "trx_" + _sha(["trade_republic_executions", *[str(value) for value in key]])[:20]
        last = datetime.strptime(members[-1]["local_time"], "%H:%M:%S")
        for offset, member in enumerate(reversed(members)):
            member["execution_group"] = group
            member["separate_executions"] = True
            moved = last - timedelta(seconds=offset)
            if offset and moved.date() == last.date():
                member["executed_local_time"] = member["local_time"]
                member["local_time"] = moved.strftime("%H:%M:%S")


READERS = {
    "trade_republic_v1": _parse_trade_republic,
}

DETECTORS = {
    "trade_republic_v1": _detect_trade_republic,
}

FINISHERS = {
    "trade_republic_v1": _finish_trade_republic,
}
