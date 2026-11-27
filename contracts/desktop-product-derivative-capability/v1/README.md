# Desktop Product Generic Derivative Capability v1

This owner-only contract upgrades an intact native schema-201 Product Catalog to the
already accepted schema-202 shape, admits `asset_type=derivative` in normal Catalog
commands and enables generic Derivative Asset Activity in newly materialized
schema-401 generations.

The operation is preview-first and consumes one confirmation before the schema
write. It preserves all existing Catalog and Transaction values exactly. The
release upgrade itself never invokes this command; applying it to a Product data
space remains a separate owner-confirmed operation.

Only the existing generic Buy, Sell, Dividend, Stock Dividend, Deposit, Withdrawal
and Transfer facts are supported. `reward` remains Crypto-only. Derivative subtype,
underlying, multiplier, strike, expiry, exercise, assignment, settlement, Provider,
FX, Tax and automatic Cash postings are neither added nor inferred.
