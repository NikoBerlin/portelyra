# Market History Review v1

ADR-156 adds a staged visual acceptance boundary after a bounded Provider fetch and before append-only Daily Market History publication.

Since rc.394 (#495) any loaded price-provider plugin with the operation `daily_history` qualifies (Yahoo, EODHD ...). The provider comes from the mapping; the request is fetched through the shared core path (`plugin_credentials_v1.provider_get_v1`: credentials only to confirmed hosts, costs counted). New failure codes: `*_credential_unavailable`, `*_cost_limit`. For Yahoo nothing changes. Results stored before rc.394 carry no `provider_id`; they stem from Yahoo.

The additive flow is:

`plan without external data retrieval → one-use fetch confirmation → one staged Candidate → machine validation → graphical/exact review → one-use publish confirmation → schema-2300 append`

Fetch confirmation cannot publish. Publish confirmation cannot refetch. A rejected or stale Review writes no Market history and causes no automatic retry.

For exchange calendars, omitted calendar-confirmed weekends and holidays are normal `non_trading_day` evidence. Provider-manifest-declared null/dropout encodings normalize only on such closed dates, remain warning-level and never create an observed zero price. A derived valuation/plot series may carry the latest preceding eligible unadjusted Close forward with explicit `imputed_non_trading_day` provenance. Source OHLCV remains null on that date. Expected-session gaps and 24/7 weekend gaps are never automatically imputed.

ADR-156 supplied the pure synthetic core. ADR-157 now adds owner-local sealed staging, a JSON-stdin CLI, an R service, exact table/plot presentation and Asset Center integration. Preview and confirmed Fetch validate the current canonical Mapping and its native audit fingerprint through an immutable query-only handle. Synthetic acceptance injects invented provider bytes and proves that staging leaves schema 2300 unchanged, publish does not refetch, stale/rejected candidates do not write, terminal fetch failure requires a one-use explicit recovery reconciliation, and uncertain publication reconciles its exact receipt.

Product v1 maps only `weekday_exchange` and `continuous_24_7`; `bank_business_day`, `custom_reviewed` and public-incompatible Market codes fail before fetch. No contract test performs real external access or productive publication, and this repository tranche grants neither permission.
