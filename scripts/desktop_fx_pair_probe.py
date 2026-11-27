#!/usr/bin/env python3
from __future__ import annotations
import json,sys,secrets
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.price_provider_admin_v1 import guard_payload_v1  # noqa: E402 - Kursanbieter je Datenraum (rc.383)
from migrations.reference.desktop_fx_pair_probe_v1 import *
def main():
 try:
  p=json.loads(sys.stdin.read());cmd=sys.argv[1]
  if cmd=='preview':
   trusted=preview_desktop_fx_pair_probe_v1(p['context'],p['candidate'],p['source_currency'],p['target_currency'],p['direction'],p['start_date'],p['end_date'],p['created_at_utc']);out={'status':'completed','trusted_preview':trusted,'public_preview':public_desktop_fx_pair_probe_preview_v1(trusted)}
  elif cmd=='apply':
   blocked=guard_payload_v1(p,'desktop_fx_pair_probe')
   if blocked:print(json.dumps(blocked,sort_keys=True,separators=(',',':')));return 2
   private=apply_desktop_fx_pair_probe_v1(p['data_space_path'],p['context'],p['trusted_preview'],p['public_preview'],p['confirmed']);out={'status':'completed','trusted_result':private,'public_result':public_desktop_fx_pair_probe_result_v1(private)}
  else:raise KeyError(cmd)
  print(json.dumps(out,sort_keys=True,separators=(',',':')));return 0
 except (DesktopFxPairProbeV1Error,KeyError,TypeError,json.JSONDecodeError) as e:print(json.dumps({'status':'blocked','code':getattr(e,'code','desktop_fx_pair_probe_input_invalid')},sort_keys=True,separators=(',',':')));return 2
 except Exception:print(json.dumps({'status':'failed','code':'desktop_fx_pair_probe_store_invalid'},sort_keys=True,separators=(',',':')));return 1
if __name__=='__main__':raise SystemExit(main())
