# Desktop Provider Probe v1

A confirmed one-attempt Yahoo Daily probe tests one saved, unverified `daily_history` mapping over at most 32 calendar days.

Since rc.394 (#495) any loaded price-provider plugin with the operation `daily_history` qualifies (Yahoo, EODHD ...). The provider comes from the mapping; the request is fetched through the shared core path (`plugin_credentials_v1.provider_get_v1`: credentials only to confirmed hosts, costs counted). New failure codes: `*_credential_unavailable`, `*_cost_limit`. For Yahoo nothing changes. Results stored before rc.394 carry no `provider_id`; they stem from Yahoo.

The normalized result is persisted owner-locally before any mapping verification or canonical Daily Market History write. It records exact returned OHLCV/Adjusted-Close text, observed currency, exchange, timezone and split-review status, but no raw response. Exact completed replay performs no second request. Incomplete attempts cannot retry automatically.

The probe itself cannot enable a mapping or feed valuation. A later owner-confirmed promotion binds Listing/calendar policy, appends the already fetched evidence to schema 2300 and only then permits mapping verification.
