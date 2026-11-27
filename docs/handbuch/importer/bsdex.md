# BSDEX

| Steckbrief | |
|---|---|
| Leser | Krypto „Krypto-Börsen und Wallets (CSV-Exporte)“ · Rewards „BSDEX“ · Cash „BSDEX Euro-Guthaben: Transaktionshistorie je Jahr mit Export „Transaktionen““ |
| Dokumente | Transaktionshistorie je Kalenderjahr (CSV) und Export „Transaktionen“ mit allen Typen (CSV) |
| Zeitraum | Historie je Jahr, das laufende jeden Monat neu; Export vom Kontobeginn bis heute, am selben Tag |
| Deckt ab | alle Coins, Staking und das Euro-Guthaben |
| Geprüft | Exportformate Stand 10/2026 |

## Herunterladen – jeden Monat, in dieser Reihenfolge

1. **Transaktionshistorie des laufenden Jahres** neu laden (Download „Transaktionshistorie“ je Jahr, CSV). Im Januar zusätzlich das
   Vorjahr noch einmal, damit dessen letzte Tage vollständig sind.
2. **Am selben Tag den Export „Transaktionen“** – CSV mit **allen Typen**, vom Kontobeginn bis heute. Er muss Zeilen wie
   „Einzahlungen“, „Auszahlung“ und „Staking Reward“ enthalten; enthält er nur „Limit“, war ein Filter gesetzt.

PDFs dürfen als Beleg dazu, gelesen werden die CSV.

## Ablegen

Beide unter `BSDEX/<Jahr>/Transaktionen/` und im Eingang übernehmen. Ältere Exporte und Historien bleiben liegen: Jede Order und
jeder ausgeführte Teil zählt einmal, auch wenn er in mehreren Dateien steht.

## Buchen

Jeweils erst prüfen, dann buchen:

1. **Krypto** – Import „Krypto-Belege“, Leser „Krypto-Börsen und Wallets (CSV-Exporte)“, aus der Ablage Institut „BSDEX“: Trades je
   Order, Coin-Ein- und -Ausgänge.
2. **Rewards** – Reward-Import mit dem Leser „BSDEX“: Staking-Rewards aus dem Export.
3. **Cash** – Karte „Cash-Auszug importieren“, Quelle „BSDEX Euro-Guthaben: Transaktionshistorie je Jahr mit Export
   „Transaktionen““, Konto des Euro-Guthabens, aus der Ablage alle Jahre seit Kontobeginn. Die Vorschau zeigt je Zeile, was es war
   („Kauf BTC“, „Einzahlung“).
4. **Saldo vergleichen:** Das Euro-Guthaben in Portelyra muss auf den Cent dem bei BSDEX entsprechen – bis auf die Teile einer noch
   offenen Order, die die Cash-Vorschau mit Betrag nennt.

## Was gebucht wird

**Je Order, nicht je Teil.** Gebucht wird, was für einen Kauf bezahlt und für einen Verkauf gutgeschrieben wurde, samt Gebühr. Eine
Limit-Order wird oft in mehreren Teilen ausgeführt, und BSDEX rechnet jeden Teil einzeln gerundet ab. Der Export nennt je Order nur
die gerundete Summe („Gefüllt“, „Transaktionsentgelt“), die Jahreshistorie jeden Teil, aber nicht seine Order. Beide Leser ordnen
jeden Teil seiner Order zu (Zeitraum und Menge) und buchen die Summe der Teile – Trade und Euro-Bewegung haben denselben Betrag.

**Es zählt nur, was ausgeführt ist.** Der Export darf alles enthalten; gelesen wird nur das Ausgeführte, jede Orderart (Limit,
Market, Stop):

| Order laut Export | gebucht wird |
|---|---|
| ausgeführt | je Ausführungstag die Summe der Teile dieses Tages – meist ein Tag, also eine Buchung |
| storniert, aber teilweise ausgeführt | der ausgeführte Teil, ebenso je Ausführungstag |
| storniert oder offen, ohne Ausführung | nichts |
| noch offen, aber teilweise ausgeführt | noch nichts: erst, wenn sie abgeschlossen ist (ausgeführt oder storniert). Bis dahin hält sie nichts an; die Cash-Vorschau nennt sie mit Betrag, der Krypto-Import mit „Order teilweise ausgeführt und noch offen“ |

**Warum je Ausführungstag:** Steuerlich ist jeder ausgeführte Teil ein eigenes Geschäft mit eigenem Datum; Steuerjahr und
Ein-Jahres-Frist zählen nach Tagen. Eine Order, die im Dezember zur Hälfte und im Februar zu Ende ausgeführt wird, steht mit je einer
Buchung in beiden Jahren.

## Grenzen

- **Ohne passende Ausführungen wird die Order gesperrt – nie mit dem gerundeten Export-Betrag gebucht.** Der Krypto-Import zeigt
  sie offen, der Cash-Import bucht dann nichts. Beide nennen den Grund so genau wie möglich, mit Datum, Menge und Beträgen:

  | Grund | was tun |
  |---|---|
  | Historie des Jahres fehlt | die Transaktionshistorie dieses Jahres laden und ablegen (BSDEX teilt sie nach Jahren in UTC) |
  | Historie zu alt („reicht nur bis …“) | die aktuelle Historie laden und ablegen, das laufende Jahr neu |
  | keine Ausführung im Zeitraum | Export und Historie vom selben Tag laden |
  | Menge der Ausführungen passt nicht | beide Belege prüfen und von Hand buchen |
  | Betrag weicht vom Export ab | beide Beträge stehen im Grund; Belege prüfen und von Hand buchen |
  | Ausführungen nicht eindeutig | von Hand buchen |

  Weicht nur eine Order ab, läuft der Rest des Stapels weiter. „Im Editor öffnen“ füllt bei diesen Orders Datum, Coin, Konto und
  Menge vor, nie einen Betrag. Umgekehrt hält ein Teil ohne Order den Cash-Import an: Der Export ist älter als die Historie; dann den
  Export neu laden.
- Steht eine Order zum Jahreswechsel noch offen, fehlt ihr Dezember-Teil im Steuerreport des alten Jahres, bis sie abgeschlossen
  ist; dann wird er mit seinem Datum nachgebucht.
- Coin-Eingänge nennt der Export ohne Richtung; sie bekommen ihre Gegenbuchung mit dem Export des sendenden Wallets.

## Steuerunterlagen

Eine Steuerübersicht bietet BSDEX im selben Bereich wie die Downloads von Transaktionen und Historie. Sie dient als Vergleich zur
eigenen Rechnung; ablegen unter `<Jahr>/Steuer`. Gelesen wird sie nicht.
