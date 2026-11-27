# Revolut

| Steckbrief | |
|---|---|
| Leser | Cash „Revolut Girokonto (CSV)“ und „Revolut Sparkonto/Tagesgeld (CSV)“ |
| Dokument | Kontoauszug „All accounts“ als CSV (`account-statement_<von>_<bis>_….csv`) |
| Zeitraum | vom Kontobeginn bis heute |
| Deckt ab | Girokonto und Sparkonto in einer Datei, getrennt über die Spalte „Product“ (Current, Deposit) |
| Geprüft | Exportformat Stand 10/2026 |

## Herunterladen

1. Im Web anmelden, auf **„Home“** → **„Statement“**.
2. Format **„Excel“** wählen – heruntergeladen wird eine CSV.
3. Zeitraum vom Kontobeginn bis heute → **„Generate“** („All accounts“).

## Ablegen

Unterordner `Revolut`, darin je Jahr `Transaktionen`. Der Eingang schlägt die Datei für beide Konten vor, über den ganzen Zeitraum.
Ein neuer Export ersetzt den älteren; beide dürfen liegen bleiben.

## Buchen

Karte „Cash-Auszug importieren“, Cash-Asset EUR, **je Konto ein Durchgang** aus der Ablage – dieselbe Datei, aber jeweils der Leser
des Kontos: Girokonto mit „Revolut Girokonto (CSV)“, Sparkonto mit „Revolut Sparkonto/Tagesgeld (CSV)“. Wählt man den falschen
Leser zum Konto, hält die Saldoprüfung an.

## Was gebucht wird

- Jede abgeschlossene Zeile („COMPLETED“) des Produkts, mit dem Saldo je Zeile als Beleg; das Konto wird damit vollständig
  abgeglichen.
- Zinsen auf dem Sparkonto: „Amount“ ist der Zins nach Steuer, „Fee“ die einbehaltene Steuer. Gebucht wird der Bruttozins als Ertrag
  und der Nettobetrag als Zufluss. Zehrt die Steuer den ganzen Zins auf, gibt es keine Bewegung; die Zeile wird gezählt, aber nicht
  gebucht.

## Steuerunterlagen

Die Jahresübersicht („Consolidated statement“, PDF) ablegen unter `<Jahr>/Steuer`. Wo Revolut sie bereitstellt, beschreibt dieses
Handbuch noch nicht; im Zweifel beim Revolut-Support anfragen.
