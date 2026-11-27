"""Stable Portelyra transaction-only CSV import through normal schema-401 commands."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import csv
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

from migrations.reference.asset_activity_reference_v1 import (
    TOKEN as REFERENCE_TOKEN, AssetActivityReferenceV1Error, read_activity_references_v1, record_activity_references_v1, reconcile_reader_provenance_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    PRODUCT_AREA, DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error,
    _canonical_snapshot, _context, _context_fingerprint, _matching_native_command, _native_events, _owner_directory,
    _owner_file, _read_connection, apply_desktop_native_asset_activity_v1,
    preview_desktop_native_asset_activity_v1, read_desktop_product_asset_activity_binding_v1,
    read_desktop_product_per_asset_catalog_v1, resolve_desktop_asset_activity_time_v1,
)

CONTRACT_VERSION = 1
FORMAT_VERSION = "portelyra_asset_activity_csv_v1"
AREA = "asset-activity-csv-v1"
MAX_BYTES = 5 * 1024 * 1024
MAX_ROWS = 10000
HEADERS_V1 = (
    "format_version", "import_key", "row_key", "event_type", "asset_key", "account_key",
    "related_account_key", "source_asset_key", "event_time_evidence", "local_date", "local_time",
    "time_zone", "price_currency", "fee_currency", "fee_role", "amount_input_mode",
    "basis_evidence_mode", "quantity_decimal", "eligible_quantity_decimal", "unit_price_decimal",
    "gross_amount_decimal", "monetary_fee_decimal", "asset_fee_quantity_decimal",
    "provided_basis_decimal", "original_acquired_time_evidence", "original_acquired_local_date",
    "original_acquired_local_time", "original_acquired_time_zone", "movement_context_code",
)
# Belegangaben (#439): Transaktions-ID und Adresse der Gegenseite gehen in den Beleg-Speicher neben dem Bestand, nicht in die
# Buchung. Eine Datei ohne diese beiden Spalten (bisheriges Format) wird weiter gelesen; der Export schreibt sie immer.
REFERENCE_HEADERS = ("transaction_id", "counterparty_address")
HEADERS = HEADERS_V1 + REFERENCE_HEADERS
KEY = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")
DECIMAL = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
CHALLENGE = re.compile(r"^aic_[a-f0-9]{16,64}$")
FAILPOINTS = frozenset({None, "after_attempt", "after_row", "before_receipt"})
FAILURE_CODES = frozenset({
    "asset_activity_csv_attempt_conflict", "asset_activity_csv_boundary_failed",
    "asset_activity_csv_catalog_stale", "asset_activity_csv_confirmation_invalid",
    "asset_activity_csv_context_invalid", "asset_activity_csv_duplicate_conflict",
    "asset_activity_csv_header_invalid", "asset_activity_csv_input_invalid",
    "asset_activity_csv_mapping_required", "asset_activity_csv_plan_stale",
    "asset_activity_csv_receipt_conflict", "asset_activity_csv_row_blocked",
    "asset_activity_csv_source_invalid", "asset_activity_csv_source_too_large",
    "asset_activity_csv_storage_invalid", "synthetic_asset_activity_csv_failpoint",
})


class AssetActivityCsvImportV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES: raise ValueError("asset_activity_csv_error_code_unregistered")
        self.code = code; super().__init__(code)


@dataclass(frozen=True)
class AssetActivityCsvImportResultV1:
    status: str
    import_key: str
    row_count: int
    created_event_count: int
    already_committed_event_count: int
    generation_ref: str
    receipt_ref: str
    reference_status: str = "not_applicable"
    reference_written_count: int = 0
    reference_kept_count: int = 0
    provenance_status: str = "not_applicable"
    cash_imported: bool = False
    schema201_canonical_write: bool = False
    provider_access: bool = False
    network_access: bool = False


def asset_activity_csv_import_v1_error_codes() -> tuple[str, ...]: return tuple(sorted(FAILURE_CODES))

def _abort(code: str) -> None: raise AssetActivityCsvImportV1Error(code)

def _canonical(value: Any) -> bytes:
    try: return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    except Exception: _abort("asset_activity_csv_input_invalid")

def _fingerprint(value: Any) -> str: return hashlib.sha256(_canonical(value)).hexdigest()

def _sha_bytes(value: bytes) -> str: return hashlib.sha256(value).hexdigest()

def _runtime(value: Any) -> DesktopProductAssetActivityContextV1:
    try: return _context(value)
    except DesktopProductAssetActivityV1Error: _abort("asset_activity_csv_context_invalid")

_product_owner_file=_owner_file
_product_owner_directory=_owner_directory

def _owner_file(path: str|Path, code: str) -> Path:
    try:return _product_owner_file(path,"desktop_asset_activity_storage_invalid")
    except DesktopProductAssetActivityV1Error:_abort(code)

def _owner_directory(path: str|Path, create: bool=False) -> Path:
    try:return _product_owner_directory(path,create=create)
    except DesktopProductAssetActivityV1Error:_abort("asset_activity_csv_storage_invalid")

def _utc(value: Any) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None: _abort("asset_activity_csv_input_invalid")
    try: parsed=datetime.strptime(value,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError: _abort("asset_activity_csv_input_invalid")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value: _abort("asset_activity_csv_input_invalid")
    return value

def _offset(value: str, seconds: int) -> str:
    parsed=datetime.strptime(_utc(value),"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (parsed+timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")

def _source(path_value: str | Path) -> tuple[Path, bytes]:
    path=Path(path_value)
    try: metadata=path.stat(follow_symlinks=False); resolved=path.resolve(strict=True)
    except OSError: _abort("asset_activity_csv_source_invalid")
    if not path.is_absolute() or resolved!=path or path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_uid!=os.geteuid() or metadata.st_nlink!=1:
        _abort("asset_activity_csv_source_invalid")
    if metadata.st_size<1 or metadata.st_size>MAX_BYTES: _abort("asset_activity_csv_source_too_large")
    try: content=path.read_bytes()
    except OSError: _abort("asset_activity_csv_source_invalid")
    return resolved,content

def _text(value: str, *, optional: bool=False, maximum: int=160) -> str | None:
    if optional and value=="": return None
    if not isinstance(value,str) or not value or value!=value.strip() or len(value.encode())>maximum or any(ord(ch)<32 for ch in value): _abort("asset_activity_csv_row_blocked")
    return value

def _decimal(value: str, *, optional: bool=True) -> str | None:
    if optional and value=="": return None
    if not isinstance(value,str) or DECIMAL.fullmatch(value) is None or len(value)>80: _abort("asset_activity_csv_row_blocked")
    return value

def _parse(content: bytes) -> tuple[str,list[dict[str,str]]]:
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content: _abort("asset_activity_csv_source_invalid")
    try: text=content.decode("utf-8",errors="strict")
    except UnicodeDecodeError: _abort("asset_activity_csv_source_invalid")
    if "\r" in text: _abort("asset_activity_csv_source_invalid")
    try:
        reader=csv.DictReader(io.StringIO(text,newline=""),strict=True)
        fields=tuple(reader.fieldnames or ())
        if fields not in (HEADERS,HEADERS_V1): _abort("asset_activity_csv_header_invalid")
        rows=[]
        for ordinal,row in enumerate(reader,1):
            if None in row or set(row)!=set(fields) or any(value is None for value in row.values()): _abort("asset_activity_csv_row_blocked")
            rows.append({**{name:"" for name in REFERENCE_HEADERS},**row,"source_row_ordinal":ordinal})
    except AssetActivityCsvImportV1Error: raise
    except (csv.Error,UnicodeError): _abort("asset_activity_csv_source_invalid")
    if not rows or len(rows)>MAX_ROWS: _abort("asset_activity_csv_row_blocked")
    imports={row["import_key"] for row in rows}; keys=[row["row_key"] for row in rows]
    if len(imports)!=1 or any(KEY.fullmatch(value) is None for value in imports): _abort("asset_activity_csv_row_blocked")
    return next(iter(imports)),rows

def _area(data_space: Path) -> Path: return _owner_directory(data_space/AREA,create=True)

def _stage(area: Path, content: bytes) -> Path:
    staged=_owner_directory(area/"staged",create=True);fingerprint=_sha_bytes(content);path=staged/(fingerprint+".csv")
    if path.exists():
        if _owner_file(path,"asset_activity_csv_storage_invalid").read_bytes()!=content: _abort("asset_activity_csv_storage_invalid")
        return path
    try:
        descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(descriptor,"wb") as handle: handle.write(content);handle.flush();os.fsync(handle.fileno())
        os.chmod(path,0o600)
    except OSError: _abort("asset_activity_csv_storage_invalid")
    return path

def _read_attempt(path: Path) -> dict[str,Any]:
    try:value=json.loads(path.read_text(encoding="utf-8"))
    except Exception:_abort("asset_activity_csv_attempt_conflict")
    body=dict(value) if isinstance(value,dict) else {};fingerprint=body.pop("attempt_fingerprint",None)
    required={"asset_activity_csv_attempt_version","attempt_status","challenge_ref","context_fingerprint","plan_fingerprint","confirmation_fingerprint","confirmation","attempted_at_utc","attempt_fingerprint"}
    if (not isinstance(value,dict) or set(value)!=required or path.read_bytes()!=_canonical(value)+b"\n"
        or value.get("asset_activity_csv_attempt_version")!=1 or value.get("attempt_status")!="consumed_before_domain_write"
        or fingerprint!=_fingerprint(body) or value.get("confirmation_fingerprint")!=value.get("confirmation",{}).get("confirmation_fingerprint")):_abort("asset_activity_csv_attempt_conflict")
    return value


class _RowProblem(Exception):
    """A named, row-local reason. The batch stays all-or-nothing; the row is reported, never dropped."""
    def __init__(self, reason_code: str, field: str|None=None):
        self.reason_code=reason_code; self.field=field; super().__init__(reason_code)

def _row_text(row: Mapping[str,Any], field: str, *, optional: bool=False, maximum: int=160) -> str|None:
    try: return _text(row[field],optional=optional,maximum=maximum)
    except AssetActivityCsvImportV1Error: raise _RowProblem("value_invalid",field) from None

def _row_decimal(row: Mapping[str,Any], field: str) -> str|None:
    try: return _decimal(row[field])
    except AssetActivityCsvImportV1Error: raise _RowProblem("decimal_invalid",field) from None

def _structure_problems(rows: Sequence[Mapping[str,Any]]) -> dict[int,_RowProblem]:
    problems={};seen=set()
    for row in rows:
        ordinal=row["source_row_ordinal"]
        if row["format_version"]!=FORMAT_VERSION: problems[ordinal]=_RowProblem("format_version_invalid","format_version")
        elif KEY.fullmatch(row["row_key"]) is None: problems[ordinal]=_RowProblem("row_key_invalid","row_key")
        elif row["row_key"] in seen: problems[ordinal]=_RowProblem("row_key_duplicate","row_key")
        seen.add(row["row_key"])
    return problems

DECIMAL_FIELDS=("quantity_decimal","eligible_quantity_decimal","unit_price_decimal","gross_amount_decimal","monetary_fee_decimal","asset_fee_quantity_decimal","provided_basis_decimal")

def _spreadsheet_damage(anchor: Mapping[str,Any], event: Mapping[str,Any]) -> str|None:
    """Returns the first decimal field a spreadsheet typically corrupts: a decimal point read as
    thousands separator (0.495 -> 495) or digits rounded away. None if other fields differ too."""
    changed=[key for key in anchor if key!="event_ref" and anchor[key]!=event.get(key)]
    if not changed or any(key not in DECIMAL_FIELDS for key in changed):return None
    for key in changed:
        old,new=anchor[key],event.get(key)
        if not isinstance(old,str) or not isinstance(new,str):return None
        thousands=new==old.replace(".","").lstrip("0")
        try:rounded=abs(float(old)-float(new))<=abs(float(old))*1e-6 or (("." in old) and len(new)<len(old) and old.startswith(new.rstrip("0").rstrip(".")))
        except ValueError:return None
        if not (thousands or rounded):return None
    return changed[0]

def asset_activity_csv_event_ref_v1(context: DesktopProductAssetActivityContextV1, import_key: str, row_key: str) -> str:
    """Event reference of an imported row: fixed by import series and row key, so importers can attach evidence after booking."""
    return "evt_"+_fingerprint({"context":_context_fingerprint(context),"import_key":import_key,"row_key":row_key})[:48]

def _export_row_key(context: DesktopProductAssetActivityContextV1, event_ref: str) -> str:
    return "bestand_"+_fingerprint({"context":_context_fingerprint(context),"event_ref":event_ref})[:16]

# Cash fuehrt die Cash-Abdeckung ueber Tagessalden, Indizes sind kein Bestand.
UNSUPPORTED_ASSET_TYPES=frozenset({"cash","index"})

def _catalog(canonical: Path,context: DesktopProductAssetActivityContextV1,portfolio_id: str) -> dict[str,Any]:
    try:
        value=read_desktop_product_per_asset_catalog_v1(canonical,context)
        snapshot=_canonical_snapshot(canonical,context)
    except DesktopProductAssetActivityV1Error: _abort("asset_activity_csv_catalog_stale")
    portfolios=[row for row in value["portfolios"] if row["portfolio_id"]==portfolio_id]
    if len(portfolios)!=1: _abort("asset_activity_csv_catalog_stale")
    accounts=[row for row in value["accounts"] if row["portfolio_id"]==portfolio_id]
    # Derivate buchen wie Aktien (Kauf legt ein Los an, Verkauf verbraucht es; rc.207 im FIFO, rc.225 Skala, rc.346 hier):
    # Die Sperre stammte aus dem ersten CSV-Import und blieb stehen, als FIFO und Skala sie aufhoben.
    excluded_asset_labels=sorted(
        row["display_name"] for row in snapshot["assets"]
        if row["status"]=="active" and row["asset_type"] in UNSUPPORTED_ASSET_TYPES
    )
    assets=[row for row in value["assets"] if row.get("status","active")=="active"]
    body={"portfolio":portfolios[0],"accounts":accounts,"assets":assets,"excluded_asset_labels":excluded_asset_labels};body["catalog_fingerprint"]=_fingerprint(body);return body

def _source_keys(kind: str, rows: Sequence[Mapping[str,Any]]) -> dict[str,str]:
    """Owner-visible CSV key per catalog row: the label, or for equal labels "label · k von n".
    Deterministic, so an export maps back to exactly the same rows without exposing IDs."""
    groups: dict[str,list[str]]={}
    for row in rows:groups.setdefault(row["label"],[]).append(row[f"{kind}_id"])
    keys={}
    for label,identifiers in groups.items():
        ordered=sorted(identifiers)
        for index,identifier in enumerate(ordered,1):keys[identifier]=label if len(ordered)==1 else f"{label} · {index} von {len(ordered)}"
    return keys

def _mapping_items(kind: str, keys: set[str], rows: Sequence[Mapping[str,Any]], context: DesktopProductAssetActivityContextV1) -> tuple[list[dict[str,Any]],dict[str,str]]:
    choices=[];refs={};source_keys=_source_keys(kind,rows)
    for key in sorted(keys):
        candidates=[];matching_refs=[]
        for row in rows:
            identifier=row[f"{kind}_id"];ref="map_"+_fingerprint({"context":_context_fingerprint(context),"kind":kind,"key":key,"id":identifier})[:32]
            refs[ref]=identifier;candidates.append({"mapping_ref":ref,"label":row["label"],"type":row[f"{kind}_type"]})
            if row["label"]==key or source_keys[identifier]==key: matching_refs.append(ref)
        choices.append({"source_key":key,"mapping_status":"auto_unique" if len(matching_refs)==1 else "mapping_required","auto_mapping_ref":matching_refs[0] if len(matching_refs)==1 else None,"choices":candidates})
    return choices,refs


def inspect_asset_activity_csv_v1(source_path: str|Path,canonical_path: str|Path,data_space_path: str|Path,context_value:Any,portfolio_id:str) -> dict[str,Any]:
    context=_runtime(context_value);data_space=_owner_directory(data_space_path);canonical=_owner_file(canonical_path,"asset_activity_csv_storage_invalid");_,content=_source(source_path);import_key,rows=_parse(content);area=_area(data_space);staged=_stage(area,content);catalog=_catalog(canonical,context,portfolio_id)
    usable=lambda value: bool(value) and value==value.strip() and len(value.encode())<=160 and not any(ord(ch)<32 for ch in value)
    asset_keys={value for row in rows for value in (row["asset_key"],row["source_asset_key"]) if usable(value)}
    account_keys={value for row in rows for value in (row["account_key"],row["related_account_key"]) if usable(value)}
    asset_mappings,asset_refs=_mapping_items("asset",asset_keys,catalog["assets"],context);account_mappings,account_refs=_mapping_items("account",account_keys,catalog["accounts"],context)
    source_fingerprint=_sha_bytes(content)
    receipt_area=_owner_directory(area/"receipts",create=True);prior_receipts=[]
    for receipt_path in sorted(receipt_area.glob("*.json")):
        receipt_path=_owner_file(receipt_path,"asset_activity_csv_receipt_conflict")
        try: receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception: _abort("asset_activity_csv_receipt_conflict")
        receipt_body=dict(receipt);receipt_fingerprint=receipt_body.pop("receipt_fingerprint",None)
        if receipt_path.read_bytes()!=_canonical(receipt)+b"\n" or receipt_fingerprint!=_fingerprint(receipt_body):_abort("asset_activity_csv_receipt_conflict")
        if receipt.get("import_key")==import_key: prior_receipts.append(receipt)
    # One import series may be extended over time (export, add rows, reimport).
    # Only an exactly repeated file or an unfinished confirmed plan changes the status.
    replay_status="new";receipt_plans={receipt.get("plan_fingerprint") for receipt in prior_receipts}
    if any(receipt.get("source_fingerprint")==source_fingerprint for receipt in prior_receipts):replay_status="already_imported"
    else:
        attempt_plans=set();attempts_path=area/"attempts"
        if attempts_path.exists():
            for attempt_path in sorted(_owner_directory(attempts_path).glob("*.json")):
                attempt=_read_attempt(_owner_file(attempt_path,"asset_activity_csv_attempt_conflict"))
                if attempt.get("context_fingerprint")!=_context_fingerprint(context):_abort("asset_activity_csv_attempt_conflict")
                attempt_plans.add(attempt["plan_fingerprint"])
        prior_plans=[];plans_path=area/"plans"
        if plans_path.exists():
            for plan_path in sorted(_owner_directory(plans_path).glob("*.json")):
                plan_path=_owner_file(plan_path,"asset_activity_csv_storage_invalid")
                try:prior_plan=json.loads(plan_path.read_text(encoding="utf-8"))
                except Exception:_abort("asset_activity_csv_storage_invalid")
                plan_body=dict(prior_plan);plan_fingerprint=plan_body.pop("plan_fingerprint",None)
                if (plan_path.read_bytes()!=_canonical(prior_plan)+b"\n" or plan_fingerprint!=_fingerprint(plan_body)
                    or prior_plan.get("context_fingerprint")!=_context_fingerprint(context)):_abort("asset_activity_csv_storage_invalid")
                if prior_plan.get("import_key")==import_key and plan_fingerprint in attempt_plans and plan_fingerprint not in receipt_plans:prior_plans.append(prior_plan)
        if prior_plans:
            if len({row["source_fingerprint"] for row in prior_plans})>1:_abort("asset_activity_csv_duplicate_conflict")
            replay_status="resumable" if prior_plans[0]["source_fingerprint"]==source_fingerprint else "changed_reupload"
    trusted={"asset_activity_csv_inspection_version":1,"context_fingerprint":_context_fingerprint(context),"portfolio_id":portfolio_id,"catalog_fingerprint":catalog["catalog_fingerprint"],"source_fingerprint":source_fingerprint,"staged_path":str(staged),"import_key":import_key,"rows":rows,"asset_mappings":asset_mappings,"account_mappings":account_mappings,"asset_mapping_refs":asset_refs,"account_mapping_refs":account_refs,"replay_status":replay_status}
    trusted["inspection_fingerprint"]=_fingerprint(trusted)
    inspection_status=replay_status if replay_status!="new" else ("mapping_required" if any(row["mapping_status"]=="mapping_required" for row in asset_mappings+account_mappings) else "ready_for_preview")
    public={"asset_activity_csv_inspection_public_version":1,"status":inspection_status,"import_key":import_key,"row_count":len(rows),"asset_mappings":asset_mappings,"account_mappings":account_mappings,"cash_row_count":0,"provider_access":False,"network_access":False,"path_exposed":False,"internal_id_exposed":False,"inspection_ref":"aci_"+trusted["inspection_fingerprint"][:32]}
    return {"public_inspection":public,"trusted_inspection":trusted}

def _resolve_mappings(trusted:Mapping[str,Any],selection:Mapping[str,Any]) -> tuple[dict[str,str],dict[str,str]]:
    if not isinstance(selection,Mapping) or set(selection)!={"assets","accounts"} or not all(isinstance(selection[k],Mapping) for k in selection): _abort("asset_activity_csv_mapping_required")
    resolved=[]
    for kind in ("asset","account"):
        definitions=trusted[f"{kind}_mappings"];allowed=trusted[f"{kind}_mapping_refs"];chosen={}
        if set(selection[kind+"s"])!={row["source_key"] for row in definitions}: _abort("asset_activity_csv_mapping_required")
        for item in definitions:
            ref=selection[kind+"s"][item["source_key"]] or item["auto_mapping_ref"]
            item_refs={choice["mapping_ref"] for choice in item["choices"]}
            if ref not in allowed or ref not in item_refs: _abort("asset_activity_csv_mapping_required")
            chosen[item["source_key"]]=allowed[ref]
        resolved.append(chosen)
    return resolved[0],resolved[1]

def _row_references(row:Mapping[str,Any]) -> dict[str,str|None]|None:
    """Transaktions-ID und Adresse einer Zeile: je eine zusammenhaengende Zeichenfolge ohne Leerzeichen, hoechstens 200 Zeichen."""
    given={}
    for field in REFERENCE_HEADERS:
        value=row.get(field,"")
        if value=="":given[field]=None;continue
        if not isinstance(value,str) or REFERENCE_TOKEN.fullmatch(value) is None:raise _RowProblem("value_invalid",field)
        given[field]=value
    return given if any(given.values()) else None

def _after_booking(data_space:Path,context:DesktopProductAssetActivityContextV1,plan:Mapping[str,Any],at:str) -> dict[str,Any]:
    """Nach jedem Buchen eines Plans - erstmals, fortgesetzt oder schon gebucht: Belegangaben und Herkunft je Buchung (rc.378). Die
    Herkunft stammt aus den Absichten, die beim Vorbereiten festgehalten wurden; gebucht ist schon, ein Fehler wird gemeldet."""
    result=_record_references(data_space,context,plan.get("references") or [],at)
    try:
        reconciled=reconcile_reader_provenance_v1(data_space,context,at,[row["event"]["event_ref"] for row in plan["rows"]])
        status="recorded" if reconciled["written_count"] else ("pending" if reconciled["pending_count"] else "not_applicable")
    except AssetActivityReferenceV1Error as error:
        status="failed:"+error.code
    return {**result,"provenance_status":status}


def _record_references(data_space:Path,context:DesktopProductAssetActivityContextV1,entries:Sequence[Mapping[str,Any]],at:str) -> dict[str,Any]:
    """Nur in leere Felder (wie das Nachtragen aus Belegen): Was an der Buchung schon steht, bleibt; die Notiz bleibt immer.
    Die Buchungen stehen an dieser Stelle; Angaben zu einer Buchung, die es nicht gibt, werden nicht geschrieben."""
    if not entries:return {"reference_status":"not_applicable","reference_written_count":0,"reference_kept_count":0}
    try:
        current=read_activity_references_v1(data_space,context,[entry["event_ref"] for entry in entries])["references"]
        booked={row["event_ref"] for row in _existing_event_rows(read_desktop_product_asset_activity_binding_v1(data_space,context))}
        wanted,kept=[],0
        for entry in entries:
            if entry["event_ref"] not in booked:continue
            before=current.get(entry["event_ref"]) or {}
            merged={field:before.get(field) or entry.get(field) for field in REFERENCE_HEADERS}
            if all(merged[field]==before.get(field) for field in REFERENCE_HEADERS):kept+=1;continue
            wanted.append({"event_ref":entry["event_ref"],**merged,"note":before.get("note")})
        written=record_activity_references_v1(data_space,context,wanted,"owner_entered",at,True)["written_count"] if wanted else 0
        return {"reference_status":"recorded","reference_written_count":written,"reference_kept_count":kept}
    except (AssetActivityReferenceV1Error,DesktopProductAssetActivityV1Error,OSError):
        # Die Buchungen sind geschrieben; der Import bleibt gelungen, gemeldet wird nur der Zustand der Angaben.
        return {"reference_status":"failed","reference_written_count":0,"reference_kept_count":0}

def _row_event(row:Mapping[str,Any],assets:Mapping[str,str],accounts:Mapping[str,str],catalog:Mapping[str,Any],context:DesktopProductAssetActivityContextV1) -> dict[str,Any]:
    """Builds the native event candidate. Validation that only matters for new rows follows in _new_row_checks."""
    event_type=_row_text(row,"event_type");event_time=_row_text(row,"event_time_evidence");local_date=_row_text(row,"local_date",maximum=10);local_time=_row_text(row,"local_time",optional=True,maximum=8);zone=_row_text(row,"time_zone",maximum=80)
    if event_time=="exact":
        if local_time is None:raise _RowProblem("time_invalid","local_time")
        try: effective=resolve_desktop_asset_activity_time_v1(local_date,local_time,zone)["effective_at_utc"]
        except DesktopProductAssetActivityV1Error:raise _RowProblem("time_invalid","local_time") from None
    elif event_time=="date_only" and local_time is None: effective=None
    else:raise _RowProblem("time_invalid","event_time_evidence")
    original_mode=_row_text(row,"original_acquired_time_evidence");original_date=_row_text(row,"original_acquired_local_date",optional=True,maximum=10);original_time=_row_text(row,"original_acquired_local_time",optional=True,maximum=8);original_zone=_row_text(row,"original_acquired_time_zone",optional=True,maximum=80)
    if original_mode=="exact":
        if None in (original_date,original_time,original_zone):raise _RowProblem("original_time_invalid","original_acquired_time_evidence")
        try: original_utc=resolve_desktop_asset_activity_time_v1(original_date,original_time,original_zone)["effective_at_utc"]
        except DesktopProductAssetActivityV1Error:raise _RowProblem("original_time_invalid","original_acquired_local_time") from None
    elif original_mode=="date_only" and original_date is not None and original_time is None and original_zone is not None:original_utc=None
    elif original_mode=="not_applicable" and original_date is None and original_time is None and original_zone is None:original_utc=None
    else:raise _RowProblem("original_time_invalid","original_acquired_time_evidence")
    for field,mapping in (("asset_key",assets),("account_key",accounts)):
        if row[field] not in mapping:raise _RowProblem("value_invalid",field)
    for field,mapping in (("related_account_key",accounts),("source_asset_key",assets)):
        if row[field]!="" and row[field] not in mapping:raise _RowProblem("value_invalid",field)
    ref=asset_activity_csv_event_ref_v1(context,row["import_key"],row["row_key"])
    return {"event_ref":ref,"event_type":event_type,"account_ref":accounts[row["account_key"]],"related_account_ref":None if row["related_account_key"]=="" else accounts[row["related_account_key"]],"asset_ref":assets[row["asset_key"]],"source_asset_ref":None if row["source_asset_key"]=="" else assets[row["source_asset_key"]],"event_time_evidence":event_time,"local_date":local_date,"local_time":local_time,"time_zone":zone,"effective_at_utc":effective,"original_acquired_time_evidence":original_mode,"original_acquired_local_date":original_date,"original_acquired_local_time":original_time,"original_acquired_time_zone":original_zone,"original_acquired_at_utc":original_utc,"amount_input_mode":_row_text(row,"amount_input_mode"),"basis_evidence_mode":_row_text(row,"basis_evidence_mode"),"quantity_decimal":_row_decimal(row,"quantity_decimal"),"eligible_quantity_decimal":_row_decimal(row,"eligible_quantity_decimal"),"unit_price_decimal":_row_decimal(row,"unit_price_decimal"),"gross_amount_decimal":_row_decimal(row,"gross_amount_decimal"),"monetary_fee_decimal":_row_decimal(row,"monetary_fee_decimal"),"asset_fee_quantity_decimal":_row_decimal(row,"asset_fee_quantity_decimal"),"provided_basis_decimal":_row_decimal(row,"provided_basis_decimal"),"movement_context_code":_row_text(row,"movement_context_code")}

def _new_row_checks(row:Mapping[str,Any],event:Mapping[str,Any],catalog:Mapping[str,Any],allowed_types:set[str]|None=None) -> dict[str,Any]:
    asset=next(item for item in catalog["assets"] if item["asset_id"]==event["asset_ref"]);price_currency=_row_text(row,"price_currency",maximum=3)
    if asset["asset_type"] in UNSUPPORTED_ASSET_TYPES or asset["label"] in catalog["excluded_asset_labels"]:raise _RowProblem("asset_type_unsupported","asset_key")
    # Umfang je Portfolio (#551, Festlegung 11.11.2026): eine neue Zeile einer im Portfolio nicht gewaehlten Klasse sperrt mit Grund
    # (Alles-oder-nichts bleibt); dazunehmen ueber den Umfang oder die Zeile aus der Datei entfernen.
    if allowed_types is not None and asset["asset_type"] not in allowed_types:raise _RowProblem("asset_class_not_selected","asset_key")
    if CURRENCY.fullmatch(price_currency) is None or price_currency!=asset["price_currency"] or price_currency!=catalog["portfolio"]["base_currency"]:raise _RowProblem("currency_mismatch","price_currency")
    monetary=event["monetary_fee_decimal"];asset_fee=event["asset_fee_quantity_decimal"];fee_role=_row_text(row,"fee_role");fee_currency=_row_text(row,"fee_currency",optional=True,maximum=8)
    if (fee_role=="none" and (fee_currency is not None or monetary is not None or asset_fee is not None)) or (fee_role=="monetary" and (fee_currency!=price_currency or monetary is None or asset_fee is not None)) or (fee_role=="asset_quantity" and (fee_currency!="ASSET" or monetary is not None or asset_fee is None)) or fee_role not in {"none","monetary","asset_quantity"}:raise _RowProblem("fee_invalid","fee_role")
    try:return _native_events([dict(event)])[0]
    except DesktopProductAssetActivityV1Error:raise _RowProblem("event_invalid","event_type") from None

def _existing_events(binding:Mapping[str,Any]) -> dict[str,dict[str,Any]]:
    if binding.get("status")!="available":return {}
    connection=_read_connection(Path(binding["ledger_path"]))
    try:rows=[dict(row) for row in connection.execute("SELECT * FROM current_asset_activity_event")]
    finally:connection.close()
    result={}
    for row in rows:
        value={key:row[key] for key in _native_events.__globals__["NATIVE_EVENT_KEYS"] if key not in {"account_ref","related_account_ref","asset_ref","source_asset_ref"}}
        value.update(account_ref=row["account_id"],related_account_ref=row["related_account_id"],asset_ref=row["asset_id"],source_asset_ref=row["source_asset_id"]);result[row["event_ref"]]=value
    return result

def _existing_event_rows(binding:Mapping[str,Any]) -> list[dict[str,Any]]:
    if binding.get("status")!="available":return []
    connection=_read_connection(Path(binding["ledger_path"]))
    try:return [dict(row) for row in connection.execute("SELECT * FROM current_asset_activity_event ORDER BY local_date, effective_at_utc IS NOT NULL, effective_at_utc, event_ref")]
    finally:connection.close()

def _semantic(event:Mapping[str,Any]) -> dict[str,Any]:return {key:value for key,value in event.items() if key!="event_ref"}

def _empty_effect() -> dict[str,Any]:
    return {"inventory_effect_code":None,"fifo_effect_code":None,"portfolio_quantity_change_decimal":None,"fifo_basis_created_decimal":None,"net_trade_proceeds_decimal":None,"realized_gain_before_tax":None,"gross_income_decimal":None}

def _row_status(row:Mapping[str,Any],status:str,reason:_RowProblem|None=None,effect:Mapping[str,Any]|None=None) -> dict[str,Any]:
    value={"row_key":row["row_key"],"source_row_ordinal":row["source_row_ordinal"],"event_type":row["event_type"],"local_date":row["local_date"],"asset_key":row["asset_key"],"account_key":row["account_key"],"status":status,"reason_code":None if reason is None else reason.reason_code,"reason_field":None if reason is None else reason.field,"cash_posting_count":0}
    value.update(_empty_effect() if effect is None else effect);return value

def _public_effect(row:Mapping[str,Any],preview:Mapping[str,Any]) -> dict[str,Any]:
    return _row_status(row,"ready",effect={"inventory_effect_code":preview["inventory_effect_code"],"fifo_effect_code":preview["fifo_effect_code"],"portfolio_quantity_change_decimal":preview["portfolio_quantity_change_decimal"],"fifo_basis_created_decimal":preview["fifo_basis_created_decimal"],"net_trade_proceeds_decimal":preview["net_trade_proceeds_decimal"],"realized_gain_before_tax":preview["event_result"]["realized_gross_gain_decimal"],"gross_income_decimal":preview["gross_income_decimal"]})

def _write_plan(area:Path,plan:dict[str,Any]) -> Path:
    plans=_owner_directory(area/"plans",create=True);path=plans/(plan["plan_fingerprint"]+".json");content=_canonical(plan)+b"\n"
    if path.exists():
        if _owner_file(path,"asset_activity_csv_storage_invalid").read_bytes()!=content:_abort("asset_activity_csv_storage_invalid")
        return path
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(fd,"wb") as handle:handle.write(content);handle.flush();os.fsync(handle.fileno())
        os.chmod(path,0o600)
    except OSError:_abort("asset_activity_csv_storage_invalid")
    return path

def preview_asset_activity_csv_import_v1(trusted_inspection:Mapping[str,Any],mapping_selection:Mapping[str,Any],canonical_path:str|Path,data_space_path:str|Path,context_value:Any,previewed_at_utc:str) -> dict[str,Any]:
    """Classifies every row as unchanged, ready or blocked. Any blocked row blocks the whole batch
    (all-or-nothing) and is named; unchanged rows (exported or previously imported) write nothing."""
    context=_runtime(context_value);at=_utc(previewed_at_utc);data_space=_owner_directory(data_space_path);canonical=_owner_file(canonical_path,"asset_activity_csv_storage_invalid")
    if not isinstance(trusted_inspection,Mapping) or trusted_inspection.get("context_fingerprint")!=_context_fingerprint(context):_abort("asset_activity_csv_input_invalid")
    if trusted_inspection.get("replay_status") not in {"new","already_imported"}:_abort("asset_activity_csv_duplicate_conflict")
    inspection=dict(trusted_inspection);fp=inspection.pop("inspection_fingerprint",None)
    if fp!=_fingerprint(inspection):_abort("asset_activity_csv_input_invalid")
    staged=_owner_file(trusted_inspection["staged_path"],"asset_activity_csv_storage_invalid");content=staged.read_bytes();import_key,source_rows=_parse(content)
    if _sha_bytes(content)!=trusted_inspection["source_fingerprint"] or source_rows!=trusted_inspection["rows"] or import_key!=trusted_inspection["import_key"]:_abort("asset_activity_csv_source_invalid")
    catalog=_catalog(canonical,context,trusted_inspection["portfolio_id"])
    if catalog["catalog_fingerprint"]!=trusted_inspection["catalog_fingerprint"]:_abort("asset_activity_csv_catalog_stale")
    assets,accounts=_resolve_mappings(trusted_inspection,mapping_selection)
    from migrations.reference import portfolio_configuration_v1 as scope_configuration  # noqa: PLC0415
    scope=scope_configuration.import_scope_v1(data_space,trusted_inspection["portfolio_id"],context);allowed_types=set(scope["asset_types"])
    binding=read_desktop_product_asset_activity_binding_v1(data_space,context);existing=_existing_events(binding)
    exported={_export_row_key(context,ref):event for ref,event in existing.items()}
    # Belegangaben zaehlen fuer den Status nur, wenn eine davon ein leeres Feld fuellt (rc.440): sonst war ein zweiter Import derselben Datei
    # nie „nichts zu tun“. Die Liste bleibt vollstaendig, damit die Rueckmeldung „blieb“ (schon vorhandene Kennung) erhalten bleibt.
    try:stored_references=read_activity_references_v1(data_space,context,None)["references"]
    except AssetActivityReferenceV1Error:_abort("asset_activity_csv_storage_invalid")
    fills=lambda event_ref,given:any(value and not (stored_references.get(event_ref) or {}).get(field) for field,value in given.items())
    structure=_structure_problems(source_rows);statuses={};pending=[];references=[]
    for source_row in source_rows:
        ordinal=source_row["source_row_ordinal"]
        try:
            if ordinal in structure:raise structure[ordinal]
            event=_row_event(source_row,assets,accounts,catalog,context)
            given=_row_references(source_row)
            anchor=exported.get(source_row["row_key"]) if source_row["row_key"].startswith("bestand_") else existing.get(event["event_ref"])
            if anchor is not None:
                if _semantic(anchor)!=_semantic(event):
                    damaged=_spreadsheet_damage(anchor,event)
                    raise _RowProblem("spreadsheet_number_changed",damaged) if damaged else _RowProblem("conflict_changed","row_key")
                if given:references.append({"event_ref":anchor["event_ref"],**given})
                statuses[ordinal]=_row_status(source_row,"unchanged");continue
            if source_row["row_key"].startswith("bestand_"):raise _RowProblem("conflict_unknown_export","row_key")
            if any(_semantic(other)==_semantic(event) for other in existing.values()):raise _RowProblem("duplicate_existing",None)
            if given:references.append({"event_ref":event["event_ref"],**given})
            pending.append((source_row,_new_row_checks(source_row,event,catalog,allowed_types)))
        except _RowProblem as problem:statuses[ordinal]=_row_status(source_row,"blocked",problem)
    order=lambda item:(item[1]["local_date"],item[1]["effective_at_utc"] is not None,item[1]["effective_at_utc"] or "",item[1]["event_ref"])
    pending.sort(key=order);area=_area(data_space);trusted_rows=[];blocked=any(item["status"]=="blocked" for item in statuses.values())
    if pending and not blocked:
        with tempfile.TemporaryDirectory(prefix=".csv-preview-",dir=area) as temporary:
            simulation=Path(temporary);os.chmod(simulation,0o700);product=data_space/PRODUCT_AREA
            if product.exists():shutil.copytree(product,simulation/PRODUCT_AREA)
            # Gespeicherte Splits (#451, rc.372) gelten auch in der Simulation: sonst wiese sie jeden Verkauf in neuen Stuecken nach
            # einem Kauf in alten als zu gross ab.
            if (data_space/"stock-split-v1").is_dir() and not (data_space/"stock-split-v1").is_symlink():shutil.copytree(data_space/"stock-split-v1",simulation/"stock-split-v1")
            for ordinal,(source_row,event) in enumerate(pending,1):
                committed=_offset(at,ordinal)
                try:preview=preview_desktop_native_asset_activity_v1(canonical,simulation,context,trusted_inspection["portfolio_id"],[event]);result=apply_desktop_native_asset_activity_v1(canonical,simulation,context,trusted_inspection["portfolio_id"],[event],preview["preview_fingerprint"],committed);post=read_desktop_product_asset_activity_binding_v1(simulation,context)
                except DesktopProductAssetActivityV1Error:
                    # Later rows depend on this one; they stay unevaluated rather than guessed.
                    statuses[source_row["source_row_ordinal"]]=_row_status(source_row,"blocked",_RowProblem("simulation_failed",None));blocked=True;break
                statuses[source_row["source_row_ordinal"]]=_public_effect(source_row,preview);trusted_rows.append({"row_key":source_row["row_key"],"source_row_ordinal":source_row["source_row_ordinal"],"event":event,"expected_preview_fingerprint":preview["preview_fingerprint"],"committed_at_utc":committed,"expected_post_activity_set_fingerprint":post["activity_set_fingerprint"],"expected_generation_ref":result.generation_ref})
    for source_row,_ in pending:
        statuses.setdefault(source_row["source_row_ordinal"],_row_status(source_row,"not_evaluated"))
    rows=[statuses[row["source_row_ordinal"]] for row in source_rows]
    counts={name:sum(1 for row in rows if row["status"]==name) for name in ("ready","unchanged","blocked","not_evaluated")}
    asset_types={item["asset_id"]:item["asset_type"] for item in catalog["assets"]};scope_classes:dict[str,dict[str,Any]]={}
    for row in rows:
        if row["reason_code"]=="asset_class_not_selected":
            key,label=scope_configuration.class_of_v1(asset_types.get(assets.get(row["asset_key"]),"other"))
            scope_classes.setdefault(key,{"key":key,"label":label,"count":0})["count"]+=1
    # Nur Angaben zu gebuchten Zeilen (etwa eine Exportdatei mit nachgetragenen Kennungen): bestaetigt wird auch das.
    useful=any(fills(entry["event_ref"],{field:entry.get(field) for field in REFERENCE_HEADERS}) for entry in references)
    status="blocked" if blocked else ("ready_for_confirmation" if trusted_rows or useful else "nothing_to_import")
    public={"asset_activity_csv_preview_version":1,"status":status,"reference_row_count":0 if blocked else len(references),"import_key":import_key,"row_count":len(rows),"ready_row_count":0 if blocked else counts["ready"],"unchanged_row_count":counts["unchanged"],"blocked_row_count":counts["blocked"],"rows":rows,"scope_classes":sorted(scope_classes.values(),key=lambda item:item["label"]),"scope_portfolio_label":scope["label"],"confirmation_required":status=="ready_for_confirmation","batch_policy":"all_or_nothing_ordered_resumable_exact_subcommands","cash_imported":False,"schema201_canonical_write":False,"provider_access":False,"network_access":False,"path_exposed":False,"internal_id_exposed":False,"preview_ref":None}
    if status!="ready_for_confirmation":return {"public_preview":public,"trusted_plan":None}
    plan={"asset_activity_csv_plan_version":1,"context_fingerprint":_context_fingerprint(context),"portfolio_id":trusted_inspection["portfolio_id"],"import_key":import_key,"source_fingerprint":trusted_inspection["source_fingerprint"],"catalog_fingerprint":catalog["catalog_fingerprint"],"source_generation_ref":binding.get("generation_ref"),"source_activity_set_fingerprint":binding["activity_set_fingerprint"],"mapping_fingerprint":_fingerprint({"assets":assets,"accounts":accounts}),"rows":trusted_rows,"row_count":len(trusted_rows),"references":references,"previewed_at_utc":at,"cash_imported":False,"provider_access":False,"network_access":False}
    plan["plan_fingerprint"]=_fingerprint(plan);_write_plan(area,plan);public["preview_ref"]="aip_"+plan["plan_fingerprint"][:32]
    return {"public_preview":public,"trusted_plan":plan}


def export_asset_activity_csv_v1(canonical_path:str|Path,data_space_path:str|Path,context_value:Any,portfolio_id:str,asset_id:str|None,exported_at_utc:str) -> dict[str,Any]:
    """Exports current Asset Activity in the import format. Every row carries a keyed, non-reversible
    row key, so an unchanged reimport is recognised as unchanged and an edited row as a conflict."""
    context=_runtime(context_value);at=_utc(exported_at_utc);data_space=_owner_directory(data_space_path);canonical=_owner_file(canonical_path,"asset_activity_csv_storage_invalid")
    catalog=_catalog(canonical,context,portfolio_id);asset_rows={row["asset_id"]:row for row in catalog["assets"]};account_rows={row["account_id"]:row for row in catalog["accounts"]}
    if asset_id is not None and asset_id not in asset_rows:_abort("asset_activity_csv_input_invalid")
    binding=read_desktop_product_asset_activity_binding_v1(data_space,context)
    events=[row for row in _existing_event_rows(binding) if row["portfolio_id"]==portfolio_id and (asset_id is None or row["asset_id"]==asset_id)]
    import_key="export_"+at.replace("-","").replace(":","").lower()
    # Belegangaben (#439) gehen mit; eine Notiz nicht - sie ist Freitext und gehoert nicht in eine Tabellenspalte.
    try:stored=read_activity_references_v1(data_space,context,None)["references"]
    except AssetActivityReferenceV1Error:_abort("asset_activity_csv_storage_invalid")
    asset_keys=_source_keys("asset",catalog["assets"]);account_keys=_source_keys("account",catalog["accounts"])
    label=lambda keys,identifier:"" if identifier is None else keys[identifier]
    output=io.StringIO(newline="");writer=csv.DictWriter(output,fieldnames=HEADERS,lineterminator="\n",quoting=csv.QUOTE_MINIMAL);writer.writeheader();skipped=0
    for event in events:
        if event["asset_id"] not in asset_rows or event["account_id"] not in account_rows or (event["related_account_id"] is not None and event["related_account_id"] not in account_rows) or (event["source_asset_id"] is not None and event["source_asset_id"] not in asset_rows):
            skipped+=1;continue
        price_currency=asset_rows[event["asset_id"]]["price_currency"]
        fee_role="monetary" if event["monetary_fee_decimal"] is not None else ("asset_quantity" if event["asset_fee_quantity_decimal"] is not None else "none")
        value={name:"" for name in HEADERS};value.update(format_version=FORMAT_VERSION,import_key=import_key,row_key=_export_row_key(context,event["event_ref"]),event_type=event["event_type"],asset_key=label(asset_keys,event["asset_id"]),account_key=label(account_keys,event["account_id"]),related_account_key=label(account_keys,event["related_account_id"]),source_asset_key=label(asset_keys,event["source_asset_id"]),price_currency=price_currency,fee_currency={"monetary":price_currency,"asset_quantity":"ASSET","none":""}[fee_role],fee_role=fee_role)
        for name in ("event_time_evidence","local_date","local_time","time_zone","amount_input_mode","basis_evidence_mode","quantity_decimal","eligible_quantity_decimal","unit_price_decimal","gross_amount_decimal","monetary_fee_decimal","asset_fee_quantity_decimal","provided_basis_decimal","original_acquired_time_evidence","original_acquired_local_date","original_acquired_local_time","original_acquired_time_zone","movement_context_code"):
            value[name]="" if event[name] is None else str(event[name])
        given=stored.get(event["event_ref"]) or {}
        for name in REFERENCE_HEADERS:value[name]=given.get(name) or ""
        writer.writerow(value)
    text=output.getvalue()
    return {"asset_activity_csv_export_version":1,"import_key":import_key,"row_count":len(events)-skipped,"skipped_row_count":skipped,"content":text,"path_exposed":False,"internal_id_exposed":False}


def build_asset_activity_csv_confirmation_v1(plan:Mapping[str,Any],context_value:Any,challenge_ref:str,issued_at_utc:str,expires_at_utc:str) -> dict[str,Any]:
    context=_runtime(context_value);issued=_utc(issued_at_utc);expires=_utc(expires_at_utc)
    if not isinstance(plan,Mapping) or not isinstance(challenge_ref,str) or CHALLENGE.fullmatch(challenge_ref) is None or plan.get("context_fingerprint")!=_context_fingerprint(context) or issued>expires:_abort("asset_activity_csv_confirmation_invalid")
    body={"asset_activity_csv_confirmation_version":1,"challenge_ref":challenge_ref,"context_fingerprint":_context_fingerprint(context),"plan_fingerprint":plan.get("plan_fingerprint"),"issued_at_utc":issued,"expires_at_utc":expires};body["confirmation_fingerprint"]=_fingerprint(body);return body

def _attempt(area:Path,confirmation:Mapping[str,Any],at:str) -> None:
    attempts=_owner_directory(area/"attempts",create=True);path=attempts/(confirmation["challenge_ref"]+".json");body={"asset_activity_csv_attempt_version":1,"attempt_status":"consumed_before_domain_write","challenge_ref":confirmation["challenge_ref"],"context_fingerprint":confirmation["context_fingerprint"],"plan_fingerprint":confirmation["plan_fingerprint"],"confirmation_fingerprint":confirmation["confirmation_fingerprint"],"confirmation":dict(confirmation),"attempted_at_utc":at};body["attempt_fingerprint"]=_fingerprint(body);content=_canonical(body)+b"\n"
    if path.exists():
        if _owner_file(path,"asset_activity_csv_attempt_conflict").read_bytes()!=content:_abort("asset_activity_csv_attempt_conflict")
        return
    try:
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(fd,"wb") as handle:handle.write(content);handle.flush();os.fsync(handle.fileno())
        os.chmod(path,0o600)
    except OSError:_abort("asset_activity_csv_attempt_conflict")

def _receipt_path(area:Path,plan_fp:str) -> Path:return _owner_directory(area/"receipts",create=True)/(plan_fp+".json")
def apply_asset_activity_csv_import_v1(canonical_path:str|Path,data_space_path:str|Path,context_value:Any,plan:Mapping[str,Any],confirmation:Mapping[str,Any],applied_at_utc:str,*,failpoint:str|None=None) -> AssetActivityCsvImportResultV1:
    context=_runtime(context_value);at=_utc(applied_at_utc);data_space=_owner_directory(data_space_path);canonical=_owner_file(canonical_path,"asset_activity_csv_storage_invalid");area=_area(data_space)
    if failpoint not in FAILPOINTS or not isinstance(plan,Mapping) or plan.get("context_fingerprint")!=_context_fingerprint(context):_abort("asset_activity_csv_input_invalid")
    body=dict(plan);plan_fp=body.pop("plan_fingerprint",None)
    if plan_fp!=_fingerprint(body):_abort("asset_activity_csv_input_invalid")
    confirmation_body=dict(confirmation) if isinstance(confirmation,Mapping) else {};confirmation_fp=confirmation_body.pop("confirmation_fingerprint",None)
    if confirmation_fp!=_fingerprint(confirmation_body) or confirmation.get("context_fingerprint")!=_context_fingerprint(context) or confirmation.get("plan_fingerprint")!=plan_fp or at>confirmation.get("expires_at_utc",""):_abort("asset_activity_csv_confirmation_invalid")
    receipt_path=_receipt_path(area,plan_fp)
    if receipt_path.exists():
        receipt_file=_owner_file(receipt_path,"asset_activity_csv_receipt_conflict")
        try:receipt=json.loads(receipt_file.read_text())
        except Exception:_abort("asset_activity_csv_receipt_conflict")
        receipt_body=dict(receipt);receipt_fingerprint=receipt_body.pop("receipt_fingerprint",None)
        if receipt_file.read_bytes()!=_canonical(receipt)+b"\n" or receipt_fingerprint!=_fingerprint(receipt_body):_abort("asset_activity_csv_receipt_conflict")
        return AssetActivityCsvImportResultV1("already_imported",receipt["import_key"],receipt["row_count"],receipt["created_event_count"],0,receipt["generation_ref"],"air_"+plan_fp[:32],**_after_booking(data_space,context,plan,at))
    if not plan["rows"]:
        # Nur Angaben zu gebuchten Zeilen: keine Buchung, keine neue Generation, keine Quittung des Imports.
        catalog=_catalog(canonical,context,plan["portfolio_id"])
        if catalog["catalog_fingerprint"]!=plan["catalog_fingerprint"]:_abort("asset_activity_csv_catalog_stale")
        binding=read_desktop_product_asset_activity_binding_v1(data_space,context)
        if binding["activity_set_fingerprint"]!=plan["source_activity_set_fingerprint"]:_abort("asset_activity_csv_plan_stale")
        return AssetActivityCsvImportResultV1("references_recorded",plan["import_key"],0,0,0,binding.get("generation_ref") or "","air_"+plan_fp[:32],**_after_booking(data_space,context,plan,at))
    staged=_owner_file(area/"staged"/(plan["source_fingerprint"]+".csv"),"asset_activity_csv_storage_invalid")
    if _sha_bytes(staged.read_bytes())!=plan["source_fingerprint"]:_abort("asset_activity_csv_source_invalid")
    catalog=_catalog(canonical,context,plan["portfolio_id"])
    if catalog["catalog_fingerprint"]!=plan["catalog_fingerprint"]:_abort("asset_activity_csv_catalog_stale")
    _attempt(area,confirmation,at)
    if failpoint=="after_attempt":_abort("synthetic_asset_activity_csv_failpoint")
    binding=read_desktop_product_asset_activity_binding_v1(data_space,context);existing=_existing_events(binding);committed_prefix=0
    for row in plan["rows"]:
        event=row["event"]
        if event["event_ref"] not in existing:break
        if existing[event["event_ref"]]!=event:_abort("asset_activity_csv_duplicate_conflict")
        committed_prefix+=1
    if any(row["event"]["event_ref"] in existing for row in plan["rows"][committed_prefix:]):_abort("asset_activity_csv_plan_stale")
    expected_source=plan["source_activity_set_fingerprint"] if committed_prefix==0 else plan["rows"][committed_prefix-1]["expected_post_activity_set_fingerprint"]
    if binding["activity_set_fingerprint"]!=expected_source:_abort("asset_activity_csv_plan_stale")
    created=0
    for row in plan["rows"][committed_prefix:]:
        try:result=apply_desktop_native_asset_activity_v1(canonical,data_space,context,plan["portfolio_id"],[row["event"]],row["expected_preview_fingerprint"],row["committed_at_utc"]);binding=read_desktop_product_asset_activity_binding_v1(data_space,context)
        except DesktopProductAssetActivityV1Error:_abort("asset_activity_csv_plan_stale")
        if binding["activity_set_fingerprint"]!=row["expected_post_activity_set_fingerprint"] or binding["generation_ref"]!=row["expected_generation_ref"]:_abort("asset_activity_csv_plan_stale")
        created+=1
        if failpoint=="after_row":_abort("synthetic_asset_activity_csv_failpoint")
    if failpoint=="before_receipt":_abort("synthetic_asset_activity_csv_failpoint")
    receipt={"asset_activity_csv_receipt_version":1,"status":"completed","context_fingerprint":_context_fingerprint(context),"plan_fingerprint":plan_fp,"confirmation_fingerprint":confirmation["confirmation_fingerprint"],"import_key":plan["import_key"],"source_fingerprint":plan["source_fingerprint"],"row_count":plan["row_count"],"created_event_count":plan["row_count"],"generation_ref":binding["generation_ref"],"activity_set_fingerprint":binding["activity_set_fingerprint"],"completed_at_utc":at,"cash_imported":False,"schema201_canonical_write":False,"provider_access":False,"network_access":False};receipt["receipt_fingerprint"]=_fingerprint(receipt);content=_canonical(receipt)+b"\n"
    try:
        fd=os.open(receipt_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
        with os.fdopen(fd,"wb") as handle:handle.write(content);handle.flush();os.fsync(handle.fileno())
        os.chmod(receipt_path,0o600)
    except OSError:_abort("asset_activity_csv_receipt_conflict")
    return AssetActivityCsvImportResultV1("completed",plan["import_key"],plan["row_count"],created,committed_prefix,binding["generation_ref"],"air_"+plan_fp[:32],**_after_booking(data_space,context,plan,at))

def list_resumable_asset_activity_csv_imports_v1(data_space_path:str|Path,context_value:Any)->dict[str,Any]:
    context=_runtime(context_value);data_space=_owner_directory(data_space_path);area=_area(data_space);plans=area/"plans";attempts=area/"attempts";receipts=area/"receipts"
    if not plans.exists() or not attempts.exists():return {"status":"available","candidates":[],"path_exposed":False,"internal_id_exposed":False}
    plans=_owner_directory(plans);attempts=_owner_directory(attempts);receipt_names=set() if not receipts.exists() else {path.stem for path in _owner_directory(receipts).glob("*.json")}
    attempted=set()
    for path in attempts.glob("*.json"):
        path=_owner_file(path,"asset_activity_csv_attempt_conflict");value=_read_attempt(path)
        if value.get("context_fingerprint")==_context_fingerprint(context):attempted.add(value.get("plan_fingerprint"))
    candidates=[]
    for path in plans.glob("*.json"):
        path=_owner_file(path,"asset_activity_csv_storage_invalid")
        try:plan=json.loads(path.read_text(encoding="utf-8"))
        except Exception:_abort("asset_activity_csv_storage_invalid")
        plan_fp=plan.get("plan_fingerprint")
        if plan.get("context_fingerprint")==_context_fingerprint(context) and plan_fp in attempted and plan_fp not in receipt_names:
            candidates.append({"resume_ref":"airp_"+plan_fp[:32],"plan_fingerprint":plan_fp,"import_key":plan["import_key"],"row_count":plan["row_count"],"previewed_at_utc":plan["previewed_at_utc"]})
    candidates.sort(key=lambda item:(item["previewed_at_utc"],item["resume_ref"]))
    return {"status":"available","candidates":candidates,"path_exposed":False,"internal_id_exposed":False}


def resume_asset_activity_csv_import_v1(canonical_path:str|Path,data_space_path:str|Path,context_value:Any,plan_fingerprint:str)->AssetActivityCsvImportResultV1:
    context=_runtime(context_value);data_space=_owner_directory(data_space_path);area=_area(data_space)
    if not isinstance(plan_fingerprint,str) or re.fullmatch(r"[a-f0-9]{64}",plan_fingerprint) is None:_abort("asset_activity_csv_input_invalid")
    plan_file=_owner_file(area/"plans"/(plan_fingerprint+".json"),"asset_activity_csv_storage_invalid")
    try:plan=json.loads(plan_file.read_text(encoding="utf-8"))
    except Exception:_abort("asset_activity_csv_storage_invalid")
    if plan_file.read_bytes()!=_canonical(plan)+b"\n" or plan.get("plan_fingerprint")!=plan_fingerprint or plan.get("context_fingerprint")!=_context_fingerprint(context):_abort("asset_activity_csv_storage_invalid")
    attempts=_owner_directory(area/"attempts");matches=[]
    for path in attempts.glob("*.json"):
        path=_owner_file(path,"asset_activity_csv_attempt_conflict");value=_read_attempt(path)
        if value.get("plan_fingerprint")==plan_fingerprint:matches.append(value)
    if len(matches)!=1:_abort("asset_activity_csv_attempt_conflict")
    attempt=matches[0]
    return apply_asset_activity_csv_import_v1(canonical_path,data_space,context,plan,attempt["confirmation"],attempt["attempted_at_utc"])


def write_asset_activity_csv_template_v1(path_value:str|Path) -> None:
    path=Path(path_value)
    try:
        with path.open("x",encoding="utf-8",newline="") as handle:csv.writer(handle,lineterminator="\n").writerow(HEADERS)
    except OSError:_abort("asset_activity_csv_storage_invalid")

__all__=["AssetActivityCsvImportResultV1","AssetActivityCsvImportV1Error","HEADERS","asset_activity_csv_event_ref_v1","asset_activity_csv_import_v1_error_codes","apply_asset_activity_csv_import_v1","build_asset_activity_csv_confirmation_v1","export_asset_activity_csv_v1","inspect_asset_activity_csv_v1","list_resumable_asset_activity_csv_imports_v1","preview_asset_activity_csv_import_v1","resume_asset_activity_csv_import_v1","write_asset_activity_csv_template_v1"]
