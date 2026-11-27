-- Store-Migration 2300 -> 2400.
--
-- Anlass: Eine Kurshistorie haengt an der Listing-Freigabe. Wird eine Freigabe
-- erneuert - etwa weil ihr Katalog-Fingerprint aus einer aelteren
-- Produktversion stammt -, entsteht eine neue Freigabe mit leerem Bestand, und
-- die Historie muss vollstaendig neu bei der Quelle geholt werden (#283).
--
-- Die Uebernahme braucht eine eigene Herkunftsangabe: Uebernommene Tage sind
-- nicht bei der Quelle geholt worden. 'carried_listing' benennt das. Die
-- Alternative - sie als 'manual_reviewed_evidence' zu fuehren - waere im
-- Pruefpfad eine Unwahrheit.
--
-- Nur die Tabelle daily_market_history_request traegt die Pruefliste der
-- Herkunftsarten; sie zaehlt je Speicher einige hundert Zeilen. Die
-- Tagesbestaende bleiben unberuehrt.
PRAGMA legacy_alter_table=ON;
PRAGMA foreign_keys=OFF;
BEGIN IMMEDIATE;

DROP TRIGGER daily_market_history_request_no_update;
DROP TRIGGER daily_market_history_request_no_delete;

CREATE TABLE daily_market_history_request_v2400 (
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

INSERT INTO daily_market_history_request_v2400 SELECT * FROM daily_market_history_request;
DROP TABLE daily_market_history_request;
ALTER TABLE daily_market_history_request_v2400 RENAME TO daily_market_history_request;

CREATE TRIGGER daily_market_history_request_no_update BEFORE UPDATE ON daily_market_history_request BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER daily_market_history_request_no_delete BEFORE DELETE ON daily_market_history_request BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;

-- Die Versionsangabe des Speichers steht unter einer Pruefliste und laesst sich
-- nicht fortschreiben; die Zeile wird deshalb mit umgebaut.
DROP TRIGGER daily_market_history_store_binding_no_update;
DROP TRIGGER daily_market_history_store_binding_no_delete;

CREATE TABLE daily_market_history_store_binding_v2400 (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 2400),
  context_binding_fingerprint TEXT NOT NULL CHECK (length(context_binding_fingerprint) = 64 AND context_binding_fingerprint NOT GLOB '*[^a-f0-9]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20)
) STRICT;

INSERT INTO daily_market_history_store_binding_v2400 (singleton_id, schema_version, context_binding_fingerprint, created_at_utc)
  SELECT singleton_id, 2400, context_binding_fingerprint, created_at_utc FROM daily_market_history_store_binding;
DROP TABLE daily_market_history_store_binding;
ALTER TABLE daily_market_history_store_binding_v2400 RENAME TO daily_market_history_store_binding;

CREATE TRIGGER daily_market_history_store_binding_no_update BEFORE UPDATE ON daily_market_history_store_binding BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;
CREATE TRIGGER daily_market_history_store_binding_no_delete BEFORE DELETE ON daily_market_history_store_binding BEGIN SELECT RAISE(ABORT,'daily_market_history_immutable'); END;

PRAGMA user_version = 2400;
COMMIT;
PRAGMA foreign_keys=ON;
PRAGMA legacy_alter_table=OFF;
