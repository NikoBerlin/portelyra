#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.desktop_market_history_coverage_v1 import DesktopMarketHistoryCoverageV1Error,read_desktop_market_history_coverage_v1
def main():
 try:
  value=json.load(sys.stdin);result=read_desktop_market_history_coverage_v1(Path(value["data_space_path"]),value["context"],value["bindings"],value["required_start_date"],value["as_of_date"]);print(json.dumps({"status":"completed","result":result},sort_keys=True,separators=(",",":")));return 0
 except (DesktopMarketHistoryCoverageV1Error,KeyError,TypeError,ValueError,json.JSONDecodeError) as error:
  print(json.dumps({"status":"blocked","code":getattr(error,"code","desktop_market_history_coverage_input_invalid")},sort_keys=True,separators=(",",":")));return 2
if __name__=="__main__":raise SystemExit(main())
