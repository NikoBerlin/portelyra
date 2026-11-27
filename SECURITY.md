# Sicherheit

## Eine Sicherheitslücke melden

Bitte **nicht** als öffentliches Issue. Melden Sie sie privat über GitHub: im Repository unter **Security → Report a vulnerability**
(„Private vulnerability reporting“). Die Meldung sieht nur der Betreuer des Projekts.

Hilfreich sind:

- betroffene Version (`VERSION` oder die Angabe im Starter) und Betriebssystem;
- was ein Angreifer erreichen kann und unter welchen Voraussetzungen;
- ein Nachstellungsweg **mit erfundenen Daten**. Bitte keine echten Belege, Kontonummern, Datenräume oder Schlüssel anhängen.

Sie erhalten eine Eingangsbestätigung. Eine bestätigte Lücke wird in einem eigenen Release behoben; die Versionshinweise nennen sie, nach
Wunsch mit Ihrem Namen.

## Unterstützte Versionen

Unterstützt wird jeweils die neueste öffentliche Version. Portelyra ist eine Beta.

## Was Portelyra schützt

- Daten bleiben lokal; es gibt keinen Server und keine Telemetrie.
- Releases und Plugins sind signiert; ein Update prüft die Signatur gegen die Vertrauensliste der installierten Version.
- Leser-Plugins für Belege laufen abgeschottet (Landlock und seccomp) und dürfen weder schreiben noch ins Netz.
- Der Datenraum lässt sich mit einem Passwort verschlüsseln ([`docs/handbuch/passwortschutz.md`](docs/handbuch/passwortschutz.md)).
