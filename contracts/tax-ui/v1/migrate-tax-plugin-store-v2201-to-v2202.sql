-- Steuerliche Vorgabe je Asset-Typ.
--
-- Klassifiziert wurde bisher ausschliesslich je Asset, also viele Einzeleintraege von Hand, und die Bereitschaft blieb
-- 'classification_required', solange auch nur einer fehlte. Die Regel haengt
-- aber am Typ: Aktien sind Aktien, Fonds sind Fonds. Die Vorgabe steht deshalb
-- am Typ; ein Einzelasset darf sie ueberschreiben, wenn es abweicht
-- (#367).
--
-- Gleiche Bauart wie die uebrigen Tabellen dieses Speichers: append-only mit
-- Revisionskette, unveraenderlich, nichts wird ueberschrieben oder geloescht.
PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
CREATE TABLE asset_type_tax_classification_entity(
 type_classification_id TEXT PRIMARY KEY CHECK(type_classification_id LIKE 'tye_%'),
 type_classification_ref TEXT NOT NULL UNIQUE CHECK(type_classification_ref LIKE 'typ_%'),
 portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),
 asset_type TEXT NOT NULL CHECK(length(asset_type) BETWEEN 2 AND 40),
 created_request_ref TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_attempt(request_ref),
 created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),
 UNIQUE(portfolio_ref,asset_type)
) STRICT;
CREATE TABLE asset_type_tax_classification_revision(
 type_classification_revision_id TEXT PRIMARY KEY CHECK(type_classification_revision_id LIKE 'tyv_%'),
 type_classification_id TEXT NOT NULL REFERENCES asset_type_tax_classification_entity(type_classification_id),
 revision_no INTEGER NOT NULL CHECK(revision_no>=1),
 classification_code TEXT NOT NULL,
 tax_bucket TEXT NOT NULL,
 partial_exemption_rate_decimal TEXT NOT NULL,
 effective_from_year INTEGER NOT NULL CHECK(effective_from_year BETWEEN 1900 AND 9999),
 effective_to_year INTEGER,
 status TEXT NOT NULL CHECK(status IN ('active','retired')),
 supersedes_type_classification_revision_id TEXT UNIQUE REFERENCES asset_type_tax_classification_revision(type_classification_revision_id),
 request_ref TEXT NOT NULL UNIQUE REFERENCES tax_ui_command_attempt(request_ref),
 created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20),
 CHECK(effective_to_year IS NULL OR effective_to_year>=effective_from_year),
 UNIQUE(type_classification_id,revision_no)
) STRICT;
CREATE VIEW current_asset_type_tax_classification_revision AS
SELECT revision.* FROM asset_type_tax_classification_revision revision
WHERE NOT EXISTS(
 SELECT 1 FROM asset_type_tax_classification_revision successor
 WHERE successor.supersedes_type_classification_revision_id=revision.type_classification_revision_id
);
CREATE TRIGGER tax_ui_type_classification_chain BEFORE INSERT ON asset_type_tax_classification_revision BEGIN
 SELECT CASE WHEN NEW.revision_no=1 AND (NEW.supersedes_type_classification_revision_id IS NOT NULL OR EXISTS(SELECT 1 FROM asset_type_tax_classification_revision WHERE type_classification_id=NEW.type_classification_id)) THEN RAISE(ABORT,'tax_ui_type_classification_initial_invalid') END;
 SELECT CASE WHEN NEW.revision_no>1 AND NOT EXISTS(SELECT 1 FROM current_asset_type_tax_classification_revision old WHERE old.type_classification_revision_id=NEW.supersedes_type_classification_revision_id AND old.type_classification_id=NEW.type_classification_id AND old.revision_no+1=NEW.revision_no) THEN RAISE(ABORT,'tax_ui_type_classification_chain_invalid') END;
END;
CREATE TRIGGER tax_ui_type_classification_entity_no_update BEFORE UPDATE ON asset_type_tax_classification_entity BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_type_classification_entity_no_delete BEFORE DELETE ON asset_type_tax_classification_entity BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_type_classification_revision_no_update BEFORE UPDATE ON asset_type_tax_classification_revision BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_type_classification_revision_no_delete BEFORE DELETE ON asset_type_tax_classification_revision BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
-- Die Vorschautabelle begrenzt die Befehlstypen per CHECK. SQLite kann eine
-- Pruefbedingung nicht aendern; die Tabelle wird deshalb nach dem in der
-- SQLite-Dokumentation vorgesehenen Verfahren neu erstellt und ihr Inhalt
-- uebernommen. Die Loeschsperre wird dafuer kurz abgelegt und danach wieder
-- gesetzt - sonst verboete sie ihre eigene Ersetzung.
DROP TRIGGER tax_ui_preview_no_update;
DROP TRIGGER tax_ui_preview_no_delete;
CREATE TABLE tax_ui_command_preview_v2202(
 preview_id TEXT PRIMARY KEY CHECK(preview_id LIKE 'tup_%'),preview_ref TEXT NOT NULL UNIQUE CHECK(preview_ref LIKE 'tprv_%'),
 command_type TEXT NOT NULL CHECK(command_type IN ('select_plugin','set_asset_classification','set_asset_type_classification','set_parameter','retire_asset_classification','retire_asset_type_classification','retire_parameter')),
 portfolio_ref TEXT NOT NULL CHECK(portfolio_ref LIKE 'pfr_%'),payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
 precondition_revision_token TEXT,preview_fingerprint TEXT NOT NULL UNIQUE CHECK(length(preview_fingerprint)=64),
 actor_id TEXT NOT NULL,created_at_utc TEXT NOT NULL CHECK(length(created_at_utc)=20)
) STRICT;
INSERT INTO tax_ui_command_preview_v2202 SELECT * FROM tax_ui_command_preview;
DROP TABLE tax_ui_command_preview;
ALTER TABLE tax_ui_command_preview_v2202 RENAME TO tax_ui_command_preview;
CREATE TRIGGER tax_ui_preview_no_update BEFORE UPDATE ON tax_ui_command_preview BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_preview_no_delete BEFORE DELETE ON tax_ui_command_preview BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
PRAGMA user_version=2202;
COMMIT;
