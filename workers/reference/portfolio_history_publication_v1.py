"""Veroeffentlichte Tageshistorie (#473): die Reihe aus portfolio-history-v1 als Artefakt fuer die Analyse.

Die Tageshistorie liegt im Datenraum; Cockpit, Steuer und Analyse lesen aber nur Veroeffentlichtes. Dieser Baustein
veroeffentlicht die Reihe so, wie die Analyse sie zeichnet (Festlegungen vom 20.10.2026):
- je Tag Gesamtvermoegen, Marktwert, Einstand, unrealisierte GuV und Cash, mit dem abgeleiteten Teil des Cash getrennt,
  damit die Anzeige ihn gekennzeichnet zeichnen kann;
- je Asset Menge, Kurs und Wert je Tag (ueber die Konten summiert), der Einstand als Stufen aus dem FIFO-Stand und die
  Zu- und Abgaenge als Punkte;
- je Tag die Zusammensetzung nach Assetklasse und Cash und der externe Netto-Fluss ueber alle eigenen Konten samt seiner
  Rechnung und der kumulierten Summe "Extern zugeflossen" (#480);
- die Anlage ohne die Cash-Konten ausserhalb (#481): Wert, Fluss und zeitgewichteter Index je Tag, Renditen je Zeitraum
  (TWR und IZF/XIRR), die Zinsrendite je Cash-Konto und Jahr und die externen Fluesse je Konto und Monat.

Gerechnet wird hier nichts Neues: Summen ueber Konten und die Stufen des FIFO-Stands sind Abfragen auf gespeicherte
Ergebnisse. Bezeichnungen ersetzen die Kennungen des Bestands. Ein unveraenderter Inhalt wird nicht noch einmal
veroeffentlicht.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, timedelta
from fractions import Fraction
import hashlib
import os
from pathlib import Path
import sqlite3
from typing import Any

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.desktop_cash_coverage_v1 import DesktopCashCoverageV1Error, read_desktop_cash_coverage_view_v1
from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1
from migrations.reference.investment_scope_v1 import InvestmentScopeV1Error, read_investment_scope_v1
from workers.reference.portfolio_history_compare_v1 import (
    benchmark_component_v1, benchmark_periods_v1, composite_levels_v1, daily_steps_v1, group_performance_v1, held_benchmark_rows_v1,
    working_days_v1,
)
from workers.reference.portfolio_history_accounts_v1 import account_views_v1
from workers.reference.portfolio_history_net_v1 import NetState, account_net_v1, lot_trace_v1, net_apply_v1, with_net_v1
from workers.reference.portfolio_history_performance_v1 import intervals_v1, performance_v1, realized_events_v1, sale_lots_v1, with_bridge_v1
from workers.reference.portfolio_history_v1 import PortfolioHistoryV1Error, asset_price_series_v1, read_portfolio_history_v1
from workers.reference.cash_settlement_v1 import match_settlements_v1
from workers.reference.portfolio_snapshot_freshness_v1 import (
    PortfolioSnapshotFreshnessV1Error,
    _basis_text,
    holdings_timeline_v1,
)

AREA_ID = "portfolio_history"
WRITER_ID = "desktop_portfolio_history_worker"
WRITER_ROLE = "portfolio_history_worker"
ARTIFACT_CONTRACT = "portfolio_history_v1"
VERSION = 1
TARGET_CURRENCY = "EUR"
# Kern mit Teildateien (#503); geht in die Kennung des Laufs ein.
PARTS_LAYOUT = "core_with_parts_v1"
PORTFOLIO_FIELDS = ("net_worth", "market_value", "cost_basis", "unrealised", "cash", "cash_derived")
SUMMARY_SOURCE = {"net_worth": "net_worth_decimal", "market_value": "market_value_decimal", "cost_basis": "cost_basis_decimal",
                  "unrealised": "unrealised_decimal", "cash": "cash_balance_decimal", "cash_derived": "cash_derived_balance_decimal"}
# Zugaenge und Abgaenge, die als Punkt auf der Linie erscheinen. Ein Transfer zwischen eigenen Konten aendert die Menge
# des Assets nicht und erscheint deshalb nicht.
TRADE_KINDS = ("buy", "sell", "reward", "deposit", "withdrawal", "stock_dividend", "other_in", "other_out")
# Die Buchungen eines markierten Tages, wie die Analyse sie beim Anklicken zeigt (#480).
EVENT_KINDS = ("buy", "sell", "reward", "stock_dividend", "deposit", "withdrawal", "transfer", "other")
# Zusammensetzung (#480): feste Reihenfolge von unten nach oben; seltene Arten fallen unter "other".
COMPOSITION_CLASSES = ("cash", "transit", "fund", "equity", "crypto", "fx", "derivative", "other")
COMPOSITION_CLASS_OF = {"cash": "cash", "fund": "fund", "etf": "fund", "equity": "equity", "crypto": "crypto", "fx": "fx",
                        "derivative": "derivative"}
# Buchungen, die Geld oder Stuecke ueber die Grenze der eigenen Konten bewegen koennen (#480).
FLOW_KINDS = ("buy", "sell", "deposit", "withdrawal")
# Konten, deren Saldo im Cash zaehlt (#481); ihre Zugehoerigkeit zur Anlage legt der Eigentuemer fest.
CASH_ACCOUNT_TYPES = ("cash", "bank")
# Kennzahlen (Raten, Index) sind gerundete Verhaeltnisse, keine Betraege.
RATE_DIGITS = 10
# Bucht das Geld eines Kaufs oder Verkaufs spaeter (Valuta), sucht der Abgleich je Konto so viele Tage weiter.
VALUTA_DAYS = 5
# Eine Umbuchung zwischen zwei eigenen Konten darf so viele Tage unterwegs sein (Wochenende und Feiertage, #481).
TRANSFER_DAYS = 5


class PortfolioHistoryPublicationV1Error(RuntimeError):
    CODES = frozenset({
        "portfolio_history_publication_context_invalid", "portfolio_history_publication_input_invalid",
        "portfolio_history_publication_evidence_invalid", "portfolio_history_publication_failed",
        "portfolio_history_publication_boundary_failed",
    })

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("portfolio_history_publication_error_code_unregistered")
        self.code = code
        super().__init__(code)


def portfolio_history_publication_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(PortfolioHistoryPublicationV1Error.CODES))


def _abort(code: str) -> None:
    raise PortfolioHistoryPublicationV1Error(code)


def _sha(value: Any) -> str:
    # Derselbe Abdruck wie Publikationsweg und Leser (ensure_ascii=False, siehe portfolio_snapshot_publication_v1).
    from migrations.reference.legacy_import_data_command_v1 import fingerprint
    return fingerprint(value)


def _utc(value: Any) -> str:
    from datetime import datetime, timezone
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        _abort("portfolio_history_publication_input_invalid")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort("portfolio_history_publication_input_invalid")
    return value


def _income_events(ledger: list[dict[str, Any]], canonical: Path, tax_of: Any = None, pooled_of: Any = None) -> dict[str, list[dict[str, Any]]]:
    """Je Asset die Dividenden (Tag, Betrag wie gebucht, Konto) - als Ertragssymbole im Asset-Verlauf (#483); mit der
    Netto-Sicht dazu die projizierte Steuer je Dividende."""
    accounts = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
    try:
        labels = dict(accounts.execute("SELECT account_id, display_name FROM account").fetchall())
    finally:
        accounts.close()
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(ledger, key=lambda item: (item["local_date"] or "", item["event_ref"])):
        if row["event_type"] != "dividend" or not row["local_date"]:
            continue
        value = row.get("gross_income_decimal") if row.get("gross_income_decimal") is not None else row["gross_amount_decimal"]
        entry = {"day": row["local_date"], "kind": "dividend", "amount": value, "currency": row["basis_currency"],
                 "account": labels.get(row["account_id"])}
        if tax_of is not None:
            known, tax = tax_of(row["event_ref"])
            entry["tax"] = tax if known else None
        if pooled_of is not None:
            known, tax = pooled_of(row["event_ref"])
            entry["tax_pooled"] = tax if known else None
        result[row["asset_id"]].append(entry)
    return result


def _holdings(positions: list[dict[str, Any]], day_keys: list[str]) -> dict[str, dict[int, str | None]]:
    """Je Asset und Tag das Konto, auf dem es liegt - None, wenn es an dem Tag auf mehreren Konten liegt (#501)."""
    index_of = {day: position for position, day in enumerate(day_keys)}
    found: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in positions:
        position = index_of.get(row["day"])
        if position is not None and row.get("quantity_decimal") not in (None, "0") and exact_amount_v1(row["quantity_decimal"]) != 0:
            found[row["asset_id"]][position].add(row["account_id"])
    return {asset: {position: (next(iter(accounts)) if len(accounts) == 1 else None) for position, accounts in days.items()}
            for asset, days in found.items()}


def asset_key_v1(asset_id: str) -> str:
    """Der Schluessel eines Assets in der Tageshistorie (rc.317, #512): nicht umkehrbar, aus der Kennung gebildet. Die Analyse
    bildet ihn aus der Kennung in der Momentaufnahme ebenso (analysis_moment_key_v1) und ordnet so Kurs und Asset zu."""
    return "akey_" + hashlib.sha256(f"portfolio_history_asset|{asset_id}".encode("utf-8")).hexdigest()[:24]


def _assets(canonical: Path) -> dict[str, dict[str, Any]]:
    """Bezeichnung, Art und Bewertungsart je Asset. Gleiche Bezeichnungen bekommen einen Zusatz, damit die Auswahl in der
    Analyse eindeutig bleibt."""
    connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT asset_id, display_name, asset_type, valuation_method FROM asset ORDER BY display_name, asset_id").fetchall()
    finally:
        connection.close()
    seen: dict[str, int] = defaultdict(int)
    result = {}
    for asset_id, name, asset_type, method in rows:
        seen[name] += 1
        result[asset_id] = {"label": name if seen[name] == 1 else f"{name} ({seen[name]})", "asset_type": asset_type,
                            "valuation_method": method}
    return result


def _ledger(data_space: Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    """Die aktuellen Buchungen des Bestands - einmal gelesen fuer Klick-Angaben und Zahlungsfluesse."""
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding.get("status") != "available" or not binding.get("ledger_path"):
        return []
    connection = sqlite3.connect("file:" + str(binding["ledger_path"]) + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in connection.execute(
            "SELECT event_ref, event_type, asset_id, account_id, local_date, quantity_decimal, unit_price_decimal,"
            " gross_economic_amount_decimal, gross_amount_decimal, gross_income_decimal, monetary_fee_decimal, net_trade_proceeds_decimal,"
            " basis_currency"
            " FROM current_asset_activity_event")]
    finally:
        connection.close()


def _events(ledger: list[dict[str, Any]], canonical: Path, fifo: dict[str, dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Je Buchung Art, Menge, Stueckpreis, Betrag, Gebuehr, Waehrung und Konto (Bezeichnung) - fuer den Klick auf einen Punkt;
    bei einem Verkauf dazu die Rechnung je Lot (#485)."""
    if not ledger:
        return {}
    accounts = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
    try:
        labels = dict(accounts.execute("SELECT account_id, display_name FROM account").fetchall())
    finally:
        accounts.close()
    dates = {row["event_ref"]: row["local_date"] for row in ledger}
    return {row["event_ref"]: {
        "kind": row["event_type"] if row["event_type"] in EVENT_KINDS else "other", "quantity": row["quantity_decimal"],
        "unit_price": row["unit_price_decimal"],
        "amount": row["gross_economic_amount_decimal"] if row["gross_economic_amount_decimal"] is not None else row["gross_amount_decimal"],
        "fee": row["monetary_fee_decimal"], "currency": row["basis_currency"], "account": labels.get(row["account_id"]),
        "lots": sale_lots_v1(row, (fifo or {}).get(row["event_ref"]), dates) if row["event_type"] == "sell" else []}
        for row in ledger}


def _text(value: Any) -> str | None:
    return None if value is None else amount_text_v1(value)


def _portfolio_series(days: list[dict[str, Any]]) -> dict[str, list[Any]]:
    series: dict[str, list[Any]] = {"day": [row["day"] for row in days]}
    for field in PORTFOLIO_FIELDS:
        series[field] = [row[SUMMARY_SOURCE[field]] for row in days]
    # Ein Tag ist vollstaendig, wenn alles bewertet ist; sonst markiert ihn die Anzeige. Ohne gehaltenes Asset gibt es
    # nichts zu bewerten - ein Tag nur mit Cash ist vollstaendig.
    series["complete"] = [(bool(row["market_value_complete"]) or not row["held_asset_count"]) and row["overall_status"] == "complete"
                          for row in days]
    return series


def _asset_series(positions: list[dict[str, Any]], day_keys: list[str] | None = None,
                  prices: dict[str, dict[str, list[str]]] | None = None) -> dict[str, dict[str, list[Any]]]:
    """Je Asset und Tag ueber die Konten summiert: Menge, Wert; der Kurs ist je Asset und Tag derselbe.

    Abgangstag (#526, Festlegung 05./06.11.2026): Ein Komplettverkauf ist ein Verkauf wie jeder andere - der Bestand faellt an
    seinem Tag auf 0. Die Reihe fuehrt nur Tage mit Bestand und endete deshalb am Vortag. Nach jedem gehaltenen Abschnitt steht
    nun der erste Tag ohne Bestand mit Menge 0 und Wert 0 (Kurs aus der Marktbewertung, sonst leer) - beim endgueltigen Verkauf
    wie in jeder Luecke. So sehen alle Leser den Ausstieg, nicht nur die Grafik der Analyse (rc.367)."""
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in positions:
        grouped[row["asset_id"]][row["day"]].append(row)
    result = {}
    for asset, by_day in grouped.items():
        series: dict[str, list[Any]] = {"day": [], "quantity": [], "unit_value": [], "market_value": []}
        for day in sorted(by_day):
            rows = by_day[day]
            quantity = sum((exact_amount_v1(row["quantity_decimal"]) for row in rows), start=exact_amount_v1("0"))
            values = [row["market_value_decimal"] for row in rows]
            unit = next((row["unit_value_decimal"] for row in rows if row["unit_value_decimal"] is not None), None)
            series["day"].append(day)
            series["quantity"].append(_text(quantity))
            series["unit_value"].append(unit)
            # Fehlt einem Konto der Wert, fehlt er dem Asset an diesem Tag - eine Teilsumme saehe vollstaendig aus.
            series["market_value"].append(None if any(value is None for value in values)
                                          else _text(sum((exact_amount_v1(value) for value in values), start=exact_amount_v1("0"))))
        if day_keys:
            series = _with_exit_days(series, day_keys, (prices or {}).get(asset))
        result[asset] = series
    return result


def _with_exit_days(series: dict[str, list[Any]], day_keys: list[str], prices: dict[str, list[str]] | None) -> dict[str, list[Any]]:
    """Nach jedem gehaltenen Abschnitt den ersten Tag ohne Bestand anhaengen, solange er im Verlauf liegt."""
    position = {day: index for index, day in enumerate(day_keys)}
    price_of = dict(zip(prices["day"], prices["unit_value"])) if prices else {}
    rows = list(zip(series["day"], series["quantity"], series["unit_value"], series["market_value"]))
    held = {day for day, quantity, _, _ in rows if exact_amount_v1(quantity) != 0}
    out = []
    for index, row in enumerate(rows):
        out.append(row)
        if row[0] not in held or row[0] not in position:
            continue
        following = position[row[0]] + 1
        if following >= len(day_keys):
            continue
        after = day_keys[following]
        if index + 1 < len(rows) and rows[index + 1][0] == after:
            continue
        out.append((after, "0", price_of.get(after), "0"))
    return {"day": [row[0] for row in out], "quantity": [row[1] for row in out], "unit_value": [row[2] for row in out],
            "market_value": [row[3] for row in out]}


def _composition(days: list[dict[str, Any]], positions: list[dict[str, Any]], labels: dict[str, dict[str, Any]],
                 transit: dict[str, Any] | None = None) -> dict[str, Any]:
    """Je Tag der Wert je Assetklasse und das Cash - zusammen das Gesamtvermoegen. Nur bewertete Positionen zaehlen, wie
    im Gesamtvermoegen; Klassen ohne Wert an jedem Tag entfallen."""
    totals: dict[str, dict[str, Any]] = defaultdict(dict)
    for row in positions:
        if not row["valued"] or row["market_value_decimal"] is None:
            continue
        group = COMPOSITION_CLASS_OF.get((labels.get(row["asset_id"]) or {}).get("asset_type"), "other")
        totals[row["day"]][group] = totals[row["day"]].get(group, exact_amount_v1("0")) + exact_amount_v1(row["market_value_decimal"])
    values: dict[str, list[Any]] = {}
    for group in COMPOSITION_CLASSES:
        if group == "transit":
            # Geld zwischen zwei eigenen Konten unterwegs (#481): Teil des Vermoegens, auf keinem Konto gebucht.
            series = [_text((transit or {}).get(row["day"], exact_amount_v1("0"))) for row in days]
        elif group == "cash":
            series = [row["cash_balance_decimal"] if row["cash_balance_decimal"] is not None else "0" for row in days]
            # Cash-Positionen im Bestand (selten) gehoeren zur selben Flaeche.
            series = [_text(exact_amount_v1(value) + totals[row["day"]].get("cash", exact_amount_v1("0"))) for value, row in zip(series, days)]
        else:
            series = [_text(totals[row["day"]].get(group, exact_amount_v1("0"))) for row in days]
        if any(exact_amount_v1(value) != 0 for value in series):
            values[group] = series
    return {"classes": [group for group in COMPOSITION_CLASSES if group in values], "values": values}


def _flows(days: list[dict[str, Any]], positions: list[dict[str, Any]], cash_accounts: list[dict[str, Any]],
           cash_view: dict[str, Any], ledger: list[dict[str, Any]], outside: frozenset[str] = frozenset(),
           transit: dict[str, Any] | None = None) -> dict[str, Any]:
    """Externer Netto-Fluss je Tag ueber alle eigenen Konten (Festlegung 20.10.2026, #480) - als nachvollziehbare Rechnung:

        extern = Kontoaenderung - (Verkaufserloese - Kaufbetraege) - Ertraege + (Ein- - Auslieferungen zum Tageswert)

    Was die Buchungen erklaeren, ist kein Fluss: Ein Kauf vom eigenen Konto hebt sich auf, ein Verkaufserloes auf dem
    eigenen Konto ebenso; einer, dessen Geld kein gefuehrtes Konto zeigt, zaehlt als Ein- bzw. Auszahlung. Ertraege sind
    Dividenden (wie gebucht) und Zinsen auf gezaehlten Konten. Umbuchungen zwischen eigenen Konten heben sich am selben
    Tag auf. Steuern und Gebuehren, die vom Konto abgehen, zaehlen als Abfluss (Festlegung 20.10.2026: Rendite vor
    Steuern). Rewards und Stockdividenden sind Ertrag in Stueck, Stueckgebuehren Kosten - beides kein Fluss. Nur Assets,
    die an dem Tag im Gesamtvermoegen stehen, tragen Kauf, Verkauf und Lieferung bei. "Extern zugeflossen" beginnt beim
    Gesamtvermoegen des ersten Tages und addiert jeden Fluss; der Abstand zum Gesamtvermoegen ist der Anlageerfolg.

    'outside' nennt Cash-Konten (Bezeichnungen) ausserhalb der Anlage (#481): Ihr Saldo zaehlt nicht zum Wert, ihre Zinsen
    nicht zum Ertrag; was von ihnen in die Anlage geht, ist eine Einlage. 'value' ist dann der Wert der Anlage je Tag.
    'transit' (Tag -> Betrag) ist Geld zwischen zwei eigenen Konten unterwegs; es zaehlt zum Cash, sonst saehe die Umbuchung
    wie ein Abfluss und ein spaeterer Zufluss aus."""
    zero = exact_amount_v1("0")
    state: dict[str, dict[str, tuple[bool, Any]]] = defaultdict(dict)
    for row in positions:
        state[row["asset_id"]].setdefault(row["day"], (bool(row["valued"]), row["unit_value_decimal"]))
    keys = {asset: sorted(by_day) for asset, by_day in state.items()}

    def at(asset: str, day: str) -> tuple[bool, Any] | None:
        # Nach einem vollstaendigen Verkauf fehlt die Zeile des Tages; dann gilt der letzte Stand davor.
        index = bisect_right(keys.get(asset, []), day) - 1
        return state[asset][keys[asset][index]] if index >= 0 else None

    parts: dict[str, dict[str, Any]] = {name: defaultdict(lambda: zero) for name in ("trades", "income", "deliveries")}
    open_days: set[str] = set()
    for row in ledger:
        kind, day = row["event_type"], row["local_date"]
        if kind not in FLOW_KINDS + ("dividend",) or not day:
            continue
        if row["basis_currency"] != TARGET_CURRENCY:
            open_days.add(day); continue
        if kind == "dividend":
            # Das Geld einer Dividende steht auf einem Konto, nicht im Asset - es zaehlt unabhaengig von der Bewertung.
            value = row.get("gross_income_decimal") if row.get("gross_income_decimal") is not None else row["gross_amount_decimal"]
            if value is None:
                open_days.add(day)
            else:
                parts["income"][day] += exact_amount_v1(value)
            continue
        status = at(row["asset_id"], day)
        if status is None or not status[0]:
            continue
        if kind == "buy":
            gross = row["gross_economic_amount_decimal"]
            target, amount = "trades", None if gross is None else -(exact_amount_v1(gross) + exact_amount_v1(row["monetary_fee_decimal"] or "0"))
        elif kind == "sell":
            proceeds = row["net_trade_proceeds_decimal"]
            target, amount = "trades", None if proceeds is None else exact_amount_v1(proceeds)
        else:
            quantity, unit = row["quantity_decimal"], status[1]
            target = "deliveries"
            amount = None if quantity is None or unit is None else exact_amount_v1(quantity) * exact_amount_v1(unit) * (1 if kind == "deposit" else -1)
        if amount is None:
            open_days.add(day)
        else:
            parts[target][day] += amount
    # Zinsen nur auf Konten, die an dem Tag im Cash zaehlen - sonst steckten sie nicht in der Kontoaenderung.
    counted = {(row["day"], row["account_label"], row["cash_asset_label"]) for row in cash_accounts if row["in_total"]}
    outside_cash: dict[str, Any] = defaultdict(lambda: zero)
    for row in cash_accounts:
        if row["in_total"] and row["account_label"] in outside and row["balance_target_decimal"] is not None:
            outside_cash[row["day"]] += exact_amount_v1(row["balance_target_decimal"])
    for event in cash_view.get("cash_history") or []:
        if event.get("event_type") != "deposit" or event.get("flow_classification") != "income_receipt":
            continue
        if (event["local_date"], event["account_label"], event["cash_asset_label"]) not in counted or event["account_label"] in outside:
            continue
        if event.get("currency") != TARGET_CURRENCY:
            open_days.add(event["local_date"]); continue
        parts["income"][event["local_date"]] += exact_amount_v1(event["amount_decimal"])
    result: dict[str, Any] = {"net_flow": [], "flow_complete": [], "contributed": [], "value": [],
                              "flow_parts": {"cash_change": [], "trades": [], "income": [], "deliveries": []}}
    pending = sorted(set().union(*(set(values) for values in parts.values())) | open_days)
    position, total, previous_cash = 0, zero, zero
    for index, row in enumerate(days):
        day = row["day"]
        moving = (transit or {}).get(day, zero)
        cash = (exact_amount_v1(row["cash_balance_decimal"]) if row["cash_balance_decimal"] is not None else zero) - outside_cash[day] + moving
        worth = None if row["net_worth_decimal"] is None else exact_amount_v1(row["net_worth_decimal"]) - outside_cash[day] + moving
        result["value"].append(None if worth is None else _text(worth))
        # Buchungen an Tagen ohne eigene Zeile gehen in den naechsten Tag der Reihe ein.
        sums, whole = {name: zero for name in parts}, True
        while position < len(pending) and pending[position] <= day:
            for name in parts:
                sums[name] += parts[name].get(pending[position], zero)
            whole = whole and pending[position] not in open_days; position += 1
        if index == 0:
            for name in result["flow_parts"]:
                result["flow_parts"][name].append(None)
            result["net_flow"].append(None); result["flow_complete"].append(True)
            total = worth if worth is not None else zero
        else:
            change = cash - previous_cash
            flow = change - sums["trades"] - sums["income"] + sums["deliveries"]
            for name, value in (("cash_change", change), ("trades", sums["trades"]), ("income", sums["income"]), ("deliveries", sums["deliveries"])):
                result["flow_parts"][name].append(_text(value))
            result["net_flow"].append(_text(flow)); result["flow_complete"].append(whole)
            total += flow
        result["contributed"].append(_text(total))
        previous_cash = cash
    return result


def _accounts(canonical: Path) -> dict[str, dict[str, Any]]:
    """Je Konto Bezeichnung, Kontoart und Institut - gelesen, nicht veraendert."""
    connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT account_id, display_name, account_type, institution_label FROM account").fetchall()
    finally:
        connection.close()
    return {account: {"label": label, "account_type": kind, "institution": (institution or "").strip() or label}
            for account, label, kind, institution in rows}


def _scope(data_space: Path, context: DesktopProductAssetActivityContextV1, accounts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Je Cash-Konto (Bezeichnung): gehoert es zur Anlage, und ist das festgelegt? Ohne Angabe zaehlt es zur Anlage."""
    stored = read_investment_scope_v1(data_space, context)["accounts"]
    result = {}
    for account, meta in sorted(accounts.items(), key=lambda item: item[1]["label"]):
        if meta["account_type"] not in CASH_ACCOUNT_TYPES:
            continue
        entry = stored.get(account)
        result[meta["label"]] = {"institution": meta["institution"], "in_investment": True if entry is None else entry["in_investment"],
                                 "scope_set": entry is not None}
    return result


def _rate(value: float | None) -> str | None:
    if value is None or value != value or value in (float("inf"), float("-inf")):
        return None
    text = f"{value:.{RATE_DIGITS}f}"
    return "0" if text.strip("-0.") == "" else text


def _xirr(cash_flows: list[tuple[float, float]], scale: float = 365.0) -> float | None:
    """Geldgewichtete Rendite: der Satz je 'scale' Tage, bei dem der Barwert aller Zahlungen null ist. Je Zeitraum gerechnet
    (scale = Laenge des Zeitraums) bleibt sie auch fuer wenige Tage im Suchbereich; p. a. folgt daraus. Halbierung statt
    Newton - langsamer, aber ohne Ausreisser; None, wenn es keinen Vorzeichenwechsel gibt."""
    if not any(amount > 0 for _, amount in cash_flows) or not any(amount < 0 for _, amount in cash_flows):
        return None

    def present(rate: float) -> float:
        return sum(amount / (1.0 + rate) ** (days / scale) for days, amount in cash_flows)

    low, high = -0.9999, 10.0
    try:
        value_low, value_high = present(low), present(high)
    except (OverflowError, ZeroDivisionError):
        return None
    if value_low * value_high > 0:
        return None
    for _ in range(120):
        middle = (low + high) / 2.0
        value = present(middle)
        if (value > 0) == (value_low > 0):
            low, value_low = middle, value
        else:
            high = middle
    return (low + high) / 2.0


def _returns(days: list[str], values: list[Any], flows: list[Any], complete: list[bool], spans: bool = True,
             neutral: list[Any] | None = None, active: tuple[int, int] | None = None,
             split: list[tuple[Any, Any]] | None = None) -> dict[str, Any]:
    """Zeitgewichteter Index je Tag und Renditen je Zeitraum fuer die Anlage.

    Tagesrendite: Ein Zufluss steht am Anfang des Tages (er arbeitet mit), ein Abfluss am Ende (er hat bis dahin
    mitgearbeitet): r = Wert / (Vortag + Zufluss) - 1 bzw. r = (Wert - Abfluss) / Vortag - 1. Ohne Wert am Vortag
    (Beginn, leere Anlage) gilt 0. Der Index ist das Produkt; je Zeitraum folgt daraus die zeitgewichtete Rendite (TWR),
    vergleichbar mit Fonds und Indizes. Die geldgewichtete (IZF/XIRR) nimmt Anfangswert, Fluesse und Endwert als
    Zahlungen und misst damit auch, wann Geld kam und ging.

    'neutral' (je Tag, optional) sind Wertaenderungen ohne Buchung und ohne Erfolg: Beginn oder Ende der Bewertung eines
    Assets. Sie zaehlen fuer Rendite und Erfolg wie ein Fluss, erscheinen aber nicht unter den externen Zu- und Abfluessen.

    'active' (erster und letzter Index mit Bestand oder Buchung) schneidet jeden Zeitraum auf die Haltedauer zu - fuer ein
    Asset oder eine Klasse. "Seit Beginn" beginnt dann am Tag vor dem ersten Kauf (Wert 0) und endet mit dem letzten Verkauf.

    "TWR p. a." rechnet ueber die Tage mit Bestand ('held_days': Tage, an denen Kapital arbeitet), nicht ueber die Spanne:
    An Tagen ohne Bestand bleibt der Index ohnehin stehen, und ein kompletter Ausstieg mit spaeterem Wiedereinstieg soll die
    Jahresrate nicht verduennen (Festlegung 21.10.2026). Der IZF braucht das nicht - er gewichtet das Kapital nach der Zeit,
    in der es angelegt ist; sein "p. a." folgt der Spanne.

    'split' (je Tag Zu- und Abfluss getrennt, optional; rc.294 fuer die Sicht je Konto) rechnet einen Tag mit beidem als
    r = (Wert + Abfluss) / (Vortag + Zufluss) - 1. Ein Konto, das am selben Tag kauft und alles auf ein anderes Konto
    uebertraegt, endet bei 0 - mit dem Nettofluss fiele der Index dort auf null."""
    numbers = [None if value is None else float(exact_amount_v1(value)) for value in values]
    neutral_values = [exact_amount_v1("0")] * len(days) if neutral is None else [exact_amount_v1("0") if item is None else item for item in neutral]
    flow_numbers = [(0.0 if flow is None else float(exact_amount_v1(flow))) + float(extra) for flow, extra in zip(flows, neutral_values)]
    index, level, working = [], 1.0, []
    for position in range(len(days)):
        works = False
        if position > 0:
            before, after, flow = numbers[position - 1], numbers[position], flow_numbers[position]
            if before is not None and after is not None:
                if split is not None:
                    inflow, outflow = (float(item) for item in split[position])
                    base, end = before + inflow, after + outflow
                else:
                    base = before + flow if flow >= 0 else before
                    end = after if flow >= 0 else after - flow
                if base > 1.0:
                    level *= end / base
                    works = True
        index.append(level)
        working.append(works)
    last = date.fromisoformat(days[-1])
    first = date.fromisoformat(days[0])
    periods: list[tuple[str, str, date, date]] = [("all", "Seit Beginn", first, last)]
    for years, label in ((1, "1 Jahr"), (3, "3 Jahre"), (5, "5 Jahre")):
        try:
            start = date(last.year - years, last.month, last.day)
        except ValueError:  # 29. Februar
            start = date(last.year - years, last.month, 28)
        if start > first:
            periods.append((f"{years}y", label, start, last))
    for year in range(first.year, last.year + 1):
        start = max(first, date(year - 1, 12, 31))
        end = min(last, date(year, 12, 31))
        if end > start:
            periods.append((str(year), str(year) if end == date(year, 12, 31) else f"{year} (bis {end.strftime('%d.%m.')})", start, end))
    keys = [date.fromisoformat(day) for day in days]

    def measure(key: str, label: str, start: date, end: date) -> dict[str, Any] | None:
        begin = max(0, bisect_right(keys, start) - 1)
        stop = bisect_right(keys, end) - 1
        if active is not None:
            begin, stop = max(begin, active[0] - 1, 0), min(stop, active[1])
        if stop <= begin or numbers[begin] is None or numbers[stop] is None:
            return None
        span = (keys[stop] - keys[begin]).days
        held = sum(1 for position in range(begin + 1, stop + 1) if working[position])
        twr = index[stop] / index[begin] - 1.0
        net_flow = sum((exact_amount_v1(flows[position]) for position in range(begin + 1, stop + 1) if flows[position] is not None),
                       start=exact_amount_v1("0"))
        valuation_flow = sum((neutral_values[position] for position in range(begin + 1, stop + 1)), start=exact_amount_v1("0"))
        start_value, end_value = exact_amount_v1(values[begin]), exact_amount_v1(values[stop])
        cash_flows = [(0.0, -numbers[begin])] + [(float((keys[position] - keys[begin]).days), -flow_numbers[position])
                                                   for position in range(begin + 1, stop + 1) if flow_numbers[position] != 0]
        cash_flows.append((float(span), numbers[stop]))
        mwr = _xirr(cash_flows, float(max(span, 1)))
        return {
            "period": key, "label": label, "start_day": days[begin], "end_day": days[stop], "day_span": span, "held_days": held,
            "start_value": _text(start_value), "end_value": _text(end_value), "net_flow": _text(net_flow),
            "gain": _text(end_value - start_value - net_flow - valuation_flow), "valuation_flow": _text(valuation_flow), "twr": _rate(twr),
            "twr_annualised": _rate((1.0 + twr) ** (365.0 / held) - 1.0) if held >= 365 and twr > -1.0 else None,
            "mwr": _rate(mwr) if mwr is not None else None,
            "mwr_annualised": _rate((1.0 + mwr) ** (365.0 / span) - 1.0) if mwr is not None and span >= 365 and mwr > -1.0 else None,
            "complete": all(complete[begin:stop + 1])}

    result = [row for row in (measure(*period) for period in periods) if row is not None]
    # Jede Spanne "von Jahr bis Jahr" vorab (#485): die Anzeige waehlt nur aus, statt selbst zu rechnen.
    year_spans = []
    for first_year in (range(first.year, last.year + 1) if spans else ()):
        for last_year in range(first_year, last.year + 1):
            row = measure(f"{first_year}-{last_year}", f"{first_year}–{last_year}" if last_year > first_year else str(first_year),
                          max(first, date(first_year - 1, 12, 31)), min(last, date(last_year, 12, 31)))
            if row is not None:
                year_spans.append(row)
    return {"twr_index": [_rate(level) for level in index], "periods": result, "year_spans": year_spans}


def _interest_yield(cash_rows: list[dict[str, Any]], cash_view: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]:
    """Je Cash-Konto und Jahr: Zinsen, durchschnittlicher Saldo an den gezaehlten Tagen und die Zinsrendite p. a. daraus."""
    balances: dict[tuple[str, int], list[Any]] = defaultdict(list)
    for row in cash_rows:
        if row["in_total"] and row["balance_target_decimal"] is not None:
            balances[(row["account_label"], int(row["day"][:4]))].append(exact_amount_v1(row["balance_target_decimal"]))
    interest: dict[tuple[str, int], Any] = defaultdict(lambda: exact_amount_v1("0"))
    for event in cash_view.get("cash_history") or []:
        if event.get("event_type") == "deposit" and event.get("flow_classification") == "income_receipt" and event.get("currency") == TARGET_CURRENCY:
            interest[(event["account_label"], int(event["local_date"][:4]))] += exact_amount_v1(event["amount_decimal"])
    result = []
    for label, meta in scope.items():
        years = sorted({year for account, year in set(balances) | set(interest) if account == label})
        rows = []
        for year in years:
            counted = balances.get((label, year), [])
            average = sum(counted, start=exact_amount_v1("0")) / len(counted) if counted else None
            earned = interest.get((label, year), exact_amount_v1("0"))
            rate = float(earned) / float(average) * 365.0 / len(counted) if average is not None and average > 0 else None
            rows.append({"year": year, "interest": _text(earned), "average_balance": None if average is None else _text(average),
                         "counted_days": len(counted), "yield_annualised": _rate(rate)})
        result.append({"label": label, "institution": meta["institution"], "in_investment": meta["in_investment"],
                       "scope_set": meta["scope_set"], "years": rows})
    return result


def _account_flows(days: list[dict[str, Any]], cash_rows: list[dict[str, Any]], cash_view: dict[str, Any],
                   ledger: list[dict[str, Any]], accounts: dict[str, dict[str, Any]], scope: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Externe Fluesse je Cash-Konto und Monat, zum Abgleich mit den Auszuegen (Festlegung 20.10.2026: je Konto, nicht je
    Institut). Je Konto und Tag: Kontoaenderung - was Buchungen dort erklaeren - Umbuchungen = extern.

    - Kauf und Verkauf: das Konto, auf dem genau der Betrag gebucht ist - beim selben Institut, am Handelstag oder bis zu
      VALUTA_DAYS Tage spaeter (Valuta); bei einem Institut ohne gefuehrtes Konto auf irgendeinem eigenen Konto (bezahlt
      von dort). Danach die Summe der Kaeufe bzw. Verkaeufe eines Depots am Tag (Teilausfuehrungen in einer Zeile). Ohne
      Treffer das Konto, auf dem das Depot sonst abrechnet; ohne solches ein eigener Posten des Depots.
    - Dividenden wie Kaeufe, mit einer Gutschrift zwischen 60 % und 100 % des gebuchten Betrags (einbehaltene Steuer).
    - Zinsen: ihr Konto.
    - Umbuchung: ein Abgang und ein gleich hoher Eingang auf zwei eigenen Konten innerhalb von TRANSFER_DAYS Tagen; die
      Paare kommen mit zurueck, damit das Geld dazwischen als "unterwegs" zaehlt.
    Was bleibt, ist extern - Gehalt, Ausgaben, Steuern, Kontostart oder das Ende einer Auszugsluecke."""
    zero = exact_amount_v1("0")
    tolerance = exact_amount_v1("0.01")
    keys = [row["day"] for row in days]
    known = set(keys)
    first = keys[0]
    labels = set(scope)
    # Die Zuordnung Abrechnung -> Auszugszeile teilt die Historie mit dem vorlaeufigen Cash-Stand (#539).
    matched = match_settlements_v1(cash_view, ledger, accounts, scope)
    events, explained, valuta = matched["events"], matched["explained"], matched["valuta"]
    for item in matched["unmatched"]:
        explained[(item["target"] or f"{item['meta']['label']} (ohne Verrechnungskonto)", item["row"]["local_date"])] += item["amount"]
    # Umbuchungen: was nach den Buchungen bleibt, paarweise zwischen zwei eigenen Konten.
    transfer: dict[tuple[str, str], Any] = defaultdict(lambda: zero)
    pairs: list[dict[str, Any]] = []
    open_deposits = sorted((index for index, event in enumerate(events) if not event["used"] and event["amount"] > 0), key=lambda index: events[index]["day"])
    for index, event in sorted(enumerate(events), key=lambda item: item[1]["day"]):
        if event["used"] or event["amount"] >= 0:
            continue
        sent = date.fromisoformat(event["day"])
        best = None
        for other in open_deposits:
            candidate = events[other]
            if candidate["used"] or candidate["label"] == event["label"] or abs(candidate["amount"] + event["amount"]) > tolerance:
                continue
            gap = abs((date.fromisoformat(candidate["day"]) - sent).days)
            if gap <= TRANSFER_DAYS and (best is None or gap < best[0]):
                best = (gap, other)
        if best is not None:
            match = events[best[1]]; event["used"] = match["used"] = True
            transfer[(event["label"], event["day"])] += event["amount"]
            transfer[(match["label"], match["day"])] += match["amount"]
            pairs.append({"from": event["label"], "to": match["label"], "sent": event["day"], "received": match["day"], "amount": match["amount"]})
    balance: dict[tuple[str, str], Any] = defaultdict(lambda: zero)
    for row in cash_rows:
        if row["in_total"] and row["balance_target_decimal"] is not None and row["account_label"] in labels:
            balance[(row["account_label"], row["day"])] += exact_amount_v1(row["balance_target_decimal"])

    def rolled(values: dict[tuple[str, str], Any]) -> dict[tuple[str, str], Any]:
        result: dict[tuple[str, str], Any] = defaultdict(lambda: zero)
        for (label, day), amount in values.items():
            if day < first:
                continue  # steckt im Anfangsstand
            index = bisect_left(keys, day)
            if index < len(keys):
                result[(label, keys[index] if day not in known else day)] += amount
        return result

    explained_days, transfer_days = rolled(explained), rolled(transfer)
    targets = sorted(labels | {label for label, _ in explained_days})
    result = []
    for label in targets:
        months: dict[str, list[Any]] = {}
        previous = None
        for day in keys:
            current = balance.get((label, day), zero)
            if previous is not None:
                moved = transfer_days.get((label, day), zero)
                rest = (current - previous) - explained_days.get((label, day), zero) - moved
                if rest != 0 or moved != 0:
                    month = months.setdefault(day[:7], [zero, zero, zero, zero])
                    if rest:
                        month[0 if rest > 0 else 1] += rest
                    if moved:
                        month[2 if moved > 0 else 3] += moved
            previous = current
        meta = scope.get(label)
        rows = [{"month": month, "inflow": _text(values[0]), "outflow": _text(values[1]), "transfer_in": _text(values[2]),
                 "transfer_out": _text(values[3]), "valuta_count": valuta.get((label, month), 0)} for month, values in sorted(months.items())]
        if not rows:
            continue
        totals = [sum((exact_amount_v1(row[name]) for row in rows), start=zero) for name in ("inflow", "outflow", "transfer_in", "transfer_out")]
        result.append({"account": label, "institution": meta["institution"] if meta else None,
                       "in_investment": meta["in_investment"] if meta else None, "without_cash_account": meta is None,
                       "inflow": _text(totals[0]), "outflow": _text(totals[1]), "transfer_in": _text(totals[2]), "transfer_out": _text(totals[3]),
                       "months": rows})
    return result, pairs


def _in_transit(days: list[dict[str, Any]], pairs: list[dict[str, Any]], counts=lambda label: True) -> dict[str, Any]:
    """Je Tag das Geld, das eine Umbuchung schon vom einen eigenen Konto abgebucht, dem anderen aber noch nicht gutgeschrieben
    hat - vom Tag des Abgangs bis vor den Tag des Eingangs. 'counts' waehlt die Konten (fuer die Anlage: beide Seiten innen)."""
    keys = [row["day"] for row in days]
    result: dict[str, Any] = defaultdict(lambda: exact_amount_v1("0"))
    for pair in pairs:
        if pair["received"] <= pair["sent"] or not (counts(pair["from"]) and counts(pair["to"])):
            continue
        for index in range(bisect_left(keys, pair["sent"]), bisect_left(keys, pair["received"])):
            result[keys[index]] += pair["amount"]
    return result


def _basis_and_trades(timeline: dict[str, list[tuple[str, int, dict[str, Any]]]], events: dict[str, dict[str, Any]]) -> dict[str, dict[str, list[Any]]]:
    """Je Asset der Einstand als Stufe nach jedem Tag mit Ereignis und die Tage, an denen sich die Menge aenderte."""
    result = {}
    for asset, entries in timeline.items():
        by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for day, _, row in entries:
            by_day[day].append(row)
        steps, trades, previous = [], [], exact_amount_v1("0")
        for day in sorted(by_day):
            rows = by_day[day]
            last = rows[-1]
            quantity_text = last["asset_quantity_after_decimal"]
            quantity = exact_amount_v1(quantity_text) if quantity_text is not None else previous
            steps.append({"day": day, "quantity": _text(quantity), "cost_basis": _basis_text(last["asset_fifo_basis_after"])})
            change = quantity - previous
            if change != 0:
                kinds = {events.get(row["event_ref"], {}).get("kind") for row in rows}
                kind = next((candidate for candidate in ("buy", "sell", "reward", "stock_dividend", "deposit", "withdrawal")
                             if candidate in kinds and (change > 0) == (candidate not in ("sell", "withdrawal"))),
                            "other_in" if change > 0 else "other_out")
                # Ein Tag nur mit Split (#451): eigene Art, keine Ein- oder Auslieferung.
                if all("split" in row for row in rows):
                    kind = "split"
                trades.append({"day": day, "kind": kind, "quantity_change": _text(change),
                               "events": [events[row["event_ref"]] for row in rows if row["event_ref"] in events]})
            previous = quantity
        result[asset] = {"basis": steps, "trades": trades}
    return result


def build_portfolio_history_artifact_v1(data_space_path: str | Path, context_value: Any, completed_at_utc: str,
                                        canonical_path: str | Path | None = None, previous_net: Any = None,
                                        net_runner: Any = None, sheet_builder: Any = None) -> dict[str, Any] | None:
    """Das Artefakt aus der gespeicherten Reihe - None, solange es keine Reihe gibt. Schreibt nichts.

    `previous_net` ist der Netto-Block der letzten Veroeffentlichung: Sind Buchungen, Steuereinstellungen und Modul gleich,
    gilt seine Steuer je Ereignis weiter (die Rechenblaetter aller Jahre kosten sonst rund eine Minute)."""
    if not isinstance(context_value, DesktopProductAssetActivityContextV1):
        _abort("portfolio_history_publication_context_invalid")
    completed = _utc(completed_at_utc)
    data_space = Path(data_space_path)
    canonical = Path(canonical_path) if canonical_path is not None else data_space / "canonical.sqlite"
    try:
        history = read_portfolio_history_v1(data_space, context_value, detail=True)
        if history["status"] != "ready" or not history["days"]:
            return None
        labels = _assets(canonical)
        # Kurse je Asset auch ohne Bestand (#526): nur fuer Assets in Marktbewertung, bis zum letzten Tag des Verlaufs.
        prices = {asset: rows for asset, rows in asset_price_series_v1(data_space, history["days"][-1]["day"], context_value).items()
                  if (labels.get(asset) or {}).get("valuation_method") == "external_market"}
        series = _asset_series(history["positions"], [row["day"] for row in history["days"]], prices)
        ledger = _ledger(data_space, context_value)
        timeline = holdings_timeline_v1(data_space, context_value)
        fifo = realized_events_v1(data_space)
        years = sorted({int(row["day"][:4]) for row in history["days"]})
        # Netto-Sicht (#481, #494): Faellt sie aus, bleibt die Brutto-Sicht vollstaendig - Netto steht dann als "nicht verfuegbar".
        # Die Lot-Spur des FIFO-Kerns einmal lesen - fuer Projektion, Netto und die Sicht je Konto (rc.294).
        try:
            trace = lot_trace_v1(data_space, context_value, canonical)
        except Exception:
            trace = None
        try:
            net_state = NetState(data_space, context_value, canonical, ledger, years, previous_net, sheet_builder, trace)
        except Exception:
            net_state = None
        net_ready = net_state is not None and net_state.status == "ready"
        event_rows = _events(ledger, canonical, fifo)
        if net_ready:
            for ref, event in event_rows.items():
                if event["kind"] in ("sell", "reward", "stock_dividend"):
                    known, tax = net_state.event_tax(ref)
                    event["tax"] = tax if known else None
                    # Je Topf im Jahr (#501): die verteilte Steuer des Topfs; ausserhalb gerechneter Jahre wie je Ereignis.
                    known, tax = net_state.event_tax_pooled(ref)
                    event["tax_pooled"] = tax if known else None
        steps = _basis_and_trades(timeline, event_rows)
        income_events = _income_events(ledger, canonical, net_state.event_tax if net_ready else None,
                                       net_state.event_tax_pooled if net_ready else None)
        portfolio = _portfolio_series(history["days"])
        try:
            cash_view = read_desktop_cash_coverage_view_v1(canonical, data_space, context_value)
        except DesktopCashCoverageV1Error as error:
            # Noch kein Cash-Asset oder Cash-Konto (neues Portfolio): keine Cash-Erklaerung, aber kein Grund, die ganze Reihe
            # nicht zu veroeffentlichen - wie in der Bereitschaftspruefung (am Demo-Home gefunden, #487).
            if error.code != "desktop_cash_coverage_catalog_invalid":
                raise
            cash_view = {"status": "absent", "periods": [], "cash_history": []}
        accounts = _accounts(canonical)
        scope = _scope(data_space, context_value, accounts)
        outside = frozenset(label for label, meta in scope.items() if not meta["in_investment"])
        account_flows, pairs = _account_flows(history["days"], history["cash"], cash_view, ledger, accounts, scope)
        transit = _in_transit(history["days"], pairs)
        transit_inside = _in_transit(history["days"], pairs, lambda label: label not in outside)
        overall = _flows(history["days"], history["positions"], history["cash"], cash_view, ledger, transit=transit)
        overall.pop("value")
        portfolio.update(overall)
        portfolio["in_transit"] = [_text(transit.get(row["day"], exact_amount_v1("0"))) for row in history["days"]]
        portfolio["composition"] = _composition(history["days"], history["positions"], labels, transit)
        anlage = _flows(history["days"], history["positions"], history["cash"], cash_view, ledger, outside, transit_inside)
        day_keys = [row["day"] for row in history["days"]]
        perf = performance_v1(day_keys, history["positions"], timeline, fifo, ledger,
                              lambda asset: COMPOSITION_CLASS_OF.get((labels.get(asset) or {}).get("asset_type"), "other"), _returns,
                              portfolio["complete"])
        returns = _returns(day_keys, anlage["value"], anlage["net_flow"], portfolio["complete"], neutral=perf["neutral"])
        # Kennwerte je Konto fuer Assets auf mehreren Konten (rc.294); faellt die Rechnung aus, bleibt die Sicht je Asset.
        try:
            account_views = {} if trace is None else account_views_v1(day_keys, history["positions"], ledger, fifo, timeline, trace, event_rows,
                                                                      income_events, _returns, portfolio["complete"])
        except Exception:
            account_views = {}
        # Zinsen der Konten in der Anlage: Ertraege der Flussrechnung ohne die Dividenden.
        interest = [exact_amount_v1("0") if value is None else exact_amount_v1(value) - dividend
                    for value, dividend in zip(anlage["flow_parts"]["income"], perf["dividends"])]
        with_bridge_v1(returns["periods"], day_keys, perf["parts"], {"interest": interest})
        with_bridge_v1(returns["year_spans"], day_keys, perf["parts"], {"interest": interest})
        # Bewertungsuebergaenge je Tag (#499): Sie zaehlen fuer Rendite und IZF wie ein Fluss; die Anzeige rechnet den IZF-Verlauf damit.
        investment = {"value": anlage["value"], "net_flow": anlage["net_flow"], "valuation_flow": [_text(value) for value in perf["neutral"]],
                      "flow_parts": anlage["flow_parts"],
                      "flow_complete": anlage["flow_complete"], "contributed": anlage["contributed"], "twr_index": returns["twr_index"],
                      "periods": returns["periods"], "year_spans": returns["year_spans"],
                      "intervals": intervals_v1(day_keys, anlage["value"], anlage["net_flow"], returns["twr_index"], perf["parts"], interest,
                                                _xirr, _rate, returns["periods"] + returns["year_spans"], perf["neutral"]),
                      "cash_accounts": _interest_yield(history["cash"], cash_view, scope),
                      "accounts_flows": account_flows,
                      "in_transit": [_text(transit_inside.get(row["day"], exact_amount_v1("0"))) for row in history["days"]],
                      "outside_count": len(outside), "unset_count": sum(1 for meta in scope.values() if not meta["scope_set"])}
        class_of = lambda asset: COMPOSITION_CLASS_OF.get((labels.get(asset) or {}).get("asset_type"), "other")  # noqa: E731
        # Eigene Gruppen (#483 Stufe 2): dieselbe Rechnung wie fuer eine Klasse, ueber die gewaehlten Assets.
        settings = _analysis_settings(data_space, context_value)
        custom: list[dict[str, Any]] = []
        for group in (settings or {}).get("groups", []):
            custom.append({"key": group["group_key"], "meta": group,
                           "row": group_performance_v1(day_keys, perf["dailies"], group["members"], _returns, portfolio["complete"])})
        net = None
        if net_state is not None:
            try:
                # Ein Einzelkonto einer FIFO-Wallet (#508) zaehlt nicht je Konto, sondern mit seiner Wallet.
                views_early = [row for rows in account_views.values() for row in rows if row["_net"]]
                # Je Konto das Institut (#501) - dieselbe Zuordnung wie im Abschluss.
                from migrations.reference.institution_tax_settings_v1 import InstitutionTaxSettingsV1Error, account_institution_keys_v1
                try:
                    institutions = account_institution_keys_v1(data_space, context_value)
                except InstitutionTaxSettingsV1Error:
                    institutions = {}
                # Eine FIFO-Wallet gehoert zum Institut ihres Hauptkontos (alle ihre Konten haben dasselbe Institut).
                from workers.reference.portfolio_history_accounts_v1 import FIFO_WALLET_KEY_PREFIX
                for main in set((trace or {}).get("wallets", {}).values()):
                    if main in institutions:
                        institutions[FIFO_WALLET_KEY_PREFIX + main] = institutions[main]
                net = net_apply_v1(net_state, day_keys, perf, ledger, class_of, [returns["periods"], returns["year_spans"]],
                                   lambda label: label not in outside, net_runner, interest,
                                   {group["key"]: (group["meta"]["members"], group["row"]) for group in custom},
                                   holdings=_holdings(history["positions"], day_keys), institution_of=institutions,
                                   account_dailies={row["_key"]: row["_daily"] for row in views_early}, fifo_events=fifo)
            except Exception:
                net = None
        if net is None:
            for periods in [*(row["periods"] for row in perf["assets"].values()), *(row["periods"] for row in perf["classes"].values()),
                            returns["periods"], returns["year_spans"], *(group["row"]["periods"] for group in custom)]:
                with_net_v1(periods, day_keys, [], [], [], available=False)
            net = {"block": {"status": "unavailable", "reason": "net_failed" if net_state is not None else "net_setup_failed",
                             "available": False}, "assets": {}, "classes": {}, "groups": {}, "investment": {"cost": None}, "available": False}
        investment["net_cost"] = None if net["investment"]["cost"] is None else [_text(value) for value in net["investment"]["cost"]]
        pooled_cost = net["investment"].get("cost_pooled")
        investment["net_cost_pooled"] = None if pooled_cost is None else [_text(value) for value in pooled_cost]
        # Netto je Konto (#499): dieselben Regeln mit den Losen des Kontos; ohne Netto-Sicht sichtbar nicht verfuegbar.
        views = [row for rows in account_views.values() for row in rows]
        try:
            account_nets = account_net_v1(net_state, day_keys, {row["_key"]: row["_daily"] for row in views if row["_net"]}, ledger, fifo,
                                          bool(net.get("available"))) if net_state is not None and views else {}
        except Exception:
            account_nets = {}
        index_of_day = {day: position for position, day in enumerate(day_keys)}
        for row in views:
            own = account_nets.get(row["_key"])
            if own is None:
                with_net_v1(row["performance"]["periods"], day_keys, [], [], [], available=False)
                continue
            with_net_v1(row["performance"]["periods"], day_keys, own["realized_tax"], own["income_tax"], own["parts"], warned=own["warned"])
            row["net"] = {"cost": [_text(own["cost_by_day"][index_of_day[day]]) for day in row["days"]["day"]],
                          "realized_net_steps": own["realized_net_steps"], "reason": own["reason"], "blocked_days": own["blocked_days"],
                          "warned_days": own["warned_days"], "fee_rate": own["fee_rate"], "fee_source": own["fee_source"]}
        for row in views:
            row.pop("_key", None); row.pop("_daily", None); row.pop("_net", None)
        # Alle Assets ohne Cash (#502): dieselbe Rechnung wie die Anlage, nur ueber die Assets. Die Differenz zur Anlage zeigt, was
        # das geparkte Cash gekostet oder gebracht hat; je Asset laesst sich das nicht rechnen (Cash nur als Tagessaldo je Konto).
        from workers.reference.portfolio_history_performance_v1 import _combine
        size = len(day_keys)
        if perf["dailies"]:
            every_value, _, every_flow, every_neutral = _combine(list(perf["dailies"].values()), size)
        else:
            every_value, every_flow, every_neutral = [exact_amount_v1("0")] * size, [exact_amount_v1("0")] * size, [exact_amount_v1("0")] * size
        assets_only = _returns(day_keys, [None if value is None else _text(value) for value in every_value],
                               [None] + [_text(value) for value in every_flow[1:]], portfolio["complete"], neutral=every_neutral)
        with_bridge_v1(assets_only["periods"], day_keys, perf["parts"])
        with_bridge_v1(assets_only["year_spans"], day_keys, perf["parts"])
        investment["assets_only"] = {"twr_index": assets_only["twr_index"], "periods": assets_only["periods"], "year_spans": assets_only["year_spans"]}
        # Vergleichsindizes (#482, #502): je Index das Niveau je Tag - mit Ausschuettungen, wo die Kursquelle sie bereinigt, und
        # taeglich fest gewichtet; je Zeitraum der Anlage (und ohne Cash) dieselbe Spanne, je Asset, Klasse und Gruppe nur die
        # Tage mit Bestand. Die Eintraege 'benchmarks' der Zeitraeume folgen der Reihenfolge der Indizes.
        members_of: dict[str, list[Any]] = defaultdict(list)
        for asset, daily in perf["dailies"].items():
            members_of[class_of(asset)].append(daily)
        held_rows = [(row["periods"], working_days_v1(perf["dailies"][asset].value, perf["dailies"][asset].flow)) for asset, row in perf["assets"].items()]
        for group, row in perf["classes"].items():
            value, _, flow, neutral = _combine(members_of[group], size)
            held_rows.append((row["periods"], working_days_v1(value, [a + b for a, b in zip(flow, neutral)])))
        for group in custom:
            held_rows.append((group["row"]["periods"], working_days_v1(group["row"]["value"], [a + b for a, b in zip(group["row"]["flow"], group["row"]["neutral"])])))
        components: dict[str, dict[str, Any]] = {}
        benchmarks = []
        for entry in (settings or {}).get("indices", []):
            usable = entry["missing_count"] == 0 and bool(entry["components"])
            parts_of_index = []
            for item in entry["components"]:
                if item["asset_id"] not in components:
                    components[item["asset_id"]] = benchmark_component_v1(data_space, item["asset_id"], day_keys)
                parts_of_index.append({"label": labels[item["asset_id"]]["label"] if item["asset_id"] in labels else item["label"],
                                       "asset_type": item["asset_type"], "weight_percent": item["weight_percent"],
                                       "basis": components[item["asset_id"]]["basis"]})
            levels = composite_levels_v1([components[item["asset_id"]]["levels"] for item in entry["components"]],
                                         [float(Fraction(item["weight_percent"]) / 100) for item in entry["components"]]) if usable else [None] * size
            for periods in (returns["periods"], returns["year_spans"], assets_only["periods"], assets_only["year_spans"]):
                benchmark_periods_v1(periods, day_keys, levels)
            index_steps = daily_steps_v1(levels)
            for periods, working in held_rows:
                held_benchmark_rows_v1(periods, day_keys, index_steps, working)
            known = [position for position, level in enumerate(levels) if level is not None]
            bases = {part["basis"] for part in parts_of_index}
            basis = ("unavailable" if not usable or not known else "total_return" if bases == {"total_return"}
                     else "price_only" if "total_return" not in bases else "mixed")
            benchmarks.append({"ordinal": len(benchmarks) + 1, "label": entry["label"], "components": parts_of_index, "basis": basis,
                               "levels": [_rate(level) for level in levels], "first_day": day_keys[known[0]] if known else None,
                               "missing_days": 0 if not known else sum(1 for position in range(known[0], size) if levels[position] is None)})
        # Aufteilungen: je Tag der Wert, den keine ihrer Gruppen traegt - so ergibt die Aufteilung samt Cash das Gesamtvermoegen.
        from workers.reference.portfolio_history_performance_v1 import _combine as _combine_all
        all_value = _combine_all(list(perf["dailies"].values()), len(day_keys))[0] if perf["dailies"] else [exact_amount_v1("0")] * len(day_keys)
        ordinal_of = {group["key"]: index + 1 for index, group in enumerate(custom)}
        partitions = []
        for partition in (settings or {}).get("partitions", []):
            covered = [group for group in custom if group["key"] in partition["groups"]]
            unassigned = [total - sum((group["row"]["value"][position] for group in covered), start=exact_amount_v1("0"))
                          for position, total in enumerate(all_value)]
            partitions.append({"label": partition["label"], "groups": [ordinal_of[group["key"]] for group in covered],
                               "unassigned": [_text(value) for value in unassigned],
                               "uncovered_labels": [labels[asset]["label"] for asset in partition["uncovered"] if asset in labels and asset in series]})
    except (PortfolioHistoryV1Error, PortfolioSnapshotFreshnessV1Error, DesktopProductAssetActivityV1Error, sqlite3.Error,
            DesktopCashCoverageV1Error, InvestmentScopeV1Error, KeyError, TypeError, ValueError, ZeroDivisionError):
        _abort("portfolio_history_publication_evidence_invalid")
    held_accounts: dict[str, list[str]] = {}
    for row in history["positions"]:
        label = (accounts.get(row["account_id"]) or {}).get("label")
        if label and label not in held_accounts.setdefault(row["asset_id"], []):
            held_accounts[row["asset_id"]].append(label)
    for names in held_accounts.values():
        names.sort(key=str.lower)
    assets = []
    for asset_id in sorted(series, key=lambda key: (labels.get(key, {}).get("label") or "", key)):
        meta = labels.get(asset_id)
        if meta is None:
            _abort("portfolio_history_publication_evidence_invalid")
        extra = steps.get(asset_id, {"basis": [], "trades": []})
        performance = perf["assets"].get(asset_id, {"periods": [], "realized_steps": [], "twr": None})
        # Ein Schluessel statt der Kennung (rc.317, #512): Die Analyse ordnet damit die Positionen der Momentaufnahme dem Asset zu;
        # die Kennung selbst steht nicht im Artefakt.
        entry = {"ordinal": len(assets) + 1, "asset_key": asset_key_v1(asset_id), "label": meta["label"], "asset_type": meta["asset_type"],
                 "valuation_method": meta["valuation_method"], "days": series[asset_id],
                 "basis": extra["basis"], "trades": extra["trades"], "income": income_events.get(asset_id, []),
                 "performance": {"periods": performance["periods"], "realized_steps": performance["realized_steps"]},
                 "twr": performance.get("twr")}
        own = net["assets"].get(asset_id, {})
        if "cost_by_day" in own:
            # Die Liquidationskosten je Tag des Assets - auf dieselben Tage wie Menge und Wert.
            index_of = {day: position for position, day in enumerate(day_keys)}
            entry["net"] = {"cost": [_text(own["cost_by_day"][index_of[day]]) for day in series[asset_id]["day"]],
                            "realized_net_steps": own["realized_net_steps"], "reason": own["reason"], "blocked_days": own["blocked_days"],
                            "warned_days": own["warned_days"],
                            "fee_rate": own["fee_rate"], "fee_source": own["fee_source"]}
            if "cost_by_day_pooled" in own:
                entry["net"]["cost_pooled"] = [_text(own["cost_by_day_pooled"][index_of[day]]) for day in series[asset_id]["day"]]
                entry["net"]["realized_net_steps_pooled"] = own["realized_net_steps_pooled"]
        if "projection" in own:
            entry["projection"] = own["projection"]
        if asset_id in account_views:
            entry["accounts"] = account_views[asset_id]
        # Auf welchen Konten das Asset je lag (#499): die Analyse nennt das Konto ueber der Grafik, auch wenn es nur eines ist.
        entry["held_accounts"] = held_accounts.get(asset_id, [])
        if asset_id in prices:
            entry["prices"] = prices[asset_id]
        assets.append(entry)
    # Beobachtet, nie gehalten (#526): Assets mit Kursreihe, aber ohne einen Tag mit Bestand. Eine eigene Liste, damit Rangliste,
    # Vergleich und Gruppen der Analyse nur gehaltene Assets sehen.
    watched = []
    for asset_id in sorted((key for key in prices if key not in series and key in labels),
                           key=lambda key: (labels[key]["label"] or "", key)):
        meta = labels[asset_id]
        watched.append({"ordinal": len(watched) + 1, "asset_key": asset_key_v1(asset_id), "label": meta["label"],
                        "asset_type": meta["asset_type"], "valuation_method": meta["valuation_method"], "prices": prices[asset_id]})
    days = history["days"]
    body = {
        "portfolio_history_version": VERSION, "status": "completed",
        "tenant_id": context_value.tenant_id, "user_id": context_value.user_id, "data_space_id": context_value.data_space_id,
        "currency": TARGET_CURRENCY, "first_day": days[0]["day"], "last_day": days[-1]["day"], "day_count": len(days),
        "portfolio": portfolio, "investment": investment, "assets": assets, "watched": watched,
        "classes": [{"class": group, **perf["classes"][group],
                     "net_cost": None if group not in net["classes"] else [_text(value) for value in net["classes"][group]["cost_by_day"]],
                     "net_realized_steps": None if group not in net["classes"] else net["classes"][group]["realized_net_steps"],
                     "net_cost_pooled": None if "cost_by_day_pooled" not in net["classes"].get(group, {}) else [
                         _text(value) for value in net["classes"][group]["cost_by_day_pooled"]],
                     "net_realized_steps_pooled": net["classes"].get(group, {}).get("realized_net_steps_pooled")}
                    for group in COMPOSITION_CLASSES if group in perf["classes"]],
        "net": net["block"],
        "benchmarks": benchmarks,
        "groups": [{"ordinal": index + 1, "label": group["meta"]["label"], "partition": group["meta"]["partition"],
                    "member_labels": sorted(labels[asset]["label"] for asset in group["meta"]["members"] if asset in labels),
                    "new_labels": sorted(labels[asset]["label"] for asset in group["meta"]["new_assets"] if asset in labels and asset in series),
                    "missing_count": group["meta"]["missing_count"],
                    "value": [_text(value) for value in group["row"]["value"]], "basis": group["row"]["basis"],
                    "realized_steps": group["row"]["realized_steps"], "periods": group["row"]["periods"], "twr": group["row"]["twr"],
                    "net_cost": None if group["key"] not in net["groups"] else [_text(value) for value in net["groups"][group["key"]]["cost_by_day"]],
                    "net_realized_steps": None if group["key"] not in net["groups"] else net["groups"][group["key"]]["realized_net_steps"],
                    "net_cost_pooled": None if "cost_by_day_pooled" not in net["groups"].get(group["key"], {}) else [
                        _text(value) for value in net["groups"][group["key"]]["cost_by_day_pooled"]],
                    "net_realized_steps_pooled": net["groups"].get(group["key"], {}).get("realized_net_steps_pooled")}
                   for index, group in enumerate(custom)],
        "partitions": partitions,
        "provider_access": False, "network_access": False, "canonical_write": False,
    }
    content = _sha(body)
    artifact = {**body, "portfolio_history_id": "phi_" + content[:32], "content_fingerprint": content, "completed_at_utc": completed}
    artifact["artifact_fingerprint"] = _sha(artifact)
    return artifact


def _analysis_settings(data_space: Path, context: Any) -> dict[str, Any] | None:
    """Vergleichsindex und eigene Gruppen aus den Einstellungen der Analyse (#482, #483); None ohne lesbaren Speicher."""
    from migrations.reference.analysis_settings_v1 import AnalysisSettingsV1Error, read_analysis_settings_v1
    try:
        return read_analysis_settings_v1(data_space, context)
    except AnalysisSettingsV1Error:
        return None


def _previous_net(area: Path) -> Any:
    """Der Netto-Block der zuletzt veroeffentlichten Reihe - fuer die Wiederverwendung der Steuer je Ereignis; sonst None."""
    import json
    try:
        latest = area / "latest.json"
        if not latest.is_file() or latest.is_symlink():
            return None
        run_id = json.loads(latest.read_text(encoding="utf-8")).get("run_id")
        if not isinstance(run_id, str) or "/" in run_id or not run_id.startswith("run_"):
            return None
        artifact = area / "runs" / run_id / "artifact.json"
        if not artifact.is_file() or artifact.is_symlink():
            return None
        return json.loads(artifact.read_text(encoding="utf-8")).get("net")
    except (OSError, ValueError, AttributeError):
        return None


def publish_portfolio_history_v1(data_space_path: str | Path, context_value: Any, published_at_utc: str,
                                 artifacts_root: str | Path | None = None, canonical_path: str | Path | None = None) -> dict[str, Any]:
    """Die Reihe veroeffentlichen, wenn sich ihr Inhalt geaendert hat; sonst nichts schreiben."""
    try:
        published = _utc(published_at_utc)
        root = Path(artifacts_root) if artifacts_root is not None else Path(data_space_path) / "artifacts"
        artifact = build_portfolio_history_artifact_v1(data_space_path, context_value, published, canonical_path, _previous_net(root / AREA_ID))
        result = {"portfolio_history_publication_version": VERSION, "provider_access": False, "network_access": False,
                  "canonical_write": False}
        if artifact is None:
            return {**result, "status": "absent", "first_day": None, "last_day": None, "asset_count": 0}
        summary = {"first_day": artifact["first_day"], "last_day": artifact["last_day"], "asset_count": len(artifact["assets"])}
        # Kern und Teildateien (#503). Die Kennung des Laufs nennt die Aufteilung mit: Ein Lauf von vor rc.297 mit gleichem Inhalt
        # ist ein ganzes Artefakt und gilt nicht als "bereits veroeffentlicht".
        run_id = "run_" + _sha({"content_fingerprint": artifact["content_fingerprint"], "layout": PARTS_LAYOUT})[:32]
        for directory in (root, root / AREA_ID):
            if directory.is_symlink():
                _abort("portfolio_history_publication_failed")
            if not directory.exists():
                directory.mkdir(mode=0o700, parents=True)
            os.chmod(directory, 0o700)
        from workers.reference.portfolio_history_parts_v1 import (
            PortfolioHistoryPartsV1Error, prune_portfolio_history_v1, split_portfolio_history_v1, write_portfolio_history_parts_v1,
        )
        try:
            core, parts = split_portfolio_history_v1(artifact)
        except PortfolioHistoryPartsV1Error:
            _abort("portfolio_history_publication_failed")
        # Der Kern muss dem Schema genuegen, das der Leser prueft - sonst stuende eine Reihe da, die die Analyse nicht lesen
        # kann (rc.300 an einer Kopie gesehen: ein Feld ausserhalb der Aufzaehlung, "display_reader_failed"). Dann bleibt der
        # vorige Stand.
        from apps.desktop_demo.read_latest_artifact_v1 import _validate_demo_schema
        try:
            _validate_demo_schema(core, AREA_ID)
        except Exception:
            _abort("portfolio_history_publication_evidence_invalid")
        try:
            # Auch bei unveraendertem Inhalt: fehlt eine Teildatei, legt dieser Lauf sie wieder an.
            stored = write_portfolio_history_parts_v1(root, parts)
        except PortfolioHistoryPartsV1Error:
            _abort("portfolio_history_publication_failed")
        summary.update({"part_count": len(parts), "parts_written": stored["written"]})
        existing = root / AREA_ID / "runs" / run_id / "artifact.json"
        if existing.is_file() and not existing.is_symlink():
            return {**result, **summary, "status": "already_published"}
        from workers.reference.run_publication_v1 import PublicationRuntimeContext, RunPublicationError, publish_completed_run_v1
        runtime = PublicationRuntimeContext(context_value.tenant_id, context_value.user_id, context_value.data_space_id,
                                            AREA_ID, WRITER_ID, WRITER_ROLE)
        try:
            published_run = publish_completed_run_v1(root / AREA_ID, runtime, run_id, core, published)
        except RunPublicationError:
            _abort("portfolio_history_publication_failed")
        # Aufbewahrung (Festlegung 22.10.2026): die juengsten Laeufe, Vorgabe fuenf, einstellbar im Reiter "Einstellungen" (#500);
        # die Reihe laesst sich jederzeit neu erzeugen.
        from migrations.reference.user_settings_v1 import history_keep_runs_v1
        pruned = (prune_portfolio_history_v1(root, AREA_ID, keep=history_keep_runs_v1(data_space_path, context_value))
                  if published_run.status == "published" else {"runs_deleted": 0, "parts_deleted": 0})
        return {**result, **summary, **pruned, "status": published_run.status}
    except PortfolioHistoryPublicationV1Error:
        raise
    except Exception:
        _abort("portfolio_history_publication_boundary_failed")


__all__ = [
    "AREA_ID", "ARTIFACT_CONTRACT", "PortfolioHistoryPublicationV1Error", "WRITER_ROLE", "build_portfolio_history_artifact_v1",
    "portfolio_history_publication_v1_error_codes", "publish_portfolio_history_v1",
]
