"""Reward-Leser des Plugins bsdex (statement_reader_v1, Bereich reward, rc.377).

BSDEX: Export „Transaktionen“ ohne eigene Kennung je Zeile und ohne Bewertung (Marktdaten bewerten).
Das Profil stammt unveraendert aus dem bisherigen Reward-Import; gelesen wird mit reward_export aus dem SDK. Schluessel, doppelte
Zeilen ueber Dateien, Zeitraum und Kandidaten bildet der Kern."""
from __future__ import annotations

from typing import Any

from portelyra_reader_sdk_v1 import reward_export

PROFILE: dict[str, Any] = {
    "delimiter": ",", "locale": "de_DE", "header_search": 1, "account": "BSDEX", "time_zone": "Europe/Berlin",
    "roles": {
        "time": ("erstellt",), "event": ("transaktionstyp",),
        "asset": ("kryptowährung", "kryptowaehrung"), "quantity": ("betrag",),
        "fee": ("transaktionsentgelt",),
    },
    "required": ("time", "event", "asset", "quantity", "fee"),
    "reward_events": frozenset(("staking reward",)),
    "valuation": "missing", "fee_role": "none", "default_currency": "EUR",
}


def _read(source: bytes, file_name: str) -> dict[str, Any]:
    return reward_export(source, PROFILE)


READERS = {"bsdex_transactions_csv_v1": _read}
