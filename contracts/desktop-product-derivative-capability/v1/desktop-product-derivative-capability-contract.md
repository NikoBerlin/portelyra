# Contract

## Authority and state transition

The only accepted source state is an owner-bound, integrity-valid, native
schema-201 Product Catalog. Preview is read-only and binds the complete canonical
file fingerprint, a value-preserving Domain-row fingerprint, exact source schema
and protected schema-202 migration bytes. An already valid native schema-202 store
returns `already_enabled` without confirmation or write.

Apply requires the exact unexpired one-use confirmation. Consumption evidence is
published owner-only before acquiring the canonical writer lock. The command then
revalidates every bound fingerprint, executes the accepted schema-201 to
schema-202 migration transaction and proves that Portfolio, Account, Asset,
Transaction, Posting and Audit values are unchanged. A completed owner-only receipt
binds the resulting canonical fingerprint. Failed consumed attempts are not
retried automatically.

## Generic Derivative boundary

Schema 202 permits the immutable Product classification `derivative`. Coupled
schema-202 Transaction postings to a Derivative remain blocked. Derivative events
are written only through Asset Activity v1. A new additive schema-401 patch replaces
only the Asset Activity validation trigger so active non-Cash Derivatives are
admitted while `reward` stays Crypto-only. The patch records an immutable capability
marker and creates no Event.

Generic quantity and FIFO semantics are exactly those of ADR-109. No lifecycle,
Provider, Market, FX, Tax or Cash semantics are inferred. Existing schema-201,
schema-401 and non-Derivative source facts are not rewritten.

## Operational boundary

Repository implementation and synthetic tests grant no Primary migration, Catalog
write, Activity apply, release installation, runtime restart, Provider access or
network access. Backup, release upgrade, Product capability apply, Derivative
Catalog creation and real Activity apply remain separately confirmed operations.
