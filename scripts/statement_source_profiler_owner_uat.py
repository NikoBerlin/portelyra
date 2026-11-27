#!/usr/bin/env python3
"""Argument-free native entry for one owner-local structural profile read."""
from __future__ import annotations
import csv, hashlib, json, os, sys
from pathlib import Path
from typing import Any, Sequence
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from migrations.reference.statement_source_profiler_owner_uat_gtk_v1 import (gtk_statement_source_profiler_authorization_v1,gtk_statement_source_profiler_review_v1,gtk_statement_source_profiler_selection_v1)
from migrations.reference.statement_source_profiler_owner_uat_v1 import (StatementSourceProfilerOwnerUATError,derive_statement_source_profiler_owner_uat_runtime_v1,run_statement_source_profiler_owner_uat_v1)
_PHRASE="owner_authorized_one_private_source_profile_read_v1"
_MANIFEST=ROOT/'contracts/desktop-statement-source-profiler-owner-uat/v1/source-fingerprints.csv'
_ALLOWED={
 'contracts/desktop-statement-source-profiler-owner-uat/v1/authorization-attempt.schema.json',
 'contracts/desktop-statement-source-profiler-owner-uat/v1/uat-failure.schema.json',
 'contracts/desktop-statement-source-profiler-owner-uat/v1/uat-receipt.schema.json',
 'contracts/desktop-statement-source-profiler/v1/source-fingerprints.csv',
 'docs/decisions/ADR-165-owner-local-one-read-statement-source-profiler-uat.md',
 'migrations/reference/desktop_statement_source_profiler_v1.py',
 'migrations/reference/statement_import_owner_uat_v1.py',
 'migrations/reference/statement_source_profiler_owner_uat_gtk_v1.py',
 'migrations/reference/statement_source_profiler_owner_uat_v1.py',
 'scripts/statement_source_profiler_owner_uat.py',
}
def _verify_bundle()->None:
 try:
  with _MANIFEST.open(encoding='utf-8',newline='') as handle:
   reader=csv.DictReader(handle,strict=True)
   if reader.fieldnames!=['source_id','path','sha256']:raise ValueError('header')
   rows=list(reader)
  ids=[x['source_id'] for x in rows]
  if len(rows)!=len(_ALLOWED) or len(ids)!=len(set(ids)) or ids!=sorted(ids) or {x['path'] for x in rows}!=_ALLOWED:raise ValueError('inventory')
  for row in rows:
   if hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()!=row['sha256']:raise ValueError('hash')
 except Exception:raise StatementSourceProfilerOwnerUATError('statement_source_profiler_owner_uat_source_bundle_invalid') from None
def _line(x:dict[str,Any])->str:return json.dumps(x,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(",",":"))
def _failure(code:str)->dict[str,Any]:return {"activation_authorized":False,"automatic_retry":False,"canonical_write":False,"cash_write":False,"network_access":False,"private_values_published":False,"profile_revision_created":False,"provider_access":False,"route_rules_created":False,"source_path_exposed":False,"statement_source_profiler_owner_uat_public_failure_version":1,"status":code,"tax_write":False,"time_zone_inferred":False}
def _runtime()->tuple[Path,str]:
    if os.environ.get("PORTELYRA_STATEMENT_PROFILE_UAT_EXECUTION_AUTHORIZED_INTERNAL")!=_PHRASE:raise StatementSourceProfilerOwnerUATError("statement_source_profiler_owner_uat_execution_not_authorized")
    home=os.environ.get("PORTELYRA_DESKTOP_HOME_INTERNAL")
    if not isinstance(home,str) or not home or "\n" in home or "\r" in home or not Path(home).is_absolute():raise StatementSourceProfilerOwnerUATError("statement_source_profiler_owner_uat_input_invalid")
    return derive_statement_source_profiler_owner_uat_runtime_v1(Path(home))
def _silence()->None:
    fd=None
    try:fd=os.open(os.devnull,os.O_WRONLY|os.O_CLOEXEC);os.dup2(fd,2)
    except OSError:pass
    finally:
        if fd is not None:os.close(fd)
def main(argv:Sequence[str]|None=None)->int:
    _silence();args=tuple(sys.argv[1:] if argv is None else argv)
    try:
        if args:raise StatementSourceProfilerOwnerUATError("statement_source_profiler_owner_uat_input_invalid")
        _verify_bundle();root,binding=_runtime();result=run_statement_source_profiler_owner_uat_v1(root,binding,selection_provider=gtk_statement_source_profiler_selection_v1,authorization_provider=gtk_statement_source_profiler_authorization_v1,review_provider=gtk_statement_source_profiler_review_v1)
        print(_line(result.public_projection()));return 0
    except StatementSourceProfilerOwnerUATError as error:print(_line(_failure(error.code)));return 1
    except Exception:print(_line(_failure("statement_source_profiler_owner_uat_boundary_failed")));return 1
if __name__=="__main__":raise SystemExit(main())
