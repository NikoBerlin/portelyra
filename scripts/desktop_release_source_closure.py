#!/usr/bin/env python3
"""Safe CLI gate for the Desktop Product's declared local source closure."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.reference.desktop_release_source_closure_v1 import (  # noqa: E402
    DesktopReleaseSourceClosureError,
    PYTHON_ROOTS,
    validate_desktop_release_source_closure_v1,
)


FAILURE_CODE = "desktop_release_transitive_source_closure_invalid"
SAFE_PATH = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("desktop_release_source_closure_cli_invalid")


def _safe_relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and SAFE_PATH.fullmatch(value) is not None
        and all(part not in {".", ".."} for part in value.split("/"))
    )


def _load(root: Path) -> tuple[dict[str, bytes], dict[str, bytes]]:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    registry = root / "contracts" / "desktop-product" / "v1" / "source-fingerprints.csv"
    try:
        with registry.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or ())
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error):
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    if (
        not rows
        or fields != ["path", "sha256"]
        or any(set(row) != {"path", "sha256"} for row in rows)
        or any(not _safe_relative(row.get("path")) for row in rows)
        or any(SHA256.fullmatch(row.get("sha256", "")) is None for row in rows)
        or len({row["path"] for row in rows}) != len(rows)
    ):
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    declared = ["AGENTS.md", "VERSION", "contracts/desktop-product/v1/source-fingerprints.csv"]
    declared.extend(row["path"] for row in rows)
    files: dict[str, bytes] = {}
    try:
        for relative in declared:
            path = root.joinpath(*relative.split("/"))
            if path.is_symlink() or not path.is_file():
                raise DesktopReleaseSourceClosureError((relative,))
            files[relative] = path.read_bytes()
        for row in rows:
            if hashlib.sha256(files[row["path"]]).hexdigest() != row["sha256"]:
                raise DesktopReleaseSourceClosureError((row["path"],))
    except OSError:
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    universe: dict[str, bytes] = {}
    try:
        for directory in PYTHON_ROOTS:
            base = root / directory
            if not base.is_dir() or base.is_symlink():
                continue
            for path in base.rglob("*.py"):
                relative = path.relative_to(root).as_posix()
                if path.is_symlink() or not path.is_file():
                    raise DesktopReleaseSourceClosureError((relative,))
                universe[relative] = path.read_bytes()
    except OSError:
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    return files, universe


def main() -> int:
    parser = SafeArgumentParser(add_help=False)
    parser.add_argument("--project-root", required=True)
    try:
        arguments = parser.parse_args()
        root = Path(arguments.project_root).resolve(strict=True)
        files, universe = _load(root)
        validate_desktop_release_source_closure_v1(files, universe_files=universe)
        print('{"status":"complete"}')
        return 0
    except Exception:
        print(json.dumps({"code": FAILURE_CODE, "status": "blocked"}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
