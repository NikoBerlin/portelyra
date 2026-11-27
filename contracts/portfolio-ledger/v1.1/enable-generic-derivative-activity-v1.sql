-- Schema-401 additive capability: admit generic non-Cash Derivative Activity.
-- Existing events and the protected schema-400/schema-401 sources remain unchanged.
PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

CREATE TEMP TABLE portfolio_ledger_v1_1_derivative_guard (
  valid INTEGER NOT NULL CHECK (valid = 1)
) STRICT;

INSERT INTO portfolio_ledger_v1_1_derivative_guard(valid)
SELECT CASE WHEN
  (SELECT user_version FROM pragma_user_version) = 401
  AND NOT EXISTS (SELECT 1 FROM ledger_store_binding WHERE schema_version != 401)
  AND EXISTS (
    SELECT 1 FROM asset_activity_schema_patch
    WHERE singleton_id = 1
      AND patch_name = 'signed_net_trade_proceeds_v1'
      AND semantic_contract = 'asset_activity_v1'
      AND source_schema_version = 401
  )
  AND EXISTS (
    SELECT 1 FROM sqlite_master
    WHERE type = 'table' AND name = 'asset_activity_fifo_order_evidence'
  )
  AND EXISTS (
    SELECT 1 FROM sqlite_master
    WHERE type = 'trigger' AND name = 'asset_activity_event_validate'
  )
  AND NOT EXISTS (
    SELECT 1 FROM sqlite_master
    WHERE type = 'table' AND name = 'asset_activity_generic_derivative_capability'
  )
THEN 1 ELSE 0 END;

DROP TABLE portfolio_ledger_v1_1_derivative_guard;

DROP TRIGGER asset_activity_event_validate;

CREATE TRIGGER asset_activity_event_validate
BEFORE INSERT ON asset_activity_event
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM ledger_command_receipt receipt
    WHERE receipt.command_id = NEW.command_id
      AND receipt.writer_area = 'data_app'
      AND receipt.action_type IN ('asset_activity_create_v1', 'per_asset_legacy_cutover_v1')
  ) THEN RAISE(ABORT, 'asset_activity_writer_invalid') END;

  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM account_entity account
    WHERE account.account_id = NEW.account_id
      AND account.portfolio_id = NEW.portfolio_id
  ) THEN RAISE(ABORT, 'asset_activity_account_scope_invalid') END;

  SELECT CASE WHEN NEW.related_account_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM account_entity account
    WHERE account.account_id = NEW.related_account_id
      AND account.portfolio_id = NEW.portfolio_id
  ) THEN RAISE(ABORT, 'asset_activity_related_account_scope_invalid') END;

  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM current_asset_revision asset
    WHERE asset.asset_id = NEW.asset_id
      AND asset.asset_type != 'cash'
      AND asset.status = 'active'
  ) THEN RAISE(ABORT, 'asset_activity_asset_invalid') END;

  SELECT CASE WHEN NEW.source_asset_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM current_asset_revision asset
    WHERE asset.asset_id = NEW.source_asset_id
      AND asset.asset_type != 'cash'
  ) THEN RAISE(ABORT, 'asset_activity_source_asset_invalid') END;

  SELECT CASE WHEN NEW.event_type = 'reward' AND NOT EXISTS (
    SELECT 1 FROM current_asset_revision asset
    WHERE asset.asset_id = NEW.asset_id
      AND asset.asset_type = 'crypto'
  ) THEN RAISE(ABORT, 'asset_activity_reward_asset_invalid') END;
END;

CREATE TABLE asset_activity_generic_derivative_capability (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  capability_name TEXT NOT NULL UNIQUE CHECK (capability_name = 'generic_derivative_activity_v1'),
  semantic_contract TEXT NOT NULL CHECK (semantic_contract = 'asset_activity_v1'),
  source_schema_version INTEGER NOT NULL CHECK (source_schema_version = 401),
  lifecycle_events_inferred INTEGER NOT NULL CHECK (lifecycle_events_inferred = 0),
  automatic_cash_postings INTEGER NOT NULL CHECK (automatic_cash_postings = 0)
) STRICT;

INSERT INTO asset_activity_generic_derivative_capability
VALUES(1, 'generic_derivative_activity_v1', 'asset_activity_v1', 401, 0, 0);

CREATE TRIGGER asset_activity_generic_derivative_capability_no_update
BEFORE UPDATE ON asset_activity_generic_derivative_capability
BEGIN
  SELECT RAISE(ABORT, 'asset_activity_generic_derivative_capability_immutable');
END;

CREATE TRIGGER asset_activity_generic_derivative_capability_no_delete
BEFORE DELETE ON asset_activity_generic_derivative_capability
BEGIN
  SELECT RAISE(ABORT, 'asset_activity_generic_derivative_capability_immutable');
END;

COMMIT;
