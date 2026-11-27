#!/usr/bin/env python3
"""Lossless current-Product CSV exchange with redundant Asset/Account projections.

The canonical portfolio CSV contains each current Catalog, Provider Mapping, coupled
Transaction and schema-401 Asset Activity fact once. Asset and Account files are
self-contained redundant projections. CSV uses RFC-4180 comma separation, quotes all
fields and localizes exact Decimal strings to a comma. Import validates and stages the
complete bundle; Product writers remain separate handoffs.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import ctypes
import errno
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
from typing import Any, Iterable, Mapping
from urllib.parse import quote

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.desktop_cash_coverage_v1 import (
    DesktopCashCoverageV1Error,
    read_desktop_cash_coverage_exchange_projection_v1,
)

CONTRACT_VERSION = 1
AREA = "portfolio-csv-exchange-v1"
HEADER = (
    "record_kind", "record_ref", "scope_role", "scope_ref", "portfolio_ref",
    "account_ref", "asset_ref", "event_ref", "portfolio_name", "account_name",
    "related_account_name", "asset_name", "source_asset_name", "event_type",
    "local_date", "effective_at_utc", "quantity_decimal", "eligible_quantity_decimal",
    "unit_price_decimal", "gross_amount_decimal", "monetary_fee_decimal",
    "asset_fee_quantity_decimal", "provided_basis_decimal", "basis_currency",
    "payload_json", "record_fingerprint",
)
DECIMAL_KEY = re.compile(r"(?:^|_)decimal$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{3,80}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
REF = re.compile(r"^[a-z]{2,4}x_[a-f0-9]{24}$")
BUNDLE_NAME = re.compile(r"^portfolio-export-[a-f0-9]{24}$")
IMPORT_NAME = re.compile(r"^imp_[a-f0-9]{24}$")
RECORD_KINDS = frozenset({
    "portfolio", "account", "asset", "provider_mapping", "coupled_transaction", "coupled_posting",
    "asset_activity", "fifo_order_evidence", "cash_coverage_period", "cash_event",
    "cash_interest_income", "cash_reconciliation",
})
REFERENCE_KEYS = frozenset({
    "portfolio_id", "account_id", "related_account_id", "asset_id", "source_asset_id", "cash_asset_id",
    "mapping_id", "transaction_id", "supersedes_transaction_id", "posting_id", "event_ref",
    "linked_cash_event_id", "source_command_ref",
})
FAILURE_CODES = frozenset({
    "portfolio_csv_context_invalid", "portfolio_csv_source_invalid",
    "portfolio_csv_schema_unsupported", "portfolio_csv_source_changed",
    "portfolio_csv_output_conflict", "portfolio_csv_bundle_invalid",
    "portfolio_csv_redundancy_invalid", "portfolio_csv_decimal_invalid",
    "portfolio_csv_confirmation_required", "portfolio_csv_confirmation_consumed", "portfolio_csv_write_failed",
    "portfolio_csv_boundary_failed",
})


class PortfolioCsvExchangeV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("portfolio_csv_error_unregistered")
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise PortfolioCsvExchangeV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    except Exception:
        _abort("portfolio_csv_source_invalid")


def _sha(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


@dataclass(frozen=True)
class PortfolioCsvContextV1:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str = "desktop_owner"
    role: str = "desktop_owner"


@dataclass(frozen=True)
class SourceSnapshot:
    path: Path
    fingerprint: str


@dataclass(frozen=True)
class PortfolioCsvExportPlanV1:
    context: PortfolioCsvContextV1
    context_fingerprint: str
    snapshots: tuple[SourceSnapshot, ...]
    records: tuple[dict[str, Any], ...]
    file_payloads: tuple[tuple[str, bytes, int, str, str], ...]
    manifest: dict[str, Any]
    bundle_fingerprint: str


@dataclass(frozen=True)
class PortfolioCsvImportPlanV1:
    bundle_path: Path
    snapshots: tuple[SourceSnapshot, ...]
    records: tuple[dict[str, Any], ...]
    manifest: dict[str, Any]
    bundle_fingerprint: str


def _context(value: PortfolioCsvContextV1 | Mapping[str, Any]) -> PortfolioCsvContextV1:
    if isinstance(value, Mapping):
        try:
            value = PortfolioCsvContextV1(
                value["tenant_id"], value["user_id"], value["data_space_id"],
                value.get("actor_id", "desktop_owner"), value.get("role", "desktop_owner"),
            )
        except (KeyError, TypeError) as error:
            raise PortfolioCsvExchangeV1Error("portfolio_csv_context_invalid") from error
    if (
        not isinstance(value, PortfolioCsvContextV1)
        or value.actor_id != "desktop_owner" or value.role != "desktop_owner"
        or not value.data_space_id.startswith("sbx_")
        or any(not isinstance(item, str) or TOKEN.fullmatch(item) is None or len(item) > 64
               for item in (value.tenant_id, value.user_id, value.data_space_id))
    ):
        _abort("portfolio_csv_context_invalid")
    return value


def _context_fp(value: PortfolioCsvContextV1) -> str:
    return _sha({
        "contract": "portfolio_csv_context_v1", "tenant_id": value.tenant_id,
        "user_id": value.user_id, "data_space_id": value.data_space_id,
    })


def _owner_directory(path: str | Path, *, create: bool = False) -> Path:
    path = Path(path)
    if create and not path.exists():
        try:
            path.mkdir(mode=0o700)
            path.chmod(0o700)
        except OSError:
            _abort("portfolio_csv_write_failed")
    try:
        info = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError:
        _abort("portfolio_csv_source_invalid")
    if (
        not path.is_absolute() or path.is_symlink() or resolved != path
        or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.geteuid()
    ):
        _abort("portfolio_csv_source_invalid")
    current = path
    while current.parent != current:
        if current.is_symlink():
            _abort("portfolio_csv_source_invalid")
        current = current.parent
    return path


def _regular_file(path: str | Path, code: str = "portfolio_csv_source_invalid") -> Path:
    path = Path(path)
    try:
        info = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError:
        _abort(code)
    if (
        not path.is_absolute() or path.is_symlink() or resolved != path
        or not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
    ):
        _abort(code)
    return path


def portfolio_csv_exchange_paths_v1(
    data_space_path: str | Path, context_value: PortfolioCsvContextV1 | Mapping[str, Any], *, create: bool = False,
) -> dict[str, Path]:
    context = _context(context_value)
    data_space = _owner_directory(data_space_path)
    if data_space.name != context.data_space_id:
        _abort("portfolio_csv_context_invalid")
    area = data_space / AREA
    if create:
        area = _owner_directory(area, create=True)
        for name in ("import-inbox", "exports", "imports", "attempts", "receipts", "failures"):
            _owner_directory(area / name, create=True)
    return {
        "area": area, "import_inbox": area / "import-inbox", "exports": area / "exports",
        "imports": area / "imports", "attempts": area / "attempts",
        "receipts": area / "receipts", "failures": area / "failures",
    }


def _snapshot(path: Path) -> SourceSnapshot:
    path = _regular_file(path)
    return SourceSnapshot(path, hashlib.sha256(path.read_bytes()).hexdigest())


def _revalidate(snapshot: SourceSnapshot) -> None:
    path = _regular_file(snapshot.path, "portfolio_csv_source_changed")
    if hashlib.sha256(path.read_bytes()).hexdigest() != snapshot.fingerprint:
        _abort("portfolio_csv_source_changed")


def _connect_ro(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(f"file:{quote(str(path))}?mode=ro&immutable=1", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error as error:
        raise PortfolioCsvExchangeV1Error("portfolio_csv_schema_unsupported") from error


def _ref(prefix: str, context_fp: str, internal_id: str) -> str:
    return f"{prefix}x_{_sha({'kind': prefix, 'context': context_fp, 'id': internal_id})[:24]}"


def _record(kind: str, ref: str, payload: dict[str, Any], *, portfolio_ref: str = "",
            account_ref: str = "", asset_ref: str = "", event_ref: str = "") -> dict[str, Any]:
    body = {
        "record_kind": kind, "record_ref": ref, "portfolio_ref": portfolio_ref,
        "account_ref": account_ref, "asset_ref": asset_ref, "event_ref": event_ref,
        "payload": payload,
    }
    body["record_fingerprint"] = _sha(body)
    return body


def _map_row(row: sqlite3.Row, replacements: Mapping[str, Mapping[str, str]], omit: Iterable[str] = ()) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in row.keys():
        if key in omit:
            continue
        value = row[key]
        if key in replacements and value is not None:
            try:
                value = replacements[key][str(value)]
            except KeyError:
                _abort("portfolio_csv_source_invalid")
        result[key] = value
    return result


def _read_current_records(canonical_path: Path, data_space_path: Path,
                          context: PortfolioCsvContextV1) -> tuple[list[dict[str, Any]], tuple[SourceSnapshot, ...], int, int, str, int, str]:
    canonical = _snapshot(canonical_path)
    context_fp = _context_fp(context)
    connection = _connect_ro(canonical.path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id,created_at_utc FROM store_binding WHERE singleton_id=1"
        ).fetchall()
        if (
            version not in {201, 202} or len(binding) != 1
            or tuple(binding[0][:4]) != (version, context.tenant_id, context.user_id, context.data_space_id)
            or connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _abort("portfolio_csv_schema_unsupported")
        portfolios = connection.execute("SELECT * FROM portfolio ORDER BY portfolio_id").fetchall()
        if not portfolios:
            _abort("portfolio_csv_source_invalid")
        accounts = connection.execute("SELECT * FROM account ORDER BY account_id").fetchall()
        assets = connection.execute("SELECT * FROM asset ORDER BY asset_id").fetchall()
        provider_mappings = connection.execute("SELECT * FROM provider_mapping ORDER BY mapping_id").fetchall()
        transactions = connection.execute("SELECT * FROM transaction_record ORDER BY transaction_id").fetchall()
        postings = connection.execute("SELECT * FROM transaction_posting ORDER BY transaction_id,sequence_no,posting_id").fetchall()
        seals = {row["transaction_id"]: dict(row) for row in connection.execute("SELECT * FROM transaction_seal ORDER BY transaction_id")}
    except sqlite3.Error as error:
        raise PortfolioCsvExchangeV1Error("portfolio_csv_schema_unsupported") from error
    finally:
        connection.close()
    portfolio_refs = {row["portfolio_id"]: _ref("pf", context_fp, row["portfolio_id"]) for row in portfolios}
    account_refs = {row["account_id"]: _ref("ac", context_fp, row["account_id"]) for row in accounts}
    asset_refs = {row["asset_id"]: _ref("as", context_fp, row["asset_id"]) for row in assets}
    mapping_refs = {row["mapping_id"]: _ref("pm", context_fp, row["mapping_id"]) for row in provider_mappings}
    transaction_refs = {row["transaction_id"]: _ref("tx", context_fp, row["transaction_id"]) for row in transactions}
    posting_refs = {row["posting_id"]: _ref("po", context_fp, row["posting_id"]) for row in postings}
    replacements = {"portfolio_id": portfolio_refs, "account_id": account_refs, "related_account_id": account_refs,
                    "asset_id": asset_refs, "source_asset_id": asset_refs, "mapping_id": mapping_refs,
                    "transaction_id": transaction_refs, "supersedes_transaction_id": transaction_refs,
                    "posting_id": posting_refs}
    records: list[dict[str, Any]] = []
    for row in portfolios:
        ref = portfolio_refs[row["portfolio_id"]]
        records.append(_record("portfolio", ref, _map_row(row, replacements, ("portfolio_id",)), portfolio_ref=ref))
    for row in accounts:
        ref = account_refs[row["account_id"]]; portfolio_ref = portfolio_refs[row["portfolio_id"]]
        records.append(_record("account", ref, _map_row(row, replacements, ("account_id",)), portfolio_ref=portfolio_ref, account_ref=ref))
    for row in assets:
        ref = asset_refs[row["asset_id"]]
        records.append(_record("asset", ref, _map_row(row, replacements, ("asset_id",)), asset_ref=ref))
    for row in provider_mappings:
        ref = mapping_refs[row["mapping_id"]]; asset_ref = asset_refs[row["asset_id"]]
        records.append(_record("provider_mapping", ref, _map_row(row, replacements, ("mapping_id",)), asset_ref=asset_ref))
    for row in transactions:
        ref = transaction_refs[row["transaction_id"]]; portfolio_ref = portfolio_refs[row["portfolio_id"]]
        payload = _map_row(row, replacements, ("transaction_id", "created_by_actor"))
        seal = seals.get(row["transaction_id"])
        if seal is None:
            _abort("portfolio_csv_source_invalid")
        payload["seal"] = {key: value for key, value in seal.items() if key != "transaction_id"}
        records.append(_record("coupled_transaction", ref, payload, portfolio_ref=portfolio_ref, event_ref=ref))
    for row in postings:
        ref = posting_refs[row["posting_id"]]; account_ref = account_refs[row["account_id"]]; asset_ref = asset_refs[row["asset_id"]]
        tx_ref = transaction_refs[row["transaction_id"]]
        records.append(_record("coupled_posting", ref, _map_row(row, replacements, ("posting_id",)), account_ref=account_ref, asset_ref=asset_ref, event_ref=tx_ref))

    activity_context = DesktopProductAssetActivityContextV1(
        context.tenant_id, context.user_id, context.data_space_id, context.actor_id, context.role
    )
    binding_value = read_desktop_product_asset_activity_binding_v1(data_space_path, activity_context)
    snapshots: list[SourceSnapshot] = [canonical]
    activity_version = 0
    activity_fp = _sha([])
    if binding_value["status"] == "available":
        ledger = _snapshot(Path(binding_value["ledger_path"])); snapshots.append(ledger); activity_version = 401
        ledger_connection = _connect_ro(ledger.path)
        try:
            events = ledger_connection.execute("SELECT * FROM asset_activity_event ORDER BY event_ref").fetchall()
            has_fifo = ledger_connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='asset_activity_fifo_order_evidence'").fetchone()[0] == 1
            fifo_rows = ledger_connection.execute("SELECT * FROM asset_activity_fifo_order_evidence ORDER BY event_ref").fetchall() if has_fifo else []
        except sqlite3.Error as error:
            raise PortfolioCsvExchangeV1Error("portfolio_csv_schema_unsupported") from error
        finally:
            ledger_connection.close()
        event_refs = {row["event_ref"]: _ref("av", context_fp, row["event_ref"]) for row in events}
        for row in events:
            ref = event_refs[row["event_ref"]]; portfolio_ref = portfolio_refs[row["portfolio_id"]]
            account_ref = account_refs[row["account_id"]]; asset_ref = asset_refs[row["asset_id"]]
            payload = _map_row(row, {**replacements, "event_ref": event_refs}, ("event_ref", "command_id"))
            records.append(_record("asset_activity", ref, payload, portfolio_ref=portfolio_ref,
                                   account_ref=account_ref, asset_ref=asset_ref, event_ref=ref))
        for row in fifo_rows:
            event_ref = event_refs[row["event_ref"]]; ref = _ref("fo", context_fp, row["event_ref"])
            payload = _map_row(row, {"event_ref": event_refs}, ())
            records.append(_record("fifo_order_evidence", ref, payload, event_ref=event_ref))
        activity_fp = binding_value["activity_set_fingerprint"]

    cash_version = 0
    cash_dimension = "absent_explicit"
    cash_store = data_space_path / "cash-coverage-v1" / "cash-coverage.sqlite"
    if cash_store.exists() or cash_store.is_symlink():
        cash_context = DesktopProductAssetActivityContextV1(
            context.tenant_id, context.user_id, context.data_space_id, context.actor_id, context.role
        )
        cash_snapshot = _snapshot(cash_store)
        try:
            cash_projection = read_desktop_cash_coverage_exchange_projection_v1(cash_snapshot.path, cash_context)
        except DesktopCashCoverageV1Error:
            _abort("portfolio_csv_source_invalid")
        cash_periods = cash_projection["coverage_periods"]
        cash_events = cash_projection["cash_events"]
        cash_incomes = cash_projection["income_events"]
        cash_reconciliations = cash_projection["reconciliations"]
        snapshots.append(cash_snapshot)
        cash_version = 2901
        cash_dimension = "complete_current"
        coverage_refs = {row["coverage_id"]: _ref("cv", context_fp, row["coverage_id"]) for row in cash_periods}
        cash_event_refs = {row["cash_event_id"]: _ref("ce", context_fp, row["cash_event_id"]) for row in cash_events}
        income_refs = {row["income_event_id"]: _ref("ci", context_fp, row["income_event_id"]) for row in cash_incomes}
        reconciliation_refs = {row["reconciliation_id"]: _ref("cr", context_fp, row["reconciliation_id"]) for row in cash_reconciliations}
        command_ids = sorted({row["command_id"] for row in (*cash_periods, *cash_events, *cash_incomes, *cash_reconciliations)})
        command_refs = {identifier: _ref("cm", context_fp, identifier) for identifier in command_ids}
        cash_replacements = {
            **replacements, "cash_asset_id": asset_refs, "linked_cash_event_id": cash_event_refs,
        }
        def cash_payload(row: sqlite3.Row, identifier: str) -> dict[str, Any]:
            payload = _map_row(row, cash_replacements, (identifier, "command_id"))
            payload["source_command_ref"] = command_refs[row["command_id"]]
            return payload
        for row in cash_periods:
            ref = coverage_refs[row["coverage_id"]]
            records.append(_record("cash_coverage_period", ref, cash_payload(row, "coverage_id"),
                                   portfolio_ref=portfolio_refs[row["portfolio_id"]], account_ref=account_refs[row["account_id"]],
                                   asset_ref=asset_refs[row["cash_asset_id"]], event_ref=ref))
        for row in cash_events:
            ref = cash_event_refs[row["cash_event_id"]]
            records.append(_record("cash_event", ref, cash_payload(row, "cash_event_id"),
                                   portfolio_ref=portfolio_refs[row["portfolio_id"]], account_ref=account_refs[row["account_id"]],
                                   asset_ref=asset_refs[row["cash_asset_id"]], event_ref=ref))
        for row in cash_incomes:
            # Der Record-Ref der Projektion macht einen Ertrag revidierbar (#465); er ist eine Kennung des Bestands,
            # kein Feld des Austauschs - mit ihm wies die Uebergabe jeden Export als ungueltig ab.
            row = {key: value for key, value in row.items() if key != "record_ref"}
            ref = income_refs[row["income_event_id"]]
            records.append(_record("cash_interest_income", ref, cash_payload(row, "income_event_id"),
                                   portfolio_ref=portfolio_refs[row["portfolio_id"]], account_ref=account_refs[row["account_id"]],
                                   asset_ref=asset_refs[row["cash_asset_id"]], event_ref=ref))
        for row in cash_reconciliations:
            ref = reconciliation_refs[row["reconciliation_id"]]
            records.append(_record("cash_reconciliation", ref, cash_payload(row, "reconciliation_id"),
                                   portfolio_ref=portfolio_refs[row["portfolio_id"]], account_ref=account_refs[row["account_id"]],
                                   asset_ref=asset_refs[row["cash_asset_id"]], event_ref=ref))
    records.sort(key=lambda row: (row["record_kind"], row["record_ref"]))
    return records, tuple(snapshots), version, activity_version, activity_fp, cash_version, cash_dimension


def _values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _values(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _values(item)


def _projection(records: list[dict[str, Any]], role: str, scope_ref: str) -> list[dict[str, Any]]:
    by_ref = {row["record_ref"]: row for row in records}
    known = set(by_ref)
    selected: set[str] = set()
    for row in records:
        if role == "asset" and (row["asset_ref"] == scope_ref or row["payload"].get("source_asset_id") == scope_ref):
            selected.add(row["record_ref"])
        if role == "account" and (
            row["account_ref"] == scope_ref or row["payload"].get("related_account_id") == scope_ref
            or row["payload"].get("account_id") == scope_ref
        ):
            selected.add(row["record_ref"])
    selected.add(scope_ref)
    changed = True
    while changed:
        before = len(selected)
        for ref in tuple(selected):
            row = by_ref.get(ref)
            if row is None:
                continue
            selected.update(value for value in _values(row) if value in known)
            if row["record_kind"] == "coupled_transaction":
                selected.update(item["record_ref"] for item in records if item["record_kind"] == "coupled_posting" and item["event_ref"] == ref)
            if row["record_kind"] == "asset_activity":
                selected.update(item["record_ref"] for item in records if item["record_kind"] == "fifo_order_evidence" and item["event_ref"] == ref)
        changed = len(selected) != before
    selected.update(row["record_ref"] for row in records if row["record_kind"] == "portfolio")
    return [row for row in records if row["record_ref"] in selected]


def _localize(value: Any) -> Any:
    if isinstance(value, list):
        return [_localize(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if DECIMAL_KEY.search(key) and isinstance(item, str):
                if "," in item or item.count(".") > 1:
                    _abort("portfolio_csv_decimal_invalid")
                item = item.replace(".", ",")
            result[key] = _localize(item)
        return result
    return value


def _delocalize(value: Any) -> Any:
    if isinstance(value, list):
        return [_delocalize(item) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if DECIMAL_KEY.search(key) and isinstance(item, str):
                if "." in item or item.count(",") > 1:
                    _abort("portfolio_csv_decimal_invalid")
                item = item.replace(",", ".")
            result[key] = _delocalize(item)
        return result
    return value


def _csv_bytes(records: Iterable[dict[str, Any]], scope_role: str, scope_ref: str) -> bytes:
    records = list(records); by_ref = {record["record_ref"]: record for record in records}
    def payload_for(ref: Any) -> dict[str, Any]:
        row = by_ref.get(ref) if isinstance(ref, str) else None
        return row["payload"] if row is not None else {}
    def label(ref: Any) -> str:
        value = payload_for(ref).get("display_name")
        if not isinstance(value, str):
            return ""
        return "'" + value if value.startswith(("'", "=", "+", "-", "@", "\t", "\r")) else value
    def decimal(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        return value.replace(".", ",") if isinstance(value, str) else ""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=HEADER, lineterminator="\n", quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for record in records:
        payload = record["payload"]; portfolio_ref = record["portfolio_ref"] or payload.get("portfolio_id", "")
        account_ref = record["account_ref"] or payload.get("account_id", ""); asset_ref = record["asset_ref"] or payload.get("asset_id", "")
        related_ref = payload.get("related_account_id", ""); source_asset_ref = payload.get("source_asset_id", "")
        event_type = payload.get("event_type") or payload.get("transaction_type") or payload_for(record["event_ref"]).get("transaction_type") or ""
        writer.writerow({
            "record_kind": record["record_kind"], "record_ref": record["record_ref"],
            "scope_role": scope_role, "scope_ref": scope_ref,
            "portfolio_ref": record["portfolio_ref"], "account_ref": record["account_ref"],
            "asset_ref": record["asset_ref"], "event_ref": record["event_ref"],
            "portfolio_name": label(portfolio_ref), "account_name": label(account_ref),
            "related_account_name": label(related_ref), "asset_name": label(asset_ref),
            "source_asset_name": label(source_asset_ref), "event_type": event_type,
            "local_date": payload.get("local_date") or "", "effective_at_utc": payload.get("effective_at_utc") or "",
            "quantity_decimal": decimal(payload, "quantity_decimal"), "eligible_quantity_decimal": decimal(payload, "eligible_quantity_decimal"),
            "unit_price_decimal": decimal(payload, "unit_price_decimal"), "gross_amount_decimal": decimal(payload, "gross_amount_decimal"),
            "monetary_fee_decimal": decimal(payload, "monetary_fee_decimal"), "asset_fee_quantity_decimal": decimal(payload, "asset_fee_quantity_decimal"),
            "provided_basis_decimal": decimal(payload, "provided_basis_decimal"),
            "basis_currency": payload.get("basis_currency") or payload.get("price_currency") or payload.get("provider_currency") or "",
            "payload_json": _canonical(_localize(payload)).decode("utf-8"),
            "record_fingerprint": record["record_fingerprint"],
        })
    return stream.getvalue().encode("utf-8")


def _cutoff(records: list[dict[str, Any]]) -> str:
    values = []
    for row in records:
        for key, value in row["payload"].items():
            if key.endswith("_at_utc") and isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
                values.append(value)
    return max(values) if values else "1970-01-01T00:00:00Z"


def preview_portfolio_csv_export_v1(canonical_path: str | Path, data_space_path: str | Path,
                                    context_value: PortfolioCsvContextV1 | Mapping[str, Any]) -> PortfolioCsvExportPlanV1:
    context = _context(context_value); data_space = _owner_directory(data_space_path)
    if data_space.name != context.data_space_id:
        _abort("portfolio_csv_context_invalid")
    records, snapshots, canonical_version, activity_version, activity_fp, cash_version, cash_dimension = _read_current_records(
        Path(canonical_path), data_space, context
    )
    asset_refs = sorted(row["record_ref"] for row in records if row["record_kind"] == "asset")
    account_refs = sorted(row["record_ref"] for row in records if row["record_kind"] == "account")
    payloads: list[tuple[str, bytes, int, str, str]] = []
    payloads.append(("portfolio.csv", _csv_bytes(records, "portfolio", "all"), len(records), "portfolio", "all"))
    for ref in asset_refs:
        projection = _projection(records, "asset", ref)
        payloads.append((f"assets/{ref}.csv", _csv_bytes(projection, "asset", ref), len(projection), "asset", ref))
    for ref in account_refs:
        projection = _projection(records, "account", ref)
        payloads.append((f"accounts/{ref}.csv", _csv_bytes(projection, "account", ref), len(projection), "account", ref))
    files = [{"relative_path": name, "row_count": count, "sha256": hashlib.sha256(payload).hexdigest(),
              "scope_role": role, "scope_ref": ref} for name, payload, count, role, ref in payloads]
    domain_fp = _sha([row["record_fingerprint"] for row in records])
    body = {
        "contract_version": CONTRACT_VERSION, "format": "portelyra_redundant_portfolio_csv_v1",
        "encoding": "UTF-8", "line_ending": "LF", "delimiter": ",", "decimal_mark": ",",
        "quote_mode": "RFC4180_ALL", "source_context_fingerprint": _context_fp(context),
        "canonical_schema_version": canonical_version, "activity_schema_version": activity_version,
        "cash_coverage_schema_version": cash_version, "evidence_cutoff_at_utc": _cutoff(records), "canonical_record_count": len(records),
        "asset_projection_count": len(asset_refs), "account_projection_count": len(account_refs),
        "domain_fingerprint": domain_fp, "activity_set_fingerprint": activity_fp,
        "dimensions": {"catalog": "complete_current", "provider_mapping": "complete_current",
                       "coupled_transaction": "complete_current", "asset_activity": "complete_current",
                       "cash_coverage": cash_dimension, "tax_policy": "not_included",
                       "market_history": "not_included", "audit_history": "not_included"},
        "files": files,
    }
    bundle_fp = _sha(body); manifest = {**body, "bundle_fingerprint": bundle_fp}
    return PortfolioCsvExportPlanV1(context, _context_fp(context), snapshots, tuple(records),
                                    tuple(payloads), manifest, bundle_fp)


def _rename_directory_noreplace(source: Path, destination: Path) -> None:
    """Atomically publish one directory without importing a larger Legacy worker."""

    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        _abort("portfolio_csv_write_failed")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1) == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        _abort("portfolio_csv_output_conflict")
    _abort("portfolio_csv_write_failed")


def _write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    descriptor = None
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0), mode)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None; handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.chmod(path, mode)
    except FileExistsError:
        _abort("portfolio_csv_output_conflict")
    except PortfolioCsvExchangeV1Error:
        raise
    except OSError:
        _abort("portfolio_csv_write_failed")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def execute_portfolio_csv_export_v1(plan: PortfolioCsvExportPlanV1, export_root: str | Path) -> Path:
    for snapshot in plan.snapshots:
        _revalidate(snapshot)
    root = _owner_directory(export_root); target = root / f"portfolio-export-{plan.bundle_fingerprint[:24]}"
    if target.exists():
        current = preview_portfolio_csv_import_v1(target)
        if current.bundle_fingerprint == plan.bundle_fingerprint:
            return target
        _abort("portfolio_csv_output_conflict")
    stage = Path(tempfile.mkdtemp(prefix=".portfolio-export-", dir=root)); stage.chmod(0o700)
    try:
        (stage / "assets").mkdir(mode=0o700); (stage / "accounts").mkdir(mode=0o700)
        for relative, payload, _, _, _ in plan.file_payloads:
            _write(stage.joinpath(*PurePosixPath(relative).parts), payload)
        _write(stage / "manifest.json", _canonical(plan.manifest) + b"\n")
        for directory in (stage / "assets", stage / "accounts", stage):
            descriptor = os.open(directory, os.O_RDONLY); os.fsync(descriptor); os.close(descriptor)
        _rename_directory_noreplace(stage, target)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return target


def _validate_payload_references(value: Any, key: str | None = None) -> None:
    if key in REFERENCE_KEYS and value is not None and (not isinstance(value, str) or REF.fullmatch(value) is None):
        _abort("portfolio_csv_bundle_invalid")
    if isinstance(value, dict):
        for nested_key, nested in value.items():
            _validate_payload_references(nested, nested_key)
    elif isinstance(value, list):
        for nested in value:
            _validate_payload_references(nested)


def _validate_record_shape(record: dict[str, Any]) -> None:
    if record["record_kind"] not in RECORD_KINDS:
        _abort("portfolio_csv_bundle_invalid")
    for field in ("portfolio_ref", "account_ref", "asset_ref", "event_ref"):
        value = record[field]
        if value != "" and REF.fullmatch(value) is None:
            _abort("portfolio_csv_bundle_invalid")
    _validate_payload_references(record["payload"])


def _read_csv(path: Path, role: str, scope_ref: str) -> tuple[dict[str, Any], ...]:
    if role not in {"portfolio", "asset", "account"} or (role == "portfolio" and scope_ref != "all") or (role != "portfolio" and (not isinstance(scope_ref, str) or REF.fullmatch(scope_ref) is None)):
        _abort("portfolio_csv_bundle_invalid")
    payload = _regular_file(path, "portfolio_csv_bundle_invalid").read_bytes()
    if b"\r" in payload or b"\x00" in payload:
        _abort("portfolio_csv_bundle_invalid")
    try:
        text = payload.decode("utf-8"); reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    except (UnicodeDecodeError, csv.Error) as error:
        raise PortfolioCsvExchangeV1Error("portfolio_csv_bundle_invalid") from error
    if tuple(reader.fieldnames or ()) != HEADER:
        _abort("portfolio_csv_bundle_invalid")
    records = []
    try:
        for source in reader:
            if None in source or any(value is None for value in source.values()) or source["scope_role"] != role or source["scope_ref"] != scope_ref:
                _abort("portfolio_csv_bundle_invalid")
            body = json.loads(source["payload_json"])
            payload_value = _delocalize(body)
            record = {
                "record_kind": source["record_kind"], "record_ref": source["record_ref"],
                "portfolio_ref": source["portfolio_ref"], "account_ref": source["account_ref"],
                "asset_ref": source["asset_ref"], "event_ref": source["event_ref"],
                "payload": payload_value,
            }
            expected = _sha(record); record["record_fingerprint"] = source["record_fingerprint"]
            if not REF.fullmatch(record["record_ref"]) or record["record_fingerprint"] != expected:
                _abort("portfolio_csv_bundle_invalid")
            _validate_record_shape(record); records.append(record)
    except (csv.Error, json.JSONDecodeError):
        _abort("portfolio_csv_bundle_invalid")
    if payload != _csv_bytes(records, role, scope_ref):
        _abort("portfolio_csv_bundle_invalid")
    return tuple(records)


def _preview_portfolio_csv_import_v1(
    bundle_path: str | Path, *, staged_bundle_fingerprint: str | None = None,
) -> PortfolioCsvImportPlanV1:
    bundle = _owner_directory(bundle_path)
    if (staged_bundle_fingerprint is None and BUNDLE_NAME.fullmatch(bundle.name) is None) or (
        staged_bundle_fingerprint is not None and (bundle.name != "bundle" or SHA.fullmatch(staged_bundle_fingerprint) is None)
    ):
        _abort("portfolio_csv_bundle_invalid")
    expected_children = {"manifest.json", "portfolio.csv", "assets", "accounts"}
    if {path.name for path in bundle.iterdir()} != expected_children:
        _abort("portfolio_csv_bundle_invalid")
    assets = _owner_directory(bundle / "assets"); accounts = _owner_directory(bundle / "accounts")
    manifest_path = _regular_file(bundle / "manifest.json", "portfolio_csv_bundle_invalid")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _abort("portfolio_csv_bundle_invalid")
    required = {
        "contract_version", "format", "encoding", "line_ending", "delimiter", "decimal_mark", "quote_mode",
        "source_context_fingerprint", "canonical_schema_version", "activity_schema_version", "cash_coverage_schema_version", "evidence_cutoff_at_utc",
        "canonical_record_count", "asset_projection_count", "account_projection_count", "domain_fingerprint",
        "activity_set_fingerprint", "dimensions", "files", "bundle_fingerprint",
    }
    expected_dimensions = {"catalog": "complete_current", "provider_mapping": "complete_current", "coupled_transaction": "complete_current", "asset_activity": "complete_current", "cash_coverage": manifest.get("dimensions", {}).get("cash_coverage"), "tax_policy": "not_included", "market_history": "not_included", "audit_history": "not_included"}
    if (
        not isinstance(manifest, dict) or set(manifest) != required or manifest["contract_version"] != 1
        or manifest["format"] != "portelyra_redundant_portfolio_csv_v1" or manifest["encoding"] != "UTF-8"
        or manifest["line_ending"] != "LF" or manifest["delimiter"] != "," or manifest["decimal_mark"] != ","
        or manifest["quote_mode"] != "RFC4180_ALL" or not SHA.fullmatch(manifest.get("source_context_fingerprint", ""))
        or manifest.get("canonical_schema_version") not in {201, 202} or manifest.get("activity_schema_version") not in {0, 401}
        or manifest.get("cash_coverage_schema_version") not in {0, 2901}
        or manifest.get("dimensions", {}).get("cash_coverage") not in {"absent_explicit", "complete_current"}
        or (manifest.get("cash_coverage_schema_version") == 0) != (manifest.get("dimensions", {}).get("cash_coverage") == "absent_explicit")
        or any(not isinstance(manifest.get(field), int) or isinstance(manifest.get(field), bool) or manifest[field] < 0 for field in ("canonical_record_count", "asset_projection_count", "account_projection_count"))
        or manifest.get("canonical_record_count", 0) < 1 or manifest.get("dimensions") != expected_dimensions
        or not SHA.fullmatch(manifest.get("domain_fingerprint", "")) or not SHA.fullmatch(manifest.get("activity_set_fingerprint", ""))
    ):
        _abort("portfolio_csv_bundle_invalid")
    body = {key: value for key, value in manifest.items() if key != "bundle_fingerprint"}
    if manifest["bundle_fingerprint"] != _sha(body) or (
        staged_bundle_fingerprint is None and bundle.name != f"portfolio-export-{manifest['bundle_fingerprint'][:24]}"
    ) or (staged_bundle_fingerprint is not None and manifest["bundle_fingerprint"] != staged_bundle_fingerprint):
        _abort("portfolio_csv_bundle_invalid")
    try:
        if datetime.strptime(manifest["evidence_cutoff_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") != manifest["evidence_cutoff_at_utc"]:
            _abort("portfolio_csv_bundle_invalid")
    except (KeyError, TypeError, ValueError):
        _abort("portfolio_csv_bundle_invalid")
    files = manifest["files"]
    if not isinstance(files, list) or not files or len(files) != len({entry.get("relative_path") for entry in files if isinstance(entry, dict)}):
        _abort("portfolio_csv_bundle_invalid")
    snapshots = [_snapshot(manifest_path)]; parsed: dict[str, tuple[dict[str, Any], ...]] = {}
    for entry in files:
        if not isinstance(entry, dict) or set(entry) != {"relative_path", "row_count", "sha256", "scope_role", "scope_ref"}:
            _abort("portfolio_csv_bundle_invalid")
        relative = entry["relative_path"]
        parts = PurePosixPath(relative).parts if isinstance(relative, str) else ()
        if not parts or any(part in {"", ".", ".."} for part in parts):
            _abort("portfolio_csv_bundle_invalid")
        if (entry["scope_role"] == "portfolio" and relative != "portfolio.csv") or (entry["scope_role"] == "asset" and relative != f"assets/{entry['scope_ref']}.csv") or (entry["scope_role"] == "account" and relative != f"accounts/{entry['scope_ref']}.csv"):
            _abort("portfolio_csv_bundle_invalid")
        path = _regular_file(bundle.joinpath(*parts), "portfolio_csv_bundle_invalid"); snapshot = _snapshot(path); snapshots.append(snapshot)
        if snapshot.fingerprint != entry["sha256"]:
            _abort("portfolio_csv_bundle_invalid")
        rows = _read_csv(path, entry["scope_role"], entry["scope_ref"]); parsed[relative] = rows
        if len(rows) != entry["row_count"]:
            _abort("portfolio_csv_bundle_invalid")
    actual_files = {"portfolio.csv", *[f"assets/{p.name}" for p in assets.iterdir()], *[f"accounts/{p.name}" for p in accounts.iterdir()]}
    if actual_files != set(parsed) or "portfolio.csv" not in parsed:
        _abort("portfolio_csv_bundle_invalid")
    records = list(parsed["portfolio.csv"])
    if (
        len(records) != manifest["canonical_record_count"] or len(records) != len({row["record_ref"] for row in records})
        or records != sorted(records, key=lambda row: (row["record_kind"], row["record_ref"]))
        or _sha([row["record_fingerprint"] for row in records]) != manifest["domain_fingerprint"]
    ):
        _abort("portfolio_csv_bundle_invalid")
    asset_refs = sorted(row["record_ref"] for row in records if row["record_kind"] == "asset")
    account_refs = sorted(row["record_ref"] for row in records if row["record_kind"] == "account")
    if len(asset_refs) != manifest["asset_projection_count"] or len(account_refs) != manifest["account_projection_count"]:
        _abort("portfolio_csv_redundancy_invalid")
    for role, refs in (("asset", asset_refs), ("account", account_refs)):
        directory = "assets" if role == "asset" else "accounts"
        for ref in refs:
            relative = f"{directory}/{ref}.csv"; expected = _projection(records, role, ref)
            if relative not in parsed or [row["record_fingerprint"] for row in parsed[relative]] != [row["record_fingerprint"] for row in expected]:
                _abort("portfolio_csv_redundancy_invalid")
    return PortfolioCsvImportPlanV1(bundle, tuple(snapshots), tuple(records), manifest, manifest["bundle_fingerprint"])


def preview_portfolio_csv_import_v1(bundle_path: str | Path) -> PortfolioCsvImportPlanV1:
    return _preview_portfolio_csv_import_v1(bundle_path)


def execute_portfolio_csv_import_v1(plan: PortfolioCsvImportPlanV1, imports_root: str | Path,
                                    target_context_value: PortfolioCsvContextV1 | Mapping[str, Any]) -> Path:
    context = _context(target_context_value)
    for snapshot in plan.snapshots:
        _revalidate(snapshot)
    root = _owner_directory(imports_root); target = root / f"imp_{plan.bundle_fingerprint[:24]}"
    if target.exists():
        receipt = _regular_file(target / "import-receipt.json", "portfolio_csv_bundle_invalid")
        try:
            value = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _abort("portfolio_csv_bundle_invalid")
        if value.get("bundle_fingerprint") == plan.bundle_fingerprint and value.get("status") == "staged_lossless_ready_for_domain_handoffs":
            return target
        _abort("portfolio_csv_output_conflict")
    stage = Path(tempfile.mkdtemp(prefix=".portfolio-import-", dir=root)); stage.chmod(0o700)
    try:
        copied = stage / "bundle"; copied.mkdir(mode=0o700)
        for source in plan.snapshots:
            relative = source.path.relative_to(plan.bundle_path)
            destination = copied.joinpath(*relative.parts); destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            _write(destination, source.path.read_bytes())
        receipt = {
            "contract_version": 1, "status": "staged_lossless_ready_for_domain_handoffs",
            "bundle_fingerprint": plan.bundle_fingerprint, "domain_fingerprint": plan.manifest["domain_fingerprint"],
            "target_context_fingerprint": _context_fp(context), "record_count": len(plan.records),
            "catalog_apply": "separate_confirmation_required", "coupled_transaction_apply": "separate_confirmation_required",
            "asset_activity_apply": "separate_per_draft_confirmation_required",
            "cash_coverage_apply": "separate_reviewed_candidate_confirmation_required", "product_write": False,
            "provider_access": False, "network_access": False, "automatic_retry": False,
        }
        _write(stage / "import-receipt.json", _canonical(receipt) + b"\n"); _write(stage / "SUCCESS", b"completed\n")
        descriptor = os.open(stage, os.O_RDONLY); os.fsync(descriptor); os.close(descriptor)
        _rename_directory_noreplace(stage, target)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return target


def list_portfolio_csv_import_bundles_v1(import_inbox: str | Path) -> tuple[dict[str, Any], ...]:
    root = _owner_directory(import_inbox); rows = []
    for path in sorted(root.iterdir(), key=lambda value: value.name):
        if path.is_symlink() or not path.is_dir() or BUNDLE_NAME.fullmatch(path.name) is None:
            _abort("portfolio_csv_bundle_invalid")
        plan = preview_portfolio_csv_import_v1(path)
        rows.append({"bundle_handle": "pcb_" + plan.bundle_fingerprint[:24], "bundle_name": path.name,
                     "bundle_fingerprint": plan.bundle_fingerprint, "record_count": len(plan.records),
                     "asset_count": plan.manifest["asset_projection_count"],
                     "account_count": plan.manifest["account_projection_count"]})
    return tuple(rows)


__all__ = [
    "PortfolioCsvContextV1", "PortfolioCsvExchangeV1Error", "PortfolioCsvExportPlanV1",
    "PortfolioCsvImportPlanV1", "execute_portfolio_csv_export_v1", "execute_portfolio_csv_import_v1",
    "list_portfolio_csv_import_bundles_v1", "portfolio_csv_exchange_paths_v1",
    "preview_portfolio_csv_export_v1", "preview_portfolio_csv_import_v1",
]
