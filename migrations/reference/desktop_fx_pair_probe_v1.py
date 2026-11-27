#!/usr/bin/env python3
"""One confirmed FX pair probe with owner-local evidence only (request and parsing by the price provider plugin since rc.382)."""
from __future__ import annotations
from datetime import date,datetime,timezone
import base64,hashlib,json,os,re,stat
from pathlib import Path
from typing import Any,Callable,Mapping
from migrations.reference import price_provider_plugins_v1 as price_providers
from migrations.reference.desktop_provider_probe_v1 import PROVIDER_ID,TIMEOUT,BYTE_LIMIT,_default_transport
AREA="desktop-fx-pair-probe-v1";SHA=re.compile(r"^[a-f0-9]{64}$");UTC=re.compile(r"^[0-9-]{10}T[0-9:]{8}Z$")
FAILURE_CODES=frozenset({"desktop_fx_pair_probe_context_invalid","desktop_fx_pair_probe_input_invalid","desktop_fx_pair_probe_preview_invalid","desktop_fx_pair_probe_confirmation_required","desktop_fx_pair_probe_attempt_consumed","desktop_fx_pair_probe_store_invalid","desktop_fx_pair_probe_transport_failed","desktop_fx_pair_probe_http_failed","desktop_fx_pair_probe_response_invalid","desktop_fx_pair_probe_response_json_invalid","desktop_fx_pair_probe_response_shape_invalid","desktop_fx_pair_probe_response_identity_invalid","desktop_fx_pair_probe_response_series_invalid","desktop_fx_pair_probe_response_currency_mismatch"})
class DesktopFxPairProbeV1Error(RuntimeError):
 def __init__(self,code):
  if code not in FAILURE_CODES:raise ValueError("desktop_fx_pair_probe_error_unregistered")
  self.code=code;super().__init__(code)
def _abort(code):raise DesktopFxPairProbeV1Error(code)
def _canon(v):return json.dumps(v,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":")).encode()
def _sha(v):return hashlib.sha256(v if isinstance(v,bytes) else _canon(v)).hexdigest()
def _context(v):
 if not isinstance(v,Mapping) or v.get("actor_id")!="market_worker" or v.get("role")!="market_worker" or not isinstance(v.get("data_space_id"),str) or not v["data_space_id"].startswith("sbx_"):_abort("desktop_fx_pair_probe_context_invalid")
 return {k:v[k] for k in ("tenant_id","user_id","data_space_id","actor_id","role")}
def _date(v):
 try:d=date.fromisoformat(v)
 except (TypeError,ValueError):_abort("desktop_fx_pair_probe_input_invalid")
 if d.isoformat()!=v:_abort("desktop_fx_pair_probe_input_invalid")
 return d
def _utc(v):
 try:d=datetime.strptime(v,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
 except (TypeError,ValueError):_abort("desktop_fx_pair_probe_input_invalid")
 return d.strftime("%Y-%m-%dT%H:%M:%SZ")
def _currency(v):
 if not isinstance(v,str) or re.fullmatch(r"[A-Z]{3}",v) is None:_abort("desktop_fx_pair_probe_input_invalid")
 return v
def _candidate(v):
 public_keys={"symbol","display_name","exchange","quote_type","quote_currency"};keys=set(v) if isinstance(v,Mapping) else set()
 if (keys!=public_keys and keys!=(public_keys|{"source_quote_fingerprint"})) or v.get("quote_type")!="currency" or not isinstance(v.get("symbol"),str) or not v["symbol"].strip():_abort("desktop_fx_pair_probe_input_invalid")
 public={k:v[k] for k in sorted(public_keys)};fingerprint=v.get("source_quote_fingerprint",_sha(public))
 if not isinstance(fingerprint,str) or SHA.fullmatch(fingerprint) is None:_abort("desktop_fx_pair_probe_input_invalid")
 return {**public,"source_quote_fingerprint":fingerprint}
def preview_desktop_fx_pair_probe_v1(context,candidate,source_currency,target_currency,direction,start_date,end_date,created_at_utc):
 ctx=_context(context);c=_candidate(candidate);source=_currency(source_currency);target=_currency(target_currency);start=_date(start_date);end=_date(end_date);created=_utc(created_at_utc)
 expected=target if direction=="direct" else source if direction=="inverse" else None
 if source==target or expected is None or c["quote_currency"] not in {None,expected} or end<start or (end-start).days>31:_abort("desktop_fx_pair_probe_input_invalid")
 body={"contract_version":"desktop_fx_pair_probe_preview_v1","status":"ready_for_confirmation","candidate":c,"source_currency":source,"target_currency":target,"direction":direction,"expected_provider_currency":expected,"start_date":start_date,"end_date":end_date,"created_at_utc":created,"context_fingerprint":_sha(ctx),"one_attempt":True,"provider_access":False,"network_access":False,"fx_history_write":False,"canonical_write":False,"automatic_retry":False};body["preview_fingerprint"]=_sha(body);return body
def _validate(v):
 if not isinstance(v,dict) or v.get("contract_version")!="desktop_fx_pair_probe_preview_v1" or v.get("status")!="ready_for_confirmation" or v.get("preview_fingerprint")!=_sha({k:x for k,x in v.items() if k!="preview_fingerprint"}):_abort("desktop_fx_pair_probe_preview_invalid")
 return v
def public_desktop_fx_pair_probe_preview_v1(v):
 v=_validate(v);return {"contract_version":"desktop_fx_pair_probe_public_preview_v1","status":"pending_confirmation","symbol":v["candidate"]["symbol"],"source_currency":v["source_currency"],"target_currency":v["target_currency"],"direction":v["direction"],"expected_provider_currency":v["expected_provider_currency"],"start_date":v["start_date"],"end_date":v["end_date"],"confirmation_required":True,"provider_access":False,"network_access":False,"owner_local_staging_after_confirmation":True,"fx_history_write":False,"canonical_write":False,"automatic_retry":False}
def _owner(path,ctx):
 p=Path(path)
 try:i=p.stat(follow_symlinks=False);r=p.resolve(strict=True)
 except OSError:_abort("desktop_fx_pair_probe_store_invalid")
 if not p.is_absolute() or p.is_symlink() or r!=p or p.name!=ctx["data_space_id"] or stat.S_IMODE(i.st_mode)!=0o700 or i.st_uid!=os.geteuid():_abort("desktop_fx_pair_probe_store_invalid")
 return p
def _dir(parent,name):
 p=parent/name
 if not p.exists():os.mkdir(p,0o700)
 if p.is_symlink() or stat.S_IMODE(p.stat().st_mode)!=0o700:_abort("desktop_fx_pair_probe_store_invalid")
 return p
def _write(path,v):
 try:
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600);os.write(fd,_canon(v)+b"\n");os.fsync(fd);os.close(fd)
 except FileExistsError:_abort("desktop_fx_pair_probe_attempt_consumed")
 except OSError:_abort("desktop_fx_pair_probe_store_invalid")
_FX_DETAIL_CODES={"json":"desktop_fx_pair_probe_response_json_invalid","shape":"desktop_fx_pair_probe_response_shape_invalid","identity":"desktop_fx_pair_probe_response_identity_invalid","series":"desktop_fx_pair_probe_response_series_invalid","value":"desktop_fx_pair_probe_response_invalid","input":"desktop_fx_pair_probe_input_invalid"}
def _parse_fx_response(body,preview):
 """Tageskurse eines Waehrungspaares; die Auswertung liegt seit rc.382 im Kursanbieter-Plugin, die Kennung je Tag bildet der Kern."""
 try:outcome=price_providers.parse_response_v1(PROVIDER_ID,"fx_daily_history",{"provider_symbol":preview["provider_symbol"],"start_date":preview["start_date"],"end_date":preview["end_date"]},{"status":200,"content_type":"application/json","body":body})
 except price_providers.PriceProviderBlocked:_abort("desktop_fx_pair_probe_response_invalid")
 if outcome["outcome"]!="ok":_abort(_FX_DETAIL_CODES[outcome["detail"]])
 result=outcome["result"];days=[]
 for row in result["days"]:
  vals={key:row[key+"_decimal"] for key in ("open","high","low","close","volume")}
  days.append(dict(row,source_observation_ref="fxo_"+_sha({"symbol":preview["provider_symbol"],"date":row["trading_date"],"values":vals})[:32]))
 return dict(result,days=days)
@price_providers.within_price_provider_session
def apply_desktop_fx_pair_probe_v1(data_space_path,context,preview,public_preview,confirmed,transport:Callable=_default_transport,clock=lambda:datetime.now(timezone.utc)):
 ctx=_context(context);v=_validate(preview)
 if v["context_fingerprint"]!=_sha(ctx) or public_preview!=public_desktop_fx_pair_probe_preview_v1(v):_abort("desktop_fx_pair_probe_preview_invalid")
 if confirmed is not True:_abort("desktop_fx_pair_probe_confirmation_required")
 root=_dir(_owner(data_space_path,ctx),AREA);attempts=_dir(root,"attempts");results=_dir(root,"results");key=v["preview_fingerprint"][:32];result_path=results/f"fxpr_{key}.json"
 if result_path.exists():
  try:return json.loads(result_path.read_text())
  except Exception:_abort("desktop_fx_pair_probe_store_invalid")
 _write(attempts/f"fxpa_{key}.json",{"contract_version":"desktop_fx_pair_probe_attempt_v1","preview_fingerprint":v["preview_fingerprint"],"started_at_utc":clock().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),"provider_access_authorized":True,"automatic_retry":False})
 try:request=price_providers.build_request_v1(PROVIDER_ID,"fx_daily_history",{"provider_symbol":v["candidate"]["symbol"],"start_date":v["start_date"],"end_date":v["end_date"],"request_start_date":v["start_date"]})
 except price_providers.PriceProviderBlocked as error:raise DesktopFxPairProbeV1Error("desktop_fx_pair_probe_transport_failed") from error
 try:response=transport(request["host"],request["target"],{"Accept":"application/json","Accept-Encoding":"identity","Connection":"close","User-Agent":"Portelyra/0.2 FX-Pair-Probe"},TIMEOUT,BYTE_LIMIT)
 except Exception as error:raise DesktopFxPairProbeV1Error("desktop_fx_pair_probe_transport_failed") from error
 if not isinstance(response,dict) or response.get("status")!=200:_abort("desktop_fx_pair_probe_http_failed")
 if not isinstance(response.get("body"),bytes):_abort("desktop_fx_pair_probe_response_invalid")
 # Ohne festgehaltene Antwort ist ein fehlgeschlagener Abruf spaeter nicht mehr
 # erklaerbar: Der Beleg nannte nur den Zeitpunkt, nicht den Grund.
 responses=_dir(root,"responses");failures=_dir(root,"failures")
 _write(responses/f"fxpq_{key}.json",{"contract_version":"desktop_fx_pair_probe_response_v1","preview_fingerprint":v["preview_fingerprint"],
   "http_status":response.get("status"),"retrieved_at_utc":clock().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
   "body_base64":base64.b64encode(response["body"]).decode("ascii")})
 parser={"provider_symbol":v["candidate"]["symbol"],"start_date":v["start_date"],"end_date":v["end_date"]}
 try:parsed=_parse_fx_response(response["body"],parser)
 except DesktopFxPairProbeV1Error as error:
  _write(failures/f"fxpf_{key}.json",{"contract_version":"desktop_fx_pair_probe_failure_v1","preview_fingerprint":v["preview_fingerprint"],
    "code":getattr(error,"code","desktop_fx_pair_probe_response_invalid"),"http_status":response.get("status"),
    "requested_symbol":v["candidate"]["symbol"],"failed_at_utc":clock().astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
  raise
 except Exception as error:raise DesktopFxPairProbeV1Error("desktop_fx_pair_probe_response_invalid") from error
 if parsed["provider_currency"]!=v["expected_provider_currency"]:_abort("desktop_fx_pair_probe_response_currency_mismatch")
 if parsed["split_review_required"]:_abort("desktop_fx_pair_probe_response_invalid")
 result={"contract_version":"desktop_fx_pair_probe_result_v1","status":"staged","preview_fingerprint":v["preview_fingerprint"],"source_currency":v["source_currency"],"target_currency":v["target_currency"],"direction":v["direction"],"symbol":v["candidate"]["symbol"],"provider_currency":parsed["provider_currency"],"exchange":parsed["exchange"],"timezone_name":parsed["timezone_name"],"start_date":v["start_date"],"end_date":v["end_date"],"days":parsed["days"],"provider_access":True,"network_access":True,"owner_local_staging":True,"fx_history_write":False,"canonical_write":False,"automatic_retry":False};result["result_fingerprint"]=_sha(result);_write(result_path,result);return result
def public_desktop_fx_pair_probe_result_v1(v):
 days=v["days"];return {"contract_version":"desktop_fx_pair_probe_public_result_v1","status":"staged","source_currency":v["source_currency"],"target_currency":v["target_currency"],"direction":v["direction"],"symbol":v["symbol"],"provider_currency":v["provider_currency"],"exchange":v["exchange"],"timezone_name":v["timezone_name"],"start_date":v["start_date"],"end_date":v["end_date"],"observed_day_count":sum(x["day_status"]=="observed" for x in days),"source_gap_day_count":sum(x["day_status"]=="source_gap" for x in days),"live_session":v.get("live_session"),"last_observed_date":next((x["trading_date"] for x in reversed(days) if x["day_status"]=="observed"),None),"last_close_decimal":next((x["close_decimal"] for x in reversed(days) if x["day_status"]=="observed"),None),"provider_access":True,"network_access":True,"owner_local_staging":True,"fx_history_write":False,"canonical_write":False,"automatic_retry":False}
