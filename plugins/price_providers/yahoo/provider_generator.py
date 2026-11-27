"""Erzeuger fuer den Selbsttest (Stufe 3): erfundene Yahoo-Antworten samt erwartetem Ergebnis.

Alles ist erfunden: Symbole, Namen, Kurse und Zeiten haben mit keinem echten Papier zu tun. Die Erwartung entsteht aus den erzeugten
Werten, nicht aus dem Parser - eine Fehldeutung des Formats faengt der Erzeuger damit nicht (sie stammt vom Plugin selbst), wohl aber
Abstuerze, verlorene Tage und falsch gerundete Zahlen.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import json
import random
from zoneinfo import ZoneInfo

_ZONES = (("Europe/Berlin", "GER", "EUR", time(9, 0)), ("America/New_York", "NMS", "USD", time(9, 30)),
          ("Europe/London", "LSE", "GBP", time(8, 0)), ("Asia/Tokyo", "JPX", "JPY", time(9, 0)), ("UTC", "CCC", "USD", time(0, 0)))


def _canonical(text: str) -> str:
    value = format(Decimal(text), "f")
    value = value.rstrip("0").rstrip(".") if "." in value else value
    return "0" if value in {"", "-0"} else value


def _price(rng: random.Random) -> str:
    whole = rng.randint(0, 4999)
    digits = rng.randint(0, 6)
    fraction = "".join(str(rng.randint(0, 9)) for _ in range(digits))
    return f"{whole}.{fraction}" if fraction else str(whole)


def _history(seed: int, fx: bool) -> dict:
    rng = random.Random(seed * 7919 + (1 if fx else 0))
    zone_name, exchange, currency, opening = _ZONES[rng.randrange(len(_ZONES))]
    if fx:
        base = rng.choice(["CHF", "GBP", "JPY", "NOK", "SEK"])
        symbol = base + "EUR=X"
        currency = "EUR"
        exchange = "CCY"
    else:
        symbol = f"INV{rng.randint(10, 9999)}.{rng.choice(['DE', 'L', 'T', 'XY'])}"
    zone = ZoneInfo(zone_name)
    start = date(2027, 1, 1) + timedelta(days=rng.randint(0, 600))
    count = rng.randint(0, 9)
    end = start + timedelta(days=max(count - 1, 0) + rng.randint(0, 3))
    timestamps, rows, expected_days = [], {k: [] for k in ("open", "high", "low", "close", "volume")}, []
    adj = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        moment = datetime.combine(day, opening, tzinfo=zone)
        stamp = int(moment.timestamp())
        values = {key: (None if rng.random() < 0.12 else _price(rng)) for key in ("open", "high", "low", "close")}
        volume = None if fx or rng.random() < 0.2 else str(rng.randint(0, 10_000_000))
        adjusted = None if rng.random() < 0.3 else _price(rng)
        timestamps.append(stamp)
        for key in ("open", "high", "low", "close"):
            rows[key].append(values[key])
        rows["volume"].append(volume if not fx else 0)
        adj.append(adjusted)
        close = None if values["close"] is None else _canonical(values["close"])
        expected_days.append({
            "trading_date": day.isoformat(),
            "open_decimal": None if values["open"] is None else _canonical(values["open"]),
            "high_decimal": None if values["high"] is None else _canonical(values["high"]),
            "low_decimal": None if values["low"] is None else _canonical(values["low"]),
            "close_decimal": close,
            "adjusted_close_decimal": None if adjusted is None else _canonical(adjusted),
            "volume_decimal": ("0" if fx else (None if volume is None else _canonical(volume))),
            "day_status": "observed" if close is not None else "source_gap",
            "corporate_action_status": "none_reported",
            "observed_at_utc": datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    meta = {"currency": currency, "symbol": symbol, "exchangeName": exchange, "exchangeTimezoneName": zone_name,
            "firstTradeDate": int(datetime.combine(date(2001, 1, 2), opening, tzinfo=zone).timestamp())}
    if not fx:
        meta["longName"] = f"Invented Holding {rng.randint(1, 999)}"
        meta["instrumentType"] = rng.choice(["EQUITY", "ETF", "MUTUALFUND"])
    live_session = None
    if count and rng.random() < 0.4:
        # Ein laufender Balken am Ende: kein Tagesschluss, getrennt ausgewiesen.
        live_day = end + timedelta(days=1)
        live_stamp = int(datetime.combine(live_day, opening, tzinfo=zone).timestamp()) + 3600
        live_close = _price(rng)
        timestamps.append(live_stamp)
        for key in ("open", "high", "low"):
            rows[key].append(None)
        rows["close"].append(live_close)
        rows["volume"].append(0 if fx else None)
        adj.append(None)
        meta["regularMarketTime"] = live_stamp
        live_session = {"trading_date": live_day.isoformat(), "close_decimal": _canonical(live_close),
                        "observed_at_utc": datetime.fromtimestamp(live_stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "session_complete": False}
    result_body = {"meta": meta, "timestamp": timestamps,
                   "indicators": {"quote": [{key: rows[key] for key in ("open", "high", "low", "close", "volume")}], "adjclose": [{"adjclose": adj}]}}
    # Zahlen als Text im JSON: so tragen sie genau die erzeugten Stellen.
    body = json.dumps({"chart": {"result": [result_body], "error": None}})
    for key in ("open", "high", "low", "close"):
        for value in rows[key]:
            if value is not None:
                body = body.replace(json.dumps(value), value, 1)
    for value in adj:
        if value is not None:
            body = body.replace(json.dumps(value), value, 1)
    if not fx:
        for value in rows["volume"]:
            if value is not None:
                body = body.replace(json.dumps(value), value, 1)
    params = {"provider_symbol": symbol, "start_date": start.isoformat(), "end_date": end.isoformat()}
    result = {"provider_symbol": symbol, "provider_currency": currency, "exchange": exchange, "timezone_name": zone_name,
              "split_review_required": False, "days": expected_days, "live_session": live_session}
    if not fx:
        result |= {"instrument_name": meta["longName"], "instrument_type": meta["instrumentType"],
                   "first_trade_date": date(2001, 1, 2).isoformat()}
    return {"params": params, "response": {"status": 200, "content_type": "application/json", "body_text": body},
            "expected": {"outcome": "ok", "result": result}}


def _search(seed: int) -> dict:
    rng = random.Random(seed * 104729)
    count = rng.randint(0, 12)
    quotes, expected, seen = [], [], set()
    types = {"EQUITY": "equity", "ETF": "etf", "MUTUALFUND": "fund", "CRYPTOCURRENCY": "cryptocurrency", "WARRANT": "other"}
    for index in range(count):
        symbol = f"INV{rng.randint(1, 60)}"
        exchange = rng.choice(["GER", "NMS", "LSE"])
        raw_type = rng.choice(list(types))
        currency = rng.choice(["EUR", "USD", "eur", None])
        quotes.append({"symbol": symbol, "longname": f"Invented Search {index}", "exchDisp": exchange, "quoteType": raw_type, "currency": currency})
        if len(expected) >= 10 or (symbol, exchange) in seen:
            continue
        seen.add((symbol, exchange))
        expected.append({"symbol": symbol, "display_name": f"Invented Search {index}", "exchange": exchange, "quote_type": types[raw_type],
                         "quote_currency": currency if currency in {"EUR", "USD"} else None})
    return {"params": {"query": "Invented", "limit": 10},
            "response": {"status": 200, "content_type": "application/json", "body_text": json.dumps({"quotes": quotes})},
            "expected": {"outcome": "ok", "candidates": expected}}


def generate(operation: str, seed: int) -> dict:
    if operation == "daily_history":
        return _history(seed, fx=False)
    if operation == "fx_daily_history":
        return _history(seed, fx=True)
    if operation == "search":
        return _search(seed)
    raise ValueError(operation)
