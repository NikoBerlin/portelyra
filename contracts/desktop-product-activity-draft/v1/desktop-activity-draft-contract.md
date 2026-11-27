# Desktop ActivityDraft contract v1

## Persistent owner model

An ActivityDraft is an owner-local preparation record bound to one explicit Runtime Context, Data Space, portfolio, origin, action and optimistic revision. Draft JSON is canonical UTF-8 with a trailing newline. Directories are `0700`; draft and Attempt files are `0600`; symlinks and cross-context reads fail closed.

Allowed origins are `manual_form`, `tolerant_csv` and `correction`. Allowed actions are `create`, `correct` and `void`. Correction origin is required for correct/void. A void has no replacement event. Create has no predecessor. Event references are generated server-side when absent and are never in the public projection.

## Shared validation

Every origin calls validator `desktop_activity_draft_shared_v1`.

- Absent canonical event fields produce `needs_input` and an exact sorted `missing_fields` list.
- A complete create delegates to the native Product preview.
- A complete correct/void delegates to the immutable correction preview.
- A complete but invalid domain candidate is `blocked` with only `activity_draft_domain_invalid`.
- Validation performs no schema-201/schema-401 write and no Provider/network access.

Validation is bound to the draft revision and input fingerprint. Updating a draft resets validation.

## Confirmation and write delegation

Only `validated_ready` can be confirmed. The confirmation binds Context, draft reference, revision and validation fingerprint. Its issue time must not precede the sealed validation time, and apply time must not move the draft clock backwards. Apply persists an owner-only `consumed_before_domain_write` Attempt first, including the exact trusted confirmation needed for explicit process-restart recovery, and marks the draft `applying`.

Create then delegates to `apply_desktop_native_asset_activity_v1`. Correct and void delegate to `apply_desktop_asset_activity_correction_v1`. These existing operations remain the sole immutable schema-401 generation writers. ActivityDraft never writes schema 201.

Explicit replay with the same confirmation or `resume_desktop_activity_draft_v1` over the sealed Attempt resumes an interrupted downstream operation and finalizes the draft. The ordinary Recovery Inbox publishes `can_resume` only for `applying`; clicking resume reuses that Attempt and creates neither a new challenge nor a new owner confirmation. Listing, opening and startup never resume automatically. A challenge bound to different bytes is rejected. Committed drafts cannot be edited.

## Explicit Quick Import mapping

Quick Import accepts `portelyra-activity.csv` and binds the active registry-derived `desktop_owner` Context. Inspection publishes owner-authored source keys and labels only. Every non-empty Portfolio, Account, related-Account, Asset and source-Asset key is explicitly mapped to a browser-local Registry reference. Blank primary Portfolio or Account keys may use visibly selected defaults. No mapping creates Catalog objects or accepts a raw canonical ID.

Every Activity row becomes a persistent tolerant-CSV Draft with a server-only deterministic event reference bound to Context, exact source fingerprint and source-row ordinal. The private source binding also seals the owner-authored row key and initial mapped identity. Repeated preparation reuses the same Draft in every lifecycle state; conflicting mapping lineage fails closed. Exact-file replay therefore neither duplicates Draft records nor canonical facts. **„Bereite Zeilen importieren“** captures only rows shown as `ready`. Because earlier rows can change the generation input for later previews, each captured Draft is revalidated immediately before its delegated write. A row that ceases to be ready remains open; a row originally shown as blocked is not silently promoted by the same confirmation.

The single-Asset/default-Account profile remains a fail-closed compatibility path and rejects multiple distinct primary keys.

## Exact source auxiliary evidence

A non-empty `unclassified_fee_decimal` is retained as exact owner-local text outside canonical event fields. A row that simultaneously supplies an already classified fee and an unclassified fee fails before the first Draft write. Shared validation keeps `unclassified_fee_resolution` missing until the owner chooses monetary fee or Asset-fee quantity. The guided transition writes that exact text to one fee field and explicitly nulls the other. Exact zero may be classified as `zero_no_fee`; nonzero evidence cannot be discarded through that action. Generic fee edits cannot bypass unresolved source evidence.

A tolerant source Draft may additionally carry one immutable `fifo_order_evidence` row. Binding it requires the exact Draft event reference, exact-time evidence, an unchanged source-file fingerprint, a positive source-row ordinal, an owner-decision fingerprint and its own content fingerprint. Binding increments the optimistic Draft revision and invalidates prior validation. The evidence remains trusted-only and is forwarded to Product preview/apply; browser output exposes none of its identifiers or fingerprints.

## Deferred source valuation

A tolerant-source Draft may retain immutable `valuation_evidence`: adapter identity and version, `source_provided`, `source_missing`, or `not_applicable` origin, exact source value mode, source currency, and an optional exact source unit price or Fiat total. Generic Draft edits never rewrite that evidence.

The public lifecycle is `valuation_pending` while source-missing Reward valuation remains incomplete. It becomes `owner_manual_complete` after exact owner input or `market_evidence_complete` after one atomic Draft revision binds a confirmed Reward valuation evidence object and its exact unit price. Source-provided evidence remains distinguishable after restart. The dedicated Data-UI action accepts an exact net-after-fee Fiat total or exact unit price and changes the Draft event in one revision. Non-terminating total-to-unit division is rejected without rounding. Validation and one-use canonical confirmation remain separate. A Statement-scoped Reward batch may collect those existing per-Draft confirmations behind one owner-visible batch confirmation. Execution revalidates each Draft immediately before delegating its write, because every prior Reward changes the cumulative generation and FIFO input. Every selected source row receives an explicit committed or blocked disposition; there is no second canonical writer and no silent drop.

## Immutable exact-source generation supersession

A trusted owner may preview one complete obsolete tolerant-CSV source generation by exact source fingerprint, one distinct replacement source fingerprint and an expected Draft count. The selected set must contain every Draft bound to that source and only `editing`, `validated_blocked` or `validated_ready` states. Applying/committed Drafts, partial sets, an already bound replacement source, pending unrelated supersession recovery or a previously superseded source fail closed.

One-use confirmation persists an owner-only supersession Attempt before any generation write. Apply publishes one create-only cumulative generation containing immutable command and Draft-tombstone evidence. Original Draft JSON bytes remain unchanged. The active pointer switches last and makes the entire batch effective atomically. Explicit resume may activate only the exact completed generation bound by the persisted Attempt; no automatic retry exists.

Read/list overlays effective state `superseded`. Update, validation, fee resolution, FIFO-order binding, confirmation apply, resume and exact-source reprepare reject an active tombstone before Draft or schema-401 writes. Replacement-source Draft creation remains a later separate operation.

The first generation installs an owner-only permanent release-awareness barrier at `.writer.lock`; this path becomes a directory and is never a stale lock. Aware releases validate its immutable marker and serialize through `.writer-v2.lock`. Release-unaware writers fail to open the legacy path. An active supersession pointer without that barrier is invalid, and rollback to an unaware release is prohibited.

A mixed-state retirement is an explicit version-2 source command. Preview must bind every Draft under the old fingerprint, the expected total and committed counts, and a distinct unbound replacement fingerprint. Only `editing`, `validated_blocked` and `validated_ready` Drafts receive tombstones. Every `committed` Draft remains active and must match its immutable fingerprint, source ordinal and binding in the durable version-2 Attempt whenever the cumulative generation is read. `applying`, partial or mismatched scopes fail closed. Pointer activation globally retires the old source. An additive permanent marker requires ADR-145-aware writers and blocks RC18 rollback before slot movement.

Supersession and mixed retirement change neither schema 201 nor schema 401 and create no Cash, Provider, network, alarm or automation side effect. Browser-safe preview, receipt and state expose counts and booleans but no source fingerprints, Draft refs, generation refs, Context or paths.

## Context-bound mapping profiles

An explicit save action persists one owner-local profile containing the source keys and trusted Registry targets. The browser sees label, revision, counts and an ephemeral handle only. On load, every Portfolio, Account and Asset ID must still exist in the active Context and is reprojected to a fresh browser-local reference. One deterministic standard-profile slot belongs to the active Runtime/Data-Space Context; no global user or automatic save exists.

## Owner-local Draft repair

Open `needs_input` and `validated_blocked` Drafts are reconstructed with ephemeral handles. The owner may set an exact text value, set a contractually nullable field to null, or remove a field. Account and Asset fields accept only browser-local Registry selections. UTC fields are derived server-side from complete local date/time/zone evidence and are not directly editable. Every repair increments the optimistic revision, invalidates prior validation and requires the shared validator again before one-use confirmation.

## Public/trusted split

Public draft, list, receipt, supersession preview and supersession state objects contain no Context, canonical IDs, event references, source or generation fingerprints, paths or challenges. Trusted objects may contain owner-internal references and must remain in the server process. Public booleans describe browser exposure explicitly.

## Listing and read cost

The trusted list carries, in the order of `draft_refs`, the source fingerprint and the source adapter id of each Draft (`source_fingerprints`, `source_adapter_ids`; `null` where a Draft has none). The adapter id is the `valuation_evidence.adapter_id` of the Draft's source auxiliary evidence — the same value a single read returns. A consumer that needs it per source generation takes it from the list instead of reading one Draft per generation: every single read validates the complete active supersession generation.

Within one list or single-read call the directory chain of the Draft store is verified once: no component may be a symbolic link. Every Draft file is still checked on each access for being a regular, owner-only file and not a symbolic link, and its content is validated in full. Nothing is remembered beyond the call; writing operations verify the complete chain on every access. Before 0.2.0-rc.230 each Draft was read through two full chains, so the number of `lstat` calls grew with the number of Drafts times the directory depth.

## Naming the reason of a blocked Draft

A blocked Draft stores only `activity_draft_domain_invalid`. The reason is read on demand, by a read-only call (`activity-draft-explain`, `migrations/reference/desktop_activity_block_reason_v1.py`): it runs the same domain preview the validation ran — both use `_domain_preview` — and reads the failure. It writes neither Draft nor canonical state and changes no rule; a Draft that is not blocked is reported as `not_blocked`, one whose preview succeeds meanwhile as `no_longer_blocked`.

The explanation carries the failure codes from the outermost to the innermost, a `reason`, and where it can be determined a `detail`:

- `custody_inventory_insufficient`, `inventory_insufficient`: the booking at which the FIFO projection stops working. It is not recomputed: the projection itself is given the events up to a point in time and says from when it fails; the available quantity is taken from its last valid result. Within one day the order is taken from exact timestamps; without them only the day is named. A missing quantity is stated only when the blocking booking carries no asset fee.
- `order_evidence_required`: several bookings of one asset share one timestamp.
- `quantity_scale_exceeded`: the field, its decimal places and the quantity scale of the asset.
- `amount_fields_conflict`, `field_not_accepted`: an amount field that does not belong to the amount input mode, or a field the canonical validator never accepts for the event type.
- `domain_rejected`: everything not yet broken down; the codes are still reported.

The explanation is a trusted object: it carries internal account and asset references and stays in the server process. The surface turns it into one sentence with the labels of the session selection; references, paths and fingerprints do not enter the text. To make the blocking booking determinable, the correction and the native preview attach the FIFO world of the failed probe to the error they raise; code and control flow are unchanged, and the FIFO projection itself is untouched.
