"""Portelyra-Leser ledger: Krypto-Export (statement_reader_v1, Aufruf read_text/detect).

Erzeugt aus dem bisherigen Kernmodul (rc.375) ohne Aenderung der Leselogik. Liefert die Zeilen einer Datei; Paarung von
Transfers ueber Boersen hinweg und Buchung bleiben im Kern.
"""
from __future__ import annotations

from typing import Any

from portelyra_reader_sdk_v1 import (
    CryptoSheet,
    iso_time as _iso_time,
    crypto_number as _number,
    csv_dict_rows as _rows,
    crypto_ticker as _ticker,
)


SOURCES = {"ledger_live": {"zone": "UTC"}}


def _Sheet(source: str, file_name: str) -> CryptoSheet:
    return CryptoSheet(source, file_name, SOURCES[source]["zone"])


_SIGNATURE = frozenset({"Operation Date", "Currency Ticker", "Operation Type", "Operation Amount", "Operation Hash"})


def _detect_format(text: str) -> bool:
    """Wie die bisherige Formaterkennung: eine Kopfzeile unter den ersten 30, die alle Spalten des Formats nennt."""
    for line in text.lstrip("\ufeff").splitlines()[:30]:
        delimiter = max(",;\t", key=line.count)
        if _SIGNATURE <= {cell.strip().strip('"') for cell in line.split(delimiter)}:
            return True
    return False


def _ledger_live(text: str, file_name: str) -> dict[str, Any]:
    sheet = _Sheet("ledger_live", file_name)
    for number, row in sheet.numbered(_rows(text)):
        try:
            kind, ticker = row.get("Operation Type", ""), _ticker(row.get("Currency Ticker", ""))
            amount, fee = _number(row.get("Operation Amount")), _number(row.get("Operation Fees"))
            at = _iso_time(row.get("Operation Date", ""))
            if (row.get("Status") or "Confirmed") not in ("Confirmed", ""):
                sheet.skip("crypto_pending"); continue
            wallet = row.get("Account Name") or ticker
            if kind in ("IN", "OUT") and amount is not None and amount == 0:
                if kind == "OUT" and fee:   # bei IN zahlt die Gebuehr der Absender
                    sheet.add(number, wallet, at, ticker, "fee_only", -abs(fee), hash=row.get("Operation Hash"))
                else:
                    sheet.skip("crypto_zero_amount")
                continue
            if kind == "IN":
                sheet.add(number, wallet, at, ticker, "move", None if amount is None else abs(amount), hash=row.get("Operation Hash"))
            elif kind == "OUT":
                # Ledger Live fuehrt den Abgang einschliesslich Gebuehr: ohne Gebuehr ist er die versendete Menge
                fee = abs(fee) if fee else None
                sent = None if amount is None else abs(amount) - (fee or 0)
                sheet.add(number, wallet, at, ticker, "move", None if sent is None else -sent, fee_quantity=fee, hash=row.get("Operation Hash"))
            elif kind == "FEES":
                paid = fee or amount   # Gebuehr 0 und Menge unlesbar (verstuemmelter Beleg): Zeile unvollstaendig statt Absturz
                sheet.add(number, wallet, at, ticker, "fee_only", None if paid is None else -abs(paid), hash=row.get("Operation Hash"))
            else:
                sheet.skip("crypto_unsupported")
        except ArithmeticError:   # Zahl oder Zeit ausserhalb jedes Rahmens (verstuemmelter Beleg): Zeile unlesbar statt Absturz
            sheet.skip("crypto_unreadable_row", number, "number", "unreadable")
    return sheet.result()


READERS = {"ledger_live_crypto_v1": _ledger_live}
DETECTORS = {"ledger_live_crypto_v1": _detect_format}
COMBINERS: dict = {}
