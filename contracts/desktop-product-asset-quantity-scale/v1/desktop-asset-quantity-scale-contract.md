# Desktop Asset Quantity Scale Revision v1 Contract

## Scope

A quantity scale is a maximum accepted effective fractional scale, never a rounding instruction. Quantity, eligible-quantity and Asset-fee evidence is parsed as exact text, including bounded scientific notation. Insignificant trailing zeros are removed before the required scale is calculated.

A required scale at or below the current Asset scale continues through the ordinary Activity preview without a Catalog write. A required scale above 24 blocks. A required scale strictly between the current scale and 24 enters `ready_for_confirmation`.

## Warning and confirmation

The public Preview contains only the Asset label, current/required/proposed scales, affected FIFO-world count and this meaning: the scale will increase and affected FIFO histories will be rebuilt; no quantity is rounded. Browser input cannot supply Context, canonical IDs, paths, command tokens, fingerprints or SQL.

## Resumable Product operation

Execution:

1. validates the exact Canonical fingerprint, active generation and Asset revision from Preview;
2. consumes an owner-only Attempt before any domain write;
3. delegates the increase to the sole Catalog writer `catalog_rescale_asset_v1`;
4. rematerializes the unchanged active Activity set from the revised Catalog;
5. requires the prospective and final FIFO-v2 world fingerprints to match exactly;
6. publishes a new immutable schema-401 generation and receipt, then replaces `active.json` last;
7. leaves Realized Materialization stale until an explicit incremental affected-world rebuild succeeds.

A crash before Catalog write is `pending_catalog_write`. A crash after Catalog commit is `pending_generation_finalize`. Explicit Resume reuses the bound Attempt and exact Catalog command; it does not ask for a second owner decision or create another Asset revision. Prior Catalog bytes cannot be restored after a valid commit, and every prior schema-401 generation remains byte-identical.

The scale-only operation writes no Activity fact. A subsequent Activity is previewed and confirmed normally against the increased scale. This v1 implementation supports increases only. A decrease remains pending the complete active-fact lower-bound validator required by ADR-135.

## Rebuild boundary

The scale is part of the FIFO-v2 world input. Therefore every existing world in which the Asset is the target or a stock-dividend source is affected even if all event bytes are unchanged. Display reads never trigger rebuilding. A failed rebuild keeps canonical facts and the active generation committed while the derived state remains visibly stale.

Cash, Provider/network, Tax policy, alarms, automation, server changes and complete-portfolio claims are outside this command.
