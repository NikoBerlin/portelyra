#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations.reference.statement_exchange_reward_adapter_v1 import (
    StatementExchangeRewardAdapterV1Error,
    project_exchange_reward_statement_v1,
    project_exchange_reward_statements_v1,
)
from migrations.reference.statement_import_mapping_v1 import (
    StatementImportMappingV1Error,
    derive_reward_manual_valuation_v1,
    project_statement_import_mapping_v1,
)
from migrations.reference.statement_import_mapping_profile_v1 import (
    StatementImportMappingProfileV1Error,
    StatementMappingProfileContextV1,
    list_statement_mapping_profiles_v1,
    preview_statement_mapping_profile_v1,
    read_statement_mapping_profile_v1,
    save_statement_mapping_profile_v1,
)


def _context(payload: dict) -> StatementMappingProfileContextV1:
    value = payload["context"]
    if not isinstance(value, dict) or set(value) != {"tenant_id", "user_id", "data_space_id"}:
        raise StatementImportMappingProfileV1Error("statement_mapping_profile_context_invalid")
    return StatementMappingProfileContextV1(value["tenant_id"], value["user_id"], value["data_space_id"])


def main() -> int:
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        operations = {"exchange_preview", "exchange_preview_many", "project", "derive_reward_manual_valuation", "profile_save", "profile_list", "profile_read", "profile_preview"}
        if not isinstance(payload, dict) or payload.get("operation") not in operations:
            raise StatementImportMappingV1Error("statement_import_mapping_input_invalid")
        if payload["operation"] == "exchange_preview":
            if set(payload) != {"operation", "source_base64", "adapter_id", "confirmed_timezone", "period_start_date", "period_end_date"} or not isinstance(payload["source_base64"], str):
                raise StatementImportMappingV1Error("statement_import_mapping_input_invalid")
            try:
                compact_base64 = "".join(payload["source_base64"].split())
                source_bytes = base64.b64decode(compact_base64, validate=True)
            except ValueError as error:
                raise StatementImportMappingV1Error("statement_import_mapping_input_invalid") from error
            result = project_exchange_reward_statement_v1(
                source_bytes, adapter_id=payload["adapter_id"],
                confirmed_timezone=payload["confirmed_timezone"],
                period_start_date=payload["period_start_date"],
                period_end_date=payload["period_end_date"],
            )
        elif payload["operation"] == "exchange_preview_many":
            # Alle Exporte einer Boerse als ein Lauf (rc.343), etwa Bisons Jahresdateien aus der Ablage.
            if set(payload) != {"operation", "sources_base64", "adapter_id", "confirmed_timezone", "period_start_date", "period_end_date"} or not isinstance(payload["sources_base64"], list) or any(not isinstance(item, str) for item in payload["sources_base64"]):
                raise StatementImportMappingV1Error("statement_import_mapping_input_invalid")
            try:
                sources = [base64.b64decode("".join(item.split()), validate=True) for item in payload["sources_base64"]]
            except ValueError as error:
                raise StatementImportMappingV1Error("statement_import_mapping_input_invalid") from error
            result = project_exchange_reward_statements_v1(
                sources, adapter_id=payload["adapter_id"],
                confirmed_timezone=payload["confirmed_timezone"],
                period_start_date=payload["period_start_date"],
                period_end_date=payload["period_end_date"],
            )
        elif payload["operation"] == "project":
            if set(payload) != {"operation", "rows", "mappings", "adapter_id", "adapter_version", "base_currency", "confirmed_timezone"}:
                raise StatementImportMappingV1Error("statement_import_mapping_input_invalid")
            result = project_statement_import_mapping_v1(
                payload["rows"], payload["mappings"], adapter_id=payload["adapter_id"],
                adapter_version=payload["adapter_version"], base_currency=payload["base_currency"],
                confirmed_timezone=payload["confirmed_timezone"],
            )
        elif payload["operation"] == "derive_reward_manual_valuation":
            if set(payload) != {"operation", "gross_quantity_decimal", "asset_fee_quantity_decimal", "mode", "value_decimal", "price_currency", "expected_currency"}:
                raise StatementImportMappingV1Error("statement_import_mapping_input_invalid")
            result = derive_reward_manual_valuation_v1(
                payload["gross_quantity_decimal"], payload["asset_fee_quantity_decimal"],
                payload["mode"], payload["value_decimal"], payload["price_currency"],
                payload["expected_currency"],
            )
        elif payload["operation"] == "profile_save":
            if set(payload) != {"operation", "data_space", "context", "adapter_id", "adapter_version", "profile_label", "mapping_rows", "created_at_utc", "profile_ref", "expected_revision"}:
                raise StatementImportMappingProfileV1Error("statement_mapping_profile_input_invalid")
            result = save_statement_mapping_profile_v1(Path(payload["data_space"]), _context(payload), adapter_id=payload["adapter_id"], adapter_version=payload["adapter_version"], profile_label=payload["profile_label"], mapping_rows=payload["mapping_rows"], created_at_utc=payload["created_at_utc"], profile_ref=payload["profile_ref"], expected_revision=payload["expected_revision"])
        elif payload["operation"] == "profile_list":
            if set(payload) != {"operation", "data_space", "context", "adapter_id", "adapter_version"}:
                raise StatementImportMappingProfileV1Error("statement_mapping_profile_input_invalid")
            result = list_statement_mapping_profiles_v1(Path(payload["data_space"]), _context(payload), adapter_id=payload["adapter_id"], adapter_version=payload["adapter_version"])
        elif payload["operation"] == "profile_read":
            if set(payload) != {"operation", "data_space", "context", "profile_ref"}:
                raise StatementImportMappingProfileV1Error("statement_mapping_profile_input_invalid")
            result = read_statement_mapping_profile_v1(Path(payload["data_space"]), _context(payload), payload["profile_ref"])
        else:
            if set(payload) != {"operation", "profile", "current_rows", "asset_ids", "account_ids"}:
                raise StatementImportMappingProfileV1Error("statement_mapping_profile_input_invalid")
            result = preview_statement_mapping_profile_v1(payload["profile"], payload["current_rows"], {"asset_ids": set(payload["asset_ids"]), "account_ids": set(payload["account_ids"])})
        output = {"status": "complete", "result": result}
        code = 0
    except (StatementExchangeRewardAdapterV1Error, StatementImportMappingV1Error, StatementImportMappingProfileV1Error, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        output = {"status": "blocked", "code": getattr(error, "code", "statement_import_mapping_input_invalid")}
        code = 2
    sys.stdout.write(json.dumps(output, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
