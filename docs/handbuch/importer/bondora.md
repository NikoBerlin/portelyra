# Bondora

| Steckbrief | |
|---|---|
| Leser | Cash „Bondora Go & Grow (xlsx oder CSV)“ |
| Dokument | Kontoauszug als Excel (xlsx) oder CSV, mit Guthaben je Zeile |
| Zeitraum | vom Kontobeginn bis heute, alle Ziele |
| Deckt ab | Go & Grow (alle Ziele zusammen) |
| Geprüft | Auszugsformat Stand 10/2026 |

## Herunterladen

1. Anmelden, im linken Menü das **Kontoauszug-Symbol**.
2. **„Herunterladen“** → als **Excel**.
3. Zeitraum vom Kontobeginn bis heute, **alle Ziele** (oder ein Ziel, wenn es je Ziel ein Konto gibt).
4. Art **„Kontoauszug“**.

## Ablegen

Unterordner `Bondora`, darin je Jahr `Transaktionen`. **Der neueste Auszug gilt;** ältere dürfen liegen bleiben und stehen in der
Dateiliste als „ersetzt durch …“.

## Buchen

Karte „Cash-Auszug importieren“, Quelle „Bondora Go & Grow (xlsx oder CSV)“, Cash-Asset EUR, aus der Ablage. Der Auszug nennt
Anfangs- und Endsaldo; das Konto wird damit vollständig abgeglichen.

## Was gebucht wird

- Einzahlungen, Auszahlungen und die täglichen Zinsen („Go & Grow Zinsen“) als Ertrag.

## Eigenheit: rückwirkend neu verteilte Zinsen

Bondora verteilt die täglichen Zinsen in jedem neuen Auszug neu – schon gebuchte Tage können um einen Cent anders dastehen, im Wechsel
mehr und weniger, bei gleichem Ergebnis bis auf Cent. Der Import korrigiert solche Tage, statt sie ein zweites Mal zu buchen; die alte
Buchung bleibt als Vorgänger erhalten. Die Vorschau nennt die Zahl der Korrekturen, ihre Summe und die Abgleiche, die sich dadurch um
Cent verschieben. Gebucht wird erst, wenn Gebuchtes, Neues und Korrekturen den Endsaldo des Auszugs ergeben.

## Steuerunterlagen

Die Steuerbescheinigung („Go & Grow“-Steuerbericht je Jahr, PDF) gibt es an derselben Stelle wie den Kontoauszug: Kontoauszug-Symbol
→ „Herunterladen“ → Art **„Steuerbescheinigung“** statt „Kontoauszug“, das Jahr wählen. Ablegen unter `<Jahr>/Steuer`; der Eingang
liest das Jahr aus dem Wortlaut („01/01/2025 - 31/12/2025“).
