# EODHD (Suche mit ISIN, Tageskurse)

Kursanbieter-Plugin für die **Suche nach Name, Kürzel oder ISIN** (#495, rc.392) und für **Tageskurse** (`daily_history`, Plugin
1.1.0). Die Suche ist für die Anlage eines Assets in den Stammdaten gedacht: Namen eingeben, einen Treffer wählen; die ISIN steht dann
im Formular, wenn EODHD sie liefert. Ohne dieses Plugin funktioniert die Stammdaten-Eingabe mit der Yahoo-Suche wie bisher. Mit den
Tageskursen kann EODHD zweiter Anbieter für Kurshistorie sein.

## Grenzen

- **Schlüssel nötig:** kostenlos nach Anmeldung bei EODHD. Eintragen unter Data → Einstellungen → Zugänge; Portelyra legt ihn im
  Schlüsselbund ab und setzt ihn als Parameter `api_token` nur in Anfragen an `eodhd.com` ein. Das Plugin sieht ihn nie.
- **Kontingent:** kostenlos 20 Abrufe am Tag; jede Suche und jeder Kursabruf (ein Zeitraum eines Wertpapiers) zählt einen. Eine
  Obergrenze lässt sich im Reiter Kursanbieter → Kosten setzen.
- **Tiefe:** kostenlos nur etwa ein Jahr Kurshistorie. Das Manifest nennt deshalb `history_max_days` 365. Ältere Tage liefert der
  kostenlose Zugang nicht; sie bleiben ohne Kurs.
- **Nur die Börsen der Tabelle unten.** Die Antwort nennt weder Währung noch Zeitzone; beides steht im Plugin je Börse.
- **Keine Kapitalmaßnahmen:** EODHD meldet in den Tageskursen keine Splits und keine Dividenden. Jeder Tag trägt
  `corporate_action_status` `none_reported`, `split_review_required` ist immer `false`. `close` ist der unbereinigte Schluss, so wie
  gehandelt; ein Split muss wie bisher als Buchung erfasst sein. `adjusted_close` ist laut EODHD um Splits **und** Dividenden
  bereinigt, wie bei Yahoo. Da dieses Plugin nie eine ungeprüfte Kapitalmaßnahme meldet, bewertet der Kern damit nicht.
- **Kein Name, keine Gattung, keine Erstnotiz:** `instrument_name` und `instrument_type` bleiben leer, `first_trade_date` ist `null`.
  Leer heißt „von der Quelle nicht gemeldet“; so zeigt Data kein „Quelle meldet: …“, das die Quelle nie gemeldet hat. Liegt ein Zeitraum
  vor der Erstnotiz, antwortet EODHD mit einer leeren Liste: Das sind Tage ohne Kurs, kein `not_listed`.
- **Kein laufender Kurs:** `live_session` ist immer `null`. Einen Balken der offenen Sitzung kann das Plugin nicht erkennen; abgerufen
  werden sollen nur abgeschlossene Handelstage.
- **Zeitpunkt je Tag:** Die Antwort trägt nur das Datum. `observed_at_utc` ist 12:00 Ortszeit der Börse (wie die Ordnungszeit der
  Devisen-Belege). Der Zeitpunkt fällt in der Börsenzeitzone sicher auf den Handelstag, und sein UTC-Datum ist für alle Börsen der
  Tabelle derselbe Tag.
- **Abdeckung der Suche:** weltweit, darunter Xetra, Frankfurt und weitere deutsche Börsen sowie Fonds (`EUFUND`). Tradegate, gettex
  und Lang & Schwarz führt EODHD nicht.
- **Datenweitergabe:** EODHD erfährt den Suchbegriff bzw. Symbol und Zeitraum.
- **Bedingungen:** https://eodhd.com/financial-apis/terms-conditions – Speichern und Auswerten für private, nicht kommerzielle
  Zwecke erlaubt; keine Weitergabe an andere.

## Börsen für Tageskurse

Das Börsenkürzel ist der Teil des Symbols nach dem letzten Punkt (`SAP.XETRA` → `XETRA`). Aufgenommen sind nur Börsen, an denen in
einer Währung gehandelt wird. Die Zeitzonen sind dieselben, die Yahoo für diese Börsen meldet, damit eine Notierung beim
Anbieterwechsel dieselbe Zeitzone behält.

| Kürzel | Börse | Währung | Zeitzone |
| --- | --- | --- | --- |
| `XETRA` | Xetra | EUR | Europe/Berlin |
| `F` | Frankfurt | EUR | Europe/Berlin |
| `STU` | Stuttgart | EUR | Europe/Berlin |
| `BE` | Berlin | EUR | Europe/Berlin |
| `MU` | München | EUR | Europe/Berlin |
| `HM` | Hamburg | EUR | Europe/Berlin |
| `DU` | Düsseldorf | EUR | Europe/Berlin |
| `HA` | Hannover | EUR | Europe/Berlin |
| `US` | US-Börsen | USD | America/New_York |
| `PA` | Euronext Paris | EUR | Europe/Paris |
| `AS` | Euronext Amsterdam | EUR | Europe/Amsterdam |
| `BR` | Euronext Brüssel | EUR | Europe/Brussels |
| `LS` | Euronext Lissabon | EUR | Europe/Lisbon |
| `MI` | Borsa Italiana (Mailand) | EUR | Europe/Rome |
| `MC` | Börse Madrid | EUR | Europe/Madrid |
| `VI` | Wiener Börse | EUR | Europe/Vienna |
| `SW` | SIX Swiss Exchange | CHF | Europe/Zurich |
| `EUFUND` | Fonds (virtuelle Börse von EODHD) | EUR | Europe/Berlin |

- **Fonds:** EODHD führt europäische Fonds unter `EUFUND` in EUR. Ein Ausgabetag ist ein Kalendertag; die Fondsstandorte der Eurozone
  liegen in MEZ, und Europe/Berlin ist die Zeitzone der deutschen Fondsnotierungen bei Yahoo.
- **Andere Handelswährung an einer dieser Börsen** (etwa USD-Linien von ETFs an SIX oder Euronext Amsterdam): Das Plugin meldet die
  Währung der Tabelle. Passt sie nicht zur Notierung, weist der Kern den Abruf ab („Währung passt nicht“). Solche Linien gehen über
  dieses Plugin nicht.
- **Nicht unterstützt:** London (`LSE`: Pence oder Pfund, je Linie verschieden), Krypto (`CC`), Devisen (`FOREX`) und alle übrigen
  Börsen. Für sie baut das Plugin keine Anfrage: kein Abruf, kein verbrauchtes Kontingent; der Kern meldet `price_provider_failed`.
  Käme trotzdem eine Antwort an, ist sie `invalid`.

## Ausgänge der Tageskurse

| Antwort | Ausgang | Begründung |
| --- | --- | --- |
| 200, JSON-Liste | `ok` | Tage in `start_date`..`end_date`, aufsteigend. Eine leere Liste heißt: keine Kurstage im Zeitraum. |
| 401, 403 | `rejected` | EODHD antwortet mit 403 „Forbidden“ sowohl auf einen ungültigen Schlüssel als auch auf ein Symbol, das der Zugang nicht abrufen darf (geprüft mit dem öffentlichen Demo-Schlüssel: jedes nicht freigegebene Symbol gibt 403). Beides ist aus der Antwort nicht zu unterscheiden. Bekannt ist nur: Die Quelle hat abgewiesen. |
| 402, 429 | `rejected` | Kontingent erschöpft bzw. zu viele Abrufe. |
| 404 | `invalid` | Unbekanntes Symbol (Annahme, nicht geprüft). Nicht `not_listed`: Das heißt im Kern „vor der Erstnotiz“, und der Lauf übergeht ein solches Fenster als Auskunft. Für ein unbekanntes Symbol wäre das falsch und still; `invalid` führt in Data zu „Das Symbol prüfen“. |
| Börse nicht in der Tabelle | `invalid` | Währung und Zeitzone unbekannt; die Anfrage wird gar nicht erst gebaut. |
| alles andere | `invalid` | 5xx, kein JSON, andere Form, Zahl als Text, negative Zahl, doppeltes Datum, Volumen nicht ganzzahlig. |

## Zahlen

JSON-Zahlen werden exakt als Dezimaltext gelesen (Decimal, nie Fließkomma); ganze Zahlen bleiben ganz (`348`), lange Nachkommastellen
bleiben vollständig. Preise sind nicht negativ, das Volumen ist ganzzahlig ab 0 oder leer. Ein leerer Schluss oder ein Schluss von 0 ist
eine Lücke der Quelle (`source_gap`), kein Kurs. Ein Eintrag, der nur aus `warning` besteht, wird übergangen; das ist vorsorglich und
nicht gemessen.

## Schnittstelle

- `daily_history`: `GET https://eodhd.com/api/eod/{Symbol}?from=…&to=…&period=d&fmt=json`, das Symbol im Pfad URL-kodiert;
  `from` = `request_start_date` (sonst `start_date`), `to` = `end_date`. Ausgewertet werden nur die Tage in `start_date`..`end_date`.
  Je Tag `date`, `open`, `high`, `low`, `close`, `adjusted_close`, `volume`.
- `search`: `GET https://eodhd.com/api/search/{Suchbegriff}?limit=…&fmt=json` → je Treffer `Code`, `Exchange`, `Name`, `Type`,
  `Currency`, `ISIN`. Vorschlag: Symbol `Code.Exchange`, Art aus `Type` (Common Stock → Aktie, ETF, Fund → Fonds …).
- `credential_check`: eine Suche mit einem Treffer; 200 → angenommen, 401/403 → abgewiesen (kostet einen Abruf).

Die Testantworten unter `fixtures/` sind erfunden: Aufbau wie bei EODHD, jede Zahl, jedes Symbol und jedes Datum erfunden.
