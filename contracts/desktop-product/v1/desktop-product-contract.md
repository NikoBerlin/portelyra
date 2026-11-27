# Desktop Product Runtime and Onboarding v1 Contract

## Product entry

The only supported v1 product entry is:

```text
Rscript --vanilla scripts/portelyra_desktop.R <command>
```

Commands are `preflight`, `install`, `initialize`, `upgrade`, `rollback`, `derivative-capability-preview`, `derivative-capability-apply`, `backup`, `backup-check`, `restore-preflight`, `restore`, `release-build`, `release-check`, `acceptance-check` and `start`. Release Operations are governed separately by Desktop Release v1. `start` binds fixed loopback `127.0.0.1`; browser input cannot provide host, port authority, home, project root, Tenant, User, Data Space, role or filesystem path. `PORTELYRA_DESKTOP_HOME` is an owner-controlled process environment resolved before app start; the default follows the Linux XDG data location.

## Preflight and installation

Preflight is read-only. It checks Linux, R, Python, SQLite/R packages, exact project sources, non-symlink home ancestry, separation from the repository, local package installation and Registry readiness. Marked current source inventories additionally prove their recursive controlled Python imports and R source edges from the exact snapshot. It returns only booleans and safe states, never paths or raw dependency output.

Installation requires exact local confirmation, performs no network access, installs tracked `spotcore` and `spotdisplay` plus the complete declared Product source set into one owner-enclosed integrity-bound release slot and atomically exposes a source-fingerprint manifest. A candidate is validated against its complete current source inventory and transitive local source closure; an installed older slot is validated against its own registry, exact complete inventory and stable boot baseline without executing older code. Normal source-inventory growth therefore yields `upgrade_required`, while missing, changed, extra, symlinked, permissive or closure-incomplete marked slot files remain conflicts. Upgrade still requires a strictly newer Product version and exact local confirmation. App start resolves that active package-and-source slot; v1 does not silently upgrade or repair a conflicting slot.

## Runtime registry

Initialization requires exact local confirmation and creates owner-only `0700` home/data directories and one `0600` Registry. Tenant, User and Data-Space IDs are cryptographically random opaque values and are never derived from label, path, e-mail or machine account. The only human value is a separate Data-Space display label. Registry loading is schema-strict and rejects symlinks, permissive modes, unknown fields and binding mismatches.

`runtime_mode=desktop_product`, `trusted_source=owner_only_desktop_registry` and role `desktop_owner` are fixed. `runtime_context_as()` cannot elevate this Context. Starting the app reads the Registry but creates no canonical store, Domain row, Artifact or Worker run. One owner-only PID/start-time lock excludes concurrent starts and Release Operations. A random process-memory launch token authorizes each Shiny server session; its value is neither persisted nor embedded in unauthenticated HTML.

## First-user data path and historical onboarding compatibility

The canonical store is initialized only after a separate explicit UI confirmation. A first user then creates Portfolio, Account and Asset masters through the normal Catalog Preview/one-use Confirmation path or strict Create-only Catalog CSV. New Non-Cash history is entered only through schema-401 Asset Activity; optional Cash facts are entered only through schema-2900 Cash Coverage. The Product UI offers no command that creates a new coupled schema-201 Transaction.

The pre-RC7 eight-command onboarding runtime and its schemas remain byte-compatible code for deterministic regression, Backup/Restore evidence and explicit historical-plan analysis. It is not exposed by the RC7 Product UI and cannot be started or resumed from browser input. Previously committed coupled facts retain their original semantics and remain available only through the separately labeled correction/void compatibility surface; they are never converted, split or reinterpreted automatically.

## Catalog and CSV additions

Data can create, correct and archive Portfolio, Account and Asset rows through separately previewed one-use Commands. The Canonical-English `desktop-catalog.csv` path is create-only, accepts only a browser upload selected by the owner and binds accounts through explicit existing Exchange refs or prior user-authored Portfolio row refs. Names never resolve identities. The exact plan is persisted before the first Command and a restart accepts only its exact completed prefix. Existing coupled Transactions remain correction/void-only; new Non-Cash events use schema-401 Asset Activity.

Optional Cash maintenance uses the separate owner-only schema-2900 Cash Coverage authority. The owner explicitly declares effective `not_tracked`, `income_only`, `partial` or `complete_reconciled` periods and appends Cash events, Interest or reconciliation evidence through Preview and one-use Confirmation. Confirmation is consumed before one write attempt. Income has no automatic Cash effect, Cash events have no automatic GuV effect and absent Cash is never zero. Schema 201 and schema 401 remain unchanged. The completed browser model contains labels and exact results only, without paths, Context, internal IDs/refs or fingerprints.

## Generic Derivative capability

An integrity-valid RC16 slot exposes a read-only `derivative-capability-preview` and
a separate `derivative-capability-apply` requiring the exact one-use confirmation.
Apply is unavailable while a Desktop session is active. It migrates only an intact
native schema-201 Catalog to schema 202, preserves all existing Domain values and
publishes owner-only Attempt/Receipt evidence. Release Upgrade never invokes it.
Derivative Catalog creation and every Asset Activity apply remain later normal
write boundaries. Coupled Derivative Transactions, lifecycle inference, automatic
Cash, Provider, FX and Tax remain unavailable.

## Targeted Activity recovery

An integrity-valid RC17 slot retains every RC16 Product and Derivative boundary.
When a locked Asset Activity Apply checks for a completed generation published
before activation, only manifests with the exact expected Plan/command fingerprint
can authorize full historical-ledger validation. Matching candidates retain all
hash, Context, canonical, schema, receipt, Activity-set and event-count checks;
multiple matches remain a conflict. This introduces no mutable index, generation
cleanup, Draft batching, Product schema change or automatic retry.

## Staged Daily Market History Review

ADR-157 adds a Product boundary without reusing the compatibility Fetch v1 operation. Planning is read-only and checks the current verified canonical Mapping plus its latest native audit fingerprint through an immutable query-only handle; the confirmed Fetch repeats that check before transport. The owner selects one contiguous Plan range, confirms one bounded external fetch and receives a sealed owner-local Candidate; this first operation cannot write schema 2300. The browser receives only exact Decimal rows, worker integer coordinates, warnings and public refs. A fresh second confirmation publishes the exact Candidate through `market_worker` without refetch, or a separate confirmation rejects it without a Market write. Current-history drift blocks as stale. A consumed uncertain effect is reconciled against the exact Stage or request receipt before any further attempt. Terminal Fetch failure additionally requires one create-only recovery Attempt and its bound reconciliation before a new Plan. An ordinary repeated publish never performs that recovery, and persisted publication evidence must match its Attempt, Candidate and receipt.

Only `weekday_exchange` and `continuous_24_7` have explicit Review v1 mappings. Other Daily Calendar codes and Market codes outside the narrower public Review shape fail before fetch. Calendar carry-forward remains derived effective-Close provenance and cannot become an observed source bar, Activity, Reward, FIFO, Tax or FX fact.

## Synthetic Statement review

ADR-161 adds one read-only Data card over the six ADR-158 adapters. The fixed CLI accepts exactly a registered adapter ID and `valid` or `adversarial`; it accepts no path or uploaded source bytes. Adapter output exists only in an owner-only ephemeral directory, is independently revalidated for a complete Candidate-or-Diagnostic row ledger, and is removed before the response returns. The browser sees exact invented row values and grouped mapping requirements but no path, Runtime Context, canonical ID or fingerprint. There is no private UAT, mapping save/apply, effect Preview, Confirmation, ActivityDraft/schema-401/Cash write or activation operation.

## Separation

The existing Desktop Demo remains fixed synthetic evidence and cannot become product authority. The Product root must be outside the repository. Product start does not inspect Demo or private roots. Cockpit, Tax and Analysis remain completed-publication readers; Data alone owns Catalog/Transaction Commands and explicitly confirmed Worker starts. Whole-Product Backup/Restore, Upgrade/Rollback, release packaging and private Acceptance follow the separate Desktop Release v1 contract.

Automatic Provider, DNS, HTTP client, socket client, retry or fallback activity is zero. The Product code contains narrow owner-confirmed search, probe and staged history request boundaries, but no repository test or release action invokes a real external service. Mail, alarm, cron, Server/OIDC, deployment and private/Legacy access remain zero.
