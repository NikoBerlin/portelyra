#!/usr/bin/env python3
"""CLI-Grenze des gemeinsamen Plugin-Verwalters (#486 Schritt 3): JSON ueber stdin, eine JSON-Zeile auf stdout.

overview: je Plugin (Leser, Kursanbieter, Steuermodul) Version, Herkunft, Signatur, Zustand.
kind:     welche Art Plugin eine hochgeladene ZIP-Datei enthaelt (aus package.json; ohne: Leser im bisherigen Format), ohne sie zu
          entpacken - damit "Paket installieren" die passende Pruefung startet. Liest die Datei nur.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import plugin_manager_v1 as manager  # noqa: E402
from migrations.reference import statement_reader_plugins_v1 as reader_plugins  # noqa: E402
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1  # noqa: E402

CONTEXT_KEYS = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if command == "kind":
            path = Path(str(value.get("zip_path") or "")) if isinstance(value, dict) else Path("")
            if not path.is_file() or path.is_symlink() or path.stat().st_size > manager.MAX_ZIP_BYTES:
                raise manager.PluginManagerBlocked("plugin_package_unreadable")
            result = manager.package_kind_v1(path.read_bytes())
        elif command == "overview":
            context = value.get("context") if isinstance(value, dict) else None
            space = value.get("data_space_path") if isinstance(value, dict) else None
            if not isinstance(context, dict) or set(context) != CONTEXT_KEYS or not isinstance(space, str) or not space:
                raise manager.PluginManagerBlocked("plugin_manager_input_invalid")
            reader_plugins.use_data_space_plugins_v1(space)
            from migrations.reference import price_provider_plugins_v1 as price_providers  # noqa: PLC0415
            price_providers.use_data_space_providers_v1(space)
            result = manager.overview_v1(Path(space), DesktopProductAssetActivityContextV1(**context))
        else:
            raise manager.PluginManagerBlocked("plugin_manager_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str))
        return 0
    except (manager.PluginManagerBlocked, OSError, ValueError, TypeError) as error:
        code = getattr(error, "code", "plugin_manager_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
