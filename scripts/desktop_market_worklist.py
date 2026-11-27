#!/usr/bin/env python3
"""Strict private worklist bridge; all requests are local, never provider-capable."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.desktop_market_fx_batch import _object, _constant
from migrations.reference.desktop_market_worklist_v1 import operate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('read', 'start', 'update', 'select'))
    args = parser.parse_args()
    try:
        text = sys.stdin.buffer.read(4 * 1024 * 1024 + 1)
        if len(text) > 4 * 1024 * 1024:
            raise ValueError()
        value = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
        if not isinstance(value, dict) or set(value) != {'context', 'data_space_path', 'payload', 'domain'}:
            raise ValueError()
        state = operate(value['data_space_path'], value['context'], args.command, value['payload'], domain=value['domain'])
        print(json.dumps({'status': 'completed', 'worklist': state}, allow_nan=False))
    except Exception:
        print(json.dumps({'status': 'blocked', 'code': 'desktop_market_worklist_invalid'}))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
