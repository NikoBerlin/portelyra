#!/usr/bin/env python3
"""Argument-free native ADR-167 entry. Requires an explicit local confirmation."""
from __future__ import annotations
import csv,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from migrations.reference.statement_source_mapping_owner_uat_gtk_v1 import gtk_statement_source_mapping_owner_review_v1,gtk_statement_source_profiler_authorization_v1,gtk_statement_source_profiler_selection_v1
from migrations.reference.statement_source_mapping_owner_uat_v1 import StatementSourceMappingOwnerUATError,derive_statement_source_mapping_owner_uat_runtime_v1,run_statement_source_mapping_owner_uat_v1
PHRASE='owner_authorized_one_private_source_mapping_read_v1'
MANIFEST=ROOT/'contracts/desktop-statement-source-mapping-owner-uat/v1/source-fingerprints.csv'
ALLOWED={'docs/decisions/ADR-167-owner-local-same-read-statement-mapping-uat.md','scripts/statement_source_mapping_owner_uat.py','migrations/reference/statement_source_mapping_owner_uat_v1.py','migrations/reference/statement_source_mapping_owner_uat_gtk_v1.py','migrations/reference/statement_source_mapping_overlay_v1.py','migrations/reference/desktop_statement_source_profiler_v1.py','migrations/reference/statement_source_profiler_owner_uat_v1.py','migrations/reference/statement_import_owner_uat_v1.py'}
def verify_bundle():
 try:
  with MANIFEST.open(encoding='utf-8',newline='') as h:r=csv.DictReader(h,strict=True);rows=list(r)
  ids=[x['source_id'] for x in rows]
  if r.fieldnames!=['source_id','path','sha256'] or ids!=sorted(ids) or len(ids)!=len(set(ids)) or len(rows)!=len(ALLOWED) or {x['path'] for x in rows}!=ALLOWED:raise ValueError()
  for x in rows:
   if hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest()!=x['sha256']:raise ValueError()
 except Exception:raise StatementSourceMappingOwnerUATError('statement_source_mapping_owner_uat_evidence_invalid') from None
def line(x):return json.dumps(x,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':'))
def failure(code):return {'activation_authorized':False,'candidate_generation_authorized':False,'private_values_published':False,'profile_revision_created':False,'route_rules_active':False,'source_path_exposed':False,'statement_source_mapping_owner_uat_public_failure_version':1,'status':code}
def main(argv=None):
 try:
  fd=os.open(os.devnull,os.O_WRONLY|os.O_CLOEXEC);os.dup2(fd,2);os.close(fd)
  if tuple(sys.argv[1:] if argv is None else argv):raise StatementSourceMappingOwnerUATError('statement_source_mapping_owner_uat_evidence_invalid')
  if os.environ.get('PORTELYRA_STATEMENT_MAPPING_UAT_EXECUTION_AUTHORIZED_INTERNAL')!=PHRASE:raise StatementSourceMappingOwnerUATError('statement_source_mapping_owner_uat_boundary_failed')
  verify_bundle();home=os.environ.get('PORTELYRA_DESKTOP_HOME_INTERNAL')
  if not home or not Path(home).is_absolute():raise StatementSourceMappingOwnerUATError('statement_source_mapping_owner_uat_evidence_invalid')
  mapping,profiler,context=derive_statement_source_mapping_owner_uat_runtime_v1(Path(home));result=run_statement_source_mapping_owner_uat_v1(mapping,profiler,context,selection_provider=gtk_statement_source_profiler_selection_v1,authorization_provider=gtk_statement_source_profiler_authorization_v1,mapping_provider=gtk_statement_source_mapping_owner_review_v1);print(line(result));return 0
 except StatementSourceMappingOwnerUATError as e:print(line(failure(e.code)));return 1
 except Exception:print(line(failure('statement_source_mapping_owner_uat_boundary_failed')));return 1
if __name__=='__main__':raise SystemExit(main())
