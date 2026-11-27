#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.manual_price_source_v1 import ManualPriceError,append_manual_price_v1,read_manual_entries_v1
def main():
 try:
  command=sys.argv[1] if len(sys.argv)>1 else ""
  value=json.load(sys.stdin);space=Path(value["data_space_path"]);context=value["context"]
  if command=="read":result=read_manual_entries_v1(space,context,value["asset_id"])
  elif command=="append":result=append_manual_price_v1(space,context,value["asset_id"],value["price_date"],value["value"],value["currency"],value["recorded_at_utc"],value["confirmed"])
  else:raise ManualPriceError("manual_price_input_invalid")
  print(json.dumps({"status":"completed","result":result},sort_keys=True,separators=(",",":")));return 0
 except (ManualPriceError,KeyError,TypeError,ValueError,json.JSONDecodeError) as error:
  print(json.dumps({"status":"blocked","code":getattr(error,"code","manual_price_input_invalid")},sort_keys=True,separators=(",",":")));return 2
if __name__=="__main__":raise SystemExit(main())
