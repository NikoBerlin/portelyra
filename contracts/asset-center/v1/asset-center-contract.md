# Guided Asset Center Contract v1

## User process

0. Read a portfolio-wide Market History Coverage inventory for every active `external_market` Asset. The inventory classifies Daily History readiness as `mapping_missing`, `mapping_test_required`, `mapping_disabled`, `fx_confirmation_required`, or `history_ready_to_plan` and opens the existing bounded next step for one selected Asset. Inventory refresh is read-only and has no Provider, network, Mapping, FX or Market-History authority.
1. Select an existing Asset, preview/confirm one Asset create command, or separately preview/confirm an explicit business price-currency revision.
2. Optionally search a reviewed Provider, copy one visible proposal into an unverified mapping draft, preview and confirm the mapping.
3. Separately authorize one bounded Provider probe; only verified evidence may activate an ordinary mapping.
4. Optionally initialize/read the Tax Policy store and preview/confirm an Asset classification.
5. Plan Daily History read-only, select exactly one contiguous range, separately confirm one external fetch into owner-local staging, review current/Candidate/effective Close in an exact table and deterministic plot, then separately confirm exact publication or rejection. Fetch never publishes; publish never refetches. Explicit recovery reads a sealed stage or receipt before any further action.
6. Hand off visibly to the opened/focused Asset Activity command form without deriving Cash. The handoff resolves the selected Asset and optional Account through server-owned identity maps, then initializes a separate browser-local one-Asset presentation scope. FIFO-world, custody and Activity-history tables are focused by ephemeral ref while the write target remains independently singular; display names are never identity.
7. Review a dimensioned completion summary.

## Boundary

A single UI process does not imply one atomic write. Catalog, Provider Mapping, Tax Policy, Daily Market History and Asset Activity keep separate storage, writers, confirmations and receipts. A business price-currency revision changes only the revision-bound Catalog Asset and never creates Provider Mapping, FX, Activity, Cash or Tax facts. Market fetch confirmation authorizes one bounded network attempt and private stage only; publication confirmation is bound to the exact public Review and sealed Candidate and grants schema-2300 authority only to `market_worker`. Browser-local multi-selection filters only completed read tables and grants no batch-command capability. The Market History Coverage inventory is likewise an orchestration read model: it may navigate to one Asset's Provider or History step but cannot silently create mappings, perform bulk fetches, infer FX authority or publish history. A later-step failure preserves prior successful facts and the process remains resumable.

## Optionality and readiness

Core Asset identity is sufficient for transaction-based realized calculations. Provider, Tax and Market History may be optional, unavailable, partial, stale or blocked. Missing facts are never projected as zero or complete.

## Provider policy

Search, probe and Market History fetch are explicit actions. No automatic multi-provider fallback exists. FMP is absent. Twelve Data may only be represented as expert-only and disabled. Search proposals cannot establish Asset identity or Tax classification. Provider currency has no Transaction- or FX-authority. Market History Review v1 supports only explicit `weekday_exchange` and `continuous_24_7` calendar mappings; unsupported Calendar or public Market-code shapes block before fetch rather than being guessed.

## Legacy provenance

The UX pattern is derived narrowly from the superseded Legacy reference `server_functions/asset_onboarding.R`, function `asset_onboarding_prefill_from_symbol_hit`: search, select, probe, visibly prefill, then preview. Direct CSV writes, generated paths, automatic Provider chains, Legacy Tax defaults, FMP use and the large all-fields modal are not adopted.
