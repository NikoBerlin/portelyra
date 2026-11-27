-- Ein gescheiterter Schreibvorgang gibt seine Bestaetigung wieder frei.
--
-- tax_ui_command_attempt trug UNIQUE(confirmation_id): eine Bestaetigung, ein
-- Versuch - gleichgueltig, ob er gelang. Scheiterte er, war derselbe Befehl
-- dauerhaft blockiert, denn die Vorschau-Referenz wird aus der Nutzlast
-- abgeleitet und ihre Bestaetigung damit ebenfalls. Das traf
-- die Wiederauswahl des Steuermoduls: Der Schreibvorgang scheiterte an der
-- Fassungskette, und danach ging derselbe Befehl gar nicht mehr
-- (#368).
--
-- Die Einmaligkeit bleibt, sie wird nur genauer gefasst: Ein neuer Versuch ist
-- erlaubt, solange jeder fruehere Versuch dieser Bestaetigung fehlgeschlagen
-- ist. Ein laufender Versuch ohne Ergebnis sperrt weiter - sonst liefen zwei
-- Schreibvorgaenge gegen dieselbe Bestaetigung. Ein gelungener sperrt ebenso:
-- Eine Bestaetigung wird genau einmal eingeloest.
--
-- Die Tabelle wird nach dem in der SQLite-Dokumentation vorgesehenen Verfahren
-- neu erstellt und ihr Inhalt uebernommen. Die Loeschsperre wird dafuer kurz
-- abgelegt und danach wieder gesetzt - sonst verboete sie ihre eigene
-- Ersetzung. Fremdschluessel bleiben dabei aus, damit die auf request_ref
-- verweisenden Tabellen den Umbau ueberstehen.
PRAGMA foreign_keys=OFF;
BEGIN IMMEDIATE;
DROP TRIGGER tax_ui_attempt_no_update;
DROP TRIGGER tax_ui_attempt_no_delete;
CREATE TABLE tax_ui_command_attempt_v2203(
 attempt_id TEXT PRIMARY KEY CHECK(attempt_id LIKE 'tua_%'),
 attempt_ref TEXT NOT NULL UNIQUE CHECK(attempt_ref LIKE 'tat_%'),
 confirmation_id TEXT NOT NULL REFERENCES tax_ui_command_confirmation(confirmation_id),
 request_ref TEXT NOT NULL UNIQUE CHECK(request_ref LIKE 'req_%'),
 attempted_at_utc TEXT NOT NULL CHECK(length(attempted_at_utc)=20)
) STRICT;
INSERT INTO tax_ui_command_attempt_v2203 SELECT * FROM tax_ui_command_attempt;
DROP TABLE tax_ui_command_attempt;
ALTER TABLE tax_ui_command_attempt_v2203 RENAME TO tax_ui_command_attempt;
CREATE TRIGGER tax_ui_attempt_no_update BEFORE UPDATE ON tax_ui_command_attempt BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_attempt_no_delete BEFORE DELETE ON tax_ui_command_attempt BEGIN SELECT RAISE(ABORT,'tax_ui_immutable'); END;
CREATE TRIGGER tax_ui_attempt_single_open BEFORE INSERT ON tax_ui_command_attempt BEGIN
 SELECT CASE WHEN EXISTS(
  SELECT 1 FROM tax_ui_command_attempt earlier
  LEFT JOIN tax_ui_command_result result ON result.attempt_id=earlier.attempt_id
  WHERE earlier.confirmation_id=NEW.confirmation_id
    AND (result.status IS NULL OR result.status='completed')
 ) THEN RAISE(ABORT,'tax_ui_confirmation_consumed') END;
END;
PRAGMA user_version=2203;
COMMIT;
PRAGMA foreign_keys=ON;
