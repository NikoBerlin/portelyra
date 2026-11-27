# Bison – Leser-Plugin

Herausgeber: Portelyra · Version 1.4.2 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Bison Transaktionen, nur Euro-Guthaben (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Transaktionsexport (CSV), nur Euro |
| Dateien | .csv |
| Erkennung | „transaction type + eur (amount) + fee“ |
| Geprüft | Export mit Transaction type, Eur (amount), Fee; Einzahlung, Auszahlung, Kauf und Verkauf. |

Grenzen:

- Kein Saldo im Export.
- Liest nur das Euro-Guthaben; Coins liest der Krypto-Import.

## Bison Verrechnungskonto, Monatsübersicht der EUWAX (PDF oder Text)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Monatsübersicht des Verrechnungskontos (PDF oder Text) |
| Dateien | .pdf, .txt |
| Erkennung | über die Dateiendung; ob der Inhalt passt, entscheidet erst das Lesen |
| Geprüft | Monatsübersichten der EUWAX für das Bison-Euro-Guthaben, mit Eröffnungsbilanz und Abschlusssaldo. |

Download: in der Bison-App unter den Dokumenten die „Monatsübersicht“ je Monat (PDF); ablegen unter `Bison/<Jahr>/Verrechnung/`.

Grenzen:

- Eröffnung plus Buchungen muss den Abschlusssaldo ergeben, sonst wird der Beleg nicht übernommen.
- Ein Monat ohne Buchung bestätigt nur den Saldo.
- Dasselbe Euro-Konto liest auch der CSV-Leser (ohne Saldo); im Cash-Import je Konto eine Quelle wählen.

## Bison (Transaktionen, Krypto)

| | |
|---|---|
| Bereich | Krypto (Käufe, Verkäufe, Transfers zwischen eigenen Konten) |
| Dokument | Transaktionsexport (CSV) |
| Dateien | .csv |
| Erkennung | „transaction id + transaction type + asset + asset (amount) + date (utc - coordinated universal time)“; danach entscheidet die Erkennung des Lesers |
| Geprüft | Export mit Transaction ID, Transaction type, Asset, Asset (amount), Date (UTC). |

Grenzen:

- Euro-Bewegungen liest der Cash-Leser.
- Zeitstempel in UTC.

## Bison (Export, Rewards)

| | |
|---|---|
| Bereich | Rewards (Staking- und andere Erträge in Coins) |
| Dokument | Export je Kalenderjahr (CSV) |
| Dateien | .csv |
| Erkennung | „asset + price“ |
| Geprüft | Export je Kalenderjahr (Semikolon) mit Transaction ID, Transaction type, Currency, Asset, Eur (amount), Asset (amount), Asset (market price), Fee, Date (UTC). |

Grenzen:

- Bewertung mit dem Marktpreis des Coins zum Zeitpunkt des Rewards.
- Mehrere Jahresdateien zählen als ein Lauf; was in mehreren steht, zählt einmal.
- Liest nur Rewards; Käufe, Verkäufe, Ein- und Auszahlungen liest der Krypto- bzw. Cash-Leser.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/bison.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin je Leser einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen
Export samt erwartetem Ergebnis.
