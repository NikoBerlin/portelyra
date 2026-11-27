# BSDEX (Börse Stuttgart Digital Exchange) – Leser-Plugin

Herausgeber: Portelyra · Version 1.2.1 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## BSDEX Euro-Guthaben: Transaktionshistorie je Jahr mit Export „Transaktionen“ (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Export Transaktionen und Transaktionshistorie (CSV) |
| Dateien | .csv |
| Erkennung | „transaktionstyp + kryptowährung + betrag + seite + gefüllt + ausgeführter gesamtbetrag + status + transaktionsentgelt + erstellt + finalisiert am“ oder „id + typ + ausführung + eingehender betrag + eingehendes asset + ausgehender betrag + ausgehendes asset + transaktionsentgelt + entgeltwährung“ |
| Geprüft | Export „Transaktionen“ zusammen mit den Jahreshistorien; je Order auf den Cent. |
| Zusammen lesen | ja: mehrere Dateien des Instituts in einem Durchgang |

Grenzen:

- Kein Saldo im Export; die Vollständigkeit belegt erst ein Saldoabgleich.
- Eine Order ohne Ausführungen in der Historie hält den Stapel an; die Vorschau nennt je Grund die erste betroffene Order.

## BSDEX (Transaktionshistorie je Jahr)

| | |
|---|---|
| Bereich | Krypto (Käufe, Verkäufe, Transfers zwischen eigenen Konten) |
| Dokument | Transaktionshistorie (CSV) |
| Dateien | .csv |
| Erkennung | „id + typ + ausführung + eingehender betrag + eingehendes asset + ausgehender betrag + ausgehendes asset + transaktionsentgelt + entgeltwährung“; danach entscheidet die Erkennung des Lesers |
| Geprüft | Transaktionshistorie je Jahr mit ID, Typ, Ausführung (UTC), ein- und ausgehendem Betrag und Asset, Transaktionsentgelt. |

Grenzen:

- Bucht nichts; belegt die genauen Euro-Beträge der Orders des Exports.

## BSDEX (Export „Transaktionen“, Krypto)

| | |
|---|---|
| Bereich | Krypto (Käufe, Verkäufe, Transfers zwischen eigenen Konten) |
| Dokument | Export Transaktionen (CSV) |
| Dateien | .csv |
| Erkennung | „transaktionstyp + kryptowährung + betrag + erstellt + zieladresse + sendeadresse“; danach entscheidet die Erkennung des Lesers |
| Geprüft | Export „Transaktionen“ mit Transaktionstyp, Kryptowährung, Betrag, Erstellt, Zieladresse, Sendeadresse; Limit-Orders mit Gefüllt und Transaktionsentgelt. |
| Zusammen lesen | ja: gleicht die Orders mit den Ausführungen der Jahreshistorie ab |

Grenzen:

- Den genauen Euro-Betrag je Order liefert erst die Jahreshistorie; ohne passende Ausführungen bleibt eine Order offen, mit dem genauen Grund (Historie fehlt oder zu alt, keine Ausführung im Zeitraum, Menge oder Betrag passen nicht).
- Weicht der genaue Betrag einer Order um mehr als 5 Cent vom gerundeten des Exports ab, bleibt nur sie offen; weichen mehr als ein Viertel der Orders ab, verwirft der Kern das Ergebnis.

## BSDEX (Export „Transaktionen“, Rewards)

| | |
|---|---|
| Bereich | Rewards (Staking- und andere Erträge in Coins) |
| Dokument | Export Transaktionen (CSV) |
| Dateien | .csv |
| Erkennung | „erstellt + transaktionstyp + kryptowährung + betrag + transaktionsentgelt“ oder „erstellt + transaktionstyp + kryptowaehrung + betrag + transaktionsentgelt“ |
| Geprüft | Export „Transaktionen“ mit Transaktionstyp, Kryptowährung, Betrag, Erstellt, Transaktionsentgelt; Staking-Rewards. |

Grenzen:

- Keine Kennung je Zeile: Der Schlüssel bindet Datei und Zeile; in einem neuen Download erkennt der Kern gebuchte Rewards an Zeit, Coin und Menge.
- Ohne Bewertung im Export; bewertet wird mit Marktdaten.
- Die Zeiten des Exports gelten in Berliner Zeit.
- Liest nur Rewards; Käufe, Verkäufe, Ein- und Auszahlungen liest der Krypto- bzw. Cash-Leser.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/bsdex.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin je Leser einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen
Export „Transaktionen“ oder eine erfundene Transaktionshistorie samt erwartetem Ergebnis.
