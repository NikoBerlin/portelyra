#!/usr/bin/env python3
"""Provider-free, restart-safe Desktop Workflow v1 coordinator."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
R_FIFO = ROOT / "scripts" / "realized_fifo_projection.R"
PLUGIN_IDS = {
    "de_reference_v1": "tax_de_personal_income_tax_projection_v1",
    "de_reference_v2": "tax_de_personal_income_tax_projection_v2",
}
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{3,80}$")
SHA = re.compile(r"^[a-f0-9]{64}$")
RUN = re.compile(r"^run_[a-z0-9_]{4,59}$")
STAGE_NAMES = ("canonical", "fifo", "tax", "grouping", "market", "fx", "valuation", "trade_analysis", "market_analysis", "publication")

ERROR_CODES = frozenset({
    "desktop_workflow_job_invalid", "desktop_workflow_job_permission_invalid",
    "desktop_workflow_context_mismatch", "desktop_workflow_storage_invalid",
    "desktop_workflow_full_rebuild_required", "desktop_workflow_fifo_blocked",
    "desktop_workflow_tax_blocked", "desktop_workflow_grouping_blocked",
    "desktop_workflow_market_blocked", "desktop_workflow_fx_blocked",
    "desktop_workflow_valuation_blocked", "desktop_workflow_analysis_blocked",
    "desktop_workflow_publication_blocked", "desktop_workflow_boundary_failed",
})


class DesktopWorkflowBlocked(RuntimeError):
    def __init__(self, code: str):
        if code not in ERROR_CODES:
            raise ValueError("unregistered_desktop_workflow_error_code")
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise DesktopWorkflowBlocked(code)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    payload = value if isinstance(value, bytes) else _canonical(value)
    return hashlib.sha256(payload).hexdigest()


def _opaque(prefix: str, value: Any) -> str:
    return f"{prefix}_{_sha(value)[:32]}"


def _utc(value: Any) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("desktop_workflow_job_invalid")
    try:
        if datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            _abort("desktop_workflow_job_invalid")
    except ValueError:
        _abort("desktop_workflow_job_invalid")
    return value


def _date(value: Any) -> str:
    if not isinstance(value, str) or DATE.fullmatch(value) is None:
        _abort("desktop_workflow_job_invalid")
    try:
        if datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") != value:
            _abort("desktop_workflow_job_invalid")
    except ValueError:
        _abort("desktop_workflow_job_invalid")
    return value


def _decimal(value: Any, *, optional: bool = False, positive: bool = False, nonnegative: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or len(value) > 80 or DECIMAL.fullmatch(value) is None or value == "-0":
        _abort("desktop_workflow_job_invalid")
    parsed = Decimal(value)
    if positive and parsed <= 0 or nonnegative and parsed < 0:
        _abort("desktop_workflow_job_invalid")
    return value


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _offset(value: str, seconds: int) -> str:
    return (datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ") + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _regular_owner_file(path: Path) -> bytes:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        _abort("desktop_workflow_job_invalid")
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        _abort("desktop_workflow_job_permission_invalid")
    try:
        return path.read_bytes()
    except OSError:
        _abort("desktop_workflow_job_invalid")


def _path_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _owner_directory(path: Path) -> Path:
    if path.is_symlink():
        _abort("desktop_workflow_storage_invalid")
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        if cursor.is_symlink():
            _abort("desktop_workflow_storage_invalid")
        missing.append(cursor); cursor = cursor.parent
    for created in reversed(missing):
        try:
            os.mkdir(created, 0o700)
            os.chmod(created, 0o700)
        except OSError:
            _abort("desktop_workflow_storage_invalid")
        if created.is_symlink() or not created.is_dir():
            _abort("desktop_workflow_storage_invalid")
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        _abort("desktop_workflow_storage_invalid")
    if path.is_symlink() or not resolved.is_dir():
        _abort("desktop_workflow_storage_invalid")
    os.chmod(resolved, 0o700)
    return resolved


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists() or path.is_symlink():
        _abort("desktop_workflow_storage_invalid")
    parent = _owner_directory(path.parent)
    temporary = parent / f".{path.name}.tmp-{os.getpid()}"
    payload = _canonical(value) + b"\n"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("desktop_workflow_storage_write_failed")
            view = view[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.link(temporary, path)
    os.unlink(temporary)
    os.chmod(path, 0o600)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _replace_json(path: Path, value: Mapping[str, Any]) -> None:
    parent = _owner_directory(path.parent)
    if path.is_symlink():
        _abort("desktop_workflow_storage_invalid")
    temporary = parent / f".{path.name}.replace-{os.getpid()}"
    payload = _canonical(value) + b"\n"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("desktop_workflow_storage_write_failed")
            view = view[written:]
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    os.chmod(path, 0o600)
    directory = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _load_job(path: Path) -> dict[str, Any]:
    raw = _regular_owner_file(path)
    try:
        envelope = json.loads(raw.decode("utf-8", errors="strict"))
    except Exception:
        _abort("desktop_workflow_job_invalid")
    if not isinstance(envelope, dict) or set(envelope) != {"contract_version", "payload_json", "payload_fingerprint"} or envelope["contract_version"] != 1:
        _abort("desktop_workflow_job_invalid")
    payload_text = envelope["payload_json"]
    if not isinstance(payload_text, str) or not isinstance(envelope["payload_fingerprint"], str) or SHA.fullmatch(envelope["payload_fingerprint"]) is None:
        _abort("desktop_workflow_job_invalid")
    if hashlib.sha256(payload_text.encode("utf-8")).hexdigest() != envelope["payload_fingerprint"]:
        _abort("desktop_workflow_job_invalid")
    try:
        payload = json.loads(payload_text)
    except Exception:
        _abort("desktop_workflow_job_invalid")
    _validate_payload(payload)
    return payload


def _validate_payload(value: Any) -> None:
    required = {
        "contract_version", "run_id", "runtime", "portfolio", "data_space_label", "run_mode",
        "as_of_date", "cutoff_at_utc", "prepared_at_utc", "executed_at_utc", "tax_policy",
        "asset_inputs", "grouping_policy", "fee_policy", "catalog_fingerprint", "canonical_fingerprint",
    }
    if not isinstance(value, dict) or set(value) not in (required, required | {"market_valuation_binding"}) or value["contract_version"] != 1 or not isinstance(value["run_id"], str) or RUN.fullmatch(value["run_id"]) is None:
        _abort("desktop_workflow_job_invalid")
    fee = value["fee_policy"]
    if not isinstance(fee, dict) or set(fee) != {"source", "fixed_decimal", "percentage_rate_decimal"}:
        _abort("desktop_workflow_job_invalid")
    if fee["source"] not in {"derived_from_transactions", "fixed_per_trade", "percentage_of_turnover"}:
        _abort("desktop_workflow_job_invalid")
    expected_fixed = fee["source"] == "fixed_per_trade"
    expected_percentage = fee["source"] == "percentage_of_turnover"
    if (fee["fixed_decimal"] is None) is expected_fixed or (fee["percentage_rate_decimal"] is None) is expected_percentage:
        _abort("desktop_workflow_job_invalid")
    runtime = value["runtime"]
    if not isinstance(runtime, dict) or set(runtime) != {"tenant_id", "user_id", "data_space_id", "data_root", "canonical_path", "ledger_path", "ledger_schema_version", "ledger_fingerprint", "semantic_contracts"}:
        _abort("desktop_workflow_job_invalid")
    if not all(isinstance(runtime[key], str) and TOKEN.fullmatch(runtime[key]) for key in ("tenant_id", "user_id", "data_space_id")) or not runtime["data_space_id"].startswith("sbx_"):
        _abort("desktop_workflow_job_invalid")
    for key in ("data_root", "canonical_path"):
        if not isinstance(runtime[key], str) or not Path(runtime[key]).is_absolute():
            _abort("desktop_workflow_job_invalid")
    if runtime["ledger_schema_version"] not in {201, 401} or not isinstance(runtime["semantic_contracts"], list):
        _abort("desktop_workflow_job_invalid")
    if runtime["ledger_schema_version"] == 201:
        if runtime["ledger_path"] is not None or runtime["ledger_fingerprint"] is not None or runtime["semantic_contracts"] != ["portfolio_ledger_v1_transaction_fact"]:
            _abort("desktop_workflow_job_invalid")
    elif (not isinstance(runtime["ledger_path"], str) or not Path(runtime["ledger_path"]).is_absolute() or
          not isinstance(runtime["ledger_fingerprint"], str) or SHA.fullmatch(runtime["ledger_fingerprint"]) is None or
          runtime["semantic_contracts"] != ["portfolio_ledger_v1_transaction_fact", "asset_activity_v1"]):
        _abort("desktop_workflow_job_invalid")
    portfolio = value["portfolio"]
    if not isinstance(portfolio, dict) or set(portfolio) != {"portfolio_id", "display_name", "base_currency"} or not all(isinstance(portfolio[key], str) for key in portfolio):
        _abort("desktop_workflow_job_invalid")
    if value["run_mode"] not in {"full", "incremental"} or value["grouping_policy"] != {"mode": "none"}:
        _abort("desktop_workflow_job_invalid")
    _date(value["as_of_date"]); _utc(value["cutoff_at_utc"]); _utc(value["prepared_at_utc"]); _utc(value["executed_at_utc"])
    if not all(isinstance(value[key], str) and SHA.fullmatch(value[key]) is not None for key in ("catalog_fingerprint", "canonical_fingerprint")):
        _abort("desktop_workflow_job_invalid")
    policy = value["tax_policy"]
    expected_policy = {"mode", "capital_income_tax_rate", "personal_income_tax_rate", "solidarity_surcharge_rate", "church_tax_applicable", "church_tax_rate"}
    if not isinstance(policy, dict) or set(policy) != expected_policy or policy["mode"] not in {"disabled", "de_reference_v1", "de_reference_v2"}:
        _abort("desktop_workflow_job_invalid")
    for key in ("capital_income_tax_rate", "personal_income_tax_rate", "solidarity_surcharge_rate", "church_tax_rate"):
        _decimal(policy[key], optional=True, nonnegative=True)
    applicable = policy["church_tax_applicable"]
    church_valid = (policy["mode"] == "de_reference_v2" and applicable in {"applicable", "not_applicable"} and ((applicable == "applicable") == (policy["church_tax_rate"] is not None))) or (policy["mode"] != "de_reference_v2" and applicable is None and policy["church_tax_rate"] is None)
    if not church_valid:
        _abort("desktop_workflow_job_invalid")
    if not isinstance(value["data_space_label"], str) or not value["data_space_label"] or len(value["data_space_label"].encode()) > 100:
        _abort("desktop_workflow_job_invalid")
    if not isinstance(value["asset_inputs"], list):
        _abort("desktop_workflow_job_invalid")
    seen: set[str] = set()
    expected = {"asset_id", "display_name", "asset_type", "listing_code", "market_currency", "close_decimal", "observed_at_utc", "tax_classification", "partial_exemption_rate_decimal", "fixed_fee_decimal", "percentage_fee_rate_decimal", "fx_base_currency", "fx_quote_currency", "fx_direction", "fx_rate_decimal", "fx_observed_at_utc"}
    for row in value["asset_inputs"]:
        if not isinstance(row, dict) or set(row) != expected or not isinstance(row["asset_id"], str) or row["asset_id"] in seen:
            _abort("desktop_workflow_job_invalid")
        seen.add(row["asset_id"])
        if row["fx_direction"] not in {"none", "direct", "inverse"}:
            _abort("desktop_workflow_job_invalid")
        for key in ("close_decimal", "partial_exemption_rate_decimal", "fixed_fee_decimal", "percentage_fee_rate_decimal", "fx_rate_decimal"):
            _decimal(row[key], optional=True, nonnegative=key != "close_decimal", positive=key in {"close_decimal", "fx_rate_decimal"})
        for key in ("observed_at_utc", "fx_observed_at_utc"):
            if row[key] is not None: _utc(row[key])


def _runtime_paths(payload: Mapping[str, Any]) -> tuple[Path, Path, Path, Path]:
    runtime = payload["runtime"]
    data_root = Path(runtime["data_root"])
    if data_root.is_symlink() or not data_root.is_dir():
        _abort("desktop_workflow_storage_invalid")
    root = data_root.resolve(strict=True)
    space = root / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"]
    canonical = space / "canonical.sqlite"
    if str(canonical) != runtime["canonical_path"] or canonical.is_symlink() or not canonical.is_file() or not _path_within(canonical.resolve(strict=True), root):
        _abort("desktop_workflow_context_mismatch")
    if hashlib.sha256(canonical.read_bytes()).hexdigest() != payload["canonical_fingerprint"]:
        _abort("desktop_workflow_context_mismatch")
    if runtime["ledger_schema_version"] == 401:
        ledger = Path(runtime["ledger_path"])
        if ledger.is_symlink() or not ledger.is_file() or not _path_within(ledger.resolve(strict=True), space.resolve(strict=True)) or hashlib.sha256(ledger.read_bytes()).hexdigest() != runtime["ledger_fingerprint"]:
            _abort("desktop_workflow_context_mismatch")
    center = _owner_directory(space / "run-center")
    run = _owner_directory(center / "runs" / payload["run_id"])
    artifacts = _owner_directory(space / "artifacts")
    return root, space, run, artifacts


def _fifo_context_fingerprint(runtime: Mapping[str, str]) -> str:
    material = "|".join(("realized-fifo-context-v1", runtime["tenant_id"], runtime["user_id"], runtime["data_space_id"]))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _fifo_ref(prefix: str, context_fingerprint: str, internal: str) -> str:
    material = "|".join(("realized-fifo-public-ref-v1", context_fingerprint, prefix, internal))
    return prefix + hashlib.sha256(material.encode("utf-8")).hexdigest()[:32]


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return [{key: (None if value == "" else value) for key, value in row.items()} for row in csv.DictReader(handle)]


def _project_schema400(payload: Mapping[str, Any], run: Path) -> Path:
    source = Path(payload["runtime"]["canonical_path"])
    target = run / "calculation-ledger.sqlite"
    target.unlink(missing_ok=True)
    schema = (ROOT / "contracts" / "portfolio-ledger" / "v1" / "schema.sql").read_text(encoding="utf-8")
    try:
        reader = sqlite3.connect(f"{source.resolve(strict=True).as_uri()}?mode=ro", uri=True)
        reader.row_factory = sqlite3.Row; reader.execute("PRAGMA query_only=ON")
        binding = reader.execute("SELECT tenant_id,user_id FROM store_binding WHERE singleton_id=1").fetchone()
        if binding is None or binding["tenant_id"] != payload["runtime"]["tenant_id"] or binding["user_id"] != payload["runtime"]["user_id"]:
            _abort("desktop_workflow_context_mismatch")
        portfolios = reader.execute("SELECT * FROM portfolio ORDER BY portfolio_id").fetchall()
        accounts = reader.execute("SELECT * FROM account ORDER BY account_id").fetchall()
        assets = reader.execute("SELECT * FROM asset ORDER BY asset_id").fetchall()
        transactions = reader.execute("SELECT * FROM current_transaction ORDER BY effective_at_utc,transaction_id").fetchall()
        postings = reader.execute("SELECT * FROM current_transaction_posting ORDER BY transaction_id,sequence_no").fetchall()
        reader.close()
        writer = sqlite3.connect(target); writer.execute("PRAGMA foreign_keys=ON"); writer.executescript(schema)
        command_id = _opaque("cmd", {"run": payload["run_id"], "projection": "schema400"})
        writer.execute("INSERT INTO ledger_store_binding VALUES (1,400,?,?,?,?)", (payload["runtime"]["tenant_id"], payload["runtime"]["user_id"], payload["runtime"]["data_space_id"], payload["executed_at_utc"]))
        writer.execute("INSERT INTO ledger_command_receipt VALUES (?,?,?,?,?,?,?)", (command_id, "data_app", "desktop_schema400_projection_v1", "desktop_workflow_worker", _sha({"catalog": payload["catalog_fingerprint"], "cutoff": payload["cutoff_at_utc"]}), None, payload["executed_at_utc"]))
        for row in portfolios:
            writer.execute("INSERT INTO portfolio_entity VALUES (?,'native',NULL,?,?)", (row["portfolio_id"], command_id, row["created_at_utc"]))
            writer.execute("INSERT INTO portfolio_revision VALUES (?,?,1,?,?,?,NULL,?,?)", (_opaque("ptr", row["portfolio_id"]), row["portfolio_id"], row["display_name"], row["base_currency"], row["status"], command_id, row["updated_at_utc"]))
        for row in accounts:
            writer.execute("INSERT INTO account_entity VALUES (?,?,'native',NULL,?,?)", (row["account_id"], row["portfolio_id"], command_id, row["created_at_utc"]))
            account_type = "other" if row["account_type"] == "external" else row["account_type"]
            writer.execute("INSERT INTO account_revision VALUES (?,?,1,?,?,?,'active','complete',NULL,?,?)", (_opaque("acr", row["account_id"]), row["account_id"], row["display_name"], account_type, row["institution_label"], command_id, row["updated_at_utc"]))
        for row in assets:
            writer.execute("INSERT INTO asset_entity VALUES (?,'native',NULL,?,?)", (row["asset_id"], command_id, row["created_at_utc"]))
            writer.execute("INSERT INTO asset_revision VALUES (?,?,1,?,?,?,?,?,NULL,?,'complete',NULL,?,?)", (_opaque("asr", row["asset_id"]), row["asset_id"], row["display_name"], row["asset_type"], row["quantity_scale"], row["valuation_method"], row["isin"], row["status"], command_id, row["updated_at_utc"]))
        by_transaction: dict[str, list[sqlite3.Row]] = {}
        for posting in postings: by_transaction.setdefault(posting["transaction_id"], []).append(posting)
        for transaction in transactions:
            rows = by_transaction.get(transaction["transaction_id"], [])
            role = lambda name: [row for row in rows if row["posting_role"] == name]
            event = transaction["transaction_type"]
            selected = None; related = None
            if event in {"buy", "sell"}: selected = (role("asset") or [None])[0]
            elif event in {"deposit", "withdrawal"}: selected = (role("cash") or role("transfer") or [None])[0]; other = [row for row in rows if selected is not None and row["account_id"] != selected["account_id"]]; related = None
            elif event == "transfer":
                negatives = [row for row in role("transfer") if row["quantity_decimal"].startswith("-")]; positives = [row for row in role("transfer") if not row["quantity_decimal"].startswith("-")]
                selected = negatives[0] if negatives else (rows[0] if rows else None); related = positives[0]["account_id"] if positives else None
            elif event in {"dividend", "interest", "reward"}: selected = (role("income") or role("asset") or role("cash") or [None])[0]
            elif event == "fee": selected = (role("fee") or [None])[0]
            if selected is None: _abort("desktop_workflow_fifo_blocked")
            quantity = selected["quantity_decimal"].lstrip("-")
            price = selected["unit_price_decimal"] or "1"
            currency = selected["price_currency"] or selected["valuation_currency"]
            if currency is None: _abort("desktop_workflow_fifo_blocked")
            fee_rows = role("fee"); fee = fee_rows[0]["valuation_amount_decimal"].lstrip("-") if fee_rows and fee_rows[0]["valuation_amount_decimal"] else None
            writer.execute("INSERT INTO transaction_fact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (transaction["transaction_id"], transaction["portfolio_id"], selected["account_id"], related, selected["asset_id"], event, transaction["effective_at_utc"], transaction["local_date"], quantity, price, None, fee, currency, None, transaction["memo"], "native", None, None, command_id, transaction["created_at_utc"]))
        writer.commit()
        if writer.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or writer.execute("PRAGMA foreign_key_check").fetchall(): _abort("desktop_workflow_fifo_blocked")
        writer.close(); os.chmod(target, 0o600); return target
    except DesktopWorkflowBlocked:
        raise
    except Exception:
        try: target.unlink(missing_ok=True)
        except OSError: pass
        _abort("desktop_workflow_fifo_blocked")


def _run_fifo(payload: Mapping[str, Any], run: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = run / "fifo-evidence"
    if evidence.exists():
        shutil.rmtree(evidence)
    if payload["runtime"]["ledger_schema_version"] == 401:
        # Aktiensplits (#451): Dieser FIFO-Weg rechnet Buchungen vor dem Stichtag in neuen Stuecken - Gewinne und Restbestand wie
        # im FIFO-Stand (realized-state-v2) - und gibt ihre Mengen in Belegstuecken aus (rc.371). Einen kontobezogenen Split kennt er
        # nicht und haelt an, ebenso bei unlesbarem Speicher.
        runtime = payload["runtime"]
        try:
            from migrations.reference.stock_split_v1 import splits_for_fifo_v1
            from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1
            split_space = Path(runtime["canonical_path"]).parent
            splits = splits_for_fifo_v1(split_space, DesktopProductAssetActivityContextV1(
                runtime["tenant_id"], runtime["user_id"], runtime["data_space_id"], "desktop_owner", "desktop_owner"))
        except Exception:  # noqa: BLE001 - ob es Splits gibt, bleibt dann offen
            if (Path(runtime.get("canonical_path", ".")).parent / "stock-split-v1").exists():
                _abort("desktop_workflow_fifo_blocked")
            splits = []
        if any(split["account_ref"] is not None for split in splits):
            _abort("desktop_workflow_fifo_blocked")
        try:
            from workers.reference.semantic_realized_fifo_v1 import (
                SemanticRealizedFifoV1Error,
                build_semantic_realized_fifo_read_model_v1,
                publish_semantic_realized_fifo_evidence_v1,
            )
            model = build_semantic_realized_fifo_read_model_v1(
                Path(payload["runtime"]["ledger_path"]),
                {key: payload["runtime"][key] for key in ("tenant_id", "user_id", "data_space_id")},
                payload["portfolio"]["portfolio_id"], payload["cutoff_at_utc"],
                _offset(payload["executed_at_utc"], 1), splits,
            )
            publish_semantic_realized_fifo_evidence_v1(model, evidence)
            manifest = json.loads((evidence / "evidence-manifest.json").read_text(encoding="utf-8"))
            model["artifact"]["evidence_artifact_fingerprint"] = manifest["artifact_fingerprint"]
            return model, manifest
        except (SemanticRealizedFifoV1Error, OSError, ValueError, KeyError, TypeError):
            _abort("desktop_workflow_fifo_blocked")
    calculation_ledger = _project_schema400(payload, run)
    command = [
        "Rscript", "--vanilla", str(R_FIFO), "--ledger", str(calculation_ledger),
        "--output", str(evidence), "--tenant-id", payload["runtime"]["tenant_id"],
        "--user-id", payload["runtime"]["user_id"], "--data-space-id", payload["runtime"]["data_space_id"],
        "--portfolio-id", payload["portfolio"]["portfolio_id"], "--cutoff-at-utc", payload["cutoff_at_utc"],
    ]
    try:
        completed = subprocess.run(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
    except (OSError, subprocess.SubprocessError):
        _abort("desktop_workflow_fifo_blocked")
    if completed.returncode != 0 or completed.stdout.strip() != "realized_fifo_projection_completed" or completed.stderr:
        _abort("desktop_workflow_fifo_blocked")
    try:
        manifest = json.loads((evidence / "evidence-manifest.json").read_text(encoding="utf-8"))
        tables = {name: _read_csv(evidence / name) for name in (
            "event-results.csv", "lot-movements.csv", "remaining-lots.csv", "position-history.csv", "position-summary.csv", "currency-summary.csv"
        )}
    except Exception:
        _abort("desktop_workflow_fifo_blocked")
    artifact_ref = _opaque("rar", {"run": payload["run_id"], "input": manifest.get("input_fingerprint")})
    model = {
        "contract_version": 1, "status": "completed",
        "artifact": {
            "artifact_ref": artifact_ref, "portfolio_ref": manifest["portfolio_ref"],
            "algorithm_version": manifest["algorithm_version"], "input_fingerprint": manifest["input_fingerprint"],
            "evidence_artifact_fingerprint": manifest["artifact_fingerprint"], "evidence_cutoff_at_utc": manifest["evidence_cutoff_at_utc"],
            "rebuild_mode": "full", "base_artifact_ref": None,
            "row_set_fingerprint": _sha(tables), "completed_at_utc": _offset(payload["executed_at_utc"], 1),
            "semantic_source_bindings": [{"semantic_contract": "portfolio_ledger_v1_transaction_fact", "source_event_count": len(tables["event-results.csv"]), "projected_event_count": len(tables["event-results.csv"]), "coupled_transaction_fact": True, "automatic_cash_posting_state": "unknown"}],
            "semantic_binding_fingerprint": _sha([{"semantic_contract": "portfolio_ledger_v1_transaction_fact", "source_event_count": len(tables["event-results.csv"]), "projected_event_count": len(tables["event-results.csv"]), "coupled_transaction_fact": True, "automatic_cash_posting_state": "unknown"}]),
        },
        "tables": tables, "stale_jobs": [],
    }
    return model, manifest


def _selection(manifest: Any, portfolio_ref: str, mode: str, seed: Any):
    from migrations.reference.tax_model_plugin_v1 import TaxPluginSelection
    selection_ref = _opaque("tsr", {"portfolio": portfolio_ref, "mode": mode, "seed": seed})
    return TaxPluginSelection(selection_ref, 1, _sha({"selection": selection_ref}), portfolio_ref, mode, manifest.plugin_id, manifest.plugin_version, manifest.rules_fingerprint, manifest.manifest_fingerprint, manifest.effective_from, "active")


def _tax_module(payload: Mapping[str, Any], portfolio_ref: str, mode: str) -> tuple[Any, Path | None, Any, str]:
    """Welche Fassung des Steuermoduls der Abschluss rechnet (#486 Schritt 2).

    Die gespeicherte Auswahl dieses Portfolios und dieser Projektionsart, die am Tag der Rechnung gilt (juengstes "Gueltig ab" bis
    heute). Gibt es die gewaehlte Fassung nicht mehr, rechnet die mitgelieferte Fassung desselben Moduls - so rechnete Portelyra bis
    rc.420 immer; die Oberflaeche meldet das. Ohne Auswahl gilt wie bisher das Modul aus dem Formular des Abschlusses.
    Rueckgabe: Manifest, Ordner der Fassung (None = mitgeliefert), Auswahl und Herkunft ("selection", "selection_module_missing",
    "run_form")."""
    from migrations.reference.tax_model_plugin_v1 import TaxPluginContext, tax_plugin_manifest_v1
    from migrations.reference.tax_module_catalog_v1 import (
        TaxModuleCatalogBlocked, resolve_tax_module_v1, tax_module_manifest_v1, tax_plugin_selection_for_v1,
    )
    runtime = payload["runtime"]
    space = Path(runtime["data_root"]) / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"]
    context = TaxPluginContext(runtime["tenant_id"], runtime["user_id"], runtime["data_space_id"], "desktop_tax_worker")
    try:
        resolved = resolve_tax_module_v1(space, context, portfolio_ref, mode, payload["executed_at_utc"][:10])
    except TaxModuleCatalogBlocked:
        resolved = {"status": "no_selection", "selection": None, "entry": None}
    entry = resolved.get("entry")
    if resolved["status"] == "selected":
        root = None if entry["origin"] == "shipped" else Path(entry["plugin_root"])
        return tax_module_manifest_v1(entry), root, tax_plugin_selection_for_v1(resolved), "selection"
    if resolved["status"] == "selected_module_missing" and entry is not None:
        manifest = tax_module_manifest_v1(entry)
        return manifest, None, _selection(manifest, portfolio_ref, mode, payload["run_id"]), "selection_module_missing"
    plugin_id = PLUGIN_IDS.get(payload["tax_policy"]["mode"])
    if plugin_id is None:
        _abort("desktop_workflow_tax_blocked")
    manifest = tax_plugin_manifest_v1(plugin_id)
    return manifest, None, _selection(manifest, portfolio_ref, mode, payload["run_id"]), "run_form"


def _tax_projection_wanted(payload: Mapping[str, Any]) -> bool:
    """Ob der Umfang des Portfolios die Steuerprojektion fuehrt (#542 Baustein, #564 rc.406).

    Ohne den Baustein rechnet der Abschluss die realisierte Steuer (Steuerbericht) weiter, die Steuer auf noch nicht verkaufte
    Positionen aber nicht: Die Bewertung bekommt ein "not_selected"-Steuerartefakt, also keine Projektion, kein Nettowert und kein
    "teilweise" wegen einer fehlenden Einordnung (Festlegung 13.11.2026: angezeigt wird nur, was als Baustein gewaehlt ist).
    Gelesen nur lesend und ohne Eigentuemerkontext; nicht lesbar oder ohne Eintrag = gefuehrt, wie bisher.
    """
    try:
        from migrations.reference.portfolio_configuration_v1 import space_configuration_v1
        portfolios = space_configuration_v1(Path(payload["runtime"]["canonical_path"]).parent)["portfolios"]
        entry = portfolios.get(payload["portfolio"]["portfolio_id"])
        return entry is None or entry["configuration"]["modules"].get("tax_projection") is not False
    except Exception:
        return True


def _persisted_tax_configuration(payload: Mapping[str, Any], portfolio_ref: str, years: Sequence[int]) -> dict[str, Any] | None:
    """Die gepflegte Steuerkonfiguration statt der Formulareingabe.

    Bis hierhin setzte der Abschluss Klassifikation und Saetze je Lauf aus dem
    Formular zusammen - je Asset eine Zeile. Gepflegt wird stattdessen im Datenbereich:
    eine Vorgabe je Asset-Typ, ein Einzelfall nur bei Abweichung (#367,
    28.09.2026).

    Die oeffentlichen Kennungen beider Seiten entstehen aus derselben Formel
    (realized-fifo-public-ref-v1), sind also unmittelbar vergleichbar.

    Gibt None zurueck, wenn kein Steuerspeicher besteht oder er fuer dieses
    Portfolio nichts traegt. Dann gilt weiter das Formular - stillschweigend
    leer zu rechnen waere die schlechtere Antwort.
    """
    runtime = payload["runtime"]
    store = (Path(runtime["data_root"]) / runtime["tenant_id"] / runtime["user_id"]
             / runtime["data_space_id"] / "tax-ui" / "tax-policy.sqlite")
    if not store.is_file() or store.is_symlink():
        return None
    try:
        from migrations.reference.tax_model_plugin_v1 import TaxPluginContext
        from migrations.reference.tax_ui_workspace_v1 import (
            TaxUiBlocked, tax_ui_authorized_product_catalog_v1, tax_ui_projection_inputs_v1,
        )
        context = TaxPluginContext(runtime["tenant_id"], runtime["user_id"], runtime["data_space_id"],
                                   "desktop_tax_worker")
        data_space = Path(runtime["data_root"]) / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"]
        catalog = tax_ui_authorized_product_catalog_v1(data_space, context)
        classifications: list[dict[str, Any]] = []
        parameters: list[dict[str, Any]] = []
        seen_assets: set[str] = set()
        seen_parameters: set[tuple[int, str]] = set()
        for year in years:
            inputs = tax_ui_projection_inputs_v1(store, context, portfolio_ref, year, catalog)
            for row in inputs["classifications"]:
                if row["asset_ref"] in seen_assets:
                    continue
                seen_assets.add(row["asset_ref"])
                classifications.append({
                    "asset_ref": row["asset_ref"], "classification_code": row["classification_code"],
                    "tax_bucket": row["tax_bucket"],
                    "partial_exemption_rate_decimal": row["partial_exemption_rate_decimal"] or "0",
                    "effective_from_year": row["effective_from_year"],
                    "effective_to_year": row["effective_to_year"],
                })
            for row in inputs["parameters"]:
                key = (row["tax_year"], row["parameter_code"])
                if key in seen_parameters:
                    continue
                seen_parameters.add(key)
                if row.get("applicability_value") is not None:
                    parameters.append({"tax_year": row["tax_year"], "parameter_code": row["parameter_code"],
                                       "applicability_value": row["applicability_value"]})
                else:
                    parameters.append({"tax_year": row["tax_year"], "parameter_code": row["parameter_code"],
                                       "rate_decimal": row["rate_decimal"], "amount_decimal": row["amount_decimal"]})
    except TaxUiBlocked:
        return None
    except Exception:
        return None
    if not classifications:
        return None
    return {"classifications": classifications, "parameters": parameters}


# Wie lange das Steuermodul rechnen darf. Die Voreinstellung der Schnittstelle
# sind 30 Sekunden - sie passt zu einem einzelnen Ereignis, nicht zu einem
# Portfolio. Bei vielen Ereignissen brauchte allein die Ereignisprojektion laenger und blockierte den Abschluss mit
# tax_plugin_timeout (#368, 28.09.2026). Die Obergrenze der Schnittstelle
# liegt bei 300 Sekunden.
TAX_PLUGIN_TIMEOUT_SECONDS = 240


def _interest_module_rows(payload: Mapping[str, Any], years: Sequence[int], fp: str) -> list[dict[str, Any]]:
    """Die Zinsgutschriften der Cash-Konten des Portfolios - als Zeilen fuers Regelmodul, mit Institut und Bezeichnung.

    Festlegung (14.10.2026): Zinsen gehoeren ebenso in die Rechnung des Abschlusses wie die Vorgaenge des
    Buchungsbestands. Sie liegen im Cash-Speicher, nicht im FIFO-Ergebnis; gelesen wird ueber denselben Leser wie im
    Steuerreport und auf dem Rechenblatt. Bis zum Stichtag des Laufs; ohne Cash-Speicher gibt es keine.
    """
    from migrations.reference.asset_activity_reference_v1 import activity_reference_scope_v1
    from workers.reference.simple_tax_report_v1 import simple_tax_report_interest_rows_v1
    runtime = payload["runtime"]
    space = Path(runtime["data_root"]) / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"]
    scope = activity_reference_scope_v1({"tenant_id": runtime["tenant_id"], "user_id": runtime["user_id"], "data_space_id": runtime["data_space_id"],
                                         "actor_id": "desktop_tax_worker", "role": "desktop_owner"})
    cutoff = payload["cutoff_at_utc"][:10]
    rows = []
    for year in years:
        for item in simple_tax_report_interest_rows_v1(space, scope, year):
            key = item["source_key"]
            if key["portfolio_id"] != payload["portfolio"]["portfolio_id"] or item["local_date"] > cutoff:
                continue
            rows.append({
                "row": {
                    "event_ref": _fifo_ref("evr_", fp, "interest|" + key["event_ref"]), "effective_at_utc": key["effective_at_utc"], "local_date": item["local_date"],
                    "event_type": "interest", "account_ref": _fifo_ref("afr_", fp, key["account_ref"]), "asset_ref": _fifo_ref("asf_", fp, key["asset_id"]),
                    "asset_type": "cash", "currency": item["currency"], "quantity_decimal": "0", "gross_proceeds_decimal": "0", "realized_gross_gain_decimal": "0",
                    "gross_income_decimal": _fraction_text(item["gross_income"]), "fee_decimal": "0", "fifo_allocations": [],
                },
                # Vermoegenswert eines Zinses ist das Konto, nicht die Waehrung (#530): "Zins · Tagesgeld" statt "EUR".
                "asset_label": "Zins · " + item["account_label"] if item.get("account_label") else item["asset_label"],
            })
    return rows


def _advance_lump_sum_module(payload: Mapping[str, Any], fp: str) -> dict[str, Any]:
    """Vorabpauschalen fuer den Abschluss (#431): Zuflusszeilen und je FIFO-Verkauf die angesetzten Vorabpauschalen.

    Dieselbe Rechnung wie Report und Rechenblatt (`workers/reference/advance_lump_sum_v1.py`): Verteilung auf die Lots zum
    31.12. aus dem Lot-Nachweis des Buchungsbestands, Minderung je verkauftem Stueck. Ohne Buchung bleibt alles, wie es war.
    """
    from migrations.reference.asset_activity_reference_v1 import activity_reference_scope_v1
    from migrations.reference.desktop_product_asset_activity_v1 import _canonical_snapshot
    from workers.reference.advance_lump_sum_v1 import allocate_v1, bookings_v1, deduction_v1, inflow_date_v1, round_cents_v1, year_end_v1
    from workers.reference.asset_activity_realized_state_v2 import read_asset_activity_realized_lot_trace_v2
    runtime = payload["runtime"]
    space = Path(runtime["data_root"]) / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"]
    scope = activity_reference_scope_v1({"tenant_id": runtime["tenant_id"], "user_id": runtime["user_id"], "data_space_id": runtime["data_space_id"],
                                         "actor_id": "desktop_tax_worker", "role": "desktop_owner"})
    bookings = bookings_v1(space, scope)
    if not bookings:
        return {"inflows": [], "deductions": {}}
    snapshot = _canonical_snapshot(space / "canonical.sqlite", scope)
    accounts = {row["account_id"]: row for row in snapshot["accounts"]}
    assets = {row["asset_id"]: row for row in snapshot["assets"]}
    bookings = [row for row in bookings if (accounts.get(row["account_id"]) or {}).get("portfolio_id") == payload["portfolio"]["portfolio_id"]]
    if not bookings:
        return {"inflows": [], "deductions": {}}
    days = sorted({year_end_v1(row["calculation_year"]) for row in bookings})
    trace = read_asset_activity_realized_lot_trace_v2(space, scope, days)
    # Ohne aktuellen Lot-Nachweis laesst sich nicht sagen, welchen Anteilen eine Vorabpauschale zukommt - dann keine Steuerzahl.
    if trace["status"] != "available" or trace["freshness"] != "fresh":
        _abort("desktop_workflow_tax_blocked")
    allocation = allocate_v1(bookings, {day: [lot for world in trace["worlds"] for lot in world["account_lots_at"].get(day, [])] for day in days})
    deductions: dict[str, Fraction] = {}
    for world in trace["worlds"]:
        activity = world["asset_activity"]
        if (assets.get(activity["assets"][0]["asset_ref"]) or {}).get("asset_type") not in ("fund", "etf"):  # ETF ist ein Investmentfonds (#447)
            continue
        events = {event["event_ref"]: event for event in activity["events"]}
        for result in world["result"]["event_results"]:
            event = events[result["event_ref"]]
            if event["event_type"] != "sell":
                continue
            rest, total = Fraction(event["quantity_decimal"]), Fraction(0)
            for lot in result["consumed_lots"]:
                if not rest:
                    break
                quantity = min(rest, Fraction(lot["quantity_decimal"]))
                total += deduction_v1(allocation, lot["lot_ref"], quantity, event["local_date"], world.get("split_steps", []))
                rest -= quantity
            total = round_cents_v1(total)
            if total:
                # Die Kennung, unter der der FIFO-Lauf des Abschlusses den Verkauf fuehrt.
                deductions[_fifo_ref("evr_", fp, f"asset_activity_v1|{event['event_ref']}")] = total
    cutoff = payload["cutoff_at_utc"][:10]
    inflows = []
    for row in bookings:
        day = inflow_date_v1(row["calculation_year"])
        if day > cutoff:
            continue
        inflows.append({
            "row": {"event_ref": _fifo_ref("evr_", fp, f"advance_lump_sum|{row['asset_id']}|{row['account_id']}|{row['calculation_year']}"),
                    "effective_at_utc": day + "T00:00:00Z", "local_date": day, "event_type": "dividend",
                    "account_ref": _fifo_ref("afr_", fp, row["account_id"]), "asset_ref": _fifo_ref("asf_", fp, row["asset_id"]), "asset_type": "fund",
                    "currency": "EUR", "quantity_decimal": "0", "gross_proceeds_decimal": "0", "realized_gross_gain_decimal": "0",
                    "gross_income_decimal": row["amount_decimal"], "fee_decimal": "0", "fifo_allocations": []},
            "asset_label": (assets.get(row["asset_id"]) or {}).get("display_name") or "Fonds", "display_type": "advance_lump_sum"})
    return {"inflows": inflows, "deductions": deductions}


def _document_taxable_values(payload: Mapping[str, Any], fp: str) -> dict[str, str]:
    """Steuerpflichtig laut Beleg (#459, #536): je Verkauf und Dividende der Betrag der Bank, unter der Kennung, mit der der
    FIFO-Lauf des Abschlusses die Buchung fuehrt. Dasselbe Feld wie im Rechenblatt; ob der Betrag gilt (hoechstens 1 Euro Abstand
    zur eigenen Rechnung), prueft das Regelmodul bei jeder Rechnung selbst. Ohne Speicher keine Werte - der Abschluss rechnet wie
    bisher. Ein unlesbarer Speicher haelt die Steuer an, statt still ohne Bankwerte zu rechnen."""
    from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, activity_reference_scope_v1, read_activity_taxable_documents_v1
    runtime = payload["runtime"]
    space = Path(runtime["data_root"]) / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"]
    try:
        scope = activity_reference_scope_v1({"tenant_id": runtime["tenant_id"], "user_id": runtime["user_id"], "data_space_id": runtime["data_space_id"],
                                             "actor_id": "desktop_tax_worker", "role": "desktop_owner"})
        values = read_activity_taxable_documents_v1(space, scope)["values"]
    except AssetActivityReferenceV1Error:
        _abort("desktop_workflow_tax_blocked")
    return {_fifo_ref("evr_", fp, f"asset_activity_v1|{event_ref}"): value["taxable_eur_decimal"] for event_ref, value in values.items()}


def _with_document_values(bound: Mapping[str, Any], values: Mapping[str, str]) -> dict[str, Any]:
    """Die Eingabe des Regelmoduls mit dem Betrag laut Beleg an Verkauf und Dividende; der Pruefwert der Eingabe wird neu gebildet."""
    rows = [{**row, "document_taxable_decimal": values[row["event_ref"]]} if row["event_type"] in ("sell", "dividend") and row["event_ref"] in values else row
            for row in bound["rows"]]
    if rows == bound["rows"]:
        return dict(bound)
    from migrations.reference.realized_tax_projection_v1 import sha
    result = {**bound, "rows": rows}
    body = dict(result); body.pop("input_fingerprint")
    result["input_fingerprint"] = sha(body)
    return result


def _fraction_text(value: Any) -> str:
    fraction = Fraction(value)
    with localcontext() as exact:
        exact.prec = 200
        text = format(Decimal(fraction.numerator) / Decimal(fraction.denominator), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _tax_models(payload: Mapping[str, Any], realized: Mapping[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]], dict[str, Any]]:
    # Gewaehlter Umfang ist kein Mangel (#564, rc.406): "Nicht auswaehlen" im Run Center bzw. ein Umfang ohne Steuerbericht ist eine
    # Wahl, keine Sperre. Bis rc.405 stand die Stufe dann auf "blocked" (tax_plugin_not_selected) und der Abschluss auf "teilweise".
    if payload["tax_policy"]["mode"] == "disabled":
        return None, [], {"status": "not_selected", "failure_code": None, "plugin_label": "None"}
    try:
        from migrations.reference.tax_model_plugin_v1 import TaxPluginContext, new_tax_plugin_bound_input_v1, run_tax_model_plugin_v1, sha as plugin_sha, tax_plugin_manifest_v1
        from migrations.reference.tax_model_plugin_v2 import run_tax_model_plugin_v2
        from migrations.reference.realized_tax_projection_v1 import prepare_event_tax_plugin_input_v1, prepare_annual_tax_plugin_input_v1, validate_event_tax_candidate_v1, validate_annual_tax_candidate_v1
        from migrations.reference.realized_tax_projection_v2 import validate_event_tax_candidate_v2, validate_annual_tax_candidate_v2
        # Die Fassung aus der gespeicherten Auswahl (#486 Schritt 2); Ereignis- und Jahresmodus rechnen mit demselben Modul.
        manifest, plugin_root, event_selection, module_source = _tax_module(payload, realized["artifact"]["portfolio_ref"], "realized_event")
        plugin_id = manifest.plugin_id
        v2 = plugin_id.endswith("_v2")
        context = TaxPluginContext(payload["runtime"]["tenant_id"], payload["runtime"]["user_id"], payload["runtime"]["data_space_id"], "desktop_tax_worker")
        fp = _fifo_context_fingerprint(payload["runtime"])
        config_by_ref = {_fifo_ref("asf_", fp, row["asset_id"]): row for row in payload["asset_inputs"]}
        event_years = sorted({int(row["local_date"][:4]) for row in realized["tables"]["event-results.csv"]})
        first_year = event_years[0] if event_years else int(payload["as_of_date"][:4])
        # Mit dem Modul v2 rechnet der Abschluss das Jahr wie die Jahresrechnung der Tax-App: mit den Zinsen der Cash-Konten,
        # Kapitalertraege je Institut und den Verlusttoepfen, die Jahr fuer Jahr ab 2020 fortgeschrieben werden (14.10.2026).
        # Das Modul v1 ist als Vergleichsmodell festgeschrieben und rechnet wie bisher.
        interest: list[dict[str, Any]] = []
        if v2:
            from workers.reference.tax_annual_chain_v1 import FIRST_YEAR as CHAIN_FIRST_YEAR
            last_year = max(event_years + [int(payload["cutoff_at_utc"][:4])])
            interest = _interest_module_rows(payload, list(range(CHAIN_FIRST_YEAR, last_year + 1)), fp)
            # Vorabpauschalen (#431): Zufluss am ersten Werktag des Folgejahres - wie die Zinsen eine eigene Zeile.
            advance = _advance_lump_sum_module(payload, fp)
            interest += advance["inflows"]
            interest_years = sorted({int(item["row"]["local_date"][:4]) for item in interest})
            years = list(range(min([CHAIN_FIRST_YEAR] + event_years + interest_years), max(event_years + interest_years + [first_year]) + 1))
            first_year = min(event_years + interest_years) if event_years or interest_years else first_year
        else:
            years = event_years
        classifications = []
        definitions = {
            "de_equity_share": "capital_equity", "de_capital_instrument": "capital_general",
            "de_cash_interest": "capital_general", "de_fund": "capital_general",
            "de_private_disposal_asset": "private_disposal", "de_other_income_asset": "other_income",
        }
        for asset_ref, row in config_by_ref.items():
            code = row["tax_classification"]
            if code in definitions:
                classifications.append({
                    "asset_ref": asset_ref, "classification_code": code, "tax_bucket": definitions[code],
                    "partial_exemption_rate_decimal": row["partial_exemption_rate_decimal"] or "0",
                    "effective_from_year": first_year, "effective_to_year": None,
                })
        parameters = []
        for year in years or [first_year]:
            for code in ("capital_income_tax_rate", "personal_income_tax_rate", "solidarity_surcharge_rate"):
                rate = payload["tax_policy"][code]
                if rate is not None:
                    parameters.append({"tax_year": year, "parameter_code": code, "rate_decimal": rate, "amount_decimal": None})
            if payload["tax_policy"]["mode"] == "de_reference_v2":
                parameters.append({"tax_year": year, "parameter_code": "church_tax_applicable", "applicability_value": payload["tax_policy"]["church_tax_applicable"]})
                if payload["tax_policy"]["church_tax_rate"] is not None:
                    parameters.append({"tax_year": year, "parameter_code": "church_tax_rate", "rate_decimal": payload["tax_policy"]["church_tax_rate"], "amount_decimal": None})
        # Der gepflegte Steuerbereich hat Vorrang vor der Formulareingabe. Er
        # traegt Vorgaben je Asset-Typ; das Formular kennt nur Zeilen je Asset.
        persisted = _persisted_tax_configuration(payload, realized["artifact"]["portfolio_ref"], years or [first_year])
        tax_configuration_source = "run_form"
        if persisted is not None:
            classifications = persisted["classifications"]
            parameters = persisted["parameters"]
            tax_configuration_source = "tax_settings_store"
        bound = prepare_event_tax_plugin_input_v1(realized, event_selection, classifications, parameters, payload["cutoff_at_utc"])
        if v2:
            # Steuerpflichtig laut Beleg (#536): wie im Rechenblatt; ob der Betrag gilt, prueft das Regelmodul selbst.
            bound = _with_document_values(bound, _document_taxable_values(payload, fp))
        if v2:
            result = run_tax_model_plugin_v2(bound_input=bound, context=context, selection=event_selection, timeout_seconds=TAX_PLUGIN_TIMEOUT_SECONDS,
                                             plugin_root=plugin_root)
            rows = validate_event_tax_candidate_v2(result, bound, event_selection)
        else:
            result = run_tax_model_plugin_v1(plugin_id=plugin_id, bound_input=bound, context=context, selection=event_selection, plugin_root=plugin_root,
                                             timeout_seconds=TAX_PLUGIN_TIMEOUT_SECONDS)
            rows = validate_event_tax_candidate_v1(result, bound, event_selection)
        # Die Zinsen rechnet das Modul je Gutschrift wie jedes Ereignis; sie stehen nicht im FIFO-Ergebnis und deshalb nicht in
        # der veroeffentlichten Ereignisprojektion, deren Zeilen sich auf die FIFO-Ereignisse beziehen. Sie gehen in die
        # Jahresrechnung und als eigene Zeilen in die Anzeige der Tax-App.
        interest_rows: list[dict[str, Any]] = []
        replaced: dict[str, dict[str, Any]] = {}
        # Ein Fondsverkauf mit angesetzten Vorabpauschalen: derselbe Vorgang mit dem geminderten Gewinn (§ 19 Abs. 1 Satz 3 InvStG),
        # fuer die Jahresrechnung. Die veroeffentlichte Ereignisprojektion behaelt den Gewinn des FIFO-Ergebnisses.
        adjusted = [
            {"row": {**row, "realized_gross_gain_decimal": _fraction_text(Fraction(row["realized_gross_gain_decimal"]) - advance["deductions"][row["event_ref"]])},
             "replaces": row["event_ref"]}
            for row in bound["rows"] if row["event_type"] == "sell" and row["event_ref"] in advance["deductions"]] if v2 else []
        if interest or adjusted:
            interest_bound = new_tax_plugin_bound_input_v1(
                projection_mode="realized_event", portfolio_ref=realized["artifact"]["portfolio_ref"],
                source_artifact_ref="rar_" + plugin_sha({"interest": [item["row"]["event_ref"] for item in interest + adjusted]})[:32],
                cutoff=payload["cutoff_at_utc"], rows=[item["row"] for item in interest + adjusted], classifications=classifications, parameters=parameters)
            interest_result = run_tax_model_plugin_v2(bound_input=interest_bound, context=context, selection=event_selection, timeout_seconds=TAX_PLUGIN_TIMEOUT_SECONDS,
                                                      plugin_root=plugin_root)
            answered = {row["event_ref"]: row for row in validate_event_tax_candidate_v2(interest_result, interest_bound, event_selection)}
            interest_rows = [{**answered[item["row"]["event_ref"]], "asset_label": item["asset_label"],
                              **({"display_type": item["display_type"]} if "display_type" in item else {})} for item in interest]
            replaced = {item["replaces"]: answered[item["row"]["event_ref"]] for item in adjusted}
        readiness = "partial_blocked" if any(row["projection_status"] == "blocked" for row in rows + interest_rows) else "complete"
        event_ref = _opaque("tar", {"run": payload["run_id"], "mode": "event", "output": result.output_fingerprint})
        event = {
            "contract_version": 1, "status": "completed", "artifact": {
                "artifact_ref": event_ref, "portfolio_ref": realized["artifact"]["portfolio_ref"], "projection_mode": "realized_event",
                "tax_year": None, "source_artifact_ref": realized["artifact"]["artifact_ref"], "plugin_id": result.plugin_id,
                "plugin_version": result.plugin_version, "rules_fingerprint": result.rules_fingerprint,
                "selection_ref": event_selection.selection_ref, "plugin_input_fingerprint": result.input_fingerprint,
                "plugin_output_fingerprint": result.output_fingerprint, "rebuild_mode": "full", "base_artifact_ref": None,
                "row_set_fingerprint": _sha(rows), "readiness_status": readiness,
                "semantic_source_bindings": realized["artifact"]["semantic_source_bindings"],
                "semantic_binding_fingerprint": realized["artifact"]["semantic_binding_fingerprint"],
                "disclaimer_code": "model_projection_not_legal_advice", "completed_at_utc": _offset(payload["executed_at_utc"], 2),
            }, "rows": rows, "stale_jobs": [],
        }
        annual_models: list[dict[str, Any]] = []
        # Jahresmodus: die Auswahl fuer "realized_annual", wenn sie dieselbe Fassung meint wie der Ereignismodus; sonst rechnet er mit der
        # Fassung des Ereignismodus (zwei Fassungen in einem Abschluss passten nicht zusammen).
        annual_manifest, annual_root, annual_selection, _annual_source = _tax_module(payload, realized["artifact"]["portfolio_ref"], "realized_annual")
        if (annual_manifest.plugin_id, annual_manifest.manifest_fingerprint) != (manifest.plugin_id, manifest.manifest_fingerprint):
            annual_selection = _selection(manifest, realized["artifact"]["portfolio_ref"], "realized_annual", payload["run_id"])
        if v2:
            annual_runs = _annual_chain(payload, event, annual_selection, parameters, [replaced.get(row["event_ref"], row) for row in rows], interest_rows,
                                        years, fp, context, plugin_root=plugin_root)
        else:
            annual_runs = []
            for year in years:
                annual_bound = prepare_annual_tax_plugin_input_v1(event, annual_selection, parameters, year)
                annual_result = run_tax_model_plugin_v1(plugin_id=plugin_id, bound_input=annual_bound, context=context, selection=annual_selection,
                                                        plugin_root=plugin_root, timeout_seconds=TAX_PLUGIN_TIMEOUT_SECONDS)
                annual_runs.append((year, annual_result, validate_annual_tax_candidate_v1(annual_result, annual_bound, annual_selection, year)))
        for index, (year, annual_result, annual_rows) in enumerate(annual_runs):
            annual_readiness = "partial_blocked" if any(row["projection_status"] == "blocked" for row in annual_rows) else "complete"
            annual_models.append({
                "contract_version": 1, "status": "completed", "artifact": {
                    "artifact_ref": _opaque("tar", {"run": payload["run_id"], "year": year, "output": annual_result.output_fingerprint}),
                    "portfolio_ref": realized["artifact"]["portfolio_ref"], "projection_mode": "realized_annual", "tax_year": year,
                    "source_artifact_ref": event_ref, "plugin_id": annual_result.plugin_id, "plugin_version": annual_result.plugin_version,
                    "rules_fingerprint": annual_result.rules_fingerprint, "selection_ref": annual_selection.selection_ref,
                    "plugin_input_fingerprint": annual_result.input_fingerprint, "plugin_output_fingerprint": annual_result.output_fingerprint,
                    "rebuild_mode": "full", "base_artifact_ref": None, "row_set_fingerprint": _sha(annual_rows),
                    "readiness_status": annual_readiness, "disclaimer_code": "model_projection_not_legal_advice",
                    "semantic_source_bindings": realized["artifact"]["semantic_source_bindings"],
                    "semantic_binding_fingerprint": realized["artifact"]["semantic_binding_fingerprint"],
                    "completed_at_utc": _offset(payload["executed_at_utc"], 3 + index),
                }, "rows": annual_rows, "stale_jobs": [],
            })
        return event, annual_models, {"status": "partial" if readiness == "partial_blocked" else "completed", "failure_code": None,
                                      "plugin_label": "German reference v2" if v2 else "German reference v1", "interest_rows": interest_rows,
                                      "replaced_rows": replaced,
                                      "annual_extra_contributions": _annual_extra_contributions(rows, interest_rows, replaced)}
    except DesktopWorkflowBlocked:
        raise
    except Exception:
        _abort("desktop_workflow_tax_blocked")


def _annual_extra_contributions(rows: Sequence[Mapping[str, Any]], interest_rows: Sequence[Mapping[str, Any]],
                                replaced: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Was die Jahresrechnung ueber die veroeffentlichten FIFO-Ereignisse hinaus rechnet, je Steuerjahr und Waehrung: Zinsen und
    Zufluesse der Vorabpauschale (eigene Zeilen) und die Minderung eines Fondsgewinns um angesetzte Vorabpauschalen. Die
    Handelsanalyse gleicht damit Jahres- und Ereignisrechnung ab (ohne diese Posten bliebe der Abschluss an diesem Abgleich haengen)."""
    totals: dict[tuple[int, str], Fraction] = {}
    def add(row: Mapping[str, Any], amount: Fraction) -> None:
        key = (int(row["tax_year"]), str(row["currency"]))
        totals[key] = totals.get(key, Fraction(0)) + amount
    economic = lambda row: Fraction(row.get("realized_gross_gain_decimal") or "0") + Fraction(row.get("gross_income_decimal") or "0")
    for row in interest_rows:
        if row["projection_status"] == "completed":
            add(row, economic(row))
    originals = {row["event_ref"]: row for row in rows}
    for event_ref, row in replaced.items():
        original = originals.get(event_ref)
        if original is not None and row["projection_status"] == "completed" and original["projection_status"] == "completed":
            add(row, economic(row) - economic(original))
    return [{"tax_year": year, "currency": currency, "amount_decimal": _fraction_text(amount)}
            for (year, currency), amount in sorted(totals.items()) if amount]


def _annual_chain(payload: Mapping[str, Any], event: Mapping[str, Any], selection: Any, parameters: Sequence[Mapping[str, Any]],
                  rows: Sequence[Mapping[str, Any]], interest_rows: Sequence[Mapping[str, Any]], years: Sequence[int], fp: str,
                  context: Any, plugin_root: Path | None = None) -> list[tuple[int, Any, list[dict[str, Any]]]]:
    """Die Jahre nacheinander durchs Modul - je Institut, mit den Zinsen und den fortgeschriebenen Verlusttoepfen.

    Dieselbe Kette wie die Jahresrechnung der Tax-App (`tax_annual_chain_v1`): Freistellungsauftrag, Quellensteuer und
    Toepfe je Institut aus dem Speicher der Steuerangaben je Institut, sonst der Stand des Vorjahres.
    """
    from migrations.reference.institution_tax_settings_v1 import account_institution_keys_v1, read_institution_tax_settings_v1
    from migrations.reference.tax_model_plugin_v1 import new_tax_plugin_bound_input_v1, sha as plugin_sha
    from migrations.reference.tax_model_plugin_v2 import run_tax_model_plugin_v2
    from migrations.reference.realized_tax_projection_v2 import validate_annual_tax_candidate_v2
    from workers.reference.tax_annual_chain_v1 import annual_parameters_v1, empty_chain_v1, entered_by_year_v1, keyed_v1, next_chain_v1
    runtime = payload["runtime"]
    space = Path(runtime["data_root"]) / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"]
    owner = {"tenant_id": runtime["tenant_id"], "user_id": runtime["user_id"], "data_space_id": runtime["data_space_id"],
             "actor_id": "desktop_tax_worker", "role": "desktop_owner"}
    entered = entered_by_year_v1(read_institution_tax_settings_v1(space, owner))
    institution_of = {_fifo_ref("afr_", fp, account_id): key for account_id, key in account_institution_keys_v1(space, owner).items()}
    completed = [row for row in list(rows) + [{key: value for key, value in row.items() if key not in ("asset_label", "display_type")} for row in interest_rows]
                 if row["projection_status"] == "completed"]
    if len({row["currency"] for row in completed}) > 1:
        _abort("desktop_workflow_tax_blocked")
    chain = empty_chain_v1()
    runs = []
    for year in years:
        year_rows = [{**row, "institution_key": institution_of.get(row["account_ref"], "")} for row in completed if row["tax_year"] == year]
        year_parameters, _ = annual_parameters_v1(parameters, year, entered.get(year, {}), chain)
        bound = new_tax_plugin_bound_input_v1(projection_mode="realized_annual", portfolio_ref=event["artifact"]["portfolio_ref"],
                                              source_artifact_ref=event["artifact"]["artifact_ref"], cutoff=str(year), rows=year_rows,
                                              classifications=[], parameters=year_parameters)
        bound["semantic_source_bindings"] = event["artifact"]["semantic_source_bindings"]
        bound["semantic_binding_fingerprint"] = event["artifact"]["semantic_binding_fingerprint"]
        body = dict(bound); body.pop("input_fingerprint"); bound["input_fingerprint"] = plugin_sha(body)
        result = run_tax_model_plugin_v2(bound_input=bound, context=context, selection=selection, timeout_seconds=TAX_PLUGIN_TIMEOUT_SECONDS,
                                         plugin_root=plugin_root)
        annual_rows = validate_annual_tax_candidate_v2(result, bound, selection, year)
        detail = result.reconciliation.get("annual_detail")
        keyed = keyed_v1(year_rows, year_parameters)
        if not isinstance(detail, dict) or (keyed and detail.get("institution_grouping") is not True):
            _abort("desktop_workflow_tax_blocked")
        chain = next_chain_v1(detail, keyed)
        runs.append((year, result, annual_rows))
    return runs


def _group_model(payload: Mapping[str, Any], realized: Mapping[str, Any], event: Mapping[str, Any] | None, annual: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    try:
        from migrations.reference.realized_group_projection_v1 import build_realized_group_candidate_v1, sha as group_sha
        fp = _fifo_context_fingerprint(payload["runtime"])
        portfolio_ref = realized["artifact"]["portfolio_ref"]
        grouping_portfolio = _opaque("gpf", {"portfolio": portfolio_ref})
        asset_refs = sorted({row["asset_ref"] for row in realized["tables"]["position-summary.csv"]})
        bridge = {
            "contract_version": "asset_grouping_identity_bridge_v1",
            "portfolio_refs": [{"fifo_portfolio_ref": portfolio_ref, "grouping_portfolio_ref": grouping_portfolio}],
            "asset_refs": [{"fifo_asset_ref": ref, "grouping_asset_ref": _opaque("gas", {"asset": ref})} for ref in asset_refs],
        }
        bridge["bridge_fingerprint"] = group_sha(bridge)
        catalog = {
            "contract_version": 1, "status": "completed", "portfolio_ref": grouping_portfolio,
            "portfolio_asset_refs": [row["grouping_asset_ref"] for row in bridge["asset_refs"]], "schemes": [],
        }
        catalog["catalog_fingerprint"] = group_sha(catalog)
        return build_realized_group_candidate_v1(realized, catalog, None, bridge, event, annual[-1] if annual else None)
    except Exception:
        _abort("desktop_workflow_grouping_blocked")


def _completed_market_units(payload):
    try:
        from workers.reference.desktop_completed_market_snapshot_v1 import validate_for_run
        return validate_for_run(payload)
    except Exception:
        _abort("desktop_workflow_valuation_blocked")


def _valuation_state_days(payload: Mapping[str, Any], as_of_date: str) -> dict[str, dict[str, Any]]:
    """Der EUR-Tageswert je Asset aus dem Bewertungsstand.

    Bis hierhin bewertete der Abschluss aus Kursen, die je Asset ins Formular
    getippt wurden - bei vielen Assets kein gangbarer Weg, und die abgerufene
    Kurshistorie ging gar nicht ein. Der Stand fuehrt den Wert je Bereich und
    Tag bereits fertig in EUR, mit Herkunft und Alter (#368, 28.09.2026).

    Gelesen, nicht gerechnet. Faellt der Stand aus, gilt weiter das Formular.
    """
    # Geoeffnet wird ueber den Standleser, nicht mit einem eigenen Connect: Er
    # prueft Bindung, Schemafassung und Rechenfassung. Ohne ihn bewertete der
    # Abschluss aus einem Stand, den der Bewertungsstand selbst als veraltet
    # zurueckweist - genau die Vermischung, die die Pruefung verhindern soll
    # (eigener Fehler, bemerkt am 28.09.2026, #368).
    try:
        from migrations.reference.market_valuation_state_v1 import (
            MarketValuationStateBlocked, open_market_valuation_state_v1,
        )
        space = Path(payload["runtime"]["canonical_path"]).parent
        path = space / "market-valuation-state-v1" / "valuation-state.sqlite"
        if not path.is_file() or path.is_symlink():
            return {}
        context = {key: payload["runtime"][key] for key in ("tenant_id", "user_id", "data_space_id")}
        connection = open_market_valuation_state_v1(path, context)
        connection.row_factory = sqlite3.Row
    except MarketValuationStateBlocked:
        return {}
    except Exception:
        return {}
    try:
        rows = connection.execute(
            "SELECT s.scope_ref,s.asset_id,s.listing_ref,s.provider_symbol,s.quote_currency,d.valuation_status,d.target_decimal,"
            "d.effective_price,d.price_age_days,d.price_basis,d.price_source_date "
            "FROM valuation_scope s JOIN valuation_day d USING(scope_ref) WHERE d.trading_date=?",
            (as_of_date,)).fetchall()
        from workers.reference.portfolio_snapshot_freshness_v1 import scope_windows_v1
        scopes = scope_windows_v1(connection)
    except Exception:
        return {}
    finally:
        connection.close()
    # Bewerten zwei Bereiche eines Assets den Stichtag (Symbol- oder Anbieterwechsel), gilt die Regel aus #474 - bis rc.384
    # gewann die zuerst gelesene Zeile, bei einem frueheren Stichtag also oft der alte Bereich.
    from workers.reference.portfolio_snapshot_freshness_v1 import choose_day_rows_v1, current_symbols_v1
    chosen = choose_day_rows_v1([dict(row) for row in rows], scopes, current_symbols_v1(space), as_of_date)
    return {asset: {key: value for key, value in row.items() if key != "scope_ref"} for asset, row in chosen.items()}


def _state_market_row(day: Mapping[str, Any] | None, as_of_date: str) -> dict[str, Any] | None:
    """Eine Marktzeile aus einem Tag des Bewertungsstands - oder keine.

    Ein fortgeschriebener Wert wird als solcher gefuehrt: 'stale_price' mit dem
    Tag, von dem der Kurs stammt. Ihn als tagesaktuell auszugeben waere die
    bequemere, aber falsche Antwort.
    """
    if day is None or day["valuation_status"] not in {"complete", "substituted"}:
        return None
    close = day["target_decimal"]
    if not isinstance(close, str) or not close:
        return None
    try:
        if Decimal(close) <= 0:
            return None
    except Exception:
        return None
    source_date = day["price_source_date"]
    if not isinstance(source_date, str) or not source_date:
        return None
    try:
        age = (date.fromisoformat(as_of_date) - date.fromisoformat(source_date)).days
    except ValueError:
        return None
    if age < 0:
        return None
    return {"close_decimal": close, "price_date": source_date, "price_age_days": age,
            "price_status": "completed" if day["valuation_status"] == "complete" and age == 0 else "stale_price",
            "listing": day["listing_ref"], "basis": day["price_basis"]}


FEE_RATE_SCALE = Decimal("0.000001")


def _derived_fee_rates(realized: Mapping[str, Any]) -> tuple[dict[tuple[str, str], str], str | None]:
    """Der Gebuehrensatz je Asset aus den bisherigen Kaeufen und Verkaeufen.

    Summe der Geldgebuehren geteilt durch Summe der Umsaetze, in Prozent. Kaeufe
    zaehlen mit, weil fast jedes Asset einen Kauf hat und ein Satz sonst gar
    nicht ableitbar waere; Kauf- und Verkaufsgebuehren koennen sich
    unterscheiden, der Satz ist deshalb eine Schaetzung und heisst auch so
    (Entscheidung 28.09.2026, #367).

    Gerechnet wird je (Asset, Waehrung): Ein Verhaeltnis ueber zwei Waehrungen
    waere eine Zahl ohne Bedeutung. Zurueck kommen die Saetze je Asset und der
    Portfoliodurchschnitt als Rueckfall.
    """
    per_asset: dict[tuple[str, str], list[Decimal]] = {}
    portfolio = [Decimal(0), Decimal(0)]
    for row in realized["tables"].get("event-results.csv", ()):
        if row.get("event_type") not in {"buy", "sell"}:
            continue
        try:
            turnover = Decimal(row["amount_decimal"] or "0")
            fee = Decimal(row["fee_decimal"] or "0")
        except (InvalidOperation, TypeError):
            continue
        if turnover <= 0 or fee < 0:
            continue
        key = (row["asset_ref"], row["currency"])
        totals = per_asset.setdefault(key, [Decimal(0), Decimal(0)])
        totals[0] += fee
        totals[1] += turnover
        portfolio[0] += fee
        portfolio[1] += turnover
    rates = {key: _fee_rate_text(value[0], value[1]) for key, value in per_asset.items()
             if value[1] > 0}
    fallback = _fee_rate_text(portfolio[0], portfolio[1]) if portfolio[1] > 0 else None
    return rates, fallback


def _fee_rate_text(fee: Decimal, turnover: Decimal) -> str:
    """Der Satz in Prozent, auf sechs Nachkommastellen gerundet und ohne Nullen."""
    value = (fee / turnover * Decimal(100)).quantize(FEE_RATE_SCALE, rounding=ROUND_HALF_EVEN)
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", "0", "0E+0"} else text


def _fee_assumption(row: Mapping[str, Any], config: Mapping[str, Any] | None,
                    policy: Mapping[str, Any], rates: Mapping[tuple[str, str], str],
                    fallback: str | None, position_ref: str) -> dict[str, Any]:
    """Die Gebuehrenannahme einer Position - Einzelfall vor Laufvorgabe.

    Traegt die Asset-Karte einen Wert, gilt er; sonst die im Lauf gewaehlte
    Quelle. Leer heisst "keine Abweichung", nicht "null Gebuehr": Eine getippte
    Null ist eine Aussage, ein leeres Feld keine.
    """
    override_fixed = None if config is None else config["fixed_fee_decimal"]
    override_rate = None if config is None else config["percentage_fee_rate_decimal"]
    if override_fixed is not None or override_rate is not None:
        return {"position_ref": position_ref, "fixed_fee_decimal": override_fixed or "0",
                "percentage_rate_decimal": override_rate or "0",
                "assumption_code": "manual_desktop_liquidation_fee"}
    source = policy["source"]
    if source == "fixed_per_trade":
        return {"position_ref": position_ref, "fixed_fee_decimal": policy["fixed_decimal"],
                "percentage_rate_decimal": "0", "assumption_code": "fixed_desktop_liquidation_fee"}
    if source == "percentage_of_turnover":
        return {"position_ref": position_ref, "fixed_fee_decimal": "0",
                "percentage_rate_decimal": policy["percentage_rate_decimal"],
                "assumption_code": "percentage_desktop_liquidation_fee"}
    asset_rate = rates.get((row["asset_ref"], row["currency"]))
    if asset_rate is not None:
        return {"position_ref": position_ref, "fixed_fee_decimal": "0",
                "percentage_rate_decimal": asset_rate,
                "assumption_code": "derived_asset_transaction_fee_rate"}
    if fallback is not None:
        return {"position_ref": position_ref, "fixed_fee_decimal": "0",
                "percentage_rate_decimal": fallback,
                "assumption_code": "derived_portfolio_transaction_fee_rate"}
    # Ohne jede Transaktion mit Gebuehr gibt es nichts abzuleiten. Null zu
    # nehmen und zu schweigen waere die schlechtere Antwort; der Code sagt es.
    return {"position_ref": position_ref, "fixed_fee_decimal": "0",
            "percentage_rate_decimal": "0",
            "assumption_code": "no_transaction_fee_evidence"}


def _tax_valuation_context(payload):
    """Der Kontext der unrealisierten Bewertung - derselbe wie im Abschluss."""
    from migrations.reference.unrealized_valuation_v1 import ValuationContext
    return ValuationContext(payload["runtime"]["tenant_id"], payload["runtime"]["user_id"],
                            payload["runtime"]["data_space_id"], "desktop_portfolio_worker",
                            "portfolio_worker")


def _unrealized_tax_artifact(payload, realized, untaxed, asset_of, build_artifact):
    """Die hypothetische Liquidation - oder None, wenn sie nicht zu haben ist.

    Gebraucht wird ein gepflegtes Steuermodul fuer die Projektionsart
    `unrealized_snapshot`; ohne das bleibt es beim bisherigen Zustand
    "keine Steuerprojektion". Faellt irgendetwas aus, bleibt es ebenfalls dabei:
    Eine geschaetzte Steuer ist ein Zusatz, kein Grund, den Abschluss zu
    blockieren (#367 Schritt 2, 28.09.2026).
    """
    if payload["tax_policy"]["mode"] == "disabled":
        return None
    try:
        from migrations.reference.tax_model_plugin_v1 import TaxPluginContext, tax_plugin_manifest_v1
        from migrations.reference.tax_model_plugin_v2 import run_tax_model_plugin_v2
        from migrations.reference.unrealized_tax_projection_v1 import (
            prepare_unrealized_tax_plugin_input_v1, validate_unrealized_tax_candidate_v1,
        )
        if PLUGIN_IDS.get(payload["tax_policy"]["mode"]) is None:
            return None
        manifest, plugin_root, selection, _source = _tax_module(payload, realized["artifact"]["portfolio_ref"], "unrealized_snapshot")
        if "unrealized_snapshot" not in manifest.supported_projection_modes or not manifest.plugin_id.endswith("_v2"):
            return None
        configuration = _persisted_tax_configuration(
            payload, realized["artifact"]["portfolio_ref"], [int(payload["as_of_date"][:4])])
        if configuration is None:
            return None
        # Die Restlose tragen die FIFO-Kennung, die Bewertung ihre verschleierte.
        # Ohne diese Uebersetzung fand die Projektion zu keiner Position Lose und
        # blockierte jedes private Veraeusserungsgut mit
        # tax_holding_evidence_required (eigener Fehler, 28.09.2026).
        lots = [dict(lot, position_ref=_opaque("psr", {"fifo_position_ref": lot["position_ref"]}))
                for lot in realized["tables"].get("remaining-lots.csv", ())]
        bound = prepare_unrealized_tax_plugin_input_v1(
            untaxed, lots, selection,
            configuration["classifications"], configuration["parameters"],
            asset_ref_of=asset_of)
        if not bound["rows"]:
            return None
        context = TaxPluginContext(payload["runtime"]["tenant_id"], payload["runtime"]["user_id"],
                                   payload["runtime"]["data_space_id"], "desktop_tax_worker")
        result = run_tax_model_plugin_v2(bound_input=bound, context=context, selection=selection,
                                        timeout_seconds=TAX_PLUGIN_TIMEOUT_SECONDS, plugin_root=plugin_root)
        rows = validate_unrealized_tax_candidate_v1(result, bound, selection)
    except Exception:
        return None
    return build_artifact(
        _tax_valuation_context(payload), portfolio_ref=realized["artifact"]["portfolio_ref"],
        as_of_date=payload["as_of_date"], completed_at_utc=_offset(payload["executed_at_utc"], 6),
        status="completed", plugin_id=result.plugin_id, plugin_version=result.plugin_version,
        rules_fingerprint=result.rules_fingerprint, manifest_fingerprint=manifest.manifest_fingerprint,
        selection_ref=selection.selection_ref, plugin_input_fingerprint=result.input_fingerprint,
        plugin_output_fingerprint=result.output_fingerprint, rows=rows,
        disclaimer_codes=["model_projection_not_legal_advice",
                          "unrealized_projection_not_advice_or_liquidation_quote"])


def _owner_choice_methods(payload: Mapping[str, Any], as_of_date: str | None = None) -> dict[str, str]:
    """Die Bewertungsart je Asset, soweit der Eigentuemer es bewusst nicht ueber den Markt bewertet - am Stichtag: mit
    Bewertungs-Zeitleiste (rc.393) die Art ihres Abschnitts."""
    if payload["runtime"]["ledger_schema_version"] != 401:
        return {}
    try:
        from migrations.reference.asset_valuation_facts_v1 import OWNER_CHOICE_METHODS, asset_master_v1
        from migrations.reference.asset_valuation_timeline_v1 import timeline_v1
        space = Path(payload["runtime"]["canonical_path"]).parent
        context = {key: payload["runtime"][key] for key in ("tenant_id", "user_id", "data_space_id")}
        timeline = timeline_v1(space)
        methods = {asset_id: facts.get("valuation_method") for asset_id, facts in asset_master_v1(space, context).items()}
        if timeline and as_of_date:
            methods = {asset_id: timeline.method_on(asset_id, as_of_date, method) for asset_id, method in methods.items()}
        return {asset_id: method for asset_id, method in methods.items() if method in OWNER_CHOICE_METHODS}
    except Exception:
        return {}


def _finite_decimal(value: Any) -> str | None:
    """Ein exakter Bruch als Dezimalzahl - oder nichts, wenn er nicht endlich darstellbar ist."""
    from fractions import Fraction
    if not isinstance(value, Fraction) or value <= 0:
        return None
    denominator = value.denominator
    for prime in (2, 5):
        while denominator % prime == 0:
            denominator //= prime
    if denominator != 1:
        return None
    with localcontext() as context:
        context.prec = 80
        return format((Decimal(value.numerator) / Decimal(value.denominator)).normalize(), "f")


def _owner_market_row(payload: Mapping[str, Any], asset_id: str, state_days: Mapping[str, Mapping[str, Any]]) -> dict[str, Any] | None:
    """Der EUR-Wert je Einheit eines Assets mit eigener Bewertung - oder keiner.

    Eigene Kursangabe zuerst, sonst der letzte bestaetigte Trade-Stueckpreis
    (Festlegung 11.10.2026). Bis dahin fuehrte der Lauf solche
    Positionen als 'missing_price' und wurde dadurch 'partial', obwohl der
    Eigentuemer die Bewertungsart gewaehlt hatte. Der Preis traegt seinen Tag;
    eine fremde Waehrung wird mit dem Faktor umgerechnet, den der
    Bewertungsstand am Stichtag fuer dieselbe Waehrung verwendet hat.
    """
    from fractions import Fraction
    try:
        from migrations.reference.asset_valuation_facts_v1 import owner_valuation_v1
        space = Path(payload["runtime"]["canonical_path"]).parent
        context = {key: payload["runtime"][key] for key in ("tenant_id", "user_id", "data_space_id")}
        owner = owner_valuation_v1(space, context, asset_id, payload["as_of_date"])
        if owner["status"] != "valued":
            return None
        native = Fraction(owner["native_decimal"])
        factor = Fraction(1) if owner["native_currency"] == "EUR" else None
        if factor is None:
            for day in state_days.values():
                if (day.get("quote_currency") == owner["native_currency"] and day.get("target_decimal")
                        and day.get("effective_price") and Fraction(day["effective_price"]) > 0):
                    factor = Fraction(day["target_decimal"]) / Fraction(day["effective_price"])
                    break
        close = None if factor is None else _finite_decimal(native * factor)
        age = (date.fromisoformat(payload["as_of_date"]) - date.fromisoformat(owner["price_source_date"])).days
        if close is None or age < 0:
            return None
        return {"close_decimal": close, "price_date": owner["price_source_date"], "price_age_days": age,
                "price_basis": owner["price_basis"], "native_decimal": owner["native_decimal"],
                "native_currency": owner["native_currency"]}
    except Exception:
        return None


def _market_and_valuation(payload: Mapping[str, Any], realized: Mapping[str, Any], run: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    try:
        from migrations.reference.unrealized_valuation_v1 import (
            ValuationContext, materialize_unrealized_valuation_v1, new_unrealized_fifo_artifact_v1,
            new_unrealized_market_artifact_v1, new_unrealized_tax_artifact_v1, new_unrealized_valuation_request_v1,
        )
        fp = _fifo_context_fingerprint(payload["runtime"])
        fifo_configs = {_fifo_ref("asf_", fp, row["asset_id"]): row for row in payload["asset_inputs"]}
        configs = {_opaque("asr", {"fifo_asset_ref": ref}): config for ref, config in fifo_configs.items()}
        state_days = _valuation_state_days(payload, payload["as_of_date"])
        owner_methods = _owner_choice_methods(payload, payload["as_of_date"])
        fee_rates, fee_fallback = _derived_fee_rates(realized)
        asset_of: dict[str, str] = {}
        positions = []
        market_rows = []
        fees = []
        for row in realized["tables"]["position-summary.csv"]:
            if row["asset_type"] == "cash" or Decimal(row["remaining_quantity_decimal"] or "0") <= 0:
                continue
            config = fifo_configs.get(row["asset_ref"])
            # Was der Eigentuemer bewusst nicht ueber den Markt bewertet, ist kein
            # fehlender Kurs. 'manual' traegt seinen eigenen Wert; 'transaction_only'
            # traegt bewusst keinen und ist deshalb keine Position dieser Bewertung -
            # sie steht im Stichtags-Snapshot namentlich unter der Eigentuemerwahl.
            # Ein getippter Kurs und ein Tag im Bewertungsstand gehen beidem vor.
            owner_row = None
            method = None if config is None else owner_methods.get(config["asset_id"])
            if method is not None and state_days.get(config["asset_id"]) is None and config["close_decimal"] is None:
                if method == "transaction_only":
                    continue
                owner_row = _owner_market_row(payload, config["asset_id"], state_days)
            position_ref = _opaque("psr", {"fifo_position_ref": row["position_ref"]})
            asset_of[position_ref] = row["asset_ref"]
            account_ref = _opaque("acr", {"fifo_account_ref": row["account_ref"]})
            asset_ref = _opaque("asr", {"fifo_asset_ref": row["asset_ref"]})
            positions.append({
                "position_ref": position_ref, "account_ref": account_ref, "asset_ref": asset_ref,
                "asset_type": row["asset_type"], "basis_status": "completed", "basis_currency": row["currency"],
                "remaining_quantity_decimal": row["remaining_quantity_decimal"], "remaining_fifo_cost_decimal": row["remaining_fifo_cost_decimal"],
            })
            fees.append(_fee_assumption(row, config, payload["fee_policy"], fee_rates,
                                        fee_fallback, position_ref))
            # Der Bewertungsstand hat Vorrang vor dem Formular: Er fuehrt den
            # EUR-Tageswert je Bereich, mit Herkunft und Alter. Nur wo er nichts
            # traegt, gilt weiter der getippte Kurs (#368, 28.09.2026).
            state_row = _state_market_row(
                None if config is None else state_days.get(config["asset_id"]), payload["as_of_date"])
            if state_row is not None:
                listing = _opaque("lsr", {"asset": asset_ref, "listing": state_row["listing"]})
                market_rows.append({
                    "position_ref": position_ref, "asset_ref": asset_ref, "listing_ref": listing,
                    "market_currency": "EUR",
                    "price_date": state_row["price_date"], "price_status": state_row["price_status"],
                    "close_decimal": state_row["close_decimal"], "price_age_days": state_row["price_age_days"],
                    "revision_ref": _opaque("mrv", {"run": payload["run_id"], "position": position_ref}),
                    "revision_fingerprint": _sha({"valuation_state": state_row, "as_of": payload["as_of_date"]}),
                    "observation_at_utc": state_row["price_date"] + "T00:00:00Z",
                })
                positions[-1]["basis_currency"] = row["currency"]
                continue
            if owner_row is not None:
                market_rows.append({
                    "position_ref": position_ref, "asset_ref": asset_ref,
                    "listing_ref": _opaque("lsr", {"asset": asset_ref, "listing": owner_row["price_basis"]}),
                    "market_currency": "EUR",
                    "price_date": owner_row["price_date"], "price_status": "completed",
                    "close_decimal": owner_row["close_decimal"], "price_age_days": owner_row["price_age_days"],
                    "revision_ref": _opaque("mrv", {"run": payload["run_id"], "position": position_ref}),
                    "revision_fingerprint": _sha({"owner_valuation": owner_row, "as_of": payload["as_of_date"]}),
                    "observation_at_utc": owner_row["price_date"] + "T00:00:00Z",
                })
                positions[-1]["basis_currency"] = row["currency"]
                continue
            listing = _opaque("lsr", {"asset": asset_ref, "listing": None if config is None else config["listing_code"]})
            complete = config is not None and config["close_decimal"] is not None and config["market_currency"] is not None and config["observed_at_utc"] is not None
            market_rows.append({
                "position_ref": position_ref, "asset_ref": asset_ref, "listing_ref": listing,
                "market_currency": row["currency"] if config is None or not config["market_currency"] else config["market_currency"],
                "price_date": payload["as_of_date"], "price_status": "completed" if complete else "missing_price",
                "close_decimal": config["close_decimal"] if complete else None, "price_age_days": 0 if complete else None,
                "revision_ref": _opaque("mrv", {"run": payload["run_id"], "position": position_ref}) if complete else None,
                "revision_fingerprint": _sha({"manual": config, "as_of": payload["as_of_date"]}) if complete else None,
                "observation_at_utc": config["observed_at_utc"] if complete else None,
            })
        context = ValuationContext(payload["runtime"]["tenant_id"], payload["runtime"]["user_id"], payload["runtime"]["data_space_id"], "desktop_portfolio_worker", "portfolio_worker")
        fifo = new_unrealized_fifo_artifact_v1(context, portfolio_ref=realized["artifact"]["portfolio_ref"], source_artifact_ref=realized["artifact"]["artifact_ref"], cutoff_at_utc=payload["cutoff_at_utc"], positions=positions)
        market = new_unrealized_market_artifact_v1(context, portfolio_ref=realized["artifact"]["portfolio_ref"], as_of_date=payload["as_of_date"], prices=market_rows)
        projection_wanted = payload["tax_policy"]["mode"] != "disabled" and _tax_projection_wanted(payload)
        tax = new_unrealized_tax_artifact_v1(context, portfolio_ref=realized["artifact"]["portfolio_ref"], as_of_date=payload["as_of_date"], completed_at_utc=_offset(payload["executed_at_utc"], 5), **({"status": "not_selected"} if not projection_wanted else {"status": "unavailable", "failure_code": "no_plugin"}), disclaimer_codes=["model_projection_not_legal_advice"])
        initial_request = new_unrealized_valuation_request_v1(context, request_ref=_opaque("req", {"run": payload["run_id"], "phase": "native"}), portfolio_ref=realized["artifact"]["portfolio_ref"], as_of_date=payload["as_of_date"], target_currency=payload["portfolio"]["base_currency"], output_scale=2, fifo_artifact=fifo, market_artifact=market, tax_artifact=tax, fx_artifacts=[], fx_component_bindings=[], fee_assumptions=fees)
        preliminary = materialize_unrealized_valuation_v1(context, initial_request)
        fx_artifacts, bindings = ([], []) if "market_valuation_binding" in payload else _fx_artifacts(payload, preliminary, configs, run)
        # Ein Zwischenstand mit aufgeloester Umrechnung, aber noch ohne Steuer:
        # Erst hier steht der unrealisierte Gewinn je Position in Basiswaehrung -
        # und genau diese Zahl vergleicht die Bewertung spaeter mit der
        # Steuerzeile. Die Projektion muss sie also lesen, nicht schaetzen
        # (#367 Schritt 2, 28.09.2026).
        untaxed_request = new_unrealized_valuation_request_v1(context, request_ref=_opaque("req", {"run": payload["run_id"], "phase": "untaxed"}), portfolio_ref=realized["artifact"]["portfolio_ref"], as_of_date=payload["as_of_date"], target_currency=payload["portfolio"]["base_currency"], output_scale=2, fifo_artifact=fifo, market_artifact=market, tax_artifact=tax, fx_artifacts=fx_artifacts, fx_component_bindings=bindings, fee_assumptions=fees)
        untaxed = materialize_unrealized_valuation_v1(context, untaxed_request)
        unrealized_tax = _unrealized_tax_artifact(payload, realized, untaxed, asset_of, new_unrealized_tax_artifact_v1) if projection_wanted else None
        if unrealized_tax is not None:
            tax = unrealized_tax
        final_request = new_unrealized_valuation_request_v1(context, request_ref=_opaque("req", {"run": payload["run_id"], "phase": "display"}), portfolio_ref=realized["artifact"]["portfolio_ref"], as_of_date=payload["as_of_date"], target_currency=payload["portfolio"]["base_currency"], output_scale=2, fifo_artifact=fifo, market_artifact=market, tax_artifact=tax, fx_artifacts=fx_artifacts, fx_component_bindings=bindings, fee_assumptions=fees)
        valuation = materialize_unrealized_valuation_v1(context, final_request)
        market_status = "completed" if market_rows and all(row["price_status"] == "completed" for row in market_rows) else "partial" if market_rows else "completed"
        # Der Code hiess "manual_market_input_required" - seit die Marktzeilen aus
        # dem Bewertungsstand kommen, ist eine getippte Zahl gerade nicht der
        # vorgesehene Weg. Er sagte also das Falsche. Jetzt benennt er, was fehlt:
        # eine Kursquelle fuer die Position oder ein Kurs vom Stichtag
        # (#368, 28.09.2026).
        market_failure = None
        if market_status != "completed":
            market_failure = ("market_price_source_missing"
                              if any(row["price_status"] == "missing_price" for row in market_rows)
                              else "market_price_carried_forward")
        return valuation, market, {"status": market_status, "failure_code": market_failure}
    except DesktopWorkflowBlocked:
        raise
    except Exception:
        _abort("desktop_workflow_valuation_blocked")


def _fx_artifacts(payload: Mapping[str, Any], valuation: Mapping[str, Any], configs: Mapping[str, Mapping[str, Any]], run: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    target = payload["portfolio"]["base_currency"]
    required = [item for item in valuation["items"] if item["market_currency"] != item["basis_currency"] or item["basis_currency"] != target]
    if not required:
        return [], []
    try:
        from migrations.reference.fx_history_v1 import (
            FxHistoryContext, append_fx_history_v1, bind_fx_pair_v1, bootstrap_fx_history_store_v1,
            fx_history_job_binding_fingerprint_v1, materialize_fx_conversion_v1, new_fx_conversion_request_v1,
            new_fx_pair_binding_v1, seal_fx_history_candidate_v1,
        )
        store = run / "fx.sqlite"
        store.unlink(missing_ok=True)
        context = FxHistoryContext(payload["runtime"]["tenant_id"], payload["runtime"]["user_id"], payload["runtime"]["data_space_id"], "desktop_market_worker", "market_worker")
        bootstrap_fx_history_store_v1(store, context, _offset(payload["executed_at_utc"], 6))
        pair_by_currency: dict[str, tuple[str, str]] = {}
        evidence_by_currency: dict[str, tuple[str, str, str, str, str]] = {}
        for item in required:
            config = configs.get(item["asset_ref"])
            if config is None or config["fx_direction"] == "none" or config["fx_rate_decimal"] is None:
                continue
            currency = item["market_currency"] if item["market_currency"] != item["basis_currency"] else item["basis_currency"]
            base = config["fx_base_currency"]; quote = config["fx_quote_currency"]; direction = config["fx_direction"]
            if direction == "direct" and (base, quote) != (currency, target) or direction == "inverse" and (base, quote) != (target, currency):
                continue
            evidence = (base, quote, direction, config["fx_rate_decimal"], config["fx_observed_at_utc"])
            if currency in evidence_by_currency and evidence_by_currency[currency] != evidence:
                _abort("desktop_workflow_fx_blocked")
            evidence_by_currency[currency] = evidence
            pair_ref = _opaque("fxp", {"base": base, "quote": quote, "run": payload["run_id"]})
            if currency not in pair_by_currency:
                pair = new_fx_pair_binding_v1(pair_ref=pair_ref, base_currency=base, quote_currency=quote, market_code="MANUAL", timezone_name="UTC", calendar_code="custom_reviewed", rate_type="reference_rate", catalog_fingerprint=_sha({"pair": pair_ref, "manual": True}))
                bind_fx_pair_v1(store, context, pair, _offset(payload["executed_at_utc"], 7))
                request_ref = _opaque("fxq", {"pair": pair_ref, "run": payload["run_id"]})
                request_fp = _sha({"manual_rate": config["fx_rate_decimal"], "observed": config["fx_observed_at_utc"], "pair": pair_ref})
                source_ref = _opaque("fxs", {"run": payload["run_id"], "currency": currency})
                candidate = seal_fx_history_candidate_v1(pair_ref=pair_ref, request_ref=request_ref, source_kind="manual_reviewed_evidence", source_ref=source_ref, source_version="desktop_manual_fx_v1", plugin_id=None, plugin_version=None, plugin_manifest_fingerprint=None, request_fingerprint=request_fp, job_binding_fingerprint=fx_history_job_binding_fingerprint_v1(context, pair_ref=pair_ref, request_ref=request_ref, request_fingerprint=request_fp, source_ref=source_ref), requested_start_date=payload["as_of_date"], requested_end_date=payload["as_of_date"], retrieved_at_utc=_offset(payload["executed_at_utc"], 8), days=[{"rate_date": payload["as_of_date"], "revision_mode": "initial", "supersedes_revision_ref": None, "day_status": "observed", "rate_decimal": config["fx_rate_decimal"], "quality_status": "complete", "gap_reason": None, "source_observation_ref": _opaque("fxo", {"pair": pair_ref, "run": payload["run_id"]}), "observed_at_utc": config["fx_observed_at_utc"], "correction_reason": None}])
                append_fx_history_v1(store, context, candidate, _offset(payload["executed_at_utc"], 9))
                pair_by_currency[currency] = (pair_ref, direction)
        conversion_items = []
        bindings = []
        component_fields = {
            "market_value": "market_value_decimal", "fifo_cost": "fifo_cost_decimal",
            "unrealized_gross_gain": "unrealized_gross_gain_decimal", "projected_tax": "projected_tax_decimal",
            "liquidation_fee": "liquidation_fee_decimal", "net_liquidation": "net_liquidation_decimal",
        }
        counter = 0
        for item in required:
            market_route = pair_by_currency.get(item["market_currency"])
            if item["market_currency"] != item["basis_currency"] and market_route is not None and item["market_value_market_decimal"] is not None:
                conversion_ref = _opaque("fci", {"run": payload["run_id"], "position": item["position_ref"], "component": "market_value_basis"})
                conversion_items.append({"conversion_item_ref": conversion_ref, "effective_date": payload["as_of_date"], "native_amount_decimal": item["market_value_market_decimal"], "native_currency": item["market_currency"], "native_currency_role": "market_currency", "output_scale": 2, "route_kind": market_route[1], "selection_policy": "exact_date", "max_age_days": 0, "legs": [{"pair_ref": market_route[0], "direction": market_route[1]}]})
                bindings.append({"position_ref": item["position_ref"], "component_code": "market_value_basis", "conversion_item_ref": conversion_ref})
            route = pair_by_currency.get(item["basis_currency"])
            if item["basis_currency"] == target or route is None:
                continue
            for component, field in component_fields.items():
                amount = item[field]
                if amount is None:
                    continue
                counter += 1
                conversion_ref = _opaque("fci", {"run": payload["run_id"], "position": item["position_ref"], "component": component})
                conversion_items.append({"conversion_item_ref": conversion_ref, "effective_date": payload["as_of_date"], "native_amount_decimal": amount, "native_currency": item["basis_currency"], "native_currency_role": "reporting_currency", "output_scale": 2, "route_kind": route[1], "selection_policy": "exact_date", "max_age_days": 0, "legs": [{"pair_ref": route[0], "direction": route[1]}]})
                bindings.append({"position_ref": item["position_ref"], "component_code": component, "conversion_item_ref": conversion_ref})
        if not conversion_items:
            return [], []
        request = new_fx_conversion_request_v1(context, conversion_scope_ref=_opaque("fxc", {"run": payload["run_id"]}), target_currency=target, input_fingerprint=_sha(conversion_items), history_cutoff_at_utc=_offset(payload["executed_at_utc"], 10), items=conversion_items)
        return [materialize_fx_conversion_v1(store, context, request)], bindings
    except Exception:
        _abort("desktop_workflow_fx_blocked")


def _analysis_models(payload: Mapping[str, Any], realized: Mapping[str, Any], event: Mapping[str, Any] | None, annual: Sequence[Mapping[str, Any]], valuation: Mapping[str, Any], run: Path,
                     annual_extra: Sequence[Mapping[str, Any]] = ()) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from workers.reference.trade_analysis_artifact_v1 import build_trade_analysis_artifact_v1
        from workers.reference.market_analysis_artifact_v1 import build_market_analysis_artifact_v1
        completed = _offset(payload["executed_at_utc"], 11)
        trade = build_trade_analysis_artifact_v1(realized_read_model=realized, event_tax_read_model=event, annual_tax_read_models=annual, tenant_id=payload["runtime"]["tenant_id"], user_id=payload["runtime"]["user_id"], data_space_id=payload["runtime"]["data_space_id"], portfolio_label=payload["portfolio"]["display_name"], completed_at_utc=completed,
                                                 annual_extra_contributions=annual_extra, event_tax_selected=payload["tax_policy"]["mode"] != "disabled")
        from migrations.reference.unrealized_valuation_v1 import (
            UnrealizedValuationBlocked, ValuationContext, validate_unrealized_valuation_artifact_v1,
        )
        history = []
        center_runs = run.parent
        # Fruehere Laeufe gehen als Historie ein - aber nur, wenn ihre Bewertung die heutige Pruefung besteht. Laeufe einer
        # aelteren Fassung derselben Stichtage bestanden sie nicht; welcher Lauf je Stichtag zaehlte, entschied bis hierhin die
        # Reihenfolge der Ordnernamen - am 14.10.2026 traf es einen ungueltigen, und der ganze Abschluss blieb unveroeffentlicht.
        checker = ValuationContext(payload["runtime"]["tenant_id"], payload["runtime"]["user_id"], payload["runtime"]["data_space_id"],
                                   "market_analysis_worker", "analysis_worker")
        for candidate in sorted(center_runs.iterdir(), key=lambda path: path.name):
            internal = candidate / "internal.json"
            if candidate == run or internal.is_symlink() or not internal.is_file() or stat.S_IMODE(internal.stat().st_mode) != 0o600:
                continue
            try:
                previous = json.loads(internal.read_text(encoding="utf-8"))
                if previous.get("context_fingerprint") == _sha({key: payload["runtime"][key] for key in ("tenant_id", "user_id", "data_space_id")}) and isinstance(previous.get("valuation"), dict):
                    validate_unrealized_valuation_artifact_v1(previous["valuation"], checker)
                    if previous["valuation"].get("portfolio_ref") != realized["artifact"]["portfolio_ref"]:
                        continue
                    history.append({"source_status": "completed", "completed_at_utc": previous["completed_at_utc"], "artifact": previous["valuation"]})
            except (UnrealizedValuationBlocked, Exception):
                continue
        # Je Stichtag zaehlt der zuletzt gerechnete Lauf; der heutige kommt zuletzt und gilt fuer seinen Stichtag.
        history.sort(key=lambda row: str(row["completed_at_utc"]))
        history.append({"source_status": "completed", "completed_at_utc": completed, "artifact": valuation})
        by_date = {row["artifact"]["as_of_date"]: row for row in history}
        history = [by_date[key] for key in sorted(by_date)][-30:]
        market = build_market_analysis_artifact_v1(valuation_read_models=history, tenant_id=payload["runtime"]["tenant_id"], user_id=payload["runtime"]["user_id"], data_space_id=payload["runtime"]["data_space_id"], portfolio_ref=realized["artifact"]["portfolio_ref"], portfolio_label=payload["portfolio"]["display_name"], completed_at_utc=_offset(payload["executed_at_utc"], 12))
        return trade, market
    except Exception:
        _abort("desktop_workflow_analysis_blocked")


def _canonical_cash_balances(payload: Mapping[str, Any]) -> dict[str, str]:
    ledger = Path(payload["runtime"]["canonical_path"])
    try:
        connection = sqlite3.connect(f"{ledger.resolve(strict=True).as_uri()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        try:
            rows = connection.execute(
                """
                SELECT asset.price_currency AS currency, posting.quantity_decimal AS quantity_decimal
                FROM current_transaction_posting posting
                JOIN account ON account.account_id=posting.account_id
                JOIN asset ON asset.asset_id=posting.asset_id
                WHERE account.account_type IN ('cash','bank') AND asset.asset_type='cash'
                  AND account.portfolio_id=?
                ORDER BY asset.price_currency,posting.transaction_id,posting.sequence_no
                """,
                (payload["portfolio"]["portfolio_id"],),
            ).fetchall()
        finally:
            connection.close()
        totals: dict[str, Decimal] = {}
        with localcontext() as context:
            context.prec = 164 + len(str(max(1, len(rows))))
            for row in rows:
                currency = row["currency"]
                value = row["quantity_decimal"]
                if (not isinstance(currency, str) or re.fullmatch(r"^[A-Z]{3}$", currency) is None or
                        not isinstance(value, str) or len(value) > 80 or value == "-0" or DECIMAL.fullmatch(value) is None):
                    _abort("desktop_workflow_fifo_blocked")
                totals[currency] = totals.get(currency, Decimal(0)) + Decimal(value)
        rendered = {currency: _decimal_text(value) for currency, value in sorted(totals.items())}
        if any(len(value) > 80 or DECIMAL.fullmatch(value) is None for value in rendered.values()):
            _abort("desktop_workflow_fifo_blocked")
        return rendered
    except DesktopWorkflowBlocked:
        raise
    except Exception:
        _abort("desktop_workflow_fifo_blocked")


def _completed_asset_selection(payload, realized):
    from workers.reference.completed_asset_selection_snapshot_v1 import (
        project_completed_asset_selection_snapshot_v1, SelectionSnapshotError,
    )
    unavailable = {"version": 1, "status": "unavailable", "reason": "complete_noncash_history_required"}
    if payload["runtime"]["ledger_schema_version"] != 401:
        return unavailable
    # Called only by the explicitly authorized run producer, never by a viewer.
    ledger = Path(payload["runtime"]["ledger_path"])
    expected_ledger = payload["runtime"]["ledger_fingerprint"]
    if ledger.is_symlink() or hashlib.sha256(ledger.read_bytes()).hexdigest() != expected_ledger:
        return unavailable
    connection = sqlite3.connect(ledger.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        asset_rows = connection.execute("SELECT asset_id,display_name,asset_type FROM current_asset_revision").fetchall()
        account_rows = connection.execute("SELECT e.account_id,r.display_name FROM account_entity e JOIN current_account_revision r USING(account_id) WHERE e.portfolio_id=?", (payload["portfolio"]["portfolio_id"],)).fetchall()
    finally:
        connection.close()
    if ledger.is_symlink() or hashlib.sha256(ledger.read_bytes()).hexdigest() != expected_ledger:
        return unavailable
    fp = _fifo_context_fingerprint(payload["runtime"])
    known_assets = {_fifo_ref("asf_", fp, r["asset_id"]) for r in asset_rows}
    assets = [{"asset_ref": _fifo_ref("asf_", fp, r["asset_id"]), "asset_label": r["display_name"], "asset_type": r["asset_type"]} for r in asset_rows if r["asset_type"] != "cash"]
    accounts = [{"account_ref": _fifo_ref("afr_", fp, r["account_id"]), "account_label": r["display_name"]} for r in account_rows]
    selected = {r["asset_ref"] for r in assets}
    events = realized["tables"]["event-results.csv"]
    history = realized["tables"]["position-history.csv"]
    if any(row["asset_ref"] not in known_assets for row in events + history):
        return unavailable
    events = [dict(row) for row in events if row["asset_ref"] in selected]
    history = [dict(row) for row in history if row["asset_ref"] in selected]
    # Removing the explicitly unsupported cash domain preserves FIFO order.
    for ordinal, row in enumerate(events, 1): row["event_sequence"] = str(ordinal)
    for ordinal, row in enumerate(history, 1): row["history_sequence"] = str(ordinal)
    try:
        return project_completed_asset_selection_snapshot_v1(assets=assets, accounts=accounts,
            events=events, history=history,
            terminal_positions=[dict(row) for row in realized["tables"]["position-summary.csv"] if row["asset_ref"] in selected],
            cutoff_date=payload["as_of_date"],
            source_fingerprint=realized["artifact"]["row_set_fingerprint"],
            complete_from_genesis=realized["artifact"]["rebuild_mode"] == "full")
    except SelectionSnapshotError:
        return unavailable


def _tax_event_display_rows(event: Mapping[str, Any] | None, fifo_labels: Mapping[str, str],
                            interest_rows: Sequence[Mapping[str, Any]], replaced: Mapping[str, Mapping[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Die Ereignisse fuer die Tax-App: die des Buchungsbestands und die Zinsen der Cash-Konten, nach Datum eingereiht.

    Festlegung (14.10.2026): Zinsen gehoeren ebenso in die Rechnung wie die Vorgaenge des Buchungsbestands. Ein
    Fondsverkauf mit angesetzten Vorabpauschalen steht mit dem geminderten Gewinn da (`replaced`) - wie im Rechenblatt
    und in der Jahresrechnung; die veroeffentlichte Ereignisprojektion behaelt den Gewinn des FIFO-Laufs.
    """
    if event is None:
        return []
    swapped = replaced or {}
    shown = [(swapped.get(row["event_ref"], row), fifo_labels.get(row["asset_ref"], "Asset")) for row in event["rows"]] + [
        ({**row, "event_type": row.get("display_type", row["event_type"])}, row["asset_label"]) for row in interest_rows]
    rows = []
    for row, label in sorted(shown, key=lambda pair: pair[0]["local_date"]):
        rows.append({
            "event_ordinal": len(rows) + 1, "local_date": row["local_date"], "event_type": row["event_type"],
            "asset_label": label, "currency": row["currency"],
            "realized_gross_gain_decimal": row["realized_gross_gain_decimal"], "gross_income_decimal": row["gross_income_decimal"],
            "projected_event_tax_decimal": row["projected_event_tax_decimal"], "projected_net_gain_decimal": row["projected_net_gain_decimal"],
            "projection_status": row["projection_status"], "failure_code": row["failure_code"],
        })
    return rows


def _safe_browser(payload: Mapping[str, Any], realized: Mapping[str, Any], event: Mapping[str, Any] | None, annual: Sequence[Mapping[str, Any]], group: Mapping[str, Any], valuation: Mapping[str, Any], trade: Mapping[str, Any], market: Mapping[str, Any], stage_states: Sequence[Mapping[str, Any]], interest_rows: Sequence[Mapping[str, Any]] = (),
                  replaced_rows: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, Any]:
    fp = _fifo_context_fingerprint(payload["runtime"])
    semantic_bindings = realized["artifact"]["semantic_source_bindings"]
    semantic_summary = [{"semantic_contract": row["semantic_contract"], "source_event_count": row["source_event_count"], "projected_event_count": row["projected_event_count"], "coupled_transaction_fact": row["coupled_transaction_fact"], "automatic_cash_posting_state": row["automatic_cash_posting_state"]} for row in semantic_bindings]
    fifo_labels = {_fifo_ref("asf_", fp, row["asset_id"]): row["display_name"] for row in payload["asset_inputs"]}
    labels = {_opaque("asr", {"fifo_asset_ref": ref}): label for ref, label in fifo_labels.items()}
    configs = {_opaque("asr", {"fifo_asset_ref": _fifo_ref("asf_", fp, row["asset_id"])}): row for row in payload["asset_inputs"]}
    asset_ordinals = {ref: index for index, ref in enumerate(sorted(labels), 1)}
    account_refs = sorted({row["account_ref"] for row in valuation["items"]})
    account_ordinals = {ref: index for index, ref in enumerate(account_refs, 1)}
    valuation_positions = []
    for item in valuation["items"]:
        config = configs.get(item["asset_ref"])
        valuation_positions.append({
            "position_ordinal": len(valuation_positions) + 1, "account_ordinal": account_ordinals[item["account_ref"]],
            "asset_ordinal": asset_ordinals.get(item["asset_ref"], len(asset_ordinals) + 1), "asset_label": labels.get(item["asset_ref"], "Asset"),
            "position_status": item["position_status"], "price_status": item["price_status"], "tax_status": item["tax_status"],
            "fx_status": item["fx_status"], "market_currency": item["market_currency"], "target_currency": item["target_currency"],
            "listing_code": None if config is None else config["listing_code"], "market_observed_at_utc": None if config is None else config["observed_at_utc"],
            "fx_direction": "none" if config is None else config["fx_direction"], "fx_base_currency": None if config is None else config["fx_base_currency"],
            "fx_quote_currency": None if config is None else config["fx_quote_currency"], "fx_rate_decimal": None if config is None else config["fx_rate_decimal"],
            "fx_observed_at_utc": None if config is None else config["fx_observed_at_utc"],
            "quantity_decimal": item["remaining_quantity_decimal"], "market_price_decimal": item["market_price_decimal"],
            "market_value_decimal": item["display_market_value_decimal"], "fifo_cost_decimal": item["display_fifo_cost_decimal"],
            "unrealized_gross_gain_decimal": item["display_unrealized_gross_gain_decimal"], "projected_tax_decimal": item["display_projected_tax_decimal"],
            "liquidation_fee_decimal": item["display_liquidation_fee_decimal"], "net_liquidation_decimal": item["display_net_liquidation_decimal"],
            "failure_codes": item["failure_codes"],
        })
    event_rows = _tax_event_display_rows(event, fifo_labels, interest_rows, replaced_rows)
    annual_rows = []
    for model in annual:
        for row in model["rows"]:
            if row["row_type"] == "summary":
                annual_rows.append({key: row[key] for key in ("tax_year", "currency", "net_contribution_decimal", "projected_annual_tax_decimal", "projected_net_gain_decimal", "projection_status", "failure_code")})
    trade_periods = []
    for row in trade["period_series"]:
        trade_periods.append({key: row[key] for key in ("period_start", "period_end", "currency", "event_count", "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal", "deposit_decimal", "withdrawal_decimal", "projected_event_tax_decimal", "projected_event_net_gain_decimal", "event_tax_status")})
    market_history = []
    for row in market["portfolio_history"]:
        market_history.append({key: row[key] for key in ("as_of_date", "source_status", "snapshot_status", "target_currency", "last_covered_market_date", "max_price_age_days", "position_count", "completed_position_count", "partial_position_count", "blocked_position_count", "market_value_decimal", "fifo_cost_decimal", "unrealized_gross_gain_decimal", "projected_tax_decimal", "liquidation_fee_decimal", "net_liquidation_decimal")})
    canonical_cash = _canonical_cash_balances(payload)
    currency_rows = [{key: row[key] for key in ("currency", "realized_gross_proceeds_decimal", "realized_fifo_cost_decimal", "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal", "cash_balance_decimal", "cross_currency_aggregation")} for row in realized["tables"]["currency-summary.csv"]]
    by_currency = {row["currency"]: row for row in currency_rows}
    for currency, balance in canonical_cash.items():
        if currency in by_currency:
            by_currency[currency]["cash_balance_decimal"] = balance
        else:
            by_currency[currency] = {
                "currency": currency, "realized_gross_proceeds_decimal": "0", "realized_fifo_cost_decimal": "0",
                "realized_gross_gain_decimal": "0", "gross_income_decimal": "0", "fee_total_decimal": "0",
                "cash_balance_decimal": balance, "cross_currency_aggregation": "not_performed",
            }
    currency_rows = [by_currency[currency] for currency in sorted(by_currency)]
    group_rows = []
    for row in group["tables"]["group-metrics.csv"]:
        if row["node_kind"] == "portfolio_root":
            projected = {key: row[key] for key in ("node_kind", "display_name", "scheme_type", "currency", "asset_count", "position_count", "remaining_fifo_cost_decimal", "realized_gross_gain_decimal", "gross_income_decimal", "fee_total_decimal", "cash_balance_decimal", "event_tax_status", "projected_event_tax_decimal", "projected_net_gain_decimal", "currency_aggregation_status", "coverage_status")}
            if projected["currency"] in canonical_cash:
                projected["cash_balance_decimal"] = canonical_cash[projected["currency"]]
            group_rows.append(projected)
    overall = valuation["status"] if valuation["status"] in {"completed", "partial", "blocked"} else "partial"
    tax_readiness = ("not_selected" if payload["tax_policy"]["mode"] == "disabled" else "blocked") if event is None else event["artifact"]["readiness_status"]
    return {
        "browser_model_version": 1, "status": overall, "attempt_status": "completed", "portfolio_label": payload["portfolio"]["display_name"],
        "data_space_label": payload["data_space_label"], "revision_label": payload["run_mode"].capitalize() + " run",
        "as_of_date": payload["as_of_date"], "completed_at_utc": _offset(payload["executed_at_utc"], 13),
        "freshness_status": "current" if overall == "completed" else "partial", "stages": list(stage_states),
        "cockpit": {"currency_rows": currency_rows, "valuation_status": valuation["status"], "valuation_currency": payload["portfolio"]["base_currency"], "valuation_summary": valuation["summary"], "positions": valuation_positions},
        "tax": {"readiness_status": tax_readiness, "plugin_label": ("German reference v2" if event["artifact"]["plugin_id"].endswith("_v2") else "German reference v1") if event else "Not selected", "semantic_sources": semantic_summary, "event_rows": event_rows, "annual_rows": annual_rows, "disclaimer_code": "model_projection_not_legal_advice"},
        "grouping": {"mode": "none", "status": "completed", "coverage_status": group["coverage_status"], "currency_status": group["currency_status"], "rows": group_rows},
        "analysis": {"trade_status": trade["projection_status"], "market_status": market["projection_status"], "semantic_sources": semantic_summary, "trade_periods": trade_periods, "market_history": market_history, "positions": valuation_positions},
        "provenance": {"run_mode": payload["run_mode"], "ledger_schema_version": payload["runtime"]["ledger_schema_version"], "semantic_sources": semantic_summary, "market_source": "manual_user_input", "fx_source": "manual_reviewed_evidence", "tax_source": "explicit_optional_plugin", "cash_source": "canonical_internal_cash_postings", "provider_access": False, "network_access": False, "canonical_write": False},
    }


def _workflow_artifact(payload: Mapping[str, Any], browser: Mapping[str, Any], stage_states: Sequence[Mapping[str, Any]], attempt: str, bindings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body = {
        "desktop_workflow_artifact_version": 1, "desktop_workflow_artifact_id": _opaque("dwf", {"run": payload["run_id"], "attempt": attempt, "stages": stage_states, "completed": browser["completed_at_utc"]}),
        "status": "completed", "workflow_status": browser["status"], "attempt_status": attempt,
        "tenant_id": payload["runtime"]["tenant_id"], "user_id": payload["runtime"]["user_id"], "data_space_id": payload["runtime"]["data_space_id"],
        "completed_at_utc": browser["completed_at_utc"], "stage_states": list(stage_states), "source_bindings": bindings or {}, "browser_model": browser,
    }
    body["artifact_fingerprint"] = _sha(body)
    return body


def _publication_area(artifacts: Path, area: str) -> Path:
    return _owner_directory(artifacts / area)


def _publish(artifacts: Path, payload: Mapping[str, Any], area: str, writer_role: str, run_id: str, artifact: Mapping[str, Any], published: str) -> Any:
    try:
        from workers.reference.run_publication_v1 import PublicationRuntimeContext, publish_completed_run_v1
        runtime = PublicationRuntimeContext(payload["runtime"]["tenant_id"], payload["runtime"]["user_id"], payload["runtime"]["data_space_id"], area, f"desktop_{area}_worker", writer_role)
        return publish_completed_run_v1(_publication_area(artifacts, area), runtime, run_id, dict(artifact), published)
    except DesktopWorkflowBlocked:
        raise
    except Exception:
        _abort("desktop_workflow_publication_blocked")


def _prior_browser(payload: Mapping[str, Any], artifacts: Path) -> dict[str, Any] | None:
    try:
        from apps.reference.latest_run_reader_v1 import LatestRunReaderContext, read_latest_completed_run_v1
        context = LatestRunReaderContext(payload["runtime"]["tenant_id"], payload["runtime"]["user_id"], payload["runtime"]["data_space_id"], "desktop_workflow", "viewer")
        artifact = read_latest_completed_run_v1(artifacts / "desktop_workflow", context)
        return artifact["browser_model"] if artifact["attempt_status"] == "completed" else artifact["browser_model"]
    except Exception:
        return None


def _stage_states_valid(states: Any, *, complete: bool) -> bool:
    if not isinstance(states, list) or complete and len(states) != len(STAGE_NAMES) or not complete and len(states) > len(STAGE_NAMES):
        return False
    for index, row in enumerate(states):
        if not isinstance(row, dict) or set(row) != {"stage_code", "status", "failure_code"} or row["stage_code"] != STAGE_NAMES[index] or row["status"] not in ({"completed", "partial", "stale", "blocked", "not_selected"} if row["stage_code"] == "tax" else {"completed", "partial", "stale", "blocked"}):
            return False
        failure = row["failure_code"]
        if failure is not None and (not isinstance(failure, str) or re.fullmatch(r"[a-z][a-z0-9_]{2,80}", failure) is None):
            return False
    return True


def _progress_stage_states(completed: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    states = [dict(row) for row in completed]
    if not _stage_states_valid(states, complete=False) or [row.get("stage_code") for row in states] != list(STAGE_NAMES[:len(states)]):
        _abort("desktop_workflow_storage_invalid")
    for index, name in enumerate(STAGE_NAMES[len(states):]):
        states.append({"stage_code": name, "status": "blocked", "failure_code": "run_in_progress" if index == 0 else None})
    return states


def _unread_semantic_sources(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Herkunft eines Laufs, der den Ledger nie gelesen hat.

    Ein blockierter oder laufender Lauf kennt seine Ereigniszahlen noch nicht.
    Er darf sie deshalb nicht behaupten: Die Zaehler stehen auf null und der
    Cash-Zustand auf 'unknown' - den Wert fuehrt das Schema genau dafuer. Die
    Kopplung folgt dem semantischen Vertrag und ist damit bekannt.

    Ohne diese Angaben fehlten dem Artefakt zwei Pflichtfelder seines eigenen
    Anzeigeschemas. Der blockierte Lauf wurde dann zwar veroeffentlicht und zum
    juengsten Stand, war aber unlesbar: Cockpit und Steuer zeigten
    'display_reader_failed' statt "Lauf blockiert" (Befund
    28.09.2026, #368).
    """
    contracts = payload["runtime"]["semantic_contracts"] or ["asset_activity_v1"]
    return [{"semantic_contract": name, "source_event_count": 0, "projected_event_count": 0,
             "coupled_transaction_fact": name == "portfolio_ledger_v1_transaction_fact",
             "automatic_cash_posting_state": "unknown"} for name in contracts]


def _publish_progress(payload: Mapping[str, Any], artifacts: Path, completed: Sequence[Mapping[str, Any]]) -> None:
    previous = _prior_browser(payload, artifacts)
    stages = _progress_stage_states(completed)
    if previous is None or previous.get("cockpit") is None:
        browser = {"browser_model_version": 1, "status": "blocked", "attempt_status": "running", "portfolio_label": payload["portfolio"]["display_name"], "data_space_label": payload["data_space_label"], "revision_label": payload["run_mode"].capitalize() + " run", "as_of_date": payload["as_of_date"], "completed_at_utc": payload["executed_at_utc"], "freshness_status": "missing", "stages": stages, "cockpit": None, "tax": None, "grouping": None, "analysis": None, "provenance": {"run_mode": payload["run_mode"], "ledger_schema_version": payload["runtime"]["ledger_schema_version"], "semantic_sources": _unread_semantic_sources(payload), "market_source": "manual_user_input", "fx_source": "manual_reviewed_evidence", "tax_source": "explicit_optional_plugin", "provider_access": False, "network_access": False, "canonical_write": False}}
    else:
        browser = json.loads(json.dumps(previous)); browser.update({"status": "stale", "attempt_status": "running", "freshness_status": "stale", "stages": stages})
    artifact = _workflow_artifact(payload, browser, stages, "running")
    suffix = "started" if not completed else f"progress_{len(completed):02d}"
    _publish(artifacts, payload, "desktop_workflow", "desktop_workflow_worker", payload["run_id"] + "_" + suffix, artifact, _offset(payload["executed_at_utc"], len(completed)))


def _publish_start(payload: Mapping[str, Any], artifacts: Path) -> None:
    _publish_progress(payload, artifacts, [])


def _blocked_stage_states(code: str, payload: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    # Ohne gewaehlte Steuer (#564) heisst die Steuerstufe auch in einem angehaltenen Lauf "not_selected", nicht "completed".
    untaxed = isinstance(payload, Mapping) and isinstance(payload.get("tax_policy"), Mapping) and payload["tax_policy"].get("mode") == "disabled"
    failure_stage = {
        "desktop_workflow_fifo_blocked": "fifo", "desktop_workflow_tax_blocked": "tax",
        "desktop_workflow_grouping_blocked": "grouping", "desktop_workflow_market_blocked": "market",
        "desktop_workflow_fx_blocked": "fx", "desktop_workflow_valuation_blocked": "valuation",
        "desktop_workflow_analysis_blocked": "trade_analysis", "desktop_workflow_publication_blocked": "publication",
    }.get(code)
    if failure_stage is None:
        return [{"stage_code": name, "status": "blocked", "failure_code": code if index == 0 else None} for index, name in enumerate(STAGE_NAMES)]
    failed_at = STAGE_NAMES.index(failure_stage)
    return [{"stage_code": name, "status": ("not_selected" if untaxed and name == "tax" else "completed") if index < failed_at else "blocked",
             "failure_code": code if index == failed_at else None} for index, name in enumerate(STAGE_NAMES)]


def _publish_blocked(payload: Mapping[str, Any], artifacts: Path, code: str) -> None:
    previous = _prior_browser(payload, artifacts)
    if previous is None or previous.get("attempt_status") == "running" and previous.get("cockpit") is None:
        browser = {"browser_model_version": 1, "status": "blocked", "attempt_status": "blocked", "portfolio_label": payload["portfolio"]["display_name"], "data_space_label": payload["data_space_label"], "revision_label": payload["run_mode"].capitalize() + " run", "as_of_date": payload["as_of_date"], "completed_at_utc": _offset(payload["executed_at_utc"], 14), "freshness_status": "missing", "stages": [], "cockpit": None, "tax": None, "grouping": None, "analysis": None, "provenance": {"run_mode": payload["run_mode"], "ledger_schema_version": payload["runtime"]["ledger_schema_version"], "semantic_sources": _unread_semantic_sources(payload), "market_source": "manual_user_input", "fx_source": "manual_reviewed_evidence", "tax_source": "explicit_optional_plugin", "provider_access": False, "network_access": False, "canonical_write": False}}
    else:
        browser = json.loads(json.dumps(previous)); browser.update({"status": "stale", "attempt_status": "blocked", "freshness_status": "stale"})
    stages = _blocked_stage_states(code, payload)
    browser["stages"] = stages
    artifact = _workflow_artifact(payload, browser, stages, "blocked")
    _publish(artifacts, payload, "desktop_workflow", "desktop_workflow_worker", payload["run_id"] + "_blocked", artifact, _offset(payload["executed_at_utc"], 14))


def _completed_publication_exists(payload: Mapping[str, Any], artifacts: Path) -> bool:
    candidate = artifacts / "desktop_workflow" / "runs" / (payload["run_id"] + "_completed")
    if not candidate.exists() and not candidate.is_symlink():
        return False
    try:
        from workers.reference.run_publication_v1 import _validate_completed_run
        manifest, artifact = _validate_completed_run(candidate)
    except Exception:
        _abort("desktop_workflow_storage_invalid")
    if manifest.get("artifact_contract") != "desktop_workflow_v1" or artifact.get("attempt_status") != "completed" or not all(artifact.get(key) == payload["runtime"][key] for key in ("tenant_id", "user_id", "data_space_id")):
        _abort("desktop_workflow_storage_invalid")
    return True


def _run_desktop_workflow_impl_v1(job_path: str | Path) -> dict[str, Any]:
    payload = _load_job(Path(job_path))
    # Ein Auftrag traegt absolute Pfade. Nach einem Restore an einen anderen Ort (#493) zeigte ein fortgesetzter alter Auftrag sonst auf den
    # alten Datenraum und schriebe dorthin. Liegt er in einem Run Center (in der App immer), muss es das seines Ziels sein - geprueft, bevor
    # dort irgendetwas angelegt wird.
    runtime = payload["runtime"]
    try:
        folder = Path(job_path).resolve(strict=True).parent
        target = Path(runtime["data_root"]).resolve() / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"] / "run-center" / "jobs"
        foreign = folder.name == "jobs" and folder.parent.name == "run-center" and folder != target
    except OSError:
        foreign = True
    if foreign:
        _abort("desktop_workflow_context_mismatch")
    _, _, run, artifacts = _runtime_paths(payload)
    state_path = run / "state.json"
    resuming = False
    if state_path.exists() or state_path.is_symlink():
        if state_path.is_symlink() or not state_path.is_file() or stat.S_IMODE(state_path.stat().st_mode) != 0o600:
            _abort("desktop_workflow_storage_invalid")
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _abort("desktop_workflow_storage_invalid")
        if not isinstance(state, dict) or state.get("contract_version") != 1 or state.get("status") not in {"running", "completed", "blocked"} or not _stage_states_valid(state.get("stage_states"), complete=True) or state.get("failure_code") is not None and state.get("failure_code") not in ERROR_CODES:
            _abort("desktop_workflow_storage_invalid")
        if state["status"] in {"completed", "blocked"}:
            return {"status": state["status"], "run_label": payload["run_mode"] + " run", "failure_code": state.get("failure_code"), "stage_states": state["stage_states"], "replayed": True}
        resuming = True
    if payload["run_mode"] == "incremental" and _prior_browser(payload, artifacts) is None:
        _abort("desktop_workflow_full_rebuild_required")
    completed_publication_exists = resuming and _completed_publication_exists(payload, artifacts)
    if not resuming:
        initial = _progress_stage_states([])
        _replace_json(state_path, {"contract_version": 1, "status": "running", "failure_code": None, "stage_states": initial})
        _publish_start(payload, artifacts)

    def checkpoint(states: Sequence[Mapping[str, Any]]) -> None:
        _replace_json(state_path, {"contract_version": 1, "status": "running", "failure_code": None, "stage_states": _progress_stage_states(states)})
        if not completed_publication_exists:
            _publish_progress(payload, artifacts, states)

    try:
        completed_units = _completed_market_units(payload) if "market_valuation_binding" in payload else None
        realized, fifo_manifest = _run_fifo(payload, run)
        stages: list[dict[str, Any]] = [
            {"stage_code": "canonical", "status": "completed", "failure_code": None},
            {"stage_code": "fifo", "status": "completed", "failure_code": None},
        ]
        checkpoint(stages)
        event, annual, tax_state = _tax_models(payload, realized)
        stages.append({"stage_code": "tax", "status": tax_state["status"], "failure_code": tax_state["failure_code"]})
        checkpoint(stages)
        group = _group_model(payload, realized, event, annual)
        stages.append({"stage_code": "grouping", "status": "completed", "failure_code": None})
        checkpoint(stages)
        valuation, market_input, market_state = _market_and_valuation(payload, realized, run)
        stages.extend([
            {"stage_code": "market", "status": market_state["status"], "failure_code": market_state["failure_code"]},
            {"stage_code": "fx", "status": "completed" if all(item["fx_status"] in {"native", "completed"} for item in valuation["items"]) else "partial", "failure_code": None},
            {"stage_code": "valuation", "status": valuation["status"], "failure_code": None},
        ])
        checkpoint(stages)
        trade, market = _analysis_models(payload, realized, event, annual, valuation, run, tax_state.get("annual_extra_contributions", []))
        stages.extend([
            {"stage_code": "trade_analysis", "status": trade["projection_status"], "failure_code": None},
            {"stage_code": "market_analysis", "status": market["projection_status"], "failure_code": None},
        ])
        checkpoint(stages)
        stages.append({"stage_code": "publication", "status": "completed", "failure_code": None})
        browser = _safe_browser(payload, realized, event, annual, group, valuation, trade, market, stages, tax_state.get("interest_rows", []),
                                tax_state.get("replaced_rows", {}))
        browser["asset_selection_snapshot"] = _completed_asset_selection(payload, realized)
        if completed_units is not None:
            try:
                from workers.reference.desktop_completed_market_snapshot_v1 import project
                asset_lookup = {_fifo_ref("asf_", _fifo_context_fingerprint(payload["runtime"]), row["asset_id"]): row for row in payload["asset_inputs"]}
                browser["exact_market_snapshot"] = project(realized["tables"]["position-summary.csv"], asset_lookup,
                                                           completed_units, payload["market_valuation_binding"])
            except Exception:
                _abort("desktop_workflow_valuation_blocked")
        if completed_units is not None and _completed_market_units(payload) != completed_units:
            _abort("desktop_workflow_valuation_blocked")
        trade_result = _publish(artifacts, payload, "trade_analysis", "analysis_worker", payload["run_id"] + "_trade", trade, _offset(payload["executed_at_utc"], 13))
        market_result = _publish(artifacts, payload, "market_analysis", "analysis_worker", payload["run_id"] + "_market", market, _offset(payload["executed_at_utc"], 13))
        if completed_units is not None and _completed_market_units(payload) != completed_units:
            _abort("desktop_workflow_valuation_blocked")
        calculation_keys = ("cockpit", "tax", "grouping", "analysis", "asset_selection_snapshot") + (("exact_market_snapshot",) if completed_units is not None else ())
        bindings = {"trade_run_id": trade_result.run_id, "market_run_id": market_result.run_id, "calculation_fingerprint": _sha({key: browser[key] for key in calculation_keys}), "semantic_binding_fingerprint": realized["artifact"]["semantic_binding_fingerprint"]}
        workflow = _workflow_artifact(payload, browser, stages, "completed", bindings)
        _publish(artifacts, payload, "desktop_workflow", "desktop_workflow_worker", payload["run_id"] + "_completed", workflow, _offset(payload["executed_at_utc"], 13))
        internal = {"contract_version": 1, "context_fingerprint": _sha({key: payload["runtime"][key] for key in ("tenant_id", "user_id", "data_space_id")}), "completed_at_utc": _offset(payload["executed_at_utc"], 13), "valuation": valuation, "market_input": market_input, "fifo_manifest_fingerprint": fifo_manifest["artifact_fingerprint"], "semantic_source_bindings": realized["artifact"]["semantic_source_bindings"], "semantic_binding_fingerprint": realized["artifact"]["semantic_binding_fingerprint"], "event_tax_semantic_binding_fingerprint": None if event is None else event["artifact"]["semantic_binding_fingerprint"], "annual_tax_semantic_binding_fingerprints": [model["artifact"]["semantic_binding_fingerprint"] for model in annual], "group_semantic_source_bindings": group["semantic_source_bindings"], "group_semantic_binding_fingerprint": group["semantic_binding_fingerprint"]}
        internal_path = run / "internal.json"
        if internal_path.is_file() and not internal_path.is_symlink():
            try:
                if json.loads(internal_path.read_text(encoding="utf-8")) != internal:
                    _abort("desktop_workflow_storage_invalid")
            except (OSError, json.JSONDecodeError):
                _abort("desktop_workflow_storage_invalid")
        else:
            _atomic_json(internal_path, internal)
        _replace_json(state_path, {"contract_version": 1, "status": "completed", "failure_code": None, "stage_states": stages, "calculation_fingerprint": bindings["calculation_fingerprint"]})
        return {"status": "completed", "run_label": payload["run_mode"] + " run", "failure_code": None, "stage_states": stages, "replayed": False}
    except DesktopWorkflowBlocked as error:
        blocked_stages = _blocked_stage_states(error.code, payload)
        try:
            _publish_blocked(payload, artifacts, error.code)
        except Exception:
            pass
        _replace_json(state_path, {"contract_version": 1, "status": "blocked", "failure_code": error.code, "stage_states": blocked_stages})
        return {"status": "blocked", "run_label": payload["run_mode"] + " run", "failure_code": error.code, "stage_states": blocked_stages, "replayed": False}
    except Exception:
        code = "desktop_workflow_boundary_failed"
        blocked_stages = _blocked_stage_states(code, payload)
        try:
            _publish_blocked(payload, artifacts, code)
        except Exception:
            pass
        _replace_json(state_path, {"contract_version": 1, "status": "blocked", "failure_code": code, "stage_states": blocked_stages})
        return {"status": "blocked", "run_label": payload["run_mode"] + " run", "failure_code": code, "stage_states": blocked_stages, "replayed": False}


def run_desktop_workflow_v1(job_path: str | Path) -> dict[str, Any]:
    previous_umask = os.umask(0o077)
    try:
        return _run_desktop_workflow_impl_v1(job_path)
    finally:
        os.umask(previous_umask)


def desktop_workflow_error_codes_v1() -> tuple[str, ...]:
    return tuple(sorted(ERROR_CODES))


__all__ = ["DesktopWorkflowBlocked", "desktop_workflow_error_codes_v1", "run_desktop_workflow_v1"]
