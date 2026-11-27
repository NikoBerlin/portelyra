#!/usr/bin/env python3
"""Promote confirmed Provider-probe evidence into append-only Daily Market History."""
from __future__ import annotations
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
import hashlib,json,os,re,stat
from pathlib import Path
from typing import Any,Mapping
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

from migrations.reference.desktop_provider_probe_v1 import history_provider_v1,read_desktop_provider_probe_evidence_v1
from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1
from migrations.reference.daily_market_history_v1 import (
 DailyMarketHistoryBlocked,MarketHistoryContext,append_daily_market_history_v1,
 bind_daily_market_listing_v1,bootstrap_daily_market_history_store_v1,
 daily_market_history_job_binding_fingerprint_v1,new_daily_market_listing_binding_v1,
 seal_daily_market_history_candidate_v1,
)
from workers.reference.semantic_realized_fifo_v1 import context_values as semantic_context_values,public_ref as semantic_public_ref

AREA='provider-probe-v1';MARKET_AREA='daily-market-history-v1';STORE_NAME='daily-market-history.sqlite'
FAILURE_CODES=frozenset({
 'desktop_provider_promotion_boundary_failed','desktop_provider_promotion_confirmation_required',
 'desktop_provider_promotion_context_invalid','desktop_provider_promotion_input_invalid',
 'desktop_provider_promotion_preview_invalid','desktop_provider_promotion_attempt_consumed',
 'desktop_provider_promotion_probe_invalid','desktop_provider_promotion_store_invalid',
 'desktop_provider_promotion_history_write_failed','desktop_provider_promotion_result_invalid',
})
SHA=re.compile(r'^[a-f0-9]{64}$');REQUEST=re.compile(r'^pbr_[a-f0-9]{32}$');MARKET=re.compile(r'^[A-Z0-9_]{2,16}$');UTC=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$');CALENDARS=frozenset({'weekday_exchange','continuous_24_7','bank_business_day','custom_reviewed'})
class DesktopProviderPromotionV1Error(RuntimeError):
 def __init__(self,code):
  if code not in FAILURE_CODES:raise ValueError('desktop_provider_promotion_error_unregistered')
  self.code=code;super().__init__(code)
def desktop_provider_promotion_v1_error_codes():return tuple(sorted(FAILURE_CODES))
def _abort(code):raise DesktopProviderPromotionV1Error(code)
def _canonical(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
def _sha(value):return hashlib.sha256(value if isinstance(value,bytes) else _canonical(value)).hexdigest()
def _context(value):
 if isinstance(value,Mapping):
  try:value=DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
  except (KeyError,TypeError) as error:raise DesktopProviderPromotionV1Error('desktop_provider_promotion_context_invalid') from error
 if not isinstance(value,DesktopProviderSearchContextV1) or value.actor_id!='market_worker' or value.role!='market_worker' or not value.data_space_id.startswith('sbx_') or any(not isinstance(item,str) or re.fullmatch(r'^[A-Za-z0-9_-]{3,64}$',item) is None for item in (value.tenant_id,value.user_id,value.data_space_id)):_abort('desktop_provider_promotion_context_invalid')
 return value
def _context_fp(value):
 value=_context(value);return _sha({'contract':'desktop_provider_promotion_context_v1','tenant_id':value.tenant_id,'user_id':value.user_id,'data_space_id':value.data_space_id,'actor_id':value.actor_id,'role':value.role})
def _utc(value):
 if not isinstance(value,str) or UTC.fullmatch(value) is None:_abort('desktop_provider_promotion_input_invalid')
 try:parsed=datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
 except ValueError:_abort('desktop_provider_promotion_input_invalid')
 if parsed.strftime('%Y-%m-%dT%H:%M:%SZ')!=value:_abort('desktop_provider_promotion_input_invalid')
 return value
def _owner_dir(path):
 path=Path(path)
 try:info=path.stat(follow_symlinks=False);resolved=path.resolve(strict=True)
 except OSError:_abort('desktop_provider_promotion_store_invalid')
 if not path.is_absolute() or path.is_symlink() or resolved!=path or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.geteuid():_abort('desktop_provider_promotion_store_invalid')
 return path
def _ensure(parent,name):
 parent=_owner_dir(parent);path=parent/name
 if not path.exists():
  try:os.mkdir(path,0o700);os.chmod(path,0o700)
  except OSError:_abort('desktop_provider_promotion_store_invalid')
 return _owner_dir(path)
def _write(path,value):
 descriptor=None
 try:
  descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.write(descriptor,_canonical(value)+b'\n');os.fsync(descriptor);os.close(descriptor);descriptor=None
 except FileExistsError:_abort('desktop_provider_promotion_attempt_consumed')
 except DesktopProviderPromotionV1Error:raise
 except OSError:_abort('desktop_provider_promotion_store_invalid')
 finally:
  if descriptor is not None:os.close(descriptor)
def _mapping(value):
 required={'mapping_id','mapping_revision','asset_id','provider_id','provider_symbol','provider_currency','capability','mapping_fingerprint','catalog_fingerprint'}
 if not isinstance(value,Mapping) or set(value)!=required or history_provider_v1(value.get('provider_id')) is None or value.get('capability')!='daily_history' or not isinstance(value.get('mapping_revision'),int) or value['mapping_revision']<1 or not isinstance(value.get('mapping_fingerprint'),str) or SHA.fullmatch(value['mapping_fingerprint']) is None or not isinstance(value.get('catalog_fingerprint'),str) or SHA.fullmatch(value['catalog_fingerprint']) is None:_abort('desktop_provider_promotion_input_invalid')
 return dict(value)
def _dates(start,end):return [(start+timedelta(days=index)).isoformat() for index in range((end-start).days+1)]
def _inconsistent(source):
 """Ein Tagesbalken, dessen Spanne die Eckwerte nicht einschliesst.

 Eine Quelle kann einen Balken liefern, dessen Schlusskurs um den Faktor zehn
 verrutscht ist. Der Kursspeicher weist einen solchen Balken zu Recht ab; bisher
 fiel damit die ganze Antwort. Der Tag gilt jetzt als
 Quellluecke: Er wird fortgeschrieben und als Ersatzwert gekennzeichnet, die
 uebrigen Tage landen im Bestand. Welcher der vier Werte falsch ist, laesst
 sich nicht entscheiden - deshalb keiner von ihnen (#283).
 """
 values=[source.get(field) for field in ('open_decimal','high_decimal','low_decimal','close_decimal')]
 if any(value is None for value in values):return False
 try:opened,high,low,close=(Decimal(str(value)) for value in values)
 except (ArithmeticError,ValueError):return True
 return low>min(opened,close) or high<max(opened,close) or low>high
def _day(probe,date_text,calendar):
 source=probe.get(date_text);observed_at=probe['_completed_at_utc']
 unusable=source is not None and source['day_status']=='observed' and _inconsistent(source)
 if source is not None and source['day_status']=='observed' and not unusable:
  complete=all(source.get(field) is not None for field in ('open_decimal','high_decimal','low_decimal','close_decimal','volume_decimal'));shape='full_ohlcv' if complete else 'close_only'
  return {'trading_date':date_text,'revision_mode':'initial','supersedes_revision_ref':None,'day_status':'observed','bar_shape':shape,'open_decimal':source['open_decimal'] if complete else None,'high_decimal':source['high_decimal'] if complete else None,'low_decimal':source['low_decimal'] if complete else None,'close_decimal':source['close_decimal'],'adjusted_close_decimal':source['adjusted_close_decimal'],'volume_decimal':source['volume_decimal'] if complete else None,'corporate_action_status':source['corporate_action_status'],'valuation_status':'blocked_corporate_action' if source['corporate_action_status']=='pending_review' else 'eligible','quality_status':'complete','gap_reason':None,'source_observation_ref':source['source_observation_ref'],'observed_at_utc':source['observed_at_utc'],'correction_reason':None}
 current=date.fromisoformat(date_text);nontrading=calendar=='weekday_exchange' and current.weekday()>=5
 if nontrading:return {'trading_date':date_text,'revision_mode':'initial','supersedes_revision_ref':None,'day_status':'non_trading_day','bar_shape':'not_applicable','open_decimal':None,'high_decimal':None,'low_decimal':None,'close_decimal':None,'adjusted_close_decimal':None,'volume_decimal':None,'corporate_action_status':'not_applicable','valuation_status':'not_applicable','quality_status':'calendar_confirmed','gap_reason':None,'source_observation_ref':'mor_'+_sha({'probe':probe['_fingerprint'],'date':date_text,'status':'non_trading_day'})[:32],'observed_at_utc':observed_at,'correction_reason':None}
 reason='source_partial_response' if unusable else 'source_no_data'
 return {'trading_date':date_text,'revision_mode':'initial','supersedes_revision_ref':None,'day_status':'source_gap','bar_shape':'not_applicable','open_decimal':None,'high_decimal':None,'low_decimal':None,'close_decimal':None,'adjusted_close_decimal':None,'volume_decimal':None,'corporate_action_status':'not_applicable','valuation_status':'not_applicable','quality_status':'explicit_gap','gap_reason':reason,'source_observation_ref':'mor_'+_sha({'probe':probe['_fingerprint'],'date':date_text,'status':'source_gap','reason':reason})[:32],'observed_at_utc':observed_at,'correction_reason':None}
def preview_desktop_provider_probe_promotion_v1(data_space_path,context,request_ref,mapping,market_code,timezone_name,calendar_code,created_at_utc):
 context=_context(context);mapping=_mapping(mapping);created=_utc(created_at_utc)
 if not isinstance(request_ref,str) or REQUEST.fullmatch(request_ref) is None or not isinstance(market_code,str) or MARKET.fullmatch(market_code) is None or calendar_code not in CALENDARS or not isinstance(timezone_name,str) or not 3<=len(timezone_name)<=64:_abort('desktop_provider_promotion_input_invalid')
 try:ZoneInfo(timezone_name)
 except ZoneInfoNotFoundError:_abort('desktop_provider_promotion_input_invalid')
 try:evidence=read_desktop_provider_probe_evidence_v1(data_space_path,context,request_ref)
 except Exception as error:raise DesktopProviderPromotionV1Error('desktop_provider_promotion_probe_invalid') from error
 if evidence.get('provider_id','yahoo')!=mapping['provider_id'] or evidence['mapping_id']!=mapping['mapping_id'] or evidence['mapping_revision']!=mapping['mapping_revision'] or evidence['mapping_fingerprint']!=mapping['mapping_fingerprint'] or evidence['asset_id']!=mapping['asset_id'] or evidence['provider_symbol']!=mapping['provider_symbol'] or evidence['expected_currency']!=mapping['provider_currency'] or evidence['provider_currency']!=mapping['provider_currency'] or evidence['timezone_name']!=timezone_name:_abort('desktop_provider_promotion_probe_invalid')
 _,_,_,context_fp=semantic_context_values({'tenant_id':context.tenant_id,'user_id':context.user_id,'data_space_id':context.data_space_id});asset_ref=semantic_public_ref('asf_',context_fp,mapping['asset_id']);listing_ref='lsr_'+_sha({'contract':'desktop_provider_listing_v1','context':context_fp,'mapping_id':mapping['mapping_id'],'mapping_revision':mapping['mapping_revision'],'market_code':market_code,'timezone_name':timezone_name,'calendar_code':calendar_code})[:32]
 listing=new_daily_market_listing_binding_v1(listing_ref=listing_ref,asset_ref=asset_ref,quote_currency=mapping['provider_currency'],market_code=market_code,timezone_name=timezone_name,calendar_code=calendar_code,catalog_fingerprint=mapping['catalog_fingerprint'])
 probe_by_date={row['trading_date']:row for row in evidence['days']};probe_by_date['_completed_at_utc']=evidence['completed_at_utc'];probe_by_date['_fingerprint']=evidence['probe_evidence_fingerprint'];start=date.fromisoformat(evidence['start_date']);end=date.fromisoformat(evidence['end_date']);days=[_day(probe_by_date,item,calendar_code) for item in _dates(start,end)];source_ref='msr_'+evidence['probe_evidence_fingerprint'][:32];market_request='mrq_'+_sha({'contract':'desktop_provider_probe_promotion_request_v1','probe':evidence['probe_evidence_fingerprint'],'listing':listing['listing_fingerprint']})[:32];request_fp=_sha({'contract':'desktop_provider_probe_promotion_request_v1','probe_evidence_fingerprint':evidence['probe_evidence_fingerprint'],'listing_fingerprint':listing['listing_fingerprint'],'days':days});market_context=MarketHistoryContext(context.tenant_id,context.user_id,context.data_space_id,'market_worker','market_worker');binding=daily_market_history_job_binding_fingerprint_v1(market_context,listing_ref=listing_ref,request_ref=market_request,request_fingerprint=request_fp,source_ref=source_ref);candidate=seal_daily_market_history_candidate_v1(listing_ref=listing_ref,request_ref=market_request,source_kind='manual_reviewed_evidence',source_ref=source_ref,source_version='desktop_provider_probe_v1.0.0',request_fingerprint=request_fp,job_binding_fingerprint=binding,requested_start_date=evidence['start_date'],requested_end_date=evidence['end_date'],retrieved_at_utc=evidence['completed_at_utc'],days=days)
 body={'contract_version':'desktop_provider_probe_promotion_preview_v1','status':'ready_for_confirmation','request_ref':request_ref,'mapping_id':mapping['mapping_id'],'mapping_revision':mapping['mapping_revision'],'mapping_fingerprint':mapping['mapping_fingerprint'],'probe_evidence_fingerprint':evidence['probe_evidence_fingerprint'],'market_code':market_code,'timezone_name':timezone_name,'calendar_code':calendar_code,'listing':listing,'candidate':candidate,'created_at_utc':created,'context_fingerprint':_context_fp(context),'first_trade_date':evidence.get('first_trade_date'),'observed_day_count':sum(row['day_status']=='observed' for row in days),'non_trading_day_count':sum(row['day_status']=='non_trading_day' for row in days),'source_gap_day_count':sum(row['day_status']=='source_gap' for row in days),'corporate_action_review_required':any(row['corporate_action_status']=='pending_review' for row in days),'provider_access':False,'network_access':False,'canonical_write':False,'market_history_write':True,'automatic_retry':False};body['preview_fingerprint']=_sha(body);return body
def public_desktop_provider_probe_promotion_preview_v1(value):
 value=_validate(value);return {'contract_version':'desktop_provider_probe_promotion_public_preview_v1','status':'pending_confirmation','market_code':value['market_code'],'timezone_name':value['timezone_name'],'calendar_code':value['calendar_code'],'start_date':value['candidate']['requested_start_date'],'end_date':value['candidate']['requested_end_date'],'observed_day_count':value['observed_day_count'],'non_trading_day_count':value['non_trading_day_count'],'source_gap_day_count':value['source_gap_day_count'],'corporate_action_review_required':value['corporate_action_review_required'],'provider_access':False,'network_access':False,'canonical_write':False,'market_history_write':True,'confirmation_required':True,'automatic_retry':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}
def _validate(value):
 if not isinstance(value,dict) or value.get('contract_version')!='desktop_provider_probe_promotion_preview_v1' or value.get('status')!='ready_for_confirmation' or not isinstance(value.get('preview_fingerprint'),str) or value['preview_fingerprint']!=_sha({key:item for key,item in value.items() if key!='preview_fingerprint'}) or value.get('provider_access') is not False or value.get('network_access') is not False or value.get('canonical_write') is not False or value.get('market_history_write') is not True or value.get('automatic_retry') is not False:_abort('desktop_provider_promotion_preview_invalid')
 return value
def _read_result(path,preview):
 try:
  if path.is_symlink() or stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)!=0o600:_abort('desktop_provider_promotion_result_invalid')
  value=json.loads(path.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError):_abort('desktop_provider_promotion_result_invalid')
 fingerprint=value.pop('result_fingerprint',None) if isinstance(value,dict) else None
 if not isinstance(value,dict) or value.get('preview_fingerprint')!=preview['preview_fingerprint'] or fingerprint!=_sha(value):_abort('desktop_provider_promotion_result_invalid')
 value['result_fingerprint']=fingerprint;return value
def recover_desktop_provider_probe_promotion_v1(data_space_path,context,mapping_id):
 context=_context(context);space=_owner_dir(Path(data_space_path))
 if space.name!=context.data_space_id or not isinstance(mapping_id,str) or not mapping_id.startswith('map_'):_abort('desktop_provider_promotion_input_invalid')
 root=space/AREA/'promotions'/'results'
 if not root.exists():return None
 if not root.is_dir() or root.is_symlink():_abort('desktop_provider_promotion_store_invalid')
 matches=[]
 for path in sorted(root.glob('promotion_*.json')):
  try:
   if path.is_symlink() or stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)!=0o600:_abort('desktop_provider_promotion_result_invalid')
   value=json.loads(path.read_text(encoding='utf-8'));fingerprint=value.pop('result_fingerprint',None)
  except (OSError,json.JSONDecodeError):_abort('desktop_provider_promotion_result_invalid')
  if not isinstance(value,dict) or fingerprint!=_sha(value) or value.get('context_fingerprint')!=_context_fp(context):_abort('desktop_provider_promotion_result_invalid')
  value['result_fingerprint']=fingerprint
  if value.get('mapping_id')==mapping_id:matches.append(value)
 if not matches:return None
 matches.sort(key=lambda row:(row['completed_at_utc'],row['result_fingerprint']))
 return matches[-1]
def public_desktop_provider_probe_promotion_result_v1(value):return {'contract_version':'desktop_provider_probe_promotion_result_v1','status':value['status'],'observed_day_count':value['observed_day_count'],'non_trading_day_count':value['non_trading_day_count'],'source_gap_day_count':value['source_gap_day_count'],'corporate_action_review_required':value['corporate_action_review_required'],'provider_access':False,'network_access':False,'canonical_write':False,'market_history_write':True,'mapping_verified':False,'automatic_retry':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}
def apply_desktop_provider_probe_promotion_v1(data_space_path,context,preview,public_preview,confirmed,applied_at_utc):
 context=_context(context);trusted=_validate(preview);applied=_utc(applied_at_utc)
 if trusted['context_fingerprint']!=_context_fp(context) or public_preview!=public_desktop_provider_probe_promotion_preview_v1(trusted):_abort('desktop_provider_promotion_preview_invalid')
 if confirmed is not True:_abort('desktop_provider_promotion_confirmation_required')
 data_space=_owner_dir(Path(data_space_path))
 if data_space.name!=context.data_space_id:_abort('desktop_provider_promotion_store_invalid')
 area=_ensure(data_space,AREA);promotions=_ensure(area,'promotions');attempts=_ensure(promotions,'attempts');results=_ensure(promotions,'results');key=trusted['preview_fingerprint'][:32];result_path=results/f'promotion_{key}.json'
 if result_path.exists():return _read_result(result_path,trusted)
 attempt={'contract_version':'desktop_provider_probe_promotion_attempt_v1','preview_fingerprint':trusted['preview_fingerprint'],'probe_evidence_fingerprint':trusted['probe_evidence_fingerprint'],'mapping_fingerprint':trusted['mapping_fingerprint'],'applied_at_utc':applied,'market_history_write_authorized':True,'canonical_write':False,'automatic_retry':False};attempt['attempt_fingerprint']=_sha(attempt);_write(attempts/f'promotion_{key}.json',attempt)
 market_root=_ensure(data_space,MARKET_AREA);store=market_root/STORE_NAME;market_context=MarketHistoryContext(context.tenant_id,context.user_id,context.data_space_id,'market_worker','market_worker')
 try:
  if not store.exists():bootstrap_daily_market_history_store_v1(store,market_context,applied)
  bind_daily_market_listing_v1(store,market_context,trusted['listing'],applied)
  receipt=append_daily_market_history_v1(store,market_context,trusted['candidate'],applied)
 except DailyMarketHistoryBlocked as error:raise DesktopProviderPromotionV1Error('desktop_provider_promotion_history_write_failed') from error
 result={'contract_version':'desktop_provider_probe_promotion_private_result_v1','status':'completed','preview_fingerprint':trusted['preview_fingerprint'],'probe_evidence_fingerprint':trusted['probe_evidence_fingerprint'],'context_fingerprint':trusted['context_fingerprint'],'mapping_id':trusted['mapping_id'],'mapping_revision':trusted['mapping_revision'],'mapping_fingerprint':trusted['mapping_fingerprint'],'listing_ref':trusted['listing']['listing_ref'],'listing_fingerprint':trusted['listing']['listing_fingerprint'],'market_request_ref':trusted['candidate']['request_ref'],'market_receipt_ref':receipt.request_ref,'market_receipt_fingerprint':receipt.receipt_fingerprint,'observed_day_count':trusted['observed_day_count'],'non_trading_day_count':trusted['non_trading_day_count'],'source_gap_day_count':trusted['source_gap_day_count'],'corporate_action_review_required':trusted['corporate_action_review_required'],'first_trade_date':trusted.get('first_trade_date'),'completed_at_utc':applied,'provider_access':False,'network_access':False,'canonical_write':False,'market_history_write':True,'mapping_verified':False,'automatic_retry':False};result['result_fingerprint']=_sha(result);_write(result_path,result);return result

__all__=['DesktopProviderPromotionV1Error','apply_desktop_provider_probe_promotion_v1','desktop_provider_promotion_v1_error_codes','preview_desktop_provider_probe_promotion_v1','public_desktop_provider_probe_promotion_preview_v1','public_desktop_provider_probe_promotion_result_v1','recover_desktop_provider_probe_promotion_v1']
