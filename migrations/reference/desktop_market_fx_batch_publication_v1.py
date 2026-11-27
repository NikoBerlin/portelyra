"""Separate, content-confirmed publication of persisted Market/FX batch reviews.

No transport import or provider authority. Native history writers remain the only
canonical owners. A crash after a write is reconciled from committed receipts, not
by repeating a publication or fetching a provider again.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path

from migrations.reference import desktop_market_fx_batch_execution_v1 as execution
from migrations.reference import desktop_market_fx_batch_binding_v1 as binding
from migrations.reference import desktop_market_history_review_v1 as market
from migrations.reference import desktop_fx_history_review_v1 as fx
from migrations.reference.fx_history_v1 import read_fx_history_request_receipt_v1

PREFIX = "desktop_market_fx_batch_publication_"
CODES = frozenset(PREFIX + name for name in (
    "input_invalid", "confirmation_required", "stale", "store_invalid", "recovery_required"))


class MarketFxBatchPublicationError(RuntimeError):
    def __init__(self, code):
        self.code = code if code in CODES else PREFIX + "store_invalid"
        super().__init__(self.code)


def _abort(suffix):
    raise MarketFxBatchPublicationError(PREFIX + suffix)


def _path(space, state):
    return space / execution.AREA / (state["execution_ref"] + "-publication.json")


def _seal(value):
    return {**value, "state_fingerprint": execution._sha({k: v for k, v in value.items() if k != "state_fingerprint"})}


def _load_publication(space, context, state):
    path = _path(space, state)
    blank = dict(publication_version=1, execution_ref=state["execution_ref"],
                 content_fingerprint=state["content_fingerprint"], context_fingerprint=execution._sha(context),
                 confirmations={}, items=[dict(ordinal=i + 1, status="waiting_review", approval=None,
                                               result=None, result_fingerprint=None)
                                          for i in range(len(state["items"]))])
    if not os.path.lexists(path):
        return _seal(blank)
    value = execution._read(path)
    if (set(value) != set(blank) | {"state_fingerprint"} or _seal(value) != value
        or any(value[k] != blank[k] for k in ("publication_version", "execution_ref", "content_fingerprint", "context_fingerprint"))
        or not isinstance(value["confirmations"], dict) or not isinstance(value["items"], list)
        or len(value["items"]) != len(blank["items"])):
        _abort("store_invalid")
    for fingerprint, command in value["confirmations"].items():
        if not isinstance(command, dict) or set(command) != {"preview", "confirmation"}:
            _abort("store_invalid")
        confirmation = command["confirmation"]
        try:
            _validate_confirmation(command["preview"], confirmation, context, confirmation["issued_at_utc"])
        except (KeyError, TypeError, MarketFxBatchPublicationError, execution.MarketFxBatchExecutionError):
            _abort("store_invalid")
        if confirmation["confirmation_fingerprint"] != fingerprint:
            _abort("store_invalid")
    for i, item in enumerate(value["items"]):
        if (not isinstance(item, dict) or set(item) != set(blank["items"][i])
            or type(item["ordinal"]) is not int or item["ordinal"] != i + 1
            or item["status"] not in {"waiting_review", "publish_started", "published"}):
            _abort("store_invalid")
        if item["status"] == "waiting_review":
            if any(item[k] is not None for k in ("approval", "result", "result_fingerprint")):
                _abort("store_invalid")
        else:
            command = value["confirmations"].get(item["approval"])
            if (not command or state["items"][i]["status"] != "staged"
                or not any(row["ordinal"] == i + 1 and row["result_fingerprint"] == state["items"][i]["result_fingerprint"]
                           for row in command["preview"]["items"])):
                _abort("store_invalid")
            if item["status"] == "published":
                if (not isinstance(item["result"], dict) or item["result"].get("status") != "published"
                    or item["result_fingerprint"] != execution._sha(item["result"])):
                    _abort("store_invalid")
            elif item["result"] is not None or item["result_fingerprint"] is not None:
                _abort("store_invalid")
    return value


def _save(space, state, publication):
    publication.update(_seal(publication))
    execution._write(_path(space, state), publication)


def _state(space, context, batch):
    return execution._load(space / execution.AREA / (execution._identity(batch, context) + ".json"), batch, context)


def _public_progress(state, publication):
    items = []
    for fetched, published, item in zip(state["items"], publication["items"], state["batch"]["items"]):
        status = published["status"] if published["status"] != "waiting_review" else fetched["status"]
        items.append(dict(ordinal=fetched["ordinal"], kind=item["kind"], consumer=item["consumer"], route=item["route"],
                          start_date=item["start_date"], end_date=item["end_date"], status=status,
                          failure_code=(fetched.get("result") or {}).get("failure", {}).get("failure_code") if status == "failed" else None))
    statuses = {item["status"] for item in items}
    status = ("recovery_required" if statuses & {"provider_call_started", "publish_started"} else
              "published" if statuses == {"published"} else
              "completed_with_failures" if statuses <= {"published", "failed"} else
              "review_required" if "staged" in statuses else "pending")
    return dict(contract_version="desktop_market_fx_batch_progress_v1", execution_ref=state["execution_ref"],
                status=status, items=items, item_count=len(items), silent_drop_count=0,
                automatic_retry=False, provider_refetch=False)


def read_market_fx_batch_progress_v1(data_space_path, context_value, batch_value):
    context, batch = execution._context(context_value), execution._batch(batch_value)
    space = execution._space(data_space_path, context)
    state = _state(space, context, batch)
    return _public_progress(state, _load_publication(space, context, state))


def _preview(space, context, state, publication, ordinals):
    if (not isinstance(ordinals, list) or not ordinals or any(type(i) is not int for i in ordinals)
        or ordinals != sorted(set(ordinals)) or ordinals[0] < 1 or ordinals[-1] > len(state["items"])):
        _abort("input_invalid")
    items = []
    for ordinal in ordinals:
        fetched, published = state["items"][ordinal - 1], publication["items"][ordinal - 1]
        if fetched["status"] != "staged" or published["status"] != "waiting_review":
            _abort("stale")
        item = state["batch"]["items"][ordinal - 1]
        recovered = binding.read_market_fx_bound_staging_v1(space, context, item)
        if recovered != fetched["result"]:
            _abort("stale")
        items.append(dict(ordinal=ordinal, kind=item["kind"], consumer=item["consumer"], route=item["route"],
                          start_date=item["start_date"], end_date=item["end_date"],
                          result_fingerprint=fetched["result_fingerprint"], public_review=recovered["public_review"],
                          daily_rows=[{key: row[key] for key in ("rate_date", "day_status", "rate_decimal", "quality_status")}
                                      for row in recovered["stage"]["candidate"]["days"]] if item["kind"] == "fx" else []))
    body = dict(contract_version="desktop_market_fx_batch_publication_preview_v1", status="ready_for_confirmation",
                execution_ref=state["execution_ref"], content_fingerprint=state["content_fingerprint"],
                execution_state_fingerprint=state["state_fingerprint"], publication_state_fingerprint=publication["state_fingerprint"],
                items=items, item_count=len(items), confirmation_required=True, provider_access=False,
                provider_refetch=False, market_history_write=False, fx_history_write=False, silent_drop_count=0)
    return {**body, "preview_fingerprint": execution._sha(body)}


def preview_market_fx_batch_publication_v1(data_space_path, context_value, batch_value, ordinals):
    context, batch = execution._context(context_value), execution._batch(batch_value)
    space = execution._space(data_space_path, context)
    state = _state(space, context, batch)
    return _preview(space, context, state, _load_publication(space, context, state), ordinals)


def confirm_market_fx_batch_publication_v1(preview, context_value, confirmed, issued_at_utc, expires_at_utc):
    context = execution._context(context_value)
    if (confirmed is not True or not isinstance(preview, dict)
        or preview.get("contract_version") != "desktop_market_fx_batch_publication_preview_v1"
        or preview.get("preview_fingerprint") != execution._sha({k: v for k, v in preview.items() if k != "preview_fingerprint"})):
        _abort("confirmation_required")
    issued, expires = execution._utc(issued_at_utc), execution._utc(expires_at_utc)
    if not 0 < (expires - issued).total_seconds() <= 600:
        _abort("confirmation_required")
    body = dict(contract_version="desktop_market_fx_batch_publication_confirmation_v1",
                preview_fingerprint=preview["preview_fingerprint"], context_fingerprint=execution._sha(context),
                issued_at_utc=issued_at_utc, expires_at_utc=expires_at_utc,
                provider_access_authorized=False, history_publication_authorized=True)
    return {**body, "confirmation_fingerprint": execution._sha(body)}


def _validate_confirmation(preview, confirmation, context, at):
    if not isinstance(confirmation, dict):
        _abort("confirmation_required")
    expected = confirm_market_fx_batch_publication_v1(
        preview, context, True, confirmation.get("issued_at_utc"), confirmation.get("expires_at_utc"))
    if confirmation != expected or not execution._utc(confirmation["issued_at_utc"]) <= execution._utc(at) <= execution._utc(confirmation["expires_at_utc"]):
        _abort("confirmation_required")


def _current_binding(space, context, item):
    native = binding._validate_item(item, context)
    if item["kind"] == "market":
        current, _ = market._validate_current_mapping(space, native["mapping"])
        if current != native["mapping"]:
            _abort("stale")
    else:
        pair, direction, provider = fx._pair(space / fx.AREA / fx.STORE, fx._ctx(binding._worker(context)),
                                              native["source_currency"], native["target_currency"])
        if pair != native["pair"] or direction != native["direction"] or provider != native["provider_binding"]:
            _abort("stale")


def _publish_native(space, context, result, at):
    if result["kind"] == "market":
        return market.publish_desktop_market_history_review_v1(
            space, binding._worker(context), result["stage"]["stage_ref"], result["public_review"], True, at)
    return fx.publish_desktop_fx_history_v1(space, binding._worker(context), result["stage"], result["public_review"], True, at)


def publish_market_fx_batch_v1(data_space_path, context_value, batch_value, preview, confirmation, completed_at_utc):
    context, batch = execution._context(context_value), execution._batch(batch_value)
    space = execution._space(data_space_path, context)
    _validate_confirmation(preview, confirmation, context, completed_at_utc)
    with execution._locked(space, context):
        state = _state(space, context, batch)
        publication = _load_publication(space, context, state)
        fingerprint = confirmation["confirmation_fingerprint"]
        if fingerprint in publication["confirmations"]:
            return _public_progress(state, publication)  # exact replay never continues writes
        ordinals = [row["ordinal"] for row in preview["items"]]
        if preview != _preview(space, context, state, publication, ordinals):
            _abort("stale")
        for ordinal in ordinals:
            _current_binding(space, context, batch["items"][ordinal - 1])
        publication["confirmations"][fingerprint] = dict(preview=copy.deepcopy(preview), confirmation=copy.deepcopy(confirmation))
        _save(space, state, publication)  # consume before first native write
        for ordinal in ordinals:
            item = publication["items"][ordinal - 1]
            item.update(status="publish_started", approval=fingerprint)
            _save(space, state, publication)
            try:
                _current_binding(space, context, batch["items"][ordinal - 1])
                result = _publish_native(space, context, state["items"][ordinal - 1]["result"], completed_at_utc)
                if not isinstance(result, dict) or result.get("status") != "published":
                    _abort("recovery_required")
            except Exception:
                break  # unknown write outcome remains persisted; no untrusted exception details
            item.update(status="published", result=result, result_fingerprint=execution._sha(result))
            _save(space, state, publication)
        return _public_progress(state, publication)


def _recover_native(space, context, result):
    stage = result["stage"]
    if result["kind"] == "market":
        recovered = market.recover_desktop_market_history_review_v1(
            space, binding._worker(context), stage["listing"]["listing_ref"], True,
            expected_stage_ref=stage["stage_ref"])
        if (not recovered or recovered["state"] != "published" or recovered["stage_ref"] != stage["stage_ref"]
            or recovered["public_review"] != result["public_review"]):
            _abort("recovery_required")
        return recovered["public_result"]
    receipt = read_fx_history_request_receipt_v1(space / fx.AREA / fx.STORE, binding._worker(context), stage["candidate"]["request_ref"])
    if receipt is None or receipt.candidate_fingerprint != stage["candidate"]["candidate_fingerprint"]:
        _abort("recovery_required")
    return dict(contract_version="desktop_fx_history_publication_v1", status="published",
                source_currency=stage["source_currency"], target_currency=stage["target_currency"],
                appended_day_count=receipt.appended_day_count, corrected_day_count=receipt.corrected_day_count,
                unchanged_day_count=receipt.unchanged_day_count, provider_access=False, network_access=False,
                fx_history_write=True, canonical_write=False, provider_refetch=False, exact_replay=True)


def recover_market_fx_batch_publication_v1(data_space_path, context_value, batch_value, ordinal, *, confirmed):
    if confirmed is not True:
        _abort("confirmation_required")
    context, batch = execution._context(context_value), execution._batch(batch_value)
    space = execution._space(data_space_path, context)
    if type(ordinal) is not int or not 1 <= ordinal <= len(batch["items"]):
        _abort("input_invalid")
    with execution._locked(space, context):
        state = _state(space, context, batch)
        publication = _load_publication(space, context, state)
        item = publication["items"][ordinal - 1]
        if item["status"] == "published":
            return _public_progress(state, publication)
        if item["status"] != "publish_started":
            _abort("recovery_required")
        # Compare the still-immutable local stage; recovery cannot introduce a new candidate.
        staged = binding.read_market_fx_bound_staging_v1(space, context, batch["items"][ordinal - 1])
        if staged != state["items"][ordinal - 1]["result"]:
            _abort("recovery_required")
        result = _recover_native(space, context, staged)
        item.update(status="published", result=result, result_fingerprint=execution._sha(result))
        _save(space, state, publication)
        return _public_progress(state, publication)
