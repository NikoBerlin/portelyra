# Coinbase

| Steckbrief | |
|---|---|
| Leser | Krypto „Krypto-Börsen und Wallets (CSV-Exporte)“ · Rewards „Coinbase“ · Cash „Coinbase Transaktionen, nur EUR-Wallet (CSV)“ |
| Dokument | Transaktionsbericht als CSV |
| Zeitraum | vom Kontobeginn bis heute |
| Deckt ab | alle Coins, Staking und die EUR-Wallet in einem Bericht |
| Geprüft | Berichtsformat Stand 10/2026 |

## Herunterladen

1. Anmelden, **Konto verwalten** → links unter „Personal Account“ **Statements**.
2. Rechts **„Generate custom statement“**: Asset „All assets“, Transaction type „All transactions“, Datum vom Kontobeginn bis
   heute, Format **CSV** → „Generate“.
3. Bei längeren Zeiträumen fragt Coinbase die Zwei-Faktor-Bestätigung ab.

Die Monatsberichte unter „Transactions“ (HTML, PDF, CSV) braucht es nicht; der eigene Bericht deckt alles ab.

## Ablegen

Unterordner `Coinbase`, darin je Jahr `Transaktionen`. Ältere Berichte dürfen liegen bleiben – der neueste gilt, gleiche Zeilen
zählen einmal. Der Eingang schlägt für den Bericht den ganzen Zeitraum und alle Coinbase-Konten vor (Coins, Staking, EUR-Wallet).

## Buchen

Jeweils erst prüfen, dann buchen:

1. **Krypto** – Import „Krypto-Belege“, Leser „Krypto-Börsen und Wallets (CSV-Exporte)“, aus der Ablage Institut „Coinbase“.
2. **Rewards** – Reward-Import mit dem Leser „Coinbase“.
3. **Cash** – Karte „Cash-Auszug importieren“, Quelle „Coinbase Transaktionen, nur EUR-Wallet (CSV)“, Konto der EUR-Wallet.

## Was gebucht wird

- **Käufe und Verkäufe:** Kurswert ist „Subtotal“, die Gebühr der Unterschied zu „Total“ – „Total“ ist, was bezahlt bzw.
  gutgeschrieben wurde. Bei Verkäufen steckt ein Spread in „Total“, nicht in „Fees“.
- **Rewards:** „Staking Income“, „Incentives Rewards Payout“ und „Retail Simple Price Improvement“ (Preisverbesserung in Coin).
- **Staking:** „Retail Staking Transfer“ ist eine Umbuchung zwischen Konto und Staking, keine Veräußerung.
- **EUR-Wallet:** Verkäufe gegen Euro schreiben gut, Käufe „using EUR-Wallet“ buchen ab. Käufe mit Karte berühren die EUR-Wallet
  nicht.
- **Eingänge** („Receive“) brauchen für ihre Richtung den Export des sendenden Wallets.

## Grenzen

- Rewards gestakter Coins landen auf dem Hauptkonto statt auf dem Staking-Konto.

## Steuerunterlagen

Eine Steuerübersicht gibt es neben den Statements: **Konto verwalten** → links **„Taxes“**. Sie dient als Vergleich zur eigenen
Rechnung; ablegen unter `<Jahr>/Steuer`. Gelesen wird sie nicht.
