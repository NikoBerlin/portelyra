# Desktop Product Asset Quantity Scale v1

ADR-135 defines an owner-visible quantity-scale increase when a finer exact Activity quantity exceeds the current Asset scale.

The Product previews exact Decimal evidence, displays the old and proposed scale plus the required FIFO rebuild, consumes a durable Attempt, delegates the Catalog mutation to `catalog_rescale_asset_v1`, republishes an immutable schema-401 generation and leaves Realized Materialization visibly stale until the affected-world rebuild completes.

Normative files:

- `desktop-asset-quantity-scale-contract.md`
- `capability-matrix.csv`
- `state-machine.csv`
- `failure-codes.csv`
- `public-preview.schema.json`
- `confirmation.schema.json`
- `attempt.schema.json`
- `receipt.schema.json`
- `source-fingerprints.csv`

The ordinary browser receives no Context, canonical IDs, paths, command tokens or fingerprints. Scale decrease, Cash, Provider/network, Tax mutation and automatic retry are excluded.
