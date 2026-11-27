"""Erzeuger erfundener Coinbase-Transaktionsberichte fuer den Selbsttest (statement_reader_v1, Stufe 3, rc.379).

Aus einem Startwert entstehen erfundene Vorgaenge eines Coinbase-Kontos. Jeder Vorgang kennt seine Bedeutung fuer die drei Leser
des Plugins: die Bewegung des EUR-Wallets (Bereich cash), die Krypto-Zeile oder den Grund, sie zu uebergehen (crypto), und die
Reward-Angaben (reward). Daraus baut der Erzeuger den Bericht - Vorspannzeilen vor der Kopfzeile wie bei Coinbase oder keine - und,
unabhaengig von den Lesern, das erwartete Ergebnis. Er ruft keinen Leser auf; aus dem SDK nutzt er nur die Kennung einer
Krypto-Zeile (crypto_row_key), die das Ergebnis verlangt. Gleicher Startwert, gleicher Beleg.

Alle Werte sind erfunden: Namen, Kennungen, Adressen, Kartennummern, Mengen, Kurse, Betraege und Zeitpunkte. Die Zeitpunkte liegen
in 2021-2024, damit der Beleg auch die Regel "kein Buchungstag nach heute" erfuellt.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
import io
import random
from typing import Any
from zoneinfo import ZoneInfo

from portelyra_reader_sdk_v1 import crypto_row_key

TOTAL, FEES = "Total (inclusive of fees and/or spread)", "Fees and/or Spread"
HEADER = ("ID", "Timestamp", "Transaction Type", "Asset", "Quantity Transacted", "Price Currency", "Price at Transaction", "Subtotal", TOTAL,
          FEES, "Notes", "Sender Address", "Recipient Address")
# Kurzform wie im Reward-Testbeleg: ohne Subtotal und ohne Adressen.
SHORT_HEADER = tuple(name for name in HEADER if name not in ("Subtotal", "Sender Address", "Recipient Address"))
# (Coin, erfundener Kurs in Euro, Nachkommastellen der Menge)
COINS = (("BTC", "23817.40", 8), ("ETH", "1642.15", 6), ("SOL", "38.27", 4), ("ADA", "0.3412", 2), ("DOT", "6.18", 4), ("TOKA", "3.20", 2),
         ("TOKC", "0.0600", 1), ("TOKB", "6.00", 2), ("ATOM", "9.71", 4), ("XTZ", "0.94", 3), ("ALGO", "0.21", 2))
STAKED = ("ETH", "SOL", "ADA", "DOT", "ATOM", "XTZ")
# Reward-Arten, die beide Leser als Reward kennen: Der Krypto-Leser uebergeht sie (crypto_reward), der Reward-Leser liest sie.
REWARD_LABELS = ("Staking Income", "Learning Reward", "Incentives Rewards Payout", "Retail Simple Price Improvement")
UNSUPPORTED = ("Pro Deposit", "Pro Withdrawal", "Exchange Deposit", "Exchange Withdrawal")
CENT = Decimal("0.01")
BERLIN = ZoneInfo("Europe/Berlin")

# Gewichte der Vorgangsarten je Leser: jeder Bericht enthaelt alles, der Schwerpunkt liegt auf dem, was der Leser liest.
CASH_WEIGHTS = {"deposit_eur": 3, "withdrawal_eur": 2, "sell_eur": 3, "buy_wallet": 3, "buy_card": 2, "sell_eurc": 1, "dust": 1,
                "trade_quote": 1, "convert": 1, "send": 1, "receive": 1, "deposit_coin": 1, "staking": 1, "reward": 1, "unsupported": 1}
CRYPTO_WEIGHTS = {"deposit_eur": 1, "withdrawal_eur": 1, "sell_eur": 3, "buy_wallet": 2, "buy_card": 3, "sell_eurc": 1, "dust": 1,
                  "trade_quote": 2, "convert": 2, "send": 2, "receive": 2, "deposit_coin": 1, "withdrawal_coin": 1, "staking": 2, "reward": 2,
                  "unsupported": 1}
REWARD_WEIGHTS = {"reward": 8, "deposit_eur": 1, "withdrawal_eur": 1, "sell_eur": 1, "buy_card": 1, "trade_quote": 1, "convert": 1, "send": 1,
                  "receive": 1, "staking": 1, "unsupported": 1}


def _plain(amount: Decimal) -> str:
    text = format(amount.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _norm(text: str) -> str:
    """Merkmal einer Zelle fuer doppelte Zeilen: klein geschrieben, Leerraum zusammengezogen."""
    return " ".join(text.lower().split())


def _hex(rng: random.Random, length: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(length))


def _money(amount: Decimal, grouped: bool = False, euro: bool = True) -> str:
    """Geldbetrag wie im Bericht: "€316.80", mit Tausendertrennung "€1,234.56", negativ "-€2.00"; ohne Euro-Zeichen "-3.20"."""
    body = f"{abs(amount):,.2f}" if grouped else f"{abs(amount):.2f}"
    return ("-" if amount < 0 else "") + ("€" if euro else "") + body


def _coin(rng: random.Random, choices: tuple[str, ...] | None = None, cheap: bool = False) -> tuple[str, Decimal, Decimal]:
    """Coin, Kurs und kleinste Mengeneinheit."""
    pool = [coin for coin in COINS if (choices is None or coin[0] in choices) and (not cheap or Decimal(coin[1]) < 1000)]
    ticker, price, places = rng.choice(pool)
    return ticker, Decimal(price), Decimal(1).scaleb(-places)


def _quantity_text(rng: random.Random, quantity: Decimal, step: Decimal, negative: bool) -> str:
    """Menge wie im Bericht, mal mit allen Nachkommastellen ("0.10000000"), mal knapp ("0.1"); abgehend oft mit Minus."""
    text = f"{quantity:.{-step.as_tuple().exponent}f}" if rng.random() < 0.3 else _plain(quantity)
    return "-" + text if negative else text


def _event(rng: random.Random, kind: str, moment: datetime, grouping: bool, special: bool = True) -> dict[str, Any]:
    """Ein erfundener Vorgang: Zellen des Berichts und seine Bedeutung fuer die drei Leser.

    cash:   None (beruehrt das EUR-Wallet nicht), "invalid" (Betrag nicht lesbar) oder die Bewegung mit Vorzeichen (0 = keine).
    crypto: Grund, die Zeile zu uebergehen (Text), oder die Angaben der Krypto-Zeile; Menge None = nicht lesbar.
    reward: None (kein Reward) oder die Reward-Angaben samt Bewertung.
    special=False: ohne Sonderfaelle (fehlende Zellen, unlesbarer Zeitpunkt)."""
    money = lambda amount, euro=True: _money(amount, grouping and rng.random() < 0.5, euro)
    cells = {name: "" for name in HEADER}
    cells["ID"] = _hex(rng, 24)
    stamp_ok = not special or rng.random() >= 0.04
    cells["Timestamp"] = moment.strftime("%Y-%m-%d %H:%M:%S UTC") if stamp_ok else rng.choice(("unbekannt", moment.strftime("%Y-02-30 %H:%M:%S UTC")))
    cash: Any = None
    crypto: Any = None
    reward: dict[str, Any] | None = None
    quantity_value: Decimal | None = None   # Menge, wie sie im Bericht steht (mit Vorzeichen); None = Zelle leer
    fee_value: Decimal | None = None        # Gebuehr, wie sie im Bericht steht; None = Zelle leer
    # Eine Zelle fehlt (Sonderfall): nur eine je Vorgang.
    missing = rng.choice(("total", "subtotal", "fees", "quantity")) if special and rng.random() < 0.22 else None

    if kind in ("deposit_eur", "withdrawal_eur"):
        incoming = kind == "deposit_eur"
        amount = Decimal(rng.randrange(1000, 500_000)) / 100 if rng.random() < 0.7 else Decimal(rng.randrange(10, 5000))
        text = rng.choice((_plain(amount), f"{amount:.2f}", f"{amount:,.2f}" if grouping else f"{amount:.2f}"))
        negative = not incoming and rng.random() < 0.6
        cells.update({"Transaction Type": "Deposit" if incoming else "Withdrawal", "Asset": "EUR", "Quantity Transacted": ("-" if negative else "") + text,
                      "Price Currency": "EUR", "Price at Transaction": "€1.00", "Subtotal": money(amount), TOTAL: money(amount), FEES: "€0.00",
                      "Notes": f"{'Deposited' if incoming else 'Withdrew'} {_plain(amount)} EUR {'from' if incoming else 'to'} Erfundene Bank"})
        quantity_value, fee_value = (-amount if negative else amount), Decimal(0)
        if missing == "quantity":   # Menge fehlt: Betrag nicht lesbar
            cells["Quantity Transacted"], quantity_value, cash = "", None, "invalid"
        else:
            cash = amount if incoming else -amount
        crypto = "crypto_fiat"

    elif kind in ("sell_eur", "sell_eurc", "dust", "buy_wallet", "buy_card"):
        buy = kind in ("buy_wallet", "buy_card")
        ticker, price, step = (("USDC", Decimal("0.9214"), CENT) if kind == "sell_eurc" else _coin(rng))
        value = Decimal(rng.randrange(500, 500_000)) / 100
        rate = Decimal(rng.randrange(0, 250)) / 10000
        if buy:   # Kauf: bezahlt wird Total; der Kurswert (Subtotal) ist Total ohne Gebuehr
            total = value
            fee = (total * rate).quantize(CENT)
            subtotal = total - fee
            quantity = max((subtotal / price).quantize(step, rounding=ROUND_DOWN), step)
        else:     # Verkauf: gutgeschrieben wird Total; Kurswert ohne Gebuehr und Spread
            quantity = max((value / price).quantize(step, rounding=ROUND_DOWN), step)
            subtotal = (quantity * price).quantize(CENT)
            fee = (subtotal * rate).quantize(CENT)
            total = subtotal - fee
        if kind == "dust":   # Kleinstverkauf: alles auf 0,00 gerundet, das EUR-Wallet bewegt sich nicht
            quantity, subtotal, fee, total, missing = step, Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), None
        label = ("Advanced Trade " if rng.random() < 0.3 else "") + ("Buy" if buy else "Sell")
        if kind in ("buy_wallet", "buy_card"):
            funding = "EUR-Wallet" if kind == "buy_wallet" else f"{rng.randrange(4000, 5000)}********{rng.randrange(1000, 10000)}"
            notes = f"Bought {_plain(quantity)} {ticker} for {_plain(total)} EUR using {funding}"
        else:
            notes = f"Sold {_plain(quantity)} {ticker} for {_plain(total)} {'EURC' if kind == 'sell_eurc' else 'EUR'}"
        negative = not buy and rng.random() < 0.7
        fee_negative = not buy and rng.random() < 0.5
        cells.update({"Transaction Type": label, "Asset": ticker, "Quantity Transacted": _quantity_text(rng, quantity, step, negative),
                      "Price Currency": rng.choice(("EUR",) * 8 + ("", "eur")), "Price at Transaction": money(price.quantize(CENT)),
                      "Subtotal": money(subtotal), TOTAL: money(total), FEES: _money(-fee if fee_negative else fee, euro=rng.random() < 0.7),
                      "Notes": notes})
        quantity_value, fee_value = (-quantity if negative else quantity), (-fee if fee_negative else fee)
        printed_total, printed_subtotal, printed_fee = total, subtotal, fee
        if missing == "total":
            cells[TOTAL], printed_total = "", None
        elif missing == "subtotal":
            cells["Subtotal"], printed_subtotal = "", None
        elif missing == "fees":
            cells[FEES], printed_fee, fee_value = "", None, None
        elif missing == "quantity":
            cells["Quantity Transacted"], quantity_value = "", None
        # EUR-Wallet: Verkauf gegen Euro schreibt Total gut, Kauf aus dem Wallet bucht Total ab; Karte und EURC beruehren es nicht.
        if kind in ("sell_eur", "dust", "buy_wallet"):
            cash = "invalid" if printed_total is None else (-printed_total if buy else printed_total)
        # Krypto: Kurswert = Subtotal, Gebuehr = Abstand von Total zu Subtotal, sonst die Gebuehrenspalte, sonst 0.
        if printed_total is not None and printed_subtotal is not None:
            eur_fee = abs(printed_total - printed_subtotal)
        else:
            eur_fee = Decimal(0) if printed_fee is None else printed_fee
        crypto = {"ticker": ticker, "kind": "trade", "quantity": None if quantity_value is None else (quantity if buy else -quantity),
                  "eur": printed_subtotal, "eur_fee": eur_fee, "quote": "", "address": ""}

    elif kind == "trade_quote":   # Handel gegen einen Stablecoin: kein Euro-Betrag, ein Tausch
        ticker, price, step = _coin(rng, ("BTC", "ETH", "SOL", "DOT", "ATOM"))
        quote, buy = rng.choice(("USDC", "USDT")), rng.random() < 0.5
        quantity = max((Decimal(rng.randrange(500, 200_000)) / 100 / price).quantize(step, rounding=ROUND_DOWN), step)
        subtotal = (quantity * price * Decimal("1.08")).quantize(CENT)
        fee = (subtotal * Decimal("0.006")).quantize(CENT)
        total = subtotal + fee if buy else subtotal - fee
        cells.update({"Transaction Type": "Advanced Trade Buy" if buy else "Advanced Trade Sell", "Asset": ticker,
                      "Quantity Transacted": _quantity_text(rng, quantity, step, not buy), "Price Currency": quote,
                      "Price at Transaction": f"{price * Decimal('1.08'):.2f}", "Subtotal": f"{subtotal:.2f}", TOTAL: f"{total:.2f}",
                      FEES: f"{fee:.2f}", "Notes": f"{'Bought' if buy else 'Sold'} {_plain(quantity)} {ticker} for {_plain(total)} {quote} on {ticker}-{quote}"})
        quantity_value, fee_value = (quantity if buy else -quantity), fee
        if missing == "quantity":
            cells["Quantity Transacted"], quantity_value = "", None
        crypto = {"ticker": ticker, "kind": "swap", "quantity": quantity_value, "eur": None, "eur_fee": None, "quote": quote, "address": ""}

    elif kind in ("convert", "staking"):   # Tausch zwischen Coins; Staking-Umbuchung innerhalb des Kontos. Menge, wie sie dasteht.
        ticker, price, step = _coin(rng, STAKED if kind == "staking" else None)
        quantity = max((Decimal(rng.randrange(500, 300_000)) / 100 / price).quantize(step, rounding=ROUND_DOWN), step)
        negative = rng.random() < 0.5
        value = (quantity * price).quantize(CENT)
        if kind == "convert":
            label, notes = "Convert", f"Converted {_plain(quantity)} {ticker} to {_plain(value)} USDC"
        else:
            label = rng.choice(("Retail Staking Transfer", "Retail Unstaking Transfer"))
            notes = f"{'Staked' if label == 'Retail Staking Transfer' else 'Unstaked'} {_plain(quantity)} {ticker}"
        cells.update({"Transaction Type": label, "Asset": ticker, "Quantity Transacted": _quantity_text(rng, quantity, step, negative),
                      "Price Currency": "EUR", "Price at Transaction": money(price.quantize(CENT)), "Subtotal": money(value), TOTAL: money(value),
                      FEES: "€0.00", "Notes": notes})
        quantity_value, fee_value = (-quantity if negative else quantity), Decimal(0)
        if missing == "quantity":
            cells["Quantity Transacted"], quantity_value = "", None
        crypto = {"ticker": ticker, "kind": "swap" if kind == "convert" else "internal", "quantity": quantity_value, "eur": None, "eur_fee": None,
                  "quote": "", "address": ""}

    elif kind in ("send", "receive", "deposit_coin", "withdrawal_coin"):
        incoming = kind in ("receive", "deposit_coin")
        label = {"send": "Send", "receive": "Receive", "deposit_coin": "Deposit", "withdrawal_coin": "Withdrawal"}[kind]
        ticker, price, step = _coin(rng)
        quantity = max((Decimal(rng.randrange(500, 300_000)) / 100 / price).quantize(step, rounding=ROUND_DOWN), step)
        negative = not incoming and rng.random() < 0.7
        value = (quantity * price).quantize(CENT)
        # Adresse ohne Leerzeichen gilt; eine Bezeichnung mit Leerzeichen (keine Adresse) und eine leere Zelle ergeben keine.
        address = rng.choice((f"0x{_hex(rng, 40)}", f"erf1q{_hex(rng, 38)}", "", "Erfundene Wallet"))
        cells.update({"Transaction Type": label, "Asset": ticker, "Quantity Transacted": _quantity_text(rng, quantity, step, negative),
                      "Price Currency": "EUR", "Price at Transaction": money(price.quantize(CENT)), "Subtotal": money(value), TOTAL: money(value),
                      FEES: "€0.00", "Sender Address" if incoming else "Recipient Address": address,
                      "Notes": f"{'Received' if incoming else 'Sent'} {_plain(quantity)} {ticker}"})
        quantity_value, fee_value = (-quantity if negative else quantity), Decimal(0)
        if missing == "quantity":
            cells["Quantity Transacted"], quantity_value = "", None
        crypto = {"ticker": ticker, "kind": "move", "quantity": None if quantity_value is None else (quantity if incoming else -quantity),
                  "eur": None, "eur_fee": None, "quote": "", "address": address if " " not in address else ""}

    elif kind == "reward":
        ticker, price, step = _coin(rng, cheap=True)
        quantity = Decimal(rng.randrange(1, 10**6)) * step / 10_000
        unit = price.quantize(CENT)
        total = (quantity * unit).quantize(CENT)          # kleine Rewards ergeben 0,00
        fee = rng.choice((Decimal("0.00"), None, Decimal(rng.randrange(1, 20)) / 100))
        currency_cell = rng.choice(("EUR", "EUR", ""))
        variant = rng.random()
        total_text, unit_text = _money(total), _money(unit)
        if variant < 0.2:                                 # ohne Gesamtbetrag: Stueckpreis
            total_text = ""
        elif variant < 0.3:                               # weder Gesamtbetrag noch Stueckpreis: keine Bewertung
            total_text, unit_text = "", ""
        elif variant < 0.36:                              # nirgends eine Waehrung: keine Bewertung
            currency_cell, total_text, unit_text = "", f"{total:.2f}", f"{unit:.2f}"
        cells.update({"Transaction Type": rng.choice(REWARD_LABELS), "Asset": ticker, "Quantity Transacted": _plain(quantity),
                      "Price Currency": currency_cell, "Price at Transaction": unit_text, "Subtotal": total_text, TOTAL: total_text,
                      FEES: "" if fee is None else _money(fee), "Notes": f"Erfundener Reward {ticker}"})
        quantity_value, fee_value = quantity, fee
        valid = True
        if special and rng.random() < 0.08:              # unvollstaendiger Reward: Menge 0 oder leer, oder kein Coin
            broken = rng.choice(("zero", "empty", "asset"))
            if broken == "zero":
                cells["Quantity Transacted"], quantity_value = "0", Decimal(0)
            elif broken == "empty":
                cells["Quantity Transacted"], quantity_value = "", None
            else:
                cells["Asset"] = ""
            valid = False
        currency = "EUR" if currency_cell == "EUR" or "€" in total_text or "€" in unit_text else None
        if total_text and total != 0 and currency:
            valuation = {"source_value_mode": "fiat_total", "price_currency": currency, "source_unit_price_decimal": None,
                         "source_fiat_total_decimal": _plain(total)}
        elif unit_text and unit != 0 and currency:
            valuation = {"source_value_mode": "unit_price", "price_currency": currency, "source_unit_price_decimal": _plain(unit),
                         "source_fiat_total_decimal": None}
        else:
            valuation = {"source_value_mode": "none", "price_currency": currency, "source_unit_price_decimal": None, "source_fiat_total_decimal": None}
        reward = {"valid": valid, "asset": ticker, "quantity": _plain(quantity), "fee": None if fee is None or fee == 0 else _plain(fee),
                  "valuation": valuation}
        crypto = "crypto_reward"

    else:   # unsupported: Arten, die keiner der Leser liest
        ticker, price, step = _coin(rng)
        quantity = max((Decimal(rng.randrange(500, 100_000)) / 100 / price).quantize(step, rounding=ROUND_DOWN), step)
        label = rng.choice(UNSUPPORTED)
        negative = "Withdrawal" in label
        cells.update({"Transaction Type": label, "Asset": ticker, "Quantity Transacted": _quantity_text(rng, quantity, step, negative),
                      "Price Currency": "EUR", "Price at Transaction": money(price.quantize(CENT)), "Subtotal": "", TOTAL: "", FEES: "",
                      "Notes": f"{label} {_plain(quantity)} {ticker}"})
        quantity_value = -quantity if negative else quantity
        crypto = "crypto_unsupported"

    return {"cells": cells, "moment": moment, "stamp_ok": stamp_ok, "cash": cash, "crypto": crypto, "reward": reward,
            "quantity_value": quantity_value, "fee_value": fee_value}


def _events(rng: random.Random, weights: dict[str, int], grouping: bool, low: int = 3, high: int = 25) -> list[dict[str, Any]]:
    kinds, chances = zip(*weights.items())
    moment = datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(days=rng.randrange(0, 365 * 3), seconds=rng.randrange(0, 86_400))
    events = []
    for _ in range(rng.randrange(low, high + 1)):
        moment += timedelta(days=rng.randrange(0, 12), seconds=rng.randrange(0, 86_400))
        # Kurz vor Mitternacht UTC: in Europe/Berlin schon der naechste Tag.
        at = moment.replace(hour=rng.choice((22, 23))) if rng.random() < 0.15 else moment
        events.append(_event(rng, rng.choices(kinds, chances)[0], at, grouping))
    return events


def _report(rng: random.Random, columns: tuple[str, ...], events: list[dict[str, Any]]) -> str:
    """Der Bericht als Text: Vorspann (Titel und erfundene Nutzerzeile wie bei Coinbase) oder keiner, dann Kopfzeile und Vorgaenge."""
    newline = rng.choice(("\n", "\r\n"))
    user = f"User,Erfundene Person {rng.randrange(10, 100)},{_hex(rng, 8)}-{_hex(rng, 4)}-{_hex(rng, 4)}-{_hex(rng, 4)}-{_hex(rng, 12)}"
    preamble = rng.choice(([], ["", "Transactions", user], ["Transactions", user], ["Transactions" + "," * (len(columns) - 1)]))
    buffer = io.StringIO()
    buffer.write("".join(line + newline for line in preamble))
    writer = csv.writer(buffer, lineterminator=newline)
    writer.writerow(columns)
    for event in events:
        writer.writerow([event["cells"][name] for name in columns])
    return buffer.getvalue()


def _cash_moves(event: dict[str, Any]) -> bool:
    return isinstance(event["cash"], Decimal) and event["cash"] != 0 and event["stamp_ok"]


def _generate_cash(seed: int) -> dict[str, Any]:
    """Nur das EUR-Wallet: Ein- und Auszahlungen, Verkaeufe gegen Euro, Kaeufe aus dem Wallet. Kartenkaeufe, EURC, Tausch, Transfers
    und Rewards beruehren es nicht und werden uebergangen; ein unlesbarer Betrag oder Zeitpunkt wird ein Hinweis."""
    rng = random.Random(seed)
    events = _events(rng, CASH_WEIGHTS, grouping=True)
    if not any(_cash_moves(event) for event in events):   # mindestens eine Bewegung: sonst ist der Bericht kein Beleg des Wallets
        events.append(_event(rng, "deposit_eur", events[-1]["moment"] + timedelta(days=1), grouping=True, special=False))
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, event in enumerate(events, 1):
        cash = event["cash"]
        if cash is None or (isinstance(cash, Decimal) and cash == 0):
            continue
        if cash == "invalid":
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        if not event["stamp_ok"]:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        cells = event["cells"]
        candidates.append({"source_row_ordinal": ordinal, "local_date": event["moment"].astimezone(BERLIN).date().isoformat(),
                           "kind": "deposit" if cash > 0 else "withdrawal", "amount_decimal": _plain(abs(cash)), "balance_after_decimal": None,
                           "text": f"{cells['Transaction Type']} {cells['Asset']}".strip()})
    days = sorted(row["local_date"] for row in candidates)
    expected = {"candidates": candidates, "diagnostics": diagnostics,
                "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}
    text = ("﻿" if rng.random() < 0.3 else "") + _report(rng, HEADER, events)
    return {"file_name": f"coinbase-eur-erfunden-{seed}.csv", "content": text.encode("utf-8"), "expected": expected}


def _crypto_row(event: dict[str, Any]) -> bool:
    return isinstance(event["crypto"], dict) and event["crypto"]["quantity"] is not None and event["stamp_ok"]


def _generate_crypto(seed: int) -> dict[str, Any]:
    """Krypto-Bewegungen: Kauf und Verkauf gegen Euro (Kurswert und Gebuehr), Handel gegen Stablecoins und Convert (Tausch),
    Staking-Umbuchungen (intern), Transfers mit Adresse; Euro-Bewegungen, Rewards, unbekannte Arten und unlesbare Zeilen mit Grund."""
    rng = random.Random(seed)
    events = _events(rng, CRYPTO_WEIGHTS, grouping=True)
    if not any(_crypto_row(event) for event in events):
        events.append(_event(rng, "buy_card", events[-1]["moment"] + timedelta(days=1), grouping=True, special=False))
    file_name = f"coinbase-krypto-erfunden-{seed}.csv"
    rows: list[dict[str, Any]] = []
    reasons: Counter[str] = Counter()
    for ordinal, event in enumerate(events, 1):
        effect = event["crypto"]
        if isinstance(effect, str):
            reasons[effect] += 1; continue
        if not _crypto_row(event):
            reasons["crypto_unreadable_row"] += 1; continue
        optional = lambda value: None if value is None else _plain(abs(value))
        row = {"profile": "crypto_row", "source": "coinbase", "file_name": file_name, "row_no": ordinal, "wallet": "main",
               "at_utc": event["moment"].strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": "UTC", "ticker": effect["ticker"], "kind": effect["kind"],
               "quantity": _plain(effect["quantity"]), "fee_quantity": None, "eur": optional(effect["eur"]), "eur_fee": optional(effect["eur_fee"]),
               "transaction_id": event["cells"]["ID"], "hash": "", "address": effect["address"], "group": "", "quote": effect["quote"]}
        row["row_key"] = crypto_row_key(row)
        rows.append(row)
    expected = {"status": "multi", "candidates": rows, "row_reasons": dict(reasons)}
    # Textbereich: der Kern gibt dem Leser den Text ohne BOM.
    return {"file_name": file_name, "content": _report(rng, HEADER, events), "expected": expected}


def _reward_valid(event: dict[str, Any]) -> bool:
    return event["reward"] is not None and event["reward"]["valid"] and event["stamp_ok"]


def _generate_reward(seed: int) -> dict[str, Any]:
    """Rewards: je Zeile Zellen, Kennung, Merkmale fuer doppelte Zeilen und Art; ein Reward mit Coin, Menge, Zeit (UTC), Gebuehr und
    Bewertung - Gesamtbetrag, sonst Stueckpreis, sonst keine. Unvollstaendige Rewards sind "invalid", alles andere "other"."""
    rng = random.Random(seed)
    events = _events(rng, REWARD_WEIGHTS, grouping=False, low=2, high=20)
    if not any(_reward_valid(event) for event in events):
        events.append(_event(rng, "reward", events[-1]["moment"] + timedelta(days=1), grouping=False, special=False))
    columns = rng.choice((HEADER, SHORT_HEADER))
    rows: list[dict[str, Any]] = []
    for event in events:
        cells, info = event["cells"], event["reward"]
        number = lambda value, cell: _norm(cell) if value is None else _plain(abs(value))
        row: dict[str, Any] = {"cells": [cells[name] for name in columns], "row_id": cells["ID"],
                               "signature": [_norm(cells["Timestamp"]), _norm(cells["Transaction Type"]), "", _norm(cells["Asset"]),
                                             number(event["quantity_value"], cells["Quantity Transacted"]), number(event["fee_value"], cells[FEES]), ""]}
        if info is None:
            row["kind"] = "other"
        elif not _reward_valid(event):
            row["kind"] = "invalid"
        else:
            row.update(kind="reward", asset=info["asset"], quantity=info["quantity"], local_date=event["moment"].date().isoformat(),
                       local_time=event["moment"].strftime("%H:%M:%S"), fee=info["fee"], account="Coinbase", valuation=info["valuation"])
        rows.append(row)
    expected = {"time_zone": "UTC", "fee_role": "monetary", "rows": rows}
    text = ("﻿" if rng.random() < 0.3 else "") + _report(rng, columns, events)
    return {"file_name": f"coinbase-rewards-erfunden-{seed}.csv", "content": text.encode("utf-8"), "expected": expected}


GENERATORS = {"coinbase_eur_v1": _generate_cash, "coinbase_crypto_v1": _generate_crypto, "coinbase_transactions_csv_v1": _generate_reward}
