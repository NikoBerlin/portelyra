#!/usr/bin/env python3
"""Server-side CLI boundary for Tax UI v1."""
from __future__ import annotations
import argparse,json,sys
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from workers.reference.durable_storage_v1 import settle_new_directory_v1  # noqa:E402
from migrations.reference.tax_model_plugin_v1 import TaxPluginBlocked,TaxPluginContext,bootstrap_tax_plugin_store_v1  # noqa:E402
from migrations.reference.tax_ui_workspace_v1 import TaxUiBlocked,apply_tax_ui_command_v1,confirm_tax_ui_command_v1,preview_tax_ui_command_v1,tax_ui_authorized_product_catalog_v1,tax_ui_definition_catalog_v1,tax_ui_overview_v1,tax_ui_plugin_catalog_v1,tax_ui_projection_inputs_v1,upgrade_tax_plugin_store_for_ui_v1  # noqa:E402
def add_context(parser):
 for name in ('tenant-id','user-id','data-space-id','actor-id'):parser.add_argument('--'+name,required=True)
def ctx(a):return TaxPluginContext(a.tenant_id,a.user_id,a.data_space_id,a.actor_id)
def emit(value):print(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')))
def parser_v1():
 p=argparse.ArgumentParser(description='Portelyra Product Tax UI Workspace v1');commands=p.add_subparsers(dest='command',required=True)
 init=commands.add_parser('init');init.add_argument('--store',required=True);init.add_argument('--created-at-utc',required=True);add_context(init)
 catalog=commands.add_parser('catalog');catalog.add_argument('--activity-data-space',required=True);add_context(catalog)
 overview=commands.add_parser('overview');overview.add_argument('--store',required=True);overview.add_argument('--activity-data-space',required=True);overview.add_argument('--portfolio-ref',required=True);overview.add_argument('--tax-year',required=True,type=int);add_context(overview)
 preview=commands.add_parser('preview');preview.add_argument('--store',required=True);preview.add_argument('--command-type',required=True);preview.add_argument('--payload-json-stdin',action='store_true',required=True);preview.add_argument('--created-at-utc',required=True);add_context(preview)
 confirm=commands.add_parser('confirm');confirm.add_argument('--store',required=True);confirm.add_argument('--preview-ref',required=True);confirm.add_argument('--confirmed',choices=('yes','no'),required=True);confirm.add_argument('--confirmed-at-utc',required=True);add_context(confirm)
 apply=commands.add_parser('apply');apply.add_argument('--store',required=True);apply.add_argument('--confirmation-ref',required=True);apply.add_argument('--request-ref',required=True);apply.add_argument('--applied-at-utc',required=True);add_context(apply)
 assessment=commands.add_parser('assessment-record');assessment.add_argument('--store',required=True);assessment.add_argument('--tax-year',required=True,type=int);assessment.add_argument('--assessment',required=True,choices=('single','joint'));assessment.add_argument('--recorded-at-utc',required=True);add_context(assessment)
 scope=commands.add_parser('assessment-scope-record');scope.add_argument('--store',required=True);scope.add_argument('--tax-year',required=True,type=int);scope.add_argument('--counts',required=True,choices=('yes','no'));scope.add_argument('--recorded-at-utc',required=True);add_context(scope)
 # Steuermodul aus ZIP (#486 Schritt 2c): Vorschau schreibt nichts; Installation nur bestaetigt und mit genau der gezeigten Vorschau.
 preserve=commands.add_parser('preserve-modules');preserve.add_argument('--store',required=True);add_context(preserve)
 mpreview=commands.add_parser('module-install-preview');mpreview.add_argument('--store',required=True);mpreview.add_argument('--zip',required=True);add_context(mpreview)
 mapply=commands.add_parser('module-install-apply');mapply.add_argument('--store',required=True);mapply.add_argument('--zip',required=True);mapply.add_argument('--preview-fingerprint',required=True)
 mapply.add_argument('--installed-at-utc',required=True);mapply.add_argument('--confirmed',choices=('yes','no'),required=True);add_context(mapply)
 inputs=commands.add_parser('projection-inputs');inputs.add_argument('--store',required=True);inputs.add_argument('--portfolio-ref',required=True);inputs.add_argument('--tax-year',required=True,type=int);add_context(inputs)
 return p
def authorized_catalog(a):return tax_ui_authorized_product_catalog_v1(a.activity_data_space,ctx(a))
def preserve_modules(a):
 """Gewaehlte mitgelieferte Fassungen der Steuermodule im Datenraum ablegen (#486 Schritt 2): Sie bleiben, bis eine neue uebernommen ist.
 Ein Fehler haelt das Kommando nicht an; beim naechsten Oeffnen der Steuereinstellungen wird es erneut versucht."""
 try:
  from migrations.reference.tax_module_catalog_v1 import preserve_selected_tax_modules_v1
  preserve_selected_tax_modules_v1(Path(a.store).parent.parent,ctx(a))
 except Exception:
  pass
def main():
 a=parser_v1().parse_args()
 try:
  if a.command=='init':
   path=Path(a.store)
   if not path.exists():
    settle_new_directory_v1(path.parent)  # #568: von R neu angelegte Ordner, auch ihre gocryptfs.diriv festschreiben
    bootstrap_tax_plugin_store_v1(path,ctx(a),a.created_at_utc)
   upgrade_tax_plugin_store_for_ui_v1(path,ctx(a));preserve_modules(a);emit({'status':'initialized','contract_version':'tax_ui_v1'})
  elif a.command=='catalog':emit({'status':'completed','catalog':authorized_catalog(a),'plugin_catalog':tax_ui_plugin_catalog_v1(),'definition_catalog':tax_ui_definition_catalog_v1()})
  elif a.command=='overview':emit(tax_ui_overview_v1(a.store,ctx(a),a.portfolio_ref,a.tax_year,authorized_catalog(a)))
  elif a.command=='preview':emit(asdict(preview_tax_ui_command_v1(a.store,ctx(a),a.command_type,json.loads(sys.stdin.read()),a.created_at_utc)))
  elif a.command=='confirm':emit(asdict(confirm_tax_ui_command_v1(a.store,ctx(a),a.preview_ref,a.confirmed=='yes',a.confirmed_at_utc)))
  elif a.command=='apply':
   result=apply_tax_ui_command_v1(a.store,ctx(a),a.confirmation_ref,a.request_ref,a.applied_at_utc);preserve_modules(a);emit(asdict(result))
  elif a.command=='assessment-record':
   # Veranlagungsart je Jahr (#498): neben dem Steuerspeicher, im selben Ordner.
   from migrations.reference.tax_assessment_v1 import TaxAssessmentV1Error,record_tax_assessment_v1
   try:emit({'status':'completed','result':record_tax_assessment_v1(Path(a.store).parent,ctx(a),a.tax_year,a.assessment,a.recorded_at_utc,True)})
   except TaxAssessmentV1Error as e:emit({'status':'blocked','code':e.code});return 2
  elif a.command=='assessment-scope-record':
   # Zaehlt das Portfolio im Jahr zur Veranlagung (#501): neben der Veranlagungsart, im selben Speicher.
   from migrations.reference.tax_assessment_v1 import TaxAssessmentV1Error,record_tax_portfolio_scope_v1
   try:emit({'status':'completed','result':record_tax_portfolio_scope_v1(Path(a.store).parent,ctx(a),a.tax_year,a.counts=='yes',a.recorded_at_utc,True)})
   except TaxAssessmentV1Error as e:emit({'status':'blocked','code':e.code});return 2
  elif a.command=='preserve-modules':
   # Von "Alles aktualisieren" (#486 Schritt 2): gewaehlte Fassungen sichern, auch wenn die Steuereinstellungen nie geoeffnet werden.
   # Legt keinen Steuerspeicher an; ohne ihn gibt es nichts zu sichern.
   from migrations.reference.tax_module_catalog_v1 import preserve_selected_tax_modules_v1
   if not Path(a.store).is_file():emit({'status':'completed','result':{'preserved':0,'present':0,'not_shipped':0,'missing':0}})
   else:emit({'status':'completed','result':preserve_selected_tax_modules_v1(Path(a.store).parent.parent,ctx(a))})
  elif a.command in ('module-install-preview','module-install-apply'):
   from migrations.reference.tax_module_install_v1 import TaxModuleInstallBlocked,apply_tax_module_install_v1,preview_tax_module_install_v1
   zip_path=Path(a.zip)
   if zip_path.is_symlink() or not zip_path.is_file() or zip_path.stat().st_size>10*1024*1024:emit({'status':'blocked','code':'tax_module_install_input_invalid'});return 2
   space=Path(a.store).parent.parent
   try:
    if a.command=='module-install-preview':emit({'status':'completed','preview':preview_tax_module_install_v1(space,ctx(a),zip_path.read_bytes())})
    else:emit({'status':'completed','result':apply_tax_module_install_v1(space,ctx(a),zip_path.read_bytes(),a.preview_fingerprint,a.confirmed=='yes',a.installed_at_utc)})
   except TaxModuleInstallBlocked as e:emit({'status':'blocked','code':e.code});return 2
  else:emit(tax_ui_projection_inputs_v1(a.store,ctx(a),a.portfolio_ref,a.tax_year))
 except (TaxUiBlocked,TaxPluginBlocked,json.JSONDecodeError) as e:
  emit({'status':'blocked','code':getattr(e,'code','tax_ui_payload_invalid')});return 2
 except Exception:
  emit({'status':'failed','code':'tax_ui_boundary_failed'});return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
