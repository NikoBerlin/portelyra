# Ledger

| Steckbrief | |
|---|---|
| Leser | Krypto „Krypto-Börsen und Wallets (CSV-Exporte)“ |
| Dokument | „Vorgänge“ aus Ledger Live als CSV (`ledgerwallet-operations-<Datum>.csv`) |
| Zeitraum | gesamte Historie |
| Deckt ab | alle Konten von Ledger Live in einer Datei (Spalte „Account Name“) |
| Geprüft | Exportformat Stand 10/2026 |

## Herunterladen

In **Ledger Live**: Konto wählen → **„Optionen“** → **„Vorgänge exportieren“**.

## Ablegen

Unterordner `Ledger` (auch `LedgerWallet`), darin je Jahr `Transaktionen`.

## Buchen

Import „Krypto-Belege“, Leser „Krypto-Börsen und Wallets (CSV-Exporte)“, aus der Ablage Institut „Ledger“. Für die Richtung von
Transfers zu Börsen deren Exporte mitwählen.

## Was gebucht wird

- Ein- und Ausgänge je Coin. **Ledger Live führt einen Ausgang samt Netzgebühr:** Der Leser zieht die Gebühr ab; versendet ist
  „Operation Amount“ minus „Operation Fees“, und genau das kommt bei der Gegenseite an.

## Grenzen und bewusst nicht gebucht

- **Solana-Stake-Konten:** Ledger Live zeigt Bewegungen zwischen Wallet und eigenen Stake-Konten wie Transfers. Sie bleiben offen
  und werden nur gebucht, wenn ein Gegenkonto feststeht.
- **Kleinstbeträge ohne Gegenstück** (Staub, Spam an die Adresse) werden nicht gebucht.
- **Coins ohne Asset im Katalog** erscheinen als „Asset fehlt“ – anlegen oder liegen lassen.
- Die ETH-Gebühr von Token-Transfers lässt sich noch nicht am Token-Transfer buchen.

## Steuerunterlagen

Keine; ein Wallet stellt keine aus.
