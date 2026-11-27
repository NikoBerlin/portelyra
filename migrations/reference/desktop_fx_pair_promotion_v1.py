#!/usr/bin/env python3
"""Separately confirmed schema-2600 promotion of staged FX pair probe evidence."""
from __future__ import annotations
from datetime import date,timedelta
import hashlib,json,os,re,stat
from pathlib import Path
from typing import Any,Mapping
from migrations.reference import price_provider_plugins_v1 as price_providers
from migrations.reference.fx_history_v1 import FxHistoryBlocked,FxHistoryContext,append_fx_history_v1,bind_fx_pair_v1,bootstrap_fx_history_store_v1,fx_history_context_fingerprint_v1,fx_history_job_binding_fingerprint_v1,new_fx_pair_binding_v1,read_fx_pair_catalog_v1,seal_fx_history_candidate_v1
# Das alte Beschreibungs-Manifest bleibt Teil des Katalogabdrucks jedes Paares (sonst waeren bestehende Paare ungueltig); die
# Herkunft je Abruf traegt seit rc.382 das Kursanbieter-Plugin, das die Antwort gelesen hat.
ROOT=Path(__file__).resolve().parents[2];MANIFEST=ROOT/'contracts/desktop-fx-pair-promotion/v1/yahoo-provider-manifest.json';AREA='fx-history-v1';STORE='fx-history.sqlite';SHA=re.compile(r'^[a-f0-9]{64}$')
FAILURE_CODES=frozenset({'desktop_fx_pair_promotion_context_invalid','desktop_fx_pair_promotion_input_invalid','desktop_fx_pair_promotion_preview_invalid','desktop_fx_pair_promotion_confirmation_required','desktop_fx_pair_promotion_store_invalid','desktop_fx_pair_promotion_conflict','desktop_fx_pair_promotion_write_failed'})
class DesktopFxPairPromotionV1Error(RuntimeError):
 def __init__(self,code):
  if code not in FAILURE_CODES:raise ValueError('desktop_fx_pair_promotion_error_unregistered')
  self.code=code;super().__init__(code)
def _abort(c):raise DesktopFxPairPromotionV1Error(c)
def _canon(v):return json.dumps(v,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
def _sha(v):return hashlib.sha256(v if isinstance(v,bytes) else _canon(v)).hexdigest()
def _ctx(v):
 if not isinstance(v,Mapping) or v.get('actor_id')!='market_worker' or v.get('role')!='market_worker':_abort('desktop_fx_pair_promotion_context_invalid')
 try:return FxHistoryContext(v['tenant_id'],v['user_id'],v['data_space_id'],v['actor_id'],v['role'])
 except (KeyError,TypeError):_abort('desktop_fx_pair_promotion_context_invalid')
def _probe(v):
 required={'contract_version','status','preview_fingerprint','source_currency','target_currency','direction','symbol','provider_currency','exchange','timezone_name','start_date','end_date','days','provider_access','network_access','owner_local_staging','fx_history_write','canonical_write','automatic_retry','result_fingerprint'}
 if not isinstance(v,Mapping) or set(v)!=required or v.get('contract_version')!='desktop_fx_pair_probe_result_v1' or v.get('status')!='staged' or v.get('owner_local_staging') is not True or v.get('fx_history_write') is not False or v.get('canonical_write') is not False or v.get('automatic_retry') is not False or v.get('result_fingerprint')!=_sha({k:x for k,x in v.items() if k!='result_fingerprint'}):_abort('desktop_fx_pair_promotion_input_invalid')
 if v['direction']=='direct':base,quote=v['source_currency'],v['target_currency']
 elif v['direction']=='inverse':base,quote=v['target_currency'],v['source_currency']
 else:_abort('desktop_fx_pair_promotion_input_invalid')
 if v['provider_currency']!=quote or not isinstance(v['days'],list) or not v['days']:_abort('desktop_fx_pair_promotion_input_invalid')
 return dict(v),base,quote
def _space(path,ctx):
 p=Path(path)
 try:i=p.stat(follow_symlinks=False);r=p.resolve(strict=True)
 except OSError:_abort('desktop_fx_pair_promotion_store_invalid')
 if not p.is_absolute() or p.is_symlink() or r!=p or p.name!=ctx.data_space_id or stat.S_IMODE(i.st_mode)!=0o700 or i.st_uid!=os.geteuid():_abort('desktop_fx_pair_promotion_store_invalid')
 return p
def _utc(v):
 try:
  from datetime import datetime
  if datetime.strptime(v,'%Y-%m-%dT%H:%M:%SZ').strftime('%Y-%m-%dT%H:%M:%SZ')!=v:raise ValueError
 except (TypeError,ValueError):_abort('desktop_fx_pair_promotion_input_invalid')
 return v
def _days(probe):
 start=date.fromisoformat(probe['start_date']);end=date.fromisoformat(probe['end_date']);observed={x['trading_date']:x for x in probe['days']};out=[]
 for n in range((end-start).days+1):
  d=start+timedelta(days=n);text=d.isoformat();row=observed.get(text);ref='fxo_'+_sha([probe['result_fingerprint'],text])[:32]
  if row is not None and row['day_status']=='observed' and row['close_decimal'] is not None:status='observed';rate=row['close_decimal'];quality='complete';gap=None;at=row['observed_at_utc']
  elif d.weekday()>=5:status='non_trading_day';rate=None;quality='calendar_confirmed';gap=None;at=text+'T12:00:00Z'
  else:status='source_gap';rate=None;quality='explicit_gap';gap='source_no_data';at=text+'T12:00:00Z'
  out.append({'rate_date':text,'revision_mode':'initial','supersedes_revision_ref':None,'day_status':status,'rate_decimal':rate,'quality_status':quality,'gap_reason':gap,'source_observation_ref':ref,'observed_at_utc':at,'correction_reason':None})
 return out
def preview_desktop_fx_pair_promotion_v1(data_space_path,context,probe_result,created_at_utc):
 ctx=_ctx(context);space=_space(data_space_path,ctx);probe,base,quote=_probe(probe_result);created=_utc(created_at_utc);manifest_fp=hashlib.sha256(MANIFEST.read_bytes()).hexdigest();identity=price_providers.provider_identity_v1('yahoo');pair_ref='fxp_'+_sha({'context':fx_history_context_fingerprint_v1(ctx),'base':base,'quote':quote,'provider':'yahoo','symbol':probe['symbol']})[:32];days=_days(probe);catalog_fp=_sha({'provider':'yahoo','symbol':probe['symbol'],'probe':probe['result_fingerprint'],'manifest':manifest_fp});pair=new_fx_pair_binding_v1(pair_ref=pair_ref,base_currency=base,quote_currency=quote,market_code='YAHOO_FX',timezone_name=probe['timezone_name'],calendar_code='weekday_fx',rate_type='market_close',catalog_fingerprint=catalog_fp);request_ref='fxq_'+_sha(['probe_promotion',probe['result_fingerprint']])[:32];source_ref='fxs_'+_sha(['yahoo_fx_probe',probe['result_fingerprint']])[:32];request_fp=_sha({'pair':pair['pair_fingerprint'],'probe':probe['result_fingerprint'],'days':days});binding=fx_history_job_binding_fingerprint_v1(ctx,pair_ref=pair_ref,request_ref=request_ref,request_fingerprint=request_fp,source_ref=source_ref);candidate=seal_fx_history_candidate_v1(pair_ref=pair_ref,request_ref=request_ref,source_kind='market_plugin',source_ref=source_ref,source_version=identity['source_version'],plugin_id=identity['plugin_id'],plugin_version=identity['plugin_version'],plugin_manifest_fingerprint=identity['manifest_sha256'],request_fingerprint=request_fp,job_binding_fingerprint=binding,requested_start_date=probe['start_date'],requested_end_date=probe['end_date'],retrieved_at_utc=created,days=days)
 body={'contract_version':'desktop_fx_pair_promotion_preview_v1','status':'ready_for_confirmation','pair':pair,'candidate':candidate,'probe_result_fingerprint':probe['result_fingerprint'],'source_currency':probe['source_currency'],'target_currency':probe['target_currency'],'direction':probe['direction'],'symbol':probe['symbol'],'observed_day_count':sum(x['day_status']=='observed' for x in days),'non_trading_day_count':sum(x['day_status']=='non_trading_day' for x in days),'source_gap_day_count':sum(x['day_status']=='source_gap' for x in days),'created_at_utc':created,'context_fingerprint':fx_history_context_fingerprint_v1(ctx),'provider_access':False,'network_access':False,'fx_history_write':True,'canonical_write':False,'provider_refetch':False};body['preview_fingerprint']=_sha(body);return body
def _valid(v):
 if not isinstance(v,dict) or v.get('contract_version')!='desktop_fx_pair_promotion_preview_v1' or v.get('preview_fingerprint')!=_sha({k:x for k,x in v.items() if k!='preview_fingerprint'}):_abort('desktop_fx_pair_promotion_preview_invalid')
 return v
def public_desktop_fx_pair_promotion_preview_v1(v):
 v=_valid(v);return {k:v[k] for k in ('contract_version','status','source_currency','target_currency','direction','symbol','observed_day_count','non_trading_day_count','source_gap_day_count','provider_access','network_access','fx_history_write','canonical_write','provider_refetch')}
def _persist_provider_binding(area: Path, value: Mapping[str, Any]) -> None:
 try:
  root=area/'provider-bindings'
  if not root.exists():os.mkdir(root,0o700)
  if root.is_symlink() or stat.S_IMODE(root.stat().st_mode)!=0o700:_abort('desktop_fx_pair_promotion_store_invalid')
  path=root/f"{value['pair_ref']}.json";body=dict(value);body['binding_fingerprint']=_sha(body);payload=_canon(body)+b'\n'
  if path.exists():
   if path.is_symlink() or path.read_bytes()!=payload:_abort('desktop_fx_pair_promotion_conflict')
   return
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.write(fd,payload);os.fsync(fd);os.close(fd)
 except DesktopFxPairPromotionV1Error:raise
 except OSError as e:raise DesktopFxPairPromotionV1Error('desktop_fx_pair_promotion_store_invalid') from e


def apply_desktop_fx_pair_promotion_v1(data_space_path,context,preview,public_preview,confirmed,completed_at_utc):
 ctx=_ctx(context);v=_valid(preview);completed=_utc(completed_at_utc)
 if public_preview!=public_desktop_fx_pair_promotion_preview_v1(v) or not confirmed:_abort('desktop_fx_pair_promotion_confirmation_required')
 space=_space(data_space_path,ctx);area=space/AREA
 try:
  if not area.exists():os.mkdir(area,0o700)
  store=area/STORE
  if not store.exists():bootstrap_fx_history_store_v1(store,ctx,completed)
  catalog=read_fx_pair_catalog_v1(store,ctx);matching=[p for p in catalog['pairs'] if p['pair_ref']==v['pair']['pair_ref']]
  if matching and matching[0]['pair_fingerprint']!=v['pair']['pair_fingerprint']:_abort('desktop_fx_pair_promotion_conflict')
  bind_fx_pair_v1(store,ctx,v['pair'],completed)
  _persist_provider_binding(area,{'contract_version':'desktop_fx_pair_provider_binding_v1','pair_ref':v['pair']['pair_ref'],'provider_id':'yahoo','provider_symbol':v['symbol'],'provider_currency':v['pair']['quote_currency'],'direction':v['direction'],'pair_fingerprint':v['pair']['pair_fingerprint'],'probe_result_fingerprint':v['probe_result_fingerprint'],'plugin_manifest_fingerprint':v['candidate']['plugin_manifest_fingerprint']})
  receipt=append_fx_history_v1(store,ctx,v['candidate'],completed)
 except DesktopFxPairPromotionV1Error:raise
 except FxHistoryBlocked as e:raise DesktopFxPairPromotionV1Error('desktop_fx_pair_promotion_write_failed') from e
 except OSError as e:raise DesktopFxPairPromotionV1Error('desktop_fx_pair_promotion_store_invalid') from e
 return {'contract_version':'desktop_fx_pair_promotion_result_v1','status':'published','source_currency':v['source_currency'],'target_currency':v['target_currency'],'direction':v['direction'],'symbol':v['symbol'],'appended_day_count':receipt.appended_day_count,'corrected_day_count':receipt.corrected_day_count,'unchanged_day_count':receipt.unchanged_day_count,'provider_access':False,'network_access':False,'fx_history_write':True,'canonical_write':False,'provider_refetch':False,'exact_replay':receipt.exact_replay}
