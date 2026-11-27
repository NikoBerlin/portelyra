# Asset Selection Context v3

V3 adds inclusive Activity and holding intervals to the frozen v2 Asset/Account selection algebra.

The Data Activity consumer uses read model v5 and supports:

- optional `Von` / `Bis einschließlich` calendar bounds;
- separate `activity`, `holding`, `activity_or_holding` and `activity_and_holding` predicates;
- world-local predicate evaluation with explicit existential aggregation to each global Asset ref;
- holding at any time, at the start, at the end or throughout the interval;
- predecessor events before `Von` solely as opening-state context;
- interval-scoped Activity rows without relabeling or moving predecessor events;
- all v2 domain, Account, algebra and final-exclusion semantics;
- a separate, singular Activity command target.

Activity dates remain available when FIFO is stale. Holding predicates require the already completed fresh FIFO-v2 event quantities and otherwise return `unavailable/holding_interval_not_fresh`. No filter starts a rebuild, Worker, Provider request or Product write.

ADR-153 clarifies the browser adapter without changing this algebra: a real browser `NULL` clears the corresponding nullable operand, an empty manual scope never widens to all Assets, and the explicit full reset restores fresh read-filter defaults without touching the singular Activity command target.
