#!/usr/bin/env python3
"""Argument-free, read-free ADR-168 recovery entry."""
import csv,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from migrations.reference.statement_source_mapping_recovery_gtk_v1 import gtk_statement_source_mapping_recovery_confirmation_v1
from migrations.reference.statement_source_mapping_recovery_v1 import StatementSourceMappingRecoveryError,derive_statement_source_mapping_recovery_runtime_v1,recover_statement_source_mapping_cancelled_attempt_v1
PHRASE='owner_authorized_read_free_statement_mapping_recovery_v1';MANIFEST=ROOT/'contracts/desktop-statement-source-mapping-recovery/v1/source-fingerprints.csv';ALLOWED={'docs/decisions/ADR-168-read-free-mapping-recovery-and-reward-account-import-scope.md','scripts/statement_source_mapping_recovery.py','migrations/reference/statement_source_mapping_recovery_v1.py','migrations/reference/statement_source_mapping_recovery_gtk_v1.py','migrations/reference/statement_source_mapping_owner_uat_v1.py','migrations/reference/statement_source_profiler_owner_uat_v1.py'}
def verify_bundle():
 try:
  with MANIFEST.open(encoding='utf-8',newline='') as h:r=csv.DictReader(h,strict=True);rows=list(r)
  ids=[x['source_id'] for x in rows]
  if r.fieldnames!=['source_id','path','sha256'] or len(rows)!=len(ALLOWED) or ids!=sorted(ids) or len(ids)!=len(set(ids)) or {x['path'] for x in rows}!=ALLOWED:raise ValueError()
  for x in rows:
   if hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest()!=x['sha256']:raise ValueError()
 except Exception:raise StatementSourceMappingRecoveryError('statement_source_mapping_recovery_evidence_invalid') from None
def main(argv=None):
 try:
  fd=os.open(os.devnull,os.O_WRONLY|os.O_CLOEXEC);os.dup2(fd,2);os.close(fd)
  if tuple(sys.argv[1:] if argv is None else argv) or os.environ.get('PORTELYRA_STATEMENT_MAPPING_RECOVERY_AUTHORIZED_INTERNAL')!=PHRASE:raise StatementSourceMappingRecoveryError('statement_source_mapping_recovery_confirmation_invalid')
  verify_bundle();home=os.environ.get('PORTELYRA_DESKTOP_HOME_INTERNAL')
  if not home or not Path(home).is_absolute():raise StatementSourceMappingRecoveryError('statement_source_mapping_recovery_evidence_invalid')
  recovery,mapping,profiler,context=derive_statement_source_mapping_recovery_runtime_v1(Path(home));result=recover_statement_source_mapping_cancelled_attempt_v1(recovery,mapping,profiler,context,confirmation_provider=gtk_statement_source_mapping_recovery_confirmation_v1);print(json.dumps(result,sort_keys=True,separators=(',',':')));return 0
 except StatementSourceMappingRecoveryError as e:print(json.dumps({'private_source_read':False,'source_path_exposed':False,'status':e.code},sort_keys=True,separators=(',',':')));return 1
if __name__=='__main__':raise SystemExit(main())
