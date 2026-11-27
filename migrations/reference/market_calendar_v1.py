#!/usr/bin/env python3
"""Provider-free versioned Listing/FX-pair calendar classification proposals."""
from __future__ import annotations
from datetime import date
import hashlib,json,re
from typing import Any,Mapping,Sequence
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
SHA=re.compile(r"^[a-f0-9]{64}$");REF=re.compile(r"^cal_[a-f0-9]{32}$");KINDS=frozenset({"continuous_24_7","weekly_sessions"});SOURCE_STATUSES=frozenset({"observed","non_trading_day","source_gap","not_requested"})
CODES=frozenset({"market_calendar_profile_invalid","market_calendar_input_invalid","market_calendar_conflict"})
class MarketCalendarV1Error(RuntimeError):
 def __init__(self,code):
  if code not in CODES:raise ValueError("market_calendar_error_unregistered")
  self.code=code;super().__init__(code)
def _abort(code):raise MarketCalendarV1Error(code)
def _canon(v):return json.dumps(v,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":"))
def _sha(v):return hashlib.sha256(_canon(v).encode()).hexdigest()
def _date(v,code):
 try:d=date.fromisoformat(v)
 except (TypeError,ValueError):_abort(code)
 if d.isoformat()!=v:_abort(code)
 return d
def validate_market_calendar_profile_v1(value:Mapping[str,Any])->dict[str,Any]:
 required={"contract_version","calendar_ref","profile_version","calendar_kind","market_code","timezone_name","valid_from","valid_to","session_weekdays","closure_dates","special_open_dates","source_kind","source_ref","profile_fingerprint"}
 if not isinstance(value,Mapping) or set(value)!=required or value.get("contract_version")!="market_calendar_profile_v1" or not isinstance(value.get("calendar_ref"),str) or REF.fullmatch(value["calendar_ref"]) is None or type(value.get("profile_version")) is not int or value["profile_version"]<1 or value.get("calendar_kind") not in KINDS:_abort("market_calendar_profile_invalid")
 if not isinstance(value.get("market_code"),str) or not value["market_code"] or not isinstance(value.get("timezone_name"),str) or not isinstance(value.get("source_kind"),str) or value["source_kind"] not in {"reviewed_manifest","provider_manifest"} or not isinstance(value.get("source_ref"),str) or not value["source_ref"]:_abort("market_calendar_profile_invalid")
 try:ZoneInfo(value["timezone_name"])
 except ZoneInfoNotFoundError:_abort("market_calendar_profile_invalid")
 start=_date(value["valid_from"],"market_calendar_profile_invalid");end=_date(value["valid_to"],"market_calendar_profile_invalid")
 weekdays=value["session_weekdays"]
 if end<start or not isinstance(weekdays,list) or any(type(x) is not int or x<1 or x>7 for x in weekdays) or len(set(weekdays))!=len(weekdays):_abort("market_calendar_profile_invalid")
 if value["calendar_kind"]=="continuous_24_7" and sorted(weekdays)!=list(range(1,8)):_abort("market_calendar_profile_invalid")
 closures=value["closure_dates"];openings=value["special_open_dates"]
 if not isinstance(closures,list) or not isinstance(openings,list) or len(closures)>10000 or len(openings)>10000:_abort("market_calendar_profile_invalid")
 normalized_closures=[];seen=set()
 for row in closures:
  if not isinstance(row,Mapping) or set(row)!={"date","reason"} or not isinstance(row.get("reason"),str) or not row["reason"]:_abort("market_calendar_profile_invalid")
  d=_date(row["date"],"market_calendar_profile_invalid")
  if d<start or d>end or row["date"] in seen:_abort("market_calendar_profile_invalid")
  seen.add(row["date"]);normalized_closures.append(dict(row))
 normalized_open=[]
 for raw in openings:
  d=_date(raw,"market_calendar_profile_invalid")
  if d<start or d>end or raw in seen or raw in normalized_open:_abort("market_calendar_profile_invalid")
  normalized_open.append(raw)
 body={k:value[k] for k in required if k!="profile_fingerprint"}
 if not isinstance(value["profile_fingerprint"],str) or not SHA.fullmatch(value["profile_fingerprint"]) or value["profile_fingerprint"]!=_sha(body):_abort("market_calendar_profile_invalid")
 return {**body,"profile_fingerprint":value["profile_fingerprint"]}
def build_market_calendar_profile_v1(*,profile_version:int,calendar_kind:str,market_code:str,timezone_name:str,valid_from:str,valid_to:str,session_weekdays:Sequence[int],closure_dates:Sequence[Mapping[str,str]],special_open_dates:Sequence[str],source_kind:str,source_ref:str)->dict[str,Any]:
 body={"contract_version":"market_calendar_profile_v1","calendar_ref":"","profile_version":profile_version,"calendar_kind":calendar_kind,"market_code":market_code,"timezone_name":timezone_name,"valid_from":valid_from,"valid_to":valid_to,"session_weekdays":list(session_weekdays),"closure_dates":[dict(x) for x in closure_dates],"special_open_dates":list(special_open_dates),"source_kind":source_kind,"source_ref":source_ref}
 identity={k:v for k,v in body.items() if k!="calendar_ref"};body["calendar_ref"]="cal_"+_sha(identity)[:32];body["profile_fingerprint"]=_sha(body);return validate_market_calendar_profile_v1(body)
def classify_market_calendar_days_v1(profile:Mapping[str,Any],days:Sequence[Mapping[str,str]])->dict[str,Any]:
 p=validate_market_calendar_profile_v1(profile);start=_date(p["valid_from"],"market_calendar_profile_invalid");end=_date(p["valid_to"],"market_calendar_profile_invalid");closures={x["date"]:x["reason"] for x in p["closure_dates"]};openings=set(p["special_open_dates"]);rows=[];seen=set()
 if not isinstance(days,Sequence) or isinstance(days,(str,bytes)):_abort("market_calendar_input_invalid")
 for raw in days:
  if not isinstance(raw,Mapping) or set(raw)!={"date","source_status"} or raw.get("source_status") not in SOURCE_STATUSES:_abort("market_calendar_input_invalid")
  d=_date(raw["date"],"market_calendar_input_invalid")
  if d<start or d>end or raw["date"] in seen:_abort("market_calendar_input_invalid")
  seen.add(raw["date"]);scheduled=raw["date"] in openings or (d.isoweekday() in p["session_weekdays"] and raw["date"] not in closures);reason="special_open" if raw["date"] in openings else closures.get(raw["date"],"regular_session" if scheduled else "weekly_closed")
  status=raw["source_status"];proposed=status;disposition="retain"
  if status=="source_gap" and not scheduled:proposed="non_trading_day";disposition="calendar_correction_proposed"
  elif status=="observed" and not scheduled:disposition="calendar_conflict_review"
  rows.append({"date":raw["date"],"source_status":status,"session_expected":scheduled,"calendar_reason":reason,"proposed_status":proposed,"disposition":disposition,"confirmation_required":disposition!="retain"})
 return {"contract_version":"market_calendar_classification_v1","status":"review_required" if any(x["confirmation_required"] for x in rows) else "classified","calendar_kind":p["calendar_kind"],"market_code":p["market_code"],"timezone_name":p["timezone_name"],"profile_fingerprint":p["profile_fingerprint"],"rows":rows,"provider_access":False,"network_access":False,"history_write":False,"canonical_write":False}
__all__=["MarketCalendarV1Error","build_market_calendar_profile_v1","validate_market_calendar_profile_v1","classify_market_calendar_days_v1"]
