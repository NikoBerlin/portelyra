#!/usr/bin/env python3
"""Read-only multi-listing Daily Market History coverage."""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from migrations.reference.daily_market_history_v1 import DailyMarketHistoryBlocked, MarketHistoryContext, read_daily_market_history_v1
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA, STORE_NAME

DATE=re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
LISTING=re.compile(r"^lsr_[a-f0-9]{32}$")
REF=re.compile(r"^(?:asset|mapping)_ref_[0-9]{4,}$")
# Erster gespeicherter Kurstag einer Notierung auch vor dem angefragten Zeitraum (#557): Bewertet wird ab dort, nicht erst ab der
# ersten Buchung. Gesucht wird nur, wenn der Speicher den Beginn des Zeitraums erreicht, und hoechstens bis zu diesem Tag zurueck.
STORED_FLOOR="1990-01-01"
CODES=frozenset({"desktop_market_history_coverage_context_invalid","desktop_market_history_coverage_input_invalid","desktop_market_history_coverage_store_invalid","desktop_market_history_coverage_read_failed"})
class DesktopMarketHistoryCoverageV1Error(RuntimeError):
 def __init__(self,code:str):
  if code not in CODES: raise ValueError("desktop_market_history_coverage_error_unregistered")
  self.code=code;super().__init__(code)
def _abort(code): raise DesktopMarketHistoryCoverageV1Error(code)
def _date(value):
 if not isinstance(value,str) or DATE.fullmatch(value) is None:_abort("desktop_market_history_coverage_input_invalid")
 try: parsed=date.fromisoformat(value)
 except ValueError:_abort("desktop_market_history_coverage_input_invalid")
 if parsed.isoformat()!=value:_abort("desktop_market_history_coverage_input_invalid")
 return parsed
def _context(value):
 try:
  result=MarketHistoryContext(value["tenant_id"],value["user_id"],value["data_space_id"],"portfolio_reader","portfolio_worker")
 except (KeyError,TypeError):_abort("desktop_market_history_coverage_context_invalid")
 if not result.data_space_id.startswith("sbx_"):_abort("desktop_market_history_coverage_context_invalid")
 return result
def read_desktop_market_history_coverage_v1(data_space_path:Path|str,context:Mapping[str,str],bindings:Sequence[Mapping[str,str]],required_start_date:str,as_of_date:str)->dict[str,Any]:
 reader=_context(context);start=_date(required_start_date);end=_date(as_of_date)
 if end<start or (end-start).days>20000 or not isinstance(bindings,Sequence) or isinstance(bindings,(str,bytes)) or len(bindings)>10000:_abort("desktop_market_history_coverage_input_invalid")
 space=Path(data_space_path);store=space/MARKET_AREA/STORE_NAME
 if not space.is_absolute() or space.name!=reader.data_space_id or space.is_symlink() or not store.is_file() or store.is_symlink():_abort("desktop_market_history_coverage_store_invalid")
 rows=[];seen=set();validated=[]
 for binding in bindings:
  if not isinstance(binding,Mapping) or set(binding)!={"asset_ref","mapping_ref","listing_ref"}:_abort("desktop_market_history_coverage_input_invalid")
  asset_ref=binding["asset_ref"];mapping_ref=binding["mapping_ref"];listing_ref=binding["listing_ref"]
  if not isinstance(asset_ref,str) or not isinstance(mapping_ref,str) or REF.fullmatch(asset_ref) is None or REF.fullmatch(mapping_ref) is None or not isinstance(listing_ref,str) or LISTING.fullmatch(listing_ref) is None or asset_ref in seen:_abort("desktop_market_history_coverage_input_invalid")
  seen.add(asset_ref);validated.append((asset_ref,mapping_ref,listing_ref))
 for asset_ref,mapping_ref,listing_ref in validated:
  try: history=read_daily_market_history_v1(store,reader,listing_ref,required_start_date,as_of_date)
  except DailyMarketHistoryBlocked as error: raise DesktopMarketHistoryCoverageV1Error("desktop_market_history_coverage_read_failed") from error
  counts={key:0 for key in ("observed","non_trading_day","source_gap","not_requested")};covered=[];missing=[];observed_days=[]
  for day in history["days"]:
   counts[day["day_status"]]+=1
   if day["day_status"]=="observed":observed_days.append(day["trading_date"])
   if day["day_status"]!="not_requested":covered.append(day["trading_date"])
   else:missing.append(day["trading_date"])
  stored_first=min(observed_days) if observed_days else None
  if covered and min(covered)==required_start_date and required_start_date>STORED_FLOOR:
   before=(start-timedelta(days=1)).isoformat()
   try: earlier=read_daily_market_history_v1(store,reader,listing_ref,STORED_FLOOR,before)
   except DailyMarketHistoryBlocked as error: raise DesktopMarketHistoryCoverageV1Error("desktop_market_history_coverage_read_failed") from error
   earliest=[day["trading_date"] for day in earlier["days"] if day["day_status"]=="observed"]
   if earliest:stored_first=min(earliest)
  missing_ranges=[]
  for value in missing:
   current=date.fromisoformat(value)
   if not missing_ranges or (current-date.fromisoformat(missing_ranges[-1]["end_date"])).days!=1:missing_ranges.append({"start_date":value,"end_date":value,"calendar_day_count":1})
   else:missing_ranges[-1]["end_date"]=value;missing_ranges[-1]["calendar_day_count"]+=1
  rows.append({"asset_ref":asset_ref,"mapping_ref":mapping_ref,"requested_day_count":len(history["days"]),"first_covered_date":min(covered) if covered else None,"first_observed_date":min(observed_days) if observed_days else None,"first_stored_observed_date":stored_first,"last_covered_date":max(covered) if covered else None,"observed_day_count":counts["observed"],"non_trading_day_count":counts["non_trading_day"],"source_gap_day_count":counts["source_gap"],"missing_day_count":counts["not_requested"],"missing_range_count":len(missing_ranges),"missing_ranges":missing_ranges,"coverage_status":"complete" if counts["not_requested"]==0 and counts["source_gap"]==0 else "partial" if covered else "missing"})
 return {"contract_version":"desktop_market_history_coverage_v1","status":"ready","required_start_date":required_start_date,"as_of_date":as_of_date,"asset_count":len(rows),"rows":rows,"provider_access":False,"network_access":False,"market_history_write":False,"canonical_write":False,"paths_exposed":False,"listing_refs_exposed":False}
__all__=["DesktopMarketHistoryCoverageV1Error","read_desktop_market_history_coverage_v1"]
