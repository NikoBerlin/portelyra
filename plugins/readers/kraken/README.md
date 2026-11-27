# Kraken – Leser-Plugin

Herausgeber: Portelyra · Version 1.3.2 · Schnittstelle `statement_reader_v1`

Das Plugin liest Belege dieses Instituts und liefert Kandidaten. Prüfen, mit dem Bestand abgleichen, Saldoprobe, Paarung von
Transfers, Vorschau und Buchen übernimmt Portelyra. Der Leser läuft abgeschottet: kein Netz, Lesezugriff nur auf den Beleg; die
Datei bleibt unverändert.

## Kraken Ledger, nur Euro-Guthaben (CSV)

| | |
|---|---|
| Bereich | Cash (Kontobewegungen und Salden) |
| Dokument | Ledger-Export (CSV), nur Euro |
| Dateien | .csv |
| Erkennung | „time + type + asset + amount + fee + balance“ |
| Geprüft | Ledger-Export mit time, type, asset, amount, fee, balance; Euro-Zeilen (EUR, ZEUR). |

Grenzen:

- Liest nur das Euro-Guthaben; Coins liest der Krypto-Import.
- Der Buchungstag zählt in Europe/Berlin, die Zeitstempel stehen in UTC.

## Kraken (Ledger-Export, Krypto)

| | |
|---|---|
| Bereich | Krypto (Käufe, Verkäufe, Transfers zwischen eigenen Konten) |
| Dokument | Ledger-Export (CSV) |
| Dateien | .csv |
| Erkennung | „txid + refid + time + type + asset + amount + fee“; danach entscheidet die Erkennung des Lesers |
| Geprüft | Ledger-Export aller Konten (Spot, Earn) mit txid, refid, time, type, asset, amount, fee. |

Grenzen:

- Rewards liest der Reward-Import, Euro-Bewegungen der Cash-Leser.
- Transfers zwischen eigenen Konten paart der Kern über Börsen hinweg.

## Kraken (Ledger-Export, Rewards)

| | |
|---|---|
| Bereich | Rewards (Staking- und andere Erträge in Coins) |
| Dokument | Ledger-Export (CSV) |
| Dateien | .csv |
| Erkennung | „type + fee + amountusd + feeusd“ |
| Geprüft | Ledger-Export aller Konten (Spot, Earn) mit txid, time, type, subtype, asset, wallet, amount, fee, amountusd, feeusd. |

Grenzen:

- Bewertung mit dem USD-Betrag des Exports abzüglich der USD-Gebühr; in Euro rechnet Portelyra mit Devisenkursen um.
- Liest nur Rewards; Käufe, Verkäufe und Transfers liest der Krypto-Leser, Euro-Bewegungen der Cash-Leser.

## Anleitung

Herunterladen beim Institut, Ablegen im Belegordner und Buchen: Handbuch `docs/handbuch/importer/kraken.md`.

Testbelege unter `fixtures/` sind erfunden; das erwartete Ergebnis steht jeweils daneben (`*.expected.json`).
Für den Selbsttest bringt das Plugin je Leser einen Erzeuger mit (`reader_generator.py`): Er baut je Startwert einen erfundenen
Export samt erwartetem Ergebnis.
