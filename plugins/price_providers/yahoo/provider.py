"""Yahoo Finance als Kursanbieter-Plugin (price_provider_v1, #495, rc.382).

Das Plugin ruft nie selbst ab: Es baut die Anfrage, der Kern ruft ab (nur an die Hosts aus dem Manifest), das Plugin liest die
Antwort. Die Auswertungen stammen unveraendert aus dem Kern (bis rc.381 in desktop_provider_probe_v1, desktop_fx_pair_probe_v1,
desktop_provider_search_v1, desktop_intraday_snapshot_v1 und desktop_market_history_review_v1); jede Abweichung waere eine
Verhaltensaenderung und faellt in der Gegenprobe gegen die gespeicherten Antworten auf.

Ausgaenge je Antwort: ``ok`` (mit Ergebnis), ``rejected`` (die Quelle bremst), ``not_listed`` (vor der Erstnotiz),
``invalid`` (kaputte oder unerwartete Antwort), bei Kursen der laufenden Sitzung zusaetzlich ``no_observation``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HOST = "query1.finance.yahoo.com"
CHART_PATH = "/v8/finance/chart/"
SEARCH_PATH = "/v1/finance/search"
_QUOTE_TYPES = {"CRYPTOCURRENCY": "cryptocurrency", "CURRENCY": "currency", "EQUITY": "equity", "ETF": "etf", "FUTURE": "future",
                "INDEX": "index", "MUTUALFUND": "fund", "OPTION": "option"}


class _Invalid(Exception):
    def __init__(self, detail: str = "value"):
        self.detail = detail
        super().__init__(detail)


def _abort(detail: str = "value"):
    raise _Invalid(detail)


# ---------------------------------------------------------------------------------------------------------------------------
# Anfragen
# ---------------------------------------------------------------------------------------------------------------------------

def _chart_target(symbol: str, first_day: str, end_day: str) -> str:
    first = date.fromisoformat(first_day)
    end = date.fromisoformat(end_day)
    period1 = int(datetime.combine(first, datetime.min.time(), tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp())
    return CHART_PATH + quote(symbol, safe="") + "?" + urlencode(
        {"period1": str(period1), "period2": str(period2), "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"})


def build_request(operation: str, params: dict) -> dict:
    if operation in ("daily_history", "fx_daily_history"):
        # request_start_date darf vor start_date liegen: Der Kern weitet ein Ein-Tages-Fenster auf (Yahoo liefert sonst null
        # Balken, 23.09.2026); ausgewertet wird nur start_date..end_date.
        return {"host": HOST, "target": _chart_target(params["provider_symbol"], params["request_start_date"], params["end_date"])}
    if operation == "quote":
        target = CHART_PATH + params["provider_symbol"].replace("/", "%2F") + "?range=1d&interval=1d&events=div,splits&includeAdjustedClose=true"
        return {"host": HOST, "target": target}
    if operation == "search":
        query = urlencode({"q": params["query"], "quotesCount": str(params["limit"]), "newsCount": "0", "listsCount": "0",
                           "enableFuzzyQuery": "false", "region": "US", "lang": "en-US"})
        return {"host": HOST, "target": SEARCH_PATH + "?" + query}
    raise ValueError(operation)


def fx_symbol(base_currency: str, quote_currency: str) -> dict:
    return {"symbol": base_currency + quote_currency + "=X"}


# ---------------------------------------------------------------------------------------------------------------------------
# Antworten
# ---------------------------------------------------------------------------------------------------------------------------

def parse_response(operation: str, params: dict, response: dict) -> dict:
    if operation == "daily_history":
        return _daily(params, response)
    if operation == "fx_daily_history":
        try:
            return {"outcome": "ok", "result": _parse_fx_response(response["body"], params)}
        except _Invalid as error:
            return {"outcome": "invalid", "detail": error.detail}
        except Exception:  # noqa: BLE001 - wie bisher: jede andere Abweichung ist eine ungueltige Antwort
            return {"outcome": "invalid", "detail": "value"}
    if operation == "quote":
        return _quote(params, response)
    if operation == "search":
        try:
            return {"outcome": "ok", "candidates": _normalize_quotes(response["body"], int(params["limit"]))}
        except Exception:  # noqa: BLE001
            return {"outcome": "invalid"}
    raise ValueError(operation)


def _before_first_notation(body) -> bool:
    if not isinstance(body, bytes) or len(body) > 8192:
        return False
    try:
        envelope = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return False
    chart = envelope.get("chart") if isinstance(envelope, dict) else None
    error_body = chart.get("error") if isinstance(chart, dict) else None
    description = error_body.get("description") if isinstance(error_body, dict) else None
    return isinstance(description, str) and description.startswith("Data doesn't exist for startDate")


def _daily(params: dict, response: dict) -> dict:
    status = response["status"]
    body = response["body"]
    content_type = response.get("content_type")
    if status in (429, 503):
        return {"outcome": "rejected"}
    # Liegt das angefragte Fenster vollstaendig vor der Erstnotiz, antwortet Yahoo mit HTTP 400 und "Data doesn't exist for
    # startDate". Das ist keine Stoerung, sondern eine Auskunft: Der Titel war an diesen Tagen nicht notiert. Es gelingt jedes Fenster, das die Erstnotiz ueberlappt - nur die vollstaendig davor
    # liegenden werden abgewiesen (#283).
    if status == 400 and _before_first_notation(body):
        return {"outcome": "not_listed"}
    if status != 200 or not isinstance(content_type, str) or not content_type.lower().startswith("application/json"):
        return {"outcome": "invalid"}
    # Die Quelle weist einen Abruf auch mit HTTP 200 ab und legt den Grund in den Koerper. Das sah aus wie eine ungueltige
    # Antwort, obwohl es eine Drosselung war.
    try:
        envelope = json.loads(body.decode("utf-8"))
    except Exception:  # noqa: BLE001
        envelope = None
    if isinstance(envelope, dict):
        chart = envelope.get("chart")
        error_body = chart.get("error") if isinstance(chart, dict) else None
        if error_body is not None or (chart is None and envelope.get("finance")):
            return {"outcome": "rejected"}
    try:
        return {"outcome": "ok", "result": _parse_chart(body, params)}
    except Exception:  # noqa: BLE001
        return {"outcome": "invalid"}


def _text(value, maximum=160):
    if not isinstance(value, str) or value != value.strip() or not 1 <= len(value) <= maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        _abort()
    return value


def _date(value):
    if not isinstance(value, str) or re.fullmatch(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", value) is None:
        _abort("input")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _abort("input")
    if parsed.isoformat() != value:
        _abort("input")
    return parsed


def _decimal(value, nullable=True):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, (Decimal, int)):
        _abort()
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError):
        _abort()
    if not decimal.is_finite():
        _abort()
    decimal_tuple = decimal.as_tuple()
    if len(decimal_tuple.digits) > 80 or abs(decimal_tuple.exponent) > 80 or (decimal and not -79 <= decimal.adjusted() <= 79):
        _abort()
    text = format(decimal, "f")
    text = text.rstrip("0").rstrip(".") if "." in text else text
    if text in {"", "-0"}:
        text = "0"
    if len(text) > 80 or re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?", text) is None:
        _abort()
    return text


def _response_json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _abort()
        value[key] = item
    return value


def _response_json_constant(value):
    _abort()


def _parse_chart(body, params):
    """Tagesbalken einer Antwort von /v8/finance/chart (bis rc.381 desktop_provider_probe_v1._parse_response)."""
    try:
        value = json.loads(body.decode("utf-8"), parse_float=Decimal, parse_int=Decimal, parse_constant=_response_json_constant,
                           object_pairs_hook=_response_json_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        _abort()
    chart = value.get("chart") if isinstance(value, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(chart, dict) or chart.get("error") is not None or not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        _abort()
    result = results[0]
    meta = result.get("meta")
    timestamps = result.get("timestamp")
    indicators = result.get("indicators")
    # Hat die Notierung im angefragten Fenster nicht gehandelt, laesst die Quelle 'timestamp' ganz weg und liefert leere
    # Kursfelder. Das ist eine gueltige Auskunft - keine Handelstage -, keine kaputte Antwort. Bei einer duenn gehandelten
    # Notierung blockierte die Abweisung den Titel dauerhaft; die Tage gehoeren als Quellluecke erfasst
    # (#283).
    if timestamps is None and isinstance(indicators, dict):
        timestamps = []
    if not isinstance(meta, dict) or not isinstance(timestamps, list) or not isinstance(indicators, dict):
        _abort()
    symbol = _text(meta.get("symbol"), 120)
    currency = _text(meta.get("currency"), 3)
    timezone_name = _text(meta.get("exchangeTimezoneName"), 64)
    exchange = _text(meta.get("exchangeName") or meta.get("fullExchangeName") or "UNKNOWN", 80)

    # Der Name und die Gattung der Quelle machen eine Verwechslung sichtbar: Ein Zertifikat auf eine Aktie traegt deren Namen,
    # ist aber ein anderes Papier.
    def _optional(item, maximum):
        return _text(item, maximum) if isinstance(item, str) and item.strip() else ""

    instrument_name = _optional(meta.get("longName") or meta.get("shortName"), 160)
    instrument_type = _optional(meta.get("instrumentType"), 40)
    # Die Quelle antwortet auf USDEUR=X auch mit ihrer Kurzform EUR=X; das ist dasselbe Paar. Jede andere Abweichung bleibt ein
    # Fehler.
    requested = params["provider_symbol"]
    aliased = symbol != requested and requested.endswith("=X") and symbol.endswith("=X") and requested == "USD" + symbol
    if (symbol != requested and not aliased) or re.fullmatch(r"[A-Z]{3}", currency) is None:
        _abort()
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        _abort()
    quotes = indicators.get("quote")
    adjusted = indicators.get("adjclose", [])
    if not isinstance(quotes, list) or len(quotes) != 1 or not isinstance(quotes[0], dict) or adjusted and (
            not isinstance(adjusted, list) or len(adjusted) != 1 or not isinstance(adjusted[0], dict)):
        _abort()
    quote_row = quotes[0]

    # Ohne Balken fehlen auch die Kursfelder; mit Balken bleibt ihr Fehlen ein Fehler.
    def _series(item):
        return [] if item is None and not timestamps else item

    fields = {key: _series(quote_row.get(key)) for key in ("open", "high", "low", "close", "volume")}
    adj_values = _series(adjusted[0].get("adjclose")) if adjusted else [None] * len(timestamps)
    if any(not isinstance(values, list) or len(values) != len(timestamps) for values in fields.values()) or not isinstance(adj_values, list) \
            or len(adj_values) != len(timestamps):
        _abort()
    split_events = result.get("events", {}).get("splits", {}) if isinstance(result.get("events", {}), dict) else {}
    if not isinstance(split_events, dict):
        _abort()
    split_review = bool(split_events)
    start = _date(params["start_date"])
    end = _date(params["end_date"])
    days = []
    seen = set()
    # Die Antwort traegt neben den abgeschlossenen Tagesbalken auch den laufenden Balken der offenen Sitzung; er ist an
    # regularMarketTime erkennbar. In der Boersenzeitzone faellt er auf denselben Handelstag wie der fertige Balken, und die
    # Dublettenpruefung verwarf die ganze Antwort. Ein laufender Balken ist kein Tagesschluss und wird uebergangen, nicht
    # uebernommen (22.09.2026, #283).
    # Die Quelle nennt die Erstnotiz in jeder Antwort. Ohne sie plant das Produkt Zeitraeume, die es nicht geben kann: Ein Abruf
    # ab 2019 fuer ein Papier mit Erstnotiz 2021 wird mit HTTP 400 "Data doesn't exist" abgewiesen und sah aus wie ein falsches
    # Symbol (Befund 25.09.2026, #283).
    raw_first = meta.get("firstTradeDate")
    first_trade_date = None
    if not isinstance(raw_first, bool) and isinstance(raw_first, (int, Decimal)):
        try:
            first_trade_date = datetime.fromtimestamp(int(raw_first), tz=zone).date().isoformat()
        except (OverflowError, OSError, ValueError):
            first_trade_date = None
    live = meta.get("regularMarketTime")
    live = Decimal(live) if not isinstance(live, bool) and isinstance(live, (Decimal, int)) else None
    live_session = None
    for index, raw_timestamp in enumerate(timestamps):
        timestamp = Decimal(raw_timestamp) if not isinstance(raw_timestamp, bool) and isinstance(raw_timestamp, (Decimal, int)) else None
        if timestamp is None or not timestamp.is_finite() or timestamp != timestamp.to_integral_value() or timestamp < Decimal("-62135596800") \
                or timestamp > Decimal("253402300799"):
            _abort()
        try:
            raw_observed = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            trading = raw_observed.astimezone(zone).date()
        except (OverflowError, OSError, ValueError):
            _abort()
        if timestamp == live:
            # Nicht verwerfen, nur trennen: Der Zwischenstand ist kein Tagesschluss, taugt aber spaeter als tagesfrischer Wert
            # fuer einen Snapshot (Festlegung 22.09.2026).
            live_session = {"trading_date": trading.isoformat(), "close_decimal": _decimal(fields["close"][index]),
                            "observed_at_utc": raw_observed.strftime("%Y-%m-%dT%H:%M:%SZ"), "session_complete": False}
            continue
        if trading < start or trading > end:
            continue
        trading_text = trading.isoformat()
        if trading_text in seen:
            _abort()
        seen.add(trading_text)
        close = _decimal(fields["close"][index])
        days.append({"trading_date": trading_text, "open_decimal": _decimal(fields["open"][index]), "high_decimal": _decimal(fields["high"][index]),
                     "low_decimal": _decimal(fields["low"][index]), "close_decimal": close, "adjusted_close_decimal": _decimal(adj_values[index]),
                     "volume_decimal": _decimal(fields["volume"][index]), "day_status": "observed" if close is not None else "source_gap",
                     "corporate_action_status": "pending_review" if split_review else "none_reported",
                     "observed_at_utc": raw_observed.strftime("%Y-%m-%dT%H:%M:%SZ")})
    days.sort(key=lambda row: row["trading_date"])
    return {"provider_symbol": symbol, "provider_currency": currency, "exchange": exchange, "timezone_name": timezone_name,
            "instrument_name": instrument_name, "instrument_type": instrument_type, "split_review_required": split_review, "days": days,
            "live_session": live_session, "first_trade_date": first_trade_date}


# Waehrungspaare (bis rc.381 desktop_fx_pair_probe_v1._parse_fx_response): eigene, aeltere Auswertung mit feineren Gruenden.

def _fx_decimal(v):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (Decimal, int)):
        _abort("value")
    d = Decimal(v)
    if not d.is_finite():
        _abort("value")
    text = format(d, "f")
    text = text.rstrip("0").rstrip(".") if "." in text else text
    return "0" if text in {"", "-0"} else text


def _fx_object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            _abort("value")
        out[key] = value
    return out


def _symbol_matches(returned, requested):
    """Die Quelle antwortet auf USDEUR=X auch mit ihrer Kurzform EUR=X: Bei US-Dollar als Basis laesst sie die Basis weg. Das ist
    dasselbe Paar, nicht eine andere Notierung. Jede andere Abweichung bleibt ein Identitaetsfehler; die Waehrung wird ohnehin
    getrennt geprueft."""
    if not isinstance(returned, str) or not isinstance(requested, str):
        return False
    if returned == requested:
        return True
    return requested.endswith("=X") and returned.endswith("=X") and requested == "USD" + returned


def _parse_fx_response(body, params):
    try:
        value = json.loads(body.decode("utf-8"), parse_float=Decimal, parse_int=Decimal, parse_constant=lambda _: _abort("value"),
                           object_pairs_hook=_fx_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        _abort("json")
    chart = value.get("chart") if isinstance(value, dict) else None
    results = chart.get("result") if isinstance(chart, dict) else None
    if not isinstance(chart, dict) or chart.get("error") is not None or not isinstance(results, list) or len(results) != 1 or not isinstance(results[0], dict):
        _abort("shape")
    result = results[0]
    meta = result.get("meta")
    timestamps = result.get("timestamp")
    indicators = result.get("indicators")
    if not isinstance(meta, dict) or not isinstance(timestamps, list) or not isinstance(indicators, dict):
        _abort("shape")
    if not _symbol_matches(meta.get("symbol"), params["provider_symbol"]):
        _abort("identity")
    currency = meta.get("currency")
    zone_name = meta.get("exchangeTimezoneName")
    exchange = meta.get("exchangeName") or meta.get("fullExchangeName") or "UNKNOWN"
    if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None or not isinstance(zone_name, str) or not isinstance(exchange, str):
        _abort("identity")
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        _abort("identity")
    quotes = indicators.get("quote")
    quote_row = quotes[0] if isinstance(quotes, list) and len(quotes) == 1 and isinstance(quotes[0], dict) else None
    if quote_row is None or not isinstance(quote_row.get("close"), list) or len(quote_row["close"]) != len(timestamps):
        _abort("series")
    series = {}
    n = len(timestamps)
    for key in ("open", "high", "low", "close", "volume"):
        values = quote_row.get(key)
        if values is None and key != "close":
            values = [None] * n
        if not isinstance(values, list) or len(values) != n:
            _abort("series")
        series[key] = values
    adjusted = indicators.get("adjclose")
    adj = adjusted[0].get("adjclose") if isinstance(adjusted, list) and len(adjusted) == 1 and isinstance(adjusted[0], dict) else [None] * n
    if not isinstance(adj, list) or len(adj) != n:
        _abort("series")
    start = _date(params["start_date"])
    end = _date(params["end_date"])
    days = []
    seen = set()
    live_session = None
    # Wie im gemeinsamen Parser: Der laufende Balken der offenen Sitzung faellt in der Boersenzeitzone auf denselben Handelstag
    # wie der fertige und verwarf die ganze Antwort. Er ist kein Tagesschluss, bleibt aber getrennt lesbar.
    live = meta.get("regularMarketTime")
    live = Decimal(live) if not isinstance(live, bool) and isinstance(live, (Decimal, int)) else None
    for i, raw in enumerate(timestamps):
        if isinstance(raw, bool) or not isinstance(raw, (Decimal, int)) or Decimal(raw) != Decimal(raw).to_integral_value():
            _abort("series")
        try:
            observed = datetime.fromtimestamp(int(raw), tz=timezone.utc)
            day = observed.astimezone(zone).date()
        except (OverflowError, OSError, ValueError):
            _abort("series")
        if live is not None and Decimal(raw) == live:
            live_session = {"trading_date": day.isoformat(), "close_decimal": _fx_decimal(series["close"][i]),
                            "observed_at_utc": observed.strftime("%Y-%m-%dT%H:%M:%SZ"), "session_complete": False}
            continue
        if day < start or day > end:
            continue
        ds = day.isoformat()
        if ds in seen:
            _abort("series")
        seen.add(ds)
        close = _fx_decimal(series["close"][i])
        vals = {key: _fx_decimal(series[key][i]) for key in series}
        days.append({"trading_date": ds, "open_decimal": vals["open"], "high_decimal": vals["high"], "low_decimal": vals["low"], "close_decimal": close,
                     "adjusted_close_decimal": _fx_decimal(adj[i]), "volume_decimal": vals["volume"],
                     "day_status": "observed" if close is not None else "source_gap", "corporate_action_status": "none_reported",
                     "observed_at_utc": observed.strftime("%Y-%m-%dT%H:%M:%SZ")})
    return {"provider_symbol": meta["symbol"], "provider_currency": currency, "exchange": exchange, "timezone_name": zone_name,
            "split_review_required": False, "days": sorted(days, key=lambda x: x["trading_date"]), "live_session": live_session}


# Kurs der laufenden Sitzung (bis rc.381 desktop_intraday_snapshot_v1._quote/_quote_from_meta).

def _quote_from_meta(body) -> dict:
    """Der Kurs aus den Kopfdaten der Antwort - kein Tagesschluss, ein Zwischenstand."""
    try:
        # Wie im Antwortparser: Zahlen exakt aus dem Text, nicht ueber Fliesskomma.
        meta = json.loads(body.decode("utf-8"), parse_float=Decimal, parse_int=Decimal)["chart"]["result"][0]["meta"]
        price = meta.get("regularMarketPrice")
        moment = meta.get("regularMarketTime")
        currency = meta.get("currency")
    except Exception:  # noqa: BLE001
        return {"outcome": "invalid"}
    if isinstance(price, bool) or not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        return {"outcome": "no_observation"}
    if isinstance(moment, bool) or not isinstance(moment, Decimal) or moment != moment.to_integral_value():
        return {"outcome": "no_observation"}
    moment = int(moment)
    if not isinstance(currency, str) or len(currency) != 3:
        return {"outcome": "invalid"}
    observed = datetime.fromtimestamp(moment, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"outcome": "ok", "quote": {"kind": "meta_quote", "decimal": str(price), "observed_at_utc": observed, "currency": currency,
                                       "as_of_date": observed[:10]}}


def _quote(params: dict, response: dict) -> dict:
    """Ein Kurs der laufenden Sitzung, sonst der juengste Tagesbalken der Antwort."""
    body = response["body"]
    try:
        parsed = _parse_chart(body, {"provider_symbol": params["provider_symbol"], "start_date": "1970-01-01", "end_date": params["end_date"]})
    except Exception:  # noqa: BLE001
        # Eine duenn gehandelte Notierung hat im Tagesfenster womoeglich keinen Balken - ihren Kurs traegt die Antwort dann nur in
        # den Kopfdaten. Fuer einen Zwischenstand genuegt das; fuer die Tageshistorie ausdruecklich nicht, dort bleibt ein
        # beobachteter Balken die Grundlage (etwa HTTP 200 mit null Balken und Kurs im Kopf).
        return _quote_from_meta(body)
    live = parsed.get("live_session")
    if isinstance(live, dict) and live.get("close_decimal") is not None:
        return {"outcome": "ok", "quote": {"kind": "live_session", "decimal": str(live["close_decimal"]), "observed_at_utc": str(live["observed_at_utc"]),
                                           "currency": parsed["provider_currency"], "as_of_date": str(live["observed_at_utc"])[:10]}}
    days = [row for row in parsed["days"] if row["day_status"] == "observed" and row["close_decimal"] is not None]
    if not days:
        return {"outcome": "no_observation"}
    latest = days[-1]
    return {"outcome": "ok", "quote": {"kind": "closing_bar", "decimal": str(latest["close_decimal"]), "observed_at_utc": str(latest["observed_at_utc"]),
                                       "currency": parsed["provider_currency"], "as_of_date": latest["trading_date"]}}


# Suche (bis rc.381 desktop_provider_search_v1._normalize_quotes); die Pruefsumme je Vorschlag bildet der Kern.

def _provided_isin(value):
    # Provider metadata is only a proposal. No symbol lookup or inferred identifier.
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value) is None:
        return None
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    total = sum((int(c) * 2 // 10 + int(c) * 2 % 10) if i % 2 else int(c) for i, c in enumerate(reversed(digits)))
    return value if total % 10 == 0 else None


def _normalize_quotes(payload, result_limit):
    value = json.loads(payload.decode("utf-8"))
    raw = value.get("quotes") if isinstance(value, dict) else None
    if not isinstance(raw, list):
        _abort()
    rows = []
    seen = set()
    for item in raw:
        if len(rows) >= result_limit:
            break
        if not isinstance(item, dict):
            _abort()
        symbol = item.get("symbol")
        if not isinstance(symbol, str) or not symbol.strip() or len(symbol.strip()) > 80:
            continue
        symbol = symbol.strip()
        display = item.get("longname") or item.get("shortname") or symbol
        exchange = item.get("exchDisp") or item.get("fullExchangeName") or item.get("exchange") or "exchange_unknown"
        display = _text(display.strip(), 120)
        exchange = _text(exchange.strip(), 80)
        key = (symbol, exchange)
        if key in seen:
            continue
        seen.add(key)
        raw_type = item.get("quoteType")
        quote_type = _QUOTE_TYPES.get(raw_type.strip().upper() if isinstance(raw_type, str) else "", "other")
        raw_currency = item.get("currency")
        currency = raw_currency.strip() if isinstance(raw_currency, str) and re.fullmatch(r"[A-Z]{3}", raw_currency.strip()) else None
        projection = {"symbol": symbol, "display_name": display, "exchange": exchange, "quote_type": quote_type, "quote_currency": currency}
        isin = _provided_isin(item.get("isin"))
        if isin is not None:
            projection["isin"] = isin
        rows.append(projection)
    return rows


def generate(operation: str, seed: int) -> dict:
    """Selbsttest Stufe 3: eine erfundene Antwort samt erwartetem Ergebnis (provider_generator.py)."""
    from provider_generator import generate as _generate  # noqa: PLC0415 - Modul neben dem Einstieg
    return _generate(operation, seed)
