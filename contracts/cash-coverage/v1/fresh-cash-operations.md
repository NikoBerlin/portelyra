# Fresh Cash operations

ADR-127 introduced schema-2900. ADR-159 evolves the same Cash Coverage family to **schema-2901** without changing any schema-2900 fact value or meaning.

## Fresh commands

- Catalog creation of Cash Assets and Accounts remains separate and must happen first.
- Cash Assets require `asset_type=cash`, `valuation_method=unit_value`, and an explicit ISO-style three-letter currency.
- `declare_coverage`, `record_cash_event`, `record_interest_income`, and `record_reconciliation` create fresh facts.
- `correct`, `supersede`, and `void` retire active facts through immutable lineage. They never update or delete predecessors.
- A revision may bind several unique `predecessor_refs` and several type-compatible `replacements` in one transaction. Complete-reconciliation corrections therefore cannot expose an intermediate opening/event/reconciliation state.
- `correct` preserves fact kind and portfolio/account/Cash-Asset/currency identity; `supersede` is the explicit operation for a broader replacement; `void` has no replacement facts.

Every command uses Preview → one-use Confirmation/Attempt → immutable facts, lineage, provenance, and receipt. Confirmation is consumed before the authoritative transaction. Exact replay of the same completed command is read-only; a changed payload under the same request is a conflict.

## Time and provenance

Fresh Cash events use `event_time_evidence=exact_local_zone` and provide a mutually consistent `local_date`, `local_time`, IANA `time_zone`, and `effective_at_utc`. DST gaps and inconsistent or unresolved folds fail closed. Migrated schema-2900 events use only `utc_only_legacy`; migration does not invent local time or zone.

Manual entry and reviewed importer input share the same command preview and confirmation boundary. `input_mode` remains `manual_entry` or `reviewed_import`; reviewed input additionally preserves `source_candidate_fingerprint`. Statement adapters remain untrusted candidate producers and never write schema-2901 directly.

## Recovery and boundaries

A consumed command attempt with no proven receipt is not retried blindly. Read-only reconciliation produces a recovery candidate, followed by a separate Recovery Preview → separate one-use Recovery Confirmation → exact finalize-or-reconcile operation. Original and recovery confirmations are never interchangeable.

Opening and observed balances are exact evidence, not inferred values. Missing or partial coverage is not zero. Cash has no FIFO; schema-401 Activity creates no Cash side. Interest Income remains orthogonal to Cash movement. No Provider/network, Tax, canonical, Asset Activity, automation, alarm, deployment, or complete-portfolio authority is introduced.
