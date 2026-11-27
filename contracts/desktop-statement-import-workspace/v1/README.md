# Desktop Statement Import Workspace v1

Status: **synthetic mapping/reconciliation boundary; private UAT and activation not completed**

This contract adds an explicit, flexible, read-only workspace for the first Kraken Ledger CSV source profile. The tracked source, catalog, enrichments, and existing-event projections are entirely invented. No private file chooser or private source read is present.

The workspace proves:

- exact header and immutable mapping-profile revision binding;
- explicit column dispositions and exact `type`/`subtype`/`aclass` routes;
- `txid` row identity, `refid` group evidence, and a non-identity source ordinal;
- browser-local portfolio, account, and asset option mapping;
- a separate Catalog handoff requirement for unknown assets;
- exact manual reward valuation by unit price or fiat total;
- closed-row reconciliation across every terminal disposition;
- visible Cash deferral to issue #184;
- a disabled, separate market-history provider handoff.

The sole executable Product operation is `review-synthetic` in `scripts/statement_import_workspace.py`. It accepts only one fixed scenario name and reads only the two hash-bound public invented fixtures listed in `synthetic-fixtures.csv`.

Normative files are the contract, public JSON Schema, CSV matrices, immutable profile registry, and fixture registry in this directory. The reference worker is `migrations/reference/desktop_statement_import_workspace_v1.py`; the Data-app service is `apps/data/data_statement_import_workspace_v1.R`.
