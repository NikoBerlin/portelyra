# Passwortschutz

Auf Wunsch verschlüsselt Portelyra den ganzen Datenbestand – alle Portfolios, Buchungen, Kurse und
Einstellungen – und die Backups mit einem Passwort. Ohne Passwort ist nichts lesbar, auch nicht in Kopien auf einer Sicherungsplatte.

**Voraussetzung:** Linux mit dem Paket `gocryptfs` (etwa `sudo apt install gocryptfs`). Unter macOS und Windows schützt vorerst die
Festplattenverschlüsselung des Systems (FileVault bzw. BitLocker).

## Einrichten

1. Daten → Einstellungen → „Sicherheit und Speicher“ → „Passwortschutz“ (oder in der geführten Einrichtung der Schritt „Passwortschutz“).
2. Passwort zweimal eingeben (mindestens 10 Zeichen), den Hinweis bestätigen, „Passwortschutz einrichten“. Das dauert je nach Größe
   des Bestands einige Minuten; in dieser Zeit nichts anderes bearbeiten.
3. Portelyra zeigt **einmal** den Wiederherstellungsschlüssel. Aufschreiben und sicher verwahren:
   - Er setzt ein neues Passwort, falls Sie es vergessen.
   - Er öffnet alle Daten und Backups ohne Passwort, auch Kopien, und bleibt nach einer Passwortänderung gültig.
   - Portelyra speichert ihn nicht. Sind Passwort und Schlüssel beide verloren, sind die Daten verloren.
4. „Portelyra beenden“, dann neu starten. Die Startseite „Portelyra entsperren“ fragt nach dem Passwort. Beim ersten Start legt
   Portelyra ein Backup im verschlüsselten Ordner an.
5. Zurück in Daten → Einstellungen → „Sicherheit und Speicher“ → „Passwortschutz“ den bisherigen, unverschlüsselten Bestand entfernen. Portelyra prüft vorher, dass
   ein neues Backup da ist und seit dem Einrichten nichts mehr in den alten Bestand geschrieben wurde. Auf SSDs können Reste
   bleiben; die deckt die Festplattenverschlüsselung ab.

## Mit der Anmeldung entsperren

Beim Einrichten vorangekreuzt, später in der Karte „Passwortschutz“ ein- und ausschaltbar (Einschalten fragt nach dem Passwort). Das
Passwort liegt dann im Schlüsselbund Ihrer Anmeldung. Solange Sie am Rechner angemeldet sind:

- startet Portelyra ohne Startseite,
- laufen Zeitpläne auch bei beendetem Portelyra (sie entsperren bei Bedarf selbst),
- gehen Backup und Update ohne Eingabe (`portelyra_desktop.R unlock` entsperrt selbst).

Nach dem Ruhezustand gilt das erst wieder, wenn Sie das Passwort eingegeben oder sich neu angemeldet haben.

Ausgeschaltet oder abgemeldet bleibt alles verschlüsselt. **Wer sich am Rechner automatisch ohne Passwort anmeldet, hebt damit den
Schutz faktisch auf.** Fehlt der Eintrag oder passt er nach einer Änderung an anderer Stelle nicht mehr, fragt wieder die Startseite.

## Im Alltag

- **Start:** Passwort auf der Startseite eingeben; danach öffnet sich die App „Daten“ wie gewohnt. Nach drei falschen Eingaben wartet
  der nächste Versuch kurz.
- **Entsperrt bleibt entsperrt:** Was Sie entsperrt haben, bleibt offen, bis Sie sich abmelden, den Rechner herunterfahren oder er in den
  Ruhezustand geht, auch wenn Portelyra beendet ist. In dieser Zeit schützt ihn die Bildschirmsperre Ihres Rechners.
- **Ruhezustand:** Vorher sperrt Portelyra den Bestand. Beim Aufwachen fragt ein Dialog nach dem Passwort; angefangene Eingaben bleiben
  stehen. Bis dahin entsperrt auch der Schlüsselbund nicht, und ein fälliger Zeitplan fällt aus. Nach der Passworteingabe holt Portelyra ihn
  von selbst einmal nach, solange der Zeitplan an ist. Läuft beim Zuklappen gerade eine Buchung oder „Alles aktualisieren“, bricht Portelyra das nie ab: Der Bestand bleibt dann
  offen, und nach dem Aufwachen steht ein Hinweis am Bildschirmrand. Der Schlüsselbund selbst bleibt im Ruhezustand geöffnet; gegen jemanden,
  der an der Bildschirmsperre vorbeikommt, hilft nur, „Mit der Anmeldung entsperren“ auszuschalten.
- **Strenger:** In der Karte „Passwortschutz“ unter „Sperren“ gibt es „Beim Beenden von Portelyra sperren“ und „Jetzt sperren“ (Portelyra
  beendet sich dabei). Läuft dann noch „Alles aktualisieren“, sperrt Portelyra an dessen Ende.
- **Verbindung verloren:** Fehlt der Bestand aus einem anderen Grund bei laufender App, sagt Portelyra das sofort und bietet „Wieder
  verbinden“, notfalls mit dem Passwort. Bis dahin lässt sich nichts speichern. Lag danach etwas im leeren Ordner, nennt die Karte „Passwortschutz“, wie viele Dateien es waren; gelöscht wird
  nichts.
- **Zeitpläne** laufen ohne „Mit der Anmeldung entsperren“ nur, solange der Bestand entsperrt ist. Mit dieser Einstellung öffnet ein
  Zeitplan den gesperrten Bestand selbst und sperrt ihn nach seinem Lauf wieder, auch nach „Jetzt sperren“. Starten Sie Portelyra
  währenddessen, bleibt er offen. Fiel ein Lauf aus, steht das nach dem Entsperren in der Karte „Passwortschutz“; „Alles aktualisieren“
  holt das Fehlende nach.
- **Passwort vergessen:** Auf der Startseite „Passwort vergessen?“ öffnen, den Wiederherstellungsschlüssel und ein neues Passwort
  eingeben.
- **Passwort ändern:** Daten → Einstellungen → „Sicherheit und Speicher“ → „Passwortschutz“ → „Passwort ändern“. Das Passwort schützt nur die kleine
  Schlüsseldatei; die Daten bleiben mit demselben Hauptschlüssel verschlüsselt. Wer eine ältere Kopie des Ordners hat (etwa aus einer
  Sicherung) und das alte Passwort kennt, öffnet damit weiter, auch die heutigen Daten. Dasselbe gilt für einen bekannt gewordenen
  Wiederherstellungsschlüssel. Dagegen hilft „Schlüssel erneuern“.

## Schlüssel erneuern

Wurde Passwort oder Wiederherstellungsschlüssel bekannt: Daten → Einstellungen → „Sicherheit und Speicher“ → „Passwortschutz“ → „Schlüssel erneuern“.

1. Anstoßen; Portelyra beendet sich.
2. Beim nächsten Start fragt die Startseite nach bisherigem und neuem Passwort (es darf das bisherige sein). Portelyra verschlüsselt
   Datenbestand und Backups mit einem neuen Hauptschlüssel und prüft jede Datei. Das dauert je nach Größe einige Minuten; zeitweise
   braucht es doppelt so viel Platz, das prüft Portelyra vorher.
3. Den **neuen** Wiederherstellungsschlüssel aufschreiben; der alte gilt nicht mehr. Danach startet Portelyra und legt ein Backup in den
   neuen Ordnern an.
4. In der Karte die alten Ordner entfernen.

Ältere Kopien der alten Ordner, etwa in einer Sicherung, öffnen weiter mit dem alten Passwort oder Schlüssel, bis Sie sie dort löschen.
„Nur entsperren“ auf der Startseite bricht das Erneuern ab.

## Was geschützt ist und was nicht

| Geschützt | Nicht geschützt |
|---|---|
| Datenbestand aller Portfolios | Ihre Belegordner mit den Original-PDFs (Portelyra liest sie nur) |
| Backups | Programmbibliothek und Release-Archive |
| Einstellungen, Kurse, Ablage | – |

Eigene Kopien außerhalb des Backup-Ordners von Portelyra, etwa dauerhafte Sicherungen an anderer Stelle, fasst das Einrichten nicht
an; sie bleiben lesbar. Nach dem Einrichten von Hand löschen oder auf ein verschlüsseltes Medium verschieben.

Die entsperrte Ansicht liegt unter `/run/user/…` und damit nicht in Sicherungen wie Déjà Dup oder Back In Time; gesichert wird der
verschlüsselte Ordner. Gegen Schadsoftware im eigenen Benutzerkonto hilft kein Passwort, solange der Bestand entsperrt ist.

**Backups von Hand** (`portelyra_desktop.R backup --target …`) müssen mit Passwortschutz in den entsperrten Backup-Ordner
`/run/user/<uid>/portelyra-…/backups/…` gehen; ein anderes Ziel lehnt Portelyra ab, damit kein Backup unverschlüsselt entsteht.

## Update mit Passwortschutz

`update --archive` erledigt alles in einem Befehl: Portelyra beenden, entsperren (über den Schlüsselbund ohne Eingabe,
sonst auf der Seite „Portelyra entsperren“), Backup im verschlüsselten Ordner, Upgrade, Start. Siehe [Update einspielen](update.md).

## Backup von Hand mit Passwortschutz

Backup und Upgrade brauchen den entsperrten Bestand und laufen bei angehaltenem Portelyra. Ist er gesperrt, entsperrt Schritt 2 ihn;
mit „Mit der Anmeldung entsperren“ ohne Eingabe. Sonst:

1. Portelyra beenden.
2. `Rscript scripts/portelyra_desktop.R unlock --browser firefox` öffnet nur die Seite „Portelyra entsperren“, ohne die Apps zu
   starten. Das Passwort dort eingeben; der Befehl endet mit `{"status":"unlocked"}`. Das Passwort nie auf die Befehlszeile oder in
   andere Programme schreiben: Dort landet es unverschlüsselt in Verlauf und Protokollen.
3. `backup --target /run/user/<uid>/portelyra-…/backups/<name> --confirm CREATE_OWNER_BACKUP`, dann `backup-check`. Das Backup
   trägt immer die Version des installierten Portelyra, auch wenn der Befehl aus einem anderen Ordner kommt.
4. `start`: Da schon entsperrt ist, starten die Apps ohne Seite.

## Notfall: das Portelyra-Home ist verloren

**Am einfachsten:** Haben Sie das ganze Portelyra-Home gesichert (etwa mit Déjà Dup oder Back In Time), spielen Sie es zurück und
entsperren wie gewohnt. Nehmen Sie dazu auch den verschlüsselten Backup-Ordner `~/.local/state/portelyra/backups.crypt` in Ihre Sicherung auf; er ist
verschlüsselt und darf auf jedes Medium.

**Anderer Ordner als vorher?** Das geht: Der Restore bindet den Bestand selbst an seinen Ursprungsort (Ergebnis
`relocation`, siehe [Backup zurückspielen](wiederherstellen.md)). Er findet den Ursprung auch dann, wenn das alte Home
verloren ist: Der Bestand notiert ihn selbst, und die Notiz liegt im Backup. Zugänge für Plugins tragen Sie am neuen Ort neu ein.

**Nur der Backup-Ordner ist da** (Kopie von `backups.crypt`, dazu Passwort oder Wiederherstellungsschlüssel):

1. Portelyra neu installieren (Programmordner) und in einem Terminal in den Programmordner wechseln.
2. Den Backup-Ordner von Hand einhängen. gocryptfs fragt nach dem Passwort:
   ```
   mkdir -m 700 ~/portelyra-notfall
   gocryptfs ~/.local/state/portelyra/backups.crypt ~/portelyra-notfall
   ```
   Mit dem Wiederherstellungsschlüssel statt des Passworts: `gocryptfs -masterkey=stdin …` und den Schlüssel mit Bindestrichen eingeben.
   Den Schlüssel nie als Teil des Befehls schreiben; dort stünde er im Verlauf der Shell.
3. Ein Hilfs-Home mit der Kennung des Backups anlegen (`<backup>` ist der Ordnername, etwa `nach-verschluesselung-…`):
   ```
   mkdir -m 700 ~/portelyra-hilfe
   PORTELYRA_DESKTOP_HOME=~/portelyra-hilfe Rscript scripts/portelyra_desktop.R install --confirm INSTALL_LOCAL_RUNTIME
   install -m 600 ~/portelyra-notfall/<backup>/payload/desktop-runtime.json ~/portelyra-hilfe/
   ```
   Portelyra spielt ein Backup nur mit derselben Kennung zurück; das schützt vor dem Vermischen fremder Datenräume.
4. Prüfen und zurückspielen in ein leeres Ziel, etwa das Standard-Home `~/.local/share/portelyra` (oder den Ordner aus
   `PORTELYRA_DESKTOP_HOME`, oder einen ganz anderen Ordner):
   ```
   PORTELYRA_DESKTOP_HOME=~/portelyra-hilfe Rscript scripts/portelyra_desktop.R restore-preflight --bundle ~/portelyra-notfall/<backup> --target ~/.local/share/portelyra
   PORTELYRA_DESKTOP_HOME=~/portelyra-hilfe Rscript scripts/portelyra_desktop.R restore --bundle ~/portelyra-notfall/<backup> --target ~/.local/share/portelyra --confirm RESTORE_TO_EMPTY_DESKTOP
   ```
   Das Ziel muss leer sein oder fehlen und in einem Ordner liegen, in den nur Sie schreiben dürfen. Das Ergebnis nennt in
   `relocation`, ob der Bestand an seinen Ursprungsort gebunden ist; bei `unverified` siehe [Backup zurückspielen](wiederherstellen.md).
5. Aushängen und aufräumen: `fusermount -u ~/portelyra-notfall`, dann `~/portelyra-hilfe` löschen.
6. Im wiederhergestellten Home `install --confirm INSTALL_LOCAL_RUNTIME`, dann `start`. Es ist **unverschlüsselt**.
7. Den Schutz neu einrichten: vorher den alten Ordner umbenennen, etwa in `backups.crypt.alt`. Er öffnet weiter mit dem alten Passwort
   oder Schlüssel. Solange er unter dem alten Namen liegt, lehnt Portelyra das Einrichten mit diesem Hinweis ab.

Der ganze Weg wird vor jedem Release an einem erfundenen Bestand geprobt: Einhängen mit Passwort und mit Schlüssel, Prüfen und
Zurückspielen des Backups in einen anderen Ordner, Start des wiederhergestellten Homes und erneutes Einrichten.

