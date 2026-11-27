#!/usr/bin/env python3
"""Persistent provider-neutral Daily Market History v1 reference boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts" / "daily-market-history" / "v1" / "schema.sql"
STORE_VERSION = 2400
PREVIOUS_STORE_VERSION = 2300
STORE_MIGRATION = ROOT / "contracts" / "daily-market-history" / "v1" / "migrate-store-v2300-to-v2400.sql"

ERROR_CODES = frozenset({
    "daily_market_history_boundary_failed",
    "daily_market_history_calendar_invalid",
    "daily_market_history_candidate_fingerprint_mismatch",
    "daily_market_history_candidate_invalid",
    "daily_market_history_context_invalid",
    "daily_market_history_correction_stale",
    "daily_market_history_decimal_invalid",
    "daily_market_history_domain_unchanged",
    "daily_market_history_initial_exists",
    "daily_market_history_job_binding_invalid",
    "daily_market_history_listing_conflict",
    "daily_market_history_listing_invalid",
    "daily_market_history_listing_missing",
    "daily_market_history_range_invalid",
    "daily_market_history_request_conflict",
    "daily_market_history_store_exists",
    "daily_market_history_store_invalid",
    "daily_market_history_store_context_mismatch",
    "daily_market_history_synthetic_failpoint",
    "daily_market_history_write_failed",
})
FAILPOINTS = frozenset({"after_request", "after_first_revision", "before_commit"})
CALENDAR_CODES = frozenset({"weekday_exchange", "continuous_24_7", "bank_business_day", "custom_reviewed"})
# "carried_listing": Tage, die aus einer Vorgaengerfreigabe derselben Zuordnung
# uebernommen wurden. Sie sind nicht bei der Quelle geholt worden, und der
# Pruefpfad muss das sagen koennen (#283, 24.09.2026).
SOURCE_KINDS = frozenset({"synthetic_fixture", "manual_reviewed_evidence", "market_plugin", "carried_listing"})
DAY_STATUSES = frozenset({"observed", "non_trading_day", "source_gap"})
BAR_SHAPES = frozenset({"full_ohlcv", "close_only", "not_applicable"})
CORPORATE_ACTION_STATUSES = frozenset({"none_reported", "pending_review", "explicitly_reconciled", "not_applicable"})
VALUATION_STATUSES = frozenset({"eligible", "blocked_corporate_action", "not_applicable"})
QUALITY_STATUSES = frozenset({"complete", "corrected", "calendar_confirmed", "explicit_gap"})
GAP_REASONS = frozenset({"source_no_data", "source_partial_response", "calendar_ambiguity"})
CORRECTION_REASONS = frozenset({"source_correction", "calendar_correction", "corporate_action_reconciliation", "manual_review_correction"})
REVISION_MODES = frozenset({"initial", "unchanged", "correction"})

_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_REF = re.compile(r"^[a-z][a-z0-9]{2}_[a-f0-9]{32}$")
_TOKEN = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,79}$")
_MARKET_CODE = re.compile(r"^[A-Z0-9_]{2,16}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")

_LISTING_FIELDS = frozenset({
    "contract_version", "listing_ref", "asset_ref", "quote_currency", "market_code",
    "timezone_name", "calendar_code", "valuation_price_policy", "catalog_fingerprint",
    "listing_fingerprint",
})
_DAY_INPUT_FIELDS = frozenset({
    "trading_date", "revision_mode", "supersedes_revision_ref", "day_status", "bar_shape",
    "open_decimal", "high_decimal", "low_decimal", "close_decimal", "adjusted_close_decimal",
    "volume_decimal", "corporate_action_status", "valuation_status", "quality_status",
    "gap_reason", "source_observation_ref", "observed_at_utc", "correction_reason",
})
_DAY_FIELDS = _DAY_INPUT_FIELDS | {"source_day_fingerprint"}
_CANDIDATE_FIELDS = frozenset({
    "contract_version", "listing_ref", "request_ref", "source_kind", "source_ref",
    "source_version", "request_fingerprint", "job_binding_fingerprint", "requested_start_date", "requested_end_date",
    "retrieved_at_utc", "days", "candidate_fingerprint",
})
_DOMAIN_FIELDS = (
    "day_status", "bar_shape", "open_decimal", "high_decimal", "low_decimal",
    "close_decimal", "adjusted_close_decimal", "volume_decimal", "corporate_action_status",
    "valuation_status", "quality_status", "gap_reason",
)
_CORRECTION_FIELDS = tuple(field for field in _DOMAIN_FIELDS if field != "quality_status")


class DailyMarketHistoryBlocked(ValueError):
    def __init__(self, code: str):
        if code not in ERROR_CODES:
            raise ValueError("daily_market_history_error_code_unregistered")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class MarketHistoryContext:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str
    role: str = "market_worker"


@dataclass(frozen=True)
class MarketListingBindingResult:
    listing_ref: str
    asset_ref: str
    quote_currency: str
    listing_fingerprint: str
    exact_replay: bool


@dataclass(frozen=True)
class MarketHistoryReceipt:
    request_ref: str
    candidate_fingerprint: str
    appended_day_count: int
    corrected_day_count: int
    unchanged_day_count: int
    row_set_fingerprint: str
    receipt_fingerprint: str
    exact_replay: bool


def _abort(code: str) -> None:
    raise DailyMarketHistoryBlocked(code)


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


def _normalize_context(context: MarketHistoryContext | Mapping[str, str], *, writer: bool = False) -> MarketHistoryContext:
    if isinstance(context, Mapping):
        try:
            context = MarketHistoryContext(
                context["tenant_id"], context["user_id"], context["data_space_id"],
                context["actor_id"], context.get("role", "market_worker"),
            )
        except (KeyError, TypeError) as exc:
            raise DailyMarketHistoryBlocked("daily_market_history_context_invalid") from exc
    if not isinstance(context, MarketHistoryContext):
        _abort("daily_market_history_context_invalid")
    values = (context.tenant_id, context.user_id, context.data_space_id, context.actor_id)
    if any(
        not isinstance(value, str) or not 3 <= len(value) <= (80 if index == 3 else 64) or
        re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
        for index, value in enumerate(values)
    ) or not context.data_space_id.startswith("sbx_"):
        _abort("daily_market_history_context_invalid")
    if context.role not in {"market_worker", "portfolio_worker"} or writer and context.role != "market_worker":
        _abort("daily_market_history_context_invalid")
    return context


def daily_market_history_context_fingerprint_v1(context: MarketHistoryContext | Mapping[str, str]) -> str:
    context = _normalize_context(context)
    return _sha({
        "contract_version": "daily_market_history_v1",
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "data_space_id": context.data_space_id,
    })


def daily_market_history_job_binding_fingerprint_v1(context: MarketHistoryContext | Mapping[str, str], *, listing_ref: str, request_ref: str, request_fingerprint: str, source_ref: str) -> str:
    context = _normalize_context(context, writer=True)
    return _sha({
        "contract_version": "daily_market_history_job_binding_v1",
        "context_fingerprint": daily_market_history_context_fingerprint_v1(context),
        "actor_id": context.actor_id, "role": context.role,
        "capability": "append_daily_history", "listing_ref": _ref(listing_ref, "lsr_"),
        "request_ref": _ref(request_ref, "mrq_"),
        "request_fingerprint": _fingerprint(request_fingerprint),
        "source_ref": _ref(source_ref, "msr_"),
    })


def _ref(value: Any, prefix: str, code: str = "daily_market_history_candidate_invalid") -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None or not value.startswith(prefix):
        _abort(code)
    return value


def _fingerprint(value: Any, code: str = "daily_market_history_candidate_invalid") -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        _abort(code)
    return value


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("daily_market_history_candidate_invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort("daily_market_history_candidate_invalid")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _abort("daily_market_history_candidate_invalid")
    return parsed


def _day_date(value: Any) -> date:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        _abort("daily_market_history_range_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _abort("daily_market_history_range_invalid")
    if parsed.isoformat() != value:
        _abort("daily_market_history_range_invalid")
    return parsed


def _date_range(start: date, end: date) -> list[str]:
    count = (end - start).days + 1
    if count < 1 or count > 20000:
        _abort("daily_market_history_range_invalid")
    return [(start + timedelta(days=index)).isoformat() for index in range(count)]


def _decimal(value: Any, *, nullable: bool = False, positive: bool = False, nonnegative: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or len(value) > 80 or _DECIMAL.fullmatch(value) is None or value == "-0":
        _abort("daily_market_history_decimal_invalid")
    try:
        number = Decimal(value)
    except InvalidOperation:
        _abort("daily_market_history_decimal_invalid")
    if positive and number <= 0 or nonnegative and number < 0:
        _abort("daily_market_history_decimal_invalid")
    return value


def _owner_only_directory(path: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(path))
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, TypeError, ValueError) as exc:
        raise DailyMarketHistoryBlocked("daily_market_history_store_invalid") from exc
    wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
    if absolute != resolved or not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o700 or wrong_owner:
        _abort("daily_market_history_store_invalid")
    return resolved


def _regular_store(path: str | Path, *, new: bool = False) -> Path:
    try:
        target = Path(path)
    except (TypeError, ValueError) as exc:
        raise DailyMarketHistoryBlocked("daily_market_history_store_invalid") from exc
    if new:
        if target.exists() or target.is_symlink():
            _abort("daily_market_history_store_exists")
        parent = _owner_only_directory(target.parent)
        return parent / target.name
    try:
        absolute = Path(os.path.abspath(target))
        resolved = target.resolve(strict=True)
        metadata = resolved.stat()
    except (OSError, TypeError, ValueError) as exc:
        raise DailyMarketHistoryBlocked("daily_market_history_store_invalid") from exc
    wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
    if (
        absolute != resolved or target.is_symlink() or
        not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or wrong_owner
    ):
        _abort("daily_market_history_store_invalid")
    _owner_only_directory(resolved.parent)
    return resolved


def _connect(path: str | Path, context: MarketHistoryContext | Mapping[str, str], *, read_only: bool = False) -> sqlite3.Connection:
    context = _normalize_context(context, writer=not read_only)
    source = _regular_store(path)
    try:
        if read_only:
            connection = sqlite3.connect(f"{source.as_uri()}?mode=ro", uri=True)
            connection.execute("PRAGMA query_only=ON")
        else:
            connection = sqlite3.connect(source, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        # Ein Speicher aus der Vorversion wird beim ersten schreibenden Zugriff
        # nachgezogen. Lesend bleibt er benutzbar, ohne ihn anzufassen: Der
        # Unterschied ist allein die Pruefliste der Herkunftsarten, und die
        # bindet nur das Schreiben (#283, 24.09.2026).
        if version == PREVIOUS_STORE_VERSION and not read_only:
            connection.executescript(STORE_MIGRATION.read_text(encoding="utf-8"))
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        binding = connection.execute("SELECT context_binding_fingerprint FROM daily_market_history_store_binding WHERE singleton_id=1").fetchone()
        if version not in (STORE_VERSION, PREVIOUS_STORE_VERSION) or binding is None or binding[0] != daily_market_history_context_fingerprint_v1(context):
            connection.close()
            _abort("daily_market_history_store_context_mismatch")
        return connection
    except DailyMarketHistoryBlocked:
        raise
    except sqlite3.Error as exc:
        raise DailyMarketHistoryBlocked("daily_market_history_store_invalid") from exc


def bootstrap_daily_market_history_store_v1(path: str | Path, context: MarketHistoryContext | Mapping[str, str], created_at_utc: str) -> Path:
    context = _normalize_context(context, writer=True)
    _utc(created_at_utc)
    target = _regular_store(path, new=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(target, flags, 0o600)
        os.close(descriptor)
    except FileExistsError:
        _abort("daily_market_history_store_exists")
    except OSError as exc:
        raise DailyMarketHistoryBlocked("daily_market_history_store_invalid") from exc
    try:
        connection = sqlite3.connect(target)
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        raise DailyMarketHistoryBlocked("daily_market_history_store_invalid") from exc
    try:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO daily_market_history_store_binding VALUES (1,2400,?,?)",
            (daily_market_history_context_fingerprint_v1(context), created_at_utc),
        )
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            _abort("daily_market_history_store_invalid")
    except Exception:
        connection.close()
        target.unlink(missing_ok=True)
        raise
    finally:
        try:
            connection.close()
        except Exception:
            pass
    os.chmod(target, 0o600)
    return target


def new_daily_market_listing_binding_v1(*, listing_ref: str, asset_ref: str, quote_currency: str, market_code: str, timezone_name: str, calendar_code: str, catalog_fingerprint: str) -> dict[str, Any]:
    body = {
        "contract_version": "daily_market_listing_v1",
        "listing_ref": _ref(listing_ref, "lsr_", "daily_market_history_listing_invalid"),
        "asset_ref": _ref(asset_ref, "asf_", "daily_market_history_listing_invalid"),
        "quote_currency": quote_currency,
        "market_code": market_code,
        "timezone_name": timezone_name,
        "calendar_code": calendar_code,
        "valuation_price_policy": "unadjusted_close_only",
        "catalog_fingerprint": _fingerprint(catalog_fingerprint),
    }
    if not isinstance(quote_currency, str) or _CURRENCY.fullmatch(quote_currency) is None:
        _abort("daily_market_history_listing_invalid")
    if not isinstance(market_code, str) or _MARKET_CODE.fullmatch(market_code) is None or calendar_code not in CALENDAR_CODES:
        _abort("daily_market_history_listing_invalid")
    if not isinstance(timezone_name, str) or not 3 <= len(timezone_name) <= 64:
        _abort("daily_market_history_listing_invalid")
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        _abort("daily_market_history_listing_invalid")
    return {**body, "listing_fingerprint": _sha(body)}


def _listing(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _LISTING_FIELDS or value.get("contract_version") != "daily_market_listing_v1":
        _abort("daily_market_history_listing_invalid")
    expected = new_daily_market_listing_binding_v1(
        listing_ref=value.get("listing_ref"), asset_ref=value.get("asset_ref"),
        quote_currency=value.get("quote_currency"), market_code=value.get("market_code"),
        timezone_name=value.get("timezone_name"), calendar_code=value.get("calendar_code"),
        catalog_fingerprint=value.get("catalog_fingerprint"),
    )
    if value != expected:
        _abort("daily_market_history_listing_invalid")
    return expected


def bind_daily_market_listing_v1(store_path: str | Path, context: MarketHistoryContext | Mapping[str, str], listing: Mapping[str, Any], bound_at_utc: str) -> MarketListingBindingResult:
    context = _normalize_context(context, writer=True)
    listing = _listing(dict(listing))
    _utc(bound_at_utc)
    connection = _connect(store_path, context)
    try:
        connection.execute("BEGIN IMMEDIATE")
        store_created = connection.execute("SELECT created_at_utc FROM daily_market_history_store_binding WHERE singleton_id=1").fetchone()[0]
        if bound_at_utc < store_created:
            connection.rollback()
            _abort("daily_market_history_listing_invalid")
        existing = connection.execute("SELECT * FROM market_listing_binding WHERE listing_ref=?", (listing["listing_ref"],)).fetchone()
        if existing is not None:
            if existing["listing_fingerprint"] != listing["listing_fingerprint"]:
                connection.rollback()
                _abort("daily_market_history_listing_conflict")
            connection.rollback()
            return MarketListingBindingResult(listing["listing_ref"], listing["asset_ref"], listing["quote_currency"], listing["listing_fingerprint"], True)
        connection.execute(
            "INSERT INTO market_listing_binding VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                _id("mli", listing["listing_ref"]), listing["listing_ref"], listing["asset_ref"],
                listing["quote_currency"], listing["market_code"], listing["timezone_name"],
                listing["calendar_code"], listing["valuation_price_policy"], listing["catalog_fingerprint"],
                listing["listing_fingerprint"], context.actor_id, bound_at_utc,
            ),
        )
        connection.commit()
    except DailyMarketHistoryBlocked:
        raise
    except sqlite3.Error as exc:
        connection.rollback()
        raise DailyMarketHistoryBlocked("daily_market_history_write_failed") from exc
    finally:
        connection.close()
    return MarketListingBindingResult(listing["listing_ref"], listing["asset_ref"], listing["quote_currency"], listing["listing_fingerprint"], False)


def _validate_day_shape(row: dict[str, Any]) -> None:
    status = row["day_status"]
    shape = row["bar_shape"]
    if status not in DAY_STATUSES or shape not in BAR_SHAPES or row["revision_mode"] not in REVISION_MODES:
        _abort("daily_market_history_candidate_invalid")
    supersedes = row["supersedes_revision_ref"]
    correction = row["correction_reason"]
    if row["revision_mode"] == "initial" and (supersedes is not None or correction is not None):
        _abort("daily_market_history_candidate_invalid")
    if row["revision_mode"] == "unchanged" and (supersedes is None or correction is not None):
        _abort("daily_market_history_candidate_invalid")
    if row["revision_mode"] == "correction" and (supersedes is None or correction not in CORRECTION_REASONS):
        _abort("daily_market_history_candidate_invalid")
    if supersedes is not None:
        _ref(supersedes, "mrv_")
    _ref(row["source_observation_ref"], "mor_")
    _utc(row["observed_at_utc"])
    if row["corporate_action_status"] not in CORPORATE_ACTION_STATUSES or row["valuation_status"] not in VALUATION_STATUSES or row["quality_status"] not in QUALITY_STATUSES:
        _abort("daily_market_history_candidate_invalid")
    values = {field: row[field] for field in ("open_decimal", "high_decimal", "low_decimal", "close_decimal", "adjusted_close_decimal", "volume_decimal")}
    if status == "observed":
        if shape not in {"full_ohlcv", "close_only"} or row["gap_reason"] is not None or row["corporate_action_status"] == "not_applicable":
            _abort("daily_market_history_candidate_invalid")
        if row["corporate_action_status"] == "pending_review":
            if row["valuation_status"] != "blocked_corporate_action":
                _abort("daily_market_history_candidate_invalid")
        elif row["valuation_status"] != "eligible":
            _abort("daily_market_history_candidate_invalid")
        close = Decimal(_decimal(values["close_decimal"], positive=True))
        adjusted = _decimal(values["adjusted_close_decimal"], nullable=True, positive=True)
        if shape == "full_ohlcv":
            open_value = Decimal(_decimal(values["open_decimal"], positive=True))
            high = Decimal(_decimal(values["high_decimal"], positive=True))
            low = Decimal(_decimal(values["low_decimal"], positive=True))
            _decimal(values["volume_decimal"], nonnegative=True)
            if low > min(open_value, close) or high < max(open_value, close) or low > high:
                _abort("daily_market_history_candidate_invalid")
        elif any(values[field] is not None for field in ("open_decimal", "high_decimal", "low_decimal", "volume_decimal")):
            _abort("daily_market_history_candidate_invalid")
        if adjusted is not None:
            Decimal(adjusted)
        if row["revision_mode"] == "correction" and row["quality_status"] != "corrected":
            _abort("daily_market_history_candidate_invalid")
        if row["revision_mode"] == "initial" and row["quality_status"] != "complete":
            _abort("daily_market_history_candidate_invalid")
        if row["revision_mode"] == "unchanged" and row["quality_status"] not in {"complete", "corrected"}:
            _abort("daily_market_history_candidate_invalid")
    else:
        if shape != "not_applicable" or any(value is not None for value in values.values()) or row["corporate_action_status"] != "not_applicable" or row["valuation_status"] != "not_applicable":
            _abort("daily_market_history_candidate_invalid")
        if status == "non_trading_day":
            if row["gap_reason"] is not None or row["quality_status"] != "calendar_confirmed":
                _abort("daily_market_history_candidate_invalid")
        elif row["gap_reason"] not in GAP_REASONS or row["quality_status"] != "explicit_gap":
            _abort("daily_market_history_candidate_invalid")


def _day(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _DAY_FIELDS:
        _abort("daily_market_history_candidate_invalid")
    row = dict(value)
    _day_date(row["trading_date"])
    _validate_day_shape(row)
    expected = _sha({key: row[key] for key in row if key != "source_day_fingerprint"})
    if row["source_day_fingerprint"] != expected:
        _abort("daily_market_history_candidate_fingerprint_mismatch")
    return row


def seal_daily_market_history_candidate_v1(*, listing_ref: str, request_ref: str, source_kind: str, source_ref: str, source_version: str, request_fingerprint: str, job_binding_fingerprint: str, requested_start_date: str, requested_end_date: str, retrieved_at_utc: str, days: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    _ref(listing_ref, "lsr_")
    _ref(request_ref, "mrq_")
    _ref(source_ref, "msr_")
    _fingerprint(request_fingerprint)
    _fingerprint(job_binding_fingerprint, "daily_market_history_job_binding_invalid")
    if source_kind not in SOURCE_KINDS or not isinstance(source_version, str) or not 3 <= len(source_version) <= 80 or _TOKEN.fullmatch(source_version) is None:
        _abort("daily_market_history_candidate_invalid")
    _utc(retrieved_at_utc)
    start = _day_date(requested_start_date)
    end = _day_date(requested_end_date)
    expected_dates = _date_range(start, end)
    if not isinstance(days, Sequence) or isinstance(days, (str, bytes)):
        _abort("daily_market_history_candidate_invalid")
    sealed_days = []
    for raw in days:
        if not isinstance(raw, Mapping) or set(raw) != _DAY_INPUT_FIELDS:
            _abort("daily_market_history_candidate_invalid")
        row = dict(raw)
        _day_date(row["trading_date"])
        _validate_day_shape(row)
        if _utc(row["observed_at_utc"]) > _utc(retrieved_at_utc):
            _abort("daily_market_history_candidate_invalid")
        row["source_day_fingerprint"] = _sha(row)
        sealed_days.append(row)
    if [row["trading_date"] for row in sealed_days] != expected_dates:
        _abort("daily_market_history_range_invalid")
    body = {
        "contract_version": "daily_market_history_candidate_v1",
        "listing_ref": listing_ref,
        "request_ref": request_ref,
        "source_kind": source_kind,
        "source_ref": source_ref,
        "source_version": source_version,
        "request_fingerprint": request_fingerprint,
        "job_binding_fingerprint": job_binding_fingerprint,
        "requested_start_date": requested_start_date,
        "requested_end_date": requested_end_date,
        "retrieved_at_utc": retrieved_at_utc,
        "days": sealed_days,
    }
    return {**body, "candidate_fingerprint": _sha(body)}


def seal_daily_market_calendar_corrections_v1(*, requested_dates, days, **header):
    """Explicit sparse calendar-only variant; one native atomic request, no filler days."""
    if (not isinstance(requested_dates, list) or not 1 <= len(requested_dates) <= 512
        or any(not isinstance(d, str) for d in requested_dates)
        or requested_dates != sorted(set(requested_dates))
        or header.get('source_kind') != 'manual_reviewed_evidence'
        or header.get('source_version') != 'market_calendar_batch_v1.0.0'
        or not isinstance(days, list) or len(days) != len(requested_dates)):
        _abort('daily_market_history_candidate_invalid')
    sealed = []
    for day, row in zip(requested_dates, days):
        if (not isinstance(row, Mapping) or row.get('trading_date') != day
            or row.get('revision_mode') != 'correction' or row.get('day_status') != 'non_trading_day'
            or row.get('quality_status') != 'calendar_confirmed' or row.get('correction_reason') != 'calendar_correction'):
            _abort('daily_market_history_candidate_invalid')
        part = seal_daily_market_history_candidate_v1(**header, requested_start_date=day,
            requested_end_date=day, days=[row])
        sealed.extend(part['days'])
    _date_range(_day_date(requested_dates[0]), _day_date(requested_dates[-1]))
    body = {k: v for k, v in part.items() if k != 'candidate_fingerprint'}
    body.update(contract_version='daily_market_history_calendar_corrections_v1',
        requested_start_date=requested_dates[0], requested_end_date=requested_dates[-1],
        requested_dates=requested_dates, days=sealed)
    return {**body, 'candidate_fingerprint': _sha(body)}


def _candidate(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get('contract_version') == 'daily_market_history_calendar_corrections_v1':
        if set(value) != _CANDIDATE_FIELDS | {'requested_dates'}:
            _abort('daily_market_history_candidate_invalid')
        try:
            header = {k: value[k] for k in _CANDIDATE_FIELDS - {'contract_version', 'candidate_fingerprint',
                'requested_start_date', 'requested_end_date', 'days'}}
            rebuilt = seal_daily_market_calendar_corrections_v1(**header, requested_dates=value['requested_dates'],
                days=[{k: row[k] for k in _DAY_INPUT_FIELDS} for row in value['days']])
        except (KeyError, TypeError):
            _abort('daily_market_history_candidate_invalid')
        if rebuilt != value:
            _abort('daily_market_history_candidate_fingerprint_mismatch')
        return rebuilt
    if not isinstance(value, dict) or set(value) != _CANDIDATE_FIELDS or value.get("contract_version") != "daily_market_history_candidate_v1":
        _abort("daily_market_history_candidate_invalid")
    body = {key: value[key] for key in value if key != "candidate_fingerprint"}
    try:
        rebuilt = seal_daily_market_history_candidate_v1(
            listing_ref=body["listing_ref"], request_ref=body["request_ref"],
            source_kind=body["source_kind"], source_ref=body["source_ref"],
            source_version=body["source_version"], request_fingerprint=body["request_fingerprint"],
            job_binding_fingerprint=body["job_binding_fingerprint"],
            requested_start_date=body["requested_start_date"], requested_end_date=body["requested_end_date"],
            retrieved_at_utc=body["retrieved_at_utc"],
            days=[{key: row[key] for key in _DAY_INPUT_FIELDS} for row in body["days"]],
        )
    except (KeyError, TypeError):
        _abort("daily_market_history_candidate_invalid")
    if rebuilt != value or value["candidate_fingerprint"] != _sha(body):
        _abort("daily_market_history_candidate_fingerprint_mismatch")
    return rebuilt


def _calendar_valid(calendar_code: str, timezone_name: str, row: Mapping[str, Any]) -> None:
    day = _day_date(row["trading_date"])
    if calendar_code == "continuous_24_7" and row["day_status"] == "non_trading_day":
        _abort("daily_market_history_calendar_invalid")
    if calendar_code in {"weekday_exchange", "bank_business_day"} and day.weekday() >= 5 and row["day_status"] != "non_trading_day":
        _abort("daily_market_history_calendar_invalid")
    if row["day_status"] == "observed" and _utc(row["observed_at_utc"]).astimezone(ZoneInfo(timezone_name)).date() != day:
        _abort("daily_market_history_calendar_invalid")


def validate_daily_market_candidate_for_listing_v1(candidate: Mapping[str, Any], listing: Mapping[str, Any]) -> dict[str, Any]:
    candidate = _candidate(dict(candidate))
    listing = _listing(dict(listing))
    if candidate["listing_ref"] != listing["listing_ref"]:
        _abort("daily_market_history_listing_invalid")
    for row in candidate["days"]:
        _calendar_valid(listing["calendar_code"], listing["timezone_name"], row)
    return candidate


def _current_day(connection: sqlite3.Connection, listing_id: str, trading_date: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT entity.market_day_id,entity.market_day_ref,revision.* FROM market_day_entity entity JOIN current_market_day_revision revision USING(market_day_id) WHERE entity.listing_id=? AND entity.trading_date=?",
        (listing_id, trading_date),
    ).fetchone()


def _domain(row: Mapping[str, Any], fields: Sequence[str] = _DOMAIN_FIELDS) -> dict[str, Any]:
    return {field: row[field] for field in fields}


def _receipt_from_row(row: sqlite3.Row, exact_replay: bool) -> MarketHistoryReceipt:
    return MarketHistoryReceipt(
        row["request_ref"], row["candidate_fingerprint"], int(row["appended_day_count"]),
        int(row["corrected_day_count"]), int(row["unchanged_day_count"]),
        row["row_set_fingerprint"], row["receipt_fingerprint"], exact_replay,
    )


def append_daily_market_history_v1(store_path: str | Path, context: MarketHistoryContext | Mapping[str, str], candidate: Mapping[str, Any], completed_at_utc: str, *, failpoint: str | None = None) -> MarketHistoryReceipt:
    context = _normalize_context(context, writer=True)
    candidate = _candidate(dict(candidate))
    if candidate["job_binding_fingerprint"] != daily_market_history_job_binding_fingerprint_v1(
        context, listing_ref=candidate["listing_ref"], request_ref=candidate["request_ref"],
        request_fingerprint=candidate["request_fingerprint"], source_ref=candidate["source_ref"],
    ):
        _abort("daily_market_history_job_binding_invalid")
    completed = _utc(completed_at_utc)
    if completed < _utc(candidate["retrieved_at_utc"]):
        _abort("daily_market_history_candidate_invalid")
    if failpoint is not None and failpoint not in FAILPOINTS:
        _abort("daily_market_history_candidate_invalid")
    connection = _connect(store_path, context)
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing_request = connection.execute("SELECT * FROM daily_market_history_request WHERE request_ref=?", (candidate["request_ref"],)).fetchone()
        if existing_request is not None:
            if existing_request["candidate_fingerprint"] != candidate["candidate_fingerprint"]:
                connection.rollback()
                _abort("daily_market_history_request_conflict")
            connection.rollback()
            return _receipt_from_row(existing_request, True)
        listing = connection.execute("SELECT * FROM market_listing_binding WHERE listing_ref=?", (candidate["listing_ref"],)).fetchone()
        if listing is None:
            connection.rollback()
            _abort("daily_market_history_listing_missing")
        if completed_at_utc < listing["bound_at_utc"]:
            connection.rollback()
            _abort("daily_market_history_candidate_invalid")
        plans: list[dict[str, Any]] = []
        counts = {"appended": 0, "corrected": 0, "unchanged": 0}
        for ordinal, row in enumerate(candidate["days"], 1):
            _calendar_valid(listing["calendar_code"], listing["timezone_name"], row)
            current = _current_day(connection, listing["listing_id"], row["trading_date"])
            if candidate['contract_version'] == 'daily_market_history_calendar_corrections_v1' and (current is None or current['day_status'] != 'source_gap'):
                _abort('daily_market_history_correction_stale')
            mode = row["revision_mode"]
            if current is None:
                if mode != "initial":
                    connection.rollback()
                    _abort("daily_market_history_correction_stale")
                market_day_ref = _id("mdy", [candidate["listing_ref"], row["trading_date"]])
                market_day_id = _id("mdi", market_day_ref)
                revision_no = 1
                supersedes_id = None
                disposition = "appended"
            else:
                market_day_ref = current["market_day_ref"]
                market_day_id = current["market_day_id"]
                latest_retrieval = connection.execute(
                    "SELECT max(request.retrieved_at_utc) FROM market_request_day_evidence evidence JOIN daily_market_history_request request USING(request_id) WHERE evidence.market_day_id=?",
                    (market_day_id,),
                ).fetchone()[0]
                if candidate["retrieved_at_utc"] <= latest_retrieval:
                    connection.rollback()
                    _abort("daily_market_history_correction_stale")
                if mode == "initial":
                    connection.rollback()
                    _abort("daily_market_history_initial_exists")
                if row["supersedes_revision_ref"] != current["market_day_revision_ref"]:
                    connection.rollback()
                    _abort("daily_market_history_correction_stale")
                if mode == "unchanged":
                    if _domain(row) != _domain(current):
                        connection.rollback()
                        _abort("daily_market_history_correction_stale")
                    plans.append({
                        "ordinal": ordinal, "row": row, "market_day_id": market_day_id,
                        "market_day_ref": market_day_ref, "revision_id": current["market_day_revision_id"],
                        "revision_ref": current["market_day_revision_ref"], "new_entity": False,
                        "new_revision": False, "disposition": "unchanged",
                    })
                    counts["unchanged"] += 1
                    continue
                if _domain(row, _CORRECTION_FIELDS) == _domain(current, _CORRECTION_FIELDS):
                    connection.rollback()
                    _abort("daily_market_history_domain_unchanged")
                revision_no = int(current["revision_no"]) + 1
                supersedes_id = current["market_day_revision_id"]
                disposition = "corrected"
            revision_ref = _id("mrv", [market_day_ref, revision_no, row["source_day_fingerprint"], candidate["request_ref"]])
            revision_id = _id("mdr", revision_ref)
            plans.append({
                "ordinal": ordinal, "row": row, "market_day_id": market_day_id,
                "market_day_ref": market_day_ref, "revision_id": revision_id,
                "revision_ref": revision_ref, "revision_no": revision_no,
                "supersedes_id": supersedes_id, "new_entity": current is None,
                "new_revision": True, "disposition": disposition,
            })
            counts[disposition] += 1
        row_set_fingerprint = _sha([{
            "trading_date": plan["row"]["trading_date"],
            "resulting_revision_ref": plan["revision_ref"],
            "source_day_fingerprint": plan["row"]["source_day_fingerprint"],
            "disposition": plan["disposition"],
        } for plan in plans])
        receipt_body = {
            "request_ref": candidate["request_ref"],
            "candidate_fingerprint": candidate["candidate_fingerprint"],
            "appended_day_count": counts["appended"],
            "corrected_day_count": counts["corrected"],
            "unchanged_day_count": counts["unchanged"],
            "row_set_fingerprint": row_set_fingerprint,
        }
        receipt_fingerprint = _sha(receipt_body)
        request_id = _id("mri", candidate["request_ref"])
        connection.execute(
            "INSERT INTO daily_market_history_request VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                request_id, candidate["request_ref"], listing["listing_id"], candidate["source_kind"],
                candidate["source_ref"], candidate["source_version"], candidate["request_fingerprint"],
                candidate["job_binding_fingerprint"], candidate["candidate_fingerprint"], candidate["requested_start_date"], candidate["requested_end_date"],
                candidate["retrieved_at_utc"], completed_at_utc, context.actor_id,
                counts["appended"], counts["corrected"], counts["unchanged"],
                row_set_fingerprint, receipt_fingerprint,
            ),
        )
        if failpoint == "after_request":
            raise RuntimeError("synthetic_failpoint")
        revision_seen = False
        for plan in plans:
            row = plan["row"]
            if plan["new_entity"]:
                connection.execute(
                    "INSERT INTO market_day_entity VALUES (?,?,?,?,?,?)",
                    (plan["market_day_id"], plan["market_day_ref"], listing["listing_id"], row["trading_date"], request_id, completed_at_utc),
                )
            if plan["new_revision"]:
                revision_body = {
                    "market_day_ref": plan["market_day_ref"], "market_day_revision_ref": plan["revision_ref"],
                    "revision_no": plan["revision_no"], "day": _domain(row),
                    "source_observation_ref": row["source_observation_ref"],
                    "observed_at_utc": row["observed_at_utc"],
                    "source_day_fingerprint": row["source_day_fingerprint"],
                    "request_ref": candidate["request_ref"], "correction_reason": row["correction_reason"],
                    "supersedes_revision_ref": row["supersedes_revision_ref"],
                    "retrieved_at_utc": candidate["retrieved_at_utc"], "completed_at_utc": completed_at_utc,
                }
                connection.execute(
                    "INSERT INTO market_day_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        plan["revision_id"], plan["revision_ref"], plan["market_day_id"], plan["revision_no"],
                        row["day_status"], row["bar_shape"], row["open_decimal"], row["high_decimal"],
                        row["low_decimal"], row["close_decimal"], row["adjusted_close_decimal"], row["volume_decimal"],
                        row["corporate_action_status"], row["valuation_status"], row["quality_status"], row["gap_reason"],
                        row["source_observation_ref"], row["observed_at_utc"], row["source_day_fingerprint"], request_id, row["correction_reason"],
                        plan["supersedes_id"], candidate["retrieved_at_utc"], completed_at_utc, _sha(revision_body),
                    ),
                )
                if failpoint == "after_first_revision" and not revision_seen:
                    raise RuntimeError("synthetic_failpoint")
                revision_seen = True
            connection.execute(
                "INSERT INTO market_request_day_evidence VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    _id("mde", [candidate["request_ref"], plan["ordinal"]]), request_id, plan["ordinal"],
                    plan["market_day_id"], plan["revision_id"], plan["disposition"],
                    row["source_observation_ref"], row["observed_at_utc"], row["source_day_fingerprint"],
                ),
            )
        if failpoint == "before_commit":
            raise RuntimeError("synthetic_failpoint")
        connection.commit()
        stored = connection.execute("SELECT * FROM daily_market_history_request WHERE request_ref=?", (candidate["request_ref"],)).fetchone()
        return _receipt_from_row(stored, False)
    except DailyMarketHistoryBlocked:
        raise
    except RuntimeError as exc:
        connection.rollback()
        if str(exc) == "synthetic_failpoint":
            raise DailyMarketHistoryBlocked("daily_market_history_synthetic_failpoint") from None
        raise DailyMarketHistoryBlocked("daily_market_history_boundary_failed") from exc
    except sqlite3.Error as exc:
        connection.rollback()
        raise DailyMarketHistoryBlocked("daily_market_history_write_failed") from exc
    except Exception as exc:
        connection.rollback()
        raise DailyMarketHistoryBlocked("daily_market_history_boundary_failed") from exc
    finally:
        connection.close()


def _read_listing(connection: sqlite3.Connection, listing_ref: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM market_listing_binding WHERE listing_ref=?", (listing_ref,)).fetchone()
    if row is None:
        _abort("daily_market_history_listing_missing")
    return row


def read_daily_market_listing_binding_v1(
    store_path: str | Path, context: MarketHistoryContext | Mapping[str, str], listing_ref: str,
) -> dict[str, Any]:
    context = _normalize_context(context)
    listing_ref = _ref(listing_ref, "lsr_")
    connection = _connect(store_path, context, read_only=True)
    try:
        row = _read_listing(connection, listing_ref)
        return {
            "contract_version": "daily_market_listing_v1", "listing_ref": row["listing_ref"],
            "asset_ref": row["asset_ref"], "quote_currency": row["quote_currency"],
            "market_code": row["market_code"], "timezone_name": row["timezone_name"],
            "calendar_code": row["calendar_code"], "valuation_price_policy": row["valuation_price_policy"],
            "catalog_fingerprint": row["catalog_fingerprint"], "listing_fingerprint": row["listing_fingerprint"],
        }
    finally:
        connection.close()


def read_daily_market_listing_bound_at_v1(
    store_path: str | Path, context: MarketHistoryContext | Mapping[str, str], listing_ref: str,
) -> str:
    """Wann die Freigabe erteilt wurde - der Zeitpunkt, zu dem ihr Katalogstand galt."""
    context = _normalize_context(context)
    listing_ref = _ref(listing_ref, "lsr_")
    connection = _connect(store_path, context, read_only=True)
    try:
        bound_at = _read_listing(connection, listing_ref)["bound_at_utc"]
        _utc(bound_at)
        return bound_at
    finally:
        connection.close()


def read_daily_market_history_v1(store_path: str | Path, context: MarketHistoryContext | Mapping[str, str], listing_ref: str, start_date: str, end_date: str) -> dict[str, Any]:
    context = _normalize_context(context)
    listing_ref = _ref(listing_ref, "lsr_")
    start = _day_date(start_date)
    end = _day_date(end_date)
    dates = _date_range(start, end)
    connection = _connect(store_path, context, read_only=True)
    try:
        listing = _read_listing(connection, listing_ref)
        rows = connection.execute(
            "SELECT entity.market_day_ref,entity.trading_date,revision.*,request.source_kind,request.source_ref,request.source_version FROM market_day_entity entity JOIN current_market_day_revision revision USING(market_day_id) JOIN daily_market_history_request request USING(request_id) WHERE entity.listing_id=? AND entity.trading_date BETWEEN ? AND ? ORDER BY entity.trading_date",
            (listing["listing_id"], start_date, end_date),
        ).fetchall()
        by_date = {row["trading_date"]: row for row in rows}
        days = []
        for trading_date in dates:
            row = by_date.get(trading_date)
            if row is None:
                days.append({
                    "trading_date": trading_date, "day_status": "not_requested", "market_day_ref": None,
                    "market_day_revision_ref": None, "revision_no": None, "bar_shape": "not_applicable",
                    "open_decimal": None, "high_decimal": None, "low_decimal": None, "close_decimal": None,
                    "adjusted_close_decimal": None, "volume_decimal": None,
                    "corporate_action_status": "not_applicable", "valuation_status": "not_applicable",
                    "quality_status": "not_requested", "gap_reason": None, "source_kind": None,
                    "source_ref": None, "source_version": None, "source_observation_ref": None,
                    "observed_at_utc": None, "retrieved_at_utc": None,
                })
            else:
                days.append({
                    "trading_date": trading_date, "day_status": row["day_status"],
                    "market_day_ref": row["market_day_ref"], "market_day_revision_ref": row["market_day_revision_ref"],
                    "revision_no": int(row["revision_no"]), "bar_shape": row["bar_shape"],
                    "open_decimal": row["open_decimal"], "high_decimal": row["high_decimal"],
                    "low_decimal": row["low_decimal"], "close_decimal": row["close_decimal"],
                    "adjusted_close_decimal": row["adjusted_close_decimal"], "volume_decimal": row["volume_decimal"],
                    "corporate_action_status": row["corporate_action_status"],
                    "valuation_status": row["valuation_status"], "quality_status": row["quality_status"],
                    "gap_reason": row["gap_reason"], "source_kind": row["source_kind"],
                    "source_ref": row["source_ref"], "source_version": row["source_version"],
                    "source_observation_ref": row["source_observation_ref"],
                    "observed_at_utc": row["observed_at_utc"], "retrieved_at_utc": row["retrieved_at_utc"],
                })
        if all(row["day_status"] == "not_requested" for row in days):
            status = "empty"
        elif any(row["day_status"] in {"not_requested", "source_gap"} or row["valuation_status"] == "blocked_corporate_action" for row in days):
            status = "partial"
        else:
            status = "completed"
        body = {
            "contract_version": "daily_market_history_read_model_v1",
            "status": status,
            "listing_ref": listing["listing_ref"], "asset_ref": listing["asset_ref"],
            "quote_currency": listing["quote_currency"], "market_code": listing["market_code"],
            "timezone_name": listing["timezone_name"], "calendar_code": listing["calendar_code"],
            "valuation_price_policy": listing["valuation_price_policy"],
            "range_start_date": start_date, "range_end_date": end_date, "days": days,
            "boundaries": {
                "provider_access": False, "network_access": False, "fx_conversion": False,
                "valuation_calculation": False, "canonical_write": False, "display_access": False,
            },
        }
        return {**body, "row_set_fingerprint": _sha(body)}
    finally:
        connection.close()


def read_daily_market_request_receipt_v1(
    store_path: str | Path, context: MarketHistoryContext | Mapping[str, str], request_ref: str,
) -> MarketHistoryReceipt | None:
    context = _normalize_context(context)
    request_ref = _ref(request_ref, "mrq_")
    connection = _connect(store_path, context, read_only=True)
    try:
        row = connection.execute(
            "SELECT * FROM daily_market_history_request WHERE request_ref=?", (request_ref,),
        ).fetchone()
        return None if row is None else _receipt_from_row(row, True)
    finally:
        connection.close()


def read_daily_market_revision_history_v1(store_path: str | Path, context: MarketHistoryContext | Mapping[str, str], listing_ref: str, trading_date: str) -> dict[str, Any]:
    context = _normalize_context(context)
    listing_ref = _ref(listing_ref, "lsr_")
    _day_date(trading_date)
    connection = _connect(store_path, context, read_only=True)
    try:
        listing = _read_listing(connection, listing_ref)
        rows = connection.execute(
            "SELECT entity.market_day_ref,revision.market_day_revision_ref,revision.revision_no,revision.day_status,revision.bar_shape,revision.open_decimal,revision.high_decimal,revision.low_decimal,revision.close_decimal,revision.adjusted_close_decimal,revision.volume_decimal,revision.corporate_action_status,revision.valuation_status,revision.quality_status,revision.gap_reason,revision.source_observation_ref,revision.observed_at_utc,revision.correction_reason,revision.retrieved_at_utc,revision.completed_at_utc,revision.revision_fingerprint FROM market_day_entity entity JOIN market_day_revision revision USING(market_day_id) WHERE entity.listing_id=? AND entity.trading_date=? ORDER BY revision.revision_no",
            (listing["listing_id"], trading_date),
        ).fetchall()
        return {
            "contract_version": "daily_market_revision_history_v1",
            "listing_ref": listing_ref,
            "trading_date": trading_date,
            "revisions": [dict(row) for row in rows],
            "provider_access": False, "network_access": False, "canonical_write": False,
        }
    finally:
        connection.close()


def read_daily_market_day_confirmations_v1(
    store_path: str | Path, context: MarketHistoryContext | Mapping[str, str], listing_ref: str, trading_dates: Sequence[str],
) -> dict[str, str]:
    """Je Tag der juengste Abruf, der ihn bestaetigt hat - auch einer, der nichts aenderte und deshalb keine neue Fassung
    anlegte (Nachweis 'unchanged'). Die Planung erkennt damit vorlaeufige Tageswerte, ohne sie nach einem bestaetigenden
    Abruf erneut anzufordern (#475)."""
    context = _normalize_context(context)
    listing_ref = _ref(listing_ref, "lsr_")
    dates = sorted({_day_date(value).isoformat() for value in trading_dates})
    if not dates:
        return {}
    connection = _connect(store_path, context, read_only=True)
    try:
        listing = _read_listing(connection, listing_ref)
        result: dict[str, str] = {}
        for start in range(0, len(dates), 400):
            chunk = dates[start:start + 400]
            marks = ",".join("?" for _ in chunk)
            for trading_date, retrieved in connection.execute(
                    "SELECT entity.trading_date, max(request.retrieved_at_utc) FROM market_day_entity entity "
                    "JOIN market_request_day_evidence evidence ON evidence.market_day_id=entity.market_day_id "
                    "JOIN daily_market_history_request request ON request.request_id=evidence.request_id "
                    f"WHERE entity.listing_id=? AND entity.trading_date IN ({marks}) GROUP BY entity.trading_date",
                    (listing["listing_id"], *chunk)):
                result[trading_date] = retrieved
        return result
    finally:
        connection.close()


def daily_market_history_error_codes_v1() -> tuple[str, ...]:
    return tuple(sorted(ERROR_CODES))


__all__ = [
    "DailyMarketHistoryBlocked", "MarketHistoryContext", "MarketHistoryReceipt",
    "MarketListingBindingResult", "append_daily_market_history_v1",
    "bind_daily_market_listing_v1", "bootstrap_daily_market_history_store_v1",
    "daily_market_history_context_fingerprint_v1", "daily_market_history_error_codes_v1",
    "daily_market_history_job_binding_fingerprint_v1", "new_daily_market_listing_binding_v1", "read_daily_market_history_v1",
    "read_daily_market_day_confirmations_v1", "read_daily_market_listing_binding_v1", "read_daily_market_request_receipt_v1", "read_daily_market_revision_history_v1", "seal_daily_market_history_candidate_v1",
    "validate_daily_market_candidate_for_listing_v1",
]
