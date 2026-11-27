#!/usr/bin/env python3
"""Allowlisted, context-bound and process-isolated Tax Model Plugin v1."""
from __future__ import annotations
import hashlib,json,os,re,shutil,signal,sqlite3,stat,subprocess,sys,tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any,Mapping,Sequence

ROOT=Path(__file__).resolve().parents[2]
PLUGIN_ROOT=ROOT/'plugins'/'tax_models'
SCHEMA=ROOT/'contracts'/'tax-model-plugin'/'v1'/'schema.sql'
SANDBOX=ROOT/'workers'/'tax_plugin_sandbox_v1.py'
MODES=frozenset({'realized_event','realized_annual','unrealized_snapshot'})
CAPABILITIES=frozenset({'read_bound_input','write_typed_output'})
UTC=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$')
DATE=re.compile(r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$')
DECIMAL=re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$')

class TaxPluginBlocked(ValueError):
 def __init__(self,code:str):super().__init__(code);self.code=code
@dataclass(frozen=True)
class TaxPluginContext:tenant_id:str;user_id:str;data_space_id:str;actor_id:str
@dataclass(frozen=True)
class TaxPluginManifest:
 plugin_id:str;plugin_version:str;jurisdiction_code:str;model_scope:str;supported_projection_modes:tuple[str,...];effective_from:str;effective_to:str|None;rules_fingerprint:str;manifest_fingerprint:str;entry_path:Path;disclaimer_codes:tuple[str,...];resource_fingerprints:tuple[tuple[str,str],...]
@dataclass(frozen=True)
class TaxPluginSelection:
 selection_ref:str;revision_no:int;revision_token:str;portfolio_ref:str;projection_mode:str;plugin_id:str;plugin_version:str;rules_fingerprint:str;manifest_fingerprint:str;effective_from:str;status:str
@dataclass(frozen=True)
class TaxPluginRunResult:
 run_ref:str;plugin_id:str;plugin_version:str;rules_fingerprint:str;projection_mode:str;input_fingerprint:str;output_fingerprint:str;rows:tuple[dict[str,Any],...];reconciliation:dict[str,Any];disclaimer_codes:tuple[str,...]

def abort(code):raise TaxPluginBlocked(code)
def canonical(value):return json.dumps(value,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':'))
def sha(value):
 if isinstance(value,bytes):payload=value
 elif isinstance(value,str):payload=value.encode()
 else:payload=canonical(value).encode()
 return hashlib.sha256(payload).hexdigest()
def internal(prefix,value):return f'{prefix}_{sha(value)[:32]}'
def normalize_context(value):
 if isinstance(value,Mapping):
  try:value=TaxPluginContext(*(value[k] for k in ('tenant_id','user_id','data_space_id','actor_id')))
  except (KeyError,TypeError) as e:raise TaxPluginBlocked('tax_plugin_context_invalid') from e
 if not isinstance(value,TaxPluginContext):abort('tax_plugin_context_invalid')
 for i,item in enumerate((value.tenant_id,value.user_id,value.data_space_id,value.actor_id)):
  if not isinstance(item,str) or not 3<=len(item)<=(80 if i==3 else 64) or re.search(r'[\x00-\x1f\x7f]',item):abort('tax_plugin_context_invalid')
 return value
def context_fingerprint(value):
 c=normalize_context(value);return sha({'contract_version':'tax_model_plugin_v1','tenant_id':c.tenant_id,'user_id':c.user_id,'data_space_id':c.data_space_id})
def valid_utc(value):
 if not isinstance(value,str) or not UTC.fullmatch(value):abort('tax_plugin_input_invalid')
 return value
def valid_date(value):
 if not isinstance(value,str) or not DATE.fullmatch(value):abort('tax_plugin_input_invalid')
 return value
def valid_ref(value,prefix=None):
 if not isinstance(value,str) or not re.fullmatch(r'[a-z][a-z0-9]{2}_[a-f0-9]{24,32}',value) or prefix and not value.startswith(prefix):abort('tax_plugin_input_invalid')
 return value
def valid_fp(value):
 if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{64}',value):abort('tax_plugin_input_invalid')
 return value

def _manifest(plugin_id:str,plugin_root:Path|None=None)->TaxPluginManifest:
 root=PLUGIN_ROOT if plugin_root is None else Path(plugin_root)
 if not isinstance(plugin_id,str) or not re.fullmatch(r'tax_[a-z0-9_]{3,60}_v[0-9]+',plugin_id):abort('tax_plugin_unknown')
 directory=root/plugin_id;manifest_path=directory/'manifest.json';entry=directory/'plugin.R'
 if directory.is_symlink() or manifest_path.is_symlink() or entry.is_symlink() or not manifest_path.is_file() or not entry.is_file():abort('tax_plugin_unknown')
 try:raw=manifest_path.read_bytes();data=json.loads(raw)
 except (OSError,UnicodeError,json.JSONDecodeError) as e:raise TaxPluginBlocked('tax_plugin_manifest_invalid') from e
 required={'plugin_id','plugin_version','api_version','jurisdiction_code','model_scope','supported_projection_modes','effective_from','effective_to','ledger_schema_versions','fifo_profiles','input_contract','output_contract','entry_point','capabilities','rules_fingerprint','disclaimer_codes','exclusions'};optional={'resource_fingerprints'}
 if not required<=set(data) or set(data)-required-optional or data['plugin_id']!=plugin_id or data['api_version']!='tax_model_plugin_v1' or data['input_contract']!='tax_plugin_input_v1' or data['output_contract']!='tax_plugin_output_v1' or data['entry_point']!='plugin.R':abort('tax_plugin_manifest_invalid')
 if not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',str(data['plugin_version'])) or not re.fullmatch(r'[A-Z]{2,8}',str(data['jurisdiction_code'])) or data['model_scope'] not in {'private_assets','scenario'}:abort('tax_plugin_manifest_invalid')
 modes=data['supported_projection_modes']
 if not isinstance(modes,list) or not modes or len(set(modes))!=len(modes) or not set(modes)<=MODES:abort('tax_plugin_manifest_invalid')
 if not isinstance(data['capabilities'],list) or set(data['capabilities'])!=CAPABILITIES:abort('tax_plugin_manifest_invalid')
 if data['ledger_schema_versions']!=[400] or 'realized_fifo_v1' not in data['fifo_profiles']:abort('tax_plugin_manifest_incompatible')
 valid_date(data['effective_from'])
 if data['effective_to'] is not None and (valid_date(data['effective_to'])<data['effective_from']):abort('tax_plugin_manifest_invalid')
 if data['rules_fingerprint']!=sha(entry.read_bytes()):abort('tax_plugin_rules_fingerprint_mismatch')
 disclaimers=data['disclaimer_codes']
 if not isinstance(disclaimers,list) or 'model_projection_not_legal_advice' not in disclaimers or any(not isinstance(x,str) or not re.fullmatch(r'[a-z][a-z0-9_]{2,79}',x) for x in disclaimers):abort('tax_plugin_manifest_invalid')
 if not isinstance(data['exclusions'],list) or not data['exclusions']:abort('tax_plugin_manifest_invalid')
 resources=data.get('resource_fingerprints',{})
 if not isinstance(resources,dict):abort('tax_plugin_manifest_invalid')
 for name,fingerprint in resources.items():
  if not isinstance(name,str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,60}\.csv',name) or not isinstance(fingerprint,str) or not re.fullmatch(r'[a-f0-9]{64}',fingerprint):abort('tax_plugin_manifest_invalid')
  resource=directory/name
  if resource.is_symlink() or not resource.is_file() or sha(resource.read_bytes())!=fingerprint:abort('tax_plugin_resource_fingerprint_mismatch')
 return TaxPluginManifest(plugin_id,data['plugin_version'],data['jurisdiction_code'],data['model_scope'],tuple(modes),data['effective_from'],data['effective_to'],data['rules_fingerprint'],sha(raw),entry,tuple(disclaimers),tuple(sorted(resources.items())))
def tax_plugin_manifest_v1(plugin_id,plugin_root=None):return _manifest(plugin_id,plugin_root)
def tax_plugin_catalog_v1(plugin_root=None):
 root=PLUGIN_ROOT if plugin_root is None else Path(plugin_root)
 if not root.is_dir() or root.is_symlink():return ()
 values=[]
 for directory in sorted(root.iterdir(),key=lambda path:path.name):
  if not directory.is_dir() or directory.is_symlink():continue
  try:manifest=_manifest(directory.name,root)
  except TaxPluginBlocked:continue
  values.append({'plugin_id':manifest.plugin_id,'plugin_version':manifest.plugin_version,'jurisdiction_code':manifest.jurisdiction_code,'model_scope':manifest.model_scope,'supported_projection_modes':list(manifest.supported_projection_modes),'effective_from':manifest.effective_from,'effective_to':manifest.effective_to,'disclaimer_codes':list(manifest.disclaimer_codes),'recommended':manifest.plugin_id=='tax_de_personal_income_tax_projection_v1'})
 return tuple(values)

def bootstrap_tax_plugin_store_v1(path,context,created_at_utc):
 c=normalize_context(context);created=valid_utc(created_at_utc);target=Path(path)
 if target.exists() or target.is_symlink():abort('tax_plugin_store_exists')
 try:target=target.parent.resolve(strict=True)/target.name
 except OSError as e:raise TaxPluginBlocked('tax_plugin_store_invalid') from e
 con=sqlite3.connect(target)
 try:
  con.executescript(SCHEMA.read_text());con.execute('INSERT INTO tax_plugin_store_binding VALUES (1,1900,?,?)',(context_fingerprint(c),created));con.commit()
 except Exception:
  con.close();target.unlink(missing_ok=True);raise
 finally:
  try:con.close()
  except:pass
 os.chmod(target,0o600);return target

def connect(path,context,ro=False):
 c=normalize_context(context);p=Path(path)
 if p.is_symlink() or not p.is_file():abort('tax_plugin_store_invalid')
 try:
  con=sqlite3.connect(f'{p.resolve(strict=True).as_uri()}?mode=ro&immutable=1',uri=True) if ro else sqlite3.connect(p.resolve(strict=True),isolation_level=None)
  con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
  if ro:con.execute('PRAGMA query_only=ON')
  b=con.execute('SELECT context_binding_fingerprint FROM tax_plugin_store_binding WHERE singleton_id=1').fetchone()
  if con.execute('PRAGMA user_version').fetchone()[0] not in {1900,2200} or b is None or b[0]!=context_fingerprint(c):con.close();abort('tax_plugin_context_mismatch')
  return con
 except TaxPluginBlocked:raise
 except sqlite3.Error as e:raise TaxPluginBlocked('tax_plugin_store_invalid') from e

def _public_selection(row):
 payload={k:row[k] for k in ('selection_ref','revision_no','portfolio_ref','projection_mode','plugin_id','plugin_version','rules_fingerprint','manifest_fingerprint','effective_from','status')}
 payload['revision_token']=sha({'contract':'tax_plugin_selection_v1','revision':payload});return TaxPluginSelection(**payload)
def select_tax_plugin_v1(store_path,context,manifest:TaxPluginManifest,*,request_ref,portfolio_ref,projection_mode,effective_from,created_at_utc,revision_token=None,status='active'):
 if not isinstance(manifest,TaxPluginManifest):abort('tax_plugin_manifest_invalid')
 valid_ref(portfolio_ref,'pfr_');valid_date(effective_from);created=valid_utc(created_at_utc)
 if projection_mode not in manifest.supported_projection_modes or status not in {'active','retired'} or not re.fullmatch(r'req_[a-f0-9]{24,32}',str(request_ref)):abort('tax_plugin_selection_invalid')
 if effective_from<manifest.effective_from or manifest.effective_to and effective_from>manifest.effective_to:abort('tax_plugin_selection_invalid')
 con=connect(store_path,context)
 try:
  con.execute('BEGIN IMMEDIATE')
  entity=con.execute('SELECT * FROM tax_plugin_selection_entity WHERE portfolio_ref=? AND projection_mode=?',(portfolio_ref,projection_mode)).fetchone()
  if entity is None:
   if revision_token is not None:abort('tax_plugin_revision_stale')
   selection_ref=internal('tsr',{'context':context_fingerprint(context),'portfolio_ref':portfolio_ref,'projection_mode':projection_mode});selection_id=internal('tse',selection_ref);revision=1;supersedes=None
   con.execute('INSERT INTO tax_plugin_selection_entity VALUES (?,?,?,?,?,?)',(selection_id,selection_ref,portfolio_ref,projection_mode,request_ref,created))
  else:
   current=con.execute('SELECT entity.selection_ref,entity.portfolio_ref,entity.projection_mode,revision.* FROM tax_plugin_selection_entity entity JOIN current_tax_plugin_selection_revision revision USING(selection_id) WHERE entity.selection_id=?',(entity['selection_id'],)).fetchone();public=_public_selection(current)
   if revision_token!=public.revision_token:abort('tax_plugin_revision_stale')
   selection_ref=entity['selection_ref'];selection_id=entity['selection_id'];revision=current['revision_no']+1;supersedes=current['selection_revision_id']
  con.execute('INSERT INTO tax_plugin_selection_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(internal('tsv',[selection_ref,revision,request_ref]),selection_id,revision,manifest.plugin_id,manifest.plugin_version,manifest.rules_fingerprint,manifest.manifest_fingerprint,effective_from,status,supersedes,request_ref,created))
  con.commit();row=con.execute('SELECT entity.selection_ref,entity.portfolio_ref,entity.projection_mode,revision.* FROM tax_plugin_selection_entity entity JOIN current_tax_plugin_selection_revision revision USING(selection_id) WHERE entity.selection_id=?',(selection_id,)).fetchone();return _public_selection(row)
 except TaxPluginBlocked:con.rollback();raise
 except sqlite3.IntegrityError as e:con.rollback();raise TaxPluginBlocked('tax_plugin_selection_conflict') from e
 finally:con.close()

def resolve_tax_plugin_selection_v1(store_path,context,portfolio_ref,projection_mode,effective_date):
 valid_ref(portfolio_ref,'pfr_');valid_date(effective_date)
 if projection_mode not in MODES:abort('tax_plugin_selection_invalid')
 con=connect(store_path,context,True)
 try:
  row=con.execute('''SELECT entity.selection_ref,entity.portfolio_ref,entity.projection_mode,revision.* FROM tax_plugin_selection_entity entity JOIN tax_plugin_selection_revision revision USING(selection_id) WHERE entity.portfolio_ref=? AND entity.projection_mode=? AND revision.effective_from<=? ORDER BY revision.effective_from DESC,revision.revision_no DESC LIMIT 1''',(portfolio_ref,projection_mode,effective_date)).fetchone()
  if row is None:return None
  value=_public_selection(row);return value if value.status=='active' else None
 finally:con.close()

def _validate_json_values(value,path='root'):
 forbidden={'tenant_id','user_id','data_space_id','actor_id','database_path','internal_id','sql','secret'}
 if isinstance(value,dict):
  if forbidden&set(value):abort('tax_plugin_context_leak')
  for k,v in value.items():
   if not isinstance(k,str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,79}',k):abort('tax_plugin_input_invalid')
   _validate_json_values(v,path+'.'+k)
 elif isinstance(value,list):
  for v in value:_validate_json_values(v,path)
 elif isinstance(value,float):abort('tax_plugin_binary_float_forbidden')
 elif value is not None and not isinstance(value,(str,int,bool)):abort('tax_plugin_input_invalid')

def new_tax_plugin_bound_input_v1(*,projection_mode,portfolio_ref,source_artifact_ref,cutoff,rows,classifications,parameters,prior_state=None):
 if projection_mode not in MODES:abort('tax_plugin_mode_unsupported')
 valid_ref(portfolio_ref,'pfr_');valid_ref(source_artifact_ref)
 if not isinstance(cutoff,str) or not cutoff:abort('tax_plugin_input_invalid')
 body={'api_version':'tax_model_plugin_v1','projection_mode':projection_mode,'portfolio_ref':portfolio_ref,'source_artifact_ref':source_artifact_ref,'cutoff':cutoff,'rows':rows,'classifications':classifications,'parameters':parameters,'prior_state':prior_state}
 _validate_json_values(body);run_ref=internal('tpr',body);body['run_ref']=run_ref;body['input_fingerprint']=sha(body);return body

def _jsonlite_library(rscript,environment,staging):
 try:
  result=subprocess.run([rscript,'--vanilla','-e','cat(find.package("jsonlite"))'],env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=10,check=True)
  source=Path(result.stdout).resolve(strict=True)
  if source.name!='jsonlite' or not source.is_dir():abort('tax_plugin_isolation_unavailable')
  library=staging/'r-library';library.mkdir(mode=0o700);shutil.copytree(source,library/'jsonlite',symlinks=False)
  return library
 except (OSError,subprocess.SubprocessError):abort('tax_plugin_isolation_unavailable')

def run_tax_model_plugin_v1(*,plugin_id,bound_input,context,selection,plugin_root=None,timeout_seconds=30,comparison_run=False):
 normalize_context(context);manifest=_manifest(plugin_id,plugin_root)
 if not comparison_run:
  if not isinstance(selection,TaxPluginSelection) or selection.status!='active' or (selection.plugin_id,selection.plugin_version,selection.rules_fingerprint,selection.manifest_fingerprint)!=(manifest.plugin_id,manifest.plugin_version,manifest.rules_fingerprint,manifest.manifest_fingerprint):abort('tax_plugin_selection_mismatch')
 expected={'api_version','run_ref','projection_mode','portfolio_ref','source_artifact_ref','cutoff','rows','classifications','parameters','prior_state','input_fingerprint'}
 if isinstance(bound_input,dict) and ('semantic_source_bindings' in bound_input or 'semantic_binding_fingerprint' in bound_input):expected|={'semantic_source_bindings','semantic_binding_fingerprint'}
 if not isinstance(bound_input,dict) or set(bound_input)!=expected:abort('tax_plugin_input_invalid')
 _validate_json_values(bound_input)
 rebuilt=dict(bound_input);input_fp=rebuilt.pop('input_fingerprint')
 if sha(rebuilt)!=input_fp or bound_input['projection_mode'] not in manifest.supported_projection_modes:abort('tax_plugin_mode_unsupported')
 if not comparison_run and (bound_input['portfolio_ref']!=selection.portfolio_ref or bound_input['projection_mode']!=selection.projection_mode):abort('tax_plugin_selection_mismatch')
 if not isinstance(timeout_seconds,int) or not 1<=timeout_seconds<=300:abort('tax_plugin_input_invalid')
 staging=Path(tempfile.mkdtemp(prefix='.portelyra-tax-plugin-v1-'));os.chmod(staging,0o700);source=staging/'bound-input.json';output=staging/'output';temporary=staging/'tmp';output.mkdir(mode=0o700);temporary.mkdir(mode=0o700);source.write_text(canonical(bound_input)+'\n');os.chmod(source,0o400)
 env={'PATH':os.environ.get('PATH',''),'HOME':str(temporary),'TMPDIR':str(temporary),'LANG':'C.UTF-8','LC_ALL':'C.UTF-8','R_LIBS_SITE':'/usr/local/lib/R/site-library:/usr/lib/R/site-library','R_ENVIRON_USER':str(temporary/'disabled-Renviron'),'R_PROFILE_USER':str(temporary/'disabled-Rprofile')}
 env['PORTELYRA_TAX_PLUGIN_ID']=manifest.plugin_id
 env['PORTELYRA_TAX_PLUGIN_VERSION']=manifest.plugin_version
 env['PORTELYRA_TAX_PLUGIN_RULES_FINGERPRINT']=manifest.rules_fingerprint
 rscript=shutil.which('Rscript',path=env['PATH'])
 try:
  if not rscript or not SANDBOX.is_file():abort('tax_plugin_isolation_unavailable')
  library=_jsonlite_library(rscript,env,staging);env['R_LIBS_USER']=str(library)
  command=[sys.executable,'-B',str(SANDBOX),'--rscript',rscript,'--r-library',str(library),'--entry',str(manifest.entry_path),'--source',str(source),'--output',str(output),'--temporary',str(temporary),'--timeout-seconds',str(timeout_seconds)]
  process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env,start_new_session=True)
  try:stdout,stderr=process.communicate(timeout=timeout_seconds)
  except subprocess.TimeoutExpired as e:
   os.killpg(process.pid,signal.SIGKILL);process.communicate();raise TaxPluginBlocked('tax_plugin_timeout') from e
  if process.returncode==78:abort('tax_plugin_isolation_unavailable')
  if process.returncode!=0:abort('tax_plugin_failed')
  if stdout or stderr:abort('tax_plugin_output_invalid')
  entries=list(output.iterdir())
  if len(entries)!=1 or entries[0].name!='tax-plugin-output.json' or entries[0].is_symlink() or not entries[0].is_file():abort('tax_plugin_output_invalid')
  raw=entries[0].read_bytes();data=json.loads(raw)
  required={'api_version','plugin_id','plugin_version','rules_fingerprint','projection_mode','status','rows','reconciliation','disclaimer_codes'}
  if set(data)!=required or data['api_version']!='tax_model_plugin_v1' or data['plugin_id']!=manifest.plugin_id or data['plugin_version']!=manifest.plugin_version or data['rules_fingerprint']!=manifest.rules_fingerprint or data['projection_mode']!=bound_input['projection_mode'] or data['status']!='completed':abort('tax_plugin_output_invalid')
  if not isinstance(data['rows'],list) or not isinstance(data['reconciliation'],dict) or data['disclaimer_codes']!=list(manifest.disclaimer_codes):abort('tax_plugin_output_invalid')
  _validate_json_values(data)
  for row in data['rows']:
   if not isinstance(row,dict):abort('tax_plugin_output_invalid')
   for field,value in row.items():
    if field.endswith('_decimal') and value is not None and (not isinstance(value,str) or not DECIMAL.fullmatch(value)):abort('tax_plugin_output_invalid')
  return TaxPluginRunResult(bound_input['run_ref'],manifest.plugin_id,manifest.plugin_version,manifest.rules_fingerprint,bound_input['projection_mode'],input_fp,sha(raw),tuple(data['rows']),data['reconciliation'],tuple(data['disclaimer_codes']))
 except (json.JSONDecodeError,UnicodeError,OSError) as e:raise TaxPluginBlocked('tax_plugin_output_invalid') from e
 finally:
  try:
   os.chmod(source,0o600);shutil.rmtree(staging)
  except OSError:pass
