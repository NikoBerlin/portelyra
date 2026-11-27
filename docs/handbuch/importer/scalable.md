# Scalable Capital

| Steckbrief | |
|---|---|
| Leser | Wertpapiere „Scalable Capital (auch Baader-Abrechnungen für Scalable)“ · Cash „Scalable Capital Verrechnungskonto“ und „Scalable Capital Tagesgeld“ (PDF oder Text) |
| Dokumente | Wertpapierabrechnungen, Wertpapierereignisse und Vorabpauschalen (PDF); monatliche Kontoauszüge (PDF) |
| Zeitraum | je Vorgang bzw. Monat, aus dem Postfach |
| Deckt ab | Depot, Verrechnungskonto und Tagesgeld |
| Geprüft | Formate Stand 10/2026 |

## Herunterladen

Aus dem **Postfach**, jeweils alles Neue: Wertpapierabrechnungen (Kauf, Verkauf), Wertpapierereignisse (Dividenden), die monatlichen
Kontoauszüge von Verrechnung und Tagesgeld (Anfang des Folgemonats), die Vorabpauschalen je Fonds (Anfang Januar für das Vorjahr) und
die Steuerbescheinigung (April für das Vorjahr). Schickt
Scalable zu einem Monat einen „Korrektur“-Auszug, darf er neben dem ursprünglichen liegen: Mit denselben Buchungen gilt er als Duplikat.

## Ablegen

```
Scalable/
  2026/
    Transaktionen/
      Käufe/           Wertpapierabrechnungen
      Verkäufe/
      Dividenden/      Wertpapierereignisse
      Vorabpauschale/  Vorabpauschale je Fonds
    Verrechnung/       monatliche Kontoauszüge Broker
    Tagesgeld/         monatliche Kontoauszüge Tagesgeld
    Steuer/            Steuerbescheinigung
    Sonstiges/         Einlieferungsbeleg, Steuerkorrektur und andere Schreiben
```

Dividendenabrechnungen gehören zum Depot, Auszüge zu Verrechnung bzw. Tagesgeld; der Cash-Leser nimmt nur Auszüge mit Kontostand.

## Buchen

Jeweils erst prüfen, dann buchen:

1. **Wertpapiere** – Import „Wertpapier-Belege“ mit dem Leser **„Scalable Capital (auch Baader-Abrechnungen für Scalable)“**, aus der
   Ablage Institut „Scalable“, die Jahre seit Kontobeginn, „Alle Zeiträume“. Abrechnungen aus der Baader-Zeit eines Scalable-Depots
   gleicht der Leser mit diesem Depot ab. Vorabpauschalen stehen als eigene Zeilen darunter: „neu“ trägt „Vorabpauschalen
   übernehmen“ ein, „weicht vom Beleg ab“ ersetzt es nur mit dem Häkchen dafür (wie bei ING).
2. **Cash** – Karte „Cash-Auszug importieren“, Cash-Asset EUR, **je Konto ein Durchgang**: Verrechnung mit „Scalable Capital
   Verrechnungskonto“, Tagesgeld mit „Scalable Capital Tagesgeld“. Beide lesen dieselbe Vorlage; im Eingang steht deshalb bei jedem
   Auszug „Tagesgeld“ als Leser, das Konto stimmt.

## Was gebucht wird

- Zinsen stehen brutto im Auszug („Erhaltene Zinsen“); Kapitalertragsteuer und Solidaritätszuschlag sind eigene Zeilen.
- Der Kontostand am Periodenbeginn: bis September 2026 der Stand am Ende des ersten Tages (dessen Buchungen schon darin), seit Oktober
  2026 der Stand davor. Der Leser nimmt die Lesart, mit der der Auszug aufgeht; geht er mit keiner auf, meldet die
  Vorschau ihn als nicht stimmig.
- **Vorabpauschale:** eingetragen wird der Betrag vor Teilfreistellung („Gewinn oder Verlust“, vorn in der Spalte „Vorabpauschale“),
  für das Jahr „Angefallen im“, zugeflossen am Ex-Tag. Vorn und hinten müssen gleich sein, und „Zu versteuern“ muss der Betrag ohne die
  Teilfreistellung sein – sonst bekommt der Beleg einen Grund statt einer Zahl. Der Beleg nennt kein Depot; der Leser ordnet ihn
  dem Scalable-Depot des Portfolios zu. Die einbehaltene Steuer bucht der Cash-Import vom Verrechnungskonto (Steuerabbuchung).

## Steuerunterlagen

Die Steuerbescheinigung ohne Kontonummer erkennt der Eingang nicht, weil Belege von Scalable und Baader-Belege für Scalable denselben Namen tragen;
sie wird in der Ablage von Hand dem Depot zugeordnet.
