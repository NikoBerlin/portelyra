"""Tagesfrischer Marktwert ueber alle Assets - in einem Vorgang statt je Asset.

Der Sammellauf geht je Asset durch die ganze Kette: planen, pruefen, bewerten,
abschliessen. Das kostete mehrere Sekunden je Asset, und
davon war nur ein Bruchteil Rechnen. Fuer einen Zwischenstand ist das der
falsche Weg.

Dieser Vorgang nimmt die Abkuerzung: Er liest die Bereiche aus dem
Bewertungsstand, holt die Kurse parallel, rechnet je Asset einen Schritt und
schreibt eine Zeile. Die Netzzeit bleibt uebrig; gleichzeitige
Abrufe verkuerzen sie.

Was hier entsteht, ist fluechtig: Ein Zwischenstand der laufenden Sitzung ist
kein Tagesschluss. Er wird bei jeder neuen Anforderung ueberschrieben, geht
nicht in den Kursspeicher und traegt keinen versiegelten Einzelbeleg. Seine
Zeile nennt Quelle, Zeitpunkt und Herkunft; das ist die angemessene Pruefetiefe
fuer einen Anzeigewert (Entscheidung 26.09.2026, #283).
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
import json
import sqlite3

from migrations.reference.asset_valuation_facts_v1 import (
    asset_master_v1,
    provider_mapping_v1,
    trade_unit_value_v1,
    why_no_market_value_v1,
)
from migrations.reference import price_provider_plugins_v1 as price_providers
from workers.reference.portfolio_snapshot_freshness_v1 import current_symbols_v1, preferred_scope_refs_v1, scope_windows_v1
from migrations.reference.desktop_provider_probe_v1 import PROVIDER_ID, _default_transport
from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1, exact_decimal_v1
from migrations.reference.fx_history_v1 import _fraction_from_decimal
from migrations.reference import market_valuation_state_v1 as state
from workers.reference.semantic_realized_fifo_v2 import _decimal_or_none

DEFAULT_PARALLEL_REQUESTS = 8
FAILURE_CODES = frozenset({
    "desktop_intraday_snapshot_input_invalid",
    "desktop_intraday_snapshot_state_required",
    "desktop_intraday_snapshot_confirmation_required",
})


class DesktopIntradaySnapshotBlocked(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("desktop_intraday_snapshot_error_unregistered")
        self.code = code
        super().__init__(code)


def desktop_intraday_snapshot_error_codes_v1() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise DesktopIntradaySnapshotBlocked(code)


def _utc(value: str) -> str:
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        _abort("desktop_intraday_snapshot_input_invalid")
    return value


# Die beiden Funktionen lesen und schreiben den alten Ort im Bewertungsstand (bis rc.399). Gelesen und gesetzt wird seit #554 ueber
# die Nutzereinstellungen (user_settings_v1.market_settings_v1 / set_market_setting_v1).
def read_parallel_request_count_v1(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT parallel_request_count FROM snapshot_setting WHERE singleton_id = 1"
    ).fetchone()
    return DEFAULT_PARALLEL_REQUESTS if row is None else int(row[0])


def write_parallel_request_count_v1(connection: sqlite3.Connection, value: int, updated_at_utc: str) -> int:
    """Wie viele Abrufe gleichzeitig laufen duerfen.

    Die Arbeit wartet auf das Netz, nicht auf die CPU - mehr als die Quelle
    vertraegt macht den Snapshot langsamer, nicht schneller.
    """
    if type(value) is not int or not 1 <= value <= 32:
        _abort("desktop_intraday_snapshot_input_invalid")
    _utc(updated_at_utc)
    connection.execute(
        "INSERT INTO snapshot_setting (singleton_id, parallel_request_count, updated_at_utc) VALUES (1,?,?) "
        "ON CONFLICT(singleton_id) DO UPDATE SET "
        "parallel_request_count = excluded.parallel_request_count, updated_at_utc = excluded.updated_at_utc",
        (value, updated_at_utc),
    )
    return value


def _parallel_requests(data_space_path: str | Path, context: Mapping[str, str], now: str) -> int:
    from migrations.reference import user_settings_v1 as user_settings  # noqa: PLC0415
    try:
        owner = user_settings.owner_settings_context_v1(context)
        user_settings.adopt_market_settings_v1(data_space_path, owner, now)
        return user_settings.market_settings_v1(data_space_path, owner)["parallel_request_count"]
    except user_settings.UserSettingsV1Error:
        _abort("desktop_intraday_snapshot_input_invalid")
    return DEFAULT_PARALLEL_REQUESTS


STATE_AREA = "market-valuation-state-v1"


def state_path_for(data_space_path: str | Path) -> Path:
    return Path(data_space_path) / STATE_AREA / "valuation-state.sqlite"


def _holdings(data_space_path: str | Path, context: Mapping[str, str]) -> dict[str, str]:
    """Die gehaltenen Mengen je Asset aus dem FIFO-Stand.

    Dessen Positionen tragen dieselbe kanonische Assetkennung wie die Bereiche des
    Bewertungsstands; ein Asset kann in mehreren FIFO-Welten liegen, seine Mengen
    werden deshalb summiert. Fehlt der Stand, bleibt die Menge offen - der
    Snapshot zeigt dann Kurse ohne Marktwert, statt zu raten.
    """
    try:
        from migrations.reference.desktop_product_asset_activity_v1 import (
            DesktopProductAssetActivityContextV1,
        )
        from workers.reference.asset_activity_realized_state_v2 import (
            read_asset_activity_realized_state_v2,
        )
        value = read_asset_activity_realized_state_v2(
            data_space_path,
            DesktopProductAssetActivityContextV1(context["tenant_id"], context["user_id"],
                                                 context["data_space_id"], "desktop_owner", "desktop_owner"),
        )
    except Exception:
        return {}
    if value.get("status") == "absent":
        return {}
    totals: dict[str, Fraction] = {}
    basis: dict[str, Fraction | None] = {}
    average: dict[str, str | None] = {}
    for row in value.get("positions", ()):
        quantity = row.get("remaining_quantity_decimal")
        if not isinstance(quantity, str):
            continue
        try:
            amount = exact_amount_v1(quantity)
        except Exception:
            continue
        asset = row["asset_ref"]
        totals[asset] = totals.get(asset, Fraction(0)) + amount
        # Die Basis eines Assets kann ueber mehrere FIFO-Welten verteilt sein;
        # fehlt sie in einer, bleibt sie fuer das Asset insgesamt offen.
        exact = exact_decimal_v1(row.get("remaining_fifo_basis"))
        if asset not in basis:
            basis[asset] = Fraction(0)
        if exact is None or basis[asset] is None:
            basis[asset] = None
        else:
            basis[asset] = basis[asset] + exact_amount_v1(exact)
        if average.get(asset) is None:
            average[asset] = exact_decimal_v1(row.get("cost_average"))
    return {key: {"quantity": amount_text_v1(value),
                  "cost_basis": None if basis.get(key) is None else amount_text_v1(basis[key]),
                  "cost_average": average.get(key)}
            for key, value in totals.items() if value != 0}


def _scopes(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    cursor = connection.execute(
        "SELECT scope_ref, asset_id, listing_ref, provider_symbol, quote_currency, pair_ref, direction "
        "FROM valuation_scope ORDER BY scope_ref"
    )
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _last_close(connection: sqlite3.Connection, scope_ref: str) -> dict[str, Any] | None:
    """Der juengste bewertete Tag des Bereichs - der Rueckfall, wenn der Abruf misslingt."""
    row = connection.execute(
        "SELECT trading_date, effective_price, fx_rate, target_decimal, target_numerator, target_denominator "
        "FROM valuation_day WHERE scope_ref = ? AND target_decimal IS NOT NULL "
        "ORDER BY trading_date DESC LIMIT 1",
        (scope_ref,),
    ).fetchone()
    if row is None:
        return None
    return {"trading_date": row[0], "effective_price": row[1], "fx_rate": row[2],
            "target_decimal": row[3], "target_numerator": row[4], "target_denominator": row[5]}


def _last_effective_rate(connection: sqlite3.Connection, pair_ref: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT rate_date, rate_decimal FROM fx_effective_day WHERE pair_ref = ? AND rate_decimal IS NOT NULL "
        "ORDER BY rate_date DESC LIMIT 1",
        (pair_ref,),
    ).fetchone()
    return None if row is None else {"rate_date": row[0], "rate_decimal": row[1]}


class _QuoteBlocked(Exception):
    def __init__(self, status: str):
        self.status = status
        super().__init__(status)


def _scope_providers(data_space_path: str | Path, scopes: list[dict[str, Any]]) -> dict[str, str | None]:
    """Je Bereich der Anbieter seiner Kurszuordnung (gleiches Symbol beim selben Asset, rc.394). Ein Bereich ohne passende Zuordnung
    stammt aus der Zeit vor rc.394, als es nur Yahoo gab; fuehren zwei Anbieter dasselbe Symbol, ist er nicht eindeutig (None)."""
    from migrations.reference.asset_valuation_timeline_v1 import mapping_symbols_v1
    symbols = mapping_symbols_v1(data_space_path)
    result: dict[str, str | None] = {}
    for scope in scopes:
        found = sorted(provider for provider, symbol in symbols.get(scope["asset_id"], {}).items() if symbol == scope["provider_symbol"])
        result[scope["scope_ref"]] = found[0] if len(found) == 1 else (PROVIDER_ID if not found else None)
    return result


def _provider_transport(data_space_path: str | Path, context: Mapping[str, str], provider_id: str) -> Callable[..., Any]:
    """Abruf eines anderen Anbieters als Yahoo ueber den gemeinsamen Weg des Kerns (Zugang, Kosten)."""
    from migrations.reference import plugin_credentials_v1 as credentials
    from migrations.reference import price_provider_costs_v1 as costs

    def fetch(host: str, target: str, headers: dict[str, str], timeout: int, limit: int) -> dict[str, Any]:
        try:
            return credentials.provider_get_v1(data_space_path, {**context, "actor_id": "market_worker", "role": "market_worker"},
                                               provider_id, {"host": host, "target": target}, headers, origin="interactive")
        except credentials.PluginCredentialsV1Error as error:
            raise _QuoteBlocked("credential_unavailable") from error
        except costs.PriceProviderCostsV1Error as error:
            raise _QuoteBlocked("cost_limit") from error
    return fetch


def _quote(symbol: str, transport: Callable[..., Any], clock: Callable[[], datetime], provider_id: str = PROVIDER_ID) -> dict[str, Any]:
    """Ein Kurs der laufenden Sitzung, sonst der juengste Tagesbalken der Antwort, sonst der Kurs aus den Kopfdaten. Anfrage und
    Auswertung liegen seit rc.382 im Kursanbieter-Plugin (#495), seit rc.394 in dem der Zuordnung; abgerufen wird hier."""
    try:
        request = price_providers.build_request_v1(provider_id, "quote", {"provider_symbol": symbol})
        response = transport(request["host"], request["target"],
                             {"Accept": "application/json", "Accept-Encoding": "identity",
                              "Connection": "close", "User-Agent": "Portelyra/0.2 Intraday-Snapshot"},
                             15, 1_048_576)
    except _QuoteBlocked as error:
        return {"status": error.status}
    except Exception:
        return {"status": "transport_failed"}
    if not isinstance(response, dict) or response.get("status") != 200:
        return {"status": "source_rejected", "http_status": (response or {}).get("status")}
    completed = clock().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    body = response.get("body")
    headers = response.get("headers") if isinstance(response.get("headers"), dict) else {}
    content_type = headers.get("content-type")
    if not isinstance(body, bytes):
        return {"status": "response_invalid"}
    try:
        outcome = price_providers.parse_response_v1(
            provider_id, "quote", {"provider_symbol": symbol, "end_date": completed[:10]},
            {"status": 200, "content_type": content_type if isinstance(content_type, str) else None, "body": body})
    except price_providers.PriceProviderBlocked:
        return {"status": "response_invalid"}
    if outcome["outcome"] == "ok":
        return {"status": "ok", **outcome["quote"]}
    return {"status": "no_observation" if outcome["outcome"] == "no_observation" else "response_invalid"}


def _exact(native: str, rate: str | None) -> tuple[str, str, str] | None:
    try:
        value = _fraction_from_decimal(native)
        if rate is not None:
            factor = _fraction_from_decimal(rate)
            if factor <= 0:
                return None
            value = value * factor
    except Exception:
        return None
    return _decimal_or_none(value), str(value.numerator), str(value.denominator)


@price_providers.within_price_provider_session
def snapshot_intraday_v1(
    data_space_path: str | Path, context: Mapping[str, str], confirmed: bool, requested_at_utc: str, *,
    transport: Callable[..., Any] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    parallel_request_count: int | None = None,
) -> dict[str, Any]:
    """Holt die Kurse aller Bereiche und schreibt je Bereich eine Zeile."""
    if confirmed is not True:
        _abort("desktop_intraday_snapshot_confirmation_required")
    _utc(requested_at_utc)
    path = state_path_for(data_space_path)
    if not path.is_file():
        _abort("desktop_intraday_snapshot_state_required")
    connection = state.open_market_valuation_state_v1(path, context)
    try:
        scopes = _scopes(connection)
        if not scopes:
            _abort("desktop_intraday_snapshot_state_required")
        # Je Asset nur der Bereich, der heute gilt (#474): Nach einem Symbol- oder Anbieterwechsel holte die Momentaufnahme bis
        # rc.384 auch das alte Symbol, und welcher Wert galt, war Zufall.
        preferred = set(preferred_scope_refs_v1(scope_windows_v1(connection), current_symbols_v1(Path(data_space_path))).values())
        scopes = [scope for scope in scopes if scope["scope_ref"] in preferred]
        # Seit #554 in den Nutzereinstellungen (der Bewertungsstand ist ableitbar); ein alter Wert aus dem Stand wird einmal uebernommen.
        workers = parallel_request_count if parallel_request_count is not None else _parallel_requests(data_space_path, context, requested_at_utc)
        if type(workers) is not int or not 1 <= workers <= 32:
            _abort("desktop_intraday_snapshot_input_invalid")
        # Je Bereich der Anbieter seiner Zuordnung (rc.394). Gemischt wird nicht: Hat der Anbieter keinen Momentkurs oder ist er nicht
        # eindeutig, gilt der juengste Schlusskurs des Bereichs, ausdruecklich gekennzeichnet.
        providers = _scope_providers(data_space_path, scopes)
        quotable = {scope["scope_ref"] for scope in scopes if providers[scope["scope_ref"]] is not None
                    and price_providers.provider_spec_v1(providers[scope["scope_ref"]]) is not None
                    and "quote" in price_providers.provider_spec_v1(providers[scope["scope_ref"]]).operations}
        keys = sorted({(providers[scope["scope_ref"]], scope["provider_symbol"]) for scope in scopes if scope["scope_ref"] in quotable})
        pairs = sorted({scope["pair_ref"] for scope in scopes if scope["pair_ref"]})
        # Das Waehrungspaar einmal, nicht je Asset - derselbe Multiplikator.
        pair_symbol = {}
        for pair_ref in pairs:
            currency = next(s["quote_currency"] for s in scopes if s["pair_ref"] == pair_ref)
            pair_symbol[pair_ref] = price_providers.fx_symbol_v1(PROVIDER_ID, currency, "EUR")
        # Wechselkurse kommen wie bisher von Yahoo.
        wanted = keys + [(PROVIDER_ID, pair_symbol[p]) for p in pairs]

        def ask(key: tuple[str, str]) -> dict[str, Any]:
            provider_id, symbol = key
            if transport is not None:
                chosen = transport
            elif provider_id == PROVIDER_ID:
                chosen = _default_transport
            else:
                chosen = _provider_transport(data_space_path, context, provider_id)
            return _quote(symbol, chosen, clock, provider_id)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            fetched = dict(zip(wanted, pool.map(ask, wanted)))
        rows = []
        for scope in scopes:
            provider_id = providers[scope["scope_ref"]]
            if scope["scope_ref"] not in quotable:
                quote = {"status": "provider_ambiguous" if provider_id is None else "provider_without_quote"}
            else:
                quote = fetched.get((provider_id, scope["provider_symbol"]), {"status": "transport_failed"})
            rate_quote = None if scope["pair_ref"] is None else fetched.get((PROVIDER_ID, pair_symbol[scope["pair_ref"]]), {})
            note = None
            if quote.get("status") == "ok" and quote.get("currency") == scope["quote_currency"]:
                native = quote["decimal"]
                basis, observed, as_of = "intraday", quote["observed_at_utc"], quote["as_of_date"]
                if scope["pair_ref"] is None:
                    rate, fx_basis = None, "identity"
                elif rate_quote.get("status") == "ok":
                    rate, fx_basis = rate_quote["decimal"], "intraday"
                else:
                    last = _last_effective_rate(connection, scope["pair_ref"])
                    rate = None if last is None else last["rate_decimal"]
                    fx_basis = "last_close" if rate else "unavailable"
                    note = "Wechselkurs nicht abrufbar: " + str(rate_quote.get("status", "unbekannt"))
                if scope["direction"] == "inverse" and rate is not None:
                    rate = amount_text_v1(1 / _fraction_from_decimal(rate))
                exact = None if (scope["pair_ref"] is not None and rate is None) else _exact(native, rate)
            else:
                # Rueckfall: der juengste bewertete Tag aus dem Stand, ausdruecklich
                # als solcher gekennzeichnet.
                note = "Abruf misslungen: " + str(quote.get("status", "unbekannt"))
                if quote.get("status") == "ok":
                    note = "Waehrung der Quelle weicht ab: " + str(quote.get("currency"))
                elif quote.get("status") == "provider_without_quote":
                    note = "Kursanbieter ohne Momentkurs: " + str(provider_id)
                elif quote.get("status") == "provider_ambiguous":
                    note = "Kursanbieter nicht eindeutig: Symbol bei zwei Anbietern"
                last = _last_close(connection, scope["scope_ref"])
                if last is None:
                    rows.append((scope["scope_ref"], requested_at_utc, "unavailable", None, None, None,
                                 scope["quote_currency"], None, "unavailable", None, None, None, note))
                    continue
                rows.append((scope["scope_ref"], requested_at_utc, "last_close", None, last["trading_date"],
                             last["effective_price"], scope["quote_currency"], last["fx_rate"],
                             "identity" if scope["pair_ref"] is None else "last_close",
                             last["target_decimal"], last["target_numerator"], last["target_denominator"], note))
                continue
            if exact is None:
                rows.append((scope["scope_ref"], requested_at_utc, "unavailable", observed, as_of, native,
                             scope["quote_currency"], rate, fx_basis, None, None, None,
                             note or "Umrechnung nicht moeglich"))
                continue
            rows.append((scope["scope_ref"], requested_at_utc, basis, observed, as_of, native,
                         scope["quote_currency"], rate, fx_basis, exact[0], exact[1], exact[2], note))
        # Zeilen von Bereichen, die nicht mehr gelten (alter Bereich nach einem Wechsel), fallen weg - sonst laesen die Leser
        # neben dem frischen Kurs einen alten aus einem frueheren Lauf.
        kept = sorted({row[0] for row in rows})
        connection.execute("DELETE FROM intraday_quote WHERE scope_ref NOT IN (" + ",".join("?" * len(kept)) + ")", kept)
        connection.executemany(
            "INSERT INTO intraday_quote VALUES (" + ",".join("?" * 13) + ") "
            "ON CONFLICT(scope_ref) DO UPDATE SET requested_at_utc=excluded.requested_at_utc, "
            "basis=excluded.basis, observed_at_utc=excluded.observed_at_utc, as_of_date=excluded.as_of_date, "
            "native_decimal=excluded.native_decimal, native_currency=excluded.native_currency, "
            "fx_rate=excluded.fx_rate, fx_basis=excluded.fx_basis, target_decimal=excluded.target_decimal, "
            "target_numerator=excluded.target_numerator, target_denominator=excluded.target_denominator, "
            "note=excluded.note",
            rows,
        )
        connection.commit()
        return read_intraday_snapshot_v1(data_space_path, context, connection=connection)
    finally:
        connection.close()


def read_intraday_snapshot_v1(
    data_space_path: str | Path, context: Mapping[str, str], *,
    connection: sqlite3.Connection | None = None
) -> dict[str, Any]:
    """Was gespeichert ist - ohne Abruf. Ohne neue Anforderung gilt der alte Stand."""
    own = connection is None
    path = state_path_for(data_space_path)
    if own:
        if not path.is_file():
            return {"contract_version": "desktop_intraday_snapshot_v1", "status": "absent", "rows": [],
                    "asset_count": 0, "valued_count": 0, "intraday_count": 0, "carried_count": 0,
                    "unavailable_count": 0, "held_asset_count": 0, "held_without_scope_count": 0,
                    "market_value_complete": False, "total_market_value_eur": None,
                    "total_unrealised_eur": None, "unrealised_unknown_count": 0,
                    "unrealised_before_fees_and_tax": True,
                    "total_trade_derived_value_eur": None, "trade_derived_rows": [],
                    "requested_at_utc": None, "provider_access": False,
                    "canonical_write": False, "market_history_write": False}
        connection = state.open_market_valuation_state_v1(path, context)
    try:
        cursor = connection.execute(
            "SELECT q.scope_ref, s.asset_id, s.provider_symbol, q.requested_at_utc, q.basis, "
            "q.observed_at_utc, q.as_of_date, q.native_decimal, q.native_currency, q.fx_rate, q.fx_basis, "
            "q.target_decimal, q.note FROM intraday_quote q JOIN valuation_scope s ON s.scope_ref = q.scope_ref "
            "ORDER BY s.asset_id"
        )
        names = [column[0] for column in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    finally:
        if own:
            connection.close()
    # Nur der juengste Lauf zaehlt; eine Zeile aus einem frueheren Lauf (etwa eines inzwischen alten Bereichs) gehoert nicht dazu.
    latest = max((row["requested_at_utc"] for row in rows if row["requested_at_utc"]), default=None)
    rows = [row for row in rows if row["requested_at_utc"] == latest]
    # Kurs mal gehaltener Menge: Der Marktwert ist die Frage, nicht der Kurs.
    holdings = _holdings(data_space_path, context)
    master = asset_master_v1(data_space_path, context)
    mappings = provider_mapping_v1(data_space_path)
    covered = {row["asset_id"] for row in rows}
    # Ein gehaltenes Asset ohne Bewertungsbereich faellt sonst still aus der
    # Summe - etwa weil es keine Notierung hat. Es wird deshalb getrennt
    # ausgewiesen, nicht weggelassen (26.09.2026, #283).
    missing = sorted(asset for asset in holdings if asset not in covered)
    as_of = (rows[0]["requested_at_utc"][:10] if rows else "2100-01-01")
    total = Fraction(0)
    unrealised = Fraction(0)
    unrealised_unknown = 0
    complete = True
    for row in rows:
        row.update(master.get(row["asset_id"]) or
                   {"asset_name": None, "asset_type": None, "valuation_method": None})
        holding = holdings.get(row["asset_id"]) or {}
        quantity = holding.get("quantity")
        row["quantity_decimal"] = quantity
        row["cost_basis_decimal"] = holding.get("cost_basis")
        row["market_value_decimal"] = None
        row["unrealised_decimal"] = None
        if quantity is None or row["target_decimal"] is None:
            if quantity is not None:
                complete = False
            continue
        try:
            value = exact_amount_v1(quantity) * exact_amount_v1(row["target_decimal"])
        except Exception:
            complete = False
            continue
        row["market_value_decimal"] = amount_text_v1(value)
        total = total + value
        basis = row["cost_basis_decimal"]
        if basis is None:
            # Eine fehlende Basis darf nicht die ganze Summe verschlucken; sie
            # wird gezaehlt und benannt (26.09.2026, #283).
            unrealised_unknown = unrealised_unknown + 1
            continue
        gain = value - exact_amount_v1(basis)
        row["unrealised_decimal"] = amount_text_v1(gain)
        unrealised = unrealised + gain
    # Aus Buchungen hergeleitet: eigene Liste, eigene Summe. Diese Werte sagen,
    # was gezahlt wurde, nicht was der Markt heute bietet.
    derived = []
    derived_total = Fraction(0)
    for asset in missing:
        holding = holdings[asset]
        unit, how = trade_unit_value_v1(data_space_path, context, asset, holding, as_of)
        facts = master.get(asset) or {"asset_name": None, "asset_type": None, "valuation_method": None}
        entry = {"asset_id": asset, **facts,
                 "reason": why_no_market_value_v1(facts, mappings.get(asset)),
                 "quantity_decimal": holding["quantity"],
                 "cost_basis_decimal": holding.get("cost_basis"), "unit_value_decimal": unit,
                 "derived_value_decimal": None, "unrealised_decimal": None, "note": how}
        if unit is not None:
            value = exact_amount_v1(holding["quantity"]) * exact_amount_v1(unit)
            entry["derived_value_decimal"] = amount_text_v1(value)
            derived_total = derived_total + value
            if holding.get("cost_basis") is not None:
                entry["unrealised_decimal"] = amount_text_v1(
                    value - exact_amount_v1(holding["cost_basis"]))
        else:
            complete = False
        derived.append(entry)
    return {
        "contract_version": "desktop_intraday_snapshot_v1",
        "status": "absent" if not rows else "available",
        "requested_at_utc": rows[0]["requested_at_utc"] if rows else None,
        "asset_count": len(rows),
        "valued_count": sum(row["target_decimal"] is not None for row in rows),
        "intraday_count": sum(row["basis"] == "intraday" for row in rows),
        "carried_count": sum(row["basis"] == "last_close" for row in rows),
        "unavailable_count": sum(row["basis"] == "unavailable" for row in rows),
        "held_asset_count": sum(row["quantity_decimal"] is not None for row in rows),
        "held_without_scope_count": len(missing),
        "market_value_complete": complete and bool(rows),
        "total_market_value_eur": amount_text_v1(total) if rows else None,
        # Brutto, vor Gebuehren und Steuern. Die geprüfte Groesse liefert die
        # Unrealized Valuation des abgeschlossenen Laufs; diese hier ist ein
        # lebender Hinweis, kein Abschluss.
        "total_unrealised_eur": amount_text_v1(unrealised) if rows else None,
        "unrealised_unknown_count": unrealised_unknown,
        "unrealised_before_fees_and_tax": True,
        "total_trade_derived_value_eur": amount_text_v1(derived_total) if derived else None,
        "trade_derived_rows": derived,
        "rows": rows,
        "provider_access": False, "canonical_write": False, "market_history_write": False,
    }


__all__ = [
    "DEFAULT_PARALLEL_REQUESTS",
    "DesktopIntradaySnapshotBlocked",
    "desktop_intraday_snapshot_error_codes_v1",
    "read_intraday_snapshot_v1",
    "state_path_for",
    "read_parallel_request_count_v1",
    "snapshot_intraday_v1",
    "write_parallel_request_count_v1",
]
