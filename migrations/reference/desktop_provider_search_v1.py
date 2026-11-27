#!/usr/bin/env python3
"""Owner-confirmed one-attempt Provider search for the guided Asset Center.

Import and preview are provider-free. Tests inject an invented transport. The default
transport reaches only hosts named by a valid price provider plugin (rc.382), and is called only
after the Data UI submits one exact confirmed preview. Attempt evidence is persisted
before network access; an incomplete consumed attempt is never retried automatically.

Seit rc.392 (#495, Festlegung 10.11.2026): jeder geladene Kursanbieter mit der Operation "search", nicht mehr nur Yahoo - etwa das
Plugin EODHD fuer die Suche mit ISIN. Ohne eingefuegten Transport ruft der Kern ueber den Abrufweg mit Zugang und Kosten ab
(plugin_credentials_v1.provider_get_v1, Herkunft "interactive"); fehlt der Zugang oder ist die Obergrenze erreicht, sagt es der Code.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any,Callable,Mapping
from migrations.reference import plugin_credentials_v1 as credentials
from migrations.reference import price_provider_costs_v1 as costs
from migrations.reference import price_provider_plugins_v1 as price_providers

CONTRACT_VERSION=1
PROVIDER_ID='yahoo'
CONNECT_TIMEOUT_SECONDS=15;RESPONSE_BYTE_LIMIT=1_048_576
AREA_NAME='provider-search-v1'
FAILURE_CODES=frozenset({
 'desktop_provider_search_boundary_failed','desktop_provider_search_confirmation_required',
 'desktop_provider_search_context_invalid','desktop_provider_search_input_invalid',
 'desktop_provider_search_preview_invalid','desktop_provider_search_attempt_consumed',
 'desktop_provider_search_store_invalid','desktop_provider_search_transport_failed',
 'desktop_provider_search_response_invalid','desktop_provider_search_result_invalid',
 'desktop_provider_search_credential_unavailable','desktop_provider_search_cost_limit',
})
TOKEN=re.compile(r'^[A-Za-z0-9_-]{3,80}$')
UTC=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$')
SHA=re.compile(r'^[a-f0-9]{64}$')
REQUEST=re.compile(r'^psr_[a-f0-9]{32}$')
NONCE=re.compile(r'^srn_[A-Za-z0-9_-]{12,64}$')
MODES=frozenset({'auto','isin','name','symbol'})

class DesktopProviderSearchV1Error(RuntimeError):
 def __init__(self,code):
  if code not in FAILURE_CODES:raise ValueError('desktop_provider_search_error_unregistered')
  self.code=code;super().__init__(code)

def desktop_provider_search_v1_error_codes():return tuple(sorted(FAILURE_CODES))
def _abort(code):raise DesktopProviderSearchV1Error(code)
def _canonical(value):
 try:return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
 except Exception:_abort('desktop_provider_search_input_invalid')
def _sha(value):return hashlib.sha256(value if isinstance(value,bytes) else _canonical(value)).hexdigest()
def _utc(value):
 if not isinstance(value,str) or UTC.fullmatch(value) is None:_abort('desktop_provider_search_input_invalid')
 try:parsed=datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
 except ValueError:_abort('desktop_provider_search_input_invalid')
 if parsed.strftime('%Y-%m-%dT%H:%M:%SZ')!=value:_abort('desktop_provider_search_input_invalid')
 return value
def _text(value,maximum=160):
 if not isinstance(value,str) or value!=value.strip() or not 1<=len(value)<=maximum or any(ord(c)<32 or ord(c)==127 for c in value):_abort('desktop_provider_search_input_invalid')
 return value
def _default_https_transport(host,target,headers,timeout_seconds,response_byte_limit):
 # Netz nur im Kern (Festlegung 09.11.2026): nur an Hosts aus dem Manifest eines gueltigen Kursanbieter-Plugins (#495, rc.382).
 try:return price_providers.https_get_v1(host,target,headers,timeout_seconds,response_byte_limit)
 except price_providers.PriceProviderBlocked as error:
  if error.code=='price_provider_response_too_large':_abort('desktop_provider_search_response_invalid')
  _abort('desktop_provider_search_transport_failed')
def _search_provider(provider_id):
 """Ein geladener Kursanbieter mit Suche (Yahoo, EODHD ...); sonst None."""
 if not isinstance(provider_id,str):return None
 spec=price_providers.provider_spec_v1(provider_id)
 return spec if spec is not None and 'search' in spec.operations else None

def _provided_isin(value):
 # Provider metadata is only a proposal. No symbol lookup or inferred identifier.
 if not isinstance(value,str):return None
 value=value.strip().upper()
 if re.fullmatch(r'[A-Z]{2}[A-Z0-9]{9}[0-9]',value) is None:return None
 digits=''.join(str(ord(c)-55) if c.isalpha() else c for c in value)
 total=sum((int(c)*2//10+int(c)*2%10) if i%2 else int(c) for i,c in enumerate(reversed(digits)))
 return value if total%10==0 else None

def _normalize_quotes(payload,result_limit,provider_id=PROVIDER_ID):
 """Vorschlaege aus einer Antwort; die Auswertung liegt seit rc.382 im Kursanbieter-Plugin, die Pruefsumme je Vorschlag bildet der Kern."""
 try:outcome=price_providers.parse_response_v1(provider_id,'search',{'limit':result_limit},{'status':200,'content_type':'application/json','body':payload})
 except price_providers.PriceProviderBlocked:_abort('desktop_provider_search_response_invalid')
 if outcome['outcome']!='ok':_abort('desktop_provider_search_response_invalid')
 return [{**row,'source_quote_fingerprint':_sha(row)} for row in outcome['candidates']]

@dataclass(frozen=True)
class DesktopProviderSearchContextV1:
 tenant_id:str;user_id:str;data_space_id:str;actor_id:str='market_worker';role:str='market_worker'

def _context(value):
 if isinstance(value,Mapping):
  try:value=DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
  except (KeyError,TypeError) as error:raise DesktopProviderSearchV1Error('desktop_provider_search_context_invalid') from error
 if not isinstance(value,DesktopProviderSearchContextV1) or value.role!='market_worker' or value.actor_id!='market_worker' or not value.data_space_id.startswith('sbx_') or any(not isinstance(item,str) or TOKEN.fullmatch(item) is None or len(item)>64 for item in (value.tenant_id,value.user_id,value.data_space_id)):_abort('desktop_provider_search_context_invalid')
 return value

def _context_fp(value):
 value=_context(value);return _sha({'contract':'desktop_provider_search_context_v1','tenant_id':value.tenant_id,'user_id':value.user_id,'data_space_id':value.data_space_id,'actor_id':value.actor_id,'role':value.role})

def preview_desktop_provider_search_v1(context,provider_id,query,search_mode,request_nonce,created_at_utc):
 context=_context(context);query=_text(query);created=_utc(created_at_utc)
 if _search_provider(provider_id) is None or search_mode not in MODES or not isinstance(request_nonce,str) or NONCE.fullmatch(request_nonce) is None:_abort('desktop_provider_search_input_invalid')
 query_fp=hashlib.sha256(query.encode()).hexdigest();request_ref='psr_'+_sha({'contract':'desktop_provider_search_request_v1','context':_context_fp(context),'provider_id':provider_id,'query_fingerprint':query_fp,'search_mode':search_mode,'nonce':request_nonce})[:32]
 body={'contract_version':'desktop_provider_search_preview_v1','request_ref':request_ref,'provider_id':provider_id,'query':query,'query_fingerprint':query_fp,'search_mode':search_mode,'result_limit':10,'created_at_utc':created,'context_fingerprint':_context_fp(context),'endpoint_class':f'{provider_id}_market_search','one_attempt':True,'automatic_retry':False,'canonical_write':False,'market_history_write':False}
 body['preview_fingerprint']=_sha(body);return body

def public_desktop_provider_search_preview_v1(preview):
 value=_validate_preview(preview)
 return {'contract_version':'desktop_provider_search_public_preview_v1','status':'pending_confirmation','provider_id':value['provider_id'],'query':value['query'],'search_mode':value['search_mode'],'result_limit':value['result_limit'],'one_attempt':True,'confirmation_required':True,'provider_access':False,'network_access':False,'canonical_write':False,'market_history_write':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}

def _validate_preview(value):
 expected={'contract_version','request_ref','provider_id','query','query_fingerprint','search_mode','result_limit','created_at_utc','context_fingerprint','endpoint_class','one_attempt','automatic_retry','canonical_write','market_history_write','preview_fingerprint'}
 if not isinstance(value,dict) or set(value)!=expected or value.get('contract_version')!='desktop_provider_search_preview_v1' or not isinstance(value.get('request_ref'),str) or REQUEST.fullmatch(value['request_ref']) is None or _search_provider(value.get('provider_id')) is None or value.get('search_mode') not in MODES or value.get('result_limit')!=10 or value.get('endpoint_class')!=f"{value.get('provider_id')}_market_search" or value.get('one_attempt') is not True or any(value.get(field) is not False for field in ('automatic_retry','canonical_write','market_history_write')) or not isinstance(value.get('context_fingerprint'),str) or SHA.fullmatch(value['context_fingerprint']) is None:_abort('desktop_provider_search_preview_invalid')
 query=_text(value.get('query'));_utc(value.get('created_at_utc'))
 if value.get('query_fingerprint')!=hashlib.sha256(query.encode()).hexdigest():_abort('desktop_provider_search_preview_invalid')
 body={key:item for key,item in value.items() if key!='preview_fingerprint'}
 if value.get('preview_fingerprint')!=_sha(body):_abort('desktop_provider_search_preview_invalid')
 return value

def _owner_dir(path,code='desktop_provider_search_store_invalid'):
 path=Path(path)
 try:info=path.stat(follow_symlinks=False);resolved=path.resolve(strict=True)
 except OSError:_abort(code)
 if not path.is_absolute() or path.is_symlink() or resolved!=path or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode)!=0o700 or info.st_uid!=os.geteuid():_abort(code)
 current=path
 while current.parent!=current:
  if current.is_symlink():_abort(code)
  current=current.parent
 return path

def _ensure_child(parent,name):
 parent=_owner_dir(parent);path=parent/name
 if not path.exists():
  try:os.mkdir(path,0o700);os.chmod(path,0o700)
  except OSError:_abort('desktop_provider_search_store_invalid')
 return _owner_dir(path)

def _write_create(path,value):
 payload=_canonical(value)+b'\n';descriptor=None
 try:
  descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.write(descriptor,payload);os.fsync(descriptor);os.close(descriptor);descriptor=None
  if stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)!=0o600:_abort('desktop_provider_search_store_invalid')
 except FileExistsError:_abort('desktop_provider_search_attempt_consumed')
 except DesktopProviderSearchV1Error:raise
 except OSError:_abort('desktop_provider_search_store_invalid')
 finally:
  if descriptor is not None:os.close(descriptor)

def _read_result(path,preview):
 try:
  if path.is_symlink() or stat.S_IMODE(path.stat(follow_symlinks=False).st_mode)!=0o600:_abort('desktop_provider_search_result_invalid')
  value=json.loads(path.read_text(encoding='utf-8'))
 except (OSError,json.JSONDecodeError):_abort('desktop_provider_search_result_invalid')
 fingerprint=value.pop('result_fingerprint',None) if isinstance(value,dict) else None
 if not isinstance(value,dict) or value.get('request_ref')!=preview['request_ref'] or value.get('preview_fingerprint')!=preview['preview_fingerprint'] or fingerprint!=_sha(value):_abort('desktop_provider_search_result_invalid')
 value['result_fingerprint']=fingerprint;return value

def _now(clock):
 value=clock()
 if not isinstance(value,datetime) or value.utcoffset() is None:_abort('desktop_provider_search_input_invalid')
 return value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _public_result(value):
 return {'contract_version':'desktop_provider_search_result_v1','status':value['status'],'provider_id':value['provider_id'],'candidate_count':len(value['candidates']),'candidates':tuple({'symbol':row['symbol'],'display_name':row['display_name'],'exchange':row['exchange'],'quote_type':row['quote_type'],'quote_currency':row['quote_currency'],'isin':row.get('isin')} for row in value['candidates']),'provider_access':True,'network_access':True,'canonical_write':False,'market_history_write':False,'automatic_retry':False,'context_exposed':False,'paths_exposed':False,'fingerprints_exposed':False}

@price_providers.within_price_provider_session
def _core_transport(data_space,context,provider_id):
 """Abruf ueber den Kern mit Zugang (Schluessel nur an bestaetigte Hosts) und Kostenzaehlung; Herkunft: von Hand bestaetigt."""
 def fetch(host,target,headers,timeout_seconds,response_byte_limit):
  try:return credentials.provider_get_v1(data_space,context,provider_id,{'host':host,'target':target},headers,origin='interactive')
  except credentials.PluginCredentialsV1Error:_abort('desktop_provider_search_credential_unavailable')
  except costs.PriceProviderCostsV1Error:_abort('desktop_provider_search_cost_limit')
  except price_providers.PriceProviderBlocked as error:
   if error.code=='price_provider_response_too_large':_abort('desktop_provider_search_response_invalid')
   _abort('desktop_provider_search_transport_failed')
 return fetch

def apply_desktop_provider_search_v1(data_space_path,context,preview,public_preview,confirmed,*,transport=None,clock=lambda:datetime.now(timezone.utc)):
 context=_context(context);trusted=_validate_preview(preview)
 if trusted['context_fingerprint']!=_context_fp(context) or public_preview!=public_desktop_provider_search_preview_v1(trusted):_abort('desktop_provider_search_preview_invalid')
 if confirmed is not True:_abort('desktop_provider_search_confirmation_required')
 data_space=_owner_dir(Path(data_space_path))
 if data_space.name!=context.data_space_id:_abort('desktop_provider_search_store_invalid')
 area=_ensure_child(data_space,AREA_NAME);attempts=_ensure_child(area,'attempts');results=_ensure_child(area,'results');failures=_ensure_child(area,'failures')
 result_path=results/f"{trusted['request_ref']}.json"
 if result_path.exists():return _public_result(_read_result(result_path,trusted))
 attempt_path=attempts/f"{trusted['request_ref']}.json";started=_now(clock)
 attempt={'contract_version':'desktop_provider_search_attempt_v1','request_ref':trusted['request_ref'],'preview_fingerprint':trusted['preview_fingerprint'],'query_fingerprint':trusted['query_fingerprint'],'provider_id':trusted['provider_id'],'started_at_utc':started,'attempt_count':1,'provider_access_authorized':True,'automatic_retry':False,'canonical_write':False,'market_history_write':False}
 attempt['attempt_fingerprint']=_sha(attempt);_write_create(attempt_path,attempt)
 provider_id=trusted['provider_id']
 if transport is None:transport=_core_transport(data_space,context,provider_id)
 try:
  if not callable(transport):_abort('desktop_provider_search_input_invalid')
  try:request=price_providers.build_request_v1(provider_id,'search',{'query':trusted['query'],'limit':10})
  except price_providers.PriceProviderBlocked:_abort('desktop_provider_search_transport_failed')
  response=transport(request['host'],request['target'],{'Accept':'application/json','Accept-Encoding':'identity','Connection':'close','User-Agent':'Portelyra/0.2 Asset-Center-Search'},CONNECT_TIMEOUT_SECONDS,RESPONSE_BYTE_LIMIT)
  completed=_now(clock)
  if not isinstance(response,dict) or set(response)!={'status','headers','body'} or response['status']!=200 or not isinstance(response['headers'],dict) or not isinstance(response['body'],bytes) or len(response['body'])>RESPONSE_BYTE_LIMIT or not response['headers'].get('content-type','').lower().startswith('application/json'):_abort('desktop_provider_search_response_invalid')
  try:candidates=_normalize_quotes(response['body'],10,provider_id)
  except Exception:_abort('desktop_provider_search_response_invalid')
  result={'contract_version':'desktop_provider_search_private_result_v1','request_ref':trusted['request_ref'],'preview_fingerprint':trusted['preview_fingerprint'],'query_fingerprint':trusted['query_fingerprint'],'provider_id':provider_id,'status':'completed','started_at_utc':started,'completed_at_utc':completed,'attempt_count':1,'candidates':candidates,'provider_access':True,'network_access':True,'canonical_write':False,'market_history_write':False,'automatic_retry':False}
  result['result_fingerprint']=_sha(result);_write_create(result_path,result);return _public_result(result)
 except DesktopProviderSearchV1Error as error:
  failure={'contract_version':'desktop_provider_search_failure_v1','request_ref':trusted['request_ref'],'attempt_fingerprint':attempt['attempt_fingerprint'],'failure_code':error.code,'failed_at_utc':_now(clock),'provider_access':True,'automatic_retry':False}
  failure['failure_fingerprint']=_sha(failure)
  try:_write_create(failures/f"{trusted['request_ref']}.json",failure)
  except DesktopProviderSearchV1Error:pass
  raise
 except Exception:
  failure={'contract_version':'desktop_provider_search_failure_v1','request_ref':trusted['request_ref'],'attempt_fingerprint':attempt['attempt_fingerprint'],'failure_code':'desktop_provider_search_transport_failed','failed_at_utc':_now(clock),'provider_access':True,'automatic_retry':False};failure['failure_fingerprint']=_sha(failure)
  try:_write_create(failures/f"{trusted['request_ref']}.json",failure)
  except DesktopProviderSearchV1Error:pass
  _abort('desktop_provider_search_transport_failed')

__all__=['DesktopProviderSearchContextV1','DesktopProviderSearchV1Error','apply_desktop_provider_search_v1','desktop_provider_search_v1_error_codes','preview_desktop_provider_search_v1','public_desktop_provider_search_preview_v1']
