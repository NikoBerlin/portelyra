#!/usr/bin/env python3
"""Strict JSON-stdin boundary for the synthetic Statement Import workspace v1."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from migrations.reference.desktop_statement_import_workspace_v1 import (  # noqa: E402
    DesktopStatementImportWorkspaceError,
    canonical_desktop_statement_import_workspace_json_bytes_v1,
    review_desktop_statement_import_workspace_synthetic_v1,
)

MAX_STDIN_BYTES = 32_000_000
BOUNDARY_FAILURE = "desktop_statement_import_workspace_boundary_failed"
INPUT_FAILURE = "desktop_statement_import_workspace_input_invalid"


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = child
    return value


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_STDIN_BYTES + 1)
    if not raw or len(raw) > MAX_STDIN_BYTES:
        raise ValueError("stdin_size_invalid")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError("non_finite_json")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("stdin_json_invalid") from error
    if not isinstance(value, dict):
        raise ValueError("stdin_payload_invalid")
    return value


def _failure(code: str) -> dict[str, str]:
    return {"code": code, "status": "blocked"}


def main(argv: list[str]) -> int:
    if argv != ["review-synthetic"]:
        output: dict[str, Any] = _failure(BOUNDARY_FAILURE)
        exit_code = 2
    else:
        try:
            payload = _read_payload()
            if set(payload) != {"scenario"}:
                raise ValueError("payload_fields_invalid")
            result = review_desktop_statement_import_workspace_synthetic_v1(payload["scenario"])
            output = {"result": result, "status": "complete"}
            exit_code = 0
        except DesktopStatementImportWorkspaceError as error:
            output = _failure(error.code)
            exit_code = 2
        except (KeyError, TypeError, ValueError):
            output = _failure(INPUT_FAILURE)
            exit_code = 2
        except Exception:
            output = _failure(BOUNDARY_FAILURE)
            exit_code = 2
    sys.stdout.buffer.write(canonical_desktop_statement_import_workspace_json_bytes_v1(output) + b"\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
