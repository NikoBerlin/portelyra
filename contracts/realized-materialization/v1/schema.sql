PRAGMA foreign_keys=ON;
PRAGMA user_version=1800;
BEGIN IMMEDIATE;

CREATE TABLE realized_store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id=1),
  schema_version INTEGER NOT NULL CHECK (schema_version=1800),
  context_binding_fingerprint TEXT NOT NULL CHECK (length(context_binding_fingerprint)=64 AND context_binding_fingerprint NOT GLOB '*[^a-f0-9]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=20)
) STRICT;

CREATE TABLE realized_rebuild_job (
  job_id TEXT PRIMARY KEY CHECK (job_id LIKE 'rji_%'),
  job_ref TEXT NOT NULL UNIQUE CHECK (job_ref LIKE 'rjb_%'),
  request_ref TEXT NOT NULL UNIQUE CHECK (request_ref LIKE 'req_%'),
  portfolio_ref TEXT NOT NULL CHECK (portfolio_ref LIKE 'pfr_%'),
  desired_input_fingerprint TEXT NOT NULL CHECK (length(desired_input_fingerprint)=64),
  invalidated_from_utc TEXT NOT NULL CHECK (length(invalidated_from_utc)=20),
  invalidation_reason TEXT NOT NULL CHECK (invalidation_reason IN ('initial_full_rebuild','append_only','backdated_event','correction','void','transfer_chain','algorithm_upgrade','recovery_mismatch')),
  affected_scope_json TEXT NOT NULL CHECK (json_valid(affected_scope_json)),
  requested_algorithm_version TEXT NOT NULL CHECK (length(requested_algorithm_version) BETWEEN 3 AND 40),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=20)
) STRICT;

CREATE TABLE realized_rebuild_job_state (
  job_state_id TEXT PRIMARY KEY CHECK (job_state_id LIKE 'rjs_%'),
  job_id TEXT NOT NULL REFERENCES realized_rebuild_job(job_id),
  state_sequence INTEGER NOT NULL CHECK (state_sequence>=1),
  status TEXT NOT NULL CHECK (status IN ('pending','running','failed','completed')),
  failure_code TEXT CHECK ((status='failed' AND failure_code LIKE 'realized_materialization_%') OR (status!='failed' AND failure_code IS NULL)),
  artifact_id TEXT,
  supersedes_job_state_id TEXT UNIQUE REFERENCES realized_rebuild_job_state(job_state_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=20),
  UNIQUE(job_id,state_sequence)
) STRICT;

CREATE TABLE realized_artifact (
  artifact_id TEXT PRIMARY KEY CHECK (artifact_id LIKE 'rai_%'),
  artifact_ref TEXT NOT NULL UNIQUE CHECK (artifact_ref LIKE 'rar_%'),
  portfolio_ref TEXT NOT NULL CHECK (portfolio_ref LIKE 'pfr_%'),
  algorithm_version TEXT NOT NULL CHECK (length(algorithm_version) BETWEEN 3 AND 40),
  input_fingerprint TEXT NOT NULL CHECK (length(input_fingerprint)=64),
  evidence_artifact_fingerprint TEXT NOT NULL CHECK (length(evidence_artifact_fingerprint)=64),
  evidence_cutoff_at_utc TEXT NOT NULL CHECK (length(evidence_cutoff_at_utc)=20),
  rebuild_mode TEXT NOT NULL CHECK (rebuild_mode IN ('full','incremental')),
  base_artifact_id TEXT REFERENCES realized_artifact(artifact_id),
  invalidated_from_utc TEXT NOT NULL CHECK (length(invalidated_from_utc)=20),
  source_job_id TEXT NOT NULL UNIQUE REFERENCES realized_rebuild_job(job_id),
  row_set_fingerprint TEXT NOT NULL CHECK (length(row_set_fingerprint)=64),
  semantic_source_bindings_json TEXT NOT NULL CHECK (json_valid(semantic_source_bindings_json)),
  semantic_binding_fingerprint TEXT NOT NULL CHECK (length(semantic_binding_fingerprint)=64 AND semantic_binding_fingerprint NOT GLOB '*[^a-f0-9]*'),
  completed_at_utc TEXT NOT NULL CHECK (length(completed_at_utc)=20),
  CHECK ((rebuild_mode='full' AND base_artifact_id IS NULL) OR (rebuild_mode='incremental' AND base_artifact_id IS NOT NULL))
) STRICT;

CREATE TABLE realized_row_blob (
  row_blob_id TEXT PRIMARY KEY CHECK (row_blob_id LIKE 'rrb_%'),
  row_fingerprint TEXT NOT NULL UNIQUE CHECK (length(row_fingerprint)=64),
  table_name TEXT NOT NULL CHECK (table_name IN ('event-results.csv','lot-movements.csv','remaining-lots.csv','position-history.csv','position-summary.csv','currency-summary.csv')),
  row_json TEXT NOT NULL CHECK (json_valid(row_json)),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=20)
) STRICT;

CREATE TABLE realized_artifact_row (
  artifact_id TEXT NOT NULL REFERENCES realized_artifact(artifact_id),
  table_name TEXT NOT NULL,
  row_ordinal INTEGER NOT NULL CHECK (row_ordinal>=1),
  row_blob_id TEXT NOT NULL REFERENCES realized_row_blob(row_blob_id),
  PRIMARY KEY(artifact_id,table_name,row_ordinal)
) STRICT, WITHOUT ROWID;

CREATE TABLE realized_position_checkpoint (
  checkpoint_id TEXT PRIMARY KEY CHECK (checkpoint_id LIKE 'rcp_%'),
  artifact_id TEXT NOT NULL REFERENCES realized_artifact(artifact_id),
  position_ref TEXT NOT NULL CHECK (position_ref LIKE 'pos_%'),
  account_ref TEXT NOT NULL CHECK (account_ref LIKE 'afr_%'),
  asset_ref TEXT NOT NULL CHECK (asset_ref LIKE 'asf_%'),
  currency TEXT NOT NULL CHECK (length(currency)=3),
  cutoff_at_utc TEXT NOT NULL CHECK (length(cutoff_at_utc)=20),
  remaining_quantity_decimal TEXT NOT NULL,
  remaining_fifo_cost_decimal TEXT NOT NULL,
  checkpoint_fingerprint TEXT NOT NULL UNIQUE CHECK (length(checkpoint_fingerprint)=64),
  UNIQUE(artifact_id,position_ref)
) STRICT;

CREATE VIEW current_realized_rebuild_job_state AS
SELECT state.* FROM realized_rebuild_job_state state
WHERE NOT EXISTS (SELECT 1 FROM realized_rebuild_job_state successor WHERE successor.supersedes_job_state_id=state.job_state_id);

CREATE TRIGGER realized_job_state_chain BEFORE INSERT ON realized_rebuild_job_state BEGIN
  SELECT CASE WHEN NEW.state_sequence=1 AND (NEW.status!='pending' OR NEW.supersedes_job_state_id IS NOT NULL) THEN RAISE(ABORT,'realized_job_state_initial_invalid') END;
  SELECT CASE WHEN NEW.state_sequence>1 AND NOT EXISTS (
    SELECT 1 FROM current_realized_rebuild_job_state old WHERE old.job_state_id=NEW.supersedes_job_state_id AND old.job_id=NEW.job_id AND old.state_sequence+1=NEW.state_sequence
  ) THEN RAISE(ABORT,'realized_job_state_chain_invalid') END;
END;

CREATE TRIGGER realized_job_state_artifact_fk BEFORE INSERT ON realized_rebuild_job_state
WHEN NEW.status='completed' BEGIN
  SELECT CASE WHEN NEW.artifact_id IS NULL OR NOT EXISTS (SELECT 1 FROM realized_artifact artifact WHERE artifact.artifact_id=NEW.artifact_id AND artifact.source_job_id=NEW.job_id) THEN RAISE(ABORT,'realized_job_artifact_invalid') END;
END;

CREATE TRIGGER realized_artifact_row_table BEFORE INSERT ON realized_artifact_row BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM realized_row_blob blob WHERE blob.row_blob_id=NEW.row_blob_id AND blob.table_name=NEW.table_name) THEN RAISE(ABORT,'realized_artifact_row_table_invalid') END;
END;

CREATE TRIGGER realized_store_binding_no_update BEFORE UPDATE ON realized_store_binding BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_store_binding_no_delete BEFORE DELETE ON realized_store_binding BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_job_no_update BEFORE UPDATE ON realized_rebuild_job BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_job_no_delete BEFORE DELETE ON realized_rebuild_job BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_job_state_no_update BEFORE UPDATE ON realized_rebuild_job_state BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_job_state_no_delete BEFORE DELETE ON realized_rebuild_job_state BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_artifact_no_update BEFORE UPDATE ON realized_artifact BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_artifact_no_delete BEFORE DELETE ON realized_artifact BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_row_blob_no_update BEFORE UPDATE ON realized_row_blob BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_row_blob_no_delete BEFORE DELETE ON realized_row_blob BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_artifact_row_no_update BEFORE UPDATE ON realized_artifact_row BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_artifact_row_no_delete BEFORE DELETE ON realized_artifact_row BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_checkpoint_no_update BEFORE UPDATE ON realized_position_checkpoint BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;
CREATE TRIGGER realized_checkpoint_no_delete BEFORE DELETE ON realized_position_checkpoint BEGIN SELECT RAISE(ABORT,'realized_immutable'); END;

COMMIT;
