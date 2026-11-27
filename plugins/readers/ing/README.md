# ING – Leser-Plugin

Herausgeber: Portelyra · Version 1.2.1 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## ING Kontoauszug, Giro und Extra-Konto (PDF oder Text)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Kontoauszug Giro und Extra-Konto (PDF oder Text) |
| Dateien | .pdf, .txt |
| Erkennung | nur die Dateiendung |
| Geprüft | Monatliche Kontoauszüge als PDF mit „Alter Saldo“ und „Neuer Saldo“. |

Grenzen:

- Eine Buchung wird an ihrer Buchungsart erkannt (Lastschrift, Gutschrift, Überweisung und weitere); eine unbekannte Buchungsart fällt in der Saldoprüfung auf.
- Erkennung nur über die Dateiendung; ob der Inhalt passt, entscheidet erst das Lesen.

## ING Direkt-Depot

| | |
|---|---|
| Bereich | Wertpapiere (Käufe, Verkäufe, Erträge, Kapitalmaßnahmen, Vorabpauschalen) |
| Dokument | Wertpapierabrechnungen, Dividenden, Splitmitteilungen, Vorabpauschalen (PDF oder Text) |
| Dateien | .pdf, .txt, .csv |
| Erkennung | „ing-diba + direkt-depot“; danach entscheidet die Erkennung des Lesers |
| Geprüft | PDF-Belege des ING Direkt-Depots: Wertpapierabrechnung Kauf und Verkauf (gleichzeitige Teilausführungen gemeinsam), Dividenden- und Ausschüttungsgutschrift, Splitmitteilung (Wertpapier Eingang der Splitaktien, übernehmbar als Kapitalmaßnahme), Vorabpauschale je Fonds (Betrag vor Teilfreistellung; ab 2026 von der Rückseite, gegen Stück × Wert je Stück geprüft). |

Grenzen:

- Überträge, thesaurierende Erträge, Steuerunterlagen, Sammelübersichten mehrerer Vorgänge.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/ing.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Je Startwert baut er für jeden Leser einen
erfundenen Beleg samt erwartetem Ergebnis, unabhängig vom Leser.
