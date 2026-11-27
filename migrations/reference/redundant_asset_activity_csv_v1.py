"""Tolerant redundant Activity CSV and read-only Legacy format adapter.

The adapter reads only explicitly bound owner-local CSV sources and returns an
in-memory private CSV projection plus a redacted reconciliation report. It owns no
Product path, Context or canonical writer.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import ctypes
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import csv
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any, Mapping, Sequence
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CONTRACT_VERSION = 1
FORMAT_VERSION = "portelyra_redundant_asset_activity_csv_v1"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILES = 1000
MAX_ROWS = 20000
HEADERS = (
    "format_version", "row_kind", "row_key", "portfolio_key", "portfolio_name",
    "portfolio_currency", "account_key", "account_name", "account_type",
    "institution_name", "related_account_key", "related_account_name", "asset_key",
    "asset_name", "asset_type", "price_currency", "quantity_scale",
    "quantity_scale_origin", "valuation_method", "isin", "asset_note",
    "source_asset_key", "source_asset_name", "event_type", "event_time_evidence",
    "local_date", "local_time", "time_zone", "amount_input_mode",
    "basis_evidence_mode", "quantity_decimal", "eligible_quantity_decimal",
    "unit_price_decimal", "gross_amount_decimal", "monetary_fee_decimal",
    "asset_fee_quantity_decimal", "unclassified_fee_decimal",
    "provided_basis_decimal", "original_acquired_time_evidence",
    "original_acquired_local_date", "original_acquired_local_time",
    "original_acquired_time_zone", "movement_context_code", "source_reference",
    "source_note",
)
STRUCTURAL_HEADERS = frozenset({"format_version", "row_kind", "asset_key"})
DECIMAL_FIELDS = frozenset({
    "quantity_decimal", "eligible_quantity_decimal", "unit_price_decimal",
    "gross_amount_decimal", "monetary_fee_decimal", "asset_fee_quantity_decimal",
    "unclassified_fee_decimal", "provided_basis_decimal",
})
LEGACY_MASTER_HEADERS = (
    "Asset_ID", "Wertpapierbezeichnung", "Ist_Cash", "Kategorie", "Steuertyp",
    "Aktiv", "Notiz",
)
LEGACY_TRANSACTION_HEADERS = (
    "Asset_ID", "Depot", "Datum", "Uhrzeit", "Typ", "Stückzahl", "Stückpreis",
    "Ordergebühr", "Kommentar",
)
EVENT_TYPES = {
    "buy": "buy", "kauf": "buy", "sell": "sell", "verkauf": "sell",
    "dividend": "dividend", "dividende": "dividend",
    "stock_dividend": "stock_dividend", "aktiendividende": "stock_dividend",
    "reward": "reward", "deposit": "deposit", "einlieferung": "deposit",
    "withdrawal": "withdrawal", "auslieferung": "withdrawal",
    "transfer": "transfer",
}
ASSET_TYPES = {
    "aktien": "equity", "fonds": "fund", "derivate": "derivative",
    "derivative": "derivative", "krypto": "crypto", "kryptowährungen": "crypto",
    "edelmetalle": "commodity", "physische edelmetalle": "commodity",
    "rohstoffe": "commodity", "anleihen": "bond", "cash": "cash",
    "girokonto": "cash", "tagesgeld": "cash",
}
VALUATION_METHODS = frozenset({"external_market", "manual", "unit_value", "transaction_only"})
ACCOUNT_TYPES = frozenset({"securities", "crypto_wallet", "other"})
TRANSFER_SEPARATOR = re.compile(r"(?:→|->)")
DECIMAL_SOURCE = re.compile(r"^[+-]?[0-9]+(?:[.,][0-9]+)?(?:[eE][+-]?[0-9]+)?$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
BLOCKING_DIAGNOSTICS = frozenset({
    "legacy_activity_cash_excluded",
    "legacy_activity_inactive_source_asset",
    "legacy_activity_quantity_scale_exceeded",
})
WARNING_DIAGNOSTICS = frozenset({
    "legacy_activity_optional_isin_ignored",
})
FAILURE_CODES = frozenset({
    "redundant_activity_csv_boundary_invalid", "redundant_activity_csv_encoding_invalid",
    "redundant_activity_csv_header_invalid", "redundant_activity_csv_source_invalid",
    "redundant_activity_csv_source_limit_exceeded", "redundant_activity_csv_target_exists",
    "redundant_activity_csv_target_invalid",
})
DIAGNOSTIC_CODES = frozenset({
    "activity_quantity_scale_revision_required",
    "legacy_activity_account_type_input_required",
    "legacy_activity_asset_identity_ambiguous",
    "legacy_activity_asset_identity_missing",
    "legacy_activity_asset_identity_unknown",
    "legacy_activity_asset_type_input_required",
    "legacy_activity_asset_type_not_yet_supported",
    "legacy_activity_basis_input_required",
    "legacy_activity_cash_excluded",
    "legacy_activity_date_input_required",
    "legacy_activity_decimal_invalid",
    "legacy_activity_event_type_input_required",
    "legacy_activity_fee_role_input_required",
    "legacy_activity_inactive_source_asset",
    "legacy_activity_optional_isin_ignored",
    "legacy_activity_original_acquisition_input_required",
    "legacy_activity_price_currency_input_required",
    "legacy_activity_quantity_input_required",
    "legacy_activity_quantity_scale_exceeded",
    "legacy_activity_quantity_scale_input_required",
    "legacy_activity_source_asset_input_required",
    "legacy_activity_source_columns_ignored",
    "legacy_activity_time_input_required",
    "legacy_activity_transfer_input_required",
    "legacy_activity_unit_price_input_required",
    "legacy_activity_valuation_method_input_required",
    "redundant_activity_repeated_master_conflict",
    "redundant_activity_unknown_column_review",
})


class RedundantAssetActivityCsvV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("redundant_asset_activity_csv_error_unregistered")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LegacyActivityConversionOptionsV1:
    time_zone: str
    valuation_method: str | None = None
    default_account_type: str | None = None
    portfolio_key: str = ""
    portfolio_name: str = ""
    portfolio_currency: str = ""


@dataclass(frozen=True)
class RedundantActivityConversionResultV1:
    status: str
    rows: tuple[dict[str, str], ...]
    report: dict[str, Any]
    csv_content: bytes


def redundant_asset_activity_csv_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def redundant_asset_activity_csv_v1_diagnostic_codes() -> tuple[str, ...]:
    return tuple(sorted(DIAGNOSTIC_CODES))


def _abort(code: str) -> None:
    raise RedundantAssetActivityCsvV1Error(code)


def assess_quantity_scale_transition_v1(
    current_quantity_scale: int | None,
    required_quantity_scale: int | None,
) -> dict[str, Any]:
    """Assess exact scale evidence without rounding or speculative reserve."""
    if (
        (current_quantity_scale is not None and (
            isinstance(current_quantity_scale, bool)
            or not isinstance(current_quantity_scale, int)
            or not 0 <= current_quantity_scale <= 24
        ))
        or (required_quantity_scale is not None and (
            isinstance(required_quantity_scale, bool)
            or not isinstance(required_quantity_scale, int)
            or required_quantity_scale < 0
        ))
    ):
        _abort("redundant_activity_csv_source_invalid")
    common = {
        "quantity_scale_transition_version": 1,
        "current_quantity_scale": current_quantity_scale,
        "required_quantity_scale": required_quantity_scale,
        "rounding_performed": False,
    }
    if required_quantity_scale is None:
        return {
            **common,
            "status": "needs_input" if current_quantity_scale is None else "within_current_scale",
            "proposed_quantity_scale": current_quantity_scale,
            "diagnostic_codes": (
                ["legacy_activity_quantity_scale_input_required"]
                if current_quantity_scale is None
                else []
            ),
            "warning_required": False,
            "asset_revision_required": False,
            "fifo_rebuild_required": False,
        }
    if required_quantity_scale > 24:
        return {
            **common,
            "status": "blocked",
            "proposed_quantity_scale": None,
            "diagnostic_codes": ["legacy_activity_quantity_scale_exceeded"],
            "warning_required": True,
            "asset_revision_required": False,
            "fifo_rebuild_required": False,
        }
    if current_quantity_scale is None:
        return {
            **common,
            "status": "initial_scale_from_evidence",
            "proposed_quantity_scale": required_quantity_scale,
            "diagnostic_codes": [],
            "warning_required": False,
            "asset_revision_required": False,
            "fifo_rebuild_required": False,
        }
    if required_quantity_scale <= current_quantity_scale:
        return {
            **common,
            "status": "within_current_scale",
            "proposed_quantity_scale": current_quantity_scale,
            "diagnostic_codes": [],
            "warning_required": False,
            "asset_revision_required": False,
            "fifo_rebuild_required": False,
        }
    return {
        **common,
        "status": "quantity_scale_revision_required",
        "proposed_quantity_scale": required_quantity_scale,
        "diagnostic_codes": ["activity_quantity_scale_revision_required"],
        "warning_required": True,
        "asset_revision_required": True,
        "fifo_rebuild_required": True,
    }


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError):
        _abort("redundant_activity_csv_source_invalid")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_text(value: Any, *, maximum: int, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError
    result = unicodedata.normalize("NFC", value).strip()
    if (not result and not allow_empty) or len(result.encode("utf-8")) > maximum or CONTROL.search(result):
        raise ValueError
    return result


def _spreadsheet_safe(value: str) -> str:
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


def _safe_key(value: Any, fallback_material: Any) -> tuple[str, bool]:
    try:
        result = _safe_text(value, maximum=200)
    except ValueError:
        return "unresolved_" + _fingerprint(fallback_material)[:24], False
    if result.startswith(("=", "+", "-", "@")):
        return "unresolved_" + _fingerprint(fallback_material)[:24], False
    return result, True


def _no_symlink_components(path: Path) -> None:
    if not path.is_absolute():
        _abort("redundant_activity_csv_boundary_invalid")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if current.is_symlink():
                _abort("redundant_activity_csv_boundary_invalid")
        except OSError:
            _abort("redundant_activity_csv_boundary_invalid")


def _directory(path_value: str | Path) -> tuple[Path, tuple[int, int, int, int]]:
    path = Path(path_value)
    _no_symlink_components(path)
    try:
        metadata = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError:
        _abort("redundant_activity_csv_boundary_invalid")
    if resolved != path or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        _abort("redundant_activity_csv_boundary_invalid")
    return path, (metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns, metadata.st_ctime_ns)


def _directory_identity(path: Path) -> tuple[int, int, int, int]:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError:
        _abort("redundant_activity_csv_source_invalid")
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        _abort("redundant_activity_csv_source_invalid")
    return metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns, metadata.st_ctime_ns


def _read_file(path_value: str | Path) -> tuple[Path, bytes, tuple[int, int, int, int, int]]:
    path = Path(path_value)
    _no_symlink_components(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        _abort("redundant_activity_csv_source_invalid")
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or not 0 < before.st_size <= MAX_FILE_BYTES
        ):
            _abort("redundant_activity_csv_source_invalid")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                _abort("redundant_activity_csv_source_invalid")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _abort("redundant_activity_csv_source_invalid")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
    try:
        current = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError:
        _abort("redundant_activity_csv_source_invalid")
    if resolved != path or identity(before) != identity(after) or identity(before) != identity(current):
        _abort("redundant_activity_csv_source_invalid")
    return path, b"".join(chunks), identity(before)


def _transaction_files(root: Path) -> tuple[list[Path], list[tuple[Path, tuple[int, int, int, int]]]]:
    pending = [root]
    files: list[Path] = []
    directories: list[tuple[Path, tuple[int, int, int, int]]] = []
    while pending:
        directory = pending.pop()
        directories.append((directory, _directory_identity(directory)))
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.encode("utf-8"))
        except OSError:
            _abort("redundant_activity_csv_source_invalid")
        for entry in entries:
            try:
                if entry.is_symlink():
                    _abort("redundant_activity_csv_boundary_invalid")
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False) and entry.name.casefold().endswith(".csv"):
                    files.append(Path(entry.path))
            except OSError:
                _abort("redundant_activity_csv_source_invalid")
    if len(files) > MAX_FILES:
        _abort("redundant_activity_csv_source_limit_exceeded")
    return sorted(files, key=lambda path: path.relative_to(root).as_posix().encode("utf-8")), directories


def _decode(content: bytes) -> str:
    try:
        result = content.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        _abort("redundant_activity_csv_encoding_invalid")
    if "\x00" in result:
        _abort("redundant_activity_csv_encoding_invalid")
    return result


def _parse_table(content: bytes, required_headers: Sequence[str]) -> tuple[list[str], list[dict[str, str]]]:
    text = _decode(content)
    candidates: list[tuple[list[str], list[list[str]]]] = []
    for delimiter in (",", ";"):
        try:
            records = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True))
        except csv.Error:
            continue
        if not records:
            continue
        headers = [unicodedata.normalize("NFC", item).strip() for item in records[0]]
        if (
            not headers
            or any(not header for header in headers)
            or len(headers) != len(set(headers))
            or not set(required_headers).issubset(headers)
        ):
            continue
        candidates.append((headers, records[1:]))
    if len(candidates) != 1:
        _abort("redundant_activity_csv_header_invalid")
    headers, source_rows = candidates[0]
    rows: list[dict[str, str]] = []
    for source_row in source_rows:
        if not source_row or all(value == "" for value in source_row):
            continue
        if len(source_row) != len(headers):
            _abort("redundant_activity_csv_source_invalid")
        rows.append(dict(zip(headers, source_row, strict=True)))
    return headers, rows


def _decimal(value: Any, *, optional: bool) -> str | None:
    if not isinstance(value, str):
        raise ValueError
    source = unicodedata.normalize("NFC", value).strip()
    if source == "" and optional:
        return None
    if not source or len(source) > 120 or DECIMAL_SOURCE.fullmatch(source) is None:
        raise ValueError
    if "e" in source.casefold():
        try:
            exponent = int(re.split(r"[eE]", source, maxsplit=1)[1])
        except (IndexError, ValueError):
            raise ValueError from None
        if abs(exponent) > 80:
            raise ValueError
    try:
        number = Decimal(source.replace(",", "."))
    except InvalidOperation:
        raise ValueError from None
    if not number.is_finite():
        raise ValueError
    number = abs(number)
    if number == 0:
        return "0"
    result = format(number, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    if len(result.replace(".", "")) > 80:
        raise ValueError
    return result


def _scale(value: str | None) -> int:
    return 0 if value is None else len(value.partition(".")[2])


def _bool(value: Any) -> bool | None:
    try:
        source = _safe_text(value, maximum=20, allow_empty=True).casefold()
    except ValueError:
        return None
    if source == "true":
        return True
    if source == "false":
        return False
    return None


def _event_type(value: Any) -> str | None:
    try:
        key = _safe_text(value, maximum=80).casefold().replace("-", "_").replace(" ", "_")
    except ValueError:
        return None
    return EVENT_TYPES.get(key)


def _asset_type(category_value: Any, tax_value: Any) -> str | None:
    try:
        category = _safe_text(category_value, maximum=120, allow_empty=True).casefold()
        tax_type = _safe_text(tax_value, maximum=120, allow_empty=True).casefold()
    except ValueError:
        return None
    if category in ASSET_TYPES:
        return ASSET_TYPES[category]
    if tax_type == "aktien":
        return "equity"
    if tax_type == "fonds":
        return "fund"
    return None


def _currency(value: Any) -> tuple[str | None, bool]:
    if not isinstance(value, str):
        return None, False
    source = unicodedata.normalize("NFC", value).strip().upper()
    if not source:
        return None, True
    return (source, True) if CURRENCY.fullmatch(source) is not None else (None, False)


def _date(value: Any) -> str | None:
    try:
        source = _safe_text(value, maximum=10)
        parsed = datetime.strptime(source, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None
    return source if parsed.strftime("%Y-%m-%d") == source else None


def _time(value: Any) -> tuple[str | None, bool]:
    try:
        source = _safe_text(value, maximum=8, allow_empty=True)
    except ValueError:
        return None, False
    if not source:
        return None, True
    try:
        parsed = datetime.strptime(source, "%H:%M:%S")
    except ValueError:
        return None, False
    return (source, True) if parsed.strftime("%H:%M:%S") == source else (None, False)


def _transfer_expression(value: Any) -> tuple[str | None, str | None, str | None]:
    try:
        source = _safe_text(value, maximum=300)
    except ValueError:
        return None, None, None
    if source.count(":") != 1:
        return None, None, None
    prefix, expression = source.split(":", 1)
    endpoints = TRANSFER_SEPARATOR.split(expression)
    if len(endpoints) != 2 or len(TRANSFER_SEPARATOR.findall(expression)) != 1:
        return None, None, None
    try:
        first, second = (_safe_text(item, maximum=120) for item in endpoints)
    except ValueError:
        return None, None, None
    first_external = first.casefold() == "ext"
    second_external = second.casefold() == "ext"
    prefix = prefix.strip().upper()
    if prefix.endswith("_WECHSEL") and not first_external and not second_external and first != second:
        return "transfer", first, second
    if prefix.endswith("_ZUFLUSS") and first_external and not second_external:
        return "deposit", second, None
    if prefix.endswith("_ABFLUSS") and not first_external and second_external:
        return "withdrawal", first, None
    return None, None, None


def _standard_crypto_asset_fee(value: Any, event_type: str | None) -> bool:
    try:
        source = _safe_text(value, maximum=300)
    except ValueError:
        return False
    if source.count(":") != 1:
        return False
    parsed_event, source_account, related_account = _transfer_expression(source)
    if parsed_event != event_type or source_account is None or event_type == "transfer" and related_account is None:
        return False
    prefix = source.split(":", 1)[0].strip().upper()
    return (
        event_type == "transfer" and prefix == "KRYPTO_WECHSEL"
        or event_type == "withdrawal" and prefix == "KRYPTO_ABFLUSS"
    )


def _account_key(label: str) -> str:
    return "legacy_account_" + hashlib.sha256(label.encode("utf-8")).hexdigest()[:24]


def _empty_row() -> dict[str, str]:
    return {header: "" for header in HEADERS}


def _row_key(material: Any) -> str:
    return "row_" + _fingerprint(material)[:32]


def _source_ref(material: Any) -> str:
    return "lsr_" + _fingerprint(material)[:32]


def _disposition(diagnostics: set[str]) -> str:
    if diagnostics & BLOCKING_DIAGNOSTICS:
        return "blocked"
    if diagnostics - WARNING_DIAGNOSTICS:
        return "needs_input"
    return "ready"


def _conversion_options(value: Any) -> LegacyActivityConversionOptionsV1:
    if not isinstance(value, LegacyActivityConversionOptionsV1):
        _abort("redundant_activity_csv_source_invalid")
    try:
        ZoneInfo(value.time_zone)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        _abort("redundant_activity_csv_source_invalid")
    if value.valuation_method is not None and value.valuation_method not in VALUATION_METHODS:
        _abort("redundant_activity_csv_source_invalid")
    if value.default_account_type is not None and value.default_account_type not in ACCOUNT_TYPES:
        _abort("redundant_activity_csv_source_invalid")
    for text, maximum in (
        (value.portfolio_key, 200), (value.portfolio_name, 120), (value.portfolio_currency, 3)
    ):
        try:
            _safe_text(text, maximum=maximum, allow_empty=True)
        except ValueError:
            _abort("redundant_activity_csv_source_invalid")
    if value.portfolio_currency and CURRENCY.fullmatch(value.portfolio_currency) is None:
        _abort("redundant_activity_csv_source_invalid")
    return value


def _render_rows(rows: Sequence[Mapping[str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    for row in rows:
        if set(row) != set(HEADERS) or not all(isinstance(value, str) for value in row.values()):
            _abort("redundant_activity_csv_source_invalid")
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


def _master_candidate(
    source_id: str,
    master_records: Sequence[Mapping[str, str]],
    transaction_records: Sequence[Mapping[str, Any]],
    options: LegacyActivityConversionOptionsV1,
) -> tuple[dict[str, str], set[str]]:
    diagnostics: set[str] = set()
    if len(master_records) != 1:
        if master_records:
            diagnostics.add("legacy_activity_asset_identity_ambiguous")
        return {
            "asset_key": source_id,
            "asset_name": "", "asset_type": "", "price_currency": "",
            "quantity_scale": "", "quantity_scale_origin": "unresolved",
            "valuation_method": options.valuation_method or "", "isin": "", "asset_note": "",
        }, diagnostics
    master = master_records[0]
    try:
        preferred_name = _safe_text(master.get("Wertpapierbezeichnung", ""), maximum=160, allow_empty=True)
        fallback_name = _safe_text(master.get("Asset", ""), maximum=160, allow_empty=True)
    except ValueError:
        preferred_name = fallback_name = ""
    asset_name = preferred_name or fallback_name
    if not asset_name:
        diagnostics.add("legacy_activity_asset_identity_missing")
    asset_type = _asset_type(master.get("Kategorie", ""), master.get("Steuertyp", ""))
    if asset_type is None:
        diagnostics.add("legacy_activity_asset_type_input_required")
    elif asset_type == "derivative":
        diagnostics.add("legacy_activity_asset_type_not_yet_supported")
    cash = _bool(master.get("Ist_Cash", ""))
    if cash is True or asset_type == "cash":
        diagnostics.add("legacy_activity_cash_excluded")
    active = _bool(master.get("Aktiv", ""))
    if active is not True:
        diagnostics.add("legacy_activity_inactive_source_asset")

    direct, direct_valid = _currency(master.get("Price_Currency", ""))
    transaction_currencies: set[str] = set()
    transaction_currency_invalid = False
    for item in transaction_records:
        raw = item["values"].get("Währung", "")
        candidate, valid = _currency(raw)
        if raw.strip() and not valid:
            transaction_currency_invalid = True
        if candidate is not None:
            transaction_currencies.add(candidate)
    fallback_currencies: set[str] = set()
    fallback_invalid = False
    for field in ("Kurs_Währung", "Währung"):
        raw = master.get(field, "")
        candidate, valid = _currency(raw)
        if isinstance(raw, str) and raw.strip() and not valid:
            fallback_invalid = True
        if candidate is not None:
            fallback_currencies.add(candidate)
    price_currency = ""
    direct_raw = master.get("Price_Currency", "")
    if isinstance(direct_raw, str) and direct_raw.strip():
        if direct_valid and direct is not None and not transaction_currency_invalid and (
            not transaction_currencies or transaction_currencies == {direct}
        ):
            price_currency = direct
        else:
            diagnostics.add("legacy_activity_price_currency_input_required")
    else:
        candidates = transaction_currencies | fallback_currencies
        if not transaction_currency_invalid and not fallback_invalid and len(candidates) == 1:
            price_currency = next(iter(candidates))
        else:
            diagnostics.add("legacy_activity_price_currency_input_required")

    scales: list[int] = []
    for item in transaction_records:
        values = item["values"]
        try:
            quantity = _decimal(values.get("Stückzahl", ""), optional=False)
            if quantity != "0":
                scales.append(_scale(quantity))
        except ValueError:
            pass
        event = _event_type(values.get("Typ", ""))
        if event not in {None, "buy", "sell"}:
            try:
                possible_asset_fee = _decimal(values.get("Ordergebühr", ""), optional=True)
                if possible_asset_fee not in {None, "0"}:
                    scales.append(_scale(possible_asset_fee))
            except ValueError:
                pass
    quantity_scale = ""
    quantity_scale_origin = "unresolved"
    scale_transition = assess_quantity_scale_transition_v1(
        None,
        max(scales) if scales else None,
    )
    diagnostics.update(scale_transition["diagnostic_codes"])
    if scale_transition["proposed_quantity_scale"] is not None:
        quantity_scale = str(scale_transition["proposed_quantity_scale"])
        quantity_scale_origin = "observed_exact"

    valuation_method = options.valuation_method or ""
    if not valuation_method:
        diagnostics.add("legacy_activity_valuation_method_input_required")

    raw_isin = master.get("ISIN", "")
    isin = ""
    if isinstance(raw_isin, str) and raw_isin.strip():
        candidate = unicodedata.normalize("NFC", raw_isin).strip().upper()
        if re.fullmatch(r"[A-Z0-9]{12}", candidate) is not None:
            isin = candidate
        else:
            diagnostics.add("legacy_activity_optional_isin_ignored")
    try:
        asset_note = _spreadsheet_safe(_safe_text(master.get("Notiz", ""), maximum=4000, allow_empty=True))
    except ValueError:
        asset_note = ""
    return {
        "asset_key": source_id,
        "asset_name": _spreadsheet_safe(asset_name),
        "asset_type": asset_type or "",
        "price_currency": price_currency,
        "quantity_scale": quantity_scale,
        "quantity_scale_origin": quantity_scale_origin,
        "valuation_method": valuation_method,
        "isin": isin,
        "asset_note": asset_note,
    }, diagnostics


def _base_row(
    row_kind: str,
    row_key: str,
    source_reference: str,
    master: Mapping[str, str],
    options: LegacyActivityConversionOptionsV1,
) -> dict[str, str]:
    row = _empty_row()
    row.update({
        "format_version": FORMAT_VERSION,
        "row_kind": row_kind,
        "row_key": row_key,
        "portfolio_key": options.portfolio_key,
        "portfolio_name": _spreadsheet_safe(options.portfolio_name),
        "portfolio_currency": options.portfolio_currency,
        "asset_key": master["asset_key"],
        "asset_name": master["asset_name"],
        "asset_type": master["asset_type"],
        "price_currency": master["price_currency"],
        "quantity_scale": master["quantity_scale"],
        "quantity_scale_origin": master["quantity_scale_origin"],
        "valuation_method": master["valuation_method"],
        "isin": master["isin"],
        "asset_note": master["asset_note"],
        "source_reference": source_reference,
    })
    return row


def _activity_row(
    item: Mapping[str, Any],
    master: Mapping[str, str],
    master_diagnostics: set[str],
    options: LegacyActivityConversionOptionsV1,
) -> tuple[dict[str, str], set[str]]:
    values = item["values"]
    diagnostics = set(master_diagnostics)
    source_reference = item["source_reference"]
    row = _base_row("activity", item["row_key"], source_reference, master, options)
    event = _event_type(values.get("Typ", ""))
    account_name: str | None = None
    related_account_name: str | None = None
    if event == "transfer":
        event, account_name, related_account_name = _transfer_expression(values.get("Depot", ""))
        if event is None or account_name is None:
            diagnostics.add("legacy_activity_transfer_input_required")
            event = ""
    else:
        try:
            account_name = _safe_text(values.get("Depot", ""), maximum=120)
        except ValueError:
            account_name = None
    if _event_type(values.get("Typ", "")) is None:
        diagnostics.add("legacy_activity_event_type_input_required")
    if account_name is None:
        diagnostics.add("legacy_activity_account_type_input_required")
    else:
        row["account_key"] = _account_key(account_name)
        row["account_name"] = _spreadsheet_safe(account_name)
        row["account_type"] = options.default_account_type or ""
        if options.default_account_type is None:
            diagnostics.add("legacy_activity_account_type_input_required")
    if related_account_name is not None:
        row["related_account_key"] = _account_key(related_account_name)
        row["related_account_name"] = _spreadsheet_safe(related_account_name)
    elif event == "transfer":
        diagnostics.add("legacy_activity_transfer_input_required")

    local_date = _date(values.get("Datum", ""))
    if local_date is None:
        diagnostics.add("legacy_activity_date_input_required")
    local_time, time_valid = _time(values.get("Uhrzeit", ""))
    if not time_valid:
        diagnostics.add("legacy_activity_time_input_required")
    row.update({
        "event_type": event or "",
        "event_time_evidence": "exact" if local_time is not None else "date_only",
        "local_date": local_date or "",
        "local_time": local_time or "",
        "time_zone": options.time_zone,
    })
    if event is not None and event != "deposit":
        row["original_acquired_time_evidence"] = "not_applicable"
    if event is not None and event not in {"deposit", "withdrawal"}:
        row["movement_context_code"] = "not_applicable"

    try:
        quantity = _decimal(values.get("Stückzahl", ""), optional=False)
    except ValueError:
        quantity = None
        diagnostics.add("legacy_activity_decimal_invalid")
    if quantity in {None, "0"}:
        diagnostics.add("legacy_activity_quantity_input_required")
        quantity = None
    try:
        unit_price = _decimal(values.get("Stückpreis", ""), optional=True)
    except ValueError:
        unit_price = None
        diagnostics.add("legacy_activity_decimal_invalid")
    try:
        fee = _decimal(values.get("Ordergebühr", ""), optional=True)
    except ValueError:
        fee = None
        diagnostics.add("legacy_activity_decimal_invalid")
    if unit_price == "0":
        unit_price = None
    if fee == "0":
        fee = None

    if event in {"buy", "sell"}:
        row["amount_input_mode"] = "quantity_unit_price"
        row["basis_evidence_mode"] = "derived_trade" if event == "buy" else "not_applicable"
        row["quantity_decimal"] = quantity or ""
        row["unit_price_decimal"] = unit_price or ""
        row["monetary_fee_decimal"] = fee or ""
        if unit_price is None:
            diagnostics.add("legacy_activity_unit_price_input_required")
    elif event == "dividend":
        row["amount_input_mode"] = "quantity_unit_price"
        row["basis_evidence_mode"] = "not_applicable"
        row["eligible_quantity_decimal"] = quantity or ""
        row["unit_price_decimal"] = unit_price or ""
        if unit_price is None:
            diagnostics.add("legacy_activity_unit_price_input_required")
        if fee is not None:
            row["unclassified_fee_decimal"] = fee
            diagnostics.add("legacy_activity_fee_role_input_required")
    elif event in {"reward", "stock_dividend"}:
        row["amount_input_mode"] = "quantity_unit_price"
        row["basis_evidence_mode"] = "basis_missing"
        row["quantity_decimal"] = quantity or ""
        row["unit_price_decimal"] = unit_price or ""
        diagnostics.add("legacy_activity_basis_input_required")
        if unit_price is None:
            diagnostics.add("legacy_activity_unit_price_input_required")
        if event == "stock_dividend":
            diagnostics.add("legacy_activity_source_asset_input_required")
        if fee is not None:
            row["unclassified_fee_decimal"] = fee
            diagnostics.add("legacy_activity_fee_role_input_required")
    elif event == "deposit":
        row["amount_input_mode"] = "quantity_unit_price" if unit_price is not None else "not_applicable"
        row["basis_evidence_mode"] = "basis_missing"
        row["quantity_decimal"] = quantity or ""
        row["unit_price_decimal"] = unit_price or ""
        row["original_acquired_time_evidence"] = ""
        row["movement_context_code"] = "unclassified"
        diagnostics.update({
            "legacy_activity_basis_input_required",
            "legacy_activity_original_acquisition_input_required",
        })
        if fee is not None:
            row["unclassified_fee_decimal"] = fee
            diagnostics.add("legacy_activity_fee_role_input_required")
    elif event == "withdrawal":
        row["amount_input_mode"] = "not_applicable"
        row["basis_evidence_mode"] = "not_applicable"
        row["quantity_decimal"] = quantity or ""
        row["original_acquired_time_evidence"] = "not_applicable"
        row["movement_context_code"] = "unclassified"
        if fee is not None:
            if _standard_crypto_asset_fee(values.get("Depot", ""), event) and Decimal(fee) > 0:
                row["asset_fee_quantity_decimal"] = fee
            else:
                row["unclassified_fee_decimal"] = fee
                diagnostics.add("legacy_activity_fee_role_input_required")
    elif event == "transfer":
        row["amount_input_mode"] = "not_applicable"
        row["basis_evidence_mode"] = "not_applicable"
        row["quantity_decimal"] = quantity or ""
        row["original_acquired_time_evidence"] = "not_applicable"
        row["movement_context_code"] = "not_applicable"
        if fee is not None:
            if _standard_crypto_asset_fee(values.get("Depot", ""), event) and Decimal(fee) > 0:
                row["asset_fee_quantity_decimal"] = fee
            else:
                row["unclassified_fee_decimal"] = fee
                diagnostics.add("legacy_activity_fee_role_input_required")
    else:
        row["quantity_decimal"] = quantity or ""

    if row["quantity_decimal"] and _scale(row["quantity_decimal"]) > 24:
        diagnostics.add("legacy_activity_quantity_scale_exceeded")
    if row["eligible_quantity_decimal"] and _scale(row["eligible_quantity_decimal"]) > 24:
        diagnostics.add("legacy_activity_quantity_scale_exceeded")
    try:
        row["source_note"] = _spreadsheet_safe(
            _safe_text(values.get("Kommentar", ""), maximum=4000, allow_empty=True)
        )
    except ValueError:
        row["source_note"] = ""
    return row, diagnostics


def convert_legacy_redundant_activity_csv_v1(
    asset_master_path: str | Path,
    transaction_root_path: str | Path,
    options_value: LegacyActivityConversionOptionsV1,
) -> RedundantActivityConversionResultV1:
    """Convert explicit Legacy sources in memory without writing either source or Product."""
    options = _conversion_options(options_value)
    _, master_content, master_identity = _read_file(asset_master_path)
    transaction_root, transaction_root_identity = _directory(transaction_root_path)
    transaction_paths, directory_identities = _transaction_files(transaction_root)
    total_bytes = len(master_content)
    transaction_sources: list[dict[str, Any]] = []
    transaction_file_identities: list[tuple[Path, tuple[int, int, int, int, int]]] = []
    source_set_material: list[dict[str, Any]] = []
    source_row_count = 0
    known_transaction_headers = set(LEGACY_TRANSACTION_HEADERS) | {
        "Asset", "Nettopreis", "Währung", "Spekulationsfrist", "Steuersatz",
        "Assetklasse", "Teilfreistellung", "Wertpapierbezeichnung", "Kursanbieter",
        "ISIN", "Kurs_Symbol", "Price_Symbol", "Kurs_Währung", "Price_Currency",
        "Fundamentals_Symbol",
    }
    source_diagnostics: set[str] = set()
    for path in transaction_paths:
        _, content, identity = _read_file(path)
        transaction_file_identities.append((path, identity))
        total_bytes += len(content)
        if total_bytes > MAX_TOTAL_BYTES:
            _abort("redundant_activity_csv_source_limit_exceeded")
        headers, records = _parse_table(content, LEGACY_TRANSACTION_HEADERS)
        if set(headers) - known_transaction_headers:
            source_diagnostics.add("legacy_activity_source_columns_ignored")
        source_row_count += len(records)
        if source_row_count > MAX_ROWS:
            _abort("redundant_activity_csv_source_limit_exceeded")
        file_fingerprint = _sha(content)
        relative_fingerprint = _sha(path.relative_to(transaction_root).as_posix().encode("utf-8"))
        source_set_material.append({
            "relative_fingerprint": relative_fingerprint,
            "content_fingerprint": file_fingerprint,
            "row_count": len(records),
        })
        for ordinal, values in enumerate(records, 1):
            source_reference = _source_ref({
                "file": file_fingerprint, "ordinal": ordinal, "row": values,
            })
            transaction_sources.append({
                "values": values,
                "source_reference": source_reference,
                "row_key": _row_key({"source_reference": source_reference, "row": values}),
                "file_identity": identity,
            })
    master_headers, master_rows = _parse_table(master_content, LEGACY_MASTER_HEADERS)
    known_master_headers = set(LEGACY_MASTER_HEADERS) | {
        "Asset", "ISIN", "Währung", "Steuersatz", "Teilfreistellung", "Kurs_Symbol",
        "Kurs_Währung", "Price_Currency", "Kurs_Provider", "Daily_Kurs_Provider",
        "Daily_Kurs_Währung", "Daily_Fallback_Chain", "Realtime_Kurs_Provider",
        "Realtime_Kurs_Währung", "Realtime_Fallback_Chain", "Provider_Modell_Status",
        "Kurs_Exchange", "Kurs_MIC_Code", "Kurs_Instrument_Type",
        "Kurs_Provider_Symbol", "Kurs_Mapping_Status", "Kurs_Mapping_Method",
        "Kurs_Mapping_Provider", "Kurs_Mapping_Verified_At",
        "Kurs_Mapping_Source_Endpoint", "Kurs_Fallback_Chain", "Yahoo_Symbol_Alt",
        "Yahoo_Exchange_Alt", "Yahoo_Quote_Type_Alt", "TD_Symbol", "TD_Exchange",
        "TD_MIC_Code", "TD_Instrument_Type", "TD_Currency", "TD_Request_Symbol",
        "Fundamentals_Symbol", "Default_Depot", "Allokationsgruppe",
    }
    if set(master_headers) - known_master_headers:
        source_diagnostics.add("legacy_activity_source_columns_ignored")
    if not master_rows:
        _abort("redundant_activity_csv_source_invalid")
    if len(master_rows) + source_row_count > MAX_ROWS:
        _abort("redundant_activity_csv_source_limit_exceeded")

    master_by_id: dict[str, list[dict[str, str]]] = defaultdict(list)
    folded_ids: dict[str, set[str]] = defaultdict(set)
    for ordinal, record in enumerate(master_rows, 1):
        key, exact = _safe_key(record.get("Asset_ID", ""), {"master_ordinal": ordinal, "record": record})
        master_by_id[key].append(record)
        folded_ids[key.casefold()].add(key)
        if not exact:
            source_diagnostics.add("legacy_activity_asset_identity_missing")
    for keys in folded_ids.values():
        if len(keys) > 1:
            for key in keys:
                if len(master_by_id[key]) == 1:
                    master_by_id[key].append(master_by_id[key][0])

    transactions_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in transaction_sources:
        key, exact = _safe_key(
            item["values"].get("Asset_ID", ""),
            {"source_reference": item["source_reference"]},
        )
        item["source_asset_key"] = key
        item["source_asset_key_exact"] = exact
        transactions_by_id[key].append(item)

    master_cache: dict[str, tuple[dict[str, str], set[str]]] = {}
    all_keys = set(master_by_id) | set(transactions_by_id)
    for key in all_keys:
        records = master_by_id.get(key, [])
        candidate, diagnostics = _master_candidate(key, records, transactions_by_id.get(key, []), options)
        if not records:
            diagnostics.add("legacy_activity_asset_identity_unknown")
        if any(not item.get("source_asset_key_exact", True) for item in transactions_by_id.get(key, [])):
            diagnostics.add("legacy_activity_asset_identity_missing")
        master_cache[key] = candidate, diagnostics

    output_rows: list[dict[str, str]] = []
    report_rows: list[dict[str, Any]] = []
    for item in transaction_sources:
        key = item["source_asset_key"]
        master, master_diagnostics = master_cache[key]
        row, diagnostics = _activity_row(item, master, master_diagnostics, options)
        disposition = _disposition(diagnostics)
        output_rows.append(row)
        report_rows.append({
            "row_key": row["row_key"],
            "source_reference": row["source_reference"],
            "row_kind": "activity",
            "disposition": disposition,
            "diagnostic_codes": sorted(diagnostics),
        })

    asset_only_count = 0
    asset_only_keys = sorted(
        set(master_by_id) - set(transactions_by_id),
        key=lambda value: value.encode("utf-8"),
    )
    for ordinal, key in enumerate(asset_only_keys, 1):
        master, diagnostics = master_cache[key]
        source_reference = _source_ref({"master": _sha(master_content), "key": key, "ordinal": ordinal})
        row_key = _row_key({"source_reference": source_reference, "kind": "asset"})
        row = _base_row("asset", row_key, source_reference, master, options)
        disposition = _disposition(diagnostics)
        output_rows.append(row)
        report_rows.append({
            "row_key": row_key,
            "source_reference": source_reference,
            "row_kind": "asset",
            "disposition": disposition,
            "diagnostic_codes": sorted(diagnostics),
        })
        asset_only_count += 1

    csv_content = _render_rows(output_rows)
    counts = Counter(row["disposition"] for row in report_rows)
    status = "blocked" if counts["blocked"] else "needs_input" if counts["needs_input"] else "ready"
    report: dict[str, Any] = {
        "conversion_report_version": 1,
        "status": status,
        "source_master_fingerprint": _sha(master_content),
        "source_transaction_set_fingerprint": _fingerprint(source_set_material),
        "output_content_fingerprint": _sha(csv_content),
        "source_file_count": 1 + len(transaction_paths),
        "source_asset_row_count": len(master_rows),
        "source_transaction_row_count": source_row_count,
        "output_row_count": len(output_rows),
        "asset_only_row_count": asset_only_count,
        "activity_row_count": len(transaction_sources),
        "ready_row_count": counts["ready"],
        "needs_input_row_count": counts["needs_input"],
        "blocked_row_count": counts["blocked"],
        "diagnostic_codes": sorted(source_diagnostics),
        "rows": report_rows,
        "source_read_only": True,
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "paths_exposed": False,
        "raw_values_exposed": False,
    }
    report["report_fingerprint"] = _fingerprint(report)

    _, _, master_after = _read_file(asset_master_path)
    if master_after != master_identity:
        _abort("redundant_activity_csv_source_invalid")
    if _directory_identity(transaction_root) != transaction_root_identity:
        _abort("redundant_activity_csv_source_invalid")
    for path, identity in transaction_file_identities:
        _, _, current_identity = _read_file(path)
        if current_identity != identity:
            _abort("redundant_activity_csv_source_invalid")
    for directory, identity in directory_identities:
        if _directory_identity(directory) != identity:
            _abort("redundant_activity_csv_source_invalid")
    return RedundantActivityConversionResultV1(status, tuple(output_rows), report, csv_content)


def _write_private_file(path: Path, content: bytes) -> None:
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(path, 0o600)
    except OSError:
        _abort("redundant_activity_csv_target_invalid")


def _rename_noreplace(source: Path, destination: Path) -> None:
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        _abort("redundant_activity_csv_target_invalid")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1) == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        _abort("redundant_activity_csv_target_exists")
    _abort("redundant_activity_csv_target_invalid")


def publish_redundant_activity_conversion_v1(
    result: RedundantActivityConversionResultV1,
    target_path: str | Path,
) -> dict[str, Any]:
    """Publish one owner-only conversion bundle atomically without replacement."""
    if not isinstance(result, RedundantActivityConversionResultV1):
        _abort("redundant_activity_csv_target_invalid")
    target = Path(target_path)
    if not target.is_absolute() or target.name in {"", ".", ".."}:
        _abort("redundant_activity_csv_target_invalid")
    parent, _ = _directory(target.parent)
    try:
        parent_mode = stat.S_IMODE(parent.stat(follow_symlinks=False).st_mode)
        target_exists = target.exists() or target.is_symlink()
    except OSError:
        _abort("redundant_activity_csv_target_invalid")
    if parent_mode & 0o077:
        _abort("redundant_activity_csv_target_invalid")
    if target_exists:
        _abort("redundant_activity_csv_target_exists")
    if _render_rows(result.rows) != result.csv_content:
        _abort("redundant_activity_csv_target_invalid")
    report = dict(result.report)
    report_fingerprint = report.pop("report_fingerprint", None)
    if (
        report_fingerprint != _fingerprint(report)
        or result.report.get("output_content_fingerprint") != _sha(result.csv_content)
        or result.report.get("status") != result.status
    ):
        _abort("redundant_activity_csv_target_invalid")
    stage = Path(tempfile.mkdtemp(prefix=".activity-conversion-", dir=parent))
    os.chmod(stage, 0o700)
    try:
        _write_private_file(stage / "portelyra-activity.csv", result.csv_content)
        _write_private_file(stage / "conversion-report.json", _canonical(result.report) + b"\n")
        directory_descriptor = os.open(stage, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
        _rename_noreplace(stage, target)
        parent_descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        stage = Path()
    finally:
        if stage != Path() and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
    try:
        target_metadata = target.stat(follow_symlinks=False)
    except OSError:
        _abort("redundant_activity_csv_target_invalid")
    if (
        target.is_symlink()
        or not stat.S_ISDIR(target_metadata.st_mode)
        or stat.S_IMODE(target_metadata.st_mode) != 0o700
    ):
        _abort("redundant_activity_csv_target_invalid")
    for name in ("portelyra-activity.csv", "conversion-report.json"):
        path = target / name
        try:
            metadata = path.stat(follow_symlinks=False)
        except OSError:
            _abort("redundant_activity_csv_target_invalid")
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
            _abort("redundant_activity_csv_target_invalid")
    return {
        "status": result.status,
        "output_row_count": result.report["output_row_count"],
        "ready_row_count": result.report["ready_row_count"],
        "needs_input_row_count": result.report["needs_input_row_count"],
        "blocked_row_count": result.report["blocked_row_count"],
        "source_read_only": True,
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "paths_exposed": False,
        "raw_values_exposed": False,
    }


def inspect_redundant_activity_csv_v1(source_path: str | Path) -> dict[str, Any]:
    """Inspect a tolerant Portelyra file without exposing its private row values."""
    _, content, _ = _read_file(source_path)
    headers, source_rows = _parse_table(content, tuple(STRUCTURAL_HEADERS))
    if not source_rows:
        _abort("redundant_activity_csv_source_invalid")
    unknown = sorted(set(headers) - set(HEADERS))
    report_rows: list[dict[str, Any]] = []
    trusted_rows: list[dict[str, str]] = []
    for ordinal, source in enumerate(source_rows, 1):
        normalized = _empty_row()
        for header in set(headers) & set(HEADERS):
            normalized[header] = source[header]
        if not normalized["row_key"]:
            normalized["row_key"] = _row_key({"content": _sha(content), "ordinal": ordinal})
        diagnostics: set[str] = set()
        for field in DECIMAL_FIELDS:
            try:
                normalized[field] = _decimal(normalized[field], optional=True) or ""
            except ValueError:
                normalized[field] = ""
                diagnostics.add("legacy_activity_decimal_invalid")
        if normalized["quantity_scale"]:
            if not re.fullmatch(r"(?:0|[1-9]|1[0-9]|2[0-4])", normalized["quantity_scale"]):
                normalized["quantity_scale"] = ""
                diagnostics.add("legacy_activity_quantity_scale_input_required")
        try:
            normalized["asset_key"] = _safe_text(normalized["asset_key"], maximum=200)
        except ValueError:
            normalized["asset_key"] = ""
            diagnostics.add("legacy_activity_asset_identity_missing")
        if normalized["format_version"] != FORMAT_VERSION:
            diagnostics.add("redundant_activity_csv_header_invalid")
        if normalized["row_kind"] not in {"asset", "activity"}:
            diagnostics.add("redundant_activity_csv_header_invalid")
        if not normalized["asset_key"].strip():
            diagnostics.add("legacy_activity_asset_identity_missing")
        if unknown:
            diagnostics.add("redundant_activity_unknown_column_review")
        disposition = (
            "blocked"
            if "redundant_activity_csv_header_invalid" in diagnostics
            else _disposition(diagnostics)
        )
        trusted_rows.append(normalized)
        report_rows.append({
            "row_ref": "inspect_" + _fingerprint({"content": _sha(content), "ordinal": ordinal})[:24],
            "row_kind": normalized["row_kind"] if normalized["row_kind"] in {"asset", "activity"} else "unknown",
            "disposition": disposition,
            "diagnostic_codes": sorted(diagnostics),
        })
    counts = Counter(row["disposition"] for row in report_rows)
    return {
        "public_inspection": {
            "redundant_activity_csv_inspection_version": 1,
            "status": "blocked" if counts["blocked"] else "needs_input" if counts["needs_input"] else "ready",
            "row_count": len(report_rows),
            "ready_row_count": counts["ready"],
            "needs_input_row_count": counts["needs_input"],
            "blocked_row_count": counts["blocked"],
            "unknown_column_count": len(unknown),
            "rows": report_rows,
            "canonical_write": False,
            "provider_access": False,
            "network_access": False,
            "paths_exposed": False,
            "raw_values_exposed": False,
        },
        "trusted_rows": trusted_rows,
        "source_fingerprint": _sha(content),
    }


__all__ = [
    "FORMAT_VERSION", "HEADERS", "LegacyActivityConversionOptionsV1",
    "assess_quantity_scale_transition_v1",
    "RedundantActivityConversionResultV1", "RedundantAssetActivityCsvV1Error",
    "convert_legacy_redundant_activity_csv_v1", "inspect_redundant_activity_csv_v1",
    "publish_redundant_activity_conversion_v1",
    "redundant_asset_activity_csv_v1_diagnostic_codes",
    "redundant_asset_activity_csv_v1_error_codes",
]
