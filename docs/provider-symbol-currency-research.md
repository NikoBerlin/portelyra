# Provider-Symbole, Währungsvorschläge und historische Kalender

## Recherche und Abgrenzung

Primärquelle für **Yahoo-spezifische Handelsplatzsuffixe**:
[Yahoo Help: Exchanges and data providers](https://help.yahoo.com/kb/finance-for-web/SLN2310.html).
Die Seite wurde für dieses Paket online gelesen, ohne Kurs-/Chart-/Suchprovideraufruf.
Sie nennt Suffix, Handelsplatz, Verzögerung und Lieferant – **keine Garantie einer
instrumentbezogenen Kurswährung**. Die lokale Währungszuordnung ist unsere
vorsichtige UX-Heuristik, nicht eine von Yahoo garantierte Currency-Tabelle.
Keine Daten oder Code aus dem Legacy-Projekt übernommen.

Beispiele: `.DE` bezeichnet Xetra, `.F` Frankfurt, `.SW` SIX, `.TO` Toronto,
`.AX` Australien, `.T` Tokio, `.HK` Hongkong, `.PA` Paris, `.AS` Amsterdam.
Typische Vorschläge sind entsprechend EUR, CHF, CAD, AUD, JPY und HKD.
Auch an diesen Handelsplätzen sind abweichende Instrument-/Handelswährungen möglich.
Keine Identitätsauflösung aus Endung, Emittentensitz oder ISIN-Länderpräfix!
Ohne passenden Provider ist eine Yahoo-Endung bedeutungslos.

Priorität:
1. Gespeichertes Mapping bleibt unverändert, auch wenn eine Heuristik widerspricht.
2. Explizit ausgewählte Provider-Metadaten schlagen die Ticker-Heuristik.
3. Neues Formular: bekannte Endung bzw. Fiat-Quote eines Crypto-Paars als Vorschlag.
4. Einfaches Yahoo-Symbol ohne Suffix: USD-Vorschlag, kein Verifizierungsclaim.
5. Sonst vorhandene Stammdatenpreiswährung als gekennzeichneter Formularvorschlag,
   oder leer, wenn nichts bekannt ist.

Manuelle Abweichungen werden bei weiterer Eingabe nicht überbügelt. Bei vorhandenen
Mappings gibt es nur eine **explizite** Vorschlagsübernahme ins Formular; persistiert
wird weiterhin über Prüfen/Bestätigen/Speichern. Probe und Revision bleiben gebunden.

## Keine stillen Einheitentransformationen

London-/Johannesburg-/Tel-Aviv-Suffixe erhalten absichtlich keinen automatischen
Währungsvorschlag: Mehrwährungs- und Untereinheitenrisiken (z. B. GBP vs. GBp/GBX)
könnten einen Faktor-100-Fehler erzeugen. Das Core-Formular erwartet eine
Hauptwährung, nicht eine still skalierte Provider-Quotierung. Nicht unterstützte
Metadaten wie `GBp`, `GBX`, `ZAc`, `ILA` werden nicht durch `toupper` repariert.
Keine Umrechnung, keine erfundenen FX-Routen. `=X`, `=F`, Index- und OCC-Optionssymbole
bekommen ebenfalls keine pauschale USD-Heuristik.
[Yahoo: OCC-Optionssymbole](https://help.yahoo.com/kb/finance-for-web/SLN13884.html)
beschreibt die Unterscheidung von Root, Datum, Call/Put und Strike.

## Historische Xetra-Kalender

Die offiziellen PDF-Fußnoten nennen die Ausnahmen ausdrücklich als **handelsfrei**,
teilweise trotz geöffnetem Settlement. Das ist nicht mit einem Kurstag gleichzusetzen.

- [Archiv](https://www.cashmarket.deutsche-boerse.com/cash-en/trading/trading-calendar-and-trading-hours/trading-calendar)
- [2019](https://www.cashmarket.deutsche-boerse.com/resource/blob/1406548/6de0eba301a5433abb110fa3c96a5778/data/xetra-trading-calendar-2019.pdf): zusätzlich 10. Juni und 3. Oktober.
- [2020](https://www.cashmarket.deutsche-boerse.com/resource/blob/1665534/112856375187d3e93671aa3d731d09d3/data/xetra-trading-calendar-2020.pdf): zusätzlich 1. Juni.
- [2021](https://www.cashmarket.deutsche-boerse.com/resource/blob/2344982/ddbcd31a616628a7ffa09dc709467ec4/data/xetra-trading-calendar-2021.pdf): zusätzlich 24. Mai.
- [2022](https://www.cashmarket.deutsche-boerse.com/resource/blob/2833162/2f53999770c09ce9c0bee8194c1fe60d/data/xetra-trading-calendar-2022.pdf): nur 15./18. April und 26. Dezember als Wochentagsausnahmen.
- [2023](https://www.cashmarket.deutsche-boerse.com/resource/blob/3317408/4c8fbfbfeea62fd44600f6fe3f14f84e/data/xetra-trading-calendar-2023.pdf)
- [2024](https://www.cashmarket.deutsche-boerse.com/resource/blob/3559262/98ebe1fde231df56c9f116bc766533b2/data/xetra-trading-calendar-2024.pdf)
- [2025](https://www.cashmarket.deutsche-boerse.com/resource/blob/4302124/bc43304f7bdce4d4fe4f38eb2bd79d00/data/xetra-trading-calendar-2025.pdf)
- [2026](https://www.cashmarket.deutsche-boerse.com/resource/blob/4481276/1b643791fcb4d60bdd7f25efad3f4626/data/deutsche-boerse-trading-calendar-2026.pdf)

Die vier zusätzlichen Daten werden **exakt jahresgebunden**, nicht als allgemeine
Pfingstmontags-/3.-Oktober-Regel aufgenommen.

Die neue Regelversion widerruft alte quellcodegebundene Vorschauen regulär; sie
ändert keine gespeicherten Kalender oder Historien. Börse, Geltung und konkrete
Schließtage bleiben im Produkt separat zu prüfen und zu bestätigen. FX erbt keine
Aktienfeiertage. Privatdaten und Recherche-Rohdateien bleiben außerhalb des Repos.
