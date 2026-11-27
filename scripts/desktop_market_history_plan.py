#!/usr/bin/env python3
"""JSON-stdin boundary for provider-free Desktop Market History planning."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1  # noqa:E402
from migrations.reference.desktop_market_history_plan_v1 import DesktopMarketHistoryPlanV1Error,plan_desktop_market_history_v1  # noqa:E402
def main():
 try:
  payload=json.loads(sys.stdin.read());ctx=payload['context'];context=DesktopProviderSearchContextV1(ctx['tenant_id'],ctx['user_id'],ctx['data_space_id'],ctx.get('actor_id','market_worker'),ctx.get('role','market_worker'));result=plan_desktop_market_history_v1(payload['data_space_path'],context,payload['listing_ref'],payload['required_start_date'],payload['as_of_date'],payload['mode']);print(json.dumps({'status':'completed','result':result},sort_keys=True,separators=(',',':')));return 0
 except (DesktopMarketHistoryPlanV1Error,KeyError,TypeError,json.JSONDecodeError) as error:print(json.dumps({'status':'blocked','code':getattr(error,'code','desktop_market_history_plan_input_invalid')},sort_keys=True,separators=(',',':')));return 2
 except Exception:print(json.dumps({'status':'failed','code':'desktop_market_history_plan_read_failed'},sort_keys=True,separators=(',',':')));return 1
if __name__=='__main__':raise SystemExit(main())
