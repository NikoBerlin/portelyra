# Completed asset-selection snapshot v1

Status: producer foundation wired into explicitly confirmed Desktop Workflow runs.
Cockpit filter controls/reader integration and multi-void are NOT delivered by this
contract. No deployment or existing-run rewrite.

## Authority and source

`workers/reference/completed_asset_selection_snapshot_v1.py` is a pure projection
of complete non-cash FIFO evidence for one portfolio. It cannot open a ledger,
fetch prices, start a calculation, publish or authorize a write. The Desktop
Workflow producer supplies its completed FIFO tables and the metadata of the
same fingerprint-bound schema-401 ledger. Metadata reads are worker-side only;
the ledger fingerprint is checked before and after reading metadata.

`asset_selection_snapshot` is additive to the existing completed browser model.
It is included in the calculation fingerprint and the immutable artifact seal.
Older snapshots remain readable; absence means unavailable, not empty. Schema-201
runs and unsupported/incomplete histories explicitly return unavailable.
The normative nested schema is `snapshot.schema.json`; the display reader pins
its bytes and validates the nested structure and revision fingerprint. Browser
envelopes retain additive compatibility, not authority to supply arbitrary evidence.

## Semantics

- A full asset universe includes unheld and closed positions, not only assets
  that could be valued. Cash is explicitly unsupported, not projected as zero.
- Asset/account ordinals are identities within this snapshot revision only.
  Duplicate labels remain distinct. Canonical IDs, source refs and paths are
  stripped. UI selections must be cleared/revalidated when the revision changes.
- Ordered effective events carry dates, exact before/after portfolio quantities
  and all custody changes. Transfer legs are applied as one event; no transient
  zero between legs may break a continuous-holding predicate.
- Quantities use exact fractions internally and canonical decimal strings.
  No binary float, guessed opening, truncated history or silent missing row.
- Ordered complete history is required from genesis through the cutoff. History
  is reconciled to terminal position-summary quantities before publication.
- Holdings outside the covered cutoff, missing history, inconsistent identities
  or unsupported evidence must be unavailable. A complete empty history is
  distinguishable from missing history.
- This is selection/quantity evidence, not a new FIFO-cost authority. Existing
  portfolio FIFO, valuation and cash semantics remain separate.

## Tests and remaining gates

`tests/contracts/test_completed_asset_selection_snapshot_v1.py` checks exact large
quantities, duplicate labels, unheld assets, atomic transfer legs, missing evidence,
terminal reconciliation and explicit emptiness. The existing native schema-401
workflow regression verifies a completed nine-event snapshot and its nested schema.
No viewer Live-SQL path, provider permission or additional ledger writer is added.

Still required before package-B delivery: filter semantics/controls, actual
Data-to-Cockpit relocation, batch-void preview/confirmation,
one-generation commit/recovery and the separate browser/user test stand.
