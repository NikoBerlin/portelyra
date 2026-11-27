# Desktop Provider Probe Contract v1

## Input

One current unverified `daily_history` mapping of a loaded price-provider plugin with `daily_history` (Yahoo until rc.393; any such plugin since rc.394), exact mapping revision/fingerprint, and an explicit inclusive date range of at most 32 calendar days.

## Execution

Preview has no side effect. Confirmation persists create-only attempt evidence and permits exactly one TLS-validated request to a host from the plugin's manifest (for Yahoo the fixed chart host/path). Since rc.394 the request goes through the shared core path: a plugin credential is inserted by the core only for confirmed hosts, and costs are counted. Redirects, cookies, compression, fallback and retry are unavailable.

The parser validates symbol, ISO currency, exchange timezone, representable bounded integer timestamps and exact bounded Decimal JSON tokens. Duplicate object keys, non-finite JSON constants and boolean timestamps fail closed. It stores normalized bars and split-review evidence without raw response bytes. Currency mismatch remains visible and blocks later verification rather than being converted.

## Boundary

Probe evidence is staging evidence, not valuation authority. It performs no Canonical, Provider Mapping, Daily Market History, FX, Tax or Activity write. Completed exact replay reads persisted evidence; a consumed incomplete attempt requires a new preview and confirmation.
