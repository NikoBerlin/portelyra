PRAGMA foreign_keys = OFF;
PRAGMA legacy_alter_table = ON;

BEGIN IMMEDIATE;

CREATE TEMP TABLE portfolio_ledger_v1_1_guard (
  valid INTEGER NOT NULL CHECK (valid = 1)
) STRICT;

INSERT INTO portfolio_ledger_v1_1_guard(valid)
SELECT CASE WHEN
  (SELECT user_version FROM pragma_user_version) = 400
  AND NOT EXISTS (SELECT 1 FROM ledger_store_binding WHERE schema_version != 400)
  AND NOT EXISTS (
    SELECT 1 FROM sqlite_master
    WHERE type IN ('table', 'view')
      AND name IN ('asset_activity_event', 'current_asset_activity_event')
  )
THEN 1 ELSE 0 END;

DROP TABLE portfolio_ledger_v1_1_guard;

DROP TRIGGER ledger_binding_no_update;
DROP TRIGGER ledger_binding_no_delete;

ALTER TABLE ledger_store_binding RENAME TO ledger_store_binding_v400;

CREATE TABLE ledger_store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 401),
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 3 AND 64),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 3 AND 64),
  data_space_id TEXT NOT NULL CHECK (length(data_space_id) BETWEEN 3 AND 64),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z')
) STRICT;

INSERT INTO ledger_store_binding(singleton_id, schema_version, tenant_id, user_id, data_space_id, created_at_utc)
SELECT singleton_id, 401, tenant_id, user_id, data_space_id, created_at_utc
FROM ledger_store_binding_v400;

DROP TABLE ledger_store_binding_v400;

CREATE TRIGGER ledger_binding_no_update
BEFORE UPDATE ON ledger_store_binding
BEGIN
  SELECT RAISE(ABORT, 'ledger_binding_immutable');
END;

CREATE TRIGGER ledger_binding_no_delete
BEFORE DELETE ON ledger_store_binding
BEGIN
  SELECT RAISE(ABORT, 'ledger_binding_immutable');
END;

CREATE TABLE asset_activity_event (
  event_ref TEXT PRIMARY KEY CHECK (
    event_ref LIKE 'evt_%'
    AND length(event_ref) BETWEEN 8 AND 64
    AND event_ref NOT GLOB '*[^a-z0-9_]*'
  ),
  portfolio_id TEXT NOT NULL REFERENCES portfolio_entity(portfolio_id),
  account_id TEXT NOT NULL REFERENCES account_entity(account_id),
  related_account_id TEXT REFERENCES account_entity(account_id),
  asset_id TEXT NOT NULL REFERENCES asset_entity(asset_id),
  source_asset_id TEXT REFERENCES asset_entity(asset_id),
  event_type TEXT NOT NULL CHECK (
    event_type IN ('buy', 'sell', 'dividend', 'stock_dividend', 'reward', 'deposit', 'withdrawal', 'transfer')
  ),
  event_time_evidence TEXT NOT NULL CHECK (event_time_evidence IN ('exact', 'date_only')),
  local_date TEXT NOT NULL CHECK (length(local_date) = 10 AND substr(local_date, 5, 1) = '-' AND substr(local_date, 8, 1) = '-'),
  local_time TEXT CHECK (local_time IS NULL OR (length(local_time) = 8 AND substr(local_time, 3, 1) = ':' AND substr(local_time, 6, 1) = ':')),
  time_zone TEXT NOT NULL CHECK (length(trim(time_zone)) BETWEEN 1 AND 80),
  effective_at_utc TEXT CHECK (effective_at_utc IS NULL OR (length(effective_at_utc) = 20 AND substr(effective_at_utc, 11, 1) = 'T' AND substr(effective_at_utc, 20, 1) = 'Z')),
  original_acquired_time_evidence TEXT NOT NULL CHECK (original_acquired_time_evidence IN ('exact', 'date_only', 'not_applicable')),
  original_acquired_local_date TEXT CHECK (original_acquired_local_date IS NULL OR (length(original_acquired_local_date) = 10 AND substr(original_acquired_local_date, 5, 1) = '-' AND substr(original_acquired_local_date, 8, 1) = '-')),
  original_acquired_local_time TEXT CHECK (original_acquired_local_time IS NULL OR (length(original_acquired_local_time) = 8 AND substr(original_acquired_local_time, 3, 1) = ':' AND substr(original_acquired_local_time, 6, 1) = ':')),
  original_acquired_time_zone TEXT CHECK (original_acquired_time_zone IS NULL OR length(trim(original_acquired_time_zone)) BETWEEN 1 AND 80),
  original_acquired_at_utc TEXT CHECK (original_acquired_at_utc IS NULL OR (length(original_acquired_at_utc) = 20 AND substr(original_acquired_at_utc, 11, 1) = 'T' AND substr(original_acquired_at_utc, 20, 1) = 'Z')),
  amount_input_mode TEXT NOT NULL CHECK (amount_input_mode IN ('quantity_unit_price', 'gross_total', 'not_applicable')),
  basis_evidence_mode TEXT NOT NULL CHECK (basis_evidence_mode IN ('derived_trade', 'valuation_confirmed_as_basis', 'provided_basis', 'basis_missing', 'not_applicable')),
  quantity_decimal TEXT,
  eligible_quantity_decimal TEXT,
  unit_price_decimal TEXT,
  gross_amount_decimal TEXT,
  monetary_fee_decimal TEXT,
  asset_fee_quantity_decimal TEXT,
  provided_basis_decimal TEXT,
  movement_context_code TEXT NOT NULL CHECK (movement_context_code IN ('not_applicable', 'unclassified', 'gift', 'inheritance', 'debt_settlement', 'donation', 'payment', 'custody_exit', 'other')),
  basis_currency TEXT NOT NULL CHECK (length(basis_currency) = 3 AND basis_currency = upper(basis_currency) AND basis_currency NOT GLOB '*[^A-Z]*'),
  inventory_effect_code TEXT NOT NULL CHECK (inventory_effect_code IN ('increase', 'decrease', 'preserve', 'none')),
  fifo_effect_code TEXT NOT NULL CHECK (fifo_effect_code IN ('create_lot', 'consume_fifo', 'none', 'create_lot_then_consume_fee', 'create_carried_lot', 'consume_fifo_and_emit_receipt', 'carry_lots_then_consume_fee')),
  portfolio_quantity_change_decimal TEXT NOT NULL,
  gross_economic_amount_decimal TEXT,
  fifo_basis_created_decimal TEXT,
  net_trade_proceeds_decimal TEXT,
  gross_income_decimal TEXT,
  distribution_value_decimal TEXT,
  income_recognition_status TEXT NOT NULL CHECK (income_recognition_status IN ('not_applicable', 'recognized_dividend_income', 'recognized_reward_income', 'tax_classification_required')),
  outgoing_lot_receipt_required INTEGER NOT NULL CHECK (outgoing_lot_receipt_required IN (0, 1)),
  transfer_lot_carry_required INTEGER NOT NULL CHECK (transfer_lot_carry_required IN (0, 1)),
  original_acquisition_evidence_required INTEGER NOT NULL CHECK (original_acquisition_evidence_required IN (0, 1)),
  cash_posting_created INTEGER NOT NULL CHECK (cash_posting_created = 0),
  tax_classification_inferred INTEGER NOT NULL CHECK (tax_classification_inferred = 0),
  provider_price_used INTEGER NOT NULL CHECK (provider_price_used = 0),
  memo TEXT CHECK (memo IS NULL OR length(memo) <= 4000),
  origin_type TEXT NOT NULL CHECK (origin_type IN ('native', 'legacy_conversion')),
  source_row_fingerprint TEXT UNIQUE CHECK (source_row_fingerprint IS NULL OR (length(source_row_fingerprint) = 64 AND source_row_fingerprint NOT GLOB '*[^a-f0-9]*')),
  effect_fingerprint TEXT NOT NULL CHECK (length(effect_fingerprint) = 64 AND effect_fingerprint NOT GLOB '*[^a-f0-9]*'),
  semantic_contract TEXT NOT NULL CHECK (semantic_contract = 'asset_activity_v1'),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  CHECK ((event_time_evidence = 'exact' AND local_time IS NOT NULL AND effective_at_utc IS NOT NULL) OR (event_time_evidence = 'date_only' AND local_time IS NULL AND effective_at_utc IS NULL)),
  CHECK (
    (original_acquired_time_evidence = 'not_applicable' AND original_acquired_local_date IS NULL AND original_acquired_local_time IS NULL AND original_acquired_time_zone IS NULL AND original_acquired_at_utc IS NULL)
    OR
    (original_acquired_time_evidence = 'date_only' AND original_acquired_local_date IS NOT NULL AND original_acquired_local_time IS NULL AND original_acquired_time_zone IS NOT NULL AND original_acquired_at_utc IS NULL)
    OR
    (original_acquired_time_evidence = 'exact' AND original_acquired_local_date IS NOT NULL AND original_acquired_local_time IS NOT NULL AND original_acquired_time_zone IS NOT NULL AND original_acquired_at_utc IS NOT NULL)
  ),
  CHECK ((event_type = 'transfer' AND related_account_id IS NOT NULL AND related_account_id != account_id) OR (event_type != 'transfer' AND related_account_id IS NULL)),
  CHECK ((event_type = 'stock_dividend' AND source_asset_id IS NOT NULL) OR (event_type != 'stock_dividend' AND source_asset_id IS NULL)),
  CHECK ((origin_type = 'native' AND source_row_fingerprint IS NULL) OR (origin_type = 'legacy_conversion' AND source_row_fingerprint IS NOT NULL)),
  CHECK (quantity_decimal IS NULL OR (
    typeof(quantity_decimal) = 'text' AND length(quantity_decimal) BETWEEN 1 AND 80
    AND quantity_decimal NOT GLOB '*[^0-9.]*' AND quantity_decimal NOT IN ('', '.', '0')
    AND (length(quantity_decimal) - length(replace(quantity_decimal, '.', ''))) <= 1
    AND (instr(quantity_decimal, '.') = 0 OR (substr(quantity_decimal, -1, 1) NOT IN ('.', '0') AND instr(quantity_decimal, '.') > 1))
    AND (quantity_decimal LIKE '0.%' OR substr(quantity_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (eligible_quantity_decimal IS NULL OR (
    typeof(eligible_quantity_decimal) = 'text' AND length(eligible_quantity_decimal) BETWEEN 1 AND 80
    AND eligible_quantity_decimal NOT GLOB '*[^0-9.]*' AND eligible_quantity_decimal NOT IN ('', '.', '0')
    AND (length(eligible_quantity_decimal) - length(replace(eligible_quantity_decimal, '.', ''))) <= 1
    AND (instr(eligible_quantity_decimal, '.') = 0 OR (substr(eligible_quantity_decimal, -1, 1) NOT IN ('.', '0') AND instr(eligible_quantity_decimal, '.') > 1))
    AND (eligible_quantity_decimal LIKE '0.%' OR substr(eligible_quantity_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (unit_price_decimal IS NULL OR (
    typeof(unit_price_decimal) = 'text' AND length(unit_price_decimal) BETWEEN 1 AND 80
    AND unit_price_decimal NOT GLOB '*[^0-9.]*' AND unit_price_decimal NOT IN ('', '.', '0')
    AND (length(unit_price_decimal) - length(replace(unit_price_decimal, '.', ''))) <= 1
    AND (instr(unit_price_decimal, '.') = 0 OR (substr(unit_price_decimal, -1, 1) NOT IN ('.', '0') AND instr(unit_price_decimal, '.') > 1))
    AND (unit_price_decimal LIKE '0.%' OR substr(unit_price_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (gross_amount_decimal IS NULL OR (
    typeof(gross_amount_decimal) = 'text' AND length(gross_amount_decimal) BETWEEN 1 AND 80
    AND gross_amount_decimal NOT GLOB '*[^0-9.]*' AND gross_amount_decimal NOT IN ('', '.', '0')
    AND (length(gross_amount_decimal) - length(replace(gross_amount_decimal, '.', ''))) <= 1
    AND (instr(gross_amount_decimal, '.') = 0 OR (substr(gross_amount_decimal, -1, 1) NOT IN ('.', '0') AND instr(gross_amount_decimal, '.') > 1))
    AND (gross_amount_decimal LIKE '0.%' OR substr(gross_amount_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (monetary_fee_decimal IS NULL OR (
    typeof(monetary_fee_decimal) = 'text' AND length(monetary_fee_decimal) BETWEEN 1 AND 80
    AND monetary_fee_decimal NOT GLOB '*[^0-9.]*' AND monetary_fee_decimal NOT IN ('', '.', '0')
    AND (length(monetary_fee_decimal) - length(replace(monetary_fee_decimal, '.', ''))) <= 1
    AND (instr(monetary_fee_decimal, '.') = 0 OR (substr(monetary_fee_decimal, -1, 1) NOT IN ('.', '0') AND instr(monetary_fee_decimal, '.') > 1))
    AND (monetary_fee_decimal LIKE '0.%' OR substr(monetary_fee_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (asset_fee_quantity_decimal IS NULL OR (
    typeof(asset_fee_quantity_decimal) = 'text' AND length(asset_fee_quantity_decimal) BETWEEN 1 AND 80
    AND asset_fee_quantity_decimal NOT GLOB '*[^0-9.]*' AND asset_fee_quantity_decimal NOT IN ('', '.', '0')
    AND (length(asset_fee_quantity_decimal) - length(replace(asset_fee_quantity_decimal, '.', ''))) <= 1
    AND (instr(asset_fee_quantity_decimal, '.') = 0 OR (substr(asset_fee_quantity_decimal, -1, 1) NOT IN ('.', '0') AND instr(asset_fee_quantity_decimal, '.') > 1))
    AND (asset_fee_quantity_decimal LIKE '0.%' OR substr(asset_fee_quantity_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (provided_basis_decimal IS NULL OR (
    typeof(provided_basis_decimal) = 'text' AND length(provided_basis_decimal) BETWEEN 1 AND 80
    AND provided_basis_decimal NOT GLOB '*[^0-9.]*' AND provided_basis_decimal NOT IN ('', '.', '0')
    AND (length(provided_basis_decimal) - length(replace(provided_basis_decimal, '.', ''))) <= 1
    AND (instr(provided_basis_decimal, '.') = 0 OR (substr(provided_basis_decimal, -1, 1) NOT IN ('.', '0') AND instr(provided_basis_decimal, '.') > 1))
    AND (provided_basis_decimal LIKE '0.%' OR substr(provided_basis_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (gross_economic_amount_decimal IS NULL OR (
    typeof(gross_economic_amount_decimal) = 'text' AND length(gross_economic_amount_decimal) BETWEEN 1 AND 80
    AND gross_economic_amount_decimal NOT GLOB '*[^0-9.]*' AND gross_economic_amount_decimal NOT IN ('', '.', '0')
    AND (length(gross_economic_amount_decimal) - length(replace(gross_economic_amount_decimal, '.', ''))) <= 1
    AND (instr(gross_economic_amount_decimal, '.') = 0 OR (substr(gross_economic_amount_decimal, -1, 1) NOT IN ('.', '0') AND instr(gross_economic_amount_decimal, '.') > 1))
    AND (gross_economic_amount_decimal LIKE '0.%' OR substr(gross_economic_amount_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (fifo_basis_created_decimal IS NULL OR (
    typeof(fifo_basis_created_decimal) = 'text' AND length(fifo_basis_created_decimal) BETWEEN 1 AND 80
    AND fifo_basis_created_decimal NOT GLOB '*[^0-9.]*' AND fifo_basis_created_decimal NOT IN ('', '.', '0')
    AND (length(fifo_basis_created_decimal) - length(replace(fifo_basis_created_decimal, '.', ''))) <= 1
    AND (instr(fifo_basis_created_decimal, '.') = 0 OR (substr(fifo_basis_created_decimal, -1, 1) NOT IN ('.', '0') AND instr(fifo_basis_created_decimal, '.') > 1))
    AND (fifo_basis_created_decimal LIKE '0.%' OR substr(fifo_basis_created_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (net_trade_proceeds_decimal IS NULL OR (
    typeof(net_trade_proceeds_decimal) = 'text' AND length(net_trade_proceeds_decimal) BETWEEN 1 AND 80
    AND net_trade_proceeds_decimal NOT GLOB '*[^0-9.]*' AND net_trade_proceeds_decimal NOT IN ('', '.', '0')
    AND (length(net_trade_proceeds_decimal) - length(replace(net_trade_proceeds_decimal, '.', ''))) <= 1
    AND (instr(net_trade_proceeds_decimal, '.') = 0 OR (substr(net_trade_proceeds_decimal, -1, 1) NOT IN ('.', '0') AND instr(net_trade_proceeds_decimal, '.') > 1))
    AND (net_trade_proceeds_decimal LIKE '0.%' OR substr(net_trade_proceeds_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (gross_income_decimal IS NULL OR (
    typeof(gross_income_decimal) = 'text' AND length(gross_income_decimal) BETWEEN 1 AND 80
    AND gross_income_decimal NOT GLOB '*[^0-9.]*' AND gross_income_decimal NOT IN ('', '.', '0')
    AND (length(gross_income_decimal) - length(replace(gross_income_decimal, '.', ''))) <= 1
    AND (instr(gross_income_decimal, '.') = 0 OR (substr(gross_income_decimal, -1, 1) NOT IN ('.', '0') AND instr(gross_income_decimal, '.') > 1))
    AND (gross_income_decimal LIKE '0.%' OR substr(gross_income_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (distribution_value_decimal IS NULL OR (
    typeof(distribution_value_decimal) = 'text' AND length(distribution_value_decimal) BETWEEN 1 AND 80
    AND distribution_value_decimal NOT GLOB '*[^0-9.]*' AND distribution_value_decimal NOT IN ('', '.', '0')
    AND (length(distribution_value_decimal) - length(replace(distribution_value_decimal, '.', ''))) <= 1
    AND (instr(distribution_value_decimal, '.') = 0 OR (substr(distribution_value_decimal, -1, 1) NOT IN ('.', '0') AND instr(distribution_value_decimal, '.') > 1))
    AND (distribution_value_decimal LIKE '0.%' OR substr(distribution_value_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (portfolio_quantity_change_decimal = '0' OR (
    typeof(portfolio_quantity_change_decimal) = 'text' AND length(portfolio_quantity_change_decimal) BETWEEN 1 AND 80
    AND portfolio_quantity_change_decimal NOT GLOB '*[^0-9.-]*' AND portfolio_quantity_change_decimal NOT IN ('', '-', '.', '-.', '-0')
    AND instr(substr(portfolio_quantity_change_decimal, 2), '-') = 0
    AND (length(portfolio_quantity_change_decimal) - length(replace(portfolio_quantity_change_decimal, '.', ''))) <= 1
    AND (instr(portfolio_quantity_change_decimal, '.') = 0 OR (substr(portfolio_quantity_change_decimal, -1, 1) NOT IN ('.', '0') AND instr(portfolio_quantity_change_decimal, '.') > CASE WHEN substr(portfolio_quantity_change_decimal, 1, 1) = '-' THEN 2 ELSE 1 END))
    AND (ltrim(portfolio_quantity_change_decimal, '-') LIKE '0.%' OR substr(ltrim(portfolio_quantity_change_decimal, '-'), 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK ((amount_input_mode = 'quantity_unit_price' AND unit_price_decimal IS NOT NULL AND gross_amount_decimal IS NULL) OR (amount_input_mode = 'gross_total' AND unit_price_decimal IS NULL AND gross_amount_decimal IS NOT NULL) OR (amount_input_mode = 'not_applicable' AND unit_price_decimal IS NULL AND gross_amount_decimal IS NULL)),
  CHECK ((event_type = 'dividend' AND quantity_decimal IS NULL AND eligible_quantity_decimal IS NOT NULL) OR (event_type != 'dividend' AND eligible_quantity_decimal IS NULL)),
  CHECK ((event_type IN ('buy', 'sell', 'stock_dividend', 'reward', 'deposit', 'withdrawal', 'transfer') AND quantity_decimal IS NOT NULL) OR event_type = 'dividend'),
  CHECK ((event_type = 'deposit' AND original_acquired_time_evidence != 'not_applicable' AND movement_context_code != 'not_applicable') OR event_type != 'deposit'),
  CHECK ((event_type = 'withdrawal' AND movement_context_code != 'not_applicable' AND outgoing_lot_receipt_required = 1) OR event_type != 'withdrawal'),
  CHECK ((event_type = 'transfer' AND transfer_lot_carry_required = 1) OR event_type != 'transfer')
) STRICT;

CREATE INDEX asset_activity_portfolio_order
ON asset_activity_event(portfolio_id, local_date, COALESCE(effective_at_utc, ''), event_ref);

CREATE TABLE asset_activity_command_receipt (
  command_id TEXT PRIMARY KEY REFERENCES ledger_command_receipt(command_id),
  action_type TEXT NOT NULL CHECK (action_type IN ('asset_activity_create_v1', 'per_asset_legacy_cutover_v1')),
  preview_fingerprint TEXT NOT NULL CHECK (length(preview_fingerprint) = 64 AND preview_fingerprint NOT GLOB '*[^a-f0-9]*'),
  confirmation_fingerprint TEXT NOT NULL UNIQUE CHECK (length(confirmation_fingerprint) = 64 AND confirmation_fingerprint NOT GLOB '*[^a-f0-9]*'),
  event_count INTEGER NOT NULL CHECK (event_count > 0),
  plan_fingerprint TEXT CHECK (plan_fingerprint IS NULL OR (length(plan_fingerprint) = 64 AND plan_fingerprint NOT GLOB '*[^a-f0-9]*')),
  projection_fingerprint TEXT CHECK (projection_fingerprint IS NULL OR (length(projection_fingerprint) = 64 AND projection_fingerprint NOT GLOB '*[^a-f0-9]*')),
  source_asset_link_fingerprint TEXT CHECK (source_asset_link_fingerprint IS NULL OR (length(source_asset_link_fingerprint) = 64 AND source_asset_link_fingerprint NOT GLOB '*[^a-f0-9]*')),
  fifo_reconciliation_fingerprint TEXT CHECK (fifo_reconciliation_fingerprint IS NULL OR (length(fifo_reconciliation_fingerprint) = 64 AND fifo_reconciliation_fingerprint NOT GLOB '*[^a-f0-9]*')),
  source_row_count INTEGER CHECK (source_row_count IS NULL OR source_row_count > 0),
  receipt_fingerprint TEXT NOT NULL UNIQUE CHECK (length(receipt_fingerprint) = 64 AND receipt_fingerprint NOT GLOB '*[^a-f0-9]*'),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc) = 20 AND substr(committed_at_utc, 11, 1) = 'T' AND substr(committed_at_utc, 20, 1) = 'Z'),
  CHECK (
    (action_type = 'asset_activity_create_v1' AND plan_fingerprint IS NULL AND projection_fingerprint IS NULL AND source_asset_link_fingerprint IS NULL AND fifo_reconciliation_fingerprint IS NULL AND source_row_count IS NULL)
    OR
    (action_type = 'per_asset_legacy_cutover_v1' AND plan_fingerprint IS NOT NULL AND projection_fingerprint IS NOT NULL AND source_asset_link_fingerprint IS NOT NULL AND fifo_reconciliation_fingerprint IS NOT NULL AND source_row_count = event_count)
  )
) STRICT;

CREATE VIEW current_asset_activity_event AS
SELECT event.*
FROM asset_activity_event event;

CREATE VIEW compatible_ledger_event AS
SELECT
  'portfolio_ledger_v1_transaction_fact' AS semantic_contract,
  transaction_row.transaction_id AS fact_ref,
  transaction_row.portfolio_id,
  transaction_row.account_id,
  transaction_row.related_account_id,
  transaction_row.asset_id,
  transaction_row.event_type,
  'exact' AS event_time_evidence,
  transaction_row.local_date,
  substr(transaction_row.effective_at_utc, 12, 8) AS local_time,
  transaction_row.effective_at_utc,
  transaction_row.quantity_decimal,
  transaction_row.unit_price_decimal,
  transaction_row.gross_amount_decimal,
  transaction_row.fee_decimal AS monetary_fee_decimal,
  NULL AS asset_fee_quantity_decimal,
  transaction_row.transaction_currency AS basis_currency,
  1 AS coupled_transaction_fact,
  NULL AS automatic_cash_posting_created,
  transaction_row.command_id,
  transaction_row.created_at_utc
FROM current_transaction_fact transaction_row
UNION ALL
SELECT
  event.semantic_contract,
  event.event_ref,
  event.portfolio_id,
  event.account_id,
  event.related_account_id,
  event.asset_id,
  event.event_type,
  event.event_time_evidence,
  event.local_date,
  event.local_time,
  event.effective_at_utc,
  event.quantity_decimal,
  event.unit_price_decimal,
  event.gross_amount_decimal,
  event.monetary_fee_decimal,
  event.asset_fee_quantity_decimal,
  event.basis_currency,
  0 AS coupled_transaction_fact,
  event.cash_posting_created,
  event.command_id,
  event.created_at_utc
FROM current_asset_activity_event event;

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
      AND asset.asset_type NOT IN ('cash', 'derivative')
      AND asset.status = 'active'
  ) THEN RAISE(ABORT, 'asset_activity_asset_invalid') END;

  SELECT CASE WHEN NEW.source_asset_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM current_asset_revision asset
    WHERE asset.asset_id = NEW.source_asset_id
      AND asset.asset_type NOT IN ('cash', 'derivative')
  ) THEN RAISE(ABORT, 'asset_activity_source_asset_invalid') END;

  SELECT CASE WHEN NEW.event_type = 'reward' AND NOT EXISTS (
    SELECT 1 FROM current_asset_revision asset
    WHERE asset.asset_id = NEW.asset_id
      AND asset.asset_type = 'crypto'
  ) THEN RAISE(ABORT, 'asset_activity_reward_asset_invalid') END;
END;

CREATE TRIGGER asset_activity_command_receipt_validate
BEFORE INSERT ON asset_activity_command_receipt
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM ledger_command_receipt receipt
    WHERE receipt.command_id = NEW.command_id
      AND receipt.writer_area = 'data_app'
      AND receipt.action_type = NEW.action_type
      AND receipt.payload_fingerprint = NEW.preview_fingerprint
      AND receipt.confirmation_fingerprint = NEW.confirmation_fingerprint
      AND receipt.committed_at_utc = NEW.committed_at_utc
  ) THEN RAISE(ABORT, 'asset_activity_receipt_command_invalid') END;

  SELECT CASE WHEN NEW.event_count != (
    SELECT count(*) FROM asset_activity_event event
    WHERE event.command_id = NEW.command_id
      AND event.cash_posting_created = 0
      AND event.provider_price_used = 0
      AND event.tax_classification_inferred = 0
  ) THEN RAISE(ABORT, 'asset_activity_receipt_event_count_invalid') END;

  SELECT CASE WHEN NEW.action_type = 'per_asset_legacy_cutover_v1' AND NEW.source_row_count != (
    SELECT count(*) FROM asset_activity_event event
    WHERE event.command_id = NEW.command_id
      AND event.origin_type = 'legacy_conversion'
      AND event.source_row_fingerprint IS NOT NULL
  ) THEN RAISE(ABORT, 'asset_activity_receipt_source_count_invalid') END;
END;

CREATE TRIGGER asset_activity_command_receipt_no_update
BEFORE UPDATE ON asset_activity_command_receipt
BEGIN
  SELECT RAISE(ABORT, 'asset_activity_command_receipt_immutable');
END;

CREATE TRIGGER asset_activity_command_receipt_no_delete
BEFORE DELETE ON asset_activity_command_receipt
BEGIN
  SELECT RAISE(ABORT, 'asset_activity_command_receipt_immutable');
END;

CREATE TRIGGER asset_activity_event_no_update
BEFORE UPDATE ON asset_activity_event
BEGIN
  SELECT RAISE(ABORT, 'asset_activity_event_immutable');
END;

CREATE TRIGGER asset_activity_event_no_delete
BEFORE DELETE ON asset_activity_event
BEGIN
  SELECT RAISE(ABORT, 'asset_activity_event_immutable');
END;

PRAGMA user_version = 401;

COMMIT;

PRAGMA legacy_alter_table = OFF;
PRAGMA foreign_keys = ON;
