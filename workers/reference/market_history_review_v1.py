"""Pure staged Market-review and calendar-safe Close-imputation proof."""

from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction
import hashlib
import json
import re
from typing import Any, Mapping, Sequence


class MarketHistoryReviewV1Error(RuntimeError):
    CODES = {
        "market_history_review_boundary_failed",
        "market_history_review_calendar_invalid",
        "market_history_review_candidate_invalid",
        "market_history_review_confirmation_required",
        "market_history_review_input_invalid",
        "market_history_review_stale",
    }

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("market_history_review_error_code_unregistered")
        self.code = code
        super().__init__(code)


_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_REVIEW_REF = re.compile(r"mhr_[a-f0-9]{32}")
_LISTING_BROWSER_REF = re.compile(r"market_listing_[a-f0-9]{32}")
_CURRENCY = re.compile(r"[A-Z]{3}")
_MARKET = re.compile(r"[A-Z0-9]{2,12}")

_CALENDAR_FIELDS = {"trading_date", "calendar_day_status", "calendar_reason"}
_CURRENT_FIELDS = {
    "trading_date",
    "day_status",
    "close_decimal",
    "valuation_status",
    "corporate_action_status",
}
_FETCHED_FIELDS = {"trading_date", "close_decimal", "corporate_action_status"}
_NORMALIZED_ABSENCE_FIELDS = {"trading_date", "normalization_kind"}
_CALENDAR_KINDS = {"exchange_calendar", "continuous_24_7"}
_CALENDAR_DAY_STATUSES = {"trading_day", "non_trading_day"}
_CURRENT_DAY_STATUSES = {"observed", "non_trading_day", "source_gap"}
_CORPORATE_ACTION_STATUSES = {"none_reported", "reconciled", "pending_review"}
_NORMALIZATION_KINDS = {"omitted", "null_marker", "manifest_zero_as_absence"}


def _abort(code: str) -> None:
    raise MarketHistoryReviewV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        _abort("market_history_review_boundary_failed")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _as_date(value: Any, code: str) -> date:
    if not isinstance(value, str):
        _abort(code)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _abort(code)
    if parsed.isoformat() != value:
        _abort(code)
    return parsed


def _positive_decimal(value: Any) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 80
        or _DECIMAL.fullmatch(value) is None
        or Fraction(value) <= 0
    ):
        _abort("market_history_review_candidate_invalid")
    return value


def _round_half_even(numerator: int, denominator: int) -> int:
    quotient, remainder = divmod(numerator, denominator)
    doubled = remainder * 2
    if doubled < denominator:
        return quotient
    if doubled > denominator:
        return quotient + 1
    return quotient if quotient % 2 == 0 else quotient + 1


def _plot_y(value: str | None, minimum: Fraction, maximum: Fraction) -> int | None:
    if value is None:
        return None
    if minimum == maximum:
        return 5000
    scaled = (Fraction(value) - minimum) * 10000 / (maximum - minimum)
    return _round_half_even(scaled.numerator, scaled.denominator)


def market_history_review_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(MarketHistoryReviewV1Error.CODES))


def _calendar_index(
    calendar_kind: str,
    start: date,
    end: date,
    rows: Any,
) -> dict[date, dict[str, str]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        _abort("market_history_review_calendar_invalid")
    expected_dates: list[date] = []
    cursor = start
    while cursor <= end:
        expected_dates.append(cursor)
        cursor += timedelta(days=1)
    if len(rows) != len(expected_dates):
        _abort("market_history_review_calendar_invalid")
    result: dict[date, dict[str, str]] = {}
    for expected, row in zip(expected_dates, rows):
        if not isinstance(row, Mapping) or set(row) != _CALENDAR_FIELDS:
            _abort("market_history_review_calendar_invalid")
        row_date = _as_date(row.get("trading_date"), "market_history_review_calendar_invalid")
        day_status = row.get("calendar_day_status")
        reason = row.get("calendar_reason")
        if row_date != expected or day_status not in _CALENDAR_DAY_STATUSES or not isinstance(reason, str):
            _abort("market_history_review_calendar_invalid")
        if calendar_kind == "continuous_24_7":
            if day_status != "trading_day" or reason != "continuous_market":
                _abort("market_history_review_calendar_invalid")
        elif day_status == "trading_day":
            if reason != "scheduled_session":
                _abort("market_history_review_calendar_invalid")
        elif reason not in {"weekend", "exchange_holiday"}:
            _abort("market_history_review_calendar_invalid")
        result[row_date] = {
            "trading_date": row_date.isoformat(),
            "calendar_day_status": day_status,
            "calendar_reason": reason,
        }
    return result


def _current_index(rows: Any, end: date) -> dict[date, dict[str, Any]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        _abort("market_history_review_input_invalid")
    result: dict[date, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != _CURRENT_FIELDS:
            _abort("market_history_review_input_invalid")
        row_date = _as_date(row.get("trading_date"), "market_history_review_input_invalid")
        day_status = row.get("day_status")
        close = row.get("close_decimal")
        valuation = row.get("valuation_status")
        corporate = row.get("corporate_action_status")
        if row_date > end or row_date in result or day_status not in _CURRENT_DAY_STATUSES:
            _abort("market_history_review_input_invalid")
        if day_status == "observed":
            close = _positive_decimal(close)
            if valuation not in {"eligible", "blocked"} or corporate not in _CORPORATE_ACTION_STATUSES:
                _abort("market_history_review_input_invalid")
            if (corporate == "pending_review") != (valuation == "blocked"):
                _abort("market_history_review_input_invalid")
        elif close is not None or valuation != "not_applicable" or corporate != "not_applicable":
            _abort("market_history_review_input_invalid")
        result[row_date] = {
            "trading_date": row_date.isoformat(),
            "day_status": day_status,
            "close_decimal": close,
            "valuation_status": valuation,
            "corporate_action_status": corporate,
        }
    return result


def _fetched_index(rows: Any, start: date, end: date) -> dict[date, dict[str, str]]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        _abort("market_history_review_candidate_invalid")
    result: dict[date, dict[str, str]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != _FETCHED_FIELDS:
            _abort("market_history_review_candidate_invalid")
        row_date = _as_date(row.get("trading_date"), "market_history_review_candidate_invalid")
        corporate = row.get("corporate_action_status")
        if row_date < start or row_date > end or row_date in result or corporate not in _CORPORATE_ACTION_STATUSES:
            _abort("market_history_review_candidate_invalid")
        result[row_date] = {
            "trading_date": row_date.isoformat(),
            "close_decimal": _positive_decimal(row.get("close_decimal")),
            "corporate_action_status": corporate,
        }
    return result


def _normalized_absence_index(rows: Any, start: date, end: date) -> dict[date, str]:
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        _abort("market_history_review_candidate_invalid")
    result: dict[date, str] = {}
    for row in rows:
        if not isinstance(row, Mapping) or set(row) != _NORMALIZED_ABSENCE_FIELDS:
            _abort("market_history_review_candidate_invalid")
        row_date = _as_date(row.get("trading_date"), "market_history_review_candidate_invalid")
        normalization_kind = row.get("normalization_kind")
        if (
            row_date < start
            or row_date > end
            or row_date in result
            or normalization_kind not in _NORMALIZATION_KINDS
        ):
            _abort("market_history_review_candidate_invalid")
        result[row_date] = normalization_kind
    return result


def _comparison(current: Mapping[str, Any] | None, candidate_status: str, candidate_close: str | None) -> str:
    if candidate_status == "observed":
        if current is None:
            return "new_observation"
        if current["day_status"] == "source_gap":
            return "gap_resolution_candidate"
        if current["day_status"] != "observed":
            return "correction_candidate"
        return "unchanged_observation" if current["close_decimal"] == candidate_close else "correction_candidate"
    if candidate_status == "non_trading_day":
        if current is None:
            return "new_calendar_day"
        if current["day_status"] == "observed":
            return "current_observation_retained"
        if current["day_status"] == "non_trading_day":
            return "unchanged_calendar_day"
        return "correction_candidate"
    if current is None:
        return "new_source_gap"
    if current["day_status"] == "observed":
        return "current_observation_retained"
    if current["day_status"] == "source_gap":
        return "unchanged_source_gap"
    return "correction_candidate"


def build_market_history_review_v1(
    *,
    review_ref: Any,
    listing_browser_ref: Any,
    quote_currency: Any,
    market_code: Any,
    calendar_kind: Any,
    scope_start_date: Any,
    scope_end_date: Any,
    calendar_days: Any,
    current_days: Any,
    fetched_days: Any,
    staged_candidate_fingerprint: Any,
    normalized_absence_days: Any = (),
) -> dict[str, Any]:
    """Return trusted binding plus a path-/Context-/fingerprint-free visual model."""

    if (
        not isinstance(review_ref, str)
        or _REVIEW_REF.fullmatch(review_ref) is None
        or not isinstance(listing_browser_ref, str)
        or _LISTING_BROWSER_REF.fullmatch(listing_browser_ref) is None
        or not isinstance(quote_currency, str)
        or _CURRENCY.fullmatch(quote_currency) is None
        or not isinstance(market_code, str)
        or _MARKET.fullmatch(market_code) is None
        or calendar_kind not in _CALENDAR_KINDS
        or not isinstance(staged_candidate_fingerprint, str)
        or _SHA256.fullmatch(staged_candidate_fingerprint) is None
    ):
        _abort("market_history_review_input_invalid")
    start = _as_date(scope_start_date, "market_history_review_input_invalid")
    end = _as_date(scope_end_date, "market_history_review_input_invalid")
    if end < start or (end - start).days + 1 > 3650:
        _abort("market_history_review_input_invalid")
    calendar = _calendar_index(calendar_kind, start, end, calendar_days)
    current = _current_index(current_days, end)
    fetched = _fetched_index(fetched_days, start, end)
    normalized_absence = _normalized_absence_index(normalized_absence_days, start, end)
    if any(
        calendar[row_date]["calendar_day_status"] != "non_trading_day" or row_date in fetched
        for row_date in normalized_absence
    ):
        _abort("market_history_review_candidate_invalid")

    preceding = [
        (row_date, row["close_decimal"])
        for row_date, row in current.items()
        if start - timedelta(days=3650) <= row_date < start
        and row["day_status"] == "observed"
        and row["valuation_status"] == "eligible"
    ]
    previous_date: date | None = None
    previous_close: str | None = None
    if preceding:
        previous_date, previous_close = max(preceding, key=lambda item: item[0])

    series: list[dict[str, Any]] = []
    all_warnings: set[str] = set()
    cursor = start
    x_ordinal = 0
    while cursor <= end:
        calendar_row = calendar[cursor]
        current_row = current.get(cursor)
        fetched_row = fetched.get(cursor)
        row_warnings: set[str] = set()
        candidate_close: str | None = None
        effective_close: str | None = None
        effective_source_date: date | None = None
        if fetched_row is not None:
            candidate_status = "observed"
            candidate_close = fetched_row["close_decimal"]
            if calendar_row["calendar_day_status"] == "non_trading_day":
                row_warnings.add("market_review_observation_on_non_trading_day")
            if fetched_row["corporate_action_status"] == "pending_review":
                effective_status = "unavailable_corporate_action"
                row_warnings.add("market_review_corporate_action_pending")
                previous_date = previous_close = None
            else:
                effective_close = candidate_close
                effective_source_date = cursor
                effective_status = "observed_candidate"
                previous_date, previous_close = cursor, candidate_close
        elif calendar_row["calendar_day_status"] == "non_trading_day":
            candidate_status = "non_trading_day"
            if cursor in normalized_absence:
                row_warnings.add("market_review_provider_closed_day_absence_normalized")
            if current_row is not None and current_row["day_status"] == "observed":
                if current_row["valuation_status"] == "eligible":
                    effective_close = current_row["close_decimal"]
                    effective_source_date = cursor
                    effective_status = "observed_current"
                    previous_date, previous_close = cursor, effective_close
                    row_warnings.add("market_review_current_observation_retained")
                    row_warnings.add("market_review_observation_on_non_trading_day")
                else:
                    effective_status = "unavailable_corporate_action"
                    previous_date = previous_close = None
                    row_warnings.add("market_review_corporate_action_pending")
            elif (
                previous_close is None
                or previous_date is None
                or (cursor - previous_date).days > 3650
            ):
                effective_status = "unavailable_no_predecessor"
                previous_date = previous_close = None
                row_warnings.add("market_review_non_trading_without_predecessor")
            else:
                effective_close = previous_close
                effective_source_date = previous_date
                effective_status = "imputed_non_trading_day"
                row_warnings.add("market_review_non_trading_close_carried_forward")
        else:
            candidate_status = "source_gap"
            row_warnings.add("market_review_source_gap")
            if current_row is not None and current_row["day_status"] == "observed":
                if current_row["valuation_status"] == "eligible":
                    effective_close = current_row["close_decimal"]
                    effective_source_date = cursor
                    effective_status = "observed_current"
                    previous_date, previous_close = cursor, effective_close
                    row_warnings.add("market_review_current_observation_retained")
                else:
                    effective_status = "unavailable_corporate_action"
                    previous_date = previous_close = None
                    row_warnings.add("market_review_corporate_action_pending")
            else:
                effective_status = "unavailable_source_gap"
                previous_date = previous_close = None
        comparison = _comparison(current_row, candidate_status, candidate_close)
        if comparison == "correction_candidate":
            row_warnings.add("market_review_candidate_correction")
        all_warnings.update(row_warnings)
        source_date_text = effective_source_date.isoformat() if effective_source_date is not None else None
        series.append(
            {
                "trading_date": cursor.isoformat(),
                "x_ordinal": x_ordinal,
                "calendar_day_status": calendar_row["calendar_day_status"],
                "calendar_reason": calendar_row["calendar_reason"],
                "candidate_day_status": candidate_status,
                "comparison_status": comparison,
                "current_close_decimal": current_row["close_decimal"] if current_row is not None and current_row["day_status"] == "observed" else None,
                "candidate_close_decimal": candidate_close,
                "effective_close_decimal": effective_close,
                "effective_close_status": effective_status,
                "source_observation_date": source_date_text,
                "effective_close_age_days": (cursor - effective_source_date).days if effective_source_date is not None else None,
                "plot_style": "dashed" if effective_status == "imputed_non_trading_day" else "gap" if effective_close is None else "solid",
                "current_plot_y": None,
                "candidate_plot_y": None,
                "effective_plot_y": None,
                "warning_codes": sorted(row_warnings),
            }
        )
        cursor += timedelta(days=1)
        x_ordinal += 1

    plotted_values = [
        value
        for row in series
        for value in (row["current_close_decimal"], row["candidate_close_decimal"], row["effective_close_decimal"])
        if value is not None
    ]
    if plotted_values:
        minimum_text = min(plotted_values, key=Fraction)
        maximum_text = max(plotted_values, key=Fraction)
        minimum = Fraction(minimum_text)
        maximum = Fraction(maximum_text)
        for row in series:
            row["current_plot_y"] = _plot_y(row["current_close_decimal"], minimum, maximum)
            row["candidate_plot_y"] = _plot_y(row["candidate_close_decimal"], minimum, maximum)
            row["effective_plot_y"] = _plot_y(row["effective_close_decimal"], minimum, maximum)
    else:
        minimum_text = maximum_text = None

    summary = {
        "calendar_day_count": len(series),
        "observed_candidate_count": sum(row["candidate_day_status"] == "observed" for row in series),
        "non_trading_day_count": sum(row["candidate_day_status"] == "non_trading_day" for row in series),
        "source_gap_count": sum(row["candidate_day_status"] == "source_gap" for row in series),
        "imputed_non_trading_day_count": sum(row["effective_close_status"] == "imputed_non_trading_day" for row in series),
        "correction_candidate_count": sum(row["comparison_status"] == "correction_candidate" for row in series),
        "unavailable_effective_close_count": sum(row["effective_close_decimal"] is None for row in series),
        "warning_count": len(all_warnings),
    }
    public_review = {
        "market_history_review_version": 1,
        "status": "ready_with_warnings" if all_warnings else "ready",
        "review_ref": review_ref,
        "listing_browser_ref": listing_browser_ref,
        "quote_currency": quote_currency,
        "market_code": market_code,
        "calendar_kind": calendar_kind,
        "scope_start_date": start.isoformat(),
        "scope_end_date": end.isoformat(),
        "plot_scale_min_decimal": minimum_text,
        "plot_scale_max_decimal": maximum_text,
        "series": series,
        "summary": summary,
        "warning_codes": sorted(all_warnings),
        "machine_validation_status": "passed",
        "visual_review_required": True,
        "publish_confirmation_required": True,
        "fetch_attempt_consumed": True,
        "staged_candidate_persisted": True,
        "candidate_fingerprint_exposed": False,
        "provider_access": False,
        "network_access": False,
        "market_history_write": False,
        "canonical_write": False,
        "tax_write": False,
        "reward_valuation_write": False,
        "automatic_retry": False,
        "path_exposed": False,
        "context_exposed": False,
        "internal_id_exposed": False,
    }
    trusted_body = {
        "market_history_trusted_review_version": 1,
        "review_ref": review_ref,
        "staged_candidate_fingerprint": staged_candidate_fingerprint,
        "public_review_fingerprint": _fingerprint(public_review),
    }
    return {
        "trusted_review": {
            **trusted_body,
            "trusted_review_fingerprint": _fingerprint(trusted_body),
        },
        "public_review": public_review,
    }


def confirm_market_history_review_v1(
    review_bundle: Any,
    public_review: Any,
    confirmed: Any,
) -> dict[str, Any]:
    """Bind publication authority to one exact staged Candidate without publishing it."""

    if not isinstance(review_bundle, Mapping) or set(review_bundle) != {"trusted_review", "public_review"}:
        _abort("market_history_review_input_invalid")
    trusted = review_bundle.get("trusted_review")
    stored_public = review_bundle.get("public_review")
    if not isinstance(trusted, Mapping) or not isinstance(stored_public, Mapping) or not isinstance(public_review, Mapping):
        _abort("market_history_review_input_invalid")
    expected_trusted_fields = {
        "market_history_trusted_review_version",
        "review_ref",        "staged_candidate_fingerprint",
        "public_review_fingerprint",
        "trusted_review_fingerprint",
    }
    if set(trusted) != expected_trusted_fields or trusted.get("market_history_trusted_review_version") != 1:
        _abort("market_history_review_input_invalid")
    trusted_body = {key: trusted[key] for key in expected_trusted_fields if key != "trusted_review_fingerprint"}
    if confirmed is not True:
        _abort("market_history_review_confirmation_required")
    if (
        _canonical(stored_public) != _canonical(public_review)
        or trusted.get("public_review_fingerprint") != _fingerprint(public_review)
        or trusted.get("trusted_review_fingerprint") != _fingerprint(trusted_body)
    ):
        _abort("market_history_review_stale")
    candidate_fingerprint = trusted.get("staged_candidate_fingerprint")
    review_ref = trusted.get("review_ref")
    if (
        not isinstance(candidate_fingerprint, str)
        or _SHA256.fullmatch(candidate_fingerprint) is None
        or not isinstance(review_ref, str)
        or _REVIEW_REF.fullmatch(review_ref) is None
        or public_review.get("review_ref") != review_ref
        or public_review.get("machine_validation_status") != "passed"
        or public_review.get("publish_confirmation_required") is not True
    ):
        _abort("market_history_review_input_invalid")
    confirmation_body = {
        "market_history_review_confirmation_version": 1,
        "review_ref": review_ref,
        "staged_candidate_fingerprint": candidate_fingerprint,
        "public_review_fingerprint": trusted["public_review_fingerprint"],
        "publication_authorized": True,
        "provider_refetch_authorized": False,
        "automatic_retry": False,
    }
    return {
        **confirmation_body,
        "confirmation_fingerprint": _fingerprint(confirmation_body),
    }


__all__ = [
    "MarketHistoryReviewV1Error",
    "build_market_history_review_v1",
    "confirm_market_history_review_v1",
    "market_history_review_v1_error_codes",
]
