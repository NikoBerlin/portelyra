# Trade Republic

| Steckbrief | |
|---|---|
| Leser | Wertpapiere „Trade Republic (CSV-Export)“ · Cash „Trade Republic Transaktionsexport (CSV)“ |
| Dokument | CSV-Export „Transaktionen“ aus der App; Kontoauszug als PDF-Beleg |
| Zeitraum | vom Kontobeginn bis heute |
| Deckt ab | Depot und Verrechnungskonto in einer Datei |
| Geprüft | Exportformat Stand 10/2026 (Zeiten in UTC) |

## Herunterladen

Aus der **App** den CSV-Export „Transaktionen“ vom Kontobeginn bis heute; den Kontoauszug (PDF) als Beleg dazu. Eine Abrechnung zur
Vorabpauschale gibt es bei Trade Republic nicht: Export und Kontoauszug nennen nur die einbehaltene Steuer („Vorabpauschale for ISIN …“).

## Ablegen

Unterordner `Trade Republic`, darin je Jahr `Transaktionen` für den CSV-Export und `Steuer` für Jahressteuerbescheinigung und Belege zur
Vorabpauschale. Der Eingang schlägt den Export für Depot und Verrechnungskonto vor; Kopien in mehreren Jahresordnern erkennt er als doppelt.

## Buchen

Jeweils erst prüfen, dann buchen:

1. **Wertpapiere** – Import „Wertpapier-Belege“ mit dem Leser **„Trade Republic (CSV-Export)“**, aus der Ablage Institut „Trade Republic“,
   „Alle Zeiträume“. Ohne Buchung bleiben mit Grund Kontobewegungen (für den Cash-Import), Steuerzeilen, aufgehobene Dividenden – und
   **Zeichnungen (IPO) sowie Einlieferungen: diese von Hand buchen** (Kauf zum Zuteilungstag mit dem zugeteilten Betrag, also Zeichnung
   abzüglich Erstattung).
2. **Cash** – Karte „Cash-Auszug importieren“, Quelle „Trade Republic Transaktionsexport (CSV)“, Konto Verrechnung, aus der Ablage.
   Zinsen erkennt der Leser als Ertrag.

## Was gebucht wird

- Eine Sparplan-Ausführung steht im Export als zwei Zeilen (ganze Stücke und Bruchteil, gleiche Zeit und gleicher Kurs) und wird eine
  Buchung.

## Grenzen

- **Vorabpauschalen:** Der Leser prüft sie gegen Daten → Steuer. Ohne Betrag im Export warnt er, wenn der eingetragene Wert nicht zur
  einbehaltenen Steuer passt – nicht die Steuer eintragen. Ohne Beleg den Betrag aus der Steuer zurückrechnen: bei einem Aktienfonds
  (30 % Teilfreistellung), ohne Kirchensteuer und bei voll einbehaltener Steuer ist die Vorabpauschale Steuer ÷ (0,7 × 26,375 %) – auf
  wenige Cent genau, weil die Bank je Schritt rundet. Ob Kirchensteuer einbehalten wurde und der Freistellungsauftrag galt, zeigt die
  Jahressteuerbescheinigung.

## Steuerunterlagen

Jahressteuerbescheinigung aus der App, ablegen unter `<Jahr>/Steuer`.
