# Desktop Statement Source Profiler v1

This contract implements ADR-164's deterministic, provider-neutral structural CSV profiler. It uses invented fixtures only and has no source-path or private-read entrypoint.

Normative files:

- `desktop-statement-source-profiler-contract.md`
- `header-role-aliases.csv`
- `public-result.schema.json`
- `capability-matrix.csv`
- `failure-codes.csv`
- `state-machine.csv`
- `source-fingerprints.csv`
- `golden-fingerprints.csv`

The public result contains structure and readiness counts only. Raw headers and semantic tokens are private in-memory review values and are never returned by the public projection.
