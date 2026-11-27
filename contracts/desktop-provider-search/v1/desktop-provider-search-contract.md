# Desktop Provider Search Contract v1

## Flow

1. The server builds a context-bound preview from one Provider, query, mode and random nonce. No filesystem or network operation occurs.
2. The browser sees Provider, exact outgoing query, result limit, one-attempt policy and terms/stability warning.
3. Explicit confirmation consumes the operation by create-only attempt evidence before network access.
4. The isolated Python boundary performs one certificate-validated HTTPS GET to the fixed Yahoo search host/path. Redirect, cookie, credential, compression, fallback and retry behavior is unavailable.
5. Bounded candidates are normalized and persisted without query text or raw response bytes. They remain unselected suggestions.

Completed exact replay is read-only. A failed or interrupted consumed attempt needs a newly previewed and confirmed operation; it cannot be automatically retried.

Search has no Canonical, Provider Mapping, Daily History, FX, Tax or Activity write authority. FMP is excluded and Twelve Data is not a search provider in v1.
