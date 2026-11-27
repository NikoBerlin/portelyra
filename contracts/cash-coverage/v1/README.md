# Cash Coverage v1

Exact Cash semantics and an owner-only persistent Data-command boundary for optional Cash maintenance.

The authority family has two explicit historical signatures:

- `schema-2900.sql`: frozen original schema;
- `schema.sql`: current schema-2901 with immutable correction lineage, attempt evidence, command provenance, recovery authority, and migration receipt.

Normative files include:

- `cash-coverage-contract.md`, `fresh-cash-operations.md`, `coverage-modes.csv`, `event-types.csv`;
- `capability-matrix.csv`, `failure-codes.csv`, `state-machine.csv`;
- semantic `input.schema.json` and `preview.schema.json`;
- product `command.schema.json`, `command-preview.schema.json`, and `read-model.schema.json`;
- `store-migration-public-preview.schema.json`, `store-migration-trusted-preview.schema.json`, `store-migration-confirmation.schema.json`, `store-migration-attempt.schema.json`, and `store-migration-receipt.schema.json`;
- `store-migration-recovery-public-preview.schema.json`, `store-migration-recovery-trusted-preview.schema.json`, `store-migration-recovery-confirmation.schema.json`, and `store-migration-recovery-attempt.schema.json`;
- `schema-2900.sql`, `schema.sql`, `source-fingerprints.csv`, and `golden-fingerprints.csv`.

References:

- pure evaluator: `migrations/reference/cash_coverage_v1.py`;
- owner-local commands/read model/recovery: `migrations/reference/desktop_cash_coverage_v1.py`;
- create-only schema migration: `migrations/reference/cash_coverage_store_migration_v2900_to_v2901.py`;
- strict migration process edge: `scripts/cash_coverage_store_migration.py`.

No Cash coverage is inferred. Missing Cash is unavailable rather than zero; Interest GuV and Cash balance effects remain separate. New facts require exact local-zone time evidence. Corrections preserve predecessors and publish only an active projection through explicit lineage. The completed browser model is label-only and exposes no path, Context, internal identifier, or fingerprint.
