# Scalable Capital – Leser-Plugin

Herausgeber: Portelyra · Version 1.2.1 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Scalable Capital Tagesgeld (PDF oder Text)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Monatsauszug Tagesgeld (PDF oder Text) |
| Dateien | .pdf, .txt |
| Erkennung | „kontostand am“ |
| Geprüft | Monatliche Kontoauszüge als PDF mit Zeitraum und den Zeilen „Kontostand am“. |

Grenzen:

- Ein Dokument ohne „Kontostand am“ (etwa eine Dividendenabrechnung) wird abgewiesen.
- Bis September 2026 nannte „Kontostand am <Beginn>“ den Stand nach dem ersten Tag; der erste Tag wird nur abgezogen, wenn der Auszug sonst nicht aufgeht.
- Ein Monat ohne Bewegung wird nur mit dem Satz „Keine Kontobewegungen“ und gleichem Anfangs- und Endstand angenommen.

## Scalable Capital Verrechnungskonto (PDF oder Text)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Monatsauszug Verrechnungskonto (PDF oder Text) |
| Dateien | .pdf, .txt |
| Erkennung | „kontostand am“ |
| Geprüft | Monatliche Kontoauszüge des Verrechnungskontos als PDF, gleiche Vorlage wie das Tagesgeld. |

Grenzen:

- Wertpapierabrechnungen, Gebühren und Ausschüttungen wirken nur auf den Saldo; als eigener Ertrag gelten nur Zinsen.
- Ein Dokument ohne „Kontostand am“ wird abgewiesen.

## Scalable Capital (auch Baader-Abrechnungen für Scalable)

| | |
|---|---|
| Bereich | Wertpapiere (Käufe, Verkäufe, Erträge, Kapitalmaßnahmen, Vorabpauschalen) |
| Dokument | Wertpapierabrechnungen, Dividenden, Vorabpauschalen (PDF oder Text) |
| Dateien | .pdf, .txt, .csv |
| Erkennung | „baader bank“ oder „scalable capital“ oder „baaderbank.de“; danach entscheidet die Erkennung des Lesers |
| Geprüft | PDF-Belege der Scalable Capital GmbH, der Scalable Capital Bank GmbH und der Baader Bank für Scalable: Wertpapierabrechnung Kauf und Verkauf, Dividende, Vorabpauschale je Fonds (Betrag vor Teilfreistellung; vorn und hinten gleich, gegen „Zu versteuern“ geprüft). |

Grenzen:

- Depotüberträge und Einlieferungen, Steuerunterlagen, Depotauszüge und Informationen.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/scalable.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`). Für den
Selbsttest bringt das Plugin einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen Beleg samt erwartetem
Ergebnis, unabhängig vom Leser.
