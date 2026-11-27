# Leser-Plugins v1 (`statement_reader_v1`, #486)

Ein Leser-Plugin liest die Belege eines Instituts (Kontoauszug, Export, Abrechnung) und liefert **Kandidaten**. Alles Weitere
bleibt bei Portelyra: Prüfen, Abgleich mit dem Bestand, Vorschau, Einmalbestätigung und Buchen. Die Schnittstelle ist offen,
damit auch andere Leser beitragen können. Ein Importer darf keinen Unsinn buchen. Deshalb stehen die Mindestanforderungen
unten ausdrücklich, und der Kern prüft sie, wo immer das möglich ist.

Stand rc.378: Bereiche `cash` (Kontobewegungen und Salden), `securities` (Wertpapiere), `fx` (Devisenkonten), `crypto`
(Krypto-Exporte der Börsen und Wallets), `reward` (Reward-Exporte der Börsen) und `income_statement` (Erträgnisaufstellung);
35 mitgelieferte Leser in 17 Plugins unter `plugins/readers/`.

Seit rc.378 prüft der Kern die Stufe der Schnittstelle (`api_minor`) und hält je Buchung fest, welcher Leser sie erzeugt hat.
Seit rc.379 durchläuft jeder Leser einen Selbsttest; Portelyra führt ihn beim Installieren aus. Die Anleitung steht in
`docs/handbuch/leser-entwickeln.md`.

Es folgt: Prüfstand je Portfolio sowie Installieren, Aktivieren und Entfernen in der Data-App (rc.380).

## Systemvoraussetzung

Leser laufen **nur abgeschottet**. Steht die Abschottung nicht zur Verfügung, gibt es keinen Import. Ungeschützt läuft er nie
(Festlegung vom 07.11.2026).

- Linux ab **Kernel 6.2** (Landlock ab Version 3) mit seccomp. Zum Beispiel reichen Ubuntu 24.04 und Debian 13, Debian 12 und
  Ubuntu 22.04 nicht.
- macOS und Windows: Import vorerst nicht verfügbar.
- Die App meldet die fehlende Voraussetzung mit der gefundenen Kernel-Version (`statement_reader_isolation_unavailable`).

## Aufbau eines Plugins

```
plugins/readers/<plugin_id>/
  manifest.json       Angaben unten, streng geprüft
  reader.py           Einstieg (verteilt auf die Module)
  reader_*.py         weitere Module des Lesers, je mit Prüfsumme im Manifest
  README.md           Handbuchseite: wofür, Export beim Institut, was geht, was nicht
  fixtures/           erfundene Testbelege, je Leser mindestens einer, mit <reader_id>.expected.json
```

| Feld | Bedeutung |
|---|---|
| `api_version` | `statement_reader_v1`; der Kern nimmt nur Plugins dieser Schnittstelle an |
| `api_minor` | Stufe der Schnittstelle innerhalb von v1, die das Plugin braucht (siehe „Versionen“) |
| `plugin_id` | gleich dem Ordnernamen, `[a-z][a-z0-9_]{1,40}` |
| `plugin_version` | `MAJOR.MINOR.PATCH` |
| `publisher` | Herausgeber; mitgelieferte Plugins: `Portelyra` |
| `institution`, `label` | Institut und Anzeigename |
| `entry_point`, `entry_point_sha256` | Einstieg und seine SHA-256-Prüfsumme; jede Abweichung verwirft das Plugin |
| `modules[]` | weitere Module (`path`, `sha256`). Python-Code im Ordner, den das Manifest nicht nennt, verwirft das Plugin |
| `handbook` | Handbuchseite im Plugin-Ordner |
| `readers[]` | je Leser: `reader_id` (`…_vN`), `domain`, `label`, `document_kind`, `extensions`, `detection`, `tested_formats`, `known_limits`; optional `combine` (liest die Belege eines Stapels zusammen, siehe unten) und `generator` (bringt einen Erzeuger für den Selbsttest mit) |
| `fixtures[]` | je Testbeleg: `domain`, `reader_id`, `input`, `expected` (beide unter `fixtures/`) |

Eine Leserkennung gilt je Bereich: `trade_republic_v1` gibt es als Cash- und als Wertpapier-Leser. Ein Plugin kann Leser mehrerer
Bereiche tragen: `bsdex` liest das EUR-Konto (`cash`) und die Krypto-Exporte (`crypto`).

Das Schema steht in `manifest.schema.json`. Der Kern prüft dasselbe in `migrations/reference/statement_reader_plugins_v1.py`.

### Versionen (rc.378)

Innerhalb einer Hauptversion (`statement_reader_v1`) kommen nur Ergänzungen dazu, nie Änderungen. `api_minor` nennt die Stufe,
die das Plugin braucht:

| Stufe | seit | eingeführt |
|---|---|---|
| 0 | rc.373 | Bereich `cash`, `read` |
| 1 | rc.374 | Bereiche `securities` und `fx`, `read_text`, `detect`, `finish` |
| 2 | rc.376 | Bereich `crypto`, Zusammenlesen (`combine`) |
| 3 | rc.377 | Bereiche `reward` und `income_statement` |
| 4 | rc.379 | Erzeuger für den Selbsttest (`generate`, `"generator": true`) |
| 6 | rc.425 | Unterkonto im Export eines Reward-Lesers (`subaccount_fallback`), siehe unten |
| 5 | rc.419 | Quellangaben eines Krypto-Lesers (`source`), Profile eines Wertpapier- oder Devisenlesers (`profiles`), Prüfstand des Formats (`format_checked`), Rezept des Eingangs (`intake`), eigene Kennung je Reward-Zeile (`row_ids`), siehe unten |

- Verlangt ein Plugin eine neuere Stufe, als der Kern kennt, wird es abgewiesen (`statement_reader_api_version_unsupported`,
  „braucht einen neueren Kern“).
- Nennt ein Manifest eine niedrigere Stufe, als es benutzt (etwa Bereich `reward` mit Stufe 0), ist es ungültig.
- Ein Plugin einer älteren Stufe bleibt lauffähig.

### Quellangaben eines Krypto-Lesers (Stufe 5, rc.419)

Bis rc.418 kannte der Kern jede Börse fest: Name, Institute, Unterkonten, Paarung, Auftragsfenster, Sonderfälle und Gründe. Seit Stufe 5
liefert das ein Krypto-Leser im Manifest unter `readers[].source`. Ein neues Börsen-Plugin braucht so keinen geänderten Kern.

| Feld | Bedeutung |
|---|---|
| `key` | Quelle der Zeilen, gleich ihrem Feld `source` (nicht `generic`, das gehört dem generischen Leser im Kern) |
| `label` | Name in Kontomasken, etwa „Kraken · Spot“ |
| `format_label` | Name des Formats in der Liste der lesbaren Exporte der Import-Karte, etwa „Kraken (Ledger-Export)“; ohne Angabe `label` |
| `institution_names` | Teile des Institutsnamens, an denen der Kontovorschlag die Konten der Börse erkennt |
| `wallets` | je Unterkonto im Export: Anzeigename (`label`) und Regel für den Kontonamen (`account_name`: mindestens ein Wort aus `any`, keines aus `none`) |
| `default_wallet` | dasselbe für alle übrigen Unterkonten; `label_prefix` steht vor dem Namen aus dem Export |
| `pairing` | `none`; `group` (Beine mit gleicher Kennung `group` werden zum Handel bzw. zur Umschichtung); `time` (Umschichtung als Abgang und Zugang gleicher Menge binnen `pair_window_minutes`, Gegenseite `pair_related_wallet`) |
| `internal_transfers` | Transfers zwischen Konten dieser Quelle gelten als Umschichtung (lockerer Abgleich bis 7 Tage) |
| `order_window_days` | Aufträge werden bis so viele Tage nach der Anlage ausgeführt (ohne Angabe 30) |
| `unpaired_reason_by_ticker` | Grund für einen Transfer ohne Gegenstück je Coin, etwa `{"SOL": "ledger_solana"}` |
| `reason_texts` | Texte der Gründe, die nur diese Quelle kennt; Platzhalter in geschweiften Klammern. Ein Text der eigenen Quelle geht dem allgemeinen vor. |

Ein Leser ohne `source` (etwa ein installiertes Plugin der Stufe 4) bekommt neutrale Vorgaben: sein Quellname als Anzeige, keine Paarung,
keine Umschichtung. Nennen zwei Plugins dieselbe Quelle, gilt das mitgelieferte bzw. das zuerst geladene.

### Profile eines Wertpapier- oder Devisenlesers (Stufe 5, rc.419)

Jede Zeile eines Wertpapier- oder Devisenlesers nennt ihr Profil (Feld `profile`, etwa ein Aussteller oder eine Kontoart). Was der Kern
bis rc.418 je Profil fest kannte, steht seit Stufe 5 unter `readers[].profiles`, je Profil:

| Feld | Bedeutung |
|---|---|
| `label` | Anzeige des Depots im Kontovorschlag, etwa „ING Direkt-Depot“ |
| `institution_names` | Institutsnamen am Konto, unter denen der Kontovorschlag das Depot sucht |
| `account_hint` | Wort im Kontonamen, wenn ein Institut Depots mehrerer Profile führt (eine Bank verwahrt für zwei Broker); ohne Angabe keiner |
| `depot_family` | Profile mit gemeinsamen Depots (zwei Aussteller desselben Brokers): Ein Beleg ohne Depotnummer gehört zum einzigen Depot der Familie; ohne Angabe das Profil selbst |

Ein Profil eines Lesers im Bereich `fx` ist ein Devisenprofil: Seine Zeilen buchen die Währung als Asset, die Saldoprobe der
Kontoauszüge gilt für sie. Ein Profil, das kein Manifest nennt, erscheint als „Depot“ ohne Kontovorschlag. Nennen zwei Leser dasselbe
Profil, gilt das mitgelieferte bzw. das zuerst geladene.

### Rezept des Eingangs (Stufe 5, rc.419)

Der monatliche Eingang ordnet die Unterordner des Belegordners Instituten zu und zeigt je Institut, was herunterzuladen ist. Bis rc.418
standen diese Rezepte als Tabelle im Kern; seit Stufe 5 bringt jedes Plugin das Rezept seines Instituts im Manifest mit (`intake`, auf
oberster Ebene, eines je Plugin):

| Feld | Bedeutung |
|---|---|
| `key`, `label` | Schlüssel und Name des Instituts im Eingang |
| `status` | `active` (Vorgabe) oder `historical`, wenn es das Angebot nicht mehr gibt; ob ein Konto des Nutzers ruht oder geschlossen ist, legt er am Konto fest |
| `folders` | Namen, unter denen ein Unterordner zum Institut gehört (ohne Groß-/Kleinschreibung, Leer- und Satzzeichen; ein Name, der so beginnt, auch) |
| `downloads`, `period`, `covers` | was herunterzuladen ist, die Zeitraumregel (`since_start`, `monthly`, `per_document`, `none`) und was es abdeckt |
| `readers` | Bereich und Leser in der Reihenfolge des Buchens, auch Leser anderer Plugins; Krypto-Leser erscheinen als gemeinsamer Krypto-Import |
| `account_words` | Wörter (klein) in der Institutsangabe der Konten, an denen Eingang und Ablage-Vorschlag die Konten des Instituts erkennen |
| `tax_all_accounts` | eine Steuerunterlage ohne Kontonummer gilt allen Konten des Instituts (nicht, wenn sich zwei Broker eine Bank teilen) |

Ein Unterordner ohne Rezept zählt mit seinem Namen als Institut, wenn der Name genau ein Institut der Konten trifft (Steuerunterlagen
ohne Kontonummer dann zu allen Konten dieses Instituts); trifft er keines oder mehrere, entscheidet wie ohne Institut die Kontonummer. Nennen zwei Plugins denselben Schlüssel, gilt das mitgelieferte bzw. das zuerst geladene.

### Eigene Kennung je Reward-Zeile (Stufe 5, rc.419)

`readers[].row_ids: true` (nur Bereich `reward`): Jede Zeile des Exports trägt eine eigene Kennung der Börse (`row_id`). Der
Zeilenschlüssel bindet dann nur Leser und Kennung, nicht die Datei – ein neuer Volldownload erkennt schon Gebuchtes wieder, und gebuchte
Rewards bekommen die Kennung als Belegangabe nachgetragen. Ohne Angabe bindet der Schlüssel Datei und Zeile. Welche Reward-Leser es
gibt, sagt allein die Leserliste; der Kern führt keine eigene.

### Unterkonto im Export (Stufe 6, rc.425)

`readers[].subaccount_fallback` (nur Bereich `reward`): Der Export nennt je Zeile ein Unterkonto (bei Kraken: Spot, Earn); der Wert ist
der Name, den der Leser setzt, wenn eine Zeile keines nennt (bei Kraken „Kraken“). Nur bei solchen Lesern heißt „gleiches
Börsenkonto“ auch „gleiches Wallet“: Die Data-App schlägt ein Konto dann auch für weitere Coins desselben Unterkontos vor – nicht für
den Ersatznamen. Bis rc.424 stand diese Liste fest in der Data-App (Festlegung 16.11.2026: ins Manifest).

### Prüfstand des Formats (Stufe 5, rc.419)

`readers[].format_checked` (jeder Bereich): `through` ist das jüngste Belegdatum, bis zu dem das Format des Lesers mit echten Belegen
geprüft ist, `checked_on` der Tag der Prüfung. Die Import-Karten zeigen „Format geprüft mit Belegen bis …“; jüngere Vorgänge liest der
Kern und kennzeichnet sie zum Vergleich mit dem Beleg. Ohne Angabe gilt das Format als noch nicht mit echten Belegen geprüft, und jeder
neue Vorgang wird gekennzeichnet. Der Krypto-Leser im Kern nennt das früheste `through` unter den Krypto-Lesern mit Angabe.
Messwerte aus Nutzerdaten (Zahl der Belege, erster Tag) gehören nicht hierher.

### Herkunft je Buchung (rc.378)

Jede Buchung aus einem Beleg trägt, welcher Leser sie erzeugt hat: `plugin_id`, `reader_id`, Bereich, `plugin_version` und
`code_sha256`. Die Prüfsumme läuft über Einstieg, Module, SDK, Host und seit rc.419 die Regeln im Manifest (siehe „An Ihren Belegen
geprüft“). Eine Buchung aus einem geänderten Leser trägt also eine andere Prüfsumme, auch bei gleicher Version. So lassen sich alle
Buchungen eines fehlerhaften Plugins finden.

- Die Ablage ist `asset-activity-reference-v1/activity-reader-provenance.sqlite` im Datenraum. Sie hängt nur an und zieht bei
  Korrekturen mit.
- Arten:
  - Buchung (`asset_event`);
  - Cash-Befehl (`cash_command`);
  - Betrag laut Erträgnisaufstellung (`taxable_document`);
  - Vorabpauschale (`advance_lump_sum`);
  - Split (`stock_split`).
- Eine Buchung kann mehrere Leser tragen, etwa einen Transfer aus zwei Exporten.
- Festgehalten wird in zwei Schritten:
  - beim Vorbereiten die Absicht, mit dem Leser, der gerade gelesen hat (Wertpapier/Krypto: CSV-Plan; Rewards: Entwurf);
  - nach jedem Buchen der Abgleich, auch bei einem fortgesetzten Import.

  So trägt ein Rollout zwischen Lesen und Buchen nicht den neueren Leser ein.
- Cash und Erträgnis lesen den Beleg beim Buchen neu und halten den Leser direkt fest.
- Gelingt das Festhalten nicht, bleibt die Buchung stehen. Die Herkunft gilt dann als „nicht verfügbar“, so auch für alles vor
  rc.378. Cash, Wertpapiere/Krypto und Erträgnis nennen es in ihrer Import-Meldung; für Rewards zeigt es ab rc.380 die Übersicht
  „Buchungen je Leser / ohne Herkunft“.

### Erkennungsregeln

`detection.match_any` ist eine Liste von Gruppen aus Teilzeichenketten. Ein Beleg kommt für den Leser in Frage, wenn eine Gruppe
**vollständig** in seinem Text vorkommt.

- Verglichen wird ohne Rücksicht auf Groß- und Kleinschreibung, mit zusammengezogenem Leerraum je Zeile.
- PDF-Belege werden dafür in Text umgewandelt, bei xlsx zählen die Zellinhalte, Textdateien werden als UTF-8 und als
  Windows-1252 gelesen.
- Reguläre Ausdrücke sind nicht erlaubt: Die Regeln sind schnell, nachvollziehbar und für den Kern ohne Risiko.
- Eine leere Liste heißt: Es entscheidet nur die Dateiendung.
- Die Regeln sind **Mindestbedingungen**: Ein Beleg, der sie nicht erfüllt, darf für den Leser nie lesbar sein.

### Aufruf

```python
def read(reader_id: str, source: bytes, file_name: str) -> dict            # Bereiche cash, reward: Beleg als Bytes
def read_text(reader_id: str, text: str, file_name: str) -> dict           # securities, fx, crypto, income_statement: Beleg als Text
def detect(reader_id: str, text: str) -> bool                              # securities, fx, crypto, income_statement: Erkennung
def finish(reader_id: str, batch: dict) -> dict                            # securities, fx: Nachbearbeitung des Stapels
def combine_documents(reader_id: str, documents: list) -> dict             # cash mit "combine": Belege zusammen lesen
def combine_rows(reader_id: str, batch: dict) -> list                      # crypto mit "combine": Zeilen mit Belegen abgleichen
def generate(reader_id: str, seed: int, domain: str) -> dict               # mit "generator": erfundener Beleg für den Selbsttest
```

- Ein Aufruf von `read` oder `read_text` liest genau einen Beleg. Der Kern bündelt alle Belege eines Stapels in einem
  abgeschotteten Prozess.
- `detect` läuft erst, wenn die Erkennungsregeln des Manifests passen.
- `finish` bekommt `{"candidates", "statements", "row_reasons"}`. Übernommen wird **nur die Ordnung am Tag**: `local_time`,
  `executed_local_time`, `execution_group`, `separate_executions`. Zahl, Reihenfolge und Belegkennung der Vorgänge müssen gleich
  bleiben; Beträge, Stücke, Daten und Gründe kann eine Nachbearbeitung nicht ändern.
- Dezimalzahlen gehen in beide Richtungen exakt als `{"decimal_text": "…"}` über, Zeitpunkte als `{"datetime_text": "…"}`
  (ISO 8601 mit Zone), Tupel als Listen.
- Ein Leser importiert nur die Standardbibliothek und das SDK `portelyra_reader_sdk_v1` (`plugins/readers/sdk/`). Das SDK
  liefert Betrags- und Tabellenhilfen, `abort(code)` und `pdf_text(source, file_name)`.
- PDF-Text erzeugt der Kern vorher mit `pdftotext -layout -nopgbrk`; ein Leser startet selbst kein Programm.
- Abbruch nur über `abort(code)` mit einem Code aus `error-codes.csv`. Jeder andere Code und jeder Absturz werden zu
  `statement_reader_failed`.

### Ergebnis in den Bereichen `securities` und `fx`

Schema: `securities-result.schema.json`. Ein Ergebnis ist einer von vier Fällen:

- **Vorgang** (`candidate`): Art (`buy`, `sell`, `dividend`, `deposit`, `advance_lump_sum`, `stock_split`), ISO-Daten,
  Dezimalzahlen als Text, Stückzahl und Kurs nie negativ, kein Buchungstag nach heute. `statement_checked` ist immer falsch:
  „abgeglichen“ setzt nur der Kern.
- **Grund** (`not_importable`): ein Code aus `reason-codes.csv`. Den Text setzt der Kern.
- **Export** (`multi`): viele Vorgänge und gezählte Gründe je Code.
- **Kontoauszug** (`statement`): Währung, Anfangs- und Endsaldo, Zeilen mit Betrag und den Vorgangsarten, die eine Zeile belegt.
  Saldenkette, Aufgehen und den Beleg je Zeile prüft der **Kern**.

### Ergebnis im Bereich `crypto`

Ein Export ist `multi` mit `candidates` (Zeilen), `row_reasons` (gezählte Gründe aus `reason-codes.csv`) und optional `evidence`;
ein unlesbarer Beleg ist `not_importable` mit einem Grund. Je Zeile:

- `source`, `file_name`, `row_no`, `wallet`, `ticker`, `at_utc` (`JJJJ-MM-TTThh:mm:ssZ`, nicht nach heute), `zone`;
- `kind` aus der festen Liste: `trade`, `trade_coin`, `trade_eur`, `swap`, `move`, `move_unknown`, `internal`,
  `internal_staking`, `internal_unstaking`, `fee_only`, `order`;
- `quantity` mit Vorzeichen (die Richtung), `fee_quantity`, `eur` und `eur_fee` als Dezimaltext oder `null`; Euro-Beträge und
  Stück-Gebühr nie negativ;
- `row_key`: Prüfsumme der Zeile, wie sie das SDK bildet (`CryptoSheet`). Der Kern rechnet sie nach; eine Zeile mit anderer
  Kennung verwirft das Ergebnis.

Aus den Zeilen bildet der **Kern** die Vorgänge (Kauf, Verkauf, Transfer zwischen Wallets, offene Fälle mit Grund). Ein Leser
bucht also nie einen Vorgang, er liefert nur, was im Export steht.

`evidence` belegt Zeilen anderer Exporte, bucht aber selbst nichts: Die BSDEX-Transaktionshistorie liefert
`{"bsdex_executions": [...]}`, je Ausführung `id`, `ordinal`, `file_name`, `side`, `asset`, `quantity`, `eur`, `fee`, `at`.

### Zusammen lesen (`combine`, rc.376)

Manche Institute brauchen mehrere Belege für einen Betrag: Der BSDEX-Export rundet je Order auf den Cent, erst die
Transaktionshistorie nennt die Ausführungen genau. Ein Leser mit `"combine": true` bekommt dafür den ganzen Stapel.

- **cash** (`combine_documents`): alle Belege des Stapels auf einmal. Das Ergebnis hat genau die Schlüssel `candidates`,
  `diagnostics`, `files`, `unreadable`, `chain_gaps`, `held_back`, `evidence`. Die Bewegungen prüft der Kern wie jedes
  Cash-Ergebnis. Eine Order oder Euro-Bewegung ohne Beleg in der Historie hält den Stapel an; je Grund steht eine Lücke in der
  Vorschau, mit der ersten betroffenen Order (bei BSDEX dieselben Gründe wie oben, dazu fehlende Euro-Bewegungen).
- Zusammen lesen darf nur ein Leser, der `"combine": true` im Manifest erklärt; sonst lehnt der Kern den Aufruf ab.
- **crypto** (`combine_rows`): die Zeilen des Stapels, je mit `combine_ref`, und die Ausführungen aus `evidence`. Zurück kommen die
  Zeilen mit genauem Betrag. Der Kern (`apply_crypto_combine_v1`) übernimmt nur, was diese Regeln erfüllt:
  - Jede Zeile kommt mit ihrem `combine_ref` zurück, keine fehlt, keine ist erfunden.
  - Ändern darf der Leser nur `quantity`, `eur`, `eur_fee`, `at_utc`, `kind` und `row_key`. Eine Order darf er in Teile je
    Ausführungstag zerlegen; die Stückzahl je Order bleibt gleich.
  - Die Art wechselt höchstens von `trade` zu `unpriced_trade`: Fehlen die Ausführungen, bleibt die Order offen und wird nie zum
    gerundeten Betrag des Exports gebucht. Andere Zeilen als Trades bleiben unverändert.
  - Eine offene Order nennt immer ihren Grund (`unpriced_reason`, Festlegung vom 08.11.2026: so genau wie möglich). Den Text setzt
    der Kern, mit Datum, Menge und Beträgen:

    | Grund | bedeutet | zusätzlich |
    |---|---|---|
    | `history_missing` | keine Historie für das Jahr der Order | `history_year` |
    | `history_outdated` | die Historie endet, bevor die Order angelegt wurde | `history_until` (ISO-Datum) |
    | `no_executions` | die Historie deckt den Tag ab, im Zeitraum der Order liegt aber keine Ausführung ihrer Richtung | – |
    | `quantity_differs` | Ausführungen im Zeitraum, ihre Menge geht nicht auf | – |
    | `amount_differs` | Ausführungen ergeben die Menge, aber nicht den Kurswert | `executions_eur`, `executions_fee` |
    | `ambiguous` | zu viele Möglichkeiten, keine eindeutige Zuordnung | – |

    Der Kern verlangt genau die Felder des Grundes und prüft ihre Form. Ob sie stimmen, kann er nicht nachrechnen. Deshalb belegt
    „Im Editor öffnen“ bei einer offenen BSDEX-Order nie einen Betrag vor; beide Beträge stehen im Grund.
  - Euro-Betrag und Gebühr je Order weichen höchstens 5 Cent vom Export ab. Weicht eine einzelne Order mehr ab, bleibt nur sie
    offen, mit eigenem Grund („Betrag weicht vom Export ab“, beide Beträge im Text), und der Rest des Stapels läuft weiter. Weichen mehr als ein Viertel der
    Orders ab (mindestens zwei), rechnet der Leser systematisch falsch, und das ganze Ergebnis wird verworfen (Festlegung vom
    08.11.2026).
  - Jeder andere Verstoß verwirft das Ergebnis (`statement_reader_output_invalid`).

### Ergebnis im Bereich `reward` (rc.377)

Ein Reward-Export ist `{"time_zone", "fee_role", "rows"}`: die Zeitzone der Zeitangaben, die Rolle der Gebühr (`none`, `monetary`,
`asset_quantity`) und je Zeile des Exports:

- `cells` (die Zellen der Zeile), `row_id` (die Kennung der Börse oder leer), `signature` (sieben Merkmale für doppelte Zeilen über
  mehrere Dateien: Zeit, Art, Unterart, Coin, Menge, Gebühr, Konto) und `kind` (`reward`, `other`, `invalid`);
- bei einem Reward zusätzlich `asset` (groß geschrieben), `quantity` (über 0), `local_date` (nicht nach heute), `local_time`, `fee`
  (über 0 oder `null`), `account` und `valuation` in genau einer Form: `fiat_total` mit Gesamtbetrag, `unit_price` mit Stückpreis
  (beide mit Währung) oder `none`.

Der Kern bildet daraus die Zeilenschlüssel (die Kennung der Börse allein, ohne Kennung Datei und Zeile), erkennt doppelte Zeilen über
Dateien, wendet den gewählten Zeitraum an und baut die Kandidaten. Jede Zeile wird gezählt; ein Reward erreicht die Buchung nur über
Zuordnung, Vorschau und Bestätigung. Das SDK liest ein Profil mit `reward_export(source, profile)`.

### Ergebnis im Bereich `income_statement` (rc.377)

`{"tax_year", "summary_line7", "postings"}`: Steuerjahr, Zeile 7 des Summennachweises und die Posten. Je Posten unter anderem `kind`
aus `sale`, `dividend`, `interest`, `fund`, `ignored`, `unclear`, `isin`, Valuta und Zufluss, `amounts` je Zeile, `taxable` und
`line7`. Wer einen Kapitalertrag übernimmt (`sale`, `dividend`, `interest`, `fund`), trägt ihn genau als Anteil an Zeile 7;
`ignored` und `unclear` tragen keinen. Die Summe der Posten und den Abgleich mit Zeile 7 rechnet der Kern selbst. Den PDF-Text erzeugt
der Kern.

### Ergebnis im Bereich `cash`

Schema: `cash-result.schema.json`.

- `candidates[]`: `source_row_ordinal` (≥ 1), `local_date` (ISO), `kind` (`interest`, `deposit`, `withdrawal`),
  `amount_decimal` (positive Dezimalzahl als Text), `balance_after_decimal` (Text oder `null`), `text`. Optional sind
  `value_date` und `gross_income_decimal`.
- `diagnostics[]`: `source_row_ordinal` (≥ 0), `reason_code`. Optional sind `gross_income_decimal` und `as_of_date`.
- `summary`: `opening_balance_decimal`, `closing_balance_decimal`, `period_from`, `period_to`, optional `closing_as_of_date`.
- Optional auf oberster Ebene: `balance_proof`, `balance_anchor_only` (wahr/falsch).
- Die Uhrzeit eines Tages ohne Zeitangabe setzt der Kern (12:00 plus Reihenfolge).

## Mindestanforderungen an jeden Leser

**Vom Kern bei jedem Aufruf geprüft.** Bei einem Verstoß wird das Ergebnis des Belegs verworfen; Leser und Grund werden genannt.

1. Das Manifest ist gültig, die Prüfsumme des Codes stimmt, die Schnittstellenversion passt, und je Leser gibt es einen Testbeleg.
2. Das Ergebnis folgt dem Schema des Bereichs:
   - exakte Dezimalzahlen als Text, keine Gleitkommazahlen;
   - gültige ISO-Daten, kein Buchungs- oder Wertstellungstag nach heute (Datum des Rechners). Ein solcher Tag heißt fast immer,
     dass der Leser das Jahr falsch erschlossen hat. Zeitraumangaben dürfen in die Zukunft reichen;
   - nennt der Beleg seinen Zeitraum (`period_from` bis `period_to`), liegt jede Buchung darin. Das fängt ein falsch erschlossenes
     Jahr auch bei alten Auszügen ab. Leser, die den Zeitraum aus der ersten und letzten Buchung bilden, schützt das nicht; sie
     sollen den Zeitraum lesen, wo der Beleg ihn nennt;
   - nur erlaubte Arten;
   - Beträge positiv, die Richtung steht in der Art;
   - Zeilennummern als ganze Zahlen.
3. Abbruch nur mit Codes aus der festen Liste.
4. Laufzeit (120 s), Speicher (2 GB), Ausgabe (32 MB) und Zeilenzahl (100 000) sind begrenzt.

**Durch den Aufbau garantiert**

5. Ein Leser schreibt nie. Abgleich mit dem Bestand, Vorschau, Einmalbestätigung und Buchen bleiben im Kern.
6. Kein Netz (seccomp sperrt Sockets) und kein Dateizugriff außer auf den Beleg, das Plugin und das SDK (Landlock). Die
   Quelldatei bleibt unverändert.
7. Nennt der Beleg Salden, rechnet der Kern nach und zeigt, wenn es nicht aufgeht. Bei den Kontoauszügen der Devisenkonten prüft
   der Kern zusätzlich die Kette der Auszüge und ob jede Zeile ihren Beleg hat. Ein Plugin meldet seine Belege nie selbst als
   abgeglichen.
8. Eine Nachbearbeitung ändert nur die Ordnung am Tag; der Kern übernimmt nichts anderes. Beim Zusammenlesen von Krypto-Zeilen
   bleibt die Stückzahl je Order gleich, und der Betrag darf vom Export nur um Rundung abweichen (siehe oben).
9. Krypto-Vorgänge bildet der Kern aus den Zeilen; ein Leser liefert keine Buchung. Ebenso bei Rewards: Schlüssel, doppelte Zeilen,
   Zeitraum und Kandidaten bleiben im Kern; bei der Erträgnisaufstellung rechnet der Kern Summe und Zeile 7 nach.

**Beim Aufnehmen und beim Installieren geprüft**

10. Jeder Leser trifft seine erfundenen Testbelege genau, zweimal gleich und in zwei frischen Prozessen.
11. Die Testbelege erfüllen die eigenen Erkennungsregeln.
12. Das Manifest nennt getestete Formate samt Zeitraum und mindestens eine bekannte Grenze.

**Geplant (rc.380)**

- Dieselbe Prozedur für jeden Leser, auch die mitgelieferten:
  - Prüfstand je Portfolio („an Ihren Belegen noch nicht geprüft“);
  - erster Import nur nach ausdrücklicher Bestätigung;
  - deutliche Warnung bei Exporten ohne Saldo.
- Installieren nur nach bestandenem Selbsttest (mit Erzeuger) und passender Stufe.

## Selbsttest (rc.379)

`migrations/reference/statement_reader_selftest_v1.py` prüft jeden Leser in drei Stufen, abgeschottet wie im Betrieb.

1. **Testbelege:** Sie werden genau getroffen, gleich in zwei frischen Prozessen und gleich in einem gemeinsamen Prozess mit
   vertauschter Reihenfolge. Ein Leser darf sich nichts von früheren Belegen merken.
2. **Veränderte Belege:** Aus den Testbelegen und aus den erfundenen Belegen der Stufe 3 entstehen zufällig verstümmelte Fassungen:
   abgeschnitten, Zeilen weg, doppelt oder vertauscht, Zeichen gekippt, Fremdzeile, anderer Zeichensatz, leer. Die erfundenen Belege
   erreichen Zweige, die kein Testbeleg zeigt.
   - Erlaubt sind ein Ergebnis in gültiger Form oder ein Code aus der festen Liste.
   - Durch fällt ein Absturz, eine Zeitüberschreitung, ein fremder Code oder ein Formfehler: falsche Typen, unbekannte Felder oder
     Arten, negative Beträge, ungültige Daten.
   - Unplausible Werte werden nur gezählt (Festlegung vom 08.11.2026), etwa ein Tag nach heute oder eine Buchung außerhalb des
     genannten Zeitraums. Verstümmelte Ziffern ergeben sie zwangsläufig, und der Kern weist sie im Betrieb ab.
3. **Erfundene Belege:** Ein Leser mit `"generator": true` liefert über `generate(reader_id, seed, domain)` je Startwert
   `{"file_name", "content", "expected"}`. `content` sind Bytes in den Bereichen `cash` und `reward`, sonst der Text, wie ihn der Kern
   dem Leser gibt.
   - Der Leser muss den Beleg in einem frischen Prozess genau treffen.
   - Der Beleg erfüllt die Erkennungsregeln.
   - Derselbe Startwert ergibt denselben Beleg.
   - Das erwartete Ergebnis baut der Erzeuger aus seinen erfundenen Vorgängen, nie durch Aufruf des eigenen Lesers.
   - Die Byte-Order-Mark schneidet der Selbsttest wie der Kern nur im Bereich `crypto` ab.

Das SDK hält die Formgrenzen des Kerns schon beim Lesen ein: `german_day` und `candidate` brechen bei einem Tag oder einer Uhrzeit, die
es nicht gibt, mit `securities_statement_source_invalid` ab; `CryptoSheet` verwirft eine Zeile außerhalb der Grenzen (Jahr, Ticker,
Textlänge, negative Gebühr oder Euro) als `crypto_unreadable_row`. Ein verstümmelter Beleg verliert so höchstens sich selbst oder
eine Zeile, nie das ganze Ergebnis.

**Verworfene Krypto-Zeilen einzeln** (Festlegung 08.11.2026: Zeile und Feld als Grund, Zeile der Datei nennen):

- Ein Krypto-Ergebnis darf `row_details` tragen: je verworfener Zeile `{"row_no", "reason_code", "field", "problem"}`, dazu `"line"`, die
  Zeile in der Datei wie in einer Tabellenkalkulation (Vorspann über der Kopfzeile und Felder über mehrere Zeilen mitgezählt).
- `field` ist eines von `time`, `ticker`, `quantity`, `fee_quantity`, `eur`, `eur_fee`, `price`, `number` (eine Zahl ohne festes Feld),
  `wallet`, `transaction_id`, `hash`, `address`, `group`, `quote`, `file_name`, `zone`. `problem` ist eines von `missing`, `unreadable`,
  `negative`, `too_long`, `out_of_range`.
- Der Kern prüft die Angaben: nur Gründe, die das Ergebnis zählt, und nie mehr Einzelangaben als gezählte Zeilen. Den Text setzt er
  selbst, etwa „Zeile 18 der Datei nicht gebucht: Euro-Betrag ist negativ“. Ohne `line` nennt er die Zählweise („Datenzeile 17, gezählt
  ab der ersten Zeile unter der Kopfzeile“).
- Im SDK: `csv_dict_rows` hält je Zeile `file_lines` fest; ein Leser zählt seine Zeilen mit `sheet.numbered(rows)` statt
  `enumerate(rows, 1)`. `CryptoSheet.add` gibt Feld und Problem selbst an; eigene Abbrüche mit
  `sheet.skip("crypto_unreadable_row", number, field, problem)`.
- Im Selbsttest vergleicht die Erwartung `row_details` nur, wenn sie sie nennt; die Zählung je Grund immer.

Grenze, offen benannt: Der Erzeuger stammt vom Plugin. Eine falsche Deutung des Formats findet er nicht. Dafür gibt es seit rc.380
die Bestätigung an den eigenen Belegen (siehe „An Ihren Belegen geprüft“).

## An Ihren Belegen geprüft (rc.380)

Festlegungen vom 07. und 09.11.2026:

- Ein Leser bucht in einem Portfolio erst, wenn eine Vorschau mit genau diesem Plugin-Code ausdrücklich bestätigt wurde
  (Häkchen vor dem Buchen). Danach gilt er dort als „an Ihren Belegen geprüft“; die Vorschau zeigt bis dahin einen Hinweis.
- Version heißt: Prüfsumme über die eigenen Dateien des Plugins (Einstieg, Module) und seit rc.419 über die Regeln im Manifest. Eine
  geänderte Hilfsbibliothek (SDK, Host) ist nur ein Hinweis. Die Herkunft je Buchung behält die volle Prüfsumme.
- Regeln im Manifest (rc.419, Festlegung 15.11.2026): alles, was steuert, wie Belege zu Buchungen werden – Erkennung, Dateiarten,
  Zusammenlesen, Quellangaben der Krypto-Leser (Unterkonten, Paarung, Fenster), Profile der Wertpapierleser (Institutsnamen,
  Kontohinweis, Depotfamilie) und das Institut. Ändert ein Update nur dort etwas, gilt der Leser wieder als ungeprüft. Nicht dazu zählen
  Beschreibungen (Namen, Formattexte, Grenzen, Version, Handbuch, Testbelege, Prüfstand des Formats, Texte der Gründe) und das Rezept des
  Eingangs, das nur ablegt. Ein neues Manifestfeld zählt mit, bis es ausdrücklich als Beschreibung gilt (`manifest_rules_sha256_v1`).
- Umzug der Regeln aus dem Kern in die Manifeste (rc.419): Eine Prüfung aus der Zeit davor gilt weiter, solange die Regeln eines
  mitgelieferten Plugins genau dem Stand von rc.419 entsprechen (`RULES_BASELINE_RC419`).
  Ändert ein späteres Release die Regeln eines Plugins, fällt sein Eintrag dort weg.
- Nachgerechnet wird nur, was der Beleg hergibt (Saldoprobe, Summenprobe der Erträgnisaufstellung). Belege ohne Saldo bekommen,
  solange der Leser ungeprüft ist, eine deutliche Warnung: Bis zur Bestätigung prüft allein der Vergleich der Vorschau mit den Belegen.
- In Datenräumen aus der Zeit vor rc.380 gelten die mitgelieferten Leser über einen einmaligen Eintrag „Bestand bis rc.379“ als geprüft.
- Speicher: `asset-activity-reference-v1/activity-reader-checks.sqlite`, nur anhängend, je Portfolio. Python prüft den Stand vor dem
  Buchen selbst nach (`statement_reader_unchecked`) und hält ihn nach dem Buchen fest.
- Das Wort „Prüfstand“ meint weiter den älteren, datumsbezogenen Stand „geprüft bis“ je Leser.

## Aktivieren je Portfolio, Installieren aus Datei, Kompatibilität nach Updates (rc.381)

Festlegungen vom 09.11.2026:

- **Aktivieren je Plugin und Portfolio.** Neue Portfolios starten ohne aktive Leser. Portfolios, die vor rc.380 angelegt wurden,
  bekommen beim ersten Kontakt alle mitgelieferten Plugins aktiv („Bestand bis rc.380“). Die Einstellungen stehen im Datenraum und
  bleiben über Updates erhalten; ein neu mitgeliefertes Plugin startet nicht aktiv und heißt im Reiter „Leser“ „neu – noch nicht eingestellt“.
- **Inaktive Leser** fehlen in den Auswahllisten der Import-Karten und in „Automatisch erkennen“. Eine Krypto-Datei einer nicht aktiven
  Börse wird mit Grund (`reader_inactive`) aussortiert, die übrigen laufen weiter. Ein Vorgang, dessen Leser im Portfolio seines Kontos
  nicht aktiv ist, bleibt einzeln offen. Der Kern sperrt das Buchen (`statement_reader_inactive`), auch mit Häkchen.
- **Fremde Plugins als ZIP** (`statement_reader_admin_v1.py`): sicher entpacken (keine Verknüpfung, kein Pfad nach außen, höchstens
  10 MB gepackt, 20 MB entpackt, 300 Dateien), Manifest und Schnittstellenstufe, keine Kennung eines mitgelieferten Plugins oder Lesers,
  Erzeuger für jeden Leser, Selbsttest mit echtem Datum. Installiert wird nur bei bestandenem Test, unveränderlich unter
  `statement-reader-plugins-v1/plugins/<plugin_id>/<version>-<prüfsumme>/<plugin_id>/`; `installed.json` nennt die geltende Fassung.
  Installieren aktiviert nichts. Vorerst nur die Bereiche Cash, Wertpapiere, Devisen und Krypto (`statement_reader_install_domain_unsupported`).
  Ein installiertes Plugin gilt nie als „von Portelyra geprüft“, auch wenn sein Manifest das behauptet.
- **Entfernen** nur bei installierten Plugins: Es wird in allen Portfolios deaktiviert und nicht mehr geladen; die Dateien bleiben.
- **Kompatibilität nach Updates:** Mitgelieferte Plugins laufen vor jedem Release durch Selbsttest und Gegenprobe. Installierte testet
  Portelyra nach jedem Update automatisch neu, bevor sie wieder lesen (Kennung: Plugin-Code, SDK/Host, Produktversion). Durchgefallen →
  gesperrt (`statement_reader_incompatible`), bis eine bestehende neue Fassung installiert ist.
- Die Einstiegs-Skripte laden die installierten Plugins des Datenraums (`use_data_space_plugins_v1`); die Leserlisten von Cash,
  Wertpapieren und Krypto bauen sich danach neu auf.

Der Bericht nennt Leser, Belegnamen, Veränderungen und Codes, nie Inhalte.

## Abschottung

`workers/import_plugin_sandbox_v1.py` startet den Host `workers/statement_reader_host_v1.py` mit `python -I -B`:

- Landlock: Lesen nur unter `/usr`, im Laufzeitverzeichnis, im Plugin-, SDK- und Eingabeordner; Schreiben nur im eigenen
  Ausgabe- und Temporärordner.
- seccomp: keine Sockets.
- Startet ein Leser trotzdem ein Programm, gelten für dieses dieselben Grenzen.
- **Leserprozess je Vorgang (rc.375):** Innerhalb eines Vorgangs bleibt je Plugin ein abgeschotteter Prozess offen und arbeitet die
  Aufträge nacheinander ab. Ein Vorgang ist ein Import-Stapel, eine Erkennung oder ein Ablage-Vorschlag. Der Prozess spart so den
  Start je Aufruf.
  - Mit dem Ende des Vorgangs endet der Prozess. Belege verschiedener Vorgänge teilen sich nie einen Prozess, ein Leser trägt nichts
    von einem Import in den nächsten.
  - Die Rechenzeit ist je Vorgang begrenzt (900 s), die Wartezeit je Auftrag (120 s). Wird sie überschritten, beendet der Kern den
    Prozess.
  - Ohne Vorgang startet jeder Aufruf frisch.
- Grenzen für Rechenzeit, Speicher, Dateigröße und Dateizahl; kein Core-Dump.
- Der Host lädt genau ein Plugin, führt je Auftrag einen Schritt aus (`read`, `read_text`, `detect`, `finish`,
  `combine_documents`, `combine_rows`) und schreibt `result.json`. Der Kern prüft Form und Inhalt.

## Fehlercodes

`error-codes.csv` nennt die Codes, mit denen ein Leser abbrechen darf (`reader`), und die Codes des Kerns (`core`).
`reason-codes.csv` ist die feste Liste der Gründe, die ein Wertpapier-, Devisen- oder Krypto-Leser nennen darf, samt dem Text, den der Kern
anzeigt.
