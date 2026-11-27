# Revolut – Leser-Plugin

Herausgeber: Portelyra · Version 1.1.0 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Revolut Girokonto (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Kontoauszug Girokonto (CSV) |
| Dateien | .csv |
| Erkennung | „type + product + completed date + amount + fee + balance“ |
| Geprüft | CSV-Kontoauszug „All accounts“ mit Type, Product, Completed Date, Amount, Fee, Balance; Zeilen mit Product „Current“; Format Stand 10/2026. |

Grenzen:

- Gebühren verlassen das Konto zusammen mit dem Betrag.
- Der Anfangssaldo wird aus der ersten Zeile abgeleitet.

## Revolut Sparkonto/Tagesgeld (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Kontoauszug Sparkonto (CSV) |
| Dateien | .csv |
| Erkennung | „type + product + completed date + amount + fee + balance“ |
| Geprüft | CSV-Kontoauszug „All accounts“ mit Type, Product, Completed Date, Amount, Fee, Balance; Zeilen mit Product „Deposit“; Format Stand 10/2026. |

Grenzen:

- Zinsen, deren Steuer den Betrag ganz aufzehrt, werden gemeldet statt gebucht.
- Der Anfangssaldo wird aus der ersten Zeile abgeleitet.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/revolut.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen Beleg
samt erwartetem Ergebnis, den der Leser genau treffen muss.
