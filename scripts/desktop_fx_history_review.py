#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.price_provider_admin_v1 import guard_payload_v1  # noqa: E402 - Kursanbieter je Datenraum (rc.383)
from migrations.reference.desktop_fx_history_review_v1 import *
from migrations.reference.desktop_fx_history_review_v1 import _ctx
from migrations.reference import desktop_fx_history_attempt_v2 as evidence

def direct_stage(p):
 if p['confirmed'] is not True:raise DesktopFxHistoryReviewV1Error('desktop_fx_history_review_confirmation_required')
 from migrations.reference import desktop_market_fx_batch_execution_v1 as execution
 from migrations.reference.desktop_market_calendar_batch_v1 import _assert_unreserved
 ctx={k:p['context'][k] for k in ('tenant_id','user_id','data_space_id')};v=p['trusted']
 # Share the coordinator lock; never bypass an existing batch reservation.
 try:
  space=execution._space(p['data_space_path'],execution._context(ctx))
  with execution._locked(space,ctx,create=True):
   _assert_unreserved(space,ctx,{'request':{'start_date':v['start_date'],'end_date':v['end_date'],'targets':[{'listing_ref':None,'mapping':{'provider_currency':v['source_currency']}}]}})
   return stage_desktop_fx_history_fetch_v1(space,p['context'],v,p['public'],True)
 except execution.MarketFxBatchExecutionError as error:
  raise DesktopFxHistoryReviewV1Error('desktop_fx_history_review_attempt_consumed') from error
def main():
 try:
  p=json.loads(sys.stdin.read());c=sys.argv[1]
  if c=='plan':o={'status':'completed','result':plan_desktop_fx_history_v1(p['data_space_path'],p['context'],p['source_currency'],p['target_currency'],p['start_date'],p['end_date'])}
  elif c=='preview':
   t=preview_desktop_fx_history_fetch_v1(p['data_space_path'],p['context'],p['source_currency'],p['target_currency'],p['start_date'],p['end_date'],p['created_at_utc']);o={'status':'completed','trusted':t,'public':public_desktop_fx_history_fetch_preview_v1(t)}
  elif c=='stage':
   blocked=guard_payload_v1(p,'desktop_fx_history_review')
   if blocked:print(json.dumps(blocked,sort_keys=True,separators=(',',':')));return 2
   t=direct_stage(p);o={'status':'completed','trusted':t,'public':public_desktop_fx_history_review_v1(t)}
  elif c=='inspect':
   t=evidence.inspect(p['data_space_path'],p['context']);o={'status':'completed','trusted':t,'public':{'rows':[{k:v for k,v in row.items() if k not in ('attempt_fingerprint','preview_fingerprint')} for row in t['rows']]}}
  elif c=='review-no-result':o={'status':'completed','result':evidence.review_no_result(p['data_space_path'],p['context'],p['trusted'],p['attempt_ref'],p['confirmed'])}
  elif c=='recover':
   t=evidence.inspect(p['data_space_path'],p['context']);rows=[r for r in t['rows'] if r['attempt_ref']==p['attempt_ref'] and r['state']=='staged']
   if len(rows)!=1:raise DesktopFxHistoryReviewV1Error('desktop_fx_history_review_preview_invalid')
   t=evidence.result_read(Path(p['data_space_path'])/STAGE_AREA/'results'/(p['attempt_ref']+'.json'),Path(p['data_space_path']),_ctx(p['context']))
   if any(t[k]!=p[k] for k in ('source_currency','target_currency','start_date','end_date')):raise DesktopFxHistoryReviewV1Error('desktop_fx_history_review_preview_invalid')
   o={'status':'completed','trusted':t,'public':public_desktop_fx_history_review_v1(t)}
  elif c=='publish':o={'status':'completed','result':publish_desktop_fx_history_v1(p['data_space_path'],p['context'],p['trusted'],p['public'],p['confirmed'],p['completed_at_utc'])}
  else:raise KeyError(c)
  print(json.dumps(o,sort_keys=True,separators=(',',':')));return 0
 except (DesktopFxHistoryReviewV1Error,KeyError,TypeError,json.JSONDecodeError) as e:print(json.dumps({'status':'blocked','code':getattr(e,'code','desktop_fx_history_review_input_invalid')},sort_keys=True,separators=(',',':')));return 2
 except Exception:print(json.dumps({'status':'failed','code':'desktop_fx_history_review_store_invalid'},sort_keys=True,separators=(',',':')));return 1
if __name__=='__main__':raise SystemExit(main())
