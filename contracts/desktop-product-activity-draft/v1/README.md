# Desktop Product ActivityDraft v1

ADR-136 defines one owner-local persistent preparation model for manual Asset Activity, tolerant CSV rows and immutable corrections. ADR-137 adds explicit multi-key Registry mapping, sequential ready-row revalidation and owner-local Draft repair. ADR-138 adds the explicit Recovery Inbox, exact-source Draft deduplication, guided unclassified-fee resolution and Context-bound mapping profiles for the registry-derived standard owner. ADR-144 adds immutable whole-source supersession for obsolete open tolerant-CSV Draft generations. ADR-145 adds explicit mixed-state source retirement that preserves committed Draft evidence and tombstones only the complete open partition.

Normative files:

- `desktop-activity-draft-contract.md`
- `capability-matrix.csv`
- `state-machine.csv`
- `failure-codes.csv`
- `draft.schema.json`
- `public-draft.schema.json`
- `mapping-profile.schema.json`
- `public-mapping-profile.schema.json`
- `confirmation.schema.json`
- `attempt.schema.json`
- `receipt.schema.json`
- `source-supersession-*.schema.json`
- `mixed-source-retirement-*.schema.json`
- `source-fingerprints.csv`

The Product UI maps owner-visible Portfolio, Account, related-Account, Asset and source-Asset keys only through ephemeral Registry references; it never infers or creates identity. Trusted mapping profiles persist only under the same Context/Data-Space boundary and resolve their canonical targets back to fresh browser-local references before use. Exact tolerant source rows reuse one source-bound Draft, and unresolved source fees remain non-writable until the owner assigns their exact semantic role. `applying` Drafts expose only an explicit resume action over the existing Attempt. Open Draft fields can be repaired under optimistic revision and must pass the shared validator again. The shared validator delegates complete drafts to existing native-create or immutable-correction previews. The trusted Python/R bridge routes the current manual Product adapter, correction adapter and tolerant-CSV draft service through this boundary. The apply boundary consumes a durable ActivityDraft Attempt and delegates the write to those same schema-401 writers.

An exact-source replacement is a separate trusted owner operation. It consumes one durable batch Attempt, publishes an immutable cumulative tombstone generation and switches one active pointer without rewriting any Draft. Effective read/list state becomes `superseded`, and all supported Draft writers reject that source. Mixed-state retirement binds the full source set and keeps committed Drafts byte-exact while tombstoning only open Drafts; its immutable Attempt remains mandatory generation evidence. A permanent `.writer.lock` directory is an intentional release-awareness barrier, not a stale lock; capable writers use `.writer-v2.lock`, and the additive ADR-145 marker blocks an RC18 rollback after activation. Retirement itself never creates replacement Drafts or writes schema 201/401, Cash, Provider or network state. It never rounds Decimal facts or exposes owner paths and internal references to the browser.
