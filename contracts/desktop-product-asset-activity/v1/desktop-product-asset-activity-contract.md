# Desktop Product Asset Activity v1 Contract

## Authority split

`canonical.sqlite` at exact schema 201 or its owner-confirmed native schema-202
successor remains Product authority for Portfolio, Account, Asset and coupled
Transaction facts. It is opened read-only, schema-/seal-/
audit-validated and must remain byte-identical. The Data-owned sidecar owns only
append-only `asset_activity_v1` events and their immutable receipts.

Each sidecar generation is a fresh schema-401 ledger. The schema-201/202 catalog and
current coupled Transactions are regenerated as derived read-only facts. Existing sidecar
Asset Activity receipts/events are copied without semantic rewriting. The accepted
schema-400 Transaction contract and the ADR-100 Asset Activity contract remain
separate in `compatible_ledger_event`.

`canonical_write=true` in a fresh Product result means that the Data command wrote
new Asset Activity authority into the fresh sidecar generation. It never means that
schema-201 `canonical.sqlite` was written. Replay and crash recovery report
`canonical_write=false` because they append no new authority.

## Trusted caller

Paths, Context, Portfolio/Asset/Account IDs, source projection, Plan fingerprint and
target capability are resolved server-side. The browser may later submit only
session-bound review references and visible confirmation. It cannot supply paths,
Context, canonical IDs, fingerprints, SQL or command authority.

Preview is write-free: it materializes an owner-only temporary generation, verifies the exact target and removes temporary state. Legacy cutover recomputes Projection + Review + full Plan/FIFO evidence. Native commands validate exactly one server-resolved Asset Activity event and run the complete semantic FIFO oracle against the current active generation plus that candidate; insufficient inventory, missing required basis or ambiguous ordering blocks before confirmation. The exact Preview fingerprint is required by Apply. Existing exact receipts return replay evidence.

The native browser form submits only session references and visible facts. A local Date object and separate `HH:MM:SS` plus IANA zone are resolved server-side to one unique UTC instant. Nonexistent or ambiguous DST instants block. A browser-supplied UTC value is at most comparison evidence and must equal the server result; it cannot establish time authority. After exact Preview/FIFO validation, a native command persists one owner-only immutable Attempt before writing the event or publishing a generation; a crash leaves that exact authority for safe same-plan recovery. Native Buy/Sell never accepts or requires a Cash Account and writes exactly zero Cash postings. The public Preview includes the candidate event's completed FIFO result—consumed basis, exact signed proceeds (including a fee-driven negative result), realized gross result, Income and zero Cash delta—plus FIFO-derived Cost Average; it omits event/account/asset refs. The former coupled Transaction surface is correction/void-only and cannot create new coupled facts.

## Exact schema-201/202 projection

Only exact schema 201 or 202, Context binding, SQLite integrity, immutable seal
content and matching transaction audit fingerprints are accepted. Schema 202 adds
Derivative Catalog identity while its coupled-Transaction trigger remains closed;
generic Derivative facts enter only through Asset Activity. Every posting must be
represented by an explicit supported profile. Unknown roles, Tax/Other postings,
incomplete counterparties, mismatched signs/amounts/assets/accounts, unsupported
Cash semantics or an execution-price mismatch block with
`desktop_asset_activity_projection_unsupported` or canonical-invalid evidence.

Buy/Sell price comes only from the exact Non-Cash Asset posting. Cash price `1` is
allowed only for a catalog-proved `cash` Asset with `valuation_method=unit_value`.
No Cash, price, FX, Account, entity or route is inferred.

## Generation lifecycle

Owner-only layout:

```text
asset-activity-ledger-v1/
  writer.lock
  active.json
  generations/
    gen_<fingerprint>/
      portfolio-ledger-v401.sqlite
      generation-manifest.json
      SUCCESS
```

Apply holds one non-blocking process-shared `flock` across recovery, build and
activation. It also uses the established canonical Product `canonical.writer.lock`
directory as a read barrier while taking the initial source snapshot and while
performing the final fingerprint check plus `active.json` replacement. A canonical
writer therefore cannot start in the final check/activation gap.

The ledger, manifest and `SUCCESS` marker are `0600`; generation directories are
`0700`. Ledger and manifest fingerprints determine the immutable generation ref.
The generation directory is renamed and fsynced before activation. `active.json` is
written to a `0600` temporary file, fsynced and atomically replaced.

Incomplete `.staging-*` directories are never readable authority and are removed by
the next locked Apply. A completed generation published before an activation crash
is detected by exact Context, canonical, Plan, receipt, ledger and manifest evidence;
the next Apply activates it as `recovered_committed` without appending again.
Recovery discovery first validates each owner-only generation directory and parses
its immutable manifest, then opens and hashes complete ledgers only when the manifest
has the exact expected Plan/command fingerprint. Nonmatching history is not recovery
authority for the current command. Every matching ledger retains all existing
Context, canonical, receipt, hash, schema, Activity-set and event-count checks.
Multiple matching generations, tampering or malformed candidate state fail closed.

## Read and semantic boundary

The active reader validates `active.json`, `SUCCESS`, manifest and ledger hashes,
Context, schema 401, SQLite integrity, Activity-set fingerprint and event count. It
returns no state and creates nothing when the Product area is absent.

Completed FIFO/Portfolio/Tax/Analysis readers must retain `semantic_contract`, `coupled_transaction_fact` and automatic-Cash state. The Data read model reads the same completed FIFO authority over the immutable active generation. Frozen v2 exposes label-only newest-first history; v3 additionally binds every history, position and custody row to the current catalog's ephemeral browser Asset ref so repeated labels stay distinct. It exposes no path, Context, canonical ID or fingerprint and performs no write. Old coupled facts have unknown automatic-Cash state; Asset Activity proves zero. Flattening the two sources or synthesizing Cash is forbidden.

## Exclusions

No private Product Home or Legacy Trade source is accessed by public tests. Provider,
network, FX fallback, Tax inference, Worker start, deployment, Server/OIDC, alarms,
cron, mail and destructive branch or generation cleanup are outside this contract.
A genuine private Legacy cutover needs separate explicit authorization. Native Product entry remains owner-confirmed local Data authority and does not authorize private Legacy reads.
