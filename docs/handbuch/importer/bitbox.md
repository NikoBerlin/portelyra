# BitBox

| Steckbrief | |
|---|---|
| Leser | Krypto „Krypto-Börsen und Wallets (CSV-Exporte)“ |
| Dokument | Transaktionsverlauf je Wallet-Konto als CSV (`<Datum>-at-<Zeit>-v0-<Kennung>-<coin>-<n>-export.csv`) |
| Zeitraum | gesamte Historie |
| Deckt ab | je Konto und Token eine Datei (etwa ETH und ein Token getrennt) |
| Geprüft | BitBoxApp 4.51 |

## Herunterladen

In der **BitBoxApp**: das Wallet-Konto wählen → **„Kontoinformationen“** → **„Transaktionsverlauf exportieren“**. Für jedes Konto
und jeden Token einzeln. Ohne neue Transaktion muss nichts neu gezogen werden.

## Ablegen

Unterordner `BitBox`, darin je Jahr `Transaktionen`. Der Eingang ordnet jede Datei ihrem Wallet-Konto zu.

## Buchen

Import „Krypto-Belege“, Leser „Krypto-Börsen und Wallets (CSV-Exporte)“, aus der Ablage Institut „BitBox“. Für die Richtung von
Transfers zwischen eigenen Wallets und Börsen die Exporte der Gegenseite mitwählen.

## Was gebucht wird

- Ein- und Ausgänge je Coin, die Netzgebühr am Ausgang in der Menge des Coins.

## Grenzen

- Bei Token-Transfers (etwa ERC-20 auf Ethereum) zahlt man die Netzgebühr in ETH. Sie steht im ETH-Export als „Gebühr ohne Transfer“
  und lässt sich noch nicht am Token-Transfer buchen.

## Steuerunterlagen

Keine; ein Wallet stellt keine aus.
