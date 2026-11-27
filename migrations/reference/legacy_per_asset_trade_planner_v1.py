"""Read-only per-Asset Legacy Trade CSV planning with exact reconciliation.

The source parser is intentionally independent of the old portfolio-wide converter.
It accepts one explicit CSV, proves one exact Legacy Asset_ID, exposes private values
only in the returned local review object and never writes. A second fingerprint-bound
review maps source Account labels to already selected opaque Accounts and supplies
only evidence that the source cannot prove. Full FIFO is run only when every row is
ready, so unresolved rows can never produce a misleading partial reconciliation.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import copy
import csv
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation, localcontext
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from migrations.reference.asset_activity_v1 import AssetActivityV1Error, validate_asset_activity_v1

CONTRACT_VERSION = 1
MAX_SOURCE_BYTES = 10_000_000
REQUIRED_HEADERS = (
    "Asset_ID",
    "Depot",
    "Datum",
    "Uhrzeit",
    "Typ",
    "Stückzahl",
    "Stückpreis",
    "Ordergebühr",
    "Kommentar",
)
SUPPORTED_TARGET_TYPES = frozenset({"buy", "sell", "dividend", "reward", "deposit", "withdrawal", "transfer"})
SUPPORTED_ASSET_TYPES = frozenset({"equity", "etf", "fund", "bond", "crypto", "commodity", "fx", "index", "other"})
SUPPORTED_ACCOUNT_TYPES = frozenset({"securities", "crypto_wallet", "other"})
MOVEMENT_CONTEXT_CODES = frozenset({"unclassified", "gift", "inheritance", "debt_settlement", "donation", "payment", "custody_exit", "other"})
BASIS_MODES = frozenset({"valuation_confirmed_as_basis", "provided_basis", "basis_missing"})
BASIS_AMOUNT_MODES = frozenset({"source_quantity_unit_price", "manual_total", "not_applicable"})
FEE_TREATMENTS = frozenset({"principal_asset_quantity", "monetary_basis_currency", "separate_event_required"})
MEMO_ACTIONS = frozenset({"accept_source", "skip"})
DUPLICATE_ACTIONS = frozenset({"keep_confirmed"})
DIVIDEND_INPUT_MODES = frozenset({"quantity_unit_price", "gross_total"})
TIME_EVIDENCE_MODES = frozenset({"date_only", "exact"})

FAILURE_CODES = frozenset(
    {
        "legacy_per_asset_trade_asset_id_invalid",
        "legacy_per_asset_trade_asset_id_multiple",
        "legacy_per_asset_trade_boundary_failed",
        "legacy_per_asset_trade_companion_invalid",
        "legacy_per_asset_trade_input_invalid",
        "legacy_per_asset_trade_review_invalid",
        "legacy_per_asset_trade_review_stale",
        "legacy_per_asset_trade_source_changed",
        "legacy_per_asset_trade_source_csv_invalid",
        "legacy_per_asset_trade_source_encoding_invalid",
        "legacy_per_asset_trade_source_file_invalid",
        "legacy_per_asset_trade_source_header_invalid",
        "legacy_per_asset_trade_target_invalid",
    }
)
DECISION_CODES = frozenset(
    {
        "deposit_basis_evidence_required",
        "deposit_original_acquisition_required",
        "dividend_input_mode_required",
        "fee_treatment_required",
        "fifo_same_day_order_required",
        "fx_conversion_evidence_required",
        "memo_action_required",
        "movement_context_required",
        "possible_duplicate_review_required",
        "primary_account_binding_required",
        "related_account_binding_required",
        "reward_basis_evidence_required",
        "stock_dividend_v2_evidence_required",
        "target_review_required",
    }
)
BLOCKER_CODES = frozenset(
    {
        "activity_semantics_invalid",
        "fee_separate_event_required",
        "fifo_inventory_insufficient",
        "interest_outside_noncash_import",
        "source_account_invalid",
        "source_amount_invalid",
        "source_date_invalid",
        "source_decimal_invalid",
        "source_sign_invalid",
        "source_time_ambiguous",
        "source_time_invalid",
        "source_time_nonexistent",
        "source_type_unsupported",
        "transfer_expression_invalid",
    }
)

_REF = re.compile(r"[a-z]{2,8}_[a-f0-9]{16,64}")
_FINGERPRINT = re.compile(r"[a-f0-9]{64}")
_CURRENCY = re.compile(r"[A-Z]{3}")
_LOCAL_TIME = re.compile(r"[0-9]{2}:[0-9]{2}:[0-9]{2}")
_SOURCE_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:[.,][0-9]+)?|[0-9]+)(?:[eE][+-]?[0-9]+)?")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_TRANSFER_ARROW = re.compile(r"(?:→|->)")


class LegacyPerAssetTradePlannerV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("legacy_per_asset_trade_error_code_unregistered")
        self.code = code
        super().__init__(code)


def legacy_per_asset_trade_planner_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def legacy_per_asset_trade_planner_v1_decision_codes() -> tuple[str, ...]:
    return tuple(sorted(DECISION_CODES))


def legacy_per_asset_trade_planner_v1_blocker_codes() -> tuple[str, ...]:
    return tuple(sorted(BLOCKER_CODES))


def _abort(code: str) -> None:
    raise LegacyPerAssetTradePlannerV1Error(code)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _exact_keys(value: Any, expected: set[str], code: str = "legacy_per_asset_trade_input_invalid") -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        _abort(code)
    return value


def _clean_text(value: Any, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError
    result = unicodedata.normalize("NFC", value).strip()
    if (not result and not allow_empty) or len(result) > maximum or _CONTROL.search(result):
        raise ValueError
    return result


def _ref(value: Any) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        _abort("legacy_per_asset_trade_target_invalid")
    return value


def _decimal_from_source(value: Any, *, optional: bool) -> tuple[str | None, str | None]:
    if not isinstance(value, str):
        return None, "source_decimal_invalid"
    source = unicodedata.normalize("NFC", value).strip()
    if source == "" and optional:
        return None, None
    if not source or len(source) > 80 or _SOURCE_DECIMAL.fullmatch(source) is None:
        return None, "source_decimal_invalid"
    try:
        number = Decimal(source.replace(",", "."))
    except InvalidOperation:
        return None, "source_decimal_invalid"
    if not number.is_finite():
        return None, "source_decimal_invalid"
    if number < 0:
        return None, "source_sign_invalid"
    if number == 0:
        return "0", None
    rendered = format(number, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if not rendered or len(rendered) > 80:
        return None, "source_decimal_invalid"
    return rendered, None


def _review_decimal(value: Any, *, nullable: bool = True, positive: bool = True) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > 80 or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?", value) is None:
        _abort("legacy_per_asset_trade_review_invalid")
    try:
        number = Decimal(value)
    except InvalidOperation:
        _abort("legacy_per_asset_trade_review_invalid")
    if not number.is_finite() or (positive and number <= 0):
        _abort("legacy_per_asset_trade_review_invalid")
    return value


def _fraction(value: str) -> Fraction:
    return Fraction(Decimal(value))


def _terminating_decimal(value: Fraction) -> str | None:
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    if denominator != 1:
        return None
    precision = max(len(str(abs(value.numerator))), len(str(value.denominator))) + 30
    with localcontext() as context:
        context.prec = precision
        result = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return "0" if result in {"", "-0"} else result


def _exact_number(value: Fraction) -> dict[str, str | None]:
    decimal_value = _terminating_decimal(value)
    return {
        "exact_number_status": "exact_decimal" if decimal_value is not None else "exact_ratio",
        "decimal": decimal_value,
        "numerator_integer": str(value.numerator),
        "denominator_integer": str(value.denominator),
    }


def _parse_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = unicodedata.normalize("NFC", value).strip()
    try:
        parsed = date.fromisoformat(normalized)
    except ValueError:
        return None
    return normalized if parsed.isoformat() == normalized else None


def _parse_time(value: Any) -> tuple[str | None, str, str | None]:
    if not isinstance(value, str):
        return None, "date_only", "source_time_invalid"
    normalized = unicodedata.normalize("NFC", value).strip()
    if not normalized:
        return None, "date_only", None
    if _LOCAL_TIME.fullmatch(normalized) is None:
        return None, "exact", "source_time_invalid"
    try:
        parsed = time.fromisoformat(normalized)
    except ValueError:
        return None, "exact", "source_time_invalid"
    if parsed.strftime("%H:%M:%S") != normalized:
        return None, "exact", "source_time_invalid"
    return normalized, "exact", None


def _unique_utc(local_date: str, local_time: str, zone_name: str) -> tuple[str | None, str | None]:
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        _abort("legacy_per_asset_trade_target_invalid")
    naive = datetime.strptime(f"{local_date}T{local_time}", "%Y-%m-%dT%H:%M:%S")
    candidates: set[datetime] = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        candidate = aware.astimezone(timezone.utc)
        if candidate.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(candidate)
    if not candidates:
        return None, "source_time_nonexistent"
    if len(candidates) != 1:
        return None, "source_time_ambiguous"
    return next(iter(candidates)).strftime("%Y-%m-%dT%H:%M:%SZ"), None


def _decode_source(source_bytes: bytes) -> str:
    if not isinstance(source_bytes, bytes) or not source_bytes or len(source_bytes) > MAX_SOURCE_BYTES:
        _abort("legacy_per_asset_trade_source_file_invalid")
    try:
        text = source_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        _abort("legacy_per_asset_trade_source_encoding_invalid")
    if "\x00" in text:
        _abort("legacy_per_asset_trade_source_encoding_invalid")
    return text


def _parse_csv(source_bytes: bytes) -> tuple[list[str], list[list[str]]]:
    text = _decode_source(source_bytes)
    candidates: list[tuple[list[str], list[list[str]]]] = []
    for delimiter in (";", ","):
        try:
            records = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
        except csv.Error:
            continue
        if not records:
            continue
        headers = [unicodedata.normalize("NFC", item).strip() for item in records[0]]
        if not headers or any(not item for item in headers) or len(headers) != len(set(headers)):
            continue
        if all(field in headers for field in REQUIRED_HEADERS):
            candidates.append((headers, records[1:]))
    if len(candidates) != 1:
        _abort("legacy_per_asset_trade_source_header_invalid")
    headers, rows = candidates[0]
    if not rows:
        _abort("legacy_per_asset_trade_source_csv_invalid")
    if any(len(row) != len(headers) or not any(cell != "" for cell in row) for row in rows):
        _abort("legacy_per_asset_trade_source_csv_invalid")
    return headers, rows


def _event_type(value: Any) -> str | None:
    try:
        normalized = _clean_text(value, maximum=80).casefold().replace("-", "_").replace(" ", "_")
    except ValueError:
        return None
    mapping = {
        "buy": "buy",
        "kauf": "buy",
        "sell": "sell",
        "verkauf": "sell",
        "dividend": "dividend",
        "dividende": "dividend",
        "reward": "reward",
        "deposit": "deposit",
        "einlieferung": "deposit",
        "withdrawal": "withdrawal",
        "auslieferung": "withdrawal",
        "transfer": "transfer_expression",
        "stock_dividend": "stock_dividend",
        "aktiendividende": "stock_dividend",
        "interest": "interest",
        "zins": "interest",
        "zinsen": "interest",
    }
    return mapping.get(normalized)


def _account_label(value: Any) -> str | None:
    try:
        result = _clean_text(value, maximum=120)
    except ValueError:
        return None
    return None if result.casefold() == "ext" else result


def _parse_transfer(value: Any) -> tuple[str | None, str | None, str | None, str | None]:
    try:
        normalized = _clean_text(value, maximum=300)
    except ValueError:
        return None, None, None, "transfer_expression_invalid"
    if normalized.count(":") != 1:
        return None, None, None, "transfer_expression_invalid"
    prefix, expression = normalized.split(":", 1)
    endpoints = _TRANSFER_ARROW.split(expression)
    arrows = _TRANSFER_ARROW.findall(expression)
    if len(endpoints) != 2 or len(arrows) != 1:
        return None, None, None, "transfer_expression_invalid"
    source_raw, destination_raw = (item.strip() for item in endpoints)
    source_external = source_raw.casefold() == "ext"
    destination_external = destination_raw.casefold() == "ext"
    prefix_value = prefix.strip().upper()
    source = _account_label(source_raw)
    destination = _account_label(destination_raw)
    if prefix_value.endswith("_WECHSEL") and not source_external and not destination_external and source and destination and source != destination:
        return "transfer", source, destination, None
    if prefix_value.endswith("_ABFLUSS") and source and destination_external:
        return "withdrawal", source, None, None
    if prefix_value.endswith("_ZUFLUSS") and source_external and destination:
        return "deposit", destination, None, None
    return None, None, None, "transfer_expression_invalid"


def _account_fingerprint(label: str) -> str:
    return _sha(label.encode("utf-8"))


def _row_ref(file_fingerprint: str, ordinal: int) -> str:
    return "row_" + hashlib.sha256(f"{file_fingerprint}:{ordinal}".encode("ascii")).hexdigest()[:32]


def _projection_impl(source_bytes: bytes) -> dict[str, Any]:
    headers, records = _parse_csv(source_bytes)
    source_file_fingerprint = _sha(source_bytes)
    header_index = {name: index for index, name in enumerate(headers)}
    source_asset_ids: set[str] = set()
    for cells in records:
        try:
            source_asset_ids.add(_clean_text(cells[header_index["Asset_ID"]], maximum=200))
        except ValueError:
            _abort("legacy_per_asset_trade_asset_id_invalid")
    if len(source_asset_ids) != 1:
        _abort("legacy_per_asset_trade_asset_id_multiple")
    source_asset_id = next(iter(source_asset_ids))
    rows: list[dict[str, Any]] = []
    account_labels: dict[str, str] = {}
    content_groups: defaultdict[str, list[str]] = defaultdict(list)
    for ordinal, cells in enumerate(records, start=1):
        values = dict(zip(headers, cells, strict=True))
        source_row_ref = _row_ref(source_file_fingerprint, ordinal)
        source_row_fingerprint = _fingerprint({"cells": cells, "file": source_file_fingerprint, "ordinal": ordinal})
        blockers: set[str] = set()
        decisions: set[str] = {"target_review_required"}
        normalized_type = _event_type(values["Typ"])
        primary_label: str | None = None
        related_label: str | None = None
        if normalized_type == "transfer_expression":
            normalized_type, primary_label, related_label, transfer_error = _parse_transfer(values["Depot"])
            if transfer_error:
                blockers.add(transfer_error)
        elif normalized_type in {"buy", "sell", "dividend", "reward", "deposit", "withdrawal", "stock_dividend"}:
            depot_value = values["Depot"]
            if _TRANSFER_ARROW.search(depot_value):
                normalized_type, primary_label, related_label, transfer_error = _parse_transfer(depot_value)
                if transfer_error:
                    blockers.add(transfer_error)
            else:
                primary_label = _account_label(depot_value)
                if primary_label is None:
                    blockers.add("source_account_invalid")
        elif normalized_type == "interest":
            blockers.add("interest_outside_noncash_import")
        else:
            blockers.add("source_type_unsupported")
        if primary_label is not None:
            account_labels[_account_fingerprint(primary_label)] = primary_label
        if related_label is not None:
            account_labels[_account_fingerprint(related_label)] = related_label
        local_date = _parse_date(values["Datum"])
        if local_date is None:
            blockers.add("source_date_invalid")
        local_time, time_evidence, time_error = _parse_time(values["Uhrzeit"])
        if time_error:
            blockers.add(time_error)
        quantity, quantity_error = _decimal_from_source(values["Stückzahl"], optional=True)
        unit_price, unit_price_error = _decimal_from_source(values["Stückpreis"], optional=True)
        fee, fee_error = _decimal_from_source(values["Ordergebühr"], optional=True)
        for error in (quantity_error, unit_price_error, fee_error):
            if error:
                blockers.add(error)
        if fee == "0":
            fee = None
        if normalized_type in {"buy", "sell", "dividend", "reward"}:
            if quantity in {None, "0"} or unit_price in {None, "0"}:
                blockers.add("source_amount_invalid")
        elif normalized_type in {"deposit", "withdrawal", "transfer"}:
            if quantity in {None, "0"}:
                blockers.add("source_amount_invalid")
        memo_source: str | None
        try:
            memo_source = _clean_text(values["Kommentar"], maximum=4000, allow_empty=True) or None
        except ValueError:
            memo_source = None
            blockers.add("source_amount_invalid")
        if normalized_type == "stock_dividend" and not blockers:
            decisions.add("stock_dividend_v2_evidence_required")
        if memo_source is not None:
            decisions.add("memo_action_required")
        if fee is not None and normalized_type not in {"buy", "sell"}:
            decisions.add("fee_treatment_required")
        if normalized_type == "reward":
            decisions.add("reward_basis_evidence_required")
        if normalized_type == "deposit":
            decisions.update({"deposit_basis_evidence_required", "deposit_original_acquisition_required", "movement_context_required"})
        if normalized_type == "withdrawal":
            decisions.add("movement_context_required")
        primary_fp = None if primary_label is None else _account_fingerprint(primary_label)
        related_fp = None if related_label is None else _account_fingerprint(related_label)
        duplicate_fingerprint = _fingerprint(
            {
                "account": primary_fp,
                "date": local_date,
                "fee": fee,
                "memo": memo_source,
                "quantity": quantity,
                "related": related_fp,
                "time": local_time,
                "type": normalized_type,
                "unit_price": unit_price,
            }
        )
        content_groups[duplicate_fingerprint].append(source_row_ref)
        disposition = "blocked" if blockers else "decision_required"
        rows.append(
            {
                "source_row_ref": source_row_ref,
                "source_row_ordinal": ordinal,
                "source_row_fingerprint": source_row_fingerprint,
                "duplicate_candidate_fingerprint": duplicate_fingerprint,
                "normalized_event_type": normalized_type,
                "local_date": local_date,
                "local_time": local_time,
                "event_time_evidence": time_evidence,
                "quantity_decimal": quantity,
                "unit_price_decimal": unit_price,
                "source_fee_decimal": fee,
                "source_primary_account_fingerprint": primary_fp,
                "source_related_account_fingerprint": related_fp,
                "source_memo": memo_source,
                "initial_disposition": disposition,
                "decision_codes": sorted(decisions) if not blockers else [],
                "blocker_codes": sorted(blockers),
                "local_review_only": True,
            }
        )
    duplicate_refs = {row_ref for refs in content_groups.values() if len(refs) > 1 for row_ref in refs}
    for row in rows:
        if row["source_row_ref"] in duplicate_refs and row["initial_disposition"] != "blocked":
            row["decision_codes"] = sorted(set(row["decision_codes"]) | {"possible_duplicate_review_required"})
    result = {
        "per_asset_trade_projection_version": CONTRACT_VERSION,
        "projection_status": "blocked" if any(row["initial_disposition"] == "blocked" for row in rows) else "review_required",
        "source_file_fingerprint": source_file_fingerprint,
        "source_header_fingerprint": _fingerprint(headers),
        "source_asset_link_fingerprint": _sha(source_asset_id.encode("utf-8")),
        "source_row_count": len(rows),
        "excluded_source_field_count": len(set(headers) - set(REQUIRED_HEADERS)),
        "source_account_candidates": [
            {
                "source_account_fingerprint": fingerprint,
                "source_account_label": label,
                "local_review_only": True,
                "canonical_identity_authority": False,
            }
            for fingerprint, label in sorted(account_labels.items())
        ],
        "rows": rows,
        "source_row_disposition_complete": len(rows) == len(records),
        "raw_source_asset_id_exposed": False,
        "filename_identity_used": False,
        "account_identity_inferred": False,
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "private_output_logged": False,
    }
    result["projection_fingerprint"] = _fingerprint(result)
    return result


def project_legacy_per_asset_trade_bytes_v1(source_bytes: bytes) -> dict[str, Any]:
    try:
        return _projection_impl(source_bytes)
    except LegacyPerAssetTradePlannerV1Error:
        raise
    except Exception:
        raise LegacyPerAssetTradePlannerV1Error("legacy_per_asset_trade_boundary_failed") from None


def _path_without_symlink(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if current.is_symlink():
                return False
        except OSError:
            return False
    return True


def _read_regular_file(path_value: Any) -> bytes:
    if not isinstance(path_value, (str, os.PathLike)):
        _abort("legacy_per_asset_trade_source_file_invalid")
    path = Path(path_value)
    if not path.is_absolute() or not _path_without_symlink(path):
        _abort("legacy_per_asset_trade_source_file_invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _abort("legacy_per_asset_trade_source_file_invalid")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > MAX_SOURCE_BYTES:
            _abort("legacy_per_asset_trade_source_file_invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                _abort("legacy_per_asset_trade_source_changed")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _abort("legacy_per_asset_trade_source_changed")
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            _abort("legacy_per_asset_trade_source_changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_legacy_per_asset_trade_v1(source_path: Any) -> dict[str, Any]:
    try:
        return _projection_impl(_read_regular_file(source_path))
    except LegacyPerAssetTradePlannerV1Error:
        raise
    except Exception:
        raise LegacyPerAssetTradePlannerV1Error("legacy_per_asset_trade_boundary_failed") from None


_ROW_REVIEW_KEYS = {
    "source_row_ref",
    "basis_evidence_mode",
    "basis_amount_mode",
    "provided_basis_decimal",
    "original_acquired_time_evidence",
    "original_acquired_local_date",
    "original_acquired_local_time",
    "original_acquired_time_zone",
    "original_acquired_at_utc",
    "movement_context_code",
    "fee_treatment",
    "memo_action",
    "duplicate_action",
    "dividend_input_mode",
    "dividend_gross_total_decimal",
    "same_day_fifo_sequence",
}


def _empty_row_review(source_row_ref: str) -> dict[str, Any]:
    return {key: (source_row_ref if key == "source_row_ref" else None) for key in _ROW_REVIEW_KEYS}


def _review_rows(value: Any, source_refs: set[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        _abort("legacy_per_asset_trade_review_invalid")
    result: dict[str, dict[str, Any]] = {}
    for item in value:
        row = _exact_keys(item, _ROW_REVIEW_KEYS, "legacy_per_asset_trade_review_invalid")
        source_ref = row["source_row_ref"]
        if source_ref not in source_refs or source_ref in result:
            _abort("legacy_per_asset_trade_review_invalid")
        if row["basis_evidence_mode"] is not None and row["basis_evidence_mode"] not in BASIS_MODES:
            _abort("legacy_per_asset_trade_review_invalid")
        if row["basis_amount_mode"] is not None and row["basis_amount_mode"] not in BASIS_AMOUNT_MODES:
            _abort("legacy_per_asset_trade_review_invalid")
        _review_decimal(row["provided_basis_decimal"])
        if row["original_acquired_time_evidence"] is not None and row["original_acquired_time_evidence"] not in TIME_EVIDENCE_MODES:
            _abort("legacy_per_asset_trade_review_invalid")
        if row["movement_context_code"] is not None and row["movement_context_code"] not in MOVEMENT_CONTEXT_CODES:
            _abort("legacy_per_asset_trade_review_invalid")
        if row["fee_treatment"] is not None and row["fee_treatment"] not in FEE_TREATMENTS:
            _abort("legacy_per_asset_trade_review_invalid")
        if row["memo_action"] is not None and row["memo_action"] not in MEMO_ACTIONS:
            _abort("legacy_per_asset_trade_review_invalid")
        if row["duplicate_action"] is not None and row["duplicate_action"] not in DUPLICATE_ACTIONS:
            _abort("legacy_per_asset_trade_review_invalid")
        if row["dividend_input_mode"] is not None and row["dividend_input_mode"] not in DIVIDEND_INPUT_MODES:
            _abort("legacy_per_asset_trade_review_invalid")
        _review_decimal(row["dividend_gross_total_decimal"])
        sequence = row["same_day_fifo_sequence"]
        if sequence is not None and (isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1):
            _abort("legacy_per_asset_trade_review_invalid")
        result[source_ref] = row
    return result


def _validate_companion(companion: Any, source_link: str, asset_type: str, quantity_scale: int) -> tuple[bool, str | None]:
    if companion is None:
        return False, None
    expected_keys = {
        "asset_companion_version", "review_status", "projection_fingerprint", "source_asset_link_fingerprint",
        "source_row_fingerprint", "display_name", "asset_type", "quantity_scale", "isin", "wkn", "note",
        "asset_type_inferred", "quantity_scale_inferred", "provider_listing_value_imported", "tax_value_imported",
        "account_binding_imported", "grouping_allocation_imported", "canonical_write", "private_output_logged", "review_fingerprint",
    }
    if not isinstance(companion, dict) or set(companion) != expected_keys:
        _abort("legacy_per_asset_trade_companion_invalid")
    body = dict(companion)
    fingerprint = body.pop("review_fingerprint")
    if (
        fingerprint != _fingerprint(body)
        or companion["asset_companion_version"] != 1
        or companion["review_status"] != "reviewed_candidate"
        or companion["source_asset_link_fingerprint"] != source_link
        or companion["asset_type"] != asset_type
        or companion["quantity_scale"] != quantity_scale
        or any(
            companion[key] is not False
            for key in (
                "asset_type_inferred", "quantity_scale_inferred", "provider_listing_value_imported",
                "tax_value_imported", "account_binding_imported", "grouping_allocation_imported",
                "canonical_write", "private_output_logged",
            )
        )
    ):
        _abort("legacy_per_asset_trade_companion_invalid")
    return True, fingerprint


def _activity_catalog(review: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, Any]]:
    target = _exact_keys(review["target_asset"], {"asset_ref", "asset_type", "quantity_scale", "target_review_confirmed"}, "legacy_per_asset_trade_target_invalid")
    asset_ref = _ref(target["asset_ref"])
    asset_type = target["asset_type"]
    scale = target["quantity_scale"]
    if (
        asset_type not in SUPPORTED_ASSET_TYPES
        or isinstance(scale, bool)
        or not isinstance(scale, int)
        or not 0 <= scale <= 24
        or target["target_review_confirmed"] is not True
    ):
        _abort("legacy_per_asset_trade_target_invalid")
    accounts_value = review["accounts"]
    if not isinstance(accounts_value, list) or not accounts_value:
        _abort("legacy_per_asset_trade_target_invalid")
    accounts: dict[str, dict[str, Any]] = {}
    for item in accounts_value:
        row = _exact_keys(item, {"account_ref", "account_type"}, "legacy_per_asset_trade_target_invalid")
        account_ref = _ref(row["account_ref"])
        if row["account_type"] not in SUPPORTED_ACCOUNT_TYPES or account_ref in accounts:
            _abort("legacy_per_asset_trade_target_invalid")
        if asset_type == "crypto" and row["account_type"] not in {"crypto_wallet", "securities", "other"}:
            _abort("legacy_per_asset_trade_target_invalid")
        if asset_type != "crypto" and row["account_type"] not in {"securities", "other"}:
            _abort("legacy_per_asset_trade_target_invalid")
        accounts[account_ref] = row
    bindings_value = review["account_bindings"]
    if not isinstance(bindings_value, list):
        _abort("legacy_per_asset_trade_review_invalid")
    bindings: dict[str, str] = {}
    for item in bindings_value:
        row = _exact_keys(item, {"source_account_fingerprint", "account_ref"}, "legacy_per_asset_trade_review_invalid")
        source_fp = row["source_account_fingerprint"]
        account_ref = _ref(row["account_ref"])
        if not isinstance(source_fp, str) or _FINGERPRINT.fullmatch(source_fp) is None or source_fp in bindings or account_ref not in accounts:
            _abort("legacy_per_asset_trade_review_invalid")
        bindings[source_fp] = account_ref
    return accounts, bindings, {"asset_ref": asset_ref, "asset_type": asset_type, "quantity_scale": scale}


def _original_acquisition(review: dict[str, Any]) -> tuple[str, str | None, str | None, str | None, str | None, set[str]]:
    decisions: set[str] = set()
    mode = review["original_acquired_time_evidence"]
    if mode is None:
        decisions.add("deposit_original_acquisition_required")
        return "not_applicable", None, None, None, None, decisions
    local_date = review["original_acquired_local_date"]
    local_time = review["original_acquired_local_time"]
    zone = review["original_acquired_time_zone"]
    utc = review["original_acquired_at_utc"]
    if _parse_date(local_date) is None or not isinstance(zone, str):
        _abort("legacy_per_asset_trade_review_invalid")
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        _abort("legacy_per_asset_trade_review_invalid")
    if mode == "date_only":
        if local_time is not None or utc is not None:
            _abort("legacy_per_asset_trade_review_invalid")
    else:
        parsed_time, evidence, error = _parse_time(local_time)
        if error or evidence != "exact" or parsed_time is None:
            _abort("legacy_per_asset_trade_review_invalid")
        expected, utc_error = _unique_utc(local_date, parsed_time, zone)
        if utc_error or utc != expected:
            _abort("legacy_per_asset_trade_review_invalid")
    return mode, local_date, local_time, zone, utc, decisions


def _build_activity_event(
    source: dict[str, Any],
    row_review: dict[str, Any],
    target: dict[str, Any],
    bindings: dict[str, str],
    zone_name: str,
    basis_currency: str,
    execution_currency: str,
    duplicate_candidate: bool,
) -> tuple[dict[str, Any] | None, str | None, set[str], set[str], int | None]:
    decisions: set[str] = set()
    blockers: set[str] = set(source["blocker_codes"])
    if blockers:
        return None, None, decisions, blockers, None
    event_type = source["normalized_event_type"]
    if event_type == "stock_dividend":
        return None, None, {"stock_dividend_v2_evidence_required"}, blockers, None
    if event_type not in SUPPORTED_TARGET_TYPES:
        blockers.add("source_type_unsupported")
        return None, None, decisions, blockers, None
    account_ref = bindings.get(source["source_primary_account_fingerprint"])
    if account_ref is None:
        decisions.add("primary_account_binding_required")
    related_account_ref = None
    if event_type == "transfer":
        related_account_ref = bindings.get(source["source_related_account_fingerprint"])
        if related_account_ref is None:
            decisions.add("related_account_binding_required")
    if execution_currency != basis_currency and event_type in {"buy", "sell", "dividend", "reward", "deposit"}:
        decisions.add("fx_conversion_evidence_required")
    effective_at_utc = None
    if source["event_time_evidence"] == "exact":
        effective_at_utc, time_error = _unique_utc(source["local_date"], source["local_time"], zone_name)
        if time_error:
            blockers.add(time_error)
    memo: str | None = None
    if source["source_memo"] is not None:
        if row_review["memo_action"] is None:
            decisions.add("memo_action_required")
        elif row_review["memo_action"] == "accept_source":
            memo = source["source_memo"]
        elif row_review["memo_action"] != "skip":
            _abort("legacy_per_asset_trade_review_invalid")
    elif row_review["memo_action"] is not None:
        _abort("legacy_per_asset_trade_review_invalid")
    if event_type not in {"reward", "deposit"} and (
        row_review["basis_evidence_mode"] is not None
        or row_review["basis_amount_mode"] is not None
        or row_review["provided_basis_decimal"] is not None
    ):
        _abort("legacy_per_asset_trade_review_invalid")
    if duplicate_candidate:
        if row_review["duplicate_action"] != "keep_confirmed":
            decisions.add("possible_duplicate_review_required")
    elif row_review["duplicate_action"] is not None:
        _abort("legacy_per_asset_trade_review_invalid")

    quantity = source["quantity_decimal"]
    unit_price = source["unit_price_decimal"]
    fee = source["source_fee_decimal"]
    monetary_fee = None
    asset_fee = None
    if fee is not None:
        if event_type in {"buy", "sell"}:
            if row_review["fee_treatment"] not in {None, "monetary_basis_currency"}:
                _abort("legacy_per_asset_trade_review_invalid")
            monetary_fee = fee
        else:
            treatment = row_review["fee_treatment"]
            if treatment is None:
                decisions.add("fee_treatment_required")
            elif treatment == "separate_event_required":
                decisions.add("fee_treatment_required")
            elif treatment == "principal_asset_quantity" and event_type in {"reward", "withdrawal", "transfer"}:
                asset_fee = fee
            elif treatment == "monetary_basis_currency" and event_type == "transfer":
                monetary_fee = fee
            else:
                blockers.add("fee_separate_event_required")
    elif row_review["fee_treatment"] is not None:
        _abort("legacy_per_asset_trade_review_invalid")

    amount_mode = "not_applicable"
    basis_mode = "not_applicable"
    eligible_quantity = None
    gross = None
    provided_basis = None
    movement_context = "not_applicable"
    original_mode = "not_applicable"
    original_date = original_time = original_zone = original_utc = None
    if event_type in {"buy", "sell"}:
        amount_mode = "quantity_unit_price"
        basis_mode = "derived_trade" if event_type == "buy" else "not_applicable"
    elif event_type == "dividend":
        mode = row_review["dividend_input_mode"] or "quantity_unit_price"
        if mode == "quantity_unit_price":
            if row_review["dividend_gross_total_decimal"] is not None:
                _abort("legacy_per_asset_trade_review_invalid")
            amount_mode = mode
            eligible_quantity = quantity
            quantity = None
        elif mode == "gross_total":
            amount_mode = mode
            eligible_quantity = quantity
            quantity = None
            unit_price = None
            gross = row_review["dividend_gross_total_decimal"]
            if gross is None:
                decisions.add("dividend_input_mode_required")
        else:
            _abort("legacy_per_asset_trade_review_invalid")
    elif row_review["dividend_input_mode"] is not None or row_review["dividend_gross_total_decimal"] is not None:
        _abort("legacy_per_asset_trade_review_invalid")

    if event_type == "reward":
        amount_mode = "quantity_unit_price"
        basis_mode = row_review["basis_evidence_mode"]
        if basis_mode is None:
            decisions.add("reward_basis_evidence_required")
            basis_mode = "basis_missing"
        if basis_mode == "provided_basis":
            if row_review["basis_amount_mode"] != "manual_total" or row_review["provided_basis_decimal"] is None:
                decisions.add("reward_basis_evidence_required")
            provided_basis = row_review["provided_basis_decimal"]
        elif basis_mode == "valuation_confirmed_as_basis":
            if row_review["basis_amount_mode"] not in {None, "source_quantity_unit_price"} or row_review["provided_basis_decimal"] is not None:
                _abort("legacy_per_asset_trade_review_invalid")
        elif basis_mode == "basis_missing":
            if row_review["basis_amount_mode"] not in {None, "not_applicable"} or row_review["provided_basis_decimal"] is not None:
                _abort("legacy_per_asset_trade_review_invalid")
    elif event_type == "deposit":
        basis_mode = row_review["basis_evidence_mode"]
        basis_amount_mode = row_review["basis_amount_mode"]
        if basis_mode is None:
            decisions.add("deposit_basis_evidence_required")
            basis_mode = "basis_missing"
            basis_amount_mode = "not_applicable"
        if basis_mode == "provided_basis":
            if basis_amount_mode == "source_quantity_unit_price" and unit_price not in {None, "0"}:
                amount_mode = "quantity_unit_price"
                provided_basis = None
            elif basis_amount_mode == "manual_total" and row_review["provided_basis_decimal"] is not None:
                amount_mode = "not_applicable"
                unit_price = None
                provided_basis = row_review["provided_basis_decimal"]
            else:
                decisions.add("deposit_basis_evidence_required")
        elif basis_mode == "basis_missing":
            if basis_amount_mode not in {None, "not_applicable"} or row_review["provided_basis_decimal"] is not None:
                _abort("legacy_per_asset_trade_review_invalid")
            amount_mode = "not_applicable"
            unit_price = None
        else:
            _abort("legacy_per_asset_trade_review_invalid")
        original_mode, original_date, original_time, original_zone, original_utc, original_decisions = _original_acquisition(row_review)
        decisions.update(original_decisions)
        movement_context = row_review["movement_context_code"] or ""
        if not movement_context:
            decisions.add("movement_context_required")
            movement_context = "unclassified"
    elif event_type == "withdrawal":
        unit_price = None
        movement_context = row_review["movement_context_code"] or ""
        if not movement_context:
            decisions.add("movement_context_required")
            movement_context = "unclassified"
    elif event_type == "transfer":
        unit_price = None

    if event_type not in {"deposit", "withdrawal"} and row_review["movement_context_code"] is not None:
        _abort("legacy_per_asset_trade_review_invalid")
    if event_type != "deposit" and any(
        row_review[key] is not None
        for key in (
            "original_acquired_time_evidence", "original_acquired_local_date", "original_acquired_local_time",
            "original_acquired_time_zone", "original_acquired_at_utc",
        )
    ):
        _abort("legacy_per_asset_trade_review_invalid")
    if blockers or decisions or account_ref is None:
        return None, memo, decisions, blockers, row_review["same_day_fifo_sequence"]
    event_ref = "evt_" + source["source_row_fingerprint"][:32]
    activity_event = {
        "event_ref": event_ref,
        "event_type": event_type,
        "account_ref": account_ref,
        "related_account_ref": related_account_ref,
        "asset_ref": target["asset_ref"],
        "source_asset_ref": None,
        "event_time_evidence": source["event_time_evidence"],
        "local_date": source["local_date"],
        "local_time": source["local_time"],
        "time_zone": zone_name,
        "effective_at_utc": effective_at_utc,
        "original_acquired_time_evidence": original_mode,
        "original_acquired_local_date": original_date,
        "original_acquired_local_time": original_time,
        "original_acquired_time_zone": original_zone,
        "original_acquired_at_utc": original_utc,
        "amount_input_mode": amount_mode,
        "basis_evidence_mode": basis_mode,
        "quantity_decimal": quantity,
        "eligible_quantity_decimal": eligible_quantity,
        "unit_price_decimal": unit_price,
        "gross_amount_decimal": gross,
        "monetary_fee_decimal": monetary_fee,
        "asset_fee_quantity_decimal": asset_fee,
        "provided_basis_decimal": provided_basis,
        "movement_context_code": movement_context,
    }
    return activity_event, memo, decisions, blockers, row_review["same_day_fifo_sequence"]


def _lot_order(lot: dict[str, Any]) -> tuple[Any, ...]:
    return (
        lot["acquired_local_date"],
        "" if lot["acquired_at_utc"] is None else lot["acquired_at_utc"],
        lot["fifo_source_sequence"],
        lot["lot_ref"],
    )


def _consume(lots: dict[str, list[dict[str, Any]]], account_ref: str, quantity: Fraction) -> list[dict[str, Any]]:
    current = sorted(lots.get(account_ref, []), key=_lot_order)
    remaining = quantity
    consumed: list[dict[str, Any]] = []
    while remaining > 0:
        if not current:
            raise ValueError("inventory")
        lot = current[0]
        take = min(lot["quantity"], remaining)
        basis_take = None if lot["basis"] is None else lot["basis"] * take / lot["quantity"]
        consumed.append(
            {
                "source_lot_ref": lot["lot_ref"],
                "acquired_local_date": lot["acquired_local_date"],
                "acquired_at_utc": lot["acquired_at_utc"],
                "fifo_source_sequence": lot["fifo_source_sequence"],
                "quantity": take,
                "basis": basis_take,
                "basis_status": lot["basis_status"],
            }
        )
        lot["quantity"] -= take
        if lot["basis"] is not None:
            lot["basis"] -= basis_take
        remaining -= take
        if lot["quantity"] == 0:
            current.pop(0)
    lots[account_ref] = current
    return consumed


def _public_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source_lot_ref": item["source_lot_ref"],
            "acquired_local_date": item["acquired_local_date"],
            "acquired_at_utc": item["acquired_at_utc"],
            "fifo_source_sequence": item["fifo_source_sequence"],
            "quantity": _exact_number(item["quantity"]),
            "basis": None if item["basis"] is None else _exact_number(item["basis"]),
            "basis_status": item["basis_status"],
        }
        for item in chunks
    ]


def _fifo_reconciliation(rows: list[dict[str, Any]], target: dict[str, Any], basis_currency: str) -> tuple[dict[str, Any], str | None]:
    lots: dict[str, list[dict[str, Any]]] = defaultdict(list)
    event_evidence: list[dict[str, Any]] = []
    outgoing_receipts: list[dict[str, Any]] = []
    transfer_receipts: list[dict[str, Any]] = []
    realized_sales: list[dict[str, Any]] = []
    monetary_fees = Fraction(0)
    asset_fees = Fraction(0)
    dividend_income = Fraction(0)
    reward_income = Fraction(0)
    event_counts: Counter[str] = Counter()
    for row in rows:
        event = row["activity_event"]
        event_type = event["event_type"]
        event_counts[event_type] += 1
        quantity = None if event["quantity_decimal"] is None else _fraction(event["quantity_decimal"])
        unit = None if event["unit_price_decimal"] is None else _fraction(event["unit_price_decimal"])
        monetary_fee = Fraction(0) if event["monetary_fee_decimal"] is None else _fraction(event["monetary_fee_decimal"])
        asset_fee = Fraction(0) if event["asset_fee_quantity_decimal"] is None else _fraction(event["asset_fee_quantity_decimal"])
        monetary_fees += monetary_fee
        asset_fees += asset_fee
        account = event["account_ref"]
        if event_type == "buy":
            basis = quantity * unit + monetary_fee
            lots[account].append(
                {
                    "lot_ref": "lot_" + event["event_ref"].split("_", 1)[1][:24],
                    "acquired_local_date": event["local_date"], "acquired_at_utc": event["effective_at_utc"],
                    "fifo_source_sequence": row["fifo_source_sequence"], "quantity": quantity,
                    "basis": basis, "basis_status": "completed",
                }
            )
            evidence = {"basis_created": _exact_number(basis)}
        elif event_type == "sell":
            try:
                consumed = _consume(lots, account, quantity)
            except ValueError:
                return {}, row["source_row_ref"]
            complete = all(item["basis"] is not None for item in consumed)
            consumed_basis = sum((item["basis"] for item in consumed if item["basis"] is not None), Fraction(0))
            proceeds = quantity * unit - monetary_fee
            gain = proceeds - consumed_basis if complete else None
            realized_sales.append(
                {
                    "source_row_ref": row["source_row_ref"], "quantity": _exact_number(quantity),
                    "net_proceeds": _exact_number(proceeds),
                    "consumed_fifo_basis": _exact_number(consumed_basis) if complete else None,
                    "realized_gain": None if gain is None else _exact_number(gain),
                    "realized_gain_status": "completed" if complete else "basis_missing",
                    "fifo_consumptions": _public_chunks(consumed),
                }
            )
            evidence = {"fifo_consumptions": _public_chunks(consumed)}
        elif event_type == "dividend":
            gross = _fraction(event["gross_amount_decimal"]) if event["gross_amount_decimal"] is not None else _fraction(event["eligible_quantity_decimal"]) * unit
            dividend_income += gross
            evidence = {"gross_income": _exact_number(gross)}
        elif event_type == "reward":
            gross = quantity * unit
            reward_income += gross
            if event["basis_evidence_mode"] == "valuation_confirmed_as_basis":
                basis = gross
                status = "completed"
            elif event["basis_evidence_mode"] == "provided_basis":
                basis = _fraction(event["provided_basis_decimal"])
                status = "completed"
            else:
                basis = None
                status = "basis_missing"
            lots[account].append(
                {
                    "lot_ref": "lot_" + event["event_ref"].split("_", 1)[1][:24],
                    "acquired_local_date": event["local_date"], "acquired_at_utc": event["effective_at_utc"],
                    "fifo_source_sequence": row["fifo_source_sequence"], "quantity": quantity,
                    "basis": basis, "basis_status": status,
                }
            )
            fee_chunks: list[dict[str, Any]] = []
            if asset_fee:
                try:
                    fee_chunks = _consume(lots, account, asset_fee)
                except ValueError:
                    return {}, row["source_row_ref"]
            evidence = {"gross_income": _exact_number(gross), "asset_fee_consumptions": _public_chunks(fee_chunks)}
        elif event_type == "deposit":
            if event["basis_evidence_mode"] == "basis_missing":
                basis = None
                status = "basis_missing"
            elif event["amount_input_mode"] == "quantity_unit_price":
                basis = quantity * unit
                status = "completed"
            else:
                basis = _fraction(event["provided_basis_decimal"])
                status = "completed"
            lots[account].append(
                {
                    "lot_ref": "lot_" + event["event_ref"].split("_", 1)[1][:24],
                    "acquired_local_date": event["original_acquired_local_date"],
                    "acquired_at_utc": event["original_acquired_at_utc"],
                    "fifo_source_sequence": row["fifo_source_sequence"], "quantity": quantity,
                    "basis": basis, "basis_status": status,
                }
            )
            evidence = {"basis_created": None if basis is None else _exact_number(basis), "basis_status": status}
        elif event_type == "withdrawal":
            try:
                principal_chunks = _consume(lots, account, quantity)
                fee_chunks = _consume(lots, account, asset_fee) if asset_fee else []
            except ValueError:
                return {}, row["source_row_ref"]
            outgoing_receipts.append(
                {
                    "source_row_ref": row["source_row_ref"], "movement_context_code": event["movement_context_code"],
                    "principal_lots": _public_chunks(principal_chunks), "asset_fee_lots": _public_chunks(fee_chunks),
                    "sale_inferred": False, "tax_disposition_inferred": False,
                }
            )
            evidence = {"outgoing_lot_receipt_emitted": True}
        else:
            try:
                moved = _consume(lots, account, quantity)
            except ValueError:
                return {}, row["source_row_ref"]
            destination = event["related_account_ref"]
            moved_public: list[dict[str, Any]] = []
            for index, chunk in enumerate(moved, start=1):
                destination_lot = {
                    "lot_ref": "lot_" + hashlib.sha256(f"{event['event_ref']}:{index}:{chunk['source_lot_ref']}".encode("ascii")).hexdigest()[:24],
                    "acquired_local_date": chunk["acquired_local_date"], "acquired_at_utc": chunk["acquired_at_utc"],
                    "fifo_source_sequence": chunk["fifo_source_sequence"], "quantity": chunk["quantity"],
                    "basis": chunk["basis"], "basis_status": chunk["basis_status"],
                }
                lots[destination].append(destination_lot)
                moved_public.append(
                    {
                        **_public_chunks([chunk])[0],
                        "destination_lot_ref": destination_lot["lot_ref"],
                    }
                )
            try:
                fee_chunks = _consume(lots, account, asset_fee) if asset_fee else []
            except ValueError:
                return {}, row["source_row_ref"]
            transfer_receipts.append(
                {
                    "source_row_ref": row["source_row_ref"], "moved_lots": moved_public,
                    "asset_fee_lots": _public_chunks(fee_chunks), "portfolio_principal_quantity_change": _exact_number(Fraction(0)),
                    "basis_preserved": True, "guv_created": False,
                }
            )
            evidence = {"transfer_lot_receipt_emitted": True}
        event_evidence.append({"source_row_ref": row["source_row_ref"], "event_type": event_type, **evidence})

    remaining_lots: list[dict[str, Any]] = []
    account_positions: list[dict[str, Any]] = []
    all_quantity = Fraction(0)
    known_basis = Fraction(0)
    basis_missing = False
    for account_ref, account_lots in sorted(lots.items()):
        ordered = sorted(account_lots, key=_lot_order)
        quantity_total = sum((lot["quantity"] for lot in ordered), Fraction(0))
        account_basis = sum((lot["basis"] for lot in ordered if lot["basis"] is not None), Fraction(0))
        account_missing = any(lot["basis"] is None for lot in ordered)
        all_quantity += quantity_total
        known_basis += account_basis
        basis_missing = basis_missing or account_missing
        account_positions.append(
            {
                "account_ref": account_ref, "quantity": _exact_number(quantity_total),
                "known_fifo_basis": _exact_number(account_basis), "basis_status": "basis_missing" if account_missing else "completed",
            }
        )
        for lot in ordered:
            remaining_lots.append(
                {
                    "lot_ref": lot["lot_ref"], "account_ref": account_ref, "asset_ref": target["asset_ref"],
                    "acquired_local_date": lot["acquired_local_date"], "acquired_at_utc": lot["acquired_at_utc"],
                    "quantity": _exact_number(lot["quantity"]),
                    "basis": None if lot["basis"] is None else _exact_number(lot["basis"]), "basis_status": lot["basis_status"],
                }
            )
    if all_quantity == 0:
        cost_average = {"cost_average_status": "empty_position", "remaining_quantity": _exact_number(Fraction(0)), "remaining_fifo_basis": _exact_number(Fraction(0)), "cost_average": None}
    elif basis_missing:
        cost_average = {"cost_average_status": "basis_missing", "remaining_quantity": _exact_number(all_quantity), "remaining_fifo_basis": None, "known_remaining_fifo_basis": _exact_number(known_basis), "cost_average": None}
    else:
        cost_average = {"cost_average_status": "completed", "remaining_quantity": _exact_number(all_quantity), "remaining_fifo_basis": _exact_number(known_basis), "cost_average": _exact_number(known_basis / all_quantity)}
    result = {
        "fifo_status": "completed_with_missing_basis" if basis_missing else "completed",
        "event_counts": [{"event_type": key, "count": event_counts[key]} for key in sorted(event_counts)],
        "event_evidence": event_evidence,
        "account_positions": account_positions,
        "remaining_lots": remaining_lots,
        "realized_sales": realized_sales,
        "outgoing_lot_receipts": outgoing_receipts,
        "transfer_lot_receipts": transfer_receipts,
        "cost_average": cost_average,
        "totals": {
            "monetary_fee": _exact_number(monetary_fees), "monetary_fee_currency": basis_currency,
            "asset_fee_quantity": _exact_number(asset_fees), "dividend_income": _exact_number(dividend_income),
            "reward_income": _exact_number(reward_income), "income_currency": basis_currency,
        },
        "cash_posting_count": 0,
        "synthetic_cash_posting_created": False,
        "provider_price_used": False,
        "tax_classification_inferred": False,
    }
    result["fifo_reconciliation_fingerprint"] = _fingerprint(result)
    return result, None


def _plan_impl(projection: Any, review: Any) -> dict[str, Any]:
    if not isinstance(projection, dict) or not isinstance(review, dict):
        _abort("legacy_per_asset_trade_review_invalid")
    projection_body = dict(projection)
    supplied_projection_fp = projection_body.pop("projection_fingerprint", None)
    if supplied_projection_fp != _fingerprint(projection_body) or projection.get("per_asset_trade_projection_version") != CONTRACT_VERSION:
        _abort("legacy_per_asset_trade_review_stale")
    expected_review_keys = {
        "per_asset_trade_plan_version", "projection_fingerprint", "target_asset", "basis_currency", "execution_currency",
        "time_zone", "accounts", "account_bindings", "companion_review", "row_reviews",
    }
    review_value = _exact_keys(review, expected_review_keys, "legacy_per_asset_trade_review_invalid")
    if review_value["per_asset_trade_plan_version"] != CONTRACT_VERSION or review_value["projection_fingerprint"] != supplied_projection_fp:
        _abort("legacy_per_asset_trade_review_stale")
    basis_currency = review_value["basis_currency"]
    execution_currency = review_value["execution_currency"]
    zone_name = review_value["time_zone"]
    if not isinstance(basis_currency, str) or _CURRENCY.fullmatch(basis_currency) is None or not isinstance(execution_currency, str) or _CURRENCY.fullmatch(execution_currency) is None:
        _abort("legacy_per_asset_trade_target_invalid")
    try:
        ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        _abort("legacy_per_asset_trade_target_invalid")
    accounts, bindings, target = _activity_catalog(review_value)
    source_account_fps = {item["source_account_fingerprint"] for item in projection["source_account_candidates"]}
    if set(bindings) - source_account_fps:
        _abort("legacy_per_asset_trade_review_invalid")
    companion_bound, companion_fp = _validate_companion(
        review_value["companion_review"], projection["source_asset_link_fingerprint"], target["asset_type"], target["quantity_scale"]
    )
    source_rows = projection.get("rows")
    if not isinstance(source_rows, list) or projection.get("source_row_count") != len(source_rows):
        _abort("legacy_per_asset_trade_review_invalid")
    source_refs = {row.get("source_row_ref") for row in source_rows}
    if len(source_refs) != len(source_rows) or not all(isinstance(value, str) for value in source_refs):
        _abort("legacy_per_asset_trade_review_invalid")
    row_reviews = _review_rows(review_value["row_reviews"], source_refs)
    duplicate_counts = Counter(row["duplicate_candidate_fingerprint"] for row in source_rows)
    planned_rows: list[dict[str, Any]] = []
    for source in source_rows:
        source_ref = source["source_row_ref"]
        row_review = row_reviews.get(source_ref, _empty_row_review(source_ref))
        activity_event, memo, decisions, blockers, same_day_sequence = _build_activity_event(
            source, row_review, target, bindings, zone_name, basis_currency, execution_currency,
            duplicate_counts[source["duplicate_candidate_fingerprint"]] > 1,
        )
        activity_effect = None
        if activity_event is not None and not decisions and not blockers:
            try:
                activity_preview = validate_asset_activity_v1(
                    {
                        "asset_activity_version": 1, "basis_currency": basis_currency,
                        "accounts": list(accounts.values()), "assets": [target], "events": [activity_event],
                    }
                )
                activity_effect = activity_preview["event_effects"][0]
            except AssetActivityV1Error:
                blockers.add("activity_semantics_invalid")
                activity_event = None
        disposition = "blocked" if blockers else ("decision_required" if decisions else "ready")
        planned_rows.append(
            {
                "source_row_ref": source_ref,
                "source_row_ordinal": source["source_row_ordinal"],
                "source_row_fingerprint": source["source_row_fingerprint"],
                "disposition": disposition,
                "decision_codes": sorted(decisions) if not blockers else [],
                "blocker_codes": sorted(blockers),
                "normalized_event_type": source["normalized_event_type"],
                "activity_event": activity_event if disposition == "ready" else None,
                "activity_effect": activity_effect if disposition == "ready" else None,
                "memo": memo if disposition == "ready" else None,
                "same_day_fifo_sequence": same_day_sequence,
                "fifo_source_sequence": source["source_row_ordinal"],
                "cash_posting_created": False,
            }
        )
    inventory_types = {"buy", "sell", "reward", "deposit", "withdrawal", "transfer"}
    by_date: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in planned_rows:
        if row["disposition"] == "ready" and row["normalized_event_type"] in inventory_types:
            by_date[row["activity_event"]["local_date"]].append(row)
    for rows_on_date in by_date.values():
        exact_times = [row["activity_event"]["effective_at_utc"] for row in rows_on_date if row["activity_event"]["event_time_evidence"] == "exact"]
        ambiguous = len(rows_on_date) > 1 and (
            any(row["activity_event"]["event_time_evidence"] == "date_only" for row in rows_on_date)
            or len(exact_times) != len(set(exact_times))
        )
        sequences = [row["same_day_fifo_sequence"] for row in rows_on_date]
        if ambiguous:
            if any(sequence is None for sequence in sequences) or len(sequences) != len(set(sequences)):
                for row in rows_on_date:
                    row["disposition"] = "decision_required"
                    row["decision_codes"] = ["fifo_same_day_order_required"]
                    row["activity_event"] = None
                    row["activity_effect"] = None
                    row["memo"] = None
            else:
                for row in rows_on_date:
                    row["fifo_source_sequence"] = row["same_day_fifo_sequence"]
        elif any(sequence is not None for sequence in sequences):
            _abort("legacy_per_asset_trade_review_invalid")
    counts = Counter(row["disposition"] for row in planned_rows)
    fifo: dict[str, Any] | None = None
    if counts["ready"] == len(planned_rows):
        ordered = sorted(
            planned_rows,
            key=lambda row: (
                row["activity_event"]["local_date"],
                0 if row["same_day_fifo_sequence"] is not None else 1,
                row["fifo_source_sequence"] if row["same_day_fifo_sequence"] is not None else 0,
                "" if row["same_day_fifo_sequence"] is not None else (row["activity_event"]["effective_at_utc"] or ""),
                row["source_row_ordinal"],
            ),
        )
        fifo, failed_ref = _fifo_reconciliation(ordered, target, basis_currency)
        if failed_ref is not None:
            failed = next(row for row in planned_rows if row["source_row_ref"] == failed_ref)
            failed["disposition"] = "blocked"
            failed["blocker_codes"] = ["fifo_inventory_insufficient"]
            failed["activity_event"] = None
            failed["activity_effect"] = None
            failed["memo"] = None
            counts = Counter(row["disposition"] for row in planned_rows)
            fifo = None
    all_ready = counts["ready"] == len(planned_rows)
    basis_incomplete = bool(fifo and fifo["fifo_status"] == "completed_with_missing_basis")
    result = {
        "per_asset_trade_plan_version": CONTRACT_VERSION,
        "plan_status": (
            "ready_for_sandbox_apply_with_incomplete_basis" if all_ready and basis_incomplete
            else "ready_for_sandbox_apply" if all_ready
            else "blocked" if counts["blocked"]
            else "decision_required"
        ),
        "projection_fingerprint": supplied_projection_fp,
        "source_asset_link_fingerprint": projection["source_asset_link_fingerprint"],
        "target_asset_ref": target["asset_ref"],
        "basis_currency": basis_currency,
        "execution_currency": execution_currency,
        "time_zone": zone_name,
        "source_row_count": len(planned_rows),
        "ready_row_count": counts["ready"],
        "decision_required_row_count": counts["decision_required"],
        "blocked_row_count": counts["blocked"],
        "rows": planned_rows,
        "source_row_disposition_complete": sum(counts.values()) == len(planned_rows),
        "fifo_reconciliation": fifo,
        "fifo_full_oracle_executed": fifo is not None,
        "companion_review_bound": companion_bound,
        "companion_review_fingerprint": companion_fp,
        "legacy_asset_id_became_canonical_id": False,
        "filename_identity_used": False,
        "automatic_account_creation": False,
        "automatic_cash_posting_count": 0,
        "provider_listing_value_imported": False,
        "tax_classification_inferred": False,
        "rounding_performed": False,
        "sandbox_apply_implemented": False,
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "private_output_logged": False,
    }
    result["plan_fingerprint"] = _fingerprint(result)
    return result


def plan_legacy_per_asset_trade_v1(projection: Any, review: Any) -> dict[str, Any]:
    try:
        return _plan_impl(projection, review)
    except LegacyPerAssetTradePlannerV1Error:
        raise
    except Exception:
        raise LegacyPerAssetTradePlannerV1Error("legacy_per_asset_trade_boundary_failed") from None


__all__ = [
    "LegacyPerAssetTradePlannerV1Error",
    "legacy_per_asset_trade_planner_v1_blocker_codes",
    "legacy_per_asset_trade_planner_v1_decision_codes",
    "legacy_per_asset_trade_planner_v1_error_codes",
    "plan_legacy_per_asset_trade_v1",
    "project_legacy_per_asset_trade_bytes_v1",
    "read_legacy_per_asset_trade_v1",
]
