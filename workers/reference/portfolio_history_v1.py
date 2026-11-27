"""Tageshistorie je Tag, Konto und Asset (#473): fortgeschrieben, ab dem fruehesten geaenderten Tag nachgerechnet.

Festlegung (12. und 19.10.2026): Fuer Plots, Tabellen und Dashboards soll je Tag ein Bild gespeichert sein, auf das
man zugreifen kann, und nachgezogen wird nur, was sich geaendert hat. Festlegungen vom 19.10.2026:

- Ein Nachtrag fuer einen vergangenen Tag wird ab diesem Tag nachgerechnet; die Reihe zeigt den heutigen Wissensstand.
  Veroeffentlichte Stichtags-Snapshots bleiben als versiegelte Staende unberuehrt.
- Gespeichert wird je Tag, Konto und Asset (Menge, Kurs, Wert), dazu Cash je Konto und die Tagessummen.

Gerechnet wird mit dem Tageskern des Stichtags-Snapshots (snapshot_day_v1) aus einmal geladenen Quellen: Bestandsverlauf
und Verwahrmengen aus dem FIFO-Stand, Bewertungstage, Markt- und Wechselkurs-Ebene, Cash-Sicht, Stammdaten. Ein Tag der
Reihe und ein Snapshot zu diesem Tag zeigen deshalb dieselben Zahlen.

Fortschreiben: Je Tag entsteht ein Abdruck der Eingaenge dieses Tages - rollend fuer alles, was sich aufsummiert
(Buchungen, FIFO-Ereignisse, Cash-Bewegungen, eigene Kursangaben), je Tag fuer die Bewertungstage und Wechselkurse, dazu
ein gemeinsamer Teil (Stammdaten, Bewertungsbereiche, Cash-Zeitraeume, Regelfassung). Der erste Tag, dessen Abdruck sich
vom gespeicherten unterscheidet, ist der frueheste geaenderte; gerechnet wird ab dort, geschrieben nur, was sich im
Ergebnis aendert. Ein Neuaufbau rechnet dieselben Tage mit derselben Funktion und ergibt denselben Stand.

Kein Provider, kein Netz, kein kanonischer Write. Ein veralteter FIFO-Stand haelt den Lauf an: Er wuerde jeden Tag mit
falschem Bestand rechnen.
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping
import hashlib
import json
import sqlite3
import time

from workers.reference.stock_split_prices_v1 import split_price_adjuster_v1
from migrations.reference.asset_valuation_facts_v1 import ValuationFactsCacheV1, asset_master_v1, provider_mapping_v1
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1
from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1
from workers.reference import portfolio_snapshot_freshness_v1 as freshness_module
from workers.reference import portfolio_snapshot_projection_v1 as projection_module

AREA = "portfolio-history-v1"
STORE = "portfolio-history.sqlite"
SCHEMA_VERSION = 1
# Aendert sich die Rechnung, aendert sich dieser Wert - und damit jeder Tagesabdruck: Der naechste Lauf rechnet alles neu.
ALGORITHM = "portfolio_history_v1/3"   # /2: je Asset und Tag zaehlt ein Bewertungsbereich (#474); /3: Konten mit mehreren Auszugszeitraeumen zaehlen (#479)
CONTRACT = "portfolio_history_v1"
FAILURE_CODES = (
    "portfolio_history_context_invalid",
    "portfolio_history_input_invalid",
    "portfolio_history_fifo_stale",
    "portfolio_history_evidence_invalid",
    "portfolio_history_store_invalid",
)
SCHEMA = (
    "CREATE TABLE history_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL,"
    " tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE history_run(run_id INTEGER PRIMARY KEY AUTOINCREMENT, requested_at_utc TEXT NOT NULL, mode TEXT NOT NULL"
    " CHECK(mode IN ('incremental','rebuild')), algorithm TEXT NOT NULL, first_day TEXT, last_day TEXT, recomputed_from TEXT,"
    " computed_day_count INTEGER NOT NULL, written_day_count INTEGER NOT NULL, removed_day_count INTEGER NOT NULL,"
    " duration_ms INTEGER NOT NULL, global_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TABLE history_day(day TEXT PRIMARY KEY, input_fingerprint TEXT NOT NULL, result_fingerprint TEXT NOT NULL,"
    " market_value_decimal TEXT, cost_basis_decimal TEXT, unrealised_decimal TEXT, trade_derived_value_decimal TEXT,"
    " cash_balance_decimal TEXT, cash_derived_balance_decimal TEXT, net_worth_decimal TEXT,"
    " market_value_complete INTEGER NOT NULL, overall_status TEXT NOT NULL, held_asset_count INTEGER NOT NULL,"
    " valued_position_count INTEGER NOT NULL, excluded_position_count INTEGER NOT NULL, owner_excluded_count INTEGER NOT NULL,"
    " owner_valued_position_count INTEGER NOT NULL, cost_basis_unknown_count INTEGER NOT NULL,"
    " cash_counted_account_count INTEGER NOT NULL, cash_derived_account_count INTEGER NOT NULL,"
    " cash_uncounted_account_count INTEGER NOT NULL, cash_oldest_balance_date TEXT, cash_newest_balance_date TEXT,"
    " run_id INTEGER NOT NULL REFERENCES history_run(run_id)) STRICT",
    "CREATE TABLE history_position(day TEXT NOT NULL REFERENCES history_day(day) ON DELETE CASCADE, account_id TEXT NOT NULL,"
    " asset_id TEXT NOT NULL, quantity_decimal TEXT NOT NULL, valued INTEGER NOT NULL, unit_value_decimal TEXT,"
    " market_value_decimal TEXT, derived_value_decimal TEXT, owner_valuation INTEGER NOT NULL, owner_excluded INTEGER NOT NULL,"
    " price_basis TEXT, price_source_date TEXT, price_age_days INTEGER, day_status TEXT, reason TEXT,"
    " PRIMARY KEY(day, account_id, asset_id)) STRICT",
    "CREATE TABLE history_cash(day TEXT NOT NULL REFERENCES history_day(day) ON DELETE CASCADE, account_label TEXT NOT NULL,"
    " cash_asset_label TEXT NOT NULL, currency TEXT, balance_decimal TEXT, balance_target_decimal TEXT, balance_date TEXT,"
    " balance_status TEXT NOT NULL, in_total INTEGER NOT NULL, derived_from_date TEXT,"
    " PRIMARY KEY(day, account_label, cash_asset_label)) STRICT",
)


class PortfolioHistoryV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def portfolio_history_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise PortfolioHistoryV1Error(code if code in FAILURE_CODES else "portfolio_history_evidence_invalid")


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _context(value: Any) -> DesktopProductAssetActivityContextV1:
    if not isinstance(value, DesktopProductAssetActivityContextV1):
        _abort("portfolio_history_context_invalid")
    return value


def _utc(value: Any) -> str:
    if not isinstance(value, str):
        _abort("portfolio_history_input_invalid")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _abort("portfolio_history_input_invalid")
    return value


# --- Quellen, einmal geladen ---------------------------------------------------------------------------------------------

def _valued_all(data_space: Path, market: Mapping[str, Any] | None, adjuster: Any = None) -> tuple[dict[str, dict[str, dict[str, Any]]], set[str]]:
    """Alle Bewertungstage je Tag und Asset - je Asset und Tag aus dem Bereich, der den Tag traegt, wie im Snapshot (#474).
    Mit einem Split (#451) steht der Kurs vor dem Stichtag je Stueck dieses Tages (stock_split_prices_v1)."""
    order = (market or {}).get("scope_order") or {}
    # Mit Bewertungs-Zeitleiste (rc.393) waehlt deren Abschnitt die Reihe, auch bei nur einem Bereich (ein manual-Abschnitt nimmt
    # dann keinen Markttag).
    timeline = getattr(order, "timeline", None)
    several = {asset for asset, rows in order.items() if len(rows) > 1 or (timeline and timeline.has(asset))}
    path = data_space / freshness_module.STATE_AREA / freshness_module.STATE_NAME
    if not path.is_file():
        return {}, set()
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            by_day: dict[str, dict[str, dict[str, Any]]] = {}
            for row in connection.execute(
                    f"SELECT d.trading_date AS trading_date, s.scope_ref AS scope_ref, {projection_module.VALUED_COLUMNS} "
                    "FROM valuation_scope s JOIN valuation_day d USING(scope_ref) ORDER BY d.trading_date, s.asset_id, s.scope_ref"):
                value = dict(row)
                day, scope_ref = value.pop("trading_date"), value.pop("scope_ref")
                if value["asset_id"] in several and freshness_module.effective_scope_refs_v1(
                        {value["asset_id"]: order.get(value["asset_id"], [])}, day, timeline).get(value["asset_id"]) != scope_ref:
                    continue
                if adjuster:
                    value = adjuster.adjust(value, scope_ref, day)
                by_day.setdefault(day, {})[value["asset_id"]] = value
            scoped = {row[0] for row in connection.execute("SELECT asset_id FROM valuation_scope")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("portfolio_history_evidence_invalid")
    return by_day, scoped


def _ledger_rows(data_space: Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    """Die geltenden Buchungen - nur fuer den Abdruck: Preise und Zeitangaben bestimmen Handelswert und eigene Bewertung."""
    from migrations.reference.desktop_product_asset_activity_v1 import read_desktop_product_asset_activity_binding_v1
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding.get("status") != "available" or not binding.get("ledger_path"):
        return []
    try:
        connection = sqlite3.connect("file:" + str(binding["ledger_path"]) + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(
                "SELECT event_ref,event_type,account_id,asset_id,local_date,local_time,event_time_evidence,effective_at_utc,"
                "quantity_decimal,unit_price_decimal,gross_amount_decimal,monetary_fee_decimal FROM current_asset_activity_event "
                "ORDER BY local_date,event_ref")]
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("portfolio_history_evidence_invalid")


def _manual_entries(data_space: Path, context: Mapping[str, str], methods: Mapping[str, str]) -> list[dict[str, Any]]:
    from migrations.reference import manual_price_source_v1 as manual
    rows: list[dict[str, Any]] = []
    timeline = getattr(methods, "timeline", None)
    # Auch Assets mit einem Abschnitt eigener Kurse in der Zeitleiste (rc.393).
    manual_assets = {asset for asset, method in methods.items() if method == "manual"}
    if timeline:
        manual_assets |= {asset for asset in timeline.assets() if timeline.has_method(asset, "manual")}
    for asset_id in sorted(manual_assets):
        try:
            for entry in manual.read_manual_entries_v1(data_space, dict(context), asset_id)["entries"]:
                rows.append({"asset_id": asset_id, **{key: entry.get(key) for key in ("price_date", "value_decimal", "currency")}})
        except Exception:
            rows.append({"asset_id": asset_id, "price_date": "0000-00-00", "value_decimal": None, "currency": "unreadable"})
    return rows


def _custody_timeline(timeline: Mapping[str, list[tuple[str, int, dict[str, Any]]]]) -> dict[str, dict[str, tuple[list[str], list[str]]]]:
    """Je Konto und Asset die Verwahrmenge nach jedem Ereignis, das das Konto beruehrt - Quelle und bei Transfers Ziel."""
    custody: dict[tuple[str, str], list[tuple[str, int, str]]] = {}
    for asset, entries in timeline.items():
        for day, sequence, row in entries:
            if row.get("account_ref") and row.get("custody_quantity_after_decimal") is not None:
                custody.setdefault((row["account_ref"], asset), []).append((day, sequence, row["custody_quantity_after_decimal"]))
            if row.get("related_account_ref") and row.get("destination_custody_quantity_after_decimal") is not None:
                custody.setdefault((row["related_account_ref"], asset), []).append((day, sequence, row["destination_custody_quantity_after_decimal"]))
    result: dict[str, dict[str, tuple[list[str], list[str]]]] = {}
    for (account, asset), entries in custody.items():
        entries.sort(key=lambda item: (item[0], item[1]))
        result.setdefault(asset, {})[account] = ([entry[0] for entry in entries], [entry[2] for entry in entries])
    return result


def _market_data_wanted(data_space: Path) -> bool:
    """Ob im Datenraum der Baustein „Marktdaten“ laeuft (#542). Nur lesend und ohne Eigentuemerkontext; nicht lesbar oder ohne
    Eintrag = er laeuft, wie bisher."""
    try:
        from migrations.reference.portfolio_configuration_v1 import effective_modules_v1
        return effective_modules_v1(data_space).get("market_data") is not False
    except Exception:
        return True


def _through_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        _abort("portfolio_history_input_invalid")
    return value


def _load(data_space: Path, context: DesktopProductAssetActivityContextV1, canonical: Path) -> dict[str, Any]:
    sources = freshness_module.freshness_sources_v1(data_space, context, canonical)
    if sources["realized"].get("freshness") != "fresh":
        _abort("portfolio_history_fifo_stale")
    plain = {"tenant_id": context.tenant_id, "user_id": context.user_id, "data_space_id": context.data_space_id}
    timeline = freshness_module.holdings_timeline_v1(data_space, context)
    market = freshness_module.market_inputs_v1(data_space, None)
    methods = freshness_module.valuation_methods_v1(data_space, context)
    adjuster = split_price_adjuster_v1(data_space, context)
    valued, scoped = _valued_all(data_space, market, adjuster)
    return {"sources": sources, "context": plain, "timeline": timeline, "custody": _custody_timeline(timeline), "market": market,
            "methods": methods, "master": asset_master_v1(data_space, plain), "mappings": provider_mapping_v1(data_space),
            "valued": valued, "scoped": scoped, "ledger": _ledger_rows(data_space, context),
            "market_data": _market_data_wanted(data_space),
            "splits": sorted((asset, day, str(ratio)) for asset, rows in adjuster.splits.items() for day, ratio in rows),
            "manual": _manual_entries(data_space, plain, methods)}


# --- Tage und Abdruecke --------------------------------------------------------------------------------------------------

def _due_through(data_space: Path, context: DesktopProductAssetActivityContextV1, inputs: Mapping[str, Any], stamp: str) -> str | None:
    """Der juengste Tag, der fuer alle gehaltenen Notierungen faellig ist - nur wenn einer davon den letzten Bewertungstag kappt (#574).

    Die Reihe endet beim juengsten Bewertungstag irgendeiner Notierung. Kurz nach Mitternacht hat eine Xetra-Notierung den Vortag
    schon (abgeschlossen 18:35), Krypto, Wechselkurse und Assets in Fremdwaehrung aber erst eine Stunde nach dem Tagesende
    (market_day_completion_v1). Ohne diese Grenze entstand im Fenster dazwischen (Winter etwa 01:00-02:00) ein letzter Tag ohne ihre
    Kurse, und die Bewertung fiel auf die eigene Bewertung zurueck. Gekappt wird nur, wenn eine gehaltene Notierung zurueckliegt,
    WEIL ihr Tag noch nicht faellig ist; liegt sie aus anderem Grund zurueck (Quelle liefert nicht), haelt sie die Reihe nicht an
    (#566). Liegt der Zeitpunkt vor dem letzten Bewertungstag (Testdaten, verstellte Uhr), wird nie gekappt. Nicht lesbar = keine
    Grenze, wie bisher.
    """
    market = inputs.get("market") or {}
    latest = market.get("latest")
    if not latest or not inputs.get("market_data", True):
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.date().isoformat() < latest:
        return None
    held = set(freshness_module.holdings_at_v1(inputs["timeline"], latest))
    scopes = market.get("scopes") or []
    # Ein Asset, dessen aktuelle Zuordnung den Tag schon traegt, haelt nichts an - auch nicht ein beendeter alter Bereich (#474).
    covered = {scope.get("asset_id") for scope in scopes if (scope.get("valued_through_date") or "") >= latest}
    lagging = [scope for scope in scopes if scope.get("asset_id") in held and scope.get("asset_id") not in covered
               and scope.get("valued_through_date") and scope["valued_through_date"] < latest]
    if not lagging:
        return None
    try:
        from migrations.reference.daily_market_history_v1 import MarketHistoryContext, read_daily_market_history_v1
        from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA, STORE_NAME
        from migrations.reference.fx_history_v1 import FxHistoryContext, read_fx_history_v1
        from migrations.reference.desktop_fx_pair_promotion_v1 import AREA as FX_AREA, STORE as FX_STORE
        from migrations.reference.market_day_completion_v1 import DEFAULT_MODE, completed_through_v1
        from migrations.reference.user_settings_v1 import read_market_day_completion_v1
    except Exception:
        return None
    try:
        mode = read_market_day_completion_v1(data_space, context)
    except Exception:
        mode = DEFAULT_MODE
    ids = (context.tenant_id, context.user_id, context.data_space_id)
    due: str | None = None
    for scope in lagging:
        try:
            history = read_daily_market_history_v1(data_space / MARKET_AREA / STORE_NAME, MarketHistoryContext(*ids, "portfolio_reader", "portfolio_worker"),
                                                   scope["listing_ref"], latest, latest)
            ready = completed_through_v1(history["timezone_name"], moment, market_code=history.get("market_code"), mode=mode)
            if scope.get("pair_ref"):
                pair = read_fx_history_v1(data_space / FX_AREA / FX_STORE, FxHistoryContext(*ids, "market_worker", "market_worker"),
                                          scope["pair_ref"], latest, latest)
                ready = min(ready, completed_through_v1(pair["timezone_name"], moment))
        except Exception:
            continue
        if ready < latest:
            candidate = max(ready, scope["valued_through_date"])
            due = candidate if due is None else min(due, candidate)
    return due


def _day_range(inputs: Mapping[str, Any], through_date: str | None = None, due_through: str | None = None) -> list[str]:
    """Die Tage der Reihe: vom ersten Bestand oder Cash-Ereignis bis zum juengsten Bewertungstag des Kursabrufs.

    Ohne den Baustein „Marktdaten“ (#567) gibt es keinen Kursabruf, der den letzten Tag bestimmt - die Reihe blieb leer, obwohl die
    eigene Bewertung jeden Tag traegt (eigene Kursangabe, sonst der Kurs der juengsten Buchung, gekennzeichnet mit Herkunft, Tag und
    Alter). Dann reicht sie bis `through_date`, dem vom Aufrufer genannten Tag (der Vortag, wie der Snapshot ohne Verlauf, #542). Mit
    Marktdaten bleibt `through_date` ohne Wirkung: Tage nach dem juengsten Bewertungstag waeren dort Luecken.
    """
    starts = [entries[0][0] for entries in inputs["timeline"].values() if entries]
    cash = inputs["sources"]["cash"]
    starts += [event["local_date"] for event in cash.get("cash_history") or [] if event.get("local_date")]
    last = (inputs["market"] or {}).get("latest")
    if not inputs.get("market_data", True) and through_date:
        last = max(last, through_date) if last else through_date
    if due_through and last and due_through < last:
        last = due_through
    if not starts or not last:
        return []
    first = date.fromisoformat(min(starts))
    final = date.fromisoformat(last)
    return [(first + timedelta(days=offset)).isoformat() for offset in range((final - first).days + 1)]


def _global_fingerprint(inputs: Mapping[str, Any]) -> str:
    market = inputs["market"] or {"scopes": [], "pairs": [], "requests": {}}
    cash = inputs["sources"]["cash"]
    binding = inputs["sources"]["binding"]
    # Was fuer jeden Tag gleich wirkt. Der juengste Bewertungstag gehoert nicht dazu - er waechst taeglich und steht in
    # keinem gespeicherten Tagesergebnis; die Bewertungsfenster wirken je Tag (siehe _window_bits).
    return _sha({
        "algorithm": ALGORITHM, "master": inputs["master"], "mappings": inputs["mappings"], "methods": inputs["methods"],
        "scoped": sorted(inputs["scoped"]),
        "scopes": [{key: scope[key] for key in ("scope_ref", "asset_id", "listing_ref", "provider_symbol", "pair_ref")} for scope in market["scopes"]],
        "stale_listings": sorted(scope["scope_ref"] for scope in market["scopes"] if market["requests"].get(scope["listing_ref"]) != scope["consumed_request_fingerprint"]),
        "pairs": sorted(pair["pair_ref"] for pair in market["pairs"]),
        # Fuer das Urteil zaehlt nur, ob es Buchungen gibt; ihre Zahl waechst mit jeder und wirkt ueber die Tagesabdruecke.
        "activity": bool(binding.get("asset_activity_event_count", 0)) if binding.get("status") == "available" else False,
        "cash_status": cash.get("status"), "cash_periods": cash.get("periods") or [],
        # Ein Split (#451) aendert die Tage vor seinem Stichtag; ohne Split bleibt der Abdruck, wie er war.
        **({"splits": inputs["splits"]} if inputs.get("splits") else {}),
    })


def _window_bits(inputs: Mapping[str, Any], day: str) -> list[Any]:
    market = inputs["market"] or {"scopes": [], "pairs": []}
    # Was die Bewertungs-Zeitleiste an diesem Tag festlegt (rc.393): Aendert sie sich, rechnet die Historie erst ab dem ersten
    # betroffenen Tag neu. Ohne Zeitleiste kommt nichts dazu - der Abdruck bleibt, wie er war.
    timeline = getattr(inputs.get("methods"), "timeline", None)
    return ([scope["scope_ref"] for scope in market["scopes"] if scope["valued_from_date"] <= day <= scope["valued_through_date"]]
            + ["fx:" + pair["pair_ref"] for pair in market["pairs"] if pair["valued_from_date"] <= day <= pair["valued_through_date"]]
            + (["timeline:" + timeline.day_key(day)] if timeline else []))


def _day_fingerprints(inputs: Mapping[str, Any], days: list[str], global_fp: str) -> dict[str, str]:
    """Je Tag ein Abdruck aller Eingaenge, die auf diesen Tag wirken - rollend fuer Aufsummiertes."""
    def by_day(rows, key):
        grouped: dict[str, list[Any]] = {}
        for row in rows:
            grouped.setdefault(row[key], []).append(row)
        return grouped
    # Die Artefakt-Kennung wechselt mit jedem FIFO-Lauf, auch wenn das Ereignis gleich bleibt - sie gehoert nicht in den Abdruck.
    fifo = by_day([{"day": day, "asset": asset, "sequence": sequence, **{key: value for key, value in row.items() if key != "world_artifact_ref"}}
                   for asset, entries in inputs["timeline"].items() for day, sequence, row in entries], "day")
    ledger = by_day(inputs["ledger"], "local_date")
    cash = by_day(list(inputs["sources"]["cash"].get("cash_history") or []), "local_date")
    manual = by_day(inputs["manual"], "price_date")
    market = inputs["market"] or {"days": {}, "pair_days": {}}
    before = [row for row in inputs["manual"] if row["price_date"] < (days[0] if days else "")]
    rolling = _sha(["start", global_fp, before,
                    [row for row in inputs["ledger"] if days and row["local_date"] < days[0]],
                    [row for row in inputs["sources"]["cash"].get("cash_history") or [] if days and (row.get("local_date") or "") < days[0]]])
    result = {}
    for day in days:
        rolling = _sha([rolling, day, sorted(json.dumps(row, sort_keys=True, default=str) for row in fifo.get(day, [])),
                        sorted(json.dumps(row, sort_keys=True, default=str) for row in ledger.get(day, [])),
                        sorted(json.dumps(row, sort_keys=True, default=str) for row in cash.get(day, [])),
                        sorted(json.dumps(row, sort_keys=True, default=str) for row in manual.get(day, []))])
        result[day] = _sha([rolling, inputs["valued"].get(day, {}), market["days"].get(day, {}), market["pair_days"].get(day, {}),
                            _window_bits(inputs, day)])
    return result


# --- Ein Tag -------------------------------------------------------------------------------------------------------------

def _custody_at(custody: Mapping[str, Mapping[str, tuple[list[str], list[str]]]], asset: str, day: str) -> list[tuple[str, str]]:
    import bisect
    rows = []
    for account, (days, quantities) in custody.get(asset, {}).items():
        position = bisect.bisect_right(days, day)
        if position and exact_amount_v1(quantities[position - 1]) != 0:
            rows.append((account, quantities[position - 1]))
    return sorted(rows)


def _day_result(data_space: Path, inputs: Mapping[str, Any], facts: ValuationFactsCacheV1, day: str) -> dict[str, Any]:
    holdings = freshness_module.holdings_at_v1(inputs["timeline"], day)
    held = set(holdings)
    market, fx, detail = freshness_module.market_levels_day_v1(inputs["market"], day, held, inputs["methods"])
    freshness = freshness_module.freshness_day_v1(inputs["sources"], day, held, market, fx, detail)
    image = projection_module.snapshot_day_v1(data_space, inputs["context"], freshness, holdings, inputs["master"], inputs["mappings"],
                                              inputs["valued"].get(day, {}), inputs["scoped"], facts=facts)
    positions = []
    for entry, valued in [(row, True) for row in image["positions"]] + [(row, False) for row in image["excluded_positions"]]:
        unit = entry.get("unit_value_decimal")
        split = _custody_at(inputs["custody"], entry["asset_id"], day) or [("", entry["quantity_decimal"])]
        for account, quantity in split:
            amount = exact_amount_v1(quantity)
            positions.append({
                "account_id": account, "asset_id": entry["asset_id"], "quantity_decimal": quantity, "valued": int(valued),
                "unit_value_decimal": unit,
                "market_value_decimal": amount_text_v1(amount * exact_amount_v1(unit)) if valued and unit is not None else None,
                "derived_value_decimal": amount_text_v1(amount * exact_amount_v1(unit)) if not valued and unit is not None else None,
                "owner_valuation": int(bool(entry.get("owner_valuation"))), "owner_excluded": int(bool(entry.get("owner_excluded"))),
                "price_basis": entry.get("price_basis"), "price_source_date": entry.get("price_source_date"),
                "price_age_days": entry.get("price_age_days"), "day_status": entry.get("day_status"), "reason": entry.get("reason")})
    cash = [{key: account.get(key) for key in ("account_label", "cash_asset_label", "currency", "balance_decimal", "balance_target_decimal",
                                               "balance_date", "balance_status", "derived_from_date")} | {"in_total": int(bool(account.get("in_total")))}
            for account in image["cash"]["accounts"]]
    totals, counts, block = image["totals"], image["counts"], image["cash"]
    summary = {**{key: totals.get(key) for key in ("market_value_decimal", "cost_basis_decimal", "unrealised_decimal", "trade_derived_value_decimal",
                                                   "cash_balance_decimal", "cash_derived_balance_decimal", "net_worth_decimal")},
               "market_value_complete": int(bool(image["market_value_complete"])), "overall_status": image["freshness"]["overall_status"],
               **{key: counts[key] for key in ("held_asset_count", "valued_position_count", "excluded_position_count", "owner_excluded_count",
                                               "owner_valued_position_count", "cost_basis_unknown_count")},
               "cash_counted_account_count": block["counted_account_count"], "cash_derived_account_count": block["derived_account_count"],
               "cash_uncounted_account_count": block["uncounted_account_count"], "cash_oldest_balance_date": block["oldest_balance_date"],
               "cash_newest_balance_date": block["newest_balance_date"]}
    return {"day": day, "summary": summary, "positions": positions, "cash": cash, "result_fingerprint": _sha([summary, positions, cash])}


# --- Speicher ------------------------------------------------------------------------------------------------------------

def _connect(data_space: Path, context: DesktopProductAssetActivityContextV1, create: bool) -> sqlite3.Connection | None:
    root = data_space / AREA
    path = root / STORE
    if root.is_symlink() or path.is_symlink():
        _abort("portfolio_history_store_invalid")
    expected = (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not path.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO history_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("portfolio_history_store_invalid")
        path.chmod(0o600)
    else:
        connection = sqlite3.connect(path if create else f"file:{path}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM history_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("portfolio_history_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("portfolio_history_store_invalid")
    return connection


POSITION_COLUMNS = ("account_id", "asset_id", "quantity_decimal", "valued", "unit_value_decimal", "market_value_decimal", "derived_value_decimal",
                    "owner_valuation", "owner_excluded", "price_basis", "price_source_date", "price_age_days", "day_status", "reason")
CASH_COLUMNS = ("account_label", "cash_asset_label", "currency", "balance_decimal", "balance_target_decimal", "balance_date", "balance_status",
                "in_total", "derived_from_date")
SUMMARY_COLUMNS = ("market_value_decimal", "cost_basis_decimal", "unrealised_decimal", "trade_derived_value_decimal", "cash_balance_decimal",
                   "cash_derived_balance_decimal", "net_worth_decimal", "market_value_complete", "overall_status", "held_asset_count",
                   "valued_position_count", "excluded_position_count", "owner_excluded_count", "owner_valued_position_count",
                   "cost_basis_unknown_count", "cash_counted_account_count", "cash_derived_account_count", "cash_uncounted_account_count",
                   "cash_oldest_balance_date", "cash_newest_balance_date")


def update_portfolio_history_v1(data_space_path: str | Path, context_value: Any, canonical_path: str | Path | None, requested_at_utc: str,
                                *, rebuild: bool = False, through_date: str | None = None) -> dict[str, Any]:
    """Schreibt die Tageshistorie fort: neue Tage anhaengen, ab dem fruehesten geaenderten Tag nachrechnen, nur Geaendertes
    schreiben. rebuild=True rechnet alle Tage, schreibt aber ebenso nur, was sich unterscheidet. `through_date`: bis zu diesem Tag
    reicht die Reihe, wenn kein Kursabruf den letzten Tag bestimmt (Umfang ohne „Marktdaten“, #567); sonst ohne Wirkung."""
    context = _context(context_value)
    stamp = _utc(requested_at_utc)
    through = _through_date(through_date)
    if not isinstance(rebuild, bool):
        _abort("portfolio_history_input_invalid")
    started = time.monotonic()
    data_space = Path(data_space_path)
    canonical = Path(canonical_path) if canonical_path is not None else data_space / "canonical.sqlite"
    try:
        inputs = _load(data_space, context, canonical)
    except PortfolioHistoryV1Error:
        raise
    except Exception:
        _abort("portfolio_history_evidence_invalid")
    days = _day_range(inputs, through, _due_through(data_space, context, inputs, stamp))
    global_fp = _global_fingerprint(inputs)
    fingerprints = _day_fingerprints(inputs, days, global_fp)
    connection = _connect(data_space, context, True)
    try:
        stored = {row["day"]: (row["input_fingerprint"], row["result_fingerprint"]) for row in connection.execute("SELECT day,input_fingerprint,result_fingerprint FROM history_day")}
        start = days[0] if (rebuild and days) else next((day for day in days if stored.get(day, (None,))[0] != fingerprints[day]), None)
        facts = ValuationFactsCacheV1(data_space, inputs["context"], days[-1]) if days else None
        computed = written = 0
        results = []
        for day in (days[days.index(start):] if start else []):
            results.append(_day_result(data_space, inputs, facts, day))
            computed += 1
        stale = sorted(set(stored) - set(days))
        with connection:
            run = connection.execute(
                "INSERT INTO history_run(requested_at_utc,mode,algorithm,first_day,last_day,recomputed_from,computed_day_count,written_day_count,"
                "removed_day_count,duration_ms,global_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (stamp, "rebuild" if rebuild else "incremental", ALGORITHM, days[0] if days else None, days[-1] if days else None, start,
                 computed, 0, len(stale), 0, global_fp)).lastrowid
            for day in stale:
                connection.execute("DELETE FROM history_day WHERE day=?", (day,))
            for result in results:
                day = result["day"]
                if stored.get(day) == (fingerprints[day], result["result_fingerprint"]):
                    continue
                if day in stored and stored[day][1] == result["result_fingerprint"]:
                    # Eingang anders, Ergebnis gleich: nur der Abdruck wandert mit.
                    connection.execute("UPDATE history_day SET input_fingerprint=?, run_id=? WHERE day=?", (fingerprints[day], run, day))
                    continue
                connection.execute("DELETE FROM history_day WHERE day=?", (day,))
                summary = result["summary"]
                connection.execute(
                    "INSERT INTO history_day(day,input_fingerprint,result_fingerprint," + ",".join(SUMMARY_COLUMNS) + ",run_id) VALUES("
                    + ",".join("?" for _ in range(len(SUMMARY_COLUMNS) + 4)) + ")",
                    (day, fingerprints[day], result["result_fingerprint"], *[summary[key] for key in SUMMARY_COLUMNS], run))
                connection.executemany(
                    "INSERT INTO history_position(day," + ",".join(POSITION_COLUMNS) + ") VALUES(" + ",".join("?" for _ in range(len(POSITION_COLUMNS) + 1)) + ")",
                    [(day, *[row[key] for key in POSITION_COLUMNS]) for row in result["positions"]])
                connection.executemany(
                    "INSERT INTO history_cash(day," + ",".join(CASH_COLUMNS) + ") VALUES(" + ",".join("?" for _ in range(len(CASH_COLUMNS) + 1)) + ")",
                    [(day, *[row[key] for key in CASH_COLUMNS]) for row in result["cash"]])
                written += 1
            duration = int((time.monotonic() - started) * 1000)
            connection.execute("UPDATE history_run SET written_day_count=?, duration_ms=? WHERE run_id=?", (written, duration, run))
    except sqlite3.Error:
        _abort("portfolio_history_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "updated", "mode": "rebuild" if rebuild else "incremental",
            "first_day": days[0] if days else None, "last_day": days[-1] if days else None, "recomputed_from": start,
            "computed_day_count": computed, "written_day_count": written, "removed_day_count": len(stale), "duration_ms": duration,
            "provider_access": False, "network_access": False, "canonical_write": False}


def verify_portfolio_history_v1(data_space_path: str | Path, context_value: Any, canonical_path: str | Path | None = None) -> dict[str, Any]:
    """Neuaufbau im Speicher gegen den gespeicherten Stand: dieselben Tage, dieselben Ergebnisse (Grundprinzip: 1:1 gleich)."""
    context = _context(context_value)
    data_space = Path(data_space_path)
    canonical = Path(canonical_path) if canonical_path is not None else data_space / "canonical.sqlite"
    inputs = _load(data_space, context, canonical)
    connection = _connect(data_space, context, False)
    if connection is None:
        return {"contract_version": CONTRACT, "status": "absent", "day_count": 0, "mismatch_days": []}
    try:
        stored = {row["day"]: row["result_fingerprint"] for row in connection.execute("SELECT day,result_fingerprint FROM history_day")}
        last_run = connection.execute("SELECT requested_at_utc FROM history_run ORDER BY run_id DESC LIMIT 1").fetchone()
    finally:
        connection.close()
    # Ohne Kursabruf (#567) reicht die Reihe so weit, wie sie zuletzt fortgeschrieben wurde - derselbe letzte Tag wie im Speicher.
    # Die Grenze der noch nicht faelligen Tage (#574) gilt zum Zeitpunkt der letzten Fortschreibung, wie dort.
    due = _due_through(data_space, context, inputs, last_run[0]) if last_run and last_run[0] else None
    days = _day_range(inputs, max(stored) if stored else None, due)
    facts = ValuationFactsCacheV1(data_space, inputs["context"], days[-1]) if days else None
    mismatch = [day for day in days if stored.get(day) != _day_result(data_space, inputs, facts, day)["result_fingerprint"]]
    mismatch += sorted(set(stored) - set(days))
    return {"contract_version": CONTRACT, "status": "exact_match" if not mismatch else "mismatch", "day_count": len(days),
            "mismatch_days": mismatch[:20], "mismatch_count": len(mismatch)}


def read_portfolio_history_v1(data_space_path: str | Path, context_value: Any, start: str | None = None, end: str | None = None,
                              *, detail: bool = False) -> dict[str, Any]:
    """Die gespeicherte Reihe im Zeitraum - Tagessummen, mit detail=True auch Positionen und Cash. Kennungen des Bestands
    gehen nur an Rechenkerne; wer anzeigt, ersetzt sie durch Bezeichnungen."""
    context = _context(context_value)
    for value in (start, end):
        if value is not None:
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                _abort("portfolio_history_input_invalid")
    connection = _connect(Path(data_space_path), context, False)
    if connection is None:
        return {"contract_version": CONTRACT, "status": "absent", "days": [], "last_run": None}
    try:
        bounds = (start or "0000-01-01", end or "9999-12-31")
        days = [dict(row) for row in connection.execute(
            "SELECT day," + ",".join(SUMMARY_COLUMNS) + " FROM history_day WHERE day BETWEEN ? AND ? ORDER BY day", bounds)]
        last = connection.execute("SELECT requested_at_utc,mode,first_day,last_day,recomputed_from,computed_day_count,written_day_count,duration_ms "
                                  "FROM history_run ORDER BY run_id DESC LIMIT 1").fetchone()
        result = {"contract_version": CONTRACT, "status": "ready", "days": days, "last_run": dict(last) if last else None}
        if detail:
            result["positions"] = [dict(row) for row in connection.execute(
                "SELECT day," + ",".join(POSITION_COLUMNS) + " FROM history_position WHERE day BETWEEN ? AND ? ORDER BY day,asset_id,account_id", bounds)]
            result["cash"] = [dict(row) for row in connection.execute(
                "SELECT day," + ",".join(CASH_COLUMNS) + " FROM history_cash WHERE day BETWEEN ? AND ? ORDER BY day,account_label,cash_asset_label", bounds)]
        return result
    except sqlite3.Error:
        _abort("portfolio_history_store_invalid")
    finally:
        connection.close()


def asset_price_series_v1(data_space_path: str | Path, last_day: str | None = None, context: Any = None) -> dict[str, dict[str, list[str]]]:
    """Der Kurs je Asset und Tag in Euro aus der Marktbewertung, unabhaengig vom Bestand (#526).

    Die Tageshistorie fuehrt je Asset nur Tage mit Bestand. Bewertet ist aber auch die Zeit davor, danach und dazwischen, dazu beobachtete, nie gehaltene Assets.
    Die Analyse zeichnet den Kurs dort gestrichelt: Er ist dann kein Hebel des Vermoegens.

    Je Asset und Tag gilt derselbe Bereich wie im Snapshot und in der Tageshistorie (`_valued_all`); Tage ohne Wert fehlen.
    Nur Kursreihen aus der Marktbewertung - eigene Bewertung und Handelswert gibt es ohne Bestand nicht. Schreibt nichts.

    Die Reihe dient der Anzeige: acht gueltige Stellen statt des exakten Bruchs (bis 37 Stellen). Das spart Platz, und die Teildateien entstehen mit jedem Tag neu. Kleinstkurse (Krypto-Token) bleiben so genau wie grosse."""
    data_space = Path(data_space_path)
    market = freshness_module.market_inputs_v1(data_space, None)
    valued, _ = _valued_all(data_space, market, None if context is None else split_price_adjuster_v1(data_space, context))
    result: dict[str, dict[str, list[str]]] = {}
    for day in sorted(valued):
        if last_day is not None and day > last_day:
            break
        for asset_id, value in valued[day].items():
            unit = value.get("target_decimal")
            if unit is None:
                continue
            series = result.setdefault(asset_id, {"day": [], "unit_value": []})
            series["day"].append(day)
            series["unit_value"].append(_display_price(unit))
    return result


def _display_price(text: str) -> str:
    """Acht gueltige Stellen, ohne Exponent und ohne Nullen am Ende."""
    value = Decimal(text)
    if value == 0:
        return "0"
    rounded = value.quantize(Decimal(1).scaleb(value.adjusted() - 7), rounding=ROUND_HALF_EVEN)
    shown = format(rounded, "f")
    return shown.rstrip("0").rstrip(".") if "." in shown else shown


__all__ = [
    "AREA", "ALGORITHM", "FAILURE_CODES", "PortfolioHistoryV1Error", "STORE", "asset_price_series_v1", "portfolio_history_v1_error_codes",
    "read_portfolio_history_v1", "update_portfolio_history_v1", "verify_portfolio_history_v1",
]
