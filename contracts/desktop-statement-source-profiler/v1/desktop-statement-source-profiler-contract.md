# Desktop Statement Source Profiler Contract v1

## Scope

The profiler deterministically identifies technical CSV structure and proposes only explicit alias-bound column roles. It MUST NOT open a path, persist input or output, infer business routes or time zones, activate an adapter, produce a Candidate, access a provider/network, or write Catalog, ActivityDraft, Cash, Tax, SQL or Canonical state.

## Detection

Accepted encodings are UTF-8 and UTF-8-BOM. Candidate delimiters are comma, semicolon and tab. Selection requires a unique consistent winner. Header order is irrelevant. Malformed input and ambiguous detection fail closed.

## Roles and completeness

Aliases are immutable rows in `header-role-aliases.csv`; fuzzy matching is forbidden. Each required role must have exactly one source column. Unknown columns remain visible for owner review. Duplicate role mappings, missing roles, blank rows, missing/duplicate source-row identities, mixed time lexemes and invalid decimal lexemes block readiness.

## Semantic boundary

Distinct source type, subtype and asset-class tokens and their exact row-wise tuples may be shown only in the private in-memory review. Every parsed row contributes to exactly one tuple when all three roles are unique; the public balance reports `silent_drop_count=0`. No route is created. Decimal detection is lexical and exact; integer-only evidence cannot establish a separator. Time format detection never establishes a time zone.

## Public boundary

The public projection contains counts, technical format codes, readiness and negative capability flags. Header labels, semantic tokens, source paths, source hashes and row values are absent.

## Profile revision

Profiler output cannot mutate `kraken_ledger_csv_source_v1:r1`. Owner-reviewed structural and semantic decisions may later propose a new immutable revision through a separate confirmation boundary.
