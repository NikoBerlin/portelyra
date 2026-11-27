# Baader Bank (auch Smartbroker) – Leser-Plugin

Herausgeber: Portelyra · Version 1.2.1 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Baader Bank Perioden-Kontoauszug, auch Smartbroker (PDF oder Text)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Perioden-Kontoauszug (PDF oder Text) |
| Dateien | .pdf, .txt |
| Erkennung | nur die Dateiendung |
| Geprüft | Perioden-Kontoauszüge der Baader Bank, auch über Smartbroker+ und für Scalable-Depots aus der Baader-Zeit. |

Grenzen:

- Ein nachgestelltes „-“ kennzeichnet die Belastung; die erste Saldozeile datiert auf den Tag vor dem Zeitraum.
- Erkennung nur über die Dateiendung; ob der Inhalt passt, entscheidet erst das Lesen.

## Baader Erträgnisaufstellung

| | |
|---|---|
| Bereich | Steuerbelege (Erträgnisaufstellung) |
| Dokument | Erträgnisaufstellung (PDF) |
| Dateien | .pdf, .txt |
| Erkennung | „erträgnisaufstellung + einzelnachweis der kapitalerträge“ |
| Geprüft | Jährliche Erträgnisaufstellung der Baader Bank mit Summennachweis (Zeile 7) und Einzelnachweis der Kapitalerträge. |

Grenzen:

- Übernimmt einen Posten nur, wenn sein Kapitalertrag eindeutig seinem Anteil an Zeile 7 entspricht; sonst „unklar“.
- Kreditzinsen und Verwahrentgelt werden nicht übernommen.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/smartbroker.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).

Für den Selbsttest bringt das Plugin je Leser einen Erzeuger erfundener Belege mit (`reader_generator.py`): je Startwert ein
Perioden-Kontoauszug bzw. eine Erträgnisaufstellung samt erwartetem Ergebnis.
