# Native set-bound Asset Activity void v2

Status: native writer, persistent drafts, shared Data-form presentation and fresh
recovery are implemented in the working tree. Draft authority is documented under
`../../desktop-product-activity-draft/v2/`. This is not a production release or
delivery of an installed Data-UX test stand.

## Native entry points and ownership

`preview_desktop_asset_activity_multi_void_v2` and
`apply_desktop_asset_activity_multi_void_v2` live in
`migrations/reference/desktop_asset_activity_correction_v1.py` and share the
existing generation writer and `_ProductWriterLockV1`. There is no second writer,
no loop of single-void commands and no physical deletion from existing generations.

Exactly 2–1000 distinct predecessors are normalized to a sorted selection. A batch
supports void only, never replacement values or implicit dependent-event inclusion.
All predecessors and their effect fingerprints, canonical fingerprint, source
generation and Activity-set fingerprint are part of one plan fingerprint. The
existing confirmation binds that fingerprint, context, challenge and expiry.

## Shared preview and execution

The producer materializes one private candidate, removes the selected effective
facts there and validates all resulting portfolio/asset FIFO worlds together.
An unselected sale depending on removed inventory blocks the whole preview.
No selection is silently expanded. Selected dependent events can be removed
jointly if the resulting FIFO state is valid.

The v2 public preview adds `selected_event_count`, the complete `selected_events`
review (labels, date/type, quantity and fees), and `batch_fifo_changes`:
changed worlds have presentation ordinals, portfolio/asset labels and exact
before/after quantity, basis, cost-average and realized/income/fee values with
explicit basis currency. Custody quantities remain separate, with account labels
and plan-local ordinals; they do not narrow the portfolio/asset FIFO basis.
`after_state=no_remaining_events` explains a missing after-world explicitly.
These labels/ordinals are not write identities. The shared UI displays every
selected booking, then joint FIFO changes and separate custody effects. The legacy
first-predecessor row is not used as the batch review.

Apply validates the plan seal and the entire source selection under the existing
writer lock, consumes one native attempt, creates one generation, compares the
resulting FIFO fingerprints and activates it through one active-pointer replacement.
The original ledger bytes survive. Receipt v2 stores every predecessor; native
readers validate the whole set and permanently reject reuse of every removed ref.
Old v1 receipts remain supported; old readers must not accept v2 receipts as v1.

## Failure/recovery boundary

Synthetic tests cover after-attempt, completed private generation, published
inactive generation, before activation and after activation. Reconciliation uses
the same native plan, confirmation and attempt; no new draft, claim reset or blind
single-command retry. Published evidence is reused, not recreated.

For a batch with a different active head, native recovery fails closed instead of
assuming that absent predecessors prove this batch was committed. Activation of a
published inactive batch also rechecks the canonical fingerprint under its barrier.
Original native failpoint tests operate within the original confirmation interval.
The additional persistent-draft recovery path supplies separately confirmed fresh
authority after expiry, with current execution time. It preserves the original
plan/confirmation and journals the fresh authority separately; both original and
fresh attempts remain immutable. The fresh native challenge is strictly one-use,
including after interruption. No original grant is replaced or backdated.
The persistent draft path can now reconcile an already active batch receipt after
lost acknowledgement without any Activity write; its historical grant is evidence
only. Explicit context binding is included in batch previews.
The open-draft view provides the complete stored batch preview and separates
receipt-only observation from freshly confirmed recovery. Old v1 correction-history
rows alone are not a batch-recovery authority.

## Tests

`tests/contracts/test_desktop_asset_activity_correction_v1.py` covers the shared
v1/v2 writer, all six normal/failpoint paths, stable selection order, exact remaining
facts, preserved original/canonical bytes, receipt schema, all-predecessor reuse
protection, dependency rejection, tampered selection, duplicate refs, forbidden
replacement and source-generation changes. No provider or productive write.
