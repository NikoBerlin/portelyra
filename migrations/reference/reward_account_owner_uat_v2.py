"""ADR-169 one-read owner UAT for focused Reward/Source-Account mapping."""
from __future__ import annotations
from datetime import datetime,timezone
import os,re,secrets
from pathlib import Path
from typing import Any,Callable
from migrations.reference.reward_account_import_preview_v2 import RewardAccountImportPreviewError,build_reward_account_import_preview_v2
from migrations.reference.statement_import_owner_uat_v1 import StatementImportOwnerUATError,_fingerprint,_fsync_directory,_read_exact_json,_validate_owner_directory,_write_once
from migrations.reference.statement_reward_source_profiler_v2 import StatementRewardSourceProfilerError,inspect_statement_reward_source_bytes_v2,project_statement_reward_source_review_v2
from migrations.reference.statement_source_profiler_owner_uat_v1 import StatementSourceProfilerOwnerUATError,derive_statement_source_profiler_owner_uat_runtime_v1,run_statement_source_profiler_owner_uat_v1
_SHA=re.compile(r'[0-9a-f]{64}');_NONCE=re.compile(r'[0-9a-f]{32}')
ATTEMPT_KEYS=frozenset({'activation_authorized','attempt_fingerprint','automatic_retry_authorized','context_binding_sha256','created_at_utc','private_values_published','profiler_authorization_sha256','selection_binding_sha256','source_path_retained','status','version'})
SEAL_KEYS=frozenset({'attempt_fingerprint','candidate_generation_authorized','private_values_published','preview_fingerprint','reward_tuple_sha256','row_count','seal_fingerprint','selected_source_account_sha256','selected_source_asset_sha256','silent_drop_count','source_balance_disposition','source_path_retained','status','target_account_option_sha256','target_asset_option_sha256','terminal_disposition_counts','time_zone_sha256','valuation_mode','version'})
RECEIPT_KEYS=frozenset({'activation_authorized','attempt_fingerprint','automatic_retry','candidate_generation_authorized','canonical_write','cash_write','context_binding_sha256','network_access','private_values_published','profile_revision_created','profiler_receipt_fingerprint','provider_access','receipt_fingerprint','seal_fingerprint','source_path_retained','source_read_attempt_count','status','tax_write','version'})
FAILURE_KEYS=frozenset({'attempt_fingerprint','automatic_retry','failure_code','failure_fingerprint','private_values_published','source_path_retained','status','version'})
CODES=frozenset({'reward_account_owner_uat_authorization_invalid','reward_account_owner_uat_boundary_failed','reward_account_owner_uat_cancelled','reward_account_owner_uat_evidence_invalid','reward_account_owner_uat_evidence_recovery_required','reward_account_owner_uat_profiler_failed','reward_account_owner_uat_review_invalid'})
class RewardAccountOwnerUATError(RuntimeError):
 def __init__(self,code):self.code=code if code in CODES else 'reward_account_owner_uat_boundary_failed';super().__init__(self.code)
def _fail(c):raise RewardAccountOwnerUATError(c)
def _write(d,n,v):
 try:_write_once(d/n,v);_fsync_directory(d)
 except StatementImportOwnerUATError:_fail('reward_account_owner_uat_evidence_invalid')
def _read(p):
 try:return _read_exact_json(p)[0]
 except StatementImportOwnerUATError:_fail('reward_account_owner_uat_evidence_invalid')
def _fp(v,f):return v.get(f)==_fingerprint({k:x for k,x in v.items() if k!=f})
def derive_reward_account_owner_uat_runtime_v2(desktop_home:Path):
 profiler,context=derive_statement_source_profiler_owner_uat_runtime_v1(desktop_home);return profiler.parent/'reward_account_owner_uat_v2',profiler,profiler.parent/'canonical.sqlite',context
def _history(root,context):
 for d in sorted(root.iterdir()):
  if re.fullmatch(r'reward_uat_[0-9a-f]{32}',d.name) is None:_fail('reward_account_owner_uat_evidence_invalid')
  try:_validate_owner_directory(d,create=False)
  except StatementImportOwnerUATError:_fail('reward_account_owner_uat_evidence_invalid')
  names=sorted(x.name for x in d.iterdir())
  if names==['reward-attempt.json']:_fail('reward_account_owner_uat_evidence_recovery_required')
  if names not in (['reward-attempt.json','reward-failure.json'],['reward-attempt.json','reward-preview-seal.json','reward-receipt.json']):_fail('reward_account_owner_uat_evidence_invalid')
  attempt=_read(d/'reward-attempt.json');terminal=_read(d/names[-1]);field='failure_fingerprint' if names[-1]=='reward-failure.json' else 'receipt_fingerprint'
  expected_terminal=FAILURE_KEYS if names[-1]=='reward-failure.json' else RECEIPT_KEYS
  if set(attempt)!=ATTEMPT_KEYS or set(terminal)!=expected_terminal or not _fp(attempt,'attempt_fingerprint') or attempt.get('context_binding_sha256')!=context or not _fp(terminal,field) or terminal.get('attempt_fingerprint')!=attempt.get('attempt_fingerprint') or terminal.get('private_values_published') is not False or terminal.get('source_path_retained') is not False or any(attempt.get(k) is not False for k in ('activation_authorized','automatic_retry_authorized','private_values_published','source_path_retained')) or (names[-1]=='reward-receipt.json' and (terminal.get('source_read_attempt_count')!=1 or any(terminal.get(k) is not False for k in ('activation_authorized','automatic_retry','candidate_generation_authorized','canonical_write','cash_write','network_access','private_values_published','profile_revision_created','provider_access','source_path_retained','tax_write')))) or (names[-1]=='reward-failure.json' and terminal.get('automatic_retry') is not False):_fail('reward_account_owner_uat_evidence_invalid')
  if 'reward-preview-seal.json' in names:
   seal=_read(d/'reward-preview-seal.json')
   if set(seal)!=SEAL_KEYS or not _fp(seal,'seal_fingerprint') or seal.get('attempt_fingerprint')!=attempt.get('attempt_fingerprint') or terminal.get('seal_fingerprint')!=seal.get('seal_fingerprint') or seal.get('silent_drop_count')!=0 or any(seal.get(k) is not False for k in ('candidate_generation_authorized','private_values_published','source_path_retained')):_fail('reward_account_owner_uat_evidence_invalid')
def run_reward_account_owner_uat_v2(evidence_root:Path,profiler_root:Path,context_binding_sha256:str,catalog:dict[str,Any],*,selection_provider:Callable[[],Any],authorization_provider:Callable[[dict[str,Any]],Any],review_provider:Callable[[dict[str,Any],dict[str,Any]],Any],now_provider=None,nonce_provider=None):
 old=os.umask(0o077);directory=None;attempt=None;seal=None;inner_error=None
 try:
  if any(not x.is_absolute() for x in (evidence_root,profiler_root)) or _SHA.fullmatch(context_binding_sha256 or '') is None or not isinstance(catalog,dict) or set(catalog)!={'account_options','asset_options','portfolio_options','private_canonical_ids_exposed','query_only'} or catalog.get('private_canonical_ids_exposed') is not False or catalog.get('query_only') is not True or any(not isinstance(catalog.get(k),list) or not catalog[k] for k in ('account_options','asset_options','portfolio_options')):_fail('reward_account_owner_uat_evidence_invalid')
  try:
   if evidence_root.exists():_validate_owner_directory(evidence_root,create=False);_history(evidence_root,context_binding_sha256)
   else:_validate_owner_directory(evidence_root,create=True);_fsync_directory(evidence_root.parent)
  except StatementImportOwnerUATError:_fail('reward_account_owner_uat_evidence_invalid')
  nonce=(nonce_provider or (lambda:secrets.token_hex(16)))()
  if _NONCE.fullmatch(nonce or '') is None:_fail('reward_account_owner_uat_boundary_failed')
  directory=evidence_root/('reward_uat_'+nonce);clock=now_provider or (lambda:datetime.now(timezone.utc).replace(microsecond=0))
  def authorize(preview):
   nonlocal attempt
   value=authorization_provider({**preview,'reward_scope':'one_source_asset_account_to_one_existing_target_asset_account'})
   if value is None:return None
   base_required={'activation_authorized','authorization_id','automatic_retry_authorized','canonical_write_authorized','context_binding_sha256','private_values_local_only_acknowledged','profiler_binding_sha256','provider_access_authorized','selection_binding_sha256','source_read_once_authorized'};required=base_required|{'reward_scope','reward_scope_acknowledged'}
   if not isinstance(value,dict) or set(value)!=required or any(value.get(k)!=preview.get(k) for k in {'authorization_id','context_binding_sha256','profiler_binding_sha256','selection_binding_sha256'}) or value.get('source_read_once_authorized') is not True or value.get('private_values_local_only_acknowledged') is not True or any(value.get(k) is not False for k in {'activation_authorized','automatic_retry_authorized','canonical_write_authorized','provider_access_authorized'}) or value.get('reward_scope')!='one_source_asset_account_to_one_existing_target_asset_account' or value.get('reward_scope_acknowledged') is not True:_fail('reward_account_owner_uat_authorization_invalid')
   try:_validate_owner_directory(directory,create=True)
   except StatementImportOwnerUATError:_fail('reward_account_owner_uat_evidence_invalid')
   attempt={'activation_authorized':False,'automatic_retry_authorized':False,'context_binding_sha256':context_binding_sha256,'created_at_utc':clock().astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),'private_values_published':False,'profiler_authorization_sha256':_fingerprint(value),'selection_binding_sha256':preview['selection_binding_sha256'],'source_path_retained':False,'status':'reward_authorization_consumed_before_source_read','version':2};attempt['attempt_fingerprint']=_fingerprint(attempt);_write(directory,'reward-attempt.json',attempt)
   return {k:value[k] for k in base_required}
  def review(private_review):
   nonlocal seal,inner_error
   try:
    decision=review_provider(private_review,catalog)
    if decision is None:_fail('reward_account_owner_uat_cancelled')
    expected={'fee_sign_convention','owner_acknowledgements','route_decisions','source_account','source_account_column_ordinal','source_asset','target_account_option_key','target_asset_option_key','target_portfolio_option_key','time_zone','valuation_mode','valuation_values'}
    if not isinstance(decision,dict) or set(decision)!=expected or decision['owner_acknowledgements']!={'disabled_only':True,'fiat_value_before_tax_after_fee':True,'no_activation':True,'row_complete':True,'source_balance_not_used':True}:_fail('reward_account_owner_uat_review_invalid')
    source=project_statement_reward_source_review_v2(private_review,source_account_column_ordinal=decision['source_account_column_ordinal']);selected_catalog={'account_options':catalog['account_options'],'asset_options':catalog['asset_options'],'selected_portfolio_option_key':decision['target_portfolio_option_key']};asset=[x for x in catalog['asset_options'] if x['option_key']==decision['target_asset_option_key'] and x['portfolio_option_key']==decision['target_portfolio_option_key']]
    if len(asset)!=1:_fail('reward_account_owner_uat_review_invalid')
    reward_routes=[k.split('|') for k,v in decision['route_decisions'].items() if v=='reward']
    if len(reward_routes)!=1:_fail('reward_account_owner_uat_review_invalid')
    eligible=[r['source_row_id'] for r in source['private_rows'] if [r['source_type'],r['source_subtype'],r['asset_class']]==reward_routes[0] and r['source_asset_key']==decision['source_asset'] and r['source_account_key']==decision['source_account']]
    if not eligible:_fail('reward_account_owner_uat_review_invalid')
    mode=decision['valuation_mode'];values=decision['valuation_values'];valuations={}
    for identity in eligible:
     if mode in {'basis_missing','provider_price_planned'}:valuations[identity]={'mode':mode}
     elif mode=='manual_fiat_total':valuations[identity]={'mode':mode,'fiat_total_decimal':values.get(identity)}
     elif mode=='manual_unit_price':valuations[identity]={'mode':mode,'unit_price_decimal':values.get(identity)}
     else:_fail('reward_account_owner_uat_review_invalid')
    selection={'event_time_format':source['public']['event_time_format'],'exact_local_zone':decision['time_zone'],'fee_sign_convention':decision['fee_sign_convention'],'price_currency':asset[0]['price_currency'],'reward_tuple':reward_routes[0],'route_decisions':decision['route_decisions'],'source_account':decision['source_account'],'source_asset':decision['source_asset'],'target_account_option_key':decision['target_account_option_key'],'target_asset_option_key':decision['target_asset_option_key']};preview=build_reward_account_import_preview_v2(source['private_rows'],selection,selected_catalog,valuations)
    seal={'attempt_fingerprint':attempt['attempt_fingerprint'],'candidate_generation_authorized':False,'private_values_published':False,'preview_fingerprint':_fingerprint(preview),'reward_tuple_sha256':_fingerprint({'reward_tuple':reward_routes[0]}),'row_count':preview['row_count'],'selected_source_account_sha256':preview['selected_source_account_sha256'],'selected_source_asset_sha256':preview['selected_source_asset_sha256'],'silent_drop_count':preview['silent_drop_count'],'source_balance_disposition':preview['source_balance_disposition'],'source_path_retained':False,'status':'reward_preview_sealed_disabled','target_account_option_sha256':_fingerprint({'target_account_option_key':decision['target_account_option_key']}),'target_asset_option_sha256':_fingerprint({'target_asset_option_key':decision['target_asset_option_key']}),'terminal_disposition_counts':preview['terminal_disposition_counts'],'time_zone_sha256':_fingerprint({'time_zone':decision['time_zone']}),'valuation_mode':mode,'version':2};seal['seal_fingerprint']=_fingerprint(seal);_write(directory,'reward-preview-seal.json',seal)
    binding=private_review['review_binding_sha256'];return {'decision':'observe_disabled','no_activation_acknowledged':True,'private_values_local_only_acknowledged':True,'review_binding_sha256':binding}
   except RewardAccountOwnerUATError as e:inner_error=e;raise StatementSourceProfilerOwnerUATError('statement_source_profiler_owner_uat_review_invalid') from e
   except (StatementRewardSourceProfilerError,RewardAccountImportPreviewError,KeyError,TypeError,ValueError) as e:inner_error=RewardAccountOwnerUATError('reward_account_owner_uat_review_invalid');raise StatementSourceProfilerOwnerUATError('statement_source_profiler_owner_uat_review_invalid') from e
  before=set(profiler_root.iterdir()) if profiler_root.exists() else set()
  try:run_statement_source_profiler_owner_uat_v1(profiler_root,context_binding_sha256,selection_provider=selection_provider,authorization_provider=authorize,review_provider=review,inspection_provider=inspect_statement_reward_source_bytes_v2,now_provider=clock)
  except StatementSourceProfilerOwnerUATError as e:
   if inner_error is not None:raise inner_error
   raise RewardAccountOwnerUATError('reward_account_owner_uat_profiler_failed') from e
  if attempt is None or seal is None:_fail('reward_account_owner_uat_review_invalid')
  new=set(profiler_root.iterdir())-before
  if len(new)!=1:_fail('reward_account_owner_uat_evidence_invalid')
  profile=_read(next(iter(new))/'uat-receipt.json');receipt={'activation_authorized':False,'attempt_fingerprint':attempt['attempt_fingerprint'],'automatic_retry':False,'candidate_generation_authorized':False,'canonical_write':False,'cash_write':False,'context_binding_sha256':context_binding_sha256,'network_access':False,'private_values_published':False,'profile_revision_created':False,'profiler_receipt_fingerprint':profile['receipt_fingerprint'],'provider_access':False,'seal_fingerprint':seal['seal_fingerprint'],'source_path_retained':False,'source_read_attempt_count':1,'status':'reward_account_owner_preview_sealed_disabled','tax_write':False,'version':2};receipt['receipt_fingerprint']=_fingerprint(receipt);_write(directory,'reward-receipt.json',receipt);return {'activation_authorized':False,'automatic_retry':False,'candidate_generation_authorized':False,'canonical_write':False,'cash_write':False,'network_access':False,'owner_evidence_created':True,'private_source_read':True,'private_values_published':False,'profile_revision_created':False,'provider_access':False,'source_read_attempt_count':1,'status':'reward_account_owner_preview_sealed_disabled','tax_write':False,'version':2}
 except RewardAccountOwnerUATError as e:
  if directory is not None and attempt is not None and not (directory/'reward-receipt.json').exists():
   failure={'attempt_fingerprint':attempt['attempt_fingerprint'],'automatic_retry':False,'failure_code':e.code,'private_values_published':False,'source_path_retained':False,'status':'terminal_failure_new_authorization_required','version':2};failure['failure_fingerprint']=_fingerprint(failure);_write(directory,'reward-failure.json',failure)
  raise
 finally:os.umask(old)
