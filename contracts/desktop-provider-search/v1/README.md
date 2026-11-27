# Desktop Provider Search v1

Owner-confirmed, one-attempt Yahoo search for the guided Asset Center.

Seit rc.392 (#495): jeder geladene Kursanbieter mit der Operation `search` (z. B. das Plugin EODHD mit ISIN in den Treffern), nicht
mehr nur Yahoo. Ohne eingefügten Transport ruft der Kern über `plugin_credentials_v1.provider_get_v1` ab (Zugang, bestätigte Hosts,
Kostenzählung, Herkunft `interactive`). Neue Codes: `desktop_provider_search_credential_unavailable`, `desktop_provider_search_cost_limit`.

Preview is provider-free. Apply persists a hash-only owner-local attempt before one strict HTTPS request. It sends only the owner-entered query and fixed search controls; no Context, Portfolio, holding or Activity value leaves the machine. Result candidates are suggestions and cannot establish Asset, Listing, Tax or FX identity. An optional `isin` is returned only when explicitly provided with a valid format/check digit; missing and malformed values become null. Previously stored results without that optional field remain readable. Quote subunits such as GBp/ZAc are not coerced to uppercase major currencies. The UI allows explicit search before Asset creation and uses search-specific candidate handles; it never searches on typing or silently saves a mapping.

An exact completed replay reads the owner-local result without a second request. A consumed incomplete attempt cannot retry automatically. FMP and multi-provider fallback are absent. Raw query text and raw responses are not persisted.
