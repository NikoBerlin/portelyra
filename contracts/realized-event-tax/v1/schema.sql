PRAGMA foreign_keys=ON;
PRAGMA user_version=2000;
BEGIN IMMEDIATE;
CREATE TABLE tax_projection_store_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),schema_version INTEGER NOT NULL CHECK(schema_version=2000),context_binding_fingerprint TEXT NOT NULL CHECK(length(context_binding_fingerprint)=64),created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20)) STRICT;
CREATE TABLE tax_projection_job(
 job_id TEXT PRIMARY KEY CHECK(job_id LIKE 'tpj_%'),job_ref TEXT NOT NULL UNIQUE CHECK(job_ref LIKE 'tjb_%'),request_ref TEXT NOT NULL UNIQUE CHECK(request_ref LIKE 'req_%'),portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),
 projection_mode TEXT NOT NULL CHECK(projection_mode IN ('realized_event','realized_annual')),tax_year INTEGER CHECK(tax_year IS NULL OR tax_year BETWEEN 1900 AND 9999),source_artifact_ref TEXT NOT NULL,
 invalidated_from TEXT NOT NULL,invalidation_reason TEXT NOT NULL CHECK(invalidation_reason IN ('fifo_change','tax_classification_change','tax_parameter_change','plugin_change','annual_carryforward_change','initial_projection')),
 created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),CHECK((projection_mode='realized_event' AND tax_year IS NULL) OR (projection_mode='realized_annual' AND tax_year IS NOT NULL))
) STRICT;
CREATE TABLE tax_projection_job_state(job_state_id TEXT PRIMARY KEY CHECK(job_state_id LIKE 'tjs_%'),job_id TEXT NOT NULL REFERENCES tax_projection_job(job_id),state_sequence INTEGER NOT NULL,status TEXT NOT NULL CHECK(status IN ('pending','running','failed','completed')),failure_code TEXT,artifact_id TEXT,supersedes_job_state_id TEXT UNIQUE REFERENCES tax_projection_job_state(job_state_id),created_at_utc TEXT NOT NULL,UNIQUE(job_id,state_sequence)) STRICT;
CREATE TABLE tax_projection_artifact(
 artifact_id TEXT PRIMARY KEY CHECK(artifact_id LIKE 'tai_%'),artifact_ref TEXT NOT NULL UNIQUE CHECK(artifact_ref LIKE 'tar_%'),portfolio_ref TEXT NOT NULL,projection_mode TEXT NOT NULL CHECK(projection_mode IN ('realized_event','realized_annual')),tax_year INTEGER,
 source_artifact_ref TEXT NOT NULL,plugin_id TEXT NOT NULL,plugin_version TEXT NOT NULL,rules_fingerprint TEXT NOT NULL CHECK(length(rules_fingerprint)=64),selection_ref TEXT NOT NULL CHECK(selection_ref LIKE 'tsr_%'),
 plugin_input_fingerprint TEXT NOT NULL CHECK(length(plugin_input_fingerprint)=64),plugin_output_fingerprint TEXT NOT NULL CHECK(length(plugin_output_fingerprint)=64),rebuild_mode TEXT NOT NULL CHECK(rebuild_mode IN ('full','incremental')),
 base_artifact_id TEXT REFERENCES tax_projection_artifact(artifact_id),source_job_id TEXT NOT NULL UNIQUE REFERENCES tax_projection_job(job_id),row_set_fingerprint TEXT NOT NULL CHECK(length(row_set_fingerprint)=64),
 semantic_source_bindings_json TEXT NOT NULL CHECK(json_valid(semantic_source_bindings_json)),semantic_binding_fingerprint TEXT NOT NULL CHECK(length(semantic_binding_fingerprint)=64),
 readiness_status TEXT NOT NULL CHECK(readiness_status IN ('complete','partial_blocked')),disclaimer_code TEXT NOT NULL CHECK(disclaimer_code='model_projection_not_legal_advice'),completed_at_utc TEXT NOT NULL,
 CHECK((projection_mode='realized_event' AND tax_year IS NULL) OR (projection_mode='realized_annual' AND tax_year IS NOT NULL)),CHECK((rebuild_mode='full' AND base_artifact_id IS NULL) OR (rebuild_mode='incremental' AND base_artifact_id IS NOT NULL))
) STRICT;
CREATE TABLE tax_projection_row_blob(row_blob_id TEXT PRIMARY KEY CHECK(row_blob_id LIKE 'trb_%'),row_fingerprint TEXT NOT NULL UNIQUE CHECK(length(row_fingerprint)=64),projection_mode TEXT NOT NULL,row_json TEXT NOT NULL CHECK(json_valid(row_json)),created_at_utc TEXT NOT NULL) STRICT;
CREATE TABLE tax_projection_artifact_row(artifact_id TEXT NOT NULL REFERENCES tax_projection_artifact(artifact_id),row_ordinal INTEGER NOT NULL CHECK(row_ordinal>=1),row_blob_id TEXT NOT NULL REFERENCES tax_projection_row_blob(row_blob_id),PRIMARY KEY(artifact_id,row_ordinal)) STRICT,WITHOUT ROWID;
CREATE VIEW current_tax_projection_job_state AS SELECT state.* FROM tax_projection_job_state state WHERE NOT EXISTS(SELECT 1 FROM tax_projection_job_state successor WHERE successor.supersedes_job_state_id=state.job_state_id);
CREATE TRIGGER tax_projection_job_state_chain BEFORE INSERT ON tax_projection_job_state BEGIN SELECT CASE WHEN NEW.state_sequence=1 AND (NEW.status!='pending' OR NEW.supersedes_job_state_id IS NOT NULL) THEN RAISE(ABORT,'tax_projection_job_initial_invalid') END;SELECT CASE WHEN NEW.state_sequence>1 AND NOT EXISTS(SELECT 1 FROM current_tax_projection_job_state old WHERE old.job_state_id=NEW.supersedes_job_state_id AND old.job_id=NEW.job_id AND old.state_sequence+1=NEW.state_sequence) THEN RAISE(ABORT,'tax_projection_job_chain_invalid') END;END;
CREATE TRIGGER tax_projection_binding_no_update BEFORE UPDATE ON tax_projection_store_binding BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_binding_no_delete BEFORE DELETE ON tax_projection_store_binding BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_job_no_update BEFORE UPDATE ON tax_projection_job BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_job_no_delete BEFORE DELETE ON tax_projection_job BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_state_no_update BEFORE UPDATE ON tax_projection_job_state BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_state_no_delete BEFORE DELETE ON tax_projection_job_state BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_artifact_no_update BEFORE UPDATE ON tax_projection_artifact BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_artifact_no_delete BEFORE DELETE ON tax_projection_artifact BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_blob_no_update BEFORE UPDATE ON tax_projection_row_blob BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_blob_no_delete BEFORE DELETE ON tax_projection_row_blob BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_row_no_update BEFORE UPDATE ON tax_projection_artifact_row BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
CREATE TRIGGER tax_projection_row_no_delete BEFORE DELETE ON tax_projection_artifact_row BEGIN SELECT RAISE(ABORT,'tax_projection_immutable'); END;
COMMIT;
