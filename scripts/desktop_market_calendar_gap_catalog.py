#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.desktop_market_calendar_gap_catalog_v1 import *
def main():
 try:
  p=json.loads(sys.stdin.read());r=read_desktop_market_calendar_gap_catalog_v1(p['data_space_path'],p['context'],p['listings'],p['fx_demands'],p['start_date'],p['end_date']);print(json.dumps({'status':'completed','result':r},sort_keys=True,separators=(',',':')));return 0
 except (DesktopMarketCalendarGapCatalogV1Error,KeyError,TypeError,json.JSONDecodeError) as e:print(json.dumps({'status':'blocked','code':getattr(e,'code','desktop_market_calendar_gap_input_invalid')},sort_keys=True,separators=(',',':')));return 2
 except Exception:print(json.dumps({'status':'failed','code':'desktop_market_calendar_gap_store_invalid'},sort_keys=True,separators=(',',':')));return 1
if __name__=='__main__':raise SystemExit(main())
