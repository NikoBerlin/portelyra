"""Erzeuger erfundener BitBox-Exporte fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Ein- und Ausgaenge eines Wallet-Kontos; aus ihnen baut der Erzeuger den Export der BitBoxApp
(je Konto und Token eine Datei, Dateiname "<Datum>-at-<Zeit>-v0-<Kennung>-<coin>-<n>-export.csv") und - unabhaengig vom Leser - das
erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf; aus dem SDK nimmt er nur die Zeilenkennung (row_key), die das Ergebnis
verlangt. Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Kennungen, Adressen, Transaktionskennungen, Mengen, Zeiten.

Abgedeckt: Ein- und Ausgang in der kleinsten Einheit (Satoshi, Wei, Gwei) und in ganzen Coins; Netzgebuehr am Ausgang in der Menge
des Coins; Token-Konto, dessen Gebuehr in Wei das ETH-Konto zahlt (nicht an der Token-Menge); Gebuehr ohne Transfer (Menge 0 mit
Gebuehr); Menge 0 ohne eigene Gebuehr; Senden an sich selbst (nicht gelesen); unbestaetigter Vorgang ohne Zeit (Zeile unvollstaendig);
Zeiten mit Zone; aeltere Exporte ohne die Spalten zum historischen Wert; umbenannte Datei (Wallet = Dateiname ohne Endung).

Die Tage liegen in der Vergangenheit (2021-2024), damit der Beleg auch die Regel "kein Buchungstag nach heute" erfuellt, wenn der
Selbsttest vor einer Installation mit dem Datum des Rechners laeuft.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import io
import random
from typing import Any

from portelyra_reader_sdk_v1 import crypto_row_key

UTC = timezone.utc
HEADER = ["Time", "Type", "Amount", "Unit", "Fee", "Fee Unit", "Address", "Transaction ID", "Historical value",
          "Historical value currency", "Note"]
OLD_HEADER = HEADER[:8] + ["Note"]          # aeltere BitBoxApp: ohne historischen Wert
BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
HEX = "0123456789abcdef"
TOKENS = ("LINK", "USDC", "UNI")


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _chars(rng: random.Random, alphabet: str, count: int) -> str:
    return "".join(rng.choice(alphabet) for _ in range(count))


class _Account:
    """Ein erfundenes Wallet-Konto: Coin im Dateinamen, Ticker, Einheiten von Menge und Gebuehr, Adress- und Kennungsform."""

    def __init__(self, rng: random.Random, kind: str):
        self.rng, self.kind = rng, kind
        self.coin = {"btc": "btc", "ltc": "ltc", "eth": "eth", "token": "eth"}[kind]
        self.token = rng.choice(TOKENS) if kind == "token" else ""
        self.ticker = {"btc": "BTC", "ltc": "LTC", "eth": "ETH"}.get(kind, self.token)
        if kind == "btc":
            self.unit = self.fee_unit = rng.choice(("satoshi", "satoshi", "satoshi", "sat"))
        elif kind == "ltc":
            self.unit = self.fee_unit = "LTC"
        elif kind == "eth":
            self.unit, self.fee_unit = rng.choice(("wei", "wei", "gwei")), rng.choice(("wei", "wei", "gwei"))
        else:
            self.unit, self.fee_unit = self.token, "wei"
        # Die Gebuehr eines Token-Transfers zahlt das ETH-Konto; sie gehoert nie zur Token-Menge.
        self.own_fee = kind != "token"

    def amount(self) -> tuple[str, Decimal]:
        """Menge als Text in der Einheit des Exports und als Coin-Menge."""
        rng = self.rng
        if self.kind == "btc":
            sats = rng.randrange(1_000, 50_000_000)
            return str(sats), Decimal(sats).scaleb(-8)
        if self.kind == "ltc":
            value = Decimal(rng.randrange(100_000, 2_000_000_000)).scaleb(-8)
            return f"{value:.8f}", value
        if self.kind == "eth":
            if self.unit == "gwei":
                gwei = rng.randrange(1_000_000, 5_000_000_000)
                return str(gwei), Decimal(gwei).scaleb(-9)
            wei = rng.randrange(10**15, 5 * 10**18)
            return str(wei), Decimal(wei).scaleb(-18)
        value = Decimal(rng.randrange(1, 100_000_000)).scaleb(-rng.choice((0, 2, 4, 6)))
        return format(value, "f"), value

    def fee(self) -> tuple[str, Decimal]:
        """Netzgebuehr als Text in der Gebuehreneinheit und als Coin-Menge (bei Token: ETH)."""
        rng = self.rng
        if self.kind == "btc":
            sats = rng.randrange(200, 20_000)
            return str(sats), Decimal(sats).scaleb(-8)
        if self.kind == "ltc":
            value = Decimal(rng.randrange(1_000, 100_000)).scaleb(-8)
            return f"{value:.8f}", value
        gwei = rng.choice((21_000, 46_000, 65_000)) * rng.randrange(5, 150)
        return (str(gwei) if self.fee_unit == "gwei" else str(gwei * 10**9)), Decimal(gwei).scaleb(-9)

    def address(self) -> str:
        if self.kind == "btc":
            return "bc1q" + _chars(self.rng, BECH32, 38)
        if self.kind == "ltc":
            return "ltc1q" + _chars(self.rng, BECH32, 38)
        return "0x" + _chars(self.rng, HEX, 40)

    def tx_hash(self) -> str:
        return ("0x" if self.coin == "eth" else "") + _chars(self.rng, HEX, 64)


def _time_text(at: datetime, style: str) -> str:
    """BitBoxApp: RFC 3339, in UTC mit Z oder mit der Zone des Rechners (hier ein erfundener Versatz)."""
    if style == "Z":
        return at.strftime("%Y-%m-%dT%H:%M:%SZ")
    offset = timedelta(hours=2 if 4 <= at.month <= 9 else 1)
    return (at + offset).strftime("%Y-%m-%dT%H:%M:%S") + f"+{offset.seconds // 3600:02d}:00"


def _generate(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    account = _Account(rng, rng.choice(("btc", "btc", "ltc", "eth", "eth", "token")))
    identifier, number = _chars(rng, HEX, 8), rng.randrange(0, 4)
    style = rng.choice(("Z", "Z", "offset"))
    header = HEADER if rng.random() < 0.8 else OLD_HEADER
    when = datetime(2021, 1, 1, tzinfo=UTC) + timedelta(seconds=rng.randrange(0, 1_100 * 86_400))
    own_address = account.address()

    lines: list[list[str]] = []
    candidates: list[dict[str, Any]] = []
    reasons: Counter = Counter()

    def expect(row_no: int, at: datetime, kind: str, quantity: Decimal, fee: Decimal | None, tx_hash: str, address: str) -> None:
        row = {"profile": "crypto_row", "source": "bitbox", "file_name": file_name, "row_no": row_no, "wallet": wallet,
               "at_utc": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": "UTC", "ticker": account.ticker, "kind": kind,
               "quantity": _plain(quantity), "fee_quantity": None if fee is None else _plain(fee), "eur": None, "eur_fee": None,
               "transaction_id": "", "hash": tx_hash, "address": address, "group": "", "quote": ""}
        row["row_key"] = crypto_row_key(row)
        candidates.append(row)

    events: list[tuple[str, datetime]] = []
    for _ in range(rng.randrange(1, 26)):
        when += timedelta(seconds=rng.randrange(60, 12 * 86_400))
        roll = rng.random()
        if roll < 0.40:
            event = "received"
        elif roll < 0.80:
            event = "sent"
        elif roll < 0.87:
            event = "fee_only" if account.kind == "eth" else "sent"
        elif roll < 0.92:
            event = "zero" if account.kind in ("eth", "token") else "received"
        elif roll < 0.96:
            event = "self"
        else:
            event = "pending"
        events.append((event, when))
    if not any(event in ("received", "sent", "fee_only") for event, _ in events):   # mindestens eine Bewegung
        when += timedelta(hours=5)
        events.append(("received", when))
    events.sort(key=lambda item: item[0] == "pending")   # unbestaetigte Vorgaenge sind die juengsten

    # Dateiname und Wallet: Kennung, Coin und Kontonummer aus dem Namen; eine umbenannte Datei heisst nach ihrem Namen.
    export = when + timedelta(days=rng.randrange(1, 30), seconds=rng.randrange(0, 86_400))
    if rng.random() < 0.8:
        token_part = f"-erc20-{account.token.lower()}" if account.token else ""
        file_name = f"{export:%Y-%m-%d}-at-{export:%H-%M-%S}-v0-{identifier}-{account.coin}-{number}{token_part}-export.csv"
        wallet = f"{identifier}-{account.coin}-{number}"
    else:
        wallet = f"bitbox-{account.coin}-konto-{seed % 1000}"
        file_name = wallet + ".csv"

    for row_no, (event, at) in enumerate(events, 1):
        tx_hash = account.tx_hash()
        amount_text, quantity = account.amount()
        fee_text, fee_unit, fee = "", "", None
        # Ausgang: Senden, Gebuehr ohne Transfer, Senden an sich selbst, beim Token auch der Vorgang ohne Menge (etwa eine Freigabe).
        outgoing = event in ("sent", "fee_only", "self") or (event == "zero" and account.kind == "token") \
            or (event == "pending" and rng.random() < 0.5)
        if outgoing:
            kind_text = "sent_to_yourself" if event == "self" else "sent"
            address = own_address if event == "self" else account.address()
            if event != "sent" or rng.random() < 0.9:
                fee_text, fee = account.fee()
                fee_unit = account.fee_unit
        else:
            kind_text, address = "received", own_address
            if event != "zero" and rng.random() < 0.2:   # mitunter mit der Gebuehr des Absenders: gehoert nicht zum Eingang
                fee_text, fee = account.fee()
                fee_unit = account.fee_unit
        if event in ("fee_only", "zero"):
            amount_text, quantity = "0", Decimal(0)
        own = fee if outgoing and account.own_fee else None
        time_text = "" if event == "pending" else _time_text(at, style)   # unbestaetigt: noch ohne Zeit
        historical = f"{Decimal(rng.randrange(1, 900_000)) / 100:.2f}"
        note = rng.choice(("", "", "", "Erfundene Notiz", "Erfunden, mit Komma"))
        cells = [time_text, kind_text, amount_text, account.unit, fee_text, fee_unit, address, tx_hash]
        lines.append(cells + ([historical, "EUR", note] if header is HEADER else [note]))

        if event == "self":
            reasons["crypto_unsupported"] += 1
        elif event == "pending":
            reasons["crypto_unreadable_row"] += 1
        elif quantity == 0:
            if own:
                expect(row_no, at, "fee_only", -own, None, tx_hash, "")
            else:
                reasons["crypto_zero_amount"] += 1
        elif outgoing:
            expect(row_no, at, "move", -quantity, own, tx_hash, address)
        else:
            expect(row_no, at, "move", quantity, None, tx_hash, "")

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(lines)
    expected = {"status": "multi", "candidates": candidates, "row_reasons": dict(reasons)}
    return {"file_name": file_name, "content": buffer.getvalue(), "expected": expected}


GENERATORS = {"bitbox_crypto_v1": _generate}
