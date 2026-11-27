# Provider Mapping Data Command v1

Owner-confirmed, provider-free commands maintain capability-specific Provider mappings for existing Assets.

- Create always writes an `unverified`, disabled mapping.
- Revise changes only Provider-owned listing fields and returns the mapping to `unverified`/disabled.
- Verify requires a 64-hex bounded probe-evidence fingerprint. The evidence prefix is retained in the immutable command type; verification enables ordinary Providers but never enables Twelve Data.
- Disable preserves history and never deletes a mapping.
- FMP aliases are rejected permanently.

Every mutation uses the canonical writer lock, optimistic revision, one SQLite transaction and one append-only `data_command_audit` row in the `provider_mapping` ownership area. Exact replay is read-only; token reuse with different evidence or payload fails closed.

This contract performs no Provider request, DNS, network, FX, Tax, Activity or Market-History write. A separately authorized Provider-probe capability must produce the evidence consumed by verification.
