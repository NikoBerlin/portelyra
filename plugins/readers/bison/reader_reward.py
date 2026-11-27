"""Reward-Leser des Plugins bison (statement_reader_v1, Bereich reward, rc.377).

Bison: Export je Kalenderjahr; Bewertung ueber den Marktpreis des Coins.
Das Profil stammt unveraendert aus dem bisherigen Reward-Import; gelesen wird mit reward_export aus dem SDK. Schluessel, doppelte
Zeilen ueber Dateien, Zeitraum und Kandidaten bildet der Kern."""
from __future__ import annotations

from typing import Any

from portelyra_reader_sdk_v1 import reward_export

PROFILE: dict[str, Any] = {
    "delimiter": ";", "locale": "en_US", "header_search": 1, "account": "Bison", "time_zone": "UTC",
    "roles": {
        "row_id": ("transaction id", "transactionid", "id"), "time": ("date (utc - coordinated universal time)", "date", "timestamp"),
        "event": ("transaction type", "type"), "asset": ("asset",), "quantity": ("asset (amount)", "asset amount", "quantity"),
        "price_currency": ("currency",), "unit_price": ("asset (market price)", "asset market price", "market price", "price"),
        "fiat_total": ("eur (amount)", "eur amount", "euro amount"), "fee": ("fee", "gebühr"),
    },
    "required": ("time", "event", "asset", "quantity", "unit_price"),
    "reward_events": frozenset(("staking reward", "staking income", "reward", "rewards")),
    "valuation": "unit_price", "fee_role": "monetary", "default_currency": "EUR",
}


def _read(source: bytes, file_name: str) -> dict[str, Any]:
    return reward_export(source, PROFILE)


READERS = {"bison_transactions_csv_v1": _read}
