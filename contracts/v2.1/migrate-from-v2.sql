PRAGMA foreign_keys = OFF;

BEGIN IMMEDIATE;

CREATE TEMP TABLE canonical_v2_1_migration_guard (
  valid INTEGER NOT NULL CHECK (valid = 1)
) STRICT;

INSERT INTO canonical_v2_1_migration_guard(valid)
SELECT CASE WHEN
  (SELECT user_version FROM pragma_user_version) = 2
  AND NOT EXISTS (SELECT 1 FROM store_binding WHERE schema_version != 2)
  AND NOT EXISTS (SELECT 1 FROM portfolio WHERE origin_type = 'legacy_import')
  AND NOT EXISTS (SELECT 1 FROM account WHERE origin_type = 'legacy_import')
  AND NOT EXISTS (SELECT 1 FROM asset WHERE origin_type = 'legacy_import')
  AND NOT EXISTS (SELECT 1 FROM transaction_record WHERE origin_type = 'legacy_import')
  AND NOT EXISTS (SELECT 1 FROM data_command_audit WHERE origin_type = 'legacy_import')
THEN 1 ELSE 0 END;

DROP TABLE canonical_v2_1_migration_guard;

DROP TRIGGER store_binding_no_update;
DROP TRIGGER store_binding_no_delete;

ALTER TABLE store_binding RENAME TO store_binding_v2;

CREATE TABLE store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 201),
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 3 AND 64 AND tenant_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 3 AND 64 AND user_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  data_space_id TEXT NOT NULL CHECK (data_space_id LIKE 'sbx_%' AND length(data_space_id) BETWEEN 8 AND 64 AND data_space_id NOT GLOB '*[^a-z0-9_]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z')
) STRICT;

INSERT INTO store_binding(singleton_id, schema_version, tenant_id, user_id, data_space_id, created_at_utc)
SELECT singleton_id, 201, tenant_id, user_id, 'sbx_primary', created_at_utc
FROM store_binding_v2;

DROP TABLE store_binding_v2;

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

DROP TRIGGER data_command_audit_no_update;
DROP TRIGGER data_command_audit_no_delete;

ALTER TABLE data_command_audit RENAME TO data_command_audit_v2;

CREATE TABLE data_command_audit (
  command_id TEXT PRIMARY KEY CHECK (command_id LIKE 'cmd_%' AND length(command_id) BETWEEN 8 AND 64 AND command_id NOT GLOB '*[^a-z0-9_]*'),
  area_id TEXT NOT NULL CHECK (area_id IN ('portfolio_catalog', 'account_catalog', 'asset_catalog', 'provider_mapping', 'transaction_ledger', 'canonical_import_receipt')),
  command_type TEXT NOT NULL CHECK (length(trim(command_type)) BETWEEN 3 AND 80),
  entity_id TEXT NOT NULL CHECK (length(trim(entity_id)) BETWEEN 8 AND 64),
  actor_id TEXT NOT NULL CHECK (length(trim(actor_id)) BETWEEN 3 AND 80),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc) = 20 AND substr(committed_at_utc, 11, 1) = 'T' AND substr(committed_at_utc, 20, 1) = 'Z'),
  payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64 AND payload_fingerprint = lower(payload_fingerprint) AND payload_fingerprint NOT GLOB '*[^a-f0-9]*'),
  origin_type TEXT NOT NULL DEFAULT 'native' CHECK (origin_type IN ('native', 'legacy_import')),
  origin_ref TEXT,
  CHECK ((origin_type = 'native' AND origin_ref IS NULL) OR (origin_type = 'legacy_import' AND length(trim(origin_ref)) > 0))
) STRICT;

INSERT INTO data_command_audit
(command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,
 payload_fingerprint, origin_type, origin_ref)
SELECT command_id, area_id, command_type, entity_id, actor_id, committed_at_utc,
       payload_fingerprint, origin_type, origin_ref
FROM data_command_audit_v2;

DROP TABLE data_command_audit_v2;

CREATE TRIGGER data_command_audit_no_update
BEFORE UPDATE ON data_command_audit
BEGIN
  SELECT RAISE(ABORT, 'data_command_audit_is_immutable');
END;

CREATE TRIGGER data_command_audit_no_delete
BEFORE DELETE ON data_command_audit
BEGIN
  SELECT RAISE(ABORT, 'data_command_audit_is_immutable');
END;

CREATE UNIQUE INDEX portfolio_legacy_origin_ref_unique
ON portfolio(origin_ref)
WHERE origin_type = 'legacy_import';

CREATE UNIQUE INDEX account_legacy_origin_ref_unique
ON account(origin_ref)
WHERE origin_type = 'legacy_import';

CREATE UNIQUE INDEX asset_legacy_origin_ref_unique
ON asset(origin_ref)
WHERE origin_type = 'legacy_import';

CREATE UNIQUE INDEX transaction_legacy_origin_ref_unique
ON transaction_record(origin_ref)
WHERE origin_type = 'legacy_import';

CREATE TABLE canonical_import_receipt (
  import_receipt_id TEXT PRIMARY KEY CHECK (import_receipt_id LIKE 'irc_%' AND length(import_receipt_id) BETWEEN 8 AND 64 AND import_receipt_id NOT GLOB '*[^a-z0-9_]*'),
  command_id TEXT NOT NULL UNIQUE REFERENCES data_command_audit(command_id),
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 3 AND 64 AND tenant_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 3 AND 64 AND user_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  target_sandbox_id TEXT NOT NULL CHECK (target_sandbox_id LIKE 'sbx_%' AND length(target_sandbox_id) BETWEEN 8 AND 64 AND target_sandbox_id NOT GLOB '*[^a-z0-9_]*'),
  target_portfolio_id TEXT NOT NULL REFERENCES portfolio(portfolio_id),
  source_contract_version INTEGER NOT NULL CHECK (source_contract_version = 1),
  staging_schema_version INTEGER NOT NULL CHECK (staging_schema_version = 1001),
  canonical_schema_version INTEGER NOT NULL CHECK (canonical_schema_version = 201),
  source_import_run_id TEXT NOT NULL UNIQUE CHECK (source_import_run_id LIKE 'imp_%' AND length(source_import_run_id) BETWEEN 8 AND 64 AND source_import_run_id NOT GLOB '*[^a-z0-9_]*'),
  source_set_fingerprint TEXT NOT NULL UNIQUE CHECK (length(source_set_fingerprint) = 64 AND source_set_fingerprint = lower(source_set_fingerprint) AND source_set_fingerprint NOT GLOB '*[^a-f0-9]*'),
  parser_bundle_fingerprint TEXT NOT NULL CHECK (length(parser_bundle_fingerprint) = 64 AND parser_bundle_fingerprint = lower(parser_bundle_fingerprint) AND parser_bundle_fingerprint NOT GLOB '*[^a-f0-9]*'),
  staging_artifact_fingerprint TEXT NOT NULL CHECK (length(staging_artifact_fingerprint) = 64 AND staging_artifact_fingerprint = lower(staging_artifact_fingerprint) AND staging_artifact_fingerprint NOT GLOB '*[^a-f0-9]*'),
  candidate_fingerprint TEXT NOT NULL UNIQUE CHECK (length(candidate_fingerprint) = 64 AND candidate_fingerprint = lower(candidate_fingerprint) AND candidate_fingerprint NOT GLOB '*[^a-f0-9]*'),
  confirmation_fingerprint TEXT NOT NULL UNIQUE CHECK (length(confirmation_fingerprint) = 64 AND confirmation_fingerprint = lower(confirmation_fingerprint) AND confirmation_fingerprint NOT GLOB '*[^a-f0-9]*'),
  origin_ref_namespace TEXT NOT NULL UNIQUE CHECK (
    origin_ref_namespace LIKE 'lir_%_'
    AND length(origin_ref_namespace) = 29
    AND origin_ref_namespace = lower(origin_ref_namespace)
    AND origin_ref_namespace NOT GLOB '*[^a-z0-9_]*'
  ),
  portfolio_count INTEGER NOT NULL CHECK (portfolio_count = 1),
  account_count INTEGER NOT NULL CHECK (account_count >= 1),
  asset_count INTEGER NOT NULL CHECK (asset_count >= 1),
  transaction_count INTEGER NOT NULL CHECK (transaction_count >= 1),
  posting_count INTEGER NOT NULL CHECK (posting_count >= 1),
  actor_id TEXT NOT NULL CHECK (length(trim(actor_id)) BETWEEN 3 AND 80),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc) = 20 AND substr(committed_at_utc, 11, 1) = 'T' AND substr(committed_at_utc, 20, 1) = 'Z'),
  receipt_fingerprint TEXT NOT NULL UNIQUE CHECK (length(receipt_fingerprint) = 64 AND receipt_fingerprint = lower(receipt_fingerprint) AND receipt_fingerprint NOT GLOB '*[^a-f0-9]*'),
  CHECK (origin_ref_namespace = 'lir_' || substr(candidate_fingerprint, 1, 24) || '_')
) STRICT;

CREATE TRIGGER canonical_import_receipt_validate
BEFORE INSERT ON canonical_import_receipt
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM store_binding binding
    WHERE binding.singleton_id = 1
      AND binding.schema_version = NEW.canonical_schema_version
      AND binding.tenant_id = NEW.tenant_id
      AND binding.user_id = NEW.user_id
      AND binding.data_space_id = NEW.target_sandbox_id
  ) THEN RAISE(ABORT, 'import_receipt_runtime_context_or_data_space_mismatch') END;

  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM data_command_audit audit
    WHERE audit.command_id = NEW.command_id
      AND audit.area_id = 'canonical_import_receipt'
      AND audit.command_type = 'legacy_import_commit_v1'
      AND audit.entity_id = NEW.target_portfolio_id
      AND audit.actor_id = NEW.actor_id
      AND audit.committed_at_utc = NEW.committed_at_utc
      AND audit.payload_fingerprint = NEW.candidate_fingerprint
      AND audit.origin_type = 'legacy_import'
      AND audit.origin_ref = NEW.source_import_run_id
  ) THEN RAISE(ABORT, 'import_receipt_audit_mismatch') END;

  SELECT CASE WHEN
    (SELECT count(*) FROM portfolio) != NEW.portfolio_count
    OR (SELECT count(*) FROM account) != NEW.account_count
    OR (SELECT count(*) FROM asset) != NEW.asset_count
    OR (SELECT count(*) FROM transaction_record) != NEW.transaction_count
    OR (SELECT count(*) FROM transaction_posting) != NEW.posting_count
    OR (SELECT count(*) FROM transaction_seal) != NEW.transaction_count
    OR (SELECT count(*) FROM provider_mapping) != 0
    OR (SELECT count(*) FROM data_command_audit) != 1
  THEN RAISE(ABORT, 'import_receipt_target_sandbox_not_empty') END;

  SELECT CASE WHEN NEW.portfolio_count != (
    SELECT count(*) FROM portfolio entity
    WHERE entity.portfolio_id = NEW.target_portfolio_id
      AND entity.origin_type = 'legacy_import'
      AND substr(entity.origin_ref, 1, length(NEW.origin_ref_namespace)) = NEW.origin_ref_namespace
  ) THEN RAISE(ABORT, 'import_receipt_portfolio_count_mismatch') END;

  SELECT CASE WHEN NEW.account_count != (
    SELECT count(*) FROM account entity
    WHERE entity.portfolio_id = NEW.target_portfolio_id
      AND entity.origin_type = 'legacy_import'
      AND substr(entity.origin_ref, 1, length(NEW.origin_ref_namespace)) = NEW.origin_ref_namespace
  ) THEN RAISE(ABORT, 'import_receipt_account_count_mismatch') END;

  SELECT CASE WHEN NEW.asset_count != (
    SELECT count(*) FROM asset entity
    WHERE entity.origin_type = 'legacy_import'
      AND substr(entity.origin_ref, 1, length(NEW.origin_ref_namespace)) = NEW.origin_ref_namespace
  ) THEN RAISE(ABORT, 'import_receipt_asset_count_mismatch') END;

  SELECT CASE WHEN NEW.transaction_count != (
    SELECT count(*) FROM transaction_record entity
    WHERE entity.portfolio_id = NEW.target_portfolio_id
      AND entity.origin_type = 'legacy_import'
      AND substr(entity.origin_ref, 1, length(NEW.origin_ref_namespace)) = NEW.origin_ref_namespace
  ) THEN RAISE(ABORT, 'import_receipt_transaction_count_mismatch') END;

  SELECT CASE WHEN NEW.transaction_count != (
    SELECT count(*)
    FROM transaction_record entity
    JOIN transaction_seal seal ON seal.transaction_id = entity.transaction_id
    WHERE entity.portfolio_id = NEW.target_portfolio_id
      AND entity.origin_type = 'legacy_import'
      AND substr(entity.origin_ref, 1, length(NEW.origin_ref_namespace)) = NEW.origin_ref_namespace
  ) THEN RAISE(ABORT, 'import_receipt_transaction_unsealed') END;

  SELECT CASE WHEN NEW.posting_count != (
    SELECT count(*)
    FROM transaction_posting posting
    JOIN transaction_record entity ON entity.transaction_id = posting.transaction_id
    WHERE entity.portfolio_id = NEW.target_portfolio_id
      AND entity.origin_type = 'legacy_import'
      AND substr(entity.origin_ref, 1, length(NEW.origin_ref_namespace)) = NEW.origin_ref_namespace
  ) THEN RAISE(ABORT, 'import_receipt_posting_count_mismatch') END;
END;

CREATE TRIGGER canonical_import_receipt_no_update
BEFORE UPDATE ON canonical_import_receipt
BEGIN
  SELECT RAISE(ABORT, 'canonical_import_receipt_is_immutable');
END;

CREATE TRIGGER canonical_import_receipt_no_delete
BEFORE DELETE ON canonical_import_receipt
BEGIN
  SELECT RAISE(ABORT, 'canonical_import_receipt_is_immutable');
END;

CREATE VIEW canonical_import_status AS
SELECT
  receipt.import_receipt_id,
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
  receipt.transaction_count,
  receipt.posting_count,
  receipt.committed_at_utc,
  receipt.receipt_fingerprint
FROM canonical_import_receipt receipt;

PRAGMA user_version = 201;

COMMIT;

PRAGMA foreign_keys = ON;
