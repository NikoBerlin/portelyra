#!/usr/bin/env python3
"""Argument-free ADR-169 owner-local Reward/Account one-read UAT."""
import csv,hashlib,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from migrations.reference.reward_account_owner_uat_gtk_v2 import gtk_reward_account_authorization_v2,gtk_reward_account_review_v2,gtk_statement_source_profiler_selection_v1
from migrations.reference.reward_account_owner_uat_v2 import RewardAccountOwnerUATError,derive_reward_account_owner_uat_runtime_v2,run_reward_account_owner_uat_v2
from migrations.reference.reward_target_catalog_reader_v1 import RewardTargetCatalogReaderError,load_reward_target_catalog_v1
PHRASE='owner_authorized_reward_account_one_read_uat_v2';MANIFEST=ROOT/'contracts/desktop-reward-account-owner-uat/v2/source-fingerprints.csv';ALLOWED={'docs/decisions/ADR-169-owner-local-one-read-reward-account-preview-uat.md','scripts/reward_account_owner_uat.py','migrations/reference/reward_account_owner_uat_gtk_v2.py','migrations/reference/reward_account_import_preview_v2.py','migrations/reference/statement_reward_source_profiler_v2.py','migrations/reference/reward_account_owner_uat_v2.py','migrations/reference/reward_target_catalog_reader_v1.py','migrations/reference/statement_source_profiler_owner_uat_v1.py','migrations/reference/statement_source_profiler_owner_uat_gtk_v1.py'}
def verify_bundle():
 try:
  with MANIFEST.open(encoding='utf-8',newline='') as h:r=csv.DictReader(h,strict=True);rows=list(r)
  if r.fieldnames!=['source_id','path','sha256'] or len(rows)!=len(ALLOWED) or [x['source_id'] for x in rows]!=sorted(x['source_id'] for x in rows) or len({x['source_id'] for x in rows})!=len(rows) or {x['path'] for x in rows}!=ALLOWED:raise ValueError()
  for x in rows:
   if hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest()!=x['sha256']:raise ValueError()
 except Exception:raise RewardAccountOwnerUATError('reward_account_owner_uat_evidence_invalid') from None
def main(argv=None):
 try:
  fd=os.open(os.devnull,os.O_WRONLY|os.O_CLOEXEC);os.dup2(fd,2);os.close(fd)
  if tuple(sys.argv[1:] if argv is None else argv) or os.environ.get('PORTELYRA_REWARD_ACCOUNT_UAT_AUTHORIZED_INTERNAL')!=PHRASE:raise RewardAccountOwnerUATError('reward_account_owner_uat_authorization_invalid')
  home=os.environ.get('PORTELYRA_DESKTOP_HOME_INTERNAL')
  if not home or not Path(home).is_absolute():raise RewardAccountOwnerUATError('reward_account_owner_uat_evidence_invalid')
  verify_bundle();evidence,profiler,database,context=derive_reward_account_owner_uat_runtime_v2(Path(home));catalog=load_reward_target_catalog_v1(database,context);result=run_reward_account_owner_uat_v2(evidence,profiler,context,catalog,selection_provider=gtk_statement_source_profiler_selection_v1,authorization_provider=gtk_reward_account_authorization_v2,review_provider=gtk_reward_account_review_v2);print(json.dumps(result,sort_keys=True,separators=(',',':')));return 0
 except (RewardAccountOwnerUATError,RewardTargetCatalogReaderError) as e:
  code=e.code if isinstance(e,RewardAccountOwnerUATError) else 'reward_account_owner_uat_boundary_failed';print(json.dumps({'private_values_published':False,'source_path_exposed':False,'status':code,'version':2},sort_keys=True,separators=(',',':')));return 1
if __name__=='__main__':raise SystemExit(main())
