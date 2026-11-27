# Reward Valuation v1

Provider-neutral exact valuation evidence for `valuation_pending` Reward drafts. See ADR-179.

- Intraday evidence must not be later than the event.
- Daily Close is an explicit confirmed fallback, never automatic.
- Asset and FX evidence remain separate and fingerprint-bound.
- No Provider or Canonical write is authorized.
- The Desktop resolver requires the published native revision for the Reward local date. FX uses that date when observed; otherwise it may propose the latest published prior observation up to three calendar days old.
- Prior FX source date, calendar age and selection basis remain visible and fingerprint-bound. Older or absent evidence leaves the Draft pending.
- A complete proposal still requires separate Daily-Close confirmation before one atomic ActivityDraft revision.
- Statement-scoped revalidation explicitly writes missing nullable Reward fields as `null` before strict validation; it does not alter quantities, prices, account assignments or source evidence.
- Canonical finalization previews only complete and ready Drafts from the current Statement. After one separate owner confirmation, each row is freshly revalidated and delegated to the sole native writer, which performs the exact FIFO guard before publishing its cumulative generation.
- BSDEX, Kraken, Coinbase and Bison share this finalization path; importers never receive canonical or FIFO write authority.
- A partially committed same-statement collision is classified read-only. Confirmed `distinct_same_time` pairs bind one shared source-row-order evidence group; the sole native writer publishes the new event and evidence for both group members atomically. `probable_duplicate` and unresolved cases remain blocked.
