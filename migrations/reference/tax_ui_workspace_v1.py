#!/usr/bin/env python3
"""Preview-confirm-apply Tax UI commands over the Tax Plugin policy store."""
from __future__ import annotations
import csv,json,re,sqlite3
from dataclasses import dataclass
from decimal import Decimal,InvalidOperation
from pathlib import Path
from typing import Any,Mapping
from migrations.reference.desktop_product_asset_activity_v1 import (
 DesktopProductAssetActivityContextV1,DesktopProductAssetActivityV1Error,_canonical_snapshot,
)
from workers.reference.semantic_realized_fifo_v1 import context_values as semantic_context_values,public_ref as semantic_public_ref
from migrations.reference.tax_model_plugin_v1 import (PLUGIN_ROOT,TaxPluginBlocked,TaxPluginContext,_manifest,_public_selection,abort as plugin_abort,canonical,connect,context_fingerprint,internal,normalize_context,sha,tax_plugin_catalog_v1,valid_date,valid_ref,valid_utc)
ROOT=Path(__file__).resolve().parents[2]
MIGRATION=ROOT/'contracts/tax-ui/v1/migrate-tax-plugin-store-v1900-to-v2200.sql'
MIGRATION_2201=ROOT/'contracts/tax-ui/v1/migrate-tax-plugin-store-v2200-to-v2201.sql'
MIGRATION_2202=ROOT/'contracts/tax-ui/v1/migrate-tax-plugin-store-v2201-to-v2202.sql'
MIGRATION_2203=ROOT/'contracts/tax-ui/v1/migrate-tax-plugin-store-v2202-to-v2203.sql'
MIGRATION_2204=ROOT/'contracts/tax-ui/v1/migrate-tax-plugin-store-v2203-to-v2204.sql'
PARAMETERS=ROOT/'contracts/tax-plugins/de-personal-income-tax-v2/parameter-definitions.csv'
CLASSIFICATIONS=ROOT/'contracts/tax-plugins/de-personal-income-tax-v2/classification-definitions.csv'
PLUGIN_ID='tax_de_personal_income_tax_projection_v2'
COMMANDS=frozenset({'select_plugin','set_asset_classification','set_asset_type_classification','set_parameter','retire_asset_classification','retire_asset_type_classification','retire_parameter'})
DECIMAL=re.compile(r'^(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$')
class TaxUiBlocked(ValueError):
 def __init__(self,code):super().__init__(code);self.code=code
@dataclass(frozen=True)
class TaxUiPreview:preview_ref:str;command_type:str;portfolio_ref:str;summary:dict[str,Any];canonical_write:bool=False;calculation:bool=False;provider_access:bool=False
@dataclass(frozen=True)
class TaxUiConfirmation:confirmation_ref:str;preview_ref:str;status:str
@dataclass(frozen=True)
class TaxUiApplyResult:attempt_ref:str;result_ref:str;status:str;invalidation_refs:tuple[str,...]
def blocked(code):raise TaxUiBlocked(code)
def _ctx(value):
 try:return normalize_context(value)
 except TaxPluginBlocked as e:raise TaxUiBlocked('tax_ui_context_invalid') from e
def _ui_connect(path,ctx,ro=False):
 c=_ctx(ctx);p=Path(path)
 if p.is_symlink() or not p.is_file():blocked('tax_plugin_store_invalid')
 try:
  probe=sqlite3.connect(f'{p.resolve(strict=True).as_uri()}?mode=ro&immutable=1',uri=True);version=probe.execute('PRAGMA user_version').fetchone()[0];probe.close()
  # 2203 liest sich wie 2204 (#468); geschrieben wird erst nach der Migration.
  if version==2203 and not ro:_migrate_2204(p,ctx)
  elif version not in {2203,2204}:blocked('tax_ui_upgrade_required')
  con=sqlite3.connect(f'{p.resolve(strict=True).as_uri()}?mode=ro&immutable=1',uri=True) if ro else sqlite3.connect(p.resolve(strict=True),isolation_level=None)
  con.row_factory=sqlite3.Row;con.execute('PRAGMA foreign_keys=ON')
  if ro:con.execute('PRAGMA query_only=ON')
  binding=con.execute('SELECT context_binding_fingerprint FROM tax_plugin_store_binding WHERE singleton_id=1').fetchone()
  if binding is None or binding[0]!=context_fingerprint(c):con.close();blocked('tax_plugin_context_mismatch')
  return con
 except TaxUiBlocked:raise
 except sqlite3.Error as e:raise TaxUiBlocked('tax_plugin_store_invalid') from e
def _upgrade_connect(path,ctx):
 """Schreibend geoeffnet, Bindung geprueft, Fassung offen gelassen."""
 c=_ctx(ctx);p=Path(path)
 if p.is_symlink() or not p.is_file():blocked('tax_ui_store_invalid')
 try:
  con=sqlite3.connect(p.resolve(strict=True),isolation_level=None);con.row_factory=sqlite3.Row
  binding=con.execute('SELECT context_binding_fingerprint FROM tax_plugin_store_binding WHERE singleton_id=1').fetchone()
  if binding is None or binding[0]!=context_fingerprint(c):con.close();blocked('tax_plugin_context_mismatch')
  return con
 except TaxUiBlocked:raise
 except sqlite3.Error as e:raise TaxUiBlocked('tax_ui_store_invalid') from e
def _migrate_2204(p,ctx):
 """Fassung 2203 auf 2204: die Einzeleinordnung darf rueckwirkend korrigiert werden (#468)."""
 con=_upgrade_connect(p,ctx)
 try:
  if con.execute('PRAGMA user_version').fetchone()[0]==2203:con.executescript(MIGRATION_2204.read_text())
  if con.execute('PRAGMA user_version').fetchone()[0]!=2204 or con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':blocked('tax_ui_store_invalid')
 except sqlite3.Error as e:raise TaxUiBlocked('tax_ui_store_invalid') from e
 finally:con.close()


def upgrade_tax_plugin_store_for_ui_v1(path,ctx):
 p=Path(path)
 try:
  probe=sqlite3.connect(f'{p.resolve(strict=True).as_uri()}?mode=ro&immutable=1',uri=True);version=probe.execute('PRAGMA user_version').fetchone()[0];probe.close()
 except (OSError,sqlite3.Error) as e:raise TaxUiBlocked('tax_ui_store_invalid') from e
 if version==2204:
  con=_ui_connect(p,ctx,True);con.close();return p
 # connect() aus dem Plugin-Vertrag laesst nur die Fassungen 1900 und 2200 zu.
 # Fuer die Zwischenfassungen dieses Speichers wird deshalb direkt geoeffnet -
 # mit derselben Bindungspruefung, nur ohne Fassungsliste (#368, 28.09.2026).
 if version in {2201,2202,2203}:
  con=_upgrade_connect(p,ctx)
  try:
   if version==2201:
    con.executescript(MIGRATION_2202.read_text());version=2202
   if version==2202:
    con.executescript(MIGRATION_2203.read_text());version=2203
   con.executescript(MIGRATION_2204.read_text())
   if con.execute('PRAGMA user_version').fetchone()[0]!=2204 or con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':blocked('tax_ui_store_invalid')
   return p
  except sqlite3.Error as e:raise TaxUiBlocked('tax_ui_store_invalid') from e
  finally:con.close()
 try:con=connect(p,_ctx(ctx))
 except TaxPluginBlocked as e:raise TaxUiBlocked(e.code) from e
 try:
  if version==1900:
   con.executescript(MIGRATION.read_text());version=2200
  if version==2200:
   con.executescript(MIGRATION_2201.read_text());version=2201
  if version==2201:
   con.executescript(MIGRATION_2202.read_text());version=2202
  if version!=2202:blocked('tax_ui_store_invalid')
  con.executescript(MIGRATION_2203.read_text())
  con.executescript(MIGRATION_2204.read_text())
  if con.execute('PRAGMA user_version').fetchone()[0]!=2204 or con.execute('PRAGMA integrity_check').fetchone()[0]!='ok':blocked('tax_ui_store_invalid')
  return p
 except sqlite3.Error as e:raise TaxUiBlocked('tax_ui_store_invalid') from e
 finally:con.close()
def _parameter_definitions():
 rows=list(csv.DictReader(PARAMETERS.open(encoding='utf-8',newline='')));result={}
 for row in rows:result.setdefault(row['parameter_code'],row)
 return result
def _classification_definitions():return {r['classification_code']:r for r in csv.DictReader(CLASSIFICATIONS.open(encoding='utf-8',newline=''))}
def _decimal(value):
 if not isinstance(value,str) or not DECIMAL.fullmatch(value):blocked('tax_ui_decimal_invalid')
 try:return Decimal(value)
 except InvalidOperation:blocked('tax_ui_decimal_invalid')
def _current_selection(con,portfolio,mode):
 return con.execute('SELECT entity.selection_ref,entity.portfolio_ref,entity.projection_mode,revision.* FROM tax_plugin_selection_entity entity JOIN current_tax_plugin_selection_revision revision USING(selection_id) WHERE entity.portfolio_ref=? AND entity.projection_mode=?',(portfolio,mode)).fetchone()
def _type_classification_public(row):
 value={k:row[k] for k in ('type_classification_ref','revision_no','portfolio_ref','asset_type','classification_code','tax_bucket','partial_exemption_rate_decimal','effective_from_year','effective_to_year','status')};value['_token']=sha({'contract':'tax_ui_type_classification_v1','revision':value});return value
def _current_type_classification(con,portfolio,asset_type):
 return con.execute('SELECT entity.type_classification_ref,entity.portfolio_ref,entity.asset_type,revision.* FROM asset_type_tax_classification_entity entity JOIN current_asset_type_tax_classification_revision revision USING(type_classification_id) WHERE entity.portfolio_ref=? AND entity.asset_type=?',(portfolio,asset_type)).fetchone()
def _resolved_classifications(classifications,type_defaults,assets):
 """Was fuer ein Asset gilt: der Einzelfall, sonst die Vorgabe seines Typs.

 Der Einzelfall gewinnt immer - er ist die ausdrueckliche Abweichung. Ohne
 Vorgabe je Typ waere je Asset ein Einzeleintrag noetig
 (Festlegung 28.09.2026, #367).
 """
 explicit={x['asset_ref']:x for x in classifications}
 by_type={x['asset_type']:x for x in type_defaults}
 resolved=[];unresolved=[]
 for asset in assets:
  ref=asset.get('exchange_ref')
  if ref in explicit:
   resolved.append({**explicit[ref],'origin':'asset'});continue
  default=by_type.get(asset.get('asset_type'))
  if default is None:unresolved.append(ref);continue
  resolved.append({'asset_ref':ref,'classification_code':default['classification_code'],'tax_bucket':default['tax_bucket'],
                   'partial_exemption_rate_decimal':default['partial_exemption_rate_decimal'],
                   'effective_from_year':default['effective_from_year'],'effective_to_year':default['effective_to_year'],
                   'status':default['status'],'origin':'asset_type','asset_type':asset.get('asset_type')})
 return resolved,sorted(unresolved)
def _classification_public(row):
 value={k:row[k] for k in ('classification_ref','revision_no','portfolio_ref','asset_ref','classification_code','tax_bucket','partial_exemption_rate_decimal','effective_from_year','effective_to_year','status')};value['_token']=sha({'contract':'tax_ui_classification_v1','revision':value});return value
def _current_classification(con,portfolio,asset):
 return con.execute('SELECT entity.classification_ref,entity.portfolio_ref,entity.asset_ref,revision.* FROM asset_tax_classification_entity entity JOIN current_asset_tax_classification_revision revision USING(classification_id) WHERE entity.portfolio_ref=? AND entity.asset_ref=?',(portfolio,asset)).fetchone()
def _parameter_public(row):
 value={k:row[k] for k in ('parameter_ref','revision_no','portfolio_ref','tax_year','parameter_code','currency','value_kind','rate_decimal','amount_decimal','status')};value['currency']=None if value['currency']=='' else value['currency'];value['_token']=sha({'contract':'tax_ui_parameter_v1','revision':value});return value
def _applicability_public(row):
 value={k:row[k] for k in ('applicability_ref','revision_no','portfolio_ref','tax_year','parameter_code','applicability_value','status')};value['currency']=None;value['value_kind']='applicability';value['_token']=sha({'contract':'tax_ui_applicability_v1','revision':value});return value
def _current_applicability(con,portfolio,year,code='church_tax_applicable'):
 return con.execute('SELECT entity.applicability_ref,entity.portfolio_ref,entity.tax_year,entity.parameter_code,revision.* FROM tax_applicability_entity entity JOIN current_tax_applicability_revision revision USING(applicability_id) WHERE entity.portfolio_ref=? AND entity.tax_year=? AND entity.parameter_code=?',(portfolio,year,code)).fetchone()
def _current_parameter(con,portfolio,year,code,currency):
 currency='' if currency is None else currency
 return con.execute('SELECT entity.parameter_ref,entity.portfolio_ref,entity.tax_year,entity.parameter_code,entity.currency,revision.* FROM tax_parameter_entity entity JOIN current_tax_parameter_revision revision USING(parameter_id) WHERE entity.portfolio_ref=? AND entity.tax_year=? AND entity.parameter_code=? AND entity.currency=?',(portfolio,year,code,currency)).fetchone()
def _module_manifest(plugin_id,module_key,data_space,plugin_root=None):
 """Eine bestimmte Fassung aus dem Katalog (#486 Schritt 2): mitgeliefert oder im Datenraum, ueber ihren Schluessel."""
 from migrations.reference.tax_module_catalog_v1 import tax_module_catalog_v1,tax_module_key_v1,tax_module_manifest_v1
 if not isinstance(module_key,str) or not re.fullmatch(r'tmk_[a-f0-9]{24}',module_key) or data_space is None:blocked('tax_ui_command_invalid')
 entry=next((e for e in tax_module_catalog_v1(data_space,plugin_root) if e['plugin_id']==plugin_id and tax_module_key_v1(e)==module_key),None)
 if entry is None:blocked('tax_plugin_unknown')
 try:return tax_module_manifest_v1(entry)
 except TaxPluginBlocked as e:raise TaxUiBlocked(e.code) from e
def _normalize_payload(con,command,payload,plugin_root=None,data_space=None):
 if command not in COMMANDS or not isinstance(payload,Mapping):blocked('tax_ui_command_invalid')
 portfolio=payload.get('portfolio_ref');valid_ref(portfolio,'pfr_')
 if command=='select_plugin':
  # Ohne module_key die mitgelieferte Fassung (wie bisher); mit ihm genau diese Fassung des Katalogs, etwa eine neue (#486 Schritt 2).
  keys={'portfolio_ref','projection_mode','plugin_id','effective_from','status'}
  if not keys<=set(payload)<=keys|{'module_key'}:blocked('tax_ui_command_invalid')
  mode=payload['projection_mode'];status=payload['status'];effective=valid_date(payload['effective_from'])
  manifest=_module_manifest(payload['plugin_id'],payload['module_key'],data_space,plugin_root) if 'module_key' in payload else _manifest(payload['plugin_id'],plugin_root)
  if mode not in manifest.supported_projection_modes or status not in {'active','retired'} or effective<manifest.effective_from or manifest.effective_to and effective>manifest.effective_to:blocked('tax_ui_command_invalid')
  current=_current_selection(con,portfolio,mode);token=None if current is None else _public_selection(current).revision_token
  normalized=dict(payload,plugin_version=manifest.plugin_version,rules_fingerprint=manifest.rules_fingerprint,manifest_fingerprint=manifest.manifest_fingerprint)
  summary={'projection_mode':mode,'plugin_id':manifest.plugin_id,'plugin_version':manifest.plugin_version,'effective_from':effective,'status':status,'revision_no':1 if current is None else current['revision_no']+1}
  return normalized,token,summary
 if command in {'set_asset_type_classification','retire_asset_type_classification'}:
  required={'portfolio_ref','asset_type','effective_from_year'} if command.startswith('retire') else {'portfolio_ref','asset_type','classification_code','tax_bucket','partial_exemption_rate_decimal','effective_from_year','effective_to_year'}
  if set(payload)!=required:blocked('tax_ui_command_invalid')
  asset_type=payload['asset_type'];year=payload['effective_from_year']
  if not isinstance(asset_type,str) or not re.fullmatch(r'[a-z][a-z0-9_]{1,39}',asset_type):blocked('tax_ui_command_invalid')
  if not isinstance(year,int) or not 1900<=year<=9999:blocked('tax_ui_command_invalid')
  current=_current_type_classification(con,portfolio,asset_type);token=None if current is None else _type_classification_public(current)['_token']
  if command.startswith('retire'):
   if current is None:blocked('tax_ui_revision_missing')
   normalized={'portfolio_ref':portfolio,'asset_type':asset_type,'classification_code':current['classification_code'],'tax_bucket':current['tax_bucket'],'partial_exemption_rate_decimal':current['partial_exemption_rate_decimal'],'effective_from_year':year,'effective_to_year':current['effective_to_year'],'status':'retired'}
  else:
   definition=_classification_definitions().get(payload['classification_code']);partial=_decimal(payload['partial_exemption_rate_decimal']);end=payload['effective_to_year']
   if definition is None or definition['tax_bucket']!=payload['tax_bucket'] or (definition['partial_exemption_policy']=='must_be_zero' and partial!=0) or partial>100:blocked('tax_ui_classification_invalid')
   if end is not None and (not isinstance(end,int) or end<year):blocked('tax_ui_command_invalid')
   normalized=dict(payload,status='active')
  summary={k:normalized[k] for k in ('asset_type','classification_code','tax_bucket','partial_exemption_rate_decimal','effective_from_year','effective_to_year','status')}
  return normalized,token,summary
 if command in {'set_asset_classification','retire_asset_classification'}:
  required={'portfolio_ref','asset_ref','effective_from_year'} if command.startswith('retire') else {'portfolio_ref','asset_ref','classification_code','tax_bucket','partial_exemption_rate_decimal','effective_from_year','effective_to_year'}
  if set(payload)!=required:blocked('tax_ui_command_invalid')
  asset=payload['asset_ref'];valid_ref(asset,'asf_');year=payload['effective_from_year']
  if not isinstance(year,int) or not 1900<=year<=9999:blocked('tax_ui_command_invalid')
  current=_current_classification(con,portfolio,asset);token=None if current is None else _classification_public(current)['_token']
  if command.startswith('retire'):
   if current is None:blocked('tax_ui_revision_missing')
   normalized={'portfolio_ref':portfolio,'asset_ref':asset,'classification_code':current['classification_code'],'tax_bucket':current['tax_bucket'],'partial_exemption_rate_decimal':current['partial_exemption_rate_decimal'],'effective_from_year':year,'effective_to_year':None,'status':'retired'}
  else:
   definition=_classification_definitions().get(payload['classification_code']);partial=_decimal(payload['partial_exemption_rate_decimal']);end=payload['effective_to_year']
   if definition is None or definition['tax_bucket']!=payload['tax_bucket'] or (definition['partial_exemption_policy']=='must_be_zero' and partial!=0) or partial<0 or partial>100 or end is not None and (not isinstance(end,int) or end<year):blocked('tax_ui_classification_invalid')
   normalized=dict(payload,status='active')
  summary={k:normalized[k] for k in ('asset_ref','classification_code','tax_bucket','partial_exemption_rate_decimal','effective_from_year','effective_to_year','status')};summary['revision_no']=1 if current is None else current['revision_no']+1
  return normalized,token,summary
 required={'portfolio_ref','tax_year','parameter_code','currency'} if command=='retire_parameter' else {'portfolio_ref','tax_year','parameter_code','currency','value_decimal'}
 if set(payload)!=required:blocked('tax_ui_command_invalid')
 year=payload['tax_year'];code=payload['parameter_code'];definition=_parameter_definitions().get(code)
 if not isinstance(year,int) or not 1900<=year<=9999 or definition is None:blocked('tax_ui_parameter_invalid')
 currency=payload['currency']
 if definition['currency_policy']=='not_applicable':
  if currency is not None:blocked('tax_ui_parameter_invalid')
 elif not isinstance(currency,str) or not re.fullmatch(r'[A-Z]{3}',currency):blocked('tax_ui_parameter_invalid')
 if definition['value_kind']=='applicability':
  current=_current_applicability(con,portfolio,year,code);token=None if current is None else _applicability_public(current)['_token']
  if command=='retire_parameter':
   if current is None:blocked('tax_ui_revision_missing')
   normalized={'portfolio_ref':portfolio,'tax_year':year,'parameter_code':code,'currency':None,'value_kind':'applicability','applicability_value':None,'status':'retired'};value=None
  else:
   value=payload['value_decimal']
   if value not in {'applicable','not_applicable'}:blocked('tax_ui_parameter_invalid')
   normalized={'portfolio_ref':portfolio,'tax_year':year,'parameter_code':code,'currency':None,'value_kind':'applicability','applicability_value':value,'status':'active'}
  summary={'tax_year':year,'parameter_code':code,'currency':None,'value_kind':'applicability','value_decimal':value,'status':normalized['status'],'revision_no':1 if current is None else current['revision_no']+1}
  return normalized,token,summary
 current=_current_parameter(con,portfolio,year,code,currency);token=None if current is None else _parameter_public(current)['_token']
 if command=='retire_parameter':
  if current is None:blocked('tax_ui_revision_missing')
  normalized={'portfolio_ref':portfolio,'tax_year':year,'parameter_code':code,'currency':currency,'value_kind':current['value_kind'],'rate_decimal':None,'amount_decimal':None,'status':'retired'}
  value=None
 else:
  value=_decimal(payload['value_decimal']);minimum=Decimal(definition['minimum_decimal']) if definition['minimum_decimal'] else None;maximum=Decimal(definition['maximum_decimal']) if definition['maximum_decimal'] else None
  if minimum is not None and value<minimum or maximum is not None and value>maximum:blocked('tax_ui_parameter_invalid')
  kind=definition['value_kind'];normalized={'portfolio_ref':portfolio,'tax_year':year,'parameter_code':code,'currency':currency,'value_kind':kind,'rate_decimal':payload['value_decimal'] if kind=='rate' else None,'amount_decimal':payload['value_decimal'] if kind=='amount' else None,'status':'active'}
  value=payload['value_decimal']
 summary={'tax_year':year,'parameter_code':code,'currency':currency,'value_kind':normalized['value_kind'],'value_decimal':value,'status':normalized['status'],'revision_no':1 if current is None else current['revision_no']+1}
 return normalized,token,summary
def preview_tax_ui_command_v1(store,ctx,command_type,payload,created_at_utc,plugin_root=None):
 c=_ctx(ctx);created=valid_utc(created_at_utc);con=_ui_connect(store,c)
 try:
  normalized,token,summary=_normalize_payload(con,command_type,payload,plugin_root,Path(store).parent.parent);body={'command_type':command_type,'portfolio_ref':normalized['portfolio_ref'],'payload':normalized,'precondition':token,'context':context_fingerprint(c)};fingerprint=sha(body);preview_ref=internal('tprv',fingerprint);preview_id=internal('tup',preview_ref)
  con.execute('BEGIN IMMEDIATE');con.execute('INSERT OR IGNORE INTO tax_ui_command_preview VALUES (?,?,?,?,?,?,?,?,?)',(preview_id,preview_ref,command_type,normalized['portfolio_ref'],canonical(normalized),token,fingerprint,c.actor_id,created));row=con.execute('SELECT preview_fingerprint,actor_id FROM tax_ui_command_preview WHERE preview_ref=?',(preview_ref,)).fetchone()
  if row is None or row['preview_fingerprint']!=fingerprint or row['actor_id']!=c.actor_id:con.rollback();blocked('tax_ui_replay_conflict')
  con.commit();return TaxUiPreview(preview_ref,command_type,normalized['portfolio_ref'],summary)
 except sqlite3.Error as e:con.rollback();raise TaxUiBlocked('tax_ui_preview_failed') from e
 finally:con.close()
def confirm_tax_ui_command_v1(store,ctx,preview_ref,confirmed,confirmed_at_utc):
 c=_ctx(ctx);at=valid_utc(confirmed_at_utc)
 if confirmed is not True or not isinstance(preview_ref,str) or not preview_ref.startswith('tprv_'):blocked('tax_ui_confirmation_required')
 con=_ui_connect(store,c)
 try:
  preview=con.execute('SELECT * FROM tax_ui_command_preview WHERE preview_ref=? AND actor_id=?',(preview_ref,c.actor_id)).fetchone()
  if preview is None:blocked('tax_ui_preview_missing')
  fingerprint=sha({'preview_fingerprint':preview['preview_fingerprint'],'actor_id':c.actor_id});confirmation_ref=internal('tcf',fingerprint);confirmation_id=internal('tuc',confirmation_ref)
  con.execute('BEGIN IMMEDIATE');existing=con.execute('SELECT confirmation_id,preview_id,actor_id FROM tax_ui_command_confirmation WHERE confirmation_ref=?',(confirmation_ref,)).fetchone()
  if existing is None:
   con.execute('INSERT INTO tax_ui_command_confirmation VALUES (?,?,?,?,?,?)',(confirmation_id,confirmation_ref,preview['preview_id'],fingerprint,c.actor_id,at));con.commit();return TaxUiConfirmation(confirmation_ref,preview_ref,'confirmed')
  # Dieselbe Vorschau wurde schon bestaetigt (#470). Die Referenz ist aus der Nutzlast
  # abgeleitet, eine gleiche Eingabe trifft also dieselbe Bestaetigung. Solange kein
  # Versuch gelang, gilt sie weiter; den Wiederholversuch regelt der Trigger der
  # Versuchstabelle (Fassung 2203). Eine eingeloeste Bestaetigung bleibt einmalig.
  completed=con.execute("SELECT 1 FROM tax_ui_command_attempt attempt JOIN tax_ui_command_result result USING(attempt_id) WHERE attempt.confirmation_id=? AND result.status='completed'",(existing['confirmation_id'],)).fetchone()
  con.rollback()
  if existing['preview_id']!=preview['preview_id'] or existing['actor_id']!=c.actor_id:blocked('tax_ui_replay_conflict')
  if completed is not None:blocked('tax_ui_confirmation_consumed')
  return TaxUiConfirmation(confirmation_ref,preview_ref,'confirmed')
 except sqlite3.IntegrityError as e:con.rollback();raise TaxUiBlocked('tax_ui_confirmation_consumed') from e
 finally:con.close()
def _check_precondition(con,preview,payload):
 token=preview['precondition_revision_token'];command=preview['command_type'];portfolio=preview['portfolio_ref']
 if command=='select_plugin':
  row=_current_selection(con,portfolio,payload['projection_mode']);current=None if row is None else _public_selection(row).revision_token
 elif 'asset_type_classification' in command:
  row=_current_type_classification(con,portfolio,payload['asset_type']);current=None if row is None else _type_classification_public(row)['_token']
 elif 'classification' in command:
  row=_current_classification(con,portfolio,payload['asset_ref']);current=None if row is None else _classification_public(row)['_token']
 else:
  if payload['value_kind']=='applicability':
   row=_current_applicability(con,portfolio,payload['tax_year'],payload['parameter_code']);current=None if row is None else _applicability_public(row)['_token']
  else:
   row=_current_parameter(con,portfolio,payload['tax_year'],payload['parameter_code'],payload['currency']);current=None if row is None else _parameter_public(row)['_token']
 if current!=token:blocked('tax_ui_revision_stale')
 return row
def _invalidation_modes(command,payload):
 if command=='select_plugin':return (payload['projection_mode'],),'plugin_change',payload['effective_from']
 # Eine geaenderte Typvorgabe entwertet dasselbe wie eine geaenderte
 # Einzelklassifikation; der Grund ist derselbe Sachverhalt.
 if 'asset_type_classification' in command:return ('realized_event','realized_annual'),'tax_classification_change',str(payload['effective_from_year'])
 if 'classification' in command:return ('realized_event','realized_annual'),'tax_classification_change',str(payload['effective_from_year'])
 definitions=_parameter_definitions();modes={r['projection_mode'] for r in csv.DictReader(PARAMETERS.open(encoding='utf-8',newline='')) if r['parameter_code']==payload['parameter_code']};return tuple(sorted(modes)),'tax_parameter_change',str(payload['tax_year'])
def apply_tax_ui_command_v1(store,ctx,confirmation_ref,request_ref,applied_at_utc,failpoint=None):
 c=_ctx(ctx);at=valid_utc(applied_at_utc)
 if not isinstance(request_ref,str) or not re.fullmatch(r'req_[a-f0-9]{24,32}',request_ref) or failpoint not in {None,'after_domain','after_invalidation'}:blocked('tax_ui_command_invalid')
 con=_ui_connect(store,c)
 try:
  confirmation=con.execute('SELECT confirmation.*,preview.* FROM tax_ui_command_confirmation confirmation JOIN tax_ui_command_preview preview USING(preview_id) WHERE confirmation.confirmation_ref=? AND confirmation.actor_id=?',(confirmation_ref,c.actor_id)).fetchone()
  if confirmation is None:blocked('tax_ui_confirmation_missing')
  attempt_ref=internal('tat',{'confirmation_ref':confirmation_ref,'request_ref':request_ref});attempt_id=internal('tua',attempt_ref)
  try:con.execute('BEGIN IMMEDIATE');con.execute('INSERT INTO tax_ui_command_attempt VALUES (?,?,?,?,?)',(attempt_id,attempt_ref,confirmation['confirmation_id'],request_ref,at));con.commit()
  except sqlite3.IntegrityError as e:con.rollback();raise TaxUiBlocked('tax_ui_confirmation_consumed') from e
  payload=json.loads(confirmation['payload_json']);invalidations=[]
  try:
   con.execute('BEGIN IMMEDIATE');current=_check_precondition(con,confirmation,payload);command=confirmation['command_type'];portfolio=confirmation['portfolio_ref']
   if command=='select_plugin':
    if current is None:selection_ref=internal('tsr',{'context':context_fingerprint(c),'portfolio_ref':portfolio,'projection_mode':payload['projection_mode']});selection_id=internal('tse',selection_ref);revision=1;supersedes=None;con.execute('INSERT INTO tax_plugin_selection_entity VALUES (?,?,?,?,?,?)',(selection_id,selection_ref,portfolio,payload['projection_mode'],request_ref,at))
    else:selection_ref=current['selection_ref'];selection_id=current['selection_id'];revision=current['revision_no']+1;supersedes=current['selection_revision_id']
    con.execute('INSERT INTO tax_plugin_selection_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(internal('tsv',[selection_ref,revision,request_ref]),selection_id,revision,payload['plugin_id'],payload['plugin_version'],payload['rules_fingerprint'],payload['manifest_fingerprint'],payload['effective_from'],payload['status'],supersedes,request_ref,at));result_ref=selection_ref
   elif 'asset_type_classification' in command:
    if current is None:result_ref=internal('typ',{'context':context_fingerprint(c),'portfolio':portfolio,'asset_type':payload['asset_type']});entity_id=internal('tye',result_ref);revision=1;supersedes=None;con.execute('INSERT INTO asset_type_tax_classification_entity VALUES (?,?,?,?,?,?)',(entity_id,result_ref,portfolio,payload['asset_type'],request_ref,at))
    else:result_ref=current['type_classification_ref'];entity_id=current['type_classification_id'];revision=current['revision_no']+1;supersedes=current['type_classification_revision_id']
    con.execute('INSERT INTO asset_type_tax_classification_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(internal('tyv',[result_ref,revision,request_ref]),entity_id,revision,payload['classification_code'],payload['tax_bucket'],payload['partial_exemption_rate_decimal'],payload['effective_from_year'],payload['effective_to_year'],payload['status'],supersedes,request_ref,at))
   elif 'classification' in command:
    if current is None:result_ref=internal('tcr',{'context':context_fingerprint(c),'portfolio':portfolio,'asset':payload['asset_ref']});entity_id=internal('tce',result_ref);revision=1;supersedes=None;con.execute('INSERT INTO asset_tax_classification_entity VALUES (?,?,?,?,?,?)',(entity_id,result_ref,portfolio,payload['asset_ref'],request_ref,at))
    else:result_ref=current['classification_ref'];entity_id=current['classification_id'];revision=current['revision_no']+1;supersedes=current['classification_revision_id']
    con.execute('INSERT INTO asset_tax_classification_revision VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(internal('tcv',[result_ref,revision,request_ref]),entity_id,revision,payload['classification_code'],payload['tax_bucket'],payload['partial_exemption_rate_decimal'],payload['effective_from_year'],payload['effective_to_year'],payload['status'],supersedes,request_ref,at))
   else:
    if payload['value_kind']=='applicability':
     if current is None:result_ref=internal('tap',{'context':context_fingerprint(c),'portfolio':portfolio,'year':payload['tax_year'],'code':payload['parameter_code']});entity_id=internal('tae',result_ref);revision=1;supersedes=None;con.execute('INSERT INTO tax_applicability_entity VALUES (?,?,?,?,?,?,?)',(entity_id,result_ref,portfolio,payload['tax_year'],payload['parameter_code'],request_ref,at))
     else:result_ref=current['applicability_ref'];entity_id=current['applicability_id'];revision=current['revision_no']+1;supersedes=current['applicability_revision_id']
     con.execute('INSERT INTO tax_applicability_revision VALUES (?,?,?,?,?,?,?,?)',(internal('tav',[result_ref,revision,request_ref]),entity_id,revision,payload['applicability_value'],payload['status'],supersedes,request_ref,at))
    else:
     if current is None:result_ref=internal('tpm',{'context':context_fingerprint(c),'portfolio':portfolio,'year':payload['tax_year'],'code':payload['parameter_code'],'currency':payload['currency']});entity_id=internal('tpe',result_ref);revision=1;supersedes=None;con.execute('INSERT INTO tax_parameter_entity VALUES (?,?,?,?,?,?,?,?)',(entity_id,result_ref,portfolio,payload['tax_year'],payload['parameter_code'],'' if payload['currency'] is None else payload['currency'],request_ref,at))
     else:result_ref=current['parameter_ref'];entity_id=current['parameter_id'];revision=current['revision_no']+1;supersedes=current['parameter_revision_id']
     con.execute('INSERT INTO tax_parameter_revision VALUES (?,?,?,?,?,?,?,?,?,?)',(internal('tpv',[result_ref,revision,request_ref]),entity_id,revision,payload['value_kind'],payload['rate_decimal'],payload['amount_decimal'],payload['status'],supersedes,request_ref,at))
   if failpoint=='after_domain':raise RuntimeError('synthetic')
   modes,reason,invalidated_from=_invalidation_modes(command,payload)
   for mode in modes:
    ref=internal('tir',{'request_ref':request_ref,'mode':mode});con.execute('INSERT INTO tax_projection_invalidation VALUES (?,?,?,?,?,?,?,?,?)',(internal('tii',ref),ref,request_ref,portfolio,mode,invalidated_from,reason,'pending',at));invalidations.append(ref)
   if failpoint=='after_invalidation':raise RuntimeError('synthetic')
   con.execute("INSERT INTO tax_ui_command_result VALUES (?,'completed',?,NULL,?)",(attempt_id,result_ref,at));con.commit();return TaxUiApplyResult(attempt_ref,result_ref,'completed',tuple(invalidations))
  except TaxUiBlocked:raise
  except Exception as e:raise TaxUiBlocked('tax_ui_domain_write_failed') from e
 except TaxUiBlocked as e:
  try:
   if con.in_transaction:con.rollback()
   if 'attempt_id' in locals():con.execute('BEGIN IMMEDIATE');con.execute("INSERT OR IGNORE INTO tax_ui_command_result VALUES (?,'failed',NULL,?,?)",(attempt_id,e.code,at));con.commit()
  except sqlite3.Error:pass
  raise
 finally:con.close()
def _type_classifications(con,portfolio):
 rows=[]
 for row in con.execute('SELECT entity.type_classification_ref,entity.portfolio_ref,entity.asset_type,revision.* FROM asset_type_tax_classification_entity entity JOIN current_asset_type_tax_classification_revision revision USING(type_classification_id) WHERE entity.portfolio_ref=? ORDER BY entity.asset_type',(portfolio,)):
  value=_type_classification_public(row)
  if value['status']=='active':value.pop('_token');rows.append(value)
 return rows
def _current_configuration(con,portfolio,year):
 # Je Asset gilt die juengste Fassung, deren "gueltig ab" nicht nach dem Jahr liegt. Eine spaetere
 # Fassung mit frueherem Jahr korrigiert rueckwirkend (#468); bei steigendem "gueltig ab" wie bisher.
 classifications=[];seen_assets=set()
 for row in con.execute('SELECT entity.classification_ref,entity.portfolio_ref,entity.asset_ref,revision.* FROM asset_tax_classification_entity entity JOIN asset_tax_classification_revision revision USING(classification_id) WHERE entity.portfolio_ref=? AND revision.effective_from_year<=? AND (revision.effective_to_year IS NULL OR revision.effective_to_year>=?) ORDER BY entity.asset_ref,revision.revision_no DESC',(portfolio,year,year)):
  if row['asset_ref'] in seen_assets:continue
  seen_assets.add(row['asset_ref']);value=_classification_public(row)
  if value['status']=='active':value.pop('_token');classifications.append(value)
 parameters=[]
 for row in con.execute('SELECT entity.parameter_ref,entity.portfolio_ref,entity.tax_year,entity.parameter_code,entity.currency,revision.* FROM tax_parameter_entity entity JOIN current_tax_parameter_revision revision USING(parameter_id) WHERE entity.portfolio_ref=? AND entity.tax_year=? ORDER BY entity.parameter_code,entity.currency',(portfolio,year)):
  value=_parameter_public(row)
  if value['status']=='active':value.pop('_token');parameters.append(value)
 for row in con.execute('SELECT entity.applicability_ref,entity.portfolio_ref,entity.tax_year,entity.parameter_code,revision.* FROM tax_applicability_entity entity JOIN current_tax_applicability_revision revision USING(applicability_id) WHERE entity.portfolio_ref=? AND entity.tax_year=? ORDER BY entity.parameter_code',(portfolio,year)):
  value=_applicability_public(row)
  if value['status']=='active':value.pop('_token');parameters.append(value)
 return classifications,parameters
def _module_tax_years(plugin_id,plugin_root=None):
 """Die Steuerjahre, fuer die ein Modul den Rechtsstand fuehrt - None, wenn es keine Jahrestabelle hat.

 Die Tabelle ist ueber das Manifest an das Modul gebunden; ein Modul im Katalog
 hat sie also unveraendert.
 """
 table=(PLUGIN_ROOT if plugin_root is None else Path(plugin_root))/plugin_id/'annual-legal-values.csv'
 if table.is_symlink() or not table.is_file():return None
 try:
  with table.open(encoding='utf-8',newline='') as handle:return frozenset(int(row['tax_year']) for row in csv.DictReader(handle))
 except (OSError,UnicodeError,KeyError,TypeError,ValueError):return frozenset()
def _module_covers_year(plugin,tax_year,plugin_root=None):
 years=_module_tax_years(plugin['plugin_id'],plugin_root)
 if years is not None:return tax_year in years
 return int(plugin['effective_from'][:4])<=tax_year and (plugin['effective_to'] is None or tax_year<=int(plugin['effective_to'][:4]))
def _module_coverage_v1(plugin_id,tax_year,plugin_root=None):
 """Wie vollstaendig das Modul ein Steuerjahr fuehrt (#496): year-coverage.csv des Moduls; ohne Datei oder Zeile None."""
 table=(PLUGIN_ROOT if plugin_root is None else Path(plugin_root))/plugin_id/'year-coverage.csv'
 if table.is_symlink() or not table.is_file():return None
 try:
  with table.open(encoding='utf-8',newline='') as handle:
   for row in csv.DictReader(handle):
    if row.get('tax_year')==str(tax_year) and row.get('coverage') in ('complete','partial'):return {'coverage':row['coverage'],'scope_code':row.get('scope_code') or ''}
 except (OSError,UnicodeError,KeyError,TypeError,ValueError):return None
 return None
def _module_values_v1(plugin_id,tax_year,plugin_root=None):
 """Die Werte, die das Modul fuer ein Steuerjahr selbst mitbringt, mit Fundstelle (#498) - Saetze, Pauschbetrag, Freigrenzen."""
 root=(PLUGIN_ROOT if plugin_root is None else Path(plugin_root))/plugin_id
 values,references=root/'annual-legal-values.csv',root/'legal-references.csv'
 if values.is_symlink() or not values.is_file():return []
 try:
  citations={}
  if references.is_file() and not references.is_symlink():
   with references.open(encoding='utf-8',newline='') as handle:citations={row['legal_reference_code']:row['citation'] for row in csv.DictReader(handle)}
  with values.open(encoding='utf-8',newline='') as handle:
   return [{'value_code':row['value_code'],'value_kind':row['value_kind'],'value_decimal':row['value_decimal'],'currency':row.get('currency') or None,
            'citation':citations.get(row.get('legal_reference_code') or '')} for row in csv.DictReader(handle) if row['tax_year']==str(tax_year)]
 except (OSError,UnicodeError,KeyError,TypeError,ValueError):return []
def tax_ui_definition_catalog_v1():
 return {'plugin_id':PLUGIN_ID,'classifications':tuple(_classification_definitions().values()),'parameters':tuple(csv.DictReader(PARAMETERS.open(encoding='utf-8',newline='')))}
def tax_ui_plugin_catalog_v1(plugin_root=None):
 return tuple({**row,'recommended':row['plugin_id']==PLUGIN_ID} for row in tax_plugin_catalog_v1(plugin_root))
def tax_ui_authorized_product_catalog_v1(data_space_path,ctx):
 c=_ctx(ctx)
 if re.fullmatch(r'sbx_[a-f0-9]{32}',c.data_space_id) is None:blocked('tax_ui_catalog_invalid')
 product_context=DesktopProductAssetActivityContextV1(c.tenant_id,c.user_id,c.data_space_id,c.actor_id,'desktop_owner')
 try:snapshot=_canonical_snapshot(Path(data_space_path)/'canonical.sqlite',product_context)
 except (DesktopProductAssetActivityV1Error,OSError) as error:raise TaxUiBlocked('tax_ui_catalog_invalid') from error
 _,_,_,context_fp=semantic_context_values({'tenant_id':c.tenant_id,'user_id':c.user_id,'data_space_id':c.data_space_id})
 return {
  'portfolios':tuple({'exchange_ref':semantic_public_ref('pfr_',context_fp,row['portfolio_id']),'display_name':row['display_name'],'status':row['status']} for row in snapshot['portfolios']),
  'assets':tuple({'exchange_ref':semantic_public_ref('asf_',context_fp,row['asset_id']),'display_name':row['display_name'],'asset_type':row['asset_type'],'status':row['status']} for row in snapshot['assets']),
  'accounts':(),
 }
def _completed_runs_v1(store,ctx,portfolio_ref):
 """Je Projektionsart der Zeitpunkt des juengsten vollstaendig abgeschlossenen Laufs im Run Center fuer dieses Portfolio (#497).

 Ein Vermerk "neu zu rechnen" ist unveraenderlich; erledigt ist er, sobald ein spaeter gestarteter Lauf die Rechnung dieser Art
 abgeschlossen hat - die Steuer je Ereignis und je Jahr in der Stufe tax, die unrealisierte in der Stufe valuation. Bis rc.295
 loeste nichts einen Vermerk auf; die Bereitschaft zeigte seit dem 27.09.2026 dauerhaft "veraltet". Liest nur."""
 c=_ctx(ctx);center=Path(store).parent.parent/'run-center';result={}
 if not (center/'runs').is_dir() or (center/'runs').is_symlink():return result
 _,_,_,context_fp=semantic_context_values({'tenant_id':c.tenant_id,'user_id':c.user_id,'data_space_id':c.data_space_id})
 for state_path in sorted((center/'runs').glob('run_*/state.json')):
  try:
   state=json.loads(state_path.read_text(encoding='utf-8'))
   if state.get('status')!='completed':continue
   payload=json.loads(json.loads((center/'jobs'/(state_path.parent.name+'.json')).read_text(encoding='utf-8'))['payload_json'])
   if semantic_public_ref('pfr_',context_fp,payload['portfolio']['portfolio_id'])!=portfolio_ref:continue
   started=payload['executed_at_utc'];stages={row['stage_code']:row['status'] for row in state.get('stage_states',[])}
  except (OSError,ValueError,KeyError,TypeError):continue
  modes=(('realized_event','realized_annual') if stages.get('tax')=='completed' else ())+(('unrealized_snapshot',) if stages.get('valuation')=='completed' else ())
  for mode in modes:
   if started>result.get(mode,''):result[mode]=started
 return result

def _version_tuple(value):
 try:return tuple(int(part) for part in str(value).split('.'))
 except ValueError:return ()
def _table_rows(entry,name):
 path=Path(entry['plugin_root'])/entry['plugin_id']/name
 if path.is_symlink() or not path.is_file():return []
 try:
  with path.open(encoding='utf-8',newline='') as handle:return list(csv.DictReader(handle))
 except (OSError,UnicodeError,csv.Error):return []
def _module_diff(current,candidate):
 """Was eine andere Fassung aendert (#486 Schritt 2): Jahreswerte (alt, neu, Fundstelle der neuen) und die Zahl geaenderter Regeln."""
 key=lambda row:(int(row['tax_year']),row['value_code'])
 old={key(row):row['value_decimal'] for row in _table_rows(current,'annual-legal-values.csv')}
 new={key(row):row for row in _table_rows(candidate,'annual-legal-values.csv')}
 citations={row['legal_reference_code']:row['citation'] for row in _table_rows(candidate,'legal-references.csv')}
 changes=[{'tax_year':year,'value_code':code,'old_value_decimal':old.get((year,code)),'new_value_decimal':(new[(year,code)]['value_decimal'] if (year,code) in new else None),
           'citation':(citations.get(new[(year,code)].get('legal_reference_code') or '') if (year,code) in new else None)}
          for year,code in sorted(set(old)|set(new)) if old.get((year,code))!=(new[(year,code)]['value_decimal'] if (year,code) in new else None)]
 rules=lambda entry:{json.dumps(row,sort_keys=True) for row in _table_rows(entry,'rule-matrix.csv')}
 return changes[:200],len(rules(current)^rules(candidate))
def tax_ui_overview_v1(store,ctx,portfolio_ref,tax_year,authorized_catalog,plugin_root=None):
 valid_ref(portfolio_ref,'pfr_')
 if not isinstance(tax_year,int) or not 1900<=tax_year<=9999 or not isinstance(authorized_catalog,Mapping):blocked('tax_ui_catalog_invalid')
 con=_ui_connect(store,ctx,True)
 try:
  classifications,parameters=_current_configuration(con,portfolio_ref,tax_year);plugins=list(tax_ui_plugin_catalog_v1(plugin_root));selections=[];readiness=[]
  # Alle Fassungen, auch die im Datenraum (#486 Schritt 2); die Oberflaeche sieht davon nur Version, Herkunft und einen Schluessel.
  from migrations.reference.tax_module_catalog_v1 import tax_module_catalog_v1,tax_module_key_v1
  modules=tax_module_catalog_v1(Path(store).parent.parent,plugin_root);module_of={};updates=[]
  type_classifications=_type_classifications(con,portfolio_ref)
  active_assets=[a for a in authorized_catalog.get('assets',()) if a.get('status')=='active']
  # Ein Asset gilt als klassifiziert, wenn es einen eigenen Eintrag hat oder
  # sein Typ eine Vorgabe traegt. Ohne diese Aufloesung blieb die Bereitschaft
  # 'classification_required', bis jedes einzelne Asset erfasst war.
  # Eine Vorgabe je Typ gilt erst ab ihrem Jahr - das Modul prueft genau das. Bis hierhin zaehlte die
  # Bereitschaft sie fuer jedes Jahr mit und meldete fuer fruehere Jahre "bereit", waehrend das Modul
  # dort jede Zeile als nicht eingeordnet abwies.
  in_year=[x for x in type_classifications if x['effective_from_year']<=tax_year and (x['effective_to_year'] is None or x['effective_to_year']>=tax_year)]
  resolved,missing_assets=_resolved_classifications(classifications,in_year,active_assets)
  definitions=list(csv.DictReader(PARAMETERS.open(encoding='utf-8',newline='')));present={p['parameter_code'] for p in parameters}
  completed=_completed_runs_v1(store,ctx,portfolio_ref);pending={}
  for row in con.execute("SELECT projection_mode,reason_code,created_at_utc FROM tax_projection_invalidation WHERE portfolio_ref=? AND status='pending' ORDER BY created_at_utc",(portfolio_ref,)):
   if row['created_at_utc']>completed.get(row['projection_mode'],''):
    entry=pending.setdefault(row['projection_mode'],{'since':row['created_at_utc'],'reasons':[]})
    if row['reason_code'] not in entry['reasons']:entry['reasons'].append(row['reason_code'])
  for mode in ('realized_event','realized_annual','unrealized_snapshot'):
   # Welches Modul gilt, sagt die juengste Auswahl; fuer welche Jahre es gilt,
   # sagt das Modul selbst. Bis hierhin entschied das Datum der Auswahl: Ein 2026
   # gewaehltes Modul galt fuer kein frueheres Steuerjahr, obwohl es deren
   # Rechtsstand fuehrt - und ein frueheres Datum liess die Fassungskette nicht
   # mehr zu (Festlegung 12.10.2026: das Modul des jeweiligen Jahres ist aktiv).
   row=_current_selection(con,portfolio_ref,mode);selection=None
   if row is not None and row['status']=='active':selection={'selection_ref':row['selection_ref'],'revision_no':row['revision_no'],'portfolio_ref':portfolio_ref,'projection_mode':mode,'plugin_id':row['plugin_id'],'plugin_version':row['plugin_version'],'effective_from':row['effective_from'],'status':row['status']};selections.append(selection)
   # Die gewaehlte Fassung: genau ihr Abdruck, sonst dieselbe Version (dann zaehlt, ob die Regeln gleich sind).
   exact=None if selection is None else next((m for m in modules if (m['plugin_id'],m['plugin_version'],m['rules_fingerprint'],m['manifest_fingerprint'])==(row['plugin_id'],row['plugin_version'],row['rules_fingerprint'],row['manifest_fingerprint'])),None)
   catalog_plugin=exact if exact is not None or selection is None else next((m for m in modules if m['plugin_id']==selection['plugin_id'] and m['plugin_version']==selection['plugin_version']),None)
   if catalog_plugin is not None:module_of[mode]=catalog_plugin
   required_codes={d['parameter_code'] for d in definitions if d['projection_mode']==mode and d['requirement']=='required_when_applicable'}
   applicability=next((p.get('applicability_value') for p in parameters if p['parameter_code']=='church_tax_applicable'),None)
   if applicability=='applicable':required_codes.add('church_tax_rate')
   missing_parameters=sorted(required_codes-present)
   if selection is None:status='no_plugin'
   elif catalog_plugin is None:status='plugin_version_stale'
   # Die Rechnung prueft den Regelabdruck der Auswahl, die Bereitschaft bislang nur Name und Version: Aenderten sich nur die
   # Regeln (Version gleich), stand hier "bereit", und der naechste Steuerschritt hielt an (#527, rc.336).
   elif row['rules_fingerprint']!=catalog_plugin['rules_fingerprint']:status='plugin_rules_changed'
   elif mode not in catalog_plugin['supported_projection_modes']:status='unsupported_mode'
   elif not _module_covers_year(catalog_plugin,tax_year,Path(catalog_plugin['plugin_root'])):status='year_not_covered'
   elif missing_assets:status='classification_required'
   elif missing_parameters:status='parameter_required'
   elif mode in pending:status='stale'
   else:status='ready'
   readiness.append({'projection_mode':mode,'status':status,'missing_asset_refs':missing_assets if status=='classification_required' else [],'missing_parameter_codes':missing_parameters if status=='parameter_required' else [],'disclaimer_code':'model_projection_not_legal_advice',
                     'last_completed_at_utc':completed.get(mode),'pending_since_utc':pending[mode]['since'] if mode in pending else None,'pending_reasons':pending[mode]['reasons'] if mode in pending else []})
  # Welche Fonds tragen nur die geerbte Vorgabe ihres Typs? Der Satz der Vorgabe gilt
  # dann fuer jeden Fonds des Typs - auch fuer Anleihe-ETFs mit 0 % und fuer ETCs, die
  # keine Investmentfonds sind. Das stand nirgends, und die Jahresrechnung wies die
  # Gewinne dieser Papiere um die Teilfreistellung zu niedrig aus
  # (#466). Genannt wird nur, was einen Satz ueber 0 erbt.
  inherited=sorted(({'asset_ref':x['asset_ref'],'asset_type':x.get('asset_type'),'classification_code':x['classification_code'],
                     'partial_exemption_rate_decimal':x['partial_exemption_rate_decimal']}
                    for x in resolved if x.get('origin')=='asset_type' and x['classification_code']=='de_fund'
                    and _decimal(x['partial_exemption_rate_decimal'])>0),key=lambda x:x['asset_ref'])
  # Welche Werte das Modul fuer das Jahr mitbringt und wie veranlagt wird (#498): zur Anzeige neben den eigenen Angaben.
  annual=next((row for row in selections if row['projection_mode']=='realized_annual'),None)
  from migrations.reference.tax_assessment_v1 import TaxAssessmentV1Error,read_tax_assessments_v1,read_tax_portfolio_scope_v1
  try:assessment=read_tax_assessments_v1(Path(store).parent,ctx).get(tax_year)
  except TaxAssessmentV1Error:assessment=None
  # Zaehlt das Portfolio im Jahr zur Veranlagung (#501)? Ohne Angabe ja.
  try:counts=read_tax_portfolio_scope_v1(Path(store).parent,ctx).get(tax_year,True)
  except TaxAssessmentV1Error:counts=True
  module_id=annual['plugin_id'] if annual else PLUGIN_ID
  # Werte und Abdeckung aus der Fassung, die fuer den Jahresmodus gilt (#486 Schritt 2), sonst aus der mitgelieferten.
  annual_module=module_of.get('realized_annual')
  module_root=Path(annual_module['plugin_root']) if annual_module is not None else plugin_root
  # Neue Fassung verfuegbar (#486 Schritt 2): je Modul die hoechste Version im Katalog, die neuer ist als eine der gewaehlten. Uebernommen
  # wird sie fuer alle Projektionsarten, die sie kann (eine hoehere Version soll im Zweifel die bessere Projektion liefern) - eine neue Fassung nur fuer "Je Jahr" zeigte deren Werte, waehrend der Abschluss mit der Fassung
  # von "Je Ereignis" rechnet. Verglichen wird mit der Fassung des Jahresmodus (deren Werte zeigt die Uebersicht), sonst der aeltesten.
  for plugin_id in sorted({m['plugin_id'] for m in module_of.values()}):
   chosen={mode:m for mode,m in module_of.items() if m['plugin_id']==plugin_id}
   oldest=min(chosen.values(),key=lambda m:_version_tuple(m['plugin_version']))
   candidates=[m for m in modules if m['plugin_id']==plugin_id and _version_tuple(m['plugin_version'])>_version_tuple(oldest['plugin_version'])]
   if not candidates:continue
   newest=max(candidates,key=lambda m:(_version_tuple(m['plugin_version']),m['origin']=='shipped'))
   reference=chosen.get('realized_annual',oldest)
   changes,rule_changes=_module_diff(reference,newest)
   updates.append({'plugin_id':plugin_id,'selected_versions':{mode:m['plugin_version'] for mode,m in sorted(chosen.items())},
                   'available_version':newest['plugin_version'],'projection_modes':[mode for mode in ('realized_event','realized_annual','unrealized_snapshot') if mode in newest['supported_projection_modes']],
                   'origin':newest['origin'],'module_key':tax_module_key_v1(newest),'value_changes':changes,'rule_change_count':rule_changes})
  extra={'module_values':_module_values_v1(module_id,tax_year,module_root),'module_coverage':_module_coverage_v1(module_id,tax_year,module_root),'assessment':assessment,'portfolio_counts':counts,
         'module_updates':updates}
  return {**extra,'contract_version':'tax_ui_browser_model_v1','portfolio_ref':portfolio_ref,'tax_year':tax_year,'plugin_catalog':plugins,'selections':selections,'classifications':classifications,'asset_type_classifications':type_classifications,'inherited_partial_exemption_assets':inherited,'resolved_classification_count':len(resolved),'asset_classification_count':len(classifications),'parameters':parameters,'readiness':readiness,'invalidations_pending':sorted(pending),'disclaimer_codes':['model_projection_not_legal_advice','reference_model_no_automatic_legal_update','church_tax_user_confirmation_only'],'provider_access':False,'calculation':False,'canonical_write':False,'browser_context_exposed':False,'filesystem_paths_exposed':False,'fingerprints_exposed':False,'internal_ids_exposed':False}
 finally:con.close()
def tax_ui_projection_inputs_v1(store,ctx,portfolio_ref,tax_year,authorized_catalog=None):
 """Die Eingaben des Modells - Klassifikation je Asset, Parameter je Jahr.

 Das Modell sucht je Asset. Eine Vorgabe je Typ wird deshalb hier auf die
 Assets ihres Typs aufgeloest, statt das Modell zu aendern. Ohne Katalog
 bleiben nur die ausdruecklichen Einzelfaelle (#367, 28.09.2026).
 """
 valid_ref(portfolio_ref,'pfr_');con=_ui_connect(store,ctx,True)
 try:
  classifications,parameters=_current_configuration(con,portfolio_ref,tax_year)
  if authorized_catalog is not None:
   active=[a for a in authorized_catalog.get('assets',()) if a.get('status')=='active']
   resolved,_=_resolved_classifications(classifications,_type_classifications(con,portfolio_ref),active)
   classifications=resolved
  projected=[]
  for x in parameters:
   if x['value_kind']=='applicability':projected.append({'tax_year':x['tax_year'],'parameter_code':x['parameter_code'],'rate_decimal':None,'amount_decimal':None,'applicability_value':x['applicability_value']})
   else:projected.append({'tax_year':x['tax_year'],'parameter_code':x['parameter_code'],'rate_decimal':x['rate_decimal'],'amount_decimal':x['amount_decimal'],'applicability_value':None})
  return {'classifications':[{'asset_ref':x['asset_ref'],'classification_code':x['classification_code'],'tax_bucket':x['tax_bucket'],'partial_exemption_rate_decimal':x['partial_exemption_rate_decimal'],'effective_from_year':x['effective_from_year'],'effective_to_year':x['effective_to_year']} for x in classifications],'parameters':projected}
 finally:con.close()
