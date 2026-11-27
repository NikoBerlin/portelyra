# Trade Republic – Leser-Plugin

Herausgeber: Portelyra · Version 1.2.2 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Trade Republic Kontoauszug (PDF oder Text)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Kontoauszug über die ganze Historie (PDF oder Text) |
| Dateien | .pdf, .txt |
| Erkennung | „€“ |
| Geprüft | Ein PDF über die gesamte Kontohistorie mit Abschnitt „UMSATZÜBERSICHT“. |

Grenzen:

- Das Vorzeichen folgt aus der Änderung des laufenden Saldos; eine Zeile mit unpassendem Saldoschritt wird gemeldet.
- Tabellen hinter der Umsatzübersicht (Geldmarktfonds, Depot) werden nicht gelesen.
- Die einbehaltene Steuer je Zinszeile nennt nur der Transaktionsexport.

## Trade Republic Transaktionsexport (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Transaktionsexport (CSV) |
| Dateien | .csv |
| Erkennung | „date + type + amount + fee + tax + currency + description“ |
| Geprüft | CSV-Export der Transaktionen mit den Spalten date, type, amount, fee, tax, currency, description. |

Grenzen:

- Der Export nennt keinen Saldo; die Vollständigkeit belegt erst ein Saldoabgleich.
- Zinsen, deren Steuer den Betrag ganz aufzehrt, werden gemeldet statt gebucht.

## Trade Republic (CSV-Export)

| | |
|---|---|
| Bereich | Wertpapiere (Käufe, Verkäufe, Erträge, Kapitalmaßnahmen, Vorabpauschalen) |
| Dokument | Transaktionsexport (CSV) |
| Dateien | .pdf, .txt, .csv |
| Erkennung | „datetime + date + category + type + name + symbol + shares + price + amount + fee + tax + currency + transaction_id“ oder „trade republic bank“; danach entscheidet die Erkennung des Lesers |
| Geprüft | CSV-Export „Transaktionen“ aus der Trade-Republic-App: Käufe und Verkäufe (Teilausführungen aus ganzen Stücken und Bruchteil getrennt, in der Reihenfolge der Bank; Zeiten in UTC, umgerechnet), Dividenden brutto in EUR; Vorabpauschale (EARNINGS) als Hinweis gegen den eingetragenen Wert. |

Grenzen:

- Betrag der Vorabpauschale (der Export nennt nur die Steuer), Steueroptimierung, Zeichnungen (IPO), Dividenden mit Rückbuchung, Ein- und Auszahlungen, Zinsen und andere Kontobewegungen.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/trade-republic.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Je Startwert baut er für jeden Leser einen
erfundenen Beleg samt erwartetem Ergebnis, unabhängig vom Leser.
