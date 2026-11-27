"""Reward-Leser des Plugins kraken (statement_reader_v1, Bereich reward, rc.377).

Kraken: Ledger-Export; Rewards sind Arten wie staking/reward oder earn mit Unterart reward. Bewertung: amountusd abzueglich feeusd, Gebuehr in Coin.
Das Profil stammt unveraendert aus dem bisherigen Reward-Import; gelesen wird mit reward_export aus dem SDK. Schluessel, doppelte
Zeilen ueber Dateien, Zeitraum und Kandidaten bildet der Kern."""
from __future__ import annotations

from typing import Any

from portelyra_reader_sdk_v1 import reward_export

PROFILE: dict[str, Any] = {
    "delimiter": ",", "locale": "en_US", "header_search": 1, "account": "Kraken", "time_zone": "UTC",
    "roles": {
        "row_id": ("txid", "tx id", "transaction id", "refid", "ref id", "reference id"),
        "time": ("time", "timestamp", "date", "datetime"), "event": ("type", "ledger type"),
        "subtype": ("subtype", "sub type"), "account": ("wallet", "location", "account", "balance type", "balance_type"),
        "asset": ("asset", "currency"), "quantity": ("amount", "quantity", "volume"), "fee": ("fee", "fees"),
        "unit_price": ("asset (market price)", "asset market price"), "fiat_total": ("amountusd",), "fiat_fee": ("feeusd",),
    },
    "required": ("time", "event", "asset", "quantity", "fee", "fiat_total", "fiat_fee"),
    "reward_events": frozenset(("staking", "reward", "rewards", "income", "interest")),
    # Kraken fuehrt Rewards auch als Art "earn" mit einer dieser Unterarten.
    "reward_subtypes": frozenset(("reward", "rewards", "staking", "payout", "income", "interest")),
    "valuation": "net_fiat_total", "fee_role": "asset_quantity", "default_currency": "USD",
}


def _read(source: bytes, file_name: str) -> dict[str, Any]:
    return reward_export(source, PROFILE)


READERS = {"kraken_ledger_csv_v1": _read}
