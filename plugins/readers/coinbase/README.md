# Coinbase – Leser-Plugin

Herausgeber: Portelyra · Version 1.3.1 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Coinbase Transaktionen, nur EUR-Wallet (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Transaktionsbericht (CSV), nur EUR-Wallet |
| Dateien | .csv |
| Erkennung | „transaction type“ |
| Geprüft | Transaktionsbericht mit Kopfzeile „Transaction Type“; Verkäufe gegen Euro und Käufe aus dem EUR-Wallet. |

Grenzen:

- Käufe per Karte berühren das EUR-Wallet nicht und werden übergangen.
- EURC ist ein Stablecoin und kein Euro-Guthaben.

## Coinbase (Transaktionsbericht, Krypto)

| | |
|---|---|
| Bereich | Krypto (Käufe, Verkäufe, Transfers zwischen eigenen Konten) |
| Dokument | Transaktionsbericht (CSV) |
| Dateien | .csv |
| Erkennung | „id + timestamp + transaction type + asset + quantity transacted“; danach entscheidet die Erkennung des Lesers |
| Geprüft | Transaktionsbericht mit ID, Timestamp, Transaction Type, Asset, Quantity Transacted; Käufe und Verkäufe mit dem Betrag „Total“. |

Grenzen:

- Staking-Erträge liest der Reward-Import.
- EURC ist ein Stablecoin und kein Euro-Guthaben.

## Coinbase (Transaktionsbericht, Rewards)

| | |
|---|---|
| Bereich | Rewards (Staking- und andere Erträge in Coins) |
| Dokument | Transaktionsbericht (CSV) |
| Dateien | .csv |
| Erkennung | „price + asset“ oder „price + currency“ |
| Geprüft | Transaktionsbericht mit ID, Timestamp, Transaction Type, Asset, Quantity Transacted, Price Currency, Price at Transaction, Total, Fees; Kopfzeile in den ersten zwölf Zeilen. Gelesen werden die Arten „Staking Income“, „Rewards Income“, „Coinbase Earn“, „Learning Reward“, „Incentives Rewards Payout“ und „Retail Simple Price Improvement“. |

Grenzen:

- Bewertung mit dem Gesamtbetrag, sonst mit dem Stückpreis des Berichts.
- Liest nur Rewards; Käufe, Verkäufe und Transfers liest der Krypto-Leser.
- Die Zeiten des Berichts stehen in UTC.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/coinbase.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).

Für den Selbsttest bringt das Plugin je Leser einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen
Transaktionsbericht samt erwartetem Ergebnis, mit oder ohne Vorspannzeilen vor der Kopfzeile.
