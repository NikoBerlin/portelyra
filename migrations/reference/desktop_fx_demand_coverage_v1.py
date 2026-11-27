#!/usr/bin/env python3
"""Provider-free on-demand FX pair and persisted daily coverage inventory."""
from __future__ import annotations
from datetime import date,timedelta
from pathlib import Path
import os,re,stat
from typing import Any,Mapping,Sequence
from migrations.reference.fx_history_v1 import FxHistoryBlocked,FxHistoryContext,read_fx_history_v1,read_fx_pair_catalog_v1

STORE_AREA="fx-history-v1";STORE_NAME="fx-history.sqlite"
FAILURE_CODES=frozenset({"desktop_fx_demand_coverage_context_invalid","desktop_fx_demand_coverage_input_invalid","desktop_fx_demand_coverage_store_invalid"})
_CURRENCY=re.compile(r"^[A-Z]{3}$");_DATE=re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
class DesktopFxDemandCoverageV1Error(RuntimeError):
 def __init__(self,code:str):
  if code not in FAILURE_CODES:raise ValueError("desktop_fx_demand_coverage_error_unregistered")
  self.code=code;super().__init__(code)
def _abort(code):raise DesktopFxDemandCoverageV1Error(code)
def _context(value):
 if not isinstance(value,Mapping):_abort("desktop_fx_demand_coverage_context_invalid")
 try:ctx=FxHistoryContext(value["tenant_id"],value["user_id"],value["data_space_id"],"portfolio_reader","portfolio_worker")
 except (KeyError,TypeError):_abort("desktop_fx_demand_coverage_context_invalid")
 return ctx
def _currency(value):
 if not isinstance(value,str) or _CURRENCY.fullmatch(value) is None:_abort("desktop_fx_demand_coverage_input_invalid")
 return value
def _day(value):
 if not isinstance(value,str) or _DATE.fullmatch(value) is None:_abort("desktop_fx_demand_coverage_input_invalid")
 try:parsed=date.fromisoformat(value)
 except ValueError:_abort("desktop_fx_demand_coverage_input_invalid")
 if parsed.isoformat()!=value:_abort("desktop_fx_demand_coverage_input_invalid")
 return parsed
def _space(path,ctx):
 p=Path(path)
 try:i=p.stat(follow_symlinks=False);r=p.resolve(strict=True)
 except OSError:_abort("desktop_fx_demand_coverage_store_invalid")
 if not p.is_absolute() or p.is_symlink() or r!=p or p.name!=ctx.data_space_id or not stat.S_ISDIR(i.st_mode) or stat.S_IMODE(i.st_mode)!=0o700 or i.st_uid!=os.geteuid():_abort("desktop_fx_demand_coverage_store_invalid")
 return p
def read_desktop_fx_demand_coverage_v1(data_space_path:str|Path,context:Mapping[str,str],demands:Sequence[Mapping[str,Any]],start_date:str,end_date:str)->dict[str,Any]:
 ctx=_context(context);space=_space(data_space_path,ctx);start=_day(start_date);end=_day(end_date)
 if end<start or not isinstance(demands,Sequence) or isinstance(demands,(str,bytes)):_abort("desktop_fx_demand_coverage_input_invalid")
 normalized=[];seen=set()
 for raw in demands:
  if not isinstance(raw,Mapping) or set(raw)!={"source_currency","target_currency","consumer_count"} or type(raw["consumer_count"]) is not int or raw["consumer_count"]<1:_abort("desktop_fx_demand_coverage_input_invalid")
  source=_currency(raw["source_currency"]);target=_currency(raw["target_currency"])
  if source==target or (source,target) in seen:_abort("desktop_fx_demand_coverage_input_invalid")
  seen.add((source,target));normalized.append((source,target,raw["consumer_count"]))
 store=space/STORE_AREA/STORE_NAME;catalog=None
 if store.exists():
  try:catalog=read_fx_pair_catalog_v1(store,ctx)
  except FxHistoryBlocked as error:raise DesktopFxDemandCoverageV1Error("desktop_fx_demand_coverage_store_invalid") from error
 rows=[];requested=(end-start).days+1
 for source,target,count in normalized:
  matches=[] if catalog is None else [p for p in catalog["pairs"] if {p["base_currency"],p["quote_currency"]}=={source,target}]
  if len(matches)>1:_abort("desktop_fx_demand_coverage_store_invalid")
  if not matches:
   rows.append({"source_currency":source,"target_currency":target,"consumer_count":count,"route_kind":"unbound","coverage_status":"pair_missing","requested_day_count":requested,"observed_day_count":0,"non_trading_day_count":0,"source_gap_day_count":0,"missing_day_count":requested,"missing_ranges":[{"start_date":start_date,"end_date":end_date,"calendar_day_count":requested}]});continue
  pair=matches[0];route="direct" if pair["base_currency"]==source else "inverse"
  try:history=read_fx_history_v1(store,ctx,pair["pair_ref"],start_date,end_date)
  except FxHistoryBlocked as error:raise DesktopFxDemandCoverageV1Error("desktop_fx_demand_coverage_store_invalid") from error
  days=history["days"];missing=[r["rate_date"] for r in days if r["day_status"]=="not_requested"];ranges=[]
  for value in missing:
   if not ranges or date.fromisoformat(value)>date.fromisoformat(ranges[-1]["end_date"])+timedelta(days=1):ranges.append({"start_date":value,"end_date":value,"calendar_day_count":1})
   else:ranges[-1]["end_date"]=value;ranges[-1]["calendar_day_count"]+=1
  gaps=sum(r["day_status"]=="source_gap" for r in days);miss=len(missing)
  rows.append({"source_currency":source,"target_currency":target,"consumer_count":count,"route_kind":route,"coverage_status":"complete" if miss==0 and gaps==0 else "partial","requested_day_count":requested,"observed_day_count":sum(r["day_status"]=="observed" for r in days),"last_observed_date":max([r["rate_date"] for r in days if r["day_status"]=="observed"],default=None),"non_trading_day_count":sum(r["day_status"]=="non_trading_day" for r in days),"source_gap_day_count":gaps,"missing_day_count":miss,"missing_ranges":ranges})
 return {"contract_version":"desktop_fx_demand_coverage_v1","status":"ready","start_date":start_date,"end_date":end_date,"pair_count":len(rows),"rows":rows,"provider_access":False,"network_access":False,"fx_history_write":False,"canonical_write":False,"pair_refs_exposed":False}
