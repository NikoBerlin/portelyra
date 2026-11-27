"""Pure hash-only owner mapping overlay for ADR-166.

The input may contain private ADR-164 review values in memory. The returned
value contains hashes and explicit decisions only. It has no file, provider,
network, activation, candidate, or product authority.
"""
from __future__ import annotations
import hashlib,json,re
from typing import Any
_SHA=re.compile(r'[0-9a-f]{64}')
ROUTES=frozenset({'reward_candidate_disabled','trade_candidate_disabled','movement_candidate_disabled','cash_domain_deferred','diagnostic'})
NONSEMANTIC='explicit_nonsemantic_evidence'
REGISTERED_ROLES=frozenset({'source_row_id','source_group_id','event_time_text','source_type','source_subtype','asset_class','source_asset_key','signed_quantity_decimal','asset_fee_quantity_decimal','balance_reconciliation_evidence','source_account_key'})
DECIMALS=frozenset({'decimal_dot','decimal_comma','integer_with_confirmed_decimal_dot','integer_with_confirmed_decimal_comma'})
FAILURE_CODES=frozenset({'statement_source_mapping_overlay_column_incomplete','statement_source_mapping_overlay_decimal_conflict','statement_source_mapping_overlay_decimal_incomplete','statement_source_mapping_overlay_decision_invalid','statement_source_mapping_overlay_input_invalid','statement_source_mapping_overlay_role_conflict','statement_source_mapping_overlay_row_balance_invalid','statement_source_mapping_overlay_semantics_incomplete','statement_source_mapping_overlay_time_zone_invalid'})
class StatementSourceMappingOverlayError(RuntimeError):
 def __init__(self,code:str):
  if code not in FAILURE_CODES:code='statement_source_mapping_overlay_input_invalid'
  self.code=code;super().__init__(code)
def _fail(code):raise StatementSourceMappingOverlayError(code)
def _canonical(x):
 try:return json.dumps(x,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')).encode()
 except (TypeError,ValueError):_fail('statement_source_mapping_overlay_input_invalid')
def _hash(x):return hashlib.sha256(_canonical(x)).hexdigest()
def _binding(domain,value):return _hash({'binding_domain':domain,'binding_version':1,'value':value})
def build_statement_source_mapping_overlay_v1(private_review:dict[str,Any],decision:dict[str,Any])->dict[str,Any]:
 if not isinstance(private_review,dict) or not isinstance(decision,dict):_fail('statement_source_mapping_overlay_input_invalid')
 required_review={'alias_registry_sha256','column_dispositions','decimal_formats','delimiter','encoding','identity_evidence','institution_hint','raw_header_retained_after_process','route_rules_created','semantic_review','semantic_route_tuples','source_bytes_retained_after_process','statement_source_private_review_version','status','time_format','time_zone_inferred'}
 if set(private_review)!=required_review or private_review['statement_source_private_review_version']!=1 or private_review['raw_header_retained_after_process'] is not False or private_review['source_bytes_retained_after_process'] is not False or private_review['route_rules_created'] is not False or private_review['time_zone_inferred'] is not False or _SHA.fullmatch(private_review['alias_registry_sha256'] or '') is None:_fail('statement_source_mapping_overlay_input_invalid')
 required_decision={'column_decisions','decimal_decisions','owner_acknowledgements','semantic_tuple_decisions','time_zone_decision'}
 if set(decision)!=required_decision:_fail('statement_source_mapping_overlay_decision_invalid')
 ack=decision['owner_acknowledgements']
 if set(ack) != {'disabled_only','hash_only_persistence','no_activation','row_complete'} or any(ack.get(x) is not True for x in ack):_fail('statement_source_mapping_overlay_decision_invalid')
 columns=private_review['column_dispositions']
 if not isinstance(columns,list) or not columns:_fail('statement_source_mapping_overlay_input_invalid')
 unknown={x['column_ordinal']:x for x in columns if x['status']=='owner_role_review_required'}
 choices=decision['column_decisions']
 if not isinstance(choices,list) or {x.get('column_ordinal') for x in choices}!=set(unknown) or len(choices)!=len(unknown):_fail('statement_source_mapping_overlay_column_incomplete')
 choice_by={x['column_ordinal']:x for x in choices}
 resolved=[];roles=[]
 for item in columns:
  if set(item)!= {'column_ordinal','normalized_header','raw_header','role','status'}:_fail('statement_source_mapping_overlay_input_invalid')
  role=item['role'];disposition='explicit_alias_match'
  if item['status']=='owner_role_review_required':
   choice=choice_by[item['column_ordinal']]
   if set(choice)!= {'column_ordinal','disposition','role'}:_fail('statement_source_mapping_overlay_decision_invalid')
   disposition=choice['disposition'];role=choice['role']
   if disposition==NONSEMANTIC:
    if role is not None:_fail('statement_source_mapping_overlay_decision_invalid')
   elif disposition=='owner_role_mapping':
    if role not in REGISTERED_ROLES or role in roles:_fail('statement_source_mapping_overlay_role_conflict')
   else:_fail('statement_source_mapping_overlay_decision_invalid')
  elif item['status']!='explicit_alias_match' or not isinstance(role,str):_fail('statement_source_mapping_overlay_input_invalid')
  if role is not None:
   if role in roles:_fail('statement_source_mapping_overlay_role_conflict')
   roles.append(role)
  resolved.append({'column_ordinal':item['column_ordinal'],'disposition':disposition,'header_token_sha256':_binding('statement_header_token',item['normalized_header']),'role':role})
 decimals=private_review['decimal_formats'];decimal_choices=decision['decimal_decisions']
 if not isinstance(decimals,dict) or not isinstance(decimal_choices,dict) or set(decimal_choices)!=set(decimals):_fail('statement_source_mapping_overlay_decimal_incomplete')
 decimal_out={}
 for role,observed in decimals.items():
  selected=decimal_choices[role]
  if selected not in DECIMALS:_fail('statement_source_mapping_overlay_decision_invalid')
  if observed in {'decimal_dot','decimal_comma'} and selected!=observed:_fail('statement_source_mapping_overlay_decimal_conflict')
  if observed=='integer_only_ambiguous_separator' and not selected.startswith('integer_with_confirmed_'):_fail('statement_source_mapping_overlay_decimal_incomplete')
  decimal_out[role]=selected
 zone=decision['time_zone_decision']
 if not isinstance(zone,dict) or set(zone)!= {'exact_local_zone','lexical_format','owner_confirmed'} or zone['owner_confirmed'] is not True or zone['lexical_format']!=private_review['time_format'] or not isinstance(zone['exact_local_zone'],str) or not re.fullmatch(r'(?:UTC|[A-Za-z]+(?:/[A-Za-z0-9_+.-]+)+)',zone['exact_local_zone']):_fail('statement_source_mapping_overlay_time_zone_invalid')
 tuples=private_review['semantic_route_tuples'];tuple_choices=decision['semantic_tuple_decisions']
 if not isinstance(tuples,list) or not isinstance(tuple_choices,list) or {x.get('tuple_ordinal') for x in tuple_choices}!=set(range(1,len(tuples)+1)) or len(tuple_choices)!=len(tuples):_fail('statement_source_mapping_overlay_semantics_incomplete')
 tuple_by={x['tuple_ordinal']:x for x in tuple_choices};semantic=[]
 for ordinal,item in enumerate(tuples,1):
  choice=tuple_by[ordinal]
  if set(choice)!= {'route','tuple_ordinal'} or choice['route'] not in ROUTES:_fail('statement_source_mapping_overlay_decision_invalid')
  semantic.append({'route':choice['route'],'row_count':item['row_count'],'tuple_sha256':_binding('statement_semantic_tuple',{'asset_class':item['asset_class'],'source_subtype':item['source_subtype'],'source_type':item['source_type']})})
 row_count=private_review['identity_evidence'].get('row_count')
 if not isinstance(row_count,int) or row_count<1 or sum(x['row_count'] for x in semantic)!=row_count:_fail('statement_source_mapping_overlay_row_balance_invalid')
 overlay={'activation_authorized':False,'alias_registry_sha256':private_review['alias_registry_sha256'],'automatic_retry_authorized':False,'candidate_generation_authorized':False,'canonical_write_authorized':False,'cash_write_authorized':False,'column_bindings':resolved,'decimal_bindings':decimal_out,'delimiter':private_review['delimiter'],'encoding':private_review['encoding'],'exact_local_zone':zone['exact_local_zone'],'header_vector_sha256':_binding('statement_header_vector',[x['raw_header'] for x in columns]),'network_access_authorized':False,'profile_revision_created':False,'provider_access_authorized':False,'route_bindings':semantic,'row_count':row_count,'silent_drop_count':0,'statement_source_mapping_overlay_version':1,'status':'owner_mapping_overlay_disabled','tax_write_authorized':False,'time_format':private_review['time_format']}
 overlay['overlay_fingerprint']=_hash(overlay)
 return overlay
__all__=['DECIMALS','FAILURE_CODES','NONSEMANTIC','REGISTERED_ROLES','ROUTES','StatementSourceMappingOverlayError','build_statement_source_mapping_overlay_v1']
