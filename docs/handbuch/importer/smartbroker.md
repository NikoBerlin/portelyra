# Smartbroker+

| Steckbrief | |
|---|---|
| Leser | Wertpapiere „Smartbroker+ (CSV-Export und Dividendenabrechnungen)“ · Devisen „Smartbroker+ Devisenkonten (USD, CHF …)“ · Cash „Baader Bank Perioden-Kontoauszug, auch Smartbroker (PDF oder Text)“ |
| Dokumente | CSV-Export der Transaktionen; Dividendenabrechnungen und Devisenbelege (PDF); Perioden-Kontoauszüge aller Konten (PDF) |
| Zeitraum | CSV vom Kontobeginn bis heute; PDFs je Vorgang bzw. Monat |
| Deckt ab | Depot, Verrechnungskonto, Tagesgeld und die Fremdwährungskonten (USD, CHF …) |
| Geprüft | Formate Stand 10/2026 |

## Herunterladen

- Die **Transaktionen als CSV**, vom Kontobeginn bis heute. Ein kürzerer Zeitraum ab dem letzten Export geht auch; Überlappung
  schadet nicht.
- Aus dem Postfach: **Dividendenabrechnungen, Devisenbelege und die Kontoauszüge aller Konten** – Verrechnung, Tagesgeld,
  Fremdwährungskonten –, auch Auszüge ohne Bewegung. Sie belegen den Saldo.
- Kauf- und Verkaufsabrechnungen als PDF braucht es nicht, die CSV deckt sie ab (PDF-Abrechnungen als Quelle sind für später vorgesehen).
- Ein Auszug trägt das Datum des Folgemonats; der Eingang ordnet ihn dem Zeitraum zu, den er laut Inhalt abdeckt.

## Ablegen

Unterordner `Smartbroker+`, darin je Jahr ein Ordner und je Thema ein weiterer, zum Beispiel:

```
Smartbroker+/
  2026/
    Transaktionen/     CSV-Export der Transaktionen
    Abrechnungen/      Dividendenabrechnungen
      Devisen/         Devisenbelege
    Verrechnung/       Kontoauszüge des Verrechnungskontos
    Zinskonto/         Kontoauszüge des Tagesgelds
    Devisenkonten/     Kontoauszüge der Fremdwährungskonten
    Steuer/            Steuerbescheinigungen
```

Die Namen unterhalb des Instituts sind frei: Der Eingang erkennt Art, Zeitraum und Konto am Inhalt.

## Buchen

Jeweils erst prüfen, dann buchen:

1. **Wertpapiere** – Import „Wertpapier-Belege“ mit dem Leser **„Smartbroker+ (CSV-Export und Dividendenabrechnungen)“**, ausdrücklich
   gewählt oder über „Im Import buchen“ im Eingang. „Automatisch erkennen“ nimmt sonst den Scalable-Leser, weil Abrechnungen der
   Baader Bank für beide gleich aussehen. Aus der Ablage: Institut „Baader“, die Jahre seit Kontobeginn, betrachteter Zeitraum „Alle Zeiträume“.
   Stornierte Orders der CSV erscheinen als Exportzeilen ohne Buchung; Kontoauszüge und Devisenbelege als Dateien ohne Buchung –
   sie gehören zu den anderen Lesern.
2. **Devisen** – Import „Devisen-Belege“ mit dem Leser „Smartbroker+ Devisenkonten (USD, CHF …)“, dieselbe Auswahl. Er bucht den
   Zufluss aus Dividenden in Fremdwährung und den Umtausch. Vorgänge des laufenden Monats tragen „ohne Zeile im Kontoauszug“, bis
   dessen Auszug im Folgemonat abgelegt ist. Eine Dividende mit Gutschrift in Fremdwährung nennt der Eingang deshalb bei beiden
   Lesern: die Dividende bucht der Wertpapier-, den Zufluss der Devisen-Import.
3. **Cash** – Karte „Cash-Auszug importieren“, Quelle „Baader Bank Perioden-Kontoauszug, auch Smartbroker“, **je Konto ein
   Durchgang** (Verrechnung, dann Tagesgeld), Cash-Asset EUR, aus der Ablage alle Jahre seit Kontobeginn. Die Auszüge eines Kontos
   bilden eine lückenlose Kette; die CSV, die in der Ablage auch am Verrechnungskonto hängt, übergeht der Leser mit Grund.

## Grenzen

- **Baader Bank als gemeinsames Institut:** Smartbroker+ und ältere Depots von Scalable Capital laufen über die Baader Bank und
  gehören in der Ablage zum Institut „Baader“. Steuerunterlagen ohne Kontonummer erkennt der Eingang deshalb nicht; sie werden in
  der Ablage von Hand dem richtigen Depot zugeordnet.

## Steuerunterlagen

Steuerbescheinigungen der Baader Bank aus dem Postfach, ablegen unter `<Jahr>/Steuer`, in der Ablage von Hand dem Depot zuordnen.

**Erträgnisaufstellung:** Sie nennt je Verkauf und Dividende den Kapitalertrag auf den Cent, wie ihn die Bank
rechnet (nach Teilfreistellung, vor Freistellungsauftrag und Verlustverrechnung). In der Ablage als „Erträgnisaufstellung“ beim
Institut Baader ablegen, dann in Daten → „4. Steuer“ die Karte „Steuerpflichtige Beträge aus der Erträgnisaufstellung“: Ablage lesen,
die Aufstellung wählen, prüfen, mit Häkchen übernehmen.

- Übernommen wird nur, was höchstens **1 €** von der eigenen Rechnung abweicht – sonst ist es ein Befund, die eigene Rechnung bleibt
  (etwa wenn die Bank mangels Anschaffungsdaten eine Ersatzbemessungsgrundlage ansetzt). Die Summe der Posten muss Zeile 7 des
  Summennachweises ergeben, sonst übernimmt die Karte nichts.
- Die Steuer rechnet Portelyra weiter selbst; Freibetrag und Verlusttöpfe wirken nur in der Jahresrechnung. Das Rechenblatt nennt,
  dass der Betrag aus dem Beleg stammt.
- Mit dem Bankwert rechnen Rechenblätter, Jahresrechnung und der ausführliche Steuerreport sofort, ebenso die
  Steuerprojektion je Ereignis aus dem Abschluss und die Netto-Sicht der Analyse – nach dem nächsten „Alles aktualisieren“, auch
  am selben Tag.
- Die Karte zeigt nur Dokumente der Art „Erträgnisaufstellung“ und liest die Liste bei jedem Öffnen von „4. Steuer“ neu. Liegt
  die Aufstellung unter einer anderen Art, in 2. Stammdaten → Ablage mit „Art ändern“ umstellen.
- Netto gebuchte Zinsen (der Monatsauszug nennt nur den Betrag nach Steuer) hebt die Karte auf den Bruttozins der Aufstellung.
  Bewegungen bucht sie nicht.
- Kleine Rundungsunterschiede einzelner Verkäufe übernimmt die Karte ebenso; es gilt dann der Betrag der Aufstellung.
