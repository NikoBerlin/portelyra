# C24 Bank – Leser-Plugin

Herausgeber: Portelyra · Version 1.1.0 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## C24 Bank Transaktionen (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Transaktionsliste (CSV) |
| Dateien | .csv |
| Erkennung | „transaktionstyp + buchungsdatum + betrag“ |
| Geprüft | CSV-Export der Transaktionen je Konto (Smartkonto, Tagesgeld), Semikolon oder Komma, auch mit BOM. |

Grenzen:

- Ein Export über „Alle Konten“ wird abgewiesen; bitte je Konto exportieren.
- Kein Saldo im Export; ohne Saldoabgleich bleibt die Abdeckung unvollständig.

Das Plugin bringt einen Erzeuger erfundener Belege für den Selbsttest mit (Referenz für alle Erzeuger).

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/c24.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
