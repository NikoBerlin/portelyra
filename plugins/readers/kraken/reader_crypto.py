"""Portelyra-Leser kraken: Krypto-Export (statement_reader_v1, Aufruf read_text/detect).

Erzeugt aus dem bisherigen Kernmodul (rc.375) ohne Aenderung der Leselogik. Liefert die Zeilen einer Datei; Paarung von
Transfers ueber Boersen hinweg und Buchung bleiben im Kern.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from portelyra_reader_sdk_v1 import (
    CryptoSheet,
    crypto_number as _number,
    parse_time as _parse_time,
    csv_dict_rows as _rows,
    crypto_ticker as _ticker,
)


SOURCES = {"kraken": {"zone": "UTC"}}


def _Sheet(source: str, file_name: str) -> CryptoSheet:
    return CryptoSheet(source, file_name, SOURCES[source]["zone"])


_SIGNATURE = frozenset({"txid", "refid", "time", "type", "asset", "amount", "fee"})


def _detect_format(text: str) -> bool:
    """Wie die bisherige Formaterkennung: eine Kopfzeile unter den ersten 30, die alle Spalten des Formats nennt."""
    for line in text.lstrip("\ufeff").splitlines()[:30]:
        delimiter = max(",;\t", key=line.count)
        if _SIGNATURE <= {cell.strip().strip('"') for cell in line.split(delimiter)}:
            return True
    return False


def _kraken(text: str, file_name: str) -> dict[str, Any]:
    sheet = _Sheet("kraken", file_name)
    for number, row in sheet.numbered(_rows(text)):
        at = _parse_time(row.get("time", ""), "%Y-%m-%d %H:%M:%S")
        ticker, amount, fee = _ticker(row.get("asset", "")), _number(row.get("amount")), _number(row.get("fee")) or Decimal(0)
        kind, wallet = row.get("type", ""), row.get("wallet") or "spot / main"
        common = {"transaction_id": row.get("txid"), "group": row.get("refid")}
        if kind == "earn" and row.get("subtype") == "reward":
            sheet.skip("crypto_reward"); continue
        if ticker == "EUR":
            if kind in ("spend", "receive", "trade"):
                sheet.add(number, wallet, at, "EUR", "trade_eur", amount, eur_fee=fee, **common)
            else:
                sheet.skip("crypto_fiat")
            continue
        if kind in ("spend", "receive", "trade"):
            sheet.add(number, wallet, at, ticker, "trade_coin", amount, fee_quantity=fee or None, **common)
        elif kind == "earn" and row.get("subtype") in ("allocation", "autoallocation", "deallocation", "autodeallocation", "transfer", ""):
            sheet.add(number, wallet, at, ticker, "internal", amount, fee_quantity=fee or None, **common)
        elif kind in ("deposit", "withdrawal"):
            # Kraken bucht die Gebuehr zusaetzlich zum Betrag: eine Auszahlung von 1,0 mit 0,1 Gebuehr verlaesst das Konto mit 1,1
            sheet.add(number, wallet, at, ticker, "move", amount, fee_quantity=fee or None, **common)
        else:
            sheet.skip("crypto_unsupported")
    return sheet.result()


READERS = {"kraken_crypto_v1": _kraken}
DETECTORS = {"kraken_crypto_v1": _detect_format}
COMBINERS: dict = {}
