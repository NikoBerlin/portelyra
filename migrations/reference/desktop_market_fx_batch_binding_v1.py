"""Server-only binding to existing Market/FX adapters; no implicit network call.

The caller resolves targets from its trusted catalog, not from browser labels.
Preparation calls only native read-only previews. Execution requires an explicitly
injected transport and must run inside the persistent batch coordinator's claim.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Callable, Mapping

from migrations.reference import desktop_fx_history_review_v1 as fx
from migrations.reference import desktop_market_history_review_v1 as market
from migrations.reference import desktop_market_fx_batch_execution_v1 as execution
from migrations.reference import desktop_market_calendar_batch_v1 as calendar_batch
from migrations.reference.desktop_provider_probe_v1 import history_provider_v1


class MarketFxBatchBindingError(RuntimeError):
    def __init__(self, code="desktop_market_fx_batch_binding_invalid"):
        self.code = code
        super().__init__(code)


def _invalid():
    raise MarketFxBatchBindingError()


def _worker(context):
    return {**execution._context(context), "actor_id": "market_worker", "role": "market_worker"}


def _validate_item(item, context):
    binding = item.get("execution_binding")
    if not isinstance(binding, dict) or set(binding) != {
        "version", "context_fingerprint", "item_fingerprint", "trusted_preview", "binding_fingerprint"
    }:
        _invalid()
    if (binding["version"] != 1 or binding["context_fingerprint"] != execution._sha(context)
        or binding["item_fingerprint"] != execution._sha({k: v for k, v in item.items() if k != "execution_binding"})
        or binding["binding_fingerprint"] != execution._sha({k: v for k, v in binding.items() if k != "binding_fingerprint"})):
        _invalid()
    native = binding["trusted_preview"]
    if not isinstance(native, dict):
        _invalid()
    if item["kind"] == "market":
        market.public_desktop_market_history_review_fetch_preview_v1(native)
        if (native["scope_start_date"] != item["start_date"] or native["scope_end_date"] != item["end_date"]
            or native["target_day_count"] != item["calendar_day_count"] or native["mode"] != "incremental"
            or history_provider_v1(native["mapping"]["provider_id"]) is None
            or native["context_fingerprint"] != market._context_fingerprint(_worker(context))):
            _invalid()
        source = native["listing"]["quote_currency"]
        if not item["route"].startswith(source + "→"):
            _invalid()
    elif item["kind"] == "fx":
        fx.public_desktop_fx_history_fetch_preview_v1(native)
        if (native["start_date"] != item["start_date"] or native["end_date"] != item["end_date"]
            or native["calendar_day_count"] != item["calendar_day_count"]
            or native["context_fingerprint"] != execution._sha(context)
            or item["route"] != native["source_currency"] + "→" + native["target_currency"]):
            _invalid()
    else:
        _invalid()
    return native


def prepare_market_fx_product_batch_v1(data_space_path, context_value, public_batch_value,
                                      server_targets, created_at_utc):
    """Return a private executable batch AND a public binding-review projection.

    Each target must reference the exact public item's content hash. This prevents
    accidental ordinal/label reuse. Native adapters prove current mapping revisions
    or FX-pair bindings. Neither return value itself grants provider authority.
    """
    context = execution._context(context_value)
    space = execution._space(data_space_path, context)
    batch = execution._batch(public_batch_value)
    if calendar_batch.KEY in batch:
        _invalid()  # calendar provenance can only come from the sealed handoff
    execution._utc(created_at_utc)
    if (not isinstance(server_targets, list) or len(server_targets) != len(batch["items"])
        or any("execution_binding" in item for item in batch["items"])):
        _invalid()
    original_fingerprint = execution._sha(batch)
    worker = _worker(context)
    identities = set()
    for index, (item, target) in enumerate(zip(batch["items"], server_targets)):
        item_fingerprint = execution._sha(item)
        if (not isinstance(target, Mapping) or target.get("item_fingerprint") != item_fingerprint
            or target.get("kind") != item["kind"]):
            _invalid()
        if item["kind"] == "market":
            if set(target) != {"kind", "item_fingerprint", "listing_ref", "mapping", "promotion_binding"}:
                _invalid()
            native = market.preview_desktop_market_history_review_fetch_v1(
                space, worker, target["listing_ref"], target["mapping"], target["promotion_binding"],
                item["start_date"], item["end_date"], "incremental",
                "mhn_" + execution._sha([original_fingerprint, index, created_at_utc])[:32], created_at_utc)
            identity = ("market", native["listing"]["listing_ref"], item["start_date"], item["end_date"])
        else:
            if set(target) != {"kind", "item_fingerprint", "source_currency", "target_currency"}:
                _invalid()
            native = fx.preview_desktop_fx_history_fetch_v1(
                space, worker, target["source_currency"], target["target_currency"],
                item["start_date"], item["end_date"], created_at_utc)
            identity = ("fx", native["pair"]["pair_ref"], item["start_date"], item["end_date"])
        if identity in identities:
            _invalid()
        identities.add(identity)
        binding = dict(version=1, context_fingerprint=execution._sha(context),
                       item_fingerprint=item_fingerprint, trusted_preview=native)
        binding["binding_fingerprint"] = execution._sha(binding)
        item["execution_binding"] = binding
        _validate_item(item, context)
    _assert_available(space, context, batch)
    return {"trusted_batch": batch, "public_review": public_market_fx_binding_review_v1(batch, context)}


def public_market_fx_binding_review_v1(trusted_batch, context_value):
    context = execution._context(context_value)
    batch = execution._batch(trusted_batch)
    previous_end = {}
    for item in batch["items"]:
        native = _validate_item(item, context)
        identity = (item["kind"], native["listing"]["listing_ref"] if item["kind"] == "market" else native["pair"]["pair_ref"])
        if identity in previous_end and item["start_date"] <= previous_end[identity]:
            _invalid()  # no overlapping ranges or duplicate routes hidden by labels
        previous_end[identity] = item["end_date"]
    public = copy.deepcopy(batch)
    public.pop(calendar_batch.KEY, None)
    for item in public["items"]:
        del item["execution_binding"]
    public["target_reviews"] = []
    for ordinal, item in enumerate(batch["items"], 1):
        native = item["execution_binding"]["trusted_preview"]
        provider = native["mapping"] if item["kind"] == "market" else native["provider_binding"]
        public["target_reviews"].append(dict(ordinal=ordinal, kind=item["kind"], consumer=item["consumer"],
            consumer_ref=item.get("consumer_ref"), provider_id=provider["provider_id"],
            provider_symbol=provider["provider_symbol"], provider_currency=provider["provider_currency"],
            source_route=native["listing"]["quote_currency"] if item["kind"] == "market" else
                native["pair"]["base_currency"] + "→" + native["pair"]["quote_currency"],
            direction="market_close" if item["kind"] == "market" else native["direction"]))
    public["binding_review_version"] = 1
    public["bound_content_fingerprint"] = execution._sha(batch)
    public["binding_fingerprints"] = [item["execution_binding"]["binding_fingerprint"] for item in batch["items"]]
    return public


def confirm_market_fx_product_batch_v1(trusted_batch, public_review, context_value,
                                      confirmed, issued_at_utc, expires_at_utc, *, data_space_path=None,
                                      selected_ordinals=None):
    if isinstance(trusted_batch, Mapping) and calendar_batch.KEY in trusted_batch:
        if data_space_path is None:
            raise calendar_batch.CalendarBatchError('input_invalid')
        space = execution._space(data_space_path, execution._context(context_value))
        calendar_batch.validate_handoff(space, context_value, trusted_batch)
    if confirmed is not True or public_review != public_market_fx_binding_review_v1(trusted_batch, context_value):
        raise MarketFxBatchBindingError("desktop_market_fx_batch_binding_confirmation_required")
    if selected_ordinals is not None:
        ordinals = execution._selected_ordinals(selected_ordinals, trusted_batch)
        context = execution._context(context_value)
        space = execution._space(data_space_path, context)
        path = space / execution.AREA / (execution._identity(trusted_batch, context) + ".json")
        if os.path.lexists(path):
            state = execution._load(path, trusted_batch, context)
            if any(row["status"] == "provider_call_started" for row in state["items"]):
                execution._abort(execution.PREFIX + "recovery_required")
            for n in ordinals:
                if state["items"][n - 1]["status"] != "pending" or not _can_start(space, context, state, n - 1):
                    execution._abort(execution.PREFIX + "selection_blocked")
        return execution.confirm_market_fx_selected_batch_v1(space, trusted_batch, context,
            ordinals, issued_at_utc, expires_at_utc)
    return execution.confirm_market_fx_batch_v1(trusted_batch, context_value, issued_at_utc, expires_at_utc)


def stage_market_fx_product_batch_v1(data_space_path, context_value, trusted_batch,
                                    confirmation, executed_at_utc, *, transport, clock):
    # Validate all bindings before the first persistent claim.
    public_market_fx_binding_review_v1(trusted_batch, context_value)
    calendar_batch.validate_handoff(Path(data_space_path), context_value, trusted_batch)
    _assert_available(Path(data_space_path), execution._context(context_value), trusted_batch)
    return execution.execute_market_fx_batch_v1(
        data_space_path, context_value, trusted_batch, confirmation, executed_at_utc,
        lambda item: _stage_with_calendar(data_space_path, context_value, trusted_batch, item,
                                          transport=transport, clock=clock),
        can_start=lambda state, index: _can_start(data_space_path, context_value, state, index),
        preflight=lambda: calendar_batch.preflight_before_claim(data_space_path, context_value, trusted_batch))


def _item_scope(item):
    native = item["execution_binding"]["trusted_preview"]
    return (item["kind"], native["listing"]["listing_ref"] if item["kind"] == "market" else native["pair"]["pair_ref"])


def _conflicts(space, context, batch, item):
    # A freshly generated preview must not bypass an unresolved prior call after
    # restart (especially FX, whose canonical coverage is unchanged by staging).
    from migrations.reference.desktop_market_fx_batch_publication_v1 import _load_publication
    own_ref = execution._identity(batch, context)
    for public in execution.list_market_fx_batches_v1(space, context):
        if public["execution_ref"] == own_ref:
            continue
        prior_batch = execution.load_market_fx_batch_v1(space, context, public["execution_ref"])["trusted_batch"]
        prior = execution._load(Path(space) / execution.AREA / (public["execution_ref"] + ".json"), prior_batch, context)
        published = _load_publication(Path(space), context, prior)
        for index, previous in enumerate(prior_batch["items"]):
            if published["items"][index]["status"] == "published":
                continue
            if (_item_scope(previous) == _item_scope(item) and previous["start_date"] <= item["end_date"]
                and item["start_date"] <= previous["end_date"]):
                return True
    return False


def _assert_available(space, context, batch):
    if any(_conflicts(space, context, batch, item) for item in batch["items"]):
        raise MarketFxBatchBindingError("desktop_market_fx_batch_recovery_required")


def _can_start(space, context, state, index):
    # A native Market review must be published before the next range of the same
    # listing is staged. Other listings and FX items may proceed independently.
    item = state["batch"]["items"][index]
    calendar_batch.assert_calendar_current(space, context, state['batch'])
    from migrations.reference.desktop_market_fx_batch_publication_v1 import _load_publication
    publication = _load_publication(Path(space), execution._context(context), state)
    if any(row["status"] == "publish_started" for row in publication["items"]):
        return False
    if _conflicts(space, execution._context(context), state["batch"], item):
        return False
    if item["kind"] != "market":
        return True
    listing_ref = item["execution_binding"]["trusted_preview"]["listing"]["listing_ref"]
    predecessors = [i for i, prior in enumerate(state["batch"]["items"][:index])
                    if prior["kind"] == "market" and prior["execution_binding"]["trusted_preview"]["listing"]["listing_ref"] == listing_ref]
    if not predecessors:
        return True
    return all(publication["items"][i]["status"] == "published" or state["items"][i]["status"] == "failed"
               for i in predecessors)


def resume_market_fx_product_batch_v1(data_space_path, context_value, trusted_batch,
                                     confirmation, resumed_at_utc, *, transport, clock):
    public_market_fx_binding_review_v1(trusted_batch, context_value)
    calendar_batch.validate_handoff(Path(data_space_path), context_value, trusted_batch)
    return execution.resume_market_fx_batch_v1(
        data_space_path, context_value, trusted_batch,
        lambda item: _stage_with_calendar(data_space_path, context_value, trusted_batch, item,
                                          transport=transport, clock=clock),
        confirmation=confirmation, resumed_at_utc=resumed_at_utc,
        can_start=lambda state, index: _can_start(data_space_path, context_value, state, index))


def _stage_with_calendar(space, context, batch, item, *, transport, clock):
    calendar_batch.assert_calendar_current(space, context, batch)
    def guarded_transport(*args, **kwargs):
        # Native validation and durable attempt creation happen before this gate.
        # A late calendar change must still not reach the network transport.
        calendar_batch.assert_calendar_current(space, context, batch)
        return transport(*args, **kwargs)
    return stage_market_fx_bound_item_v1(space, context, item, transport=guarded_transport, clock=clock)


def stage_market_fx_bound_item_v1(data_space_path, context_value, item, *, transport: Callable, clock: Callable):
    """Only called AFTER the coordinator durably claims the item."""
    if not callable(transport) or not callable(clock):
        _invalid()
    context = execution._context(context_value)
    space = execution._space(data_space_path, context)
    native = _validate_item(item, context)
    worker = _worker(context)
    if item["kind"] == "market":
        stage = market.stage_desktop_market_history_review_fetch_v1(
            space, worker, native, market.public_desktop_market_history_review_fetch_preview_v1(native),
            True, transport=transport, clock=clock)
        return {"status": "staged", "kind": "market", "binding_fingerprint": item["execution_binding"]["binding_fingerprint"],
                "stage": stage, "public_review": market.public_desktop_market_history_review_stage_v1(stage)}
    # Native FX staging alone does not revalidate current pair bindings; do so
    # explicitly before allowing its transport to run. Changed coverage also blocks.
    current = fx.preview_desktop_fx_history_fetch_v1(
        space, worker, native["source_currency"], native["target_currency"],
        native["start_date"], native["end_date"], native["created_at_utc"])
    if current != native:
        _invalid()
    stage = fx.stage_desktop_fx_history_fetch_v1(
        space, worker, native, fx.public_desktop_fx_history_fetch_preview_v1(native), True,
        transport=transport, clock=clock)
    return {"status": "staged", "kind": "fx", "binding_fingerprint": item["execution_binding"]["binding_fingerprint"],
            "stage": stage, "public_review": fx.public_desktop_fx_history_review_v1(stage)}


def recover_market_fx_bound_outcome_v1(data_space_path, context_value, item):
    """Confirmed recovery only: stages OR exact native failed-fetch acknowledgement.

    No transport, no market writer, no claim reset. Failed scopes remain reserved
    against replacement batches. Missing/unsealed failure evidence stays unknown.
    """
    staged = read_market_fx_bound_staging_v1(data_space_path, context_value, item)
    if staged is not None:
        return staged
    context = execution._context(context_value)
    space = execution._space(data_space_path, context)
    native = _validate_item(item, context)
    if item["kind"] != "market":
        return None  # FX v1 has no sealed terminal failure receipt.
    ref = market._stage_ref(native["preview_fingerprint"])
    area = space / market.AREA
    failure_path = area / "failures" / ("fetch-" + ref + ".json")
    if not os.path.lexists(failure_path):
        return None
    attempt = market._read_fetch_attempt(area / "fetch-attempts" / (ref + ".json"), market._context(_worker(context)))
    if any(attempt[key] != native[key] for key in ("preview_fingerprint", "context_fingerprint", "scope_start_date", "scope_end_date")) or (
        attempt["listing_ref"] != native["listing"]["listing_ref"]
        or attempt["mapping_fingerprint"] != native["mapping"]["mapping_fingerprint"]
        or attempt["started_at_utc"] < native["created_at_utc"]):
        _invalid()
    failure = market._read_fetch_failure(failure_path, attempt)
    recovered = market.recover_desktop_market_history_review_v1(
        space, _worker(context), native["listing"]["listing_ref"], True, expected_stage_ref=ref)
    if not recovered or recovered["state"] != "fetch_failed" or recovered["stage_ref"] != ref:
        _invalid()
    return {"status": "failed", "kind": "market",
            "binding_fingerprint": item["execution_binding"]["binding_fingerprint"],
            "attempt": attempt, "failure": failure, "native_recovery": recovered}


def read_market_fx_bound_staging_v1(data_space_path, context_value, item):
    """Read-only native result recovery. Never calls stage, publish or transport."""
    context = execution._context(context_value)
    space = execution._space(data_space_path, context)
    native = _validate_item(item, context)
    if item["kind"] == "market":
        ref = market._stage_ref(native["preview_fingerprint"])
        path = space / market.AREA / "stages" / (ref + ".json")
        if not os.path.lexists(path):
            return None
        stage = market.read_desktop_market_history_review_stage_v1(space, _worker(context), ref)
        if stage["preview_fingerprint"] != native["preview_fingerprint"]:
            _invalid()
        public = market.public_desktop_market_history_review_stage_v1(stage)
    else:
        path = space / fx.STAGE_AREA / "results" / ("fxh_" + native["preview_fingerprint"][:32] + ".json")
        if not os.path.lexists(path):
            return None
        # Reject linked ancestors as well as a linked result before reading.
        if path.resolve(strict=True) != path:
            _invalid()
        execution._check_owner(space / fx.STAGE_AREA, True)
        stage = execution._read(path)
        if (stage.get("staging_fingerprint") != execution._sha({k: v for k, v in stage.items() if k != "staging_fingerprint"})
            or stage.get("preview_fingerprint") != native["preview_fingerprint"]
            or stage.get("status") != "staged"
            or stage.get("candidate", {}).get("pair_ref") != native["pair"]["pair_ref"]
            or any(stage.get(k) != native[k] for k in ("source_currency", "target_currency", "direction", "start_date", "end_date"))):
            _invalid()
        public = fx.public_desktop_fx_history_review_v1(stage)
    return {"status": "staged", "kind": item["kind"], "binding_fingerprint": item["execution_binding"]["binding_fingerprint"],
            "stage": stage, "public_review": public}
