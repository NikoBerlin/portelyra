# Das Demo-Portfolio

Portelyra bringt ein Demo-Portfolio mit: ein eigenes, vollständiges Portelyra mit erfundenem Bestand auf echten, bekannten Assets. Es eignet sich zum Ausprobieren, bevor eigene Daten im Spiel sind.

## Starten

```
Rscript scripts/portelyra_desktop.R demo --prices yahoo --confirm ACKNOWLEDGE_PROVIDER_TERMS   # mit aktuellen Kursen von Yahoo Finance
Rscript scripts/portelyra_desktop.R demo                                                       # ohne Netz
```

- **Der erste Aufruf baut das Demo auf.** Das dauert drei bis vier Minuten und braucht kein Netz. Mit `--prices yahoo` schaltet Portelyra danach im Demo die Kurse von Yahoo Finance ein, rund zweieinhalb Minuten. Danach öffnet sich das Demo im Browser.
- **Mit `--confirm ACKNOWLEDGE_PROVIDER_TERMS`** nehmen Sie die Hinweise und die Bedingungen des Anbieters zur Kenntnis (siehe unten), wie bei der Frage nach den Kursen in der Einrichtung.
- **Jeder weitere Aufruf startet es nur.** Ein unterbrochener Aufbau wird beim nächsten Aufruf fortgesetzt.
- **Beenden** mit Strg+C im Terminal, wie beim eigenen Portelyra.
- `--no-browser` öffnet keinen Browser, `--port <n>` wählt andere Ports, `--no-start` baut nur auf.

## Aus der Einrichtung

Beim ersten Start von Portelyra bietet die Einrichtung den Abschnitt **„Erst das Demo-Portfolio ansehen“** an. Das ist derselbe Aufbau wie mit dem Befehl, ohne Terminal:

- **„Demo mit aktuellen Kursen ansehen“** ist der Hauptknopf. Die Hinweise des Anbieters stehen daneben; mit dem Klick nehmen Sie sie und seine Bedingungen zur Kenntnis.
- **„Demo ohne Netz ansehen“** baut das Demo nur mit den Kursen der Buchungen.
- Die Seite zeigt, welche Schritte erledigt sind; das Demo öffnet sich danach in einem eigenen Tab.
- Ihre eigene Einrichtung bleibt offen. Sie können sie jederzeit fortsetzen, auch während das Demo läuft.
- Das so gestartete Demo endet, wenn Sie Portelyra beenden.

## Der Rundgang

Nur im Demo führt ein Rundgang in acht Schritten durch [Erste Schritte](erste-schritte.md), über alle vier Apps: Alles
aktualisieren, Verlauf und Rendite, eine Buchung, den Beispielbeleg, den Steuerbericht und ein Backup. Er beginnt beim ersten Öffnen
von selbst und lässt sich jederzeit beenden; links unter **„Rundgang starten“** beginnt er neu. „Zeig es mir“ öffnet die Stelle, die
Eingaben machen Sie selbst – der Rundgang nennt für jedes Feld einen Wert, der im Demo passt. Gebucht wird nur über Vorschau und
Bestätigung, wie sonst auch.

## Getrennt vom eigenen Bestand

Das Demo liegt in einem eigenen Home und teilt nichts mit Ihrem Bestand:

| | Demo | eigenes Portelyra (Vorgabe) |
|---|---|---|
| Ordner | `~/.local/share/portelyra-demo` | `~/.local/share/portelyra` |
| Zustandsordner (Backups, Protokolle) | `~/.local/state/portelyra-demo` | `~/.local/state/portelyra` |
| Ports | 4838 bis 4841 | 3838 bis 3841 |

Beide können gleichzeitig laufen. Portelyra baut das Demo nie in einen Ordner, der nicht als Demo gekennzeichnet ist, und nie in oder neben den eigenen Bestand.

## Inhalt

- **Konten:** Demo-Depot, Demo-Börse, Demo-Wallet und ein Demo-Tagesgeld bei der Demo-Bank.
- **Assets:** ein MSCI-World-ETF, Allianz, Apple, Deutsche Telekom, Bitcoin, Ethereum.
- **145 Buchungen von 2021 bis 2026:** ETF-Sparplan, Käufe, Teil- und Komplettverkauf, Dividenden, eine Einlieferung mit früherer Anschaffung, eine Umbuchung mit Netzwerkgebühr, monatliche Staking-Rewards. Jedes am Ende gehaltene Asset hat eine Buchung kurz vor dem Release, damit auch ohne Netz kein Kurs Jahre alt ist.
- **Erfunden** sind Mengen, Termine, Gebühren, Konten und der Steuersatz (30 %). Die Stückpreise der Buchungen liegen beim Schlusskurs des jeweiligen Tages.
- **Cash:** Das Demo-Tagesgeld hat Ein- und Auszahlungen ab 2021, Quartalszinsen ab 2023 und je Jahresende einen Prüf-Saldo, dazu einen zum letzten Monatsende vor dem Release. Gebucht ist es über „Cash von Hand“ wie in der App „Daten“. Der Saldo zählt abgestimmt im Vermögen mit, die Zinsen erscheinen in den Kapitalerträgen.
- **Beispielbeleg:** ein erfundener Export im Format von Trade Republic (ein Kauf, eine Dividende) unter `beispielbeleg/` im Demo-Ordner,
  zum Üben des Imports ([Erste Schritte](erste-schritte.md#7-einen-beleg-importieren)). Der Eingang steht da, aber ohne Belegordner.

## Kurse im Demo

Portelyra liefert keine Kursreihen mit. Die Kurse kommen entweder von Yahoo Finance oder aus den Buchungen.

**Mit aktuellen Kursen (Yahoo Finance):**

- Portelyra schaltet im Demo den Kursanbieter Yahoo ein und richtet für jedes Asset die Kurszuordnung mit einem Testabruf ein.
- Danach holt es die Kurshistorie ab der ersten Buchung. Verlauf, Rendite, Snapshot und Momentaufnahme zeigen dann echte Marktkurse.
- **Probieren geht immer:** „Demo mit aktuellen Kursen ansehen“ lässt sich auch später klicken, auch nach einem Demo ohne Netz; ein
  späterer Klick versucht es erneut. Scheitert der Abruf, sagt die Seite das.
- Ist Yahoo nicht erreichbar oder klappt es nur für einen Teil der Assets, bewerten die übrigen wie ohne Netz: mit den Kursen der
  Buchungen und für Allianz, Apple, Bitcoin und Ethereum mit den **erfundenen Kursangaben** (siehe unten). Dann stehen erfundene
  Werte neben echten Marktkursen. Die Ansichten nennen bei jedem Kurs die Herkunft – „eigene Kursangabe“ ist im Demo erfunden, „Marktkurs“
  kommt von Yahoo.

**Ohne Netz:**

- Das Demo läuft im Umfang ohne „Marktdaten“. Bewertet wird mit **eigenen Bewertungen**: Gibt es für ein Asset eine eigene
  Kursangabe, gilt die jüngste davon; sonst der **Kurs der jüngsten Buchung**.
- **Warum erfundene Kursangaben:** Portelyra liefert keine Kursreihen von Kursanbietern mit; deren Nutzungsbedingungen (etwa die von
  Yahoo Finance) erlauben die Weitergabe in der Regel nicht. Allianz, Apple, Bitcoin und Ethereum werden im Demo nur selten
  gekauft – ihr Wert bliebe jahrelang stehen und spränge am nächsten Kauftag um die ganze Kursbewegung dieser Zeit. Für sie trägt das
  Demo deshalb **erfundene eigene Kursangaben** ein: am Kauftag den Kaufkurs, dazwischen zu jedem Quartalsende einen Wert, eingeschoben
  zwischen den beiden Kaufkursen. Sie sind **keine Marktkurse und können von den tatsächlichen Kursen dieser Tage deutlich abweichen.**
  Echte Kurse zeigt das Demo mit „Demo mit aktuellen Kursen ansehen“.
- Für diese vier Assets gilt im Demo ohne Netz deshalb die jüngste Kursangabe (die letzte ist vom 12.11.2026): Eine Übungsbuchung
  ändert dort Menge und Einstand, aber nicht den Kurs. Der ETF wird mit den Kursen seiner monatlichen Sparplankäufe bewertet, Deutsche Telekom mit dem Kurs ihrer Buchung.
- Die Ansichten nennen Herkunft, Tag und Alter des Kurses. Der Wert bewegt sich in Stufen: an Buchungstagen und zu den Kursangaben.
- Die Momentaufnahme und die Kursschritte von „Alles aktualisieren“ entfallen, wie gewählt.

## Entfernen

Demo beenden, dann die beiden Ordner des Demos löschen (siehe Tabelle). Haben Sie im Demo Zeitpläne eingeschaltet, schalten Sie sie vorher in den Einstellungen des Demos wieder aus.
