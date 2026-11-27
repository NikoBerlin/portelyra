PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;
PRAGMA user_version = 2;

CREATE TABLE store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 2),
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 3 AND 64 AND tenant_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 3 AND 64 AND user_id NOT GLOB '*[^A-Za-z0-9_-]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z')
) STRICT;

CREATE TABLE portfolio (
  portfolio_id TEXT PRIMARY KEY CHECK (portfolio_id LIKE 'ptf_%' AND length(portfolio_id) BETWEEN 8 AND 64 AND portfolio_id NOT GLOB '*[^a-z0-9_]*'),
  display_name TEXT NOT NULL COLLATE NOCASE CHECK (length(trim(display_name)) BETWEEN 1 AND 120),
  base_currency TEXT NOT NULL CHECK (length(base_currency) = 3 AND base_currency = upper(base_currency) AND base_currency NOT GLOB '*[^A-Z]*'),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  origin_type TEXT NOT NULL DEFAULT 'native' CHECK (origin_type IN ('native', 'legacy_import')),
  origin_ref TEXT,
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc) = 20 AND substr(updated_at_utc, 11, 1) = 'T' AND substr(updated_at_utc, 20, 1) = 'Z'),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  CHECK ((origin_type = 'native' AND origin_ref IS NULL) OR (origin_type = 'legacy_import' AND length(trim(origin_ref)) > 0)),
  UNIQUE (display_name)
) STRICT;

CREATE TABLE account (
  account_id TEXT PRIMARY KEY CHECK (account_id LIKE 'acc_%' AND length(account_id) BETWEEN 8 AND 64 AND account_id NOT GLOB '*[^a-z0-9_]*'),
  portfolio_id TEXT NOT NULL REFERENCES portfolio(portfolio_id),
  display_name TEXT NOT NULL COLLATE NOCASE CHECK (length(trim(display_name)) BETWEEN 1 AND 120),
  account_type TEXT NOT NULL CHECK (account_type IN ('securities', 'cash', 'bank', 'crypto_wallet', 'external', 'other')),
  institution_label TEXT CHECK (institution_label IS NULL OR length(trim(institution_label)) BETWEEN 1 AND 120),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  origin_type TEXT NOT NULL DEFAULT 'native' CHECK (origin_type IN ('native', 'legacy_import')),
  origin_ref TEXT,
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc) = 20 AND substr(updated_at_utc, 11, 1) = 'T' AND substr(updated_at_utc, 20, 1) = 'Z'),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  CHECK ((origin_type = 'native' AND origin_ref IS NULL) OR (origin_type = 'legacy_import' AND length(trim(origin_ref)) > 0)),
  UNIQUE (portfolio_id, display_name)
) STRICT;

CREATE TABLE asset (
  asset_id TEXT PRIMARY KEY CHECK (asset_id LIKE 'ast_%' AND length(asset_id) BETWEEN 8 AND 64 AND asset_id NOT GLOB '*[^a-z0-9_]*'),
  display_name TEXT NOT NULL COLLATE NOCASE CHECK (length(trim(display_name)) BETWEEN 1 AND 160),
  asset_type TEXT NOT NULL CHECK (asset_type IN ('equity', 'etf', 'fund', 'bond', 'crypto', 'commodity', 'cash', 'fx', 'index', 'other')),
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

CREATE UNIQUE INDEX asset_isin_unique ON asset(isin) WHERE isin IS NOT NULL;

CREATE TABLE provider_mapping (
  mapping_id TEXT PRIMARY KEY CHECK (mapping_id LIKE 'map_%' AND length(mapping_id) BETWEEN 8 AND 64 AND mapping_id NOT GLOB '*[^a-z0-9_]*'),
  asset_id TEXT NOT NULL REFERENCES asset(asset_id),
  capability TEXT NOT NULL CHECK (capability IN ('daily_history', 'quote', 'intraday', 'fundamentals', 'fx')),
  provider_id TEXT NOT NULL CHECK (
    length(trim(provider_id)) BETWEEN 2 AND 64
    AND provider_id = lower(provider_id)
    AND provider_id NOT GLOB '*[^a-z0-9_]*'
    AND lower(provider_id) NOT IN ('fmp', 'financial_modeling_prep', 'financialmodelingprep')
  ),
  provider_symbol TEXT NOT NULL CHECK (length(trim(provider_symbol)) BETWEEN 1 AND 120),
  exchange_code TEXT,
  mic_code TEXT CHECK (mic_code IS NULL OR (length(mic_code) = 4 AND mic_code = upper(mic_code) AND mic_code NOT GLOB '*[^A-Z0-9]*')),
  provider_currency TEXT NOT NULL CHECK (length(provider_currency) = 3 AND provider_currency = upper(provider_currency) AND provider_currency NOT GLOB '*[^A-Z]*'),
  verification_status TEXT NOT NULL DEFAULT 'unverified' CHECK (verification_status IN ('unverified', 'verified', 'disabled')),
  expert_only INTEGER NOT NULL DEFAULT 0 CHECK (expert_only IN (0, 1)),
  enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
  verified_at_utc TEXT CHECK (verified_at_utc IS NULL OR (length(verified_at_utc) = 20 AND substr(verified_at_utc, 11, 1) = 'T' AND substr(verified_at_utc, 20, 1) = 'Z')),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc) = 20 AND substr(updated_at_utc, 11, 1) = 'T' AND substr(updated_at_utc, 20, 1) = 'Z'),
  revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
  CHECK ((verification_status = 'verified' AND verified_at_utc IS NOT NULL) OR verification_status != 'verified'),
  CHECK (lower(provider_id) != 'twelve_data' OR (expert_only = 1 AND enabled = 0)),
  UNIQUE (asset_id, capability, provider_id)
) STRICT;

CREATE TABLE transaction_record (
  transaction_id TEXT PRIMARY KEY CHECK (transaction_id LIKE 'txn_%' AND length(transaction_id) BETWEEN 8 AND 64 AND transaction_id NOT GLOB '*[^a-z0-9_]*'),
  portfolio_id TEXT NOT NULL REFERENCES portfolio(portfolio_id),
  transaction_type TEXT NOT NULL CHECK (transaction_type IN ('buy', 'sell', 'transfer', 'deposit', 'withdrawal', 'dividend', 'interest', 'reward', 'fee', 'tax', 'split', 'adjustment', 'other')),
  record_action TEXT NOT NULL DEFAULT 'book' CHECK (record_action IN ('book', 'void')),
  effective_at_utc TEXT NOT NULL CHECK (length(effective_at_utc) = 20 AND substr(effective_at_utc, 11, 1) = 'T' AND substr(effective_at_utc, 20, 1) = 'Z'),
  local_date TEXT NOT NULL CHECK (length(local_date) = 10 AND substr(local_date, 5, 1) = '-' AND substr(local_date, 8, 1) = '-'),
  memo TEXT CHECK (memo IS NULL OR length(memo) <= 500),
  supersedes_transaction_id TEXT UNIQUE REFERENCES transaction_record(transaction_id),
  origin_type TEXT NOT NULL DEFAULT 'native' CHECK (origin_type IN ('native', 'legacy_import')),
  origin_ref TEXT,
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  created_by_actor TEXT NOT NULL CHECK (length(trim(created_by_actor)) BETWEEN 3 AND 80),
  CHECK (supersedes_transaction_id IS NULL OR supersedes_transaction_id != transaction_id),
  CHECK ((origin_type = 'native' AND origin_ref IS NULL) OR (origin_type = 'legacy_import' AND length(trim(origin_ref)) > 0))
) STRICT;

CREATE TABLE transaction_posting (
  posting_id TEXT PRIMARY KEY CHECK (posting_id LIKE 'pst_%' AND length(posting_id) BETWEEN 8 AND 64 AND posting_id NOT GLOB '*[^a-z0-9_]*'),
  transaction_id TEXT NOT NULL REFERENCES transaction_record(transaction_id),
  sequence_no INTEGER NOT NULL CHECK (sequence_no >= 1),
  account_id TEXT NOT NULL REFERENCES account(account_id),
  asset_id TEXT NOT NULL REFERENCES asset(asset_id),
  posting_role TEXT NOT NULL CHECK (posting_role IN ('asset', 'cash', 'fee', 'tax', 'income', 'transfer', 'valuation', 'other')),
  quantity_decimal TEXT NOT NULL CHECK (
    typeof(quantity_decimal) = 'text'
    AND length(quantity_decimal) BETWEEN 1 AND 80
    AND quantity_decimal NOT GLOB '*[^0-9.-]*'
    AND quantity_decimal NOT IN ('', '-', '.', '-.', '0', '-0')
    AND instr(substr(quantity_decimal, 2), '-') = 0
    AND (length(quantity_decimal) - length(replace(quantity_decimal, '.', ''))) <= 1
    AND (instr(quantity_decimal, '.') = 0 OR (substr(quantity_decimal, -1, 1) NOT IN ('.', '0') AND instr(quantity_decimal, '.') > CASE WHEN substr(quantity_decimal, 1, 1) = '-' THEN 2 ELSE 1 END))
    AND (ltrim(quantity_decimal, '-') = '0' OR ltrim(quantity_decimal, '-') LIKE '0.%' OR substr(ltrim(quantity_decimal, '-'), 1, 1) BETWEEN '1' AND '9')
  ),
  unit_price_decimal TEXT CHECK (
    unit_price_decimal IS NULL OR (
      typeof(unit_price_decimal) = 'text'
      AND length(unit_price_decimal) BETWEEN 1 AND 80
      AND unit_price_decimal NOT GLOB '*[^0-9.]*'
      AND unit_price_decimal NOT IN ('', '.', '0')
      AND (length(unit_price_decimal) - length(replace(unit_price_decimal, '.', ''))) <= 1
      AND (instr(unit_price_decimal, '.') = 0 OR (substr(unit_price_decimal, -1, 1) NOT IN ('.', '0') AND instr(unit_price_decimal, '.') > 1))
      AND (unit_price_decimal LIKE '0.%' OR substr(unit_price_decimal, 1, 1) BETWEEN '1' AND '9')
    )
  ),
  price_currency TEXT CHECK (price_currency IS NULL OR (length(price_currency) = 3 AND price_currency = upper(price_currency) AND price_currency NOT GLOB '*[^A-Z]*')),
  valuation_amount_decimal TEXT CHECK (
    valuation_amount_decimal IS NULL OR (
      typeof(valuation_amount_decimal) = 'text'
      AND length(valuation_amount_decimal) BETWEEN 1 AND 80
      AND valuation_amount_decimal NOT GLOB '*[^0-9.-]*'
      AND valuation_amount_decimal NOT IN ('', '-', '.', '-.', '-0')
      AND instr(substr(valuation_amount_decimal, 2), '-') = 0
      AND (length(valuation_amount_decimal) - length(replace(valuation_amount_decimal, '.', ''))) <= 1
      AND (instr(valuation_amount_decimal, '.') = 0 OR (substr(valuation_amount_decimal, -1, 1) NOT IN ('.', '0') AND instr(valuation_amount_decimal, '.') > CASE WHEN substr(valuation_amount_decimal, 1, 1) = '-' THEN 2 ELSE 1 END))
      AND (ltrim(valuation_amount_decimal, '-') = '0' OR ltrim(valuation_amount_decimal, '-') LIKE '0.%' OR substr(ltrim(valuation_amount_decimal, '-'), 1, 1) BETWEEN '1' AND '9')
    )
  ),
  valuation_currency TEXT CHECK (valuation_currency IS NULL OR (length(valuation_currency) = 3 AND valuation_currency = upper(valuation_currency) AND valuation_currency NOT GLOB '*[^A-Z]*')),
  memo TEXT CHECK (memo IS NULL OR length(memo) <= 500),
  CHECK ((unit_price_decimal IS NULL) = (price_currency IS NULL)),
  CHECK ((valuation_amount_decimal IS NULL) = (valuation_currency IS NULL)),
  UNIQUE (transaction_id, sequence_no)
) STRICT;

CREATE TABLE transaction_seal (
  transaction_id TEXT PRIMARY KEY REFERENCES transaction_record(transaction_id),
  sealed_at_utc TEXT NOT NULL CHECK (length(sealed_at_utc) = 20 AND substr(sealed_at_utc, 11, 1) = 'T' AND substr(sealed_at_utc, 20, 1) = 'Z'),
  posting_count INTEGER NOT NULL CHECK (posting_count >= 0),
  content_fingerprint TEXT NOT NULL CHECK (length(content_fingerprint) = 64 AND content_fingerprint = lower(content_fingerprint) AND content_fingerprint NOT GLOB '*[^a-f0-9]*')
) STRICT;

CREATE TABLE data_command_audit (
  command_id TEXT PRIMARY KEY CHECK (command_id LIKE 'cmd_%' AND length(command_id) BETWEEN 8 AND 64 AND command_id NOT GLOB '*[^a-z0-9_]*'),
  area_id TEXT NOT NULL CHECK (area_id IN ('portfolio_catalog', 'account_catalog', 'asset_catalog', 'provider_mapping', 'transaction_ledger')),
  command_type TEXT NOT NULL CHECK (length(trim(command_type)) BETWEEN 3 AND 80),
  entity_id TEXT NOT NULL CHECK (length(trim(entity_id)) BETWEEN 8 AND 64),
  actor_id TEXT NOT NULL CHECK (length(trim(actor_id)) BETWEEN 3 AND 80),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc) = 20 AND substr(committed_at_utc, 11, 1) = 'T' AND substr(committed_at_utc, 20, 1) = 'Z'),
  payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64 AND payload_fingerprint = lower(payload_fingerprint) AND payload_fingerprint NOT GLOB '*[^a-f0-9]*'),
  origin_type TEXT NOT NULL DEFAULT 'native' CHECK (origin_type IN ('native', 'legacy_import')),
  origin_ref TEXT,
  CHECK ((origin_type = 'native' AND origin_ref IS NULL) OR (origin_type = 'legacy_import' AND length(trim(origin_ref)) > 0))
) STRICT;

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

CREATE TRIGGER portfolio_no_delete
BEFORE DELETE ON portfolio
BEGIN
  SELECT RAISE(ABORT, 'portfolio_must_be_archived_not_deleted');
END;

CREATE TRIGGER account_no_delete
BEFORE DELETE ON account
BEGIN
  SELECT RAISE(ABORT, 'account_must_be_archived_not_deleted');
END;

CREATE TRIGGER asset_no_delete
BEFORE DELETE ON asset
BEGIN
  SELECT RAISE(ABORT, 'asset_must_be_archived_not_deleted');
END;

CREATE TRIGGER provider_mapping_no_delete
BEFORE DELETE ON provider_mapping
BEGIN
  SELECT RAISE(ABORT, 'provider_mapping_must_be_disabled_not_deleted');
END;

CREATE TRIGGER transaction_supersedes_same_portfolio
BEFORE INSERT ON transaction_record
WHEN NEW.supersedes_transaction_id IS NOT NULL
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
    FROM transaction_record old
    JOIN transaction_seal seal ON seal.transaction_id = old.transaction_id
    WHERE old.transaction_id = NEW.supersedes_transaction_id
      AND old.portfolio_id = NEW.portfolio_id
  ) THEN RAISE(ABORT, 'superseded_transaction_missing_unsealed_or_cross_portfolio') END;
END;

CREATE TRIGGER transaction_record_no_update
BEFORE UPDATE ON transaction_record
BEGIN
  SELECT RAISE(ABORT, 'transaction_record_is_immutable');
END;

CREATE TRIGGER transaction_record_no_delete
BEFORE DELETE ON transaction_record
BEGIN
  SELECT RAISE(ABORT, 'transaction_record_is_immutable');
END;

CREATE TRIGGER transaction_posting_same_portfolio
BEFORE INSERT ON transaction_posting
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
    FROM transaction_record tx
    JOIN account acc ON acc.account_id = NEW.account_id
    WHERE tx.transaction_id = NEW.transaction_id
      AND tx.portfolio_id = acc.portfolio_id
  ) THEN RAISE(ABORT, 'posting_account_cross_portfolio') END;
END;

CREATE TRIGGER transaction_posting_book_only
BEFORE INSERT ON transaction_posting
BEGIN
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM transaction_record tx
    WHERE tx.transaction_id = NEW.transaction_id AND tx.record_action != 'book'
  ) THEN RAISE(ABORT, 'void_transaction_cannot_have_postings') END;
END;

CREATE TRIGGER transaction_posting_not_after_seal
BEFORE INSERT ON transaction_posting
WHEN EXISTS (SELECT 1 FROM transaction_seal s WHERE s.transaction_id = NEW.transaction_id)
BEGIN
  SELECT RAISE(ABORT, 'sealed_transaction_cannot_receive_postings');
END;

CREATE TRIGGER transaction_posting_no_update
BEFORE UPDATE ON transaction_posting
BEGIN
  SELECT RAISE(ABORT, 'transaction_posting_is_immutable');
END;

CREATE TRIGGER transaction_posting_no_delete
BEFORE DELETE ON transaction_posting
BEGIN
  SELECT RAISE(ABORT, 'transaction_posting_is_immutable');
END;

CREATE TRIGGER transaction_seal_validate
BEFORE INSERT ON transaction_seal
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM transaction_record tx WHERE tx.transaction_id = NEW.transaction_id
  ) THEN RAISE(ABORT, 'seal_transaction_missing') END;
  SELECT CASE WHEN NEW.posting_count != (
    SELECT count(*) FROM transaction_posting p WHERE p.transaction_id = NEW.transaction_id
  ) THEN RAISE(ABORT, 'seal_posting_count_mismatch') END;
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM transaction_record tx
    WHERE tx.transaction_id = NEW.transaction_id
      AND ((tx.record_action = 'book' AND NEW.posting_count < 1) OR (tx.record_action = 'void' AND NEW.posting_count != 0))
  ) THEN RAISE(ABORT, 'seal_action_posting_contract_invalid') END;
END;

CREATE TRIGGER transaction_seal_no_update
BEFORE UPDATE ON transaction_seal
BEGIN
  SELECT RAISE(ABORT, 'transaction_seal_is_immutable');
END;

CREATE TRIGGER transaction_seal_no_delete
BEFORE DELETE ON transaction_seal
BEGIN
  SELECT RAISE(ABORT, 'transaction_seal_is_immutable');
END;

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

CREATE VIEW current_transaction AS
SELECT tx.*
FROM transaction_record tx
JOIN transaction_seal seal ON seal.transaction_id = tx.transaction_id
WHERE tx.record_action = 'book'
  AND NOT EXISTS (
    SELECT 1
    FROM transaction_record successor
    JOIN transaction_seal successor_seal ON successor_seal.transaction_id = successor.transaction_id
    WHERE successor.supersedes_transaction_id = tx.transaction_id
  );

CREATE VIEW current_transaction_posting AS
SELECT posting.*
FROM transaction_posting posting
JOIN current_transaction tx ON tx.transaction_id = posting.transaction_id;

COMMIT;
