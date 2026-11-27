"""Private in-memory Reward/Source-Account projection for ADR-168/169."""
from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any
from migrations.reference.desktop_statement_source_profiler_v1 import _canonical,_decode,_detect_records,inspect_statement_source_bytes_v1
from migrations.reference.statement_source_mapping_overlay_v1 import REGISTERED_ROLES
class StatementRewardSourceProfilerError(RuntimeError):pass
@dataclass(frozen=True)
class StatementRewardSourceInspectionV2:
 private_review:dict[str,Any]
 _public:dict[str,Any]
 def public_projection(self):return json.loads(_canonical(self._public).decode('ascii'))
def inspect_statement_reward_source_bytes_v2(source_bytes:bytes):
 base=inspect_statement_source_bytes_v1(source_bytes,institution_hint='kraken');text,_encoding=_decode(source_bytes);_code,_delimiter,records=_detect_records(text);review=dict(base.private_review);review['private_source_rows_by_ordinal']=[list(row) for row in records[1:]];return StatementRewardSourceInspectionV2(review,base.public_projection())
def project_statement_reward_source_review_v2(review:dict[str,Any],*,source_account_column_ordinal:int):
 columns=review.get('column_dispositions');raw_rows=review.get('private_source_rows_by_ordinal')
 if not isinstance(columns,list) or not isinstance(raw_rows,list) or not isinstance(source_account_column_ordinal,int) or source_account_column_ordinal<1 or source_account_column_ordinal>len(columns):raise StatementRewardSourceProfilerError('statement_reward_source_account_column_invalid')
 account_column=columns[source_account_column_ordinal-1]
 if account_column['role'] is not None or account_column['status']!='owner_role_review_required' or 'source_account_key' not in REGISTERED_ROLES:raise StatementRewardSourceProfilerError('statement_reward_source_account_column_invalid')
 role_indices={x['role']:x['column_ordinal']-1 for x in columns if x['role'] is not None};needed={'source_row_id','event_time_text','source_type','source_subtype','asset_class','source_asset_key','signed_quantity_decimal','asset_fee_quantity_decimal'}
 if set(role_indices)<needed:raise StatementRewardSourceProfilerError('statement_reward_source_roles_incomplete')
 private=[]
 for row in raw_rows:
  if not isinstance(row,list) or len(row)!=len(columns):raise StatementRewardSourceProfilerError('statement_reward_source_roles_incomplete')
  value=row[source_account_column_ordinal-1]
  if not isinstance(value,str) or not value.strip():raise StatementRewardSourceProfilerError('statement_reward_source_account_missing')
  item={role:row[index] for role,index in role_indices.items() if role in needed};item['source_account_key']=value;private.append(item)
 assets=sorted({x['source_asset_key'] for x in private});accounts=sorted({x['source_account_key'] for x in private});return {'private_rows':private,'private_source_accounts':accounts,'private_source_assets':assets,'public':{'event_time_format':review['time_format'],'row_count':len(private),'source_account_count':len(accounts),'source_asset_count':len(assets),'source_values_exposed':False,'statement_reward_source_profiler_version':2,'status':'ready_for_reward_account_selection'}}
def profile_statement_reward_source_v2(source_bytes:bytes,*,source_account_column_ordinal:int):return project_statement_reward_source_review_v2(inspect_statement_reward_source_bytes_v2(source_bytes).private_review,source_account_column_ordinal=source_account_column_ordinal)
__all__=['StatementRewardSourceProfilerError','StatementRewardSourceInspectionV2','inspect_statement_reward_source_bytes_v2','profile_statement_reward_source_v2','project_statement_reward_source_review_v2']
