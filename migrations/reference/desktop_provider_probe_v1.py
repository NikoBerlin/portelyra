#!/usr/bin/env python3
"""One-attempt Daily probe with persistent normalized evidence (request and parsing by the price provider plugin since rc.382).

Seit rc.394 (#495) fuer jeden geladenen Kursanbieter mit Tageskursen: Der Anbieter kommt aus der Zuordnung, abgerufen wird ueber den
gemeinsamen Abrufweg des Kerns (Zugang, Kosten; ``plugin_credentials_v1.provider_get_v1``). Fuer Yahoo aendert sich nichts.

The probe validates an owner-created unverified Provider mapping. It does not verify
that mapping and does not write canonical Daily Market History. A later separately
confirmed promotion may consume the sealed probe evidence without another request.
"""
from __future__ import annotations
from datetime import date,datetime,timezone
import hashlib,json,os,re,stat
from pathlib import Path
from typing import Mapping

from migrations.reference import price_provider_plugins_v1 as price_providers
from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1

CONTRACT_VERSION=1
AREA_NAME='provider-probe-v1'
PROVIDER_ID='yahoo'
TIMEOUT=price_providers.FETCH_TIMEOUT_SECONDS;BYTE_LIMIT=price_providers.FETCH_BYTE_LIMIT
FAILURE_CODES=frozenset({
 'desktop_provider_probe_boundary_failed','desktop_provider_probe_confirmation_required',
 'desktop_provider_probe_context_invalid','desktop_provider_probe_input_invalid',
 'desktop_provider_probe_preview_invalid','desktop_provider_probe_attempt_consumed',
 'desktop_provider_probe_store_invalid','desktop_provider_probe_transport_failed',
 'desktop_provider_probe_response_invalid','desktop_provider_probe_result_invalid',
 'desktop_provider_probe_credential_unavailable','desktop_provider_probe_cost_limit','desktop_provider_probe_scheduled_disabled',
})
SHA=re.compile(r'^[a-f0-9]{64}$');REQUEST=re.compile(r'^pbr_[a-f0-9]{32}$');NONCE=re.compile(r'^pbn_[A-Za-z0-9_-]{12,64}$');DATE=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')

class DesktopProviderProbeV1Error(RuntimeError):
 def __init__(self,code):
  if code not in FAILURE_CODES:raise ValueError('desktop_provider_probe_error_unregistered')
  self.code=code;super().__init__(code)
def desktop_provider_probe_v1_error_codes():return tuple(sorted(FAILURE_CODES))
def _abort(code):raise DesktopProviderProbeV1Error(code)
def _canonical(value):
 try:return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
 except Exception:_abort('desktop_provider_probe_input_invalid')
def _sha(value):return hashlib.sha256(value if isinstance(value,bytes) else _canonical(value)).hexdigest()
def _text(value,maximum=160):
 if not isinstance(value,str) or value!=value.strip() or not 1<=len(value)<=maximum or any(ord(c)<32 or ord(c)==127 for c in value):_abort('desktop_provider_probe_input_invalid')
 return value
def _utc(value):
 if not isinstance(value,str) or re.fullmatch(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$',value) is None:_abort('desktop_provider_probe_input_invalid')
 try:parsed=datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
 except ValueError:_abort('desktop_provider_probe_input_invalid')
 if parsed.strftime('%Y-%m-%dT%H:%M:%SZ')!=value:_abort('desktop_provider_probe_input_invalid')
 return value
def _context(value):
 if isinstance(value,Mapping):
  try:value=DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
  except (KeyError,TypeError) as error:raise DesktopProviderProbeV1Error('desktop_provider_probe_context_invalid') from error
 if not isinstance(value,DesktopProviderSearchContextV1) or value.role!='market_worker' or value.actor_id!='market_worker' or not value.data_space_id.startswith('sbx_') or any(not isinstance(item,str) or re.fullmatch(r'^[A-Za-z0-9_-]{3,64}$',item) is None for item in (value.tenant_id,value.user_id,value.data_space_id)):_abort('desktop_provider_probe_context_invalid')
 return value
def _context_fp(value):
 value=_context(value);return _sha({'contract':'desktop_provider_probe_context_v1','tenant_id':value.tenant_id,'user_id':value.user_id,'data_space_id':value.data_space_id,'actor_id':value.actor_id,'role':value.role})
def _owner_dir(path):
 path=Path(path)
 try:info=path.stat(follow_symlinks=False);resolved=path.resolve(strict=True)
 except OSError:_abort('desktop_provider_probe_store_invalid')
 if not path.is_absolute() or path.is_symlink() or resolved!=path or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.geteuid():_abort('desktop_provider_probe_store_invalid')
 current=path
 while current.parent!=current:
  if current.is_symlink():_abort('desktop_provider_probe_store_invalid')
  current=current.parent
 return path
def _ensure_child(parent,name):
 parent=_owner_dir(parent);path=parent/name
 if not path.exists():
  try:os.mkdir(path,0o700);os.chmod(path,0o700)
  except OSError:_abort('desktop_provider_probe_store_invalid')
 return _owner_dir(path)
def _write_create(path,value):
 descriptor=None
 try:
  descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.write(descriptor,_canonical(value)+b'\n');os.fsync(descriptor);os.close(descriptor);descriptor=None
  if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)!=0o600:_abort('desktop_provider_probe_store_invalid')
 except FileExistsError:_abort('desktop_provider_probe_attempt_consumed')
 except DesktopProviderProbeV1Error:raise
 except OSError:_abort('desktop_provider_probe_store_invalid')
 finally:
  if descriptor is not None:os.close(descriptor)
def _date(value):
 if not isinstance(value,str) or DATE.fullmatch(value) is None:_abort('desktop_provider_probe_input_invalid')
 try:parsed=date.fromisoformat(value)
 except ValueError:_abort('desktop_provider_probe_input_invalid')
 if parsed.isoformat()!=value:_abort('desktop_provider_probe_input_invalid')
 return parsed
def history_provider_v1(provider_id):
 """Ein geladener Kursanbieter mit Tageskursen (Yahoo, EODHD ...); sonst None. Ob er im Datenraum aktiv ist, prueft das Skript."""
 if not isinstance(provider_id,str):return None
 spec=price_providers.provider_spec_v1(provider_id)
 return spec if spec is not None and 'daily_history' in spec.operations else None
def core_transport_v1(data_space,context,provider_id,abort,prefix):
 """Abruf ueber den gemeinsamen Weg des Kerns: Zugang nur an bestaetigte Hosts, Kosten gezaehlt, Herkunft "von Hand bestaetigt"
 (im Zeitlauf macht der Kern daraus "zeitgesteuert"). Ein kostenloser Anbieter ohne Zugang (Yahoo) geht unveraendert an https_get_v1.
 ``abort(code)`` bricht mit dem Code des aufrufenden Moduls ab: ``<prefix>_credential_unavailable``, ``<prefix>_scheduled_disabled``
 (im Zeitlauf nicht freigegeben, Vorgabe), ``<prefix>_cost_limit``,
 ``<prefix>_response_invalid`` (zu gross) oder ``<prefix>_transport_failed``."""
 from migrations.reference import plugin_credentials_v1 as credentials
 from migrations.reference import price_provider_costs_v1 as costs
 def fetch(host,target,headers,timeout_seconds,response_byte_limit):
  try:return credentials.provider_get_v1(data_space,context,provider_id,{'host':host,'target':target},headers,origin='interactive')
  except credentials.PluginCredentialsV1Error:abort(prefix+'_credential_unavailable')
  except costs.PriceProviderCostsV1Error as error:abort(prefix+('_scheduled_disabled' if error.code=='price_provider_costs_scheduled_disabled' else '_cost_limit'))
  except price_providers.PriceProviderBlocked as error:
   if error.code=='price_provider_response_too_large':abort(prefix+'_response_invalid')
   abort(prefix+'_transport_failed')
 return fetch
def _mapping(value):
 required={'mapping_id','mapping_revision','asset_id','provider_id','provider_symbol','provider_currency','capability','mapping_fingerprint'}
 if not isinstance(value,Mapping) or set(value)!=required or not isinstance(value.get('mapping_id'),str) or not value['mapping_id'].startswith('map_') or not isinstance(value.get('mapping_revision'),int) or value['mapping_revision']<1 or not isinstance(value.get('asset_id'),str) or not value['asset_id'].startswith('ast_') or history_provider_v1(value.get('provider_id')) is None or value.get('capability')!='daily_history' or not isinstance(value.get('mapping_fingerprint'),str) or SHA.fullmatch(value['mapping_fingerprint']) is None:_abort('desktop_provider_probe_input_invalid')
 symbol=_text(value.get('provider_symbol'),120);currency=_text(value.get('provider_currency'),3)
 if re.fullmatch(r'[A-Z]{3}',currency) is None:_abort('desktop_provider_probe_input_invalid')
 return dict(value,provider_symbol=symbol,provider_currency=currency)
def preview_desktop_provider_probe_v1(context,mapping,start_date,end_date,request_nonce,created_at_utc):
 context=_context(context);mapping=_mapping(mapping);start=_date(start_date);end=_date(end_date);created=_utc(created_at_utc)
 if end<start or (end-start).days>31 or not isinstance(request_nonce,str) or NONCE.fullmatch(request_nonce) is None:_abort('desktop_provider_probe_input_invalid')
 request_ref='pbr_'+_sha({'contract':'desktop_provider_probe_request_v1','context':_context_fp(context),'mapping_fingerprint':mapping['mapping_fingerprint'],'mapping_revision':mapping['mapping_revision'],'start_date':start_date,'end_date':end_date,'nonce':request_nonce})[:32]
 body={'contract_version':'desktop_provider_probe_preview_v1','request_ref':request_ref,'provider_id':mapping['provider_id'],'provider_symbol':mapping['provider_symbol'],'provider_currency':mapping['provider_currency'],'mapping_id':mapping['mapping_id'],'mapping_revision':mapping['mapping_revision'],'asset_id':mapping['asset_id'],'mapping_fingerprint':mapping['mapping_fingerprint'],'start_date':start_date,'end_date':end_date,'created_at_utc':created,'context_fingerprint':_context_fp(context),'one_attempt':True,'automatic_retry':False,'canonical_write':False,'market_history_write':False}
 body['preview_fingerprint']=_sha(body);return body
def _validate_preview(value):
 required={'contract_version','request_ref','provider_id','provider_symbol','provider_currency','mapping_id','mapping_revision','asset_id','mapping_fingerprint','start_date','end_date','created_at_utc','context_fingerprint','one_attempt','automatic_retry','canonical_write','market_history_write','preview_fingerprint'}
 if not isinstance(value,dict) or set(value)!=required or value.get('contract_version')!='desktop_provider_probe_preview_v1' or not isinstance(value.get('request_ref'),str) or REQUEST.fullmatch(value['request_ref']) is None or history_provider_v1(value.get('provider_id')) is None or not isinstance(value.get('mapping_revision'),int) or value['mapping_revision']<1 or not isinstance(value.get('mapping_fingerprint'),str) or SHA.fullmatch(value['mapping_fingerprint']) is None or not isinstance(value.get('context_fingerprint'),str) or SHA.fullmatch(value['context_fingerprint']) is None or value.get('one_attempt') is not True or any(value.get(field) is not False for field in ('automatic_retry','canonical_write','market_history_write')):_abort('desktop_provider_probe_preview_invalid')
 _text(value.get('provider_symbol'),120);currency=_text(value.get('provider_currency'),3);start=_date(value.get('start_date'));end=_date(value.get('end_date'));_utc(value.get('created_at_utc'))
 if re.fullmatch(r'[A-Z]{3}',currency) is None or end<start or (end-start).days>31:_abort('desktop_provider_probe_preview_invalid')
 body={key:item for key,item in value.items() if key!='preview_fingerprint'}
 if value.get('preview_fingerprint')!=_sha(body):_abort('desktop_provider_probe_preview_invalid')
 return value
def public_desktop_provider_probe_preview_v1(value):
 value=_validate_preview(value);return {'contract_version':'desktop_provider_probe_public_preview_v1','status':'pending_confirmation','provider_id':value['provider_id'],'provider_symbol':value['provider_symbol'],'expected_currency':value['provider_currency'],'start_date':value['start_date'],'end_date':value['end_date'],'maximum_calendar_days':32,'one_attempt':True,'confirmation_required':True,'provider_access':False,'network_access':False,'canonical_write':False,'market_history_write':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}
def _now(clock):
 value=clock()
 if not isinstance(value,datetime) or value.utcoffset() is None:_abort('desktop_provider_probe_input_invalid')
 return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def with_observation_refs_v1(result,request_ref):
 """Die Kennung je Tag bildet der Kern, nicht das Plugin - dieselbe Formel wie bis rc.381."""
 days=[dict(row,source_observation_ref='mor_'+_sha({'request_ref':request_ref,'trading_date':row['trading_date'],'values':[row['open_decimal'],row['high_decimal'],row['low_decimal'],row['close_decimal'],row['volume_decimal']]})[:32]) for row in result['days']]
 return dict(result,days=days)
def provider_request_v1(operation,params,provider_id=PROVIDER_ID):
 """Die Anfrage baut das Kursanbieter-Plugin (#495, rc.382); Host und Ziel prueft price_provider_plugins_v1 gegen das Manifest."""
 return price_providers.build_request_v1(provider_id,operation,params)
def _default_transport(host,target,headers,timeout,limit):
 # Netz nur im Kern (Festlegung 09.11.2026): nur an Hosts aus dem Manifest eines gueltigen Kursanbieter-Plugins.
 try:return price_providers.https_get_v1(host,target,headers,timeout,limit)
 except price_providers.PriceProviderBlocked as error:
  if error.code=='price_provider_response_too_large':_abort('desktop_provider_probe_response_invalid')
  _abort('desktop_provider_probe_transport_failed')
def _parse_response(body,preview,observed_at,provider_id=None):
 """Tagesbalken einer Antwort mit HTTP 200; die Auswertung liegt seit rc.382 im Kursanbieter-Plugin (dem der Zuordnung, rc.394)."""
 provider_id=provider_id or preview.get('provider_id') or PROVIDER_ID
 try:
  outcome=price_providers.parse_response_v1(provider_id,'daily_history',{'provider_symbol':preview['provider_symbol'],'start_date':preview['start_date'],'end_date':preview['end_date']},{'status':200,'content_type':'application/json','body':body})
 except (price_providers.PriceProviderBlocked,KeyError,TypeError):_abort('desktop_provider_probe_response_invalid')
 if outcome['outcome']!='ok':_abort('desktop_provider_probe_response_invalid')
 return with_observation_refs_v1(outcome['result'],preview['request_ref'])
def _read_result(path,preview):
 try:
  if path.is_symlink() or stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)!=0o600:_abort('desktop_provider_probe_result_invalid')
  value=json.loads(path.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError):_abort('desktop_provider_probe_result_invalid')
 fingerprint=value.pop('probe_evidence_fingerprint',None) if isinstance(value,dict) else None
 if not isinstance(value,dict) or value.get('request_ref')!=preview['request_ref'] or value.get('preview_fingerprint')!=preview['preview_fingerprint'] or fingerprint!=_sha(value):_abort('desktop_provider_probe_result_invalid')
 value['probe_evidence_fingerprint']=fingerprint;return value
def _public(value):
 days=value['days'];observed=sum(row['day_status']=='observed' for row in days)
 # Ergebnisse bis rc.393 tragen keinen Anbieter: Sie stammen alle von Yahoo.
 return {'contract_version':'desktop_provider_probe_result_v1','status':'completed','provider_id':value.get('provider_id','yahoo'),'provider_symbol':value['provider_symbol'],'expected_currency':value['expected_currency'],'observed_currency':value['provider_currency'],'currency_match':value['provider_currency']==value['expected_currency'],'exchange':value['exchange'],'timezone_name':value['timezone_name'],'requested_start_date':value['start_date'],'requested_end_date':value['end_date'],'first_observed_date':days[0]['trading_date'] if days else None,'last_observed_date':days[-1]['trading_date'] if days else None,'observed_day_count':observed,'source_gap_day_count':len(days)-observed,'live_session':value.get('live_session'),'first_trade_date':value.get('first_trade_date'),'instrument_name':value.get('instrument_name'),'instrument_type':value.get('instrument_type'),'last_close_decimal':next((row['close_decimal'] for row in reversed(days) if row['day_status']=='observed'),None),'split_review_required':value['split_review_required'],'provider_access':True,'network_access':True,'probe_evidence_persisted':True,'canonical_write':False,'market_history_write':False,'automatic_retry':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}
def public_desktop_provider_probe_result_v1(value):return _public(value)
@price_providers.within_price_provider_session
def apply_desktop_provider_probe_v1(data_space_path,context,preview,public_preview,confirmed,*,transport=None,clock=lambda:datetime.now(timezone.utc)):
 context=_context(context);trusted=_validate_preview(preview)
 if trusted['context_fingerprint']!=_context_fp(context) or public_preview!=public_desktop_provider_probe_preview_v1(trusted):_abort('desktop_provider_probe_preview_invalid')
 if confirmed is not True:_abort('desktop_provider_probe_confirmation_required')
 data_space=_owner_dir(Path(data_space_path))
 if data_space.name!=context.data_space_id:_abort('desktop_provider_probe_store_invalid')
 area=_ensure_child(data_space,AREA_NAME);attempts=_ensure_child(area,'attempts');results=_ensure_child(area,'results');failures=_ensure_child(area,'failures');result_path=results/f"{trusted['request_ref']}.json"
 if result_path.exists():return _public(_read_result(result_path,trusted))
 started=_now(clock);attempt={'contract_version':'desktop_provider_probe_attempt_v1','request_ref':trusted['request_ref'],'preview_fingerprint':trusted['preview_fingerprint'],'mapping_fingerprint':trusted['mapping_fingerprint'],'started_at_utc':started,'attempt_count':1,'provider_access_authorized':True,'automatic_retry':False,'canonical_write':False,'market_history_write':False};attempt['attempt_fingerprint']=_sha(attempt)
 try:_write_create(attempts/f"{trusted['request_ref']}.json",attempt)
 except DesktopProviderProbeV1Error as error:
  if error.code=='desktop_provider_probe_attempt_consumed':raise
  raise
 try:
  provider_id=trusted['provider_id']
  if transport is None:transport=core_transport_v1(data_space,context,provider_id,_abort,'desktop_provider_probe')
  try:request=provider_request_v1('daily_history',{'provider_symbol':trusted['provider_symbol'],'start_date':trusted['start_date'],'end_date':trusted['end_date'],'request_start_date':trusted['start_date']},provider_id)
  except price_providers.PriceProviderBlocked:_abort('desktop_provider_probe_transport_failed')
  response=transport(request['host'],request['target'],{'Accept':'application/json','Accept-Encoding':'identity','Connection':'close','User-Agent':'Portelyra/0.2 Asset-Center-Probe'},TIMEOUT,BYTE_LIMIT);completed=_now(clock)
  if not isinstance(response,dict) or set(response)!={'status','headers','body'} or response['status']!=200 or not isinstance(response['headers'],dict) or not isinstance(response['body'],bytes) or len(response['body'])>BYTE_LIMIT or not response['headers'].get('content-type','').lower().startswith('application/json'):_abort('desktop_provider_probe_response_invalid')
  parsed=_parse_response(response['body'],trusted,completed);result={'contract_version':'desktop_provider_probe_private_result_v1','request_ref':trusted['request_ref'],'preview_fingerprint':trusted['preview_fingerprint'],'mapping_id':trusted['mapping_id'],'mapping_revision':trusted['mapping_revision'],'mapping_fingerprint':trusted['mapping_fingerprint'],'asset_id':trusted['asset_id'],'context_fingerprint':trusted['context_fingerprint'],'expected_currency':trusted['provider_currency'],'start_date':trusted['start_date'],'end_date':trusted['end_date'],'started_at_utc':started,'completed_at_utc':completed,**parsed,'provider_id':provider_id,'provider_access':True,'network_access':True,'canonical_write':False,'market_history_write':False,'automatic_retry':False};result['probe_evidence_fingerprint']=_sha(result);_write_create(result_path,result);return _public(result)
 except DesktopProviderProbeV1Error as error:
  failure={'contract_version':'desktop_provider_probe_failure_v1','request_ref':trusted['request_ref'],'attempt_fingerprint':attempt['attempt_fingerprint'],'failure_code':error.code,'failed_at_utc':_now(clock),'provider_access':True,'automatic_retry':False};failure['failure_fingerprint']=_sha(failure)
  try:_write_create(failures/f"{trusted['request_ref']}.json",failure)
  except Exception:pass
  raise
 except Exception:
  failure={'contract_version':'desktop_provider_probe_failure_v1','request_ref':trusted['request_ref'],'attempt_fingerprint':attempt['attempt_fingerprint'],'failure_code':'desktop_provider_probe_transport_failed','failed_at_utc':_now(clock),'provider_access':True,'automatic_retry':False};failure['failure_fingerprint']=_sha(failure)
  try:_write_create(failures/f"{trusted['request_ref']}.json",failure)
  except Exception:pass
  _abort('desktop_provider_probe_transport_failed')

def recover_desktop_provider_probe_evidence_v1(data_space_path,context,mapping):
 context=_context(context);mapping=_mapping(mapping);data_space=_owner_dir(Path(data_space_path))
 if data_space.name!=context.data_space_id:_abort('desktop_provider_probe_store_invalid')
 results=data_space/AREA_NAME/'results'
 if not results.exists():return None
 if not results.is_dir() or results.is_symlink():_abort('desktop_provider_probe_store_invalid')
 matches=[]
 for path in sorted(results.glob('pbr_*.json')):
  request_ref=path.stem
  try:value=read_desktop_provider_probe_evidence_v1(data_space,context,request_ref)
  except DesktopProviderProbeV1Error:_abort('desktop_provider_probe_result_invalid')
  if value.get('mapping_id')==mapping['mapping_id'] and value.get('mapping_revision')==mapping['mapping_revision'] and value.get('mapping_fingerprint')==mapping['mapping_fingerprint'] and value.get('provider_symbol')==mapping['provider_symbol']:matches.append(value)
 if not matches:return None
 matches.sort(key=lambda row:(row['completed_at_utc'],row['request_ref']))
 return matches[-1]
def read_desktop_provider_probe_evidence_v1(data_space_path,context,request_ref):
 context=_context(context)
 if not isinstance(request_ref,str) or REQUEST.fullmatch(request_ref) is None:_abort('desktop_provider_probe_input_invalid')
 data_space=_owner_dir(Path(data_space_path))
 if data_space.name!=context.data_space_id:_abort('desktop_provider_probe_store_invalid')
 path=data_space/AREA_NAME/'results'/f'{request_ref}.json'
 if not path.is_file():_abort('desktop_provider_probe_result_invalid')
 try:value=json.loads(path.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError):_abort('desktop_provider_probe_result_invalid')
 fingerprint=value.pop('probe_evidence_fingerprint',None) if isinstance(value,dict) else None
 if not isinstance(value,dict) or value.get('context_fingerprint')!=_context_fp(context) or fingerprint!=_sha(value):_abort('desktop_provider_probe_result_invalid')
 value['probe_evidence_fingerprint']=fingerprint;return value

__all__=['DesktopProviderProbeV1Error','apply_desktop_provider_probe_v1','core_transport_v1','history_provider_v1','desktop_provider_probe_v1_error_codes','preview_desktop_provider_probe_v1','public_desktop_provider_probe_preview_v1','public_desktop_provider_probe_result_v1','read_desktop_provider_probe_evidence_v1','recover_desktop_provider_probe_evidence_v1']
