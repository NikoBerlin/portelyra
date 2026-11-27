"""Provider-neutral Statement candidate mapping and deferred valuation projection.

The projector is pure: it opens no files, resolves no canonical IDs and writes no
Draft.  A trusted Data-UI adapter may resolve the opaque target option keys and
hand each projected row to the existing ActivityDraft writer.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
import re
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from migrations.reference.desktop_product_asset_activity_v1 import NATIVE_EVENT_KEYS

_DECIMAL = re.compile(r"^(0|[1-9][0-9]*)(?:\.([0-9]+))?$")
_ADAPTER = re.compile(r"^[a-z][a-z0-9_]{7,80}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_TEXT = re.compile(r"^[^\x00\r\n]{1,200}$")
SUPPORTED_VALUATION_EVENTS = frozenset({"reward", "stock_dividend", "deposit"})


class StatementImportMappingV1Error(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise StatementImportMappingV1Error(code)


def _text(value: Any) -> str:
    if not isinstance(value, str) or value != value.strip() or _TEXT.fullmatch(value) is None:
        _abort("statement_import_mapping_input_invalid")
    return value


def _decimal(value: Any) -> tuple[str, Fraction]:
    if not isinstance(value, str) or len(value) > 80 or _DECIMAL.fullmatch(value) is None:
        _abort("statement_import_mapping_decimal_invalid")
    whole, _, fraction = value.partition(".")
    return value, Fraction(int(whole + fraction), 10 ** len(fraction))


def _valuation(value: Any, adapter_id: str, adapter_version: str, *, valuation_required: bool) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _abort("statement_import_mapping_valuation_invalid")
    keys = {"source_value_mode", "price_currency", "source_unit_price_decimal", "source_fiat_total_decimal"}
    if set(value) != keys:
        _abort("statement_import_mapping_valuation_invalid")
    mode = value.get("source_value_mode")
    currency = value.get("price_currency")
    unit = value.get("source_unit_price_decimal")
    total = value.get("source_fiat_total_decimal")
    if mode not in {"none", "unit_price", "fiat_total"}:
        _abort("statement_import_mapping_valuation_invalid")
    if currency is not None and (not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None):
        _abort("statement_import_mapping_valuation_invalid")
    if mode == "none":
        if unit is not None or total is not None or (valuation_required and currency is None):
            _abort("statement_import_mapping_valuation_invalid")
        origin = "source_missing" if currency is not None else "not_applicable"
    elif mode == "unit_price":
        if currency is None:
            _abort("statement_import_mapping_valuation_invalid")
        unit, _ = _decimal(unit)
        if total is not None:
            _abort("statement_import_mapping_valuation_invalid")
        origin = "source_provided"
    else:
        if currency is None:
            _abort("statement_import_mapping_valuation_invalid")
        total, _ = _decimal(total)
        if unit is not None:
            _abort("statement_import_mapping_valuation_invalid")
        origin = "source_provided"
    return {
        "adapter_id": adapter_id,
        "adapter_version": adapter_version,
        "valuation_origin": origin,
        "source_value_mode": mode,
        "price_currency": currency,
        "source_unit_price_decimal": unit,
        "source_fiat_total_decimal": total,
    }


def _mapping_key(source_asset: str, source_account: str, event_type: str) -> tuple[str, str, str]:
    return source_asset, source_account, event_type


def _event(value: Any, event_type: str) -> dict[str, Any]:
    source_metadata_keys = {"fee_role", "fee_currency"}
    if not isinstance(value, Mapping) or set(value) - NATIVE_EVENT_KEYS - source_metadata_keys:
        _abort("statement_import_mapping_input_invalid")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"event_ref", "account_ref", "related_account_ref", "asset_ref", "source_asset_ref"}:
            _abort("statement_import_mapping_authority_invalid")
        if item is not None:
            _text(item)
        result[key] = item
    if "event_type" in result and result["event_type"] != event_type:
        _abort("statement_import_mapping_input_invalid")
    result["event_type"] = event_type
    return result


def _bind_confirmed_time(event: dict[str, Any], confirmed_timezone: str) -> None:
    if event.get("event_time_evidence") != "exact":
        return
    try:
        naive = datetime.fromisoformat(str(event["local_date"]) + "T" + str(event["local_time"]))
        zone = ZoneInfo(confirmed_timezone)
        candidates = set()
        for fold in (0, 1):
            aware = naive.replace(tzinfo=zone, fold=fold)
            utc = aware.astimezone(timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == naive:
                candidates.add(utc)
        if len(candidates) != 1:
            _abort("statement_import_mapping_timezone_invalid")
        event["time_zone"] = confirmed_timezone
        event["effective_at_utc"] = next(iter(candidates)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except StatementImportMappingV1Error:
        raise
    except Exception:
        _abort("statement_import_mapping_timezone_invalid")


def _apply_reward_valuation(event: dict[str, Any], evidence: Mapping[str, Any], base_currency: str) -> tuple[str, str]:
    event["amount_input_mode"] = "quantity_unit_price"
    mode = evidence["source_value_mode"]
    if mode == "none":
        event["basis_evidence_mode"] = "basis_missing"
        event.pop("unit_price_decimal", None)
        event.pop("provided_basis_decimal", None)
        return "valuation_pending", "source_valuation_missing"
    if evidence["price_currency"] != base_currency:
        event["basis_evidence_mode"] = "basis_missing"
        event.pop("unit_price_decimal", None)
        event.pop("provided_basis_decimal", None)
        return "valuation_pending", "source_currency_conversion_required"
    if mode == "unit_price":
        event["unit_price_decimal"] = evidence["source_unit_price_decimal"]
        event["basis_evidence_mode"] = "valuation_confirmed_as_basis"
        event["provided_basis_decimal"] = None
        return "source_provided", "source_unit_price_exact"
    _, gross = _decimal(event.get("quantity_decimal"))
    fee_text = event.get("asset_fee_quantity_decimal")
    fee = Fraction(0) if fee_text is None else _decimal(fee_text)[1]
    if fee >= gross:
        _abort("statement_import_mapping_quantity_invalid")
    total_text, _ = _decimal(evidence["source_fiat_total_decimal"])
    event["amount_input_mode"] = "gross_total"
    event["gross_amount_decimal"] = total_text
    event["unit_price_decimal"] = None
    event["basis_evidence_mode"] = "valuation_confirmed_as_basis"
    event["provided_basis_decimal"] = None
    return "source_provided", "source_fiat_total_exactly_projected"


def derive_reward_manual_valuation_v1(
    gross_quantity_decimal: str,
    asset_fee_quantity_decimal: str | None,
    mode: str,
    value_decimal: str,
    price_currency: str,
    expected_currency: str,
) -> dict[str, Any]:
    """Build one exact owner-manual Reward valuation patch without writes."""
    _, gross = _decimal(gross_quantity_decimal)
    fee = Fraction(0) if asset_fee_quantity_decimal is None else _decimal(asset_fee_quantity_decimal)[1]
    _decimal(value_decimal)
    # Der Kern nimmt nur die kanonische Form: "10.00" wurde dort als asset_activity_amount_invalid abgelehnt (#520).
    if "." in value_decimal:
        value_decimal = value_decimal.rstrip("0").rstrip(".")
    if fee >= gross:
        _abort("statement_import_mapping_quantity_invalid")
    if mode not in {"manual_unit_price", "manual_fiat_total"} or re.fullmatch(r"[A-Z]{3}", str(price_currency)) is None or price_currency != expected_currency:
        _abort("statement_import_mapping_valuation_invalid")
    event_patch = {
        "basis_evidence_mode": "valuation_confirmed_as_basis",
        "provided_basis_decimal": None,
    }
    if mode == "manual_unit_price":
        event_patch.update(
            amount_input_mode="quantity_unit_price", unit_price_decimal=value_decimal,
            gross_amount_decimal=None,
        )
    else:
        event_patch.update(
            amount_input_mode="gross_total", unit_price_decimal=None,
            gross_amount_decimal=value_decimal,
        )
    return {
        "status": "owner_manual_valuation_exact",
        "mode": mode,
        "price_currency": price_currency,
        "event_patch": event_patch,
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "tax_write": False,
    }


def project_statement_import_mapping_v1(
    rows: list[Mapping[str, Any]],
    mappings: list[Mapping[str, Any]],
    *,
    adapter_id: str,
    adapter_version: str,
    base_currency: str,
    confirmed_timezone: str,
) -> dict[str, Any]:
    """Project all rows to Draft handoffs or explicit deferred dispositions."""
    if (
        not isinstance(rows, list) or not rows
        or not isinstance(mappings, list)
        or not isinstance(adapter_id, str) or _ADAPTER.fullmatch(adapter_id) is None
        or not isinstance(adapter_version, str) or _VERSION.fullmatch(adapter_version) is None
        or not isinstance(base_currency, str) or re.fullmatch(r"[A-Z]{3}", base_currency) is None
    ):
        _abort("statement_import_mapping_input_invalid")
    confirmed_timezone = _text(confirmed_timezone)
    try:
        ZoneInfo(confirmed_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        _abort("statement_import_mapping_timezone_invalid")
    mapping_index: dict[tuple[str, str, str], Mapping[str, Any]] = {}
    for mapping in mappings:
        keys = {"source_asset_key", "source_account_key", "event_type", "disposition", "target_asset_option_key", "target_account_option_key"}
        if not isinstance(mapping, Mapping) or set(mapping) != keys or mapping.get("disposition") not in {"map", "defer"}:
            _abort("statement_import_mapping_input_invalid")
        source_asset = _text(mapping.get("source_asset_key"))
        source_account = _text(mapping.get("source_account_key"))
        event_type = _text(mapping.get("event_type"))
        key = _mapping_key(source_asset, source_account, event_type)
        if key in mapping_index:
            _abort("statement_import_mapping_duplicate_invalid")
        if mapping["disposition"] == "map":
            _text(mapping.get("target_asset_option_key")); _text(mapping.get("target_account_option_key"))
        elif mapping.get("target_asset_option_key") is not None or mapping.get("target_account_option_key") is not None:
            _abort("statement_import_mapping_input_invalid")
        mapping_index[key] = mapping
    projected = []
    seen_ordinals: set[int] = set()
    seen_keys: set[str] = set()
    tuple_counts: dict[tuple[str, str, str], int] = {}
    for row in rows:
        required = {"source_row_ordinal", "source_row_key", "source_asset_key", "source_account_key", "event_type", "event_fields", "valuation"}
        if not isinstance(row, Mapping) or set(row) != required:
            _abort("statement_import_mapping_input_invalid")
        ordinal = row.get("source_row_ordinal")
        row_key = _text(row.get("source_row_key"))
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1 or ordinal in seen_ordinals:
            _abort("statement_import_mapping_duplicate_invalid")
        seen_ordinals.add(ordinal)
        source_asset = _text(row.get("source_asset_key")); source_account = _text(row.get("source_account_key")); event_type = _text(row.get("event_type"))
        tuple_key = _mapping_key(source_asset, source_account, event_type)
        tuple_counts[tuple_key] = tuple_counts.get(tuple_key, 0) + 1
        if row_key in seen_keys:
            projected.append({"source_row_ordinal": ordinal, "source_row_key": row_key, "disposition": "duplicate_deferred", "reason_code": "duplicate_source_row_key", "draft_handoff": None})
            continue
        seen_keys.add(row_key)
        mapping = mapping_index.get(tuple_key)
        if mapping is None:
            projected.append({"source_row_ordinal": ordinal, "source_row_key": row_key, "disposition": "mapping_required", "reason_code": "source_tuple_unmapped", "draft_handoff": None})
            continue
        if mapping["disposition"] == "defer":
            projected.append({"source_row_ordinal": ordinal, "source_row_key": row_key, "disposition": "deferred", "reason_code": "owner_deferred_source_tuple", "draft_handoff": None})
            continue
        event = _event(row.get("event_fields"), event_type)
        if event.get("time_zone") is not None and event.get("time_zone") != confirmed_timezone:
            _abort("statement_import_mapping_timezone_invalid")
        _bind_confirmed_time(event, confirmed_timezone)
        evidence = _valuation(row.get("valuation"), adapter_id, adapter_version, valuation_required=event_type in SUPPORTED_VALUATION_EVENTS)
        if event_type in SUPPORTED_VALUATION_EVENTS:
            status, reason = _apply_reward_valuation(event, evidence, base_currency) if event_type == "reward" else ("valuation_pending", "event_valuation_adapter_required")
        else:
            status, reason = ("not_applicable", "event_valuation_not_applicable")
            if evidence["valuation_origin"] != "not_applicable" and evidence["source_value_mode"] != "none":
                status, reason = "source_evidence_retained", "event_specific_projection_required"
        source_monetary_fee = event.pop("monetary_fee_decimal", None) if event_type == "reward" else None
        source_fee_currency = event.pop("fee_currency", None) or evidence.get("price_currency")
        event.pop("fee_role", None)
        auxiliary = {
            "unclassified_fee_decimal": None,
            "unclassified_fee_resolution": "not_present",
            "valuation_evidence": evidence,
        }
        if source_monetary_fee is not None:
            auxiliary["source_fee_evidence"] = {"fee_decimal": source_monetary_fee, "fee_currency": source_fee_currency, "treatment": "source_retained_not_reapplied"}
        projected.append({
            "source_row_ordinal": ordinal,
            "source_row_key": row_key,
            "disposition": "draft_needs_valuation" if status == "valuation_pending" else "draft_ready",
            "reason_code": reason,
            "draft_handoff": {
                "target_asset_option_key": mapping["target_asset_option_key"],
                "target_account_option_key": mapping["target_account_option_key"],
                "event_fields": event,
                "source_auxiliary": auxiliary,
                "valuation_status": status,
            },
        })
    projected.sort(key=lambda item: item["source_row_ordinal"])
    count_keys = ("draft_ready", "draft_needs_valuation", "mapping_required", "deferred", "duplicate_deferred")
    counts = {key: sum(item["disposition"] == key for item in projected) for key in count_keys}
    inventory = []
    for key in sorted(tuple_counts):
        mapping = mapping_index.get(key)
        inventory.append({
            "source_asset_key": key[0], "source_account_key": key[1], "event_type": key[2],
            "source_row_count": tuple_counts[key],
            "mapping_status": "mapping_required" if mapping is None else mapping["disposition"],
        })
    return {
        "statement_import_mapping_version": 1,
        "status": "mapping_projected_no_write",
        "row_count": len(projected),
        "rows": projected,
        "tuple_count": len(inventory),
        "tuple_inventory": inventory,
        "disposition_counts": counts,
        "duplicate_source_row_count": counts["duplicate_deferred"],
        "silent_drop_count": 0,
        "activity_draft_write": False,
        "canonical_write": False,
        "cash_write": False,
        "provider_access": False,
        "network_access": False,
        "tax_write": False,
    }


__all__ = ["StatementImportMappingV1Error", "derive_reward_manual_valuation_v1", "project_statement_import_mapping_v1"]
