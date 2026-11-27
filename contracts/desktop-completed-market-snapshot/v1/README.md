# Completed EUR market snapshot v1

Normativ: `snapshot.schema.json`; fachliche Grenzen: [ADR-201](../../../docs/decisions/ADR-201-completed-eur-valuation-in-desktop-run-snapshots.md).

- Read-only Bridge: `workers/reference/desktop_completed_market_snapshot_v1.py`.
- Privater CLI-Read `scripts/desktop_market_valuation.py portfolio-input`: exakt `{preview_ref,as_of_date}` plus bestehende Runtime-/Datenraumhülle. Antwort nur Bindung und öffentliche Zählübersicht, keine Asset-IDs, Kurse oder Pfade.
- Optionaler privater Workflowinput `market_valuation_binding`: exakt `preview_ref`, `valuation_fingerprint`, `receipt_fingerprint`, `as_of_date`, `bridge_fingerprint` (Strings). EUR, Tagesend-Cutoff, keine manuellen Preis-/FX-Eingaben. Keine alternative Datenquelle. Die versiegelte Bewertungsregel nach ADR-204 bleibt erhalten.
- Fehlende Completion, ungültige Evidenz und Drift verwenden sichere `desktop_market_valuation_*`-Codes; Run-Gates `desktop_run_center_market_valuation_changed` beziehungsweise `desktop_workflow_valuation_blocked`.
- Bestehender Desktop-Workflow-Publisher schreibt den optionalen `browser_model.exact_market_snapshot` und bindet ihn in den Calculationfingerprint. Keine neue Publicationautorität.
- Mengen, Einheitswerte und Summen als `{numerator,denominator,decimal}`; `decimal=null` bei nicht endlicher Darstellung. Nullable Marktwerte sind fehlend, niemals implizit null Euro.
- `complete` betrifft nur gehaltene Non-Cash-FIFO-Positionen. Cash, Tax, Netto-Liquidation und Gesamtabschluss bleiben ausgeschlossen. Bekannte Teilsumme separat vom vollständigen Non-Cash-Wert.
- `valuation_policy` und `valuation_status=complete|substituted|incomplete` unterscheiden vollständige, ersatzwertgestützte und unvollständige Bewertungen. Kurs-/FX-Herkunft, Datum und Alter bleiben pro Position sichtbar; `substituted_position_count` zählt ersatzwertgestützte gehaltene Positionen. Eine fehlende gehaltene Position erzwingt weiterhin einen null-Gesamtwert. Ältere Snapshots ohne diese optionalen Metadaten bleiben unverändert lesbar.
- Displayreader prüft beide bytegebundenen Schemata. Anzeige nur aus completed Publication; keine Live-Frischeprüfung oder Rechnung durch Cockpit/Analyse.

Tests: `tests/contracts/test_desktop_completed_market_snapshot_v1.py`, einschließlich `tests/helpers/read_publish_completed_market_snapshot_v1.R`, sowie Produktbrowser im Market-Workspace-Test.
