PRAGMA foreign_keys=ON;
PRAGMA user_version=1900;
BEGIN IMMEDIATE;
CREATE TABLE tax_plugin_store_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),schema_version INTEGER NOT NULL CHECK(schema_version=1900),context_binding_fingerprint TEXT NOT NULL CHECK(length(context_binding_fingerprint)=64),created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20)) STRICT;
CREATE TABLE tax_plugin_selection_entity(
 selection_id TEXT PRIMARY KEY CHECK(selection_id LIKE 'tse_%'),selection_ref TEXT NOT NULL UNIQUE CHECK(selection_ref LIKE 'tsr_%'),
 portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),projection_mode TEXT NOT NULL CHECK(projection_mode IN ('realized_event','realized_annual','unrealized_snapshot')),
 created_request_ref TEXT NOT NULL UNIQUE CHECK(created_request_ref LIKE 'req_%'),created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),UNIQUE(portfolio_ref,projection_mode)
) STRICT;
CREATE TABLE tax_plugin_selection_revision(
 selection_revision_id TEXT PRIMARY KEY CHECK(selection_revision_id LIKE 'tsv_%'),selection_id TEXT NOT NULL REFERENCES tax_plugin_selection_entity(selection_id),
 revision_no INTEGER NOT NULL CHECK(revision_no>=1),plugin_id TEXT NOT NULL CHECK(plugin_id GLOB 'tax_[a-z0-9_]*'),plugin_version TEXT NOT NULL,
 rules_fingerprint TEXT NOT NULL CHECK(length(rules_fingerprint)=64),manifest_fingerprint TEXT NOT NULL CHECK(length(manifest_fingerprint)=64),
 effective_from TEXT NOT NULL CHECK(length(effective_from)=10),status TEXT NOT NULL CHECK(status IN ('active','retired')),
 supersedes_selection_revision_id TEXT UNIQUE REFERENCES tax_plugin_selection_revision(selection_revision_id),request_ref TEXT NOT NULL UNIQUE CHECK(request_ref LIKE 'req_%'),
 created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),UNIQUE(selection_id,revision_no)
) STRICT;
CREATE VIEW current_tax_plugin_selection_revision AS SELECT revision.* FROM tax_plugin_selection_revision revision WHERE NOT EXISTS(SELECT 1 FROM tax_plugin_selection_revision successor WHERE successor.supersedes_selection_revision_id=revision.selection_revision_id);
CREATE TRIGGER tax_plugin_selection_chain BEFORE INSERT ON tax_plugin_selection_revision BEGIN
 SELECT CASE WHEN NEW.revision_no=1 AND (NEW.supersedes_selection_revision_id IS NOT NULL OR EXISTS(SELECT 1 FROM tax_plugin_selection_revision WHERE selection_id=NEW.selection_id)) THEN RAISE(ABORT,'tax_plugin_selection_initial_invalid') END;
 SELECT CASE WHEN NEW.revision_no>1 AND NOT EXISTS(SELECT 1 FROM current_tax_plugin_selection_revision old WHERE old.selection_revision_id=NEW.supersedes_selection_revision_id AND old.selection_id=NEW.selection_id AND old.revision_no+1=NEW.revision_no AND NEW.effective_from>old.effective_from) THEN RAISE(ABORT,'tax_plugin_selection_chain_invalid') END;
END;
CREATE TRIGGER tax_plugin_binding_no_update BEFORE UPDATE ON tax_plugin_store_binding BEGIN SELECT RAISE(ABORT,'tax_plugin_immutable'); END;
CREATE TRIGGER tax_plugin_binding_no_delete BEFORE DELETE ON tax_plugin_store_binding BEGIN SELECT RAISE(ABORT,'tax_plugin_immutable'); END;
CREATE TRIGGER tax_plugin_selection_entity_no_update BEFORE UPDATE ON tax_plugin_selection_entity BEGIN SELECT RAISE(ABORT,'tax_plugin_immutable'); END;
CREATE TRIGGER tax_plugin_selection_entity_no_delete BEFORE DELETE ON tax_plugin_selection_entity BEGIN SELECT RAISE(ABORT,'tax_plugin_immutable'); END;
CREATE TRIGGER tax_plugin_selection_revision_no_update BEFORE UPDATE ON tax_plugin_selection_revision BEGIN SELECT RAISE(ABORT,'tax_plugin_immutable'); END;
CREATE TRIGGER tax_plugin_selection_revision_no_delete BEFORE DELETE ON tax_plugin_selection_revision BEGIN SELECT RAISE(ABORT,'tax_plugin_immutable'); END;
COMMIT;
