"""Erzeuger erfundener Ledger-Live-Exporte fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Vorgaenge auf einem bis vier Konten; aus ihnen baut der Erzeuger den Export der Vorgaenge aus
Ledger Live (alle Konten in einer Datei, juengster Vorgang oben, Zeiten in UTC mit Millisekunden) und - unabhaengig vom Leser - das
erwartete Ergebnis. Der Erzeuger ruft den Leser nie auf; aus dem SDK nimmt er nur die Zeilenkennung (row_key), die das Ergebnis
verlangt. Gleicher Startwert, gleicher Beleg. Alle Werte sind erfunden: Kontonamen, xpub, Transaktionskennungen, Mengen, Zeiten.

Abgedeckt: Eingang (eine mitgefuehrte Gebuehr des Absenders zaehlt nicht), Ausgang samt Netzgebuehr (Ledger Live fuehrt den Abgang
einschliesslich Gebuehr; versendet ist "Operation Amount" minus "Operation Fees"), Ausgang ohne genannte Gebuehr, Vorgang nur mit
Gebuehr (Typ FEES, auch ohne Gebuehrenspalte), Ausgang mit Menge 0 und Gebuehr, Eingang mit Menge 0 (Staub, Spam), nicht gelesene
Vorgangsarten (etwa DELEGATE, REWARD), noch nicht bestaetigte Vorgaenge, Konto ohne Namen (Wallet = Ticker), aeltere Exporte ohne
Spalte "Status".

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
HEADER = ["Operation Date", "Status", "Currency Ticker", "Operation Type", "Operation Amount", "Operation Fees", "Operation Hash",
          "Account Name", "Account xpub", "Countervalue Ticker", "Countervalue at Operation Date", "Countervalue at CSV Export"]
# Kontoname, Ticker, Stellen, Spanne der Menge (in Stellen), Spanne der Gebuehr (in Stellen), Form der Kennung, Kurs in EUR
ACCOUNTS = (
    ("Bitcoin", "BTC", 8, (10_000, 100_000_000), (500, 20_000), "hex", 30_000),
    ("Ethereum", "ETH", 10, (10_000_000, 100_000_000_000), (2_000_000, 100_000_000), "0x", 2_000),
    ("Solana", "SOL", 9, (10_000_000, 100_000_000_000), (5_000, 5_001), "base58", 60),
    ("XRP", "XRP", 6, (1_000_000, 5_000_000_000), (10, 20), "HEX", 1),
    ("Cardano", "ADA", 6, (1_000_000, 5_000_000_000), (160_000, 200_000), "hex", 1),
    ("Polkadot", "DOT", 10, (1_000_000_000, 5_000_000_000_000), (150_000_000, 2_000_000_000), "0x", 6),
    ("Litecoin", "LTC", 8, (1_000_000, 5_000_000_000), (1_000, 100_000), "hex", 80),
)
UNSUPPORTED = ("DELEGATE", "UNDELEGATE", "REWARD", "NFT_IN", "OPT_IN", "NONE")
HEX = "0123456789abcdef"
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _hash(rng: random.Random, form: str) -> str:
    if form == "base58":
        return "".join(rng.choice(BASE58) for _ in range(88))
    digits = "".join(rng.choice(HEX) for _ in range(64))
    return {"hex": digits, "HEX": digits.upper(), "0x": "0x" + digits}[form]


def _generate(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    with_status = rng.random() < 0.85
    header = HEADER if with_status else [name for name in HEADER if name != "Status"]
    accounts = []
    for label, ticker, places, amounts, fees, form, price in rng.sample(ACCOUNTS, rng.randrange(1, 5)):
        name = "" if rng.random() < 0.1 else f"{label} {rng.randrange(1, 4)}"
        xpub = "xpubERFUNDEN" + "".join(rng.choice(BASE58) for _ in range(24))
        accounts.append({"name": name, "ticker": ticker, "places": places, "amounts": amounts, "fees": fees, "form": form, "price": price,
                         "xpub": xpub})
    when = datetime(2021, 1, 1, tzinfo=UTC) + timedelta(seconds=rng.randrange(0, 1_100 * 86_400))
    events = []
    for _ in range(rng.randrange(1, 26)):
        roll = rng.random()
        if roll < 0.35:
            event = "IN"
        elif roll < 0.70:
            event = "OUT"
        elif roll < 0.78:
            event = "FEES"
        elif roll < 0.83:
            event = "OUT_ZERO"
        elif roll < 0.87:
            event = "IN_ZERO"
        elif roll < 0.94:
            event = "UNSUPPORTED"
        else:
            event = "PENDING" if with_status else "IN"
        events.append(event)
    if not any(event in ("IN", "OUT", "FEES", "OUT_ZERO") for event in events):   # mindestens eine Bewegung
        events.append("IN")
    events.sort(key=lambda event: event == "PENDING")   # noch nicht bestaetigt sind nur die juengsten
    operations = []
    for event in events:
        when += timedelta(seconds=rng.randrange(60, 12 * 86_400), milliseconds=rng.randrange(1000))
        operations.append((when, event, rng.choice(accounts)))
    operations.reverse()   # Ledger Live: juengster Vorgang oben
    export = when + timedelta(days=rng.randrange(1, 40))
    file_name = f"ledgerwallet-operations-{export:%Y.%m.%d}.csv"

    lines: list[list[str]] = []
    candidates: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    for row_no, (at, event, account) in enumerate(operations, 1):
        places = account["places"]
        amount = Decimal(rng.randrange(*account["amounts"])).scaleb(-places)
        fee = Decimal(rng.randrange(*account["fees"])).scaleb(-places)
        tx_hash = _hash(rng, account["form"])
        status = "Confirmed"
        wallet = account["name"] or account["ticker"]
        if event == "IN":
            kind, amount_value, fee_value = "IN", amount, fee if rng.random() < 0.3 else None
        elif event == "OUT":
            kind, amount_value, fee_value = "OUT", amount + fee, fee if rng.random() < 0.92 else None
            if fee_value is None:   # ohne genannte Gebuehr ist der Abgang die versendete Menge
                amount_value = amount
        elif event == "FEES":
            kind, amount_value, fee_value = "FEES", fee, fee if rng.random() < 0.7 else None
        elif event == "OUT_ZERO":
            kind, amount_value, fee_value = "OUT", Decimal(0), fee
        elif event == "IN_ZERO":
            kind, amount_value, fee_value = "IN", Decimal(0), None
        elif event == "UNSUPPORTED":
            kind, amount_value, fee_value = rng.choice(UNSUPPORTED), amount if rng.random() < 0.5 else Decimal(0), fee
        else:
            kind, amount_value, fee_value = rng.choice(("IN", "OUT")), amount, fee
            status = "Pending"
        # Mengen mit oder ohne nachgestellte Nullen, wie sie in Exporten vorkommen
        text = (lambda value: f"{value:.{places}f}") if rng.random() < 0.3 else _plain
        countervalue = f"{amount_value * account['price']:.2f}"
        cells = [f"{at:%Y-%m-%dT%H:%M:%S}.{at.microsecond // 1000:03d}Z"] + ([status] if with_status else [])
        cells += [account["ticker"], kind, text(amount_value), "" if fee_value is None else text(fee_value), tx_hash, account["name"],
                  account["xpub"], "EUR", countervalue, f"{amount_value * account['price'] * Decimal('1.1'):.2f}"]
        lines.append(cells)

        quantity: Decimal | None = None
        fee_quantity: Decimal | None = None
        if status != "Confirmed":
            reasons["crypto_pending"] += 1; continue
        if event == "IN":
            kind_out, quantity = "move", amount
        elif event == "OUT":
            kind_out, quantity, fee_quantity = "move", -amount, fee_value
        elif event in ("FEES", "OUT_ZERO"):
            kind_out, quantity = "fee_only", -fee
        elif event == "IN_ZERO":
            reasons["crypto_zero_amount"] += 1; continue
        else:
            reasons["crypto_unsupported"] += 1; continue
        row = {"profile": "crypto_row", "source": "ledger_live", "file_name": file_name, "row_no": row_no, "wallet": wallet,
               "at_utc": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": "UTC", "ticker": account["ticker"], "kind": kind_out,
               "quantity": _plain(quantity), "fee_quantity": None if fee_quantity is None else _plain(fee_quantity), "eur": None,
               "eur_fee": None, "transaction_id": "", "hash": tx_hash, "address": "", "group": "", "quote": ""}
        row["row_key"] = crypto_row_key(row)
        candidates.append(row)

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(lines)
    expected = {"status": "multi", "candidates": candidates, "row_reasons": dict(reasons)}
    return {"file_name": file_name, "content": buffer.getvalue(), "expected": expected}


GENERATORS = {"ledger_live_crypto_v1": _generate}
