"""Read-only Legacy assets.csv companion projection for one Asset migration.

The source Asset_ID is used only for exact local matching and redacted lineage.
Provider, Listing, Account, Grouping and Tax values never enter the reviewed
candidate. This module performs no canonical write and prints nothing.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

CONTRACT_VERSION = 1
MAX_SOURCE_BYTES = 10_000_000
REQUIRED_HEADERS = frozenset({"Asset_ID", "Wertpapierbezeichnung"})
OPTIONAL_SOURCE_FIELDS = {"isin": "ISIN", "wkn": "WKN", "note": "Notiz"}
CLASSIFICATION_HINT_FIELDS = {
    "category_present": "Kategorie",
    "cash_flag_present": "Ist_Cash",
    "tax_type_present": "Steuertyp",
}
ASSET_TYPES = frozenset(
    {
        "equity",
        "etf",
        "fund",
        "bond",
        "derivative",
        "crypto",
        "commodity",
        "cash",
        "fx",
        "index",
        "other",
    }
)
FIELD_POLICIES = {
    "Asset_ID": ("source_identity", "exact_link_only"),
    "Wertpapierbezeichnung": ("presentation", "required_candidate"),
    "ISIN": ("identifier", "optional_candidate"),
    "WKN": ("identifier", "optional_candidate"),
    "Notiz": ("presentation", "optional_candidate"),
    "Kategorie": ("classification_hint", "presence_only"),
    "Ist_Cash": ("classification_hint", "presence_only"),
    "Steuertyp": ("tax_hint", "presence_only"),
    "Asset": ("listing_hint", "excluded"),
    "Währung": ("transaction_hint", "excluded"),
    "Steuersatz": ("tax", "excluded"),
    "Teilfreistellung": ("tax", "excluded"),
    "Kurs_Symbol": ("market_identity", "excluded"),
    "Kurs_Währung": ("market_identity", "excluded"),
    "Price_Currency": ("market_identity", "excluded"),
    "Kurs_Provider": ("provider_identity", "excluded"),
    "Daily_Kurs_Provider": ("provider_identity", "excluded"),
    "Daily_Kurs_Währung": ("market_identity", "excluded"),
    "Daily_Fallback_Chain": ("provider_policy", "excluded"),
    "Realtime_Kurs_Provider": ("provider_identity", "excluded"),
    "Realtime_Kurs_Währung": ("market_identity", "excluded"),
    "Realtime_Fallback_Chain": ("provider_policy", "excluded"),
    "Provider_Modell_Status": ("provider_policy", "excluded"),
    "Kurs_Exchange": ("listing_identity", "excluded"),
    "Kurs_MIC_Code": ("listing_identity", "excluded"),
    "Kurs_Instrument_Type": ("listing_identity", "excluded"),
    "Kurs_Provider_Symbol": ("provider_identity", "excluded"),
    "Kurs_Mapping_Status": ("provider_policy", "excluded"),
    "Kurs_Mapping_Method": ("provider_policy", "excluded"),
    "Kurs_Mapping_Provider": ("provider_identity", "excluded"),
    "Kurs_Mapping_Verified_At": ("provider_evidence", "excluded"),
    "Kurs_Mapping_Source_Endpoint": ("provider_evidence", "excluded"),
    "Kurs_Fallback_Chain": ("provider_policy", "excluded"),
    "Yahoo_Symbol_Alt": ("provider_identity", "excluded"),
    "Yahoo_Exchange_Alt": ("listing_identity", "excluded"),
    "Yahoo_Quote_Type_Alt": ("provider_identity", "excluded"),
    "TD_Symbol": ("provider_identity", "excluded"),
    "TD_Exchange": ("listing_identity", "excluded"),
    "TD_MIC_Code": ("listing_identity", "excluded"),
    "TD_Instrument_Type": ("listing_identity", "excluded"),
    "TD_Currency": ("market_identity", "excluded"),
    "TD_Request_Symbol": ("provider_identity", "excluded"),
    "Fundamentals_Symbol": ("provider_identity", "excluded"),
    "Default_Depot": ("account_hint", "excluded"),
    "Allokationsgruppe": ("grouping", "excluded"),
    "Ziel_Ebene": ("allocation", "excluded"),
    "Ziel_Prozent": ("allocation", "excluded"),
    "Minimum_Prozent": ("allocation", "excluded"),
    "Maximum_Prozent": ("allocation", "excluded"),
    "Aktiv": ("lifecycle", "excluded"),
    "Watchlist_Aktiv": ("watchlist", "excluded"),
    "Watchlist_Status": ("watchlist", "excluded"),
    "Watchlist_Limitkurs": ("watchlist", "excluded"),
    "Watchlist_Zielkurs": ("watchlist", "excluded"),
    "Watchlist_Korridor_Unten": ("watchlist", "excluded"),
    "Watchlist_Korridor_Oben": ("watchlist", "excluded"),
    "User_Score": ("analysis_input", "excluded"),
    "User_Confidence": ("analysis_input", "excluded"),
    "User_These": ("analysis_input", "excluded"),
    "User_Risk_Note": ("analysis_input", "excluded"),
}
PROVIDER_LISTING_ROLES = frozenset(
    {"market_identity", "provider_identity", "provider_policy", "provider_evidence", "listing_identity"}
)
FAILURE_CODES = frozenset(
    {
        "legacy_asset_companion_asset_id_duplicate",
        "legacy_asset_companion_asset_id_invalid",
        "legacy_asset_companion_asset_id_not_found",
        "legacy_asset_companion_asset_type_invalid",
        "legacy_asset_companion_boundary_failed",
        "legacy_asset_companion_display_name_invalid",
        "legacy_asset_companion_input_invalid",
        "legacy_asset_companion_optional_field_invalid",
        "legacy_asset_companion_quantity_scale_invalid",
        "legacy_asset_companion_review_invalid",
        "legacy_asset_companion_review_stale",
        "legacy_asset_companion_source_changed",
        "legacy_asset_companion_source_csv_invalid",
        "legacy_asset_companion_source_encoding_invalid",
        "legacy_asset_companion_source_file_invalid",
        "legacy_asset_companion_source_header_invalid",
    }
)
_ISIN = re.compile(r"[A-Z0-9]{12}")
_WKN = re.compile(r"[A-Z0-9]{6}")
_FINGERPRINT = re.compile(r"[a-f0-9]{64}")


class LegacyAssetCompanionV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("legacy_asset_companion_error_code_unregistered")
        self.code = code
        super().__init__(code)


def legacy_asset_companion_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise LegacyAssetCompanionV1Error(code)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _clean_asset_id(value: Any) -> str:
    if not isinstance(value, str):
        _abort("legacy_asset_companion_asset_id_invalid")
    result = value.strip()
    if not result or len(result.encode("utf-8")) > 200 or any(ord(char) < 32 for char in result):
        _abort("legacy_asset_companion_asset_id_invalid")
    return result


def _clean_display_name(value: Any) -> str:
    if not isinstance(value, str):
        _abort("legacy_asset_companion_display_name_invalid")
    result = value.strip()
    if not 1 <= len(result) <= 160 or any(ord(char) < 32 for char in result):
        _abort("legacy_asset_companion_display_name_invalid")
    return result


def _decode_source(source_bytes: bytes) -> str:
    if not isinstance(source_bytes, bytes) or not source_bytes or len(source_bytes) > MAX_SOURCE_BYTES:
        _abort("legacy_asset_companion_source_file_invalid")
    try:
        text = source_bytes.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        _abort("legacy_asset_companion_source_encoding_invalid")
    if "\x00" in text:
        _abort("legacy_asset_companion_source_encoding_invalid")
    return text


def _reader_rows(text: str, delimiter: str) -> tuple[list[str], list[list[str]]]:
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        records = [row for row in reader if row]
    except (csv.Error, UnicodeError):
        _abort("legacy_asset_companion_source_csv_invalid")
    if not records:
        _abort("legacy_asset_companion_source_csv_invalid")
    headers = [item.strip() for item in records[0]]
    if any(not item for item in headers) or len(headers) != len(set(headers)):
        _abort("legacy_asset_companion_source_header_invalid")
    rows = records[1:]
    if any(len(row) != len(headers) for row in rows):
        _abort("legacy_asset_companion_source_csv_invalid")
    return headers, rows


def _parse_source(source_bytes: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = _decode_source(source_bytes)
    candidates: list[tuple[list[str], list[list[str]]]] = []
    for delimiter in (";", ","):
        try:
            headers, rows = _reader_rows(text, delimiter)
        except LegacyAssetCompanionV1Error:
            continue
        if REQUIRED_HEADERS.issubset(headers):
            candidates.append((headers, rows))
    if len(candidates) != 1:
        _abort("legacy_asset_companion_source_header_invalid")
    headers, rows = candidates[0]
    return headers, [dict(zip(headers, row, strict=True)) for row in rows]


def _projection_impl(source_bytes: bytes, source_asset_id: str) -> dict[str, Any]:
    normalized_asset_id = _clean_asset_id(source_asset_id)
    headers, rows = _parse_source(source_bytes)
    matches = [row for row in rows if str(row.get("Asset_ID", "")).strip() == normalized_asset_id]
    if not matches:
        _abort("legacy_asset_companion_asset_id_not_found")
    if len(matches) != 1:
        _abort("legacy_asset_companion_asset_id_duplicate")
    row = matches[0]
    display_name = _clean_display_name(row.get("Wertpapierbezeichnung"))
    optional_candidates = {
        field: (str(row.get(source_field, "")).strip() or None)
        for field, source_field in OPTIONAL_SOURCE_FIELDS.items()
    }
    classification_hint_presence = {
        field: bool(str(row.get(source_field, "")).strip())
        for field, source_field in CLASSIFICATION_HINT_FIELDS.items()
    }
    disposition_counts = {
        "exact_link_only": 0,
        "required_candidate": 0,
        "optional_candidate": 0,
        "presence_only": 0,
        "excluded": 0,
        "unknown_excluded": 0,
    }
    provider_listing_field_count = 0
    for header in headers:
        policy = FIELD_POLICIES.get(header)
        if policy is None:
            disposition_counts["unknown_excluded"] += 1
            continue
        role, projection_policy = policy
        disposition_counts[projection_policy] += 1
        if role in PROVIDER_LISTING_ROLES:
            provider_listing_field_count += 1
    link_fingerprint = _sha256_bytes(normalized_asset_id.encode("utf-8"))
    selected_row = [row[header] for header in headers]
    result = {
        "asset_companion_version": CONTRACT_VERSION,
        "projection_status": "ready_for_review",
        "source_asset_link_fingerprint": link_fingerprint,
        "source_file_fingerprint": _sha256_bytes(source_bytes),
        "source_header_fingerprint": _fingerprint(headers),
        "source_row_fingerprint": _fingerprint(selected_row),
        "display_name_candidate": display_name,
        "optional_candidates": optional_candidates,
        "classification_hint_presence": classification_hint_presence,
        "field_disposition_counts": disposition_counts,
        "provider_listing_field_count": provider_listing_field_count,
        "provider_listing_value_imported": False,
        "tax_value_imported": False,
        "account_binding_imported": False,
        "grouping_allocation_imported": False,
        "canonical_write": False,
        "private_output_logged": False,
    }
    result["projection_fingerprint"] = _fingerprint(result)
    return result


def project_legacy_asset_companion_bytes_v1(source_bytes: bytes, source_asset_id: str) -> dict[str, Any]:
    try:
        return _projection_impl(source_bytes, source_asset_id)
    except LegacyAssetCompanionV1Error:
        raise
    except Exception:
        raise LegacyAssetCompanionV1Error("legacy_asset_companion_boundary_failed") from None


def _path_without_symlink(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if current.is_symlink():
                return False
        except OSError:
            return False
    return True


def _read_regular_file(path_value: Any) -> bytes:
    if not isinstance(path_value, (str, os.PathLike)):
        _abort("legacy_asset_companion_source_file_invalid")
    path = Path(path_value)
    if not path.is_absolute() or not _path_without_symlink(path):
        _abort("legacy_asset_companion_source_file_invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _abort("legacy_asset_companion_source_file_invalid")
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size <= 0 or before.st_size > MAX_SOURCE_BYTES:
            _abort("legacy_asset_companion_source_file_invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                _abort("legacy_asset_companion_source_changed")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _abort("legacy_asset_companion_source_changed")
        after = os.fstat(descriptor)
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if not stable:
            _abort("legacy_asset_companion_source_changed")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def read_legacy_asset_companion_v1(source_path: Any, source_asset_id: str) -> dict[str, Any]:
    try:
        return _projection_impl(_read_regular_file(source_path), source_asset_id)
    except LegacyAssetCompanionV1Error:
        raise
    except Exception:
        raise LegacyAssetCompanionV1Error("legacy_asset_companion_boundary_failed") from None


def _review_impl(projection: Any, review: Any) -> dict[str, Any]:
    if not isinstance(projection, dict) or not isinstance(review, dict):
        _abort("legacy_asset_companion_review_invalid")
    expected_projection_keys = {
        "account_binding_imported",
        "asset_companion_version",
        "canonical_write",
        "classification_hint_presence",
        "display_name_candidate",
        "field_disposition_counts",
        "grouping_allocation_imported",
        "optional_candidates",
        "private_output_logged",
        "projection_fingerprint",
        "projection_status",
        "provider_listing_field_count",
        "provider_listing_value_imported",
        "source_asset_link_fingerprint",
        "source_file_fingerprint",
        "source_header_fingerprint",
        "source_row_fingerprint",
        "tax_value_imported",
    }
    if set(projection) != expected_projection_keys or projection.get("projection_status") != "ready_for_review":
        _abort("legacy_asset_companion_review_invalid")
    body = dict(projection)
    supplied_projection_fingerprint = body.pop("projection_fingerprint", None)
    if supplied_projection_fingerprint != _fingerprint(body):
        _abort("legacy_asset_companion_review_stale")
    expected_review_keys = {
        "asset_companion_version",
        "projection_fingerprint",
        "source_asset_link_fingerprint",
        "display_name_action",
        "manual_display_name",
        "asset_type",
        "quantity_scale",
        "optional_field_actions",
    }
    if set(review) != expected_review_keys or review.get("asset_companion_version") != CONTRACT_VERSION:
        _abort("legacy_asset_companion_review_invalid")
    if (
        review.get("projection_fingerprint") != supplied_projection_fingerprint
        or review.get("source_asset_link_fingerprint") != projection.get("source_asset_link_fingerprint")
    ):
        _abort("legacy_asset_companion_review_stale")
    action = review.get("display_name_action")
    if action == "accept_candidate":
        if review.get("manual_display_name") is not None:
            _abort("legacy_asset_companion_review_invalid")
        display_name = _clean_display_name(projection.get("display_name_candidate"))
    elif action == "replace_manually":
        display_name = _clean_display_name(review.get("manual_display_name"))
    else:
        _abort("legacy_asset_companion_review_invalid")
    asset_type = review.get("asset_type")
    if asset_type not in ASSET_TYPES:
        _abort("legacy_asset_companion_asset_type_invalid")
    quantity_scale = review.get("quantity_scale")
    if isinstance(quantity_scale, bool) or not isinstance(quantity_scale, int) or not 0 <= quantity_scale <= 24:
        _abort("legacy_asset_companion_quantity_scale_invalid")
    actions = review.get("optional_field_actions")
    if not isinstance(actions, dict) or set(actions) != set(OPTIONAL_SOURCE_FIELDS):
        _abort("legacy_asset_companion_optional_field_invalid")
    candidates = projection.get("optional_candidates")
    if not isinstance(candidates, dict) or set(candidates) != set(OPTIONAL_SOURCE_FIELDS):
        _abort("legacy_asset_companion_review_invalid")
    accepted: dict[str, str | None] = {}
    for field in sorted(OPTIONAL_SOURCE_FIELDS):
        field_action = actions.get(field)
        if field_action == "skip":
            accepted[field] = None
            continue
        if field_action != "accept_candidate" or not isinstance(candidates.get(field), str):
            _abort("legacy_asset_companion_optional_field_invalid")
        value = str(candidates[field]).strip()
        if field == "isin":
            value = value.upper()
            if _ISIN.fullmatch(value) is None:
                _abort("legacy_asset_companion_optional_field_invalid")
        elif field == "wkn":
            value = value.upper()
            if _WKN.fullmatch(value) is None:
                _abort("legacy_asset_companion_optional_field_invalid")
        elif not value or len(value) > 4000 or any(ord(char) < 32 and char not in "\n\t" for char in value):
            _abort("legacy_asset_companion_optional_field_invalid")
        accepted[field] = value
    result = {
        "asset_companion_version": CONTRACT_VERSION,
        "review_status": "reviewed_candidate",
        "projection_fingerprint": supplied_projection_fingerprint,
        "source_asset_link_fingerprint": projection["source_asset_link_fingerprint"],
        "source_row_fingerprint": projection["source_row_fingerprint"],
        "display_name": display_name,
        "asset_type": asset_type,
        "quantity_scale": quantity_scale,
        "isin": accepted["isin"],
        "wkn": accepted["wkn"],
        "note": accepted["note"],
        "asset_type_inferred": False,
        "quantity_scale_inferred": False,
        "provider_listing_value_imported": False,
        "tax_value_imported": False,
        "account_binding_imported": False,
        "grouping_allocation_imported": False,
        "canonical_write": False,
        "private_output_logged": False,
    }
    result["review_fingerprint"] = _fingerprint(result)
    return result


def review_legacy_asset_companion_v1(projection: Any, review: Any) -> dict[str, Any]:
    try:
        return _review_impl(projection, review)
    except LegacyAssetCompanionV1Error:
        raise
    except Exception:
        raise LegacyAssetCompanionV1Error("legacy_asset_companion_boundary_failed") from None


__all__ = [
    "ASSET_TYPES",
    "FIELD_POLICIES",
    "LegacyAssetCompanionV1Error",
    "legacy_asset_companion_v1_error_codes",
    "project_legacy_asset_companion_bytes_v1",
    "read_legacy_asset_companion_v1",
    "review_legacy_asset_companion_v1",
]
