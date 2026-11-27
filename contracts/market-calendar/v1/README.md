# Market Calendar v1

RC92 uses one public-row selector for displayed additions and select-proposals:
bound validity alone no longer hides an unreviewed in-range closure proposal.
Already correctable dates, explicit openings and unverified contexts are excluded;
FX remains manual. Native authority is unchanged. See
[ADR-209](../../../docs/decisions/ADR-209-in-range-calendar-addition-controls.md).

Desktop additive extensions preserve the verified current scope's decisions and
validity, expose retained/new/full dates, and compare the expected binding inside
the registry write transaction. Native source evidence is revalidated under a read
lock through commit. Unverified selected profiles, incompatible rules and stale
previews block. No automatic correction or replay. See
[ADR-208](../../../docs/decisions/ADR-208-additive-reviewed-calendar-extension.md).

Versioned provider-free calendar profiles belong to one Listing or FX-pair binding, never merely to an Asset type. Profiles declare timezone, market code, validity, ISO session weekdays, explicit reviewed closures and special openings.

Classification emits review proposals only. A missing fetched value on a confirmed closed day may be proposed as `non_trading_day`; a missing expected session remains `source_gap`; `not_requested` remains fetch demand; an observation on a declared closed day becomes a conflict. No interpolation, history write, Provider call or Canonical write occurs.

The owner-local registry persists immutable profile versions and append-only Listing/FX-pair binding revisions in a `0700` area and `0600` SQLite store. One explicit candidate confirmation publishes a binding; replay of the same current profile is read-only.

Catalog reads require an existing owner-only regular store, reject links and SQLite
sidecars and WAL-mode headers, and use a read-only/query-only transaction without
file/schema creation. SQLite read locking remains active (no immutable bypass).
Latest profile and binding fingerprints are verified. Explicit binding commands also
record tenant/user/data-space/absolute-path proof in `calendar_binding_owner`.
Legacy bindings without proof require separate confirmation; confirming one does not
adopt sibling bindings. Diagnostic `require_context=false` exposes an explicit
`context_verified` flag but never permits unverified valuation use. Default readers
fail closed. Optional explicit `scopes` only limits which intact bindings need
positive proof; all stored rows and foreign-owner evidence still undergo validation.
Gap diagnostics use unproven bindings solely to display `context_confirmation_required`,
never to classify closures. A confirmed listing remains independently usable. The UI
selects a native listing or FX pair and separately confirms binding and one-date
correction; edits revoke both session authorities. See [ADR-202](../../../docs/decisions/ADR-202-calendar-diagnostics-and-provider-form-proposals.md)
and [ADR-199](../../../docs/decisions/ADR-199-saved-calendar-valuation-and-fetch-requirements.md).

The shared Desktop gap catalog reads native schema-2300 and FX schema-2600 histories together. It exposes only consumer labels/refs, dates, source/proposed statuses, reasons and dispositions; internal Listing/Pair refs stay private. Reading it performs no Provider or history write.

The listing UI additionally supports an explicit sparse, atomic correction set with
one confirmation, one native Market History request receipt and a local status panel.
Every selected date is enumerated; unselected/uncertain days and other scopes stay
unchanged. The calendar read lock spans native publication; stale source revisions
abort the entire set. FX retains the single-date boundary. See
[ADR-203](../../../docs/decisions/ADR-203-atomic-selected-calendar-corrections.md).

A separate one-date correction boundary revalidates the current bound profile and source-gap revision, then requires explicit confirmation before appending a `calendar_correction` revision to the owning schema-2300 or schema-2600 store. It never creates an observed price.
