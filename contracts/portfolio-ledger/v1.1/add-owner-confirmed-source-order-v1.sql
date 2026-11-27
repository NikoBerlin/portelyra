PRAGMA foreign_keys = ON;

CREATE TABLE asset_activity_fifo_order_evidence (
  event_ref TEXT PRIMARY KEY REFERENCES asset_activity_event(event_ref),
  evidence_mode TEXT NOT NULL CHECK (evidence_mode = 'owner_confirmed_source_row_order'),
  source_file_fingerprint TEXT NOT NULL CHECK (
    length(source_file_fingerprint) = 64
    AND source_file_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  source_row_ordinal INTEGER NOT NULL CHECK (source_row_ordinal > 0),
  owner_decision_fingerprint TEXT NOT NULL CHECK (
    length(owner_decision_fingerprint) = 64
    AND owner_decision_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  evidence_fingerprint TEXT NOT NULL UNIQUE CHECK (
    length(evidence_fingerprint) = 64
    AND evidence_fingerprint NOT GLOB '*[^a-f0-9]*'
  ),
  UNIQUE (source_file_fingerprint, source_row_ordinal)
) STRICT;

CREATE TRIGGER asset_activity_fifo_order_evidence_validate
BEFORE INSERT ON asset_activity_fifo_order_evidence
BEGIN
  SELECT CASE WHEN NOT EXISTS (
    SELECT 1
    FROM asset_activity_event event
    WHERE event.event_ref = NEW.event_ref
      AND event.event_type IN ('buy', 'sell', 'stock_dividend', 'reward', 'deposit', 'withdrawal', 'transfer')
      AND event.event_time_evidence = 'exact'
      AND event.effective_at_utc IS NOT NULL
  ) THEN RAISE(ABORT, 'asset_activity_fifo_order_evidence_event_invalid') END;
END;

CREATE TRIGGER asset_activity_fifo_order_evidence_no_update
BEFORE UPDATE ON asset_activity_fifo_order_evidence
BEGIN
  SELECT RAISE(ABORT, 'asset_activity_fifo_order_evidence_immutable');
END;

CREATE TRIGGER asset_activity_fifo_order_evidence_no_delete
BEFORE DELETE ON asset_activity_fifo_order_evidence
BEGIN
  SELECT RAISE(ABORT, 'asset_activity_fifo_order_evidence_immutable');
END;
