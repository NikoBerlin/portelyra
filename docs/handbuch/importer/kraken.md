# Kraken

| Steckbrief | |
|---|---|
| Leser | Krypto „Krypto-Börsen und Wallets (CSV-Exporte)“ · Rewards „Kraken“ · Cash „Kraken Ledger, nur Euro-Guthaben (CSV)“ |
| Dokument | Ledger-Export als CSV (`kraken-spot-ledgers-<von>-<bis>.csv`) |
| Zeitraum | vom Kontobeginn bis heute |
| Deckt ab | alle Unterkonten – Spot, Earn gebunden, Earn flexibel – und das Euro-Guthaben in einer Datei |
| Geprüft | Exportformat „Hauptbuch“ Stand 10/2026 |

## Herunterladen

1. Anmelden, rechts oben im persönlichen Bereich **„Dokumente“**.
2. **„+ Neuer Export“** → im obersten Feld **„Hauptbuch“** (englisch „Ledgers“) wählen – **nicht „Trades“**: Der Trades-Export nennt
   nur Orders an der Spot-Börse und ist ohne solche leer; Käufe über „Krypto kaufen“, Ein- und Auszahlungen, Staking-Erträge und
   Umbuchungen zwischen Spot und Earn stehen nur im Hauptbuch.
3. Zeitraum vom Kontobeginn bis heute, Felder „Alle“, Format **CSV** → „Generieren“.
4. In der Export-Liste herunterladen; Kraken liefert ein ZIP. Entpacken, die CSV ablegen, das ZIP löschen oder archivieren.

## Ablegen

Unterordner `Kraken`, darin je Jahr `Transaktionen`. Ein Export vom Kontobeginn darf in mehreren Jahresordnern liegen; der Eingang
erkennt die Kopien als doppelt. Ältere Exporte dürfen liegen bleiben – der neueste gilt.

## Buchen

Jeweils erst prüfen, dann buchen:

1. **Krypto** – Import „Krypto-Belege“, Leser „Krypto-Börsen und Wallets (CSV-Exporte)“, aus der Ablage Institut „Kraken“: Käufe,
   Verkäufe, Coin-Ein- und -Ausgänge, Umbuchungen zwischen Spot und Earn.
2. **Rewards** – Reward-Import mit dem Leser „Kraken“: Staking-Erträge der Earn-Konten.
3. **Cash** – Karte „Cash-Auszug importieren“, Quelle „Kraken Ledger, nur Euro-Guthaben (CSV)“, Konto des Euro-Guthabens, aus der
   Ablage: Euro-Ein- und -Auszahlungen und die Euro-Seite der Trades.

## Was gebucht wird

- **Unterkonten:** „spot / main“, „earn / bonded“ und „earn / liquid“ sind eigene Wallets. Umbuchungen zwischen ihnen sind interne
  Bewegungen, keine Veräußerung.
- **Trades:** die Euro-Seite samt Gebühr; die Coin-Seite ist die angekommene bzw. abgegebene Menge.
- **Rewards:** Kraken zahlt mitunter zwei Rewards desselben Coins in derselben Sekunde (einen kleinen auf „spot / main“, den
  eigentlichen auf „earn / bonded“). Der Reward-Import versetzt den zweiten um ganze Sekunden, damit die FIFO-Rechnung eine
  eindeutige Reihenfolge hat; Menge, Wert und Konto bleiben.

## Grenzen

- Ein Coin-Ausgang zu einem eigenen Wallet bekommt seine Gegenbuchung erst mit dem Export dieses Wallets (im Krypto-Import
  mitwählen).
- Eine Netzgebühr, die in einem anderen Coin bezahlt wird als dem versendeten, lässt sich noch nicht buchen.

## Steuerunterlagen

Kraken stellt keine deutsche Steuerbescheinigung aus. Unter **„Dokumente“ → „Kontodokumente“**, direkt unter der Export-Liste, gibt
es – sofern vorhanden – einen Steuerbericht. Er dient als Vergleich zur eigenen Rechnung; ablegen unter `<Jahr>/Steuer`. Gelesen wird
er nicht.
