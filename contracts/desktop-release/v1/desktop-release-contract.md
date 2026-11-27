# Portelyra Desktop Release and Local Safety Contract v1

## Authority and quiescence

Only the local launcher may request Backup, Restore, Upgrade, Rollback, Release Build or private acceptance. Owner-controlled absolute paths are CLI input only; Browser input never supplies a path. Backup, Restore, Upgrade, Rollback and private Acceptance require the same owner-only `desktop-session.lock` used by `start`, so an active four-app session, Worker or concurrent Product-home operation blocks. Source-only Release Build/Check have no Product-home capability. A cryptographically random launch token exists only in process memory and must bind every Shiny session; navigation propagates it client-side without embedding its value in unauthenticated HTML.

## Backup scope

A confirmed Backup copies exactly:

1. the strict owner-only Desktop Runtime Registry;
2. the one bound active Data-Space tree, including the canonical SQLite Store, Data-/Tax-/Policy state present in that tree, onboarding and CSV-import Plans/Receipts, immutable Jobs/checkpoints and completed Composite Artifacts.

Installed package libraries, release archives, rollback slots, operation locks, temporary/incoming paths, Legacy/private sources and external files are excluded. The source is read-only. Every source directory/file must be non-symlink and owner-only. Every SQLite file passes read-only integrity checking; known `store_binding`, `ledger_store_binding`, `cash_coverage_binding` and `realized_state_binding` rows must match the Registry Context. Asset Activity, Cash Coverage, schema-3100 Realized State and ActivityDraft use recognized empty owner-only regular writer-lock files as persistent advisory-lock inodes: Backup acquires each such lock nonblocking and holds it through both source inventories, excludes the lock file itself, and blocks if another writer holds it. ADR-144's permanent ActivityDraft `.writer.lock` **directory** is not operational lock state: Backup strictly validates and includes the directory with its immutable base marker and optional additive ADR-145 marker while excluding/holding the aware `.writer-v2.lock` inode. Any other lock, malformed barrier or persistent lock, WAL, SHM, temporary or incoming state blocks.

Backup writes into a command-owned sibling staging directory, writes payload bytes first, canonical `backup-manifest.json` next and canonical `SUCCESS` last, fsyncs, then publishes with a no-replace rename. Manifest entries bind relative path, type, mode, byte count and SHA-256. The source inventory is re-read before publication. Exact replay validates the existing immutable bundle and writes nothing. An interrupted command may remove and rebuild only its own marker-bound staging after a new explicit confirmation; it never removes source data or a completed bundle.

## Restore

Restore Preflight is read-only for Product and target roots. It completely revalidates Manifest, SUCCESS, all files, modes, SQLite integrity, Registry and Context. The target must be a separate non-overlapping absent or explicitly empty owner-only Product home. A nonempty target is never overwritten. A target Registry with another Tenant/User/Data-Space fails as a Cross-Data-Space attempt.

Confirmed Restore repeats Preflight, copies to a sibling staging root, revalidates the exact tree and atomically publishes it. Restored Runtime Registry and Data Space are byte-identical to the Backup payload. Release code is deliberately not restored: the supported current release must be installed separately before start. Recovery after publication but before internal finalization recognizes the exact restored tree and performs no duplicate write.

## Upgrade and rollback

Installation manifests bind Product version, exact tracked-source fingerprint, the two local R packages and an owner-only complete source snapshot. Candidate validation requires the complete current install inventory. An already installed active or rollback slot is independently validated against its own integrity-bound registry, exact snapshot inventory and stable boot baseline; candidate code never executes code from the older slot. Preflight reports `upgrade_required` rather than applying the candidate's expanded inventory to an intact older slot. Corrupt, missing, changed, extra, symlinked or permissive slot files still fail closed. Confirmed Upgrade requires a strictly newer Product version, installs the entire release slot into owner-only staging while the active slot remains usable, records a strict journal, moves the old complete slot into one rollback location and activates the complete new slot. Confirmed replay resumes only the exact journal state. Rollback swaps the two complete package-and-source slots under the same exclusion lock. If the active Data Space contains ADR-144's permanent writer barrier, Rollback first proves that the target slot declares the supersession generation and barrier capability. If the additive ADR-145 marker is present, the target must additionally declare mixed-source retirement support; RC18 then fails with `desktop_product_rollback_incompatible` before a Rollback journal or slot move. App start always resolves the active slot, including while a newer candidate reports `upgrade_required`. Canonical, Receipt, ActivityDraft, Cash, Job and Artifact trees are never moved or opened for write by Upgrade/Rollback. v1 intentionally retains one local rollback slot and performs no automatic retention deletion.

## Reproducible release

Release Build accepts only the exact Desktop Product source registry plus `AGENTS.md`, `VERSION` and that registry itself. Before its first target write it parses every registered Python source under `apps`, `migrations`, `workers` and `scripts`, follows the complete controlled local import graph and resolves registered R `source()` edges. Missing direct/transitive modules, absent statically resolved R targets or invalid source syntax block with `desktop_release_transitive_source_closure_invalid`. Historical adapters excluded from the Product registry cannot become implicit runtime dependencies.

It creates a deterministic gzip/PAX archive with normalized owner/group, modes and timestamps and an internal canonical `release-manifest.json`. Two builds from the same tree are byte-identical. Archive validation repeats closure validation over the archived bytes; manifest consistency alone is not sufficient. New marked Product snapshots repeat the gate before installation, Upgrade or Start. No Git metadata, test fixture, runtime/private file, backup, log, cache, Server deployment configuration or downloaded dependency is included. Installation remains tracked-source and network-free.

## Private acceptance

The user alone selects and enters real values locally. The local acceptance checker may inspect the bound private Product homes and Backup, but its complete public result is exactly:

```json
{"status":"pass"}
```

or:

```json
{"status":"fail","code":"registered_redacted_code"}
```

No path, Context value, identifier, label, row, amount, quantity, count, fingerprint or raw log is allowed in feedback. Passing is a product workflow result, not tax or legal advice.

## Explicit exclusions

There is no Cloud backup, encryption claim, destructive overwrite, automatic delete, Provider/network fallback, Server/OIDC activation, deployment, mail, Alarm, Cron or Branch deletion capability.
