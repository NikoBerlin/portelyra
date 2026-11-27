"""Owner-only Product bridge for schema-201/202 plus Asset Activity schema 401.

Schema 201 or its additive native schema-202 successor remains the editable authority
for Product Portfolio, Account, Asset and coupled Transaction facts.  This module
materializes those facts into the
accepted schema-400 shape, adds the schema-401 compatibility objects plus ADR-129's
fresh-only signed-net-proceeds marker, and copies only previously committed Asset
Activity facts from the active Product generation.
A per-Asset cutover appends Asset Activity to a fresh generation and atomically
switches the owner-only active pointer.  No browser-facing caller supplies paths,
Context, canonical IDs, fingerprints or confirmation authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import fcntl
import hashlib
import json
import os
from pathlib import Path
import errno
import re
import secrets
import shutil
import sqlite3
import stat
import tempfile
from typing import Any, Mapping, Sequence
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference.asset_activity_v1 import (
    AssetActivityV1Error,
    fifo_cost_average_evidence_v1,
    validate_asset_activity_v1,
)

from migrations.reference.schema400_asset_activity_compat_v1 import (
    OneUseSchema400AssetActivityAuthorizerV1,
    Schema400AssetActivityCompatV1Error,
    Schema400AssetActivityContextV1,
    apply_recomputed_per_asset_schema400_cutover_v1,
    build_schema400_asset_activity_confirmation_v1,
    preview_recomputed_per_asset_schema400_cutover_v1,
    _event_payload,
    apply_schema400_asset_activity_v1,
    preview_schema400_asset_activity_v1,
)
from workers.reference.semantic_realized_fifo_v1 import (
    ACTIVITY as SEMANTIC_ACTIVITY,
    SemanticRealizedFifoV1Error,
    build_semantic_realized_fifo_read_model_v1,
    context_values as semantic_context_values,
    public_ref as semantic_public_ref,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_400 = ROOT / "contracts" / "portfolio-ledger" / "v1" / "schema.sql"
MIGRATION_401 = ROOT / "contracts" / "portfolio-ledger" / "v1.1" / "add-asset-activity-v1.sql"
PATCH_401_SIGNED_NET_PROCEEDS = ROOT / "contracts" / "portfolio-ledger" / "v1.1" / "patch-signed-net-trade-proceeds-v1.sql"
PATCH_401_FIFO_SOURCE_ORDER = ROOT / "contracts" / "portfolio-ledger" / "v1.1" / "add-owner-confirmed-source-order-v1.sql"
PATCH_401_GENERIC_DERIVATIVE = ROOT / "contracts" / "portfolio-ledger" / "v1.1" / "enable-generic-derivative-activity-v1.sql"
CANONICAL_MIGRATION_202 = ROOT / "contracts" / "v2.2" / "migrate-from-v2.1.sql"
PRODUCT_AREA = "asset-activity-ledger-v1"
LEDGER_NAME = "portfolio-ledger-v401.sqlite"
MANIFEST_NAME = "generation-manifest.json"
SUCCESS_NAME = "SUCCESS"
ACTIVE_NAME = "active.json"
CORRECTION_RECEIPT_NAME = "asset-activity-correction-receipt.json"
LOCK_NAME = "writer.lock"
NATIVE_ATTEMPT_AREA = "native-attempts"
CANONICAL_LOCK_NAME = "canonical.writer.lock"
CONTRACT_VERSION = 1
ALLOWED_FAILPOINTS = frozenset({
    None,
    "after_native_attempt",
    "after_generation_complete",
    "after_generation_publish",
    "before_active_replace",
    "after_active_replace",
})
DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
SHA = re.compile(r"^[a-f0-9]{64}$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{3,80}$")
GENERATION = re.compile(r"^gen_[a-f0-9]{32}$")
LOCAL_TIME = re.compile(r"^[0-9]{2}:[0-9]{2}:[0-9]{2}$")
LOCAL_DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

FAILURE_CODES = frozenset(
    {
        "desktop_asset_activity_active_invalid",
        "desktop_asset_activity_already_committed",
        "desktop_asset_activity_boundary_failed",
        "desktop_asset_activity_canonical_changed",
        "desktop_asset_activity_canonical_invalid",
        "desktop_asset_activity_confirmation_expired",
        "desktop_asset_activity_context_invalid",
        "desktop_asset_activity_generation_conflict",
        "desktop_asset_activity_generation_invalid",
        "desktop_asset_activity_fifo_invalid",
        "desktop_asset_activity_input_invalid",
        "desktop_asset_activity_ledger_invalid",
        "desktop_asset_activity_lock_unavailable",
        "desktop_asset_activity_plan_stale",
        "desktop_asset_activity_projection_unsupported",
        "desktop_asset_activity_publication_failed",
        "desktop_asset_activity_source_invalid",
        "desktop_asset_activity_storage_invalid",
        "synthetic_desktop_asset_activity_failpoint",
    }
)


class DesktopProductAssetActivityV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("desktop_asset_activity_error_code_unregistered")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DesktopProductAssetActivityContextV1:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str
    role: str = "desktop_owner"


@dataclass(frozen=True)
class DesktopProductAssetActivityResultV1:
    status: str
    generation_ref: str
    event_count: int
    total_asset_activity_event_count: int
    schema_version: int
    canonical_write: bool
    cash_posting_count: int
    semantic_contracts: tuple[str, ...]


@dataclass(frozen=True)
class DesktopNativeAssetActivityResultV1:
    status: str
    generation_ref: str
    event_count: int
    total_asset_activity_event_count: int
    schema_version: int
    canonical_write: bool
    cash_posting_count: int
    semantic_contracts: tuple[str, ...]
    command_ref: str


def desktop_product_asset_activity_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise DesktopProductAssetActivityV1Error(code)


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
        _abort("desktop_asset_activity_input_invalid")


def _sha(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _canonical_domain_sha(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except Exception:
        _abort("desktop_asset_activity_canonical_invalid")
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        _abort("desktop_asset_activity_storage_invalid")


def _context(value: Any) -> DesktopProductAssetActivityContextV1:
    if isinstance(value, Schema400AssetActivityContextV1):
        value = DesktopProductAssetActivityContextV1(
            value.tenant_id, value.user_id, value.data_space_id, value.actor_id, value.role
        )
    if not isinstance(value, DesktopProductAssetActivityContextV1):
        _abort("desktop_asset_activity_context_invalid")
    scoped = (value.tenant_id, value.user_id, value.data_space_id)
    if (
        any(
            not isinstance(item, str)
            or len(item) > 64
            or TOKEN.fullmatch(item) is None
            for item in scoped
        )
        or not isinstance(value.actor_id, str)
        or TOKEN.fullmatch(value.actor_id) is None
        or value.role != "desktop_owner"
        or not value.data_space_id.startswith("sbx_")
    ):
        _abort("desktop_asset_activity_context_invalid")
    return value


def _compat_context(value: DesktopProductAssetActivityContextV1) -> Schema400AssetActivityContextV1:
    return Schema400AssetActivityContextV1(
        value.tenant_id, value.user_id, value.data_space_id, value.actor_id, value.role
    )


def _context_fingerprint(value: DesktopProductAssetActivityContextV1) -> str:
    return _sha(
        {
            "contract_version": "desktop_product_asset_activity_context_v1",
            "tenant_id": value.tenant_id,
            "user_id": value.user_id,
            "data_space_id": value.data_space_id,
            "actor_id": value.actor_id,
            "role": value.role,
        }
    )


def _generation_writer_context_matches(
    connection: sqlite3.Connection,
    manifest_context_fingerprint: Any,
    reader_context: DesktopProductAssetActivityContextV1,
) -> bool:
    """Bind the immutable writer actor without requiring it to equal the reader actor."""
    if not isinstance(manifest_context_fingerprint, str) or SHA.fullmatch(manifest_context_fingerprint) is None:
        return False
    try:
        actors = {row[0] for row in connection.execute(
            "SELECT DISTINCT actor_id FROM ledger_command_receipt ORDER BY actor_id"
        )}
    except sqlite3.Error:
        return False
    if not actors:
        return False
    for actor_id in actors:
        if (
            isinstance(actor_id, str)
            and len(actor_id) <= 64
            and TOKEN.fullmatch(actor_id) is not None
            and manifest_context_fingerprint == _context_fingerprint(
                DesktopProductAssetActivityContextV1(
                    reader_context.tenant_id,
                    reader_context.user_id,
                    reader_context.data_space_id,
                    actor_id,
                    reader_context.role,
                )
            )
        ):
            return True
    return False


def _path_without_symlink(path: Path) -> bool:
    if not path.is_absolute():
        return False
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if current.is_symlink():
                return False
        except OSError:
            return False
    return True


def _owner_directory(path_value: str | Path, *, create: bool = False) -> Path:
    path = Path(path_value)
    if not path.is_absolute() or not _path_without_symlink(path):
        _abort("desktop_asset_activity_storage_invalid")
    if create and not path.exists():
        parent = _owner_directory(path.parent, create=True)
        try:
            os.mkdir(path, 0o700)
        except OSError:
            _abort("desktop_asset_activity_storage_invalid")
        try:
            os.chmod(path, 0o700)
        except OSError:
            _abort("desktop_asset_activity_storage_invalid")
        settle_new_directory_v1(path)  # #568: neuer Speicherordner, auch seine gocryptfs.diriv festschreiben
        if parent not in path.parents:
            _abort("desktop_asset_activity_storage_invalid")
    try:
        metadata = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError:
        _abort("desktop_asset_activity_storage_invalid")
    if (
        resolved != path
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_uid != os.geteuid()
    ):
        _abort("desktop_asset_activity_storage_invalid")
    return resolved


def _owner_file(path_value: str | Path, code: str) -> Path:
    path = Path(path_value)
    if not path.is_absolute() or not _path_without_symlink(path):
        _abort(code)
    try:
        metadata = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError:
        _abort(code)
    if (
        resolved != path
        or not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.geteuid()
    ):
        _abort(code)
    return resolved


def _correction_receipt_for_generation(
    generation_value: Path,
    context: DesktopProductAssetActivityContextV1,
    manifest: Mapping[str, Any],
    activity: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    generation = _owner_directory(generation_value)
    path = generation / CORRECTION_RECEIPT_NAME
    if not path.exists():
        return None
    path = _owner_file(path, "desktop_asset_activity_generation_invalid")
    try:
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _abort("desktop_asset_activity_generation_invalid")
    required = {
        "asset_activity_correction_receipt_version", "action_type", "context_fingerprint",
        "plan_fingerprint", "confirmation_fingerprint", "prior_generation_ref", "generation_ref",
        "predecessor_event_ref", "predecessor_effect_fingerprint", "replacement_event_ref",
        "replacement_event_count", "total_asset_activity_event_count", "activity_set_fingerprint",
        "fifo_world_result_fingerprints", "committed_at_utc", "predecessor_preserved",
        "schema201_canonical_write", "cash_posting_count", "provider_access", "network_access",
        "receipt_fingerprint",
    }
    batch = isinstance(receipt, dict) and receipt.get("asset_activity_correction_receipt_version") == 2
    if batch:
        required.add("batch_predecessors")
    if not isinstance(receipt, dict) or set(receipt) != required or path.read_bytes() != _canonical(receipt) + b"\n":
        _abort("desktop_asset_activity_generation_invalid")
    fingerprint = receipt.get("receipt_fingerprint")
    body = dict(receipt); body.pop("receipt_fingerprint", None)
    if (
        receipt.get("asset_activity_correction_receipt_version") not in {1, 2}
        or receipt.get("action_type") not in {"correct", "void"}
        or receipt.get("context_fingerprint") != manifest.get("context_fingerprint")
        or fingerprint != _sha(body)
        or receipt.get("plan_fingerprint") != manifest.get("plan_fingerprint")
        or receipt.get("generation_ref") != manifest.get("generation_ref")
        or receipt.get("activity_set_fingerprint") != manifest.get("activity_set_fingerprint")
        or receipt.get("total_asset_activity_event_count") != manifest.get("total_asset_activity_event_count")
        or receipt.get("replacement_event_count") not in {0, 1}
        or (receipt.get("action_type") == "void") != (receipt.get("replacement_event_count") == 0)
        or not isinstance(receipt.get("predecessor_event_ref"), str)
        or not receipt["predecessor_event_ref"].startswith("evt_")
        or receipt.get("predecessor_preserved") is not True
        or receipt.get("schema201_canonical_write") is not False
        or receipt.get("cash_posting_count") != 0
        or receipt.get("provider_access") is not False
        or receipt.get("network_access") is not False
    ):
        _abort("desktop_asset_activity_generation_invalid")
    predecessors = [{"event_ref": receipt["predecessor_event_ref"], "effect_fingerprint": receipt["predecessor_effect_fingerprint"]}]
    if batch:
        predecessors = receipt["batch_predecessors"]
        if (receipt["action_type"] != "void" or not isinstance(predecessors, list) or
            not 2 <= len(predecessors) <= 1000 or any(not isinstance(row, dict) or
                set(row) != {"event_ref", "effect_fingerprint"} or
                not isinstance(row["event_ref"], str) or not row["event_ref"].startswith("evt_") or
                not isinstance(row["effect_fingerprint"], str) or SHA.fullmatch(row["effect_fingerprint"]) is None
                for row in predecessors)):
            _abort("desktop_asset_activity_generation_invalid")
        refs = [row["event_ref"] for row in predecessors]
        if refs != sorted(set(refs)) or predecessors[0] != {"event_ref": receipt["predecessor_event_ref"], "effect_fingerprint": receipt["predecessor_effect_fingerprint"]}:
            _abort("desktop_asset_activity_generation_invalid")
    replacement_ref = receipt.get("replacement_event_ref")
    if (replacement_ref is None) != (receipt["replacement_event_count"] == 0) or (
        replacement_ref is not None and (not isinstance(replacement_ref, str) or not replacement_ref.startswith("evt_"))
    ):
        _abort("desktop_asset_activity_generation_invalid")
    if activity is not None:
        refs = {row["event_ref"] for row in activity.get("asset_activity_events", [])}
        if any(row["event_ref"] in refs for row in predecessors) or (replacement_ref is not None and replacement_ref not in refs):
            _abort("desktop_asset_activity_generation_invalid")
    return receipt


def _corrected_event_refs(
    data_space: Path,
    context: DesktopProductAssetActivityContextV1,
) -> set[str]:
    area = data_space / PRODUCT_AREA
    if not area.exists():
        return set()
    area = _owner_directory(area)
    generations = area / "generations"
    if not generations.exists():
        return set()
    generations = _owner_directory(generations)
    corrected: set[str] = set()
    for child in sorted(generations.iterdir()):
        if not child.is_dir() or child.is_symlink() or GENERATION.fullmatch(child.name) is None:
            continue
        generation = _owner_directory(child)
        receipt_path = generation / CORRECTION_RECEIPT_NAME
        if not receipt_path.exists():
            continue
        manifest_path = _owner_file(generation / MANIFEST_NAME, "desktop_asset_activity_generation_invalid")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _abort("desktop_asset_activity_generation_invalid")
        receipt = _correction_receipt_for_generation(generation, context, manifest)
        corrected.update(row["event_ref"] for row in receipt.get("batch_predecessors", [{"event_ref": receipt["predecessor_event_ref"]}]))
    return corrected


def _assert_event_refs_not_corrected(
    data_space: Path,
    context: DesktopProductAssetActivityContextV1,
    events: Sequence[Mapping[str, Any]],
) -> None:
    corrected = _corrected_event_refs(data_space, context)
    if any(event.get("event_ref") in corrected for event in events):
        _abort("desktop_asset_activity_already_committed")


def _uri(path: Path, mode: str, immutable: bool = False) -> str:
    suffix = "&immutable=1" if immutable else ""
    return f"file:{quote(str(path))}?mode={mode}{suffix}"


def _read_connection(path: Path) -> sqlite3.Connection:
    try:
        connection = sqlite3.connect(_uri(path, "ro", immutable=True), uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA query_only=ON")
        return connection
    except sqlite3.Error:
        _abort("desktop_asset_activity_ledger_invalid")


def _utc(value: Any, code: str = "desktop_asset_activity_input_invalid") -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort(code)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort(code)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _abort(code)
    return value


def _offset(value: str, seconds: int) -> str:
    parsed = datetime.strptime(_utc(value), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_desktop_asset_activity_time_v1(
    local_date_value: Any,
    local_time_value: Any,
    time_zone_value: Any,
) -> dict[str, str]:
    if (
        not isinstance(local_date_value, str)
        or LOCAL_DATE.fullmatch(local_date_value) is None
        or not isinstance(local_time_value, str)
        or LOCAL_TIME.fullmatch(local_time_value) is None
        or not isinstance(time_zone_value, str)
        or not 1 <= len(time_zone_value) <= 80
    ):
        _abort("desktop_asset_activity_input_invalid")
    try:
        local_day = date.fromisoformat(local_date_value)
        local_clock = time.fromisoformat(local_time_value)
        zone = ZoneInfo(time_zone_value)
    except (ValueError, ZoneInfoNotFoundError):
        _abort("desktop_asset_activity_input_invalid")
    if local_day.isoformat() != local_date_value or local_clock.strftime("%H:%M:%S") != local_time_value:
        _abort("desktop_asset_activity_input_invalid")
    naive = datetime.combine(local_day, local_clock)
    candidates: set[datetime] = set()
    for fold in (0, 1):
        aware = naive.replace(tzinfo=zone, fold=fold)
        candidate = aware.astimezone(timezone.utc)
        if candidate.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(candidate)
    if len(candidates) != 1:
        _abort("desktop_asset_activity_input_invalid")
    return {
        "local_date": local_date_value,
        "local_time": local_time_value,
        "time_zone": time_zone_value,
        "effective_at_utc": next(iter(candidates)).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _decimal(value: Any, *, positive: bool = False, nonzero: bool = False) -> Decimal:
    if (
        not isinstance(value, str)
        or len(value) > 80
        or value == "-0"
        or DECIMAL.fullmatch(value) is None
    ):
        _abort("desktop_asset_activity_projection_unsupported")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        _abort("desktop_asset_activity_projection_unsupported")
    if not parsed.is_finite() or positive and parsed <= 0 or nonzero and parsed == 0:
        _abort("desktop_asset_activity_projection_unsupported")
    return parsed


def _text(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if len(rendered) > 80 or rendered == "-0" or DECIMAL.fullmatch(rendered) is None:
        _abort("desktop_asset_activity_projection_unsupported")
    return rendered


def _abs_text(value: str) -> str:
    parsed = _decimal(value, nonzero=True)
    return _text(abs(parsed))


def _fingerprint_origin(kind: str, origin_type: str, origin_ref: Any) -> str | None:
    if origin_type == "native":
        if origin_ref is not None:
            _abort("desktop_asset_activity_canonical_invalid")
        return None
    if origin_type != "legacy_import" or not isinstance(origin_ref, str) or not origin_ref:
        _abort("desktop_asset_activity_canonical_invalid")
    return _sha({"kind": kind, "origin_type": origin_type, "origin_ref": origin_ref})


def _schema_signature(connection: sqlite3.Connection) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type,name"
        )
    )


_EXPECTED_CANONICAL_SCHEMA_SIGNATURES: dict[int, tuple[tuple[Any, ...], ...]] = {}


def _expected_canonical_schema_signature(version: int) -> tuple[tuple[Any, ...], ...]:
    if version in _EXPECTED_CANONICAL_SCHEMA_SIGNATURES:
        return _EXPECTED_CANONICAL_SCHEMA_SIGNATURES[version]
    if version not in {201, 202}:
        _abort("desktop_asset_activity_canonical_invalid")
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            (ROOT / "contracts" / "v2" / "schema.sql").read_text(encoding="utf-8")
        )
        connection.executescript(
            (ROOT / "contracts" / "v2.1" / "migrate-from-v2.sql").read_text(encoding="utf-8")
        )
        if version == 202:
            connection.executescript(CANONICAL_MIGRATION_202.read_text(encoding="utf-8"))
        signature = _schema_signature(connection)
        _EXPECTED_CANONICAL_SCHEMA_SIGNATURES[version] = signature
        return signature
    except sqlite3.Error:
        _abort("desktop_asset_activity_canonical_invalid")
    finally:
        connection.close()


def _canonical_snapshot(
    canonical_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    context = _context(context_value)
    path = _owner_file(canonical_path, "desktop_asset_activity_canonical_invalid")
    if any(Path(str(path) + suffix).exists() for suffix in ("-journal", "-wal", "-shm")):
        _abort("desktop_asset_activity_canonical_invalid")
    source_fingerprint = _sha_file(path)
    connection = _read_connection(path)
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id,created_at_utc "
            "FROM store_binding WHERE singleton_id=1"
        ).fetchall()
        if (
            version not in {201, 202}
            or _schema_signature(connection) != _expected_canonical_schema_signature(version)
            or len(binding) != 1
            or tuple(binding[0][:4])
            != (version, context.tenant_id, context.user_id, context.data_space_id)
            or UTC.fullmatch(binding[0]["created_at_utc"]) is None
        ):
            _abort("desktop_asset_activity_canonical_invalid")
        if (
            connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _abort("desktop_asset_activity_canonical_invalid")
        portfolios = [dict(row) for row in connection.execute("SELECT * FROM portfolio ORDER BY portfolio_id")]
        accounts = [dict(row) for row in connection.execute("SELECT * FROM account ORDER BY account_id")]
        assets = [dict(row) for row in connection.execute("SELECT * FROM asset ORDER BY asset_id")]
        transactions = [
            dict(row)
            for row in connection.execute(
                "SELECT tx.*,audit.command_type AS audit_command_type,audit.payload_fingerprint AS audit_payload_fingerprint "
                "FROM current_transaction tx "
                "JOIN data_command_audit audit ON audit.entity_id=tx.transaction_id "
                "AND audit.area_id='transaction_ledger' "
                "ORDER BY tx.effective_at_utc,tx.transaction_id"
            )
        ]
        if len({row["transaction_id"] for row in transactions}) != len(transactions):
            _abort("desktop_asset_activity_canonical_invalid")
        transaction_ids = [row["transaction_id"] for row in transactions]
        postings: list[dict[str, Any]] = []
        if transaction_ids:
            placeholders = ",".join("?" for _ in transaction_ids)
            postings = [
                dict(row)
                for row in connection.execute(
                    f"SELECT * FROM transaction_posting WHERE transaction_id IN ({placeholders}) "
                    "ORDER BY transaction_id,sequence_no,posting_id",
                    transaction_ids,
                )
            ]
            seals = {
                row["transaction_id"]: dict(row)
                for row in connection.execute(
                    f"SELECT * FROM transaction_seal WHERE transaction_id IN ({placeholders})",
                    transaction_ids,
                )
            }
            counts: dict[str, int] = {}
            postings_by_transaction: dict[str, list[dict[str, Any]]] = {}
            for posting in postings:
                transaction_id = posting["transaction_id"]
                counts[transaction_id] = counts.get(transaction_id, 0) + 1
                postings_by_transaction.setdefault(transaction_id, []).append(posting)
            for transaction in transactions:
                transaction_id = transaction["transaction_id"]
                seal = seals.get(transaction_id)
                record = {
                    key: transaction[key]
                    for key in transaction
                    if key not in {"audit_command_type", "audit_payload_fingerprint"}
                }
                content_fingerprint = _canonical_domain_sha(
                    {
                        "transaction_content_version": 1,
                        "record": record,
                        "postings": postings_by_transaction.get(transaction_id, []),
                    }
                )
                if (
                    seal is None
                    or seal["posting_count"] != counts.get(transaction_id, 0)
                    or seal["content_fingerprint"] != content_fingerprint
                    or transaction["audit_payload_fingerprint"] != content_fingerprint
                ):
                    _abort("desktop_asset_activity_canonical_invalid")
    except DesktopProductAssetActivityV1Error:
        raise
    except sqlite3.Error:
        _abort("desktop_asset_activity_canonical_invalid")
    finally:
        connection.close()
    return {
        "path": path,
        "source_fingerprint": source_fingerprint,
        "schema_version": version,
        "created_at_utc": binding[0]["created_at_utc"],
        "portfolios": portfolios,
        "accounts": accounts,
        "assets": assets,
        "transactions": transactions,
        "postings": postings,
    }


def read_desktop_product_per_asset_catalog_v1(
    canonical_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    """Read the trusted internal Product choices for session-ref projection."""
    context = _context(context_value)
    snapshot = _canonical_snapshot(canonical_path, context)
    portfolios = [
        {
            "portfolio_id": row["portfolio_id"],
            "label": row["display_name"],
            "base_currency": row["base_currency"],
        }
        for row in snapshot["portfolios"]
        if row["status"] == "active"
    ]
    assets = [
        {
            "asset_id": row["asset_id"],
            "label": row["display_name"],
            "asset_type": row["asset_type"],
            "quantity_scale": row["quantity_scale"],
            "price_currency": row["price_currency"],
        }
        for row in snapshot["assets"]
        if row["status"] == "active" and row["asset_type"] != "cash"
    ]
    accounts = [
        {
            "account_id": row["account_id"],
            "label": row["display_name"],
            "account_type": row["account_type"],
            "portfolio_id": row["portfolio_id"],
        }
        for row in snapshot["accounts"]
        if row["status"] == "active"
        and row["account_type"] in {"securities", "crypto_wallet", "other"}
    ]
    if not portfolios or not assets or not accounts:
        _abort("desktop_asset_activity_source_invalid")
    return {"portfolios": portfolios, "assets": assets, "accounts": accounts}


def resolve_desktop_product_per_asset_scope_v1(
    canonical_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    target_asset_id: str,
    selected_account_ids: Sequence[str],
) -> dict[str, Any]:
    """Resolve Product scope from trusted server-owned IDs only.

    Portfolio identity is derived from the selected current Accounts; callers do not
    supply it. The target must be one active non-Cash Asset.
    """
    context = _context(context_value)
    if (
        not isinstance(target_asset_id, str)
        or not target_asset_id.startswith("ast_")
        or not isinstance(selected_account_ids, Sequence)
        or isinstance(selected_account_ids, (str, bytes))
        or not selected_account_ids
        or any(not isinstance(value, str) or not value.startswith("acc_") for value in selected_account_ids)
        or len(set(selected_account_ids)) != len(selected_account_ids)
    ):
        _abort("desktop_asset_activity_input_invalid")
    snapshot = _canonical_snapshot(canonical_path, context)
    assets = {row["asset_id"]: row for row in snapshot["assets"]}
    accounts = {row["account_id"]: row for row in snapshot["accounts"]}
    asset = assets.get(target_asset_id)
    selected = [accounts.get(account_id) for account_id in selected_account_ids]
    if (
        asset is None
        or asset["status"] != "active"
        or asset["asset_type"] == "cash"
        or asset["quantity_scale"] is None
        or any(account is None or account["status"] != "active" for account in selected)
    ):
        _abort("desktop_asset_activity_source_invalid")
    portfolio_ids = {account["portfolio_id"] for account in selected}
    if len(portfolio_ids) != 1:
        _abort("desktop_asset_activity_source_invalid")
    portfolio_id = next(iter(portfolio_ids))
    portfolios = {row["portfolio_id"]: row for row in snapshot["portfolios"]}
    portfolio = portfolios.get(portfolio_id)
    if portfolio is None or portfolio["status"] != "active":
        _abort("desktop_asset_activity_source_invalid")
    allowed_accounts = {"securities", "crypto_wallet", "other"}
    if any(account["account_type"] not in allowed_accounts for account in selected):
        _abort("desktop_asset_activity_source_invalid")
    return {
        "portfolio_id": portfolio_id,
        "target_asset_id": target_asset_id,
        "selected_account_ids": tuple(selected_account_ids),
        "canonical_fingerprint": snapshot["source_fingerprint"],
    }


def _posting_groups(postings: Sequence[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in postings:
        groups.setdefault(str(row["transaction_id"]), []).append(row)
    return groups


def _unit_cash(row: Mapping[str, Any], asset: Mapping[str, Any]) -> None:
    if (
        asset["asset_type"] != "cash"
        or asset["valuation_method"] != "unit_value"
        or row["unit_price_decimal"] is not None
        or row["price_currency"] is not None
        or row["valuation_currency"] != asset["price_currency"]
        or _decimal(row["quantity_decimal"], nonzero=True)
        != _decimal(row["valuation_amount_decimal"], nonzero=True)
    ):
        _abort("desktop_asset_activity_projection_unsupported")


def _priced(row: Mapping[str, Any], asset: Mapping[str, Any]) -> str:
    price = row["unit_price_decimal"]
    if (
        price is None
        or row["price_currency"] != asset["price_currency"]
        or row["valuation_currency"] != asset["price_currency"]
    ):
        _abort("desktop_asset_activity_projection_unsupported")
    quantity = _decimal(row["quantity_decimal"], nonzero=True)
    unit = _decimal(price, positive=True)
    valuation = _decimal(row["valuation_amount_decimal"], nonzero=True)
    with localcontext() as decimal_context:
        decimal_context.prec = 240
        if quantity * unit != valuation:
            _abort("desktop_asset_activity_projection_unsupported")
    return price


def _project_transaction(
    transaction: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    portfolios: Mapping[str, Mapping[str, Any]],
    accounts: Mapping[str, Mapping[str, Any]],
    assets: Mapping[str, Mapping[str, Any]],
    command_id: str,
) -> tuple[Any, ...]:
    event_type = transaction["transaction_type"]
    portfolio = portfolios.get(transaction["portfolio_id"])
    if portfolio is None or transaction["record_action"] != "book" or not rows:
        _abort("desktop_asset_activity_projection_unsupported")
    roles: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if row["account_id"] not in accounts or row["asset_id"] not in assets:
            _abort("desktop_asset_activity_canonical_invalid")
        roles.setdefault(row["posting_role"], []).append(row)
    if sum(len(values) for values in roles.values()) != len(rows):
        _abort("desktop_asset_activity_projection_unsupported")
    selected: Mapping[str, Any]
    related_account: str | None = None
    fee: str | None = None
    if len(roles.get("fee", [])) > 1 or len(roles.get("tax", [])) > 1:
        _abort("desktop_asset_activity_projection_unsupported")
    fee_row = roles.get("fee", [None])[0]

    if event_type in {"buy", "sell"}:
        principal = roles.get("asset", [])
        cash = roles.get("cash", [])
        if (
            set(roles) - {"asset", "cash", "fee"}
            or len(principal) != 1
            or len(cash) not in {0, 1}
        ):
            _abort("desktop_asset_activity_projection_unsupported")
        selected = principal[0]
        asset = assets[selected["asset_id"]]
        if asset["asset_type"] == "cash":
            _abort("desktop_asset_activity_projection_unsupported")
        price = _priced(selected, asset)
        quantity_value = _decimal(selected["quantity_decimal"], nonzero=True)
        if event_type == "buy" and quantity_value <= 0 or event_type == "sell" and quantity_value >= 0:
            _abort("desktop_asset_activity_projection_unsupported")
        if cash:
            cash_row = cash[0]
            _unit_cash(cash_row, assets[cash_row["asset_id"]])
            cash_value = _decimal(cash_row["valuation_amount_decimal"], nonzero=True)
            asset_value = _decimal(selected["valuation_amount_decimal"], nonzero=True)
            if (
                cash_row["account_id"] == selected["account_id"]
                or event_type == "buy" and (cash_value >= 0 or cash_value != -asset_value)
                or event_type == "sell" and (cash_value <= 0 or cash_value != -asset_value)
            ):
                _abort("desktop_asset_activity_projection_unsupported")
        if fee_row is not None:
            _unit_cash(fee_row, assets[fee_row["asset_id"]])
            if (
                _decimal(fee_row["quantity_decimal"], nonzero=True) >= 0
                or not cash
                or fee_row["account_id"] != cash[0]["account_id"]
                or fee_row["asset_id"] != cash[0]["asset_id"]
            ):
                _abort("desktop_asset_activity_projection_unsupported")
            fee = _abs_text(fee_row["valuation_amount_decimal"])
        transaction_currency = selected["price_currency"]
    elif event_type in {"deposit", "withdrawal"}:
        if set(roles) - {"cash", "transfer", "fee"}:
            _abort("desktop_asset_activity_projection_unsupported")
        candidates = roles.get("cash", []) or roles.get("transfer", [])
        internal = [
            row
            for row in candidates
            if accounts[row["account_id"]]["account_type"] != "external"
        ]
        if len(candidates) != 2 or len(internal) != 1:
            _abort("desktop_asset_activity_projection_unsupported")
        selected = internal[0]
        counterpart = next(row for row in candidates if row is not selected)
        if (
            accounts[counterpart["account_id"]]["account_type"] != "external"
            or counterpart["asset_id"] != selected["asset_id"]
            or _decimal(counterpart["quantity_decimal"], nonzero=True)
            != -_decimal(selected["quantity_decimal"], nonzero=True)
            or _decimal(counterpart["valuation_amount_decimal"], nonzero=True)
            != -_decimal(selected["valuation_amount_decimal"], nonzero=True)
        ):
            _abort("desktop_asset_activity_projection_unsupported")
        asset = assets[selected["asset_id"]]
        if asset["asset_type"] == "cash":
            _unit_cash(selected, asset)
            price = "1"
        else:
            price = _priced(selected, asset)
            if fee_row is not None:
                _abort("desktop_asset_activity_projection_unsupported")
        quantity_value = _decimal(selected["quantity_decimal"], nonzero=True)
        if event_type == "deposit" and quantity_value <= 0 or event_type == "withdrawal" and quantity_value >= 0:
            _abort("desktop_asset_activity_projection_unsupported")
        if fee_row is not None:
            _unit_cash(fee_row, assets[fee_row["asset_id"]])
            if (
                fee_row["account_id"] != selected["account_id"]
                or fee_row["asset_id"] != selected["asset_id"]
                or _decimal(fee_row["quantity_decimal"], nonzero=True) >= 0
            ):
                _abort("desktop_asset_activity_projection_unsupported")
            fee = _abs_text(fee_row["valuation_amount_decimal"])
        transaction_currency = asset["price_currency"]
    elif event_type == "transfer":
        if set(roles) - {"transfer", "fee"}:
            _abort("desktop_asset_activity_projection_unsupported")
        principal = roles.get("transfer", [])
        if len(principal) != 2:
            _abort("desktop_asset_activity_projection_unsupported")
        negatives = [row for row in principal if _decimal(row["quantity_decimal"], nonzero=True) < 0]
        positives = [row for row in principal if _decimal(row["quantity_decimal"], nonzero=True) > 0]
        if len(negatives) != 1 or len(positives) != 1:
            _abort("desktop_asset_activity_projection_unsupported")
        selected = negatives[0]
        destination = positives[0]
        if (
            selected["asset_id"] != destination["asset_id"]
            or selected["account_id"] == destination["account_id"]
            or _decimal(selected["quantity_decimal"]) != -_decimal(destination["quantity_decimal"])
            or _decimal(selected["valuation_amount_decimal"])
            != -_decimal(destination["valuation_amount_decimal"])
        ):
            _abort("desktop_asset_activity_projection_unsupported")
        asset = assets[selected["asset_id"]]
        if asset["asset_type"] == "cash":
            _unit_cash(selected, asset)
            _unit_cash(destination, asset)
            price = "1"
            if fee_row is not None:
                _unit_cash(fee_row, assets[fee_row["asset_id"]])
                if (
                    fee_row["account_id"] != selected["account_id"]
                    or fee_row["asset_id"] != selected["asset_id"]
                    or _decimal(fee_row["quantity_decimal"], nonzero=True) >= 0
                ):
                    _abort("desktop_asset_activity_projection_unsupported")
                fee = _abs_text(fee_row["valuation_amount_decimal"])
        else:
            price = _priced(selected, asset)
            destination_price = _priced(destination, asset)
            if destination_price != price or fee_row is not None:
                _abort("desktop_asset_activity_projection_unsupported")
        related_account = destination["account_id"]
        transaction_currency = asset["price_currency"]
    elif event_type in {"reward", "dividend"}:
        if set(roles) != {"income"}:
            _abort("desktop_asset_activity_projection_unsupported")
        principal = roles.get("income", [])
        if len(principal) != 1 or fee_row is not None:
            _abort("desktop_asset_activity_projection_unsupported")
        selected = principal[0]
        asset = assets[selected["asset_id"]]
        if asset["asset_type"] == "cash" or event_type == "reward" and asset["asset_type"] != "crypto":
            _abort("desktop_asset_activity_projection_unsupported")
        price = _priced(selected, asset)
        if _decimal(selected["quantity_decimal"], nonzero=True) <= 0:
            _abort("desktop_asset_activity_projection_unsupported")
        transaction_currency = asset["price_currency"]
    elif event_type == "interest":
        if set(roles) != {"income"}:
            _abort("desktop_asset_activity_projection_unsupported")
        principal = roles.get("income", [])
        if len(principal) != 1 or fee_row is not None:
            _abort("desktop_asset_activity_projection_unsupported")
        selected = principal[0]
        asset = assets[selected["asset_id"]]
        _unit_cash(selected, asset)
        if _decimal(selected["quantity_decimal"], nonzero=True) <= 0:
            _abort("desktop_asset_activity_projection_unsupported")
        price = "1"
        transaction_currency = asset["price_currency"]
    elif event_type == "fee":
        if set(roles) != {"fee"}:
            _abort("desktop_asset_activity_projection_unsupported")
        principal = roles.get("fee", [])
        if len(principal) != 1:
            _abort("desktop_asset_activity_projection_unsupported")
        selected = principal[0]
        asset = assets[selected["asset_id"]]
        if _decimal(selected["quantity_decimal"], nonzero=True) >= 0:
            _abort("desktop_asset_activity_projection_unsupported")
        if asset["asset_type"] == "cash":
            _unit_cash(selected, asset)
            price = "1"
        else:
            price = _priced(selected, asset)
        fee = None
        transaction_currency = asset["price_currency"]
    else:
        _abort("desktop_asset_activity_projection_unsupported")

    quantity = _abs_text(selected["quantity_decimal"])
    origin_type = "native" if transaction["origin_type"] == "native" else "legacy_conversion"
    source_row_fingerprint = _fingerprint_origin(
        "transaction", transaction["origin_type"], transaction["origin_ref"]
    )
    command_semantics = transaction.get("audit_command_type")
    if not isinstance(command_semantics, str) or not command_semantics:
        _abort("desktop_asset_activity_canonical_invalid")
    transaction_code = f"schema201_projection:{command_semantics}"
    if len(transaction_code) > 200:
        _abort("desktop_asset_activity_projection_unsupported")
    return (
        transaction["transaction_id"],
        transaction["portfolio_id"],
        selected["account_id"],
        related_account,
        selected["asset_id"],
        event_type,
        transaction["effective_at_utc"],
        transaction["local_date"],
        quantity,
        price,
        None,
        fee,
        transaction_currency,
        transaction_code,
        transaction["memo"],
        origin_type,
        source_row_fingerprint,
        None,
        command_id,
        transaction["created_at_utc"],
    )


def _fifo_order_evidence_table_exists(connection: sqlite3.Connection) -> bool:
    return connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='asset_activity_fifo_order_evidence'"
    ).fetchone()[0] == 1


def _activity_rows(connection: sqlite3.Connection) -> dict[str, Any]:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version != 401:
        _abort("desktop_asset_activity_ledger_invalid")
    command_ids = [
        row[0]
        for row in connection.execute(
            "SELECT command_id FROM asset_activity_command_receipt ORDER BY committed_at_utc,command_id"
        )
    ]
    receipts: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    activity_receipts: list[dict[str, Any]] = []
    fifo_order_evidence: list[dict[str, Any]] = []
    if command_ids:
        placeholders = ",".join("?" for _ in command_ids)
        receipts = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM ledger_command_receipt WHERE command_id IN ({placeholders}) ORDER BY command_id",
                command_ids,
            )
        ]
        events = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM asset_activity_event WHERE command_id IN ({placeholders}) ORDER BY event_ref",
                command_ids,
            )
        ]
        activity_receipts = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM asset_activity_command_receipt WHERE command_id IN ({placeholders}) ORDER BY command_id",
                command_ids,
            )
        ]
        if _fifo_order_evidence_table_exists(connection):
            fifo_order_evidence = [
                dict(row)
                for row in connection.execute(
                    f"SELECT evidence.* FROM asset_activity_fifo_order_evidence evidence "
                    f"JOIN asset_activity_event event USING(event_ref) "
                    f"WHERE event.command_id IN ({placeholders}) ORDER BY evidence.event_ref",
                    command_ids,
                )
            ]
    payload = {
        "ledger_command_receipts": receipts,
        "asset_activity_events": events,
        "asset_activity_command_receipts": activity_receipts,
    }
    if fifo_order_evidence:
        payload["asset_activity_fifo_order_evidence"] = fifo_order_evidence
    payload["activity_set_fingerprint"] = _sha(payload)
    return payload


def read_desktop_product_asset_activity_binding_v1(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    """Read and verify the active generation without creating Product state."""

    context = _context(context_value)
    data_space = _owner_directory(data_space_path)
    area = data_space / PRODUCT_AREA
    if not area.exists():
        return {
            "status": "absent",
            "generation_ref": None,
            "ledger_path": None,
            "ledger_fingerprint": None,
            "activity_set_fingerprint": _sha(
                {
                    "ledger_command_receipts": [],
                    "asset_activity_events": [],
                    "asset_activity_command_receipts": [],
                }
            ),
            "asset_activity_event_count": 0,
            "semantic_contracts": ("portfolio_ledger_v1_transaction_fact",),
        }
    area = _owner_directory(area)
    active_path = area / ACTIVE_NAME
    if not active_path.exists():
        generations_path = area / "generations"
        if generations_path.exists():
            _owner_directory(generations_path)
        return {
            "status": "absent",
            "generation_ref": None,
            "ledger_path": None,
            "ledger_fingerprint": None,
            "activity_set_fingerprint": _sha(
                {
                    "ledger_command_receipts": [],
                    "asset_activity_events": [],
                    "asset_activity_command_receipts": [],
                }
            ),
            "asset_activity_event_count": 0,
            "semantic_contracts": ("portfolio_ledger_v1_transaction_fact",),
        }
    active_path = _owner_file(active_path, "desktop_asset_activity_active_invalid")
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _abort("desktop_asset_activity_active_invalid")
    if (
        not isinstance(active, dict)
        or set(active) != {"contract_version", "generation_ref", "ledger_fingerprint", "manifest_fingerprint"}
        or active["contract_version"] != CONTRACT_VERSION
        or not isinstance(active["generation_ref"], str)
        or GENERATION.fullmatch(active["generation_ref"]) is None
        or not isinstance(active["ledger_fingerprint"], str)
        or SHA.fullmatch(active["ledger_fingerprint"]) is None
        or not isinstance(active["manifest_fingerprint"], str)
        or SHA.fullmatch(active["manifest_fingerprint"]) is None
    ):
        _abort("desktop_asset_activity_active_invalid")
    generation = _owner_directory(area / "generations" / active["generation_ref"])
    ledger = _owner_file(generation / LEDGER_NAME, "desktop_asset_activity_generation_invalid")
    manifest_path = _owner_file(
        generation / MANIFEST_NAME, "desktop_asset_activity_generation_invalid"
    )
    success = _owner_file(generation / SUCCESS_NAME, "desktop_asset_activity_generation_invalid")
    if success.read_bytes() != b"completed\n":
        _abort("desktop_asset_activity_generation_invalid")
    if _sha_file(ledger) != active["ledger_fingerprint"] or _sha_file(manifest_path) != active["manifest_fingerprint"]:
        _abort("desktop_asset_activity_generation_invalid")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _abort("desktop_asset_activity_generation_invalid")
    required_manifest = {
        "contract_version", "authority_contract", "context_fingerprint", "generation_ref",
        "canonical_schema_version", "canonical_fingerprint", "prior_activity_set_fingerprint",
        "activity_set_fingerprint", "ledger_schema_version", "ledger_fingerprint",
        "plan_fingerprint", "command_id", "new_event_count", "total_asset_activity_event_count",
        "committed_at_utc", "semantic_contracts", "boundaries",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != required_manifest
        or manifest["contract_version"] != CONTRACT_VERSION
        or manifest["authority_contract"] != "schema201_derived_base_plus_asset_activity_v1"
        or not isinstance(manifest["context_fingerprint"], str)
        or SHA.fullmatch(manifest["context_fingerprint"]) is None
        or manifest["generation_ref"] != active["generation_ref"]
        or manifest["canonical_schema_version"] not in {201, 202}
        or manifest["ledger_schema_version"] != 401
        or manifest["ledger_fingerprint"] != active["ledger_fingerprint"]
        or manifest["semantic_contracts"]
        != ["portfolio_ledger_v1_transaction_fact", "asset_activity_v1"]
    ):
        _abort("desktop_asset_activity_generation_invalid")
    connection = _read_connection(ledger)
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM ledger_store_binding WHERE singleton_id=1"
        ).fetchall()
        if (
            len(binding) != 1
            or tuple(binding[0])
            != (401, context.tenant_id, context.user_id, context.data_space_id)
            or not _generation_writer_context_matches(
                connection, manifest["context_fingerprint"], context
            )
            or connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _abort("desktop_asset_activity_generation_invalid")
        activity = _activity_rows(connection)
    finally:
        connection.close()
    _correction_receipt_for_generation(generation, context, manifest, activity)
    if (
        activity["activity_set_fingerprint"] != manifest["activity_set_fingerprint"]
        or len(activity["asset_activity_events"]) != manifest["total_asset_activity_event_count"]
    ):
        _abort("desktop_asset_activity_generation_invalid")
    return {
        "status": "available",
        "generation_ref": active["generation_ref"],
        "ledger_path": str(ledger),
        "ledger_fingerprint": active["ledger_fingerprint"],
        "manifest_fingerprint": active["manifest_fingerprint"],
        "canonical_fingerprint": manifest["canonical_fingerprint"],
        "activity_set_fingerprint": activity["activity_set_fingerprint"],
        "asset_activity_event_count": len(activity["asset_activity_events"]),
        "semantic_contracts": tuple(manifest["semantic_contracts"]),
    }


def _copy_activity(source_path: Path | None, writer: sqlite3.Connection, context: DesktopProductAssetActivityContextV1) -> dict[str, Any]:
    empty = {
        "ledger_command_receipts": [],
        "asset_activity_events": [],
        "asset_activity_command_receipts": [],
    }
    empty["activity_set_fingerprint"] = _sha(empty)
    if source_path is None:
        return empty
    source = _read_connection(source_path)
    try:
        binding = source.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM ledger_store_binding WHERE singleton_id=1"
        ).fetchall()
        if len(binding) != 1 or tuple(binding[0]) != (
            401, context.tenant_id, context.user_id, context.data_space_id
        ):
            _abort("desktop_asset_activity_ledger_invalid")
        activity = _activity_rows(source)
    finally:
        source.close()
    if not activity["asset_activity_events"]:
        return activity
    try:
        trigger = writer.execute(
            "SELECT sql FROM sqlite_master WHERE type='trigger' AND name='asset_activity_event_validate'"
        ).fetchone()
        if trigger is None or not isinstance(trigger[0], str):
            _abort("desktop_asset_activity_ledger_invalid")
        trigger_sql = trigger[0]
        writer.execute("DROP TRIGGER asset_activity_event_validate")
        for row in activity["ledger_command_receipts"]:
            columns = list(row)
            writer.execute(
                f"INSERT INTO ledger_command_receipt ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )
        for row in activity["asset_activity_events"]:
            columns = list(row)
            writer.execute(
                f"INSERT INTO asset_activity_event ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )
        for row in activity.get("asset_activity_fifo_order_evidence", []):
            columns = list(row)
            writer.execute(
                f"INSERT INTO asset_activity_fifo_order_evidence ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )
        for row in activity["asset_activity_command_receipts"]:
            columns = list(row)
            writer.execute(
                f"INSERT INTO asset_activity_command_receipt ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(row[column] for column in columns),
            )
        writer.execute(trigger_sql)
    except DesktopProductAssetActivityV1Error:
        raise
    except sqlite3.Error:
        _abort("desktop_asset_activity_ledger_invalid")
    return activity


def materialize_desktop_product_semantic_ledger_v1(
    canonical_path: str | Path,
    activity_ledger_path: str | Path | None,
    target_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    context = _context(context_value)
    snapshot = _canonical_snapshot(canonical_path, context)
    target = Path(target_path)
    if not target.is_absolute() or not _path_without_symlink(target) or target.exists() or target.is_symlink():
        _abort("desktop_asset_activity_storage_invalid")
    _owner_directory(target.parent)
    activity_source = None if activity_ledger_path is None else _owner_file(
        activity_ledger_path, "desktop_asset_activity_ledger_invalid"
    )
    previous_umask = os.umask(0o077)
    writer: sqlite3.Connection | None = None
    try:
        writer = sqlite3.connect(target)
        writer.row_factory = sqlite3.Row
        writer.execute("PRAGMA foreign_keys=ON")
        writer.execute("PRAGMA journal_mode=DELETE")
        writer.execute("PRAGMA synchronous=FULL")
        writer.executescript(SCHEMA_400.read_text(encoding="utf-8"))
        projection_seed = {
            "contract_version": "schema201_to_portfolio_ledger_projection_v1",
            "canonical_fingerprint": snapshot["source_fingerprint"],
            "context_fingerprint": _context_fingerprint(context),
        }
        command_id = "cmd_product_" + _sha(projection_seed)[:48]
        timestamps = [snapshot["created_at_utc"]]
        timestamps.extend(row["updated_at_utc"] for row in snapshot["portfolios"])
        timestamps.extend(row["updated_at_utc"] for row in snapshot["accounts"])
        timestamps.extend(row["updated_at_utc"] for row in snapshot["assets"])
        timestamps.extend(row["created_at_utc"] for row in snapshot["transactions"])
        committed_at = max(timestamps)
        writer.execute(
            "INSERT INTO ledger_store_binding VALUES(1,400,?,?,?,?)",
            (context.tenant_id, context.user_id, context.data_space_id, snapshot["created_at_utc"]),
        )
        writer.execute(
            "INSERT INTO ledger_command_receipt VALUES(?, 'data_app','desktop_schema201_projection_v1',?,?,NULL,?)",
            (command_id, context.actor_id, _sha(projection_seed), committed_at),
        )
        portfolios = {row["portfolio_id"]: row for row in snapshot["portfolios"]}
        accounts = {row["account_id"]: row for row in snapshot["accounts"]}
        assets = {row["asset_id"]: row for row in snapshot["assets"]}
        for row in snapshot["portfolios"]:
            origin = "native" if row["origin_type"] == "native" else "legacy_conversion"
            source_key = _fingerprint_origin("portfolio", row["origin_type"], row["origin_ref"])
            writer.execute(
                "INSERT INTO portfolio_entity VALUES(?,?,?,?,?)",
                (row["portfolio_id"], origin, source_key, command_id, row["created_at_utc"]),
            )
            writer.execute(
                "INSERT INTO portfolio_revision VALUES(?,?,1,?,?,?,NULL,?,?)",
                (
                    "ptr_" + _sha({"portfolio": row["portfolio_id"], "revision": row["revision"]})[:32],
                    row["portfolio_id"], row["display_name"], row["base_currency"], row["status"],
                    command_id, row["updated_at_utc"],
                ),
            )
        for row in snapshot["accounts"]:
            origin = "native" if row["origin_type"] == "native" else "legacy_conversion"
            source_key = _fingerprint_origin("account", row["origin_type"], row["origin_ref"])
            writer.execute(
                "INSERT INTO account_entity VALUES(?,?,?,?,?,?)",
                (row["account_id"], row["portfolio_id"], origin, source_key, command_id, row["created_at_utc"]),
            )
            account_type = "other" if row["account_type"] == "external" else row["account_type"]
            writer.execute(
                "INSERT INTO account_revision VALUES(?,?,1,?,?,?,?,'complete',NULL,?,?)",
                (
                    "acr_" + _sha({"account": row["account_id"], "revision": row["revision"]})[:32],
                    row["account_id"], row["display_name"], account_type, row["institution_label"],
                    row["status"], command_id, row["updated_at_utc"],
                ),
            )
        for row in snapshot["assets"]:
            origin = "native" if row["origin_type"] == "native" else "legacy_conversion"
            source_key = _fingerprint_origin("asset", row["origin_type"], row["origin_ref"])
            writer.execute(
                "INSERT INTO asset_entity VALUES(?,?,?,?,?)",
                (row["asset_id"], origin, source_key, command_id, row["created_at_utc"]),
            )
            writer.execute(
                "INSERT INTO asset_revision VALUES(?,?,1,?,?,?,?,?,NULL,?,'complete',NULL,?,?)",
                (
                    "asr_" + _sha({"asset": row["asset_id"], "revision": row["revision"]})[:32],
                    row["asset_id"], row["display_name"], row["asset_type"], row["quantity_scale"],
                    row["valuation_method"], row["isin"], row["status"], command_id, row["updated_at_utc"],
                ),
            )
        groups = _posting_groups(snapshot["postings"])
        for transaction in snapshot["transactions"]:
            values = _project_transaction(
                transaction,
                groups.get(transaction["transaction_id"], []),
                portfolios,
                accounts,
                assets,
                command_id,
            )
            writer.execute(
                "INSERT INTO transaction_fact VALUES(%s)" % ",".join("?" for _ in range(20)),
                values,
            )
        writer.commit()
        writer.executescript(MIGRATION_401.read_text(encoding="utf-8"))
        writer.executescript(PATCH_401_SIGNED_NET_PROCEEDS.read_text(encoding="utf-8"))
        writer.executescript(PATCH_401_FIFO_SOURCE_ORDER.read_text(encoding="utf-8"))
        writer.executescript(PATCH_401_GENERIC_DERIVATIVE.read_text(encoding="utf-8"))
        copied = _copy_activity(activity_source, writer, context)
        writer.commit()
        if (
            writer.execute("PRAGMA user_version").fetchone()[0] != 401
            or writer.execute(
                "SELECT patch_name FROM asset_activity_schema_patch WHERE singleton_id=1"
            ).fetchone()[0] != "signed_net_trade_proceeds_v1"
            or writer.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='asset_activity_fifo_order_evidence'"
            ).fetchone()[0] != 1
            or writer.execute(
                "SELECT count(*) FROM asset_activity_generic_derivative_capability "
                "WHERE singleton_id=1 AND capability_name='generic_derivative_activity_v1' "
                "AND lifecycle_events_inferred=0 AND automatic_cash_postings=0"
            ).fetchone()[0] != 1
            or writer.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or writer.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _abort("desktop_asset_activity_ledger_invalid")
        projected_transaction_count = writer.execute("SELECT count(*) FROM transaction_fact").fetchone()[0]
        semantic_counts = {
            row[0]: row[1]
            for row in writer.execute(
                "SELECT semantic_contract,count(*) FROM compatible_ledger_event GROUP BY semantic_contract"
            )
        }
        writer.close()
        writer = None
        os.chmod(target, 0o600)
        _owner_file(target, "desktop_asset_activity_ledger_invalid")
        if _sha_file(snapshot["path"]) != snapshot["source_fingerprint"]:
            _abort("desktop_asset_activity_canonical_changed")
        return {
            "status": "materialized",
            "schema_version": 401,
            "canonical_schema_version": snapshot["schema_version"],
            "canonical_fingerprint": snapshot["source_fingerprint"],
            "activity_set_fingerprint": copied["activity_set_fingerprint"],
            "asset_activity_event_count": len(copied["asset_activity_events"]),
            "projected_transaction_count": projected_transaction_count,
            "semantic_contract_counts": semantic_counts,
            "ledger_fingerprint": _sha_file(target),
        }
    except DesktopProductAssetActivityV1Error:
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        target.unlink(missing_ok=True)
        raise
    except (OSError, sqlite3.Error, KeyError, TypeError, ValueError):
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
        target.unlink(missing_ok=True)
        _abort("desktop_asset_activity_ledger_invalid")
    finally:
        os.umask(previous_umask)


def _matching_cutover(
    ledger_path: Path | None,
    plan_fingerprint: str,
    source_row_count: int | None = None,
) -> dict[str, Any] | None:
    if ledger_path is None:
        return None
    connection = _read_connection(ledger_path)
    try:
        rows = connection.execute(
            "SELECT command_id,event_count,source_row_count,committed_at_utc "
            "FROM asset_activity_command_receipt "
            "WHERE action_type='per_asset_legacy_cutover_v1' AND plan_fingerprint=?",
            (plan_fingerprint,),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1 or source_row_count is not None and rows[0]["source_row_count"] != source_row_count:
            _abort("desktop_asset_activity_generation_invalid")
        stored_count = connection.execute(
            "SELECT count(*) FROM asset_activity_event WHERE command_id=? AND origin_type='legacy_conversion'",
            (rows[0]["command_id"],),
        ).fetchone()[0]
        if stored_count != rows[0]["event_count"]:
            _abort("desktop_asset_activity_generation_invalid")
        return dict(rows[0])
    finally:
        connection.close()


def _matching_native_command(
    ledger_path: Path | None,
    portfolio_id: str,
    events: Sequence[Mapping[str, Any]],
    fifo_order_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    if ledger_path is None:
        return None
    refs = [event["event_ref"] for event in events]
    connection = _read_connection(ledger_path)
    try:
        stored = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM asset_activity_event WHERE event_ref IN (%s) ORDER BY event_ref"
                % ",".join("?" for _ in refs),
                refs,
            )
        ]
        if not stored:
            return None
        if len(stored) != len(events):
            _abort("desktop_asset_activity_generation_invalid")
        key_map = {
            "account_ref": "account_id",
            "related_account_ref": "related_account_id",
            "asset_ref": "asset_id",
            "source_asset_ref": "source_asset_id",
        }
        expected = []
        for event in events:
            row = {
                key_map.get(key, key): value
                for key, value in event.items()
            }
            expected.append(row)
        expected.sort(key=lambda row: row["event_ref"])
        for actual, wanted in zip(stored, expected):
            if (
                actual["portfolio_id"] != portfolio_id
                or actual["origin_type"] != "native"
                or actual["source_row_fingerprint"] is not None
                or any(actual[key] != value for key, value in wanted.items())
            ):
                _abort("desktop_asset_activity_generation_invalid")
        command_ids = {row["command_id"] for row in stored}
        if len(command_ids) != 1:
            _abort("desktop_asset_activity_generation_invalid")
        command_id = next(iter(command_ids))
        rows = connection.execute(
            "SELECT receipt.command_id,receipt.event_count,receipt.committed_at_utc "
            "FROM asset_activity_command_receipt receipt "
            "JOIN ledger_command_receipt command USING(command_id) "
            "WHERE receipt.command_id=? AND receipt.action_type='asset_activity_create_v1' "
            "AND receipt.plan_fingerprint IS NULL "
            "AND command.action_type='asset_activity_create_v1'",
            (command_id,),
        ).fetchall()
        evidence_rows = [] if fifo_order_evidence is None else [dict(row) for row in ([fifo_order_evidence] if isinstance(fifo_order_evidence, Mapping) else fifo_order_evidence)]
        evidence_refs = refs if not evidence_rows else [row["event_ref"] for row in evidence_rows]
        stored_evidence = []
        if _fifo_order_evidence_table_exists(connection):
            stored_evidence = [
                dict(row) for row in connection.execute(
                    "SELECT * FROM asset_activity_fifo_order_evidence WHERE event_ref IN (%s) ORDER BY event_ref"
                    % ",".join("?" for _ in evidence_refs), evidence_refs,
                )
            ]
        expected_evidence = sorted(evidence_rows,key=lambda row:row["event_ref"])
        if (
            len(rows) != 1
            or rows[0]["event_count"] != len(events)
            or stored_evidence != expected_evidence
        ):
            _abort("desktop_asset_activity_generation_invalid")
        return dict(rows[0])
    except sqlite3.Error:
        _abort("desktop_asset_activity_ledger_invalid")
    finally:
        connection.close()


def _target_asset_ref(review: Any) -> str:
    target = review.get("target_asset") if isinstance(review, dict) else None
    value = target.get("asset_ref") if isinstance(target, dict) else None
    if not isinstance(value, str) or not value.startswith("ast_"):
        _abort("desktop_asset_activity_source_invalid")
    return value


def _assert_target_unused(ledger_path: Path, target_asset_ref: str) -> None:
    connection = _read_connection(ledger_path)
    try:
        coupled = connection.execute(
            "SELECT count(*) FROM current_transaction_fact WHERE asset_id=?",
            (target_asset_ref,),
        ).fetchone()[0]
        activity = connection.execute(
            "SELECT count(*) FROM current_asset_activity_event WHERE asset_id=?",
            (target_asset_ref,),
        ).fetchone()[0]
    except sqlite3.Error:
        _abort("desktop_asset_activity_ledger_invalid")
    finally:
        connection.close()
    if coupled or activity:
        _abort("desktop_asset_activity_already_committed")


def _preview_payload(
    preview: Mapping[str, Any],
    materialized: Mapping[str, Any],
    binding: Mapping[str, Any],
    plan_fingerprint: str,
) -> dict[str, Any]:
    payload = {
        "product_asset_activity_preview_version": CONTRACT_VERSION,
        "status": "ready_for_confirmation",
        "schema_version": 401,
        "preview_fingerprint": preview["preview_fingerprint"],
        "plan_fingerprint": plan_fingerprint,
        "canonical_fingerprint": materialized["canonical_fingerprint"],
        "prior_activity_set_fingerprint": materialized["activity_set_fingerprint"],
        "event_count": preview["event_count"],
        "source_row_count": preview["cutover_evidence"]["source_row_count"],
        "projected_transaction_count": materialized["projected_transaction_count"],
        "existing_asset_activity_event_count": materialized["asset_activity_event_count"],
        "cash_posting_count": preview["cash_posting_count"],
        "provider_price_use_count": preview["provider_price_use_count"],
        "tax_classification_inference_count": preview["tax_classification_inference_count"],
        "semantic_contracts": ["portfolio_ledger_v1_transaction_fact", "asset_activity_v1"],
        "authority_contract": "schema201_derived_base_plus_asset_activity_v1",
        "active_generation_ref": binding.get("generation_ref"),
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "private_data_access": False,
    }
    payload["product_preview_fingerprint"] = _sha(payload)
    return payload


def preview_desktop_product_per_asset_cutover_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    portfolio_id: str,
    projection: Any,
    review: Any,
    expected_plan_fingerprint: str,
) -> dict[str, Any]:
    """Recompute and preview one Product cutover without publishing Product state."""

    context = _context(context_value)
    if not isinstance(expected_plan_fingerprint, str) or SHA.fullmatch(expected_plan_fingerprint) is None:
        _abort("desktop_asset_activity_input_invalid")
    data_space = _owner_directory(data_space_path)
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    active_ledger = None if binding["status"] == "absent" else Path(binding["ledger_path"])
    source_row_count = projection.get("source_row_count") if isinstance(projection, dict) else None
    matched = _matching_cutover(active_ledger, expected_plan_fingerprint, source_row_count)
    if matched is not None:
        payload = {
            "product_asset_activity_preview_version": CONTRACT_VERSION,
            "status": "already_committed",
            "schema_version": 401,
            "plan_fingerprint": expected_plan_fingerprint,
            "event_count": matched["event_count"],
            "source_row_count": matched["source_row_count"],
            "existing_asset_activity_event_count": binding["asset_activity_event_count"],
            "semantic_contracts": list(binding["semantic_contracts"]),
            "authority_contract": "schema201_derived_base_plus_asset_activity_v1",
            "active_generation_ref": binding["generation_ref"],
            "canonical_write": False,
            "provider_access": False,
            "network_access": False,
            "private_data_access": False,
        }
        payload["product_preview_fingerprint"] = _sha(payload)
        return payload
    with tempfile.TemporaryDirectory(prefix=".asset-activity-preview-", dir=data_space) as temporary:
        temporary_path = Path(temporary)
        os.chmod(temporary_path, 0o700)
        target = temporary_path / LEDGER_NAME
        materialized = materialize_desktop_product_semantic_ledger_v1(
            canonical_path, active_ledger, target, context
        )
        _assert_target_unused(target, _target_asset_ref(review))
        try:
            preview = preview_recomputed_per_asset_schema400_cutover_v1(
                target,
                _compat_context(context),
                portfolio_id,
                projection,
                review,
                expected_plan_fingerprint,
            )
        except Schema400AssetActivityCompatV1Error as error:
            if error.code == "schema400_asset_activity_source_stale":
                _abort("desktop_asset_activity_plan_stale")
            _abort("desktop_asset_activity_source_invalid")
        return _preview_payload(preview, materialized, binding, expected_plan_fingerprint)


def _atomic_json_replace(path: Path, value: Mapping[str, Any]) -> None:
    parent = _owner_directory(path.parent)
    if path.is_symlink() or path.exists() and not path.is_file():
        _abort("desktop_asset_activity_publication_failed")
    payload = _canonical(value) + b"\n"
    temporary = parent / f".{path.name}.tmp-{secrets.token_hex(8)}"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short_write")
            view = view[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    except OSError:
        os.close(descriptor)
        temporary.unlink(missing_ok=True)
        _abort("desktop_asset_activity_publication_failed")
    os.close(descriptor)
    try:
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError:
        temporary.unlink(missing_ok=True)
        _abort("desktop_asset_activity_publication_failed")


class _ProductWriterLockV1:
    """Process-shared lock for Product generation publication and recovery."""

    def __init__(self, area: Path):
        self.area = _owner_directory(area)
        self.path = self.area / LOCK_NAME
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        self.descriptor: int | None = None
        try:
            self.descriptor = os.open(self.path, flags, 0o600)
            metadata = os.fstat(self.descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
            ):
                _abort("desktop_asset_activity_storage_invalid")
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            _abort("desktop_asset_activity_lock_unavailable")
        except DesktopProductAssetActivityV1Error:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            raise
        except OSError:
            if self.descriptor is not None:
                os.close(self.descriptor)
                self.descriptor = None
            _abort("desktop_asset_activity_storage_invalid")

    def __enter__(self) -> "_ProductWriterLockV1":
        return self

    def __exit__(self, *_: object) -> None:
        if self.descriptor is not None:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            os.close(self.descriptor)
            self.descriptor = None


class _CanonicalReadBarrierV1:
    """Hold the canonical writer's directory lock through active replacement."""

    def __init__(self, data_space: Path):
        self.path = data_space / CANONICAL_LOCK_NAME
        self.held = False
        if self.path.is_symlink():
            _abort("desktop_asset_activity_canonical_invalid")
        try:
            os.mkdir(self.path, 0o700)
            os.chmod(self.path, 0o700)
            self.held = True
        except FileExistsError:
            _abort("desktop_asset_activity_lock_unavailable")
        except OSError:
            _abort("desktop_asset_activity_storage_invalid")

    def __enter__(self) -> "_CanonicalReadBarrierV1":
        return self

    def __exit__(self, *_: object) -> None:
        if self.held:
            try:
                os.rmdir(self.path)
            except OSError:
                _abort("desktop_asset_activity_storage_invalid")
            self.held = False


def _failpoint(value: Any, point: str) -> None:
    if callable(value):
        try:
            value(point)
        except DesktopProductAssetActivityV1Error:
            raise
        except Exception:
            _abort("synthetic_desktop_asset_activity_failpoint")
        return
    if value == point:
        _abort("synthetic_desktop_asset_activity_failpoint")


def _write_new_file(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        _abort("desktop_asset_activity_generation_conflict")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short_write")
            view = view[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    except OSError:
        os.close(descriptor)
        path.unlink(missing_ok=True)
        _abort("desktop_asset_activity_publication_failed")
    os.close(descriptor)


def _result_from_binding(
    status: str, binding: Mapping[str, Any], event_count: int, *, canonical_write: bool
) -> DesktopProductAssetActivityResultV1:
    return DesktopProductAssetActivityResultV1(
        status,
        binding["generation_ref"],
        event_count,
        binding["asset_activity_event_count"],
        401,
        canonical_write,
        0,
        tuple(binding["semantic_contracts"]),
    )


def _generation_candidates(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    canonical_fingerprint: str,
    expected_plan_fingerprint: str,
) -> list[dict[str, Any]]:
    if (
        not isinstance(expected_plan_fingerprint, str)
        or SHA.fullmatch(expected_plan_fingerprint) is None
    ):
        _abort("desktop_asset_activity_generation_invalid")
    generations_path = area / "generations"
    if not generations_path.exists():
        return []
    generations = _owner_directory(generations_path)
    candidates: list[dict[str, Any]] = []
    try:
        children = list(generations.iterdir())
    except OSError:
        _abort("desktop_asset_activity_storage_invalid")
    for child in children:
        if child.name.startswith(".staging-"):
            continue
        if child.is_symlink() or GENERATION.fullmatch(child.name) is None:
            _abort("desktop_asset_activity_generation_invalid")
        generation = _owner_directory(child)
        manifest_path = _owner_file(
            generation / MANIFEST_NAME, "desktop_asset_activity_generation_invalid"
        )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _abort("desktop_asset_activity_generation_invalid")
        if (
            not isinstance(manifest, dict)
            or manifest.get("plan_fingerprint") != expected_plan_fingerprint
        ):
            continue
        ledger = _owner_file(
            generation / LEDGER_NAME, "desktop_asset_activity_generation_invalid"
        )
        success = _owner_file(
            generation / SUCCESS_NAME, "desktop_asset_activity_generation_invalid"
        )
        if success.read_bytes() != b"completed\n":
            _abort("desktop_asset_activity_generation_invalid")
        required_manifest = {
            "contract_version", "authority_contract", "context_fingerprint", "generation_ref",
            "canonical_schema_version", "canonical_fingerprint", "prior_activity_set_fingerprint",
            "activity_set_fingerprint", "ledger_schema_version", "ledger_fingerprint",
            "plan_fingerprint", "command_id", "new_event_count", "total_asset_activity_event_count",
            "committed_at_utc", "semantic_contracts", "boundaries",
        }
        if (
            not isinstance(manifest, dict)
            or set(manifest) != required_manifest
            or manifest.get("contract_version") != CONTRACT_VERSION
            or manifest.get("authority_contract") != "schema201_derived_base_plus_asset_activity_v1"
            or manifest.get("generation_ref") != child.name
            or not isinstance(manifest.get("context_fingerprint"), str)
            or SHA.fullmatch(manifest["context_fingerprint"]) is None
            or manifest.get("canonical_schema_version") not in {201, 202}
            or manifest.get("ledger_schema_version") != 401
            or manifest.get("ledger_fingerprint") != _sha_file(ledger)
            or manifest.get("canonical_fingerprint") != canonical_fingerprint
            or manifest.get("semantic_contracts") != [
                "portfolio_ledger_v1_transaction_fact", "asset_activity_v1"
            ]
            or not isinstance(manifest.get("plan_fingerprint"), str)
            or SHA.fullmatch(manifest["plan_fingerprint"]) is None
            or not isinstance(manifest.get("command_id"), str)
            or re.fullmatch(r"cmd_asset_[a-f0-9]{48}", manifest["command_id"]) is None
            or not isinstance(manifest.get("activity_set_fingerprint"), str)
            or SHA.fullmatch(manifest["activity_set_fingerprint"]) is None
            or not isinstance(manifest.get("prior_activity_set_fingerprint"), str)
            or SHA.fullmatch(manifest["prior_activity_set_fingerprint"]) is None
            or not isinstance(manifest.get("new_event_count"), int)
            or manifest["new_event_count"] < 1
            or not isinstance(manifest.get("total_asset_activity_event_count"), int)
            or manifest["total_asset_activity_event_count"] < manifest["new_event_count"]
        ):
            continue
        connection = _read_connection(ledger)
        try:
            writer_context_matches = _generation_writer_context_matches(
                connection, manifest["context_fingerprint"], context
            )
            activity = _activity_rows(connection)
        finally:
            connection.close()
        if (
            not writer_context_matches
            or activity["activity_set_fingerprint"] != manifest["activity_set_fingerprint"]
            or len(activity["asset_activity_events"])
            != manifest["total_asset_activity_event_count"]
        ):
            continue
        candidates.append({
            "generation_ref": child.name,
            "ledger_path": str(ledger),
            "ledger_fingerprint": manifest["ledger_fingerprint"],
            "manifest_fingerprint": _sha_file(manifest_path),
            "activity_set_fingerprint": manifest["activity_set_fingerprint"],
            "asset_activity_event_count": manifest["total_asset_activity_event_count"],
            "semantic_contracts": tuple(manifest["semantic_contracts"]),
            "manifest": manifest,
        })
    return candidates


def _generation_candidate_for_plan(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    canonical_fingerprint: str,
    plan_fingerprint: str,
    source_row_count: int | None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for candidate in _generation_candidates(
        area, context, canonical_fingerprint, plan_fingerprint
    ):
        manifest = candidate["manifest"]
        if manifest.get("plan_fingerprint") != plan_fingerprint:
            continue
        matched = _matching_cutover(
            Path(candidate["ledger_path"]), plan_fingerprint, source_row_count
        )
        if matched is not None:
            candidates.append({**candidate, "matched": matched})
    if len(candidates) > 1:
        _abort("desktop_asset_activity_generation_conflict")
    return None if not candidates else candidates[0]


def _activate_generation_candidate(
    area: Path, data_space: Path, context: DesktopProductAssetActivityContextV1,
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    _atomic_json_replace(
        area / ACTIVE_NAME,
        {
            "contract_version": CONTRACT_VERSION,
            "generation_ref": candidate["generation_ref"],
            "ledger_fingerprint": candidate["ledger_fingerprint"],
            "manifest_fingerprint": candidate["manifest_fingerprint"],
        },
    )
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if (
        binding["generation_ref"] != candidate["generation_ref"]
        or binding["activity_set_fingerprint"] != candidate["activity_set_fingerprint"]
    ):
        _abort("desktop_asset_activity_publication_failed")
    return binding


def _remove_staging_generations(generations: Path) -> None:
    try:
        entries = list(generations.iterdir())
    except OSError:
        _abort("desktop_asset_activity_storage_invalid")
    for entry in entries:
        if not entry.name.startswith(".staging-"):
            continue
        if entry.is_symlink() or not entry.is_dir():
            _abort("desktop_asset_activity_storage_invalid")
        try:
            shutil.rmtree(entry)
        except OSError:
            # #568: Ein nach hartem Ausschalten unlesbarer Zwischenordner (leere gocryptfs.diriv) gehoert nie zum gueltigen Stand - die
            # Leser ueberspringen .staging-* ohnehin. Er bleibt liegen, statt jede weitere Buchung zu blockieren; die Karte „Backups“ meldet
            # ihn nach dem Entsperren und nimmt ihn auf Bestaetigung in Quarantaene.
            if _unreadable_directory(entry):
                continue
            _abort("desktop_asset_activity_storage_invalid")


def _unreadable_directory(path: Path) -> bool:
    try:
        os.listdir(path)
    except OSError as error:
        return error.errno == errno.EIO
    return False


def apply_desktop_product_per_asset_cutover_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    portfolio_id: str,
    projection: Any,
    review: Any,
    expected_plan_fingerprint: str,
    expected_preview_fingerprint: str,
    committed_at_utc: str,
    *,
    failpoint: Any = None,
) -> DesktopProductAssetActivityResultV1:
    """Append under one process-shared lock and atomically activate a generation."""

    context = _context(context_value)
    committed = _utc(committed_at_utc)
    if (
        not (failpoint is None or callable(failpoint) or failpoint in ALLOWED_FAILPOINTS)
        or not isinstance(expected_plan_fingerprint, str)
        or SHA.fullmatch(expected_plan_fingerprint) is None
        or not isinstance(expected_preview_fingerprint, str)
        or SHA.fullmatch(expected_preview_fingerprint) is None
    ):
        _abort("desktop_asset_activity_input_invalid")
    data_space = _owner_directory(data_space_path)
    area = _owner_directory(data_space / PRODUCT_AREA, create=True)

    with _ProductWriterLockV1(area):
        with _CanonicalReadBarrierV1(data_space):
            canonical = _canonical_snapshot(canonical_path, context)
            _failpoint(failpoint, "after_initial_canonical_snapshot")
        expected_canonical_fingerprint = canonical["source_fingerprint"]
        binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
        active_ledger = None if binding["status"] == "absent" else Path(binding["ledger_path"])
        source_row_count = projection.get("source_row_count") if isinstance(projection, dict) else None
        matched = _matching_cutover(active_ledger, expected_plan_fingerprint, source_row_count)
        if matched is not None:
            if binding.get("canonical_fingerprint") != expected_canonical_fingerprint:
                _abort("desktop_asset_activity_canonical_changed")
            return _result_from_binding(
                "already_committed", binding, matched["event_count"], canonical_write=False
            )

        generations = _owner_directory(area / "generations", create=True)
        _remove_staging_generations(generations)
        candidate = _generation_candidate_for_plan(
            area, context, expected_canonical_fingerprint,
            expected_plan_fingerprint, source_row_count,
        )
        if candidate is not None:
            with _CanonicalReadBarrierV1(data_space):
                _failpoint(failpoint, "before_recovery_canonical_recheck")
                if _sha_file(canonical["path"]) != expected_canonical_fingerprint:
                    _abort("desktop_asset_activity_canonical_changed")
                recovered = _activate_generation_candidate(area, data_space, context, candidate)
            return _result_from_binding(
                "recovered_committed", recovered, candidate["matched"]["event_count"],
                canonical_write=False,
            )

        staging = generations / f".staging-{secrets.token_hex(16)}"
        try:
            os.mkdir(staging, 0o700)
            os.chmod(staging, 0o700)
        except OSError:
            _abort("desktop_asset_activity_storage_invalid")
        generation_published = False
        try:
            target = staging / LEDGER_NAME
            materialized = materialize_desktop_product_semantic_ledger_v1(
                canonical["path"], active_ledger, target, context
            )
            if materialized["canonical_fingerprint"] != expected_canonical_fingerprint:
                _abort("desktop_asset_activity_canonical_changed")
            _assert_target_unused(target, _target_asset_ref(review))
            try:
                preview = preview_recomputed_per_asset_schema400_cutover_v1(
                    target, _compat_context(context), portfolio_id, projection, review,
                    expected_plan_fingerprint,
                )
            except Schema400AssetActivityCompatV1Error as error:
                if error.code == "schema400_asset_activity_source_stale":
                    _abort("desktop_asset_activity_plan_stale")
                _abort("desktop_asset_activity_source_invalid")
            if preview["preview_fingerprint"] != expected_preview_fingerprint:
                _abort("desktop_asset_activity_plan_stale")
            challenge = "sac_" + _sha(
                {
                    "contract_version": "desktop_product_asset_activity_confirmation_v1",
                    "context_fingerprint": _context_fingerprint(context),
                    "preview_fingerprint": preview["preview_fingerprint"],
                    "committed_at_utc": committed,
                }
            )[:32]
            confirmation = build_schema400_asset_activity_confirmation_v1(
                preview, _compat_context(context), challenge,
                committed, committed, _offset(committed, 300),
            )
            authorizer = OneUseSchema400AssetActivityAuthorizerV1()
            authorizer.register(confirmation)
            try:
                result = apply_recomputed_per_asset_schema400_cutover_v1(
                    target, _compat_context(context), portfolio_id, projection, review,
                    expected_plan_fingerprint, confirmation, authorizer, committed,
                )
            except Schema400AssetActivityCompatV1Error as error:
                if error.code in {
                    "schema400_asset_activity_source_stale",
                    "schema400_asset_activity_confirmation_scope_mismatch",
                }:
                    _abort("desktop_asset_activity_plan_stale")
                _abort("desktop_asset_activity_source_invalid")
            connection = _read_connection(target)
            try:
                activity = _activity_rows(connection)
                semantic_counts = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT semantic_contract,count(*) FROM compatible_ledger_event GROUP BY semantic_contract"
                    )
                }
            finally:
                connection.close()
            if set(semantic_counts) - {
                "portfolio_ledger_v1_transaction_fact", "asset_activity_v1"
            } or semantic_counts.get("asset_activity_v1", 0) != len(activity["asset_activity_events"]):
                _abort("desktop_asset_activity_ledger_invalid")
            ledger_fingerprint = _sha_file(target)
            generation_ref = "gen_" + _sha(
                {
                    "canonical_fingerprint": expected_canonical_fingerprint,
                    "activity_set_fingerprint": activity["activity_set_fingerprint"],
                    "command_id": result.command_id,
                    "plan_fingerprint": expected_plan_fingerprint,
                }
            )[:32]
            manifest = {
                "contract_version": CONTRACT_VERSION,
                "authority_contract": "schema201_derived_base_plus_asset_activity_v1",
                "context_fingerprint": _context_fingerprint(context),
                "generation_ref": generation_ref,
                "canonical_schema_version": materialized["canonical_schema_version"],
                "canonical_fingerprint": expected_canonical_fingerprint,
                "prior_activity_set_fingerprint": materialized["activity_set_fingerprint"],
                "activity_set_fingerprint": activity["activity_set_fingerprint"],
                "ledger_schema_version": 401,
                "ledger_fingerprint": ledger_fingerprint,
                "plan_fingerprint": expected_plan_fingerprint,
                "command_id": result.command_id,
                "new_event_count": result.event_count,
                "total_asset_activity_event_count": len(activity["asset_activity_events"]),
                "committed_at_utc": committed,
                "semantic_contracts": [
                    "portfolio_ledger_v1_transaction_fact", "asset_activity_v1"
                ],
                "boundaries": {
                    "schema201_catalog_authority": "derived_read_only",
                    "schema201_transaction_authority": "derived_read_only",
                    "asset_activity_authority": "data_app_append_only",
                    "automatic_cash_posting_count": 0,
                    "provider_access": False,
                    "network_access": False,
                },
            }
            _write_new_file(staging / MANIFEST_NAME, _canonical(manifest) + b"\n")
            _write_new_file(staging / SUCCESS_NAME, b"completed\n")
            _failpoint(failpoint, "after_generation_complete")
            final = generations / generation_ref
            if final.exists() or final.is_symlink():
                _abort("desktop_asset_activity_generation_conflict")
            try:
                settle_new_directory_v1(staging)  # #568: auch die gocryptfs.diriv neuer Ordner festschreiben
                os.rename(staging, final)
                directory = os.open(generations, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory)
                finally:
                    os.close(directory)
            except OSError:
                _abort("desktop_asset_activity_publication_failed")
            generation_published = True
            _failpoint(failpoint, "after_generation_publish")

            # This is the final authority recheck: no active pointer can be replaced
            # after the source schema-201 bytes have changed.
            with _CanonicalReadBarrierV1(data_space):
                _failpoint(failpoint, "before_final_canonical_recheck")
                if _sha_file(canonical["path"]) != expected_canonical_fingerprint:
                    _abort("desktop_asset_activity_canonical_changed")
                _failpoint(failpoint, "before_active_replace")
                active = {
                    "contract_version": CONTRACT_VERSION,
                    "generation_ref": generation_ref,
                    "ledger_fingerprint": ledger_fingerprint,
                    "manifest_fingerprint": _sha_file(final / MANIFEST_NAME),
                }
                _atomic_json_replace(area / ACTIVE_NAME, active)
            _failpoint(failpoint, "after_active_replace")
            verified = read_desktop_product_asset_activity_binding_v1(data_space, context)
            if (
                verified["generation_ref"] != generation_ref
                or verified["activity_set_fingerprint"] != activity["activity_set_fingerprint"]
            ):
                _abort("desktop_asset_activity_publication_failed")
            return DesktopProductAssetActivityResultV1(
                result.status, generation_ref, result.event_count,
                len(activity["asset_activity_events"]), 401, True, 0,
                tuple(manifest["semantic_contracts"]),
            )
        finally:
            if not generation_published and staging.exists() and not staging.is_symlink():
                shutil.rmtree(staging, ignore_errors=True)


NATIVE_EVENT_KEYS = {
    "event_ref", "event_type", "account_ref", "related_account_ref", "asset_ref",
    "source_asset_ref", "event_time_evidence", "local_date", "local_time", "time_zone",
    "effective_at_utc", "original_acquired_time_evidence", "original_acquired_local_date",
    "original_acquired_local_time", "original_acquired_time_zone", "original_acquired_at_utc",
    "amount_input_mode", "basis_evidence_mode", "quantity_decimal", "eligible_quantity_decimal",
    "unit_price_decimal", "gross_amount_decimal", "monetary_fee_decimal",
    "asset_fee_quantity_decimal", "provided_basis_decimal", "movement_context_code",
}
FIFO_ORDER_EVIDENCE_KEYS = {
    "event_ref", "evidence_mode", "source_file_fingerprint", "source_row_ordinal",
    "owner_decision_fingerprint", "evidence_fingerprint",
}


def _native_fifo_order_evidence(value: Any, event: Mapping[str, Any]) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != FIFO_ORDER_EVIDENCE_KEYS:
        _abort("desktop_asset_activity_input_invalid")
    row = dict(value)
    body = {key: row[key] for key in FIFO_ORDER_EVIDENCE_KEYS if key != "evidence_fingerprint"}
    ordinal = row.get("source_row_ordinal")
    if (
        row.get("event_ref") != event.get("event_ref")
        or row.get("evidence_mode") != "owner_confirmed_source_row_order"
        or not isinstance(row.get("source_file_fingerprint"), str)
        or SHA.fullmatch(row["source_file_fingerprint"]) is None
        or isinstance(ordinal, bool)
        or not isinstance(ordinal, int)
        or ordinal < 1
        or not isinstance(row.get("owner_decision_fingerprint"), str)
        or SHA.fullmatch(row["owner_decision_fingerprint"]) is None
        or row.get("evidence_fingerprint") != _sha(body)
        or event.get("event_type") not in {
            "buy", "sell", "stock_dividend", "reward", "deposit", "withdrawal", "transfer"
        }
        or event.get("event_time_evidence") != "exact"
        or event.get("effective_at_utc") is None
    ):
        _abort("desktop_asset_activity_input_invalid")
    return row


def _native_fifo_order_evidence_rows(
    value: Any, event: Mapping[str, Any], ledger_path: Path | None,
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        row = _native_fifo_order_evidence(value, event)
        return [] if row is None else [row]
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) < 2 or ledger_path is None:
        _abort("desktop_asset_activity_input_invalid")
    refs = [item.get("event_ref") for item in value if isinstance(item, Mapping)]
    if len(refs) != len(value) or len(set(refs)) != len(refs) or event.get("event_ref") not in refs:
        _abort("desktop_asset_activity_input_invalid")
    peer_refs = [ref for ref in refs if ref != event["event_ref"]]
    connection = _read_connection(ledger_path)
    try:
        peers = {
            row["event_ref"]: dict(row)
            for row in connection.execute(
                "SELECT event_ref,event_type,asset_id AS asset_ref,local_date,effective_at_utc,event_time_evidence FROM asset_activity_event WHERE event_ref IN (%s)"
                % ",".join("?" for _ in peer_refs), peer_refs,
            )
        }
    except sqlite3.Error:
        _abort("desktop_asset_activity_ledger_invalid")
    finally:
        connection.close()
    events = {event["event_ref"]: dict(event), **peers}
    if set(events) != set(refs):
        _abort("desktop_asset_activity_input_invalid")
    try:
        from workers.reference.semantic_realized_fifo_v2 import build_owner_confirmed_source_row_order_evidence_v1
        source_rows = {
            item["event_ref"]: {
                "source_file_fingerprint": item.get("source_file_fingerprint"),
                "source_row_ordinal": item.get("source_row_ordinal"),
            }
            for item in value
        }
        expected = build_owner_confirmed_source_row_order_evidence_v1(list(events.values()), source_rows)
    except Exception:
        _abort("desktop_asset_activity_input_invalid")
    normalized = sorted((dict(item) for item in value), key=lambda item: item["event_ref"])
    if normalized != expected:
        _abort("desktop_asset_activity_input_invalid")
    return normalized


def _insert_native_fifo_order_evidence(
    connection: sqlite3.Connection,
    evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None,
) -> None:
    if evidence is None:
        return
    if not _fifo_order_evidence_table_exists(connection):
        _abort("desktop_asset_activity_ledger_invalid")
    columns = [
        "event_ref", "evidence_mode", "source_file_fingerprint", "source_row_ordinal",
        "owner_decision_fingerprint", "evidence_fingerprint",
    ]
    rows = [evidence] if isinstance(evidence, Mapping) else list(evidence)
    for row in rows:
        existing = connection.execute(
            "SELECT * FROM asset_activity_fifo_order_evidence WHERE event_ref=?", (row["event_ref"],)
        ).fetchone()
        if existing is not None:
            actual = dict(existing) if isinstance(existing, sqlite3.Row) else dict(zip(columns, existing))
            if actual != dict(row):
                _abort("desktop_asset_activity_ledger_invalid")
            continue
        connection.execute(
            f"INSERT INTO asset_activity_fifo_order_evidence ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            tuple(row[column] for column in columns),
        )


def _native_attempt_payload(
    context: DesktopProductAssetActivityContextV1,
    command_fingerprint: str,
    preview_fingerprint: str,
    committed_at_utc: str,
) -> dict[str, Any]:
    body = {
        "native_asset_activity_attempt_version": 1,
        "attempt_status": "consumed_before_domain_write",
        "context_fingerprint": _context_fingerprint(context),
        "command_fingerprint": command_fingerprint,
        "preview_fingerprint": preview_fingerprint,
        "committed_at_utc": committed_at_utc,
    }
    body["attempt_fingerprint"] = _sha(body)
    return body


def _persist_native_attempt(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    command_fingerprint: str,
    preview_fingerprint: str,
    committed_at_utc: str,
) -> Path:
    attempts = _owner_directory(area / NATIVE_ATTEMPT_AREA, create=True)
    path = attempts / (command_fingerprint + ".json")
    payload = _canonical(_native_attempt_payload(context, command_fingerprint, preview_fingerprint, committed_at_utc)) + b"\n"
    if path.exists():
        if _owner_file(path, "desktop_asset_activity_plan_stale").read_bytes() != payload:
            _abort("desktop_asset_activity_plan_stale")
        return path
    _write_new_file(path, payload)
    return path


def _validate_native_attempt(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    command_fingerprint: str,
    preview_fingerprint: str,
) -> None:
    path = _owner_file(area / NATIVE_ATTEMPT_AREA / (command_fingerprint + ".json"), "desktop_asset_activity_generation_invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _abort("desktop_asset_activity_generation_invalid")
    if (
        not isinstance(value, dict)
        or value.get("context_fingerprint") != _context_fingerprint(context)
        or value.get("command_fingerprint") != command_fingerprint
        or value.get("preview_fingerprint") != preview_fingerprint
        or path.read_bytes() != _canonical(value) + b"\n"
        or value.get("attempt_fingerprint") != _sha({key: item for key, item in value.items() if key != "attempt_fingerprint"})
    ):
        _abort("desktop_asset_activity_generation_invalid")


def _native_command_fingerprint(
    context: DesktopProductAssetActivityContextV1,
    portfolio_id: str,
    events: Sequence[Mapping[str, Any]],
    fifo_order_evidence: Mapping[str, Any] | None = None,
) -> str:
    body = {
        "contract_version": "desktop_native_asset_activity_command_v1",
        "context_fingerprint": _context_fingerprint(context),
        "portfolio_id": portfolio_id,
        "events": list(events),
    }
    if fifo_order_evidence is not None:
        body["fifo_order_evidence"] = dict(fifo_order_evidence) if isinstance(fifo_order_evidence, Mapping) else [dict(row) for row in fifo_order_evidence]
    return _sha(body)


def _public_native_ref(prefix: str, context: DesktopProductAssetActivityContextV1, value: str) -> str:
    _, _, _, context_fp = semantic_context_values({
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "data_space_id": context.data_space_id,
    })
    return semantic_public_ref(prefix, context_fp, value)


def _native_events(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 1:
        _abort("desktop_asset_activity_input_invalid")
    events: list[dict[str, Any]] = []
    for event in value:
        if not isinstance(event, Mapping) or set(event) != NATIVE_EVENT_KEYS:
            _abort("desktop_asset_activity_input_invalid")
        normalized = dict(event)
        if normalized.get("event_time_evidence") == "exact":
            resolved = resolve_desktop_asset_activity_time_v1(
                normalized.get("local_date"), normalized.get("local_time"),
                normalized.get("time_zone"),
            )
            if normalized.get("effective_at_utc") != resolved["effective_at_utc"]:
                _abort("desktop_asset_activity_input_invalid")
        elif normalized.get("event_time_evidence") == "date_only":
            if normalized.get("local_time") is not None or normalized.get("effective_at_utc") is not None:
                _abort("desktop_asset_activity_input_invalid")
            if (
                not isinstance(normalized.get("local_date"), str)
                or LOCAL_DATE.fullmatch(normalized["local_date"]) is None
                or date.fromisoformat(normalized["local_date"]).isoformat() != normalized["local_date"]
                or not isinstance(normalized.get("time_zone"), str)
            ):
                _abort("desktop_asset_activity_input_invalid")
            try:
                ZoneInfo(normalized["time_zone"])
            except (ValueError, ZoneInfoNotFoundError):
                _abort("desktop_asset_activity_input_invalid")
        else:
            _abort("desktop_asset_activity_input_invalid")
        original_mode = normalized.get("original_acquired_time_evidence")
        if original_mode == "exact":
            resolved_original = resolve_desktop_asset_activity_time_v1(
                normalized.get("original_acquired_local_date"),
                normalized.get("original_acquired_local_time"),
                normalized.get("original_acquired_time_zone"),
            )
            if normalized.get("original_acquired_at_utc") != resolved_original["effective_at_utc"]:
                _abort("desktop_asset_activity_input_invalid")
        elif original_mode == "date_only":
            if (
                not isinstance(normalized.get("original_acquired_local_date"), str)
                or LOCAL_DATE.fullmatch(normalized["original_acquired_local_date"]) is None
                or date.fromisoformat(normalized["original_acquired_local_date"]).isoformat()
                != normalized["original_acquired_local_date"]
                or normalized.get("original_acquired_local_time") is not None
                or normalized.get("original_acquired_at_utc") is not None
                or not isinstance(normalized.get("original_acquired_time_zone"), str)
            ):
                _abort("desktop_asset_activity_input_invalid")
            try:
                ZoneInfo(normalized["original_acquired_time_zone"])
            except (ValueError, ZoneInfoNotFoundError):
                _abort("desktop_asset_activity_input_invalid")
        elif original_mode == "not_applicable":
            if any(
                normalized.get(key) is not None
                for key in (
                    "original_acquired_local_date", "original_acquired_local_time",
                    "original_acquired_time_zone", "original_acquired_at_utc",
                )
            ):
                _abort("desktop_asset_activity_input_invalid")
        else:
            _abort("desktop_asset_activity_input_invalid")
        events.append(normalized)
    return events


def _native_expected_preview_fingerprint(
    schema_preview_fingerprint: str,
    command_fingerprint: str,
    fifo_order_evidence: Mapping[str, Any] | None,
) -> str:
    if fifo_order_evidence is None:
        return schema_preview_fingerprint
    return _sha({
        "native_asset_activity_evidence_bound_preview_version": 1,
        "schema_preview_fingerprint": schema_preview_fingerprint,
        "command_fingerprint": command_fingerprint,
        "fifo_order_evidence_fingerprint": fifo_order_evidence["evidence_fingerprint"] if isinstance(fifo_order_evidence, Mapping) else _sha([dict(row) for row in fifo_order_evidence]),
    })


def _native_preview_payload(
    preview: Mapping[str, Any],
    materialized: Mapping[str, Any],
    binding: Mapping[str, Any],
    command_fingerprint: str,
    fifo_evidence: Mapping[str, Any],
    context: DesktopProductAssetActivityContextV1,
    fifo_order_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    effect = preview["event_effects"][0]
    event = fifo_evidence["event"]
    safe_event_result = {
        key: fifo_evidence["event_result"][key]
        for key in (
            "event_sequence", "effective_at_utc", "local_date", "event_time_evidence",
            "event_type", "asset_type", "currency", "quantity_decimal", "amount_decimal",
            "fee_decimal", "asset_fee_quantity_decimal", "basis_added_decimal",
            "basis_consumed_decimal", "gross_proceeds_decimal",
            "realized_gross_gain_decimal", "gross_income_decimal",
            "distribution_value_decimal", "cash_balance_delta_decimal", "holding_effect",
            "projection_status", "semantic_contract", "coupled_transaction_fact",
            "automatic_cash_posting_created", "basis_added_exact", "basis_consumed_exact",
            "realized_gross_gain_exact", "fifo_authority",
        )
    }
    result = {
        "native_asset_activity_preview_version": 2,
        "status": "ready_for_confirmation",
        "schema_version": 401,
        "command_ref": _public_native_ref("nac_", context, command_fingerprint),
        "event_type": event["event_type"],
        "event_time_evidence": event["event_time_evidence"],
        "local_date": event["local_date"],
        "local_time": event["local_time"],
        "time_zone": event["time_zone"],
        "effective_at_utc": event["effective_at_utc"],
        "inventory_effect_code": effect["inventory_effect_code"],
        "fifo_effect_code": effect["fifo_effect_code"],
        "portfolio_quantity_change_decimal": effect["portfolio_quantity_change_decimal"],
        "fifo_basis_created_decimal": effect["fifo_basis_created_decimal"],
        "net_trade_proceeds_decimal": effect["net_trade_proceeds_decimal"],
        "gross_income_decimal": effect["gross_income_decimal"],
        "distribution_value_decimal": effect["distribution_value_decimal"],
        "cash_posting_count": preview["cash_posting_count"],
        "provider_price_use_count": preview["provider_price_use_count"],
        "tax_classification_inference_count": preview["tax_classification_inference_count"],
        "existing_asset_activity_event_count": materialized["asset_activity_event_count"],
        "cost_average": fifo_evidence["cost_average"],
        "event_result": safe_event_result,
        "fifo_version": fifo_evidence["fifo_version"],
        "fifo_world_dimension": fifo_evidence["fifo_world_dimension"],
        "custody_dimension": fifo_evidence["custody_dimension"],
        "rounding_performed": fifo_evidence["rounding_performed"],
        "coupled_transaction_facts_in_fifo": False,
        "semantic_contracts": ["asset_activity_v1"],
        "authority_contract": "schema201_derived_base_plus_asset_activity_v1",
        "confirmation_required": True,
        "one_attempt_only": True,
        "canonical_write": False,
        "schema201_canonical_write": False,
        "automatic_cash_posting_created": False,
        "provider_access": False,
        "network_access": False,
        "private_data_access": False,
        "path_exposed": False,
        "internal_id_exposed": False,
    }
    result["preview_fingerprint"] = _native_expected_preview_fingerprint(
        preview["preview_fingerprint"], command_fingerprint, fifo_order_evidence
    )
    result["command_fingerprint"] = command_fingerprint
    result["canonical_fingerprint"] = materialized["canonical_fingerprint"]
    result["prior_activity_set_fingerprint"] = materialized["activity_set_fingerprint"]
    result["active_generation_ref"] = binding.get("generation_ref")
    result["product_preview_fingerprint"] = _sha(result)
    return result


def _fifo_v2_exact_decimal(value: Mapping[str, Any]) -> str | None:
    status = value.get("exactness_status")
    if status == "exact_decimal":
        result = value.get("decimal")
        if not isinstance(result, str):
            _abort("desktop_asset_activity_fifo_invalid")
        return result
    if status in {"exact_ratio", "basis_missing", "not_applicable"}:
        return None
    _abort("desktop_asset_activity_fifo_invalid")


def _fifo_v2_cost_average(position: Mapping[str, Any]) -> dict[str, Any]:
    exact = position["cost_average"]
    status = exact.get("exactness_status")
    mapped = {
        "not_applicable": "empty_position",
        "basis_missing": "basis_missing",
        "exact_decimal": "exact_decimal",
        "exact_ratio": "exact_ratio",
    }.get(status)
    if mapped is None:
        _abort("desktop_asset_activity_fifo_invalid")
    basis = position["remaining_fifo_basis"]
    body = {
        "cost_average_status": mapped,
        "remaining_quantity_decimal": position["remaining_quantity_decimal"],
        "remaining_fifo_basis_decimal": _fifo_v2_exact_decimal(basis),
        "cost_average_decimal": _fifo_v2_exact_decimal(exact),
        "cost_average_exact": dict(exact),
        "cost_average_numerator_integer": exact.get("numerator_integer") if status in {"exact_decimal", "exact_ratio"} else None,
        "cost_average_denominator_integer": exact.get("denominator_integer") if status in {"exact_decimal", "exact_ratio"} else None,
    }
    return {**body, "cost_average_fingerprint": _sha(body)}


def _native_fifo_inputs(data_space: str | Path | None, context: DesktopProductAssetActivityContextV1) -> tuple[list, list, list]:
    """Wertermittlung je Wallet (rc.294), FIFO-Wallet aus mehreren Konten (#508) und Splits (#451) fuer die Probe einer neuen
    Buchung.

    Ohne sie rechnete die Vorschau den Verbrauch je Konto mit FIFO, auch wo der Stand danach anders rechnet - und nach einem Split
    wiese sie jeden Verkauf in neuen Stuecken als zu gross ab. Laesst sich ein Speicher nicht lesen, rechnet die Vorschau wie
    bisher; das Fortschreiben des Stands bricht dann ohnehin ab."""
    if data_space is None:
        return [], [], []
    from migrations.reference.crypto_valuation_method_v1 import valuation_methods_for_fifo_v1
    from migrations.reference.fifo_wallet_v1 import fifo_wallets_for_fifo_v1
    from migrations.reference.stock_split_v1 import splits_for_fifo_v1
    try:
        methods = valuation_methods_for_fifo_v1(data_space, context)
    except Exception:
        methods = []
    try:
        wallets = fifo_wallets_for_fifo_v1(data_space, context)
    except Exception:
        wallets = []
    try:
        splits = splits_for_fifo_v1(data_space, context)
    except Exception:
        splits = []
    return methods, wallets, splits


def _native_fifo_preview(
    ledger: Path,
    context: DesktopProductAssetActivityContextV1,
    portfolio_id: str,
    event: Mapping[str, Any],
    effect: Mapping[str, Any],
    fifo_order_evidence: Mapping[str, Any] | None = None,
    data_space: str | Path | None = None,
) -> dict[str, Any]:
    probe = ledger.parent / f".fifo-probe-{secrets.token_hex(8)}.sqlite"
    try:
        shutil.copyfile(ledger, probe)
        os.chmod(probe, 0o600)
    except OSError:
        _abort("desktop_asset_activity_storage_invalid")
    connection = sqlite3.connect(probe)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        existing_refs = {
            row[0] for row in connection.execute("SELECT event_ref FROM asset_activity_event")
        }
        probe_ref = event["event_ref"] if fifo_order_evidence is not None else "evt_" + _sha({
            "contract_version": "desktop_native_asset_activity_fifo_probe_v1",
            "event": event,
        })[:32]
        if probe_ref in existing_refs:
            _abort("desktop_asset_activity_input_invalid")
        command_id = "cmd_asset_" + _sha({
            "contract_version": "desktop_native_asset_activity_fifo_probe_v1",
            "event_ref": probe_ref,
            "effect_fingerprint": effect["effect_fingerprint"],
        })[:48]
        committed = event["effective_at_utc"] or (event["local_date"] + "T23:59:59Z")
        payload_fingerprint = _sha({"probe": probe_ref, "effect": effect})
        confirmation_fingerprint = _sha({"probe": probe_ref, "confirmation": True})
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO ledger_command_receipt VALUES(?, 'data_app','asset_activity_create_v1',?,?,?,?)",
            (command_id, context.actor_id, payload_fingerprint, confirmation_fingerprint, committed),
        )
        probe_event = dict(event)
        probe_event["event_ref"] = probe_ref
        connection.execute(
            "INSERT INTO asset_activity_event VALUES(%s)" % ",".join("?" for _ in range(50)),
            _event_payload(
                probe_event, effect, portfolio_id, command_id, committed,
                "native", None, None,
            ),
        )
        _insert_native_fifo_order_evidence(connection, fifo_order_evidence)
        connection.execute("COMMIT")
    except DesktopProductAssetActivityV1Error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    except sqlite3.Error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        _abort("desktop_asset_activity_ledger_invalid")
    finally:
        connection.close()
    probe_world = None
    try:
        from workers.reference import asset_activity_realized_state_v2 as state_v2
        from workers.reference.semantic_realized_fifo_v2 import (
            SemanticRealizedFifoV2Error,
            project_semantic_realized_fifo_v2,
        )
        worlds = state_v2._ledger_worlds_v2(probe, *_native_fifo_inputs(data_space, context))
        matching_worlds = [
            world for world in worlds.values()
            if world["portfolio_ref"] == portfolio_id and world["asset_ref"] == event["asset_ref"]
        ]
        if len(matching_worlds) != 1:
            _abort("desktop_asset_activity_fifo_invalid")
        world = matching_worlds[0]
        probe_world = world["wrapper"]
        result = project_semantic_realized_fifo_v2(probe_world)
    except (state_v2.AssetActivityRealizedStateV2Error, SemanticRealizedFifoV2Error):
        # Die Welt, an der die Probe scheitert, und die Kennung der neuen Buchung darin
        # bleiben am Fehler haengen. Nur damit laesst sich spaeter sagen, an welcher
        # Buchung es liegt (#420); am Code und am Ablauf aendert das nichts.
        failure = DesktopProductAssetActivityV1Error("desktop_asset_activity_fifo_invalid")
        failure.fifo_world = probe_world
        failure.fifo_probe_event_ref = probe_ref
        raise failure
    finally:
        probe.unlink(missing_ok=True)
    rows = [row for row in result["event_results"] if row["event_ref"] == probe_ref]
    positions = [row for row in result["asset_positions"] if row["asset_ref"] == event["asset_ref"]]
    if len(rows) != 1 or len(positions) != 1:
        _abort("desktop_asset_activity_fifo_invalid")
    row = rows[0]
    asset = next(item for item in world["activity"]["assets"] if item["asset_ref"] == event["asset_ref"])
    holding = {
        "buy": "acquired", "stock_dividend": "acquired", "reward": "acquired", "deposit": "acquired",
        "sell": "consumed", "withdrawal": "consumed", "transfer": "transferred", "dividend": "no_holding_change",
    }[event["event_type"]]
    safe = {
        "event_sequence": row["event_sequence"],
        "effective_at_utc": event["effective_at_utc"],
        "local_date": event["local_date"],
        "event_time_evidence": event["event_time_evidence"],
        "event_type": event["event_type"],
        "asset_type": asset["asset_type"],
        "currency": effect["basis_currency"],
        "quantity_decimal": event["quantity_decimal"],
        "amount_decimal": effect["gross_economic_amount_decimal"],
        "fee_decimal": event["monetary_fee_decimal"],
        "asset_fee_quantity_decimal": event["asset_fee_quantity_decimal"],
        "basis_added_decimal": _fifo_v2_exact_decimal(row["basis_added"]),
        "basis_consumed_decimal": _fifo_v2_exact_decimal(row["basis_consumed"]),
        "gross_proceeds_decimal": effect["net_trade_proceeds_decimal"] or "0",
        "realized_gross_gain_decimal": _fifo_v2_exact_decimal(row["realized_gain"]),
        "gross_income_decimal": effect["gross_income_decimal"] or "0",
        "distribution_value_decimal": effect["distribution_value_decimal"] or "0",
        "cash_balance_delta_decimal": "0",
        "holding_effect": holding,
        "projection_status": "completed",
        "semantic_contract": "asset_activity_v1",
        "coupled_transaction_fact": "0",
        "automatic_cash_posting_created": "0",
        "basis_added_exact": row["basis_added"],
        "basis_consumed_exact": row["basis_consumed"],
        "realized_gross_gain_exact": row["realized_gain"],
        "fifo_authority": "semantic_realized_fifo_v2",
    }
    return {
        "event": dict(event), "event_result": safe,
        "cost_average": _fifo_v2_cost_average(positions[0]),
        "fifo_version": 2, "fifo_world_dimension": "portfolio_asset",
        "custody_dimension": "portfolio_account_asset", "rounding_performed": False,
    }


def read_desktop_product_asset_activity_view_v1(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    """Read the immutable active generation as a browser-safe newest-first Data view."""
    context = _context(context_value)
    binding = read_desktop_product_asset_activity_binding_v1(data_space_path, context)
    empty = {
        "product_asset_activity_read_model_version": CONTRACT_VERSION,
        "status": "absent",
        "ledger_schema_version": None,
        "portfolio_count": 0,
        "event_count": 0,
        "position_count": 0,
        "semantic_sources": [],
        "portfolios": [],
        "provider_access": False,
        "network_access": False,
        "canonical_write": False,
        "path_exposed": False,
        "internal_id_exposed": False,
    }
    if binding["status"] == "absent":
        return empty
    ledger = Path(binding["ledger_path"])
    connection = _read_connection(ledger)
    try:
        portfolio_rows = [
            dict(row) for row in connection.execute(
                "SELECT entity.portfolio_id,revision.display_name "
                "FROM portfolio_entity entity JOIN current_portfolio_revision revision USING(portfolio_id) "
                "WHERE revision.status='active' ORDER BY revision.display_name,entity.portfolio_id"
            )
        ]
        account_rows = [
            dict(row) for row in connection.execute(
                "SELECT entity.account_id,entity.portfolio_id,revision.display_name "
                "FROM account_entity entity JOIN current_account_revision revision USING(account_id) "
                "ORDER BY entity.account_id"
            )
        ]
        asset_rows = [
            dict(row) for row in connection.execute(
                "SELECT entity.asset_id,revision.display_name "
                "FROM asset_entity entity JOIN current_asset_revision revision USING(asset_id) "
                "ORDER BY entity.asset_id"
            )
        ]
    except sqlite3.Error:
        _abort("desktop_asset_activity_ledger_invalid")
    finally:
        connection.close()
    _, _, _, context_fp = semantic_context_values({
        "tenant_id": context.tenant_id,
        "user_id": context.user_id,
        "data_space_id": context.data_space_id,
    })
    account_labels = {
        semantic_public_ref("afr_", context_fp, row["account_id"]): row["display_name"]
        for row in account_rows
    }
    asset_labels = {
        semantic_public_ref("asf_", context_fp, row["asset_id"]): row["display_name"]
        for row in asset_rows
    }
    portfolios: list[dict[str, Any]] = []
    source_counts: dict[tuple[str, bool, str], list[int]] = {}
    total_events = 0
    total_positions = 0
    for portfolio in portfolio_rows:
        model = build_semantic_realized_fifo_read_model_v1(
            ledger,
            {
                "tenant_id": context.tenant_id,
                "user_id": context.user_id,
                "data_space_id": context.data_space_id,
            },
            portfolio["portfolio_id"],
            "9999-12-31T23:59:59Z",
            "9999-12-31T23:59:59Z",
        )
        for row in model["artifact"]["semantic_source_bindings"]:
            key = (
                row["semantic_contract"], row["coupled_transaction_fact"],
                row["automatic_cash_posting_state"],
            )
            counts = source_counts.setdefault(key, [0, 0])
            counts[0] += row["source_event_count"]
            counts[1] += row["projected_event_count"]
        events = []
        for row in reversed(model["tables"]["event-results.csv"]):
            events.append({
                "event_sequence": row["event_sequence"],
                "effective_at_utc": row["effective_at_utc"],
                "local_date": row["local_date"],
                "event_time_evidence": row["event_time_evidence"],
                "event_type": row["event_type"],
                "account_label": account_labels.get(row["account_ref"], "Account"),
                "related_account_label": None if row["related_account_ref"] is None else account_labels.get(row["related_account_ref"], "Account"),
                "asset_label": asset_labels.get(row["asset_ref"], "Asset"),
                "asset_type": row["asset_type"],
                "currency": row["currency"],
                "quantity_decimal": row["quantity_decimal"],
                "amount_decimal": row["amount_decimal"],
                "fee_decimal": row["fee_decimal"],
                "asset_fee_quantity_decimal": row["asset_fee_quantity_decimal"],
                "basis_added_decimal": row["basis_added_decimal"],
                "basis_consumed_decimal": row["basis_consumed_decimal"],
                "gross_proceeds_decimal": row["gross_proceeds_decimal"],
                "realized_gross_gain_decimal": row["realized_gross_gain_decimal"],
                "gross_income_decimal": row["gross_income_decimal"],
                "distribution_value_decimal": row["distribution_value_decimal"],
                "cash_balance_delta_decimal": row["cash_balance_delta_decimal"],
                "holding_effect": row["holding_effect"],
                "semantic_contract": row["semantic_contract"],
                "coupled_transaction_fact": row["coupled_transaction_fact"] == "1",
                "automatic_cash_posting_state": "unknown" if row["automatic_cash_posting_created"] is None else "none_created",
            })
        positions = []
        for ordinal, row in enumerate(model["tables"]["position-summary.csv"], 1):
            quantity = row["remaining_quantity_decimal"]
            basis = row["remaining_fifo_cost_decimal"]
            if row["asset_type"] == "cash":
                cost_average = None
            elif basis is None:
                cost_average = {
                    "cost_average_status": "basis_missing",
                    "remaining_quantity_decimal": quantity,
                    "remaining_fifo_basis_decimal": None,
                    "cost_average_decimal": None,
                    "cost_average_numerator_integer": None,
                    "cost_average_denominator_integer": None,
                }
            elif quantity == "0":
                cost_average = fifo_cost_average_evidence_v1([])
                cost_average.pop("cost_average_fingerprint", None)
            else:
                cost_average = fifo_cost_average_evidence_v1([{
                    "quantity_decimal": quantity, "basis_decimal": basis,
                    "basis_status": "completed",
                }])
                cost_average.pop("cost_average_fingerprint", None)
            positions.append({
                "position_ordinal": ordinal,
                "account_label": account_labels.get(row["account_ref"], "Account"),
                "asset_label": asset_labels.get(row["asset_ref"], "Asset"),
                "asset_type": row["asset_type"],
                "currency": row["currency"],
                "remaining_quantity_decimal": quantity,
                "remaining_fifo_basis_decimal": basis,
                "realized_gross_proceeds_decimal": row["realized_gross_proceeds_decimal"],
                "realized_fifo_cost_decimal": row["realized_fifo_cost_decimal"],
                "realized_gross_gain_decimal": row["realized_gross_gain_decimal"],
                "gross_income_decimal": row["gross_income_decimal"],
                "fee_total_decimal": row["fee_total_decimal"],
                "cash_coverage_state": "separate_not_read",
                "semantic_contract_coverage": row["semantic_contract_coverage"],
                "cost_average": cost_average,
            })
        total_events += len(events)
        total_positions += len(positions)
        portfolios.append({
            "portfolio_ordinal": len(portfolios) + 1,
            "portfolio_label": portfolio["display_name"],
            "events_newest_first": events,
            "positions": positions,
        })
    semantic_sources = [
        {
            "semantic_contract": key[0],
            "source_event_count": counts[0],
            "projected_event_count": counts[1],
            "coupled_transaction_fact": key[1],
            "automatic_cash_posting_state": key[2],
        }
        for key, counts in sorted(source_counts.items())
    ]
    return {
        **empty,
        "status": "available",
        "ledger_schema_version": 401,
        "portfolio_count": len(portfolios),
        "event_count": total_events,
        "position_count": total_positions,
        "semantic_sources": semantic_sources,
        "portfolios": portfolios,
    }


def _native_matching_preview(
    binding: Mapping[str, Any],
    matched: Mapping[str, Any],
    command_fingerprint: str,
    event: Mapping[str, Any],
    context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    result = {
        "native_asset_activity_preview_version": CONTRACT_VERSION,
        "status": "already_committed",
        "schema_version": 401,
        "command_ref": _public_native_ref("nac_", context, command_fingerprint),
        "event_type": event["event_type"],
        "event_time_evidence": event["event_time_evidence"],
        "local_date": event["local_date"],
        "local_time": event["local_time"],
        "time_zone": event["time_zone"],
        "effective_at_utc": event["effective_at_utc"],
        "event_count": matched["event_count"],
        "existing_asset_activity_event_count": binding["asset_activity_event_count"],
        "semantic_contracts": list(binding["semantic_contracts"]),
        "authority_contract": "schema201_derived_base_plus_asset_activity_v1",
        "confirmation_required": False,
        "one_attempt_only": True,
        "canonical_write": False,
        "schema201_canonical_write": False,
        "automatic_cash_posting_created": False,
        "provider_access": False,
        "network_access": False,
        "private_data_access": False,
        "path_exposed": False,
        "internal_id_exposed": False,
    }
    result["command_fingerprint"] = command_fingerprint
    result["active_generation_ref"] = binding["generation_ref"]
    result["product_preview_fingerprint"] = _sha(result)
    return result


def preview_desktop_native_asset_activity_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    portfolio_id: str,
    events_value: Any,
    *,
    fifo_order_evidence_value: Any = None,
) -> dict[str, Any]:
    context = _context(context_value)
    events = _native_events(events_value)
    data_space = _owner_directory(data_space_path)
    _assert_event_refs_not_corrected(data_space, context, events)
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    active_ledger = None if binding["status"] == "absent" else Path(binding["ledger_path"])
    evidence_rows = _native_fifo_order_evidence_rows(fifo_order_evidence_value, events[0], active_ledger)
    fifo_order_evidence = None if not evidence_rows else (evidence_rows[0] if isinstance(fifo_order_evidence_value, Mapping) else evidence_rows)
    command_fingerprint = _native_command_fingerprint(
        context, portfolio_id, events, fifo_order_evidence
    )
    matched = _matching_native_command(
        active_ledger, portfolio_id, events, fifo_order_evidence
    )
    if matched is not None:
        return _native_matching_preview(binding, matched, command_fingerprint, events[0], context)
    with tempfile.TemporaryDirectory(prefix=".native-asset-activity-preview-", dir=data_space) as temporary:
        temporary_path = Path(temporary)
        os.chmod(temporary_path, 0o700)
        target = temporary_path / LEDGER_NAME
        materialized = materialize_desktop_product_semantic_ledger_v1(
            canonical_path, active_ledger, target, context
        )
        try:
            preview = preview_schema400_asset_activity_v1(
                target, _compat_context(context), portfolio_id, events
            )
        except (Schema400AssetActivityCompatV1Error, AssetActivityV1Error):
            _abort("desktop_asset_activity_input_invalid")
        fifo_evidence = _native_fifo_preview(
            target, context, portfolio_id, events[0], preview["event_effects"][0],
            fifo_order_evidence, data_space_path,
        )
        return _native_preview_payload(
            preview, materialized, binding, command_fingerprint, fifo_evidence, context,
            fifo_order_evidence,
        )


def _generation_candidate_for_native_command(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
    canonical_fingerprint: str,
    command_fingerprint: str,
    portfolio_id: str,
    events: Sequence[Mapping[str, Any]],
    fifo_order_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for candidate in _generation_candidates(
        area, context, canonical_fingerprint, command_fingerprint
    ):
        manifest = candidate["manifest"]
        if manifest.get("plan_fingerprint") != command_fingerprint:
            continue
        matched = _matching_native_command(
            Path(candidate["ledger_path"]), portfolio_id, events, fifo_order_evidence
        )
        if matched is not None:
            candidates.append({**candidate, "matched": matched})
    if len(candidates) > 1:
        _abort("desktop_asset_activity_generation_conflict")
    return None if not candidates else candidates[0]


def _native_result(
    status: str,
    binding: Mapping[str, Any],
    event_count: int,
    command_fingerprint: str,
    context: DesktopProductAssetActivityContextV1,
    *,
    canonical_write: bool,
) -> DesktopNativeAssetActivityResultV1:
    return DesktopNativeAssetActivityResultV1(
        status=status,
        generation_ref=binding["generation_ref"],
        event_count=event_count,
        total_asset_activity_event_count=binding["asset_activity_event_count"],
        schema_version=401,
        canonical_write=canonical_write,
        cash_posting_count=0,
        semantic_contracts=tuple(binding["semantic_contracts"]),
        command_ref=_public_native_ref("nac_", context, command_fingerprint),
    )


def apply_desktop_native_asset_activity_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    portfolio_id: str,
    events_value: Any,
    expected_preview_fingerprint: str,
    committed_at_utc: str,
    *,
    fifo_order_evidence_value: Any = None,
    failpoint: Any = None,
) -> DesktopNativeAssetActivityResultV1:
    context = _context(context_value)
    events = _native_events(events_value)
    committed = _utc(committed_at_utc)
    if (
        not isinstance(expected_preview_fingerprint, str)
        or SHA.fullmatch(expected_preview_fingerprint) is None
        or not (failpoint is None or callable(failpoint) or failpoint in ALLOWED_FAILPOINTS)
    ):
        _abort("desktop_asset_activity_input_invalid")
    data_space = _owner_directory(data_space_path)
    area = _owner_directory(data_space / PRODUCT_AREA, create=True)
    # Group evidence is validated against the active ledger while holding the writer lock.

    with _ProductWriterLockV1(area):
        _assert_event_refs_not_corrected(data_space, context, events)
        with _CanonicalReadBarrierV1(data_space):
            canonical = _canonical_snapshot(canonical_path, context)
            _failpoint(failpoint, "after_initial_canonical_snapshot")
        expected_canonical_fingerprint = canonical["source_fingerprint"]
        binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
        active_ledger = None if binding["status"] == "absent" else Path(binding["ledger_path"])
        evidence_rows = _native_fifo_order_evidence_rows(fifo_order_evidence_value, events[0], active_ledger)
        fifo_order_evidence = None if not evidence_rows else (evidence_rows[0] if isinstance(fifo_order_evidence_value, Mapping) else evidence_rows)
        command_fingerprint = _native_command_fingerprint(context, portfolio_id, events, fifo_order_evidence)
        matched = _matching_native_command(
            active_ledger, portfolio_id, events, fifo_order_evidence
        )
        if matched is not None:
            if binding.get("canonical_fingerprint") != expected_canonical_fingerprint:
                _abort("desktop_asset_activity_canonical_changed")
            return _native_result(
                "already_committed", binding, matched["event_count"], command_fingerprint,
                context, canonical_write=False,
            )

        generations = _owner_directory(area / "generations", create=True)
        _remove_staging_generations(generations)
        candidate = _generation_candidate_for_native_command(
            area, context, expected_canonical_fingerprint, command_fingerprint,
            portfolio_id, events, fifo_order_evidence,
        )
        if candidate is not None:
            _validate_native_attempt(area, context, command_fingerprint, expected_preview_fingerprint)
            with _CanonicalReadBarrierV1(data_space):
                _failpoint(failpoint, "before_recovery_canonical_recheck")
                if _sha_file(canonical["path"]) != expected_canonical_fingerprint:
                    _abort("desktop_asset_activity_canonical_changed")
                recovered = _activate_generation_candidate(area, data_space, context, candidate)
            return _native_result(
                "recovered_committed", recovered, candidate["matched"]["event_count"],
                command_fingerprint, context, canonical_write=False,
            )

        staging = generations / f".staging-{secrets.token_hex(16)}"
        try:
            os.mkdir(staging, 0o700)
            os.chmod(staging, 0o700)
        except OSError:
            _abort("desktop_asset_activity_storage_invalid")
        generation_published = False
        try:
            target = staging / LEDGER_NAME
            materialized = materialize_desktop_product_semantic_ledger_v1(
                canonical["path"], active_ledger, target, context
            )
            if materialized["canonical_fingerprint"] != expected_canonical_fingerprint:
                _abort("desktop_asset_activity_canonical_changed")
            try:
                preview = preview_schema400_asset_activity_v1(
                    target, _compat_context(context), portfolio_id, events
                )
            except (Schema400AssetActivityCompatV1Error, AssetActivityV1Error):
                _abort("desktop_asset_activity_input_invalid")
            if _native_expected_preview_fingerprint(
                preview["preview_fingerprint"], command_fingerprint, fifo_order_evidence
            ) != expected_preview_fingerprint:
                _abort("desktop_asset_activity_plan_stale")
            _native_fifo_preview(
                target, context, portfolio_id, events[0], preview["event_effects"][0],
                fifo_order_evidence, data_space_path,
            )
            _persist_native_attempt(
                area, context, command_fingerprint, expected_preview_fingerprint, committed
            )
            _failpoint(failpoint, "after_native_attempt")
            challenge = "sac_" + _sha({
                "contract_version": "desktop_native_asset_activity_confirmation_v1",
                "context_fingerprint": _context_fingerprint(context),
                "preview_fingerprint": preview["preview_fingerprint"],
                "committed_at_utc": committed,
            })[:32]
            confirmation = build_schema400_asset_activity_confirmation_v1(
                preview, _compat_context(context), challenge,
                committed, committed, _offset(committed, 300),
            )
            authorizer = OneUseSchema400AssetActivityAuthorizerV1()
            authorizer.register(confirmation)
            try:
                result = apply_schema400_asset_activity_v1(
                    target, _compat_context(context), portfolio_id, events,
                    confirmation, authorizer, committed,
                )
            except Schema400AssetActivityCompatV1Error:
                _abort("desktop_asset_activity_input_invalid")
            if fifo_order_evidence is not None:
                evidence_writer = sqlite3.connect(target)
                try:
                    evidence_writer.execute("PRAGMA foreign_keys=ON")
                    evidence_writer.execute("BEGIN IMMEDIATE")
                    _insert_native_fifo_order_evidence(
                        evidence_writer, fifo_order_evidence
                    )
                    evidence_writer.execute("COMMIT")
                except DesktopProductAssetActivityV1Error:
                    if evidence_writer.in_transaction:
                        evidence_writer.execute("ROLLBACK")
                    raise
                except sqlite3.Error:
                    if evidence_writer.in_transaction:
                        evidence_writer.execute("ROLLBACK")
                    _abort("desktop_asset_activity_ledger_invalid")
                finally:
                    evidence_writer.close()
            connection = _read_connection(target)
            try:
                activity = _activity_rows(connection)
                semantic_counts = {
                    row[0]: row[1]
                    for row in connection.execute(
                        "SELECT semantic_contract,count(*) FROM compatible_ledger_event GROUP BY semantic_contract"
                    )
                }
            finally:
                connection.close()
            if set(semantic_counts) - {
                "portfolio_ledger_v1_transaction_fact", "asset_activity_v1"
            } or semantic_counts.get("asset_activity_v1", 0) != len(activity["asset_activity_events"]):
                _abort("desktop_asset_activity_ledger_invalid")
            ledger_fingerprint = _sha_file(target)
            generation_ref = "gen_" + _sha({
                "canonical_fingerprint": expected_canonical_fingerprint,
                "activity_set_fingerprint": activity["activity_set_fingerprint"],
                "command_id": result.command_id,
                "plan_fingerprint": command_fingerprint,
            })[:32]
            manifest = {
                "contract_version": CONTRACT_VERSION,
                "authority_contract": "schema201_derived_base_plus_asset_activity_v1",
                "context_fingerprint": _context_fingerprint(context),
                "generation_ref": generation_ref,
                "canonical_schema_version": materialized["canonical_schema_version"],
                "canonical_fingerprint": expected_canonical_fingerprint,
                "prior_activity_set_fingerprint": materialized["activity_set_fingerprint"],
                "activity_set_fingerprint": activity["activity_set_fingerprint"],
                "ledger_schema_version": 401,
                "ledger_fingerprint": ledger_fingerprint,
                "plan_fingerprint": command_fingerprint,
                "command_id": result.command_id,
                "new_event_count": result.event_count,
                "total_asset_activity_event_count": len(activity["asset_activity_events"]),
                "committed_at_utc": committed,
                "semantic_contracts": [
                    "portfolio_ledger_v1_transaction_fact", "asset_activity_v1"
                ],
                "boundaries": {
                    "schema201_catalog_authority": "derived_read_only",
                    "schema201_transaction_authority": "derived_read_only",
                    "asset_activity_authority": "data_app_append_only",
                    "automatic_cash_posting_count": 0,
                    "provider_access": False,
                    "network_access": False,
                },
            }
            _write_new_file(staging / MANIFEST_NAME, _canonical(manifest) + b"\n")
            _write_new_file(staging / SUCCESS_NAME, b"completed\n")
            _failpoint(failpoint, "after_generation_complete")
            final = generations / generation_ref
            if final.exists() or final.is_symlink():
                _abort("desktop_asset_activity_generation_conflict")
            try:
                settle_new_directory_v1(staging)  # #568: auch die gocryptfs.diriv neuer Ordner festschreiben
                os.rename(staging, final)
                descriptor = os.open(generations, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            except OSError:
                _abort("desktop_asset_activity_publication_failed")
            generation_published = True
            _failpoint(failpoint, "after_generation_publish")
            with _CanonicalReadBarrierV1(data_space):
                _failpoint(failpoint, "before_final_canonical_recheck")
                if _sha_file(canonical["path"]) != expected_canonical_fingerprint:
                    _abort("desktop_asset_activity_canonical_changed")
                _failpoint(failpoint, "before_active_replace")
                _atomic_json_replace(area / ACTIVE_NAME, {
                    "contract_version": CONTRACT_VERSION,
                    "generation_ref": generation_ref,
                    "ledger_fingerprint": ledger_fingerprint,
                    "manifest_fingerprint": _sha_file(final / MANIFEST_NAME),
                })
            _failpoint(failpoint, "after_active_replace")
            verified = read_desktop_product_asset_activity_binding_v1(data_space, context)
            if (
                verified["generation_ref"] != generation_ref
                or verified["activity_set_fingerprint"] != activity["activity_set_fingerprint"]
            ):
                _abort("desktop_asset_activity_publication_failed")
            return _native_result(
                result.status, verified, result.event_count, command_fingerprint,
                context, canonical_write=True,
            )
        finally:
            if not generation_published and staging.exists() and not staging.is_symlink():
                shutil.rmtree(staging, ignore_errors=True)


def apply_desktop_asset_activity_republication_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    committed_at_utc: str,
    *,
    failpoint: Any = None,
) -> dict[str, Any]:
    """Den Buchungsbestand gegen die heutigen Stammdaten neu veroeffentlichen.

    Jede Generation ist aus den Stammdaten abgeleitet und traegt deren
    Fingerabdruck vom Zeitpunkt ihrer Entstehung. Schreibt danach etwas die
    Stammdaten - eine Bewertungsart, ein neues Asset, eine Kurszuordnung -,
    bleibt die Generation zurueck, bis die naechste Buchung sie neu aufbaut.
    Bis dahin wies das Run Center jeden Plan ab: Es reichte
    eine Minute zwischen letzter Buchung und geaenderter Bewertungsart, und der
    Abschluss war ohne weitere Buchung nicht mehr zu rechnen (11.10.2026).

    Hier entsteht dieselbe Generation ohne Buchung: Stammdaten neu abgeleitet,
    die Buchungen unveraendert uebernommen. Weicht die Menge der Buchungen
    danach von der bisherigen ab, wird nichts veroeffentlicht.
    """
    context = _context(context_value)
    committed = _utc(committed_at_utc)
    if not (failpoint is None or callable(failpoint) or failpoint in ALLOWED_FAILPOINTS):
        _abort("desktop_asset_activity_input_invalid")
    data_space = _owner_directory(data_space_path)

    def outcome(status: str, binding: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": status,
            "generation_ref": binding["generation_ref"],
            "asset_activity_event_count": binding["asset_activity_event_count"],
            "new_event_count": 0,
            "canonical_write": False,
        }

    if not (data_space / PRODUCT_AREA).exists():
        return outcome("absent", read_desktop_product_asset_activity_binding_v1(data_space, context))
    area = _owner_directory(data_space / PRODUCT_AREA)
    with _ProductWriterLockV1(area):
        with _CanonicalReadBarrierV1(data_space):
            canonical = _canonical_snapshot(canonical_path, context)
        expected_canonical_fingerprint = canonical["source_fingerprint"]
        binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
        if binding["status"] == "absent":
            return outcome("absent", binding)
        if binding["canonical_fingerprint"] == expected_canonical_fingerprint:
            return outcome("already_current", binding)
        plan_fingerprint = _sha({
            "contract_version": "desktop_asset_activity_republication_v1",
            "context_fingerprint": _context_fingerprint(context),
            "prior_generation_ref": binding["generation_ref"],
            "canonical_fingerprint": expected_canonical_fingerprint,
            "activity_set_fingerprint": binding["activity_set_fingerprint"],
        })
        generation_ref = "gen_" + _sha({
            "prior_generation_ref": binding["generation_ref"],
            "plan_fingerprint": plan_fingerprint,
            "canonical_fingerprint": expected_canonical_fingerprint,
            "activity_set_fingerprint": binding["activity_set_fingerprint"],
        })[:32]
        generations = _owner_directory(area / "generations")
        _remove_staging_generations(generations)
        final = generations / generation_ref
        if final.is_symlink():
            _abort("desktop_asset_activity_generation_conflict")
        staging = generations / f".staging-{secrets.token_hex(16)}"
        generation_published = final.exists()
        try:
            # Ein frueherer Anlauf kann die Generation schon abgelegt haben, ohne
            # sie zu aktivieren. Sie traegt denselben Namen, weil der Name aus
            # Vorgaenger, Stammdaten und Buchungsmenge folgt; der Leser prueft
            # sie nach der Aktivierung vollstaendig.
            if not generation_published:
                try:
                    os.mkdir(staging, 0o700)
                    os.chmod(staging, 0o700)
                except OSError:
                    _abort("desktop_asset_activity_storage_invalid")
                target = staging / LEDGER_NAME
                materialized = materialize_desktop_product_semantic_ledger_v1(
                    canonical["path"], Path(binding["ledger_path"]), target, context
                )
                if materialized["canonical_fingerprint"] != expected_canonical_fingerprint:
                    _abort("desktop_asset_activity_canonical_changed")
                connection = _read_connection(target)
                try:
                    activity = _activity_rows(connection)
                    semantic_counts = {
                        row[0]: row[1]
                        for row in connection.execute(
                            "SELECT semantic_contract,count(*) FROM compatible_ledger_event GROUP BY semantic_contract"
                        )
                    }
                finally:
                    connection.close()
                if (
                    set(semantic_counts) - {"portfolio_ledger_v1_transaction_fact", "asset_activity_v1"}
                    or semantic_counts.get("asset_activity_v1", 0) != len(activity["asset_activity_events"])
                    or activity["activity_set_fingerprint"] != binding["activity_set_fingerprint"]
                    or len(activity["asset_activity_events"]) != binding["asset_activity_event_count"]
                ):
                    _abort("desktop_asset_activity_ledger_invalid")
                manifest = {
                    "contract_version": CONTRACT_VERSION,
                    "authority_contract": "schema201_derived_base_plus_asset_activity_v1",
                    "context_fingerprint": _context_fingerprint(context),
                    "generation_ref": generation_ref,
                    "canonical_schema_version": materialized["canonical_schema_version"],
                    "canonical_fingerprint": expected_canonical_fingerprint,
                    "prior_activity_set_fingerprint": binding["activity_set_fingerprint"],
                    "activity_set_fingerprint": activity["activity_set_fingerprint"],
                    "ledger_schema_version": 401,
                    "ledger_fingerprint": _sha_file(target),
                    "plan_fingerprint": plan_fingerprint,
                    "command_id": "cmd_republication_" + plan_fingerprint[:48],
                    "new_event_count": 0,
                    "total_asset_activity_event_count": len(activity["asset_activity_events"]),
                    "committed_at_utc": committed,
                    "semantic_contracts": [
                        "portfolio_ledger_v1_transaction_fact", "asset_activity_v1"
                    ],
                    "boundaries": {
                        "schema201_catalog_authority": "derived_read_only",
                        "schema201_transaction_authority": "derived_read_only",
                        "asset_activity_authority": "unchanged_generation_republication",
                        "automatic_cash_posting_count": 0,
                        "provider_access": False,
                        "network_access": False,
                    },
                }
                _write_new_file(staging / MANIFEST_NAME, _canonical(manifest) + b"\n")
                _write_new_file(staging / SUCCESS_NAME, b"completed\n")
                _failpoint(failpoint, "after_generation_complete")
                try:
                    settle_new_directory_v1(staging)  # #568: auch die gocryptfs.diriv neuer Ordner festschreiben
                    os.rename(staging, final)
                    _fsync_directory(generations)
                except OSError:
                    _abort("desktop_asset_activity_publication_failed")
                generation_published = True
                _failpoint(failpoint, "after_generation_publish")
            with _CanonicalReadBarrierV1(data_space):
                if _sha_file(canonical["path"]) != expected_canonical_fingerprint:
                    _abort("desktop_asset_activity_canonical_changed")
                _failpoint(failpoint, "before_active_replace")
                _atomic_json_replace(area / ACTIVE_NAME, {
                    "contract_version": CONTRACT_VERSION,
                    "generation_ref": generation_ref,
                    "ledger_fingerprint": _sha_file(
                        _owner_file(final / LEDGER_NAME, "desktop_asset_activity_generation_invalid")
                    ),
                    "manifest_fingerprint": _sha_file(
                        _owner_file(final / MANIFEST_NAME, "desktop_asset_activity_generation_invalid")
                    ),
                })
            _failpoint(failpoint, "after_active_replace")
            verified = read_desktop_product_asset_activity_binding_v1(data_space, context)
            if (
                verified["generation_ref"] != generation_ref
                or verified["canonical_fingerprint"] != expected_canonical_fingerprint
                or verified["activity_set_fingerprint"] != binding["activity_set_fingerprint"]
                or verified["asset_activity_event_count"] != binding["asset_activity_event_count"]
            ):
                _abort("desktop_asset_activity_publication_failed")
            return outcome("republished", verified)
        finally:
            if staging.exists() and not staging.is_symlink():
                shutil.rmtree(staging, ignore_errors=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


GENERATION_BASE_NAMES = frozenset({LEDGER_NAME, MANIFEST_NAME, SUCCESS_NAME})


def _generation_retention_plan(area: Path, context: DesktopProductAssetActivityContextV1) -> dict[str, Any]:
    """Welche Generationen tragen etwas, das nur in ihnen steht.

    Jede Buchung veroeffentlicht eine vollstaendige Kopie des Ledgers. Die
    aktive traegt den heutigen Stand; eine Generation mit Quittung wird von
    _corrected_event_refs und der Korrekturhistorie gelesen; und die in einer
    Quittung als 'prior_generation_ref' benannte Generation ist die einzige
    Stelle, an der die wegkorrigierte Buchung noch im Wortlaut steht - genau
    das meint 'predecessor_preserved'.

    Alle uebrigen sind Zwischenstaende einer append-only Folge: Ihr Inhalt
    steht vollstaendig in der aktiven Generation. Die Kette wird nirgends
    rueckwaerts gelaufen; 'prior_generation_ref' und
    'prior_activity_set_fingerprint' werden ausschliesslich gegen die aktive
    Bindung geprueft (nachgesehen 26.09.2026, #283).

    Fail-closed: Faellt eine Generation oder ein Manifest aus der erwarteten
    Gestalt, entsteht kein Plan.
    """
    generations = _owner_directory(area / "generations")
    active_path = _owner_file(area / ACTIVE_NAME, "desktop_asset_activity_active_invalid")
    try:
        active = json.loads(active_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _abort("desktop_asset_activity_active_invalid")
    if not isinstance(active, dict) or GENERATION.fullmatch(str(active.get("generation_ref"))) is None:
        _abort("desktop_asset_activity_active_invalid")
    present: dict[str, Path] = {}
    for child in sorted(generations.iterdir()):
        if child.name.startswith(".staging-"):
            continue
        if not child.is_dir() or child.is_symlink() or GENERATION.fullmatch(child.name) is None:
            _abort("desktop_asset_activity_generation_invalid")
        present[child.name] = _owner_directory(child)
    if active["generation_ref"] not in present:
        _abort("desktop_asset_activity_active_invalid")
    keep = {active["generation_ref"]}
    receipts = 0
    priors: set[str] = set()
    for name, path in present.items():
        extra = sorted({entry.name for entry in path.iterdir()} - GENERATION_BASE_NAMES)
        if not extra:
            continue
        receipts += 1
        keep.add(name)
        for entry in extra:
            try:
                value = json.loads((path / entry).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                _abort("desktop_asset_activity_generation_invalid")
            prior = value.get("prior_generation_ref") if isinstance(value, dict) else None
            if isinstance(prior, str) and GENERATION.fullmatch(prior) is not None:
                priors.add(prior)
    # Ein benannter Vorgaenger, den es nicht mehr gibt, waere ein gebrochenes
    # Versprechen. Dann lieber kein Plan als ein weiterer Schnitt.
    if priors - set(present):
        _abort("desktop_asset_activity_generation_invalid")
    keep |= priors
    removed = sorted(set(present) - keep)

    def weigh(names: Iterable[str]) -> int:
        return sum(entry.stat().st_size for name in names for entry in present[name].iterdir() if entry.is_file())

    plan = {
        "contract_version": "desktop_asset_activity_generation_retention_v1",
        "context_fingerprint": _context_fingerprint(context),
        "generation_count": len(present),
        "active_generation_ref": active["generation_ref"],
        "receipt_generation_count": receipts,
        "preserved_predecessor_count": len(priors),
        "kept_generation_count": len(keep),
        "removed_generation_count": len(removed),
        "kept_byte_count": weigh(sorted(keep)),
        "removed_byte_count": weigh(removed),
        "removed_generations": removed,
    }
    plan["plan_fingerprint"] = _sha({k: v for k, v in plan.items() if k != "removed_generations"} | {"removed_generations": removed})
    return plan


def read_desktop_asset_activity_generation_retention_plan_v1(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    """Nur lesen: was bliebe, was ginge. Keine Aenderung, kein Anlegen."""
    try:
        context = _context(context_value)
        area = Path(data_space_path) / PRODUCT_AREA
        if not area.exists():
            return {"contract_version": "desktop_asset_activity_generation_retention_v1", "status": "absent",
                    "generation_count": 0, "removed_generation_count": 0, "removed_byte_count": 0}
        plan = _generation_retention_plan(_owner_directory(area), context)
        return {**{k: v for k, v in plan.items() if k != "removed_generations"}, "status": "available"}
    except DesktopProductAssetActivityV1Error:
        raise
    except Exception:
        _abort("desktop_asset_activity_boundary_failed")


def apply_desktop_asset_activity_generation_retention_v1(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    plan_fingerprint: str,
    confirmed: bool,
    applied_at_utc: str,
) -> dict[str, Any]:
    """Genau den bestaetigten Plan entfernen - unter der Schreibsperre neu erhoben."""
    try:
        context = _context(context_value)
        if confirmed is not True or not isinstance(plan_fingerprint, str) or SHA.fullmatch(plan_fingerprint) is None:
            _abort("desktop_asset_activity_input_invalid")
        _utc(applied_at_utc)
        area = _owner_directory(Path(data_space_path) / PRODUCT_AREA)
        with _ProductWriterLockV1(area):
            plan = _generation_retention_plan(area, context)
            if plan["plan_fingerprint"] != plan_fingerprint:
                _abort("desktop_asset_activity_plan_stale")
            generations = _owner_directory(area / "generations")
            for name in plan["removed_generations"]:
                path = _owner_directory(generations / name)
                for entry in sorted(path.iterdir()):
                    if entry.is_dir() or entry.is_symlink():
                        _abort("desktop_asset_activity_generation_invalid")
                    os.unlink(entry)
                os.rmdir(path)
            _fsync_directory(generations)
            receipt = {
                "contract_version": "desktop_asset_activity_generation_retention_v1",
                "context_fingerprint": _context_fingerprint(context),
                "applied_at_utc": applied_at_utc,
                "active_generation_ref": plan["active_generation_ref"],
                "kept_generation_count": plan["kept_generation_count"],
                "receipt_generation_count": plan["receipt_generation_count"],
                "preserved_predecessor_count": plan["preserved_predecessor_count"],
                "removed_generation_count": plan["removed_generation_count"],
                "removed_byte_count": plan["removed_byte_count"],
                "plan_fingerprint": plan_fingerprint,
            }
            receipt["receipt_fingerprint"] = _sha(receipt)
            retention = _owner_directory(area / "retention-receipts", create=True)
            _write_new_file(retention / (applied_at_utc.replace(":", "") + ".json"), _canonical(receipt) + b"\n")
            _fsync_directory(retention)
        return receipt
    except DesktopProductAssetActivityV1Error:
        raise
    except Exception:
        _abort("desktop_asset_activity_boundary_failed")


__all__ = [
    "DesktopNativeAssetActivityResultV1",
    "DesktopProductAssetActivityContextV1",
    "DesktopProductAssetActivityResultV1",
    "DesktopProductAssetActivityV1Error",
    "apply_desktop_asset_activity_generation_retention_v1",
    "apply_desktop_native_asset_activity_v1",
    "apply_desktop_product_per_asset_cutover_v1",
    "desktop_product_asset_activity_v1_error_codes",
    "materialize_desktop_product_semantic_ledger_v1",
    "preview_desktop_native_asset_activity_v1",
    "preview_desktop_product_per_asset_cutover_v1",
    "resolve_desktop_product_per_asset_scope_v1",
    "read_desktop_asset_activity_generation_retention_plan_v1",
    "read_desktop_product_asset_activity_binding_v1",
    "read_desktop_product_asset_activity_view_v1",
    "read_desktop_product_per_asset_catalog_v1",
]
