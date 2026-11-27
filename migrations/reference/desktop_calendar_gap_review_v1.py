#!/usr/bin/env python3
"""FX calendar profile binding and one-gap correction Product orchestration."""
from datetime import datetime,timezone
from pathlib import Path
from typing import Mapping,Sequence
from contextlib import contextmanager
import sqlite3, os
from migrations.reference import market_calendar_registry_v1 as registry
from migrations.reference.fx_history_v1 import FxHistoryContext,read_fx_pair_catalog_v1,read_fx_history_v1
from migrations.reference.desktop_fx_demand_coverage_v1 import STORE_AREA,STORE_NAME
from migrations.reference.market_calendar_v1 import build_market_calendar_profile_v1
from migrations.reference.market_valuation_calendar_v1 import propose_calendar
from migrations.reference.daily_market_history_v1 import read_daily_market_history_v1, MarketHistoryContext
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA, STORE_NAME as MARKET_STORE
from migrations.reference.market_calendar_registry_v1 import *
from migrations.reference.market_calendar_correction_v1 import *
CODES=frozenset({'desktop_calendar_gap_review_input_invalid','desktop_calendar_gap_review_pair_missing','desktop_calendar_gap_review_preview_invalid'})
class DesktopCalendarGapReviewV1Error(RuntimeError):
 def __init__(self,code):self.code=code;super().__init__(code)
def _abort(c):raise DesktopCalendarGapReviewV1Error(c)
def _pair(space,ctx,source,target):
 reader=FxHistoryContext(ctx['tenant_id'],ctx['user_id'],ctx['data_space_id'],'portfolio_reader','portfolio_worker');matches=[p for p in read_fx_pair_catalog_v1(Path(space)/STORE_AREA/STORE_NAME,reader)['pairs'] if {p['base_currency'],p['quote_currency']}=={source,target}]
 if len(matches)!=1:_abort('desktop_calendar_gap_review_pair_missing')
 return matches[0],reader
def preview_desktop_fx_calendar_binding_v1(space,ctx,source,target,closure_dates,valid_from,valid_to,created):
 pair,reader=_pair(space,ctx,source,target)
 if not isinstance(closure_dates,list) or not 1 <= len(closure_dates) <= 10000 or any(not isinstance(d,str) for d in closure_dates):_abort('desktop_calendar_gap_review_input_invalid')
 history=read_fx_history_v1(Path(space)/STORE_AREA/STORE_NAME,reader,pair['pair_ref'],valid_from,valid_to);gaps={x['rate_date'] for x in history['days'] if x['day_status']=='source_gap'}
 if len(set(closure_dates))!=len(closure_dates) or not set(closure_dates)<=gaps:_abort('desktop_calendar_gap_review_input_invalid')
 profile=build_market_calendar_profile_v1(profile_version=1,calendar_kind='weekly_sessions',market_code=pair['market_code'],timezone_name=pair['timezone_name'],valid_from=valid_from,valid_to=valid_to,session_weekdays=[1,2,3,4,5],closure_dates=[{'date':d,'reason':'owner_reviewed_provider_closure'} for d in sorted(closure_dates)],special_open_dates=[],source_kind='reviewed_manifest',source_ref='desktop_fx_calendar_review_v1');trusted=preview_market_calendar_extension_v1(space,ctx,profile,'fx_pair',pair['pair_ref'],created,source_fingerprint=registry._sha(history));return trusted,public_market_calendar_binding_preview_v1(trusted)
def apply_desktop_fx_calendar_binding_v1(space,ctx,trusted,public,confirmed,completed):return apply_desktop_calendar_binding_v1(space,ctx,trusted,public,confirmed,completed)
def preview_desktop_fx_calendar_correction_v1(space,ctx,source,target,day,created):pair,_=_pair(space,ctx,source,target);trusted=preview_market_calendar_correction_v1(space,ctx,'fx_pair',pair['pair_ref'],day,created);return trusted,public_market_calendar_correction_preview_v1(trusted)
def apply_desktop_fx_calendar_correction_v1(space,ctx,trusted,public,confirmed,completed):return apply_market_calendar_correction_v1(space,ctx,trusted,public,confirmed,completed)
def preview_desktop_listing_calendar_binding_v1(space,ctx,listing_ref,closure_dates,valid_from,valid_to,created):
 reader=MarketHistoryContext(ctx['tenant_id'],ctx['user_id'],ctx['data_space_id'],'portfolio_reader','portfolio_worker')
 history=read_daily_market_history_v1(Path(space)/MARKET_AREA/MARKET_STORE,reader,listing_ref,valid_from,valid_to)
 if not isinstance(closure_dates,list) or not closure_dates or len(closure_dates)>10000 or any(not isinstance(d,str) for d in closure_dates) or len(set(closure_dates))!=len(closure_dates):_abort('desktop_calendar_gap_review_input_invalid')
 proposed=propose_calendar(history,valid_from,valid_to,[],use_rules=True)['profile']
 rules={x['date']:x for x in proposed['closure_dates']}
 eligible={x['trading_date'] for x in history['days'] if x['day_status']=='source_gap' or (x['day_status']=='non_trading_day' and x.get('quality_status')=='calendar_confirmed')}
 if not set(closure_dates)<=eligible or not set(closure_dates)<=set(rules):_abort('desktop_calendar_gap_review_input_invalid')
 profile=build_market_calendar_profile_v1(profile_version=1,calendar_kind=proposed['calendar_kind'],market_code=history['market_code'],timezone_name=history['timezone_name'],valid_from=valid_from,valid_to=valid_to,session_weekdays=proposed['session_weekdays'],closure_dates=[rules[d] for d in sorted(closure_dates)],special_open_dates=[],source_kind='reviewed_manifest',source_ref=proposed['source_ref'])
 trusted=preview_market_calendar_extension_v1(space,ctx,profile,'listing',listing_ref,created,source_fingerprint=registry._sha(history))
 return trusted,public_market_calendar_binding_preview_v1(trusted)

@contextmanager
def _history_guard(space, ctx, kind):
 # Pin the native source read snapshot until the separately confirmed calendar
 # transaction commits. No recovery, immutable-mode read, or history writes.
 space=registry._space(space,registry._ctx(ctx,True))
 area,name=(MARKET_AREA,MARKET_STORE) if kind=='listing' else (STORE_AREA,STORE_NAME)
 registry._private(space/area,True);store=space/area/name;registry._private(store)
 if any(os.path.lexists(Path(str(store)+suffix)) for suffix in ('-wal','-shm','-journal')):_abort('desktop_calendar_gap_review_preview_invalid')
 with store.open('rb') as f:header=f.read(20)
 if not header.startswith(b'SQLite format 3\x00') or header[18:20]!=b'\x01\x01':_abort('desktop_calendar_gap_review_preview_invalid')
 con=sqlite3.connect(store.as_uri()+'?mode=ro',uri=True,timeout=0)
 try:
  con.execute('PRAGMA query_only=ON');con.execute('BEGIN');con.execute('SELECT count(*) FROM sqlite_master').fetchone()
  yield
 finally:con.close()

def apply_desktop_calendar_binding_v1(space,ctx,trusted,public,confirmed,completed):
 if confirmed is not True:raise MarketCalendarRegistryV1Error('market_calendar_registry_confirmation_required')
 # Old replacement candidates must be prepared anew in this Product workflow.
 if trusted.get('contract_version')!='market_calendar_binding_extension_v1':_abort('desktop_calendar_gap_review_preview_invalid')
 if public!=public_market_calendar_binding_preview_v1(trusted):_abort('desktop_calendar_gap_review_preview_invalid')
 with _history_guard(space,ctx,trusted['scope_kind']):
  p=trusted['extension']['addition_profile'];dates=[x['date'] for x in p['closure_dates']]
  if trusted['scope_kind']=='listing':
   fresh,_=preview_desktop_listing_calendar_binding_v1(space,ctx,trusted['scope_ref'],dates,p['valid_from'],p['valid_to'],trusted['created_at_utc'])
  elif trusted['scope_kind']=='fx_pair':
   reader=FxHistoryContext(ctx['tenant_id'],ctx['user_id'],ctx['data_space_id'],'portfolio_reader','portfolio_worker')
   pairs=[x for x in read_fx_pair_catalog_v1(Path(space)/STORE_AREA/STORE_NAME,reader)['pairs'] if x['pair_ref']==trusted['scope_ref']]
   if len(pairs)!=1:_abort('desktop_calendar_gap_review_pair_missing')
   pair=pairs[0]
   fresh,_=preview_desktop_fx_calendar_binding_v1(space,ctx,pair['base_currency'],pair['quote_currency'],dates,p['valid_from'],p['valid_to'],trusted['created_at_utc'])
  else:_abort('desktop_calendar_gap_review_input_invalid')
  if fresh!=trusted:_abort('desktop_calendar_gap_review_preview_invalid')
  return apply_market_calendar_binding_v1(space,ctx,trusted,public,confirmed,completed)

__all__=['preview_desktop_listing_calendar_binding_v1','apply_desktop_calendar_binding_v1','preview_market_calendar_correction_v1','public_market_calendar_correction_preview_v1','DesktopCalendarGapReviewV1Error','preview_desktop_fx_calendar_binding_v1','apply_desktop_fx_calendar_binding_v1','preview_desktop_fx_calendar_correction_v1','apply_desktop_fx_calendar_correction_v1']
