PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
CREATE TABLE tax_applicability_entity(
 applicability_id TEXT PRIMARY KEY CHECK(applicability_id LIKE 'tae_%'),
 applicability_ref TEXT NOT NULL UNIQUE CHECK(applicability_ref LIKE 'tap_%'),
 portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),
 tax_year INTEGER NOT NULL CHECK(tax_year BETWEEN 1900 AND 9999),
 parameter_code TEXT NOT NULL CHECK(parameter_code='church_tax_applicable'),
 created_request_ref TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_attempt(request_ref),
 created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),
 UNIQUE(portfolio_ref,tax_year,parameter_code)
) STRICT;
CREATE TABLE tax_applicability_revision(
 applicability_revision_id TEXT PRIMARY KEY CHECK(applicability_revision_id LIKE 'tav_%'),
 applicability_id TEXT NOT NULL REFERENCES tax_applicability_entity(applicability_id),
 revision_no INTEGER NOT NULL CHECK(revision_no>=1),
 applicability_value TEXT CHECK(applicability_value IN ('applicable','not_applicable')),
 status TEXT NOT NULL CHECK(status IN ('active','retired')),
 supersedes_applicability_revision_id TEXT UNIQUE REFERENCES tax_applicability_revision(applicability_revision_id),
 request_ref TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_attempt(request_ref),
 created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),
 CHECK((status='active' AND applicability_value IS NOT NULL) OR (status='retired' AND applicability_value IS NULL)),
 UNIQUE(applicability_id,revision_no)
) STRICT;
CREATE VIEW current_tax_applicability_revision AS
SELECT revision.* FROM tax_applicability_revision revision
WHERE NOT EXISTS(
 SELECT 1 FROM tax_applicability_revision successor
 WHERE successor.supersedes_applicability_revision_id=revision.applicability_revision_id
);
CREATE TRIGGER tax_ui_applicability_chain BEFORE INSERT ON tax_applicability_revision BEGIN
 SELECT CASE WHEN NEW.revision_no=1 AND (NEW.supersedes_applicability_revision_id IS NOT NULL OR EXISTS(SELECT 1 FROM tax_applicability_revision WHERE applicability_id=NEW.applicability_id)) THEN RAISE(ABORT,'tax_ui_applicability_initial_invalid') END;
 SELECT CASE WHEN NEW.revision_no>1 AND NOT EXISTS(SELECT 1 FROM current_tax_applicability_revision old WHERE old.applicability_revision_id=NEW.supersedes_applicability_revision_id AND old.applicability_id=NEW.applicability_id AND old.revision_no+1=NEW.revision_no) THEN RAISE(ABORT,'tax_ui_applicability_chain_invalid') END;
END;
CREATE TRIGGER tax_ui_applicability_entity_no_update BEFORE UPDATE ON tax_applicability_entity BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_applicability_entity_no_delete BEFORE DELETE ON tax_applicability_entity BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_applicability_revision_no_update BEFORE UPDATE ON tax_applicability_revision BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_applicability_revision_no_delete BEFORE DELETE ON tax_applicability_revision BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
PRAGMA user_version=2201;
COMMIT;
