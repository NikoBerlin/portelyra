"""Pure ADR-168 reward/account-scoped import preview; no file or write authority."""
from __future__ import annotations
from datetime import datetime,timezone
from fractions import Fraction
import hashlib,json,re
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from typing import Any
_DEC=re.compile(r'^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$');_TOKEN=re.compile(r'^[^\x00\r\n]{1,240}$')
MODES=frozenset({'basis_missing','manual_fiat_total','manual_unit_price','provider_price_planned'})
DEFERRED=frozenset({'nonreward_trade_deferred','manual_account_transfer_deferred','cash_domain_deferred','diagnostic'})
class RewardAccountImportPreviewError(RuntimeError):
 def __init__(self,code):self.code=code;super().__init__(code)
def _fail(c):raise RewardAccountImportPreviewError(c)
def _decimal(x):
 if not isinstance(x,str) or len(x)>240 or _DEC.fullmatch(x) is None:_fail('reward_account_import_decimal_invalid')
 whole,fraction=(x.split('.',1)+[''])[:2] if '.' in x else (x,'')
 return Fraction(int(whole+fraction),10**len(fraction))
def _text(x):
 if not isinstance(x,str) or _TOKEN.fullmatch(x) is None:_fail('reward_account_import_input_invalid')
 return x
def _norm(x):
 if not isinstance(x,Fraction) or x<0:_fail('reward_account_import_decimal_invalid')
 whole,remainder=divmod(x.numerator,x.denominator)
 if remainder==0:return str(whole)
 digits=[]
 while remainder:
  digit,remainder=divmod(remainder*10,x.denominator);digits.append(str(digit))
 return str(whole)+'.'+''.join(digits)
def _event_utc(value,format_code,zone):
 try:
  fraction=re.search(r'\.(\d+)',value)
  if fraction is not None and len(fraction.group(1))>6:_fail('reward_account_import_time_invalid')
  if format_code=='ymd_space_hms':parsed=datetime.strptime(value,'%Y-%m-%d %H:%M:%S').replace(tzinfo=zone)
  elif format_code=='ymd_space_hms_fraction':parsed=datetime.strptime(value,'%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=zone)
  elif format_code=='iso_utc':parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
  elif format_code=='iso_offset':parsed=datetime.fromisoformat(value)
  else:_fail('reward_account_import_time_invalid')
  if format_code in {'iso_utc','iso_offset'} and parsed.astimezone(zone).utcoffset()!=parsed.utcoffset():_fail('reward_account_import_time_zone_invalid')
  utc=parsed.astimezone(timezone.utc);base=utc.strftime('%Y-%m-%dT%H:%M:%S');fraction_text=f'{utc.microsecond:06d}'.rstrip('0');return base+(('.'+fraction_text) if fraction_text else '')+'Z'
 except (ValueError,TypeError):_fail('reward_account_import_time_invalid')
def _hash(domain,x):return hashlib.sha256(json.dumps({'domain':domain,'value':x},ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def build_reward_account_import_preview_v2(rows:list[dict[str,str]],selection:dict[str,Any],catalog:dict[str,Any],valuations:dict[str,dict[str,str]]):
 required={'event_time_format','exact_local_zone','fee_sign_convention','price_currency','reward_tuple','route_decisions','source_account','source_asset','target_account_option_key','target_asset_option_key'}
 if not isinstance(rows,list) or not rows or set(selection)!=required or selection['fee_sign_convention']!='nonnegative_fee_subtracted':_fail('reward_account_import_input_invalid')
 if not isinstance(catalog,dict) or set(catalog)!={'account_options','asset_options','selected_portfolio_option_key'}:_fail('reward_account_import_catalog_mapping_invalid')
 portfolio=catalog['selected_portfolio_option_key'];assets=catalog['asset_options'];accounts=catalog['account_options']
 if not isinstance(assets,list) or not isinstance(accounts,list) or not isinstance(portfolio,str):_fail('reward_account_import_catalog_mapping_invalid')
 asset_matches=[x for x in assets if isinstance(x,dict) and x.get('option_key')==selection['target_asset_option_key'] and x.get('portfolio_option_key')==portfolio]
 account_matches=[x for x in accounts if isinstance(x,dict) and x.get('option_key')==selection['target_account_option_key'] and x.get('portfolio_option_key')==portfolio and selection['target_asset_option_key'] in x.get('supported_asset_option_keys',[])]
 if len(asset_matches)!=1 or len(account_matches)!=1:_fail('reward_account_import_catalog_mapping_invalid')
 for k in ('source_account','source_asset','price_currency'):_text(selection[k])
 try:zone=ZoneInfo(selection['exact_local_zone'])
 except (ZoneInfoNotFoundError,TypeError):_fail('reward_account_import_time_zone_invalid')
 reward_tuple=selection['reward_tuple']
 if not isinstance(reward_tuple,list) or len(reward_tuple)!=3 or any(not isinstance(x,str) for x in reward_tuple):_fail('reward_account_import_route_invalid')
 routes=selection['route_decisions'];seen=set();result=[];eligible_ids=[]
 required_row={'source_row_id','event_time_text','source_type','source_subtype','asset_class','source_asset_key','source_account_key','signed_quantity_decimal','asset_fee_quantity_decimal'}
 ids=[]
 for row in rows:
  if set(row)!=required_row:_fail('reward_account_import_input_invalid')
  txid=_text(row['source_row_id']);ids.append(txid)
 if len(ids)!=len(set(ids)):_fail('reward_account_import_identity_invalid')
 for row in rows:
  txid=row['source_row_id'];key='|'.join([row['source_type'],row['source_subtype'],row['asset_class']])
  if key not in routes or routes[key] not in DEFERRED|{'reward'}:_fail('reward_account_import_route_invalid')
  route=routes[key];disposition=route
  if route=='reward':
   if [row['source_type'],row['source_subtype'],row['asset_class']]!=reward_tuple:_fail('reward_account_import_route_invalid')
   if row['source_asset_key']!=selection['source_asset']:disposition='other_source_asset_deferred'
   elif row['source_account_key']!=selection['source_account']:disposition='other_source_account_deferred'
   else:disposition='reward_candidate_disabled';eligible_ids.append(txid)
  item={'disposition':disposition,'source_identity_sha256':_hash('reward_source_identity',txid)}
  if disposition=='reward_candidate_disabled':
   gross=_decimal(row['signed_quantity_decimal']);fee=_decimal(row['asset_fee_quantity_decimal'])
   if gross<0 or fee<0 or fee>gross:_fail('reward_account_import_quantity_invalid')
   net=gross-fee
   utc=_event_utc(row['event_time_text'],selection['event_time_format'],zone)
   valuation=valuations.get(txid,{'mode':'basis_missing'});mode=valuation.get('mode')
   if mode not in MODES:_fail('reward_account_import_valuation_invalid')
   fiat=None;unit=None
   if mode=='manual_fiat_total':
    if set(valuation)!={'mode','fiat_total_decimal'}:_fail('reward_account_import_valuation_invalid')
    fiat=_norm(_decimal(valuation.get('fiat_total_decimal')))
   elif mode=='manual_unit_price':
    if set(valuation)!={'mode','unit_price_decimal'}:_fail('reward_account_import_valuation_invalid')
    unit=_decimal(valuation.get('unit_price_decimal'));fiat=_norm(net*unit);unit=_norm(unit)
   elif mode in {'basis_missing','provider_price_planned'} and set(valuation)!={'mode'}:_fail('reward_account_import_valuation_invalid')
   item['candidate']={'account_option_key':selection['target_account_option_key'],'asset_fee_quantity_decimal':_norm(fee),'asset_option_key':selection['target_asset_option_key'],'event_time_utc':utc,'fiat_currency':selection['price_currency'],'fiat_unit_price_decimal':unit,'reward_fiat_value_before_tax_after_fee':fiat,'reward_quantity_gross_decimal':_norm(gross),'reward_quantity_net_decimal':_norm(net),'status':'disabled_preview','valuation_mode':mode}
  result.append(item)
 if set(valuations)-set(eligible_ids):_fail('reward_account_import_valuation_invalid')
 counts={}
 for x in result:counts[x['disposition']]=counts.get(x['disposition'],0)+1
 return {'activation_authorized':False,'candidate_generation_authorized':False,'rows':result,'row_count':len(rows),'selected_source_account_sha256':_hash('source_account',selection['source_account']),'selected_source_asset_sha256':_hash('source_asset',selection['source_asset']),'silent_drop_count':0,'source_balance_disposition':'source_balance_not_used_portelyra_recalculates','status':'reward_account_import_preview_disabled','target_account_option_key':selection['target_account_option_key'],'target_asset_option_key':selection['target_asset_option_key'],'terminal_disposition_counts':counts,'version':2}
