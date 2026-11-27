# Asset Selection Context v1

This contract defines a browser-local, provider-free presentation scope over already completed/readable Asset models.

The first product slice supports manual multi-selection and explicit `selected`/`all` modes for the Data Activity read tables. ADR-150 binds v3 rows to the same browser-local Asset refs as the catalog, so duplicate presentation labels remain independently selectable. Asset-Center handoff initializes one selected Asset and one independent single Activity command target through server-owned identity maps. Selection never authorizes a batch command or any Product write.

Advanced filters documented in issue #228 remain additive. Missing capabilities are unavailable rather than approximated.
