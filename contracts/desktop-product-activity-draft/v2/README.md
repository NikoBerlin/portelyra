# Persistent multi-void ActivityDraft v2

Native/R-adapter and shared-form integration are implemented in the working tree.
This is not a production release or an installed Data-UX test stand.

Uses the existing `activity-drafts-v1` owner and storage, locks, revision checks,
validation fingerprints, one-use confirmations and immutable attempt evidence.
No second writer or independent per-event drafts are introduced.

The public v2 draft reports the selected count without exposing event refs. New
batch drafts overlapping an applying correction are blocked rather than creating
replacement drafts. The R correction center forwards the whole selection in one
preview/confirmation/apply sequence and rejects duplicate refs and batch edits.

Only v2 drafts accept a sorted, unique array of 2–1000 event refs in the existing
`predecessor_event_ref` slot. This shape is versioned explicitly: v1 scalar drafts
remain unchanged and cannot contain a batch. Only correction/void with an empty
replacement event is valid. `portfolio_id` is the existing anchor field, not a
filter narrowing the selected set; the native preview checks every selected world.

One validation delegates the entire set to the native common FIFO preview. One
apply delegates the same persistent plan and confirmation to the existing sole
Activity-generation writer. Applying drafts cannot be blindly executed again.

## Two distinct recovery actions

`resume_desktop_activity_draft_v1` treats a v2 applying draft differently from v1:
it verifies the original durable attempt and reconciles an already active,
matching native batch receipt. Historical confirmation identifies evidence; it
does not authorize a current write, and no backdated apply is invoked. Only draft
completion metadata is saved. No Activity generation or pointer is changed.

Absent, inactive, ambiguous or advanced generation evidence blocks receipt-only
reconciliation. It never activates an unfinished batch.

`build_desktop_activity_draft_recovery_confirmation_v2` rereads the SAME applying
draft and its unique original attempt. Its separate v2 confirmation binds context,
draft, revision, validation and `original_attempt_fingerprint`. The UI presents the
stored complete selection/FIFO/custody preview and requires a new checkbox event;
its grant expires after five minutes. `recover_desktop_activity_draft_v2` consumes
a separate one-use journal under `recovery-attempts-v2`, then delegates fresh
current-time authority to the existing Activity writer. Original attempts and
receipts are neither changed nor replaced. Different heads/canonical fingerprints
block rather than rebasing the original plan. An uncertain recovery also requires
an explicit evidence reread and a fresh grant, not reuse of its consumed grant.

Receipt timestamps describe the immutable generation artifact; recovery journals
record the actual fresh attempt time separately. Completion metadata uses the same
receipt timestamp whether obtained directly or after a lost response. A refresh
never automatically selects another pending draft. Successful completion remains
visible after the completed draft disappears from the open-draft selector.

Tests: `tests/contracts/test_desktop_activity_draft_v1.py` exercises persisted
selection, schema, fresh reads, duplicate/invalid selection, one generation,
interruption before native write and lost acknowledgement after domain commit.
During reconciliation the apply entry point is replaced by a failing sentinel;
active pointer and original attempt bytes must remain unchanged. Fresh recovery
after original expiry covers both an unexecuted native attempt and a published
inactive generation; changed original-attempt bindings and expired/replayed grants
are rejected. The browser regression additionally exercises the shared batch form
and performs a separate read-only SQLite/receipt reconciliation.
