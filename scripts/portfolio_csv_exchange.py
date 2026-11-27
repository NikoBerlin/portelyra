#!/usr/bin/env python3
"""JSON-stdin boundary for the owner-local Portfolio CSV exchange."""
from __future__ import annotations
import argparse,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.portfolio_csv_exchange_v1 import (  # noqa:E402
 PortfolioCsvContextV1,PortfolioCsvExchangeV1Error,execute_portfolio_csv_export_v1,
 execute_portfolio_csv_import_v1,list_portfolio_csv_import_bundles_v1,
 portfolio_csv_exchange_paths_v1,preview_portfolio_csv_export_v1,preview_portfolio_csv_import_v1,
)

def emit(value):print(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')))
def context(value):return PortfolioCsvContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','desktop_owner'),value.get('role','desktop_owner'))
def write_create(path,value):
 payload=(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':'))+'\n').encode();fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600)
 try:
  with os.fdopen(fd,'wb') as handle:fd=None;handle.write(payload);handle.flush();os.fsync(handle.fileno())
  os.chmod(path,0o600);parent=os.open(path.parent,os.O_RDONLY);os.fsync(parent);os.close(parent)
 finally:
  if fd is not None:os.close(fd)
def public_export(plan,status='pending_confirmation'):
 return {'contract_version':'portfolio_csv_export_preview_v1','status':status,'bundle_handle':'pcb_'+plan.bundle_fingerprint[:24],'record_count':len(plan.records),'asset_file_count':plan.manifest['asset_projection_count'],'account_file_count':plan.manifest['account_projection_count'],'delimiter':',','decimal_mark':',','all_fields_quoted':True,'dimensions':plan.manifest['dimensions'],'confirmation_required':status=='pending_confirmation','product_write':False,'provider_access':False,'network_access':False,'automatic_retry':False}
def resolve_bundle(paths,handle):
 rows=list_portfolio_csv_import_bundles_v1(paths['import_inbox']);matches=[row for row in rows if row['bundle_handle']==handle]
 if len(matches)!=1:raise PortfolioCsvExchangeV1Error('portfolio_csv_bundle_invalid')
 return paths['import_inbox']/matches[0]['bundle_name']
def guarded(paths,operation,fingerprint,callback,recover):
 receipt=paths['receipts']/f'{operation}_{fingerprint[:24]}.json';attempt=paths['attempts']/f'{operation}_{fingerprint[:24]}.json'
 if receipt.is_file():return json.loads(receipt.read_text(encoding='utf-8'))
 if attempt.exists():
  recovered=recover()
  if recovered is None:raise PortfolioCsvExchangeV1Error('portfolio_csv_confirmation_consumed')
  value={'contract_version':1,'operation':operation,'fingerprint':fingerprint,'status':'recovered_completed','result_handle':recovered.name,'product_write':False,'provider_access':False,'automatic_retry':False};write_create(receipt,value);return value
 write_create(attempt,{'contract_version':1,'operation':operation,'fingerprint':fingerprint,'attempt_count':1,'confirmation_consumed':True,'automatic_retry':False})
 try:result=callback();value={'contract_version':1,'operation':operation,'fingerprint':fingerprint,'status':'completed','result_handle':result.name,'product_write':False,'provider_access':False,'automatic_retry':False};write_create(receipt,value);return value
 except Exception as error:
  failure=paths['failures']/f'{operation}_{fingerprint[:24]}.json'
  try:write_create(failure,{'contract_version':1,'operation':operation,'fingerprint':fingerprint,'status':'failed','failure_code':getattr(error,'code','portfolio_csv_boundary_failed'),'automatic_retry':False})
  except FileExistsError:pass
  raise
def main():
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=('paths','initialize','export-preview','export-apply','import-list','import-preview','import-apply'));args=parser.parse_args()
 try:
  payload=json.loads(sys.stdin.read());ctx=context(payload['context']);data_space=Path(payload['data_space_path']).resolve();create=args.command=='initialize';paths=portfolio_csv_exchange_paths_v1(data_space,ctx,create=create)
  if args.command=='paths':emit({'status':'available','product_data_path':str(data_space),'import_inbox_path':str(paths['import_inbox']),'export_path':str(paths['exports']),'staged_import_path':str(paths['imports']),'initialized':all(paths[key].is_dir() for key in ('import_inbox','exports','imports'))})
  elif args.command=='initialize':emit({'status':'initialized','product_data_path':str(data_space),'import_inbox_path':str(paths['import_inbox']),'export_path':str(paths['exports']),'staged_import_path':str(paths['imports']),'initialized':True,'product_write':False,'provider_access':False})
  elif args.command.startswith('export'):
   plan=preview_portfolio_csv_export_v1(payload['canonical_path'],data_space,ctx)
   if args.command=='export-preview':emit({'status':'previewed','preview':public_export(plan)})
   else:
    if payload.get('confirmed') is not True:raise PortfolioCsvExchangeV1Error('portfolio_csv_confirmation_required')
    if payload.get('bundle_handle')!='pcb_'+plan.bundle_fingerprint[:24]:raise PortfolioCsvExchangeV1Error('portfolio_csv_source_changed')
    def recover_export():
     target=paths['exports']/f'portfolio-export-{plan.bundle_fingerprint[:24]}'
     return target if target.is_dir() and preview_portfolio_csv_import_v1(target).bundle_fingerprint==plan.bundle_fingerprint else None
    result=guarded(paths,'export',plan.bundle_fingerprint,lambda:execute_portfolio_csv_export_v1(plan,paths['exports']),recover_export);emit({'status':'completed','result':{**public_export(plan,'completed'),'bundle_name':result['result_handle'],'recovery_status':result['status']}})
  elif args.command=='import-list':
   rows=list_portfolio_csv_import_bundles_v1(paths['import_inbox']);emit({'status':'available','bundles':[{key:value for key,value in row.items() if key!='bundle_fingerprint'} for row in rows]})
  else:
   bundle=resolve_bundle(paths,payload['bundle_handle']);plan=preview_portfolio_csv_import_v1(bundle);preview={'contract_version':'portfolio_csv_import_preview_v1','status':'pending_confirmation','bundle_handle':'pcb_'+plan.bundle_fingerprint[:24],'record_count':len(plan.records),'asset_file_count':plan.manifest['asset_projection_count'],'account_file_count':plan.manifest['account_projection_count'],'redundancy_status':'exact','catalog_apply':'separate_confirmation_required','coupled_transaction_apply':'separate_confirmation_required','activity_apply':'separate_per_draft_confirmation_required','cash_coverage_apply':'separate_reviewed_candidate_confirmation_required','confirmation_required':True,'product_write':False,'provider_access':False,'network_access':False,'automatic_retry':False}
   if args.command=='import-preview':emit({'status':'previewed','preview':preview})
   else:
    if payload.get('confirmed') is not True:raise PortfolioCsvExchangeV1Error('portfolio_csv_confirmation_required')
    def recover_import():
     target=paths['imports']/f'imp_{plan.bundle_fingerprint[:24]}';receipt=target/'import-receipt.json'
     if not target.is_dir() or not receipt.is_file():return None
     value=json.loads(receipt.read_text(encoding='utf-8'))
     return target if value.get('bundle_fingerprint')==plan.bundle_fingerprint and value.get('status')=='staged_lossless_ready_for_domain_handoffs' else None
    result=guarded(paths,'import',plan.bundle_fingerprint,lambda:execute_portfolio_csv_import_v1(plan,paths['imports'],ctx),recover_import);emit({'status':'completed','result':{**preview,'status':'staged_lossless_ready_for_domain_handoffs','staged_import_handle':result['result_handle'],'recovery_status':result['status'],'confirmation_required':False}})
 except (PortfolioCsvExchangeV1Error,KeyError,TypeError,json.JSONDecodeError) as error:emit({'status':'blocked','code':getattr(error,'code','portfolio_csv_source_invalid')});return 2
 except Exception:emit({'status':'failed','code':'portfolio_csv_boundary_failed'});return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
