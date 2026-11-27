"""Immutable generation-level correction/void for schema-401 Asset Activity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
from typing import Any, Mapping, Sequence

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference.asset_activity_v1 import AssetActivityV1Error
from migrations.reference.schema400_asset_activity_compat_v1 import (
    OneUseSchema400AssetActivityAuthorizerV1,
    Schema400AssetActivityCompatV1Error,
    apply_schema400_asset_activity_v1,
    build_schema400_asset_activity_confirmation_v1,
    preview_schema400_asset_activity_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    ACTIVE_NAME, LEDGER_NAME, MANIFEST_NAME, PRODUCT_AREA, SUCCESS_NAME,
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error,
    _CanonicalReadBarrierV1, _ProductWriterLockV1, _activity_rows, _assert_event_refs_not_corrected, _atomic_json_replace,
    _canonical_snapshot, _compat_context, _context, _context_fingerprint, _native_events,
    _owner_directory, _owner_file, _read_connection, _remove_staging_generations,
    _sha, _sha_file, _write_new_file, materialize_desktop_product_semantic_ledger_v1,
    read_desktop_product_asset_activity_binding_v1,
)
from workers.reference.semantic_realized_fifo_v2 import SemanticRealizedFifoV2Error, project_semantic_realized_fifo_v2

CONTRACT_VERSION = 1
CORRECTION_NAME = "asset-activity-correction-receipt.json"
ATTEMPT_AREA = "correction-attempts"
ATTEMPT_SUFFIX = ".json"
CHALLENGE = re.compile(r"^aac_[a-f0-9]{16,64}$")
FP = re.compile(r"^[a-f0-9]{64}$")
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
FAILPOINTS = frozenset({None, "after_attempt", "after_generation_complete", "after_generation_publish", "before_active_replace", "after_active_replace"})
FAILURE_CODES = frozenset({
    "asset_activity_correction_attempt_conflict", "asset_activity_correction_boundary_failed",
    "asset_activity_correction_confirmation_expired", "asset_activity_correction_confirmation_invalid",
    "asset_activity_correction_context_invalid", "asset_activity_correction_fifo_invalid",
    "asset_activity_correction_generation_conflict", "asset_activity_correction_input_invalid",
    "asset_activity_correction_predecessor_missing", "asset_activity_correction_preview_stale",
    "asset_activity_correction_publication_failed", "asset_activity_correction_receipt_invalid",
    "asset_activity_correction_storage_invalid", "synthetic_asset_activity_correction_failpoint",
})
EVENT_COLUMNS = (
    "event_ref", "event_type", "account_ref", "related_account_ref", "asset_ref", "source_asset_ref",
    "event_time_evidence", "local_date", "local_time", "time_zone", "effective_at_utc",
    "original_acquired_time_evidence", "original_acquired_local_date", "original_acquired_local_time",
    "original_acquired_time_zone", "original_acquired_at_utc", "amount_input_mode", "basis_evidence_mode",
    "quantity_decimal", "eligible_quantity_decimal", "unit_price_decimal", "gross_amount_decimal",
    "monetary_fee_decimal", "asset_fee_quantity_decimal", "provided_basis_decimal", "movement_context_code",
)


class DesktopAssetActivityCorrectionV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES: raise ValueError("asset_activity_correction_error_code_unregistered")
        self.code = code; super().__init__(code)


@dataclass(frozen=True)
class DesktopAssetActivityCorrectionResultV1:
    status: str
    action_type: str
    generation_ref: str
    predecessor_preserved: bool
    replacement_event_count: int
    total_asset_activity_event_count: int
    schema201_canonical_write: bool = False
    cash_posting_count: int = 0
    provider_access: bool = False
    network_access: bool = False


def desktop_asset_activity_correction_v1_error_codes() -> tuple[str, ...]: return tuple(sorted(FAILURE_CODES))

def _abort(code: str) -> None: raise DesktopAssetActivityCorrectionV1Error(code)

def _canonical(value: Any) -> bytes:
    try: return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    except Exception: _abort("asset_activity_correction_input_invalid")

def _fingerprint(value: Any) -> str: return hashlib.sha256(_canonical(value)).hexdigest()

def _utc(value: Any) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None: _abort("asset_activity_correction_input_invalid")
    try: parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError: _abort("asset_activity_correction_input_invalid")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value: _abort("asset_activity_correction_input_invalid")
    return value

def _runtime(value: Any) -> DesktopProductAssetActivityContextV1:
    try: return _context(value)
    except DesktopProductAssetActivityV1Error: _abort("asset_activity_correction_context_invalid")

_product_read_activity_binding=read_desktop_product_asset_activity_binding_v1

def read_desktop_product_asset_activity_binding_v1(data_space: str|Path, context: DesktopProductAssetActivityContextV1) -> dict[str, Any]:
    try:return _product_read_activity_binding(data_space,context)
    except DesktopProductAssetActivityV1Error:_abort("asset_activity_correction_generation_conflict")

def _correction_file(path: str | Path, code: str) -> Path:
    try: return _owner_file(path, "desktop_asset_activity_storage_invalid")
    except DesktopProductAssetActivityV1Error: _abort(code)

def _correction_directory(path: str | Path, *, create: bool = False, code: str = "asset_activity_correction_storage_invalid") -> Path:
    try: return _owner_directory(path, create=create)
    except DesktopProductAssetActivityV1Error: _abort(code)

def _read_json(path: Path, code: str) -> dict[str, Any]:
    path = _correction_file(path, code)
    try: value = json.loads(path.read_text(encoding="utf-8"))
    except Exception: _abort(code)
    if not isinstance(value, dict) or path.read_bytes() != _canonical(value) + b"\n": _abort(code)
    return value

def _offset(value: str, seconds: int) -> str:
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    from datetime import timedelta
    return (parsed + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _event_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    mapped = {key: row[key] for key in EVENT_COLUMNS if key not in {"account_ref", "related_account_ref", "asset_ref", "source_asset_ref"}}
    mapped.update(account_ref=row["account_id"], related_account_ref=row["related_account_id"], asset_ref=row["asset_id"], source_asset_ref=row["source_asset_id"])
    return mapped


def _predecessor(ledger: Path, event_ref: str) -> dict[str, Any]:
    if not isinstance(event_ref, str) or not event_ref.startswith("evt_"): _abort("asset_activity_correction_input_invalid")
    connection = _read_connection(ledger)
    try: rows = connection.execute("SELECT * FROM current_asset_activity_event WHERE event_ref=?", (event_ref,)).fetchall()
    except sqlite3.Error: _abort("asset_activity_correction_storage_invalid")
    finally: connection.close()
    if len(rows) != 1: _abort("asset_activity_correction_predecessor_missing")
    return dict(rows[0])


def _remove_predecessor(ledger: Path, event_ref: str | list[str]) -> None:
    """Remove a selected set in one private transaction and rebase once; never edit a published ledger."""
    refs = event_ref if isinstance(event_ref, list) else [event_ref]
    parameters = [(ref,) for ref in refs]
    connection = sqlite3.connect(ledger); connection.row_factory = sqlite3.Row; connection.execute("PRAGMA foreign_keys=ON")
    trigger_names = [
        "asset_activity_event_no_delete", "asset_activity_event_no_update",
        "asset_activity_command_receipt_no_delete", "ledger_receipt_no_delete",
    ]
    evidence_table = connection.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='asset_activity_fifo_order_evidence'"
    ).fetchone()[0] == 1
    if evidence_table:
        trigger_names.append("asset_activity_fifo_order_evidence_no_delete")
    try:
        triggers = {
            name: connection.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)).fetchone()
            for name in trigger_names
        }
        if any(row is None or not isinstance(row[0], str) for row in triggers.values()):
            _abort("asset_activity_correction_storage_invalid")
        old_commands = [row[0] for row in connection.execute("SELECT command_id FROM asset_activity_command_receipt ORDER BY command_id")]
        if not old_commands: _abort("asset_activity_correction_predecessor_missing")
        connection.execute("BEGIN IMMEDIATE")
        for name in trigger_names: connection.execute(f"DROP TRIGGER {name}")
        if evidence_table:
            connection.executemany(
                "DELETE FROM asset_activity_fifo_order_evidence WHERE event_ref=?", parameters
            )
        deleted = connection.executemany("DELETE FROM asset_activity_event WHERE event_ref=?", parameters).rowcount
        if deleted != len(refs): _abort("asset_activity_correction_predecessor_missing")
        remaining = [dict(row) for row in connection.execute("SELECT event_ref,effect_fingerprint,created_at_utc FROM asset_activity_event ORDER BY event_ref")]
        if remaining:
            material = {"contract_version": "asset_activity_effective_generation_rebase_v1", "removed_event_ref": event_ref, "events": remaining}
            if isinstance(event_ref, list):
                material = {"contract_version": "asset_activity_effective_generation_rebase_v2", "removed_event_refs": refs, "events": remaining}
            token = _fingerprint(material)
            command_id = "cmd_asset_rebase_" + token[:40]
            preview_fingerprint = _fingerprint({"rebase_preview": material})
            confirmation_fingerprint = _fingerprint({"rebase_confirmation": material})
            receipt_fingerprint = _fingerprint({"rebase_receipt": material})
            committed_at_utc = max(row["created_at_utc"] for row in remaining)
            connection.execute(
                "INSERT INTO ledger_command_receipt VALUES(?,'data_app','asset_activity_create_v1','data_generation_rebase',?,?,?)",
                (command_id, preview_fingerprint, confirmation_fingerprint, committed_at_utc),
            )
            connection.execute("UPDATE asset_activity_event SET command_id=?", (command_id,))
        placeholders = ",".join("?" for _ in old_commands)
        connection.execute(f"DELETE FROM asset_activity_command_receipt WHERE command_id IN ({placeholders})", old_commands)
        connection.execute(f"DELETE FROM ledger_command_receipt WHERE command_id IN ({placeholders})", old_commands)
        if remaining:
            connection.execute(
                "INSERT INTO asset_activity_command_receipt VALUES(?,'asset_activity_create_v1',?,?,?,NULL,NULL,NULL,NULL,NULL,?,?)",
                (command_id, preview_fingerprint, confirmation_fingerprint, len(remaining), receipt_fingerprint, committed_at_utc),
            )
        for name in trigger_names: connection.execute(triggers[name][0])
        connection.execute("COMMIT")
    except DesktopAssetActivityCorrectionV1Error:
        if connection.in_transaction: connection.execute("ROLLBACK")
        raise
    except sqlite3.Error:
        if connection.in_transaction: connection.execute("ROLLBACK")
        _abort("asset_activity_correction_storage_invalid")
    finally: connection.close()


def _correction_splits(data_space: Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    """Die Splits (#451) fuer die FIFO-Probe einer Korrektur. Ohne sie wiese die Probe nach einem Split jeden spaeteren Verkauf in
    neuen Stuecken als zu gross ab. Laesst sich der Speicher nicht lesen, rechnet die Probe ohne - das Fortschreiben des Stands
    bricht dann ohnehin ab."""
    from migrations.reference.stock_split_v1 import splits_for_fifo_v1
    try:
        return splits_for_fifo_v1(data_space, context)
    except Exception:
        return []


def _fifo_worlds(ledger: Path, details: dict | None = None, splits: Sequence[Mapping[str, Any]] = ()) -> dict[str, str]:
    connection = _read_connection(ledger)
    try:
        accounts = {row["account_id"]: dict(row) for row in connection.execute("SELECT entity.account_id,revision.account_type,revision.display_name FROM account_entity entity JOIN current_account_revision revision USING(account_id) WHERE revision.status='active'")}
        assets = {row["asset_id"]: dict(row) for row in connection.execute("SELECT asset_id,display_name,asset_type,quantity_scale FROM current_asset_revision WHERE status='active'")}
        portfolio_labels = {row['portfolio_id']: row['display_name'] for row in connection.execute("SELECT portfolio_id,display_name FROM current_portfolio_revision")}
        rows = [dict(row) for row in connection.execute("SELECT * FROM current_asset_activity_event ORDER BY portfolio_id,asset_id,local_date,COALESCE(effective_at_utc,''),event_ref")]
        evidence_table = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='asset_activity_fifo_order_evidence'"
        ).fetchone()[0] == 1
        order_evidence = [] if not evidence_table else [
            dict(row) for row in connection.execute(
                "SELECT * FROM asset_activity_fifo_order_evidence ORDER BY event_ref"
            )
        ]
    except sqlite3.Error: _abort("asset_activity_correction_storage_invalid")
    finally: connection.close()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows: grouped.setdefault((row["portfolio_id"], row["asset_id"]), []).append(row)
    results: dict[str, str] = {}
    for (portfolio_ref, asset_ref), values in sorted(grouped.items()):
        basis = {row["basis_currency"] for row in values}; account_refs = {row["account_id"] for row in values} | {row["related_account_id"] for row in values if row["related_account_id"]}; source_refs = {row["source_asset_id"] for row in values if row["source_asset_id"]}
        if len(basis) != 1 or not account_refs <= set(accounts) or not ({asset_ref} | source_refs) <= set(assets): _abort("asset_activity_correction_fifo_invalid")
        activity = {
            "asset_activity_version": 1, "basis_currency": next(iter(basis)),
            "accounts": [{"account_ref": ref, "account_type": accounts[ref]["account_type"]} for ref in sorted(account_refs)],
            "assets": [{"asset_ref": ref, "asset_type": assets[ref]["asset_type"], "quantity_scale": assets[ref]["quantity_scale"]} for ref in sorted({asset_ref} | source_refs)],
            "events": [_event_from_row(row) for row in values],
        }
        wrapper = {"realized_fifo_version": 2, "source_contract": "asset_activity_v1", "asset_activity": activity}
        event_refs = {event["event_ref"] for event in activity["events"]}
        world_evidence = [row for row in order_evidence if row["event_ref"] in event_refs]
        if world_evidence:
            wrapper["fifo_order_evidence"] = world_evidence
        world_splits = sorted((dict(item) for item in splits if item["asset_ref"] == asset_ref
                               and (item["account_ref"] is None or item["account_ref"] in account_refs)),
                              key=lambda item: (item["effective_local_date"], item["split_ref"]))
        if world_splits:
            wrapper["splits"] = world_splits
        try: result = project_semantic_realized_fifo_v2(wrapper)
        except SemanticRealizedFifoV2Error:
            # Die Welt, an der die Probe scheitert, bleibt am Fehler haengen. Nur damit
            # laesst sich spaeter sagen, an welcher Buchung es liegt (#420); am Code und
            # am Ablauf aendert das nichts.
            failure = DesktopAssetActivityCorrectionV1Error("asset_activity_correction_fifo_invalid")
            failure.fifo_world = wrapper
            raise failure
        key = _fingerprint({"portfolio_ref": portfolio_ref, "asset_ref": asset_ref})
        results[key] = result["result_fingerprint"]
        if details is not None:
            position = next(row for row in result["asset_positions"] if row["asset_ref"] == asset_ref)
            details[key] = {name: value for name, value in position.items() if name != "asset_ref"}
            details[key].update(asset_label=assets[asset_ref]['display_name'], portfolio_label=portfolio_labels[portfolio_ref], basis_currency=next(iter(basis)))
            ordinals = {ref: n+1 for n, ref in enumerate(sorted(accounts))}
            details[key]['custody_positions'] = [
                {'account_ordinal': ordinals[row['account_ref']], 'account_label': accounts[row['account_ref']]['display_name'],
                 'remaining_quantity_decimal': row['remaining_quantity_decimal']}
                for row in result['custody_positions'] if row['asset_ref'] == asset_ref
            ]
    return results


def _probe_replacement(ledger: Path, context: DesktopProductAssetActivityContextV1, portfolio_id: str, replacement: dict[str, Any] | None, at_utc: str,
                       splits: Sequence[Mapping[str, Any]] = ()) -> tuple[dict[str, Any] | None, dict[str, str]]:
    if replacement is None: return None, _fifo_worlds(ledger, splits=splits)
    try: preview = preview_schema400_asset_activity_v1(ledger, _compat_context(context), portfolio_id, [replacement])
    except (Schema400AssetActivityCompatV1Error, AssetActivityV1Error): _abort("asset_activity_correction_input_invalid")
    confirmation = build_schema400_asset_activity_confirmation_v1(preview, _compat_context(context), "sac_" + _fingerprint({"probe": replacement})[:32], at_utc, at_utc, _offset(at_utc, 300))
    authorizer = OneUseSchema400AssetActivityAuthorizerV1(); authorizer.register(confirmation)
    try: apply_schema400_asset_activity_v1(ledger, _compat_context(context), portfolio_id, [replacement], confirmation, authorizer, at_utc)
    except Schema400AssetActivityCompatV1Error: _abort("asset_activity_correction_input_invalid")
    return preview, _fifo_worlds(ledger, splits=splits)


def _preview_build(canonical_path: Path, data_space: Path, context: DesktopProductAssetActivityContextV1, predecessor_ref: str | list[str], replacement_value: Any, at_utc: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding.get("status") != "available": _abort("asset_activity_correction_predecessor_missing")
    batch = isinstance(predecessor_ref, list)
    if batch:
        if (replacement_value is not None or not 2 <= len(predecessor_ref) <= 1000 or
            not all(isinstance(ref, str) for ref in predecessor_ref) or len(set(predecessor_ref)) != len(predecessor_ref)):
            _abort("asset_activity_correction_input_invalid")
        refs = sorted(predecessor_ref)
    else:
        refs = [predecessor_ref]
    predecessors = [_predecessor(Path(binding["ledger_path"]), ref) for ref in refs]
    predecessor = predecessors[0]
    predecessor_ref = refs[0]
    if replacement_value is None: replacement = None
    else:
        try: replacement = _native_events([replacement_value])[0]
        except DesktopProductAssetActivityV1Error: _abort("asset_activity_correction_input_invalid")
        if replacement["event_ref"] == predecessor_ref: _abort("asset_activity_correction_input_invalid")
        _assert_event_refs_not_corrected(data_space, context, [replacement])
    action = "void" if replacement is None else "correct"
    with __import__("tempfile").TemporaryDirectory(prefix=".activity-correction-preview-", dir=data_space) as temporary:
        target = Path(temporary) / LEDGER_NAME
        materialized = materialize_desktop_product_semantic_ledger_v1(canonical_path, Path(binding["ledger_path"]), target, context)
        before_details = {}; after_details = {}
        splits = _correction_splits(data_space, context)
        before_fifo = _fifo_worlds(target, before_details, splits)
        selected_events = []
        if batch:
            connection = _read_connection(target)
            try:
                for ref in refs:
                    row = connection.execute(
                        'SELECT p.display_name AS portfolio_label,a.display_name AS asset_label,'
                        'c.display_name AS account_label,r.display_name AS related_account_label,'
                        'e.event_type,e.local_date,e.local_time,e.time_zone,e.unit_price_decimal,e.gross_amount_decimal,e.basis_currency,'
                        'e.quantity_decimal,e.monetary_fee_decimal,e.asset_fee_quantity_decimal '
                        'FROM current_asset_activity_event e JOIN current_portfolio_revision p ON p.portfolio_id=e.portfolio_id '
                        'JOIN current_asset_revision a ON a.asset_id=e.asset_id '
                        'JOIN current_account_revision c ON c.account_id=e.account_id '
                        'LEFT JOIN current_account_revision r ON r.account_id=e.related_account_id WHERE e.event_ref=?', (ref,)).fetchone()
                    if row is None: _abort('asset_activity_correction_predecessor_missing')
                    selected_events.append(dict(row))
            finally: connection.close()
        # All removals occur only in this private candidate, never as separate commits.
        _remove_predecessor(target, refs if batch else predecessor_ref)
        schema_preview, fifo = _probe_replacement(target, context, predecessor["portfolio_id"], replacement, at_utc, splits)
        _fifo_worlds(target, after_details, splits)
        changed = sorted(key for key in set(before_fifo) | set(fifo) if before_fifo.get(key) != fifo.get(key))
    body = {
        "asset_activity_correction_preview_version": 1, "status": "ready_for_confirmation", "action_type": action,
        "source_generation_ref": binding["generation_ref"], "source_activity_set_fingerprint": binding["activity_set_fingerprint"],
        "canonical_fingerprint": materialized["canonical_fingerprint"], "predecessor_event_ref": predecessor_ref,
        "predecessor_effect_fingerprint": predecessor["effect_fingerprint"], "replacement_event": replacement,
        "replacement_preview_fingerprint": None if schema_preview is None else schema_preview["preview_fingerprint"],
        "fifo_world_result_fingerprints": fifo, "confirmation_required": True, "one_attempt_only": True,
        "predecessor_preserved": True, "schema201_canonical_write": False, "cash_posting_count": 0,
        "provider_access": False, "network_access": False,
    }
    if batch:
        body["asset_activity_correction_preview_version"] = 2
        body["context_fingerprint"] = _context_fingerprint(context)
        body["selected_events"] = selected_events
        body["batch_predecessors"] = [{"event_ref": row["event_ref"], "effect_fingerprint": row["effect_fingerprint"]} for row in predecessors]
        body["batch_fifo_changes"] = [{"world_ordinal": n+1, "before": before_details.get(key),
                                      "after": after_details.get(key),
                                      "after_state": "present" if key in after_details else "no_remaining_events"} for n, key in enumerate(changed)]
    else:
        body["single_affected_fifo_world_count"] = len(changed)
        body["single_after_state"] = "no_remaining_events" if changed and all(key not in after_details for key in changed) else "present"
    body["plan_fingerprint"] = _fingerprint(body)
    return body, predecessor, schema_preview


def preview_desktop_asset_activity_correction_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, predecessor_event_ref: str | list[str], replacement_event: Any, previewed_at_utc: str) -> dict[str, Any]:
    context = _runtime(context_value); data_space = _correction_directory(data_space_path); canonical = _correction_file(canonical_path, "asset_activity_correction_storage_invalid"); at = _utc(previewed_at_utc)
    internal, predecessor, schema_preview = _preview_build(canonical, data_space, context, predecessor_event_ref, replacement_event, at)
    public = {
        "asset_activity_correction_public_preview_version": 3, "status": "ready_for_confirmation", "action_type": internal["action_type"],
        "predecessor": {"event_type": predecessor["event_type"], "local_date": predecessor["local_date"], "quantity_decimal": predecessor["quantity_decimal"], "gross_amount_decimal": predecessor["gross_economic_amount_decimal"], "fifo_basis_created_decimal": predecessor["fifo_basis_created_decimal"], "net_trade_proceeds_decimal": predecessor["net_trade_proceeds_decimal"], "gross_income_decimal": predecessor["gross_income_decimal"]},
        "replacement": None if schema_preview is None else {key: schema_preview["event_effects"][0][key] for key in ("event_type", "inventory_effect_code", "fifo_effect_code", "portfolio_quantity_change_decimal", "fifo_basis_created_decimal", "net_trade_proceeds_decimal", "gross_income_decimal")},
        "affected_fifo_world_count": internal.get("single_affected_fifo_world_count", 0), "after_state": internal.get("single_after_state", "present"), "predecessor_preserved": True,
        "confirmation_required": True, "schema201_canonical_write": False, "cash_posting_count": 0,
        "provider_access": False, "network_access": False, "path_exposed": False, "internal_id_exposed": False,
    }
    if "batch_predecessors" in internal:
        public["asset_activity_correction_public_preview_version"] = 2
        public.pop("after_state", None)
        public["selected_event_count"] = len(internal["batch_predecessors"])
        public["selected_events"] = internal["selected_events"]
        public["batch_fifo_changes"] = internal["batch_fifo_changes"]
        public["affected_fifo_world_count"] = len(internal["batch_fifo_changes"])
    return {"public_preview": public, "trusted_preview": internal}


def preview_desktop_asset_activity_multi_void_v2(canonical_path, data_space_path, context_value, predecessor_event_refs, previewed_at_utc):
    if not isinstance(predecessor_event_refs, list): _abort("asset_activity_correction_input_invalid")
    return preview_desktop_asset_activity_correction_v1(canonical_path, data_space_path, context_value, predecessor_event_refs, None, previewed_at_utc)


def apply_desktop_asset_activity_multi_void_v2(canonical_path, data_space_path, context_value, trusted_preview, confirmation, committed_at_utc, *, failpoint=None):
    if not isinstance(trusted_preview, Mapping) or trusted_preview.get("asset_activity_correction_preview_version") != 2:
        _abort("asset_activity_correction_input_invalid")
    return apply_desktop_asset_activity_correction_v1(canonical_path, data_space_path, context_value, trusted_preview, confirmation, committed_at_utc, failpoint=failpoint)


def build_desktop_asset_activity_correction_confirmation_v1(trusted_preview: Mapping[str, Any], context_value: Any, challenge_ref: str, issued_at_utc: str, confirmed_at_utc: str, expires_at_utc: str) -> dict[str, Any]:
    context = _runtime(context_value); issued = _utc(issued_at_utc); confirmed = _utc(confirmed_at_utc); expires = _utc(expires_at_utc)
    if not isinstance(trusted_preview, Mapping) or trusted_preview.get("status") != "ready_for_confirmation" or not isinstance(challenge_ref, str) or CHALLENGE.fullmatch(challenge_ref) is None or not issued <= confirmed <= expires:
        _abort("asset_activity_correction_confirmation_invalid")
    body = {"asset_activity_correction_confirmation_version": 1, "challenge_ref": challenge_ref, "context_fingerprint": _context_fingerprint(context), "plan_fingerprint": trusted_preview.get("plan_fingerprint"), "issued_at_utc": issued, "confirmed_at_utc": confirmed, "expires_at_utc": expires}
    body["confirmation_fingerprint"] = _fingerprint(body); return body


def _attempt(area: Path, confirmation: Mapping[str, Any], context: DesktopProductAssetActivityContextV1, at_utc: str) -> Path:
    attempts = _correction_directory(area / ATTEMPT_AREA, create=True); path = attempts / (confirmation["challenge_ref"] + ATTEMPT_SUFFIX)
    body = {"asset_activity_correction_attempt_version": 1, "attempt_status": "consumed_before_domain_write", "context_fingerprint": _context_fingerprint(context), "challenge_ref": confirmation["challenge_ref"], "plan_fingerprint": confirmation["plan_fingerprint"], "confirmation_fingerprint": confirmation["confirmation_fingerprint"], "attempted_at_utc": at_utc}
    content = _canonical(body) + b"\n"
    if path.exists():
        if _correction_file(path, "asset_activity_correction_attempt_conflict").read_bytes() != content: _abort("asset_activity_correction_attempt_conflict")
        return path
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle: handle.write(content); handle.flush(); os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except OSError: _abort("asset_activity_correction_attempt_conflict")
    return path


def _receipt_candidates(area: Path, plan_fingerprint: str) -> list[tuple[Path, dict[str, Any]]]:
    generations = area / "generations"
    if not generations.exists(): return []
    result = []
    for path in sorted(generations.iterdir()):
        if not path.is_dir() or path.is_symlink(): continue
        receipt = path / CORRECTION_NAME
        if receipt.exists():
            value = _read_json(receipt, "asset_activity_correction_receipt_invalid")
            body=dict(value);fingerprint=body.pop("receipt_fingerprint",None)
            if fingerprint!=_fingerprint(body):_abort("asset_activity_correction_receipt_invalid")
            if value.get("plan_fingerprint") == plan_fingerprint: result.append((path, value))
    if len(result) > 1: _abort("asset_activity_correction_generation_conflict")
    return result


def apply_desktop_asset_activity_correction_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, trusted_preview: Mapping[str, Any], confirmation: Mapping[str, Any], committed_at_utc: str, *, failpoint: str | None = None, recovery_confirmation: Mapping[str, Any] | None = None) -> DesktopAssetActivityCorrectionResultV1:
    context = _runtime(context_value); committed = _utc(committed_at_utc)
    if failpoint not in FAILPOINTS or not isinstance(trusted_preview, Mapping) or not isinstance(confirmation, Mapping): _abort("asset_activity_correction_input_invalid")
    preview_body = dict(trusted_preview); plan_fingerprint = preview_body.pop("plan_fingerprint", None)
    if plan_fingerprint != _fingerprint(preview_body): _abort("asset_activity_correction_preview_stale")
    if trusted_preview.get("asset_activity_correction_preview_version") not in {1, 2}:
        _abort("asset_activity_correction_input_invalid")
    batch = trusted_preview.get("asset_activity_correction_preview_version") == 2
    if batch:
        if trusted_preview.get("context_fingerprint") != _context_fingerprint(context):
            _abort("asset_activity_correction_confirmation_invalid")
        selected = trusted_preview.get("batch_predecessors")
        if (not isinstance(selected, list) or not 2 <= len(selected) <= 1000 or
            any(not isinstance(row, dict) or set(row) != {"event_ref", "effect_fingerprint"} or
                not isinstance(row["event_ref"], str) or not isinstance(row["effect_fingerprint"], str)
                for row in selected) or
            [row["event_ref"] for row in selected] != sorted(set(row["event_ref"] for row in selected)) or
            selected[0] != {"event_ref": trusted_preview.get("predecessor_event_ref"), "effect_fingerprint": trusted_preview.get("predecessor_effect_fingerprint")}):
            _abort("asset_activity_correction_input_invalid")
    if batch and (trusted_preview.get("action_type") != "void" or trusted_preview.get("replacement_event") is not None):
        _abort("asset_activity_correction_input_invalid")
    if (confirmation.get("asset_activity_correction_confirmation_version") != 1 or
        not isinstance(confirmation.get("challenge_ref"), str) or CHALLENGE.fullmatch(confirmation["challenge_ref"]) is None):
        _abort("asset_activity_correction_confirmation_invalid")
    if batch:
        issued = _utc(confirmation.get("issued_at_utc")); confirmed = _utc(confirmation.get("confirmed_at_utc")); expires = _utc(confirmation.get("expires_at_utc"))
        if not issued <= confirmed <= committed or confirmed > expires:
            _abort("asset_activity_correction_confirmation_invalid")
    expected_confirmation = {key: confirmation.get(key) for key in ("asset_activity_correction_confirmation_version", "challenge_ref", "context_fingerprint", "plan_fingerprint", "issued_at_utc", "confirmed_at_utc", "expires_at_utc")}
    expected_confirmation["confirmation_fingerprint"] = _fingerprint(expected_confirmation)
    if dict(confirmation) != expected_confirmation or confirmation.get("context_fingerprint") != _context_fingerprint(context) or confirmation.get("plan_fingerprint") != trusted_preview.get("plan_fingerprint"):
        _abort("asset_activity_correction_confirmation_invalid")
    if recovery_confirmation is not None:
        if not batch or not isinstance(recovery_confirmation, Mapping):
            _abort("asset_activity_correction_confirmation_invalid")
        fresh = build_desktop_asset_activity_correction_confirmation_v1(
            trusted_preview, context, recovery_confirmation.get('challenge_ref'),
            recovery_confirmation.get('issued_at_utc'), recovery_confirmation.get('confirmed_at_utc'),
            recovery_confirmation.get('expires_at_utc'))
        if fresh != dict(recovery_confirmation) or fresh['confirmation_fingerprint'] == confirmation['confirmation_fingerprint'] or committed < fresh['confirmed_at_utc']:
            _abort("asset_activity_correction_confirmation_invalid")
        if committed > fresh['expires_at_utc']:
            _abort("asset_activity_correction_confirmation_expired")
    elif committed > confirmation.get("expires_at_utc", ""):
        _abort("asset_activity_correction_confirmation_expired")
    data_space = _correction_directory(data_space_path); canonical = _correction_file(canonical_path, "asset_activity_correction_storage_invalid"); area = _correction_directory(data_space / PRODUCT_AREA)
    with _ProductWriterLockV1(area):
        existing = _receipt_candidates(area, trusted_preview["plan_fingerprint"])
        if len(existing) > 1: _abort("asset_activity_correction_receipt_invalid")
        if recovery_confirmation is not None:
            # Fresh authority is journaled separately. Original attempts and receipts
            # are never reset, replaced or backdated.
            fresh_path = area / ATTEMPT_AREA / (recovery_confirmation['challenge_ref'] + ATTEMPT_SUFFIX)
            recovery_path = area / ATTEMPT_AREA / (recovery_confirmation['challenge_ref'] + '.recovery.json')
            if fresh_path.exists() or fresh_path.is_symlink() or recovery_path.exists() or recovery_path.is_symlink():
                _abort('asset_activity_correction_attempt_conflict')
            _attempt(area, recovery_confirmation, context, committed)
            recovery_body = {'context_fingerprint': _context_fingerprint(context),
                             'plan_fingerprint': trusted_preview['plan_fingerprint'],
                             'confirmation': dict(recovery_confirmation),
                             'original_confirmation_fingerprint': confirmation['confirmation_fingerprint'],
                             'recovered_at_utc': committed}
            content = _canonical(recovery_body) + b'\n'
            _write_new_file(recovery_path, content)
        if existing:
            final, receipt = existing[0]
            if batch and (receipt.get("asset_activity_correction_receipt_version") != 2 or
                          receipt.get("batch_predecessors") != trusted_preview["batch_predecessors"] or
                          receipt.get("confirmation_fingerprint") != confirmation["confirmation_fingerprint"]):
                _abort("asset_activity_correction_receipt_invalid")
            if receipt.get("context_fingerprint") != _context_fingerprint(context):
                _abort("asset_activity_correction_receipt_invalid")
            binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
            if binding.get("generation_ref") == receipt["generation_ref"]:
                status = "already_committed"
            elif binding.get("generation_ref") == receipt["prior_generation_ref"]:
                manifest = _read_json(final / MANIFEST_NAME, "asset_activity_correction_receipt_invalid")
                ledger = _correction_file(final / LEDGER_NAME, "asset_activity_correction_receipt_invalid")
                if manifest.get("generation_ref") != receipt["generation_ref"] or manifest.get("activity_set_fingerprint") != receipt["activity_set_fingerprint"] or _sha_file(ledger) != manifest.get("ledger_fingerprint"):
                    _abort("asset_activity_correction_receipt_invalid")
                if batch:
                    with _CanonicalReadBarrierV1(data_space):
                        if _sha_file(canonical) != trusted_preview["canonical_fingerprint"]:
                            _abort("asset_activity_correction_preview_stale")
                        _atomic_json_replace(area / ACTIVE_NAME, {"contract_version": 1, "generation_ref": receipt["generation_ref"], "ledger_fingerprint": manifest["ledger_fingerprint"], "manifest_fingerprint": _sha_file(final / MANIFEST_NAME)})
                else:
                    _atomic_json_replace(area / ACTIVE_NAME, {"contract_version": 1, "generation_ref": receipt["generation_ref"], "ledger_fingerprint": manifest["ledger_fingerprint"], "manifest_fingerprint": _sha_file(final / MANIFEST_NAME)})
                status = "recovered_committed"
            else:
                if batch: _abort("asset_activity_correction_generation_conflict")
                current = _read_connection(Path(binding["ledger_path"]))
                try: predecessor_count = current.execute("SELECT count(*) FROM current_asset_activity_event WHERE event_ref=?", (receipt["predecessor_event_ref"],)).fetchone()[0]
                finally: current.close()
                if predecessor_count != 0: _abort("asset_activity_correction_generation_conflict")
                status = "already_committed"
            return DesktopAssetActivityCorrectionResultV1(status, receipt["action_type"], receipt["generation_ref"], True, receipt["replacement_event_count"], receipt["total_asset_activity_event_count"])
        if recovery_confirmation is None:
            _attempt(area, confirmation, context, committed)
        if failpoint == "after_attempt": _abort("synthetic_asset_activity_correction_failpoint")
        with _CanonicalReadBarrierV1(data_space): canonical_snapshot = _canonical_snapshot(canonical, context)
        binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
        if binding.get("generation_ref") != trusted_preview.get("source_generation_ref") or binding.get("activity_set_fingerprint") != trusted_preview.get("source_activity_set_fingerprint") or canonical_snapshot["source_fingerprint"] != trusted_preview.get("canonical_fingerprint"):
            _abort("asset_activity_correction_preview_stale")
        expected_predecessors = trusted_preview.get("batch_predecessors") if batch else [{"event_ref": trusted_preview["predecessor_event_ref"], "effect_fingerprint": trusted_preview["predecessor_effect_fingerprint"]}]
        if not isinstance(expected_predecessors, list) or not expected_predecessors: _abort("asset_activity_correction_input_invalid")
        predecessors = []
        for expected in expected_predecessors:
            row = _predecessor(Path(binding["ledger_path"]), expected["event_ref"])
            if row["effect_fingerprint"] != expected["effect_fingerprint"]: _abort("asset_activity_correction_preview_stale")
            predecessors.append(row)
        if batch and (not 2 <= len(predecessors) <= 1000 or [row["event_ref"] for row in predecessors] != sorted(set(row["event_ref"] for row in predecessors))):
            _abort("asset_activity_correction_input_invalid")
        predecessor = predecessors[0]
        generations = _correction_directory(area / "generations", create=True); _remove_staging_generations(generations)
        staging = generations / (".staging-correction-" + secrets.token_hex(16)); os.mkdir(staging, 0o700); os.chmod(staging, 0o700)
        published = False
        try:
            target = staging / LEDGER_NAME
            materialized = materialize_desktop_product_semantic_ledger_v1(canonical, Path(binding["ledger_path"]), target, context)
            _remove_predecessor(target, [row["event_ref"] for row in predecessors] if batch else predecessor["event_ref"])
            replacement = trusted_preview.get("replacement_event")
            schema_preview = None; command_id = "cmd_correction_" + trusted_preview["plan_fingerprint"][:47]
            if replacement is not None:
                try: schema_preview = preview_schema400_asset_activity_v1(target, _compat_context(context), predecessor["portfolio_id"], [replacement])
                except (Schema400AssetActivityCompatV1Error, AssetActivityV1Error): _abort("asset_activity_correction_preview_stale")
                if schema_preview["preview_fingerprint"] != trusted_preview.get("replacement_preview_fingerprint"): _abort("asset_activity_correction_preview_stale")
                schema_confirmation = build_schema400_asset_activity_confirmation_v1(schema_preview, _compat_context(context), "sac_" + confirmation["confirmation_fingerprint"][:32], committed, committed, _offset(committed, 300))
                authorizer = OneUseSchema400AssetActivityAuthorizerV1(); authorizer.register(schema_confirmation)
                try: applied = apply_schema400_asset_activity_v1(target, _compat_context(context), predecessor["portfolio_id"], [replacement], schema_confirmation, authorizer, committed)
                except Schema400AssetActivityCompatV1Error: _abort("asset_activity_correction_preview_stale")
                command_id = applied.command_id
            fifo = _fifo_worlds(target, splits=_correction_splits(data_space, context))
            if fifo != trusted_preview.get("fifo_world_result_fingerprints"): _abort("asset_activity_correction_preview_stale")
            connection = _read_connection(target)
            try: activity = _activity_rows(connection)
            finally: connection.close()
            ledger_fingerprint = _sha_file(target)
            generation_ref = "gen_" + _fingerprint({"prior_generation_ref": binding["generation_ref"], "plan_fingerprint": trusted_preview["plan_fingerprint"], "activity_set_fingerprint": activity["activity_set_fingerprint"], "committed_at_utc": committed})[:32]
            receipt_body = {"asset_activity_correction_receipt_version": 1, "action_type": trusted_preview["action_type"], "context_fingerprint": _context_fingerprint(context), "plan_fingerprint": trusted_preview["plan_fingerprint"], "confirmation_fingerprint": confirmation["confirmation_fingerprint"], "prior_generation_ref": binding["generation_ref"], "generation_ref": generation_ref, "predecessor_event_ref": predecessor["event_ref"], "predecessor_effect_fingerprint": predecessor["effect_fingerprint"], "replacement_event_ref": None if replacement is None else replacement["event_ref"], "replacement_event_count": 0 if replacement is None else 1, "total_asset_activity_event_count": len(activity["asset_activity_events"]), "activity_set_fingerprint": activity["activity_set_fingerprint"], "fifo_world_result_fingerprints": fifo, "committed_at_utc": committed, "predecessor_preserved": True, "schema201_canonical_write": False, "cash_posting_count": 0, "provider_access": False, "network_access": False}
            if batch:
                receipt_body["asset_activity_correction_receipt_version"] = 2
                receipt_body["batch_predecessors"] = expected_predecessors
            receipt_body["receipt_fingerprint"] = _fingerprint(receipt_body)
            manifest = {"contract_version": 1, "authority_contract": "schema201_derived_base_plus_asset_activity_v1", "context_fingerprint": _context_fingerprint(context), "generation_ref": generation_ref, "canonical_schema_version": materialized["canonical_schema_version"], "canonical_fingerprint": materialized["canonical_fingerprint"], "prior_activity_set_fingerprint": binding["activity_set_fingerprint"], "activity_set_fingerprint": activity["activity_set_fingerprint"], "ledger_schema_version": 401, "ledger_fingerprint": ledger_fingerprint, "plan_fingerprint": trusted_preview["plan_fingerprint"], "command_id": command_id, "new_event_count": 0 if replacement is None else 1, "total_asset_activity_event_count": len(activity["asset_activity_events"]), "committed_at_utc": committed, "semantic_contracts": ["portfolio_ledger_v1_transaction_fact", "asset_activity_v1"], "boundaries": {"schema201_catalog_authority": "derived_read_only", "schema201_transaction_authority": "derived_read_only", "asset_activity_authority": "data_app_append_only_generation_supersession", "automatic_cash_posting_count": 0, "provider_access": False, "network_access": False}}
            _write_new_file(staging / CORRECTION_NAME, _canonical(receipt_body) + b"\n"); _write_new_file(staging / MANIFEST_NAME, _canonical(manifest) + b"\n"); _write_new_file(staging / SUCCESS_NAME, b"completed\n")
            if failpoint == "after_generation_complete": _abort("synthetic_asset_activity_correction_failpoint")
            final = generations / generation_ref
            if final.exists(): _abort("asset_activity_correction_generation_conflict")
            settle_new_directory_v1(staging); os.rename(staging, final); published = True  # #568: diriv neuer Ordner festschreiben
            if failpoint == "after_generation_publish": _abort("synthetic_asset_activity_correction_failpoint")
            with _CanonicalReadBarrierV1(data_space):
                if _sha_file(canonical) != materialized["canonical_fingerprint"]: _abort("asset_activity_correction_preview_stale")
                if failpoint == "before_active_replace": _abort("synthetic_asset_activity_correction_failpoint")
                _atomic_json_replace(area / ACTIVE_NAME, {"contract_version": 1, "generation_ref": generation_ref, "ledger_fingerprint": ledger_fingerprint, "manifest_fingerprint": _sha_file(final / MANIFEST_NAME)})
            if failpoint == "after_active_replace": _abort("synthetic_asset_activity_correction_failpoint")
            verified = read_desktop_product_asset_activity_binding_v1(data_space, context)
            if verified["generation_ref"] != generation_ref or verified["activity_set_fingerprint"] != activity["activity_set_fingerprint"]: _abort("asset_activity_correction_publication_failed")
            return DesktopAssetActivityCorrectionResultV1("committed", trusted_preview["action_type"], generation_ref, True, 0 if replacement is None else 1, len(activity["asset_activity_events"]))
        finally:
            if not published and staging.exists(): shutil.rmtree(staging, ignore_errors=True)


def read_desktop_asset_activity_correction_candidates_v1(data_space_path: str | Path, context_value: Any) -> dict[str, Any]:
    context = _runtime(context_value); data_space = _correction_directory(data_space_path)
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding.get("status") != "available":
        return {"status": "absent", "generation_ref": None, "candidates": []}
    connection = _read_connection(Path(binding["ledger_path"]))
    try:
        rows = [dict(row) for row in connection.execute(
            "SELECT event.*,portfolio.display_name AS portfolio_label,account.display_name AS account_label,"
            "related.display_name AS related_account_label,asset.display_name AS asset_label,source.display_name AS source_asset_label "
            "FROM current_asset_activity_event event "
            "JOIN current_portfolio_revision portfolio ON portfolio.portfolio_id=event.portfolio_id "
            "JOIN current_account_revision account ON account.account_id=event.account_id "
            "LEFT JOIN current_account_revision related ON related.account_id=event.related_account_id "
            "JOIN current_asset_revision asset ON asset.asset_id=event.asset_id "
            "LEFT JOIN current_asset_revision source ON source.asset_id=event.source_asset_id "
            "ORDER BY event.local_date DESC,COALESCE(event.effective_at_utc,'') DESC,event.event_ref DESC"
        )]
    except sqlite3.Error: _abort("asset_activity_correction_storage_invalid")
    finally: connection.close()
    candidates = []
    for row in rows:
        candidate_ref = "acr_" + _fingerprint({"context_fingerprint": _context_fingerprint(context), "generation_ref": binding["generation_ref"], "event_ref": row["event_ref"]})[:32]
        candidates.append({
            "candidate_ref": candidate_ref,
            "event_ref": row["event_ref"],
            "portfolio_ref": row["portfolio_id"],
            "event": _event_from_row(row),
            "public": {
                "candidate_ref": candidate_ref, "portfolio_label": row["portfolio_label"],
                "account_label": row["account_label"], "related_account_label": row["related_account_label"],
                "asset_label": row["asset_label"], "source_asset_label": row["source_asset_label"],
                "event_type": row["event_type"], "local_date": row["local_date"],
                "effective_at_utc": row["effective_at_utc"], "quantity_decimal": row["quantity_decimal"],
                "gross_amount_decimal": row["gross_economic_amount_decimal"],
                "monetary_fee_decimal": row["monetary_fee_decimal"],
                # Waehrung von Betrag und Gebuehr, damit die Tabelle sie mit Einheit zeigt (#529 Punkt 8).
                "currency": row["basis_currency"],
            },
        })
    return {"status": "available", "generation_ref": binding["generation_ref"], "candidates": candidates}


def _correction_chain(data_space: Path, context: DesktopProductAssetActivityContextV1) -> tuple[dict[str, str], dict[str, str], set[str]]:
    """Nachfolger je korrigierter Buchung, Storno-Zeitpunkt je stornierter Buchung und die stehenden Buchungen. Liest nur.

    Belege jedes Bearbeiters dieses Datenraums zaehlen (ein Sammelstorno traegt mitunter einen anderen Bearbeiter); ein
    unlesbarer Beleg wird uebergangen."""
    generations = data_space / PRODUCT_AREA / "generations"
    if generations.is_symlink() or not generations.is_dir():
        return {}, {}, set()
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding.get("status") != "available":
        return {}, {}, set()
    connection = _read_connection(Path(binding["ledger_path"]))
    try:
        live = {row[0] for row in connection.execute("SELECT event_ref FROM current_asset_activity_event")}
    finally:
        connection.close()
    successor: dict[str, str] = {}
    voided: dict[str, str] = {}
    # Nur die direkten Generationsordner; ihr Beleg liegt immer obenauf.
    for path in generations.iterdir():
        receipt = path / CORRECTION_NAME
        if path.is_symlink() or not path.is_dir() or receipt.is_symlink() or not receipt.is_file():
            continue
        try:
            value = json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(value, Mapping):
            continue
        predecessor = value.get("predecessor_event_ref")
        if value.get("action_type") == "correct" and isinstance(predecessor, str) and isinstance(value.get("replacement_event_ref"), str):
            successor[predecessor] = value["replacement_event_ref"]
        elif value.get("action_type") == "void" and isinstance(value.get("committed_at_utc"), str):
            batch = value.get("batch_predecessors") if isinstance(value.get("batch_predecessors"), list) else []
            for ref in [predecessor] + [item.get("event_ref") for item in batch if isinstance(item, Mapping)]:
                if isinstance(ref, str):
                    voided[ref] = value["committed_at_utc"]
    return successor, voided, live


def _chain_end(successor: Mapping[str, str], ref: str) -> str:
    seen: set[str] = set()
    while ref in successor and ref not in seen:
        seen.add(ref); ref = successor[ref]
    return ref


def read_desktop_asset_activity_voided_event_refs_v1(data_space_path: str | Path, context_value: Any) -> dict[str, str]:
    """Buchungen, die storniert sind - direkt oder am Ende ihrer Korrekturkette -, mit dem Zeitpunkt des Stornos. Liest nur.

    Ein gebuchter Entwurf behaelt die Kennung der Buchung, die er geschrieben hat. Eine Korrektur ersetzt sie durch eine neue
    Kennung, ein Storno nimmt sie zurueck. Wer wissen will, ob ein gebuchter Entwurf noch gilt, folgt dieser Kette (#509: nach
    einem Storno zaehlte der Reward-Import die Zeile weiter als gebucht).

    Belege jedes Bearbeiters dieses Datenraums zaehlen: Ein Sammelstorno traegt mitunter einen anderen
    Bearbeiter als die Oberflaeche, gilt aber. Massgeblich ist, dass die Buchung in der aktiven Generation fehlt - sonst zaehlt
    der Storno nicht. Ein unlesbarer Beleg wird uebergangen; die Buchung gilt dann weiter als gebucht. Das ist der sichere
    Fehler, denn er bucht nichts doppelt.
    """
    context = _runtime(context_value)
    successor, voided, live = _correction_chain(Path(data_space_path), context)
    result = {ref: at for ref, at in voided.items() if ref not in live}
    for start in successor:
        end = _chain_end(successor, start)
        if end in result and start not in live:
            result[start] = result[end]
    return result


def resolve_desktop_asset_activity_live_event_refs_v1(data_space_path: str | Path, context_value: Any, event_refs: Sequence[str]) -> dict[str, str | None]:
    """Je Kennung die stehende Buchung am Ende ihrer Korrekturkette, oder None, wenn sie storniert ist oder fehlt. Liest nur."""
    context = _runtime(context_value)
    if not isinstance(event_refs, (list, tuple)) or any(not isinstance(ref, str) for ref in event_refs):
        _abort("asset_activity_correction_input_invalid")
    if not event_refs:
        return {}
    successor, _, live = _correction_chain(Path(data_space_path), context)
    if not live:
        binding = read_desktop_product_asset_activity_binding_v1(Path(data_space_path), context)
        if binding.get("status") == "available":
            connection = _read_connection(Path(binding["ledger_path"]))
            try:
                live = {row[0] for row in connection.execute("SELECT event_ref FROM current_asset_activity_event")}
            finally:
                connection.close()
    result: dict[str, str | None] = {}
    for ref in event_refs:
        end = _chain_end(successor, ref)
        result[ref] = end if end in live else None
    return result


def read_desktop_asset_activity_correction_history_v1(data_space_path: str | Path, context_value: Any) -> dict[str, Any]:
    context = _runtime(context_value); data_space = _correction_directory(data_space_path)
    empty = {"asset_activity_correction_history_version": 1, "status": "available", "correction_count": 0, "rows": [], "foreign_receipt_count": 0, "path_exposed": False, "internal_id_exposed": False, "provider_access": False, "network_access": False, "canonical_write": False}
    # A fresh data space has no Activity generation yet. This is an empty
    # correction history, not a storage error, and the read must not create it.
    if read_desktop_product_asset_activity_binding_v1(data_space, context).get("status") != "available":
        return empty
    area = _correction_directory(data_space / PRODUCT_AREA)
    rows = []
    foreign = 0
    generations = _correction_directory(area / "generations")
    own = _context_fingerprint(context)
    for path in sorted(generations.iterdir()):
        receipt = path / CORRECTION_NAME
        if path.is_dir() and not path.is_symlink() and receipt.exists():
            value = _read_json(receipt, "asset_activity_correction_receipt_invalid")
            # Ein Beleg aus einem fremden Kontext wird gezaehlt, nicht verschwiegen -
            # und er sperrt die Ansicht nicht. Vorher brach die ganze Historie beim
            # ersten solchen Beleg ab, und damit auch die Buchungsauswahl, die sie
            # mitlaedt: ein einzelner Protokolleintrag machte das Korrigieren
            # unbenutzbar, ohne den Grund zu nennen (07.10.2026). Der Beleg selbst
            # bleibt unveraendert; er gehoert zur Historie, auch wenn er falsch
            # gebildet wurde.
            if value.get("context_fingerprint") != own:
                foreign += 1
                continue
            rows.append({"action_type": value["action_type"], "selected_event_count": len(value['batch_predecessors']) if value.get('asset_activity_correction_receipt_version') == 2 else 1, "committed_at_utc": value["committed_at_utc"], "replacement_event_count": value["replacement_event_count"], "predecessor_preserved": True})
    rows.sort(key=lambda row: row["committed_at_utc"], reverse=True)
    return {"asset_activity_correction_history_version": 1, "status": "available", "correction_count": len(rows), "rows": rows, "foreign_receipt_count": foreign, "path_exposed": False, "internal_id_exposed": False, "provider_access": False, "network_access": False, "canonical_write": False}


def reconcile_desktop_asset_activity_multi_void_v2(data_space_path, context_value, trusted_preview, confirmation):
    """Observe an already active batch receipt; never activate or retry a write.

    Historical confirmation may have expired. It identifies the completed attempt,
    but grants no present write authority. Inactive/absent/advanced heads block.
    """
    context = _runtime(context_value)
    preview_body = dict(trusted_preview); plan = preview_body.pop("plan_fingerprint", None)
    confirmation_body = dict(confirmation); grant = confirmation_body.pop("confirmation_fingerprint", None)
    if (trusted_preview.get("asset_activity_correction_preview_version") != 2 or
        plan != _fingerprint(preview_body) or grant != _fingerprint(confirmation_body) or
        trusted_preview.get("context_fingerprint") != _context_fingerprint(context) or
        confirmation.get("context_fingerprint") != _context_fingerprint(context) or
        confirmation.get("plan_fingerprint") != plan):
        _abort("asset_activity_correction_confirmation_invalid")
    data_space = _correction_directory(data_space_path)
    area = _correction_directory(data_space / PRODUCT_AREA)
    with _ProductWriterLockV1(area):
        candidates = _receipt_candidates(area, plan)
        if len(candidates) != 1: _abort("asset_activity_correction_receipt_invalid")
        final, receipt = candidates[0]
        if (receipt.get("asset_activity_correction_receipt_version") != 2 or
            receipt.get("context_fingerprint") != _context_fingerprint(context) or
            receipt.get("confirmation_fingerprint") != grant or
            receipt.get("batch_predecessors") != trusted_preview.get("batch_predecessors")):
            _abort("asset_activity_correction_receipt_invalid")
        binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
        if binding.get("generation_ref") != final.name:
            _abort("asset_activity_correction_generation_conflict")
        result = DesktopAssetActivityCorrectionResultV1(
            "recovered_committed", "void", final.name, False, 0,
            receipt["total_asset_activity_event_count"],
        )
        return {**vars(result), 'committed_at_utc': receipt['committed_at_utc']}


__all__ = ["reconcile_desktop_asset_activity_multi_void_v2", "preview_desktop_asset_activity_multi_void_v2", "apply_desktop_asset_activity_multi_void_v2", "DesktopAssetActivityCorrectionResultV1", "DesktopAssetActivityCorrectionV1Error", "apply_desktop_asset_activity_correction_v1", "build_desktop_asset_activity_correction_confirmation_v1", "desktop_asset_activity_correction_v1_error_codes", "preview_desktop_asset_activity_correction_v1", "read_desktop_asset_activity_correction_candidates_v1", "read_desktop_asset_activity_correction_history_v1", "read_desktop_asset_activity_voided_event_refs_v1", "resolve_desktop_asset_activity_live_event_refs_v1"]
