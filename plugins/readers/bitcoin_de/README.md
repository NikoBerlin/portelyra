# Bitcoin.de – Leser-Plugin

Herausgeber: Portelyra · Version 1.1.1 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Bitcoin.de (Kontoauszug je Coin)

| | |
|---|---|
| Bereich | Krypto (Käufe, Verkäufe, Transfers zwischen eigenen Konten) |
| Dokument | Kontoauszug je Coin (CSV) |
| Dateien | .csv |
| Erkennung | „datum + typ + währung + referenz + zu- / abgang“; danach entscheidet die Erkennung des Lesers |
| Geprüft | Kontoauszug je Coin mit Datum, Typ, Währung, Referenz, Zu- / Abgang; Zeiten in Europe/Berlin. |

Grenzen:

- Je Coin eine Datei; den bezahlten Betrag am Bankauszug prüfen.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: siehe Handbuch `docs/handbuch/monatlicher-eingang.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen Kontoauszug
samt erwartetem Ergebnis.
