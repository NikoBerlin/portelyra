# Desktop FX History Review v1

One confirmation stays one confirmation: in the guided path the owner authorizes the planned
requests with a single button that names them (count and period) after a read-only plan, instead of
ticking a box and then pressing a button. The staged candidate is still published without a refetch
(#283, 21.09.2026). The single-step controls keep their separate confirmations for corrections.

Plans only `not_requested` schema-2600 days without Provider access. The owner selects exactly one contiguous missing range. One confirmation authorizes one Yahoo chart request and persists a normalized candidate only in owner-local review staging. A separate publication confirmation appends that exact candidate without Provider refetch.

Weekends are explicit non-trading days; absent weekdays are source gaps. Incremental mode never modifies an existing day. Corrections and source-gap retries require later explicit modes. Pair Provider symbols come only from the reviewed persistent Pair-Provider binding and are never inferred from currency codes.

RC93 adds owner/path-bound v2 attempts, bounded saved responses, separate failure phases,
read-only inspection/recovery, and explicit append-only no-result review. No old claim
is reset. New overlapping requests are blocked while prior attempts are unreviewed
or staged; existing batch reservations are protected by the coordinator lock.
Native receipts distinguish published results from unpublished stages. A v2 writer
marker blocks incompatible runtime rollback. See
[ADR-210](../../../docs/decisions/ADR-210-fx-attempt-evidence-and-inline-provider-workflow.md).
The UI uses independent FX dates, consumes private dispatch authority before calling
the CLI and withdraws visible stale previews. Installation performs no domain operation.
