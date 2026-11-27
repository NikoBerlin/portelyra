#!/usr/bin/env python3
"""Explicit, provider-free calendar preview/apply CLI. No startup migration."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from migrations.reference.desktop_calendar_gap_review_v1 import *
from migrations.reference.market_calendar_correction_batch_v1 import (
    preview_market_calendar_correction_batch_v1, public_market_calendar_correction_batch_v1,
    apply_market_calendar_correction_batch_v1,
)


def pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError('duplicate_key')
        result[key] = value
    return result


def main():
    try:
        raw = sys.stdin.read(2000001)
        if len(raw.encode()) > 2000000:
            raise ValueError('input_limit')
        p = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('number')))
        cmd = sys.argv[1]
        if cmd == 'batch_preview':
            if set(p) != {'space','context','listing_ref','dates','created'}: raise ValueError('fields')
            t = preview_market_calendar_correction_batch_v1(p['space'],p['context'],p['listing_ref'],p['dates'],p['created'])
            o = {'trusted':t,'public':public_market_calendar_correction_batch_v1(t)}
        elif cmd == 'batch_apply':
            if set(p) != {'space','context','trusted','public','confirmed','completed'}: raise ValueError('fields')
            o = apply_market_calendar_correction_batch_v1(p['space'],p['context'],p['trusted'],p['public'],p['confirmed'],p['completed'])
        elif cmd == 'binding_preview':
            t, u = preview_desktop_fx_calendar_binding_v1(p['space'], p['context'], p['source'], p['target'], p['dates'], p['valid_from'], p['valid_to'], p['created'])
            o = {'trusted': t, 'public': u}
        elif cmd == 'listing_binding_preview':
            t, u = preview_desktop_listing_calendar_binding_v1(p['space'], p['context'], p['listing_ref'], p['dates'], p['valid_from'], p['valid_to'], p['created'])
            o = {'trusted': t, 'public': u}
        elif cmd == 'binding_apply':
            o = apply_desktop_calendar_binding_v1(p['space'], p['context'], p['trusted'], p['public'], p['confirmed'], p['completed'])
        elif cmd == 'correction_preview':
            t, u = preview_desktop_fx_calendar_correction_v1(p['space'], p['context'], p['source'], p['target'], p['date'], p['created'])
            o = {'trusted': t, 'public': u}
        elif cmd == 'listing_correction_preview':
            t = preview_market_calendar_correction_v1(p['space'], p['context'], 'listing', p['listing_ref'], p['date'], p['created'])
            o = {'trusted': t, 'public': public_market_calendar_correction_preview_v1(t)}
        elif cmd == 'correction_apply':
            o = apply_desktop_fx_calendar_correction_v1(p['space'], p['context'], p['trusted'], p['public'], p['confirmed'], p['completed'])
        else:
            raise KeyError(cmd)
        print(json.dumps({'status': 'completed', 'result': o}, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception as e:
        print(json.dumps({'status': 'blocked', 'code': getattr(e, 'code', 'desktop_calendar_gap_review_input_invalid')}, sort_keys=True, separators=(',', ':')))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
