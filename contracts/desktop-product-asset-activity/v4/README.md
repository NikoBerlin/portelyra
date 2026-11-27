# Desktop Product Asset Activity read model v4

V4 is the browser-safe Account-identity successor to the frozen Asset-identity v3 read model.

- Every FIFO position, custody position and Activity event retains its ephemeral `activity_asset_*` reference.
- Every custody row and Activity event additionally carries the same ephemeral `activity_account_*` reference as the current Activity catalog. Transfer destinations carry a nullable related Account ref.
- Canonical Asset and Account IDs remain inside the trusted Python boundary and are never returned.
- Asset and Account labels remain presentation and may repeat. Filtering uses refs exclusively.
- The consumer domain is explicitly `noncash`. Cash is not projected as empty or zero; it requires a separate compatible Cash read model.
- A Canonical/catalog change, unknown identity, portfolio mismatch or non-bijective ref blocks the read.
- The reader consumes only an already completed schema-3100 FIFO-v2 state. It starts no calculation, Provider or network operation and writes no Product data.

The v2 and v3 readers remain unchanged compatibility interfaces. V4 is the first Activity model suitable for Account facets in Asset Selection Context v2.
