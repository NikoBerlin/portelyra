#!/usr/bin/env python3
"""Persistent, context-bound Realized FIFO/GuV materialization v1."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts" / "realized-materialization" / "v1" / "schema.sql"
TEMPLATE_ROOT = ROOT / "contracts" / "realized-fifo" / "v1" / "templates"
STORE_VERSION = 1800
TABLE_ORDER = (
    "event-results.csv", "lot-movements.csv", "remaining-lots.csv",
    "position-history.csv", "position-summary.csv", "currency-summary.csv",
)
REASONS = frozenset({
    "initial_full_rebuild", "append_only", "backdated_event", "correction",
    "void", "transfer_chain", "algorithm_upgrade", "recovery_mismatch",
})
FAILPOINTS = frozenset({"after_artifact", "after_rows", "after_checkpoints"})
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_REF = re.compile(r"^[a-z][a-z0-9]{2}_[a-f0-9]{24,32}$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_.-]{2,79}$")


class RealizedMaterializationBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class RealizedContext:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str


@dataclass(frozen=True)
class RealizedJob:
    job_ref: str
    portfolio_ref: str
    desired_input_fingerprint: str
    invalidated_from_utc: str
    invalidation_reason: str
    requested_algorithm_version: str


@dataclass(frozen=True)
class RealizedArtifact:
    artifact_ref: str
    portfolio_ref: str
    algorithm_version: str
    input_fingerprint: str
    evidence_artifact_fingerprint: str
    evidence_cutoff_at_utc: str
    rebuild_mode: str
    base_artifact_ref: str | None
    row_set_fingerprint: str


def _abort(code: str) -> None:
    raise RealizedMaterializationBlocked(code)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _sha(value: bytes | str | Any) -> str:
    if isinstance(value, bytes): payload = value
    elif isinstance(value, str): payload = value.encode("utf-8")
    else: payload = _json(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _normalize_context(context: RealizedContext | Mapping[str, str]) -> RealizedContext:
    if isinstance(context, Mapping):
        try:
            context = RealizedContext(*(context[key] for key in ("tenant_id", "user_id", "data_space_id", "actor_id")))
        except (KeyError, TypeError) as exc:
            raise RealizedMaterializationBlocked("realized_materialization_context_invalid") from exc
    if not isinstance(context, RealizedContext): _abort("realized_materialization_context_invalid")
    for index, value in enumerate((context.tenant_id, context.user_id, context.data_space_id, context.actor_id)):
        if not isinstance(value, str) or not 3 <= len(value) <= (80 if index == 3 else 64) or re.search(r"[\x00-\x1f\x7f]", value):
            _abort("realized_materialization_context_invalid")
    return context


def realized_store_context_fingerprint_v1(context: RealizedContext | Mapping[str, str]) -> str:
    context = _normalize_context(context)
    return _sha({
        "contract_version": "realized_materialization_v1",
        "tenant_id": context.tenant_id, "user_id": context.user_id,
        "data_space_id": context.data_space_id,
    })


def fifo_context_fingerprint_v1(context: RealizedContext | Mapping[str, str]) -> str:
    context = _normalize_context(context)
    return _sha("|".join(("realized-fifo-context-v1", context.tenant_id, context.user_id, context.data_space_id)))


def _utc(value: Any) -> str:
    if not isinstance(value, str) or not _UTC.fullmatch(value): _abort("realized_materialization_input_invalid")
    return value


def _public_ref(value: Any, prefix: str | None = None) -> str:
    if not isinstance(value, str) or not _REF.fullmatch(value) or (prefix and not value.startswith(prefix)):
        _abort("realized_materialization_input_invalid")
    return value


def _fingerprint(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        _abort("realized_materialization_input_invalid")
    return value


def _algorithm(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{2,39}", value):
        _abort("realized_materialization_input_invalid")
    return value


def _regular_store(path: str | Path, *, new: bool = False) -> Path:
    target = Path(path)
    if new:
        if target.exists() or target.is_symlink(): _abort("realized_materialization_store_exists")
        try: parent = target.parent.resolve(strict=True)
        except OSError as exc: raise RealizedMaterializationBlocked("realized_materialization_store_invalid") from exc
        if target.parent.is_symlink(): _abort("realized_materialization_store_invalid")
        return parent / target.name
    if target.is_symlink() or not target.is_file(): _abort("realized_materialization_store_invalid")
    try:
        resolved = target.resolve(strict=True)
        if not stat.S_ISREG(resolved.stat().st_mode): _abort("realized_materialization_store_invalid")
        return resolved
    except OSError as exc:
        raise RealizedMaterializationBlocked("realized_materialization_store_invalid") from exc


def _connect(path: str | Path, context: RealizedContext | Mapping[str, str], *, read_only: bool = False) -> sqlite3.Connection:
    context = _normalize_context(context)
    source = _regular_store(path)
    try:
        if read_only:
            connection = sqlite3.connect(f"{source.as_uri()}?mode=ro&immutable=1", uri=True)
            connection.execute("PRAGMA query_only=ON")
        else:
            connection = sqlite3.connect(source, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        binding = connection.execute("SELECT context_binding_fingerprint FROM realized_store_binding WHERE singleton_id=1").fetchone()
        if version != STORE_VERSION or binding is None or binding[0] != realized_store_context_fingerprint_v1(context):
            connection.close(); _abort("realized_materialization_context_mismatch")
        return connection
    except RealizedMaterializationBlocked:
        raise
    except sqlite3.Error as exc:
        raise RealizedMaterializationBlocked("realized_materialization_store_invalid") from exc


def bootstrap_realized_materialization_store_v1(path: str | Path, context: RealizedContext | Mapping[str, str], created_at_utc: str) -> Path:
    context = _normalize_context(context); created = _utc(created_at_utc); target = _regular_store(path, new=True)
    connection = sqlite3.connect(target)
    try:
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO realized_store_binding VALUES (1,1800,?,?)",
            (realized_store_context_fingerprint_v1(context), created),
        )
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok": _abort("realized_materialization_store_invalid")
    except Exception:
        connection.close()
        try: target.unlink()
        except OSError: pass
        raise
    finally:
        try: connection.close()
        except Exception: pass
    os.chmod(target, 0o600)
    return target


def _id(prefix: str, value: Any) -> str:
    return f"{prefix}_{_sha(value)[:32]}"


def _job_current(connection: sqlite3.Connection, job_ref: str) -> sqlite3.Row:
    row = connection.execute(
        "SELECT job.*,state.job_state_id,state.state_sequence,state.status FROM realized_rebuild_job job JOIN current_realized_rebuild_job_state state USING(job_id) WHERE job.job_ref=?",
        (job_ref,),
    ).fetchone()
    if row is None: _abort("realized_materialization_job_missing")
    return row


def schedule_realized_rebuild_v1(
    store_path: str | Path,
    context: RealizedContext | Mapping[str, str],
    *,
    request_ref: str,
    portfolio_ref: str,
    desired_input_fingerprint: str,
    invalidated_from_utc: str,
    invalidation_reason: str,
    affected_scope_refs: Sequence[str],
    requested_algorithm_version: str,
    created_at_utc: str,
) -> RealizedJob:
    context = _normalize_context(context)
    if not isinstance(request_ref, str) or not re.fullmatch(r"req_[a-f0-9]{24,32}", request_ref): _abort("realized_materialization_input_invalid")
    portfolio_ref = _public_ref(portfolio_ref, "pfr_"); desired = _fingerprint(desired_input_fingerprint)
    invalidated = _utc(invalidated_from_utc); created = _utc(created_at_utc); algorithm = _algorithm(requested_algorithm_version)
    if invalidation_reason not in REASONS or not isinstance(affected_scope_refs, Sequence) or isinstance(affected_scope_refs, (str, bytes)):
        _abort("realized_materialization_input_invalid")
    affected = sorted({_public_ref(value) for value in affected_scope_refs})
    payload = {
        "context": realized_store_context_fingerprint_v1(context), "request_ref": request_ref,
        "portfolio_ref": portfolio_ref, "desired_input_fingerprint": desired,
        "invalidated_from_utc": invalidated, "invalidation_reason": invalidation_reason,
        "affected_scope_refs": affected, "requested_algorithm_version": algorithm,
    }
    job_ref = _id("rjb", payload); job_id = _id("rji", job_ref); state_id = _id("rjs", [job_ref, 1])
    connection = _connect(store_path, context)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO realized_rebuild_job VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job_id, job_ref, request_ref, portfolio_ref, desired, invalidated, invalidation_reason, _json(affected), algorithm, created),
        )
        connection.execute(
            "INSERT INTO realized_rebuild_job_state VALUES (?,?,1,'pending',NULL,NULL,NULL,?)",
            (state_id, job_id, created),
        )
        connection.commit()
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        existing = connection.execute("SELECT job_ref FROM realized_rebuild_job WHERE request_ref=?", (request_ref,)).fetchone()
        if existing and existing[0] == job_ref: _abort("realized_materialization_request_replay")
        raise RealizedMaterializationBlocked("realized_materialization_write_failed") from exc
    finally:
        connection.close()
    return RealizedJob(job_ref, portfolio_ref, desired, invalidated, invalidation_reason, algorithm)


def ensure_realized_rebuild_job_v1(
    store_path: str | Path, context: RealizedContext | Mapping[str, str], *, request_ref: str,
    portfolio_ref: str, observed_input_fingerprint: str, observed_earliest_utc: str,
    requested_algorithm_version: str, created_at_utc: str,
) -> RealizedJob | None:
    """Restart reconciliation: schedule a durable job whenever latest completed input differs."""
    latest = read_latest_realized_materialization_v1(store_path, context, portfolio_ref)
    observed = _fingerprint(observed_input_fingerprint)
    if latest["artifact"] is not None and latest["artifact"]["input_fingerprint"] == observed and latest["artifact"]["algorithm_version"] == requested_algorithm_version:
        return None
    connection = _connect(store_path, context, read_only=True)
    try:
        existing = connection.execute(
            "SELECT job.job_ref FROM realized_rebuild_job job JOIN current_realized_rebuild_job_state state USING(job_id) WHERE job.portfolio_ref=? AND job.desired_input_fingerprint=? AND job.requested_algorithm_version=? AND state.status IN ('pending','running','failed') ORDER BY job.created_at_utc DESC LIMIT 1",
            (portfolio_ref, observed, requested_algorithm_version),
        ).fetchone()
        if existing:
            row = connection.execute("SELECT * FROM realized_rebuild_job WHERE job_ref=?", (existing[0],)).fetchone()
            return RealizedJob(row["job_ref"], row["portfolio_ref"], row["desired_input_fingerprint"], row["invalidated_from_utc"], row["invalidation_reason"], row["requested_algorithm_version"])
    finally:
        connection.close()
    return schedule_realized_rebuild_v1(
        store_path, context, request_ref=request_ref, portfolio_ref=portfolio_ref,
        desired_input_fingerprint=observed, invalidated_from_utc=observed_earliest_utc,
        invalidation_reason="recovery_mismatch", affected_scope_refs=[portfolio_ref],
        requested_algorithm_version=requested_algorithm_version, created_at_utc=created_at_utc,
    )


def _manifest_fingerprint(manifest: dict[str, Any]) -> str:
    body = dict(manifest); body.pop("artifact_fingerprint", None)
    if manifest.get("profile_id") == "realized_fifo_v1_1":
        return _sha(body)
    # jsonlite emits insertion order and a final LF for the shared v1 manifest.
    raw = json.dumps(body, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=False).encode("utf-8") + b"\n"
    return _sha(raw)


def _semantic_bindings(value: Any, fingerprint: Any) -> tuple[list[dict[str, Any]], str]:
    required = {"semantic_contract", "source_event_count", "projected_event_count", "coupled_transaction_fact", "automatic_cash_posting_state"}
    if not isinstance(value, list) or not value:
        _abort("realized_materialization_evidence_invalid")
    bindings: list[dict[str, Any]] = []
    contracts: set[str] = set()
    for row in value:
        if not isinstance(row, dict) or set(row) != required:
            _abort("realized_materialization_evidence_invalid")
        semantic = row["semantic_contract"]
        if semantic in contracts or semantic not in {"portfolio_ledger_v1_transaction_fact", "asset_activity_v1"}:
            _abort("realized_materialization_evidence_invalid")
        if not all(isinstance(row[key], int) and not isinstance(row[key], bool) and row[key] >= 0 for key in ("source_event_count", "projected_event_count")) or row["projected_event_count"] > row["source_event_count"]:
            _abort("realized_materialization_evidence_invalid")
        if semantic == "portfolio_ledger_v1_transaction_fact":
            valid = row["coupled_transaction_fact"] is True and row["automatic_cash_posting_state"] == "unknown"
        else:
            valid = row["coupled_transaction_fact"] is False and row["automatic_cash_posting_state"] == "none_created"
        if not valid:
            _abort("realized_materialization_evidence_invalid")
        contracts.add(semantic); bindings.append(dict(row))
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint) or fingerprint != _sha(bindings):
        _abort("realized_materialization_evidence_invalid")
    return bindings, fingerprint


def _read_evidence(evidence_path: str | Path, context: RealizedContext | Mapping[str, str]) -> tuple[dict[str, Any], dict[str, list[dict[str, str]]], str]:
    root = Path(evidence_path)
    if root.is_symlink() or not root.is_dir(): _abort("realized_materialization_evidence_invalid")
    manifest_path = root / "evidence-manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file(): _abort("realized_materialization_evidence_invalid")
    try: manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc: raise RealizedMaterializationBlocked("realized_materialization_evidence_invalid") from exc
    required = {
        "calculation_evidence_version", "profile_id", "status", "algorithm_version", "portfolio_ref",
        "context_binding_fingerprint", "input_fingerprint", "evidence_cutoff_at_utc", "files",
        "reconciliation", "boundaries", "artifact_fingerprint",
    }
    semantic = manifest.get("profile_id") == "realized_fifo_v1_1"
    if semantic: required |= {"semantic_source_bindings", "semantic_binding_fingerprint"}
    if set(manifest) != required or manifest["calculation_evidence_version"] != 1 or manifest["profile_id"] not in {"realized_fifo_v1", "realized_fifo_v1_1"} or manifest["status"] != "completed":
        _abort("realized_materialization_evidence_invalid")
    _algorithm(manifest["algorithm_version"]); _public_ref(manifest["portfolio_ref"], "pfr_")
    _fingerprint(manifest["input_fingerprint"]); _utc(manifest["evidence_cutoff_at_utc"])
    _fingerprint(manifest["artifact_fingerprint"])
    if manifest["context_binding_fingerprint"] != fifo_context_fingerprint_v1(context): _abort("realized_materialization_context_mismatch")
    if _manifest_fingerprint(manifest) != manifest["artifact_fingerprint"]: _abort("realized_materialization_evidence_fingerprint_mismatch")
    if not isinstance(manifest["files"], list) or [item.get("file_name") for item in manifest["files"]] != list(TABLE_ORDER):
        _abort("realized_materialization_evidence_invalid")
    if {path.name for path in root.iterdir()} != set(TABLE_ORDER) | {"evidence-manifest.json"}: _abort("realized_materialization_evidence_invalid")
    tables: dict[str, list[dict[str, str]]] = {}
    row_fingerprints: list[str] = []
    forbidden = {"tenant_id", "user_id", "data_space_id", "internal_id", "database_path"}
    for entry in manifest["files"]:
        file_name = entry["file_name"]; path = root / file_name
        if path.is_symlink() or not path.is_file(): _abort("realized_materialization_evidence_invalid")
        payload = path.read_bytes()
        if _sha(payload) != entry.get("sha256"): _abort("realized_materialization_evidence_fingerprint_mismatch")
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle, strict=True); headers = tuple(reader.fieldnames or ()); rows = list(reader)
        except (OSError, UnicodeError, csv.Error) as exc: raise RealizedMaterializationBlocked("realized_materialization_evidence_invalid") from exc
        if semantic:
            from workers.reference.semantic_realized_fifo_v1 import TABLE_COLUMNS
            template_headers = tuple(TABLE_COLUMNS[file_name])
        else:
            template_headers = tuple((TEMPLATE_ROOT / file_name).read_text(encoding="utf-8").rstrip("\n").split(","))
        if headers != template_headers or forbidden & set(headers) or len(rows) != entry.get("row_count"):
            _abort("realized_materialization_evidence_invalid")
        for row in rows:
            if None in row or any(value is None or "\r" in value or "\n" in value for value in row.values()): _abort("realized_materialization_evidence_invalid")
            for field, value in row.items():
                if field.endswith("_decimal") and value and not _DECIMAL.fullmatch(value): _abort("realized_materialization_evidence_invalid")
                if not field.endswith("_decimal") and value.startswith(("=", "+", "@")): _abort("realized_materialization_evidence_invalid")
            row_fingerprints.append(_sha({"table_name": file_name, "row": row}))
        tables[file_name] = rows
    row_set = _sha({"table_order": TABLE_ORDER, "row_fingerprints": row_fingerprints})
    if not semantic:
        bindings = [{"semantic_contract": "portfolio_ledger_v1_transaction_fact", "source_event_count": len(tables["event-results.csv"]), "projected_event_count": len(tables["event-results.csv"]), "coupled_transaction_fact": True, "automatic_cash_posting_state": "unknown"}]
        manifest["semantic_source_bindings"] = bindings
        manifest["semantic_binding_fingerprint"] = _sha(bindings)
    bindings, semantic_fingerprint = _semantic_bindings(
        manifest["semantic_source_bindings"], manifest["semantic_binding_fingerprint"]
    )
    manifest["semantic_source_bindings"] = bindings
    manifest["semantic_binding_fingerprint"] = semantic_fingerprint
    if semantic:
        event_contracts = {row["semantic_contract"] for row in tables["event-results.csv"]}
        if event_contracts - {"portfolio_ledger_v1_transaction_fact", "asset_activity_v1"} or event_contracts != {row["semantic_contract"] for row in bindings if row["projected_event_count"] > 0}:
            _abort("realized_materialization_evidence_invalid")
    return manifest, tables, row_set


def _append_job_state(connection: sqlite3.Connection, row: sqlite3.Row, status: str, created_at_utc: str, *, failure_code: str | None = None, artifact_id: str | None = None) -> None:
    sequence = int(row["state_sequence"]) + 1
    connection.execute(
        "INSERT INTO realized_rebuild_job_state VALUES (?,?,?,?,?,?,?,?)",
        (_id("rjs", [row["job_ref"], sequence, status]), row["job_id"], sequence, status, failure_code, artifact_id, row["job_state_id"], created_at_utc),
    )


def _latest_artifact_row(connection: sqlite3.Connection, portfolio_ref: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT artifact.*,base.artifact_ref AS base_artifact_ref FROM realized_artifact artifact LEFT JOIN realized_artifact base ON base.artifact_id=artifact.base_artifact_id WHERE artifact.portfolio_ref=? ORDER BY artifact.completed_at_utc DESC,artifact.artifact_ref DESC LIMIT 1",
        (portfolio_ref,),
    ).fetchone()


def _artifact_tables(connection: sqlite3.Connection, artifact_id: str) -> dict[str, list[dict[str, str]]]:
    result = {name: [] for name in TABLE_ORDER}
    rows = connection.execute(
        "SELECT link.table_name,blob.row_json FROM realized_artifact_row link JOIN realized_row_blob blob USING(row_blob_id) WHERE link.artifact_id=? ORDER BY CASE link.table_name WHEN 'event-results.csv' THEN 1 WHEN 'lot-movements.csv' THEN 2 WHEN 'remaining-lots.csv' THEN 3 WHEN 'position-history.csv' THEN 4 WHEN 'position-summary.csv' THEN 5 ELSE 6 END,link.row_ordinal",
        (artifact_id,),
    ).fetchall()
    for row in rows: result[row["table_name"]].append(json.loads(row["row_json"]))
    return result


def _validate_incremental_prefix(previous: dict[str, list[dict[str, str]]], current: dict[str, list[dict[str, str]]], invalidated_from_utc: str, reason: str) -> None:
    if reason == "algorithm_upgrade": _abort("realized_materialization_full_rebuild_required")
    previous_events = {row["event_ref"]: row for row in previous["event-results.csv"] if row["effective_at_utc"] is not None and row["effective_at_utc"] < invalidated_from_utc}
    current_events = {row["event_ref"]: row for row in current["event-results.csv"] if row["effective_at_utc"] is not None and row["effective_at_utc"] < invalidated_from_utc}
    if previous_events != current_events: _abort("realized_materialization_incremental_prefix_mismatch")
    previous_history = [row for row in previous["position-history.csv"] if row["effective_at_utc"] is not None and row["effective_at_utc"] < invalidated_from_utc]
    current_history = [row for row in current["position-history.csv"] if row["effective_at_utc"] is not None and row["effective_at_utc"] < invalidated_from_utc]
    if previous_history != current_history: _abort("realized_materialization_incremental_prefix_mismatch")
    if reason == "append_only":
        maximum = max((row["effective_at_utc"] for row in previous["event-results.csv"] if row["effective_at_utc"] is not None), default="0000-00-00T00:00:00Z")
        if invalidated_from_utc <= maximum: _abort("realized_materialization_append_fast_path_invalid")


def publish_realized_materialization_v1(
    store_path: str | Path, context: RealizedContext | Mapping[str, str], *, job_ref: str,
    evidence_path: str | Path, rebuild_mode: str, completed_at_utc: str, failpoint: str | None = None,
) -> RealizedArtifact:
    context = _normalize_context(context); completed = _utc(completed_at_utc)
    if rebuild_mode not in {"full", "incremental"} or (failpoint is not None and failpoint not in FAILPOINTS):
        _abort("realized_materialization_input_invalid")
    manifest, tables, row_set = _read_evidence(evidence_path, context)
    connection = _connect(store_path, context)
    try:
        job = _job_current(connection, job_ref)
        if job["status"] != "pending": _abort("realized_materialization_job_not_pending")
        if manifest["portfolio_ref"] != job["portfolio_ref"] or manifest["input_fingerprint"] != job["desired_input_fingerprint"] or manifest["algorithm_version"] != job["requested_algorithm_version"]:
            _abort("realized_materialization_job_evidence_mismatch")
        previous = _latest_artifact_row(connection, job["portfolio_ref"])
        if rebuild_mode == "incremental":
            if previous is None: _abort("realized_materialization_full_rebuild_required")
            previous_tables = _artifact_tables(connection, previous["artifact_id"])
            _validate_incremental_prefix(previous_tables, tables, job["invalidated_from_utc"], job["invalidation_reason"])
        elif job["invalidation_reason"] == "append_only" and previous is not None:
            # Explicit full rebuild remains valid and is the parity oracle.
            pass
        connection.execute("BEGIN IMMEDIATE")
        current = _job_current(connection, job_ref); _append_job_state(connection, current, "running", completed)
        connection.commit()
        running = _job_current(connection, job_ref)
        artifact_ref = _id("rar", {
            "job_ref": job_ref, "evidence_artifact_fingerprint": manifest["artifact_fingerprint"],
            "algorithm_version": manifest["algorithm_version"], "rebuild_mode": rebuild_mode,
        })
        artifact_id = _id("rai", artifact_ref)
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO realized_artifact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (artifact_id, artifact_ref, manifest["portfolio_ref"], manifest["algorithm_version"], manifest["input_fingerprint"],
                 manifest["artifact_fingerprint"], manifest["evidence_cutoff_at_utc"], rebuild_mode,
                 previous["artifact_id"] if rebuild_mode == "incremental" and previous is not None else None,
                 job["invalidated_from_utc"], job["job_id"], row_set,
                 _json(manifest["semantic_source_bindings"]), manifest["semantic_binding_fingerprint"], completed),
            )
            if failpoint == "after_artifact": raise RuntimeError("synthetic")
            for table_name in TABLE_ORDER:
                for ordinal, row in enumerate(tables[table_name], 1):
                    row_json = _json(row); row_fp = _sha({"table_name": table_name, "row": row})
                    blob_id = _id("rrb", row_fp)
                    connection.execute(
                        "INSERT OR IGNORE INTO realized_row_blob VALUES (?,?,?,?,?)",
                        (blob_id, row_fp, table_name, row_json, completed),
                    )
                    connection.execute(
                        "INSERT INTO realized_artifact_row VALUES (?,?,?,?)",
                        (artifact_id, table_name, ordinal, blob_id),
                    )
            if failpoint == "after_rows": raise RuntimeError("synthetic")
            for row in tables["position-summary.csv"]:
                checkpoint_fp = _sha({"artifact_ref": artifact_ref, "position": row, "cutoff": manifest["evidence_cutoff_at_utc"]})
                connection.execute(
                    "INSERT INTO realized_position_checkpoint VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (_id("rcp", checkpoint_fp), artifact_id, row["position_ref"], row["account_ref"], row["asset_ref"], row["currency"],
                     manifest["evidence_cutoff_at_utc"], row["remaining_quantity_decimal"], row["remaining_fifo_cost_decimal"], checkpoint_fp),
                )
            if failpoint == "after_checkpoints": raise RuntimeError("synthetic")
            _append_job_state(connection, running, "completed", completed, artifact_id=artifact_id)
            connection.commit()
        except Exception as exc:
            connection.rollback()
            failed_current = _job_current(connection, job_ref)
            connection.execute("BEGIN IMMEDIATE")
            _append_job_state(connection, failed_current, "failed", completed, failure_code="realized_materialization_publication_failed")
            connection.commit()
            if isinstance(exc, RealizedMaterializationBlocked): raise
            raise RealizedMaterializationBlocked("realized_materialization_publication_failed") from exc
    finally:
        connection.close()
    return RealizedArtifact(
        artifact_ref, manifest["portfolio_ref"], manifest["algorithm_version"], manifest["input_fingerprint"],
        manifest["artifact_fingerprint"], manifest["evidence_cutoff_at_utc"], rebuild_mode,
        previous["artifact_ref"] if rebuild_mode == "incremental" and previous is not None else None, row_set,
    )


def read_latest_realized_materialization_v1(store_path: str | Path, context: RealizedContext | Mapping[str, str], portfolio_ref: str) -> dict[str, Any]:
    portfolio_ref = _public_ref(portfolio_ref, "pfr_")
    connection = _connect(store_path, context, read_only=True)
    try:
        artifact = _latest_artifact_row(connection, portfolio_ref)
        jobs = connection.execute(
            "SELECT job.job_ref,job.desired_input_fingerprint,job.invalidation_reason,state.status,state.failure_code,job.created_at_utc FROM realized_rebuild_job job JOIN current_realized_rebuild_job_state state USING(job_id) WHERE job.portfolio_ref=? ORDER BY job.created_at_utc,job.job_ref",
            (portfolio_ref,),
        ).fetchall()
        stale_jobs = [dict(row) for row in jobs if row["status"] != "completed" and (artifact is None or row["desired_input_fingerprint"] != artifact["input_fingerprint"] or row["created_at_utc"] >= artifact["completed_at_utc"])]
        if artifact is None:
            return {"contract_version": 1, "status": "pending" if stale_jobs else "empty", "artifact": None, "tables": None, "stale_jobs": stale_jobs}
        public = {
            key: artifact[key] for key in (
                "artifact_ref", "portfolio_ref", "algorithm_version", "input_fingerprint",
                "evidence_artifact_fingerprint", "evidence_cutoff_at_utc", "rebuild_mode",
                "base_artifact_ref", "row_set_fingerprint", "completed_at_utc",
            )
        }
        tables = _artifact_tables(connection, artifact["artifact_id"])
        try:
            bindings = json.loads(artifact["semantic_source_bindings_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise RealizedMaterializationBlocked("realized_materialization_evidence_invalid") from exc
        bindings, semantic_fingerprint = _semantic_bindings(bindings, artifact["semantic_binding_fingerprint"])
        public["semantic_source_bindings"] = bindings
        public["semantic_binding_fingerprint"] = semantic_fingerprint
        return {
            "contract_version": 1, "status": "stale" if stale_jobs else "completed",
            "artifact": public, "tables": tables,
            "stale_jobs": stale_jobs,
        }
    finally:
        connection.close()


def realized_materialization_reconciliation_v1(store_path: str | Path, context: RealizedContext | Mapping[str, str], artifact_ref: str, evidence_path: str | Path) -> dict[str, Any]:
    manifest, tables, row_set = _read_evidence(evidence_path, context)
    connection = _connect(store_path, context, read_only=True)
    try:
        artifact = connection.execute("SELECT * FROM realized_artifact WHERE artifact_ref=?", (artifact_ref,)).fetchone()
        if artifact is None: _abort("realized_materialization_artifact_missing")
        stored = _artifact_tables(connection, artifact["artifact_id"])
        return {
            "artifact_ref": artifact_ref,
            "evidence_artifact_fingerprint": manifest["artifact_fingerprint"],
            "row_set_fingerprint": row_set,
            "csv_equals_persistent_rows": stored == tables,
            "artifact_fingerprint_matches": artifact["evidence_artifact_fingerprint"] == manifest["artifact_fingerprint"],
            "status": "reconciled" if stored == tables and artifact["row_set_fingerprint"] == row_set else "mismatch",
        }
    finally:
        connection.close()


def realized_materialization_retention_plan_v1(store_path: str | Path, context: RealizedContext | Mapping[str, str], portfolio_ref: str, referenced_artifact_refs: Sequence[str]) -> dict[str, Any]:
    portfolio_ref = _public_ref(portfolio_ref, "pfr_")
    references = {_public_ref(value, "rar_") for value in referenced_artifact_refs}
    connection = _connect(store_path, context, read_only=True)
    try:
        rows = connection.execute("SELECT artifact_ref FROM realized_artifact WHERE portfolio_ref=? ORDER BY completed_at_utc,artifact_ref", (portfolio_ref,)).fetchall()
        latest = _latest_artifact_row(connection, portfolio_ref)
        protected = references | ({latest["artifact_ref"]} if latest else set())
        return {
            "portfolio_ref": portfolio_ref, "protected_artifact_refs": sorted(protected),
            "eligible_artifact_refs": [row["artifact_ref"] for row in rows if row["artifact_ref"] not in protected],
            "deletion_executed": False,
        }
    finally:
        connection.close()
