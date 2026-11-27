# Desktop Statement Exchange Reward Adapters v1

Exact projection for the Kraken, Coinbase, Bison and BSDEX
Reward CSV formats. The adapters are active; "disabled" in dispositions such as `reward_candidate_disabled`
means only that an adapter has no write authority. Candidates reach the product solely
through the trusted Draft handoff and the canonical commands. Every source row is reconciled and no target identity is inferred.
An inclusive owner-selected local-date period is required by the product boundary. Reward
rows outside it remain visible as `outside_selected_period` and never become mapping rows
or Drafts; changing the period invalidates the current browser preview.

The output `mapping_rows` uses the shared Statement mapping contract. Source asset
labels such as an exchange's long-form crypto name remain unresolved for explicit UI
dropdown assignment. Other event classes remain deferred. Source valuation is retained
under an explicit precedence: Coinbase uses its currency-symbol-bearing inclusive Fiat total before its transaction price; Bison uses its profile-bound EUR market price; Kraken uses exact `amountusd - feeusd` in USD while preserving `amount - fee` as the net Asset quantity; BSDEX has no Source valuation. Missing currency or incomplete components remain `none` for later `valuation_pending` handling. No inclusive total is charged a second time. The common finalization proof carries all three Legacy-derived adapters through shared mapping, exact source-FX valuation where required, and strict canonical Reward semantics without granting an adapter write authority.

## Versioned profiles (#398)

Each adapter has one frozen profile: delimiter, locale, time zone, header search, default
account, valuation precedence, fee role, default currency, lifecycle state and write authority.
Profiles and a binding to the exact SHA-256 of `statement_exchange_reward_adapter_v1.py` and of
each reader module `plugins/readers/<exchange>/reader_reward.py` are kept with the development
sources; a code change requires raising the affected profile versions deliberately.

## Reader plugins (rc.377, #486)

Each exchange reads in its own reader plugin (domain `reward`, sandboxed, see
`contracts/statement-reader-plugin/v1/README.md`): the profile, header detection,
numbers, time, reward event values and source valuation. The plugin returns per source
row its cells, the exchange's own ID, the fields for cross-file duplicates and, for a
reward, asset, quantity, local time, fee, account and valuation. This core keeps the
source row keys (unchanged: the exchange ID alone, otherwise file and row), cross-file
duplicates, the selected period, the mapping rows and the row accounting. A reward dated
after today is rejected like in every other reader domain. Owner format overlays are
gone; an own format is a reader plugin (`statement_exchange_adapter_overlay_invalid`).
