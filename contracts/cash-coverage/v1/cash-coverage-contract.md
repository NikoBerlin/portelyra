# Cash Coverage Contract v1

## Purpose and authority

Cash is an optional factual balance ledger, not the mandatory counter-entry world of every Asset Trade. Maintenance quality is explicit per Cash Account and effective period; Interest GuV remains orthogonal. The pure evaluator is write-free. Owner-only Data commands persist confirmed facts in the separate Cash Coverage authority.

`schema-2900.sql` is the frozen historical signature. Current `schema.sql` is schema-2901. The version change is explicit: no schema-2900 fact is updated, deleted, or reinterpreted under its old `PRAGMA user_version`.

## Coverage modes

- `not_tracked`: no Cash or Income facts and no balance claim;
- `income_only`: Interest Income may be analyzed, but no Cash balance event or claim exists;
- `partial`: sporadic Cash events provide an explicitly partial delta or indicative balance when an opening exists;
- `complete_reconciled`: exactly one opening balance at period start plus independent observed-balance evidence prove the exact period balance at reconciliation.

Coverage is owner-declared and effective-dated. It is never inferred from row count, balance, Account label, import format, or linked Trade. A Cash Asset requires `asset_type=cash`, `valuation_method=unit_value`, and an explicit three-letter currency. Cash commands never create or repair Catalog rows. Missing Cash is `unavailable`, never zero. Active periods for one Account cannot overlap.

## Cash and Income facts

Cash events are `opening_balance`, one-sided `deposit`, one-sided `withdrawal`, and same-Cash-Asset internal `transfer`. Optional flow classification may state external capital, internal-unlinked movement, investment settlement, Income receipt, or Fee/Tax payment; `unclassified` remains valid. Classification is never inferred. Internal Transfer changes Account distribution but Portfolio-wide Cash effect and GuV remain exactly zero. Negative factual balances are not clamped.

Interest Income is a separate exact fact. Only Income changes Interest GuV; only a Cash event changes Cash balance. An explicit link reconciles separately recorded facts and creates neither fact implicitly.

Every `complete_reconciled` declaration atomically includes one opening event and one independent reconciliation. A closed period reconciles at its end. Observed balance must equal exact opening plus Cash-event deltas. Income is absent from that equation unless independently represented by a Cash event. `partial` never becomes complete by arithmetic inference.

Fresh Cash-event time evidence is `exact_local_zone`: `local_date`, `local_time`, IANA `time_zone`, and `effective_at_utc` must describe the same instant, including DST-fold choice. Migrated schema-2900 events remain `utc_only_legacy` and have null local time and zone.

## Immutable command lifecycle

Fresh creation and `correct`, `supersede`, or `void` use Preview → one-use Confirmation/Attempt → atomic append. Corrections append supersession lineage; predecessor rows remain physical facts. Stable public `cash_record_…` refs select complete active predecessor command fact sets. A compound revision can bind several unique predecessors and type-compatible replacements in one transaction. `correct` preserves fact kind and domain identity; `supersede` is explicit for broader replacement; `void` creates no replacement.

### Raising a period to reconciled (#417, 08.10.2026)

One revision creates more facts than it retires: a `supersede` that replaces exactly one period that is not `complete_reconciled` by a `complete_reconciled` declaration of the same Account, Cash Asset, start and end. Every complete declaration atomically includes its opening and its reconciliation; the predecessor had neither, so they carry no supersession lineage. The period itself is replaced one to one, and an opening already recorded for the predecessor must be retired in the same command, never left beside the new one. Any other revision still requires type-compatible replacements, and the store rejects a revising command whose facts without lineage are anything but that opening on the first day and a reconciliation of the same Account.

This closes a circle: `record_reconciliation` requires a period that is already reconciled, and a revision required equal fact counts, so a balance confirmed at the institution could not be recorded for an export without a balance column. `partial` still never becomes complete by arithmetic inference - the owner declares it, with evidence. When the owner supplies an observed balance for a period without an opening, the opening is that balance minus the recorded movements up to that day, exactly as for a balance confirmed during statement import; the product states this derivation before confirmation.

A store that contains such a revision is not readable by releases before 0.2.0-rc.228, whose validator required every fact of a revising command to be a lineage replacement. There is no schema change and no migration.

### Evidence without a document (#417, #419)

A reconciliation carries one evidence fingerprint. For a document it is the SHA-256 of the file, formed by the product, never typed by the owner. Two further kinds have no file and derive the fingerprint from the reconciliation itself (Portfolio, Account, Cash Asset, date, observed balance and kind), so the kind can be recomputed from the stored fact without a new column:

- `owner_sighted`: the owner saw the balance at the institution; a second source, not a file;
- `owner_asserted_without_balance`: the owner declares completeness where no balance can be obtained. Nothing is checked. The recorded balance is the computed one, an absent opening is taken as zero, and the product shows such an Account as declared, unverified.

Any other fingerprint is a document or statement-import evidence.

### Manual batch (#419)

A small batch of regular manual commands is previewed on an in-memory copy and committed in one transaction through the same writer as a reviewed-import batch: the first booking on an Account without a period declares a `partial` period from that day, and an interest credit is a Cash event plus an Interest Income fact. Each command keeps its own attempt, receipt, facts and provenance; the owner confirms the batch once, and the commit is refused when the preview no longer matches. Flow classification is not inferred: a manual deposit or withdrawal is `unclassified`.

Attempt evidence and command provenance bind input mode, optional source-candidate fingerprint, exact payload, before/after state, predecessor set, and receipt. Manual and reviewed-import commands share the same handoff. Exact replay of a completed identical command is read-only; changed reuse is conflict. An ambiguous consumed attempt is never blindly retried: read-only reconciliation and a separate one-use Recovery Confirmation are required.

Reviewed imports may also be committed as one batch (`apply_desktop_cash_coverage_reviewed_batch_v1`, #184). The single-command handoff validates the complete ledger several times per command, so a long statement grew quadratically. A batch writes attempt, evidence, receipt, facts and provenance for every command as before, but validates lineage, semantics and provenance of the complete ledger once, after the last command of the batch; if that validation fails, nothing of the batch is committed. The owner confirms the batch once in the Data app, and each command's confirmation fingerprint binds the batch fingerprint, its request ref, the actor and that moment. Before and after state fingerprints of batch commands refer to the batch as a whole. A request ref that already has a receipt replays read-only; a changed payload under a known request ref is a conflict. Batches accept only regular create actions of input mode `reviewed_import`; corrections keep the single-command lifecycle.

The trusted Portfolio-CSV exchange reader may project all active current schema-2901 facts and reviewed-import provenance without becoming a writer. Its import side stages only fingerprint-bound Reviewed Candidates. A linked Interest Candidate is resolved server-side to exactly one active public `cash_event_####` ref after the corresponding event Candidate was committed. The exchange boundary never receives internal Cash IDs and never bypasses this command lifecycle.

## Migration and boundaries

The schema-2900→2901 migration validates exact source schema, owner/context binding, unchanged source fingerprint, catalog semantics, and source/target fact-projection parity. It reads the source immutably, creates a new target, consumes a migration-specific confirmation before publication, and records an immutable migration receipt. It never overwrites a target or invents historical local time.

The evaluator and persistent boundary create no canonical facts, external Accounts, Revenue/Expense Accounts, Cash from Income, Cash from Trades, Provider/network request, Tax calculation, alarm, automation, publication, or retry. Schema 201 and schema 401 remain unchanged. Browser models are label-only and exclude Context, paths, internal IDs, and fingerprints. Public tests use only invented data.
