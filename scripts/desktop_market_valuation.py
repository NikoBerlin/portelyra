#!/usr/bin/env python3
"""Private bounded JSON bridge for explicit valuation draft/review commands."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from migrations.reference.desktop_market_valuation_v1 import operate
from scripts.desktop_market_fx_batch import _object, _constant

CODES={'desktop_market_valuation_'+code for code in (
    'input_invalid','calendar_options_conflict','capacity_invalid','stage_invalid','context_invalid','store_invalid',
    'completion_required','period_uncovered','source_conflict','mapping_invalid','fx_pair_ambiguous','unused_exceptions','stale','source_busy','confirmation_required','staged_not_published')}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=('prepare','detail','list','confirm','publish','portfolio-input','retain-plan','retain-apply'))
    args=parser.parse_args()
    try:
        raw=sys.stdin.buffer.read(2_000_001)
        if len(raw)>2_000_000:raise ValueError('input too large')
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=_object,parse_constant=_constant)
        if not isinstance(value,dict) or set(value)!={'context','data_space_path','payload'}:raise ValueError('invalid fields')
        result={'status':'completed','value':operate(value['data_space_path'],value['context'],args.command,value['payload'])};code=0
    except Exception as error:
        message=str(error)
        result={'status':'blocked','code':message if message in CODES else 'desktop_market_valuation_input_invalid'};code=1
    print(json.dumps(result,ensure_ascii=True,allow_nan=False,separators=(',',':')))
    return code


if __name__=='__main__':raise SystemExit(main())
