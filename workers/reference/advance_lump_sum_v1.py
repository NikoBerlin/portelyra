"""Was eine gebuchte Vorabpauschale steuerlich bewirkt - gerechnet beim Lesen, aus dem Lot-Nachweis des Buchungsbestands (#431).

- Zufluss am ersten Werktag des Folgejahres (§ 18 Abs. 3 InvStG): ein Kapitalertrag dieses Jahres, mit der
  Teilfreistellung des Fonds (§ 20 InvStG).
- Verteilung auf die Lots, die am 31.12. des Jahres auf dem Konto liegen, nach Stueckzahl; im Erwerbsjahr um ein
  Zwoelftel je vollem Monat vor dem Erwerbsmonat gekuerzt (§ 18 Abs. 2 InvStG).
- Minderung des Veraeusserungsgewinns um die waehrend der Besitzzeit angesetzten Vorabpauschalen, in voller Hoehe und
  ungeachtet der Teilfreistellung (§ 19 Abs. 1 Satz 3 InvStG): je verkauftem Stueck eines Lots die Vorabpauschalen,
  die ihm zu einem 31.12. vor dem Verkauf zugeteilt wurden.

Liest nur. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from migrations.reference.advance_lump_sum_v1 import (
    AdvanceLumpSumV1Error, advance_lump_sum_scope_v1, read_advance_lump_sums_v1, record_advance_lump_sums_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityV1Error, _canonical_snapshot
from workers.reference.asset_activity_realized_state_v2 import AssetActivityRealizedStateV2Error, read_asset_activity_realized_lot_trace_v2

CONTRACT = "advance_lump_sum_overview_v1"
FAILURE_CODES = ("advance_lump_sum_overview_input_invalid", "advance_lump_sum_overview_source_invalid")


class AdvanceLumpSumOverviewV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise AdvanceLumpSumOverviewV1Error(code if code in FAILURE_CODES else "advance_lump_sum_overview_source_invalid")


def year_end_v1(year: int) -> str:
    return f"{year:04d}-12-31"


def inflow_date_v1(calculation_year: int) -> str:
    """Der erste Werktag des Folgejahres: der 2. Januar, faellt er auf einen Sonntag, der 3."""
    day = date(calculation_year + 1, 1, 2)
    if day.weekday() == 6:
        day += timedelta(days=1)
    return day.isoformat()


def _month_factor(acquisition_local_date: str, calculation_year: int) -> Fraction:
    """Im Erwerbsjahr ein Zwoelftel weniger je vollem Monat vor dem Erwerbsmonat (§ 18 Abs. 2 InvStG)."""
    if int(acquisition_local_date[:4]) != calculation_year:
        return Fraction(1)
    return Fraction(13 - int(acquisition_local_date[5:7]), 12)


def allocate_v1(bookings: Sequence[Mapping[str, Any]], lots_at: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Teilt jede Buchung auf die Lots zum 31.12. ihres Jahres - je Stueck eines Lots ein Betrag.

    `bookings`: asset_id, account_id, calculation_year, amount_decimal. `lots_at`: je Stichtag die Lots wie im Lot-Nachweis
    (asset_ref, account_ref, lot_ref, remaining_quantity_decimal, acquisition_local_date). Eine Buchung ohne Bestand am
    Stichtag laesst sich keinem Lot zuteilen; sie wird genannt und mindert keinen Gewinn.
    """
    per_unit: dict[str, list[dict[str, Any]]] = {}
    unallocated = []
    for booking in bookings:
        year = int(booking["calculation_year"])
        amount = Fraction(str(booking["amount_decimal"]))
        lots = [lot for lot in lots_at.get(year_end_v1(year), [])
                if lot["asset_ref"] == booking["asset_id"] and lot["account_ref"] == booking["account_id"]
                and lot["remaining_quantity_decimal"] is not None and Fraction(lot["remaining_quantity_decimal"]) > 0]
        weights = [(lot, Fraction(lot["remaining_quantity_decimal"]) * _month_factor(lot["acquisition_local_date"], year)) for lot in lots]
        total = sum((weight for _, weight in weights), Fraction(0))
        if not lots or total <= 0:
            unallocated.append(dict(booking))
            continue
        for lot, _ in weights:
            unit = amount * _month_factor(lot["acquisition_local_date"], year) / total
            per_unit.setdefault(lot["lot_ref"], []).append({"calculation_year": year, "account_ref": booking["account_id"], "per_unit": unit})
    return {"per_unit": per_unit, "unallocated": unallocated}


def deduction_v1(allocation: Mapping[str, Any], lot_ref: str, quantity: Fraction, sale_local_date: str,
                 splits: Sequence[Mapping[str, Any]] = ()) -> Fraction:
    """Die Vorabpauschalen, die auf die verkauften Stuecke eines Lots entfallen - aus Jahren, deren 31.12. vor dem Verkauf liegt.

    Lag dasselbe Lot zu einem Stichtag auf mehreren Konten, gilt je Stueck der nach Stueckzahl gewogene Betrag; das
    ergibt sich aus der Zuteilung je Stueck von selbst. Ein Split zwischen dem 31.12. und dem Verkauf (#451) teilt den Betrag je
    Stueck im Verhaeltnis; `splits` sind die Schritte der Lot-Spur (effective_local_date, ratio_numerator, ratio_denominator).
    """
    entries = [entry for entry in allocation["per_unit"].get(lot_ref, []) if year_end_v1(entry["calculation_year"]) < sale_local_date]
    by_year: dict[int, list[Fraction]] = {}
    for entry in entries:
        by_year.setdefault(entry["calculation_year"], []).append(entry["per_unit"])

    def ratio_after(year: int) -> Fraction:
        ratio = Fraction(1)
        for step in splits:
            if year_end_v1(year) < step["effective_local_date"] <= sale_local_date:
                ratio *= Fraction(int(step["ratio_numerator"]), int(step["ratio_denominator"]))
        return ratio
    # Mehrere Konten zu einem Stichtag: das Mittel je Stueck; der Regelfall ist ein Eintrag je Jahr.
    return quantity * sum((sum(values, Fraction(0)) / len(values) / ratio_after(year) for year, values in by_year.items()), Fraction(0))


def round_cents_v1(value: Fraction) -> Fraction:
    """Auf Cent, kaufmaennisch - wie eine Bank die angesetzte Vorabpauschale eines Verkaufs ausweist.

    Die Zuteilung je Anteil kann periodisch werden (10 Euro auf 7 Anteile); das Regelmodul rechnet nur mit endlichen
    Dezimalzahlen. Gerundet wird der Betrag je Verkauf, nicht der je Anteil.
    """
    cents = value * 100
    whole = cents.numerator // cents.denominator
    rest = cents - whole
    return Fraction(whole + (1 if rest >= Fraction(1, 2) else 0), 100)


def bookings_v1(space: str | Path, context_value: Any) -> list[dict[str, Any]]:
    """Die gueltigen Buchungen des Datenraums (mit den Kennungen des Bestands) - fuer Rechenkerne."""
    try:
        return read_advance_lump_sums_v1(space, context_value)["bookings"]
    except AdvanceLumpSumV1Error:
        _abort("advance_lump_sum_overview_source_invalid")
        return []


def _token(context: Any, asset_id: str, account_id: str) -> str:
    material = "|".join(("advance-lump-sum-row-v1", context.tenant_id, context.user_id, context.data_space_id, asset_id, account_id))
    return "vpf_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _rows(space: Path, context: Any, calculation_year: int) -> tuple[str, list[dict[str, Any]]]:
    """Je Fonds und Konto: Stueckzahl am 31.12. und gebuchter Betrag - mit den Kennungen, nur fuer diesen Modul."""
    try:
        snapshot = _canonical_snapshot(space / "canonical.sqlite", context)
        trace = read_asset_activity_realized_lot_trace_v2(space, context, [year_end_v1(calculation_year)])
    except (DesktopProductAssetActivityV1Error, AssetActivityRealizedStateV2Error, OSError, KeyError, TypeError):
        _abort("advance_lump_sum_overview_source_invalid")
    assets = {row["asset_id"]: row for row in snapshot["assets"]}
    accounts = {row["account_id"]: row for row in snapshot["accounts"]}
    status = "ready" if trace["status"] == "available" and trace["freshness"] == "fresh" else (
        "fifo_state_absent" if trace["status"] != "available" else "fifo_state_stale")
    held: dict[tuple[str, str], Fraction] = {}
    if status == "ready":
        for world in trace["worlds"]:
            for lot in world["account_lots_at"].get(year_end_v1(calculation_year), []):
                if (assets.get(lot["asset_ref"]) or {}).get("asset_type") not in ("fund", "etf") or lot["remaining_quantity_decimal"] is None:
                    continue
                key = (lot["asset_ref"], lot["account_ref"])
                held[key] = held.get(key, Fraction(0)) + Fraction(lot["remaining_quantity_decimal"])
    booked = {(row["asset_id"], row["account_id"]): row["amount_decimal"] for row in bookings_v1(space, context)
              if row["calculation_year"] == calculation_year}
    rows = []
    for key in sorted(set(held) | set(booked), key=lambda key: ((assets.get(key[0]) or {}).get("display_name", "").lower(),
                                                              (accounts.get(key[1]) or {}).get("display_name", "").lower())):
        asset, account = assets.get(key[0]) or {}, accounts.get(key[1]) or {}
        rows.append({"asset_id": key[0], "account_id": key[1], "token": _token(context, *key), "fund_label": asset.get("display_name") or "unbekannter Fonds",
                     "account_label": account.get("display_name") or "unbekanntes Konto", "institution_label": account.get("institution_label") or None,
                     "quantity": held.get(key), "amount_decimal": booked.get(key)})
    return status, rows


def advance_lump_sum_overview_v1(data_space_path: str | Path, context_value: Any, calculation_year: int) -> dict[str, Any]:
    """Fuer die Eingabe: je Fonds und Konto mit Bestand am 31.12. des Jahres die Stueckzahl und der gebuchte Betrag. Liest nur."""
    if isinstance(calculation_year, bool) or not isinstance(calculation_year, int) or not 2018 <= calculation_year <= 2100:
        _abort("advance_lump_sum_overview_input_invalid")
    try:
        context = advance_lump_sum_scope_v1(context_value)
    except AdvanceLumpSumV1Error:
        _abort("advance_lump_sum_overview_input_invalid")
    status, rows = _rows(Path(data_space_path), context, calculation_year)
    public = [{"token": row["token"], "fund_label": row["fund_label"], "account_label": row["account_label"], "institution_label": row["institution_label"],
               "quantity_decimal": None if row["quantity"] is None else _text(row["quantity"]), "amount_decimal": row["amount_decimal"]} for row in rows]
    return {"contract_version": CONTRACT, "status": status, "calculation_year": calculation_year, "inflow_date": inflow_date_v1(calculation_year),
            "rows": public, "provider_access": False, "network_access": False, "canonical_write": False}


def record_advance_lump_sums_by_token_v1(data_space_path: str | Path, context_value: Any, calculation_year: int, entries: Any,
                                          recorded_at_utc: str, confirmed: bool) -> dict[str, Any]:
    """Speichert Betraege zu den Zeilen der Uebersicht - die Oberflaeche kennt nur deren Marken."""
    if isinstance(calculation_year, bool) or not isinstance(calculation_year, int) or not 2018 <= calculation_year <= 2100:
        _abort("advance_lump_sum_overview_input_invalid")
    try:
        context = advance_lump_sum_scope_v1(context_value)
    except AdvanceLumpSumV1Error:
        _abort("advance_lump_sum_overview_input_invalid")
    _, rows = _rows(Path(data_space_path), context, calculation_year)
    known = {row["token"]: row for row in rows}
    if not isinstance(entries, list) or not entries or any(not isinstance(entry, dict) or set(entry) != {"token", "amount_decimal"} or entry["token"] not in known
                                                         for entry in entries):
        _abort("advance_lump_sum_overview_input_invalid")
    try:
        return record_advance_lump_sums_v1(data_space_path, context, [
            {"asset_id": known[entry["token"]]["asset_id"], "account_id": known[entry["token"]]["account_id"], "calculation_year": calculation_year,
             "amount_decimal": entry["amount_decimal"]} for entry in entries], recorded_at_utc, confirmed)
    except AdvanceLumpSumV1Error as error:
        raise error


def advance_lump_sum_gaps_v1(data_space_path: str | Path, context_value: Any, last_calculation_year: int) -> dict[str, Any]:
    """Je Berechnungsjahr ab 2018: wie viele Fonds je Konto am 31.12. im Bestand lagen und fuer wie viele weder eine
    Vorabpauschale noch 0 eingetragen ist (#472) - damit die Karte sagt, wo etwas fehlt. Ein Lot-Nachweis fuer alle Jahre."""
    if isinstance(last_calculation_year, bool) or not isinstance(last_calculation_year, int) or not 2018 <= last_calculation_year <= 2100:
        _abort("advance_lump_sum_overview_input_invalid")
    try:
        context = advance_lump_sum_scope_v1(context_value)
    except AdvanceLumpSumV1Error:
        _abort("advance_lump_sum_overview_input_invalid")
    space = Path(data_space_path)
    years = list(range(2018, last_calculation_year + 1))
    try:
        snapshot = _canonical_snapshot(space / "canonical.sqlite", context)
        trace = read_asset_activity_realized_lot_trace_v2(space, context, [year_end_v1(year) for year in years])
    except (DesktopProductAssetActivityV1Error, AssetActivityRealizedStateV2Error, OSError, KeyError, TypeError):
        _abort("advance_lump_sum_overview_source_invalid")
    status = "ready" if trace["status"] == "available" and trace["freshness"] == "fresh" else (
        "fifo_state_absent" if trace["status"] != "available" else "fifo_state_stale")
    if status != "ready":
        return {"contract_version": "advance_lump_sum_gaps_v1", "status": status, "years": [], "provider_access": False, "network_access": False,
                "canonical_write": False}
    funds = {row["asset_id"] for row in snapshot["assets"] if row.get("asset_type") in ("fund", "etf")}
    booked = {(row["calculation_year"], row["asset_id"], row["account_id"]) for row in bookings_v1(space, context)}
    rows = []
    for year in years:
        held: dict[tuple[str, str], Fraction] = {}
        for world in trace["worlds"]:
            for lot in world["account_lots_at"].get(year_end_v1(year), []):
                if lot["asset_ref"] in funds and lot["remaining_quantity_decimal"] is not None:
                    key = (lot["asset_ref"], lot["account_ref"])
                    held[key] = held.get(key, Fraction(0)) + Fraction(lot["remaining_quantity_decimal"])
        positions = [key for key, quantity in held.items() if quantity > 0]
        missing = [key for key in positions if (year, *key) not in booked]
        rows.append({"calculation_year": year, "tax_year": year + 1, "held_count": len(positions), "missing_count": len(missing)})
    return {"contract_version": "advance_lump_sum_gaps_v1", "status": "ready", "years": rows, "provider_access": False, "network_access": False,
            "canonical_write": False}


def _text(value: Fraction) -> str:
    from decimal import Decimal, localcontext
    with localcontext() as exact:
        exact.prec = 200
        text = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


__all__ = [
    "AdvanceLumpSumOverviewV1Error", "FAILURE_CODES", "advance_lump_sum_gaps_v1", "advance_lump_sum_overview_v1", "allocate_v1", "bookings_v1", "deduction_v1",
    "inflow_date_v1", "record_advance_lump_sums_by_token_v1", "round_cents_v1", "year_end_v1",
]
