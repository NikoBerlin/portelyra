"""Die Datenbasis veroeffentlichen (rc.314, #478 Stufe 2): Grundlagen fuer die Datenbasis-App, ohne Werte und ohne GuV.

Festlegung 20.10.2026: Die Datenbasis zeigt, welche Daten hinterlegt sind und wie alles eingestellt ist - getrennt von dem, was
daraus gerechnet wird. Die anzeigenden Apps lesen keinen Speicher, nur Veroeffentlichtes. "Alles aktualisieren" sammelt deshalb
zum Schluss aus den Speichern der Data-App:

- die Staende je Datenart (`data_stands_v1`);
- je Konto die Buchungen nach Art, ihren Zeitraum und die Zahl der Assets, bei Cash-Konten die Auszuege;
- je Asset die Bewertungsart, die Kurszuordnung, wie weit die Kurse reichen und der Bestand je Konto;
- je Waehrungspaar die Wechselkurse;
- je Jahr die Belege der Ablage, gegliedert nach Institut und Konto;
- die Einstellungen: Bewertung je Coin und Wallet, FIFO-Wallets, Anlage je Cash-Konto, Steuer je Jahr, Steuerangaben je
  Institut, Anzeige und die Eingaben des letzten Abschlusses im Run Center samt Gebuehrenquelle.

Ein Teil, der sich nicht lesen laesst, steht als "unavailable" da; die uebrigen erscheinen trotzdem. Was fehlt, wird nicht als
null gezeigt. Veroeffentlicht wird nur, wenn sich der Inhalt gegenueber dem geltenden Stand geaendert hat; es bleiben die
juengsten fuenf Laeufe. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from datetime import date
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Any, Callable

from migrations.reference.legacy_import_data_command_v1 import fingerprint
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _context as _product_context,
    read_desktop_product_asset_activity_binding_v1,
)

AREA_ID = "data_basis"
WRITER_ID = "desktop_data_basis_worker"
WRITER_ROLE = "data_basis_worker"
ARTIFACT_CONTRACT = "data_basis_v1"
VERSION = 1
KEEP_RUNS = 5
SECTIONS = ("stands", "accounts", "assets", "fx", "statements", "settings")
TRADE_TYPES = ("buy", "sell")
INCOME_TYPES = ("dividend", "stock_dividend", "reward")
MOVEMENT_TYPES = ("deposit", "withdrawal", "transfer")
# Die Eingaben des letzten Abschlusses im Run Center: Die Data-App liest sie (spotcore) und gibt sie mit.
RUN_CENTER_FIELDS = ("status", "reason", "portfolio_label", "run_mode", "tax_mode", "capital_income_tax_rate",
                     "personal_income_tax_rate", "solidarity_surcharge_rate", "church_tax_applicable", "church_tax_rate",
                     "fee_source", "fee_fixed_decimal", "fee_percentage_rate_decimal", "grouping_mode", "last_as_of_date")
RUN_CENTER_STATUSES = ("ready", "absent", "not_reusable")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_RUN = re.compile(r"run_[a-z0-9_]{4,72}")


class DataBasisPublicationV1Error(RuntimeError):
    CODES = frozenset({"data_basis_publication_context_invalid", "data_basis_publication_input_invalid",
                       "data_basis_publication_failed"})

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in self.CODES else "data_basis_publication_failed"


def data_basis_publication_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(DataBasisPublicationV1Error.CODES))


def _abort(code: str) -> None:
    raise DataBasisPublicationV1Error(code)


# Grund des letzten Lesefehlers je Teil (rc.343): nur Fehlerart und -code, nie Inhalte. Er geht mit dem Ergebnis der
# Veroeffentlichung an die Data-App, nicht ins Artefakt - so laesst sich ein "nicht lesbar" klaeren (31.10.2026: Belege).
_LAST_REASONS: dict[str, str] = {}


def _reason(error: Exception) -> str:
    code = getattr(error, "code", None)
    return f"{type(error).__name__}:{code}" if isinstance(code, str) and code else type(error).__name__


def _section(read: Callable[[], dict[str, Any]], name: str | None = None) -> dict[str, Any]:
    """Ein Teil der Datenbasis. Laesst er sich nicht lesen, steht er als nicht verfuegbar da - die uebrigen bleiben."""
    try:
        return {"status": "available", **read()}
    except Exception as error:  # noqa: BLE001 - jeder Lesefehler eines Teils heisst hier "nicht verfuegbar", nie "leer"
        if name is not None:
            _LAST_REASONS[name] = _reason(error)
        return {"status": "unavailable"}


def _readonly(path: Path) -> sqlite3.Connection:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(path.name)
    connection = sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _catalog(canonical: Path, context: DesktopProductAssetActivityContextV1) -> tuple[list[dict], list[dict]]:
    connection = _readonly(canonical)
    try:
        binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
        if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
            raise ValueError("canonical_binding_mismatch")
        accounts = [dict(row) for row in connection.execute(
            "SELECT account_id,display_name,account_type,institution_label,status FROM account ORDER BY account_id")]
        assets = [dict(row) for row in connection.execute(
            "SELECT asset_id,display_name,asset_type,price_currency,valuation_method,isin,status FROM asset "
            "WHERE asset_type <> 'cash' ORDER BY asset_id")]
        all_mappings: dict[str, list[dict]] = {}
        for row in connection.execute(
                "SELECT asset_id,provider_id,provider_symbol,exchange_code,provider_currency,verification_status,enabled "
                "FROM provider_mapping WHERE capability='daily_history' ORDER BY asset_id,revision"):
            all_mappings.setdefault(row["asset_id"], []).append(dict(row))
    finally:
        connection.close()
    # Mit Bewertungs-Zeitleiste (rc.393) die Zuordnung des laufenden Marktabschnitts, sonst wie bisher die zuletzt gelesene.
    from migrations.reference.asset_valuation_timeline_v1 import timeline_v1
    timeline = timeline_v1(canonical.parent)
    for asset in assets:
        rows = all_mappings.get(asset["asset_id"], [])
        segment = timeline.current(asset["asset_id"]) if timeline else None
        chosen = None
        if segment is not None and segment.method == "external_market":
            chosen = next((row for row in rows if (row["provider_id"], row["provider_symbol"]) == (segment.provider_id, segment.provider_symbol)), None)
        asset["mapping"] = chosen if chosen is not None else (rows[-1] if rows else None)
    return accounts, assets


def _ledger_rows(space: Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    binding = read_desktop_product_asset_activity_binding_v1(space, context)
    if binding.get("status") != "available" or not binding.get("ledger_path"):
        return []
    connection = _readonly(Path(binding["ledger_path"]))
    try:
        return [dict(row) for row in connection.execute(
            "SELECT account_id,related_account_id,asset_id,event_type,local_date FROM current_asset_activity_event")]
    finally:
        connection.close()


def _stands(space: Path, context, as_of: str, canonical: Path) -> dict[str, Any]:
    from workers.reference.data_stands_v1 import read_data_stands_v1
    value = read_data_stands_v1(space, context, as_of, canonical)
    return {key: value[key] for key in ("transactions", "rewards", "cash", "prices", "history", "snapshot")}


def _accounts(space: Path, context, canonical: Path, accounts: list[dict], events: list[dict]) -> dict[str, Any]:
    from migrations.reference.desktop_cash_coverage_v1 import DesktopCashCoverageV1Error, read_desktop_cash_coverage_view_v1
    from migrations.reference.desktop_cash_manual_v1 import read_desktop_cash_evidence_overview_v1
    from migrations.reference.fifo_wallet_v1 import read_fifo_wallets_v1
    from migrations.reference.statement_archive_v1 import StatementArchiveV1Error, read_statement_account_states_v1
    from migrations.reference.investment_scope_v1 import read_investment_scope_v1
    from workers.reference.portfolio_history_accounts_v1 import wallet_label_v1
    labels = {row["account_id"]: row["display_name"] for row in accounts}
    wallets = {row["account_id"]: row["wallet_account_id"] for row in read_fifo_wallets_v1(space, context)["entries"]}
    scope = read_investment_scope_v1(space, context)["accounts"]
    try:
        cash = read_desktop_cash_coverage_view_v1(canonical, space, context)
    except DesktopCashCoverageV1Error:
        cash = {"status": "absent", "periods": [], "cash_history": []}
    periods: dict[str, list[dict]] = {}
    for period in cash.get("periods") or []:
        periods.setdefault(period["account_label"], []).append(period)
    # Zustand je Konto (#529 Punkt 1) und je Cash-Konto der frueheste abgeglichene Zeitraum mit Anfangssaldo und Herkunft.
    try:
        states = read_statement_account_states_v1(space, context)
    except StatementArchiveV1Error:
        states = {}
    openings: dict[str, dict[str, Any]] = {}
    try:
        evidence = read_desktop_cash_evidence_overview_v1(canonical, space, context, "2000-01-01")
    except DesktopCashCoverageV1Error:
        evidence = {"accounts": []}
    for row in evidence.get("accounts") or []:
        if row.get("reconciled_from_date") is None:
            continue
        known = openings.get(row["account_label"])
        if known is None or row["reconciled_from_date"] < known["reconciled_from"]:
            currency = row.get("cash_asset_label")
            openings[row["account_label"]] = {"reconciled_from": row["reconciled_from_date"], "opening_balance_decimal": row["opening_balance_decimal"],
                                              "opening_origin": row["opening_origin"],
                                              "opening_currency": currency if isinstance(currency, str) and len(currency) == 3 and currency.isupper() else None}
    cash_events: dict[str, int] = {}
    for row in cash.get("cash_history") or []:
        cash_events[row["account_label"]] = cash_events.get(row["account_label"], 0) + 1
    per: dict[str, dict[str, Any]] = {}

    def touch(account: str, kind: str, day: str, asset: str) -> None:
        entry = per.setdefault(account, {"trade": 0, "income": 0, "movement": 0, "days": [], "assets": set()})
        entry[kind] += 1
        entry["days"].append(day)
        entry["assets"].add(asset)

    for event in events:
        kind = "trade" if event["event_type"] in TRADE_TYPES else "income" if event["event_type"] in INCOME_TYPES else "movement"
        touch(event["account_id"], kind, event["local_date"], event["asset_id"])
        # Ein Uebertrag gehoert beiden Konten: Er verlaesst das eine und kommt im anderen an.
        if event["event_type"] == "transfer" and event["related_account_id"]:
            touch(event["related_account_id"], "movement", event["local_date"], event["asset_id"])
    rows = []
    for account in accounts:
        mine = per.get(account["account_id"])
        own_periods = periods.get(account["display_name"], [])
        statement_days = sorted(period["as_of_date"][:10] for period in own_periods if period.get("as_of_date"))
        # Ein archiviertes Konto ohne jede Buchung und ohne Auszug sagt nichts ueber die Datenbasis.
        if account["status"] != "active" and mine is None and not own_periods:
            continue
        main = wallets.get(account["account_id"])
        root = main if main is not None else (account["account_id"] if account["account_id"] in wallets.values() else None)
        rows.append({
            "institution_label": account["institution_label"] or None,
            "account_label": account["display_name"], "account_type": account["account_type"], "account_status": account["status"],
            "fifo_wallet_label": wallet_label_v1(labels, wallets, root) if root is not None else None,
            "in_investment": scope[account["account_id"]]["in_investment"] if account["account_id"] in scope else None,
            "booking_count": 0 if mine is None else mine["trade"] + mine["income"] + mine["movement"],
            "trade_count": 0 if mine is None else mine["trade"], "income_count": 0 if mine is None else mine["income"],
            "movement_count": 0 if mine is None else mine["movement"],
            "asset_count": 0 if mine is None else len(mine["assets"]),
            "first_date": min(mine["days"]) if mine else None, "last_date": max(mine["days"]) if mine else None,
            "statement_period_count": len(own_periods),
            "cash_event_count": cash_events.get(account["display_name"], 0),
            "cash_through": statement_days[-1] if statement_days else None,
            "closed_on": states.get(account["account_id"], {}).get("closed_on"),
            "inactive_since": states.get(account["account_id"], {}).get("inactive_since"),
            **openings.get(account["display_name"], {"reconciled_from": None, "opening_balance_decimal": None, "opening_origin": None,
                                                      "opening_currency": None}),
        })
    rows.sort(key=lambda row: ((row["institution_label"] or "￿").casefold(), row["account_label"].casefold()))
    return {"rows": rows, "cash_status": "available" if cash.get("status") == "available" else "absent"}


def _custody_at(entries: list[tuple[str, int, dict[str, Any]]], as_of: str) -> dict[str, Any]:
    """Stueck je Konto nach dem letzten Ereignis bis zum Stichtag (#529 Punkt 7). Der FIFO-Stand fuehrt die Verwahrmenge des
    Kontos nach jedem Vorgang, bei einem Transfer auch die des Zielkontos; gelesen, nicht nachgerechnet."""
    from migrations.reference.exact_amount_v1 import exact_amount_v1
    held: dict[str, Any] = {}
    for day, _, row in entries:
        if day > as_of:
            break
        if row.get("custody_quantity_after_decimal") is not None:
            held[row["account_ref"]] = row["custody_quantity_after_decimal"]
        if row.get("related_account_ref") and row.get("destination_custody_quantity_after_decimal") is not None:
            held[row["related_account_ref"]] = row["destination_custody_quantity_after_decimal"]
    return {account: quantity for account, quantity in held.items() if exact_amount_v1(quantity) != 0}


def _assets(space: Path, context, as_of: str, assets: list[dict], accounts: list[dict] | None = None) -> dict[str, Any]:
    from workers.reference.portfolio_snapshot_freshness_v1 import holdings_at_v1, holdings_timeline_v1, market_inputs_v1
    from migrations.reference.exact_amount_v1 import amount_text_v1, exact_amount_v1
    from migrations.reference.manual_price_source_v1 import read_manual_entries_v1
    timeline = holdings_timeline_v1(space, context)
    holdings = holdings_at_v1(timeline, as_of)
    held = set(holdings)
    names = {row["account_id"]: (row["display_name"], row["institution_label"] or None) for row in accounts or []}
    inputs = market_inputs_v1(space, set())
    # Je Asset der Bewertungsbereich der aktuellen Zuordnung - der vorderste in der Reihenfolge (#474).
    scopes = {asset: rows[0] for asset, rows in (inputs or {}).get("scope_order", {}).items() if rows}
    rows = []
    for asset in assets:
        if asset["status"] != "active" and asset["asset_id"] not in held:
            continue
        scope = scopes.get(asset["asset_id"])
        mapping = asset["mapping"]
        manual = None
        if asset["valuation_method"] == "manual":
            try:
                entries = read_manual_entries_v1(space, context, asset["asset_id"])["entries"]
                manual = {"count": len(entries), "last_date": entries[-1]["price_date"] if entries else None}
            except Exception:  # noqa: BLE001 - ein unlesbarer Eintrag heisst "nicht verfuegbar"
                manual = None
        rows.append({
            "asset_label": asset["display_name"], "asset_type": asset["asset_type"], "asset_status": asset["status"],
            "price_currency": asset["price_currency"], "valuation_method": asset["valuation_method"],
            "isin_present": bool(asset["isin"]), "held": asset["asset_id"] in held,
            "listing": None if mapping is None else {
                "provider_id": mapping["provider_id"], "provider_symbol": mapping["provider_symbol"],
                "exchange_code": mapping["exchange_code"] or None, "provider_currency": mapping["provider_currency"] or None,
                "verification_status": mapping["verification_status"], "enabled": bool(mapping["enabled"])},
            "valued_from": None if scope is None else scope["valued_from_date"],
            "valued_through": None if scope is None else scope["valued_through_date"],
            "manual_price_count": None if manual is None else manual["count"],
            "manual_price_last": None if manual is None else manual["last_date"],
            # Bestand des Assets und je Konto zum Stichtag der Datenbasis; die Konten zusammen ergeben den Bestand.
            "held_quantity_decimal": amount_text_v1(exact_amount_v1(holdings[asset["asset_id"]]["quantity"])) if asset["asset_id"] in held else None,
            "custody": sorted(({"account_label": names.get(account, ("Konto ohne Stammdaten", None))[0],
                                "institution_label": names.get(account, ("", None))[1],
                                "quantity_decimal": amount_text_v1(exact_amount_v1(quantity))}
                               for account, quantity in _custody_at(timeline.get(asset["asset_id"], []), as_of).items()),
                              key=lambda item: (-exact_amount_v1(item["quantity_decimal"]), item["account_label"].casefold())),
        })
    rows.sort(key=lambda row: row["asset_label"].casefold())
    return {"rows": rows, "valuation_status": "available" if inputs is not None else "absent"}


def _fx(space: Path) -> dict[str, Any]:
    from workers.reference.portfolio_snapshot_freshness_v1 import market_inputs_v1
    path = space / "fx-history-v1" / "fx-history.sqlite"
    if not path.is_file():
        return {"rows": [], "history_status": "absent"}
    connection = _readonly(path)
    try:
        pairs = [dict(row) for row in connection.execute(
            "SELECT p.pair_id,p.pair_ref,p.base_currency,p.quote_currency,"
            "count(CASE WHEN r.day_status='observed' THEN 1 END) AS observed_count,"
            "min(CASE WHEN r.day_status='observed' THEN d.rate_date END) AS first_date,"
            "max(CASE WHEN r.day_status='observed' THEN d.rate_date END) AS last_date "
            "FROM fx_pair_binding p LEFT JOIN fx_day_entity d USING(pair_id) "
            "LEFT JOIN current_fx_day_revision r ON r.fx_day_id=d.fx_day_id GROUP BY p.pair_id ORDER BY p.base_currency,p.quote_currency")]
        sources: dict[int, list[str]] = {}
        for row in connection.execute("SELECT DISTINCT pair_id,source_kind FROM fx_history_request ORDER BY pair_id,source_kind"):
            sources.setdefault(row["pair_id"], []).append(row["source_kind"])
    finally:
        connection.close()
    inputs = market_inputs_v1(space, set())
    effective = {row["pair_ref"]: row for row in (inputs or {}).get("pairs", [])}
    rows = [{"base_currency": pair["base_currency"], "quote_currency": pair["quote_currency"],
             "observed_day_count": int(pair["observed_count"]), "first_date": pair["first_date"], "last_date": pair["last_date"],
             "source_kinds": sources.get(pair["pair_id"], []),
             "effective_from": effective.get(pair["pair_ref"], {}).get("valued_from_date"),
             "effective_through": effective.get(pair["pair_ref"], {}).get("valued_through_date")} for pair in pairs]
    return {"rows": rows, "history_status": "available"}


def _statements(space: Path, context, years: list[int]) -> dict[str, Any]:
    from migrations.reference.statement_archive_v1 import read_statement_archive_years_v1
    rows = []
    for year, overview in zip(years, read_statement_archive_years_v1(space, context, years)):
        counts = overview["month_status_counts"]
        kinds: dict[str, int] = {}
        held = [document for document in overview["documents"] if document["status"] in ("confirmed", "unconfirmed")]
        for document in held:
            kinds[document["document_kind"]] = kinds.get(document["document_kind"], 0) + 1
        rows.append({"year": year, "document_count": sum(kinds.values()),
                     "kinds": [{"document_kind": kind, "count": count} for kind, count in sorted(kinds.items())],
                     "confirmed_months": counts["confirmed"], "unconfirmed_months": counts["unconfirmed"],
                     "not_available_months": counts["not_available"], "open_months": counts["open"],
                     "institutions": _statement_groups(overview["institutions"], held)})
    return {"rows": rows}


_MONTH_FIELDS = (("confirmed", "confirmed_months"), ("unconfirmed", "unconfirmed_months"), ("not_available", "not_available_months"),
                 ("open", "open_months"))


def _statement_groups(institutions: list[dict], documents: list[dict]) -> list[dict[str, Any]]:
    """Je Institut und Konto die Belege und Monate des Jahres (#529 Punkt 6). Ein Beleg fuer mehrere Konten zaehlt bei jedem
    Konto, beim Institut einmal. Konten ohne Beleg und ohne erwarteten Monat fallen weg; sie sagen nichts ueber das Jahr."""
    groups = []
    for institution in institutions:
        accounts, refs = [], set()
        for account in institution["accounts"]:
            mine = {document["document_ref"] for document in documents if account["account_id"] in document["account_ids"]}
            months = {field: sum(1 for cell in account["months"] if cell["status"] == status) for status, field in _MONTH_FIELDS}
            if not mine and not any(months.values()):
                continue
            refs |= mine
            accounts.append({"account_label": account["account_label"], "document_count": len(mine), **months})
        if accounts:
            groups.append({"institution_label": institution["institution_label"], "document_count": len(refs),
                           **{field: sum(account[field] for account in accounts) for _, field in _MONTH_FIELDS}, "accounts": accounts})
    return groups


def _tax_years(space: Path, context, years: list[int]) -> list[dict[str, Any]]:
    from migrations.reference.tax_model_plugin_v1 import TaxPluginContext
    from migrations.reference.tax_ui_workspace_v1 import tax_ui_authorized_product_catalog_v1, tax_ui_overview_v1
    store = space / "tax-ui" / "tax-policy.sqlite"
    if not store.is_file():
        return []
    tax_context = TaxPluginContext(context.tenant_id, context.user_id, context.data_space_id, context.actor_id)
    catalog = tax_ui_authorized_product_catalog_v1(space, tax_context)
    rows = []
    for portfolio in catalog["portfolios"]:
        if portfolio["status"] != "active":
            continue
        for year in years:
            overview = tax_ui_overview_v1(store, tax_context, portfolio["exchange_ref"], year, catalog)
            rows.append({
                "portfolio_label": portfolio["display_name"], "tax_year": year,
                "modules": [{"projection_mode": row["projection_mode"], "plugin_id": row["plugin_id"], "plugin_version": row["plugin_version"]}
                            for row in overview["selections"]],
                "readiness": [{"projection_mode": row["projection_mode"], "status": row["status"]} for row in overview["readiness"]],
                "assessment": overview.get("assessment"), "portfolio_counts": bool(overview.get("portfolio_counts", True)),
                "parameters": [{"parameter_code": row["parameter_code"], "value_kind": row["value_kind"],
                                "value": row.get("applicability_value") if row["value_kind"] == "applicability"
                                else row.get("rate_decimal") if row.get("rate_decimal") is not None else row.get("amount_decimal")}
                               for row in overview["parameters"]],
            })
    return rows


def _settings(space: Path, context, years: list[int], run_center: dict[str, Any] | None) -> dict[str, Any]:
    from migrations.reference.crypto_valuation_method_v1 import read_crypto_valuation_methods_v1
    from migrations.reference.fifo_wallet_v1 import read_fifo_wallets_v1
    from migrations.reference.institution_tax_settings_v1 import read_institution_tax_settings_v1
    from migrations.reference.investment_scope_v1 import read_investment_scope_v1
    from migrations.reference.user_settings_v1 import read_user_settings_v1

    def part(read: Callable[[], Any]) -> Any:
        value = _section(lambda: {"value": read()})
        return value if value["status"] == "unavailable" else {"status": "available", "rows": value["value"]}

    def wallet_rows() -> list[dict]:
        entries = read_fifo_wallets_v1(space, context)["entries"]
        groups: dict[str, dict[str, Any]] = {}
        for row in entries:
            group = groups.setdefault(row["wallet_account_id"], {"wallet_label": row["wallet_account_label"], "institution_label": row["institution"] or None,
                                                                 "member_labels": []})
            group["member_labels"].append(row["account_label"])
        return [{**group, "member_labels": sorted(group["member_labels"], key=str.casefold)}
                for group in sorted(groups.values(), key=lambda group: (group["wallet_label"] or "").casefold())]

    def display() -> dict[str, Any]:
        settings = read_user_settings_v1(space, context)["settings"]
        return {"amount_decimals": int(settings["amount_decimals"]), "tint": settings["tint"] == "on",
                "drawdown_zones": settings.get("drawdown_zones", ""), "expert_tools": settings.get("expert_tools", "off") == "on",
                "analysis_period": settings.get("analysis_period", "all")}

    return {
        "crypto_methods": part(lambda: [{"asset_label": row["asset_label"], "account_label": row["account_label"], "method": row["method"],
                                         "valid_from": row["valid_from_local_date"]} for row in read_crypto_valuation_methods_v1(space, context)["entries"]]),
        "fifo_wallets": part(wallet_rows),
        "investment_scope": part(lambda: [{"institution_label": row["institution"] or None, "account_label": row["label"],
                                           "account_type": row["account_type"], "in_investment": row["in_investment"]}
                                          for row in read_investment_scope_v1(space, context)["cash_accounts"]]),
        "tax_years": part(lambda: _tax_years(space, context, years)),
        "institution_tax": part(lambda: [{"institution_label": row["institution_label"], "tax_year": row["tax_year"], "field_code": row["field_code"],
                                          "amount_decimal": row["amount_decimal"], "orphaned": bool(row["orphaned"])}
                                         for row in read_institution_tax_settings_v1(space, context)["settings"]]),
        "display": _section(display),
        "run_center": {"status": "not_read"} if run_center is None else dict(run_center),
    }


def _run_center(value: Any) -> dict[str, Any] | None:
    """Die Eingaben des letzten Abschlusses, wie die Data-App sie liest - nur bekannte Felder, kurze Texte."""
    if value is None:
        return None
    if not isinstance(value, dict) or not set(value) <= set(RUN_CENTER_FIELDS) or value.get("status") not in RUN_CENTER_STATUSES:
        _abort("data_basis_publication_input_invalid")
    for key, item in value.items():
        if item is not None and (not isinstance(item, str) or not 1 <= len(item) <= 120):
            _abort("data_basis_publication_input_invalid")
    return {key: value.get(key) for key in RUN_CENTER_FIELDS}


def _years(as_of: str, events: list[dict]) -> list[int]:
    """Vom Jahr der ersten Buchung bis zum Jahr des Stichtags; ohne Buchung nur dieses."""
    last = int(as_of[:4])
    first = min((int(event["local_date"][:4]) for event in events), default=last)
    return list(range(max(first, last - 30), last + 1))


def build_data_basis_artifact_v1(data_space_path, context_value: Any, as_of_date: str, completed_at_utc: str,
                                 run_center: Any = None, canonical_path=None) -> dict[str, Any]:
    try:
        context = _product_context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("data_basis_publication_context_invalid")
    try:
        if not isinstance(as_of_date, str) or date.fromisoformat(as_of_date).isoformat() != as_of_date:
            raise ValueError
    except ValueError:
        _abort("data_basis_publication_input_invalid")
    if not isinstance(completed_at_utc, str) or _UTC.fullmatch(completed_at_utc) is None:
        _abort("data_basis_publication_input_invalid")
    center = _run_center(run_center)
    space = Path(data_space_path)
    canonical = Path(canonical_path) if canonical_path is not None else space / "canonical.sqlite"
    catalog = _section(lambda: dict(zip(("accounts", "assets"), _catalog(canonical, context))))
    ledger = _section(lambda: {"events": _ledger_rows(space, context)})
    events = ledger.get("events", [])
    years = _years(as_of_date, events)
    accounts, assets = catalog.get("accounts"), catalog.get("assets")
    unavailable = {"status": "unavailable"}
    _LAST_REASONS.clear()
    sections = {
        "stands": _section(lambda: _stands(space, context, as_of_date, canonical), "stands"),
        "accounts": unavailable if accounts is None or ledger["status"] != "available"
                    else _section(lambda: _accounts(space, context, canonical, accounts, events), "accounts"),
        "assets": unavailable if assets is None else _section(lambda: _assets(space, context, as_of_date, assets, accounts), "assets"),
        "fx": _section(lambda: _fx(space), "fx"),
        "statements": _section(lambda: _statements(space, context, years), "statements"),
        "settings": _section(lambda: _settings(space, context, years, center), "settings"),
    }
    body = {
        "data_basis_version": VERSION, "status": "completed",
        "tenant_id": context.tenant_id, "user_id": context.user_id, "data_space_id": context.data_space_id,
        "as_of_date": as_of_date, "sections": sections,
        "provider_access": False, "network_access": False, "canonical_write": False,
    }
    content = fingerprint(body)
    artifact = {**body, "data_basis_id": "dtb_" + content[:32], "content_fingerprint": content, "completed_at_utc": completed_at_utc}
    artifact["artifact_fingerprint"] = fingerprint(artifact)
    return artifact


def _current_content(area: Path) -> str | None:
    try:
        run_id = json.loads((area / "latest.json").read_text(encoding="utf-8")).get("run_id")
        if not isinstance(run_id, str) or _RUN.fullmatch(run_id) is None:
            return None
        return json.loads((area / "runs" / run_id / "artifact.json").read_text(encoding="utf-8")).get("content_fingerprint")
    except (OSError, ValueError, AttributeError):
        return None


def _prune(area: Path, keep_run: str) -> int:
    """Aeltere Laeufe entfernen: nur Laufverzeichnisse, nie den geltenden Stand."""
    runs = area / "runs"
    if not runs.is_dir() or runs.is_symlink():
        return 0
    candidates = sorted((entry for entry in runs.iterdir() if entry.is_dir() and not entry.is_symlink() and _RUN.fullmatch(entry.name)),
                        key=lambda entry: entry.stat().st_mtime, reverse=True)
    removed = 0
    for entry in candidates[KEEP_RUNS:]:
        if entry.name != keep_run:
            shutil.rmtree(entry)
            removed += 1
    return removed


def _summary(artifact: dict[str, Any]) -> dict[str, Any]:
    sections = artifact["sections"]
    # Die Staende gehen mit zurueck: Die Data-App zeigt sie ueber "Alles aktualisieren", ohne sie ein zweites Mal zu lesen.
    return {"section_status": {name: sections[name]["status"] for name in SECTIONS},
            "section_reasons": {name: _LAST_REASONS[name] for name in SECTIONS if sections[name]["status"] != "available" and name in _LAST_REASONS},
            "account_count": len(sections["accounts"].get("rows", [])), "asset_count": len(sections["assets"].get("rows", [])),
            "stands": sections["stands"]}


def publish_data_basis_v1(data_space_path, context_value: Any, as_of_date: str, published_at_utc: str, run_center: Any = None,
                          artifacts_root=None, canonical_path=None) -> dict[str, Any]:
    """Veroeffentlicht die Datenbasis, wenn sich ihr Inhalt gegenueber dem geltenden Stand geaendert hat."""
    artifact = build_data_basis_artifact_v1(data_space_path, context_value, as_of_date, published_at_utc, run_center, canonical_path)
    root = Path(artifacts_root) if artifacts_root is not None else Path(data_space_path) / "artifacts"
    return _publish_artifact(root, _product_context(context_value), artifact, published_at_utc)


def _publish_artifact(root: Path, context, artifact: dict[str, Any], published_at_utc: str) -> dict[str, Any]:
    area = root / AREA_ID
    result = {"data_basis_publication_version": VERSION, "as_of_date": artifact["as_of_date"], **_summary(artifact),
              "provider_access": False, "network_access": False, "canonical_write": False}
    if _current_content(area) == artifact["content_fingerprint"]:
        return {**result, "status": "already_published"}
    for directory in (root, area):
        if directory.is_symlink():
            _abort("data_basis_publication_failed")
        if not directory.exists():
            directory.mkdir(mode=0o700, parents=True)
        os.chmod(directory, 0o700)
    from workers.reference.run_publication_v1 import PublicationRuntimeContext, RunPublicationError, publish_completed_run_v1
    runtime = PublicationRuntimeContext(context.tenant_id, context.user_id, context.data_space_id, AREA_ID, WRITER_ID, WRITER_ROLE)
    run_id = "run_" + fingerprint({"content": artifact["content_fingerprint"], "published_at_utc": published_at_utc})[:32]
    try:
        published = publish_completed_run_v1(area, runtime, run_id, artifact, published_at_utc)
    except RunPublicationError:
        _abort("data_basis_publication_failed")
    return {**result, "status": published.status, "pruned_run_count": _prune(area, run_id)}


# Was seit der letzten Veroeffentlichung geaendert ist, und ob Steuer und Analyse damit rechnen (#422, rc.332).
#
# Festlegung 27.10.2026: Nach Konten- oder Stammdatenpflege bietet Data an, die Datenbasis gleich neu zu veroeffentlichen -
# aber nur, solange keine Aenderung offen ist, mit der Steuer und Analyse rechnen. Sonst zeigte die Datenbasis Einstellungen oder
# Buchungen, mit denen noch nicht gerechnet wurde; dann bleibt es bei "Alles aktualisieren".
#
# Verglichen wird die frisch gebaute Datenbasis (zum Stichtag und mit den Run-Center-Eingaben der geltenden) mit der geltenden:
# - frei sind Namen (Konto, Institut, Asset, Portfolio, Wallet), ISIN, neue Konten ohne jede Bewegung, Assets ohne Buchung und
#   ohne Bestand - auch mit Kurszuordnung und Kursen, etwa beobachtete Werte (rc.334) -, die Ablage und die Anzeige;
# - alles andere zaehlt fuer die Rechnung: Buchungen, Cash, Kurse und Zuordnungen gebuchter Assets, Wechselkurse, Bewertungsart,
#   FIFO-Wallets, Bewertung je Coin, Anlage, Steuer. Ein Asset in einem Vergleichsindex zaehlt auch ohne Buchung: Die Analyse
#   rechnet seine Kurse (#482, #502). Wechselt ein Konto das Institut, aendert sich die Steuer je Institut - auch das zaehlt;
#   darum werden Konten je Institut gruppiert, nicht nur ohne Namen verglichen.
_NAME_FIELDS = frozenset({"account_label", "institution_label", "asset_label", "portfolio_label", "wallet_label", "isin_present"})
# Nur zur Auskunft (#529 Punkte 1 und 7, Cash-Tabelle): Zustand des Kontos, Anfangssaldo und Bestand je Konto. Die Rechnung liest
# nichts davon aus der Datenbasis - ein ruhendes Konto zaehlt weiter, Anfangssaldo und Bestand stecken schon in Cash- und FIFO-Stand.
_NOTE_FIELDS = frozenset({"closed_on", "inactive_since", "reconciled_from", "opening_balance_decimal", "opening_origin", "opening_currency",
                          "held_quantity_decimal", "custody"})


def _ordered(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _without_names(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if key in _NAME_FIELDS or key in _NOTE_FIELDS:
                continue
            if key == "member_labels":
                out["member_count"] = len(item) if isinstance(item, list) else None
            elif key == "fifo_wallet_label":
                out["in_fifo_wallet"] = item is not None
            else:
                out[key] = _without_names(item)
        return out
    if isinstance(value, list):
        return sorted((_without_names(item) for item in value), key=_ordered)
    return value


def _idle_account(row: dict[str, Any]) -> bool:
    return (row.get("booking_count") == 0 and row.get("cash_event_count") == 0 and row.get("statement_period_count") == 0
            and row.get("fifo_wallet_label") is None and row.get("in_investment") is None)


def _idle_asset(row: dict[str, Any], bound: frozenset[str] | None) -> bool:
    # Ohne Buchung und Bestand rechnet ein Asset nirgends mit - auch nicht mit Kurszuordnung und Kursen (rc.334). Ein
    # ausverkauftes Asset hat Buchungen und zaehlt weiter: seine Bewertungsart wirkt auf die Tage, an denen es gehalten wurde.
    return bound is not None and row.get("held") is False and row.get("asset_label") not in bound


def _bound_asset_labels(space: Path, context, canonical: Path) -> frozenset[str] | None:
    """Die heutigen Namen der Assets, mit denen gerechnet wird, auch ohne Bestand: mit mindestens einer Buchung oder als
    Bestandteil eines Vergleichsindex. Fuer beide Seiten des Vergleichs dieselben."""
    from migrations.reference.analysis_settings_v1 import read_analysis_settings_v1
    try:
        _, assets = _catalog(canonical, context)
        ids = {row["asset_id"] for row in _ledger_rows(space, context)}
        ids |= {item["asset_id"] for entry in read_analysis_settings_v1(space, context)["indices"] for item in entry["components"]}
    except Exception:  # noqa: BLE001 - unlesbar (None) heisst: kein Asset gilt als frei
        return None
    return frozenset(asset["display_name"] for asset in assets if asset["asset_id"] in ids)


def _calculation_view(name: str, section: Any, bound: frozenset[str] | None = None) -> Any:
    """Der Teil eines Abschnitts, mit dem gerechnet wird; None fuer Abschnitte, die nur dokumentieren."""
    if name == "statements" or not isinstance(section, dict):
        return None if name == "statements" else section
    if name == "accounts" and isinstance(section.get("rows"), list):
        groups: dict[Any, list] = {}
        for row in section["rows"]:
            if not _idle_account(row):
                groups.setdefault(row.get("institution_label"), []).append(row)
        return {**{key: value for key, value in section.items() if key != "rows"}, "institutions": _without_names(list(groups.values()))}
    if name == "assets" and isinstance(section.get("rows"), list):
        return {**{key: value for key, value in section.items() if key != "rows"},
                "rows": _without_names([row for row in section["rows"] if not _idle_asset(row, bound)])}
    if name == "settings":
        return _without_names({key: value for key, value in section.items() if key != "display"})
    return section


def _current_artifact(area: Path) -> dict[str, Any] | None:
    try:
        if area.is_symlink():
            return None
        run_id = json.loads((area / "latest.json").read_text(encoding="utf-8")).get("run_id")
        if not isinstance(run_id, str) or _RUN.fullmatch(run_id) is None:
            return None
        value = json.loads((area / "runs" / run_id / "artifact.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return None
    if (not isinstance(value, dict) or not isinstance(value.get("sections"), dict) or set(value["sections"]) != set(SECTIONS)
            or not isinstance(value.get("as_of_date"), str) or not isinstance(value.get("completed_at_utc"), str)):
        return None
    return value


def _published_run_center(artifact: dict[str, Any]) -> dict[str, Any] | None:
    settings = artifact["sections"].get("settings")
    value = settings.get("run_center") if isinstance(settings, dict) else None
    return None if not isinstance(value, dict) or value.get("status") == "not_read" else value


def _pending(space: Path, context, root: Path, canonical_path, completed_at_utc: str | None):
    """(Ergebnis, frisch gebaute Datenbasis oder None). Gebaut wird zum Stichtag der geltenden, damit nur Geaendertes abweicht."""
    published = _current_artifact(root / AREA_ID)
    base = {"data_basis_pending_version": VERSION, "provider_access": False, "network_access": False, "canonical_write": False}
    if published is None:
        state = "never_published" if not (root / AREA_ID / "latest.json").exists() else "unreadable"
        return {**base, "status": state, "published_as_of_date": None, "published_at_utc": None,
                "changed_sections": [], "calculation_sections": []}, None
    try:
        fresh = build_data_basis_artifact_v1(space, context, published["as_of_date"], completed_at_utc or published["completed_at_utc"],
                                             _published_run_center(published), canonical_path)
    except DataBasisPublicationV1Error:
        # Eine geltende Datenbasis aus einer anderen Fassung (andere Run-Center-Felder) gleicht man mit "Alles aktualisieren" an.
        return {**base, "status": "calculation", "published_as_of_date": published["as_of_date"],
                "published_at_utc": published["completed_at_utc"], "changed_sections": list(SECTIONS),
                "calculation_sections": list(SECTIONS)}, None
    changed = [name for name in SECTIONS if _ordered(fresh["sections"][name]) != _ordered(published["sections"][name])]
    bound = _bound_asset_labels(space, context, Path(canonical_path) if canonical_path is not None else space / "canonical.sqlite")
    calculation = [name for name in changed if _ordered(_calculation_view(name, fresh["sections"][name], bound))
                   != _ordered(_calculation_view(name, published["sections"][name], bound))]
    state = "current" if fresh["content_fingerprint"] == published.get("content_fingerprint") else "calculation" if calculation else "names_only"
    return {**base, "status": state, "published_as_of_date": published["as_of_date"], "published_at_utc": published["completed_at_utc"],
            "changed_sections": changed, "calculation_sections": calculation}, fresh


def data_basis_pending_v1(data_space_path, context_value: Any, artifacts_root=None, canonical_path=None) -> dict[str, Any]:
    """Liest nur: current, names_only (frei neu zu veroeffentlichen), calculation, never_published oder unreadable."""
    try:
        context = _product_context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("data_basis_publication_context_invalid")
    space = Path(data_space_path)
    root = Path(artifacts_root) if artifacts_root is not None else space / "artifacts"
    return _pending(space, context, root, canonical_path, None)[0]


def publish_data_basis_names_v1(data_space_path, context_value: Any, published_at_utc: str, artifacts_root=None,
                                canonical_path=None) -> dict[str, Any]:
    """Veroeffentlicht neu, wenn nur Freies geaendert ist - mit genau dem geprueften Bau, ohne zweites Lesen."""
    try:
        context = _product_context(context_value)
    except DesktopProductAssetActivityV1Error:
        _abort("data_basis_publication_context_invalid")
    if not isinstance(published_at_utc, str) or _UTC.fullmatch(published_at_utc) is None:
        _abort("data_basis_publication_input_invalid")
    space = Path(data_space_path)
    root = Path(artifacts_root) if artifacts_root is not None else space / "artifacts"
    pending, fresh = _pending(space, context, root, canonical_path, published_at_utc)
    if pending["status"] == "current":
        return {**pending, "status": "already_published"}
    if pending["status"] != "names_only" or fresh is None:
        return {**pending, "status": "blocked_" + pending["status"]}
    published = _publish_artifact(root, context, fresh, published_at_utc)
    return {**pending, "status": published["status"], "publication": published}


__all__ = ["AREA_ID", "ARTIFACT_CONTRACT", "DataBasisPublicationV1Error", "SECTIONS", "WRITER_ROLE", "build_data_basis_artifact_v1",
           "data_basis_pending_v1", "data_basis_publication_v1_error_codes", "publish_data_basis_names_v1", "publish_data_basis_v1"]
