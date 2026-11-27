# Native Asset Activity Preview v1.1

The storage command remains Asset Activity v1/schema 401. The current Preview is
additively bound to FIFO v2:

- `fifo_version=2`;
- FIFO world `portfolio_asset`;
- custody `portfolio_account_asset`;
- no coupled Transaction fact in FIFO;
- exact basis and realized values retain Decimal or ratio evidence;
- no rounding, Cash, Provider/network or schema-201 write.

The older v1 Preview schema remains frozen compatibility evidence and is no longer
the M7 Data surface.
