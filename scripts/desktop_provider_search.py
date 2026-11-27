#!/usr/bin/env python3
"""JSON-stdin boundary for the Asset Center Provider search."""
from __future__ import annotations
import argparse,json,secrets,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.price_provider_admin_v1 import guard_payload_v1  # noqa: E402 - Kursanbieter je Datenraum (rc.383)
from migrations.reference.desktop_provider_search_v1 import (  # noqa:E402
 DesktopProviderSearchContextV1,DesktopProviderSearchV1Error,apply_desktop_provider_search_v1,
 preview_desktop_provider_search_v1,public_desktop_provider_search_preview_v1,
)

def emit(value):print(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')))
def context(value):return DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
def main():
 parser=argparse.ArgumentParser(description='Portelyra Desktop Provider Search v1');parser.add_argument('command',choices=('preview','apply'));args=parser.parse_args()
 try:
  payload=json.loads(sys.stdin.read())
  if args.command=='preview':
   preview=preview_desktop_provider_search_v1(context(payload['context']),payload['provider_id'],payload['query'],payload.get('search_mode','auto'),'srn_'+secrets.token_urlsafe(18),payload['created_at_utc']);emit({'status':'previewed','public_preview':public_desktop_provider_search_preview_v1(preview),'trusted_preview':preview})
  else:
   provider=payload['trusted_preview'].get('provider_id','yahoo') if isinstance(payload.get('trusted_preview'),dict) else 'yahoo'
   blocked=guard_payload_v1(payload,'desktop_provider_search',provider if isinstance(provider,str) else 'yahoo')
   if blocked:emit(blocked);return 2
   result=apply_desktop_provider_search_v1(payload['data_space_path'],context(payload['context']),payload['trusted_preview'],payload['public_preview'],payload.get('confirmed') is True);emit({'status':'completed','result':result})
 except (DesktopProviderSearchV1Error,KeyError,TypeError,json.JSONDecodeError) as error:emit({'status':'blocked','code':getattr(error,'code','desktop_provider_search_input_invalid')});return 2
 except Exception:emit({'status':'failed','code':'desktop_provider_search_boundary_failed'});return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
