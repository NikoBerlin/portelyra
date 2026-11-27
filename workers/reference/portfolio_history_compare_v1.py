"""Vergleichsindizes (#482, #502) und eigene Asset-Gruppen (#483 Stufe 2) fuer die Tageshistorie.

Bestandteil eines Index: der EUR-Wert je Einheit eines Assets je Tag, wie ihn der Bewertungsstand fuehrt (Kurs ueber die
Wechselkurshistorie umgerechnet) - auch fuer ein Asset, das nicht gehalten wird, sobald es eine Kurszuordnung hat. Ein Tag
ohne Wert bleibt leer (None), nie 0.

Mit Ausschuettungen (#502, Festlegung 22.10.2026): Die eigenen Positionen rechnen mit Gesamtrendite (Dividenden brutto,
Rewards als neue Stuecke). Damit der Vergleich fair ist, rechnet jeder Bestandteil mit dem um Ausschuettungen bereinigten
Kurs der Kursquelle, der in der Kurshistorie neben dem Kurs liegt: Tagesschritt = Kursschritt mal Schritt des Faktors
(bereinigter Kurs / Kurs) derselben Notierung. Fehlt der Faktor an einem bewerteten Tag oder faellt er irgendwo (eine aus
verschiedenen Abrufen zusammengesetzte Bereinigung), rechnet der Bestandteil ganz mit dem Kurs ("price_only") - die
Anzeige sagt das, statt still falsch zu rechnen.

Ein Index aus mehreren Bestandteilen ist taeglich fest gewichtet (Entscheidung): Der Tagesschritt ist die
gewichtete Summe der Tagesschritte. Fehlt einem Bestandteil der Wert, fehlt der Index an diesem Tag; danach geht es vom
letzten vollstaendigen Tag weiter.

Je Zeitraum der Anlage die Rendite des Index ueber dieselbe Spanne; je Asset, Klasse und Gruppe ueber dieselben Tage mit
Bestand - der Index laeuft nur an den Tagen mit, an denen
Kapital arbeitet, und wird ueber dieselbe Zahl von Tagen aufs Jahr gerechnet.

Liest nur. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from fractions import Fraction
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping, Sequence

from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1

STATE_PATH = ("market-valuation-state-v1", "valuation-state.sqlite")
MARKET_PATH = ("daily-market-history-v1", "daily-market-history.sqlite")
VALUED_STATUSES = ("complete", "substituted")
# Faellt der Faktor bereinigter Kurs / Kurs um mehr als das, ist die Bereinigung nicht durchgehend (Rundung der Quelle bleibt darunter).
FACTOR_DROP_TOLERANCE = 0.001


def _text(value: Fraction | None) -> str | None:
    return None if value is None else amount_text_v1(value)


def _rate(value: float | None) -> str | None:
    return None if value is None else f"{value:.10f}"


def benchmark_series_v1(data_space: Path, asset_id: str, days: Sequence[str]) -> list[Fraction | None]:
    """Der EUR-Wert je Einheit des Vergleichsindex je Tag aus dem Bewertungsstand; None, wo der Stand keinen fuehrt."""
    from workers.reference.portfolio_snapshot_freshness_v1 import current_symbols_v1, effective_scope_refs_v1, scope_order_v1
    from workers.reference.portfolio_snapshot_projection_v1 import _exact_unit
    path = Path(data_space).joinpath(*STATE_PATH)
    if not path.is_file() or path.is_symlink():
        return [None] * len(days)
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        scopes = [dict(row) for row in connection.execute(
            "SELECT s.scope_ref,s.asset_id,s.provider_symbol,w.valued_from_date,w.valued_through_date "
            "FROM valuation_scope s JOIN valuation_watermark w USING(scope_ref) WHERE s.asset_id=?", (asset_id,))]
        if not scopes:
            return [None] * len(days)
        marks = ",".join("?" for _ in scopes)
        rows = connection.execute(
            f"SELECT scope_ref,trading_date,valuation_status,target_decimal,target_numerator,target_denominator FROM valuation_day "
            f"WHERE scope_ref IN ({marks}) AND trading_date BETWEEN ? AND ?", (*[scope["scope_ref"] for scope in scopes], days[0], days[-1])).fetchall()
    finally:
        connection.close()
    by_day: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_day.setdefault(row["trading_date"], {})[row["scope_ref"]] = dict(row)
    order = scope_order_v1(scopes, current_symbols_v1(Path(data_space)))
    result: list[Fraction | None] = []
    for day in days:
        entries = by_day.get(day)
        if not entries:
            result.append(None)
            continue
        scope = effective_scope_refs_v1(order, day).get(asset_id)
        row = entries.get(scope) if scope is not None else None
        result.append(_exact_unit(row) if row is not None and row["valuation_status"] in VALUED_STATUSES else None)
    return result


def _dividend_factors(data_space: Path, listing_refs: Sequence[str]) -> tuple[dict[str, dict[str, float]], set[str]]:
    """Je Notierung und Handelstag der Faktor bereinigter Kurs / Kurs der Kursquelle und die Notierungen, deren Faktor
    irgendwo faellt. Ohne Kurshistorie: nichts."""
    path = Path(data_space).joinpath(*MARKET_PATH)
    refs = sorted({ref for ref in listing_refs if ref})
    if not refs or not path.is_file() or path.is_symlink():
        return {}, set()
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        marks = ",".join("?" for _ in refs)
        rows = connection.execute(
            "SELECT b.listing_ref, e.trading_date, r.close_decimal, r.adjusted_close_decimal FROM current_market_day_revision r "
            "JOIN market_day_entity e USING(market_day_id) JOIN market_listing_binding b ON b.listing_id = e.listing_id "
            f"WHERE b.listing_ref IN ({marks}) AND r.day_status = 'observed' AND r.close_decimal IS NOT NULL "
            "AND r.adjusted_close_decimal IS NOT NULL ORDER BY b.listing_ref, e.trading_date", refs).fetchall()
    except sqlite3.Error:
        return {}, set()
    finally:
        connection.close()
    factors: dict[str, dict[str, float]] = defaultdict(dict)
    broken: set[str] = set()
    last: dict[str, float] = {}
    for ref, day, close, adjusted in rows:
        try:
            close_value, adjusted_value = float(exact_amount_v1(close)), float(exact_amount_v1(adjusted))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if close_value <= 0 or adjusted_value <= 0:
            continue
        factor = adjusted_value / close_value
        if ref in last and factor < last[ref] * (1.0 - FACTOR_DROP_TOLERANCE):
            broken.add(ref)
        last[ref] = factor
        factors[ref][day] = factor
    return dict(factors), broken


def benchmark_component_v1(data_space: Path, asset_id: str, days: Sequence[str]) -> dict[str, Any]:
    """Ein Bestandteil eines Vergleichsindex je Tag: 'levels' mit Ausschuettungen ('total_return') oder nur der Kurs
    ('price_only'); 'no_prices', wenn der Stand keinen Wert fuehrt. Nur die Verhaeltnisse der Werte zaehlen."""
    from workers.reference.portfolio_snapshot_freshness_v1 import current_symbols_v1, effective_scope_refs_v1, scope_order_v1
    from workers.reference.portfolio_snapshot_projection_v1 import _exact_unit
    empty = {"levels": [None] * len(days), "basis": "no_prices"}
    path = Path(data_space).joinpath(*STATE_PATH)
    if not days or not path.is_file() or path.is_symlink():
        return empty
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        scopes = [dict(row) for row in connection.execute(
            "SELECT s.scope_ref,s.asset_id,s.listing_ref,s.provider_symbol,w.valued_from_date,w.valued_through_date "
            "FROM valuation_scope s JOIN valuation_watermark w USING(scope_ref) WHERE s.asset_id=?", (asset_id,))]
        if not scopes:
            return empty
        marks = ",".join("?" for _ in scopes)
        rows = connection.execute(
            f"SELECT scope_ref,trading_date,valuation_status,target_decimal,target_numerator,target_denominator,price_source_date,"
            f"price_source_kind FROM valuation_day WHERE scope_ref IN ({marks}) AND trading_date BETWEEN ? AND ?",
            (*[scope["scope_ref"] for scope in scopes], days[0], days[-1])).fetchall()
    finally:
        connection.close()
    by_day: dict[str, dict[str, Any]] = {}
    for row in rows:
        by_day.setdefault(row["trading_date"], {})[row["scope_ref"]] = dict(row)
    listing_of = {scope["scope_ref"]: scope["listing_ref"] for scope in scopes}
    order = scope_order_v1(scopes, current_symbols_v1(Path(data_space)))
    factors, broken = _dividend_factors(Path(data_space), list(listing_of.values()))
    prices: list[Fraction | None] = []
    steps: list[tuple[str | None, float | None] | None] = []
    for day in days:
        entries = by_day.get(day) or {}
        scope = effective_scope_refs_v1(order, day).get(asset_id)
        row = entries.get(scope) if scope is not None else None
        price = _exact_unit(row) if row is not None and row["valuation_status"] in VALUED_STATUSES else None
        if price is None or price <= 0:
            prices.append(None); steps.append(None)
            continue
        listing = listing_of.get(scope)
        # Ein splitbereinigt bewerteter Tag nimmt den bereinigten Kurs schon als Kurs: Faktor 1.
        factor = 1.0 if row.get("price_source_kind") == "split_adjusted_close" else (factors.get(listing) or {}).get(row.get("price_source_date") or day)
        prices.append(price); steps.append((listing, factor))
    if not any(price is not None for price in prices):
        return empty
    total = all(step is None or (step[1] is not None and step[0] not in broken) for step in steps)
    if not total:
        return {"levels": [None if price is None else float(price) for price in prices], "basis": "price_only"}
    levels: list[float | None] = []
    level, last_price, last_step = None, None, None
    for price, step in zip(prices, steps):
        if price is None:
            levels.append(None)
            continue
        if level is None:
            level = float(price)
        else:
            ratio = float(price / last_price)
            # Wechselt die Notierung, zaehlt an diesem Tag nur der Kurs; die Faktoren zweier Notierungen sind nicht vergleichbar.
            if step[0] == last_step[0]:
                ratio *= step[1] / last_step[1]
            level *= ratio
        last_price, last_step = price, step
        levels.append(level)
    return {"levels": levels, "basis": "total_return"}


def composite_levels_v1(series: Sequence[Sequence[float | None]], weights: Sequence[float]) -> list[float | None]:
    """Taeglich fest gewichteter Index: Tagesschritt = gewichtete Summe der Schritte seit dem letzten vollstaendigen Tag.
    Fehlt einem Bestandteil der Wert, fehlt der Index an diesem Tag. Ein Bestandteil allein ergibt sein eigenes Verhaeltnis."""
    size = len(series[0]) if series else 0
    result: list[float | None] = []
    level, last = None, None
    for position in range(size):
        values = [item[position] for item in series]
        if any(value is None or value <= 0 for value in values):
            result.append(None)
            continue
        if level is None:
            level = 1.0
        else:
            level *= sum(weight * value / before for weight, value, before in zip(weights, values, last))
        last = values
        result.append(level)
    return result


def _carried(prices: Sequence[Fraction | None], position: int) -> Fraction | None:
    """Der letzte bekannte Wert bis zum Tag - fuer Wochenende und Feiertag."""
    for back in range(position, max(-1, position - 7), -1):
        if prices[back] is not None:
            return prices[back]
    return None


def benchmark_periods_v1(periods: list[dict[str, Any]], days: Sequence[str], prices: Sequence[Any]) -> None:
    """Je Zeitraum der Anlage die Rendite des Index ueber dieselbe Spanne; p. a. ab 365 Tagen. Fehlt der Wert am Anfang oder
    Ende, bleibt sie leer; Tage ohne Wert dazwischen werden gezaehlt. Haengt je Index einen Eintrag an 'benchmarks' an - in
    der Reihenfolge der Indizes."""
    index_of = {day: position for position, day in enumerate(days)}
    gaps, count = [], 0
    for position in range(len(days)):
        count += _carried(prices, position) is None
        gaps.append(count)
    for row in periods:
        begin, stop = index_of[row["start_day"]], index_of[row["end_day"]]
        start, end = _carried(prices, begin), _carried(prices, stop)
        result = None if start is None or end is None or start == 0 else float(end / start) - 1.0
        span = row.get("day_span") or 0
        row.setdefault("benchmarks", []).append({
            "return": _rate(result),
            "annualised": _rate((1.0 + result) ** (365.0 / span) - 1.0) if result is not None and span >= 365 and result > -1.0 else None,
            "missing_days": gaps[stop] - (gaps[begin - 1] if begin > 0 else 0)})


def working_days_v1(values: Sequence[Any], flows: Sequence[Any]) -> list[bool]:
    """Die Tage, an denen Kapital arbeitet - dieselbe Regel wie der TWR-Index."""
    working = [False] * len(values)
    for position in range(1, len(values)):
        before, after, flow = values[position - 1], values[position], float(flows[position])
        if before is None or after is None:
            continue
        base = float(before) + flow if flow >= 0 else float(before)
        working[position] = base > 1.0
    return working


def daily_steps_v1(prices: Sequence[Any]) -> list[float | None]:
    """Je Tag das Verhaeltnis zum Vortag (mit fortgeschriebenem Wert); None, wo einer fehlt."""
    steps: list[float | None] = [None]
    for position in range(1, len(prices)):
        today, yesterday = _carried(prices, position), _carried(prices, position - 1)
        steps.append(None if today is None or yesterday is None or yesterday == 0 else float(today / yesterday))
    return steps


def held_benchmark_rows_v1(periods: list[dict[str, Any]], days: Sequence[str], steps: Sequence[float | None], working: Sequence[bool]) -> None:
    """Je Zeitraum die Rendite des Index nur an den Tagen mit Bestand, p. a. ueber dieselben Tage mit Bestand. Vorab je Tag
    aufsummiert, damit jeder Zeitraum nur noch Anfang und Ende liest."""
    product, held, missing = [1.0], [0], [0]
    for position in range(1, len(days)):
        factor, works = steps[position], working[position]
        product.append(product[-1] * factor if works and factor is not None else product[-1])
        held.append(held[-1] + works)
        missing.append(missing[-1] + (works and factor is None))
    index_of = {day: position for position, day in enumerate(days)}
    for row in periods:
        begin, stop = index_of[row["start_day"]], index_of[row["end_day"]]
        count, gaps = held[stop] - held[begin], missing[stop] - missing[begin]
        level = product[stop] / product[begin]
        result = None if count == 0 or gaps == count else level - 1.0
        row.setdefault("benchmarks", []).append({
            "return": _rate(result),
            "annualised": _rate(level ** (365.0 / count) - 1.0) if result is not None and count >= 365 and level > 0 else None,
            "missing_days": gaps})


def held_benchmark_periods_v1(periods: list[dict[str, Any]], days: Sequence[str], prices: Sequence[Any],
                              values: Sequence[Fraction | None], flows: Sequence[Fraction]) -> None:
    """Je Zeitraum eines Assets die Rendite des Index nur an den Tagen mit Bestand (dieselbe Regel wie der TWR-Index: ein Tag
    zaehlt, wenn Kapital arbeitet), p. a. ueber dieselben Tage mit Bestand."""
    held_benchmark_rows_v1(periods, days, daily_steps_v1(prices), working_days_v1(values, flows))


def group_performance_v1(days: Sequence[str], dailies: Mapping[str, Any], members: Sequence[str], returns: Callable[..., dict[str, Any]],
                         complete: Sequence[bool]) -> dict[str, Any]:
    """Kennzahlen einer Gruppe von Assets - dieselbe Rechnung wie fuer eine Assetklasse (Wert, Einstand, Zeitraeume mit
    Bruecke, realisiert)."""
    from workers.reference.portfolio_history_performance_v1 import ZERO, _combine, _sum_parts, active_range_v1, with_bridge_v1
    size = len(days)
    chosen = [dailies[asset] for asset in members if asset in dailies]
    if not chosen:
        return {"value": [None] * size, "basis": ["0"] * size, "realized_steps": [], "periods": [], "flow": [ZERO] * size, "neutral": [ZERO] * size,
                "twr": None}
    value, basis, flow, neutral = _combine(chosen, size)
    parts = _sum_parts(chosen, size)
    active = active_range_v1(value, flow, neutral)
    computed = None if active is None else returns(days, [_text(item) for item in value], [None] + [_text(item) for item in flow[1:]],
                                                   list(complete), spans=False, neutral=neutral, active=active)
    periods = [] if computed is None else computed["periods"]
    realized, cumulative = [], ZERO
    for position in range(size):
        if parts["realized"][position]:
            cumulative += parts["realized"][position]
            realized.append({"day": days[position], "realized_cumulative": _text(cumulative)})
    return {"value": value, "basis": [_text(item) for item in basis], "realized_steps": realized,
            "periods": with_bridge_v1(periods, days, parts), "flow": flow, "neutral": neutral,
            "twr": None if computed is None else twr_window_v1(days, computed["twr_index"], active)}


def twr_window_v1(days: Sequence[str], index: Sequence[Any], active: tuple[int, int] | None) -> dict[str, Any] | None:
    """Der TWR-Index je Tag fuer das Vergleichsbild (#502), nur ueber die Haltedauer: vom Tag vor dem ersten Bestand bis zum
    letzten Tag mit Bestand oder Buchung. Davor und danach gibt es nichts zu vergleichen."""
    if active is None:
        return None
    begin, stop = max(active[0] - 1, 0), active[1]
    return {"first_day": days[begin], "index": list(index[begin:stop + 1])}


__all__ = ["benchmark_component_v1", "benchmark_periods_v1", "benchmark_series_v1", "composite_levels_v1", "daily_steps_v1",
           "group_performance_v1", "held_benchmark_periods_v1", "held_benchmark_rows_v1", "twr_window_v1", "working_days_v1"]
