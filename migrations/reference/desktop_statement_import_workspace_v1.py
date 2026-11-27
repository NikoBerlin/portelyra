"""Synthetic Kraken-ledger mapping and reconciliation workspace v1.

This module has no private-source, provider, confirmation, or Product-write entrypoint.
The only public operation reads two repository-tracked invented fixtures.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "contracts" / "desktop-statement-import-workspace" / "v1"
MAX_BYTES = 32_000_000
SCENARIOS = ("basis_missing", "manual_fiat_total", "manual_unit_price")
DISPOSITIONS = (
    "new_candidate",
    "exact_existing_noop",
    "existing_link_required",
    "correction_proposed",
    "ambiguous_match_blocked",
    "deferred",
    "cash_domain_deferred",
    "diagnostic",
)
DECIMAL_TEXT = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
SOURCE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}")
MACHINE_TOKEN = re.compile(r"[a-z][a-z0-9_]{2,100}")
UTC_SOURCE_TIME = re.compile(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})")
_SHA256 = re.compile(r"[0-9a-f]{64}")

_FIXTURE_REGISTRY_FIELDS = ("fixture_id", "path", "purpose", "sha256")
_PROFILE_REGISTRY_FIELDS = (
    "source_profile_id",
    "source_profile_revision",
    "profile_semantics_sha256",
    "status",
)
_EXPECTED_FIXTURES = {
    "invented_kraken_ledger_csv": "fixtures/product/statement-import-workspace-v1/invented_kraken_ledger.csv",
    "synthetic_workspace_input": "fixtures/product/statement-import-workspace-v1/synthetic_workspace_input.json",
}
_FORBIDDEN_PUBLIC_KEYS = frozenset(
    {
        "tenant_id",
        "user_id",
        "data_space_id",
        "context",
        "context_fingerprint",
        "source_fingerprint",
        "manifest_fingerprint",
        "candidate_bundle_fingerprint",
        "result_fingerprint",
        "source_path",
        "fixture_path",
        "entrypoint",
        "output_directory",
        "attempt_id",
        "confirmation_id",
        "challenge",
        "existing_event_key",
        "source_identity_binding",
    }
)
_CANDIDATE_FIELDS = frozenset(
    {
        "account_key",
        "amount_input_mode",
        "asset_fee_quantity_decimal",
        "basis_evidence_mode",
        "event_time_evidence",
        "event_type",
        "fee_role",
        "gross_income_decimal",
        "local_date",
        "local_time",
        "price_currency",
        "quantity_decimal",
        "source_asset_key",
        "source_reference",
        "time_zone",
        "unit_price_decimal",
    }
)


class DesktopStatementImportWorkspaceError(RuntimeError):
    """A stable browser-safe workspace failure."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def canonical_desktop_statement_import_workspace_json_bytes_v1(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fail(code: str) -> None:
    raise DesktopStatementImportWorkspaceError(code)


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _safe_repository_bytes(relative_path: str, failure_code: str) -> bytes:
    try:
        pure = PurePosixPath(relative_path)
        if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
            _fail(failure_code)
        path = ROOT.joinpath(*pure.parts)
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(path, flags)
    except DesktopStatementImportWorkspaceError:
        raise
    except (OSError, TypeError, ValueError):
        _fail(failure_code)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= MAX_BYTES:
            _fail(failure_code)
        chunks: list[bytes] = []
        remaining = info.st_size
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                _fail(failure_code)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(failure_code)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _strict_json_bytes(raw: bytes, failure_code: str) -> dict[str, Any]:
    if not raw or len(raw) > MAX_BYTES or b"\x00" in raw:
        _fail(failure_code)
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non_finite_json")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        _fail(failure_code)
    if not isinstance(value, dict):
        _fail(failure_code)
    return value


def _registry_rows(relative_path: str, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    raw = _safe_repository_bytes(relative_path, "desktop_statement_import_workspace_fixture_invalid")
    try:
        text = raw.decode("utf-8", errors="strict")
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != expected_fields:
            _fail("desktop_statement_import_workspace_fixture_invalid")
        rows = list(reader)
    except DesktopStatementImportWorkspaceError:
        raise
    except Exception:
        _fail("desktop_statement_import_workspace_fixture_invalid")
    if not rows or any(set(row) != set(expected_fields) or any(value is None for value in row.values()) for row in rows):
        _fail("desktop_statement_import_workspace_fixture_invalid")
    return rows


def _load_tracked_synthetic_input() -> tuple[bytes, dict[str, Any], str]:
    rows = _registry_rows(
        "contracts/desktop-statement-import-workspace/v1/synthetic-fixtures.csv",
        _FIXTURE_REGISTRY_FIELDS,
    )
    if [row["fixture_id"] for row in rows] != sorted(_EXPECTED_FIXTURES):
        _fail("desktop_statement_import_workspace_fixture_invalid")
    loaded: dict[str, bytes] = {}
    for row in rows:
        fixture_id = row["fixture_id"]
        if set(row) != set(_FIXTURE_REGISTRY_FIELDS) or _EXPECTED_FIXTURES.get(fixture_id) != row["path"]:
            _fail("desktop_statement_import_workspace_fixture_invalid")
        if not row["purpose"] or _SHA256.fullmatch(row["sha256"]) is None:
            _fail("desktop_statement_import_workspace_fixture_invalid")
        raw = _safe_repository_bytes(row["path"], "desktop_statement_import_workspace_fixture_invalid")
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            _fail("desktop_statement_import_workspace_fixture_invalid")
        loaded[fixture_id] = raw
    config = _strict_json_bytes(
        loaded["synthetic_workspace_input"],
        "desktop_statement_import_workspace_fixture_invalid",
    )
    profile_rows = _registry_rows(
        "contracts/desktop-statement-import-workspace/v1/profile-revisions.csv",
        _PROFILE_REGISTRY_FIELDS,
    )
    if len(profile_rows) != 1:
        _fail("desktop_statement_import_workspace_profile_invalid")
    profile_row = profile_rows[0]
    profile = config.get("source_profile")
    if not isinstance(profile, dict):
        _fail("desktop_statement_import_workspace_profile_invalid")
    profile_sha = hashlib.sha256(canonical_desktop_statement_import_workspace_json_bytes_v1(profile)).hexdigest()
    if (
        profile_row["source_profile_id"] != profile.get("source_profile_id")
        or profile_row["source_profile_revision"] != profile.get("source_profile_revision")
        or profile_row["profile_semantics_sha256"] != profile_sha
        or profile_row["status"] != "synthetic_pending_private_owner_uat"
    ):
        _fail("desktop_statement_import_workspace_profile_invalid")
    return loaded["invented_kraken_ledger_csv"], config, profile_sha


def _exact_names(value: Any, names: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != names:
        _fail(code)
    return value


def _scalar_text(value: Any, code: str, maximum: int = 160) -> str:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > maximum or "\x00" in value:
        _fail(code)
    return value


def _decimal_parts(value: Any) -> tuple[int, int, str]:
    if not isinstance(value, str) or DECIMAL_TEXT.fullmatch(value) is None:
        _fail("desktop_statement_import_workspace_decimal_invalid")
    negative = value.startswith("-")
    unsigned = value[1:] if negative else value
    whole, separator, fraction = unsigned.partition(".")
    coefficient = int(whole + fraction)
    if negative:
        coefficient = -coefficient
    return coefficient, len(fraction) if separator else 0, value


def _decimal_normalized(value: str) -> str:
    coefficient, scale, _ = _decimal_parts(value)
    if coefficient == 0:
        return "0"
    negative = coefficient < 0
    digits = str(abs(coefficient))
    if scale:
        digits = digits.zfill(scale + 1)
        rendered = digits[:-scale] + "." + digits[-scale:]
        rendered = rendered.rstrip("0").rstrip(".")
    else:
        rendered = digits
    return ("-" if negative else "") + rendered


def _decimal_multiply_exact(left: str, right: str) -> str:
    left_coefficient, left_scale, _ = _decimal_parts(left)
    right_coefficient, right_scale, _ = _decimal_parts(right)
    coefficient = left_coefficient * right_coefficient
    scale = left_scale + right_scale
    negative = coefficient < 0
    digits = str(abs(coefficient)).zfill(scale + 1)
    rendered = digits if scale == 0 else digits[:-scale] + "." + digits[-scale:]
    return ("-" if negative and coefficient else "") + rendered


def _source_time(value: Any, configured_zone: str) -> tuple[str, str, str]:
    text = _scalar_text(value, "desktop_statement_import_workspace_row_invalid", 32)
    match = UTC_SOURCE_TIME.fullmatch(text)
    if match is None or configured_zone != "UTC":
        _fail("desktop_statement_import_workspace_row_invalid")
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    try:
        from datetime import datetime, timezone

        instant = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError:
        _fail("desktop_statement_import_workspace_row_invalid")
    return instant.strftime("%Y-%m-%dT%H:%M:%SZ"), instant.strftime("%Y-%m-%d"), instant.strftime("%H:%M:%S")


def _validate_profile(profile: Any, expected_profile_sha256: str | None) -> dict[str, Any]:
    code = "desktop_statement_import_workspace_profile_invalid"
    profile = _exact_names(
        profile,
        {
            "column_mappings",
            "export_profile",
            "format_version",
            "header_columns",
            "identity_policy",
            "institution",
            "locale",
            "medium",
            "route_rules",
            "source_profile_id",
            "source_profile_revision",
            "source_profile_status",
            "time_zone",
        },
        code,
    )
    expected_scalars = {
        "export_profile": "ledger_csv",
        "format_version": "synthetic_contract_v1",
        "institution": "kraken",
        "locale": "en",
        "medium": "csv",
        "source_profile_id": "kraken_ledger_csv_source_v1",
        "source_profile_revision": "r1",
        "source_profile_status": "synthetic_pending_private_owner_uat",
        "time_zone": "UTC",
    }
    if any(profile.get(field) != expected for field, expected in expected_scalars.items()):
        _fail(code)
    if expected_profile_sha256 is not None:
        actual = hashlib.sha256(canonical_desktop_statement_import_workspace_json_bytes_v1(profile)).hexdigest()
        if actual != expected_profile_sha256:
            _fail(code)
    header = profile.get("header_columns")
    if not isinstance(header, list) or not header or len(header) != len(set(header)):
        _fail(code)
    if any(not isinstance(item, str) or MACHINE_TOKEN.fullmatch(item) is None for item in header):
        _fail(code)
    mappings = profile.get("column_mappings")
    if not isinstance(mappings, list) or len(mappings) != len(header):
        _fail(code)
    roles: list[str] = []
    columns: list[str] = []
    for mapping in mappings:
        mapping = _exact_names(mapping, {"disposition", "required", "role", "source_column"}, code)
        if mapping.get("disposition") not in {"mapped", "retained_not_imported"} or mapping.get("required") is not True:
            _fail(code)
        role = mapping.get("role")
        column = mapping.get("source_column")
        if not isinstance(role, str) or MACHINE_TOKEN.fullmatch(role) is None or column not in header:
            _fail(code)
        roles.append(role)
        columns.append(column)
    required_roles = {
        "source_row_id",
        "source_group_id",
        "event_time_utc_text",
        "source_type",
        "source_subtype",
        "asset_class",
        "source_asset_key",
        "signed_quantity_decimal",
        "asset_fee_quantity_decimal",
        "balance_reconciliation_evidence",
    }
    if columns != header or len(set(columns)) != len(columns) or set(roles) != required_roles or len(set(roles)) != len(roles):
        _fail(code)
    identity = _exact_names(
        profile.get("identity_policy"),
        {
            "date_only_matching_allowed",
            "duplicate_txid_disposition",
            "missing_txid_disposition",
            "source_group_identity_components",
            "source_ordinal_role",
            "source_row_identity_components",
        },
        code,
    )
    if (
        identity.get("date_only_matching_allowed") is not False
        or identity.get("duplicate_txid_disposition") != "diagnostic"
        or identity.get("missing_txid_disposition") != "diagnostic"
        or identity.get("source_ordinal_role") != "closed_row_ledger_only"
        or identity.get("source_row_identity_components")
        != ["source_profile_id", "source_profile_revision", "txid"]
        or identity.get("source_group_identity_components")
        != ["source_profile_id", "source_profile_revision", "refid", "sorted_member_txids"]
    ):
        _fail(code)
    rules = profile.get("route_rules")
    if not isinstance(rules, list) or len(rules) != 3:
        _fail(code)
    seen_pairs: set[tuple[str, str, str]] = set()
    for rule in rules:
        rule = _exact_names(
            rule,
            {"adapter_id", "domain", "route", "route_status", "source_asset_class", "source_subtype", "source_type"},
            code,
        )
        pair = (rule.get("source_type"), rule.get("source_subtype"), rule.get("source_asset_class"))
        if not all(isinstance(item, str) and MACHINE_TOKEN.fullmatch(item) for item in pair) or pair in seen_pairs:
            _fail(code)
        if rule.get("domain") not in {"asset_activity", "cash"} or rule.get("route") not in {"reward", "trade", "cash"}:
            _fail(code)
        if rule.get("adapter_id") is not None and (
            not isinstance(rule.get("adapter_id"), str) or MACHINE_TOKEN.fullmatch(rule["adapter_id"]) is None
        ):
            _fail(code)
        _scalar_text(rule.get("route_status"), code)
        seen_pairs.add(pair)
    return profile


def _parse_source(source_bytes: bytes, profile: dict[str, Any]) -> list[dict[str, Any]]:
    if not source_bytes or len(source_bytes) > MAX_BYTES or b"\x00" in source_bytes:
        _fail("desktop_statement_import_workspace_fixture_invalid")
    try:
        text = source_bytes.decode("utf-8", errors="strict")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        records = list(reader)
    except (UnicodeDecodeError, csv.Error):
        _fail("desktop_statement_import_workspace_fixture_invalid")
    if len(records) < 2 or records[0] != profile["header_columns"]:
        _fail("desktop_statement_import_workspace_header_drift")
    header = records[0]
    roles = {mapping["role"]: mapping["source_column"] for mapping in profile["column_mappings"]}
    raw_rows: list[dict[str, str]] = []
    for record in records[1:]:
        if len(record) != len(header) or all(value == "" for value in record):
            _fail("desktop_statement_import_workspace_row_invalid")
        raw_rows.append(dict(zip(header, record)))
    txid_column = roles["source_row_id"]
    txid_counts: dict[str, int] = {}
    for row in raw_rows:
        txid = row[txid_column]
        if txid:
            txid_counts[txid] = txid_counts.get(txid, 0) + 1
    rows: list[dict[str, Any]] = []
    for ordinal, raw in enumerate(raw_rows, 1):
        mapped = {role: raw[column] for role, column in roles.items()}
        txid = mapped["source_row_id"]
        identity_error = None
        if not txid:
            identity_error = "source_txid_missing"
        elif SOURCE_TOKEN.fullmatch(txid) is None:
            identity_error = "source_txid_invalid"
        elif txid_counts.get(txid) != 1:
            identity_error = "source_txid_duplicate"
        refid = mapped["source_group_id"]
        if identity_error is None and SOURCE_TOKEN.fullmatch(refid) is None:
            identity_error = "source_refid_invalid"
        for role in ("source_type", "source_subtype", "asset_class"):
            if MACHINE_TOKEN.fullmatch(mapped[role]) is None:
                identity_error = identity_error or f"{role}_invalid"
        asset_key = mapped["source_asset_key"]
        if SOURCE_TOKEN.fullmatch(asset_key) is None:
            identity_error = identity_error or "source_asset_key_invalid"
        for role in ("signed_quantity_decimal", "asset_fee_quantity_decimal", "balance_reconciliation_evidence"):
            _decimal_parts(mapped[role])
        event_time_utc, local_date, local_time = _source_time(mapped["event_time_utc_text"], profile["time_zone"])
        rows.append(
            {
                "event_time_utc": event_time_utc,
                "identity_error": identity_error,
                "local_date": local_date,
                "local_time": local_time,
                "mapped": mapped,
                "ordinal": ordinal,
            }
        )
    return rows


def _validate_catalog(value: Any) -> dict[str, Any]:
    code = "desktop_statement_import_workspace_fixture_invalid"
    value = _exact_names(value, {"account_mapping", "asset_mappings", "portfolio_selection"}, code)
    portfolio = _exact_names(value.get("portfolio_selection"), {"mapping_status", "target_label", "target_option_key"}, code)
    if portfolio.get("mapping_status") != "selected_existing":
        _fail(code)
    _scalar_text(portfolio.get("target_label"), code)
    _scalar_text(portfolio.get("target_option_key"), code)
    account = _exact_names(
        value.get("account_mapping"),
        {"mapping_status", "source_account_scope", "target_label", "target_option_key"},
        code,
    )
    if account.get("mapping_status") != "matched_existing":
        _fail(code)
    for field in ("source_account_scope", "target_label", "target_option_key"):
        _scalar_text(account.get(field), code)
    mappings = value.get("asset_mappings")
    if not isinstance(mappings, list) or not mappings:
        _fail(code)
    seen: set[str] = set()
    allowed_statuses = {
        "matched_existing",
        "separate_catalog_handoff_required",
        "route_deferred",
        "cash_domain_deferred",
        "diagnostic_only",
    }
    for mapping in mappings:
        mapping = _exact_names(mapping, {"mapping_status", "source_asset_key", "target_label", "target_option_key"}, code)
        source_key = _scalar_text(mapping.get("source_asset_key"), code)
        if source_key in seen or mapping.get("mapping_status") not in allowed_statuses:
            _fail(code)
        seen.add(source_key)
        if mapping["mapping_status"] == "matched_existing":
            _scalar_text(mapping.get("target_label"), code)
            _scalar_text(mapping.get("target_option_key"), code)
        elif mapping.get("target_label") is not None or mapping.get("target_option_key") is not None:
            _fail(code)
    return value


def _validate_existing_events(value: Any) -> list[dict[str, Any]]:
    code = "desktop_statement_import_workspace_fixture_invalid"
    if not isinstance(value, list) or not value:
        _fail(code)
    result: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for event in value:
        event = _exact_names(event, {"existing_event_key", "facts", "source_identity_binding"}, code)
        key = _scalar_text(event.get("existing_event_key"), code)
        if key in seen_keys:
            _fail(code)
        seen_keys.add(key)
        binding = event.get("source_identity_binding")
        if binding is not None:
            _scalar_text(binding, code, 240)
        facts = _exact_names(
            event.get("facts"),
            {
                "account_target_key",
                "asset_fee_quantity_decimal",
                "asset_target_key",
                "event_time_utc",
                "event_type",
                "quantity_decimal",
            },
            code,
        )
        for field in ("account_target_key", "asset_target_key", "event_time_utc", "event_type"):
            _scalar_text(facts.get(field), code)
        _decimal_parts(facts.get("asset_fee_quantity_decimal"))
        _decimal_parts(facts.get("quantity_decimal"))
        result.append(event)
    return result


def _fact_signature(facts: dict[str, str]) -> tuple[str, ...]:
    return (
        facts["event_type"],
        facts["asset_target_key"],
        facts["account_target_key"],
        facts["event_time_utc"],
        _decimal_normalized(facts["quantity_decimal"]),
        _decimal_normalized(facts["asset_fee_quantity_decimal"]),
    )


def _reconcile(
    source_identity: str,
    facts: dict[str, str],
    existing_events: list[dict[str, Any]],
) -> tuple[str, int]:
    bound = [event for event in existing_events if event["source_identity_binding"] == source_identity]
    if len(bound) > 1:
        return "ambiguous_match_blocked", len(bound)
    if len(bound) == 1:
        if _fact_signature(bound[0]["facts"]) == _fact_signature(facts):
            return "exact_existing_noop", 1
        return "correction_proposed", 1
    equivalent = [event for event in existing_events if _fact_signature(event["facts"]) == _fact_signature(facts)]
    if not equivalent:
        return "new_candidate", 0
    if len(equivalent) == 1:
        return "existing_link_required", 1
    return "ambiguous_match_blocked", len(equivalent)


def _validate_manual_enrichment(value: Any, scenario: str, expected_txid: str) -> dict[str, Any] | None:
    if scenario == "basis_missing":
        return None
    code = "desktop_statement_import_workspace_fixture_invalid"
    enrichments = _exact_names(value, {"manual_fiat_total", "manual_unit_price"}, code)
    enrichment = enrichments.get(scenario)
    common = {
        "amount_input_mode",
        "exact_local_date",
        "exact_local_time",
        "exact_local_zone",
        "observed_at_utc",
        "price_currency",
        "target_txid",
    }
    expected = common | ({"unit_price_decimal"} if scenario == "manual_unit_price" else {"gross_income_decimal"})
    enrichment = _exact_names(enrichment, expected, code)
    if enrichment.get("target_txid") != expected_txid:
        _fail(code)
    if enrichment.get("price_currency") != "EUR" or enrichment.get("exact_local_zone") != "UTC":
        _fail(code)
    if enrichment.get("amount_input_mode") != (
        "quantity_unit_price" if scenario == "manual_unit_price" else "quantity_gross_amount"
    ):
        _fail(code)
    if (
        enrichment.get("exact_local_date") != "2031-01-03"
        or enrichment.get("exact_local_time") != "08:00:00"
        or enrichment.get("observed_at_utc") != "2031-01-03T08:00:00Z"
    ):
        _fail(code)
    _decimal_parts(enrichment.get("unit_price_decimal") if scenario == "manual_unit_price" else enrichment.get("gross_income_decimal"))
    return enrichment


def _candidate_values(candidate: dict[str, str]) -> list[dict[str, str]]:
    if not candidate or not set(candidate).issubset(_CANDIDATE_FIELDS):
        _fail("desktop_statement_import_workspace_projection_invalid")
    values: list[dict[str, str]] = []
    for field in sorted(candidate):
        value = candidate[field]
        if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 240:
            _fail("desktop_statement_import_workspace_projection_invalid")
        values.append({"field": field, "value": value})
    return values


def _row_for_non_candidate(
    source: dict[str, Any],
    *,
    disposition: str,
    route: str | None,
    domain: str | None,
    mapping_status: str,
    reason_code: str,
) -> dict[str, Any]:
    return {
        "candidate_values": [],
        "domain": domain,
        "existing_match_count": 0,
        "fifo_revalidation_required": False,
        "handoff_eligibility": "not_eligible",
        "mapping_status": mapping_status,
        "mapped_route": route,
        "predecessor_supersession_required": False,
        "reason_code": reason_code,
        "reconciliation_disposition": disposition,
        "source_group_status": "retained_for_grouping",
        "source_identity_status": "stable_txid_bound" if source["identity_error"] is None else "identity_invalid",
        "source_row_key": f"synthetic_row_{source['ordinal']:02d}",
        "source_row_ordinal": source["ordinal"],
        "valuation_status": "not_applicable",
    }


def _build_desktop_statement_import_workspace_synthetic_v1(
    source_bytes: bytes,
    config: dict[str, Any],
    scenario: str,
    *,
    expected_profile_sha256: str | None = None,
) -> dict[str, Any]:
    """Pure synthetic builder used by the tracked-fixture entrypoint and tests."""

    if scenario not in SCENARIOS:
        _fail("desktop_statement_import_workspace_input_invalid")
    config = _exact_names(
        config,
        {
            "catalog_projection",
            "existing_events",
            "manual_enrichments",
            "source_profile",
            "synthetic_statement_import_workspace_input_version",
        },
        "desktop_statement_import_workspace_fixture_invalid",
    )
    if config.get("synthetic_statement_import_workspace_input_version") != 1:
        _fail("desktop_statement_import_workspace_fixture_invalid")
    profile = _validate_profile(config.get("source_profile"), expected_profile_sha256)
    source_rows = _parse_source(source_bytes, profile)
    catalog = _validate_catalog(config.get("catalog_projection"))
    existing_events = _validate_existing_events(config.get("existing_events"))
    enrichment = _validate_manual_enrichment(config.get("manual_enrichments"), scenario, "syn-ledger-003")

    route_rules = {
        (rule["source_type"], rule["source_subtype"], rule["source_asset_class"]): rule
        for rule in profile["route_rules"]
    }
    asset_mappings = {row["source_asset_key"]: row for row in catalog["asset_mappings"]}
    account = catalog["account_mapping"]
    rows: list[dict[str, Any]] = []
    targeted_row_key = "synthetic_row_03"

    for source in source_rows:
        mapped = source["mapped"]
        if source["identity_error"] is not None:
            rows.append(
                _row_for_non_candidate(
                    source,
                    disposition="diagnostic",
                    route=None,
                    domain=None,
                    mapping_status="not_evaluated",
                    reason_code=source["identity_error"],
                )
            )
            continue
        rule = route_rules.get((mapped["source_type"], mapped["source_subtype"], mapped["asset_class"]))
        if rule is None:
            rows.append(
                _row_for_non_candidate(
                    source,
                    disposition="diagnostic",
                    route=None,
                    domain=None,
                    mapping_status="diagnostic_only",
                    reason_code="type_subtype_asset_class_route_unknown",
                )
            )
            continue
        asset_mapping = asset_mappings.get(mapped["source_asset_key"])
        if asset_mapping is None:
            _fail("desktop_statement_import_workspace_fixture_invalid")
        if rule["route"] == "cash":
            rows.append(
                _row_for_non_candidate(
                    source,
                    disposition="cash_domain_deferred",
                    route="cash",
                    domain="cash",
                    mapping_status=asset_mapping["mapping_status"],
                    reason_code="cash_import_owned_by_issue_184",
                )
            )
            continue
        if rule["route"] != "reward":
            rows.append(
                _row_for_non_candidate(
                    source,
                    disposition="deferred",
                    route=rule["route"],
                    domain=rule["domain"],
                    mapping_status=asset_mapping["mapping_status"],
                    reason_code="route_not_in_reward_pilot",
                )
            )
            continue
        if asset_mapping["mapping_status"] != "matched_existing":
            rows.append(
                _row_for_non_candidate(
                    source,
                    disposition="deferred",
                    route="reward",
                    domain="asset_activity",
                    mapping_status=asset_mapping["mapping_status"],
                    reason_code="separate_catalog_handoff_required",
                )
            )
            continue
        quantity = mapped["signed_quantity_decimal"]
        fee = mapped["asset_fee_quantity_decimal"]
        quantity_coefficient, _quantity_scale, _ = _decimal_parts(quantity)
        fee_coefficient, _fee_scale, _ = _decimal_parts(fee)
        if quantity_coefficient <= 0 or fee_coefficient < 0:
            rows.append(
                _row_for_non_candidate(
                    source,
                    disposition="diagnostic",
                    route="reward",
                    domain=None,
                    mapping_status="matched_existing",
                    reason_code="reward_quantity_or_fee_invalid",
                )
            )
            continue
        facts = {
            "account_target_key": account["target_option_key"],
            "asset_fee_quantity_decimal": fee,
            "asset_target_key": asset_mapping["target_option_key"],
            "event_time_utc": source["event_time_utc"],
            "event_type": "reward",
            "quantity_decimal": quantity,
        }
        source_identity = (
            f"{profile['source_profile_id']}:{profile['source_profile_revision']}:{mapped['source_row_id']}"
        )
        disposition, match_count = _reconcile(source_identity, facts, existing_events)
        candidate = {
            "account_key": account["source_account_scope"],
            "amount_input_mode": "quantity_only",
            "asset_fee_quantity_decimal": fee,
            "basis_evidence_mode": "basis_missing",
            "event_time_evidence": "exact_local_zone",
            "event_type": "reward",
            "fee_role": "asset_fee",
            "local_date": source["local_date"],
            "local_time": source["local_time"],
            "quantity_decimal": quantity,
            "source_asset_key": mapped["source_asset_key"],
            "source_reference": mapped["source_row_id"],
            "time_zone": profile["time_zone"],
        }
        valuation_status = "basis_missing"
        if enrichment is not None and mapped["source_row_id"] == enrichment["target_txid"]:
            candidate["amount_input_mode"] = enrichment["amount_input_mode"]
            candidate["basis_evidence_mode"] = "valuation_confirmed_as_basis"
            candidate["price_currency"] = enrichment["price_currency"]
            if scenario == "manual_unit_price":
                candidate["unit_price_decimal"] = enrichment["unit_price_decimal"]
                candidate["gross_income_decimal"] = _decimal_multiply_exact(
                    quantity,
                    enrichment["unit_price_decimal"],
                )
                valuation_status = "manual_unit_price_exact"
            else:
                candidate["gross_income_decimal"] = enrichment["gross_income_decimal"]
                valuation_status = "manual_fiat_total_exact"
        if disposition == "exact_existing_noop":
            handoff = "excluded_exact_noop"
            valuation_status = "not_required_exact_noop"
        elif disposition == "correction_proposed":
            handoff = "separate_correction_confirmation_required"
        elif disposition == "existing_link_required":
            handoff = "separate_lineage_confirmation_required"
        elif disposition == "ambiguous_match_blocked":
            handoff = "blocked_ambiguous_match"
        elif valuation_status == "basis_missing":
            handoff = "blocked_basis_missing"
        else:
            handoff = "ready_untrusted_candidate"
        reason_codes = {
            "new_candidate": "no_existing_match",
            "exact_existing_noop": "bound_existing_facts_identical",
            "existing_link_required": "one_unbound_existing_fact_match",
            "correction_proposed": "bound_existing_facts_changed",
            "ambiguous_match_blocked": "multiple_existing_fact_matches",
        }
        rows.append(
            {
                "candidate_values": _candidate_values(candidate),
                "domain": "asset_activity",
                "existing_match_count": match_count,
                "fifo_revalidation_required": disposition == "correction_proposed",
                "handoff_eligibility": handoff,
                "mapping_status": "matched_existing",
                "mapped_route": "reward",
                "predecessor_supersession_required": disposition == "correction_proposed",
                "reason_code": reason_codes[disposition],
                "reconciliation_disposition": disposition,
                "source_group_status": "retained_for_grouping",
                "source_identity_status": "stable_txid_bound",
                "source_row_key": f"synthetic_row_{source['ordinal']:02d}",
                "source_row_ordinal": source["ordinal"],
                "valuation_status": valuation_status,
            }
        )

    counts = [
        {"count": sum(row["reconciliation_disposition"] == disposition for row in rows), "disposition": disposition}
        for disposition in DISPOSITIONS
    ]
    if sum(row["count"] for row in counts) != len(source_rows) or len(rows) != len(source_rows):
        _fail("desktop_statement_import_workspace_reconciliation_invalid")
    manual = None
    if enrichment is not None:
        manual = {
            "amount_input_mode": enrichment["amount_input_mode"],
            "basis_evidence_mode": "valuation_confirmed_as_basis",
            "exact_local_date": enrichment["exact_local_date"],
            "exact_local_time": enrichment["exact_local_time"],
            "exact_local_zone": enrichment["exact_local_zone"],
            "gross_income_decimal": next(
                item["value"]
                for row in rows
                if row["source_row_key"] == targeted_row_key
                for item in row["candidate_values"]
                if item["field"] == "gross_income_decimal"
            ),
            "observed_at_utc": enrichment["observed_at_utc"],
            "price_currency": enrichment["price_currency"],
            "unit_price_decimal": enrichment.get("unit_price_decimal"),
        }
    public_asset_mappings = [dict(row) for row in catalog["asset_mappings"]]
    creation_requests = [
        {
            "entity_type": "asset",
            "separate_confirmation_required": True,
            "source_asset_key": row["source_asset_key"],
            "synthetic_preview_status": "ready",
        }
        for row in public_asset_mappings
        if row["mapping_status"] == "separate_catalog_handoff_required"
    ]
    projection: dict[str, Any] = {
        "activation_authorized": False,
        "activity_draft_write": False,
        "automatic_retry": False,
        "candidate_handoff_available": False,
        "canonical_write": False,
        "cash_completeness_claimed": False,
        "cash_handoff_available": False,
        "cash_write": False,
        "catalog_handoff_available": False,
        "catalog_review": {
            "account_mappings": [dict(account)],
            "asset_mappings": public_asset_mappings,
            "catalog_creation_requests": creation_requests,
            "catalog_write": False,
            "portfolio_selection": dict(catalog["portfolio_selection"]),
        },
        "column_mappings": [dict(row) for row in profile["column_mappings"]],
        "confirmation_available": False,
        "context_exposed": False,
        "correction_confirmation_available": False,
        "desktop_statement_import_workspace_version": 1,
        "execution_purpose": "public_synthetic_mapping_reconciliation",
        "fingerprint_exposed": False,
        "identity_policy": dict(profile["identity_policy"]),
        "lineage_confirmation_available": False,
        "mapping_apply_available": False,
        "network_access": False,
        "normal_adapter_execution_available": False,
        "owner_accepted_disabled_recorded": False,
        "path_exposed": False,
        "portfolio_completeness_claimed": False,
        "private_owner_uat_completed": False,
        "private_source_read": False,
        "provider_access": False,
        "provider_enrichment": {
            "automatic_retry": False,
            "market_history_plan_available": False,
            "network_access": False,
            "provider_access": False,
            "status": "disabled_separate_market_history_plan_required",
        },
        "reconciliation_summary": {
            "candidate_projection_count": sum(bool(row["candidate_values"]) for row in rows),
            "date_only_match_count": 0,
            "disposition_counts": counts,
            "handoff_ready_count": sum(row["handoff_eligibility"] == "ready_untrusted_candidate" for row in rows),
            "silent_drop_count": 0,
            "source_row_count": len(rows),
        },
        "route_rules": [dict(row) for row in profile["route_rules"]],
        "rows": rows,
        "scenario": scenario,
        "source_is_public_invented_fixture": True,
        "source_profile_private_accepted": False,
        "source_profile": {
            "column_count": len(profile["header_columns"]),
            "export_profile": profile["export_profile"],
            "format_version": profile["format_version"],
            "header_change_policy": "new_immutable_profile_revision_required",
            "header_status": "exact_match",
            "institution": profile["institution"],
            "locale": profile["locale"],
            "medium": profile["medium"],
            "private_owner_uat_status": "not_completed",
            "source_profile_id": profile["source_profile_id"],
            "source_profile_revision": profile["source_profile_revision"],
            "source_profile_status": profile["source_profile_status"],
        },
        "sql_access": False,
        "status": "synthetic_workspace_ready",
        "tax_write": False,
        "temporary_output_persisted": False,
        "valuation_confirmation_available": False,
        "valuation_review": {
            "exact_decimal_arithmetic": True,
            "manual_input": manual,
            "rounding_applied": False,
            "scenario": scenario,
            "target_source_row_key": targeted_row_key,
            "valuation_status": "basis_missing" if manual is None else f"{scenario}_exact",
        },
    }
    _validate_public_projection(projection)
    return projection


def _validate_public_projection(value: dict[str, Any]) -> None:
    def walk(child: Any) -> None:
        if isinstance(child, dict):
            if set(child).intersection(_FORBIDDEN_PUBLIC_KEYS):
                _fail("desktop_statement_import_workspace_projection_invalid")
            for nested in child.values():
                walk(nested)
        elif isinstance(child, list):
            for nested in child:
                walk(nested)
        elif child is not None and type(child) not in {str, int, bool}:
            _fail("desktop_statement_import_workspace_projection_invalid")

    walk(value)
    required = {
        "activation_authorized",
        "activity_draft_write",
        "automatic_retry",
        "candidate_handoff_available",
        "canonical_write",
        "cash_completeness_claimed",
        "cash_handoff_available",
        "cash_write",
        "catalog_handoff_available",
        "catalog_review",
        "column_mappings",
        "confirmation_available",
        "context_exposed",
        "correction_confirmation_available",
        "desktop_statement_import_workspace_version",
        "execution_purpose",
        "fingerprint_exposed",
        "identity_policy",
        "lineage_confirmation_available",
        "mapping_apply_available",
        "network_access",
        "normal_adapter_execution_available",
        "owner_accepted_disabled_recorded",
        "path_exposed",
        "portfolio_completeness_claimed",
        "private_owner_uat_completed",
        "private_source_read",
        "provider_access",
        "provider_enrichment",
        "reconciliation_summary",
        "route_rules",
        "rows",
        "scenario",
        "source_is_public_invented_fixture",
        "source_profile_private_accepted",
        "source_profile",
        "sql_access",
        "status",
        "tax_write",
        "temporary_output_persisted",
        "valuation_confirmation_available",
        "valuation_review",
    }
    if set(value) != required:
        _fail("desktop_statement_import_workspace_projection_invalid")
    if (
        value.get("desktop_statement_import_workspace_version") != 1
        or value.get("status") != "synthetic_workspace_ready"
        or value.get("execution_purpose") != "public_synthetic_mapping_reconciliation"
        or value.get("scenario") not in SCENARIOS
        or value.get("source_is_public_invented_fixture") is not True
    ):
        _fail("desktop_statement_import_workspace_projection_invalid")
    false_fields = required.intersection(
        {
            "activation_authorized",
            "activity_draft_write",
            "automatic_retry",
            "candidate_handoff_available",
            "canonical_write",
            "cash_completeness_claimed",
            "cash_handoff_available",
            "cash_write",
            "catalog_handoff_available",
            "confirmation_available",
            "context_exposed",
            "correction_confirmation_available",
            "fingerprint_exposed",
            "lineage_confirmation_available",
            "mapping_apply_available",
            "network_access",
            "normal_adapter_execution_available",
            "owner_accepted_disabled_recorded",
            "path_exposed",
            "portfolio_completeness_claimed",
            "private_owner_uat_completed",
            "private_source_read",
            "provider_access",
            "source_profile_private_accepted",
            "sql_access",
            "tax_write",
            "temporary_output_persisted",
            "valuation_confirmation_available",
        }
    )
    if any(value.get(field) is not False for field in false_fields):
        _fail("desktop_statement_import_workspace_projection_invalid")
    summary = value.get("reconciliation_summary")
    if not isinstance(summary, dict) or summary.get("silent_drop_count") != 0:
        _fail("desktop_statement_import_workspace_projection_invalid")
    rows = value.get("rows")
    counts = summary.get("disposition_counts")
    if not isinstance(rows, list) or not isinstance(counts, list) or len(counts) != len(DISPOSITIONS):
        _fail("desktop_statement_import_workspace_projection_invalid")
    if [row.get("disposition") for row in counts] != list(DISPOSITIONS):
        _fail("desktop_statement_import_workspace_projection_invalid")
    if summary.get("source_row_count") != len(rows) or sum(row.get("count", -1) for row in counts) != len(rows):
        _fail("desktop_statement_import_workspace_projection_invalid")
    if [row.get("source_row_ordinal") for row in rows] != list(range(1, len(rows) + 1)):
        _fail("desktop_statement_import_workspace_projection_invalid")
    if len({row.get("source_row_key") for row in rows}) != len(rows):
        _fail("desktop_statement_import_workspace_projection_invalid")
    for row in rows:
        if row.get("reconciliation_disposition") not in DISPOSITIONS:
            _fail("desktop_statement_import_workspace_projection_invalid")
        values = row.get("candidate_values")
        if not isinstance(values, list) or [item.get("field") for item in values] != sorted(item.get("field") for item in values):
            _fail("desktop_statement_import_workspace_projection_invalid")
        if any(set(item) != {"field", "value"} or item.get("field") not in _CANDIDATE_FIELDS for item in values):
            _fail("desktop_statement_import_workspace_projection_invalid")


def review_desktop_statement_import_workspace_synthetic_v1(scenario: str) -> dict[str, Any]:
    """Review the fixed public invented Kraken-ledger fixture without private access."""

    if not isinstance(scenario, str) or scenario not in SCENARIOS:
        _fail("desktop_statement_import_workspace_input_invalid")
    source_bytes, config, profile_sha = _load_tracked_synthetic_input()
    return _build_desktop_statement_import_workspace_synthetic_v1(
        source_bytes,
        config,
        scenario,
        expected_profile_sha256=profile_sha,
    )


__all__ = [
    "DesktopStatementImportWorkspaceError",
    "canonical_desktop_statement_import_workspace_json_bytes_v1",
    "review_desktop_statement_import_workspace_synthetic_v1",
]
