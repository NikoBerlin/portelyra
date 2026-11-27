PRAGMA foreign_keys = ON;
PRAGMA user_version = 2400;

BEGIN IMMEDIATE;

CREATE TABLE daily_market_history_store_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 2400),
  context_binding_fingerprint TEXT NOT NULL CHECK (length(context_binding_fingerprint) = 64 AND context_binding_fingerprint NOT GLOB '*[^a-f0-9]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20)
) STRICT;

CREATE TABLE market_listing_binding (
  listing_id TEXT PRIMARY KEY CHECK (listing_id LIKE 'mli_%' AND length(listing_id) = 36),
  listing_ref TEXT NOT NULL UNIQUE CHECK (listing_ref LIKE 'lsr_%' AND length(listing_ref) = 36),
  asset_ref TEXT NOT NULL CHECK (asset_ref LIKE 'asf_%' AND length(asset_ref) = 36),
  quote_currency TEXT NOT NULL CHECK (length(quote_currency) = 3 AND quote_currency = upper(quote_currency)),
  market_code TEXT NOT NULL CHECK (length(market_code) BETWEEN 2 AND 16),
  timezone_name TEXT NOT NULL CHECK (length(timezone_name) BETWEEN 3 AND 64),
  calendar_code TEXT NOT NULL CHECK (calendar_code IN ('weekday_exchange','continuous_24_7','bank_business_day','custom_reviewed')),
  valuation_price_policy TEXT NOT NULL CHECK (valuation_price_policy = 'unadjusted_close_only'),
  -- Bindet die Freigabe an den Katalogstand GENAU DIESES Assets (Identitaet, Name,
  -- Typ, Waehrung, Mengenskala, Bewertungsmethode, ISIN, Status, Revision), nicht an
  -- den Gesamtkatalog. Anders entwertete jede fremde Katalogaenderung saemtliche
  -- Freigaben und sperrte Bewertung wie Historienabruf (20.09.2026).
  catalog_fingerprint TEXT NOT NULL CHECK (length(catalog_fingerprint) = 64 AND catalog_fingerprint NOT GLOB '*[^a-f0-9]*'),
  listing_fingerprint TEXT NOT NULL UNIQUE CHECK (length(listing_fingerprint) = 64 AND listing_fingerprint NOT GLOB '*[^a-f0-9]*'),
  bound_by_actor TEXT NOT NULL CHECK (length(bound_by_actor) BETWEEN 3 AND 80),
  bound_at_utc TEXT NOT NULL CHECK (length(bound_at_utc) = 20)
) STRICT;

CREATE TABLE daily_market_history_request (
  request_id TEXT PRIMARY KEY CHECK (request_id LIKE 'mri_%' AND length(request_id) = 36),
  request_ref TEXT NOT NULL UNIQUE CHECK (request_ref LIKE 'mrq_%' AND length(request_ref) = 36),
  listing_id TEXT NOT NULL REFERENCES market_listing_binding(listing_id),
  source_kind TEXT NOT NULL CHECK (source_kind IN ('synthetic_fixture','manual_reviewed_evidence','market_plugin','carried_listing')),
  source_ref TEXT NOT NULL CHECK (source_ref LIKE 'msr_%' AND length(source_ref) = 36),
  source_version TEXT NOT NULL CHECK (length(source_version) BETWEEN 3 AND 80),
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
  receipt_fingerprint TEXT NOT NULL UNIQUE CHECK (length(receipt_fingerprint) = 64 AND receipt_fingerprint NOT GLOB '*[^a-f0-9]*')
) STRICT;

CREATE TABLE market_day_entity (
  market_day_id TEXT PRIMARY KEY CHECK (market_day_id LIKE 'mdi_%' AND length(market_day_id) = 36),
  market_day_ref TEXT NOT NULL UNIQUE CHECK (market_day_ref LIKE 'mdy_%' AND length(market_day_ref) = 36),
  listing_id TEXT NOT NULL REFERENCES market_listing_binding(listing_id),
  trading_date TEXT NOT NULL CHECK (length(trading_date) = 10),
  created_by_request_id TEXT NOT NULL REFERENCES daily_market_history_request(request_id),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20),
  UNIQUE (listing_id, trading_date)
) STRICT;

CREATE TABLE market_day_revision (
  market_day_revision_id TEXT PRIMARY KEY CHECK (market_day_revision_id LIKE 'mdr_%' AND length(market_day_revision_id) = 36),
  market_day_revision_ref TEXT NOT NULL UNIQUE CHECK (market_day_revision_ref LIKE 'mrv_%' AND length(market_day_revision_ref) = 36),
  market_day_id TEXT NOT NULL REFERENCES market_day_entity(market_day_id),
  revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
  day_status TEXT NOT NULL CHECK (day_status IN ('observed','non_trading_day','source_gap')),
  bar_shape TEXT NOT NULL CHECK (bar_shape IN ('full_ohlcv','close_only','not_applicable')),
  open_decimal TEXT,
  high_decimal TEXT,
  low_decimal TEXT,
  close_decimal TEXT,
  adjusted_close_decimal TEXT,
  volume_decimal TEXT,
  corporate_action_status TEXT NOT NULL CHECK (corporate_action_status IN ('none_reported','pending_review','explicitly_reconciled','not_applicable')),
  valuation_status TEXT NOT NULL CHECK (valuation_status IN ('eligible','blocked_corporate_action','not_applicable')),
  quality_status TEXT NOT NULL CHECK (quality_status IN ('complete','corrected','calendar_confirmed','explicit_gap')),
  gap_reason TEXT CHECK (gap_reason IN ('source_no_data','source_partial_response','calendar_ambiguity')),
  source_observation_ref TEXT NOT NULL CHECK (source_observation_ref LIKE 'mor_%' AND length(source_observation_ref) = 36),
  observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc) = 20),
  source_day_fingerprint TEXT NOT NULL CHECK (length(source_day_fingerprint) = 64 AND source_day_fingerprint NOT GLOB '*[^a-f0-9]*'),
  request_id TEXT NOT NULL REFERENCES daily_market_history_request(request_id),
  correction_reason TEXT CHECK (correction_reason IN ('source_correction','calendar_correction','corporate_action_reconciliation','manual_review_correction')),
  supersedes_revision_id TEXT UNIQUE REFERENCES market_day_revision(market_day_revision_id),
  retrieved_at_utc TEXT NOT NULL CHECK (length(retrieved_at_utc) = 20),
  completed_at_utc TEXT NOT NULL CHECK (length(completed_at_utc) = 20),
  revision_fingerprint TEXT NOT NULL UNIQUE CHECK (length(revision_fingerprint) = 64 AND revision_fingerprint NOT GLOB '*[^a-f0-9]*'),
  UNIQUE (market_day_id, revision_no),
  CHECK (
    (day_status = 'observed' AND bar_shape IN ('full_ohlcv','close_only') AND close_decimal IS NOT NULL AND gap_reason IS NULL AND corporate_action_status != 'not_applicable' AND valuation_status != 'not_applicable') OR
    (day_status != 'observed' AND bar_shape = 'not_applicable' AND open_decimal IS NULL AND high_decimal IS NULL AND low_decimal IS NULL AND close_decimal IS NULL AND adjusted_close_decimal IS NULL AND volume_decimal IS NULL AND corporate_action_status = 'not_applicable' AND valuation_status = 'not_applicable')
  ),
  CHECK (
    (bar_shape = 'full_ohlcv' AND open_decimal IS NOT NULL AND high_decimal IS NOT NULL AND low_decimal IS NOT NULL AND volume_decimal IS NOT NULL) OR
    (bar_shape = 'close_only' AND open_decimal IS NULL AND high_decimal IS NULL AND low_decimal IS NULL AND volume_decimal IS NULL) OR
    bar_shape = 'not_applicable'
  ),
  CHECK ((day_status = 'source_gap' AND gap_reason IS NOT NULL AND quality_status = 'explicit_gap') OR (day_status != 'source_gap' AND gap_reason IS NULL)),
  CHECK ((day_status = 'non_trading_day' AND quality_status = 'calendar_confirmed') OR day_status != 'non_trading_day'),
  CHECK ((corporate_action_status = 'pending_review' AND valuation_status = 'blocked_corporate_action') OR (corporate_action_status IN ('none_reported','explicitly_reconciled') AND valuation_status = 'eligible') OR corporate_action_status = 'not_applicable')
) STRICT;

CREATE TABLE market_request_day_evidence (
  request_day_evidence_id TEXT PRIMARY KEY CHECK (request_day_evidence_id LIKE 'mde_%' AND length(request_day_evidence_id) = 36),
  request_id TEXT NOT NULL REFERENCES daily_market_history_request(request_id),
  row_ordinal INTEGER NOT NULL CHECK (row_ordinal >= 1),
  market_day_id TEXT NOT NULL REFERENCES market_day_entity(market_day_id),
  resulting_revision_id TEXT NOT NULL REFERENCES market_day_revision(market_day_revision_id),
  disposition TEXT NOT NULL CHECK (disposition IN ('appended','corrected','unchanged')),
  source_observation_ref TEXT NOT NULL CHECK (source_observation_ref LIKE 'mor_%' AND length(source_observation_ref) = 36),
  observed_at_utc TEXT NOT NULL CHECK (length(observed_at_utc) = 20),
  source_day_fingerprint TEXT NOT NULL CHECK (length(source_day_fingerprint) = 64 AND source_day_fingerprint NOT GLOB '*[^a-f0-9]*'),
  UNIQUE (request_id, row_ordinal),
  UNIQUE (request_id, market_day_id)
) STRICT;

CREATE VIEW current_market_day_revision AS
SELECT revision.* FROM market_day_revision revision
WHERE NOT EXISTS (
  SELECT 1 FROM market_day_revision successor
  WHERE successor.supersedes_revision_id = revision.market_day_revision_id
);

CREATE TRIGGER market_day_entity_scope BEFORE INSERT ON market_day_entity BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM daily_market_history_request request
    WHERE request.request_id = NEW.created_by_request_id AND request.listing_id = NEW.listing_id
  ) THEN RAISE(ABORT,'market_day_request_scope_invalid') END;
END;

CREATE TRIGGER market_day_revision_chain BEFORE INSERT ON market_day_revision BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM market_day_entity entity JOIN daily_market_history_request request ON request.request_id = NEW.request_id
    WHERE entity.market_day_id = NEW.market_day_id AND entity.listing_id = request.listing_id
  ) THEN RAISE(ABORT,'market_day_request_scope_invalid') END;
  SELECT CASE WHEN NEW.revision_no = 1 AND (
    NEW.supersedes_revision_id IS NOT NULL OR NEW.correction_reason IS NOT NULL OR
    EXISTS (SELECT 1 FROM market_day_revision WHERE market_day_id = NEW.market_day_id)
  ) THEN RAISE(ABORT,'market_day_initial_revision_invalid') END;
  SELECT CASE WHEN NEW.revision_no > 1 AND NOT EXISTS (
    SELECT 1 FROM current_market_day_revision old
    WHERE old.market_day_revision_id = NEW.supersedes_revision_id
      AND old.market_day_id = NEW.market_day_id
      AND old.revision_no + 1 = NEW.revision_no
      AND NEW.correction_reason IS NOT NULL
  ) THEN RAISE(ABORT,'market_day_revision_chain_invalid') END;
END;

CREATE TRIGGER market_request_day_evidence_scope BEFORE INSERT ON market_request_day_evidence BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1 FROM market_day_entity entity
    JOIN market_day_revision revision ON revision.market_day_revision_id = NEW.resulting_revision_id
    JOIN daily_market_history_request request ON request.request_id = NEW.request_id
    WHERE entity.market_day_id = NEW.market_day_id
      AND revision.market_day_id = entity.market_day_id
      AND request.listing_id = entity.listing_id
      AND ((NEW.disposition = 'appended' AND revision.request_id = NEW.request_id AND revision.revision_no = 1)
        OR (NEW.disposition = 'corrected' AND revision.request_id = NEW.request_id AND revision.revision_no > 1)
        OR (NEW.disposition = 'unchanged' AND revision.request_id != NEW.request_id))
  ) THEN RAISE(ABORT,'market_request_day_scope_invalid') END;
  SELECT CASE WHEN NEW.disposition != 'unchanged' AND NOT EXISTS (
    SELECT 1 FROM market_day_revision revision
    WHERE revision.market_day_revision_id = NEW.resulting_revision_id
      AND revision.source_observation_ref = NEW.source_observation_ref
      AND revision.observed_at_utc = NEW.observed_at_utc
      AND revision.source_day_fingerprint = NEW.source_day_fingerprint
  ) THEN RAISE(ABORT,'market_request_day_source_invalid') END;
  SELECT CASE WHEN EXISTS (
    SELECT 1 FROM market_request_day_evidence prior
    JOIN daily_market_history_request prior_request ON prior_request.request_id = prior.request_id
    JOIN daily_market_history_request current_request ON current_request.request_id = NEW.request_id
    WHERE prior.market_day_id = NEW.market_day_id
      AND prior.request_id != NEW.request_id
      AND prior_request.retrieved_at_utc >= current_request.retrieved_at_utc
  ) THEN RAISE(ABORT,'market_request_day_time_invalid') END;
END;

CREATE TRIGGER daily_market_history_store_binding_no_update BEFORE UPDATE ON daily_market_history_store_binding BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER daily_market_history_store_binding_no_delete BEFORE DELETE ON daily_market_history_store_binding BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER market_listing_binding_no_update BEFORE UPDATE ON market_listing_binding BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER market_listing_binding_no_delete BEFORE DELETE ON market_listing_binding BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER daily_market_history_request_no_update BEFORE UPDATE ON daily_market_history_request BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER daily_market_history_request_no_delete BEFORE DELETE ON daily_market_history_request BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER market_day_entity_no_update BEFORE UPDATE ON market_day_entity BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER market_day_entity_no_delete BEFORE DELETE ON market_day_entity BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER market_day_revision_no_update BEFORE UPDATE ON market_day_revision BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER market_day_revision_no_delete BEFORE DELETE ON market_day_revision BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER market_request_day_evidence_no_update BEFORE UPDATE ON market_request_day_evidence BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER market_request_day_evidence_no_delete BEFORE DELETE ON market_request_day_evidence BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;

COMMIT;
