PRAGMA foreign_keys = ON;
PRAGMA user_version = 2901;

BEGIN IMMEDIATE;

CREATE TABLE cash_coverage_store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 2901),
  tenant_id TEXT NOT NULL CHECK (length(tenant_id) BETWEEN 3 AND 64),
  user_id TEXT NOT NULL CHECK (length(user_id) BETWEEN 3 AND 64),
  data_space_id TEXT NOT NULL CHECK (length(data_space_id) BETWEEN 3 AND 64),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20 AND substr(created_at_utc, 11, 1) = 'T' AND substr(created_at_utc, 20, 1) = 'Z')
) STRICT;

CREATE TABLE cash_coverage_confirmation_attempt (
  confirmation_fingerprint TEXT PRIMARY KEY CHECK (length(confirmation_fingerprint) = 64 AND confirmation_fingerprint NOT GLOB '*[^a-f0-9]*'),
  request_ref TEXT NOT NULL CHECK (request_ref LIKE 'ccrq_%' AND length(request_ref) = 37),
  preview_fingerprint TEXT NOT NULL CHECK (length(preview_fingerprint) = 64 AND preview_fingerprint NOT GLOB '*[^a-f0-9]*'),
  attempted_at_utc TEXT NOT NULL CHECK (length(attempted_at_utc) = 20 AND substr(attempted_at_utc, 11, 1) = 'T' AND substr(attempted_at_utc, 20, 1) = 'Z'),
  attempt_status TEXT NOT NULL CHECK (attempt_status = 'attempted')
) STRICT;

CREATE TABLE cash_coverage_attempt_evidence (
  confirmation_fingerprint TEXT PRIMARY KEY REFERENCES cash_coverage_confirmation_attempt(confirmation_fingerprint),
  context_fingerprint TEXT NOT NULL CHECK (length(context_fingerprint) = 64 AND context_fingerprint NOT GLOB '*[^a-f0-9]*'),
  input_mode TEXT NOT NULL CHECK (input_mode IN ('manual_entry','reviewed_import')),
  source_candidate_fingerprint TEXT CHECK (source_candidate_fingerprint IS NULL OR (length(source_candidate_fingerprint) = 64 AND source_candidate_fingerprint NOT GLOB '*[^a-f0-9]*')),
  command_payload_json TEXT NOT NULL CHECK (length(command_payload_json) BETWEEN 2 AND 32000000),
  command_payload_fingerprint TEXT NOT NULL CHECK (length(command_payload_fingerprint) = 64 AND command_payload_fingerprint NOT GLOB '*[^a-f0-9]*'),
  confirmation_payload_json TEXT NOT NULL CHECK (length(confirmation_payload_json) BETWEEN 2 AND 32000000),
  canonical_fingerprint TEXT NOT NULL CHECK (length(canonical_fingerprint) = 64 AND canonical_fingerprint NOT GLOB '*[^a-f0-9]*'),
  recorded_at_utc TEXT NOT NULL CHECK (length(recorded_at_utc) = 20 AND substr(recorded_at_utc, 11, 1) = 'T' AND substr(recorded_at_utc, 20, 1) = 'Z'),
  CHECK ((input_mode='manual_entry' AND source_candidate_fingerprint IS NULL) OR (input_mode='reviewed_import' AND source_candidate_fingerprint IS NOT NULL))
) STRICT;

CREATE TABLE cash_coverage_command_receipt (
  command_id TEXT PRIMARY KEY CHECK (command_id LIKE 'ccmd_%' AND length(command_id) = 37),
  request_ref TEXT NOT NULL UNIQUE CHECK (request_ref LIKE 'ccrq_%' AND length(request_ref) = 37),
  writer_area TEXT NOT NULL CHECK (writer_area = 'data_app'),
  action_type TEXT NOT NULL CHECK (action_type IN ('declare_coverage','record_cash_event','record_interest_income','record_reconciliation','revise_cash_coverage')),
  actor_id TEXT NOT NULL CHECK (length(actor_id) BETWEEN 3 AND 80),
  payload_fingerprint TEXT NOT NULL CHECK (length(payload_fingerprint) = 64 AND payload_fingerprint NOT GLOB '*[^a-f0-9]*'),
  canonical_fingerprint TEXT NOT NULL CHECK (length(canonical_fingerprint) = 64 AND canonical_fingerprint NOT GLOB '*[^a-f0-9]*'),
  confirmation_fingerprint TEXT NOT NULL UNIQUE REFERENCES cash_coverage_confirmation_attempt(confirmation_fingerprint),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc) = 20 AND substr(committed_at_utc, 11, 1) = 'T' AND substr(committed_at_utc, 20, 1) = 'Z')
) STRICT;

CREATE TABLE cash_coverage_period (
  coverage_id TEXT PRIMARY KEY CHECK (coverage_id LIKE 'cvg_%' AND length(coverage_id) = 36),
  portfolio_id TEXT NOT NULL CHECK (portfolio_id LIKE 'ptf_%' AND length(portfolio_id) BETWEEN 8 AND 64),
  account_id TEXT NOT NULL CHECK (account_id LIKE 'acc_%' AND length(account_id) BETWEEN 8 AND 64),
  cash_asset_id TEXT NOT NULL CHECK (cash_asset_id LIKE 'ast_%' AND length(cash_asset_id) BETWEEN 8 AND 64),
  currency TEXT NOT NULL CHECK (length(currency) = 3 AND currency = upper(currency) AND currency NOT GLOB '*[^A-Z]*'),
  effective_from TEXT NOT NULL CHECK (length(effective_from) = 10 AND substr(effective_from, 5, 1) = '-' AND substr(effective_from, 8, 1) = '-'),
  effective_to TEXT CHECK (effective_to IS NULL OR (length(effective_to) = 10 AND substr(effective_to, 5, 1) = '-' AND substr(effective_to, 8, 1) = '-')),
  coverage_mode TEXT NOT NULL CHECK (coverage_mode IN ('not_tracked','income_only','partial','complete_reconciled')),
  command_id TEXT NOT NULL REFERENCES cash_coverage_command_receipt(command_id),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc) = 20 AND substr(committed_at_utc, 11, 1) = 'T' AND substr(committed_at_utc, 20, 1) = 'Z'),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
) STRICT;

CREATE TABLE cash_coverage_event (
  cash_event_id TEXT PRIMARY KEY CHECK (cash_event_id LIKE 'csh_%' AND length(cash_event_id) = 36),
  event_type TEXT NOT NULL CHECK (event_type IN ('opening_balance','deposit','withdrawal','transfer')),
  portfolio_id TEXT NOT NULL CHECK (portfolio_id LIKE 'ptf_%' AND length(portfolio_id) BETWEEN 8 AND 64),
  account_id TEXT NOT NULL CHECK (account_id LIKE 'acc_%' AND length(account_id) BETWEEN 8 AND 64),
  related_account_id TEXT CHECK (related_account_id IS NULL OR (related_account_id LIKE 'acc_%' AND length(related_account_id) BETWEEN 8 AND 64)),
  cash_asset_id TEXT NOT NULL CHECK (cash_asset_id LIKE 'ast_%' AND length(cash_asset_id) BETWEEN 8 AND 64),
  currency TEXT NOT NULL CHECK (length(currency) = 3 AND currency = upper(currency) AND currency NOT GLOB '*[^A-Z]*'),
  event_time_evidence TEXT NOT NULL CHECK (event_time_evidence IN ('exact_local_zone','utc_only_legacy')),
  local_date TEXT NOT NULL CHECK (length(local_date) = 10 AND substr(local_date, 5, 1) = '-' AND substr(local_date, 8, 1) = '-'),
  local_time TEXT CHECK (local_time IS NULL OR (length(local_time) = 8 AND substr(local_time, 3, 1) = ':' AND substr(local_time, 6, 1) = ':')),
  time_zone TEXT CHECK (time_zone IS NULL OR length(time_zone) BETWEEN 1 AND 80),
  effective_at_utc TEXT NOT NULL CHECK (length(effective_at_utc) = 20 AND substr(effective_at_utc, 11, 1) = 'T' AND substr(effective_at_utc, 20, 1) = 'Z'),
  amount_decimal TEXT NOT NULL CHECK (
    typeof(amount_decimal) = 'text' AND length(amount_decimal) BETWEEN 1 AND 80
    AND amount_decimal NOT GLOB '*[^0-9.-]*' AND amount_decimal NOT IN ('','-','.','-.','-0')
    AND instr(substr(amount_decimal,2),'-') = 0
    AND (length(amount_decimal)-length(replace(amount_decimal,'.',''))) <= 1
    AND (instr(amount_decimal,'.') = 0 OR (substr(amount_decimal,-1,1) NOT IN ('.','0') AND instr(amount_decimal,'.') > CASE WHEN substr(amount_decimal,1,1)='-' THEN 2 ELSE 1 END))
    AND (ltrim(amount_decimal,'-')='0' OR ltrim(amount_decimal,'-') LIKE '0.%' OR substr(ltrim(amount_decimal,'-'),1,1) BETWEEN '1' AND '9')
  ),
  flow_classification TEXT NOT NULL CHECK (flow_classification IN ('not_applicable','unclassified','external_contribution','external_withdrawal','internal_unlinked','investment_settlement','income_receipt','fee_or_tax_payment')),
  command_id TEXT NOT NULL REFERENCES cash_coverage_command_receipt(command_id),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc) = 20 AND substr(committed_at_utc, 11, 1) = 'T' AND substr(committed_at_utc, 20, 1) = 'Z'),
  CHECK ((event_type='transfer' AND related_account_id IS NOT NULL AND related_account_id!=account_id) OR (event_type!='transfer' AND related_account_id IS NULL)),
  CHECK ((event_time_evidence='exact_local_zone' AND local_time IS NOT NULL AND time_zone IS NOT NULL) OR (event_time_evidence='utc_only_legacy' AND local_time IS NULL AND time_zone IS NULL))
) STRICT;

CREATE TABLE cash_income_event (
  income_event_id TEXT PRIMARY KEY CHECK (income_event_id LIKE 'inc_%' AND length(income_event_id) = 36),
  income_type TEXT NOT NULL CHECK (income_type = 'interest'),
  portfolio_id TEXT NOT NULL CHECK (portfolio_id LIKE 'ptf_%' AND length(portfolio_id) BETWEEN 8 AND 64),
  account_id TEXT NOT NULL CHECK (account_id LIKE 'acc_%' AND length(account_id) BETWEEN 8 AND 64),
  cash_asset_id TEXT NOT NULL CHECK (cash_asset_id LIKE 'ast_%' AND length(cash_asset_id) BETWEEN 8 AND 64),
  currency TEXT NOT NULL CHECK (length(currency) = 3 AND currency = upper(currency) AND currency NOT GLOB '*[^A-Z]*'),
  local_date TEXT NOT NULL CHECK (length(local_date) = 10 AND substr(local_date,5,1)='-' AND substr(local_date,8,1)='-'),
  gross_income_decimal TEXT NOT NULL CHECK (
    typeof(gross_income_decimal)='text' AND length(gross_income_decimal) BETWEEN 1 AND 80
    AND gross_income_decimal NOT GLOB '*[^0-9.]*' AND gross_income_decimal NOT IN ('','.','0')
    AND (length(gross_income_decimal)-length(replace(gross_income_decimal,'.',''))) <= 1
    AND (instr(gross_income_decimal,'.')=0 OR (substr(gross_income_decimal,-1,1) NOT IN ('.','0') AND instr(gross_income_decimal,'.')>1))
    AND (gross_income_decimal LIKE '0.%' OR substr(gross_income_decimal,1,1) BETWEEN '1' AND '9')
  ),
  linked_cash_event_id TEXT REFERENCES cash_coverage_event(cash_event_id),
  command_id TEXT NOT NULL REFERENCES cash_coverage_command_receipt(command_id),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=20 AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,20,1)='Z')
) STRICT;

CREATE TABLE cash_coverage_reconciliation (
  reconciliation_id TEXT PRIMARY KEY CHECK (reconciliation_id LIKE 'rec_%' AND length(reconciliation_id)=36),
  portfolio_id TEXT NOT NULL CHECK (portfolio_id LIKE 'ptf_%' AND length(portfolio_id) BETWEEN 8 AND 64),
  account_id TEXT NOT NULL CHECK (account_id LIKE 'acc_%' AND length(account_id) BETWEEN 8 AND 64),
  cash_asset_id TEXT NOT NULL CHECK (cash_asset_id LIKE 'ast_%' AND length(cash_asset_id) BETWEEN 8 AND 64),
  currency TEXT NOT NULL CHECK (length(currency)=3 AND currency=upper(currency) AND currency NOT GLOB '*[^A-Z]*'),
  as_of_date TEXT NOT NULL CHECK (length(as_of_date)=10 AND substr(as_of_date,5,1)='-' AND substr(as_of_date,8,1)='-'),
  observed_balance_decimal TEXT NOT NULL CHECK (
    typeof(observed_balance_decimal)='text' AND length(observed_balance_decimal) BETWEEN 1 AND 80
    AND observed_balance_decimal NOT GLOB '*[^0-9.-]*' AND observed_balance_decimal NOT IN ('','-','.','-.','-0')
    AND instr(substr(observed_balance_decimal,2),'-')=0
    AND (length(observed_balance_decimal)-length(replace(observed_balance_decimal,'.',''))) <= 1
    AND (instr(observed_balance_decimal,'.')=0 OR (substr(observed_balance_decimal,-1,1) NOT IN ('.','0') AND instr(observed_balance_decimal,'.')>CASE WHEN substr(observed_balance_decimal,1,1)='-' THEN 2 ELSE 1 END))
    AND (ltrim(observed_balance_decimal,'-')='0' OR ltrim(observed_balance_decimal,'-') LIKE '0.%' OR substr(ltrim(observed_balance_decimal,'-'),1,1) BETWEEN '1' AND '9')
  ),
  evidence_fingerprint TEXT NOT NULL CHECK (length(evidence_fingerprint)=64 AND evidence_fingerprint NOT GLOB '*[^a-f0-9]*'),
  command_id TEXT NOT NULL REFERENCES cash_coverage_command_receipt(command_id),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=20 AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,20,1)='Z')
) STRICT;

CREATE TABLE cash_coverage_fact_supersession (
  supersession_id TEXT PRIMARY KEY CHECK (supersession_id LIKE 'css_%' AND length(supersession_id)=36),
  predecessor_kind TEXT NOT NULL CHECK (predecessor_kind IN ('coverage_period','cash_event','income_event','reconciliation')),
  predecessor_fact_id TEXT NOT NULL CHECK (length(predecessor_fact_id) BETWEEN 8 AND 64),
  replacement_kind TEXT CHECK (replacement_kind IS NULL OR replacement_kind IN ('coverage_period','cash_event','income_event','reconciliation')),
  replacement_fact_id TEXT CHECK (replacement_fact_id IS NULL OR length(replacement_fact_id) BETWEEN 8 AND 64),
  revision_action TEXT NOT NULL CHECK (revision_action IN ('correct','supersede','void')),
  command_id TEXT NOT NULL REFERENCES cash_coverage_command_receipt(command_id),
  committed_at_utc TEXT NOT NULL CHECK (length(committed_at_utc)=20 AND substr(committed_at_utc,11,1)='T' AND substr(committed_at_utc,20,1)='Z'),
  UNIQUE (predecessor_kind, predecessor_fact_id),
  UNIQUE (replacement_kind, replacement_fact_id),
  CHECK (
    (revision_action='void' AND replacement_kind IS NULL AND replacement_fact_id IS NULL)
    OR
    (revision_action IN ('correct','supersede') AND replacement_kind=predecessor_kind AND replacement_fact_id IS NOT NULL)
  )
) STRICT;

CREATE TABLE cash_coverage_recovery_attempt (
  recovery_confirmation_fingerprint TEXT PRIMARY KEY CHECK (length(recovery_confirmation_fingerprint)=64 AND recovery_confirmation_fingerprint NOT GLOB '*[^a-f0-9]*'),
  original_confirmation_fingerprint TEXT NOT NULL REFERENCES cash_coverage_confirmation_attempt(confirmation_fingerprint),
  recovery_plan_fingerprint TEXT NOT NULL CHECK (length(recovery_plan_fingerprint)=64 AND recovery_plan_fingerprint NOT GLOB '*[^a-f0-9]*'),
  attempted_at_utc TEXT NOT NULL CHECK (length(attempted_at_utc)=20 AND substr(attempted_at_utc,11,1)='T' AND substr(attempted_at_utc,20,1)='Z'),
  attempt_status TEXT NOT NULL CHECK (attempt_status='attempted'),
  UNIQUE (original_confirmation_fingerprint)
) STRICT;

CREATE TABLE cash_coverage_schema_migration_recovery_attempt (
  recovery_confirmation_fingerprint TEXT PRIMARY KEY CHECK (length(recovery_confirmation_fingerprint)=64 AND recovery_confirmation_fingerprint NOT GLOB '*[^a-f0-9]*'),
  original_confirmation_fingerprint TEXT NOT NULL CHECK (length(original_confirmation_fingerprint)=64 AND original_confirmation_fingerprint NOT GLOB '*[^a-f0-9]*'),
  migration_plan_fingerprint TEXT NOT NULL CHECK (length(migration_plan_fingerprint)=64 AND migration_plan_fingerprint NOT GLOB '*[^a-f0-9]*'),
  recovery_plan_fingerprint TEXT NOT NULL CHECK (length(recovery_plan_fingerprint)=64 AND recovery_plan_fingerprint NOT GLOB '*[^a-f0-9]*'),
  attempted_at_utc TEXT NOT NULL CHECK (length(attempted_at_utc)=20 AND substr(attempted_at_utc,11,1)='T' AND substr(attempted_at_utc,20,1)='Z'),
  attempt_status TEXT NOT NULL CHECK (attempt_status='attempted'),
  UNIQUE (original_confirmation_fingerprint)
) STRICT;

CREATE TABLE cash_coverage_schema_migration_receipt (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id=1),
  migration_id TEXT NOT NULL UNIQUE CHECK (migration_id LIKE 'ccm_%' AND length(migration_id)=36),
  source_schema_version INTEGER NOT NULL CHECK (source_schema_version=2900),
  target_schema_version INTEGER NOT NULL CHECK (target_schema_version=2901),
  source_store_fingerprint TEXT NOT NULL CHECK (length(source_store_fingerprint)=64 AND source_store_fingerprint NOT GLOB '*[^a-f0-9]*'),
  migration_plan_fingerprint TEXT NOT NULL CHECK (length(migration_plan_fingerprint)=64 AND migration_plan_fingerprint NOT GLOB '*[^a-f0-9]*'),
  legacy_attempt_set_fingerprint TEXT NOT NULL CHECK (length(legacy_attempt_set_fingerprint)=64 AND legacy_attempt_set_fingerprint NOT GLOB '*[^a-f0-9]*'),
  legacy_command_set_fingerprint TEXT NOT NULL CHECK (length(legacy_command_set_fingerprint)=64 AND legacy_command_set_fingerprint NOT GLOB '*[^a-f0-9]*'),
  source_fact_projection_fingerprint TEXT NOT NULL CHECK (length(source_fact_projection_fingerprint)=64 AND source_fact_projection_fingerprint NOT GLOB '*[^a-f0-9]*'),
  target_fact_projection_fingerprint TEXT NOT NULL CHECK (target_fact_projection_fingerprint=source_fact_projection_fingerprint),
  period_count INTEGER NOT NULL CHECK (period_count>=0),
  cash_event_count INTEGER NOT NULL CHECK (cash_event_count>=0),
  income_event_count INTEGER NOT NULL CHECK (income_event_count>=0),
  reconciliation_count INTEGER NOT NULL CHECK (reconciliation_count>=0),
  migrated_at_utc TEXT NOT NULL CHECK (length(migrated_at_utc)=20 AND substr(migrated_at_utc,11,1)='T' AND substr(migrated_at_utc,20,1)='Z'),
  confirmation_fingerprint TEXT NOT NULL CHECK (length(confirmation_fingerprint)=64 AND confirmation_fingerprint NOT GLOB '*[^a-f0-9]*'),
  recovery_confirmation_fingerprint TEXT REFERENCES cash_coverage_schema_migration_recovery_attempt(recovery_confirmation_fingerprint),
  receipt_fingerprint TEXT NOT NULL UNIQUE CHECK (length(receipt_fingerprint)=64 AND receipt_fingerprint NOT GLOB '*[^a-f0-9]*')
) STRICT;

CREATE TABLE cash_coverage_command_provenance (
  command_id TEXT PRIMARY KEY REFERENCES cash_coverage_command_receipt(command_id),
  operation_type TEXT NOT NULL CHECK (operation_type IN ('create','correct','supersede','void')),
  input_mode TEXT NOT NULL CHECK (input_mode IN ('manual_entry','reviewed_import')),
  source_candidate_fingerprint TEXT CHECK (source_candidate_fingerprint IS NULL OR (length(source_candidate_fingerprint)=64 AND source_candidate_fingerprint NOT GLOB '*[^a-f0-9]*')),
  predecessor_command_id TEXT REFERENCES cash_coverage_command_receipt(command_id),
  predecessor_set_fingerprint TEXT CHECK (predecessor_set_fingerprint IS NULL OR (length(predecessor_set_fingerprint)=64 AND predecessor_set_fingerprint NOT GLOB '*[^a-f0-9]*')),
  before_state_fingerprint TEXT NOT NULL CHECK (length(before_state_fingerprint)=64 AND before_state_fingerprint NOT GLOB '*[^a-f0-9]*'),
  after_state_fingerprint TEXT NOT NULL CHECK (length(after_state_fingerprint)=64 AND after_state_fingerprint NOT GLOB '*[^a-f0-9]*'),
  recovery_confirmation_fingerprint TEXT REFERENCES cash_coverage_recovery_attempt(recovery_confirmation_fingerprint),
  predecessor_preserved INTEGER NOT NULL CHECK (predecessor_preserved=1),
  receipt_fingerprint TEXT NOT NULL UNIQUE CHECK (length(receipt_fingerprint)=64 AND receipt_fingerprint NOT GLOB '*[^a-f0-9]*'),
  CHECK (
    (operation_type='create' AND predecessor_command_id IS NULL AND predecessor_set_fingerprint IS NULL)
    OR
    (operation_type!='create' AND predecessor_set_fingerprint IS NOT NULL)
  ),
  CHECK ((input_mode='manual_entry' AND source_candidate_fingerprint IS NULL) OR (input_mode='reviewed_import' AND source_candidate_fingerprint IS NOT NULL))
) STRICT;

CREATE TRIGGER cash_coverage_period_overlap BEFORE INSERT ON cash_coverage_period BEGIN
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM cash_coverage_period existing
    WHERE existing.account_id=NEW.account_id
      AND NOT EXISTS (SELECT 1 FROM cash_coverage_fact_supersession s WHERE s.predecessor_kind='coverage_period' AND s.predecessor_fact_id=existing.coverage_id)
      AND COALESCE(existing.effective_to,'9999-12-31')>=NEW.effective_from
      AND COALESCE(NEW.effective_to,'9999-12-31')>=existing.effective_from
  ) THEN RAISE(ABORT,'cash_coverage_period_overlap') END;
END;

CREATE TRIGGER cash_coverage_binding_no_update BEFORE UPDATE ON cash_coverage_store_binding BEGIN SELECT RAISE(ABORT,'cash_coverage_binding_immutable'); END;
CREATE TRIGGER cash_coverage_binding_no_delete BEFORE DELETE ON cash_coverage_store_binding BEGIN SELECT RAISE(ABORT,'cash_coverage_binding_immutable'); END;
CREATE TRIGGER cash_coverage_attempt_no_update BEFORE UPDATE ON cash_coverage_confirmation_attempt BEGIN SELECT RAISE(ABORT,'cash_coverage_attempt_immutable'); END;
CREATE TRIGGER cash_coverage_attempt_no_delete BEFORE DELETE ON cash_coverage_confirmation_attempt BEGIN SELECT RAISE(ABORT,'cash_coverage_attempt_immutable'); END;
CREATE TRIGGER cash_coverage_attempt_evidence_no_update BEFORE UPDATE ON cash_coverage_attempt_evidence BEGIN SELECT RAISE(ABORT,'cash_coverage_attempt_evidence_immutable'); END;
CREATE TRIGGER cash_coverage_attempt_evidence_no_delete BEFORE DELETE ON cash_coverage_attempt_evidence BEGIN SELECT RAISE(ABORT,'cash_coverage_attempt_evidence_immutable'); END;
CREATE TRIGGER cash_coverage_receipt_no_update BEFORE UPDATE ON cash_coverage_command_receipt BEGIN SELECT RAISE(ABORT,'cash_coverage_receipt_immutable'); END;
CREATE TRIGGER cash_coverage_receipt_no_delete BEFORE DELETE ON cash_coverage_command_receipt BEGIN SELECT RAISE(ABORT,'cash_coverage_receipt_immutable'); END;
CREATE TRIGGER cash_coverage_period_no_update BEFORE UPDATE ON cash_coverage_period BEGIN SELECT RAISE(ABORT,'cash_coverage_period_immutable'); END;
CREATE TRIGGER cash_coverage_period_no_delete BEFORE DELETE ON cash_coverage_period BEGIN SELECT RAISE(ABORT,'cash_coverage_period_immutable'); END;
CREATE TRIGGER cash_coverage_event_no_update BEFORE UPDATE ON cash_coverage_event BEGIN SELECT RAISE(ABORT,'cash_coverage_event_immutable'); END;
CREATE TRIGGER cash_coverage_event_no_delete BEFORE DELETE ON cash_coverage_event BEGIN SELECT RAISE(ABORT,'cash_coverage_event_immutable'); END;
CREATE TRIGGER cash_income_event_no_update BEFORE UPDATE ON cash_income_event BEGIN SELECT RAISE(ABORT,'cash_income_event_immutable'); END;
CREATE TRIGGER cash_income_event_no_delete BEFORE DELETE ON cash_income_event BEGIN SELECT RAISE(ABORT,'cash_income_event_immutable'); END;
CREATE TRIGGER cash_coverage_reconciliation_no_update BEFORE UPDATE ON cash_coverage_reconciliation BEGIN SELECT RAISE(ABORT,'cash_coverage_reconciliation_immutable'); END;
CREATE TRIGGER cash_coverage_reconciliation_no_delete BEFORE DELETE ON cash_coverage_reconciliation BEGIN SELECT RAISE(ABORT,'cash_coverage_reconciliation_immutable'); END;
CREATE TRIGGER cash_coverage_supersession_no_update BEFORE UPDATE ON cash_coverage_fact_supersession BEGIN SELECT RAISE(ABORT,'cash_coverage_supersession_immutable'); END;
CREATE TRIGGER cash_coverage_supersession_no_delete BEFORE DELETE ON cash_coverage_fact_supersession BEGIN SELECT RAISE(ABORT,'cash_coverage_supersession_immutable'); END;
CREATE TRIGGER cash_coverage_recovery_attempt_no_update BEFORE UPDATE ON cash_coverage_recovery_attempt BEGIN SELECT RAISE(ABORT,'cash_coverage_recovery_attempt_immutable'); END;
CREATE TRIGGER cash_coverage_recovery_attempt_no_delete BEFORE DELETE ON cash_coverage_recovery_attempt BEGIN SELECT RAISE(ABORT,'cash_coverage_recovery_attempt_immutable'); END;
CREATE TRIGGER cash_coverage_migration_recovery_attempt_no_update BEFORE UPDATE ON cash_coverage_schema_migration_recovery_attempt BEGIN SELECT RAISE(ABORT,'cash_coverage_migration_recovery_attempt_immutable'); END;
CREATE TRIGGER cash_coverage_migration_recovery_attempt_no_delete BEFORE DELETE ON cash_coverage_schema_migration_recovery_attempt BEGIN SELECT RAISE(ABORT,'cash_coverage_migration_recovery_attempt_immutable'); END;
CREATE TRIGGER cash_coverage_migration_receipt_no_update BEFORE UPDATE ON cash_coverage_schema_migration_receipt BEGIN SELECT RAISE(ABORT,'cash_coverage_migration_receipt_immutable'); END;
CREATE TRIGGER cash_coverage_migration_receipt_no_delete BEFORE DELETE ON cash_coverage_schema_migration_receipt BEGIN SELECT RAISE(ABORT,'cash_coverage_migration_receipt_immutable'); END;
CREATE TRIGGER cash_coverage_provenance_no_update BEFORE UPDATE ON cash_coverage_command_provenance BEGIN SELECT RAISE(ABORT,'cash_coverage_provenance_immutable'); END;
CREATE TRIGGER cash_coverage_provenance_no_delete BEFORE DELETE ON cash_coverage_command_provenance BEGIN SELECT RAISE(ABORT,'cash_coverage_provenance_immutable'); END;

COMMIT;
