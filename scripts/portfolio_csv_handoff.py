#!/usr/bin/env python3
"""Strict JSON-stdin bridge for separate staged Portfolio CSV domain handoffs."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations.reference.portfolio_csv_exchange_v1 import PortfolioCsvContextV1  # noqa: E402
from migrations.reference.portfolio_csv_handoffs_v1 import (  # noqa: E402
    PortfolioCsvHandoffV1Error,
    apply_portfolio_csv_asset_activity_handoff_v1,
    apply_portfolio_csv_catalog_handoff_v1,
    apply_portfolio_csv_cash_handoff_v1,
    apply_portfolio_csv_handoff_recovery_v1,
    apply_portfolio_csv_transaction_handoff_v1,
    build_portfolio_csv_handoff_confirmation_v1,
    build_portfolio_csv_handoff_recovery_confirmation_v1,
    preview_portfolio_csv_asset_activity_handoff_v1,
    preview_portfolio_csv_catalog_handoff_v1,
    preview_portfolio_csv_cash_handoff_v1,
    preview_portfolio_csv_handoff_recovery_v1,
    preview_portfolio_csv_transaction_handoff_v1,
    read_portfolio_csv_cash_candidates_v1,
    read_portfolio_csv_handoff_recovery_candidates_v1,
    read_portfolio_csv_staged_imports_v1,
    resolve_portfolio_csv_cash_candidate_v1,
)

MAX_INPUT_BYTES = 32_000_000
DOMAINS = ("catalog", "transaction", "activity", "cash")


class _InputError(ValueError):
    pass


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")))


def _reject_constant(value: str) -> None:
    raise _InputError(value)


def _closed_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _InputError("duplicate_key")
        result[key] = value
    return result


def _payload(command: str) -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise _InputError("input_size")
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant, object_pairs_hook=_closed_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _InputError("strict_json") from error
    preview = {"context", "data_space_path", "canonical_path", "staged_import_handle"}
    confirmation = {"context", "trusted_preview", "confirmation_ref", "issued_at_utc", "expires_at_utc"}
    apply = {"context", "data_space_path", "canonical_path", "trusted_preview", "confirmation", "applied_at_utc"}
    fields = {
        **{f"{domain}-preview": preview for domain in DOMAINS},
        **{f"{domain}-confirmation": confirmation for domain in DOMAINS},
        **{f"{domain}-apply": apply for domain in DOMAINS},
        "staged-imports": {"context", "data_space_path"},
        "recovery-candidates": {"context", "data_space_path"},
        "recovery-preview": {"context", "data_space_path", "canonical_path", "recovery_ref"},
        "recovery-confirmation": {"context", "trusted_recovery_preview", "confirmation_ref", "issued_at_utc", "expires_at_utc"},
        "recovery-apply": {"context", "data_space_path", "canonical_path", "trusted_recovery_preview", "recovery_confirmation", "recovered_at_utc"},
        "cash-candidates": {"context", "data_space_path", "canonical_path", "staged_import_handle"},
        "cash-candidate": {"context", "data_space_path", "canonical_path", "staged_import_handle", "candidate_ref"},
    }[command]
    if not isinstance(value, dict) or set(value) != fields:
        raise _InputError("fields")
    return value


def _context(value: Any) -> PortfolioCsvContextV1:
    fields = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}
    if not isinstance(value, dict) or set(value) != fields:
        raise _InputError("context")
    return PortfolioCsvContextV1(**value)


def main() -> int:
    commands = tuple(f"{domain}-{operation}" for domain in DOMAINS for operation in ("preview", "confirmation", "apply")) + (
        "staged-imports", "recovery-candidates", "recovery-preview", "recovery-confirmation", "recovery-apply",
        "cash-candidates", "cash-candidate",
    )
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        _emit({"status": "blocked", "code": "portfolio_csv_handoff_boundary_failed"})
        return 2
    command = sys.argv[1]
    preview_functions = {
        "catalog": preview_portfolio_csv_catalog_handoff_v1,
        "transaction": preview_portfolio_csv_transaction_handoff_v1,
        "activity": preview_portfolio_csv_asset_activity_handoff_v1,
        "cash": preview_portfolio_csv_cash_handoff_v1,
    }
    apply_functions = {
        "catalog": apply_portfolio_csv_catalog_handoff_v1,
        "transaction": apply_portfolio_csv_transaction_handoff_v1,
        "activity": apply_portfolio_csv_asset_activity_handoff_v1,
        "cash": apply_portfolio_csv_cash_handoff_v1,
    }
    try:
        value = _payload(command); context = _context(value["context"])
        domain = command.split("-")[0]
        if command in {f"{item}-preview" for item in DOMAINS}:
            output = preview_functions[domain](Path(value["data_space_path"]), Path(value["canonical_path"]), context, value["staged_import_handle"])
            _emit({"status": "previewed", **output})
        elif command in {f"{item}-confirmation" for item in DOMAINS}:
            output = build_portfolio_csv_handoff_confirmation_v1(value["trusted_preview"], context, value["confirmation_ref"], value["issued_at_utc"], value["expires_at_utc"])
            _emit({"status": "confirmation_built", "confirmation": output})
        elif command in {f"{item}-apply" for item in DOMAINS}:
            output = apply_functions[domain](Path(value["data_space_path"]), Path(value["canonical_path"]), context, value["trusted_preview"], value["confirmation"], value["applied_at_utc"])
            _emit({"status": "applied", "result": output})
        elif command == "staged-imports":
            _emit(read_portfolio_csv_staged_imports_v1(Path(value["data_space_path"]), context))
        elif command == "recovery-candidates":
            _emit(read_portfolio_csv_handoff_recovery_candidates_v1(Path(value["data_space_path"]), context))
        elif command == "recovery-preview":
            output = preview_portfolio_csv_handoff_recovery_v1(Path(value["data_space_path"]), Path(value["canonical_path"]), context, value["recovery_ref"])
            _emit({"status": "recovery_previewed", **output})
        elif command == "recovery-confirmation":
            output = build_portfolio_csv_handoff_recovery_confirmation_v1(value["trusted_recovery_preview"], context, value["confirmation_ref"], value["issued_at_utc"], value["expires_at_utc"])
            _emit({"status": "recovery_confirmation_built", "confirmation": output})
        elif command == "recovery-apply":
            output = apply_portfolio_csv_handoff_recovery_v1(Path(value["data_space_path"]), Path(value["canonical_path"]), context, value["trusted_recovery_preview"], value["recovery_confirmation"], value["recovered_at_utc"])
            _emit({"status": "recovery_applied", "result": output})
        elif command == "cash-candidates":
            _emit(read_portfolio_csv_cash_candidates_v1(Path(value["data_space_path"]), Path(value["canonical_path"]), context, value["staged_import_handle"]))
        else:
            _emit(resolve_portfolio_csv_cash_candidate_v1(Path(value["data_space_path"]), Path(value["canonical_path"]), context, value["staged_import_handle"], value["candidate_ref"]))
        return 0
    except _InputError:
        _emit({"status": "blocked", "code": "portfolio_csv_handoff_boundary_failed"})
        return 2
    except PortfolioCsvHandoffV1Error as error:
        _emit({"status": "blocked", "code": error.code})
        return 2
    except (KeyError, TypeError):
        _emit({"status": "blocked", "code": "portfolio_csv_handoff_boundary_failed"})
        return 2
    except Exception:
        _emit({"status": "failed", "code": "portfolio_csv_handoff_boundary_failed"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
