#!/usr/bin/env python3
"""Strict JSON-stdin bridge for create-only Cash schema-2900 -> 2901 migration."""
from __future__ import annotations

from dataclasses import asdict
import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations.reference.cash_coverage_store_migration_v2900_to_v2901 import (  # noqa: E402
    apply_cash_coverage_store_migration_recovery_v1,
    apply_cash_coverage_store_migration_v2900_to_v2901,
    build_cash_coverage_store_migration_confirmation_v1,
    build_cash_coverage_store_migration_recovery_confirmation_v1,
    preview_cash_coverage_store_migration_recovery_v1,
    preview_cash_coverage_store_migration_v2900_to_v2901,
)
from migrations.reference.desktop_cash_coverage_v1 import DesktopCashCoverageV1Error  # noqa: E402
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1  # noqa: E402

MAX_INPUT_BYTES = 32_000_000


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
        value = json.loads(
            raw.decode("utf-8"), parse_constant=_reject_constant,
            object_pairs_hook=_closed_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _InputError("strict_json") from error
    fields = {
        "preview": {"context", "source_store_path", "target_data_space_path", "canonical_path"},
        "confirmation": {"context", "trusted_preview", "confirmation_ref", "issued_at_utc", "expires_at_utc"},
        "apply": {"context", "source_store_path", "target_data_space_path", "canonical_path", "trusted_preview", "confirmation", "migrated_at_utc"},
        "recovery-preview": {"context", "source_store_path", "target_data_space_path", "canonical_path", "trusted_preview", "original_confirmation"},
        "recovery-confirmation": {"context", "trusted_recovery_preview", "confirmation_ref", "issued_at_utc", "expires_at_utc"},
        "recovery-apply": {"context", "source_store_path", "target_data_space_path", "canonical_path", "trusted_preview", "original_confirmation", "trusted_recovery_preview", "recovery_confirmation", "recovered_at_utc"},
    }[command]
    if not isinstance(value, dict) or set(value) != fields:
        raise _InputError("fields")
    return value


def _context(value: Any) -> DesktopProductAssetActivityContextV1:
    fields = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}
    if not isinstance(value, dict) or set(value) != fields:
        raise _InputError("context")
    return DesktopProductAssetActivityContextV1(**value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Portelyra Cash store migration v2900 to v2901")
    parser.add_argument("command", choices=("preview", "confirmation", "apply", "recovery-preview", "recovery-confirmation", "recovery-apply"))
    arguments = parser.parse_args()
    try:
        value = _payload(arguments.command)
        context = _context(value["context"])
        if arguments.command == "preview":
            output = preview_cash_coverage_store_migration_v2900_to_v2901(
                Path(value["source_store_path"]), Path(value["target_data_space_path"]),
                Path(value["canonical_path"]), context,
            )
            _emit({"status": "previewed", **output})
        elif arguments.command == "confirmation":
            confirmation = build_cash_coverage_store_migration_confirmation_v1(
                value["trusted_preview"], context, value["confirmation_ref"],
                value["issued_at_utc"], value["expires_at_utc"],
            )
            _emit({"status": "confirmation_built", "confirmation": confirmation})
        elif arguments.command == "apply":
            result = apply_cash_coverage_store_migration_v2900_to_v2901(
                Path(value["source_store_path"]), Path(value["target_data_space_path"]),
                Path(value["canonical_path"]), context, value["trusted_preview"],
                value["confirmation"], value["migrated_at_utc"],
            )
            _emit({"status": "applied", "result": asdict(result)})
        elif arguments.command == "recovery-preview":
            output = preview_cash_coverage_store_migration_recovery_v1(
                Path(value["source_store_path"]), Path(value["target_data_space_path"]),
                Path(value["canonical_path"]), context, value["trusted_preview"], value["original_confirmation"],
            )
            _emit({"status": "recovery_previewed", **output})
        elif arguments.command == "recovery-confirmation":
            confirmation = build_cash_coverage_store_migration_recovery_confirmation_v1(
                value["trusted_recovery_preview"], context, value["confirmation_ref"],
                value["issued_at_utc"], value["expires_at_utc"],
            )
            _emit({"status": "recovery_confirmation_built", "confirmation": confirmation})
        else:
            result = apply_cash_coverage_store_migration_recovery_v1(
                Path(value["source_store_path"]), Path(value["target_data_space_path"]),
                Path(value["canonical_path"]), context, value["trusted_preview"],
                value["original_confirmation"], value["trusted_recovery_preview"],
                value["recovery_confirmation"], value["recovered_at_utc"],
            )
            _emit({"status": "recovery_applied", "result": asdict(result)})
        return 0
    except _InputError:
        _emit({"status": "blocked", "code": "desktop_cash_coverage_boundary_failed"})
        return 2
    except DesktopCashCoverageV1Error as error:
        _emit({"status": "blocked", "code": error.code})
        return 2
    except (KeyError, TypeError):
        _emit({"status": "blocked", "code": "desktop_cash_coverage_boundary_failed"})
        return 2
    except Exception:
        _emit({"status": "failed", "code": "desktop_cash_coverage_boundary_failed"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
