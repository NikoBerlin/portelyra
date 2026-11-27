"""Portfolio-Stichtagsbild aus dem Bewertungsstand. Reine Abfrage.

Der Wert eines Tages steht bereits im Bewertungsstand; hier wird er gelesen,
nicht erneut hergeleitet. Kein Provider, keine Rechnung ueber die Multiplikation
mit dem Bestand hinaus, kein Schreiben (#373, Schritt 2, 26.09.2026).

Was fehlt, erscheint als Fehlendes: Eine Quellluecke wird nicht zu null, ein
gehaltenes Asset ohne Bewertungsbereich faellt nicht still aus der Summe, und
ein aus Buchungen hergeleiteter Wert steht getrennt - er sagt, was gezahlt
wurde, nicht was der Markt am Stichtag bot.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from migrations.reference.asset_valuation_facts_v1 import (
    OWNER_CHOICE_METHODS,
    asset_master_v1,
    owner_valuation_reason_text_v1,
    owner_valuation_v1,
    provider_ids_v1,
    provider_mapping_v1,
    trade_unit_value_v1,
    why_no_market_value_v1,
)
from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1
from workers.reference.portfolio_snapshot_freshness_v1 import (
    DERIVED_CASH_STATUSES,
    PortfolioSnapshotFreshnessV1Error,
    STATE_AREA,
    STATE_NAME,
    current_symbols_v1,
    effective_scope_refs_v1,
    holdings_as_of_v1,
    read_portfolio_snapshot_freshness_v1,
    scope_order_v1,
)
from workers.reference.stock_split_prices_v1 import split_price_adjuster_v1

TARGET_CURRENCY = "EUR"


class PortfolioSnapshotProjectionV1Error(RuntimeError):
    CODES = frozenset({
        "portfolio_snapshot_projection_context_invalid",
        "portfolio_snapshot_projection_input_invalid",
        "portfolio_snapshot_projection_evidence_invalid",
        "portfolio_snapshot_projection_boundary_failed",
    })

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("portfolio_snapshot_projection_error_code_unregistered")
        self.code = code
        super().__init__(code)


def portfolio_snapshot_projection_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(PortfolioSnapshotProjectionV1Error.CODES))


def _abort(code: str) -> None:
    raise PortfolioSnapshotProjectionV1Error(code)


def _exact_unit(row: dict[str, Any]) -> Fraction | None:
    """Der EUR-Wert je Einheit am Stichtag - exakt, nicht gerundet.

    Der Stand haelt ihn als Dezimalzahl, wo das geht, und sonst als Bruch aus
    Zaehler und Nenner. Nur die Dezimalform zu lesen verlore jeden Wert, der
    nicht endlich darstellbar ist (#283, 26.09.2026).
    """
    if row.get("target_numerator") is not None and row.get("target_denominator") is not None:
        return Fraction(int(row["target_numerator"]), int(row["target_denominator"]))
    if row.get("target_decimal") is not None:
        return exact_amount_v1(row["target_decimal"])
    return None


def project_portfolio_snapshot_v1(
    data_space_path: str | Path,
    context_value: Any,
    as_of_date: str,
    canonical_path: str | Path | None = None,
    *,
    price_source: Any = None,
) -> dict[str, Any]:
    """Das Stichtagsbild samt Frische je Ebene. Nichts wird geschrieben.

    Ohne 'price_source' stammen die Kurse aus den Bewertungstagen des
    Stichtags. Mit ihr rechnet dieselbe Projektion ein fluides Bild: Bestand,
    eigene Bewertung, Eigentuemerwahl, Cash und Summen bleiben, wie sie sind -
    verschieden ist allein, woher der Preis einer ueber den Markt bewerteten
    Position kommt. Die Quelle liefert 'market_levels', 'valued' und
    'undated_reason'; siehe portfolio_intraday_projection_v1.
    """
    try:
        if not isinstance(context_value, DesktopProductAssetActivityContextV1):
            _abort("portfolio_snapshot_projection_context_invalid")
        data_space = Path(data_space_path)
        try:
            freshness = read_portfolio_snapshot_freshness_v1(
                data_space, context_value, as_of_date, canonical_path,
                market_levels=None if price_source is None else price_source.market_levels)
        except PortfolioSnapshotFreshnessV1Error as error:
            if error.code == "portfolio_snapshot_freshness_input_invalid":
                _abort("portfolio_snapshot_projection_input_invalid")
            _abort("portfolio_snapshot_projection_evidence_invalid")

        context = {"tenant_id": context_value.tenant_id, "user_id": context_value.user_id,
                   "data_space_id": context_value.data_space_id}
        holdings = holdings_as_of_v1(data_space, context_value, freshness["as_of_date"])
        master = asset_master_v1(data_space, context)
        mappings = provider_mapping_v1(data_space)

        path = data_space / STATE_AREA / STATE_NAME
        valued: dict[str, dict[str, Any]] = {}
        scoped: set[str] = set()
        if price_source is not None:
            valued, scoped = price_source.valued(data_space, freshness["as_of_date"])
        elif path.is_file():
            valued, scoped = valued_day_v1(path, freshness["as_of_date"], split_price_adjuster_v1(data_space, context_value))
        projection = snapshot_day_v1(data_space, context, freshness, holdings, master, mappings, valued, scoped,
                                     undated_reason=None if price_source is None else price_source.undated_reason,
                                     observed=price_source is not None)
        _with_provider_ids(projection, provider_ids_v1(data_space), _timeline_of(data_space), freshness["as_of_date"])
        canonical = Path(canonical_path) if canonical_path is not None else data_space / "canonical.sqlite"
        return with_provisional_cash_v1(projection, data_space, context_value, canonical)
    except PortfolioSnapshotProjectionV1Error:
        raise
    except Exception:
        _abort("portfolio_snapshot_projection_boundary_failed")


def _with_provider_ids(projection: dict[str, Any], provider_ids: Mapping[str, str], timeline: Any = None, day: str | None = None) -> None:
    """Kursanbieter je bewerteter Position, nur zur Anzeige (rc.384, #495). Erst nach der gemeinsamen Schrittfunktion gesetzt:
    Rechnung und Tageshistorie bleiben unberuehrt. Positionen ohne Kurs vom Anbieter (eigene Bewertung) tragen keinen.
    Mit Bewertungs-Zeitleiste (rc.393) der Anbieter des Abschnitts, der den Stichtag traegt - die tatsaechliche Herkunft."""
    for row in projection.get("positions", []):
        provider = provider_ids.get(row.get("asset_id"))
        if timeline and day and timeline.has(row.get("asset_id")):
            segment = timeline.segment_on(row["asset_id"], day)
            provider = segment.provider_id if segment is not None and segment.method == "external_market" else None
        row["provider_id"] = provider if row.get("provider_symbol") else None


def with_provisional_cash_v1(projection: dict[str, Any], data_space: Path, context: DesktopProductAssetActivityContextV1,
                             canonical: Path, inputs: Any = None) -> dict[str, Any]:
    """Der vorlaeufige Cash-Stand (#539) neben dem amtlichen - nur Anzeige, nichts wird gebucht.

    Je Euro-Konto: amtlicher Saldo plus die Bewegungen nach seinem Datum plus die Abrechnungen seiner Depots ohne
    Auszugszeile (cash_settlement_v1). Der amtliche Saldo, die Summe und das Gesamtvermoegen bleiben, wie sie sind; die
    vorlaeufigen Werte stehen daneben und sind null, wo nichts offen ist. Laesst sich die Zuordnung nicht lesen, heisst der
    Stand "unavailable" - das Bild bleibt vollstaendig, nur ohne Schaetzung. Ohne Cash-Konten bleibt der Block unveraendert.
    `inputs` ersetzt im Test das Lesen (cash_view, ledger, accounts)."""
    from workers.reference.cash_settlement_v1 import cash_scope_v1, match_settlements_v1, provisional_cash_v1, read_accounts_v1, read_ledger_v1
    cash = projection["cash"]
    # Ohne Cash-Konten gibt es nichts zu schaetzen; der Block bleibt, wie er war (die Felder sind optional).
    if cash["status"] != "available" or not cash["accounts"]:
        return projection
    for account in cash["accounts"]:
        account.update(provisional_balance_decimal=None, provisional_settlement_count=0, provisional_movement_count=0,
                       provisional_unestimated_count=0)
    cash.update(provisional_status="none", provisional_account_count=0, provisional_settlement_count=0, provisional_movement_count=0,
                provisional_unestimated_account_count=0)
    totals = projection["totals"]
    totals.update(cash_provisional_balance_decimal=None, net_worth_provisional_decimal=None)
    try:
        if inputs is None:
            from migrations.reference.desktop_cash_coverage_v1 import read_desktop_cash_coverage_view_v1
            from migrations.reference.desktop_product_asset_activity_v1 import read_desktop_product_asset_activity_binding_v1
            binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
            ledger = read_ledger_v1(binding["ledger_path"]) if binding.get("status") == "available" and binding.get("ledger_path") else []
            cash_view, accounts = read_desktop_cash_coverage_view_v1(canonical, data_space, context), read_accounts_v1(canonical)
        else:
            cash_view, ledger, accounts = inputs
        matched = match_settlements_v1(cash_view, ledger, accounts, cash_scope_v1(accounts))
        found = provisional_cash_v1(cash["accounts"], matched, projection["as_of_date"])
    except Exception:
        cash["provisional_status"] = "unavailable"
        return projection
    estimated = {label: hit for label, hit in found["accounts"].items() if hit["provisional_balance_decimal"] is not None}
    for account in cash["accounts"]:
        hit = found["accounts"].get(account["account_label"])
        if hit is not None and account["currency"] == TARGET_CURRENCY and account["in_total"]:
            account.update(provisional_balance_decimal=hit["provisional_balance_decimal"], provisional_settlement_count=hit["settlement_count"],
                           provisional_movement_count=hit["movement_count"], provisional_unestimated_count=hit["unestimated_count"])
    cash["provisional_unestimated_account_count"] = len(found["accounts"]) - len(estimated)
    if not estimated:
        return projection
    cash.update(provisional_status="available", provisional_account_count=len(estimated),
                provisional_settlement_count=sum(hit["settlement_count"] for hit in estimated.values()),
                provisional_movement_count=sum(hit["movement_count"] for hit in estimated.values()))
    if totals.get("cash_balance_decimal") is not None:
        totals["cash_provisional_balance_decimal"] = amount_text_v1(exact_amount_v1(totals["cash_balance_decimal"]) + found["delta"])
    if totals.get("net_worth_decimal") is not None:
        totals["net_worth_provisional_decimal"] = amount_text_v1(exact_amount_v1(totals["net_worth_decimal"]) + found["delta"])
    return projection


VALUED_COLUMNS = ("s.asset_id,s.provider_symbol,s.quote_currency,d.status,d.valuation_status,"
                  "d.target_decimal,d.target_numerator,d.target_denominator,d.effective_price,"
                  "d.price_basis,d.price_source_date,d.price_age_days,d.fx_rate,d.fx_basis,"
                  "d.substitution_used")


def valued_day_v1(path: Path, as_of_date: str, adjuster: Any = None) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Die Bewertungstage eines Stichtags je Asset und die Assets mit Bewertungsbereich - gelesen, nicht hergeleitet."""
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
    except sqlite3.Error:
        _abort("portfolio_snapshot_projection_evidence_invalid")
    try:
        rows = [dict(row) for row in connection.execute(
            f"SELECT s.scope_ref AS scope_ref, {VALUED_COLUMNS} FROM valuation_scope s JOIN valuation_day d USING(scope_ref) "
            "WHERE d.trading_date=? ORDER BY s.asset_id, s.scope_ref", (as_of_date,))]
        scopes = [dict(row) for row in connection.execute(
            "SELECT s.scope_ref,s.asset_id,s.provider_symbol,w.valued_from_date,w.valued_through_date "
            "FROM valuation_scope s JOIN valuation_watermark w USING(scope_ref)")]
        scoped = {row[0] for row in connection.execute("SELECT asset_id FROM valuation_scope")}
    except sqlite3.Error:
        _abort("portfolio_snapshot_projection_evidence_invalid")
    finally:
        connection.close()
    # Je Asset der Bereich, der den Tag traegt - dieselbe Regel wie im Frische-Urteil (#474).
    effective = effective_scope_refs_v1(scope_order_v1(scopes, current_symbols_v1(path.parent.parent)), as_of_date)
    valued: dict[str, dict[str, Any]] = {}
    for row in rows:
        scope_ref = row.pop("scope_ref")
        if effective.get(row["asset_id"], scope_ref) == scope_ref:
            # Vor einem Split (#451) der Kurs je Stueck dieses Tages - wie in der Tageshistorie.
            valued[row["asset_id"]] = adjuster.adjust(row, scope_ref, as_of_date) if adjuster else row
    return valued, scoped


def _timeline_of(data_space: Path) -> Any:
    from migrations.reference.asset_valuation_timeline_v1 import timeline_v1
    return timeline_v1(data_space)


def snapshot_day_v1(data_space: Path, context: dict[str, Any], freshness: dict[str, Any], holdings: dict[str, dict[str, Any]],
                    master: dict[str, Any], mappings: dict[str, Any], valued: dict[str, dict[str, Any]], scoped: set[str],
                    *, undated_reason: str | None = None, observed: bool = False, facts: Any = None) -> dict[str, Any]:
    """Der Tageskern des Stichtagsbilds: Positionen, eigene Bewertung, Eigentuemerwahl, Cash und Summen eines Tages aus
    bereits gelesenen Eingaengen. Stichtags-Snapshot und Tageshistorie (#473) rechnen beide hiermit - dieselbe Regel,
    dieselben Zahlen. 'valued' ist je Asset nach asset_id geordnet (davon haengt der Umrechnungsfaktor je Waehrung ab).
    'facts' (ValuationFactsCacheV1) liefert eigene Bewertung und Handelswert aus einmal gelesenen Quellen; ohne sie wird je
    Aufruf frisch gelesen."""
    owner_valuation = (lambda asset, day: owner_valuation_v1(data_space, context, asset, day)) if facts is None else facts.owner_valuation
    trade_unit_value = (lambda asset, holding, day: trade_unit_value_v1(data_space, context, asset, holding, day)) if facts is None else facts.trade_unit_value
    if True:
        rows: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        market_total = Fraction(0)
        basis_total = Fraction(0)
        gain_total = Fraction(0)
        derived_total = Fraction(0)
        basis_unknown = 0
        owner_valued = 0
        complete = True


        # Der Umrechnungsfaktor je Kurswaehrung, wie ihn der Stand am Stichtag fuer
        # seine eigenen Positionen verwendet hat: Zielwert durch Kurs. So rechnet
        # eine eigene Bewertung in fremder Waehrung mit demselben Wechselkurs wie
        # die uebrigen Positionen dieser Waehrung - und ohne eigene Annahme ueber
        # dessen Richtung.
        conversion: dict[str, dict[str, Any]] = {TARGET_CURRENCY: {"factor": Fraction(1), "fx_rate": None, "fx_basis": None}}
        for day in valued.values():
            currency = day.get("quote_currency")
            unit_value = _exact_unit(day)
            if currency in conversion or unit_value is None or day.get("effective_price") is None:
                continue
            try:
                native = exact_amount_v1(day["effective_price"])
            except Exception:
                continue
            if native > 0:
                conversion[currency] = {"factor": unit_value / native, "fx_rate": day.get("fx_rate"), "fx_basis": day.get("fx_basis")}

        # Bewertungs-Zeitleiste (rc.393): Die Art des Abschnitts, der den Stichtag traegt, ersetzt die eine Art der Stammdaten.
        timeline = _timeline_of(data_space)
        for asset, holding in sorted(holdings.items()):
            facts = master.get(asset) or {"asset_name": None, "asset_type": None, "valuation_method": None}
            if timeline and timeline.has(asset):
                facts = {**facts, "valuation_method": timeline.method_on(asset, freshness["as_of_date"], facts.get("valuation_method"))}
            quantity = exact_amount_v1(holding["quantity"])
            basis = None if holding.get("cost_basis") is None else exact_amount_v1(holding["cost_basis"])
            day = valued.get(asset)
            unit = None if day is None else _exact_unit(day)
            owner_reason = None
            if (day is None or unit is None) and facts.get("valuation_method") == "manual":
                # Eigene Bewertung ist eine Bewertung: eigene Kursangabe zuerst,
                # sonst der letzte bestaetigte Trade-Stueckpreis. Die Position
                # zaehlt in die Summe und sagt, woher ihr Preis stammt und von
                # wann (Festlegung 11.10.2026). Vorher stand sie mit
                # einem hergeleiteten Wert neben der Summe.
                owner = owner_valuation(asset, freshness["as_of_date"])
                rate = conversion.get(owner.get("native_currency")) if owner["status"] == "valued" else None
                if owner["status"] != "valued":
                    owner_reason = owner["reason_code"]
                elif rate is None:
                    owner_reason = "owner_valuation_currency_without_rate"
                else:
                    unit = exact_amount_v1(owner["native_decimal"]) * rate["factor"]
                    value = quantity * unit
                    market_total = market_total + value
                    owner_valued += 1
                    entry = {"asset_id": asset, **facts,
                             "provider_symbol": None,
                             "native_currency": owner["native_currency"],
                             "native_decimal": owner["native_decimal"],
                             "fx_rate_decimal": rate["fx_rate"], "fx_basis": rate["fx_basis"],
                             "price_basis": owner["price_basis"], "price_source_date": owner["price_source_date"],
                             "price_age_days": (date.fromisoformat(freshness["as_of_date"])
                                                - date.fromisoformat(owner["price_source_date"])).days,
                             "substitution_used": False,
                             "valuation_status": "complete", "day_status": "owner_valuation",
                             "owner_valuation": True,
                             "quantity_decimal": holding["quantity"],
                             "unit_value_decimal": amount_text_v1(unit),
                             "market_value_decimal": amount_text_v1(value),
                             "cost_basis_decimal": holding.get("cost_basis"),
                             "unrealised_decimal": None}
                    if basis is None:
                        basis_unknown += 1
                    else:
                        basis_total = basis_total + basis
                        gain = value - basis
                        gain_total = gain_total + gain
                        entry["unrealised_decimal"] = amount_text_v1(gain)
                    rows.append(entry)
                    continue
                unit = None
            if day is None or unit is None:
                # Getrennt gehalten: Was der Eigentuemer ausgenommen hat, ist keine
                # Luecke; was ohne Wert blieb, macht die Summe unvollstaendig.
                unit_value, how = trade_unit_value(asset, holding, freshness["as_of_date"])
                # Ein Bereich besteht, nur der Stichtag fehlt: Das ist etwas
                # anderes als "nie abgerufen", und die Zeile muss es sagen,
                # sonst sucht man an der falschen Stelle (#373, 26.09.2026).
                undated = ("für den Stichtag kein bewerteter Kurstag im Bewertungsstand"
                           if undated_reason is None else undated_reason)
                reason = undated if asset in scoped else why_no_market_value_v1(facts, mappings.get(asset))
                if owner_reason == "owner_valuation_not_configured":
                    # #576: Der Stand nennt eigene Bewertung, das Asset ist aber auf Marktdaten eingerichtet (etwa ein Stand von vor der
                    # Umstellung). Dann fehlt der Marktkurs dieses Tages - das ist der Grund, nicht eine unlesbare eigene Bewertung.
                    reason = "Marktkurs dieses Tages fehlt: " + (undated if asset in scoped else why_no_market_value_v1(
                        {**facts, "valuation_method": "external_market"}, mappings.get(asset)))
                elif owner_reason is not None:
                    reason = "eigene Bewertung ohne Wert: " + owner_valuation_reason_text_v1(owner_reason)
                entry = {"asset_id": asset, **facts,
                         "reason": reason,
                         "quantity_decimal": holding["quantity"],
                         "cost_basis_decimal": holding.get("cost_basis"),
                         "unit_value_decimal": unit_value,
                         "derived_value_decimal": None, "unrealised_decimal": None, "note": how,
                         # 'transaction_only' fuehrt der Eigentuemer bewusst ohne
                         # Wert; bis 11.10.2026 galt es hier als Luecke. Eine
                         # eigene Bewertung, die keinen Wert ergibt, ist dagegen
                         # eine: Der Eigentuemer hat eine Bewertung gewaehlt, und
                         # sie fehlt.
                         "owner_excluded": facts.get("valuation_method") in OWNER_CHOICE_METHODS
                                           and owner_reason is None}
                if unit_value is not None:
                    value = quantity * exact_amount_v1(unit_value)
                    entry["derived_value_decimal"] = amount_text_v1(value)
                    derived_total = derived_total + value
                    if basis is not None:
                        entry["unrealised_decimal"] = amount_text_v1(value - basis)
                if not entry["owner_excluded"]:
                    complete = False
                excluded.append(entry)
                continue
            value = quantity * unit
            market_total = market_total + value
            entry = {"asset_id": asset, **facts,
                     "provider_symbol": day["provider_symbol"],
                     "native_currency": day["quote_currency"],
                     "native_decimal": day["effective_price"],
                     "fx_rate_decimal": day["fx_rate"], "fx_basis": day["fx_basis"],
                     "price_basis": day["price_basis"], "price_source_date": day["price_source_date"],
                     "price_age_days": day["price_age_days"],
                     "substitution_used": bool(day["substitution_used"]),
                     "valuation_status": day["valuation_status"], "day_status": day["status"],
                     "quantity_decimal": holding["quantity"],
                     "unit_value_decimal": amount_text_v1(unit),
                     "market_value_decimal": amount_text_v1(value),
                     "cost_basis_decimal": holding.get("cost_basis"),
                     "unrealised_decimal": None}
            if observed:
                # Wann die Quelle den Kurs beobachtet hat: Daran haengt, wie
                # aktuell ein fluides Bild wirklich ist.
                entry["price_observed_at_utc"] = day.get("price_observed_at_utc")
            if basis is None:
                basis_unknown += 1
            else:
                basis_total = basis_total + basis
                gain = value - basis
                gain_total = gain_total + gain
                entry["unrealised_decimal"] = amount_text_v1(gain)
            rows.append(entry)

        if freshness["overall_status"] != "complete":
            complete = False

        # Cash am Stichtag: je Konto der belegte Saldo mit seinem Datum, dazu die
        # Summe in der Zielwaehrung und das Gesamtvermoegen aus Marktwert plus
        # Cash. Ein Konto ohne Saldo steht benannt ausserhalb der Summe, ein
        # Saldo von vor dem Stichtag traegt sein Datum und wird als aelter
        # gekennzeichnet (Darstellung nach Festlegung 11.10.2026). Cash
        # bleibt nachrichtlich: Es macht den Snapshot nicht unvollstaendig.
        # Aus Bewegungen abgeleitete Salden zaehlen mit; ihr Anteil steht eigens
        # da, damit die Summe ohne ihn nachrechenbar bleibt.
        cash = freshness.pop("cash_as_of", None) or {"status": "absent", "accounts": []}
        freshness = dict(freshness)
        cash_total = Fraction(0)
        cash_derived_total = Fraction(0)
        cash_derived_count = 0
        counted = 0
        balance_dates: list[str] = []
        for account in cash["accounts"]:
            rate = conversion.get(account["currency"])
            if account["in_total"] and rate is None:
                account["in_total"] = False
                account["balance_status"] = "currency_without_rate"
            if account["in_total"]:
                value = exact_amount_v1(account["balance_decimal"]) * rate["factor"]
                account["balance_target_decimal"] = amount_text_v1(value)
                cash_total = cash_total + value
                counted += 1
                balance_dates.append(account["balance_date"])
                if account["balance_status"] in DERIVED_CASH_STATUSES:
                    cash_derived_total = cash_derived_total + value
                    cash_derived_count += 1
            else:
                account["balance_target_decimal"] = None
        cash_block = {
            "status": cash["status"],
            "accounts": cash["accounts"],
            "counted_account_count": counted,
            "derived_account_count": cash_derived_count,
            "uncounted_account_count": len(cash["accounts"]) - counted,
            "oldest_balance_date": min(balance_dates) if balance_dates else None,
            "newest_balance_date": max(balance_dates) if balance_dates else None,
            "dated_before_as_of": any(day < freshness["as_of_date"] for day in balance_dates),
        }
        return {
            "portfolio_snapshot_projection_version": 1,
            "as_of_date": freshness["as_of_date"],
            "target_currency": TARGET_CURRENCY,
            "freshness": freshness,
            "positions": rows,
            "excluded_positions": excluded,
            "cash": cash_block,
            "totals": {
                "market_value_decimal": amount_text_v1(market_total) if rows else None,
                # Nur die Basis der bewerteten Positionen; fehlt eine, sagt es die
                # Zahl darunter, statt die Summe stillschweigend zu verkleinern.
                "cost_basis_decimal": amount_text_v1(basis_total) if rows else None,
                "unrealised_decimal": amount_text_v1(gain_total) if rows else None,
                "trade_derived_value_decimal": amount_text_v1(derived_total) if excluded else None,
                # Cash nur, wo mindestens ein Konto einen Saldo traegt; das
                # Gesamtvermoegen nur, wo es Marktwert oder Cash gibt.
                "cash_balance_decimal": amount_text_v1(cash_total) if counted else None,
                # Der Teil davon, den kein Auszug bestaetigt.
                "cash_derived_balance_decimal": amount_text_v1(cash_derived_total) if cash_derived_count else None,
                "net_worth_decimal": amount_text_v1(market_total + cash_total) if (rows or counted) else None,
            },
            "counts": {
                "valued_position_count": len(rows),
                "excluded_position_count": len(excluded),
                "owner_excluded_count": sum(entry["owner_excluded"] for entry in excluded),
                "owner_valued_position_count": owner_valued,
                "cost_basis_unknown_count": basis_unknown,
                "held_asset_count": len(holdings),
            },
            "market_value_complete": complete and bool(rows),
            "unrealised_before_fees_and_tax": True,
            "provider_access": False, "network_access": False,
            "canonical_write": False, "market_history_write": False, "path_exposed": False,
        }


__all__ = [
    "PortfolioSnapshotProjectionV1Error",
    "portfolio_snapshot_projection_v1_error_codes",
    "project_portfolio_snapshot_v1",
    "snapshot_day_v1",
    "valued_day_v1",
    "with_provisional_cash_v1",
]
