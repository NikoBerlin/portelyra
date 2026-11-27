"""Read-only latest-run repository adapter with no Worker publication capability."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

from migrations.reference.publication_limits_v1 import MAX_ARTIFACT_BYTES

LATEST_RUN_READER_FAILURE_CODES = frozenset(
    {
        "run_publication_root_invalid",
        "run_publication_symlink_rejected",
        "run_publication_reader_context_mismatch",
        "run_publication_reader_integrity_invalid",
        "run_publication_no_latest",
        "run_publication_boundary_failed",
    }
)
_AREA_ROLES = {
    "analysis_snapshot": {"analysis_viewer"},
    "group_projection": {"owner", "viewer", "desktop_owner"},
    "market_snapshot": {"portfolio_worker"},
    "market_analysis": {"viewer", "analysis_viewer"},
    "portfolio_snapshot": {"owner", "viewer", "desktop_owner"},
    "tax_report": {"owner", "viewer", "desktop_owner", "tax_viewer"},
    "trade_analysis": {"viewer", "tax_viewer", "analysis_viewer"},
    "desktop_workflow": {"viewer", "tax_viewer", "analysis_viewer"},
    # Tageshistorie (#473): die Analyse zeigt sie, die Data-App prueft ihre Veroeffentlichung.
    "portfolio_history": {"analysis_viewer", "desktop_owner"},
    # Anzeige-Einstellungen (#500): jede anzeigende App liest sie, die Data-App prueft ihre Veroeffentlichung.
    "display_settings": {"viewer", "tax_viewer", "analysis_viewer", "desktop_owner"},
    # Momentaufnahme (rc.313): Die Data-App veroeffentlicht und prueft sie, die Analyse zeigt sie.
    "intraday_snapshot": {"analysis_viewer", "desktop_owner"},
    # Datenbasis (rc.314, #478): Die Data-App veroeffentlicht sie, die Datenbasis-App zeigt sie.
    "data_basis": {"viewer"},
    # Stand der Aktualisierung (#540, rc.366): der Hintergrundlauf veroeffentlicht ihn, alle Apps zeigen ihn links.
    "activity_status": {"viewer", "tax_viewer", "analysis_viewer", "desktop_owner"},
}
_AREA_WRITERS = {
    "analysis_snapshot": "analysis_worker",
    "group_projection": "group_projection_writer",
    "market_snapshot": "market_worker",
    "market_analysis": "analysis_worker",
    "portfolio_snapshot": "portfolio_worker",
    "tax_report": "tax_worker",
    "trade_analysis": "analysis_worker",
    "desktop_workflow": "desktop_workflow_worker",
    "portfolio_history": "portfolio_history_worker",
    "display_settings": "display_settings_worker",
    "intraday_snapshot": "portfolio_worker",
    "data_basis": "data_basis_worker",
    "activity_status": "activity_status_worker",
}
_AREA_ARTIFACT_CONTRACTS = {
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
_ID = re.compile(r"[a-z0-9_]+")
_SHA256 = re.compile(r"[a-f0-9]{64}")
_MAX_ARTIFACT_BYTES = MAX_ARTIFACT_BYTES


class LatestRunReaderError(RuntimeError):
    def __init__(self, code: str):
        if code not in LATEST_RUN_READER_FAILURE_CODES:
            raise ValueError("unregistered_latest_run_reader_error_code")
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LatestRunReaderContext:
    tenant_id: str
    user_id: str
    data_space_id: str
    area_id: str
    role: str


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _context_valid(runtime: LatestRunReaderContext) -> bool:
    return (
        isinstance(runtime, LatestRunReaderContext)
        and runtime.area_id in _AREA_ROLES
        and runtime.role in _AREA_ROLES[runtime.area_id]
        and isinstance(runtime.data_space_id, str)
        and runtime.data_space_id.startswith("sbx_")
        and _ID.fullmatch(runtime.data_space_id) is not None
        and all(
            isinstance(value, str)
            and 3 <= len(value) <= 80
            and re.fullmatch(r"[A-Za-z0-9_-]+", value) is not None
            for value in (runtime.tenant_id, runtime.user_id)
        )
    )


def _root(root: Any) -> Path:
    if not isinstance(root, Path) or not root.is_absolute() or not root.exists() or not root.is_dir():
        raise LatestRunReaderError("run_publication_root_invalid")
    if root.is_symlink():
        raise LatestRunReaderError("run_publication_symlink_rejected")
    return root


def _read_bytes(path: Path, maximum: int) -> bytes:
    if path.is_symlink():
        raise LatestRunReaderError("run_publication_symlink_rejected")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        if path.is_symlink():
            raise LatestRunReaderError("run_publication_symlink_rejected") from None
        raise LatestRunReaderError("run_publication_reader_integrity_invalid") from None
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
            raise LatestRunReaderError("run_publication_reader_integrity_invalid")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        result = b"".join(chunks)
        if len(result) > maximum:
            raise LatestRunReaderError("run_publication_reader_integrity_invalid")
        return result
    finally:
        os.close(descriptor)


def _read_canonical_json(path: Path, maximum: int) -> tuple[dict[str, Any], bytes]:
    raw = _read_bytes(path, maximum)
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except Exception:
        raise LatestRunReaderError("run_publication_reader_integrity_invalid") from None
    if not isinstance(value, dict) or raw != _canonical_bytes(value) + b"\n":
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    return value, raw


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
        latest["area_id"] not in _AREA_ROLES
        or not isinstance(latest["run_id"], str)
        or not latest["run_id"].startswith("run_")
        or _ID.fullmatch(latest["run_id"]) is None
        or not all(isinstance(latest[key], str) and _SHA256.fullmatch(latest[key]) for key in (
            "manifest_fingerprint",
            "artifact_fingerprint",
            "latest_fingerprint",
        ))
    ):
        return False
    return _fingerprint({key: latest[key] for key in latest if key != "latest_fingerprint"}) == latest["latest_fingerprint"]


def _manifest_valid(manifest: dict[str, Any], run_id: str) -> bool:
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
    if (
        manifest["publication_contract_version"] != 1
        or manifest["run_id"] != run_id
        or manifest["artifact_file"] != "artifact.json"
        or manifest["area_id"] not in _AREA_ROLES
        or manifest.get("writer_role") != _AREA_WRITERS[manifest["area_id"]]
        or manifest["artifact_contract"] not in _AREA_ARTIFACT_CONTRACTS[manifest["area_id"]]
        or not all(isinstance(manifest[key], str) and _SHA256.fullmatch(manifest[key]) for key in (
            "artifact_fingerprint",
            "artifact_bytes_fingerprint",
            "manifest_fingerprint",
        ))
    ):
        return False
    return _fingerprint({key: manifest[key] for key in manifest if key != "manifest_fingerprint"}) == manifest["manifest_fingerprint"]


def _read_latest_completed_run_v1_impl(
    area_root: Path,
    runtime: LatestRunReaderContext,
) -> dict[str, Any]:
    if not _context_valid(runtime):
        raise LatestRunReaderError("run_publication_reader_context_mismatch")
    root = _root(area_root)
    latest_path = root / "latest.json"
    if latest_path.is_symlink():
        raise LatestRunReaderError("run_publication_symlink_rejected")
    if not latest_path.exists():
        raise LatestRunReaderError("run_publication_no_latest")
    latest, _ = _read_canonical_json(latest_path, 1_000_000)
    if not _latest_valid(latest):
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    if (
        latest["area_id"] != runtime.area_id
        or latest["tenant_id"] != runtime.tenant_id
        or latest["user_id"] != runtime.user_id
        or latest["data_space_id"] != runtime.data_space_id
    ):
        raise LatestRunReaderError("run_publication_reader_context_mismatch")
    return _read_run(root, runtime, latest["run_id"], latest)


def _read_run(
    root: Path,
    runtime: LatestRunReaderContext,
    run_id: str,
    latest: dict[str, Any] | None = None,
    with_artifact: bool = True,
) -> tuple[dict[str, Any] | None, dict[str, Any]] | dict[str, Any]:
    """Ein Lauf, vollstaendig geprueft: Verzeichnis, Manifest, Erfolgsmarke, Artefakt.

    Mit 'latest' gilt zusaetzlich, was der Zeiger ueber den Lauf sagt - so liest
    der Weg ueber den juengsten Stand genau wie zuvor. Ohne ihn wird ein
    bestimmter Lauf gelesen, etwa ein frueher veroeffentlichter Stichtag.
    """
    runs_root = root / "runs"
    run_directory = runs_root / run_id
    if runs_root.is_symlink() or run_directory.is_symlink():
        raise LatestRunReaderError("run_publication_symlink_rejected")
    if not run_directory.is_dir() or {item.name for item in run_directory.iterdir()} != {"artifact.json", "manifest.json", "SUCCESS"}:
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    manifest, _ = _read_canonical_json(run_directory / "manifest.json", 1_000_000)
    if not _manifest_valid(manifest, run_id):
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    if (
        (latest is not None and (manifest["manifest_fingerprint"] != latest["manifest_fingerprint"]
                                 or manifest["artifact_fingerprint"] != latest["artifact_fingerprint"]))
        or manifest["area_id"] != runtime.area_id
        or manifest["tenant_id"] != runtime.tenant_id
        or manifest["user_id"] != runtime.user_id
        or manifest["data_space_id"] != runtime.data_space_id
    ):
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    success, _ = _read_canonical_json(run_directory / "SUCCESS", 1_000_000)
    if success != {"run_id": run_id, "manifest_fingerprint": manifest["manifest_fingerprint"]}:
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    if not with_artifact:
        return None, manifest
    artifact, artifact_bytes = _read_canonical_json(run_directory / "artifact.json", _MAX_ARTIFACT_BYTES)
    if hashlib.sha256(artifact_bytes).hexdigest() != manifest["artifact_bytes_fingerprint"]:
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    artifact_fingerprint = _fingerprint({key: artifact[key] for key in artifact if key != "artifact_fingerprint"})
    if artifact.get("artifact_fingerprint") != artifact_fingerprint or artifact_fingerprint != manifest["artifact_fingerprint"]:
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    if latest is not None:
        return artifact
    return artifact, manifest


def _run_id_valid(run_id: Any) -> bool:
    return isinstance(run_id, str) and run_id.startswith("run_") and _ID.fullmatch(run_id) is not None


def read_completed_run_v1(
    area_root: Path,
    runtime: LatestRunReaderContext,
    run_id: str,
) -> dict[str, Any]:
    """Ein bestimmter veroeffentlichter Lauf - geprueft wie der juengste.

    Veroeffentlichte Laeufe bleiben liegen; bis rc.242 liess sich nur der
    juengste lesen. Wer einen frueheren Stichtag noch einmal sehen wollte, bekam
    "bereits veroeffentlicht" und weiter den anderen Stand gezeigt
    (Befund 12.10.2026).
    """
    try:
        if not _context_valid(runtime):
            raise LatestRunReaderError("run_publication_reader_context_mismatch")
        if not _run_id_valid(run_id):
            raise LatestRunReaderError("run_publication_reader_integrity_invalid")
        artifact, _ = _read_run(_root(area_root), runtime, run_id)
        return artifact
    except LatestRunReaderError:
        raise
    except Exception:
        raise LatestRunReaderError("run_publication_boundary_failed") from None


def list_completed_runs_v1(
    area_root: Path,
    runtime: LatestRunReaderContext,
) -> dict[str, Any]:
    """Alle veroeffentlichten Laeufe eines Bereichs - aus geprueften Manifesten.

    Ein Lauf, dessen Verzeichnis, Manifest oder Erfolgsmarke nicht stimmt, steht
    nicht in der Liste; er wird gezaehlt, damit eine Luecke nicht wie Leere
    aussieht.
    """
    try:
        if not _context_valid(runtime):
            raise LatestRunReaderError("run_publication_reader_context_mismatch")
        root = _root(area_root)
        runs_root = root / "runs"
        if runs_root.is_symlink():
            raise LatestRunReaderError("run_publication_symlink_rejected")
        latest_run = None
        latest_path = root / "latest.json"
        if latest_path.exists() and not latest_path.is_symlink():
            try:
                latest, _ = _read_canonical_json(latest_path, 1_000_000)
                if _latest_valid(latest):
                    latest_run = latest["run_id"]
            except LatestRunReaderError:
                latest_run = None
        rows: list[dict[str, Any]] = []
        unreadable = 0
        names = sorted(item.name for item in runs_root.iterdir()) if runs_root.is_dir() else []
        for name in names:
            if not _run_id_valid(name):
                unreadable += 1
                continue
            try:
                _, manifest = _read_run(root, runtime, name, with_artifact=False)
            except LatestRunReaderError:
                unreadable += 1
                continue
            rows.append({"run_id": name, "artifact_id": manifest["artifact_id"],
                         "artifact_contract": manifest["artifact_contract"],
                         "completed_at_utc": manifest["completed_at_utc"],
                         "published_at_utc": manifest["published_at_utc"],
                         "latest": name == latest_run})
        return {"runs": rows, "unreadable_run_count": unreadable}
    except LatestRunReaderError:
        raise
    except Exception:
        raise LatestRunReaderError("run_publication_boundary_failed") from None


def read_latest_completed_run_v1(
    area_root: Path,
    runtime: LatestRunReaderContext,
) -> dict[str, Any]:
    """Read a verified latest artifact without any publication capability."""

    try:
        return _read_latest_completed_run_v1_impl(area_root, runtime)
    except LatestRunReaderError:
        raise
    except Exception:
        raise LatestRunReaderError("run_publication_boundary_failed") from None
