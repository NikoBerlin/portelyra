"""Owner-local, context-bound Statement mapping profiles.

Profiles contain private source tuple keys and canonical target identities.  They are
trusted-process artifacts only; public projections expose counts and opaque handles.
Every revision is immutable and writes are serialized under an owner-only lock.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterator, Mapping

from migrations.reference.statement_import_mapping_v1 import StatementImportMappingV1Error

_ID = {
    "tenant_id": re.compile(r"^ten_[a-f0-9]{16,64}$"),
    "user_id": re.compile(r"^usr_[a-f0-9]{16,64}$"),
    "data_space_id": re.compile(r"^sbx_[a-f0-9]{16,64}$"),
    "target_asset_id": re.compile(r"^ast_[a-f0-9]{16,64}$"),
    "target_account_id": re.compile(r"^acc_[a-f0-9]{16,64}$"),
}
_PROFILE = re.compile(r"^smp_[a-f0-9]{32}$")
_ADAPTER = re.compile(r"^[a-z][a-z0-9_]{7,80}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_TEXT = re.compile(r"^[^\x00\r\n]{1,200}$")


class StatementImportMappingProfileV1Error(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise StatementImportMappingProfileV1Error(code)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _text(value: Any, maximum: int = 200) -> str:
    if not isinstance(value, str) or value != value.strip() or len(value) > maximum or _TEXT.fullmatch(value) is None:
        _abort("statement_mapping_profile_input_invalid")
    return value


@dataclass(frozen=True)
class StatementMappingProfileContextV1:
    tenant_id: str
    user_id: str
    data_space_id: str

    def __post_init__(self) -> None:
        for key, value in (("tenant_id", self.tenant_id), ("user_id", self.user_id), ("data_space_id", self.data_space_id)):
            if not isinstance(value, str) or _ID[key].fullmatch(value) is None:
                _abort("statement_mapping_profile_context_invalid")

    @property
    def fingerprint(self) -> str:
        return _fingerprint({"tenant_id": self.tenant_id, "user_id": self.user_id, "data_space_id": self.data_space_id})


def _root(data_space: Path) -> Path:
    raw = Path(data_space)
    if raw.is_symlink():
        _abort("statement_mapping_profile_storage_invalid")
    try:
        base = raw.resolve(strict=True)
    except OSError:
        _abort("statement_mapping_profile_storage_invalid")
    if not base.is_dir() or base.stat().st_uid != os.getuid():
        _abort("statement_mapping_profile_storage_invalid")
    root = base / "statement-import" / "mapping-profiles-v1"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    for path in (base / "statement-import", root):
        if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid():
            _abort("statement_mapping_profile_storage_invalid")
        path.chmod(0o700)
    return root


@contextmanager
def _lock(root: Path) -> Iterator[None]:
    path = root / ".writer.lock"
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb") as handle:
            payload = handle.read(4_000_001)
        if len(payload) > 4_000_000:
            _abort("statement_mapping_profile_storage_invalid")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _abort("statement_mapping_profile_storage_invalid")
    if not isinstance(value, dict):
        _abort("statement_mapping_profile_storage_invalid")
    return value


def _mapping_rows(rows: Any, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or (not rows and not allow_empty):
        _abort("statement_mapping_profile_input_invalid")
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    required = {"source_asset_key", "source_account_key", "event_type", "disposition", "target_asset_id", "target_account_id"}
    for raw in rows:
        if not isinstance(raw, Mapping) or set(raw) != required or raw.get("disposition") not in {"map", "defer"}:
            _abort("statement_mapping_profile_input_invalid")
        key = (_text(raw.get("source_asset_key")), _text(raw.get("source_account_key")), _text(raw.get("event_type")))
        if key in seen:
            _abort("statement_mapping_profile_duplicate_invalid")
        seen.add(key)
        asset = raw.get("target_asset_id"); account = raw.get("target_account_id")
        if raw["disposition"] == "map":
            if not isinstance(asset, str) or _ID["target_asset_id"].fullmatch(asset) is None or not isinstance(account, str) or _ID["target_account_id"].fullmatch(account) is None:
                _abort("statement_mapping_profile_target_invalid")
        elif asset is not None or account is not None:
            _abort("statement_mapping_profile_target_invalid")
        result.append({"source_asset_key": key[0], "source_account_key": key[1], "event_type": key[2], "disposition": raw["disposition"], "target_asset_id": asset, "target_account_id": account})
    return sorted(result, key=lambda row: (row["source_asset_key"], row["source_account_key"], row["event_type"]))


def _profile_dir(root: Path, profile_ref: str) -> Path:
    if not isinstance(profile_ref, str) or _PROFILE.fullmatch(profile_ref) is None:
        _abort("statement_mapping_profile_ref_invalid")
    path = root / profile_ref
    if path.exists() and (path.is_symlink() or not path.is_dir()):
        _abort("statement_mapping_profile_storage_invalid")
    return path


def _revisions(path: Path) -> list[Path]:
    return sorted(item for item in path.glob("revision-*.json") if item.is_file() and not item.is_symlink()) if path.is_dir() else []


def _validate_profile(value: Mapping[str, Any], context: StatementMappingProfileContextV1) -> dict[str, Any]:
    expected = {"statement_mapping_profile_version", "profile_ref", "context_fingerprint", "adapter_id", "adapter_version", "profile_label", "revision", "mapping_rows", "created_at_utc", "profile_fingerprint"}
    if set(value) != expected or value.get("statement_mapping_profile_version") != 1 or value.get("context_fingerprint") != context.fingerprint:
        _abort("statement_mapping_profile_context_invalid")
    body = dict(value); sealed = body.pop("profile_fingerprint", None)
    if not isinstance(sealed, str) or sealed != _fingerprint(body):
        _abort("statement_mapping_profile_storage_invalid")
    if (
        not isinstance(body.get("profile_ref"), str) or _PROFILE.fullmatch(body["profile_ref"]) is None
        or not isinstance(body.get("adapter_id"), str) or _ADAPTER.fullmatch(body["adapter_id"]) is None
        or not isinstance(body.get("adapter_version"), str) or _VERSION.fullmatch(body["adapter_version"]) is None
        or isinstance(body.get("revision"), bool) or not isinstance(body.get("revision"), int) or body["revision"] < 1
    ):
        _abort("statement_mapping_profile_storage_invalid")
    try:
        _text(body.get("profile_label"), 100)
    except StatementImportMappingProfileV1Error:
        _abort("statement_mapping_profile_storage_invalid")
    try:
        timestamp = datetime.fromisoformat(body["created_at_utc"].replace("Z", "+00:00"))
        if timestamp.tzinfo != timezone.utc or not body["created_at_utc"].endswith("Z"):
            raise ValueError
    except (AttributeError, KeyError, ValueError):
        _abort("statement_mapping_profile_storage_invalid")
    try:
        normalized_rows = _mapping_rows(body.get("mapping_rows"))
    except StatementImportMappingProfileV1Error:
        _abort("statement_mapping_profile_storage_invalid")
    if normalized_rows != body["mapping_rows"]:
        _abort("statement_mapping_profile_storage_invalid")
    body["profile_fingerprint"] = sealed
    return body


def save_statement_mapping_profile_v1(data_space: Path, context: StatementMappingProfileContextV1, *, adapter_id: str, adapter_version: str, profile_label: str, mapping_rows: list[Mapping[str, Any]], created_at_utc: str, profile_ref: str | None = None, expected_revision: int | None = None) -> dict[str, Any]:
    if not isinstance(adapter_id, str) or _ADAPTER.fullmatch(adapter_id) is None or not isinstance(adapter_version, str) or _VERSION.fullmatch(adapter_version) is None:
        _abort("statement_mapping_profile_input_invalid")
    label = _text(profile_label, 100)
    try:
        parsed = datetime.fromisoformat(created_at_utc.replace("Z", "+00:00"))
        if parsed.tzinfo != timezone.utc or not created_at_utc.endswith("Z"):
            raise ValueError
    except (AttributeError, ValueError):
        _abort("statement_mapping_profile_input_invalid")
    mappings = _mapping_rows(mapping_rows); root = _root(data_space)
    with _lock(root):
        if profile_ref is None:
            seed = {"context": context.fingerprint, "adapter_id": adapter_id, "adapter_version": adapter_version, "label": label}
            profile_ref = "smp_" + _fingerprint(seed)[:32]
        directory = _profile_dir(root, profile_ref); existing = _revisions(directory)
        revision = len(existing) + 1
        if existing and expected_revision is None:
            _abort("statement_mapping_profile_revision_conflict")
        if expected_revision is not None and (isinstance(expected_revision, bool) or expected_revision != revision - 1):
            _abort("statement_mapping_profile_revision_conflict")
        if existing:
            previous = _validate_profile(_read_json(existing[-1]), context)
            if previous["adapter_id"] != adapter_id or previous["adapter_version"] != adapter_version:
                _abort("statement_mapping_profile_adapter_mismatch")
        directory.mkdir(mode=0o700, exist_ok=True); directory.chmod(0o700)
        body = {"statement_mapping_profile_version": 1, "profile_ref": profile_ref, "context_fingerprint": context.fingerprint, "adapter_id": adapter_id, "adapter_version": adapter_version, "profile_label": label, "revision": revision, "mapping_rows": mappings, "created_at_utc": created_at_utc}
        profile = {**body, "profile_fingerprint": _fingerprint(body)}
        target = directory / f"revision-{revision:08d}.json"
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical(profile) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    return {"status": "statement_mapping_profile_saved", "profile_ref": profile_ref, "revision": revision, "mapping_count": len(mappings), "profile_fingerprint": profile["profile_fingerprint"], "canonical_write": False, "provider_access": False, "network_access": False}


def read_statement_mapping_profile_v1(data_space: Path, context: StatementMappingProfileContextV1, profile_ref: str) -> dict[str, Any]:
    directory = _profile_dir(_root(data_space), profile_ref); revisions = _revisions(directory)
    if not revisions:
        _abort("statement_mapping_profile_not_found")
    return _validate_profile(_read_json(revisions[-1]), context)


def list_statement_mapping_profiles_v1(data_space: Path, context: StatementMappingProfileContextV1, *, adapter_id: str, adapter_version: str) -> dict[str, Any]:
    if not isinstance(adapter_id, str) or _ADAPTER.fullmatch(adapter_id) is None or not isinstance(adapter_version, str) or _VERSION.fullmatch(adapter_version) is None:
        _abort("statement_mapping_profile_input_invalid")
    root = _root(data_space); profiles = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir() and _PROFILE.fullmatch(path.name)):
        value = read_statement_mapping_profile_v1(data_space, context, directory.name)
        if value["adapter_id"] == adapter_id and value["adapter_version"] == adapter_version:
            profiles.append({"profile_ref": value["profile_ref"], "profile_label": value["profile_label"], "revision": value["revision"], "mapping_count": len(value["mapping_rows"])})
    return {"status": "statement_mapping_profiles_available", "profiles": profiles, "canonical_write": False, "provider_access": False, "network_access": False}


def preview_statement_mapping_profile_v1(profile: Mapping[str, Any], current_rows: list[Mapping[str, Any]], catalog_target_ids: Mapping[str, set[str]]) -> dict[str, Any]:
    stored = _mapping_rows(profile.get("mapping_rows")); current = _mapping_rows(current_rows, allow_empty=True)
    stored_by = {(r["source_asset_key"], r["source_account_key"], r["event_type"]): r for r in stored}
    current_by = {(r["source_asset_key"], r["source_account_key"], r["event_type"]): r for r in current}
    keys = sorted(set(stored_by) | set(current_by)); changes = []
    stale = 0
    assets = catalog_target_ids.get("asset_ids", set()); accounts = catalog_target_ids.get("account_ids", set())
    if not isinstance(assets, set) or not isinstance(accounts, set):
        _abort("statement_mapping_profile_input_invalid")
    for key in keys:
        before = current_by.get(key); after = stored_by.get(key)
        state = "unchanged" if before == after else "added" if before is None else "removed" if after is None else "changed"
        target_status = "not_applicable"
        if after is not None and after["disposition"] == "map":
            target_status = "available" if after["target_asset_id"] in assets and after["target_account_id"] in accounts else "stale"
            stale += target_status == "stale"
        changes.append({"source_asset_key": key[0], "source_account_key": key[1], "event_type": key[2], "change_state": state, "target_status": target_status})
    return {"status": "statement_mapping_profile_preview", "changes": changes, "changed_mapping_count": sum(row["change_state"] != "unchanged" for row in changes), "stale_target_count": stale, "applicable": stale == 0, "canonical_write": False, "provider_access": False, "network_access": False}


__all__ = ["StatementImportMappingProfileV1Error", "StatementMappingProfileContextV1", "list_statement_mapping_profiles_v1", "preview_statement_mapping_profile_v1", "read_statement_mapping_profile_v1", "save_statement_mapping_profile_v1"]
