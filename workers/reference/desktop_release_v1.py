#!/usr/bin/env python3
"""Owner-only Desktop backup, restore, release and acceptance boundary v1."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import csv
import fcntl
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import tarfile
from typing import Any, Iterable

from workers.reference.desktop_release_source_closure_v1 import (
    DesktopReleaseSourceClosureError,
    PYTHON_ROOTS,
    validate_desktop_release_source_closure_v1,
)

DESKTOP_RELEASE_VERSION = 1
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
OPAQUE = {
    "tenant_id": re.compile(r"^ten_[a-f0-9]{32}$"),
    "user_id": re.compile(r"^usr_[a-f0-9]{32}$"),
    "data_space_id": re.compile(r"^sbx_[a-f0-9]{32}$"),
}
SHA = re.compile(r"^[a-f0-9]{64}$")
NONCE = re.compile(r"^lck_[a-f0-9]{32}$")
VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,119}$")
# Innerhalb des Datenraums ist ein fuehrender Punkt zulaessig: Arbeitsbereiche
# legen dort regulaer .context-, .lock- und .json-Dateien ab. Die Regel bleibt
# bewusst musterbasiert - eine Aufzaehlung einzelner Pfade ist genau der Grund,
# warum die Sicherung eines gewachsenen Datenraums zuvor abbrach.
SAFE_DATA_SEGMENT = re.compile(r"^[.]?[A-Za-z0-9_][A-Za-z0-9._-]{0,119}$")
# Rebuildbare Arbeitsverzeichnisse im Datenraum. Sie entstehen als
# TemporaryDirectory waehrend einer Vorschau und koennen nach einem
# abgebrochenen Prozess zurueckbleiben. Sie gehoeren nicht in eine Sicherung.
# Der Vermerk des Ursprungsorts (#493, data_space_relocation_v1) beschreibt den Ort, nicht den Bestand: nicht im Backup, nach jedem Restore
# setzt der Restore ihn neu (bind_restored_data_space_v1). Auch Abnahmepruefung und wiederholter Restore vergleichen ohne ihn.
TRANSIENT_SCRATCH_PREFIXES = (".native-asset-activity-preview-", "data-space-relocation-v1")
MAX_FILE_BYTES = 1_000_000_000
MAX_TOTAL_BYTES = 20_000_000_000
# Signatur eines Release (#486 Schritt 3, Festlegungen 16.11.2026): signiert ist release-manifest.json (jede Datei mit Pruefsumme), die
# Signatur liegt als eigene Datei daneben im Archiv. Ein Update prueft sie gegen die Vertrauensliste des INSTALLIERTEN Release.
RELEASE_SIGNATURE_NAME = "release-manifest.json.sig"
MAX_RELEASE_SIGNATURE_BYTES = 8192
MAX_RELEASE_ARCHIVE_BYTES = 500_000_000
# Steuer- und Auftragsdokumente bleiben klein und fest begrenzt.
MAX_JSON_BYTES = 4_000_000
# Das Backup-Manifest fuehrt eine Zeile je Eintrag und waechst deshalb mit dem
# Datenraum, nicht mit der Programmversion. Bei rund 350 Byte je Eintrag deckt
# dieses Limit ueber eine Million Eintraege ab; eine feste kleine Grenze
# machte einen gewachsenen Datenraum
# unlesbar. Die Datei ist owner-lokal und wurde unmittelbar
# zuvor selbst geschrieben.
MAX_BACKUP_MANIFEST_BYTES = 400_000_000

FAILURE_CODES = frozenset({
    "desktop_release_acceptance_artifact_missing",
    "desktop_release_acceptance_failed",
    "desktop_release_backup_conflict",
    "desktop_release_backup_integrity_invalid",
    "desktop_release_backup_source_changed",
    "desktop_release_backup_target_unprotected",
    "desktop_release_locked",
    "desktop_release_boundary_failed",
    "desktop_release_context_mismatch",
    "desktop_release_input_invalid",
    "desktop_release_manifest_invalid",
    "desktop_release_permissions_invalid",
    "desktop_release_release_conflict",
    "desktop_release_release_integrity_invalid",
    "desktop_release_restore_conflict",
    "desktop_release_restore_context_mismatch",
    "desktop_release_restore_target_not_empty",
    "desktop_release_restore_newer_version",
    "desktop_release_root_invalid",
    "desktop_release_session_invalid",
    "desktop_release_signature_invalid",
    "desktop_release_signature_missing",
    "desktop_release_signature_tool_missing",
    "desktop_release_signature_untrusted",
    "desktop_release_signing_copy_unconfirmed",
    "desktop_release_signing_declined",
    "desktop_release_signing_failed",
    "desktop_release_signing_key_not_loaded",
    "desktop_release_signing_key_untrusted",
    "desktop_release_signing_not_set_up",
    "desktop_release_signing_required_for_public_release",
    "desktop_release_update_conflict",
    "desktop_release_update_entry_untrusted",
    "desktop_release_source_unsettled",
    "desktop_release_sqlite_integrity_invalid",
    "desktop_release_transitive_source_closure_invalid",
    "desktop_release_symlink_rejected",
    "desktop_release_source_unreadable",
    "desktop_release_write_failed",
    "synthetic_desktop_release_failpoint",
})


class DesktopReleaseError(RuntimeError):
    def __init__(self, code: str, relative_path: str | None = None):
        if code not in FAILURE_CODES:
            raise ValueError("desktop_release_error_code_unregistered")
        self.code = code
        # Nur bei desktop_release_source_unreadable (#568): welcher Eintrag, relativ zum Datenraum (ohne Kennungen davor).
        self.relative_path = relative_path
        super().__init__(code)


def _abort(code: str) -> None:
    raise DesktopReleaseError(code)


def _abort_unreadable(shown: str) -> None:
    """Ein Eintrag des Datenbestands laesst sich nicht lesen (Ein-/Ausgabefehler, #568): etwa ein verschluesselter Ordner, dessen
    gocryptfs.diriv ein Neustart leer zurueckliess. Eigener Grund mit Pfad statt desktop_release_boundary_failed."""
    raise DesktopReleaseError("desktop_release_source_unreadable", shown)


def desktop_release_error_codes_v1() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        _abort("desktop_release_input_invalid")


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _fingerprint(value: Any) -> str:
    return _sha_bytes(_canonical(value))


def _utc(value: Any) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("desktop_release_input_invalid")
    try:
        if datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            _abort("desktop_release_input_invalid")
    except ValueError:
        _abort("desktop_release_input_invalid")
    return value


def _version(value: Any) -> str:
    if not isinstance(value, str) or VERSION.fullmatch(value) is None:
        _abort("desktop_release_input_invalid")
    return value


def _mode(path: Path) -> int:
    try:
        return stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)
    except Exception:
        _abort("desktop_release_root_invalid")


def _owner_only(path: Path) -> bool:
    try:
        metadata = path.stat(follow_symlinks=False)
        return stat.S_IMODE(metadata.st_mode) & 0o077 == 0 and metadata.st_uid == os.geteuid()
    except Exception:
        return False


def _assert_no_symlink_ancestry(path: Path, *, allow_missing_leaf: bool = False) -> None:
    if not isinstance(path, Path) or not path.is_absolute():
        _abort("desktop_release_root_invalid")
    current = path
    missing_seen = False
    while True:
        try:
            exists = current.exists()
            is_link = current.is_symlink()
        except Exception:
            _abort("desktop_release_root_invalid")
        if is_link:
            _abort("desktop_release_symlink_rejected")
        if not exists:
            missing_seen = True
        elif missing_seen and not allow_missing_leaf:
            _abort("desktop_release_root_invalid")
        if current.parent == current:
            break
        current = current.parent


def _existing_directory(path: Path, *, owner_only: bool = True) -> Path:
    _assert_no_symlink_ancestry(path)
    if not path.is_dir() or path.is_symlink():
        _abort("desktop_release_root_invalid")
    if owner_only and not _owner_only(path):
        _abort("desktop_release_permissions_invalid")
    try:
        return path.resolve(strict=True)
    except Exception:
        _abort("desktop_release_root_invalid")


SOURCE_PERMISSIONS = frozenset({"strict", "ignored"})


def _source_permissions(value: Any) -> bool:
    """True = Besitzer und Rechte der Quelle pruefen (Vorgabe); False = nur Lesbarkeit (ein vom Nutzer genannter Ordner, rc.410)."""
    if value not in SOURCE_PERMISSIONS:
        _abort("desktop_release_input_invalid")
    return value == "strict"


def _source_directory(path: Path, strict: bool) -> Path:
    """Ein Ordner, aus dem ein Backup gelesen wird.

    Streng (Backup-Ordner von Portelyra): eigener Besitz, keine Rechte fuer andere. Sonst (rc.410, Ordnerwahl beim Wiederherstellen):
    nur lesbar - ein Medium ohne Rechteverwaltung (FAT, exFAT, NTFS) zeigt jede Datei als fuer alle lesbar, ein Datentraeger von einem
    anderen Rechner traegt eine fremde Besitzerkennung, und der nur lesend eingehaengte verschluesselte Ordner erbt beides. Gelesen wird
    dort nur; fuer die Unversehrtheit buergen die Pruefsummen des Manifests, die Rechte im Home setzt das Zurueckspielen selbst.
    """
    if strict:
        return _existing_directory(path)
    resolved = _existing_directory(path, owner_only=False)
    if not os.access(resolved, os.R_OK | os.X_OK):
        _abort("desktop_release_permissions_invalid")
    return resolved


def _destination(path: Path) -> tuple[Path, Path]:
    if not isinstance(path, Path) or not path.is_absolute() or not SAFE_NAME.fullmatch(path.name):
        _abort("desktop_release_root_invalid")
    _assert_no_symlink_ancestry(path, allow_missing_leaf=True)
    parent = _existing_directory(path.parent, owner_only=False)
    if not os.access(parent, os.W_OK | os.X_OK):
        _abort("desktop_release_root_invalid")
    if _mode(parent) & 0o022 and not (_mode(parent) & stat.S_ISVTX):
        _abort("desktop_release_permissions_invalid")
    return parent / path.name, parent


def _overlap(left: Path, right: Path) -> bool:
    try:
        a = left.resolve(strict=False)
        b = right.resolve(strict=False)
    except Exception:
        _abort("desktop_release_root_invalid")
    return a == b or a in b.parents or b in a.parents


def _read_bytes(path: Path, *, maximum: int = MAX_FILE_BYTES, code: str = "desktop_release_manifest_invalid",
                unreadable: str | None = None) -> bytes:
    """`unreadable`: Anzeigepfad einer Quelldatei - ein Lesefehler des Systems meldet dann desktop_release_source_unreadable."""
    try:
        if path.is_symlink() or not path.is_file():
            _abort("desktop_release_symlink_rejected" if path.is_symlink() else code)
        size = path.stat(follow_symlinks=False).st_size
        if size < 0 or size > maximum:
            _abort(code)
        with path.open("rb") as handle:
            data = handle.read(maximum + 1)
        if len(data) != size or len(data) > maximum:
            _abort(code)
        return data
    except DesktopReleaseError:
        raise
    except OSError:
        if unreadable is not None:
            _abort_unreadable(unreadable)
        _abort(code)
    except Exception:
        _abort(code)


def _read_json(
    path: Path, *, canonical: bool = False, code: str = "desktop_release_manifest_invalid",
    maximum: int = MAX_JSON_BYTES,
) -> dict[str, Any]:
    raw = _read_bytes(path, maximum=maximum, code=code)
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except Exception:
        _abort(code)
    if not isinstance(value, dict):
        _abort(code)
    if canonical and raw != _canonical(value) + b"\n":
        _abort(code)
    return value


def _registry(path: Path) -> dict[str, Any]:
    value = _read_json(path, code="desktop_release_context_mismatch")
    expected = {
        "contract_version", "runtime_mode", "registry_revision", "tenant_id", "user_id",
        "active_data_space_id", "data_spaces", "created_at_utc",
    }
    if set(value) != expected or value.get("contract_version") != 1 or value.get("runtime_mode") != "desktop_product" or value.get("registry_revision") != 1:
        _abort("desktop_release_context_mismatch")
    if not OPAQUE["tenant_id"].fullmatch(value.get("tenant_id", "")) or not OPAQUE["user_id"].fullmatch(value.get("user_id", "")) or not OPAQUE["data_space_id"].fullmatch(value.get("active_data_space_id", "")):
        _abort("desktop_release_context_mismatch")
    _utc(value.get("created_at_utc"))
    spaces = value.get("data_spaces")
    if not isinstance(spaces, list) or len(spaces) != 1 or not isinstance(spaces[0], dict):
        _abort("desktop_release_context_mismatch")
    space = spaces[0]
    if set(space) != {"data_space_id", "display_label", "status", "created_at_utc"} or space.get("data_space_id") != value["active_data_space_id"] or space.get("status") != "active" or not isinstance(space.get("display_label"), str) or not 1 <= len(space["display_label"].encode("utf-8")) <= 100 or any(ord(ch) < 32 for ch in space["display_label"]):
        _abort("desktop_release_context_mismatch")
    _utc(space.get("created_at_utc"))
    return value


def _context(registry: dict[str, Any]) -> dict[str, str]:
    return {
        "tenant_id": registry["tenant_id"],
        "user_id": registry["user_id"],
        "data_space_id": registry["active_data_space_id"],
    }


def _process_start(pid: int) -> str | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        close = text.rfind(") ")
        fields = text[close + 2:].split(" ")
        return fields[19] if close >= 0 and len(fields) >= 20 and fields[19].isdigit() else None
    except Exception:
        return None


@dataclass(frozen=True)
class DesktopReleaseCapability:
    home: Path
    tenant_id: str
    user_id: str
    data_space_id: str
    session_nonce: str


def new_desktop_release_capability_v1(home: Path, session_nonce: str) -> DesktopReleaseCapability:
    root = _existing_directory(home)
    if not isinstance(session_nonce, str) or NONCE.fullmatch(session_nonce) is None:
        _abort("desktop_release_session_invalid")
    registry = _registry(root / "desktop-runtime.json")
    owner = _read_json(root / "desktop-session.lock" / "owner.json", code="desktop_release_session_invalid")
    if set(owner) != {"contract_version", "pid", "process_start", "nonce"} or owner.get("contract_version") != 1 or owner.get("nonce") != session_nonce or not isinstance(owner.get("pid"), int) or isinstance(owner.get("pid"), bool) or owner["pid"] < 1 or not isinstance(owner.get("process_start"), str) or _process_start(owner["pid"]) != owner["process_start"]:
        _abort("desktop_release_session_invalid")
    context = _context(registry)
    return DesktopReleaseCapability(root, context["tenant_id"], context["user_id"], context["data_space_id"], session_nonce)


def _validate_capability(capability: Any) -> tuple[Path, dict[str, Any]]:
    if not isinstance(capability, DesktopReleaseCapability):
        _abort("desktop_release_session_invalid")
    rebuilt = new_desktop_release_capability_v1(capability.home, capability.session_nonce)
    if rebuilt != capability:
        _abort("desktop_release_session_invalid")
    return capability.home, _registry(capability.home / "desktop-runtime.json")


def _data_root(home: Path) -> Path:
    """Der Datenbestand: ohne Passwortschutz <home>/data, mit Schutz die eingehaengte Ansicht (#535, rc.396). Gesperrt: Abbruch."""
    from migrations.reference.desktop_protection_v1 import DesktopProtectionV1Error, data_root_v1
    try:
        return data_root_v1(home)
    except DesktopProtectionV1Error as error:
        _abort("desktop_release_locked" if error.code == "desktop_protection_locked" else "desktop_release_root_invalid")
        raise


def _relative(home: Path, data_root: Path, path: Path) -> str:
    """Pfad im Backup: Der Datenbestand heisst immer data/..., auch wenn er (mit Passwortschutz) ausserhalb des Home haengt."""
    if path == data_root:
        return "data"
    try:
        return "data/" + path.relative_to(data_root).as_posix()
    except ValueError:
        return path.relative_to(home).as_posix()


def _source_path(home: Path, relative: str) -> Path:
    parts = relative.split("/")
    return _data_root(home).joinpath(*parts[1:]) if parts[0] == "data" else home.joinpath(*parts)


def _data_space_path(home: Path, registry: dict[str, Any]) -> Path:
    return _data_root(home) / registry["tenant_id"] / registry["user_id"] / registry["active_data_space_id"]


def _validate_sqlite(path: Path, context: dict[str, str] | None) -> None:
    try:
        uri = f"file:{path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        try:
            integrity = connection.execute("PRAGMA quick_check").fetchall()
            if integrity != [("ok",)]:
                _abort("desktop_release_sqlite_integrity_invalid")
            names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if context is not None:
                for binding_table in ("store_binding", "ledger_store_binding", "cash_coverage_binding", "realized_state_binding"):
                    if binding_table not in names:
                        continue
                    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({binding_table})")}
                    required = {"tenant_id", "user_id", "data_space_id"}
                    if required <= columns:
                        rows = connection.execute(f"SELECT tenant_id,user_id,data_space_id FROM {binding_table}").fetchall()
                        if rows != [(context["tenant_id"], context["user_id"], context["data_space_id"])]:
                            _abort("desktop_release_context_mismatch")
        finally:
            connection.close()
    except DesktopReleaseError:
        raise
    except Exception:
        _abort("desktop_release_sqlite_integrity_invalid")


def _relative_safe(value: str) -> bool:
    if not isinstance(value, str) or not value or value.startswith("/") or "\\" in value:
        return False
    parts = value.split("/")
    return all(
        part not in {"", ".", ".."} and SAFE_DATA_SEGMENT.fullmatch(part) is not None
        for part in parts
    )


def _transient_scratch(relative: str, expected_data_space_prefix: str) -> bool:
    """Rebuildbarer Arbeitsbereich unterhalb des Datenraums.

    Wird uebersprungen statt gesichert und loest keinen Fehler aus. Ein
    zurueckgebliebenes Vorschauverzeichnis darf die Sicherung nicht blockieren.
    """
    prefix = f"{expected_data_space_prefix}/"
    if not relative.startswith(prefix):
        return False
    head = relative[len(prefix):].split("/", 1)[0]
    return head.startswith(TRANSIENT_SCRATCH_PREFIXES)


RUN_LOCK_AREA = "refresh-all-v1"


def _run_lock(relative: str) -> bool:
    """Die Laufsperre von „Alles aktualisieren“ und Wartung (`<Datenraum>/refresh-all-v1/lock`, rc.416).

    Sie ist kein Datenbestand: Waehrend einer Wartung haelt der Wartungsprozess sie, und ein Begleitprozess erneuert jede Minute ihren
    Herzschlag (rc.410). Mitgesichert aenderte sie sich zwischen den beiden Lesedurchgaengen eines Backups, das laenger als eine Minute
    dauert - das Backup brach deshalb mit desktop_release_backup_source_changed ab. Zurueckgespielt
    braechte sie eine fremde Sperre in das wiederhergestellte Home. Deshalb: nicht sichern, nicht zurueckspielen, beim Abgleich mit
    dem Manifest eines aelteren Backups uebergehen (dort steht sie noch drin).
    """
    parts = relative.split("/")
    return len(parts) >= 6 and parts[0] == "data" and parts[4] == RUN_LOCK_AREA and parts[5] == "lock"


def _without_run_lock(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in entries if not _run_lock(row["relative_path"])]


def _persistent_writer_lock(relative: str, expected_data_space_prefix: str) -> bool:
    return relative in {
        f"{expected_data_space_prefix}/asset-activity-ledger-v1/writer.lock",
        f"{expected_data_space_prefix}/cash-coverage-v1/writer.lock",
        f"{expected_data_space_prefix}/realized-state-v2/writer.lock",
        f"{expected_data_space_prefix}/activity-drafts-v1/.writer.lock",
        f"{expected_data_space_prefix}/activity-drafts-v1/.writer-v2.lock",
    }


def _activity_draft_writer_barrier(relative: str, expected_data_space_prefix: str) -> bool:
    return relative == f"{expected_data_space_prefix}/activity-drafts-v1/.writer.lock"


def _activity_draft_special_relative(relative: str, expected_data_space_prefix: str) -> bool:
    base = f"{expected_data_space_prefix}/activity-drafts-v1"
    return relative in {
        f"{base}/.writer.lock",
        f"{base}/.writer.lock/immutable-source-supersession-v1.json",
        f"{base}/.writer.lock/mixed-source-retirement-v1.json",
        f"{base}/.writer-v2.lock",
    }


def _validate_activity_draft_writer_barrier(path: Path) -> None:
    try:
        metadata = path.stat(follow_symlinks=False)
        children = list(path.iterdir())
    except Exception:
        _abort("desktop_release_source_unsettled")
    child_names = {item.name for item in children}
    allowed = {
        "immutable-source-supersession-v1.json",
        "mixed-source-retirement-v1.json",
    }
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.geteuid()
        or "immutable-source-supersession-v1.json" not in child_names
        or not child_names <= allowed
        or any(item.is_symlink() for item in children)
    ):
        _abort("desktop_release_source_unsettled")
    marker = path / "immutable-source-supersession-v1.json"
    try:
        marker_metadata = marker.stat(follow_symlinks=False)
    except Exception:
        _abort("desktop_release_source_unsettled")
    if (
        not stat.S_ISREG(marker_metadata.st_mode)
        or stat.S_IMODE(marker_metadata.st_mode) != 0o600
        or marker_metadata.st_uid != os.geteuid()
        or marker_metadata.st_nlink != 1
    ):
        _abort("desktop_release_source_unsettled")
    value = _read_json(marker, canonical=True, code="desktop_release_source_unsettled")
    body = dict(value)
    fingerprint = body.pop("barrier_fingerprint", None)
    if body != {
        "activity_draft_writer_barrier_version": 1,
        "minimum_writer_capability": "immutable_exact_source_generation_supersession_v1",
        "legacy_writer_blocked": True,
    } or fingerprint != _sha_bytes(_canonical(body)):
        _abort("desktop_release_source_unsettled")
    mixed_marker = path / "mixed-source-retirement-v1.json"
    if mixed_marker.exists():
        try:
            mixed_metadata = mixed_marker.stat(follow_symlinks=False)
        except Exception:
            _abort("desktop_release_source_unsettled")
        if (
            not stat.S_ISREG(mixed_metadata.st_mode)
            or stat.S_IMODE(mixed_metadata.st_mode) != 0o600
            or mixed_metadata.st_uid != os.geteuid()
            or mixed_metadata.st_nlink != 1
            or mixed_marker.is_symlink()
        ):
            _abort("desktop_release_source_unsettled")
        mixed = _read_json(
            mixed_marker, canonical=True, code="desktop_release_source_unsettled",
        )
        mixed_body = dict(mixed)
        mixed_fingerprint = mixed_body.pop("barrier_fingerprint", None)
        if mixed_body != {
            "activity_draft_writer_barrier_version": 2,
            "minimum_writer_capability": "mixed_source_retirement_preserve_committed_v1",
            "legacy_writer_blocked": True,
        } or mixed_fingerprint != _sha_bytes(_canonical(mixed_body)):
            _abort("desktop_release_source_unsettled")


def _persistent_writer_lock_metadata_valid(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and stat.S_IMODE(metadata.st_mode) == 0o600
        and metadata.st_uid == os.geteuid()
        and metadata.st_nlink == 1
        and metadata.st_size == 0
    )


def _hold_or_check_persistent_writer_lock(path: Path, held_locks: dict[Path, int] | None) -> Path:
    try:
        resolved = path.resolve(strict=True)
    except Exception:
        _abort("desktop_release_root_invalid")
    if held_locks is not None and resolved in held_locks:
        try:
            held = os.fstat(held_locks[resolved])
            current = path.stat(follow_symlinks=False)
            if (
                (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino)
                or not _persistent_writer_lock_metadata_valid(held)
            ):
                _abort("desktop_release_source_unsettled")
        except DesktopReleaseError:
            raise
        except Exception:
            _abort("desktop_release_source_unsettled")
        return resolved
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(descriptor)
        current = path.stat(follow_symlinks=False)
        if (
            (metadata.st_dev, metadata.st_ino) != (current.st_dev, current.st_ino)
            or not _persistent_writer_lock_metadata_valid(metadata)
        ):
            _abort("desktop_release_permissions_invalid")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if held_locks is not None:
            held_locks[resolved] = descriptor
            descriptor = None
    except BlockingIOError:
        _abort("desktop_release_source_unsettled")
    except DesktopReleaseError:
        raise
    except Exception:
        _abort("desktop_release_source_unsettled")
    finally:
        if descriptor is not None:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
    return resolved


def _release_persistent_writer_locks(held_locks: dict[Path, int]) -> None:
    for descriptor in held_locks.values():
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)
    held_locks.clear()


def _shown_path(rel: str, expected_prefix: str) -> str:
    """Anzeigepfad eines Eintrags: relativ zum Datenraum, ohne Mandanten-, Nutzer- und Datenraumkennung davor."""
    return rel[len(expected_prefix) + 1:] if rel.startswith(expected_prefix + "/") else rel


def _source_tree(source: Path, unreadable, skip=None) -> list[Path]:
    """Alle Eintraege unter `source` (wie rglob, ohne Verknuepfungen zu folgen). Ein Lesefehler des Systems - etwa ein Ordner, dessen
    gocryptfs.diriv nach einem Neustart leer ist (#568) - ruft `unreadable(pfad)` und endet nicht als boundary_failed; ein waehrend
    des Durchlaufs verschwundener Eintrag gilt als veraenderte Quelle. `skip(pfad)`: Teilbaeume, die das Backup ohnehin uebergeht
    (fluechtige Arbeitsbereiche, Laufsperre) - in sie geht der Durchlauf nicht hinein, ein unlesbarer Eintrag dort blockiert nichts."""
    found: list[Path] = []
    pending = [source]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                children = [Path(entry.path) for entry in iterator]
        except FileNotFoundError:
            _abort("desktop_release_backup_source_changed")
        except OSError:
            unreadable(directory)
        for child in children:
            if skip is not None and skip(child):
                continue
            try:
                metadata = os.lstat(child)
            except FileNotFoundError:
                _abort("desktop_release_backup_source_changed")
            except OSError:
                unreadable(child)
            found.append(child)
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(child)
    return found


def _source_entries(
    home: Path, registry: dict[str, Any], *, held_locks: dict[Path, int] | None = None,
) -> list[dict[str, Any]]:
    data_space = _data_space_path(home, registry)
    if not data_space.is_dir() or data_space.is_symlink():
        _abort("desktop_release_root_invalid")
    data_root = _data_root(home)
    roots = [(home / "desktop-runtime.json", "desktop-runtime.json"), (data_root, "data")]
    context = _context(registry)
    expected_prefix = f"data/{context['tenant_id']}/{context['user_id']}/{context['data_space_id']}"
    entries: list[dict[str, Any]] = []
    seen_persistent_locks: set[Path] = set()
    total = 0
    for source, relative in roots:
        if source.is_symlink():
            _abort("desktop_release_symlink_rejected")
        if source.is_file():
            candidates: Iterable[Path] = [source]
        elif source.is_dir():
            def unreadable(path: Path) -> None:
                _abort_unreadable(_shown_path(_relative(home, data_root, path), expected_prefix))

            def skipped(path: Path) -> bool:
                rel = _relative(home, data_root, path)
                return _transient_scratch(rel, expected_prefix) or _run_lock(rel)
            candidates = [source, *sorted(_source_tree(source, unreadable, skipped), key=lambda item: _relative(home, data_root, item))]
        else:
            _abort("desktop_release_root_invalid")
        for path in candidates:
            if path.is_symlink():
                _abort("desktop_release_symlink_rejected")
            rel = relative if path == source else _relative(home, data_root, path)
            if _transient_scratch(rel, expected_prefix) or _run_lock(rel):
                continue
            if not _relative_safe(rel) and not _activity_draft_special_relative(rel, expected_prefix):
                _abort("desktop_release_root_invalid")
            if path.is_dir():
                if not _owner_only(path):
                    _abort("desktop_release_permissions_invalid")
                if path.name.endswith(".lock"):
                    if not _activity_draft_writer_barrier(rel, expected_prefix):
                        _abort("desktop_release_source_unsettled")
                    _validate_activity_draft_writer_barrier(path)
                if ".incoming" in path.name:
                    _abort("desktop_release_source_unsettled")
                entries.append({"relative_path": rel, "entry_type": "directory", "mode": f"{_mode(path):04o}", "byte_count": None, "bytes_fingerprint": None})
            elif path.is_file():
                if not _owner_only(path):
                    _abort("desktop_release_permissions_invalid")
                if _persistent_writer_lock(rel, expected_prefix):
                    seen_persistent_locks.add(_hold_or_check_persistent_writer_lock(path, held_locks))
                    continue
                if path.name.endswith((".tmp", ".journal", "-journal", "-wal", "-shm")) or path.name in {"publication.lock", "writer.lock"} or ".incoming" in path.name:
                    _abort("desktop_release_source_unsettled")
                payload = _read_bytes(path, unreadable=_shown_path(rel, expected_prefix))
                total += len(payload)
                if total > MAX_TOTAL_BYTES:
                    _abort("desktop_release_root_invalid")
                if path.suffix == ".sqlite":
                    _validate_sqlite(path, context)
                entries.append({"relative_path": rel, "entry_type": "file", "mode": f"{_mode(path):04o}", "byte_count": len(payload), "bytes_fingerprint": _sha_bytes(payload)})
            else:
                _abort("desktop_release_root_invalid")
    # Only the bound context may exist below data/.
    files_below_data = [row["relative_path"] for row in entries if row["relative_path"].startswith("data/")]
    if not files_below_data or any(not (path == "data" or path in {
        f"data/{context['tenant_id']}", f"data/{context['tenant_id']}/{context['user_id']}", expected_prefix,
    } or path.startswith(expected_prefix + "/")) for path in files_below_data):
        _abort("desktop_release_context_mismatch")
    entries.sort(key=lambda row: row["relative_path"])
    if len({row["relative_path"] for row in entries}) != len(entries):
        _abort("desktop_release_root_invalid")
    if held_locks is not None and set(held_locks) != seen_persistent_locks:
        _abort("desktop_release_source_unsettled")
    return entries


def _settled_source_entries(home: Path, registry: dict[str, Any]) -> list[dict[str, Any]]:
    held_locks: dict[Path, int] = {}
    try:
        entries = _source_entries(home, registry, held_locks=held_locks)
        if _source_entries(home, registry, held_locks=held_locks) != entries:
            _abort("desktop_release_backup_source_changed")
        return entries
    finally:
        _release_persistent_writer_locks(held_locks)


def _mkdir(path: Path, mode: int = 0o700) -> None:
    try:
        path.mkdir(mode=mode)
        os.chmod(path, mode)
    except Exception:
        _abort("desktop_release_write_failed")


def _write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, mode)
    except FileExistsError:
        raise
    except Exception:
        _abort("desktop_release_write_failed")


def _fsync(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except Exception:
        _abort("desktop_release_write_failed")


def _remove_owned_stage(path: Path, marker_name: str, operation: str) -> None:
    if not path.exists():
        return
    code = "desktop_release_restore_conflict" if operation == "restore" else "desktop_release_backup_conflict"
    if path.is_symlink() or not path.is_dir():
        _abort(code)
    marker = _read_json(path / marker_name, canonical=True, code=code)
    if marker.get("operation") != operation or marker.get("contract_version") != 1:
        _abort(code)
    try:
        shutil.rmtree(path)
        _fsync(path.parent)
    except Exception:
        _abort("desktop_release_write_failed")


def _copy_entries(source_home: Path, target_payload: Path, entries: list[dict[str, Any]]) -> None:
    for row in entries:
        relative = row["relative_path"]
        destination = target_payload.joinpath(*relative.split("/"))
        if row["entry_type"] == "directory":
            _mkdir(destination, int(row["mode"], 8))
            continue
        source = _source_path(source_home, relative)
        payload = _read_bytes(source)
        if len(payload) != row["byte_count"] or _sha_bytes(payload) != row["bytes_fingerprint"]:
            _abort("desktop_release_backup_source_changed")
        _write(destination, payload, int(row["mode"], 8))
    for row in reversed(entries):
        if row["entry_type"] == "directory":
            _fsync(target_payload.joinpath(*row["relative_path"].split("/")))
    _fsync(target_payload)


def _backup_manifest(registry: dict[str, Any], product_version: str, created_at_utc: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    context = _context(registry)
    payload = {
        "desktop_backup_version": 1,
        "backup_format": "portelyra_desktop_backup_v1",
        "product_version": _version(product_version),
        "created_at_utc": _utc(created_at_utc),
        **context,
        "registry_revision": registry["registry_revision"],
        "scope_profile": "complete_active_data_space_v1",
        "entry_count": len(entries),
        "source_tree_fingerprint": _fingerprint(entries),
        "entries": entries,
        "automatic_restore": False,
        "contains_release_code": False,
    }
    return {**payload, "backup_manifest_fingerprint": _fingerprint(payload)}


def _safe_result(operation: str, status: str) -> dict[str, Any]:
    return {
        "desktop_release_version": 1,
        "operation": operation,
        "status": status,
        "safe_output": True,
        "automatic_retry": False,
    }


def create_desktop_backup_v1(
    capability: DesktopReleaseCapability,
    bundle_directory: Path,
    product_version: str,
    created_at_utc: str,
    *,
    fail_at: str | None = None,
) -> dict[str, Any]:
    if fail_at not in {None, "after_payload", "after_manifest", "after_success", "after_publish"}:
        _abort("desktop_release_input_invalid")
    home, registry = _validate_capability(capability)
    target, parent = _destination(bundle_directory)
    if _overlap(home, target):
        _abort("desktop_release_root_invalid")
    # Mit Passwortschutz (#535) liegen Backups nur im verschluesselten Backup-Ordner - sonst laege eine lesbare Kopie daneben.
    from migrations.reference.desktop_protection_v1 import DesktopProtectionV1Error, backups_root_v1
    try:
        protected_backups = backups_root_v1(home)
    except DesktopProtectionV1Error:
        _abort("desktop_release_locked")
        raise
    if protected_backups is not None:
        try:
            target.relative_to(protected_backups.resolve())
        except ValueError:
            _abort("desktop_release_backup_target_unprotected")
    if target.exists():
        existing = validate_desktop_backup_v1(target)
        if _context(registry) != {key: existing[key] for key in ("tenant_id", "user_id", "data_space_id")}:
            _abort("desktop_release_context_mismatch")
        current_entries = _settled_source_entries(home, registry)
        if existing["source_tree_fingerprint"] != _fingerprint(current_entries):
            _abort("desktop_release_backup_conflict")
        return {**_safe_result("backup", "already_created"), **_bundle_summary(existing)}
    stage = parent / f".{target.name}.portelyra-backup-incoming"
    marker_name = "OPERATION.json"
    _remove_owned_stage(stage, marker_name, "backup")
    held_locks: dict[Path, int] = {}
    try:
        entries = _source_entries(home, registry, held_locks=held_locks)
        manifest = _backup_manifest(registry, product_version, created_at_utc, entries)
        published = False
        try:
            _mkdir(stage)
            _write(stage / marker_name, _canonical({"contract_version": 1, "operation": "backup"}) + b"\n")
            payload_root = stage / "payload"
            _mkdir(payload_root)
            _copy_entries(home, payload_root, entries)
            if _source_entries(home, registry, held_locks=held_locks) != entries:
                _abort("desktop_release_backup_source_changed")
            if fail_at == "after_payload":
                _abort("synthetic_desktop_release_failpoint")
            _write(stage / "backup-manifest.json", _canonical(manifest) + b"\n")
            if fail_at == "after_manifest":
                _abort("synthetic_desktop_release_failpoint")
            success = {"desktop_backup_version": 1, "backup_manifest_fingerprint": manifest["backup_manifest_fingerprint"]}
            _write(stage / "SUCCESS", _canonical(success) + b"\n")
            if fail_at == "after_success":
                _abort("synthetic_desktop_release_failpoint")
            (stage / marker_name).unlink()
            _fsync(stage)
            os.rename(stage, target)
            published = True
            _fsync(parent)
            if fail_at == "after_publish":
                _abort("synthetic_desktop_release_failpoint")
            return {**_safe_result("backup", "created"), **_bundle_summary(validate_desktop_backup_v1(target))}
        finally:
            if not published and stage.exists():
                try:
                    shutil.rmtree(stage)
                    _fsync(parent)
                except Exception:
                    if not isinstance(__import__("sys").exc_info()[1], DesktopReleaseError):
                        _abort("desktop_release_write_failed")
    finally:
        _release_persistent_writer_locks(held_locks)


def _manifest_shape(manifest: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    expected = {
        "desktop_backup_version", "backup_format", "product_version", "created_at_utc",
        "tenant_id", "user_id", "data_space_id", "registry_revision", "scope_profile",
        "entry_count", "source_tree_fingerprint", "entries", "automatic_restore",
        "contains_release_code", "backup_manifest_fingerprint",
    }
    if set(manifest) != expected or manifest.get("desktop_backup_version") != 1 or manifest.get("backup_format") != "portelyra_desktop_backup_v1" or manifest.get("registry_revision") != 1 or manifest.get("scope_profile") != "complete_active_data_space_v1" or manifest.get("automatic_restore") is not False or manifest.get("contains_release_code") is not False:
        _abort("desktop_release_manifest_invalid")
    _version(manifest.get("product_version")); _utc(manifest.get("created_at_utc"))
    context = {key: manifest.get(key) for key in ("tenant_id", "user_id", "data_space_id")}
    if any(not isinstance(context[key], str) or OPAQUE[key].fullmatch(context[key]) is None for key in context):
        _abort("desktop_release_manifest_invalid")
    entries = manifest.get("entries")
    if not isinstance(entries, list) or not entries or manifest.get("entry_count") != len(entries) or isinstance(manifest.get("entry_count"), bool):
        _abort("desktop_release_manifest_invalid")
    previous = ""
    expected_prefix = f"data/{context['tenant_id']}/{context['user_id']}/{context['data_space_id']}"
    for row in entries:
        if not isinstance(row, dict) or set(row) != {"relative_path", "entry_type", "mode", "byte_count", "bytes_fingerprint"}:
            _abort("desktop_release_manifest_invalid")
        relative = row.get("relative_path")
        if (not _relative_safe(relative) and not _activity_draft_special_relative(relative, expected_prefix)) or relative <= previous:
            _abort("desktop_release_manifest_invalid")
        previous = relative
        if row.get("entry_type") not in {"directory", "file"} or not isinstance(row.get("mode"), str) or re.fullmatch(r"0[0467]00", row["mode"]) is None:
            _abort("desktop_release_manifest_invalid")
        if int(row["mode"], 8) & 0o077:
            _abort("desktop_release_manifest_invalid")
        if row["entry_type"] == "directory":
            if row["byte_count"] is not None or row["bytes_fingerprint"] is not None:
                _abort("desktop_release_manifest_invalid")
        elif not isinstance(row["byte_count"], int) or isinstance(row["byte_count"], bool) or not 0 <= row["byte_count"] <= MAX_FILE_BYTES or not isinstance(row["bytes_fingerprint"], str) or SHA.fullmatch(row["bytes_fingerprint"]) is None:
            _abort("desktop_release_manifest_invalid")
    payload = {key: value for key, value in manifest.items() if key != "backup_manifest_fingerprint"}
    if manifest.get("source_tree_fingerprint") != _fingerprint(entries) or manifest.get("backup_manifest_fingerprint") != _fingerprint(payload):
        _abort("desktop_release_manifest_invalid")
    return context, entries


def validate_desktop_backup_v1(bundle_directory: Path, *, source_permissions: str = "strict") -> dict[str, Any]:
    """Prueft ein Backup vollstaendig: Form, Manifest, jede Datei gegen ihre Pruefsumme, jede SQLite-Datei, die Kennung.

    `source_permissions="ignored"` (rc.410): Besitzer und Rechte der Quelle zaehlen nicht, nur ihre Lesbarkeit - siehe
    `_source_directory`. Alles andere bleibt: keine symbolischen Verweise, genau die Eintraege des Manifests, Groesse und Pruefsumme.
    """
    strict = _source_permissions(source_permissions)
    try:
        bundle = _source_directory(bundle_directory, strict)
        children = {item.name for item in bundle.iterdir()}
        if children != {"SUCCESS", "backup-manifest.json", "payload"}:
            _abort("desktop_release_backup_integrity_invalid")
        if not strict and not all(os.access(bundle / name, os.R_OK) for name in ("SUCCESS", "backup-manifest.json")):
            _abort("desktop_release_permissions_invalid")
        manifest = _read_json(
            bundle / "backup-manifest.json", canonical=True, maximum=MAX_BACKUP_MANIFEST_BYTES,
        )
        context, entries = _manifest_shape(manifest)
        success = _read_json(bundle / "SUCCESS", canonical=True, code="desktop_release_backup_integrity_invalid")
        if success != {"desktop_backup_version": 1, "backup_manifest_fingerprint": manifest["backup_manifest_fingerprint"]}:
            _abort("desktop_release_backup_integrity_invalid")
        payload_root = _source_directory(bundle / "payload", strict)
        actual: set[str] = set()
        for path in [*sorted(payload_root.rglob("*"), key=lambda item: item.relative_to(payload_root).as_posix())]:
            if path.is_symlink():
                _abort("desktop_release_symlink_rejected")
            actual.add(path.relative_to(payload_root).as_posix())
        expected = {row["relative_path"] for row in entries}
        if actual != expected:
            _abort("desktop_release_backup_integrity_invalid")
        for row in entries:
            path = payload_root.joinpath(*row["relative_path"].split("/"))
            if strict:
                if _mode(path) != int(row["mode"], 8) or not _owner_only(path):
                    _abort("desktop_release_permissions_invalid")
            elif not os.access(path, os.R_OK | os.X_OK if row["entry_type"] == "directory" else os.R_OK):
                _abort("desktop_release_permissions_invalid")
            if row["entry_type"] == "directory":
                if not path.is_dir():
                    _abort("desktop_release_backup_integrity_invalid")
            else:
                payload = _read_bytes(path, code="desktop_release_backup_integrity_invalid")
                if len(payload) != row["byte_count"] or _sha_bytes(payload) != row["bytes_fingerprint"]:
                    _abort("desktop_release_backup_integrity_invalid")
                if path.suffix == ".sqlite":
                    _validate_sqlite(path, context)
        registry = _registry(payload_root / "desktop-runtime.json")
        if _context(registry) != context:
            _abort("desktop_release_context_mismatch")
        expected_prefix = f"data/{context['tenant_id']}/{context['user_id']}/{context['data_space_id']}"
        if not any(row["relative_path"] == expected_prefix for row in entries):
            _abort("desktop_release_context_mismatch")
        return manifest
    except DesktopReleaseError as error:
        if error.code in {"desktop_release_symlink_rejected", "desktop_release_permissions_invalid", "desktop_release_context_mismatch", "desktop_release_sqlite_integrity_invalid", "desktop_release_manifest_invalid"}:
            raise
        _abort("desktop_release_backup_integrity_invalid")
    except Exception:
        _abort("desktop_release_backup_integrity_invalid")


BACKUP_BUNDLE_CHILDREN = frozenset({"SUCCESS", "backup-manifest.json", "payload"})
MAX_PRUNE_KEEP = 50


def _bundle_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    """Groesse und Inhalt eines Backups fuer die Statusmeldung (#438): nur Zaehler, Zeitpunkt und Programmstand."""
    entries = manifest["entries"]
    return {
        "created_at_utc": manifest["created_at_utc"], "product_version": manifest["product_version"],
        "entry_count": len(entries), "file_count": sum(1 for row in entries if row["entry_type"] == "file"),
        "byte_count": sum(row["byte_count"] or 0 for row in entries if row["entry_type"] == "file"),
    }


def backup_summary_desktop_v1(bundle_directory: Path, *, source_permissions: str = "strict") -> dict[str, Any]:
    """Geprueftes Backup samt Groesse und Inhalt (#438)."""
    return _bundle_summary(validate_desktop_backup_v1(bundle_directory, source_permissions=source_permissions))


def _prune_plan(root: Path, keep: int, own_context: dict[str, str] | None = None) -> tuple[dict[str, Any], list[Path]]:
    """Welche Backups bleiben, welche gehen (#438, Festlegung 23.10.2026: die drei juengsten, nur gepruefte zaehlen).

    Bundel ist ein Verzeichnis direkt im Backup-Ordner mit genau SUCCESS, backup-manifest.json und payload. Vom juengsten an
    wird vollstaendig geprueft, bis keep Backups gueltig sind; ein ungueltiges bleibt liegen und zaehlt nicht. Entfernt werden
    nur aeltere Buendel desselben Datenraums, und nur wenn keep gueltige gefunden sind. Alles andere bleibt unberuehrt.

    Mit `own_context` (rc.410) zaehlt nur dieser Datenraum: Der Backup-Ordner gehoert allen Homes eines Benutzerkontos, und ohne
    Vorgabe bestimmt das juengste gueltige Backup den Datenraum - aus der Karte „Backups“ einer Installation waeren so die Backups
    einer anderen ausgeduennt worden (Prüfung 13.11.2026). Ohne Vorgabe (Aufruf nur mit Ordner) gilt das bisherige Verhalten.
    """
    if isinstance(keep, bool) or not isinstance(keep, int) or not 1 <= keep <= MAX_PRUNE_KEEP:
        _abort("desktop_release_input_invalid")
    base = _existing_directory(root)
    found: list[tuple[str, str, Path, dict[str, Any]]] = []
    foreign = 0
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if child.is_symlink() or not child.is_dir() or not SAFE_NAME.fullmatch(child.name):
            foreign += 1
            continue
        try:
            if {item.name for item in child.iterdir()} != BACKUP_BUNDLE_CHILDREN:
                foreign += 1
                continue
            manifest = _read_json(child / "backup-manifest.json", canonical=True, maximum=MAX_BACKUP_MANIFEST_BYTES)
            _manifest_shape(manifest)
        except DesktopReleaseError:
            foreign += 1
            continue
        found.append((manifest["created_at_utc"], child.name, child, manifest))
    found.sort(key=lambda item: (item[0], item[1]), reverse=True)
    kept: list[tuple[Path, dict[str, Any]]] = []
    invalid: list[Path] = []
    context = dict(own_context) if own_context is not None else None
    for created, name, path, manifest in found:
        if len(kept) == keep:
            break
        own = {key: manifest[key] for key in ("tenant_id", "user_id", "data_space_id")}
        if context is not None and own != context:
            continue
        try:
            validate_desktop_backup_v1(path)
        except DesktopReleaseError:
            invalid.append(path)
            continue
        context = own
        kept.append((path, manifest))
    oldest_kept = min((manifest["created_at_utc"], path.name) for path, manifest in kept) if kept else None
    removal = [] if len(kept) < keep else [
        (path, manifest) for created, name, path, manifest in found
        if path not in invalid and all(path != item for item, _ in kept)
        and {key: manifest[key] for key in ("tenant_id", "user_id", "data_space_id")} == context
        and (created, name) < oldest_kept
    ]
    other = len(found) - len(kept) - len(invalid) - len(removal)
    plan = {
        "keep_count": keep, "kept": [_bundle_summary(manifest) for _, manifest in kept],
        "removed": [_bundle_summary(manifest) for _, manifest in removal],
        "invalid_kept_count": len(invalid), "other_data_space_or_newer_count": other, "foreign_entry_count": foreign,
        "removed_byte_count": sum(_bundle_summary(manifest)["byte_count"] for _, manifest in removal),
        "enough_valid": len(kept) == keep,
    }
    plan["plan_fingerprint"] = _fingerprint(plan)
    return plan, [path for path, _ in removal]


def version_key_v1(value: str) -> tuple[int, int, int, int]:
    """Ordnung der Programmstaende: 0.2.0-rc.406 < 0.2.0-rc.407 < 0.2.0 < 0.3.0-rc.1 (ein Release steht nach seinen Kandidaten)."""
    version = _version(value)
    core, _, rc = version.partition("-rc.")
    major, minor, patch = (int(part) for part in core.split("."))
    return (major, minor, patch, int(rc) if rc else 10**9)


def list_desktop_backups_v1(root: Path, product_version: str, home: Path | None = None, *,
                            source_permissions: str = "strict") -> dict[str, Any]:
    """Backups eines Ordners fuer die Karte „Backups“ und den Einrichtungsdialog (#559, rc.407) - schnell, ohne Pruefsummen.

    Gelesen werden nur Ordnerform und Manifest. Ob ein Backup vollstaendig und unversehrt ist, sagt erst `backup_check`
    (nach dem Anlegen, vor dem Wiederherstellen). Je Backup: Name, Zeitpunkt, Programmstand, Groesse, ob es zum Datenraum dieses
    Homes gehoert und ob es aus einem neueren Programmstand stammt - ein solches wird nicht wiederhergestellt.
    `source_permissions="ignored"` (rc.410): ein vom Nutzer genannter Ordner, der nur gelesen wird - siehe `_source_directory`.
    """
    current = version_key_v1(product_version)
    base = _source_directory(root, _source_permissions(source_permissions))
    own_context = None
    if home is not None:
        try:
            own_context = _context(_registry(_existing_directory(home) / "desktop-runtime.json"))
        except DesktopReleaseError:
            own_context = None
    bundles: list[dict[str, Any]] = []
    foreign = 0
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if child.is_symlink() or not child.is_dir() or not SAFE_NAME.fullmatch(child.name):
            foreign += 1
            continue
        try:
            if {item.name for item in child.iterdir()} != BACKUP_BUNDLE_CHILDREN:
                foreign += 1
                continue
            manifest = _read_json(child / "backup-manifest.json", canonical=True, maximum=MAX_BACKUP_MANIFEST_BYTES)
            _manifest_shape(manifest)
        except (DesktopReleaseError, OSError):
            foreign += 1
            continue
        context = {key: manifest[key] for key in ("tenant_id", "user_id", "data_space_id")}
        bundles.append({"name": child.name, **_bundle_summary(manifest),
                        "own_data_space": None if own_context is None else context == own_context,
                        "newer_version": version_key_v1(manifest["product_version"]) > current})
    bundles.sort(key=lambda row: (row["created_at_utc"], row["name"]), reverse=True)
    # Die Namen der Backups stehen bewusst drin (Auswahl in Karte und Dialog) - deshalb kein „safe_output“ fuer Protokolle.
    return {"desktop_release_version": 1, "operation": "backup_list", "status": "listed", "safe_output": False,
            "bundles": bundles, "foreign_entry_count": foreign}


def prune_desktop_backups_v1(root: Path, keep: int, plan_fingerprint: str | None = None, home: Path | None = None) -> dict[str, Any]:
    """Ohne plan_fingerprint nur der Plan; mit dem Fingerprint genau diesen Plan ausfuehren, sonst nichts (#438). Mit `home` nur die
    Backups von dessen Datenraum (rc.410)."""
    own_context = None if home is None else _context(_registry(_existing_directory(home) / "desktop-runtime.json"))
    plan, removal = _prune_plan(root, keep, own_context)
    if plan_fingerprint is None:
        return {"status": "planned", "operation": "backup_prune", "safe_output": True, **plan}
    if not isinstance(plan_fingerprint, str) or SHA.fullmatch(plan_fingerprint) is None:
        _abort("desktop_release_input_invalid")
    if plan_fingerprint != plan["plan_fingerprint"]:
        _abort("desktop_release_backup_conflict")
    base = _existing_directory(root)
    for path in removal:
        if path.parent != base or path.is_symlink() or {item.name for item in path.iterdir()} != BACKUP_BUNDLE_CHILDREN:
            _abort("desktop_release_backup_conflict")
        try:
            shutil.rmtree(path)
        except Exception:
            _abort("desktop_release_write_failed")
    _fsync(base)
    return {"status": "pruned", "operation": "backup_prune", "safe_output": True, **plan}


def preflight_desktop_restore_v1(bundle_directory: Path, target_home: Path) -> dict[str, Any]:
    manifest = validate_desktop_backup_v1(bundle_directory)
    target, _ = _destination(target_home)
    bundle = bundle_directory.resolve(strict=True)
    if _overlap(bundle, target):
        _abort("desktop_release_root_invalid")
    if target.exists():
        if target.is_symlink() or not target.is_dir():
            _abort("desktop_release_restore_conflict")
        children = list(target.iterdir())
        if children:
            registry_path = target / "desktop-runtime.json"
            if registry_path.exists():
                try:
                    existing_context = _context(_registry(registry_path))
                except DesktopReleaseError:
                    _abort("desktop_release_restore_context_mismatch")
                wanted = {key: manifest[key] for key in ("tenant_id", "user_id", "data_space_id")}
                if existing_context != wanted:
                    _abort("desktop_release_restore_context_mismatch")
            _abort("desktop_release_restore_target_not_empty")
        if not _owner_only(target):
            _abort("desktop_release_permissions_invalid")
    return {
        "desktop_release_version": 1,
        "operation": "restore_preflight",
        "status": "ready_for_confirmed_restore",
        "target_empty": True,
        "manifest_fingerprint": manifest["backup_manifest_fingerprint"],
        "source_tree_fingerprint": manifest["source_tree_fingerprint"],
        "automatic_restore": False,
    }


def _copy_restore_payload(bundle: Path, stage: Path, entries: list[dict[str, Any]]) -> None:
    payload = bundle / "payload"
    # Die Laufsperre eines aelteren Backups kommt nicht mit (rc.416, siehe _run_lock).
    for row in _without_run_lock(entries):
        source = payload.joinpath(*row["relative_path"].split("/"))
        destination = stage.joinpath(*row["relative_path"].split("/"))
        if row["entry_type"] == "directory":
            _mkdir(destination, int(row["mode"], 8))
        else:
            data = _read_bytes(source, code="desktop_release_backup_integrity_invalid")
            # Jede Datei beim Zurueckspielen noch einmal gegen das Manifest (rc.410): Zwischen Pruefung und Kopie kann sich eine Quelle
            # aendern, die nicht nur dem Nutzer gehoert (Wechselmedium). Die Rechte kommen aus dem Manifest, nie von der Quelle.
            if len(data) != row["byte_count"] or _sha_bytes(data) != row["bytes_fingerprint"]:
                _abort("desktop_release_backup_integrity_invalid")
            _write(destination, data, int(row["mode"], 8))
    for row in reversed(_without_run_lock(entries)):
        if row["entry_type"] == "directory":
            _fsync(stage.joinpath(*row["relative_path"].split("/")))
    _fsync(stage)


def restore_desktop_backup_v1(
    capability: DesktopReleaseCapability,
    bundle_directory: Path,
    target_home: Path,
    *,
    fail_at: str | None = None,
) -> dict[str, Any]:
    if fail_at not in {None, "after_payload", "after_target_publish"}:
        _abort("desktop_release_input_invalid")
    current_home, current_registry = _validate_capability(capability)
    target, parent = _destination(target_home)
    bundle = bundle_directory.resolve(strict=True)
    if _overlap(current_home, target) or _overlap(current_home, bundle):
        _abort("desktop_release_root_invalid")
    manifest = validate_desktop_backup_v1(bundle)
    expected_context = {key: manifest[key] for key in ("tenant_id", "user_id", "data_space_id")}
    if _context(current_registry) != expected_context:
        _abort("desktop_release_restore_context_mismatch")
    _, entries = _manifest_shape(manifest)
    placeholder = parent / f".{target.name}.empty-before-restore"
    if target.exists() and any(target.iterdir()):
        try:
            restored_registry = _registry(target / "desktop-runtime.json")
            restored_entries = _settled_source_entries(target, restored_registry)
        except DesktopReleaseError:
            _abort("desktop_release_restore_target_not_empty")
        if _context(restored_registry) != expected_context or restored_entries != _without_run_lock(entries):
            _abort("desktop_release_restore_target_not_empty")
        if placeholder.exists():
            if placeholder.is_symlink() or not placeholder.is_dir() or any(placeholder.iterdir()):
                _abort("desktop_release_restore_conflict")
            placeholder.rmdir(); _fsync(parent)
        return _safe_result("restore", "already_restored")
    preflight = preflight_desktop_restore_v1(bundle_directory, target_home)
    stage = parent / f".{target.name}.portelyra-restore-incoming"
    _remove_owned_stage(stage, "OPERATION.json", "restore")
    published = False
    empty_placeholder: Path | None = None
    try:
        _mkdir(stage)
        _write(stage / "OPERATION.json", _canonical({"contract_version": 1, "operation": "restore"}) + b"\n")
        _copy_restore_payload(bundle, stage, entries)
        (stage / "OPERATION.json").unlink()
        if fail_at == "after_payload":
            _abort("synthetic_desktop_release_failpoint")
        if target.exists():
            empty_placeholder = placeholder
            if empty_placeholder.exists() or not target.is_dir() or any(target.iterdir()):
                _abort("desktop_release_restore_target_not_empty")
            os.rename(target, empty_placeholder)
        os.rename(stage, target)
        published = True
        _fsync(parent)
        if fail_at == "after_target_publish":
            _abort("synthetic_desktop_release_failpoint")
        if empty_placeholder is not None:
            empty_placeholder.rmdir()
            _fsync(parent)
        restored_registry = _registry(target / "desktop-runtime.json")
        if _context(restored_registry) != expected_context:
            _abort("desktop_release_restore_context_mismatch")
        restored_entries = _settled_source_entries(target, restored_registry)
        # Ohne die Laufsperre eines aelteren Backups (rc.416); ohne sie ist der Abdruck des Manifests unveraendert gueltig.
        kept = _without_run_lock(entries)
        expected_fingerprint = preflight["source_tree_fingerprint"] if kept == entries else _fingerprint(kept)
        if restored_entries != kept or _fingerprint(restored_entries) != expected_fingerprint:
            _abort("desktop_release_backup_integrity_invalid")
        return _safe_result("restore", "restored")
    finally:
        if not published and stage.exists():
            try:
                shutil.rmtree(stage)
                _fsync(parent)
            except Exception:
                pass
        if empty_placeholder is not None and empty_placeholder.exists() and not target.exists():
            try:
                os.rename(empty_placeholder, target)
                _fsync(parent)
            except Exception:
                pass


def restore_into_fresh_home_v1(capability: DesktopReleaseCapability, bundle_directory: Path, product_version: str, *,
                               source_permissions: str = "strict", fail_at: str | None = None) -> dict[str, Any]:
    """Wiederherstellen im Einrichtungsdialog (#559 Teil 2, rc.408): in das gerade eingerichtete Home, nicht in einen leeren Ordner.

    Ein frisch installiertes Home hat ein eigenes Register (eigene Kennung) und die Programmbibliothek, aber keinen Datenbestand.
    Der allgemeine Restore verlangt ein leeres Ziel und eine Installation mit der Kennung des Backups (Notfallweg, #535) - fuer den
    Dialog zu umstaendlich. Hier: Backup vollstaendig pruefen, einen neueren Programmstand abweisen, die Nutzdaten in einen eigenen
    Zwischenordner im Home zurueckspielen, dann `data` und das Register des Backups einsetzen (die Kennung des Backups gilt) und den
    Bestand an den neuen Ort binden. Die Bibliothek bleibt, die Quelle bleibt unveraendert. Mit Datenbestand oder Passwortschutz im
    Home: Abbruch - dort waere es kein frisches Home mehr.

    `source_permissions="ignored"` (rc.410, Ordnerwahl): Die Quelle darf auf einem Medium ohne Rechteverwaltung liegen oder einem
    anderen Benutzer gehoeren. Sie wird nur gelesen; das Home bekommt die Rechte aus dem Manifest, und der Abgleich am Ende vergleicht
    den zurueckgespielten Bestand samt Rechten mit dem Manifest.
    """
    if fail_at not in {None, "after_data", "after_publish"}:
        _abort("desktop_release_input_invalid")
    _source_permissions(source_permissions)
    home, _ = _validate_capability(capability)
    bundle = bundle_directory.resolve(strict=True)
    if _overlap(home, bundle):
        _abort("desktop_release_root_invalid")
    manifest = validate_desktop_backup_v1(bundle, source_permissions=source_permissions)
    if version_key_v1(manifest["product_version"]) > version_key_v1(product_version):
        _abort("desktop_release_restore_newer_version")
    data = home / "data"
    if (home / "protection.json").exists() or data.is_symlink() or (data.exists() and (not data.is_dir() or any(data.iterdir()))):
        _abort("desktop_release_restore_target_not_empty")
    _, entries = _manifest_shape(manifest)
    expected_context = {key: manifest[key] for key in ("tenant_id", "user_id", "data_space_id")}
    stage = home / ".restore-incoming"
    _remove_owned_stage(stage, "OPERATION.json", "restore_fresh")
    # Rueckweg (rc.410, Review 13.11.2026): Scheitert etwas, nachdem `data` und das Register eingesetzt sind, waere das Home halb
    # wiederhergestellt - ungepruefte Daten unter fremdem Register, und ein zweiter Versuch scheiterte an „nicht leer“. Deshalb das
    # frische Register merken und bei jedem Fehler danach beides zuruecknehmen: Das Home ist wieder frisch, die Quelle ohnehin unberuehrt.
    fresh_registry = _read_bytes(home / "desktop-runtime.json", code="desktop_release_context_mismatch")
    data_published = registry_published = False
    try:
        _mkdir(stage)
        _write(stage / "OPERATION.json", _canonical({"contract_version": 1, "operation": "restore_fresh"}) + b"\n")
        _copy_restore_payload(bundle, stage, entries)
        (stage / "OPERATION.json").unlink()
        if _context(_registry(stage / "desktop-runtime.json")) != expected_context:
            _abort("desktop_release_restore_context_mismatch")
        if data.exists():
            data.rmdir()
        os.rename(stage / "data", data)
        data_published = True
        if fail_at == "after_data":
            _abort("synthetic_desktop_release_failpoint")
        os.replace(stage / "desktop-runtime.json", home / "desktop-runtime.json")
        registry_published = True
        _fsync(home)
        if fail_at == "after_publish":
            _abort("synthetic_desktop_release_failpoint")
        restored_registry = _registry(home / "desktop-runtime.json")
        if _settled_source_entries(home, restored_registry) != _without_run_lock(entries):
            _abort("desktop_release_backup_integrity_invalid")
    except BaseException:
        try:
            if registry_published:
                _write(home / ".desktop-runtime.json.restore-rollback", fresh_registry)
                os.replace(home / ".desktop-runtime.json.restore-rollback", home / "desktop-runtime.json")
            if data_published and data.is_dir() and not data.is_symlink():
                shutil.rmtree(data)
            _fsync(home)
        except Exception:
            pass
        raise
    finally:
        if stage.exists():
            try:
                shutil.rmtree(stage)
                _fsync(home)
            except Exception:
                pass
    relocation = bind_restored_data_space_v1(new_desktop_release_capability_v1(home, capability.session_nonce), home)
    return {**_safe_result("restore_fresh", "restored"), "product_version": manifest["product_version"],
            "created_at_utc": manifest["created_at_utc"], **relocation}


def _release_registry(project_root: Path) -> list[dict[str, str]]:
    root = _existing_directory(project_root, owner_only=False)
    registry_path = root / "contracts" / "desktop-product" / "v1" / "source-fingerprints.csv"
    raw = _read_bytes(registry_path, maximum=2_000_000, code="desktop_release_release_integrity_invalid")
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    except Exception:
        _abort("desktop_release_release_integrity_invalid")
    if not rows or list(rows[0]) != ["path", "sha256"]:
        _abort("desktop_release_release_integrity_invalid")
    previous = ""
    for row in rows:
        relative = row.get("path", "")
        if not _relative_safe(relative) or relative <= previous or not isinstance(row.get("sha256"), str) or SHA.fullmatch(row["sha256"]) is None:
            _abort("desktop_release_release_integrity_invalid")
        previous = relative
        path = root.joinpath(*relative.split("/"))
        if path.is_symlink() or not path.is_file() or _sha_bytes(_read_bytes(path)) != row["sha256"]:
            _abort("desktop_release_release_integrity_invalid")
    return rows


def _release_python_universe(root: Path) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    try:
        for directory in PYTHON_ROOTS:
            base = root / directory
            if not base.is_dir() or base.is_symlink():
                continue
            for path in base.rglob("*.py"):
                relative = path.relative_to(root).as_posix()
                if path.is_symlink() or not path.is_file():
                    _abort("desktop_release_transitive_source_closure_invalid")
                result[relative] = _read_bytes(
                    path, code="desktop_release_transitive_source_closure_invalid",
                )
    except DesktopReleaseError:
        raise
    except Exception:
        _abort("desktop_release_transitive_source_closure_invalid")
    return result


def _validate_release_source_closure(
    files: dict[str, bytes], *, universe: dict[str, bytes] | None = None,
) -> None:
    try:
        validate_desktop_release_source_closure_v1(files, universe_files=universe)
    except DesktopReleaseSourceClosureError:
        _abort("desktop_release_transitive_source_closure_invalid")


def _tar_info(name: str, size: int, mode: int = 0o644) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = size; info.mode = mode; info.mtime = 0; info.uid = 0; info.gid = 0; info.uname = ""; info.gname = ""
    return info


def _signing_home() -> Path:
    configured = os.environ.get("PORTELYRA_SIGNING_HOME", "")
    return Path(configured) if configured else Path.home() / ".local" / "state" / "portelyra" / "signing"


def release_signer_v1(project_root: Path, *, trust_list: Path | None = None, signing_home: Path | None = None):
    """Wer das Release signiert (#486 Schritt 3). Traegt die Vertrauensliste des Projekts keinen Schluessel, wird nicht signiert (None).
    Sonst nur mit eingerichtetem Schluessel: Sicherungskopie bestaetigt, Hauptschluessel in der Liste und im eigenen Signatur-Agenten
    geladen (jede Signatur wird in einem Fenster bestaetigt).
    Die Passphrase fragt release-build nie ab. Jede Signatur wird gleich gegen die Liste geprueft."""
    from migrations.reference import plugin_signature_v1 as signature  # noqa: PLC0415
    root = _existing_directory(project_root, owner_only=False)
    trust = trust_list if trust_list is not None else root / "contracts" / "plugin-signing" / "v1" / "allowed_signers"
    if not signature.trusted_keys_v1(trust):
        return None
    home = signing_home if signing_home is not None else _signing_home()
    setup_path = home / "setup.json"
    try:
        if home.is_symlink() or not home.is_dir() or setup_path.is_symlink() or not setup_path.is_file() or setup_path.stat().st_size > 100_000:
            _abort("desktop_release_signing_not_set_up")
        setup = json.loads(setup_path.read_text(encoding="utf-8"))
        # Schluesselwechsel (rc.430): Das Uebergangs-Release signiert der bisherige Ersatzschluessel (setup.json `transition`).
        public = signature.active_signing_public_key_v1(home)
        key_line = signature.public_key_line_v1(public)
    except DesktopReleaseError:
        raise
    except Exception:
        _abort("desktop_release_signing_not_set_up")
    transition = setup.get("transition") if isinstance(setup, dict) else None
    expected = (transition.get("signer_public_key") if isinstance(transition, dict) else None) if transition is not None else \
        (setup.get("main_public_key") if isinstance(setup, dict) else None)
    if not isinstance(setup, dict) or setup.get("contract_version") != "portelyra_signing_setup_v1" or expected != key_line:
        _abort("desktop_release_signing_not_set_up")
    if not isinstance(setup.get("stick_copy_confirmed_at_utc"), str) or not setup["stick_copy_confirmed_at_utc"]:
        _abort("desktop_release_signing_copy_unconfirmed")
    if not signature.trust_list_contains_v1(public, trust):
        _abort("desktop_release_signing_key_untrusted")

    def sign(data: bytes) -> bytes:
        try:
            signed = signature.sign_with_agent_v1(data, public, signature.NAMESPACE_RELEASE, agent_socket=home / "agent.sock")
            signature.verify_signature_v1(data, signed, signature.NAMESPACE_RELEASE, trust)
        except signature.PluginSignatureBlocked as error:
            _abort({"signing_key_not_loaded": "desktop_release_signing_key_not_loaded",
                    "signing_declined": "desktop_release_signing_declined"}.get(error.code, "desktop_release_signing_failed"))
        if len(signed) > MAX_RELEASE_SIGNATURE_BYTES:
            _abort("desktop_release_signing_failed")
        return signed
    return sign


def release_signing_required_v1(product_version: str, signer) -> None:
    """Ein oeffentliches Release (Version ohne `-rc.`, etwa 0.3.0) nur signiert: Die Signatur schuetzt nur Updates, und eine leere Vertrauensliste nimmt jedes Update an - das erste oeffentliche Archiv
    muss den Schluessel tragen. Release Candidates bleiben unsigniert moeglich."""
    if signer is None and re.search(r"-rc[.][0-9]+$", str(product_version)) is None:
        _abort("desktop_release_signing_required_for_public_release")


def build_desktop_release_v1(project_root: Path, archive_path: Path, product_version: str, signer=None) -> dict[str, Any]:
    root = _existing_directory(project_root, owner_only=False)
    version = _version(product_version)
    version_bytes = _read_bytes(root / "VERSION", maximum=100, code="desktop_release_release_integrity_invalid")
    if version_bytes != (version + "\n").encode("utf-8"):
        _abort("desktop_release_release_integrity_invalid")
    package_version = re.sub(r"-rc[.][0-9]+$", "", version)
    for package in ("spotcore", "spotdisplay"):
        description = _read_bytes(root / "packages" / package / "DESCRIPTION", maximum=100_000, code="desktop_release_release_integrity_invalid").decode("utf-8")
        versions = [line.split(":", 1)[1].strip() for line in description.splitlines() if line.startswith("Version:")]
        if versions != [package_version]:
            _abort("desktop_release_release_integrity_invalid")
    rows = _release_registry(root)
    fixed = ["AGENTS.md", "VERSION", "contracts/desktop-product/v1/source-fingerprints.csv"]
    relative_paths = sorted(set(fixed + [row["path"] for row in rows]))
    declared = {row["path"]: row["sha256"] for row in rows}
    fixed_hashes = {relative: _sha_bytes(_read_bytes(root.joinpath(*relative.split("/")))) for relative in fixed}
    entries = []
    source_files: dict[str, bytes] = {}
    for relative in relative_paths:
        path = root.joinpath(*relative.split("/"))
        data = _read_bytes(path)
        digest = _sha_bytes(data)
        if relative in declared and digest != declared[relative] or relative in fixed_hashes and digest != fixed_hashes[relative]:
            _abort("desktop_release_release_integrity_invalid")
        source_files[relative] = data
        entries.append({"relative_path": relative, "byte_count": len(data), "bytes_fingerprint": digest})
    _validate_release_source_closure(source_files, universe=_release_python_universe(root))
    payload = {
        "desktop_release_version": 1,
        "release_format": "portelyra_linux_source_release_v1",
        "product_version": version,
        "platform": "linux_x86_64_source",
        "entry_count": len(entries),
        "entries": entries,
        "network_installation": False,
        "private_data_included": False,
    }
    manifest = {**payload, "release_manifest_fingerprint": _fingerprint(payload)}
    target, parent = _destination(archive_path)
    if target.exists():
        existing = validate_desktop_release_archive_v1(target)
        if existing["product_version"] != version:
            _abort("desktop_release_release_conflict")
        return _safe_result("release_build", "already_created")
    manifest_data = _canonical(manifest) + b"\n"
    signature_data = signer(manifest_data) if signer is not None else None
    stage = parent / f".{target.name}.portelyra-release-incoming"
    if stage.exists():
        if stage.is_symlink() or not stage.is_file():
            _abort("desktop_release_release_conflict")
        stage.unlink()
    prefix = f"portelyra-{version}"
    try:
        with stage.open("xb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=9) as zipped:
                with tarfile.open(fileobj=zipped, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    archive.addfile(_tar_info(f"{prefix}/release-manifest.json", len(manifest_data)), io.BytesIO(manifest_data))
                    if signature_data is not None:
                        archive.addfile(_tar_info(f"{prefix}/{RELEASE_SIGNATURE_NAME}", len(signature_data)), io.BytesIO(signature_data))
                    for row in entries:
                        data = _read_bytes(root.joinpath(*row["relative_path"].split("/")))
                        if len(data) != row["byte_count"] or _sha_bytes(data) != row["bytes_fingerprint"]:
                            _abort("desktop_release_release_integrity_invalid")
                        archive.addfile(_tar_info(f"{prefix}/{row['relative_path']}", len(data)), io.BytesIO(data))
            raw.flush(); os.fsync(raw.fileno())
        os.chmod(stage, 0o600)
        os.rename(stage, target); _fsync(parent)
    except DesktopReleaseError:
        if stage.exists():
            stage.unlink(missing_ok=True)
            _fsync(parent)
        raise
    except Exception:
        if stage.exists():
            stage.unlink(missing_ok=True)
            _fsync(parent)
        _abort("desktop_release_write_failed")
    try:
        validate_desktop_release_archive_v1(target)
    except DesktopReleaseError:
        target.unlink(missing_ok=True)
        _fsync(parent)
        raise
    result = _safe_result("release_build", "created")
    if signature_data is not None:
        result["signature"] = "valid"
    return result


def validate_desktop_release_archive_v1(archive_path: Path) -> dict[str, Any]:
    _assert_no_symlink_ancestry(archive_path)
    if archive_path.is_symlink() or not archive_path.is_file() or not _owner_only(archive_path):
        _abort("desktop_release_release_integrity_invalid")
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            members = archive.getmembers()
            if not members or any(member.issym() or member.islnk() or not member.isfile() or member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
                _abort("desktop_release_release_integrity_invalid")
            prefixes = {member.name.split("/", 1)[0] for member in members}
            if len(prefixes) != 1:
                _abort("desktop_release_release_integrity_invalid")
            prefix = next(iter(prefixes))
            by_name = {member.name: member for member in members}
            if len(by_name) != len(members):
                _abort("desktop_release_release_integrity_invalid")
            manifest_name = f"{prefix}/release-manifest.json"
            if manifest_name not in by_name or by_name[manifest_name].size > 4_000_000:
                _abort("desktop_release_release_integrity_invalid")
            extracted = archive.extractfile(by_name[manifest_name])
            if extracted is None:
                _abort("desktop_release_release_integrity_invalid")
            raw = extracted.read()
            manifest = json.loads(raw.decode("utf-8"))
            if raw != _canonical(manifest) + b"\n" or set(manifest) != {"desktop_release_version", "release_format", "product_version", "platform", "entry_count", "entries", "network_installation", "private_data_included", "release_manifest_fingerprint"}:
                _abort("desktop_release_release_integrity_invalid")
            if manifest["desktop_release_version"] != 1 or manifest["release_format"] != "portelyra_linux_source_release_v1" or manifest["platform"] != "linux_x86_64_source" or manifest["network_installation"] is not False or manifest["private_data_included"] is not False:
                _abort("desktop_release_release_integrity_invalid")
            version = _version(manifest["product_version"])
            if prefix != f"portelyra-{version}":
                _abort("desktop_release_release_integrity_invalid")
            entries = manifest["entries"]
            if not isinstance(entries, list) or not entries or manifest["entry_count"] != len(entries):
                _abort("desktop_release_release_integrity_invalid")
            expected_names = {manifest_name}; previous = ""; total = 0
            signature_name = f"{prefix}/{RELEASE_SIGNATURE_NAME}"
            if signature_name in by_name:
                if by_name[signature_name].size > MAX_RELEASE_SIGNATURE_BYTES:
                    _abort("desktop_release_release_integrity_invalid")
                expected_names.add(signature_name)
            source_files: dict[str, bytes] = {}
            for row in entries:
                if not isinstance(row, dict) or set(row) != {"relative_path", "byte_count", "bytes_fingerprint"} or not _relative_safe(row["relative_path"]) or row["relative_path"] <= previous or not isinstance(row["byte_count"], int) or isinstance(row["byte_count"], bool) or not 0 <= row["byte_count"] <= MAX_FILE_BYTES or not isinstance(row["bytes_fingerprint"], str) or SHA.fullmatch(row["bytes_fingerprint"]) is None:
                    _abort("desktop_release_release_integrity_invalid")
                previous = row["relative_path"]; total += row["byte_count"]
                if total > MAX_TOTAL_BYTES:
                    _abort("desktop_release_release_integrity_invalid")
                name = f"{prefix}/{row['relative_path']}"; expected_names.add(name)
                if name not in by_name or by_name[name].size != row["byte_count"]:
                    _abort("desktop_release_release_integrity_invalid")
                handle = archive.extractfile(by_name[name]); data = b"" if handle is None else handle.read(row["byte_count"] + 1)
                if len(data) != row["byte_count"] or _sha_bytes(data) != row["bytes_fingerprint"]:
                    _abort("desktop_release_release_integrity_invalid")
                source_files[row["relative_path"]] = data
            if set(by_name) != expected_names:
                _abort("desktop_release_release_integrity_invalid")
            body = {key: value for key, value in manifest.items() if key != "release_manifest_fingerprint"}
            if manifest["release_manifest_fingerprint"] != _fingerprint(body):
                _abort("desktop_release_release_integrity_invalid")
            _validate_release_source_closure(source_files)
            return manifest
    except DesktopReleaseError:
        raise
    except Exception:
        _abort("desktop_release_release_integrity_invalid")


def _release_signature_parts(archive_path: Path) -> tuple[dict[str, Any], bytes, bytes | None]:
    manifest = validate_desktop_release_archive_v1(archive_path)
    prefix = f"portelyra-{manifest['product_version']}"
    try:
        with tarfile.open(archive_path, mode="r:gz") as archive:
            names = set(archive.getnames())
            raw = archive.extractfile(f"{prefix}/release-manifest.json").read()
            signature = None
            if f"{prefix}/{RELEASE_SIGNATURE_NAME}" in names:
                signature = archive.extractfile(f"{prefix}/{RELEASE_SIGNATURE_NAME}").read(MAX_RELEASE_SIGNATURE_BYTES + 1)
    except Exception:
        _abort("desktop_release_release_integrity_invalid")
    return manifest, raw, signature


def release_archive_signature_v1(archive_path: Path, trust_list: Path) -> dict[str, Any]:
    """Signatur eines Release-Archivs gegen eine Vertrauensliste (#486 Schritt 3). Leere Liste: nicht verlangt ("not_required", wie vor dem
    ersten Schluessel). Sonst Pflicht ohne Ausnahme: fehlt, fremd, verfaelscht -> Abbruch mit Grund."""
    from migrations.reference import plugin_signature_v1 as signature  # noqa: PLC0415
    manifest, raw, signed = _release_signature_parts(archive_path)
    if not signature.trusted_keys_v1(trust_list):
        return {"signature": "not_required", "product_version": manifest["product_version"], "manifest": manifest}
    if not signed:
        _abort("desktop_release_signature_missing")
    try:
        signature.verify_signature_v1(raw, signed, signature.NAMESPACE_RELEASE, trust_list)
    except signature.PluginSignatureBlocked as error:
        _abort({"plugin_signature_missing": "desktop_release_signature_missing", "plugin_signature_untrusted": "desktop_release_signature_untrusted",
                "plugin_signature_tool_missing": "desktop_release_signature_tool_missing"}.get(error.code, "desktop_release_signature_invalid"))
    return {"signature": "valid", "product_version": manifest["product_version"], "manifest": manifest}


def stage_desktop_update_v1(archive_path: Path, staging: Path, trust_list: Path) -> dict[str, Any]:
    """Update aus einem Archiv (#486 Schritt 3): Das INSTALLIERTE Portelyra prueft, bevor Code aus dem Archiv laeuft. Kopiert das Archiv in
    einen eigenen, nur fuer den Besitzer lesbaren Ordner, prueft dort Aufbau, Pruefsummen und Signatur (gegen `trust_list`, die Liste des
    installierten Release) und entpackt nur die im Manifest genannten Dateien. Eingespielt wird danach wie beim Upgrade aus einem Ordner."""
    _assert_no_symlink_ancestry(staging, allow_missing_leaf=True)
    if staging.exists() or staging.is_symlink():
        _abort("desktop_release_update_conflict")
    _existing_directory(staging.parent)
    _assert_no_symlink_ancestry(archive_path)
    if archive_path.is_symlink() or not archive_path.is_file() or archive_path.stat().st_size > MAX_RELEASE_ARCHIVE_BYTES:
        _abort("desktop_release_release_integrity_invalid")
    os.mkdir(staging, 0o700)
    try:
        copy = staging / "release.tar.gz"
        with archive_path.open("rb") as source, copy.open("xb") as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
        os.chmod(copy, 0o600)
        checked = release_archive_signature_v1(copy, trust_list)
        manifest = checked["manifest"]
        version = manifest["product_version"]
        prefix = f"portelyra-{version}"
        root = staging / prefix
        with tarfile.open(copy, mode="r:gz") as archive:
            names = ["release-manifest.json"] + ([RELEASE_SIGNATURE_NAME] if f"{prefix}/{RELEASE_SIGNATURE_NAME}" in archive.getnames() else [])
            expected = {row["relative_path"]: (row["byte_count"], row["bytes_fingerprint"]) for row in manifest["entries"]}
            for relative in names + [row["relative_path"] for row in manifest["entries"]]:
                handle = archive.extractfile(f"{prefix}/{relative}")
                data = b"" if handle is None else handle.read(MAX_FILE_BYTES + 1)
                if relative in expected and (len(data) != expected[relative][0] or _sha_bytes(data) != expected[relative][1]):
                    _abort("desktop_release_release_integrity_invalid")
                path = root.joinpath(*relative.split("/"))
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(descriptor, "wb") as written:
                    written.write(data)
        copy.unlink()
        _fsync(staging)
    except DesktopReleaseError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        _abort("desktop_release_update_conflict")
    return {"status": "staged", "operation": "release_update_stage", "product_version": version, "signature": checked["signature"],
            "safe_output": True}


def _completed_desktop_workflow(home: Path, registry: Mapping[str, Any]) -> None:
    workflow = _data_space_path(home, registry) / "artifacts" / "desktop_workflow"
    try:
        from apps.reference.latest_run_reader_v1 import LatestRunReaderContext, read_latest_completed_run_v1
        artifact = read_latest_completed_run_v1(
            workflow,
            LatestRunReaderContext(
                registry["tenant_id"], registry["user_id"], registry["active_data_space_id"],
                "desktop_workflow", "viewer",
            ),
        )
    except Exception:
        _abort("desktop_release_acceptance_artifact_missing")
    if artifact.get("status") != "completed" or artifact.get("attempt_status") != "completed":
        _abort("desktop_release_acceptance_artifact_missing")


def bind_restored_data_space_v1(capability: DesktopReleaseCapability, target_home: Path) -> dict[str, Any]:
    """Restore bindet neu (#493, Festlegung 11.11.2026): Nach einem Restore an einen anderen Ort den Ursprung der
    pfadgebundenen Speicher vermerken. Der Hinweis kommt aus der laufenden Installation (deren Ursprung), sonst aus den Auftraegen des
    Run Centers; vermerkt wird erst nach der Pruefung gegen die gespeicherten Bindungen. Der Restore selbst bleibt davon unberuehrt:
    misslingt das Binden, meldet das Ergebnis es (dann `relocate`, notfalls mit `--origin`)."""
    from migrations.reference.data_space_relocation_v1 import DataSpaceRelocationV1Error, origin_v1, relocate_v1  # noqa: PLC0415
    try:
        current_home, current_registry = _validate_capability(capability)
        target = target_home.resolve(strict=True)
        space = _data_space_path(target, _registry(target / "desktop-runtime.json"))
        if not space.is_dir():
            return {"relocation": "not_possible"}
        hint = origin_v1(_data_space_path(current_home, current_registry))
        return {"relocation": relocate_v1(space, True, hints=[hint])["status"]}
    except DataSpaceRelocationV1Error as error:
        return {"relocation": "unverified" if error.code == "data_space_relocation_unverified" else "not_possible"}
    except Exception:
        return {"relocation": "not_possible"}


def private_acceptance_check_v1(capability: DesktopReleaseCapability, bundle_directory: Path, restored_home: Path) -> dict[str, Any]:
    try:
        source, registry = _validate_capability(capability)
        source_entries = _settled_source_entries(source, registry)
        manifest = validate_desktop_backup_v1(bundle_directory)
        restored = _existing_directory(restored_home)
        restored_registry = _registry(restored / "desktop-runtime.json")
        restored_entries = _settled_source_entries(restored, restored_registry)
        expected = _without_run_lock(manifest["entries"])   # ein aelteres Backup fuehrt die Laufsperre noch (rc.416)
        if _context(registry) != _context(restored_registry) or source_entries != restored_entries or _fingerprint(expected) != _fingerprint(source_entries):
            _abort("desktop_release_acceptance_failed")
        _completed_desktop_workflow(source, registry)
        _completed_desktop_workflow(restored, restored_registry)
        return {"status": "pass"}
    except DesktopReleaseError as error:
        return {"status": "fail", "code": error.code}
    except Exception:
        return {"status": "fail", "code": "desktop_release_acceptance_failed"}


__all__ = [
    "DESKTOP_RELEASE_VERSION", "DesktopReleaseCapability", "DesktopReleaseError",
    "backup_summary_desktop_v1", "build_desktop_release_v1", "create_desktop_backup_v1", "desktop_release_error_codes_v1",
    "list_desktop_backups_v1", "prune_desktop_backups_v1", "version_key_v1", "restore_into_fresh_home_v1",
    "new_desktop_release_capability_v1", "preflight_desktop_restore_v1",
    "bind_restored_data_space_v1", "private_acceptance_check_v1", "restore_desktop_backup_v1",
    "validate_desktop_backup_v1", "validate_desktop_release_archive_v1",
]
