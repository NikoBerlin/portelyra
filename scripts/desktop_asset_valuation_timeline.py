#!/usr/bin/env python3
"""CLI-Grenze der Bewertungs-Zeitleiste (#495, rc.393): JSON ueber stdin, eine JSON-Zeile auf stdout.

overview: alle Assets mit Zeitleiste und ihre Abschnitte (fuer Sammellauf, Datenbasis, Asset-Center).
read: die geltende Zeitleiste eines Assets samt Zuordnungen und Kursabdeckung je Reihe (ohne Zeitleiste: ein Abschnitt mit der Art
      aus den Stammdaten).
preview / apply: eine neue Zeitleiste mit Vorschau (Abschnitte, Abdeckung, Vergleich an jedem Anbieterwechsel, ob die Bewertungsart der
      Stammdaten mit umgestellt werden muss) und Einmalbestaetigung. Muss die Art umgestellt werden, stellt die Data-App sie zuerst ueber
      den Katalogbefehl um; apply prueft das.
series: alle Kursreihen (Asset, Symbol), die der Bewertungsstand fuehrt - der Sammellauf bewertet eine fehlende Reihe (#493).
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import asset_valuation_timeline_v1 as timeline  # noqa: E402

CONTEXT_KEYS = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}
COMMANDS = {
    "overview": ((), lambda s, c, v: timeline.overview_v1(s, c)),
    "read": (("asset_id",), lambda s, c, v: timeline.read_timeline_v1(s, c, v["asset_id"])),
    "preview": (("asset_id", "segments"), lambda s, c, v: timeline.preview_timeline_v1(s, c, v["asset_id"], v["segments"])),
    "apply": (("preview", "confirmed"), lambda s, c, v: timeline.apply_timeline_v1(s, c, v["preview"], v["confirmed"])),
    "series": ((), lambda s, c, v: timeline.valued_series_v1(s, c)),
}


def _emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        if command not in COMMANDS:
            raise timeline.AssetValuationTimelineV1Error("asset_valuation_timeline_input_invalid")
        extra, run = COMMANDS[command]
        value = json.loads(sys.stdin.read())
        if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *extra} or not isinstance(value["context"], dict) \
                or set(value["context"]) != CONTEXT_KEYS or not isinstance(value["data_space_path"], str):
            raise timeline.AssetValuationTimelineV1Error("asset_valuation_timeline_input_invalid")
        _emit({"status": "completed", "result": run(value["data_space_path"], value["context"], value)})
        return 0
    except (RuntimeError, OSError, KeyError, TypeError, ValueError, sqlite3.Error) as error:
        code = getattr(error, "code", None)
        if not isinstance(code, str) or not code.startswith("asset_valuation_timeline_"):
            code = "asset_valuation_timeline_input_invalid" if isinstance(error, (ValueError, TypeError, KeyError)) else "asset_valuation_timeline_store_invalid"
        _emit({"status": "blocked", "code": code})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
