"""Erzeuger erfundener Bison-Exporte fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Vorgaenge: Ein- und Auszahlungen in Euro, Kauf und Verkauf mit und ohne Gebuehr,
Staking-Rewards (mit und ohne Marktpreis), Ein- und Auszahlungen von Coins und Umbuchungen. Aus ihnen baut der Erzeuger den
Transaktionsexport im Format von Bison (Semikolon mit Leerzeichen, Zeiten in UTC, neueste oder aelteste Zeile zuerst, mit oder ohne
BOM) und - unabhaengig von den Lesern - das erwartete Ergebnis je Leser: das Euro-Guthaben (cash), die Coins (crypto) und die
Rewards (reward). Jede Zeile traegt schon beim Erfinden, was aus ihr werden soll.

Der Erzeuger ruft keinen Leser auf, sonst bestaetigte der Leser nur sich selbst. Aus dem SDK nutzt er nur die Zeilenkennung der
Krypto-Zeilen (crypto_row_key) und die Schreibweise der Reward-Merkmale (reward_norm), weil das Ergebnis genau sie verlangt. Gleicher
Startwert, gleicher Beleg. Alle Werte sind erfunden: Kennungen, Betraege, Kurse, Zeiten. Die Tage liegen in 2021-2024.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
import random
from typing import Any, Callable
from zoneinfo import ZoneInfo

from portelyra_reader_sdk_v1 import crypto_row_key, reward_norm

UTC = timezone.utc
BERLIN = ZoneInfo("Europe/Berlin")
ZERO, CENT, SATOSHI = Decimal("0"), Decimal("0.01"), Decimal("0.00000001")
START = datetime(2021, 1, 1, tzinfo=UTC)
LAST_START = datetime(2024, 9, 1, tzinfo=UTC)   # bis zu 30 Vorgaenge mit hoechstens drei Tagen Abstand: alles bleibt in 2024
HEADER = ("Transaction ID", "Transaction type", "Currency", "Asset", "Eur (amount)", "Asset (amount)", "Asset (market price)", "Fee",
          "Date (UTC - Coordinated Universal Time)")
COLUMNS = ("id", "type", "currency", "asset", "eur", "quantity", "price", "fee", "date")
# Coins: Schreibweise im Export, Kurs in Cent von/bis, ob Bison Staking anbietet (erfundene Auswahl).
COINS = {
    "Btc": (1_800_000, 6_500_000, False), "Eth": (90_000, 420_000, True), "Ltc": (4_000, 30_000, False), "Xrp": (30, 250, False),
    "Link": (500, 5_000, False), "Ada": (20, 250, True), "Dot": (300, 4_500, True), "Sol": (800, 22_000, True), "Avax": (900, 12_000, False),
    "Uni": (300, 4_000, False), "Bch": (9_000, 60_000, False), "Pol": (20, 250, True),
}
STAKING = tuple(name for name, coin in COINS.items() if coin[2])
CRYPTO_KINDS = frozenset({"trade", "move"})


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _euros(rng: random.Random, low_cents: int, high_cents: int) -> Decimal:
    return Decimal(rng.randrange(low_cents, high_cents + 1)) / 100


def _ident(rng: random.Random) -> str:
    """Kennung in UUID-Form, erfunden."""
    return f"{rng.getrandbits(32):08x}-{rng.getrandbits(16):04x}-4{rng.getrandbits(12):03x}-{rng.getrandbits(16):04x}-{rng.getrandbits(48):012x}"


class _Export:
    """Erfundener Export: Zeilen in zeitlicher Folge samt dem, was jeder Leser aus ihnen machen soll."""

    def __init__(self, rng: random.Random, focus: str):
        self.rng, self.focus, self.specials = rng, focus, True
        self.rows: list[dict[str, Any]] = []
        self.holdings: dict[str, Decimal] = {name: (_euros(rng, 1_000, 200_000) / self.price(name)).quantize(SATOSHI)
                                             for name in rng.sample(sorted(COINS), rng.randrange(0, 4))}
        self.zero_fee = rng.choice(("0.0000000000", "0"))

    def price(self, name: str) -> Decimal:
        return _euros(self.rng, COINS[name][0], COINS[name][1])

    def quantity_text(self, value: Decimal) -> str:
        """Bison schreibt Mengen mal knapp, mal mit festen Nachkommastellen."""
        places = self.rng.choice((None, 8, 10))
        return _plain(value) if places is None else f"{value:.{places}f}"

    def row(self, at: datetime, kind: str, currency: str, asset: str, eur: Decimal | None, quantity: Decimal | None,
            price: Decimal | None, fee: Decimal, *, cash: str | None, crypto: str, reward: bool = False) -> dict[str, Any]:
        rng = self.rng
        row: dict[str, Any] = {
            "id": _ident(rng), "type": kind, "currency": currency, "asset": asset, "eur": "" if eur is None else f"{eur:.2f}",
            "quantity": "" if quantity is None else self.quantity_text(quantity),
            "price": "" if price is None else rng.choice((_plain(price), f"{price:.2f}")),
            "fee": self.zero_fee if fee == 0 else rng.choice((f"{fee:.10f}", _plain(fee))), "date": at.strftime("%Y-%m-%d %H:%M:%S"),
            "_at": at, "_eur": eur, "_quantity": quantity, "_price": price, "_fee": fee, "_cash": cash, "_crypto": crypto, "_reward": reward,
        }
        if self.specials:
            chance = rng.random()
            if self.focus == "cash" and cash:
                if chance < 0.04:       # Euro-Betrag fehlt: Hinweis statt Bewegung
                    row["eur"], row["_eur"] = "", None
                elif chance < 0.09:     # unlesbarer Zeitpunkt (30. Februar)
                    row["date"], row["_at"] = f"{at.year}-02-30 {at:%H:%M:%S}", None
                elif chance < 0.11:     # Zeile ohne Euro-Bewegung: wird uebergangen
                    row["eur"], row["_eur"], row["fee"], row["_fee"] = "0.00", ZERO, self.zero_fee, ZERO
            elif self.focus == "crypto" and crypto in CRYPTO_KINDS:
                if chance < 0.04:       # unlesbarer Zeitpunkt: Zeile mit Grund
                    row["date"], row["_at"] = f"{at.year}-02-30 {at:%H:%M:%S}", None
                elif chance < 0.08:     # Menge fehlt: ebenso
                    row["quantity"], row["_quantity"] = "", None
        self.rows.append(row)
        return row

    def text(self, line_end: str, newest_first: bool) -> str:
        rows = self.rows[::-1] if newest_first else self.rows
        return line_end.join(["; ".join(HEADER)] + ["; ".join(row[column] for column in COLUMNS) for row in rows]) + line_end

    def ordered(self, newest_first: bool) -> list[dict[str, Any]]:
        return self.rows[::-1] if newest_first else self.rows


# ---------------------------------------------------------------- Vorgaenge
def _eur_deposit(export: _Export, at: datetime) -> None:
    export.row(at, "Deposit", "Eur", "", _euros(export.rng, 1_000, 500_000), None, None, ZERO, cash="deposit", crypto="crypto_fiat")


def _eur_withdraw(export: _Export, at: datetime) -> None:
    export.row(at, "Withdraw", "Eur", "", _euros(export.rng, 1_000, 300_000), None, None, ZERO, cash="withdraw", crypto="crypto_fiat")


def _fee(export: _Export, amount: Decimal) -> Decimal:
    """Meist ohne Gebuehr (Spread), manchmal mit einer in Euro."""
    return (amount * export.rng.choice((Decimal("0.0075"), Decimal("0.01")))).quantize(CENT) if export.rng.random() < 0.35 else ZERO


def _buy(export: _Export, at: datetime) -> None:
    rng = export.rng
    name = rng.choice(sorted(COINS))
    price, amount = export.price(name), _euros(rng, 1_000, 300_000)
    quantity = max(SATOSHI, (amount / price).quantize(SATOSHI))
    export.holdings[name] = export.holdings.get(name, ZERO) + quantity
    export.row(at, "Buy", "Eur", name, amount, quantity, price, _fee(export, amount), cash="buy", crypto="trade")


def _sell(export: _Export, at: datetime) -> None:
    rng = export.rng
    held = [name for name in sorted(export.holdings) if export.holdings[name] >= 1000 * SATOSHI]
    if not held:
        return _buy(export, at)
    name = rng.choice(held)
    quantity = max(SATOSHI, (export.holdings[name] * Decimal(rng.randrange(5, 101)) / 100).quantize(SATOSHI, rounding=ROUND_DOWN))
    price = export.price(name)
    amount = (quantity * price).quantize(CENT)
    fee = _fee(export, amount)
    if amount < 1 or amount <= fee:
        return _buy(export, at)
    export.holdings[name] -= quantity
    export.row(at, "Sell", "Eur", name, amount, quantity, price, fee, cash="sell", crypto="trade")


def _staking(export: _Export, at: datetime) -> None:
    """Staking-Reward: Marktpreis und Euro-Wert meist dabei, Waehrung mal genannt, mal leer."""
    rng = export.rng
    name = rng.choice(STAKING)
    price = export.price(name)
    quantity = max(SATOSHI, (_euros(rng, 1, 2_000) / price).quantize(SATOSHI))
    fee = ZERO
    if export.specials and export.focus == "reward":
        chance = rng.random()
        if chance < 0.08:
            quantity = ZERO          # ohne Menge: der Leser nennt die Zeile ungueltig
        elif chance < 0.18:
            price = None             # ohne Marktpreis: keine Bewertung
        elif chance < 0.24:
            fee = _euros(rng, 1, 50)  # mit Gebuehr in Euro
    eur = None if price is None else (quantity * price).quantize(CENT)
    export.holdings[name] = export.holdings.get(name, ZERO) + quantity
    export.row(at, "Staking Reward", rng.choice(("EUR", "Eur", "")), name, eur, quantity, price, fee, cash=None, crypto="crypto_reward",
               reward=True)


def _coin_deposit(export: _Export, at: datetime) -> None:
    rng = export.rng
    name = rng.choice(sorted(COINS))
    quantity = max(SATOSHI, (_euros(rng, 1_000, 300_000) / export.price(name)).quantize(SATOSHI))
    export.holdings[name] = export.holdings.get(name, ZERO) + quantity
    export.row(at, "Deposit", "", name, None, quantity, None, ZERO, cash=None, crypto="move")


def _coin_withdraw(export: _Export, at: datetime) -> None:
    """Auszahlung eines Coins: Gebuehr in Coins, auch ohne Gebuehr."""
    rng = export.rng
    held = [name for name in sorted(export.holdings) if export.holdings[name] >= 1000 * SATOSHI]
    if not held:
        return _coin_deposit(export, at)
    name = rng.choice(held)
    quantity = max(SATOSHI, (export.holdings[name] * Decimal(rng.randrange(5, 91)) / 100).quantize(SATOSHI, rounding=ROUND_DOWN))
    fee = max(SATOSHI, (quantity * Decimal("0.001")).quantize(SATOSHI)) if rng.random() < 0.6 else ZERO
    export.holdings[name] -= quantity + fee
    export.row(at, "Withdraw", "", name, None, quantity, None, fee, cash=None, crypto="move")


def _transfer(export: _Export, at: datetime) -> None:
    """Umbuchung, die kein Leser bucht: fuer den Krypto-Leser nicht unterstuetzt, mit Grund."""
    rng = export.rng
    name = rng.choice(STAKING)
    quantity = max(SATOSHI, (_euros(rng, 100, 50_000) / export.price(name)).quantize(SATOSHI))
    export.row(at, "Transfer", "", name, None, quantity, None, ZERO, cash=None, crypto="crypto_unsupported")


EVENTS: dict[str, Callable[[_Export, datetime], None]] = {
    "eur_deposit": _eur_deposit, "eur_withdraw": _eur_withdraw, "buy": _buy, "sell": _sell, "staking": _staking,
    "coin_deposit": _coin_deposit, "coin_withdraw": _coin_withdraw, "transfer": _transfer,
}
# Ein- und Auszahlungen von Coins nur ausserhalb des Cash-Lesers: was Bison dort unter "Eur (amount)" schreibt, ist nicht belegt.
WEIGHTS = {
    "cash": {"eur_deposit": 3, "eur_withdraw": 2, "buy": 4, "sell": 2.5, "staking": 1.5, "coin_deposit": 0, "coin_withdraw": 0, "transfer": 0.3},
    "crypto": {"eur_deposit": 1.5, "eur_withdraw": 1, "buy": 3, "sell": 2, "staking": 1.5, "coin_deposit": 1, "coin_withdraw": 1, "transfer": 0.3},
    "reward": {"eur_deposit": 1, "eur_withdraw": 0.5, "buy": 1.5, "sell": 1, "staking": 5, "coin_deposit": 0.5, "coin_withdraw": 0.5,
               "transfer": 0.2},
}


# ---------------------------------------------------------------- Erwartung je Leser (aus den erfundenen Werten, nicht aus dem Text)
def _expected_cash(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Euro-Guthaben: Einzahlung und Verkauf (Kurswert abzueglich Gebuehr) schreiben gut, Auszahlung und Kauf (Kurswert und Gebuehr)
    belasten; kein Saldo im Export."""
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for ordinal, row in enumerate(rows, 1):
        if not row["_cash"]:
            continue
        if row["_eur"] is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        eur, fee = row["_eur"], row["_fee"]
        cash = {"deposit": eur, "withdraw": -eur, "buy": -(eur + fee), "sell": eur - fee}[row["_cash"]]
        if cash == 0:
            continue
        if row["_at"] is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        candidates.append({"source_row_ordinal": ordinal, "local_date": row["_at"].astimezone(BERLIN).date().isoformat(),
                           "kind": "deposit" if cash > 0 else "withdrawal", "amount_decimal": _plain(abs(cash)),
                           "balance_after_decimal": None, "text": f"{row['type']} {row['asset']}".strip()})
    if not candidates:
        return {}
    days = sorted(row["local_date"] for row in candidates)
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}}


def _expected_crypto(rows: list[dict[str, Any]], file_name: str) -> dict[str, Any]:
    """Kauf und Verkauf mit Kurswert und Gebuehr in Euro, Ein- und Auszahlung von Coins mit Gebuehr in Coins; der Rest mit Grund."""
    candidates: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    for number, row in enumerate(rows, 1):
        kind = row["_crypto"]
        if kind in CRYPTO_KINDS and (row["_at"] is None or row["_quantity"] is None):
            kind = "crypto_unreadable_row"
        if kind not in CRYPTO_KINDS:
            reasons[kind] = reasons.get(kind, 0) + 1; continue
        outgoing = row["type"] in ("Sell", "Withdraw")
        quantity = -row["_quantity"] if outgoing else row["_quantity"]
        trade = kind == "trade"
        item = {"profile": "crypto_row", "source": "bison", "file_name": file_name, "row_no": number, "wallet": "main",
                "at_utc": row["_at"].strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": "UTC", "ticker": row["asset"].upper(), "kind": kind,
                "quantity": _plain(quantity),
                "fee_quantity": _plain(row["_fee"]) if row["type"] == "Withdraw" else None,
                "eur": _plain(row["_eur"]) if trade and row["_eur"] is not None else None,
                "eur_fee": _plain(row["_fee"]) if trade else None,
                "transaction_id": row["id"], "hash": "", "address": "", "group": "", "quote": ""}
        item["row_key"] = crypto_row_key(item)
        candidates.append(item)
    return {"status": "multi", "candidates": candidates, "row_reasons": reasons} if candidates else {}


def _expected_reward(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Je Zeile Zellen (mit dem Leerzeichen nach dem Semikolon), Kennung, sieben Merkmale fuer doppelte Zeilen; ein Staking-Reward
    mit Menge, Zeit, Gebuehr in Euro, Konto Bison und dem Marktpreis des Coins als Stueckpreis in Euro."""
    out: list[dict[str, Any]] = []
    number = lambda value: "" if value is None else _plain(abs(value))
    for row in rows:
        cells = [row[column] for column in COLUMNS]
        item: dict[str, Any] = {
            "cells": cells[:1] + [" " + cell for cell in cells[1:]], "row_id": row["id"],
            "signature": [reward_norm(row["date"]), reward_norm(row["type"]), "", reward_norm(row["asset"]), number(row["_quantity"]),
                          number(row["_fee"]), ""]}
        if not row["_reward"]:
            item["kind"] = "other"
        elif row["_at"] is None or not row["_quantity"] or not row["asset"]:
            item["kind"] = "invalid"
        else:
            price = row["_price"]
            valuation = ({"source_value_mode": "unit_price", "price_currency": "EUR", "source_unit_price_decimal": _plain(price),
                          "source_fiat_total_decimal": None} if price else
                         {"source_value_mode": "none", "price_currency": "EUR", "source_unit_price_decimal": None, "source_fiat_total_decimal": None})
            item.update(kind="reward", asset=row["asset"].upper(), quantity=_plain(row["_quantity"]), local_date=row["_at"].date().isoformat(),
                        local_time=row["_at"].strftime("%H:%M:%S"), fee=None if row["_fee"] == 0 else _plain(row["_fee"]), account="Bison",
                        valuation=valuation)
        out.append(item)
    if not any(item["kind"] == "reward" for item in out):
        return {}
    return {"time_zone": "UTC", "fee_role": "monetary", "rows": out}


def _generate(focus: str, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    export = _Export(rng, focus)
    names = list(EVENTS)
    weights = [WEIGHTS[focus][name] for name in names]
    moment = START + timedelta(seconds=rng.randrange(0, int((LAST_START - START).total_seconds())))
    for _ in range(rng.randrange(3, 28)):
        moment += timedelta(seconds=rng.randrange(300, 3 * 86_400))
        EVENTS[rng.choices(names, weights)[0]](export, moment)
    newest_first = rng.random() < 0.5
    file_name = f"bison-transactions-erfunden-{seed}.csv"
    build = {"cash": _expected_cash, "crypto": lambda rows: _expected_crypto(rows, file_name), "reward": _expected_reward}[focus]
    fallback = {"cash": _eur_deposit, "crypto": _buy, "reward": _staking}[focus]
    export.specials = False
    expected = build(export.ordered(newest_first))
    while not expected:   # mindestens ein lesbarer Vorgang: sonst ist der Export kein Beleg dieses Lesers
        moment += timedelta(hours=1)
        fallback(export, moment)
        expected = build(export.ordered(newest_first))
    text = export.text(rng.choice(("\n", "\r\n")), newest_first)
    if focus == "crypto":
        return {"file_name": file_name, "content": text, "expected": expected}
    return {"file_name": file_name, "content": (("﻿" if rng.random() < 0.3 else "") + text).encode("utf-8"), "expected": expected}


# ---------------------------------------------------------------- Verrechnungskonto: EUWAX Monatsuebersicht (#550, rc.434)
_SETTLEMENT_PARTIES = ("Erika Mustermann", "EUWAX Aktiengesellschaft", "Max Beispiel")
_SETTLEMENT_DESCRIPTIONS = ("Umbuchung", "Einzahlung", "Auszahlung", "Gutschrift aus Verkauf", "Belastung aus Kauf")


def _german_money(cents: int) -> str:
    sign, cents = ("-" if cents < 0 else ""), abs(cents)
    euros = f"{cents // 100:,}".replace(",", ".")
    return f"{sign}{euros},{cents % 100:02d}€"


def _generate_settlement(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    month = rng.randrange(0, 34)                                          # Januar 2024 bis Oktober 2026
    start = datetime(2024 + month // 12, month % 12 + 1, 1).date()
    end = (datetime(2024 + (month + 1) // 12, (month + 1) % 12 + 1, 1) - timedelta(days=1)).date()
    opening = rng.randrange(0, 2_500_000)
    count = 0 if rng.random() < 0.3 else rng.randrange(1, 18)
    days = sorted(start + timedelta(days=rng.randrange((end - start).days + 1)) for _ in range(count))
    bookings, balance = [], opening
    for day in days:
        cents = rng.randrange(100, 400_000) * (1 if rng.random() < 0.45 else -1)
        if balance + cents < 0:
            cents = abs(cents)
        balance += cents
        bookings.append((day, rng.choice(_SETTLEMENT_PARTIES), rng.choice(_SETTLEMENT_DESCRIPTIONS), cents))
    closing = balance
    dmy = lambda value: value.strftime("%d.%m.%Y")
    lines = [f"{rng.choice(_SETTLEMENT_PARTIES)}                       IBAN: DE00 1000 0000 {rng.randrange(10**9, 10**10)}",
             f"Musterweg {rng.randrange(1, 99)}                        BIC: DEUTDESSXXX",
             f"{rng.randrange(10000, 99999)} Musterstadt              Eröffnungsdatum: {dmy(start - timedelta(days=rng.randrange(1, 400)))}",
             f"                                        Rechnungsdatum: {dmy(end + timedelta(days=1))}",
             "Monatsübersicht                         Eröffnungsbilanz                       Abschlusssaldo",
             f"{dmy(start)} - {dmy(end)}                      {_german_money(opening)}                         {_german_money(closing)}",
             "Transaktion                    Buchungsdatum          Valutadatum                          Wert"]
    for index, (day, party, description, cents) in enumerate(bookings, 1):
        lines += [f"{party}                  {dmy(day)}             {dmy(day)}                        {_german_money(cents)}",
                  f"Referenz: P{rng.randrange(10**7, 10**8)}", f"Beschreibung: {description}",
                  f"IBAN: DE00 2000 0000 {rng.randrange(10**9, 10**10)}| BIC: TESTDEFFXXX"]
        if index % 8 == 0 and index < len(bookings):                     # Seitenwechsel: pdftotext -nopgbrk reiht die Seiten aneinander
            lines += ["", "Transaktion                    Buchungsdatum          Valutadatum                          Wert"]
    lines += ["Sehr geehrte Kundin, sehr geehrter Kunde, bitte prüfen Sie die Buchungen, Berechnungen und den",
              "Abschlusssaldo in der beiliegenden Monatsübersicht."]
    candidates = [{"source_row_ordinal": ordinal, "local_date": day.isoformat(), "kind": "deposit" if cents > 0 else "withdrawal",
                   "amount_decimal": _plain(Decimal(abs(cents)) / 100), "balance_after_decimal": None, "text": f"{party}: {description}"}
                  for ordinal, (day, party, description, cents) in enumerate(bookings, 1)]
    summary = {"opening_balance_decimal": _plain(Decimal(opening) / 100), "closing_balance_decimal": _plain(Decimal(closing) / 100),
               "period_from": start.isoformat(), "period_to": end.isoformat(), "closing_as_of_date": end.isoformat()}
    content = "\n".join(lines) + "\n"
    return {"file_name": f"bison-monatsuebersicht-erfunden-{seed}.txt", "content": content.encode("utf-8"),
            "expected": {"candidates": candidates, "diagnostics": [], "summary": summary}}


GENERATORS = {
    "bison_settlement_v1": _generate_settlement,
    "bison_eur_v1": lambda seed: _generate("cash", seed),
    "bison_crypto_v1": lambda seed: _generate("crypto", seed),
    "bison_transactions_csv_v1": lambda seed: _generate("reward", seed),
}
