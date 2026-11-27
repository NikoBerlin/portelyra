# Bondora Go & Grow – Leser-Plugin

Herausgeber: Portelyra · Version 1.1.0 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Bondora Go & Grow (xlsx oder CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Kontoauszug (xlsx oder CSV) |
| Dateien | .xlsx, .csv |
| Erkennung | „datum + zahlungsart“ oder „date + payment + type“ |
| Geprüft | Kontoauszug von Go & Grow als xlsx oder CSV, Spalten deutsch (Datum, Zahlungsart, Eingänge, Ausgänge, Guthaben) oder englisch. |

Grenzen:

- Zinsen werden an „Zins“ bzw. „interest“ in der Zahlungsart erkannt.
- Anfangs- und Endsaldo nur, wenn der Export die Kopfzeilen „Zu Beginn“ und „Ergebnis“ trägt; sonst prüft der Saldo je Zeile.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/bondora.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen Beleg
samt erwartetem Ergebnis, den der Leser genau treffen muss.
