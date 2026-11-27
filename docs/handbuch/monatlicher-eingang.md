# Monatlicher Eingang

Der Eingang bringt die Belege eines Monats mit wenigen Klicks in die Ablage und von dort in die Importe.
Er arbeitet mit einem **Belegordner außerhalb von Portelyra**. Portelyra liest diesen Ordner nur und ändert keine Datei darin.

## Einmal einrichten

1. Einen Ordner anlegen, etwa `Belege`, mit einem **Unterordner je Institut**. Die Unterordner heißen wie das Institut,
   zum Beispiel `Scalable`, `ING` oder `Trade Republic`; Groß- und Kleinschreibung, Leer- und Satzzeichen zählen nicht.
   Ein Name, der mit dem Institut beginnt, geht auch („Baader_Depot“, „ING-Depot“). Innerhalb eines Instituts sind beliebig
   tiefe Unterordner erlaubt, etwa `Smartbroker+/2026/Abrechnungen/Devisen`; das Institut bestimmt nur die erste Ebene. Im ganzen
   Belegordner dürfen höchstens 10.000 Dateien liegen – ältere, schon abgelegte Jahre lassen sich herausnehmen, die Ablage hat sie.
2. Daten → Assets pflegen → Transaktionen → **Eingang**: den Ordner wählen („Ordner wählen …“ oder den vollständigen Pfad
   eintragen) und „Als Belegordner festlegen“. Der Ordner darf nicht im Datenraum liegen. Den Belegordner können Sie auch schon im
   Einrichtungsdialog angeben, bei der Frage nach Ihren Instituten.

## Jeden Monat

1. **Herunterladen** – je Institut das, was sein Rezept nennt (Tabelle unten), und in seinen Unterordner legen.
2. **Eingang prüfen** – liest den Ordner und zeigt je Institut: *neu*, *schon abgelegt*, *doppelt im Ordner* oder
   *nicht erkannt* mit Grund. Es wird nichts geschrieben.
3. **Neue Dateien ablegen** – je Institut ein Klick. Abgelegt wird genau, was die Prüfung gezeigt hat; kam inzwischen eine Datei
   dazu, legt der Eingang nichts ab und bittet um eine neue Prüfung. Die Dateien werden unverändert in die Ablage kopiert, die im
   Backup liegt. Umbenennen, Verschieben oder Löschen im Belegordner schadet danach nicht – der Eingang erkennt jede Datei an
   ihrem Prüfwert.
4. **Im Import buchen** – der Knopf des Lesers öffnet den passenden Import. Dort „… oder Dateien aus der Ablage nehmen“
   aufklappen, das Institut wählen, übernehmen, prüfen und buchen – mit Vorschau und Bestätigung wie bei jedem Import.
5. **Offene Monate ansehen** – 2. Stammdaten → Ablage → „Auszüge und Belege je Konto“ zeigt je Konto und Monat, was belegt ist. Einen
   Monat decken Kontoauszug, Depotauszug, Transaktionsexport und Abrechnung; Jahresdokumente (Jahressteuerbescheinigung,
   Erträgnisaufstellung, Vorabpauschale) und *Sonstiges* liegen in der Ablage und im ZIP des Steuerjahres, decken aber keinen Monat
  . Die Liste „Dokumente im Jahr …“ zeigt das oben gewählte Institut und lässt sich nach Art filtern; „Art
   ändern“ stellt ein falsch eingeordnetes Dokument um, ohne es zurückzuziehen. Beim Hinterlegen springt der Zeitraum mit dem
   gewählten Jahr auf Januar bis Dezember. Danach „Alles aktualisieren“ oder den täglichen Lauf abwarten.
   Zwischen zwei Auszügen zeigt Portelyra hinter dem Cash einen vorläufigen Stand in Klammern; was er enthält und was nicht, steht in
   [Wie aktuell ist der Gesamtstand?](aktueller-stand.md).

Nicht erkannte Dateien bleiben im Belegordner liegen. Sie lassen sich in der Ablage mit eigenen Angaben hinterlegen oder in einen
Ordner „Sonstiges“ verschieben (unten).

Ein Kontoauszug gehört genau einem Konto. Nennt er bei einer Umbuchung die Nummer eines zweiten eigenen Kontos, gilt die Nummer
im Dateinamen, sonst die zuerst stehende – die im Kopf des Auszugs. Nimmt der Cash-Import aus der Ablage
eine Datei mit, die kein Auszug seiner Quelle ist, übergeht er sie und nennt sie, statt den ganzen Stapel abzulehnen.

## Zurückgezogene Dateien erneut ablegen

Eine in der Ablage zurückgezogene Datei schlägt der Eingang nicht wieder vor; sie steht als *abgelegt, zurückgezogen* in der Liste.
So taucht eine bewusst entfernte Datei nicht jeden Monat neu auf. Wer Dateien zurückgezogen hat, um sie sauber neu abzulegen, setzt
das Häkchen **„Zurückgezogene Dateien erneut vorschlagen“** und drückt „Eingang prüfen“. Der Eingang schlägt für sie Zeitraum und
Konto vor wie für neue Dateien; „ablegen“ nennt, wie viele davon erneut abgelegt werden. Die alten Einträge bleiben zurückgezogen,
die neuen kommen dazu.

## Steuerunterlagen

Steuerbescheinigungen, Erträgnisaufstellungen, Verlustbescheinigungen und Steuerberichte nennen ihr Jahr im Wortlaut („für das
Kalenderjahr 2024“). Der Eingang nimmt dieses Jahr als Zeitraum, bei einer Verlustverrechnung den Monat ihres Tages. Zugeordnet
werden die Konten des Instituts, deren Nummer die Unterlage nennt – eine Nummer bei einer anderen Bank, etwa das Referenzkonto,
zählt nicht. Nennt sie keine Nummer, gehört sie zu allen Konten des Instituts laut Institutsangabe am Konto. Ausgenommen sind
**Baader, Smartbroker+ und Scalable**: Smartbroker+ und ältere Depots von Scalable Capital laufen über die Baader Bank, neuere führt
Scalable selbst. Ihre Steuerunterlagen ohne Kontonummer bleiben *nicht erkannt* und werden in der Ablage von Hand hinterlegt.
Ein Schreiben, das nur auf „das vergangene Steuerjahr“ verweist, hat kein Jahr und bleibt ebenfalls offen.
Ein Zeitraum mit Schrägstrichen gilt in beiden Schreibweisen, „31/12/2025“ wie „12/31/2025“ (Bondora); welche gemeint ist, zeigt
ein Teil über 12. Eine Entgeltaufstellung ist *Sonstiges*, kein Kontoauszug.

## Ordner „Sonstiges“

Was der Eingang falsch oder gar nicht liest, ordnen Sie selbst ein: Ein Ordner **`Sonstiges` unter einem Jahr**, etwa
`ING/2024/Sonstiges`, nimmt allgemeine Unterlagen auf – Info-Schreiben, Kontoeröffnung, Bestandsveränderungen. Jede Datei darin ist
*Sonstiges* dieses Jahres, ohne Leser; kein Import nimmt sie. Zugeordnet werden die Konten wie bei einer Steuerunterlage: die des
Instituts, deren Nummer sie nennt, sonst alle des Instituts (nicht bei Baader, Smartbroker+ und Scalable – dort bleibt sie ohne
Kontonummer offen). Ein Ordner `Sonstiges` ohne Jahr darüber ist ein gewöhnlicher Ordner.

## Ordner „Vorabpauschalen“

Ein Ordner **`Vorabpauschalen` unter einem Jahr**, etwa `Trade Republic/2025/Vorabpauschalen`, macht jede Datei darin zur Art
*Vorabpauschale*. Das Jahr ist das des **Zuflusses**, wie bei den Lesern: Die Vorabpauschale für das
Berechnungsjahr 2024 fließt am ersten Werktag 2025 zu und gehört in den Ordner 2025. Anders als bei *Sonstiges* lesen die Leser die
Datei trotzdem; erkennt einer sie, gelten sein Zeitraum und seine Konten, und Betrag und Übernahme bleiben beim Wertpapier-Import.
Erkennt keiner sie, gilt sie für Januar des Ordnerjahres und für die Konten wie bei einer Steuerunterlage. ING- und
Scalable-Belege brauchen den Ordner nicht: Ihr Leser erkennt die Vorabpauschale am Inhalt und setzt die Art selbst.

## Zeitraumregeln

Die Regel je Rezept ist der Hebel gegen die Verschiedenheit der Belege:

- **Vom Kontobeginn**: Export mit freiem Zeitraum: immer vom Kontobeginn bis heute. Überlappung schadet nicht – schon Gebuchtes erkennt der Leser.
- **Je Monat**: Monats-PDFs: die Dokumente des neuen Monats. Was schon in der Ablage liegt, erkennt der Eingang am Prüfwert.
- **Je Vorgang**: Je Vorgang ein PDF (Abrechnung, Dividende): alle neuen aus dem Postfach. Schon Abgelegtes erkennt der Eingang am Prüfwert.
- **Abgeschlossen**: Keine neuen Auszüge mehr: Das Institut ist abgeschlossen; alte Belege lassen sich weiter ablegen und lesen.
- **Von Hand**: Kein Leser: Belege nur ablegen, Buchungen von Hand erfassen.

**Der neueste Export gilt.** Liegen mehrere Exporte „vom Kontobeginn“ eines Kontos in der Ablage, nimmt der
Cash-Import den neuesten; ältere stehen in der Dateiliste als „ersetzt durch …“ und halten nichts an. Nennt der neueste einen
schon gebuchten Tag anders – Bondora verteilt die Tageszinsen rückwirkend neu –, wird dieser Tag korrigiert statt ein zweites Mal
gebucht; die alte Buchung bleibt als Vorgänger erhalten. Die Vorschau nennt die Zahl der Korrekturen und Abgleiche, die sich
dadurch um Cent verschieben. Bevor sie einen Abgleich vorschlägt, prüft sie, ob Gebuchtes, Neues und Korrekturen den Endsaldo des
Auszugs ergeben; sonst bucht sie nichts und nennt den ersten gebuchten Tag, den der Auszug nicht kennt. **Je Konto eine Datei:**
Ein Export über mehrere Konten (C24 „Alle Konten“) bucht nichts.

## Konto geschlossen seit …

In der Ablage (2. Stammdaten → Ablage → „Auszüge und Belege je Konto“) lassen sich angehakte Konten als **geschlossen seit einem Tag**
markieren. Ab dem Monat danach erwartet die Ablage keine Auszüge mehr (Raster: ⊘), und der Eingang nimmt das Konto nicht mehr an.
Buchungen und Belege davor bleiben, wie sie sind. „Für die angehakten Konten gibt es keine Auszüge“ bleibt für Konten, die nie
Auszüge haben – etwa Sachwerte ohne Bank oder Verwahrstelle.

Daneben lässt sich ein Konto **inaktiv seit einem Tag** setzen: vorübergehend. Bestand und Buchungen zählen
weiter; Eingang und Importe bieten das Konto nicht an, bis es wieder aktiviert ist.

Schließen, Ruhen und „keine Auszüge“ wirken erst mit dem Häkchen darüber („Ja, …“), und das Datum ist anfangs leer. Ein Klick allein ändert nichts; die Meldung nennt die Konten, die geändert wurden. Zurücknehmen geht jederzeit mit den
Knöpfen daneben.

## Abläufe je Institut

Wie man bei einem Institut herunterlädt, was wohin abgelegt wird, in welcher Reihenfolge gebucht wird und wo die Grenzen der Leser
liegen, steht je Institut auf einer eigenen Seite: **[Import-Plugins](importer/README.md)**. Die Leser der Institute sollen später als
installierbare Plugins kommen; diese Seiten wandern dann als README mit. Das Basispaket – Eingang, Ablage, die Regel „der neueste
Export gilt“ und die generischen CSV-Importer – beschreibt dieses Kapitel.

| Smartbroker+ | ING | Scalable Capital | Trade Republic | DKB | C24 Bank | Bondora |
|---|---|---|---|---|---|---|
| [Seite](importer/smartbroker.md) | [Seite](importer/ing.md) | [Seite](importer/scalable.md) | [Seite](importer/trade-republic.md) | [Seite](importer/dkb.md) | [Seite](importer/c24.md) | [Seite](importer/bondora.md) |

| Revolut | Kraken | Coinbase | Bison | BSDEX | BitBox | Ledger |
|---|---|---|---|---|---|---|
| [Seite](importer/revolut.md) | [Seite](importer/kraken.md) | [Seite](importer/coinbase.md) | [Seite](importer/bison.md) | [Seite](importer/bsdex.md) | [Seite](importer/bitbox.md) | [Seite](importer/ledger.md) |

Weitere Leser und Institute ohne Leser: [eigene Seite](importer/historisch-und-von-hand.md).

## Rezepte je Institut

Die Rezepte stehen so auch im Eingang der App; diese Tabelle ist aus ihnen erzeugt. Die Seiten je Institut führen sie aus.

| Institut | Stand | Herunterladen | Deckt ab | Leser | Unterordner |
|---|---|---|---|---|---|
| Bison | aktiv | „Transaction history (CSV)“ je Kalenderjahr – das laufende Jahr jeden Monat neu, im Januar auch das Vorjahr; „Monatsübersicht“ des Verrechnungskontos (PDF) je Monat, unter <Jahr>/Verrechnung/ | alle Coins, das Euro-Guthaben und dessen Monatssalden | Krypto-Börsen und Wallets (CSV-Exporte) · Bison · Bison Transaktionen, nur Euro-Guthaben (CSV) · Bison Verrechnungskonto, Monatsübersicht der EUWAX (PDF oder Text) | bison |
| BitBox | aktiv | Export je Konto aus der BitBoxApp als CSV (gesamte Historie) | je Konto (Coin) ein Export | Krypto-Börsen und Wallets (CSV-Exporte) | bitbox, bitbox02 |
| Bitcoin.de | aktiv | Kontoauszug je Coin als CSV (vom Kontobeginn bis heute) | je Coin ein Kontoauszug | Krypto-Börsen und Wallets (CSV-Exporte) | bitcoinde, bitcoin.de |
| Bondora | aktiv | Go & Grow-Kontoauszug als XLSX oder CSV (vom Kontobeginn bis heute) | Go & Grow | Bondora Go & Grow (xlsx oder CSV) | bondora |
| BSDEX | aktiv | zuerst die Transaktionshistorie des laufenden Jahres als CSV (jeden Monat neu; im Januar auch das Vorjahr); am selben Tag die Transaktionen als CSV mit allen Typen (vom Kontobeginn bis heute) | alle Coins, Staking und das Euro-Guthaben | Krypto-Börsen und Wallets (CSV-Exporte) · BSDEX · BSDEX Euro-Guthaben: Transaktionshistorie je Jahr mit Export „Transaktionen“ (CSV) | bsdex |
| C24 Bank | aktiv | Transaktionen als CSV je Konto – oben das Konto wählen, nicht „Alle Konten“ (vom Kontobeginn bis heute) | die Konten der C24 Bank, je Konto ein Export | C24 Bank Transaktionen (CSV) | c24, c24bank |
| CHECK24 Geldanlage | aktiv | Tagesgeld-Umsätze als PDF-Druck (vom Kontobeginn bis heute) | Tagesgeld | CHECK24 Geldanlagecenter, Tagesgeld (PDF-Druck oder Text) | check24, check24geldanlage |
| Coinbase | aktiv | Transaktionsbericht als CSV (vom Kontobeginn bis heute) | alle Coins, Staking und die EUR-Wallet in einem Bericht | Krypto-Börsen und Wallets (CSV-Exporte) · Coinbase · Coinbase Transaktionen, nur EUR-Wallet (CSV) | coinbase |
| DKB | aktiv | Umsatzliste als CSV je Konto, Giro und Tagesgeld (vom Kontobeginn bis heute); oder die Kontoauszüge des Girokontos als PDF | Girokonto und Tagesgeld | DKB Umsatzliste, Giro und Tagesgeld (CSV) · DKB Girokonto-Kontoauszug (PDF oder Text) | dkb |
| ING | aktiv | Wertpapierabrechnungen, Dividenden- und Ausschüttungsgutschriften und Vorabpauschalen als PDF aus der Post-Box; Kontoauszüge von Girokonto und Extra-Konto als PDF | Direkt-Depot, Girokonto und Extra-Konto | ING Direkt-Depot · ING Kontoauszug, Giro und Extra-Konto (PDF oder Text) | ing, ingdiba |
| Kraken | aktiv | Ledger-Export als CSV (vom Kontobeginn bis heute) | alle Unterkonten (Spot, Earn) und das Euro-Guthaben in einem Export | Krypto-Börsen und Wallets (CSV-Exporte) · Kraken · Kraken Ledger, nur Euro-Guthaben (CSV) | kraken |
| Ledger | aktiv | Operationen aus Ledger Live als CSV (gesamte Historie) | alle Konten von Ledger Live in einem Export | Krypto-Börsen und Wallets (CSV-Exporte) | ledger, ledgerlive |
| Revolut | aktiv | Kontoauszug „All accounts“ als CSV – eine Datei für Girokonto und Sparkonto (vom Kontobeginn bis heute) | Girokonto und Sparkonto, beide in einer Datei | Revolut Girokonto (CSV) · Revolut Sparkonto/Tagesgeld (CSV) | revolut |
| Scalable Capital | aktiv | Wertpapierabrechnungen (Kauf, Verkauf) und Dividenden als PDF aus dem Postfach; Monatliche Kontoauszüge des Verrechnungskontos und des Tagesgelds als PDF | Depot, Verrechnungskonto und Tagesgeld | Scalable Capital (auch Baader-Abrechnungen für Scalable) · Scalable Capital Verrechnungskonto (PDF oder Text) · Scalable Capital Tagesgeld (PDF oder Text) | scalable, scalablecapital |
| Smartbroker+ | aktiv | CSV-Export der Transaktionen (vom Kontobeginn bis heute); Dividendenabrechnungen und Devisenbelege der Baader Bank als PDF; Perioden-Kontoauszüge aller Konten als PDF (Verrechnung, Tagesgeld, Fremdwährungskonten), auch ohne Bewegung | Depot, Verrechnungskonto, Tagesgeld und die Fremdwährungskonten (USD, CHF …) | Smartbroker+ (CSV-Export und Dividendenabrechnungen) · Smartbroker+ Devisenkonten (USD, CHF …) · Baader Bank Perioden-Kontoauszug, auch Smartbroker (PDF oder Text) | smartbroker, smartbrokerplus, smartbroker+ |
| Trade Republic | aktiv | CSV-Export „Transaktionen“ aus der App (vom Kontobeginn bis heute) | Depot und Verrechnungskonto in einem Export | Trade Republic (CSV-Export) · Trade Republic Transaktionsexport (CSV) | traderepublic, traderepublik, tr |
| Baader Bank (Scalable-Depots aus der Baader-Zeit) | historisch, abgeschlossen | Perioden-Kontoauszüge und Abrechnungen als PDF | Depot und Verrechnungskonto bei Baader | Scalable Capital (auch Baader-Abrechnungen für Scalable) · Baader Bank Perioden-Kontoauszug, auch Smartbroker (PDF oder Text) | baader, baaderbank |

Institute ohne Rezept oder ohne Leser: Dateien ablegen, Buchungen von Hand erfassen. Für sie ist der experimentelle generische
Importer gedacht. Die Rezepte bringen die Leser-Plugins mit; ein installiertes Plugin kann ein weiteres mitbringen.

**Kontonummer und Institut am Konto sind wichtig.** Der Eingang ordnet eine Datei über die Kontonummer im Beleg (IBAN, Depotnummer
oder Wallet-Adresse) und über die Institutsangabe am Konto zu. Beides bitte bei jedem Konto eintragen: in *2. Stammdaten* unter
„Konto / Wallet anlegen oder umbenennen“ (Institut und „Kontonummer / IBAN / Adresse“). Fehlt beides, bleiben Dateien ohne Konto offen
und lassen sich nur von Hand in der Ablage hinterlegen.

Ein Unterordner ohne Rezept zählt mit seinem Namen als Institut, wenn der Name genau ein Institut der Konten trifft: Heißt der Ordner
wie die Institutsangabe („Beispiel Bank“), gehört eine Steuerunterlage ohne Kontonummer zu dessen Konten. Ein allgemeiner Name
wie „Steuern“ oder „Bank“ (trifft keines oder mehrere Institute) zählt nicht; dann entscheidet allein die Kontonummer im Beleg.
