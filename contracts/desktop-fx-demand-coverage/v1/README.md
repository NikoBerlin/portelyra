# Desktop FX Demand Coverage v1

Provider-free read boundary for ADR-177 on-demand currency pairs. For each concrete source-to-target demand it reports whether one explicit direct or inverse schema-2600 pair is bound and counts persisted observed, non-trading, source-gap and not-requested days over an exact range, and names the newest observed rate date so the freshness of the conversion basis is visible.

An absent store or pair is normal `pair_missing` state. The reader performs no pair inference beyond exact direct/inverse matching, no graph search, conversion, Provider/network access, FX History write or canonical write. Internal Pair refs are not exposed.
