"""ADR-167 same-read orchestration for ADR-165 profiling and ADR-166 mapping."""
from __future__ import annotations
from datetime import datetime,timezone
import os,re,secrets
from pathlib import Path
from typing import Any,Callable
from migrations.reference.statement_import_owner_uat_v1 import StatementImportOwnerUATError,_canonical,_fingerprint,_fsync_directory,_read_exact_json,_validate_owner_directory,_write_once
from migrations.reference.statement_source_mapping_overlay_v1 import StatementSourceMappingOverlayError,build_statement_source_mapping_overlay_v1
from migrations.reference.statement_source_profiler_owner_uat_v1 import StatementSourceProfilerOwnerUATError,derive_statement_source_profiler_owner_uat_runtime_v1,run_statement_source_profiler_owner_uat_v1
_SHA=re.compile(r'[0-9a-f]{64}');_NONCE=re.compile(r'[0-9a-f]{32}')
CODES=frozenset({'statement_source_mapping_owner_uat_boundary_failed','statement_source_mapping_owner_uat_evidence_exists','statement_source_mapping_owner_uat_evidence_invalid','statement_source_mapping_owner_uat_evidence_recovery_required','statement_source_mapping_owner_uat_mapping_cancelled','statement_source_mapping_owner_uat_mapping_invalid','statement_source_mapping_owner_uat_profiler_failed'})
class StatementSourceMappingOwnerUATError(RuntimeError):
 def __init__(self,code):self.code=code if code in CODES else 'statement_source_mapping_owner_uat_boundary_failed';super().__init__(self.code)
def _fail(c):raise StatementSourceMappingOwnerUATError(c)
def derive_statement_source_mapping_owner_uat_runtime_v1(desktop_home:Path):
 profiler_root,context=derive_statement_source_profiler_owner_uat_runtime_v1(desktop_home)
 return profiler_root.parent/'statement_source_mapping_owner_uat_v1',profiler_root,context
def _write(directory,name,value):
 try:_write_once(directory/name,value);_fsync_directory(directory)
 except StatementImportOwnerUATError:_fail('statement_source_mapping_owner_uat_evidence_invalid')
def _history(root,context):
 for d in sorted(root.iterdir()):
  if not re.fullmatch(r'mapping_uat_[0-9a-f]{32}',d.name):_fail('statement_source_mapping_owner_uat_evidence_invalid')
  try:_validate_owner_directory(d,create=False)
  except StatementImportOwnerUATError:_fail('statement_source_mapping_owner_uat_evidence_invalid')
  names=sorted(x.name for x in d.iterdir())
  if names==['mapping-attempt.json']:_fail('statement_source_mapping_owner_uat_evidence_recovery_required')
  if names not in (['mapping-attempt.json','mapping-failure.json'],['mapping-attempt.json','mapping-failure.json','mapping-overlay.json'],['mapping-attempt.json','mapping-overlay.json','mapping-receipt.json']):_fail('statement_source_mapping_owner_uat_evidence_invalid')
  values=[]
  for n in names:
   try:v,_raw=_read_exact_json(d/n)
   except StatementImportOwnerUATError:_fail('statement_source_mapping_owner_uat_evidence_invalid')
   values.append(v)
  attempt=values[0]
  if attempt.get('context_binding_sha256')!=context or attempt.get('attempt_fingerprint')!=_fingerprint({k:v for k,v in attempt.items() if k!='attempt_fingerprint'}):_fail('statement_source_mapping_owner_uat_evidence_invalid')
  if 'mapping-overlay.json' in names:
   pending=values[names.index('mapping-overlay.json')]
   if pending.get('mapping_attempt_fingerprint')!=attempt['attempt_fingerprint'] or pending.get('overlay_fingerprint')!=_fingerprint({k:v for k,v in pending.items() if k not in {'overlay_fingerprint','mapping_attempt_fingerprint'}}):_fail('statement_source_mapping_owner_uat_evidence_invalid')
  terminal_name='mapping-failure.json' if 'mapping-failure.json' in names else 'mapping-receipt.json';terminal=values[names.index(terminal_name)];field='failure_fingerprint' if terminal_name=='mapping-failure.json' else 'receipt_fingerprint'
  if terminal.get(field)!=_fingerprint({k:v for k,v in terminal.items() if k!=field}) or terminal.get('attempt_fingerprint')!=attempt['attempt_fingerprint'] or terminal.get('source_path_retained') is not False or terminal.get('private_values_published') is not False:_fail('statement_source_mapping_owner_uat_evidence_invalid')
def run_statement_source_mapping_owner_uat_v1(mapping_root:Path,profiler_uat_root:Path,context_binding_sha256:str,*,selection_provider:Callable[[],Any],authorization_provider:Callable[[dict[str,Any]],Any],mapping_provider:Callable[[dict[str,Any]],Any],now_provider:Callable[[],datetime]|None=None,nonce_provider:Callable[[],str]|None=None)->dict[str,Any]:
 old=os.umask(0o077);directory=None;attempt=None;overlay=None;mapping_error=None;private_review_binding=None
 try:
  if not mapping_root.is_absolute() or not profiler_uat_root.is_absolute() or _SHA.fullmatch(context_binding_sha256 or '') is None:_fail('statement_source_mapping_owner_uat_evidence_invalid')
  try:
   if mapping_root.exists():_validate_owner_directory(mapping_root,create=False);_history(mapping_root,context_binding_sha256)
   else:_validate_owner_directory(mapping_root,create=True);_fsync_directory(mapping_root.parent)
  except StatementImportOwnerUATError:_fail('statement_source_mapping_owner_uat_evidence_invalid')
  nonce=(nonce_provider or (lambda:secrets.token_hex(16)))()
  if _NONCE.fullmatch(nonce or '') is None:_fail('statement_source_mapping_owner_uat_boundary_failed')
  directory=mapping_root/('mapping_uat_'+nonce)
  clock=now_provider or (lambda:datetime.now(timezone.utc).replace(microsecond=0))
  profile_before=set(profiler_uat_root.iterdir()) if profiler_uat_root.exists() else set()
  def authorize(preview):
   nonlocal attempt
   value=authorization_provider(preview)
   if value is None:return None
   try:_validate_owner_directory(directory,create=True)
   except StatementImportOwnerUATError:_fail('statement_source_mapping_owner_uat_evidence_exists')
   attempt={'activation_authorized':False,'automatic_retry_authorized':False,'context_binding_sha256':context_binding_sha256,'created_at_utc':clock().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),'profiler_authorization_sha256':_fingerprint(value),'selection_binding_sha256':preview['selection_binding_sha256'],'source_path_retained':False,'status':'mapping_authorization_consumed','version':1};attempt['attempt_fingerprint']=_fingerprint(attempt);_write(directory,'mapping-attempt.json',attempt);return value
  def review(private_review):
   nonlocal overlay,mapping_error,private_review_binding
   private_review_binding=private_review.get('review_binding_sha256')
   mapping_review={k:v for k,v in private_review.items() if k!='review_binding_sha256'}
   if private_review_binding!=_fingerprint(mapping_review):_fail('statement_source_mapping_owner_uat_evidence_invalid')
   decision=mapping_provider(private_review)
   if decision is None:
    mapping_error=StatementSourceMappingOwnerUATError('statement_source_mapping_owner_uat_mapping_cancelled');raise mapping_error
   try:overlay=build_statement_source_mapping_overlay_v1(mapping_review,decision)
   except StatementSourceMappingOverlayError as e:
    mapping_error=StatementSourceMappingOwnerUATError('statement_source_mapping_owner_uat_mapping_invalid');raise mapping_error from e
   pending=dict(overlay);pending['mapping_attempt_fingerprint']=attempt['attempt_fingerprint'];_write(directory,'mapping-overlay.json',pending)
   return {'decision':'observe_disabled','no_activation_acknowledged':True,'private_values_local_only_acknowledged':True,'review_binding_sha256':private_review['review_binding_sha256']}
  try:profile=run_statement_source_profiler_owner_uat_v1(profiler_uat_root,context_binding_sha256,selection_provider=selection_provider,authorization_provider=authorize,review_provider=review,now_provider=clock)
  except StatementSourceProfilerOwnerUATError as e:
   if mapping_error is not None:raise mapping_error
   raise StatementSourceMappingOwnerUATError('statement_source_mapping_owner_uat_profiler_failed') from e
  if attempt is None or overlay is None:_fail('statement_source_mapping_owner_uat_mapping_invalid')
  profile_new=set(profiler_uat_root.iterdir())-profile_before
  if len(profile_new)!=1:_fail('statement_source_mapping_owner_uat_evidence_invalid')
  try:profile_receipt,_raw=_read_exact_json(next(iter(profile_new))/'uat-receipt.json')
  except StatementImportOwnerUATError:_fail('statement_source_mapping_owner_uat_evidence_invalid')
  if profile_receipt.get('private_review_sha256')!=private_review_binding:_fail('statement_source_mapping_owner_uat_evidence_invalid')
  receipt={'activation_authorized':False,'attempt_fingerprint':attempt['attempt_fingerprint'],'automatic_retry':False,'candidate_generation_authorized':False,'canonical_write':False,'cash_write':False,'network_access':False,'completed_at_utc':clock().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),'context_binding_sha256':context_binding_sha256,'overlay_fingerprint':overlay['overlay_fingerprint'],'private_values_published':False,'profile_revision_created':False,'provider_access':False,'profiler_receipt_fingerprint':profile_receipt['receipt_fingerprint'],'profiler_review_binding_sha256':private_review_binding,'profiler_status':profile.status,'route_rules_active':False,'source_path_retained':False,'tax_write':False,'status':'owner_mapping_overlay_sealed_disabled','version':1};receipt['receipt_fingerprint']=_fingerprint(receipt);_write(directory,'mapping-receipt.json',receipt)
  return {'activation_authorized':False,'candidate_generation_authorized':False,'owner_evidence_created':True,'private_values_published':False,'profile_revision_created':False,'route_rules_active':False,'source_read_attempt_count':1,'statement_source_mapping_owner_uat_public_result_version':1,'status':'owner_mapping_overlay_sealed_disabled'}
 except StatementSourceMappingOwnerUATError as e:
  if directory is not None and attempt is not None and not (directory/'mapping-receipt.json').exists():
   failure={'activation_authorized':False,'attempt_fingerprint':attempt['attempt_fingerprint'],'automatic_retry':False,'candidate_generation_authorized':False,'canonical_write':False,'cash_write':False,'failure_code':e.code,'network_access':False,'private_values_published':False,'profile_revision_created':False,'provider_access':False,'route_rules_active':False,'source_path_retained':False,'tax_write':False,'status':'terminal_failure_new_authorization_required','version':1};failure['failure_fingerprint']=_fingerprint(failure);_write(directory,'mapping-failure.json',failure)
  raise
 finally:os.umask(old)
