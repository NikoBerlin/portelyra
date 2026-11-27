# Desktop Provider Probe Promotion Contract v1

## Preview

Read and verify one persisted probe result, current mapping revision/fingerprint and Product Catalog fingerprint. Require exact Provider symbol/currency and provider-observed timezone. The owner supplies market code and calendar policy. Build the immutable Listing and complete Daily History Candidate entirely in memory.

## Apply

After a separate confirmation, persist a create-only promotion attempt, bootstrap the context-bound Daily History store if absent, bind the Listing and append the candidate. There is no Provider or network access. Existing observations remain append-only.

Weekends become `non_trading_day` only under `weekday_exchange`. Other absent requested dates remain `source_gap`; holidays are not guessed. Split evidence remains `pending_review` and blocks valuation but may be stored.

Promotion does not update Provider Mapping, Canonical Catalog, Tax, FX or Activity. A second owner-confirmed mapping command consumes the probe evidence fingerprint and enables an ordinary Provider mapping. The two writes are intentionally not a distributed transaction.
