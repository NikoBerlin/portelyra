# DKB – Leser-Plugin

Herausgeber: Portelyra · Version 1.1.1 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## DKB Girokonto-Kontoauszug (PDF oder Text)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Kontoauszug Girokonto (PDF oder Text) |
| Dateien | .pdf, .txt |
| Erkennung | „belastung in eur“ oder „betrag haben eur“ |
| Geprüft | Zwei Vorlagen: ältere (Spalten Belastung und Gutschrift, Datum ohne Jahr) und neuere (volles Datum, Soll mit Minus). |

Grenzen:

- Bei der alten Vorlage entscheidet allein die Spalte über das Vorzeichen; das Jahr folgt aus dem Auszugszeitraum.

## DKB Umsatzliste, Giro und Tagesgeld (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Umsatzliste Giro und Tagesgeld (CSV) |
| Dateien | .csv |
| Erkennung | „"buchungsdatum" + betrag (€)“ |
| Geprüft | CSV-Umsatzliste mit „Buchungsdatum“ und „Betrag (€)“, deutsche Beträge. |

Grenzen:

- „-2.000“ sind zweitausend, nicht zwei (deutsches Format).
- Zinsen des Tagesgelds sind netto; den Bruttozins nennt der Text der Abrechnung.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/dkb.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen Beleg
samt erwartetem Ergebnis, den der Leser genau treffen muss.
