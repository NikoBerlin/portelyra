# Portfolio-Snapshot v3

Unveraenderliches Stichtagsbild des Portfolios mit **Frische je Ebene**.

## Warum eine dritte Fassung

v1/v1.1/v2 verlangen `cash_balances` mit mindestens einem Eintrag. Ein nicht
erklaerter Cash-Bestand waere damit entweder eine Sperre oder eine Null — beides
falsch. In v3 ist Cash eine Ebene der Frischematrix und darf `not_requested`
sein.

Dazu kommt der eigentliche Anlass (#373): Die bisherige Frischepruefung des
Abschlusses war **ein** Fingerabdruck ueber die gesamten Kurs- und FX-Speicher.
Jeder Abruf fuer irgendein Asset entwertete den Lauf jedes anderen; so waren
alle abgeschlossenen Laeufe dauerhaft
`stale`, und ein erreichbarer Zustand "alles aktuell" existierte nicht. v3
traegt stattdessen die Frische je Ebene, wie sie der Bewertungsstand je Bereich
fuehrt.

## Zwei Statusfelder, die nicht dasselbe meinen

- `status` ist das Feld der Publikationshuelle: Der Lauf ist abgeschlossen.
  Es ist immer `completed`, sonst wird nicht veroeffentlicht.
- `snapshot_status` ist die fachliche Aussage: `complete` nur, wenn jede Ebene
  vollstaendig ist und jede gehaltene Position einen Marktwert hat. Sonst
  `partial`. Ein teilweiser Lauf veroeffentlicht keinen gemischten
  "vollstaendig"-Status.

## Was nicht in den Marktwert eingeht

`excluded_positions` fuehrt zwei verschiedene Faelle, unterschieden durch
`owner_excluded`:

- **Eigentuemerwahl** (`owner_excluded: true`): Bewertungsmethode `manual`.
  Kein Mangel, eine Entscheidung.
- **Luecke** (`owner_excluded: false`): Es fehlt ein bewerteter Kurstag oder
  ein Bewertungsbereich. Dann ist `snapshot_status` hoechstens `partial`.

Beide tragen gegebenenfalls einen aus Buchungen hergeleiteten Wert. Der sagt,
was gezahlt wurde, nicht was der Markt am Stichtag bot, und fliesst bewusst
**nicht** in `totals.market_value_decimal`.

## Exakte Betraege

Betraege stehen ungerundet. Was nicht endlich dezimal darstellbar ist, steht als
exakter Bruch `Zaehler/Nenner`. Gerundet wird ausschliesslich in der Anzeige.

## Seit rc.237 (11.10.2026)

Zwei Aussagen oben gelten nicht mehr: Ein Asset mit eigener Bewertung (`manual`)
steht in `positions` und zaehlt in `totals.market_value_decimal` - mit
`price_basis`, `price_source_date` und `price_age_days`. `owner_excluded: true`
traegt nur noch `transaction_only`. Das Schema liess beides schon zu. Neue
Snapshots entstehen in Fassung 4 (`../v4/README.md`).
