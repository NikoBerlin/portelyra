#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.desktop_fx_demand_coverage_v1 import DesktopFxDemandCoverageV1Error,read_desktop_fx_demand_coverage_v1
try:
 payload=json.loads(sys.stdin.read());result=read_desktop_fx_demand_coverage_v1(payload['data_space_path'],payload['context'],payload['demands'],payload['start_date'],payload['end_date']);print(json.dumps({'status':'completed','result':result},sort_keys=True,separators=(',',':')));raise SystemExit(0)
except (DesktopFxDemandCoverageV1Error,KeyError,TypeError,json.JSONDecodeError) as error:
 print(json.dumps({'status':'blocked','code':getattr(error,'code','desktop_fx_demand_coverage_input_invalid')},sort_keys=True,separators=(',',':')));raise SystemExit(2)
except Exception:
 print(json.dumps({'status':'failed','code':'desktop_fx_demand_coverage_store_invalid'},sort_keys=True,separators=(',',':')));raise SystemExit(1)
