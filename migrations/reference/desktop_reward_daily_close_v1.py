#!/usr/bin/env python3
"""Resolve persisted Reward valuation evidence without Provider access."""
from pathlib import Path
import hashlib,json,sqlite3
from datetime import date as Date,datetime,timedelta,timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from migrations.reference.desktop_activity_draft_v1 import read_desktop_activity_draft_v1,apply_confirmed_reward_valuation_evidence_v1
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1
from migrations.reference.daily_market_history_v1 import MarketHistoryContext,read_daily_market_history_v1
from migrations.reference.fx_history_v1 import FxHistoryContext,read_fx_pair_catalog_v1,read_fx_history_v1
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA,STORE_NAME as MARKET_STORE
from migrations.reference.desktop_fx_demand_coverage_v1 import STORE_AREA as FX_AREA,STORE_NAME as FX_STORE
from migrations.reference.reward_valuation_v1 import preview_reward_valuation_v1,preview_source_reward_fx_valuation_v1,confirm_reward_valuation_v1
from workers.reference.semantic_realized_fifo_v1 import context_values as semantic_context_values,public_ref as semantic_public_ref
CODES=frozenset({'desktop_reward_daily_close_input_invalid','desktop_reward_daily_close_asset_history_missing','desktop_reward_daily_close_fx_history_missing','desktop_reward_daily_close_ambiguous_listing'})
class DesktopRewardDailyCloseV1Error(RuntimeError):
 def __init__(self,code):self.code=code;super().__init__(code)
def _abort(c):raise DesktopRewardDailyCloseV1Error(c)
def _sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def _event_at(event):
 if event.get('effective_at_utc'):return event['effective_at_utc']
 try:return datetime.fromisoformat(event['local_date']+'T'+event['local_time']).replace(tzinfo=ZoneInfo(event['time_zone'])).astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
 except Exception:_abort('desktop_reward_daily_close_input_invalid')
def _quantity(event):return format(Decimal(event['quantity_decimal'])-Decimal(event.get('asset_fee_quantity_decimal') or '0'),'f')
def _fx(root,context,base_currency,valuation_currency,local_date):
 fr=FxHistoryContext(context['tenant_id'],context['user_id'],context['data_space_id'],'portfolio_reader','portfolio_worker');store=root/FX_AREA/FX_STORE
 pairs=[p for p in read_fx_pair_catalog_v1(store,fr)['pairs'] if {p['base_currency'],p['quote_currency']}=={base_currency,valuation_currency}]
 if len(pairs)!=1:_abort('desktop_reward_daily_close_fx_history_missing')
 start=(Date.fromisoformat(local_date)-timedelta(days=3)).isoformat();observed=[v for v in read_fx_history_v1(store,fr,pairs[0]['pair_ref'],start,local_date)['days'] if v['day_status']=='observed']
 if not observed:_abort('desktop_reward_daily_close_fx_history_missing')
 rate=observed[-1];rate_date=rate['rate_date'];age=(Date.fromisoformat(local_date)-Date.fromisoformat(rate_date)).days
 return {'evidence_kind':'fx_rate','observation_mode':'daily_close_fallback','observation_date':rate_date,'observed_at_utc':None,'currency':valuation_currency,'base_currency':pairs[0]['base_currency'],'quote_currency':pairs[0]['quote_currency'],'value_decimal':rate['rate_decimal'],'selection_basis':'exact_date' if age==0 else 'prior_observation','rate_age_days':age,'evidence_fingerprint':hashlib.sha256((pairs[0]['pair_ref']+'|'+rate['revision_ref']).encode()).hexdigest()}
def preview_desktop_reward_daily_close_v1(space,context,draft_ref,valuation_currency='EUR'):
 root=Path(space);ctx=DesktopProductAssetActivityContextV1(context['tenant_id'],context['user_id'],context['data_space_id'],context['actor_id'],'desktop_owner');draft=read_desktop_activity_draft_v1(root,ctx,draft_ref)['trusted_draft'];event=draft['event'];aux=draft.get('source_auxiliary',{});ve=aux.get('valuation_evidence',{})
 if event.get('event_type')!='reward' or aux.get('confirmed_reward_valuation') is not None:_abort('desktop_reward_daily_close_input_invalid')
 event_at=_event_at(event);qty=_quantity(event);origin=ve.get('valuation_origin')
 if origin=='source_provided' and event.get('basis_evidence_mode')=='basis_missing' and ve.get('price_currency')!=valuation_currency and ve.get('source_value_mode') in {'fiat_total','unit_price'}:
  fx=_fx(root,context,ve['price_currency'],valuation_currency,event['local_date']);mode='source_fiat_total_fx' if ve['source_value_mode']=='fiat_total' else 'source_unit_price_fx';source_value=ve['source_fiat_total_decimal'] if ve['source_value_mode']=='fiat_total' else ve['source_unit_price_decimal'];source_fp=_sha({'valuation_evidence':ve,'source_binding_fingerprint':draft['source_binding']['binding_fingerprint']})
  req={'mode':mode,'event_type':'reward','local_date':event['local_date'],'event_at_utc':event_at,'eligible_quantity_decimal':qty,'asset_currency':'AST','source_currency':ve['price_currency'],'valuation_currency':valuation_currency,'source_value_decimal':source_value,'source_evidence_fingerprint':source_fp};candidate=preview_source_reward_fx_valuation_v1(req,fx)
 elif origin=='source_missing':
  store=root/MARKET_AREA/MARKET_STORE;_,_,_,context_fp=semantic_context_values({'tenant_id':context['tenant_id'],'user_id':context['user_id'],'data_space_id':context['data_space_id']});public_asset_ref=semantic_public_ref('asf_',context_fp,event['asset_ref'])
  try:
   c=sqlite3.connect(f'file:{store}?mode=ro',uri=True);c.row_factory=sqlite3.Row;rows=c.execute('select listing_ref,quote_currency,bound_at_utc from market_listing_binding where asset_ref=? order by bound_at_utc desc,listing_ref desc',(public_asset_ref,)).fetchall();c.close()
  except sqlite3.Error:_abort('desktop_reward_daily_close_asset_history_missing')
  reader=MarketHistoryContext(context['tenant_id'],context['user_id'],context['data_space_id'],'portfolio_reader','portfolio_worker');observed=[]
  for listing in rows:
   try:
    day=read_daily_market_history_v1(store,reader,listing['listing_ref'],event['local_date'],event['local_date'])['days'][0]
    if day['day_status']=='observed':observed.append((listing,day))
   except Exception:pass
  if not observed:_abort('desktop_reward_daily_close_asset_history_missing')
  listing,day=observed[0];quote=listing['quote_currency'];fx=None if quote==valuation_currency else _fx(root,context,quote,valuation_currency,event['local_date']);asset={'evidence_kind':'asset_price','observation_mode':'daily_close_fallback','observation_date':event['local_date'],'observed_at_utc':None,'currency':quote,'value_decimal':day['close_decimal'],'evidence_fingerprint':hashlib.sha256((listing['listing_ref']+'|'+day['market_day_revision_ref']).encode()).hexdigest()};req={'mode':'daily_close_fallback','event_type':'reward','local_date':event['local_date'],'event_at_utc':event_at,'eligible_quantity_decimal':qty,'asset_currency':'AST','quote_currency':quote,'valuation_currency':valuation_currency};candidate=preview_reward_valuation_v1(req,asset,fx)
 else:_abort('desktop_reward_daily_close_input_invalid')
 fields=('status','mode','local_date','eligible_quantity_decimal','valuation_currency','unit_price_decimal','fiat_total_decimal','fx_route','fx_observation_date','fx_rate_age_days','fx_selection_basis','fallback_confirmation_required','provider_access','activity_draft_write','canonical_write');return {'trusted_candidate':candidate,'public_preview':{k:candidate.get(k) for k in fields},'draft_revision':draft['revision']}
def apply_desktop_reward_daily_close_v1(space,context,draft_ref,draft_revision,candidate,confirmed,updated_at_utc):
 evidence=confirm_reward_valuation_v1(candidate,confirmed);ctx=DesktopProductAssetActivityContextV1(context['tenant_id'],context['user_id'],context['data_space_id'],context['actor_id'],'desktop_owner');return apply_confirmed_reward_valuation_evidence_v1(space,ctx,draft_ref,draft_revision,evidence,updated_at_utc)
__all__=['DesktopRewardDailyCloseV1Error','preview_desktop_reward_daily_close_v1','apply_desktop_reward_daily_close_v1']
