#!/usr/bin/env python3
"""Plugin-driven persistent realized Event and Annual Tax projections."""
from __future__ import annotations
import csv,hashlib,json,os,re,sqlite3,stat
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation,localcontext
from pathlib import Path
from typing import Any,Mapping,Sequence
from migrations.reference.tax_model_plugin_v1 import TaxPluginRunResult,TaxPluginSelection,new_tax_plugin_bound_input_v1
ROOT=Path(__file__).resolve().parents[2];SCHEMA=ROOT/'contracts'/'realized-event-tax'/'v1'/'schema.sql'
UTC=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$');DATE=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$');DECIMAL=re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$')
EVENT_FIELDS=('event_ref','effective_at_utc','local_date','event_type','account_ref','asset_ref','currency','gross_proceeds_decimal','realized_gross_gain_decimal','gross_income_decimal','fee_decimal','tax_year','classification_code','tax_bucket','partial_exemption_rate_decimal','taxable_contribution_decimal','projected_event_tax_decimal','projected_net_gain_decimal','projected_net_proceeds_decimal','projection_status','failure_code','plugin_id','plugin_version','rules_fingerprint','disclaimer_code')
ANNUAL_FIELDS=('tax_year','row_type','tax_bucket','currency','positive_contribution_decimal','negative_contribution_decimal','net_contribution_decimal','opening_loss_carryforward_decimal','used_loss_decimal','closing_loss_carryforward_decimal','allowance_available_decimal','allowance_used_decimal','withholding_credit_decimal','projected_annual_tax_decimal','projected_net_gain_decimal','defaulted_parameter_codes','projection_status','failure_code','plugin_id','plugin_version','rules_fingerprint','disclaimer_code')
REASONS={'fifo_change','tax_classification_change','tax_parameter_change','plugin_change','annual_carryforward_change','initial_projection'}
class RealizedTaxBlocked(ValueError):
 def __init__(self,code):super().__init__(code);self.code=code
@dataclass(frozen=True)
class TaxProjectionContext:tenant_id:str;user_id:str;data_space_id:str;actor_id:str
@dataclass(frozen=True)
class TaxProjectionJob:job_ref:str;portfolio_ref:str;projection_mode:str;tax_year:int|None;source_artifact_ref:str;invalidated_from:str;invalidation_reason:str
@dataclass(frozen=True)
class TaxProjectionArtifact:artifact_ref:str;portfolio_ref:str;projection_mode:str;tax_year:int|None;source_artifact_ref:str;plugin_id:str;plugin_version:str;rules_fingerprint:str;selection_ref:str;readiness_status:str;row_set_fingerprint:str

def abort(code):raise RealizedTaxBlocked(code)
def canonical(v):return json.dumps(v,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':'))
def sha(v):
 p=v if isinstance(v,bytes) else (v.encode() if isinstance(v,str) else canonical(v).encode());return hashlib.sha256(p).hexdigest()
def ident(prefix,v):return f'{prefix}_{sha(v)[:32]}'
def context(value):
 if isinstance(value,Mapping):
  try:value=TaxProjectionContext(*(value[k] for k in ('tenant_id','user_id','data_space_id','actor_id')))
  except (KeyError,TypeError) as e:raise RealizedTaxBlocked('realized_tax_context_invalid') from e
 if not isinstance(value,TaxProjectionContext):abort('realized_tax_context_invalid')
 for i,x in enumerate((value.tenant_id,value.user_id,value.data_space_id,value.actor_id)):
  if not isinstance(x,str) or not 3<=len(x)<=(80 if i==3 else 64) or re.search(r'[\x00-\x1f\x7f]',x):abort('realized_tax_context_invalid')
 return value
def context_fp(value):
 c=context(value);return sha({'contract_version':'realized_tax_projection_v1','tenant_id':c.tenant_id,'user_id':c.user_id,'data_space_id':c.data_space_id})
def utc(v):
 if not isinstance(v,str) or not UTC.fullmatch(v):abort('realized_tax_input_invalid')
 return v
def ref(v,prefix=None):
 if not isinstance(v,str) or not re.fullmatch(r'[a-z][a-z0-9]{2}_[a-f0-9]{24,32}',v) or prefix and not v.startswith(prefix):abort('realized_tax_input_invalid')
 return v
def decimal(v,nullable=False):
 if v is None and nullable:return None
 if not isinstance(v,str) or len(v)>80 or not DECIMAL.fullmatch(v):abort('realized_tax_decimal_invalid')
 return v
def d(v):
 decimal(v)
 try:
  with localcontext() as c:c.prec=200;return Decimal(v)
 except InvalidOperation:abort('realized_tax_decimal_invalid')
def bootstrap_tax_projection_store_v1(path,ctx,created_at_utc):
 c=context(ctx);created=utc(created_at_utc);target=Path(path)
 if target.exists() or target.is_symlink():abort('realized_tax_store_exists')
 try:target=target.parent.resolve(strict=True)/target.name
 except OSError as e:raise RealizedTaxBlocked('realized_tax_store_invalid') from e
 con=sqlite3.connect(target)
 try:con.executescript(SCHEMA.read_text());con.execute('INSERT INTO tax_projection_store_binding VALUES (1,2000,?,?)',(context_fp(c),created));con.commit()
 except Exception:con.close();target.unlink(missing_ok=True);raise
 finally:
  try:con.close()
  except:pass
 os.chmod(target,0o600);return target
def connect(path,ctx,ro=False):
 c=context(ctx);p=Path(path)
 if p.is_symlink() or not p.is_file():abort('realized_tax_store_invalid')
 try:
  con=sqlite3.connect(f'{p.resolve(strict=True).as_uri()}?mode=ro&immutable=1',uri=True) if ro else sqlite3.connect(p.resolve(strict=True),isolation_level=None);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
  if ro:con.execute('PRAGMA query_only=ON')
  b=con.execute('SELECT context_binding_fingerprint FROM tax_projection_store_binding WHERE singleton_id=1').fetchone()
  if con.execute('PRAGMA user_version').fetchone()[0]!=2000 or b is None or b[0]!=context_fp(c):con.close();abort('realized_tax_context_mismatch')
  return con
 except RealizedTaxBlocked:raise
 except sqlite3.Error as e:raise RealizedTaxBlocked('realized_tax_store_invalid') from e
def schedule_tax_projection_v1(store,ctx,*,request_ref,portfolio_ref,projection_mode,tax_year,source_artifact_ref,invalidated_from,invalidation_reason,created_at_utc):
 if not re.fullmatch(r'req_[a-f0-9]{24,32}',str(request_ref)) or projection_mode not in {'realized_event','realized_annual'} or invalidation_reason not in REASONS:abort('realized_tax_input_invalid')
 ref(portfolio_ref,'pfr_');ref(source_artifact_ref);created=utc(created_at_utc)
 if projection_mode=='realized_event':
  if tax_year is not None:abort('realized_tax_input_invalid')
  utc(invalidated_from)
 else:
  if not isinstance(tax_year,int) or not 1900<=tax_year<=9999 or str(tax_year)!=str(invalidated_from):abort('realized_tax_input_invalid')
 payload={'context':context_fp(ctx),'request_ref':request_ref,'portfolio_ref':portfolio_ref,'mode':projection_mode,'tax_year':tax_year,'source':source_artifact_ref,'from':invalidated_from,'reason':invalidation_reason};job_ref=ident('tjb',payload);job_id=ident('tpj',job_ref);created_state=ident('tjs',[job_ref,1])
 con=connect(store,ctx)
 try:
  con.execute('BEGIN IMMEDIATE');con.execute('INSERT INTO tax_projection_job VALUES (?,?,?,?,?,?,?,?,?,?)',(job_id,job_ref,request_ref,portfolio_ref,projection_mode,tax_year,source_artifact_ref,invalidated_from,invalidation_reason,created));con.execute("INSERT INTO tax_projection_job_state VALUES (?,?,1,'pending',NULL,NULL,NULL,?)",(created_state,job_id,created));con.commit()
 except sqlite3.IntegrityError as e:con.rollback();raise RealizedTaxBlocked('realized_tax_job_conflict') from e
 finally:con.close()
 return TaxProjectionJob(job_ref,portfolio_ref,projection_mode,tax_year,source_artifact_ref,invalidated_from,invalidation_reason)
def schedule_annual_tax_chain_v1(store,ctx,*,request_refs,portfolio_ref,source_artifact_ref,from_year,through_year,invalidation_reason,created_at_utc):
 if not isinstance(from_year,int) or not isinstance(through_year,int) or from_year>through_year or not isinstance(request_refs,Sequence) or len(request_refs)!=(through_year-from_year+1):abort('realized_tax_input_invalid')
 return [schedule_tax_projection_v1(store,ctx,request_ref=request_refs[index],portfolio_ref=portfolio_ref,projection_mode='realized_annual',tax_year=year,source_artifact_ref=source_artifact_ref,invalidated_from=str(year),invalidation_reason=invalidation_reason,created_at_utc=created_at_utc) for index,year in enumerate(range(from_year,through_year+1))]

def _semantic(value,fingerprint,code='realized_tax_fifo_not_completed'):
 required={'semantic_contract','source_event_count','projected_event_count','coupled_transaction_fact','automatic_cash_posting_state'}
 if not isinstance(value,list) or not value:abort(code)
 bindings=[];contracts=set()
 for row in value:
  if not isinstance(row,dict) or set(row)!=required or row['semantic_contract'] in contracts or row['semantic_contract'] not in {'portfolio_ledger_v1_transaction_fact','asset_activity_v1'}:abort(code)
  if not all(isinstance(row[key],int) and not isinstance(row[key],bool) and row[key]>=0 for key in ('source_event_count','projected_event_count')) or row['projected_event_count']>row['source_event_count']:abort(code)
  valid=(row['semantic_contract']=='portfolio_ledger_v1_transaction_fact' and row['coupled_transaction_fact'] is True and row['automatic_cash_posting_state']=='unknown') or (row['semantic_contract']=='asset_activity_v1' and row['coupled_transaction_fact'] is False and row['automatic_cash_posting_state']=='none_created')
  if not valid:abort(code)
  contracts.add(row['semantic_contract']);bindings.append(dict(row))
 if not isinstance(fingerprint,str) or not re.fullmatch(r'[a-f0-9]{64}',fingerprint) or fingerprint!=sha(bindings):abort(code)
 return bindings,fingerprint
def prepare_event_tax_plugin_input_v1(realized_read_model,selection,classifications,parameters,cutoff):
 if not isinstance(realized_read_model,dict) or realized_read_model.get('status')!='completed' or not isinstance(realized_read_model.get('artifact'),dict):abort('realized_tax_fifo_not_completed')
 semantic_bindings,semantic_fingerprint=_semantic(realized_read_model['artifact'].get('semantic_source_bindings'),realized_read_model['artifact'].get('semantic_binding_fingerprint'))
 if not isinstance(selection,TaxPluginSelection) or selection.projection_mode!='realized_event':abort('realized_tax_plugin_unavailable')
 tables=realized_read_model.get('tables',{});rows=tables.get('event-results.csv');movements=tables.get('lot-movements.csv')
 if not isinstance(rows,list) or not isinstance(movements,list):abort('realized_tax_fifo_not_completed')
 allocations={}
 for movement in movements:
  if movement.get('movement_type')!='sell_consumption':continue
  allocations.setdefault(movement['event_ref'],[]).append({key:movement[key] for key in ('quantity_decimal','fifo_cost_decimal','acquisition_event_ref','acquisition_effective_at_utc','acquisition_local_date')})
 event_rows=[]
 for row in rows:
  semantic=row.get('semantic_contract','portfolio_ledger_v1_transaction_fact');coupled=row.get('coupled_transaction_fact','1')=='1';automatic=None if row.get('automatic_cash_posting_created') is None else row.get('automatic_cash_posting_created')=='1'
  if semantic not in {'portfolio_ledger_v1_transaction_fact','asset_activity_v1'} or semantic=='portfolio_ledger_v1_transaction_fact' and (not coupled or automatic is not None) or semantic=='asset_activity_v1' and (coupled or automatic is not False):abort('realized_tax_fifo_not_completed')
  event_row={key:row[key] for key in ('event_ref','effective_at_utc','local_date','event_type','account_ref','asset_ref','asset_type','currency','quantity_decimal','gross_proceeds_decimal','realized_gross_gain_decimal','gross_income_decimal','fee_decimal')};event_row['fee_decimal']=event_row['fee_decimal'] or '0';event_row['fifo_allocations']=allocations.get(row['event_ref'],[]);event_row['semantic_contract']=semantic;event_row['coupled_transaction_fact']=coupled;event_row['automatic_cash_posting_created']=automatic;event_rows.append(event_row)
 bound=new_tax_plugin_bound_input_v1(projection_mode='realized_event',portfolio_ref=realized_read_model['artifact']['portfolio_ref'],source_artifact_ref=realized_read_model['artifact']['artifact_ref'],cutoff=cutoff,rows=event_rows,classifications=classifications,parameters=parameters)
 bound['semantic_source_bindings']=semantic_bindings;bound['semantic_binding_fingerprint']=semantic_fingerprint
 body=dict(bound);body.pop('input_fingerprint');bound['input_fingerprint']=sha(body)
 return bound
def prepare_annual_tax_plugin_input_v1(event_read_model,selection,parameters,tax_year,prior_state=None):
 if not isinstance(event_read_model,dict) or event_read_model.get('status')!='completed' or not isinstance(event_read_model.get('artifact'),dict):abort('realized_tax_event_not_completed')
 if not isinstance(selection,TaxPluginSelection) or selection.projection_mode!='realized_annual':abort('realized_tax_plugin_unavailable')
 semantic_bindings,semantic_fingerprint=_semantic(event_read_model['artifact'].get('semantic_source_bindings'),event_read_model['artifact'].get('semantic_binding_fingerprint'),'realized_tax_event_not_completed')
 rows=[row for row in event_read_model['rows'] if row['projection_status']=='completed' and row['tax_year']==tax_year]
 if len({row['currency'] for row in rows})>1:abort('realized_tax_currency_conflict')
 bound=new_tax_plugin_bound_input_v1(projection_mode='realized_annual',portfolio_ref=event_read_model['artifact']['portfolio_ref'],source_artifact_ref=event_read_model['artifact']['artifact_ref'],cutoff=str(tax_year),rows=rows,classifications=[],parameters=parameters,prior_state=prior_state)
 bound['semantic_source_bindings']=semantic_bindings;bound['semantic_binding_fingerprint']=semantic_fingerprint;body=dict(bound);body.pop('input_fingerprint');bound['input_fingerprint']=sha(body);return bound
def _validate_identity(row,result,selection):
 if row['plugin_id']!=result.plugin_id or row['plugin_version']!=result.plugin_version or row['rules_fingerprint']!=result.rules_fingerprint or row['disclaimer_code']!='model_projection_not_legal_advice':abort('realized_tax_plugin_output_invalid')
 if (selection.plugin_id,selection.plugin_version,selection.rules_fingerprint)!=(result.plugin_id,result.plugin_version,result.rules_fingerprint):abort('realized_tax_plugin_output_invalid')
def validate_event_tax_candidate_v1(result,bound_input,selection):
 with localcontext() as c:
  c.prec=200
  return _validate_event_tax_candidate_v1_exact(result,bound_input,selection)
def _validate_event_tax_candidate_v1_exact(result,bound_input,selection):
 if not isinstance(result,TaxPluginRunResult) or result.projection_mode!='realized_event' or result.input_fingerprint!=bound_input['input_fingerprint']:abort('realized_tax_plugin_output_invalid')
 source={r['event_ref']:r for r in bound_input['rows']};observed=set();rows=[]
 for raw in result.rows:
  if set(raw)!=set(EVENT_FIELDS) or raw['event_ref'] not in source or raw['event_ref'] in observed:abort('realized_tax_plugin_output_invalid')
  observed.add(raw['event_ref']);s=source[raw['event_ref']];_validate_identity(raw,result,selection)
  for key in ('effective_at_utc','local_date','event_type','account_ref','asset_ref','currency','gross_proceeds_decimal','realized_gross_gain_decimal','gross_income_decimal','fee_decimal'):
   if raw[key]!=s[key]:abort('realized_tax_plugin_output_invalid')
  if raw['tax_year']!=int(raw['local_date'][:4]) or raw['projection_status'] not in {'completed','blocked'}:abort('realized_tax_plugin_output_invalid')
  if raw['projection_status']=='blocked':
   if raw['failure_code'] not in {'tax_classification_required','tax_classification_invalid','tax_holding_evidence_required','tax_rate_required'} or any(raw[k] is not None for k in ('taxable_contribution_decimal','projected_event_tax_decimal','projected_net_gain_decimal','projected_net_proceeds_decimal')):abort('realized_tax_plugin_output_invalid')
  else:
   if raw['failure_code'] is not None or not all(isinstance(raw[k],str) for k in ('classification_code','tax_bucket')):abort('realized_tax_plugin_output_invalid')
   for k in ('taxable_contribution_decimal','projected_event_tax_decimal','projected_net_gain_decimal','projected_net_proceeds_decimal'):decimal(raw[k])
   economic_gain=d(raw['realized_gross_gain_decimal'])+d(raw['gross_income_decimal']);economic_proceeds=d(raw['gross_proceeds_decimal'])+d(raw['gross_income_decimal'])
   if d(raw['projected_event_tax_decimal'])<0 or d(raw['projected_net_gain_decimal'])!=economic_gain-d(raw['projected_event_tax_decimal']) or d(raw['projected_net_proceeds_decimal'])!=economic_proceeds-d(raw['projected_event_tax_decimal']):abort('realized_tax_reconciliation_failed')
  rows.append(dict(raw))
 if observed!=set(source):abort('realized_tax_plugin_output_invalid')
 return rows
def validate_annual_tax_candidate_v1(result,bound_input,selection,tax_year):
 with localcontext() as c:
  c.prec=200
  return _validate_annual_tax_candidate_v1_exact(result,bound_input,selection,tax_year)
def _validate_annual_tax_candidate_v1_exact(result,bound_input,selection,tax_year):
 if not isinstance(result,TaxPluginRunResult) or result.projection_mode!='realized_annual' or result.input_fingerprint!=bound_input['input_fingerprint']:abort('realized_tax_plugin_output_invalid')
 rows=[];summary=0;summary_row=None;buckets=[]
 economic_gain=sum((d(row['realized_gross_gain_decimal'])+d(row['gross_income_decimal']) for row in bound_input['rows']),Decimal(0))
 for raw in result.rows:
  if set(raw)!=set(ANNUAL_FIELDS) or raw['tax_year']!=tax_year or raw['row_type'] not in {'bucket','summary'} or raw['projection_status'] not in {'completed','blocked'}:abort('realized_tax_plugin_output_invalid')
  _validate_identity(raw,result,selection)
  for key in ANNUAL_FIELDS:
   if key.endswith('_decimal') and key not in {'projected_annual_tax_decimal','projected_net_gain_decimal'}:decimal(raw[key])
  positive=d(raw['positive_contribution_decimal']);negative=d(raw['negative_contribution_decimal']);net=d(raw['net_contribution_decimal'])
  if positive<0 or negative>0 or net!=positive+negative:abort('realized_tax_reconciliation_failed')
  if raw['row_type']=='summary':summary+=1;summary_row=raw
  else:buckets.append(raw)
  if raw['projection_status']=='blocked':
   if raw['failure_code'] not in {'tax_rate_required','tax_currency_conflict'} or raw['projected_annual_tax_decimal'] is not None or raw['projected_net_gain_decimal'] is not None:abort('realized_tax_plugin_output_invalid')
  else:
   if raw['failure_code'] is not None:abort('realized_tax_plugin_output_invalid')
   decimal(raw['projected_annual_tax_decimal']);decimal(raw['projected_net_gain_decimal'])
   if d(raw['projected_annual_tax_decimal'])<0:abort('realized_tax_reconciliation_failed')
  if not isinstance(raw['defaulted_parameter_codes'],str):abort('realized_tax_plugin_output_invalid')
  rows.append(dict(raw))
 if summary!=1:abort('realized_tax_plugin_output_invalid')
 for key in ('positive_contribution_decimal','negative_contribution_decimal','net_contribution_decimal'):
  if d(summary_row[key])!=sum((d(row[key]) for row in buckets),Decimal(0)):abort('realized_tax_reconciliation_failed')
 if summary_row['projection_status']=='completed' and d(summary_row['projected_net_gain_decimal'])!=economic_gain-d(summary_row['projected_annual_tax_decimal']):abort('realized_tax_reconciliation_failed')
 return rows
def _current_job(con,job_ref):
 row=con.execute('SELECT job.*,state.job_state_id,state.state_sequence,state.status FROM tax_projection_job job JOIN current_tax_projection_job_state state USING(job_id) WHERE job.job_ref=?',(job_ref,)).fetchone()
 if row is None:abort('realized_tax_job_missing')
 return row
def _state(con,row,status,at,failure=None,artifact=None):
 seq=row['state_sequence']+1;con.execute('INSERT INTO tax_projection_job_state VALUES (?,?,?,?,?,?,?,?)',(ident('tjs',[row['job_ref'],seq,status]),row['job_id'],seq,status,failure,artifact,row['job_state_id'],at))
def _latest(con,portfolio,mode,year):
 return con.execute('SELECT artifact.*,base.artifact_ref AS base_artifact_ref FROM tax_projection_artifact artifact LEFT JOIN tax_projection_artifact base ON base.artifact_id=artifact.base_artifact_id WHERE artifact.portfolio_ref=? AND artifact.projection_mode=? AND artifact.tax_year IS ? ORDER BY artifact.completed_at_utc DESC,artifact.artifact_ref DESC LIMIT 1',(portfolio,mode,year)).fetchone()
def _rows(con,artifact_id):return [json.loads(r[0]) for r in con.execute('SELECT blob.row_json FROM tax_projection_artifact_row link JOIN tax_projection_row_blob blob USING(row_blob_id) WHERE link.artifact_id=? ORDER BY link.row_ordinal',(artifact_id,))]
def publish_tax_projection_v1(store,ctx,*,job_ref,result,bound_input,selection,rebuild_mode,completed_at_utc,failpoint=None):
 if rebuild_mode not in {'full','incremental'} or failpoint not in {None,'after_artifact','after_rows'}:abort('realized_tax_input_invalid')
 completed=utc(completed_at_utc);con=connect(store,ctx)
 try:
  job=_current_job(con,job_ref)
  if job['status']!='pending':abort('realized_tax_job_not_pending')
  if result.projection_mode!=job['projection_mode'] or bound_input['source_artifact_ref']!=job['source_artifact_ref']:abort('realized_tax_job_candidate_mismatch')
  if job['projection_mode']=='realized_event':candidate=validate_event_tax_candidate_v1(result,bound_input,selection)
  else:candidate=validate_annual_tax_candidate_v1(result,bound_input,selection,job['tax_year'])
  previous=_latest(con,job['portfolio_ref'],job['projection_mode'],job['tax_year'])
  if rebuild_mode=='incremental' and previous is None:abort('realized_tax_full_rebuild_required')
  if rebuild_mode=='incremental' and job['projection_mode']=='realized_event':
   old={r['event_ref']:r for r in _rows(con,previous['artifact_id']) if r['effective_at_utc'] is not None and r['effective_at_utc']<job['invalidated_from']};new={r['event_ref']:r for r in candidate if r['effective_at_utc'] is not None and r['effective_at_utc']<job['invalidated_from']}
   if old!=new:abort('realized_tax_incremental_prefix_mismatch')
  con.execute('BEGIN IMMEDIATE');_state(con,job,'running',completed);con.commit();running=_current_job(con,job_ref)
  artifact_ref=ident('tar',{'job_ref':job_ref,'output':result.output_fingerprint,'mode':job['projection_mode']});artifact_id=ident('tai',artifact_ref);row_fps=[sha({'mode':job['projection_mode'],'row':r}) for r in candidate];row_set=sha(row_fps);readiness='partial_blocked' if any(r['projection_status']=='blocked' for r in candidate) else 'complete'
  try:
   semantic_bindings,semantic_fingerprint=_semantic(bound_input.get('semantic_source_bindings'),bound_input.get('semantic_binding_fingerprint'),'realized_tax_job_candidate_mismatch')
   con.execute('BEGIN IMMEDIATE');con.execute('INSERT INTO tax_projection_artifact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(artifact_id,artifact_ref,job['portfolio_ref'],job['projection_mode'],job['tax_year'],job['source_artifact_ref'],result.plugin_id,result.plugin_version,result.rules_fingerprint,selection.selection_ref,result.input_fingerprint,result.output_fingerprint,rebuild_mode,previous['artifact_id'] if rebuild_mode=='incremental' else None,job['job_id'],row_set,canonical(semantic_bindings),semantic_fingerprint,readiness,'model_projection_not_legal_advice',completed))
   if failpoint=='after_artifact':raise RuntimeError('synthetic')
   for i,(row,fp) in enumerate(zip(candidate,row_fps),1):
    blob=ident('trb',fp);con.execute('INSERT OR IGNORE INTO tax_projection_row_blob VALUES (?,?,?,?,?)',(blob,fp,job['projection_mode'],canonical(row),completed));con.execute('INSERT INTO tax_projection_artifact_row VALUES (?,?,?)',(artifact_id,i,blob))
   if failpoint=='after_rows':raise RuntimeError('synthetic')
   _state(con,running,'completed',completed,artifact=artifact_id);con.commit()
  except Exception as e:
   con.rollback();current=_current_job(con,job_ref);con.execute('BEGIN IMMEDIATE');_state(con,current,'failed',completed,'realized_tax_publication_failed');con.commit();raise RealizedTaxBlocked('realized_tax_publication_failed') from e
  return TaxProjectionArtifact(artifact_ref,job['portfolio_ref'],job['projection_mode'],job['tax_year'],job['source_artifact_ref'],result.plugin_id,result.plugin_version,result.rules_fingerprint,selection.selection_ref,readiness,row_set)
 finally:con.close()
def read_latest_tax_projection_v1(store,ctx,portfolio_ref,projection_mode,tax_year=None):
 ref(portfolio_ref,'pfr_');con=connect(store,ctx,True)
 try:
  artifact=_latest(con,portfolio_ref,projection_mode,tax_year);jobs=con.execute('SELECT job.job_ref,job.source_artifact_ref,job.invalidation_reason,state.status,state.failure_code,job.created_at_utc FROM tax_projection_job job JOIN current_tax_projection_job_state state USING(job_id) WHERE job.portfolio_ref=? AND job.projection_mode=? AND job.tax_year IS ? ORDER BY job.created_at_utc',(portfolio_ref,projection_mode,tax_year)).fetchall();stale=[dict(x) for x in jobs if x['status']!='completed' and (artifact is None or x['created_at_utc']>=artifact['completed_at_utc'])]
  if artifact is None:return {'contract_version':1,'status':'pending' if stale else 'empty','artifact':None,'rows':None,'stale_jobs':stale}
  public={k:artifact[k] for k in ('artifact_ref','portfolio_ref','projection_mode','tax_year','source_artifact_ref','plugin_id','plugin_version','rules_fingerprint','selection_ref','plugin_input_fingerprint','plugin_output_fingerprint','rebuild_mode','base_artifact_ref','row_set_fingerprint','readiness_status','disclaimer_code','completed_at_utc')}
  try:semantic_bindings=json.loads(artifact['semantic_source_bindings_json'])
  except (TypeError,json.JSONDecodeError) as e:raise RealizedTaxBlocked('realized_tax_event_not_completed') from e
  semantic_bindings,semantic_fingerprint=_semantic(semantic_bindings,artifact['semantic_binding_fingerprint'],'realized_tax_event_not_completed');public['semantic_source_bindings']=semantic_bindings;public['semantic_binding_fingerprint']=semantic_fingerprint
  return {'contract_version':1,'status':'stale' if stale else 'completed','artifact':public,'rows':_rows(con,artifact['artifact_id']),'stale_jobs':stale}
 finally:con.close()
def publish_tax_evidence_v1(read_model,output_path,context_binding_fingerprint):
 if not isinstance(read_model,dict) or read_model.get('status')!='completed' or not isinstance(context_binding_fingerprint,str) or not re.fullmatch(r'[a-f0-9]{64}',context_binding_fingerprint):abort('realized_tax_not_completed')
 mode=read_model['artifact']['projection_mode'];fields=EVENT_FIELDS if mode=='realized_event' else ANNUAL_FIELDS;name='event-tax-results.csv' if mode=='realized_event' else 'annual-tax-results.csv';profile='realized_event_tax_v1' if mode=='realized_event' else 'realized_annual_tax_v1';target=Path(output_path)
 if target.exists() or target.is_symlink() or target.parent.is_symlink() or not target.parent.is_dir():abort('realized_tax_evidence_target_invalid')
 target.mkdir(mode=0o700);csv_path=target/name
 try:
  with csv_path.open('w',encoding='utf-8',newline='') as h:
   w=csv.DictWriter(h,fieldnames=fields,lineterminator='\n',extrasaction='raise');w.writeheader();w.writerows(read_model['rows'])
  os.chmod(csv_path,0o600);payload=csv_path.read_bytes();artifact=read_model['artifact'];body={'calculation_evidence_version':1,'profile_id':profile,'status':'completed','algorithm_version':profile+'.0.0','portfolio_ref':artifact['portfolio_ref'],'context_binding_fingerprint':context_binding_fingerprint,'input_fingerprint':artifact['plugin_input_fingerprint'],'evidence_cutoff_at_utc':artifact['completed_at_utc'],'files':[{'file_name':name,'content_role':profile+'_results','row_count':len(read_model['rows']),'sha256':sha(payload)}],'reconciliation':{'persistent_row_count':len(read_model['rows']),'csv_equals_persistent_rows':True,'readiness_status':artifact['readiness_status']},'boundaries':{'canonical_write':False,'provider_access':False,'network_access':False,'app_side_calculation':False,'tax_calculation':True,'market_calculation':False,'automatic_retry':False,'grouping_dependency':False}}
  body['artifact_fingerprint']=sha((canonical(body)+'\n').encode());mp=target/'evidence-manifest.json';mp.write_text(canonical(body)+'\n',encoding='utf-8');os.chmod(mp,0o600);return body
 except Exception:
  import shutil;shutil.rmtree(target,ignore_errors=True);raise
