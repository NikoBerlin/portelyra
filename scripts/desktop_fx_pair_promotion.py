#!/usr/bin/env python3
from __future__ import annotations
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.desktop_fx_pair_promotion_v1 import *
def main():
 try:
  p=json.loads(sys.stdin.read());cmd=sys.argv[1]
  if cmd=='preview':
   t=preview_desktop_fx_pair_promotion_v1(p['data_space_path'],p['context'],p['probe_result'],p['created_at_utc']);o={'status':'completed','trusted_preview':t,'public_preview':public_desktop_fx_pair_promotion_preview_v1(t)}
  elif cmd=='apply':o={'status':'completed','result':apply_desktop_fx_pair_promotion_v1(p['data_space_path'],p['context'],p['trusted_preview'],p['public_preview'],p['confirmed'],p['completed_at_utc'])}
  else:raise KeyError(cmd)
  print(json.dumps(o,sort_keys=True,separators=(',',':')));return 0
 except (DesktopFxPairPromotionV1Error,KeyError,TypeError,json.JSONDecodeError) as e:print(json.dumps({'status':'blocked','code':getattr(e,'code','desktop_fx_pair_promotion_input_invalid')},sort_keys=True,separators=(',',':')));return 2
 except Exception:print(json.dumps({'status':'failed','code':'desktop_fx_pair_promotion_write_failed'},sort_keys=True,separators=(',',':')));return 1
if __name__=='__main__':raise SystemExit(main())
