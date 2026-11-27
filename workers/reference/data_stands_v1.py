"""Staende je Datenart (#463): bis wann jede Datenart reicht. Nur lesend.

Es muss klar sein, welches Bild ein Snapshot wirklich liefert. Cash kommt hoechstens
monatlich mit den Auszuegen, Rewards auch untermonatlich, Kurse taeglich. Ein Bild mit Stichtag heute wirkt sonst
vollstaendiger, als es ist. Dieser Leser nennt deshalb je Datenart das juengste belegte Datum - und wo es auf jedes Konto
oder Asset ankommt, auch das aelteste. Er rechnet nichts nach, ruft nichts ab und schreibt nichts.

Der FIFO-Stand gehoert nicht dazu: Er hat kein Datum, sondern ist aktuell oder nicht - und ihn zu beurteilen kostet einige Sekunden. "Alles aktualisieren" prueft ihn als eigenen Schritt.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import sqlite3
from typing import Any

from migrations.reference.desktop_cash_coverage_v1 import DesktopCashCoverageV1Error, read_desktop_cash_coverage_view_v1
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _context as _product_context,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.asset_valuation_facts_v1 import OWNER_CHOICE_METHODS
from migrations.reference.daily_market_history_v1 import DailyMarketHistoryBlocked, MarketHistoryContext, read_daily_market_history_v1
from workers.reference.portfolio_history_v1 import PortfolioHistoryV1Error, read_portfolio_history_v1
from workers.reference.portfolio_snapshot_freshness_v1 import (
    PortfolioSnapshotFreshnessV1Error,
    effective_scope_refs_v1,
    holdings_as_of_v1,
    market_inputs_v1,
    valuation_methods_v1,
)
from workers.reference.portfolio_snapshot_publication_v1 import (
    PortfolioSnapshotPublicationV1Error,
    list_published_portfolio_snapshots_v1,
)

CONTRACT = 1


class DataStandsV1Error(RuntimeError):
    CODES = frozenset({"data_stands_context_invalid", "data_stands_input_invalid", "data_stands_evidence_invalid"})

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("data_stands_error_code_unregistered")
        self.code = code
        super().__init__(code)


def data_stands_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(DataStandsV1Error.CODES))


def _abort(code: str) -> None:
    raise DataStandsV1Error(code)


def _activity(data_space: Path, context: DesktopProductAssetActivityContextV1) -> tuple[dict[str, Any], dict[str, Any]]:
    """Juengste Buchung, getrennt nach Rewards und allem anderen. Rewards kommen aus eigenen Importen und haben ihren
    eigenen Takt; ein frischer Kauf darf nicht verdecken, dass seit Wochen kein Reward eingelesen ist."""
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding.get("status") != "available" or not binding.get("ledger_path"):
        empty = {"status": "absent", "through": None, "event_count": 0, "account_count": 0}
        return dict(empty), dict(empty)
    try:
        connection = sqlite3.connect("file:" + str(binding["ledger_path"]) + "?mode=ro", uri=True)
        try:
            rows = connection.execute(
                "SELECT event_type='reward', max(local_date), count(*), count(DISTINCT account_id) "
                "FROM current_asset_activity_event GROUP BY event_type='reward'").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("data_stands_evidence_invalid")
    found = {bool(row[0]): {"status": "available", "through": row[1], "event_count": row[2], "account_count": row[3]} for row in rows}
    empty = {"status": "absent", "through": None, "event_count": 0, "account_count": 0}
    return found.get(False, dict(empty)), found.get(True, dict(empty))


def _cash(canonical: Path, data_space: Path, context: DesktopProductAssetActivityContextV1) -> dict[str, Any]:
    """Je Cash-Konto der Tag, bis zu dem sein Auszug reicht. Mehrere Zeitraeume eines Kontos zaehlen mit dem juengsten."""
    if not canonical.is_file():
        return {"status": "absent", "through": None, "earliest": None, "account_count": 0}
    try:
        view = read_desktop_cash_coverage_view_v1(canonical, data_space, context)
    except DesktopCashCoverageV1Error:
        # Fehlende Cash-Erklaerung ist eine offene Datenart, kein Beweisfehler der uebrigen.
        return {"status": "absent", "through": None, "earliest": None, "account_count": 0}
    if view.get("status") != "available":
        return {"status": "absent", "through": None, "earliest": None, "account_count": 0}
    through: dict[tuple[str, str], str] = {}
    for period in view.get("periods") or []:
        day = period.get("as_of_date")
        if isinstance(day, str) and day:
            key = (period["account_label"], period["cash_asset_label"])
            through[key] = max(through.get(key, ""), day[:10])
    if not through:
        return {"status": "absent", "through": None, "earliest": None, "account_count": 0}
    return {"status": "available", "through": max(through.values()), "earliest": min(through.values()),
            "account_count": len(through)}


def _prices(data_space: Path, context: DesktopProductAssetActivityContextV1, as_of: str) -> dict[str, Any]:
    """Bis wann die heute gehaltenen, am Markt bewerteten Assets bewertet sind: das juengste und das aelteste Ende. Ein
    einzelnes Asset, das zurueckliegt, haelt sonst unbemerkt jedes Bild unvollstaendig."""
    inputs = market_inputs_v1(data_space, set())
    methods = valuation_methods_v1(data_space, context)
    held = {asset for asset in holdings_as_of_v1(data_space, context, as_of) if methods.get(asset) not in OWNER_CHOICE_METHODS}
    if inputs is None:
        return {"status": "absent", "through": None, "earliest": None, "asset_count": len(held), "behind_count": 0,
                "without_valuation_count": len(held)}
    # Je Asset der Bereich, der den Stichtag traegt - nach einem Symbolwechsel der der aktuellen Zuordnung (#474).
    effective = set(effective_scope_refs_v1(inputs["scope_order"], as_of).values())
    through: dict[str, str] = {}
    for scope in inputs["scopes"]:
        if scope["asset_id"] in held and scope["scope_ref"] in effective and scope["valued_through_date"]:
            through[scope["asset_id"]] = scope["valued_through_date"]
    latest = max(through.values()) if through else None
    return {"status": "available" if through else "absent", "through": latest,
            "earliest": min(through.values()) if through else None, "asset_count": len(held),
            "behind_count": sum(1 for value in through.values() if value < latest) if latest else 0,
            "without_valuation_count": len(held - set(through))}


def read_data_stands_v1(data_space_path: str | Path, context_value: Any, as_of_date: str,
                        canonical_path: str | Path | None = None) -> dict[str, Any]:
    """Die Staende je Datenart zum Stichtag 'as_of_date' (Vorgabe der Data-App: heute)."""
    try:
        context = _product_context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("data_stands_context_invalid")
    try:
        if not isinstance(as_of_date, str) or date.fromisoformat(as_of_date).isoformat() != as_of_date:
            raise ValueError
    except ValueError:
        _abort("data_stands_input_invalid")
    data_space = Path(data_space_path)
    canonical = Path(canonical_path) if canonical_path is not None else data_space / "canonical.sqlite"
    try:
        transactions, rewards = _activity(data_space, context)
        prices = _prices(data_space, context, as_of_date)
        try:
            history = read_portfolio_history_v1(data_space, context)
        except PortfolioHistoryV1Error:
            history = {"status": "unavailable", "days": [], "last_run": None}
        try:
            library = list_published_portfolio_snapshots_v1(data_space, context)
        except PortfolioSnapshotPublicationV1Error:
            library = {"status": "unavailable", "snapshots": []}
    except (DesktopProductAssetActivityV1Error, PortfolioSnapshotFreshnessV1Error, sqlite3.Error, KeyError, TypeError):
        _abort("data_stands_evidence_invalid")
    days = history.get("days") or []
    snapshots = library.get("snapshots") or []
    newest = max(snapshots, key=lambda row: (row["as_of_date"], row["completed_at_utc"])) if snapshots else None
    return {
        "data_stands_version": CONTRACT,
        "as_of_date": as_of_date,
        "transactions": transactions,
        "rewards": rewards,
        "cash": _cash(canonical, data_space, context),
        "prices": prices,
        "history": {"status": history.get("status", "absent") if days else "absent",
                    "first": days[0]["day"] if days else None, "through": days[-1]["day"] if days else None,
                    # Der juengste Tag mit vollstaendiger Bewertung - fuer ihn veroeffentlicht "Alles aktualisieren" den Snapshot.
                    "complete_through": next((row["day"] for row in reversed(days)
                                              if row["overall_status"] == "complete" and row["market_value_complete"]), None)},
        "snapshot": {"status": "available" if newest else "absent",
                     "as_of_date": newest["as_of_date"] if newest else None,
                     "snapshot_status": newest["snapshot_status"] if newest else None},
        "provider_access": False, "network_access": False, "canonical_write": False,
    }


RECENT_GAP_WINDOW_MAX_DAYS = 31


def read_recent_source_gaps_v1(data_space_path: str | Path, context_value: Any, start: str, end: str) -> dict[str, Any]:
    """Quellluecken der letzten Tage (#477): je am Markt bewertetem Asset, das am Ende des Zeitraums gehalten wird, die Tage
    mit 'source_gap' an der Notierung der aktuellen Zuordnung. "Alles aktualisieren" fragt auf Wunsch genau diese Notierungen
    erneut ab. Nicht gehaltene Assets bleiben aussen vor: Ihre Luecken aendern kein aktuelles Bild. Nur lesend. Die Asset-Kennung geht nur an den Server der Data-App, der damit seine
    eigenen Zeilen zuordnet; angezeigt wird sie nicht."""
    try:
        context = _product_context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("data_stands_context_invalid")
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first.isoformat() != start or last.isoformat() != end or first > last or last - first > timedelta(days=RECENT_GAP_WINDOW_MAX_DAYS):
            raise ValueError
    except (TypeError, ValueError):
        _abort("data_stands_input_invalid")
    data_space = Path(data_space_path)
    empty = {"data_stands_version": CONTRACT, "status": "absent", "start": start, "end": end, "held_asset_count": 0,
             "listings": [], "gap_day_count": 0, "provider_access": False, "network_access": False, "canonical_write": False}
    try:
        inputs = market_inputs_v1(data_space, set())
        methods = valuation_methods_v1(data_space, context)
        held = {asset for asset in holdings_as_of_v1(data_space, context, end) if methods.get(asset) not in OWNER_CHOICE_METHODS}
        if inputs is None or not held:
            return {**empty, "held_asset_count": len(held)}
        store = data_space / "daily-market-history-v1" / "daily-market-history.sqlite"
        reader = MarketHistoryContext(context.tenant_id, context.user_id, context.data_space_id, "portfolio_reader", "portfolio_worker")
        listings = []
        for asset in sorted(held):
            # Die Reihenfolge stellt die Notierung der aktuellen Zuordnung voran (#474); sie ruft der Sammellauf ab.
            rows = inputs["scope_order"].get(asset) or []
            if not rows or not store.is_file():
                continue
            listing = next(scope["listing_ref"] for scope in inputs["scopes"] if scope["scope_ref"] == rows[0]["scope_ref"])
            history = read_daily_market_history_v1(store, reader, listing, start, end)
            gaps = sum(1 for day in history["days"] if day["day_status"] == "source_gap")
            if gaps:
                listings.append({"asset_id": asset, "listing_ref": listing, "gap_day_count": gaps})
    except (DesktopProductAssetActivityV1Error, PortfolioSnapshotFreshnessV1Error, DailyMarketHistoryBlocked, sqlite3.Error,
            StopIteration, KeyError, TypeError):
        _abort("data_stands_evidence_invalid")
    return {**empty, "status": "available", "held_asset_count": len(held), "listings": listings,
            "gap_day_count": sum(row["gap_day_count"] for row in listings)}


__all__ = ["DataStandsV1Error", "RECENT_GAP_WINDOW_MAX_DAYS", "data_stands_v1_error_codes", "read_data_stands_v1",
           "read_recent_source_gaps_v1"]
