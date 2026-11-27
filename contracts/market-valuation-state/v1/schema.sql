-- Bewertungsstand v1: fortschreibbare Tagesreihe statt Neuberechnung.
--
-- Der Stand haelt, was die Bewertung eines Tages ergeben hat, und den Uebertrag,
-- mit dem der naechste Tag weitergerechnet wird. Ein Tag haengt ausschliesslich
-- von Tagen <= ihm ab (siehe valuation_day_step); deshalb ist Anhaengen zulaessig
-- und ein Neuaufbau von vorn muss zwingend dasselbe ergeben (#283, 26.09.2026).
PRAGMA user_version = 105;

CREATE TABLE valuation_state_binding (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 105),
  context_fingerprint TEXT NOT NULL CHECK (length(context_fingerprint) = 64 AND context_fingerprint NOT GLOB '*[^a-f0-9]*'),
  -- Fingerprint ueber den Quelltext der Rechenfunktionen. Aendert sich die
  -- Rechnung, passt der Stand nicht mehr und wird neu aufgebaut - sichtbar,
  -- nicht stillschweigend.
  algorithm_id TEXT NOT NULL CHECK (length(algorithm_id) BETWEEN 3 AND 80),
  algorithm_fingerprint TEXT NOT NULL CHECK (length(algorithm_fingerprint) = 64 AND algorithm_fingerprint NOT GLOB '*[^a-f0-9]*'),
  created_at_utc TEXT NOT NULL CHECK (length(created_at_utc) = 20)
) STRICT;

-- Ein Waehrungspaar wird einmal gefaltet, nicht je Asset.
CREATE TABLE fx_effective_watermark (
  pair_ref TEXT PRIMARY KEY CHECK (pair_ref LIKE 'fxp_%' AND length(pair_ref) = 36),
  policy_fingerprint TEXT NOT NULL CHECK (length(policy_fingerprint) = 64 AND policy_fingerprint NOT GLOB '*[^a-f0-9]*'),
  -- Anfang und Ende des berechneten Fensters. Ohne den Anfang gaelte ein spaeter
  -- verlangter frueherer Beginn als "nichts Neues", und die Reihe kaeme zu kurz
  -- zurueck (26.09.2026, #283).
  valued_from_date TEXT NOT NULL CHECK (length(valued_from_date) = 10),
  valued_through_date TEXT NOT NULL CHECK (length(valued_through_date) = 10 AND valued_through_date >= valued_from_date),
  resume_from TEXT NOT NULL CHECK (length(resume_from) = 10 AND resume_from > valued_through_date),
  previous_date TEXT CHECK (previous_date IS NULL OR length(previous_date) = 10),
  previous_value TEXT CHECK (previous_value IS NULL OR length(previous_value) BETWEEN 1 AND 80),
  crossed_gap INTEGER NOT NULL CHECK (crossed_gap IN (0, 1)),
  consumed_request_fingerprint TEXT NOT NULL CHECK (length(consumed_request_fingerprint) = 64 AND consumed_request_fingerprint NOT GLOB '*[^a-f0-9]*'),
  updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc) = 20),
  CHECK ((previous_date IS NULL) = (previous_value IS NULL))
) STRICT;

CREATE TABLE fx_effective_day (
  pair_ref TEXT NOT NULL REFERENCES fx_effective_watermark(pair_ref),
  rate_date TEXT NOT NULL CHECK (length(rate_date) = 10),
  rate_decimal TEXT CHECK (rate_decimal IS NULL OR length(rate_decimal) BETWEEN 1 AND 80),
  basis TEXT NOT NULL CHECK (length(basis) BETWEEN 3 AND 40),
  source_date TEXT CHECK (source_date IS NULL OR length(source_date) = 10),
  age_days INTEGER CHECK (age_days IS NULL OR age_days >= 0),
  calendar_reason TEXT NOT NULL CHECK (length(calendar_reason) BETWEEN 3 AND 40),
  native_status TEXT CHECK (native_status IS NULL OR length(native_status) BETWEEN 3 AND 40),
  substitution_used INTEGER NOT NULL CHECK (substitution_used IN (0, 1)),
  PRIMARY KEY (pair_ref, rate_date)
) STRICT;

-- Ein bewerteter Bereich: ein Asset an einer Notierung unter einer Richtlinie.
-- Aendert sich die Richtlinie, ist es ein anderer Bereich - alte Zeilen bleiben
-- gueltig fuer ihre Richtlinie und werden nicht stillschweigend ueberschrieben.
CREATE TABLE valuation_scope (
  scope_ref TEXT PRIMARY KEY CHECK (scope_ref LIKE 'vsc_%' AND length(scope_ref) = 36),
  -- Die kanonische Assetkennung, nicht die laufende Nummer der Katalogansicht:
  -- deren Schema heisst ausdruecklich "activity_catalog_ephemeral_v1" und haengt
  -- an der Listenposition. Ein hinzugekommenes Asset haette die Zeilen sonst
  -- einem anderen zugeordnet (26.09.2026, #283).
  asset_id TEXT NOT NULL CHECK (length(asset_id) BETWEEN 3 AND 128),
  listing_ref TEXT NOT NULL CHECK (listing_ref LIKE 'lsr_%' AND length(listing_ref) = 36),
  provider_symbol TEXT NOT NULL CHECK (length(provider_symbol) BETWEEN 1 AND 64),
  quote_currency TEXT NOT NULL CHECK (length(quote_currency) = 3),
  target_currency TEXT NOT NULL CHECK (target_currency = 'EUR'),
  pair_ref TEXT REFERENCES fx_effective_watermark(pair_ref),
  direction TEXT NOT NULL CHECK (direction IN ('identity', 'direct', 'inverse')),
  -- Die Bewertungsrichtlinie gehoert NICHT in die Identitaet des Bereichs.
  -- Sie tat es bis rc.190, und das Kalenderprofil traegt die auf das Fenster
  -- zugeschnittenen Schliesstage: Rueckte das Fensterende ueber einen Feiertag,
  -- entstand ein zweiter Bereich fuer dasselbe Asset an derselben Notierung -
  -- und der Snapshot zaehlte dessen Bestand doppelt. Die Richtlinie ist eine
  -- Eingabe und steht am Wasserstand (26.09.2026, #283).
  UNIQUE (asset_id, listing_ref),
  CHECK ((quote_currency = target_currency) = (pair_ref IS NULL)),
  CHECK ((direction = 'identity') = (pair_ref IS NULL))
) STRICT;

CREATE TABLE valuation_watermark (
  scope_ref TEXT PRIMARY KEY REFERENCES valuation_scope(scope_ref),
  -- Anfang und Ende des berechneten Fensters. Ohne den Anfang gaelte ein spaeter
  -- verlangter frueherer Beginn als "nichts Neues", und die Reihe kaeme zu kurz
  -- zurueck (26.09.2026, #283).
  valued_from_date TEXT NOT NULL CHECK (length(valued_from_date) = 10),
  valued_through_date TEXT NOT NULL CHECK (length(valued_through_date) = 10 AND valued_through_date >= valued_from_date),
  resume_from TEXT NOT NULL CHECK (length(resume_from) = 10 AND resume_from > valued_through_date),
  previous_date TEXT CHECK (previous_date IS NULL OR length(previous_date) = 10),
  previous_value TEXT CHECK (previous_value IS NULL OR length(previous_value) BETWEEN 1 AND 80),
  crossed_gap INTEGER NOT NULL CHECK (crossed_gap IN (0, 1)),
  -- Woran erkannt wird, dass etwas Zurueckliegendes sich geaendert hat: die
  -- verbrauchten Anfragen der Notierung und die offenen Abrufstaende. Beide
  -- Mengen sind lueckenlos protokolliert.
  policy_fingerprint TEXT NOT NULL CHECK (length(policy_fingerprint) = 64 AND policy_fingerprint NOT GLOB '*[^a-f0-9]*'),
  consumed_request_fingerprint TEXT NOT NULL CHECK (length(consumed_request_fingerprint) = 64 AND consumed_request_fingerprint NOT GLOB '*[^a-f0-9]*'),
  barrier_fingerprint TEXT NOT NULL CHECK (length(barrier_fingerprint) = 64 AND barrier_fingerprint NOT GLOB '*[^a-f0-9]*'),
  -- Die EUR-Zeilen haengen am Wechselkursvektor. Ohne diesen Fingerprint bliebe
  -- eine geaenderte Umrechnung unbemerkt: Der Kurs waere derselbe, das Ergebnis
  -- nicht (26.09.2026, #283).
  pair_fingerprint TEXT NOT NULL CHECK (length(pair_fingerprint) = 64 AND pair_fingerprint NOT GLOB '*[^a-f0-9]*'),
  updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc) = 20),
  CHECK ((previous_date IS NULL) = (previous_value IS NULL))
) STRICT;

CREATE TABLE valuation_day (
  scope_ref TEXT NOT NULL REFERENCES valuation_scope(scope_ref),
  trading_date TEXT NOT NULL CHECK (length(trading_date) = 10),
  status TEXT NOT NULL CHECK (status IN ('native', 'converted', 'market_unavailable', 'fx_unavailable')),
  target_decimal TEXT CHECK (target_decimal IS NULL OR length(target_decimal) BETWEEN 1 AND 120),
  target_numerator TEXT CHECK (target_numerator IS NULL OR length(target_numerator) BETWEEN 1 AND 120),
  target_denominator TEXT CHECK (target_denominator IS NULL OR length(target_denominator) BETWEEN 1 AND 120),
  original_price TEXT CHECK (original_price IS NULL OR length(original_price) BETWEEN 1 AND 80),
  effective_price TEXT CHECK (effective_price IS NULL OR length(effective_price) BETWEEN 1 AND 80),
  price_basis TEXT NOT NULL CHECK (length(price_basis) BETWEEN 3 AND 40),
  price_source_date TEXT CHECK (price_source_date IS NULL OR length(price_source_date) = 10),
  price_age_days INTEGER CHECK (price_age_days IS NULL OR price_age_days >= 0),
  price_calendar_reason TEXT NOT NULL CHECK (length(price_calendar_reason) BETWEEN 3 AND 40),
  price_on_closed_day INTEGER NOT NULL CHECK (price_on_closed_day IN (0, 1)),
  price_native_status TEXT CHECK (price_native_status IS NULL OR length(price_native_status) BETWEEN 3 AND 40),
  price_source_kind TEXT CHECK (price_source_kind IS NULL OR length(price_source_kind) BETWEEN 3 AND 40),
  fx_rate TEXT CHECK (fx_rate IS NULL OR length(fx_rate) BETWEEN 1 AND 80),
  fx_basis TEXT NOT NULL CHECK (length(fx_basis) BETWEEN 3 AND 40),
  fx_source_date TEXT CHECK (fx_source_date IS NULL OR length(fx_source_date) = 10),
  fx_age_days INTEGER CHECK (fx_age_days IS NULL OR fx_age_days >= 0),
  fx_calendar_reason TEXT CHECK (fx_calendar_reason IS NULL OR length(fx_calendar_reason) BETWEEN 3 AND 40),
  fx_native_status TEXT CHECK (fx_native_status IS NULL OR length(fx_native_status) BETWEEN 3 AND 40),
  substitution_used INTEGER NOT NULL CHECK (substitution_used IN (0, 1)),
  valuation_status TEXT NOT NULL CHECK (valuation_status IN ('complete', 'substituted', 'incomplete')),
  PRIMARY KEY (scope_ref, trading_date),
  -- Ein bewerteter Tag traegt einen Wert, ein unbewerteter keinen.
  CHECK ((status IN ('native', 'converted')) = (target_decimal IS NOT NULL)),
  CHECK ((target_decimal IS NULL) = (target_numerator IS NULL)),
  CHECK ((target_numerator IS NULL) = (target_denominator IS NULL)),
  CHECK ((valuation_status = 'incomplete') = (target_decimal IS NULL)),
  CHECK ((valuation_status = 'substituted') = (substitution_used = 1))
) STRICT;

CREATE TABLE valuation_state_job (
  job_ref TEXT PRIMARY KEY CHECK (job_ref LIKE 'vsj_%' AND length(job_ref) = 36),
  request_mode TEXT NOT NULL CHECK (request_mode IN ('full_rebuild', 'incremental')),
  prior_job_ref TEXT REFERENCES valuation_state_job(job_ref),
  algorithm_fingerprint TEXT NOT NULL CHECK (length(algorithm_fingerprint) = 64 AND algorithm_fingerprint NOT GLOB '*[^a-f0-9]*'),
  scope_count INTEGER NOT NULL CHECK (scope_count >= 0),
  appended_day_count INTEGER NOT NULL CHECK (appended_day_count >= 0),
  recomputed_day_count INTEGER NOT NULL CHECK (recomputed_day_count >= 0),
  requested_at_utc TEXT NOT NULL CHECK (length(requested_at_utc) = 20),
  job_fingerprint TEXT NOT NULL UNIQUE CHECK (length(job_fingerprint) = 64 AND job_fingerprint NOT GLOB '*[^a-f0-9]*')
) STRICT;

CREATE INDEX valuation_day_by_date ON valuation_day (trading_date);

-- Der zuletzt angeforderte Intraday-Stand: eine Zeile je Bereich, bei jeder
-- neuen Anforderung ueberschrieben. Er ist fluechtig und gehoert nicht in den
-- Kursspeicher - ein Zwischenstand der laufenden Sitzung ist kein Tagesschluss.
-- Schlaegt der Abruf fehl, traegt die Zeile den juengsten Tagesschluss und sagt
-- das auch: basis = 'last_close' (Festlegung 26.09.2026, #283).
CREATE TABLE intraday_quote (
  scope_ref TEXT PRIMARY KEY REFERENCES valuation_scope(scope_ref),
  requested_at_utc TEXT NOT NULL CHECK (length(requested_at_utc) = 20),
  basis TEXT NOT NULL CHECK (basis IN ('intraday', 'last_close', 'unavailable')),
  observed_at_utc TEXT CHECK (observed_at_utc IS NULL OR length(observed_at_utc) = 20),
  as_of_date TEXT CHECK (as_of_date IS NULL OR length(as_of_date) = 10),
  native_decimal TEXT CHECK (native_decimal IS NULL OR length(native_decimal) BETWEEN 1 AND 80),
  native_currency TEXT NOT NULL CHECK (length(native_currency) = 3),
  fx_rate TEXT CHECK (fx_rate IS NULL OR length(fx_rate) BETWEEN 1 AND 80),
  fx_basis TEXT NOT NULL CHECK (fx_basis IN ('identity', 'intraday', 'last_close', 'pair_missing', 'unavailable')),
  target_decimal TEXT CHECK (target_decimal IS NULL OR length(target_decimal) BETWEEN 1 AND 120),
  target_numerator TEXT CHECK (target_numerator IS NULL OR length(target_numerator) BETWEEN 1 AND 120),
  target_denominator TEXT CHECK (target_denominator IS NULL OR length(target_denominator) BETWEEN 1 AND 120),
  note TEXT CHECK (note IS NULL OR length(note) BETWEEN 3 AND 160),
  CHECK ((basis = 'unavailable') = (target_decimal IS NULL)),
  CHECK ((target_decimal IS NULL) = (target_numerator IS NULL)),
  CHECK ((target_numerator IS NULL) = (target_denominator IS NULL))
) STRICT;

-- Wie viele Abrufe gleichzeitig laufen duerfen. Die Arbeit wartet auf das Netz,
-- nicht auf die CPU; die Grenze setzt die Quelle (Festlegung 26.09.2026).
-- carry_across_blocked: Ob ein gesperrter Tag den Vorgaenger loescht. Eine Sperre
-- sagt nur, dass ueber diesen einen Tag nichts feststeht; der Kurs des Vortages
-- bleibt ein Fakt. Ohne diesen Schalter steckte eine Sperre alle Folgetage an
-- (#368, 28.09.2026). Der gesperrte Tag selbst bleibt in jedem Fall ohne Wert.
CREATE TABLE snapshot_setting (
  singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
  parallel_request_count INTEGER NOT NULL DEFAULT 8 CHECK (parallel_request_count BETWEEN 1 AND 32),
  carry_across_blocked INTEGER NOT NULL DEFAULT 0 CHECK (carry_across_blocked IN (0, 1)),
  updated_at_utc TEXT NOT NULL CHECK (length(updated_at_utc) = 20)
) STRICT;
