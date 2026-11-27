#!/usr/bin/env python3
"""One confirmed append-only calendar correction for one native or FX source gap."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from typing import Any,Mapping
from migrations.reference.market_calendar_v1 import classify_market_calendar_days_v1
from migrations.reference.market_calendar_registry_v1 import read_market_calendar_catalog_v1
from migrations.reference.fx_history_v1 import *
from migrations.reference.daily_market_history_v1 import MarketHistoryContext,read_daily_market_history_v1,seal_daily_market_history_candidate_v1,append_daily_market_history_v1,daily_market_history_job_binding_fingerprint_v1
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA,STORE_NAME as MARKET_STORE
from migrations.reference.desktop_fx_demand_coverage_v1 import STORE_AREA as FX_AREA,STORE_NAME as FX_STORE
SHA=re.compile(r"^[a-f0-9]{64}$");DATE=re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$");SCOPE=re.compile(r"^(?:lsr|fxp)_[a-f0-9]{32}$")
CODES=frozenset({"market_calendar_correction_context_invalid","market_calendar_correction_input_invalid","market_calendar_correction_profile_missing","market_calendar_correction_not_applicable","market_calendar_correction_preview_invalid","market_calendar_correction_confirmation_required","market_calendar_correction_stale","market_calendar_correction_write_failed"})
class MarketCalendarCorrectionV1Error(RuntimeError):
 def __init__(self,code):
  if code not in CODES:raise ValueError("market_calendar_correction_error_unregistered")
  self.code=code;super().__init__(code)
def _abort(code):raise MarketCalendarCorrectionV1Error(code)
def _canon(v):return json.dumps(v,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":"))
def _sha(v):return hashlib.sha256(_canon(v).encode()).hexdigest()
def _ctx(v):
 if not isinstance(v,Mapping) or v.get("actor_id")!="market_worker" or v.get("role")!="market_worker" or not isinstance(v.get("data_space_id"),str):_abort("market_calendar_correction_context_invalid")
 return dict(v)
def _utc(v):
 try:return datetime.strptime(v,"%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
 except (TypeError,ValueError):_abort("market_calendar_correction_input_invalid")
def _profile(space,ctx,kind,scope):
 try:matches=[x for x in read_market_calendar_catalog_v1(space,{**ctx,"actor_id":"portfolio_reader","role":"portfolio_worker"},scopes=[(kind,scope)])["bindings"] if x["scope_kind"]==kind and x["scope_ref"]==scope]
 except Exception as e:raise MarketCalendarCorrectionV1Error("market_calendar_correction_profile_missing") from e
 if len(matches)!=1:_abort("market_calendar_correction_profile_missing")
 return matches[0]
def preview_market_calendar_correction_v1(data_space_path,context,scope_kind,scope_ref,day,created_at_utc):
 ctx=_ctx(context);space=Path(data_space_path);_utc(created_at_utc)
 if scope_kind not in {"listing","fx_pair"} or not isinstance(scope_ref,str) or not SCOPE.fullmatch(scope_ref) or not isinstance(day,str) or not DATE.fullmatch(day):_abort("market_calendar_correction_input_invalid")
 binding=_profile(space,ctx,scope_kind,scope_ref);profile=binding["profile"]
 try:
  if scope_kind=="fx_pair":current=read_fx_history_v1(space/FX_AREA/FX_STORE,FxHistoryContext(ctx["tenant_id"],ctx["user_id"],ctx["data_space_id"],"portfolio_reader","portfolio_worker"),scope_ref,day,day)["days"][0];status=current["day_status"];revision=current["revision_ref"]
  else:current=read_daily_market_history_v1(space/MARKET_AREA/MARKET_STORE,MarketHistoryContext(ctx["tenant_id"],ctx["user_id"],ctx["data_space_id"],"portfolio_reader","portfolio_worker"),scope_ref,day,day)["days"][0];status=current["day_status"];revision=current["market_day_revision_ref"]
 except Exception as e:raise MarketCalendarCorrectionV1Error("market_calendar_correction_input_invalid") from e
 proposal=classify_market_calendar_days_v1(profile,[{"date":day,"source_status":status}])["rows"][0]
 if proposal["disposition"]!="calendar_correction_proposed" or proposal["proposed_status"]!="non_trading_day" or not isinstance(revision,str):_abort("market_calendar_correction_not_applicable")
 body={"contract_version":"market_calendar_correction_candidate_v1","status":"pending_confirmation","scope_kind":scope_kind,"scope_ref":scope_ref,"date":day,"supersedes_revision_ref":revision,"calendar_reason":proposal["calendar_reason"],"profile_fingerprint":profile["profile_fingerprint"],"binding_revision":binding["binding_revision"],"created_at_utc":created_at_utc,"context_fingerprint":_sha(ctx),"provider_access":False,"history_write":False,"canonical_write":False};body["candidate_fingerprint"]=_sha(body);return body
def public_market_calendar_correction_preview_v1(v):
 if not isinstance(v,dict) or v.get("candidate_fingerprint")!=_sha({k:x for k,x in v.items() if k!="candidate_fingerprint"}):_abort("market_calendar_correction_preview_invalid")
 return {"contract_version":"market_calendar_correction_public_preview_v1","status":"pending_confirmation","scope_kind":v["scope_kind"],"date":v["date"],"source_status":"source_gap","proposed_status":"non_trading_day","calendar_reason":v["calendar_reason"],"confirmation_required":True,"provider_access":False,"history_write":False,"canonical_write":False}
def apply_market_calendar_correction_v1(data_space_path,context,candidate,public_preview,confirmed,completed_at_utc):
 ctx=_ctx(context);completed=_utc(completed_at_utc);space=Path(data_space_path)
 if confirmed is not True:_abort("market_calendar_correction_confirmation_required")
 if public_preview!=public_market_calendar_correction_preview_v1(candidate) or candidate["context_fingerprint"]!=_sha(ctx):_abort("market_calendar_correction_preview_invalid")
 binding=_profile(space,ctx,candidate["scope_kind"],candidate["scope_ref"])
 if binding["binding_revision"]!=candidate["binding_revision"] or binding["profile"]["profile_fingerprint"]!=candidate["profile_fingerprint"]:_abort("market_calendar_correction_stale")
 day=candidate["date"];scope=candidate["scope_ref"];key=candidate["candidate_fingerprint"][:32]
 try:
  if candidate["scope_kind"]=="fx_pair":
   writer=FxHistoryContext(ctx["tenant_id"],ctx["user_id"],ctx["data_space_id"],"market_worker","market_worker");store=space/FX_AREA/FX_STORE;src="fxs_"+_sha({"calendar":candidate["profile_fingerprint"]})[:32];req="fxq_"+key;rfp=_sha({"candidate":candidate["candidate_fingerprint"]});row={"rate_date":day,"revision_mode":"correction","supersedes_revision_ref":candidate["supersedes_revision_ref"],"day_status":"non_trading_day","rate_decimal":None,"quality_status":"calendar_confirmed","gap_reason":None,"source_observation_ref":"fxo_"+key,"observed_at_utc":completed,"correction_reason":"calendar_correction"};sealed=seal_fx_history_candidate_v1(pair_ref=scope,request_ref=req,source_kind="manual_reviewed_evidence",source_ref=src,source_version="market_calendar_v1.0.0",plugin_id=None,plugin_version=None,plugin_manifest_fingerprint=None,request_fingerprint=rfp,job_binding_fingerprint=fx_history_job_binding_fingerprint_v1(writer,pair_ref=scope,request_ref=req,request_fingerprint=rfp,source_ref=src),requested_start_date=day,requested_end_date=day,retrieved_at_utc=completed,days=[row]);receipt=append_fx_history_v1(store,writer,sealed,completed);corrected=receipt.corrected_day_count
  else:
   writer=MarketHistoryContext(ctx["tenant_id"],ctx["user_id"],ctx["data_space_id"],"market_worker","market_worker");store=space/MARKET_AREA/MARKET_STORE;src="msr_"+_sha({"calendar":candidate["profile_fingerprint"]})[:32];req="mrq_"+key;rfp=_sha({"candidate":candidate["candidate_fingerprint"]});row={"trading_date":day,"revision_mode":"correction","supersedes_revision_ref":candidate["supersedes_revision_ref"],"day_status":"non_trading_day","bar_shape":"not_applicable","open_decimal":None,"high_decimal":None,"low_decimal":None,"close_decimal":None,"adjusted_close_decimal":None,"volume_decimal":None,"valuation_status":"not_applicable","quality_status":"calendar_confirmed","gap_reason":None,"corporate_action_status":"not_applicable","source_observation_ref":"mor_"+key,"observed_at_utc":completed,"correction_reason":"calendar_correction"};sealed=seal_daily_market_history_candidate_v1(listing_ref=scope,request_ref=req,source_kind="manual_reviewed_evidence",source_ref=src,source_version="market_calendar_v1.0.0",request_fingerprint=rfp,job_binding_fingerprint=daily_market_history_job_binding_fingerprint_v1(writer,listing_ref=scope,request_ref=req,request_fingerprint=rfp,source_ref=src),requested_start_date=day,requested_end_date=day,retrieved_at_utc=completed,days=[row]);receipt=append_daily_market_history_v1(store,writer,sealed,completed);corrected=receipt.corrected_day_count
  return {"status":"published","scope_kind":candidate["scope_kind"],"date":day,"corrected_day_count":corrected,"provider_access":False,"canonical_write":False}
 except MarketCalendarCorrectionV1Error:raise
 except Exception as e:raise MarketCalendarCorrectionV1Error("market_calendar_correction_write_failed") from e
__all__=["MarketCalendarCorrectionV1Error","preview_market_calendar_correction_v1","public_market_calendar_correction_preview_v1","apply_market_calendar_correction_v1"]
