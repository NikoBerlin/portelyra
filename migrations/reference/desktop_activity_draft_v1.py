"""Persistent shared ActivityDraft boundary for manual, CSV, and correction flows.

Draft persistence is owner-local and has no canonical write authority. One shared
validator turns complete drafts into the existing native-create or immutable-
correction product preview. The optional apply boundary delegates to those sole
schema-401 writers after a durable one-use draft attempt.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from migrations.reference.desktop_product_asset_activity_v1 import (
    NATIVE_EVENT_KEYS,
    FIFO_ORDER_EVIDENCE_KEYS,
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _context as _product_context,
    _context_fingerprint,
    _native_fifo_order_evidence,
    apply_desktop_native_asset_activity_v1,
    preview_desktop_native_asset_activity_v1,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.desktop_asset_activity_correction_v1 import (
    DesktopAssetActivityCorrectionV1Error,
    apply_desktop_asset_activity_correction_v1,
    build_desktop_asset_activity_correction_confirmation_v1,
    preview_desktop_asset_activity_correction_v1,
    read_desktop_asset_activity_voided_event_refs_v1,
    reconcile_desktop_asset_activity_multi_void_v2,
)

CONTRACT_VERSION = 1
AREA_NAME = "activity-drafts-v1"
DRAFTS_NAME = "drafts"
ATTEMPTS_NAME = "attempts"
PROFILES_NAME = "mapping-profiles"
SUPERSESSION_GENERATIONS_NAME = "supersession-generations"
SUPERSESSION_ATTEMPTS_NAME = "supersession-attempts"
SUPERSESSION_ACTIVE_NAME = "active-supersession-generation.json"
LOCK_NAME = ".writer.lock"
LOCK_V2_NAME = ".writer-v2.lock"
LOCK_BARRIER_NAME = "immutable-source-supersession-v1.json"
LOCK_MIXED_SOURCE_RETIREMENT_BARRIER_NAME = "mixed-source-retirement-v1.json"
DRAFT_REF = re.compile(r"^adt_[a-f0-9]{32}$")
PROFILE_REF = re.compile(r"^amp_[a-f0-9]{32}$")
SUPERSESSION_GENERATION_REF = re.compile(r"^adg_[a-f0-9]{32}$")
CHALLENGE = re.compile(r"^adc_[a-f0-9]{16,64}$")
SUPERSESSION_CHALLENGE = re.compile(r"^ads_[a-f0-9]{16,64}$")
REFERENCE = re.compile(r"^[a-z]{2,8}_[a-f0-9]{16,64}$")
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
SHA = re.compile(r"^[a-f0-9]{64}$")
ORIGIN_TYPES = frozenset({"manual_form", "tolerant_csv", "correction"})
ACTION_TYPES = frozenset({"create", "correct", "void"})
DRAFT_STATES = frozenset({"editing", "validated_ready", "validated_blocked", "applying", "committed"})
EFFECTIVE_DRAFT_STATES = DRAFT_STATES | frozenset({"superseded"})
SUPERSEDABLE_DRAFT_STATES = frozenset({"editing", "validated_ready", "validated_blocked"})
VALIDATION_STATUSES = frozenset({"not_validated", "needs_input", "ready", "blocked"})
ISSUE_CODES = frozenset({"activity_draft_fields_missing", "activity_draft_domain_invalid"})
UNCLASSIFIED_FEE_RESOLUTIONS = frozenset({
    "not_present", "unresolved", "monetary_fee", "asset_fee_quantity", "zero_no_fee",
})
VALUATION_ORIGINS = frozenset({"source_provided", "source_missing", "not_applicable"})
VALUATION_VALUE_MODES = frozenset({"unit_price", "fiat_total", "none"})
DRAFT_INPUT_FIELDS = NATIVE_EVENT_KEYS | frozenset({"unclassified_fee_resolution"})
LEGACY_DRAFT_KEYS = frozenset({
    "activity_draft_version", "draft_ref", "context_fingerprint", "portfolio_id",
    "origin_type", "action_type", "predecessor_event_ref", "event", "revision",
    "draft_state", "validation_status", "validation", "created_at_utc",
    "updated_at_utc", "validated_at_utc", "committed_at_utc", "domain_result",
    "draft_fingerprint",
})
DRAFT_KEYS = LEGACY_DRAFT_KEYS | frozenset({"source_binding", "source_auxiliary"})
PROFILE_KEYS = frozenset({
    "activity_mapping_profile_version", "profile_ref", "context_fingerprint",
    "profile_label", "is_standard", "revision", "default_portfolio_id",
    "default_account_id", "portfolio_mappings", "account_mappings", "asset_mappings",
    "created_at_utc", "updated_at_utc", "profile_fingerprint",
})
VALIDATION_KEYS = frozenset({
    "activity_draft_validation_version", "validator_id", "draft_revision",
    "input_fingerprint", "validated_at_utc", "missing_fields", "issue_codes",
    "plan_kind", "expected_preview_fingerprint", "domain_public_preview",
    "trusted_preview", "status", "validation_fingerprint",
})
FAILPOINTS = frozenset({None, "after_draft_attempt", "after_domain_commit"})
SUPERSESSION_FAILPOINTS = frozenset({
    None, "after_supersession_attempt", "after_supersession_generation",
    "after_supersession_barrier",
})
FAILURE_CODES = frozenset({
    "activity_draft_attempt_conflict",
    "activity_draft_boundary_failed",
    "activity_draft_confirmation_expired",
    "activity_draft_confirmation_invalid",
    "activity_draft_context_invalid",
    "activity_draft_domain_invalid",
    "activity_draft_input_invalid",
    "activity_draft_not_found",
    "activity_draft_publication_failed",
    "activity_draft_revision_conflict",
    "activity_draft_source_binding_conflict",
    "activity_draft_source_superseded",
    "activity_draft_state_conflict",
    "activity_draft_storage_invalid",
    "activity_draft_supersession_conflict",
    "activity_draft_supersession_not_found",
    "synthetic_activity_draft_failpoint",
    "synthetic_activity_draft_supersession_failpoint",
})


class DesktopActivityDraftV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("activity_draft_error_code_unregistered")
        self.code = code
        super().__init__(code)


def desktop_activity_draft_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise DesktopActivityDraftV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        _abort("activity_draft_input_invalid")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc(value: Any) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("activity_draft_input_invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort("activity_draft_input_invalid")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _abort("activity_draft_input_invalid")
    return value


def _context(value: Any) -> DesktopProductAssetActivityContextV1:
    try:
        return _product_context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("activity_draft_context_invalid")


# Verzeichnisse, deren ganze Kette innerhalb des laufenden Lesevorgangs schon
# geprueft ist. Ausserhalb eines Lesevorgangs None: Dann prueft jeder Aufruf die
# ganze Kette wie bisher.
_VERIFIED_DIRECTORIES: set[str] | None = None


@contextmanager
def _verified_directories():
    """Die Verzeichniskette je Lesevorgang einmal pruefen, nicht je Datei.

    Jeder Entwurf wurde ueber zwei volle Ketten gelesen - Entwurfsverzeichnis und
    Datei, je ein lstat fuer jede Ebene ab der Wurzel. Bei vielen Entwuerfen waren
    das viele lstat fuer immer dieselben Verzeichnisse und ein grosser Teil
    der Zeit der Entwurfsliste. Innerhalb eines
    Lesevorgangs gilt eine gepruefte Kette als geprueft; das Blatt selbst - kein
    Symlink, Art, Rechte - wird weiter bei jedem Zugriff geprueft. Schreibende
    Wege oeffnen keinen solchen Vorgang und pruefen wie bisher.
    """
    global _VERIFIED_DIRECTORIES
    previous = _VERIFIED_DIRECTORIES
    if previous is None:
        _VERIFIED_DIRECTORIES = set()
    try:
        yield
    finally:
        _VERIFIED_DIRECTORIES = previous


def _existing_path(path: Path, *, directory: bool) -> Path:
    if not path.is_absolute():
        _abort("activity_draft_storage_invalid")
    verified = _VERIFIED_DIRECTORIES
    parent = str(path.parent)
    if verified is not None and parent in verified:
        try:
            if path.is_symlink():
                _abort("activity_draft_storage_invalid")
        except OSError:
            _abort("activity_draft_storage_invalid")
    else:
        current = Path(path.anchor)
        for part in path.parts[1:]:
            current = current / part
            try:
                if current.is_symlink():
                    _abort("activity_draft_storage_invalid")
            except OSError:
                _abort("activity_draft_storage_invalid")
    try:
        metadata = path.stat()
    except OSError:
        _abort("activity_draft_storage_invalid")
    if directory != stat.S_ISDIR(metadata.st_mode) or (metadata.st_mode & 0o077):
        _abort("activity_draft_storage_invalid")
    if not directory and not stat.S_ISREG(metadata.st_mode):
        _abort("activity_draft_storage_invalid")
    if verified is not None:
        verified.add(parent)
        if directory:
            verified.add(str(path))
    return path


def _directory(path: Path, *, create: bool = False) -> Path:
    if create and not path.exists():
        parent = _existing_path(path.parent, directory=True)
        try:
            os.mkdir(parent / path.name, 0o700)
            os.chmod(parent / path.name, 0o700)
        except OSError:
            _abort("activity_draft_storage_invalid")
    return _existing_path(path, directory=True)


def _file(path: Path) -> Path:
    return _existing_path(path, directory=False)


def _area(data_space_value: str | Path, *, create: bool = True) -> Path:
    data_space = _directory(Path(data_space_value))
    return _directory(data_space / AREA_NAME, create=create)


def _write_new(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
        parent = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except OSError:
        _abort("activity_draft_storage_invalid")


def _replace(path: Path, content: bytes) -> None:
    temporary = path.parent / (".draft-tmp-" + secrets.token_hex(16))
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        parent = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except OSError:
        if temporary.exists() and not temporary.is_symlink():
            temporary.unlink(missing_ok=True)
        _abort("activity_draft_publication_failed")


def _strict_owner_directory(path: Path) -> Path:
    value = _directory(path)
    try:
        metadata = value.stat()
    except OSError:
        _abort("activity_draft_storage_invalid")
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        _abort("activity_draft_storage_invalid")
    return value


def _strict_owner_file(path: Path) -> Path:
    value = _file(path)
    try:
        metadata = value.stat()
    except OSError:
        _abort("activity_draft_storage_invalid")
    if (
        metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
    ):
        _abort("activity_draft_storage_invalid")
    return value


def _read_owner_json(path: Path) -> dict[str, Any]:
    path = _strict_owner_file(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _abort("activity_draft_storage_invalid")
    if not isinstance(value, dict) or raw != _canonical(value) + b"\n":
        _abort("activity_draft_storage_invalid")
    return value


def _writer_barrier_body() -> dict[str, Any]:
    body = {
        "activity_draft_writer_barrier_version": 1,
        "minimum_writer_capability": "immutable_exact_source_generation_supersession_v1",
        "legacy_writer_blocked": True,
    }
    body["barrier_fingerprint"] = _fingerprint(body)
    return body


def _mixed_source_retirement_barrier_body() -> dict[str, Any]:
    body = {
        "activity_draft_writer_barrier_version": 2,
        "minimum_writer_capability": "mixed_source_retirement_preserve_committed_v1",
        "legacy_writer_blocked": True,
    }
    body["barrier_fingerprint"] = _fingerprint(body)
    return body


def _validate_mixed_source_retirement_barrier(area: Path) -> dict[str, Any]:
    barrier = _strict_owner_directory(area / LOCK_NAME)
    value = _read_owner_json(barrier / LOCK_MIXED_SOURCE_RETIREMENT_BARRIER_NAME)
    body = dict(value)
    fingerprint = body.pop("barrier_fingerprint", None)
    if body != {
        "activity_draft_writer_barrier_version": 2,
        "minimum_writer_capability": "mixed_source_retirement_preserve_committed_v1",
        "legacy_writer_blocked": True,
    } or fingerprint != _fingerprint(body):
        _abort("activity_draft_storage_invalid")
    return value


def _validate_writer_barrier(area: Path) -> dict[str, Any]:
    barrier = _strict_owner_directory(area / LOCK_NAME)
    try:
        children = {item.name for item in barrier.iterdir()}
    except OSError:
        _abort("activity_draft_storage_invalid")
    allowed = {LOCK_BARRIER_NAME, LOCK_MIXED_SOURCE_RETIREMENT_BARRIER_NAME}
    if LOCK_BARRIER_NAME not in children or not children <= allowed:
        _abort("activity_draft_storage_invalid")
    value = _read_owner_json(barrier / LOCK_BARRIER_NAME)
    body = dict(value)
    fingerprint = body.pop("barrier_fingerprint", None)
    if body != {
        "activity_draft_writer_barrier_version": 1,
        "minimum_writer_capability": "immutable_exact_source_generation_supersession_v1",
        "legacy_writer_blocked": True,
    } or fingerprint != _fingerprint(body):
        _abort("activity_draft_storage_invalid")
    if LOCK_MIXED_SOURCE_RETIREMENT_BARRIER_NAME in children:
        _validate_mixed_source_retirement_barrier(area)
    return value


class _DraftWriterLockV1:
    def __init__(self, area: Path):
        self.area = area
        self.path = area / LOCK_NAME
        self.descriptor: int | None = None
        self.barrier_active = False

    def __enter__(self) -> "_DraftWriterLockV1":
        legacy = self.area / LOCK_NAME
        try:
            if legacy.is_symlink():
                _abort("activity_draft_storage_invalid")
            if legacy.exists() and legacy.is_dir():
                _validate_writer_barrier(self.area)
                self.path = self.area / LOCK_V2_NAME
                self.barrier_active = True
            elif legacy.exists() and not legacy.is_file():
                _abort("activity_draft_storage_invalid")
            self.descriptor = os.open(
                self.path,
                os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.chmod(self.path, 0o600)
            metadata = os.fstat(self.descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
            ):
                _abort("activity_draft_storage_invalid")
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except DesktopActivityDraftV1Error:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            raise
        except OSError:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            _abort("activity_draft_state_conflict")
        return self

    def install_supersession_barrier(self) -> None:
        if self.descriptor is None:
            _abort("activity_draft_state_conflict")
        if self.barrier_active:
            _validate_writer_barrier(self.area)
            return
        if self.path != self.area / LOCK_NAME:
            _abort("activity_draft_storage_invalid")
        try:
            descriptor_metadata = os.fstat(self.descriptor)
            path_metadata = os.lstat(self.path)
        except OSError:
            _abort("activity_draft_storage_invalid")
        if (
            not stat.S_ISREG(path_metadata.st_mode)
            or descriptor_metadata.st_dev != path_metadata.st_dev
            or descriptor_metadata.st_ino != path_metadata.st_ino
            or path_metadata.st_uid != os.getuid()
            or stat.S_IMODE(path_metadata.st_mode) != 0o600
            or path_metadata.st_nlink != 1
        ):
            _abort("activity_draft_storage_invalid")
        temporary = self.area / (".writer-barrier-tmp-" + secrets.token_hex(16))
        try:
            os.mkdir(temporary, 0o700)
            os.chmod(temporary, 0o700)
            _write_new(
                temporary / LOCK_BARRIER_NAME,
                _canonical(_writer_barrier_body()) + b"\n",
            )
            os.unlink(self.path)
            os.rename(temporary, self.area / LOCK_NAME)
            parent = os.open(self.area, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(parent)
            finally:
                os.close(parent)
        except OSError:
            if temporary.exists() and temporary.is_dir():
                for child in temporary.iterdir():
                    child.unlink(missing_ok=True)
                temporary.rmdir()
            _abort("activity_draft_storage_invalid")
        self.barrier_active = True
        _validate_writer_barrier(self.area)

    def install_mixed_source_retirement_barrier(self) -> None:
        if self.descriptor is None or not self.barrier_active:
            _abort("activity_draft_state_conflict")
        _validate_writer_barrier(self.area)
        barrier = self.area / LOCK_NAME
        marker = barrier / LOCK_MIXED_SOURCE_RETIREMENT_BARRIER_NAME
        content = _canonical(_mixed_source_retirement_barrier_body()) + b"\n"
        if marker.exists():
            if _strict_owner_file(marker).read_bytes() != content:
                _abort("activity_draft_storage_invalid")
        else:
            _write_new(marker, content)
            try:
                parent = os.open(barrier, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
            except OSError:
                _abort("activity_draft_storage_invalid")
        _validate_mixed_source_retirement_barrier(self.area)
        _validate_writer_barrier(self.area)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self.descriptor is not None:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            os.close(self.descriptor)
            self.descriptor = None


def _safe_event(value: Any) -> dict[str, str | None]:
    if not isinstance(value, Mapping):
        _abort("activity_draft_input_invalid")
    if set(value) - NATIVE_EVENT_KEYS:
        _abort("activity_draft_input_invalid")
    event: dict[str, str | None] = {}
    for key, item in value.items():
        if item is not None and (
            not isinstance(item, str)
            or item != item.strip()
            or len(item.encode("utf-8")) > 512
            or any(ord(character) < 32 for character in item)
        ):
            _abort("activity_draft_input_invalid")
        event[key] = item
    return event


def _safe_text(value: Any, *, maximum: int, allow_empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or (not allow_empty and not value)
        or len(value.encode("utf-8")) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        _abort("activity_draft_input_invalid")
    return value


def _decimal_text(value: Any) -> str:
    text = _safe_text(value, maximum=80)
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        _abort("activity_draft_input_invalid")
    if not parsed.is_finite():
        _abort("activity_draft_input_invalid")
    return text


def _source_binding(
    value: Any,
    context: DesktopProductAssetActivityContextV1,
    mapping_fingerprint: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _abort("activity_draft_input_invalid")
    supplied = dict(value)
    expected_input = {"source_fingerprint", "source_row_ordinal", "source_row_key"}
    expected_stored = expected_input | {
        "activity_draft_source_binding_version", "context_fingerprint",
        "mapping_fingerprint", "binding_fingerprint",
    }
    supplied_keys = set(supplied)
    if supplied_keys != expected_input and supplied_keys != expected_stored:
        _abort("activity_draft_input_invalid")
    source_fingerprint = supplied.get("source_fingerprint")
    ordinal = supplied.get("source_row_ordinal")
    row_key = _safe_text(supplied.get("source_row_key"), maximum=200)
    if (
        not isinstance(source_fingerprint, str)
        or SHA.fullmatch(source_fingerprint) is None
        or isinstance(ordinal, bool)
        or not isinstance(ordinal, int)
        or ordinal < 1
    ):
        _abort("activity_draft_input_invalid")
    stored_mapping = supplied.get("mapping_fingerprint") if supplied_keys == expected_stored else mapping_fingerprint
    if not isinstance(stored_mapping, str) or SHA.fullmatch(stored_mapping) is None or (mapping_fingerprint is not None and stored_mapping != mapping_fingerprint):
        _abort("activity_draft_input_invalid")
    body = {
        "activity_draft_source_binding_version": 1,
        "context_fingerprint": _context_fingerprint(context),
        "source_fingerprint": source_fingerprint,
        "source_row_ordinal": ordinal,
        "source_row_key": row_key,
        "mapping_fingerprint": stored_mapping,
    }
    body["binding_fingerprint"] = _fingerprint(body)
    if supplied_keys == expected_stored and supplied != body:
        _abort("activity_draft_input_invalid")
    return body


def _source_mapping_fingerprint(portfolio_id: str, event: Mapping[str, Any]) -> str:
    return _fingerprint({
        "portfolio_id": portfolio_id,
        "account_ref": event.get("account_ref"),
        "related_account_ref": event.get("related_account_ref"),
        "asset_ref": event.get("asset_ref"),
        "source_asset_ref": event.get("source_asset_ref"),
    })


def _bound_event_ref(binding: Mapping[str, Any]) -> str:
    material = "|".join((
        "tolerant-csv-activity", binding["context_fingerprint"],
        binding["source_fingerprint"], str(binding["source_row_ordinal"]),
    ))
    return "evt_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _valuation_evidence(value: Any) -> dict[str, Any]:
    keys = {
        "adapter_id", "adapter_version", "valuation_origin", "source_value_mode",
        "price_currency", "source_unit_price_decimal", "source_fiat_total_decimal",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        _abort("activity_draft_input_invalid")
    adapter_id = _safe_text(value.get("adapter_id"), maximum=80)
    adapter_version = _safe_text(value.get("adapter_version"), maximum=40)
    origin = value.get("valuation_origin")
    mode = value.get("source_value_mode")
    currency = value.get("price_currency")
    unit = value.get("source_unit_price_decimal")
    total = value.get("source_fiat_total_decimal")
    if (
        not re.fullmatch(r"[a-z][a-z0-9_]{7,80}", adapter_id)
        or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", adapter_version)
        or origin not in VALUATION_ORIGINS
        or mode not in VALUATION_VALUE_MODES
    ):
        _abort("activity_draft_input_invalid")
    if currency is not None:
        currency = _safe_text(currency, maximum=12)
        if re.fullmatch(r"[A-Z]{3}", currency) is None:
            _abort("activity_draft_input_invalid")
    if unit is not None:
        unit = _decimal_text(unit)
        if Decimal(unit) < 0:
            _abort("activity_draft_input_invalid")
    if total is not None:
        total = _decimal_text(total)
        if Decimal(total) < 0:
            _abort("activity_draft_input_invalid")
    valid_shape = (
        origin == "source_missing" and mode == "none" and currency is not None and unit is None and total is None
        or origin == "not_applicable" and mode == "none" and currency is None and unit is None and total is None
        or origin == "source_provided" and mode == "unit_price" and currency is not None and unit is not None and total is None
        or origin == "source_provided" and mode == "fiat_total" and currency is not None and unit is None and total is not None
    )
    if not valid_shape:
        _abort("activity_draft_input_invalid")
    return {
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "valuation_origin": origin,
        "source_value_mode": mode,
        "price_currency": currency,
        "source_unit_price_decimal": unit,
        "source_fiat_total_decimal": total,
    }


def _draft_fifo_order_evidence(value: Any, event: Mapping[str, Any]) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return _native_fifo_order_evidence(value, event)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 2:
        _abort("activity_draft_input_invalid")
    rows = [dict(row) for row in value if isinstance(row, Mapping)]
    if len(rows) != len(value) or len({row.get("event_ref") for row in rows}) != len(rows):
        _abort("activity_draft_input_invalid")
    candidate = [row for row in rows if row.get("event_ref") == event.get("event_ref")]
    if len(candidate) != 1:
        _abort("activity_draft_input_invalid")
    _native_fifo_order_evidence(candidate[0], event)
    decision = candidate[0]["owner_decision_fingerprint"]
    source = candidate[0]["source_file_fingerprint"]
    ordinals = set()
    for row in rows:
        if set(row) != FIFO_ORDER_EVIDENCE_KEYS:
            _abort("activity_draft_input_invalid")
        body = {key: row[key] for key in FIFO_ORDER_EVIDENCE_KEYS if key != "evidence_fingerprint"}
        ordinal = row.get("source_row_ordinal")
        if row.get("evidence_mode") != "owner_confirmed_source_row_order" or row.get("owner_decision_fingerprint") != decision or row.get("source_file_fingerprint") != source or isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1 or ordinal in ordinals or row.get("evidence_fingerprint") != _fingerprint(body):
            _abort("activity_draft_input_invalid")
        ordinals.add(ordinal)
    return sorted(rows, key=lambda row: row["event_ref"])


def _source_auxiliary(
    value: Any, event: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    base_keys = {"unclassified_fee_decimal", "unclassified_fee_resolution"}
    optional_keys = {"fifo_order_evidence", "valuation_evidence", "confirmed_reward_valuation", "source_fee_evidence"}
    if not isinstance(value, Mapping) or not base_keys <= set(value) or set(value) - base_keys - optional_keys:
        _abort("activity_draft_input_invalid")
    fee = value.get("unclassified_fee_decimal")
    resolution = value.get("unclassified_fee_resolution")
    if resolution not in UNCLASSIFIED_FEE_RESOLUTIONS:
        _abort("activity_draft_input_invalid")
    if fee is None:
        if resolution != "not_present":
            _abort("activity_draft_input_invalid")
        result = {"unclassified_fee_decimal": None, "unclassified_fee_resolution": resolution}
    else:
        fee = _decimal_text(fee)
        if resolution == "not_present":
            _abort("activity_draft_input_invalid")
        if resolution == "zero_no_fee" and Decimal(fee) != 0:
            _abort("activity_draft_input_invalid")
        result = {"unclassified_fee_decimal": fee, "unclassified_fee_resolution": resolution}
    if "source_fee_evidence" in value:
        source_fee = value.get("source_fee_evidence")
        if (
            not isinstance(source_fee, Mapping)
            or set(source_fee) != {"fee_decimal", "fee_currency", "treatment"}
            or source_fee.get("treatment") != "source_retained_not_reapplied"
            or not isinstance(source_fee.get("fee_currency"), str)
            or re.fullmatch(r"[A-Z]{3}", source_fee["fee_currency"]) is None
        ):
            _abort("activity_draft_input_invalid")
        result["source_fee_evidence"] = {
            "fee_decimal": _decimal_text(source_fee.get("fee_decimal")),
            "fee_currency": source_fee["fee_currency"],
            "treatment": source_fee["treatment"],
        }
    if "fifo_order_evidence" in value:
        if event is None:
            _abort("activity_draft_input_invalid")
        try:
            result["fifo_order_evidence"] = _draft_fifo_order_evidence(
                value.get("fifo_order_evidence"), event
            )
        except DesktopProductAssetActivityV1Error:
            _abort("activity_draft_input_invalid")
    if "valuation_evidence" in value:
        result["valuation_evidence"] = _valuation_evidence(value.get("valuation_evidence"))
    if "confirmed_reward_valuation" in value:
        evidence = value.get("confirmed_reward_valuation")
        required = {"contract_version", "status", "valuation_method", "local_date", "unit_price_decimal", "fiat_total_decimal", "valuation_currency", "fx_route", "asset_evidence_fingerprint", "fx_evidence_fingerprint", "candidate_fingerprint", "provider_access", "activity_draft_write", "canonical_write"}
        fx_timing = {"fx_observation_date", "fx_rate_age_days", "fx_selection_basis"}
        source_fingerprint = {"source_valuation_evidence_fingerprint"}
        allowed_keys = {
            frozenset(required), frozenset(required | fx_timing),
            frozenset(required | fx_timing | source_fingerprint),
        }
        if not isinstance(evidence, Mapping) or frozenset(evidence) not in allowed_keys or evidence.get("contract_version") != "reward_valuation_evidence_v1" or evidence.get("status") != "confirmed" or evidence.get("valuation_method") not in {"intraday_observation", "daily_close_fallback", "source_fiat_total_fx", "source_unit_price_fx"} or evidence.get("fx_route") not in {"identity", "direct", "inverse"} or evidence.get("provider_access") is not False or evidence.get("activity_draft_write") is not False or evidence.get("canonical_write") is not False:
            _abort("activity_draft_input_invalid")
        if not isinstance(evidence.get("local_date"), str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", evidence["local_date"]) is None or not isinstance(evidence.get("valuation_currency"), str) or re.fullmatch(r"[A-Z]{3}", evidence["valuation_currency"]) is None:
            _abort("activity_draft_input_invalid")
        source_fx = evidence.get("valuation_method") in {"source_fiat_total_fx", "source_unit_price_fx"}
        if (
            Decimal(_decimal_text(evidence.get("fiat_total_decimal"))) <= 0
            or (source_fx and evidence.get("unit_price_decimal") is not None)
            or (not source_fx and Decimal(_decimal_text(evidence.get("unit_price_decimal"))) <= 0)
        ):
            _abort("activity_draft_input_invalid")
        candidate_fp = evidence.get("candidate_fingerprint")
        asset_fp = evidence.get("asset_evidence_fingerprint")
        source_fp = evidence.get("source_valuation_evidence_fingerprint")
        if (
            not isinstance(candidate_fp, str) or SHA.fullmatch(candidate_fp) is None
            or (source_fx and (asset_fp is not None or not isinstance(source_fp, str) or SHA.fullmatch(source_fp) is None))
            or (not source_fx and (not isinstance(asset_fp, str) or SHA.fullmatch(asset_fp) is None))
        ):
            _abort("activity_draft_input_invalid")
        if evidence.get("fx_evidence_fingerprint") is not None and (not isinstance(evidence["fx_evidence_fingerprint"], str) or SHA.fullmatch(evidence["fx_evidence_fingerprint"]) is None):
            _abort("activity_draft_input_invalid")
        if fx_timing.issubset(evidence):
            fx_date=evidence.get("fx_observation_date");fx_age=evidence.get("fx_rate_age_days");fx_basis=evidence.get("fx_selection_basis")
            if fx_basis not in {"identity","exact_date","prior_observation"} or fx_basis=="identity" and (fx_date is not None or fx_age is not None) or fx_basis!="identity" and (not isinstance(fx_date,str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}",fx_date) is None or not isinstance(fx_age,int) or isinstance(fx_age,bool) or fx_age<0 or fx_age>3):
                _abort("activity_draft_input_invalid")
        result["confirmed_reward_valuation"] = dict(evidence)
    return result


def _source_auxiliary_event_valid(auxiliary: Mapping[str, Any] | None, event: Mapping[str, Any]) -> bool:
    if auxiliary is None or auxiliary.get("unclassified_fee_resolution") == "not_present":
        return True
    resolution = auxiliary["unclassified_fee_resolution"]
    fee = auxiliary["unclassified_fee_decimal"]
    if resolution == "unresolved":
        return "monetary_fee_decimal" not in event and "asset_fee_quantity_decimal" not in event
    if resolution == "monetary_fee":
        return event.get("monetary_fee_decimal") == fee and "asset_fee_quantity_decimal" in event and event["asset_fee_quantity_decimal"] is None
    if resolution == "asset_fee_quantity":
        return event.get("asset_fee_quantity_decimal") == fee and "monetary_fee_decimal" in event and event["monetary_fee_decimal"] is None
    if resolution == "zero_no_fee":
        return all(field in event and event[field] is None for field in ("monetary_fee_decimal", "asset_fee_quantity_decimal"))
    return False


def _validation_input(draft: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    value = {
        "portfolio_id": draft["portfolio_id"],
        "action_type": draft["action_type"],
        "predecessor_event_ref": draft["predecessor_event_ref"],
        "event": dict(event),
    }
    if "source_auxiliary" in draft and draft.get("source_auxiliary") is not None:
        value["source_auxiliary"] = draft["source_auxiliary"]
    return value


def _seal(draft: dict[str, Any]) -> dict[str, Any]:
    body = dict(draft)
    body.pop("draft_fingerprint", None)
    body["draft_fingerprint"] = _fingerprint(body)
    return body


def _draft_path(area: Path, draft_ref: str) -> Path:
    if not isinstance(draft_ref, str) or DRAFT_REF.fullmatch(draft_ref) is None:
        _abort("activity_draft_input_invalid")
    drafts = _directory(area / DRAFTS_NAME, create=True)
    return drafts / (draft_ref + ".json")


def _validate_stored_draft(value: Any, context: DesktopProductAssetActivityContextV1) -> dict[str, Any]:
    if not isinstance(value, dict):
        _abort("activity_draft_storage_invalid")
    stored_keys = frozenset(value)
    if stored_keys not in {LEGACY_DRAFT_KEYS, DRAFT_KEYS}:
        _abort("activity_draft_storage_invalid")
    body = dict(value)
    fingerprint = body.pop("draft_fingerprint", None)
    try:
        event = _safe_event(value.get("event"))
        source_binding = None if "source_binding" not in value or value.get("source_binding") is None else _source_binding(value["source_binding"], context)
        source_auxiliary = None if "source_auxiliary" not in value else _source_auxiliary(value.get("source_auxiliary"), event)
        created = _utc(value.get("created_at_utc"))
        updated = _utc(value.get("updated_at_utc"))
        validated_at = None if value.get("validated_at_utc") is None else _utc(value["validated_at_utc"])
        committed_at = None if value.get("committed_at_utc") is None else _utc(value["committed_at_utc"])
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_storage_invalid")
    action = value.get("action_type")
    predecessor = value.get("predecessor_event_ref")
    validation = value.get("validation")
    if (
        value.get("activity_draft_version") not in (1, 2)
        or (value.get("activity_draft_version") == 2) != isinstance(predecessor, list)
        or (isinstance(predecessor, list) and predecessor != sorted(predecessor, key=str))
        or DRAFT_REF.fullmatch(str(value.get("draft_ref", ""))) is None
        or value.get("context_fingerprint") != _context_fingerprint(context)
        or REFERENCE.fullmatch(str(value.get("portfolio_id", ""))) is None
        or value.get("origin_type") not in ORIGIN_TYPES
        or action not in ACTION_TYPES
        or (value.get("origin_type") == "correction") != (action in {"correct", "void"})
        or (action == "create" and predecessor is not None)
        or (action in {"correct", "void"} and not _valid_correction_predecessor(action, predecessor))
        or (action == "void" and event)
        or (action != "void" and REFERENCE.fullmatch(str(event.get("event_ref", ""))) is None)
        or (source_binding is None) != (source_auxiliary is None)
        or not _source_auxiliary_event_valid(source_auxiliary, event)
        or (source_binding is not None and (
            value.get("origin_type") != "tolerant_csv"
            or action != "create"
            or event.get("event_ref") != _bound_event_ref(source_binding)
        ))
        or value.get("draft_state") not in DRAFT_STATES
        or value.get("validation_status") not in VALIDATION_STATUSES
        or isinstance(value.get("revision"), bool)
        or not isinstance(value.get("revision"), int)
        or value["revision"] < 1
        or not created <= updated
        or (validated_at is not None and not created <= validated_at <= updated)
        or (committed_at is not None and not created <= committed_at <= updated)
        or fingerprint != _fingerprint(body)
        or not (value.get("domain_result") is None or isinstance(value.get("domain_result"), Mapping))
    ):
        _abort("activity_draft_storage_invalid")
    if validation is None:
        if value["validation_status"] != "not_validated" or validated_at is not None or value["draft_state"] != "editing":
            _abort("activity_draft_storage_invalid")
    else:
        if not isinstance(validation, Mapping) or set(validation) != VALIDATION_KEYS:
            _abort("activity_draft_storage_invalid")
        validation_body = dict(validation)
        validation_fingerprint = validation_body.pop("validation_fingerprint", None)
        missing = validation.get("missing_fields")
        issues = validation.get("issue_codes")
        expected_input = _fingerprint(_validation_input(value, event))
        if (
            validation.get("activity_draft_validation_version") != 1
            or validation.get("validator_id") != "desktop_activity_draft_shared_v1"
            or validation.get("draft_revision") != value["revision"]
            or validation.get("input_fingerprint") != expected_input
            or validation.get("validated_at_utc") != validated_at
            or not isinstance(missing, list)
            or missing != sorted(set(missing))
            or any(key not in DRAFT_INPUT_FIELDS for key in missing)
            or not isinstance(issues, list)
            or issues != list(dict.fromkeys(issues))
            or any(code not in ISSUE_CODES for code in issues)
            or validation.get("status") != value["validation_status"]
            or validation_fingerprint != _fingerprint(validation_body)
        ):
            _abort("activity_draft_storage_invalid")
        status = validation["status"]
        if status == "needs_input":
            valid_shape = bool(missing) and issues == ["activity_draft_fields_missing"] and validation.get("plan_kind") is None and validation.get("expected_preview_fingerprint") is None and validation.get("domain_public_preview") is None and validation.get("trusted_preview") is None and value["draft_state"] == "editing"
        elif status == "blocked":
            valid_shape = not missing and issues == ["activity_draft_domain_invalid"] and validation.get("plan_kind") is None and validation.get("expected_preview_fingerprint") is None and validation.get("domain_public_preview") is None and validation.get("trusted_preview") is None and value["draft_state"] == "validated_blocked"
        elif status == "ready":
            expected_plan = "native_create" if action == "create" else "immutable_correction"
            public_shape = validation.get("domain_public_preview")
            valid_shape = not missing and not issues and validation.get("plan_kind") == expected_plan and SHA.fullmatch(str(validation.get("expected_preview_fingerprint", ""))) is not None and (public_shape is None if action == "create" else isinstance(public_shape, Mapping)) and isinstance(validation.get("trusted_preview"), Mapping) and value["draft_state"] in {"validated_ready", "applying", "committed"}
        else:
            valid_shape = False
        if not valid_shape:
            _abort("activity_draft_storage_invalid")
    if value["draft_state"] == "committed":
        if committed_at is None or not isinstance(value.get("domain_result"), Mapping):
            _abort("activity_draft_storage_invalid")
    elif committed_at is not None or value.get("domain_result") is not None:
        _abort("activity_draft_storage_invalid")
    return value


def _read(area: Path, context: DesktopProductAssetActivityContextV1, draft_ref: str) -> dict[str, Any]:
    if not isinstance(draft_ref, str) or DRAFT_REF.fullmatch(draft_ref) is None:
        _abort("activity_draft_input_invalid")
    drafts_path = area / DRAFTS_NAME
    if not drafts_path.exists():
        _abort("activity_draft_not_found")
    path = _directory(drafts_path) / (draft_ref + ".json")
    if not path.exists():
        _abort("activity_draft_not_found")
    path = _file(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _abort("activity_draft_storage_invalid")
    if raw != _canonical(value) + b"\n":
        _abort("activity_draft_storage_invalid")
    return _validate_stored_draft(value, context)


def _persist(area: Path, draft: dict[str, Any], *, create: bool = False) -> dict[str, Any]:
    sealed = _seal(draft)
    path = _draft_path(area, sealed["draft_ref"])
    content = _canonical(sealed) + b"\n"
    if create:
        _write_new(path, content)
    else:
        _file(path)
        _replace(path, content)
    return sealed


def _supersession_tombstone(value: Any) -> dict[str, Any]:
    expected = {
        "activity_draft_tombstone_version", "draft_ref", "draft_fingerprint",
        "source_fingerprint", "replacement_source_fingerprint",
        "supersession_command_fingerprint", "superseded_at_utc",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        _abort("activity_draft_storage_invalid")
    result = dict(value)
    if (
        result.get("activity_draft_tombstone_version") != 1
        or DRAFT_REF.fullmatch(str(result.get("draft_ref", ""))) is None
        or SHA.fullmatch(str(result.get("draft_fingerprint", ""))) is None
        or SHA.fullmatch(str(result.get("source_fingerprint", ""))) is None
        or SHA.fullmatch(str(result.get("replacement_source_fingerprint", ""))) is None
        or result["source_fingerprint"] == result["replacement_source_fingerprint"]
        or SHA.fullmatch(str(result.get("supersession_command_fingerprint", ""))) is None
    ):
        _abort("activity_draft_storage_invalid")
    try:
        _utc(result.get("superseded_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_storage_invalid")
    return result


def _supersession_command(value: Any) -> dict[str, Any]:
    expected = {
        "activity_draft_source_supersession_command_version", "context_fingerprint",
        "source_fingerprint", "replacement_source_fingerprint", "draft_count",
        "draft_set_fingerprint", "plan_fingerprint", "confirmation_fingerprint",
        "confirmed_at_utc", "superseded_at_utc", "command_fingerprint",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        _abort("activity_draft_storage_invalid")
    body = dict(value)
    fingerprint = body.pop("command_fingerprint", None)
    if (
        body.get("activity_draft_source_supersession_command_version") not in {1, 2}
        or SHA.fullmatch(str(body.get("context_fingerprint", ""))) is None
        or SHA.fullmatch(str(body.get("source_fingerprint", ""))) is None
        or SHA.fullmatch(str(body.get("replacement_source_fingerprint", ""))) is None
        or body["source_fingerprint"] == body["replacement_source_fingerprint"]
        or isinstance(body.get("draft_count"), bool)
        or not isinstance(body.get("draft_count"), int)
        or body["draft_count"] < 1
        or SHA.fullmatch(str(body.get("draft_set_fingerprint", ""))) is None
        or SHA.fullmatch(str(body.get("plan_fingerprint", ""))) is None
        or SHA.fullmatch(str(body.get("confirmation_fingerprint", ""))) is None
        or fingerprint != _fingerprint(body)
    ):
        _abort("activity_draft_storage_invalid")
    try:
        confirmed = _utc(body.get("confirmed_at_utc"))
        superseded = _utc(body.get("superseded_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_storage_invalid")
    if confirmed > superseded:
        _abort("activity_draft_storage_invalid")
    return dict(value)


def _validate_supersession_generation(
    value: Any, context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    expected = {
        "activity_draft_supersession_generation_version", "generation_ref",
        "predecessor_generation_ref", "context_fingerprint", "created_at_utc",
        "commands", "tombstones", "boundaries", "generation_fingerprint",
    }
    if not isinstance(value, dict) or set(value) != expected:
        _abort("activity_draft_storage_invalid")
    body = dict(value)
    fingerprint = body.pop("generation_fingerprint", None)
    predecessor = body.get("predecessor_generation_ref")
    commands_value = body.get("commands")
    tombstones_value = body.get("tombstones")
    boundaries = body.get("boundaries")
    if (
        body.get("activity_draft_supersession_generation_version") != 1
        or SUPERSESSION_GENERATION_REF.fullmatch(str(body.get("generation_ref", ""))) is None
        or not (predecessor is None or SUPERSESSION_GENERATION_REF.fullmatch(str(predecessor)) is not None)
        or body.get("context_fingerprint") != _context_fingerprint(context)
        or not isinstance(commands_value, list)
        or not commands_value
        or not isinstance(tombstones_value, list)
        or not tombstones_value
        or boundaries != {
            "draft_files_rewritten": 0, "schema201_write": False,
            "schema401_write": False, "cash_posting_count": 0,
            "provider_access": False, "network_access": False,
            "automatic_retry": False,
        }
        or fingerprint != _fingerprint(body)
    ):
        _abort("activity_draft_storage_invalid")
    try:
        created = _utc(body.get("created_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_storage_invalid")
    commands = [_supersession_command(item) for item in commands_value]
    tombstones = [_supersession_tombstone(item) for item in tombstones_value]
    command_fingerprints = [item["command_fingerprint"] for item in commands]
    if (
        len(set(command_fingerprints)) != len(command_fingerprints)
        or any(item["context_fingerprint"] != _context_fingerprint(context) for item in commands)
        or [item["draft_ref"] for item in tombstones] != sorted(item["draft_ref"] for item in tombstones)
        or len({item["draft_ref"] for item in tombstones}) != len(tombstones)
        or any(item["supersession_command_fingerprint"] not in command_fingerprints for item in tombstones)
        or created != commands[-1]["superseded_at_utc"]
    ):
        _abort("activity_draft_storage_invalid")
    for command in commands:
        selected = [
            {"draft_ref": item["draft_ref"], "draft_fingerprint": item["draft_fingerprint"]}
            for item in tombstones
            if item["supersession_command_fingerprint"] == command["command_fingerprint"]
        ]
        version = command["activity_draft_source_supersession_command_version"]
        if (
            (version == 1 and (
                len(selected) != command["draft_count"]
                or _fingerprint(selected) != command["draft_set_fingerprint"]
            ))
            or (version == 2 and not (0 < len(selected) < command["draft_count"]))
            or any(
                item["source_fingerprint"] != command["source_fingerprint"]
                or item["replacement_source_fingerprint"] != command["replacement_source_fingerprint"]
                or item["superseded_at_utc"] != command["superseded_at_utc"]
                for item in tombstones
                if item["supersession_command_fingerprint"] == command["command_fingerprint"]
            )
        ):
            _abort("activity_draft_storage_invalid")
    expected_ref = "adg_" + _fingerprint({
        "predecessor_generation_ref": predecessor,
        "command_fingerprint": commands[-1]["command_fingerprint"],
    })[:32]
    if body["generation_ref"] != expected_ref:
        _abort("activity_draft_storage_invalid")
    return value


def _validate_mixed_source_retirement_generation_evidence(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    generation: Mapping[str, Any],
    *,
    require_barrier: bool = True,
) -> None:
    mixed_commands = [
        item for item in generation["commands"]
        if item["activity_draft_source_supersession_command_version"] == 2
    ]
    if not mixed_commands:
        return
    if require_barrier:
        _validate_mixed_source_retirement_barrier(area)
    attempts_path = area / SUPERSESSION_ATTEMPTS_NAME
    if not attempts_path.exists():
        _abort("activity_draft_storage_invalid")
    attempts = [
        _read_supersession_attempt(path, context)
        for path in sorted(_strict_owner_directory(attempts_path).glob("ads_*.json"))
    ]
    all_tombstone_refs = {item["draft_ref"] for item in generation["tombstones"]}
    for command in mixed_commands:
        matches = [
            item for item in attempts
            if item["plan_fingerprint"] == command["plan_fingerprint"]
            and item["confirmation_fingerprint"] == command["confirmation_fingerprint"]
        ]
        if len(matches) != 1:
            _abort("activity_draft_storage_invalid")
        attempt = matches[0]
        preview = _validate_trusted_supersession_preview(attempt["trusted_preview"], context)
        confirmation = attempt["confirmation"]
        if (
            preview["activity_draft_source_supersession_preview_version"] != 2
            or confirmation.get("activity_draft_source_supersession_confirmation_version") != 2
            or attempt["activity_draft_source_supersession_attempt_version"] != 2
            or attempt["committed_at_utc"] != command["superseded_at_utc"]
            or preview["source_fingerprint"] != command["source_fingerprint"]
            or preview["replacement_source_fingerprint"] != command["replacement_source_fingerprint"]
            or preview["expected_draft_count"] != command["draft_count"]
            or preview["draft_set_fingerprint"] != command["draft_set_fingerprint"]
        ):
            _abort("activity_draft_storage_invalid")
        open_drafts = [
            {"draft_ref": item["draft_ref"], "draft_fingerprint": item["draft_fingerprint"]}
            for item in preview["selected_drafts"]
            if item["draft_state"] != "committed"
        ]
        committed_drafts = [
            item for item in preview["selected_drafts"]
            if item["draft_state"] == "committed"
        ]
        command_tombstones = [
            {"draft_ref": item["draft_ref"], "draft_fingerprint": item["draft_fingerprint"]}
            for item in generation["tombstones"]
            if item["supersession_command_fingerprint"] == command["command_fingerprint"]
        ]
        if command_tombstones != open_drafts or not committed_drafts:
            _abort("activity_draft_storage_invalid")
        for item in committed_drafts:
            if item["draft_ref"] in all_tombstone_refs:
                _abort("activity_draft_storage_invalid")
            _strict_owner_file(area / DRAFTS_NAME / (item["draft_ref"] + ".json"))
            draft = _read(area, context, item["draft_ref"])
            binding = draft.get("source_binding")
            if (
                draft["draft_state"] != "committed"
                or draft["draft_fingerprint"] != item["draft_fingerprint"]
                or not isinstance(binding, Mapping)
                or binding.get("source_fingerprint") != command["source_fingerprint"]
                or binding.get("source_row_ordinal") != item["source_row_ordinal"]
                or binding.get("binding_fingerprint") != item["binding_fingerprint"]
            ):
                _abort("activity_draft_storage_invalid")


def _read_supersession_generation(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    generation_ref: str,
    *,
    require_mixed_barrier: bool = True,
) -> dict[str, Any]:
    if not isinstance(generation_ref, str) or SUPERSESSION_GENERATION_REF.fullmatch(generation_ref) is None:
        _abort("activity_draft_storage_invalid")
    generations_path = area / SUPERSESSION_GENERATIONS_NAME
    if not generations_path.exists():
        _abort("activity_draft_storage_invalid")
    generations = _strict_owner_directory(generations_path)
    path = generations / (generation_ref + ".json")
    if not path.exists():
        _abort("activity_draft_storage_invalid")
    value = _read_owner_json(path)
    generation = _validate_supersession_generation(value, context)
    if generation["generation_ref"] != generation_ref:
        _abort("activity_draft_storage_invalid")
    _validate_mixed_source_retirement_generation_evidence(
        area, context, generation, require_barrier=require_mixed_barrier,
    )
    return generation


def _active_supersession_generation(
    area: Path, context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any] | None:
    pointer_path = area / SUPERSESSION_ACTIVE_NAME
    if not pointer_path.exists():
        return None
    if not (area / LOCK_NAME).exists() or not (area / LOCK_NAME).is_dir():
        _abort("activity_draft_storage_invalid")
    _validate_writer_barrier(area)
    value = _read_owner_json(pointer_path)
    expected = {
        "activity_draft_supersession_active_version", "context_fingerprint",
        "generation_ref", "generation_fingerprint", "activated_at_utc",
        "pointer_fingerprint",
    }
    body = dict(value)
    fingerprint = body.pop("pointer_fingerprint", None)
    if (
        set(value) != expected
        or body.get("activity_draft_supersession_active_version") != 1
        or body.get("context_fingerprint") != _context_fingerprint(context)
        or SUPERSESSION_GENERATION_REF.fullmatch(str(body.get("generation_ref", ""))) is None
        or SHA.fullmatch(str(body.get("generation_fingerprint", ""))) is None
        or fingerprint != _fingerprint(body)
    ):
        _abort("activity_draft_storage_invalid")
    try:
        activated = _utc(body.get("activated_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_storage_invalid")
    generation = _read_supersession_generation(area, context, body["generation_ref"])
    if any(
        item["activity_draft_source_supersession_command_version"] == 2
        for item in generation["commands"]
    ):
        _validate_mixed_source_retirement_barrier(area)
    if (
        generation["generation_fingerprint"] != body["generation_fingerprint"]
        or activated < generation["created_at_utc"]
    ):
        _abort("activity_draft_storage_invalid")
    return generation


def _supersession_index(
    area: Path, context: DesktopProductAssetActivityContextV1,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any] | None]:
    generation = _active_supersession_generation(area, context)
    if generation is None:
        return {}, None
    return {item["draft_ref"]: item for item in generation["tombstones"]}, generation


def _supersession_for_draft(
    area: Path, context: DesktopProductAssetActivityContextV1, draft: Mapping[str, Any],
) -> dict[str, Any] | None:
    index, _ = _supersession_index(area, context)
    tombstone = index.get(draft["draft_ref"])
    if tombstone is not None:
        _strict_owner_file(area / DRAFTS_NAME / (draft["draft_ref"] + ".json"))
    if tombstone is not None and tombstone["draft_fingerprint"] != draft["draft_fingerprint"]:
        _abort("activity_draft_storage_invalid")
    return tombstone


def _ensure_draft_not_superseded(
    area: Path, context: DesktopProductAssetActivityContextV1, draft: Mapping[str, Any],
) -> None:
    _ensure_no_pending_supersession(area, context)
    if _supersession_for_draft(area, context, draft) is not None:
        _abort("activity_draft_source_superseded")


def _source_is_superseded(
    area: Path, context: DesktopProductAssetActivityContextV1, source_fingerprint: str,
) -> bool:
    _, generation = _supersession_index(area, context)
    return generation is not None and any(
        item["source_fingerprint"] == source_fingerprint
        for item in generation["commands"]
    )


def _validation_reset(draft: dict[str, Any]) -> None:
    draft.update(
        draft_state="editing",
        validation_status="not_validated",
        validation=None,
        validated_at_utc=None,
        committed_at_utc=None,
        domain_result=None,
    )


def _valuation_public(auxiliary: Mapping[str, Any], event: Mapping[str, Any]) -> dict[str, Any]:
    evidence = auxiliary.get("valuation_evidence")
    if not isinstance(evidence, Mapping):
        return {"origin": "not_recorded", "lifecycle": "not_recorded", "source_value_mode": "none", "price_currency": None}
    origin = evidence["valuation_origin"]
    if origin == "source_missing":
        complete = (
            event.get("basis_evidence_mode") in {"valuation_confirmed_as_basis", "provided_basis"}
            and (event.get("unit_price_decimal") is not None or event.get("gross_amount_decimal") is not None or event.get("provided_basis_decimal") is not None)
        )
        lifecycle = "market_evidence_complete" if complete and isinstance(auxiliary.get("confirmed_reward_valuation"), Mapping) else "owner_manual_complete" if complete else "valuation_pending"
    elif origin == "source_provided":
        complete = (
            event.get("basis_evidence_mode") in {"valuation_confirmed_as_basis", "provided_basis"}
            and (event.get("unit_price_decimal") is not None or event.get("gross_amount_decimal") is not None or event.get("provided_basis_decimal") is not None)
        )
        lifecycle = "market_evidence_complete" if complete and isinstance(auxiliary.get("confirmed_reward_valuation"), Mapping) else "source_provided" if complete else "valuation_pending"
    else:
        lifecycle = "not_applicable"
    return {
        "origin": origin, "lifecycle": lifecycle,
        "source_value_mode": evidence["source_value_mode"],
        "price_currency": evidence["price_currency"],
    }


def _public(
    draft: Mapping[str, Any], supersession: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validation = draft.get("validation") if isinstance(draft.get("validation"), Mapping) else {}
    event = draft.get("event") if isinstance(draft.get("event"), Mapping) else {}
    binding = draft.get("source_binding") if isinstance(draft.get("source_binding"), Mapping) else {}
    auxiliary = draft.get("source_auxiliary") if isinstance(draft.get("source_auxiliary"), Mapping) else {}
    fee_resolution = auxiliary.get("unclassified_fee_resolution", "not_present")
    summary_keys = (
        "event_type", "event_time_evidence", "local_date", "local_time", "time_zone",
        "original_acquired_time_evidence", "original_acquired_local_date",
        "original_acquired_local_time", "original_acquired_time_zone",
        "amount_input_mode", "basis_evidence_mode", "quantity_decimal",
        "eligible_quantity_decimal", "unit_price_decimal", "gross_amount_decimal",
        "monetary_fee_decimal", "asset_fee_quantity_decimal", "provided_basis_decimal",
        "movement_context_code",
    )
    effective_status = "superseded" if supersession is not None else draft["draft_state"]
    return {
        "activity_draft_public_version": draft["activity_draft_version"],
        **({"selected_event_count": len(draft["predecessor_event_ref"])} if draft["activity_draft_version"] == 2 else {}),
        "status": effective_status,
        "origin_type": draft["origin_type"],
        "action_type": draft["action_type"],
        "revision": draft["revision"],
        "validation_status": draft["validation_status"],
        "missing_fields": list(validation.get("missing_fields", [])),
        "issue_codes": list(validation.get("issue_codes", [])),
        "event_summary": {key: event.get(key) for key in summary_keys},
        "source_row_ordinal": binding.get("source_row_ordinal"),
        "source_row_key": binding.get("source_row_key"),
        "unclassified_fee_summary": {
            "status": fee_resolution,
            "decimal": auxiliary.get("unclassified_fee_decimal"),
        },
        "valuation_summary": _valuation_public(auxiliary, event),
        "can_resolve_unclassified_fee": supersession is None and fee_resolution == "unresolved" and draft["draft_state"] not in {"applying", "committed"},
        "can_confirm": supersession is None and (draft["draft_state"] == "validated_ready" or (draft["activity_draft_version"] == 2 and draft["draft_state"] == "applying")),
        "can_resume": supersession is None and draft["draft_state"] == "applying",
        "canonical_write": False,
        "schema201_canonical_write": False,
        "cash_posting_count": 0,
        "provider_access": False,
        "network_access": False,
        "path_exposed": False,
        "browser_internal_id_exposed": False,
        "fingerprint_exposed": False,
    }


def _valid_correction_predecessor(action: str, value: Any) -> bool:
    if isinstance(value, list):
        return (action == "void" and 2 <= len(value) <= 1000 and
                all(isinstance(ref, str) and ref.startswith("evt_") and REFERENCE.fullmatch(ref) for ref in value) and
                len(set(value)) == len(value))
    return isinstance(value, str) and REFERENCE.fullmatch(value) is not None


def create_desktop_activity_draft_v1(
    data_space_path: str | Path,
    context_value: Any,
    portfolio_id: str,
    origin_type: str,
    action_type: str,
    event_fields: Mapping[str, Any],
    created_at_utc: str,
    *,
    predecessor_event_ref: str | list[str] | None = None,
) -> dict[str, Any]:
    context = _context(context_value)
    created = _utc(created_at_utc)
    if (
        not isinstance(portfolio_id, str)
        or REFERENCE.fullmatch(portfolio_id) is None
        or origin_type not in ORIGIN_TYPES
        or action_type not in ACTION_TYPES
        or (action_type == "create" and predecessor_event_ref is not None)
        or (action_type in {"correct", "void"} and not _valid_correction_predecessor(action_type, predecessor_event_ref))
        or (origin_type == "correction") != (action_type in {"correct", "void"})
    ):
        _abort("activity_draft_input_invalid")
    if isinstance(predecessor_event_ref, list):
        predecessor_event_ref = sorted(predecessor_event_ref)
    event = _safe_event(event_fields)
    if action_type == "void" and event:
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        _ensure_no_pending_supersession(area, context)
        if isinstance(predecessor_event_ref, list) and (area / DRAFTS_NAME).exists():
            for path in _directory(area / DRAFTS_NAME).glob("adt_*.json"):
                pending = _read(area, context, path.stem)
                prior = pending.get("predecessor_event_ref")
                prior_refs = prior if isinstance(prior, list) else [prior]
                if pending["draft_state"] == "applying" and set(predecessor_event_ref).intersection(prior_refs):
                    _abort("activity_draft_state_conflict")
        draft_ref = "adt_" + secrets.token_hex(16)
        if action_type != "void" and "event_ref" not in event:
            event["event_ref"] = "evt_" + _fingerprint({
                "context_fingerprint": _context_fingerprint(context),
                "draft_ref": draft_ref,
            })[:32]
        draft = {
            "activity_draft_version": 2 if isinstance(predecessor_event_ref, list) else 1,
            "draft_ref": draft_ref,
            "context_fingerprint": _context_fingerprint(context),
            "portfolio_id": portfolio_id,
            "origin_type": origin_type,
            "action_type": action_type,
            "predecessor_event_ref": predecessor_event_ref,
            "event": event,
            "revision": 1,
            "draft_state": "editing",
            "validation_status": "not_validated",
            "validation": None,
            "created_at_utc": created,
            "updated_at_utc": created,
            "validated_at_utc": None,
            "committed_at_utc": None,
            "domain_result": None,
            "source_binding": None,
            "source_auxiliary": None,
        }
        stored = _persist(area, draft, create=True)
    return {"public_draft": _public(stored), "trusted_draft": stored}


def create_or_reuse_tolerant_csv_activity_draft_v1(
    data_space_path: str | Path,
    context_value: Any,
    portfolio_id: str,
    event_fields: Mapping[str, Any],
    source_binding_value: Mapping[str, Any],
    source_auxiliary_value: Mapping[str, Any],
    created_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    created = _utc(created_at_utc)
    if not isinstance(portfolio_id, str) or REFERENCE.fullmatch(portfolio_id) is None:
        _abort("activity_draft_input_invalid")
    event = _safe_event(event_fields)
    binding = _source_binding(
        source_binding_value, context, _source_mapping_fingerprint(portfolio_id, event),
    )
    event_ref = _bound_event_ref(binding)
    if "event_ref" in event and event["event_ref"] != event_ref:
        _abort("activity_draft_source_binding_conflict")
    event["event_ref"] = event_ref
    auxiliary = _source_auxiliary(source_auxiliary_value, event)
    if auxiliary is None or auxiliary["unclassified_fee_resolution"] not in {"not_present", "unresolved"}:
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        _ensure_no_pending_supersession(area, context)
        if _source_is_superseded(area, context, binding["source_fingerprint"]):
            _abort("activity_draft_source_superseded")
        drafts = _directory(area / DRAFTS_NAME, create=True)
        matches: list[dict[str, Any]] = []
        for path in sorted(drafts.glob("adt_*.json")):
            draft = _read(area, context, path.stem)
            stored_binding = draft.get("source_binding")
            binding_match = (
                isinstance(stored_binding, Mapping)
                and stored_binding.get("binding_fingerprint") == binding["binding_fingerprint"]
            )
            if binding_match or draft.get("event", {}).get("event_ref") == event_ref:
                matches.append(draft)
        for candidate in matches:
            stored_binding = candidate.get("source_binding")
            stored_auxiliary = candidate.get("source_auxiliary")
            if (
                candidate.get("origin_type") != "tolerant_csv"
                or candidate.get("action_type") != "create"
                or candidate.get("portfolio_id") != portfolio_id
                or (isinstance(stored_binding, Mapping) and stored_binding != binding)
                or (
                    stored_binding is None
                    and candidate.get("draft_state") not in {"applying", "committed"}
                    and any(
                        candidate.get("event", {}).get(field) != event.get(field)
                        for field in ("account_ref", "related_account_ref", "asset_ref", "source_asset_ref")
                    )
                )
                or (
                    isinstance(stored_auxiliary, Mapping)
                    and (
                        stored_auxiliary.get("unclassified_fee_decimal")
                        != auxiliary.get("unclassified_fee_decimal")
                        or auxiliary.get("fifo_order_evidence") is not None
                        and stored_auxiliary.get("fifo_order_evidence")
                        != auxiliary.get("fifo_order_evidence")
                        or stored_auxiliary.get("valuation_evidence")
                        != auxiliary.get("valuation_evidence")
                    )
                )
            ):
                _abort("activity_draft_source_binding_conflict")
        if matches:
            priority = {
                "committed": 0, "applying": 1, "validated_ready": 2,
                "validated_blocked": 3, "editing": 4,
            }
            draft = dict(sorted(
                matches,
                key=lambda item: (
                    priority[item["draft_state"]], item["created_at_utc"], item["draft_ref"],
                ),
            )[0])
            if "source_binding" not in draft or draft.get("source_binding") is None:
                if draft["draft_state"] not in {"applying", "committed"}:
                    if created < draft["updated_at_utc"]:
                        _abort("activity_draft_input_invalid")
                    draft["source_binding"] = binding
                    draft["source_auxiliary"] = auxiliary
                    if draft.get("validation") is not None:
                        draft["revision"] += 1
                        draft["updated_at_utc"] = created
                        _validation_reset(draft)
                    draft = _persist(area, draft)
            return {
                "public_draft": _public(draft), "trusted_draft": draft,
                "created_new": False, "reused_existing": True,
            }
        draft_ref = "adt_" + secrets.token_hex(16)
        draft = {
            "activity_draft_version": 1,
            "draft_ref": draft_ref,
            "context_fingerprint": _context_fingerprint(context),
            "portfolio_id": portfolio_id,
            "origin_type": "tolerant_csv",
            "action_type": "create",
            "predecessor_event_ref": None,
            "event": event,
            "revision": 1,
            "draft_state": "editing",
            "validation_status": "not_validated",
            "validation": None,
            "created_at_utc": created,
            "updated_at_utc": created,
            "validated_at_utc": None,
            "committed_at_utc": None,
            "domain_result": None,
            "source_binding": binding,
            "source_auxiliary": auxiliary,
        }
        stored = _persist(area, draft, create=True)
    return {
        "public_draft": _public(stored), "trusted_draft": stored,
        "created_new": True, "reused_existing": False,
    }


def resolve_desktop_activity_draft_unclassified_fee_v1(
    data_space_path: str | Path,
    context_value: Any,
    draft_ref: str,
    expected_revision: int,
    resolution: str,
    updated_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    updated = _utc(updated_at_utc)
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or resolution not in {"monetary_fee", "asset_fee_quantity", "zero_no_fee"}
    ):
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref))
        _ensure_draft_not_superseded(area, context, draft)
        if draft["revision"] != expected_revision:
            _abort("activity_draft_revision_conflict")
        if updated < draft["updated_at_utc"]:
            _abort("activity_draft_input_invalid")
        if draft["draft_state"] in {"applying", "committed"} or draft["action_type"] == "void":
            _abort("activity_draft_state_conflict")
        auxiliary = _source_auxiliary(draft.get("source_auxiliary"), draft["event"])
        if auxiliary is None or auxiliary["unclassified_fee_decimal"] is None:
            _abort("activity_draft_input_invalid")
        fee = auxiliary["unclassified_fee_decimal"]
        if resolution == "zero_no_fee" and Decimal(fee) != 0:
            _abort("activity_draft_input_invalid")
        event = dict(draft["event"])
        if resolution == "monetary_fee":
            event["monetary_fee_decimal"] = fee
            event["asset_fee_quantity_decimal"] = None
        elif resolution == "asset_fee_quantity":
            event["monetary_fee_decimal"] = None
            event["asset_fee_quantity_decimal"] = fee
        else:
            event["monetary_fee_decimal"] = None
            event["asset_fee_quantity_decimal"] = None
        auxiliary["unclassified_fee_resolution"] = resolution
        draft["event"] = event
        draft["source_auxiliary"] = auxiliary
        draft["revision"] += 1
        draft["updated_at_utc"] = updated
        _validation_reset(draft)
        stored = _persist(area, draft)
    return {"public_draft": _public(stored), "trusted_draft": stored}


def bind_desktop_activity_draft_fifo_order_evidence_v1(
    data_space_path: str | Path,
    context_value: Any,
    draft_ref: str,
    expected_revision: int,
    fifo_order_evidence_value: Mapping[str, Any],
    updated_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    updated = _utc(updated_at_utc)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref))
        _ensure_draft_not_superseded(area, context, draft)
        if draft["revision"] != expected_revision:
            _abort("activity_draft_revision_conflict")
        if updated < draft["updated_at_utc"]:
            _abort("activity_draft_input_invalid")
        if (
            draft["draft_state"] in {"applying", "committed"}
            or draft["origin_type"] != "tolerant_csv"
            or draft["action_type"] != "create"
            or not isinstance(draft.get("source_binding"), Mapping)
        ):
            _abort("activity_draft_state_conflict")
        try:
            evidence = _draft_fifo_order_evidence(
                fifo_order_evidence_value, draft["event"]
            )
        except DesktopProductAssetActivityV1Error:
            _abort("activity_draft_input_invalid")
        auxiliary = _source_auxiliary(draft.get("source_auxiliary"), draft["event"])
        if auxiliary is None:
            _abort("activity_draft_input_invalid")
        existing = auxiliary.get("fifo_order_evidence")
        if existing is not None:
            if existing != evidence:
                _abort("activity_draft_source_binding_conflict")
            return {"public_draft": _public(draft), "trusted_draft": draft}
        auxiliary["fifo_order_evidence"] = evidence
        draft["source_auxiliary"] = auxiliary
        draft["revision"] += 1
        draft["updated_at_utc"] = updated
        _validation_reset(draft)
        stored = _persist(area, draft)
    return {"public_draft": _public(stored), "trusted_draft": stored}


def bind_desktop_activity_draft_fifo_order_group_v1(
    data_space_path: str | Path, context_value: Any, draft_ref: str,
    expected_revision: int, peer_draft_refs: Sequence[str], updated_at_utc: str,
) -> dict[str, Any]:
    """Bind one owner-confirmed same-source order group without exposing identifiers."""
    context = _context(context_value)
    updated = _utc(updated_at_utc)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or not isinstance(peer_draft_refs, Sequence) or isinstance(peer_draft_refs, (str, bytes)) or not peer_draft_refs or any(not isinstance(ref, str) for ref in peer_draft_refs) or len(set(peer_draft_refs)) != len(peer_draft_refs) or draft_ref in peer_draft_refs:
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref))
        peers = [dict(_read(area, context, ref)) for ref in peer_draft_refs]
        _ensure_draft_not_superseded(area, context, draft)
        for peer in peers:
            _ensure_draft_not_superseded(area, context, peer)
        if draft["revision"] != expected_revision or updated < draft["updated_at_utc"]:
            _abort("activity_draft_revision_conflict")
        if draft["draft_state"] in {"applying", "committed"} or draft["action_type"] != "create" or any(peer["draft_state"] != "committed" or peer["action_type"] != "create" for peer in peers):
            _abort("activity_draft_state_conflict")
        source = draft.get("source_binding")
        peer_sources = [peer.get("source_binding") for peer in peers]
        if not isinstance(source, Mapping) or any(not isinstance(item, Mapping) for item in peer_sources):
            _abort("activity_draft_source_binding_conflict")
        all_sources = [*peer_sources, source]
        if len({item.get("source_fingerprint") for item in all_sources}) != 1 or len({item.get("source_row_ordinal") for item in all_sources}) != len(all_sources):
            _abort("activity_draft_source_binding_conflict")
        event = draft["event"]
        peer_events = [peer["event"] for peer in peers]
        collision_key = lambda item: (item.get("asset_ref"), item.get("local_date"), item.get("effective_at_utc"))
        if any(collision_key(event) != collision_key(item) or item.get("event_time_evidence") != "exact" for item in peer_events) or event.get("event_time_evidence") != "exact":
            _abort("activity_draft_source_binding_conflict")
        try:
            from workers.reference.semantic_realized_fifo_v2 import build_owner_confirmed_source_row_order_evidence_v1
            events = [*peer_events, event]
            bindings = [*peer_sources, source]
            evidence = build_owner_confirmed_source_row_order_evidence_v1(
                events,
                {item["event_ref"]: {"source_file_fingerprint": binding["source_fingerprint"], "source_row_ordinal": binding["source_row_ordinal"]} for item, binding in zip(events, bindings)},
            )
            evidence = _draft_fifo_order_evidence(evidence, event)
        except Exception:
            _abort("activity_draft_input_invalid")
        auxiliary = _source_auxiliary(draft.get("source_auxiliary"), event)
        if auxiliary is None:
            _abort("activity_draft_input_invalid")
        existing = auxiliary.get("fifo_order_evidence")
        if existing is not None:
            if existing != evidence:
                _abort("activity_draft_source_binding_conflict")
            return {"public_draft": _public(draft), "trusted_draft": draft}
        auxiliary["fifo_order_evidence"] = evidence
        draft["source_auxiliary"] = auxiliary
        draft["revision"] += 1
        draft["updated_at_utc"] = updated
        _validation_reset(draft)
        stored = _persist(area, draft)
    return {"public_draft": _public(stored), "trusted_draft": stored}


def apply_confirmed_reward_valuation_evidence_v1(
    data_space_path: str | Path, context_value: Any, draft_ref: str,
    expected_revision: int, evidence_value: Mapping[str, Any], updated_at_utc: str,
) -> dict[str, Any]:
    """Persist complete confirmed evidence and its exact unit or gross value in one Draft revision."""
    context = _context(context_value); updated = _utc(updated_at_utc); area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref)); _ensure_draft_not_superseded(area, context, draft)
        if draft["revision"] != expected_revision:
            _abort("activity_draft_revision_conflict")
        if updated < draft["updated_at_utc"] or draft["draft_state"] in {"applying", "committed"} or draft["action_type"] == "void":
            _abort("activity_draft_state_conflict")
        event = dict(draft["event"]); auxiliary = _source_auxiliary(draft.get("source_auxiliary"), event)
        valuation = None if auxiliary is None else auxiliary.get("valuation_evidence")
        source_fx = evidence_value.get("valuation_method") in {"source_fiat_total_fx", "source_unit_price_fx"}
        source_mode = "fiat_total" if evidence_value.get("valuation_method") == "source_fiat_total_fx" else "unit_price"
        source_fp = _fingerprint({
            "valuation_evidence": dict(valuation) if isinstance(valuation, Mapping) else None,
            "source_binding_fingerprint": draft["source_binding"]["binding_fingerprint"],
        })
        common_invalid = (
            event.get("event_type") != "reward" or not isinstance(valuation, Mapping)
            or auxiliary.get("confirmed_reward_valuation") is not None
            or event.get("local_date") != evidence_value.get("local_date")
        )
        source_invalid = source_fx and (
            valuation.get("valuation_origin") != "source_provided"
            or valuation.get("source_value_mode") != source_mode
            or valuation.get("price_currency") == evidence_value.get("valuation_currency")
            or event.get("basis_evidence_mode") != "basis_missing"
            or source_fp != evidence_value.get("source_valuation_evidence_fingerprint")
        )
        market_invalid = not source_fx and (
            valuation.get("valuation_origin") != "source_missing"
            or valuation.get("price_currency") != evidence_value.get("valuation_currency")
        )
        if common_invalid or source_invalid or market_invalid:
            _abort("activity_draft_input_invalid")
        candidate_auxiliary = dict(auxiliary); candidate_auxiliary["confirmed_reward_valuation"] = dict(evidence_value)
        candidate_auxiliary = _source_auxiliary(candidate_auxiliary, event)
        gross = Decimal(_decimal_text(event.get("quantity_decimal")))
        fee = Decimal(_decimal_text(event.get("asset_fee_quantity_decimal", "0") or "0"))
        eligible = gross - fee
        total = Decimal(_decimal_text(evidence_value.get("fiat_total_decimal")))
        if source_fx:
            if eligible <= 0 or total <= 0:
                _abort("activity_draft_input_invalid")
            event.update(
                amount_input_mode="gross_total",
                gross_amount_decimal=_decimal_text(evidence_value["fiat_total_decimal"]),
                basis_evidence_mode="valuation_confirmed_as_basis",
                unit_price_decimal=None, provided_basis_decimal=None,
            )
        else:
            unit = Decimal(_decimal_text(evidence_value.get("unit_price_decimal")))
            if eligible <= 0 or Fraction(eligible) * Fraction(unit) != Fraction(total):
                _abort("activity_draft_input_invalid")
            event.update(amount_input_mode="quantity_unit_price", basis_evidence_mode="valuation_confirmed_as_basis", unit_price_decimal=_decimal_text(evidence_value["unit_price_decimal"]), provided_basis_decimal=None)
        draft["event"] = _safe_event(event); draft["source_auxiliary"] = candidate_auxiliary
        draft["revision"] += 1; draft["updated_at_utc"] = updated; _validation_reset(draft)
        stored = _persist(area, draft)
    return {"public_draft": _public(stored), "trusted_draft": stored}


def update_desktop_activity_draft_v1(
    data_space_path: str | Path,
    context_value: Any,
    draft_ref: str,
    expected_revision: int,
    event_patch: Mapping[str, Any],
    remove_fields: list[str] | tuple[str, ...],
    updated_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    updated = _utc(updated_at_utc)
    patch = _safe_event(event_patch)
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or not isinstance(remove_fields, (list, tuple))
        or any(not isinstance(key, str) or key not in NATIVE_EVENT_KEYS for key in remove_fields)
        or "event_ref" in remove_fields
        or len(remove_fields) != len(set(remove_fields))
        or set(patch) & set(remove_fields)
    ):
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref))
        _ensure_draft_not_superseded(area, context, draft)
        if draft["revision"] != expected_revision:
            _abort("activity_draft_revision_conflict")
        if updated < draft["updated_at_utc"]:
            _abort("activity_draft_input_invalid")
        if draft["draft_state"] in {"applying", "committed"} or draft["action_type"] == "void":
            _abort("activity_draft_state_conflict")
        auxiliary = draft.get("source_auxiliary")
        if (
            isinstance(auxiliary, Mapping)
            and auxiliary.get("unclassified_fee_resolution") != "not_present"
            and (set(patch) | set(remove_fields)) & {"monetary_fee_decimal", "asset_fee_quantity_decimal"}
        ):
            _abort("activity_draft_input_invalid")
        event = dict(draft["event"])
        event.update(patch)
        for key in remove_fields:
            if key != "event_ref":
                event.pop(key, None)
        draft["event"] = event
        draft["revision"] += 1
        draft["updated_at_utc"] = updated
        _validation_reset(draft)
        stored = _persist(area, draft)
    return {"public_draft": _public(stored), "trusted_draft": stored}


def _booked_seconds(data_space_path: str | Path, context: DesktopProductAssetActivityContextV1) -> dict[str, dict[str, list[tuple[str, str]]]]:
    """Je Asset und Zeitpunkt (UTC, auf die Sekunde) die gebuchten Vorgaenge als (Konto, Menge) - nur gelesen."""
    binding = read_desktop_product_asset_activity_binding_v1(data_space_path, context)
    if binding["status"] == "absent" or not binding.get("ledger_path"):
        return {}
    taken: dict[str, dict[str, list[tuple[str, str]]]] = {}
    try:
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        try:
            for asset_id, moment, account_id, quantity in connection.execute(
                    "SELECT asset_id, effective_at_utc, account_id, quantity_decimal FROM current_asset_activity_event WHERE effective_at_utc IS NOT NULL"):
                taken.setdefault(asset_id, {}).setdefault(moment, []).append((account_id, quantity))
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("activity_draft_storage_invalid")
    return taken


def shift_desktop_activity_draft_past_booked_second_v1(
    data_space_path: str | Path,
    context_value: Any,
    draft_ref: str,
    expected_revision: int,
    updated_at_utc: str,
) -> dict[str, Any]:
    """Ein Reward-Entwurf, dessen Coin in derselben Sekunde schon eine gebuchte Buchung hat, rueckt um ganze Sekunden nach hinten
    (rc.323). Kraken bucht den Reward auf "spot / main" und den auf "earn / bonded" in derselben Sekunde; ist der eine gebucht, fehlt
    dem anderen die Reihenfolge, die der FIFO-Kern verlangt - einer gebuchten Buchung laesst sie sich nicht mehr beilegen. Wie beim
    Krypto-Import seit rc.272: Menge, Wert und Konto bleiben, nur Uhrzeit (und gegebenenfalls Tag) folgen. Ohne Zusammenstoss mit
    einer gebuchten Buchung bleibt der Entwurf unveraendert (Zeitgleiches unter Entwuerfen klaert "Zeitgleiche Rewards
    klassifizieren"). Traegt die gebuchte Buchung dieser Sekunde dasselbe Konto und dieselbe Menge, ist es vermutlich derselbe
    Reward: dann wird nicht versetzt ("same_as_booked", Festlegung 26.10.2026) - sonst stuende er doppelt da."""
    context = _context(context_value)
    updated = _utc(updated_at_utc)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int):
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path)
    taken = _booked_seconds(data_space_path, context)
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref))
        _ensure_draft_not_superseded(area, context, draft)
        if draft["revision"] != expected_revision:
            _abort("activity_draft_revision_conflict")
        if updated < draft["updated_at_utc"]:
            _abort("activity_draft_input_invalid")
        if draft["draft_state"] in {"applying", "committed"} or draft["action_type"] != "create":
            _abort("activity_draft_state_conflict")
        event = dict(draft["event"])
        moment_text = event.get("effective_at_utc")
        if (event.get("event_type") != "reward" or event.get("event_time_evidence") != "exact"
                or not isinstance(moment_text, str) or UTC.fullmatch(moment_text) is None or not isinstance(event.get("time_zone"), str)):
            _abort("activity_draft_input_invalid")
        try:
            zone = ZoneInfo(event["time_zone"])
        except (ZoneInfoNotFoundError, ValueError):
            _abort("activity_draft_input_invalid")
        booked = taken.get(event.get("asset_ref"), {})
        try:
            quantity = Decimal(str(event.get("quantity_decimal")))
        except (InvalidOperation, ValueError):
            _abort("activity_draft_input_invalid")
        same = [(account, value) for account, value in booked.get(moment_text, [])
                if account == event.get("account_ref") and value is not None and Decimal(value) == quantity]
        if same:
            return {"status": "same_as_booked", "shift_seconds": 0, "public_draft": _public(draft), "trusted_draft": draft}
        moment = datetime.strptime(moment_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        shifted = moment
        while shifted.strftime("%Y-%m-%dT%H:%M:%SZ") in booked:
            shifted += timedelta(seconds=1)
        seconds = int((shifted - moment).total_seconds())
        if seconds == 0:
            return {"status": "no_booked_collision", "shift_seconds": 0, "public_draft": _public(draft), "trusted_draft": draft}
        local = shifted.astimezone(zone)
        event.update(effective_at_utc=shifted.strftime("%Y-%m-%dT%H:%M:%SZ"), local_date=local.strftime("%Y-%m-%d"),
                     local_time=local.strftime("%H:%M:%S"))
        draft["event"] = event
        draft["revision"] += 1
        draft["updated_at_utc"] = updated
        _validation_reset(draft)
        stored = _persist(area, draft)
    return {"status": "shifted", "shift_seconds": seconds, "public_draft": _public(stored), "trusted_draft": stored}


def read_desktop_activity_draft_v1(
    data_space_path: str | Path,
    context_value: Any,
    draft_ref: str,
) -> dict[str, Any]:
    context = _context(context_value)
    with _verified_directories():
        area = _area(data_space_path, create=False)
        draft = _read(area, context, draft_ref)
        supersession = _supersession_for_draft(area, context, draft)
    result = {"public_draft": _public(draft, supersession), "trusted_draft": draft}
    if supersession is not None:
        result["trusted_supersession"] = supersession
    return result


def _validation_body(
    draft: Mapping[str, Any],
    canonical_path: str | Path,
    data_space_path: str | Path,
    context: DesktopProductAssetActivityContextV1,
    validated_at_utc: str,
) -> dict[str, Any]:
    event = dict(draft["event"])
    missing = [] if draft["action_type"] == "void" else list(NATIVE_EVENT_KEYS - set(event))
    auxiliary = draft.get("source_auxiliary")
    if isinstance(auxiliary, Mapping) and auxiliary.get("unclassified_fee_resolution") == "unresolved":
        missing.append("unclassified_fee_resolution")
    missing = sorted(set(missing))
    base = {
        "activity_draft_validation_version": 1,
        "validator_id": "desktop_activity_draft_shared_v1",
        "draft_revision": draft["revision"],
        "input_fingerprint": _fingerprint(_validation_input(draft, event)),
        "validated_at_utc": validated_at_utc,
        "missing_fields": missing,
        "issue_codes": [],
        "plan_kind": None,
        "expected_preview_fingerprint": None,
        "domain_public_preview": None,
        "trusted_preview": None,
    }
    if missing:
        base.update(status="needs_input", issue_codes=["activity_draft_fields_missing"])
    else:
        try:
            plan_kind, preview = _domain_preview(
                draft, event, canonical_path, data_space_path, context, validated_at_utc,
            )
            if plan_kind == "native_create":
                expected = preview.get("preview_fingerprint") or preview.get("product_preview_fingerprint")
                if not isinstance(expected, str) or SHA.fullmatch(expected) is None:
                    _abort("activity_draft_domain_invalid")
                base.update(
                    status="ready", plan_kind="native_create",
                    expected_preview_fingerprint=expected, trusted_preview=preview,
                )
            else:
                base.update(
                    status="ready", plan_kind="immutable_correction",
                    expected_preview_fingerprint=preview["trusted_preview"]["plan_fingerprint"],
                    domain_public_preview=preview["public_preview"],
                    trusted_preview=preview["trusted_preview"],
                )
        except (DesktopProductAssetActivityV1Error, DesktopAssetActivityCorrectionV1Error):
            base.update(status="blocked", issue_codes=["activity_draft_domain_invalid"])
    base["validation_fingerprint"] = _fingerprint(base)
    return base


def _domain_preview(
    draft: Mapping[str, Any],
    event: Mapping[str, Any],
    canonical_path: str | Path,
    data_space_path: str | Path,
    context: DesktopProductAssetActivityContextV1,
    validated_at_utc: str,
) -> tuple[str, dict[str, Any]]:
    """Die fachliche Vorschau eines vollstaendigen Entwurfs - oder der Fachfehler des Kerns.

    Die Pruefung eines Entwurfs haelt davon nur fest, dass der Kern ablehnte
    (`activity_draft_domain_invalid`). Wer den Grund nennen will, ruft dieselbe
    Vorschau noch einmal auf und liest den Fehler: Deshalb steht sie an genau
    einer Stelle (desktop_activity_block_reason_v1, #420).
    """
    if draft["action_type"] == "create":
        source_auxiliary = draft.get("source_auxiliary")
        fifo_order_evidence = (
            source_auxiliary.get("fifo_order_evidence")
            if isinstance(source_auxiliary, Mapping) else None
        )
        return "native_create", preview_desktop_native_asset_activity_v1(
            canonical_path, data_space_path, context, draft["portfolio_id"], [event],
            fifo_order_evidence_value=fifo_order_evidence,
        )
    replacement = None if draft["action_type"] == "void" else event
    return "immutable_correction", preview_desktop_asset_activity_correction_v1(
        canonical_path, data_space_path, context,
        draft["predecessor_event_ref"], replacement, validated_at_utc,
    )


def validate_desktop_activity_draft_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: Any,
    draft_ref: str,
    expected_revision: int,
    validated_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    validated = _utc(validated_at_utc)
    area = _area(data_space_path)
    snapshot = _read(area, context, draft_ref)
    _ensure_draft_not_superseded(area, context, snapshot)
    if snapshot["revision"] != expected_revision:
        _abort("activity_draft_revision_conflict")
    if validated < snapshot["updated_at_utc"]:
        _abort("activity_draft_input_invalid")
    if snapshot["draft_state"] in {"applying", "committed"}:
        _abort("activity_draft_state_conflict")
    validation = _validation_body(
        snapshot, canonical_path, data_space_path, context, validated
    )
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref))
        _ensure_draft_not_superseded(area, context, draft)
        if (
            draft["revision"] != snapshot["revision"]
            or _fingerprint(draft["event"]) != _fingerprint(snapshot["event"])
        ):
            _abort("activity_draft_revision_conflict")
        draft["validation"] = validation
        draft["validation_status"] = validation["status"]
        draft["validated_at_utc"] = validated
        draft["updated_at_utc"] = validated
        draft["draft_state"] = (
            "validated_ready" if validation["status"] == "ready"
            else "validated_blocked" if validation["status"] == "blocked"
            else "editing"
        )
        stored = _persist(area, draft)
    return {"public_draft": _public(stored), "trusted_draft": stored}


def build_desktop_activity_draft_confirmation_v1(
    trusted_draft: Mapping[str, Any],
    context_value: Any,
    challenge_ref: str,
    issued_at_utc: str,
    confirmed_at_utc: str,
    expires_at_utc: str,
    *, original_attempt_fingerprint: str | None = None,
) -> dict[str, Any]:
    context = _context(context_value)
    issued = _utc(issued_at_utc)
    confirmed = _utc(confirmed_at_utc)
    expires = _utc(expires_at_utc)
    if (
        not isinstance(trusted_draft, Mapping)
        or trusted_draft.get("context_fingerprint") != _context_fingerprint(context)
        or not (trusted_draft.get("draft_state") == "validated_ready" or
                (trusted_draft.get("activity_draft_version") == 2 and trusted_draft.get("draft_state") == "applying"))
        or not isinstance(trusted_draft.get("validated_at_utc"), str)
        or UTC.fullmatch(trusted_draft["validated_at_utc"]) is None
        or issued < trusted_draft["validated_at_utc"]
        or not isinstance(challenge_ref, str)
        or CHALLENGE.fullmatch(challenge_ref) is None
        or not issued <= confirmed <= expires
        or not isinstance(trusted_draft.get("validation"), Mapping)
    ):
        _abort("activity_draft_confirmation_invalid")
    body = {
        "activity_draft_confirmation_version": 2 if trusted_draft.get("draft_state") == "applying" else 1,
        "challenge_ref": challenge_ref,
        "context_fingerprint": _context_fingerprint(context),
        "draft_ref": trusted_draft["draft_ref"],
        "draft_revision": trusted_draft["revision"],
        "validation_fingerprint": trusted_draft["validation"]["validation_fingerprint"],
        "issued_at_utc": issued,
        "confirmed_at_utc": confirmed,
        "expires_at_utc": expires,
    }
    if body['activity_draft_confirmation_version'] == 2:
        if not isinstance(original_attempt_fingerprint, str) or re.fullmatch(r'[a-f0-9]{64}', original_attempt_fingerprint) is None:
            _abort('activity_draft_confirmation_invalid')
        body['original_attempt_fingerprint'] = original_attempt_fingerprint
    elif original_attempt_fingerprint is not None:
        _abort('activity_draft_confirmation_invalid')
    body["confirmation_fingerprint"] = _fingerprint(body)
    return body


def build_desktop_activity_draft_recovery_confirmation_v2(data_space_path, context_value, draft_ref,
                                                          challenge_ref, issued_at_utc, confirmed_at_utc, expires_at_utc):
    context = _context(context_value); area = _area(data_space_path)
    draft = _read(area, context, draft_ref)
    _ensure_draft_not_superseded(area, context, draft)
    if draft['activity_draft_version'] != 2 or draft['draft_state'] != 'applying':
        _abort('activity_draft_state_conflict')
    attempts = [_read_attempt_for_draft(path, draft, context)
                for path in _directory(area / ATTEMPTS_NAME).glob('adc_*.json')]
    matches = [item for item in attempts if item['draft_ref'] == draft_ref]
    if len(matches) != 1: _abort('activity_draft_attempt_conflict')
    if _utc(issued_at_utc) < matches[0]['committed_at_utc']: _abort('activity_draft_confirmation_invalid')
    return build_desktop_activity_draft_confirmation_v1(draft, context, challenge_ref,
        issued_at_utc, confirmed_at_utc, expires_at_utc, original_attempt_fingerprint=matches[0]['attempt_fingerprint'])


def _confirmation(
    value: Any,
    draft: Mapping[str, Any],
    context: DesktopProductAssetActivityContextV1,
    committed_at_utc: str,
    *, recovery: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _abort("activity_draft_confirmation_invalid")
    body = dict(value)
    fingerprint = body.pop("confirmation_fingerprint", None)
    expected = {
        "activity_draft_confirmation_version", "challenge_ref", "context_fingerprint",
        "draft_ref", "draft_revision", "validation_fingerprint", "issued_at_utc",
        "confirmed_at_utc", "expires_at_utc",
    }
    if recovery: expected.add('original_attempt_fingerprint')
    if (
        set(body) != expected
        or body.get("activity_draft_confirmation_version") != (2 if recovery else 1)
        or fingerprint != _fingerprint(body)
        or body.get("context_fingerprint") != _context_fingerprint(context)
        or body.get("draft_ref") != draft["draft_ref"]
        or body.get("draft_revision") != draft["revision"]
        or body.get("validation_fingerprint") != draft["validation"]["validation_fingerprint"]
        or CHALLENGE.fullmatch(str(body.get("challenge_ref", ""))) is None
    ):
        _abort("activity_draft_confirmation_invalid")
    try:
        issued = _utc(body["issued_at_utc"])
        confirmed = _utc(body["confirmed_at_utc"])
        expires = _utc(body["expires_at_utc"])
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_confirmation_invalid")
    if (
        not issued <= confirmed <= expires
        or issued < draft["validated_at_utc"]
        or committed_at_utc < confirmed
        or committed_at_utc < draft["updated_at_utc"]
    ):
        _abort("activity_draft_confirmation_invalid")
    if committed_at_utc > expires:
        _abort("activity_draft_confirmation_expired")
    return dict(value)


def _attempt(
    area: Path,
    confirmation: Mapping[str, Any],
    committed_at_utc: str,
) -> dict[str, Any]:
    attempts = _directory(area / ATTEMPTS_NAME, create=True)
    path = attempts / (confirmation["challenge_ref"] + ".json")
    body = {
        "activity_draft_attempt_version": 1,
        "attempt_status": "consumed_before_domain_write",
        "challenge_ref": confirmation["challenge_ref"],
        "context_fingerprint": confirmation["context_fingerprint"],
        "draft_ref": confirmation["draft_ref"],
        "draft_revision": confirmation["draft_revision"],
        "validation_fingerprint": confirmation["validation_fingerprint"],
        "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
        "confirmation": dict(confirmation),
        "committed_at_utc": committed_at_utc,
    }
    body["attempt_fingerprint"] = _fingerprint(body)
    content = _canonical(body) + b"\n"
    if path.exists():
        if _file(path).read_bytes() != content:
            _abort("activity_draft_attempt_conflict")
        return body
    try:
        _write_new(path, content)
    except DesktopActivityDraftV1Error as error:
        if error.code == "activity_draft_storage_invalid":
            _abort("activity_draft_attempt_conflict")
        raise
    return body


def _read_attempt_for_draft(
    path: Path,
    draft: Mapping[str, Any],
    context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    path = _file(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _abort("activity_draft_attempt_conflict")
    body = dict(value) if isinstance(value, dict) else {}
    fingerprint = body.pop("attempt_fingerprint", None)
    expected = {
        "activity_draft_attempt_version", "attempt_status", "challenge_ref",
        "context_fingerprint", "draft_ref", "draft_revision", "validation_fingerprint",
        "confirmation_fingerprint", "confirmation", "committed_at_utc",
    }
    if (
        set(body) != expected
        or raw != _canonical(value) + b"\n"
        or fingerprint != _fingerprint(body)
        or body.get("activity_draft_attempt_version") != 1
        or body.get("attempt_status") != "consumed_before_domain_write"
        or body.get("context_fingerprint") != _context_fingerprint(context)
        or DRAFT_REF.fullmatch(str(body.get("draft_ref", ""))) is None
        or isinstance(body.get("draft_revision"), bool)
        or not isinstance(body.get("draft_revision"), int)
        or body["draft_revision"] < 1
        or SHA.fullmatch(str(body.get("validation_fingerprint", ""))) is None
        or not isinstance(body.get("confirmation"), Mapping)
        or body.get("confirmation_fingerprint") != body["confirmation"].get("confirmation_fingerprint")
    ):
        _abort("activity_draft_attempt_conflict")
    try:
        _utc(body.get("committed_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_attempt_conflict")
    if body["draft_ref"] == draft["draft_ref"]:
        if (
            body["draft_revision"] != draft["revision"]
            or body["validation_fingerprint"] != draft["validation"]["validation_fingerprint"]
        ):
            _abort("activity_draft_attempt_conflict")
        _confirmation(body["confirmation"], draft, context, body["committed_at_utc"])
    return value


def _result_dict(result: Any) -> dict[str, Any]:
    if is_dataclass(result):
        return asdict(result)
    if isinstance(result, Mapping):
        return dict(result)
    _abort("activity_draft_domain_invalid")


def _public_receipt(draft: Mapping[str, Any], domain: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "activity_draft_receipt_version": 1,
        "status": domain.get("status", "committed"),
        "origin_type": draft["origin_type"],
        "action_type": draft["action_type"],
        "draft_status": "committed",
        "activity_generation_updated": bool(
            domain.get("canonical_write", False)
            or (draft.get('activity_draft_version') != 2 and domain.get("status") in {"committed", "recovered_committed"})
        ),
        "schema201_canonical_write": False,
        "cash_posting_count": int(domain.get("cash_posting_count", 0)),
        "provider_access": False,
        "network_access": False,
        "path_exposed": False,
        "browser_internal_id_exposed": False,
        "fingerprint_exposed": False,
    }


def apply_desktop_activity_draft_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: Any,
    draft_ref: str,
    confirmation_value: Mapping[str, Any],
    committed_at_utc: str,
    *,
    failpoint: str | None = None,
) -> dict[str, Any]:
    context = _context(context_value)
    committed = _utc(committed_at_utc)
    if isinstance(confirmation_value, Mapping) and confirmation_value.get('activity_draft_confirmation_version') == 2:
        return recover_desktop_activity_draft_v2(canonical_path, data_space_path, context, draft_ref, confirmation_value, committed, failpoint=failpoint)
    if failpoint not in FAILPOINTS:
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref))
        _ensure_draft_not_superseded(area, context, draft)
        if draft["draft_state"] not in {"validated_ready", "applying", "committed"} or not isinstance(draft.get("validation"), Mapping):
            _abort("activity_draft_state_conflict")
        if draft["activity_draft_version"] == 2 and draft["draft_state"] == "applying":
            _abort("activity_draft_state_conflict")
        confirmation = _confirmation(confirmation_value, draft, context, committed)
        _attempt(area, confirmation, committed)
        if draft["draft_state"] == "committed":
            domain = draft.get("domain_result") or {"status": "already_committed"}
            return {"public_receipt": _public_receipt(draft, domain), "trusted_draft": draft}
        draft["draft_state"] = "applying"
        draft["updated_at_utc"] = committed
        draft = _persist(area, draft)
    if failpoint == "after_draft_attempt":
        _abort("synthetic_activity_draft_failpoint")
    validation = draft["validation"]
    try:
        if draft["action_type"] == "create":
            source_auxiliary = draft.get("source_auxiliary")
            fifo_order_evidence = (
                source_auxiliary.get("fifo_order_evidence")
                if isinstance(source_auxiliary, Mapping) else None
            )
            result = apply_desktop_native_asset_activity_v1(
                canonical_path, data_space_path, context, draft["portfolio_id"],
                [draft["event"]], validation["expected_preview_fingerprint"], committed,
                fifo_order_evidence_value=fifo_order_evidence,
            )
        else:
            downstream = build_desktop_asset_activity_correction_confirmation_v1(
                validation["trusted_preview"], context,
                "aac_" + confirmation["confirmation_fingerprint"][:32],
                confirmation["issued_at_utc"], confirmation["confirmed_at_utc"],
                confirmation["expires_at_utc"],
            )
            result = apply_desktop_asset_activity_correction_v1(
                canonical_path, data_space_path, context,
                validation["trusted_preview"], downstream, committed,
            )
    except (DesktopProductAssetActivityV1Error, DesktopAssetActivityCorrectionV1Error):
        _abort("activity_draft_domain_invalid")
    if failpoint == "after_domain_commit":
        _abort("synthetic_activity_draft_failpoint")
    domain = _result_dict(result)
    with _DraftWriterLockV1(area):
        current = dict(_read(area, context, draft_ref))
        if (
            current["draft_state"] == "committed"
            and current.get("domain_result") == domain
        ):
            stored = current
        else:
            if (
                current["draft_state"] != "applying"
                or current["revision"] != draft["revision"]
                or current["validation"]["validation_fingerprint"]
                != validation["validation_fingerprint"]
            ):
                _abort("activity_draft_publication_failed")
            current["draft_state"] = "committed"
            current["committed_at_utc"] = committed
            current["updated_at_utc"] = committed
            current["domain_result"] = domain
            stored = _persist(area, current)
    return {"public_receipt": _public_receipt(stored, domain), "trusted_draft": stored}


def recover_desktop_activity_draft_v2(canonical_path, data_space_path, context_value, draft_ref,
                                      confirmation_value, recovered_at_utc, *, failpoint=None):
    """Freshly confirmed recovery of the SAME persisted selection and attempt."""
    context = _context(context_value); recovered = _utc(recovered_at_utc)
    if failpoint not in FAILPOINTS: _abort('activity_draft_input_invalid')
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        draft = dict(_read(area, context, draft_ref))
        _ensure_draft_not_superseded(area, context, draft)
        if draft['activity_draft_version'] != 2 or draft['draft_state'] != 'applying':
            _abort('activity_draft_state_conflict')
        fresh = _confirmation(confirmation_value, draft, context, recovered, recovery=True)
        attempts = [_read_attempt_for_draft(path, draft, context)
                    for path in _directory(area / ATTEMPTS_NAME).glob('adc_*.json')]
        matches = [item for item in attempts if item['draft_ref'] == draft_ref]
        if len(matches) != 1: _abort('activity_draft_attempt_conflict')
        original = matches[0]
        if fresh['original_attempt_fingerprint'] != original['attempt_fingerprint'] or fresh['issued_at_utc'] < original['committed_at_utc']:
            _abort('activity_draft_confirmation_invalid')
        journal = dict(original)
        journal.update(activity_draft_attempt_version=2, challenge_ref=fresh['challenge_ref'],
                       confirmation=fresh, confirmation_fingerprint=fresh['confirmation_fingerprint'],
                       committed_at_utc=recovered, original_attempt_fingerprint=original['attempt_fingerprint'])
        journal.pop('attempt_fingerprint')
        journal['attempt_fingerprint'] = _fingerprint(journal)
        path = _directory(area / 'recovery-attempts-v2', create=True) / (fresh['challenge_ref'] + '.json')
        if path.exists(): _abort('activity_draft_attempt_conflict')
        _write_new(path, _canonical(journal) + b'\n')
    if failpoint == 'after_draft_attempt': _abort('synthetic_activity_draft_failpoint')
    def downstream(value):
        return build_desktop_asset_activity_correction_confirmation_v1(
            draft['validation']['trusted_preview'], context, 'aac_' + value['confirmation_fingerprint'][:32],
            value['issued_at_utc'], value['confirmed_at_utc'], value['expires_at_utc'])
    try:
        result = apply_desktop_asset_activity_correction_v1(
            canonical_path, data_space_path, context, draft['validation']['trusted_preview'],
            downstream(original['confirmation']), recovered, recovery_confirmation=downstream(fresh))
    except (DesktopProductAssetActivityV1Error, DesktopAssetActivityCorrectionV1Error):
        _abort('activity_draft_domain_invalid')
    if failpoint == 'after_domain_commit': _abort('synthetic_activity_draft_failpoint')
    try:
        domain = _result_dict(reconcile_desktop_asset_activity_multi_void_v2(
            data_space_path, context, draft['validation']['trusted_preview'], downstream(original['confirmation'])))
        domain['canonical_write'] = result.status in {'committed', 'recovered_committed'}
    except (DesktopProductAssetActivityV1Error, DesktopAssetActivityCorrectionV1Error):
        _abort('activity_draft_domain_invalid')
    with _DraftWriterLockV1(area):
        current = dict(_read(area, context, draft_ref))
        if current['revision'] != draft['revision'] or current['validation'] != draft['validation'] or current['draft_state'] not in {'applying', 'committed'}:
            _abort('activity_draft_publication_failed')
        if current['draft_state'] == 'committed':
            return {'public_receipt': _public_receipt(current, current['domain_result']), 'trusted_draft': current}
        # Receipt time is immutable artifact evidence; the fresh execution time
        # is recorded independently in both recovery journals.
        current.update(draft_state='committed', committed_at_utc=domain['committed_at_utc'], updated_at_utc=recovered, domain_result=domain)
        stored = _persist(area, current)
    return {'public_receipt': _public_receipt(stored, domain), 'trusted_draft': stored}


def resume_desktop_activity_draft_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: Any,
    draft_ref: str,
) -> dict[str, Any]:
    context = _context(context_value)
    area = _area(data_space_path)
    draft = _read(area, context, draft_ref)
    _ensure_draft_not_superseded(area, context, draft)
    if draft["draft_state"] == "committed":
        domain = draft.get("domain_result") or {"status": "already_committed"}
        return {"public_receipt": _public_receipt(draft, domain), "trusted_draft": draft}
    if draft["draft_state"] != "applying" or not isinstance(draft.get("validation"), Mapping):
        _abort("activity_draft_state_conflict")
    attempts = _directory(area / ATTEMPTS_NAME)
    matches = []
    for path in sorted(attempts.glob("adc_*.json")):
        value = _read_attempt_for_draft(path, draft, context)
        if value["draft_ref"] == draft_ref:
            matches.append(value)
    if len(matches) != 1:
        _abort("activity_draft_attempt_conflict")
    attempt = matches[0]
    if draft["activity_draft_version"] == 2:
        # Historical authorization is evidence, not permission to execute now.
        # In particular, never replay a batch with the old attempt timestamp.
        confirmation = attempt["confirmation"]
        downstream = build_desktop_asset_activity_correction_confirmation_v1(
            draft["validation"]["trusted_preview"], context,
            "aac_" + confirmation["confirmation_fingerprint"][:32],
            confirmation["issued_at_utc"], confirmation["confirmed_at_utc"], confirmation["expires_at_utc"],
        )
        try:
            result = reconcile_desktop_asset_activity_multi_void_v2(
                data_space_path, context, draft["validation"]["trusted_preview"], downstream,
            )
        except (DesktopProductAssetActivityV1Error, DesktopAssetActivityCorrectionV1Error):
            _abort("activity_draft_domain_invalid")
        domain = _result_dict(result)
        with _DraftWriterLockV1(area):
            current = dict(_read(area, context, draft_ref))
            if current["revision"] != draft["revision"] or current["validation"] != draft["validation"]:
                _abort("activity_draft_publication_failed")
            if current["draft_state"] not in {"applying", "committed"}:
                _abort("activity_draft_state_conflict")
            current["draft_state"] = "committed"
            current["committed_at_utc"] = domain['committed_at_utc']
            current['updated_at_utc'] = max(current['updated_at_utc'], domain['committed_at_utc'])
            current["domain_result"] = domain
            stored = _persist(area, current)
        return {"public_receipt": _public_receipt(stored, domain), "trusted_draft": stored}
    return apply_desktop_activity_draft_v1(
        canonical_path, data_space_path, context, draft_ref,
        attempt["confirmation"], attempt["committed_at_utc"],
    )


def _validate_trusted_supersession_preview(
    value: Any, context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    expected = {
        "activity_draft_source_supersession_preview_version", "context_fingerprint",
        "source_fingerprint", "replacement_source_fingerprint",
        "expected_draft_count", "selected_drafts", "draft_set_fingerprint",
        "state_counts", "replacement_bound_draft_count", "prior_generation_ref",
        "prior_generation_fingerprint", "previewed_at_utc", "boundaries",
        "plan_fingerprint",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        _abort("activity_draft_confirmation_invalid")
    body = dict(value)
    plan_fingerprint = body.pop("plan_fingerprint", None)
    selected = body.get("selected_drafts")
    counts = body.get("state_counts")
    prior_ref = body.get("prior_generation_ref")
    prior_fingerprint = body.get("prior_generation_fingerprint")
    version = body.get("activity_draft_source_supersession_preview_version")
    allowed_states = (
        SUPERSEDABLE_DRAFT_STATES if version == 1
        else SUPERSEDABLE_DRAFT_STATES | frozenset({"committed"}) if version == 2
        else frozenset()
    )
    expected_counts = None if not isinstance(selected, list) else {
        state: sum(item.get("draft_state") == state for item in selected)
        for state in sorted(allowed_states)
    }
    if (
        version not in {1, 2}
        or body.get("context_fingerprint") != _context_fingerprint(context)
        or SHA.fullmatch(str(body.get("source_fingerprint", ""))) is None
        or SHA.fullmatch(str(body.get("replacement_source_fingerprint", ""))) is None
        or body["source_fingerprint"] == body["replacement_source_fingerprint"]
        or isinstance(body.get("expected_draft_count"), bool)
        or not isinstance(body.get("expected_draft_count"), int)
        or body["expected_draft_count"] < 1
        or not isinstance(selected, list)
        or len(selected) != body["expected_draft_count"]
        or counts != expected_counts
        or (version == 2 and (
            counts.get("committed", 0) < 1
            or counts.get("committed", 0) >= body["expected_draft_count"]
        ))
        or body.get("replacement_bound_draft_count") != 0
        or not ((prior_ref is None and prior_fingerprint is None) or (
            SUPERSESSION_GENERATION_REF.fullmatch(str(prior_ref)) is not None
            and SHA.fullmatch(str(prior_fingerprint)) is not None
        ))
        or body.get("boundaries") != {
            "draft_files_rewritten": 0, "schema201_write": False,
            "schema401_write": False, "cash_posting_count": 0,
            "provider_access": False, "network_access": False,
            "automatic_retry": False,
        }
        or plan_fingerprint != _fingerprint(body)
    ):
        _abort("activity_draft_confirmation_invalid")
    try:
        _utc(body.get("previewed_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_confirmation_invalid")
    item_keys = {
        "draft_ref", "draft_fingerprint", "draft_state", "source_row_ordinal",
        "binding_fingerprint",
    }
    if any(
        not isinstance(item, Mapping)
        or set(item) != item_keys
        or DRAFT_REF.fullmatch(str(item.get("draft_ref", ""))) is None
        or SHA.fullmatch(str(item.get("draft_fingerprint", ""))) is None
        or item.get("draft_state") not in allowed_states
        or isinstance(item.get("source_row_ordinal"), bool)
        or not isinstance(item.get("source_row_ordinal"), int)
        or item["source_row_ordinal"] < 1
        or SHA.fullmatch(str(item.get("binding_fingerprint", ""))) is None
        for item in selected
    ):
        _abort("activity_draft_confirmation_invalid")
    if (
        [item["draft_ref"] for item in selected] != sorted(item["draft_ref"] for item in selected)
        or len({item["draft_ref"] for item in selected}) != len(selected)
        or len({item["source_row_ordinal"] for item in selected}) != len(selected)
        or _fingerprint([
            {"draft_ref": item["draft_ref"], "draft_fingerprint": item["draft_fingerprint"]}
            for item in selected
        ]) != body["draft_set_fingerprint"]
    ):
        _abort("activity_draft_confirmation_invalid")
    return dict(value)


def _read_supersession_attempt(
    path: Path, context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    value = _read_owner_json(path)
    expected = {
        "activity_draft_source_supersession_attempt_version", "attempt_status",
        "challenge_ref", "context_fingerprint", "plan_fingerprint",
        "confirmation_fingerprint", "confirmation", "trusted_preview",
        "committed_at_utc", "attempt_fingerprint",
    }
    body = dict(value)
    fingerprint = body.pop("attempt_fingerprint", None)
    if (
        set(value) != expected
        or body.get("activity_draft_source_supersession_attempt_version") not in {1, 2}
        or body.get("attempt_status") != "consumed_before_supersession_generation_write"
        or SUPERSESSION_CHALLENGE.fullmatch(str(body.get("challenge_ref", ""))) is None
        or body.get("context_fingerprint") != _context_fingerprint(context)
        or SHA.fullmatch(str(body.get("plan_fingerprint", ""))) is None
        or SHA.fullmatch(str(body.get("confirmation_fingerprint", ""))) is None
        or not isinstance(body.get("confirmation"), Mapping)
        or not isinstance(body.get("trusted_preview"), Mapping)
        or fingerprint != _fingerprint(body)
    ):
        _abort("activity_draft_attempt_conflict")
    preview = _validate_trusted_supersession_preview(body["trusted_preview"], context)
    try:
        committed = _utc(body.get("committed_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_attempt_conflict")
    confirmation = _supersession_confirmation(
        body["confirmation"], preview, context, committed,
    )
    if (
        body["activity_draft_source_supersession_attempt_version"]
        != preview["activity_draft_source_supersession_preview_version"]
        or body["challenge_ref"] != confirmation["challenge_ref"]
        or body["plan_fingerprint"] != preview["plan_fingerprint"]
        or body["confirmation_fingerprint"] != confirmation["confirmation_fingerprint"]
    ):
        _abort("activity_draft_attempt_conflict")
    return value


def _pending_supersession_attempts(
    area: Path, context: DesktopProductAssetActivityContextV1,
    active_generation: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    attempts_path = area / SUPERSESSION_ATTEMPTS_NAME
    if not attempts_path.exists():
        return []
    attempts = _strict_owner_directory(attempts_path)
    active_plans = set() if active_generation is None else {
        item["plan_fingerprint"] for item in active_generation["commands"]
    }
    rows = []
    for path in sorted(attempts.glob("ads_*.json")):
        attempt = _read_supersession_attempt(path, context)
        if attempt["plan_fingerprint"] not in active_plans:
            rows.append(attempt)
    return rows


def _ensure_no_pending_supersession(
    area: Path, context: DesktopProductAssetActivityContextV1,
) -> None:
    active = _active_supersession_generation(area, context)
    if _pending_supersession_attempts(area, context, active):
        _abort("activity_draft_supersession_conflict")


def _build_supersession_preview(
    data_space_path: str | Path,
    context: DesktopProductAssetActivityContextV1,
    source_fingerprint: str,
    replacement_source_fingerprint: str,
    expected_draft_count: int,
    previewed_at_utc: str,
    *,
    allow_pending_attempt: bool = False,
) -> dict[str, Any]:
    if (
        not isinstance(source_fingerprint, str)
        or SHA.fullmatch(source_fingerprint) is None
        or not isinstance(replacement_source_fingerprint, str)
        or SHA.fullmatch(replacement_source_fingerprint) is None
        or source_fingerprint == replacement_source_fingerprint
        or isinstance(expected_draft_count, bool)
        or not isinstance(expected_draft_count, int)
        or expected_draft_count < 1
    ):
        _abort("activity_draft_input_invalid")
    previewed = _utc(previewed_at_utc)
    area = _area(data_space_path, create=False)
    supersessions, active = _supersession_index(area, context)
    pending = _pending_supersession_attempts(area, context, active)
    if pending and not allow_pending_attempt:
        _abort("activity_draft_supersession_conflict")
    if active is not None and any(
        item["source_fingerprint"] == source_fingerprint for item in active["commands"]
    ):
        _abort("activity_draft_source_superseded")
    drafts_path = area / DRAFTS_NAME
    if not drafts_path.exists():
        _abort("activity_draft_supersession_conflict")
    drafts = _directory(drafts_path)
    selected: list[dict[str, Any]] = []
    replacement_count = 0
    for path in sorted(drafts.glob("adt_*.json")):
        _strict_owner_file(path)
        draft = _read(area, context, path.stem)
        if draft["draft_state"] == "applying":
            _abort("activity_draft_supersession_conflict")
        binding = draft.get("source_binding")
        if not isinstance(binding, Mapping):
            continue
        if binding.get("source_fingerprint") == replacement_source_fingerprint:
            replacement_count += 1
        if binding.get("source_fingerprint") != source_fingerprint:
            continue
        tombstone = supersessions.get(draft["draft_ref"])
        if tombstone is not None:
            if tombstone["draft_fingerprint"] != draft["draft_fingerprint"]:
                _abort("activity_draft_storage_invalid")
            _abort("activity_draft_source_superseded")
        if (
            draft.get("origin_type") != "tolerant_csv"
            or draft.get("action_type") != "create"
            or draft.get("draft_state") not in SUPERSEDABLE_DRAFT_STATES
        ):
            _abort("activity_draft_supersession_conflict")
        selected.append({
            "draft_ref": draft["draft_ref"],
            "draft_fingerprint": draft["draft_fingerprint"],
            "draft_state": draft["draft_state"],
            "source_row_ordinal": binding["source_row_ordinal"],
            "binding_fingerprint": binding["binding_fingerprint"],
        })
    selected.sort(key=lambda item: item["draft_ref"])
    if (
        len(selected) != expected_draft_count
        or replacement_count != 0
        or len({item["source_row_ordinal"] for item in selected}) != len(selected)
    ):
        _abort("activity_draft_supersession_conflict")
    draft_set = [
        {"draft_ref": item["draft_ref"], "draft_fingerprint": item["draft_fingerprint"]}
        for item in selected
    ]
    body = {
        "activity_draft_source_supersession_preview_version": 1,
        "context_fingerprint": _context_fingerprint(context),
        "source_fingerprint": source_fingerprint,
        "replacement_source_fingerprint": replacement_source_fingerprint,
        "expected_draft_count": expected_draft_count,
        "selected_drafts": selected,
        "draft_set_fingerprint": _fingerprint(draft_set),
        "state_counts": {
            state: sum(item["draft_state"] == state for item in selected)
            for state in sorted(SUPERSEDABLE_DRAFT_STATES)
        },
        "replacement_bound_draft_count": replacement_count,
        "prior_generation_ref": None if active is None else active["generation_ref"],
        "prior_generation_fingerprint": None if active is None else active["generation_fingerprint"],
        "previewed_at_utc": previewed,
        "boundaries": {
            "draft_files_rewritten": 0, "schema201_write": False,
            "schema401_write": False, "cash_posting_count": 0,
            "provider_access": False, "network_access": False,
            "automatic_retry": False,
        },
    }
    body["plan_fingerprint"] = _fingerprint(body)
    return body


def _build_mixed_source_retirement_preview(
    data_space_path: str | Path,
    context: DesktopProductAssetActivityContextV1,
    source_fingerprint: str,
    replacement_source_fingerprint: str,
    expected_source_draft_count: int,
    expected_committed_draft_count: int,
    previewed_at_utc: str,
    *,
    allow_pending_attempt: bool = False,
) -> dict[str, Any]:
    if (
        not isinstance(source_fingerprint, str)
        or SHA.fullmatch(source_fingerprint) is None
        or not isinstance(replacement_source_fingerprint, str)
        or SHA.fullmatch(replacement_source_fingerprint) is None
        or source_fingerprint == replacement_source_fingerprint
        or isinstance(expected_source_draft_count, bool)
        or not isinstance(expected_source_draft_count, int)
        or expected_source_draft_count < 2
        or isinstance(expected_committed_draft_count, bool)
        or not isinstance(expected_committed_draft_count, int)
        or expected_committed_draft_count < 1
        or expected_committed_draft_count >= expected_source_draft_count
    ):
        _abort("activity_draft_input_invalid")
    previewed = _utc(previewed_at_utc)
    area = _area(data_space_path, create=False)
    supersessions, active = _supersession_index(area, context)
    pending = _pending_supersession_attempts(area, context, active)
    if pending and not allow_pending_attempt:
        _abort("activity_draft_supersession_conflict")
    if active is not None and any(
        item["source_fingerprint"] == source_fingerprint for item in active["commands"]
    ):
        _abort("activity_draft_source_superseded")
    drafts_path = area / DRAFTS_NAME
    if not drafts_path.exists():
        _abort("activity_draft_supersession_conflict")
    drafts = _directory(drafts_path)
    selected: list[dict[str, Any]] = []
    replacement_count = 0
    allowed_states = SUPERSEDABLE_DRAFT_STATES | frozenset({"committed"})
    for path in sorted(drafts.glob("adt_*.json")):
        _strict_owner_file(path)
        draft = _read(area, context, path.stem)
        if draft["draft_state"] == "applying":
            _abort("activity_draft_supersession_conflict")
        binding = draft.get("source_binding")
        if not isinstance(binding, Mapping):
            continue
        if binding.get("source_fingerprint") == replacement_source_fingerprint:
            replacement_count += 1
        if binding.get("source_fingerprint") != source_fingerprint:
            continue
        tombstone = supersessions.get(draft["draft_ref"])
        if tombstone is not None:
            if tombstone["draft_fingerprint"] != draft["draft_fingerprint"]:
                _abort("activity_draft_storage_invalid")
            _abort("activity_draft_source_superseded")
        if (
            draft.get("origin_type") != "tolerant_csv"
            or draft.get("action_type") != "create"
            or draft.get("draft_state") not in allowed_states
        ):
            _abort("activity_draft_supersession_conflict")
        selected.append({
            "draft_ref": draft["draft_ref"],
            "draft_fingerprint": draft["draft_fingerprint"],
            "draft_state": draft["draft_state"],
            "source_row_ordinal": binding["source_row_ordinal"],
            "binding_fingerprint": binding["binding_fingerprint"],
        })
    selected.sort(key=lambda item: item["draft_ref"])
    committed_count = sum(item["draft_state"] == "committed" for item in selected)
    if (
        len(selected) != expected_source_draft_count
        or committed_count != expected_committed_draft_count
        or replacement_count != 0
        or len({item["source_row_ordinal"] for item in selected}) != len(selected)
    ):
        _abort("activity_draft_supersession_conflict")
    draft_set = [
        {"draft_ref": item["draft_ref"], "draft_fingerprint": item["draft_fingerprint"]}
        for item in selected
    ]
    body = {
        "activity_draft_source_supersession_preview_version": 2,
        "context_fingerprint": _context_fingerprint(context),
        "source_fingerprint": source_fingerprint,
        "replacement_source_fingerprint": replacement_source_fingerprint,
        "expected_draft_count": expected_source_draft_count,
        "selected_drafts": selected,
        "draft_set_fingerprint": _fingerprint(draft_set),
        "state_counts": {
            state: sum(item["draft_state"] == state for item in selected)
            for state in sorted(allowed_states)
        },
        "replacement_bound_draft_count": replacement_count,
        "prior_generation_ref": None if active is None else active["generation_ref"],
        "prior_generation_fingerprint": None if active is None else active["generation_fingerprint"],
        "previewed_at_utc": previewed,
        "boundaries": {
            "draft_files_rewritten": 0, "schema201_write": False,
            "schema401_write": False, "cash_posting_count": 0,
            "provider_access": False, "network_access": False,
            "automatic_retry": False,
        },
    }
    body["plan_fingerprint"] = _fingerprint(body)
    return body


def _public_supersession_preview(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "activity_draft_source_supersession_public_preview_version": 1,
        "status": "ready",
        "draft_count": value["expected_draft_count"],
        "state_counts": dict(value["state_counts"]),
        "replacement_bound_draft_count": value["replacement_bound_draft_count"],
        "exact_source_scope": True,
        "original_draft_files_rewritten": False,
        "legacy_writer_barrier_required": True,
        "schema201_canonical_write": False,
        "schema401_activity_write": False,
        "cash_posting_count": 0,
        "provider_access": False,
        "network_access": False,
        "automatic_retry": False,
        "path_exposed": False,
        "browser_internal_id_exposed": False,
        "fingerprint_exposed": False,
    }


def _public_mixed_source_retirement_preview(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "activity_draft_source_supersession_public_preview_version": 2,
        "status": "ready",
        "draft_count": value["expected_draft_count"],
        "state_counts": dict(value["state_counts"]),
        "replacement_bound_draft_count": value["replacement_bound_draft_count"],
        "exact_source_scope": True,
        "original_draft_files_rewritten": False,
        "legacy_writer_barrier_required": True,
        "schema201_canonical_write": False,
        "schema401_activity_write": False,
        "cash_posting_count": 0,
        "provider_access": False,
        "network_access": False,
        "automatic_retry": False,
        "path_exposed": False,
        "browser_internal_id_exposed": False,
        "fingerprint_exposed": False,
    }


def preview_desktop_activity_draft_source_supersession_v1(
    data_space_path: str | Path,
    context_value: Any,
    source_fingerprint: str,
    replacement_source_fingerprint: str,
    expected_draft_count: int,
    previewed_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    trusted = _build_supersession_preview(
        data_space_path, context, source_fingerprint, replacement_source_fingerprint,
        expected_draft_count, previewed_at_utc,
    )
    return {
        "public_preview": _public_supersession_preview(trusted),
        "trusted_preview": trusted,
    }


def preview_desktop_activity_draft_mixed_source_retirement_v1(
    data_space_path: str | Path,
    context_value: Any,
    source_fingerprint: str,
    replacement_source_fingerprint: str,
    expected_source_draft_count: int,
    expected_committed_draft_count: int,
    previewed_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    trusted = _build_mixed_source_retirement_preview(
        data_space_path, context, source_fingerprint, replacement_source_fingerprint,
        expected_source_draft_count, expected_committed_draft_count, previewed_at_utc,
    )
    return {
        "public_preview": _public_mixed_source_retirement_preview(trusted),
        "trusted_preview": trusted,
    }


def build_desktop_activity_draft_source_supersession_confirmation_v1(
    trusted_preview_value: Mapping[str, Any],
    context_value: Any,
    challenge_ref: str,
    issued_at_utc: str,
    confirmed_at_utc: str,
    expires_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    preview = _validate_trusted_supersession_preview(trusted_preview_value, context)
    if preview["activity_draft_source_supersession_preview_version"] != 1:
        _abort("activity_draft_confirmation_invalid")
    issued = _utc(issued_at_utc)
    confirmed = _utc(confirmed_at_utc)
    expires = _utc(expires_at_utc)
    if (
        not isinstance(challenge_ref, str)
        or SUPERSESSION_CHALLENGE.fullmatch(challenge_ref) is None
        or issued < preview["previewed_at_utc"]
        or not issued <= confirmed <= expires
    ):
        _abort("activity_draft_confirmation_invalid")
    body = {
        "activity_draft_source_supersession_confirmation_version": 1,
        "challenge_ref": challenge_ref,
        "context_fingerprint": _context_fingerprint(context),
        "plan_fingerprint": preview["plan_fingerprint"],
        "draft_set_fingerprint": preview["draft_set_fingerprint"],
        "source_fingerprint": preview["source_fingerprint"],
        "replacement_source_fingerprint": preview["replacement_source_fingerprint"],
        "draft_count": preview["expected_draft_count"],
        "issued_at_utc": issued,
        "confirmed_at_utc": confirmed,
        "expires_at_utc": expires,
    }
    body["confirmation_fingerprint"] = _fingerprint(body)
    return body


def build_desktop_activity_draft_mixed_source_retirement_confirmation_v1(
    trusted_preview_value: Mapping[str, Any],
    context_value: Any,
    challenge_ref: str,
    issued_at_utc: str,
    confirmed_at_utc: str,
    expires_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    preview = _validate_trusted_supersession_preview(trusted_preview_value, context)
    if preview["activity_draft_source_supersession_preview_version"] != 2:
        _abort("activity_draft_confirmation_invalid")
    issued = _utc(issued_at_utc)
    confirmed = _utc(confirmed_at_utc)
    expires = _utc(expires_at_utc)
    if (
        not isinstance(challenge_ref, str)
        or SUPERSESSION_CHALLENGE.fullmatch(challenge_ref) is None
        or issued < preview["previewed_at_utc"]
        or not issued <= confirmed <= expires
    ):
        _abort("activity_draft_confirmation_invalid")
    body = {
        "activity_draft_source_supersession_confirmation_version": 2,
        "challenge_ref": challenge_ref,
        "context_fingerprint": _context_fingerprint(context),
        "plan_fingerprint": preview["plan_fingerprint"],
        "draft_set_fingerprint": preview["draft_set_fingerprint"],
        "source_fingerprint": preview["source_fingerprint"],
        "replacement_source_fingerprint": preview["replacement_source_fingerprint"],
        "draft_count": preview["expected_draft_count"],
        "issued_at_utc": issued,
        "confirmed_at_utc": confirmed,
        "expires_at_utc": expires,
    }
    body["confirmation_fingerprint"] = _fingerprint(body)
    return body


def _supersession_confirmation(
    value: Any,
    trusted_preview: Mapping[str, Any],
    context: DesktopProductAssetActivityContextV1,
    committed_at_utc: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _abort("activity_draft_confirmation_invalid")
    body = dict(value)
    fingerprint = body.pop("confirmation_fingerprint", None)
    expected = {
        "activity_draft_source_supersession_confirmation_version", "challenge_ref",
        "context_fingerprint", "plan_fingerprint", "draft_set_fingerprint",
        "source_fingerprint", "replacement_source_fingerprint", "draft_count",
        "issued_at_utc", "confirmed_at_utc", "expires_at_utc",
    }
    if (
        set(body) != expected
        or body.get("activity_draft_source_supersession_confirmation_version")
        != trusted_preview["activity_draft_source_supersession_preview_version"]
        or body.get("activity_draft_source_supersession_confirmation_version") not in {1, 2}
        or SUPERSESSION_CHALLENGE.fullmatch(str(body.get("challenge_ref", ""))) is None
        or body.get("context_fingerprint") != _context_fingerprint(context)
        or body.get("plan_fingerprint") != trusted_preview["plan_fingerprint"]
        or body.get("draft_set_fingerprint") != trusted_preview["draft_set_fingerprint"]
        or body.get("source_fingerprint") != trusted_preview["source_fingerprint"]
        or body.get("replacement_source_fingerprint") != trusted_preview["replacement_source_fingerprint"]
        or body.get("draft_count") != trusted_preview["expected_draft_count"]
        or fingerprint != _fingerprint(body)
    ):
        _abort("activity_draft_confirmation_invalid")
    try:
        issued = _utc(body.get("issued_at_utc"))
        confirmed = _utc(body.get("confirmed_at_utc"))
        expires = _utc(body.get("expires_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_confirmation_invalid")
    if (
        issued < trusted_preview["previewed_at_utc"]
        or not issued <= confirmed <= expires
        or committed_at_utc < confirmed
    ):
        _abort("activity_draft_confirmation_invalid")
    if committed_at_utc > expires:
        _abort("activity_draft_confirmation_expired")
    return dict(value)


def _write_supersession_attempt(
    area: Path,
    trusted_preview: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    committed_at_utc: str,
) -> dict[str, Any]:
    attempts = _directory(area / SUPERSESSION_ATTEMPTS_NAME, create=True)
    _strict_owner_directory(attempts)
    path = attempts / (confirmation["challenge_ref"] + ".json")
    body = {
        "activity_draft_source_supersession_attempt_version": trusted_preview[
            "activity_draft_source_supersession_preview_version"
        ],
        "attempt_status": "consumed_before_supersession_generation_write",
        "challenge_ref": confirmation["challenge_ref"],
        "context_fingerprint": confirmation["context_fingerprint"],
        "plan_fingerprint": trusted_preview["plan_fingerprint"],
        "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
        "confirmation": dict(confirmation),
        "trusted_preview": dict(trusted_preview),
        "committed_at_utc": committed_at_utc,
    }
    body["attempt_fingerprint"] = _fingerprint(body)
    content = _canonical(body) + b"\n"
    if path.exists():
        if _strict_owner_file(path).read_bytes() != content:
            _abort("activity_draft_attempt_conflict")
        return body
    _write_new(path, content)
    _strict_owner_file(path)
    return body


def _build_supersession_generation(
    active: Mapping[str, Any] | None,
    trusted_preview: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    committed_at_utc: str,
    context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    command_body = {
        "activity_draft_source_supersession_command_version": trusted_preview[
            "activity_draft_source_supersession_preview_version"
        ],
        "context_fingerprint": _context_fingerprint(context),
        "source_fingerprint": trusted_preview["source_fingerprint"],
        "replacement_source_fingerprint": trusted_preview["replacement_source_fingerprint"],
        "draft_count": trusted_preview["expected_draft_count"],
        "draft_set_fingerprint": trusted_preview["draft_set_fingerprint"],
        "plan_fingerprint": trusted_preview["plan_fingerprint"],
        "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
        "confirmed_at_utc": confirmation["confirmed_at_utc"],
        "superseded_at_utc": committed_at_utc,
    }
    command_body["command_fingerprint"] = _fingerprint(command_body)
    prior_commands = [] if active is None else [dict(item) for item in active["commands"]]
    prior_tombstones = [] if active is None else [dict(item) for item in active["tombstones"]]
    new_tombstones = [{
        "activity_draft_tombstone_version": 1,
        "draft_ref": item["draft_ref"],
        "draft_fingerprint": item["draft_fingerprint"],
        "source_fingerprint": trusted_preview["source_fingerprint"],
        "replacement_source_fingerprint": trusted_preview["replacement_source_fingerprint"],
        "supersession_command_fingerprint": command_body["command_fingerprint"],
        "superseded_at_utc": committed_at_utc,
    } for item in trusted_preview["selected_drafts"] if item["draft_state"] != "committed"]
    tombstones = sorted(prior_tombstones + new_tombstones, key=lambda item: item["draft_ref"])
    if len({item["draft_ref"] for item in tombstones}) != len(tombstones):
        _abort("activity_draft_supersession_conflict")
    predecessor = None if active is None else active["generation_ref"]
    generation_ref = "adg_" + _fingerprint({
        "predecessor_generation_ref": predecessor,
        "command_fingerprint": command_body["command_fingerprint"],
    })[:32]
    body = {
        "activity_draft_supersession_generation_version": 1,
        "generation_ref": generation_ref,
        "predecessor_generation_ref": predecessor,
        "context_fingerprint": _context_fingerprint(context),
        "created_at_utc": committed_at_utc,
        "commands": prior_commands + [command_body],
        "tombstones": tombstones,
        "boundaries": {
            "draft_files_rewritten": 0, "schema201_write": False,
            "schema401_write": False, "cash_posting_count": 0,
            "provider_access": False, "network_access": False,
            "automatic_retry": False,
        },
    }
    body["generation_fingerprint"] = _fingerprint(body)
    return _validate_supersession_generation(body, context)


def _publish_supersession_generation(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    generation: Mapping[str, Any],
) -> bool:
    generations = _directory(area / SUPERSESSION_GENERATIONS_NAME, create=True)
    _strict_owner_directory(generations)
    path = generations / (generation["generation_ref"] + ".json")
    content = _canonical(generation) + b"\n"
    if path.exists():
        if _strict_owner_file(path).read_bytes() != content:
            _abort("activity_draft_supersession_conflict")
        _read_supersession_generation(
            area, context, generation["generation_ref"], require_mixed_barrier=False,
        )
        return True
    _write_new(path, content)
    _read_supersession_generation(
        area, context, generation["generation_ref"], require_mixed_barrier=False,
    )
    return False


def _activate_supersession_generation(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    generation: Mapping[str, Any],
    activated_at_utc: str,
) -> bool:
    current = _active_supersession_generation(area, context)
    if current is not None:
        if current["generation_ref"] == generation["generation_ref"]:
            return False
        if current["generation_ref"] != generation["predecessor_generation_ref"]:
            _abort("activity_draft_supersession_conflict")
    elif generation["predecessor_generation_ref"] is not None:
        _abort("activity_draft_supersession_conflict")
    body = {
        "activity_draft_supersession_active_version": 1,
        "context_fingerprint": _context_fingerprint(context),
        "generation_ref": generation["generation_ref"],
        "generation_fingerprint": generation["generation_fingerprint"],
        "activated_at_utc": activated_at_utc,
    }
    body["pointer_fingerprint"] = _fingerprint(body)
    path = area / SUPERSESSION_ACTIVE_NAME
    content = _canonical(body) + b"\n"
    if path.exists():
        _strict_owner_file(path)
        _replace(path, content)
    else:
        _write_new(path, content)
    _strict_owner_file(path)
    verified = _active_supersession_generation(area, context)
    if verified is None or verified["generation_ref"] != generation["generation_ref"]:
        _abort("activity_draft_publication_failed")
    return True


def _public_supersession_receipt(
    status: str, generation: Mapping[str, Any], generation_updated: bool,
    superseded_count: int,
) -> dict[str, Any]:
    return {
        "activity_draft_source_supersession_receipt_version": 1,
        "status": status,
        "superseded_draft_count": superseded_count,
        "active_superseded_draft_count": len(generation["tombstones"]),
        "supersession_generation_updated": generation_updated,
        "original_draft_files_rewritten": False,
        "legacy_writer_blocked": True,
        "schema201_canonical_write": False,
        "schema401_activity_write": False,
        "cash_posting_count": 0,
        "provider_access": False,
        "network_access": False,
        "automatic_retry": False,
        "path_exposed": False,
        "browser_internal_id_exposed": False,
        "fingerprint_exposed": False,
    }


def apply_desktop_activity_draft_source_supersession_v1(
    data_space_path: str | Path,
    context_value: Any,
    trusted_preview_value: Mapping[str, Any],
    confirmation_value: Mapping[str, Any],
    committed_at_utc: str,
    *,
    failpoint: str | None = None,
) -> dict[str, Any]:
    context = _context(context_value)
    committed = _utc(committed_at_utc)
    if failpoint not in SUPERSESSION_FAILPOINTS:
        _abort("activity_draft_input_invalid")
    trusted = _validate_trusted_supersession_preview(trusted_preview_value, context)
    if trusted["activity_draft_source_supersession_preview_version"] != 1:
        _abort("activity_draft_confirmation_invalid")
    confirmation = _supersession_confirmation(
        confirmation_value, trusted, context, committed,
    )
    area = _area(data_space_path, create=False)
    with _DraftWriterLockV1(area) as writer:
        active = _active_supersession_generation(area, context)
        if active is not None:
            matching = [
                item for item in active["commands"]
                if item["plan_fingerprint"] == trusted["plan_fingerprint"]
            ]
            if matching:
                if (
                    len(matching) != 1
                    or matching[0]["confirmation_fingerprint"]
                    != confirmation["confirmation_fingerprint"]
                ):
                    _abort("activity_draft_supersession_conflict")
                _write_supersession_attempt(area, trusted, confirmation, committed)
                return {
                    "public_receipt": _public_supersession_receipt(
                        "already_superseded", active, False,
                        trusted["expected_draft_count"],
                    ),
                    "trusted_generation": active,
                }
        refreshed = _build_supersession_preview(
            data_space_path, context, trusted["source_fingerprint"],
            trusted["replacement_source_fingerprint"],
            trusted["expected_draft_count"], trusted["previewed_at_utc"],
            allow_pending_attempt=True,
        )
        if refreshed != trusted:
            _abort("activity_draft_supersession_conflict")
        _write_supersession_attempt(area, trusted, confirmation, committed)
        if failpoint == "after_supersession_attempt":
            _abort("synthetic_activity_draft_supersession_failpoint")
        generation = _build_supersession_generation(
            active, trusted, confirmation, committed, context,
        )
        generation_reused = _publish_supersession_generation(area, context, generation)
        if failpoint == "after_supersession_generation":
            _abort("synthetic_activity_draft_supersession_failpoint")
        writer.install_supersession_barrier()
        if failpoint == "after_supersession_barrier":
            _abort("synthetic_activity_draft_supersession_failpoint")
        generation_updated = _activate_supersession_generation(
            area, context, generation, committed,
        )
    return {
        "public_receipt": _public_supersession_receipt(
            "recovered_superseded" if generation_reused else "superseded",
            generation, generation_updated, trusted["expected_draft_count"],
        ),
        "trusted_generation": generation,
    }


def apply_desktop_activity_draft_mixed_source_retirement_v1(
    data_space_path: str | Path,
    context_value: Any,
    trusted_preview_value: Mapping[str, Any],
    confirmation_value: Mapping[str, Any],
    committed_at_utc: str,
    *,
    failpoint: str | None = None,
) -> dict[str, Any]:
    context = _context(context_value)
    committed = _utc(committed_at_utc)
    if failpoint not in SUPERSESSION_FAILPOINTS:
        _abort("activity_draft_input_invalid")
    trusted = _validate_trusted_supersession_preview(trusted_preview_value, context)
    if trusted["activity_draft_source_supersession_preview_version"] != 2:
        _abort("activity_draft_confirmation_invalid")
    confirmation = _supersession_confirmation(
        confirmation_value, trusted, context, committed,
    )
    superseded_count = (
        trusted["expected_draft_count"] - trusted["state_counts"]["committed"]
    )
    area = _area(data_space_path, create=False)
    with _DraftWriterLockV1(area) as writer:
        active = _active_supersession_generation(area, context)
        if active is not None:
            matching = [
                item for item in active["commands"]
                if item["plan_fingerprint"] == trusted["plan_fingerprint"]
            ]
            if matching:
                if (
                    len(matching) != 1
                    or matching[0]["confirmation_fingerprint"]
                    != confirmation["confirmation_fingerprint"]
                    or matching[0]["activity_draft_source_supersession_command_version"] != 2
                ):
                    _abort("activity_draft_supersession_conflict")
                _write_supersession_attempt(area, trusted, confirmation, committed)
                return {
                    "public_receipt": _public_supersession_receipt(
                        "already_superseded", active, False, superseded_count,
                    ),
                    "trusted_generation": active,
                }
        refreshed = _build_mixed_source_retirement_preview(
            data_space_path, context, trusted["source_fingerprint"],
            trusted["replacement_source_fingerprint"],
            trusted["expected_draft_count"], trusted["state_counts"]["committed"],
            trusted["previewed_at_utc"], allow_pending_attempt=True,
        )
        if refreshed != trusted:
            _abort("activity_draft_supersession_conflict")
        _write_supersession_attempt(area, trusted, confirmation, committed)
        if failpoint == "after_supersession_attempt":
            _abort("synthetic_activity_draft_supersession_failpoint")
        generation = _build_supersession_generation(
            active, trusted, confirmation, committed, context,
        )
        generation_reused = _publish_supersession_generation(area, context, generation)
        if failpoint == "after_supersession_generation":
            _abort("synthetic_activity_draft_supersession_failpoint")
        writer.install_supersession_barrier()
        writer.install_mixed_source_retirement_barrier()
        if failpoint == "after_supersession_barrier":
            _abort("synthetic_activity_draft_supersession_failpoint")
        generation_updated = _activate_supersession_generation(
            area, context, generation, committed,
        )
    return {
        "public_receipt": _public_supersession_receipt(
            "recovered_superseded" if generation_reused else "superseded",
            generation, generation_updated, superseded_count,
        ),
        "trusted_generation": generation,
    }


def resume_desktop_activity_draft_source_supersession_v1(
    data_space_path: str | Path,
    context_value: Any,
    challenge_ref: str,
) -> dict[str, Any]:
    context = _context(context_value)
    if not isinstance(challenge_ref, str) or SUPERSESSION_CHALLENGE.fullmatch(challenge_ref) is None:
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path, create=False)
    attempts_path = area / SUPERSESSION_ATTEMPTS_NAME
    if not attempts_path.exists():
        _abort("activity_draft_supersession_not_found")
    path = _strict_owner_directory(attempts_path) / (challenge_ref + ".json")
    if not path.exists():
        _abort("activity_draft_supersession_not_found")
    attempt = _read_supersession_attempt(path, context)
    if attempt["trusted_preview"]["activity_draft_source_supersession_preview_version"] != 1:
        _abort("activity_draft_supersession_conflict")
    return apply_desktop_activity_draft_source_supersession_v1(
        data_space_path, context, attempt["trusted_preview"],
        attempt["confirmation"], attempt["committed_at_utc"],
    )


def resume_desktop_activity_draft_mixed_source_retirement_v1(
    data_space_path: str | Path,
    context_value: Any,
    challenge_ref: str,
) -> dict[str, Any]:
    context = _context(context_value)
    if not isinstance(challenge_ref, str) or SUPERSESSION_CHALLENGE.fullmatch(challenge_ref) is None:
        _abort("activity_draft_input_invalid")
    area = _area(data_space_path, create=False)
    attempts_path = area / SUPERSESSION_ATTEMPTS_NAME
    if not attempts_path.exists():
        _abort("activity_draft_supersession_not_found")
    path = _strict_owner_directory(attempts_path) / (challenge_ref + ".json")
    if not path.exists():
        _abort("activity_draft_supersession_not_found")
    attempt = _read_supersession_attempt(path, context)
    if attempt["trusted_preview"]["activity_draft_source_supersession_preview_version"] != 2:
        _abort("activity_draft_supersession_conflict")
    return apply_desktop_activity_draft_mixed_source_retirement_v1(
        data_space_path, context, attempt["trusted_preview"],
        attempt["confirmation"], attempt["committed_at_utc"],
    )


def read_desktop_activity_draft_supersession_state_v1(
    data_space_path: str | Path,
    context_value: Any,
) -> dict[str, Any]:
    context = _context(context_value)
    data_space = _directory(Path(data_space_path))
    area_path = data_space / AREA_NAME
    if not area_path.exists():
        public = {
            "activity_draft_supersession_state_version": 1, "status": "absent",
            "active_generation_present": False, "supersession_command_count": 0,
            "superseded_draft_count": 0, "pending_attempt_count": 0,
            "legacy_writer_blocked": False, "original_draft_files_rewritten": False,
            "schema201_canonical_write": False, "schema401_activity_write": False,
            "cash_posting_count": 0, "provider_access": False, "network_access": False,
            "path_exposed": False, "browser_internal_id_exposed": False,
            "fingerprint_exposed": False,
        }
        return {"public_state": public, "trusted_state": {"active_generation": None}}
    area = _directory(area_path)
    barrier = (area / LOCK_NAME).exists() and (area / LOCK_NAME).is_dir()
    if barrier:
        _validate_writer_barrier(area)
    active = _active_supersession_generation(area, context)
    pending = _pending_supersession_attempts(area, context, active)
    status = "recovery_required" if pending else "available" if active is not None else "recovery_required" if barrier else "absent"
    public = {
        "activity_draft_supersession_state_version": 1,
        "status": status,
        "active_generation_present": active is not None,
        "supersession_command_count": 0 if active is None else len(active["commands"]),
        "superseded_draft_count": 0 if active is None else len(active["tombstones"]),
        "pending_attempt_count": len(pending),
        "legacy_writer_blocked": barrier,
        "original_draft_files_rewritten": False,
        "schema201_canonical_write": False,
        "schema401_activity_write": False,
        "cash_posting_count": 0,
        "provider_access": False,
        "network_access": False,
        "path_exposed": False,
        "browser_internal_id_exposed": False,
        "fingerprint_exposed": False,
    }
    return {
        "public_state": public,
        "trusted_state": {
            "active_generation": active,
            "pending_challenge_refs": [item["challenge_ref"] for item in pending],
        },
    }


def _profile_ref(context: DesktopProductAssetActivityContextV1, label: str, is_standard: bool) -> str:
    material = {
        "context_fingerprint": _context_fingerprint(context),
        "profile_slot": "standard" if is_standard else "label:" + label,
    }
    return "amp_" + _fingerprint(material)[:32]


def _profile_mapping_entries(value: Any, target_prefix: str) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        _abort("activity_draft_input_invalid")
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"source_key", "target_id"}:
            _abort("activity_draft_input_invalid")
        source_key = _safe_text(item.get("source_key"), maximum=200)
        target_id = _safe_text(item.get("target_id"), maximum=80)
        if not target_id.startswith(target_prefix) or REFERENCE.fullmatch(target_id) is None:
            _abort("activity_draft_input_invalid")
        rows.append({"source_key": source_key, "target_id": target_id})
    rows.sort(key=lambda item: item["source_key"])
    if len({item["source_key"] for item in rows}) != len(rows):
        _abort("activity_draft_input_invalid")
    return rows


def _seal_profile(profile: dict[str, Any]) -> dict[str, Any]:
    body = dict(profile)
    body.pop("profile_fingerprint", None)
    body["profile_fingerprint"] = _fingerprint(body)
    return body


def _profile_path(area: Path, profile_ref: str) -> Path:
    if not isinstance(profile_ref, str) or PROFILE_REF.fullmatch(profile_ref) is None:
        _abort("activity_draft_input_invalid")
    profiles = _directory(area / PROFILES_NAME, create=True)
    return profiles / (profile_ref + ".json")


def _validate_profile(value: Any, context: DesktopProductAssetActivityContextV1) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != PROFILE_KEYS:
        _abort("activity_draft_storage_invalid")
    body = dict(value)
    fingerprint = body.pop("profile_fingerprint", None)
    try:
        label = _safe_text(value.get("profile_label"), maximum=100)
        default_portfolio = _safe_text(value.get("default_portfolio_id"), maximum=80)
        default_account = _safe_text(value.get("default_account_id"), maximum=80)
        portfolios = _profile_mapping_entries(value.get("portfolio_mappings"), "ptf_")
        accounts = _profile_mapping_entries(value.get("account_mappings"), "acc_")
        assets = _profile_mapping_entries(value.get("asset_mappings"), "ast_")
        created = _utc(value.get("created_at_utc"))
        updated = _utc(value.get("updated_at_utc"))
    except DesktopActivityDraftV1Error:
        _abort("activity_draft_storage_invalid")
    if (
        value.get("activity_mapping_profile_version") != 1
        or value.get("context_fingerprint") != _context_fingerprint(context)
        or not isinstance(value.get("is_standard"), bool)
        or value.get("profile_ref") != _profile_ref(context, label, value["is_standard"])
        or not default_portfolio.startswith("ptf_")
        or REFERENCE.fullmatch(default_portfolio) is None
        or not default_account.startswith("acc_")
        or REFERENCE.fullmatch(default_account) is None
        or value.get("portfolio_mappings") != portfolios
        or value.get("account_mappings") != accounts
        or value.get("asset_mappings") != assets
        or isinstance(value.get("revision"), bool)
        or not isinstance(value.get("revision"), int)
        or value["revision"] < 1
        or created > updated
        or any(character in label for character in "@/\\")
        or fingerprint != _fingerprint(body)
    ):
        _abort("activity_draft_storage_invalid")
    return value


def _read_profile(area: Path, context: DesktopProductAssetActivityContextV1, profile_ref: str) -> dict[str, Any]:
    if not isinstance(profile_ref, str) or PROFILE_REF.fullmatch(profile_ref) is None:
        _abort("activity_draft_input_invalid")
    profiles_path = area / PROFILES_NAME
    if not profiles_path.exists():
        _abort("activity_draft_not_found")
    path = _directory(profiles_path) / (profile_ref + ".json")
    if not path.exists():
        _abort("activity_draft_not_found")
    path = _file(path)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _abort("activity_draft_storage_invalid")
    if raw != _canonical(value) + b"\n":
        _abort("activity_draft_storage_invalid")
    return _validate_profile(value, context)


def _public_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "activity_mapping_profile_public_version": 1,
        "status": "available",
        "profile_label": profile["profile_label"],
        "is_standard": profile["is_standard"],
        "revision": profile["revision"],
        "portfolio_mapping_count": len(profile["portfolio_mappings"]),
        "account_mapping_count": len(profile["account_mappings"]),
        "asset_mapping_count": len(profile["asset_mappings"]),
        "updated_at_utc": profile["updated_at_utc"],
        "context_bound": True,
        "canonical_write": False,
        "path_exposed": False,
        "browser_internal_id_exposed": False,
        "fingerprint_exposed": False,
    }


def save_desktop_activity_mapping_profile_v1(
    data_space_path: str | Path,
    context_value: Any,
    profile_label: str,
    is_standard: bool,
    default_portfolio_id: str,
    default_account_id: str,
    portfolio_mappings: list[Mapping[str, Any]],
    account_mappings: list[Mapping[str, Any]],
    asset_mappings: list[Mapping[str, Any]],
    saved_at_utc: str,
) -> dict[str, Any]:
    context = _context(context_value)
    saved = _utc(saved_at_utc)
    label = _safe_text(profile_label, maximum=100)
    if not isinstance(is_standard, bool) or any(character in label for character in "@/\\"):
        _abort("activity_draft_input_invalid")
    default_portfolio = _safe_text(default_portfolio_id, maximum=80)
    default_account = _safe_text(default_account_id, maximum=80)
    if (
        not default_portfolio.startswith("ptf_")
        or REFERENCE.fullmatch(default_portfolio) is None
        or not default_account.startswith("acc_")
        or REFERENCE.fullmatch(default_account) is None
    ):
        _abort("activity_draft_input_invalid")
    portfolios = _profile_mapping_entries(portfolio_mappings, "ptf_")
    accounts = _profile_mapping_entries(account_mappings, "acc_")
    assets = _profile_mapping_entries(asset_mappings, "ast_")
    profile_ref = _profile_ref(context, label, is_standard)
    area = _area(data_space_path)
    with _DraftWriterLockV1(area):
        _ensure_no_pending_supersession(area, context)
        path = _profile_path(area, profile_ref)
        if path.exists():
            current = _read_profile(area, context, profile_ref)
            if saved < current["updated_at_utc"]:
                _abort("activity_draft_input_invalid")
            revision = current["revision"] + 1
            created = current["created_at_utc"]
        else:
            revision = 1
            created = saved
        profile = {
            "activity_mapping_profile_version": 1,
            "profile_ref": profile_ref,
            "context_fingerprint": _context_fingerprint(context),
            "profile_label": label,
            "is_standard": is_standard,
            "revision": revision,
            "default_portfolio_id": default_portfolio,
            "default_account_id": default_account,
            "portfolio_mappings": portfolios,
            "account_mappings": accounts,
            "asset_mappings": assets,
            "created_at_utc": created,
            "updated_at_utc": saved,
        }
        sealed = _seal_profile(profile)
        content = _canonical(sealed) + b"\n"
        if path.exists():
            _replace(path, content)
        else:
            _write_new(path, content)
    return {"public_profile": _public_profile(sealed), "trusted_profile": sealed}


def read_desktop_activity_mapping_profile_v1(
    data_space_path: str | Path,
    context_value: Any,
    profile_ref: str,
) -> dict[str, Any]:
    context = _context(context_value)
    profile = _read_profile(_area(data_space_path, create=False), context, profile_ref)
    return {"public_profile": _public_profile(profile), "trusted_profile": profile}


def list_desktop_activity_mapping_profiles_v1(
    data_space_path: str | Path,
    context_value: Any,
) -> dict[str, Any]:
    context = _context(context_value)
    data_space = _directory(Path(data_space_path))
    area_path = data_space / AREA_NAME
    profiles_path = area_path / PROFILES_NAME
    rows: list[tuple[dict[str, Any], str]] = []
    if not area_path.exists() or not profiles_path.exists():
        return {
            "public_list": {
                "activity_mapping_profile_list_version": 1, "status": "available",
                "profile_count": 0, "profiles": [], "canonical_write": False,
                "path_exposed": False, "browser_internal_id_exposed": False,
                "fingerprint_exposed": False,
            },
            "trusted_list": {"profile_refs": []},
        }
    area = _directory(area_path)
    profiles = _directory(profiles_path)
    for path in sorted(profiles.glob("amp_*.json")):
        if path.is_symlink():
            _abort("activity_draft_storage_invalid")
        profile = _read_profile(area, context, path.stem)
        rows.append((_public_profile(profile), profile["profile_ref"]))
    rows.sort(key=lambda item: (not item[0]["is_standard"], item[0]["profile_label"], item[1]))
    return {
        "public_list": {
            "activity_mapping_profile_list_version": 1,
            "status": "available",
            "profile_count": len(rows),
            "profiles": [item[0] for item in rows],
            "canonical_write": False,
            "path_exposed": False,
            "browser_internal_id_exposed": False,
            "fingerprint_exposed": False,
        },
        "trusted_list": {"profile_refs": [item[1] for item in rows]},
    }


def list_desktop_activity_drafts_v1(
    data_space_path: str | Path,
    context_value: Any,
) -> dict[str, Any]:
    context = _context(context_value)
    with _verified_directories():
        return _list_drafts(context, Path(data_space_path))


def _list_drafts(context: DesktopProductAssetActivityContextV1, data_space_path: Path) -> dict[str, Any]:
    data_space = _directory(data_space_path)
    area_path = data_space / AREA_NAME
    drafts_path = area_path / DRAFTS_NAME
    if not area_path.exists() or not drafts_path.exists():
        return {
            "public_list": {
                "activity_draft_list_version": 1, "status": "available",
                "draft_count": 0, "drafts": [], "path_exposed": False,
                "browser_internal_id_exposed": False, "provider_access": False,
                "network_access": False, "canonical_write": False,
            },
            "trusted_list": {"draft_refs": [], "source_fingerprints": [], "source_adapter_ids": [], "created_at_utc": [], "committed_voided_at_utc": []},
        }
    area = _directory(area_path)
    drafts = _directory(drafts_path)
    supersessions, _ = _supersession_index(area, context)
    public_rows = []
    trusted_refs = []
    trusted_source_fingerprints = []
    # Die Kennung des Auszugsadapters je Entwurf. Die Wiederaufnahme zeigt sie je
    # Lauf an und las dafuer bisher je Lauf einen Entwurf einzeln nach - jeder
    # Einzelabruf prueft den ganzen Abloesestand und kostete spuerbar Zeit. Die Liste hat den Entwurf ohnehin in der Hand.
    trusted_source_adapter_ids = []
    # Je Entwurf: wann er entstand, und - wenn er gebucht ist - ob und wann seine Buchung storniert wurde (#509). Die Uebersicht
    # der Reward-Laeufe zaehlt eine stornierte Buchung sonst weiter als gebucht. Die Stornos werden nur gelesen, wenn es
    # gebuchte Entwuerfe gibt.
    trusted_created = []
    trusted_voided = []
    voided_refs: dict[str, str] | None = None
    for path in sorted(drafts.glob("adt_*.json")):
        if path.is_symlink():
            _abort("activity_draft_storage_invalid")
        draft_ref = path.stem
        draft = _read(area, context, draft_ref)
        supersession = supersessions.get(draft_ref)
        if supersession is not None and supersession["draft_fingerprint"] != draft["draft_fingerprint"]:
            _abort("activity_draft_storage_invalid")
        public_rows.append(_public(draft, supersession))
        trusted_refs.append(draft_ref)
        source_binding = draft.get("source_binding")
        trusted_source_fingerprints.append(
            source_binding.get("source_fingerprint") if isinstance(source_binding, dict) else None
        )
        auxiliary = draft.get("source_auxiliary")
        evidence = auxiliary.get("valuation_evidence") if isinstance(auxiliary, dict) else None
        adapter_id = evidence.get("adapter_id") if isinstance(evidence, dict) else None
        trusted_source_adapter_ids.append(adapter_id if isinstance(adapter_id, str) else None)
        trusted_created.append(draft.get("created_at_utc") if isinstance(draft.get("created_at_utc"), str) else None)
        voided_at = None
        event_ref = draft.get("event", {}).get("event_ref") if isinstance(draft.get("event"), dict) else None
        if draft.get("draft_state") == "committed" and isinstance(event_ref, str):
            if voided_refs is None:
                voided_refs = read_desktop_asset_activity_voided_event_refs_v1(data_space, context)
            voided_at = voided_refs.get(event_ref)
        trusted_voided.append(voided_at)
    return {
        "public_list": {
            "activity_draft_list_version": 1,
            "status": "available",
            "draft_count": len(public_rows),
            "drafts": public_rows,
            "path_exposed": False,
            "browser_internal_id_exposed": False,
            "provider_access": False,
            "network_access": False,
            "canonical_write": False,
        },
        "trusted_list": {
            "draft_refs": trusted_refs,
            "source_fingerprints": trusted_source_fingerprints,
            "source_adapter_ids": trusted_source_adapter_ids,
            "created_at_utc": trusted_created,
            "committed_voided_at_utc": trusted_voided,
        },
    }


__all__ = [
    "DesktopActivityDraftV1Error",
    "apply_desktop_activity_draft_mixed_source_retirement_v1",
    "apply_desktop_activity_draft_source_supersession_v1",
    "apply_desktop_activity_draft_v1",
    "apply_confirmed_reward_valuation_evidence_v1",
    "bind_desktop_activity_draft_fifo_order_evidence_v1",
    "bind_desktop_activity_draft_fifo_order_group_v1",
    "build_desktop_activity_draft_confirmation_v1",
    "build_desktop_activity_draft_recovery_confirmation_v2",
    "recover_desktop_activity_draft_v2",
    "build_desktop_activity_draft_mixed_source_retirement_confirmation_v1",
    "build_desktop_activity_draft_source_supersession_confirmation_v1",
    "create_desktop_activity_draft_v1",
    "create_or_reuse_tolerant_csv_activity_draft_v1",
    "shift_desktop_activity_draft_past_booked_second_v1",
    "desktop_activity_draft_v1_error_codes",
    "list_desktop_activity_drafts_v1",
    "list_desktop_activity_mapping_profiles_v1",
    "preview_desktop_activity_draft_mixed_source_retirement_v1",
    "preview_desktop_activity_draft_source_supersession_v1",
    "read_desktop_activity_draft_supersession_state_v1",
    "read_desktop_activity_draft_v1",
    "read_desktop_activity_mapping_profile_v1",
    "resolve_desktop_activity_draft_unclassified_fee_v1",
    "resume_desktop_activity_draft_mixed_source_retirement_v1",
    "resume_desktop_activity_draft_source_supersession_v1",
    "resume_desktop_activity_draft_v1",
    "save_desktop_activity_mapping_profile_v1",
    "update_desktop_activity_draft_v1",
    "validate_desktop_activity_draft_v1",
]
