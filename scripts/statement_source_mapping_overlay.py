#!/usr/bin/env python3
"""Synthetic-only ADR-166 mapping-overlay demonstration; accepts no paths."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from migrations.reference.desktop_statement_source_profiler_v1 import inspect_statement_source_bytes_v1
from migrations.reference.statement_source_mapping_overlay_v1 import build_statement_source_mapping_overlay_v1
FIXTURE=ROOT/'fixtures/product/statement-source-profiler-v1/unknown-column.csv'
def main(argv=None):
 args=tuple(sys.argv[1:] if argv is None else argv)
 if args:return 2
 r=inspect_statement_source_bytes_v1(FIXTURE.read_bytes(),institution_hint='kraken').private_review
 routes=[]
 for n,item in enumerate(r['semantic_route_tuples'],1):
  route={('earn','reward','currency'):'reward_candidate_disabled',('trade','spot','currency'):'trade_candidate_disabled'}.get((item['source_type'],item['source_subtype'],item['asset_class']),'diagnostic');routes.append({'tuple_ordinal':n,'route':route})
 d={'column_decisions':[{'column_ordinal':x['column_ordinal'],'disposition':'explicit_nonsemantic_evidence','role':None} for x in r['column_dispositions'] if x['status']=='owner_role_review_required'],'decimal_decisions':dict(r['decimal_formats']),'owner_acknowledgements':{'disabled_only':True,'hash_only_persistence':True,'no_activation':True,'row_complete':True},'semantic_tuple_decisions':routes,'time_zone_decision':{'exact_local_zone':'UTC','lexical_format':r['time_format'],'owner_confirmed':True}}
 print(json.dumps(build_statement_source_mapping_overlay_v1(r,d),ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':')));return 0
if __name__=='__main__':raise SystemExit(main())
