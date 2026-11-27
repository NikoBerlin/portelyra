# Desktop Product Asset Activity read model v3

V3 is the identity-bearing browser-safe successor to the frozen label-only v2 read model.

- Every FIFO position, custody position and Activity event carries the same ephemeral `activity_asset_*` reference as the current Activity catalog.
- Canonical Asset IDs are resolved only inside the trusted Python boundary and are never returned.
- Labels remain presentation and may repeat. Filtering and handoff use browser refs, not names.
- A canonical/catalog change, unknown identity, type mismatch or non-bijective ref blocks the read.
- The reader consumes only an already completed schema-3100 FIFO-v2 state. It starts no calculation, Provider or network operation and writes no Product data.
- Coupled schema-400 Transactions, Cash, Tax, Market/FX and valuation remain separate.

The v2 schema and reader remain unchanged as a frozen compatibility interface. RC25's temporary label bridge is not used by the Product surface after this contract.
