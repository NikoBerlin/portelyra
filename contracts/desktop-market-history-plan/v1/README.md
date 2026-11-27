# Desktop Market History Plan v1

Provider-free planning over one promoted schema-2300 Listing:

- `incremental` targets only `not_requested` dates;
- `retry_source_gaps` targets only persisted `source_gap` dates;
- `full_refresh` targets all persisted dates for explicit comparison.

The planner coalesces contiguous ranges, exposes no Listing, Context, path or fingerprint, and performs no write or Provider access. Execution remains a separate confirmed worker operation.

Planned dates end at the latest completed day (`completed_through`, #475). Since rc.368 (#516) the owner setting `market_day_completion` (user-settings-v1) decides when: `session_close` (default) completes exchange Listings one hour after their known session close (`SESSION_CLOSES` in `market_day_completion_v1.py`, by `market_code`; the latest regular close, e.g. XETRA 17:35, Frankfurt and Stuttgart 22:00, New York 16:00 local), `calendar_day_end` completes every Listing one hour after the calendar day ends in its time zone. Crypto, FX and unknown market codes always use the calendar day end. Callers still cap the requested end at yesterday (local date), and a foreign-currency Listing ends at the last completed day of its FX pair; the setting therefore takes effect for runs after midnight. The result reports `completion_mode`; a value retrieved before completion stays provisional and is requested again. A running day would otherwise be stored as the day's value and then count as present. The result reports the effective `as_of_date` next to `requested_as_of_date`; callers end fetch, calendar binding and valuation there. The FX history plan applies the same rule with the pair's time zone (`end_date`, `requested_end_date`).

`incremental` also targets observed or gap days that were retrieved before their day was complete and that no later request confirmed (`provisional_day_count`). The latest confirming request comes from the request-day evidence, so an unchanged re-fetch ends the re-planning.
