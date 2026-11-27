# Desktop Product Asset Activity view and Preview v2

ADR-130 moves the M7 Data surface from the retained FIFO-v1 compatibility projector
to the protected FIFO-v2 authority.

- Native Preview evaluates the complete affected `Portfolio × Asset` world with
  custody at `Portfolio × Account × Asset`.
- Exact ratios remain ratios; no Float or implicit rounding is introduced.
- The browser read model joins labels and facts only to an already completed, fresh
  schema-3100 artifact. Display performs no materialization, retry or Full rebuild.
- If schema-3100 is absent or stale, Events remain visible but calculated positions,
  consumed basis and realized result stay unavailable.
- Coupled schema-400 Transaction facts are excluded from Asset Activity FIFO and
  remain on their separate correction/history surface.
- Cash, Provider/network, Tax inference, canonical writes and complete-portfolio
  claims remain outside this reader.

The old FIFO-v1 read model and v1 Preview contract remain available only as frozen
compatibility interfaces; they no longer back the M7 Data command surface.

ADR-131 separates immutable generation-writer evidence from reader authority. The
manifest writer Context must reconstruct from an actor recorded in the ledger, while
the current trusted reader may use another `desktop_owner` actor in the same exact
Tenant/User/Data-Space. Schema-401 scope binding remains mandatory.
