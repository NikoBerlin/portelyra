#!/usr/bin/env python3
"""JSON-stdin boundary for the intraday market snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from migrations.reference.price_provider_admin_v1 import guard_payload_v1  # noqa: E402 - Kursanbieter je Datenraum (rc.383)

from migrations.reference.desktop_intraday_snapshot_v1 import (  # noqa: E402
    DesktopIntradaySnapshotBlocked,
    read_intraday_snapshot_v1,
    snapshot_intraday_v1,
)
from migrations.reference import market_valuation_state_v1 as state  # noqa: E402
from migrations.reference.desktop_product_asset_activity_v1 import (  # noqa: E402
    DesktopProductAssetActivityContextV1,
)
from workers.reference.portfolio_intraday_projection_v1 import (  # noqa: E402
    project_portfolio_intraday_snapshot_v1,
)
from workers.reference.portfolio_snapshot_projection_v1 import (  # noqa: E402
    PortfolioSnapshotProjectionV1Error,
)
from migrations.reference.user_settings_v1 import (  # noqa: E402
    UserSettingsV1Error,
    market_settings_v1,
    owner_settings_context_v1,
    set_market_setting_v1,
)


class _CliInputError(ValueError):
    pass


def _emit(value: object) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                sort_keys=True, separators=(",", ":")))


def _read_payload(command: str) -> dict:
    raw = sys.stdin.buffer.read(200_000)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _CliInputError("request is not strict JSON") from error
    fields = {
        "snapshot": {"context", "data_space_path", "confirmed", "requested_at_utc"},
        "read": {"context", "data_space_path"},
        "view": {"context", "data_space_path", "as_of_date"},
        "setting": {"context", "data_space_path"},
        "set-parallel": {"context", "data_space_path", "parallel_request_count", "updated_at_utc"},
        "set-carry": {"context", "data_space_path", "carry_across_blocked", "updated_at_utc"},
    }[command]
    if not isinstance(value, dict) or set(value) != fields:
        raise _CliInputError("request fields invalid")
    return value


def _context(value: object) -> dict:
    fields = {"tenant_id", "user_id", "data_space_id"}
    if not isinstance(value, dict) or set(value) != fields:
        raise _CliInputError("context fields invalid")
    return dict(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Portelyra intraday market snapshot v1")
    parser.add_argument("command", choices=("snapshot", "read", "view", "setting", "set-parallel", "set-carry"))
    arguments = parser.parse_args()
    try:
        payload = _read_payload(arguments.command)
        context = _context(payload["context"])
        if arguments.command == "snapshot":
            blocked = guard_payload_v1(payload, "desktop_intraday_snapshot")
            if blocked:
                _emit(blocked)
                return 0
            _emit(snapshot_intraday_v1(payload["data_space_path"], context,
                                       payload.get("confirmed") is True, payload["requested_at_utc"]))
        elif arguments.command == "read":
            # Ein Stand aelteren Aufbaus wird beim naechsten Vorbereiten neu
            # erstellt. Fuer die Anzeige heisst das schlicht: noch kein Snapshot -
            # kein Fehlercode fuer einen Zustand, der sich selbst behebt.
            try:
                _emit(read_intraday_snapshot_v1(payload["data_space_path"], context))
            except state.MarketValuationStateBlocked as error:
                if error.code not in {"market_valuation_state_schema_changed",
                                      "market_valuation_state_algorithm_changed"}:
                    raise
                _emit({"contract_version": "desktop_intraday_snapshot_v1", "status": "absent",
                       "rows": [], "asset_count": 0, "valued_count": 0, "intraday_count": 0,
                       "carried_count": 0, "unavailable_count": 0, "held_asset_count": 0,
                       "market_value_complete": False, "total_market_value_eur": None,
                       "requested_at_utc": None, "provider_access": False,
                       "canonical_write": False, "market_history_write": False})
        elif arguments.command == "view":
            # Das fluide Bild: dieselbe Projektion wie der Stichtags-Snapshot, mit
            # den zuletzt abgerufenen Kursen. Liest nur; den Abruf macht 'snapshot'.
            _emit(project_portfolio_intraday_snapshot_v1(
                payload["data_space_path"],
                DesktopProductAssetActivityContextV1(context["tenant_id"], context["user_id"],
                                                     context["data_space_id"], "desktop_owner"),
                payload["as_of_date"]))
        elif arguments.command == "setting":
            # Seit #554 in den Nutzereinstellungen: der gesetzte Wert, sonst der alte aus dem Bewertungsstand, sonst die Vorgabe.
            _emit({"status": "known", **market_settings_v1(payload["data_space_path"], owner_settings_context_v1(context))})
        elif arguments.command == "set-carry":
            if type(payload["carry_across_blocked"]) is not bool:
                raise _CliInputError("carry_across_blocked must be boolean")
            value = set_market_setting_v1(payload["data_space_path"], owner_settings_context_v1(context), "carry_across_blocked",
                                          "on" if payload["carry_across_blocked"] else "off", payload["updated_at_utc"])
            _emit({"status": "known", "carry_across_blocked": value["carry_across_blocked"]})
        else:
            if type(payload["parallel_request_count"]) is not int or not 1 <= payload["parallel_request_count"] <= 32:
                raise _CliInputError("parallel_request_count out of range")
            value = set_market_setting_v1(payload["data_space_path"], owner_settings_context_v1(context), "snapshot_parallel_requests",
                                          str(payload["parallel_request_count"]), payload["updated_at_utc"])
            _emit({"status": "known", "parallel_request_count": value["parallel_request_count"]})
    except UserSettingsV1Error as error:
        _emit({"status": "blocked", "code": "desktop_intraday_snapshot_input_invalid" if error.code == "user_settings_input_invalid"
               else "user_settings_store_invalid"})
    except (DesktopIntradaySnapshotBlocked, state.MarketValuationStateBlocked,
            PortfolioSnapshotProjectionV1Error, _CliInputError, KeyError, TypeError) as error:
        _emit({"status": "blocked",
               "code": getattr(error, "code", "desktop_intraday_snapshot_input_invalid")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
