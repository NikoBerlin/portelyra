#!/usr/bin/env python3
"""Confirmed fetch for only not-requested Daily Market History ranges (request and parsing by the price provider plugin since rc.382)."""
from __future__ import annotations
from datetime import date,datetime,timedelta,timezone
import hashlib,json,os,re,stat
from pathlib import Path
from typing import Any,Mapping,Callable

from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1
from migrations.reference import price_provider_plugins_v1 as price_providers
from migrations.reference.desktop_provider_probe_v1 import PROVIDER_ID,TIMEOUT,BYTE_LIMIT,_default_transport,_parse_response,core_transport_v1,history_provider_v1
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA,STORE_NAME,_day
from migrations.reference.desktop_market_history_plan_v1 import plan_desktop_market_history_v1
from migrations.reference.daily_market_history_v1 import (
 DailyMarketHistoryBlocked,MarketHistoryContext,append_daily_market_history_v1,
 daily_market_history_job_binding_fingerprint_v1,read_daily_market_history_v1,
 read_daily_market_listing_binding_v1,seal_daily_market_history_candidate_v1,
 validate_daily_market_candidate_for_listing_v1,
)
AREA='desktop-market-history-fetch-v1';MAX_RANGE_DAYS=3650;MAX_RANGES=100
_DOMAIN_FIELDS=('day_status','bar_shape','open_decimal','high_decimal','low_decimal','close_decimal','adjusted_close_decimal','volume_decimal','corporate_action_status','valuation_status','quality_status','gap_reason')
_CORRECTION_FIELDS=tuple(field for field in _DOMAIN_FIELDS if field!='quality_status')
FAILURE_CODES=frozenset({'desktop_market_history_fetch_context_invalid','desktop_market_history_fetch_credential_unavailable','desktop_market_history_fetch_cost_limit','desktop_market_history_fetch_scheduled_disabled','desktop_market_history_fetch_input_invalid','desktop_market_history_fetch_preview_invalid','desktop_market_history_fetch_confirmation_required','desktop_market_history_fetch_attempt_consumed','desktop_market_history_fetch_store_invalid','desktop_market_history_fetch_transport_failed','desktop_market_history_fetch_response_invalid','desktop_market_history_fetch_write_failed','desktop_market_history_fetch_result_invalid'})
SHA=re.compile(r'^[a-f0-9]{64}$');NONCE=re.compile(r'^mhn_[A-Za-z0-9_-]{12,64}$');UTC=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$')
class DesktopMarketHistoryFetchV1Error(RuntimeError):
 def __init__(self,code):
  if code not in FAILURE_CODES:raise ValueError('desktop_market_history_fetch_error_unregistered')
  self.code=code;super().__init__(code)
def desktop_market_history_fetch_v1_error_codes():return tuple(sorted(FAILURE_CODES))
def _abort(code):raise DesktopMarketHistoryFetchV1Error(code)
def _canonical(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
def _sha(value):return hashlib.sha256(value if isinstance(value,bytes) else _canonical(value)).hexdigest()
def _context(value):
 if isinstance(value,Mapping):
  try:value=DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
  except (KeyError,TypeError) as error:raise DesktopMarketHistoryFetchV1Error('desktop_market_history_fetch_context_invalid') from error
 if not isinstance(value,DesktopProviderSearchContextV1) or value.actor_id!='market_worker' or value.role!='market_worker' or not value.data_space_id.startswith('sbx_'):_abort('desktop_market_history_fetch_context_invalid')
 return value
def _context_fp(value):
 value=_context(value);return _sha({'contract':'desktop_market_history_fetch_context_v1','tenant_id':value.tenant_id,'user_id':value.user_id,'data_space_id':value.data_space_id,'actor_id':value.actor_id,'role':value.role})
def _utc(value):
 if not isinstance(value,str) or UTC.fullmatch(value) is None:_abort('desktop_market_history_fetch_input_invalid')
 try:parsed=datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
 except ValueError:_abort('desktop_market_history_fetch_input_invalid')
 if parsed.strftime('%Y-%m-%dT%H:%M:%SZ')!=value:_abort('desktop_market_history_fetch_input_invalid')
 return value
def _mapping(value):
 required={'mapping_id','mapping_revision','asset_id','provider_id','provider_symbol','provider_currency','capability','mapping_fingerprint','catalog_fingerprint','verification_status','enabled'}
 if not isinstance(value,Mapping) or set(value)!=required or history_provider_v1(value.get('provider_id')) is None or value.get('capability')!='daily_history' or value.get('verification_status')!='verified' or value.get('enabled') is not True or not isinstance(value.get('mapping_fingerprint'),str) or SHA.fullmatch(value['mapping_fingerprint']) is None:_abort('desktop_market_history_fetch_input_invalid')
 return dict(value)
def _owner(path):
 path=Path(path)
 try:info=path.stat(follow_symlinks=False);resolved=path.resolve(strict=True)
 except OSError:_abort('desktop_market_history_fetch_store_invalid')
 if not path.is_absolute() or path.is_symlink() or resolved!=path or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.geteuid():_abort('desktop_market_history_fetch_store_invalid')
 return path
def _ensure(parent,name):
 parent=_owner(parent);path=parent/name
 if not path.exists():
  try:os.mkdir(path,0o700);os.chmod(path,0o700)
  except OSError:_abort('desktop_market_history_fetch_store_invalid')
 return _owner(path)
def _write(path,value):
 descriptor=None
 try:descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.write(descriptor,_canonical(value)+b'\n');os.fsync(descriptor);os.close(descriptor);descriptor=None
 except FileExistsError:_abort('desktop_market_history_fetch_attempt_consumed')
 except OSError:_abort('desktop_market_history_fetch_store_invalid')
 finally:
  if descriptor is not None:os.close(descriptor)
def _split_ranges(ranges):
 result=[]
 for row in ranges:
  start=date.fromisoformat(row['start_date']);end=date.fromisoformat(row['end_date'])
  while start<=end:
   chunk_end=min(end,start+timedelta(days=MAX_RANGE_DAYS-1));result.append({'start_date':start.isoformat(),'end_date':chunk_end.isoformat(),'calendar_day_count':(chunk_end-start).days+1});start=chunk_end+timedelta(days=1)
 return result
def preview_desktop_market_history_fetch_v1(data_space_path,context,listing_ref,mapping,required_start_date,as_of_date,request_nonce,created_at_utc,mode='incremental'):
 context=_context(context);mapping=_mapping(mapping);created=_utc(created_at_utc)
 if not isinstance(request_nonce,str) or NONCE.fullmatch(request_nonce) is None or mode not in {'incremental','retry_source_gaps','full_refresh'}:_abort('desktop_market_history_fetch_input_invalid')
 # Geplant wird zum Zeitpunkt der Vorschau und nur bis zum abgeschlossenen Tag der Notierung (#475) - auch beim vollen Neuabruf.
 plan=plan_desktop_market_history_v1(data_space_path,context,listing_ref,required_start_date,as_of_date,mode,now_utc=datetime.strptime(created,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc));end_date=plan['as_of_date']
 source_ranges=([{'start_date':required_start_date,'end_date':end_date,'calendar_day_count':(date.fromisoformat(end_date)-date.fromisoformat(required_start_date)).days+1}] if end_date>=required_start_date else []) if mode=='full_refresh' else plan['ranges'];ranges=_split_ranges(source_ranges)
 if len(ranges)>MAX_RANGES:_abort('desktop_market_history_fetch_input_invalid')
 store=Path(data_space_path)/MARKET_AREA/STORE_NAME;reader=MarketHistoryContext(context.tenant_id,context.user_id,context.data_space_id,'portfolio_reader','portfolio_worker')
 try:listing=read_daily_market_listing_binding_v1(store,reader,listing_ref)
 except DailyMarketHistoryBlocked as error:raise DesktopMarketHistoryFetchV1Error('desktop_market_history_fetch_store_invalid') from error
 if listing['quote_currency']!=mapping['provider_currency']:_abort('desktop_market_history_fetch_input_invalid')
 body={'contract_version':'desktop_market_history_fetch_preview_v1','status':'ready_for_confirmation','listing':listing,'mapping':mapping,'mode':mode,'required_start_date':required_start_date,'as_of_date':as_of_date,'ranges':ranges,'target_day_count':sum(row['calendar_day_count'] for row in ranges),'provider_call_count':len(ranges),'created_at_utc':created,'request_nonce':request_nonce,'context_fingerprint':_context_fp(context),'provider_access':False,'network_access':False,'market_history_write':bool(ranges),'canonical_write':False,'automatic_retry':False};body['preview_fingerprint']=_sha(body);return body
def _validate(value):
 if not isinstance(value,dict) or value.get('contract_version')!='desktop_market_history_fetch_preview_v1' or value.get('status')!='ready_for_confirmation' or value.get('provider_access') is not False or value.get('network_access') is not False or value.get('canonical_write') is not False or value.get('automatic_retry') is not False or value.get('market_history_write') is not bool(value.get('ranges')) or value.get('preview_fingerprint')!=_sha({key:item for key,item in value.items() if key!='preview_fingerprint'}):_abort('desktop_market_history_fetch_preview_invalid')
 return value
def public_desktop_market_history_fetch_preview_v1(value):
 value=_validate(value);return {'contract_version':'desktop_market_history_fetch_public_preview_v1','status':'pending_confirmation' if value['ranges'] else 'nothing_missing','mode':value['mode'],'required_start_date':value['required_start_date'],'as_of_date':value['as_of_date'],'target_day_count':value['target_day_count'],'provider_call_count':value['provider_call_count'],'ranges':value['ranges'],'confirmation_required':bool(value['ranges']),'provider_access':False,'network_access':False,'market_history_write':bool(value['ranges']),'canonical_write':False,'automatic_retry':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}
def _now(clock):
 value=clock()
 if not isinstance(value,datetime) or value.utcoffset() is None:_abort('desktop_market_history_fetch_input_invalid')
 return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def _range_days(parsed,preview,completed):
 by_date={row['trading_date']:row for row in parsed['days']};by_date['_completed_at_utc']=completed;by_date['_fingerprint']=_sha({'preview':preview['preview_fingerprint'],'range':[preview['start_date'],preview['end_date']],'days':parsed['days']});start=date.fromisoformat(preview['start_date']);end=date.fromisoformat(preview['end_date']);return [_day(by_date,(start+timedelta(days=index)).isoformat(),preview['calendar_code']) for index in range((end-start).days+1)]
def _domain(row,fields):return {field:row[field] for field in fields}
def _quality(status):return {'observed':'corrected','non_trading_day':'calendar_confirmed','source_gap':'explicit_gap'}[status]
def _compare_candidate(candidate,current_history,listing):
 current={row['trading_date']:row for row in current_history['days']};transformed=[]
 for proposal in candidate['days']:
  prior=current[proposal['trading_date']];row={key:value for key,value in proposal.items() if key!='source_day_fingerprint'};prior_status=prior['day_status']
  if prior_status!='not_requested':
   if prior['corporate_action_status'] in {'pending_review','explicitly_reconciled'} and row['corporate_action_status']!=prior['corporate_action_status']:
    comparable=tuple(field for field in _CORRECTION_FIELDS if field not in {'corporate_action_status','valuation_status'})
    if prior['corporate_action_status']=='explicitly_reconciled' and _domain(row,comparable)==_domain(prior,comparable):
     for field in _DOMAIN_FIELDS:row[field]=prior[field]
    else:_abort('desktop_market_history_fetch_response_invalid')
   if _domain(row,_CORRECTION_FIELDS)==_domain(prior,_CORRECTION_FIELDS):
    for field in _DOMAIN_FIELDS:row[field]=prior[field]
    row['revision_mode']='unchanged';row['supersedes_revision_ref']=prior['market_day_revision_ref'];row['correction_reason']=None
   else:
    row['revision_mode']='correction';row['supersedes_revision_ref']=prior['market_day_revision_ref'];row['correction_reason']='calendar_correction' if 'non_trading_day' in {prior_status,row['day_status']} else 'source_correction';row['quality_status']=_quality(row['day_status'])
  transformed.append(row)
 try:
  rebuilt=seal_daily_market_history_candidate_v1(listing_ref=candidate['listing_ref'],request_ref=candidate['request_ref'],source_kind=candidate['source_kind'],source_ref=candidate['source_ref'],source_version=candidate['source_version'],request_fingerprint=candidate['request_fingerprint'],job_binding_fingerprint=candidate['job_binding_fingerprint'],requested_start_date=candidate['requested_start_date'],requested_end_date=candidate['requested_end_date'],retrieved_at_utc=candidate['retrieved_at_utc'],days=transformed);validate_daily_market_candidate_for_listing_v1(rebuilt,listing);return rebuilt
 except DailyMarketHistoryBlocked as error:raise DesktopMarketHistoryFetchV1Error('desktop_market_history_fetch_response_invalid') from error
def _read_result(path,preview):
 try:
  value=json.loads(path.read_text(encoding='utf-8'));fingerprint=value.pop('result_fingerprint',None)
 except (OSError,json.JSONDecodeError):_abort('desktop_market_history_fetch_result_invalid')
 if not isinstance(value,dict) or value.get('preview_fingerprint')!=preview['preview_fingerprint'] or fingerprint!=_sha(value):_abort('desktop_market_history_fetch_result_invalid')
 value['result_fingerprint']=fingerprint;return value
def public_desktop_market_history_fetch_result_v1(value):return {'contract_version':'desktop_market_history_fetch_result_v1','status':value['status'],'mode':value['mode'],'provider_call_count':value['provider_call_count'],'appended_day_count':value['appended_day_count'],'corrected_day_count':value['corrected_day_count'],'unchanged_day_count':value['unchanged_day_count'],'observed_day_count':value['observed_day_count'],'non_trading_day_count':value['non_trading_day_count'],'source_gap_day_count':value['source_gap_day_count'],'provider_access':value['provider_call_count']>0,'network_access':value['provider_call_count']>0,'market_history_write':value['provider_call_count']>0,'canonical_write':False,'automatic_retry':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}
@price_providers.within_price_provider_session
def apply_desktop_market_history_fetch_v1(data_space_path,context,preview,public_preview,confirmed,*,transport=None,clock=lambda:datetime.now(timezone.utc)):
 context=_context(context);trusted=_validate(preview)
 if trusted['context_fingerprint']!=_context_fp(context) or public_preview!=public_desktop_market_history_fetch_preview_v1(trusted):_abort('desktop_market_history_fetch_preview_invalid')
 if not trusted['ranges']:
  result={'contract_version':'desktop_market_history_fetch_private_result_v1','status':'nothing_missing','mode':trusted['mode'],'preview_fingerprint':trusted['preview_fingerprint'],'provider_call_count':0,'appended_day_count':0,'corrected_day_count':0,'unchanged_day_count':0,'observed_day_count':0,'non_trading_day_count':0,'source_gap_day_count':0,'completed_at_utc':trusted['created_at_utc'],'automatic_retry':False};result['result_fingerprint']=_sha(result);return result
 if confirmed is not True:_abort('desktop_market_history_fetch_confirmation_required')
 space=_owner(Path(data_space_path));area=_ensure(space,AREA);attempts=_ensure(area,'attempts');results=_ensure(area,'results');failures=_ensure(area,'failures');key=trusted['preview_fingerprint'][:32];result_path=results/f'fetch_{key}.json'
 if result_path.exists():return _read_result(result_path,trusted)
 started=_now(clock);attempt={'contract_version':'desktop_market_history_fetch_attempt_v1','preview_fingerprint':trusted['preview_fingerprint'],'mapping_fingerprint':trusted['mapping']['mapping_fingerprint'],'started_at_utc':started,'provider_call_count':len(trusted['ranges']),'provider_access_authorized':True,'market_history_write_authorized':True,'automatic_retry':False};attempt['attempt_fingerprint']=_sha(attempt);_write(attempts/f'fetch_{key}.json',attempt)
 store=space/MARKET_AREA/STORE_NAME;market_context=MarketHistoryContext(context.tenant_id,context.user_id,context.data_space_id,'market_worker','market_worker');reader_context=MarketHistoryContext(context.tenant_id,context.user_id,context.data_space_id,'portfolio_reader','portfolio_worker');counts={'appended':0,'corrected':0,'unchanged':0,'observed':0,'closed':0,'gap':0}
 try:
  for ordinal,row in enumerate(trusted['ranges'],1):
   provider_id=trusted['mapping']['provider_id']
   if transport is None:transport=core_transport_v1(space,context,provider_id,_abort,'desktop_market_history_fetch')
   try:request=price_providers.build_request_v1(provider_id,'daily_history',{'provider_symbol':trusted['mapping']['provider_symbol'],'start_date':row['start_date'],'end_date':row['end_date'],'request_start_date':row['start_date']});response=transport(request['host'],request['target'],{'Accept':'application/json','Accept-Encoding':'identity','Connection':'close','User-Agent':'Portelyra/0.2 Missing-History'},TIMEOUT,BYTE_LIMIT)
   except DesktopMarketHistoryFetchV1Error:raise
   except Exception as error:raise DesktopMarketHistoryFetchV1Error('desktop_market_history_fetch_transport_failed') from error
   completed=_now(clock)
   if not isinstance(response,dict) or response.get('status')!=200 or not isinstance(response.get('headers'),dict) or not response['headers'].get('content-type','').lower().startswith('application/json') or not isinstance(response.get('body'),bytes):_abort('desktop_market_history_fetch_response_invalid')
   parser_preview={'provider_symbol':trusted['mapping']['provider_symbol'],'start_date':row['start_date'],'end_date':row['end_date'],'request_ref':'mhf_'+_sha([trusted['preview_fingerprint'],ordinal])[:32]}
   try:parsed=_parse_response(response['body'],parser_preview,completed,provider_id)
   except Exception as error:raise DesktopMarketHistoryFetchV1Error('desktop_market_history_fetch_response_invalid') from error
   if parsed['provider_currency']!=trusted['listing']['quote_currency'] or parsed['timezone_name']!=trusted['listing']['timezone_name']:_abort('desktop_market_history_fetch_response_invalid')
   day_preview={'preview_fingerprint':trusted['preview_fingerprint'],'start_date':row['start_date'],'end_date':row['end_date'],'calendar_code':trusted['listing']['calendar_code']};days=_range_days(parsed,day_preview,completed);request_ref='mrq_'+_sha({'preview':trusted['preview_fingerprint'],'ordinal':ordinal})[:32];source_ref='msr_'+_sha({'request':request_ref,'provider':'yahoo'})[:32];request_fp=_sha({'contract':'desktop_market_history_fetch_request_v1','range':row,'mapping_fingerprint':trusted['mapping']['mapping_fingerprint'],'days':days});binding=daily_market_history_job_binding_fingerprint_v1(market_context,listing_ref=trusted['listing']['listing_ref'],request_ref=request_ref,request_fingerprint=request_fp,source_ref=source_ref);candidate=seal_daily_market_history_candidate_v1(listing_ref=trusted['listing']['listing_ref'],request_ref=request_ref,source_kind='market_plugin',source_ref=source_ref,source_version='desktop_yahoo_history_v1.0.0',request_fingerprint=request_fp,job_binding_fingerprint=binding,requested_start_date=row['start_date'],requested_end_date=row['end_date'],retrieved_at_utc=completed,days=days)
   if trusted['mode']!='incremental':
    try:current=read_daily_market_history_v1(store,reader_context,trusted['listing']['listing_ref'],row['start_date'],row['end_date']);candidate=_compare_candidate(candidate,current,trusted['listing'])
    except DailyMarketHistoryBlocked as error:raise DesktopMarketHistoryFetchV1Error('desktop_market_history_fetch_response_invalid') from error
   receipt=append_daily_market_history_v1(store,market_context,candidate,completed);counts['appended']+=receipt.appended_day_count;counts['corrected']+=receipt.corrected_day_count;counts['unchanged']+=receipt.unchanged_day_count;counts['observed']+=sum(item['day_status']=='observed' for item in candidate['days']);counts['closed']+=sum(item['day_status']=='non_trading_day' for item in candidate['days']);counts['gap']+=sum(item['day_status']=='source_gap' for item in candidate['days'])
  result={'contract_version':'desktop_market_history_fetch_private_result_v1','status':'completed','mode':trusted['mode'],'preview_fingerprint':trusted['preview_fingerprint'],'provider_call_count':len(trusted['ranges']),'appended_day_count':counts['appended'],'corrected_day_count':counts['corrected'],'unchanged_day_count':counts['unchanged'],'observed_day_count':counts['observed'],'non_trading_day_count':counts['closed'],'source_gap_day_count':counts['gap'],'completed_at_utc':_now(clock),'automatic_retry':False};result['result_fingerprint']=_sha(result);_write(result_path,result);return result
 except DesktopMarketHistoryFetchV1Error as error:
  failure={'contract_version':'desktop_market_history_fetch_failure_v1','preview_fingerprint':trusted['preview_fingerprint'],'attempt_fingerprint':attempt['attempt_fingerprint'],'failure_code':error.code,'completed_day_count':counts['appended'],'failed_at_utc':_now(clock),'automatic_retry':False};failure['failure_fingerprint']=_sha(failure)
  try:_write(failures/f'fetch_{key}.json',failure)
  except Exception:pass
  raise
 except Exception as error:
  failure={'contract_version':'desktop_market_history_fetch_failure_v1','preview_fingerprint':trusted['preview_fingerprint'],'attempt_fingerprint':attempt['attempt_fingerprint'],'failure_code':'desktop_market_history_fetch_write_failed','completed_day_count':counts['appended'],'failed_at_utc':_now(clock),'automatic_retry':False};failure['failure_fingerprint']=_sha(failure)
  try:_write(failures/f'fetch_{key}.json',failure)
  except Exception:pass
  raise DesktopMarketHistoryFetchV1Error('desktop_market_history_fetch_write_failed') from error
__all__=['DesktopMarketHistoryFetchV1Error','apply_desktop_market_history_fetch_v1','desktop_market_history_fetch_v1_error_codes','preview_desktop_market_history_fetch_v1','public_desktop_market_history_fetch_preview_v1','public_desktop_market_history_fetch_result_v1']
