# Desktop Product Asset Activity v1

This contract integrates both native Asset Activity commands and the per-Asset Legacy review with the owner-only Desktop Product without making the ephemeral Desktop Workflow ledger canonical.

Normative files:

- `desktop-product-asset-activity-contract.md` — authority and generation lifecycle;
- `preview.schema.json` — trusted Legacy-cutover Product Preview/replay response;
- `native-preview.schema.json` — frozen FIFO-v1 compatibility shape; M7 Data Preview uses the additive `../v1.1/native-preview.schema.json` FIFO-v2 shape;
- `native-attempt.schema.json` — immutable Attempt persisted after validation and before native event/generation write;
- `generation-manifest.schema.json` — immutable completed generation binding;
- `result.schema.json` — commit/replay/recovery result and `canonical_write` meaning;
- `failure-codes.csv`, `state-machine.csv`, `capability-matrix.csv`;
- `source-fingerprints.csv` — implementation/test integrity boundary.

Implementation is in
`migrations/reference/desktop_product_asset_activity_v1.py`; the M7 Data reader is
`migrations/reference/desktop_product_asset_activity_view_v2.py`. Tests use only invented
schema-201 catalogs, Transactions and Legacy-style CSV fixtures. This contract does
not authorize private Trade access or Product cutover. ADR-143 narrows immutable
recovery discovery to the expected Plan/command fingerprint before a historical
ledger is opened or hashed; matching-candidate validation remains unchanged.
