"""Portelyra-Leser bitbox: Krypto-Export (statement_reader_v1, Aufruf read_text/detect).

Erzeugt aus dem bisherigen Kernmodul (rc.375) ohne Aenderung der Leselogik. Liefert die Zeilen einer Datei; Paarung von
Transfers ueber Boersen hinweg und Buchung bleiben im Kern.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import re
from typing import Any

from portelyra_reader_sdk_v1 import (
    CryptoSheet,
    COIN_UNITS as _UNITS,
    iso_time as _iso_time,
    crypto_number as _number,
    csv_dict_rows as _rows,
    crypto_ticker as _ticker,
)


SOURCES = {"bitbox": {"zone": "UTC"}}


def _Sheet(source: str, file_name: str) -> CryptoSheet:
    return CryptoSheet(source, file_name, SOURCES[source]["zone"])


_SIGNATURE = frozenset({"Time", "Type", "Amount", "Unit", "Fee", "Fee Unit", "Address", "Transaction ID"})


def _detect_format(text: str) -> bool:
    """Wie die bisherige Formaterkennung: eine Kopfzeile unter den ersten 30, die alle Spalten des Formats nennt."""
    for line in text.lstrip("\ufeff").splitlines()[:30]:
        delimiter = max(",;\t", key=line.count)
        if _SIGNATURE <= {cell.strip().strip('"') for cell in line.split(delimiter)}:
            return True
    return False


def _bitbox(text: str, file_name: str) -> dict[str, Any]:
    sheet = _Sheet("bitbox", file_name)
    found = re.search(r"-v0-([0-9a-f]{8})-([a-z0-9]+)-(\d+)", Path(file_name).name)
    wallet = f"{found.group(1)}-{found.group(2)}-{found.group(3)}" if found else Path(file_name).stem
    for number, row in sheet.numbered(_rows(text)):
        try:
            scale, ticker = _UNITS.get((row.get("Unit") or "").lower(), (Decimal(1), _ticker(row.get("Unit", ""))))
            fee_scale = _UNITS.get((row.get("Fee Unit") or "").lower(), (Decimal(1), ""))[0]
            amount, fee = _number(row.get("Amount")), _number(row.get("Fee"))
            kind = row.get("Type", "")
            if kind not in ("sent", "received"):
                sheet.skip("crypto_unsupported"); continue
            fee_unit = _UNITS.get((row.get("Fee Unit") or "").lower(), (Decimal(1), ""))[1]
            value = None if amount is None else abs(amount) * scale
            # Die Gebuehr eines Token-Transfers zahlt das ETH-Konto: steht sie in Wei bei einem Token, gehoert sie nicht zur Token-Menge.
            own_fee = None if fee is None or kind != "sent" or (fee_unit and fee_unit != ticker) else abs(fee) * fee_scale
            if value is not None and value == 0:
                if own_fee:
                    sheet.add(number, wallet, _iso_time(row.get("Time", "")), ticker, "fee_only", -own_fee, hash=row.get("Transaction ID"))
                else:
                    sheet.skip("crypto_zero_amount")
                continue
            sheet.add(number, wallet, _iso_time(row.get("Time", "")), ticker, "move",
                      None if value is None else (value if kind == "received" else -value), fee_quantity=own_fee,
                      hash=row.get("Transaction ID"), address=row.get("Address") if kind == "sent" else "")
        except ArithmeticError:   # Zahl oder Zeit ausserhalb jedes Rahmens (verstuemmelter Beleg): Zeile unlesbar statt Absturz
            sheet.skip("crypto_unreadable_row", number, "number", "unreadable")
    return sheet.result()


READERS = {"bitbox_crypto_v1": _bitbox}
DETECTORS = {"bitbox_crypto_v1": _detect_format}
COMBINERS: dict = {}
