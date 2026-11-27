# Desktop Market History Fetch v1

Owner-confirmed Yahoo execution over one exact read-only plan:

Since rc.394 (#495) any loaded price-provider plugin with the operation `daily_history` qualifies (Yahoo, EODHD ...). The provider comes from the mapping; the request is fetched through the shared core path (`plugin_credentials_v1.provider_get_v1`: credentials only to confirmed hosts, costs counted). New failure codes: `*_credential_unavailable`, `*_cost_limit`. For Yahoo nothing changes. Results stored before rc.394 carry no `provider_id`; they stem from Yahoo.

- `incremental` requests only contiguous `not_requested` ranges;
- `retry_source_gaps` requests only explicitly selected gaps;
- `full_refresh` requests the whole confirmed range.

Incremental never requests a covered date. Retry/full results pass through the accepted CAS comparator and become immutable `unchanged` or reasoned correction revisions; they never overwrite history.

Apply persists an attempt before network access, performs one strict request per displayed range, normalizes complete date coverage, and appends schema-2300 evidence. The batch is not globally transactional: successful earlier ranges remain authoritative if a later range fails. A consumed incomplete attempt cannot automatically retry and requires explicit recovery.
