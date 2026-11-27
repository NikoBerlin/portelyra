"""Atomic immutable run publication reference for synthetic artifacts only."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any

from migrations.reference.publication_limits_v1 import MAX_ARTIFACT_BYTES
from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference.legacy_import_data_command_v1 import (
    DataCommandError,
    canonical_json_bytes,
    fingerprint,
)

PUBLICATION_CONTRACT_VERSION = 1
AREA_WRITERS = {
    "analysis_snapshot": "analysis_worker",
    "group_projection": "group_projection_writer",
    "market_snapshot": "market_worker",
    "market_analysis": "analysis_worker",
    "portfolio_snapshot": "portfolio_worker",
    "tax_report": "tax_worker",
    "trade_analysis": "analysis_worker",
    "desktop_workflow": "desktop_workflow_worker",
    # Tageshistorie fuer die Analyse (#473)
    "portfolio_history": "portfolio_history_worker",
    # Anzeige-Einstellungen fuer Cockpit, Steuer und Analyse (#500)
    "display_settings": "display_settings_worker",
    # Momentaufnahme (rc.313, #478): dieselbe Form wie der Stichtags-Snapshot, mit den zuletzt abgerufenen Kursen.
    "intraday_snapshot": "portfolio_worker",
    # Datenbasis (rc.314, #478): Grundlagen ohne Werte und GuV fuer die Datenbasis-App.
    "data_basis": "data_basis_worker",
    # Stand der Aktualisierung fuer alle Apps (#540, rc.366): was laeuft, seit wann, wie weit.
    "activity_status": "activity_status_worker",
}
AREA_ARTIFACT_CONTRACTS = {
    "analysis_snapshot": {"analysis_snapshot_v1"},
    "group_projection": {"cockpit_group_drilldown_v1"},
    "market_snapshot": {"manual_market_input_v1"},
    "market_analysis": {"market_analysis_v1"},
    "portfolio_snapshot": {"portfolio_snapshot_v1", "portfolio_snapshot_v1_1", "portfolio_snapshot_v2", "portfolio_snapshot_v3", "portfolio_snapshot_v4", "portfolio_snapshot_v5"},
    "tax_report": {"tax_report_v1", "tax_report_v1_1", "tax_report_v2"},
    "trade_analysis": {"trade_analysis_v1"},
    "desktop_workflow": {"desktop_workflow_v1"},
    "portfolio_history": {"portfolio_history_v1"},
    "display_settings": {"display_settings_v1"},
    "intraday_snapshot": {"portfolio_snapshot_v5"},
    "data_basis": {"data_basis_v1"},
    "activity_status": {"activity_status_v1"},
}
RUN_PUBLICATION_FAILURE_CODES = frozenset(
    {
        "run_publication_input_invalid",
        "run_publication_runtime_invalid",
        "run_publication_root_invalid",
        "run_publication_symlink_rejected",
        "run_publication_lock_unavailable",
        "run_publication_latest_invalid",
        "run_publication_artifact_fingerprint_invalid",
        "run_publication_run_conflict",
        "run_publication_run_exists_not_latest",
        "run_publication_incoming_exists",
        "run_publication_write_failed",
        "run_publication_reader_context_mismatch",
        "run_publication_reader_integrity_invalid",
        "run_publication_no_latest",
        "run_publication_boundary_failed",
        "synthetic_publication_failpoint",
    }
)
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_ID = re.compile(r"[a-z0-9_]+")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_MAX_ARTIFACT_BYTES = MAX_ARTIFACT_BYTES


class RunPublicationError(RuntimeError):
    """Fail-closed publication error carrying only a safe registered code."""

    def __init__(self, code: str):
        if code not in RUN_PUBLICATION_FAILURE_CODES:
            raise ValueError("unregistered_run_publication_error_code")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class PublicationRuntimeContext:
    tenant_id: str
    user_id: str
    data_space_id: str
    area_id: str
    writer_id: str
    writer_role: str


@dataclass(frozen=True)
class RunPublicationResult:
    status: str
    run_id: str
    area_id: str
    artifact_fingerprint: str
    manifest_fingerprint: str


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        raise RunPublicationError("run_publication_input_invalid")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise RunPublicationError("run_publication_input_invalid") from None


def _runtime_valid(runtime: PublicationRuntimeContext) -> bool:
    return (
        isinstance(runtime, PublicationRuntimeContext)
        and runtime.area_id in AREA_WRITERS
        and AREA_WRITERS[runtime.area_id] == runtime.writer_role
        and isinstance(runtime.data_space_id, str)
        and runtime.data_space_id.startswith("sbx_")
        and 8 <= len(runtime.data_space_id) <= 64
        and _ID.fullmatch(runtime.data_space_id) is not None
        and all(
            isinstance(value, str)
            and 3 <= len(value) <= 80
            and re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None
            for value in (runtime.tenant_id, runtime.user_id, runtime.writer_id)
        )
    )


def _run_id_valid(run_id: Any) -> bool:
    return (
        isinstance(run_id, str)
        and run_id.startswith("run_")
        and 8 <= len(run_id) <= 64
        and _ID.fullmatch(run_id) is not None
    )


def _root_valid(root: Any) -> Path:
    if not isinstance(root, Path) or not root.is_absolute() or not root.exists() or not root.is_dir():
        raise RunPublicationError("run_publication_root_invalid")
    if root.is_symlink():
        raise RunPublicationError("run_publication_symlink_rejected")
    return root


def _ensure_real_directory(path: Path) -> None:
    if path.is_symlink():
        raise RunPublicationError("run_publication_symlink_rejected")
    if path.exists():
        if not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
            raise RunPublicationError("run_publication_root_invalid")
        return
    path.mkdir(mode=0o700)
    os.chmod(path, 0o700)
    if path.is_symlink() or not path.is_dir() or stat.S_IMODE(path.stat().st_mode) != 0o700:
        raise RunPublicationError("run_publication_symlink_rejected")
    settle_new_directory_v1(path)   # #568: mit Passwortschutz auch die gocryptfs.diriv des neuen Ordners festschreiben


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exclusive_write(path: Path, payload: bytes, mode: int = 0o600) -> None:
    if path.is_symlink():
        raise RunPublicationError("run_publication_symlink_rejected")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, mode)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RunPublicationError("run_publication_write_failed")
            offset += written
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_bytes(path: Path, maximum: int = _MAX_ARTIFACT_BYTES) -> bytes:
    if path.is_symlink():
        raise RunPublicationError("run_publication_symlink_rejected")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        if path.is_symlink():
            raise RunPublicationError("run_publication_symlink_rejected") from None
        raise RunPublicationError("run_publication_reader_integrity_invalid") from None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
            raise RunPublicationError("run_publication_reader_integrity_invalid")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > maximum:
            raise RunPublicationError("run_publication_reader_integrity_invalid")
        return payload
    finally:
        os.close(descriptor)


def _read_json(path: Path, maximum: int = 1_000_000) -> dict[str, Any]:
    try:
        value = json.loads(_read_bytes(path, maximum).decode("utf-8", errors="strict"))
    except RunPublicationError:
        raise
    except Exception:
        raise RunPublicationError("run_publication_reader_integrity_invalid") from None
    if not isinstance(value, dict):
        raise RunPublicationError("run_publication_reader_integrity_invalid")
    return value


def _artifact_envelope(
    artifact: dict[str, Any],
    runtime: PublicationRuntimeContext,
) -> tuple[str, str, str, bytes]:
    if not isinstance(artifact, dict) or artifact.get("status") != "completed":
        raise RunPublicationError("run_publication_input_invalid")
    if (
        artifact.get("tenant_id") != runtime.tenant_id
        or artifact.get("user_id") != runtime.user_id
        or artifact.get("data_space_id") != runtime.data_space_id
    ):
        raise RunPublicationError("run_publication_runtime_invalid")
    if runtime.area_id == "analysis_snapshot":
        if artifact.get("analysis_snapshot_version") != 1 or artifact.get("scope_status") != "portfolio_valuation_decomposition_only":
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "analysis_snapshot_v1"
        artifact_id = artifact.get("analysis_snapshot_id")
    elif runtime.area_id == "group_projection":
        if artifact.get("cockpit_group_artifact_version") != 1:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "cockpit_group_drilldown_v1"
        artifact_id = artifact.get("cockpit_group_artifact_id")
    elif runtime.area_id == "trade_analysis":
        if artifact.get("trade_analysis_artifact_version") != 1 or artifact.get("market_status") != "unavailable_m4_required":
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "trade_analysis_v1"
        artifact_id = artifact.get("trade_analysis_artifact_id")
    elif runtime.area_id == "market_analysis":
        if artifact.get("market_analysis_artifact_version") != 1:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "market_analysis_v1"
        artifact_id = artifact.get("market_analysis_artifact_id")
    elif runtime.area_id == "market_snapshot":
        if artifact.get("market_snapshot_version") != 1 or artifact.get("source_kind") != "manual_user_input":
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "manual_market_input_v1"
        artifact_id = artifact.get("market_snapshot_id")
    elif runtime.area_id == "desktop_workflow":
        if artifact.get("desktop_workflow_artifact_version") != 1:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "desktop_workflow_v1"
        artifact_id = artifact.get("desktop_workflow_artifact_id")
    elif runtime.area_id == "display_settings":
        if artifact.get("display_settings_version") != 1:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "display_settings_v1"
        artifact_id = artifact.get("display_settings_id")
    elif runtime.area_id == "activity_status":
        if artifact.get("activity_status_version") != 1:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "activity_status_v1"
        artifact_id = artifact.get("activity_status_id")
    elif runtime.area_id == "portfolio_history":
        if artifact.get("portfolio_history_version") != 1:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "portfolio_history_v1"
        artifact_id = artifact.get("portfolio_history_id")
    elif runtime.area_id == "data_basis":
        if artifact.get("data_basis_version") != 1:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "data_basis_v1"
        artifact_id = artifact.get("data_basis_id")
    elif runtime.area_id == "intraday_snapshot":
        # Die Momentaufnahme (rc.313): Fassung 5 des Snapshots, eigener Bereich.
        if artifact.get("portfolio_snapshot_version") != 5:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = "portfolio_snapshot_v5"
        artifact_id = artifact.get("snapshot_id")
    elif runtime.area_id == "portfolio_snapshot":
        version = artifact.get("portfolio_snapshot_version")
        if version not in {1, 2, 3, 4, 5, 101}:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = {
            1: "portfolio_snapshot_v1",
            2: "portfolio_snapshot_v2",
            # v3 traegt die Frische je Ebene und laesst Cash offen, statt es zu
            # erzwingen: Ein nicht erklaerter Bestand ist nicht null (#373).
            3: "portfolio_snapshot_v3",
            # v4 weist den belegten Cash-Bestand je Konto mit seinem Datum aus.
            4: "portfolio_snapshot_v4",
            # v5 fuehrt aus Bewegungen abgeleitete Salden als eigene Art.
            5: "portfolio_snapshot_v5",
            101: "portfolio_snapshot_v1_1",
        }[version]
        artifact_id = artifact.get("snapshot_id")
    else:
        version = artifact.get("tax_report_version")
        if version not in {1, 2, 101}:
            raise RunPublicationError("run_publication_input_invalid")
        artifact_contract = {
            1: "tax_report_v1",
            2: "tax_report_v2",
            101: "tax_report_v1_1",
        }[version]
        artifact_id = artifact.get("tax_report_id")
    if not isinstance(artifact_id, str) or not 8 <= len(artifact_id) <= 80 or _ID.fullmatch(artifact_id) is None:
        raise RunPublicationError("run_publication_input_invalid")
    artifact_fingerprint = artifact.get("artifact_fingerprint")
    if not isinstance(artifact_fingerprint, str) or _SHA256.fullmatch(artifact_fingerprint) is None:
        raise RunPublicationError("run_publication_artifact_fingerprint_invalid")
    try:
        recomputed = fingerprint({key: artifact[key] for key in artifact if key != "artifact_fingerprint"})
        artifact_bytes = canonical_json_bytes(artifact) + b"\n"
    except DataCommandError:
        raise RunPublicationError("run_publication_artifact_fingerprint_invalid") from None
    if recomputed != artifact_fingerprint or len(artifact_bytes) > _MAX_ARTIFACT_BYTES:
        raise RunPublicationError("run_publication_artifact_fingerprint_invalid")
    completed_at = artifact.get("completed_at_utc")
    _utc(completed_at)
    return artifact_contract, artifact_id, completed_at, artifact_bytes


def _manifest_valid(manifest: dict[str, Any]) -> bool:
    required = {
        "publication_contract_version",
        "area_id",
        "run_id",
        "tenant_id",
        "user_id",
        "data_space_id",
        "writer_id",
        "writer_role",
        "artifact_contract",
        "artifact_id",
        "artifact_file",
        "artifact_fingerprint",
        "artifact_bytes_fingerprint",
        "completed_at_utc",
        "published_at_utc",
        "manifest_fingerprint",
    }
    if not isinstance(manifest, dict) or set(manifest) != required:
        return False
    if manifest["publication_contract_version"] != PUBLICATION_CONTRACT_VERSION or manifest["artifact_file"] != "artifact.json":
        return False
    if not _run_id_valid(manifest["run_id"]):
        return False
    if not all(isinstance(manifest[key], str) and _SHA256.fullmatch(manifest[key]) for key in (
        "artifact_fingerprint",
        "artifact_bytes_fingerprint",
        "manifest_fingerprint",
    )):
        return False
    if (
        manifest["area_id"] not in AREA_WRITERS
        or AREA_WRITERS[manifest["area_id"]] != manifest["writer_role"]
        or manifest["artifact_contract"] not in AREA_ARTIFACT_CONTRACTS[manifest["area_id"]]
        or not isinstance(manifest["data_space_id"], str)
        or not manifest["data_space_id"].startswith("sbx_")
        or _ID.fullmatch(manifest["data_space_id"]) is None
        or not all(
            isinstance(manifest[key], str)
            and 3 <= len(manifest[key]) <= 80
            and re.fullmatch(r"[A-Za-z0-9_-]+", manifest[key]) is not None
            for key in ("tenant_id", "user_id", "writer_id")
        )
        or not isinstance(manifest["artifact_contract"], str)
        or _ID.fullmatch(manifest["artifact_contract"]) is None
        or not isinstance(manifest["artifact_id"], str)
        or _ID.fullmatch(manifest["artifact_id"]) is None
    ):
        return False
    try:
        if _utc(manifest["published_at_utc"]) < _utc(manifest["completed_at_utc"]):
            return False
    except RunPublicationError:
        return False
    payload = {key: manifest[key] for key in manifest if key != "manifest_fingerprint"}
    try:
        return fingerprint(payload) == manifest["manifest_fingerprint"]
    except DataCommandError:
        return False


def _latest_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "publication_contract_version": PUBLICATION_CONTRACT_VERSION,
        "area_id": manifest["area_id"],
        "run_id": manifest["run_id"],
        "tenant_id": manifest["tenant_id"],
        "user_id": manifest["user_id"],
        "data_space_id": manifest["data_space_id"],
        "manifest_fingerprint": manifest["manifest_fingerprint"],
        "artifact_fingerprint": manifest["artifact_fingerprint"],
    }
    result = dict(payload)
    result["latest_fingerprint"] = fingerprint(payload)
    return result


def _latest_valid(latest: dict[str, Any]) -> bool:
    required = {
        "publication_contract_version",
        "area_id",
        "run_id",
        "tenant_id",
        "user_id",
        "data_space_id",
        "manifest_fingerprint",
        "artifact_fingerprint",
        "latest_fingerprint",
    }
    if not isinstance(latest, dict) or set(latest) != required or latest["publication_contract_version"] != 1:
        return False
    if (
        latest["area_id"] not in AREA_WRITERS
        or not _run_id_valid(latest["run_id"])
        or not all(isinstance(latest[key], str) and _SHA256.fullmatch(latest[key]) for key in (
            "manifest_fingerprint",
            "artifact_fingerprint",
            "latest_fingerprint",
        ))
    ):
        return False
    payload = {key: latest[key] for key in latest if key != "latest_fingerprint"}
    try:
        return fingerprint(payload) == latest["latest_fingerprint"]
    except DataCommandError:
        return False


def _validate_completed_run(run_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if run_directory.is_symlink() or not run_directory.is_dir():
        raise RunPublicationError("run_publication_reader_integrity_invalid")
    expected_names = {"artifact.json", "manifest.json", "SUCCESS"}
    if {item.name for item in run_directory.iterdir()} != expected_names:
        raise RunPublicationError("run_publication_reader_integrity_invalid")
    manifest_bytes = _read_bytes(run_directory / "manifest.json", 1_000_000)
    manifest = _read_json(run_directory / "manifest.json")
    if (
        not _manifest_valid(manifest)
        or manifest["run_id"] != run_directory.name
        or manifest_bytes != canonical_json_bytes(manifest) + b"\n"
    ):
        raise RunPublicationError("run_publication_reader_integrity_invalid")
    artifact_bytes = _read_bytes(run_directory / "artifact.json")
    if hashlib.sha256(artifact_bytes).hexdigest() != manifest["artifact_bytes_fingerprint"]:
        raise RunPublicationError("run_publication_reader_integrity_invalid")
    try:
        artifact = json.loads(artifact_bytes.decode("utf-8"))
    except Exception:
        raise RunPublicationError("run_publication_reader_integrity_invalid") from None
    if not isinstance(artifact, dict) or artifact_bytes != canonical_json_bytes(artifact) + b"\n":
        raise RunPublicationError("run_publication_reader_integrity_invalid")
    try:
        artifact_fingerprint = fingerprint({key: artifact[key] for key in artifact if key != "artifact_fingerprint"})
    except DataCommandError:
        raise RunPublicationError("run_publication_reader_integrity_invalid") from None
    if artifact.get("artifact_fingerprint") != artifact_fingerprint or artifact_fingerprint != manifest["artifact_fingerprint"]:
        raise RunPublicationError("run_publication_reader_integrity_invalid")
    success = _read_json(run_directory / "SUCCESS")
    if success != {"run_id": manifest["run_id"], "manifest_fingerprint": manifest["manifest_fingerprint"]}:
        raise RunPublicationError("run_publication_reader_integrity_invalid")
    return manifest, artifact


def _failpoint(fail_at: str | None, stage: str) -> None:
    if fail_at == stage:
        raise RunPublicationError("synthetic_publication_failpoint")


def _publish_completed_run_v1_impl(
    area_root: Path,
    runtime: PublicationRuntimeContext,
    run_id: str,
    artifact: dict[str, Any],
    published_at_utc: str,
    fail_at: str | None,
) -> RunPublicationResult:
    if not _runtime_valid(runtime):
        raise RunPublicationError("run_publication_runtime_invalid")
    if not _run_id_valid(run_id):
        raise RunPublicationError("run_publication_input_invalid")
    allowed_failpoints = {None, "after_artifact", "after_manifest", "after_success", "after_run_publish", "after_latest_temp"}
    if fail_at not in allowed_failpoints:
        raise RunPublicationError("run_publication_input_invalid")
    root = _root_valid(area_root)
    artifact_contract, artifact_id, completed_at_utc, artifact_bytes = _artifact_envelope(artifact, runtime)
    completed = _utc(completed_at_utc)
    published = _utc(published_at_utc)
    if published < completed:
        raise RunPublicationError("run_publication_input_invalid")
    incoming_root = root / "incoming"
    runs_root = root / "runs"
    _ensure_real_directory(incoming_root)
    _ensure_real_directory(runs_root)
    latest_path = root / "latest.json"
    lock_path = root / "publication.lock"
    incoming_run = incoming_root / run_id
    final_run = runs_root / run_id
    latest_temp = root / f"latest_{run_id}.tmp"

    if latest_path.is_symlink():
        raise RunPublicationError("run_publication_symlink_rejected")
    existing_latest: dict[str, Any] | None = None
    if latest_path.exists():
        existing_latest = _read_json(latest_path)
        if not _latest_valid(existing_latest):
            raise RunPublicationError("run_publication_latest_invalid")
        if (
            existing_latest["area_id"] != runtime.area_id
            or existing_latest["tenant_id"] != runtime.tenant_id
            or existing_latest["user_id"] != runtime.user_id
            or existing_latest["data_space_id"] != runtime.data_space_id
        ):
            raise RunPublicationError("run_publication_latest_invalid")
    if lock_path.is_symlink():
        raise RunPublicationError("run_publication_symlink_rejected")
    try:
        _exclusive_write(
            lock_path,
            canonical_json_bytes(
                {
                    "run_id": run_id,
                    "area_id": runtime.area_id,
                    "writer_id": runtime.writer_id,
                }
            ) + b"\n",
        )
    except FileExistsError:
        raise RunPublicationError("run_publication_lock_unavailable") from None
    except RunPublicationError:
        raise
    except Exception:
        raise RunPublicationError("run_publication_lock_unavailable") from None

    lock_acquired = True
    final_published = False
    try:
        if final_run.is_symlink():
            raise RunPublicationError("run_publication_symlink_rejected")
        if final_run.exists():
            try:
                existing_manifest, _ = _validate_completed_run(final_run)
            except RunPublicationError:
                raise RunPublicationError("run_publication_run_conflict") from None
            if (
                existing_manifest["artifact_fingerprint"] != artifact["artifact_fingerprint"]
                or existing_manifest["area_id"] != runtime.area_id
                or existing_manifest["tenant_id"] != runtime.tenant_id
                or existing_manifest["user_id"] != runtime.user_id
                or existing_manifest["data_space_id"] != runtime.data_space_id
                or existing_manifest["writer_id"] != runtime.writer_id
                or existing_manifest["writer_role"] != runtime.writer_role
                or existing_manifest["artifact_contract"] != artifact_contract
                or existing_manifest["artifact_id"] != artifact_id
            ):
                raise RunPublicationError("run_publication_run_conflict")
            if existing_latest is not None and existing_latest["run_id"] == run_id and existing_latest["manifest_fingerprint"] == existing_manifest["manifest_fingerprint"]:
                return RunPublicationResult(
                    "already_published",
                    run_id,
                    runtime.area_id,
                    existing_manifest["artifact_fingerprint"],
                    existing_manifest["manifest_fingerprint"],
                )
            raise RunPublicationError("run_publication_run_exists_not_latest")
        if incoming_run.is_symlink() or latest_temp.is_symlink():
            raise RunPublicationError("run_publication_symlink_rejected")
        if incoming_run.exists() or latest_temp.exists():
            raise RunPublicationError("run_publication_incoming_exists")
        incoming_run.mkdir(mode=0o700)
        os.chmod(incoming_run, 0o700)
        _exclusive_write(incoming_run / "artifact.json", artifact_bytes)
        _failpoint(fail_at, "after_artifact")
        manifest_payload = {
            "publication_contract_version": PUBLICATION_CONTRACT_VERSION,
            "area_id": runtime.area_id,
            "run_id": run_id,
            "tenant_id": runtime.tenant_id,
            "user_id": runtime.user_id,
            "data_space_id": runtime.data_space_id,
            "writer_id": runtime.writer_id,
            "writer_role": runtime.writer_role,
            "artifact_contract": artifact_contract,
            "artifact_id": artifact_id,
            "artifact_file": "artifact.json",
            "artifact_fingerprint": artifact["artifact_fingerprint"],
            "artifact_bytes_fingerprint": hashlib.sha256(artifact_bytes).hexdigest(),
            "completed_at_utc": completed_at_utc,
            "published_at_utc": published_at_utc,
        }
        manifest = dict(manifest_payload)
        manifest["manifest_fingerprint"] = fingerprint(manifest_payload)
        _exclusive_write(incoming_run / "manifest.json", canonical_json_bytes(manifest) + b"\n")
        _failpoint(fail_at, "after_manifest")
        success = {"run_id": run_id, "manifest_fingerprint": manifest["manifest_fingerprint"]}
        _exclusive_write(incoming_run / "SUCCESS", canonical_json_bytes(success) + b"\n")
        _failpoint(fail_at, "after_success")
        _fsync_directory(incoming_run)
        # #568: Bevor der Lauf sichtbar wird und latest.json auf ihn zeigt, auch seine gocryptfs.diriv festschreiben - sonst kann ein
        # Neustart einen unlesbaren Lauf hinterlassen, auf den latest.json zeigt (17.11.2026).
        settle_new_directory_v1(incoming_run)
        os.rename(incoming_run, final_run)
        final_published = True
        _fsync_directory(incoming_root)
        _fsync_directory(runs_root)
        _failpoint(fail_at, "after_run_publish")
        latest = _latest_payload(manifest)
        _exclusive_write(latest_temp, canonical_json_bytes(latest) + b"\n")
        reread_latest = _read_json(latest_temp)
        if not _latest_valid(reread_latest) or reread_latest != latest:
            raise RunPublicationError("run_publication_write_failed")
        _failpoint(fail_at, "after_latest_temp")
        os.replace(latest_temp, latest_path)
        _fsync_directory(root)
        return RunPublicationResult(
            "published",
            run_id,
            runtime.area_id,
            manifest["artifact_fingerprint"],
            manifest["manifest_fingerprint"],
        )
    except RunPublicationError:
        raise
    except Exception:
        raise RunPublicationError("run_publication_write_failed") from None
    finally:
        if not final_published and incoming_run.exists() and not incoming_run.is_symlink():
            shutil.rmtree(incoming_run)
        if latest_temp.exists() and not latest_temp.is_symlink():
            latest_temp.unlink()
        if lock_acquired and lock_path.exists() and not lock_path.is_symlink():
            lock_path.unlink()
            _fsync_directory(root)


def publish_completed_run_v1(
    area_root: Path,
    runtime: PublicationRuntimeContext,
    run_id: str,
    artifact: dict[str, Any],
    published_at_utc: str,
    fail_at: str | None = None,
) -> RunPublicationResult:
    """Publish one already completed artifact without automatic retry."""

    try:
        return _publish_completed_run_v1_impl(
            area_root,
            runtime,
            run_id,
            artifact,
            published_at_utc,
            fail_at,
        )
    except RunPublicationError:
        raise
    except Exception:
        raise RunPublicationError("run_publication_boundary_failed") from None
