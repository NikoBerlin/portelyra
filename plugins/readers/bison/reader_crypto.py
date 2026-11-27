"""Portelyra-Leser bison: Krypto-Export (statement_reader_v1, Aufruf read_text/detect).

Erzeugt aus dem bisherigen Kernmodul (rc.375) ohne Aenderung der Leselogik. Liefert die Zeilen einer Datei; Paarung von
Transfers ueber Boersen hinweg und Buchung bleiben im Kern.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from portelyra_reader_sdk_v1 import (
    CryptoSheet,
    UTC,
    crypto_number as _number,
    parse_time as _parse_time,
    csv_dict_rows as _rows,
    crypto_ticker as _ticker,
)


SOURCES = {"bison": {"zone": "UTC"}}


def _Sheet(source: str, file_name: str) -> CryptoSheet:
    return CryptoSheet(source, file_name, SOURCES[source]["zone"])


_SIGNATURE = frozenset({"Transaction ID", "Transaction type", "Asset", "Asset (amount)", "Date (UTC - Coordinated Universal Time)"})


def _detect_format(text: str) -> bool:
    """Wie die bisherige Formaterkennung: eine Kopfzeile unter den ersten 30, die alle Spalten des Formats nennt."""
    for line in text.lstrip("\ufeff").splitlines()[:30]:
        delimiter = max(",;\t", key=line.count)
        if _SIGNATURE <= {cell.strip().strip('"') for cell in line.split(delimiter)}:
            return True
    return False


def _bison(text: str, file_name: str) -> dict[str, Any]:
    sheet = _Sheet("bison", file_name)
    for number, row in sheet.numbered(_rows(text)):
        at = _parse_time(row.get("Date (UTC - Coordinated Universal Time)", ""), "%Y-%m-%d %H:%M:%S")
        kind, ticker, quantity = row.get("Transaction type", ""), _ticker(row.get("Asset", "")), _number(row.get("Asset (amount)"))
        common = {"transaction_id": row.get("Transaction ID")}
        if kind == "Staking Reward":
            sheet.skip("crypto_reward"); continue
        if not row.get("Asset"):
            sheet.skip("crypto_fiat"); continue
        if kind in ("Buy", "Sell"):
            # "Eur (amount)" ist der Kurswert, "Fee" die Gebuehr in EUR
            signed = None if quantity is None else (abs(quantity) if kind == "Buy" else -abs(quantity))
            sheet.add(number, "main", at, ticker, "trade", signed, eur=_number(row.get("Eur (amount)")), eur_fee=_number(row.get("Fee")) or Decimal(0), **common)
        elif kind in ("Deposit", "Withdraw", "Withdrawal"):
            signed = None if quantity is None else (abs(quantity) if kind == "Deposit" else -abs(quantity))
            sheet.add(number, "main", at, ticker, "move", signed, fee_quantity=_number(row.get("Fee")) if kind != "Deposit" else None, **common)
        else:
            sheet.skip("crypto_unsupported")
    return sheet.result()


READERS = {"bison_crypto_v1": _bison}
DETECTORS = {"bison_crypto_v1": _detect_format}
COMBINERS: dict = {}
