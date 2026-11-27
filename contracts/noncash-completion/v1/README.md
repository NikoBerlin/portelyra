# Non-Cash Completion v1

ADR-155 defines a domain-scoped completion model that lets factual Non-Cash closure, enrichment capability, actual analysis-data readiness and concrete Importer coverage remain independent.

This repository-local tranche defines `dimensions.csv` as the **Non-Cash Completion Matrix v1** and provides:

- an additive owner-local factual closure-receipt shape and closed terminal-disposition policy for a later separately authorized Legacy freeze/delta run;
- a browser-safe dimensional completion read model;
- six versioned concrete source-profile adapters, explicitly including generic Reward, Staking Reward and Airdrop profiles;
- an explicit bridge into the closed-row Statement Import Protocol rather than the older `csv_exchange_v1` pilot;
- a mandatory per-adapter lifecycle ending in separate private owner UAT and explicit activation;
- invented valid, malformed and adversarial fixtures plus focused sandbox tests.

All six adapters are `synthetic_validated_disabled`: they have fingerprint-bound executable entry points and may read only an explicitly bound source inside the sandbox, but the normal runner remains blocked. They have no Provider, network, SQL, schema-401, schema-2900, Cash or Tax write capability. Public synthetic validation is not private owner acceptance and does not authorize activation.

Non-Cash completion never includes Cash and never authorizes a complete-Portfolio claim. Display reads completed artifacts and starts no Importer, Provider, FIFO, Tax, valuation or write operation.
