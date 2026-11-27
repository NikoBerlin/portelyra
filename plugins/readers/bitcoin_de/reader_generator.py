"""Erzeuger erfundener Bitcoin.de-Kontoauszuege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Vorgaenge eines Coins; aus ihnen baut der Erzeuger den Kontoauszug je Coin (Semikolon,
deutsche Zahlen, Zeiten in Europe/Berlin, laufender Kontostand) und - unabhaengig vom Leser - das erwartete Ergebnis. Der Erzeuger
ruft den Leser nie auf; aus dem SDK nimmt er nur die Zeilenkennung (row_key), die das Ergebnis verlangt. Gleicher Startwert, gleicher
Beleg. Alle Werte sind erfunden: Referenzen, Adressen, Kurse, Mengen, Zeiten.

Der Text ist der, den der Kern dem Leser gibt: Die Datei von Bitcoin.de beginnt mit einer Byte-Order-Mark, die der Kern vor dem
Lesen abschneidet (crypto_statement_import_v1.parse_crypto_export_v1); der Erzeuger liefert den Text deshalb ohne sie.

Abgedeckt: Kauf gegen EUR (gebuchte Menge nach Gebuehr, Kurswert = Kurs x angekommene Menge, Gebuehr = bezahlter Betrag - Kurswert,
auf den Cent und nie negativ), Verkauf gegen EUR (Kurswert = Menge vor Gebuehr, Gebuehr = Unterschied zur Menge nach Gebuehr), Tausch
gegen USDT, Gegenseite eines Tauschs (Zu-/Abgang in der Gegenwaehrung, uebergangen), Ein- und Auszahlung mit Adresse, Netzwerkgebuehr
in einer oder mehreren eigenen Zeilen mit der Referenz der Auszahlung (am Transfer verrechnet), Auszahlung ohne Netzwerkgebuehr,
Registrierung, nicht gelesene Vorgangsart, Sommer- und Winterzeit.

Die Tage liegen in der Vergangenheit (2021-2024), damit der Beleg auch die Regel "kein Buchungstag nach heute" erfuellt, wenn der
Selbsttest vor einer Installation mit dem Datum des Rechners laeuft. Die Stunde 2 (Zeitumstellung) kommt nicht vor.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, ROUND_UP, Decimal
import random
from typing import Any

from portelyra_reader_sdk_v1 import crypto_row_key

CENT = Decimal("0.01")
SATOSHI = Decimal("0.00000001")
MICRO = Decimal("0.000001")
# Coin, Kursspanne in EUR, Adressform
COINS = (("BTC", (20_000, 65_000), "bc1q"), ("ETH", (1_000, 4_000), "0x"), ("BCH", (90, 600), "qq"), ("LTC", (40, 300), "ltc1q"),
         ("SOL", (10, 200), "So"))
ALPHANUMERIC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
HEX = "0123456789abcdef"
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _german(value: Decimal, places: int) -> str:
    """Bitcoin.de: Komma, feste Stellen, ohne Tausenderpunkt; Abgang mit Minus."""
    return f"{value:.{places}f}".replace(".", ",")


def _last_sunday(year: int, month: int) -> date:
    day = date(year, month, 31)
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _berlin_to_utc(local: datetime) -> datetime:
    """Sommerzeit von Ende Maerz 03:00 bis Ende Oktober 02:00 (Ortszeit); die Stunde 2 kommt im Beleg nicht vor."""
    summer = datetime.combine(_last_sunday(local.year, 3), time(3)) <= local < datetime.combine(_last_sunday(local.year, 10), time(2))
    return local - timedelta(hours=2 if summer else 1)


def _address(rng: random.Random, form: str) -> str:
    if form in ("bc1q", "ltc1q"):
        return form + "".join(rng.choice(BECH32) for _ in range(38))
    if form == "0x":
        return form + "".join(rng.choice(HEX) for _ in range(40))
    if form == "qq":
        return form + "".join(rng.choice(BECH32) for _ in range(40))
    return form + "".join(rng.choice(BASE58) for _ in range(42))


def _generate(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    coin, (low, high), form = rng.choice(COINS)
    own_address = _address(rng, form)
    header = ["Datum", "Typ", "Währung", "Referenz", f"{coin}-Adresse", "Kurs", "Einheit (Kurs)", f"{coin} vor Gebühr", "Menge vor Gebühr",
              "Einheit (Menge vor Gebühr)", f"{coin} nach Bitcoin.de-Gebühr", "Menge nach Bitcoin.de-Gebühr",
              "Einheit (Menge nach Bitcoin.de-Gebühr)", "Zu- / Abgang", "Kontostand"]
    file_name = ""
    local = datetime(2021, 1, 1) + timedelta(days=rng.randrange(0, 1_100))
    references: set[str] = set()
    lines: list[list[str]] = []
    candidates: list[dict[str, Any]] = []
    reasons: Counter = Counter()
    balance = Decimal(0)
    rate = Decimal(rng.randrange(low * 100, high * 100)) / 100

    def reference() -> str:
        while True:
            value = "".join(rng.choice(ALPHANUMERIC) for _ in range(rng.choice((6, 8, 10))))
            if value not in references:
                references.add(value); return value

    def stamp() -> datetime:
        nonlocal local
        local += timedelta(seconds=rng.randrange(600, 8 * 86_400))
        if local.hour == 2:   # Zeitumstellung: die Stunde 2 kommt nicht vor
            local += timedelta(hours=1)
        return local

    def line(at: datetime, kind: str, ref: str = "", address: str = "", rate: str = "", rate_unit: str = "", coin_before: str = "",
             before: str = "", before_unit: str = "", coin_after: str = "", after: str = "", after_unit: str = "", change: str = "") -> int:
        lines.append([at.strftime("%Y-%m-%d %H:%M:%S"), kind, coin, ref, address, rate, rate_unit, coin_before, before, before_unit,
                      coin_after, after, after_unit, change, _german(balance, 8)])
        return len(lines)

    def expect(row_no: int, at: datetime, kind: str, quantity: Decimal, ref: str, *, eur: Decimal | None = None, eur_fee: Decimal | None = None,
               fee: Decimal | None = None, address: str = "", quote: str = "") -> None:
        row = {"profile": "crypto_row", "source": "bitcoin_de", "file_name": file_name, "row_no": row_no, "wallet": "main",
               "at_utc": _berlin_to_utc(at).strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": "Europe/Berlin", "ticker": coin, "kind": kind,
               "quantity": _plain(quantity), "fee_quantity": None if fee is None else _plain(fee),
               "eur": None if eur is None else _plain(eur), "eur_fee": None if eur_fee is None else _plain(eur_fee),
               "transaction_id": ref, "hash": "", "address": address, "group": "", "quote": quote}
        candidates.append(row)

    def coin_amount(euro_low: int, euro_high: int, rate: Decimal) -> Decimal:
        amount = (Decimal(rng.randrange(euro_low * 100, euro_high * 100)) / 100 / rate).quantize(SATOSHI, ROUND_DOWN)
        return max(amount, Decimal("0.00010000"))

    first = local
    if rng.random() < 0.3:   # Auszug ab der Kontoeroeffnung
        line(stamp(), "Registrierung", change="0")
        reasons["crypto_registration"] += 1
    for _ in range(rng.randrange(1, 22)):
        roll = rng.random()
        # Kurs in EUR: Zufallsweg innerhalb der Spanne des Coins, je Vorgang hoechstens 5 % Schritt
        rate = min(max((rate * Decimal(rng.randrange(950, 1051)) / 1000).quantize(CENT, ROUND_HALF_UP), Decimal(low)), Decimal(high))
        if balance <= Decimal("0.001") and roll >= 0.45:
            roll = rng.choice((0.05, 0.30))   # ohne Bestand zuerst einzahlen oder kaufen
        at = stamp()
        if roll < 0.15:                                    # Einzahlung auf die eigene Adresse
            amount = coin_amount(50, 6_000, rate)
            ref = reference()
            balance += amount
            row_no = line(at, "Einzahlung", ref, own_address, change=_german(amount, 8))
            expect(row_no, at, "move", amount, ref, address=own_address)
        elif roll < 0.45:                                  # Kauf gegen EUR: Gebuehr in Coins, bezahlt ist "Menge nach Gebuehr"
            before = coin_amount(20, 5_000, rate)
            fee_coin = (before * Decimal(rng.choice(("0.005", "0.0025", "0.008")))).quantize(SATOSHI, ROUND_HALF_UP)
            arrived = before - fee_coin
            paid = (rate * arrived).quantize(CENT, rng.choice((ROUND_HALF_UP, ROUND_HALF_UP, ROUND_DOWN, ROUND_UP)))
            if rng.random() < 0.3:                          # bezahlt mehr als der Kurswert (etwa ein Expressaufschlag)
                paid += Decimal(rng.randrange(1, 300)) / 100
            ref = reference()
            balance += arrived
            row_no = line(at, "Kauf", ref, "", _german(rate, 2), f"{coin} / EUR", _german(before, 8),
                          _german((rate * before).quantize(CENT, ROUND_HALF_UP), 2), "EUR", _german(arrived, 8), _german(paid, 2), "EUR",
                          _german(arrived, 8))
            value = rate * arrived
            fee = (paid - value).quantize(CENT, ROUND_HALF_UP)
            expect(row_no, at, "trade", arrived, ref, eur=value, eur_fee=fee if fee > 0 else Decimal(0))
        elif roll < 0.62:                                  # Verkauf gegen EUR: Gebuehr in EUR
            sold = (balance * Decimal(rng.randrange(5, 101)) / 100).quantize(SATOSHI, ROUND_DOWN)
            gross = (rate * sold).quantize(CENT, ROUND_HALF_UP)
            fee = (gross * Decimal(rng.choice(("0.005", "0.0025", "0.008")))).quantize(CENT, ROUND_HALF_UP)
            ref = reference()
            balance -= sold
            row_no = line(at, "Verkauf", ref, "", _german(rate, 2), f"{coin} / EUR", _german(sold, 8), _german(gross, 2), "EUR",
                          _german(sold, 8), _german(gross - fee, 2), "EUR", _german(-sold, 8))
            expect(row_no, at, "trade", -sold, ref, eur=gross, eur_fee=fee)
        elif roll < 0.80:                                  # Auszahlung, Netzwerkgebuehr in eigenen Zeilen mit derselben Referenz
            fees = [Decimal(rng.randrange(1_000, 60_000)) * SATOSHI for _ in range(rng.choice((0, 1, 1, 1, 2)))]
            amount = ((balance - sum(fees)) * Decimal(rng.randrange(10, 101)) / 100).quantize(SATOSHI, ROUND_DOWN)
            if amount <= 0:
                fees, amount = [], balance
            ref = reference()
            target = _address(rng, form)
            fee_first = fees and rng.random() < 0.3
            fee_rows = []
            for part in fees if fee_first else []:
                balance -= part
                fee_rows.append(line(at, "Netzwerk-Gebühr", ref, change=_german(-part, 8)))
            balance -= amount
            row_no = line(at, "Auszahlung", ref, target, change=_german(-amount, 8))
            for part in [] if fee_first else fees:
                balance -= part
                fee_rows.append(line(at, "Netzwerk-Gebühr", ref, change=_german(-part, 8)))
            if fee_rows:
                reasons["crypto_fee_row"] += len(fee_rows)
            expect(row_no, at, "move", -amount, ref, fee=sum(fees) if fees else None, address=target)
        elif roll < 0.90:                                  # Tausch gegen USDT: Menge in Coins, Gegenwaehrung im Ergebnis
            usdt_rate = (rate * Decimal(rng.randrange(102, 112)) / 100).quantize(CENT, ROUND_HALF_UP)
            buy = rng.random() < 0.5 or balance <= Decimal("0.001")
            amount = coin_amount(20, 3_000, rate) if buy else (balance * Decimal(rng.randrange(5, 60)) / 100).quantize(SATOSHI, ROUND_DOWN)
            fee_coin = (amount * Decimal("0.005")).quantize(SATOSHI, ROUND_HALF_UP) if buy else Decimal(0)
            gross = (usdt_rate * amount).quantize(MICRO, ROUND_HALF_UP)
            net_quote = gross if buy else (gross * Decimal("0.995")).quantize(MICRO, ROUND_HALF_UP)
            change = amount - fee_coin if buy else -amount
            ref = reference()
            balance += change
            row_no = line(at, "Kauf" if buy else "Verkauf", ref, "", _german(usdt_rate, 2), f"{coin} / USDT", _german(amount, 8), _german(gross, 6),
                          "USDT", _german(amount - fee_coin, 8), _german(net_quote, 6), "USDT", _german(change, 8))
            expect(row_no, at, "swap", change, ref, quote="USDT")
        elif roll < 0.95:                                  # Gegenseite eines Tauschs: Zu-/Abgang in USDT, steht beim anderen Coin
            usdt = Decimal(rng.randrange(10_000_000, 3_000_000_000)) * MICRO
            buy = rng.random() < 0.5
            line(at, "Kauf" if buy else "Verkauf", reference(), "", _german(rate, 2), f"{coin} / USDT", "", _german(usdt, 6), "USDT", "",
                 _german((usdt * Decimal("0.998")).quantize(MICRO, ROUND_HALF_UP), 6), "USDT", _german(-usdt if buy else usdt, 6))
            reasons["crypto_swap_counter_leg"] += 1
        else:                                              # nicht gelesene Vorgangsart (erfunden)
            amount = Decimal(rng.randrange(1_000, 500_000)) * SATOSHI
            balance += amount
            line(at, "Bonus", reference(), change=_german(amount, 8))
            reasons["crypto_unsupported"] += 1
    if not candidates:   # mindestens eine Bewegung
        at = stamp()
        amount = Decimal("0.01000000")
        ref = reference()
        balance += amount
        row_no = line(at, "Einzahlung", ref, own_address, change=_german(amount, 8))
        expect(row_no, at, "move", amount, ref, address=own_address)

    file_name = f"{coin.lower()}_account_statement_{first:%Y%m%d}-{local:%Y%m%d}.csv"
    for row in candidates:
        row["file_name"] = file_name
        row["row_key"] = crypto_row_key(row)
    text = "\n".join(";".join(cells) for cells in [header] + lines) + "\n"
    expected = {"status": "multi", "candidates": candidates, "row_reasons": dict(reasons)}
    return {"file_name": file_name, "content": text, "expected": expected}


GENERATORS = {"bitcoin_de_crypto_v1": _generate}
