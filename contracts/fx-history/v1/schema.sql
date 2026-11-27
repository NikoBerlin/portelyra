PRAGMA foreign_keys = ON;
PRAGMA user_version = 2600;

BEGIN IMMEDIATE;

CREATE TABLE fx_history_store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 2600),
  context_binding_fingerprint TEXT NOT NULL CHECK (length(context_binding_fingerprint) = 64 AND context_binding_fingerprint NOT GLOB '*[^a-f0-9]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20)
) STRICT;

CREATE TABLE fx_pair_binding (
  pair_id TEXT PRIMARY KEY CHECK (pair_id LIKE 'fpi_%' AND length(pair_id) = 36),
  pair_ref TEXT NOT NULL UNIQUE CHECK (pair_ref LIKE 'fxp_%' AND length(pair_ref) = 36),
  base_currency TEXT NOT NULL CHECK (length(base_currency) = 3 AND base_currency = upper(base_currency)),
  quote_currency TEXT NOT NULL CHECK (length(quote_currency) = 3 AND quote_currency = upper(quote_currency)),
  market_code TEXT NOT NULL CHECK (length(market_code) BETWEEN 2 AND 16),
  timezone_name TEXT NOT NULL CHECK (length(timezone_name) BETWEEN 3 AND 64),
  calendar_code TEXT NOT NULL CHECK (calendar_code IN ('weekday_fx','continuous_24_7','custom_reviewed')),
  rate_type TEXT NOT NULL CHECK (rate_type IN ('reference_rate','market_close','mid_rate')),
  catalog_fingerprint TEXT NOT NULL CHECK (length(catalog_fingerprint) = 64 AND catalog_fingerprint NOT GLOB '*[^a-f0-9]*'),
  pair_fingerprint TEXT NOT NULL UNIQUE CHECK (length(pair_fingerprint) = 64 AND pair_fingerprint NOT GLOB '*[^a-f0-9]*'),
  bound_by_actor TEXT NOT NULL CHECK (length(bound_by_actor) BETWEEN 3 AND 80),
  bound_at_utc TEXT NOT NULL CHECK (length(bound_at_utc) = 20),
  CHECK (base_currency != quote_currency),
  UNIQUE (base_currency, quote_currency, market_code, rate_type)
) STRICT;

CREATE TABLE fx_history_request (
  request_id TEXT PRIMARY KEY CHECK (request_id LIKE 'fri_%' AND length(request_id) = 36),
  request_ref TEXT NOT NULL UNIQUE CHECK (request_ref LIKE 'fxq_%' AND length(request_ref) = 36),
  pair_id TEXT NOT NULL REFERENCES fx_pair_binding(pair_id),
  source_kind TEXT NOT NULL CHECK (source_kind IN ('synthetic_fixture','manual_reviewed_evidence','market_plugin')),
  source_ref TEXT NOT NULL CHECK (source_ref LIKE 'fxs_%' AND length(source_ref) = 36),
  source_version TEXT NOT NULL CHECK (length(source_version) BETWEEN 3 AND 80),
  plugin_id TEXT,
  plugin_version TEXT,
  plugin_manifest_fingerprint TEXT,
  request_fingerprint TEXT NOT NULL CHECK (length(request_fingerprint) = 64 AND request_fingerprint NOT GLOB '*[^a-f0-9]*'),
  job_binding_fingerprint TEXT NOT NULL CHECK (length(job_binding_fingerprint) = 64 AND job_binding_fingerprint NOT GLOB '*[^a-f0-9]*'),
  candidate_fingerprint TEXT NOT NULL UNIQUE CHECK (length(candidate_fingerprint) = 64 AND candidate_fingerprint NOT GLOB '*[^a-f0-9]*'),
  requested_start_date TEXT NOT NULL CHECK (length(requested_start_date) = 10),
  requested_end_date TEXT NOT NULL CHECK (length(requested_end_date) = 10 AND requested_end_date >= requested_start_date),
  retrieved_at_utc TEXT NOT NULL CHECK (length(retrieved_at_utc) = 20),
  completed_at_utc TEXT NOT NULL CHECK (length(completed_at_utc) = 20 AND completed_at_utc >= retrieved_at_utc),
  actor_id TEXT NOT NULL CHECK (length(actor_id) BETWEEN 3 AND 80),
  appended_day_count INTEGER NOT NULL CHECK (appended_day_count >= 0),
  corrected_day_count INTEGER NOT NULL CHECK (corrected_day_count >= 0),
  unchanged_day_count INTEGER NOT NULL CHECK (unchanged_day_count >= 0),
  row_set_fingerprint TEXT NOT NULL CHECK (length(row_set_fingerprint) = 64 AND row_set_fingerprint NOT GLOB '*[^a-f0-9]*'),
  receipt_fingerprint TEXT NOT NULL UNIQUE CHECK (length(receipt_fingerprint) = 64 AND receipt_fingerprint NOT GLOB '*[^a-f0-9]*'),
  CHECK (
    (source_kind = 'market_plugin' AND plugin_id IS NOT NULL AND plugin_version IS NOT NULL AND length(plugin_manifest_fingerprint) = 64) OR
    (source_kind != 'market_plugin' AND plugin_id IS NULL AND plugin_version IS NULL AND plugin_manifest_fingerprint IS NULL)
  )
) STRICT;

CREATE TABLE fx_day_entity (
  fx_day_id TEXT PRIMARY KEY CHECK (fx_day_id LIKE 'fdi_%' AND length(fx_day_id) = 36),
  fx_day_ref TEXT NOT NULL UNIQUE CHECK (fx_day_ref LIKE 'fxd_%' AND length(fx_day_ref) = 36),
  pair_id TEXT NOT NULL REFERENCES fx_pair_binding(pair_id),
  rate_date TEXT NOT NULL CHECK (length(rate_date) = 10),
  created_by_request_id TEXT NOT NULL REFERENCES fx_history_request(request_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20),
  UNIQUE (pair_id, rate_date)
) STRICT;

CREATE TABLE fx_day_revision (
  revision_id TEXT PRIMARY KEY CHECK (revision_id LIKE 'fdr_%' AND length(revision_id) = 36),
  revision_ref TEXT NOT NULL UNIQUE CHECK (revision_ref LIKE 'fxv_%' AND length(revision_ref) = 36),
  fx_day_id TEXT NOT NULL REFERENCES fx_day_entity(fx_day_id),
  revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
  day_status TEXT NOT NULL CHECK (day_status IN ('observed','non_trading_day','source_gap')),
  rate_decimal TEXT,
  quality_status TEXT NOT NULL CHECK (quality_status IN ('complete','corrected','calendar_confirmed','explicit_gap')),
  gap_reason TEXT CHECK (gap_reason IN ('source_no_data','source_partial_response','calendar_ambiguity')),
  source_observation_ref TEXT NOT NULL CHECK (source_observation_ref LIKE 'fxo_%' AND length(source_observation_ref) = 36),
  observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc) = 20),
  source_day_fingerprint TEXT NOT NULL CHECK (length(source_day_fingerprint) = 64 AND source_day_fingerprint NOT GLOB '*[^a-f0-9]*'),
  request_id TEXT NOT NULL REFERENCES fx_history_request(request_id),
  correction_reason TEXT CHECK (correction_reason IN ('source_correction','calendar_correction','quality_correction','manual_review_correction')),
  supersedes_revision_id TEXT UNIQUE REFERENCES fx_day_revision(revision_id),
  retrieved_at_utc TEXT NOT NULL CHECK (length(retrieved_at_utc) = 20),
  completed_at_utc TEXT NOT NULL CHECK (length(completed_at_utc) = 20),
  revision_fingerprint TEXT NOT NULL UNIQUE CHECK (length(revision_fingerprint) = 64 AND revision_fingerprint NOT GLOB '*[^a-f0-9]*'),
  UNIQUE (fx_day_id, revision_no),
  CHECK ((day_status = 'observed' AND rate_decimal IS NOT NULL AND gap_reason IS NULL AND quality_status IN ('complete','corrected')) OR
         (day_status = 'non_trading_day' AND rate_decimal IS NULL AND gap_reason IS NULL AND quality_status = 'calendar_confirmed') OR
         (day_status = 'source_gap' AND rate_decimal IS NULL AND gap_reason IS NOT NULL AND quality_status = 'explicit_gap'))
) STRICT;

CREATE TABLE fx_request_day_evidence (
  evidence_id TEXT PRIMARY KEY CHECK (evidence_id LIKE 'fde_%' AND length(evidence_id) = 36),
  request_id TEXT NOT NULL REFERENCES fx_history_request(request_id),
  row_ordinal INTEGER NOT NULL CHECK (row_ordinal >= 1),
  fx_day_id TEXT NOT NULL REFERENCES fx_day_entity(fx_day_id),
  resulting_revision_id TEXT NOT NULL REFERENCES fx_day_revision(revision_id),
  disposition TEXT NOT NULL CHECK (disposition IN ('appended','corrected','unchanged')),
  source_observation_ref TEXT NOT NULL CHECK (source_observation_ref LIKE 'fxo_%' AND length(source_observation_ref) = 36),
  observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc) = 20),
  source_day_fingerprint TEXT NOT NULL CHECK (length(source_day_fingerprint) = 64 AND source_day_fingerprint NOT GLOB '*[^a-f0-9]*'),
  UNIQUE (request_id, row_ordinal),
  UNIQUE (request_id, fx_day_id)
) STRICT;

CREATE VIEW current_fx_day_revision AS
SELECT revision.* FROM fx_day_revision revision
WHERE NOT EXISTS (SELECT 1 FROM fx_day_revision successor WHERE successor.supersedes_revision_id = revision.revision_id);

CREATE TRIGGER fx_day_entity_scope BEFORE INSERT ON fx_day_entity BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM fx_history_request request WHERE request.request_id = NEW.created_by_request_id AND request.pair_id = NEW.pair_id)
    THEN RAISE(ABORT,'fx_day_request_scope_invalid') END;
END;

CREATE TRIGGER fx_day_revision_chain BEFORE INSERT ON fx_day_revision BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM fx_day_entity entity JOIN fx_history_request request ON request.request_id = NEW.request_id
    WHERE entity.fx_day_id = NEW.fx_day_id AND entity.pair_id = request.pair_id
  ) THEN RAISE(ABORT,'fx_day_request_scope_invalid') END;
  SELECT CASE WHEN NEW.revision_no = 1 AND (NEW.supersedes_revision_id IS NOT NULL OR NEW.correction_reason IS NOT NULL OR EXISTS (SELECT 1 FROM fx_day_revision WHERE fx_day_id = NEW.fx_day_id))
    THEN RAISE(ABORT,'fx_day_initial_revision_invalid') END;
  SELECT CASE WHEN NEW.revision_no > 1 AND NOT EXISTS (
    SELECT 1 FROM current_fx_day_revision old WHERE old.revision_id = NEW.supersedes_revision_id AND old.fx_day_id = NEW.fx_day_id AND old.revision_no + 1 = NEW.revision_no AND NEW.correction_reason IS NOT NULL
  ) THEN RAISE(ABORT,'fx_day_revision_chain_invalid') END;
END;

CREATE TRIGGER fx_request_day_evidence_scope BEFORE INSERT ON fx_request_day_evidence BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM fx_day_entity entity JOIN fx_day_revision revision ON revision.revision_id = NEW.resulting_revision_id JOIN fx_history_request request ON request.request_id = NEW.request_id
    WHERE entity.fx_day_id = NEW.fx_day_id AND revision.fx_day_id = entity.fx_day_id AND request.pair_id = entity.pair_id
      AND ((NEW.disposition = 'appended' AND revision.request_id = NEW.request_id AND revision.revision_no = 1)
        OR (NEW.disposition = 'corrected' AND revision.request_id = NEW.request_id AND revision.revision_no > 1)
        OR (NEW.disposition = 'unchanged' AND revision.request_id != NEW.request_id))
  ) THEN RAISE(ABORT,'fx_request_day_scope_invalid') END;
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM fx_request_day_evidence prior JOIN fx_history_request prior_request ON prior_request.request_id = prior.request_id JOIN fx_history_request current_request ON current_request.request_id = NEW.request_id
    WHERE prior.fx_day_id = NEW.fx_day_id AND prior.request_id != NEW.request_id AND prior_request.retrieved_at_utc >= current_request.retrieved_at_utc
  ) THEN RAISE(ABORT,'fx_request_day_time_invalid') END;
END;

CREATE TRIGGER fx_history_store_binding_no_update BEFORE UPDATE ON fx_history_store_binding BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_history_store_binding_no_delete BEFORE DELETE ON fx_history_store_binding BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_pair_binding_no_update BEFORE UPDATE ON fx_pair_binding BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_pair_binding_no_delete BEFORE DELETE ON fx_pair_binding BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_history_request_no_update BEFORE UPDATE ON fx_history_request BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_history_request_no_delete BEFORE DELETE ON fx_history_request BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_day_entity_no_update BEFORE UPDATE ON fx_day_entity BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_day_entity_no_delete BEFORE DELETE ON fx_day_entity BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_day_revision_no_update BEFORE UPDATE ON fx_day_revision BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_day_revision_no_delete BEFORE DELETE ON fx_day_revision BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_request_day_evidence_no_update BEFORE UPDATE ON fx_request_day_evidence BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;
CREATE TRIGGER fx_request_day_evidence_no_delete BEFORE DELETE ON fx_request_day_evidence BEGIN SELECT RAISE(ABORT,'fx_history_immutable'); END;

COMMIT;
