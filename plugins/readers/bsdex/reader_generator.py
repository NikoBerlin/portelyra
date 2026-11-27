"""Erzeuger erfundener BSDEX-Belege fuer den Selbsttest (statement_reader_v1, Stufe 4, rc.379).

Aus einem Startwert entstehen erfundene Vorgaenge; aus ihnen baut der Erzeuger den Beleg im Format von BSDEX und - unabhaengig vom
Leser - das erwartete Ergebnis. Er ruft die Leser-Module nie auf, sonst bestaetigte der Leser nur sich selbst; aus dem SDK nutzt er
nur die Kennung einer Krypto-Zeile (crypto_row_key), die das Ergebnis verlangt. Gleicher Startwert, gleicher Beleg. Alle Werte sind
erfunden: Kennungen, Adressen, IBAN, Betraege, Zeiten. Die Tage liegen in 2021-2024 (Vergangenheit, auch fuer einen Selbsttest mit
dem Datum des Rechners).

Zwei Belegarten:
- Export "Transaktionen" (Minuten in Berlin, Betraege deutsch geschrieben; Spalte "Gefüllt" = Kurswert in EUR, "Ausgeführter
  Gesamtbetrag" = ausgefuehrte Menge in Coin; "Bestellstatus" und "Storniert" fehlen aelteren Exporten);
- Transaktionshistorie je Jahr (Ausfuehrungen in UTC auf die Sekunde, Betraege mit Punkt, je Ausfuehrung Betrag und Entgelt).
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import io
import random
from typing import Any
from zoneinfo import ZoneInfo

from portelyra_reader_sdk_v1 import crypto_row_key

BERLIN = ZoneInfo("Europe/Berlin")

# Coins: Name in der Spalte "Kryptowährung", Kuerzel, Stellen der Menge, Kursspanne in EUR (erfunden).
COINS = (("Bitcoin", "BTC", 6, 15_000, 60_000), ("Ether", "ETH", 5, 900, 3_500), ("XRP", "XRP", 2, 0.3, 0.9),
         ("Solana", "SOL", 3, 15, 180), ("Cardano", "ADA", 2, 0.2, 1.4), ("Polkadot", "DOT", 3, 4, 30),
         ("Litecoin", "LTC", 4, 50, 200), ("Chainlink", "LINK", 3, 5, 30))

EXPORT_HEADER = ["Transaktionstyp", "Kryptowährung", "Betrag", "Seite", "Ausgelöster Preis", "Gefüllt", "Ausgeführter Gesamtbetrag",
                 "Ausgeführte Menge", "Status", "Transaktionsentgelt", "Bestellstatus", "Erstellt", "Finalisiert am", "Stop-Preis",
                 "Ausgelöst am", "Storniert", "Sendeadresse", "Zieladresse", "Zieladressen-Tag", "Sendeadressen-Tag", "IBAN",
                 "Operation Type", "Completed At"]
OLD_DROPPED = ("Bestellstatus", "Storniert")   # aeltere Exporte
HISTORY_HEADER = ["ID", "Typ", "Ausführung", "eingehender Betrag", "eingehendes Asset", "ausgehender Betrag", "ausgehendes Asset",
                  "Transaktionsentgelt", "Entgeltwährung", "Sender", "Empfänger"]
NO_PRICE = "–,–– €"


# ---------------------------------------------------------------- Zahlen und Zeiten
def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _german_number(value: Decimal, places: int | None = None) -> str:
    """1234.5 -> "1.234,5" (Tausenderpunkt, Dezimalkomma), mit festen Stellen auf Wunsch."""
    text = f"{value:.{places}f}" if places is not None else _plain(value)
    whole, _, fraction = text.partition(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:]); whole = whole[:-3]
    groups.insert(0, whole)
    return ".".join(groups) + ("," + fraction if fraction else "")


def _euro(value: Decimal) -> str:
    return _german_number(value, 2) + " €"


def _coin(value: Decimal, ticker: str) -> str:
    return _german_number(value) + " " + ticker


def _stamp(moment: datetime) -> str:
    """Zeit des Exports: Minuten in Berlin, "15.04.2023, 09:05"."""
    return moment.strftime("%d.%m.%Y, %H:%M")


def _utc(moment: datetime) -> datetime:
    """Eine Zeit in Berlin (ohne Zone, wie im Export geschrieben) in UTC."""
    return moment.replace(tzinfo=BERLIN).astimezone(timezone.utc)


def _cents(rng: random.Random, low: float, high: float) -> Decimal:
    return Decimal(rng.randrange(int(low * 100), int(high * 100) + 1)) / 100


def _quantity(rng: random.Random, places: int, eur: Decimal, low: float, high: float) -> Decimal:
    """Menge zu einem Kurswert: Stellen je Coin; ganze Mengen ab 1.000 stets mit Nachkommastelle (sonst lese ein Tausenderpunkt
    sich je nach Leser anders)."""
    price = Decimal(str(round(rng.uniform(low, high), 4)))
    quantity = (eur / price).quantize(Decimal(1).scaleb(-places))
    if quantity <= 0:
        quantity = Decimal(1).scaleb(-places)
    if quantity >= 1000 and quantity == quantity.to_integral_value():
        quantity += Decimal(1).scaleb(-places)
    return quantity


def _fee(eur: Decimal) -> Decimal:
    return max(Decimal("0.01"), (eur * Decimal("0.0035")).quantize(Decimal("0.01")))


def _hex(rng: random.Random, length: int) -> str:
    return "".join(rng.choice("0123456789abcdef") for _ in range(length))


def _start(rng: random.Random) -> datetime:
    return datetime(2021, 1, 4, 8, 0) + timedelta(days=rng.randrange(0, 365 * 3 - 30), minutes=rng.randrange(0, 12 * 60))


def _csv(rows: list[list[str]], line_end: str) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator=line_end)
    writer.writerows(rows)
    return buffer.getvalue()


# ---------------------------------------------------------------- Export "Transaktionen"
# Vorgangsarten des Exports mit Gewicht je Leser (Euro-Guthaben, Krypto, Rewards).
EXPORT_KINDS = {
    "order_closed": (8, 8, 3),            # Limit/Market, ausgefuehrt, mit "Finalisiert am"
    "order_closed_unstamped": (1, 2, 0),  # ausgefuehrt, aelterer Export ohne "Finalisiert am" (nur "Erstellt")
    "order_cancelled_partly": (2, 2, 1),  # storniert mit Teilausfuehrung ("Storniert" = Ende)
    "order_cancelled": (1, 1, 1),         # storniert ohne Ausfuehrung
    "order_open": (1, 1, 1),              # offen ohne Ausfuehrung
    "order_open_partly": (1, 1, 1),       # offen mit Teilausfuehrung (wartet auf den Abschluss)
    "order_bad_time": (1, 1, 0),          # "Finalisiert am" unlesbar
    "eur_deposit": (3, 1, 1),
    "eur_withdrawal": (2, 1, 1),
    "eur_bad_date": (1, 0, 0),            # Euro-Bewegung ohne lesbare Zeit
    "eur_bad_amount": (1, 0, 0),          # Euro-Bewegung ohne lesbaren Betrag
    "order_bad_amount": (1, 0, 0),        # ausgefuehrte Order ohne lesbaren Kurswert
    "coin_deposit": (1, 2, 1),
    "coin_withdrawal": (1, 2, 1),
    "coin_without_address": (0, 1, 0),    # Coin-Bewegung ohne Adresse
    "staking": (1, 2, 1),
    "unstaking": (1, 1, 1),
    "staking_reward": (1, 2, 8),
    "reward_bad": (0, 0, 2),              # Staking Reward ohne Menge oder lesbare Zeit
    "other_operation": (0, 1, 1),         # andere Operation (wird nicht gelesen)
}


def _export_events(rng: random.Random, weight_index: int, old_format: bool) -> list[dict[str, Any]]:
    """Erfundene Vorgaenge des Exports, je Vorgang alle Angaben, aus denen Beleg und Erwartung entstehen."""
    kinds = [kind for kind, weights in EXPORT_KINDS.items() if weights[weight_index]
             and not (old_format and kind in ("order_cancelled_partly", "order_open_partly", "order_open", "order_cancelled"))]
    weights = [EXPORT_KINDS[kind][weight_index] for kind in kinds]
    moment = _start(rng)
    events = []
    for _ in range(rng.randrange(1, 26)):
        moment += timedelta(days=rng.randrange(0, 12), minutes=rng.randrange(1, 600))
        name, ticker, places, low, high = rng.choice(COINS)
        kind = rng.choices(kinds, weights)[0]
        side = rng.choice(("Kaufen", "Verkaufen"))
        filled = _cents(rng, 5, 4000)
        ordered = _quantity(rng, places, filled, low, high)
        event = {"kind": kind, "coin": name, "ticker": ticker, "side": side, "created": moment, "finished": None, "cancelled_at": None,
                 "ordered": ordered, "executed": ordered, "filled": filled, "fee": _fee(filled), "status": "Ausgeführt",
                 "order_status": "Geschlossen", "type": rng.choice(("Limit", "Limit", "Market")), "eur_amount": None,
                 "bad_finish": False, "bad_created": False, "bad_amount": False, "amount_in_euro": False}
        if kind.startswith("order"):
            if kind in ("order_closed", "order_bad_time", "order_bad_amount"):
                event["finished"] = moment + timedelta(minutes=rng.choice((0, 1, 3, 45)), days=rng.choice((0, 0, 0, 1, 9)))
                # Market-Kauf ueber einen Euro-Betrag: "Betrag" nennt Euro statt Coin
                event["amount_in_euro"] = event["type"] == "Market" and side == "Kaufen" and rng.random() < 0.5
            elif kind == "order_closed_unstamped":
                pass
            elif kind in ("order_cancelled_partly", "order_open_partly"):
                event["executed"] = (ordered * Decimal(rng.randrange(10, 90)) / 100).quantize(Decimal(1).scaleb(-places))
                if event["executed"] <= 0 or event["executed"] >= 1000 and event["executed"] == event["executed"].to_integral_value():
                    event["executed"] += Decimal(1).scaleb(-places)
                event["filled"] = (filled * event["executed"] / ordered).quantize(Decimal("0.01")) or Decimal("0.01")
                event["fee"] = _fee(event["filled"])
                event["status"] = "Teilweise ausgeführt"
                if kind == "order_cancelled_partly":
                    event["order_status"] = "Storniert"
                    event["cancelled_at"] = moment + timedelta(days=rng.randrange(0, 5), minutes=rng.randrange(1, 300))
                else:
                    event["order_status"] = "Offen"
            else:   # ohne Ausfuehrung
                event["executed"], event["filled"], event["fee"] = Decimal(0), Decimal(0), Decimal(0)
                event["status"] = "Storniert" if kind == "order_cancelled" else "Offen"
                event["order_status"] = "Storniert" if kind == "order_cancelled" else "Offen"
                if kind == "order_cancelled":
                    event["cancelled_at"] = moment + timedelta(hours=rng.randrange(1, 72))
            event["bad_finish"] = kind == "order_bad_time"
            event["bad_amount"] = kind == "order_bad_amount"
        elif kind in ("eur_deposit", "eur_withdrawal", "eur_bad_date", "eur_bad_amount"):
            event["eur_amount"] = _cents(rng, 10, 5000)
            event["withdrawal"] = kind == "eur_withdrawal" or (kind != "eur_deposit" and rng.random() < 0.5)
            event["finished"] = None if rng.random() < 0.3 else moment + timedelta(days=rng.choice((0, 0, 1, 2)), minutes=rng.randrange(1, 90))
            event["type"] = "Auszahlung" if event["withdrawal"] else rng.choice(("Einzahlung", "Einzahlungen"))
            event["bad_created"] = kind == "eur_bad_date"
            if event["bad_created"]:
                event["finished"] = None
            event["bad_amount"] = kind == "eur_bad_amount"
        elif kind in ("coin_deposit", "coin_withdrawal", "coin_without_address"):
            event["type"] = "Auszahlung" if kind == "coin_withdrawal" or (kind == "coin_without_address" and rng.random() < 0.5) else "Einzahlung"
            event["finished"] = None if rng.random() < 0.2 else moment + timedelta(minutes=rng.randrange(5, 240))
            event["address"] = "" if kind == "coin_without_address" else f"erf{_hex(rng, 30)}"
        elif kind in ("staking", "unstaking", "staking_reward", "reward_bad", "other_operation"):
            event["type"] = {"staking": "Staking", "unstaking": "Unstaking", "other_operation": "Sonderaktion"}.get(kind, "Staking Reward")
            if kind in ("staking_reward", "reward_bad"):
                event["ordered"] = Decimal(rng.randrange(1, 10**6)).scaleb(-8)
            event["completed"] = moment + timedelta(days=rng.randrange(0, 10), minutes=rng.randrange(0, 600))
            if kind == "reward_bad":
                event["bad_created"] = rng.random() < 0.5
                if not event["bad_created"]:
                    event["ordered"] = Decimal(0)
        events.append(event)
    return events


def _export_cells(event: dict[str, Any], rng: random.Random) -> dict[str, str]:
    """Die Zellen einer Zeile des Exports nach Spaltennamen."""
    cells = {name: "" for name in EXPORT_HEADER}
    kind = event["kind"]
    created = "erfunden" if event["bad_created"] else _stamp(event["created"])
    if kind.startswith("order"):
        cells.update({"Transaktionstyp": event["type"], "Kryptowährung": event["coin"],
                      "Betrag": _euro(event["filled"]) if event["amount_in_euro"] else _coin(event["ordered"], event["ticker"]),
                      "Seite": event["side"], "Ausgelöster Preis": NO_PRICE,
                      "Gefüllt": NO_PRICE if event["bad_amount"] else _euro(event["filled"]),
                      "Ausgeführter Gesamtbetrag": _coin(event["executed"], event["ticker"]), "Ausgeführte Menge": "0,00 €",
                      "Status": event["status"], "Transaktionsentgelt": _euro(event["fee"]), "Bestellstatus": event["order_status"],
                      "Erstellt": created,
                      "Finalisiert am": "erfunden" if event["bad_finish"] else (_stamp(event["finished"]) if event["finished"] else ""),
                      "Storniert": _stamp(event["cancelled_at"]) if event["cancelled_at"] else ""})
        if event["type"] == "Market":
            cells["Ausgelöster Preis"] = ""
    elif event["eur_amount"] is not None:
        cells.update({"Transaktionstyp": event["type"], "Betrag": NO_PRICE if event["bad_amount"] else _euro(event["eur_amount"]),
                      "Status": "Ausgeführt", "Erstellt": created, "Finalisiert am": _stamp(event["finished"]) if event["finished"] else "",
                      "IBAN": f"DE00 0000 0000 {rng.randrange(1000, 9999)} {rng.randrange(1000, 9999)} 00"})
    elif kind.startswith("coin"):
        cells.update({"Transaktionstyp": event["type"], "Kryptowährung": event["coin"], "Betrag": _coin(event["ordered"], event["ticker"]),
                      "Status": "Ausgeführt", "Erstellt": created, "Finalisiert am": _stamp(event["finished"]) if event["finished"] else ""})
        if event["address"]:
            cells["Zieladresse" if event["type"] == "Auszahlung" else "Sendeadresse"] = event["address"]
            if event["type"] == "Auszahlung":
                cells["Sendeadresse"] = f"bsdex{_hex(rng, 12)}"
    else:   # Staking, Unstaking, Staking Reward, andere Operation
        cells.update({"Transaktionstyp": event["type"], "Kryptowährung": event["coin"],
                      "Betrag": ("0 " + event["ticker"]) if event["ordered"] == 0 else _coin(event["ordered"], event["ticker"]),
                      "Status": "Ausgeführt", "Erstellt": created, "Operation Type": event["type"],
                      "Completed At": _stamp(event["completed"])})
    return cells


def _export_document(rng: random.Random, events: list[dict[str, Any]], old_format: bool) -> tuple[list[str], list[list[str]]]:
    header = [name for name in EXPORT_HEADER if not (old_format and name in OLD_DROPPED)]
    rows = []
    for event in events:
        cells = _export_cells(event, rng)
        rows.append([cells[name] for name in header])
    return header, rows


# ---------------------------------------------------------------- Transaktionshistorie
HISTORY_KINDS = (("buy", 6), ("sell", 5), ("deposit", 2), ("withdrawal", 1), ("coin_withdrawal_eur_fee", 1),
                 ("coin_withdrawal_coin_fee", 1), ("coin_deposit", 1), ("reward", 1), ("bad_date", 1), ("bad_amount", 1))


def _history_events(rng: random.Random) -> list[dict[str, Any]]:
    """Erfundene Zeilen einer Jahreshistorie: Ausfuehrungen (oft mehrere je Order in Minuten, auch ueber Mitternacht in Berlin),
    Euro-Ein- und -Auszahlungen, Coin-Bewegungen mit Entgelt in EUR oder Coin, Rewards, unlesbare Zeilen."""
    moment = datetime(2021, 1, 4, 6, 0, tzinfo=timezone.utc) + timedelta(days=rng.randrange(0, 365 * 3 - 30), seconds=rng.randrange(0, 86_400))
    events = []
    kinds, weights = [kind for kind, _ in HISTORY_KINDS], [weight for _, weight in HISTORY_KINDS]
    for _ in range(rng.randrange(1, 26)):
        moment += timedelta(days=rng.choice((0, 0, 1, 3, 8)), seconds=rng.randrange(1, 20_000))
        if rng.random() < 0.15:   # spaet am Abend in UTC: in Berlin schon der naechste Tag
            moment = moment.replace(hour=rng.choice((22, 23)), minute=rng.randrange(0, 60))
        kind = rng.choices(kinds, weights)[0]
        _name, ticker, places, low, high = rng.choice(COINS)
        parts = rng.choice((1, 1, 1, 2, 3)) if kind in ("buy", "sell") else 1
        at = moment
        for _part in range(parts):   # Teilausfuehrungen einer Order: dieselbe Richtung und derselbe Coin, Sekunden bis Minuten spaeter
            eur = _cents(rng, 1, 3000)
            identity = "" if rng.random() < 0.03 else f"{_hex(rng, 8)}-{_hex(rng, 4)}-{_hex(rng, 4)}-{_hex(rng, 12)}"   # selten ohne ID
            event = {"kind": kind, "ticker": ticker, "at": at, "id": identity, "eur": eur, "fee": _fee(eur),
                     "quantity": _quantity(rng, places, eur, low, high)}
            events.append(event)
            at += timedelta(seconds=rng.randrange(1, 900))
        moment = at
    return events


def _history_cells(event: dict[str, Any], rng: random.Random) -> list[str]:
    kind, ticker = event["kind"], event["ticker"]
    stamp = event["at"].strftime("%Y-%m-%d %H:%M:%S +0000 UTC")
    quantity, eur, fee = _plain(event["quantity"]), f"{event['eur']:.2f}", f"{event['fee']:.2f}"
    row = {"ID": event["id"], "Typ": kind, "Ausführung": stamp, "eingehender Betrag": "", "eingehendes Asset": "", "ausgehender Betrag": "",
           "ausgehendes Asset": "", "Transaktionsentgelt": "", "Entgeltwährung": "", "Sender": "", "Empfänger": ""}
    if kind == "buy":
        row.update({"eingehender Betrag": quantity, "eingehendes Asset": ticker, "ausgehender Betrag": eur, "ausgehendes Asset": "EUR",
                    "Transaktionsentgelt": fee, "Entgeltwährung": "EUR"})
    elif kind == "sell":
        row.update({"eingehender Betrag": eur, "eingehendes Asset": "EUR", "ausgehender Betrag": quantity, "ausgehendes Asset": ticker,
                    "Transaktionsentgelt": fee, "Entgeltwährung": "EUR"})
    elif kind == "deposit":
        row.update({"eingehender Betrag": eur, "eingehendes Asset": "EUR"})
    elif kind == "withdrawal":
        row.update({"ausgehender Betrag": eur, "ausgehendes Asset": "EUR"})
    elif kind.startswith("coin_withdrawal"):
        row.update({"Typ": "withdrawal", "ausgehender Betrag": quantity, "ausgehendes Asset": ticker, "Sender": "erfunden",
                    "Empfänger": f"erf{_hex(rng, 20)}"})
        row.update({"Transaktionsentgelt": fee, "Entgeltwährung": "EUR"} if kind.endswith("eur_fee") else
                   {"Transaktionsentgelt": _plain(event["quantity"] / 100), "Entgeltwährung": ticker})
    elif kind in ("coin_deposit", "reward"):
        row.update({"Typ": "deposit" if kind == "coin_deposit" else "reward", "eingehender Betrag": quantity, "eingehendes Asset": ticker})
    elif kind == "bad_date":
        row.update({"Typ": "buy", "Ausführung": "erfunden", "eingehender Betrag": quantity, "eingehendes Asset": ticker,
                    "ausgehender Betrag": eur, "ausgehendes Asset": "EUR", "Transaktionsentgelt": fee, "Entgeltwährung": "EUR"})
    elif kind == "bad_amount":   # Betrag mit Dezimalkomma: in der Historie nicht lesbar
        row.update({"Typ": "sell", "eingehender Betrag": eur.replace(".", ","), "eingehendes Asset": "EUR", "ausgehender Betrag": quantity,
                    "ausgehendes Asset": ticker, "Transaktionsentgelt": fee, "Entgeltwährung": "EUR"})
    return [row[name] for name in HISTORY_HEADER]


def _history_document(rng: random.Random) -> tuple[list[dict[str, Any]], str]:
    """Zeilen (mit ihren Vorgaengen) und Text einer Jahreshistorie; aufsteigend oder absteigend sortiert."""
    events = _history_events(rng)
    if rng.random() < 0.4:
        events.reverse()
    rows = [_history_cells(event, rng) for event in events]
    return events, _csv([HISTORY_HEADER] + rows, rng.choice(("\n", "\r\n")))


def _history_fill(event: dict[str, Any], ordinal: int, file_name: str) -> dict[str, Any] | None:
    """Die Ausfuehrung einer Zeile, wie die Historie sie belegt; None fuer alle anderen Zeilen."""
    if event["kind"] not in ("buy", "sell"):
        return None
    return {"id": event["id"] or f"{file_name}:{ordinal}", "ordinal": ordinal, "file_name": file_name, "side": event["kind"],
            "asset": event["ticker"], "quantity": Decimal(_plain(event["quantity"])), "eur": Decimal(f"{event['eur']:.2f}"),
            "fee": Decimal(f"{event['fee']:.2f}"), "at": event["at"]}


# ---------------------------------------------------------------- Euro-Guthaben (bsdex_eur_v1, eine Datei allein)
def _cash_row(ordinal: int, day: str, cash: Decimal, text: str) -> dict[str, Any]:
    return {"source_row_ordinal": ordinal, "local_date": day, "kind": "deposit" if cash > 0 else "withdrawal", "amount_decimal": _plain(abs(cash)),
            "balance_after_decimal": None, "text": text}


def _cash_from_history(rng: random.Random) -> tuple[str, dict[str, Any]]:
    """Eine Historie allein: Ausfuehrungen je Berliner Tag, Richtung und Coin zusammen; Euro-Ein- und -Auszahlungen und Euro-Entgelte
    an Coin-Ausgaengen je Zeile; Coin-Bewegungen ohne Euro werden uebergangen; unlesbare Zeilen werden Hinweise."""
    events, text = _history_document(rng)
    days: dict[tuple[str, str, str], list[tuple[int, dict[str, Any]]]] = {}
    flows, diagnostics = [], []
    for ordinal, event in enumerate(events, 1):
        kind = event["kind"]
        day = event["at"].astimezone(BERLIN).date().isoformat()
        if kind == "bad_date":
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"})
        elif kind == "bad_amount":
            diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"})
        elif kind in ("buy", "sell"):
            days.setdefault((day, kind, event["ticker"]), []).append((ordinal, event))
        elif kind == "deposit":
            flows.append(_cash_row(ordinal, day, event["eur"], "Einzahlung"))
        elif kind == "withdrawal":
            flows.append(_cash_row(ordinal, day, -event["eur"], "Auszahlung"))
        elif kind == "coin_withdrawal_eur_fee":
            flows.append(_cash_row(ordinal, day, -event["fee"], f"Gebühr {event['ticker']}"))
    candidates = []
    for (day, side, ticker), group in sorted(days.items()):
        eur, fee = sum(event["eur"] for _, event in group), sum(event["fee"] for _, event in group)
        candidates.append(_cash_row(group[0][0], day, -(eur + fee) if side == "buy" else eur - fee, f"{'Kauf' if side == 'buy' else 'Verkauf'} {ticker}"))
    return text, {"candidates": candidates + flows, "diagnostics": diagnostics}


def _cash_from_export(rng: random.Random) -> tuple[str, dict[str, Any]]:
    """Ein Export allein: je ausgefuehrter Order ihr Kurswert samt Entgelt zum Tag des Abschlusses (Finalisiert am, Storniert oder
    Erstellt), Euro-Ein- und -Auszahlungen zum Tag des Abschlusses; offene Orders warten, Orders ohne Ausfuehrung und Coin-Vorgaenge
    werden uebergangen, unlesbare Zeilen werden Hinweise."""
    old_format = rng.random() < 0.2
    events = _export_events(rng, 0, old_format)
    header, rows = _export_document(rng, events, old_format)
    orders, flows, diagnostics = [], [], []
    for ordinal, event in enumerate(events, 1):
        kind = event["kind"]
        if kind.startswith("order"):
            if event["executed"] == 0:
                continue
            finished = None if event["bad_finish"] else (event["finished"] or (None if old_format else event["cancelled_at"]))
            is_open = event["order_status"] == "Offen" if not old_format else event["status"] != "Ausgeführt" and finished is None
            if is_open:
                continue
            if event["bad_amount"]:
                diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
            day = (finished or event["created"]).date().isoformat()
            cash = -(event["filled"] + event["fee"]) if event["side"] == "Kaufen" else event["filled"] - event["fee"]
            orders.append((day, ordinal, _cash_row(ordinal, day, cash, f"{'Kauf' if event['side'] == 'Kaufen' else 'Verkauf'} {event['coin']}")))
        elif event["eur_amount"] is not None:
            if event["bad_created"]:
                diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "date_invalid"}); continue
            if event["bad_amount"]:
                diagnostics.append({"source_row_ordinal": ordinal, "reason_code": "amount_invalid"}); continue
            day = (event["finished"] or event["created"]).date().isoformat()
            cash = -event["eur_amount"] if event["withdrawal"] else event["eur_amount"]
            flows.append((day, ordinal, _cash_row(ordinal, day, cash, "Auszahlung" if event["withdrawal"] else "Einzahlung")))
    candidates = [row for _, _, row in sorted(orders, key=lambda item: item[:2])] + [row for _, _, row in sorted(flows, key=lambda item: item[:2])]
    return _csv([header] + rows, rng.choice(("\n", "\r\n"))), {"candidates": candidates, "diagnostics": diagnostics}


def _generate_eur(seed: int) -> dict[str, Any]:
    for attempt in range(50):   # ohne Bewegung ist die Datei kein Beleg dieses Formats: dann der naechste Versuch
        rng = random.Random(seed * 100 + attempt)
        if rng.random() < 0.5:
            file_name = f"bsdex-historie-erfunden-{seed}.csv"
            text, expected = _cash_from_history(rng)
        else:
            file_name = f"bsdex-transaktionen-erfunden-{seed}.csv"
            text, expected = _cash_from_export(rng)
        if expected["candidates"]:
            break
    days = sorted(row["local_date"] for row in expected["candidates"])
    expected["summary"] = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0], "period_to": days[-1]}
    bom = "﻿" if rng.random() < 0.3 else ""
    return {"file_name": file_name, "content": (bom + text).encode("utf-8"), "expected": expected}


# ---------------------------------------------------------------- Transaktionshistorie als Beleg (bsdex_history_v1)
def _generate_history(seed: int) -> dict[str, Any]:
    """Bucht nichts: belegt je Ausfuehrung (Kauf, Verkauf gegen EUR) Menge, Kurswert, Entgelt und Zeit in UTC; alle anderen Zeilen
    und unlesbare Zeilen gehoeren nicht dazu."""
    rng = random.Random(seed)
    file_name = f"bsdex-historie-erfunden-{seed}.csv"
    events, text = _history_document(rng)
    fills = [fill for ordinal, event in enumerate(events, 1) if (fill := _history_fill(event, ordinal, file_name)) is not None]
    return {"file_name": file_name, "content": text,
            "expected": {"status": "multi", "candidates": [], "row_reasons": {}, "evidence": {"bsdex_executions": fills}}}


# ---------------------------------------------------------------- Export als Krypto-Beleg (bsdex_crypto_v1)
def _crypto_row(file_name: str, row_no: int, at: datetime, ticker: str, kind: str, quantity: Decimal, eur: Decimal | None = None,
                eur_fee: Decimal | None = None, address: str = "", window_from: datetime | None = None, at_last_execution: bool = False) -> dict[str, Any]:
    row = {"profile": "crypto_row", "source": "bsdex", "file_name": file_name, "row_no": row_no, "wallet": "main",
           "at_utc": _utc(at).strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": "Europe/Berlin", "ticker": ticker, "kind": kind,
           "quantity": _plain(quantity), "fee_quantity": None, "eur": None if eur is None else _plain(eur),
           "eur_fee": None if eur_fee is None else _plain(eur_fee), "transaction_id": "", "hash": "", "address": address, "group": "", "quote": ""}
    if window_from is not None:
        row["window_from_utc"] = _utc(window_from).strftime("%Y-%m-%dT%H:%M:%SZ")
    if at_last_execution:
        row["at_last_execution"] = True
    row["row_key"] = crypto_row_key(row)
    return row


def _generate_crypto(seed: int) -> dict[str, Any]:
    """Je Zeile des Exports: ausgefuehrte Order als Trade zum Abschluss (mit Anlage als Fenster), ohne Abschlusszeit als Auftrag,
    storniert mit Teilausfuehrung zur letzten Ausfuehrung; Staking und Unstaking als interne Umbuchung zur Anlage; Coin-Ein- und
    -Auszahlungen ohne Richtung; Gruende fuer Rewards, Euro-Bewegungen, offene und stornierte Orders, andere Operationen und
    unvollstaendige Zeilen."""
    rng = random.Random(seed)
    file_name = f"bsdex-transaktionen-erfunden-{seed}.csv"
    old_format = rng.random() < 0.2
    events = _export_events(rng, 1, old_format)
    header, rows = _export_document(rng, events, old_format)
    candidates: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}
    skip = lambda code: reasons.__setitem__(code, reasons.get(code, 0) + 1)
    for row_no, event in enumerate(events, 1):
        kind, ticker = event["kind"], event["ticker"]
        if kind in ("staking_reward", "reward_bad"):
            skip("crypto_reward")
        elif kind in ("staking", "unstaking"):
            candidates.append(_crypto_row(file_name, row_no, event["created"], ticker, "internal_" + kind, event["ordered"]))
        elif kind == "other_operation":
            skip("crypto_unsupported")
        elif kind.startswith("order"):
            status = None if old_format else event["order_status"]
            if status != "Geschlossen" and not event["executed"]:
                skip("crypto_order_open" if status == "Offen" else "crypto_cancelled"); continue
            if status == "Offen":
                skip("crypto_order_partly_open"); continue
            cancelled = status != "Geschlossen"
            if event["bad_finish"]:
                skip("crypto_unreadable_row"); continue
            executed = event["finished"] or (event["cancelled_at"] if cancelled else None)
            signed = event["executed"] if event["side"] == "Kaufen" else -event["executed"]
            candidates.append(_crypto_row(file_name, row_no, executed or event["created"], ticker, "trade" if executed else "order", signed,
                                          eur=None if event["bad_amount"] else event["filled"], eur_fee=event["fee"],
                                          window_from=event["created"] if executed else None, at_last_execution=cancelled))
        elif event["eur_amount"] is not None:
            skip("crypto_fiat")
        elif kind.startswith("coin"):
            if not event["address"]:
                skip("crypto_unsupported"); continue
            candidates.append(_crypto_row(file_name, row_no, event["finished"] or event["created"], ticker, "move_unknown", event["ordered"],
                                          address=event["address"] if event["type"] == "Auszahlung" else ""))
    return {"file_name": file_name, "content": _csv([header] + rows, rng.choice(("\n", "\r\n"))),
            "expected": {"status": "multi", "candidates": candidates, "row_reasons": reasons}}


# ---------------------------------------------------------------- Export als Reward-Beleg (bsdex_transactions_csv_v1)
def _norm(text: str) -> str:
    return " ".join(text.strip().lower().replace("_", " ").split())


def _generate_reward(seed: int) -> dict[str, Any]:
    """Je Zeile ihre Zellen und Merkmale; Staking Rewards mit Coin (Name gross geschrieben), Menge, Tag und Uhrzeit in Berlin, ohne
    Bewertung (Marktdaten bewerten); Staking Reward ohne Menge oder lesbare Zeit ungueltig; alles andere "other"."""
    rng = random.Random(seed)
    file_name = f"bsdex-transaktionen-erfunden-{seed}.csv"
    events = _export_events(rng, 2, False)
    if not any(event["kind"] == "staking_reward" for event in events):
        extra = _export_events(random.Random(seed + 7_000_000), 2, False)
        reward = next((event for event in extra if event["kind"] == "staking_reward"), None)
        if reward is not None:
            events.append({**reward, "created": events[-1]["created"] + timedelta(hours=5)})
    header, rows = _export_document(rng, events, False)
    spelled = rng.random() < 0.15   # Umschrift "Kryptowaehrung" in manchen Exporten
    if spelled:
        header = ["Kryptowaehrung" if name == "Kryptowährung" else name for name in header]
    if rng.random() < 0.3:   # schmaler Export: nur die Spalten, die der Reward-Import braucht, in anderer Reihenfolge
        keep = [name for name in header if name in ("Transaktionstyp", "Kryptowährung", "Kryptowaehrung", "Betrag", "Erstellt",
                                                     "Transaktionsentgelt", "Operation Type")]
        rng.shuffle(keep)
        rows = [[row[header.index(name)] for name in keep] for row in rows]
        header = keep
    position = {name: index for index, name in enumerate(header)}
    coin_column = "Kryptowaehrung" if spelled else "Kryptowährung"
    expected_rows = []
    for event, cells in zip(events, rows):
        value = lambda name: cells[position[name]].strip() if name in position else ""
        quantity_text = value("Betrag")
        quantity = None if quantity_text in ("", NO_PRICE) else _reward_amount(quantity_text)
        fee_text = value("Transaktionsentgelt")
        fee = None if fee_text == "" else _reward_amount(fee_text)
        signature = [_norm(value("Erstellt")), _norm(value("Transaktionstyp")), "", _norm(value(coin_column)),
                     quantity if quantity is not None else _norm(quantity_text), fee if fee is not None else _norm(fee_text), ""]
        row: dict[str, Any] = {"cells": list(cells), "row_id": "", "signature": signature}
        if event["kind"] not in ("staking_reward", "reward_bad"):
            row["kind"] = "other"
        elif event["bad_created"] or quantity in (None, "0") or not value(coin_column):
            row["kind"] = "invalid"
        else:
            row.update(kind="reward", asset=value(coin_column).upper(), quantity=quantity, local_date=event["created"].date().isoformat(),
                       local_time=event["created"].strftime("%H:%M:00"), fee=None if fee in (None, "0") else fee, account="BSDEX",
                       valuation={"source_value_mode": "none", "price_currency": "EUR", "source_unit_price_decimal": None,
                                  "source_fiat_total_decimal": None})
        expected_rows.append(row)
    bom = "﻿" if rng.random() < 0.3 else ""
    return {"file_name": file_name, "content": (bom + _csv([header] + rows, rng.choice(("\n", "\r\n")))).encode("utf-8"),
            "expected": {"time_zone": "Europe/Berlin", "fee_role": "none", "rows": expected_rows}}


def _reward_amount(text: str) -> str:
    """Menge oder Entgelt des Exports ("0,00017321 ETH", "1.234,5 XRP", "0,38 €") ohne Vorzeichen, ohne Nullen am Ende."""
    number = text.replace("€", "").strip().split(" ")[0].replace(".", "").replace(",", ".")
    return _plain(abs(Decimal(number)))


GENERATORS = {"bsdex_eur_v1": _generate_eur, "bsdex_history_v1": _generate_history, "bsdex_crypto_v1": _generate_crypto,
              "bsdex_transactions_csv_v1": _generate_reward}
