PRAGMA foreign_keys = ON;
PRAGMA user_version = 2700;
BEGIN IMMEDIATE;

CREATE TABLE unrealized_valuation_store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 2700),
  context_binding_fingerprint TEXT NOT NULL CHECK (length(context_binding_fingerprint)=64 AND context_binding_fingerprint NOT GLOB '*[^a-f0-9]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc)=20)
) STRICT;

CREATE TABLE unrealized_valuation_invalidation (
  invalidation_id TEXT PRIMARY KEY CHECK (invalidation_id LIKE 'uvi_%' AND length(invalidation_id)=36),
  invalidation_ref TEXT NOT NULL UNIQUE CHECK (invalidation_ref LIKE 'uvn_%' AND length(invalidation_ref)=36),
  request_ref TEXT NOT NULL UNIQUE CHECK (request_ref LIKE 'req_%' AND length(request_ref) BETWEEN 28 AND 36),
  portfolio_ref TEXT NOT NULL CHECK (portfolio_ref LIKE 'pfr_%' AND length(portfolio_ref)=36),
  reason TEXT NOT NULL CHECK (reason IN ('fifo_correction','market_correction','tax_policy_revision','fx_correction','algorithm_upgrade')),
  source_fingerprint TEXT NOT NULL CHECK (length(source_fingerprint)=64 AND source_fingerprint NOT GLOB '*[^a-f0-9]*'),
  affected_position_refs_json TEXT NOT NULL CHECK (json_valid(affected_position_refs_json)),
  actor_id TEXT NOT NULL CHECK (length(actor_id) BETWEEN 3 AND 80),
  invalidated_at_utc TEXT NOT NULL CHECK (length(invalidated_at_utc)=20),
  invalidation_fingerprint TEXT NOT NULL UNIQUE CHECK (length(invalidation_fingerprint)=64 AND invalidation_fingerprint NOT GLOB '*[^a-f0-9]*')
) STRICT;

CREATE TABLE unrealized_valuation_snapshot (
  snapshot_id TEXT PRIMARY KEY CHECK (snapshot_id LIKE 'uvs_%' AND length(snapshot_id)=36),
  snapshot_ref TEXT NOT NULL UNIQUE CHECK (snapshot_ref LIKE 'uva_%' AND length(snapshot_ref)=36),
  request_ref TEXT NOT NULL UNIQUE CHECK (request_ref LIKE 'req_%' AND length(request_ref) BETWEEN 28 AND 36),
  portfolio_ref TEXT NOT NULL CHECK (portfolio_ref LIKE 'pfr_%' AND length(portfolio_ref)=36),
  as_of_date TEXT NOT NULL CHECK (length(as_of_date)=10),
  target_currency TEXT NOT NULL CHECK (length(target_currency)=3 AND target_currency=upper(target_currency)),
  status TEXT NOT NULL CHECK (status IN ('completed','partial','blocked')),
  calculation_mode TEXT NOT NULL CHECK (calculation_mode IN ('full','incremental')),
  algorithm_version TEXT NOT NULL CHECK (length(algorithm_version) BETWEEN 3 AND 40),
  input_fingerprint TEXT NOT NULL CHECK (length(input_fingerprint)=64 AND input_fingerprint NOT GLOB '*[^a-f0-9]*'),
  fifo_artifact_fingerprint TEXT NOT NULL CHECK (length(fifo_artifact_fingerprint)=64 AND fifo_artifact_fingerprint NOT GLOB '*[^a-f0-9]*'),
  market_artifact_fingerprint TEXT NOT NULL CHECK (length(market_artifact_fingerprint)=64 AND market_artifact_fingerprint NOT GLOB '*[^a-f0-9]*'),
  tax_artifact_fingerprint TEXT NOT NULL CHECK (length(tax_artifact_fingerprint)=64 AND tax_artifact_fingerprint NOT GLOB '*[^a-f0-9]*'),
  fx_artifacts_fingerprint TEXT NOT NULL CHECK (length(fx_artifacts_fingerprint)=64 AND fx_artifacts_fingerprint NOT GLOB '*[^a-f0-9]*'),
  base_snapshot_id TEXT REFERENCES unrealized_valuation_snapshot(snapshot_id),
  row_set_fingerprint TEXT NOT NULL CHECK (length(row_set_fingerprint)=64 AND row_set_fingerprint NOT GLOB '*[^a-f0-9]*'),
  artifact_fingerprint TEXT NOT NULL UNIQUE CHECK (length(artifact_fingerprint)=64 AND artifact_fingerprint NOT GLOB '*[^a-f0-9]*'),
  artifact_json TEXT NOT NULL CHECK (json_valid(artifact_json)),
  actor_id TEXT NOT NULL CHECK (length(actor_id) BETWEEN 3 AND 80),
  completed_at_utc TEXT NOT NULL CHECK (length(completed_at_utc)=20)
) STRICT;

CREATE TABLE unrealized_valuation_position_result (
  result_id TEXT PRIMARY KEY CHECK (result_id LIKE 'uvr_%' AND length(result_id)=36),
  snapshot_id TEXT NOT NULL REFERENCES unrealized_valuation_snapshot(snapshot_id),
  row_ordinal INTEGER NOT NULL CHECK (row_ordinal>=1),
  position_ref TEXT NOT NULL CHECK (position_ref LIKE 'psr_%' AND length(position_ref)=36),
  account_ref TEXT NOT NULL CHECK (account_ref LIKE 'acr_%' AND length(account_ref)=36),
  asset_ref TEXT NOT NULL CHECK (asset_ref LIKE 'asr_%' AND length(asset_ref)=36),
  position_status TEXT NOT NULL CHECK (position_status IN ('completed','partial','blocked')),
  position_input_fingerprint TEXT NOT NULL CHECK (length(position_input_fingerprint)=64 AND position_input_fingerprint NOT GLOB '*[^a-f0-9]*'),
  result_fingerprint TEXT NOT NULL CHECK (length(result_fingerprint)=64 AND result_fingerprint NOT GLOB '*[^a-f0-9]*'),
  result_json TEXT NOT NULL CHECK (json_valid(result_json)),
  UNIQUE(snapshot_id,row_ordinal),
  UNIQUE(snapshot_id,position_ref)
) STRICT;

CREATE TABLE unrealized_valuation_invalidation_resolution (
  resolution_id TEXT PRIMARY KEY CHECK (resolution_id LIKE 'uvx_%' AND length(resolution_id)=36),
  snapshot_id TEXT NOT NULL REFERENCES unrealized_valuation_snapshot(snapshot_id),
  invalidation_id TEXT NOT NULL REFERENCES unrealized_valuation_invalidation(invalidation_id),
  resolved_at_utc TEXT NOT NULL CHECK (length(resolved_at_utc)=20),
  UNIQUE(snapshot_id,invalidation_id)
) STRICT;

CREATE TRIGGER unrealized_valuation_snapshot_base BEFORE INSERT ON unrealized_valuation_snapshot BEGIN
  SELECT CASE WHEN NEW.calculation_mode='full' AND NEW.base_snapshot_id IS NOT NULL THEN RAISE(ABORT,'unrealized_valuation_base_invalid') END;
  SELECT CASE WHEN NEW.calculation_mode='incremental' AND NOT EXISTS (
    SELECT 1 FROM unrealized_valuation_snapshot base WHERE base.snapshot_id=NEW.base_snapshot_id AND base.portfolio_ref=NEW.portfolio_ref AND base.status IN ('completed','partial')
  ) THEN RAISE(ABORT,'unrealized_valuation_base_invalid') END;
END;

CREATE TRIGGER unrealized_valuation_result_scope BEFORE INSERT ON unrealized_valuation_position_result BEGIN
  SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM unrealized_valuation_snapshot snapshot WHERE snapshot.snapshot_id=NEW.snapshot_id)
    THEN RAISE(ABORT,'unrealized_valuation_result_scope_invalid') END;
END;

CREATE TRIGGER unrealized_valuation_resolution_scope BEFORE INSERT ON unrealized_valuation_invalidation_resolution BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM unrealized_valuation_snapshot snapshot JOIN unrealized_valuation_invalidation invalidation ON invalidation.invalidation_id=NEW.invalidation_id
    WHERE snapshot.snapshot_id=NEW.snapshot_id AND snapshot.portfolio_ref=invalidation.portfolio_ref AND snapshot.status IN ('completed','partial')
  ) THEN RAISE(ABORT,'unrealized_valuation_resolution_scope_invalid') END;
END;

CREATE TRIGGER unrealized_valuation_store_no_update BEFORE UPDATE ON unrealized_valuation_store_binding BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_store_no_delete BEFORE DELETE ON unrealized_valuation_store_binding BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_invalidation_no_update BEFORE UPDATE ON unrealized_valuation_invalidation BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_invalidation_no_delete BEFORE DELETE ON unrealized_valuation_invalidation BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_snapshot_no_update BEFORE UPDATE ON unrealized_valuation_snapshot BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_snapshot_no_delete BEFORE DELETE ON unrealized_valuation_snapshot BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_result_no_update BEFORE UPDATE ON unrealized_valuation_position_result BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_result_no_delete BEFORE DELETE ON unrealized_valuation_position_result BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_resolution_no_update BEFORE UPDATE ON unrealized_valuation_invalidation_resolution BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;
CREATE TRIGGER unrealized_valuation_resolution_no_delete BEFORE DELETE ON unrealized_valuation_invalidation_resolution BEGIN SELECT RAISE(ABORT,'unrealized_valuation_immutable'); END;

COMMIT;
