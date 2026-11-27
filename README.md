# Portelyra

*English summary: [In English](#in-english).*

Portelyra führt ein privates Wertpapier-, Krypto- und Kontodepot lokal auf dem eigenen Rechner: Buchungen aus Belegen, Kurse, Bestand
und Rendite, deutsche Steuerberechnung mit Steuerreport. Vier getrennte Oberflächen laufen im Browser: **Daten** (die einzige, die
schreibt), **Cockpit**, **Steuer** und **Analyse**.

**Erste öffentliche Beta 0.3.5:** Linux (Ubuntu 24.04), deutsche Oberfläche, ein Portfolio in Euro, deutsches Steuerrecht.

> **Beta, ohne Gewähr.** Portelyra ist keine Anlage- und keine Steuerberatung. Berechnungen ersetzen weder Steuerberater noch die
> Abrechnungen der Institute; im Zweifel gilt der Beleg.

## In English

Portelyra keeps a private securities, crypto and bank-account portfolio locally on your own computer: bookings from broker and bank
statements, prices, holdings and returns, and German tax calculations with a tax report. It runs on Linux (Ubuntu 24.04) as four local
web apps in your browser. **For now, the user interface, the handbook and the tax rules are German only**; Portelyra is aimed at private
investors taxed in Germany. There is no account, no server and no telemetry; prices are fetched from a provider such as Yahoo Finance
only when you choose to. Before installing, compare the archive checksum with the release notes and with the independent DNS record
(`dig +short TXT _release.portelyra.com`). This is a beta without warranty and not tax or investment advice. Portelyra is free software under the
AGPL-3.0-or-later. Bug reports and security reports (see [`SECURITY.md`](SECURITY.md)) are welcome in English, too – please never attach
your own statements or account data.

## Datenschutz

- **Keine Telemetrie, kein Konto, kein Server.** Alle Daten liegen in einem Datenraum auf dem eigenen Rechner, auf Wunsch verschlüsselt.
- **Netzzugriff nur auf Wunsch:** Kurse und Devisen holt Portelyra erst, wenn Sie es auslösen oder einen Zeitlauf freigeben.
- **Bei der Suche nach Updates** fragt Portelyra die Liste der Versionen bei GitHub ab (`api.github.com`): mit Ihrer Zustimmung höchstens
  einmal am Tag, sonst nur, wenn Sie auf „Nach Updates suchen“ klicken. GitHub erfährt dabei Ihre IP-Adresse und den Zeitpunkt, nichts aus
  Ihrem Bestand und keine Kennung. Die Zustimmung erfragt der Einrichtungsdialog ohne Vorauswahl; ändern lässt sie sich in Daten →
  Einstellungen → „Programm“.
- **Beim Kursabruf und bei der Suche nach einer Kursquelle** erfährt der Anbieter (etwa Yahoo Finance), welche Wertpapiere und Währungen
  abgefragt werden – also ungefähr, was Sie halten – und Ihre IP-Adresse; Mengen, Beträge und Konten erfährt er nicht. Mit eigenem Zugang
  (etwa EODHD) kann er die Abrufe Ihrem Konto zuordnen.
- **Belege werden nur gelesen.** Leser-Plugins laufen abgeschottet und verändern ihre Quelldateien nicht.
- Fehlende Angaben zeigt Portelyra als „nicht verfügbar“, nie stillschweigend als 0.

## Schnellstart

1. **Installieren:** einmal im Terminal, rund eine Viertelstunde – [`docs/handbuch/installation.md`](docs/handbuch/installation.md).
   Prüfen Sie vorher die Prüfsumme des Archivs und den Fingerabdruck des Signaturschlüssels: in den Versionshinweisen des Releases und,
   unabhängig von GitHub, im DNS mit `dig +short TXT _release.portelyra.com`.
2. **Ausprobieren:** Beim ersten Start bietet der Einrichtungsdialog ein Demo-Portfolio an, mit oder ohne aktuelle Kurse. Es liegt
   getrennt von Ihren eigenen Daten.
3. **Erste Schritte:** ein Durchgang am Demo vom Einrichten bis zum Backup –
   [`docs/handbuch/erste-schritte.md`](docs/handbuch/erste-schritte.md). Dasselbe Handbuch öffnet in jeder App der Knopf **Hilfe**,
   offline.
4. **Updates:** aus der App (Daten → Einstellungen → „Programm“) oder mit einem Befehl im Terminal –
   [`docs/handbuch/update.md`](docs/handbuch/update.md).

Das ganze Handbuch liegt unter [`docs/handbuch/`](docs/handbuch/).

## Systemvoraussetzungen

- Linux als Einzelplatz; die Apps laufen lokal im Browser.
- **Import von Belegen:** Leser laufen nur abgeschottet (Landlock und seccomp). Das braucht Linux ab **Kernel 6.2**: Ubuntu 24.04
  und Debian 13 reichen, Debian 12 und Ubuntu 22.04 nicht. Fehlt die Abschottung, gibt es keinen Import; ungeschützt läuft kein
  Leser. Unter macOS und Windows ist der Import vorerst nicht verfügbar.
- PDF-Belege brauchen `pdftotext` (Paket poppler-utils).
- Schnittstelle und Mindestanforderungen der Leser-Plugins: [`contracts/statement-reader-plugin/v1/README.md`](contracts/statement-reader-plugin/v1/README.md).

## Rückmeldungen

- **Fehler und Wünsche** als Issue. Bitte **keine privaten Daten anhängen**: keine Belege, Auszüge, Kontonummern, Beträge aus dem eigenen
  Depot, Datenräume oder Protokolle mit solchen Angaben. Ein nachgestelltes Beispiel mit erfundenen Zahlen reicht fast immer.
- **Sicherheitslücken** bitte nicht öffentlich, sondern privat melden: [`SECURITY.md`](SECURITY.md).
- **Beiträge:** Pull Requests nimmt das Projekt vorerst nicht an; mehr in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Entwicklung

Dieses Repository enthält je Release genau den Programmstand, der auch im signierten Archiv liegt – den Quelltext nach der AGPL.
Entwickelt und getestet wird in einem eigenen, nicht öffentlichen Repository; Tests und Entwicklungswerkzeuge gehören nicht hierher.
Interne Kennungen und Paketnamen tragen noch den Arbeitsnamen **Portfolio Ledger Suite**; der Name des Programms ist Portelyra.
Hinweise für Mitwirkende und Coding-Agents stehen in [`AGENTS.md`](AGENTS.md). Aus RStudio startet
`source("start_portelyra.R"); portelyra_start()` das installierte Programm.

## Verzeichnisse

- `apps/` – die vier Oberflächen und ihre gemeinsame Hülle
- `packages/` – gemeinsam genutzte R-Pakete (`spotcore`, `spotdisplay`)
- `workers/`, `migrations/` – Rechenkern, Fachmodule mit Speicherzugriff, Import
- `plugins/` – Leser für Belege, Kursanbieter, Steuermodule
- `contracts/` – versionierte Daten- und Artefaktverträge mit Prüfsummen
- `docs/` – das Handbuch (`docs/handbuch/`)

## Lizenz

Portelyra ist freie Software unter der GNU Affero General Public License, Version 3 oder nach Wahl jeder späteren Version (SPDX: `AGPL-3.0-or-later`). Der vollständige Lizenztext steht in [`LICENSE`](LICENSE). Wer eine geänderte Fassung über ein Netzwerk zur Nutzung anbietet, muss deren Nutzern den Quelltext dieser Fassung zugänglich machen (Abschnitt 13).

Der Name „Portelyra“ und die Bildmarke sind nicht Teil der Lizenz; Rechte daran räumt die AGPL nicht ein (Abschnitt 7 Buchstabe e).

Eingebundene Abhängigkeiten behalten ihre eigenen Lizenzen. Alle sind mit der AGPL vereinbar:
- die R-Pakete stehen unter MIT, BSD, LGPL-2.1-or-later oder unter GPL-Fassungen, die GPL-3.0 zulassen, ebenso R selbst;
- die Python-Module jsonschema (MIT) und PyGObject (LGPL-2.1-or-later), Letzteres nur in den GTK-Prüfwerkzeugen.

poppler (`pdftotext`) wird als eigenständiges Programm aufgerufen und nicht eingebunden. Kursdaten der Anbieter unterliegen deren Nutzungsbedingungen.
