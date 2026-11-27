#!/usr/bin/env python3
"""JSON-stdin boundary for staged Desktop Daily Market History review."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from migrations.reference.price_provider_admin_v1 import guard_payload_v1  # noqa: E402 - Kursanbieter je Datenraum (rc.383)

from migrations.reference.desktop_market_history_review_v1 import (  # noqa: E402
    DesktopMarketHistoryReviewV1Error,
    preview_desktop_market_history_review_fetch_v1,
    public_desktop_market_history_review_fetch_preview_v1,
    public_desktop_market_history_review_stage_v1,
    publish_desktop_market_history_review_v1,
    recover_desktop_market_history_review_v1,
    reject_desktop_market_history_review_v1,
    stage_desktop_market_history_review_fetch_v1,
    discard_unresolved_desktop_market_history_review_v1,
    read_desktop_market_history_notation_v1,
    read_desktop_market_history_notations_v1,
)
from migrations.reference.desktop_provider_search_v1 import (  # noqa: E402
    DesktopProviderSearchContextV1,
)


class _CliInputError(ValueError):
    pass


def _emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")))


def _reject_json_constant(value: str) -> None:
    raise _CliInputError(f"non-canonical JSON constant: {value}")


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _CliInputError("duplicate JSON object key")
        value[key] = item
    return value


def _read_payload(command: str) -> dict[str, object]:
    raw = sys.stdin.buffer.read(32_000_001)
    if len(raw) > 32_000_000:
        raise _CliInputError("request too large")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_strict_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _CliInputError("request is not strict JSON") from error
    fields = {
        "preview": {
            "context", "data_space_path", "listing_ref", "mapping",
            "promotion_binding", "scope_start_date", "scope_end_date", "mode",
            "created_at_utc",
        },
        "stage": {
            "context", "data_space_path", "trusted_preview", "public_preview", "confirmed",
        },
        "publish": {
            "context", "data_space_path", "stage_ref", "public_review", "confirmed",
            "completed_at_utc",
        },
        "reject": {
            "context", "data_space_path", "stage_ref", "public_review", "confirmed",
            "rejected_at_utc",
        },
        "recover": {"context", "data_space_path", "listing_ref", "confirmed"},
        "discard": {
            "context", "data_space_path", "listing_ref", "confirmed", "discarded_at_utc",
        },
        "notation": {"context", "data_space_path", "provider_symbol"},
        "notations": {"context", "data_space_path"},
    }[command]
    if not isinstance(value, dict) or set(value) != fields:
        raise _CliInputError("request fields invalid")
    return value


def _context(value: object) -> DesktopProviderSearchContextV1:
    fields = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}
    if not isinstance(value, dict) or set(value) != fields:
        raise _CliInputError("context fields invalid")
    return DesktopProviderSearchContextV1(
        value["tenant_id"],
        value["user_id"],
        value["data_space_id"],
        value["actor_id"],
        value["role"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Portelyra staged Market History Review v1")
    parser.add_argument("command", choices=(
            "preview", "stage", "publish", "reject", "recover", "discard", "notation", "notations",
        ))
    arguments = parser.parse_args()
    try:
        payload = _read_payload(arguments.command)
        context = _context(payload["context"])
        if arguments.command == "preview":
            trusted = preview_desktop_market_history_review_fetch_v1(
                payload["data_space_path"],
                context,
                payload["listing_ref"],
                payload["mapping"],
                payload["promotion_binding"],
                payload["scope_start_date"],
                payload["scope_end_date"],
                payload["mode"],
                "mhn_" + secrets.token_urlsafe(18),
                payload["created_at_utc"],
            )
            _emit(
                {
                    "status": "previewed",
                    "trusted_preview": trusted,
                    "public_preview": public_desktop_market_history_review_fetch_preview_v1(trusted),
                }
            )
        elif arguments.command == "stage":
            # Der Anbieter der Zuordnung aus der vertrauten Vorschau (rc.394); geprueft wird die Vorschau selbst im Modul.
            mapping = payload.get("trusted_preview", {}).get("mapping") if isinstance(payload.get("trusted_preview"), dict) else None
            provider = mapping.get("provider_id") if isinstance(mapping, dict) and isinstance(mapping.get("provider_id"), str) else "yahoo"
            blocked = guard_payload_v1(payload, "desktop_market_history_review", provider)
            if blocked:
                _emit(blocked)
                return 2
            stage = stage_desktop_market_history_review_fetch_v1(
                payload["data_space_path"],
                context,
                payload["trusted_preview"],
                payload["public_preview"],
                payload.get("confirmed") is True,
            )
            _emit(
                {
                    "status": "staged",
                    "stage_ref": stage["stage_ref"],
                    "public_review": public_desktop_market_history_review_stage_v1(stage),
                }
            )
        elif arguments.command == "publish":
            result = publish_desktop_market_history_review_v1(
                payload["data_space_path"],
                context,
                payload["stage_ref"],
                payload["public_review"],
                payload.get("confirmed") is True,
                payload["completed_at_utc"],
            )
            _emit({"status": "published", "public_result": result})
        elif arguments.command == "reject":
            result = reject_desktop_market_history_review_v1(
                payload["data_space_path"],
                context,
                payload["stage_ref"],
                payload["public_review"],
                payload.get("confirmed") is True,
                payload["rejected_at_utc"],
            )
            _emit({"status": "rejected", "public_result": result})
        elif arguments.command == "notations":
            _emit({"status": "known", "rows": read_desktop_market_history_notations_v1(
                payload["data_space_path"], context)})
        elif arguments.command == "notation":
            known = read_desktop_market_history_notation_v1(
                payload["data_space_path"], context, payload["provider_symbol"]
            )
            _emit({"status": "absent"} if known is None else known)
        elif arguments.command == "discard":
            result = discard_unresolved_desktop_market_history_review_v1(
                payload["data_space_path"],
                context,
                payload["listing_ref"],
                payload.get("confirmed") is True,
                payload["discarded_at_utc"],
            )
            _emit(
                {"status": "absent"}
                if result is None
                else {"status": "discarded", "public_result": result}
            )
        else:
            recovered = recover_desktop_market_history_review_v1(
                payload["data_space_path"],
                context,
                payload["listing_ref"],
                payload.get("confirmed") is True,
            )
            _emit({"status": "absent"} if recovered is None else {"status": "recovered", **recovered})
    except (DesktopMarketHistoryReviewV1Error, _CliInputError, KeyError, TypeError) as error:
        _emit(
            {
                "status": "blocked",
                "code": getattr(error, "code", "desktop_market_history_review_input_invalid"),
            }
        )
        return 2
    except Exception:
        _emit({"status": "failed", "code": "desktop_market_history_review_boundary_failed"})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
