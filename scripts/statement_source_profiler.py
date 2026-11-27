#!/usr/bin/env python3
"""Run the ADR-164 profiler against repository-tracked invented fixtures only."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations.reference.desktop_statement_source_profiler_v1 import (  # noqa: E402
    DesktopStatementSourceProfilerError,
    inspect_registered_synthetic_statement_sources_v1,
)


def main() -> int:
    if len(sys.argv) != 1:
        print(json.dumps({"status": "desktop_statement_source_profiler_input_invalid"}, separators=(",", ":")))
        return 1
    try:
        result = {
            "private_source_read": False,
            "results": inspect_registered_synthetic_statement_sources_v1(),
            "statement_source_profiler_synthetic_review_version": 1,
            "status": "completed_synthetic_only",
        }
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")))
        return 0
    except DesktopStatementSourceProfilerError as error:
        print(json.dumps({"status": error.code}, separators=(",", ":")))
        return 1
    except Exception:
        print(json.dumps({"status": "desktop_statement_source_profiler_boundary_failed"}, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
