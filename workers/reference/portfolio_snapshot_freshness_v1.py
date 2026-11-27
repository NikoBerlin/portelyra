"""Frische je Ebene fuer den Portfolio-Snapshot. Nur lesend.

Ein Sammelurteil verdeckt, woran es liegt. Dieser Leser sagt je Ebene, was ihr
Stand ist, und mischt nichts: Marktkurse, Wechselkurse, FIFO und Bestand werden
getrennt beurteilt, mit je eigener Begruendung (#373, 26.09.2026).

Die Frische der Marktseite haengt am Bewertungsstand, nicht an einem Abdruck
ueber die gesamten Kurs- und FX-Speicher. Der alte Sammelabdruck entwertete mit
jedem Abruf fuer irgendein Asset den Lauf jedes anderen - so waren alle abgeschlossenen Laeufe dauerhaft 'stale', ein erreichbarer
Zustand "alles aktuell" existierte nicht.

Kein Provider, keine Berechnung, kein Schreiben.
"""
from __future__ import annotations

import bisect
import json
import sqlite3
from fractions import Fraction
from pathlib import Path
from typing import Any

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _context as _product_context,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.desktop_cash_coverage_v1 import (
    DesktopCashCoverageV1Error,
    read_desktop_cash_coverage_view_v1,
)
from migrations.reference.asset_valuation_facts_v1 import OWNER_CHOICE_METHODS
from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1
from workers.reference.asset_activity_realized_state_v2 import (
    AssetActivityRealizedStateV2Error,
    read_asset_activity_realized_state_v2,
)

STATE_AREA = "market-valuation-state-v1"
STATE_NAME = "valuation-state.sqlite"

# Die Statussemantik dieses Issues, bewusst getrennt gehalten.
STATUSES = ("not_requested", "source_gap", "stale_fifo", "stale_market", "valuation_pending", "complete")


class PortfolioSnapshotFreshnessV1Error(RuntimeError):
    CODES = frozenset({
        "portfolio_snapshot_freshness_context_invalid",
        "portfolio_snapshot_freshness_evidence_invalid",
        "portfolio_snapshot_freshness_input_invalid",
        "portfolio_snapshot_freshness_boundary_failed",
    })

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("portfolio_snapshot_freshness_error_code_unregistered")
        self.code = code
        super().__init__(code)


def portfolio_snapshot_freshness_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(PortfolioSnapshotFreshnessV1Error.CODES))


def _abort(code: str) -> None:
    raise PortfolioSnapshotFreshnessV1Error(code)


def _runtime(value: Any) -> DesktopProductAssetActivityContextV1:
    try:
        return _product_context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("portfolio_snapshot_freshness_context_invalid")


def _date(value: Any) -> str:
    from datetime import date
    if not isinstance(value, str):
        _abort("portfolio_snapshot_freshness_input_invalid")
    try:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        _abort("portfolio_snapshot_freshness_input_invalid")
    return value


# Nicht jede Ebene traegt den Marktwert. Cash und die Eigentuemerwahl gehoeren
# in die Auskunft, aber sie duerfen sie nicht sperren; und "nichts zu bewerten"
# ist erfuellt, nicht offen - sonst koennte ein Portfolio ohne Fremdwaehrung nie
# vollstaendig sein (gefunden im Vertragstest, 26.09.2026).
BLOCKING_LEVELS = frozenset({"activity", "fifo_basis", "market_history", "fx_history"})
SATISFIED_WITHOUT_WORK = frozenset({"nothing_to_value"})


def _level(code: str, status: str, reason: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    if status not in STATUSES:
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    blocking = code in BLOCKING_LEVELS
    satisfied = status == "complete" or (status == "not_requested" and reason in SATISFIED_WITHOUT_WORK)
    row = {"level_code": code, "status": status, "reason_code": reason,
           "blocking": blocking, "satisfied": satisfied}
    if detail is not None:
        row["detail"] = detail
    return row


def _open(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _listing_requests(data_space: Path, listing_ref: str) -> str:
    # Derselbe Abdruck, den der Bewertungsstand beim Fortschreiben verbraucht
    # hat. Weicht er ab, wurde fuer diese Notierung seither etwas abgerufen.
    from migrations.reference.desktop_market_valuation_v1 import _listing_requests as source
    try:
        return source(data_space, listing_ref)
    except Exception:
        _abort("portfolio_snapshot_freshness_evidence_invalid")


# Zeitraeume ohne abgestimmten Saldo und die Zahl der Anfangsbuchungen, mit der
# sich ihr Saldo ableiten laesst: nur Bewegungen (von null) oder ein genannter,
# nicht abgestimmter Anfangsbestand.
_DERIVED_OPENINGS = {"partial_delta_only": 0, "indicative_balance": 1}
# Was davon in der Summe steht, ohne dass ein Auszug es bestaetigt.
DERIVED_CASH_STATUSES = frozenset({"derived_at_as_of", "derived_before_as_of"})


def cash_as_of_v1(cash: dict[str, Any], as_of_date: str) -> dict[str, Any]:
    """Der Cash-Bestand je Konto am Stichtag - soweit er belegt ist.

    Ein abgestimmtes Konto traegt einen Anfangssaldo und seine Bewegungen; der
    Saldo eines Tages ist Anfang plus Einzahlungen minus Auszahlungen bis zu
    diesem Tag. Belegt ist er bis zum Tag der Abstimmung ('as_of_date' des
    Zeitraums). Liegt der Stichtag danach, gilt der Saldo vom Abstimmungstag -
    mit seinem Datum, damit niemand ihn fuer den Stand des Stichtags haelt.

    Ein Konto, das nur Bewegungen fuehrt, hat keinen belegten Saldo. Sein Saldo
    wird abgeleitet: die Summe seiner Bewegungen - bei einem vom Eigentuemer
    genannten, aber nicht abgestimmten Anfangsbestand von diesem aus, sonst von
    null. Er zaehlt in die Summe und heisst 'derived_*', damit ihn niemand fuer
    einen Auszugssaldo haelt: berechnet und nicht durch den Auszug selbst
    validiert. Die Annahme dahinter - vor der ersten Bewegung war nichts auf dem
    Konto - prueft niemand; lag dort schon Geld, ist der Saldo um genau diesen
    Betrag zu niedrig. Deshalb traegt die Zeile 'derived_from_date': den Tag, ab
    dem summiert ist. Ob das die Kontoeroeffnung war oder nur der Beginn eines
    Exports, weiss allein der Eigentuemer. Widerlegt der Bestand die Annahme
    selbst, weil die Summe an einem Tagesende unter null faellt, gibt es keinen
    Saldo ('movements_sum_negative'): fehlendes Cash ist niemals null (#373).

    Anfang plus Bewegungen ergibt bei abgestimmten Konten den ausgewiesenen Saldo, und die
    Bewegungssumme stimmt. Die Cash-Konten fuehren keine
    Asset-Buchungen; aus dem Buchungsbestand laesst sich deshalb nicht ablesen,
    ob ein Konto vor seiner ersten Cash-Bewegung schon bestand.
    """
    if not isinstance(cash, dict) or cash.get("status") != "available":
        return {"status": "absent", "accounts": []}
    moves: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for event in cash.get("cash_history") or []:
        moves.setdefault((event["account_label"], event["cash_asset_label"]), []).append(event)
    periods: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for period in cash.get("periods") or []:
        periods.setdefault((period["account_label"], period["cash_asset_label"]), []).append(period)
    sign = {"deposit": 1, "withdrawal": -1}
    accounts = []
    for key in sorted(periods):
        rows = sorted(periods[key], key=lambda item: str(item.get("effective_from") or ""))
        row = {"account_label": key[0], "cash_asset_label": key[1], "currency": rows[0]["currency"],
               "balance_decimal": None, "balance_date": None, "in_total": False,
               # Nur beim abgeleiteten Saldo: der Tag, ab dem die Bewegungen
               # summiert sind. Davor gilt das Konto als leer - das ist die
               # Annahme, und an diesem Datum laesst sie sich pruefen.
               "derived_from_date": None}
        period = rows[0]
        events = moves.get(key, [])
        ambiguous = False
        if len(rows) > 1:
            # Mehrere Zeitraeume je Konto (#467): Auszuege vor einer bestehenden Abdeckung bilden einen eigenen, je bewiesenen
            # Zeitraum. Es gilt der Zeitraum, in dem der Stichtag liegt - sein Anfangssaldo und seine Bewegungen. In einer
            # Luecke danach gilt sein abgestimmter Saldo mit Datum, wie nach dem letzten Auszug (Festlegung 20.10.2026, #479).
            # Mehrdeutig bleibt nur, was keinen Beginn hat oder sich ueberlappt: Dann ist nicht entschieden, welcher
            # Anfangssaldo welche Bewegungen traegt.
            starts = [item.get("effective_from") for item in rows]
            ends = [item.get("as_of_date") for item in rows]
            ambiguous = (any(not isinstance(value, str) for value in starts + ends)
                         or any(ends[index][:10] >= starts[index + 1][:10] for index in range(len(rows) - 1)))
            if not ambiguous:
                chosen = max((index for index, value in enumerate(starts) if value[:10] <= as_of_date), default=0)
                period = rows[chosen]
                until = starts[chosen + 1][:10] if chosen + 1 < len(rows) else None
                events = [event for event in events if period["effective_from"][:10] <= event["local_date"]
                          and (until is None or event["local_date"] < until)]
        opening = [event for event in events if event["event_type"] == "opening_balance"]
        plain = all(event["event_type"] in ("deposit", "withdrawal", "opening_balance") for event in events)
        if ambiguous:
            row["balance_status"] = "periods_ambiguous"
        elif not isinstance(period.get("effective_from"), str) or as_of_date < period["effective_from"][:10]:
            row["balance_status"] = "not_covered_yet"
        elif plain and isinstance(period.get("as_of_date"), str) and len(opening) == _DERIVED_OPENINGS.get(period.get("balance_status")):
            # Belegt sind die Bewegungen bis zur letzten gebuchten; liegt der
            # Stichtag danach, traegt der Saldo deren Datum - wie beim
            # abgestimmten Konto.
            through = min(as_of_date, period["as_of_date"])
            per_day: dict[str, Fraction] = {}
            for event in events:
                if event["event_type"] in sign and event["local_date"] <= through:
                    per_day[event["local_date"]] = per_day.get(event["local_date"], Fraction(0)) \
                        + sign[event["event_type"]] * exact_amount_v1(event["amount_decimal"])
            total = exact_amount_v1(opening[0]["amount_decimal"]) if opening else Fraction(0)
            negative = total < 0
            for day in sorted(per_day):
                total = total + per_day[day]
                negative = negative or total < 0
            if negative:
                row["balance_status"] = "movements_sum_negative"
            else:
                row.update(balance_decimal=amount_text_v1(total), balance_date=through, in_total=True,
                           derived_from_date=period["effective_from"][:10],
                           balance_status="derived_at_as_of" if through == as_of_date else "derived_before_as_of")
        elif period.get("balance_status") != "complete_reconciled" or period.get("computed_balance_decimal") is None \
                or len(opening) != 1 or not plain:
            row["balance_status"] = "movements_only"
        elif as_of_date >= period["as_of_date"]:
            row.update(balance_decimal=period["computed_balance_decimal"], balance_date=period["as_of_date"], in_total=True,
                       balance_status="reconciled_at_as_of" if as_of_date == period["as_of_date"] else "reconciled_before_as_of")
        else:
            total = exact_amount_v1(opening[0]["amount_decimal"])
            for event in events:
                if event["event_type"] in sign and event["local_date"] <= as_of_date:
                    total = total + sign[event["event_type"]] * exact_amount_v1(event["amount_decimal"])
            row.update(balance_decimal=amount_text_v1(total), balance_date=as_of_date, in_total=True,
                       balance_status="reconciled_at_as_of")
        accounts.append(row)
    return {"status": "available", "accounts": accounts}


def valuation_methods_v1(data_space: Path, context: DesktopProductAssetActivityContextV1) -> dict[str, str]:
    return _valuation_methods(data_space, context)


class _WithTimeline(dict):
    """Ein dict, das die Bewertungs-Zeitleiste des Datenraums mitfuehrt (rc.393): So erreichen Bereichs- und Methodenwahl sie, ohne dass
    jeder Aufrufer sie selbst laden muss. Ohne Zeitleiste ist ``timeline`` leer und alles wie bisher."""
    timeline: Any = None


def _with_timeline(value: dict, data_space: Path | None) -> "_WithTimeline":
    result = _WithTimeline(value)
    result.timeline = _timeline_module().timeline_v1(data_space) if data_space is not None else None
    return result


def _timeline_module():
    from migrations.reference import asset_valuation_timeline_v1 as timeline
    return timeline


def methods_on_day_v1(methods: dict[str, str] | None, day: str) -> dict[str, str]:
    """Die Bewertungsart je Asset an einem Tag: mit Zeitleiste deren Abschnitt, sonst die Art aus den Stammdaten."""
    methods = methods or {}
    return _timeline_module().methods_on_day_v1(methods, day, getattr(methods, "timeline", None))


def _valuation_methods(data_space: Path, context: DesktopProductAssetActivityContextV1) -> dict[str, str]:
    """Wie ein Asset bewertet werden soll - laut Stammdaten.

    Wer 'manual' gewaehlt hat, will kein Marktergebnis. Ein solches Asset ohne
    Bewertungsbereich ist kein Quellmangel, sondern eine Entscheidung, und darf
    die Marktebene nicht in 'source_gap' ziehen (#373, 26.09.2026). Dasselbe gilt
    fuer 'transaction_only': Der Eigentuemer fuehrt das Asset bewusst ohne Wert.
    Bis 11.10.2026 zaehlte es als Luecke und machte jeden Snapshot unvollstaendig.
    """
    try:
        binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
        if binding.get("status") != "available" or not binding.get("ledger_path"):
            return {}
        connection = sqlite3.connect("file:" + str(binding["ledger_path"]) + "?mode=ro", uri=True)
    except Exception:
        return {}
    try:
        return _with_timeline({row[0]: row[1] for row in connection.execute(
            "SELECT asset_id, valuation_method FROM current_asset_revision")}, data_space)
    except sqlite3.Error:
        return {}
    finally:
        connection.close()


def scope_order_v1(scopes: list[dict[str, Any]], current_symbols: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    """Je Asset seine Bewertungsbereiche in der Reihenfolge, in der sie einen Tag tragen (#474).

    Ein Bereich ist ein Asset an einer Notierung. Wechselt die Anbieterzuordnung auf ein anderes Symbol, entsteht ein
    zweiter Bereich; der alte bleibt stehen und wird nicht mehr fortgeschrieben. Bis rc.281 beurteilte das Frische-Urteil
    jeden Bereich, und so galt ab dem Ende des alten Bereichs jeder Tag als unbewertet. Den
    Wert nahm die Rechnung von dem Bereich, den die Abfrage zuletzt lieferte.
    Vorne steht deshalb der Bereich der aktuellen Zuordnung (gleiches Anbietersymbol), danach die uebrigen mit dem
    spaetesten Ende zuerst. Ein Asset mit einem Bereich rechnet wie bisher."""
    order: dict[str, list[dict[str, Any]]] = _WithTimeline()
    order.timeline = getattr(current_symbols, "timeline", None)
    for scope in scopes:
        order.setdefault(scope["asset_id"], []).append(scope)
    for asset, rows in order.items():
        if len(rows) > 1:
            current = current_symbols.get(asset)
            rows.sort(key=lambda row: (row["provider_symbol"] != current, _negated_day(row["valued_through_date"]), row["scope_ref"]))
    return order


def _negated_day(value: str | None) -> tuple[int, ...]:
    # Spaetestes Ende zuerst; ohne Ende ganz hinten.
    if not value:
        return (1,)
    return (0, *(-int(part) for part in value.split("-")))


def effective_scope_refs_v1(order: dict[str, list[dict[str, Any]]], day: str, timeline: Any = None) -> dict[str, str | None]:
    """Je Asset der eine Bereich, der den Tag traegt: der erste in der Reihenfolge, dessen Bewertungsfenster den Tag
    enthaelt - sonst der vorderste, an dem der Tag dann offen ist (#474).

    Mit Bewertungs-Zeitleiste (rc.393) entscheidet allein ihr Abschnitt: ist er keine Marktbewertung, traegt kein Bereich den Tag
    (``None``); sonst nur Bereiche mit dem Symbol des Abschnitts, ohne Rueckfall auf eine andere Reihe."""
    timeline = timeline if timeline is not None else getattr(order, "timeline", None)
    chosen: dict[str, str | None] = {}
    for asset, rows in order.items():
        if timeline and timeline.has(asset):
            segment = timeline.segment_on(asset, day)
            if segment is None or segment.method != "external_market":
                chosen[asset] = None
                continue
            rows = [row for row in rows if row["provider_symbol"] == segment.provider_symbol]
            if not rows:
                chosen[asset] = None
                continue
        if len(rows) == 1:
            chosen[asset] = rows[0]["scope_ref"]
            continue
        inside = next((row for row in rows if row["valued_from_date"] and row["valued_through_date"]
                       and row["valued_from_date"] <= day <= row["valued_through_date"]), None)
        chosen[asset] = (inside or rows[0])["scope_ref"]
    return chosen


def current_symbols_v1(data_space: Path) -> dict[str, str]:
    """Je Asset das Anbietersymbol seiner Kurshistorien-Zuordnung. Gibt es mehrere (etwa zwei Anbieter, #495), gilt die eine
    aktive; sind es mehrere aktive mit verschiedenen Symbolen, entscheidet das Ende (scope_order_v1)."""
    path = Path(data_space) / "canonical.sqlite"
    if not path.is_file():
        return _with_timeline({}, Path(data_space))
    try:
        connection = sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT asset_id, provider_symbol, enabled FROM provider_mapping WHERE capability='daily_history'").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return {}
    found: dict[str, set[str]] = {}
    enabled: dict[str, set[str]] = {}
    for asset, symbol, active in rows:
        found.setdefault(asset, set()).add(symbol)
        if active:
            enabled.setdefault(asset, set()).add(symbol)
    result: dict[str, str] = {}
    for asset, symbols in found.items():
        if len(symbols) == 1:
            result[asset] = next(iter(symbols))
        elif len(enabled.get(asset, ())) == 1:
            result[asset] = next(iter(enabled[asset]))
    # Mit Zeitleiste (rc.393) ist das aktuelle Symbol das des laufenden Marktabschnitts.
    result = _with_timeline(result, Path(data_space))
    timeline = result.timeline
    if timeline:
        for asset in timeline.assets():
            segment = timeline.current(asset)
            if segment is not None and segment.method == "external_market":
                result[asset] = segment.provider_symbol
    return result


def scope_windows_v1(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """Alle Bewertungsbereiche mit ihrem Bewertungsfenster (Wasserstand) - Grundlage fuer die Regel aus #474."""
    cursor = connection.execute(
        "SELECT s.scope_ref, s.asset_id, s.provider_symbol, w.valued_from_date, w.valued_through_date "
        "FROM valuation_scope s LEFT JOIN valuation_watermark w USING(scope_ref) ORDER BY s.scope_ref")
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def preferred_scope_refs_v1(scopes: list[dict[str, Any]], current_symbols: dict[str, str]) -> dict[str, str]:
    """Je Asset der Bereich, der heute gilt (#474): der der aktuellen Zuordnung, sonst der mit dem spaetesten Ende. Fuer
    Abrufe ohne Tag (Kurs der laufenden Sitzung): Ein alter Bereich nach einem Symbol- oder Anbieterwechsel wird nicht mehr
    abgefragt (bis rc.384 holte die Momentaufnahme beide Symbole, und welcher Wert galt, war Zufall).
    Mit Zeitleiste (rc.393) gilt ihr laufender Abschnitt: keine Marktbewertung - kein Bereich; sonst nur das Symbol des Abschnitts."""
    order = scope_order_v1([dict(row) for row in scopes], current_symbols)
    timeline = getattr(order, "timeline", None)
    result: dict[str, str] = {}
    for asset, rows in order.items():
        if timeline and timeline.has(asset):
            segment = timeline.current(asset)
            rows = [] if segment is None or segment.method != "external_market" else [row for row in rows if row["provider_symbol"] == segment.provider_symbol]
        if rows:
            result[asset] = rows[0]["scope_ref"]
    return result


def choose_day_rows_v1(rows: list[dict[str, Any]], scopes: list[dict[str, Any]], current_symbols: dict[str, str], day: str) -> dict[str, dict[str, Any]]:
    """Je Asset die eine Zeile eines Tages nach der Regel aus #474, wenn mehrere Bereiche den Tag bewerten. ``rows`` tragen
    ``asset_id`` und ``scope_ref``. Fehlt der gewaehlte Bereich unter den Zeilen, gilt der vorderste vorhandene."""
    present: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows:
        present.setdefault(row["asset_id"], {})[row["scope_ref"]] = row
    order = scope_order_v1([dict(scope) for scope in scopes if scope["asset_id"] in present], current_symbols)
    timeline = getattr(order, "timeline", None)
    chosen: dict[str, dict[str, Any]] = {}
    for asset, by_scope in present.items():
        if timeline and timeline.has(asset):
            # Zeitleiste (rc.393): nur der Bereich ihres Abschnitts; sonst traegt keine Zeile den Tag (das Asset entfaellt).
            effective = effective_scope_refs_v1({asset: order.get(asset, [])}, day, timeline).get(asset)
            if effective in by_scope:
                chosen[asset] = by_scope[effective]
            continue
        if len(by_scope) == 1:
            chosen[asset] = next(iter(by_scope.values()))
            continue
        ranked = order.get(asset, [])
        effective = effective_scope_refs_v1({asset: ranked}, day).get(asset) if ranked else None
        if effective in by_scope:
            chosen[asset] = by_scope[effective]
            continue
        first = next((scope["scope_ref"] for scope in ranked if scope["scope_ref"] in by_scope), None)
        chosen[asset] = by_scope[first] if first is not None else by_scope[sorted(by_scope)[0]]
    return chosen


def market_inputs_v1(data_space: Path, dates: set[str] | None = None) -> dict[str, Any] | None:
    """Was die Markt- und Wechselkurs-Ebene liest - einmal geladen, fuer einen Stichtag oder (dates=None) fuer alle Tage
    des Bewertungsstands. Die Tageshistorie (#473) beurteilt so jeden Tag mit derselben Regel wie der Snapshot."""
    path = data_space / STATE_AREA / STATE_NAME
    if not path.is_file():
        return None
    try:
        connection = _open(path)
    except sqlite3.Error:
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    try:
        scopes = [dict(row) for row in connection.execute(
            "SELECT s.scope_ref,s.asset_id,s.listing_ref,s.provider_symbol,s.pair_ref,"
            "w.valued_from_date,w.valued_through_date,w.consumed_request_fingerprint "
            "FROM valuation_scope s JOIN valuation_watermark w USING(scope_ref) ORDER BY s.asset_id,s.listing_ref")]
        days: dict[str, dict[str, dict[str, Any]]] = {}
        pair_days: dict[str, dict[str, dict[str, Any]]] = {}
        selected = sorted(dates) if dates is not None else None
        for chunk in ([selected[i:i + 500] for i in range(0, len(selected), 500)] if selected is not None else [None]):
            where, values = ("", ()) if chunk is None else (" WHERE trading_date IN (" + ",".join("?" for _ in chunk) + ")", tuple(chunk))
            for row in connection.execute("SELECT scope_ref,trading_date,valuation_status,status FROM valuation_day" + where, values):
                days.setdefault(row["trading_date"], {})[row["scope_ref"]] = {"scope_ref": row["scope_ref"], "valuation_status": row["valuation_status"], "status": row["status"]}
            where = where.replace("trading_date", "rate_date")
            for row in connection.execute("SELECT pair_ref,rate_date,rate_decimal FROM fx_effective_day" + where, values):
                pair_days.setdefault(row["rate_date"], {})[row["pair_ref"]] = {"pair_ref": row["pair_ref"], "rate_decimal": row["rate_decimal"]}
        latest = connection.execute(
            "SELECT max(trading_date) FROM valuation_day WHERE valuation_status <> 'incomplete'").fetchone()[0]
        pairs = [dict(row) for row in connection.execute(
            "SELECT pair_ref,valued_from_date,valued_through_date FROM fx_effective_watermark ORDER BY pair_ref")]
    except sqlite3.Error:
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    finally:
        connection.close()
    requests = {scope["listing_ref"]: _listing_requests(data_space, scope["listing_ref"]) for scope in scopes}
    return {"scopes": scopes, "days": days, "pair_days": pair_days, "latest": latest, "pairs": pairs, "requests": requests,
            "scope_order": scope_order_v1(scopes, current_symbols_v1(data_space))}


def _market_levels(data_space: Path, as_of_date: str, held: set[str],
                   methods: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return market_levels_day_v1(market_inputs_v1(data_space, {as_of_date}), as_of_date, held, methods)


def market_levels_day_v1(inputs: dict[str, Any] | None, as_of_date: str, held: set[str],
                         methods: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Markt- und Wechselkurs-Ebene eines Tages aus geladenen Eingaengen (market_inputs_v1). Liest nichts."""
    methods = methods_on_day_v1(methods, as_of_date)
    if inputs is None:
        # Ohne Stand ist nichts angefordert. Auch dann gilt die Eigentuemerwahl:
        # ein 'manual' bewertetes Asset fehlt nicht, es ist ausgenommen.
        uncovered = sorted(held)
        # Haelt der Eigentuemer nur, was er selbst bewertet oder ohne Wert fuehrt,
        # gibt es am Markt nichts anzufordern - auch ohne Stand.
        absent_reason = ("valuation_state_absent"
                         if any(methods.get(a) not in OWNER_CHOICE_METHODS for a in uncovered) else "nothing_to_value")
        return (_level("market_history", "not_requested", absent_reason),
                _level("fx_history", "not_requested", absent_reason),
                {"scope_count": 0, "held_scope_count": 0,
                 "held_without_scope": [a for a in uncovered if methods.get(a) not in OWNER_CHOICE_METHODS],
                 "held_by_owner_choice": [a for a in uncovered if methods.get(a) in OWNER_CHOICE_METHODS],
                 "scopes": [], "pairs": [], "latest_valued_date": None})
    scopes, latest, pairs = inputs["scopes"], inputs["latest"], inputs["pairs"]
    days = inputs["days"].get(as_of_date, {})
    pair_days = inputs["pair_days"].get(as_of_date, {})

    scope_rows: list[dict[str, Any]] = []
    # Was die Bewertungstage der gehaltenen Positionen ueber ihr Waehrungspaar
    # belegen: Ein umgerechneter Tag beweist, dass an ihm ein Kurs wirksam war.
    needed_pairs: set[str] = set()
    proven_pairs: set[str] = set()
    unavailable_pairs: set[str] = set()
    # Je Asset zaehlt der Bereich, der den Tag traegt; ein abgeloester Bereich haelt den Tag nicht offen (#474).
    effective = effective_scope_refs_v1(inputs.get("scope_order") or scope_order_v1(scopes, {}), as_of_date)
    for scope in scopes:
        if effective.get(scope["asset_id"], scope["scope_ref"]) != scope["scope_ref"]:
            continue
        day = days.get(scope["scope_ref"])
        if inputs["requests"][scope["listing_ref"]] != scope["consumed_request_fingerprint"]:
            status, reason = "stale_market", "listing_requests_changed"
        elif not scope["valued_from_date"] <= as_of_date <= scope["valued_through_date"]:
            status, reason = "valuation_pending", "as_of_outside_valued_window"
        elif day is None:
            status, reason = "valuation_pending", "no_valued_day"
        elif day["valuation_status"] == "complete":
            status, reason = "complete", "valued_" + day["status"]
        elif day["valuation_status"] == "substituted":
            status, reason = "complete", "valued_substituted"
        else:
            status, reason = "source_gap", "day_" + day["status"]
        scope_rows.append({"asset_id": scope["asset_id"], "provider_symbol": scope["provider_symbol"],
                           "status": status, "reason_code": reason, "held": scope["asset_id"] in held})
        if scope["asset_id"] in held and scope["pair_ref"] is not None:
            needed_pairs.add(scope["pair_ref"])
            if status == "complete" and day["status"] == "converted":
                proven_pairs.add(scope["pair_ref"])
            elif status == "source_gap" and day["status"] == "fx_unavailable":
                unavailable_pairs.add(scope["pair_ref"])

    # Die Wechselkurs-Ebene beurteilt, was der Snapshot braucht: die Paare, in
    # denen gehaltene Positionen notieren - wie die Marktebene nur gehaltene
    # Assets beurteilt. Bis rc.239 zaehlte jedes Paar des Stands, und gelesen
    # wurde allein dessen Tagesvektor. Deshalb war jeder aeltere
    # Stichtag "unvollstaendig", obwohl jede Position bewertet
    # war: Keine Position hielt eine Fremdwaehrung, und der Vektor
    # des einen Paares reichte nur bis zu diesem Tag zurueck - der Sammellauf
    # baut ihn je Asset fuer dessen eigenen Zeitraum neu, der Wasserstand nennt
    # weiter den fruehesten Beginn (12.10.2026).
    # Der staerkste Beleg ist deshalb der Bewertungstag der Position selbst: Er
    # ist es, mit dem der Snapshot rechnet. Der Vektor zaehlt nur, wo keine
    # Position den Tag belegt.
    known_pairs = {pair["pair_ref"]: pair for pair in pairs}
    pair_rows: list[dict[str, Any]] = []
    for pair_ref in sorted(set(known_pairs) | needed_pairs):
        pair = known_pairs.get(pair_ref)
        if pair_ref in unavailable_pairs:
            status, reason = "source_gap", "rate_unavailable"
        elif pair_ref in proven_pairs:
            status, reason = "complete", "rate_effective_in_valuation"
        elif pair is None:
            status, reason = "valuation_pending", "no_effective_day"
        elif not pair["valued_from_date"] <= as_of_date <= pair["valued_through_date"]:
            status, reason = "valuation_pending", "as_of_outside_valued_window"
        elif pair_ref not in pair_days:
            status, reason = "valuation_pending", "no_effective_day"
        elif pair_days[pair_ref]["rate_decimal"] is None:
            status, reason = "source_gap", "rate_unavailable"
        else:
            status, reason = "complete", "rate_effective"
        pair_rows.append({"pair_ref": pair_ref, "status": status, "reason_code": reason,
                          "needed": pair_ref in needed_pairs})

    # Beurteilt wird, was der Snapshot braucht: die gehaltenen Assets. Ein
    # Bereich ohne Bestand darf die Aussage nicht truebe machen, ein Bestand
    # ohne Bereich darf nicht stillschweigend fehlen.
    relevant = [row for row in scope_rows if row["held"]]
    covered = {row["asset_id"] for row in relevant}
    uncovered = sorted(held - covered)
    by_owner_choice = [asset for asset in uncovered if methods.get(asset) in OWNER_CHOICE_METHODS]
    missing = [asset for asset in uncovered if methods.get(asset) not in OWNER_CHOICE_METHODS]
    market = _worst("market_history", relevant, missing)
    fx = _worst("fx_history", [row for row in pair_rows if row["needed"]], [])
    detail = {"scope_count": len(scopes), "held_scope_count": len(relevant),
              "held_without_scope": missing, "held_by_owner_choice": by_owner_choice,
              "scopes": scope_rows, "pairs": pair_rows, "latest_valued_date": latest}
    return market, fx, detail


def _worst(code: str, rows: list[dict[str, Any]], missing: list[str]) -> dict[str, Any]:
    if missing:
        return _level(code, "source_gap", "held_without_scope",
                      {"held_without_scope_count": len(missing)})
    if not rows:
        return _level(code, "not_requested", "nothing_to_value")
    for status, reason in (("stale_market", "listing_requests_changed"),
                           ("source_gap", "day_unavailable"),
                           ("valuation_pending", "window_or_day_missing")):
        hit = [row for row in rows if row["status"] == status]
        if hit:
            return _level(code, status, reason, {"affected_count": len(hit)})
    return _level(code, "complete", "all_valued", {"valued_count": len(rows)})


def _basis_text(value: Any) -> str | None:
    """Die Anschaffungsbasis eines Ereignisses als Text - dezimal oder als Bruch.

    Der Stand legt sie als JSON-Text mit Genauigkeitsvermerk ab. Nicht jeder Wert
    ist endlich dezimal darstellbar; dann tragen Zaehler und Nenner ihn, und nur
    die Dezimalform zu lesen verlore ihn (#283, 26.09.2026).
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return value
    if not isinstance(value, dict):
        return None
    if value.get("exactness_status") == "basis_missing":
        return None
    if value.get("decimal") is not None:
        return str(value["decimal"])
    numerator, denominator = value.get("numerator_integer"), value.get("denominator_integer")
    if numerator is None or denominator is None:
        return None
    return amount_text_v1(Fraction(int(numerator), int(denominator)))


def holdings_as_of_v1(data_space: Path, context: DesktopProductAssetActivityContextV1,
                    as_of_date: str) -> dict[str, dict[str, Any]]:
    """Bestand und Anschaffungsbasis, wie sie am Stichtag waren.

    Der FIFO-Stand fuehrt je Ereignis den Stand danach: asset_quantity_after und
    asset_fifo_basis_after. Der Stand eines Tages ist also der Stand nach dem
    letzten Ereignis mit Datum <= Stichtag - keine Neuberechnung, eine Abfrage.

    Den heutigen Bestand zu nehmen war falsch: Ein Stichtagsbild fuehrte ein
    Asset mit seinem heutigen Bestand, obwohl der erste Kauf erst nach dem
    Stichtag lag (Befund 27.09.2026, #373).
    """
    return holdings_at_v1(holdings_timeline_v1(data_space, context), as_of_date)


def holdings_timeline_v1(data_space: Path, context: DesktopProductAssetActivityContextV1) -> dict[str, list[tuple[str, int, dict[str, Any]]]]:
    """Je Asset die Ereignisse des FIFO-Stands mit Datum, geordnet nach (Tag, Folge) - einmal geladen. Der Stand eines Tages
    ist eine Abfrage darauf (holdings_at_v1); die Tageshistorie (#473) liest so jeden Tag aus derselben Quelle wie der Snapshot.
    Die Zeilen tragen auch die Verwahrmengen je Konto (Quelle und bei Transfers Ziel)."""
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding.get("status") != "available" or not binding.get("ledger_path"):
        return {}
    try:
        ledger = sqlite3.connect("file:" + str(binding["ledger_path"]) + "?mode=ro", uri=True)
    except sqlite3.Error:
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    try:
        dates = {row[0]: row[1] for row in ledger.execute(
            "SELECT event_ref, local_date FROM current_asset_activity_event")}
    except sqlite3.Error:
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    finally:
        ledger.close()

    path = data_space / "realized-state-v2" / "realized-state.sqlite"
    if not path.is_file():
        return {}
    try:
        store = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        store.row_factory = sqlite3.Row
    except sqlite3.Error:
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    try:
        rows = store.execute("SELECT world_artifacts_json FROM current_realized_global_artifact").fetchall()
        if not rows:
            return {}
        worlds = {item["world_artifact_ref"] for item in json.loads(rows[0]["world_artifacts_json"])}
        if not worlds:
            return {}
        marks = ",".join("?" for _ in worlds)
        events = store.execute(
            f"SELECT world_artifact_ref,event_sequence,event_ref,asset_ref,"
            f"asset_quantity_after_decimal,asset_fifo_basis_after,account_ref,related_account_ref,"
            f"custody_quantity_after_decimal,destination_custody_quantity_after_decimal "
            f"FROM realized_event_result WHERE world_artifact_ref IN ({marks})",
            tuple(sorted(worlds))).fetchall()
        # Splits (#451) stehen nicht in realized_event_result, sondern im Ergebnis der Welt. Nur Welten mit Split werden gelesen.
        split_worlds = store.execute(
            f"SELECT world_artifact_ref,result_json FROM realized_world_artifact WHERE world_artifact_ref IN ({marks}) "
            f"AND instr(result_json, '\"split_results\"') > 0", tuple(sorted(worlds))).fetchall()
        split_results = {row["world_artifact_ref"]: json.loads(row["result_json"]).get("split_results", []) for row in split_worlds}
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    finally:
        store.close()

    timeline: dict[str, list[tuple[str, int, dict[str, Any]]]] = {}
    for row in events:
        day = dates.get(row["event_ref"])
        if day is None:
            continue
        timeline.setdefault(row["asset_ref"], []).append((day, row["event_sequence"], dict(row)))
    _add_split_rows(timeline, events, split_results)
    for entries in timeline.values():
        entries.sort(key=lambda item: (item[0], item[1]))
    return timeline


def _add_split_rows(timeline: dict[str, list[tuple[str, Any, dict[str, Any]]]], events: Any,
                    split_results: dict[str, list[dict[str, Any]]]) -> None:
    """Je Split und Konto eine Zeile am Stichtag, vor dessen Buchungen (#451): Menge danach, Einstand wie vor dem Split.

    Folge ist die der letzten Buchung davor plus einen Bruchteil - so steht der Split nach allen frueheren und vor allen Buchungen
    seines Tages. Die Zeile traegt "split" mit Kennung und Verhaeltnis; wer Buchungen nachschlaegt, erkennt sie daran. Ohne
    Buchung davor gab es nichts zu teilen."""
    if not split_results:
        return
    previous = {(row["world_artifact_ref"], int(row["event_sequence"])): row for row in events}
    for world, rows in split_results.items():
        for split in rows:
            after = int(split["after_event_sequence"])
            prior = previous.get((world, after))
            if prior is None:
                continue
            for index, custody in enumerate(split["custody"], 1):
                timeline.setdefault(split["asset_ref"], []).append((split["effective_local_date"], after + index / 1000, {
                    "world_artifact_ref": world, "event_sequence": after + index / 1000, "event_ref": split["split_ref"],
                    "asset_ref": split["asset_ref"], "asset_quantity_after_decimal": split["asset_quantity_after_decimal"],
                    "asset_fifo_basis_after": prior["asset_fifo_basis_after"], "account_ref": custody["account_ref"],
                    "related_account_ref": None, "custody_quantity_after_decimal": custody["custody_quantity_after_decimal"],
                    "destination_custody_quantity_after_decimal": None,
                    "split": {"split_ref": split["split_ref"], "ratio_numerator": split["ratio_numerator"],
                              "ratio_denominator": split["ratio_denominator"]}}))


def holdings_at_v1(timeline: dict[str, list[tuple[str, int, dict[str, Any]]]], as_of_date: str) -> dict[str, dict[str, Any]]:
    """Bestand und Anschaffungsbasis je Asset am Stichtag: Stand nach dem letzten Ereignis mit Datum <= Stichtag."""
    latest: dict[str, tuple[str, int, dict[str, Any]]] = {}
    for asset, entries in timeline.items():
        position = bisect.bisect_right([entry[0] for entry in entries], as_of_date)
        if position:
            latest[asset] = entries[position - 1]

    holdings: dict[str, dict[str, Any]] = {}
    for asset, (_, _, row) in latest.items():
        quantity = row["asset_quantity_after_decimal"]
        if quantity is None or exact_amount_v1(quantity) == 0:
            continue
        basis = _basis_text(row["asset_fifo_basis_after"])
        average = None
        if basis is not None:
            average = amount_text_v1(exact_amount_v1(basis) / exact_amount_v1(quantity))
        holdings[asset] = {"quantity": quantity, "cost_basis": basis, "cost_average": average}
    return holdings


def read_portfolio_snapshot_freshness_v1(
    data_space_path: str | Path,
    context_value: Any,
    as_of_date: str,
    canonical_path: str | Path | None = None,
    *,
    market_levels: Any = None,
) -> dict[str, Any]:
    """Frische je Ebene zum Stichtag. Kein Provider, keine Rechnung, kein Schreiben.

    'market_levels' tauscht aus, woran Markt- und Wechselkurs-Ebene gemessen
    werden: der Stichtags-Snapshot an den Bewertungstagen, der fluide an den
    zuletzt abgerufenen Kursen. Alles andere - Buchungsbestand, FIFO,
    Eigentuemerwahl, Cash - ist fuer beide dieselbe Rechnung
    (Festlegung 12.10.2026).
    """
    try:
        context = _runtime(context_value)
        as_of = _date(as_of_date)
        data_space = Path(data_space_path)
        sources = freshness_sources_v1(data_space, context, canonical_path)
        # Der Bestand des Stichtags, nicht der heutige: Sonst beurteilte die
        # Frische Assets, die an diesem Tag noch gar nicht gehalten wurden
        # (Befund 27.09.2026, #373).
        held = set(holdings_as_of_v1(data_space, context, as_of))
        market, fx, detail = (market_levels or _market_levels)(
            data_space, as_of, held, _valuation_methods(data_space, context))
        return freshness_day_v1(sources, as_of, held, market, fx, detail)
    except PortfolioSnapshotFreshnessV1Error:
        raise
    except Exception:
        _abort("portfolio_snapshot_freshness_boundary_failed")


def freshness_sources_v1(data_space: Path, context: DesktopProductAssetActivityContextV1, canonical_path: str | Path | None = None) -> dict[str, Any]:
    """Was das Frische-Urteil unabhaengig vom Stichtag liest: Buchungsbestand, FIFO-Stand, Cash-Sicht - einmal geladen."""
    try:
        binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    except DesktopProductAssetActivityV1Error:
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    try:
        realized = read_asset_activity_realized_state_v2(data_space, context)
    except AssetActivityRealizedStateV2Error:
        _abort("portfolio_snapshot_freshness_evidence_invalid")
    canonical = Path(canonical_path) if canonical_path is not None else data_space / "canonical.sqlite"
    if not canonical.is_file():
        cash = {"status": "absent", "periods": []}
    else:
        try:
            cash = read_desktop_cash_coverage_view_v1(canonical, data_space, context)
        except DesktopCashCoverageV1Error:
            # Fehlende Cash-Erklaerung ist kein Beweisfehler, sondern eine
            # offene Ebene. Sie darf die uebrigen nicht mitreissen.
            cash = {"status": "absent", "periods": []}
    return {"binding": binding, "realized": realized, "cash": cash, "account_states": _account_states_by_label(data_space, context, canonical)}


def _account_states_by_label(data_space: Path, context: DesktopProductAssetActivityContextV1, canonical: Path) -> dict[str, dict[str, Any]] | None:
    """Geschlossen seit / inaktiv seit je Kontoname (#534): Die Cash-Zeilen des Snapshots tragen den Namen, nicht die Kennung.
    Ohne lesbare Ablage oder bei einem doppelten Namen kein Zustand - dann blendet die Anzeige nichts aus."""
    from migrations.reference.statement_archive_v1 import StatementArchiveV1Error, read_statement_account_states_v1
    if not canonical.is_file():
        return None
    try:
        states = read_statement_account_states_v1(data_space, context)
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            names = connection.execute("SELECT account_id, display_name FROM account").fetchall()
        finally:
            connection.close()
    except (StatementArchiveV1Error, sqlite3.Error):
        return None
    seen: dict[str, int] = {}
    for _, name in names:
        seen[name] = seen.get(name, 0) + 1
    return {name: states.get(account_id, {}) for account_id, name in names if seen[name] == 1}


def account_state_v1(state: dict[str, Any] | None, as_of: str) -> str:
    """Zustand eines Kontos am Stichtag: "closed" (geschlossen bis dahin), "resting" (ruht seit einem Tag bis dahin) oder "active"."""
    state = state or {}
    if state.get("closed_on") and state["closed_on"] <= as_of:
        return "closed"
    if state.get("inactive_since") and state["inactive_since"] <= as_of:
        return "resting"
    return "active"


def _with_account_states(cash_as_of: dict[str, Any], states: dict[str, dict[str, Any]] | None, as_of: str) -> dict[str, Any]:
    """Seit rc.360 (#534): je Cash-Konto sein Zustand am Stichtag - die Anzeige blendet Kleinstbestaende nur auf geschlossenen und
    ruhenden Konten aus (Festlegung 04.11.2026). Unbekannter Zustand: kein Feld."""
    if states is None:
        return cash_as_of
    for account in cash_as_of.get("accounts", []):
        if account.get("account_label") in states:
            account["account_state"] = account_state_v1(states[account["account_label"]], as_of)
    return cash_as_of


def freshness_day_v1(sources: dict[str, Any], as_of: str, held: set[str], market: dict[str, Any], fx: dict[str, Any],
                     detail: dict[str, Any]) -> dict[str, Any]:
    """Das Frische-Urteil eines Tages aus geladenen Quellen und den Markt-Ebenen dieses Tages. Liest nichts."""
    binding, realized, cash = sources["binding"], sources["realized"], sources["cash"]
    if True:
        levels = []
        events = binding.get("asset_activity_event_count", 0) if binding.get("status") == "available" else 0
        levels.append(_level("activity", "complete" if events else "not_requested",
                             "active_generation" if events else "no_active_generation",
                             {"event_count": events}))

        freshness = realized.get("freshness", "unavailable")
        if freshness == "fresh":
            fifo = _level("fifo_basis", "complete", "fifo_v2_fresh")
        elif freshness.startswith("stale"):
            fifo = _level("fifo_basis", "stale_fifo", "fifo_v2_" + freshness)
        else:
            fifo = _level("fifo_basis", "not_requested", "fifo_v2_" + freshness)
        levels.append(fifo)

        levels.append(market)
        levels.append(fx)
        # Eigene Ebene, damit die Entscheidung sichtbar bleibt statt zu verschwinden.
        owner_choice = detail["held_by_owner_choice"]
        levels.append(_level("owner_excluded_assets",
                             "not_requested" if owner_choice else "complete",
                             "valuation_method_owner_choice" if owner_choice else "no_owner_choice_assets",
                             {"asset_count": len(owner_choice)}))

        periods = cash.get("periods") or []
        levels.append(_level("cash_coverage",
                             "complete" if cash.get("status") == "available" and periods else "not_requested",
                             "declared_periods" if periods else "cash_not_declared",
                             {"period_count": len(periods)}))

        # Ein Sammelurteil ist zulaessig, solange es nichts verdeckt: 'complete'
        # nur, wenn jede tragende Ebene erfuellt ist; sonst die schwerwiegendste
        # Abweichung unter genau diesen Ebenen.
        order = ("source_gap", "stale_market", "stale_fifo", "valuation_pending", "not_requested")
        open_levels = [row for row in levels if row["blocking"] and not row["satisfied"]]
        overall = next((s for s in order if any(row["status"] == s for row in open_levels)), "complete")
        return {
            "portfolio_snapshot_freshness_version": 1,
            "as_of_date": as_of,
            "overall_status": overall,
            "publishable": overall == "complete",
            "levels": levels,
            "held_asset_count": len(held),
            "held_without_scope_count": len(detail["held_without_scope"]),
            "held_by_owner_choice_count": len(detail["held_by_owner_choice"]),
            # Der juengste Tag, fuer den ueberhaupt ein Wert im Stand steht. Ohne
            # ihn bot die Karte "gestern" an - einen Tag, den der Stand noch nicht
            # kennt, und jede Position erschien als Luecke (26.09.2026, #373).
            "latest_valued_date": detail["latest_valued_date"],
            "scope_count": detail["scope_count"],
            # Der Cash-Bestand je Konto am Stichtag. Er gehoert nicht zur Frische,
            # entsteht aber aus derselben, hier schon gelesenen Cash-Sicht.
            "cash_as_of": _with_account_states(cash_as_of_v1(cash, as_of), sources.get("account_states"), as_of),
            "provider_access": False, "network_access": False,
            "canonical_write": False, "market_history_write": False, "path_exposed": False,
        }


__all__ = [
    "PortfolioSnapshotFreshnessV1Error", "account_state_v1",
    "portfolio_snapshot_freshness_v1_error_codes",
    "DERIVED_CASH_STATUSES",
    "cash_as_of_v1",
    "freshness_day_v1",
    "freshness_sources_v1",
    "holdings_at_v1",
    "holdings_timeline_v1",
    "market_inputs_v1",
    "market_levels_day_v1",
    "valuation_methods_v1",
    "read_portfolio_snapshot_freshness_v1",
    "current_symbols_v1",
    "effective_scope_refs_v1",
    "methods_on_day_v1",
    "scope_order_v1",
]
