#!/usr/bin/env python3
"""Provider-free missing/range planner for one promoted Daily Market Listing."""
from __future__ import annotations
from datetime import date,timedelta
from pathlib import Path
import re
from typing import Any,Mapping
from migrations.reference.daily_market_history_v1 import DailyMarketHistoryBlocked,MarketHistoryContext,read_daily_market_day_confirmations_v1,read_daily_market_history_v1
from migrations.reference.desktop_provider_probe_promotion_v1 import STORE_NAME,MARKET_AREA
from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1
from migrations.reference.market_day_completion_v1 import completed_at_v1,completed_through_v1
from migrations.reference.user_settings_v1 import UserSettingsV1Error,read_market_day_completion_v1
MODES=frozenset({'incremental','retry_source_gaps','full_refresh'});DATE=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$');LISTING=re.compile(r'^lsr_[a-f0-9]{32}$')
FAILURE_CODES=frozenset({'desktop_market_history_plan_context_invalid','desktop_market_history_plan_input_invalid','desktop_market_history_plan_store_invalid','desktop_market_history_plan_read_failed'})
class DesktopMarketHistoryPlanV1Error(RuntimeError):
 def __init__(self,code):
  if code not in FAILURE_CODES:raise ValueError('desktop_market_history_plan_error_unregistered')
  self.code=code;super().__init__(code)
def desktop_market_history_plan_v1_error_codes():return tuple(sorted(FAILURE_CODES))
def _abort(code):raise DesktopMarketHistoryPlanV1Error(code)
def _context(value):
 if isinstance(value,Mapping):
  try:value=DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
  except (KeyError,TypeError) as error:raise DesktopMarketHistoryPlanV1Error('desktop_market_history_plan_context_invalid') from error
 if not isinstance(value,DesktopProviderSearchContextV1) or value.actor_id!='market_worker' or value.role!='market_worker' or not value.data_space_id.startswith('sbx_'):_abort('desktop_market_history_plan_context_invalid')
 return value
def _date(value):
 if not isinstance(value,str) or DATE.fullmatch(value) is None:_abort('desktop_market_history_plan_input_invalid')
 try:result=date.fromisoformat(value)
 except ValueError:_abort('desktop_market_history_plan_input_invalid')
 if result.isoformat()!=value:_abort('desktop_market_history_plan_input_invalid')
 return result
def _ranges(values):
 if not values:return []
 parsed=sorted(date.fromisoformat(item) for item in values);result=[];start=previous=parsed[0]
 for item in parsed[1:]:
  if item!=previous+timedelta(days=1):result.append((start,previous));start=item
  previous=item
 result.append((start,previous));return [{'start_date':start.isoformat(),'end_date':end.isoformat(),'calendar_day_count':(end-start).days+1} for start,end in result]
def plan_desktop_market_history_v1(data_space_path,context,listing_ref,required_start_date,as_of_date,mode='incremental',now_utc=None):
 context=_context(context);start=_date(required_start_date);end=_date(as_of_date)
 if end<start or (end-start).days>20000 or mode not in MODES or not isinstance(listing_ref,str) or LISTING.fullmatch(listing_ref) is None:_abort('desktop_market_history_plan_input_invalid')
 space=Path(data_space_path);store=space/MARKET_AREA/STORE_NAME
 try:
  if not space.is_absolute() or space.name!=context.data_space_id or space.is_symlink() or not store.is_file() or store.is_symlink():_abort('desktop_market_history_plan_store_invalid')
  reader=MarketHistoryContext(context.tenant_id,context.user_id,context.data_space_id,'portfolio_reader','portfolio_worker');history=read_daily_market_history_v1(store,reader,listing_ref,required_start_date,as_of_date)
 except DesktopMarketHistoryPlanV1Error:raise
 except DailyMarketHistoryBlocked as error:raise DesktopMarketHistoryPlanV1Error('desktop_market_history_plan_read_failed') from error
 # Geplant wird nur bis zum juengsten abgeschlossenen Tag (#475); ein laufender Tag kaeme sonst als Tageswert in den Speicher
 # und gaelte danach als vorhanden. Boersen gelten je nach Einstellung eine Stunde nach Handelsschluss als abgeschlossen (#516).
 try:completion_mode=read_market_day_completion_v1(space,context)
 except UserSettingsV1Error as error:raise DesktopMarketHistoryPlanV1Error('desktop_market_history_plan_read_failed') from error
 market_code=history['market_code']
 completed=completed_through_v1(history['timezone_name'],now_utc,market_code=market_code,mode=completion_mode);end_date=min(as_of_date,completed)
 target_status={'incremental':{'not_requested'},'retry_source_gaps':{'source_gap'},'full_refresh':{'observed','non_trading_day','source_gap'}}[mode]
 # Vorlaeufig ist ein Kurs oder eine Luecke, die abgerufen wurde, bevor der Tag abgeschlossen war - und die kein spaeterer Abruf
 # bestaetigt hat. 'Nur fehlende Tage' fordert sie erneut an; der Abgleich beim Veroeffentlichen korrigiert oder bestaetigt (#475).
 provisional=set()
 if mode=='incremental':
  timezone_name=history['timezone_name'];suspects={row['trading_date'] for row in history['days'] if row['day_status'] in ('observed','source_gap') and row['trading_date']<=end_date and (row['retrieved_at_utc'] or '')<completed_at_v1(row['trading_date'],timezone_name,market_code=market_code,mode=completion_mode)}
  if suspects:
   try:confirmed=read_daily_market_day_confirmations_v1(store,reader,listing_ref,sorted(suspects))
   except DailyMarketHistoryBlocked as error:raise DesktopMarketHistoryPlanV1Error('desktop_market_history_plan_read_failed') from error
   provisional={day for day in suspects if confirmed.get(day,'')<completed_at_v1(day,timezone_name,market_code=market_code,mode=completion_mode)}
 targets=[row['trading_date'] for row in history['days'] if (row['day_status'] in target_status or row['trading_date'] in provisional) and row['trading_date']<=end_date];ranges=_ranges(targets)
 return {'contract_version':'desktop_market_history_plan_v1','status':'ready','mode':mode,'required_start_date':required_start_date,'as_of_date':end_date,'requested_as_of_date':as_of_date,'completed_through':completed,'completion_mode':completion_mode,'provisional_day_count':len(provisional),'target_day_count':len(targets),'range_count':len(ranges),'ranges':ranges,'provider_run_required':bool(ranges),'provider_access':False,'network_access':False,'market_history_write':False,'canonical_write':False,'automatic_retry':False,'listing_ref_exposed':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}
__all__=['DesktopMarketHistoryPlanV1Error','desktop_market_history_plan_v1_error_codes','plan_desktop_market_history_v1']
