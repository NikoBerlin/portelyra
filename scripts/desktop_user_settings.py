#!/usr/bin/env python3
"""CLI-Grenze fuer Nutzereinstellungen (#500) und Schrittdauern von "Alles aktualisieren" (#457) - JSON ueber stdin/stdout."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.user_settings_v1 import (  # noqa: E402
    UserSettingsV1Error, read_step_durations_v1, read_user_settings_v1, record_step_durations_v1, record_user_settings_v1,
)
from workers.reference.display_settings_publication_v1 import (  # noqa: E402
    DisplaySettingsPublicationV1Error, publish_display_settings_v1,
)


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise UserSettingsV1Error("user_settings_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command == "read":
            space, context = _expect(value)
            result = read_user_settings_v1(space, context)
        elif command == "record":
            # Speichern und fuer die anzeigenden Apps veroeffentlichen; schlaegt die Veroeffentlichung fehl, bleibt das Gespeicherte.
            space, context = _expect(value, "values", "recorded_at_utc", "confirmed")
            result = record_user_settings_v1(space, context, value["values"], value["recorded_at_utc"], value["confirmed"])
            try:
                published = publish_display_settings_v1(space, context, value["recorded_at_utc"])
                result = {**result, "publication": published["status"]}
            except DisplaySettingsPublicationV1Error as error:
                result = {**result, "publication": "failed", "publication_code": error.code}
        elif command == "publish":
            space, context = _expect(value, "published_at_utc")
            result = publish_display_settings_v1(space, context, value["published_at_utc"])
        elif command == "durations-read":
            space, context = _expect(value)
            result = read_step_durations_v1(space, context)
        elif command == "durations-record":
            space, context = _expect(value, "durations", "recorded_at_utc")
            result = record_step_durations_v1(space, context, value["durations"], value["recorded_at_utc"])
        else:
            raise UserSettingsV1Error("user_settings_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (UserSettingsV1Error, DisplaySettingsPublicationV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "user_settings_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
