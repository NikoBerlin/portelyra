"""Persistent world-scoped FIFO-v2 materialization with Full-rebuild parity."""
from __future__ import annotations

from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _context,
    _owner_directory,
    _owner_file,
    read_desktop_product_asset_activity_binding_v1,
)
from migrations.reference.crypto_valuation_method_v1 import (
    CryptoValuationMethodV1Error,
    valuation_methods_for_fifo_v1,
)
from migrations.reference.fifo_wallet_v1 import (
    FifoWalletV1Error,
    fifo_wallets_for_fifo_v1,
)
from migrations.reference.stock_split_v1 import StockSplitV1Error, splits_for_fifo_v1
from workers.reference.semantic_realized_fifo_v2 import (
    SemanticRealizedFifoV2Error,
    project_semantic_realized_fifo_lot_trace_v2,
    project_semantic_realized_fifo_v2,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts/realized-materialization/v2/schema.sql"
FIFO_SOURCE = ROOT / "workers/reference/semantic_realized_fifo_v2.py"
FIFO_SHA256 = "c8499b00a134be35387c91840bff163b01929e1399ecc9e16c86550ffb3165f7"
SCHEMA_VERSION = 3100
AREA_NAME = "realized-state-v2"
STORE_NAME = "realized-state.sqlite"
LOCK_NAME = "writer.lock"
MODES = frozenset({"incremental", "full_rebuild"})
COMPLETENESS = frozenset({"complete", "incomplete_quarantined_or_derivative_blocked"})
FP = re.compile(r"^[a-f0-9]{64}$")
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
FAILPOINTS = frozenset({None, "after_job", "after_world_artifacts", "before_completion"})
EVENT_COLUMNS = (
    "event_ref", "event_type", "account_ref", "related_account_ref", "asset_ref",
    "source_asset_ref", "event_time_evidence", "local_date", "local_time", "time_zone",
    "effective_at_utc", "original_acquired_time_evidence", "original_acquired_local_date",
    "original_acquired_local_time", "original_acquired_time_zone", "original_acquired_at_utc",
    "amount_input_mode", "basis_evidence_mode", "quantity_decimal", "eligible_quantity_decimal",
    "unit_price_decimal", "gross_amount_decimal", "monetary_fee_decimal",
    "asset_fee_quantity_decimal", "provided_basis_decimal", "movement_context_code",
)
FAILURE_CODES = frozenset({
    "asset_activity_state_algorithm_changed",
    "asset_activity_state_boundary_failed",
    "asset_activity_state_context_invalid",
    "asset_activity_state_full_rebuild_mismatch",
    "asset_activity_state_input_invalid",
    "asset_activity_state_job_conflict",
    "asset_activity_state_ledger_invalid",
    "asset_activity_state_lock_unavailable",
    "asset_activity_state_source_invalid",
    "asset_activity_state_source_stale",
    "asset_activity_state_store_invalid",
    "asset_activity_state_write_failed",
    "synthetic_asset_activity_state_failpoint",
})


class AssetActivityRealizedStateV2Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("asset_activity_state_error_code_unregistered")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class AssetActivityRealizedStateV2Result:
    status: str
    source_generation_ref: str
    global_artifact_ref: str
    world_count: int
    changed_world_count: int
    reused_world_count: int
    request_mode: str
    full_rebuild_verified: bool
    canonical_write: bool = False
    cash_imported: bool = False
    provider_access: bool = False
    network_access: bool = False


def asset_activity_realized_state_v2_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise AssetActivityRealizedStateV2Error(code)


def _state_owner_file(path: str | Path, code: str) -> Path:
    try:return _owner_file(path,"desktop_asset_activity_storage_invalid")
    except DesktopProductAssetActivityV1Error:_abort(code)


def _state_owner_directory(path: str | Path, *, create: bool=False, code: str="asset_activity_state_store_invalid") -> Path:
    try:return _owner_directory(path,create=create)
    except DesktopProductAssetActivityV1Error:_abort(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except Exception:
        _abort("asset_activity_state_input_invalid")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha_file(path: Path, code: str) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        _abort(code)


def _utc(value: Any) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("asset_activity_state_input_invalid")
    try:
        from datetime import datetime, timezone
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort("asset_activity_state_input_invalid")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _abort("asset_activity_state_input_invalid")
    return value


def _product_context(value: Any) -> DesktopProductAssetActivityContextV1:
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("asset_activity_state_context_invalid")


def _uri(path: Path, mode: str, immutable: bool = False) -> str:
    return f"file:{quote(str(path))}?mode={mode}" + ("&immutable=1" if immutable else "")


def _schema_signature(connection: sqlite3.Connection) -> tuple[tuple[Any, ...], ...]:
    return tuple(tuple(row) for row in connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND sql IS NOT NULL ORDER BY type,name"
    ))


_EXPECTED_SCHEMA: tuple[tuple[Any, ...], ...] | None = None


def _expected_schema() -> tuple[tuple[Any, ...], ...]:
    global _EXPECTED_SCHEMA
    if _EXPECTED_SCHEMA is None:
        connection = sqlite3.connect(":memory:")
        try:
            connection.executescript(SCHEMA.read_text(encoding="utf-8"))
            _EXPECTED_SCHEMA = _schema_signature(connection)
        except (OSError, sqlite3.Error):
            _abort("asset_activity_state_store_invalid")
        finally:
            connection.close()
    return _EXPECTED_SCHEMA


def _validate_algorithm() -> None:
    if _sha_file(FIFO_SOURCE, "asset_activity_state_algorithm_changed") != FIFO_SHA256:
        _abort("asset_activity_state_algorithm_changed")


def _area(data_space_path: str | Path, *, create: bool) -> Path:
    data_space = _state_owner_directory(data_space_path,code="asset_activity_state_source_invalid")
    area = data_space / AREA_NAME
    if create and not area.exists():
        try: os.mkdir(area, 0o700); os.chmod(area, 0o700)
        except OSError: _abort("asset_activity_state_store_invalid")
    if not area.exists():
        _abort("asset_activity_state_store_invalid")
    return _state_owner_directory(area,code="asset_activity_state_store_invalid")


def _store_path(data_space_path: str | Path) -> Path:
    return Path(data_space_path) / AREA_NAME / STORE_NAME


def _validate_portfolio_completeness(data_space: Path, requested: str) -> str:
    receipt_path=data_space/"noncash-canonical-cutover-v1"/"receipt.json"
    if not receipt_path.exists():
        return requested
    receipt_path=_state_owner_file(receipt_path,"asset_activity_state_source_invalid")
    try:receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
    except Exception:_abort("asset_activity_state_source_invalid")
    body=dict(receipt);fingerprint=body.pop("receipt_fingerprint",None)
    if (
        receipt_path.read_bytes()!=_canonical(receipt)+b"\n" or fingerprint!=_fingerprint(body)
        or receipt.get("status")!="completed_incomplete_portfolio" or receipt.get("cash_imported") is not False
        or receipt.get("complete_portfolio_claim_authorized") is not False
        or receipt.get("portfolio_completeness")!="incomplete_quarantined_or_derivative_blocked"
        or requested!=receipt["portfolio_completeness"]
    ):
        _abort("asset_activity_state_source_invalid")
    return requested


def _validate_store(connection: sqlite3.Connection, context: DesktopProductAssetActivityContextV1) -> None:
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id,algorithm_id,algorithm_fingerprint FROM realized_state_binding WHERE singleton_id=1"
        ).fetchall()
        if (
            connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION
            or _schema_signature(connection) != _expected_schema()
            or len(binding) != 1
            or tuple(binding[0]) != (
                SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id,
                "semantic_realized_fifo_v2", FIFO_SHA256,
            )
            or connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
            or connection.execute("PRAGMA foreign_key_check").fetchall()
        ):
            _abort("asset_activity_state_store_invalid")
        for artifact in connection.execute("SELECT * FROM realized_world_artifact ORDER BY world_artifact_ref"):
            result=json.loads(artifact["result_json"]);result_body=dict(result);result_fingerprint=result_body.pop("result_fingerprint",None)
            stored_source=json.loads(artifact["source_activity_json"])
            activity, wrapper = _stored_wrapper(stored_source)
            artifact_body={
                "job_ref":artifact["job_ref"],"world_ref":artifact["world_ref"],"portfolio_ref":artifact["portfolio_ref"],
                "asset_ref":artifact["asset_ref"],"calculation_mode":artifact["calculation_mode"],
                "prior_world_artifact_ref":artifact["prior_world_artifact_ref"],"earliest_changed_order_key":artifact["earliest_changed_order_key"],
                "source_event_count":artifact["source_event_count"],"source_input_fingerprint":artifact["source_input_fingerprint"],
                "result_fingerprint":artifact["result_fingerprint"],"table_fingerprint":artifact["table_fingerprint"],
                "completed_at_utc":artifact["completed_at_utc"],
            }
            result_table = _result_table_projection(result)
            stored_table = _stored_result_table_projection(connection, artifact["world_artifact_ref"])
            corrected_table_fingerprint = _fingerprint(result_table)
            legacy_table_fingerprint = _fingerprint(_legacy_result_table_projection(result))
            event_sequences = sorted(
                (row["event_sequence"] for row in result["event_results"]), key=int
            )
            legacy_order_applicable = (
                len(event_sequences) >= 10
                and event_sequences == [str(sequence) for sequence in range(1, len(event_sequences) + 1)]
            )
            table_fingerprint_compatible = artifact["table_fingerprint"] == corrected_table_fingerprint
            if legacy_order_applicable and legacy_table_fingerprint != corrected_table_fingerprint:
                table_fingerprint_compatible = table_fingerprint_compatible or (
                    artifact["table_fingerprint"] == legacy_table_fingerprint
                )
            if (
                _canonical(result).decode("utf-8")!=artifact["result_json"]
                or _canonical(stored_source).decode("utf-8")!=artifact["source_activity_json"]
                or result_fingerprint!=artifact["result_fingerprint"] or _fingerprint(result_body)!=result_fingerprint
                or _fingerprint(wrapper)!=artifact["source_input_fingerprint"]
                or not table_fingerprint_compatible
                or result_table != stored_table
                or _fingerprint(artifact_body)!=artifact["artifact_fingerprint"]
            ):
                _abort("asset_activity_state_store_invalid")
    except AssetActivityRealizedStateV2Error:
        raise
    except (KeyError, TypeError, ValueError, sqlite3.Error):
        _abort("asset_activity_state_store_invalid")


_ENVELOPE_V1 = {"source_activity_envelope_version", "asset_activity", "fifo_order_evidence"}
_ENVELOPE_V2 = _ENVELOPE_V1 | {"valuation_methods"}
# Umschlag 3 (#508): zusaetzlich die FIFO-Wallet aus mehreren Konten; die Wahl der Wertermittlung darf dann leer sein.
_ENVELOPE_V3 = _ENVELOPE_V2 | {"fifo_wallets"}
# Umschlag 4 (#451): zusaetzlich die Splits; Wahl und FIFO-Wallet duerfen dann leer sein.
_ENVELOPE_V4 = _ENVELOPE_V3 | {"splits"}


def _stored_wrapper(stored_source: Any) -> tuple[Any, dict[str, Any]]:
    """Buchungen und Eingabe des Kerns aus dem gespeicherten Quellstand einer Welt.

    Drei Formen: die Buchungen allein; Umschlag 1 mit bestaetigter Reihenfolge; Umschlag 2 (rc.294) zusaetzlich mit der
    Wertermittlung je Wallet. Eine Welt ohne Wahl wird wie bisher gespeichert - ihr Abdruck bleibt gleich."""
    wrapper: dict[str, Any] = {"realized_fifo_version": 2, "source_contract": "asset_activity_v1"}
    if isinstance(stored_source, dict) and stored_source.get("source_activity_envelope_version") == 1:
        if set(stored_source) != _ENVELOPE_V1:
            _abort("asset_activity_state_store_invalid")
        wrapper.update({"asset_activity": stored_source["asset_activity"], "fifo_order_evidence": stored_source["fifo_order_evidence"]})
        return stored_source["asset_activity"], wrapper
    if isinstance(stored_source, dict) and stored_source.get("source_activity_envelope_version") == 2:
        if set(stored_source) != _ENVELOPE_V2 or not stored_source["valuation_methods"]:
            _abort("asset_activity_state_store_invalid")
        wrapper["asset_activity"] = stored_source["asset_activity"]
        if stored_source["fifo_order_evidence"] is not None:
            wrapper["fifo_order_evidence"] = stored_source["fifo_order_evidence"]
        wrapper["valuation_methods"] = stored_source["valuation_methods"]
        return stored_source["asset_activity"], wrapper
    if isinstance(stored_source, dict) and stored_source.get("source_activity_envelope_version") == 3:
        if (set(stored_source) != _ENVELOPE_V3 or not stored_source["fifo_wallets"]
                or not isinstance(stored_source["valuation_methods"], list)):
            _abort("asset_activity_state_store_invalid")
        wrapper["asset_activity"] = stored_source["asset_activity"]
        if stored_source["fifo_order_evidence"] is not None:
            wrapper["fifo_order_evidence"] = stored_source["fifo_order_evidence"]
        if stored_source["valuation_methods"]:
            wrapper["valuation_methods"] = stored_source["valuation_methods"]
        wrapper["fifo_wallets"] = stored_source["fifo_wallets"]
        return stored_source["asset_activity"], wrapper
    if isinstance(stored_source, dict) and stored_source.get("source_activity_envelope_version") == 4:
        if (set(stored_source) != _ENVELOPE_V4 or not stored_source["splits"] or not isinstance(stored_source["valuation_methods"], list)
                or not isinstance(stored_source["fifo_wallets"], list)):
            _abort("asset_activity_state_store_invalid")
        wrapper["asset_activity"] = stored_source["asset_activity"]
        if stored_source["fifo_order_evidence"] is not None:
            wrapper["fifo_order_evidence"] = stored_source["fifo_order_evidence"]
        if stored_source["valuation_methods"]:
            wrapper["valuation_methods"] = stored_source["valuation_methods"]
        if stored_source["fifo_wallets"]:
            wrapper["fifo_wallets"] = stored_source["fifo_wallets"]
        wrapper["splits"] = stored_source["splits"]
        return stored_source["asset_activity"], wrapper
    wrapper["asset_activity"] = stored_source
    return stored_source, wrapper


def _world_methods(methods: Sequence[Mapping[str, Any]], asset_ref: str, activity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Die Wahlen, die eine Welt betreffen: ihr Asset, ein Konto mit Buchungen darin, nur Kryptowerte."""
    accounts = {item["account_ref"] for item in activity["accounts"]}
    crypto = any(item["asset_ref"] == asset_ref and item["asset_type"] == "crypto" for item in activity["assets"])
    if not crypto:
        return []
    return sorted((dict(item) for item in methods if item["asset_ref"] == asset_ref and item["account_ref"] in accounts),
                  key=lambda item: (item["account_ref"], item["valid_from_local_date"]))


def _world_wallets(wallets: Sequence[Mapping[str, Any]], asset_ref: str, activity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Die Zuordnungen, die eine Welt betreffen (#508): ein Unterkonto mit Buchungen darin, nur reine Krypto-Welten."""
    accounts = {item["account_ref"] for item in activity["accounts"]}
    if not activity["assets"] or any(item["asset_type"] != "crypto" for item in activity["assets"]):
        return []
    if not any(item["asset_ref"] == asset_ref for item in activity["assets"]):
        return []
    return sorted((dict(item) for item in wallets if item["account_ref"] in accounts), key=lambda item: item["account_ref"])


def _world_splits(splits: Sequence[Mapping[str, Any]], asset_ref: str, activity: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Die Splits, die eine Welt betreffen (#451): ihr Asset, fuer alle Konten oder ein Konto mit Buchungen darin."""
    accounts = {item["account_ref"] for item in activity["accounts"]}
    return sorted((dict(item) for item in splits if item["asset_ref"] == asset_ref and (item["account_ref"] is None or item["account_ref"] in accounts)),
                  key=lambda item: (item["effective_local_date"], item["split_ref"]))


def _source_splits(data_space_path: str | Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    try:
        return splits_for_fifo_v1(data_space_path, context)
    except StockSplitV1Error:
        _abort("asset_activity_state_source_invalid")
        return []


def _source_wallets(data_space_path: str | Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    try:
        return fifo_wallets_for_fifo_v1(data_space_path, context)
    except FifoWalletV1Error:
        _abort("asset_activity_state_source_invalid")
        return []


def _source_methods(data_space_path: str | Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    try:
        return valuation_methods_for_fifo_v1(data_space_path, context)
    except CryptoValuationMethodV1Error:
        _abort("asset_activity_state_source_invalid")
        return []


def _superseded_store(path: Path) -> bool:
    """Ein Stand, den ein anderer Rechenkern geschrieben hat.

    Der Stand ist abgeleitet und an den Kern gebunden, der ihn gerechnet hat; die
    Pruefung beim Oeffnen rechnet jede Welt nach. Aendert sich der Kern, kann
    kein gespeichertes Ergebnis mehr stimmen - der Stand ist dann nicht
    beschaedigt, sondern ueberholt, und wird beim naechsten Fortschreiben aus
    den Buchungen neu aufgebaut. Bis rc.244 gab es diesen Weg nicht: Ein
    geaenderter Kern haette jeden vorhandenen Stand als ungueltig abgewiesen und
    damit alles blockiert, was den Bestand liest (FIFO je Konto, 12.10.2026).
    Erkannt wird nur die saubere Bindung an einen anderen Kern; alles andere
    bleibt ein ungueltiger Speicher.
    """
    try:
        if not path.is_file() or path.is_symlink():
            return False
        connection = sqlite3.connect(_uri(path, "ro"), uri=True)
        try:
            rows = connection.execute(
                "SELECT algorithm_id,algorithm_fingerprint FROM realized_state_binding WHERE singleton_id=1").fetchall()
        finally:
            connection.close()
    except (sqlite3.Error, OSError):
        return False
    return (len(rows) == 1 and rows[0][0] == "semantic_realized_fifo_v2"
            and isinstance(rows[0][1], str) and re.fullmatch(r"[a-f0-9]{64}", rows[0][1]) is not None
            and rows[0][1] != FIFO_SHA256)


def _open_store(path: Path, context: DesktopProductAssetActivityContextV1, *, read_only: bool) -> sqlite3.Connection:
    store = _state_owner_file(path, "asset_activity_state_store_invalid")
    journal = Path(str(store) + "-journal")
    wal = Path(str(store) + "-wal")
    shared_memory = Path(str(store) + "-shm")
    if read_only and (journal.exists() or wal.exists() or shared_memory.exists()):
        _abort("asset_activity_state_store_invalid")
    if not read_only:
        if wal.exists() or shared_memory.exists():
            _abort("asset_activity_state_store_invalid")
        if journal.exists():
            _state_owner_file(journal, "asset_activity_state_store_invalid")
    try:
        connection = sqlite3.connect(_uri(store, "ro" if read_only else "rw", immutable=read_only), uri=True, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON"); connection.execute("PRAGMA busy_timeout=0")
        if read_only: connection.execute("PRAGMA query_only=ON")
        _validate_store(connection, context)
        return connection
    except AssetActivityRealizedStateV2Error:
        try: connection.close()
        except Exception: pass
        raise
    except sqlite3.Error:
        try: connection.close()
        except Exception: pass
        _abort("asset_activity_state_store_invalid")


def _create_store(path: Path, context: DesktopProductAssetActivityContextV1, created_at_utc: str) -> None:
    if path.exists() or path.is_symlink():
        _abort("asset_activity_state_store_invalid")
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}"
    try:
        connection = sqlite3.connect(temporary)
        connection.execute("PRAGMA foreign_keys=ON"); connection.execute("PRAGMA journal_mode=DELETE"); connection.execute("PRAGMA synchronous=FULL")
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO realized_state_binding VALUES(1,3100,?,?,?,'semantic_realized_fifo_v2',?,?)",
            (context.tenant_id, context.user_id, context.data_space_id, FIFO_SHA256, created_at_utc),
        )
        connection.commit(); _validate_store(connection, context); connection.close()
        os.chmod(temporary, 0o600)
        os.link(temporary, path); os.chmod(path, 0o600); temporary.unlink()
    except AssetActivityRealizedStateV2Error:
        try: connection.close()
        except Exception: pass
        temporary.unlink(missing_ok=True); raise
    except Exception:
        try: connection.close()
        except Exception: pass
        temporary.unlink(missing_ok=True); _abort("asset_activity_state_write_failed")


class _WriterLock:
    def __init__(self, area: Path): self.area = area; self.descriptor: int | None = None
    def __enter__(self):
        try:
            self.descriptor = os.open(self.area / LOCK_NAME, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
            metadata = os.fstat(self.descriptor)
            if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_uid != os.geteuid():
                _abort("asset_activity_state_store_invalid")
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB); return self
        except BlockingIOError: _abort("asset_activity_state_lock_unavailable")
        except AssetActivityRealizedStateV2Error: raise
        except OSError: _abort("asset_activity_state_lock_unavailable")
    def __exit__(self, *_):
        if self.descriptor is not None:
            fcntl.flock(self.descriptor, fcntl.LOCK_UN); os.close(self.descriptor); self.descriptor = None


def _event_order(
    event: Mapping[str, Any],
    order_evidence: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[Any, ...]:
    evidence = None if order_evidence is None else order_evidence.get(event["event_ref"])
    return (
        event["local_date"], event["effective_at_utc"] is not None,
        event["effective_at_utc"] or "", 0 if evidence is not None else 1,
        0 if evidence is None else evidence["source_row_ordinal"], event["event_ref"],
    )


def _order_key(event: Mapping[str, Any]) -> str:
    return "|".join((event["local_date"], "1" if event["effective_at_utc"] is not None else "0", event["effective_at_utc"] or "", event["event_ref"]))


def _ledger_worlds_v2(ledger_path: str | Path, methods: Sequence[Mapping[str, Any]] = (),
                      wallets: Sequence[Mapping[str, Any]] = (), splits: Sequence[Mapping[str, Any]] = ()) -> dict[str, dict[str, Any]]:
    """Reconstruct projectable FIFO-v2 worlds from one trusted immutable ledger."""
    ledger = _state_owner_file(ledger_path, "asset_activity_state_ledger_invalid")
    connection = sqlite3.connect(_uri(ledger, "ro", immutable=True), uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        accounts = {row["account_id"]: dict(row) for row in connection.execute(
            "SELECT entity.account_id,entity.portfolio_id,revision.account_type FROM account_entity entity JOIN current_account_revision revision USING(account_id) WHERE revision.status='active'"
        )}
        assets = {row["asset_id"]: dict(row) for row in connection.execute(
            "SELECT asset_id,asset_type,quantity_scale FROM current_asset_revision WHERE status='active'"
        )}
        rows = [dict(row) for row in connection.execute(
            "SELECT * FROM current_asset_activity_event ORDER BY portfolio_id,asset_id,local_date,COALESCE(effective_at_utc,''),event_ref"
        )]
        evidence_table = connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='asset_activity_fifo_order_evidence'"
        ).fetchone()[0]
        order_rows = [] if evidence_table == 0 else [
            dict(row) for row in connection.execute(
                "SELECT * FROM asset_activity_fifo_order_evidence ORDER BY event_ref"
            )
        ]
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or connection.execute("PRAGMA foreign_key_check").fetchall():
            _abort("asset_activity_state_ledger_invalid")
    except AssetActivityRealizedStateV2Error:
        raise
    except sqlite3.Error:
        _abort("asset_activity_state_ledger_invalid")
    finally:
        connection.close()
    row_refs = {row["event_ref"] for row in rows}
    if any(row.get("event_ref") not in row_refs for row in order_rows):
        _abort("asset_activity_state_ledger_invalid")
    order_by_ref = {row["event_ref"]: row for row in order_rows}
    if len(order_by_ref) != len(order_rows):
        _abort("asset_activity_state_ledger_invalid")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["portfolio_id"], row["asset_id"]), []).append(row)
    worlds: dict[str, dict[str, Any]] = {}
    for (portfolio_ref, asset_ref), world_rows in sorted(grouped.items()):
        basis = {row["basis_currency"] for row in world_rows}
        if len(basis) != 1 or asset_ref not in assets:
            _abort("asset_activity_state_ledger_invalid")
        account_refs = {row["account_id"] for row in world_rows} | {
            row["related_account_id"] for row in world_rows if row["related_account_id"] is not None
        }
        source_assets = {row["source_asset_id"] for row in world_rows if row["source_asset_id"] is not None}
        if not account_refs <= set(accounts) or not source_assets <= set(assets):
            _abort("asset_activity_state_ledger_invalid")
        event_rows = []
        for row in world_rows:
            event = {
                column: row[column]
                for column in EVENT_COLUMNS
                if column not in {"account_ref", "related_account_ref", "asset_ref", "source_asset_ref"}
            }
            event.update({
                "account_ref": row["account_id"], "related_account_ref": row["related_account_id"],
                "asset_ref": row["asset_id"], "source_asset_ref": row["source_asset_id"],
            })
            event_rows.append(event)
        world_order_evidence = {
            event["event_ref"]: order_by_ref[event["event_ref"]]
            for event in event_rows if event["event_ref"] in order_by_ref
        }
        event_rows.sort(key=lambda event: _event_order(event, world_order_evidence))
        asset_refs = {asset_ref} | source_assets
        activity = {
            "asset_activity_version": 1,
            "basis_currency": next(iter(basis)),
            "accounts": [
                {"account_ref": ref, "account_type": accounts[ref]["account_type"]}
                for ref in sorted(account_refs)
            ],
            "assets": [
                {"asset_ref": ref, "asset_type": assets[ref]["asset_type"], "quantity_scale": assets[ref]["quantity_scale"]}
                for ref in sorted(asset_refs)
            ],
            "events": event_rows,
        }
        world_ref = "rwd_" + _fingerprint({"portfolio_ref": portfolio_ref, "asset_ref": asset_ref})[:32]
        wrapper = {"realized_fifo_version": 2, "source_contract": "asset_activity_v1", "asset_activity": activity}
        if world_order_evidence:
            wrapper["fifo_order_evidence"] = [
                world_order_evidence[event_ref] for event_ref in sorted(world_order_evidence)
            ]
        chosen = _world_methods(methods, asset_ref, activity)
        if chosen:
            wrapper["valuation_methods"] = chosen
        joined = _world_wallets(wallets, asset_ref, activity)
        if joined:
            wrapper["fifo_wallets"] = joined
        divided = _world_splits(splits, asset_ref, activity)
        if divided:
            wrapper["splits"] = divided
        worlds[world_ref] = {
            "world_ref": world_ref, "portfolio_ref": portfolio_ref, "asset_ref": asset_ref,
            "activity": activity, "wrapper": wrapper,
            "source_input_fingerprint": _fingerprint(wrapper), "source_event_count": len(event_rows),
        }
    if not worlds:
        _abort("asset_activity_state_ledger_invalid")
    return worlds


def _source_worlds(data_space_path: str | Path, context: DesktopProductAssetActivityContextV1) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    try: binding = read_desktop_product_asset_activity_binding_v1(data_space_path, context)
    except DesktopProductAssetActivityV1Error: _abort("asset_activity_state_ledger_invalid")
    if binding.get("status") != "available" or binding.get("asset_activity_event_count", 0) < 1:
        _abort("asset_activity_state_ledger_invalid")
    ledger = _state_owner_file(binding["ledger_path"], "asset_activity_state_ledger_invalid")
    if _sha_file(ledger, "asset_activity_state_ledger_invalid") != binding["ledger_fingerprint"]:
        _abort("asset_activity_state_source_stale")
    return binding, _ledger_worlds_v2(ledger, _source_methods(data_space_path, context), _source_wallets(data_space_path, context),
                                      _source_splits(data_space_path, context))


def _current(connection: sqlite3.Connection) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]]]:
    global_rows = connection.execute("SELECT * FROM current_realized_global_artifact").fetchall()
    if not global_rows: return None, {}
    if len(global_rows) != 1: _abort("asset_activity_state_store_invalid")
    global_row = dict(global_rows[0])
    try: references = json.loads(global_row["world_artifacts_json"])
    except json.JSONDecodeError: _abort("asset_activity_state_store_invalid")
    if not isinstance(references, list) or len(references) != global_row["world_count"]:
        _abort("asset_activity_state_store_invalid")
    artifacts: dict[str, dict[str, Any]] = {}
    for item in references:
        if not isinstance(item, dict) or set(item) != {"world_ref", "world_artifact_ref", "result_fingerprint"}:
            _abort("asset_activity_state_store_invalid")
        rows = connection.execute("SELECT * FROM realized_world_artifact WHERE world_artifact_ref=?", (item["world_artifact_ref"],)).fetchall()
        if len(rows) != 1 or rows[0]["world_ref"] != item["world_ref"] or rows[0]["result_fingerprint"] != item["result_fingerprint"]:
            _abort("asset_activity_state_store_invalid")
        artifacts[item["world_ref"]] = dict(rows[0])
    return global_row, artifacts


def _decode_activity(row: Mapping[str, Any]) -> dict[str, Any]:
    try: value = json.loads(row["source_activity_json"])
    except Exception: _abort("asset_activity_state_store_invalid")
    if _canonical(value).decode("utf-8") != row["source_activity_json"]:
        _abort("asset_activity_state_store_invalid")
    return _stored_wrapper(value)[0]


def _stored_world_source(world: Mapping[str, Any]) -> dict[str, Any]:
    evidence = world["wrapper"].get("fifo_order_evidence")
    methods = world["wrapper"].get("valuation_methods")
    wallets = world["wrapper"].get("fifo_wallets")
    splits = world["wrapper"].get("splits")
    if splits:
        return {
            "source_activity_envelope_version": 4,
            "asset_activity": world["activity"],
            "fifo_order_evidence": evidence,
            "valuation_methods": methods or [],
            "fifo_wallets": wallets or [],
            "splits": splits,
        }
    if wallets:
        return {
            "source_activity_envelope_version": 3,
            "asset_activity": world["activity"],
            "fifo_order_evidence": evidence,
            "valuation_methods": methods or [],
            "fifo_wallets": wallets,
        }
    if methods:
        return {
            "source_activity_envelope_version": 2,
            "asset_activity": world["activity"],
            "fifo_order_evidence": evidence,
            "valuation_methods": methods,
        }
    if evidence is None:
        return world["activity"]
    return {
        "source_activity_envelope_version": 1,
        "asset_activity": world["activity"],
        "fifo_order_evidence": evidence,
    }


def _change_mode(prior: Mapping[str, Any] | None, world: Mapping[str, Any], request_mode: str) -> tuple[str, str | None]:
    events = world["activity"]["events"]
    if request_mode == "full_rebuild": return "full_rebuild", _order_key(events[0])
    if prior is None: return "initial_world_rebuild", _order_key(events[0])
    previous = _decode_activity(prior)["events"]
    common = 0
    for left, right in zip(previous, events):
        if left != right: break
        common += 1
    if common == len(previous) and len(events) > len(previous):
        return "incremental_append", _order_key(events[common])
    if common == len(previous) and common == len(events):
        return "affected_world_rebuild", _order_key(events[0])
    changed = events[common] if common < len(events) else previous[common]
    return "affected_world_rebuild", _order_key(changed)


def _project(world: Mapping[str, Any]) -> dict[str, Any]:
    try: return project_semantic_realized_fifo_v2(world["wrapper"])
    except SemanticRealizedFifoV2Error: _abort("asset_activity_state_full_rebuild_mismatch")


def _exact_json(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        _abort("asset_activity_state_full_rebuild_mismatch")
    return _canonical(value).decode("utf-8")


def _exact_display(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        _abort("asset_activity_state_store_invalid")
    status = value.get("exactness_status")
    if status == "exact_decimal":
        return value.get("decimal")
    if status == "exact_ratio":
        return value.get("numerator_integer") + "/" + value.get("denominator_integer")
    if status in {"basis_missing", "not_applicable"}:
        return None
    _abort("asset_activity_state_store_invalid")


def _result_table_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "event_results": sorted(result["event_results"], key=lambda row: int(row["event_sequence"])),
        "custody_positions": sorted(result["custody_positions"], key=lambda row: (row["account_ref"], row["asset_ref"])),
        "asset_positions": sorted(result["asset_positions"], key=lambda row: row["asset_ref"]),
        "remaining_lots": sorted(result["remaining_lots"], key=lambda row: row["lot_ref"]),
    }


def _legacy_result_table_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    """Reconstruct only the pre-ADR-132 lexicographic event-table seal."""
    return {
        **_result_table_projection(result),
        "event_results": sorted(result["event_results"], key=lambda row: row["event_sequence"]),
    }


def _stored_result_table_projection(connection: sqlite3.Connection, artifact_ref: str) -> dict[str, Any]:
    events = []
    for row in connection.execute("SELECT * FROM realized_event_result WHERE world_artifact_ref=? ORDER BY event_sequence", (artifact_ref,)):
        movements = [
            {
                "lot_ref": item["lot_ref"], "quantity_decimal": item["quantity_decimal"],
                "fifo_basis": None if item["fifo_basis"] is None else json.loads(item["fifo_basis"]),
                "acquisition_event_ref": item["acquisition_event_ref"],
            }
            for item in connection.execute(
                "SELECT * FROM realized_lot_movement WHERE world_artifact_ref=? AND event_sequence=? ORDER BY movement_sequence",
                (artifact_ref, row["event_sequence"]),
            )
        ]
        events.append({
            "event_sequence": str(row["event_sequence"]), "event_ref": row["event_ref"],
            "event_type": row["event_type"], "account_ref": row["account_ref"],
            "related_account_ref": row["related_account_ref"], "asset_ref": row["asset_ref"],
            "custody_quantity_before_decimal": row["custody_quantity_before_decimal"],
            "custody_quantity_after_decimal": row["custody_quantity_after_decimal"],
            "destination_custody_quantity_before_decimal": row["destination_custody_quantity_before_decimal"],
            "destination_custody_quantity_after_decimal": row["destination_custody_quantity_after_decimal"],
            "asset_quantity_before_decimal": row["asset_quantity_before_decimal"],
            "asset_quantity_after_decimal": row["asset_quantity_after_decimal"],
            "asset_fifo_basis_before": None if row["asset_fifo_basis_before"] is None else json.loads(row["asset_fifo_basis_before"]),
            "asset_fifo_basis_after": None if row["asset_fifo_basis_after"] is None else json.loads(row["asset_fifo_basis_after"]),
            "basis_added": None if row["basis_added"] is None else json.loads(row["basis_added"]),
            "basis_consumed": None if row["basis_consumed"] is None else json.loads(row["basis_consumed"]),
            "realized_gain": json.loads(row["realized_gain_before_tax"]), "consumed_lots": movements,
        })
    custody = [
        {"account_ref": row["account_ref"], "asset_ref": row["asset_ref"], "remaining_quantity_decimal": row["remaining_quantity_decimal"]}
        for row in connection.execute("SELECT * FROM realized_custody_position WHERE world_artifact_ref=? ORDER BY account_ref,asset_ref", (artifact_ref,))
    ]
    positions = [
        {
            "asset_ref": row["asset_ref"], "asset_type": row["asset_type"],
            "remaining_quantity_decimal": row["remaining_quantity_decimal"],
            "remaining_fifo_basis": json.loads(row["remaining_fifo_basis"]),
            "cost_average": json.loads(row["cost_average"]),
            "realized_gross_proceeds": json.loads(row["realized_gross_proceeds"]),
            "realized_fifo_basis": json.loads(row["realized_fifo_basis"]),
            "realized_gain": json.loads(row["realized_gain_before_tax"]),
            "gross_income": json.loads(row["gross_income"]), "monetary_fees": json.loads(row["monetary_fees"]),
        }
        for row in connection.execute("SELECT * FROM realized_asset_position WHERE world_artifact_ref=? ORDER BY asset_ref", (artifact_ref,))
    ]
    lots = [
        {
            "lot_ref": row["lot_ref"], "asset_ref": row["asset_ref"],
            "acquisition_event_ref": row["acquisition_event_ref"],
            "acquisition_local_date": row["acquisition_local_date"],
            "acquisition_effective_at_utc": row["acquisition_effective_at_utc"],
            "remaining_quantity_decimal": row["remaining_quantity_decimal"],
            "remaining_fifo_basis": None if row["remaining_fifo_basis"] is None else json.loads(row["remaining_fifo_basis"]),
        }
        for row in connection.execute("SELECT * FROM realized_remaining_lot WHERE world_artifact_ref=? ORDER BY lot_ref", (artifact_ref,))
    ]
    return {"event_results": events, "custody_positions": custody, "asset_positions": positions, "remaining_lots": lots}


def _insert_result_tables(connection: sqlite3.Connection, artifact_ref: str, result: Mapping[str, Any]) -> None:
    for row in result["event_results"]:
        connection.execute(
            "INSERT INTO realized_event_result VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (artifact_ref, row["event_sequence"], row["event_ref"], row["event_type"], row["account_ref"],
             row["related_account_ref"], row["asset_ref"], row["custody_quantity_before_decimal"],
             row["custody_quantity_after_decimal"], row["destination_custody_quantity_before_decimal"],
             row["destination_custody_quantity_after_decimal"], row["asset_quantity_before_decimal"],
             row["asset_quantity_after_decimal"], _exact_json(row["asset_fifo_basis_before"]), _exact_json(row["asset_fifo_basis_after"]),
             _exact_json(row["basis_added"]), _exact_json(row["basis_consumed"]), _exact_json(row["realized_gain"])),
        )
        for movement_sequence, movement in enumerate(row["consumed_lots"], 1):
            connection.execute(
                "INSERT INTO realized_lot_movement VALUES(?,?,?,?,?,?,?)",
                (artifact_ref, row["event_sequence"], movement_sequence, movement["lot_ref"],
                 movement["acquisition_event_ref"], movement["quantity_decimal"], _exact_json(movement["fifo_basis"])),
            )
    for row in result["custody_positions"]:
        connection.execute(
            "INSERT INTO realized_custody_position VALUES(?,?,?,?)",
            (artifact_ref, row["account_ref"], row["asset_ref"], row["remaining_quantity_decimal"]),
        )
    for row in result["asset_positions"]:
        connection.execute(
            "INSERT INTO realized_asset_position VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (artifact_ref, row["asset_ref"], row["asset_type"], row["remaining_quantity_decimal"],
             _exact_json(row["remaining_fifo_basis"]), _exact_json(row["cost_average"]), _exact_json(row["realized_gross_proceeds"]),
             _exact_json(row["realized_fifo_basis"]), _exact_json(row["realized_gain"]), _exact_json(row["gross_income"]), _exact_json(row["monetary_fees"])),
        )
    for row in result["remaining_lots"]:
        connection.execute(
            "INSERT INTO realized_remaining_lot VALUES(?,?,?,?,?,?,?,?)",
            (artifact_ref, row["lot_ref"], row["asset_ref"], row["acquisition_event_ref"],
             row["acquisition_local_date"], row["acquisition_effective_at_utc"],
             row["remaining_quantity_decimal"], _exact_json(row["remaining_fifo_basis"])),
        )


def _job_completion_failed(connection: sqlite3.Connection, job_ref: str, code: str, completed_at_utc: str) -> None:
    body = {"job_ref": job_ref, "completion_status": "failed", "failure_code": code, "completed_at_utc": completed_at_utc}
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("INSERT INTO realized_state_job_completion VALUES(?,'failed',NULL,?,?,?)", (job_ref, code, completed_at_utc, _fingerprint(body)))
        connection.execute("COMMIT")
    except sqlite3.Error:
        if connection.in_transaction: connection.execute("ROLLBACK")
        _abort("asset_activity_state_write_failed")


def materialize_asset_activity_realized_state_v2(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    request_mode: str,
    requested_at_utc: str,
    portfolio_completeness: str,
    *, failpoint: str | None = None,
) -> AssetActivityRealizedStateV2Result:
    context = _product_context(context_value); _validate_algorithm(); requested = _utc(requested_at_utc)
    if request_mode not in MODES or portfolio_completeness not in COMPLETENESS or failpoint not in FAILPOINTS:
        _abort("asset_activity_state_input_invalid")
    data_space=_state_owner_directory(data_space_path,code="asset_activity_state_source_invalid");portfolio_completeness=_validate_portfolio_completeness(data_space,portfolio_completeness)
    binding, worlds = _source_worlds(data_space, context)
    area = _area(data_space, create=True); store_path = area / STORE_NAME
    with _WriterLock(area):
        if _superseded_store(store_path):
            # Der ueberholte Stand weicht dem neuen. Verloren geht nichts: Er war
            # abgeleitet, und was er trug, entsteht aus den Buchungen neu.
            for stale in (store_path, Path(str(store_path) + "-journal")):
                try: stale.unlink()
                except FileNotFoundError: pass
                except OSError: _abort("asset_activity_state_store_invalid")
        if not store_path.exists(): _create_store(store_path, context, requested)
        connection = _open_store(store_path, context, read_only=False)
        try:
            current, prior_worlds = _current(connection)
            # Gleicher Buchungsstand und dieselbe Wahl je Wallet: nichts zu tun. Eine geaenderte Wahl (rc.294) laesst die
            # Buchungen gleich, aendert aber die Eingabe der betroffenen Welten.
            same_input = set(prior_worlds) == set(worlds) and all(
                prior_worlds[world_ref]["source_input_fingerprint"] == world["source_input_fingerprint"] for world_ref, world in worlds.items())
            if request_mode == "incremental" and current is not None and same_input and current["source_activity_set_fingerprint"] == binding["activity_set_fingerprint"] and current["source_generation_ref"] == binding["generation_ref"]:
                if current["portfolio_completeness"] != portfolio_completeness:
                    _abort("asset_activity_state_input_invalid")
                return AssetActivityRealizedStateV2Result(
                    "already_current", binding["generation_ref"], current["global_artifact_ref"], current["world_count"], 0,
                    current["world_count"], request_mode, True,
                )
            if current is not None and requested <= current["completed_at_utc"]:
                _abort("asset_activity_state_input_invalid")
            job_body = {
                "source_generation_ref": binding["generation_ref"], "source_ledger_fingerprint": binding["ledger_fingerprint"],
                "source_activity_set_fingerprint": binding["activity_set_fingerprint"], "request_mode": request_mode,
                "prior_global_artifact_ref": None if current is None else current["global_artifact_ref"],
                "requested_at_utc": requested, "source_world_count": len(worlds),
            }
            job_fingerprint = _fingerprint(job_body); job_ref = "rsj_" + job_fingerprint[:32]
            existing = connection.execute("SELECT completion_status FROM realized_state_job LEFT JOIN realized_state_job_completion USING(job_ref) WHERE job_ref=?", (job_ref,)).fetchall()
            if existing: _abort("asset_activity_state_job_conflict")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("INSERT INTO realized_state_job VALUES(?,?,?,?,?,?,?,?,?)", (
                job_ref, binding["generation_ref"], binding["ledger_fingerprint"], binding["activity_set_fingerprint"],
                request_mode, job_body["prior_global_artifact_ref"], requested, len(worlds), job_fingerprint,
            ))
            connection.execute("COMMIT")
            if failpoint == "after_job": _abort("synthetic_asset_activity_state_failpoint")
            references = []; new_rows = []; changed = 0; reused = 0
            for world_ref, world in sorted(worlds.items()):
                prior = prior_worlds.get(world_ref)
                if request_mode == "incremental" and prior is not None and prior["source_input_fingerprint"] == world["source_input_fingerprint"]:
                    references.append({"world_ref": world_ref, "world_artifact_ref": prior["world_artifact_ref"], "result_fingerprint": prior["result_fingerprint"]}); reused += 1; continue
                mode, earliest = _change_mode(prior, world, request_mode)
                result = _project(world)
                artifact_body = {
                    "job_ref": job_ref, "world_ref": world_ref, "portfolio_ref": world["portfolio_ref"], "asset_ref": world["asset_ref"],
                    "calculation_mode": mode, "prior_world_artifact_ref": None if prior is None else prior["world_artifact_ref"],
                    "earliest_changed_order_key": earliest, "source_event_count": world["source_event_count"],
                    "source_input_fingerprint": world["source_input_fingerprint"], "result_fingerprint": result["result_fingerprint"],
                    "table_fingerprint": _fingerprint(_result_table_projection(result)), "completed_at_utc": requested,
                }
                artifact_fingerprint = _fingerprint(artifact_body); artifact_ref = "rwa_" + artifact_fingerprint[:32]
                new_rows.append((artifact_ref, artifact_body, world, result, artifact_fingerprint))
                references.append({"world_ref": world_ref, "world_artifact_ref": artifact_ref, "result_fingerprint": result["result_fingerprint"]}); changed += 1
            references.sort(key=lambda item: item["world_ref"])
            if failpoint == "after_world_artifacts": _abort("synthetic_asset_activity_state_failpoint")
            world_set_fingerprint = _fingerprint(references)
            global_body = {
                "job_ref": job_ref, "source_generation_ref": binding["generation_ref"],
                "source_ledger_fingerprint": binding["ledger_fingerprint"], "source_activity_set_fingerprint": binding["activity_set_fingerprint"],
                "world_count": len(worlds), "changed_world_count": changed, "reused_world_count": reused,
                "world_set_fingerprint": world_set_fingerprint, "full_rebuild_verified": True,
                "portfolio_completeness": portfolio_completeness, "complete_portfolio_claim_authorized": False,
                "completed_at_utc": requested,
            }
            global_fingerprint = _fingerprint(global_body); global_ref = "rga_" + global_fingerprint[:32]
            if failpoint == "before_completion": _abort("synthetic_asset_activity_state_failpoint")
            try:
                latest_binding = read_desktop_product_asset_activity_binding_v1(data_space_path, context)
            except DesktopProductAssetActivityV1Error:
                _abort("asset_activity_state_source_stale")
            if any(latest_binding.get(key) != binding.get(key) for key in ("generation_ref", "ledger_fingerprint", "activity_set_fingerprint")):
                _abort("asset_activity_state_source_stale")
            connection.execute("BEGIN IMMEDIATE")
            for artifact_ref, body, world, result, artifact_fp in new_rows:
                connection.execute("INSERT INTO realized_world_artifact VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    artifact_ref, job_ref, body["world_ref"], body["portfolio_ref"], body["asset_ref"], body["calculation_mode"],
                    body["prior_world_artifact_ref"], body["earliest_changed_order_key"], body["source_event_count"], body["source_input_fingerprint"],
                    _canonical(_stored_world_source(world)).decode("utf-8"), body["result_fingerprint"], _canonical(result).decode("utf-8"), body["table_fingerprint"], requested, artifact_fp,
                ))
                _insert_result_tables(connection, artifact_ref, result)
            connection.execute("INSERT INTO realized_global_artifact VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                global_ref, job_ref, binding["generation_ref"], binding["ledger_fingerprint"], binding["activity_set_fingerprint"],
                len(worlds), changed, reused, world_set_fingerprint, _canonical(references).decode("utf-8"), 1,
                portfolio_completeness, 0, requested, global_fingerprint,
            ))
            completion_body = {"job_ref": job_ref, "completion_status": "completed", "global_artifact_ref": global_ref, "completed_at_utc": requested}
            connection.execute("INSERT INTO realized_state_job_completion VALUES(?,'completed',?,NULL,?,?)", (job_ref, global_ref, requested, _fingerprint(completion_body)))
            connection.execute("COMMIT")
            _validate_store(connection, context)
            return AssetActivityRealizedStateV2Result("completed", binding["generation_ref"], global_ref, len(worlds), changed, reused, request_mode, True)
        except AssetActivityRealizedStateV2Error as error:
            if connection.in_transaction: connection.execute("ROLLBACK")
            if 'job_ref' in locals() and not connection.execute("SELECT 1 FROM realized_state_job_completion WHERE job_ref=?", (job_ref,)).fetchone():
                _job_completion_failed(connection, job_ref, error.code, requested)
            raise
        except sqlite3.Error:
            if connection.in_transaction: connection.execute("ROLLBACK")
            if 'job_ref' in locals() and not connection.execute("SELECT 1 FROM realized_state_job_completion WHERE job_ref=?", (job_ref,)).fetchone():
                _job_completion_failed(connection, job_ref, "asset_activity_state_write_failed", requested)
            _abort("asset_activity_state_write_failed")
        finally:
            connection.close()


def verify_asset_activity_realized_state_full_rebuild_v2(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    context = _product_context(context_value); _validate_algorithm(); binding, worlds = _source_worlds(data_space_path, context)
    # Ein ueberholter Stand laesst sich nicht pruefen - er ist das Ergebnis eines
    # anderen Kerns. Das sagt der Code, statt ihn als beschaedigt zu melden.
    if _superseded_store(_store_path(data_space_path)): _abort("asset_activity_state_algorithm_changed")
    connection = _open_store(_store_path(data_space_path), context, read_only=True)
    try: current, artifacts = _current(connection)
    finally: connection.close()
    if current is None or current["source_generation_ref"] != binding["generation_ref"] or set(artifacts) != set(worlds):
        _abort("asset_activity_state_source_stale")
    rebuilt = {world_ref: _project(world)["result_fingerprint"] for world_ref, world in sorted(worlds.items())}
    stored = {world_ref: row["result_fingerprint"] for world_ref, row in sorted(artifacts.items())}
    if rebuilt != stored:
        _abort("asset_activity_state_full_rebuild_mismatch")
    body = {
        "asset_activity_realized_state_parity_version": 2, "status": "exact_match",
        "source_generation_ref": binding["generation_ref"], "source_activity_set_fingerprint": binding["activity_set_fingerprint"],
        "global_artifact_ref": current["global_artifact_ref"], "world_count": len(worlds),
        "world_result_fingerprints": rebuilt, "canonical_write": False, "cash_imported": False,
        "provider_access": False, "network_access": False,
    }
    return {**body, "parity_fingerprint": _fingerprint(body)}


def read_asset_activity_realized_state_v2(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    return _read_public_with_current(data_space_path, context_value)[0]


def _read_public_with_current(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
) -> tuple[dict[str, Any], Mapping[str, Any] | None, dict[str, Mapping[str, Any]]]:
    """Lesemodell samt aktuellem Stand und Welt-Artefakten aus einem einzigen Oeffnen.

    Das Oeffnen prueft den ganzen Speicher - jede Welt wird nachgerechnet. Die
    Activity-Sicht las erst das Lesemodell und oeffnete den Speicher danach ein
    zweites Mal fuer die Artefakte: zwei volle Pruefungen je Aufruf. Beides stammt
    jetzt aus demselben geprueften Stand.
    """
    context = _product_context(context_value); _validate_algorithm()
    try: binding = read_desktop_product_asset_activity_binding_v1(data_space_path, context)
    except DesktopProductAssetActivityV1Error: _abort("asset_activity_state_ledger_invalid")
    path = _store_path(data_space_path)
    # Ein ueberholter Stand wird gelesen wie ein fehlender: Es gibt noch kein
    # Ergebnis des heutigen Kerns. Das naechste Fortschreiben baut ihn neu auf.
    if not path.exists() or _superseded_store(path):
        return ({"asset_activity_realized_state_read_model_version": 2, "status": "absent", "freshness": "unavailable", "job_status": "unavailable", "job_failure_code": None, "world_count": 0, "positions": [], "canonical_write": False, "cash_imported": False, "provider_access": False, "network_access": False, "path_exposed": False, "context_exposed": False}, None, {})
    connection = _open_store(path, context, read_only=True)
    try:
        current, artifacts = _current(connection)
        latest_job_row = connection.execute(
            "SELECT job.requested_at_utc,completion.completion_status,completion.failure_code "
            "FROM realized_state_job job LEFT JOIN realized_state_job_completion completion USING(job_ref) "
            "ORDER BY job.requested_at_utc DESC,job.job_ref DESC LIMIT 1"
        ).fetchone()
    finally: connection.close()
    if current is None: _abort("asset_activity_state_store_invalid")
    positions = []
    for ordinal, (world_ref, artifact) in enumerate(sorted(artifacts.items()), 1):
        try: result = json.loads(artifact["result_json"])
        except Exception: _abort("asset_activity_state_store_invalid")
        for row in result["asset_positions"]:
            positions.append({
                # Kanonische Asset-Identitaet. Ohne sie ist eine Position keinem
                # Asset zuordenbar: `world_ordinal` ist eine laufende Nummer ueber
                # die FIFO-Welten, und Anzeigenamen sind nicht eindeutig. Die
                # R-Produktebene bildet diese Ref auf ihre browserlokale Ref ab und
                # gibt ausschliesslich diese an die Oberflaeche weiter.
                "asset_ref": row["asset_ref"],
                "world_ordinal": ordinal, "asset_type": row["asset_type"],
                "remaining_quantity_decimal": row["remaining_quantity_decimal"],
                "remaining_fifo_basis": _exact_display(row["remaining_fifo_basis"]), "cost_average": _exact_display(row["cost_average"]),
                "realized_gross_proceeds": _exact_display(row["realized_gross_proceeds"]), "realized_fifo_basis": _exact_display(row["realized_fifo_basis"]),
                "realized_gain_before_tax": _exact_display(row["realized_gain"]), "gross_income": _exact_display(row["gross_income"]),
                "monetary_fees": _exact_display(row["monetary_fees"]),
            })
    source_fresh = binding.get("status") == "available" and current["source_generation_ref"] == binding.get("generation_ref") and current["source_activity_set_fingerprint"] == binding.get("activity_set_fingerprint")
    if source_fresh:
        # Die Wahl je Wallet gehoert zur Eingabe (rc.294), ebenso die FIFO-Wallet aus mehreren Konten (#508): Weicht eine
        # davon von der gespeicherten ab, ist der Stand ueberholt.
        methods = _source_methods(data_space_path, context)
        wallets = _source_wallets(data_space_path, context)
        splits = _source_splits(data_space_path, context)
        for artifact in artifacts.values():
            try: stored_source = json.loads(artifact["source_activity_json"])
            except Exception: _abort("asset_activity_state_store_invalid")
            activity, wrapper = _stored_wrapper(stored_source)
            if (wrapper.get("valuation_methods", []) != _world_methods(methods, artifact["asset_ref"], activity)
                    or wrapper.get("fifo_wallets", []) != _world_wallets(wallets, artifact["asset_ref"], activity)
                    or wrapper.get("splits", []) != _world_splits(splits, artifact["asset_ref"], activity)):
                source_fresh = False
                break
    latest_job = None if latest_job_row is None else dict(latest_job_row)
    if not source_fresh:
        freshness, job_status = "stale", "source_changed"
    elif latest_job is not None and latest_job["requested_at_utc"] > current["completed_at_utc"] and latest_job["completion_status"] is None:
        freshness, job_status = "stale_pending", "pending"
    elif latest_job is not None and latest_job["requested_at_utc"] > current["completed_at_utc"] and latest_job["completion_status"] == "failed":
        freshness, job_status = "stale_failed", "failed"
    else:
        freshness, job_status = "fresh", "completed"
    public = {
        "asset_activity_realized_state_read_model_version": 2, "status": "available", "freshness": freshness,
        "job_status": job_status, "job_failure_code": None if job_status != "failed" else latest_job["failure_code"],
        "world_count": current["world_count"], "positions": positions,
        "portfolio_completeness": current["portfolio_completeness"], "complete_portfolio_claim_authorized": False,
        "full_rebuild_verified": bool(current["full_rebuild_verified"]),
        "canonical_write": False, "cash_imported": False, "provider_access": False, "network_access": False,
        "path_exposed": False, "context_exposed": False,
    }
    return public, current, artifacts


def read_asset_activity_realized_lot_trace_v2(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    snapshot_dates: Sequence[str] = (),
) -> dict[str, Any]:
    """Die Spur der Lots zum gueltigen FIFO-Stand: je Welt die Buchungen, das Ergebnis und der Lot-Nachweis.

    Gerechnet wird mit dem Kern, an den der Stand gebunden ist, aus den im Stand
    gespeicherten Buchungen - und nur geliefert, wenn das Ergebnis dabei Zeichen
    fuer Zeichen dem gespeicherten gleicht. Wer Lots ueber Transfers hinweg oder
    zu einem Stichtag je Konto belegen will, liest hier und rechnet nicht selbst.
    Die Frische des Stands wird genannt, nicht erzwungen.
    """
    if not _lot_trace_dates_valid(snapshot_dates):
        _abort("asset_activity_state_input_invalid")
    public, current, artifacts = _read_public_with_current(data_space_path, context_value)
    base = {
        "asset_activity_realized_lot_trace_version": 1, "status": public["status"], "freshness": public["freshness"],
        "world_count": public["world_count"], "worlds": [],
        "canonical_write": False, "cash_imported": False, "provider_access": False, "network_access": False,
    }
    if current is None:
        return base
    for world_ref, artifact in sorted(artifacts.items()):
        activity = _decode_activity(artifact)
        _, wrapper = _stored_wrapper(json.loads(artifact["source_activity_json"]))
        try:
            trace = project_semantic_realized_fifo_lot_trace_v2(wrapper, snapshot_dates)
        except SemanticRealizedFifoV2Error:
            _abort("asset_activity_state_full_rebuild_mismatch")
        if _canonical(trace["result"]).decode("utf-8") != artifact["result_json"]:
            _abort("asset_activity_state_full_rebuild_mismatch")
        base["worlds"].append({
            "world_ref": world_ref, "asset_activity": activity, "result": trace["result"],
            "transfer_lot_movements": trace["transfer_lot_movements"], "account_lots": trace["account_lots"],
            "account_lots_at": trace["account_lots_at"],
            "wallet_segments": trace["wallet_segments"], "basis_adjustments": trace["basis_adjustments"],
            # FIFO-Wallet aus mehreren Konten (#508): Lose, Abschnitte und Lot-Spur nennen dann das Hauptkonto; wer je Konto
            # zeigt, braucht die Zuordnung, mit der gerechnet wurde.
            "fifo_wallets": [dict(item) for item in wrapper.get("fifo_wallets") or []],
            # Splits (#451) nur, wo es welche gibt: wer Mengen einer Anschaffung mit spaeteren Lots vergleicht, braucht sie.
            **({"split_steps": trace["split_steps"]} if trace.get("split_steps") else {}),
        })
    return base


def preview_valuation_methods_v2(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    asset_ref: str,
    methods: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Vorschau einer Wahl je Wallet (rc.294): das Asset aus den aktuellen Buchungen, einmal mit der gueltigen und einmal mit
    der angefragten Wahl gerechnet. Schreibt nichts; liefert je Fassung die Spur des Kerns (Ergebnis, Abschnitte je Wallet)."""
    context = _product_context(context_value); _validate_algorithm()
    binding, worlds = _source_worlds(data_space_path, context)
    ledger = _state_owner_file(binding["ledger_path"], "asset_activity_state_ledger_invalid")
    try:
        # Mit den gueltigen FIFO-Wallets (#508): Die Vorschau aendert nur die Wahl der Wertermittlung.
        candidate = _ledger_worlds_v2(ledger, methods, _source_wallets(data_space_path, context), _source_splits(data_space_path, context))
    except (KeyError, TypeError):
        _abort("asset_activity_state_input_invalid")
    rows = []
    for world_ref, world in sorted(worlds.items()):
        if world["asset_ref"] != asset_ref:
            continue
        try:
            current = project_semantic_realized_fifo_lot_trace_v2(world["wrapper"])
            chosen = project_semantic_realized_fifo_lot_trace_v2(candidate[world_ref]["wrapper"])
        except SemanticRealizedFifoV2Error:
            _abort("asset_activity_state_input_invalid")
        rows.append({"world_ref": world_ref, "asset_activity": world["activity"], "current": current, "candidate": chosen})
    return {"asset_ref": asset_ref, "worlds": rows, "canonical_write": False, "provider_access": False, "network_access": False}


def preview_fifo_wallets_v2(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    wallets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Vorschau einer FIFO-Wallet aus mehreren Konten (#508): die aktuellen Buchungen einmal mit den gueltigen und einmal mit
    den angefragten Zuordnungen gerechnet - nur die Welten, deren Eingabe sich aendert. Schreibt nichts."""
    context = _product_context(context_value); _validate_algorithm()
    binding, worlds = _source_worlds(data_space_path, context)
    ledger = _state_owner_file(binding["ledger_path"], "asset_activity_state_ledger_invalid")
    try:
        candidate = _ledger_worlds_v2(ledger, _source_methods(data_space_path, context), wallets, _source_splits(data_space_path, context))
    except (KeyError, TypeError):
        _abort("asset_activity_state_input_invalid")
    rows = []
    for world_ref, world in sorted(worlds.items()):
        if candidate[world_ref]["wrapper"].get("fifo_wallets", []) == world["wrapper"].get("fifo_wallets", []):
            continue
        try:
            current = project_semantic_realized_fifo_lot_trace_v2(world["wrapper"])
            chosen = project_semantic_realized_fifo_lot_trace_v2(candidate[world_ref]["wrapper"])
        except SemanticRealizedFifoV2Error:
            _abort("asset_activity_state_input_invalid")
        rows.append({"world_ref": world_ref, "asset_ref": world["asset_ref"], "asset_activity": world["activity"],
                     "current": current, "candidate": chosen})
    return {"worlds": rows, "canonical_write": False, "provider_access": False, "network_access": False}


def preview_stock_splits_v2(
    data_space_path: str | Path,
    context_value: DesktopProductAssetActivityContextV1,
    splits: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Vorschau von Splits (#451): die betroffenen Welten aus den aktuellen Buchungen, einmal mit den gueltigen und einmal mit den
    angefragten Splits gerechnet. Weist der Kern die angefragten ab (etwa keine endliche Stueckzahl oder ein Verkauf, der danach
    nicht mehr gedeckt ist), steht sein Fehlercode in der Welt. Schreibt nichts."""
    context = _product_context(context_value); _validate_algorithm()
    binding, worlds = _source_worlds(data_space_path, context)
    ledger = _state_owner_file(binding["ledger_path"], "asset_activity_state_ledger_invalid")
    try:
        candidate = _ledger_worlds_v2(ledger, _source_methods(data_space_path, context), _source_wallets(data_space_path, context), splits)
    except (KeyError, TypeError):
        _abort("asset_activity_state_input_invalid")
    rows = []
    for world_ref, world in sorted(worlds.items()):
        if candidate[world_ref]["wrapper"].get("splits", []) == world["wrapper"].get("splits", []):
            continue
        try:
            current = project_semantic_realized_fifo_v2(world["wrapper"])
        except SemanticRealizedFifoV2Error:
            _abort("asset_activity_state_input_invalid")
        try:
            chosen, failure = project_semantic_realized_fifo_v2(candidate[world_ref]["wrapper"]), None
        except SemanticRealizedFifoV2Error as error:
            chosen, failure = None, error.code
        rows.append({"world_ref": world_ref, "asset_ref": world["asset_ref"], "current": current, "candidate": chosen, "failure_code": failure})
    return {"worlds": rows, "canonical_write": False, "provider_access": False, "network_access": False}


def _lot_trace_dates_valid(snapshot_dates: Any) -> bool:
    return (not isinstance(snapshot_dates, (str, bytes)) and isinstance(snapshot_dates, Sequence)
            and all(isinstance(day, str) and len(day) == 10 and day[4] == "-" and day[7] == "-"
                    and (day[:4] + day[5:7] + day[8:]).isdigit() for day in snapshot_dates))


__all__ = [
    "AssetActivityRealizedStateV2Error", "AssetActivityRealizedStateV2Result", "preview_fifo_wallets_v2", "preview_stock_splits_v2", "preview_valuation_methods_v2", "read_asset_activity_realized_lot_trace_v2",
    "asset_activity_realized_state_v2_error_codes", "materialize_asset_activity_realized_state_v2",
    "verify_asset_activity_realized_state_full_rebuild_v2", "read_asset_activity_realized_state_v2",
]
