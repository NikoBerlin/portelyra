# Desktop Asset Worklists v1

Private Domain: `provider` (die Stammdaten-Domain `master` ist seit rc.309 entfernt; sie stammte aus dem einmaligen Legacy-Import). Alle Commands bleiben lokal. Ein Writer:
`migrations/reference/desktop_market_worklist_v1.py`, aufgerufen über die strikte
private JSON-stdin-CLI `scripts/desktop_market_worklist.py`.

## State und Operationen

- Version 1, opaque Queue-Ref, Kontext-/Pfad-/Domain-Bindung, komplette Mitgliederliste,
  Cursor und Inhaltsrevision. Pro Mitglied stabile private Asset-ID, Disposition und
  optionaler unbestätigter Entwurf. Keine Browser-Refs oder Commands.
- `read`: keine Writes, auch bei fehlender Liste. Keine automatische Fortsetzung.
- `start`: neue Liste bzw. explizite Ergänzung der geladenen Liste; keine stillen Drops.
- `select`: explizite Position; keine Provideraktion.
- `update`: erwartete Revision und exakte aktuelle Asset-Identität erforderlich;
  speichern/pausieren oder zum nächsten `pending`-Mitglied wechseln.
- Dispositionen: `pending`, `deferred`, `skipped`, `mapping_saved`, `reviewed`.
  `mapping_saved` behauptet weder Verifizierung noch fertige Historie.
- Providerentwurf: Provider, Symbol, Providerwährung, Börse, MIC; keine Aktivierungs-
  oder Abrufbestätigung. Masterentwurf: Bezeichnung, ISIN und fachliche Preiswährung.
- Korrekturen schreiben ausschließlich über vorhandene separate native Catalog-/Mapping-
  Commands. Der Controller prüft zum Abschluss den aktuellen kanonischen Zustand.
- Nach einem unterbrochenen Mapping-Commit bleibt die Zuordnung beim nächsten Lesen
  sichtbar und kann ohne Writer-Replay ausdrücklich in der Liste disponiert werden.

## Sicherheit

Owner-Verzeichnisse 0700, Dateien 0600; nichtblockierendes flock, atomarer Ersatz,
fsync, erwartete Revision. Fremde Kontexte, kopierte Datenräume, Symlinks, Hardlinks,
fehlende Bindung und stale Sitzungen blockieren. Kein Provider-, Activity-, Cash-,
FIFO-, Tax-, Snapshot- oder Deployment-Write. Keine Initialisierung beim App-Start.
Der private R-Service veröffentlicht niemals persistierte IDs oder Dateipfade an den Browser.
Hashes schützen Bindung/Integrität, nicht gegen einen Angreifer mit denselben OS-Rechten.

Die Default-, UI- und Fehler-Recovery-Regeln stehen in
[ADR-197](../../../docs/decisions/ADR-197-market-data-workspace-and-identity-bound-review-worklists.md).
