# Glossar

Die Oberfläche spricht deutsche Finanzfachsprache. Diese Seite nennt die Begriffe, die Portelyra verwendet,
und das englische Wort dazu. Die Quelle ist `contracts/ui-presentation/v1/glossary.csv`; ein Vertragstest prüft, dass die Oberfläche
die dort vermiedenen Wörter nicht mehr zeigt und dass diese Seite jeden Begriff nennt.

## Die vier Apps

| App | Wofür | Englisch |
|---|---|---|
| **Daten** | Buchungen, Konten, Assets, Importe und Einstellungen; die einzige App, die schreibt | Data |
| **Cockpit** | Grundlagen: Bestände, Cash laut Auszug, Stand je Datenart; zeigt die Datenbasis, nur lesend | Cockpit |
| **Steuer** | Steuerreport und Steuerprojektion | Tax |
| **Analyse** | Verlauf, Rendite und Projektion | Analysis |

„Cockpit“, „Steuer“ und „Analyse“ lesen nur veröffentlichte Stände.

## Begriffe aus Verlauf, Rendite und Steuer

Die Begriffe, die in den Auswertungen am häufigsten vorkommen, ausführlicher. „Erste Schritte“ und die Seiten der Apps verweisen
hierher.

### Einstand

Was die Positionen gekostet haben, die Sie noch halten: die Anschaffungskosten der noch offenen Lots nach [FIFO](#fifo) – bei Krypto
je Wallet auch nach dem Durchschnitt, wenn Sie das gewählt haben.

### Marktwert

Menge mal Kurs eines Tages, je Position und zusammen. Ohne Kursanbieter gilt die eigene Bewertung: Ihre jüngste eigene
Kursangabe, und wenn es keine gibt, der Kurs Ihrer jüngsten Buchung – jeweils für den ganzen Bestand. Der Verlauf bewegt sich dann nur
an diesen Tagen und kann an einem Kauftag springen, wenn der neue Kurs weit vom alten liegt. Fehlt ein Kurs ganz, heißt es „nicht vollständig bewertet“ statt einer geschätzten
Zahl.

### Unrealisierte GuV

Gewinn oder Verlust der Positionen, die Sie noch halten: Marktwert minus Einstand, bewertet zu den aktuellen Kursen – die
„Buchgewinne und Buchverluste“. GuV steht für Gewinn und Verlust. Realisiert wird er erst beim Verkauf.

### Realisierte GuV

Gewinn oder Verlust aus Verkäufen: Erlös minus Einstand der verkauften Lots. Erst er ist steuerlich ein Ereignis.

### TWR

Zeitgewichtete Rendite (englisch time-weighted return): wie sich die Anlagen selbst entwickelt haben, unabhängig davon, wann und wie
viel Sie ein- oder ausgezahlt haben. Sie eignet sich zum Vergleich mit Fonds oder Indizes.

### IZF

Interner Zinsfuß (englisch XIRR): Ihre persönliche Rendite pro Jahr, mit Zeitpunkt und Höhe Ihrer Ein- und Auszahlungen. Wer kurz vor
einem Kursanstieg viel eingezahlt hat, hat einen höheren IZF als TWR.

### FIFO

„First in, first out“: Ein Verkauf verbraucht die ältesten Lots zuerst. Danach richten sich Einstand, Haltedauer und realisierte GuV.

- **Wertpapiere im Depot:** Das Gesetz schreibt FIFO vor (§ 20 Abs. 4 Satz 7 EStG).
- **Kryptowerte:** Es gilt eine walletbezogene Betrachtung (BMF-Schreiben vom 06.03.2025, Rn. 61 und 62). Grundsatz ist die
  Einzelbetrachtung: Lässt sich belegen, welcher Coin verkauft wurde, zählt genau dieser. Ist das nicht möglich, gelten für die
  Haltefrist die zuerst angeschafften Coins als veräußert, und für die Anschaffungskosten ist der Durchschnitt anzuwenden; aus
  Vereinfachungsgründen darf auch dafür FIFO unterstellt werden. Die gewählte Methode gilt je Wallet und Coin, bis die Wallet leer ist. Portelyra rechnet je Konto nach FIFO und bietet für
  Krypto je Coin und Wallet wahlweise den Durchschnitt an (Data → „2. Stammdaten“ → „FIFO-Wallet“, Karte
  „Krypto · Wertermittlung je Wallet“).

### Stichtag

Das verbindliche Bild eines abgeschlossenen Tages: Bestand, Einstand, Kurs und Wert vom selben Tag, mit den Schlusskursen
(Stichtags-Snapshot).

### Momentaufnahme

Der Bestand des letzten abgeschlossenen Tages zu den Kursen des laufenden Handelstags, so wie sie zuletzt abgerufen wurden (beim
Kursanbieter oft mit einigen Minuten Verzögerung). Ein Blick zwischendurch, bevor der Tag abgeschlossen ist; Buchungen von heute
zählen erst mit dem nächsten Tagesschluss. Fehlt einem Asset ein frischer Kurs, gilt sein letzter Schlusskurs, und die Analyse nennt
das. Die Momentaufnahme ersetzt den Stichtag nicht.

### Veröffentlichung

Der letzte Schritt von „Alles aktualisieren“: Erst danach sehen Cockpit, Steuer und Analyse den neuen Stand. Bis dahin zeigen sie den
zuletzt veröffentlichten.

### Persönlicher Steuersatz

Ihr Grenzsteuersatz: wie stark der nächste verdiente Euro mit Einkommensteuer belastet wird. Er steht nicht im Steuerbescheid.
Teilt man dort die Steuer durch das Einkommen, erhält man den Durchschnittssatz, und der ist niedriger: Bei 80.000 € zu
versteuerndem Einkommen sind das 2026 rund 28 %, der Grenzsteuersatz liegt bei 42 %. Mit dem Durchschnittssatz schätzt Portelyra
die Steuer zu niedrig. Portelyra braucht den Satz für private
Veräußerungen (etwa Krypto innerhalb eines Jahres) und für sonstige Einkünfte (etwa Staking-Rewards). Kapitalerträge rechnet es
unabhängig davon pauschal mit der [Abgeltungsteuer](#abgeltungsteuer).

Zur Orientierung, ohne Gewähr – der Einkommensteuertarif 2026 nach § 32a EStG, je Person, ohne Solidaritätszuschlag und
Kirchensteuer (bei Zusammenveranlagung gelten die doppelten Beträge):

| Zu versteuerndes Einkommen | Grenzsteuersatz |
|---|---|
| bis 12.348 € (Grundfreibetrag) | 0 % |
| ab 12.349 € | ab 14 %, mit dem Einkommen steigend |
| ab 69.879 € | 42 % |
| ab 277.826 € | 45 % |

Die Werte gelten für das genannte Jahr; die eines neuen Jahres kommen mit einem Update. Ihren genauen Satz nennt der
[Steuerrechner des Bundesfinanzministeriums](https://www.bmf-steuerrechner.de/). Portelyra rechnet
nach deutschem Steuerrecht; für die Beta gilt nur Deutschland.

### Abgeltungsteuer

Der feste Satz auf Kapitalerträge – Dividenden, Zinsen, Gewinne aus Aktien, ETF und Fonds: 25 %, darauf 5,5 % Solidaritätszuschlag
und gegebenenfalls Kirchensteuer. Er hängt nicht vom persönlichen Steuersatz ab.

**Günstigerprüfung:** Liegt Ihr persönlicher Steuersatz unter 25 %, besteuert das Finanzamt Kapitalerträge auf Antrag mit dem
niedrigeren persönlichen Satz (§ 32d Abs. 6 EStG). Diesen Sonderfall bildet Portelyra nicht ab und rechnet immer mit dem festen Satz –
im Zweifel also eher zu hoch, eine bewusst vorsichtige Modellannahme. Ob sich der Antrag lohnt, ist eine Frage für die
Steuerberatung.

### Jahresfrist

Bei privaten Veräußerungsgeschäften – etwa Krypto, Edelmetalle und Devisen – ist ein Gewinn steuerfrei, wenn zwischen Anschaffung und
Verkauf mehr als ein Jahr liegt (§ 23 Abs. 1 Satz 1 Nr. 2 EStG). Portelyra prüft die Frist je Lot nach [FIFO](#fifo).
Innerhalb der Frist gilt der [persönliche Steuersatz](#persönlicher-steuersatz). Bleibt der Gesamtgewinn eines Jahres aus solchen
Geschäften unter der Freigrenze (seit 2024 1.000 €, davor 600 €), ist er steuerfrei; wird sie erreicht, ist der ganze Gewinn
steuerpflichtig. Für Wertpapiere gibt es keine Jahresfrist, ihre Gewinne sind Kapitalerträge.

### Vorabpauschale

Eine Mindestbesteuerung für Fonds und ETF, die wenig oder nichts ausschütten (§ 18 InvStG). Für jedes Jahr wird aus dem Basiszins ein
Ertrag errechnet, gekürzt um die Ausschüttungen und höchstens so hoch wie der Wertzuwachs; er gilt am ersten Werktag des Folgejahres als
zugeflossen, und die Bank behält die Steuer darauf ein. Beim späteren Verkauf mindern die schon versteuerten Vorabpauschalen den
Gewinn, damit nichts doppelt besteuert wird. Portelyra übernimmt die Beträge aus Belegen, soweit ein Leser sie liest, oder aus Ihrer
Eingabe in Data → „Steuer“ → „Vorabpauschalen je Fonds und Konto“.

### Teilfreistellung

Ein fester Anteil der Erträge aus Fonds bleibt steuerfrei, weil der Fonds selbst schon Steuern zahlt (§ 20 InvStG): 30 % bei
Aktienfonds, 15 % bei Mischfonds, 60 % bei Immobilienfonds und 80 % bei Immobilienfonds mit Schwerpunkt im Ausland; Anleihefonds haben
keine. Sie gilt für Ausschüttungen, Vorabpauschalen und Verkaufsgewinne. Den Satz nimmt Portelyra aus der Einordnung des Assets – die
Vorgabe für ETF ist 30 %, Anleihe- und Mischfonds prüfen Sie deshalb je Asset.

### Verlusttopf

Verluste aus Kapitalanlagen werden mit Gewinnen desselben und späterer Jahre verrechnet. Verluste aus dem Verkauf von Aktien dürfen nur
mit Gewinnen aus Aktien verrechnet werden (Aktienverlusttopf, § 20 Abs. 6 Satz 4 EStG); die übrigen Verluste aus Kapitalvermögen kommen
in den allgemeinen Verlusttopf. Jede Bank führt ihre Töpfe getrennt und trägt Übriges ins nächste Jahr vor oder bescheinigt es auf
Antrag. In Data stehen sie je Institut unter „Steuer“ → „Freistellung, Verlusttöpfe und Quellensteuer je Institut“.

### Sparer-Pauschbetrag

Kapitalerträge bis 1.000 € im Jahr bleiben steuerfrei, bei Zusammenveranlagung bis 2.000 € (seit 2023, davor 801 € und 1.602 €;
§ 20 Abs. 9 EStG). Damit die Bank ihn berücksichtigt, braucht sie einen Freistellungsauftrag; über mehrere Banken verteilt zusammen
höchstens bis zum Pauschbetrag.

### Quellensteuer

Steuer, die ein anderer Staat auf Dividenden oder Zinsen schon einbehält. Ein Teil davon, meist bis 15 %, lässt sich auf die deutsche
[Abgeltungsteuer](#abgeltungsteuer) anrechnen; das erledigt in der Regel die Bank. Darüber hinaus Einbehaltenes fordern Sie im Ausland
zurück.

### Valuta

Der Tag der Wertstellung: ab wann eine Buchung auf dem Konto zählt, etwa für Zinsen. Er kann vom Buchungstag abweichen; Kontoauszüge
nennen oft beide. Beim Einlesen von Kontoauszügen nimmt Portelyra für Zinsen den Tag der Wertstellung, wenn der Auszug ihn nennt.

### Prüf-Saldo

Ein Kontostand an einem bestimmten Tag, den Sie aus einem Auszug übernehmen. Damit gleicht Portelyra ab, ob die gebuchten Bewegungen
bis zu diesem Tag vollständig sind; dann gilt der Zeitraum als abgestimmt. Ohne Prüf-Saldo oder Auszug zeigt Portelyra für den Saldo
„nicht verfügbar“, nie 0.

## Begriffe

| Begriff | Bedeutung | Englisch |
|---|---|---|
| **Abdeckung** | Zeitraum, für den Kurse oder Auszüge vorliegen | Coverage |
| **Abschluss** | Rechenlauf über Buchungen, FIFO, Steuer und Bewertung zu einem Stichtag (früher „Run Center“) | Closing |
| **Abschlussplan** | Was ein Abschluss rechnen würde, bevor er bestätigt wird | Closing plan |
| **Abstimmung** | Abgleich eines Saldos mit den Buchungen | Reconciliation |
| **Altbestand** | – | Legacy |
| **Anfangssaldo** | – | Opening balance |
| **Auszug** | Konto- oder Depotauszug eines Instituts | Statement |
| **Baustein** | Ein zu- und abschaltbarer Teil des Umfangs je Portfolio: Cash, Marktdaten, Verlauf und Analyse, Steuerbericht, Steuerprojektion, Import aus Belegen und Auszügen | Module |
| **Berechtigung** | – | Capability |
| **Bereich** | – | Domain |
| **bereit** | – | ready |
| **Bestätigung** | – | Confirmation |
| **Buchung** | Ein Vorgang im Buchungsbestand: Kauf, Verkauf, Ertrag, Übertrag | Activity |
| **Buchungsbestand** | – | Ledger |
| **Buchungszeilen** | – | Postings |
| **Datenbasis** | Der veröffentlichte Stand der Grundlagen (Buchungen je Konto, Assets und Kurse, Belege, Einstellungen), den das Cockpit zeigt | Data basis |
| **Datum** | Kalendertag im Format TT.MM.JJJJ | Date |
| **Eigentümer** | – | Owner |
| **Eingangsordner** | – | Inbox |
| **Entwurf** | Noch nicht gebuchte Angaben | Draft |
| **Ereignis** | Steuerlich relevanter Vorgang | Event |
| **erneut versuchen** | – | Retry |
| **Ertrag** | Dividende, Zins, Reward | Income |
| **Fassung** | – | Revision |
| **Historie** | – | History |
| **Katalog** | – | Catalog |
| **Kursanbieter** | Dienst, der Kurse liefert, etwa Yahoo Finance | Price provider |
| **Kurszuordnung** | Zuordnung eines Assets zu einem Symbol beim Kursanbieter | Price mapping |
| **Leser** | Plugin, das Belege eines Instituts liest | Reader |
| **Markt** | – | Market |
| **Nachweis** | Beleg dafür, woher ein Wert stammt, etwa ein Kurs oder ein Auszug | Evidence |
| **Notierung** | Handelsplatz und Währung eines Kurses beim Kursanbieter | Listing |
| **nur fortgeschrieben** | Nichts wird überschrieben; jede Änderung kommt als neue Fassung hinzu | append-only |
| **nur lesend** | – | read-only |
| **Nutzer** | – | User |
| **Paket** | Austauschpaket mit Stammdaten und Buchungen | Bundle |
| **Probe** | – | Sandbox |
| **Prüfbereich** | – | Staging |
| **Prüfung** | – | Review |
| **Quelle** | – | Source |
| **Register** | – | Registry |
| **Sammellauf** | Abruf oder Prüfung für mehrere Assets in einem Durchgang | Batch |
| **Schreiben** | Ein bestätigter Schritt hält etwas dauerhaft fest | Write |
| **Schreiben in den Bestand** | – | Product write |
| **Stammdaten** | Portfolios, Konten und Assets | Master data |
| **Stand** | – | State |
| **Stichzeitpunkt** | Zeitpunkt, bis zu dem ein Lauf Buchungen berücksichtigt | Cutoff |
| **Tageskurs** | – | Daily price |
| **Testdaten** | Erfundene Daten für Tests und Proben | Fixtures |
| **Übergabe** | – | Handoff |
| **Übernahme** | Übernahme geprüfter Daten in den Bestand | Cutover |
| **Uhrzeit** | Uhrzeit mit Zeitzone; UTC ist die Weltzeit | Time |
| **ungeprüft** | – | unverified |
| **unveränderlich** | – | immutable |
| **Vorgang** | – | Command |
| **Vorschau** | Was ein Schritt schreiben würde, bevor er bestätigt wird | Preview |
| **Vorschläge** | – | Candidates |
| **Wiederaufnahme** | Einen unterbrochenen Schritt sicher zu Ende führen | Recovery |

## Eingeführte Begriffe, die bleiben

Einige Wörter sind im deutschen Finanzalltag üblich und bleiben deshalb auch in der Oberfläche:

| Begriff | Bedeutung |
|---|---|
| **Backup** | Gesicherte Kopie des Datenraums |
| **Lot** | Anschaffungsposten im FIFO |
| **Reward** | Buchungsart für Staking- und andere Krypto-Belohnungen |
| **Snapshot** | Verbindliches Bild eines Stichtags (Stichtags-Snapshot) |
| **Steuerreport** | Bericht für die Steuererklärung, als PDF und CSV |
| **Transfer** | Buchungsart: Übertrag zwischen eigenen Konten |
| **Wallet** | Krypto-Wallet |

Ebenso bleiben Asset, Cash, Portfolio, FIFO, FX, Plugin, Broker, Import, Export, CSV, PDF, UTC, ISIN und Symbol.

## Fehlermeldungen

Jede Fehlermeldung nennt den Grund und den nächsten Schritt; dahinter steht in Klammern der Code, etwa
„(Code: desktop_release_backup_source_changed)“. Meldet ein interner Prüfschritt einen Fehler, steht dort
„Bitte melden Sie diesen Fehlercode: …“ – mit diesem Code lässt sich der Fall nachvollziehen.
