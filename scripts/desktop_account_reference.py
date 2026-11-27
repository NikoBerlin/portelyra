#!/usr/bin/env python3
"""CLI-Grenze fuer die Kontonummer zu einem Konto (JSON ueber stdin/stdout)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.account_reference_v1 import (  # noqa: E402
    AccountReferenceV1Error, read_account_references_v1, record_account_references_v1,
)


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise AccountReferenceV1Error("account_reference_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command == "read":
            space, context = _expect(value)
            result = read_account_references_v1(space, context)
        elif command == "record":
            space, context = _expect(value, "entries", "recorded_at_utc", "confirmed")
            result = record_account_references_v1(space, context, value["entries"], value["recorded_at_utc"], value["confirmed"])
        else:
            raise AccountReferenceV1Error("account_reference_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (AccountReferenceV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "account_reference_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
