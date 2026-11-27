#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.desktop_reward_daily_close_v1 import *
def main():
 try:
  p=json.loads(sys.stdin.read());cmd=sys.argv[1]
  if cmd=='preview':o=preview_desktop_reward_daily_close_v1(p['space'],p['context'],p['draft_ref'])
  elif cmd=='apply':o=apply_desktop_reward_daily_close_v1(p['space'],p['context'],p['draft_ref'],p['draft_revision'],p['candidate'],p['confirmed'],p['updated_at_utc'])
  else:raise KeyError(cmd)
  print(json.dumps({'status':'completed','result':o},sort_keys=True,separators=(',',':')));return 0
 except Exception as e:print(json.dumps({'status':'blocked','code':getattr(e,'code','desktop_reward_daily_close_input_invalid')},sort_keys=True,separators=(',',':')));return 2
if __name__=='__main__':raise SystemExit(main())
