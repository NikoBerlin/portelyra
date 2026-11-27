#!/usr/bin/env python3
"""Stand der Aktualisierung (#540): veroeffentlichen (Hintergrundlauf) und lesen (alle Apps). Eingabe als JSON auf stdin:
  publish: {"context": {...}, "data_space_path": ..., "status": {...}, "published_at_utc": ...}
  read:    {"context": {...}, "data_space_path": ..., "role": "viewer"|"tax_viewer"|"analysis_viewer"|"desktop_owner"}
Ausgabe: eine JSON-Zeile. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from workers.reference.activity_status_publication_v1 import (  # noqa: E402
    ActivityStatusPublicationV1Error, publish_activity_status_v1, read_activity_status_v1,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("publish", "read"))
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(200_001)
        if len(raw) > 200_000:
            raise ValueError("input too large")
        value = json.loads(raw.decode("utf-8"))
        if args.command == "publish":
            if not isinstance(value, dict) or set(value) != {"context", "data_space_path", "status", "published_at_utc"}:
                raise ValueError("invalid fields")
            result = publish_activity_status_v1(Path(value["data_space_path"]), value["context"], value["status"], value["published_at_utc"])
        else:
            if not isinstance(value, dict) or set(value) != {"context", "data_space_path", "role"}:
                raise ValueError("invalid fields")
            result = read_activity_status_v1(Path(value["data_space_path"]), value["context"], role=value["role"])
        print(json.dumps({"status": "completed", "value": result}, ensure_ascii=True, separators=(",", ":")))
        return 0
    except ActivityStatusPublicationV1Error as error:
        print(json.dumps({"status": "blocked", "code": error.code}, separators=(",", ":")))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "code": "activity_status_input_invalid"}, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
