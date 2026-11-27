# ING

| Steckbrief | |
|---|---|
| Leser | Wertpapiere „ING Direkt-Depot“ · Cash „ING Kontoauszug, Giro und Extra-Konto (PDF oder Text)“ |
| Dokumente | Wertpapier- und Ertragsabrechnungen (PDF); Kontoauszüge von Girokonto und Extra-Konto (PDF) |
| Zeitraum | je Vorgang bzw. Auszug, aus der Post-Box |
| Deckt ab | Direkt-Depot, Girokonto und Extra-Konten |
| Geprüft | Formate Stand 10/2026 |

## Herunterladen

Alles liegt in der **Post-Box** (Postfach) – Abrechnungen, Kontoauszüge und Steuerunterlagen. Jeweils alles Neue:

- Wertpapierabrechnungen und Ertragsabrechnungen – Dividenden, Ausschüttungen und Vorabpauschalen.
- Kontoauszüge des Girokontos (monatlich, Anfang des Folgemonats) und der Extra-Konten (jährlich, im Januar für das Vorjahr).
- Jahressteuerbescheinigung und Erträgnisaufstellung (im März für das Vorjahr).
- Entgeltaufstellung, Info-Schreiben und Bestandsveränderungen (Split, Abspaltung) gehören nach `<Jahr>/Sonstiges`.
- Verlustverrechnungen braucht es nicht; wer sie ablegen will, legt sie nach `Steuer` (dort gilt der Tag aus dem Inhalt).

## Ablegen

```
ING/
  2026/
    Transaktionen/     Abrechnungen Kauf/Verkauf, Ertragsabrechnungen
    Cash/
      Giro/            Kontoauszüge des Girokontos
      Extra-Konto/     Kontoauszüge je Extra-Konto
    Steuer/            Jahressteuerbescheinigung, Erträgnisaufstellung
    Sonstiges/         Entgeltaufstellung, Info-Schreiben, Bestandsveränderungen
```

Ein Giro-Auszug, der eine Umbuchung auf ein Extra-Konto nennt, gehört nur dem Girokonto.

## Buchen

Jeweils erst prüfen, dann buchen:

1. **Wertpapiere** – Import „Wertpapier-Belege“ mit dem Leser **„ING Direkt-Depot“**, aus der Ablage Institut „ING“, die Jahre seit
   Kontobeginn, „Alle Zeiträume“. Vorabpauschalen erscheinen als eigene Zeile. Kontoauszüge, Steuerunterlagen und „Sonstiges“
   erscheinen als Dateien ohne Buchung.
2. **Cash** – Karte „Cash-Auszug importieren“, Quelle „ING Kontoauszug, Giro und Extra-Konto (PDF oder Text)“, Cash-Asset EUR, **je
   Konto ein Durchgang**: Girokonto, dann jedes Extra-Konto. Die Auszüge eines Kontos bilden eine lückenlose Kette. Ein
   Extra-Konto-Auszug gilt vom Tag der ersten bis zur letzten Buchung des Jahres; fürs laufende Jahr gibt es ihn erst im Januar.

## Was gebucht wird

- Teilausführungen einer Order prüft der Leser gemeinsam; Stückzahlen vor einem Split erkennt er split-bereinigt.

## Steuerunterlagen

Jahressteuerbescheinigung und Erträgnisaufstellung aus der Post-Box (im März für das Vorjahr), ablegen unter `<Jahr>/Steuer`. Der
Eingang liest das Jahr aus dem Wortlaut und ordnet sie den Konten zu, deren Nummer sie nennen.
