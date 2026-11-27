#!/usr/bin/env python3
"""Private JSON-stdin bridge. Never expose its trusted payloads directly to a browser."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from migrations.reference.price_provider_admin_v1 import guard_payload_v1  # noqa: E402 - Kursanbieter je Datenraum (rc.383)

from migrations.reference import desktop_market_fx_batch_execution_v1 as execution
from migrations.reference import desktop_market_fx_batch_binding_v1 as binding
from migrations.reference import desktop_market_fx_batch_publication_v1 as publication
from migrations.reference import desktop_market_calendar_batch_v1 as calendar_batch

BASE = {"context", "data_space_path"}
FIELDS = {
    "prepare": BASE | {"batch", "targets", "created_at_utc"},
    "prepare-calendar": BASE | {"preview_ref", "created_at_utc"},
    "confirm": BASE | {"trusted_batch", "public_review", "confirmed", "issued_at_utc", "expires_at_utc"},
    "confirm-selected": BASE | {"trusted_batch", "public_review", "confirmed", "ordinals", "issued_at_utc", "expires_at_utc"},
    "stage": BASE | {"trusted_batch", "confirmation", "executed_at_utc"},
    "resume": BASE | {"execution_ref", "confirmation", "executed_at_utc"},
    "list": BASE,
    "read": BASE | {"execution_ref"},
    "recover-staging": BASE | {"execution_ref", "ordinal", "confirmed"},
    "review": BASE | {"execution_ref", "ordinals"},
    "confirm-publication": BASE | {"preview", "confirmed", "issued_at_utc", "expires_at_utc"},
    "publish": BASE | {"execution_ref", "preview", "confirmation", "completed_at_utc"},
    "recover-publication": BASE | {"execution_ref", "ordinal", "confirmed"},
}


def dispatch(command, value, *, transport=None, clock=lambda: datetime.now(timezone.utc)):
    if command not in FIELDS or not isinstance(value, dict) or set(value) != FIELDS[command]:
        raise ValueError("invalid payload")
    ctx = execution._context(value["context"])
    space = execution._space(value["data_space_path"], ctx)
    if command == "prepare-calendar":
        return calendar_batch.prepare_calendar_batch(space, ctx, value['preview_ref'], value['created_at_utc'])
    if command == "prepare":
        batch = execution._batch(value["batch"])
        if not isinstance(value["targets"], list) or len(value["targets"]) != len(batch["items"]):
            raise ValueError("invalid targets")
        targets = []
        for item, target in zip(batch["items"], value["targets"]):
            if not isinstance(target, dict) or target.get("public_item") != item:
                raise ValueError("item mismatch")
            targets.append({**{k: v for k, v in target.items() if k != "public_item"}, "item_fingerprint": execution._sha(item)})
        return binding.prepare_market_fx_product_batch_v1(space, ctx, batch, targets, value["created_at_utc"])
    if command == "list":
        values = execution.list_market_fx_batches_v1(space, ctx)
        return {"executions": [publication.read_market_fx_batch_progress_v1(
            space, ctx, execution.load_market_fx_batch_v1(space, ctx, value["execution_ref"])["trusted_batch"])
            for value in values]}
    if command in {"confirm", "confirm-selected"}:
        ordinals = (execution._selected_ordinals(value["ordinals"], execution._batch(value["trusted_batch"]))
                    if command == "confirm-selected" else None)
        return {"confirmation": binding.confirm_market_fx_product_batch_v1(
            value["trusted_batch"], value["public_review"], ctx, value["confirmed"], value["issued_at_utc"], value["expires_at_utc"],
            data_space_path=space, selected_ordinals=ordinals)}
    if command == "confirm-publication":
        return {"confirmation": publication.confirm_market_fx_batch_publication_v1(
            value["preview"], ctx, value["confirmed"], value["issued_at_utc"], value["expires_at_utc"])}
    batch = (value["trusted_batch"] if command == "stage" else
             execution.load_market_fx_batch_v1(space, ctx, value["execution_ref"])["trusted_batch"])
    if command in {"stage", "resume"}:
        # Kursanbieter je Datenraum (rc.383): ohne aktiven Anbieter kein Abruf.
        blocked = guard_payload_v1(value, "desktop_market_fx_batch")
        if blocked:
            raise _Blocked(blocked["code"])
        # The coordinator verifies the exact confirmation before it can invoke
        # this transport. Merely importing/loading/preparing performs no access.
        if transport is None:
            from migrations.reference.desktop_provider_probe_v1 import _default_transport
            transport = _default_transport
        operation = binding.stage_market_fx_product_batch_v1 if command == "stage" else binding.resume_market_fx_product_batch_v1
        operation(space, ctx, batch, value["confirmation"], value["executed_at_utc"], transport=transport, clock=clock)
    elif command == "recover-staging":
        execution.recover_market_fx_batch_item_v1(
            space, ctx, batch, value["ordinal"], lambda item: binding.recover_market_fx_bound_outcome_v1(space, ctx, item),
            confirmed=value["confirmed"])
    elif command == "review":
        return {"preview": publication.preview_market_fx_batch_publication_v1(space, ctx, batch, value["ordinals"])}
    elif command == "publish":
        publication.publish_market_fx_batch_v1(space, ctx, batch, value["preview"], value["confirmation"], value["completed_at_utc"])
    elif command == "recover-publication":
        publication.recover_market_fx_batch_publication_v1(space, ctx, batch, value["ordinal"], confirmed=value["confirmed"])
    return {"trusted_batch": batch, "public_review": binding.public_market_fx_binding_review_v1(batch, ctx),
            "progress": publication.read_market_fx_batch_progress_v1(space, ctx, batch)}


class _Blocked(RuntimeError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite number")


def main():
    parser = argparse.ArgumentParser(description="Explicit owner-local Market/FX batch workflow")
    parser.add_argument("command", choices=tuple(FIELDS))
    args = parser.parse_args()
    try:
        raw = sys.stdin.buffer.read(32_000_001)
        if len(raw) > 32_000_000:
            raise ValueError("too large")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
        result = {"status": "completed", **dispatch(args.command, value)}
        code = 0
    except Exception as error:
        allowed = execution.ERRORS | publication.CODES | calendar_batch.CODES | {
            "desktop_market_fx_batch_binding_invalid", "desktop_market_fx_batch_binding_confirmation_required",
            "desktop_market_fx_batch_provider_inactive", "desktop_market_fx_batch_provider_state_invalid"}
        candidate = getattr(error, "code", None)
        result = {"status": "blocked", "code": candidate if isinstance(candidate, str) and candidate in allowed else "desktop_market_fx_batch_input_invalid"}
        code = 1
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
