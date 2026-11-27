# Desktop Statement Import Mapping v1

Provider-neutral trusted Data-UI boundary for mapping normalized Statement rows.
The normal interaction follows ADR-173's **tolerant read, explicit preview, strict
write** rule: internal identities and fingerprints remain hidden, additional or reordered
columns do not block a known format, and technical failures are translated into short
actionable messages.

Each mapping row binds exactly one `source_asset_key × source_account_key × event_type`
tuple to one existing target Asset option and one existing target Account option, or
explicitly defers that tuple. One import session may contain any number of unique
mapping rows. Missing mappings remain visible; every source row receives exactly one
disposition and `silent_drop_count` is always zero. Repeated source row keys become an
explicit `duplicate_deferred` disposition rather than a second Draft. The projection
contains a sorted inventory of every unique source tuple and its row count.

Optional owner-local profiles persist private source tuples and canonical target identities
under the explicit Runtime/User/Data-Space context. Every profile update appends an
immutable revision. Loading first produces a change preview and fails applicability when
a stored target is absent from the current read-only Catalog. Browser code receives only
session handles; raw canonical IDs remain in the trusted process.

The adapter supplies its recognized
time representation, while the owner must explicitly confirm one valid IANA timezone for
the session; any normalized row timezone that differs is rejected.

Valuation evidence is adapter-declared, never guessed:

- `source_provided/unit_price`: retain the exact source unit price and currency;
- `source_provided/fiat_total`: retain the exact source total; derive a unit price only
  when division by net Reward quantity terminates exactly;
- `source_missing`: create a valuation-pending Draft handoff;
- source currency differing from the Portfolio base currency remains pending; this
  contract performs no FX or Provider access.

A pending handoff is intentionally suitable for a persistent ActivityDraft with
`needs_input`. Later owner edits change only the Draft event. Immutable source
valuation evidence remains attached, so the browser can distinguish
`valuation_pending`, `source_provided`, and `owner_manual_complete` after restart.

This projector resolves no canonical IDs and performs no Catalog, ActivityDraft,
Canonical, Cash, Tax, Provider, network, activation, release, or deployment write.
Actual Draft creation is delegated to the existing ActivityDraft writer after
browser-local target options are resolved by the trusted Data UI process. Under ADR-174,
the shared handoff is available only after one explicit owner-facing final confirmation.
It creates or reuses at most one Draft per source-row key and returns a complete
reconciliation. The exchange adapters still have no direct Draft or canonical write
authority.
