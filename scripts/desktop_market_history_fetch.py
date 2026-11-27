#!/usr/bin/env python3
"""JSON-stdin boundary for confirmed missing-only Yahoo history fetch."""
from __future__ import annotations
import argparse,json,secrets,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.price_provider_admin_v1 import guard_payload_v1  # noqa: E402 - Kursanbieter je Datenraum (rc.383)
from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1  # noqa:E402
from migrations.reference.desktop_market_history_fetch_v1 import DesktopMarketHistoryFetchV1Error,apply_desktop_market_history_fetch_v1,preview_desktop_market_history_fetch_v1,public_desktop_market_history_fetch_preview_v1,public_desktop_market_history_fetch_result_v1  # noqa:E402
def provider_of(payload,*path):
 """Der Anbieter der Zuordnung aus der vertrauten Vorschau (rc.394); die Pruefung der Vorschau selbst folgt im Modul."""
 value=payload
 for key in path:value=value.get(key) if isinstance(value,dict) else None
 return value if isinstance(value,str) else 'yahoo'
def emit(value):print(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')))
def context(value):return DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
def main():
 parser=argparse.ArgumentParser(description='Portelyra Missing Market History Fetch v1');parser.add_argument('command',choices=('preview','apply'));args=parser.parse_args()
 try:
  payload=json.loads(sys.stdin.read())
  if args.command=='preview':
   preview=preview_desktop_market_history_fetch_v1(payload['data_space_path'],context(payload['context']),payload['listing_ref'],payload['mapping'],payload['required_start_date'],payload['as_of_date'],'mhn_'+secrets.token_urlsafe(18),payload['created_at_utc'],payload.get('mode','incremental'));emit({'status':'previewed','trusted_preview':preview,'public_preview':public_desktop_market_history_fetch_preview_v1(preview)})
  else:
   blocked=guard_payload_v1(payload,'desktop_market_history_fetch',provider_of(payload,'trusted_preview','mapping','provider_id'))
   if blocked:emit(blocked);return 2
   private=apply_desktop_market_history_fetch_v1(payload['data_space_path'],context(payload['context']),payload['trusted_preview'],payload['public_preview'],payload.get('confirmed') is True);emit({'status':'completed','private_result':private,'public_result':public_desktop_market_history_fetch_result_v1(private)})
 except (DesktopMarketHistoryFetchV1Error,KeyError,TypeError,json.JSONDecodeError) as error:emit({'status':'blocked','code':getattr(error,'code','desktop_market_history_fetch_input_invalid')});return 2
 except Exception:emit({'status':'failed','code':'desktop_market_history_fetch_write_failed'});return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
