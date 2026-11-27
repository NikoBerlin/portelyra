# Desktop Market/FX batch execution v1

Owner-lokale Koordination mit injiziertem Executor; kein Providerdefault, keine
Publication-Autorität im Abrufkoordinator, kein Startup-Hook. Die zentrale Produkt-UI
bindet die getrennten Autoritäten über den privaten R-Service an (ADR-196).

## Bindung und Bestätigung

Der Koordinator verwendet intern `execution_version=2`. Die Bestätigung bindet den
**vollständigen** Batch einschließlich privater Adaptervorschauen und Runtime-Kontext.
Der von R gelieferte `batch_fingerprint` allein ist kein Integritätsnachweis.
`content_fingerprint` verwendet UTF-8-JSON mit sortierten Schlüsseln, kompakten
Separatoren, unveränderten Unicode-Strings und ohne NaN/Infinity. R muss diesen Hash
nicht selbst berechnen, sondern die öffentliche Bindungsvorschau unverändert halten.
Eine Bestätigung gilt höchstens 600 Sekunden; Execute prüft alle Erzeugungsregeln.

`desktop_market_fx_batch_binding_v1.py` verbindet serverseitig aufgelöste Ziele mit
nativen read-only Market-/FX-Vorschauen. Market bindet Listing, Mappingrevision und
Promotion; FX bindet gerichtetes Paar, Providerbindung und angeforderten Bereich.
Die bestätigte öffentliche Projektion enthält keine privaten Adapterpayloads.
Vor Transport prüfen die nativen Market-Grenzen das aktuelle Mapping; der FX-Adapter
prüft zusätzlich aktuelle Paarbindung und Coverage erneut. Stale Evidenz blockiert.

## Persistenz und Wiederanlauf

- Exklusive nichtblockierende `flock`-Sperre über den gesamten Ausführungsaufruf.
- Owner-Verzeichnis `0700`, Dateien ab dem ersten Byte `0600`; keine Symlinkziele.
- Kontext-/Datenraumpfadbindung des Bereichs; Kopieren in einen anderen Pfad ist
  **keine** Recovery und wird abgewiesen.
- Atomare Dateiablösung sowie Datei- und Verzeichnis-`fsync` vor jedem Callback.
- `pending → provider_call_started → staged`; das Resultat bleibt privat persistent.
- Exception oder Prozessabbruch nach dem Claim bedeutet `recovery_required`, nicht
  nachgewiesenen Providerfehlschlag. Kein Retry und kein automatischer Fallback.
- Execute-Replay liest nur den vorhandenen Zustand und setzt ihn nicht implizit fort.
- Resume erfordert eine frische Bestätigung und führt ausschließlich `pending` aus;
  bei unbekanntem begonnenem Ausgang bleibt es gesperrt.
- Explizite Recovery verwendet lokal validierte Staging-Evidenz oder seit ADR-197
  einen exakt gebundenen nativen Market-Fetch-Fehler mit nativer Recovery-Quittierung.
  Das Item wird dann terminal `failed`, mit vollständigem privatem Ergebnis und Hash.
  Fehlende Evidenz beweist keinen fehlgeschlagenen Provideraufruf und entsperrt nicht.
  Für FX ohne terminales natives Fehlerreceipt bleibt die Sperre bestehen.
- `failed` ist kein Coverage-Erfolg und kein Retry-Grant. Der ursprüngliche Bereich
  bleibt reserviert; nur `pending` darf explizit weiterlaufen. Ein Batch mit lediglich
  `published`/`failed` heißt `completed_with_failures`, nicht `published`.
- Native gestagte Reviews sind nach echtem Prozessende ohne R-Sessioncache lesbar.
- Öffentliche Fehlercodes sind fest begrenzt; private Exceptiontexte werden verworfen.

Version-1-Zustände aus der früheren synthetischen Referenz werden nicht automatisch
übernommen. Hashes dienen Integrität und Bindung, nicht Authentifizierung gegen einen
Angreifer mit denselben OS-Schreibrechten. Die injizierten Adapter sind vertrauenswürdig;
Browserpayloads dürfen niemals als Executor oder serverseitige Zielauflösung dienen.

## Mehrbereichs-Review und getrennte Veröffentlichung (ADR-195)

Mehrere disjunkte, aufsteigend angeordnete Market-Bereiche desselben Listings sind
planbar. Der erste darf stagen; Nachfolger bleiben explizit `pending`, **ohne Claim**,
bis alle vorangegangenen Bereiche veröffentlicht oder per nativer Fehlerquittierung
explizit als fehlgeschlagen abgeglichen sind (ADR-197). Andere Listings und FX-Items
können weiter stagen. Keine Vorabveröffentlichung und kein stilles Überspringen.
Überlappende Bereiche oder mehrfach versteckte Paar-/Listing-Routen werden abgewiesen.

`desktop_market_fx_batch_publication_v1.py` erzeugt eine rein lesende Auswahlvorschau
bereits gestagter Reviews. Eine eigene zeitgebundene Bestätigung bindet ihre exakten
Inhalte, Dispositionen und Fortschrittsfingerprints. Die Abrufbestätigung reicht nicht.
Vor jedem nativen Write steht ein dauerhafter Publication-Claim unter derselben
Prozesssperre. Ein Replay setzt angefangene Veröffentlichungen niemals automatisch fort.

Bei unbekanntem Write-Ausgang bleibt `publish_started` gesperrt. Explizite Recovery
prüft bestehende lokale Staging-Evidenz und kanonische Request-Receipts. Für FX existiert
ein read-only Receipt-Reader mit Fingerprint-/Zeilen-/Anzahlprüfung. Market-Recovery
wählt exakt den gebundenen Stage statt versehentlich das neueste Listing-Review.
Kein erneuter kanonischer Write zur Diagnose; ein fehlendes Receipt lässt gesperrt.

`scripts/desktop_market_fx_batch.py` bietet eine strikte private JSON-stdin-Grenze.
Der neue R-Service `apps/data/data_market_fx_batch_service_v1.R` hält private Payloads
im Server-Closure und trennt Vorbereitung, Abrufbestätigung, Ausführung, Review und
Publication. Konstruktion führt weder CLI-Aufrufe noch Writes aus. Explizites Lesen
nach Neustart lädt den Batch über eine kontextgebundene, opaque Execution-Referenz.

## Ausgewählte wartende Abrufe (ADR-206)

Die Produkt-UI verwendet ausschließlich `confirm-selected` mit expliziten
`ordinals`. Der resultierende v3-Grant bindet den vollständigen Batch samt privaten
Zielen, Kontext, absoluten Datenraumpfad und genau die ausgewählten Ordinals.
Ungültige oder nicht mehr wartende Auswahl blockiert, statt still erweitert oder
reduziert zu werden. Keine Vorauswahl. Auswahländerungen widerrufen die Autorität.

Unter der bestehenden Prozesssperre werden Startfähigkeit und Vorgänger erneut
geprüft. Die zusätzliche owner-only `.fetch-grant-<fingerprint>.json`-Quittung
verbraucht den Grant atomar und dauerhaft vor dem ersten Provider-Claim. Sein
Replay setzt auch nach Crash/Recovery keine verbleibenden Bereiche fort. Ein
neuer, ausdrücklich bestätigter Grant darf ausschließlich weiterhin wartende
Bereiche auswählen. Begonnene/fehlgeschlagene Items sind niemals Retry-Kandidaten.

Vor dem ersten v3-State/Verbrauch wird der permanente Capabilitymarker
`.selected-fetch-authority-v1.json` mit `capability_version=1` und
`minimum_writer_capability=selected_market_fx_fetch_grants_v1` dauerhaft gespeichert.
Der native Runtime-Rollback blockiert ältere Ziele ohne ADR-206-Deklaration vor
Journalanlage/Slotbewegung und bei Wiederaufnahme. Kein Marker beim bloßen Upgrade.

V2-Ausführungsdateien bleiben kompatibel; kein Rebase und keine Migration ihrer
ursprünglichen Bestätigung oder gebundenen Bereiche. Ungewählte Items und native
Ergebnisse bleiben erhalten. Andere gestagte Reviews dürfen offen bleiben,
während unabhängige ausgewählte Bereiche stagen. Unbekannte Schreibausgänge und
unveröffentlichte notwendige Market-Vorgänger bleiben Sperren. Die alte explizite
V2-Vollbatch-Referenzschnittstelle bleibt kompatibel, wird von der Produkt-UI aber
nicht mehr zur Bestätigung verwendet.

Der unveränderliche ursprüngliche Plan wird als solcher einklappbar angezeigt;
seine geplanten Provideraufrufe sind kein aktueller Coverage- oder Ausführungsstand.
Details und Tests: [ADR-206](../../../docs/decisions/ADR-206-selected-pending-batch-fetch-authority.md).

## Produktgrenzen (#352)

Die sichtbare UI ist über `data_market_fx_batch_ui_v1.R` angebunden. Private Asset-ID
und Mapping-Asset-ID müssen im serverseitigen Resolver übereinstimmen; Anzeigenamen
sind keine Identitätsautorität. Eine neue Vorschau darf ungelöste ältere FX-/Market-
Bereiche nicht umgehen. Überlappende Ausführungen bleiben ohne weiteren Abruf gesperrt.
Market- und FX-Lücken werden unabhängig für die explizite Zielwährung geplant.

UI und Service zeigen persistierten Teilfortschritt und die exakt bestätigten
Review-Zeilen. Ein erfolgreicher Batch ist kein Claim für gesamte Coverage, bereits
erfolgte FX-Umrechnung oder fertigen Snapshot. FIFO-/Snapshot-Abschluss bleibt separat.
Reale Providerzugriffe, Publication und produktiver Runtime-Upgrade benötigen weiterhin
eine ausdrückliche operative Bestätigung.

## Reviewgeneration und Bedienbereiche (ADR-207)

Der Abruf-Checkboxwiderruf benutzt ausschließlich `invalidate_fetch()`; Auswahl-,
Kontext- und Einstellungswechsel invalidieren weiterhin beide Autoritäten. Sichtbarer
Review und privater Service-Slot werden gemeinsam verworfen. Die Publication-Checkbox
sendet einen strikten Boolean für ihre aktuelle sitzungslokale Reviewgeneration;
verzögerte Events alter Generationen können keine neue Veröffentlichung autorisieren.
Die native bindungs-/quellen-/fristgebundene Publication bleibt unverändert.

Die Review-/Publication-Controls stehen zusammen und vor den separat beschrifteten
Abruf-Controls. Ein unbekannter Service-Schreibausgang blockiert weitere Aktionen bis
zum expliziten Lesen; bekannte unbekannte Ausgänge benötigen danach bestätigtes Recovery.
Kompakte Prüffälle ändern keine Daten und ersetzen nicht die vollständige Tagesansicht.
Siehe [ADR-207](../../../docs/decisions/ADR-207-review-bound-batch-confirmations-and-guided-workflow.md).

## Kalendergebundene Vorbereitung (ADR-200)

`prepare-calendar` liest ausschließlich eine versiegelte Bewertungsreferenz mit
`use_saved_calendars=true`. Kein Providerzugriff und kein Write. Die daraus
abgeleiteten inkrementellen Bereiche werden nativ neu gebunden. Kalender- und
Tagesdispositionen bleiben öffentlich sichtbar; private Handoffbindung nicht.
Quelllücken bleiben Blocker, FX wird dedupliziert. Ein leerer Schließtagsbedarf
liefert `trusted_batch=null` und keine Abrufbestätigung, nicht fertige Coverage.

Vor Bestätigung/erstem Claim werden alle Bewertungsquellen erneut gebunden;
vor weiteren Claims und vor Transport werden Kalender-/Codequellen erneut geprüft.
Ein serverseitiger optionaler `preflight` prüft unter der Koordinatorsperre noch vor
dem ersten Execution-State-Write; Erfolg ist ausschließlich ein Rückgabewert `None`.
Vorhandene exakte Replays überspringen diesen Preflight und erzeugen keinen Provideraufruf.
Ursprüngliche Auswahlbereiche einschließlich ausgesparter Schließtage bleiben
gegen alle unveröffentlichten Altclaims geschützt. Eigene Publication erlaubt
normales bestätigtes Resume; Kalenderdrift erlaubt keinen automatischen Rebase.
Siehe [ADR-200](../../../docs/decisions/ADR-200-calendar-bound-native-batch-preparation.md).

## Synthetische Evidenz

`test_desktop_market_calendar_batch_v1.py`: native Handoff-/Frische-/Reservierungs-
Tests, leerer Bedarf, FX-Deduplizierung, sequenziertes Resume, spätes Transportgate,
getrennter Publication-/EUR-Abschluss und echter R/CLI-Roundtrip.

`test_desktop_market_fx_batch_execution_v1.py`: Payload-/Kontextbindung, sichere
Dateien, Replay, Teilfortschritt, Sperre zwischen Prozessen, Fehlerredaktion, fsync-
Fehler und private Ergebniswiederherstellung.

`test_desktop_market_fx_batch_binding_v1.py`: native FX-only- und Mixed-Market/FX-
Stagingpfade mit injizierten JSON-Antworten, unveränderte kanonische Historien,
Stale-Mapping-/Paarbindung, exakte Dezimalwerte und echter `os._exit`-Prozessabbruch
nach nativem Staging mit anschließendem Recovery ohne Refetch.

`test_desktop_market_fx_batch_publication_v1.py`: native Mehrbereichssequenz,
getrennte Bestätigungen, FX-Prozessabbruch nach Commit, Market-Abbruch vor nativem
Publication-Record, exakte Receipt-Recovery, kein Writer-Replay, strikt lesende
Neustart-CLI sowie Sprachgrenzenbindung ohne Neuberechnung eines R-JSON-Hashes.
`test_data_market_fx_batch_service_v1.R`: lazy Startup, private Payloadgrenze,
Einmalbestätigung, veränderte Review-Projektionen und explizite Session-Recovery.

`test_data_market_fx_batch_ui_service_v1.R`: produktionsgleicher R-Service und
Controller mit ausschließlich erfundener CLI; verspätete Checkboxrückmeldung,
Reviewgenerationen, Auswahl-/Einstellungswiderruf, verlorene Write-Antworten,
Read/Recovery und gekoppelte Bewertungsinvalidierung ohne implizite Runs.
`test_desktop_market_fx_batch_browser_v1.py`: echte Browserereignisse mit diesem
R-Service, neuer Batch sowie erfundener Neun-Bereiche-Mischzustand, getrennte
Controls und session-lokale Autorität nach Neuladen.
