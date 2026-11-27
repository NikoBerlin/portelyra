"""Create-only ADR-168 recovery for an ADR-167 cancellation left in ADR-165."""
from __future__ import annotations
from datetime import datetime,timezone
import os,re,secrets
from pathlib import Path
from typing import Any,Callable
from migrations.reference.statement_import_owner_uat_v1 import StatementImportOwnerUATError,_fingerprint,_fsync_directory,_read_exact_json,_validate_owner_directory,_write_once
from migrations.reference.statement_source_mapping_owner_uat_v1 import StatementSourceMappingOwnerUATError,_history as _mapping_history,derive_statement_source_mapping_owner_uat_runtime_v1
_SHA=re.compile(r'[0-9a-f]{64}');_NONCE=re.compile(r'[0-9a-f]{32}')
CODES=frozenset({'statement_source_mapping_recovery_ambiguous','statement_source_mapping_recovery_boundary_failed','statement_source_mapping_recovery_confirmation_invalid','statement_source_mapping_recovery_evidence_invalid','statement_source_mapping_recovery_evidence_recovery_required','statement_source_mapping_recovery_not_required','statement_source_mapping_recovery_source_mismatch'})
class StatementSourceMappingRecoveryError(RuntimeError):
 def __init__(self,code):self.code=code if code in CODES else 'statement_source_mapping_recovery_boundary_failed';super().__init__(self.code)
def _fail(c):raise StatementSourceMappingRecoveryError(c)
def _read(path):
 try:return _read_exact_json(path)[0]
 except StatementImportOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
def _valid_fp(v,field):return v.get(field)==_fingerprint({k:x for k,x in v.items() if k!=field})
def _write(directory,name,value):
 try:_write_once(directory/name,value);_fsync_directory(directory)
 except StatementImportOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
def derive_statement_source_mapping_recovery_runtime_v1(desktop_home:Path):
 mapping,profiler,context=derive_statement_source_mapping_owner_uat_runtime_v1(desktop_home);return mapping.parent/'statement_source_mapping_recovery_v1',mapping,profiler,context
def recover_statement_source_mapping_cancelled_attempt_v1(recovery_root:Path,mapping_root:Path,profiler_root:Path,context_binding_sha256:str,*,confirmation_provider:Callable[[dict[str,Any]],Any],now_provider=None,nonce_provider=None):
 old=os.umask(0o077)
 try:
  if any(not p.is_absolute() for p in (recovery_root,mapping_root,profiler_root)) or _SHA.fullmatch(context_binding_sha256 or '') is None:_fail('statement_source_mapping_recovery_evidence_invalid')
  for root in (mapping_root,profiler_root):
   try:_validate_owner_directory(root,create=False)
   except StatementImportOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
  if recovery_root.exists():
   try:_validate_owner_directory(recovery_root,create=False)
   except StatementImportOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
   for d in sorted(recovery_root.iterdir()):
    if re.fullmatch(r'recovery_[0-9a-f]{32}',d.name) is None:_fail('statement_source_mapping_recovery_evidence_invalid')
    try:_validate_owner_directory(d,create=False)
    except StatementImportOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
    names=sorted(x.name for x in d.iterdir())
    if names==['recovery-attempt.json']:_fail('statement_source_mapping_recovery_evidence_recovery_required')
    if names!=['recovery-attempt.json','recovery-receipt.json']:_fail('statement_source_mapping_recovery_evidence_invalid')
    prior_attempt=_read(d/'recovery-attempt.json');prior_receipt=_read(d/'recovery-receipt.json')
    if not _valid_fp(prior_attempt,'recovery_attempt_fingerprint') or not _valid_fp(prior_receipt,'recovery_receipt_fingerprint') or prior_receipt.get('recovery_attempt_fingerprint')!=prior_attempt.get('recovery_attempt_fingerprint') or prior_attempt.get('private_source_read_authorized') is not False or prior_receipt.get('private_source_read') is not False:_fail('statement_source_mapping_recovery_evidence_invalid')
  try:_mapping_history(mapping_root,context_binding_sha256)
  except StatementSourceMappingOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
  pending=[]
  for d in sorted(profiler_root.iterdir()):
   if re.fullmatch(r'profile_uat_[0-9a-f]{32}',d.name) is None:_fail('statement_source_mapping_recovery_evidence_invalid')
   try:_validate_owner_directory(d,create=False)
   except StatementImportOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
   names=sorted(x.name for x in d.iterdir())
   if names==['authorization-attempt.json']:pending.append((d,_read(d/'authorization-attempt.json')));continue
   if names not in (['authorization-attempt.json','uat-failure.json'],['authorization-attempt.json','uat-receipt.json']):_fail('statement_source_mapping_recovery_evidence_invalid')
   historical_attempt=_read(d/'authorization-attempt.json');terminal_name=names[1];terminal=_read(d/terminal_name);field='failure_fingerprint' if terminal_name=='uat-failure.json' else 'receipt_fingerprint'
   if not _valid_fp(historical_attempt,'attempt_fingerprint') or historical_attempt.get('context_binding_sha256')!=context_binding_sha256 or not _valid_fp(terminal,field) or terminal.get('attempt_fingerprint')!=historical_attempt.get('attempt_fingerprint') or terminal.get('source_path_retained') is not False or terminal.get('private_values_published') is not False:_fail('statement_source_mapping_recovery_evidence_invalid')
  if not pending:_fail('statement_source_mapping_recovery_not_required')
  if len(pending)!=1:_fail('statement_source_mapping_recovery_ambiguous')
  target,profile_attempt=pending[0]
  if not _valid_fp(profile_attempt,'attempt_fingerprint') or profile_attempt.get('context_binding_sha256')!=context_binding_sha256:_fail('statement_source_mapping_recovery_evidence_invalid')
  matches=[]
  for d in sorted(mapping_root.iterdir()):
   try:_validate_owner_directory(d,create=False)
   except StatementImportOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
   if not (d/'mapping-attempt.json').exists() or not (d/'mapping-failure.json').exists():continue
   attempt=_read(d/'mapping-attempt.json');failure=_read(d/'mapping-failure.json')
   if not _valid_fp(attempt,'attempt_fingerprint') or not _valid_fp(failure,'failure_fingerprint'):_fail('statement_source_mapping_recovery_evidence_invalid')
   if attempt.get('context_binding_sha256')==context_binding_sha256 and attempt.get('selection_binding_sha256')==profile_attempt.get('selection_binding_sha256') and failure.get('attempt_fingerprint')==attempt.get('attempt_fingerprint') and failure.get('failure_code')=='statement_source_mapping_owner_uat_mapping_cancelled':matches.append((attempt,failure))
  if len(matches)!=1:_fail('statement_source_mapping_recovery_source_mismatch')
  mapping_attempt,mapping_failure=matches[0];preview={'automatic_retry_authorized':False,'context_binding_sha256':context_binding_sha256,'mapping_failure_fingerprint':mapping_failure['failure_fingerprint'],'private_source_read_authorized':False,'profile_attempt_fingerprint':profile_attempt['attempt_fingerprint'],'recovery_action':'seal_profiler_terminal_failure_without_source_read','source_path_exposed':False}
  confirmation=confirmation_provider(dict(preview))
  if confirmation!={**preview,'owner_confirms_no_source_reread':True}:_fail('statement_source_mapping_recovery_confirmation_invalid')
  nonce=(nonce_provider or (lambda:secrets.token_hex(16)))()
  if _NONCE.fullmatch(nonce or '') is None:_fail('statement_source_mapping_recovery_boundary_failed')
  try:
   if not recovery_root.exists():_validate_owner_directory(recovery_root,create=True);_fsync_directory(recovery_root.parent)
   else:_validate_owner_directory(recovery_root,create=False)
   evidence=recovery_root/('recovery_'+nonce);_validate_owner_directory(evidence,create=True)
  except StatementImportOwnerUATError:_fail('statement_source_mapping_recovery_evidence_invalid')
  clock=now_provider or (lambda:datetime.now(timezone.utc).replace(microsecond=0));attempt={'context_binding_sha256':context_binding_sha256,'created_at_utc':clock().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),'mapping_failure_fingerprint':mapping_failure['failure_fingerprint'],'private_source_read_authorized':False,'profile_attempt_fingerprint':profile_attempt['attempt_fingerprint'],'status':'recovery_authorization_consumed','version':1};attempt['recovery_attempt_fingerprint']=_fingerprint(attempt);_write(evidence,'recovery-attempt.json',attempt)
  terminal={'activation_authorized':False,'attempt_fingerprint':profile_attempt['attempt_fingerprint'],'automatic_retry':False,'canonical_write':False,'cash_write':False,'failure_code':'statement_source_profiler_owner_uat_boundary_failed','network_access':False,'private_values_published':False,'profile_revision_created':False,'provider_access':False,'route_rules_created':False,'source_path_retained':False,'source_read_attempted':True,'source_read_completed':True,'status':'terminal_failure_new_authorization_required','tax_write':False,'time_zone_inferred':False,'version':1};terminal['failure_fingerprint']=_fingerprint(terminal);_write(target,'uat-failure.json',terminal)
  receipt={'context_binding_sha256':context_binding_sha256,'mapping_failure_fingerprint':mapping_failure['failure_fingerprint'],'private_source_read':False,'profile_failure_fingerprint':terminal['failure_fingerprint'],'recovery_attempt_fingerprint':attempt['recovery_attempt_fingerprint'],'status':'profiler_attempt_recovered_terminal_without_reread','version':1};receipt['recovery_receipt_fingerprint']=_fingerprint(receipt);_write(evidence,'recovery-receipt.json',receipt)
  return {'automatic_retry':False,'owner_evidence_created':True,'private_source_read':False,'source_path_exposed':False,'statement_source_mapping_recovery_public_result_version':1,'status':'profiler_attempt_recovered_terminal_without_reread'}
 finally:os.umask(old)
