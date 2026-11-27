#!/usr/bin/env python3
"""CLI-Grenze fuer die Kursanbieter (rc.383, #495): JSON ueber stdin, eine JSON-Zeile auf stdout.

overview: je Kursanbieter Plugin, Version, Kosten, Adressen, Bedingungen, Abschottung und Stand im Datenraum. Schreibt hoechstens den
          einmaligen Eintrag "Bestand bis rc.382" (Anbieter, zu denen der Datenraum schon Zuordnungen fuehrt).
activation-preview / activation-apply: einen Anbieter im Datenraum ein- oder ausschalten; der Schreibschritt ist an genau seine
          Vorschau gebunden (preview_fingerprint, Stand des Speichers).
selftest: Selbsttest eines Kursanbieter-Plugins ohne Netz. Beruehrt den Datenraum nicht.
costs-overview / costs-preview / costs-apply (rc.390, #546): je kostenpflichtigem Anbieter Zeitlauf ja/nein und Obergrenzen je Tag
          und Monat, mit Vorschau und Bestaetigung; dazu die Abrufe heute und im Monat.
install-preview / install-apply / revert-preview / revert-apply (#486 Schritt 3): Kursanbieter aus einem Paket installieren (Selbsttest,
          Signatur, Update eines mitgelieferten nur signiert) und "Zur vorigen Fassung". Jeder Befehl mit Datenraum laedt dessen
          installierte Anbieter.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import price_provider_admin_v1 as admin  # noqa: E402
from migrations.reference import price_provider_costs_v1 as costs  # noqa: E402
from migrations.reference import price_provider_install_v1 as install  # noqa: E402
from migrations.reference import price_provider_plugins_v1 as providers  # noqa: E402
from migrations.reference import price_provider_selftest_v1 as selftest  # noqa: E402

CONTEXT_KEYS = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}


class PriceProvidersCliError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _expect(value, extra=()):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *extra} or not isinstance(value["context"], dict) \
            or set(value["context"]) != CONTEXT_KEYS or not isinstance(value["data_space_path"], str):
        raise PriceProvidersCliError("price_provider_admin_input_invalid")
    return value["data_space_path"], value["context"]


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if isinstance(value, dict) and isinstance(value.get("data_space_path"), str) and value["data_space_path"]:
            providers.use_data_space_providers_v1(value["data_space_path"])   # installierte Anbieter dieses Datenraums (#486 Schritt 3)
        if command == "overview":
            space, context = _expect(value)
            result = admin.overview_v1(space, context)
        elif command == "activation-preview":
            space, context = _expect(value, ("provider_id", "active"))
            result = admin.preview_activation_v1(space, context, value.get("provider_id"), value.get("active"))
        elif command == "activation-apply":
            space, context = _expect(value, ("preview", "confirmed"))
            result = admin.apply_activation_v1(space, context, value.get("preview"), value.get("confirmed"))
        elif command == "selftest":
            _expect(value, ("provider_id",))
            started = time.monotonic()
            report = selftest.selftest_v1(str(value.get("provider_id")))
            result = dict(report, duration_seconds=round(time.monotonic() - started, 1), canonical_write=False)
        elif command == "costs-overview":
            space, context = _expect(value)
            result = costs.overview_v1(space, context)
        elif command == "costs-preview":
            space, context = _expect(value, ("provider_id", "scheduled_enabled", "daily_cap", "monthly_cap"))
            result = costs.preview_setting_v1(space, context, value.get("provider_id"), value.get("scheduled_enabled"), value.get("daily_cap"),
                                              value.get("monthly_cap"))
        elif command == "costs-apply":
            space, context = _expect(value, ("preview", "confirmed"))
            result = costs.apply_setting_v1(space, context, value.get("preview"), value.get("confirmed"))
        elif command in ("install-preview", "install-apply"):
            extra = ("zip_path",) if command == "install-preview" else ("zip_path", "preview_fingerprint", "confirmed", "recorded_at_utc")
            space, context = _expect(value, extra)
            path = Path(str(value.get("zip_path") or ""))
            if not path.is_file() or path.is_symlink() or path.stat().st_size > 10 * 1024 * 1024:
                raise PriceProvidersCliError("price_provider_install_package_invalid")
            data = path.read_bytes()
            result = install.preview_install_v1(space, context, data) if command == "install-preview" else \
                install.apply_install_v1(space, context, data, value.get("preview_fingerprint"), value.get("confirmed"), value.get("recorded_at_utc"))
        elif command == "revert-preview":
            space, context = _expect(value, ("plugin_id",))
            result = install.preview_revert_v1(space, context, value.get("plugin_id"))
        elif command == "revert-apply":
            space, context = _expect(value, ("plugin_id", "preview_fingerprint", "confirmed", "recorded_at_utc"))
            result = install.apply_revert_v1(space, context, value.get("plugin_id"), value.get("preview_fingerprint"), value.get("confirmed"),
                                             value.get("recorded_at_utc"))
        else:
            raise PriceProvidersCliError("price_provider_admin_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (RuntimeError, OSError, KeyError, TypeError, ValueError, sqlite3.Error) as error:
        code = getattr(error, "code", "price_provider_admin_input_invalid" if isinstance(error, json.JSONDecodeError) else "price_provider_admin_store_invalid")
        if not isinstance(code, str) or not code.startswith("price_provider_"):
            code = "price_provider_admin_store_invalid"
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
