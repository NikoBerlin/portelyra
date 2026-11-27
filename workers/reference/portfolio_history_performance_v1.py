"""Erfolg je Asset, je Assetklasse und fuer die Anlage (#483, #481, #485) - fuer die veroeffentlichte Tageshistorie.

Alles beruht auf gespeicherten Ergebnissen: dem Wert je Asset und Tag aus der Tageshistorie, dem FIFO-Stand (realisierte
GuV je Verkauf, hinzugekommener und verbrauchter Einstand, Lot-Bewegungen) und den Buchungen. Gerechnet wird je Tag:

    Erfolg = realisiert + Aenderung unrealisiert + Ertraege + Wertaenderung der Abgaenge - mitgebrachte Wertaenderung
             der Zugaenge - Stueckgebuehren zum Einstand

(Erfolgsbruecke, Festlegung 20.10.2026). Realisiert ist Erloes minus verbrauchtem Einstand. Ertraege sind Dividenden wie gebucht und Rewards zum Wert bei Zufluss; fuer die Anlage
kommen Zinsen der Konten innerhalb der Anlage dazu. Alles vor Steuern; netto folgt mit #494.

Die Rendite je Asset und Klasse folgt derselben Rechnung wie fuer die Anlage: Kaeufe und Einlieferungen sind Zufluss in die
Position, Verkaeufe, Auslieferungen und Dividenden Abfluss (die Dividende verlaesst die Position als Geld).
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
import statistics
from typing import Any, Callable

from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1
from workers.reference.portfolio_snapshot_freshness_v1 import _basis_text
from workers.reference.portfolio_history_compare_v1 import twr_window_v1

ZERO = exact_amount_v1("0")
# Die Teile der Erfolgsbruecke, in dieser Reihenfolge angezeigt.
BRIDGE_PARTS = ("realized", "unrealised_change", "income", "disposal_change", "delivery_change", "fee_basis")
# Kennzahlen je Intervall und ihre Zusammenfassung (Festlegung 20.10.2026: Werte und Durchschnitte).
INTERVAL_METRICS = ("gain", "realized", "unrealised_change", "income", "net_flow", "twr", "mwr")
GRANULARITIES = ("day", "week", "month", "quarter")


def _text(value: Any) -> str | None:
    return None if value is None else amount_text_v1(value)


def _exact(value: Any) -> Any:
    text = _basis_text(value)
    return None if text is None else exact_amount_v1(text)


def realized_events_v1(data_space: Path) -> dict[str, dict[str, Any]]:
    """Je Buchung des aktuellen FIFO-Stands: Art, Asset, Konto, hinzugekommener und verbrauchter Einstand, realisierte GuV
    und die verbrauchten Lots (Lot, Anschaffungsbuchung, Menge, Einstand). Leer, solange es keinen Stand gibt."""
    path = data_space / "realized-state-v2" / "realized-state.sqlite"
    if not path.is_file():
        return {}
    store = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    store.row_factory = sqlite3.Row
    try:
        rows = store.execute("SELECT world_artifacts_json FROM current_realized_global_artifact").fetchall()
        if not rows:
            return {}
        worlds = sorted({item["world_artifact_ref"] for item in json.loads(rows[0]["world_artifacts_json"])})
        if not worlds:
            return {}
        marks = ",".join("?" for _ in worlds)
        events = store.execute(
            f"SELECT world_artifact_ref,event_sequence,event_ref,event_type,asset_ref,account_ref,basis_added,basis_consumed,"
            f"realized_gain_before_tax FROM realized_event_result WHERE world_artifact_ref IN ({marks})", tuple(worlds)).fetchall()
        movements = store.execute(
            f"SELECT world_artifact_ref,event_sequence,movement_sequence,lot_ref,acquisition_event_ref,quantity_decimal,fifo_basis "
            f"FROM realized_lot_movement WHERE world_artifact_ref IN ({marks}) ORDER BY world_artifact_ref,event_sequence,movement_sequence",
            tuple(worlds)).fetchall()
    finally:
        store.close()
    by_sequence: dict[tuple[str, int], str] = {}
    result: dict[str, dict[str, Any]] = {}
    for row in events:
        by_sequence[(row["world_artifact_ref"], row["event_sequence"])] = row["event_ref"]
        result[row["event_ref"]] = {"type": row["event_type"], "asset": row["asset_ref"], "account": row["account_ref"],
                                    "basis_added": _exact(row["basis_added"]), "basis_consumed": _exact(row["basis_consumed"]),
                                    "realized": _exact(row["realized_gain_before_tax"]), "lots": []}
    for row in movements:
        ref = by_sequence.get((row["world_artifact_ref"], row["event_sequence"]))
        if ref is not None:
            result[ref]["lots"].append({"acquisition_event_ref": row["acquisition_event_ref"], "quantity": row["quantity_decimal"],
                                        "basis": _exact(row["fifo_basis"])})
    return result


def sale_lots_v1(ledger_row: dict[str, Any], event: dict[str, Any] | None, dates: dict[str, str]) -> list[dict[str, Any]]:
    """Die Rechnung eines Verkaufs je Lot: Anschaffung, Menge, Einstand, anteiliger Erloes, GuV (#485). Der Erloes wird nach
    Menge auf die Lots verteilt; die Summe der GuV ist die realisierte GuV des Verkaufs."""
    if event is None or not event["lots"] or ledger_row.get("net_trade_proceeds_decimal") is None:
        return []
    proceeds = exact_amount_v1(ledger_row["net_trade_proceeds_decimal"])
    total = sum((exact_amount_v1(lot["quantity"]) for lot in event["lots"]), start=ZERO)
    if total <= 0:
        return []
    rows = []
    for lot in event["lots"]:
        share = proceeds * exact_amount_v1(lot["quantity"]) / total
        basis = lot["basis"] if lot["basis"] is not None else ZERO
        rows.append({"acquired": dates.get(lot["acquisition_event_ref"]), "quantity": lot["quantity"], "basis": _text(basis),
                     "proceeds": _text(share), "gain": _text(share - basis)})
    return rows


class _Daily:
    """Tagesteile je Asset auf dem Tagesraster der Historie."""

    def __init__(self, size: int):
        self.value: list[Any] = [ZERO] * size        # Marktwert, None = nicht bewertet
        self.basis: list[Any] = [ZERO] * size
        self.flow: list[Any] = [ZERO] * size         # Zufluss in die Position (+), Abfluss (-)
        self.parts = {name: [ZERO] * size for name in BRIDGE_PARTS}
        self.dividends: list[Any] = [ZERO] * size
        self.realized_steps: list[dict[str, Any]] = []


def asset_daily_v1(days: list[str], positions: list[dict[str, Any]], timeline: dict[str, list[tuple[str, int, dict[str, Any]]]],
                   events: dict[str, dict[str, Any]], ledger: list[dict[str, Any]]) -> dict[str, _Daily]:
    """Je Asset und Tag: Wert, Einstand, Fluss in die Position und die Teile der Erfolgsbruecke."""
    size = len(days)
    index_of = {day: position for position, day in enumerate(days)}
    result: dict[str, _Daily] = {}

    def series(asset: str) -> _Daily:
        if asset not in result:
            result[asset] = _Daily(size)
        return result[asset]

    unit: dict[str, dict[int, Any]] = defaultdict(dict)
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in positions:
        position = index_of.get(row["day"])
        if position is not None:
            grouped[(row["asset_id"], position)].append(row)
    for (asset, position), rows in grouped.items():
        daily = series(asset)
        if any(not row["valued"] or row["market_value_decimal"] is None for row in rows):
            daily.value[position] = None
        else:
            daily.value[position] = sum((exact_amount_v1(row["market_value_decimal"]) for row in rows), start=ZERO)
        price = next((row["unit_value_decimal"] for row in rows if row["unit_value_decimal"] is not None), None)
        if price is not None:
            unit[asset][position] = exact_amount_v1(price)
    # Einstand je Tag: Stand nach dem letzten Ereignis bis zu diesem Tag.
    for asset, entries in timeline.items():
        daily = series(asset)
        steps = [(day, _exact(row["asset_fifo_basis_after"])) for day, _, row in entries]
        step_days = [day for day, _ in steps]
        for position, day in enumerate(days):
            hit = bisect_right(step_days, day) - 1
            daily.basis[position] = steps[hit][1] if hit >= 0 and steps[hit][1] is not None else ZERO

    def price_at(asset: str, position: int) -> Any:
        known = unit.get(asset, {})
        for back in range(position, max(-1, position - 10), -1):
            if back in known:
                return known[back]
        return None

    keys = days
    for row in ledger:
        kind, day, asset = row["event_type"], row["local_date"], row["asset_id"]
        if not day or day < keys[0] or day > keys[-1] or row["basis_currency"] != "EUR":
            continue
        position = index_of.get(day)
        if position is None:
            continue
        daily = series(asset)
        event = events.get(row["event_ref"]) or {}
        if kind == "buy" and row["gross_economic_amount_decimal"] is not None:
            daily.flow[position] += exact_amount_v1(row["gross_economic_amount_decimal"]) + exact_amount_v1(row["monetary_fee_decimal"] or "0")
        elif kind == "sell" and row["net_trade_proceeds_decimal"] is not None:
            daily.flow[position] -= exact_amount_v1(row["net_trade_proceeds_decimal"])
            if event.get("realized") is not None:
                daily.parts["realized"][position] += event["realized"]
        elif kind == "dividend":
            value = row.get("gross_income_decimal") if row.get("gross_income_decimal") is not None else row.get("gross_amount_decimal")
            if value is not None:
                amount = exact_amount_v1(value)
                daily.flow[position] -= amount
                daily.dividends[position] += amount
                daily.parts["income"][position] += amount
        elif kind == "reward":
            if event.get("basis_added") is not None:
                daily.parts["income"][position] += event["basis_added"]
        elif kind in ("deposit", "withdrawal"):
            price = price_at(asset, position if kind == "deposit" else max(0, position - 1)) or price_at(asset, position)
            if price is None or row["quantity_decimal"] is None:
                continue
            value = exact_amount_v1(row["quantity_decimal"]) * price
            if kind == "deposit":
                daily.flow[position] += value
                daily.parts["delivery_change"][position] += value - (event.get("basis_added") or ZERO)
            else:
                daily.flow[position] -= value
                daily.parts["disposal_change"][position] += value - (event.get("basis_consumed") or ZERO)
        elif kind == "transfer":
            if event.get("basis_consumed"):
                daily.parts["fee_basis"][position] += event["basis_consumed"]
    for asset, daily in result.items():
        previous = ZERO
        cumulative = ZERO
        for position in range(size):
            value = daily.value[position]
            unrealised = None if value is None else value - daily.basis[position]
            if unrealised is not None:
                daily.parts["unrealised_change"][position] = unrealised - previous
                previous = unrealised
            if daily.parts["realized"][position]:
                cumulative += daily.parts["realized"][position]
                daily.realized_steps.append({"day": days[position], "realized_cumulative": _text(cumulative)})
    return result


def active_range_v1(value: list[Any], flow: list[Any], neutral: list[Any] | None = None) -> tuple[int, int] | None:
    """Erster und letzter Tag mit Bestand, Buchung oder Bewertungsuebergang - die Haltedauer einer Position oder Gruppe."""
    marks = [position for position in range(len(value))
             if (value[position] is None or value[position] != 0) or flow[position] != 0 or (neutral is not None and neutral[position] != 0)]
    return (marks[0], marks[-1]) if marks else None


def bridge_gain_v1(parts: dict[str, list[Any]], position: int) -> Any:
    """Der Erfolg eines Tages aus den Teilen der Bruecke."""
    return (parts["realized"][position] + parts["unrealised_change"][position] + parts["income"][position]
            + parts["disposal_change"][position] - parts["delivery_change"][position] - parts["fee_basis"][position])


def _sum_parts(dailies: list[_Daily], size: int) -> dict[str, list[Any]]:
    """Die Bruecke einer Gruppe: Ein Mitglied zaehlt nur an Tagen, an denen es selbst und am Vortag bewertet ist - wie bei
    Wert und Fluss; der Tag, an dem seine Bewertung beginnt, ist neutral (siehe _combine)."""
    total = {name: [ZERO] * size for name in BRIDGE_PARTS}
    for daily in dailies:
        for name in BRIDGE_PARTS:
            values = daily.parts[name]
            target = total[name]
            for position in range(size):
                if values[position] and daily.value[position] is not None and (position == 0 or daily.value[position - 1] is not None):
                    target[position] += values[position]
    return total


def _combine(dailies: list[_Daily], size: int) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    """Wert, Einstand und Fluss einer Gruppe als Summe - wie das Gesamtvermoegen: Ein an dem Tag nicht bewertetes Mitglied
    zaehlt weder mit Wert noch mit Buchungen. Beginnt oder endet seine Bewertung, aendert sich der Wert der Gruppe ohne
    Buchung; dieser Uebergang ist 'neutral' (weder Erfolg noch externer Fluss) und wird fuer die Rendite herausgerechnet."""
    value, basis, flow, neutral = [ZERO] * size, [ZERO] * size, [ZERO] * size, [ZERO] * size
    for daily in dailies:
        for position in range(size):
            current = daily.value[position]
            before = daily.value[position - 1] if position else current
            if current is None:
                if before is not None and position:
                    neutral[position] -= before
                continue
            value[position] += current
            basis[position] += daily.basis[position]
            if before is None:
                neutral[position] += current
            else:
                flow[position] += daily.flow[position]
    return value, basis, flow, neutral


def with_bridge_v1(periods: list[dict[str, Any]], days: list[str], parts: dict[str, list[Any]],
                   extra: dict[str, list[Any]] | None = None) -> list[dict[str, Any]]:
    """Haengt an jede Zeile die Summen der Bruecke im Zeitraum (ohne den Anfangstag) und den Rest bis zum Erfolg."""
    index_of = {day: position for position, day in enumerate(days)}
    for row in periods:
        begin, stop = index_of[row["start_day"]], index_of[row["end_day"]]
        sums = {name: sum((parts[name][position] for position in range(begin + 1, stop + 1)), start=ZERO) for name in BRIDGE_PARTS}
        for name, values in (extra or {}).items():
            sums[name] = sum((values[position] for position in range(begin + 1, stop + 1)), start=ZERO)
        explained = (sums["realized"] + sums["unrealised_change"] + sums["income"] + sums.get("interest", ZERO)
                     + sums["disposal_change"] - sums["delivery_change"] - sums["fee_basis"])
        gain = exact_amount_v1(row["gain"]) if row.get("gain") is not None else None
        row["bridge"] = {**{name: _text(value) for name, value in sums.items()}, "rest": None if gain is None else _text(gain - explained)}
    return periods


def performance_v1(days: list[str], positions: list[dict[str, Any]], timeline: dict[str, list[tuple[str, int, dict[str, Any]]]],
                   events: dict[str, dict[str, Any]], ledger: list[dict[str, Any]], class_of: Callable[[str], str],
                   returns: Callable[..., dict[str, Any]], complete: list[bool]) -> dict[str, Any]:
    """Kennzahlen je Asset und je Klasse sowie die Tagesteile der Bruecke ueber alle Assets."""
    size = len(days)
    dailies = asset_daily_v1(days, positions, timeline, events, ledger)
    assets: dict[str, dict[str, Any]] = {}
    for asset, daily in dailies.items():
        values = [None if value is None else _text(value) for value in daily.value]
        flows = [None] + [_text(value) for value in daily.flow[1:]]
        active = active_range_v1(daily.value, daily.flow)
        computed = None if active is None else returns(days, values, flows, complete, spans=False, active=active)
        periods = [] if computed is None else computed["periods"]
        assets[asset] = {"periods": with_bridge_v1(periods, days, daily.parts), "realized_steps": daily.realized_steps,
                         "twr": None if computed is None else twr_window_v1(days, computed["twr_index"], active)}
    classes: dict[str, list[_Daily]] = defaultdict(list)
    for asset, daily in dailies.items():
        classes[class_of(asset)].append(daily)
    class_rows = {}
    for group, members in classes.items():
        value, basis, flow, neutral = _combine(members, size)
        parts = _sum_parts(members, size)
        active = active_range_v1(value, flow, neutral)
        computed = None if active is None else returns(days, [_text(item) for item in value], [None] + [_text(item) for item in flow[1:]],
                                                       complete, spans=False, neutral=neutral, active=active)
        periods = [] if computed is None else computed["periods"]
        realized, cumulative = [], ZERO
        for position in range(size):
            if parts["realized"][position]:
                cumulative += parts["realized"][position]
                realized.append({"day": days[position], "realized_cumulative": _text(cumulative)})
        class_rows[group] = {"basis": [_text(item) for item in basis], "realized_steps": realized,
                             "periods": with_bridge_v1(periods, days, parts),
                             "twr": None if computed is None else twr_window_v1(days, computed["twr_index"], active)}
    everything = list(dailies.values())
    return {"assets": assets, "classes": class_rows, "parts": _sum_parts(everything, size), "neutral": _combine(everything, size)[3],
            "dailies": dailies,
            "dividends": [sum((daily.dividends[position] for daily in dailies.values()), start=ZERO) for position in range(size)]}


def _interval_key(day: date, granularity: str) -> str:
    if granularity == "day":
        return day.isoformat()
    if granularity == "week":
        year, week, _ = day.isocalendar()
        return f"{year}-W{week:02d}"
    if granularity == "month":
        return f"{day.year}-{day.month:02d}"
    return f"{day.year}-Q{(day.month - 1) // 3 + 1}"


def intervals_v1(days: list[str], values: list[Any], flows: list[Any], index: list[Any], parts: dict[str, list[Any]],
                 interest: list[Any], xirr: Callable[..., Any], rate: Callable[[Any], Any],
                 windows: list[dict[str, Any]], neutral: list[Any] | None = None) -> dict[str, Any]:
    """Kennzahlen je Tag, Woche, Monat und Quartal fuer die Anlage, dazu je fester Zeitraum und Jahresspanne Durchschnitt,
    Median, bestes und schlechtestes Intervall und Anteil positiver Intervalle (Festlegung 20.10.2026)."""
    keys = [date.fromisoformat(day) for day in days]
    numbers = [None if value is None else float(exact_amount_v1(value)) for value in values]
    neutral = neutral or [ZERO] * len(days)
    flow_numbers = [(0.0 if flow is None else float(exact_amount_v1(flow))) + float(extra) for flow, extra in zip(flows, neutral)]
    levels = [float(exact_amount_v1(level)) for level in index]
    result: dict[str, Any] = {}
    for granularity in GRANULARITIES:
        groups: list[list[int]] = []
        last_key = None
        for position in range(1, len(days)):
            key = _interval_key(keys[position], granularity)
            if key != last_key:
                groups.append([]); last_key = key
            groups[-1].append(position)
        rows = []
        for members in groups:
            begin, stop = members[0] - 1, members[-1]
            if numbers[begin] is None or numbers[stop] is None:
                continue
            sums = {name: sum((parts[name][position] for position in members), start=ZERO) for name in BRIDGE_PARTS}
            income = sums["income"] + sum((interest[position] for position in members), start=ZERO)
            net_flow = sum((exact_amount_v1(flows[position]) for position in members if flows[position] is not None), start=ZERO)
            gain = exact_amount_v1(values[stop]) - exact_amount_v1(values[begin]) - net_flow - sum((neutral[position] for position in members), start=ZERO)
            twr = levels[stop] / levels[begin] - 1.0 if levels[begin] else None
            mwr = None
            if granularity != "day":
                span = float(max(1, (keys[stop] - keys[begin]).days))
                cash = [(0.0, -numbers[begin])] + [(float((keys[position] - keys[begin]).days), -flow_numbers[position])
                                                     for position in members if flow_numbers[position]] + [(span, numbers[stop])]
                mwr = xirr(cash, span)
            rows.append({"key": _interval_key(keys[stop], granularity), "start_day": days[begin], "end_day": days[stop],
                         "gain": _text(gain), "realized": _text(sums["realized"]), "unrealised_change": _text(sums["unrealised_change"]),
                         "income": _text(income), "net_flow": _text(net_flow), "twr": rate(twr), "mwr": rate(mwr)})
        summaries = []
        for window in windows:
            inside = [row for row in rows if row["start_day"] >= window["start_day"] and row["end_day"] <= window["end_day"]]
            metrics = {}
            for metric in INTERVAL_METRICS:
                values_in = [float(exact_amount_v1(row[metric])) for row in inside if row[metric] is not None]
                if not values_in:
                    continue
                as_text = rate if metric in ("twr", "mwr") else (lambda number: _text(exact_amount_v1(f"{number:.2f}")))
                metrics[metric] = {"mean": as_text(statistics.fmean(values_in)), "median": as_text(statistics.median(values_in)),
                                   "best": as_text(max(values_in)), "worst": as_text(min(values_in)),
                                   "positive_share": rate(sum(1 for number in values_in if number > 0) / len(values_in)), "count": len(values_in)}
            summaries.append({"window": window["period"], "count": len(inside), "metrics": metrics})
        result[granularity] = {"rows": rows, "summaries": summaries}
    return result


__all__ = ["BRIDGE_PARTS", "GRANULARITIES", "INTERVAL_METRICS", "asset_daily_v1", "bridge_gain_v1", "intervals_v1",
           "performance_v1", "realized_events_v1", "sale_lots_v1", "with_bridge_v1"]
