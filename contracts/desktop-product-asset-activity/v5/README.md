# Desktop Product Asset Activity read model v5

V5 is the additive interval-evidence successor to the frozen Account-identity v4 read model.

- Asset and Account identity remains browser-local through the same ephemeral `activity_asset_*` and `activity_account_*` refs.
- Every Activity event carries nullable `fifo_event_sequence`, `asset_quantity_before_decimal` and `asset_quantity_after_decimal` fields.
- Those three fields are populated only from an already completed, fresh FIFO-v2 generation; stale, failed, pending or absent FIFO evidence publishes all three as null.
- A fresh view binds event type, source Account, related Account and Asset back to the schema-401 event before publishing FIFO state.
- World-local event sequences and quantity continuity let a read-only consumer derive opening and closing holding state without reordering, recalculating or inventing events.
- Canonical IDs, paths and fingerprints remain inside the trusted Python boundary. Labels remain presentation and may repeat.
- The consumer domain remains explicitly `noncash`.
- The reader starts no calculation, rebuild, Provider or network operation and writes no Product data.

The v2, v3 and v4 readers remain unchanged compatibility interfaces. V5 is the first Activity model suitable for inclusive holding-interval predicates in Asset Selection Context v3.
