# Asset Selection Context v2

V2 adds explicit filter algebra and identity-bearing Non-Cash Account facets to the frozen RC26 `selected`/`all` v1 slice.

The Data Activity consumer uses read model v4 and supports:

- `all`, manual-only, filter-only, union and intersection scopes;
- an explicit Asset exclusion set applied last;
- canonical Asset domain selection without inferring Cash from Account names or types;
- Account match `any`, `all` or `none`;
- current positive Custody or historical effective Activity usage as separate predicates;
- duplicate Account labels through ephemeral `activity_account_*` refs;
- a single independent Activity command target.

The Activity consumer declares only `noncash`. A Cash predicate is `unavailable`, never an empty truth, until a compatible completed Cash read model exists. Current Account filtering is unavailable when FIFO/Custody evidence is not fresh; historical usage can still read effective Activity facts. No filter starts a rebuild, Worker, Provider or Product write.
