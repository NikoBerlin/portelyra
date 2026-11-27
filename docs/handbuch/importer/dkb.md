# DKB

| Steckbrief | |
|---|---|
| Leser | Cash „DKB Umsatzliste, Giro und Tagesgeld (CSV)“ · Cash „DKB Girokonto-Kontoauszug (PDF oder Text)“ |
| Dokumente | Umsatzliste je Konto (CSV); Kontoauszüge des Girokontos (PDF) |
| Zeitraum | Umsatzliste so weit zurück, wie die DKB sie anbietet, bis heute |
| Deckt ab | Girokonto und Tagesgeld |
| Geprüft | Formate Stand 10/2026 |

## Herunterladen

- **Quelle der Buchungen ist die Umsatzliste (CSV) je Konto**, so weit zurück, wie die DKB sie anbietet, bis heute. Überlappung
  schadet nicht.
- Die Kontoauszüge als PDF liegen im **Postfach**; sie sind Belege für die Ablage. Ältere Auszüge, die das Postfach nicht mehr
  anbietet, kosten bei der Bank Gebühr; wo sie fehlen, bleiben die Monate in „Auszüge und Belege je Konto“ offen – die Buchungen kommen aus der CSV. Zum
  Jahreswechsel gibt es beim Girokonto einen 13. Auszug.

## Ablegen

```
DKB/
  2026/
    Giro/
      Transaktionen/   Umsatzliste als CSV
      Auszüge/         Kontoauszüge als PDF
    Tagesgeld/
      Transaktionen/
      Auszüge/
    Steuer/            Jahressteuerbescheinigung, Erträgnisaufstellung
```

Jeder Auszug gehört dem Konto, dessen Nummer er im Dateinamen und im Kopf trägt; die CSV hängt an ihrem Konto.

## Buchen

Karte „Cash-Auszug importieren“, Quelle **„DKB Umsatzliste, Giro und Tagesgeld (CSV)“**, Cash-Asset EUR, **je Konto ein Durchgang**
aus der Ablage ab dem ersten Jahr der CSV. Die PDF-Auszüge am Konto übergeht der Leser mit Grund. Der Leser „DKB
Girokonto-Kontoauszug“ ist für Zeiträume ohne CSV gedacht; er prüft die Auszüge als lückenlose Kette und bucht nichts, wenn einer fehlt.

Ein neuer Export, der sich mit dem abgelegten überschneidet (etwa ab Jahresbeginn bis heute), gilt ab seinem ersten Tag; der ältere zählt
nur bis davor. Beide bleiben in der Ablage. Voraussetzung: Am ersten Tag des neuen ergeben beide denselben Kontostand, sonst meldet der
Import eine Lücke.

## Was gebucht wird

- „-2.000“ in der Umsatzliste sind zweitausend Euro; den Saldo belegen die Quartalsabrechnungen („Kontostand am“). Auf dem Tagesgeld
  ist die Zinsabrechnung netto.

## Steuerunterlagen

Jahressteuerbescheinigung und Erträgnisaufstellung liegen im **Postfach**; ablegen unter `<Jahr>/Steuer`.
