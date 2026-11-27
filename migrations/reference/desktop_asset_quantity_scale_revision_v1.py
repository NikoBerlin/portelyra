"""ADR-135 owner-local Asset quantity-scale increase and generation recovery."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import tempfile
from typing import Any, Mapping

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference.desktop_asset_activity_correction_v1 import (
    DesktopAssetActivityCorrectionV1Error,
    _fifo_worlds,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    ACTIVE_NAME,
    LEDGER_NAME,
    MANIFEST_NAME,
    PRODUCT_AREA,
    SUCCESS_NAME,
    DesktopProductAssetActivityContextV1,
    DesktopProductAssetActivityV1Error,
    _CanonicalReadBarrierV1,
    _ProductWriterLockV1,
    _activity_rows,
    _atomic_json_replace,
    _canonical_snapshot,
    _context,
    _context_fingerprint,
    _owner_directory,
    _owner_file,
    _read_connection,
    _remove_staging_generations,
    _sha_file,
    _write_new_file,
    materialize_desktop_product_semantic_ledger_v1,
    read_desktop_product_asset_activity_binding_v1,
)

CONTRACT_VERSION = 1
ATTEMPT_AREA = "quantity-scale-revision-attempts"
NO_GENERATION_RECEIPT_AREA = "quantity-scale-revision-receipts"
RECEIPT_NAME = "asset-quantity-scale-revision-receipt.json"
ATTEMPT_SUFFIX = ".json"
CHALLENGE = re.compile(r"^aqs_[a-f0-9]{16,64}$")
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
DECIMAL_SOURCE = re.compile(r"^[+-]?[0-9]+(?:[.,][0-9]+)?(?:[eE][+-]?[0-9]+)?$")
QUANTITY_FIELDS = ("quantity_decimal", "eligible_quantity_decimal", "asset_fee_quantity_decimal")
HEX64 = re.compile(r"^[a-f0-9]{64}$")
TRUSTED_PREVIEW_KEYS = frozenset({
    "asset_quantity_scale_preview_version",
    "status",
    "context_fingerprint",
    "source_canonical_fingerprint",
    "source_generation_ref",
    "source_activity_set_fingerprint",
    "asset_id",
    "asset_label",
    "asset_stable_fingerprint",
    "expected_catalog_revision",
    "current_quantity_scale",
    "required_quantity_scale",
    "proposed_quantity_scale",
    "quantity_evidence_fingerprint",
    "prospective_fifo_world_result_fingerprints",
    "affected_fifo_world_count",
    "previewed_at_utc",
    "confirmation_required",
    "catalog_write",
    "activity_fact_write",
    "rounding_performed",
    "provider_access",
    "network_access",
    "plan_fingerprint",
})
FAILPOINTS = frozenset({
    None,
    "after_attempt",
    "after_generation_complete",
    "after_generation_publish",
    "before_active_replace",
    "after_active_replace",
})
FAILURE_CODES = frozenset({
    "asset_quantity_scale_attempt_conflict",
    "asset_quantity_scale_boundary_failed",
    "asset_quantity_scale_catalog_conflict",
    "asset_quantity_scale_confirmation_expired",
    "asset_quantity_scale_confirmation_invalid",
    "asset_quantity_scale_context_invalid",
    "asset_quantity_scale_fifo_invalid",
    "asset_quantity_scale_generation_conflict",
    "asset_quantity_scale_input_invalid",
    "asset_quantity_scale_no_increase",
    "asset_quantity_scale_preview_stale",
    "asset_quantity_scale_publication_failed",
    "asset_quantity_scale_receipt_invalid",
    "asset_quantity_scale_required_exceeds_limit",
    "asset_quantity_scale_storage_invalid",
    "synthetic_asset_quantity_scale_failpoint",
})


class DesktopAssetQuantityScaleRevisionV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("asset_quantity_scale_error_code_unregistered")
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class DesktopAssetQuantityScaleRevisionResultV1:
    status: str
    current_quantity_scale: int
    proposed_quantity_scale: int
    catalog_revision: int
    generation_updated: bool
    affected_fifo_world_count: int
    catalog_write: bool
    activity_fact_write: bool = False
    rounding_performed: bool = False
    fifo_rebuild_required: bool = True
    provider_access: bool = False
    network_access: bool = False
    path_exposed: bool = False
    internal_id_exposed: bool = False


def desktop_asset_quantity_scale_revision_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise DesktopAssetQuantityScaleRevisionV1Error(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        _abort("asset_quantity_scale_input_invalid")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _catalog_fingerprint(value: Any) -> str:
    r"""Der Fingerabdruck eines Katalogzustands, wie der Katalog ihn selbst bildet.

    Der Katalog ist native R-Autorität (ADR-020) und schreibt den
    payload_fingerprint mit rohen UTF-8-Bytes, ohne \uXXXX-Fluchten. Dieses
    Modul hasht sonst mit ensure_ascii=True; fuer ASCII-Namen sind beide Byte-
    folgen gleich, fuer einen Namen mit Umlaut, Akzent oder Gedankenstrich nicht.
    Jede Skalenanhebung fuer ein solches Asset brach deshalb in finalize mit
    asset_quantity_scale_catalog_conflict ab - nach dem Katalogschreiben, also
    mitten im Vorgang.
    """
    try:
        return hashlib.sha256(json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        _abort("asset_quantity_scale_input_invalid")


def _utc_valid(value: Any) -> bool:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        return False
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value


def _utc(value: Any) -> str:
    if not _utc_valid(value):
        _abort("asset_quantity_scale_input_invalid")
    return value


def _runtime(value: Any) -> DesktopProductAssetActivityContextV1:
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("asset_quantity_scale_context_invalid")


def _scale_file(path: str | Path, code: str = "asset_quantity_scale_storage_invalid") -> Path:
    try:
        return _owner_file(path, "desktop_asset_activity_storage_invalid")
    except DesktopProductAssetActivityV1Error:
        _abort(code)


def _scale_directory(
    path: str | Path,
    *,
    create: bool = False,
    code: str = "asset_quantity_scale_storage_invalid",
) -> Path:
    try:
        return _owner_directory(path, create=create)
    except DesktopProductAssetActivityV1Error:
        _abort(code)


def _binding(
    data_space: Path,
    context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    try:
        return read_desktop_product_asset_activity_binding_v1(data_space, context)
    except DesktopProductAssetActivityV1Error:
        _abort("asset_quantity_scale_generation_conflict")


def _read_json(path: Path, code: str) -> dict[str, Any]:
    path = _scale_file(path, code)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _abort(code)
    if not isinstance(value, dict) or path.read_bytes() != _canonical(value) + b"\n":
        _abort(code)
    return value


def _asset(snapshot: Mapping[str, Any], asset_id: str) -> dict[str, Any]:
    if not isinstance(asset_id, str) or not asset_id.startswith("ast_"):
        _abort("asset_quantity_scale_input_invalid")
    matches = [row for row in snapshot["assets"] if row["asset_id"] == asset_id]
    if len(matches) != 1 or matches[0]["status"] != "active":
        _abort("asset_quantity_scale_input_invalid")
    row = dict(matches[0])
    # cash bleibt aussen vor: Cash laeuft auf Skala 2 (Euro-Cent) und wird ueber
    # Tagessalden gefuehrt, nicht ueber Stueckzahlen.
    #
    # derivative stand hier mit, ohne Begruendung in Code, Vertrag oder
    # Entscheidungen - ein Ueberbleibsel derselben Sperre, die rc.207
    # im semantischen FIFO entfernt hat: Ein gekauftes Open-End-
    # Zertifikat verhaelt sich bestandsseitig wie eine Aktie, die Short-Richtung
    # steckt im Papier und nicht in der Buchung. Derivate sind seither buchbar
    # und FIFO-faehig; nur die Skalenanhebung war beim Entsperren uebersehen
    # worden, womit jedes Derivat dauerhaft auf ganze Stuecke festgenagelt blieb
    # und ein Kauf mit Bruchteilen nicht buchbar war.
    if (
        row["asset_type"] == "cash"
        or isinstance(row["quantity_scale"], bool)
        or not isinstance(row["quantity_scale"], int)
        or not 0 <= row["quantity_scale"] <= 24
        or row["origin_type"] != "native"
        or row["origin_ref"] is not None
    ):
        _abort("asset_quantity_scale_input_invalid")
    return row


def _stable_asset_fingerprint(row: Mapping[str, Any]) -> str:
    return _fingerprint({
        key: row[key]
        for key in sorted(row)
        if key not in {"quantity_scale", "updated_at_utc", "revision"}
    })


def _quantity_scale(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 100 or DECIMAL_SOURCE.fullmatch(value) is None:
        _abort("asset_quantity_scale_input_invalid")
    source = value.replace(",", ".")
    try:
        parsed = Decimal(source)
    except InvalidOperation:
        _abort("asset_quantity_scale_input_invalid")
    if not parsed.is_finite():
        _abort("asset_quantity_scale_input_invalid")
    if parsed == 0:
        return 0
    _, raw_digits, raw_exponent = parsed.as_tuple()
    digits = list(raw_digits)
    exponent = raw_exponent
    while digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    if exponent >= 0:
        rendered_length = len(digits) + exponent
    elif len(digits) + exponent > 0:
        rendered_length = len(digits) + 1
    else:
        rendered_length = 2 - exponent
    if rendered_length > 80:
        _abort("asset_quantity_scale_required_exceeds_limit")
    return max(0, -exponent)


def _required_scale(quantity_values: Any) -> tuple[int | None, str]:
    if not isinstance(quantity_values, Mapping) or set(quantity_values) != set(QUANTITY_FIELDS):
        _abort("asset_quantity_scale_input_invalid")
    scales = [_quantity_scale(quantity_values[field]) for field in QUANTITY_FIELDS]
    observed = [value for value in scales if value is not None]
    required = max(observed) if observed else None
    evidence = {
        field: None if quantity_values[field] in {None, ""} else str(quantity_values[field])
        for field in QUANTITY_FIELDS
    }
    return required, _fingerprint(evidence)


def _trusted_preview(
    value: Any,
    context: DesktopProductAssetActivityContextV1,
    code: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _abort(code)
    preview = dict(value)
    if set(preview) != TRUSTED_PREVIEW_KEYS:
        _abort(code)
    body = dict(preview)
    plan_fingerprint = body.pop("plan_fingerprint", None)
    worlds = preview.get("prospective_fifo_world_result_fingerprints")
    source_generation = preview.get("source_generation_ref")
    source_activity = preview.get("source_activity_set_fingerprint")
    integer_values = (
        preview.get("expected_catalog_revision"),
        preview.get("current_quantity_scale"),
        preview.get("required_quantity_scale"),
        preview.get("proposed_quantity_scale"),
        preview.get("affected_fifo_world_count"),
    )
    if (
        preview.get("asset_quantity_scale_preview_version") != 1
        or isinstance(preview.get("asset_quantity_scale_preview_version"), bool)
        or preview.get("status") != "ready_for_confirmation"
        or preview.get("context_fingerprint") != _context_fingerprint(context)
        or any(not isinstance(item, int) or isinstance(item, bool) for item in integer_values)
        or preview["expected_catalog_revision"] < 1
        or not 0 <= preview["current_quantity_scale"] < preview["proposed_quantity_scale"] <= 24
        or preview["required_quantity_scale"] != preview["proposed_quantity_scale"]
        or preview["affected_fifo_world_count"] < 0
        or not isinstance(preview.get("asset_id"), str)
        or not preview["asset_id"].startswith("ast_")
        or not isinstance(preview.get("asset_label"), str)
        or not 1 <= len(preview["asset_label"]) <= 160
        or not _utc_valid(preview.get("previewed_at_utc"))
        or any(
            HEX64.fullmatch(preview.get(key, "")) is None
            for key in (
                "context_fingerprint",
                "source_canonical_fingerprint",
                "asset_stable_fingerprint",
                "quantity_evidence_fingerprint",
            )
        )
        or HEX64.fullmatch(plan_fingerprint or "") is None
        or plan_fingerprint != _fingerprint(body)
        or not isinstance(worlds, dict)
        or any(
            not isinstance(world_ref, str)
            or not world_ref
            or not isinstance(result_fingerprint, str)
            or HEX64.fullmatch(result_fingerprint) is None
            for world_ref, result_fingerprint in worlds.items()
        )
        or preview["affected_fifo_world_count"] > len(worlds)
        or preview.get("confirmation_required") is not True
        or preview.get("catalog_write") is not True
        or preview.get("activity_fact_write") is not False
        or preview.get("rounding_performed") is not False
        or preview.get("provider_access") is not False
        or preview.get("network_access") is not False
    ):
        _abort(code)
    if source_generation is None:
        if source_activity is not None or worlds or preview["affected_fifo_world_count"] != 0:
            _abort(code)
    elif (
        not isinstance(source_generation, str)
        or not source_generation.startswith("gen_")
        or not isinstance(source_activity, str)
        or HEX64.fullmatch(source_activity) is None
    ):
        _abort(code)
    return preview


def _append_preview_revision(
    ledger: Path,
    asset_id: str,
    expected_scale: int,
    proposed_scale: int,
    plan_seed: str,
    at_utc: str,
) -> None:
    connection = sqlite3.connect(ledger)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        current = connection.execute(
            "SELECT * FROM current_asset_revision WHERE asset_id=?",
            (asset_id,),
        ).fetchall()
        if len(current) != 1 or current[0]["quantity_scale"] != expected_scale:
            _abort("asset_quantity_scale_preview_stale")
        row = dict(current[0])
        command_id = "cmd_scale_preview_" + plan_seed[:40]
        payload_fingerprint = _fingerprint({
            "asset_id": asset_id,
            "current_quantity_scale": expected_scale,
            "proposed_quantity_scale": proposed_scale,
        })
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO ledger_command_receipt VALUES(?,'data_app','asset_quantity_scale_revision_v1','scale_preview',?,NULL,?)",
            (command_id, payload_fingerprint, at_utc),
        )
        connection.execute(
            "INSERT INTO asset_revision "
            "(asset_revision_id,asset_id,revision_no,display_name,asset_type,quantity_scale,valuation_method,isin,note,status,metadata_status,supersedes_revision_id,command_id,created_at_utc) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "asr_" + _fingerprint({"plan_seed": plan_seed, "asset_id": asset_id})[:32],
                asset_id,
                row["revision_no"] + 1,
                row["display_name"],
                row["asset_type"],
                proposed_scale,
                row["valuation_method"],
                row["isin"],
                row["note"],
                row["status"],
                row["metadata_status"],
                row["asset_revision_id"],
                command_id,
                at_utc,
            ),
        )
        connection.execute("COMMIT")
    except DesktopAssetQuantityScaleRevisionV1Error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    except sqlite3.Error:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        _abort("asset_quantity_scale_storage_invalid")
    finally:
        connection.close()


def _affected_world_count(ledger: Path, asset_id: str) -> int:
    connection = _read_connection(ledger)
    try:
        return int(connection.execute(
            "SELECT count(*) FROM ("
            "SELECT DISTINCT portfolio_id,asset_id FROM current_asset_activity_event "
            "WHERE asset_id=? OR source_asset_id=?"
            ")",
            (asset_id, asset_id),
        ).fetchone()[0])
    except sqlite3.Error:
        _abort("asset_quantity_scale_storage_invalid")
    finally:
        connection.close()


def preview_desktop_asset_quantity_scale_revision_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: Any,
    asset_id: str,
    quantity_values: Mapping[str, Any],
    previewed_at_utc: str,
) -> dict[str, Any]:
    context = _runtime(context_value)
    at_utc = _utc(previewed_at_utc)
    canonical = _scale_file(canonical_path)
    data_space = _scale_directory(data_space_path)
    snapshot = _canonical_snapshot(canonical, context)
    asset = _asset(snapshot, asset_id)
    required_scale, evidence_fingerprint = _required_scale(quantity_values)
    if required_scale is None or required_scale <= asset["quantity_scale"]:
        public = {
            "asset_quantity_scale_public_preview_version": 1,
            "status": "within_current_scale",
            "asset_label": asset["display_name"],
            "current_quantity_scale": asset["quantity_scale"],
            "required_quantity_scale": required_scale,
            "proposed_quantity_scale": asset["quantity_scale"],
            "scale_revision_required": False,
            "warning_required": False,
            "rounding_performed": False,
            "affected_fifo_world_count": 0,
            "confirmation_required": False,
            "catalog_write": False,
            "activity_fact_write": False,
            "fifo_rebuild_required": False,
            "provider_access": False,
            "network_access": False,
            "path_exposed": False,
            "internal_id_exposed": False,
        }
        return {"public_preview": public, "trusted_preview": None}
    if required_scale > 24:
        _abort("asset_quantity_scale_required_exceeds_limit")

    binding = _binding(data_space, context)
    source_generation_ref = None
    source_activity_set_fingerprint = None
    prospective_fifo: dict[str, str] = {}
    affected_count = 0
    if binding.get("status") == "available":
        source_generation_ref = binding["generation_ref"]
        source_activity_set_fingerprint = binding["activity_set_fingerprint"]
        with tempfile.TemporaryDirectory(prefix=".quantity-scale-preview-", dir=data_space) as temporary:
            target = Path(temporary) / LEDGER_NAME
            materialize_desktop_product_semantic_ledger_v1(
                canonical,
                Path(binding["ledger_path"]),
                target,
                context,
            )
            seed = _fingerprint({
                "canonical_fingerprint": snapshot["source_fingerprint"],
                "source_generation_ref": source_generation_ref,
                "asset_id": asset_id,
                "required_quantity_scale": required_scale,
                "quantity_evidence_fingerprint": evidence_fingerprint,
            })
            _append_preview_revision(
                target,
                asset_id,
                asset["quantity_scale"],
                required_scale,
                seed,
                at_utc,
            )
            try:
                prospective_fifo = _fifo_worlds(target)
            except DesktopAssetActivityCorrectionV1Error:
                _abort("asset_quantity_scale_fifo_invalid")
            affected_count = _affected_world_count(target, asset_id)
    elif binding.get("status") != "absent":
        _abort("asset_quantity_scale_generation_conflict")

    body = {
        "asset_quantity_scale_preview_version": 1,
        "status": "ready_for_confirmation",
        "context_fingerprint": _context_fingerprint(context),
        "source_canonical_fingerprint": snapshot["source_fingerprint"],
        "source_generation_ref": source_generation_ref,
        "source_activity_set_fingerprint": source_activity_set_fingerprint,
        "asset_id": asset_id,
        "asset_label": asset["display_name"],
        "asset_stable_fingerprint": _stable_asset_fingerprint(asset),
        "expected_catalog_revision": asset["revision"],
        "current_quantity_scale": asset["quantity_scale"],
        "required_quantity_scale": required_scale,
        "proposed_quantity_scale": required_scale,
        "quantity_evidence_fingerprint": evidence_fingerprint,
        "prospective_fifo_world_result_fingerprints": prospective_fifo,
        "affected_fifo_world_count": affected_count,
        "previewed_at_utc": at_utc,
        "confirmation_required": True,
        "catalog_write": True,
        "activity_fact_write": False,
        "rounding_performed": False,
        "provider_access": False,
        "network_access": False,
    }
    body["plan_fingerprint"] = _fingerprint(body)
    public = {
        "asset_quantity_scale_public_preview_version": 1,
        "status": "ready_for_confirmation",
        "asset_label": asset["display_name"],
        "current_quantity_scale": asset["quantity_scale"],
        "required_quantity_scale": required_scale,
        "proposed_quantity_scale": required_scale,
        "scale_revision_required": True,
        "warning_required": True,
        "warning_code": "activity_quantity_scale_revision_required",
        "warning_text": (
            "Die eingegebene Menge benötigt eine feinere Mengenskala. Portelyra passt "
            f"die Skala dieses Assets von {asset['quantity_scale']} auf {required_scale} an "
            "und baut anschließend die betroffenen FIFO-Historien neu auf. Mengen werden nicht gerundet."
        ),
        "rounding_performed": False,
        "affected_fifo_world_count": affected_count,
        "confirmation_required": True,
        "catalog_write": True,
        "activity_fact_write": False,
        "fifo_rebuild_required": affected_count > 0,
        "provider_access": False,
        "network_access": False,
        "path_exposed": False,
        "internal_id_exposed": False,
    }
    return {"public_preview": public, "trusted_preview": body}


def build_desktop_asset_quantity_scale_confirmation_v1(
    trusted_preview: Mapping[str, Any],
    context_value: Any,
    challenge_ref: str,
    issued_at_utc: str,
    confirmed_at_utc: str,
    expires_at_utc: str,
) -> dict[str, Any]:
    context = _runtime(context_value)
    trusted = _trusted_preview(
        trusted_preview, context, "asset_quantity_scale_confirmation_invalid"
    )
    if not all(_utc_valid(value) for value in (issued_at_utc, confirmed_at_utc, expires_at_utc)):
        _abort("asset_quantity_scale_confirmation_invalid")
    issued = issued_at_utc
    confirmed = confirmed_at_utc
    expires = expires_at_utc
    if (
        not isinstance(challenge_ref, str)
        or CHALLENGE.fullmatch(challenge_ref) is None
        or not issued <= confirmed <= expires
    ):
        _abort("asset_quantity_scale_confirmation_invalid")
    body = {
        "asset_quantity_scale_confirmation_version": 1,
        "challenge_ref": challenge_ref,
        "context_fingerprint": _context_fingerprint(context),
        "plan_fingerprint": trusted["plan_fingerprint"],
        "issued_at_utc": issued,
        "confirmed_at_utc": confirmed,
        "expires_at_utc": expires,
    }
    body["confirmation_fingerprint"] = _fingerprint(body)
    return body


def _catalog_token(plan_fingerprint: str) -> str:
    return "tok_scale_" + plan_fingerprint[:40]


def _catalog_command_id(
    context: DesktopProductAssetActivityContextV1,
    token: str,
    asset_id: str,
) -> str:
    parts = (
        "native-catalog-command-v1",
        context.tenant_id,
        context.user_id,
        context.data_space_id,
        "catalog_rescale_asset_v1",
        token,
        asset_id,
    )
    return "cmd_catalog_" + hashlib.sha256(b"\x00".join(part.encode("utf-8") for part in parts)).hexdigest()[:52]


def _attempt_path(area: Path, challenge_ref: str) -> Path:
    attempts = _scale_directory(area / ATTEMPT_AREA, create=True)
    return attempts / (challenge_ref + ATTEMPT_SUFFIX)


def _validate_confirmation(
    trusted_preview: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    context: DesktopProductAssetActivityContextV1,
    committed_at_utc: str,
) -> None:
    keys = (
        "asset_quantity_scale_confirmation_version",
        "challenge_ref",
        "context_fingerprint",
        "plan_fingerprint",
        "issued_at_utc",
        "confirmed_at_utc",
        "expires_at_utc",
    )
    expected = {key: confirmation.get(key) for key in keys}
    expected["confirmation_fingerprint"] = _fingerprint(expected)
    times = tuple(confirmation.get(key) for key in ("issued_at_utc", "confirmed_at_utc", "expires_at_utc"))
    if (
        dict(confirmation) != expected
        or confirmation.get("asset_quantity_scale_confirmation_version") != 1
        or isinstance(confirmation.get("asset_quantity_scale_confirmation_version"), bool)
        or not isinstance(confirmation.get("challenge_ref"), str)
        or CHALLENGE.fullmatch(confirmation["challenge_ref"]) is None
        or confirmation.get("context_fingerprint") != _context_fingerprint(context)
        or confirmation.get("plan_fingerprint") != trusted_preview.get("plan_fingerprint")
        or HEX64.fullmatch(confirmation.get("confirmation_fingerprint", "")) is None
        or not all(_utc_valid(value) for value in times)
        or not times[0] <= times[1] <= times[2]
        or committed_at_utc < times[1]
    ):
        _abort("asset_quantity_scale_confirmation_invalid")
    if committed_at_utc > confirmation["expires_at_utc"]:
        _abort("asset_quantity_scale_confirmation_expired")


def _validate_source_state(
    canonical: Path,
    data_space: Path,
    context: DesktopProductAssetActivityContextV1,
    trusted_preview: Mapping[str, Any],
) -> dict[str, Any]:
    snapshot = _canonical_snapshot(canonical, context)
    asset = _asset(snapshot, trusted_preview.get("asset_id"))
    binding = _binding(data_space, context)
    source_generation = trusted_preview.get("source_generation_ref")
    source_activity = trusted_preview.get("source_activity_set_fingerprint")
    binding_matches = (
        (source_generation is None and binding.get("status") == "absent")
        or (
            binding.get("status") == "available"
            and binding.get("generation_ref") == source_generation
            and binding.get("activity_set_fingerprint") == source_activity
        )
    )
    if (
        snapshot["source_fingerprint"] != trusted_preview.get("source_canonical_fingerprint")
        or asset["revision"] != trusted_preview.get("expected_catalog_revision")
        or asset["quantity_scale"] != trusted_preview.get("current_quantity_scale")
        or _stable_asset_fingerprint(asset) != trusted_preview.get("asset_stable_fingerprint")
        or not binding_matches
    ):
        _abort("asset_quantity_scale_preview_stale")
    return asset


def begin_desktop_asset_quantity_scale_revision_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: Any,
    trusted_preview: Mapping[str, Any],
    confirmation: Mapping[str, Any],
    committed_at_utc: str,
    *,
    failpoint: str | None = None,
) -> dict[str, Any]:
    context = _runtime(context_value)
    committed = _utc(committed_at_utc)
    if (
        failpoint not in {None, "after_attempt"}
        or not isinstance(trusted_preview, Mapping)
        or trusted_preview.get("status") != "ready_for_confirmation"
        or not isinstance(confirmation, Mapping)
    ):
        _abort("asset_quantity_scale_input_invalid")
    trusted = _trusted_preview(trusted_preview, context, "asset_quantity_scale_input_invalid")
    _validate_confirmation(trusted, confirmation, context, committed)
    canonical = _scale_file(canonical_path)
    data_space = _scale_directory(data_space_path)
    area = _scale_directory(data_space / PRODUCT_AREA, create=True)
    with _ProductWriterLockV1(area):
        _validate_source_state(canonical, data_space, context, trusted)
        token = _catalog_token(trusted["plan_fingerprint"])
        command = {
            "command_token": token,
            "asset_id": trusted["asset_id"],
            "expected_revision": trusted["expected_catalog_revision"],
            "quantity_scale": trusted["proposed_quantity_scale"],
            "committed_at_utc": committed,
        }
        body = {
            "asset_quantity_scale_attempt_version": 1,
            "attempt_status": "consumed_before_catalog_write",
            "context_fingerprint": _context_fingerprint(context),
            "challenge_ref": confirmation["challenge_ref"],
            "plan_fingerprint": trusted["plan_fingerprint"],
            "confirmation_fingerprint": confirmation["confirmation_fingerprint"],
            "trusted_preview": trusted,
            "catalog_command": command,
            "catalog_command_id": _catalog_command_id(context, token, trusted["asset_id"]),
            "attempted_at_utc": committed,
        }
        body["attempt_fingerprint"] = _fingerprint(body)
        matching_plan_attempts = [
            value
            for _, value in _attempts(area, context)
            if value["plan_fingerprint"] == trusted["plan_fingerprint"]
        ]
        if len(matching_plan_attempts) > 1 or (
            matching_plan_attempts and matching_plan_attempts[0] != body
        ):
            _abort("asset_quantity_scale_attempt_conflict")
        path = _attempt_path(area, confirmation["challenge_ref"])
        content = _canonical(body) + b"\n"
        if path.exists():
            if _scale_file(path, "asset_quantity_scale_attempt_conflict").read_bytes() != content:
                _abort("asset_quantity_scale_attempt_conflict")
        else:
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
                _abort("asset_quantity_scale_attempt_conflict")
        if failpoint == "after_attempt":
            _abort("synthetic_asset_quantity_scale_failpoint")
        return {
            "status": "pending_catalog_write",
            "plan_fingerprint": trusted["plan_fingerprint"],
            "catalog_command": command,
            "attempt_consumed": True,
            "path_exposed": False,
            "internal_id_exposed": False,
        }


def _validate_attempt(
    path: Path,
    value: Any,
    context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _abort("asset_quantity_scale_attempt_conflict")
    attempt = dict(value)
    expected_keys = {
        "asset_quantity_scale_attempt_version",
        "attempt_status",
        "context_fingerprint",
        "challenge_ref",
        "plan_fingerprint",
        "confirmation_fingerprint",
        "trusted_preview",
        "catalog_command",
        "catalog_command_id",
        "attempted_at_utc",
        "attempt_fingerprint",
    }
    body = dict(attempt)
    attempt_fingerprint = body.pop("attempt_fingerprint", None)
    trusted = _trusted_preview(
        attempt.get("trusted_preview"), context, "asset_quantity_scale_attempt_conflict"
    )
    command = attempt.get("catalog_command")
    challenge = attempt.get("challenge_ref")
    expected_command = {
        "command_token": _catalog_token(trusted["plan_fingerprint"]),
        "asset_id": trusted["asset_id"],
        "expected_revision": trusted["expected_catalog_revision"],
        "quantity_scale": trusted["proposed_quantity_scale"],
        "committed_at_utc": attempt.get("attempted_at_utc"),
    }
    if (
        set(attempt) != expected_keys
        or attempt.get("asset_quantity_scale_attempt_version") != 1
        or isinstance(attempt.get("asset_quantity_scale_attempt_version"), bool)
        or attempt.get("attempt_status") != "consumed_before_catalog_write"
        or attempt.get("context_fingerprint") != _context_fingerprint(context)
        or attempt.get("plan_fingerprint") != trusted["plan_fingerprint"]
        or not isinstance(challenge, str)
        or CHALLENGE.fullmatch(challenge) is None
        or path.name != challenge + ATTEMPT_SUFFIX
        or HEX64.fullmatch(attempt.get("confirmation_fingerprint", "")) is None
        or not _utc_valid(attempt.get("attempted_at_utc"))
        or command != expected_command
        or attempt.get("catalog_command_id")
        != _catalog_command_id(context, expected_command["command_token"], trusted["asset_id"])
        or HEX64.fullmatch(attempt_fingerprint or "") is None
        or attempt_fingerprint != _fingerprint(body)
    ):
        _abort("asset_quantity_scale_attempt_conflict")
    return attempt


def _attempts(
    area: Path,
    context: DesktopProductAssetActivityContextV1,
) -> list[tuple[Path, dict[str, Any]]]:
    directory = area / ATTEMPT_AREA
    if not directory.exists():
        return []
    directory = _scale_directory(directory)
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(directory.iterdir()):
        if not path.name.endswith(ATTEMPT_SUFFIX) or path.is_symlink() or not path.is_file():
            _abort("asset_quantity_scale_attempt_conflict")
        value = _read_json(path, "asset_quantity_scale_attempt_conflict")
        result.append((path, _validate_attempt(path, value, context)))
    return result


def _find_attempt(
    area: Path,
    plan_fingerprint: str,
    context: DesktopProductAssetActivityContextV1,
) -> dict[str, Any]:
    matches = [
        value
        for _, value in _attempts(area, context)
        if value.get("plan_fingerprint") == plan_fingerprint
    ]
    if len(matches) != 1:
        _abort("asset_quantity_scale_attempt_conflict")
    return matches[0]


def _catalog_asset_payload_fingerprint(asset: Mapping[str, Any]) -> str:
    columns = (
        "asset_id",
        "display_name",
        "asset_type",
        "price_currency",
        "quantity_scale",
        "valuation_method",
        "isin",
        "status",
        "origin_type",
        "origin_ref",
        "created_at_utc",
        "updated_at_utc",
        "revision",
    )
    if any(column not in asset for column in columns):
        _abort("asset_quantity_scale_catalog_conflict")
    return _catalog_fingerprint({
        "catalog_entity_state_version": 1,
        "entity_type": "asset",
        "entity": {column: asset[column] for column in columns},
    })


def _catalog_state(
    canonical: Path,
    context: DesktopProductAssetActivityContextV1,
    attempt: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    preview = attempt["trusted_preview"]
    snapshot = _canonical_snapshot(canonical, context)
    asset = _asset(snapshot, preview["asset_id"])
    if (
        snapshot["source_fingerprint"] == preview["source_canonical_fingerprint"]
        and asset["revision"] == preview["expected_catalog_revision"]
        and asset["quantity_scale"] == preview["current_quantity_scale"]
        and _stable_asset_fingerprint(asset) == preview["asset_stable_fingerprint"]
    ):
        return "pending_catalog_write", asset
    if (
        asset["revision"] != preview["expected_catalog_revision"] + 1
        or asset["quantity_scale"] != preview["proposed_quantity_scale"]
        or asset["updated_at_utc"] != attempt["catalog_command"]["committed_at_utc"]
        or _stable_asset_fingerprint(asset) != preview["asset_stable_fingerprint"]
    ):
        _abort("asset_quantity_scale_catalog_conflict")
    connection = _read_connection(canonical)
    try:
        rows = connection.execute(
            "SELECT command_id,command_type,actor_id,committed_at_utc,payload_fingerprint,origin_type,origin_ref "
            "FROM data_command_audit WHERE area_id='asset_catalog' AND entity_id=? "
            "ORDER BY committed_at_utc DESC,command_id DESC LIMIT 1",
            (preview["asset_id"],),
        ).fetchall()
    except sqlite3.Error:
        _abort("asset_quantity_scale_catalog_conflict")
    finally:
        connection.close()
    if (
        len(rows) != 1
        or rows[0]["command_id"] != attempt["catalog_command_id"]
        or rows[0]["command_type"] != "catalog_rescale_asset_v1"
        or rows[0]["actor_id"] != context.actor_id
        or rows[0]["committed_at_utc"] != attempt["catalog_command"]["committed_at_utc"]
        or rows[0]["payload_fingerprint"] != _catalog_asset_payload_fingerprint(asset)
        or rows[0]["origin_type"] != "native"
        or rows[0]["origin_ref"] is not None
    ):
        _abort("asset_quantity_scale_catalog_conflict")
    return "pending_generation_finalize", asset


def _receipt_body(value: dict[str, Any]) -> dict[str, Any]:
    body = dict(value)
    fingerprint = body.pop("receipt_fingerprint", None)
    if fingerprint != _fingerprint(body):
        _abort("asset_quantity_scale_receipt_invalid")
    return value


def _generation_receipts(area: Path, plan_fingerprint: str) -> list[tuple[Path, dict[str, Any]]]:
    generations = area / "generations"
    if not generations.exists():
        return []
    generations = _scale_directory(generations)
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(generations.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        receipt_path = path / RECEIPT_NAME
        if receipt_path.exists():
            value = _receipt_body(_read_json(receipt_path, "asset_quantity_scale_receipt_invalid"))
            if value.get("plan_fingerprint") == plan_fingerprint:
                result.append((path, value))
    if len(result) > 1:
        _abort("asset_quantity_scale_generation_conflict")
    return result


def _generation_receipts_by_plan(area: Path) -> dict[str, list[tuple[Path, dict[str, Any]]]]:
    """Alle Quittungen in einem Durchgang, nach Plan geordnet."""
    generations = area / "generations"
    if not generations.exists():
        return {}
    generations = _scale_directory(generations)
    result: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for path in sorted(generations.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        receipt_path = path / RECEIPT_NAME
        if receipt_path.exists():
            value = _receipt_body(_read_json(receipt_path, "asset_quantity_scale_receipt_invalid"))
            result.setdefault(value.get("plan_fingerprint"), []).append((path, value))
    return result


def _no_generation_receipt(area: Path, plan_fingerprint: str) -> dict[str, Any] | None:
    directory = area / NO_GENERATION_RECEIPT_AREA
    if not directory.exists():
        return None
    path = _scale_directory(directory) / (plan_fingerprint + ".json")
    if not path.exists():
        return None
    return _receipt_body(_read_json(path, "asset_quantity_scale_receipt_invalid"))


def _result_from_receipt(receipt: Mapping[str, Any], status: str) -> DesktopAssetQuantityScaleRevisionResultV1:
    return DesktopAssetQuantityScaleRevisionResultV1(
        status=status,
        current_quantity_scale=receipt["current_quantity_scale"],
        proposed_quantity_scale=receipt["proposed_quantity_scale"],
        catalog_revision=receipt["catalog_revision"],
        generation_updated=receipt["generation_ref"] is not None,
        affected_fifo_world_count=receipt["affected_fifo_world_count"],
        catalog_write=status == "committed",
        fifo_rebuild_required=receipt["affected_fifo_world_count"] > 0,
    )


def finalize_desktop_asset_quantity_scale_revision_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: Any,
    plan_fingerprint: str,
    *,
    failpoint: str | None = None,
) -> DesktopAssetQuantityScaleRevisionResultV1:
    context = _runtime(context_value)
    if (
        not isinstance(plan_fingerprint, str)
        or re.fullmatch(r"[a-f0-9]{64}", plan_fingerprint) is None
        or failpoint not in FAILPOINTS
    ):
        _abort("asset_quantity_scale_input_invalid")
    canonical = _scale_file(canonical_path)
    data_space = _scale_directory(data_space_path)
    area = _scale_directory(data_space / PRODUCT_AREA, create=True)
    with _ProductWriterLockV1(area):
        attempt = _find_attempt(area, plan_fingerprint, context)
        if attempt.get("context_fingerprint") != _context_fingerprint(context):
            _abort("asset_quantity_scale_context_invalid")
        no_generation = _no_generation_receipt(area, plan_fingerprint)
        if no_generation is not None:
            preview = attempt["trusted_preview"]
            if (
                no_generation.get("context_fingerprint") != _context_fingerprint(context)
                or no_generation.get("plan_fingerprint") != plan_fingerprint
                or no_generation.get("confirmation_fingerprint")
                != attempt["confirmation_fingerprint"]
                or no_generation.get("catalog_command_id") != attempt["catalog_command_id"]
                or no_generation.get("prior_generation_ref") is not None
                or no_generation.get("generation_ref") is not None
                or no_generation.get("current_quantity_scale")
                != preview["current_quantity_scale"]
                or no_generation.get("proposed_quantity_scale")
                != preview["proposed_quantity_scale"]
                or no_generation.get("affected_fifo_world_count") != 0
                or no_generation.get("fifo_world_result_fingerprints") != {}
                or no_generation.get("activity_set_fingerprint") is not None
            ):
                _abort("asset_quantity_scale_receipt_invalid")
            return _result_from_receipt(no_generation, "already_committed")
        existing = _generation_receipts(area, plan_fingerprint)
        if existing:
            final, receipt = existing[0]
            binding = _binding(data_space, context)
            if binding.get("generation_ref") == receipt["generation_ref"]:
                return _result_from_receipt(receipt, "already_committed")
            if binding.get("generation_ref") != receipt["prior_generation_ref"]:
                _abort("asset_quantity_scale_generation_conflict")
            catalog_state, _ = _catalog_state(canonical, context, attempt)
            if catalog_state != "pending_generation_finalize":
                _abort("asset_quantity_scale_catalog_conflict")
            preview = attempt["trusted_preview"]
            manifest = _read_json(final / MANIFEST_NAME, "asset_quantity_scale_receipt_invalid")
            ledger = _scale_file(final / LEDGER_NAME, "asset_quantity_scale_receipt_invalid")
            success = _scale_file(final / SUCCESS_NAME, "asset_quantity_scale_receipt_invalid")
            if (
                final.name != receipt.get("generation_ref")
                or success.read_bytes() != b"completed\n"
                or receipt.get("context_fingerprint") != _context_fingerprint(context)
                or receipt.get("plan_fingerprint") != plan_fingerprint
                or receipt.get("confirmation_fingerprint") != attempt["confirmation_fingerprint"]
                or receipt.get("catalog_command_id") != attempt["catalog_command_id"]
                or receipt.get("prior_generation_ref") != preview["source_generation_ref"]
                or receipt.get("current_quantity_scale") != preview["current_quantity_scale"]
                or receipt.get("proposed_quantity_scale") != preview["proposed_quantity_scale"]
                or receipt.get("affected_fifo_world_count") != preview["affected_fifo_world_count"]
                or receipt.get("fifo_world_result_fingerprints")
                != preview["prospective_fifo_world_result_fingerprints"]
                or receipt.get("activity_set_fingerprint")
                != preview["source_activity_set_fingerprint"]
                or manifest.get("context_fingerprint") != _context_fingerprint(context)
                or manifest.get("generation_ref") != receipt["generation_ref"]
                or manifest.get("prior_activity_set_fingerprint")
                != preview["source_activity_set_fingerprint"]
                or manifest.get("activity_set_fingerprint")
                != preview["source_activity_set_fingerprint"]
                or manifest.get("plan_fingerprint") != plan_fingerprint
                or manifest.get("command_id") != attempt["catalog_command_id"]
                or manifest.get("ledger_fingerprint") != _sha_file(ledger)
            ):
                _abort("asset_quantity_scale_receipt_invalid")
            with _CanonicalReadBarrierV1(data_space):
                if _sha_file(canonical) != manifest.get("canonical_fingerprint"):
                    _abort("asset_quantity_scale_preview_stale")
                _atomic_json_replace(area / ACTIVE_NAME, {
                    "contract_version": 1,
                    "generation_ref": receipt["generation_ref"],
                    "ledger_fingerprint": manifest["ledger_fingerprint"],
                    "manifest_fingerprint": _sha_file(final / MANIFEST_NAME),
                })
            return _result_from_receipt(receipt, "recovered_committed")

        catalog_state, asset = _catalog_state(canonical, context, attempt)
        if catalog_state != "pending_generation_finalize":
            _abort("asset_quantity_scale_catalog_conflict")
        preview = attempt["trusted_preview"]
        binding = _binding(data_space, context)
        source_generation = preview["source_generation_ref"]
        if source_generation is None:
            if binding.get("status") != "absent":
                _abort("asset_quantity_scale_generation_conflict")
            receipt_body = {
                "asset_quantity_scale_receipt_version": 1,
                "context_fingerprint": _context_fingerprint(context),
                "plan_fingerprint": plan_fingerprint,
                "confirmation_fingerprint": attempt["confirmation_fingerprint"],
                "catalog_command_id": attempt["catalog_command_id"],
                "prior_generation_ref": None,
                "generation_ref": None,
                "current_quantity_scale": preview["current_quantity_scale"],
                "proposed_quantity_scale": preview["proposed_quantity_scale"],
                "catalog_revision": asset["revision"],
                "affected_fifo_world_count": 0,
                "fifo_world_result_fingerprints": {},
                "activity_set_fingerprint": None,
                "committed_at_utc": attempt["catalog_command"]["committed_at_utc"],
                "catalog_write": True,
                "activity_fact_write": False,
                "rounding_performed": False,
                "provider_access": False,
                "network_access": False,
            }
            receipt_body["receipt_fingerprint"] = _fingerprint(receipt_body)
            directory = _scale_directory(area / NO_GENERATION_RECEIPT_AREA, create=True)
            _write_new_file(directory / (plan_fingerprint + ".json"), _canonical(receipt_body) + b"\n")
            return _result_from_receipt(receipt_body, "committed")
        if (
            binding.get("status") != "available"
            or binding.get("generation_ref") != source_generation
            or binding.get("activity_set_fingerprint") != preview["source_activity_set_fingerprint"]
        ):
            _abort("asset_quantity_scale_generation_conflict")

        generations = _scale_directory(area / "generations", create=True)
        _remove_staging_generations(generations)
        staging = generations / (".staging-scale-" + secrets.token_hex(16))
        os.mkdir(staging, 0o700)
        os.chmod(staging, 0o700)
        published = False
        try:
            target = staging / LEDGER_NAME
            materialized = materialize_desktop_product_semantic_ledger_v1(
                canonical,
                Path(binding["ledger_path"]),
                target,
                context,
            )
            connection = _read_connection(target)
            try:
                current = connection.execute(
                    "SELECT quantity_scale FROM current_asset_revision WHERE asset_id=?",
                    (preview["asset_id"],),
                ).fetchall()
                activity = _activity_rows(connection)
            except sqlite3.Error:
                _abort("asset_quantity_scale_storage_invalid")
            finally:
                connection.close()
            if len(current) != 1 or current[0]["quantity_scale"] != preview["proposed_quantity_scale"]:
                _abort("asset_quantity_scale_preview_stale")
            try:
                fifo = _fifo_worlds(target)
            except DesktopAssetActivityCorrectionV1Error:
                _abort("asset_quantity_scale_fifo_invalid")
            if fifo != preview["prospective_fifo_world_result_fingerprints"]:
                _abort("asset_quantity_scale_fifo_invalid")
            if activity["activity_set_fingerprint"] != preview["source_activity_set_fingerprint"]:
                _abort("asset_quantity_scale_preview_stale")
            ledger_fingerprint = _sha_file(target)
            generation_ref = "gen_" + _fingerprint({
                "prior_generation_ref": source_generation,
                "plan_fingerprint": plan_fingerprint,
                "canonical_fingerprint": materialized["canonical_fingerprint"],
                "activity_set_fingerprint": activity["activity_set_fingerprint"],
            })[:32]
            receipt_body = {
                "asset_quantity_scale_receipt_version": 1,
                "context_fingerprint": _context_fingerprint(context),
                "plan_fingerprint": plan_fingerprint,
                "confirmation_fingerprint": attempt["confirmation_fingerprint"],
                "catalog_command_id": attempt["catalog_command_id"],
                "prior_generation_ref": source_generation,
                "generation_ref": generation_ref,
                "current_quantity_scale": preview["current_quantity_scale"],
                "proposed_quantity_scale": preview["proposed_quantity_scale"],
                "catalog_revision": asset["revision"],
                "affected_fifo_world_count": preview["affected_fifo_world_count"],
                "fifo_world_result_fingerprints": fifo,
                "activity_set_fingerprint": activity["activity_set_fingerprint"],
                "committed_at_utc": attempt["catalog_command"]["committed_at_utc"],
                "catalog_write": True,
                "activity_fact_write": False,
                "rounding_performed": False,
                "provider_access": False,
                "network_access": False,
            }
            receipt_body["receipt_fingerprint"] = _fingerprint(receipt_body)
            manifest = {
                "contract_version": 1,
                "authority_contract": "schema201_derived_base_plus_asset_activity_v1",
                "context_fingerprint": _context_fingerprint(context),
                "generation_ref": generation_ref,
                "canonical_schema_version": materialized["canonical_schema_version"],
                "canonical_fingerprint": materialized["canonical_fingerprint"],
                "prior_activity_set_fingerprint": binding["activity_set_fingerprint"],
                "activity_set_fingerprint": activity["activity_set_fingerprint"],
                "ledger_schema_version": 401,
                "ledger_fingerprint": ledger_fingerprint,
                "plan_fingerprint": plan_fingerprint,
                "command_id": attempt["catalog_command_id"],
                "new_event_count": 0,
                "total_asset_activity_event_count": len(activity["asset_activity_events"]),
                "committed_at_utc": attempt["catalog_command"]["committed_at_utc"],
                "semantic_contracts": ["portfolio_ledger_v1_transaction_fact", "asset_activity_v1"],
                "boundaries": {
                    "schema201_catalog_authority": "catalog_rescale_asset_v1",
                    "schema201_transaction_authority": "derived_read_only",
                    "asset_activity_authority": "unchanged_generation_republication",
                    "automatic_cash_posting_count": 0,
                    "provider_access": False,
                    "network_access": False,
                },
            }
            _write_new_file(staging / RECEIPT_NAME, _canonical(receipt_body) + b"\n")
            _write_new_file(staging / MANIFEST_NAME, _canonical(manifest) + b"\n")
            _write_new_file(staging / SUCCESS_NAME, b"completed\n")
            if failpoint == "after_generation_complete":
                _abort("synthetic_asset_quantity_scale_failpoint")
            final = generations / generation_ref
            if final.exists():
                _abort("asset_quantity_scale_generation_conflict")
            settle_new_directory_v1(staging)  # #568: auch die gocryptfs.diriv neuer Ordner festschreiben
            os.rename(staging, final)
            published = True
            if failpoint == "after_generation_publish":
                _abort("synthetic_asset_quantity_scale_failpoint")
            with _CanonicalReadBarrierV1(data_space):
                if _sha_file(canonical) != materialized["canonical_fingerprint"]:
                    _abort("asset_quantity_scale_preview_stale")
                if failpoint == "before_active_replace":
                    _abort("synthetic_asset_quantity_scale_failpoint")
                _atomic_json_replace(area / ACTIVE_NAME, {
                    "contract_version": 1,
                    "generation_ref": generation_ref,
                    "ledger_fingerprint": ledger_fingerprint,
                    "manifest_fingerprint": _sha_file(final / MANIFEST_NAME),
                })
            if failpoint == "after_active_replace":
                _abort("synthetic_asset_quantity_scale_failpoint")
            verified = _binding(data_space, context)
            if verified.get("generation_ref") != generation_ref:
                _abort("asset_quantity_scale_publication_failed")
            return _result_from_receipt(receipt_body, "committed")
        finally:
            if not published and staging.exists():
                shutil.rmtree(staging, ignore_errors=True)


def list_pending_desktop_asset_quantity_scale_revisions_v1(
    canonical_path: str | Path,
    data_space_path: str | Path,
    context_value: Any,
) -> dict[str, Any]:
    context = _runtime(context_value)
    canonical = _scale_file(canonical_path)
    data_space = _scale_directory(data_space_path)
    area_path = data_space / PRODUCT_AREA
    if not area_path.exists():
        return {
            "status": "available",
            "candidates": [],
            "path_exposed": False,
            "internal_id_exposed": False,
        }
    area = _scale_directory(area_path)
    candidates = []
    # Ein Versuch, dessen Katalogzustand nicht mehr zum Plan passt, ist ueberholt:
    # Der Katalog ist seit dem Versuch weitergezogen, meist weil die Skala auf
    # einem anderen Weg angehoben wurde. Fruehere Fassungen liessen _catalog_state
    # dafuer abbrechen; damit riss ein einziger liegengebliebener Versuch die ganze
    # Liste mit und die Skalenkarte war nicht mehr bedienbar. Solche Versuche
    # werden gezaehlt, nicht gemeldet (dieselbe Linie wie bei der Korrekturhistorie).
    superseded = 0
    # Quittungen und Bindung einmal lesen, nicht je Versuch: Die Bindung prueft
    # das ganze Ledger, und jede Suche lief ueber alle Generationen. Bei vielen
    # Versuchen und Generationen dauerte die Liste
    # viele Sekunden.
    receipts_by_plan = _generation_receipts_by_plan(area)
    active_binding: list[dict[str, Any]] = []
    for _, attempt in _attempts(area, context):
        plan = attempt["plan_fingerprint"]
        if _no_generation_receipt(area, plan) is not None:
            continue
        completed_generations = receipts_by_plan.get(plan, [])
        if len(completed_generations) > 1:
            _abort("asset_quantity_scale_generation_conflict")
        if completed_generations:
            receipt = completed_generations[0][1]
            if not active_binding:
                active_binding.append(_binding(data_space, context))
            binding = active_binding[0]
            if binding.get("generation_ref") == receipt["generation_ref"]:
                continue
            # Nur wenn die Bindung genau auf der Vorgaengergeneration steht, ist
            # der Vorgang wirklich fortzuschreiben - genau das akzeptiert
            # finalize. Fruehere Fassungen meldeten jeden Vorgang wieder als
            # offen, sobald spaeter weitere Generationen entstanden waren; nach
            # einer Reihe von Anhebungen bot die Karte dann fast alle schon
            # abgeschlossenen Vorgaenge erneut zur Wiederaufnahme an, obwohl
            # finalize sie mit asset_quantity_scale_generation_conflict abwies
            # (Scheinkandidaten nach jeder Anhebung).
            if binding.get("generation_ref") != receipt["prior_generation_ref"]:
                superseded += 1
                continue
            state = "pending_generation_finalize"
        else:
            try:
                state, _ = _catalog_state(canonical, context, attempt)
            except DesktopAssetQuantityScaleRevisionV1Error as error:
                if error.code != "asset_quantity_scale_catalog_conflict":
                    raise
                superseded += 1
                continue
        preview = attempt["trusted_preview"]
        resume_ref = "qsr_" + _fingerprint({
            "context_fingerprint": _context_fingerprint(context),
            "plan_fingerprint": plan,
        })[:32]
        candidates.append({
            "resume_ref": resume_ref,
            "status": state,
            "current_quantity_scale": preview["current_quantity_scale"],
            "proposed_quantity_scale": preview["proposed_quantity_scale"],
            "affected_fifo_world_count": preview["affected_fifo_world_count"],
            "plan_fingerprint": plan,
            "catalog_command": dict(attempt["catalog_command"]),
        })
    candidates.sort(key=lambda row: row["resume_ref"])
    return {
        "status": "available",
        "candidates": candidates,
        "superseded_attempt_count": superseded,
        "path_exposed": False,
        "internal_id_exposed": False,
    }


__all__ = [
    "DesktopAssetQuantityScaleRevisionResultV1",
    "DesktopAssetQuantityScaleRevisionV1Error",
    "begin_desktop_asset_quantity_scale_revision_v1",
    "build_desktop_asset_quantity_scale_confirmation_v1",
    "desktop_asset_quantity_scale_revision_v1_error_codes",
    "finalize_desktop_asset_quantity_scale_revision_v1",
    "list_pending_desktop_asset_quantity_scale_revisions_v1",
    "preview_desktop_asset_quantity_scale_revision_v1",
]
