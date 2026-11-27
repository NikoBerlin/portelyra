# Portfolio-Snapshot v4

Unveraenderliches Stichtagsbild des Portfolios mit Frische je Ebene - und seit
dieser Fassung mit dem **belegten Cash-Bestand**.

## Warum eine vierte Fassung

v3 fuehrte Cash nur als Ebene der Frische: ob Zeitraeume erklaert sind, nicht
wie viel. Die Hoehe des Cash-Bestandes stand nirgends im Snapshot. v4 traegt sie.

## Der Cash-Block

`cash.accounts` fuehrt jedes Cash-Konto mit einem erklaerten Zeitraum:

- `balance_decimal` und `balance_date`: der belegte Saldo und der Tag, von dem
  er stammt. Ein abgestimmtes Konto ist bis zum Tag seiner Abstimmung belegt;
  liegt der Stichtag danach, gilt der Saldo vom Abstimmungstag
  (`reconciled_before_as_of`), sonst der aus Anfangssaldo und Bewegungen bis
  zum Stichtag gerechnete (`reconciled_at_as_of`).
- `in_total: false` heisst: Das Konto traegt keinen Saldo und steht ausserhalb
  der Summe - nur Bewegungen (`movements_only`), am Stichtag noch nicht gefuehrt
  (`not_covered_yet`), mehrere Zeitraeume ohne eindeutigen Saldo
  (`periods_ambiguous`) oder eine Fremdwaehrung ohne Wechselkurs am Stichtag
  (`currency_without_rate`). **Fehlendes Cash ist niemals null.**
- `balance_target_decimal`: der Saldo in der Zielwaehrung, umgerechnet mit dem
  Faktor, den der Bewertungsstand am Stichtag fuer dieselbe Waehrung verwendet.

`cash.dated_before_as_of` sagt, ob mindestens ein gezaehlter Saldo aelter ist als
der Stichtag; `oldest_balance_date` und `newest_balance_date` nennen die Spanne.

## Summen

- `totals.cash_balance_decimal`: Summe der gezaehlten Salden in der
  Zielwaehrung; `null`, wenn kein Konto einen Saldo traegt.
- `totals.net_worth_decimal`: Marktwert plus Cash. Es wird ausgewiesen, auch wenn
  Cash-Salden aelter sind als der Stichtag - die Anzeige kennzeichnet das, und der
  Block darunter nennt je Konto das Datum.

## Was sich an `snapshot_status` nicht aendert

Cash bleibt nachrichtlich: `complete` haengt weiterhin an den tragenden Ebenen
und den gehaltenen Positionen, nicht am Alter der Cash-Salden.

## Positionen und Ausschluesse (seit rc.237, unveraendert gegenueber v3)

- Ein Asset mit eigener Bewertung (`manual`) steht in `positions`: juengste
  eigene Kursangabe bis zum Stichtag, sonst letzter bestaetigter
  Trade-Stueckpreis; `price_basis`, `price_source_date` und `price_age_days` sagen
  woher und von wann. Laesst sich kein Wert herleiten, steht es als Luecke in
  `excluded_positions`.
- `owner_excluded: true` traegt nur noch, was der Eigentuemer bewusst ohne Wert
  fuehrt (`transaction_only`).

## Exakte Betraege

Betraege stehen ungerundet. Was nicht endlich dezimal darstellbar ist, steht als
exakter Bruch `Zaehler/Nenner`. Gerundet wird ausschliesslich in der Anzeige.
