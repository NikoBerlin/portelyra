"""Exact FIFO read model for discriminated schema-401 ledger events."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote

ALGORITHM_VERSION = "realized_fifo_v1.1.0"
OLD = "portfolio_ledger_v1_transaction_fact"
ACTIVITY = "asset_activity_v1"
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
FAILURE_CODES = frozenset({
    "semantic_realized_fifo_basis_missing",
    "semantic_realized_fifo_boundary_failed",
    "semantic_realized_fifo_cash_event_invalid",
    "semantic_realized_fifo_context_invalid",
    "semantic_realized_fifo_currency_mismatch",
    "semantic_realized_fifo_decimal_invalid",
    "semantic_realized_fifo_event_unsupported",
    "semantic_realized_fifo_input_invalid",
    "semantic_realized_fifo_inventory_insufficient",
    "semantic_realized_fifo_ledger_invalid",
    "semantic_realized_fifo_order_evidence_required",
    "semantic_realized_fifo_portfolio_missing",
    "semantic_realized_fifo_publication_failed",
    "semantic_realized_fifo_publication_invalid",
    "semantic_realized_fifo_rounding_policy_required",
    "semantic_realized_fifo_source_invalid",
})

TABLE_COLUMNS = {
    "event-results.csv": (
        "event_sequence", "event_ref", "effective_at_utc", "local_date", "event_time_evidence",
        "event_type", "account_ref", "related_account_ref", "asset_ref", "asset_type", "currency",
        "quantity_decimal", "amount_decimal", "fee_decimal", "asset_fee_quantity_decimal",
        "basis_added_decimal", "basis_consumed_decimal", "gross_proceeds_decimal",
        "realized_gross_gain_decimal", "gross_income_decimal", "distribution_value_decimal",
        "cash_balance_delta_decimal", "holding_effect", "projection_status", "semantic_contract",
        "coupled_transaction_fact", "automatic_cash_posting_created",
    ),
    "lot-movements.csv": (
        "movement_sequence", "event_ref", "movement_type", "origin_lot_ref", "lot_segment_ref",
        "source_account_ref", "destination_account_ref", "asset_ref", "currency", "quantity_decimal",
        "fifo_cost_decimal", "acquisition_event_ref", "acquisition_effective_at_utc",
        "acquisition_local_date", "semantic_contract",
    ),
    "remaining-lots.csv": (
        "position_ref", "account_ref", "asset_ref", "asset_type", "currency", "origin_lot_ref",
        "lot_segment_ref", "acquisition_event_ref", "acquisition_effective_at_utc",
        "acquisition_local_date", "remaining_quantity_decimal", "remaining_fifo_cost_decimal",
        "acquisition_semantic_contract",
    ),
    "position-history.csv": (
        "history_sequence", "event_ref", "effective_at_utc", "local_date", "event_time_evidence",
        "account_ref", "asset_ref", "currency", "position_quantity_decimal", "fifo_cost_balance_decimal",
        "cumulative_realized_gross_gain_decimal", "cumulative_gross_income_decimal",
        "cash_balance_decimal", "semantic_contract",
    ),
    "position-summary.csv": (
        "position_ref", "account_ref", "asset_ref", "asset_type", "currency",
        "remaining_quantity_decimal", "remaining_fifo_cost_decimal", "realized_gross_proceeds_decimal",
        "realized_fifo_cost_decimal", "realized_gross_gain_decimal", "gross_income_decimal",
        "fee_total_decimal", "cash_balance_decimal", "semantic_contract_coverage",
    ),
    "currency-summary.csv": (
        "currency", "realized_gross_proceeds_decimal", "realized_fifo_cost_decimal",
        "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal",
        "cash_balance_decimal", "cross_currency_aggregation", "semantic_contract_coverage",
    ),
}
TABLE_ROLES = {
    "event-results.csv": "normative_event_results",
    "lot-movements.csv": "normative_fifo_lot_movements",
    "remaining-lots.csv": "normative_remaining_fifo_lots",
    "position-history.csv": "normative_position_history",
    "position-summary.csv": "normative_position_summary",
    "currency-summary.csv": "normative_currency_summary",
}


class SemanticRealizedFifoV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("semantic_realized_fifo_error_code_unregistered")
        self.code = code
        super().__init__(code)


def semantic_realized_fifo_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def abort(code: str) -> None:
    raise SemanticRealizedFifoV1Error(code)


def canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    except Exception:
        abort("semantic_realized_fifo_input_invalid")


def sha(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def public_ref(prefix: str, context_fp: str, value: str) -> str:
    material = "|".join(("realized-fifo-public-ref-v1", context_fp, prefix, value))
    return prefix + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def fraction(value: Any, *, positive: bool = False, nullable: bool = False) -> Fraction | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > 80 or value == "-0" or DECIMAL.fullmatch(value) is None:
        abort("semantic_realized_fifo_decimal_invalid")
    result = Fraction(value)
    if positive and result <= 0:
        abort("semantic_realized_fifo_decimal_invalid")
    return result


def decimal_text(value: Fraction) -> str:
    if value == 0:
        return "0"
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    if denominator != 1:
        abort("semantic_realized_fifo_rounding_policy_required")
    scale = 0
    power = 1
    while power % value.denominator:
        power *= 10
        scale += 1
        if scale > 240:
            abort("semantic_realized_fifo_rounding_policy_required")
    digits = str(abs(value.numerator) * power // value.denominator)
    if scale:
        digits = digits.rjust(scale + 1, "0")
        digits = (digits[:-scale] + "." + digits[-scale:]).rstrip("0").rstrip(".")
    result = ("-" if value < 0 else "") + digits
    if len(result) > 80 or result == "-0" or DECIMAL.fullmatch(result) is None:
        abort("semantic_realized_fifo_rounding_policy_required")
    return result


def utc(value: Any, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        abort("semantic_realized_fifo_input_invalid")
    try:
        if datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            abort("semantic_realized_fifo_input_invalid")
    except ValueError:
        abort("semantic_realized_fifo_input_invalid")
    return value


def owner_file(value: str | Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        abort("semantic_realized_fifo_ledger_invalid")
    current = path
    while current.parent != current:
        if current.is_symlink():
            abort("semantic_realized_fifo_ledger_invalid")
        current = current.parent
    try:
        info = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError:
        abort("semantic_realized_fifo_ledger_invalid")
    if resolved != path or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid():
        abort("semantic_realized_fifo_ledger_invalid")
    return resolved


def connect(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(f"file:{quote(str(path))}?mode=ro&immutable=1", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error:
        abort("semantic_realized_fifo_ledger_invalid")


def context_values(value: Mapping[str, Any]) -> tuple[str, str, str, str]:
    if not isinstance(value, Mapping) or set(value) != {"tenant_id", "user_id", "data_space_id"}:
        abort("semantic_realized_fifo_context_invalid")
    values = tuple(value[key] for key in ("tenant_id", "user_id", "data_space_id"))
    if any(not isinstance(item, str) or TOKEN.fullmatch(item) is None for item in values):
        abort("semantic_realized_fifo_context_invalid")
    material = "|".join(("realized-fifo-context-v1", *values))
    return (*values, hashlib.sha256(material.encode("utf-8")).hexdigest())


@dataclass
class Lot:
    origin_ref: str
    segment_ref: str
    acquisition_event_ref: str
    acquisition_semantic_contract: str
    acquisition_effective_at_utc: str | None
    acquisition_local_date: str
    order: tuple[Any, ...]
    asset_id: str
    currency: str
    quantity: Fraction
    cost: Fraction | None


@dataclass
class Metric:
    account_id: str
    asset_id: str
    currency: str
    proceeds: Fraction = Fraction(0)
    basis: Fraction = Fraction(0)
    realized: Fraction = Fraction(0)
    income: Fraction = Fraction(0)
    fees: Fraction = Fraction(0)
    cash: Fraction = Fraction(0)
    semantics: set[str] = field(default_factory=set)


def coverage(values: Iterable[str]) -> str:
    observed = set(values)
    if observed == {OLD}:
        return OLD
    if observed == {ACTIVITY}:
        return ACTIVITY
    if observed == {OLD, ACTIVITY}:
        return "mixed_explicit_semantic_contracts"
    if not observed:
        return "none"
    abort("semantic_realized_fifo_source_invalid")


def normalize_old(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "fact_ref": row["transaction_id"], "semantic_contract": OLD,
        "coupled_transaction_fact": "1", "automatic_cash_posting_created": None,
        "event_type": row["event_type"], "event_time_evidence": "exact",
        "effective_at_utc": row["effective_at_utc"], "local_date": row["local_date"],
        "account_id": row["account_id"], "related_account_id": row["related_account_id"],
        "asset_id": row["asset_id"], "quantity": fraction(row["quantity_decimal"], positive=True),
        "unit_price": fraction(row["unit_price_decimal"], positive=True),
        "gross_amount": fraction(row["gross_amount_decimal"], positive=True, nullable=True),
        "monetary_fee": fraction(row["fee_decimal"], positive=True, nullable=True) or Fraction(0),
        "asset_fee": Fraction(0), "currency": row["transaction_currency"],
        "basis_created": None, "net_proceeds": None, "gross_income": None,
        "distribution_value": None, "basis_missing": False,
        "original_date": None, "original_utc": None,
    }


def normalize_activity(row: Mapping[str, Any]) -> dict[str, Any]:
    if row["cash_posting_created"] != 0 or row["provider_price_used"] != 0 or row["tax_classification_inferred"] != 0:
        abort("semantic_realized_fifo_source_invalid")
    return {
        "fact_ref": row["event_ref"], "semantic_contract": ACTIVITY,
        "coupled_transaction_fact": "0", "automatic_cash_posting_created": "0",
        "event_type": row["event_type"], "event_time_evidence": row["event_time_evidence"],
        "effective_at_utc": row["effective_at_utc"], "local_date": row["local_date"],
        "account_id": row["account_id"], "related_account_id": row["related_account_id"],
        "asset_id": row["asset_id"], "quantity": fraction(row["quantity_decimal"], positive=True, nullable=True),
        "unit_price": fraction(row["unit_price_decimal"], positive=True, nullable=True),
        "gross_amount": fraction(row["gross_amount_decimal"], positive=True, nullable=True),
        "monetary_fee": fraction(row["monetary_fee_decimal"], positive=True, nullable=True) or Fraction(0),
        "asset_fee": fraction(row["asset_fee_quantity_decimal"], positive=True, nullable=True) or Fraction(0),
        "currency": row["basis_currency"],
        "basis_created": fraction(row["fifo_basis_created_decimal"], positive=True, nullable=True),
        "net_proceeds": fraction(row["net_trade_proceeds_decimal"], nullable=True),
        "basis_missing": row["basis_evidence_mode"] == "basis_missing",
        "gross_income": fraction(row["gross_income_decimal"], positive=True, nullable=True),
        "distribution_value": fraction(row["distribution_value_decimal"], positive=True, nullable=True),
        "original_date": row["original_acquired_local_date"],
        "original_utc": row["original_acquired_at_utc"],
    }


def amount(event: Mapping[str, Any]) -> Fraction | None:
    if event["gross_amount"] is not None:
        return event["gross_amount"]
    if event["quantity"] is not None and event["unit_price"] is not None:
        return event["quantity"] * event["unit_price"]
    return None


def touches(event: Mapping[str, Any]) -> set[str]:
    return {value for value in (event["account_id"], event["related_account_id"]) if value is not None}


def assert_order(events: Sequence[Mapping[str, Any]], assets: Mapping[str, Mapping[str, Any]]) -> None:
    inventory = {"buy", "sell", "stock_dividend", "reward", "deposit", "withdrawal", "transfer", "fee"}
    relevant = [event for event in events if assets[event["asset_id"]]["asset_type"] != "cash" and event["event_type"] in inventory]
    for index, left in enumerate(relevant):
        for right in relevant[index + 1:]:
            if left["asset_id"] != right["asset_id"] or left["local_date"] != right["local_date"] or not touches(left).intersection(touches(right)):
                continue
            if left["event_time_evidence"] == "date_only" or right["event_time_evidence"] == "date_only":
                abort("semantic_realized_fifo_order_evidence_required")
            if left["effective_at_utc"] == right["effective_at_utc"] and ACTIVITY in {left["semantic_contract"], right["semantic_contract"]}:
                abort("semantic_realized_fifo_order_evidence_required")


ALLOCATION_SCALE = 10 ** 12


def allocate_lot_cost(cost: Fraction, take: Fraction, quantity: Fraction) -> Fraction:
    """Anteilige Losbasis mit fester Skala; der exakte Rest bleibt im Los.

    Der proportionale Anteil ist oft periodisch (etwa 83 von 120 Stueck).  Er wird auf
    ALLOCATION_SCALE Nachkommastellen gerundet, damit jede Bewegung eine endliche
    Dezimalzahl traegt.  Weil der Aufrufer die Differenz vom Los abzieht, bleiben die
    Summen exakt; ein vollstaendiger Verbrauch gibt die Losbasis unveraendert zurueck.
    """
    if take == quantity:
        return cost
    return Fraction(round(cost * take / quantity * ALLOCATION_SCALE), ALLOCATION_SCALE)


def consume(lots: dict[tuple[str, str], list[Lot]], account: str, asset: str, quantity: Fraction) -> list[tuple[Lot, Fraction, Fraction | None]]:
    current = sorted(lots.get((account, asset), []), key=lambda item: item.order)
    remaining = quantity
    consumed = []
    while remaining:
        if not current:
            abort("semantic_realized_fifo_inventory_insufficient")
        lot = current[0]
        take = min(remaining, lot.quantity)
        cost = None if lot.cost is None else allocate_lot_cost(lot.cost, take, lot.quantity)
        consumed.append((lot, take, cost))
        lot.quantity -= take
        if lot.cost is not None:
            lot.cost -= cost
        remaining -= take
        if lot.quantity == 0:
            current.pop(0)
    lots[(account, asset)] = current
    return consumed


def _split_ratios(splits: Sequence[Mapping[str, Any]]) -> dict[str, list[tuple[str, Fraction]]]:
    """Aktiensplits fuer alle Konten (#451) je Asset: Stichtag und Verhaeltnis neu/alt. Kontobezogene Splits kennt dieser Weg nicht."""
    ratios: dict[str, list[tuple[str, Fraction]]] = {}
    for split in splits:
        if not isinstance(split, Mapping) or split.get("account_ref") is not None or not isinstance(split.get("asset_ref"), str) or \
                not isinstance(split.get("effective_local_date"), str) or len(split["effective_local_date"]) != 10:
            abort("semantic_realized_fifo_input_invalid")
        numerator, denominator = split.get("ratio_numerator"), split.get("ratio_denominator")
        if not all(isinstance(value, str) and value.isdigit() and value[0] != "0" for value in (numerator, denominator)) or numerator == denominator:
            abort("semantic_realized_fifo_input_invalid")
        ratios.setdefault(split["asset_ref"], []).append((split["effective_local_date"], Fraction(int(numerator), int(denominator))))
    return ratios


def _factor_before(steps: Sequence[tuple[str, Fraction]], day: str) -> Fraction:
    """Das Verhaeltnis aller Splits nach dem Tag: so viele neue Stuecke je Stueck des Tages."""
    factor = Fraction(1)
    for effective, ratio in steps:
        if day < effective:
            factor *= ratio
    return factor


def _divide_before_splits(events: list[dict[str, Any]], splits: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aktiensplits fuer alle Konten (#451, rc.370): Mengen vor dem Stichtag zum Rechnen in neue Stuecke umgerechnet.

    Der FIFO-Kern v2 teilt am Stichtag die offenen Lots. Dieser Weg rechnet stattdessen jede fruehere Buchung des Assets in neue
    Stuecke um (Menge x neu/alt, Stueckpreis / neu/alt). Betraege, Reihenfolge und Anteile je Verbrauch bleiben, deshalb sind
    Gewinne, Einstand und Restbestand gleich. Ausgegeben werden die Mengen wieder in Belegstuecken (`_restore_document_units`).
    """
    ratios = _split_ratios(splits)
    divided = []
    for event in events:
        factor = _factor_before(ratios.get(event["asset_id"], ()), event["local_date"])
        if factor != 1:
            event = dict(event)
            for key in ("quantity", "asset_fee"):
                if event[key]:
                    event[key] = event[key] * factor
            if event["unit_price"] is not None:
                event["unit_price"] = event["unit_price"] / factor
        divided.append(event)
    return divided


def _restore_document_units(tables: Mapping[str, list[dict[str, Any]]], splits: Sequence[Mapping[str, Any]], context_fp: str) -> None:
    """Mengen vor einem Split wieder in Belegstuecken (#451, rc.371): wie in Data, Tageshistorie und Beleg.

    Gerechnet wird in neuen Stuecken (`_divide_before_splits`). Eine Buchung vor dem Stichtag steht danach wieder mit der Menge
    ihres Belegs, ebenso ihre Lot-Bewegungen und der Bestand nach ihr. Buchungen ab dem Stichtag, Restbestand und Summen zum Stichtag
    der Rechnung stehen in neuen Stuecken; Betraege aendern sich nicht.
    """
    ratios = {public_ref("asf_", context_fp, asset_id): steps for asset_id, steps in _split_ratios(splits).items()}
    if not ratios:
        return

    def restore(row: dict[str, Any], key: str, day: str) -> None:
        factor = _factor_before(ratios.get(row["asset_ref"], ()), day)
        if factor != 1 and row[key] is not None:
            row[key] = decimal_text(Fraction(row[key]) / factor)

    days: dict[str, str] = {}
    for row in tables["event-results.csv"]:
        days[row["event_ref"]] = row["local_date"]
        restore(row, "quantity_decimal", row["local_date"])
        restore(row, "asset_fee_quantity_decimal", row["local_date"])
    for row in tables["lot-movements.csv"]:
        if row["event_ref"] not in days:
            abort("semantic_realized_fifo_source_invalid")
        restore(row, "quantity_decimal", days[row["event_ref"]])
    for row in tables["position-history.csv"]:
        restore(row, "position_quantity_decimal", row["local_date"])


def build_semantic_realized_fifo_read_model_v1(
    database_path: str | Path, context: Mapping[str, Any], portfolio_id: str,
    evidence_cutoff_at_utc: str, completed_at_utc: str, splits: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    path = owner_file(database_path)
    tenant, user, space, context_fp = context_values(context)
    cutoff, completed = utc(evidence_cutoff_at_utc), utc(completed_at_utc)
    if not isinstance(portfolio_id, str) or not portfolio_id.startswith("ptf_") or completed < cutoff:
        abort("semantic_realized_fifo_input_invalid")
    connection = connect(path)
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM ledger_store_binding").fetchall()
        if connection.execute("PRAGMA user_version").fetchone()[0] != 401 or len(binding) != 1 or binding[0]["schema_version"] != 401:
            abort("semantic_realized_fifo_ledger_invalid")
        if tuple(binding[0][key] for key in ("tenant_id", "user_id", "data_space_id")) != (tenant, user, space):
            abort("semantic_realized_fifo_context_invalid")
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
            abort("semantic_realized_fifo_ledger_invalid")
        portfolio = connection.execute(
            "SELECT entity.portfolio_id,revision.base_currency,revision.status FROM portfolio_entity entity "
            "JOIN current_portfolio_revision revision USING(portfolio_id) WHERE entity.portfolio_id=?", (portfolio_id,)
        ).fetchall()
        if len(portfolio) != 1 or portfolio[0]["status"] != "active":
            abort("semantic_realized_fifo_portfolio_missing")
        accounts = {row["account_id"]: dict(row) for row in connection.execute(
            "SELECT entity.account_id,revision.account_type,revision.status FROM account_entity entity "
            "JOIN current_account_revision revision USING(account_id) WHERE entity.portfolio_id=?", (portfolio_id,)
        )}
        assets = {row["asset_id"]: dict(row) for row in connection.execute(
            "SELECT asset_id,asset_type,status FROM current_asset_revision"
        )}
        old_rows = [dict(row) for row in connection.execute(
            "SELECT * FROM current_transaction_fact WHERE portfolio_id=? ORDER BY effective_at_utc,transaction_id", (portfolio_id,)
        )]
        activity_rows = [dict(row) for row in connection.execute(
            "SELECT * FROM current_asset_activity_event WHERE portfolio_id=? ORDER BY local_date,COALESCE(effective_at_utc,''),event_ref", (portfolio_id,)
        )]
        compatible = {row[0]: row[1] for row in connection.execute(
            "SELECT semantic_contract,count(*) FROM compatible_ledger_event WHERE portfolio_id=? GROUP BY semantic_contract", (portfolio_id,)
        )}
    except sqlite3.Error:
        abort("semantic_realized_fifo_ledger_invalid")
    finally:
        connection.close()
    if compatible.get(OLD, 0) != len(old_rows) or compatible.get(ACTIVITY, 0) != len(activity_rows):
        abort("semantic_realized_fifo_source_invalid")
    events = [normalize_old(row) for row in old_rows] + [normalize_activity(row) for row in activity_rows]
    # Splits nach dem Stichtag der Rechnung gelten noch nicht (#451): Bestand und Buchungen stehen dann in den Stuecken von damals.
    _split_ratios(splits)
    splits = [split for split in splits if split["effective_local_date"] <= cutoff[:10]]
    if splits:
        events = _divide_before_splits(events, splits)
    if any(event["account_id"] not in accounts or event["asset_id"] not in assets or event["related_account_id"] is not None and event["related_account_id"] not in accounts for event in events):
        abort("semantic_realized_fifo_source_invalid")
    selected = [event for event in events if event["local_date"] <= cutoff[:10] and (event["effective_at_utc"] is None or event["effective_at_utc"] <= cutoff)]
    assert_order(selected, assets)
    selected.sort(key=lambda event: (event["local_date"], event["effective_at_utc"] is not None, event["effective_at_utc"] or "", event["semantic_contract"], event["fact_ref"]))
    bindings = [
        {"semantic_contract": OLD, "source_event_count": len(old_rows), "projected_event_count": sum(e["semantic_contract"] == OLD for e in selected), "coupled_transaction_fact": True, "automatic_cash_posting_state": "unknown"},
        {"semantic_contract": ACTIVITY, "source_event_count": len(activity_rows), "projected_event_count": sum(e["semantic_contract"] == ACTIVITY for e in selected), "coupled_transaction_fact": False, "automatic_cash_posting_state": "none_created"},
    ]
    source = {"portfolio": dict(portfolio[0]), "accounts": accounts, "assets": assets, "old": old_rows, "activity": activity_rows, "cutoff": cutoff, "bindings": bindings}
    if splits:
        source["splits"] = sorted((dict(split) for split in splits), key=lambda split: (split["effective_local_date"], split["asset_ref"]))
    input_fp = sha(source)
    portfolio_ref = public_ref("pfr_", context_fp, portfolio_id)
    # Imported lazily to keep the pure projector independently testable without a
    # circular module-initialization dependency.
    from workers.reference.semantic_realized_fifo_projector_v1 import project_events

    tables = project_events(selected, accounts, assets, context_fp)
    _restore_document_units(tables, splits, context_fp)
    row_fp = sha([{"table": name, "rows": tables[name]} for name in TABLE_COLUMNS])
    artifact = {
        "artifact_ref": public_ref("rar_", context_fp, input_fp), "portfolio_ref": portfolio_ref,
        "algorithm_version": ALGORITHM_VERSION, "input_fingerprint": input_fp,
        "evidence_artifact_fingerprint": row_fp, "evidence_cutoff_at_utc": cutoff,
        "rebuild_mode": "full", "base_artifact_ref": None, "row_set_fingerprint": row_fp,
        "semantic_source_bindings": bindings, "semantic_binding_fingerprint": sha(bindings),
        "completed_at_utc": completed,
        "context_binding_fingerprint": context_fp,
    }
    return {
        "contract_version": 1, "status": "completed", "artifact": artifact, "tables": tables,
        "reconciliation": {
            "source_current_event_count": len(events), "projected_event_count": len(selected),
            "excluded_after_cutoff_count": len(events) - len(selected),
            "event_result_count": len(tables["event-results.csv"]),
            "lot_movement_count": len(tables["lot-movements.csv"]),
            "remaining_lot_count": len(tables["remaining-lots.csv"]),
            "position_summary_count": len(tables["position-summary.csv"]),
            "projection_reconciliation_status": "full_oracle_not_persisted",
            "semantic_binding_fingerprint": artifact["semantic_binding_fingerprint"],
        }, "stale_jobs": [],
    }


def _csv_bytes(rows: Any, columns: tuple[str, ...]) -> bytes:
    if not isinstance(rows, list):
        abort("semantic_realized_fifo_publication_invalid")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        if not isinstance(row, dict) or set(row) != set(columns):
            abort("semantic_realized_fifo_publication_invalid")
        values: list[str] = []
        for column in columns:
            value = row[column]
            if value is None:
                values.append("")
                continue
            if not isinstance(value, str) or "\r" in value or "\n" in value:
                abort("semantic_realized_fifo_publication_invalid")
            if not column.endswith("_decimal") and value.startswith(("=", "+", "@")):
                abort("semantic_realized_fifo_publication_invalid")
            if not column.endswith("_decimal") and value.startswith("-") and not value[1:].isdigit():
                abort("semantic_realized_fifo_publication_invalid")
            values.append(value)
        writer.writerow(values)
    return stream.getvalue().encode("utf-8")


def _exclusive_file(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short_write")
            view = view[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_semantic_realized_fifo_evidence_v1(
    read_model: Mapping[str, Any], output_path: str | Path
) -> dict[str, Any]:
    """Publish one immutable owner-only completed evidence directory.

    The target must be an absent absolute path below an existing owner-only,
    symlink-free directory.  CSVs are completed and fsynced before the manifest.
    """
    if (
        not isinstance(read_model, Mapping)
        or read_model.get("contract_version") != 1
        or read_model.get("status") != "completed"
        or not isinstance(read_model.get("artifact"), dict)
        or not isinstance(read_model.get("reconciliation"), dict)
        or not isinstance(read_model.get("tables"), dict)
        or tuple(read_model["tables"]) != tuple(TABLE_COLUMNS)
    ):
        abort("semantic_realized_fifo_publication_invalid")
    artifact = read_model["artifact"]
    required_artifact = {
        "artifact_ref", "portfolio_ref", "algorithm_version", "input_fingerprint",
        "evidence_artifact_fingerprint", "evidence_cutoff_at_utc", "rebuild_mode",
        "base_artifact_ref", "row_set_fingerprint", "semantic_source_bindings",
        "semantic_binding_fingerprint", "completed_at_utc", "context_binding_fingerprint",
    }
    if set(artifact) != required_artifact or artifact["algorithm_version"] != ALGORITHM_VERSION:
        abort("semantic_realized_fifo_publication_invalid")
    target = Path(output_path)
    if not target.is_absolute() or target.exists() or target.is_symlink():
        abort("semantic_realized_fifo_publication_invalid")
    try:
        parent = target.parent.resolve(strict=True)
        parent_info = parent.stat(follow_symlinks=False)
    except OSError:
        abort("semantic_realized_fifo_publication_invalid")
    if (
        target.parent != parent
        or target.parent.is_symlink()
        or not stat.S_ISDIR(parent_info.st_mode)
        or stat.S_IMODE(parent_info.st_mode) != 0o700
        or parent_info.st_uid != os.geteuid()
    ):
        abort("semantic_realized_fifo_publication_invalid")
    previous_umask = os.umask(0o077)
    completed = False
    try:
        os.mkdir(target, 0o700)
        os.chmod(target, 0o700)
        files: list[dict[str, Any]] = []
        for file_name, columns in TABLE_COLUMNS.items():
            payload = _csv_bytes(read_model["tables"][file_name], columns)
            _exclusive_file(target / file_name, payload)
            files.append(
                {
                    "file_name": file_name,
                    "content_role": TABLE_ROLES[file_name],
                    "row_count": len(read_model["tables"][file_name]),
                    "sha256": sha(payload),
                }
            )
        manifest_body = {
            "calculation_evidence_version": 1,
            "profile_id": "realized_fifo_v1_1",
            "status": "completed",
            "algorithm_version": artifact["algorithm_version"],
            "portfolio_ref": artifact["portfolio_ref"],
            "context_binding_fingerprint": artifact["context_binding_fingerprint"],
            "input_fingerprint": artifact["input_fingerprint"],
            "evidence_cutoff_at_utc": artifact["evidence_cutoff_at_utc"],
            "files": files,
            "reconciliation": read_model["reconciliation"],
            "semantic_source_bindings": artifact["semantic_source_bindings"],
            "semantic_binding_fingerprint": artifact["semantic_binding_fingerprint"],
            "boundaries": {
                "canonical_write": False,
                "provider_access": False,
                "network_access": False,
                "app_side_calculation": False,
                "tax_calculation": False,
                "market_calculation": False,
                "automatic_retry": False,
                "grouping_dependency": False,
                "automatic_cash_posting_created": False,
            },
        }
        manifest_body["artifact_fingerprint"] = sha(manifest_body)
        manifest_payload = canonical(manifest_body) + b"\n"
        _exclusive_file(target / "evidence-manifest.json", manifest_payload)
        directory = os.open(target, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        completed = True
        return {
            "status": "evidence_published",
            "artifact_fingerprint": manifest_body["artifact_fingerprint"],
            "file_count": len(files),
            "row_count": sum(item["row_count"] for item in files),
        }
    except SemanticRealizedFifoV1Error:
        raise
    except (OSError, TypeError, ValueError):
        abort("semantic_realized_fifo_publication_failed")
    finally:
        os.umask(previous_umask)
        if not completed and target.exists() and not target.is_symlink():
            import shutil
            shutil.rmtree(target, ignore_errors=True)
