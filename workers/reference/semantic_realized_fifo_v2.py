"""Exact Asset-identity FIFO projection over validated Asset Activity facts.

FIFO v2 deliberately separates two dimensions:

* custody inventory is maintained per Account and Asset;
* acquisition lots, basis, realized gain and Cost Average are maintained per Asset.

Inside one Asset the lots are consumed per Account (wallet-based FIFO,
Festlegung 12.10.2026): a Sell, Withdrawal or Asset fee consumes the oldest lots
held on its Account, and a Transfer carries the oldest lots of the source Account
- with acquisition date, order and proportional basis - to the destination.
Until 0.2.0-rc.244 one queue per Asset ran across all Accounts.

Wertermittlung je Wallet (rc.294, BMF 06.03.2025 Rn. 61/62): Fuer Kryptowerte kann
der Eigentuemer je Wallet und Coin die Durchschnittsmethode waehlen
(`valuation_methods`). Die Haltefrist folgt weiter FIFO - verbraucht werden die
aeltesten Lots des Kontos -, die Kosten aber zum Durchschnitt der Wallet: Nach
jedem Zugang in eine solche Wallet tragen alle ihre Lots denselben Stueckpreis.
Eine Wahl wirkt erst, wenn die Wallet leer war und wieder befuellt wird
(Rn. 62: beizubehalten bis zur vollstaendigen Veraeusserung); sie ist nicht
jahresbezogen. Ohne Wahl rechnet der Kern wie bisher, Zeichen fuer Zeichen.

FIFO-Wallet aus mehreren Konten (#508, Festlegung 23.10.2026): Ein Unterkonto einer Boerse oder eines Hardware-Wallets
(Staking, Earn, weitere Konten auf dem Geraet) laesst sich einem Hauptkonto desselben Instituts zuordnen (`fifo_wallets`,
nur Kryptowerte, eine Stufe). Haupt- und Unterkonten bilden dann eine Wallet: Ihre Lots liegen beim Hauptkonto, ein Verkauf
verbraucht die aeltesten Lots der ganzen Wallet, und eine Umbuchung innerhalb der Wallet bewegt kein Lot. Die verwahrte
Menge bleibt je Konto. Die Zuordnung gilt fuer die ganze Historie. Ohne Zuordnung rechnet der Kern wie bisher.

The module is pure and provider-free.  It imports no calculated Legacy result, rounds
no value and owns no filesystem, SQLite, publication or canonical-write capability.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from migrations.reference.asset_activity_v1 import (
    AssetActivityV1Error,
    validate_asset_activity_v1,
)

CONTRACT_VERSION = 2
SOURCE_CONTRACT = "asset_activity_v1"
FIFO_WORLD_DIMENSION = "portfolio_asset"
CUSTODY_DIMENSION = "portfolio_account_asset"
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_INVENTORY_EVENTS = frozenset(
    {"buy", "sell", "stock_dividend", "reward", "deposit", "withdrawal", "transfer"}
)
_ORDER_EVIDENCE_MODE = "owner_confirmed_source_row_order"
# Wertermittlung je Wallet (rc.294): FIFO ist die Vorgabe, die Durchschnittsmethode eine Wahl fuer Kryptowerte.
VALUATION_METHODS = ("fifo", "average")
_METHOD_KEYS = {"account_ref", "asset_ref", "method", "valid_from_local_date"}
_INPUT_KEYS = {"realized_fifo_version", "source_contract", "asset_activity"}
_OPTIONAL_INPUT_KEYS = {"fifo_order_evidence", "valuation_methods", "fifo_wallets", "splits"}
# Aktiensplit (#451, rc.370): neben dem Buchungsbestand gespeichert, je Asset und optional je Konto.
_SPLIT_KEYS = {"split_ref", "asset_ref", "account_ref", "effective_local_date", "ratio_numerator", "ratio_denominator"}
_SPLIT_REF = re.compile(r"^spl_[a-f0-9]{32}$")
_RATIO_INTEGER = re.compile(r"^[1-9][0-9]{0,11}$")
_WALLET_KEYS = {"account_ref", "wallet_account_ref"}
_ACCOUNT_REF = re.compile(r"^[A-Za-z0-9_-]{3,128}$")
_ORDER_EVIDENCE_KEYS = {
    "event_ref", "evidence_mode", "source_file_fingerprint", "source_row_ordinal",
    "owner_decision_fingerprint", "evidence_fingerprint",
}
FAILURE_CODES = frozenset(
    {
        "semantic_realized_fifo_v2_account_invalid",
        "semantic_realized_fifo_v2_asset_invalid",
        "semantic_realized_fifo_v2_basis_missing",
        "semantic_realized_fifo_v2_boundary_failed",
        "semantic_realized_fifo_v2_cash_excluded",
        "semantic_realized_fifo_v2_custody_inventory_insufficient",
        "semantic_realized_fifo_v2_decimal_invalid",
        "semantic_realized_fifo_v2_input_invalid",
        "semantic_realized_fifo_v2_inventory_insufficient",
        "semantic_realized_fifo_v2_order_evidence_required",
        "semantic_realized_fifo_v2_source_invalid",
        "semantic_realized_fifo_v2_split_inexact",
    }
)


class SemanticRealizedFifoV2Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("semantic_realized_fifo_v2_error_code_unregistered")
        self.code = code
        super().__init__(code)


def semantic_realized_fifo_v2_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise SemanticRealizedFifoV2Error(code)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        _abort("semantic_realized_fifo_v2_input_invalid")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _fraction(value: Any, *, nullable: bool = False) -> Fraction | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or len(value) > 80
        or value == "-0"
        or _DECIMAL.fullmatch(value) is None
    ):
        _abort("semantic_realized_fifo_v2_decimal_invalid")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError):
        _abort("semantic_realized_fifo_v2_decimal_invalid")


def _decimal_or_none(value: Fraction) -> str | None:
    if value == 0:
        return "0"
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    if denominator != 1:
        return None
    scale = 0
    power = 1
    while power % value.denominator:
        power *= 10
        scale += 1
        if scale > 240:
            return None
    digits = str(abs(value.numerator) * power // value.denominator)
    if scale:
        digits = digits.rjust(scale + 1, "0")
        digits = (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    result = ("-" if value < 0 else "") + digits
    if len(result) > 80 or result == "-0" or _DECIMAL.fullmatch(result) is None:
        return None
    return result


def _exact(value: Fraction) -> dict[str, str | None]:
    decimal = _decimal_or_none(value)
    return {
        "exactness_status": "exact_decimal" if decimal is not None else "exact_ratio",
        "decimal": decimal,
        "numerator_integer": str(value.numerator),
        "denominator_integer": str(value.denominator),
    }


def _basis_missing() -> dict[str, str | None]:
    return {
        "exactness_status": "basis_missing",
        "decimal": None,
        "numerator_integer": None,
        "denominator_integer": None,
    }


def _not_applicable() -> dict[str, str | None]:
    return {
        "exactness_status": "not_applicable",
        "decimal": None,
        "numerator_integer": None,
        "denominator_integer": None,
    }


@dataclass
class _Lot:
    lot_ref: str
    asset_ref: str
    acquisition_event_ref: str
    acquisition_local_date: str
    acquisition_effective_at_utc: str | None
    acquisition_order: tuple[Any, ...]
    quantity: Fraction
    basis: Fraction | None
    # Das Konto, auf dem das Lot liegt. FIFO laeuft je Konto: Ein Verkauf
    # verbraucht die aeltesten Lots des Kontos, von dem verkauft wird, und ein
    # Transfer nimmt die aeltesten Lots des Quellkontos samt Anschaffungsdatum
    # und Anschaffungskosten mit (Festlegung 12.10.2026:
    # walletbezogen als Vorgabe fuer alle Typen). Bis rc.244 gab es je Asset
    # eine Reihe ueber alle Konten; ein Transfer beruehrte kein Lot.
    account_ref: str = ""


@dataclass
class _AssetMetric:
    realized_proceeds: Fraction = Fraction(0)
    realized_basis: Fraction = Fraction(0)
    realized_gain: Fraction = Fraction(0)
    gross_income: Fraction = Fraction(0)
    monetary_fees: Fraction = Fraction(0)


def _lot_quantity(lots: Mapping[str, list[_Lot]], asset_ref: str) -> Fraction:
    return sum((lot.quantity for lot in lots.get(asset_ref, [])), Fraction(0))


def _lot_basis(lots: Mapping[str, list[_Lot]], asset_ref: str) -> Fraction | None:
    entries = lots.get(asset_ref, [])
    if any(lot.basis is None for lot in entries):
        return None
    return sum((lot.basis for lot in entries if lot.basis is not None), Fraction(0))


def _cost_average(lots: Mapping[str, list[_Lot]], asset_ref: str) -> dict[str, str | None]:
    quantity = _lot_quantity(lots, asset_ref)
    if quantity == 0:
        return _not_applicable()
    basis = _lot_basis(lots, asset_ref)
    if basis is None:
        return _basis_missing()
    return _exact(basis / quantity)


def _custody_total(custody: Mapping[tuple[str, str], Fraction], asset_ref: str) -> Fraction:
    return sum(
        (quantity for (_, scoped_asset), quantity in custody.items() if scoped_asset == asset_ref),
        Fraction(0),
    )


def _assert_asset_conservation(
    custody: Mapping[tuple[str, str], Fraction], lots: Mapping[str, list[_Lot]], asset_ref: str,
    wallets: Mapping[str, str] | None = None,
) -> None:
    if _custody_total(custody, asset_ref) != _lot_quantity(lots, asset_ref):
        _abort("semantic_realized_fifo_v2_boundary_failed")
    # Je Wallet dasselbe: Die Lots einer Wallet ergeben die verwahrte Menge ihrer Konten. Ohne Zuordnung ist jedes Konto
    # seine eigene Wallet (#508).
    wallets = wallets or {}
    held: dict[str, Fraction] = {}
    for lot in lots.get(asset_ref, []):
        held[lot.account_ref] = held.get(lot.account_ref, Fraction(0)) + lot.quantity
    kept: dict[str, Fraction] = {}
    for (account, scoped_asset), quantity in custody.items():
        if scoped_asset == asset_ref:
            wallet = wallets.get(account, account)
            kept[wallet] = kept.get(wallet, Fraction(0)) + quantity
    for wallet in set(held) | set(kept):
        if held.get(wallet, Fraction(0)) != kept.get(wallet, Fraction(0)):
            _abort("semantic_realized_fifo_v2_boundary_failed")


def _account_lots(entries: Sequence[_Lot], account_ref: str) -> list[_Lot]:
    """Die FIFO-Reihe eines Kontos: seine Lots, aelteste Anschaffung zuerst."""
    return sorted((lot for lot in entries if lot.account_ref == account_ref),
                  key=lambda item: item.acquisition_order)


def _move_lots(
    lots: dict[str, list[_Lot]], asset_ref: str, source_ref: str, destination_ref: str, quantity: Fraction,
) -> list[dict[str, Any]]:
    """Ein Transfer nimmt die aeltesten Lots des Quellkontos mit.

    Anschaffungsdatum, Reihenfolge und anteilige Anschaffungskosten wandern
    unveraendert; im Zielkonto ordnen sich die Lots nach ihrem Anschaffungsdatum
    ein, nicht nach dem Tag des Transfers. Ein Transfer ist keine Veraeusserung.
    Trifft ein Teil auf einen Teil desselben Lots, werden beide wieder eins.
    """
    if quantity <= 0:
        _abort("semantic_realized_fifo_v2_decimal_invalid")
    entries = lots.get(asset_ref, [])
    queue = _account_lots(entries, source_ref)
    remaining = quantity
    moved: list[dict[str, Any]] = []
    while remaining:
        if not queue:
            _abort("semantic_realized_fifo_v2_inventory_insufficient")
        lot = queue[0]
        take = min(remaining, lot.quantity)
        basis = None if lot.basis is None else lot.basis * take / lot.quantity
        moved.append({
            "lot_ref": lot.lot_ref, "quantity": take, "basis": basis,
            "acquisition_event_ref": lot.acquisition_event_ref,
        })
        target = next((item for item in entries
                       if item.account_ref == destination_ref and item.lot_ref == lot.lot_ref), None)
        if target is None:
            entries.append(_Lot(
                lot_ref=lot.lot_ref, asset_ref=asset_ref, acquisition_event_ref=lot.acquisition_event_ref,
                acquisition_local_date=lot.acquisition_local_date,
                acquisition_effective_at_utc=lot.acquisition_effective_at_utc,
                acquisition_order=lot.acquisition_order, quantity=take, basis=basis, account_ref=destination_ref))
        else:
            target.quantity += take
            target.basis = None if target.basis is None or basis is None else target.basis + basis
        lot.quantity -= take
        if lot.basis is not None:
            lot.basis -= basis
        remaining -= take
        if lot.quantity == 0:
            queue.pop(0)
    lots[asset_ref] = [lot for lot in entries if lot.quantity != 0]
    return moved


def _account_lot_rows(lots: Mapping[str, list[_Lot]]) -> list[dict[str, Any]]:
    """Die Lots, wie sie liegen: je Asset und Konto, aelteste Anschaffung zuerst."""
    rows: list[dict[str, Any]] = []
    for asset_ref, entries in sorted(lots.items()):
        for lot in sorted(entries, key=lambda item: (item.account_ref, item.acquisition_order)):
            rows.append({
                "asset_ref": asset_ref,
                "account_ref": lot.account_ref,
                "lot_ref": lot.lot_ref,
                "acquisition_event_ref": lot.acquisition_event_ref,
                "acquisition_local_date": lot.acquisition_local_date,
                "acquisition_effective_at_utc": lot.acquisition_effective_at_utc,
                "remaining_quantity_decimal": _decimal_or_none(lot.quantity),
                "remaining_fifo_basis": _basis_missing() if lot.basis is None else _exact(lot.basis),
            })
    return rows


def _capture_snapshots(trace: dict[str, Any], lots: Mapping[str, list[_Lot]], next_local_date: str | None) -> None:
    """Haelt den Stand zum Ende jedes angefragten Tages fest, bevor das erste spaetere Ereignis wirkt."""
    while trace["pending_dates"] and (next_local_date is None or trace["pending_dates"][0] < next_local_date):
        trace["account_lots_at"][trace["pending_dates"].pop(0)] = _account_lot_rows(lots)


def _consume(
    lots: dict[str, list[_Lot]], asset_ref: str, quantity: Fraction, account_ref: str,
) -> tuple[list[dict[str, Any]], Fraction | None]:
    """Verbraucht die aeltesten Lots des Kontos - nicht die aeltesten des Assets."""
    if quantity <= 0:
        _abort("semantic_realized_fifo_v2_decimal_invalid")
    entries = lots.get(asset_ref, [])
    current = _account_lots(entries, account_ref)
    remaining = quantity
    consumed: list[dict[str, Any]] = []
    basis_total = Fraction(0)
    basis_complete = True
    while remaining:
        if not current:
            _abort("semantic_realized_fifo_v2_inventory_insufficient")
        lot = current[0]
        take = min(remaining, lot.quantity)
        basis = None if lot.basis is None else lot.basis * take / lot.quantity
        consumed.append(
            {
                "lot_ref": lot.lot_ref,
                "quantity": take,
                "basis": basis,
                "acquisition_event_ref": lot.acquisition_event_ref,
            }
        )
        lot.quantity -= take
        if lot.basis is None:
            basis_complete = False
        else:
            lot.basis -= basis
            basis_total += basis
        remaining -= take
        if lot.quantity == 0:
            current.pop(0)
    lots[asset_ref] = [lot for lot in entries if lot.quantity != 0]
    return consumed, basis_total if basis_complete else None


def _local_date_valid(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 10 and value[4] == "-" and value[7] == "-"
            and (value[:4] + value[5:7] + value[8:]).isdigit())


def _valuation_methods(
    value: Any, accounts: Mapping[str, Any], assets: Mapping[str, Any],
) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Die Wahl je Wallet und Coin: (Konto, Asset) -> [(gueltig ab, Methode)], aelteste zuerst."""
    if value is None:
        return {}
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _abort("semantic_realized_fifo_v2_input_invalid")
    result: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for item in value:
        if (
            not isinstance(item, Mapping) or set(item) != _METHOD_KEYS
            or item["account_ref"] not in accounts or item["asset_ref"] not in assets
            or assets[item["asset_ref"]]["asset_type"] != "crypto"
            or item["method"] not in VALUATION_METHODS or not _local_date_valid(item["valid_from_local_date"])
        ):
            _abort("semantic_realized_fifo_v2_input_invalid")
        entries = result.setdefault((item["account_ref"], item["asset_ref"]), [])
        if any(day == item["valid_from_local_date"] for day, _ in entries):
            _abort("semantic_realized_fifo_v2_input_invalid")
        entries.append((item["valid_from_local_date"], item["method"]))
    for entries in result.values():
        entries.sort()
    return result


def _fifo_wallets(value: Any, accounts: Mapping[str, Any], assets: Mapping[str, Any]) -> dict[str, str]:
    """Die FIFO-Wallet aus mehreren Konten (#508): Unterkonto -> Hauptkonto. Nur Kryptowerte, eine Stufe, keine Kette."""
    if value is None:
        return {}
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        _abort("semantic_realized_fifo_v2_input_invalid")
    if any(item["asset_type"] != "crypto" for item in assets.values()):
        _abort("semantic_realized_fifo_v2_input_invalid")
    result: dict[str, str] = {}
    for item in value:
        if (
            not isinstance(item, Mapping) or set(item) != _WALLET_KEYS
            or not isinstance(item["account_ref"], str) or item["account_ref"] not in accounts
            or not isinstance(item["wallet_account_ref"], str) or _ACCOUNT_REF.fullmatch(item["wallet_account_ref"]) is None
            or item["account_ref"] == item["wallet_account_ref"] or item["account_ref"] in result
        ):
            _abort("semantic_realized_fifo_v2_input_invalid")
        result[item["account_ref"]] = item["wallet_account_ref"]
    if set(result) & set(result.values()):
        _abort("semantic_realized_fifo_v2_input_invalid")
    return result


def _splits(value: Any, accounts: Mapping[str, Any], assets: Mapping[str, Any], wallets: Mapping[str, str]) -> list[dict[str, Any]]:
    """Die Splits der Welt, nach Stichtag und Kennung geordnet (#451).

    Ein Split teilt jedes offene Lot des Assets im Verhaeltnis neu : alt; Einstand und Anschaffungsdatum je Lot bleiben. Er wirkt
    zu Beginn seines Stichtags, vor jeder Buchung dieses Tages: Buchungen ab dem Stichtag stehen in neuen Stuecken, wie die Kurse
    der Anbieter. Ohne Konto gilt er fuer alle Konten; ein Konto einer FIFO-Wallet kann nicht allein geteilt werden, weil seine
    Lots der Wallet gehoeren."""
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        _abort("semantic_realized_fifo_v2_input_invalid")
    members = set(wallets) | set(wallets.values())
    result, seen_refs, seen_days = [], set(), set()
    for item in value:
        if (
            not isinstance(item, Mapping) or set(item) != _SPLIT_KEYS
            or not isinstance(item["split_ref"], str) or _SPLIT_REF.fullmatch(item["split_ref"]) is None or item["split_ref"] in seen_refs
            or item["asset_ref"] not in assets
            or (item["account_ref"] is not None and (item["account_ref"] not in accounts or item["account_ref"] in members))
            or not _local_date_valid(item["effective_local_date"])
            or not isinstance(item["ratio_numerator"], str) or _RATIO_INTEGER.fullmatch(item["ratio_numerator"]) is None
            or not isinstance(item["ratio_denominator"], str) or _RATIO_INTEGER.fullmatch(item["ratio_denominator"]) is None
            or item["ratio_numerator"] == item["ratio_denominator"]
        ):
            _abort("semantic_realized_fifo_v2_input_invalid")
        day_key = (item["asset_ref"], item["account_ref"], item["effective_local_date"])
        if day_key in seen_days:
            _abort("semantic_realized_fifo_v2_input_invalid")
        seen_refs.add(item["split_ref"]); seen_days.add(day_key)
        result.append(dict(item))
    result.sort(key=lambda item: (item["effective_local_date"], item["split_ref"]))
    return result


def _apply_split(split: Mapping[str, Any], lots: dict[str, list[_Lot]], custody: dict[tuple[str, str], Fraction],
                 wallets: Mapping[str, str], after_sequence: int) -> dict[str, Any]:
    """Teilt die Lots und Verwahrmengen eines Splits. Basis, Anschaffungsfolge und Lot-Kennung bleiben."""
    asset_ref, account_ref = split["asset_ref"], split["account_ref"]
    ratio = Fraction(int(split["ratio_numerator"]), int(split["ratio_denominator"]))
    quantity_before = _lot_quantity(lots, asset_ref)
    for lot in lots.get(asset_ref, []):
        if account_ref is None or lot.account_ref == account_ref:
            lot.quantity *= ratio
            if _decimal_or_none(lot.quantity) is None:
                _abort("semantic_realized_fifo_v2_split_inexact")
    rows = []
    for key in sorted(key for key in custody if key[1] == asset_ref and (account_ref is None or key[0] == account_ref)):
        before = custody[key]
        custody[key] = before * ratio
        if _decimal_or_none(custody[key]) is None:
            _abort("semantic_realized_fifo_v2_split_inexact")
        rows.append({"account_ref": key[0], "custody_quantity_before_decimal": _decimal_or_none(before),
                     "custody_quantity_after_decimal": _decimal_or_none(custody[key])})
    _assert_asset_conservation(custody, lots, asset_ref, wallets)
    return {"split_ref": split["split_ref"], "asset_ref": asset_ref, "account_ref": account_ref,
            "effective_local_date": split["effective_local_date"], "ratio_numerator": split["ratio_numerator"],
            "ratio_denominator": split["ratio_denominator"], "after_event_sequence": str(after_sequence),
            "asset_quantity_before_decimal": _decimal_or_none(quantity_before),
            "asset_quantity_after_decimal": _decimal_or_none(_lot_quantity(lots, asset_ref)), "custody": rows}


def _chosen_method(entries: Sequence[tuple[str, str]], local_date: str) -> str:
    """Die Methode einer neu befuellten Wallet: die zuletzt gueltig gewordene Wahl, sonst FIFO."""
    method = "fifo"
    for day, chosen in entries:
        if day <= local_date:
            method = chosen
    return method


def _reaverage(lots: Mapping[str, list[_Lot]], asset_ref: str, account_ref: str) -> list[tuple[_Lot, Fraction | None]]:
    """Alle Lots einer Wallet zum Durchschnitt ihrer Kosten - Mengen und Anschaffungsdaten bleiben.

    Die Summe bleibt exakt erhalten. Fehlen einem Lot die Kosten, ist auch der
    Durchschnitt unbekannt: Dann fehlen sie allen Lots der Wallet. Liefert je
    geaendertem Lot die Aenderung seiner Kosten (None = jetzt unbekannt)."""
    entries = [lot for lot in lots.get(asset_ref, []) if lot.account_ref == account_ref]
    quantity = sum((lot.quantity for lot in entries), Fraction(0))
    if quantity == 0:
        return []
    known = all(lot.basis is not None for lot in entries)
    average = sum((lot.basis for lot in entries if lot.basis is not None), Fraction(0)) / quantity if known else None
    changes: list[tuple[_Lot, Fraction | None]] = []
    for lot in sorted(entries, key=lambda item: item.acquisition_order):
        target = None if average is None else lot.quantity * average
        if target != lot.basis:
            changes.append((lot, None if target is None or lot.basis is None else target - lot.basis))
            lot.basis = target
    return changes


def _decision_fingerprint(
    events: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
) -> str:
    ordered = sorted(
        events,
        key=lambda event: (evidence[event["event_ref"]]["source_row_ordinal"], event["event_ref"]),
    )
    first = ordered[0]
    return _fingerprint({
        "fifo_order_decision_version": 1,
        "evidence_mode": _ORDER_EVIDENCE_MODE,
        "source_file_fingerprint": evidence[first["event_ref"]]["source_file_fingerprint"],
        "asset_ref": first["asset_ref"],
        "local_date": first["local_date"],
        "effective_at_utc": first["effective_at_utc"],
        "ordered_source_rows": [
            {
                "event_ref": event["event_ref"],
                "source_row_ordinal": evidence[event["event_ref"]]["source_row_ordinal"],
            }
            for event in ordered
        ],
    })


def _order_evidence(value: Any, events: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if not isinstance(value, list):
        _abort("semantic_realized_fifo_v2_source_invalid")
    event_by_ref = {event["event_ref"]: event for event in events}
    event_refs = set(event_by_ref)
    result: dict[str, dict[str, Any]] = {}
    source_rows: set[tuple[str, int]] = set()
    for item in value:
        if not isinstance(item, Mapping) or set(item) != _ORDER_EVIDENCE_KEYS:
            _abort("semantic_realized_fifo_v2_source_invalid")
        row = dict(item)
        body = {key: row[key] for key in _ORDER_EVIDENCE_KEYS if key != "evidence_fingerprint"}
        event_ref = row.get("event_ref")
        source_fingerprint = row.get("source_file_fingerprint")
        ordinal = row.get("source_row_ordinal")
        if (
            event_ref not in event_refs
            or event_ref in result
            or row.get("evidence_mode") != _ORDER_EVIDENCE_MODE
            or event_by_ref[event_ref].get("event_type") not in _INVENTORY_EVENTS
            or event_by_ref[event_ref].get("event_time_evidence") != "exact"
            or event_by_ref[event_ref].get("effective_at_utc") is None
            or not isinstance(source_fingerprint, str)
            or _SHA.fullmatch(source_fingerprint) is None
            or isinstance(ordinal, bool)
            or not isinstance(ordinal, int)
            or ordinal < 1
            or not isinstance(row.get("owner_decision_fingerprint"), str)
            or _SHA.fullmatch(row["owner_decision_fingerprint"]) is None
            or row.get("evidence_fingerprint") != _fingerprint(body)
            or (source_fingerprint, ordinal) in source_rows
        ):
            _abort("semantic_realized_fifo_v2_source_invalid")
        source_rows.add((source_fingerprint, ordinal))
        result[event_ref] = row
    return result


def build_owner_confirmed_source_row_order_evidence_v1(
    events: Sequence[Mapping[str, Any]],
    source_rows: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build explicit evidence only for equal exact-time inventory groups."""
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)) or not isinstance(source_rows, Mapping):
        _abort("semantic_realized_fifo_v2_source_invalid")
    refs = [event.get("event_ref") for event in events if isinstance(event, Mapping)]
    if len(refs) != len(events) or len(set(refs)) != len(refs) or set(source_rows) != set(refs):
        _abort("semantic_realized_fifo_v2_source_invalid")
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for event in events:
        if event.get("event_type") not in _INVENTORY_EVENTS or event.get("event_time_evidence") != "exact":
            continue
        key = (event.get("asset_ref"), event.get("local_date"), event.get("effective_at_utc"))
        if not all(isinstance(item, str) and item for item in key):
            _abort("semantic_realized_fifo_v2_source_invalid")
        groups.setdefault(key, []).append(event)
    result: list[dict[str, Any]] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        partial: dict[str, dict[str, Any]] = {}
        for event in group:
            source = source_rows.get(event["event_ref"])
            if not isinstance(source, Mapping) or set(source) != {"source_file_fingerprint", "source_row_ordinal"}:
                _abort("semantic_realized_fifo_v2_source_invalid")
            fingerprint = source.get("source_file_fingerprint")
            ordinal = source.get("source_row_ordinal")
            if (
                not isinstance(fingerprint, str)
                or _SHA.fullmatch(fingerprint) is None
                or isinstance(ordinal, bool)
                or not isinstance(ordinal, int)
                or ordinal < 1
            ):
                _abort("semantic_realized_fifo_v2_source_invalid")
            partial[event["event_ref"]] = {
                "event_ref": event["event_ref"],
                "evidence_mode": _ORDER_EVIDENCE_MODE,
                "source_file_fingerprint": fingerprint,
                "source_row_ordinal": ordinal,
            }
        if len({row["source_file_fingerprint"] for row in partial.values()}) != 1 or len({row["source_row_ordinal"] for row in partial.values()}) != len(group):
            _abort("semantic_realized_fifo_v2_order_evidence_required")
        decision = _decision_fingerprint(group, partial)
        for event in group:
            row = {**partial[event["event_ref"]], "owner_decision_fingerprint": decision}
            row["evidence_fingerprint"] = _fingerprint(row)
            result.append(row)
    result.sort(key=lambda row: row["event_ref"])
    return result


def _validate_order(
    events: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Mapping[str, Any]],
) -> None:
    relevant = [event for event in events if event["event_type"] in _INVENTORY_EVENTS]
    by_day: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for event in relevant:
        by_day.setdefault((event["asset_ref"], event["local_date"]), []).append(event)
    for day_events in by_day.values():
        if len(day_events) < 2:
            continue
        if any(event["event_time_evidence"] == "date_only" for event in day_events):
            _abort("semantic_realized_fifo_v2_order_evidence_required")
        collisions: dict[str, list[Mapping[str, Any]]] = {}
        for event in day_events:
            collisions.setdefault(event["effective_at_utc"], []).append(event)
        for group in collisions.values():
            if len(group) < 2:
                continue
            rows = [evidence.get(event["event_ref"]) for event in group]
            if (
                any(row is None for row in rows)
                or len({row["source_file_fingerprint"] for row in rows}) != 1
                or len({row["source_row_ordinal"] for row in rows}) != len(group)
                or len({row["owner_decision_fingerprint"] for row in rows}) != 1
                or rows[0]["owner_decision_fingerprint"] != _decision_fingerprint(group, evidence)
            ):
                _abort("semantic_realized_fifo_v2_order_evidence_required")


def _event_order(
    event: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]],
) -> tuple[Any, ...]:
    row = evidence.get(event["event_ref"])
    return (
        event["local_date"],
        event["effective_at_utc"] is not None,
        event["effective_at_utc"] or "",
        0 if row is not None else 1,
        0 if row is None else row["source_row_ordinal"],
        event["event_ref"],
    )


def _acquisition_order(
    event: Mapping[str, Any], evidence: Mapping[str, Mapping[str, Any]],
) -> tuple[Any, ...]:
    if event["event_type"] == "deposit":
        local_date = event["original_acquired_local_date"]
        effective = event["original_acquired_at_utc"]
        row = None
    else:
        local_date = event["local_date"]
        effective = event["effective_at_utc"]
        row = evidence.get(event["event_ref"])
    if local_date is None:
        _abort("semantic_realized_fifo_v2_source_invalid")
    return (
        local_date, effective is not None, effective or "",
        0 if row is not None else 1, 0 if row is None else row["source_row_ordinal"],
        event["event_ref"],
    )


def _add_lot(
    lots: dict[str, list[_Lot]], event: Mapping[str, Any], quantity: Fraction,
    basis: Fraction | None, evidence: Mapping[str, Mapping[str, Any]], account_ref: str | None = None,
) -> _Lot:
    asset_ref = event["asset_ref"]
    order = _acquisition_order(event, evidence)
    for existing in lots.get(asset_ref, []):
        if existing.acquisition_local_date != order[0]:
            continue
        if (
            existing.acquisition_effective_at_utc is None
            or event["original_acquired_at_utc"] is None and event["event_type"] == "deposit"
            or event["effective_at_utc"] is None and event["event_type"] != "deposit"
            or existing.acquisition_effective_at_utc == order[2] and (existing.acquisition_order[3] != 0 or order[3] != 0)
        ):
            _abort("semantic_realized_fifo_v2_order_evidence_required")
    lot_ref = "lot_" + hashlib.sha256(
        f"semantic-realized-fifo-v2|{event['event_ref']}".encode("utf-8")
    ).hexdigest()[:32]
    lot = _Lot(
        lot_ref=lot_ref,
        asset_ref=asset_ref,
        acquisition_event_ref=event["event_ref"],
        acquisition_local_date=order[0],
        acquisition_effective_at_utc=order[2] or None,
        acquisition_order=order,
        quantity=quantity,
        basis=basis,
        account_ref=event["account_ref"] if account_ref is None else account_ref,
    )
    lots.setdefault(asset_ref, []).append(lot)
    return lot


def _custody_available(
    custody: Mapping[tuple[str, str], Fraction], account_ref: str, asset_ref: str, quantity: Fraction
) -> None:
    if custody.get((account_ref, asset_ref), Fraction(0)) < quantity:
        _abort("semantic_realized_fifo_v2_custody_inventory_insufficient")


def _consume_rows(consumed: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "lot_ref": item["lot_ref"],
            "quantity_decimal": _decimal_or_none(item["quantity"]),
            "fifo_basis": _basis_missing() if item["basis"] is None else _exact(item["basis"]),
            "acquisition_event_ref": item["acquisition_event_ref"],
        }
        for item in consumed
    ]


def project_semantic_realized_fifo_v2(value: Mapping[str, Any]) -> dict[str, Any]:
    """Project one complete exact Asset FIFO result from source facts only."""
    return _project(value, None)


def project_semantic_realized_fifo_lot_trace_v2(
    value: Mapping[str, Any], snapshot_dates: Sequence[str] = (),
) -> dict[str, Any]:
    """Dieselbe Rechnung, zusaetzlich mit der Spur der Lots.

    Das Ergebnis der Rechnung bleibt, wie es ist; die Spur steht daneben: welche
    Lots ein Transfer von welchem Konto auf welches trug, welche Lots am Ende auf
    welchem Konto liegen und - je angefragtem Tag - wie sie am Ende dieses Tages
    lagen. Sie belegt die walletbezogene Verbrauchsfolge ueber Transfers hinweg.
    Dazu je Wallet und Coin die Abschnitte von einer Befuellung bis zur
    vollstaendigen Veraeusserung mit ihrer Methode und - bei der
    Durchschnittsmethode - jede Angleichung der Kosten eines Lots.
    """
    if isinstance(snapshot_dates, (str, bytes)) or not isinstance(snapshot_dates, Sequence):
        _abort("semantic_realized_fifo_v2_input_invalid")
    dates = sorted(set(snapshot_dates))
    for day in dates:
        if not isinstance(day, str) or len(day) != 10 or day[4] != "-" or day[7] != "-" or not (day[:4] + day[5:7] + day[8:]).isdigit():
            _abort("semantic_realized_fifo_v2_input_invalid")
    trace: dict[str, Any] = {"pending_dates": list(dates), "transfer_lot_movements": [], "account_lots_at": {}, "account_lots": [],
                             "wallet_segments": [], "basis_adjustments": [], "split_steps": []}
    result = _project(value, trace)
    traced = {
        "lot_trace_version": 1,
        "result": result,
        "transfer_lot_movements": trace["transfer_lot_movements"],
        "account_lots": trace["account_lots"],
        "account_lots_at": trace["account_lots_at"],
        "wallet_segments": trace["wallet_segments"],
        "basis_adjustments": trace["basis_adjustments"],
    }
    # Splits (#451) nur, wenn es welche gibt - ohne Split bleibt die Spur, wie sie war.
    if trace["split_steps"]:
        traced["split_steps"] = trace["split_steps"]
    return traced


def _project(value: Mapping[str, Any], trace: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not _INPUT_KEYS <= set(value) or not set(value) - _INPUT_KEYS <= _OPTIONAL_INPUT_KEYS:
        _abort("semantic_realized_fifo_v2_input_invalid")
    if value["realized_fifo_version"] != CONTRACT_VERSION or value["source_contract"] != SOURCE_CONTRACT:
        _abort("semantic_realized_fifo_v2_input_invalid")
    source = value["asset_activity"]
    try:
        preview = validate_asset_activity_v1(source)
    except AssetActivityV1Error:
        _abort("semantic_realized_fifo_v2_source_invalid")
    if preview["cash_posting_count"] != 0:
        _abort("semantic_realized_fifo_v2_cash_excluded")
    if not isinstance(source, Mapping):
        _abort("semantic_realized_fifo_v2_source_invalid")

    accounts = {item["account_ref"]: item for item in source["accounts"]}
    assets = {item["asset_ref"]: item for item in source["assets"]}
    if len(accounts) != len(source["accounts"]):
        _abort("semantic_realized_fifo_v2_account_invalid")
    if len(assets) != len(source["assets"]):
        _abort("semantic_realized_fifo_v2_asset_invalid")
    if any(item["asset_type"] == "cash" for item in assets.values()):
        _abort("semantic_realized_fifo_v2_cash_excluded")

    events = list(source["events"])
    effects = {item["event_ref"]: item for item in preview["event_effects"]}
    if len(effects) != len(events) or set(effects) != {item["event_ref"] for item in events}:
        _abort("semantic_realized_fifo_v2_source_invalid")
    order_evidence = _order_evidence(value.get("fifo_order_evidence"), events)
    methods = _valuation_methods(value.get("valuation_methods"), accounts, assets)
    # FIFO-Wallet aus mehreren Konten (#508): Lots und Wahl der Wertermittlung gehoeren der Wallet, also dem Hauptkonto.
    wallets = _fifo_wallets(value.get("fifo_wallets"), accounts, assets)
    if wallets:
        merged: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for (method_account, method_asset), entries in methods.items():
            target = merged.setdefault((wallets.get(method_account, method_account), method_asset), [])
            for day, chosen in entries:
                if any(existing == day for existing, _ in target):
                    _abort("semantic_realized_fifo_v2_input_invalid")
                target.append((day, chosen))
        methods = {key: sorted(entries) for key, entries in merged.items()}

    def wallet_of(account: str) -> str:
        return wallets.get(account, account)
    splits = _splits(value.get("splits"), accounts, assets, wallets)
    split_results: list[dict[str, Any]] = []

    def apply_splits_until(local_date: str | None, after_sequence: int) -> None:
        # Splits wirken zu Beginn ihres Stichtags: vor jeder Buchung dieses Tages, nach dem Tagesende des Vortags.
        while splits and (local_date is None or splits[0]["effective_local_date"] <= local_date):
            split = splits.pop(0)
            if trace is not None:
                _capture_snapshots(trace, lots, split["effective_local_date"])
            row = _apply_split(split, lots, custody, wallets, after_sequence)
            split_results.append(row)
            if trace is not None:
                trace["split_steps"].append(row)
    # Die Methode je Wallet und Coin - gewaehlt, wenn die Wallet leer war und wieder befuellt wird.
    wallet_method: dict[tuple[str, str], str] = {}
    _validate_order(events, order_evidence)
    events.sort(key=lambda event: _event_order(event, order_evidence))

    custody: dict[tuple[str, str], Fraction] = {}
    lots: dict[str, list[_Lot]] = {}
    metrics: dict[str, _AssetMetric] = {asset_ref: _AssetMetric() for asset_ref in assets}
    event_results: list[dict[str, Any]] = []

    for sequence, event in enumerate(events, 1):
        event_type = event["event_type"]
        account_ref = event["account_ref"]
        related_ref = event["related_account_ref"]
        asset_ref = event["asset_ref"]
        apply_splits_until(event["local_date"], sequence - 1)
        if trace is not None:
            _capture_snapshots(trace, lots, event["local_date"])
        if account_ref not in accounts or related_ref is not None and related_ref not in accounts:
            _abort("semantic_realized_fifo_v2_account_invalid")
        if asset_ref not in assets:
            _abort("semantic_realized_fifo_v2_asset_invalid")
        effect = effects[event["event_ref"]]
        quantity = _fraction(event["quantity_decimal"], nullable=True)
        asset_fee = _fraction(event["asset_fee_quantity_decimal"], nullable=True) or Fraction(0)
        monetary_fee = _fraction(event["monetary_fee_decimal"], nullable=True) or Fraction(0)
        metric = metrics[asset_ref]
        metric.monetary_fees += monetary_fee
        source_key = (account_ref, asset_ref)
        destination_key = None if related_ref is None else (related_ref, asset_ref)
        source_before = custody.get(source_key, Fraction(0))
        destination_before = None if destination_key is None else custody.get(destination_key, Fraction(0))
        asset_quantity_before = _lot_quantity(lots, asset_ref)
        asset_basis_before = _lot_basis(lots, asset_ref)
        basis_added: Fraction | None = Fraction(0)
        basis_consumed: Fraction | None = Fraction(0)
        realized_gain = Fraction(0)
        consumed_rows: list[dict[str, Any]] = []
        source_wallet = wallet_of(account_ref)
        destination_wallet = None if related_ref is None else wallet_of(related_ref)

        def held(wallet: str) -> Fraction:
            # Verwahrte Menge einer Wallet: die Summe ihrer Konten; ohne Zuordnung die des Kontos.
            if not wallets:
                return custody.get((wallet, asset_ref), Fraction(0))
            return sum((amount for (scoped_account, scoped_asset), amount in custody.items()
                        if scoped_asset == asset_ref and wallet_of(scoped_account) == wallet), Fraction(0))

        def begin(wallet: tuple[str, str], before: Fraction) -> None:
            # Eine leere Wallet wird befuellt: Hier beginnt ein Abschnitt, und hier gilt eine neue Wahl.
            if before == 0:
                wallet_method[wallet] = _chosen_method(methods.get(wallet, ()), event["local_date"])
                if trace is not None:
                    trace["wallet_segments"].append({
                        "asset_ref": asset_ref, "account_ref": wallet[0], "start_local_date": event["local_date"],
                        "start_event_ref": event["event_ref"], "method": wallet_method[wallet],
                    })

        def settle(wallet: tuple[str, str]) -> None:
            # Nach einem Zugang in eine Wallet mit Durchschnittsmethode tragen alle Lots denselben Stueckpreis.
            if wallet_method.get(wallet) != "average":
                return
            for lot, delta in _reaverage(lots, asset_ref, wallet[0]):
                if trace is not None:
                    trace["basis_adjustments"].append({
                        "event_sequence": str(sequence), "event_ref": event["event_ref"], "asset_ref": asset_ref,
                        "account_ref": wallet[0], "lot_ref": lot.lot_ref,
                        "basis_delta": _basis_missing() if delta is None else _exact(delta),
                    })

        if event_type in {"buy", "stock_dividend", "reward", "deposit"}:
            if quantity is None or quantity <= 0:
                _abort("semantic_realized_fifo_v2_decimal_invalid")
            raw_basis = effect["fifo_basis_created_decimal"]
            lot_basis = _fraction(raw_basis, nullable=True)
            if lot_basis is None:
                if event["basis_evidence_mode"] != "basis_missing":
                    _abort("semantic_realized_fifo_v2_source_invalid")
                basis_added = None
            # Eine beim Zugang in Stueck einbehaltene Gebuehr mindert das neue Lot: Zugegangen ist die Menge nach
            # Gebuehr, mit dem gebuchten Wert als Anschaffungskosten. Aeltere Lots des Kontos bleiben unberuehrt
            # (Festlegung 12.10.2026). Bis rc.248 entstand das Lot in voller Menge, und die Gebuehr
            # verbrauchte danach die aeltesten Lots des Kontos.
            net_quantity = quantity - asset_fee
            if net_quantity <= 0:
                _abort("semantic_realized_fifo_v2_decimal_invalid")
            begin((source_wallet, asset_ref), held(source_wallet))
            custody[source_key] = source_before + net_quantity
            _add_lot(lots, event, net_quantity, lot_basis, order_evidence, source_wallet)
            settle((source_wallet, asset_ref))
            if lot_basis is not None:
                basis_added = lot_basis
            if event_type == "reward":
                metric.gross_income += _fraction(effect["gross_income_decimal"])

        elif event_type in {"sell", "withdrawal"}:
            if quantity is None or quantity <= 0:
                _abort("semantic_realized_fifo_v2_decimal_invalid")
            required = quantity + (asset_fee if event_type == "withdrawal" else Fraction(0))
            _custody_available(custody, account_ref, asset_ref, required)
            custody[source_key] = source_before - required
            consumed, basis_consumed = _consume(lots, asset_ref, quantity, source_wallet)
            consumed_rows.extend(_consume_rows(consumed))
            if event_type == "sell":
                if basis_consumed is None:
                    _abort("semantic_realized_fifo_v2_basis_missing")
                proceeds = _fraction(effect["net_trade_proceeds_decimal"])
                realized_gain = proceeds - basis_consumed
                metric.realized_proceeds += proceeds
                metric.realized_basis += basis_consumed
                metric.realized_gain += realized_gain
            if asset_fee:
                fee_consumed, fee_basis = _consume(lots, asset_ref, asset_fee, source_wallet)
                consumed_rows.extend(_consume_rows(fee_consumed))
                basis_consumed = (
                    None
                    if basis_consumed is None or fee_basis is None
                    else basis_consumed + fee_basis
                )

        elif event_type == "transfer":
            if quantity is None or quantity <= 0 or related_ref is None or related_ref == account_ref:
                _abort("semantic_realized_fifo_v2_source_invalid")
            required = quantity + asset_fee
            _custody_available(custody, account_ref, asset_ref, required)
            within = source_wallet == destination_wallet
            if not within:
                begin((destination_wallet, asset_ref), held(destination_wallet))
            custody[source_key] = source_before - required
            custody[destination_key] = destination_before + quantity
            # Der Transfer nimmt die aeltesten Lots des Quellkontos mit; verbraucht
            # wird dabei nichts. Eine in Stueck gezahlte Gebuehr verbraucht danach
            # die naechsten Lots des Quellkontos. Innerhalb einer Wallet (#508) bleibt
            # jedes Lot, wo es ist: Es gehoert der Wallet, nicht dem Konto.
            if not within:
                moved = _move_lots(lots, asset_ref, source_wallet, destination_wallet, quantity)
                settle((destination_wallet, asset_ref))
                if trace is not None:
                    trace["transfer_lot_movements"].append({
                        "event_sequence": str(sequence),
                        "event_ref": event["event_ref"],
                        "asset_ref": asset_ref,
                        "source_account_ref": source_wallet,
                        "destination_account_ref": destination_wallet,
                        "moved_lots": _consume_rows(moved),
                    })
            if asset_fee:
                consumed, basis_consumed = _consume(lots, asset_ref, asset_fee, source_wallet)
                consumed_rows.extend(_consume_rows(consumed))

        elif event_type == "dividend":
            metric.gross_income += _fraction(effect["gross_income_decimal"])
            basis_consumed = Fraction(0)
        else:
            _abort("semantic_realized_fifo_v2_source_invalid")

        _assert_asset_conservation(custody, lots, asset_ref, wallets)
        source_after = custody.get(source_key, Fraction(0))
        destination_after = None if destination_key is None else custody.get(destination_key, Fraction(0))
        asset_quantity_after = _lot_quantity(lots, asset_ref)
        asset_basis_after = _lot_basis(lots, asset_ref)
        event_results.append(
            {
                "event_sequence": str(sequence),
                "event_ref": event["event_ref"],
                "event_type": event_type,
                "account_ref": account_ref,
                "related_account_ref": related_ref,
                "asset_ref": asset_ref,
                "custody_quantity_before_decimal": _decimal_or_none(source_before),
                "custody_quantity_after_decimal": _decimal_or_none(source_after),
                "destination_custody_quantity_before_decimal": None if destination_before is None else _decimal_or_none(destination_before),
                "destination_custody_quantity_after_decimal": None if destination_after is None else _decimal_or_none(destination_after),
                "asset_quantity_before_decimal": _decimal_or_none(asset_quantity_before),
                "asset_quantity_after_decimal": _decimal_or_none(asset_quantity_after),
                "asset_fifo_basis_before": _basis_missing() if asset_basis_before is None else _exact(asset_basis_before),
                "asset_fifo_basis_after": _basis_missing() if asset_basis_after is None else _exact(asset_basis_after),
                "basis_added": _basis_missing() if basis_added is None else _exact(basis_added),
                "basis_consumed": _basis_missing() if basis_consumed is None else _exact(basis_consumed),
                "realized_gain": _exact(realized_gain),
                "consumed_lots": consumed_rows,
            }
        )

    apply_splits_until(None, len(events))
    if trace is not None:
        _capture_snapshots(trace, lots, None)
        trace["account_lots"] = _account_lot_rows(lots)
    custody_positions = [
        {
            "account_ref": account_ref,
            "asset_ref": asset_ref,
            "remaining_quantity_decimal": _decimal_or_none(quantity),
        }
        for (account_ref, asset_ref), quantity in sorted(custody.items())
    ]
    # Ein Lot ist eine Anschaffung. Liegt es nach Transfers auf mehreren Konten,
    # bleibt es in dieser Aufstellung ein Lot mit seiner ganzen Restmenge; auf
    # welchem Konto wie viel liegt, sagen die Verwahrpositionen.
    remaining_lots = []
    for asset_ref, entries in sorted(lots.items()):
        whole: dict[str, list[Any]] = {}
        for lot in sorted(entries, key=lambda item: item.acquisition_order):
            if lot.lot_ref not in whole:
                whole[lot.lot_ref] = [lot, lot.quantity, lot.basis]
            else:
                row = whole[lot.lot_ref]
                row[1] += lot.quantity
                row[2] = None if row[2] is None or lot.basis is None else row[2] + lot.basis
        for lot, quantity, basis in whole.values():
            remaining_lots.append({
                "lot_ref": lot.lot_ref,
                "asset_ref": asset_ref,
                "acquisition_event_ref": lot.acquisition_event_ref,
                "acquisition_local_date": lot.acquisition_local_date,
                "acquisition_effective_at_utc": lot.acquisition_effective_at_utc,
                "remaining_quantity_decimal": _decimal_or_none(quantity),
                "remaining_fifo_basis": _basis_missing() if basis is None else _exact(basis),
            })
    asset_positions = []
    for asset_ref, asset in sorted(assets.items()):
        quantity = _lot_quantity(lots, asset_ref)
        basis = _lot_basis(lots, asset_ref)
        metric = metrics[asset_ref]
        asset_positions.append(
            {
                "asset_ref": asset_ref,
                "asset_type": asset["asset_type"],
                "remaining_quantity_decimal": _decimal_or_none(quantity),
                "remaining_fifo_basis": _basis_missing() if basis is None else _exact(basis),
                "cost_average": _cost_average(lots, asset_ref),
                "realized_gross_proceeds": _exact(metric.realized_proceeds),
                "realized_fifo_basis": _exact(metric.realized_basis),
                "realized_gain": _exact(metric.realized_gain),
                "gross_income": _exact(metric.gross_income),
                "monetary_fees": _exact(metric.monetary_fees),
            }
        )

    body = {
        "realized_fifo_version": CONTRACT_VERSION,
        "status": "completed",
        "source_contract": SOURCE_CONTRACT,
        "source_input_fingerprint": _fingerprint(value),
        "source_event_count": len(events),
        "fifo_world_dimension": FIFO_WORLD_DIMENSION,
        "custody_dimension": CUSTODY_DIMENSION,
        "calculation_results_imported": False,
        "rounding_performed": False,
        "cash_imported": False,
        "provider_access": False,
        "network_access": False,
        "private_data_access": False,
        "canonical_write": False,
        "event_results": event_results,
        "custody_positions": custody_positions,
        "asset_positions": asset_positions,
        "remaining_lots": remaining_lots,
    }
    # Splits (#451): eigene Zeilen statt Zeilen in event_results - deren Leser erwarten je Buchung genau eine Zeile.
    if split_results:
        body["split_results"] = split_results
    body["result_fingerprint"] = _fingerprint(body)
    return body


__all__ = [
    "SemanticRealizedFifoV2Error",
    "VALUATION_METHODS",
    "build_owner_confirmed_source_row_order_evidence_v1",
    "project_semantic_realized_fifo_lot_trace_v2",
    "project_semantic_realized_fifo_v2",
    "semantic_realized_fifo_v2_error_codes",
]
