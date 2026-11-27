PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

BEGIN IMMEDIATE;

CREATE TEMP TABLE canonical_v2_2_migration_guard (
  valid INTEGER NOT NULL CHECK (valid = 1)
) STRICT;

INSERT INTO canonical_v2_2_migration_guard(valid)
SELECT CASE WHEN
  (SELECT user_version FROM pragma_user_version) = 201
  AND NOT EXISTS (SELECT 1 FROM store_binding WHERE schema_version != 201)
  AND NOT EXISTS (
    SELECT 1 FROM sqlite_master
    WHERE type IN ('table', 'view')
      AND name IN ('canonical_master_import_receipt', 'canonical_master_import_status')
  )
THEN 1 ELSE 0 END;

DROP TABLE canonical_v2_2_migration_guard;

DROP TRIGGER store_binding_no_update;
DROP TRIGGER store_binding_no_delete;

ALTER TABLE store_binding RENAME TO store_binding_v201;

CREATE TABLE store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 202),
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 3 AND 64 AND tenant_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 3 AND 64 AND user_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  data_space_id TEXT NOT NULL CHECK (data_space_id LIKE 'sbx_%' AND length(data_space_id) BETWEEN 8 AND 64 AND data_space_id NOT GLOB '*[^a-z0-9_]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z')
) STRICT;

INSERT INTO store_binding(singleton_id, schema_version, tenant_id, user_id, data_space_id, created_at_utc)
SELECT singleton_id, 202, tenant_id, user_id, data_space_id, created_at_utc
FROM store_binding_v201;

DROP TABLE store_binding_v201;

CREATE TRIGGER store_binding_no_update
BEFORE UPDATE ON store_binding
BEGIN
  SELECT RAISE(ABORT, 'store_binding_is_immutable');
END;

CREATE TRIGGER store_binding_no_delete
BEFORE DELETE ON store_binding
BEGIN
  SELECT RAISE(ABORT, 'store_binding_is_immutable');
END;

DROP TRIGGER asset_no_delete;

ALTER TABLE asset RENAME TO asset_v201;

CREATE TABLE asset (
  asset_id TEXT PRIMARY KEY CHECK (asset_id LIKE 'ast_%' AND length(asset_id) BETWEEN 8 AND 64 AND asset_id NOT GLOB '*[^a-z0-9_]*'),
  display_name TEXT NOT NULL COLLATE NOCASE CHECK (length(trim(display_name)) BETWEEN 1 AND 160),
  asset_type TEXT NOT NULL CHECK (asset_type IN ('equity', 'etf', 'fund', 'bond', 'crypto', 'commodity', 'cash', 'fx', 'index', 'derivative', 'other')),
  price_currency TEXT NOT NULL CHECK (length(price_currency) = 3 AND price_currency = upper(price_currency) AND price_currency NOT GLOB '*[^A-Z]*'),
  quantity_scale INTEGER NOT NULL DEFAULT 8 CHECK (quantity_scale BETWEEN 0 AND 24),
  valuation_method TEXT NOT NULL CHECK (valuation_method IN ('external_market', 'manual', 'unit_value', 'transaction_only')),
  isin TEXT CHECK (isin IS NULL OR (length(isin) = 12 AND isin = upper(isin) AND isin NOT GLOB '*[^A-Z0-9]*')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  origin_type TEXT NOT NULL DEFAULT 'native' CHECK (origin_type IN ('native', 'legacy_import')),
  origin_ref TEXT,
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc) = 20 AND substr(updated_at_utc, 11, 1) = 'T' AND substr(updated_at_utc, 20, 1) = 'Z'),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  CHECK ((origin_type = 'native' AND origin_ref IS NULL) OR (origin_type = 'legacy_import' AND length(trim(origin_ref)) > 0))
) STRICT;

INSERT INTO asset
(asset_id, display_name, asset_type, price_currency, quantity_scale, valuation_method,
 isin, status, origin_type, origin_ref, created_at_utc, updated_at_utc, revision)
SELECT asset_id, display_name, asset_type, price_currency, quantity_scale, valuation_method,
       isin, status, origin_type, origin_ref, created_at_utc, updated_at_utc, revision
FROM asset_v201;

DROP TABLE asset_v201;

CREATE UNIQUE INDEX asset_isin_unique
ON asset(isin)
WHERE isin IS NOT NULL;

CREATE UNIQUE INDEX asset_legacy_origin_ref_unique
ON asset(origin_ref)
WHERE origin_type = 'legacy_import';

CREATE TRIGGER asset_no_delete
BEFORE DELETE ON asset
BEGIN
  SELECT RAISE(ABORT, 'asset_must_be_archived_not_deleted');
END;

CREATE TRIGGER derivative_transaction_posting_blocked
BEFORE INSERT ON transaction_posting
WHEN EXISTS (
  SELECT 1 FROM asset entity
  WHERE entity.asset_id = NEW.asset_id
    AND entity.asset_type = 'derivative'
)
BEGIN
  SELECT RAISE(ABORT, 'derivative_transaction_contract_required');
END;

CREATE TABLE canonical_master_import_receipt (
  master_import_receipt_id TEXT PRIMARY KEY CHECK (
    master_import_receipt_id LIKE 'mrc_%'
    AND length(master_import_receipt_id) BETWEEN 8 AND 64
    AND master_import_receipt_id NOT GLOB '*[^a-z0-9_]*'
  ),
  command_id TEXT NOT NULL UNIQUE REFERENCES data_command_audit(command_id),
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 3 AND 64 AND tenant_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 3 AND 64 AND user_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  target_sandbox_id TEXT NOT NULL CHECK (
    target_sandbox_id LIKE 'sbx_%'
    AND length(target_sandbox_id) BETWEEN 8 AND 64
    AND target_sandbox_id NOT GLOB '*[^a-z0-9_]*'
  ),
  target_portfolio_id TEXT NOT NULL REFERENCES portfolio(portfolio_id),
  source_contract_version INTEGER NOT NULL CHECK (source_contract_version = 1),
  master_staging_schema_version INTEGER NOT NULL CHECK (master_staging_schema_version = 1402),
  canonical_schema_version INTEGER NOT NULL CHECK (canonical_schema_version = 202),
  source_import_run_id TEXT NOT NULL UNIQUE CHECK (
    source_import_run_id LIKE 'mimp_%'
    AND length(source_import_run_id) BETWEEN 9 AND 64
    AND source_import_run_id NOT GLOB '*[^a-z0-9_]*'
  ),
  source_set_fingerprint TEXT NOT NULL UNIQUE CHECK (
    length(source_set_fingerprint) = 64
    AND source_set_fingerprint = lower(source_set_fingerprint)
    AND source_set_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  projection_contract_fingerprint TEXT NOT NULL CHECK (
    length(projection_contract_fingerprint) = 64
    AND projection_contract_fingerprint = lower(projection_contract_fingerprint)
    AND projection_contract_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  staging_artifact_fingerprint TEXT NOT NULL CHECK (
    length(staging_artifact_fingerprint) = 64
    AND staging_artifact_fingerprint = lower(staging_artifact_fingerprint)
    AND staging_artifact_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  candidate_fingerprint TEXT NOT NULL UNIQUE CHECK (
    length(candidate_fingerprint) = 64
    AND candidate_fingerprint = lower(candidate_fingerprint)
    AND candidate_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  confirmation_fingerprint TEXT NOT NULL UNIQUE CHECK (
    length(confirmation_fingerprint) = 64
    AND confirmation_fingerprint = lower(confirmation_fingerprint)
    AND confirmation_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  origin_ref_namespace TEXT NOT NULL UNIQUE CHECK (
    origin_ref_namespace LIKE 'lmr_%_'
    AND length(origin_ref_namespace) = 29
    AND origin_ref_namespace = lower(origin_ref_namespace)
    AND origin_ref_namespace NOT GLOB '*[^a-z0-9_]*'
  ),
  portfolio_count INTEGER NOT NULL CHECK (portfolio_count = 1),
  account_count INTEGER NOT NULL CHECK (account_count >= 1),
  asset_count INTEGER NOT NULL CHECK (asset_count >= 1),
  provider_mapping_count INTEGER NOT NULL CHECK (provider_mapping_count = 0),
  actor_id TEXT NOT NULL CHECK (length(trim(actor_id)) BETWEEN 3 AND 80),
  committed_at_utc TEXT NOT NULL CHECK (
    length(committed_at_utc) = 20
    AND substr(committed_at_utc, 11, 1) = 'T'
    AND substr(committed_at_utc, 20, 1) = 'Z'
  ),
  receipt_fingerprint TEXT NOT NULL UNIQUE CHECK (
    length(receipt_fingerprint) = 64
    AND receipt_fingerprint = lower(receipt_fingerprint)
    AND receipt_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  CHECK (origin_ref_namespace = 'lmr_' || substr(candidate_fingerprint, 1, 24) || '_')
) STRICT;

CREATE TRIGGER canonical_master_import_receipt_validate
BEFORE INSERT ON canonical_master_import_receipt
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM store_binding binding
    WHERE binding.singleton_id = 1
      AND binding.schema_version = NEW.canonical_schema_version
      AND binding.tenant_id = NEW.tenant_id
      AND binding.user_id = NEW.user_id
      AND binding.data_space_id = NEW.target_sandbox_id
  ) THEN RAISE(ABORT, 'master_import_receipt_runtime_context_or_data_space_mismatch') END;

  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM data_command_audit audit
    WHERE audit.command_id = NEW.command_id
      AND audit.area_id = 'canonical_import_receipt'
      AND audit.command_type = 'legacy_master_bootstrap_v1'
      AND audit.entity_id = NEW.target_portfolio_id
      AND audit.actor_id = NEW.actor_id
      AND audit.committed_at_utc = NEW.committed_at_utc
      AND audit.payload_fingerprint = NEW.candidate_fingerprint
      AND audit.origin_type = 'legacy_import'
      AND audit.origin_ref = NEW.source_import_run_id
  ) THEN RAISE(ABORT, 'master_import_receipt_audit_mismatch') END;

  SELECT CASE WHEN
    (SELECT count(*) FROM portfolio) != NEW.portfolio_count
    OR (SELECT count(*) FROM account) != NEW.account_count
    OR (SELECT count(*) FROM asset) != NEW.asset_count
    OR (SELECT count(*) FROM provider_mapping) != NEW.provider_mapping_count
    OR (SELECT count(*) FROM transaction_record) != 0
    OR (SELECT count(*) FROM transaction_posting) != 0
    OR (SELECT count(*) FROM transaction_seal) != 0
    OR (SELECT count(*) FROM data_command_audit) != 1
    OR (SELECT count(*) FROM canonical_import_receipt) != 0
    OR (SELECT count(*) FROM canonical_master_import_receipt) != 0
  THEN RAISE(ABORT, 'master_import_receipt_target_sandbox_not_empty') END;

  SELECT CASE WHEN NEW.portfolio_count != (
    SELECT count(*) FROM portfolio entity
    WHERE entity.portfolio_id = NEW.target_portfolio_id
      AND entity.origin_type = 'native'
      AND entity.origin_ref IS NULL
  ) THEN RAISE(ABORT, 'master_import_receipt_portfolio_count_mismatch') END;

  SELECT CASE WHEN NEW.account_count != (
    SELECT count(*) FROM account entity
    WHERE entity.portfolio_id = NEW.target_portfolio_id
      AND entity.origin_type = 'native'
      AND entity.origin_ref IS NULL
  ) THEN RAISE(ABORT, 'master_import_receipt_account_count_mismatch') END;

  SELECT CASE WHEN NEW.asset_count != (
    SELECT count(*) FROM asset entity
    WHERE entity.origin_type = 'legacy_import'
      AND substr(entity.origin_ref, 1, length(NEW.origin_ref_namespace)) = NEW.origin_ref_namespace
  ) THEN RAISE(ABORT, 'master_import_receipt_asset_count_mismatch') END;
END;

CREATE TRIGGER canonical_master_import_receipt_no_update
BEFORE UPDATE ON canonical_master_import_receipt
BEGIN
  SELECT RAISE(ABORT, 'canonical_master_import_receipt_is_immutable');
END;

CREATE TRIGGER canonical_master_import_receipt_no_delete
BEFORE DELETE ON canonical_master_import_receipt
BEGIN
  SELECT RAISE(ABORT, 'canonical_master_import_receipt_is_immutable');
END;

CREATE VIEW canonical_master_import_status AS
SELECT
  receipt.master_import_receipt_id,
  receipt.command_id,
  receipt.tenant_id,
  receipt.user_id,
  receipt.target_sandbox_id,
  receipt.target_portfolio_id,
  receipt.source_import_run_id,
  receipt.source_set_fingerprint,
  receipt.candidate_fingerprint,
  receipt.confirmation_fingerprint,
  receipt.portfolio_count,
  receipt.account_count,
  receipt.asset_count,
  receipt.provider_mapping_count,
  receipt.committed_at_utc,
  receipt.receipt_fingerprint
FROM canonical_master_import_receipt receipt;

PRAGMA user_version = 202;

COMMIT;

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
