#!/usr/bin/env python3
"""Provider-free append-only Unrealized Valuation v1 reference boundary.

Die Summe ueber *alle* Positionen (market_value_decimal und die anderen) bleibt
leer, solange auch nur eine Position keinen Wert traegt - ein Portfoliowert, der
einen Teil des Bestands verschweigt, waere die schlechtere Antwort. Daneben steht
die ausgewiesene Teilsumme (valued_*) ueber die bewerteten Positionen, mit ihrer
Anzahl. Welche Position warum fehlt, sagt ihr failure_codes (#368, 28.09.2026).

Ein fortgeschriebener Kurs (price_status='stale_price') traegt einen Wert: Er ist
der beste erreichbare Schaetzer, und genau dafuer wird fortgeschrieben.  Die
Position wird 'partial' und fuehrt 'market_price_stale', damit sie niemand fuer
eine Stichtagsnotiz haelt (#368, 28.09.2026).  Ohne Kurs bleibt sie 'blocked'.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import tempfile
from typing import Any, Mapping, Sequence

from migrations.reference.daily_market_history_v1 import daily_market_history_context_fingerprint_v1
from migrations.reference.fx_history_v1 import fx_history_context_fingerprint_v1, validate_fx_conversion_artifact_v1
from migrations.reference.realized_materialization_v1 import fifo_context_fingerprint_v1
from migrations.reference.tax_model_plugin_v1 import context_fingerprint as tax_context_fingerprint_v1

ROOT=Path(__file__).resolve().parents[2]
SCHEMA=ROOT/'contracts'/'unrealized-valuation'/'v1'/'schema.sql'
STORE_VERSION=2700
ALGORITHM_VERSION='unrealized_valuation_v1.0.0'
ERROR_CODES=frozenset({
 'unrealized_valuation_artifact_exists','unrealized_valuation_artifact_invalid','unrealized_valuation_base_invalid',
 'unrealized_valuation_boundary_failed','unrealized_valuation_context_invalid','unrealized_valuation_context_mismatch',
 'unrealized_valuation_decimal_invalid','unrealized_valuation_evidence_exists','unrealized_valuation_evidence_invalid',
 'unrealized_valuation_fx_artifact_invalid','unrealized_valuation_input_invalid','unrealized_valuation_invalidation_conflict',
 'unrealized_valuation_job_invalid','unrealized_valuation_market_artifact_invalid','unrealized_valuation_request_conflict',
 'unrealized_valuation_snapshot_missing','unrealized_valuation_store_exists','unrealized_valuation_store_invalid',
 'unrealized_valuation_synthetic_failpoint','unrealized_valuation_tax_artifact_invalid','unrealized_valuation_write_failed',
})
FAILPOINTS=frozenset({'after_snapshot','after_first_result','before_commit'})
INVALIDATION_REASONS=frozenset({'fifo_correction','market_correction','tax_policy_revision','fx_correction','algorithm_upgrade'})
PRICE_STATUSES=frozenset({'completed','stale_price','missing_price','source_gap','corporate_action_review_required'})
POSITION_STATUSES=frozenset({'completed','partial','blocked'})
COMPONENT_CODES=frozenset({'market_value_basis','market_value','fifo_cost','unrealized_gross_gain','projected_tax','liquidation_fee','net_liquidation'})
ASSET_TYPES=frozenset({'equity','fund','etf','bond','crypto','commodity','derivative','fx','index','other'})
TAX_STATUSES=frozenset({'completed','negative_gain_no_tax','no_plugin','not_selected','classification_required','parameter_required','plugin_blocked','not_calculated'})
FX_STATUSES=frozenset({'completed','native','conversion_unavailable','not_calculated'})
POSITION_FAILURE_CODES=frozenset({'fifo_basis_unavailable','fifo_currency_unavailable','market_price_stale','market_price_missing','market_source_gap','market_corporate_action_review_required','market_basis_fx_unavailable','tax_projection_unavailable','display_fx_unavailable'})
_UTC=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$')
_DATE=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
_SHA=re.compile(r'^[a-f0-9]{64}$')
_REF=re.compile(r'^[a-z][a-z0-9]{2}_[a-f0-9]{24,32}$')
_CURRENCY=re.compile(r'^[A-Z]{3}$')
_DECIMAL=re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$')
_TOKEN=re.compile(r'^[a-z][a-z0-9_.-]{2,79}$')
REQUEST_FIELDS=frozenset({'contract_version','request_ref','portfolio_ref','as_of_date','target_currency','output_scale','algorithm_version','calculation_mode','base_snapshot_ref','context_binding_fingerprint','fifo_artifact','market_artifact','tax_artifact','fx_artifacts','fx_component_bindings','fee_assumptions','resolved_invalidation_refs','input_fingerprint','request_fingerprint'})
FIFO_POSITION_FIELDS=frozenset({'position_ref','account_ref','asset_ref','asset_type','basis_status','basis_currency','remaining_quantity_decimal','remaining_fifo_cost_decimal'})
MARKET_ROW_FIELDS=frozenset({'position_ref','asset_ref','listing_ref','market_currency','price_date','price_status','close_decimal','price_age_days','revision_ref','revision_fingerprint','observation_at_utc'})
TAX_ROW_FIELDS=frozenset({'position_ref','currency','unrealized_gross_gain_decimal','projected_unrealized_tax_decimal','projection_status','failure_code'})
FEE_FIELDS=frozenset({'position_ref','fixed_fee_decimal','percentage_rate_decimal','assumption_code'})
FX_BINDING_FIELDS=frozenset({'position_ref','component_code','conversion_item_ref'})
ARTIFACT_FIELDS=frozenset({'contract_version','snapshot_ref','status','portfolio_ref','as_of_date','target_currency','output_scale','algorithm_version','calculation_mode','base_snapshot_ref','context_binding_fingerprint','input_fingerprint','request_fingerprint','source_fingerprints','tax_plugin','items','account_summaries','summary','reconciliation','disclaimer_codes','boundaries','row_set_fingerprint','artifact_fingerprint'})
ITEM_FIELDS=frozenset({'position_ref','account_ref','asset_ref','asset_type','listing_ref','as_of_date','price_date','price_status','price_age_days','market_currency','basis_currency','target_currency','remaining_quantity_decimal','market_price_decimal','market_value_market_decimal','market_value_decimal','fifo_cost_decimal','unrealized_gross_gain_decimal','projected_tax_decimal','liquidation_fee_decimal','net_liquidation_decimal','display_market_value_decimal','display_fifo_cost_decimal','display_unrealized_gross_gain_decimal','display_projected_tax_decimal','display_liquidation_fee_decimal','display_net_liquidation_decimal','tax_status','fx_status','position_status','failure_codes','fee_assumption','market_revision_ref','market_revision_fingerprint','position_input_fingerprint','result_fingerprint'})

class UnrealizedValuationBlocked(ValueError):
 def __init__(self,code:str):
  if code not in ERROR_CODES:raise ValueError('unrealized_valuation_error_code_unregistered')
  super().__init__(code);self.code=code
@dataclass(frozen=True)
class ValuationContext:
 tenant_id:str;user_id:str;data_space_id:str;actor_id:str;role:str='portfolio_worker'

def abort(code):raise UnrealizedValuationBlocked(code)
def canonical(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':'))
def sha(value):
 payload=value if isinstance(value,bytes) else value.encode() if isinstance(value,str) else canonical(value).encode()
 return hashlib.sha256(payload).hexdigest()
def opaque(prefix,value):return f'{prefix}_{sha(value)[:32]}'
def normalize_context(value,writer=False):
 if isinstance(value,Mapping):
  try:value=ValuationContext(value['tenant_id'],value['user_id'],value['data_space_id'],value['actor_id'],value.get('role','portfolio_worker'))
  except (KeyError,TypeError) as e:raise UnrealizedValuationBlocked('unrealized_valuation_context_invalid') from e
 if not isinstance(value,ValuationContext):abort('unrealized_valuation_context_invalid')
 vals=(value.tenant_id,value.user_id,value.data_space_id,value.actor_id)
 if any(not isinstance(v,str) or not 3<=len(v)<=(80 if i==3 else 64) or re.fullmatch(r'[A-Za-z0-9_-]+',v) is None for i,v in enumerate(vals)) or not value.data_space_id.startswith('sbx_'):abort('unrealized_valuation_context_invalid')
 if value.role not in {'portfolio_worker','tax_worker','analysis_worker','viewer'} or writer and value.role!='portfolio_worker':abort('unrealized_valuation_context_invalid')
 return value
def context_fingerprint(value):
 c=normalize_context(value);return sha({'contract_version':'unrealized_valuation_context_v1','tenant_id':c.tenant_id,'user_id':c.user_id,'data_space_id':c.data_space_id})
def domain_context(value):
 c=normalize_context(value);return {'tenant_id':c.tenant_id,'user_id':c.user_id,'data_space_id':c.data_space_id,'actor_id':c.actor_id,'role':c.role}
def valid_ref(value,prefix=None,code='unrealized_valuation_input_invalid'):
 if not isinstance(value,str) or _REF.fullmatch(value) is None or prefix and not value.startswith(prefix):abort(code)
 return value
def valid_fp(value,code='unrealized_valuation_input_invalid'):
 if not isinstance(value,str) or _SHA.fullmatch(value) is None:abort(code)
 return value
def valid_currency(value,code='unrealized_valuation_input_invalid'):
 if not isinstance(value,str) or _CURRENCY.fullmatch(value) is None:abort(code)
 return value
def valid_date(value,code='unrealized_valuation_input_invalid'):
 if not isinstance(value,str) or _DATE.fullmatch(value) is None:abort(code)
 try:parsed=date.fromisoformat(value)
 except ValueError:abort(code)
 if parsed.isoformat()!=value:abort(code)
 return value
def valid_utc(value,code='unrealized_valuation_input_invalid'):
 if not isinstance(value,str) or _UTC.fullmatch(value) is None:abort(code)
 try:parsed=datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
 except ValueError:abort(code)
 if parsed.strftime('%Y-%m-%dT%H:%M:%SZ')!=value:abort(code)
 return value
def fraction_decimal(value,nonnegative=False,positive=False,code='unrealized_valuation_decimal_invalid'):
 if not isinstance(value,str) or len(value)>80 or _DECIMAL.fullmatch(value) is None or value=='-0':abort(code)
 sign=-1 if value.startswith('-') else 1;u=value[1:] if sign<0 else value
 if '.' in u:w,f=u.split('.',1);result=Fraction(sign*int(w+f),10**len(f))
 else:result=Fraction(sign*int(u),1)
 if nonnegative and result<0 or positive and result<=0:abort(code)
 return result
def round_fraction(value:Fraction,scale:int):
 factor=10**scale;n=abs(value.numerator)*factor;q,r=divmod(n,value.denominator);twice=r*2
 if twice>value.denominator or twice==value.denominator and q%2:q+=1
 sign='-' if value<0 and q else '';digits=str(q)
 if scale:
  digits=digits.rjust(scale+1,'0');text=sign+digits[:-scale]+'.'+digits[-scale:];text=text.rstrip('0').rstrip('.')
 else:text=sign+digits
 if len(text)>80:abort('unrealized_valuation_decimal_invalid')
 return text

def owner_directory(path):
 try:absolute=Path(os.path.abspath(path));resolved=Path(path).resolve(strict=True);meta=resolved.stat()
 except (OSError,ValueError,TypeError) as e:raise UnrealizedValuationBlocked('unrealized_valuation_store_invalid') from e
 wrong=hasattr(os,'geteuid') and meta.st_uid!=os.geteuid()
 if absolute!=resolved or not stat.S_ISDIR(meta.st_mode) or stat.S_IMODE(meta.st_mode)!=0o700 or wrong:abort('unrealized_valuation_store_invalid')
 return resolved
def regular_path(path,new=False,artifact=False):
 target=Path(path);exists='unrealized_valuation_artifact_exists' if artifact else 'unrealized_valuation_store_exists';invalid='unrealized_valuation_artifact_invalid' if artifact else 'unrealized_valuation_store_invalid'
 if new:
  if target.exists() or target.is_symlink():abort(exists)
  return owner_directory(target.parent)/target.name
 try:absolute=Path(os.path.abspath(target));resolved=target.resolve(strict=True);meta=resolved.stat()
 except (OSError,ValueError,TypeError) as e:raise UnrealizedValuationBlocked(invalid) from e
 wrong=hasattr(os,'geteuid') and meta.st_uid!=os.geteuid()
 if absolute!=resolved or target.is_symlink() or not stat.S_ISREG(meta.st_mode) or stat.S_IMODE(meta.st_mode)!=0o600 or wrong:abort(invalid)
 owner_directory(resolved.parent);return resolved
def connect(path,context,ro=False):
 c=normalize_context(context,writer=not ro)
 if ro and c.role not in {'portfolio_worker','tax_worker','analysis_worker'}:abort('unrealized_valuation_context_invalid')
 source=regular_path(path)
 try:
  con=sqlite3.connect(f'{source.as_uri()}?mode=ro',uri=True) if ro else sqlite3.connect(source,isolation_level=None)
  con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
  if ro:con.execute('PRAGMA query_only=ON')
  row=con.execute('SELECT context_binding_fingerprint FROM unrealized_valuation_store_binding WHERE singleton_id=1').fetchone()
  if con.execute('PRAGMA user_version').fetchone()[0]!=STORE_VERSION or row is None or row[0]!=context_fingerprint(c):con.close();abort('unrealized_valuation_context_mismatch')
  return con
 except UnrealizedValuationBlocked:raise
 except sqlite3.Error as e:raise UnrealizedValuationBlocked('unrealized_valuation_store_invalid') from e

def bootstrap_unrealized_valuation_store_v1(path,context,created_at_utc):
 c=normalize_context(context,writer=True);valid_utc(created_at_utc);target=regular_path(path,new=True);fd=None
 try:
  fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.fchmod(fd,0o600);os.close(fd);fd=None
  con=sqlite3.connect(target);con.executescript(SCHEMA.read_text());con.execute('INSERT INTO unrealized_valuation_store_binding VALUES (1,2700,?,?)',(context_fingerprint(c),created_at_utc));con.commit()
  if con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':abort('unrealized_valuation_store_invalid')
  con.close();os.chmod(target,0o600);return target
 except UnrealizedValuationBlocked:target.unlink(missing_ok=True);raise
 except Exception as e:
  if fd is not None:os.close(fd)
  target.unlink(missing_ok=True);raise UnrealizedValuationBlocked('unrealized_valuation_store_invalid') from e

def _seal(body):return {**body,'artifact_fingerprint':sha(body)}
def new_unrealized_fifo_artifact_v1(context,*,portfolio_ref,source_artifact_ref,cutoff_at_utc,positions):
 c=normalize_context(context);valid_ref(portfolio_ref,'pfr_');valid_ref(source_artifact_ref,'rar_');valid_utc(cutoff_at_utc)
 if not isinstance(positions,Sequence) or isinstance(positions,(str,bytes)) or not positions:abort('unrealized_valuation_input_invalid')
 normalized=[];seen=set()
 for raw in positions:
  if not isinstance(raw,Mapping) or set(raw)!=FIFO_POSITION_FIELDS:abort('unrealized_valuation_input_invalid')
  row=dict(raw);p=valid_ref(row['position_ref'],'psr_')
  if p in seen:abort('unrealized_valuation_input_invalid')
  seen.add(p);valid_ref(row['account_ref'],'acr_');valid_ref(row['asset_ref'],'asr_')
  if row['asset_type'] not in ASSET_TYPES or row['basis_status'] not in {'completed','missing_basis','missing_currency'}:abort('unrealized_valuation_input_invalid')
  fraction_decimal(row['remaining_quantity_decimal'],positive=True)
  if row['basis_status']=='completed':valid_currency(row['basis_currency']);fraction_decimal(row['remaining_fifo_cost_decimal'],nonnegative=True)
  elif row['basis_status']=='missing_basis':
   valid_currency(row['basis_currency'])
   if row['remaining_fifo_cost_decimal'] is not None:abort('unrealized_valuation_input_invalid')
  elif row['basis_currency'] is not None or row['remaining_fifo_cost_decimal'] is not None:abort('unrealized_valuation_input_invalid')
  normalized.append(row)
 normalized.sort(key=lambda x:x['position_ref'])
 body={'contract_version':'unrealized_fifo_open_positions_v1','status':'completed','portfolio_ref':portfolio_ref,'source_artifact_ref':source_artifact_ref,'source_context_fingerprint':fifo_context_fingerprint_v1(domain_context(c)),'cutoff_at_utc':cutoff_at_utc,'positions':normalized}
 return _seal(body)
def new_unrealized_market_artifact_v1(context,*,portfolio_ref,as_of_date,prices):
 c=normalize_context(context);valid_ref(portfolio_ref,'pfr_');valid_date(as_of_date)
 if not isinstance(prices,Sequence) or isinstance(prices,(str,bytes)) or not prices:abort('unrealized_valuation_market_artifact_invalid')
 rows=[];seen=set()
 for raw in prices:
  if not isinstance(raw,Mapping) or set(raw)!=MARKET_ROW_FIELDS:abort('unrealized_valuation_market_artifact_invalid')
  row=dict(raw);p=valid_ref(row['position_ref'],'psr_','unrealized_valuation_market_artifact_invalid')
  if p in seen:abort('unrealized_valuation_market_artifact_invalid')
  seen.add(p);valid_ref(row['asset_ref'],'asr_','unrealized_valuation_market_artifact_invalid');valid_ref(row['listing_ref'],'lsr_','unrealized_valuation_market_artifact_invalid');valid_currency(row['market_currency'],'unrealized_valuation_market_artifact_invalid');valid_date(row['price_date'],'unrealized_valuation_market_artifact_invalid')
  expected_age=(date.fromisoformat(as_of_date)-date.fromisoformat(row['price_date'])).days
  if expected_age<0:abort('unrealized_valuation_market_artifact_invalid')
  if row['price_status'] not in PRICE_STATUSES:abort('unrealized_valuation_market_artifact_invalid')
  if row['price_status']=='completed':
   fraction_decimal(row['close_decimal'],positive=True,code='unrealized_valuation_market_artifact_invalid');valid_ref(row['revision_ref'],'mrv_','unrealized_valuation_market_artifact_invalid');valid_fp(row['revision_fingerprint'],'unrealized_valuation_market_artifact_invalid');valid_utc(row['observation_at_utc'],'unrealized_valuation_market_artifact_invalid')
   if isinstance(row['price_age_days'],bool) or row['price_age_days']!=expected_age:abort('unrealized_valuation_market_artifact_invalid')
  else:
   if row['close_decimal'] is not None and row['price_status']!='stale_price':abort('unrealized_valuation_market_artifact_invalid')
   if row['price_status']=='stale_price':
    fraction_decimal(row['close_decimal'],positive=True,code='unrealized_valuation_market_artifact_invalid');valid_ref(row['revision_ref'],'mrv_','unrealized_valuation_market_artifact_invalid');valid_fp(row['revision_fingerprint'],'unrealized_valuation_market_artifact_invalid');valid_utc(row['observation_at_utc'],'unrealized_valuation_market_artifact_invalid')
    if isinstance(row['price_age_days'],bool) or row['price_age_days']!=expected_age:abort('unrealized_valuation_market_artifact_invalid')
   elif any(row[key] is not None for key in ('price_age_days','revision_ref','revision_fingerprint','observation_at_utc')):abort('unrealized_valuation_market_artifact_invalid')
  rows.append(row)
 rows.sort(key=lambda x:x['position_ref']);status='completed' if all(x['price_status']=='completed' for x in rows) else 'partial'
 body={'contract_version':'unrealized_market_input_v1','status':status,'portfolio_ref':portfolio_ref,'source_context_fingerprint':daily_market_history_context_fingerprint_v1(domain_context(c)),'as_of_date':as_of_date,'prices':rows}
 return _seal(body)
def new_unrealized_tax_artifact_v1(context,*,portfolio_ref,as_of_date,completed_at_utc,status,plugin_id=None,plugin_version=None,rules_fingerprint=None,manifest_fingerprint=None,selection_ref=None,plugin_input_fingerprint=None,plugin_output_fingerprint=None,rows=(),failure_code=None,disclaimer_codes=('model_projection_not_legal_advice',)):
 c=normalize_context(context);valid_ref(portfolio_ref,'pfr_','unrealized_valuation_tax_artifact_invalid');valid_date(as_of_date,'unrealized_valuation_tax_artifact_invalid');valid_utc(completed_at_utc,'unrealized_valuation_tax_artifact_invalid')
# Gewaehlter Umfang ist kein Mangel (#564, rc.406): 'not_selected' = bewusst ohne Steuermodul gerechnet (Run Center "Nicht auswaehlen",
# Umfang ohne Steuerbericht). Anders als 'unavailable' (Modul oder Einordnung fehlt) ist das keine Luecke: Positionen bleiben abgeschlossen,
# Steuer und Nettowert leer - nie 0.
 if status not in {'completed','unavailable','not_selected'}:abort('unrealized_valuation_tax_artifact_invalid')
 normalized=[]
 if status=='completed':
  if not all(isinstance(x,str) and x for x in (plugin_id,plugin_version)) or not _TOKEN.fullmatch(plugin_id) or not isinstance(plugin_version,str):abort('unrealized_valuation_tax_artifact_invalid')
  for fp in (rules_fingerprint,manifest_fingerprint,plugin_input_fingerprint,plugin_output_fingerprint):valid_fp(fp,'unrealized_valuation_tax_artifact_invalid')
  valid_ref(selection_ref,'tsr_','unrealized_valuation_tax_artifact_invalid')
  if failure_code is not None:abort('unrealized_valuation_tax_artifact_invalid')
  seen=set()
  for raw in rows:
   if not isinstance(raw,Mapping):abort('unrealized_valuation_tax_artifact_invalid')
   try:row={key:raw[key] for key in TAX_ROW_FIELDS}
   except KeyError:abort('unrealized_valuation_tax_artifact_invalid')
   p=valid_ref(row['position_ref'],'psr_','unrealized_valuation_tax_artifact_invalid')
   if p in seen:abort('unrealized_valuation_tax_artifact_invalid')
   seen.add(p);valid_currency(row['currency'],'unrealized_valuation_tax_artifact_invalid');fraction_decimal(row['unrealized_gross_gain_decimal'],code='unrealized_valuation_tax_artifact_invalid')
   if row['projection_status'] not in {'completed','blocked'}:abort('unrealized_valuation_tax_artifact_invalid')
   if row['projection_status']=='completed':
    fraction_decimal(row['projected_unrealized_tax_decimal'],nonnegative=True,code='unrealized_valuation_tax_artifact_invalid')
    if row['failure_code'] is not None:abort('unrealized_valuation_tax_artifact_invalid')
   elif row['projected_unrealized_tax_decimal'] is not None or not isinstance(row['failure_code'],str):abort('unrealized_valuation_tax_artifact_invalid')
   normalized.append(row)
  normalized.sort(key=lambda x:x['position_ref'])
 else:
  if any(x is not None for x in (plugin_id,plugin_version,rules_fingerprint,manifest_fingerprint,selection_ref,plugin_input_fingerprint,plugin_output_fingerprint)) or rows or (failure_code is not None if status=='not_selected' else not isinstance(failure_code,str)):abort('unrealized_valuation_tax_artifact_invalid')
 if not isinstance(disclaimer_codes,(list,tuple)) or 'model_projection_not_legal_advice' not in disclaimer_codes:abort('unrealized_valuation_tax_artifact_invalid')
 body={'contract_version':'unrealized_tax_projection_v1','status':status,'portfolio_ref':portfolio_ref,'as_of_date':as_of_date,'completed_at_utc':completed_at_utc,'projection_mode':'unrealized_snapshot','source_context_fingerprint':tax_context_fingerprint_v1(domain_context(c)),'plugin_id':plugin_id,'plugin_version':plugin_version,'rules_fingerprint':rules_fingerprint,'manifest_fingerprint':manifest_fingerprint,'selection_ref':selection_ref,'plugin_input_fingerprint':plugin_input_fingerprint,'plugin_output_fingerprint':plugin_output_fingerprint,'rows':normalized,'failure_code':failure_code,'disclaimer_codes':list(disclaimer_codes)}
 return _seal(body)

def _validate_sealed(value,contract,expected_fields,code):
 if not isinstance(value,dict) or set(value)!=expected_fields or value.get('contract_version')!=contract:abort(code)
 fp=value.get('artifact_fingerprint');valid_fp(fp,code);body=dict(value);body.pop('artifact_fingerprint')
 if sha(body)!=fp:abort(code)
 return value
def validate_fifo(value,context,portfolio):
 value=_validate_sealed(dict(value),'unrealized_fifo_open_positions_v1',{'contract_version','status','portfolio_ref','source_artifact_ref','source_context_fingerprint','cutoff_at_utc','positions','artifact_fingerprint'},'unrealized_valuation_input_invalid')
 if value.get('status')!='completed' or value.get('portfolio_ref')!=portfolio or value.get('source_context_fingerprint')!=fifo_context_fingerprint_v1(domain_context(context)):abort('unrealized_valuation_context_mismatch')
 rebuilt=new_unrealized_fifo_artifact_v1(context,portfolio_ref=portfolio,source_artifact_ref=value['source_artifact_ref'],cutoff_at_utc=value['cutoff_at_utc'],positions=value['positions'])
 if rebuilt!=value:abort('unrealized_valuation_input_invalid')
 return value
def validate_market(value,context,portfolio,as_of):
 value=_validate_sealed(dict(value),'unrealized_market_input_v1',{'contract_version','status','portfolio_ref','source_context_fingerprint','as_of_date','prices','artifact_fingerprint'},'unrealized_valuation_market_artifact_invalid')
 if value.get('portfolio_ref')!=portfolio or value.get('as_of_date')!=as_of or value.get('source_context_fingerprint')!=daily_market_history_context_fingerprint_v1(domain_context(context)):abort('unrealized_valuation_context_mismatch')
 rebuilt=new_unrealized_market_artifact_v1(context,portfolio_ref=portfolio,as_of_date=as_of,prices=value['prices'])
 if rebuilt!=value:abort('unrealized_valuation_market_artifact_invalid')
 return value
def validate_tax(value,context,portfolio,as_of_date):
 value=_validate_sealed(dict(value),'unrealized_tax_projection_v1',{'contract_version','status','portfolio_ref','as_of_date','completed_at_utc','projection_mode','source_context_fingerprint','plugin_id','plugin_version','rules_fingerprint','manifest_fingerprint','selection_ref','plugin_input_fingerprint','plugin_output_fingerprint','rows','failure_code','disclaimer_codes','artifact_fingerprint'},'unrealized_valuation_tax_artifact_invalid')
 if value.get('portfolio_ref')!=portfolio or value.get('as_of_date')!=as_of_date or value.get('source_context_fingerprint')!=tax_context_fingerprint_v1(domain_context(context)):abort('unrealized_valuation_context_mismatch')
 kwargs={k:value[k] for k in ('status','plugin_id','plugin_version','rules_fingerprint','manifest_fingerprint','selection_ref','plugin_input_fingerprint','plugin_output_fingerprint','rows','failure_code','disclaimer_codes')}
 rebuilt=new_unrealized_tax_artifact_v1(context,portfolio_ref=portfolio,as_of_date=as_of_date,completed_at_utc=value['completed_at_utc'],**kwargs)
 if rebuilt!=value:abort('unrealized_valuation_tax_artifact_invalid')
 return value

def new_unrealized_valuation_request_v1(context,*,request_ref,portfolio_ref,as_of_date,target_currency,output_scale,fifo_artifact,market_artifact,tax_artifact,fx_artifacts,fx_component_bindings,fee_assumptions,calculation_mode='full',base_snapshot_ref=None,resolved_invalidation_refs=()):
 c=normalize_context(context,writer=True);valid_ref(request_ref,'req_');valid_ref(portfolio_ref,'pfr_');valid_date(as_of_date);valid_currency(target_currency)
 if isinstance(output_scale,bool) or not isinstance(output_scale,int) or not 0<=output_scale<=18:abort('unrealized_valuation_input_invalid')
 if calculation_mode not in {'full','incremental'} or calculation_mode=='full' and base_snapshot_ref is not None or calculation_mode=='incremental' and (base_snapshot_ref is None or valid_ref(base_snapshot_ref,'uva_') is None):abort('unrealized_valuation_base_invalid')
 fifo=validate_fifo(fifo_artifact,c,portfolio_ref);market=validate_market(market_artifact,c,portfolio_ref,as_of_date);tax=validate_tax(tax_artifact,c,portfolio_ref,as_of_date)
 if not isinstance(fx_artifacts,Sequence) or isinstance(fx_artifacts,(str,bytes)):abort('unrealized_valuation_fx_artifact_invalid')
 fxs=[];all_fx_item_refs=set()
 for raw in fx_artifacts:
  try:fx=validate_fx_conversion_artifact_v1(raw,domain_context(c))
  except Exception as e:raise UnrealizedValuationBlocked('unrealized_valuation_fx_artifact_invalid') from e
  refs={item['conversion_item_ref'] for item in fx['items']}
  if all_fx_item_refs & refs:abort('unrealized_valuation_fx_artifact_invalid')
  all_fx_item_refs.update(refs);fxs.append(fx)
 fxs.sort(key=lambda value:value['artifact_fingerprint'])
 fees=[];seen=set()
 for raw in fee_assumptions:
  if not isinstance(raw,Mapping) or set(raw)!=FEE_FIELDS:abort('unrealized_valuation_input_invalid')
  row=dict(raw);p=valid_ref(row['position_ref'],'psr_')
  if p in seen:abort('unrealized_valuation_input_invalid')
  seen.add(p);fraction_decimal(row['fixed_fee_decimal'],nonnegative=True);fraction_decimal(row['percentage_rate_decimal'],nonnegative=True)
  if not isinstance(row['assumption_code'],str) or _TOKEN.fullmatch(row['assumption_code']) is None:abort('unrealized_valuation_input_invalid')
  fees.append(row)
 positions={x['position_ref'] for x in fifo['positions']}
 if seen!=positions:abort('unrealized_valuation_input_invalid')
 bindings=[];keys=set();item_refs=set()
 for raw in fx_component_bindings:
  if not isinstance(raw,Mapping) or set(raw)!=FX_BINDING_FIELDS:abort('unrealized_valuation_fx_artifact_invalid')
  row=dict(raw);valid_ref(row['position_ref'],'psr_','unrealized_valuation_fx_artifact_invalid');valid_ref(row['conversion_item_ref'],'fci_','unrealized_valuation_fx_artifact_invalid')
  if row['position_ref'] not in positions or row['component_code'] not in COMPONENT_CODES or (row['position_ref'],row['component_code']) in keys or row['conversion_item_ref'] in item_refs:abort('unrealized_valuation_fx_artifact_invalid')
  keys.add((row['position_ref'],row['component_code']));item_refs.add(row['conversion_item_ref']);bindings.append(row)
 if bindings and not fxs:abort('unrealized_valuation_fx_artifact_invalid')
 if item_refs!=all_fx_item_refs:abort('unrealized_valuation_fx_artifact_invalid')
 invalidations=[]
 for value in resolved_invalidation_refs:
  invalidations.append(valid_ref(value,'uvn_'))
 if len(invalidations)!=len(set(invalidations)):abort('unrealized_valuation_input_invalid')
 fees.sort(key=lambda x:x['position_ref']);bindings.sort(key=lambda x:(x['position_ref'],x['component_code']));invalidations.sort()
 source={'fifo':fifo['artifact_fingerprint'],'market':market['artifact_fingerprint'],'tax':tax['artifact_fingerprint'],'fx':[value['artifact_fingerprint'] for value in fxs]}
 input_fp=sha({'portfolio_ref':portfolio_ref,'as_of_date':as_of_date,'target_currency':target_currency,'output_scale':output_scale,'sources':source,'fees':fees,'bindings':bindings})
 body={'contract_version':'unrealized_valuation_request_v1','request_ref':request_ref,'portfolio_ref':portfolio_ref,'as_of_date':as_of_date,'target_currency':target_currency,'output_scale':output_scale,'algorithm_version':ALGORITHM_VERSION,'calculation_mode':calculation_mode,'base_snapshot_ref':base_snapshot_ref,'context_binding_fingerprint':context_fingerprint(c),'fifo_artifact':fifo,'market_artifact':market,'tax_artifact':tax,'fx_artifacts':fxs,'fx_component_bindings':bindings,'fee_assumptions':fees,'resolved_invalidation_refs':invalidations,'input_fingerprint':input_fp}
 return {**body,'request_fingerprint':sha(body)}
def validate_request(value,context):
 if not isinstance(value,dict) or set(value)!=REQUEST_FIELDS or value.get('contract_version')!='unrealized_valuation_request_v1' or value.get('algorithm_version')!=ALGORITHM_VERSION:abort('unrealized_valuation_input_invalid')
 rebuilt=new_unrealized_valuation_request_v1(context,**{k:value[k] for k in ('request_ref','portfolio_ref','as_of_date','target_currency','output_scale','fifo_artifact','market_artifact','tax_artifact','fx_artifacts','fx_component_bindings','fee_assumptions','calculation_mode','base_snapshot_ref','resolved_invalidation_refs')})
 if rebuilt!=value:abort('unrealized_valuation_input_invalid')
 return value

def _tax_status(failure):
 if failure is None:return 'plugin_blocked'
 text=str(failure)
 if 'classification' in text:return 'classification_required'
 if 'parameter' in text or 'rate' in text:return 'parameter_required'
 if 'plugin' in text:return 'plugin_blocked'
 return 'plugin_blocked'
def _sum_display(items,field,scale):
 values=[x[field] for x in items]
 if any(x is None for x in values):return None
 return round_fraction(sum((fraction_decimal(x) for x in values),Fraction(0)),scale)
def _sum_valued(items,field,scale):
 values=[x[field] for x in items if x[field] is not None]
 if not values:return None
 return round_fraction(sum((fraction_decimal(x) for x in values),Fraction(0)),scale)
def _component_summary(items,scale,target_currency):
 statuses=[row['position_status'] for row in items]
 snapshot_status='completed' if all(value=='completed' for value in statuses) else 'blocked' if all(value=='blocked' for value in statuses) else 'partial'
 result={'target_currency':target_currency,'aggregation_status':'completed' if snapshot_status=='completed' else 'unavailable' if snapshot_status=='blocked' else 'partial','position_count':len(items),'completed_position_count':statuses.count('completed'),'partial_position_count':statuses.count('partial'),'blocked_position_count':statuses.count('blocked'),'market_value_decimal':_sum_display(items,'display_market_value_decimal',scale),'fifo_cost_decimal':_sum_display(items,'display_fifo_cost_decimal',scale),'unrealized_gross_gain_decimal':_sum_display(items,'display_unrealized_gross_gain_decimal',scale),'projected_tax_decimal':_sum_display(items,'display_projected_tax_decimal',scale),'liquidation_fee_decimal':_sum_display(items,'display_liquidation_fee_decimal',scale),'net_liquidation_decimal':_sum_display(items,'display_net_liquidation_decimal',scale)}
 valued=[row for row in items if row['display_market_value_decimal'] is not None]
 result.update({'valued_position_count':len(valued),
  'valued_market_value_decimal':_sum_valued(valued,'display_market_value_decimal',scale),
  'valued_fifo_cost_decimal':_sum_valued(valued,'display_fifo_cost_decimal',scale),
  'valued_unrealized_gross_gain_decimal':_sum_valued(valued,'display_unrealized_gross_gain_decimal',scale),
  'valued_liquidation_fee_decimal':_sum_valued(valued,'display_liquidation_fee_decimal',scale),
  'valued_projected_tax_decimal':_sum_valued(valued,'display_projected_tax_decimal',scale),
  'valued_net_liquidation_decimal':_sum_valued(valued,'display_net_liquidation_decimal',scale)})
 if all(value is None for key,value in result.items() if key.endswith('_decimal')):result['aggregation_status']='unavailable'
 return result

def _fx_component(position_ref,component,value,currency,target,as_of,bindings,fx_items):
 if value is None:return None,'not_calculated',False
 if currency==target:return value,'native',False
 binding=bindings.get((position_ref,component))
 if binding is None:return None,'conversion_unavailable',False
 row=fx_items[binding]
 if row['native_amount_decimal']!=value or row['native_currency']!=currency or row['target_currency']!=target or row['effective_date']!=as_of:abort('unrealized_valuation_fx_artifact_invalid')
 if row['conversion_status'] not in {'completed','native'} or row['converted_amount_decimal'] is None:return None,'conversion_unavailable',True
 return row['converted_amount_decimal'],'completed',True

def materialize_unrealized_valuation_v1(context,request,previous_artifact=None):
 c=normalize_context(context,writer=True);request=validate_request(dict(request),c)
 if request['calculation_mode']=='incremental':
  if previous_artifact is None:abort('unrealized_valuation_base_invalid')
  previous=validate_unrealized_valuation_artifact_v1(previous_artifact,c)
  if previous['snapshot_ref']!=request['base_snapshot_ref'] or previous['portfolio_ref']!=request['portfolio_ref']:abort('unrealized_valuation_base_invalid')
  previous_rows={x['position_ref']:x for x in previous['items']}
 else:
  if previous_artifact is not None:abort('unrealized_valuation_base_invalid')
  previous_rows={}
 market={x['position_ref']:x for x in request['market_artifact']['prices']};tax_rows={x['position_ref']:x for x in request['tax_artifact']['rows']};fees={x['position_ref']:x for x in request['fee_assumptions']};bindings={(x['position_ref'],x['component_code']):x['conversion_item_ref'] for x in request['fx_component_bindings']};fx_items={item['conversion_item_ref']:item for artifact in request['fx_artifacts'] for item in artifact['items']}
 output=[];reused=0;scale=request['output_scale']
 for fifo in request['fifo_artifact']['positions']:
  p=fifo['position_ref'];price=market.get(p)
  if price is None or price['asset_ref']!=fifo['asset_ref']:abort('unrealized_valuation_market_artifact_invalid')
  fee=fees[p];tax_row=tax_rows.get(p);relevant_bindings={k[1]:fx_items[v]['result_fingerprint'] for k,v in bindings.items() if k[0]==p}
  position_input_fp=sha({'fifo':fifo,'market':price,'tax':tax_row,'tax_plugin':{key:request['tax_artifact'][key] for key in ('status','plugin_id','plugin_version','rules_fingerprint','manifest_fingerprint','selection_ref')},'fee':fee,'fx':relevant_bindings})
  failures=[];basis=fifo['basis_currency'];market_currency=price['market_currency'];target=request['target_currency'];quantity=fraction_decimal(fifo['remaining_quantity_decimal'],positive=True);cost=None if fifo['remaining_fifo_cost_decimal'] is None else round_fraction(fraction_decimal(fifo['remaining_fifo_cost_decimal'],nonnegative=True),scale)
  common={'position_ref':p,'account_ref':fifo['account_ref'],'asset_ref':fifo['asset_ref'],'asset_type':fifo['asset_type'],'listing_ref':price['listing_ref'],'as_of_date':request['as_of_date'],'price_date':price['price_date'],'price_status':price['price_status'],'price_age_days':price['price_age_days'],'market_currency':market_currency,'basis_currency':basis,'target_currency':target,'remaining_quantity_decimal':fifo['remaining_quantity_decimal'],'fifo_cost_decimal':cost,'fee_assumption':fee,'market_revision_ref':price['revision_ref'],'market_revision_fingerprint':price['revision_fingerprint'],'position_input_fingerprint':position_input_fp}
  if fifo['basis_status']!='completed':
   failures.append('fifo_basis_unavailable' if fifo['basis_status']=='missing_basis' else 'fifo_currency_unavailable')
   if price['price_status']!='completed':failures.append({'stale_price':'market_price_stale','missing_price':'market_price_missing','source_gap':'market_source_gap','corporate_action_review_required':'market_corporate_action_review_required'}[price['price_status']])
   market_market=None if price['price_status']!='completed' else round_fraction(quantity*fraction_decimal(price['close_decimal'],positive=True),scale)
   row={**common,'market_price_decimal':price['close_decimal'],'market_value_market_decimal':market_market,'market_value_decimal':None,'unrealized_gross_gain_decimal':None,'projected_tax_decimal':None,'liquidation_fee_decimal':None,'net_liquidation_decimal':None,'display_market_value_decimal':None,'display_fifo_cost_decimal':None,'display_unrealized_gross_gain_decimal':None,'display_projected_tax_decimal':None,'display_liquidation_fee_decimal':None,'display_net_liquidation_decimal':None,'tax_status':'not_calculated','fx_status':'not_calculated','position_status':'blocked','failure_codes':failures}
  elif price['price_status'] not in ('completed','stale_price'):
   failures.append({'missing_price':'market_price_missing','source_gap':'market_source_gap','corporate_action_review_required':'market_corporate_action_review_required'}[price['price_status']])
   row={**common,'market_price_decimal':price['close_decimal'],'market_value_market_decimal':None,'market_value_decimal':None,'unrealized_gross_gain_decimal':None,'projected_tax_decimal':None,'liquidation_fee_decimal':None,'net_liquidation_decimal':None,'display_market_value_decimal':None,'display_fifo_cost_decimal':None,'display_unrealized_gross_gain_decimal':None,'display_projected_tax_decimal':None,'display_liquidation_fee_decimal':None,'display_net_liquidation_decimal':None,'tax_status':'not_calculated','fx_status':'not_calculated','position_status':'blocked','failure_codes':failures}
  else:
   if price['price_status']=='stale_price':failures.append('market_price_stale')
   close=fraction_decimal(price['close_decimal'],positive=True);market_market=round_fraction(quantity*close,scale);used_fx=False
   if market_currency==basis:market_value=market_market
   else:
    market_value,fxstate,used=_fx_component(p,'market_value_basis',market_market,market_currency,basis,request['as_of_date'],bindings,fx_items);used_fx|=used
    if market_value is None:
     failures.append('market_basis_fx_unavailable');row={**common,'market_price_decimal':price['close_decimal'],'market_value_market_decimal':market_market,'market_value_decimal':None,'unrealized_gross_gain_decimal':None,'projected_tax_decimal':None,'liquidation_fee_decimal':None,'net_liquidation_decimal':None,'display_market_value_decimal':None,'display_fifo_cost_decimal':None,'display_unrealized_gross_gain_decimal':None,'display_projected_tax_decimal':None,'display_liquidation_fee_decimal':None,'display_net_liquidation_decimal':None,'tax_status':'not_calculated','fx_status':'conversion_unavailable','position_status':'blocked','failure_codes':failures}
   if 'row' not in locals() or row.get('position_ref')!=p:
    market_rat=fraction_decimal(market_value);cost_rat=fraction_decimal(cost);gain=round_fraction(market_rat-cost_rat,scale);gain_rat=fraction_decimal(gain);fixed=fraction_decimal(fee['fixed_fee_decimal'],nonnegative=True);rate=fraction_decimal(fee['percentage_rate_decimal'],nonnegative=True);fee_value=round_fraction(fixed+market_rat*rate/Fraction(100),scale)
    if request['tax_artifact']['status']=='not_selected':
     # Ohne gewaehlte Steuer (#564, rc.406) auch keine "0" fuer Verlustpositionen: Ohne Modul ist nicht gesagt, dass keine Steuer
     # anfaellt (privates Veraeusserungsgut, Loesung (a) unten). Brutto wird nicht als Netto behauptet (Festlegung 13.11.2026).
     tax_value=None;tax_status='not_selected'
    elif gain_rat<=0:
     # Loesung (a), Festlegung 21.10.2026: Eine Position kann insgesamt im Verlust stehen und doch steuerpflichtigen Gewinn
     # tragen - bei privatem Veraeusserungsgut, wenn die Lose in der Jahresfrist im Plus und die steuerfreien Lose ausserhalb
     # im Minus sind. Dann gilt die Steuer des Moduls; ohne sie bleibt es bei 0. Bis rc.294 musste die Steuer hier 0 sein,
     # und der Abschluss blockierte, sobald das Modul fuer eine solche Position Steuer lieferte.
     taxed=None
     if request['tax_artifact']['status']=='completed':
      if tax_row is None or tax_row['currency']!=basis or fraction_decimal(tax_row['unrealized_gross_gain_decimal'])!=gain_rat or tax_row['projection_status']!='completed':abort('unrealized_valuation_tax_artifact_invalid')
      taxed=fraction_decimal(tax_row['projected_unrealized_tax_decimal'],nonnegative=True)
     if taxed:tax_value=round_fraction(taxed,scale);tax_status='completed'
     else:tax_value='0';tax_status='negative_gain_no_tax'
    elif request['tax_artifact']['status']=='unavailable':tax_value=None;tax_status='no_plugin';failures.append('tax_projection_unavailable')
    elif tax_row is None:tax_value=None;tax_status='plugin_blocked';failures.append('tax_projection_unavailable')
    else:
     if tax_row['currency']!=basis or fraction_decimal(tax_row['unrealized_gross_gain_decimal'])!=gain_rat:abort('unrealized_valuation_tax_artifact_invalid')
     if tax_row['projection_status']=='completed':tax_value=round_fraction(fraction_decimal(tax_row['projected_unrealized_tax_decimal'],nonnegative=True),scale);tax_status='completed'
     else:tax_value=None;tax_status=_tax_status(tax_row['failure_code']);failures.append('tax_projection_unavailable')
    net=None if tax_value is None else round_fraction(market_rat-fraction_decimal(fee_value)-fraction_decimal(tax_value),scale)
    native={'market_value':market_value,'fifo_cost':cost,'unrealized_gross_gain':gain,'projected_tax':tax_value,'liquidation_fee':fee_value,'net_liquidation':net};display={};fx_states=[]
    for component,value in native.items():
     converted,state,used=_fx_component(p,component,value,basis,target,request['as_of_date'],bindings,fx_items);display[component]=converted;fx_states.append(state);used_fx|=used
    if any(state=='conversion_unavailable' for state in fx_states):failures.append('display_fx_unavailable');fx_status='conversion_unavailable'
    elif used_fx:fx_status='completed'
    else:fx_status='native'
    untaxed=tax_status=='not_selected'
    status='completed' if (tax_value is not None or untaxed) and all(v is not None for k,v in display.items() if not (untaxed and k in ('projected_tax','net_liquidation'))) and price['price_status']=='completed' else 'partial'
    row={**common,'market_price_decimal':price['close_decimal'],'market_value_market_decimal':market_market,'market_value_decimal':market_value,'unrealized_gross_gain_decimal':gain,'projected_tax_decimal':tax_value,'liquidation_fee_decimal':fee_value,'net_liquidation_decimal':net,'display_market_value_decimal':display['market_value'],'display_fifo_cost_decimal':display['fifo_cost'],'display_unrealized_gross_gain_decimal':display['unrealized_gross_gain'],'display_projected_tax_decimal':display['projected_tax'],'display_liquidation_fee_decimal':display['liquidation_fee'],'display_net_liquidation_decimal':display['net_liquidation'],'tax_status':tax_status,'fx_status':fx_status,'position_status':status,'failure_codes':sorted(set(failures))}
  result_body=dict(row);result_body['failure_codes']=sorted(set(result_body['failure_codes']));row={**result_body,'result_fingerprint':sha(result_body)}
  prior=previous_rows.get(p)
  if prior is not None and prior['position_input_fingerprint']==row['position_input_fingerprint'] and prior['result_fingerprint']==row['result_fingerprint']:row=prior;reused+=1
  output.append(row)
  if 'row' in locals():del row
 statuses=[x['position_status'] for x in output];snapshot_status='completed' if all(x=='completed' for x in statuses) else 'blocked' if all(x=='blocked' for x in statuses) else 'partial'
 summary=_component_summary(output,scale,request['target_currency']);account_summaries=[]
 for account_ref in sorted({row['account_ref'] for row in output}):
  account_body={'account_ref':account_ref,**_component_summary([row for row in output if row['account_ref']==account_ref],scale,request['target_currency'])};account_summaries.append({**account_body,'account_fingerprint':sha(account_body)})
 source={'fifo_artifact_fingerprint':request['fifo_artifact']['artifact_fingerprint'],'market_artifact_fingerprint':request['market_artifact']['artifact_fingerprint'],'tax_artifact_fingerprint':request['tax_artifact']['artifact_fingerprint'],'fx_artifact_fingerprints':[value['artifact_fingerprint'] for value in request['fx_artifacts']]}
 tax_plugin={key:request['tax_artifact'][key] for key in ('status','plugin_id','plugin_version','rules_fingerprint','manifest_fingerprint','selection_ref','disclaimer_codes')}
 snapshot_ref=opaque('uva',[request['request_ref'],request['request_fingerprint']]);body={'contract_version':'unrealized_valuation_artifact_v1','snapshot_ref':snapshot_ref,'status':snapshot_status,'portfolio_ref':request['portfolio_ref'],'as_of_date':request['as_of_date'],'target_currency':request['target_currency'],'output_scale':scale,'algorithm_version':ALGORITHM_VERSION,'calculation_mode':request['calculation_mode'],'base_snapshot_ref':request['base_snapshot_ref'],'context_binding_fingerprint':context_fingerprint(c),'input_fingerprint':request['input_fingerprint'],'request_fingerprint':request['request_fingerprint'],'source_fingerprints':source,'tax_plugin':tax_plugin,'items':output,'account_summaries':account_summaries,'summary':summary,'reconciliation':{'item_count':len(output),'reused_item_count':reused,'calculation_mode':request['calculation_mode'],'full_incremental_row_parity':True,'resolved_invalidation_refs':request['resolved_invalidation_refs']},'disclaimer_codes':['model_projection_not_legal_advice','unrealized_projection_not_advice_or_liquidation_quote'],'boundaries':{'provider_access':False,'network_access':False,'automatic_fx':False,'tax_rules_in_core':False,'display_calculation':False,'canonical_write':False,'legacy_runtime':False},'row_set_fingerprint':sha(output)}
 return {**body,'artifact_fingerprint':sha(body)}

def validate_unrealized_valuation_artifact_v1(value,context):
 c=normalize_context(context);value=dict(value)
 try:
  if set(value)!=ARTIFACT_FIELDS or value['contract_version']!='unrealized_valuation_artifact_v1' or value['algorithm_version']!=ALGORITHM_VERSION or value['status'] not in {'completed','partial','blocked'}:abort('unrealized_valuation_artifact_invalid')
  if value['context_binding_fingerprint']!=context_fingerprint(c):abort('unrealized_valuation_context_mismatch')
  for key in ('input_fingerprint','request_fingerprint','row_set_fingerprint','artifact_fingerprint'):valid_fp(value[key],'unrealized_valuation_artifact_invalid')
  valid_ref(value['snapshot_ref'],'uva_','unrealized_valuation_artifact_invalid');valid_ref(value['portfolio_ref'],'pfr_','unrealized_valuation_artifact_invalid');valid_date(value['as_of_date'],'unrealized_valuation_artifact_invalid');valid_currency(value['target_currency'],'unrealized_valuation_artifact_invalid')
  if isinstance(value['output_scale'],bool) or not isinstance(value['output_scale'],int) or not 0<=value['output_scale']<=18:abort('unrealized_valuation_artifact_invalid')
  if value['calculation_mode'] not in {'full','incremental'} or value['calculation_mode']=='full' and value['base_snapshot_ref'] is not None or value['calculation_mode']=='incremental' and valid_ref(value['base_snapshot_ref'],'uva_','unrealized_valuation_artifact_invalid') is None:abort('unrealized_valuation_artifact_invalid')
  source=value['source_fingerprints']
  if not isinstance(source,dict) or set(source)!={'fifo_artifact_fingerprint','market_artifact_fingerprint','tax_artifact_fingerprint','fx_artifact_fingerprints'} or not isinstance(source['fx_artifact_fingerprints'],list):abort('unrealized_valuation_artifact_invalid')
  for key in ('fifo_artifact_fingerprint','market_artifact_fingerprint','tax_artifact_fingerprint'):valid_fp(source[key],'unrealized_valuation_artifact_invalid')
  for fingerprint in source['fx_artifact_fingerprints']:valid_fp(fingerprint,'unrealized_valuation_artifact_invalid')
  if len(source['fx_artifact_fingerprints'])!=len(set(source['fx_artifact_fingerprints'])):abort('unrealized_valuation_artifact_invalid')
  expected_boundaries={'provider_access':False,'network_access':False,'automatic_fx':False,'tax_rules_in_core':False,'display_calculation':False,'canonical_write':False,'legacy_runtime':False}
  if value['boundaries']!=expected_boundaries or value['disclaimer_codes']!=['model_projection_not_legal_advice','unrealized_projection_not_advice_or_liquidation_quote']:abort('unrealized_valuation_artifact_invalid')
  plugin=value['tax_plugin']
  if not isinstance(plugin,dict) or set(plugin)!={'status','plugin_id','plugin_version','rules_fingerprint','manifest_fingerprint','selection_ref','disclaimer_codes'} or plugin['status'] not in {'completed','unavailable','not_selected'} or 'model_projection_not_legal_advice' not in plugin['disclaimer_codes']:abort('unrealized_valuation_artifact_invalid')
  if plugin['status']=='completed':
   if not isinstance(plugin['plugin_id'],str) or not isinstance(plugin['plugin_version'],str):abort('unrealized_valuation_artifact_invalid')
   valid_fp(plugin['rules_fingerprint'],'unrealized_valuation_artifact_invalid');valid_fp(plugin['manifest_fingerprint'],'unrealized_valuation_artifact_invalid');valid_ref(plugin['selection_ref'],'tsr_','unrealized_valuation_artifact_invalid')
  elif any(plugin[key] is not None for key in ('plugin_id','plugin_version','rules_fingerprint','manifest_fingerprint','selection_ref')):abort('unrealized_valuation_artifact_invalid')
  if not isinstance(value['items'],list) or not value['items']:abort('unrealized_valuation_artifact_invalid')
  scale=value['output_scale'];seen=set();statuses=[]
  for row in value['items']:
   if not isinstance(row,dict) or set(row)!=ITEM_FIELDS:abort('unrealized_valuation_artifact_invalid')
   p=valid_ref(row['position_ref'],'psr_','unrealized_valuation_artifact_invalid')
   if p in seen:abort('unrealized_valuation_artifact_invalid')
   seen.add(p);statuses.append(row['position_status']);valid_ref(row['account_ref'],'acr_','unrealized_valuation_artifact_invalid');valid_ref(row['asset_ref'],'asr_','unrealized_valuation_artifact_invalid');valid_ref(row['listing_ref'],'lsr_','unrealized_valuation_artifact_invalid');valid_date(row['as_of_date'],'unrealized_valuation_artifact_invalid');valid_date(row['price_date'],'unrealized_valuation_artifact_invalid')
   if row['as_of_date']!=value['as_of_date'] or row['target_currency']!=value['target_currency']:abort('unrealized_valuation_artifact_invalid')
   valid_currency(row['market_currency'],'unrealized_valuation_artifact_invalid');valid_currency(row['target_currency'],'unrealized_valuation_artifact_invalid')
   if row['basis_currency'] is not None:valid_currency(row['basis_currency'],'unrealized_valuation_artifact_invalid')
   valid_fp(row['position_input_fingerprint'],'unrealized_valuation_artifact_invalid')
   body=dict(row);fp=body.pop('result_fingerprint');valid_fp(fp,'unrealized_valuation_artifact_invalid')
   if fp!=sha(body):abort('unrealized_valuation_artifact_invalid')
   if row['asset_type'] not in ASSET_TYPES or row['position_status'] not in POSITION_STATUSES or row['price_status'] not in PRICE_STATUSES or row['tax_status'] not in TAX_STATUSES or row['fx_status'] not in FX_STATUSES or not isinstance(row['failure_codes'],list) or len(row['failure_codes'])!=len(set(row['failure_codes'])) or not set(row['failure_codes'])<=POSITION_FAILURE_CODES:abort('unrealized_valuation_artifact_invalid')
   quantity=fraction_decimal(row['remaining_quantity_decimal'],positive=True,code='unrealized_valuation_artifact_invalid');cost=None if row['fifo_cost_decimal'] is None else fraction_decimal(row['fifo_cost_decimal'],nonnegative=True,code='unrealized_valuation_artifact_invalid')
   for key in ('market_price_decimal','market_value_market_decimal','market_value_decimal','unrealized_gross_gain_decimal','projected_tax_decimal','liquidation_fee_decimal','net_liquidation_decimal','display_market_value_decimal','display_fifo_cost_decimal','display_unrealized_gross_gain_decimal','display_projected_tax_decimal','display_liquidation_fee_decimal','display_net_liquidation_decimal'):
    if row[key] is not None:fraction_decimal(row[key],code='unrealized_valuation_artifact_invalid')
   if row['price_status']=='completed':
    if row['market_price_decimal'] is None or isinstance(row['price_age_days'],bool) or not isinstance(row['price_age_days'],int) or row['price_age_days']<0:abort('unrealized_valuation_artifact_invalid')
    valid_ref(row['market_revision_ref'],'mrv_','unrealized_valuation_artifact_invalid');valid_fp(row['market_revision_fingerprint'],'unrealized_valuation_artifact_invalid')
   assumption=row['fee_assumption']
   if not isinstance(assumption,dict) or set(assumption)!=FEE_FIELDS or assumption['position_ref']!=p:abort('unrealized_valuation_artifact_invalid')
   fixed=fraction_decimal(assumption['fixed_fee_decimal'],nonnegative=True,code='unrealized_valuation_artifact_invalid');rate=fraction_decimal(assumption['percentage_rate_decimal'],nonnegative=True,code='unrealized_valuation_artifact_invalid')
   if row['market_price_decimal'] is not None and row['market_value_market_decimal'] is not None and row['market_value_market_decimal']!=round_fraction(quantity*fraction_decimal(row['market_price_decimal'],positive=True),scale):abort('unrealized_valuation_artifact_invalid')
   if row['market_value_decimal'] is not None:
    market=fraction_decimal(row['market_value_decimal'])
    if cost is None or row['unrealized_gross_gain_decimal']!=round_fraction(market-cost,scale) or row['liquidation_fee_decimal']!=round_fraction(fixed+market*rate/Fraction(100),scale):abort('unrealized_valuation_artifact_invalid')
    gain=fraction_decimal(row['unrealized_gross_gain_decimal'])
    if gain<=0 and row['projected_tax_decimal']!='0' and row['tax_status'] not in {'completed','not_selected'}:abort('unrealized_valuation_artifact_invalid')
    if row['projected_tax_decimal'] is not None and fraction_decimal(row['projected_tax_decimal'])<0:abort('unrealized_valuation_artifact_invalid')
    if row['net_liquidation_decimal'] is not None:
     if row['projected_tax_decimal'] is None or row['net_liquidation_decimal']!=round_fraction(market-fraction_decimal(row['liquidation_fee_decimal'])-fraction_decimal(row['projected_tax_decimal']),scale):abort('unrealized_valuation_artifact_invalid')
   untaxed=row['tax_status']=='not_selected'
   tax_keys=('projected_tax_decimal','net_liquidation_decimal','display_projected_tax_decimal','display_net_liquidation_decimal')
   if untaxed and (plugin['status']!='not_selected' or any(row[key] is not None for key in tax_keys)):abort('unrealized_valuation_artifact_invalid')
   if plugin['status']=='not_selected' and row['tax_status']!='not_selected' and row['market_value_decimal'] is not None:abort('unrealized_valuation_artifact_invalid')
   if row['position_status']=='completed' and any(row[key] is None for key in ('market_value_decimal','unrealized_gross_gain_decimal','projected_tax_decimal','liquidation_fee_decimal','net_liquidation_decimal','display_market_value_decimal','display_fifo_cost_decimal','display_unrealized_gross_gain_decimal','display_projected_tax_decimal','display_liquidation_fee_decimal','display_net_liquidation_decimal') if not (untaxed and key in tax_keys)):abort('unrealized_valuation_artifact_invalid')
   if row['position_status']=='blocked' and row['market_value_decimal'] is not None:abort('unrealized_valuation_artifact_invalid')
  expected='completed' if all(x=='completed' for x in statuses) else 'blocked' if all(x=='blocked' for x in statuses) else 'partial'
  if value['status']!=expected or value['row_set_fingerprint']!=sha(value['items']):abort('unrealized_valuation_artifact_invalid')
  summary=value['summary'];summary_fields={'target_currency','aggregation_status','position_count','completed_position_count','partial_position_count','blocked_position_count','market_value_decimal','fifo_cost_decimal','unrealized_gross_gain_decimal','projected_tax_decimal','liquidation_fee_decimal','net_liquidation_decimal','valued_position_count','valued_market_value_decimal','valued_fifo_cost_decimal','valued_unrealized_gross_gain_decimal','valued_liquidation_fee_decimal','valued_projected_tax_decimal','valued_net_liquidation_decimal'}
  if not isinstance(summary,dict) or set(summary)!=summary_fields:abort('unrealized_valuation_artifact_invalid')
  expected_summary=_component_summary(value['items'],scale,value['target_currency'])
  if summary!=expected_summary or not isinstance(value['account_summaries'],list):abort('unrealized_valuation_artifact_invalid')
  expected_accounts=[]
  for account_ref in sorted({row['account_ref'] for row in value['items']}):
   account_body={'account_ref':account_ref,**_component_summary([row for row in value['items'] if row['account_ref']==account_ref],scale,value['target_currency'])};expected_accounts.append({**account_body,'account_fingerprint':sha(account_body)})
  if value['account_summaries']!=expected_accounts:abort('unrealized_valuation_artifact_invalid')
  reconciliation=value['reconciliation']
  if not isinstance(reconciliation,dict) or set(reconciliation)!={'item_count','reused_item_count','calculation_mode','full_incremental_row_parity','resolved_invalidation_refs'} or reconciliation['item_count']!=len(statuses) or isinstance(reconciliation['reused_item_count'],bool) or not isinstance(reconciliation['reused_item_count'],int) or not 0<=reconciliation['reused_item_count']<=len(statuses) or reconciliation['calculation_mode']!=value['calculation_mode'] or reconciliation['full_incremental_row_parity'] is not True:abort('unrealized_valuation_artifact_invalid')
  body=dict(value);fp=body.pop('artifact_fingerprint')
  if fp!=sha(body):abort('unrealized_valuation_artifact_invalid')
  return value
 except UnrealizedValuationBlocked:raise
 except (KeyError,TypeError,ValueError,OverflowError) as e:raise UnrealizedValuationBlocked('unrealized_valuation_artifact_invalid') from e

def record_unrealized_valuation_invalidation_v1(store_path,context,*,request_ref,portfolio_ref,reason,source_fingerprint,affected_position_refs,invalidated_at_utc):
 c=normalize_context(context,writer=True);valid_ref(request_ref,'req_');valid_ref(portfolio_ref,'pfr_');valid_fp(source_fingerprint);valid_utc(invalidated_at_utc)
 if reason not in INVALIDATION_REASONS or not isinstance(affected_position_refs,Sequence) or isinstance(affected_position_refs,(str,bytes)):abort('unrealized_valuation_input_invalid')
 affected=sorted({valid_ref(x,'psr_') for x in affected_position_refs});body={'portfolio_ref':portfolio_ref,'reason':reason,'source_fingerprint':source_fingerprint,'affected_position_refs':affected,'invalidated_at_utc':invalidated_at_utc};fingerprint=sha(body);ref=opaque('uvn',[request_ref,body]);con=connect(store_path,c)
 try:
  con.execute('BEGIN IMMEDIATE');existing=con.execute('SELECT invalidation_ref,invalidation_fingerprint FROM unrealized_valuation_invalidation WHERE request_ref=?',(request_ref,)).fetchone()
  if existing:
   con.rollback()
   if existing['invalidation_fingerprint']!=fingerprint:abort('unrealized_valuation_invalidation_conflict')
   return existing['invalidation_ref']
  con.execute('INSERT INTO unrealized_valuation_invalidation VALUES (?,?,?,?,?,?,?,?,?,?)',(opaque('uvi',ref),ref,request_ref,portfolio_ref,reason,source_fingerprint,canonical(affected),c.actor_id,invalidated_at_utc,fingerprint));con.commit();return ref
 except UnrealizedValuationBlocked:con.rollback();raise
 except sqlite3.Error as e:con.rollback();raise UnrealizedValuationBlocked('unrealized_valuation_write_failed') from e
 finally:con.close()

def append_unrealized_valuation_snapshot_v1(store_path,context,request,artifact,completed_at_utc,failpoint=None):
 c=normalize_context(context,writer=True);request=validate_request(dict(request),c);artifact=validate_unrealized_valuation_artifact_v1(artifact,c);valid_utc(completed_at_utc)
 source_times=[request['fifo_artifact']['cutoff_at_utc'],request['tax_artifact']['completed_at_utc']]+[value['history_cutoff_at_utc'] for value in request['fx_artifacts']]
 if completed_at_utc<max(source_times):abort('unrealized_valuation_input_invalid')
 expected_sources={'fifo_artifact_fingerprint':request['fifo_artifact']['artifact_fingerprint'],'market_artifact_fingerprint':request['market_artifact']['artifact_fingerprint'],'tax_artifact_fingerprint':request['tax_artifact']['artifact_fingerprint'],'fx_artifact_fingerprints':[value['artifact_fingerprint'] for value in request['fx_artifacts']]}
 if artifact['request_fingerprint']!=request['request_fingerprint'] or artifact['snapshot_ref']!=opaque('uva',[request['request_ref'],request['request_fingerprint']]) or artifact['portfolio_ref']!=request['portfolio_ref'] or artifact['as_of_date']!=request['as_of_date'] or artifact['target_currency']!=request['target_currency'] or artifact['input_fingerprint']!=request['input_fingerprint'] or artifact['calculation_mode']!=request['calculation_mode'] or artifact['base_snapshot_ref']!=request['base_snapshot_ref'] or artifact['source_fingerprints']!=expected_sources or {row['position_ref'] for row in artifact['items']}!={row['position_ref'] for row in request['fifo_artifact']['positions']}:abort('unrealized_valuation_artifact_invalid')
 if failpoint is not None and failpoint not in FAILPOINTS:abort('unrealized_valuation_input_invalid')
 con=connect(store_path,c)
 try:
  con.execute('BEGIN IMMEDIATE');existing=con.execute('SELECT artifact_fingerprint,artifact_json FROM unrealized_valuation_snapshot WHERE request_ref=?',(request['request_ref'],)).fetchone()
  if existing:
   con.rollback()
   if existing['artifact_fingerprint']!=artifact['artifact_fingerprint']:abort('unrealized_valuation_request_conflict')
   return json.loads(existing['artifact_json'])
  base_id=None
  if request['calculation_mode']=='incremental':
   base=con.execute('SELECT snapshot_id FROM unrealized_valuation_snapshot WHERE snapshot_ref=? AND portfolio_ref=? AND status IN (\'completed\',\'partial\')',(request['base_snapshot_ref'],request['portfolio_ref'])).fetchone()
   if base is None:abort('unrealized_valuation_base_invalid')
   base_id=base['snapshot_id']
  invalidations=[]
  for ref in request['resolved_invalidation_refs']:
   row=con.execute('SELECT invalidation_id,reason,source_fingerprint,affected_position_refs_json,invalidated_at_utc FROM unrealized_valuation_invalidation WHERE invalidation_ref=? AND portfolio_ref=?',(ref,request['portfolio_ref'])).fetchone()
   if row is None:abort('unrealized_valuation_invalidation_conflict')
   if completed_at_utc<row['invalidated_at_utc'] or con.execute('SELECT 1 FROM unrealized_valuation_invalidation_resolution WHERE invalidation_id=? LIMIT 1',(row['invalidation_id'],)).fetchone() is not None:abort('unrealized_valuation_invalidation_conflict')
   affected=json.loads(row['affected_position_refs_json'])
   if affected and not set(affected)<={x['position_ref'] for x in artifact['items']}:abort('unrealized_valuation_invalidation_conflict')
   current_sources={'fifo_correction':request['fifo_artifact']['artifact_fingerprint'],'market_correction':request['market_artifact']['artifact_fingerprint'],'tax_policy_revision':request['tax_artifact']['artifact_fingerprint'],'algorithm_upgrade':request['input_fingerprint']}
   if row['reason']=='fx_correction':
    if row['source_fingerprint'] in {value['artifact_fingerprint'] for value in request['fx_artifacts']}:abort('unrealized_valuation_invalidation_conflict')
   elif current_sources[row['reason']]==row['source_fingerprint']:abort('unrealized_valuation_invalidation_conflict')
   invalidations.append(row['invalidation_id'])
  snapshot_id=opaque('uvs',artifact['snapshot_ref']);source=artifact['source_fingerprints']
  con.execute('INSERT INTO unrealized_valuation_snapshot VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(snapshot_id,artifact['snapshot_ref'],request['request_ref'],artifact['portfolio_ref'],artifact['as_of_date'],artifact['target_currency'],artifact['status'],artifact['calculation_mode'],artifact['algorithm_version'],artifact['input_fingerprint'],source['fifo_artifact_fingerprint'],source['market_artifact_fingerprint'],source['tax_artifact_fingerprint'],sha(source['fx_artifact_fingerprints']),base_id,artifact['row_set_fingerprint'],artifact['artifact_fingerprint'],canonical(artifact),c.actor_id,completed_at_utc))
  if failpoint=='after_snapshot':raise RuntimeError('synthetic_failpoint')
  for ordinal,row in enumerate(artifact['items'],1):
   con.execute('INSERT INTO unrealized_valuation_position_result VALUES (?,?,?,?,?,?,?,?,?,?)',(opaque('uvr',[artifact['snapshot_ref'],ordinal]),snapshot_id,ordinal,row['position_ref'],row['account_ref'],row['asset_ref'],row['position_status'],row['position_input_fingerprint'],row['result_fingerprint'],canonical(row)))
   if failpoint=='after_first_result' and ordinal==1:raise RuntimeError('synthetic_failpoint')
  if artifact['status']!='blocked':
   for invalidation_id in invalidations:con.execute('INSERT INTO unrealized_valuation_invalidation_resolution VALUES (?,?,?,?)',(opaque('uvx',[snapshot_id,invalidation_id]),snapshot_id,invalidation_id,completed_at_utc))
  if failpoint=='before_commit':raise RuntimeError('synthetic_failpoint')
  con.commit();return artifact
 except UnrealizedValuationBlocked:con.rollback();raise
 except RuntimeError as e:
  con.rollback()
  if str(e)=='synthetic_failpoint':raise UnrealizedValuationBlocked('unrealized_valuation_synthetic_failpoint') from None
  raise UnrealizedValuationBlocked('unrealized_valuation_boundary_failed') from e
 except sqlite3.Error as e:con.rollback();raise UnrealizedValuationBlocked('unrealized_valuation_write_failed') from e
 finally:con.close()

def read_unrealized_valuation_v1(store_path,context,portfolio_ref):
 c=normalize_context(context);valid_ref(portfolio_ref,'pfr_');con=connect(store_path,c,ro=True)
 try:
  latest=con.execute('SELECT * FROM unrealized_valuation_snapshot WHERE portfolio_ref=? ORDER BY completed_at_utc DESC,snapshot_ref DESC LIMIT 1',(portfolio_ref,)).fetchone();usable=con.execute("SELECT * FROM unrealized_valuation_snapshot WHERE portfolio_ref=? AND status IN ('completed','partial') ORDER BY completed_at_utc DESC,snapshot_ref DESC LIMIT 1",(portfolio_ref,)).fetchone()
  pending=con.execute('''SELECT invalidation.* FROM unrealized_valuation_invalidation invalidation WHERE invalidation.portfolio_ref=? AND (? IS NULL OR NOT EXISTS (SELECT 1 FROM unrealized_valuation_invalidation_resolution resolution JOIN unrealized_valuation_snapshot resolved ON resolved.snapshot_id=resolution.snapshot_id WHERE resolution.invalidation_id=invalidation.invalidation_id AND resolved.completed_at_utc<=?)) ORDER BY invalidated_at_utc,invalidation_ref''',(portfolio_ref,None if usable is None else usable['completed_at_utc'],None if usable is None else usable['completed_at_utc'])).fetchall()
  pending_rows=[{'invalidation_ref':r['invalidation_ref'],'reason':r['reason'],'source_fingerprint':r['source_fingerprint'],'affected_position_refs':json.loads(r['affected_position_refs_json']),'invalidated_at_utc':r['invalidated_at_utc']} for r in pending]
  artifact=None if usable is None else json.loads(usable['artifact_json']);attempt=None if latest is None else {'snapshot_ref':latest['snapshot_ref'],'status':latest['status'],'input_fingerprint':latest['input_fingerprint'],'completed_at_utc':latest['completed_at_utc']}
  if latest is None:status='empty'
  elif usable is None:status='blocked'
  elif pending_rows or latest['status']=='blocked':status='stale'
  else:status=usable['status']
  return {'contract_version':'unrealized_valuation_read_model_v1','status':status,'artifact':artifact,'latest_attempt':attempt,'pending_invalidations':pending_rows,'boundaries':{'query_only':True,'provider_access':False,'network_access':False,'calculation':False,'write_authority':False}}
 finally:con.close()
def read_unrealized_valuation_history_v1(store_path,context,portfolio_ref):
 c=normalize_context(context);valid_ref(portfolio_ref,'pfr_');con=connect(store_path,c,ro=True)
 try:return [json.loads(r[0]) for r in con.execute('SELECT artifact_json FROM unrealized_valuation_snapshot WHERE portfolio_ref=? ORDER BY completed_at_utc,snapshot_ref',(portfolio_ref,)).fetchall()]
 finally:con.close()

def fsync_dir(path,code):
 fd=None
 try:fd=os.open(path,os.O_RDONLY|getattr(os,'O_DIRECTORY',0));os.fsync(fd)
 except OSError as e:raise UnrealizedValuationBlocked(code) from e
 finally:
  if fd is not None:os.close(fd)
def atomic_file(target,payload):
 fd=None;stage=None
 try:
  fd,name=tempfile.mkstemp(prefix=f'.{target.name}.',suffix='.tmp',dir=target.parent);stage=Path(name);os.fchmod(fd,0o600)
  with os.fdopen(fd,'wb') as h:fd=None;h.write(payload);h.flush();os.fsync(h.fileno())
  os.link(stage,target,follow_symlinks=False);stage.unlink();stage=None;fsync_dir(target.parent,'unrealized_valuation_artifact_invalid');return target
 except FileExistsError:abort('unrealized_valuation_artifact_exists')
 except UnrealizedValuationBlocked:raise
 except Exception as e:raise UnrealizedValuationBlocked('unrealized_valuation_artifact_invalid') from e
 finally:
  if fd is not None:os.close(fd)
  if stage is not None and stage.exists() and not stage.is_symlink():stage.unlink()
def read_unrealized_valuation_artifact_v1(path,context,browser_safe=False):
 c=normalize_context(context)
 if c.role=='viewer' and not browser_safe:abort('unrealized_valuation_context_invalid')
 source=regular_path(path,artifact=True)
 try:value=json.loads(source.read_text())
 except Exception as e:raise UnrealizedValuationBlocked('unrealized_valuation_artifact_invalid') from e
 artifact=validate_unrealized_valuation_artifact_v1(value,c)
 return redact_unrealized_valuation_artifact_v1(artifact) if browser_safe else artifact
def publish_unrealized_valuation_artifact_v1(artifact,context,path):
 c=normalize_context(context,writer=True);artifact=validate_unrealized_valuation_artifact_v1(artifact,c)
 try:target=regular_path(path,new=True,artifact=True)
 except UnrealizedValuationBlocked as e:
  if e.code!='unrealized_valuation_artifact_exists':raise
  existing=read_unrealized_valuation_artifact_v1(path,c)
  if existing!=artifact:raise
  return regular_path(path,artifact=True)
 try:return atomic_file(target,(canonical(artifact)+'\n').encode())
 except UnrealizedValuationBlocked as e:
  if e.code!='unrealized_valuation_artifact_exists':raise
  existing=read_unrealized_valuation_artifact_v1(path,c)
  if existing!=artifact:raise
  return regular_path(path,artifact=True)
def redact_unrealized_valuation_artifact_v1(artifact):
 rows=[];account_ordinals={account['account_ref']:ordinal for ordinal,account in enumerate(artifact['account_summaries'],1)}
 for ordinal,row in enumerate(artifact['items'],1):
  keys=('position_status','price_status','tax_status','fx_status','basis_currency','market_currency','remaining_quantity_decimal','market_price_decimal','market_value_decimal','fifo_cost_decimal','unrealized_gross_gain_decimal','projected_tax_decimal','liquidation_fee_decimal','net_liquidation_decimal','display_market_value_decimal','display_fifo_cost_decimal','display_unrealized_gross_gain_decimal','display_projected_tax_decimal','display_liquidation_fee_decimal','display_net_liquidation_decimal','failure_codes')
  fee={key:row['fee_assumption'][key] for key in ('fixed_fee_decimal','percentage_rate_decimal','assumption_code')}
  rows.append({'position_ordinal':ordinal,'account_ordinal':account_ordinals[row['account_ref']],'fee_assumption':fee,**{k:row[k] for k in keys}})
 accounts=[{'account_ordinal':ordinal,**{key:value for key,value in account.items() if key not in {'account_ref','account_fingerprint','target_currency'}}} for ordinal,account in enumerate(artifact['account_summaries'],1)]
 return {'status':artifact['status'],'as_of_date':artifact['as_of_date'],'target_currency':artifact['target_currency'],'summary':artifact['summary'],'tax_plugin':{'status':artifact['tax_plugin']['status'],'plugin_id':artifact['tax_plugin']['plugin_id'],'plugin_version':artifact['tax_plugin']['plugin_version'],'disclaimer_codes':artifact['tax_plugin']['disclaimer_codes']},'accounts':accounts,'positions':rows,'disclaimer_codes':artifact['disclaimer_codes'],'boundaries':{'context_exposed':False,'filesystem_authority':False,'sql_authority':False,'write_authority':False,'provider_access':False,'network_access':False,'calculation':False}}
def csv_bytes(fields,rows):
 stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n',extrasaction='raise');writer.writeheader()
 for row in rows:
  values={k:'' if row.get(k) is None else str(row.get(k)).lower() if isinstance(row.get(k),bool) else str(row.get(k)) for k in fields}
  if any('\n' in v or '\r' in v or v.startswith(('=','+','@')) for v in values.values()):abort('unrealized_valuation_evidence_invalid')
  writer.writerow(values)
 return stream.getvalue().encode()
def exact_evidence(target,bundle):
 try:
  directory=owner_directory(target);children={x.name:x for x in directory.iterdir()}
  if set(children)!=set(bundle):abort('unrealized_valuation_evidence_exists')
  for name,payload in bundle.items():
   source=regular_path(children[name])
   if source.read_bytes()!=payload:abort('unrealized_valuation_evidence_exists')
  return directory
 except UnrealizedValuationBlocked as e:
  if e.code=='unrealized_valuation_evidence_exists':raise
  raise UnrealizedValuationBlocked('unrealized_valuation_evidence_invalid') from None
def write_fsync(path,payload):
 fd=None
 try:
  fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600);os.fchmod(fd,0o600)
  with os.fdopen(fd,'wb') as h:fd=None;h.write(payload);h.flush();os.fsync(h.fileno())
 except Exception as e:
  if fd is not None:os.close(fd)
  raise UnrealizedValuationBlocked('unrealized_valuation_evidence_invalid') from e
def publish_unrealized_valuation_evidence_v1(artifact,context,output_directory):
 c=normalize_context(context,writer=True);artifact=validate_unrealized_valuation_artifact_v1(artifact,c);target=Path(output_directory);parent=owner_directory(target.parent);target=parent/target.name
 positions=[];components=[];account_ordinals={account['account_ref']:ordinal for ordinal,account in enumerate(artifact['account_summaries'],1)}
 for ordinal,row in enumerate(artifact['items'],1):
  account_ordinal=account_ordinals[row['account_ref']]
  positions.append({'position_ordinal':ordinal,'account_ordinal':account_ordinal,'position_status':row['position_status'],'price_status':row['price_status'],'tax_status':row['tax_status'],'fx_status':row['fx_status'],'market_currency':row['market_currency'],'basis_currency':row['basis_currency'],'target_currency':row['target_currency'],'quantity_decimal':row['remaining_quantity_decimal'],'fee_assumption_code':row['fee_assumption']['assumption_code'],'fixed_fee_decimal':row['fee_assumption']['fixed_fee_decimal'],'percentage_rate_decimal':row['fee_assumption']['percentage_rate_decimal'],'failure_codes':'|'.join(row['failure_codes'])})
  for code,native,display in (('market_value',row['market_value_decimal'],row['display_market_value_decimal']),('fifo_cost',row['fifo_cost_decimal'],row['display_fifo_cost_decimal']),('unrealized_gross_gain',row['unrealized_gross_gain_decimal'],row['display_unrealized_gross_gain_decimal']),('projected_tax',row['projected_tax_decimal'],row['display_projected_tax_decimal']),('liquidation_fee',row['liquidation_fee_decimal'],row['display_liquidation_fee_decimal']),('net_liquidation',row['net_liquidation_decimal'],row['display_net_liquidation_decimal'])):components.append({'position_ordinal':ordinal,'account_ordinal':account_ordinal,'component_code':code,'native_currency':row['basis_currency'],'native_amount_decimal':native,'display_currency':row['target_currency'],'display_amount_decimal':display})
 s=artifact['summary'];recon=[{'snapshot_status':artifact['status'],'target_currency':artifact['target_currency'],'position_count':s['position_count'],'account_count':len(artifact['account_summaries']),'completed_position_count':s['completed_position_count'],'partial_position_count':s['partial_position_count'],'blocked_position_count':s['blocked_position_count'],'row_set_fingerprint':artifact['row_set_fingerprint']}]
 files={'valuation-positions.csv':csv_bytes(('position_ordinal','account_ordinal','position_status','price_status','tax_status','fx_status','market_currency','basis_currency','target_currency','quantity_decimal','fee_assumption_code','fixed_fee_decimal','percentage_rate_decimal','failure_codes'),positions),'valuation-components.csv':csv_bytes(('position_ordinal','account_ordinal','component_code','native_currency','native_amount_decimal','display_currency','display_amount_decimal'),components),'valuation-reconciliation.csv':csv_bytes(('snapshot_status','target_currency','position_count','account_count','completed_position_count','partial_position_count','blocked_position_count','row_set_fingerprint'),recon)};roles={'valuation-positions.csv':'normative_position_results','valuation-components.csv':'normative_component_reconciliation','valuation-reconciliation.csv':'normative_snapshot_reconciliation'}
 body={'calculation_evidence_version':'1.3','profile_id':'unrealized_valuation_v1','status':'completed','scope_kind':'portfolio','scope_ref':artifact['portfolio_ref'],'target_currency':artifact['target_currency'],'algorithm_version':artifact['algorithm_version'],'context_binding_fingerprint':artifact['context_binding_fingerprint'],'input_fingerprint':artifact['input_fingerprint'],'as_of_date':artifact['as_of_date'],'files':[{'file_name':n,'content_role':roles[n],'row_count':len(p.decode().splitlines())-1,'sha256':sha(p)} for n,p in sorted(files.items())],'reconciliation':{'snapshot_status':artifact['status'],'position_count':s['position_count'],'account_count':len(artifact['account_summaries']),'completed_position_count':s['completed_position_count'],'partial_position_count':s['partial_position_count'],'blocked_position_count':s['blocked_position_count'],'row_set_fingerprint':artifact['row_set_fingerprint']},'boundaries':{'provider_access':False,'network_access':False,'canonical_write':False,'app_side_calculation':False,'automatic_fx':False,'tax_rules_in_core':False,'reimport_authorized':False}}
 manifest={**body,'evidence_fingerprint':sha(body)};bundle={**files,'evidence-manifest.json':(canonical(manifest)+'\n').encode()}
 if target.exists() or target.is_symlink():return exact_evidence(target,bundle)
 stage=None
 try:
  stage=Path(tempfile.mkdtemp(prefix=f'.{target.name}.',suffix='.tmp',dir=parent));os.chmod(stage,0o700)
  for n,p in bundle.items():write_fsync(stage/n,p)
  fsync_dir(stage,'unrealized_valuation_evidence_invalid');os.rename(stage,target);stage=None;fsync_dir(parent,'unrealized_valuation_evidence_invalid');return target
 except UnrealizedValuationBlocked:raise
 except OSError:
  if target.exists() or target.is_symlink():return exact_evidence(target,bundle)
  abort('unrealized_valuation_evidence_invalid')
 finally:
  if stage is not None and stage.exists() and not stage.is_symlink():
   for child in stage.iterdir():
    if child.is_file() and not child.is_symlink():child.unlink()
   stage.rmdir()

def new_unrealized_valuation_worker_job_v1(context,*,store_path,request,output_path,evidence_output_path,completed_at_utc):
 c=normalize_context(context,writer=True);request=validate_request(dict(request),c);valid_utc(completed_at_utc,'unrealized_valuation_job_invalid')
 def path(value,nullable=False):
  if value is None and nullable:return None
  text=str(value)
  if not text.startswith('/') or '\x00' in text or len(text)>4096:abort('unrealized_valuation_job_invalid')
  return text
 body={'contract_version':'unrealized_valuation_worker_job_v1','context':domain_context(c),'store_path':path(store_path),'request':request,'output_path':path(output_path),'evidence_output_path':path(evidence_output_path,True),'completed_at_utc':completed_at_utc};return {**body,'job_fingerprint':sha(body)}
def load_unrealized_valuation_worker_job_v1(path):
 try:
  source=regular_path(path,artifact=True)
  if source.stat().st_size>5_000_000:abort('unrealized_valuation_job_invalid')
  value=json.loads(source.read_text())
  return validate_job(value)
 except UnrealizedValuationBlocked as error:
  if error.code=='unrealized_valuation_job_invalid':raise
  raise UnrealizedValuationBlocked('unrealized_valuation_job_invalid') from None
 except Exception as e:raise UnrealizedValuationBlocked('unrealized_valuation_job_invalid') from e
def validate_job(value):
 required={'contract_version','context','store_path','request','output_path','evidence_output_path','completed_at_utc','job_fingerprint'}
 if not isinstance(value,dict) or set(value)!=required or value.get('contract_version')!='unrealized_valuation_worker_job_v1':abort('unrealized_valuation_job_invalid')
 rebuilt=new_unrealized_valuation_worker_job_v1(value['context'],store_path=value['store_path'],request=value['request'],output_path=value['output_path'],evidence_output_path=value['evidence_output_path'],completed_at_utc=value['completed_at_utc'])
 if rebuilt!=value:abort('unrealized_valuation_job_invalid')
 return value
def run_unrealized_valuation_worker_job_v1(job):
 value=validate_job(dict(job));c=normalize_context(value['context'],writer=True);previous=None
 if value['request']['calculation_mode']=='incremental':
  read=read_unrealized_valuation_v1(value['store_path'],c,value['request']['portfolio_ref']);previous=read['artifact']
 artifact=materialize_unrealized_valuation_v1(c,value['request'],previous);stored=append_unrealized_valuation_snapshot_v1(value['store_path'],c,value['request'],artifact,value['completed_at_utc']);publish_unrealized_valuation_artifact_v1(stored,c,value['output_path'])
 if value['evidence_output_path'] is not None:publish_unrealized_valuation_evidence_v1(stored,c,value['evidence_output_path'])
 return stored

def unrealized_valuation_error_codes_v1():return tuple(sorted(ERROR_CODES))
__all__=['ALGORITHM_VERSION','UnrealizedValuationBlocked','ValuationContext','append_unrealized_valuation_snapshot_v1','bootstrap_unrealized_valuation_store_v1','context_fingerprint','load_unrealized_valuation_worker_job_v1','materialize_unrealized_valuation_v1','new_unrealized_fifo_artifact_v1','new_unrealized_market_artifact_v1','new_unrealized_tax_artifact_v1','new_unrealized_valuation_request_v1','new_unrealized_valuation_worker_job_v1','publish_unrealized_valuation_artifact_v1','publish_unrealized_valuation_evidence_v1','read_unrealized_valuation_artifact_v1','read_unrealized_valuation_history_v1','read_unrealized_valuation_v1','record_unrealized_valuation_invalidation_v1','redact_unrealized_valuation_artifact_v1','run_unrealized_valuation_worker_job_v1','unrealized_valuation_error_codes_v1','validate_unrealized_valuation_artifact_v1']
