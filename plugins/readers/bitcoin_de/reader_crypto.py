"""Portelyra-Leser bitcoin_de: Krypto-Export (statement_reader_v1, Aufruf read_text/detect).

Erzeugt aus dem bisherigen Kernmodul (rc.375) ohne Aenderung der Leselogik. Liefert die Zeilen einer Datei; Paarung von
Transfers ueber Boersen hinweg und Buchung bleiben im Kern.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from decimal import ROUND_HALF_UP
from typing import Any

from portelyra_reader_sdk_v1 import (
    CryptoSheet,
    BERLIN,
    crypto_number as _number,
    parse_time as _parse_time,
    csv_dict_rows as _rows,
    crypto_ticker as _ticker,
)


SOURCES = {"bitcoin_de": {"zone": "Europe/Berlin"}}


def _Sheet(source: str, file_name: str) -> CryptoSheet:
    return CryptoSheet(source, file_name, SOURCES[source]["zone"])


_SIGNATURE = frozenset({"Datum", "Typ", "Währung", "Referenz", "Zu- / Abgang"})


def _detect_format(text: str) -> bool:
    """Wie die bisherige Formaterkennung: eine Kopfzeile unter den ersten 30, die alle Spalten des Formats nennt."""
    for line in text.lstrip("\ufeff").splitlines()[:30]:
        delimiter = max(",;\t", key=line.count)
        if _SIGNATURE <= {cell.strip().strip('"') for cell in line.split(delimiter)}:
            return True
    return False


def _bitcoin_de(text: str, file_name: str) -> dict[str, Any]:
    sheet = _Sheet("bitcoin_de", file_name)
    rows = _rows(text)
    fees: dict[str, Decimal] = defaultdict(Decimal)
    unreadable_fees: set[str] = set()
    for row in rows:
        if row.get("Typ") == "Netzwerk-Gebühr":
            try:
                fees[row.get("Referenz", "")] += abs(_number(row.get("Zu- / Abgang")) or Decimal(0))
            except ArithmeticError:   # Zahl ausserhalb jedes Rahmens (verstuemmelter Beleg): die Gebuehr dieser Referenz ist unlesbar
                unreadable_fees.add(row.get("Referenz", ""))
    for number, row in sheet.numbered(rows):
        try:
            kind, ticker = row.get("Typ", ""), _ticker(row.get("Währung", ""))
            at = _parse_time(row.get("Datum", ""), "%Y-%m-%d %H:%M:%S", BERLIN)
            if kind == "Registrierung":
                sheet.skip("crypto_registration"); continue
            if kind == "Netzwerk-Gebühr":
                sheet.skip("crypto_fee_row"); continue
            net = _number(row.get("Zu- / Abgang"))
            if kind in ("Kauf", "Verkauf"):
                quote = (row.get("Einheit (Menge vor Gebühr)") or "").upper()
                before_quote = _number(row.get("Menge vor Gebühr"))
                if quote and quote != "EUR" and net is not None and before_quote is not None and abs(net) == abs(before_quote):
                    sheet.skip("crypto_swap_counter_leg"); continue   # Zu-/Abgang in der Gegenwaehrung: Datei des Tausch-Coins
                if quote and quote != "EUR":
                    sheet.add(number, "main", at, ticker, "swap", net, quote=quote, transaction_id=row.get("Referenz")); continue
                # Gebuchte Menge = Zu-/Abgang. Kauf: bezahlt ist "Menge nach Bitcoin.de-Gebühr": Bei
                # Kaeufen geht genau dieser Betrag vom Girokonto ab, nicht "Menge vor Gebühr". Kurswert = Kurs x angekommene Menge,
                # Gebuehr = bezahlter Betrag - Kurswert: zusammen genau der bezahlte Betrag.
                # Verkauf: Kurswert = "Menge vor Gebühr", Gebuehr = Unterschied zu "Menge nach Bitcoin.de-Gebühr".
                before, after = _number(row.get("Menge vor Gebühr")), _number(row.get("Menge nach Bitcoin.de-Gebühr"))
                rate = _number(row.get("Kurs"))
                if rate is not None and rate < 0:   # verstuemmelter Beleg: ein negativer Kurs ist unlesbar, nie ein negativer Kurswert
                    rate = None
                if kind == "Kauf":
                    eur = None if rate is None or net is None else rate * abs(net)
                    fee = None if eur is None or after is None else max(Decimal(0), (abs(after) - eur).quantize(Decimal("0.01"),
                                                                                                 rounding=ROUND_HALF_UP))
                else:
                    eur = None if before is None else abs(before)
                    fee = None if before is None or after is None else abs(abs(before) - abs(after))
                sheet.add(number, "main", at, ticker, "trade", net, eur=eur, eur_fee=fee, transaction_id=row.get("Referenz"))
                continue
            if kind in ("Auszahlung", "Einzahlung"):
                if row.get("Referenz", "") in unreadable_fees:   # Netzwerkgebuehr der Referenz unlesbar
                    sheet.skip("crypto_unreadable_row", number, "fee_quantity", "unreadable"); continue
                address = next((value for key, value in row.items() if key.endswith("-Adresse") and value), "")
                sheet.add(number, "main", at, ticker, "move", net, fee_quantity=fees.get(row.get("Referenz", "")) or None,
                          transaction_id=row.get("Referenz"), address=address)
                continue
            sheet.skip("crypto_unsupported")
        except ArithmeticError:   # Zahl oder Zeit ausserhalb jedes Rahmens (verstuemmelter Beleg): Zeile unlesbar statt Absturz
            sheet.skip("crypto_unreadable_row", number, "number", "unreadable")
    return sheet.result()


READERS = {"bitcoin_de_crypto_v1": _bitcoin_de}
DETECTORS = {"bitcoin_de_crypto_v1": _detect_format}
COMBINERS: dict = {}
