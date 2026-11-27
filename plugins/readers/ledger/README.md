# Ledger Live – Leser-Plugin

Herausgeber: Portelyra · Version 1.1.0 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Ledger Live (Export der Vorgänge)

| | |
|---|---|
| Bereich | Krypto (Käufe, Verkäufe, Transfers zwischen eigenen Konten) |
| Dokument | Export der Vorgänge (CSV) |
| Dateien | .csv |
| Erkennung | „operation date + currency ticker + operation type + operation amount + operation hash“; danach entscheidet die Erkennung des Lesers |
| Geprüft | Export aus Ledger Live mit Operation Date, Currency Ticker, Operation Type, Operation Amount, Operation Hash. |

Grenzen:

- Nur Ein- und Ausgänge; Transfers paart der Kern mit der Gegenseite.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/ledger.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen Export
samt erwartetem Ergebnis.
