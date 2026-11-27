#!/usr/bin/env python3
"""Provider-neutral append-only FX History and exact Conversion v1 boundary."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts" / "fx-history" / "v1" / "schema.sql"
STORE_VERSION = 2600
ALGORITHM_VERSION = "fx_conversion_v1.0.0"
MAX_RATE_AGE_DAYS = (date.max - date.min).days

ERROR_CODES = frozenset({
    "fx_history_artifact_context_mismatch", "fx_history_artifact_exists",
    "fx_history_artifact_invalid", "fx_history_boundary_failed",
    "fx_history_calendar_invalid", "fx_history_candidate_fingerprint_mismatch",
    "fx_history_candidate_invalid", "fx_history_context_invalid",
    "fx_history_conversion_input_invalid", "fx_history_conversion_route_invalid",
    "fx_history_correction_stale", "fx_history_decimal_invalid",
    "fx_history_domain_unchanged", "fx_history_evidence_exists",
    "fx_history_evidence_invalid", "fx_history_initial_exists",
    "fx_history_job_binding_invalid", "fx_history_job_invalid", "fx_history_pair_conflict",
    "fx_history_pair_invalid", "fx_history_pair_missing", "fx_history_range_invalid",
    "fx_history_request_conflict", "fx_history_store_context_mismatch",
    "fx_history_store_exists", "fx_history_store_invalid",
    "fx_history_synthetic_failpoint", "fx_history_write_failed",
})
FAILPOINTS = frozenset({"after_request", "after_first_revision", "before_commit"})
CALENDAR_CODES = frozenset({"weekday_fx", "continuous_24_7", "custom_reviewed"})
RATE_TYPES = frozenset({"reference_rate", "market_close", "mid_rate"})
SOURCE_KINDS = frozenset({"synthetic_fixture", "manual_reviewed_evidence", "market_plugin"})
DAY_STATUSES = frozenset({"observed", "non_trading_day", "source_gap"})
QUALITY_STATUSES = frozenset({"complete", "corrected", "calendar_confirmed", "explicit_gap"})
GAP_REASONS = frozenset({"source_no_data", "source_partial_response", "calendar_ambiguity"})
CORRECTION_REASONS = frozenset({"source_correction", "calendar_correction", "quality_correction", "manual_review_correction"})
REVISION_MODES = frozenset({"initial", "unchanged", "correction"})
ROUTE_KINDS = frozenset({"identity", "direct", "inverse", "explicit_two_leg_chain", "unsupported"})
SELECTION_POLICIES = frozenset({"exact_date", "previous_observed_within_max_age"})
DIRECTIONS = frozenset({"direct", "inverse"})
CURRENCY_ROLES = frozenset({"native_currency", "transaction_currency", "reporting_currency", "market_currency", "tax_currency"})

_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9]{2}_[a-f0-9]{32}$")
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,79}$")
_PLUGIN = re.compile(r"^[a-z][a-z0-9_.-]{2,79}$")
_MARKET_CODE = re.compile(r"^[A-Z0-9_]{2,16}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")

_PAIR_FIELDS = frozenset({
    "contract_version", "pair_ref", "base_currency", "quote_currency", "market_code",
    "timezone_name", "calendar_code", "rate_type", "catalog_fingerprint", "pair_fingerprint",
})
_DAY_INPUT_FIELDS = frozenset({
    "rate_date", "revision_mode", "supersedes_revision_ref", "day_status", "rate_decimal",
    "quality_status", "gap_reason", "source_observation_ref", "observed_at_utc", "correction_reason",
})
_DAY_FIELDS = _DAY_INPUT_FIELDS | {"source_day_fingerprint"}
_CANDIDATE_FIELDS = frozenset({
    "contract_version", "pair_ref", "request_ref", "source_kind", "source_ref", "source_version",
    "plugin_id", "plugin_version", "plugin_manifest_fingerprint", "request_fingerprint",
    "job_binding_fingerprint", "requested_start_date", "requested_end_date", "retrieved_at_utc",
    "days", "candidate_fingerprint",
})
_ITEM_FIELDS = frozenset({
    "conversion_item_ref", "effective_date", "native_amount_decimal", "native_currency",
    "native_currency_role", "output_scale", "route_kind", "selection_policy", "max_age_days", "legs",
})
_LEG_FIELDS = frozenset({"pair_ref", "direction"})
_REQUEST_FIELDS = frozenset({
    "contract_version", "conversion_scope_ref", "target_currency", "algorithm_version",
    "rounding_mode", "input_fingerprint", "history_cutoff_at_utc", "job_binding_fingerprint",
    "items", "request_fingerprint",
})
_RESULT_FIELDS = frozenset({
    "conversion_item_ref", "effective_date", "native_amount_decimal", "native_currency",
    "native_currency_role", "target_currency", "output_scale", "route_kind", "selection_policy", "max_age_days",
    "item_input_fingerprint", "route_legs", "conversion_status", "converted_amount_decimal",
    "effective_rate_numerator", "effective_rate_denominator", "legs",
    "rate_evidence_fingerprint", "result_fingerprint",
})
_RESULT_LEG_FIELDS = frozenset({
    "pair_ref", "base_currency", "quote_currency", "direction", "rate_date", "rate_decimal",
    "factor_numerator", "factor_denominator", "rate_age_days", "selection_basis",
    "effective_day_status", "revision_ref",
    "revision_fingerprint", "observed_at_utc", "quality_status", "source_kind", "source_ref",
    "source_version", "plugin_id", "plugin_version", "plugin_manifest_fingerprint",
})
_DOMAIN_FIELDS = ("day_status", "rate_decimal", "quality_status", "gap_reason")


class FxHistoryBlocked(ValueError):
    def __init__(self, code: str):
        if code not in ERROR_CODES:
            raise ValueError("fx_history_error_code_unregistered")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class FxHistoryContext:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str
    role: str = "market_worker"


@dataclass(frozen=True)
class FxHistoryReceipt:
    request_ref: str
    candidate_fingerprint: str
    appended_day_count: int
    corrected_day_count: int
    unchanged_day_count: int
    row_set_fingerprint: str
    receipt_fingerprint: str
    exact_replay: bool


def _abort(code: str) -> None:
    raise FxHistoryBlocked(code)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = _canonical(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _id(prefix: str, value: Any) -> str:
    return f"{prefix}_{_sha(value)[:32]}"


def _normalize_context(context: FxHistoryContext | Mapping[str, str], *, writer: bool = False) -> FxHistoryContext:
    if isinstance(context, Mapping):
        try:
            context = FxHistoryContext(
                context["tenant_id"], context["user_id"], context["data_space_id"],
                context["actor_id"], context.get("role", "market_worker"),
            )
        except (KeyError, TypeError) as exc:
            raise FxHistoryBlocked("fx_history_context_invalid") from exc
    if not isinstance(context, FxHistoryContext):
        _abort("fx_history_context_invalid")
    values = (context.tenant_id, context.user_id, context.data_space_id, context.actor_id)
    if any(
        not isinstance(value, str) or not 3 <= len(value) <= (80 if index == 3 else 64)
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
        for index, value in enumerate(values)
    ) or not context.data_space_id.startswith("sbx_"):
        _abort("fx_history_context_invalid")
    if context.role not in {
        "market_worker", "portfolio_worker", "tax_worker", "analysis_worker",
        "viewer", "tax_viewer", "analysis_viewer",
    }:
        _abort("fx_history_context_invalid")
    if writer and context.role != "market_worker":
        _abort("fx_history_context_invalid")
    return context


def fx_history_context_fingerprint_v1(context: FxHistoryContext | Mapping[str, str]) -> str:
    context = _normalize_context(context)
    return _sha({
        "contract_version": "fx_history_context_v1", "tenant_id": context.tenant_id,
        "user_id": context.user_id, "data_space_id": context.data_space_id,
    })


def _ref(value: Any, prefix: str, code: str = "fx_history_candidate_invalid") -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None or not value.startswith(prefix):
        _abort(code)
    return value


def _fingerprint(value: Any, code: str = "fx_history_candidate_invalid") -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        _abort(code)
    return value


def _utc(value: Any, code: str = "fx_history_candidate_invalid") -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort(code)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _abort(code)
    return parsed


def _day_date(value: Any) -> date:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        _abort("fx_history_range_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _abort("fx_history_range_invalid")
    if parsed.isoformat() != value:
        _abort("fx_history_range_invalid")
    return parsed


def _date_range(start: date, end: date) -> list[str]:
    count = (end - start).days + 1
    if count < 1 or count > 20000:
        _abort("fx_history_range_invalid")
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def _currency(value: Any, code: str = "fx_history_pair_invalid") -> str:
    if not isinstance(value, str) or _CURRENCY.fullmatch(value) is None:
        _abort(code)
    return value


def _decimal_text(value: Any, *, positive: bool = False, code: str = "fx_history_decimal_invalid") -> str:
    if not isinstance(value, str) or len(value) > 80 or _DECIMAL.fullmatch(value) is None or value == "-0":
        _abort(code)
    fraction = _fraction_from_decimal(value)
    if positive and fraction <= 0:
        _abort(code)
    return value


def _fraction_from_decimal(value: str) -> Fraction:
    sign = -1 if value.startswith("-") else 1
    unsigned = value[1:] if sign < 0 else value
    if "." in unsigned:
        whole, fractional = unsigned.split(".", 1)
        return Fraction(sign * int(whole + fractional), 10 ** len(fractional))
    return Fraction(sign * int(unsigned), 1)


def _round_fraction(value: Fraction, scale: int) -> str:
    factor = 10 ** scale
    numerator = abs(value.numerator) * factor
    quotient, remainder = divmod(numerator, value.denominator)
    doubled = remainder * 2
    if doubled > value.denominator or doubled == value.denominator and quotient % 2 == 1:
        quotient += 1
    sign = "-" if value < 0 and quotient else ""
    digits = str(quotient)
    if scale:
        digits = digits.rjust(scale + 1, "0")
        text = sign + digits[:-scale] + "." + digits[-scale:]
        text = text.rstrip("0").rstrip(".")
    else:
        text = sign + digits
    if text == "-0":
        text = "0"
    if len(text) > 80:
        _abort("fx_history_decimal_invalid")
    return text


def _owner_only_directory(path: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(path))
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, TypeError, ValueError) as exc:
        raise FxHistoryBlocked("fx_history_store_invalid") from exc
    wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
    if absolute != resolved or not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700 or wrong_owner:
        _abort("fx_history_store_invalid")
    return resolved


def _regular_path(path: str | Path, *, new: bool = False, artifact: bool = False) -> Path:
    try:
        target = Path(path)
    except (TypeError, ValueError) as exc:
        raise FxHistoryBlocked("fx_history_store_invalid") from exc
    exists_code = "fx_history_artifact_exists" if artifact else "fx_history_store_exists"
    invalid_code = "fx_history_artifact_invalid" if artifact else "fx_history_store_invalid"
    if new:
        if target.exists() or target.is_symlink():
            _abort(exists_code)
        parent = _owner_only_directory(target.parent)
        return parent / target.name
    try:
        absolute = Path(os.path.abspath(target))
        resolved = target.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, TypeError, ValueError) as exc:
        raise FxHistoryBlocked(invalid_code) from exc
    wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
    if absolute != resolved or target.is_symlink() or not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or wrong_owner:
        _abort(invalid_code)
    _owner_only_directory(resolved.parent)
    return resolved


def _connect(path: str | Path, context: FxHistoryContext | Mapping[str, str], *, read_only: bool = False) -> sqlite3.Connection:
    context = _normalize_context(context, writer=not read_only)
    if read_only and context.role not in {"market_worker", "portfolio_worker", "tax_worker", "analysis_worker"}:
        _abort("fx_history_context_invalid")
    source = _regular_path(path)
    try:
        if read_only:
            connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
            connection.execute("PRAGMA query_only=ON")
        else:
            connection = sqlite3.connect(source, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        binding = connection.execute("SELECT context_binding_fingerprint FROM fx_history_store_binding WHERE singleton_id=1").fetchone()
        if version != STORE_VERSION or binding is None or binding[0] != fx_history_context_fingerprint_v1(context):
            connection.close()
            _abort("fx_history_store_context_mismatch")
        return connection
    except FxHistoryBlocked:
        raise
    except sqlite3.Error as exc:
        raise FxHistoryBlocked("fx_history_store_invalid") from exc


def bootstrap_fx_history_store_v1(path: str | Path, context: FxHistoryContext | Mapping[str, str], created_at_utc: str) -> Path:
    context = _normalize_context(context, writer=True)
    _utc(created_at_utc)
    target = _regular_path(path, new=True)
    descriptor = None
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(descriptor)
        descriptor = None
        connection = sqlite3.connect(target)
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute("INSERT INTO fx_history_store_binding VALUES (1,2600,?,?)", (fx_history_context_fingerprint_v1(context), created_at_utc))
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            _abort("fx_history_store_invalid")
        connection.close()
        os.chmod(target, 0o600)
        return target
    except FxHistoryBlocked:
        target.unlink(missing_ok=True)
        raise
    except FileExistsError:
        _abort("fx_history_store_exists")
    except Exception as exc:
        if descriptor is not None:
            os.close(descriptor)
        target.unlink(missing_ok=True)
        raise FxHistoryBlocked("fx_history_store_invalid") from exc


def new_fx_pair_binding_v1(*, pair_ref: str, base_currency: str, quote_currency: str, market_code: str, timezone_name: str, calendar_code: str, rate_type: str, catalog_fingerprint: str) -> dict[str, Any]:
    body = {
        "contract_version": "fx_pair_binding_v1",
        "pair_ref": _ref(pair_ref, "fxp_", "fx_history_pair_invalid"),
        "base_currency": _currency(base_currency), "quote_currency": _currency(quote_currency),
        "market_code": market_code, "timezone_name": timezone_name,
        "calendar_code": calendar_code, "rate_type": rate_type,
        "catalog_fingerprint": _fingerprint(catalog_fingerprint, "fx_history_pair_invalid"),
    }
    if base_currency == quote_currency or not isinstance(market_code, str) or _MARKET_CODE.fullmatch(market_code) is None:
        _abort("fx_history_pair_invalid")
    if calendar_code not in CALENDAR_CODES or rate_type not in RATE_TYPES or not isinstance(timezone_name, str) or not 3 <= len(timezone_name) <= 64:
        _abort("fx_history_pair_invalid")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        _abort("fx_history_pair_invalid")
    return {**body, "pair_fingerprint": _sha(body)}


def _pair(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _PAIR_FIELDS or value.get("contract_version") != "fx_pair_binding_v1":
        _abort("fx_history_pair_invalid")
    rebuilt = new_fx_pair_binding_v1(**{key: value[key] for key in (
        "pair_ref", "base_currency", "quote_currency", "market_code", "timezone_name",
        "calendar_code", "rate_type", "catalog_fingerprint",
    )})
    if rebuilt != value:
        _abort("fx_history_pair_invalid")
    return rebuilt


def bind_fx_pair_v1(store_path: str | Path, context: FxHistoryContext | Mapping[str, str], pair: Mapping[str, Any], bound_at_utc: str) -> bool:
    context = _normalize_context(context, writer=True)
    pair = _pair(dict(pair))
    _utc(bound_at_utc)
    connection = _connect(store_path, context)
    try:
        connection.execute("BEGIN IMMEDIATE")
        created = connection.execute("SELECT created_at_utc FROM fx_history_store_binding WHERE singleton_id=1").fetchone()[0]
        if bound_at_utc < created:
            _abort("fx_history_pair_invalid")
        existing = connection.execute("SELECT pair_fingerprint FROM fx_pair_binding WHERE pair_ref=?", (pair["pair_ref"],)).fetchone()
        if existing is not None:
            if existing[0] != pair["pair_fingerprint"]:
                _abort("fx_history_pair_conflict")
            connection.rollback()
            return True
        connection.execute(
            "INSERT INTO fx_pair_binding(pair_id,pair_ref,base_currency,quote_currency,market_code,timezone_name,calendar_code,rate_type,catalog_fingerprint,pair_fingerprint,bound_by_actor,bound_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (_id("fpi", pair["pair_ref"]), pair["pair_ref"], pair["base_currency"], pair["quote_currency"], pair["market_code"], pair["timezone_name"], pair["calendar_code"], pair["rate_type"], pair["catalog_fingerprint"], pair["pair_fingerprint"], context.actor_id, bound_at_utc),
        )
        connection.commit()
        return False
    except FxHistoryBlocked:
        connection.rollback()
        raise
    except sqlite3.Error as exc:
        connection.rollback()
        raise FxHistoryBlocked("fx_history_write_failed") from exc
    finally:
        connection.close()


def fx_history_job_binding_fingerprint_v1(context: FxHistoryContext | Mapping[str, str], *, pair_ref: str, request_ref: str, request_fingerprint: str, source_ref: str) -> str:
    context = _normalize_context(context, writer=True)
    return _sha({
        "contract_version": "fx_history_job_binding_v1",
        "context_binding_fingerprint": fx_history_context_fingerprint_v1(context),
        "actor_id": context.actor_id, "role": context.role, "capability": "append_fx_history",
        "pair_ref": _ref(pair_ref, "fxp_"), "request_ref": _ref(request_ref, "fxq_"),
        "request_fingerprint": _fingerprint(request_fingerprint), "source_ref": _ref(source_ref, "fxs_"),
    })


def _validate_day(row: Mapping[str, Any]) -> None:
    _day_date(row["rate_date"])
    if row["revision_mode"] not in REVISION_MODES or row["day_status"] not in DAY_STATUSES or row["quality_status"] not in QUALITY_STATUSES:
        _abort("fx_history_candidate_invalid")
    mode = row["revision_mode"]
    if mode == "initial" and (row["supersedes_revision_ref"] is not None or row["correction_reason"] is not None):
        _abort("fx_history_candidate_invalid")
    if mode == "unchanged" and (row["supersedes_revision_ref"] is None or row["correction_reason"] is not None):
        _abort("fx_history_candidate_invalid")
    if mode == "correction" and (row["supersedes_revision_ref"] is None or row["correction_reason"] not in CORRECTION_REASONS):
        _abort("fx_history_candidate_invalid")
    if row["supersedes_revision_ref"] is not None:
        _ref(row["supersedes_revision_ref"], "fxv_")
    _ref(row["source_observation_ref"], "fxo_")
    _utc(row["observed_at_utc"])
    status = row["day_status"]
    if status == "observed":
        _decimal_text(row["rate_decimal"], positive=True)
        if row["gap_reason"] is not None or row["quality_status"] not in {"complete", "corrected"}:
            _abort("fx_history_candidate_invalid")
        if mode == "initial" and row["quality_status"] != "complete" or mode == "correction" and row["quality_status"] != "corrected":
            _abort("fx_history_candidate_invalid")
    elif row["rate_decimal"] is not None:
        _abort("fx_history_candidate_invalid")
    elif status == "non_trading_day":
        if row["gap_reason"] is not None or row["quality_status"] != "calendar_confirmed":
            _abort("fx_history_candidate_invalid")
    elif row["gap_reason"] not in GAP_REASONS or row["quality_status"] != "explicit_gap":
        _abort("fx_history_candidate_invalid")


def seal_fx_history_candidate_v1(*, pair_ref: str, request_ref: str, source_kind: str, source_ref: str, source_version: str, plugin_id: str | None, plugin_version: str | None, plugin_manifest_fingerprint: str | None, request_fingerprint: str, job_binding_fingerprint: str, requested_start_date: str, requested_end_date: str, retrieved_at_utc: str, days: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    _ref(pair_ref, "fxp_"); _ref(request_ref, "fxq_"); _ref(source_ref, "fxs_")
    _fingerprint(request_fingerprint); _fingerprint(job_binding_fingerprint, "fx_history_job_binding_invalid")
    if source_kind not in SOURCE_KINDS or not isinstance(source_version, str) or not 3 <= len(source_version) <= 80 or _TOKEN.fullmatch(source_version) is None:
        _abort("fx_history_candidate_invalid")
    if source_kind == "market_plugin":
        if not isinstance(plugin_id, str) or _PLUGIN.fullmatch(plugin_id) is None or not isinstance(plugin_version, str) or _TOKEN.fullmatch(plugin_version) is None:
            _abort("fx_history_candidate_invalid")
        _fingerprint(plugin_manifest_fingerprint)
    elif any(value is not None for value in (plugin_id, plugin_version, plugin_manifest_fingerprint)):
        _abort("fx_history_candidate_invalid")
    retrieved = _utc(retrieved_at_utc)
    expected_dates = _date_range(_day_date(requested_start_date), _day_date(requested_end_date))
    if not isinstance(days, Sequence) or isinstance(days, (str, bytes)):
        _abort("fx_history_candidate_invalid")
    sealed = []
    for raw in days:
        if not isinstance(raw, Mapping) or set(raw) != _DAY_INPUT_FIELDS:
            _abort("fx_history_candidate_invalid")
        row = dict(raw); _validate_day(row)
        if _utc(row["observed_at_utc"]) > retrieved:
            _abort("fx_history_candidate_invalid")
        row["source_day_fingerprint"] = _sha(row)
        sealed.append(row)
    if [row["rate_date"] for row in sealed] != expected_dates:
        _abort("fx_history_range_invalid")
    body = {
        "contract_version": "fx_history_candidate_v1", "pair_ref": pair_ref,
        "request_ref": request_ref, "source_kind": source_kind, "source_ref": source_ref,
        "source_version": source_version, "plugin_id": plugin_id, "plugin_version": plugin_version,
        "plugin_manifest_fingerprint": plugin_manifest_fingerprint,
        "request_fingerprint": request_fingerprint, "job_binding_fingerprint": job_binding_fingerprint,
        "requested_start_date": requested_start_date, "requested_end_date": requested_end_date,
        "retrieved_at_utc": retrieved_at_utc, "days": sealed,
    }
    return {**body, "candidate_fingerprint": _sha(body)}


def _candidate(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _CANDIDATE_FIELDS or value.get("contract_version") != "fx_history_candidate_v1":
        _abort("fx_history_candidate_invalid")
    try:
        rebuilt = seal_fx_history_candidate_v1(
            **{key: value[key] for key in (
                "pair_ref", "request_ref", "source_kind", "source_ref", "source_version", "plugin_id",
                "plugin_version", "plugin_manifest_fingerprint", "request_fingerprint", "job_binding_fingerprint",
                "requested_start_date", "requested_end_date", "retrieved_at_utc",
            )},
            days=[{key: row[key] for key in _DAY_INPUT_FIELDS} for row in value["days"]],
        )
    except (KeyError, TypeError):
        _abort("fx_history_candidate_invalid")
    if rebuilt != value:
        _abort("fx_history_candidate_fingerprint_mismatch")
    return rebuilt


def _calendar_valid(pair: Mapping[str, Any], row: Mapping[str, Any]) -> None:
    rate_date = _day_date(row["rate_date"])
    if pair["calendar_code"] == "continuous_24_7" and row["day_status"] == "non_trading_day":
        _abort("fx_history_calendar_invalid")
    if pair["calendar_code"] == "weekday_fx" and rate_date.weekday() >= 5 and row["day_status"] != "non_trading_day":
        _abort("fx_history_calendar_invalid")
    if row["day_status"] == "observed" and _utc(row["observed_at_utc"]).astimezone(ZoneInfo(pair["timezone_name"])).date() != rate_date:
        _abort("fx_history_calendar_invalid")


def _receipt(row: sqlite3.Row, replay: bool) -> FxHistoryReceipt:
    return FxHistoryReceipt(row["request_ref"], row["candidate_fingerprint"], int(row["appended_day_count"]), int(row["corrected_day_count"]), int(row["unchanged_day_count"]), row["row_set_fingerprint"], row["receipt_fingerprint"], replay)


def read_fx_history_request_receipt_v1(store_path: str | Path, context: FxHistoryContext | Mapping[str, str], request_ref: str) -> FxHistoryReceipt | None:
    """Read committed request evidence without replaying the canonical writer."""
    context = _normalize_context(context)
    _ref(request_ref, "fxq_")
    connection = _connect(store_path, context, read_only=True)
    try:
        connection.execute("BEGIN")
        row = connection.execute("SELECT * FROM fx_history_request WHERE request_ref=?", (request_ref,)).fetchone()
        if row is None:
            return None
        receipt = _receipt(row, True)
        body = {key: getattr(receipt, key) for key in (
            "request_ref", "candidate_fingerprint", "appended_day_count", "corrected_day_count",
            "unchanged_day_count", "row_set_fingerprint")}
        evidence = connection.execute(
            "SELECT entity.rate_date,revision.revision_ref,evidence.disposition "
            "FROM fx_request_day_evidence evidence JOIN fx_day_entity entity USING(fx_day_id) "
            "JOIN fx_day_revision revision ON revision.revision_id=evidence.resulting_revision_id "
            "WHERE evidence.request_id=? ORDER BY evidence.row_ordinal", (row["request_id"],)
        ).fetchall()
        dates = _date_range(_day_date(row["requested_start_date"]), _day_date(row["requested_end_date"]))
        if (receipt.receipt_fingerprint != _sha(body)
            or receipt.row_set_fingerprint != _sha([dict(item) for item in evidence])
            or [item["rate_date"] for item in evidence] != dates
            or any(body[key] != sum(item["disposition"] == disposition for item in evidence)
                   for key, disposition in (("appended_day_count", "appended"),
                                            ("corrected_day_count", "corrected"),
                                            ("unchanged_day_count", "unchanged")))):
            _abort("fx_history_store_invalid")
        return receipt
    except sqlite3.Error as error:
        raise FxHistoryBlocked("fx_history_store_invalid") from error
    finally:
        connection.close()


def append_fx_history_v1(store_path: str | Path, context: FxHistoryContext | Mapping[str, str], candidate: Mapping[str, Any], completed_at_utc: str, *, failpoint: str | None = None) -> FxHistoryReceipt:
    context = _normalize_context(context, writer=True)
    candidate = _candidate(dict(candidate))
    expected_job = fx_history_job_binding_fingerprint_v1(context, pair_ref=candidate["pair_ref"], request_ref=candidate["request_ref"], request_fingerprint=candidate["request_fingerprint"], source_ref=candidate["source_ref"])
    if candidate["job_binding_fingerprint"] != expected_job:
        _abort("fx_history_job_binding_invalid")
    if _utc(completed_at_utc) < _utc(candidate["retrieved_at_utc"]):
        _abort("fx_history_candidate_invalid")
    if failpoint is not None and failpoint not in FAILPOINTS:
        _abort("fx_history_candidate_invalid")
    connection = _connect(store_path, context)
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing_request = connection.execute("SELECT * FROM fx_history_request WHERE request_ref=?", (candidate["request_ref"],)).fetchone()
        if existing_request is not None:
            if existing_request["candidate_fingerprint"] != candidate["candidate_fingerprint"]:
                _abort("fx_history_request_conflict")
            connection.rollback(); return _receipt(existing_request, True)
        pair = connection.execute("SELECT * FROM fx_pair_binding WHERE pair_ref=?", (candidate["pair_ref"],)).fetchone()
        if pair is None:
            _abort("fx_history_pair_missing")
        if completed_at_utc < pair["bound_at_utc"]:
            _abort("fx_history_candidate_invalid")
        plans = []; counts = {"appended": 0, "corrected": 0, "unchanged": 0}
        for ordinal, row in enumerate(candidate["days"], 1):
            _calendar_valid(pair, row)
            current = connection.execute(
                "SELECT entity.fx_day_id,entity.fx_day_ref,revision.* FROM fx_day_entity entity JOIN current_fx_day_revision revision USING(fx_day_id) WHERE entity.pair_id=? AND entity.rate_date=?",
                (pair["pair_id"], row["rate_date"]),
            ).fetchone()
            if current is None:
                if row["revision_mode"] != "initial": _abort("fx_history_correction_stale")
                fx_day_ref = _id("fxd", [candidate["pair_ref"], row["rate_date"]]); fx_day_id = _id("fdi", fx_day_ref)
                revision_no = 1; supersedes_id = None; disposition = "appended"
            else:
                latest_retrieval = connection.execute(
                    "SELECT max(request.retrieved_at_utc) FROM fx_request_day_evidence evidence JOIN fx_history_request request USING(request_id) WHERE evidence.fx_day_id=?", (current["fx_day_id"],),
                ).fetchone()[0]
                if candidate["retrieved_at_utc"] <= latest_retrieval: _abort("fx_history_correction_stale")
                if row["revision_mode"] == "initial": _abort("fx_history_initial_exists")
                if row["supersedes_revision_ref"] != current["revision_ref"]: _abort("fx_history_correction_stale")
                fx_day_ref = current["fx_day_ref"]; fx_day_id = current["fx_day_id"]
                if row["revision_mode"] == "unchanged":
                    if any(row[field] != current[field] for field in _DOMAIN_FIELDS): _abort("fx_history_correction_stale")
                    plans.append({"ordinal": ordinal, "row": row, "fx_day_id": fx_day_id, "fx_day_ref": fx_day_ref, "revision_id": current["revision_id"], "revision_ref": current["revision_ref"], "new_entity": False, "new_revision": False, "disposition": "unchanged"})
                    counts["unchanged"] += 1; continue
                if all(row[field] == current[field] for field in ("day_status", "rate_decimal", "gap_reason")):
                    _abort("fx_history_domain_unchanged")
                revision_no = int(current["revision_no"]) + 1; supersedes_id = current["revision_id"]; disposition = "corrected"
            revision_ref = _id("fxv", [fx_day_ref, revision_no, row["source_day_fingerprint"], candidate["request_ref"]])
            plans.append({"ordinal": ordinal, "row": row, "fx_day_id": fx_day_id, "fx_day_ref": fx_day_ref, "revision_id": _id("fdr", revision_ref), "revision_ref": revision_ref, "revision_no": revision_no, "supersedes_id": supersedes_id, "new_entity": current is None, "new_revision": True, "disposition": disposition})
            counts[disposition] += 1
        row_set = _sha([{"rate_date": plan["row"]["rate_date"], "revision_ref": plan["revision_ref"], "disposition": plan["disposition"]} for plan in plans])
        receipt_body = {"request_ref": candidate["request_ref"], "candidate_fingerprint": candidate["candidate_fingerprint"], "appended_day_count": counts["appended"], "corrected_day_count": counts["corrected"], "unchanged_day_count": counts["unchanged"], "row_set_fingerprint": row_set}
        receipt_fingerprint = _sha(receipt_body); request_id = _id("fri", candidate["request_ref"])
        connection.execute(
            "INSERT INTO fx_history_request(request_id,request_ref,pair_id,source_kind,source_ref,source_version,plugin_id,plugin_version,plugin_manifest_fingerprint,request_fingerprint,job_binding_fingerprint,candidate_fingerprint,requested_start_date,requested_end_date,retrieved_at_utc,completed_at_utc,actor_id,appended_day_count,corrected_day_count,unchanged_day_count,row_set_fingerprint,receipt_fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (request_id, candidate["request_ref"], pair["pair_id"], candidate["source_kind"], candidate["source_ref"], candidate["source_version"], candidate["plugin_id"], candidate["plugin_version"], candidate["plugin_manifest_fingerprint"], candidate["request_fingerprint"], candidate["job_binding_fingerprint"], candidate["candidate_fingerprint"], candidate["requested_start_date"], candidate["requested_end_date"], candidate["retrieved_at_utc"], completed_at_utc, context.actor_id, counts["appended"], counts["corrected"], counts["unchanged"], row_set, receipt_fingerprint),
        )
        if failpoint == "after_request": raise RuntimeError("synthetic_failpoint")
        revision_seen = False
        for plan in plans:
            row = plan["row"]
            if plan["new_entity"]:
                connection.execute("INSERT INTO fx_day_entity VALUES (?,?,?,?,?,?)", (plan["fx_day_id"], plan["fx_day_ref"], pair["pair_id"], row["rate_date"], request_id, completed_at_utc))
            if plan["new_revision"]:
                revision_body = {"fx_day_ref": plan["fx_day_ref"], "revision_ref": plan["revision_ref"], "revision_no": plan["revision_no"], "domain": {field: row[field] for field in _DOMAIN_FIELDS}, "source_observation_ref": row["source_observation_ref"], "observed_at_utc": row["observed_at_utc"], "request_ref": candidate["request_ref"], "completed_at_utc": completed_at_utc}
                connection.execute(
                    "INSERT INTO fx_day_revision(revision_id,revision_ref,fx_day_id,revision_no,day_status,rate_decimal,quality_status,gap_reason,source_observation_ref,observed_at_utc,source_day_fingerprint,request_id,correction_reason,supersedes_revision_id,retrieved_at_utc,completed_at_utc,revision_fingerprint) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (plan["revision_id"], plan["revision_ref"], plan["fx_day_id"], plan["revision_no"], row["day_status"], row["rate_decimal"], row["quality_status"], row["gap_reason"], row["source_observation_ref"], row["observed_at_utc"], row["source_day_fingerprint"], request_id, row["correction_reason"], plan["supersedes_id"], candidate["retrieved_at_utc"], completed_at_utc, _sha(revision_body)),
                )
                if failpoint == "after_first_revision" and not revision_seen: raise RuntimeError("synthetic_failpoint")
                revision_seen = True
            connection.execute("INSERT INTO fx_request_day_evidence VALUES (?,?,?,?,?,?,?,?,?)", (_id("fde", [candidate["request_ref"], plan["ordinal"]]), request_id, plan["ordinal"], plan["fx_day_id"], plan["revision_id"], plan["disposition"], row["source_observation_ref"], row["observed_at_utc"], row["source_day_fingerprint"]))
        if failpoint == "before_commit": raise RuntimeError("synthetic_failpoint")
        connection.commit()
        return _receipt(connection.execute("SELECT * FROM fx_history_request WHERE request_ref=?", (candidate["request_ref"],)).fetchone(), False)
    except FxHistoryBlocked:
        connection.rollback(); raise
    except RuntimeError as exc:
        connection.rollback()
        if str(exc) == "synthetic_failpoint": raise FxHistoryBlocked("fx_history_synthetic_failpoint") from None
        raise FxHistoryBlocked("fx_history_boundary_failed") from exc
    except sqlite3.Error as exc:
        connection.rollback(); raise FxHistoryBlocked("fx_history_write_failed") from exc
    except Exception as exc:
        connection.rollback(); raise FxHistoryBlocked("fx_history_boundary_failed") from exc
    finally:
        connection.close()


def _read_pair(connection: sqlite3.Connection, pair_ref: str) -> sqlite3.Row:
    pair = connection.execute("SELECT * FROM fx_pair_binding WHERE pair_ref=?", (pair_ref,)).fetchone()
    if pair is None: _abort("fx_history_pair_missing")
    return pair


def read_fx_pair_catalog_v1(store_path: str | Path, context: FxHistoryContext | Mapping[str, str]) -> dict[str, Any]:
    context = _normalize_context(context)
    connection = _connect(store_path, context, read_only=True)
    try:
        rows = connection.execute(
            "SELECT pair_ref,base_currency,quote_currency,market_code,timezone_name,calendar_code,rate_type,pair_fingerprint FROM fx_pair_binding ORDER BY base_currency,quote_currency,market_code,rate_type,pair_ref"
        ).fetchall()
        body = {
            "contract_version": "fx_pair_catalog_v1", "status": "ready",
            "pairs": [dict(row) for row in rows], "pair_count": len(rows),
            "provider_access": False, "network_access": False,
            "automatic_pair_mapping": False, "canonical_write": False,
        }
        return {**body, "catalog_fingerprint": _sha(body)}
    finally:
        connection.close()


def read_fx_history_v1(store_path: str | Path, context: FxHistoryContext | Mapping[str, str], pair_ref: str, start_date: str, end_date: str) -> dict[str, Any]:
    context = _normalize_context(context); pair_ref = _ref(pair_ref, "fxp_")
    dates = _date_range(_day_date(start_date), _day_date(end_date))
    connection = _connect(store_path, context, read_only=True)
    try:
        pair = _read_pair(connection, pair_ref)
        rows = connection.execute(
            "SELECT entity.fx_day_ref,entity.rate_date,revision.*,request.source_kind,request.source_ref,request.source_version,request.plugin_id,request.plugin_version,request.plugin_manifest_fingerprint FROM fx_day_entity entity JOIN current_fx_day_revision revision USING(fx_day_id) JOIN fx_history_request request USING(request_id) WHERE entity.pair_id=? AND entity.rate_date BETWEEN ? AND ? ORDER BY entity.rate_date",
            (pair["pair_id"], start_date, end_date),
        ).fetchall(); by_date = {row["rate_date"]: row for row in rows}; output = []
        for rate_date in dates:
            row = by_date.get(rate_date)
            if row is None:
                output.append({"rate_date": rate_date, "day_status": "not_requested", "fx_day_ref": None, "revision_ref": None, "revision_no": None, "rate_decimal": None, "quality_status": "not_requested", "gap_reason": None, "source_kind": None, "source_ref": None, "source_version": None, "plugin_id": None, "plugin_version": None, "plugin_manifest_fingerprint": None, "source_observation_ref": None, "observed_at_utc": None, "retrieved_at_utc": None})
            else:
                output.append({key: row[key] for key in ("rate_date", "day_status", "fx_day_ref", "revision_ref", "revision_no", "rate_decimal", "quality_status", "gap_reason", "source_kind", "source_ref", "source_version", "plugin_id", "plugin_version", "plugin_manifest_fingerprint", "source_observation_ref", "observed_at_utc", "retrieved_at_utc")})
                output[-1]["revision_no"] = int(output[-1]["revision_no"])
        status = "empty" if all(row["day_status"] == "not_requested" for row in output) else "partial" if any(row["day_status"] in {"not_requested", "source_gap"} for row in output) else "completed"
        body = {"contract_version": "fx_history_read_model_v1", "status": status, "pair_ref": pair_ref, "base_currency": pair["base_currency"], "quote_currency": pair["quote_currency"], "market_code": pair["market_code"], "timezone_name": pair["timezone_name"], "calendar_code": pair["calendar_code"], "rate_type": pair["rate_type"], "range_start_date": start_date, "range_end_date": end_date, "days": output, "boundaries": {"provider_access": False, "network_access": False, "automatic_pair_mapping": False, "conversion_calculation": False, "canonical_write": False, "display_access": False}}
        return {**body, "row_set_fingerprint": _sha(body)}
    finally:
        connection.close()


def read_fx_revision_history_v1(store_path: str | Path, context: FxHistoryContext | Mapping[str, str], pair_ref: str, rate_date: str) -> dict[str, Any]:
    context = _normalize_context(context); pair_ref = _ref(pair_ref, "fxp_"); _day_date(rate_date)
    connection = _connect(store_path, context, read_only=True)
    try:
        pair = _read_pair(connection, pair_ref)
        rows = connection.execute("SELECT revision.revision_ref,revision.revision_no,revision.day_status,revision.rate_decimal,revision.quality_status,revision.gap_reason,revision.source_observation_ref,revision.observed_at_utc,revision.correction_reason,revision.retrieved_at_utc,revision.completed_at_utc,revision.revision_fingerprint FROM fx_day_entity entity JOIN fx_day_revision revision USING(fx_day_id) WHERE entity.pair_id=? AND entity.rate_date=? ORDER BY revision.revision_no", (pair["pair_id"], rate_date)).fetchall()
        return {"contract_version": "fx_revision_history_v1", "pair_ref": pair_ref, "rate_date": rate_date, "revisions": [dict(row) for row in rows], "provider_access": False, "network_access": False, "canonical_write": False}
    finally:
        connection.close()


def fx_conversion_job_binding_fingerprint_v1(context: FxHistoryContext | Mapping[str, str], *, conversion_scope_ref: str, target_currency: str, input_fingerprint: str, history_cutoff_at_utc: str) -> str:
    context = _normalize_context(context, writer=True)
    return _sha({"contract_version": "fx_conversion_job_binding_v1", "context_binding_fingerprint": fx_history_context_fingerprint_v1(context), "actor_id": context.actor_id, "role": context.role, "capability": "materialize_fx_conversion", "conversion_scope_ref": _ref(conversion_scope_ref, "fxc_", "fx_history_conversion_input_invalid"), "target_currency": _currency(target_currency, "fx_history_conversion_input_invalid"), "input_fingerprint": _fingerprint(input_fingerprint, "fx_history_conversion_input_invalid"), "history_cutoff_at_utc": history_cutoff_at_utc})


def new_fx_conversion_request_v1(context: FxHistoryContext | Mapping[str, str], *, conversion_scope_ref: str, target_currency: str, input_fingerprint: str, history_cutoff_at_utc: str, items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    context = _normalize_context(context, writer=True); _ref(conversion_scope_ref, "fxc_", "fx_history_conversion_input_invalid")
    target_currency = _currency(target_currency, "fx_history_conversion_input_invalid"); _fingerprint(input_fingerprint, "fx_history_conversion_input_invalid"); _utc(history_cutoff_at_utc, "fx_history_conversion_input_invalid")
    if not isinstance(items, Sequence) or isinstance(items, (str, bytes)) or not items:
        _abort("fx_history_conversion_input_invalid")
    normalized = []; seen = set()
    for raw in items:
        if not isinstance(raw, Mapping) or set(raw) != _ITEM_FIELDS:
            _abort("fx_history_conversion_input_invalid")
        item = dict(raw); item_ref = _ref(item["conversion_item_ref"], "fci_", "fx_history_conversion_input_invalid")
        if item_ref in seen: _abort("fx_history_conversion_input_invalid")
        seen.add(item_ref); _day_date(item["effective_date"]); _decimal_text(item["native_amount_decimal"], code="fx_history_conversion_input_invalid")
        native = _currency(item["native_currency"], "fx_history_conversion_input_invalid")
        if item["native_currency_role"] not in CURRENCY_ROLES:
            _abort("fx_history_conversion_input_invalid")
        if isinstance(item["output_scale"], bool) or not isinstance(item["output_scale"], int) or not 0 <= item["output_scale"] <= 18:
            _abort("fx_history_conversion_input_invalid")
        if item["route_kind"] not in ROUTE_KINDS or item["selection_policy"] not in SELECTION_POLICIES or isinstance(item["max_age_days"], bool) or not isinstance(item["max_age_days"], int) or not 0 <= item["max_age_days"] <= 366:
            _abort("fx_history_conversion_input_invalid")
        legs = item["legs"]
        if not isinstance(legs, list) or any(not isinstance(leg, dict) or set(leg) != _LEG_FIELDS or leg["direction"] not in DIRECTIONS for leg in legs):
            _abort("fx_history_conversion_input_invalid")
        for leg in legs: _ref(leg["pair_ref"], "fxp_", "fx_history_conversion_input_invalid")
        expected_count = {"identity": 0, "unsupported": 0, "direct": 1, "inverse": 1, "explicit_two_leg_chain": 2}[item["route_kind"]]
        if len(legs) != expected_count or item["route_kind"] == "identity" and native != target_currency or item["route_kind"] in {"unsupported", "direct", "inverse", "explicit_two_leg_chain"} and native == target_currency:
            _abort("fx_history_conversion_input_invalid")
        if item["route_kind"] == "direct" and legs[0]["direction"] != "direct" or item["route_kind"] == "inverse" and legs[0]["direction"] != "inverse":
            _abort("fx_history_conversion_input_invalid")
        if item["selection_policy"] == "exact_date" and (item["max_age_days"] != 0):
            _abort("fx_history_conversion_input_invalid")
        normalized.append(item)
    job = fx_conversion_job_binding_fingerprint_v1(context, conversion_scope_ref=conversion_scope_ref, target_currency=target_currency, input_fingerprint=input_fingerprint, history_cutoff_at_utc=history_cutoff_at_utc)
    body = {"contract_version": "fx_conversion_request_v1", "conversion_scope_ref": conversion_scope_ref, "target_currency": target_currency, "algorithm_version": ALGORITHM_VERSION, "rounding_mode": "half_even_v1", "input_fingerprint": input_fingerprint, "history_cutoff_at_utc": history_cutoff_at_utc, "job_binding_fingerprint": job, "items": normalized}
    return {**body, "request_fingerprint": _sha(body)}


def _conversion_request(value: Any, context: FxHistoryContext | Mapping[str, str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _REQUEST_FIELDS or value.get("contract_version") != "fx_conversion_request_v1" or value.get("algorithm_version") != ALGORITHM_VERSION or value.get("rounding_mode") != "half_even_v1":
        _abort("fx_history_conversion_input_invalid")
    rebuilt = new_fx_conversion_request_v1(context, conversion_scope_ref=value["conversion_scope_ref"], target_currency=value["target_currency"], input_fingerprint=value["input_fingerprint"], history_cutoff_at_utc=value["history_cutoff_at_utc"], items=value["items"])
    if rebuilt != value: _abort("fx_history_job_binding_invalid")
    return rebuilt


def _as_of_day(connection: sqlite3.Connection, pair_id: str, rate_date: str, cutoff: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT entity.rate_date,revision.*,request.source_kind,request.source_ref,request.source_version,request.plugin_id,request.plugin_version,request.plugin_manifest_fingerprint,pair.pair_ref,pair.base_currency,pair.quote_currency,pair.market_code,pair.rate_type FROM fx_day_entity entity JOIN fx_pair_binding pair USING(pair_id) JOIN fx_day_revision revision USING(fx_day_id) JOIN fx_history_request request USING(request_id) WHERE entity.pair_id=? AND entity.rate_date=? AND revision.completed_at_utc<=? ORDER BY revision.revision_no DESC LIMIT 1",
        (pair_id, rate_date, cutoff),
    ).fetchone()


def _select_rate(connection: sqlite3.Connection, pair: sqlite3.Row, effective_date: str, cutoff: str, policy: str, max_age: int) -> tuple[str, sqlite3.Row | None, int | None, str]:
    exact = _as_of_day(connection, pair["pair_id"], effective_date, cutoff)
    effective_day_status = "not_requested" if exact is None else exact["day_status"]
    if policy == "exact_date":
        if exact is None: return "missing_observation", None, None, effective_day_status
        if exact["day_status"] == "source_gap": return "source_gap", exact, None, effective_day_status
        if exact["day_status"] == "non_trading_day": return "non_trading_day", exact, None, effective_day_status
        return "completed", exact, 0, effective_day_status
    row = connection.execute(
        "SELECT entity.rate_date,revision.*,request.source_kind,request.source_ref,request.source_version,request.plugin_id,request.plugin_version,request.plugin_manifest_fingerprint,pair.pair_ref,pair.base_currency,pair.quote_currency,pair.market_code,pair.rate_type FROM fx_day_entity entity JOIN fx_pair_binding pair USING(pair_id) JOIN fx_day_revision revision USING(fx_day_id) JOIN fx_history_request request USING(request_id) WHERE entity.pair_id=? AND entity.rate_date<=? AND revision.completed_at_utc<=? AND revision.day_status='observed' AND revision.revision_no=(SELECT max(candidate.revision_no) FROM fx_day_revision candidate WHERE candidate.fx_day_id=entity.fx_day_id AND candidate.completed_at_utc<=?) ORDER BY entity.rate_date DESC LIMIT 1",
        (pair["pair_id"], effective_date, cutoff, cutoff),
    ).fetchone()
    if row is None:
        if exact is not None and exact["day_status"] == "source_gap": return "source_gap", exact, None, effective_day_status
        if exact is not None and exact["day_status"] == "non_trading_day": return "non_trading_day", exact, None, effective_day_status
        return "missing_observation", None, None, effective_day_status
    age = (_day_date(effective_date) - _day_date(row["rate_date"])).days
    if age > max_age: return "stale_rate", row, age, effective_day_status
    return "completed", row, age, effective_day_status


def _leg_evidence(row: sqlite3.Row, direction: str, age: int, effective_date: str, effective_day_status: str) -> dict[str, Any]:
    rate = _fraction_from_decimal(row["rate_decimal"])
    factor = rate if direction == "direct" else 1 / rate
    return {"pair_ref": row["pair_ref"], "base_currency": row["base_currency"], "quote_currency": row["quote_currency"], "direction": direction, "rate_date": row["rate_date"], "rate_decimal": row["rate_decimal"], "factor_numerator": str(factor.numerator), "factor_denominator": str(factor.denominator), "rate_age_days": age, "selection_basis": "exact_date" if row["rate_date"] == effective_date else "prior_observation", "effective_day_status": effective_day_status, "revision_ref": row["revision_ref"], "revision_fingerprint": row["revision_fingerprint"], "observed_at_utc": row["observed_at_utc"], "quality_status": row["quality_status"], "source_kind": row["source_kind"], "source_ref": row["source_ref"], "source_version": row["source_version"], "plugin_id": row["plugin_id"], "plugin_version": row["plugin_version"], "plugin_manifest_fingerprint": row["plugin_manifest_fingerprint"]}


def materialize_fx_conversion_v1(store_path: str | Path, context: FxHistoryContext | Mapping[str, str], request: Mapping[str, Any], *, mode: str = "full", previous_artifact: Mapping[str, Any] | None = None) -> dict[str, Any]:
    context = _normalize_context(context, writer=True); request = _conversion_request(dict(request), context)
    if mode not in {"full", "incremental"} or mode == "full" and previous_artifact is not None:
        _abort("fx_history_conversion_input_invalid")
    previous_by_ref = {}
    if mode == "incremental":
        if previous_artifact is None:
            _abort("fx_history_conversion_input_invalid")
        previous = _validate_artifact(dict(previous_artifact), context)
        if previous["conversion_scope_ref"] != request["conversion_scope_ref"] or previous["target_currency"] != request["target_currency"]:
            _abort("fx_history_conversion_input_invalid")
        previous_by_ref = {row["conversion_item_ref"]: row for row in previous["items"]}
    connection = _connect(store_path, context, read_only=True)
    try:
        output = []; reused = 0
        for item in request["items"]:
            item_input_fingerprint = _sha(item)
            base = {"conversion_item_ref": item["conversion_item_ref"], "effective_date": item["effective_date"], "native_amount_decimal": item["native_amount_decimal"], "native_currency": item["native_currency"], "native_currency_role": item["native_currency_role"], "target_currency": request["target_currency"], "output_scale": item["output_scale"], "route_kind": item["route_kind"], "selection_policy": item["selection_policy"], "max_age_days": item["max_age_days"], "item_input_fingerprint": item_input_fingerprint, "route_legs": item["legs"]}
            if item["route_kind"] == "identity":
                rounded_native = _round_fraction(_fraction_from_decimal(item["native_amount_decimal"]), item["output_scale"])
                result = {**base, "conversion_status": "native", "converted_amount_decimal": rounded_native, "effective_rate_numerator": "1", "effective_rate_denominator": "1", "legs": []}
            elif item["route_kind"] == "unsupported":
                result = {**base, "conversion_status": "unsupported_pair", "converted_amount_decimal": None, "effective_rate_numerator": None, "effective_rate_denominator": None, "legs": []}
            else:
                current_currency = item["native_currency"]; factor = Fraction(1); legs = []; unavailable = None
                for leg in item["legs"]:
                    pair = connection.execute("SELECT * FROM fx_pair_binding WHERE pair_ref=?", (leg["pair_ref"],)).fetchone()
                    if pair is None:
                        unavailable = "unsupported_pair"; break
                    source_currency = pair["base_currency"] if leg["direction"] == "direct" else pair["quote_currency"]
                    next_currency = pair["quote_currency"] if leg["direction"] == "direct" else pair["base_currency"]
                    if current_currency != source_currency:
                        _abort("fx_history_conversion_route_invalid")
                    selection_status, selected, age, effective_day_status = _select_rate(connection, pair, item["effective_date"], request["history_cutoff_at_utc"], item["selection_policy"], item["max_age_days"])
                    if selection_status != "completed":
                        if selection_status == "stale_rate" and selected is not None and age is not None:
                            legs.append(_leg_evidence(selected, leg["direction"], int(age), item["effective_date"], effective_day_status))
                        unavailable = selection_status; break
                    evidence = _leg_evidence(selected, leg["direction"], int(age), item["effective_date"], effective_day_status); legs.append(evidence)
                    factor *= Fraction(int(evidence["factor_numerator"]), int(evidence["factor_denominator"])); current_currency = next_currency
                if unavailable is None and current_currency != request["target_currency"]:
                    _abort("fx_history_conversion_route_invalid")
                if unavailable is not None:
                    result = {**base, "conversion_status": unavailable, "converted_amount_decimal": None, "effective_rate_numerator": None, "effective_rate_denominator": None, "legs": legs}
                else:
                    converted = _fraction_from_decimal(item["native_amount_decimal"]) * factor
                    result = {**base, "conversion_status": "completed", "converted_amount_decimal": _round_fraction(converted, item["output_scale"]), "effective_rate_numerator": str(factor.numerator), "effective_rate_denominator": str(factor.denominator), "legs": legs}
            result["rate_evidence_fingerprint"] = _sha(result["legs"])
            result["result_fingerprint"] = _sha(result)
            previous_row = previous_by_ref.get(item["conversion_item_ref"])
            if previous_row is not None and previous_row.get("item_input_fingerprint") == result["item_input_fingerprint"] and previous_row.get("rate_evidence_fingerprint") == result["rate_evidence_fingerprint"] and previous_row.get("result_fingerprint") == result["result_fingerprint"]:
                result = previous_row; reused += 1
            output.append(result)
        row_set = _sha(output); statuses = [row["conversion_status"] for row in output]
        result_status = "no_conversion_required" if all(status == "native" for status in statuses) else "complete" if all(status in {"native", "completed"} for status in statuses) else "partial"
        body = {"contract_version": "fx_conversion_artifact_v1", "status": "completed", "result_status": result_status, "conversion_scope_ref": request["conversion_scope_ref"], "target_currency": request["target_currency"], "algorithm_version": request["algorithm_version"], "rounding_mode": request["rounding_mode"], "input_fingerprint": request["input_fingerprint"], "history_cutoff_at_utc": request["history_cutoff_at_utc"], "context_binding_fingerprint": fx_history_context_fingerprint_v1(context), "request_fingerprint": request["request_fingerprint"], "items": output, "reconciliation": {"item_count": len(output), "converted_item_count": sum(status == "completed" for status in statuses), "native_item_count": sum(status == "native" for status in statuses), "unavailable_item_count": sum(status not in {"completed", "native"} for status in statuses), "reused_item_count": reused, "execution_mode": mode}, "boundaries": {"provider_access": False, "network_access": False, "automatic_route_selection": False, "current_rate_substitution": False, "binary_float_arithmetic": False, "ui_calculation": False, "canonical_write": False}, "row_set_fingerprint": row_set}
        return {**body, "artifact_fingerprint": _sha(body)}
    finally:
        connection.close()


def _validate_artifact(value: dict[str, Any], context: FxHistoryContext | Mapping[str, str]) -> dict[str, Any]:
    required = {
        "contract_version", "status", "result_status", "conversion_scope_ref", "target_currency",
        "algorithm_version", "rounding_mode", "input_fingerprint", "history_cutoff_at_utc",
        "context_binding_fingerprint", "request_fingerprint", "items", "reconciliation",
        "boundaries", "row_set_fingerprint", "artifact_fingerprint",
    }
    try:
        if (
            set(value) != required or value.get("contract_version") != "fx_conversion_artifact_v1"
            or value.get("status") != "completed" or value.get("algorithm_version") != ALGORITHM_VERSION
            or value.get("rounding_mode") != "half_even_v1"
        ):
            _abort("fx_history_artifact_invalid")
        _ref(value["conversion_scope_ref"], "fxc_", "fx_history_artifact_invalid")
        target_currency = _currency(value["target_currency"], "fx_history_artifact_invalid")
        _utc(value["history_cutoff_at_utc"], "fx_history_artifact_invalid")
        for key in ("input_fingerprint", "context_binding_fingerprint", "request_fingerprint", "row_set_fingerprint", "artifact_fingerprint"):
            _fingerprint(value[key], "fx_history_artifact_invalid")
        if not isinstance(value["items"], list) or not value["items"]:
            _abort("fx_history_artifact_invalid")
        seen = set(); statuses = []
        for row in value["items"]:
            if not isinstance(row, dict) or set(row) != _RESULT_FIELDS:
                _abort("fx_history_artifact_invalid")
            item_ref = _ref(row["conversion_item_ref"], "fci_", "fx_history_artifact_invalid")
            if item_ref in seen:
                _abort("fx_history_artifact_invalid")
            seen.add(item_ref); _day_date(row["effective_date"])
            _decimal_text(row["native_amount_decimal"], code="fx_history_artifact_invalid")
            native_currency = _currency(row["native_currency"], "fx_history_artifact_invalid")
            if row["native_currency_role"] not in CURRENCY_ROLES:
                _abort("fx_history_artifact_invalid")
            if _currency(row["target_currency"], "fx_history_artifact_invalid") != target_currency:
                _abort("fx_history_artifact_invalid")
            if isinstance(row["output_scale"], bool) or not isinstance(row["output_scale"], int) or not 0 <= row["output_scale"] <= 18:
                _abort("fx_history_artifact_invalid")
            if row["route_kind"] not in ROUTE_KINDS or row["selection_policy"] not in SELECTION_POLICIES:
                _abort("fx_history_artifact_invalid")
            if isinstance(row["max_age_days"], bool) or not isinstance(row["max_age_days"], int) or not 0 <= row["max_age_days"] <= 366:
                _abort("fx_history_artifact_invalid")
            if not isinstance(row["route_legs"], list) or any(not isinstance(leg, dict) or set(leg) != _LEG_FIELDS or leg.get("direction") not in DIRECTIONS for leg in row["route_legs"]):
                _abort("fx_history_artifact_invalid")
            for route_leg in row["route_legs"]:
                _ref(route_leg["pair_ref"], "fxp_", "fx_history_artifact_invalid")
            expected_route_count = {"identity": 0, "unsupported": 0, "direct": 1, "inverse": 1, "explicit_two_leg_chain": 2}[row["route_kind"]]
            if len(row["route_legs"]) != expected_route_count:
                _abort("fx_history_artifact_invalid")
            if row["route_kind"] == "direct" and row["route_legs"][0]["direction"] != "direct" or row["route_kind"] == "inverse" and row["route_legs"][0]["direction"] != "inverse":
                _abort("fx_history_artifact_invalid")
            original_item = {
                "conversion_item_ref": row["conversion_item_ref"], "effective_date": row["effective_date"],
                "native_amount_decimal": row["native_amount_decimal"], "native_currency": row["native_currency"],
                "native_currency_role": row["native_currency_role"], "output_scale": row["output_scale"], "route_kind": row["route_kind"],
                "selection_policy": row["selection_policy"], "max_age_days": row["max_age_days"],
                "legs": row["route_legs"],
            }
            if row["item_input_fingerprint"] != _sha(original_item):
                _abort("fx_history_artifact_invalid")
            if not isinstance(row["legs"], list) or len(row["legs"]) > len(row["route_legs"]):
                _abort("fx_history_artifact_invalid")
            current_currency = native_currency; effective_factor = Fraction(1)
            for index, leg in enumerate(row["legs"]):
                if not isinstance(leg, dict) or set(leg) != _RESULT_LEG_FIELDS:
                    _abort("fx_history_artifact_invalid")
                if leg["pair_ref"] != row["route_legs"][index]["pair_ref"] or leg["direction"] != row["route_legs"][index]["direction"]:
                    _abort("fx_history_artifact_invalid")
                _ref(leg["pair_ref"], "fxp_", "fx_history_artifact_invalid")
                base_currency = _currency(leg["base_currency"], "fx_history_artifact_invalid")
                quote_currency = _currency(leg["quote_currency"], "fx_history_artifact_invalid")
                _day_date(leg["rate_date"]); rate = _fraction_from_decimal(_decimal_text(leg["rate_decimal"], positive=True, code="fx_history_artifact_invalid"))
                if not isinstance(leg["factor_numerator"], str) or re.fullmatch(r"[1-9][0-9]*", leg["factor_numerator"]) is None or not isinstance(leg["factor_denominator"], str) or re.fullmatch(r"[1-9][0-9]*", leg["factor_denominator"]) is None:
                    _abort("fx_history_artifact_invalid")
                factor = rate if leg["direction"] == "direct" else 1 / rate
                if factor != Fraction(int(leg["factor_numerator"]), int(leg["factor_denominator"])):
                    _abort("fx_history_artifact_invalid")
                source_currency = base_currency if leg["direction"] == "direct" else quote_currency
                next_currency = quote_currency if leg["direction"] == "direct" else base_currency
                if current_currency != source_currency:
                    _abort("fx_history_artifact_invalid")
                age = (_day_date(row["effective_date"]) - _day_date(leg["rate_date"])).days
                if isinstance(leg["rate_age_days"], bool) or leg["rate_age_days"] != age or not 0 <= age <= MAX_RATE_AGE_DAYS:
                    _abort("fx_history_artifact_invalid")
                expected_basis = "exact_date" if leg["rate_date"] == row["effective_date"] else "prior_observation"
                if leg["selection_basis"] != expected_basis or leg["effective_day_status"] not in {"observed", "non_trading_day", "source_gap", "not_requested"}:
                    _abort("fx_history_artifact_invalid")
                _ref(leg["revision_ref"], "fxv_", "fx_history_artifact_invalid")
                _fingerprint(leg["revision_fingerprint"], "fx_history_artifact_invalid")
                _utc(leg["observed_at_utc"], "fx_history_artifact_invalid")
                if leg["quality_status"] not in {"complete", "corrected"} or leg["source_kind"] not in SOURCE_KINDS:
                    _abort("fx_history_artifact_invalid")
                _ref(leg["source_ref"], "fxs_", "fx_history_artifact_invalid")
                if not isinstance(leg["source_version"], str) or not 3 <= len(leg["source_version"]) <= 80 or _TOKEN.fullmatch(leg["source_version"]) is None:
                    _abort("fx_history_artifact_invalid")
                plugin_values = (leg["plugin_id"], leg["plugin_version"], leg["plugin_manifest_fingerprint"])
                if leg["source_kind"] == "market_plugin":
                    if not isinstance(plugin_values[0], str) or _PLUGIN.fullmatch(plugin_values[0]) is None or not isinstance(plugin_values[1], str) or _TOKEN.fullmatch(plugin_values[1]) is None:
                        _abort("fx_history_artifact_invalid")
                    _fingerprint(plugin_values[2], "fx_history_artifact_invalid")
                elif any(item is not None for item in plugin_values):
                    _abort("fx_history_artifact_invalid")
                current_currency = next_currency; effective_factor *= factor
            if row["rate_evidence_fingerprint"] != _sha(row["legs"]):
                _abort("fx_history_artifact_invalid")
            result_body = dict(row); result_fingerprint = result_body.pop("result_fingerprint")
            if result_fingerprint != _sha(result_body):
                _abort("fx_history_artifact_invalid")
            status = row["conversion_status"]
            if status not in {"completed", "native", "non_trading_day", "source_gap", "missing_observation", "stale_rate", "unsupported_pair"}:
                _abort("fx_history_artifact_invalid")
            statuses.append(status)
            if status == "native":
                rounded_native = _round_fraction(_fraction_from_decimal(row["native_amount_decimal"]), row["output_scale"])
                if row["route_kind"] != "identity" or native_currency != target_currency or row["converted_amount_decimal"] != rounded_native or row["effective_rate_numerator"] != "1" or row["effective_rate_denominator"] != "1" or row["legs"]:
                    _abort("fx_history_artifact_invalid")
            elif status == "completed":
                if len(row["legs"]) != expected_route_count or current_currency != target_currency or _decimal_text(row["converted_amount_decimal"], code="fx_history_artifact_invalid") != _round_fraction(_fraction_from_decimal(row["native_amount_decimal"]) * effective_factor, row["output_scale"]):
                    _abort("fx_history_artifact_invalid")
                if row["effective_rate_numerator"] != str(effective_factor.numerator) or row["effective_rate_denominator"] != str(effective_factor.denominator):
                    _abort("fx_history_artifact_invalid")
                if any(leg["rate_age_days"] > row["max_age_days"] for leg in row["legs"]):
                    _abort("fx_history_artifact_invalid")
            elif row["converted_amount_decimal"] is not None or row["effective_rate_numerator"] is not None or row["effective_rate_denominator"] is not None:
                _abort("fx_history_artifact_invalid")
            if status == "unsupported_pair" and row["route_kind"] == "identity" or status == "stale_rate" and (not row["legs"] or row["legs"][-1]["rate_age_days"] <= row["max_age_days"]):
                _abort("fx_history_artifact_invalid")
        expected_status = "no_conversion_required" if all(status == "native" for status in statuses) else "complete" if all(status in {"native", "completed"} for status in statuses) else "partial"
        if value["result_status"] != expected_status:
            _abort("fx_history_artifact_invalid")
        reconciliation = value["reconciliation"]
        if not isinstance(reconciliation, dict) or set(reconciliation) != {"item_count", "converted_item_count", "native_item_count", "unavailable_item_count", "reused_item_count", "execution_mode"}:
            _abort("fx_history_artifact_invalid")
        expected_counts = (len(statuses), sum(status == "completed" for status in statuses), sum(status == "native" for status in statuses), sum(status not in {"completed", "native"} for status in statuses))
        actual_counts = tuple(reconciliation[key] for key in ("item_count", "converted_item_count", "native_item_count", "unavailable_item_count"))
        if actual_counts != expected_counts or reconciliation["execution_mode"] not in {"full", "incremental"} or isinstance(reconciliation["reused_item_count"], bool) or not isinstance(reconciliation["reused_item_count"], int) or not 0 <= reconciliation["reused_item_count"] <= len(statuses):
            _abort("fx_history_artifact_invalid")
        expected_boundaries = {"provider_access": False, "network_access": False, "automatic_route_selection": False, "current_rate_substitution": False, "binary_float_arithmetic": False, "ui_calculation": False, "canonical_write": False}
        if value["boundaries"] != expected_boundaries or value["row_set_fingerprint"] != _sha(value["items"]):
            _abort("fx_history_artifact_invalid")
        artifact_fingerprint = value["artifact_fingerprint"]; body = dict(value); body.pop("artifact_fingerprint")
        if artifact_fingerprint != _sha(body):
            _abort("fx_history_artifact_invalid")
    except FxHistoryBlocked as error:
        if error.code == "fx_history_artifact_context_mismatch":
            raise
        if error.code != "fx_history_artifact_invalid":
            raise FxHistoryBlocked("fx_history_artifact_invalid") from None
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        raise FxHistoryBlocked("fx_history_artifact_invalid") from None
    if value["context_binding_fingerprint"] != fx_history_context_fingerprint_v1(context):
        _abort("fx_history_artifact_context_mismatch")
    return value


def _fsync_directory(path: Path, code: str) -> None:
    descriptor = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        os.fsync(descriptor)
    except OSError as exc:
        raise FxHistoryBlocked(code) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _atomic_artifact_no_replace(target: Path, payload: bytes) -> Path:
    descriptor = None; staging: Path | None = None
    try:
        descriptor, staging_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        staging = Path(staging_name); os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None; handle.write(payload); handle.flush(); os.fsync(handle.fileno())
        os.link(staging, target, follow_symlinks=False)
        staging.unlink(); staging = None
        _fsync_directory(target.parent, "fx_history_artifact_invalid")
        return target
    except FileExistsError:
        _abort("fx_history_artifact_exists")
    except FxHistoryBlocked:
        raise
    except Exception as exc:
        raise FxHistoryBlocked("fx_history_artifact_invalid") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if staging is not None and staging.exists() and not staging.is_symlink():
            staging.unlink()


def _exact_artifact_replay(path: str | Path, artifact: Mapping[str, Any], context: FxHistoryContext) -> Path:
    existing = read_fx_conversion_artifact_v1(path, context)
    if existing != artifact:
        _abort("fx_history_artifact_exists")
    return _regular_path(path, artifact=True)


def validate_fx_conversion_artifact_v1(artifact: Mapping[str, Any], context: FxHistoryContext | Mapping[str, str]) -> dict[str, Any]:
    context = _normalize_context(context)
    return _validate_artifact(dict(artifact), context)


def publish_fx_conversion_artifact_v1(artifact: Mapping[str, Any], context: FxHistoryContext | Mapping[str, str], output_path: str | Path) -> Path:
    context = _normalize_context(context, writer=True); artifact = _validate_artifact(dict(artifact), context)
    try:
        target = _regular_path(output_path, new=True, artifact=True)
    except FxHistoryBlocked as error:
        if error.code != "fx_history_artifact_exists":
            raise
        return _exact_artifact_replay(output_path, artifact, context)
    payload = (_canonical(artifact) + "\n").encode("utf-8")
    try:
        return _atomic_artifact_no_replace(target, payload)
    except FxHistoryBlocked as error:
        if error.code != "fx_history_artifact_exists":
            raise
        return _exact_artifact_replay(output_path, artifact, context)


def read_fx_conversion_artifact_v1(path: str | Path, context: FxHistoryContext | Mapping[str, str], *, browser_safe: bool = False) -> dict[str, Any]:
    context = _normalize_context(context)
    if context.role in {"viewer", "tax_viewer", "analysis_viewer"} and not browser_safe:
        _abort("fx_history_context_invalid")
    source = _regular_path(path, artifact=True)
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FxHistoryBlocked("fx_history_artifact_invalid") from exc
    artifact = _validate_artifact(value, context)
    if not browser_safe: return artifact
    return {"status": artifact["status"], "result_status": artifact["result_status"], "target_currency": artifact["target_currency"], "items": [{"effective_date": row["effective_date"], "native_amount_decimal": row["native_amount_decimal"], "native_currency": row["native_currency"], "native_currency_role": row["native_currency_role"], "display_amount_decimal": row["converted_amount_decimal"], "display_currency": row["target_currency"], "conversion_status": row["conversion_status"], "route_kind": row["route_kind"], "rate_dates": [leg["rate_date"] for leg in row["legs"]], "rate_age_days": [leg["rate_age_days"] for leg in row["legs"]], "selection_bases": [leg["selection_basis"] for leg in row["legs"]], "effective_day_statuses": [leg["effective_day_status"] for leg in row["legs"]], "quality_statuses": [leg["quality_status"] for leg in row["legs"]]} for row in artifact["items"]], "boundaries": {"filesystem_authority": False, "sql_authority": False, "write_authority": False, "provider_access": False, "network_access": False, "fx_calculation": False}}


def _csv_bytes(fieldnames: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> bytes:
    stream = io.StringIO(newline=""); writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        normalized = {key: "" if row.get(key) is None else str(row.get(key)).lower() if isinstance(row.get(key), bool) else str(row.get(key)) for key in fieldnames}
        if any("\n" in value or "\r" in value or value.startswith(("=", "+", "@")) for value in normalized.values()):
            _abort("fx_history_evidence_invalid")
        writer.writerow(normalized)
    return stream.getvalue().encode("utf-8")


def _exact_evidence_replay(target: Path, expected: Mapping[str, bytes]) -> Path:
    try:
        directory = _owner_only_directory(target)
        children = {child.name: child for child in directory.iterdir()}
        if set(children) != set(expected):
            _abort("fx_history_evidence_exists")
        for name, payload in expected.items():
            source = _regular_path(children[name])
            if source.read_bytes() != payload:
                _abort("fx_history_evidence_exists")
        return directory
    except FxHistoryBlocked as error:
        if error.code == "fx_history_evidence_exists":
            raise
        raise FxHistoryBlocked("fx_history_evidence_invalid") from None
    except (OSError, KeyError) as exc:
        raise FxHistoryBlocked("fx_history_evidence_invalid") from exc


def _write_fsynced_file(path: Path, payload: bytes, code: str) -> None:
    descriptor = None
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None; handle.write(payload); handle.flush(); os.fsync(handle.fileno())
    except Exception as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise FxHistoryBlocked(code) from exc


def publish_fx_conversion_evidence_v1(artifact: Mapping[str, Any], context: FxHistoryContext | Mapping[str, str], output_directory: str | Path) -> Path:
    context = _normalize_context(context)
    if context.role in {"viewer", "tax_viewer", "analysis_viewer"}:
        _abort("fx_history_context_invalid")
    artifact = _validate_artifact(dict(artifact), context)
    target = Path(output_directory)
    parent = _owner_only_directory(target.parent); target = parent / target.name
    files: dict[str, bytes] = {}
    files["fx-conversions.csv"] = _csv_bytes(("effective_date", "native_amount_decimal", "native_currency", "native_currency_role", "target_currency", "converted_amount_decimal", "conversion_status", "route_kind", "output_scale"), artifact["items"])
    rate_rows = []
    for item in artifact["items"]:
        for ordinal, leg in enumerate(item["legs"], 1):
            rate_rows.append({"effective_date": item["effective_date"], "leg_ordinal": ordinal, "base_currency": leg["base_currency"], "quote_currency": leg["quote_currency"], "direction": leg["direction"], "rate_date": leg["rate_date"], "rate_decimal": leg["rate_decimal"], "rate_age_days": leg["rate_age_days"], "selection_basis": leg["selection_basis"], "effective_day_status": leg["effective_day_status"], "quality_status": leg["quality_status"], "source_kind": leg["source_kind"]})
    files["fx-rates.csv"] = _csv_bytes(("effective_date", "leg_ordinal", "base_currency", "quote_currency", "direction", "rate_date", "rate_decimal", "rate_age_days", "selection_basis", "effective_day_status", "quality_status", "source_kind"), rate_rows)
    recon = artifact["reconciliation"]
    files["fx-reconciliation.csv"] = _csv_bytes(("result_status", "item_count", "converted_item_count", "native_item_count", "unavailable_item_count", "row_set_fingerprint"), [{"result_status": artifact["result_status"], "item_count": recon["item_count"], "converted_item_count": recon["converted_item_count"], "native_item_count": recon["native_item_count"], "unavailable_item_count": recon["unavailable_item_count"], "row_set_fingerprint": artifact["row_set_fingerprint"]}])
    roles = {
        "fx-conversions.csv": "normative_conversion_results",
        "fx-rates.csv": "normative_rate_selection",
        "fx-reconciliation.csv": "normative_result_reconciliation",
    }
    manifest_body = {
        "calculation_evidence_version": "1.2", "profile_id": "fx_conversion_v1",
        "status": "completed", "scope_kind": "fx_conversion",
        "scope_ref": artifact["conversion_scope_ref"], "target_currency": artifact["target_currency"],
        "algorithm_version": artifact["algorithm_version"],
        "context_binding_fingerprint": artifact["context_binding_fingerprint"],
        "input_fingerprint": artifact["input_fingerprint"],
        "history_cutoff_at_utc": artifact["history_cutoff_at_utc"],
        "files": [{
            "file_name": name, "content_role": roles[name],
            "row_count": len(payload.decode("utf-8").splitlines()) - 1, "sha256": _sha(payload),
        } for name, payload in sorted(files.items())],
        "reconciliation": {
            "result_status": artifact["result_status"],
            "item_count": artifact["reconciliation"]["item_count"],
            "converted_item_count": artifact["reconciliation"]["converted_item_count"],
            "native_item_count": artifact["reconciliation"]["native_item_count"],
            "unavailable_item_count": artifact["reconciliation"]["unavailable_item_count"],
            "row_set_fingerprint": artifact["row_set_fingerprint"],
        },
        "boundaries": {
            "provider_access": False, "network_access": False, "canonical_write": False,
            "app_side_calculation": False, "automatic_route_selection": False,
            "reimport_authorized": False,
        },
    }
    manifest = {**manifest_body, "evidence_fingerprint": _sha(manifest_body)}
    bundle = {**files, "evidence-manifest.json": (_canonical(manifest) + "\n").encode("utf-8")}
    if target.exists() or target.is_symlink():
        return _exact_evidence_replay(target, bundle)
    staging: Path | None = None
    try:
        staging = Path(tempfile.mkdtemp(prefix=f".{target.name}.", suffix=".tmp", dir=parent))
        os.chmod(staging, 0o700)
        for name, payload in bundle.items():
            _write_fsynced_file(staging / name, payload, "fx_history_evidence_invalid")
        _fsync_directory(staging, "fx_history_evidence_invalid")
        try:
            os.rename(staging, target)
        except OSError:
            if target.exists() or target.is_symlink():
                return _exact_evidence_replay(target, bundle)
            raise
        staging = None
        _fsync_directory(parent, "fx_history_evidence_invalid")
        return target
    except FxHistoryBlocked:
        raise
    except Exception as exc:
        raise FxHistoryBlocked("fx_history_evidence_invalid") from exc
    finally:
        if staging is not None and staging.exists() and not staging.is_symlink():
            for child in staging.iterdir():
                if child.is_file() and not child.is_symlink(): child.unlink()
            staging.rmdir()


def new_fx_conversion_worker_job_v1(
    context: FxHistoryContext | Mapping[str, str], *, store_path: str | Path,
    request: Mapping[str, Any], output_path: str | Path, mode: str = "full",
    previous_artifact_path: str | Path | None = None,
    evidence_output_path: str | Path | None = None, created_at_utc: str,
) -> dict[str, Any]:
    context = _normalize_context(context, writer=True)
    request = _conversion_request(dict(request), context)
    created = _utc(created_at_utc, "fx_history_job_invalid")
    if created < _utc(request["history_cutoff_at_utc"], "fx_history_job_invalid"):
        _abort("fx_history_job_invalid")
    if mode not in {"full", "incremental"} or mode == "full" and previous_artifact_path is not None or mode == "incremental" and previous_artifact_path is None:
        _abort("fx_history_job_invalid")
    def job_path(value: str | Path | None, *, nullable: bool = False) -> str | None:
        if value is None and nullable:
            return None
        if not isinstance(value, (str, Path)):
            _abort("fx_history_job_invalid")
        text = str(value)
        if not text.startswith("/") or "\x00" in text or len(text) > 4096:
            _abort("fx_history_job_invalid")
        return text
    body = {
        "contract_version": "fx_conversion_worker_job_v1",
        "context": {
            "tenant_id": context.tenant_id, "user_id": context.user_id,
            "data_space_id": context.data_space_id, "actor_id": context.actor_id,
            "role": context.role,
        },
        "store_path": job_path(store_path), "request": request,
        "output_path": job_path(output_path), "mode": mode,
        "previous_artifact_path": job_path(previous_artifact_path, nullable=True),
        "evidence_output_path": job_path(evidence_output_path, nullable=True),
        "created_at_utc": created_at_utc,
    }
    return {**body, "job_fingerprint": _sha(body)}


def load_fx_conversion_worker_job_v1(path: str | Path) -> dict[str, Any]:
    try:
        source = Path(path)
        absolute = Path(os.path.abspath(source))
        resolved = source.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, TypeError, ValueError) as exc:
        raise FxHistoryBlocked("fx_history_job_invalid") from exc
    wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
    if absolute != resolved or source.is_symlink() or not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or wrong_owner or metadata.st_size > 2_000_000:
        _abort("fx_history_job_invalid")
    try:
        _owner_only_directory(resolved.parent)
        value = json.loads(resolved.read_text(encoding="utf-8"))
        required = {
            "contract_version", "context", "store_path", "request", "output_path", "mode",
            "previous_artifact_path", "evidence_output_path", "created_at_utc", "job_fingerprint",
        }
        if not isinstance(value, dict) or set(value) != required or value.get("contract_version") != "fx_conversion_worker_job_v1":
            _abort("fx_history_job_invalid")
        rebuilt = new_fx_conversion_worker_job_v1(
            value["context"], store_path=value["store_path"], request=value["request"],
            output_path=value["output_path"], mode=value["mode"],
            previous_artifact_path=value["previous_artifact_path"],
            evidence_output_path=value["evidence_output_path"],
            created_at_utc=value["created_at_utc"],
        )
        if rebuilt != value:
            _abort("fx_history_job_invalid")
        return rebuilt
    except FxHistoryBlocked:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise FxHistoryBlocked("fx_history_job_invalid") from exc


def run_fx_conversion_worker_job_v1(job: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(job, Mapping):
        _abort("fx_history_job_invalid")
    value = dict(job)
    required = {
        "contract_version", "context", "store_path", "request", "output_path", "mode",
        "previous_artifact_path", "evidence_output_path", "created_at_utc", "job_fingerprint",
    }
    if set(value) != required or value.get("contract_version") != "fx_conversion_worker_job_v1":
        _abort("fx_history_job_invalid")
    rebuilt = new_fx_conversion_worker_job_v1(
        value["context"], store_path=value["store_path"], request=value["request"],
        output_path=value["output_path"], mode=value["mode"],
        previous_artifact_path=value["previous_artifact_path"],
        evidence_output_path=value["evidence_output_path"], created_at_utc=value["created_at_utc"],
    )
    if rebuilt != value:
        _abort("fx_history_job_invalid")
    context = _normalize_context(value["context"], writer=True)
    previous = None
    if value["previous_artifact_path"] is not None:
        previous = read_fx_conversion_artifact_v1(value["previous_artifact_path"], context)
    artifact = materialize_fx_conversion_v1(
        value["store_path"], context, value["request"], mode=value["mode"],
        previous_artifact=previous,
    )
    publish_fx_conversion_artifact_v1(artifact, context, value["output_path"])
    if value["evidence_output_path"] is not None:
        publish_fx_conversion_evidence_v1(artifact, context, value["evidence_output_path"])
    return artifact


def fx_history_error_codes_v1() -> tuple[str, ...]:
    return tuple(sorted(ERROR_CODES))


__all__ = [
    "ALGORITHM_VERSION", "FxHistoryBlocked", "FxHistoryContext", "FxHistoryReceipt",
    "append_fx_history_v1", "bind_fx_pair_v1", "bootstrap_fx_history_store_v1",
    "fx_conversion_job_binding_fingerprint_v1", "fx_history_context_fingerprint_v1",
    "fx_history_error_codes_v1", "fx_history_job_binding_fingerprint_v1",
    "load_fx_conversion_worker_job_v1", "materialize_fx_conversion_v1",
    "new_fx_conversion_request_v1", "new_fx_conversion_worker_job_v1", "new_fx_pair_binding_v1",
    "publish_fx_conversion_artifact_v1", "publish_fx_conversion_evidence_v1",
    "read_fx_conversion_artifact_v1", "read_fx_history_v1", "read_fx_revision_history_v1",
    "validate_fx_conversion_artifact_v1",
    "run_fx_conversion_worker_job_v1", "seal_fx_history_candidate_v1",
]
