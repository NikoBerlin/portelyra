"""EODHD als Kursanbieter-Plugin: Suche nach Name, Kuerzel oder ISIN (#495, rc.392) und Tageskurse (``daily_history``).

Festlegung (10.11.2026): Bei der Anlage eines Assets in den Stammdaten den Namen eingeben und die ISIN vorgeschlagen
bekommen, wenn sie nicht ueber einen Import kommt. Das ist ein Zusatz: Ohne dieses Plugin funktioniert die Stammdaten-Eingabe mit der
Yahoo-Suche wie bisher. EODHD braucht einen (kostenlosen) Schluessel; jede Suche und jeder Kursabruf kostet einen von 20 Abrufen am
Tag. Mit ``daily_history`` kann EODHD zweiter Anbieter fuer Kurshistorie sein (kostenlos nur etwa ein Jahr Tiefe).

Das Plugin ruft nie selbst ab und sieht den Schluessel nie: Es baut die Anfrage ohne ihn, der Kern setzt ihn als Parameter
``api_token`` ein (Manifest), ruft ab und entfernt ihn aus der Antwort. Eine ISIN steht nur im Vorschlag, wenn EODHD sie liefert
und sie formal gueltig ist (Pruefziffer); sie ist ein Vorschlag, keine gepruefte Stammangabe.

Tageskurse: Die Antwort von ``/api/eod`` nennt weder Waehrung noch Zeitzone. Beides steht deshalb in einer festen Tabelle je
Boersenkuerzel (Teil nach dem letzten Punkt des Symbols), nur fuer eindeutige Faelle. Eine Boerse ausserhalb der Tabelle baut keine
Anfrage (kein Abruf, kein verbrauchtes Kontingent) und liest keine Antwort (``invalid``).
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
import json
import re
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

HOST = "eodhd.com"
SEARCH_PATH = "/api/search/"
EOD_PATH = "/api/eod/"
# EODHD-Arten (Feld "Type") auf die Arten des Kerns; Unbekanntes wird "other".
_TYPES = {"common stock": "equity", "preferred stock": "equity", "etf": "etf", "fund": "fund", "mutual fund": "fund", "index": "index",
          "currency": "currency", "crypto": "cryptocurrency", "cryptocurrency": "cryptocurrency", "bond": "other", "etc": "etf", "etn": "etf"}

# Boersenkuerzel -> (Handelswaehrung, Zeitzone). Nur Boersen, an denen in einer Waehrung gehandelt wird; die Zeitzonen sind dieselben
# IANA-Namen, die Yahoo fuer diese Boersen meldet, damit eine Notierung beim Anbieterwechsel dieselbe Zeitzone behaelt.
# Bewusst nicht aufgenommen: London (LSE: Pence oder Pfund, je Linie verschieden), Krypto (CC) und Devisen (FOREX).
# Fonds (EUFUND): EODHD fuehrt sie als virtuelle Boerse in EUR. Ein Ausgabetag ist ein Kalendertag; die Fondsstandorte der
# Eurozone liegen in MEZ, und Europe/Berlin ist die Zeitzone der deutschen Fondsnotierungen bei Yahoo.
_EXCHANGES = {
    "XETRA": ("EUR", "Europe/Berlin"), "F": ("EUR", "Europe/Berlin"), "STU": ("EUR", "Europe/Berlin"), "BE": ("EUR", "Europe/Berlin"),
    "MU": ("EUR", "Europe/Berlin"), "HM": ("EUR", "Europe/Berlin"), "DU": ("EUR", "Europe/Berlin"), "HA": ("EUR", "Europe/Berlin"),
    "US": ("USD", "America/New_York"),
    "PA": ("EUR", "Europe/Paris"), "AS": ("EUR", "Europe/Amsterdam"), "BR": ("EUR", "Europe/Brussels"), "LS": ("EUR", "Europe/Lisbon"),
    "MI": ("EUR", "Europe/Rome"), "MC": ("EUR", "Europe/Madrid"), "VI": ("EUR", "Europe/Vienna"),
    "SW": ("CHF", "Europe/Zurich"),
    "EUFUND": ("EUR", "Europe/Berlin"),
}
# Die Antwort traegt nur das Datum. Als Zeitpunkt gilt 12:00 Ortszeit der Boerse (wie die Ordnungszeit der Devisen-Belege): Der
# Zeitpunkt faellt in der Boersenzeitzone sicher auf den Handelstag, und sein UTC-Datum ist fuer alle Boersen der Tabelle derselbe Tag.
_ORDER_TIME = time(12, 0)


class _Invalid(Exception):
    pass


def _abort():
    raise _Invalid()


# ---------------------------------------------------------------------------------------------------------------------------
# Anfragen
# ---------------------------------------------------------------------------------------------------------------------------

def _exchange(symbol) -> str | None:
    """Das Boersenkuerzel eines Symbols wie ``SAP.XETRA``, wenn die Boerse in der Tabelle steht."""
    if not isinstance(symbol, str) or symbol != symbol.strip() or not 3 <= len(symbol) <= 120 or "." not in symbol \
            or any(ord(c) < 33 or ord(c) == 127 for c in symbol):
        return None
    code, exchange = symbol.rsplit(".", 1)
    return exchange if code and exchange in _EXCHANGES else None


def _iso_day(value) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None or date.fromisoformat(value).isoformat() != value:
        raise ValueError("date")
    return value


def build_request(operation: str, params: dict) -> dict:
    if operation == "daily_history":
        symbol = params["provider_symbol"]
        if _exchange(symbol) is None:
            # Ohne Waehrung und Zeitzone laesst sich die Antwort nicht lesen; der Abruf wuerde nur Kontingent kosten.
            raise ValueError("exchange_unsupported")
        # request_start_date darf vor start_date liegen (der Kern weitet ein kurzes Fenster auf); ausgewertet wird start_date..end_date.
        first = _iso_day(params.get("request_start_date") or params["start_date"])
        query = urlencode({"from": first, "to": _iso_day(params["end_date"]), "period": "d", "fmt": "json"})
        return {"host": HOST, "target": EOD_PATH + quote(symbol, safe="") + "?" + query}
    if operation == "search":
        limit = max(1, min(int(params["limit"]), 50))
        return {"host": HOST, "target": SEARCH_PATH + quote(str(params["query"]), safe="") + "?" + urlencode({"limit": str(limit), "fmt": "json"})}
    if operation == "credential_check":
        # Eine kleine Suche: angenommen, wenn EODHD mit 200 antwortet. Kostet einen Abruf.
        return {"host": HOST, "target": SEARCH_PATH + "AAPL?" + urlencode({"limit": "1", "fmt": "json"})}
    raise ValueError(operation)


# ---------------------------------------------------------------------------------------------------------------------------
# Antworten
# ---------------------------------------------------------------------------------------------------------------------------

def _json_content(response: dict) -> bool:
    content_type = response.get("content_type")
    return response.get("status") == 200 and isinstance(content_type, str) and content_type.lower().startswith("application/json")


def parse_response(operation: str, params: dict, response: dict) -> dict:
    if operation == "daily_history":
        return _daily(params, response)
    if operation == "credential_check":
        status = response.get("status")
        if status == 200:
            return {"outcome": "accepted"}
        return {"outcome": "rejected" if status in (401, 403) else "invalid"}
    if operation == "search":
        try:
            if not _json_content(response):
                return {"outcome": "invalid"}
            return {"outcome": "ok", "candidates": _candidates(response["body"], int(params["limit"]))}
        except Exception:  # noqa: BLE001 - jede Abweichung ist eine ungueltige Antwort
            return {"outcome": "invalid"}
    raise ValueError(operation)


def _daily(params: dict, response: dict) -> dict:
    """Ausgaenge (Begruendung im README):
    - 401/403: ``rejected``. EODHD antwortet mit 403 "Forbidden" sowohl auf einen ungueltigen Schluessel als auch auf ein Symbol, das
      der Schluessel nicht abrufen darf; beides ist aus der Antwort nicht zu unterscheiden. Die Quelle hat abgewiesen - mehr ist nicht
      bekannt.
    - 402/429 (Kontingent erschoepft, zu viele Abrufe): ``rejected``.
    - 404 (unbekanntes Symbol) und eine Boerse ausserhalb der Tabelle: ``invalid``. ``not_listed`` heisst im Kern "vor der
      Erstnotiz"; der Lauf uebergeht ein solches Fenster als Auskunft. Fuer ein unbekanntes Symbol waere das falsch und still.
    - jeder andere Status, kein JSON, falsche Form, ungueltige Zahl: ``invalid``.
    """
    if _exchange(params.get("provider_symbol")) is None:
        return {"outcome": "invalid"}
    status = response.get("status")
    if status in (401, 402, 403, 429):
        return {"outcome": "rejected"}
    if not _json_content(response):
        return {"outcome": "invalid"}
    try:
        return {"outcome": "ok", "result": _parse_eod(response["body"], params)}
    except Exception:  # noqa: BLE001 - jede Abweichung ist eine ungueltige Antwort
        return {"outcome": "invalid"}


def _json_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _abort()
        value[key] = item
    return value


def _json_constant(_value):
    _abort()


def _number(value, *, integral: bool = False):
    """Exakter Dezimaltext einer JSON-Zahl (nie ueber Fliesskomma), nicht negativ; ``None`` bleibt ``None``."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        _abort()
    if integral and value != value.to_integral_value():
        _abort()
    digits = value.as_tuple()
    if len(digits.digits) > 80 or abs(digits.exponent) > 80 or (value and not -79 <= value.adjusted() <= 79):
        _abort()
    text = format(value, "f")
    text = text.rstrip("0").rstrip(".") if "." in text else text
    if text in {"", "-0"}:
        text = "0"
    if len(text) > 80 or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?", text) is None:
        _abort()
    return text


def _day(value) -> date:
    try:
        return date.fromisoformat(_iso_day(value))
    except ValueError:
        _abort()


def _parse_eod(body: bytes, params: dict) -> dict:
    """Tagesbalken einer Antwort von /api/eod: eine Liste von Tagen mit date, open, high, low, close, adjusted_close, volume."""
    symbol = params["provider_symbol"]
    exchange = _exchange(symbol)
    currency, zone_name = _EXCHANGES[exchange]
    zone = ZoneInfo(zone_name)
    try:
        value = json.loads(body.decode("utf-8"), parse_float=Decimal, parse_int=Decimal, parse_constant=_json_constant,
                           object_pairs_hook=_json_object)
    except (UnicodeDecodeError, ValueError, RecursionError, InvalidOperation):
        _abort()
    if not isinstance(value, list):
        _abort()
    start = _day(params["start_date"])
    end = _day(params["end_date"])
    days, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            _abort()
        # Vorsorglich, nicht gemessen: Ein Hinweis ohne Datum (etwa {"warning": "..."} zur Tiefe des kostenlosen Zugangs) ist kein
        # Kurstag und wird uebergangen. Jeder andere Eintrag ohne Datum ist ein Fehler.
        if set(item) == {"warning"} and isinstance(item["warning"], str):
            continue
        trading = _day(item.get("date"))
        if trading in seen:
            _abort()
        seen.add(trading)
        prices = {key: _number(item.get(key)) for key in ("open", "high", "low", "close", "adjusted_close")}
        volume = _number(item.get("volume"), integral=True)
        if trading < start or trading > end:
            continue
        # Ein Schluss von 0 ist keine Beobachtung, sondern eine Luecke der Quelle (bewertet wuerde sonst mit 0).
        observed = prices["close"] not in (None, "0")
        observed_at = datetime.combine(trading, _ORDER_TIME, tzinfo=zone).astimezone(timezone.utc)
        days.append({"trading_date": trading.isoformat(), "open_decimal": prices["open"], "high_decimal": prices["high"],
                     "low_decimal": prices["low"], "close_decimal": prices["close"] if observed else None,
                     "adjusted_close_decimal": prices["adjusted_close"] if observed else None, "volume_decimal": volume,
                     "day_status": "observed" if observed else "source_gap", "corporate_action_status": "none_reported",
                     "observed_at_utc": observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")})
    days.sort(key=lambda row: row["trading_date"])
    # EOD nennt keinen Namen, keine Gattung, keine Erstnotiz und keine Kapitalmassnahmen; leer heisst "von der Quelle nicht gemeldet".
    return {"provider_symbol": symbol, "provider_currency": currency, "exchange": exchange, "timezone_name": zone_name,
            "instrument_name": "", "instrument_type": "", "split_review_required": False, "days": days, "live_session": None,
            "first_trade_date": None}


# ---------------------------------------------------------------------------------------------------------------------------
# Suche
# ---------------------------------------------------------------------------------------------------------------------------

def _isin(value):
    if not isinstance(value, str):
        return None
    value = value.strip().upper()
    if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", value) is None:
        return None
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    total = sum((int(c) * 2 // 10 + int(c) * 2 % 10) if i % 2 else int(c) for i, c in enumerate(reversed(digits)))
    return value if total % 10 == 0 else None


def _text(value, limit):
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        return None
    return value[:limit].rstrip()


def _candidates(payload: bytes, limit: int) -> list[dict]:
    value = json.loads(payload.decode("utf-8"))
    if not isinstance(value, list):
        raise ValueError("shape")
    rows, seen = [], set()
    for item in value:
        if len(rows) >= limit:
            break
        if not isinstance(item, dict):
            raise ValueError("shape")
        code, exchange = _text(item.get("Code"), 60), _text(item.get("Exchange"), 19)
        if code is None or exchange is None:
            continue
        symbol = f"{code}.{exchange}"
        if symbol in seen:
            continue
        seen.add(symbol)
        raw_type = item.get("Type")
        currency = item.get("Currency")
        row = {"symbol": symbol, "display_name": _text(item.get("Name"), 120) or symbol, "exchange": exchange,
               "quote_type": _TYPES.get(raw_type.strip().lower() if isinstance(raw_type, str) else "", "other"),
               "quote_currency": currency.strip() if isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency.strip()) else None}
        isin = _isin(item.get("ISIN"))
        if isin is not None:
            row["isin"] = isin
        rows.append(row)
    return rows
