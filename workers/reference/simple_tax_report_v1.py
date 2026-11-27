"""Einfacher Steuerreport: Dokumentation der Veraeusserungen und Ertraege eines Jahres, ohne Steuerrechnung.

Der Report belegt je Veraeusserung, welche Anschaffungen sie verbraucht hat
(Verbrauchsfolge FiFo je Konto), wie die Lots auf das veraeussernde Konto kamen,
wie lange sie gehalten wurden und welche Kennungen dazu vorliegen. Er rechnet
keine Steuer und wendet keine Freigrenze an. Lots und Anschaffungskosten kommen
aus dem FIFO-Stand (Spur der Lots), Betraege aus dem Buchungsbestand,
Kennungen aus den Belegangaben; hier wird nichts nachgerechnet, nur
zusammengestellt. Kein Providerzugriff, kein Netzzugriff, kein Write.

Festlegungen (12.10.2026): Ein Transfer ist keine
Veraeusserung; eine in Stueck gezahlte Gebuehr wird am jeweiligen Vorgang
ausgewiesen und nicht als Veraeusserung behandelt; ein Abgang (Withdrawal) ist
eine Veraeusserung. Ein Abgang traegt im Buchungsbestand keinen Erloes: Als
Wert gilt, was der Eigentuemer am Abgang eingetragen hat, sonst Stueckzahl mal
Tageswert aus dem Bewertungsstand am Tag des Abgangs. Der Report nennt je
Vorgang, woher der Wert stammt.

Zinsen der Cash-Konten (Festlegung 13.10.2026: im Report waehlbar wie auf dem
Rechenblatt) kommen aus dem Cash-Speicher, nicht aus dem Buchungsbestand: je
Zinsgutschrift eine Zeile, dazu die Summe je Konto. Sie brauchen keinen
FIFO-Stand; ein Report nur ueber Zinsen entsteht auch ohne ihn.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
import hashlib
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from migrations.reference.asset_activity_reference_v1 import (
    AssetActivityReferenceV1Error, activity_reference_scope_v1, read_activity_disposal_values_v1, read_activity_references_v1,
)
from migrations.reference.desktop_cash_coverage_v1 import (
    STORE_AREA as CASH_STORE_AREA, STORE_NAME as CASH_STORE_NAME, DesktopCashCoverageV1Error,
    read_desktop_cash_coverage_exchange_projection_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityV1Error, _canonical_snapshot, read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.institution_tax_settings_v1 import InstitutionTaxSettingsV1Error, read_institution_tax_settings_v1
from workers.reference.stock_split_prices_v1 import split_price_adjuster_v1
from workers.reference.advance_lump_sum_v1 import (
    AdvanceLumpSumOverviewV1Error, allocate_v1, bookings_v1, deduction_v1, inflow_date_v1, round_cents_v1, year_end_v1,
)
from workers.reference.asset_activity_realized_state_v2 import (
    AssetActivityRealizedStateV2Error, read_asset_activity_realized_lot_trace_v2,
)

CONTRACT = "simple_tax_report_v1"
# Klassen mit Kapitalertraegen: Bei ihnen weist der Report die je Institut eingetragene Quellensteuer aus (#432).
CAPITAL_TYPES = ("equity", "fund", "cash")
ASSET_TYPES = ("crypto", "equity", "fund", "commodity", "derivative", "fx")   # fx = Devisen (#449)
# "cash" ist keine Assetklasse des Buchungsbestands: Die Wahl holt die Zinsen der Cash-Konten aus dem Cash-Speicher dazu.
CASH_TYPE = "cash"
REPORT_TYPES = (*ASSET_TYPES, CASH_TYPE)
ACQUISITION_TYPES = ("buy", "reward", "deposit", "stock_dividend")
VALUATION_AREA = "market-valuation-state-v1"
VALUATION_STORE = "valuation-state.sqlite"
FAILURE_CODES = (
    "simple_tax_report_input_invalid",
    "simple_tax_report_source_invalid",
)


class SimpleTaxReportV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def simple_tax_report_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise SimpleTaxReportV1Error(code if code in FAILURE_CODES else "simple_tax_report_source_invalid")


def _fraction(value: Any) -> Fraction | None:
    if value is None or value == "":
        return None
    try:
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError):
        _abort("simple_tax_report_source_invalid")
        return None


def _exact(value: Any) -> Fraction | None:
    """Ein exakter Wert des FIFO-Ergebnisses; fehlende Basis bleibt fehlend."""
    if not isinstance(value, Mapping) or value.get("exactness_status") == "basis_missing":
        return None
    try:
        return Fraction(int(value["numerator_integer"]), int(value["denominator_integer"]))
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        _abort("simple_tax_report_source_invalid")
        return None


def _number(value: Fraction | None) -> str | None:
    """Exakter Dezimaltext, wo es ihn gibt; sonst auf zwoelf Stellen."""
    if value is None:
        return None
    denominator = value.denominator
    while denominator % 2 == 0:
        denominator //= 2
    while denominator % 5 == 0:
        denominator //= 5
    if denominator == 1:
        text = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    else:
        text = format((Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal("0.000000000001")), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _money(value: Fraction | None) -> str | None:
    """Kaufmaennisch auf Cent gerundet - nur fuer die Ausgabe; gerechnet wird ungerundet."""
    if value is None:
        return None
    return format((Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")


def _anniversary(day: str) -> str:
    """Der Tag, mit dessen Ablauf die Jahresfrist endet (§ 188 Abs. 2 und 3 BGB)."""
    year, month, number = (int(part) for part in day.split("-"))
    if month == 2 and number == 29:
        number = 28
    return f"{year + 1:04d}-{month:02d}-{number:02d}"


def _days(first: str, second: str) -> int:
    return (date.fromisoformat(second) - date.fromisoformat(first)).days


def _ledger(space: Path, context) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    try:
        binding = read_desktop_product_asset_activity_binding_v1(space, context)
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            assets = {row["asset_id"]: dict(row) for row in connection.execute(
                "SELECT asset_id,display_name,asset_type,isin FROM current_asset_revision")}
            accounts = {row["account_id"]: dict(row) for row in connection.execute(
                "SELECT account_id,display_name,account_type,institution_label FROM current_account_revision")}
            events = {row["event_ref"]: dict(row) for row in connection.execute(
                "SELECT event_ref,portfolio_id,gross_economic_amount_decimal,net_trade_proceeds_decimal,fifo_basis_created_decimal,"
                "gross_income_decimal,movement_context_code,time_zone,local_time FROM current_asset_activity_event")}
        finally:
            connection.close()
    except (DesktopProductAssetActivityV1Error, sqlite3.Error, KeyError, TypeError):
        _abort("simple_tax_report_source_invalid")
        return {}, {}, {}
    return assets, accounts, events


def simple_tax_report_interest_rows_v1(data_space_path: str | Path, context_value: Any, tax_year: int) -> list[dict[str, Any]]:
    """Die Zinsgutschriften der Cash-Konten im Steuerjahr - aus dem Cash-Speicher, Konto und Institut aus den Stammdaten.

    Ohne Cash-Speicher gibt es keine Zinsen und keinen Fehler. Jede Zeile traegt die Schluessel des Speichers
    (`source_key`) fuer Rechenkerne, die darauf aufbauen; wer sie liest, gibt sie nicht weiter. Der Betrag ist exakt.
    """
    space = Path(data_space_path)
    store = space / CASH_STORE_AREA / CASH_STORE_NAME
    if not store.exists():
        return []
    try:
        incomes = read_desktop_cash_coverage_exchange_projection_v1(store, context_value)["income_events"]
        snapshot = _canonical_snapshot(space / "canonical.sqlite", context_value)
    except (DesktopCashCoverageV1Error, DesktopProductAssetActivityV1Error, OSError, KeyError, TypeError):
        _abort("simple_tax_report_source_invalid")
    accounts = {row["account_id"]: row for row in snapshot["accounts"]}
    assets = {row["asset_id"]: row for row in snapshot["assets"]}
    year = f"{tax_year:04d}"
    chosen = [row for row in incomes if row["income_type"] == "interest" and row["local_date"][:4] == year]
    rows = []
    for sequence, row in enumerate(sorted(chosen, key=lambda row: (
            row["local_date"], accounts.get(row["account_id"], {}).get("display_name") or "", row["income_event_id"])), 1):
        account = accounts.get(row["account_id"]) or {}
        rows.append({
            "asset_label": (assets.get(row["cash_asset_id"]) or {}).get("display_name") or "unbekanntes Cash-Asset", "asset_type": CASH_TYPE,
            "account_label": account.get("display_name") or "unbekanntes Konto", "institution_label": account.get("institution_label"),
            "local_date": row["local_date"], "event_sequence": sequence, "income_type": "interest", "currency": row["currency"],
            "gross_income": Fraction(row["gross_income_decimal"]),
            "source_key": {"event_ref": row["income_event_id"], "asset_id": row["cash_asset_id"], "account_ref": row["account_id"],
                           "portfolio_id": row["portfolio_id"], "effective_at_utc": row["local_date"] + "T00:00:00Z"},
        })
    return rows


def simple_tax_report_withholding_rows_v1(data_space_path: str | Path, context_value: Any, tax_year: int) -> list[dict[str, Any]]:
    """Die anrechenbare auslaendische Quellensteuer des Jahres je Institut, wie der Eigentuemer sie eingetragen hat (#432).

    Festlegung (12.10.2026): ein Betrag je Institut und Jahr - eingetragen in Data, Steuer, je Institut. Ohne Speicher
    gibt es keine Angabe und keinen Fehler. Angaben zu Instituten, die an keinem Konto mehr stehen, zaehlen nicht.
    """
    try:
        model = read_institution_tax_settings_v1(data_space_path, context_value)
    except InstitutionTaxSettingsV1Error:
        _abort("simple_tax_report_source_invalid")
    labels = {row["institution_key"]: row["institution_label"] for row in model["institutions"]}
    rows = [{"institution_label": labels.get(row["institution_key"]) or None, "currency": "EUR", "withholding_amount": Fraction(row["amount_decimal"])}
            for row in model["settings"] if row["tax_year"] == tax_year and row["field_code"] == "creditable_foreign_withholding_tax" and not row["orphaned"]]
    return sorted(rows, key=lambda row: (row["institution_label"] is None, (row["institution_label"] or "").lower()))


def _interest_totals(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Je Konto und Waehrung die Zahl der Gutschriften und ihre Summe - aus den exakten Betraegen."""
    totals: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = ((row["institution_label"] or "").lower(), row["account_label"], row["currency"])
        total = totals.setdefault(key, {"account_label": row["account_label"], "institution_label": row["institution_label"],
                                        "currency": row["currency"], "interest_count": 0, "income": Fraction(0)})
        total["interest_count"] += 1
        total["income"] += row["gross_income"]
    return [totals[key] for key in sorted(totals, key=lambda key: (key[0] == "", key[0], key[1].lower(), key[2]))]


def _daily_values(space: Path, wanted: set[tuple[str, str]], adjuster: Any = None, context: Any = None) -> tuple[str, dict[tuple[str, str], dict[str, Any]]]:
    """Der EUR-Wert je Einheit am Tag, wie ihn der Bewertungsstand fuehrt - gelesen, nicht hergeleitet.

    Bewerten mehrere Kursreihen des Assets den Tag (Symbol- oder Anbieterwechsel), gilt die Regel aus #474: die Reihe der
    aktuellen Zuordnung, sonst die mit dem spaetesten Ende (rc.385). Bis rc.384 entfiel der Wert dann ganz.

    Seit rc.393: Mit Bewertungs-Zeitleiste traegt allein die Reihe des Abschnitts den Tag. Wird das Asset an dem Tag mit eigenen
    Kursen bewertet (Abschnitt oder Art "eigene Kurse"), zaehlt der eigene Kurs bzw. der letzte bestaetigte Trade-Kurs auch hier
    (Festlegung 10.11.2026), in EUR; bis rc.392 stand dort kein Tageswert. "Nur Transaktionen" traegt keinen.
    """
    owner = _owner_daily_values(space, wanted, context)
    # Mit Zeitleiste entscheidet allein der Abschnitt; ohne bleibt der Markttag des Bewertungsstands vorn wie bisher, ein eigener
    # Kurs fuellt nur, wo keiner ist.
    wanted = {key for key in wanted if key not in owner["handled"]}
    path = space / VALUATION_AREA / VALUATION_STORE
    if not wanted or not path.is_file():
        found_owner = {**owner["fallback"], **owner["values"]}
        return ("available" if found_owner else "absent"), found_owner
    found: dict[tuple[str, str], dict[str, Any]] = dict(owner["values"])
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            from workers.reference.portfolio_snapshot_freshness_v1 import choose_day_rows_v1, current_symbols_v1, scope_windows_v1
            scopes = scope_windows_v1(connection)
            current = current_symbols_v1(space)
            for asset_id, day in sorted(wanted):
                rows = connection.execute(
                    "SELECT s.scope_ref,s.asset_id,d.target_decimal,d.target_numerator,d.target_denominator,d.price_basis,d.price_source_date "
                    "FROM valuation_scope s JOIN valuation_day d USING(scope_ref) "
                    "WHERE s.asset_id=? AND d.trading_date=? AND d.target_decimal IS NOT NULL", (asset_id, day)).fetchall()
                if not rows:
                    continue
                if len(rows) > 1 or (getattr(current, "timeline", None) and current.timeline.has(asset_id)):
                    chosen = choose_day_rows_v1([dict(row) for row in rows], scopes, current, day).get(asset_id)
                    if chosen is None:
                        continue
                    rows = [chosen]
                # Vor einem Split (#451) je Stueck dieses Tages - die gebuchte Menge steht in diesen Stuecken.
                row = dict(rows[0]) if not adjuster else adjuster.adjust(dict(rows[0]), rows[0]["scope_ref"], day)
                unit = Fraction(int(row["target_numerator"]), int(row["target_denominator"]))
                if unit < 0:
                    continue
                found[(asset_id, day)] = {"unit_value": unit, "price_basis": rows[0]["price_basis"],
                                          "price_source_date": rows[0]["price_source_date"]}
        finally:
            connection.close()
    except (sqlite3.Error, TypeError, ValueError, ZeroDivisionError):
        return "unreadable", {}
    for key, value in owner["fallback"].items():
        found.setdefault(key, value)
    return "available", found


def _owner_daily_values(space: Path, wanted: set[tuple[str, str]], context: Any) -> dict[str, Any]:
    """Tageswerte aus eigener Bewertung (rc.393). Mit Zeitleiste: (Asset, Tag) eines Abschnitts "eigene Kurse" bzw. "nur
    Transaktionen" sind entschieden ('handled'), "eigene Kurse" mit Wert. Ohne Zeitleiste und mit Art "eigene Kurse": der eigene Wert
    nur als Ergaenzung ('fallback'), wo der Bewertungsstand keinen Tag fuehrt - wie im Snapshot ohne Zeitleiste."""
    if not wanted or context is None:
        return {"handled": set(), "values": {}, "fallback": {}}
    try:
        from migrations.reference.asset_valuation_facts_v1 import asset_master_v1, owner_valuation_v1
        from migrations.reference.asset_valuation_timeline_v1 import timeline_v1
        plain = {key: getattr(context, key, None) if not isinstance(context, Mapping) else context.get(key) for key in ("tenant_id", "user_id", "data_space_id")}
        master = asset_master_v1(space, plain)
        timeline = timeline_v1(space)
    except Exception:
        return {"handled": set(), "values": {}, "fallback": {}}
    handled: set[tuple[str, str]] = set()
    values: dict[tuple[str, str], dict[str, Any]] = {}
    fallback: dict[tuple[str, str], dict[str, Any]] = {}
    for asset_id, day in sorted(wanted):
        method = (master.get(asset_id) or {}).get("valuation_method")
        explicit = bool(timeline) and timeline.has(asset_id)
        if explicit:
            method = timeline.method_on(asset_id, day, method)
        if method not in ("manual", "transaction_only") or (not explicit and method != "manual"):
            continue
        if explicit:
            handled.add((asset_id, day))
        if method != "manual":
            continue
        result = owner_valuation_v1(space, plain, asset_id, day)
        if result.get("status") != "valued" or result.get("native_currency") != "EUR":
            continue
        unit = Fraction(str(result["native_decimal"]))
        if unit >= 0:
            (values if explicit else fallback)[(asset_id, day)] = {"unit_value": unit, "price_basis": result["price_basis"],
                                                                  "price_source_date": result["price_source_date"]}
    return {"handled": handled, "values": values, "fallback": fallback}


def _acquisition_day(event: Mapping[str, Any]) -> str:
    day = event.get("original_acquired_local_date") if event["event_type"] == "deposit" else event["local_date"]
    if not isinstance(day, str):
        _abort("simple_tax_report_source_invalid")
    return day


# Auswahl einzelner Konten oder Vermoegenswerte (#433): Die Oberflaeche kennt sie nur ueber diese Marken, nicht ueber
# die Kennungen des Bestands.
SELECTION_KINDS = {"accounts": "kto", "assets": "vmw"}


def _selection_token(context: Any, kind: str, internal: str) -> str:
    material = "|".join(("simple-tax-report-selection-v1", context.tenant_id, context.user_id, context.data_space_id, kind, internal))
    return SELECTION_KINDS[kind] + "_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _tax_asset_type(value: str) -> str:
    """Steuerlich ist ein ETF ein Investmentfonds (InvStG): Er zaehlt wie "Fonds" - im Report, bei der Vorabpauschale und
    beim Abzug beim Verkauf. Das Asset-Center fuehrt ETF und Fonds getrennt; vor #447 fiel ein ETF aus dem Report."""
    return "fund" if value == "etf" else value


def simple_tax_report_choices_v1(data_space_path: str | Path, context_value: Any, asset_types: Sequence[str]) -> dict[str, Any]:
    """Was sich fuer einen Report auswaehlen laesst: die Konten und die Vermoegenswerte der gewaehlten Klassen. Liest nur."""
    if isinstance(asset_types, (str, bytes)) or not isinstance(asset_types, Sequence) or not asset_types or any(
            kind not in REPORT_TYPES for kind in asset_types) or len(set(asset_types)) != len(asset_types):
        _abort("simple_tax_report_input_invalid")
    try:
        context = activity_reference_scope_v1(context_value)
        snapshot = _canonical_snapshot(Path(data_space_path) / "canonical.sqlite", context)
    except AssetActivityReferenceV1Error:
        _abort("simple_tax_report_input_invalid")
    except (DesktopProductAssetActivityV1Error, OSError, KeyError, TypeError):
        _abort("simple_tax_report_source_invalid")
    accounts = sorted(({"token": _selection_token(context, "accounts", row["account_id"]), "label": row["display_name"],
                        "institution_label": row.get("institution_label") or None}
                       for row in snapshot["accounts"] if row.get("status") != "archived"), key=lambda row: row["label"].lower())
    assets = sorted(({"token": _selection_token(context, "assets", row["asset_id"]), "label": row["display_name"], "asset_type": _tax_asset_type(row["asset_type"])}
                     for row in snapshot["assets"] if row.get("status") != "archived" and _tax_asset_type(row["asset_type"]) in asset_types and row["asset_type"] != CASH_TYPE),
                    key=lambda row: row["label"].lower())
    return {"contract_version": CONTRACT, "accounts": accounts, "assets": assets,
            "provider_access": False, "network_access": False, "canonical_write": False}


def _selection(space: Path, context: Any, selection: Any) -> tuple[set[str] | None, set[str] | None, dict[str, list[str]] | None]:
    """Die gewaehlten Konten und Vermoegenswerte als Kennungen des Bestands - und als Namen fuer den Report."""
    if selection is None:
        return None, None, None
    if not isinstance(selection, Mapping) or not set(selection) <= set(SELECTION_KINDS) or any(
            not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value) or len(set(value)) != len(value)
            for value in selection.values()):
        _abort("simple_tax_report_input_invalid")
    try:
        snapshot = _canonical_snapshot(space / "canonical.sqlite", context)
    except (DesktopProductAssetActivityV1Error, OSError, KeyError, TypeError):
        _abort("simple_tax_report_source_invalid")
    chosen: dict[str, set[str] | None] = {}
    labels: dict[str, list[str]] = {}
    for kind, rows, key in (("accounts", snapshot["accounts"], "account_id"), ("assets", snapshot["assets"], "asset_id")):
        wanted = list(selection.get(kind) or [])
        if not wanted:
            chosen[kind] = None
            continue
        known = {_selection_token(context, kind, row[key]): row for row in rows}
        if any(token not in known for token in wanted):
            _abort("simple_tax_report_input_invalid")
        chosen[kind] = {known[token][key] for token in wanted}
        labels[kind] = sorted((known[token]["display_name"] for token in wanted), key=str.lower)
    if chosen["accounts"] is None and chosen["assets"] is None:
        return None, None, None
    return chosen["accounts"], chosen["assets"], labels


def build_simple_tax_report_v1(
    data_space_path: str | Path, context_value: Any, tax_year: int, asset_types: Sequence[str] = ("crypto",), selection: Any = None,
) -> dict[str, Any]:
    """Stellt den einfachen Report eines Steuerjahres zusammen - auf Wunsch nur fuer gewaehlte Konten oder Vermoegenswerte. Liest nur."""
    return _build(data_space_path, context_value, tax_year, asset_types, False, selection)


def build_simple_tax_report_with_keys_v1(
    data_space_path: str | Path, context_value: Any, tax_year: int, asset_types: Sequence[str] = ("crypto",), selection: Any = None,
) -> dict[str, Any]:
    """Derselbe Report, dazu je Vorgang die Schluessel des Bestands - fuer Rechenkerne, die darauf aufbauen.

    Die Schluessel (`source_key`) sind interne Kennungen. Wer sie liest, gibt sie nicht weiter: nicht in eine
    Antwort an die Oberflaeche, nicht in eine Datei.
    """
    return _build(data_space_path, context_value, tax_year, asset_types, True, selection)


def _average_wallets(worlds, year: str, ledger_types, chosen_accounts, chosen_assets, assets, label) -> list[dict[str, str]]:
    """Wallets mit Durchschnittsmethode in diesem Jahr (rc.294, BMF 06.03.2025 Rn. 61/62, Angabe nach Rn. 103): je Coin und Konto
    der Abschnitt, der vor Jahresende begann und nicht vor Jahresbeginn endete. Alle uebrigen Wallets rechnen FiFo."""
    rows = []
    for world in worlds:
        wallets: dict[tuple[str, str], list[dict]] = {}
        for segment in world.get("wallet_segments", []):
            wallets.setdefault((segment["asset_ref"], segment["account_ref"]), []).append(segment)
        for (asset_ref, account_ref), segments in wallets.items():
            asset = assets.get(asset_ref, {})
            if _tax_asset_type(asset.get("asset_type")) not in ledger_types or (chosen_assets is not None and asset_ref not in chosen_assets) or (
                    chosen_accounts is not None and account_ref not in chosen_accounts):
                continue
            segments = sorted(segments, key=lambda row: row["start_local_date"])
            for index, segment in enumerate(segments):
                ends = segments[index + 1]["start_local_date"] if index + 1 < len(segments) else None
                if segment["method"] == "average" and segment["start_local_date"] <= f"{year}-12-31" and (ends is None or ends >= f"{year}-01-01"):
                    rows.append({"asset_label": asset.get("display_name") or "unbekanntes Asset",
                                 "account_label": label(account_ref), "account_ref": account_ref,
                                 "since": segment["start_local_date"]})
    return sorted(rows, key=lambda row: (row["asset_label"].lower(), row["account_label"].lower(), row["since"]))


def _method() -> dict[str, Any]:
    return {
        "consumption_order": "fifo_per_account",
        "holding_period_rule": "calendar_anniversary_inclusive",
        "transfer_treatment": "no_disposal_lots_carried",
        "asset_fee_treatment": "documented_at_event_not_disposal",
        "withdrawal_treatment": "by_purpose_gratuitous_transfer_is_no_disposal",
        "withdrawal_value": "owner_value_else_daily_value",
        "interest_source": "cash_statement_bookings",
        "amount_currency": "EUR",
        "tax_calculated": False,
    }


def _build(data_space_path: str | Path, context_value: Any, tax_year: int, asset_types: Sequence[str], with_keys: bool,
           selection: Any = None) -> dict[str, Any]:
    if isinstance(tax_year, bool) or not isinstance(tax_year, int) or not 2000 <= tax_year <= 2100:
        _abort("simple_tax_report_input_invalid")
    if isinstance(asset_types, (str, bytes)) or not isinstance(asset_types, Sequence) or not asset_types or any(
            kind not in REPORT_TYPES for kind in asset_types) or len(set(asset_types)) != len(asset_types):
        _abort("simple_tax_report_input_invalid")
    try:
        context = activity_reference_scope_v1(context_value)
    except AssetActivityReferenceV1Error:
        _abort("simple_tax_report_input_invalid")
    space = Path(data_space_path)
    year = str(tax_year)
    days = [f"{tax_year - 1}-12-31", f"{tax_year}-12-31"]
    ledger_types = [kind for kind in asset_types if kind != CASH_TYPE]
    chosen_accounts, chosen_assets, chosen_labels = _selection(space, context, selection)
    interest = simple_tax_report_interest_rows_v1(space, context, tax_year) if CASH_TYPE in asset_types else []
    withholding = simple_tax_report_withholding_rows_v1(space, context, tax_year) if any(kind in CAPITAL_TYPES for kind in asset_types) else []
    if chosen_accounts is not None:
        # Gewaehlte Konten: ihre Zinsen und die Quellensteuer ihrer Institute.
        interest = [row for row in interest if row["source_key"]["account_ref"] in chosen_accounts]
        try:
            snapshot = _canonical_snapshot(space / "canonical.sqlite", context)
        except (DesktopProductAssetActivityV1Error, OSError, KeyError, TypeError):
            _abort("simple_tax_report_source_invalid")
        institutes = {(row.get("institution_label") or "").lower() for row in snapshot["accounts"] if row["account_id"] in chosen_accounts}
        withholding = [row for row in withholding if (row["institution_label"] or "").lower() in institutes]
    elif chosen_assets is not None:
        # Gewaehlte Vermoegenswerte ohne Konten: Zinsen gehoeren zu keinem davon.
        interest = []
    # Wofuer Unterlagen gebraucht werden: Konto, Monat und Rolle jedes Vorgangs. Nur fuer Rechenkerne (`with_keys`).
    evidence: set[tuple[str, str, str]] = {(row["source_key"]["account_ref"], row["local_date"][:7], "event_in_year") for row in interest}

    def finish(model: dict[str, Any]) -> dict[str, Any]:
        model["interest"] = [dict(row) if with_keys else {name: value for name, value in row.items() if name != "source_key"} for row in interest]
        model["interest_totals"] = _interest_totals(interest)
        model["withholding"] = [dict(row) for row in withholding]
        model["selection"] = chosen_labels
        if with_keys:
            model["evidence_accounts"] = [{"account_ref": account, "month": month, "role": role} for account, month, role in sorted(evidence)]
        return _plain(model)

    if not ledger_types:
        # Nur Zinsen: Es gibt keine Lots zu belegen, also braucht es weder Buchungsbestand noch FIFO-Stand.
        if not space.is_dir() or space.is_symlink():
            _abort("simple_tax_report_source_invalid")
        return finish({
            "contract_version": CONTRACT, "tax_year": tax_year, "asset_types": sorted(asset_types),
            "fifo_state_status": None, "fifo_state_freshness": None, "method": _method(), "status": "ready",
            "provider_access": False, "network_access": False, "canonical_write": False,
            "disposals": [], "gratuitous_transfers": [], "income": [], "transfers": [], "asset_fees": [],
            "holdings": {day: [] for day in days}, "missing_identifiers": [], "totals": []})
    # Vorabpauschalen (#431): gebucht je Fonds, Konto und Jahr; verteilt auf die Lots zum 31.12. ihres Jahres.
    try:
        bookings = bookings_v1(space, context) if "fund" in asset_types else []
    except AdvanceLumpSumOverviewV1Error:
        _abort("simple_tax_report_source_invalid")
    trace_days = sorted(set(days) | {year_end_v1(row["calculation_year"]) for row in bookings if row["calculation_year"] < tax_year})
    try:
        trace = read_asset_activity_realized_lot_trace_v2(space, context, trace_days)
        references = read_activity_references_v1(space, context)["references"]
        owner_values = read_activity_disposal_values_v1(space, context)["values"]
    except (AssetActivityRealizedStateV2Error, AssetActivityReferenceV1Error):
        _abort("simple_tax_report_source_invalid")
    base = {
        "contract_version": CONTRACT, "tax_year": tax_year, "asset_types": sorted(asset_types),
        "fifo_state_status": trace["status"], "fifo_state_freshness": trace["freshness"],
        "method": _method(),
        "provider_access": False, "network_access": False, "canonical_write": False,
    }
    if trace["status"] != "available" or trace["freshness"] != "fresh":
        # Ohne aktuellen FIFO-Stand gibt es keinen Lot-Nachweis zum heutigen Buchungsbestand; der Report sagt
        # das und bleibt leer, statt einen Nachweis zu frueheren Buchungen als den heutigen auszugeben.
        interest = []
        evidence = set()
        return finish({**base, "status": "fifo_state_absent" if trace["status"] != "available" else "fifo_state_stale",
                       "disposals": [], "gratuitous_transfers": [], "income": [], "transfers": [], "asset_fees": [],
                       "holdings": {day: [] for day in days}, "missing_identifiers": [], "totals": []})
    assets, accounts, ledger = _ledger(space, context)
    allocation = allocate_v1(bookings, {day: [lot for world in trace["worlds"] for lot in world["account_lots_at"].get(day, [])] for day in trace_days}) if bookings else None
    # Tageswerte nur fuer Abgaenge des Jahres, an denen der Eigentuemer keinen Wert eingetragen hat.
    valuation_status, daily_values = _daily_values(space, {
        (world["asset_activity"]["assets"][0]["asset_ref"], event["local_date"])
        for world in trace["worlds"] if len(world["asset_activity"].get("assets") or []) == 1
        for event in world["asset_activity"]["events"]
        if event["event_type"] == "withdrawal" and event["local_date"][:4] == year and event["event_ref"] not in owner_values},
        split_price_adjuster_v1(space, context), context)

    def account_label(ref):
        return accounts.get(ref, {}).get("display_name") or "unbekanntes Konto"

    # FIFO-Wallet aus mehreren Konten (#508): Unterkonto -> Hauptkonto, so wie der FIFO-Stand gerechnet hat. Lose und Bestaende
    # gehoeren dann der Wallet; Vorgaenge bleiben beim Konto, auf dem sie gebucht sind.
    wallet_root: dict[str, str] = {}
    for world in trace["worlds"]:
        for item in world.get("fifo_wallets") or []:
            wallet_root[item["account_ref"]] = item["wallet_account_ref"]
    wallet_members: dict[str, list[str]] = {}
    for member, main in wallet_root.items():
        wallet_members.setdefault(main, []).append(member)

    def root(ref):
        return wallet_root.get(ref, ref)

    def wallet_label(ref):
        main = root(ref)
        if main not in wallet_members:
            return account_label(main)
        return account_label(main) + " mit " + ", ".join(sorted((account_label(member) for member in wallet_members[main]), key=str.lower))

    def wallet_accounts(main):
        return [main, *wallet_members.get(main, [])]

    chosen_roots = None if chosen_accounts is None else {root(account) for account in chosen_accounts}
    touched: dict[str, set[str]] = {}

    def identifier(event_ref):
        entry = references.get(event_ref) or {}
        return {"transaction_id": entry.get("transaction_id"), "counterparty_address": entry.get("counterparty_address"),
                "note": entry.get("note")}

    disposals: list[dict] = []
    gratuitous_transfers: list[dict] = []
    income: list[dict] = []
    transfers: list[dict] = []
    asset_fees: list[dict] = []
    holdings: dict[str, list[dict]] = {day: [] for day in days}
    shown: dict[str, set[str]] = {}
    totals: dict[str, dict[str, Any]] = {}
    for world in trace["worlds"]:
        activity = world["asset_activity"]
        if len(activity.get("assets") or []) != 1:
            _abort("simple_tax_report_source_invalid")
        asset_ref = activity["assets"][0]["asset_ref"]
        asset_type = _tax_asset_type(activity["assets"][0]["asset_type"])
        if asset_type not in ledger_types or (chosen_assets is not None and asset_ref not in chosen_assets):
            continue
        asset_label = assets.get(asset_ref, {}).get("display_name") or "unbekanntes Asset"
        events = {event["event_ref"]: event for event in activity["events"]}
        results = {row["event_ref"]: row for row in world["result"]["event_results"]}
        if set(events) != set(results):
            _abort("simple_tax_report_source_invalid")
        total = totals.setdefault(asset_ref, {
            "asset_label": asset_label, "asset_type": asset_type, "disposal_count": 0, "proceeds": Fraction(0),
            "basis": Fraction(0), "gain": Fraction(0), "gain_within_period": Fraction(0), "gain_outside_period": Fraction(0),
            "disposals_without_value": 0, "disposals_at_daily_value": 0, "gratuitous_transfer_count": 0,
            "income_count": 0, "income": Fraction(0)})
        arrivals: dict[tuple[str, str], list[dict]] = {}
        for movement in world["transfer_lot_movements"]:
            for lot in movement["moved_lots"]:
                arrivals.setdefault((lot["lot_ref"], movement["destination_account_ref"]), []).append(movement)

        def path(lot_ref: str, account_ref: str, before: int, depth: int = 0) -> list[dict]:
            """Die Transfers, die das Lot auf dieses Konto trugen - aelteste zuerst, ueber Zwischenkonten hinweg."""
            steps: list[dict] = []
            if depth > 32:
                _abort("simple_tax_report_source_invalid")
            for movement in arrivals.get((lot_ref, account_ref), []):
                sequence = int(movement["event_sequence"])
                if sequence >= before:
                    continue
                steps.extend(path(lot_ref, movement["source_account_ref"], sequence, depth + 1))
                transfer = events[movement["event_ref"]]
                shown.setdefault(movement["event_ref"], set()).add("transfer_in_lot_path")
                # Die Spur nennt Wallets (#508); Von und Nach sind die Konten, auf denen der Transfer gebucht ist.
                for account in (transfer["account_ref"], transfer["related_account_ref"]):
                    evidence.add((account, transfer["local_date"][:7], "transfer_in_lot_path"))
                steps.append({
                    "event_sequence": sequence, "local_date": transfer["local_date"],
                    "from_account_label": account_label(transfer["account_ref"]),
                    "to_account_label": account_label(transfer["related_account_ref"]), **identifier(movement["event_ref"])})
            unique: dict[int, dict] = {step["event_sequence"]: step for step in steps}
            return [unique[key] for key in sorted(unique)]

        def lot_row(lot: Mapping[str, Any], event: Mapping[str, Any], sequence: int, role: str) -> dict:
            acquisition = events.get(lot["acquisition_event_ref"])
            if acquisition is None or acquisition["event_type"] not in ACQUISITION_TYPES:
                _abort("simple_tax_report_source_invalid")
            shown.setdefault(acquisition["event_ref"], set()).add(role)
            acquired = _acquisition_day(acquisition)
            # Der Beleg der Anschaffung liegt im Monat der Buchung, auch wenn ein frueherer Anschaffungstag eingetragen ist.
            evidence.add((acquisition["account_ref"], acquisition["local_date"][:7], "acquisition"))
            end = _anniversary(acquired)
            quantity = _fraction(lot["quantity_decimal"])
            # Splits zwischen Anschaffung und Abgang (#451): Das Lot steht in neuen Stuecken, die Anschaffung im Beleg in alten.
            # Menge und Kurs der Anschaffung stehen deshalb umgerechnet in den Stuecken des Lots; der Einstand bleibt.
            ratio, split_days = Fraction(1), set()
            for step in world.get("split_steps", []):
                if acquisition["local_date"] < step["effective_local_date"] <= event["local_date"] and (
                        step["account_ref"] is None or step["account_ref"] == root(acquisition["account_ref"])):
                    ratio *= Fraction(int(step["ratio_numerator"]), int(step["ratio_denominator"]))
                    split_days.add(step["effective_local_date"])
            document_quantity = _fraction(acquisition["quantity_decimal"])
            acquired_quantity = None if document_quantity is None else document_quantity * ratio
            document_price = _fraction(acquisition.get("unit_price_decimal"))
            unit_price = None if document_price is None else document_price / ratio
            # Der Hinweis dazu (rc.371): Verhaeltnis, Stichtage und Menge und Kurs des Kaufbelegs.
            split = {"ratio_numerator": str(ratio.numerator), "ratio_denominator": str(ratio.denominator),
                     "effective_local_dates": sorted(split_days), "document_quantity": document_quantity,
                     "document_unit_price": document_price} if ratio != 1 else None
            fee = _fraction(acquisition.get("monetary_fee_decimal"))
            return {
                "acquisition_type": acquisition["event_type"], "acquisition_local_date": acquired,
                "acquisition_local_time": acquisition.get("local_time"), "acquisition_time_zone": acquisition.get("time_zone"),
                "acquisition_account_label": account_label(acquisition["account_ref"]),
                "quantity": quantity, "acquisition_unit_price": unit_price,
                "acquisition_quantity": acquired_quantity,
                "acquisition_fee_share": None if fee is None or not acquired_quantity else fee * quantity / acquired_quantity,
                "basis": _exact(lot["fifo_basis"]),
                "holding_days": _days(acquired, event["local_date"]), "holding_period_end_date": end,
                "within_holding_period": event["local_date"] <= end,
                "acquisition_identifier": identifier(acquisition["event_ref"]),
                "path": path(lot["lot_ref"], root(event["account_ref"]), sequence),
                **({"acquisition_split": split} if split is not None else {}),
                **({"advance_lump_sum": deduction_v1(allocation, lot["lot_ref"], quantity, event["local_date"], world.get("split_steps", []))}
                   if allocation is not None and asset_type == "fund" and role == "acquisition_of_consumed_lot" else {}),
            }

        for event in activity["events"]:
            result = results[event["event_ref"]]
            sequence = int(result["event_sequence"])
            in_year = event["local_date"][:4] == year
            if not in_year or (chosen_accounts is not None and event["account_ref"] not in chosen_accounts):
                continue
            kind = event["event_type"]
            row = ledger.get(event["event_ref"])
            if row is None:
                _abort("simple_tax_report_source_invalid")
            if asset_type == "crypto":
                for account in (event["account_ref"], event.get("related_account_ref")):
                    if account is not None and (chosen_roots is None or root(account) in chosen_roots):
                        touched.setdefault(root(account), set()).add(asset_ref)
            quantity = _fraction(event.get("quantity_decimal"))
            fee_quantity = _fraction(event.get("asset_fee_quantity_decimal"))
            consumed = list(result["consumed_lots"])
            principal: list[Mapping[str, Any]] = []
            if kind in ("sell", "withdrawal"):
                # Der Kern verbraucht erst die veraeusserte Menge, danach getrennt eine in Stueck gezahlte Gebuehr.
                rest = quantity
                while consumed and rest:
                    lot = consumed.pop(0)
                    rest -= _fraction(lot["quantity_decimal"])
                    principal.append(lot)
                if rest != 0:
                    _abort("simple_tax_report_source_invalid")
            # Bei einem Zugang mindert die Stueck-Gebuehr das neue Lot und verbraucht nichts; sonst kommt sie aus den
            # aeltesten Lots des Kontos, und der FIFO-Stand nennt genau diese.
            expected_fee = Fraction(0) if kind in ACQUISITION_TYPES else (fee_quantity or Fraction(0))
            if sum((_fraction(lot["quantity_decimal"]) for lot in consumed), Fraction(0)) != expected_fee:
                _abort("simple_tax_report_source_invalid")
            head = {
                "asset_label": asset_label, "asset_type": asset_type, "account_label": account_label(event["account_ref"]),
                "institution_label": accounts.get(event["account_ref"], {}).get("institution_label"),
                "local_date": event["local_date"], "local_time": event.get("local_time"), "time_zone": event.get("time_zone"),
                "event_sequence": sequence, **identifier(event["event_ref"]),
            }
            if kind in ("sell", "withdrawal", "reward", "dividend") or consumed:
                evidence.add((event["account_ref"], event["local_date"][:7], "event_in_year"))
            if with_keys:
                head["source_key"] = {"event_ref": event["event_ref"], "asset_id": asset_ref, "account_ref": event["account_ref"],
                                      "portfolio_id": row["portfolio_id"], "effective_at_utc": event["effective_at_utc"]}
            if consumed:
                # Gebuehr in Stueck: am Vorgang ausgewiesen, keine Veraeusserung.
                shown.setdefault(event["event_ref"], set()).add("event_with_asset_fee")
                asset_fees.append({
                    **head, "event_type": kind, "fee_quantity": fee_quantity,
                    "related_account_label": None if not event.get("related_account_ref") else account_label(event["related_account_ref"]),
                    "basis": sum((value for value in (_exact(lot["fifo_basis"]) for lot in consumed) if value is not None), Fraction(0))
                    if all(_exact(lot["fifo_basis"]) is not None for lot in consumed) else None,
                    "lots": [lot_row(lot, event, sequence, "acquisition_of_fee_lot") for lot in consumed],
                })
            if kind in ("sell", "withdrawal"):
                treatment = simple_tax_report_treatment_v1(kind, row["movement_context_code"])
                gratuitous = treatment == "gratuitous_transfer"
                shown.setdefault(event["event_ref"], set()).add("gratuitous_transfer" if gratuitous else "disposal")
                unit_price = _fraction(event.get("unit_price_decimal"))
                gross = _fraction(row["gross_economic_amount_decimal"])
                value_source, value_price_date, value_price_basis, value_missing_reason = "booked", None, None, None
                if kind == "sell":
                    proceeds = _fraction(row["net_trade_proceeds_decimal"])
                elif event["event_ref"] in owner_values:
                    proceeds = _fraction(owner_values[event["event_ref"]]["value_eur_decimal"])
                    value_source = "owner_entered"
                elif (asset_ref, event["local_date"]) in daily_values and quantity:
                    daily = daily_values[(asset_ref, event["local_date"])]
                    proceeds = daily["unit_value"] * quantity
                    value_source, value_price_date, value_price_basis = "daily_value", daily["price_source_date"], daily["price_basis"]
                else:
                    proceeds, value_source = None, None
                    value_missing_reason = "valuation_state_unreadable" if valuation_status == "unreadable" else "no_daily_value"
                if kind == "withdrawal" and proceeds is not None:
                    # Der Wert des Abgangs steht fuer den Erloes; eine Gebuehr in Geld kennt der Abgang nicht.
                    gross = proceeds
                    unit_price = proceeds / quantity if quantity else None
                lots = [lot_row(lot, event, sequence, "acquisition_of_consumed_lot") for lot in principal]
                basis = None if any(lot["basis"] is None for lot in lots) else sum((lot["basis"] for lot in lots), Fraction(0))
                for lot in lots:
                    lot["proceeds_share"] = None if proceeds is None else proceeds * lot["quantity"] / quantity
                    lot["gain"] = None if lot["proceeds_share"] is None or lot["basis"] is None else lot["proceeds_share"] - lot["basis"]
                if gratuitous:
                    # Spende, Schenkung, Erbschaft: Die Lots verlassen den Bestand ohne Gegenleistung. Dokumentiert werden
                    # Menge, Lots und der Wert am Tag; ein Gewinn wird nicht gebildet - es ist keine Veraeusserung.
                    for lot in lots:
                        lot["gain"] = None
                gain = None if gratuitous or proceeds is None or basis is None else proceeds - basis
                within = None if gain is None else sum((lot["gain"] for lot in lots if lot["within_holding_period"]), Fraction(0))
                if kind == "sell" and (gain is None or gain != _exact(result["realized_gain"])):
                    _abort("simple_tax_report_source_invalid")
                # Vorabpauschalen mindern den Gewinn in voller Hoehe, ungeachtet der Teilfreistellung (§ 19 Abs. 1 Satz 3 InvStG).
                advance = None if gratuitous or allocation is None or asset_type != "fund" else round_cents_v1(sum((lot["advance_lump_sum"] for lot in lots), Fraction(0)))
                advance_fields = {} if advance is None else {
                    "advance_lump_sum_deduction": advance, "gain_after_advance_lump_sum": None if gain is None else gain - advance}
                (gratuitous_transfers if gratuitous else disposals).append({
                    **head, "disposal_type": kind, "movement_context_code": row["movement_context_code"],
                    "treatment_code": treatment, "counts_as_disposal": not gratuitous,
                    "treatment_label": simple_tax_report_treatment_label_v1(
                        {"treatment_code": treatment, "movement_context_code": row["movement_context_code"]}),
                    "quantity": quantity, "unit_price": unit_price, "gross_amount": gross,
                    "monetary_fee": _fraction(event.get("monetary_fee_decimal")), "net_proceeds": proceeds,
                    "basis": basis, "gain": gain, "gain_within_holding_period": within,
                    "gain_outside_holding_period": None if gain is None else gain - within,
                    "value_recorded": proceeds is not None, "value_source": value_source, "value_price_date": value_price_date,
                    "value_price_basis": value_price_basis, "value_missing_reason": value_missing_reason, "lots": lots, **advance_fields,
                })
                if gratuitous:
                    total["gratuitous_transfer_count"] += 1
                else:
                    total["disposal_count"] += 1
                    total["disposals_at_daily_value"] += value_source == "daily_value"
                    if gain is None:
                        total["disposals_without_value"] += 1
                    else:
                        total["proceeds"] += proceeds
                        total["basis"] += basis
                        total["gain"] += gain
                        total["gain_within_period"] += within
                        total["gain_outside_period"] += gain - within
                        if advance is not None:
                            total["advance_lump_sum_deduction"] = total.get("advance_lump_sum_deduction", Fraction(0)) + advance
            elif kind in ("reward", "dividend"):
                shown.setdefault(event["event_ref"], set()).add("income")
                value = _fraction(row["gross_income_decimal"])
                # Der Buchungsbestand weist den Ertrag auf die Menge nach einer in Stueck einbehaltenen Gebuehr aus.
                net_quantity = None if quantity is None else quantity - (fee_quantity or Fraction(0))
                income.append({
                    **head, "income_type": kind, "quantity": quantity, "fee_quantity": fee_quantity, "net_quantity": net_quantity,
                    "gross_income": value,
                    "value_per_unit": None if value is None or not net_quantity else value / net_quantity,
                })
                total["income_count"] += 1
                total["income"] += value or Fraction(0)
        for movement in world["transfer_lot_movements"]:
            transfer = events[movement["event_ref"]]
            booked = (transfer["account_ref"], transfer["related_account_ref"])
            if transfer["local_date"][:4] != year or (chosen_accounts is not None and not set(booked) & chosen_accounts):
                continue
            shown.setdefault(movement["event_ref"], set()).add("transfer_in_year")
            for account in booked:
                evidence.add((account, transfer["local_date"][:7], "transfer_in_year"))
            moved = []
            for lot in movement["moved_lots"]:
                acquisition = events[lot["acquisition_event_ref"]]
                moved.append({"acquisition_local_date": _acquisition_day(acquisition),
                              "acquisition_account_label": account_label(acquisition["account_ref"]),
                              "quantity": _fraction(lot["quantity_decimal"]), "basis": _exact(lot["fifo_basis"])})
            transfers.append({
                "asset_label": asset_label, "asset_type": asset_type, "local_date": transfer["local_date"],
                "local_time": transfer.get("local_time"), "time_zone": transfer.get("time_zone"),
                "event_sequence": int(movement["event_sequence"]),
                "from_account_label": account_label(booked[0]), "to_account_label": account_label(booked[1]),
                "quantity": _fraction(transfer["quantity_decimal"]),
                "fee_quantity": _fraction(transfer.get("asset_fee_quantity_decimal")),
                **identifier(movement["event_ref"]), "moved_lots": moved, "within_wallet": False, "wallet_label": None,
            })
        # Umschichtung innerhalb einer FIFO-Wallet (#508, BMF 06.03.2025 Rn. 103): keine Veraeusserung, und kein Los bewegt sich -
        # die Lose gehoeren der Wallet. Dokumentiert wird sie trotzdem, mit beiden Konten.
        moved_refs = {movement["event_ref"] for movement in world["transfer_lot_movements"]}
        for event in activity["events"]:
            target = event.get("related_account_ref")
            if event["event_type"] != "transfer" or event["event_ref"] in moved_refs or target is None or event["local_date"][:4] != year:
                continue
            if root(event["account_ref"]) != root(target):
                _abort("simple_tax_report_source_invalid")
            if chosen_accounts is not None and not {event["account_ref"], target} & chosen_accounts:
                continue
            shown.setdefault(event["event_ref"], set()).add("transfer_in_year")
            for account in (event["account_ref"], target):
                evidence.add((account, event["local_date"][:7], "transfer_in_year"))
            transfers.append({
                "asset_label": asset_label, "asset_type": asset_type, "local_date": event["local_date"],
                "local_time": event.get("local_time"), "time_zone": event.get("time_zone"),
                "event_sequence": int(results[event["event_ref"]]["event_sequence"]),
                "from_account_label": account_label(event["account_ref"]), "to_account_label": account_label(target),
                "quantity": _fraction(event["quantity_decimal"]), "fee_quantity": _fraction(event.get("asset_fee_quantity_decimal")),
                **identifier(event["event_ref"]), "moved_lots": [], "within_wallet": True, "wallet_label": wallet_label(target),
            })
        for day in days:
            for lot in world["account_lots_at"][day]:
                if chosen_roots is not None and root(lot["account_ref"]) not in chosen_roots:
                    continue
                if asset_type == "crypto":
                    touched.setdefault(root(lot["account_ref"]), set()).add(asset_ref)
                if day == days[1]:
                    # Ein Bestand zum Jahresende gehoert zu den Unterlagen des Jahres: der Auszug des Kontos zum Dezember (#433),
                    # bei einer FIFO-Wallet aus mehreren Konten der Auszug jedes ihrer Konten.
                    for account in wallet_accounts(root(lot["account_ref"])):
                        evidence.add((account, f"{year}-12", "holding_at_year_end"))
                holdings[day].append({
                    "asset_label": asset_label, "asset_type": asset_type, "account_label": wallet_label(lot["account_ref"]),
                    "quantity": _fraction(lot["remaining_quantity_decimal"]), "acquisition_local_date": lot["acquisition_local_date"],
                    "basis": _exact(lot["remaining_fifo_basis"]), "holding_days": _days(lot["acquisition_local_date"], day),
                })
        missing_source = {**events}
        for event_ref, roles in shown.items():
            if event_ref in missing_source and not (references.get(event_ref) or {}).get("transaction_id"):
                event = missing_source[event_ref]
                totals[asset_ref].setdefault("missing", []).append({
                    "asset_label": asset_label, "event_type": event["event_type"], "local_date": event["local_date"],
                    "local_time": event.get("local_time"), "account_label": account_label(event["account_ref"]),
                    "related_account_label": None if not event.get("related_account_ref") else account_label(event["related_account_ref"]),
                    "quantity": _fraction(event.get("quantity_decimal")), "roles": sorted(roles),
                    "note": (references.get(event_ref) or {}).get("note"),
                })
        shown = {}
    missing = [row for total in totals.values() for row in total.pop("missing", [])]
    model = {
        **base, "status": "ready",
        "disposals": sorted(disposals, key=lambda row: (row["local_date"], row["local_time"] or "", row["asset_label"], row["event_sequence"])),
        "gratuitous_transfers": sorted(gratuitous_transfers, key=lambda row: (row["local_date"], row["local_time"] or "", row["asset_label"], row["event_sequence"])),
        "income": sorted(income, key=lambda row: (row["local_date"], row["local_time"] or "", row["asset_label"], row["event_sequence"])),
        "transfers": sorted(transfers, key=lambda row: (row["local_date"], row["local_time"] or "", row["asset_label"], row["event_sequence"])),
        "asset_fees": sorted(asset_fees, key=lambda row: (row["local_date"], row["local_time"] or "", row["asset_label"], row["event_sequence"])),
        "holdings": {day: sorted(rows, key=lambda row: (row["asset_label"], row["account_label"], row["acquisition_local_date"]))
                     for day, rows in holdings.items()},
        "missing_identifiers": sorted(missing, key=lambda row: (row["local_date"], row["local_time"] or "", row["asset_label"])),
        "totals": sorted((row for row in totals.values() if row["disposal_count"] or row["income_count"] or row["gratuitous_transfer_count"]),
                         key=lambda row: row["asset_label"]),
    }
    # Nur wenn eine Wallet die Durchschnittsmethode traegt - sonst bleibt das Modell, wie es war (FiFo ueberall).
    averaged = _average_wallets(trace["worlds"], year, ledger_types, chosen_roots, chosen_assets, assets, wallet_label)
    if "crypto" in ledger_types:
        # Verwendungsreihenfolge je Wallet (BMF 06.03.2025 Rn. 103): jede Wallet mit Vorgang oder Bestand im Jahr, ihre Konten
        # und ihre Wertermittlung. Eine FIFO-Wallet aus mehreren Konten nennt alle ihre Konten (#508).
        model["wallets"] = sorted(({
            "wallet_label": wallet_label(main), "account_labels": [account_label(account) for account in wallet_accounts(main)],
            "combined": main in wallet_members, "consumption_order": "fifo",
            "average": [{"asset_label": row["asset_label"], "since": row["since"]} for row in averaged if root(row["account_ref"]) == main],
        } for main in touched), key=lambda row: row["wallet_label"].lower())
    for row in averaged:
        row.pop("account_ref")
    if averaged:
        model["valuation_methods"] = averaged
    if "fund" in asset_types:
        # Vorabpauschalen, die in diesem Jahr zufliessen: berechnet fuer das Vorjahr, Zufluss am ersten Werktag (§ 18 Abs. 3 InvStG).
        unallocated = {(row["asset_id"], row["account_id"], row["calculation_year"]) for row in (allocation or {}).get("unallocated", [])}
        try:
            portfolio_of = {row["account_id"]: row.get("portfolio_id") for row in _canonical_snapshot(space / "canonical.sqlite", context)["accounts"]} if bookings else {}
        except (DesktopProductAssetActivityV1Error, OSError, KeyError, TypeError):
            _abort("simple_tax_report_source_invalid")
        inflows = []
        for row in bookings:
            if row["calculation_year"] != tax_year - 1 or (chosen_accounts is not None and row["account_id"] not in chosen_accounts) or (
                    chosen_assets is not None and row["asset_id"] not in chosen_assets):
                continue
            account = accounts.get(row["account_id"], {})
            inflow = {"asset_label": assets.get(row["asset_id"], {}).get("display_name") or "unbekanntes Asset", "asset_type": "fund",
                      "account_label": account_label(row["account_id"]), "institution_label": account.get("institution_label"),
                      "calculation_year": row["calculation_year"], "local_date": inflow_date_v1(row["calculation_year"]),
                      "advance_lump_sum_amount": Fraction(row["amount_decimal"]), "currency": "EUR",
                      "allocated_to_lots": (row["asset_id"], row["account_id"], row["calculation_year"]) not in unallocated}
            if with_keys:
                inflow["source_key"] = {"event_ref": f"advance_lump_sum|{row['asset_id']}|{row['account_id']}|{row['calculation_year']}",
                                        "asset_id": row["asset_id"], "account_ref": row["account_id"], "portfolio_id": portfolio_of.get(row["account_id"]),
                                        "effective_at_utc": inflow["local_date"] + "T00:00:00Z"}
            inflows.append(inflow)
        model["advance_lump_sums"] = sorted(inflows, key=lambda row: (row["asset_label"].lower(), row["account_label"].lower()))
    return finish(model)


_MONEY_KEYS = frozenset({
    "basis", "gain", "proceeds", "proceeds_share", "gross_amount", "monetary_fee", "net_proceeds", "gross_income",
    "gain_within_holding_period", "gain_outside_holding_period", "gain_within_period", "gain_outside_period",
    "acquisition_fee_share", "income", "withholding_amount", "advance_lump_sum", "advance_lump_sum_deduction", "gain_after_advance_lump_sum",
    "advance_lump_sum_amount",
})


def _plain(value: Any, key: str | None = None) -> Any:
    """Bruchzahlen als Text: Geldbetraege exakt und zusaetzlich auf Cent, Mengen und Preise exakt."""
    if isinstance(value, Fraction):
        return _number(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for name, item in value.items():
            result[name] = _plain(item, name)
            if name in _MONEY_KEYS and (isinstance(item, Fraction) or item is None):
                result[name + "_rounded"] = _money(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_plain(item, key) for item in value]
    return value


_TYPE_LABELS = {
    "sell": "Verkauf", "withdrawal": "Abgang", "buy": "Kauf", "reward": "Reward", "dividend": "Dividende",
    "deposit": "Zugang", "stock_dividend": "Stockdividende", "transfer": "Transfer",
}
_ROLE_LABELS = {
    "disposal": "Veräußerung", "gratuitous_transfer": "Unentgeltlicher Abgang", "acquisition_of_consumed_lot": "Anschaffung eines verbrauchten Lots", "income": "Ertrag",
    "transfer_in_year": "Umschichtung im Jahr", "transfer_in_lot_path": "Umschichtung im Weg eines Lots",
    "event_with_asset_fee": "Vorgang mit Gebühr in Stück", "acquisition_of_fee_lot": "Anschaffung eines Gebühren-Lots",
}
# Ein Abgang ist nach seinem Zweck einzuordnen (Festlegung 13.10.2026): Wer mit Coins zahlt oder eine Schuld
# tilgt, veraeussert; wer spendet, schenkt oder vererbt, uebertraegt unentgeltlich - keine Veraeusserung. Ein
# Abgang ohne Einordnung wird vorsorglich als Veraeusserung gefuehrt und so benannt, statt still zu verschwinden.
_WITHDRAWAL_TREATMENT = {
    "payment": "disposal_by_payment", "debt_settlement": "disposal_by_payment",
    "donation": "gratuitous_transfer", "gift": "gratuitous_transfer", "inheritance": "gratuitous_transfer",
}
_CONTEXT_LABELS = {
    "payment": "Zahlung", "debt_settlement": "Schuldentilgung", "donation": "Spende", "gift": "Schenkung",
    "inheritance": "Erbschaft", "custody_exit": "Verwahrausgang", "other": "Sonstiges", "unclassified": "nicht eingeordnet",
    "not_applicable": "nicht eingeordnet",
}


def simple_tax_report_treatment_v1(event_type: str, movement_context_code: Any) -> str:
    """Wie ein Vorgang gefuehrt wird: Verkauf, Veraeusserung durch Zahlung, unentgeltlicher Abgang oder ohne Einordnung."""
    if event_type == "sell":
        return "sale"
    return _WITHDRAWAL_TREATMENT.get(movement_context_code, "purpose_unclassified")


def simple_tax_report_treatment_label_v1(item: Mapping[str, Any]) -> str:
    """Die Einordnung eines Vorgangs in Worten - mit dem Zweck des Abgangs und der steuerlichen Folge."""
    treatment = item.get("treatment_code")
    purpose = _CONTEXT_LABELS.get(item.get("movement_context_code"), "nicht eingeordnet")
    if treatment == "sale":
        return "Verkauf – Veräußerung"
    if treatment == "disposal_by_payment":
        return f"{purpose} – Veräußerung, steuerpflichtig"
    if treatment == "gratuitous_transfer":
        return f"{purpose} – keine Veräußerung, nicht steuerpflichtig"
    return ("Zweck nicht eingeordnet" if purpose == "nicht eingeordnet" else f"{purpose}, Zweck nicht eingeordnet") + " – vorsorglich als Veräußerung geführt"


_ASSET_TYPE_LABELS = {"crypto": "Krypto", "equity": "Aktien", "fund": "Fonds", "commodity": "Rohstoffe", "derivative": "Derivate", "fx": "Devisen",
                      CASH_TYPE: "Cash (Zinsen)"}


def simple_tax_report_method_lines_v1(model: Mapping[str, Any]) -> list[str]:
    """Die Reporteinstellungen in Worten - Teil jedes Reports (BMF-Schreiben vom 06.03.2025, Rn. 90)."""
    kinds = list(model.get("asset_types") or [])
    with_cash = CASH_TYPE in kinds
    combined = [row["wallet_label"] for row in model.get("wallets") or [] if row.get("combined")]
    # Ein Report nur ueber Zinsen belegt keine Lots; die Saetze zu Verbrauchsfolge und Haltedauer gehoeren dort nicht hin.
    lines = [
        "Dieser Report dokumentiert Veräußerungen, Erträge, Umschichtungen und Bestände. Er berechnet keine Steuer und wendet keine Freigrenze an.",
        "Verbrauchsfolge: First in, first out je Konto (walletbezogen). Veräußert wird aus den ältesten Anschaffungen des Kontos, von dem der Vorgang abgeht.",
        *([] if not model.get("valuation_methods") else [
            "Wertermittlung: Durchschnittsmethode (BMF-Schreiben vom 06.03.2025, Rn. 61 f.) für " + "; ".join(
                f"{row['asset_label']} auf {row['account_label']} ab {date.fromisoformat(row['since']).strftime('%d.%m.%Y')}" for row in model["valuation_methods"])
            + ". Die Haltefrist folgt dort der Verbrauchsfolge FiFo; als Anschaffungskosten gilt der Durchschnitt der Wallet. Alle übrigen Wallets: FiFo."]),
        *([] if not combined else [
            "FIFO-Wallet aus mehreren Konten: " + "; ".join(combined) + ". Nach Wahl des Eigentümers rechnen Haupt- und Unterkonto desselben "
            "Instituts als eine Wallet (BMF-Schreiben vom 06.03.2025, Rn. 62), für die ganze Historie: Ein Verkauf verbraucht die ältesten Lots "
            "der ganzen Wallet."]),
        "Umschichtung zwischen eigenen Konten: keine Veräußerung. Sie nimmt die ältesten Lots des Quellkontos mit Anschaffungsdatum und anteiligen Anschaffungskosten mit."
        + ("" if not combined else " Innerhalb einer FIFO-Wallet bewegt sie keine Lots; sie steht mit dem Vermerk „innerhalb der Wallet“ bei den Umschichtungen."),
        "Haltedauer: Tage zwischen Anschaffungs- und Veräußerungstag. Innerhalb der Jahresfrist liegt ein Lot, wenn bis einschließlich des Jahrestags der Anschaffung veräußert wird.",
        "Gebühr in Stück: am jeweiligen Vorgang ausgewiesen und nicht als Veräußerung behandelt; bei einem Zugang (Reward) mindert sie die zugegangene Menge, ältere Lots bleiben unberührt.",
        "Abgang (Withdrawal): nach seinem Zweck eingeordnet. Zahlung und Schuldentilgung sind Veräußerungen (steuerpflichtig). Spende, Schenkung und Erbschaft sind unentgeltliche Übertragungen: keine Veräußerung, nicht steuerpflichtig – sie stehen mit ihren Lots in einem eigenen Abschnitt, ein Gewinn wird nicht gebildet. Ein Abgang ohne Einordnung wird vorsorglich als Veräußerung geführt. Als Erlös bzw. Wert gilt der am Abgang eingetragene Wert, sonst Stückzahl mal Tageswert der Kursquelle am Tag des Abgangs; die Wertquelle steht am Vorgang. Ohne Wert und ohne Kurs ist kein Gewinn ausgewiesen.",
    ] if any(kind != CASH_TYPE for kind in kinds) or not with_cash else [
        "Dieser Report dokumentiert die Zinsgutschriften der Cash-Konten. Er berechnet keine Steuer und wendet keinen Freibetrag an.",
    ]
    if with_cash:
        lines.append(
            "Zinsen: Zinsgutschriften der Cash-Konten, wie sie aus den Kontoauszügen gebucht sind – je Gutschrift Datum, Konto und Betrag in der "
            "Währung des Kontos, dazu die Summe je Konto. Vom Institut einbehaltene Steuern sind nicht erfasst.")
    if "fund" in kinds:
        lines.append(
            "Vorabpauschale: je Fonds und Konto mit dem Betrag der Bank gebucht und den Anteilen zum 31.12. des Jahres zugeordnet – im Erwerbsjahr "
            "um ein Zwölftel je vollem Monat vor dem Erwerb gekürzt. Sie gilt am ersten Werktag des Folgejahres als zugeflossen; beim Verkauf mindern "
            "die auf die verkauften Anteile entfallenden Vorabpauschalen den Gewinn in voller Höhe (§§ 18, 19 Abs. 1 Satz 3 InvStG).")
    if any(kind in CAPITAL_TYPES for kind in kinds):
        lines.append(
            "Anrechenbare ausländische Quellensteuer: je Institut und Jahr ein Betrag, wie ihn der Eigentümer nach der Bescheinigung des "
            "Instituts eingetragen hat. Der Report weist ihn aus; ob und in welcher Höhe er angerechnet wird, steht nicht hier.")
    selection = model.get("selection") or {}
    if selection:
        parts = [f"Konten: {', '.join(selection['accounts'])}" if selection.get("accounts") else None,
                 f"Vermögenswerte: {', '.join(selection['assets'])}" if selection.get("assets") else None]
        lines.append("Auswahl: Der Report enthält nur die gewählten " + " · ".join(part for part in parts if part) + ".")
    return [
        *lines,
        "Beträge in EUR wie gebucht (Erlöse und Erträge brutto, Erlös je Verkauf nach Abzug der Gebühr). Gerechnet wird exakt; ausgegebene Beträge sind kaufmännisch auf Cent gerundet, Summen aus den ungerundeten Werten gebildet.",
        "Datum und Uhrzeit wie gebucht, mit der Zeitzone der Buchung.",
    ]


def simple_tax_report_wallet_valuation_label_v1(item: Mapping[str, Any]) -> str:
    """Die Wertermittlung einer Wallet in Worten (Rn. 61/62): FiFo oder - je Coin ab einem Tag - die Durchschnittsmethode."""
    average = item.get("average") or []
    if not average:
        return "FiFo"
    return "Durchschnittsmethode für " + "; ".join(
        f"{row['asset_label']} ab {date.fromisoformat(row['since']).strftime('%d.%m.%Y')}" for row in average) + "; übrige Coins FiFo"


def simple_tax_report_value_source_label_v1(item: Mapping[str, Any]) -> str:
    """Woher der Erlös einer Veräußerung stammt, in Worten."""
    source = item.get("value_source")
    if source == "booked":
        return "gebucht"
    if source == "owner_entered":
        return "am Abgang eingetragen"
    if source == "daily_value":
        day = item.get("value_price_date") or item.get("local_date")
        return f"Tageswert der Kursquelle vom {day}" + ("" if item.get("value_price_basis") == "observed" else " (fortgeschrieben)")
    return "kein Wert – Bewertungsstand nicht lesbar" if item.get("value_missing_reason") == "valuation_state_unreadable" else "kein Wert – kein Kurs für den Tag"


def _comma(text: Any) -> str:
    return "" if text is None else str(text).replace(".", ",")


def _split_text(split: Mapping[str, Any] | None) -> str:
    """Ein Split zwischen Kauf und Verkauf (#451): Stueckzahl und Kaufpreis der Zeile stehen in Stuecken nach dem Split."""
    if not split:
        return ""
    price = "" if split["document_unit_price"] is None else " à " + _comma(split["document_unit_price"])
    return (f"{split['ratio_numerator']} : {split['ratio_denominator']} am {', '.join(split['effective_local_dates'])}; "
            f"Kaufbeleg {_comma(split['document_quantity'])} Stück{price}")


def _safe(text: Any) -> str:
    """Kein Zellinhalt, den eine Tabellenkalkulation als Formel liest."""
    value = "" if text is None else str(text).replace("\r", " ").replace("\n", " ")
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


def _id_text(identifier: Mapping[str, Any], account_label: str) -> str:
    return _safe(f"{identifier.get('transaction_id') or '(keine Kennung)'} bei {account_label}")


def _path_text(path: Sequence[Mapping[str, Any]]) -> str:
    return _safe(" | ".join(
        f"{step['local_date']} {step['from_account_label']} → {step['to_account_label']}"
        + (f" [{step['transaction_id']}]" if step.get("transaction_id") else " [ohne Kennung]") for step in path))


def render_simple_tax_report_csv_v1(model: Mapping[str, Any], generated_at_utc: str, notes: Sequence[str] = ()) -> str:
    """Der Report als Tabelle: Semikolon, Dezimalkomma, ISO-Datum; ein Abschnitt je Sicht."""
    import csv
    import io
    if not isinstance(model, Mapping) or model.get("contract_version") != CONTRACT or isinstance(notes, (str, bytes)):
        _abort("simple_tax_report_input_invalid")
    year = model["tax_year"]
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    row = writer.writerow
    row([f"Steuerreport {year} – einfache Fassung (Dokumentation ohne Steuerberechnung)"])
    row(["Assetklassen", ", ".join(_ASSET_TYPE_LABELS.get(kind, kind) for kind in model["asset_types"])])
    row(["Erstellt (UTC)", generated_at_utc])
    row(["FIFO-Stand", "nicht benötigt – der Report enthält nur Zinsen" if model["status"] == "ready" and all(kind == CASH_TYPE for kind in model["asset_types"]) else {
        "ready": "aktuell",
        "fifo_state_stale": "nicht aktuell – seit der letzten Fortschreibung wurden Buchungen geändert; der Report enthält deshalb keine Vorgänge",
    }.get(model["status"], "nicht vorhanden – der Report enthält keine Vorgänge")])
    for line in simple_tax_report_method_lines_v1(model):
        row(["Methode", line])
    for note in notes:
        row(["Anmerkung", _safe(note)])
    if "wallets" in model:
        # Verwendungsreihenfolge je Wallet (BMF 06.03.2025 Rn. 103).
        row([])
        row(["Verwendungsreihenfolge je Wallet"])
        row(["Wallet", "Konten", "Verbrauchsfolge (Haltefrist)", "Wertermittlung"])
        for item in model["wallets"]:
            row([_safe(item["wallet_label"]), _safe(", ".join(item["account_labels"])), "FiFo", simple_tax_report_wallet_valuation_label_v1(item)])
    # Ein Report nur ueber Zinsen belegt keine Lots: Die Abschnitte A bis I gehoeren dort nicht hin.
    if any(kind != CASH_TYPE for kind in model["asset_types"]):
        row([])
        row(["A. Veräußerungen – eine Zeile je Vorgang"])
        row(["Steuerjahr", "Transaktionsart", "Einordnung", "Vermögenswert", "Konto", "Institut", "Datum", "Uhrzeit", "Zeitzone", "Stückzahl", "Stückpreis",
             "Bruttoerlös", "Gebühr", "Erlös nach Gebühr", "Anschaffungskosten", "GuV Brutto", "davon innerhalb Jahresfrist",
             "davon außerhalb Jahresfrist", "Wertquelle", "Transaktions-ID", "Adresse der Gegenseite", "Notiz"])
        for item in model["disposals"]:
            row([year, _TYPE_LABELS[item["disposal_type"]], item["treatment_label"], _safe(item["asset_label"]), _safe(item["account_label"]), _safe(item["institution_label"]),
                 item["local_date"], item["local_time"] or "", item["time_zone"] or "", _comma(item["quantity"]), _comma(item["unit_price"]),
                 _comma(item["gross_amount_rounded"]), _comma(item["monetary_fee_rounded"]), _comma(item["net_proceeds_rounded"]),
                 _comma(item["basis_rounded"]), _comma(item["gain_rounded"]), _comma(item["gain_within_holding_period_rounded"]),
                 _comma(item["gain_outside_holding_period_rounded"]), simple_tax_report_value_source_label_v1(item),
                 _safe(item["transaction_id"]), _safe(item["counterparty_address"]), _safe(item["note"])])
        row([])
        row(["B. Veräußerungen – eine Zeile je verbrauchtem Lot"])
        row(["Steuerjahr", "Transaktionsart", "Einordnung", "Vermögenswert", "Konto (Veräußerung)", "Kaufdatum", "Datum Verkauf", "Haltedauer [Tage]",
             "Ende der Jahresfrist", "Innerhalb Jahresfrist", "GuV Brutto", "GuV innerhalb Jahresfrist", "Stückzahl", "Anschaffungsart",
             "Konto (Anschaffung)", "Kauf: Stückpreis", "Kauf: Gebühr (anteilig)", "Kauf: Gesamtpreis (Anschaffungskosten)",
             "Verkauf: Stückpreis", "Verkauf: Gesamtpreis (Erlös nach Gebühr, anteilig)", "Weg über Umschichtungen",
             "Kauf: ID – Konto", "Verkauf: ID – Konto", "Split zwischen Kauf und Verkauf"])
        for item in model["disposals"]:
            for lot in item["lots"]:
                row([year, _TYPE_LABELS[item["disposal_type"]], item["treatment_label"], _safe(item["asset_label"]),
                     _safe(item["account_label"]), lot["acquisition_local_date"],
                     item["local_date"], lot["holding_days"], lot["holding_period_end_date"], "ja" if lot["within_holding_period"] else "nein",
                     _comma(lot["gain_rounded"]), _comma(lot["gain_rounded"] if lot["within_holding_period"] else ("0.00" if lot["gain_rounded"] is not None else None)),
                     _comma(lot["quantity"]), _TYPE_LABELS.get(lot["acquisition_type"], lot["acquisition_type"]), _safe(lot["acquisition_account_label"]),
                     _comma(lot["acquisition_unit_price"]), _comma(lot["acquisition_fee_share_rounded"]), _comma(lot["basis_rounded"]),
                     _comma(item["unit_price"]), _comma(lot["proceeds_share_rounded"]), _path_text(lot["path"]),
                     _id_text(lot["acquisition_identifier"], lot["acquisition_account_label"]), _id_text(item, item["account_label"]),
                     _split_text(lot.get("acquisition_split"))])
        row([])
        row(["C. Unentgeltliche Abgänge (Spende, Schenkung, Erbschaft) – keine Veräußerung, nicht steuerpflichtig – eine Zeile je abgegangenem Lot"])
        row(["Steuerjahr", "Einordnung", "Vermögenswert", "Konto", "Datum", "Uhrzeit", "Zeitzone", "Stückzahl (Abgang)", "Wert am Tag des Abgangs",
             "Wertquelle", "Stückzahl (Lot)", "Kaufdatum des Lots", "Konto der Anschaffung", "Anschaffungskosten des Lots", "Haltedauer [Tage]",
             "Kauf: ID – Konto", "Transaktions-ID", "Adresse der Gegenseite", "Notiz"])
        for item in model["gratuitous_transfers"]:
            for lot in item["lots"]:
                row([year, item["treatment_label"], _safe(item["asset_label"]), _safe(item["account_label"]), item["local_date"],
                     item["local_time"] or "", item["time_zone"] or "", _comma(item["quantity"]), _comma(item["net_proceeds_rounded"]),
                     simple_tax_report_value_source_label_v1(item), _comma(lot["quantity"]), lot["acquisition_local_date"],
                     _safe(lot["acquisition_account_label"]), _comma(lot["basis_rounded"]), lot["holding_days"],
                     _id_text(lot["acquisition_identifier"], lot["acquisition_account_label"]), _safe(item["transaction_id"]),
                     _safe(item["counterparty_address"]), _safe(item["note"])])
        row([])
        row(["D. Erträge"])
        row(["Steuerjahr", "Ertragsart", "Vermögenswert", "Konto", "Institut", "Datum", "Uhrzeit", "Zeitzone", "Stückzahl", "Gebühr in Stück",
             "Stückzahl nach Gebühr", "Wert je Stück bei Zufluss", "Bruttoertrag", "Transaktions-ID", "Notiz"])
        for item in model["income"]:
            row([year, _TYPE_LABELS[item["income_type"]], _safe(item["asset_label"]), _safe(item["account_label"]), _safe(item["institution_label"]),
                 item["local_date"], item["local_time"] or "", item["time_zone"] or "", _comma(item["quantity"]), _comma(item["fee_quantity"]),
                 _comma(item["net_quantity"]), _comma(item["value_per_unit"]), _comma(item["gross_income_rounded"]),
                 _safe(item["transaction_id"]), _safe(item["note"])])
        row([])
        row(["E. Umschichtungen zwischen eigenen Konten – eine Zeile je mitgenommenem Lot"])
        row(["Datum", "Uhrzeit", "Zeitzone", "Vermögenswert", "Von Konto", "Nach Konto", "Stückzahl (Transfer)", "Gebühr in Stück (Transfer)",
             "Stückzahl (Lot)", "Kaufdatum des Lots", "Konto der Anschaffung", "Anschaffungskosten des Teils", "Transaktions-ID", "Adresse der Gegenseite", "Notiz"])
        for item in model["transfers"]:
            if item.get("within_wallet"):
                # Innerhalb einer FIFO-Wallet (#508) bewegt sich kein Lot: eine Zeile mit dem Vermerk statt der Lots.
                row([item["local_date"], item["local_time"] or "", item["time_zone"] or "", _safe(item["asset_label"]), _safe(item["from_account_label"]),
                     _safe(item["to_account_label"]), _comma(item["quantity"]), _comma(item["fee_quantity"]),
                     "innerhalb der Wallet " + _safe(item["wallet_label"]) + " – keine Lots bewegt", "", "", "",
                     _safe(item["transaction_id"]), _safe(item["counterparty_address"]), _safe(item["note"])])
            for lot in item["moved_lots"]:
                row([item["local_date"], item["local_time"] or "", item["time_zone"] or "", _safe(item["asset_label"]), _safe(item["from_account_label"]),
                     _safe(item["to_account_label"]), _comma(item["quantity"]), _comma(item["fee_quantity"]), _comma(lot["quantity"]),
                     lot["acquisition_local_date"], _safe(lot["acquisition_account_label"]), _comma(lot["basis_rounded"]),
                     _safe(item["transaction_id"]), _safe(item["counterparty_address"]), _safe(item["note"])])
        row([])
        row(["F. Gebühren in Stück – am Vorgang ausgewiesen, keine Veräußerung – eine Zeile je verbrauchtem Lot"])
        row(["Datum", "Uhrzeit", "Vorgang", "Vermögenswert", "Konto", "Gegenkonto", "Gebühr in Stück (Vorgang)", "Stückzahl (Lot)", "Kaufdatum des Lots",
             "Anschaffungskosten des Teils", "Transaktions-ID des Vorgangs", "Notiz des Vorgangs"])
        for item in model["asset_fees"]:
            for lot in item["lots"]:
                row([item["local_date"], item["local_time"] or "", _TYPE_LABELS.get(item["event_type"], item["event_type"]), _safe(item["asset_label"]),
                     _safe(item["account_label"]), _safe(item["related_account_label"]), _comma(item["fee_quantity"]), _comma(lot["quantity"]),
                     lot["acquisition_local_date"], _comma(lot["basis_rounded"]), _safe(item["transaction_id"]), _safe(item["note"])])
        row([])
        row(["G. Bestände je Konto und Lot zum Stichtag"])
        row(["Stichtag", "Vermögenswert", "Konto", "Stückzahl", "Kaufdatum", "Anschaffungskosten", "Haltedauer am Stichtag [Tage]"])
        for day in sorted(model["holdings"]):
            for lot in model["holdings"][day]:
                row([day, _safe(lot["asset_label"]), _safe(lot["account_label"]), _comma(lot["quantity"]), lot["acquisition_local_date"],
                     _comma(lot["basis_rounded"]), lot["holding_days"]])
        row([])
        row(["H. Summen je Vermögenswert"])
        row(["Vermögenswert", "Veräußerungen", "davon ohne Wert", "davon mit Tageswert angesetzt", "Erlöse nach Gebühr", "Anschaffungskosten", "GuV Brutto",
             "davon innerhalb Jahresfrist", "davon außerhalb Jahresfrist", "Erträge (Anzahl)", "Erträge (Brutto)", "Unentgeltliche Abgänge (Anzahl)"])
        for item in model["totals"]:
            row([_safe(item["asset_label"]), item["disposal_count"], item["disposals_without_value"], item["disposals_at_daily_value"], _comma(item["proceeds_rounded"]),
                 _comma(item["basis_rounded"]), _comma(item["gain_rounded"]), _comma(item["gain_within_period_rounded"]),
                 _comma(item["gain_outside_period_rounded"]), item["income_count"], _comma(item["income_rounded"]), item["gratuitous_transfer_count"]])
        row([])
        row(["I. Buchungen dieses Reports ohne Transaktions-ID"])
        row(["Datum", "Uhrzeit", "Art", "Vermögenswert", "Konto", "Gegenkonto", "Stückzahl", "Rolle im Report", "vorhandene Notiz"])
        for item in model["missing_identifiers"]:
            row([item["local_date"], item["local_time"] or "", _TYPE_LABELS.get(item["event_type"], item["event_type"]), _safe(item["asset_label"]),
                 _safe(item["account_label"]), _safe(item["related_account_label"]), _comma(item["quantity"]),
                 " / ".join(_ROLE_LABELS.get(role, role) for role in item["roles"]), _safe(item["note"])])
    if CASH_TYPE in model["asset_types"]:
        # Zinsen stehen nur im Report, wenn sie gewaehlt sind; ein Report ohne sie bleibt, wie er war.
        row([])
        row(["J. Zinsen der Cash-Konten – eine Zeile je Gutschrift"])
        row(["Steuerjahr", "Institut", "Konto", "Datum", "Währung", "Zinsertrag"])
        for item in model.get("interest") or []:
            row([year, _safe(item["institution_label"]), _safe(item["account_label"]), item["local_date"], item["currency"],
                 _comma(item["gross_income_rounded"])])
        row([])
        row(["K. Zinsen – Summe je Konto"])
        row(["Institut", "Konto", "Währung", "Gutschriften", "Zinsertrag"])
        for item in model.get("interest_totals") or []:
            row([_safe(item["institution_label"]), _safe(item["account_label"]), item["currency"], item["interest_count"], _comma(item["income_rounded"])])
    if any(kind in CAPITAL_TYPES for kind in model["asset_types"]):
        # Die Quellensteuer steht nur bei Klassen mit Kapitalertraegen; ein Krypto-Report bleibt, wie er war (#432).
        row([])
        row(["L. Anrechenbare ausländische Quellensteuer – eigene Angabe je Institut"])
        row(["Steuerjahr", "Institut", "Währung", "Betrag"])
        for item in model.get("withholding") or []:
            row([year, _safe(item["institution_label"] or "ohne Institutsangabe"), item["currency"], _comma(item["withholding_amount_rounded"])])
    if "fund" in model["asset_types"] and model.get("status") == "ready":
        # Vorabpauschalen nur bei Fonds (#431): was im Jahr zufliesst, und um wie viel sie Gewinne beim Verkauf mindern.
        row([])
        row(["M. Vorabpauschalen – Zufluss in diesem Jahr (berechnet für das Vorjahr)"])
        row(["Steuerjahr", "Fonds", "Konto", "Institut", "Jahr der Berechnung", "Zufluss am", "Betrag laut Bank", "Anteilen zum 31.12. zugeordnet"])
        for item in model.get("advance_lump_sums") or []:
            row([year, _safe(item["asset_label"]), _safe(item["account_label"]), _safe(item["institution_label"]), item["calculation_year"], item["local_date"],
                 _comma(item["advance_lump_sum_amount_rounded"]), "ja" if item["allocated_to_lots"] else "nein – kein Bestand zum 31.12."])
        row([])
        row(["N. Vorabpauschalen – Minderung des Veräußerungsgewinns (§ 19 Abs. 1 Satz 3 InvStG)"])
        row(["Datum", "Fonds", "Konto", "Gewinn", "angesetzte Vorabpauschalen", "Gewinn nach Vorabpauschalen"])
        for item in model["disposals"]:
            if item.get("advance_lump_sum_deduction") not in (None, "0"):
                row([item["local_date"], _safe(item["asset_label"]), _safe(item["account_label"]), _comma(item["gain_rounded"]),
                     _comma(item["advance_lump_sum_deduction_rounded"]), _comma(item["gain_after_advance_lump_sum_rounded"])])
    return "\ufeff" + out.getvalue()


__all__ = [
    "ASSET_TYPES", "CASH_TYPE", "FAILURE_CODES", "REPORT_TYPES", "SimpleTaxReportV1Error", "build_simple_tax_report_v1", "render_simple_tax_report_csv_v1", "simple_tax_report_wallet_valuation_label_v1",
    "build_simple_tax_report_with_keys_v1", "simple_tax_report_interest_rows_v1", "simple_tax_report_method_lines_v1", "simple_tax_report_treatment_label_v1", "simple_tax_report_treatment_v1",
    "simple_tax_report_v1_error_codes", "simple_tax_report_value_source_label_v1",
]
