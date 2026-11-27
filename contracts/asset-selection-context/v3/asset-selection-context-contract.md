# Asset Selection Context v3 Contract

## Inclusive interval

The optional bounds are ISO calendar dates. `interval_from` means **Von einschließlich** and `interval_to` means **Bis einschließlich**. Either bound may be open; a nonempty lower bound after the upper bound is invalid.

When the interval is enabled, Activity rows outside the bounds are not part of the visible history. Events before `interval_from` may contribute only to exact opening quantity and FIFO continuity. They do not count as Activity in the interval and are not moved to a different date.

## Independent predicates

The interval relation is explicit:

- `activity`: at least one effective Activity date lies in the interval;
- `holding`: the selected holding predicate is true;
- `activity_or_holding`: either predicate is true;
- `activity_and_holding`: both predicates are true.

Each predicate is evaluated in every `Portfolio × Asset` FIFO world and then existentially aggregated to the browser's global Asset ref. `activity_and_holding` combines those two per-Asset aggregates; Activity and holding may therefore be evidenced by different Portfolios. The per-Portfolio interval rows retain the world-local distinction instead of silently merging their quantities.

Holding has a separately selected meaning:

- `any_time`: exact quantity is positive at any point in the interval;
- `at_start`: exact opening quantity is positive;
- `at_end`: exact closing quantity after all Activities through the inclusive upper bound is positive;
- `throughout`: opening quantity and every subsequent in-window state remain positive.

Activity is derived from schema-401 `local_date`. Holding is derived only from the world-local FIFO-v2 sequence and exact `asset_quantity_before_decimal` / `asset_quantity_after_decimal` fields published by Activity read model v5. Binary floating point, tolerances and inferred events are forbidden.

## Freshness and fail-closed behavior

Activity-only filtering does not require fresh FIFO. Any relation containing holding requires `fifo_state=fresh` and `interval_holding_evidence=fresh_completed_fifo_event_quantities`. Missing, pending, failed or stale evidence returns `unavailable/holding_interval_not_fresh`; the interaction starts no rebuild.

Malformed dates, broken FIFO sequence, discontinuous before/after quantities, a final quantity inconsistent with the completed position, unknown refs or identity mismatches block the projection. A valid empty result remains `empty` and never falls back to all.

## Algebra and display

Domain, Account and interval facets form the filter set. V2 algebra remains unchanged: `all`, `manual`, `filter`, `union`, `intersection`, then explicit exclusions last. `all` is an explicit reset to compatible Catalog Assets and therefore does not apply an otherwise available filter set; unavailable evidence still fails closed.

Current FIFO and Custody tables remain current-state tables. The Activity table becomes interval-scoped when enabled. Per-Portfolio interval state exposes only browser refs, presentation labels, booleans, exact opening/closing quantities and a predecessor-context count.

## Identity and command boundary

Catalog, positions, custody, events and interval states use the same ephemeral `activity_asset_*` refs. Account facets continue to use `activity_account_*` refs. Canonical IDs remain server-only and labels never become identity.

The browser-local display scope may contain zero, one or many Assets. The write form retains exactly one separately validated target Asset. Changing dates, holding semantics or selection algebra cannot prepare, confirm or execute an Activity command.

## Legacy provenance

No Legacy runtime, calculation or write code is copied. The only adopted UX concept is a user-visible date interval. Its implementation is newly derived from canonical schema-401 dates and the completed FIFO-v2 artifact and is covered by focused contract and reactive tests.
