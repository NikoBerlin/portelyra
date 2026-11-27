"""Deterministic, provider-neutral Statement CSV source profiler v1.

The engine accepts bytes already read by a separately authorized boundary. It has
no path, provider, persistence, activation, Candidate, or Product-write API.
Private header names and semantic tokens remain only in ``private_review``;
``public_projection`` is safe for browser/process boundaries.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts/desktop-statement-source-profiler/v1"
MAX_BYTES = 32_000_000
DELIMITERS = (("comma", ","), ("semicolon", ";"), ("tab", "\t"))
REQUIRED_ROLES = (
    "source_row_id",
    "source_group_id",
    "event_time_text",
    "source_type",
    "source_subtype",
    "asset_class",
    "source_asset_key",
    "signed_quantity_decimal",
    "asset_fee_quantity_decimal",
    "balance_reconciliation_evidence",
)
SEMANTIC_ROLES = ("source_type", "source_subtype", "asset_class")
DECIMAL_ROLES = (
    "signed_quantity_decimal",
    "asset_fee_quantity_decimal",
    "balance_reconciliation_evidence",
)
TOKEN = re.compile(r"[a-z][a-z0-9_]{1,79}")
DOT_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?")
COMMA_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]*)(?:,[0-9]+)?")
TIME_FORMATS = (
    ("ymd_space_hms", re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")),
    ("ymd_space_hms_fraction", re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+")),
    ("iso_utc", re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")),
    ("iso_offset", re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2}")),
)
FAILURE_CODES = frozenset(
    {
        "desktop_statement_source_profiler_alias_registry_invalid",
        "desktop_statement_source_profiler_boundary_failed",
        "desktop_statement_source_profiler_csv_ambiguous",
        "desktop_statement_source_profiler_csv_invalid",
        "desktop_statement_source_profiler_input_invalid",
        "desktop_statement_source_profiler_utf8_invalid",
    }
)


class DesktopStatementSourceProfilerError(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            code = "desktop_statement_source_profiler_boundary_failed"
        self.code = code
        super().__init__(code)


def _fail(code: str) -> None:
    raise DesktopStatementSourceProfilerError(code)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _normalize_header(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).strip().casefold()
    text = re.sub(r"[\s\-]+", "_", text)
    if not text or not text.isascii() or TOKEN.fullmatch(text) is None:
        return ""
    return text


def _load_aliases() -> tuple[dict[str, str], str]:
    path = CONTRACT / "header-role-aliases.csv"
    try:
        raw = path.read_bytes()
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8", errors="strict"), newline=""), strict=True)
        if reader.fieldnames != ["normalized_header", "role", "status"]:
            raise ValueError("header")
        rows = list(reader)
        aliases: dict[str, str] = {}
        for row in rows:
            if (
                set(row) != {"normalized_header", "role", "status"}
                or row["status"] != "explicit_alias"
                or _normalize_header(row["normalized_header"]) != row["normalized_header"]
                or row["role"] not in REQUIRED_ROLES
                or row["normalized_header"] in aliases
            ):
                raise ValueError("row")
            aliases[row["normalized_header"]] = row["role"]
        if not aliases or set(REQUIRED_ROLES) - set(aliases.values()):
            raise ValueError("coverage")
        return aliases, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeDecodeError, csv.Error, ValueError):
        _fail("desktop_statement_source_profiler_alias_registry_invalid")


def _decode(raw: bytes) -> tuple[str, str]:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES or b"\x00" in raw:
        _fail("desktop_statement_source_profiler_input_invalid")
    encoding = "utf8_bom" if raw.startswith(b"\xef\xbb\xbf") else "utf8"
    try:
        return raw.decode("utf-8-sig" if encoding == "utf8_bom" else "utf-8", errors="strict"), encoding
    except UnicodeDecodeError:
        _fail("desktop_statement_source_profiler_utf8_invalid")


def _parse_candidate(text: str, delimiter: str) -> list[list[str]] | None:
    try:
        records = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
    except csv.Error:
        return None
    if len(records) < 2 or len(records[0]) < 2:
        return None
    width = len(records[0])
    if any(len(record) != width for record in records):
        return None
    return records


def _detect_records(text: str) -> tuple[str, str, list[list[str]]]:
    candidates: list[tuple[str, str, list[list[str]]]] = []
    for code, delimiter in DELIMITERS:
        records = _parse_candidate(text, delimiter)
        if records is not None:
            candidates.append((code, delimiter, records))
    if not candidates:
        _fail("desktop_statement_source_profiler_csv_invalid")
    maximum = max(len(candidate[2][0]) for candidate in candidates)
    winners = [candidate for candidate in candidates if len(candidate[2][0]) == maximum]
    if len(winners) != 1:
        _fail("desktop_statement_source_profiler_csv_ambiguous")
    return winners[0]


def _lexical_decimal_format(values: list[str]) -> str:
    nonempty = [value.strip() for value in values if value.strip()]
    if not nonempty:
        return "no_nonempty_values"
    dot = all(DOT_DECIMAL.fullmatch(value) is not None for value in nonempty)
    comma = all(COMMA_DECIMAL.fullmatch(value) is not None for value in nonempty)
    if dot and comma:  # integer-only evidence cannot establish a separator
        return "integer_only_ambiguous_separator"
    if dot:
        return "decimal_dot"
    if comma:
        return "decimal_comma"
    return "mixed_or_invalid"


def _lexical_time_format(values: list[str]) -> str:
    nonempty = [value.strip() for value in values if value.strip()]
    if not nonempty:
        return "no_nonempty_values"
    matches = [code for code, pattern in TIME_FORMATS if all(pattern.fullmatch(value) for value in nonempty)]
    return matches[0] if len(matches) == 1 else "mixed_or_unknown"


@dataclass(frozen=True)
class StatementSourceProfileInspectionV1:
    private_review: dict[str, Any]
    _public: dict[str, Any]

    def public_projection(self) -> dict[str, Any]:
        return json.loads(_canonical(self._public).decode("ascii"))


def inspect_statement_source_bytes_v1(source_bytes: bytes, *, institution_hint: str | None = None) -> StatementSourceProfileInspectionV1:
    """Inspect bytes in memory without inferring business routes or writing output."""
    if institution_hint is not None and institution_hint not in {"kraken", "unknown"}:
        _fail("desktop_statement_source_profiler_input_invalid")
    aliases, aliases_sha256 = _load_aliases()
    text, encoding = _decode(source_bytes)
    delimiter_code, _delimiter, records = _detect_records(text)
    header = records[0]
    normalized = [_normalize_header(value) for value in header]
    normalized_valid = all(normalized)
    duplicate_headers = len(normalized) - len(set(normalized))

    role_to_indices: dict[str, list[int]] = {role: [] for role in REQUIRED_ROLES}
    dispositions: list[dict[str, Any]] = []
    for index, (raw_header, normalized_header) in enumerate(zip(header, normalized)):
        role = aliases.get(normalized_header) if normalized_header else None
        if role is not None:
            role_to_indices[role].append(index)
        dispositions.append(
            {
                "column_ordinal": index + 1,
                "normalized_header": normalized_header,
                "raw_header": raw_header,
                "role": role,
                "status": "explicit_alias_match" if role else "owner_role_review_required",
            }
        )

    role_status: dict[str, str] = {}
    for role, indices in role_to_indices.items():
        role_status[role] = "mapped_unique" if len(indices) == 1 else "missing" if not indices else "ambiguous_multiple_columns"

    rows = records[1:]
    blank_rows = sum(all(not value.strip() for value in row) for row in rows)
    row_id_index = role_to_indices["source_row_id"][0] if len(role_to_indices["source_row_id"]) == 1 else None
    row_ids = [row[row_id_index] for row in rows] if row_id_index is not None else []
    nonempty_ids = [value for value in row_ids if value.strip()]
    duplicate_row_id_count = len(nonempty_ids) - len(set(nonempty_ids))
    missing_row_id_count = len(row_ids) - len(nonempty_ids)

    semantic_review: dict[str, Any] = {}
    for role in SEMANTIC_ROLES:
        indices = role_to_indices[role]
        values = [row[indices[0]] for row in rows] if len(indices) == 1 else []
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        semantic_review[role] = {
            "distinct_values": [{"value": value, "row_count": counts[value]} for value in sorted(counts)],
            "route_inference": False,
            "status": "owner_route_mapping_required" if values else "unavailable",
        }

    semantic_tuple_counts: dict[tuple[str, str, str], int] = {}
    semantic_indices = [role_to_indices[role] for role in SEMANTIC_ROLES]
    if all(len(indices) == 1 for indices in semantic_indices):
        for row in rows:
            key = tuple(row[indices[0]] for indices in semantic_indices)
            semantic_tuple_counts[key] = semantic_tuple_counts.get(key, 0) + 1

    decimal_formats: dict[str, str] = {}
    for role in DECIMAL_ROLES:
        indices = role_to_indices[role]
        decimal_formats[role] = _lexical_decimal_format([row[indices[0]] for row in rows]) if len(indices) == 1 else "unavailable"
    time_indices = role_to_indices["event_time_text"]
    time_format = _lexical_time_format([row[time_indices[0]] for row in rows]) if len(time_indices) == 1 else "unavailable"

    missing_roles = sum(status == "missing" for status in role_status.values())
    ambiguous_roles = sum(status == "ambiguous_multiple_columns" for status in role_status.values())
    unmapped_columns = sum(item["role"] is None for item in dispositions)
    lexical_blocked = (
        time_format in {"unavailable", "no_nonempty_values", "mixed_or_unknown"}
        or any(
            value in {"unavailable", "no_nonempty_values", "integer_only_ambiguous_separator", "mixed_or_invalid"}
            for value in decimal_formats.values()
        )
    )
    structurally_ready = (
        normalized_valid
        and duplicate_headers == 0
        and missing_roles == 0
        and ambiguous_roles == 0
        and unmapped_columns == 0
        and blank_rows == 0
        and missing_row_id_count == 0
        and duplicate_row_id_count == 0
        and not lexical_blocked
    )
    status = "ready_for_owner_semantic_review" if structurally_ready else "owner_mapping_or_format_review_required"

    private_review = {
        "alias_registry_sha256": aliases_sha256,
        "column_dispositions": dispositions,
        "decimal_formats": decimal_formats,
        "delimiter": delimiter_code,
        "encoding": encoding,
        "identity_evidence": {
            "duplicate_source_row_id_count": duplicate_row_id_count,
            "missing_source_row_id_count": missing_row_id_count,
            "row_count": len(rows),
        },
        "institution_hint": institution_hint or "unknown",
        "raw_header_retained_after_process": False,
        "route_rules_created": False,
        "semantic_review": semantic_review,
        "semantic_route_tuples": [
            {
                "asset_class": key[2],
                "row_count": semantic_tuple_counts[key],
                "source_subtype": key[1],
                "source_type": key[0],
            }
            for key in sorted(semantic_tuple_counts)
        ],
        "source_bytes_retained_after_process": False,
        "statement_source_private_review_version": 1,
        "status": status,
        "time_format": time_format,
        "time_zone_inferred": False,
    }
    public = {
        "activation_authorized": False,
        "ambiguous_role_count": ambiguous_roles,
        "automatic_retry": False,
        "canonical_write": False,
        "cash_write": False,
        "column_count": len(header),
        "decimal_format_review_required": any(value != "decimal_dot" for value in decimal_formats.values()),
        "delimiter": delimiter_code,
        "duplicate_header_count": duplicate_headers,
        "duplicate_source_row_id_count": duplicate_row_id_count,
        "encoding": encoding,
        "header_values_exposed": False,
        "missing_role_count": missing_roles,
        "missing_source_row_id_count": missing_row_id_count,
        "network_access": False,
        "private_values_published": False,
        "provider_access": False,
        "route_rules_created": False,
        "row_count": len(rows),
        "semantic_tuple_count": len(semantic_tuple_counts),
        "semantic_values_exposed": False,
        "silent_drop_count": 0,
        "source_path_exposed": False,
        "statement_source_profiler_public_result_version": 1,
        "status": status,
        "time_format": time_format,
        "time_zone_inferred": False,
        "unmapped_column_count": unmapped_columns,
    }
    return StatementSourceProfileInspectionV1(private_review=private_review, _public=public)


def inspect_registered_synthetic_statement_sources_v1() -> list[dict[str, Any]]:
    """Run only repository-tracked invented variants; no path input is accepted."""
    fixture_root = ROOT / "fixtures/product/statement-source-profiler-v1"
    variants = ("ordered.csv", "reordered-bom.csv", "semicolon.csv", "unknown-column.csv")
    results: list[dict[str, Any]] = []
    for name in variants:
        raw = fixture_root.joinpath(name).read_bytes()
        result = inspect_statement_source_bytes_v1(raw, institution_hint="kraken").public_projection()
        result["fixture_case"] = name.removesuffix(".csv").replace("-", "_")
        results.append(result)
    return results
