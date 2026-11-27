"""Erzeuger erfundener Kraken-Ledger-Exporte fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Vorgaenge: Ein- und Auszahlungen in Euro und in Coins, Kauf und Verkauf ueber "trade" oder
"spend"/"receive", Tausch zwischen Coins, Umbuchungen nach Earn und zurueck, Rewards (auch auf gehaltene Euro), Korrekturen und
Umstellungen. Aus ihnen baut der Erzeuger den Ledger-Export im Format von Kraken (aktuelle Fassung mit Wallet und USD-Werten, aeltere
ohne beides, schlichte ohne Anfuehrungszeichen) und - unabhaengig von den Lesern - das erwartete Ergebnis je Leser: das Euro-Guthaben
(cash), die Coins (crypto) und die Rewards (reward). Jede Zeile traegt schon beim Erfinden, was aus ihr werden soll.

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
ZERO, ONE, CENT, SATOSHI = Decimal("0"), Decimal("1"), Decimal("0.01"), Decimal("0.00000001")
USD_RATE = Decimal("1.08")
START = datetime(2021, 1, 1, tzinfo=UTC)
LAST_START = datetime(2024, 9, 1, tzinfo=UTC)   # bis zu 30 Vorgaenge mit hoechstens drei Tagen Abstand: alles bleibt in 2024
SPOT = "spot / main"
EARN_WALLETS = ("earn / flexible", "earn / bonded")

# Fassungen des Exports: Spalten und ob Texte in Anfuehrungszeichen stehen.
LAYOUTS = {
    "current": (("txid", "refid", "time", "type", "subtype", "aclass", "subclass", "asset", "wallet", "amount", "fee", "balance",
                 "amountusd", "feeusd", "balanceusd", "feecurrency"), True),
    "older": (("txid", "refid", "time", "type", "subtype", "aclass", "asset", "amount", "fee", "balance"), True),
    "plain": (("txid", "refid", "time", "type", "subtype", "aclass", "asset", "amount", "fee", "amountusd", "feeusd", "balance"), False),
}
NUMERIC = frozenset({"amount", "fee", "balance", "amountusd", "feeusd", "balanceusd"})
# Der Reward-Leser braucht die USD-Werte, der Cash- und der Krypto-Leser nicht.
FOCUS_LAYOUTS = {"cash": ("current", "older"), "crypto": ("current", "older"), "reward": ("current", "plain")}

# Coins: Kuerzel im Export (alte Schreibweise, neue Schreibweise), Kuerzel im Staking der alten Fassung, Kurs in Cent von/bis.
COINS = {
    "BTC": ("XXBT", "XBT", "XBT.M", 1_800_000, 6_500_000),
    "ETH": ("XETH", "ETH", "ETH2.S", 90_000, 420_000),
    "ADA": ("ADA", "ADA", "ADA.S", 20, 250),
    "DOT": ("DOT", "DOT", "DOT.S", 300, 4_500),
    "SOL": ("SOL", "SOL", "SOL.S", 800, 22_000),
    "DOGE": ("XXDG", "XDG", None, 5, 60),
    "LTC": ("XLTC", "LTC", None, 4_000, 30_000),
    "USDC": ("USDC", "USDC", "USDC.M", 85, 100),
}
EARN_TICKERS = tuple(ticker for ticker, coin in COINS.items() if coin[2])
# Ticker je Kuerzel, wie ihn der Kern erwartet (eigene Tabelle, nicht aus dem Leser).
TICKERS = {"XXBT": "BTC", "XBT": "BTC", "XBT.M": "BTC", "XETH": "ETH", "ETH": "ETH", "ETH2.S": "ETH", "ADA": "ADA", "ADA.S": "ADA",
           "DOT": "DOT", "DOT.S": "DOT", "SOL": "SOL", "SOL.S": "SOL", "XXDG": "DOGE", "XDG": "DOGE", "XLTC": "LTC", "LTC": "LTC",
           "USDC": "USDC", "USDC.M": "USDC", "EUR": "EUR", "ZEUR": "EUR", "EUR.HOLD": "EUR"}
# Arten einer Krypto-Zeile, die der Leser liefert; alles andere ist ein gezaehlter Grund.
CRYPTO_KINDS = frozenset({"trade_eur", "trade_coin", "internal", "move"})


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _ident(rng: random.Random, first: str) -> str:
    """Kennung in der Form von Kraken (LABCDE-FGHIJ-KLMNOP), erfunden."""
    body = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567") for _ in range(16))
    return f"{first}{body[:5]}-{body[5:10]}-{body[10:]}"


def _euros(rng: random.Random, low_cents: int, high_cents: int) -> Decimal:
    return Decimal(rng.randrange(low_cents, high_cents + 1)) / 100


class _Ledger:
    """Erfundener Ledger: Zeilen in Exportreihenfolge (aufsteigend nach Zeit) samt dem, was jeder Leser aus ihnen machen soll."""

    def __init__(self, rng: random.Random, focus: str):
        self.rng, self.focus, self.specials = rng, focus, True
        self.layout = rng.choice(FOCUS_LAYOUTS[focus])
        self.header, self.quoted = LAYOUTS[self.layout]
        self.wallets = "wallet" in self.header
        newer = self.layout == "current"
        self.eur = "EUR" if newer else rng.choice(("ZEUR", "ZEUR", "EUR"))
        self.codes = {ticker: coin[1] if newer else coin[0] for ticker, coin in COINS.items()}
        self.coin_places = 8 if self.layout == "plain" else 10
        self.usd_places = 2 if self.layout == "plain" else 4
        self.rows: list[dict[str, Any]] = []
        self.balances: dict[tuple[str, str], Decimal] = {}
        # Ein Export beginnt oft mitten in der Geschichte: Anfangsbestaende ohne eigene Zeile.
        if rng.random() < 0.5:
            self.balances[(self.eur, SPOT)] = _euros(rng, 0, 300_000)
        for ticker in rng.sample(sorted(COINS), rng.randrange(0, 4)):
            self.balances[(self.codes[ticker], SPOT)] = (_euros(rng, 1_000, 200_000) / self.price(ticker)).quantize(SATOSHI)

    def price(self, ticker: str) -> Decimal:
        coin = COINS[ticker]
        return _euros(self.rng, coin[3], coin[4])

    def balance(self, asset: str, wallet: str = SPOT) -> Decimal:
        return self.balances.get((asset, wallet), ZERO)

    def row(self, at: datetime, kind: str, subtype: str, asset: str, amount: Decimal, fee: Decimal, refid: str, crypto: str,
            price: Decimal, wallet: str = SPOT, reward: bool = False) -> None:
        rng = self.rng
        if reward and self.specials and self.focus == "reward" and rng.random() < 0.1:
            amount = fee = ZERO   # Reward ohne Menge: Kraken fuehrt ihn, der Leser nennt ihn ungueltig
        balance = self.balance(asset, wallet) + amount - fee
        self.balances[(asset, wallet)] = balance
        euro = asset in ("EUR", "ZEUR", "EUR.HOLD")
        places = 4 if euro else self.coin_places
        usd_unit = price * USD_RATE
        usd, feeusd = (amount * usd_unit).quantize(Decimal(1).scaleb(-self.usd_places)), (fee * usd_unit).quantize(Decimal(1).scaleb(-self.usd_places))
        if reward and self.specials and self.focus == "reward" and rng.random() < 0.05:
            usd = ZERO   # ohne USD-Wert: keine Bewertung
        row: dict[str, Any] = {
            "txid": _ident(rng, "L"), "refid": refid, "time": at.strftime("%Y-%m-%d %H:%M:%S"), "type": kind, "subtype": subtype,
            "aclass": "currency", "subclass": "fiat" if euro else ("stable_coin" if asset.startswith("USDC") else "crypto"),
            "asset": asset, "wallet": wallet, "amount": f"{amount:.{places}f}", "fee": f"{fee:.{places}f}", "balance": f"{balance:.{places}f}",
            "amountusd": f"{usd:.{self.usd_places}f}", "feeusd": f"{feeusd:.{self.usd_places}f}",
            "balanceusd": f"{(balance * usd_unit).quantize(Decimal(1).scaleb(-self.usd_places)):.{self.usd_places}f}",
            "feecurrency": asset if fee else "",
            "_at": at, "_amount": amount, "_fee": fee, "_balance": balance, "_usd": usd, "_feeusd": feeusd,
            "_cash": asset == self.eur, "_crypto": crypto, "_reward": reward,
        }
        if self.specials:
            chance = rng.random()
            if self.focus == "cash" and row["_cash"]:
                if chance < 0.04:      # Betrag fehlt: Hinweis statt Bewegung
                    row["amount"], row["_amount"] = "", None
                elif chance < 0.08:    # Saldo fehlt: ebenso
                    row["balance"], row["_balance"] = "", None
                elif chance < 0.13:    # unlesbarer Zeitpunkt (30. Februar)
                    row["time"], row["_at"] = f"{at.year}-02-30 {at:%H:%M:%S}", None
            elif self.focus == "crypto" and crypto in CRYPTO_KINDS:
                if chance < 0.04:      # unlesbarer Zeitpunkt: Zeile mit Grund
                    row["time"], row["_at"] = f"{at.year}-02-30 {at:%H:%M:%S}", None
                elif chance < 0.08:    # Menge fehlt: ebenso
                    row["amount"], row["_amount"] = "", None
            elif self.focus == "reward" and chance < 0.15:   # Zeit mit Sekundenbruchteil
                row["time"] = f"{row['time']}.{rng.randrange(0, 10_000):04d}"
        self.rows.append(row)

    def text(self, line_end: str) -> str:
        quote = (lambda column, value: value if column in NUMERIC else f'"{value}"') if self.quoted else (lambda column, value: value)
        lines = [",".join(quote("", column) for column in self.header)]
        lines += [",".join(quote(column, row[column]) for column in self.header) for row in self.rows]
        return line_end.join(lines) + line_end


# ---------------------------------------------------------------- Vorgaenge
def _eur_deposit(ledger: _Ledger, at: datetime) -> None:
    rng = ledger.rng
    amount = _euros(rng, 1_000, 500_000)
    fee = _euros(rng, 9, 150) if rng.random() < 0.15 else ZERO
    ledger.row(at, "deposit", "", ledger.eur, amount, fee, _ident(rng, "Q"), "crypto_fiat", ONE)


def _eur_withdrawal(ledger: _Ledger, at: datetime) -> None:
    rng = ledger.rng
    fee = _euros(rng, 9, 250)
    available = ledger.balance(ledger.eur) - fee
    if available < 10:
        return _eur_deposit(ledger, at)
    amount = _euros(rng, 1_000, int(available * 100))
    ledger.row(at, "withdrawal", "", ledger.eur, -amount, fee, _ident(rng, "A"), "crypto_fiat", ONE)


def _eur_transfer(ledger: _Ledger, at: datetime) -> None:
    rng = ledger.rng
    ledger.row(at, "transfer", "spotfromfutures", ledger.eur, _euros(rng, 100, 100_000), ZERO, _ident(rng, "B"), "crypto_fiat", ONE)


def _eur_zero(ledger: _Ledger, at: datetime) -> None:
    """Korrektur ohne Betrag auf dem Euro-Konto: keine Bewegung, der Saldo zaehlt trotzdem."""
    ledger.row(at, "adjustment", "", ledger.eur, ZERO, ZERO, _ident(ledger.rng, "B"), "crypto_fiat", ONE)


def _legs(ledger: _Ledger, legs: list[tuple]) -> None:
    """Beide Seiten eines Vorgangs zur selben Zeit; Kraken schreibt sie in wechselnder Reihenfolge."""
    if ledger.rng.random() < 0.5:
        legs.reverse()
    for leg in legs:
        ledger.row(*leg)


def _buy(ledger: _Ledger, at: datetime, spend: bool = False) -> None:
    rng = ledger.rng
    rate = Decimal("0.015") if spend else rng.choice((ZERO, Decimal("0.0016"), Decimal("0.0026"), Decimal("0.004")))
    most = ((ledger.balance(ledger.eur) - CENT) / (1 + rate)).quantize(CENT, rounding=ROUND_DOWN)
    if most < 10:
        return _eur_deposit(ledger, at)
    ticker = rng.choice(sorted(COINS))
    price, cost = ledger.price(ticker), _euros(rng, 1_000, int(most * 100))
    quantity, fee, refid = max(SATOSHI, (cost / price).quantize(SATOSHI)), (cost * rate).quantize(CENT), _ident(rng, "T")
    _legs(ledger, [(at, "spend" if spend else "trade", "", ledger.eur, -cost, fee, refid, "trade_eur", ONE),
                   (at, "receive" if spend else "trade", "", ledger.codes[ticker], quantity, ZERO, refid, "trade_coin", price)])


def _held(ledger: _Ledger, tickers: tuple[str, ...] | list[str], wallet: str = SPOT) -> list[str]:
    return [ticker for ticker in sorted(tickers) if ledger.balance(ledger.codes[ticker], wallet) >= 1000 * SATOSHI]


def _part(ledger: _Ledger, ticker: str, wallet: str = SPOT) -> Decimal:
    held = ledger.balance(ledger.codes[ticker], wallet)
    return max(SATOSHI, (held * Decimal(ledger.rng.randrange(5, 96)) / 100).quantize(SATOSHI, rounding=ROUND_DOWN))


def _sell(ledger: _Ledger, at: datetime, receive: bool = False) -> None:
    rng = ledger.rng
    held = _held(ledger, list(COINS))
    if not held:
        return _buy(ledger, at, spend=receive)
    ticker = rng.choice(held)
    quantity, price = _part(ledger, ticker), ledger.price(ticker)
    proceeds = (quantity * price).quantize(CENT)
    if proceeds < 1:
        return _buy(ledger, at, spend=receive)
    fee, refid = (proceeds * (Decimal("0.015") if receive else Decimal("0.0026"))).quantize(CENT), _ident(rng, "T")
    _legs(ledger, [(at, "spend" if receive else "trade", "", ledger.codes[ticker], -quantity, ZERO, refid, "trade_coin", price),
                   (at, "receive" if receive else "trade", "", ledger.eur, proceeds, fee, refid, "trade_eur", ONE)])


def _swap(ledger: _Ledger, at: datetime) -> None:
    rng = ledger.rng
    held = _held(ledger, list(COINS))
    if not held:
        return _coin_deposit(ledger, at)
    source = rng.choice(held)
    target = rng.choice([ticker for ticker in sorted(COINS) if ticker != source])
    quantity, source_price, target_price = _part(ledger, source), ledger.price(source), ledger.price(target)
    received = (quantity * source_price / target_price).quantize(SATOSHI)
    if received < 10 * SATOSHI:
        return _coin_deposit(ledger, at)
    fee = (received * Decimal("0.0026")).quantize(SATOSHI) if rng.random() < 0.6 else ZERO   # Gebuehr in Coins
    refid = _ident(rng, "T")
    _legs(ledger, [(at, "trade", "", ledger.codes[source], -quantity, ZERO, refid, "trade_coin", source_price),
                   (at, "trade", "", ledger.codes[target], received, fee, refid, "trade_coin", target_price)])


def _coin_deposit(ledger: _Ledger, at: datetime) -> None:
    rng = ledger.rng
    ticker = rng.choice(sorted(COINS))
    price = ledger.price(ticker)
    quantity = max(SATOSHI, (_euros(rng, 1_000, 500_000) / price).quantize(SATOSHI))
    ledger.row(at, "deposit", "", ledger.codes[ticker], quantity, ZERO, _ident(rng, "F"), "move", price)


def _coin_withdrawal(ledger: _Ledger, at: datetime) -> None:
    """Kraken bucht die Gebuehr zusaetzlich zur Menge: 1,0 mit 0,001 Gebuehr verlassen das Konto mit 1,001."""
    rng = ledger.rng
    held = _held(ledger, list(COINS))
    if not held:
        return _coin_deposit(ledger, at)
    ticker = rng.choice(held)
    quantity = _part(ledger, ticker)
    fee = max(SATOSHI, (quantity * rng.choice((Decimal("0.0005"), Decimal("0.001"), Decimal("0.002")))).quantize(SATOSHI))
    if quantity + fee > ledger.balance(ledger.codes[ticker]):
        return _coin_deposit(ledger, at)
    ledger.row(at, "withdrawal", "", ledger.codes[ticker], -quantity, fee, _ident(rng, "F"), "move", ledger.price(ticker))


def _earn_move(ledger: _Ledger, at: datetime) -> None:
    """Umbuchung zwischen Spot und Earn: aktuelle Fassung als earn/allocation (zurueck deallocation), aeltere als transfer."""
    rng = ledger.rng
    refid = _ident(rng, "U")
    if not ledger.wallets:
        held = _held(ledger, EARN_TICKERS)
        if not held:
            return _coin_deposit(ledger, at)
        ticker = rng.choice(held)
        quantity, price = _part(ledger, ticker), ledger.price(ticker)
        _legs(ledger, [(at, "transfer", "spottostaking", ledger.codes[ticker], -quantity, ZERO, refid, "crypto_unsupported", price),
                       (at, "transfer", "stakingfromspot", COINS[ticker][2], quantity, ZERO, refid, "crypto_unsupported", price)])
        return
    back = [(ticker, wallet) for wallet in EARN_WALLETS for ticker in _held(ledger, EARN_TICKERS, wallet)]
    if back and rng.random() < 0.4:
        ticker, wallet = rng.choice(back)
        quantity, subtype, origin, destination = _part(ledger, ticker, wallet), rng.choice(("deallocation", "autodeallocation")), wallet, SPOT
    else:
        held = _held(ledger, EARN_TICKERS)
        if not held:
            return _coin_deposit(ledger, at)
        ticker = rng.choice(held)
        quantity, subtype, origin, destination = _part(ledger, ticker), rng.choice(("allocation", "autoallocation", "")), SPOT, rng.choice(EARN_WALLETS)
    price, code = ledger.price(ticker), ledger.codes[ticker]
    ledger.row(at, "earn", subtype, code, -quantity, ZERO, refid, "internal", price, wallet=origin)
    ledger.row(at, "earn", subtype, code, quantity, ZERO, refid, "internal", price, wallet=destination)


def _reward(ledger: _Ledger, at: datetime) -> None:
    """Reward: aktuelle Fassung earn/reward ins Earn-Wallet, aeltere staking auf das Staking-Kuerzel."""
    rng = ledger.rng
    ticker = rng.choice(EARN_TICKERS)
    price = ledger.price(ticker)
    quantity = max(SATOSHI, (_euros(rng, 1, 2_000) / price).quantize(SATOSHI))
    fee = (quantity * Decimal("0.15")).quantize(SATOSHI) if rng.random() < 0.25 else ZERO
    if ledger.wallets:
        ledger.row(at, "earn", "reward", ledger.codes[ticker], quantity, fee, _ident(rng, "S"), "crypto_reward", price,
                   wallet=rng.choice(EARN_WALLETS + (SPOT,)), reward=True)
    elif ledger.focus == "crypto":
        _coin_deposit(ledger, at)   # alte staking-Zeilen gehoeren dem Reward-Leser
    else:
        ledger.row(at, "staking", "", COINS[ticker][2], quantity, fee, _ident(rng, "S"), "crypto_unsupported", price, reward=True)


def _eur_reward(ledger: _Ledger, at: datetime) -> None:
    """Reward auf gehaltene Euro (EUR.HOLD): kein Teil des Euro-Kontos, fuer den Krypto-Leser ein Reward."""
    if not ledger.wallets:
        return _reward(ledger, at)
    rng = ledger.rng
    ledger.row(at, "earn", "reward", "EUR.HOLD", Decimal(rng.randrange(1, 5_000)) / 10_000, ZERO, _ident(rng, "S"), "crypto_reward", ONE,
               wallet=SPOT, reward=True)


def _adjustment(ledger: _Ledger, at: datetime) -> None:
    """Korrektur oder Umstellung (earn/migration): fuer den Krypto-Leser nicht unterstuetzt, mit Grund."""
    rng = ledger.rng
    ticker = rng.choice(EARN_TICKERS)
    price = ledger.price(ticker)
    quantity = max(SATOSHI, (_euros(rng, 1, 5_000) / price).quantize(SATOSHI))
    if ledger.wallets and rng.random() < 0.5:
        ledger.row(at, "earn", "migration", ledger.codes[ticker], quantity, ZERO, _ident(rng, "M"), "crypto_unsupported", price,
                   wallet=rng.choice(EARN_WALLETS))
    else:
        ledger.row(at, "adjustment", "", ledger.codes[ticker], quantity, ZERO, _ident(rng, "M"), "crypto_unsupported", price)


EVENTS: dict[str, Callable[[_Ledger, datetime], None]] = {
    "eur_deposit": _eur_deposit, "eur_withdrawal": _eur_withdrawal, "eur_transfer": _eur_transfer, "eur_zero": _eur_zero,
    "buy": _buy, "buy_spend": lambda ledger, at: _buy(ledger, at, spend=True), "sell": _sell,
    "sell_receive": lambda ledger, at: _sell(ledger, at, receive=True), "swap": _swap, "coin_deposit": _coin_deposit,
    "coin_withdrawal": _coin_withdrawal, "earn_move": _earn_move, "reward": _reward, "eur_reward": _eur_reward, "adjustment": _adjustment,
}
WEIGHTS = {
    "cash": {"eur_deposit": 3, "eur_withdrawal": 2, "eur_transfer": 0.5, "eur_zero": 0.4, "buy": 3, "buy_spend": 1.5, "sell": 2,
             "sell_receive": 1, "swap": 0.5, "coin_deposit": 0.6, "coin_withdrawal": 0.5, "earn_move": 0.4, "reward": 0.6, "eur_reward": 0.3,
             "adjustment": 0.2},
    "crypto": {"eur_deposit": 1.5, "eur_withdrawal": 0.8, "eur_transfer": 0.3, "eur_zero": 0.2, "buy": 2.5, "buy_spend": 1.2, "sell": 2,
               "sell_receive": 1, "swap": 1.2, "coin_deposit": 1.2, "coin_withdrawal": 1, "earn_move": 1.2, "reward": 1, "eur_reward": 0.3,
               "adjustment": 0.4},
    "reward": {"eur_deposit": 1, "eur_withdrawal": 0.3, "eur_transfer": 0.1, "eur_zero": 0.1, "buy": 1, "buy_spend": 0.4, "sell": 0.6,
               "sell_receive": 0.3, "swap": 0.3, "coin_deposit": 0.5, "coin_withdrawal": 0.3, "earn_move": 0.8, "reward": 5, "eur_reward": 0.5,
               "adjustment": 0.3},
}


# ---------------------------------------------------------------- Erwartung je Leser (aus den erfundenen Werten, nicht aus dem Text)
def _expected_cash(ledger: _Ledger) -> dict[str, Any]:
    """Euro-Konto: Bewegung = Betrag abzueglich Gebuehr, Saldo laut Zeile; Anfangssaldo vor der ersten lesbaren Euro-Zeile."""
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    opening = closing = None
    for ordinal, row in enumerate(ledger.rows, 1):
        if not row["_cash"]:
            continue
        if row["_amount"] is None or row["_balance"] is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
        cash = row["_amount"] - row["_fee"]
        if opening is None:
            opening = row["_balance"] - cash
        closing = row["_balance"]
        if cash == 0:
            continue
        if row["_at"] is None:
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
        candidates.append({"source_row_ordinal": ordinal, "local_date": row["_at"].astimezone(BERLIN).date().isoformat(),
                           "kind": "deposit" if cash > 0 else "withdrawal", "amount_decimal": _plain(abs(cash)),
                           "balance_after_decimal": _plain(row["_balance"]), "text": f"{row['type']} {row['subtype']}".strip()})
    if not candidates:
        return {}
    days = sorted(row["local_date"] for row in candidates)
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {"opening_balance_decimal": _plain(opening), "closing_balance_decimal": _plain(closing),
                        "period_from": days[0], "period_to": days[-1]}}


def _expected_crypto(ledger: _Ledger, file_name: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    for number, row in enumerate(ledger.rows, 1):
        kind = row["_crypto"]
        if kind in CRYPTO_KINDS and (row["_at"] is None or row["_amount"] is None):
            kind = "crypto_unreadable_row"
        if kind not in CRYPTO_KINDS:
            reasons[kind] = reasons.get(kind, 0) + 1; continue
        fee = row["_fee"]
        item = {"profile": "crypto_row", "source": "kraken", "file_name": file_name, "row_no": number,
                "wallet": row["wallet"] if ledger.wallets else SPOT, "at_utc": row["_at"].strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": "UTC",
                "ticker": TICKERS[row["asset"]], "kind": kind, "quantity": _plain(row["_amount"]),
                "fee_quantity": None if kind == "trade_eur" or fee == 0 else _plain(fee), "eur": None,
                "eur_fee": _plain(fee) if kind == "trade_eur" else None, "transaction_id": row["txid"], "hash": "", "address": "",
                "group": row["refid"], "quote": ""}
        item["row_key"] = crypto_row_key(item)
        candidates.append(item)
    return {"status": "multi", "candidates": candidates, "row_reasons": reasons} if candidates else {}


def _expected_reward(ledger: _Ledger) -> dict[str, Any]:
    """Je Zeile Zellen, Kennung, sieben Merkmale fuer doppelte Zeilen; ein Reward mit Menge, Zeit, Gebuehr in Coins, Konto und dem
    USD-Wert abzueglich USD-Gebuehr als Bewertung."""
    rows: list[dict[str, Any]] = []
    number = lambda value: "" if value is None else _plain(abs(value))
    for row in ledger.rows:
        item: dict[str, Any] = {
            "cells": [row[column] for column in ledger.header], "row_id": row["txid"],
            "signature": [reward_norm(row["time"]), reward_norm(row["type"]), reward_norm(row["subtype"]), reward_norm(row["asset"]),
                          number(row["_amount"]), number(row["_fee"]), reward_norm(row["wallet"]) if ledger.wallets else ""]}
        if not row["_reward"]:
            item["kind"] = "other"
        elif row["_at"] is None or not row["_amount"]:
            item["kind"] = "invalid"
        else:
            total = abs(row["_usd"]) - abs(row["_feeusd"])
            valuation = ({"source_value_mode": "fiat_total", "price_currency": "USD", "source_unit_price_decimal": None,
                          "source_fiat_total_decimal": _plain(total)} if total > 0 else
                         {"source_value_mode": "none", "price_currency": "USD", "source_unit_price_decimal": None, "source_fiat_total_decimal": None})
            item.update(kind="reward", asset=row["asset"].upper(), quantity=_plain(abs(row["_amount"])), local_date=row["_at"].date().isoformat(),
                        local_time=row["_at"].strftime("%H:%M:%S"), fee=None if row["_fee"] == 0 else _plain(abs(row["_fee"])),
                        account=row["wallet"] if ledger.wallets and row["wallet"] else "Kraken", valuation=valuation)
        rows.append(item)
    if not any(item["kind"] == "reward" for item in rows):
        return {}
    return {"time_zone": "UTC", "fee_role": "asset_quantity", "rows": rows}


def _generate(focus: str, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    ledger = _Ledger(rng, focus)
    names = list(EVENTS)
    weights = [WEIGHTS[focus][name] for name in names]
    moment = START + timedelta(seconds=rng.randrange(0, int((LAST_START - START).total_seconds())))
    for _ in range(rng.randrange(3, 28)):
        moment += timedelta(seconds=rng.randrange(300, 3 * 86_400))
        EVENTS[rng.choices(names, weights)[0]](ledger, moment)
    file_name = f"kraken-ledger-erfunden-{seed}.csv"
    build = {"cash": _expected_cash, "crypto": lambda item: _expected_crypto(item, file_name), "reward": _expected_reward}[focus]
    fallback = {"cash": _eur_deposit, "crypto": _coin_deposit, "reward": _reward}[focus]
    ledger.specials = False
    expected = build(ledger)
    while not expected:   # mindestens ein lesbarer Vorgang: sonst ist der Export kein Beleg dieses Lesers
        moment += timedelta(hours=1)
        fallback(ledger, moment)
        expected = build(ledger)
    text = ledger.text(rng.choice(("\n", "\r\n")))
    return {"file_name": file_name, "content": text if focus == "crypto" else text.encode("utf-8"), "expected": expected}


GENERATORS = {
    "kraken_eur_v1": lambda seed: _generate("cash", seed),
    "kraken_crypto_v1": lambda seed: _generate("crypto", seed),
    "kraken_ledger_csv_v1": lambda seed: _generate("reward", seed),
}
