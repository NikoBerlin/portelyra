-- Eine Einordnung je Asset laesst sich rueckwirkend korrigieren.
--
-- Die Kette der Einzeleinordnung verlangte, dass eine neue Fassung nicht frueher
-- gilt als die bestehende (NEW.effective_from_year >= old.effective_from_year).
-- Trug ein Asset schon eine Fassung "gueltig ab 2026", war jede Korrektur fuer
-- die Jahre davor ausgeschlossen, etwa fuer eine Teilfreistellung (#468, #466).
-- Die Vorgabe je Asset-Typ kannte diese Sperre nie.
--
-- Die Kette bleibt lueckenlos und append-only: eine Fassung folgt genau auf die
-- aktuelle, nichts wird ueberschrieben oder geloescht. Fuer ein Steuerjahr gilt
-- die juengste Fassung, deren "gueltig ab" nicht nach dem Jahr liegt. Fuer jede
-- bestehende Kette ist das dasselbe Ergebnis wie bisher, denn dort faellt
-- "gueltig ab" nie.
PRAGMA foreign_keys=ON;
BEGIN IMMEDIATE;
DROP TRIGGER tax_ui_classification_chain;
CREATE TRIGGER tax_ui_classification_chain BEFORE INSERT ON asset_tax_classification_revision BEGIN
 SELECT CASE WHEN NEW.revision_no=1 AND (NEW.supersedes_classification_revision_id IS NOT NULL OR EXISTS(SELECT 1 FROM asset_tax_classification_revision WHERE classification_id=NEW.classification_id)) THEN RAISE(ABORT,'tax_ui_classification_initial_invalid') END;
 SELECT CASE WHEN NEW.revision_no>1 AND NOT EXISTS(SELECT 1 FROM current_asset_tax_classification_revision old WHERE old.classification_revision_id=NEW.supersedes_classification_revision_id AND old.classification_id=NEW.classification_id AND old.revision_no+1=NEW.revision_no) THEN RAISE(ABORT,'tax_ui_classification_chain_invalid') END;
END;
PRAGMA user_version=2204;
COMMIT;
