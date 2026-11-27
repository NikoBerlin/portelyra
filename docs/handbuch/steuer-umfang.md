# Steuer: was das Regelmodul abdeckt

Portelyra rechnet Steuern als **Projektion** nach einem Regelmodul – keine Steuerberatung und keine
Steuererklärung. Das mitgelieferte Modul `tax_de_personal_income_tax_projection_v2` gilt für Deutschland und private Kapitalanlagen.

## Steuerjahre

| Jahre | Umfang |
|---|---|
| **2020–2026** | weitgehend vollständig für die Kapitalanlage: Abgeltungsteuer mit Solidaritätszuschlag und Kirchensteuer, Kapitalerträge je Institut mit Verrechnung, Verlusttöpfen, Freistellungsauftrag und Quellensteuer, private Veräußerungsgeschäfte mit Jahresfrist und Freigrenze, sonstige Einkünfte (Rewards), Teilfreistellung bei Fonds, Vorabpauschale. **Ausnahmen:** Fondsanteile, die vor 2018 angeschafft wurden (siehe unten), und die Punkte unter „Bewusst nicht enthalten“. |
| **2016–2019** | **nur in Grundzügen, ausdrücklich nicht vollständig:** dieselben Jahreswerte und Regeln (Abgeltungsteuer 25 %, Solidaritätszuschlag 5,5 %, Sparer-Pauschbetrag 801/1.602 €, Freigrenzen 600 € und 256 €), die Jahresfrist und die Rewards. Fonds rechnet das Modul in diesen Jahren nicht. |
| vor 2016 | keine Regeln – keine Steuerzahl, mit Hinweis. |

Wo das Modul nur in Grundzügen rechnet, sagen es die App „Daten“ („4. Steuer“ → „Steuerangaben je Jahr“) und die Jahresrechnung der Steuer-App
ausdrücklich. Abschluss und Netto-Sicht der Tageshistorie rechnen ihre Jahreskette ab 2020; für die Jahre davor zeigt die Netto-Sicht
„netto = brutto“ mit Hinweis.

## Bewusst nicht enthalten (alle Jahre)

- die Ermäßigung der Abgeltungsteuer durch die Kirchensteuer (die Kirchensteuer rechnet als Zuschlag auf die projizierte Steuer),
- Freigrenze und Milderungszone beim Solidaritätszuschlag,
- die Verlustverrechnungsgrenze für Termingeschäfte und Forderungsausfälle (2020–2024),
- Zahlungen mit Coins als Veräußerung: Sie stehen im Steuerreport und im Rechenblatt, das Modul rechnet sie nicht,
- die Günstigerprüfung (§ 32d Abs. 6 EStG): Kapitalerträge rechnet Portelyra immer mit 25 % Abgeltungsteuer zuzüglich
  Solidaritätszuschlag und gegebenenfalls Kirchensteuer. Bei einem persönlichen Steuersatz unter 25 % ist die Projektion damit eher
  zu hoch – eine bewusst vorsichtige Annahme; ob sich der Antrag lohnt, ist eine Frage für die Steuerberatung,
- ein progressiver Einkommensteuertarif: Für private Veräußerungen und sonstige Einkünfte gilt der eingetragene persönliche Satz.

## Fonds vor 2018

Bis Ende 2017 galt das alte Investmentsteuergesetz, und für Anteile aus dieser Zeit (Altanteile) gilt eine gedachte Veräußerung zum
31.12.2017 (§ 56 InvStG). Beides bildet das Modul nicht ab. Ein Fonds-Ereignis vor 2018 und ein Fondsverkauf mit Anteilen, die vor
2018 angeschafft wurden, bekommen deshalb **keine Steuerzahl**, sondern den Hinweis „altes Investmentsteuergesetz – nicht
berechnet“ – nie eine falsche Zahl. Das gilt auch für Verkäufe ab 2020.

## Belege der Jahreswerte

Jede Zahl steht mit Fundstelle im Modul (`legal-references.csv`) und ist in der App „Daten“ je Jahr mit ihr zu sehen. Für 2016–2019 ist der
Wortlaut der damals geltenden Fassung an der konsolidierten Fassung (buzer.de) und am geltenden amtlichen Text
(gesetze-im-internet.de) geprüft, nicht am Original-Bundesgesetzblatt – dessen Archiv 2007–2022 ist maschinell nicht lesbar.

## Später als Plugin

Genauere Regeln für frühere Jahre (etwa das alte Investmentsteuergesetz) und Regeln für Jahre nach 2026 sollen als eigene
Regelmodule (Plugins) kommen. Ein Modul nennt seinen Umfang je Jahr selbst (`year-coverage.csv`); die Apps „Daten“ und „Steuer“ zeigen ihn an.

## Welche Fassung gerechnet wird

Gerechnet wird mit der Fassung, die in der App „Daten“ unter „4. Steuer“ → Karte „Regelmodul“ je Projektionsart gewählt ist
(„Je Ereignis“, „Je Jahr“, „Unrealisiert“) – im Abschluss, in den Rechenblättern, in der Jahresrechnung und im Netto-Verlauf.
„Gültig ab“ heißt: Ab diesem Tag rechnet Portelyra **alle** Steuerjahre mit dieser Fassung; früher erstellte Berichte nennen ihre
Fassung. Ohne Auswahl rechnet Portelyra mit der mitgelieferten Fassung.

Die gewählte Fassung legt Portelyra im Datenraum ab (sie liegt damit im Backup) – beim Öffnen der Steuereinstellungen, bei jeder
Übernahme und bei jedem Lauf von „Alles aktualisieren“. Bringt ein neues Release eine neuere Fassung mit, rechnet Portelyra weiter
mit Ihrer, bis Sie die neue übernehmen. Wurde zwischen zwei Updates weder „Alles aktualisieren“ ausgeführt noch die
Steuereinstellungen geöffnet, ist die Fassung noch nicht abgelegt: Öffnen Sie nach einem Update deshalb einmal die
Steuereinstellungen, wenn „Alles aktualisieren“ bei Ihnen nicht regelmäßig läuft.

## Neue Fassung übernehmen

Gibt es eine neuere Fassung, zeigt die Karte „Regelmodul“ „Neue Fassung verfügbar“: welche Jahreswerte sich ändern (bisher, neu,
Fundstelle) und wie viele Regeln. „Neue Fassung für alle Projektionsarten übernehmen“ mit „Gültig ab“ (Vorgabe heute) übernimmt
sie für „Je Ereignis“, „Je Jahr“ und „Unrealisiert“ zugleich; das Datum muss nach dem der bisherigen Auswahl liegen.

## Neue Fassung aus Datei installieren

Eine neue Fassung kommt mit einem neuen Release oder als Paket (ZIP) von Portelyra. In der Karte „Regelmodul“ unter „Neue Fassung
aus Datei installieren“ die Datei wählen und „Paket prüfen“ drücken. Portelyra prüft, ohne etwas zu schreiben:

- die **Portelyra-Signatur** – ohne sie läuft kein Code aus dem Paket;
- die Prüfsumme jeder Datei und ob die Jahreswerte, mit denen das Modul rechnet, mit seiner Tabelle übereinstimmen;
- die **Testfälle** des Pakets – das Modul muss sie genau so rechnen wie angegeben;
- welche Jahreswerte sich gegenüber der mitgelieferten Fassung ändern.

Ist alles in Ordnung, „Ich habe Fassung und Unterschiede gesehen“ ankreuzen und „Fassung installieren“. Danach steht sie oben unter
„Neue Fassung verfügbar“ und gilt erst, wenn Sie sie übernehmen. Solange der Signaturschlüssel von Portelyra nicht eingerichtet ist,
lässt sich kein Paket installieren.

Eine Fassung gibt es nur, wenn ihre Prüfsummen stimmen und die Jahreswerte, mit denen das Modul rechnet, mit seiner Tabelle
übereinstimmen. Ändert sich eine Fassung unter gleichem Namen (Regeln geändert), zeigt die Tabelle „Bereitschaft je
Projektionsart“ „Regeln des Moduls geändert – neu übernehmen“, und die Auswahl klappt von selbst auf.
