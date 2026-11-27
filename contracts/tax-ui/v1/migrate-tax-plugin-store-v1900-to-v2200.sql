PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
CREATE TABLE tax_ui_command_preview(
 preview_id TEXT PRIMARY KEY CHECK(preview_id LIKE 'tup_%'),preview_ref TEXT NOT NULL UNIQUE CHECK(preview_ref LIKE 'tprv_%'),
 command_type TEXT NOT NULL CHECK(command_type IN ('select_plugin','set_asset_classification','set_parameter','retire_asset_classification','retire_parameter')),
 portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 precondition_revision_token TEXT,preview_fingerprint TEXT NOT NULL UNIQUE CHECK(length(preview_fingerprint)=64),
 actor_id TEXT NOT NULL,created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20)
) STRICT;
CREATE TABLE tax_ui_command_confirmation(
 confirmation_id TEXT PRIMARY KEY CHECK(confirmation_id LIKE 'tuc_%'),confirmation_ref TEXT NOT NULL UNIQUE CHECK(confirmation_ref LIKE 'tcf_%'),
 preview_id TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_preview(preview_id),confirmation_fingerprint TEXT NOT NULL UNIQUE CHECK(length(confirmation_fingerprint)=64),
 actor_id TEXT NOT NULL,confirmed_at_utc TEXT NOT NULL CHECK(length(confirmed_at_utc)=20)
) STRICT;
CREATE TABLE tax_ui_command_attempt(
 attempt_id TEXT PRIMARY KEY CHECK(attempt_id LIKE 'tua_%'),attempt_ref TEXT NOT NULL UNIQUE CHECK(attempt_ref LIKE 'tat_%'),
 confirmation_id TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_confirmation(confirmation_id),request_ref TEXT NOT NULL UNIQUE CHECK(request_ref LIKE 'req_%'),
 attempted_at_utc TEXT NOT NULL CHECK(length(attempted_at_utc)=20)
) STRICT;
CREATE TABLE tax_ui_command_result(
 attempt_id TEXT PRIMARY KEY REFERENCES tax_ui_command_attempt(attempt_id),status TEXT NOT NULL CHECK(status IN ('completed','failed')),
 result_ref TEXT,failure_code TEXT,completed_at_utc TEXT NOT NULL CHECK(length(completed_at_utc)=20),
 CHECK((status='completed')=(result_ref IS NOT NULL AND failure_code IS NULL)),CHECK((status='failed')=(result_ref IS NULL AND failure_code IS NOT NULL))
) STRICT;
CREATE TABLE asset_tax_classification_entity(
 classification_id TEXT PRIMARY KEY CHECK(classification_id LIKE 'tce_%'),classification_ref TEXT NOT NULL UNIQUE CHECK(classification_ref LIKE 'tcr_%'),
 portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),asset_ref TEXT NOT NULL CHECK(asset_ref LIKE 'asf_%'),created_request_ref TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_attempt(request_ref),created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),UNIQUE(portfolio_ref,asset_ref)
) STRICT;
CREATE TABLE asset_tax_classification_revision(
 classification_revision_id TEXT PRIMARY KEY CHECK(classification_revision_id LIKE 'tcv_%'),classification_id TEXT NOT NULL REFERENCES asset_tax_classification_entity(classification_id),
 revision_no INTEGER NOT NULL CHECK(revision_no>=1),classification_code TEXT NOT NULL,tax_bucket TEXT NOT NULL,partial_exemption_rate_decimal TEXT NOT NULL,
 effective_from_year INTEGER NOT NULL CHECK(effective_from_year BETWEEN 1900 AND 9999),effective_to_year INTEGER,status TEXT NOT NULL CHECK(status IN ('active','retired')),
 supersedes_classification_revision_id TEXT UNIQUE REFERENCES asset_tax_classification_revision(classification_revision_id),request_ref TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_attempt(request_ref),created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),
 CHECK(effective_to_year IS NULL OR effective_to_year>=effective_from_year),UNIQUE(classification_id,revision_no)
) STRICT;
CREATE VIEW current_asset_tax_classification_revision AS SELECT revision.* FROM asset_tax_classification_revision revision WHERE NOT EXISTS(SELECT 1 FROM asset_tax_classification_revision successor WHERE successor.supersedes_classification_revision_id=revision.classification_revision_id);
CREATE TABLE tax_parameter_entity(
 parameter_id TEXT PRIMARY KEY CHECK(parameter_id LIKE 'tpe_%'),parameter_ref TEXT NOT NULL UNIQUE CHECK(parameter_ref LIKE 'tpm_%'),portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),
 tax_year INTEGER NOT NULL CHECK(tax_year BETWEEN 1900 AND 9999),parameter_code TEXT NOT NULL,currency TEXT NOT NULL CHECK(currency='' OR currency GLOB '[A-Z][A-Z][A-Z]'),created_request_ref TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_attempt(request_ref),created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),UNIQUE(portfolio_ref,tax_year,parameter_code,currency)
) STRICT;
CREATE TABLE tax_parameter_revision(
 parameter_revision_id TEXT PRIMARY KEY CHECK(parameter_revision_id LIKE 'tpv_%'),parameter_id TEXT NOT NULL REFERENCES tax_parameter_entity(parameter_id),revision_no INTEGER NOT NULL CHECK(revision_no>=1),
 value_kind TEXT NOT NULL CHECK(value_kind IN ('rate','amount')),rate_decimal TEXT,amount_decimal TEXT,status TEXT NOT NULL CHECK(status IN ('active','retired')),
 supersedes_parameter_revision_id TEXT UNIQUE REFERENCES tax_parameter_revision(parameter_revision_id),request_ref TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_attempt(request_ref),created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),
 CHECK((status='retired') OR (value_kind='rate' AND rate_decimal IS NOT NULL AND amount_decimal IS NULL) OR (value_kind='amount' AND amount_decimal IS NOT NULL AND rate_decimal IS NULL)),UNIQUE(parameter_id,revision_no)
) STRICT;
CREATE VIEW current_tax_parameter_revision AS SELECT revision.* FROM tax_parameter_revision revision WHERE NOT EXISTS(SELECT 1 FROM tax_parameter_revision successor WHERE successor.supersedes_parameter_revision_id=revision.parameter_revision_id);
CREATE TABLE tax_projection_invalidation(
 invalidation_id TEXT PRIMARY KEY CHECK(invalidation_id LIKE 'tii_%'),invalidation_ref TEXT NOT NULL UNIQUE CHECK(invalidation_ref LIKE 'tir_%'),request_ref TEXT NOT NULL REFERENCES tax_ui_command_attempt(request_ref),
 portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),projection_mode TEXT NOT NULL CHECK(projection_mode IN ('realized_event','realized_annual','unrealized_snapshot')),
 invalidated_from TEXT NOT NULL,reason_code TEXT NOT NULL CHECK(reason_code IN ('plugin_change','tax_classification_change','tax_parameter_change')),
 status TEXT NOT NULL CHECK(status='pending'),created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),UNIQUE(request_ref,projection_mode)
) STRICT;
CREATE TRIGGER tax_ui_classification_chain BEFORE INSERT ON asset_tax_classification_revision BEGIN
 SELECT CASE WHEN NEW.revision_no=1 AND (NEW.supersedes_classification_revision_id IS NOT NULL OR EXISTS(SELECT 1 FROM asset_tax_classification_revision WHERE classification_id=NEW.classification_id)) THEN RAISE(ABORT,'tax_ui_classification_initial_invalid') END;
 SELECT CASE WHEN NEW.revision_no>1 AND NOT EXISTS(SELECT 1 FROM current_asset_tax_classification_revision old WHERE old.classification_revision_id=NEW.supersedes_classification_revision_id AND old.classification_id=NEW.classification_id AND old.revision_no+1=NEW.revision_no AND NEW.effective_from_year>=old.effective_from_year) THEN RAISE(ABORT,'tax_ui_classification_chain_invalid') END;
END;
CREATE TRIGGER tax_ui_parameter_chain BEFORE INSERT ON tax_parameter_revision BEGIN
 SELECT CASE WHEN NEW.revision_no=1 AND (NEW.supersedes_parameter_revision_id IS NOT NULL OR EXISTS(SELECT 1 FROM tax_parameter_revision WHERE parameter_id=NEW.parameter_id)) THEN RAISE(ABORT,'tax_ui_parameter_initial_invalid') END;
 SELECT CASE WHEN NEW.revision_no>1 AND NOT EXISTS(SELECT 1 FROM current_tax_parameter_revision old WHERE old.parameter_revision_id=NEW.supersedes_parameter_revision_id AND old.parameter_id=NEW.parameter_id AND old.revision_no+1=NEW.revision_no) THEN RAISE(ABORT,'tax_ui_parameter_chain_invalid') END;
END;
CREATE TRIGGER tax_ui_preview_no_update BEFORE UPDATE ON tax_ui_command_preview BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_preview_no_delete BEFORE DELETE ON tax_ui_command_preview BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_confirmation_no_update BEFORE UPDATE ON tax_ui_command_confirmation BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_confirmation_no_delete BEFORE DELETE ON tax_ui_command_confirmation BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_attempt_no_update BEFORE UPDATE ON tax_ui_command_attempt BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_attempt_no_delete BEFORE DELETE ON tax_ui_command_attempt BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_result_no_update BEFORE UPDATE ON tax_ui_command_result BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_result_no_delete BEFORE DELETE ON tax_ui_command_result BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_classification_entity_no_update BEFORE UPDATE ON asset_tax_classification_entity BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_classification_entity_no_delete BEFORE DELETE ON asset_tax_classification_entity BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_classification_revision_no_update BEFORE UPDATE ON asset_tax_classification_revision BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_classification_revision_no_delete BEFORE DELETE ON asset_tax_classification_revision BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_parameter_entity_no_update BEFORE UPDATE ON tax_parameter_entity BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_parameter_entity_no_delete BEFORE DELETE ON tax_parameter_entity BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_parameter_revision_no_update BEFORE UPDATE ON tax_parameter_revision BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_parameter_revision_no_delete BEFORE DELETE ON tax_parameter_revision BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_invalidation_no_update BEFORE UPDATE ON tax_projection_invalidation BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_invalidation_no_delete BEFORE DELETE ON tax_projection_invalidation BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
PRAGMA user_version=2200;
COMMIT;
