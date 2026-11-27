PRAGMA foreign_keys = ON;
PRAGMA user_version = 3100;

CREATE TABLE realized_state_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 3100),
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  data_space_id TEXT NOT NULL,
  algorithm_id TEXT NOT NULL CHECK (algorithm_id = 'semantic_realized_fifo_v2'),
  algorithm_fingerprint TEXT NOT NULL CHECK (length(algorithm_fingerprint) = 64),
  created_at_utc TEXT NOT NULL
) STRICT;

CREATE TABLE realized_state_job (
  job_ref TEXT PRIMARY KEY CHECK (job_ref LIKE 'rsj_%'),
  source_generation_ref TEXT NOT NULL CHECK (source_generation_ref LIKE 'gen_%'),
  source_ledger_fingerprint TEXT NOT NULL CHECK (length(source_ledger_fingerprint) = 64),
  source_activity_set_fingerprint TEXT NOT NULL CHECK (length(source_activity_set_fingerprint) = 64),
  request_mode TEXT NOT NULL CHECK (request_mode IN ('incremental', 'full_rebuild')),
  prior_global_artifact_ref TEXT,
  requested_at_utc TEXT NOT NULL,
  source_world_count INTEGER NOT NULL CHECK (source_world_count > 0),
  job_fingerprint TEXT NOT NULL UNIQUE CHECK (length(job_fingerprint) = 64)
) STRICT;

CREATE TABLE realized_world_artifact (
  world_artifact_ref TEXT PRIMARY KEY CHECK (world_artifact_ref LIKE 'rwa_%'),
  job_ref TEXT NOT NULL REFERENCES realized_state_job(job_ref),
  world_ref TEXT NOT NULL CHECK (world_ref LIKE 'rwd_%'),
  portfolio_ref TEXT NOT NULL CHECK (portfolio_ref LIKE 'ptf_%'),
  asset_ref TEXT NOT NULL CHECK (asset_ref LIKE 'ast_%'),
  calculation_mode TEXT NOT NULL CHECK (calculation_mode IN ('initial_world_rebuild', 'incremental_append', 'affected_world_rebuild', 'full_rebuild')),
  prior_world_artifact_ref TEXT REFERENCES realized_world_artifact(world_artifact_ref),
  earliest_changed_order_key TEXT,
  source_event_count INTEGER NOT NULL CHECK (source_event_count > 0),
  source_input_fingerprint TEXT NOT NULL CHECK (length(source_input_fingerprint) = 64),
  source_activity_json TEXT NOT NULL,
  result_fingerprint TEXT NOT NULL CHECK (length(result_fingerprint) = 64),
  result_json TEXT NOT NULL,
  table_fingerprint TEXT NOT NULL CHECK (length(table_fingerprint) = 64),
  completed_at_utc TEXT NOT NULL,
  artifact_fingerprint TEXT NOT NULL UNIQUE CHECK (length(artifact_fingerprint) = 64),
  UNIQUE (job_ref, world_ref)
) STRICT;

CREATE TABLE realized_event_result (
  world_artifact_ref TEXT NOT NULL REFERENCES realized_world_artifact(world_artifact_ref),
  event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
  event_ref TEXT NOT NULL,
  event_type TEXT NOT NULL,
  account_ref TEXT NOT NULL,
  related_account_ref TEXT,
  asset_ref TEXT NOT NULL,
  custody_quantity_before_decimal TEXT NOT NULL,
  custody_quantity_after_decimal TEXT NOT NULL,
  destination_custody_quantity_before_decimal TEXT,
  destination_custody_quantity_after_decimal TEXT,
  asset_quantity_before_decimal TEXT NOT NULL,
  asset_quantity_after_decimal TEXT NOT NULL,
  asset_fifo_basis_before TEXT,
  asset_fifo_basis_after TEXT,
  basis_added TEXT,
  basis_consumed TEXT,
  realized_gain_before_tax TEXT NOT NULL,
  PRIMARY KEY (world_artifact_ref,event_sequence),
  UNIQUE (world_artifact_ref,event_ref)
) STRICT;

CREATE TABLE realized_lot_movement (
  world_artifact_ref TEXT NOT NULL,
  event_sequence INTEGER NOT NULL,
  movement_sequence INTEGER NOT NULL CHECK (movement_sequence > 0),
  lot_ref TEXT NOT NULL,
  acquisition_event_ref TEXT NOT NULL,
  quantity_decimal TEXT NOT NULL,
  fifo_basis TEXT,
  PRIMARY KEY (world_artifact_ref,event_sequence,movement_sequence),
  FOREIGN KEY (world_artifact_ref,event_sequence) REFERENCES realized_event_result(world_artifact_ref,event_sequence)
) STRICT;

CREATE TABLE realized_custody_position (
  world_artifact_ref TEXT NOT NULL REFERENCES realized_world_artifact(world_artifact_ref),
  account_ref TEXT NOT NULL,
  asset_ref TEXT NOT NULL,
  remaining_quantity_decimal TEXT NOT NULL,
  PRIMARY KEY (world_artifact_ref,account_ref,asset_ref)
) STRICT;

CREATE TABLE realized_asset_position (
  world_artifact_ref TEXT NOT NULL REFERENCES realized_world_artifact(world_artifact_ref),
  asset_ref TEXT NOT NULL,
  asset_type TEXT NOT NULL,
  remaining_quantity_decimal TEXT NOT NULL,
  remaining_fifo_basis TEXT,
  cost_average TEXT,
  realized_gross_proceeds TEXT NOT NULL,
  realized_fifo_basis TEXT NOT NULL,
  realized_gain_before_tax TEXT NOT NULL,
  gross_income TEXT NOT NULL,
  monetary_fees TEXT NOT NULL,
  PRIMARY KEY (world_artifact_ref,asset_ref)
) STRICT;

CREATE TABLE realized_remaining_lot (
  world_artifact_ref TEXT NOT NULL REFERENCES realized_world_artifact(world_artifact_ref),
  lot_ref TEXT NOT NULL,
  asset_ref TEXT NOT NULL,
  acquisition_event_ref TEXT NOT NULL,
  acquisition_local_date TEXT NOT NULL,
  acquisition_effective_at_utc TEXT,
  remaining_quantity_decimal TEXT NOT NULL,
  remaining_fifo_basis TEXT,
  PRIMARY KEY (world_artifact_ref,lot_ref)
) STRICT;

CREATE TABLE realized_global_artifact (
  global_artifact_ref TEXT PRIMARY KEY CHECK (global_artifact_ref LIKE 'rga_%'),
  job_ref TEXT NOT NULL UNIQUE REFERENCES realized_state_job(job_ref),
  source_generation_ref TEXT NOT NULL,
  source_ledger_fingerprint TEXT NOT NULL CHECK (length(source_ledger_fingerprint) = 64),
  source_activity_set_fingerprint TEXT NOT NULL CHECK (length(source_activity_set_fingerprint) = 64),
  world_count INTEGER NOT NULL CHECK (world_count > 0),
  changed_world_count INTEGER NOT NULL CHECK (changed_world_count >= 0),
  reused_world_count INTEGER NOT NULL CHECK (reused_world_count >= 0),
  world_set_fingerprint TEXT NOT NULL CHECK (length(world_set_fingerprint) = 64),
  world_artifacts_json TEXT NOT NULL,
  full_rebuild_verified INTEGER NOT NULL CHECK (full_rebuild_verified = 1),
  portfolio_completeness TEXT NOT NULL CHECK (portfolio_completeness IN ('complete', 'incomplete_quarantined_or_derivative_blocked')),
  complete_portfolio_claim_authorized INTEGER NOT NULL CHECK (complete_portfolio_claim_authorized = 0),
  completed_at_utc TEXT NOT NULL,
  artifact_fingerprint TEXT NOT NULL UNIQUE CHECK (length(artifact_fingerprint) = 64),
  CHECK (changed_world_count + reused_world_count = world_count)
) STRICT;

CREATE TABLE realized_state_job_completion (
  job_ref TEXT PRIMARY KEY REFERENCES realized_state_job(job_ref),
  completion_status TEXT NOT NULL CHECK (completion_status IN ('completed', 'failed')),
  global_artifact_ref TEXT REFERENCES realized_global_artifact(global_artifact_ref),
  failure_code TEXT,
  completed_at_utc TEXT NOT NULL,
  completion_fingerprint TEXT NOT NULL UNIQUE CHECK (length(completion_fingerprint) = 64),
  CHECK ((completion_status = 'completed' AND global_artifact_ref IS NOT NULL AND failure_code IS NULL) OR (completion_status = 'failed' AND global_artifact_ref IS NULL AND failure_code IS NOT NULL))
) STRICT;

CREATE VIEW current_realized_global_artifact AS
SELECT artifact.*
FROM realized_global_artifact artifact
JOIN realized_state_job_completion completion USING(job_ref)
WHERE completion.completion_status = 'completed'
  AND NOT EXISTS (
    SELECT 1 FROM realized_global_artifact newer
    JOIN realized_state_job_completion newer_completion USING(job_ref)
    WHERE newer_completion.completion_status = 'completed'
      AND (newer.completed_at_utc > artifact.completed_at_utc OR (newer.completed_at_utc = artifact.completed_at_utc AND newer.global_artifact_ref > artifact.global_artifact_ref))
  );

CREATE TRIGGER realized_state_binding_no_update BEFORE UPDATE ON realized_state_binding BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_state_binding_no_delete BEFORE DELETE ON realized_state_binding BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_state_job_no_update BEFORE UPDATE ON realized_state_job BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_state_job_no_delete BEFORE DELETE ON realized_state_job BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_world_artifact_no_update BEFORE UPDATE ON realized_world_artifact BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_world_artifact_no_delete BEFORE DELETE ON realized_world_artifact BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_event_result_no_update BEFORE UPDATE ON realized_event_result BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_event_result_no_delete BEFORE DELETE ON realized_event_result BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_lot_movement_no_update BEFORE UPDATE ON realized_lot_movement BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_lot_movement_no_delete BEFORE DELETE ON realized_lot_movement BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_custody_position_no_update BEFORE UPDATE ON realized_custody_position BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_custody_position_no_delete BEFORE DELETE ON realized_custody_position BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_asset_position_no_update BEFORE UPDATE ON realized_asset_position BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_asset_position_no_delete BEFORE DELETE ON realized_asset_position BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_remaining_lot_no_update BEFORE UPDATE ON realized_remaining_lot BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_remaining_lot_no_delete BEFORE DELETE ON realized_remaining_lot BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_global_artifact_no_update BEFORE UPDATE ON realized_global_artifact BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_global_artifact_no_delete BEFORE DELETE ON realized_global_artifact BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_state_job_completion_no_update BEFORE UPDATE ON realized_state_job_completion BEGIN SELECT RAISE(ABORT, 'immutable'); END;
CREATE TRIGGER realized_state_job_completion_no_delete BEFORE DELETE ON realized_state_job_completion BEGIN SELECT RAISE(ABORT, 'immutable'); END;
