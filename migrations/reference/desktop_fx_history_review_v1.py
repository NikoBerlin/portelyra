#!/usr/bin/env python3
"""Incremental one-range FX staging and separate schema-2600 publication (request and parsing by the price provider plugin since rc.382)."""
from __future__ import annotations
from datetime import date,datetime,timedelta,timezone
import base64,json,os,stat
from migrations.reference import desktop_fx_history_attempt_v2 as evidence
from pathlib import Path
from typing import Any,Callable,Mapping
from migrations.reference import price_provider_plugins_v1 as price_providers
from migrations.reference.desktop_provider_probe_v1 import PROVIDER_ID,TIMEOUT,BYTE_LIMIT,_default_transport,_parse_response
from migrations.reference.desktop_fx_pair_promotion_v1 import AREA,STORE,_ctx,_space,_sha,_canon
from migrations.reference.market_day_completion_v1 import completed_through_v1
from migrations.reference.fx_history_v1 import FxHistoryBlocked,append_fx_history_v1,fx_history_job_binding_fingerprint_v1,read_fx_history_v1,read_fx_pair_catalog_v1,seal_fx_history_candidate_v1
STAGE_AREA='desktop-fx-history-review-v1';FAILURE_CODES=frozenset({'desktop_fx_history_review_input_invalid','desktop_fx_history_review_pair_missing','desktop_fx_history_review_preview_invalid','desktop_fx_history_review_confirmation_required','desktop_fx_history_review_attempt_consumed','desktop_fx_history_review_transport_failed','desktop_fx_history_review_response_invalid','desktop_fx_history_review_store_invalid','desktop_fx_history_review_write_failed'})
class DesktopFxHistoryReviewV1Error(RuntimeError):
 def __init__(self,code):
  if code not in FAILURE_CODES:raise ValueError('desktop_fx_history_review_error_unregistered')
  self.code=code;super().__init__(code)
def _abort(c):raise DesktopFxHistoryReviewV1Error(c)
def _utc(v):
 try:d=datetime.strptime(v,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
 except (TypeError,ValueError):_abort('desktop_fx_history_review_input_invalid')
 if d.strftime('%Y-%m-%dT%H:%M:%SZ')!=v:_abort('desktop_fx_history_review_input_invalid')
 return v
def _range(a,b):
 try:s=date.fromisoformat(a);e=date.fromisoformat(b)
 except (TypeError,ValueError):_abort('desktop_fx_history_review_input_invalid')
 if e<s or (e-s).days>=3650:_abort('desktop_fx_history_review_input_invalid')
 return s,e
def _pair(store,ctx,source,target):
 try:catalog=read_fx_pair_catalog_v1(store,ctx)
 except FxHistoryBlocked as e:raise DesktopFxHistoryReviewV1Error('desktop_fx_history_review_store_invalid') from e
 rows=[p for p in catalog['pairs'] if {p['base_currency'],p['quote_currency']}=={source,target}]
 if len(rows)!=1:_abort('desktop_fx_history_review_pair_missing')
 p=rows[0];direction='direct' if p['base_currency']==source else 'inverse';path=store.parent/'provider-bindings'/f"{p['pair_ref']}.json"
 try:
  if path.is_symlink() or stat.S_IMODE(path.stat().st_mode)!=0o600:_abort('desktop_fx_history_review_store_invalid')
  binding=json.loads(path.read_text());fp=binding.pop('binding_fingerprint');valid=fp==_sha(binding) and binding.get('pair_ref')==p['pair_ref'] and binding.get('pair_fingerprint')==p['pair_fingerprint'] and binding.get('provider_id')=='yahoo' and binding.get('provider_currency')==p['quote_currency'] and binding.get('direction')==direction;binding['binding_fingerprint']=fp
 except (OSError,json.JSONDecodeError,KeyError):_abort('desktop_fx_history_review_store_invalid')
 if not valid:_abort('desktop_fx_history_review_store_invalid')
 return p,direction,binding
def _ranges(values):
 out=[]
 for v in values:
  if not out or date.fromisoformat(v)>date.fromisoformat(out[-1]['end_date'])+timedelta(days=1):out.append({'range_ref':f"fx_range_{len(out)+1:03d}",'start_date':v,'end_date':v,'calendar_day_count':1})
  else:out[-1]['end_date']=v;out[-1]['calendar_day_count']+=1
 return out
def plan_desktop_fx_history_v1(data_space_path,context,source_currency,target_currency,start_date,end_date,now_utc=None):
 ctx=_ctx(context);space=_space(data_space_path,ctx);start,end=_range(start_date,end_date);store=space/AREA/STORE
 if not store.is_file():_abort('desktop_fx_history_review_pair_missing')
 pair,direction,binding=_pair(store,ctx,source_currency,target_currency)
 try:h=read_fx_history_v1(store,ctx,pair['pair_ref'],start_date,end_date)
 except FxHistoryBlocked as e:raise DesktopFxHistoryReviewV1Error('desktop_fx_history_review_store_invalid') from e
 # Nur bis zum juengsten Tag, der in der Zeitzone des Paares abgeschlossen ist (#475).
 completed=completed_through_v1(h['timezone_name'],now_utc);effective_end=min(end_date,completed)
 ranges=_ranges([x['rate_date'] for x in h['days'] if x['day_status']=='not_requested' and x['rate_date']<=effective_end])
 return {'contract_version':'desktop_fx_history_plan_v1','status':'ready','source_currency':source_currency,'target_currency':target_currency,'direction':direction,'start_date':start_date,'end_date':effective_end,'requested_end_date':end_date,'completed_through':completed,'ranges':ranges,'range_count':len(ranges),'target_day_count':sum(x['calendar_day_count'] for x in ranges),'provider_access':False,'network_access':False,'fx_history_write':False,'canonical_write':False}
def preview_desktop_fx_history_fetch_v1(data_space_path,context,source_currency,target_currency,start_date,end_date,created_at_utc):
 ctx=_ctx(context);space=_space(data_space_path,ctx);start,end=_range(start_date,end_date);created=_utc(created_at_utc);store=space/AREA/STORE;pair,direction,binding=_pair(store,ctx,source_currency,target_currency)
 try:h=read_fx_history_v1(store,ctx,pair['pair_ref'],start_date,end_date)
 except FxHistoryBlocked as e:raise DesktopFxHistoryReviewV1Error('desktop_fx_history_review_store_invalid') from e
 if any(x['day_status']!='not_requested' for x in h['days']):_abort('desktop_fx_history_review_input_invalid')
 body={'contract_version':'desktop_fx_history_fetch_preview_v1','status':'ready_for_confirmation','pair':pair,'provider_binding':binding,'source_currency':source_currency,'target_currency':target_currency,'direction':direction,'start_date':start_date,'end_date':end_date,'calendar_day_count':(end-start).days+1,'created_at_utc':created,'context_fingerprint':_sha({'tenant_id':ctx.tenant_id,'user_id':ctx.user_id,'data_space_id':ctx.data_space_id}),'provider_call_count':1,'provider_access':False,'network_access':False,'owner_local_staging_after_confirmation':True,'fx_history_write':False,'canonical_write':False,'automatic_retry':False};body['owner_fingerprint']=evidence.owner(space,ctx);body['preview_fingerprint']=_sha(body);return body
def _valid(v):
 if not isinstance(v,dict) or v.get('contract_version')!='desktop_fx_history_fetch_preview_v1' or v.get('preview_fingerprint')!=_sha({k:x for k,x in v.items() if k!='preview_fingerprint'}):_abort('desktop_fx_history_review_preview_invalid')
 return v
def public_desktop_fx_history_fetch_preview_v1(v):
 v=_valid(v);return {k:v[k] for k in ('contract_version','status','source_currency','target_currency','direction','start_date','end_date','calendar_day_count','provider_call_count','provider_access','network_access','owner_local_staging_after_confirmation','fx_history_write','canonical_write','automatic_retry')}
def _mkdir(parent,name):
 p=parent/name
 if not p.exists():os.mkdir(p,0o700)
 if p.is_symlink() or stat.S_IMODE(p.stat().st_mode)!=0o700:_abort('desktop_fx_history_review_store_invalid')
 return p
def _write(path,v):
 try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.write(fd,_canon(v)+b'\n');os.fsync(fd);os.close(fd)
 except FileExistsError:_abort('desktop_fx_history_review_attempt_consumed')
 except OSError:_abort('desktop_fx_history_review_store_invalid')
def _candidate(v,parsed,retrieved,ctx):
 start,end=_range(v['start_date'],v['end_date']);by={x['trading_date']:x for x in parsed['days']};days=[]
 for n in range((end-start).days+1):
  d=start+timedelta(days=n);text=d.isoformat();r=by.get(text);ref='fxo_'+_sha([v['preview_fingerprint'],text])[:32]
  if r is not None and r['day_status']=='observed' and r['close_decimal'] is not None:status='observed';rate=r['close_decimal'];quality='complete';gap=None;observed=r['observed_at_utc']
  elif d.weekday()>=5:status='non_trading_day';rate=None;quality='calendar_confirmed';gap=None;observed=text+'T12:00:00Z'
  else:status='source_gap';rate=None;quality='explicit_gap';gap='source_no_data';observed=text+'T12:00:00Z'
  days.append({'rate_date':text,'revision_mode':'initial','supersedes_revision_ref':None,'day_status':status,'rate_decimal':rate,'quality_status':quality,'gap_reason':gap,'source_observation_ref':ref,'observed_at_utc':observed,'correction_reason':None})
 request='fxq_'+_sha(['history',v['preview_fingerprint']])[:32];source='fxs_'+_sha(['yahoo',v['preview_fingerprint']])[:32];request_fp=_sha({'pair':v['pair']['pair_fingerprint'],'preview':v['preview_fingerprint'],'days':days});binding=fx_history_job_binding_fingerprint_v1(ctx,pair_ref=v['pair']['pair_ref'],request_ref=request,request_fingerprint=request_fp,source_ref=source);identity=price_providers.provider_identity_v1(PROVIDER_ID)
 # Herkunft je Abruf: das Kursanbieter-Plugin, das die Antwort gelesen hat (#495, rc.382).
 return seal_fx_history_candidate_v1(pair_ref=v['pair']['pair_ref'],request_ref=request,source_kind='market_plugin',source_ref=source,source_version=identity['source_version'],plugin_id=identity['plugin_id'],plugin_version=identity['plugin_version'],plugin_manifest_fingerprint=identity['manifest_sha256'],request_fingerprint=request_fp,job_binding_fingerprint=binding,requested_start_date=v['start_date'],requested_end_date=v['end_date'],retrieved_at_utc=retrieved,days=days)
@price_providers.within_price_provider_session
def stage_desktop_fx_history_fetch_v1(data_space_path,context,preview,public_preview,confirmed,transport:Callable=_default_transport,clock=lambda:datetime.now(timezone.utc)):
 ctx=_ctx(context);v=_valid(preview);space=_space(data_space_path,ctx)
 if public_preview!=public_desktop_fx_history_fetch_preview_v1(v) or confirmed is not True:_abort('desktop_fx_history_review_confirmation_required')
 if v.get('owner_fingerprint')!=evidence.owner(space,ctx):_abort('desktop_fx_history_review_preview_invalid')
 with evidence.locked(space) as root:
  return _stage_locked(space,context,ctx,v,root,transport,clock)
def _stage_locked(space,context,ctx,v,root,transport,clock):
 attempts=evidence.mkdir(root,'attempts');results=evidence.mkdir(root,'results');key=v['preview_fingerprint'][:32];name=f'fxh_{key}.json';result_path=results/name
 if os.path.lexists(result_path):return evidence.result_read(result_path,space,ctx)
 if os.path.lexists(attempts/name):_abort('desktop_fx_history_review_attempt_consumed')
 evidence.assert_no_unreviewed_overlap(space,ctx,v)
 if preview_desktop_fx_history_fetch_v1(space,context,v['source_currency'],v['target_currency'],v['start_date'],v['end_date'],v['created_at_utc'])!=v:_abort('desktop_fx_history_review_preview_invalid')
 s,e=_range(v['start_date'],v['end_date'])
 # Dasselbe wie beim Kursabruf: Ein Ein-Tages-Fenster liefert bei einem
 # Waehrungspaar null Balken. Der Parser verwirft jeden Tag ausserhalb des
 # angefragten Bereichs, deshalb aendert das Aufweiten am Bestand nichts
 # (#283).
 w=min(s,e-timedelta(days=4));symbol=v['provider_binding']['provider_symbol']
 attempt=dict(contract_version='desktop_fx_history_attempt_v2',preview_fingerprint=v['preview_fingerprint'],owner_fingerprint=evidence.owner(space,ctx),source_currency=v['source_currency'],target_currency=v['target_currency'],start_date=v['start_date'],end_date=v['end_date'],trusted_preview=v,provider_access_authorized=True,automatic_retry=False)
 evidence.write(attempts/name,evidence.seal(attempt))
 phase='transport_callback';http_status=None
 try:
  request=price_providers.build_request_v1(PROVIDER_ID,'fx_daily_history',{'provider_symbol':symbol,'start_date':v['start_date'],'end_date':v['end_date'],'request_start_date':w.isoformat()})
  response=transport(request['host'],request['target'],{'Accept':'application/json','Accept-Encoding':'identity','Connection':'close','User-Agent':'Portelyra/0.2 FX-History'},TIMEOUT,BYTE_LIMIT)
  retrieved=clock().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ');phase='response_envelope'
  if not isinstance(response,dict) or set(response)!={'status','headers','body'} or type(response['status']) is not int or not isinstance(response['headers'],dict) or not isinstance(response['body'],bytes) or len(response['body'])>BYTE_LIMIT:_abort('desktop_fx_history_review_response_invalid')
  http_status=response['status'];content_type=response['headers'].get('content-type','')
  if not isinstance(content_type,str):_abort('desktop_fx_history_review_response_invalid')
  evidence.write(evidence.mkdir(root,'responses')/name,evidence.seal(dict(contract_version='desktop_fx_history_response_v2',preview_fingerprint=v['preview_fingerprint'],retrieved_at_utc=retrieved,http_status=http_status,content_type=content_type[:256],body_base64=base64.b64encode(response['body']).decode('ascii'),body_sha256=_sha(response['body']))))
  phase='http_status'
  if http_status!=200:_abort('desktop_fx_history_review_response_invalid')
  phase='content_type'
  if not content_type.lower().startswith('application/json'):_abort('desktop_fx_history_review_response_invalid')
  phase='response_parse';parsed=_parse_response(response['body'],{'provider_symbol':symbol,'start_date':v['start_date'],'end_date':v['end_date'],'request_ref':'fxr_'+key},retrieved)
  phase='response_identity'
  if parsed['provider_currency']!=v['pair']['quote_currency'] or parsed['split_review_required']:_abort('desktop_fx_history_review_response_invalid')
  phase='candidate_validation';candidate=_candidate(v,parsed,retrieved,ctx)
 except Exception as error:
  code='desktop_fx_history_review_transport_failed' if phase=='transport_callback' else 'desktop_fx_history_review_response_invalid'
  # Do not misreport an evidence-store failure as a provider response failure.
  if isinstance(error,DesktopFxHistoryReviewV1Error) and error.code=='desktop_fx_history_review_store_invalid':raise
  evidence.write(evidence.mkdir(root,'failures')/name,evidence.seal(dict(contract_version='desktop_fx_history_failure_v2',preview_fingerprint=v['preview_fingerprint'],category=phase,http_status=http_status,code=code,network_start_proven=False,automatic_retry=False)))
  raise DesktopFxHistoryReviewV1Error(code) from error
 days=candidate['days'];result={'contract_version':'desktop_fx_history_staged_v1','status':'staged','preview_fingerprint':v['preview_fingerprint'],'owner_fingerprint':evidence.owner(space,ctx),'candidate':candidate,'source_currency':v['source_currency'],'target_currency':v['target_currency'],'direction':v['direction'],'start_date':v['start_date'],'end_date':v['end_date'],'observed_day_count':sum(x['day_status']=='observed' for x in days),'non_trading_day_count':sum(x['day_status']=='non_trading_day' for x in days),'source_gap_day_count':sum(x['day_status']=='source_gap' for x in days),'provider_access':True,'network_access':True,'owner_local_staging':True,'fx_history_write':False,'canonical_write':False,'automatic_retry':False};result['staging_fingerprint']=_sha(result);evidence.write(result_path,result);return result
def public_desktop_fx_history_review_v1(v):return {k:v[k] for k in ('contract_version','status','source_currency','target_currency','direction','start_date','end_date','observed_day_count','non_trading_day_count','source_gap_day_count','provider_access','network_access','owner_local_staging','fx_history_write','canonical_write','automatic_retry')}
def publish_desktop_fx_history_v1(data_space_path,context,staged,public_review,confirmed,completed_at_utc):
 ctx=_ctx(context);_utc(completed_at_utc)
 if not isinstance(staged,dict) or staged.get('staging_fingerprint')!=_sha({k:x for k,x in staged.items() if k!='staging_fingerprint'}) or public_review!=public_desktop_fx_history_review_v1(staged) or not confirmed:_abort('desktop_fx_history_review_confirmation_required')
 try:r=append_fx_history_v1(_space(data_space_path,ctx)/AREA/STORE,ctx,staged['candidate'],completed_at_utc)
 except FxHistoryBlocked as e:raise DesktopFxHistoryReviewV1Error('desktop_fx_history_review_write_failed') from e
 return {'contract_version':'desktop_fx_history_publication_v1','status':'published','source_currency':staged['source_currency'],'target_currency':staged['target_currency'],'appended_day_count':r.appended_day_count,'corrected_day_count':r.corrected_day_count,'unchanged_day_count':r.unchanged_day_count,'provider_access':False,'network_access':False,'fx_history_write':True,'canonical_write':False,'provider_refetch':False,'exact_replay':r.exact_replay}
