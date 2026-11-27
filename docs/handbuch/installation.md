# Installation

Portelyra wird einmal im Terminal installiert; danach startet es aus dem Anwendungsmenü, und Updates
brauchen einen Befehl ([Update einspielen](update.md)).

## Voraussetzungen

| | Unterstützt | Bemerkung |
|---|---|---|
| Betriebssystem | **Ubuntu 24.04 LTS**, 64 Bit (x86_64) | Andere Linux-Systeme ohne Gewähr; macOS und Windows später |
| R | 4.3 (Ubuntu: 4.3.3) | technische Untergrenze 4.2 |
| Python | 3.12 (Ubuntu: 3.12.3) | technische Untergrenze 3.10 |
| Browser | Firefox oder der Standardbrowser | |
| Platz | rund 260 MB für die Pakete, rund 20 MB für Portelyra, dazu Ihre Daten und Backups | im Test-Container |

Geprüft im frischen Container `ubuntu:24.04` als gewöhnlicher Benutzer (17.11.2026): Pakete 43 s, `install` 34 s, `initialize` 11 s,
Starter, Einrichtungsseite nach 29 s, Beenden 2 s, Demo-Aufbau rund 5 Minuten.

## 1. Pakete installieren

Eine Zeile, alles aus Ubuntu, ohne Übersetzen und ohne Downloads von CRAN:

```
sudo apt install r-base-core r-cran-shiny r-cran-jsonlite r-cran-digest r-cran-openssl r-cran-rsqlite r-cran-dbi \
  python3 python3-jsonschema gocryptfs fuse3 libsecret-tools poppler-utils openssh-client
```

Wofür: R und seine Pakete für die Apps; Python und `jsonschema` für den Rechenkern; `gocryptfs` und `fuse3` für den Passwortschutz;
`libsecret-tools` für „Mit der Anmeldung entsperren“; `poppler-utils` (`pdftotext`) für PDF-Belege; `openssh-client` (`ssh-keygen`)
für die Prüfung der Signaturen.

## 2. Archiv prüfen und entpacken

Das Archiv heißt `portelyra-<version>.tar.gz`. Vor dem Entpacken die Prüfsumme mit **beiden** Quellen vergleichen: der Release-Seite
und dem DNS von portelyra.com, das nicht über GitHub verwaltet wird:

```
sha256sum portelyra-<version>.tar.gz
dig +short TXT _release.portelyra.com
```

Stimmt sie an einer Stelle nicht überein, das Archiv nicht verwenden. Das ist bei der ersten Installation die entscheidende Prüfung:
Sie prüft noch keine Signatur, weil auf dem Rechner noch keine Vertrauensliste liegt. Ab dann prüft jedes Update gegen die Schlüssel
der installierten Fassung ([Signaturschlüssel](signaturschluessel.md)).

```
tar xzf portelyra-<version>.tar.gz
```

Das Archiv bringt die Schlüssel mit, gegen die künftige Updates geprüft werden. Ihre Fingerabdrücke zeigt:

```
grep -o 'ssh-ed25519 [A-Za-z0-9+/=]\{40,\}' portelyra-<version>/contracts/plugin-signing/v1/allowed_signers | ssh-keygen -lf -
```

Die Ausgabe muss genau diese zwei nennen – den Hauptschlüssel und den Ersatzschlüssel für einen späteren Wechsel:

- `SHA256:F62dAUshZG2xt7+inrWBYF60+9a1jnxkGfbfB8loYXc`
- `SHA256:zOdcl9W34y1OpMXCm4IUjTt5IDL09ijztcT1x+zJcn0`

Dieselben stehen in den Versionshinweisen jedes Release und im DNS (`dig` wie oben). Weicht einer ab, das Archiv nicht installieren.

## 3. Installieren und einrichten

```
Rscript portelyra-<version>/scripts/portelyra_desktop.R install --confirm INSTALL_LOCAL_RUNTIME
```

Das legt die Programmbibliothek unter `~/.local/share/portelyra` an. Der entpackte Ordner wird danach nicht mehr gebraucht. Alle
weiteren Befehle kommen aus dem installierten Portelyra; zur Abkürzung:

```
P=~/.local/share/portelyra/library/.portelyra-source/scripts/portelyra_desktop.R
Rscript $P initialize --label "Mein Portfolio" --confirm INITIALIZE_LOCAL_DESKTOP
Rscript $P desktop-entry --confirm CREATE_DESKTOP_ENTRY
```

`desktop-entry` legt **Portelyra** mit seiner Bildmarke im Anwendungsmenü an, mit der Zusatzaktion „Portelyra beenden“ (Rechtsklick
auf das Symbol).
Portelyra öffnet sich im Standardbrowser des Systems. Einen anderen Browser wählen Sie später in Daten unter Einstellungen →
„Programm“, oder gleich hier mit `--browser firefox` (ebenso `chromium`, `google-chrome`, `brave`, `microsoft-edge`, `vivaldi`, `opera`,
`librewolf`, `epiphany`). Geprüft wird Portelyra mit Firefox.

## 4. Starten

Aus dem Anwendungsmenü, oder im Terminal mit `Rscript $P start`. Beim ersten Start führt der Einrichtungsdialog weiter: Portfolio,
Kurse, Steuer, Passwortschutz, Suche nach Updates, Backup ([Backups](backups.md), [Passwortschutz](passwortschutz.md), [Update](update.md)). Zum Ausprobieren gibt es das
Demo-Portfolio ([Demo](demo.md)).

Portelyra öffnet sich nur mit dem Zugang, den der Starter beim Öffnen in die Adresse schreibt (`?launch_token=…`); er gilt bis zum
nächsten Öffnen. Mit `Rscript $P start --no-browser` öffnet sich kein Browser – das Terminal nennt dann die Adresse samt Zugang zum
Einfügen. Eine Adresse ohne Zugang, etwa aus einem Lesezeichen, zeigt nur einen Hinweis.

**Starten, auch wenn Portelyra schon läuft**: Ein Klick auf den Starter führt immer zu Portelyra.

| Zustand | Was ein Klick tut |
|---|---|
| Läuft (etwa Tab versehentlich geschlossen) | Öffnet Portelyra im Browser wieder, ohne Neustart und ohne erneutes Entsperren. Ungespeicherte Eingaben im geschlossenen Tab sind verloren, Gebuchtes nicht. |
| Wartet auf das Passwort oder im Einrichtungsdialog | Öffnet diese Seite wieder; der Entwurf des Dialogs bleibt erhalten. |
| Startet gerade | Öffnet Portelyra, sobald es bereit ist. |
| Wird gerade beendet | Wartet, bis es beendet ist, und startet es dann neu. |
| Läuft nicht | Startet Portelyra; mit Passwortschutz entsperrt der Schlüsselbund ohne Eingabe. |

Der Starter meldet jeden Schritt als Hinweis am Bildschirmrand („Portelyra startet …“, „Portelyra läuft bereits“, Fehler mit Grund).
Jedes Öffnen bekommt einen neuen Zugang, den nur das laufende Portelyra kennt; der vorige verfällt. Im geöffneten Tab gehen Neuladen und
der Wechsel zwischen den Apps weiter. Ein älterer Tab oder ein Link aus dem Browser-Verlauf zeigt danach „Zugang abgelaufen“ – dann über
den Starter öffnen.

**Beenden:** links in jeder App „Portelyra beenden“ (mit Rückfrage), „Portelyra beenden“ im Anwendungsmenü oder `Rscript $P stop`. Alle
vier Apps schließen; die Zeitpläne laufen weiter. Mit Passwortschutz bleibt der Bestand entsperrt, bis Sie sich abmelden, den Rechner
herunterfahren oder er in den Ruhezustand geht ([Passwortschutz](passwortschutz.md)). Arbeitet eine App gerade (etwa an einer
Buchung oder einem Import), beendet Portelyra sich nicht, sondern sagt es (`desktop_product_update_busy`); dann kurz warten und erneut
beenden. Vor dem Zuklappen des Rechners eine laufende Buchung oder einen Import bitte erst fertig werden lassen.

## Wenn etwas fehlt

`Rscript $P preflight` prüft alles und meldet etwa `desktop_product_dependency_missing`, wenn ein Paket aus Schritt 1 fehlt.
