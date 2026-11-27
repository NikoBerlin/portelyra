# Portfolio CSV Exchange v1 Contract

## Authority

SQLite Product-Catalog, die aktive schema-401-Generation und – falls vorhanden – der validierte Cash-schema-2901-Store bleiben kanonisch. Export ist read-only. Import übernimmt ein validiertes Bundle nur in die separate Exchange-Inbox; vier Product-Handoffs bleiben getrennt und besitzen keine gemeinsame Write-Autorität.

## Layout

```text
portfolio-export-<opaque>/
  manifest.json
  portfolio.csv
  assets/<opaque-asset-ref>.csv
  accounts/<opaque-account-ref>.csv
```

`portfolio.csv` enthält die kanonische aktuelle Zeilenmenge einmal. Jede Scope-Datei ist die deterministische transitive Referenzschließung ihres Assets beziehungsweise Kontos. Ihre Record-Fingerprints müssen exakt der kanonischen Zeilenmenge entstammen.

## CSV

Header:

```text
record_kind,record_ref,scope_role,scope_ref,portfolio_ref,account_ref,asset_ref,event_ref,portfolio_name,account_name,related_account_name,asset_name,source_asset_name,event_type,local_date,effective_at_utc,quantity_decimal,eligible_quantity_decimal,unit_price_decimal,gross_amount_decimal,monetary_fee_decimal,asset_fee_quantity_decimal,provided_basis_decimal,basis_currency,payload_json,record_fingerprint
```

UTF-8, LF, Trennzeichen `,`, Dezimalzeichen `,`, `RFC4180_ALL`. Häufig benötigte Namen, Zeiten, Ereignisarten, Währungen und Decimal-Felder stehen als eigene lesbare Spalten bereit; der vollständige verlustfreie Record bleibt zusätzlich im `payload_json`. Decimal-Felder sind exakte Strings im lokalisierten JSON-Payload und werden beim Import bijektiv auf kanonische Punkt-Decimale zurückgeführt. Eine erneute kanonische Serialisierung muss bytegleich sein.

## Included records

- `portfolio`, `account`, `asset`;
- `provider_mapping`;
- `coupled_transaction`, `coupled_posting`;
- `asset_activity`, `fifo_order_evidence`;
- optional vollständig alle **aktiven aktuellen** `cash_coverage_period`-, `cash_event`-, `cash_interest_income`- und `cash_reconciliation`-Fakten aus schema-2901.

`cash_coverage_schema_version=0` ist ausschließlich mit `dimensions.cash_coverage=absent_explicit` zulässig. `cash_coverage_schema_version=2901` ist ausschließlich mit `complete_current` zulässig. Supersedete Cash-Vorgänger bleiben außerhalb des CSV-Austauschs und in der Backup-Autorität. Interne SQL-IDs und Cash-Command-IDs werden durch opake typed Exchange-Refs ersetzt. Command-Actor und interne Command-IDs werden nicht exportiert. Fachliche Source-/Effect-Fingerprints bleiben erhalten.

## Import boundary

Nur ein regulärer Bundle-Ordner unter der Runtime-konstruierten `import-inbox` ist zulässig. Browserwerte wählen ausschließlich einen serverseitig aufgelösten Bundle-Handle. Bestätigter Import ist create-only, persistiert den Attempt vor dem Write und kopiert alle Bundlebytes owner-only in eine staged Inbox. Er erzeugt keine Catalog-, Transaction-, Activity- oder Cash-Fakten. Jede spätere Prüfung des staged `bundle/` ist an den im Import-Receipt versiegelten `bundle_fingerprint` gebunden.

## Vier getrennte Domain-Handoffs

Es gibt absichtlich keinen Multi-Domain-Apply:

1. **Catalog** plant exakte Portfolio-, Konto-, Asset- und Provider-Mapping-Zuordnungen. Exakt vorhandene Fakten werden wiederverwendet; neue Fakten werden unter dem kanonischen Catalog-Writer-Lock atomar mit Auditzeilen geschrieben.
2. **Coupled Transaction** setzt den abgeschlossenen Catalog-Receipt voraus und schreibt eine Transaction zusammen mit allen Postings, Seal und Audit atomar. Eine neue Catalog-/Transaction-Wirkung ist bei bereits aktiver schema-401-Bindung fail-closed blockiert; bestehende identische Fakten dürfen read-only wiederverwendet werden.
3. **Asset Activity** setzt den Catalog-Receipt voraus und erzeugt ausschließlich persistente `tolerant_csv`-ActivityDrafts mit Quellbindung und FIFO-Evidenz. Es schreibt keine schema-401-Activity. Jeder Draft durchläuft danach die bestehende fachliche Draft-Bestätigung.
4. **Cash Coverage** setzt den Catalog-Receipt voraus und erzeugt ausschließlich versiegelte Reviewed Candidates. Erst `preview_desktop_reviewed_cash_coverage_candidate_v1` übernimmt einen Candidate mit `input_mode=reviewed_import` und gebundenem `source_candidate_fingerprint` in den bestehenden Cash-Preview-/Confirmation-/Apply-Pfad. Der CSV-Handoff schreibt nie Cash-Fakten.

Jeder Domain-Plan besitzt einen eigenen Preview-Fingerprint, eine eigene zeitgebundene One-Use-Confirmation, einen vor der Wirkung create-only persistierten Attempt und einen eigenen Receipt. Eine Confirmation autorisiert keine andere Domain. Staged- und Recovery-Read-Models enthalten nur opake Handles; Pfade, Runtime-Kontext, interne IDs und Fingerprints bleiben serverseitig.

### Cash-Abhängigkeiten

Eine vollständige Coverage-Declaration bindet Opening Event und Reconciliation als einen atomaren Cash-Candidate. Ein Interest-Candidate mit verknüpftem Cash Event bleibt `blocked_dependency`, bis genau der gebundene Event-Candidate über den bestehenden Cash-Writer committed wurde. Erst dann löst die serverseitige Cash-Grenze dessen aktuelle opake `cash_event_####`-Referenz auf. Browserwerte dürfen weder SQL-IDs noch freie Event-IDs liefern.

## One-use recovery

Ein konsumierter Attempt wird niemals blind wiederholt. Recovery liest den versiegelten Originalplan, revalidiert Bundle und Context und klassifiziert die beabsichtigte Wirkung als `absent`, `partial` oder `complete`. Partielle kanonische Catalog-/Transaction-Wirkungen sind Konflikte; partielle ActivityDraft-Wirkungen dürfen exakt fortgesetzt werden. Ein nach dem Recovery-Preview veränderter wirkungsloser Zielstand ist `portfolio_csv_handoff_recovery_stale`. Erst eine getrennte `pchr_…`-Confirmation darf den exakt gleichen Plan fortsetzen oder einen bereits vollständigen Effekt mit Receipt versiegeln.

## Release-Closure

Exchange-CLI, Handoff-CLI und ihre vollständige direkte/transitive lokale Import-Closure gehören zum integrity-gebundenen Product-Release-Snapshot. Der Gate führt Initialisierung, Export, redundante Validierung, Import-Staging und einen frischen List-Read aus einem tatsächlich extrahierten Slot aus. Ein Working-Tree-Fallback ist unzulässig.

## Exact recovery

Der CSV-Austausch bewahrt den aktuellen fachlichen Stand einschließlich einer optional vollständig vorhandenen aktuellen Cash-schema-2901-Dimension. Immutable Vorgängergenerationen, vollständige Audit-Historie sowie ausgeschlossene Tax-/Market-Dimensionsstores bleiben Aufgabe des Desktop-Backups.
