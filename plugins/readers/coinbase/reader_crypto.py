"""Portelyra-Leser coinbase: Krypto-Export (statement_reader_v1, Aufruf read_text/detect).

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


SOURCES = {"coinbase": {"zone": "UTC"}}


def _Sheet(source: str, file_name: str) -> CryptoSheet:
    return CryptoSheet(source, file_name, SOURCES[source]["zone"])


_SIGNATURE = frozenset({"ID", "Timestamp", "Transaction Type", "Asset", "Quantity Transacted"})


def _detect_format(text: str) -> bool:
    """Wie die bisherige Formaterkennung: eine Kopfzeile unter den ersten 30, die alle Spalten des Formats nennt."""
    for line in text.lstrip("\ufeff").splitlines()[:30]:
        delimiter = max(",;\t", key=line.count)
        if _SIGNATURE <= {cell.strip().strip('"') for cell in line.split(delimiter)}:
            return True
    return False


def _coinbase(text: str, file_name: str) -> dict[str, Any]:
    sheet = _Sheet("coinbase", file_name)
    for number, row in sheet.numbered(_rows(text, "ID,")):
        try:
            at = _parse_time(row.get("Timestamp", ""), "%Y-%m-%d %H:%M:%S UTC")
            ticker, quantity, kind = _ticker(row.get("Asset", "")), _number(row.get("Quantity Transacted")), row.get("Transaction Type", "")
            common = {"transaction_id": row.get("ID")}
            if kind in ("Staking Income", "Incentives Rewards Payout", "Retail Simple Price Improvement", "Inflation Reward", "Learning Reward", "Reward Income"):
                sheet.skip("crypto_reward"); continue
            if kind in ("Buy", "Sell", "Advanced Trade Buy", "Advanced Trade Sell"):
                if (row.get("Price Currency") or "EUR").upper() != "EUR":
                    sheet.add(number, "main", at, ticker, "swap", quantity, quote=row.get("Price Currency"), **common); continue
                # Kurswert = Subtotal; Gebuehr = Abstand zu "Total (inclusive of fees and/or spread)" - Total ist, was bezahlt bzw.
                # gutgeschrieben wurde (Kaeufe = Abbuchung, Verkauf = Eingang auf dem Verrechnungskonto;
                # beim Verkauf steckt der Spread nicht in "Fees and/or Spread"). Ohne Total gilt die Gebuehrenspalte.
                subtotal, fee = _number(row.get("Subtotal")), _number(row.get("Fees and/or Spread"))
                total = _number(row.get("Total (inclusive of fees and/or spread)"))
                if subtotal is not None and total is not None:
                    fee = abs(abs(total) - abs(subtotal))
                signed = abs(quantity) if quantity is not None and "Buy" in kind else (-abs(quantity) if quantity is not None else None)
                sheet.add(number, "main", at, ticker, "trade", signed, eur=None if subtotal is None else abs(subtotal), eur_fee=Decimal(0) if fee is None else abs(fee), **common)
            elif kind in ("Convert",):
                sheet.add(number, "main", at, ticker, "swap", quantity, **common)
            elif kind == "Retail Staking Transfer" or kind == "Retail Unstaking Transfer":
                sheet.add(number, "main", at, ticker, "internal", quantity, **common)
            elif kind in ("Receive", "Deposit", "Send", "Withdrawal"):
                incoming = kind in ("Receive", "Deposit")
                signed = None if quantity is None else (abs(quantity) if incoming else -abs(quantity))
                if ticker == "EUR":
                    sheet.skip("crypto_fiat"); continue
                address = row.get("Sender Address") if incoming else row.get("Recipient Address")
                sheet.add(number, "main", at, ticker, "move", signed, address=address if address and " " not in address else "", **common)
            else:
                sheet.skip("crypto_unsupported")
        except ArithmeticError:   # Zahl ausserhalb jedes Rahmens ("1e9999999" in einem beschaedigten Beleg): nicht lesbar statt Absturz
            sheet.skip("crypto_unreadable_row", number, "number", "unreadable")
    return sheet.result()


READERS = {"coinbase_crypto_v1": _coinbase}
DETECTORS = {"coinbase_crypto_v1": _detect_format}
COMBINERS: dict = {}
