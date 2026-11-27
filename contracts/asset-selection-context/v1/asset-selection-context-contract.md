# Asset Selection Context v1 Contract

## Scope and algebra

The presentation scope is session-local and resolves browser-local Asset references from one validated catalog. V1 has two explicit modes:

- `selected`: exactly the manual set, including a valid empty set;
- `all`: every compatible Asset in the validated catalog.

An empty selected set never falls back to all. Unknown, duplicate or malformed references fail closed. Selection order does not establish business order or identity.

## Activity projection

The first adapter filters three Data read components together:

- Portfolio × Asset FIFO-world rows;
- Portfolio × Account × Asset custody rows;
- effective Activity-history rows.

The Product surface consumes Activity read model v3. Every FIFO, custody and Event row carries the same ephemeral `activity_asset_*` ref as the current Activity catalog. Filtering uses that ref exclusively; labels are presentation and may repeat. Each row's ref, label and Asset type must agree with its catalog entry. Unknown, stale, malformed or mismatched refs block the projection, and no identities are silently merged.

The catalog also carries a unique browser-only `selection_label`. Unique labels remain concise; duplicate groups add type and an ephemeral group ordinal. This disambiguator is display text only and never becomes identity.

## Command separation

The presentation set may contain zero, one or many Assets. `activity_asset` remains a separate single command target validated by the existing Activity editor. Changing presentation mode or membership cannot prepare, confirm or execute an Activity, Cash, Catalog, Provider, Tax, Market or Projection command.

Asset-Center handoff performs only these browser/session effects:

1. refresh the read/catalog model;
2. select exactly the handed-off Asset in the presentation set;
3. switch the presentation mode to `selected`;
4. select the same Asset as the independent Activity command target;
5. optionally preselect one compatible custody Account;
6. open and focus the command form.

## Boundaries

The projection starts no calculation or rebuild, performs no Provider/network request and writes no file or database. Its public model contains no Context, filesystem path, internal ID, fingerprint, SQL or write handle. `absent` and stale FIFO states remain visible; they are not translated to zero or complete.

## Legacy provenance

Only three UX concepts are derived from the superseded Legacy references `ui.R` and `server_functions/asset_selection_model.R`: searchable manual multi-selection, an explicit mode and a visible summary. Legacy Runtime/write code, path/category identity, calculation coupling and Buy/Sell-row-count position inference are rejected. The implementation and focused test are fresh.

## Deferred extensions

Cash/Non-Cash, Account, time/holding, Lot lifecycle, FIFO basis/concentration, saved definitions and persisted Market/FX/liquidation facets require additive compatible read models and tests. They are never inferred by this v1 slice.
