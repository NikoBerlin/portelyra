# Market History Review v1 Contract

## Separate authority cuts

The accepted Desktop Market History Fetch v1 remains unchanged as a compatibility implementation. ADR-157 makes it unreachable from the Asset Center and supplies an additive Product orchestration that separates its external and persistent effects:

1. range planning without external data retrieval;
2. durable one-use confirmation before one Provider fetch;
3. owner-only staging of exactly one validated Candidate;
4. browser-safe visual and exact-table Review;
5. a second durable one-use confirmation bound to the staged Candidate and Review;
6. publication by the sole schema-2300 `market_worker` without refetch.

A consumed or uncertain fetch is never repeated automatically. A terminal fetch failure remains visible as sealed failure evidence and the normal Product service requires explicit recovery before a new preview. That action first consumes a create-only owner-local recovery Attempt and then seals recovery evidence against the exact Fetch Attempt and Failure, so an App restart cannot silently skip recovery. An attempt without either exact Stage or terminal failure evidence remains `recovery_required` and blocks every new Review for that Listing. Fetch-Attempt reservation is serialized by an owner-only Listing lock and repeats the unresolved-state check while holding that lock, so concurrent processes can consume at most one competing Preview before any Provider call. Publish-Attempt reservation and rejection use the same Listing lock, so they cannot both become terminal. A publication attempt uses the already staged Candidate bytes; while its effect is unresolved, both retry and rejection are blocked. A repeated publish invocation never acts as recovery. Only explicit recovery may seal a missing publication result after matching the exact Attempt, Candidate and schema-2300 Receipt; existing publication evidence is accepted only with the same three-way match. Rejection and stale browser state cause zero schema-2300 writes. The owner selects exactly one contiguous Plan range per fetch confirmation.

The Product boundary persists sealed private attempts, stages, failures, rejections and publication evidence create-only beneath the owner data space (`0700` directories and `0600` files). It binds the Listing to the Promotion Mapping and its verified successor revision, then seals the exact current-history row-set fingerprint used by the Review. Preview and confirmed Fetch re-read the isolated canonical Mapping row and latest native audit fingerprint through an immutable query-only SQLite handle. A one-revision verified successor additionally requires the immediately preceding native verification audit to match the promoted Mapping fingerprint; stale, disabled, unverified or skipped-revision state blocks before transport. Neither private storage locations nor internal fingerprints enter the browser model.

## Review model

One Review covers one Listing, quote currency and contiguous date range. Internal Listing identity, Context, paths, Secrets and Candidate fingerprints remain server-side behind an ephemeral Review ref. The public model provides:

- current, Candidate and projected effective Close values as exact Decimal text;
- deterministic worker-produced integer plot coordinates on one shared scale;
- new/unchanged/correction/gap classifications;
- calendar state, original observation date and effective-value age;
- visible warnings plus exact row counts;
- solid observed, dashed imputed and explicit gap presentation.

The chart is a plausibility aid. Exact staged bytes and Decimal values remain publication authority. Real observed jumps are never smoothed or replaced.

## Calendar and imputation

The explicit Listing calendar decides whether a date is an expected session. Asset class alone never does. Product v1 supports only the explicit Daily mapping `weekday_exchange → exchange_calendar` and `continuous_24_7 → continuous_24_7`. `bank_business_day` and `custom_reviewed` fail before fetch until reviewed day-level Calendar evidence exists. Provider-specific omitted/null dropout markers are normalized before the staged Review. A literal zero is never an observed price; only a Provider-manifest-declared zero-as-absence encoding on a calendar-confirmed closed date may normalize to absence with a warning.

- Missing exchange session: persist/review as `source_gap`; no automatic imputation.
- Missing continuous-24/7 date: persist/review as `source_gap`; no weekend exception.
- Missing calendar-confirmed exchange weekend/holiday: source day is `non_trading_day`, not an error.
- A preceding eligible observed unadjusted Close may be carried into the derived valuation/plot view as `imputed_non_trading_day`.
- No eligible predecessor leaves the effective Close unavailable with a warning.
- An unresolved expected-session gap or pending Corporate Action breaks the carry-forward chain rather than permitting imputation through unsafe evidence.

Carried values retain the original observation date and increasing age. Carry-forward stops once that age would exceed 3,650 calendar days; the effective Close then becomes `unavailable_no_predecessor`, so every public age remains inside the bounded Review schema. The source-history day keeps null Open, High, Low, Close, Adjusted Close and Volume. Only the derived effective Close is populated.

Imputation is allowed only for Market valuation and Market plots. It is forbidden as executed Trade price, Reward valuation, FIFO basis, Tax fact, Provider correction or FX evidence.

## Compatibility gates

The public Review contract accepts `market_code` only as `^[A-Z0-9]{2,12}$`. Daily History and Promotion may contain a wider legacy-valid code. Product v1 rejects that Listing before external access; it never truncates, aliases or silently rewrites the code.

## Non-authority

The pure reference creates no file, network request, Provider execution, Market append, canonical write, Tax write, Reward update or worker start. ADR-157 adds the explicit owner-local staging and Product publication boundaries plus synthetic execution with an invented transport. Repository tests perform no real Provider request or productive write. Real external access and productive publication still require separate explicit authorization.
