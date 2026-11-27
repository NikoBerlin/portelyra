# Desktop Statement Import Workspace Contract v1

## 1. Scope

This boundary proves a flexible but non-heuristic Statement Import workspace using only an invented Kraken-shaped Ledger CSV. It is a successor slice to ADR-161, not an expansion of ADR-161's adapter-review authority.

The implementation MUST NOT read a private statement, accept a source path, expose Runtime context, access a provider or network, persist temporary output, offer a confirmation, write a Catalog entity, write an ActivityDraft, write schema-401, write Cash schema-2901, write Tax/SQL state, or activate an adapter.

## 2. Versioned source profile

`kraken_ledger_csv_source_v1:r1` is a synthetic profile awaiting acceptance. It binds institution, export profile, medium, locale, format revision, exact ordered header, column-role mapping, explicit routing rules, and time-zone interpretation.

Every source column MUST have exactly one declared disposition: `mapped` or `retained_not_imported`. Header drift fails closed. A changed header or changed semantic mapping requires a new immutable profile revision; it MUST NOT silently reuse `r1`.

The synthetic profile does not prove the shape of any real Kraken export; that is checked separately.

## 3. Row and group identity

Durable source-row identity is the tuple:

1. source profile ID;
2. source profile revision;
3. non-empty unique `txid`.

`refid` is grouping evidence. A future grouped Trade identity uses profile ID, profile revision, `refid`, and sorted member `txid` values. Source ordinal exists only for the closed row ledger and MUST NOT become durable identity. Missing or duplicate `txid` is diagnostic. Date-only matching is forbidden.

## 4. Explicit routing

Routing uses the exact mapped `type`, `subtype`, and `aclass` combination. The synthetic Reward pilot maps only `earn/reward/currency` to the disabled `noncash_reward_activity_v1` adapter family. The synthetic Trade route is deferred, the synthetic fiat route is `cash_domain_deferred`, and an unknown combination is diagnostic. There are no inferred routes or fallback defaults.

Every source row MUST receive exactly one of:

- `new_candidate`;
- `exact_existing_noop`;
- `existing_link_required`;
- `correction_proposed`;
- `ambiguous_match_blocked`;
- `deferred`;
- `cash_domain_deferred`;
- `diagnostic`.

The complete balance MUST report `silent_drop_count=0`. Cash and portfolio completeness claims remain explicitly false; deferral is not completeness.

## 5. Catalog mapping

Portfolio, account, and asset choices are invented browser-local option keys, never canonical IDs inferred from names. Existing options may be selected explicitly. A missing asset yields only a synthetic Catalog preview and `separate_catalog_handoff_required`; the workspace has no Catalog write or confirmation authority.

## 6. Reward enrichment

A Reward without value remains `basis_missing` and is not handoff-ready. The synthetic scenarios demonstrate either:

- exact quantity multiplied by an exact manual unit price; or
- an exact owner-supplied fiat total without deriving or rounding a unit price.

Currency, UTC observation, exact local date, exact local time, and exact local zone are mandatory in the invented enrichment. Arithmetic uses decimal text and integer coefficients; binary float, clamping, and silent rounding are forbidden. Enrichment is an overlay and MUST NOT alter the source row.

A future daily-price request belongs to a separate market-history plan, review, authorization, and publication boundary. It is disabled here and MUST NOT run automatically.

## 7. Reconciliation

Source identity binding has priority over event facts. An identical bound event becomes `exact_existing_noop`; a changed bound event becomes `correction_proposed`. Without a binding, zero complete-fact matches means `new_candidate`, one means `existing_link_required`, and multiple mean `ambiguous_match_blocked`.

A correction MUST preserve its predecessor, require a separate one-use confirmation, and revalidate FIFO before any future write. An exact no-op may be excluded from a future handoff but MUST remain visible in the closed row balance. This workspace performs none of those handoffs.

## 8. Provenance and rejected Legacy behavior

Read-only provenance is an earlier implementation of the Kraken ledger import.

No Legacy implementation code is copied. The vocabulary informed only the synthetic profile draft. Automatic price lookup, hidden defaults, float arithmetic, skipped rows, and direct Product effects are explicitly rejected. The new focused tests use only invented rows and verify exact mapping, drift blocking, identity, enrichment, and every reconciliation disposition.

## 9. Later authorities

Private file selection, one-use source-read authorization, owner-only `0700`/`0600` evidence, acceptance, `owner_accepted_disabled`, adapter activation, Candidate-to-ActivityDraft handoff, immutable correction apply, Catalog creation, provider execution, and Cash import under #184 are separate later steps.
