# Update einspielen

Ein Update spielen Sie aus der App ein oder mit einem Befehl im Terminal. Beide Wege prüfen das Archiv gegen die Signatur und legen vorher
ein Backup an. Die erste Installation beschreibt [Installation](installation.md). Ein Update kommt als Archiv `portelyra-<version>.tar.gz`.

## Neue Version finden

Ob es eine neuere Version gibt, zeigt Portelyra selbst: In Daten → Einstellungen → „Programm“ fragt **„Nach Updates suchen“** einmal bei
GitHub nach und zeigt die Versionshinweise. Mit Ihrer Zustimmung (Einrichtungsdialog oder dieselbe Karte) sucht Portelyra einmal am Tag
von selbst; eine neuere Version steht dann links in jeder App. GitHub erfährt dabei Ihre IP-Adresse und den Zeitpunkt, nichts aus Ihrem
Bestand. Ohne Zustimmung erfahren Sie von neuen Versionen auch über GitHub: auf der Seite des Projekts „Watch“ → „Custom“ → „Releases“.

Steht bei GitHub eine neuere Version, die Portelyra nicht einspielen kann, weil ihr Archiv fehlt oder anders heißt, meldet die Suche nicht
„aktuell“: Links steht „Version … nicht einspielbar“, und die Karte nennt unter „Nicht angeboten“ jede solche Version mit Grund. Suchen
Sie dann später noch einmal; bleibt der Hinweis, aktualisieren Sie im Terminal (unten).

## Aus der App

1. Daten → Einstellungen → „Programm“ → Karte **„Updates“** (oder links „Version … verfügbar“ → „Ansehen“).
2. **„Herunterladen und prüfen“** lädt das Archiv von GitHub und prüft Größe, Prüfsumme und Signatur gegen die installierte
   Vertrauensliste, wie der erste Schritt des Befehls unten. Eingespielt wird noch nichts.
3. Kästchen setzen, **„Update jetzt einspielen“**: Portelyra beendet sich, und eine eigene Seite zeigt die Schritte (dieselben wie unten).
   Danach öffnet sich das neue Portelyra. Scheitert ein Schritt, nennt die Seite den Grund und den Rückweg; das Protokoll steht unter
   `~/.local/state/portelyra/update-<version>.log`.

## Im Terminal

```
Rscript ~/.local/share/portelyra/library/.portelyra-source/scripts/portelyra_desktop.R update --archive <archiv> --confirm UPGRADE_LOCAL_RUNTIME
```

Der Befehl muss aus dem **installierten** Portelyra kommen (Pfad oben), nicht aus dem entpackten Archiv. So prüft das vertraute,
installierte Portelyra das neue Archiv, bevor daraus etwas läuft ([Signaturschlüssel](signaturschluessel.md)). Läuft Portelyra
gerade, muss es nicht vorher beendet werden.

## Was der Befehl tut

Je Schritt schreibt er eine Zeile (`update_step`):

1. **`check`:** Archiv und Signatur prüfen. Ist genau dieser Stand schon installiert, endet er mit `already_current` und tut nichts.
   Ein älterer Stand wird nicht eingespielt.
2. **`stop`:** Ein laufendes Portelyra ruhig beenden. Läuft gerade „Alles aktualisieren“ oder arbeitet eine App (etwa eine Buchung
   oder ein Import), bricht er ab, ohne etwas zu beenden. Dann warten und den Befehl erneut starten.
3. **`unlock`:** Mit Passwortschutz entsperren. Mit „Mit der Anmeldung entsperren“ geschieht das ohne Eingabe, sonst öffnet sich die
   Seite „Portelyra entsperren“ im Browser. Das Passwort nie auf die Befehlszeile schreiben.
4. **`backup`:** Ein Backup im Backup-Ordner von Portelyra anlegen (mit Passwortschutz im verschlüsselten) und vollständig prüfen.
   Es heißt `vor-<neue Version>-<Datum>-<Uhrzeit>` und trägt die Version, die bisher lief. Ohne gültiges Backup kein Update.
5. **`upgrade`:** Den neuen Stand einspielen. Der bisherige bleibt für den Rückweg erhalten.
6. **`preflight`:** Der neue Stand prüft sich selbst.
7. **`prune`:** Die drei jüngsten gültigen Backups dieses Datenraums bleiben, ältere entfallen ([Backups](backups.md)).
8. **`start`:** Portelyra mit dem neuen Stand starten. Die Ausgabe des Starts steht in `~/.local/state/portelyra/start-<version>.log`.

Die letzte Zeile lautet `{"status":"updated", …}` mit neuer und bisheriger Version, Name des Backups und Zahl der entfernten Backups.

**Optionen:** `--browser firefox` öffnet Portelyra für dieses Update in Firefox; ohne die Option gilt der Browser aus Daten →
Einstellungen → „Programm“. `--no-browser` öffnet keinen Browser (mit Passwortschutz dann nur über den Schlüsselbund). `--port` wählt den
Port der Data-App wie bei `start`.

Nach dem Update zeigt Daten einmal oben „Neu in Version …“. Die Liste steht danach unter Einstellungen → „Programm“.

## Wenn etwas nicht klappt

Die letzte Zeile heißt dann `{"status":"blocked", "code": …, "step": …}` und nennt den Schritt.

| Meldung | Bedeutung |
|---|---|
| `desktop_release_signature_missing`, `…_untrusted`, `…_invalid` | Das Archiv ist nicht vertrauenswürdig. Nicht einspielen ([Signaturschlüssel](signaturschluessel.md)). |
| `desktop_release_update_entry_untrusted` | Der Befehl kam nicht aus dem installierten Portelyra (Pfad oben). |
| `desktop_product_upgrade_unavailable` | Das Archiv ist nicht neuer als der installierte Stand. |
| `desktop_product_refresh_running` | „Alles aktualisieren“ läuft gerade. Nach dem Lauf erneut starten. |
| `desktop_product_update_busy` | Eine App arbeitet gerade, etwa an einer Buchung. Abwarten und erneut starten. |
| `desktop_product_update_stop_failed` | Portelyra hat sich nicht innerhalb von zwei Minuten beendet. Nichts wurde eingespielt. |
| `desktop_product_locked` | Nicht entsperrt (Seite geschlossen oder Schlüsselbund nicht verfügbar). |
| `desktop_release_source_unreadable` | Ein Eintrag im Datenraum ist unlesbar, das Backup scheitert ([Backups](backups.md), „Unlesbarer Eintrag“). |
| `desktop_product_update_preflight_failed` | Der neue Stand startet nicht. Die Zeile nennt den Rückweg `rollback`. |

**Vor dem Einspielen gescheitert** (Schritte `stop` bis `backup`): Am installierten Stand hat sich nichts geändert. War Portelyra
gestartet, startet es wieder mit dem bisherigen Stand (`"restarted":"started"`).

**Nach dem Einspielen gescheitert** (`preflight`): Zurück zum bisherigen Stand mit

```
Rscript ~/.local/share/portelyra/library/.portelyra-source/scripts/portelyra_desktop.R rollback --confirm ROLLBACK_LOCAL_RUNTIME
```

Das Backup aus Schritt 4 bleibt in jedem Fall liegen.
