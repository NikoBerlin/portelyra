# Portfolio CSV Exchange v1

Owner-lokaler verlustfreier CSV-Austausch des aktuellen Product-Catalogs, der Provider-Mappings, gekoppelter Transaction-Fakten, der aktiven schema-401 Asset Activities und einer optional vollständig vorhandenen aktuellen Cash-schema-2901-Dimension.

- kanonische Gesamtsicht: `portfolio.csv`
- redundante selbstständige Sichten: eine Datei je Asset und je Konto/Wallet
- UTF-8, LF, Komma-Trenner, Komma-Dezimalzeichen, alle Felder RFC-4180-gequotet
- create-only Export und context-gebundene Import-Inbox
- vier getrennte Handoffs: Catalog, gekoppelte Transaction, ActivityDraft und Cash Reviewed Candidate
- je Handoff eigener Plan, One-Use-Confirmation, Attempt, Receipt und effect-reconciled Recovery
- Activity- und Cash-Handoffs bleiben Candidates; kein direkter schema-401- oder Cash-Fact-Write
- kein versteckter Provider-, Tax-, FX- oder Market-Write

Maßgeblich sind [portfolio-csv-exchange-contract.md](portfolio-csv-exchange-contract.md), [ADR-147](../../../docs/decisions/ADR-147-lossless-redundant-portfolio-csv-exchange.md) und [ADR-160](../../../docs/decisions/ADR-160-separate-portfolio-csv-domain-handoffs.md).
