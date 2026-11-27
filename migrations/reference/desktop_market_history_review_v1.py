#!/usr/bin/env python3
"""Owner-local staged Daily Market History review and publication boundary.

The default transport is network-capable but is invoked only by the separately
confirmed stage operation. Contract tests inject an invented transport. Fetch
writes only an owner-local sealed stage; publication performs no provider call.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import base64
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Callable, Mapping

from migrations.reference.daily_market_history_v1 import (
    DailyMarketHistoryBlocked,
    MarketHistoryContext,
    append_daily_market_history_v1,
    daily_market_history_job_binding_fingerprint_v1,
    new_daily_market_listing_binding_v1,
    read_daily_market_history_v1,
    read_daily_market_listing_binding_v1,
    read_daily_market_listing_bound_at_v1,
    read_daily_market_request_receipt_v1,
    seal_daily_market_history_candidate_v1,
    validate_daily_market_candidate_for_listing_v1,
)
from migrations.reference.desktop_market_history_fetch_v1 import (
    _DOMAIN_FIELDS,
    _compare_candidate,
    _range_days,
)
from migrations.reference.desktop_market_history_plan_v1 import (
    DesktopMarketHistoryPlanV1Error,
    plan_desktop_market_history_v1,
)
from migrations.reference import price_provider_plugins_v1 as price_providers
from migrations.reference.desktop_provider_probe_v1 import (
    BYTE_LIMIT,
    PROVIDER_ID,
    TIMEOUT,
    _default_transport,
    core_transport_v1,
    history_provider_v1,
    with_observation_refs_v1,
)
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA, STORE_NAME
from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1
from workers.reference.market_history_review_v1 import (
    MarketHistoryReviewV1Error,
    build_market_history_review_v1,
    confirm_market_history_review_v1,
)
from workers.reference.semantic_realized_fifo_v1 import (
    context_values as semantic_context_values,
    public_ref as semantic_public_ref,
)

AREA = "desktop-market-history-review-v1"
MAX_RANGE_DAYS = 3650
MODES = frozenset({"incremental", "retry_source_gaps", "full_refresh"})
FAILURE_CODES = frozenset(
    {
        "desktop_market_history_review_boundary_failed",
        "desktop_market_history_review_discard_invalid",
        "desktop_market_history_review_confirmation_required",
        "desktop_market_history_review_context_invalid",
        "desktop_market_history_review_fetch_attempt_consumed",
        "desktop_market_history_review_input_invalid",
        "desktop_market_history_review_preview_invalid",
        "desktop_market_history_review_publication_invalid",
        "desktop_market_history_review_publish_attempt_consumed",
        "desktop_market_history_review_publish_write_failed",
        "desktop_market_history_review_recovery_required",
        "desktop_market_history_review_rejected",
        "desktop_market_history_review_response_invalid",
        "desktop_market_history_review_source_not_listed",
        "desktop_market_history_review_source_rejected",
        "desktop_market_history_review_response_currency_mismatch",
        "desktop_market_history_review_response_timezone_mismatch",
        "desktop_market_history_review_stage_invalid",
        "desktop_market_history_review_store_invalid",
        "desktop_market_history_review_transport_failed",
        "desktop_market_history_review_fetch_interrupted",
        "desktop_market_history_review_credential_unavailable",
        "desktop_market_history_review_cost_limit",
        "desktop_market_history_review_scheduled_disabled",
        "market_history_review_boundary_failed",
        "market_history_review_calendar_invalid",
        "market_history_review_candidate_invalid",
        "market_history_review_confirmation_required",
        "market_history_review_input_invalid",
        "market_history_review_stale",
    }
)

_SHA = re.compile(r"^[a-f0-9]{64}$")
_NONCE = re.compile(r"^mhn_[A-Za-z0-9_-]{12,64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_STAGE_REF = re.compile(r"^mhs_[a-f0-9]{32}$")
_REVIEW_REF = re.compile(r"^mhr_[a-f0-9]{32}$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


class DesktopMarketHistoryReviewV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("desktop_market_history_review_error_unregistered")
        self.code = code
        super().__init__(code)


def desktop_market_history_review_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise DesktopMarketHistoryReviewV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_boundary_failed"
        ) from error


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-canonical JSON constant: {value}")


def _catalog_sha(value: Any) -> str:
    """Match the UTF-8 canonical JSON used by native catalog commands."""
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_boundary_failed"
        ) from error
    return hashlib.sha256(payload).hexdigest()


def _sha(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _context(value: Any) -> DesktopProviderSearchContextV1:
    if isinstance(value, Mapping):
        try:
            value = DesktopProviderSearchContextV1(
                value["tenant_id"],
                value["user_id"],
                value["data_space_id"],
                value.get("actor_id", "market_worker"),
                value.get("role", "market_worker"),
            )
        except (KeyError, TypeError) as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_context_invalid"
            ) from error
    if (
        not isinstance(value, DesktopProviderSearchContextV1)
        or value.actor_id != "market_worker"
        or value.role != "market_worker"
        or any(
            not isinstance(item, str)
            or re.fullmatch(r"^[A-Za-z0-9_-]{3,64}$", item) is None
            for item in (value.tenant_id, value.user_id, value.data_space_id)
        )
        or not value.data_space_id.startswith("sbx_")
    ):
        _abort("desktop_market_history_review_context_invalid")
    return value


def _context_fingerprint(value: Any) -> str:
    current = _context(value)
    return _sha(
        {
            "contract": "desktop_market_history_review_context_v1",
            "tenant_id": current.tenant_id,
            "user_id": current.user_id,
            "data_space_id": current.data_space_id,
            "actor_id": current.actor_id,
            "role": current.role,
        }
    )


def _as_utc(value: Any, code: str = "desktop_market_history_review_input_invalid") -> str:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort(code)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _abort(code)
    return value


def _now(clock: Callable[[], datetime]) -> str:
    try:
        value = clock()
    except Exception as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_input_invalid"
        ) from error
    if not isinstance(value, datetime) or value.utcoffset() is None:
        _abort("desktop_market_history_review_input_invalid")
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _system_boot_utc() -> str | None:
    """Zeitpunkt des letzten Systemstarts (Linux: btime in /proc/stat), sonst None.

    Ein Abrufversuch, der davor begann, kann nicht mehr laufen: Sein Prozess hat den Neustart nicht ueberlebt. Nur daran
    erkennt die Wiederherstellung einen unterbrochenen Versuch sicher - die Sperre der Notierung ist waehrend des Netzabrufs
    frei und unterscheidet "unterbrochen" nicht von "laeuft noch".
    """
    try:
        with open("/proc/stat", "r", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("btime "):
                    return datetime.fromtimestamp(int(line.split()[1]), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OSError, ValueError, IndexError):
        return None
    return None


def _as_date(value: Any) -> date:
    if not isinstance(value, str):
        _abort("desktop_market_history_review_input_invalid")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _abort("desktop_market_history_review_input_invalid")
    if parsed.isoformat() != value:
        _abort("desktop_market_history_review_input_invalid")
    return parsed


def _listing_binding(value: Any, code: str) -> dict[str, Any]:
    fields = {
        "contract_version",
        "listing_ref",
        "asset_ref",
        "quote_currency",
        "market_code",
        "timezone_name",
        "calendar_code",
        "valuation_price_policy",
        "catalog_fingerprint",
        "listing_fingerprint",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        _abort(code)
    try:
        expected = new_daily_market_listing_binding_v1(
            listing_ref=value["listing_ref"],
            asset_ref=value["asset_ref"],
            quote_currency=value["quote_currency"],
            market_code=value["market_code"],
            timezone_name=value["timezone_name"],
            calendar_code=value["calendar_code"],
            catalog_fingerprint=value["catalog_fingerprint"],
        )
    except (DailyMarketHistoryBlocked, KeyError, TypeError) as error:
        raise DesktopMarketHistoryReviewV1Error(code) from error
    if dict(value) != expected:
        _abort(code)
    return expected


def _mapping(value: Any) -> dict[str, Any]:
    fields = {
        "mapping_id",
        "mapping_revision",
        "asset_id",
        "provider_id",
        "provider_symbol",
        "provider_currency",
        "capability",
        "mapping_fingerprint",
        "catalog_fingerprint",
        "verification_status",
        "enabled",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or history_provider_v1(value.get("provider_id")) is None
        or value.get("capability") != "daily_history"
        or value.get("verification_status") != "verified"
        or value.get("enabled") is not True
        or not isinstance(value.get("mapping_id"), str)
        or re.fullmatch(r"^map_[a-z0-9_]{4,60}$", value["mapping_id"]) is None
        or len(value["mapping_id"].encode("utf-8")) > 64
        or not isinstance(value.get("asset_id"), str)
        or re.fullmatch(r"^ast_[a-z0-9_]{4,60}$", value["asset_id"]) is None
        or len(value["asset_id"].encode("utf-8")) > 64
        or type(value.get("mapping_revision")) is not int
        or value["mapping_revision"] < 1
        or not isinstance(value.get("provider_symbol"), str)
        or not 1 <= len(value["provider_symbol"].encode("utf-8")) <= 120
        or value["provider_symbol"] != value["provider_symbol"].strip()
        or any(character in value["provider_symbol"] for character in "\r\n\t")
        or not isinstance(value.get("provider_currency"), str)
        or re.fullmatch(r"^[A-Z]{3}$", value["provider_currency"]) is None
        or not isinstance(value.get("mapping_fingerprint"), str)
        or _SHA.fullmatch(value["mapping_fingerprint"]) is None
        or not isinstance(value.get("catalog_fingerprint"), str)
        or _SHA.fullmatch(value["catalog_fingerprint"]) is None
    ):
        _abort("desktop_market_history_review_input_invalid")
    return dict(value)


def _promotion_binding(
    value: Any,
    listing: Mapping[str, Any],
    mapping: Mapping[str, Any],
    context: DesktopProviderSearchContextV1 | None = None,
) -> dict[str, Any]:
    fields = {
        "listing_ref",
        "listing_fingerprint",
        "mapping_id",
        "mapping_revision",
        "mapping_fingerprint",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != fields
        or value.get("listing_ref") != listing.get("listing_ref")
        or value.get("listing_fingerprint") != listing.get("listing_fingerprint")
        or value.get("mapping_id") != mapping.get("mapping_id")
        or type(value.get("mapping_revision")) is not int
        or value["mapping_revision"] < 1
        or not isinstance(value.get("mapping_fingerprint"), str)
        or _SHA.fullmatch(value["mapping_fingerprint"]) is None
    ):
        _abort("desktop_market_history_review_input_invalid")
    if context is not None:
        _, _, _, semantic_context_fingerprint = semantic_context_values(
            {
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "data_space_id": context.data_space_id,
            }
        )
        expected_listing_ref = "lsr_" + _sha(
            {
                "contract": "desktop_provider_listing_v1",
                "context": semantic_context_fingerprint,
                "mapping_id": value["mapping_id"],
                "mapping_revision": value["mapping_revision"],
                "market_code": listing.get("market_code"),
                "timezone_name": listing.get("timezone_name"),
                "calendar_code": listing.get("calendar_code"),
            }
        )[:32]
        expected_asset_ref = semantic_public_ref(
            "asf_", semantic_context_fingerprint, mapping["asset_id"]
        )
        if (
            listing.get("listing_ref") != expected_listing_ref
            or listing.get("asset_ref") != expected_asset_ref
        ):
            _abort("desktop_market_history_review_input_invalid")
    same_revision = (
        mapping["mapping_revision"] == value["mapping_revision"]
        and mapping["mapping_fingerprint"] == value["mapping_fingerprint"]
    )
    verified_successor = mapping["mapping_revision"] == value["mapping_revision"] + 1
    if not (same_revision or verified_successor):
        _abort("desktop_market_history_review_input_invalid")
    return dict(value)


def _owner_directory(path: Path) -> Path:
    try:
        absolute = Path(os.path.abspath(path))
        resolved = path.resolve(strict=True)
        metadata = path.stat(follow_symlinks=False)
    except (OSError, TypeError, ValueError) as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    wrong_owner = hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
    if (
        absolute != resolved
        or path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or wrong_owner
    ):
        _abort("desktop_market_history_review_store_invalid")
    return resolved


def _data_space(path: str | Path, context: DesktopProviderSearchContextV1) -> Path:
    try:
        result = _owner_directory(Path(path))
    except (TypeError, ValueError) as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    if result.name != context.data_space_id:
        _abort("desktop_market_history_review_store_invalid")
    return result


def _ensure(parent: Path, name: str) -> Path:
    parent = _owner_directory(parent)
    target = parent / name
    if not target.exists():
        try:
            os.mkdir(target, 0o700)
            os.chmod(target, 0o700)
        except FileExistsError:
            # A concurrent owner process may have materialized the same
            # directory after the optimistic existence check.
            pass
        except OSError as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_store_invalid"
            ) from error
    return _owner_directory(target)


def _write_create(path: Path, value: Any, exists_code: str) -> None:
    descriptor: int | None = None
    directory_descriptor: int | None = None
    try:
        parent = _owner_directory(path.parent)
        payload = _canonical(value) + b"\n"
        if len(payload) > 32_000_000:
            _abort("desktop_market_history_review_store_invalid")
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short sealed evidence write")
            offset += written
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            _abort("desktop_market_history_review_store_invalid")
        os.close(descriptor)
        descriptor = None
        directory_descriptor = os.open(
            parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        os.fsync(directory_descriptor)
    except FileExistsError:
        _abort(exists_code)
    except DesktopMarketHistoryReviewV1Error:
        raise
    except OSError as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)


@contextmanager
def _listing_lock(area: Path, listing_ref: str):
    if not isinstance(listing_ref, str) or re.fullmatch(r"^lsr_[a-f0-9]{32}$", listing_ref) is None:
        _abort("desktop_market_history_review_input_invalid")
    locks = _ensure(area, "locks")
    path = locks / f"{listing_ref}.lock"
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            _abort("desktop_market_history_review_store_invalid")
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except DesktopMarketHistoryReviewV1Error:
        raise
    except OSError as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    finally:
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)


def _plugin_outcome(params: Mapping[str, Any], response: Mapping[str, Any], provider_id: str = PROVIDER_ID) -> dict[str, Any]:
    """Einordnung und Auswertung einer Antwort durch das Kursanbieter-Plugin der Zuordnung (rc.394); jede Stoerung des Plugins gilt
    als ungueltige Antwort."""
    body = response.get("body")
    content_type = response.get("headers", {}).get("content-type") if isinstance(response.get("headers"), dict) else None
    try:
        return price_providers.parse_response_v1(
            provider_id,
            "daily_history",
            params,
            {
                "status": response["status"],
                "content_type": content_type if isinstance(content_type, str) else None,
                "body": body if isinstance(body, bytes) else b"",
            },
        )
    except price_providers.PriceProviderBlocked:
        return {"outcome": "invalid"}


def _notation_ref(context: Any, provider_symbol: str, provider_id: str = "yahoo") -> str:
    return "nor_" + _sha(
        {
            "contract": "desktop_market_history_notation_v1",
            "context": _context_fingerprint(context),
            "provider_id": provider_id,
            "provider_symbol": provider_symbol,
        }
    )[:32]


def _notation_path(space: Path, context: Any, provider_symbol: str, provider_id: str = "yahoo") -> Path:
    return _ensure(_ensure(space, AREA), "notations") / f"{_notation_ref(context, provider_symbol, provider_id)}.json"


def _write_notation(space: Path, context: Any, provider_symbol: str, first_trade_date: str, observed_at_utc: str,
                    provider_id: str = "yahoo") -> None:
    # Die Erstnotiz gehoert zum Anbietersymbol, nicht zur Notierungsbindung:
    # Eine erneuerte Einrichtung legt eine neue, leere Bindung an, die Erstnotiz
    # des Titels bleibt dieselbe. Sie steht deshalb unter dem Symbol und
    # ueberlebt jede Erneuerung (25.09.2026, #283).
    record = {
        "contract_version": "desktop_market_history_notation_v1",
        "notation_ref": _notation_ref(context, provider_symbol, provider_id),
        "context_fingerprint": _context_fingerprint(context),
        "provider_id": provider_id,
        "provider_symbol": provider_symbol,
        "first_trade_date": first_trade_date,
        "observed_at_utc": observed_at_utc,
    }
    record["notation_fingerprint"] = _sha(record)
    path = _notation_path(space, context, provider_symbol, provider_id)
    existing = _read_notation_path(path)
    if existing is not None and existing["first_trade_date"] == first_trade_date:
        return
    temporary = path.with_name(path.name + ".partial")
    try:
        if temporary.exists():
            os.unlink(temporary)
    except OSError:
        return
    try:
        _write_create(temporary, record, "desktop_market_history_review_store_invalid")
        os.replace(temporary, path)
    except (DesktopMarketHistoryReviewV1Error, OSError):
        try:
            os.unlink(temporary)
        except OSError:
            pass


def _read_notation_path(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = _read_sealed(
            path, "notation_fingerprint", "desktop_market_history_review_store_invalid"
        )
    except DesktopMarketHistoryReviewV1Error:
        return None
    if (
        value.get("contract_version") != "desktop_market_history_notation_v1"
        or not isinstance(value.get("first_trade_date"), str)
        or _DAY.fullmatch(value["first_trade_date"]) is None
    ):
        return None
    return value


def read_desktop_market_history_notations_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
) -> list[dict[str, Any]]:
    """Alle festgehaltenen Erstnotizen auf einmal.

    Die Vorbereitung eines Sammellaufs fragte sie je Asset einzeln ab; das waren viele
    Prozessstarts, nur um eine Datumsangabe zu lesen. Ein Aufruf genuegt (#283).
    """
    current_context = _context(context)
    space = _data_space(data_space_path, current_context)
    folder = _ensure(_ensure(space, AREA), "notations")
    records = []
    for path in sorted(folder.glob("nor_*.json")):
        value = _read_notation_path(path)
        if value is None or value["context_fingerprint"] != _context_fingerprint(current_context):
            continue
        records.append({"provider_symbol": value["provider_symbol"],
                        "first_trade_date": value["first_trade_date"],
                        "observed_at_utc": value["observed_at_utc"]})
    return records


def read_desktop_market_history_notation_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    provider_symbol: str,
) -> dict[str, Any] | None:
    """Return the recorded first notation of a provider symbol, or None."""
    current_context = _context(context)
    if not isinstance(provider_symbol, str) or not 1 <= len(provider_symbol) <= 64:
        _abort("desktop_market_history_review_input_invalid")
    space = _data_space(data_space_path, current_context)
    value = _read_notation_path(_notation_path(space, current_context, provider_symbol))
    if value is None:
        return None
    return {
        "contract_version": "desktop_market_history_notation_public_v1",
        "status": "known",
        "provider_symbol": value["provider_symbol"],
        "first_trade_date": value["first_trade_date"],
        "observed_at_utc": value["observed_at_utc"],
        "provider_access": False,
        "network_access": False,
        "canonical_write": False,
        "market_history_write": False,
        "automatic_retry": False,
        "paths_exposed": False,
        "fingerprints_exposed": False,
    }


def _read_sealed(path: Path, fingerprint_field: str, invalid_code: str) -> dict[str, Any]:
    descriptor: int | None = None
    try:
        _owner_directory(path.parent)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 32_000_000
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            _abort(invalid_code)
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(1_048_576, 32_000_001 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > 32_000_000:
                _abort(invalid_code)
        value = json.loads(
            bytes(payload).decode("utf-8"), parse_constant=_reject_json_constant
        )
    except DesktopMarketHistoryReviewV1Error:
        raise
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise DesktopMarketHistoryReviewV1Error(invalid_code) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if not isinstance(value, dict):
        _abort(invalid_code)
    fingerprint = value.pop(fingerprint_field, None)
    if not isinstance(fingerprint, str) or fingerprint != _sha(value):
        _abort(invalid_code)
    value[fingerprint_field] = fingerprint
    if bytes(payload) != _canonical(value) + b"\n":
        _abort(invalid_code)
    return value


def _listing_browser_ref(listing: Mapping[str, Any]) -> str:
    return "market_listing_" + _sha(
        {
            "contract": "desktop_market_history_review_browser_listing_v1",
            "listing_fingerprint": listing["listing_fingerprint"],
        }
    )[:32]


def _calendar_kind(calendar_code: str) -> str:
    if calendar_code == "continuous_24_7":
        return "continuous_24_7"
    if calendar_code == "weekday_exchange":
        return "exchange_calendar"
    _abort("market_history_review_calendar_invalid")


def _calendar_rows(listing: Mapping[str, Any], start: date, end: date) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    cursor = start
    while cursor <= end:
        if listing["calendar_code"] == "continuous_24_7":
            status, reason = "trading_day", "continuous_market"
        elif listing["calendar_code"] == "weekday_exchange" and cursor.weekday() >= 5:
            status, reason = "non_trading_day", "weekend"
        elif listing["calendar_code"] == "weekday_exchange":
            status, reason = "trading_day", "scheduled_session"
        else:
            _abort("market_history_review_calendar_invalid")
        result.append(
            {
                "trading_date": cursor.isoformat(),
                "calendar_day_status": status,
                "calendar_reason": reason,
            }
        )
        cursor += timedelta(days=1)
    return result


def _current_review_rows(history: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in history["days"]:
        if source["day_status"] == "not_requested":
            continue
        corporate = source["corporate_action_status"]
        if corporate == "explicitly_reconciled":
            corporate = "reconciled"
        valuation = source["valuation_status"]
        if valuation == "blocked_corporate_action":
            valuation = "blocked"
        result.append(
            {
                "trading_date": source["trading_date"],
                "day_status": source["day_status"],
                "close_decimal": source["close_decimal"],
                "valuation_status": valuation,
                "corporate_action_status": corporate,
            }
        )
    return result


def _fetched_review_rows(parsed: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "trading_date": row["trading_date"],
            "close_decimal": row["close_decimal"],
            "corporate_action_status": row["corporate_action_status"],
        }
        for row in parsed["days"]
        if row["day_status"] == "observed"
    ]


def _absence_rows(
    parsed: Mapping[str, Any], calendar_rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    by_date = {row["trading_date"]: row for row in parsed["days"]}
    return [
        {
            "trading_date": row["trading_date"],
            "normalization_kind": (
                "null_marker"
                if row["trading_date"] in by_date
                and by_date[row["trading_date"]]["day_status"] == "source_gap"
                else "omitted"
            ),
        }
        for row in calendar_rows
        if row["calendar_day_status"] == "non_trading_day"
        and not (
            row["trading_date"] in by_date
            and by_date[row["trading_date"]]["day_status"] == "observed"
        )
    ]


def _retain_current_observations_on_dropout(
    candidate: Mapping[str, Any], current_history: Mapping[str, Any]
) -> dict[str, Any]:
    """A provider absence cannot erase a currently eligible observed bar."""
    current = {row["trading_date"]: row for row in current_history["days"]}
    days: list[dict[str, Any]] = []
    for raw in candidate["days"]:
        row = dict(raw)
        prior = current[row["trading_date"]]
        if (
            prior["day_status"] == "observed"
            and prior["valuation_status"] == "eligible"
            and row["day_status"] == "source_gap"
        ):
            for field in (*_DOMAIN_FIELDS, "source_observation_ref", "observed_at_utc"):
                row[field] = prior[field]
        days.append(row)
    return {**candidate, "days": days}


def _compare_for_publication(
    candidate: Mapping[str, Any], current_history: Mapping[str, Any], listing: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        retained = _retain_current_observations_on_dropout(candidate, current_history)
        result = _compare_candidate(retained, current_history, listing)
        return validate_daily_market_candidate_for_listing_v1(result, listing)
    except Exception as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_response_invalid"
        ) from error


def _market_store(space: Path) -> Path:
    target = space / MARKET_AREA / STORE_NAME
    _owner_directory(target.parent)
    if not target.is_file() or target.is_symlink():
        _abort("desktop_market_history_review_store_invalid")
    return target


def _validate_current_mapping(
    space: Path, mapping: Mapping[str, Any]
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    current = _mapping(mapping)
    database = space / "canonical.sqlite"
    descriptor: int | None = None
    connection: sqlite3.Connection | None = None
    try:
        descriptor = os.open(
            database, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600}
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            _abort("desktop_market_history_review_store_invalid")
        uri = f"file:/proc/self/fd/{descriptor}?mode=ro&immutable=1"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        row = connection.execute(
            """
            SELECT mapping_id,asset_id,capability,provider_id,provider_symbol,
                   exchange_code,mic_code,provider_currency,verification_status,
                   expert_only,enabled,verified_at_utc,created_at_utc,updated_at_utc,revision
              FROM provider_mapping
             WHERE mapping_id=?
            """,
            (current["mapping_id"],),
        ).fetchone()
        audits = connection.execute(
            """
            SELECT command_id,command_type,entity_id,actor_id,committed_at_utc,
                   payload_fingerprint,origin_type,origin_ref
              FROM data_command_audit
             WHERE area_id='provider_mapping' AND entity_id=?
             ORDER BY committed_at_utc DESC,command_id DESC
             LIMIT 2
            """,
            (current["mapping_id"],),
        ).fetchall()
        asset = connection.execute(
            "SELECT asset_id, valuation_method FROM asset WHERE asset_id=? AND status='active'",
            (current["asset_id"],),
        ).fetchone()
        # Heute am Markt bewertet - oder die Bewertungs-Zeitleiste fuehrt einen Marktabschnitt mit genau dieser Reihe (rc.393):
        # Dann bleibt sie abruf- und bewertbar, auch wenn das Asset heute eigene Kurse traegt; sonst ginge sie beim Neuaufbau
        # des Bewertungsstands verloren.
        if asset is not None and asset[1] != "external_market" and not _timeline_keeps_series(space, current):
            asset = None
        check = connection.execute("PRAGMA quick_check").fetchone()
    except DesktopMarketHistoryReviewV1Error:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    finally:
        if connection is not None:
            connection.close()
        if descriptor is not None:
            os.close(descriptor)
    if row is None or asset is None or check is None or check[0] != "ok" or not audits:
        _abort("desktop_market_history_review_store_invalid")
    audit = audits[0]
    row_value = dict(row)
    row_fingerprint = _catalog_sha(
        {
            "provider_mapping_state_version": 1,
            "provider_mapping": row_value,
        }
    )
    row_matches = (
        row["mapping_id"] == current["mapping_id"]
        and row["asset_id"] == current["asset_id"]
        and row["capability"] == current["capability"]
        and row["provider_id"] == current["provider_id"]
        and row["provider_symbol"] == current["provider_symbol"]
        and (row["exchange_code"] is None or isinstance(row["exchange_code"], str))
        and (row["mic_code"] is None or isinstance(row["mic_code"], str))
        and row["provider_currency"] == current["provider_currency"]
        and row["verification_status"] == "verified"
        and type(row["expert_only"]) is int
        and row["expert_only"] in {0, 1}
        and type(row["enabled"]) is int
        and row["enabled"] == 1
        and type(row["revision"]) is int
        and row["revision"] == current["mapping_revision"]
        and row_fingerprint == current["mapping_fingerprint"]
    )
    audit_matches = (
        audit["entity_id"] == current["mapping_id"]
        and isinstance(audit["actor_id"], str)
        and bool(audit["actor_id"])
        and audit["committed_at_utc"] == row["updated_at_utc"]
        and audit["payload_fingerprint"] == row_fingerprint
        and isinstance(audit["command_type"], str)
        and (
            re.fullmatch(
                r"provider_mapping_verify_v1_[a-f0-9]{48}",
                audit["command_type"],
            )
            is not None
        )
        and audit["origin_type"] == "native"
        and audit["origin_ref"] is None
        and not (
            len(audits) > 1
            and audits[1]["committed_at_utc"] == audit["committed_at_utc"]
        )
    )
    if not row_matches or not audit_matches:
        _abort("desktop_market_history_review_input_invalid")
    try:
        created_at = _as_utc(row["created_at_utc"])
        verified_at = _as_utc(row["verified_at_utc"])
        updated_at = _as_utc(row["updated_at_utc"])
    except DesktopMarketHistoryReviewV1Error as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_input_invalid"
        ) from error
    if created_at > verified_at or verified_at != updated_at:
        _abort("desktop_market_history_review_input_invalid")
    return current, tuple(dict(item) for item in audits)


def _validate_promotion_audit(
    binding: Mapping[str, Any],
    mapping: Mapping[str, Any],
    audits: tuple[dict[str, Any], ...],
) -> None:
    if mapping["mapping_revision"] == binding["mapping_revision"]:
        return
    if len(audits) != 2:
        _abort("desktop_market_history_review_input_invalid")
    previous = audits[1]
    if (
        mapping["mapping_revision"] != binding["mapping_revision"] + 1
        or previous.get("entity_id") != mapping["mapping_id"]
        or previous.get("payload_fingerprint") != binding["mapping_fingerprint"]
        or not isinstance(previous.get("actor_id"), str)
        or not previous["actor_id"]
        or not isinstance(previous.get("command_type"), str)
        or re.fullmatch(
            r"provider_mapping_(?:create|revise)_v1(?:_[a-f0-9]{48})?",
            previous["command_type"],
        ) is None
        or previous.get("origin_type") != "native"
        or previous.get("origin_ref") is not None
        or not isinstance(previous.get("committed_at_utc"), str)
        or previous["committed_at_utc"] >= audits[0]["committed_at_utc"]
    ):
        _abort("desktop_market_history_review_input_invalid")
    _as_utc(previous["committed_at_utc"])


def _asset_commands_since(space: Path, asset_id: str, since_utc: str) -> tuple[dict[str, Any], ...]:
    database = space / "canonical.sqlite"
    descriptor: int | None = None
    connection: sqlite3.Connection | None = None
    try:
        descriptor = os.open(database, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) not in {0o400, 0o600}
            or (hasattr(os, "geteuid") and metadata.st_uid != os.geteuid())
        ):
            _abort("desktop_market_history_review_store_invalid")
        connection = sqlite3.connect(
            f"file:/proc/self/fd/{descriptor}?mode=ro&immutable=1", uri=True
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(
            """
            SELECT command_type,origin_type,origin_ref
              FROM data_command_audit
             WHERE entity_id=? AND committed_at_utc>=?
            """,
            (asset_id, since_utc),
        ).fetchall()
    except DesktopMarketHistoryReviewV1Error:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    finally:
        if connection is not None:
            connection.close()
        if descriptor is not None:
            os.close(descriptor)
    return tuple(dict(row) for row in rows)


# Seit rc.393 auch der Wechsel der Bewertungsart: Mit der Bewertungs-Zeitleiste traegt eine Kursreihe ihre Tage weiter, wenn das
# Asset heute anders bewertet wird; Papier, Kurswaehrung und Symbol aendert der Wechsel nicht.
_LISTING_NEUTRAL_ASSET_COMMANDS = frozenset({"catalog_rescale_asset_v1", "catalog_set_isin_asset_v1", "catalog_revise_asset_type_v1",
                                             "catalog_revise_valuation_method_asset_v1"})


def _timeline_keeps_series(space: Path, current: Mapping[str, Any]) -> bool:
    try:
        from migrations.reference.asset_valuation_timeline_v1 import timeline_v1
        return (current.get("provider_id"), current.get("provider_symbol")) in timeline_v1(space).market_series(current["asset_id"])
    except Exception:  # noqa: BLE001 - eine unlesbare Zeitleiste gibt keine Erlaubnis
        return False


def _listing_catalog_current(
    space: Path,
    context: DesktopProviderSearchContextV1,
    listing: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> bool:
    """Gilt die Freigabe noch fuer die heutige Asset-Zeile?

    Die Freigabe traegt den Fingerabdruck der Asset-Zeile vom Tag ihrer
    Erteilung, und in den gehen Mengenskala und Revision ein. Eine
    Skalenanhebung aendert genau diese beiden Felder und sonst nichts - am
    Kurs, an der Kurswaehrung und am Papier aendert sie nichts. Trotzdem
    hat eine Anhebung alle
    Freigaben auf einmal entwertet: Kursabruf und Bewertung wiesen jedes Asset
    ab.

    Weicht der Fingerabdruck ab, gilt die Freigabe deshalb weiter, wenn das
    Audit-Protokoll seit ihrer Erteilung fuer dieses Asset ausschliesslich
    Skalenanhebungen und nachgetragene ISIN fuehrt - mindestens einen solchen
    Befehl, und nichts anderes. Das Nachtragen (catalog_set_isin_asset_v1)
    fuellt nur eine leere ISIN; Name, Kurswaehrung und Kurssymbol, auf die die
    Freigabe sich stuetzt, bleiben (rc.265). Ebenso
    der Wechsel zwischen ETF und Fonds (catalog_revise_asset_type_v1, rc.274):
    beides ist ein Investmentfonds, Kurs und Symbol bleiben.
    Jede andere Aenderung (Name, geaenderte ISIN, anderer Typ, Kurswaehrung,
    Bewertungsart, Status) entwertet sie wie bisher.
    """
    if listing["catalog_fingerprint"] == mapping["catalog_fingerprint"]:
        return True
    try:
        bound_at = read_daily_market_listing_bound_at_v1(
            _market_store(space), _reader_context(context), listing["listing_ref"]
        )
    except DailyMarketHistoryBlocked as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    commands = _asset_commands_since(space, mapping["asset_id"], _as_utc(bound_at))
    return bool(commands) and all(
        command["command_type"] in _LISTING_NEUTRAL_ASSET_COMMANDS
        and command["origin_type"] == "native"
        and command["origin_ref"] is None
        for command in commands
    )


def _reader_context(context: DesktopProviderSearchContextV1) -> MarketHistoryContext:
    return MarketHistoryContext(
        context.tenant_id,
        context.user_id,
        context.data_space_id,
        "portfolio_reader",
        "portfolio_worker",
    )


def _writer_context(context: DesktopProviderSearchContextV1) -> MarketHistoryContext:
    return MarketHistoryContext(
        context.tenant_id,
        context.user_id,
        context.data_space_id,
        "market_worker",
        "market_worker",
    )


def preview_desktop_market_history_review_fetch_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    listing_ref: str,
    mapping: Mapping[str, Any],
    promotion_binding: Mapping[str, Any],
    scope_start_date: str,
    scope_end_date: str,
    mode: str,
    request_nonce: str,
    created_at_utc: str,
) -> dict[str, Any]:
    current_context = _context(context)
    supplied_mapping = _mapping(mapping)
    space = _data_space(data_space_path, current_context)
    current_mapping, mapping_audits = _validate_current_mapping(
        space, supplied_mapping
    )
    start = _as_date(scope_start_date)
    end = _as_date(scope_end_date)
    created = _as_utc(created_at_utc)
    if (
        end < start
        or (end - start).days + 1 > MAX_RANGE_DAYS
        or not isinstance(mode, str)
        or mode not in MODES
        or not isinstance(request_nonce, str)
        or _NONCE.fullmatch(request_nonce) is None
    ):
        _abort("desktop_market_history_review_input_invalid")
    try:
        # Die Vorschau plant zu ihrem eigenen Zeitpunkt: Welcher Tag abgeschlossen ist, haengt an der Uhr (#475).
        plan = plan_desktop_market_history_v1(
            space, current_context, listing_ref, scope_start_date, scope_end_date, mode,
            now_utc=datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc),
        )
    except DesktopMarketHistoryPlanV1Error as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_input_invalid"
        ) from error
    expected_range = {
        "start_date": scope_start_date,
        "end_date": scope_end_date,
        "calendar_day_count": (end - start).days + 1,
    }
    if expected_range not in plan["ranges"]:
        _abort("desktop_market_history_review_input_invalid")
    store = _market_store(space)
    try:
        listing = read_daily_market_listing_binding_v1(
            store, _reader_context(current_context), listing_ref
        )
    except DailyMarketHistoryBlocked as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    if listing["quote_currency"] != current_mapping[
        "provider_currency"
    ] or not _listing_catalog_current(space, current_context, listing, current_mapping):
        _abort("desktop_market_history_review_input_invalid")
    current_promotion = _promotion_binding(
        promotion_binding, listing, current_mapping, current_context
    )
    _validate_promotion_audit(current_promotion, current_mapping, mapping_audits)
    _assert_no_unresolved_review(space, current_context, listing["listing_ref"])
    if listing["calendar_code"] not in {"weekday_exchange", "continuous_24_7"}:
        _abort("market_history_review_calendar_invalid")
    if re.fullmatch(r"^[A-Z0-9]{2,12}$", listing["market_code"]) is None:
        _abort("desktop_market_history_review_input_invalid")
    body = {
        "contract_version": "desktop_market_history_review_fetch_preview_v1",
        "status": "ready_for_fetch_confirmation",
        "listing": listing,
        "mapping": current_mapping,
        "promotion_binding": current_promotion,
        "mode": mode,
        "scope_start_date": scope_start_date,
        "scope_end_date": scope_end_date,
        "target_day_count": (end - start).days + 1,
        "provider_call_count": 1,
        "request_nonce": request_nonce,
        "created_at_utc": created,
        "context_fingerprint": _context_fingerprint(current_context),
        "provider_access": False,
        "network_access": False,
        "staging_write": False,
        "market_history_write": False,
        "canonical_write": False,
        "automatic_retry": False,
    }
    return {**body, "preview_fingerprint": _sha(body)}


def _validate_preview(value: Any) -> dict[str, Any]:
    fields = {
        "contract_version",
        "status",
        "listing",
        "mapping",
        "promotion_binding",
        "mode",
        "scope_start_date",
        "scope_end_date",
        "target_day_count",
        "provider_call_count",
        "request_nonce",
        "created_at_utc",
        "context_fingerprint",
        "provider_access",
        "network_access",
        "staging_write",
        "market_history_write",
        "canonical_write",
        "automatic_retry",
        "preview_fingerprint",
    }
    if not isinstance(value, dict) or set(value) != fields:
        _abort("desktop_market_history_review_preview_invalid")
    body = {key: item for key, item in value.items() if key != "preview_fingerprint"}
    try:
        start = _as_date(value["scope_start_date"])
        end = _as_date(value["scope_end_date"])
        _as_utc(value["created_at_utc"])
        current_listing = _listing_binding(
            value["listing"], "desktop_market_history_review_preview_invalid"
        )
        current_mapping = _mapping(value["mapping"])
        _promotion_binding(
            value["promotion_binding"], current_listing, current_mapping
        )
    except (DesktopMarketHistoryReviewV1Error, AttributeError, KeyError, TypeError):
        _abort("desktop_market_history_review_preview_invalid")
    if (
        value["contract_version"] != "desktop_market_history_review_fetch_preview_v1"
        or value["status"] != "ready_for_fetch_confirmation"
        or current_listing["calendar_code"]
        not in {"weekday_exchange", "continuous_24_7"}
        or re.fullmatch(r"^[A-Z0-9]{2,12}$", current_listing["market_code"])
        is None
        or not isinstance(value["mode"], str)
        or value["mode"] not in MODES
        or end < start
        or (end - start).days + 1 > MAX_RANGE_DAYS
        or type(value["target_day_count"]) is not int
        or value["target_day_count"] != (end - start).days + 1
        or type(value["provider_call_count"]) is not int
        or value["provider_call_count"] != 1
        or not isinstance(value["request_nonce"], str)
        or _NONCE.fullmatch(value["request_nonce"]) is None
        or not isinstance(value["context_fingerprint"], str)
        or _SHA.fullmatch(value["context_fingerprint"]) is None
        or any(
            value[field] is not False
            for field in (
                "provider_access",
                "network_access",
                "staging_write",
                "market_history_write",
                "canonical_write",
                "automatic_retry",
            )
        )
        or value["preview_fingerprint"] != _sha(body)
    ):
        _abort("desktop_market_history_review_preview_invalid")
    return value


def public_desktop_market_history_review_fetch_preview_v1(value: Any) -> dict[str, Any]:
    trusted = _validate_preview(value)
    return {
        "market_history_review_fetch_preview_version": 1,
        "status": "pending_fetch_confirmation",
        "listing_browser_ref": _listing_browser_ref(trusted["listing"]),
        "quote_currency": trusted["listing"]["quote_currency"],
        "market_code": trusted["listing"]["market_code"],
        "calendar_kind": _calendar_kind(trusted["listing"]["calendar_code"]),
        "mode": trusted["mode"],
        "scope_start_date": trusted["scope_start_date"],
        "scope_end_date": trusted["scope_end_date"],
        "target_day_count": trusted["target_day_count"],
        "provider_call_count": 1,
        "fetch_confirmation_required": True,
        "provider_access": False,
        "network_access": False,
        "staging_write_after_confirmation": True,
        "market_history_write": False,
        "publish_confirmation_required_later": True,
        "provider_refetch_on_publish": False,
        "canonical_write": False,
        "automatic_retry": False,
        "candidate_fingerprint_exposed": False,
        "context_exposed": False,
        "paths_exposed": False,
        "internal_id_exposed": False,
    }


def _review_error(error: MarketHistoryReviewV1Error) -> DesktopMarketHistoryReviewV1Error:
    return DesktopMarketHistoryReviewV1Error(error.code)


def _stage_ref(preview_fingerprint: str) -> str:
    return "mhs_" + _sha(
        {"contract": "desktop_market_history_review_stage_ref_v1", "preview": preview_fingerprint}
    )[:32]


def _stage_path(space: Path, stage_ref: str) -> Path:
    if not isinstance(stage_ref, str) or _STAGE_REF.fullmatch(stage_ref) is None:
        _abort("desktop_market_history_review_input_invalid")
    return space / AREA / "stages" / f"{stage_ref}.json"


def _validate_fetch_attempt(
    value: Any, context: DesktopProviderSearchContextV1
) -> dict[str, Any]:
    fields = {
        "contract_version",
        "stage_ref",
        "preview_fingerprint",
        "listing_ref",
        "scope_start_date",
        "scope_end_date",
        "mapping_fingerprint",
        "context_fingerprint",
        "started_at_utc",
        "provider_call_count",
        "provider_access_authorized",
        "network_access_authorized",
        "staging_write_authorized",
        "market_history_write_authorized",
        "automatic_retry",
        "attempt_fingerprint",
    }
    if not isinstance(value, dict) or set(value) != fields:
        _abort("desktop_market_history_review_stage_invalid")
    body = {key: item for key, item in value.items() if key != "attempt_fingerprint"}
    try:
        start = _as_date(value["scope_start_date"])
        end = _as_date(value["scope_end_date"])
        _as_utc(value["started_at_utc"])
    except DesktopMarketHistoryReviewV1Error:
        _abort("desktop_market_history_review_stage_invalid")
    if (
        value["contract_version"] != "desktop_market_history_review_fetch_attempt_v1"
        or not isinstance(value["stage_ref"], str)
        or _STAGE_REF.fullmatch(value["stage_ref"]) is None
        or not isinstance(value["listing_ref"], str)
        or re.fullmatch(r"^lsr_[a-f0-9]{32}$", value["listing_ref"]) is None
        or end < start
        or any(
            not isinstance(value[field], str) or _SHA.fullmatch(value[field]) is None
            for field in ("preview_fingerprint", "mapping_fingerprint", "context_fingerprint")
        )
        or value["stage_ref"] != _stage_ref(value["preview_fingerprint"])
        or value["context_fingerprint"] != _context_fingerprint(context)
        or type(value["provider_call_count"]) is not int
        or value["provider_call_count"] != 1
        or value["provider_access_authorized"] is not True
        or value["network_access_authorized"] is not True
        or value["staging_write_authorized"] is not True
        or value["market_history_write_authorized"] is not False
        or value["automatic_retry"] is not False
        or value["attempt_fingerprint"] != _sha(body)
    ):
        _abort("desktop_market_history_review_stage_invalid")
    return value


def _names_listing(path: Path, listing_ref: str) -> bool:
    """Ob eine Versuchsdatei die Notierung ueberhaupt nennt - vor der vollen Pruefung (rc.364).

    Die Kette fragt je Asset fuenfmal nach den Versuchen seiner Notierung (Vorschau, Stage, Veroeffentlichen, Verwerfen,
    Wiederherstellen) und las dafuer jedes Mal alle je gemachten Versuche vollstaendig,
    mit jedem Abruf mehr. Ein Versuch einer anderen Notierung traegt deren Kennung, nicht diese. Eine verlinkte Datei geht
    weiter durch die volle Pruefung und wird dort abgewiesen."""
    return path.is_symlink() or listing_ref.encode("utf-8") in path.read_bytes()


ATTEMPT_INDEX = "fetch-attempts-by-listing"


def _mark_fetch_attempt(area: Path, listing_ref: str, stage_ref: str) -> None:
    """Vermerk je Notierung (rc.365, #516): ein leerer Eintrag `fetch-attempts-by-listing/<Notierung>/<Stage>`.

    Er entsteht vor der Versuchsdatei, unter der Sperre der Notierung. So lesen die Pruefungen je Asset nur noch die Versuche
    dieser Notierung; ihre Zahl waechst nicht mehr mit allen Abrufen, die es je gab.
    Ein Vermerk ohne Versuchsdatei - etwa nach einem Absturz dazwischen - ist harmlos."""
    if re.fullmatch(r"^lsr_[a-f0-9]{32}$", listing_ref) is None or _STAGE_REF.fullmatch(stage_ref) is None:
        _abort("desktop_market_history_review_input_invalid")
    folder = _ensure(_ensure(area, ATTEMPT_INDEX), listing_ref)
    try:
        os.close(os.open(folder / stage_ref, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600))
    except FileExistsError:
        pass


def _complete_fetch_attempt_index(area: Path, context: DesktopProviderSearchContextV1) -> None:
    """Einmal nach dem Upgrade: jeden Versuch ohne Vermerk eintragen, dann das Verzeichnis als vollstaendig kennzeichnen.
    Additiv und ohne globale Sperre: Ein gleichzeitiger neuer Versuch traegt sich selbst ein."""
    index = _ensure(area, ATTEMPT_INDEX)
    if (index / ".complete").exists():
        return
    attempts = area / "fetch-attempts"
    if attempts.exists():
        for path in sorted(_owner_directory(attempts).glob("mhs_*.json")):
            attempt = _read_fetch_attempt(path, context)
            _mark_fetch_attempt(area, attempt["listing_ref"], attempt["stage_ref"])
    try:
        os.close(os.open(index / ".complete", os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600))
    except FileExistsError:
        pass


def _fetch_attempt_paths(area: Path, listing_ref: str) -> list[Path]:
    """Die Versuchsdateien, die die Notierung betreffen koennen (rc.365). Mit vollstaendigem Verzeichnis je Notierung nur deren
    eigene - gelesen werden dafuer nur Namen, keine Dateien. Fehlt einem vorhandenen Versuch der Vermerk (etwa nach einem
    Zurueckgehen auf eine aeltere Fassung), gilt das Verzeichnis nicht, und es bleibt bei der Vorauswahl ueber alle Dateien:
    ein fehlender Vermerk darf nie einen offenen Versuch verstecken."""
    attempts = area / "fetch-attempts"
    index = area / ATTEMPT_INDEX
    if index.is_dir() and not index.is_symlink() and (index / ".complete").is_file() and not (index / ".complete").is_symlink():
        marked: set[str] = set()
        own: list[str] = []
        with os.scandir(index) as entries:
            for entry in entries:
                if entry.is_dir(follow_symlinks=False):
                    names = os.listdir(entry.path)
                    marked.update(names)
                    if entry.name == listing_ref:
                        own = names
        present = {name[:-5] for name in os.listdir(attempts) if name.endswith(".json")} if attempts.is_dir() else set()
        if present <= marked:
            return [attempts / f"{name}.json" for name in sorted(own) if name in present]
    if not attempts.is_dir():
        return []
    return [path for path in sorted(attempts.glob("mhs_*.json")) if _names_listing(path, listing_ref)]


def _read_fetch_attempt(
    path: Path, context: DesktopProviderSearchContextV1
) -> dict[str, Any]:
    value = _validate_fetch_attempt(
        _read_sealed(
            path,
            "attempt_fingerprint",
            "desktop_market_history_review_stage_invalid",
        ),
        context,
    )
    if path.stem != value["stage_ref"]:
        _abort("desktop_market_history_review_stage_invalid")
    return value


def _read_fetch_failure(path: Path, attempt: Mapping[str, Any]) -> dict[str, Any]:
    value = _read_sealed(
        path,
        "failure_fingerprint",
        "desktop_market_history_review_stage_invalid",
    )
    fields = {
        "contract_version",
        "stage_ref",
        "preview_fingerprint",
        "attempt_fingerprint",
        "failure_code",
        "failed_at_utc",
        "provider_access_possible",
        "network_access_possible",
        "market_history_write",
        "automatic_retry",
        "failure_fingerprint",
    }
    if (
        set(value) != fields
        or value.get("contract_version") != "desktop_market_history_review_fetch_failure_v1"
        or value.get("stage_ref") != attempt["stage_ref"]
        or value.get("preview_fingerprint") != attempt["preview_fingerprint"]
        or value.get("attempt_fingerprint") != attempt["attempt_fingerprint"]
        or value.get("failure_code") not in FAILURE_CODES
        or value.get("provider_access_possible") is not True
        or value.get("network_access_possible") is not True
        or value.get("market_history_write") is not False
        or value.get("automatic_retry") is not False
    ):
        _abort("desktop_market_history_review_stage_invalid")
    _as_utc(value.get("failed_at_utc"), "desktop_market_history_review_stage_invalid")
    if value["failed_at_utc"] < attempt["started_at_utc"]:
        _abort("desktop_market_history_review_stage_invalid")
    return value


def _fetch_recovery_attempt_evidence(
    attempt: Mapping[str, Any],
    failure: Mapping[str, Any],
    context: DesktopProviderSearchContextV1,
) -> dict[str, Any]:
    body = {
        "contract_version": "desktop_market_history_review_fetch_recovery_attempt_v1",
        "stage_ref": attempt["stage_ref"],
        "fetch_attempt_fingerprint": attempt["attempt_fingerprint"],
        "failure_fingerprint": failure["failure_fingerprint"],
        "context_fingerprint": _context_fingerprint(context),
        "recovery_write_authorized": True,
        "provider_access_authorized": False,
        "network_access_authorized": False,
        "market_history_write_authorized": False,
        "automatic_retry": False,
    }
    return {**body, "recovery_attempt_fingerprint": _sha(body)}


def _read_fetch_recovery_attempt(
    path: Path,
    attempt: Mapping[str, Any],
    failure: Mapping[str, Any],
    context: DesktopProviderSearchContextV1,
) -> dict[str, Any]:
    value = _read_sealed(
        path,
        "recovery_attempt_fingerprint",
        "desktop_market_history_review_stage_invalid",
    )
    if value != _fetch_recovery_attempt_evidence(attempt, failure, context):
        _abort("desktop_market_history_review_stage_invalid")
    return value


def _fetch_recovery_evidence(
    attempt: Mapping[str, Any],
    failure: Mapping[str, Any],
    recovery_attempt: Mapping[str, Any],
    context: DesktopProviderSearchContextV1,
) -> dict[str, Any]:
    body = {
        "contract_version": "desktop_market_history_review_fetch_recovery_v1",
        "status": "fetch_failed_reconciled",
        "stage_ref": attempt["stage_ref"],
        "fetch_attempt_fingerprint": attempt["attempt_fingerprint"],
        "failure_fingerprint": failure["failure_fingerprint"],
        "recovery_attempt_fingerprint": recovery_attempt[
            "recovery_attempt_fingerprint"
        ],
        "context_fingerprint": _context_fingerprint(context),
        "provider_access": False,
        "network_access": False,
        "market_history_write": False,
        "automatic_retry": False,
    }
    return {**body, "recovery_fingerprint": _sha(body)}


def _read_fetch_recovery(
    path: Path,
    attempt: Mapping[str, Any],
    failure: Mapping[str, Any],
    recovery_attempt: Mapping[str, Any],
    context: DesktopProviderSearchContextV1,
) -> dict[str, Any]:
    value = _read_sealed(
        path,
        "recovery_fingerprint",
        "desktop_market_history_review_stage_invalid",
    )
    if value != _fetch_recovery_evidence(
        attempt, failure, recovery_attempt, context
    ):
        _abort("desktop_market_history_review_stage_invalid")
    return value


def _build_review_bundle(
    *,
    review_ref: str,
    listing: Mapping[str, Any],
    candidate_fingerprint: str,
    scope_start_date: str,
    scope_end_date: str,
    calendar_days: list[dict[str, str]],
    current_days: list[dict[str, Any]],
    fetched_days: list[dict[str, Any]],
    normalized_absence_days: list[dict[str, str]],
) -> dict[str, Any]:
    try:
        return build_market_history_review_v1(
            review_ref=review_ref,
            listing_browser_ref=_listing_browser_ref(listing),
            quote_currency=listing["quote_currency"],
            market_code=listing["market_code"],
            calendar_kind=_calendar_kind(listing["calendar_code"]),
            scope_start_date=scope_start_date,
            scope_end_date=scope_end_date,
            calendar_days=calendar_days,
            current_days=current_days,
            fetched_days=fetched_days,
            normalized_absence_days=normalized_absence_days,
            staged_candidate_fingerprint=candidate_fingerprint,
        )
    except MarketHistoryReviewV1Error as error:
        raise _review_error(error) from error


def _validate_stage(value: Any, context: DesktopProviderSearchContextV1) -> dict[str, Any]:
    fields = {
        "contract_version",
        "status",
        "stage_ref",
        "review_ref",
        "preview_fingerprint",
        "context_fingerprint",
        "listing",
        "mapping_fingerprint",
        "promotion_binding_fingerprint",
        "mode",
        "scope_start_date",
        "scope_end_date",
        "current_window_start_date",
        "current_history_fingerprint",
        "candidate",
        "calendar_days",
        "current_days",
        "fetched_days",
        "normalized_absence_days",
        "review_bundle",
        "fetched_at_utc",
        "provider_call_count",
        "provider_access",
        "network_access",
        "market_history_write",
        "canonical_write",
        "automatic_retry",
        "stage_fingerprint",
    }
    if not isinstance(value, dict) or set(value) != fields:
        _abort("desktop_market_history_review_stage_invalid")
    body = {key: item for key, item in value.items() if key != "stage_fingerprint"}
    try:
        scope_start = _as_date(value["scope_start_date"])
        scope_end = _as_date(value["scope_end_date"])
        window_start = _as_date(value["current_window_start_date"])
        _as_utc(value["fetched_at_utc"])
    except DesktopMarketHistoryReviewV1Error as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_stage_invalid"
        ) from error
    if (
        scope_end < scope_start
        or (scope_end - scope_start).days + 1 > MAX_RANGE_DAYS
        or window_start
        != date.fromordinal(max(1, scope_end.toordinal() - 19_999))
        or not isinstance(value["listing"], Mapping)
        or not isinstance(value["mode"], str)
        or value["mode"] not in MODES
        or not isinstance(value["preview_fingerprint"], str)
        or _SHA.fullmatch(value["preview_fingerprint"]) is None
        or value["stage_ref"] != _stage_ref(value["preview_fingerprint"])
        or not isinstance(value["current_history_fingerprint"], str)
        or _SHA.fullmatch(value["current_history_fingerprint"]) is None
        or value["contract_version"] != "desktop_market_history_review_private_stage_v1"
        or value["status"] != "staged_review"
        or not isinstance(value["stage_ref"], str)
        or _STAGE_REF.fullmatch(value["stage_ref"]) is None
        or not isinstance(value["review_ref"], str)
        or _REVIEW_REF.fullmatch(value["review_ref"]) is None
        or value["context_fingerprint"] != _context_fingerprint(context)
        or not isinstance(value["mapping_fingerprint"], str)
        or _SHA.fullmatch(value["mapping_fingerprint"]) is None
        or not isinstance(value["promotion_binding_fingerprint"], str)
        or _SHA.fullmatch(value["promotion_binding_fingerprint"]) is None
        or type(value["provider_call_count"]) is not int
        or value["provider_call_count"] != 1
        or value["provider_access"] is not True
        or value["network_access"] is not True
        or value["market_history_write"] is not False
        or value["canonical_write"] is not False
        or value["automatic_retry"] is not False
        or value["stage_fingerprint"] != _sha(body)
    ):
        _abort("desktop_market_history_review_stage_invalid")
    try:
        listing = _listing_binding(
            value["listing"], "desktop_market_history_review_stage_invalid"
        )
        candidate = validate_daily_market_candidate_for_listing_v1(
            value["candidate"], listing
        )
        rebuilt = _build_review_bundle(
            review_ref=value["review_ref"],
            listing=listing,
            candidate_fingerprint=candidate["candidate_fingerprint"],
            scope_start_date=value["scope_start_date"],
            scope_end_date=value["scope_end_date"],
            calendar_days=value["calendar_days"],
            current_days=value["current_days"],
            fetched_days=value["fetched_days"],
            normalized_absence_days=value["normalized_absence_days"],
        )
    except (DailyMarketHistoryBlocked, DesktopMarketHistoryReviewV1Error) as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_stage_invalid"
        ) from error
    expected_review_ref = "mhr_" + _sha(
        {
            "contract": "desktop_market_history_review_ref_v1",
            "stage_ref": value["stage_ref"],
            "candidate_fingerprint": candidate["candidate_fingerprint"],
        }
    )[:32]
    if (
        rebuilt != value["review_bundle"]
        or value["review_ref"] != expected_review_ref
        or candidate["listing_ref"] != value["listing"].get("listing_ref")
        or candidate["requested_start_date"] != value["scope_start_date"]
        or candidate["requested_end_date"] != value["scope_end_date"]
        or candidate["retrieved_at_utc"] != value["fetched_at_utc"]
    ):
        _abort("desktop_market_history_review_stage_invalid")
    return value


def read_desktop_market_history_review_stage_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    stage_ref: str,
) -> dict[str, Any]:
    current_context = _context(context)
    space = _data_space(data_space_path, current_context)
    path = _stage_path(space, stage_ref)
    if not path.is_file():
        _abort("desktop_market_history_review_stage_invalid")
    stage = _validate_stage(
        _read_sealed(path, "stage_fingerprint", "desktop_market_history_review_stage_invalid"),
        current_context,
    )
    attempt_path = space / AREA / "fetch-attempts" / f"{stage_ref}.json"
    failure_path = space / AREA / "failures" / f"fetch-{stage_ref}.json"
    if not attempt_path.is_file() or failure_path.exists():
        _abort("desktop_market_history_review_stage_invalid")
    attempt = _read_fetch_attempt(attempt_path, current_context)
    if (
        stage["preview_fingerprint"] != attempt["preview_fingerprint"]
        or stage["listing"]["listing_ref"] != attempt["listing_ref"]
        or stage["scope_start_date"] != attempt["scope_start_date"]
        or stage["scope_end_date"] != attempt["scope_end_date"]
        or stage["mapping_fingerprint"] != attempt["mapping_fingerprint"]
        or stage["context_fingerprint"] != attempt["context_fingerprint"]
        or stage["fetched_at_utc"] < attempt["started_at_utc"]
    ):
        _abort("desktop_market_history_review_stage_invalid")
    return stage


@price_providers.within_price_provider_session
def stage_desktop_market_history_review_fetch_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    trusted_preview: Mapping[str, Any],
    public_preview: Mapping[str, Any],
    confirmed: bool,
    *,
    transport: Callable[[str, str, dict[str, str], int, int], dict[str, Any]] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    current_context = _context(context)
    trusted = _validate_preview(dict(trusted_preview))
    provider_id = trusted["mapping"]["provider_id"]
    if (
        trusted["context_fingerprint"] != _context_fingerprint(current_context)
        or dict(public_preview) != public_desktop_market_history_review_fetch_preview_v1(trusted)
    ):
        _abort("desktop_market_history_review_preview_invalid")
    if confirmed is not True:
        _abort("desktop_market_history_review_confirmation_required")
    space = _data_space(data_space_path, current_context)
    try:
        current_listing = read_daily_market_listing_binding_v1(
            _market_store(space),
            _reader_context(current_context),
            trusted["listing"]["listing_ref"],
        )
    except (DailyMarketHistoryBlocked, KeyError, TypeError) as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_preview_invalid"
        ) from error
    if current_listing != trusted["listing"]:
        _abort("desktop_market_history_review_preview_invalid")
    try:
        current_mapping, mapping_audits = _validate_current_mapping(
            space, trusted["mapping"]
        )
        current_promotion = _promotion_binding(
            trusted["promotion_binding"],
            current_listing,
            current_mapping,
            current_context,
        )
        _validate_promotion_audit(
            current_promotion, current_mapping, mapping_audits
        )
    except DesktopMarketHistoryReviewV1Error as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_preview_invalid"
        ) from error
    if (
        current_mapping != trusted["mapping"]
        or current_promotion != trusted["promotion_binding"]
    ):
        _abort("desktop_market_history_review_preview_invalid")
    stage_ref = _stage_ref(trusted["preview_fingerprint"])
    _assert_no_unresolved_review(
        space,
        current_context,
        trusted["listing"]["listing_ref"],
        ignore_stage_ref=stage_ref,
    )
    area = _ensure(space, AREA)
    fetch_attempts = _ensure(area, "fetch-attempts")
    stages = _ensure(area, "stages")
    failures = _ensure(area, "failures")
    stage_path = stages / f"{stage_ref}.json"
    attempt_path = fetch_attempts / f"{stage_ref}.json"
    if stage_path.exists():
        if (
            not attempt_path.exists()
            or failures.joinpath(f"fetch-{stage_ref}.json").exists()
        ):
            _abort("desktop_market_history_review_stage_invalid")
        existing_attempt = _read_fetch_attempt(attempt_path, current_context)
        existing_stage = read_desktop_market_history_review_stage_v1(
            space, current_context, stage_ref
        )
        if (
            existing_attempt["preview_fingerprint"] != trusted["preview_fingerprint"]
            or existing_attempt["listing_ref"] != trusted["listing"]["listing_ref"]
            or existing_attempt["scope_start_date"] != trusted["scope_start_date"]
            or existing_attempt["scope_end_date"] != trusted["scope_end_date"]
            or existing_attempt["mapping_fingerprint"]
            != trusted["mapping"]["mapping_fingerprint"]
            or existing_attempt["context_fingerprint"]
            != trusted["context_fingerprint"]
            or existing_attempt["started_at_utc"] < trusted["created_at_utc"]
            or existing_stage["preview_fingerprint"]
            != existing_attempt["preview_fingerprint"]
            or existing_stage["listing"] != trusted["listing"]
            or existing_stage["mapping_fingerprint"]
            != existing_attempt["mapping_fingerprint"]
            or existing_stage["promotion_binding_fingerprint"]
            != _sha(trusted["promotion_binding"])
            or existing_stage["mode"] != trusted["mode"]
            or existing_stage["scope_start_date"]
            != existing_attempt["scope_start_date"]
            or existing_stage["scope_end_date"]
            != existing_attempt["scope_end_date"]
            or existing_stage["context_fingerprint"]
            != existing_attempt["context_fingerprint"]
            or existing_stage["fetched_at_utc"]
            < existing_attempt["started_at_utc"]
        ):
            _abort("desktop_market_history_review_stage_invalid")
        return existing_stage
    with _listing_lock(area, trusted["listing"]["listing_ref"]):
        # Recheck under the Listing lock: another process may have consumed a
        # different Preview after the optimistic read above.
        _assert_no_unresolved_review(
            space,
            current_context,
            trusted["listing"]["listing_ref"],
            ignore_stage_ref=stage_ref,
        )
        if stage_path.exists() or attempt_path.exists():
            _abort("desktop_market_history_review_recovery_required")
        started = _now(clock)
        if started < trusted["created_at_utc"]:
            _abort("desktop_market_history_review_preview_invalid")
        attempt_body = {
            "contract_version": "desktop_market_history_review_fetch_attempt_v1",
            "stage_ref": stage_ref,
            "preview_fingerprint": trusted["preview_fingerprint"],
            "listing_ref": trusted["listing"]["listing_ref"],
            "scope_start_date": trusted["scope_start_date"],
            "scope_end_date": trusted["scope_end_date"],
            "mapping_fingerprint": trusted["mapping"]["mapping_fingerprint"],
            "context_fingerprint": trusted["context_fingerprint"],
            "started_at_utc": started,
            "provider_call_count": 1,
            "provider_access_authorized": True,
            "network_access_authorized": True,
            "staging_write_authorized": True,
            "market_history_write_authorized": False,
            "automatic_retry": False,
        }
        attempt = {**attempt_body, "attempt_fingerprint": _sha(attempt_body)}
        _complete_fetch_attempt_index(area, current_context)
        _mark_fetch_attempt(area, attempt["listing_ref"], stage_ref)
        _write_create(
            attempt_path, attempt, "desktop_market_history_review_fetch_attempt_consumed"
        )
    try:
        start = _as_date(trusted["scope_start_date"])
        end = _as_date(trusted["scope_end_date"])
        # Ein Ein-Tages-Fenster liefert bei einer Boersennotierung nichts: Abrufe
        # fuer einen einzelnen Tag gaben HTTP 200 mit null Balken zurueck,
        # waehrend dieselben Symbole ueber zwei Tage beide Tage lieferten. Bei
        # Kryptowerten ging auch der einzelne Tag. Das Fenster der Anfrage wird
        # deshalb nach hinten aufgeweitet; der Parser verwirft ohnehin jeden Tag
        # ausserhalb des angefragten Bereichs, der Bestand aendert sich dadurch
        # nicht. Fuenf Tage, weil ein Wochenende zwei davon schluckt.
        window_start = min(start, end - timedelta(days=4))
        # Die Anfrage baut das Kursanbieter-Plugin (#495, rc.382); Host und Ziel prueft der Kern gegen das Manifest.
        parser_params = {
            "provider_symbol": trusted["mapping"]["provider_symbol"],
            "start_date": trusted["scope_start_date"],
            "end_date": trusted["scope_end_date"],
        }
        try:
            request = price_providers.build_request_v1(
                provider_id, "daily_history", dict(parser_params, request_start_date=window_start.isoformat())
            )
            if transport is None:
                # Abruf ueber den gemeinsamen Weg des Kerns (Zugang, Kosten; rc.394); fuer Yahoo wie bisher.
                transport = core_transport_v1(space, current_context, provider_id, _abort, "desktop_market_history_review")
            response = transport(
                request["host"],
                request["target"],
                {
                    "Accept": "application/json",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                    "User-Agent": "Portelyra/0.2 Staged-History-Review",
                },
                TIMEOUT,
                BYTE_LIMIT,
            )
        except DesktopMarketHistoryReviewV1Error:
            raise
        except Exception as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_transport_failed"
            ) from error
        fetched_at = _now(clock)
        if fetched_at < started:
            _abort("desktop_market_history_review_response_invalid")
        # Eine Abweisung auf HTTP-Ebene ist etwas anderes als eine kaputte
        # Antwort. Am 24.09.2026 scheiterte ein Abruf, ohne dass eine Antwort
        # festgehalten wurde - die Hüllenpruefung greift vor dem Festhalten, und
        # damit war hinterher nicht zu sagen, ob die Quelle gebremst hat. Status
        # und Inhaltstyp werden jetzt in jedem Fall festgehalten, und die
        # bekannten Bremssignale heissen source_rejected: Der Sammellauf wartet
        # darauf und versucht es erneut, statt das Asset zurueckzustellen.
        envelope_ok = (
            isinstance(response, dict)
            and set(response) == {"status", "headers", "body"}
            and response.get("status") == 200
            and isinstance(response.get("headers"), dict)
            and isinstance(response.get("body"), bytes)
            and len(response["body"]) <= BYTE_LIMIT
            and isinstance(response["headers"].get("content-type"), str)
            and response["headers"]["content-type"].lower().startswith("application/json")
        )
        if not envelope_ok and isinstance(response, dict) and isinstance(response.get("status"), int):
            try:
                _write_create(
                    _ensure(area, "responses") / f"fetch-{stage_ref}.json",
                    {
                        "contract_version": "desktop_market_history_review_response_v1",
                        "stage_ref": stage_ref,
                        "preview_fingerprint": trusted["preview_fingerprint"],
                        "provider_symbol": trusted["mapping"]["provider_symbol"],
                        "requested_start_date": trusted["scope_start_date"],
                        "requested_end_date": trusted["scope_end_date"],
                        "http_status": response["status"],
                        "content_type": str(response.get("headers", {}).get("content-type"))[:256],
                        "retrieved_at_utc": fetched_at,
                        "body_base64": base64.b64encode(
                            response["body"][:4096] if isinstance(response.get("body"), bytes) else b""
                        ).decode("ascii"),
                    },
                    "desktop_market_history_review_store_invalid",
                )
            except DesktopMarketHistoryReviewV1Error:
                pass
            # Ob die Quelle bremst oder der Titel an diesen Tagen noch nicht
            # notiert war, weiss nur das Plugin (bei Yahoo: HTTP 429/503 bzw.
            # HTTP 400 "Data doesn't exist for startDate", 25.09.2026, #283).
            outcome = _plugin_outcome(parser_params, response, provider_id)
            if outcome["outcome"] == "rejected":
                _abort("desktop_market_history_review_source_rejected")
            if outcome["outcome"] == "not_listed":
                _abort("desktop_market_history_review_source_not_listed")
        # Dieselbe Regel nur einmal formuliert: envelope_ok oben ist die
        # Bedingung, hier ist ihre Verneinung. Zweimal ausgeschrieben haette eine
        # kuenftige Aenderung womoeglich nur eine der beiden Stellen getroffen
        # (Prüfung 25.09.2026).
        if not envelope_ok:
            _abort("desktop_market_history_review_response_invalid")
        # Ohne festgehaltene Antwort ist ein fehlgeschlagener Abruf spaeter nicht
        # erklaerbar. Der Beleg nannte nur den Code; zweimal liess sich damit die
        # Ursache nicht rekonstruieren (22.09.2026).
        try:
            _write_create(
                _ensure(area, "responses") / f"fetch-{stage_ref}.json",
                {
                    "contract_version": "desktop_market_history_review_response_v1",
                    "stage_ref": stage_ref,
                    "preview_fingerprint": trusted["preview_fingerprint"],
                    "provider_symbol": trusted["mapping"]["provider_symbol"],
                    "requested_start_date": trusted["scope_start_date"],
                    "requested_end_date": trusted["scope_end_date"],
                    "http_status": response["status"],
                    "content_type": str(response["headers"].get("content-type"))[:256],
                    "retrieved_at_utc": fetched_at,
                    "body_base64": base64.b64encode(response["body"]).decode("ascii"),
                },
                "desktop_market_history_review_store_invalid",
            )
        except DesktopMarketHistoryReviewV1Error:
            pass
        # Die Quelle weist einen Abruf auch mit HTTP 200 ab und legt den Grund in
        # den Koerper. Ein abgewiesener Abruf ist etwas anderes als eine kaputte
        # Antwort und heisst deshalb anders; erkennen kann ihn nur das Plugin.
        outcome = _plugin_outcome(parser_params, response, provider_id)
        if outcome["outcome"] == "rejected":
            _abort("desktop_market_history_review_source_rejected")
        if outcome["outcome"] != "ok":
            _abort("desktop_market_history_review_response_invalid")
        parsed = with_observation_refs_v1(outcome["result"], "mhf_" + trusted["preview_fingerprint"][:32])
        # Waehrung und Zeitzone der Antwort muessen zur gebundenen Notierung passen.
        # Welche der beiden abweicht, gehoert in den Beleg: Ohne diese Angabe ist
        # ein fehlgeschlagener Abruf spaeter nicht erklaerbar und sieht aus wie ein
        # Serverproblem (Festlegung 22.09.2026).
        # Jede gelungene Antwort nennt die Erstnotiz mit. Sie wird festgehalten,
        # damit die naechste Planung nicht wieder vor ihr beginnt.
        if isinstance(parsed.get("first_trade_date"), str):
            _write_notation(
                space,
                current_context,
                trusted["mapping"]["provider_symbol"],
                parsed["first_trade_date"],
                fetched_at,
                provider_id,
            )
        if parsed["provider_currency"] != trusted["listing"]["quote_currency"]:
            _abort("desktop_market_history_review_response_currency_mismatch")
        if parsed["timezone_name"] != trusted["listing"]["timezone_name"]:
            _abort("desktop_market_history_review_response_timezone_mismatch")
        day_preview = {
            "preview_fingerprint": trusted["preview_fingerprint"],
            "start_date": trusted["scope_start_date"],
            "end_date": trusted["scope_end_date"],
            "calendar_code": trusted["listing"]["calendar_code"],
        }
        try:
            raw_days = _range_days(parsed, day_preview, fetched_at)
        except Exception as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_response_invalid"
            ) from error
        request_ref = "mrq_" + _sha(
            {
                "contract": "desktop_market_history_review_request_v1",
                "preview": trusted["preview_fingerprint"],
            }
        )[:32]
        source_ref = "msr_" + _sha(
            {"contract": "desktop_market_history_review_source_v1", "request": request_ref}
        )[:32]
        request_fingerprint = _sha(
            {
                "contract": "desktop_market_history_review_request_v1",
                "preview_fingerprint": trusted["preview_fingerprint"],
                "mapping_fingerprint": trusted["mapping"]["mapping_fingerprint"],
                "days": raw_days,
            }
        )
        writer_context = _writer_context(current_context)
        try:
            binding = daily_market_history_job_binding_fingerprint_v1(
                writer_context,
                listing_ref=trusted["listing"]["listing_ref"],
                request_ref=request_ref,
                request_fingerprint=request_fingerprint,
                source_ref=source_ref,
            )
            raw_candidate = seal_daily_market_history_candidate_v1(
                listing_ref=trusted["listing"]["listing_ref"],
                request_ref=request_ref,
                source_kind="market_plugin",
                source_ref=source_ref,
                # Herkunft je Kurstag: Plugin, Version und Pruefsumme (#495, rc.382).
                source_version=price_providers.provider_identity_v1(provider_id)["source_version"],
                request_fingerprint=request_fingerprint,
                job_binding_fingerprint=binding,
                requested_start_date=trusted["scope_start_date"],
                requested_end_date=trusted["scope_end_date"],
                retrieved_at_utc=fetched_at,
                days=raw_days,
            )
        except DailyMarketHistoryBlocked as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_response_invalid"
            ) from error
        store = _market_store(space)
        reader_context = _reader_context(current_context)
        try:
            current_range = read_daily_market_history_v1(
                store,
                reader_context,
                trusted["listing"]["listing_ref"],
                trusted["scope_start_date"],
                trusted["scope_end_date"],
            )
        except DailyMarketHistoryBlocked as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_store_invalid"
            ) from error
        candidate = _compare_for_publication(
            raw_candidate, current_range, trusted["listing"]
        )
        window_start = date.fromordinal(max(1, end.toordinal() - 19999))
        try:
            current_window = read_daily_market_history_v1(
                store,
                reader_context,
                trusted["listing"]["listing_ref"],
                window_start.isoformat(),
                trusted["scope_end_date"],
            )
        except DailyMarketHistoryBlocked as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_store_invalid"
            ) from error
        calendar_days = _calendar_rows(trusted["listing"], start, end)
        current_days = _current_review_rows(current_window)
        fetched_days = _fetched_review_rows(parsed)
        absence_days = _absence_rows(parsed, calendar_days)
        review_ref = "mhr_" + _sha(
            {
                "contract": "desktop_market_history_review_ref_v1",
                "stage_ref": stage_ref,
                "candidate_fingerprint": candidate["candidate_fingerprint"],
            }
        )[:32]
        review_bundle = _build_review_bundle(
            review_ref=review_ref,
            listing=trusted["listing"],
            candidate_fingerprint=candidate["candidate_fingerprint"],
            scope_start_date=trusted["scope_start_date"],
            scope_end_date=trusted["scope_end_date"],
            calendar_days=calendar_days,
            current_days=current_days,
            fetched_days=fetched_days,
            normalized_absence_days=absence_days,
        )
        stage_body = {
            "contract_version": "desktop_market_history_review_private_stage_v1",
            "status": "staged_review",
            "stage_ref": stage_ref,
            "review_ref": review_ref,
            "preview_fingerprint": trusted["preview_fingerprint"],
            "context_fingerprint": trusted["context_fingerprint"],
            "listing": trusted["listing"],
            "mapping_fingerprint": trusted["mapping"]["mapping_fingerprint"],
            "promotion_binding_fingerprint": _sha(trusted["promotion_binding"]),
            "mode": trusted["mode"],
            "scope_start_date": trusted["scope_start_date"],
            "scope_end_date": trusted["scope_end_date"],
            "current_window_start_date": window_start.isoformat(),
            "current_history_fingerprint": current_window["row_set_fingerprint"],
            "candidate": candidate,
            "calendar_days": calendar_days,
            "current_days": current_days,
            "fetched_days": fetched_days,
            "normalized_absence_days": absence_days,
            "review_bundle": review_bundle,
            "fetched_at_utc": fetched_at,
            "provider_call_count": 1,
            "provider_access": True,
            "network_access": True,
            "market_history_write": False,
            "canonical_write": False,
            "automatic_retry": False,
        }
        stage = {**stage_body, "stage_fingerprint": _sha(stage_body)}
        _write_create(
            stage_path, stage, "desktop_market_history_review_fetch_attempt_consumed"
        )
        return read_desktop_market_history_review_stage_v1(
            space, current_context, stage_ref
        )
    except Exception as caught:
        failure_error = (
            caught
            if isinstance(caught, DesktopMarketHistoryReviewV1Error)
            else DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_boundary_failed"
            )
        )
        # A present stage is a possibly completed staging effect and must be
        # reconciled as that exact effect, never contradicted by failure evidence.
        if not stage_path.exists():
            try:
                failed_at = _now(clock)
            except DesktopMarketHistoryReviewV1Error:
                failed_at = started
            if failed_at < started:
                failed_at = started
            failure_body = {
                "contract_version": "desktop_market_history_review_fetch_failure_v1",
                "stage_ref": stage_ref,
                "preview_fingerprint": trusted["preview_fingerprint"],
                "attempt_fingerprint": attempt["attempt_fingerprint"],
                "failure_code": failure_error.code,
                "failed_at_utc": failed_at,
                "provider_access_possible": True,
                "network_access_possible": True,
                "market_history_write": False,
                "automatic_retry": False,
            }
            failure = {**failure_body, "failure_fingerprint": _sha(failure_body)}
            try:
                _write_create(
                    failures / f"fetch-{stage_ref}.json",
                    failure,
                    "desktop_market_history_review_fetch_attempt_consumed",
                )
            except Exception:
                pass
        if failure_error is caught:
            raise
        raise failure_error from caught


def public_desktop_market_history_review_stage_v1(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _abort("desktop_market_history_review_stage_invalid")
    bundle = value.get("review_bundle", {})
    review = bundle.get("public_review") if isinstance(bundle, Mapping) else None
    if not isinstance(review, dict):
        _abort("desktop_market_history_review_stage_invalid")
    try:
        confirm_market_history_review_v1(bundle, review, True)
    except MarketHistoryReviewV1Error as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_stage_invalid"
        ) from error
    return dict(review)


def _publication_path(space: Path, stage_ref: str) -> Path:
    return space / AREA / "publications" / f"{stage_ref}.json"


def _discard_path(space: Path, stage_ref: str) -> Path:
    return space / AREA / "discards" / f"{stage_ref}.json"


def _public_publication(value: Mapping[str, Any], *, exact_replay: bool) -> dict[str, Any]:
    return {
        "market_history_review_publication_result_version": 1,
        "status": "published",
        "review_ref": value["review_ref"],
        "mode": value["mode"],
        "scope_start_date": value["scope_start_date"],
        "scope_end_date": value["scope_end_date"],
        "appended_day_count": value["appended_day_count"],
        "corrected_day_count": value["corrected_day_count"],
        "unchanged_day_count": value["unchanged_day_count"],
        "observed_candidate_count": value["observed_candidate_count"],
        "non_trading_day_count": value["non_trading_day_count"],
        "source_gap_count": value["source_gap_count"],
        "imputed_non_trading_day_count": value["imputed_non_trading_day_count"],
        "warning_count": value["warning_count"],
        "exact_replay": exact_replay,
        "provider_access": False,
        "network_access": False,
        "provider_refetch": False,
        "market_history_write": True,
        "canonical_write": False,
        "tax_write": False,
        "reward_valuation_write": False,
        "automatic_retry": False,
        "candidate_fingerprint_exposed": False,
        "receipt_fingerprint_exposed": False,
        "context_exposed": False,
        "paths_exposed": False,
        "internal_id_exposed": False,
    }


def _validate_market_receipt(
    stage: Mapping[str, Any], receipt: Any, *, exact_replay: bool | None = None
) -> Any:
    attributes = (
        "request_ref",
        "candidate_fingerprint",
        "appended_day_count",
        "corrected_day_count",
        "unchanged_day_count",
        "row_set_fingerprint",
        "receipt_fingerprint",
        "exact_replay",
    )
    if any(not hasattr(receipt, field) for field in attributes):
        _abort("desktop_market_history_review_publication_invalid")
    counts = (
        receipt.appended_day_count,
        receipt.corrected_day_count,
        receipt.unchanged_day_count,
    )
    receipt_body = {
        "request_ref": receipt.request_ref,
        "candidate_fingerprint": receipt.candidate_fingerprint,
        "appended_day_count": receipt.appended_day_count,
        "corrected_day_count": receipt.corrected_day_count,
        "unchanged_day_count": receipt.unchanged_day_count,
        "row_set_fingerprint": receipt.row_set_fingerprint,
    }
    if (
        receipt.request_ref != stage["candidate"]["request_ref"]
        or receipt.candidate_fingerprint
        != stage["candidate"]["candidate_fingerprint"]
        or any(type(value) is not int or value < 0 for value in counts)
        or sum(counts) != len(stage["candidate"]["days"])
        or not isinstance(receipt.row_set_fingerprint, str)
        or _SHA.fullmatch(receipt.row_set_fingerprint) is None
        or not isinstance(receipt.receipt_fingerprint, str)
        or receipt.receipt_fingerprint != _sha(receipt_body)
        or type(receipt.exact_replay) is not bool
        or (exact_replay is not None and receipt.exact_replay is not exact_replay)
    ):
        _abort("desktop_market_history_review_publication_invalid")
    return receipt


def _publication_from_receipt(
    stage: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    receipt: Any,
    completed_at_utc: str,
    *,
    exact_replay: bool,
) -> dict[str, Any]:
    receipt = _validate_market_receipt(stage, receipt, exact_replay=exact_replay)
    summary = stage["review_bundle"]["public_review"]["summary"]
    body = {
        "contract_version": "desktop_market_history_review_private_publication_v1",
        "status": "published",
        "stage_ref": stage["stage_ref"],
        "review_ref": stage["review_ref"],
        "context_fingerprint": stage["context_fingerprint"],
        "preview_fingerprint": stage["preview_fingerprint"],
        "candidate_fingerprint": stage["candidate"]["candidate_fingerprint"],
        "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
        "request_ref": receipt.request_ref,
        "receipt_fingerprint": receipt.receipt_fingerprint,
        "mode": stage["mode"],
        "scope_start_date": stage["scope_start_date"],
        "scope_end_date": stage["scope_end_date"],
        "appended_day_count": receipt.appended_day_count,
        "corrected_day_count": receipt.corrected_day_count,
        "unchanged_day_count": receipt.unchanged_day_count,
        "observed_candidate_count": summary["observed_candidate_count"],
        "non_trading_day_count": summary["non_trading_day_count"],
        "source_gap_count": summary["source_gap_count"],
        "imputed_non_trading_day_count": summary["imputed_non_trading_day_count"],
        "warning_count": summary["warning_count"],
        "completed_at_utc": completed_at_utc,
        "provider_access": False,
        "network_access": False,
        "provider_refetch": False,
        "market_history_write": True,
        "canonical_write": False,
        "automatic_retry": False,
    }
    return {**body, "publication_fingerprint": _sha(body)}


def _read_publication(
    path: Path,
    stage: Mapping[str, Any],
    publish_attempt: Mapping[str, Any],
    receipt: Any,
) -> dict[str, Any]:
    value = _read_sealed(
        path,
        "publication_fingerprint",
        "desktop_market_history_review_publication_invalid",
    )
    fields = {
        "contract_version",
        "status",
        "stage_ref",
        "review_ref",
        "context_fingerprint",
        "preview_fingerprint",
        "candidate_fingerprint",
        "confirmation_fingerprint",
        "request_ref",
        "receipt_fingerprint",
        "mode",
        "scope_start_date",
        "scope_end_date",
        "appended_day_count",
        "corrected_day_count",
        "unchanged_day_count",
        "observed_candidate_count",
        "non_trading_day_count",
        "source_gap_count",
        "imputed_non_trading_day_count",
        "warning_count",
        "completed_at_utc",
        "provider_access",
        "network_access",
        "provider_refetch",
        "market_history_write",
        "canonical_write",
        "automatic_retry",
        "publication_fingerprint",
    }
    summary = stage["review_bundle"]["public_review"]["summary"]
    receipt_counts = {
        "appended_day_count": receipt.appended_day_count,
        "corrected_day_count": receipt.corrected_day_count,
        "unchanged_day_count": receipt.unchanged_day_count,
    }
    summary_counts = {
        field: summary[field]
        for field in (
            "observed_candidate_count",
            "non_trading_day_count",
            "source_gap_count",
            "imputed_non_trading_day_count",
            "warning_count",
        )
    }
    if (
        set(value) != fields
        or value.get("contract_version")
        != "desktop_market_history_review_private_publication_v1"
        or value.get("status") != "published"
        or value.get("stage_ref") != stage["stage_ref"]
        or value.get("review_ref") != stage["review_ref"]
        or value.get("context_fingerprint") != stage["context_fingerprint"]
        or value.get("preview_fingerprint") != stage["preview_fingerprint"]
        or value.get("candidate_fingerprint")
        != stage["candidate"]["candidate_fingerprint"]
        or value.get("confirmation_fingerprint")
        != publish_attempt["confirmation_fingerprint"]
        or value.get("request_ref") != stage["candidate"]["request_ref"]
        or value.get("request_ref") != receipt.request_ref
        or value.get("receipt_fingerprint") != receipt.receipt_fingerprint
        or receipt.candidate_fingerprint
        != stage["candidate"]["candidate_fingerprint"]
        or value.get("mode") != stage["mode"]
        or value.get("scope_start_date") != stage["scope_start_date"]
        or value.get("scope_end_date") != stage["scope_end_date"]
        or value.get("completed_at_utc") != publish_attempt["started_at_utc"]
        or any(
            type(value.get(field)) is not int or value[field] < 0
            for field in (*receipt_counts, *summary_counts)
        )
        or any(value.get(field) != expected for field, expected in receipt_counts.items())
        or any(value.get(field) != expected for field, expected in summary_counts.items())
        or value.get("provider_access") is not False
        or value.get("network_access") is not False
        or value.get("provider_refetch") is not False
        or value.get("market_history_write") is not True
        or value.get("canonical_write") is not False
        or value.get("automatic_retry") is not False
    ):
        _abort("desktop_market_history_review_publication_invalid")
    _as_utc(
        value.get("completed_at_utc"),
        "desktop_market_history_review_publication_invalid",
    )
    return value


def _read_rejection(path: Path, stage: Mapping[str, Any]) -> dict[str, Any]:
    value = _read_sealed(
        path,
        "rejection_fingerprint",
        "desktop_market_history_review_publication_invalid",
    )
    fields = {
        "contract_version",
        "status",
        "stage_ref",
        "review_ref",
        "context_fingerprint",
        "candidate_fingerprint",
        "rejected_at_utc",
        "provider_access",
        "network_access",
        "market_history_write",
        "automatic_retry",
        "rejection_fingerprint",
    }
    if (
        set(value) != fields
        or value.get("contract_version") != "desktop_market_history_review_rejection_v1"
        or value.get("status") != "rejected"
        or value.get("stage_ref") != stage["stage_ref"]
        or value.get("review_ref") != stage["review_ref"]
        or value.get("context_fingerprint") != stage["context_fingerprint"]
        or value.get("candidate_fingerprint")
        != stage["candidate"]["candidate_fingerprint"]
        or value.get("provider_access") is not False
        or value.get("network_access") is not False
        or value.get("market_history_write") is not False
        or value.get("automatic_retry") is not False
    ):
        _abort("desktop_market_history_review_publication_invalid")
    _as_utc(
        value.get("rejected_at_utc"),
        "desktop_market_history_review_publication_invalid",
    )
    if value["rejected_at_utc"] < stage["fetched_at_utc"]:
        _abort("desktop_market_history_review_publication_invalid")
    return value


def _read_publish_attempt(path: Path, stage: Mapping[str, Any]) -> dict[str, Any]:
    value = _read_sealed(
        path,
        "attempt_fingerprint",
        "desktop_market_history_review_publication_invalid",
    )
    try:
        expected_confirmation = confirm_market_history_review_v1(
            stage["review_bundle"],
            stage["review_bundle"]["public_review"],
            True,
        )
    except (MarketHistoryReviewV1Error, KeyError, TypeError) as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_publication_invalid"
        ) from error
    fields = {
        "contract_version",
        "stage_ref",
        "review_ref",
        "candidate_fingerprint",
        "public_review_fingerprint",
        "confirmation_fingerprint",
        "context_fingerprint",
        "started_at_utc",
        "provider_access_authorized",
        "network_access_authorized",
        "provider_refetch_authorized",
        "market_history_write_authorized",
        "automatic_retry",
        "attempt_fingerprint",
    }
    if (
        set(value) != fields
        or value.get("contract_version") != "desktop_market_history_review_publish_attempt_v1"
        or value.get("stage_ref") != stage["stage_ref"]
        or value.get("review_ref") != stage["review_ref"]
        or value.get("candidate_fingerprint")
        != stage["candidate"]["candidate_fingerprint"]
        or value.get("context_fingerprint") != stage["context_fingerprint"]
        or any(
            not isinstance(value.get(field), str)
            or _SHA.fullmatch(value[field]) is None
            for field in ("public_review_fingerprint", "confirmation_fingerprint")
        )
        or value.get("public_review_fingerprint")
        != expected_confirmation["public_review_fingerprint"]
        or value.get("confirmation_fingerprint")
        != expected_confirmation["confirmation_fingerprint"]
        or value.get("provider_access_authorized") is not False
        or value.get("network_access_authorized") is not False
        or value.get("provider_refetch_authorized") is not False
        or value.get("market_history_write_authorized") is not True
        or value.get("automatic_retry") is not False
    ):
        _abort("desktop_market_history_review_publication_invalid")
    _as_utc(
        value.get("started_at_utc"),
        "desktop_market_history_review_publication_invalid",
    )
    if value["started_at_utc"] < stage["fetched_at_utc"]:
        _abort("desktop_market_history_review_publication_invalid")
    return value


def _read_exact_publication_receipt(
    space: Path,
    context: DesktopProviderSearchContextV1,
    stage: Mapping[str, Any],
) -> Any:
    try:
        receipt = read_daily_market_request_receipt_v1(
            _market_store(space),
            _reader_context(context),
            stage["candidate"]["request_ref"],
        )
    except DailyMarketHistoryBlocked as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_publication_invalid"
        ) from error
    if receipt is None:
        _abort("desktop_market_history_review_publication_invalid")
    return _validate_market_receipt(stage, receipt, exact_replay=True)


def _assert_no_unresolved_review(
    space: Path,
    context: DesktopProviderSearchContextV1,
    listing_ref: str,
    *,
    ignore_stage_ref: str | None = None,
) -> None:
    area = space / AREA
    if not area.exists():
        return
    area = _owner_directory(area)
    attempts = area / "fetch-attempts"
    stages = area / "stages"
    have_attempts = attempts.exists()
    if have_attempts:
        attempts = _owner_directory(attempts)
    # Beanstanden kann dieser Abgleich nur eine Stage ohne Versuchsdatei; alle
    # anderen prueft die Schleife darunter ohnehin gegen ihren Versuch. Vorher
    # wurde jede Stage vollstaendig gelesen und hash-geprueft, nur um ihre
    # Listing-Kennung zu erfahren - die die Versuchsdatei mit einem Kilobyte
    # nennt. Bei vielen Stages kostet das viele
    # Sekunden, und die Kette ruft diese Pruefung je Asset dreimal auf:
    # in preview, in stage und in publish. Fuer einen einzigen nachgetragenen
    # Kurstag kostete das Minuten (#283).
    if stages.exists():
        stages = _owner_directory(stages)
        for stage_path in sorted(stages.glob("mhs_*.json")):
            stage_ref = stage_path.stem
            if stage_ref == ignore_stage_ref:
                continue
            if have_attempts and attempts.joinpath(f"{stage_ref}.json").exists():
                continue
            stage = read_desktop_market_history_review_stage_v1(
                space, context, stage_ref
            )
            if stage["listing"]["listing_ref"] == listing_ref:
                _abort("desktop_market_history_review_stage_invalid")
    if not have_attempts:
        return
    for path in _fetch_attempt_paths(area, listing_ref):
        attempt = _read_fetch_attempt(path, context)
        if attempt["listing_ref"] != listing_ref:
            continue
        if attempt["stage_ref"] == ignore_stage_ref:
            continue
        stage_path = _stage_path(space, attempt["stage_ref"])
        if not stage_path.exists():
            failure_path = area / "failures" / f"fetch-{attempt['stage_ref']}.json"
            if not failure_path.exists():
                _abort("desktop_market_history_review_recovery_required")
            failure = _read_fetch_failure(failure_path, attempt)
            recovery_attempt_path = (
                area / "recovery-attempts" / f"fetch-{attempt['stage_ref']}.json"
            )
            recovery_path = (
                area / "recoveries" / f"fetch-{attempt['stage_ref']}.json"
            )
            if not recovery_attempt_path.exists() or not recovery_path.exists():
                _abort("desktop_market_history_review_recovery_required")
            recovery_attempt = _read_fetch_recovery_attempt(
                recovery_attempt_path, attempt, failure, context
            )
            _read_fetch_recovery(
                recovery_path, attempt, failure, recovery_attempt, context
            )
            continue
        stage = read_desktop_market_history_review_stage_v1(
            space, context, attempt["stage_ref"]
        )
        if (
            stage["preview_fingerprint"] != attempt["preview_fingerprint"]
            or stage["listing"]["listing_ref"] != attempt["listing_ref"]
            or stage["scope_start_date"] != attempt["scope_start_date"]
            or stage["scope_end_date"] != attempt["scope_end_date"]
            or stage["mapping_fingerprint"] != attempt["mapping_fingerprint"]
            or stage["context_fingerprint"] != attempt["context_fingerprint"]
            or stage["fetched_at_utc"] < attempt["started_at_utc"]
        ):
            _abort("desktop_market_history_review_stage_invalid")
        publication_path = _publication_path(space, attempt["stage_ref"])
        rejection_path = area / "rejections" / f"{attempt['stage_ref']}.json"
        publish_attempt_path = area / "publish-attempts" / f"{attempt['stage_ref']}.json"
        if publication_path.exists() and rejection_path.exists():
            _abort("desktop_market_history_review_publication_invalid")
        if publication_path.exists():
            if not publish_attempt_path.exists():
                _abort("desktop_market_history_review_publication_invalid")
            publish_attempt = _read_publish_attempt(publish_attempt_path, stage)
            receipt = _read_exact_publication_receipt(space, context, stage)
            _read_publication(publication_path, stage, publish_attempt, receipt)
            continue
        if rejection_path.exists():
            if publish_attempt_path.exists():
                _abort("desktop_market_history_review_publication_invalid")
            _read_rejection(rejection_path, stage)
            continue
        discard_path = _discard_path(space, attempt["stage_ref"])
        if discard_path.exists():
            _read_discard(discard_path, stage)
            continue
        _abort("desktop_market_history_review_recovery_required")


def _read_discard(path: Path, stage: Mapping[str, Any]) -> dict[str, Any]:
    value = _read_sealed(
        path, "discard_fingerprint", "desktop_market_history_review_discard_invalid"
    )
    fields = {
        "contract_version",
        "status",
        "stage_ref",
        "listing_ref",
        "scope_start_date",
        "scope_end_date",
        "candidate_fingerprint",
        "reason",
        "discarded_at_utc",
        "discard_fingerprint",
    }
    if (
        set(value) != fields
        or value["contract_version"] != "desktop_market_history_review_discard_v1"
        or value["status"] != "discarded"
        or value["stage_ref"] != stage["stage_ref"]
        or value["listing_ref"] != stage["listing"]["listing_ref"]
        or value["scope_start_date"] != stage["scope_start_date"]
        or value["scope_end_date"] != stage["scope_end_date"]
        or value["candidate_fingerprint"] != stage["candidate"]["candidate_fingerprint"]
        or value["reason"] != "publication_never_landed"
    ):
        _abort("desktop_market_history_review_discard_invalid")
    _as_utc(value["discarded_at_utc"])
    return value


def discard_desktop_market_history_review_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    stage_ref: str,
    confirmed: bool,
    discarded_at_utc: str,
) -> dict[str, Any]:
    """Loest einen begonnenen, nie angekommenen Schreibvorgang auf.

    Wird eine Veroeffentlichung begonnen und der Vorgang bricht ab, bevor der
    Anhang im Kursspeicher ankommt, bleibt ein verbrauchter
    Veroeffentlichungsversuch ohne Quittung zurueck. Erneut veroeffentlichen
    laesst sich nicht - der Versuch ist verbraucht -, verwerfen bisher auch
    nicht: Ein verworfener Stand mit verbrauchtem Versuch galt als
    widerspruechlich. Damit blieb das Asset dauerhaft gesperrt (etwa nach
    einem Abschalten des Rechners, #283).

    Verworfen wird nur, was nachweislich nie geschrieben wurde: Die Quittung zum
    Kandidaten muss im Kursspeicher fehlen. Die geholten Tage sind damit nicht
    verloren, sondern schlicht ungeschrieben - ein erneuter Abruf holt sie.
    """
    current_context = _context(context)
    if confirmed is not True:
        _abort("desktop_market_history_review_confirmation_required")
    discarded = _as_utc(discarded_at_utc)
    space = _data_space(data_space_path, current_context)
    area = _owner_directory(space / AREA)
    stage = read_desktop_market_history_review_stage_v1(space, current_context, stage_ref)
    publish_attempt_path = area / "publish-attempts" / f"{stage_ref}.json"
    publication_path = _publication_path(space, stage_ref)
    rejection_path = area / "rejections" / f"{stage_ref}.json"
    # Nur der eine Fall, und nur er: begonnener Schreibvorgang, keine
    # Veroeffentlichung, keine Verwerfung - und kein Anhang im Kursspeicher.
    if (
        not publish_attempt_path.exists()
        or publication_path.exists()
        or rejection_path.exists()
    ):
        _abort("desktop_market_history_review_discard_invalid")
    try:
        receipt = read_daily_market_request_receipt_v1(
            _market_store(space),
            _reader_context(current_context),
            stage["candidate"]["request_ref"],
        )
    except DailyMarketHistoryBlocked as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    if receipt is not None:
        # Der Anhang ist angekommen; hier gehoert eine Veroeffentlichung hin,
        # keine Verwerfung. Das loest die Wiederherstellung.
        _abort("desktop_market_history_review_discard_invalid")
    body = {
        "contract_version": "desktop_market_history_review_discard_v1",
        "status": "discarded",
        "stage_ref": stage_ref,
        "listing_ref": stage["listing"]["listing_ref"],
        "scope_start_date": stage["scope_start_date"],
        "scope_end_date": stage["scope_end_date"],
        "candidate_fingerprint": stage["candidate"]["candidate_fingerprint"],
        "reason": "publication_never_landed",
        "discarded_at_utc": discarded,
    }
    _write_create(
        _ensure(area, "discards") / f"{stage_ref}.json",
        {**body, "discard_fingerprint": _sha(body)},
        "desktop_market_history_review_discard_invalid",
    )
    return {
        "contract_version": "desktop_market_history_review_discard_result_v1",
        "status": "discarded",
        "scope_start_date": stage["scope_start_date"],
        "scope_end_date": stage["scope_end_date"],
        "day_count": len(stage["candidate"]["days"]),
        "provider_access": False,
        "network_access": False,
        "market_history_write": False,
        "canonical_write": False,
        "automatic_retry": False,
    }


def discard_unresolved_desktop_market_history_review_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    listing_ref: str,
    confirmed: bool,
    discarded_at_utc: str,
) -> dict[str, Any] | None:
    """Sucht den offenen Stand einer Notierung und verwirft ihn.

    Die Kette fragte zuvor die Wiederherstellung und leitete daraus die Stage ab.
    Deren Antwort wird streng nachgeprueft, und scheitert diese Pruefung, kam das
    Verwerfen nie an die Reihe - die Aufloesung hing an einem Schritt, der selbst
    scheitern kann. Hier wird der offene Stand direkt gesucht: derselbe Vorgang,
    ohne Umweg (#283, 25.09.2026).

    Offen heisst: Veroeffentlichungsversuch vorhanden, keine Veroeffentlichung,
    keine Verwerfung. Ob der Anhang wirklich ausblieb, prueft das Verwerfen
    selbst. Gibt es nichts zu verwerfen, ist das kein Fehler, sondern None.
    """
    current_context = _context(context)
    if confirmed is not True:
        _abort("desktop_market_history_review_confirmation_required")
    if not isinstance(listing_ref, str) or re.fullmatch(r"^lsr_[a-f0-9]{32}$", listing_ref) is None:
        _abort("desktop_market_history_review_input_invalid")
    space = _data_space(data_space_path, current_context)
    area = space / AREA
    attempts_path = area / "fetch-attempts"
    if not area.exists() or not attempts_path.exists():
        return None
    area = _owner_directory(area)
    attempts_path = _owner_directory(attempts_path)
    matches: list[dict[str, Any]] = []
    for path in _fetch_attempt_paths(area, listing_ref):
        attempt = _read_fetch_attempt(path, current_context)
        if attempt["listing_ref"] != listing_ref:
            continue
        stage_ref = attempt["stage_ref"]
        if not _stage_path(space, stage_ref).exists():
            continue
        if not (area / "publish-attempts" / f"{stage_ref}.json").exists():
            continue
        if _publication_path(space, stage_ref).exists():
            continue
        if (area / "rejections" / f"{stage_ref}.json").exists():
            continue
        if _discard_path(space, stage_ref).exists():
            continue
        matches.append(attempt)
    if not matches:
        return None
    matches.sort(key=lambda row: (row["started_at_utc"], row["stage_ref"]))
    return discard_desktop_market_history_review_v1(
        space, current_context, matches[-1]["stage_ref"], True, discarded_at_utc
    )


def _public_recovery_result(
    status: str,
    code: str,
    *,
    provider_access_possible: bool,
    market_history_write_possible: bool,
) -> dict[str, Any]:
    if status not in {"fetch_failed", "recovery_required"} or code not in FAILURE_CODES:
        _abort("desktop_market_history_review_boundary_failed")
    return {
        "market_history_review_recovery_result_version": 1,
        "status": status,
        "code": code,
        "provider_access_possible": provider_access_possible,
        "network_access_possible": provider_access_possible,
        "market_history_write_possible": market_history_write_possible,
        "canonical_write": False,
        "automatic_retry": False,
        "candidate_fingerprint_exposed": False,
        "receipt_fingerprint_exposed": False,
        "context_exposed": False,
        "paths_exposed": False,
        "internal_id_exposed": False,
    }


def publish_desktop_market_history_review_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    stage_ref: str,
    public_review: Mapping[str, Any],
    confirmed: bool,
    completed_at_utc: str,
) -> dict[str, Any]:
    current_context = _context(context)
    completed = _as_utc(completed_at_utc)
    space = _data_space(data_space_path, current_context)
    stage = read_desktop_market_history_review_stage_v1(space, current_context, stage_ref)
    if confirmed is not True:
        _abort("desktop_market_history_review_confirmation_required")
    if not isinstance(public_review, Mapping):
        _abort("market_history_review_stale")
    try:
        confirmation = confirm_market_history_review_v1(
            stage["review_bundle"], dict(public_review), True
        )
    except MarketHistoryReviewV1Error as error:
        raise _review_error(error) from error
    area = _ensure(space, AREA)
    attempts = _ensure(area, "publish-attempts")
    publications = _ensure(area, "publications")
    rejections = _ensure(area, "rejections")
    if rejections.joinpath(f"{stage_ref}.json").exists():
        _abort("desktop_market_history_review_rejected")
    result_path = publications / f"{stage_ref}.json"
    store = _market_store(space)
    reader_context = _reader_context(current_context)
    writer_context = _writer_context(current_context)
    attempt_path = attempts / f"{stage_ref}.json"
    if result_path.exists():
        if not attempt_path.exists():
            _abort("desktop_market_history_review_publication_invalid")
        publish_attempt = _read_publish_attempt(attempt_path, stage)
        if (
            publish_attempt["public_review_fingerprint"]
            != confirmation["public_review_fingerprint"]
            or publish_attempt["confirmation_fingerprint"]
            != confirmation["confirmation_fingerprint"]
        ):
            _abort("desktop_market_history_review_publication_invalid")
        receipt = _read_exact_publication_receipt(space, current_context, stage)
        result = _read_publication(
            result_path, stage, publish_attempt, receipt
        )
        return _public_publication(result, exact_replay=True)
    if attempt_path.exists():
        _read_publish_attempt(attempt_path, stage)
        _abort("desktop_market_history_review_recovery_required")
    try:
        current_listing = read_daily_market_listing_binding_v1(
            store, reader_context, stage["listing"]["listing_ref"]
        )
        current = read_daily_market_history_v1(
            store,
            reader_context,
            stage["listing"]["listing_ref"],
            stage["current_window_start_date"],
            stage["scope_end_date"],
        )
    except DailyMarketHistoryBlocked as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_store_invalid"
        ) from error
    if (
        current_listing != stage["listing"]
        or current["row_set_fingerprint"] != stage["current_history_fingerprint"]
    ):
        _abort("market_history_review_stale")
    if completed < stage["fetched_at_utc"]:
        _abort("desktop_market_history_review_publication_invalid")
    attempt_body = {
        "contract_version": "desktop_market_history_review_publish_attempt_v1",
        "stage_ref": stage_ref,
        "review_ref": stage["review_ref"],
        "candidate_fingerprint": stage["candidate"]["candidate_fingerprint"],
        "public_review_fingerprint": confirmation["public_review_fingerprint"],
        "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
        "context_fingerprint": stage["context_fingerprint"],
        "started_at_utc": completed,
        "provider_access_authorized": False,
        "network_access_authorized": False,
        "provider_refetch_authorized": False,
        "market_history_write_authorized": True,
        "automatic_retry": False,
    }
    attempt = {**attempt_body, "attempt_fingerprint": _sha(attempt_body)}
    with _listing_lock(area, stage["listing"]["listing_ref"]):
        # Publish and reject are competing terminal dispositions. Reserve the
        # write Attempt only after rechecking both under one Listing lock.
        if rejections.joinpath(f"{stage_ref}.json").exists():
            _abort("desktop_market_history_review_rejected")
        if result_path.exists() or attempt_path.exists():
            _abort("desktop_market_history_review_recovery_required")
        _write_create(
            attempt_path,
            attempt,
            "desktop_market_history_review_publish_attempt_consumed",
        )
    try:
        receipt = append_daily_market_history_v1(
            store, writer_context, stage["candidate"], completed
        )
        receipt = _validate_market_receipt(stage, receipt, exact_replay=False)
        persisted_receipt = _read_exact_publication_receipt(
            space, current_context, stage
        )
        receipt_fields = (
            "request_ref",
            "candidate_fingerprint",
            "appended_day_count",
            "corrected_day_count",
            "unchanged_day_count",
            "row_set_fingerprint",
            "receipt_fingerprint",
        )
        if any(
            getattr(receipt, field) != getattr(persisted_receipt, field)
            for field in receipt_fields
        ):
            _abort("desktop_market_history_review_publication_invalid")
        result = _publication_from_receipt(
            stage, confirmation, receipt, completed, exact_replay=False
        )
        _write_create(
            result_path, result, "desktop_market_history_review_publication_invalid"
        )
    except Exception as error:
        raise DesktopMarketHistoryReviewV1Error(
            "desktop_market_history_review_publish_write_failed"
        ) from error
    return _public_publication(result, exact_replay=False)


def reject_desktop_market_history_review_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    stage_ref: str,
    public_review: Mapping[str, Any],
    confirmed: bool,
    rejected_at_utc: str,
) -> dict[str, Any]:
    current_context = _context(context)
    rejected_at = _as_utc(rejected_at_utc)
    space = _data_space(data_space_path, current_context)
    stage = read_desktop_market_history_review_stage_v1(space, current_context, stage_ref)
    if confirmed is not True:
        _abort("desktop_market_history_review_confirmation_required")
    if not isinstance(public_review, Mapping):
        _abort("market_history_review_stale")
    if rejected_at < stage["fetched_at_utc"]:
        _abort("desktop_market_history_review_publication_invalid")
    if _canonical(stage["review_bundle"]["public_review"]) != _canonical(dict(public_review)):
        _abort("market_history_review_stale")
    area = _ensure(space, AREA)
    rejections = _ensure(area, "rejections")
    publications = _ensure(area, "publications")
    publish_attempt = area / "publish-attempts" / f"{stage_ref}.json"
    path = rejections / f"{stage_ref}.json"
    with _listing_lock(area, stage["listing"]["listing_ref"]):
        if publications.joinpath(f"{stage_ref}.json").exists() or publish_attempt.exists():
            _abort("desktop_market_history_review_publication_invalid")
        if path.exists():
            value = _read_rejection(path, stage)
        else:
            body = {
                "contract_version": "desktop_market_history_review_rejection_v1",
                "status": "rejected",
                "stage_ref": stage_ref,
                "review_ref": stage["review_ref"],
                "context_fingerprint": stage["context_fingerprint"],
                "candidate_fingerprint": stage["candidate"]["candidate_fingerprint"],
                "rejected_at_utc": rejected_at,
                "provider_access": False,
                "network_access": False,
                "market_history_write": False,
                "automatic_retry": False,
            }
            value = {**body, "rejection_fingerprint": _sha(body)}
            _write_create(
                path, value, "desktop_market_history_review_publish_attempt_consumed"
            )
    return {
        "market_history_review_rejection_result_version": 1,
        "status": "rejected",
        "review_ref": stage["review_ref"],
        "provider_access": False,
        "network_access": False,
        "market_history_write": False,
        "canonical_write": False,
        "automatic_retry": False,
        "candidate_fingerprint_exposed": False,
        "context_exposed": False,
        "paths_exposed": False,
        "internal_id_exposed": False,
    }


def recover_desktop_market_history_review_v1(
    data_space_path: str | Path,
    context: DesktopProviderSearchContextV1 | Mapping[str, str],
    listing_ref: str,
    confirmed: bool,
    *,
    expected_stage_ref: str | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any] | None:
    current_context = _context(context)
    if confirmed is not True:
        _abort("desktop_market_history_review_confirmation_required")
    if not isinstance(listing_ref, str) or re.fullmatch(r"^lsr_[a-f0-9]{32}$", listing_ref) is None:
        _abort("desktop_market_history_review_input_invalid")
    space = _data_space(data_space_path, current_context)
    area = space / AREA
    attempts_path = area / "fetch-attempts"
    if not area.exists() or not attempts_path.exists():
        return None
    area = _owner_directory(area)
    attempts_path = _owner_directory(attempts_path)
    matches: list[dict[str, Any]] = []
    for path in _fetch_attempt_paths(area, listing_ref):
        attempt = _read_fetch_attempt(path, current_context)
        if attempt["listing_ref"] == listing_ref:
            matches.append(attempt)
    if expected_stage_ref is not None:
        if not isinstance(expected_stage_ref, str) or _STAGE_REF.fullmatch(expected_stage_ref) is None:
            _abort("desktop_market_history_review_input_invalid")
        matches = [row for row in matches if row["stage_ref"] == expected_stage_ref]
    if not matches:
        return None
    matches.sort(key=lambda row: (row["started_at_utc"], row["stage_ref"]))
    attempt = matches[-1]
    stage_ref = attempt["stage_ref"]
    stage_path = _stage_path(space, stage_ref)
    if not stage_path.exists():
        failure_path = area / "failures" / f"fetch-{stage_ref}.json"
        # Begonnen, aber weder Stage noch Fehlschlag: Der Prozess endete mitten im Abruf. Lag ein Neustart dazwischen, ist
        # das sicher; dann wird der Versuch als unterbrochen festgehalten (nur angehaengt) und unten wie jeder Fehlschlag
        # aufgeloest. Ohne diesen Schritt blieb die Notierung dauerhaft gesperrt: Startet der Rechner mitten in einem Abruf neu, hielt jeder Lauf danach an diesem Asset an.
        boot = _system_boot_utc()
        if not failure_path.exists() and boot is not None and attempt["started_at_utc"] < boot:
            with _listing_lock(area, listing_ref):
                if not stage_path.exists() and not failure_path.exists():
                    failed_at = _now(clock)
                    if failed_at < attempt["started_at_utc"]:
                        failed_at = attempt["started_at_utc"]
                    failure_body = {
                        "contract_version": "desktop_market_history_review_fetch_failure_v1",
                        "stage_ref": stage_ref,
                        "preview_fingerprint": attempt["preview_fingerprint"],
                        "attempt_fingerprint": attempt["attempt_fingerprint"],
                        "failure_code": "desktop_market_history_review_fetch_interrupted",
                        "failed_at_utc": failed_at,
                        "provider_access_possible": True,
                        "network_access_possible": True,
                        "market_history_write": False,
                        "automatic_retry": False,
                    }
                    _write_create(
                        _ensure(area, "failures") / f"fetch-{stage_ref}.json",
                        {**failure_body, "failure_fingerprint": _sha(failure_body)},
                        "desktop_market_history_review_recovery_required",
                    )
        if not stage_path.exists() and failure_path.exists():
            failure = _read_fetch_failure(failure_path, attempt)
            recovery_attempts = _ensure(area, "recovery-attempts")
            recovery_attempt_path = (
                recovery_attempts / f"fetch-{stage_ref}.json"
            )
            if recovery_attempt_path.exists():
                recovery_attempt = _read_fetch_recovery_attempt(
                    recovery_attempt_path, attempt, failure, current_context
                )
            else:
                recovery_attempt = _fetch_recovery_attempt_evidence(
                    attempt, failure, current_context
                )
                _write_create(
                    recovery_attempt_path,
                    recovery_attempt,
                    "desktop_market_history_review_recovery_required",
                )
                recovery_attempt = _read_fetch_recovery_attempt(
                    recovery_attempt_path, attempt, failure, current_context
                )
            recoveries = _ensure(area, "recoveries")
            recovery_path = recoveries / f"fetch-{stage_ref}.json"
            if recovery_path.exists():
                _read_fetch_recovery(
                    recovery_path,
                    attempt,
                    failure,
                    recovery_attempt,
                    current_context,
                )
            else:
                recovery = _fetch_recovery_evidence(
                    attempt, failure, recovery_attempt, current_context
                )
                _write_create(
                    recovery_path,
                    recovery,
                    "desktop_market_history_review_recovery_required",
                )
                _read_fetch_recovery(
                    recovery_path,
                    attempt,
                    failure,
                    recovery_attempt,
                    current_context,
                )
            return {
                "state": "fetch_failed",
                "stage_ref": stage_ref,
                "public_review": None,
                "public_result": _public_recovery_result(
                    "fetch_failed",
                    failure["failure_code"],
                    provider_access_possible=True,
                    market_history_write_possible=False,
                ),
            }
        return {
            "state": "recovery_required",
            "stage_ref": stage_ref,
            "public_review": None,
            "public_result": _public_recovery_result(
                "recovery_required",
                "desktop_market_history_review_recovery_required",
                provider_access_possible=True,
                market_history_write_possible=False,
            ),
        }

    stage = read_desktop_market_history_review_stage_v1(
        space, current_context, stage_ref
    )
    if (
        stage["preview_fingerprint"] != attempt["preview_fingerprint"]
        or stage["listing"]["listing_ref"] != attempt["listing_ref"]
        or stage["scope_start_date"] != attempt["scope_start_date"]
        or stage["scope_end_date"] != attempt["scope_end_date"]
        or stage["mapping_fingerprint"] != attempt["mapping_fingerprint"]
        or stage["context_fingerprint"] != attempt["context_fingerprint"]
        or stage["fetched_at_utc"] < attempt["started_at_utc"]
    ):
        _abort("desktop_market_history_review_stage_invalid")
    publication_path = _publication_path(space, stage_ref)
    rejection_path = area / "rejections" / f"{stage_ref}.json"
    publish_attempt_path = area / "publish-attempts" / f"{stage_ref}.json"
    if publication_path.exists() and rejection_path.exists():
        _abort("desktop_market_history_review_publication_invalid")
    if publication_path.exists():
        if not publish_attempt_path.exists():
            _abort("desktop_market_history_review_publication_invalid")
        publish_attempt = _read_publish_attempt(publish_attempt_path, stage)
        receipt = _read_exact_publication_receipt(space, current_context, stage)
        result = _read_publication(
            publication_path, stage, publish_attempt, receipt
        )
        return {
            "state": "published",
            "stage_ref": stage_ref,
            "public_review": stage["review_bundle"]["public_review"],
            "public_result": _public_publication(result, exact_replay=True),
        }
    if rejection_path.exists():
        if publish_attempt_path.exists():
            _abort("desktop_market_history_review_publication_invalid")
        _read_rejection(rejection_path, stage)
        return {
            "state": "rejected",
            "stage_ref": stage_ref,
            "public_review": stage["review_bundle"]["public_review"],
            "public_result": {
                "market_history_review_rejection_result_version": 1,
                "status": "rejected",
                "review_ref": stage["review_ref"],
                "provider_access": False,
                "network_access": False,
                "market_history_write": False,
                "canonical_write": False,
                "automatic_retry": False,
                "candidate_fingerprint_exposed": False,
                "context_exposed": False,
                "paths_exposed": False,
                "internal_id_exposed": False,
            },
        }
    if publish_attempt_path.exists():
        publish_attempt = _read_publish_attempt(publish_attempt_path, stage)
        try:
            confirmation = confirm_market_history_review_v1(
                stage["review_bundle"],
                stage["review_bundle"]["public_review"],
                True,
            )
        except MarketHistoryReviewV1Error as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_publication_invalid"
            ) from error
        if (
            publish_attempt["public_review_fingerprint"]
            != confirmation["public_review_fingerprint"]
            or publish_attempt["confirmation_fingerprint"]
            != confirmation["confirmation_fingerprint"]
        ):
            _abort("desktop_market_history_review_publication_invalid")
        try:
            receipt = read_daily_market_request_receipt_v1(
                _market_store(space),
                _reader_context(current_context),
                stage["candidate"]["request_ref"],
            )
        except DailyMarketHistoryBlocked as error:
            raise DesktopMarketHistoryReviewV1Error(
                "desktop_market_history_review_recovery_required"
            ) from error
        if receipt is None:
            return {
                "state": "recovery_required",
                "stage_ref": stage_ref,
                "public_review": stage["review_bundle"]["public_review"],
                "public_result": _public_recovery_result(
                    "recovery_required",
                    "desktop_market_history_review_recovery_required",
                    provider_access_possible=False,
                    market_history_write_possible=True,
                ),
            }
        if receipt.candidate_fingerprint != stage["candidate"]["candidate_fingerprint"]:
            _abort("desktop_market_history_review_publication_invalid")
        result = _publication_from_receipt(
            stage,
            confirmation,
            receipt,
            publish_attempt["started_at_utc"],
            exact_replay=True,
        )
        publications = _ensure(area, "publications")
        _write_create(
            publications / f"{stage_ref}.json",
            result,
            "desktop_market_history_review_publication_invalid",
        )
        return {
            "state": "published",
            "stage_ref": stage_ref,
            "public_review": stage["review_bundle"]["public_review"],
            "public_result": _public_publication(result, exact_replay=True),
        }
    return {
        "state": "staged_review",
        "stage_ref": stage_ref,
        "public_review": stage["review_bundle"]["public_review"],
        "public_result": None,
    }


__all__ = [
    "DesktopMarketHistoryReviewV1Error",
    "desktop_market_history_review_v1_error_codes",
    "preview_desktop_market_history_review_fetch_v1",
    "public_desktop_market_history_review_fetch_preview_v1",
    "public_desktop_market_history_review_stage_v1",
    "publish_desktop_market_history_review_v1",
    "read_desktop_market_history_notation_v1",
    "read_desktop_market_history_notations_v1",
    "read_desktop_market_history_review_stage_v1",
    "recover_desktop_market_history_review_v1",
    "reject_desktop_market_history_review_v1",
    "stage_desktop_market_history_review_fetch_v1",
]
