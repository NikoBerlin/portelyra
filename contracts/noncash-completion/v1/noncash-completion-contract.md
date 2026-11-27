# Non-Cash Completion v1 Contract

## Claims

The contract publishes four different facts and never collapses them into one boolean:

1. `noncash_fact_scope_complete` requires a valid terminal closure receipt, active schema-401 facts and fresh exact FIFO-v2 Full-rebuild parity.
2. `noncash_enrichment_capability_ready` requires prepared manual Provider/Listing, staged Market review, explicit FX, Tax policy, importer protocol and incremental invalidation boundaries.
3. `noncash_analysis_data_ready` additionally requires compatible completed Market, required FX, applicable Tax, valuation and analysis artifacts for the selected Non-Cash scope.
4. Concrete statement-adapter coverage is independent. `synthetic_validated_disabled` means executable public-fixture coverage only; it must never be presented as private owner acceptance, activation or real-source coverage.

Cash is always outside v1. `complete_portfolio_claim_authorized` is therefore always false.

## Factual closure receipt

A future separately authorized owner-local operation may publish one additive receipt only after an identity-stable read-only Legacy freeze and delta comparison. Every frozen Non-Cash lineage is either canonical or explicitly terminally excluded under the closed `terminal-dispositions.csv` policy, and unresolved count is zero. Quarantine, missing Activity and unsupported semantics are not closure-eligible. The receipt binds the disposition-policy bytes plus source-freeze, delta, actual terminal disposition, active Activity and exact FIFO Full-rebuild fingerprints. It asserts unchanged Source bytes and writes no canonical fact.

The repository contract contains no private source selector, path, value, Product Context or execution command. Defining the receipt does not authorize creating it.

## Disabled Importer adapters

`importer-slots.csv` is a closed executable-but-disabled capability inventory. It contains six explicit profile families: Trade, Distribution, generic Reward, Staking Reward, Airdrop and Movement. Staking and Airdrop remain separate source-profile slots even though their v1 output is only a Reward-shaped untrusted candidate; this grants no valuation, basis, legal or Tax classification.

Each adapter:

- implements exactly one immutable manifest/profile version and fingerprint-bound entry point;
- reads one server-bound regular source only inside the isolated Statement Import Protocol;
- emits one candidate or registered diagnostic for every stable source row;
- writes only untrusted Candidate output for later ActivityDraft review;
- receives no Provider, network, SQL, Context, target, Cash or canonical capability;
- has passed public invented/malformed/adversarial tests but still requires one owner-local private manual UAT;
- remains `default_activation=disabled` and returns to `implemented_disabled` whenever parser or executable bytes change.

A Reward candidate may preserve source quantity, event time and explicitly supplied evidence. It cannot infer valuation, basis, Cash, Provider price, Tax class or legal treatment. Missing mandatory Reward evidence remains `needs_input` and cannot be silently dropped.

## Persistent dependency boundary

Activity invalidates affected `Portfolio × Asset` FIFO and downstream Tax/valuation. Market/FX corrections invalidate affected valuation points. Tax-policy changes invalidate Tax and dependent valuation. Grouping changes only group/analysis projections. The last completed artifact remains visibly stale after failed successors; Full replay remains the equality oracle.

The read model is path-, Context-, internal-ID- and fingerprint-free. It performs no source read, calculation, Provider access, network request or write.
