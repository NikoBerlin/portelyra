#!/usr/bin/env python3
"""JSON-stdin boundary for the Asset Center Yahoo Daily probe."""
from __future__ import annotations
import argparse,json,secrets,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.price_provider_admin_v1 import guard_payload_v1  # noqa: E402 - Kursanbieter je Datenraum (rc.383)
from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1  # noqa:E402
from migrations.reference.desktop_provider_probe_v1 import DesktopProviderProbeV1Error,apply_desktop_provider_probe_v1,preview_desktop_provider_probe_v1,public_desktop_provider_probe_preview_v1,public_desktop_provider_probe_result_v1,recover_desktop_provider_probe_evidence_v1  # noqa:E402

def provider_of(payload,*path):
 """Der Anbieter der Zuordnung aus der vertrauten Vorschau (rc.394); die Pruefung der Vorschau selbst folgt im Modul."""
 value=payload
 for key in path:value=value.get(key) if isinstance(value,dict) else None
 return value if isinstance(value,str) else 'yahoo'
def emit(value):print(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')))
def context(value):return DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
def main():
 parser=argparse.ArgumentParser(description='Portelyra Desktop Provider Probe v1');parser.add_argument('command',choices=('preview','apply','recover'));args=parser.parse_args()
 try:
  payload=json.loads(sys.stdin.read())
  if args.command=='preview':
   preview=preview_desktop_provider_probe_v1(context(payload['context']),payload['mapping'],payload['start_date'],payload['end_date'],'pbn_'+secrets.token_urlsafe(18),payload['created_at_utc']);emit({'status':'previewed','public_preview':public_desktop_provider_probe_preview_v1(preview),'trusted_preview':preview})
  elif args.command=='apply':
   blocked=guard_payload_v1(payload,'desktop_provider_probe',provider_of(payload,'trusted_preview','provider_id'))
   if blocked:emit(blocked);return 2
   result=apply_desktop_provider_probe_v1(payload['data_space_path'],context(payload['context']),payload['trusted_preview'],payload['public_preview'],payload.get('confirmed') is True);emit({'status':'completed','result':result})
  else:
   private=recover_desktop_provider_probe_evidence_v1(payload['data_space_path'],context(payload['context']),payload['mapping']);emit({'status':'absent'} if private is None else {'status':'completed','request_ref':private['request_ref'],'result':public_desktop_provider_probe_result_v1(private)})
 except (DesktopProviderProbeV1Error,KeyError,TypeError,json.JSONDecodeError) as error:emit({'status':'blocked','code':getattr(error,'code','desktop_provider_probe_input_invalid')});return 2
 except Exception:emit({'status':'failed','code':'desktop_provider_probe_boundary_failed'});return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
