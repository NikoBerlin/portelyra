# Backups in der App

Dafür gibt es in Daten → Einstellungen unter **„Sicherheit und Speicher“** die Karte **„Backups“**. Eine Kommandozeile ist nicht nötig.

## Backup anlegen

1. Daten → Einstellungen → „Sicherheit und Speicher“ → „Backups“ öffnen.
2. „Verstanden: Während des Backups pausieren …“ ankreuzen und **„Backup anlegen“** klicken.
3. Ein Fenster zeigt den Schritt: Wartungssperre, sichern, prüfen. Es schließt sich von selbst, und die Karte zeigt das Ergebnis.

Portelyra läuft dabei weiter. Für die Dauer des Backups warten „Alles aktualisieren“, Zeitpläne und Sammelläufe. Läuft gerade einer, ist der Knopf gesperrt, und die Karte nennt den Lauf. Wird gerade etwas geschrieben, etwa eine Buchung, meldet die Karte das, und der Versuch lässt sich eine Minute später wiederholen.

**Ziel:**
- Mit Passwortschutz der verschlüsselte Backup-Ordner.
- Sonst `~/.local/state/portelyra/backups` (genauer: `$XDG_STATE_HOME/portelyra/backups`).
- Der Name des Backups ist `app-<Datum>-<Uhrzeit>`.

**Nicht im Backup:**
- der eigene Belegordner mit den Original-PDFs;
- die Programmbibliothek;
- die Zeitpläne (die Einrichtung fragt sie nach einem Wiederherstellen neu).

## Liste

Die Karte zeigt je Backup Name, Zeitpunkt, Programmstand, Größe, Dateien und ob es zu diesem Datenraum gehört. Ein Backup aus einem neueren Programmstand ist gekennzeichnet; es wird nicht wiederhergestellt. Die Liste liest nur die Kopfdaten. Vollständig geprüft wird jedes Backup nach dem Anlegen und vor dem Wiederherstellen.

## Ausdünnen

1. Unter „Ausdünnen“ wählen, wie viele der jüngsten gültigen Backups bleiben sollen (1–10, Vorgabe 3).
2. **„Plan anzeigen“** klicken. Portelyra prüft dafür jedes Backup vollständig; bei verschlüsselten Backups dauert das einige Minuten.
3. Der Plan nennt, welche Backups entfielen. Nur **„Diesen Plan ausführen“** entfernt sie, und zwar genau diese.

Backups anderer Datenräume, aus neueren Programmständen und beschädigte Backups fasst Portelyra nicht an.

## Unlesbarer Eintrag

Meldet die Karte „Ein Eintrag im Datenraum lässt sich nicht lesen“, nennt sie den Eintrag, etwa `artifacts/activity_status/runs/run_…`.
Solange er da ist, entsteht kein Backup. Das letzte geprüfte Backup bleibt gültig.

**Ursache:** Fast immer ein hartes Ausschalten des Rechners (Einfrieren, Stromausfall, langes Drücken der Ein-Taste), und nur mit
Passwortschutz. Ein gerade angelegter Ordner kann dann unlesbar bleiben, weil die Verschlüsselung seine Schlüsseldatei noch nicht
festgeschrieben hatte. Ein normales Herunterfahren schreibt alles fest. Portelyra schreibt neue Ordner fest, bevor es
sie verwendet: Buchungsstände, Ablage, Einstellungen, Plugins und veröffentlichte Läufe.

**Prüfung nach dem Entsperren:** Portelyra sieht nach jedem Entsperren nach, ob ein Ordner unlesbar ist. Die Karte
„Backups“ meldet dann „Unlesbarer Ordner im Datenraum“, auch bevor ein Backup scheitert.

**Was tun:**
1. In der Karte **„Prüfen“** klicken. Portelyra liest den Datenraum einmal ganz durch und nennt jeden unlesbaren Ordner.
2. **Lauf eines veröffentlichten Bereichs** (der Pfad beginnt mit `artifacts/` und enthält `/runs/run_`): Er enthält nur abgeleitete
   Anzeigedaten, „Alles aktualisieren“ schreibt ihn neu. Die Kenntnisnahme ankreuzen und **„Für den nächsten Start vormerken“** klicken.
   Zeigt der aktuelle Stand eines Bereichs auf diesen Lauf, bleibt der Bereich bis zur nächsten Veröffentlichung leer.
   **Unfertiger Zwischenstand einer Buchung** (`asset-activity-ledger-v1/generations/.staging-…`) oder einer Steuermodul-Installation
   (`tax-model-plugins-v1/<modul>/.kopie-…`): Er war nie gültig, der gültige Stand ist unverändert. Ebenso vormerken. Die Buchung, die
   beim Ausschalten lief, ist nicht gespeichert: in der Liste der Buchungen prüfen und gegebenenfalls wiederholen. Weiteres Buchen ist
   bis dahin möglich, nur das Backup wartet.
3. Portelyra beenden und wieder starten. Noch vor dem Entsperren verschiebt Portelyra genau die vorgemerkten Ordner verschlüsselt in eine
   Quarantäne im Portelyra-Ordner Ihres Benutzerkontos (`quarantaene-<Datum>`, mit Herkunftsnotiz). Gelöscht wird nichts. Danach gelingen
   Backups wieder; „Alles aktualisieren“ veröffentlicht die betroffenen Bereiche neu.

**Anderer Eintrag** (gültiger Buchungsstand, Ablage, Einstellungen): Portelyra verschiebt ihn nicht. Nichts selbst verschieben oder löschen,
sondern den genannten Pfad melden. Ein solcher Stand lässt sich nur aus einem Backup zurückholen.

## Backups außerhalb des Rechners aufbewahren

„Backup anlegen“ schreibt in den Backup-Ordner von Portelyra, also auf dieselbe Platte wie die Daten. Gegen einen Ausfall der Platte hilft
nur eine Kopie an anderer Stelle: den Ordner `~/.local/state/portelyra/backups` (mit Passwortschutz `backups.crypt`, er ist verschlüsselt und
darf auf jedes Medium) regelmäßig auf eine Sicherungsplatte kopieren oder in die eigene Datensicherung aufnehmen. Ein anderes Ziel direkt in
der Karte ist für später vorgesehen.

## Kommandozeile

Für Werkzeuge bleibt `Rscript scripts/portelyra_desktop.R backup-live --confirm CREATE_OWNER_BACKUP`. Das ist derselbe Ablauf wie der Knopf, bei laufendem Portelyra. Die bisherigen Befehle `backup`, `backup-check` und `backup-prune` gelten weiter, `backup` nur bei beendetem Portelyra.

## Wiederherstellen beim ersten Start

Liegen beim ersten Start Backups im Backup-Ordner von Portelyra, bietet die Einrichtung **„Aus einem vorhandenen Backup übernehmen“** an. Das ist der Weg für einen neuen Rechner oder ein verlorenes Home.

1. Liegen die Backups nicht im Backup-Ordner von Portelyra auf diesem Rechner (neuer Rechner, USB-Stick, Sicherungsplatte): unter „Backups
   in einem anderen Ordner“ den vollständigen Pfad nennen und „Ordner lesen“ klicken. Gemeint ist der Ordner, der die einzelnen Backups
   enthält, oder ein verschlüsselter Ordner `backups.crypt`; ein einzelnes Backup geht auch. Ein eingestecktes Medium liegt meist unter
   `/media/<Benutzername>/<Name des Mediums>`. Portelyra liest den Ordner nur. Er darf auf einem Medium ohne Rechteverwaltung liegen (FAT,
   exFAT, NTFS) oder von einem anderen Rechner stammen; die Dateien müssen für Sie lesbar sein. Die Rechte im neuen Datenbestand setzt
   Portelyra selbst.
1. Ist der Ordner verschlüsselt: Passwort oder Wiederherstellungsschlüssel eingeben und „Öffnen“. Geöffnet wird nur lesend.
2. Ein Backup wählen, bestätigen und **„Prüfen und übernehmen“** klicken. Portelyra prüft das Backup vollständig und spielt es zurück. Die Quelle bleibt unverändert.
3. Zeitplan und Passwortschutz festlegen. Kam das Backup aus dem verschlüsselten Ordner, ist der Schutz vorbelegt. Der alte Ordner heißt danach `backups.crypt.alt-…` und öffnet weiter mit dem alten Passwort.

Ein Backup aus einem neueren Programmstand wird nicht übernommen; vorher Portelyra aktualisieren. Zugänge für Plugins tragen Sie am neuen Ort neu ein.

**Backups auf Stick oder Sicherungsplatte:** Ein unverschlüsseltes Backup kann jeder lesen, der das Medium in die Hand bekommt. Mit eingerichtetem Passwortschutz liegen die Backups im verschlüsselten Ordner `~/.local/state/portelyra/backups.crypt`; kopieren Sie diesen Ordner als Ganzes auf das Medium. Er öffnet beim Wiederherstellen mit dem Passwort oder dem Wiederherstellungsschlüssel.

Andere Ordner und die Kommandozeile: siehe [Backup zurückspielen](wiederherstellen.md).
