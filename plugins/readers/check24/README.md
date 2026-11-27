# CHECK24 Geldanlagecenter – Leser-Plugin

Herausgeber: Portelyra · Version 1.1.0 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## CHECK24 Geldanlagecenter, Tagesgeld (PDF-Druck oder Text)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Buchungsliste Tagesgeld (Browserdruck als PDF oder Text) |
| Dateien | .pdf, .txt |
| Erkennung | „€“ |
| Geprüft | Buchungsliste des Geldanlagecenters, im Browser als PDF gedruckt. |

Grenzen:

- Kein Saldo im Ausdruck; ohne Saldoabgleich bleibt die Abdeckung unvollständig.
- Steuern stehen als eigene Abbuchungen.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: siehe Handbuch `docs/handbuch/monatlicher-eingang.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen Beleg
samt erwartetem Ergebnis, den der Leser genau treffen muss.
