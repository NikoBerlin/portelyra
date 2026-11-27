"""Owner-local one-read Statement source-profile UAT boundary v1.

No operation in this module is called by the normal Statement adapter runner. A
private source path can enter only through an injected local selection provider;
it is never returned, persisted, printed, or accepted as a CLI argument.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any


MAX_BYTES = 32_000_000
AUTHORIZATION_SECONDS = 300
ROOT = Path(__file__).resolve().parents[2]
_SHA256 = re.compile(r"[0-9a-f]{64}")
_NONCE = re.compile(r"[0-9a-f]{32}")
FAILURE_CODES = frozenset(
    {
        "statement_import_owner_uat_authorization_expired",
        "statement_import_owner_uat_authorization_invalid",
        "statement_import_owner_uat_boundary_failed",
        "statement_import_owner_uat_evidence_exists",
        "statement_import_owner_uat_evidence_invalid",
        "statement_import_owner_uat_evidence_recovery_required",
        "statement_import_owner_uat_execution_not_authorized",
        "statement_import_owner_uat_input_invalid",
        "statement_import_owner_uat_profile_invalid",
        "statement_import_owner_uat_review_cancelled",
        "statement_import_owner_uat_review_invalid",
        "statement_import_owner_uat_selection_cancelled",
        "statement_import_owner_uat_source_bundle_invalid",
        "statement_import_owner_uat_source_changed",
        "statement_import_owner_uat_source_invalid",
    }
)


class StatementImportOwnerUATError(RuntimeError):
    """Stable failure without private source detail."""

    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("statement_import_owner_uat_error_code_unregistered")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class _SourceSnapshot:
    path: Path
    selection_binding_sha256: str
    device: int
    inode: int
    size: int
    modified_ns: int
    mode: int
    uid: int


def _abort(code: str) -> None:
    raise StatementImportOwnerUATError(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        _abort("statement_import_owner_uat_evidence_invalid")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _utc_text(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        _abort("statement_import_owner_uat_boundary_failed")
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        _abort("statement_import_owner_uat_boundary_failed")
    return normalized.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _abort("statement_import_owner_uat_authorization_invalid")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort("statement_import_owner_uat_authorization_invalid")
    return parsed


def _open_directory_chain(path: Path) -> int:
    if not path.is_absolute() or path == Path(os.sep):
        if path == Path(os.sep):
            try:
                return os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            except OSError:
                _abort("statement_import_owner_uat_evidence_invalid")
        _abort("statement_import_owner_uat_evidence_invalid")
    descriptor: int | None = None
    try:
        descriptor = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for component in path.parts[1:]:
            if component in {"", ".", ".."}:
                raise OSError("invalid_component")
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        _abort("statement_import_owner_uat_evidence_invalid")


def _validate_owner_directory(path: Path, *, create: bool) -> None:
    if not path.is_absolute() or path == Path(os.sep):
        _abort("statement_import_owner_uat_evidence_invalid")
    parent_descriptor: int | None = None
    descriptor: int | None = None
    try:
        if create:
            parent_descriptor = _open_directory_chain(path.parent)
            os.mkdir(path.name, 0o700, dir_fd=parent_descriptor)
        descriptor = _open_directory_chain(path)
        info = os.fstat(descriptor)
    except FileExistsError:
        _abort("statement_import_owner_uat_evidence_exists")
    except StatementImportOwnerUATError:
        raise
    except OSError:
        _abort("statement_import_owner_uat_evidence_invalid")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        _abort("statement_import_owner_uat_evidence_invalid")


def _write_once(path: Path, value: dict[str, Any]) -> bytes:
    payload = _canonical(value) + b"\n"
    if not 1 <= len(payload) <= MAX_BYTES:
        _abort("statement_import_owner_uat_evidence_invalid")
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(path, flags, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written < 1:
                raise OSError("short_write")
            offset += written
        os.fsync(descriptor)
    except FileExistsError:
        _abort("statement_import_owner_uat_evidence_exists")
    except StatementImportOwnerUATError:
        raise
    except OSError:
        _abort("statement_import_owner_uat_evidence_invalid")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return payload


def _read_exact_json(path: Path) -> tuple[dict[str, Any], bytes]:
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(path, flags)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or not 0 < info.st_size <= MAX_BYTES
        ):
            _abort("statement_import_owner_uat_evidence_invalid")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                _abort("statement_import_owner_uat_evidence_invalid")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _abort("statement_import_owner_uat_evidence_invalid")
        raw = b"".join(chunks)
    except StatementImportOwnerUATError:
        raise
    except OSError:
        _abort("statement_import_owner_uat_evidence_invalid")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non_finite_json")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _abort("statement_import_owner_uat_evidence_invalid")
    if not isinstance(value, dict) or raw != _canonical(value) + b"\n":
        _abort("statement_import_owner_uat_evidence_invalid")
    return value, raw


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = child
    return value


def _fsync_directory(path: Path) -> None:
    descriptor: int | None = None
    try:
        descriptor = _open_directory_chain(path)
        os.fsync(descriptor)
    except StatementImportOwnerUATError:
        raise
    except OSError:
        _abort("statement_import_owner_uat_evidence_invalid")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _open_parent_chain(path: Path) -> tuple[int, str]:
    if not isinstance(path, Path) or not path.is_absolute() or path.name in {"", ".", ".."}:
        _abort("statement_import_owner_uat_input_invalid")
    parts = path.parts
    if not parts or parts[0] != os.sep or any(part in {"", ".", ".."} for part in parts[1:]):
        _abort("statement_import_owner_uat_input_invalid")
    descriptor: int | None = None
    try:
        descriptor = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        for component in parts[1:-1]:
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, parts[-1]
    except OSError:
        if descriptor is not None:
            os.close(descriptor)
        _abort("statement_import_owner_uat_source_invalid")


def _valid_source_stat(info: os.stat_result) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_nlink == 1
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == 0o600
        and 0 < info.st_size <= MAX_BYTES
    )


def _select_snapshot(path_value: Any, context_binding_sha256: str, profile_sha256: str) -> _SourceSnapshot:
    if not isinstance(path_value, (str, os.PathLike)):
        _abort("statement_import_owner_uat_input_invalid")
    path = Path(path_value)
    if path.suffix.lower() != ".csv":
        _abort("statement_import_owner_uat_source_invalid")
    parent, name = _open_parent_chain(path)
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except OSError:
        os.close(parent)
        _abort("statement_import_owner_uat_source_invalid")
    os.close(parent)
    if not _valid_source_stat(info):
        _abort("statement_import_owner_uat_source_invalid")
    binding = hashlib.sha256(
        _canonical(
            {
                "context_binding_sha256": context_binding_sha256,
                "device": info.st_dev,
                "inode": info.st_ino,
                "mode": stat.S_IMODE(info.st_mode),
                "modified_ns": info.st_mtime_ns,
                "profile_semantics_sha256": profile_sha256,
                "private_path": os.fspath(path),
                "size": info.st_size,
                "uid": info.st_uid,
            }
        )
    ).hexdigest()
    return _SourceSnapshot(
        path=path,
        selection_binding_sha256=binding,
        device=info.st_dev,
        inode=info.st_ino,
        size=info.st_size,
        modified_ns=info.st_mtime_ns,
        mode=stat.S_IMODE(info.st_mode),
        uid=info.st_uid,
    )


def _runtime_owner_directory(path: Path) -> None:
    descriptor: int | None = None
    try:
        descriptor = _open_directory_chain(path)
        info = os.fstat(descriptor)
    except StatementImportOwnerUATError:
        _abort("statement_import_owner_uat_input_invalid")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        _abort("statement_import_owner_uat_input_invalid")


def _read_runtime_registry(path: Path) -> dict[str, Any]:
    parent: int | None = None
    descriptor: int | None = None
    try:
        parent, name = _open_parent_chain(path)
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(name, flags, dir_fd=parent)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or not 1 < info.st_size <= 1_048_576
        ):
            raise OSError("runtime_registry_metadata")
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise OSError("runtime_registry_short_read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise OSError("runtime_registry_growth")
        raw = b"".join(chunks)
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non_finite_json")),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, StatementImportOwnerUATError):
        _abort("statement_import_owner_uat_input_invalid")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent is not None:
            os.close(parent)
    if not isinstance(value, dict):
        _abort("statement_import_owner_uat_input_invalid")
    return value


def derive_statement_import_owner_uat_runtime_v1(
    desktop_home: str | os.PathLike[str],
) -> tuple[Path, str]:
    """Derive the isolated evidence root and redacted binding from a trusted Desktop registry."""

    try:
        home = Path(desktop_home)
    except TypeError:
        _abort("statement_import_owner_uat_input_invalid")
    if not home.is_absolute() or home.name in {"", ".", ".."}:
        _abort("statement_import_owner_uat_input_invalid")
    _runtime_owner_directory(home)
    registry = _read_runtime_registry(home / "desktop-runtime.json")
    required = {
        "active_data_space_id",
        "contract_version",
        "created_at_utc",
        "data_spaces",
        "registry_revision",
        "runtime_mode",
        "tenant_id",
        "user_id",
    }
    id_patterns = {
        "tenant_id": re.compile(r"ten_[0-9a-f]{32}"),
        "user_id": re.compile(r"usr_[0-9a-f]{32}"),
        "active_data_space_id": re.compile(r"sbx_[0-9a-f]{32}"),
    }
    if (
        set(registry) != required
        or type(registry.get("contract_version")) is not int
        or registry["contract_version"] != 1
        or type(registry.get("registry_revision")) is not int
        or registry["registry_revision"] != 1
        or registry.get("runtime_mode") != "desktop_product"
        or any(
            not isinstance(registry.get(field), str)
            or pattern.fullmatch(registry[field]) is None
            for field, pattern in id_patterns.items()
        )
        or not isinstance(registry.get("created_at_utc"), str)
        or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", registry["created_at_utc"]) is None
        or not isinstance(registry.get("data_spaces"), list)
        or len(registry["data_spaces"]) != 1
    ):
        _abort("statement_import_owner_uat_input_invalid")
    try:
        if _utc_text(_parse_utc(registry["created_at_utc"])) != registry["created_at_utc"]:
            raise ValueError("created_at")
    except (ValueError, StatementImportOwnerUATError):
        _abort("statement_import_owner_uat_input_invalid")
    space = registry["data_spaces"][0]
    if (
        not isinstance(space, dict)
        or set(space) != {"created_at_utc", "data_space_id", "display_label", "status"}
        or space.get("data_space_id") != registry["active_data_space_id"]
        or space.get("created_at_utc") != registry["created_at_utc"]
        or space.get("status") != "active"
        or not isinstance(space.get("display_label"), str)
        or space["display_label"] != space["display_label"].strip()
        or not 1 <= len(space["display_label"].encode("utf-8")) <= 100
        or any(ord(character) < 32 for character in space["display_label"])
        or any(character in "@/\\" for character in space["display_label"])
    ):
        _abort("statement_import_owner_uat_input_invalid")
    from migrations.reference.desktop_protection_v1 import data_root_v1  # Passwortschutz (#535): eingehaengte Ansicht
    data_root = data_root_v1(home)
    data_space = data_root / registry["tenant_id"] / registry["user_id"] / registry["active_data_space_id"]
    for directory in (
        data_root,
        data_root / registry["tenant_id"],
        data_root / registry["tenant_id"] / registry["user_id"],
        data_space,
    ):
        _runtime_owner_directory(directory)
    binding = _fingerprint(
        {
            "active_data_space_id": registry["active_data_space_id"],
            "data_root": os.fspath(data_root),
            "registry_revision": 1,
            "runtime_mode": "desktop_product",
            "tenant_id": registry["tenant_id"],
            "user_id": registry["user_id"],
        }
    )
    return data_space / "statement_import_owner_uat_v1", binding


def _snapshot_matches(info: os.stat_result, snapshot: _SourceSnapshot) -> bool:
    return (
        _valid_source_stat(info)
        and info.st_dev == snapshot.device
        and info.st_ino == snapshot.inode
        and info.st_size == snapshot.size
        and info.st_mtime_ns == snapshot.modified_ns
        and stat.S_IMODE(info.st_mode) == snapshot.mode
        and info.st_uid == snapshot.uid
    )


def _secure_read_once(snapshot: _SourceSnapshot) -> bytes:
    parent, name = _open_parent_chain(snapshot.path)
    descriptor: int | None = None
    try:
        before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not _snapshot_matches(before, snapshot):
            _abort("statement_import_owner_uat_source_changed")
        flags = os.O_RDONLY | os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(name, flags, dir_fd=parent)
        opened = os.fstat(descriptor)
        if not _snapshot_matches(opened, snapshot):
            _abort("statement_import_owner_uat_source_changed")
        chunks: list[bytes] = []
        remaining = snapshot.size
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                _abort("statement_import_owner_uat_source_changed")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _abort("statement_import_owner_uat_source_changed")
        after = os.fstat(descriptor)
        if not _snapshot_matches(after, snapshot):
            _abort("statement_import_owner_uat_source_changed")
        return b"".join(chunks)
    except StatementImportOwnerUATError:
        raise
    except OSError:
        _abort("statement_import_owner_uat_source_invalid")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent)


__all__ = [
    "FAILURE_CODES",
    "StatementImportOwnerUATError",
    "derive_statement_import_owner_uat_runtime_v1",
]
