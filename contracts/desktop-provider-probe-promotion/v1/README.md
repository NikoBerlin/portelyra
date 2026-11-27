# Desktop Provider Probe Promotion v1

This provider-free, owner-confirmed step promotes already persisted Yahoo probe evidence into the append-only schema-2300 Daily Market History store.

Since rc.394 (#495) the probe evidence may stem from any loaded price-provider plugin with `daily_history`; the evidence's provider must equal the mapping's provider (evidence before rc.394 carries none and counts as Yahoo).

It binds one immutable Listing from the exact current Provider mapping, owner-confirmed market code, provider-observed timezone and owner-confirmed calendar policy. Every requested date becomes `observed`, explicit `non_trading_day`, or `source_gap`. No second Provider request occurs.

Promotion writes Market History before Provider Mapping verification. If the later mapping command fails, the listing/history remains immutable but unverified and unavailable to valuation. Promotion does not itself enable a mapping.
