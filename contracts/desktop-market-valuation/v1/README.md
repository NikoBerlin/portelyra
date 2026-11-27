# Desktop Market Valuation v1 – Entwicklungsvertrag

Seit [ADR-211](../../../docs/decisions/ADR-211-reviewed-fx-attempts-in-eur-valuation.md)
liest die Bewertung gültige FX-No-result-Prüfentscheidungen über den gemeinsamen
Attempt-Validator. Geprüfte fehlende Resultate sind keine globale FX-Sperre mehr;
ungeprüfte Versuche und unveröffentlichte Resultate bleiben blockierend. Der
Validatorcode und die Nachweisdateien sind Teil der Quellen-/Frischebindung.

Siehe [ADR-198](../../../docs/decisions/ADR-198-calendar-bound-market-fx-valuation-reviews.md)
und [ADR-199](../../../docs/decisions/ADR-199-saved-calendar-valuation-and-fetch-requirements.md).

Privater CLI: `scripts/desktop_market_valuation.py`; Produkt-UI:
`apps/data/data_market_valuation_v1.R`. Einziger neuer Writer:
`migrations/reference/desktop_market_valuation_v1.py` für `market-valuation-v1`.

## Einfacher Modus und providerfreie Bewertung (ADR-212)

Siehe [ADR-212](../../../docs/decisions/ADR-212-simple-market-workflow-and-trade-price-reference.md).
`simple_absence_policy` und `use_trade_prices` sind optionale Booleans (CLI-Default
jeweils `false`). Einfacher Modus plus `last_valid` ersetzt native gespeicherte
Nichtveröffentlichungen begrenzt, ohne diese als Feiertage oder neue Originalkurse
zu speichern. Keine Kombination mit Expertenkalendern/Regeln/Ausnahmen.

Manuelle Assets benötigen zusätzlich ausdrückliche Trade-Preisfreigabe. Quelle
ist das abgeschlossene native Activity-Ledger desselben Assets und Datenraums;
keine Underlyingpreise oder automatischen Multiplikatoren. `trade_price_reference`
ist stets sichtbar ersatzwertgestützt, auch am Trade-Tag; danach nur begrenzt mit
`last_valid`. Unklare Reihenfolge, Währung, fehlender letzter Stückpreis und
Corporate Actions sperren. Kanonisches `unit_value` liefert 1 je Mengeneinheit;
`transaction_only` liefert keinen Kurs. Kein freier manueller Historieneditor.
Der bestehende Bewertungswriter bleibt alleiniger Eigentümer des Ergebnisstores.

## Commands

Jeder Aufruf bindet `context`, `data_space_path`, `payload`. Der CLI akzeptiert
höchstens 2 MB JSON, keine doppelten Schlüssel und keine nicht endlichen Zahlen.

- `prepare`: expliziter privater Entwurf, keine Provider-/Canonicalwrites.
  Targets aus frischer serverseitiger Inventory-/Mapping-/Promotionauflösung;
  `start_date`, `end_date`, Ziel EUR, Kalenderoptionen, maximale Fortschreibungsdauer,
  getrennte Börsen-/FX-Ausnahmen und optional `execution_ref` des geladenen Batches.
  Maximal 10000 Assets, 20001 Tage pro Zeitraum und 1 Million Assettage insgesamt.
  Optional `use_saved_calendars` (Default `false`): nur exakt Listing-/Pair-gebundene,
  kontextgeprüfte Profile mit passender Gültigkeit; nicht mit Regeln/Ausnahmen kombinieren.
  Kein stiller Kalenderfallback. Die Registry bleibt bei ausgeschalteter Option isoliert.
- `detail`: nur Lesen eines gebundenen Entwurfs/Ergebnisses, genau ein Assetordinal;
  einschließlich `market_requirements`/`fx_requirements` mit Bereichen und Tagesdispositionen.
  `requirements` in der Übersicht dedupliziert FX und zählt nicht prüfbare Tage explizit.
  `execution_authority=false`: diese Übersicht erteilt keine Abruf-/Publicationfreigabe.
  Die separate native `prepare-calendar`-Grenze (ADR-200) kann daraus eine erneut
  quellgeprüfte Batchvorschau erzeugen; Bestätigung, Abruf und Publication bleiben separat.
- `confirm`: neue serverseitige, maximal zehn Minuten gültige Bestätigung.
  Bei Stagequellen `desktop_market_valuation_staged_not_published`.
- `publish`: nur Abschluss des exakt bestätigten Bewertungsentwurfs. Alle Blobhashes
  und unveränderte Quellen prüfen; exakter Receipt-Replay schreibt nicht erneut.
- `list`: nur abgeschlossene Ergebnisse, `read_only=true`; kein mkdir bei leerem Store.
- `portfolio-input`: read-only Prüfung eines abgeschlossenen Ergebnisses für `preview_ref`
  und `as_of_date`; nur private Bindung plus Zählübersicht. Der bestehende Run Center
  kann diese Quelle separat bestätigen und publizieren, siehe [ADR-201](../../../docs/decisions/ADR-201-completed-eur-valuation-in-desktop-run-snapshots.md).

Der Browser erhält keine internen Asset-, Mapping-, Listing- oder Pair-IDs und
keine Datenraumpfade. Private Blobs erhalten Originalquellen und Kalenderprovenienz.
Die UI zeigt Ergebnisse je Tag als exakte Strings, gegebenenfalls Zähler/Nenner.

`ready` beschreibt bewertbare Tage des Entwurfs, nicht Providerpublication oder
Portfolioabschluss. `source_policy=staged_review_only` ist immer unabschließbar.
`incomplete` bleibt beim ausdrücklich bestätigten Ergebnisabschluss sichtbar;
keine Nullersetzung, kein stilles Weglassen ungeklärter Assets/Tage.

## Getrennte Bewertungsregel für Quelllücken (ADR-204)

Optional `valuation_policy={mode,max_age_days,age_unit}`: Ohne Parameter gilt
`strict`, null Höchstalter, `calendar_days`. `last_valid` verlangt ein explizites
Höchstalter 1–366 Kalendertage und überbrückt nur gespeicherte `source_gap`, keine
unabgerufenen offenen Handelstage oder technischen/Corporate-Action-Sperren.
Kurs und FX werden unabhängig geprüft. Die äußere Altersgrenze für belegte
Schließtage bleibt getrennt; nach einer Quelllücke gilt an Schließtagen die engere.

Public/Detail enthalten die versiegelte `valuation_policy`. `valuation_status`
unterscheidet `complete`, `substituted`, `incomplete`; Tagesbasen unterscheiden
`imputed_source_gap` und `imputed_after_source_gap` von regulärer Schließtagsableitung.
`substitution_used` kennzeichnet einen tatsächlich bewertbaren Ersatzwert. Summaries
zählen Markt-/FX-/EUR-Ersatzwerttage. Native Daten und Fetchbedarfe bleiben unverändert.
Modus/Alter binden die Bestätigung; Änderungen widerrufen sie. Keine automatische
Neuberechnung gespeicherter Abschlüsse. Siehe
[ADR-204](../../../docs/decisions/ADR-204-explicit-source-gap-valuation-policy.md).

## Assetauswahl im verzögert aufgebauten Bewertungsbereich

Die konstante `renderUI`-Oberfläche wird erst beim Anzeigen gebunden. Der Controller
wartet deshalb einmalig auf die Bindung des Umfang-Inputs, bevor er die gespeicherte
Inventarliste an `valuation_assets` sendet. Spätere Umfangwechsel senden keine neue
Liste und überschreiben keine inzwischen getroffene Auswahl. Inventaränderungen
aktualisieren Labels und behalten nur weiterhin vorhandene Referenzen. Keine
Freitexterzeugung; leere, doppelte oder unbekannte explizite Auswahl wird vor
Targetauflösung und CLI-Aufruf mit `desktop_market_valuation_selection_invalid`
abgewiesen, ohne stilles Weglassen. Eine leere Liste zeigt den Aktualisierungshinweis.

Der Produktbrowser-Test prüft beide Reihenfolgen (Inventar vor/nach Erstaufbau),
echte Suche/Trefferauswahl, eine Ein-Asset-Vorschau, Umfangwechsel mit
Bestätigungswiderruf und Ablehnung freier Texte. Shiny prüft zusätzlich die
fehlende vorzeitige Nachricht, Labelwechsel, entfernte Referenzen und ungültige
Auswahl ohne Serviceaufruf. Vor der Korrektur scheitert der Browser-Test schon
an der fehlenden Liste beim ersten Öffnen; reine `testServer`-Tests hatten die
verlorene DOM-Nachricht nicht erfasst.

Nicht Bestandteil der Autorität dieses Bewertungswriters: Providerfreigaben, Änderung versiegelter
Stages, automatische Kalenderstoremigration, automatischer Batch-Rebase, Activity-/Cash-/
FIFO-/Taxwrites und Portfolio-Snapshot-Publication. Keine Releasefreigabe durch diesen Vertrag.
