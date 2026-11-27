#!/usr/bin/env python3
"""JSON-stdin boundary for Provider-probe Daily History promotion."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from migrations.reference.desktop_provider_search_v1 import DesktopProviderSearchContextV1  # noqa:E402
from migrations.reference.desktop_provider_probe_promotion_v1 import DesktopProviderPromotionV1Error,apply_desktop_provider_probe_promotion_v1,preview_desktop_provider_probe_promotion_v1,public_desktop_provider_probe_promotion_preview_v1,public_desktop_provider_probe_promotion_result_v1,recover_desktop_provider_probe_promotion_v1  # noqa:E402

def emit(value):print(json.dumps(value,ensure_ascii=True,sort_keys=True,separators=(',',':')))
def context(value):return DesktopProviderSearchContextV1(value['tenant_id'],value['user_id'],value['data_space_id'],value.get('actor_id','market_worker'),value.get('role','market_worker'))
def main():
 parser=argparse.ArgumentParser(description='Portelyra Provider Probe Promotion v1');parser.add_argument('command',choices=('preview','apply','recover'));args=parser.parse_args()
 try:
  payload=json.loads(sys.stdin.read())
  if args.command=='preview':
   preview=preview_desktop_provider_probe_promotion_v1(payload['data_space_path'],context(payload['context']),payload['request_ref'],payload['mapping'],payload['market_code'],payload['timezone_name'],payload['calendar_code'],payload['created_at_utc']);emit({'status':'previewed','public_preview':public_desktop_provider_probe_promotion_preview_v1(preview),'trusted_preview':preview})
  elif args.command=='apply':
   private=apply_desktop_provider_probe_promotion_v1(payload['data_space_path'],context(payload['context']),payload['trusted_preview'],payload['public_preview'],payload.get('confirmed') is True,payload['applied_at_utc']);emit({'status':'completed','private_result':private,'public_result':public_desktop_provider_probe_promotion_result_v1(private)})
  else:
   private=recover_desktop_provider_probe_promotion_v1(payload['data_space_path'],context(payload['context']),payload['mapping_id']);emit({'status':'absent'} if private is None else {'status':'completed','private_result':private,'public_result':public_desktop_provider_probe_promotion_result_v1(private)})
 except (DesktopProviderPromotionV1Error,KeyError,TypeError,json.JSONDecodeError) as error:emit({'status':'blocked','code':getattr(error,'code','desktop_provider_promotion_input_invalid')});return 2
 except Exception:emit({'status':'failed','code':'desktop_provider_promotion_boundary_failed'});return 1
 return 0
if __name__=='__main__':raise SystemExit(main())
