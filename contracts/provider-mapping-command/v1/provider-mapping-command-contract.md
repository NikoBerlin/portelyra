# Provider Mapping Data Command Contract v1

## Ownership

`data_app` is the sole writer of canonical `provider_mapping`. Asset identity remains owned by the Asset Catalog. Provider probes and Daily Market History remain separate domains.

## Commands

| Action | Required current state | Result |
|---|---|---|
| `create` | active Asset; tuple Asset/capability/Provider absent | revision 1, `unverified`, disabled |
| `revise` | exact mapping revision | next revision, changed listing fields, `unverified`, disabled |
| `verify` | exact revision; state `unverified` or `verified`; probe fingerprint supplied | next revision, `verified`; enabled except Twelve Data |
| `disable` | exact revision | next revision, `disabled`, disabled |

Immutable identity fields are Asset, capability and Provider. A correction of one of these creates a separate mapping and disables the predecessor.

## Provider fields

A mapping records Provider symbol, optional exchange label, optional MIC, Provider currency and expert-only state. These fields have no Transaction-, FX-, Tax- or Asset-price-currency authority.

## Verification

A browser cannot assert `verified` directly. The server command requires a bounded probe-evidence fingerprint. Its first 192 bits are retained in the immutable audit command type, while the canonical row remains free of raw Provider output. The future probe store retains full evidence and is validated before this command is built.

## Safety

Commands require the owner Desktop Runtime Context, canonical writer lock, exact revision and a strictly later UTC timestamp. They are transactional, tamper-evident and one-token idempotent. No delete, automatic retry, fallback Provider, Provider access, network, Secret, Tax, Activity or Market-History capability exists here.
