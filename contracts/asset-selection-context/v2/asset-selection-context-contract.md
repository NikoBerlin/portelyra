# Asset Selection Context v2 Contract

## Set algebra

The browser-local scope consists of four independently visible sets:

1. manual Asset refs;
2. the current filter result;
3. their explicitly chosen combination (`manual`, `filter`, `union` or `intersection`), or the explicit reset mode `all`;
4. an exclusion set applied last.

Unknown, malformed or duplicate refs fail closed. Empty results remain empty and never fall back to all. Catalog order controls presentation only; it creates no business order.

## Canonical domain

An Asset is Cash only when its canonical `asset_type` is exactly `cash`; every other valid canonical Asset type is Non-Cash for this facet. Account type, Account label, Wallet semantics, Stablecoin properties and liquidity never classify the Asset.

Each consumer declares its supported domains. Desktop Product Asset Activity v4 declares only `noncash`. Requesting Cash from this consumer returns `unavailable/unsupported_asset_domain`, not zero Assets, irrespective of the selected set-algebra mode. A future Cash consumer requires a separate compatible completed Cash model.

## Account identity and predicates

Catalog, custody and Activity rows share one ephemeral `activity_account_*` ref. Canonical Account IDs remain server-only. Labels may repeat and receive a unique browser-only `selection_label`; labels never become identity.

Selected Account refs use one explicit relation mode:

- `any`: at least one selected Account is related;
- `all`: every selected Account is related;
- `none`: no selected Account is related.

Account evidence is selected independently:

- `current`: exact positive Custody quantity in the fresh completed FIFO/Custody model;
- `historical`: effective Activity source or related Account usage.

Zero Custody is not current holding. `current` is unavailable unless FIFO/Custody is fresh. Historical usage does not imply current holding. Account filtering selects Assets; it does not split Portfolio×Asset FIFO basis across Accounts.

## Read and command boundaries

The projection validates every Asset and Account ref, label and type relationship before filtering. Unknown, stale, malformed or mismatched rows block instead of disappearing. It starts no rebuild or calculation, performs no Provider/network request and writes no Product file or database.

The presentation scope may contain zero, one or many Assets. The Activity command target remains a separate single Non-Cash Asset. Changing filters, algebra, exclusions or Accounts cannot prepare, confirm or execute a command.

## Deferred facets

Cash balances, time/holding intervals, Lot lifecycle, FIFO basis/concentration, Grouping, readiness, Analysis and persisted Market/FX/liquidation facets remain additive. Missing evidence is unavailable rather than approximated.
