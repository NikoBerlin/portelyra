# Portfolio-Snapshot v5

Unveraenderliches Stichtagsbild des Portfolios mit Frische je Ebene und dem
Cash-Bestand je Konto - seit dieser Fassung auch dort, wo kein Auszug einen
Saldo bestaetigt: als **abgeleiteter Saldo**, benannt und eigens ausgewiesen.

## Warum eine fuenfte Fassung

v4 fuehrte ein Konto, das nur Bewegungen traegt, ohne Betrag ausserhalb der
Summe. Cash-Summe und Gesamtvermoegen blieben um sie zu klein. Der fehlende
Saldo wird jetzt berechnet, mit dem Hinweis, dass er abgeleitet und nicht durch
den Auszug selbst validiert ist.

## Der abgeleitete Saldo

Fuer ein Konto mit genau einem erklaerten Zeitraum ohne abgestimmten Saldo, das
nur Ein- und Auszahlungen fuehrt:

- Saldo = Summe der Bewegungen bis zum Stichtag. Nennt der Zeitraum einen nicht
  abgestimmten Anfangsbestand, ist er der Ausgangspunkt, sonst null.
- `balance_status` ist `derived_at_as_of`, wenn die Bewegungen bis zum Stichtag
  reichen, sonst `derived_before_as_of`; `balance_date` ist dann der Tag der
  letzten gebuchten Bewegung.
- `derived_from_date` nennt den Tag, ab dem summiert ist. **An ihm haengt die
  Annahme: Davor war das Konto leer.** Lag dort schon Geld, ist der Saldo um
  genau diesen Betrag zu niedrig - das sieht keine Rechnung. Ob der Tag die
  Kontoeroeffnung ist oder nur der Beginn eines Exports, weiss der Eigentuemer.
  Bei jedem anderen Konto ist das Feld `null`.
- Faellt die Summe an einem Tagesende unter null, ist die Annahme vom Bestand
  selbst widerlegt: `movements_sum_negative`, kein Betrag, nicht in der Summe.
  **Fehlendes Cash ist niemals null** - ein abgeleiteter Saldo von null dagegen
  ist ein Rechenergebnis und zaehlt.

Ein abgeleiteter Saldo zaehlt in `totals.cash_balance_decimal` und
`totals.net_worth_decimal`. Damit die Summe ohne ihn nachrechenbar bleibt:

- `cash.derived_account_count`: wie viele der gezaehlten Konten abgeleitet sind.
- `totals.cash_derived_balance_decimal`: ihr Anteil an der Cash-Summe in der
  Zielwaehrung; `null`, wenn kein Konto abgeleitet ist.

Wer einen Kontostand aus einem Auszug nachtraegt, macht aus dem abgeleiteten
einen belegten Saldo (`reconciled_*`).

## Vorlaeufiger Cash-Stand (seit 0.2.0-rc.362, #539)

Cash kommt mit dem Monatsauszug, Wertpapiere kommen mit den Abrechnungen. Damit das
Bild zwischen zwei Auszuegen nicht nach einem Kauf zu viel und nach einem Verkauf
zu wenig zeigt, steht neben dem amtlichen Stand ein vorlaeufiger - angezeigt, nie
gebucht. Die Felder sind optional; Staende vor rc.362 tragen sie nicht.

- je Konto `provisional_balance_decimal`: amtlicher Saldo plus die Bewegungen nach
  `balance_date` plus die Abrechnungen der Depots, die nachweislich auf dieses Konto
  abrechnen und noch keiner Auszugszeile zugeordnet sind (Kauf mit Kurswert und
  Gebuehr, Verkauf mit Erloes nach Gebuehr und vor Steuer, Dividende mit dem
  gebuchten Betrag). `null`, wo nichts offen ist. Nur Euro-Konten in der Summe,
  nicht auf geschlossenen oder ruhenden Konten.
- `provisional_settlement_count`, `provisional_movement_count`: was eingerechnet ist.
- `provisional_unestimated_count`: offene Abrechnungen eines Kontos, dessen letzter
  Auszug mehr als 62 Tage vor dem Stichtag liegt - sie werden nicht geschaetzt.
  Gebuchte Bewegungen nach dem Auszug zaehlen auch dort; sie sind Tatsachen.
- `cash.provisional_status`: `available`, `none` (nichts offen) oder `unavailable`
  (Zuordnung nicht lesbar - das Bild bleibt vollstaendig, nur ohne Schaetzung);
  dazu die Zaehler je Block.
- `totals.cash_provisional_balance_decimal`, `totals.net_worth_provisional_decimal`:
  die Summen mit den vorlaeufigen Salden; `null` ohne Schaetzung.

Die amtlichen Felder bleiben unveraendert. Umbuchungen zwischen eigenen Konten
erscheinen erst mit dem Auszug - die Verteilung kann abweichen, die Summe nicht.

## Unveraendert gegenueber v4

Der uebrige Cash-Block (`balance_decimal`, `balance_date`, `in_total`,
`balance_target_decimal`, `dated_before_as_of`, die Spanne der Saldodaten), die
Positionen, die Ausschluesse und `snapshot_status`: Cash bleibt nachrichtlich und
macht den Snapshot nicht unvollstaendig. Der Leser nimmt die Fassungen 3 und 4
weiter an.

## Exakte Betraege

Betraege stehen ungerundet. Was nicht endlich dezimal darstellbar ist, steht als
exakter Bruch `Zaehler/Nenner`. Gerundet wird ausschliesslich in der Anzeige.
