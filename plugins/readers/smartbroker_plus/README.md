# Smartbroker+ (Baader Bank) – Leser-Plugin

Herausgeber: Portelyra · Version 1.2.0 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Smartbroker+ (CSV-Export und Dividendenabrechnungen)

| | |
|---|---|
| Bereich | Wertpapiere (Käufe, Verkäufe, Erträge, Kapitalmaßnahmen, Vorabpauschalen) |
| Dokument | Transaktionsexport (CSV) und Dividendenabrechnungen (PDF) |
| Dateien | .pdf, .txt, .csv |
| Erkennung | „depotnummer + transaktionstyp + isin + name 1 + stücke + ausführungszeitpunkt + ausführungskurs + handelswährung + kontowährung + anlagebetrag in kontowährung + gebühren in kontowährung + steuern in kontowährung + gesamtbetrag in kontowährung + status der transaktion“ oder „smartbroker“; danach entscheidet die Erkennung des Lesers |
| Geprüft | CSV-Export der Transaktionen aus SMARTBROKER+ (nur Zeilen mit Status CONFIRMED; Zeiten lokal) und Dividendenabrechnungen der Baader Bank für Smartbroker als PDF (Brutto in Fremdwährung über den Umrechnungskurs des Belegs, Datum = Zahltag). |

Grenzen:

- Vorläufige (PRECONFIRMED) und stornierte Orders, Devisengeschäfte (folgen mit #449), Steuerunterlagen.

## Smartbroker+ Devisenkonten (USD, CHF …)

| | |
|---|---|
| Bereich | Devisen (Fremdwährungskonten) |
| Dokument | Devisenbelege, Perioden-Kontoauszüge der Fremdwährungskonten, Dividenden in Fremdwährung (PDF oder Text) |
| Dateien | .pdf, .txt, .csv |
| Erkennung | „perioden-kontoauszug: + -konto“ oder „devisengeschäft“ oder „devisengeschaft“ oder (seit 1.2.0) „zu gunsten konto + umrechnungskurs: eur/“ für Dividenden mit Gutschrift in Fremdwährung; danach entscheidet die Erkennung des Lesers |
| Geprüft | Perioden-Kontoauszüge der Fremdwährungskonten (Saldo-Anker), Devisenbelege der Baader Bank für Smartbroker (Kauf und Verkauf der Währung; Kurs = EUR-Gegenwert ÷ Fremdwährungsbetrag, Datum = Abschlussdatum) und Dividendenabrechnungen mit Gutschrift in Fremdwährung (Zugang aus Ertrag; EUR-Wert über den Umrechnungskurs des Belegs, Datum = Valuta). |

Grenzen:

- Gutschriften auf dem EUR-Verrechnungskonto (liest der Wertpapier-Leser), Wertpapierabrechnungen, Steuerunterlagen; die Dividende selbst bucht der Wertpapier-Leser.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/smartbroker.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`). Für den
Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen Beleg samt erwartetem
Ergebnis, unabhängig vom Leser.
