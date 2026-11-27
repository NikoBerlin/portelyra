#!/usr/bin/env python3
"""Completed native-currency Realized Group Projection v1."""
from __future__ import annotations
import csv,hashlib,json,os,re,shutil,sqlite3
from dataclasses import dataclass
from decimal import Decimal,localcontext
from pathlib import Path
from typing import Any,Mapping
ROOT=Path(__file__).resolve().parents[2];SCHEMA=ROOT/'contracts'/'realized-group-projection'/'v1'/'schema.sql';TABLES=('group-metrics.csv','group-drilldown.csv','group-reconciliation.csv','group-annual-tax.csv');UTC=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$');DECIMAL_FIELDS=('remaining_fifo_cost_decimal','realized_gross_proceeds_decimal','realized_gross_gain_decimal','gross_income_decimal','fee_total_decimal','cash_balance_decimal')
class GroupProjectionBlocked(ValueError):
 def __init__(self,code):super().__init__(code);self.code=code
@dataclass(frozen=True)
class GroupProjectionContext:tenant_id:str;user_id:str;data_space_id:str;actor_id:str
@dataclass(frozen=True)
class GroupProjectionJob:job_ref:str;fifo_portfolio_ref:str;grouping_portfolio_ref:str;scheme_ref:str|None;grouping_revision_fingerprint:str;fifo_artifact_ref:str
@dataclass(frozen=True)
class GroupProjectionArtifact:artifact_ref:str;fifo_portfolio_ref:str;grouping_portfolio_ref:str;scheme_ref:str|None;scheme_type:str;grouping_revision_fingerprint:str;fifo_artifact_ref:str;event_tax_artifact_ref:str|None;annual_tax_artifact_ref:str|None;row_set_fingerprint:str;coverage_status:str;currency_status:str

def abort(code):raise GroupProjectionBlocked(code)
def canonical(v):return json.dumps(v,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':'))
def sha(v):
 p=v if isinstance(v,bytes) else (v.encode() if isinstance(v,str) else canonical(v).encode());return hashlib.sha256(p).hexdigest()
def ident(prefix,v):return f'{prefix}_{sha(v)[:32]}'
def context(v):
 if isinstance(v,Mapping):
  try:v=GroupProjectionContext(*(v[k] for k in ('tenant_id','user_id','data_space_id','actor_id')))
  except (KeyError,TypeError) as e:raise GroupProjectionBlocked('group_projection_context_invalid') from e
 if not isinstance(v,GroupProjectionContext):abort('group_projection_context_invalid')
 for i,x in enumerate((v.tenant_id,v.user_id,v.data_space_id,v.actor_id)):
  if not isinstance(x,str) or not 3<=len(x)<=(80 if i==3 else 64) or re.search(r'[\x00-\x1f\x7f]',x):abort('group_projection_context_invalid')
 return v
def context_fp(v):
 c=context(v);return sha({'contract_version':'realized_group_projection_v1','tenant_id':c.tenant_id,'user_id':c.user_id,'data_space_id':c.data_space_id})
def utc(v):
 if not isinstance(v,str) or not UTC.fullmatch(v):abort('group_projection_input_invalid')
 return v
def ref(v,prefix=None,nullable=False):
 if v is None and nullable:return None
 if not isinstance(v,str) or not re.fullmatch(r'[a-z][a-z0-9]{2}_[a-f0-9]{24,32}',v) or prefix and not v.startswith(prefix):abort('group_projection_input_invalid')
 return v
def d(v):
 if v in ('',None):v='0'
 if not isinstance(v,str) or not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?',v):abort('group_projection_decimal_invalid')
 with localcontext() as c:c.prec=200;return Decimal(v)
def text(v):
 if not isinstance(v,Decimal):v=d(v)
 if v==0:return '0'
 rendered=format(v,'f').rstrip('0').rstrip('.') if '.' in format(v,'f') else format(v,'f')
 return rendered
def bootstrap_group_projection_store_v1(path,ctx,created_at_utc):
 c=context(ctx);created=utc(created_at_utc);target=Path(path)
 if target.exists() or target.is_symlink():abort('group_projection_store_exists')
 try:target=target.parent.resolve(strict=True)/target.name
 except OSError as e:raise GroupProjectionBlocked('group_projection_store_invalid') from e
 con=sqlite3.connect(target)
 try:con.executescript(SCHEMA.read_text());con.execute('INSERT INTO group_projection_store_binding VALUES (1,2100,?,?)',(context_fp(c),created));con.commit()
 except Exception:con.close();target.unlink(missing_ok=True);raise
 finally:
  try:con.close()
  except:pass
 os.chmod(target,0o600);return target
def connect(path,ctx,ro=False):
 c=context(ctx);p=Path(path)
 if p.is_symlink() or not p.is_file():abort('group_projection_store_invalid')
 try:
  con=sqlite3.connect(f'{p.resolve(strict=True).as_uri()}?mode=ro&immutable=1',uri=True) if ro else sqlite3.connect(p.resolve(strict=True),isolation_level=None);con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
  if ro:con.execute('PRAGMA query_only=ON')
  b=con.execute('SELECT context_binding_fingerprint FROM group_projection_store_binding WHERE singleton_id=1').fetchone()
  if con.execute('PRAGMA user_version').fetchone()[0]!=2100 or b is None or b[0]!=context_fp(c):con.close();abort('group_projection_context_mismatch')
  return con
 except GroupProjectionBlocked:raise
 except sqlite3.Error as e:raise GroupProjectionBlocked('group_projection_store_invalid') from e
def _bridge_maps(bridge):
 if not isinstance(bridge,dict) or bridge.get('contract_version')!='asset_grouping_identity_bridge_v1' or sha({k:v for k,v in bridge.items() if k!='bridge_fingerprint'})!=bridge.get('bridge_fingerprint'):abort('group_projection_identity_bridge_invalid')
 p={r['fifo_portfolio_ref']:r['grouping_portfolio_ref'] for r in bridge['portfolio_refs']};a={r['fifo_asset_ref']:r['grouping_asset_ref'] for r in bridge['asset_refs']};return p,a
def _semantic(value,fingerprint):
 required={'semantic_contract','source_event_count','projected_event_count','coupled_transaction_fact','automatic_cash_posting_state'}
 if not isinstance(value,list) or not value:abort('group_projection_fifo_not_completed')
 bindings=[];contracts=set()
 for row in value:
  if not isinstance(row,dict) or set(row)!=required or row['semantic_contract'] in contracts or row['semantic_contract'] not in {'portfolio_ledger_v1_transaction_fact','asset_activity_v1'}:abort('group_projection_fifo_not_completed')
  if not all(isinstance(row[key],int) and not isinstance(row[key],bool) and row[key]>=0 for key in ('source_event_count','projected_event_count')) or row['projected_event_count']>row['source_event_count']:abort('group_projection_fifo_not_completed')
  valid=(row['semantic_contract']=='portfolio_ledger_v1_transaction_fact' and row['coupled_transaction_fact'] is True and row['automatic_cash_posting_state']=='unknown') or (row['semantic_contract']=='asset_activity_v1' and row['coupled_transaction_fact'] is False and row['automatic_cash_posting_state']=='none_created')
  if not valid:abort('group_projection_fifo_not_completed')
  contracts.add(row['semantic_contract']);bindings.append(dict(row))
 if not isinstance(fingerprint,str) or not re.fullmatch(r'[a-f0-9]{64}',fingerprint) or fingerprint!=sha(bindings):abort('group_projection_fifo_not_completed')
 return bindings,fingerprint
def _selection(grouping_catalog,scheme_ref):
 if not isinstance(grouping_catalog,dict) or grouping_catalog.get('status')!='completed':abort('group_projection_grouping_invalid')
 if scheme_ref is None:return None
 matches=[s for s in grouping_catalog.get('schemes',[]) if s['scheme_ref']==scheme_ref]
 if len(matches)!=1:abort('group_projection_scheme_missing')
 return matches[0]
def _revision_fingerprint(catalog,scheme):
 if scheme is None:return sha({'catalog_fingerprint':catalog['catalog_fingerprint'],'scheme_ref':None,'portfolio_assets':catalog['portfolio_asset_refs']})
 return sha({'scheme':{k:scheme[k] for k in ('scheme_ref','scheme_type','revision_token','effective_from','status')},'groups':[{k:g[k] for k in ('group_ref','parent_group_ref','revision_token','status')} for g in scheme['groups']],'memberships':[{k:m[k] for k in ('membership_ref','asset_ref','group_ref','membership_mode','revision_token','status','effective_from','effective_to')} for m in scheme['memberships']],'unassigned_asset_refs':scheme['unassigned_asset_refs']})
def _targets(group_asset,nodes,scheme,root_ref,unassigned_ref):
 if scheme is None:return [root_ref]
 memberships=[m for m in scheme['memberships'] if m['asset_ref']==group_asset]
 if scheme['scheme_type']=='tag_set':return [root_ref]+sorted({m['group_ref'] for m in memberships})
 if not memberships:return [root_ref,unassigned_ref]
 leaf=memberships[0]['group_ref'];targets=[root_ref,leaf];parents={g['group_ref']:g['parent_group_ref'] for g in scheme['groups']};cursor=parents.get(leaf)
 while cursor is not None:targets.append(cursor);cursor=parents.get(cursor)
 return targets
def build_realized_group_candidate_v1(realized_read_model,grouping_catalog,scheme_ref,identity_bridge,event_tax_read_model=None,annual_tax_read_model=None):
 if not isinstance(realized_read_model,dict) or realized_read_model.get('status')!='completed' or not isinstance(realized_read_model.get('artifact'),dict):abort('group_projection_fifo_not_completed')
 portfolio_map,asset_map=_bridge_maps(identity_bridge);fifo_portfolio=realized_read_model['artifact']['portfolio_ref'];grouping_portfolio=portfolio_map.get(fifo_portfolio)
 if grouping_portfolio is None or grouping_catalog.get('portfolio_ref')!=grouping_portfolio:abort('group_projection_identity_bridge_invalid')
 scheme=_selection(grouping_catalog,scheme_ref);scheme_type='none' if scheme is None else scheme['scheme_type'];revision_fp=_revision_fingerprint(grouping_catalog,scheme)
 root_ref=ident('xrt',{'portfolio_ref':grouping_portfolio,'scheme_ref':scheme_ref});unassigned_ref=ident('xun',{'portfolio_ref':grouping_portfolio,'scheme_ref':scheme_ref})
 nodes={root_ref:{'node_kind':'portfolio_root','parent_node_ref':None,'display_name':'Portfolio','group_ref':None}}
 if scheme:
  root_ref=scheme['portfolio_root_ref'];nodes={root_ref:{'node_kind':'portfolio_root','parent_node_ref':None,'display_name':'Portfolio','group_ref':None}}
  for g in scheme['groups']:nodes[g['group_ref']]={'node_kind':'group','parent_node_ref':g['parent_group_ref'] or root_ref,'display_name':g['display_name'],'group_ref':g['group_ref']}
  if scheme_type=='exclusive_hierarchy' and scheme['unassigned_asset_refs']:nodes[unassigned_ref]={'node_kind':'unassigned','parent_node_ref':root_ref,'display_name':'unassigned','group_ref':None}
 metrics={};asset_sets={};position_sets={};drill=[]
 def ensure(node,currency):
  key=(node,currency)
  if key not in metrics:metrics[key]={field:Decimal(0) for field in DECIMAL_FIELDS};asset_sets[key]=set();position_sets[key]=set()
  return key
 positions=realized_read_model['tables']['position-summary.csv']
 for row in positions:
  group_asset=asset_map.get(row['asset_ref'])
  if group_asset is None:abort('group_projection_identity_bridge_invalid')
  targets=_targets(group_asset,nodes,scheme,root_ref,unassigned_ref)
  for node in targets:
   key=ensure(node,row['currency']);asset_sets[key].add(row['asset_ref']);position_sets[key].add(row['position_ref'])
   for field in DECIMAL_FIELDS:metrics[key][field]+=d(row[field])
   drill.append({'node_ref':node,'source_kind':'position','source_ref':row['position_ref'],'asset_ref':row['asset_ref'],'account_ref':row['account_ref'],'event_ref':None,'currency':row['currency'],'remaining_fifo_cost_decimal':text(d(row['remaining_fifo_cost_decimal'])),'realized_gross_gain_decimal':text(d(row['realized_gross_gain_decimal'])),'projected_event_tax_decimal':None,'projected_net_gain_decimal':None})
 event_by_ref={row['event_ref']:row for row in realized_read_model['tables']['event-results.csv']}
 event_tax_rows=None;event_tax_artifact=None
 if event_tax_read_model is not None:
  if (event_tax_read_model.get('status')!='completed' or event_tax_read_model['artifact']['source_artifact_ref']!=realized_read_model['artifact']['artifact_ref'] or
      event_tax_read_model['artifact'].get('semantic_binding_fingerprint')!=realized_read_model['artifact'].get('semantic_binding_fingerprint') or
      event_tax_read_model['artifact'].get('semantic_source_bindings')!=realized_read_model['artifact'].get('semantic_source_bindings')):abort('group_projection_tax_incompatible')
  event_tax_rows={row['event_ref']:row for row in event_tax_read_model['rows']};event_tax_artifact=event_tax_read_model['artifact']['artifact_ref']
 tax_metrics={}
 for event_ref,event in event_by_ref.items():
  group_asset=asset_map.get(event['asset_ref']);targets=_targets(group_asset,nodes,scheme,root_ref,unassigned_ref)
  taxrow=event_tax_rows.get(event_ref) if event_tax_rows else None
  for node in targets:
   key=(node,event['currency']);tax_metrics.setdefault(key,{'tax':Decimal(0),'net':Decimal(0),'status':'completed' if event_tax_rows else 'unavailable'})
   projected_tax=projected_net=None
   if taxrow and taxrow['projection_status']=='completed':tax_metrics[key]['tax']+=d(taxrow['projected_event_tax_decimal']);tax_metrics[key]['net']+=d(taxrow['projected_net_gain_decimal']);projected_tax=taxrow['projected_event_tax_decimal'];projected_net=taxrow['projected_net_gain_decimal']
   elif event_tax_rows:tax_metrics[key]['status']='partial_blocked'
   drill.append({'node_ref':node,'source_kind':'event','source_ref':event_ref,'asset_ref':event['asset_ref'],'account_ref':event['account_ref'],'event_ref':event_ref,'currency':event['currency'],'remaining_fifo_cost_decimal':None,'realized_gross_gain_decimal':event['realized_gross_gain_decimal'],'projected_event_tax_decimal':projected_tax,'projected_net_gain_decimal':projected_net})
 rows=[];currencies_by_node={node:sorted({currency for candidate,currency in metrics if candidate==node}) for node in nodes}
 for node in sorted(nodes,key=lambda x:(nodes[x]['node_kind']!='portfolio_root',nodes[x]['display_name'],x)):
  currencies=currencies_by_node[node]
  if not currencies:
   rows.append({'node_ref':node,'node_kind':nodes[node]['node_kind'],'parent_node_ref':nodes[node]['parent_node_ref'],'display_name':nodes[node]['display_name'],'scheme_ref':scheme_ref,'scheme_type':scheme_type,'currency':None,'asset_count':0,'position_count':0,**{field:'0' for field in DECIMAL_FIELDS},'event_tax_status':'unavailable' if event_tax_rows is None else 'completed','projected_event_tax_decimal':None if event_tax_rows is None else '0','projected_net_gain_decimal':None if event_tax_rows is None else '0','annual_tax_status':'unavailable','currency_aggregation_status':'empty','coverage_status':'not_applicable'})
  for currency in currencies:
   key=(node,currency);tm=tax_metrics.get(key,{'status':'unavailable','tax':Decimal(0),'net':Decimal(0)})
   rows.append({'node_ref':node,'node_kind':nodes[node]['node_kind'],'parent_node_ref':nodes[node]['parent_node_ref'],'display_name':nodes[node]['display_name'],'scheme_ref':scheme_ref,'scheme_type':scheme_type,'currency':currency,'asset_count':len(asset_sets[key]),'position_count':len(position_sets[key]),**{field:text(metrics[key][field]) for field in DECIMAL_FIELDS},'event_tax_status':tm['status'],'projected_event_tax_decimal':text(tm['tax']) if event_tax_rows is not None else None,'projected_net_gain_decimal':text(tm['net']) if event_tax_rows is not None else None,'annual_tax_status':('portfolio_root_only' if nodes[node]['node_kind']=='portfolio_root' else 'group_contribution_only') if annual_tax_read_model else 'unavailable','currency_aggregation_status':'conversion_unavailable' if len(currencies)>1 else 'native_currency','coverage_status':'unassigned' if nodes[node]['node_kind']=='unassigned' else 'complete'})
 reconciliation=[]
 if scheme_type=='tag_set':reconciliation=[{'parent_node_ref':root_ref,'currency':None,'metric_code':'all_metrics','parent_decimal':None,'child_decimal':None,'reconciliation_status':'nonadditive_tag_filter'}]
 else:
  children={node:[] for node in nodes}
  for node,value in nodes.items():
   if value['parent_node_ref'] in children:children[value['parent_node_ref']].append(node)
  for parent,child_nodes in children.items():
   if not child_nodes:continue
   currencies=sorted({r['currency'] for r in rows if r['node_ref']==parent and r['currency'] is not None})
   for currency in currencies:
    parent_row=next(r for r in rows if r['node_ref']==parent and r['currency']==currency)
    for field in DECIMAL_FIELDS:
     child_sum=sum((d(r[field]) for r in rows if r['node_ref'] in child_nodes and r['currency']==currency),Decimal(0));status='reconciled' if d(parent_row[field])==child_sum else 'mismatch'
     if status!='reconciled':abort('group_projection_reconciliation_failed')
     reconciliation.append({'parent_node_ref':parent,'currency':currency,'metric_code':field.removesuffix('_decimal'),'parent_decimal':parent_row[field],'child_decimal':text(child_sum),'reconciliation_status':status})
 annual_rows=[];annual_artifact=None
 if annual_tax_read_model is not None:
  if (annual_tax_read_model.get('status')!='completed' or event_tax_artifact is None or annual_tax_read_model['artifact']['source_artifact_ref']!=event_tax_artifact or
      annual_tax_read_model['artifact'].get('semantic_binding_fingerprint')!=realized_read_model['artifact'].get('semantic_binding_fingerprint') or
      annual_tax_read_model['artifact'].get('semantic_source_bindings')!=realized_read_model['artifact'].get('semantic_source_bindings')):abort('group_projection_tax_incompatible')
  annual_artifact=annual_tax_read_model['artifact']['artifact_ref']
  for row in annual_tax_read_model['rows']:
   if row['row_type']=='summary':annual_rows.append({'node_ref':root_ref,'tax_year':row['tax_year'],'tax_bucket':'all','currency':row['currency'],'taxable_contribution_decimal':row['net_contribution_decimal'],'projected_annual_tax_decimal':row['projected_annual_tax_decimal'],'annual_tax_scope':'portfolio_root','projection_status':row['projection_status']})
  if event_tax_rows:
   grouped={}
   for taxrow in event_tax_rows.values():
    if taxrow['projection_status']!='completed':continue
    event=event_by_ref[taxrow['event_ref']];group_asset=asset_map[event['asset_ref']]
    for node in _targets(group_asset,nodes,scheme,root_ref,unassigned_ref):
     if node==root_ref:continue
     key=(node,taxrow['tax_year'],taxrow['tax_bucket'],taxrow['currency']);grouped[key]=grouped.get(key,Decimal(0))+d(taxrow['taxable_contribution_decimal'])
   for key,value in sorted(grouped.items()):annual_rows.append({'node_ref':key[0],'tax_year':key[1],'tax_bucket':key[2],'currency':key[3],'taxable_contribution_decimal':text(value),'projected_annual_tax_decimal':None,'annual_tax_scope':'group_contribution_only','projection_status':'completed'})
 coverage='not_applicable' if scheme_type in {'none','tag_set'} else ('unassigned' if scheme['unassigned_asset_refs'] else 'complete');root_currencies=currencies_by_node[root_ref];currency_status='empty' if not root_currencies else ('single_currency' if len(root_currencies)==1 else 'native_currency_slices')
 tables={'group-metrics.csv':rows,'group-drilldown.csv':sorted(drill,key=lambda r:(r['node_ref'],r['source_kind'],r['source_ref'])),'group-reconciliation.csv':reconciliation,'group-annual-tax.csv':annual_rows}
 semantic_bindings,semantic_fingerprint=_semantic(realized_read_model['artifact'].get('semantic_source_bindings'),realized_read_model['artifact'].get('semantic_binding_fingerprint'))
 return {'contract_version':1,'algorithm_version':'realized_group_projection_v1.0.0','fifo_portfolio_ref':fifo_portfolio,'grouping_portfolio_ref':grouping_portfolio,'scheme_ref':scheme_ref,'scheme_type':scheme_type,'grouping_revision_fingerprint':revision_fp,'fifo_artifact_ref':realized_read_model['artifact']['artifact_ref'],'event_tax_artifact_ref':event_tax_artifact,'annual_tax_artifact_ref':annual_artifact,'coverage_status':coverage,'currency_status':currency_status,'semantic_source_bindings':semantic_bindings,'semantic_binding_fingerprint':semantic_fingerprint,'tables':tables,'row_set_fingerprint':sha([{ 'table':name,'rows':tables[name]} for name in TABLES])}
def schedule_group_projection_v1(store,ctx,*,request_ref,candidate,invalidated_by,created_at_utc):
 if not re.fullmatch(r'req_[a-f0-9]{24,32}',str(request_ref)) or invalidated_by not in {'initial','fifo','grouping','event_tax','annual_tax'} or not isinstance(candidate,dict):abort('group_projection_input_invalid')
 created=utc(created_at_utc);payload={'context':context_fp(ctx),'request_ref':request_ref,'candidate':{k:candidate[k] for k in ('fifo_portfolio_ref','grouping_portfolio_ref','scheme_ref','grouping_revision_fingerprint','fifo_artifact_ref','event_tax_artifact_ref','annual_tax_artifact_ref')},'invalidated_by':invalidated_by};job_ref=ident('gjb',payload);job_id=ident('gpj',job_ref)
 con=connect(store,ctx)
 try:
  con.execute('BEGIN IMMEDIATE');con.execute('INSERT INTO group_projection_job VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(job_id,job_ref,request_ref,candidate['fifo_portfolio_ref'],candidate['grouping_portfolio_ref'],candidate['scheme_ref'],candidate['grouping_revision_fingerprint'],candidate['fifo_artifact_ref'],candidate['event_tax_artifact_ref'],candidate['annual_tax_artifact_ref'],invalidated_by,created));con.execute("INSERT INTO group_projection_job_state VALUES (?,?,1,'pending',NULL,NULL,NULL,?)",(ident('gjs',[job_ref,1]),job_id,created));con.commit()
 except sqlite3.IntegrityError as e:con.rollback();raise GroupProjectionBlocked('group_projection_job_conflict') from e
 finally:con.close()
 return GroupProjectionJob(job_ref,candidate['fifo_portfolio_ref'],candidate['grouping_portfolio_ref'],candidate['scheme_ref'],candidate['grouping_revision_fingerprint'],candidate['fifo_artifact_ref'])
def _job(con,job_ref):
 row=con.execute('SELECT job.*,state.job_state_id,state.state_sequence,state.status FROM group_projection_job job JOIN current_group_projection_job_state state USING(job_id) WHERE job.job_ref=?',(job_ref,)).fetchone()
 if row is None:abort('group_projection_job_missing')
 return row
def _state(con,row,status,at,failure=None,artifact=None):
 seq=row['state_sequence']+1;con.execute('INSERT INTO group_projection_job_state VALUES (?,?,?,?,?,?,?,?)',(ident('gjs',[row['job_ref'],seq,status]),row['job_id'],seq,status,failure,artifact,row['job_state_id'],at))
def _latest(con,fifo_portfolio,scheme_ref):return con.execute('SELECT artifact.*,base.artifact_ref AS base_artifact_ref FROM group_projection_artifact artifact LEFT JOIN group_projection_artifact base ON base.artifact_id=artifact.base_artifact_id WHERE artifact.fifo_portfolio_ref=? AND artifact.scheme_ref IS ? ORDER BY artifact.completed_at_utc DESC,artifact.artifact_ref DESC LIMIT 1',(fifo_portfolio,scheme_ref)).fetchone()
def _artifact_tables(con,artifact_id):
 out={name:[] for name in TABLES}
 for row in con.execute('SELECT link.table_name,blob.row_json FROM group_projection_artifact_row link JOIN group_projection_row_blob blob USING(row_blob_id) WHERE link.artifact_id=? ORDER BY link.table_name,link.row_ordinal',(artifact_id,)):out[row['table_name']].append(json.loads(row['row_json']))
 return out
def publish_group_projection_v1(store,ctx,*,job_ref,candidate,rebuild_mode,completed_at_utc,failpoint=None):
 if rebuild_mode not in {'full','incremental'} or failpoint not in {None,'after_artifact','after_rows'}:abort('group_projection_input_invalid')
 completed=utc(completed_at_utc);con=connect(store,ctx)
 try:
  job=_job(con,job_ref)
  if job['status']!='pending':abort('group_projection_job_not_pending')
  for field in ('fifo_portfolio_ref','grouping_portfolio_ref','scheme_ref','grouping_revision_fingerprint','fifo_artifact_ref','event_tax_artifact_ref','annual_tax_artifact_ref'):
   if candidate[field]!=job[field]:abort('group_projection_job_candidate_mismatch')
  previous=_latest(con,job['fifo_portfolio_ref'],job['scheme_ref'])
  if rebuild_mode=='incremental' and previous is None:abort('group_projection_full_rebuild_required')
  con.execute('BEGIN IMMEDIATE');_state(con,job,'running',completed);con.commit();running=_job(con,job_ref);artifact_ref=ident('gpr',{'job_ref':job_ref,'row_set':candidate['row_set_fingerprint']});artifact_id=ident('gpa',artifact_ref)
  try:
   semantic_bindings,semantic_fingerprint=_semantic(candidate.get('semantic_source_bindings'),candidate.get('semantic_binding_fingerprint'))
   con.execute('BEGIN IMMEDIATE');con.execute('INSERT INTO group_projection_artifact VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(artifact_id,artifact_ref,candidate['fifo_portfolio_ref'],candidate['grouping_portfolio_ref'],candidate['scheme_ref'],candidate['scheme_type'],candidate['grouping_revision_fingerprint'],candidate['fifo_artifact_ref'],candidate['event_tax_artifact_ref'],candidate['annual_tax_artifact_ref'],candidate['algorithm_version'],rebuild_mode,previous['artifact_id'] if rebuild_mode=='incremental' else None,job['job_id'],candidate['row_set_fingerprint'],canonical(semantic_bindings),semantic_fingerprint,candidate['coverage_status'],candidate['currency_status'],completed))
   if failpoint=='after_artifact':raise RuntimeError('synthetic')
   for table_name in TABLES:
    for ordinal,row in enumerate(candidate['tables'][table_name],1):
     fp=sha({'table_name':table_name,'row':row});blob=ident('grb',fp);con.execute('INSERT OR IGNORE INTO group_projection_row_blob VALUES (?,?,?,?,?)',(blob,fp,table_name,canonical(row),completed));con.execute('INSERT INTO group_projection_artifact_row VALUES (?,?,?,?)',(artifact_id,table_name,ordinal,blob))
   if failpoint=='after_rows':raise RuntimeError('synthetic')
   _state(con,running,'completed',completed,artifact=artifact_id);con.commit()
  except Exception as e:
   con.rollback();current=_job(con,job_ref);con.execute('BEGIN IMMEDIATE');_state(con,current,'failed',completed,'group_projection_publication_failed');con.commit();raise GroupProjectionBlocked('group_projection_publication_failed') from e
  return GroupProjectionArtifact(artifact_ref,candidate['fifo_portfolio_ref'],candidate['grouping_portfolio_ref'],candidate['scheme_ref'],candidate['scheme_type'],candidate['grouping_revision_fingerprint'],candidate['fifo_artifact_ref'],candidate['event_tax_artifact_ref'],candidate['annual_tax_artifact_ref'],candidate['row_set_fingerprint'],candidate['coverage_status'],candidate['currency_status'])
 finally:con.close()
def read_latest_group_projection_v1(store,ctx,fifo_portfolio_ref,scheme_ref=None):
 ref(fifo_portfolio_ref,'pfr_');ref(scheme_ref,'xgs_',True);con=connect(store,ctx,True)
 try:
  artifact=_latest(con,fifo_portfolio_ref,scheme_ref);jobs=con.execute('SELECT job.job_ref,job.invalidated_by,state.status,state.failure_code,job.created_at_utc FROM group_projection_job job JOIN current_group_projection_job_state state USING(job_id) WHERE job.fifo_portfolio_ref=? AND job.scheme_ref IS ? ORDER BY job.created_at_utc',(fifo_portfolio_ref,scheme_ref)).fetchall();stale=[dict(r) for r in jobs if r['status']!='completed' and (artifact is None or r['created_at_utc']>=artifact['completed_at_utc'])]
  if artifact is None:return {'contract_version':1,'status':'pending' if stale else 'empty','artifact':None,'tables':None,'stale_jobs':stale}
  public={k:artifact[k] for k in ('artifact_ref','fifo_portfolio_ref','grouping_portfolio_ref','scheme_ref','scheme_type','grouping_revision_fingerprint','fifo_artifact_ref','event_tax_artifact_ref','annual_tax_artifact_ref','algorithm_version','rebuild_mode','base_artifact_ref','row_set_fingerprint','coverage_status','currency_status','completed_at_utc')}
  tables=_artifact_tables(con,artifact['artifact_id'])
  try:semantic_bindings=json.loads(artifact['semantic_source_bindings_json'])
  except (TypeError,json.JSONDecodeError) as e:raise GroupProjectionBlocked('group_projection_fifo_not_completed') from e
  semantic_bindings,semantic_fingerprint=_semantic(semantic_bindings,artifact['semantic_binding_fingerprint']);public['semantic_source_bindings']=semantic_bindings;public['semantic_binding_fingerprint']=semantic_fingerprint
  return {'contract_version':1,'status':'stale' if stale else 'completed','artifact':public,'tables':tables,'stale_jobs':stale}
 finally:con.close()
def _csv_safe(value):
 if isinstance(value,str) and value.startswith(('=','+','-','@')) and not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?',value):return "'"+value
 return value
def publish_group_projection_evidence_v1(read_model,output_path,context_binding_fingerprint):
 if not isinstance(read_model,dict) or read_model.get('status')!='completed' or not re.fullmatch(r'[a-f0-9]{64}',str(context_binding_fingerprint)):abort('group_projection_not_completed')
 target=Path(output_path)
 if target.exists() or target.is_symlink() or target.parent.is_symlink() or not target.parent.is_dir():abort('group_projection_evidence_target_invalid')
 target.mkdir(mode=0o700);files=[]
 try:
  for name in TABLES:
   rows=read_model['tables'][name];headers=list(rows[0]) if rows else {'group-metrics.csv':['node_ref','node_kind','parent_node_ref','display_name','scheme_ref','scheme_type','currency','asset_count','position_count',*DECIMAL_FIELDS,'event_tax_status','projected_event_tax_decimal','projected_net_gain_decimal','annual_tax_status','currency_aggregation_status','coverage_status'],'group-drilldown.csv':['node_ref','source_kind','source_ref','asset_ref','account_ref','event_ref','currency','remaining_fifo_cost_decimal','realized_gross_gain_decimal','projected_event_tax_decimal','projected_net_gain_decimal'],'group-reconciliation.csv':['parent_node_ref','currency','metric_code','parent_decimal','child_decimal','reconciliation_status'],'group-annual-tax.csv':['node_ref','tax_year','tax_bucket','currency','taxable_contribution_decimal','projected_annual_tax_decimal','annual_tax_scope','projection_status']}[name]
   path=target/name
   with path.open('w',encoding='utf-8',newline='') as h:
    w=csv.DictWriter(h,fieldnames=headers,lineterminator='\n');w.writeheader();w.writerows([{k:_csv_safe(v) for k,v in row.items()} for row in rows])
   os.chmod(path,0o600);files.append({'file_name':name,'content_role':name[:-4].replace('-','_'),'row_count':len(rows),'sha256':sha(path.read_bytes())})
  a=read_model['artifact'];body={'calculation_evidence_version':1,'profile_id':'realized_group_projection_v1','status':'completed','algorithm_version':a['algorithm_version'],'portfolio_ref':a['fifo_portfolio_ref'],'context_binding_fingerprint':context_binding_fingerprint,'input_fingerprint':a['row_set_fingerprint'],'evidence_cutoff_at_utc':a['completed_at_utc'],'files':files,'reconciliation':{'group_row_count':len(read_model['tables']['group-metrics.csv']),'reconciliation_row_count':len(read_model['tables']['group-reconciliation.csv']),'coverage_status':a['coverage_status'],'currency_status':a['currency_status']},'boundaries':{'canonical_write':False,'provider_access':False,'network_access':False,'app_side_calculation':False,'tax_calculation':False,'market_calculation':False,'automatic_retry':False,'grouping_dependency':True}};body['artifact_fingerprint']=sha((canonical(body)+'\n').encode());mp=target/'evidence-manifest.json';mp.write_text(canonical(body)+'\n');os.chmod(mp,0o600);return body
 except Exception:shutil.rmtree(target,ignore_errors=True);raise
