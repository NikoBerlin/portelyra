# Bison

| Steckbrief | |
|---|---|
| Leser | Krypto „Krypto-Börsen und Wallets (CSV-Exporte)“ · Rewards „Bison“ · Cash „Bison Transaktionen, nur Euro-Guthaben (CSV)“ |
| Dokument | „Transaction history (CSV)“ je Kalenderjahr |
| Zeitraum | je Jahr; das laufende Jahr jeden Monat neu, im Januar auch das Vorjahr |
| Deckt ab | alle Coins, Staking und das Euro-Guthaben |
| Geprüft | Berichtsformat Stand 10/2026 (Semikolon, Zeiten in UTC) |

## Herunterladen

1. Anmelden, **Profil** → links **„Reports“**.
2. Kachel **„Transaction history (CSV)“**: das Jahr wählen (es geht nur jahresweise) → **„Request report“**.
3. Der Bericht kommt in die **Bison-Inbox** („Your transaction history for the year … is ready to download“) und wird dort
   heruntergeladen.

Weitere Kacheln: „Info-Report“ (vorläufige FIFO-Gewinne des Steuerjahres) und „Bank account statement“ (Euro-Saldo je Monat). Beide
lassen sich als Beleg ablegen; gelesen werden sie nicht.

## Ablegen

Unterordner `Bison`, darin je Jahr `Transaktionen`. Ein erneuter Download desselben Jahres heißt oft wie der alte mit „(2)“; beide
dürfen liegen bleiben – der neuere gilt, gleiche Zeilen zählen einmal. Der Eingang schlägt Zeitraum und alle Bison-Konten vor.

## Buchen

Jeweils erst prüfen, dann buchen:

1. **Krypto** – Import „Krypto-Belege“, Leser „Krypto-Börsen und Wallets (CSV-Exporte)“, aus der Ablage Institut „Bison“.
2. **Rewards** – Reward-Import mit dem Leser „Bison“: Staking-Rewards.
3. **Cash** – Karte „Cash-Auszug importieren“, Quelle „Bison Transaktionen, nur Euro-Guthaben (CSV)“, Konto des Euro-Guthabens.

## Was gebucht wird

- Käufe und Verkäufe mit Euro-Betrag und Gebühr; Euro-Ein- und -Auszahlungen; Staking-Rewards über den Reward-Import.

## Grenzen

- Der Bericht nennt keinen Saldo. Das Euro-Konto bleibt „teilweise erfasst“, bis ein Saldo bestätigt wird („Saldo bestätigen“ im
  Cash-Import). Ob der monatliche „Bank account statement“ dafür als Beleg dient, ist offen.

## Steuerunterlagen

Der „Info-Report“ je Steuerjahr nennt die realisierten Gewinne nach FIFO bei Bison – unverbindlich, als Vergleich zur eigenen
Rechnung. Ablegen unter `<Jahr>/Steuer`.
