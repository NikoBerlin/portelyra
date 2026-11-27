PRAGMA foreign_keys = ON;
PRAGMA user_version = 400;

BEGIN IMMEDIATE;

CREATE TABLE ledger_store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 400),
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 3 AND 64),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 3 AND 64),
  data_space_id TEXT NOT NULL CHECK (length(data_space_id) BETWEEN 3 AND 64),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z')
) STRICT;

CREATE TABLE ledger_command_receipt (
  command_id TEXT PRIMARY KEY CHECK (command_id LIKE 'cmd_%' AND length(command_id) BETWEEN 8 AND 64),
  writer_area TEXT NOT NULL CHECK (writer_area IN ('data_app', 'tax_app', 'tax_worker', 'trusted_model')),
  action_type TEXT NOT NULL CHECK (length(trim(action_type)) BETWEEN 3 AND 80),
  actor_id TEXT NOT NULL CHECK (length(trim(actor_id)) BETWEEN 3 AND 80),
  payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64 AND payload_fingerprint NOT GLOB '*[^a-f0-9]*'),
  confirmation_fingerprint TEXT CHECK (confirmation_fingerprint IS NULL OR (length(confirmation_fingerprint) = 64 AND confirmation_fingerprint NOT GLOB '*[^a-f0-9]*')),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc) = 20 AND substr(committed_at_utc, 11, 1) = 'T' AND substr(committed_at_utc, 20, 1) = 'Z')
) STRICT;

CREATE TABLE portfolio_entity (
  portfolio_id TEXT PRIMARY KEY CHECK (portfolio_id LIKE 'ptf_%' AND length(portfolio_id) BETWEEN 8 AND 64),
  origin_type TEXT NOT NULL CHECK (origin_type IN ('native', 'legacy_conversion')),
  source_key_fingerprint TEXT UNIQUE CHECK (source_key_fingerprint IS NULL OR (length(source_key_fingerprint) = 64 AND source_key_fingerprint NOT GLOB '*[^a-f0-9]*')),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  CHECK ((origin_type = 'native' AND source_key_fingerprint IS NULL) OR (origin_type = 'legacy_conversion' AND source_key_fingerprint IS NOT NULL))
) STRICT;

CREATE TABLE portfolio_revision (
  portfolio_revision_id TEXT PRIMARY KEY CHECK (portfolio_revision_id LIKE 'ptr_%' AND length(portfolio_revision_id) BETWEEN 8 AND 64),
  portfolio_id TEXT NOT NULL REFERENCES portfolio_entity(portfolio_id),
  revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
  display_name TEXT NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 120),
  base_currency TEXT NOT NULL CHECK (length(base_currency) = 3 AND base_currency = upper(base_currency) AND base_currency NOT GLOB '*[^A-Z]*'),
  status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
  supersedes_revision_id TEXT UNIQUE REFERENCES portfolio_revision(portfolio_revision_id),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  UNIQUE (portfolio_id, revision_no)
) STRICT;

CREATE TABLE account_entity (
  account_id TEXT PRIMARY KEY CHECK (account_id LIKE 'acc_%' AND length(account_id) BETWEEN 8 AND 64),
  portfolio_id TEXT NOT NULL REFERENCES portfolio_entity(portfolio_id),
  origin_type TEXT NOT NULL CHECK (origin_type IN ('native', 'legacy_conversion')),
  source_key_fingerprint TEXT UNIQUE CHECK (source_key_fingerprint IS NULL OR (length(source_key_fingerprint) = 64 AND source_key_fingerprint NOT GLOB '*[^a-f0-9]*')),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  CHECK ((origin_type = 'native' AND source_key_fingerprint IS NULL) OR (origin_type = 'legacy_conversion' AND source_key_fingerprint IS NOT NULL))
) STRICT;

CREATE TABLE account_revision (
  account_revision_id TEXT PRIMARY KEY CHECK (account_revision_id LIKE 'acr_%' AND length(account_revision_id) BETWEEN 8 AND 64),
  account_id TEXT NOT NULL REFERENCES account_entity(account_id),
  revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
  display_name TEXT NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 120),
  account_type TEXT NOT NULL CHECK (account_type IN ('securities', 'cash', 'bank', 'crypto_wallet', 'other')),
  institution_label TEXT CHECK (institution_label IS NULL OR length(trim(institution_label)) BETWEEN 1 AND 120),
  status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
  review_status TEXT NOT NULL CHECK (review_status IN ('complete', 'type_review_pending', 'metadata_pending')),
  supersedes_revision_id TEXT UNIQUE REFERENCES account_revision(account_revision_id),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  UNIQUE (account_id, revision_no)
) STRICT;

CREATE TABLE asset_entity (
  asset_id TEXT PRIMARY KEY CHECK (asset_id LIKE 'ast_%' AND length(asset_id) BETWEEN 8 AND 64),
  origin_type TEXT NOT NULL CHECK (origin_type IN ('native', 'legacy_conversion')),
  source_key_fingerprint TEXT UNIQUE CHECK (source_key_fingerprint IS NULL OR (length(source_key_fingerprint) = 64 AND source_key_fingerprint NOT GLOB '*[^a-f0-9]*')),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  CHECK ((origin_type = 'native' AND source_key_fingerprint IS NULL) OR (origin_type = 'legacy_conversion' AND source_key_fingerprint IS NOT NULL))
) STRICT;

CREATE TABLE asset_revision (
  asset_revision_id TEXT PRIMARY KEY CHECK (asset_revision_id LIKE 'asr_%' AND length(asset_revision_id) BETWEEN 8 AND 64),
  asset_id TEXT NOT NULL REFERENCES asset_entity(asset_id),
  revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
  display_name TEXT NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 160),
  asset_type TEXT NOT NULL CHECK (asset_type IN ('equity', 'etf', 'fund', 'bond', 'derivative', 'crypto', 'commodity', 'cash', 'fx', 'index', 'other')),
  quantity_scale INTEGER CHECK (quantity_scale IS NULL OR quantity_scale BETWEEN 0 AND 24),
  valuation_method TEXT CHECK (valuation_method IS NULL OR valuation_method IN ('external_market', 'manual', 'unit_value', 'transaction_only')),
  isin TEXT CHECK (isin IS NULL OR (length(isin) = 12 AND isin = upper(isin) AND isin NOT GLOB '*[^A-Z0-9]*')),
  note TEXT CHECK (note IS NULL OR length(note) <= 4000),
  status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
  metadata_status TEXT NOT NULL CHECK (metadata_status IN ('complete', 'optional_fields_pending')),
  supersedes_revision_id TEXT UNIQUE REFERENCES asset_revision(asset_revision_id),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  UNIQUE (asset_id, revision_no)
) STRICT;

CREATE TABLE transaction_fact (
  transaction_id TEXT PRIMARY KEY CHECK (transaction_id LIKE 'txn_%' AND length(transaction_id) BETWEEN 8 AND 64),
  portfolio_id TEXT NOT NULL REFERENCES portfolio_entity(portfolio_id),
  account_id TEXT NOT NULL REFERENCES account_entity(account_id),
  related_account_id TEXT REFERENCES account_entity(account_id),
  asset_id TEXT NOT NULL REFERENCES asset_entity(asset_id),
  event_type TEXT NOT NULL CHECK (event_type IN ('buy', 'sell', 'deposit', 'withdrawal', 'transfer', 'dividend', 'interest', 'reward', 'fee', 'adjustment', 'other')),
  effective_at_utc TEXT NOT NULL CHECK (length(effective_at_utc) = 20 AND substr(effective_at_utc, 11, 1) = 'T' AND substr(effective_at_utc, 20, 1) = 'Z'),
  local_date TEXT NOT NULL CHECK (length(local_date) = 10 AND substr(local_date, 5, 1) = '-' AND substr(local_date, 8, 1) = '-'),
  quantity_decimal TEXT NOT NULL CHECK (
    typeof(quantity_decimal) = 'text'
    AND length(quantity_decimal) BETWEEN 1 AND 80
    AND quantity_decimal NOT GLOB '*[^0-9.]*'
    AND quantity_decimal NOT IN ('', '.', '0')
    AND (length(quantity_decimal) - length(replace(quantity_decimal, '.', ''))) <= 1
    AND (instr(quantity_decimal, '.') = 0 OR (substr(quantity_decimal, -1, 1) NOT IN ('.', '0') AND instr(quantity_decimal, '.') > 1))
    AND (quantity_decimal LIKE '0.%' OR substr(quantity_decimal, 1, 1) BETWEEN '1' AND '9')
  ),
  unit_price_decimal TEXT NOT NULL CHECK (
    typeof(unit_price_decimal) = 'text'
    AND length(unit_price_decimal) BETWEEN 1 AND 80
    AND unit_price_decimal NOT GLOB '*[^0-9.]*'
    AND unit_price_decimal NOT IN ('', '.', '0')
    AND (length(unit_price_decimal) - length(replace(unit_price_decimal, '.', ''))) <= 1
    AND (instr(unit_price_decimal, '.') = 0 OR (substr(unit_price_decimal, -1, 1) NOT IN ('.', '0') AND instr(unit_price_decimal, '.') > 1))
    AND (unit_price_decimal LIKE '0.%' OR substr(unit_price_decimal, 1, 1) BETWEEN '1' AND '9')
  ),
  gross_amount_decimal TEXT CHECK (
    gross_amount_decimal IS NULL OR (
      typeof(gross_amount_decimal) = 'text'
      AND length(gross_amount_decimal) BETWEEN 1 AND 80
      AND gross_amount_decimal NOT GLOB '*[^0-9.]*'
      AND gross_amount_decimal NOT IN ('', '.', '0')
      AND (length(gross_amount_decimal) - length(replace(gross_amount_decimal, '.', ''))) <= 1
      AND (instr(gross_amount_decimal, '.') = 0 OR (substr(gross_amount_decimal, -1, 1) NOT IN ('.', '0') AND instr(gross_amount_decimal, '.') > 1))
      AND (gross_amount_decimal LIKE '0.%' OR substr(gross_amount_decimal, 1, 1) BETWEEN '1' AND '9')
    )
  ),
  fee_decimal TEXT CHECK (
    fee_decimal IS NULL OR (
      typeof(fee_decimal) = 'text'
      AND length(fee_decimal) BETWEEN 1 AND 80
      AND fee_decimal NOT GLOB '*[^0-9.]*'
      AND fee_decimal NOT IN ('', '.', '0')
      AND (length(fee_decimal) - length(replace(fee_decimal, '.', ''))) <= 1
      AND (instr(fee_decimal, '.') = 0 OR (substr(fee_decimal, -1, 1) NOT IN ('.', '0') AND instr(fee_decimal, '.') > 1))
      AND (fee_decimal LIKE '0.%' OR substr(fee_decimal, 1, 1) BETWEEN '1' AND '9')
    )
  ),
  transaction_currency TEXT NOT NULL CHECK (length(transaction_currency) = 3 AND transaction_currency = upper(transaction_currency) AND transaction_currency NOT GLOB '*[^A-Z]*'),
  transaction_code TEXT CHECK (transaction_code IS NULL OR length(transaction_code) BETWEEN 1 AND 200),
  memo TEXT CHECK (memo IS NULL OR length(memo) <= 4000),
  origin_type TEXT NOT NULL CHECK (origin_type IN ('native', 'legacy_conversion')),
  source_row_fingerprint TEXT UNIQUE CHECK (source_row_fingerprint IS NULL OR (length(source_row_fingerprint) = 64 AND source_row_fingerprint NOT GLOB '*[^a-f0-9]*')),
  supersedes_transaction_id TEXT UNIQUE REFERENCES transaction_fact(transaction_id),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  CHECK ((event_type = 'transfer' AND related_account_id IS NOT NULL AND related_account_id != account_id) OR (event_type != 'transfer' AND related_account_id IS NULL)),
  CHECK (gross_amount_decimal IS NULL OR (quantity_decimal = '1' AND unit_price_decimal = gross_amount_decimal)),
  CHECK ((origin_type = 'native' AND source_row_fingerprint IS NULL) OR (origin_type = 'legacy_conversion' AND source_row_fingerprint IS NOT NULL)),
  CHECK (supersedes_transaction_id IS NULL OR supersedes_transaction_id != transaction_id)
) STRICT;

CREATE TABLE transaction_void (
  void_id TEXT PRIMARY KEY CHECK (void_id LIKE 'tvd_%' AND length(void_id) BETWEEN 8 AND 64),
  transaction_id TEXT NOT NULL UNIQUE REFERENCES transaction_fact(transaction_id),
  reason TEXT NOT NULL CHECK (length(trim(reason)) BETWEEN 1 AND 500),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z')
) STRICT;

CREATE TABLE tax_model_definition (
  tax_model_id TEXT NOT NULL CHECK (tax_model_id GLOB '[a-z]*_v[0-9]*' AND length(tax_model_id) BETWEEN 5 AND 80),
  model_version TEXT NOT NULL CHECK (length(trim(model_version)) BETWEEN 1 AND 40),
  label TEXT NOT NULL CHECK (length(trim(label)) BETWEEN 1 AND 160),
  country_code TEXT NOT NULL CHECK (length(country_code) BETWEEN 2 AND 8 AND country_code = upper(country_code)),
  model_scope TEXT NOT NULL CHECK (model_scope IN ('private_assets', 'scenario')),
  rules_fingerprint TEXT NOT NULL CHECK (length(rules_fingerprint) = 64 AND rules_fingerprint NOT GLOB '*[^a-f0-9]*'),
  disclaimer_code TEXT NOT NULL CHECK (disclaimer_code = 'model_projection_not_legal_advice'),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  PRIMARY KEY (tax_model_id, model_version)
) STRICT;

CREATE TABLE tax_classification_definition (
  tax_model_id TEXT NOT NULL,
  model_version TEXT NOT NULL,
  classification_code TEXT NOT NULL CHECK (length(classification_code) BETWEEN 3 AND 80 AND classification_code = lower(classification_code)),
  partial_exemption_applicability TEXT NOT NULL CHECK (partial_exemption_applicability IN ('applicable', 'not_applicable')),
  partial_exemption_rate_decimal TEXT CHECK (
    partial_exemption_rate_decimal IS NULL OR (
      typeof(partial_exemption_rate_decimal) = 'text'
      AND partial_exemption_rate_decimal NOT GLOB '*[^0-9.]*'
      AND partial_exemption_rate_decimal NOT IN ('', '.')
      AND (length(partial_exemption_rate_decimal) - length(replace(partial_exemption_rate_decimal, '.', ''))) <= 1
      AND (instr(partial_exemption_rate_decimal, '.') = 0 OR (substr(partial_exemption_rate_decimal, -1, 1) NOT IN ('.', '0') AND instr(partial_exemption_rate_decimal, '.') > 1))
      AND (partial_exemption_rate_decimal = '0' OR partial_exemption_rate_decimal LIKE '0.%' OR substr(partial_exemption_rate_decimal, 1, 1) BETWEEN '1' AND '9')
      AND CAST(partial_exemption_rate_decimal AS NUMERIC) BETWEEN 0 AND 100
    )
  ),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  PRIMARY KEY (tax_model_id, model_version, classification_code),
  FOREIGN KEY (tax_model_id, model_version) REFERENCES tax_model_definition(tax_model_id, model_version),
  CHECK ((partial_exemption_applicability = 'applicable' AND partial_exemption_rate_decimal IS NOT NULL) OR (partial_exemption_applicability = 'not_applicable' AND partial_exemption_rate_decimal IS NULL))
) STRICT;

CREATE TABLE tax_classification_asset_type (
  tax_model_id TEXT NOT NULL,
  model_version TEXT NOT NULL,
  classification_code TEXT NOT NULL,
  asset_type TEXT NOT NULL CHECK (asset_type IN ('equity', 'etf', 'fund', 'bond', 'derivative', 'crypto', 'commodity', 'cash', 'fx', 'index', 'other')),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  PRIMARY KEY (tax_model_id, model_version, classification_code, asset_type),
  FOREIGN KEY (tax_model_id, model_version, classification_code) REFERENCES tax_classification_definition(tax_model_id, model_version, classification_code)
) STRICT;

CREATE TABLE asset_tax_assignment_revision (
  assignment_revision_id TEXT PRIMARY KEY CHECK (assignment_revision_id LIKE 'atr_%' AND length(assignment_revision_id) BETWEEN 8 AND 64),
  asset_id TEXT NOT NULL REFERENCES asset_entity(asset_id),
  tax_model_id TEXT NOT NULL,
  model_version TEXT NOT NULL,
  classification_code TEXT NOT NULL,
  effective_from TEXT NOT NULL CHECK (length(effective_from) = 10 AND substr(effective_from, 5, 1) = '-' AND substr(effective_from, 8, 1) = '-'),
  effective_to TEXT CHECK (effective_to IS NULL OR (length(effective_to) = 10 AND substr(effective_to, 5, 1) = '-' AND substr(effective_to, 8, 1) = '-')),
  status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
  input_source TEXT NOT NULL CHECK (input_source IN ('manual', 'reviewed_legacy_hint')),
  note TEXT CHECK (note IS NULL OR length(note) <= 1000),
  supersedes_assignment_revision_id TEXT UNIQUE REFERENCES asset_tax_assignment_revision(assignment_revision_id),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  FOREIGN KEY (tax_model_id, model_version, classification_code) REFERENCES tax_classification_definition(tax_model_id, model_version, classification_code),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
) STRICT;

CREATE TABLE tax_configuration (
  tax_configuration_id TEXT PRIMARY KEY CHECK (tax_configuration_id LIKE 'txc_%' AND length(tax_configuration_id) BETWEEN 8 AND 64),
  portfolio_id TEXT NOT NULL REFERENCES portfolio_entity(portfolio_id),
  tax_year INTEGER NOT NULL CHECK (tax_year BETWEEN 1900 AND 9999),
  tax_model_id TEXT NOT NULL,
  model_version TEXT NOT NULL,
  reporting_currency TEXT NOT NULL CHECK (length(reporting_currency) = 3 AND reporting_currency = upper(reporting_currency) AND reporting_currency NOT GLOB '*[^A-Z]*'),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  FOREIGN KEY (tax_model_id, model_version) REFERENCES tax_model_definition(tax_model_id, model_version),
  UNIQUE (portfolio_id, tax_year, tax_model_id, model_version)
) STRICT;

CREATE TABLE tax_parameter_revision (
  parameter_revision_id TEXT PRIMARY KEY CHECK (parameter_revision_id LIKE 'tpr_%' AND length(parameter_revision_id) BETWEEN 8 AND 64),
  tax_configuration_id TEXT NOT NULL REFERENCES tax_configuration(tax_configuration_id),
  parameter_code TEXT NOT NULL CHECK (length(parameter_code) BETWEEN 3 AND 100),
  scope_type TEXT NOT NULL CHECK (scope_type IN ('global', 'account')),
  account_id TEXT REFERENCES account_entity(account_id),
  value_type TEXT NOT NULL CHECK (value_type IN ('money_amount', 'percentage_rate')),
  amount_decimal TEXT,
  rate_decimal TEXT,
  externally_used_decimal TEXT,
  currency TEXT CHECK (currency IS NULL OR (length(currency) = 3 AND currency = upper(currency) AND currency NOT GLOB '*[^A-Z]*')),
  status TEXT NOT NULL CHECK (status IN ('active', 'inactive')),
  input_source TEXT NOT NULL CHECK (input_source IN ('manual', 'legacy_import')),
  note TEXT CHECK (note IS NULL OR length(note) <= 1000),
  supersedes_parameter_revision_id TEXT UNIQUE REFERENCES tax_parameter_revision(parameter_revision_id),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z'),
  CHECK ((scope_type = 'global' AND account_id IS NULL) OR (scope_type = 'account' AND account_id IS NOT NULL)),
  CHECK (
    (value_type = 'money_amount' AND amount_decimal IS NOT NULL AND rate_decimal IS NULL AND currency IS NOT NULL)
    OR
    (value_type = 'percentage_rate' AND amount_decimal IS NULL AND rate_decimal IS NOT NULL AND externally_used_decimal IS NULL AND currency IS NULL)
  ),
  CHECK (amount_decimal IS NULL OR (
    typeof(amount_decimal) = 'text' AND amount_decimal NOT GLOB '*[^0-9.]*' AND amount_decimal NOT IN ('', '.')
    AND (length(amount_decimal) - length(replace(amount_decimal, '.', ''))) <= 1
    AND (instr(amount_decimal, '.') = 0 OR (substr(amount_decimal, -1, 1) NOT IN ('.', '0') AND instr(amount_decimal, '.') > 1))
    AND (amount_decimal = '0' OR amount_decimal LIKE '0.%' OR substr(amount_decimal, 1, 1) BETWEEN '1' AND '9')
  )),
  CHECK (rate_decimal IS NULL OR (
    typeof(rate_decimal) = 'text' AND rate_decimal NOT GLOB '*[^0-9.]*' AND rate_decimal NOT IN ('', '.')
    AND (length(rate_decimal) - length(replace(rate_decimal, '.', ''))) <= 1
    AND (instr(rate_decimal, '.') = 0 OR (substr(rate_decimal, -1, 1) NOT IN ('.', '0') AND instr(rate_decimal, '.') > 1))
    AND (rate_decimal = '0' OR rate_decimal LIKE '0.%' OR substr(rate_decimal, 1, 1) BETWEEN '1' AND '9')
    AND CAST(rate_decimal AS NUMERIC) BETWEEN 0 AND 100
  )),
  CHECK (externally_used_decimal IS NULL OR (
    typeof(externally_used_decimal) = 'text' AND externally_used_decimal NOT GLOB '*[^0-9.]*' AND externally_used_decimal NOT IN ('', '.')
    AND (length(externally_used_decimal) - length(replace(externally_used_decimal, '.', ''))) <= 1
    AND (instr(externally_used_decimal, '.') = 0 OR (substr(externally_used_decimal, -1, 1) NOT IN ('.', '0') AND instr(externally_used_decimal, '.') > 1))
    AND (externally_used_decimal = '0' OR externally_used_decimal LIKE '0.%' OR substr(externally_used_decimal, 1, 1) BETWEEN '1' AND '9')
  ))
) STRICT;

CREATE TABLE tax_projection_run (
  tax_projection_run_id TEXT PRIMARY KEY CHECK (tax_projection_run_id LIKE 'txr_%' AND length(tax_projection_run_id) BETWEEN 8 AND 64),
  tax_configuration_id TEXT NOT NULL REFERENCES tax_configuration(tax_configuration_id),
  projection_mode TEXT NOT NULL CHECK (projection_mode IN ('unrealized_snapshot', 'realized_annual')),
  snapshot_at_utc TEXT CHECK (snapshot_at_utc IS NULL OR (length(snapshot_at_utc) = 20 AND substr(snapshot_at_utc, 11, 1) = 'T' AND substr(snapshot_at_utc, 20, 1) = 'Z')),
  tax_year INTEGER CHECK (tax_year IS NULL OR tax_year BETWEEN 1900 AND 9999),
  loss_netting_policy_applied INTEGER NOT NULL CHECK (loss_netting_policy_applied IN (0, 1)),
  annual_relief_policy_applied INTEGER NOT NULL CHECK (annual_relief_policy_applied IN (0, 1)),
  default_zero_parameter_count INTEGER NOT NULL CHECK (default_zero_parameter_count >= 0),
  projected_tax_total_decimal TEXT NOT NULL CHECK (
    typeof(projected_tax_total_decimal) = 'text'
    AND projected_tax_total_decimal NOT GLOB '*[^0-9.]*'
    AND projected_tax_total_decimal NOT IN ('', '.')
    AND (length(projected_tax_total_decimal) - length(replace(projected_tax_total_decimal, '.', ''))) <= 1
    AND (instr(projected_tax_total_decimal, '.') = 0 OR (substr(projected_tax_total_decimal, -1, 1) NOT IN ('.', '0') AND instr(projected_tax_total_decimal, '.') > 1))
    AND (projected_tax_total_decimal = '0' OR projected_tax_total_decimal LIKE '0.%' OR substr(projected_tax_total_decimal, 1, 1) BETWEEN '1' AND '9')
  ),
  input_fingerprint TEXT NOT NULL CHECK (length(input_fingerprint) = 64 AND input_fingerprint NOT GLOB '*[^a-f0-9]*'),
  parameter_set_fingerprint TEXT NOT NULL CHECK (length(parameter_set_fingerprint) = 64 AND parameter_set_fingerprint NOT GLOB '*[^a-f0-9]*'),
  assignment_set_fingerprint TEXT NOT NULL CHECK (length(assignment_set_fingerprint) = 64 AND assignment_set_fingerprint NOT GLOB '*[^a-f0-9]*'),
  rules_fingerprint TEXT NOT NULL CHECK (length(rules_fingerprint) = 64 AND rules_fingerprint NOT GLOB '*[^a-f0-9]*'),
  report_artifact_fingerprint TEXT NOT NULL UNIQUE CHECK (length(report_artifact_fingerprint) = 64 AND report_artifact_fingerprint NOT GLOB '*[^a-f0-9]*'),
  disclaimer_code TEXT NOT NULL CHECK (disclaimer_code = 'model_projection_not_legal_advice'),
  command_id TEXT NOT NULL REFERENCES ledger_command_receipt(command_id),
  completed_at_utc TEXT NOT NULL CHECK (length(completed_at_utc) = 20 AND substr(completed_at_utc, 11, 1) = 'T' AND substr(completed_at_utc, 20, 1) = 'Z'),
  CHECK (
    (projection_mode = 'unrealized_snapshot' AND snapshot_at_utc IS NOT NULL AND tax_year IS NULL AND loss_netting_policy_applied = 0 AND annual_relief_policy_applied = 0 AND default_zero_parameter_count = 0)
    OR
    (projection_mode = 'realized_annual' AND snapshot_at_utc IS NULL AND tax_year IS NOT NULL AND loss_netting_policy_applied = 1 AND annual_relief_policy_applied = 1)
  )
) STRICT;

CREATE VIEW current_portfolio_revision AS
SELECT revision.*
FROM portfolio_revision revision
WHERE NOT EXISTS (SELECT 1 FROM portfolio_revision successor WHERE successor.supersedes_revision_id = revision.portfolio_revision_id);

CREATE VIEW current_account_revision AS
SELECT revision.*
FROM account_revision revision
WHERE NOT EXISTS (SELECT 1 FROM account_revision successor WHERE successor.supersedes_revision_id = revision.account_revision_id);

CREATE VIEW current_asset_revision AS
SELECT revision.*
FROM asset_revision revision
WHERE NOT EXISTS (SELECT 1 FROM asset_revision successor WHERE successor.supersedes_revision_id = revision.asset_revision_id);

CREATE VIEW current_transaction_fact AS
SELECT tx.*
FROM transaction_fact tx
WHERE NOT EXISTS (SELECT 1 FROM transaction_fact successor WHERE successor.supersedes_transaction_id = tx.transaction_id)
  AND NOT EXISTS (SELECT 1 FROM transaction_void voided WHERE voided.transaction_id = tx.transaction_id);

CREATE VIEW current_asset_tax_assignment AS
SELECT assignment.*
FROM asset_tax_assignment_revision assignment
WHERE NOT EXISTS (
  SELECT 1 FROM asset_tax_assignment_revision successor
  WHERE successor.supersedes_assignment_revision_id = assignment.assignment_revision_id
);

CREATE VIEW current_tax_parameter AS
SELECT parameter.*
FROM tax_parameter_revision parameter
WHERE NOT EXISTS (
  SELECT 1 FROM tax_parameter_revision successor
  WHERE successor.supersedes_parameter_revision_id = parameter.parameter_revision_id
);

CREATE TRIGGER ledger_binding_no_update BEFORE UPDATE ON ledger_store_binding BEGIN SELECT RAISE(ABORT, 'ledger_binding_immutable'); END;
CREATE TRIGGER ledger_binding_no_delete BEFORE DELETE ON ledger_store_binding BEGIN SELECT RAISE(ABORT, 'ledger_binding_immutable'); END;
CREATE TRIGGER ledger_receipt_no_update BEFORE UPDATE ON ledger_command_receipt BEGIN SELECT RAISE(ABORT, 'ledger_receipt_immutable'); END;
CREATE TRIGGER ledger_receipt_no_delete BEFORE DELETE ON ledger_command_receipt BEGIN SELECT RAISE(ABORT, 'ledger_receipt_immutable'); END;

CREATE TRIGGER portfolio_entity_writer BEFORE INSERT ON portfolio_entity BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'data_app') THEN RAISE(ABORT, 'portfolio_writer_invalid') END;
END;
CREATE TRIGGER account_entity_writer BEFORE INSERT ON account_entity BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'data_app') THEN RAISE(ABORT, 'account_writer_invalid') END;
END;
CREATE TRIGGER asset_entity_writer BEFORE INSERT ON asset_entity BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'data_app') THEN RAISE(ABORT, 'asset_writer_invalid') END;
END;

CREATE TRIGGER portfolio_revision_validate BEFORE INSERT ON portfolio_revision BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'data_app') THEN RAISE(ABORT, 'portfolio_writer_invalid') END;
  SELECT CASE WHEN NEW.revision_no = 1 AND (NEW.supersedes_revision_id IS NOT NULL OR EXISTS (SELECT 1 FROM portfolio_revision WHERE portfolio_id = NEW.portfolio_id)) THEN RAISE(ABORT, 'portfolio_revision_initial_invalid') END;
  SELECT CASE WHEN NEW.revision_no > 1 AND NOT EXISTS (
    SELECT 1 FROM portfolio_revision old
    WHERE old.portfolio_revision_id = NEW.supersedes_revision_id AND old.portfolio_id = NEW.portfolio_id AND old.revision_no + 1 = NEW.revision_no
      AND NOT EXISTS (SELECT 1 FROM portfolio_revision successor WHERE successor.supersedes_revision_id = old.portfolio_revision_id)
  ) THEN RAISE(ABORT, 'portfolio_revision_chain_invalid') END;
END;

CREATE TRIGGER account_revision_validate BEFORE INSERT ON account_revision BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'data_app') THEN RAISE(ABORT, 'account_writer_invalid') END;
  SELECT CASE WHEN NEW.revision_no = 1 AND (NEW.supersedes_revision_id IS NOT NULL OR EXISTS (SELECT 1 FROM account_revision WHERE account_id = NEW.account_id)) THEN RAISE(ABORT, 'account_revision_initial_invalid') END;
  SELECT CASE WHEN NEW.revision_no > 1 AND NOT EXISTS (
    SELECT 1 FROM account_revision old
    WHERE old.account_revision_id = NEW.supersedes_revision_id AND old.account_id = NEW.account_id AND old.revision_no + 1 = NEW.revision_no
      AND NOT EXISTS (SELECT 1 FROM account_revision successor WHERE successor.supersedes_revision_id = old.account_revision_id)
  ) THEN RAISE(ABORT, 'account_revision_chain_invalid') END;
END;

CREATE TRIGGER asset_revision_validate BEFORE INSERT ON asset_revision BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'data_app') THEN RAISE(ABORT, 'asset_writer_invalid') END;
  SELECT CASE WHEN NEW.revision_no = 1 AND (NEW.supersedes_revision_id IS NOT NULL OR EXISTS (SELECT 1 FROM asset_revision WHERE asset_id = NEW.asset_id)) THEN RAISE(ABORT, 'asset_revision_initial_invalid') END;
  SELECT CASE WHEN NEW.revision_no > 1 AND NOT EXISTS (
    SELECT 1 FROM asset_revision old
    WHERE old.asset_revision_id = NEW.supersedes_revision_id AND old.asset_id = NEW.asset_id AND old.revision_no + 1 = NEW.revision_no
      AND NOT EXISTS (SELECT 1 FROM asset_revision successor WHERE successor.supersedes_revision_id = old.asset_revision_id)
  ) THEN RAISE(ABORT, 'asset_revision_chain_invalid') END;
  SELECT CASE WHEN NEW.isin IS NOT NULL AND EXISTS (
    SELECT 1 FROM current_asset_revision existing
    WHERE existing.isin = NEW.isin AND existing.asset_id != NEW.asset_id
  ) THEN RAISE(ABORT, 'asset_isin_current_duplicate') END;
END;

CREATE TRIGGER transaction_fact_validate BEFORE INSERT ON transaction_fact BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'data_app') THEN RAISE(ABORT, 'transaction_writer_invalid') END;
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM account_entity WHERE account_id = NEW.account_id AND portfolio_id = NEW.portfolio_id) THEN RAISE(ABORT, 'transaction_account_scope_invalid') END;
  SELECT CASE WHEN NEW.related_account_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM account_entity WHERE account_id = NEW.related_account_id AND portfolio_id = NEW.portfolio_id) THEN RAISE(ABORT, 'transaction_related_account_scope_invalid') END;
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM current_asset_revision WHERE asset_id = NEW.asset_id) THEN RAISE(ABORT, 'transaction_asset_revision_missing') END;
  SELECT CASE WHEN EXISTS (SELECT 1 FROM current_asset_revision WHERE asset_id = NEW.asset_id AND asset_type = 'cash') AND NEW.event_type NOT IN ('deposit', 'withdrawal', 'transfer', 'interest', 'fee', 'adjustment', 'other') THEN RAISE(ABORT, 'transaction_cash_event_invalid') END;
  SELECT CASE WHEN EXISTS (SELECT 1 FROM current_asset_revision WHERE asset_id = NEW.asset_id AND asset_type != 'cash') AND NEW.event_type = 'interest' THEN RAISE(ABORT, 'transaction_noncash_interest_invalid') END;
  SELECT CASE WHEN NEW.event_type = 'reward' AND NOT EXISTS (SELECT 1 FROM current_asset_revision WHERE asset_id = NEW.asset_id AND asset_type = 'crypto') THEN RAISE(ABORT, 'transaction_reward_asset_invalid') END;
  SELECT CASE WHEN NEW.supersedes_transaction_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM current_transaction_fact old
    WHERE old.transaction_id = NEW.supersedes_transaction_id AND old.portfolio_id = NEW.portfolio_id
  ) THEN RAISE(ABORT, 'transaction_supersession_invalid') END;
END;

CREATE TRIGGER transaction_void_validate BEFORE INSERT ON transaction_void BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'data_app') THEN RAISE(ABORT, 'transaction_writer_invalid') END;
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM current_transaction_fact WHERE transaction_id = NEW.transaction_id) THEN RAISE(ABORT, 'transaction_void_target_invalid') END;
END;

CREATE TRIGGER tax_model_definition_writer BEFORE INSERT ON tax_model_definition BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'trusted_model') THEN RAISE(ABORT, 'tax_model_writer_invalid') END;
END;
CREATE TRIGGER tax_classification_definition_writer BEFORE INSERT ON tax_classification_definition BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'trusted_model') THEN RAISE(ABORT, 'tax_model_writer_invalid') END;
END;
CREATE TRIGGER tax_classification_asset_type_writer BEFORE INSERT ON tax_classification_asset_type BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'trusted_model') THEN RAISE(ABORT, 'tax_model_writer_invalid') END;
END;

CREATE TRIGGER asset_tax_assignment_validate BEFORE INSERT ON asset_tax_assignment_revision BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'tax_app') THEN RAISE(ABORT, 'tax_assignment_writer_invalid') END;
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM current_asset_revision asset
    JOIN tax_classification_asset_type allowed ON allowed.asset_type = asset.asset_type
    WHERE asset.asset_id = NEW.asset_id AND allowed.tax_model_id = NEW.tax_model_id AND allowed.model_version = NEW.model_version AND allowed.classification_code = NEW.classification_code
  ) THEN RAISE(ABORT, 'tax_assignment_asset_type_invalid') END;
  SELECT CASE WHEN NEW.supersedes_assignment_revision_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM current_asset_tax_assignment old
    WHERE old.assignment_revision_id = NEW.supersedes_assignment_revision_id AND old.asset_id = NEW.asset_id AND old.tax_model_id = NEW.tax_model_id AND old.model_version = NEW.model_version
  ) THEN RAISE(ABORT, 'tax_assignment_supersession_invalid') END;
  SELECT CASE WHEN NEW.status = 'active' AND EXISTS (
    SELECT 1 FROM current_asset_tax_assignment existing
    WHERE existing.asset_id = NEW.asset_id AND existing.tax_model_id = NEW.tax_model_id AND existing.model_version = NEW.model_version AND existing.status = 'active'
      AND existing.assignment_revision_id != COALESCE(NEW.supersedes_assignment_revision_id, '')
      AND COALESCE(existing.effective_to, '9999-12-31') >= NEW.effective_from
      AND COALESCE(NEW.effective_to, '9999-12-31') >= existing.effective_from
  ) THEN RAISE(ABORT, 'tax_assignment_period_overlap') END;
END;

CREATE TRIGGER tax_configuration_validate BEFORE INSERT ON tax_configuration BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'tax_app') THEN RAISE(ABORT, 'tax_configuration_writer_invalid') END;
END;

CREATE TRIGGER tax_parameter_validate BEFORE INSERT ON tax_parameter_revision BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'tax_app') THEN RAISE(ABORT, 'tax_parameter_writer_invalid') END;
  SELECT CASE WHEN NEW.scope_type = 'account' AND NOT EXISTS (
    SELECT 1 FROM tax_configuration configuration
    JOIN account_entity account ON account.portfolio_id = configuration.portfolio_id
    WHERE configuration.tax_configuration_id = NEW.tax_configuration_id AND account.account_id = NEW.account_id
  ) THEN RAISE(ABORT, 'tax_parameter_account_scope_invalid') END;
  SELECT CASE WHEN NEW.supersedes_parameter_revision_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM current_tax_parameter old
    WHERE old.parameter_revision_id = NEW.supersedes_parameter_revision_id
      AND old.tax_configuration_id = NEW.tax_configuration_id AND old.parameter_code = NEW.parameter_code
      AND old.scope_type = NEW.scope_type AND COALESCE(old.account_id, '') = COALESCE(NEW.account_id, '')
  ) THEN RAISE(ABORT, 'tax_parameter_supersession_invalid') END;
  SELECT CASE WHEN NEW.supersedes_parameter_revision_id IS NULL AND EXISTS (
    SELECT 1 FROM current_tax_parameter existing
    WHERE existing.tax_configuration_id = NEW.tax_configuration_id AND existing.parameter_code = NEW.parameter_code
      AND existing.scope_type = NEW.scope_type AND COALESCE(existing.account_id, '') = COALESCE(NEW.account_id, '')
  ) THEN RAISE(ABORT, 'tax_parameter_current_duplicate') END;
END;

CREATE TRIGGER tax_projection_run_validate BEFORE INSERT ON tax_projection_run BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM ledger_command_receipt WHERE command_id = NEW.command_id AND writer_area = 'tax_worker') THEN RAISE(ABORT, 'tax_projection_writer_invalid') END;
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM tax_configuration configuration
    JOIN tax_model_definition model ON model.tax_model_id = configuration.tax_model_id AND model.model_version = configuration.model_version
    WHERE configuration.tax_configuration_id = NEW.tax_configuration_id AND model.rules_fingerprint = NEW.rules_fingerprint
  ) THEN RAISE(ABORT, 'tax_projection_rules_mismatch') END;
  SELECT CASE WHEN NEW.projection_mode = 'realized_annual' AND NOT EXISTS (
    SELECT 1 FROM tax_configuration configuration
    WHERE configuration.tax_configuration_id = NEW.tax_configuration_id AND configuration.tax_year = NEW.tax_year
  ) THEN RAISE(ABORT, 'tax_projection_year_mismatch') END;
END;

CREATE TRIGGER portfolio_entity_no_update BEFORE UPDATE ON portfolio_entity BEGIN SELECT RAISE(ABORT, 'portfolio_entity_immutable'); END;
CREATE TRIGGER portfolio_entity_no_delete BEFORE DELETE ON portfolio_entity BEGIN SELECT RAISE(ABORT, 'portfolio_entity_immutable'); END;
CREATE TRIGGER portfolio_revision_no_update BEFORE UPDATE ON portfolio_revision BEGIN SELECT RAISE(ABORT, 'portfolio_revision_immutable'); END;
CREATE TRIGGER portfolio_revision_no_delete BEFORE DELETE ON portfolio_revision BEGIN SELECT RAISE(ABORT, 'portfolio_revision_immutable'); END;
CREATE TRIGGER account_entity_no_update BEFORE UPDATE ON account_entity BEGIN SELECT RAISE(ABORT, 'account_entity_immutable'); END;
CREATE TRIGGER account_entity_no_delete BEFORE DELETE ON account_entity BEGIN SELECT RAISE(ABORT, 'account_entity_immutable'); END;
CREATE TRIGGER account_revision_no_update BEFORE UPDATE ON account_revision BEGIN SELECT RAISE(ABORT, 'account_revision_immutable'); END;
CREATE TRIGGER account_revision_no_delete BEFORE DELETE ON account_revision BEGIN SELECT RAISE(ABORT, 'account_revision_immutable'); END;
CREATE TRIGGER asset_entity_no_update BEFORE UPDATE ON asset_entity BEGIN SELECT RAISE(ABORT, 'asset_entity_immutable'); END;
CREATE TRIGGER asset_entity_no_delete BEFORE DELETE ON asset_entity BEGIN SELECT RAISE(ABORT, 'asset_entity_immutable'); END;
CREATE TRIGGER asset_revision_no_update BEFORE UPDATE ON asset_revision BEGIN SELECT RAISE(ABORT, 'asset_revision_immutable'); END;
CREATE TRIGGER asset_revision_no_delete BEFORE DELETE ON asset_revision BEGIN SELECT RAISE(ABORT, 'asset_revision_immutable'); END;
CREATE TRIGGER transaction_fact_no_update BEFORE UPDATE ON transaction_fact BEGIN SELECT RAISE(ABORT, 'transaction_fact_immutable'); END;
CREATE TRIGGER transaction_fact_no_delete BEFORE DELETE ON transaction_fact BEGIN SELECT RAISE(ABORT, 'transaction_fact_immutable'); END;
CREATE TRIGGER transaction_void_no_update BEFORE UPDATE ON transaction_void BEGIN SELECT RAISE(ABORT, 'transaction_void_immutable'); END;
CREATE TRIGGER transaction_void_no_delete BEFORE DELETE ON transaction_void BEGIN SELECT RAISE(ABORT, 'transaction_void_immutable'); END;
CREATE TRIGGER tax_model_definition_no_update BEFORE UPDATE ON tax_model_definition BEGIN SELECT RAISE(ABORT, 'tax_model_definition_immutable'); END;
CREATE TRIGGER tax_model_definition_no_delete BEFORE DELETE ON tax_model_definition BEGIN SELECT RAISE(ABORT, 'tax_model_definition_immutable'); END;
CREATE TRIGGER tax_classification_definition_no_update BEFORE UPDATE ON tax_classification_definition BEGIN SELECT RAISE(ABORT, 'tax_classification_definition_immutable'); END;
CREATE TRIGGER tax_classification_definition_no_delete BEFORE DELETE ON tax_classification_definition BEGIN SELECT RAISE(ABORT, 'tax_classification_definition_immutable'); END;
CREATE TRIGGER tax_classification_asset_type_no_update BEFORE UPDATE ON tax_classification_asset_type BEGIN SELECT RAISE(ABORT, 'tax_classification_asset_type_immutable'); END;
CREATE TRIGGER tax_classification_asset_type_no_delete BEFORE DELETE ON tax_classification_asset_type BEGIN SELECT RAISE(ABORT, 'tax_classification_asset_type_immutable'); END;
CREATE TRIGGER asset_tax_assignment_no_update BEFORE UPDATE ON asset_tax_assignment_revision BEGIN SELECT RAISE(ABORT, 'tax_assignment_immutable'); END;
CREATE TRIGGER asset_tax_assignment_no_delete BEFORE DELETE ON asset_tax_assignment_revision BEGIN SELECT RAISE(ABORT, 'tax_assignment_immutable'); END;
CREATE TRIGGER tax_configuration_no_update BEFORE UPDATE ON tax_configuration BEGIN SELECT RAISE(ABORT, 'tax_configuration_immutable'); END;
CREATE TRIGGER tax_configuration_no_delete BEFORE DELETE ON tax_configuration BEGIN SELECT RAISE(ABORT, 'tax_configuration_immutable'); END;
CREATE TRIGGER tax_parameter_no_update BEFORE UPDATE ON tax_parameter_revision BEGIN SELECT RAISE(ABORT, 'tax_parameter_immutable'); END;
CREATE TRIGGER tax_parameter_no_delete BEFORE DELETE ON tax_parameter_revision BEGIN SELECT RAISE(ABORT, 'tax_parameter_immutable'); END;
CREATE TRIGGER tax_projection_run_no_update BEFORE UPDATE ON tax_projection_run BEGIN SELECT RAISE(ABORT, 'tax_projection_run_immutable'); END;
CREATE TRIGGER tax_projection_run_no_delete BEFORE DELETE ON tax_projection_run BEGIN SELECT RAISE(ABORT, 'tax_projection_run_immutable'); END;

COMMIT;
