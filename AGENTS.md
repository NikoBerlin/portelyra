# Portelyra – Hinweise für Mitwirkende und Coding-Agents

Dieses Repository enthält genau den Programmstand eines Release: den Quelltext nach der AGPL, so wie er im signierten Archiv liegt.
Entwickelt und getestet wird in einem eigenen, nicht öffentlichen Repository; Tests und Entwicklungswerkzeuge gehören nicht hierher.
Diese Datei gilt für alle, die am Code arbeiten, auch für Coding-Agents, und ergänzt deren allgemeine Arbeitsregeln.

## Daten

- In dieses Repository gehören keine privaten Daten: keine echten Belege, Kontonummern, Beträge, Namen, Datenräume, Logs, Secrets und
  keine Sitzungs- oder Transkriptdateien von Coding-Agents.
- Eigene Tests und Testbelege nur mit erfundenen Daten. Ein Testbeleg darf den Aufbau eines echten Belegs übernehmen; jede Zahl, Uhrzeit,
  Kennung und jeder Name ist erfunden.
- Importer und Leser verändern ihre Quelldateien nicht. Sie schreiben nur in die vorgesehene Datenhaltung und melden Fehler, Auslassungen
  und nicht eindeutig zuordenbare Datensätze nachvollziehbar.
- Fehlende Evidenz wird als „nicht verfügbar“ gezeigt, nie als 0.

## Architektur und Integrationen

- Vermeide konkurrierende Schreibzugriffe auf kanonische Daten. Desktop- und Serverbetrieb müssen den jeweils vorgesehenen Nutzer-, Runtime- und Datenkontext korrekt berücksichtigen.
- Providerintegrationen sind zulässig und werden nach fachlicher Eignung und vorhandener Konfiguration ausgewählt. FMP, Twelve Data und andere Provider sind nicht pauschal ausgeschlossen. Das kanonische Schema sperrt `fmp` und erlaubt `twelve_data` nur als abgeschalteten Expertenentwurf; die Sperre hebt eine eigene Migration auf, wenn ein Kursanbieter-Plugin dafür kommt.
- Halte Providerzugriffe soweit sinnvoll austauschbar und konfigurierbar, ohne dafür unnötige Abstraktionsschichten einzuführen.
- Anzeige- und Analysefunktionen dürfen vorhandene Snapshots verwenden, Berechnungen anstoßen oder Providerdaten abrufen, wenn dies zur beauftragten Funktion gehört.
- Trenne externe Ausführung vom fachlichen Kern, soweit dies einen konkreten architektonischen Nutzen hat.

## Externe Auswirkungen

- Lokale Berechnungen, Dateiimporte und Testläufe brauchen keine Freigabe.
- Reale Trades, Schreibzugriffe auf externe Konten, kostenpflichtige Aktionen, versendete Benachrichtigungen und Änderungen an produktiven
  Systemen nur mit ausdrücklichem Auftrag.

## Umgebungen

- **Python:** 3.12, Systeminterpreter, keine virtuelle Umgebung und keine Lockdatei. Standardbibliothek plus `jsonschema`; Aufrufe aus R
  laufen isoliert mit `-B -E -s`.
- **R:** ab 4.3 (wie Ubuntu 24.04 per apt), kein renv. Benötigt `shiny`, `jsonlite`, `digest`, `RSQLite`/`DBI`. Die beiden Projektpakete
  `packages/spotcore` und `packages/spotdisplay` werden **nicht** aus der Quelle geladen, sondern in die Desktop-Runtime installiert.
- **Systemabhängigkeiten:** SQLite (über R und Python), ein Browser für die Apps, `openssl` für Zufallsreferenzen.
- **Mindeststand für Nutzer:** was Ubuntu 24.04 per apt liefert (R 4.3.3, Shiny 1.8.0, Python 3.12). Neueres R verdeckt Lücken – etwa
  `%||%` (erst R 4.4) oder `actionButton(disabled=)` (erst Shiny 1.9).

## Befehle

| Zweck | Kommando |
|---|---|
| Umgebung prüfen | `Rscript scripts/portelyra_desktop.R preflight` |
| Installieren und starten | siehe Handbuch [`docs/handbuch/installation.md`](docs/handbuch/installation.md) |
| Update einspielen | siehe Handbuch [`docs/handbuch/update.md`](docs/handbuch/update.md) |

Desktop-Kommandos brauchen `PORTELYRA_DESKTOP_HOME` (Vorgabe der Installation: `$HOME/.local/share/portelyra`). Beurteilt wird die
JSON-Statuszeile, nicht der Exit-Code.

## Struktur

- `apps/` — Shiny-Oberflächen: `data` (schreibt), `cockpit`, `tax`, `analysis` (lesen nur veröffentlichte Artefakte), `shared` (gemeinsame UI und Dienste), `reference`, `desktop_demo`.
- `packages/spotcore` — R-Kern: Runtime, Data Commands, Run Center. `packages/spotdisplay` — Leser der veröffentlichten Artefakte.
- `workers/reference/` — Python-Rechenkern (Abschluss, FIFO, Analysen, Publikation).
- `migrations/reference/` — Python-Fachmodule mit Speicherzugriff (Marktbewertung, Bewertungsstand, Steuer-UI, unrealisierte Bewertung).
- `contracts/` — Verträge: Schemata, Migrations-SQL, Fähigkeits- und Fehlercode-Tabellen, `source-fingerprints.csv` je Vertrag.
- `plugins/` — Leser für Belege, Kursanbieter und Steuermodule (im Sandkasten ausgeführt).
- `scripts/` — CLI-Grenzen (JSON über stdin/stdout) und die Desktop-CLI.

## Pfade mit besonderer Behandlung

- **Prüfsummen:** `contracts/**/source-fingerprints.csv` und `golden-fingerprints.csv` müssen zu den Dateien passen; die Programmliste
  `contracts/desktop-product/v1/source-fingerprints.csv` bestimmt, was ein Release enthält. Migrations-SQL unter `contracts/**/migrate-*.sql`
  ist einmal geschrieben und bleibt; `plugins/tax_models/tax_de_personal_income_tax_projection_v1/` ist als Vergleichsmodell byteweise
  festgeschrieben.
- **Neue Ordner im Datenraum festschreiben:** Wer im Datenraum einen Ordner anlegt und ihn danach sichtbar macht (umbenennen, Zeiger wie
  `active.json`, `latest.json` oder `installed.json` umsetzen), ruft vorher `settle_new_directory_v1` auf (`workers/reference/durable_storage_v1.py`;
  in R `.canonical_settle_new_directory`). Mit Passwortschutz schreibt gocryptfs die `gocryptfs.diriv` neuer Ordner sonst nicht fest; nach
  einem harten Ausschalten wäre der Ordner unlesbar und jedes Backup blockiert.
- **Konfiguration und Secrets:** keine `.env` im Projekt. Provider-Einstellungen, Verweise auf Zugänge und Laufzeitzustand liegen im
  Datenraum, nicht im Repository. API-Schlüssel und Passwörter liegen nur im Schlüsselbund des Systems, nie in Datenraum, Backup, Logs
  oder Artefakten; Plugins haben kein Netz, der Kern ruft für sie ab.

### Was beim Ändern erfahrungsgemäß mitzuziehen ist

- Eine Änderung an einer Programmdatei macht ihre Zeile in `contracts/desktop-product/v1/source-fingerprints.csv` und in den Prüfsummen
  des betroffenen Vertrags veraltet.
- Ein geändertes JSON-Schema kann per SHA in `apps/desktop_demo/read_latest_artifact_v1.py` gepinnt sein; dessen SHA wiederum in
  `packages/spotdisplay/R/display_reader.R` und zwei Registries.
- Eine Änderung an `migrations/reference/market_valuation_projection_v1.py` ändert den Algorithmus-Fingerabdruck; der Bewertungsstand wird
  beim nächsten Lauf vollständig neu gerechnet.
- Eine Änderung an einem `plugins/tax_models/*/plugin.R` ändert `rules_fingerprint`; `manifest.json` nachziehen, und die gespeicherte
  Modulauswahl muss in der Oberfläche neu bestätigt werden.
- Ein geänderter Leser braucht neue Prüfsummen im Manifest und eine neue Version; Nutzer bestätigen ihn danach einmal neu an ihren Belegen.
- Schemaversionen stehen doppelt: als `PRAGMA user_version` **und** als `CHECK`-Bedingung in der Bindungstabelle.

## Weitere Dokumentation

Handbuch unter `docs/handbuch/`, Verträge unter `contracts/`. Bei Widersprüchen zum Code gilt der Code; melden Sie die Abweichung, statt sie
stillschweigend aufzulösen.
