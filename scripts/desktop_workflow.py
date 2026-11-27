#!/usr/bin/env python3
"""Fixed, safe-output Desktop Workflow v1 boundary."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from workers.reference.desktop_workflow_v1 import DesktopWorkflowBlocked,run_desktop_workflow_v1

def main()->int:
 parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--job',required=True);args=parser.parse_args()
 try:
  result=run_desktop_workflow_v1(Path(args.job));print(json.dumps(result,sort_keys=True,separators=(',',':')));return 0 if result['status']=='completed' else 2
 except DesktopWorkflowBlocked as error:
  print(json.dumps({'status':'blocked','failure_code':error.code},sort_keys=True,separators=(',',':')));return 2
 except Exception:
  print(json.dumps({'status':'blocked','failure_code':'desktop_workflow_boundary_failed'},sort_keys=True,separators=(',',':')));return 2
if __name__=='__main__':raise SystemExit(main())
