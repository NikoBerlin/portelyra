# Wie aktuell ist der Gesamtstand?

Portelyra erfährt jede Bewegung aus den Belegen der Institute, und die kommen in verschiedenem Takt:

| Datenart | Takt | Woher |
|---|---|---|
| Wertpapiere, Krypto, Devisen | täglich bis wöchentlich | Abrechnungen und Transaktionsexporte |
| Rewards | auch innerhalb des Monats | Exporte der Börsen |
| Cash auf Bankkonten | höchstens monatlich | Kontoauszug |
| Kurse | täglich, die Momentaufnahme öfter | Kursanbieter |

**Zeitpläne:** Daten → Einstellungen → „Automatik“ → „Von selbst aktualisieren“.
- „Alles aktualisieren“ läuft zu bis zu sechs Uhrzeiten am Tag.
- Die Momentaufnahme hat einen eigenen, schnellen Zeitplan: nur aktuelle Kurse, ohne Tageshistorie und Abschluss.
- Quelllücken fragt der Lauf bei jedem Lauf, einmal pro Woche (Vorgabe) oder nie erneut ab.
- Läuft gerade etwas, wartet ein Zeitplan bis zu 30 Minuten und startet dann; zwei Läufe zugleich gibt es nie.
- Abgerufen wird bis gestern; die Werte von heute zeigt die Momentaufnahme.

**Ab wann ein Tageskurs gilt:** Daten → Einstellungen → „Anzeige und Berechnung“ → „Kursabruf“.
- **Handelsschluss + 1 Stunde (Vorgabe):** Börsen gelten eine Stunde nach ihrem Schluss als abgeschlossen. Ein Lauf nach
  Mitternacht holt so die Schlusskurse des Vortags. Schlusszeiten: XETRA 17:35, Frankfurt und Stuttgart 22:00, New York 16:00
  Ortszeit, London 16:35, Paris, Amsterdam, Mailand und Wien 17:35, Zürich 17:30.
- **Ende des Kalendertags + 1 Stunde:** vorsichtiger; deutsche Börsen ab 1 Uhr, US-Börsen ab 7 Uhr (Winterzeit).
- **Krypto und Wechselkurse** gelten in beiden Fällen erst nach dem Ende ihres Kalendertags, gegen 2 Uhr nachts.
- **Assets in Fremdwährung** bekommen den Wert eines Tages erst, wenn auch der Wechselkurs dieses Tages abgeschlossen ist. Eine
  US-Aktie in Euro hat den Vortag also ab etwa 2 Uhr, nicht früher.
- Ein früher geholter Kurs bleibt vorläufig und wird erneut angefordert, bis ein späterer Abruf ihn bestätigt.

**Stand links:** In jeder App steht links unter der Navigation:
- **Aktualisierung:** ob gerade ein Lauf rechnet, seit wann, welcher Schritt, wie weit und wie lange noch (geschätzt aus dem
  letzten Lauf); wann zuletzt einer fertig wurde und wann die nächsten Termine sind.
- **Läuft gerade:** der Sammellauf im Reiter Marktdaten, eine Wartung oder ein langer Vorgang der Seite.
- **Alles aktualisieren** und **Einstellungen:** In der App „Daten“ öffnen sie die Bereiche, in den anderen Apps führen sie dorthin.

Zwischen zwei Kontoauszügen kennt Portelyra einen Kauf schon, aber noch nicht den Abgang vom Verrechnungskonto. Ohne Ausgleich
zeigt der Gesamtstand nach einem Kauf zu viel und nach einem Verkauf zu wenig.

## Der vorläufige Cash-Stand

- Hinter dem amtlichen Saldo steht in Klammern der vorläufige, etwa „1.250,00 € (vorl. 310,40 €)“. Das gilt für die Tabelle
  „Cash je Konto“ und für die Zeilen Cash und Gesamtvermögen, in der Analyse (Stichtag und Momentaufnahme) und im Cockpit.
  Eine Klammer steht nur, wo der vorläufige Betrag abweicht.
- **Amtlich** ist der Saldo des letzten Auszugs oder Abgleichs. **Vorläufig** kommen hinzu: Buchungen auf dem Konto nach diesem
  Tag und die Abrechnungen der Depots, die auf dieses Konto abrechnen und noch in keinem Auszug stehen. Ein Kauf zählt mit
  Kurswert und Gebühr, ein Verkauf mit dem Erlös nach Gebühr.
- Welches Depot auf welches Konto abrechnet, lernt Portelyra aus den bisherigen Auszügen: Es zählt, wo seine Abrechnungen
  angekommen sind, mindestens dreimal.
- **Gebucht wird nichts.** Kommt der Auszug, findet der Import jede Abrechnung in ihrer Zeile, und die Klammer fällt weg. Deshalb
  kann sich nichts doppelt buchen.
- Verlauf, Rendite, Steuer und Kennzahlen rechnen weiter mit dem amtlichen Stand.

### Grenzen

- **Umbuchungen** zwischen eigenen Konten, etwa vom Tagesgeld auf das Verrechnungskonto, erscheinen erst mit dem Auszug. Fehlen
  beide Seiten noch, oder sind beide schon gebucht, stimmt die Summe; nur die Verteilung auf die Konten kann abweichen.
- **Auszüge, die verschieden weit reichen:** Ist nur eine Seite einer Umbuchung schon gebucht, stimmt auch die vorläufige Summe
  nicht. Beispiel: 1.000 € gehen vom Tagesgeld aufs Verrechnungskonto und kaufen dort Aktien. Der Tagesgeld-Auszug ist schon
  importiert, der des Verrechnungskontos noch nicht. Dann zählt der Abgang doppelt, einmal amtlich beim Tagesgeld und einmal als
  Kauf in der Klammer; die vorläufige Summe ist 1.000 € zu niedrig. Abhilfe: **die Auszüge eines Monats zusammen importieren**, für
  alle Konten, zwischen denen umgebucht wird, auch über Institute hinweg. Mit dem fehlenden Auszug stimmt alles wieder.
- **Steuer, Zinsen, Kontogebühren** zählen erst mit dem Auszug. Ein Verkauf steht mit dem Erlös vor Steuer da.
- **Alter Auszug:** Ist der letzte Auszug eines Kontos älter als zwei Monate, wird nicht geschätzt. Die Tabelle nennt dann, wie
  viele Abrechnungen seitdem ohne Auszugszeile sind – ein Hinweis, dass Auszüge fehlen.
- **Konto mit Jahresauszug** (manche Extra- oder Tagesgeldkonten): Es bekommt aus demselben Grund keine Schätzung. Geht das Geld
  kurz darauf per Umbuchung auf ein Konto mit Monatsauszug, stimmt die Summe schon; eine Schätzung würde es doppelt zählen. Der
  Import des Jahresauszugs reicht, von Hand buchen ist nicht nötig.
- **Geschlossene und ruhende Konten** bekommen keine Schätzung.
- **Konto außerhalb von Portelyra:** Bezahlt ein Depot über ein Konto, das Portelyra nicht führt, kommt das Geld von außen. Der
  Gesamtstand ist dann schon richtig, eine Schätzung gibt es nicht.

## Wann von Hand buchen?

- **Konten mit Auszug-Import** (Verrechnungs- und Girokonten): nicht von Hand buchen. Die Lücke bis zum nächsten Auszug überbrückt
  der vorläufige Stand von selbst; der Auszug bringt dann die amtlichen Zeilen.
- **Konten ohne Importer mit wenigen Bewegungen im Jahr**, etwa ein Tagesgeldkonto ohne Leser: von Hand buchen (Daten → Manuell → Cash →
  „Cash-Buchung eintragen“), mit Buchungstag und Betrag wie im Kontoauszug, danach „Saldo prüfen“ mit dem Saldo aus der
  Banking-App. Erst der Abgleich macht den Stand amtlich: Bei einem abgestimmten Konto gilt der Saldo des letzten Abgleichs, eine
  spätere Buchung allein ändert ihn nicht. Bis zum Abgleich steht sie im vorläufigen Stand („1 Buchung seit … eingerechnet“).
- **Doch auf einem Konto mit Auszug-Import gebucht:** dann nur mit Buchungstag und Betrag genau wie im späteren Auszug. So erkennt
  der Cash-Import die Zeile als gebucht. Weicht eins davon ab, erscheint sie beim Import als „neu“ und die Saldoprüfung schlägt an;
  still doppelt gebucht wird nichts.
- **Umbuchungen** zwischen eigenen Konten muss man nicht nachtragen.

## Momentaufnahme und Verlauf

- Der Reiter **Momentaufnahme** zeigt den heutigen Bestand zu den zuletzt abgerufenen Kursen, also mit den Käufen und Verkäufen
  von heute.
- Der hohle Punkt **„jetzt“** im Verlauf rechnet mit dem Bestand des letzten Tagesschlusses zu denselben Kursen. Buchungen von
  heute zählen dort ab dem nächsten Tagesschluss; unter dem Bild steht, welche es sind.
- Liegen beide auseinander, ist der Unterschied der Wert der seit dem letzten Tagesschluss gebuchten Stücke. Für denselben Tag
  stimmen Stichtags-Snapshot und Verlauf auf den Cent überein.
