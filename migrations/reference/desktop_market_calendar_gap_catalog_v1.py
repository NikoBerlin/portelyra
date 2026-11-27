#!/usr/bin/env python3
"""Provider-free shared native-market and FX gap catalog with calendar proposals."""
from __future__ import annotations
from pathlib import Path
import re
from typing import Any,Mapping,Sequence
from migrations.reference.daily_market_history_v1 import MarketHistoryContext,read_daily_market_history_v1,DailyMarketHistoryBlocked
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA,STORE_NAME as MARKET_STORE
from migrations.reference.fx_history_v1 import FxHistoryContext,read_fx_pair_catalog_v1,read_fx_history_v1,FxHistoryBlocked
from migrations.reference.desktop_fx_demand_coverage_v1 import STORE_AREA as FX_AREA,STORE_NAME as FX_STORE
from migrations.reference.market_calendar_registry_v1 import read_market_calendar_catalog_v1,MarketCalendarRegistryV1Error
from migrations.reference.market_calendar_v1 import classify_market_calendar_days_v1,MarketCalendarV1Error
from migrations.reference.market_valuation_calendar_v1 import propose_calendar
DATE=re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$");LISTING=re.compile(r"^lsr_[a-f0-9]{32}$");ASSET=re.compile(r"^asset_ref_[0-9]{4,}$");CUR=re.compile(r"^[A-Z]{3}$")
CODES=frozenset({"desktop_market_calendar_gap_context_invalid","desktop_market_calendar_gap_input_invalid","desktop_market_calendar_gap_store_invalid"})
class DesktopMarketCalendarGapCatalogV1Error(RuntimeError):
 def __init__(self,code):
  if code not in CODES:raise ValueError("desktop_market_calendar_gap_error_unregistered")
  self.code=code;super().__init__(code)
def _abort(code):raise DesktopMarketCalendarGapCatalogV1Error(code)
def _context(v):
 if not isinstance(v,Mapping) or not all(isinstance(v.get(k),str) and v[k] for k in ("tenant_id","user_id","data_space_id")):_abort("desktop_market_calendar_gap_context_invalid")
 return dict(v,actor_id="portfolio_reader",role="portfolio_worker")
def _date(v):
 from datetime import date
 try:d=date.fromisoformat(v)
 except (TypeError,ValueError):_abort("desktop_market_calendar_gap_input_invalid")
 if d.isoformat()!=v:_abort("desktop_market_calendar_gap_input_invalid")
 return d
def read_desktop_market_calendar_gap_catalog_v1(data_space_path:str|Path,context:Mapping[str,str],listings:Sequence[Mapping[str,str]],fx_demands:Sequence[Mapping[str,Any]],start_date:str,end_date:str)->dict[str,Any]:
 ctx=_context(context);start=_date(start_date);end=_date(end_date);space=Path(data_space_path)
 if end<start or not isinstance(listings,Sequence) or isinstance(listings,(str,bytes)) or not isinstance(fx_demands,Sequence) or isinstance(fx_demands,(str,bytes)):_abort("desktop_market_calendar_gap_input_invalid")
 profiles={};unverified=set()
 try:
  # Diagnostic only: unproven legacy profiles are NEVER classification authority.
  catalog=read_market_calendar_catalog_v1(space,ctx,require_context=False)
  profiles={(x['scope_kind'],x['scope_ref']):x['profile'] for x in catalog['bindings'] if x['context_verified']}
  unverified={(x['scope_kind'],x['scope_ref']) for x in catalog['bindings'] if not x['context_verified']}
 except MarketCalendarRegistryV1Error as e:
  if (space/"market-calendar-v1").exists():raise DesktopMarketCalendarGapCatalogV1Error("desktop_market_calendar_gap_store_invalid") from e
 rows=[];seen=set();mctx=MarketHistoryContext(ctx["tenant_id"],ctx["user_id"],ctx["data_space_id"],"portfolio_reader","portfolio_worker")
 for raw in listings:
  if not isinstance(raw,Mapping) or set(raw)!={"asset_ref","listing_ref"} or not ASSET.fullmatch(raw.get("asset_ref","")) or not LISTING.fullmatch(raw.get("listing_ref","")) or raw["asset_ref"] in seen:_abort("desktop_market_calendar_gap_input_invalid")
  seen.add(raw["asset_ref"]);store=space/MARKET_AREA/MARKET_STORE
  try:history=read_daily_market_history_v1(store,mctx,raw['listing_ref'],start_date,end_date)
  except DailyMarketHistoryBlocked as e:raise DesktopMarketCalendarGapCatalogV1Error('desktop_market_calendar_gap_store_invalid') from e
  try:rules=propose_calendar(history,start_date,end_date,[],use_rules=True)['profile']
  except ValueError:rules=None
  _append(rows,'listing',raw['asset_ref'],raw['listing_ref'],history['days'],'trading_date',profiles.get(('listing',raw['listing_ref'])),rules,('listing',raw['listing_ref']) in unverified)
 fctx=FxHistoryContext(ctx["tenant_id"],ctx["user_id"],ctx["data_space_id"],"portfolio_reader","portfolio_worker");fxstore=space/FX_AREA/FX_STORE
 try:pairs=read_fx_pair_catalog_v1(fxstore,fctx)["pairs"] if fxstore.exists() else []
 except FxHistoryBlocked as e:raise DesktopMarketCalendarGapCatalogV1Error("desktop_market_calendar_gap_store_invalid") from e
 for raw in fx_demands:
  if not isinstance(raw,Mapping) or set(raw)!={"source_currency","target_currency","consumer_count"} or not CUR.fullmatch(raw.get("source_currency","")) or not CUR.fullmatch(raw.get("target_currency","")) or type(raw.get("consumer_count")) is not int or raw["consumer_count"]<1:_abort("desktop_market_calendar_gap_input_invalid")
  matches=[p for p in pairs if {p["base_currency"],p["quote_currency"]}=={raw["source_currency"],raw["target_currency"]}]
  if len(matches)>1:_abort("desktop_market_calendar_gap_store_invalid")
  if not matches:continue
  pair=matches[0]
  try:days=read_fx_history_v1(fxstore,fctx,pair["pair_ref"],start_date,end_date)["days"]
  except FxHistoryBlocked as e:raise DesktopMarketCalendarGapCatalogV1Error("desktop_market_calendar_gap_store_invalid") from e
  _append(rows,'fx_pair',raw['source_currency']+'→'+raw['target_currency'],pair['pair_ref'],days,'rate_date',profiles.get(('fx_pair',pair['pair_ref'])),None,('fx_pair',pair['pair_ref']) in unverified)
 rows.sort(key=lambda x:(x["scope_kind"],x["consumer_ref"],x["date"]));counts={k:sum(x["disposition"]==k for x in rows) for k in ("fetch_required","source_gap_retry_required","calendar_profile_missing","calendar_correction_proposed","calendar_conflict_review")}
 return {"contract_version":"desktop_market_calendar_gap_catalog_v1","status":"review_required" if rows else "complete","start_date":start_date,"end_date":end_date,"row_count":len(rows),"unverified_binding_count":len(unverified),"counts":counts,"rows":rows,"provider_access":False,"network_access":False,"history_write":False,"canonical_write":False,"internal_scope_refs_exposed":False}
def _append(out,kind,consumer,scope,days,date_key,profile,rules=None,unverified=False):
 relevant=[x for x in days if x["day_status"] in {"not_requested","source_gap"}]
 classified={}
 if profile and relevant:
  try:c=classify_market_calendar_days_v1(profile,[{'date':x[date_key],'source_status':x['day_status']} for x in relevant if profile['valid_from']<=x[date_key]<=profile['valid_to']]);classified={x['date']:x for x in c['rows']}
  except MarketCalendarV1Error as e:raise DesktopMarketCalendarGapCatalogV1Error("desktop_market_calendar_gap_store_invalid") from e
 for day in relevant:
  ds=day[date_key];status=day["day_status"];c=classified.get(ds)
  if status=="not_requested":disposition="fetch_required";proposed=status;reason="not_requested"
  elif c is None:disposition='calendar_profile_missing';proposed=status;reason='context_confirmation_required' if unverified else 'profile_missing_or_outside_validity'
  elif c["disposition"]=="calendar_correction_proposed":disposition="calendar_correction_proposed";proposed=c["proposed_status"];reason=c["calendar_reason"]
  else:disposition="source_gap_retry_required";proposed=status;reason=c["calendar_reason"]
  out.append({"scope_kind":kind,"consumer_ref":consumer,"date":ds,"source_status":status,"proposed_status":proposed,"reason":reason,"disposition":disposition,"calendar_profile_bound":c is not None,"context_confirmation_required":unverified,"rule_closure_candidate":bool(rules and any(x['date']==ds for x in rules['closure_dates'])),"rule_reason":next((x['reason'] for x in rules['closure_dates'] if x['date']==ds),'') if rules else ''})
__all__=["DesktopMarketCalendarGapCatalogV1Error","read_desktop_market_calendar_gap_catalog_v1"]
