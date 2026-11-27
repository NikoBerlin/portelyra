#!/usr/bin/env python3
"""JSON-stdin boundary for carrying a market history to another listing binding."""
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.daily_market_history_v1 import MarketHistoryContext  # noqa:E402
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA,STORE_NAME  # noqa:E402
from migrations.reference.desktop_market_history_carry_v1 import DesktopMarketHistoryCarryV1Error,carry_desktop_market_history_v1  # noqa:E402
def main():
 try:
  payload=json.loads(sys.stdin.read());ctx=payload['context']
  context=MarketHistoryContext(ctx['tenant_id'],ctx['user_id'],ctx['data_space_id'],'market_worker','market_worker')
  store=Path(payload['data_space_path'])/MARKET_AREA/STORE_NAME
  result=carry_desktop_market_history_v1(store,context,source_listing_ref=payload['source_listing_ref'],
   target_listing_ref=payload['target_listing_ref'],start_date=payload['start_date'],end_date=payload['end_date'],
   carried_at_utc=payload['carried_at_utc'],dry_run=bool(payload.get('dry_run')))
  print(json.dumps({'status':'completed','result':result},sort_keys=True,separators=(',',':')));return 0
 except (DesktopMarketHistoryCarryV1Error,KeyError,TypeError,json.JSONDecodeError) as error:
  print(json.dumps({'status':'blocked','code':getattr(error,'code','desktop_market_history_carry_input_invalid')},sort_keys=True,separators=(',',':')));return 2
 except Exception:
  print(json.dumps({'status':'failed','code':'desktop_market_history_carry_write_failed'},sort_keys=True,separators=(',',':')));return 1
if __name__=='__main__':raise SystemExit(main())
