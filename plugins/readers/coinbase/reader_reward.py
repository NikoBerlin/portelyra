"""Reward-Leser des Plugins coinbase (statement_reader_v1, Bereich reward, rc.377).

Coinbase: Transaktionsbericht; die Kopfzeile steht in den ersten zwoelf Zeilen. Bewertung: Gesamtbetrag, sonst Stueckpreis; Gebuehr in Geld.
Das Profil stammt unveraendert aus dem bisherigen Reward-Import; gelesen wird mit reward_export aus dem SDK. Schluessel, doppelte
Zeilen ueber Dateien, Zeitraum und Kandidaten bildet der Kern."""
from __future__ import annotations

from typing import Any

from portelyra_reader_sdk_v1 import reward_export

PROFILE: dict[str, Any] = {
    "delimiter": ",", "locale": "en_US", "header_search": 12, "account": "Coinbase", "time_zone": "UTC",
    "roles": {
        "row_id": ("id", "transaction id", "transactionid"), "time": ("timestamp", "time", "date", "datetime"),
        "event": ("transaction type", "type"), "asset": ("asset", "currency"),
        "quantity": ("quantity transacted", "quantity", "amount"),
        "price_currency": ("price currency", "spot price currency"),
        "unit_price": ("price at transaction", "spot price at transaction", "unit price", "price"),
        "fiat_total": ("total (inclusive of fees and/or spread)", "subtotal"), "fee": ("fees and/or spread", "fees", "fee"),
    },
    "required": ("time", "event", "asset", "quantity", "unit_price"),
    "reward_events": frozenset(("staking income", "staking reward", "rewards income", "reward", "rewards", "coinbase earn", "learning reward", "learn reward", "incentives rewards payout", "retail simple price improvement")),
    "valuation": "prefer_fiat_total", "fee_role": "monetary", "default_currency": None,
}


def _read(source: bytes, file_name: str) -> dict[str, Any]:
    return reward_export(source, PROFILE)


READERS = {"coinbase_transactions_csv_v1": _read}
