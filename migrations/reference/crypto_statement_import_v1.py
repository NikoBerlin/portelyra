"""Krypto-Exporte von Boersen und Wallets (#454): Kaeufe und Verkaeufe gegen EUR, Transfers zwischen eigenen Konten.

Ein Leser fuer alle Formate, weil ein Transfer erst mit beiden Seiten feststeht: die Auszahlung bei der Boerse und der
Eingang im Wallet stehen in zwei Dateien. Gelesen werden die CSV-Exporte von Kraken (Ledger-Export), Coinbase, Bison,
BSDEX, Bitcoin.de, BitBox und Ledger Live; erkannt wird jede Datei an ihrem Tabellenkopf.

- Handel gegen EUR wird Kauf oder Verkauf mit den Betraegen des Exports (Kurs = EUR-Betrag / Menge, 12 Stellen).
- Transfer: Abgang auf dem einen, Eingang auf dem anderen eigenen Konto, gepaart ueber den Hash der Kette oder ueber
  die Menge (Eingang = Abgang ohne Gebuehr) in einem Zeitfenster. Gebucht wird die angekommene Menge; die Netzwerk-
  gebuehr traegt das Quellkonto (so wird gebucht).
- Umschichtungen innerhalb einer Boerse (Kraken Spot/Earn, Coinbase Staking, BSDEX Staking) sind Transfers zwischen
  den Konten dieser Boerse.
- Nicht automatisch gebucht wird, was der Export nicht vollstaendig hergibt: ein Abgang ohne Eingang (Ziel fehlt), ein
  Eingang ohne Abgang (Herkunft fehlt), Tausch Coin gegen Coin (EUR-Wert fehlt), BSDEX-Auftraege ohne "Finalisiert am"
  (aeltere Exporte nennen nur die Anlage des Auftrags) und reine Gebuehren. Sie stehen mit Grund in der Liste.
- Rewards bucht der Reward-Import ("Boersen-Statements importieren"), EUR-Bewegungen gehoeren zum Cash-Konto.

Wiedererkannt wird eine Buchung zuerst an der Kennung im Beleg-Speicher (Transaktions-ID, Hash), dann an Konto, Coin,
Art, Menge und Zeitpunkt. Die Pruefung schreibt nichts.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Callable, Mapping, Sequence
from zoneinfo import ZoneInfo

from migrations.reference import statement_reader_plugins_v1 as reader_plugins

PROFILE = "crypto"
BERLIN = ZoneInfo("Europe/Berlin")
UTC = timezone.utc
PRICE_STEP = Decimal("1e-12")
PAIR_WINDOW = timedelta(hours=12)
CLOCK_SKEW = timedelta(minutes=30)
WINDOWS = (timedelta(minutes=20), timedelta(hours=3), timedelta(hours=36))
ORDER_WINDOW_DAYS = 30   # Vorgabe fuer Auftraege einer Quelle ohne eigene Angabe (order_window_days im Manifest, Stufe 5)
DUST = Decimal("0.00001")   # Eingang bis zu dieser Menge ohne Gegenstueck: Staub (Spam an die Adresse), nicht gebucht
FEE_TOLERANCE = Decimal("1e-12")   # Netzgebuehr in Coin: kleinster Rest, der als Rundung gilt
SHORT_DECIMALS = 8          # Boersen kuerzen Mengen (Kraken 8-10 Stellen); ab so vielen Stellen gilt gekuerzt = gleich

# Quellangaben je Boerse und Wallet liefern die Leser-Plugins im Manifest (Stufe 5, rc.419, #486): Name, Institute, Unterkonten, Paarung,
# Auftragsfenster, Gruende. Der Kern kennt nur noch den generischen Leser (#514), der zu keinem Institut gehoert.
GENERIC_PROFILE: dict[str, Any] = {
    "key": "generic", "label": "Generisch (experimentell)", "institution_names": (), "pairing": "none", "internal_transfers": False,
    "wallets": {}, "default_wallet": {"label_prefix": "", "account_name": {"any": (), "none": ()}}, "reason_texts": {}, "unpaired_reason_by_ticker": {},
}


def _profile(source: str) -> Mapping[str, Any]:
    """Quellangaben der Quelle einer Zeile; ein installierter Leser ohne Angaben bekommt neutrale Vorgaben unter seinem Namen."""
    if source == "generic":
        return GENERIC_PROFILE
    return reader_plugins.crypto_source_profiles_v1().get(source) or {**GENERIC_PROFILE, "key": source, "label": source}


REASONS = {
    "crypto_reward": "Reward – bucht der Reward-Import („Börsenauszüge importieren“)",
    "crypto_fiat": "EUR-Ein- oder Auszahlung – gehört zum Cash-Konto",
    "crypto_cancelled": "Auftrag storniert oder nicht ausgeführt",
    "crypto_order_open": "Auftrag noch offen – wird gelesen, sobald die Börse ihn als geschlossen führt",
    "crypto_order_partly_open": "Order teilweise ausgeführt und noch offen – wird mit allen Ausführungen gebucht, sobald sie abgeschlossen ist (ausgeführt oder storniert)",
    "crypto_fee_row": "Netzwerkgebühr – am zugehörigen Transfer verrechnet",
    "crypto_registration": "Kontoeröffnung ohne Bestand",
    "crypto_pending": "noch nicht abgeschlossen",
    "crypto_unsupported": "Vorgangsart wird nicht gelesen",
    "crypto_zero_amount": "Menge 0 ohne Gebühr – keine Bewegung (z. B. Token-Vorgang)",
    "crypto_swap_counter_leg": "Gegenseite eines Tauschs – der Vorgang steht in der Datei des gekauften Coins",
    "crypto_unreadable_row": "Zeile unvollständig oder unlesbar (Zeit, Coin, Menge oder ein Betrag)",
}
# Text je einzeln verworfener Zeile (rc.379, Vorgabe: Zeile der Datei nennen): "Zeile 18 der Datei nicht gebucht:
# Euro-Betrag ist negativ" - die Zeilennummer, die eine Tabellenkalkulation zeigt. Kennt der Leser sie nicht, nennt der Text die Zaehlweise.
DETAIL_FIELD_LABELS = {"time": "Zeitpunkt", "ticker": "Coin", "quantity": "Menge", "fee_quantity": "Netzwerkgebühr", "eur": "Euro-Betrag",
                       "eur_fee": "Euro-Gebühr", "price": "Kurs", "number": "Eine Zahl", "wallet": "Wallet", "transaction_id": "Transaktions-ID",
                       "hash": "Hash", "address": "Adresse", "group": "Gruppe", "quote": "Gegenwährung", "file_name": "Dateiname", "zone": "Zeitzone"}
DETAIL_PROBLEM_LABELS = {"missing": "fehlt oder ist unlesbar", "unreadable": "ist unlesbar", "negative": "ist negativ",
                         "too_long": "ist zu lang (mehr als 400 Zeichen, beim Coin mehr als 40)", "out_of_range": "liegt außerhalb des gültigen Bereichs"}



def crypto_row_detail_reason_v1(detail: Mapping[str, Any]) -> str:
    where = (f"Zeile {detail['line']} der Datei" if detail.get("line") is not None
             else f"Datenzeile {detail['row_no']} (gezählt ab der ersten Zeile unter der Kopfzeile)")
    return f"{where} nicht gebucht: {DETAIL_FIELD_LABELS[detail['field']]} {DETAIL_PROBLEM_LABELS[detail['problem']]}"


# Allgemeine Gruende offener Vorgaenge. Gruende, die nur eine Quelle kennt (etwa die Auftraege bei BSDEX), liefert ihr Leser im Manifest
# (reason_texts, Stufe 5); open_reasons_v1 fuegt beides zusammen.
OPEN_REASONS = {
    "direction_unknown": "Der Export nennt die Richtung nicht – Export des Gegen-Wallets mitwählen",
    "order_time": "Auftrag vom {date} ohne Ausführungszeit – von Hand buchen, sobald sie feststeht",
    "transfer_out": "Abgang ohne Gegenstück – Export des Ziel-Wallets mitwählen oder von Hand buchen",
    "transfer_in": "Eingang ohne Gegenstück – Export der Herkunft mitwählen oder von Hand buchen",
    "swap": "Tausch Coin gegen Coin – EUR-Wert fehlt im Export, von Hand buchen",
    "fee_only": "Gebühr ohne Transfer (z. B. Token-Transfer) – am Transfer von Hand erfassen",
    "amount_mismatch": "Eingang kleiner als Abgang ohne passende Gebühr – Mengen prüfen",
    "same_wallet": "Abgang und Eingang auf demselben Konto",
    "dust": "Kleinstbetrag ohne Gegenstück (vermutlich Staub oder Spam an die Adresse) – wird nicht gebucht",
}

def open_reasons_v1() -> dict[str, str]:
    """Texte der Gruende offener Vorgaenge: die allgemeinen, dazu die der Leser (Manifest, Stufe 5); ein Leser ersetzt einen allgemeinen
    Text fuer seine Quelle nicht, er ergaenzt nur - nennen zwei Quellen denselben Code, gilt der erste."""
    texts = dict(OPEN_REASONS)
    for profile in reader_plugins.crypto_source_profiles_v1().values():
        for code, text in profile["reason_texts"].items():
            texts.setdefault(code, text) if code not in OPEN_REASONS else None
    return texts


def _open_reason_text(kind: str, candidate: Mapping[str, Any]) -> str:
    """Text eines offenen Grundes; der Text der eigenen Quelle geht vor (etwa der genauere BSDEX-Text bei unbekannter Richtung)."""
    own = _profile(candidate["source"])["reason_texts"].get(kind)
    text = own or open_reasons_v1().get(kind) or f"Offen ({kind}) – von Hand prüfen"
    return text.format_map(candidate.get("open_detail") or {})


def _order_window_days(candidate: Mapping[str, Any]) -> int:
    """Wie lange nach der Anlage ein Auftrag noch ausgefuehrt werden kann (Manifest der Quelle, sonst die Vorgabe)."""
    return int(_profile(candidate["source"]).get("order_window_days", ORDER_WINDOW_DAYS))


SECOND_SIDE_NOTE = "zweite Seite eines gebuchten Transfers"
DAY_FEES_NOTE = "Gebühr enthält die Token-Gebühren desselben Tages"
FEE_BOOKED_NOTE = "als Gebühr am Transfer desselben Tages gebucht"
# Zwei Buchungen desselben Coins in derselben Sekunde verlangt der FIFO-Kern mit einem Reihenfolge-Beleg aus einer Quelldatei; Reward-Import
# und Belegimport sind zwei (Kraken bucht Reward und Earn-Umschichtung oft in derselben Sekunde). Ein neuer Vorgang rueckt deshalb nach hinten.
SAME_SECOND_NOTE = "Uhrzeit um {seconds} s versetzt – derselbe Coin hat in dieser Sekunde schon eine Buchung (sonst keine eindeutige FIFO-Reihenfolge)"
KIND_LABELS = {"buy": "Kauf", "sell": "Verkauf", "transfer": "Transfer", "open": "offen"}
_KRAKEN_CODES = {"XXBT": "BTC", "XBT": "BTC", "XETH": "ETH", "XXRP": "XRP", "XLTC": "LTC", "XXDG": "DOGE", "XDG": "DOGE", "XXLM": "XLM",
                 "XZEC": "ZEC", "XXMR": "XMR", "ETH2": "ETH", "ZEUR": "EUR", "EUR.HOLD": "EUR", "EUR.M": "EUR"}
_NAMES = {"bitcoin": "BTC", "ether": "ETH", "ethereum": "ETH", "solana": "SOL", "xrp": "XRP", "polkadot": "DOT", "chainlink": "LINK",
          "cardano": "ADA", "litecoin": "LTC", "avalanche": "AVAX", "polygon": "POL", "tron": "TRX", "stellar": "XLM", "dogecoin": "DOGE"}
_UNITS = {"satoshi": (Decimal("1e-8"), "BTC"), "sat": (Decimal("1e-8"), "BTC"), "wei": (Decimal("1e-18"), "ETH"), "gwei": (Decimal("1e-9"), "ETH")}
_HEX = re.compile(r"(0x)?[0-9a-fA-F]{16,}")


class CryptoStatementError(ValueError):
    pass


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _plain(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _number(text: Any) -> Decimal | None:
    """Zahl aus Exportfeldern: "1.234,56 €", "€1,234.56", "-0.5", "0,015 BTC". Vorzeichen bleibt."""
    value = str(text or "").replace("\xa0", " ").replace("€", "").strip()
    match = re.match(r"^(-?)\s*(-?)([0-9][0-9.,]*)(?:[eE](-?[0-9]+))?", value)
    if match is None:
        return None
    number = match.group(3)
    if "," in number and "." in number:
        number = number.replace(".", "").replace(",", ".") if number.rfind(",") > number.rfind(".") else number.replace(",", "")
    elif "," in number:
        number = number.replace(",", ".")
    try:
        result = Decimal(number + (("e" + match.group(4)) if match.group(4) else ""))
    except InvalidOperation:
        return None
    return -result if (match.group(1) or match.group(2)) else result


def _ticker(code: str) -> str:
    value = re.sub(r"[^A-Z0-9.]", "", (code or "").upper())
    if value in _KRAKEN_CODES:
        return _KRAKEN_CODES[value]
    value = re.sub(r"\.[A-Z0-9]+$", "", value)
    return _KRAKEN_CODES.get(value, value)


def _parse_time(text: str, pattern: str, zone=UTC) -> datetime | None:
    try:
        return datetime.strptime((text or "").strip(), pattern).replace(tzinfo=zone).astimezone(UTC)
    except ValueError:
        return None


def _iso_time(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat((text or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def _normal_id(value: str) -> str:
    """Hex-Kennungen ohne Praefix und klein; alles andere unveraendert (Base58 unterscheidet Gross und Klein)."""
    value = (value or "").strip()
    if _HEX.fullmatch(value):
        return (value[2:] if value[:2].lower() == "0x" else value).lower()
    return value


def _rows(text: str, start_marker: str | None = None) -> list[dict[str, str]]:
    lines = text.splitlines()
    start = 0
    if start_marker:
        start = next((index for index, line in enumerate(lines[:30]) if line.startswith(start_marker)), None)
        if start is None:
            return []
    if start >= len(lines):
        return []
    delimiter = max(",;\t", key=lines[start].count)
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delimiter)
    return [{(key or "").strip(): (value or "").strip() for key, value in row.items() if key is not None} for row in reader]


def _row_key(row: Mapping[str, Any]) -> str:
    return _sha(["crypto_row", row["source"], row["wallet"], row["at_utc"], row["ticker"], row["kind"], row["quantity"], row["fee_quantity"], row["eur"],
                 row["transaction_id"], row["hash"], row["group"]])


class _Sheet:
    """Sammelt die Zeilen einer Datei: lesbare Bewegungen und gezaehlte Gruende fuer den Rest."""

    def __init__(self, source: str, file_name: str):
        self.source, self.file_name, self.rows, self.reasons = source, file_name, [], Counter()

    def skip(self, code: str) -> None:
        self.reasons[code] += 1

    def add(self, row_no: int, wallet: str, at: datetime | None, ticker: str, kind: str, quantity: Decimal | None, **extra: Any) -> None:
        if at is None or not ticker or quantity is None:
            self.skip("crypto_unreadable_row"); return
        row = {"profile": "crypto_row", "source": self.source, "file_name": self.file_name, "row_no": row_no, "wallet": wallet,
               "at_utc": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": extra.get("zone") or "UTC", "ticker": ticker,
               "kind": kind, "quantity": _plain(quantity), "fee_quantity": _plain(extra.get("fee_quantity")),
               "eur": _plain(extra.get("eur")), "eur_fee": _plain(extra.get("eur_fee")), "transaction_id": (extra.get("transaction_id") or "").strip(),
               "hash": (extra.get("hash") or "").strip(), "address": (extra.get("address") or "").strip(), "group": (extra.get("group") or "").strip(),
               "quote": extra.get("quote") or ""}
        if extra.get("window_from") is not None:   # BSDEX: Anlage der Order, fuer die Zuordnung der Ausfuehrungen (nicht Teil der Kennung)
            row["window_from_utc"] = extra["window_from"].strftime("%Y-%m-%dT%H:%M:%SZ")
        if extra.get("at_last_execution"):   # BSDEX, stornierte Order mit Teilausfuehrung: Zeit ist die ihrer letzten Ausfuehrung
            row["at_last_execution"] = True
        row["row_key"] = _row_key(row)
        self.rows.append(row)

    def result(self) -> dict[str, Any]:
        return {"status": "multi", "candidates": self.rows, "row_reasons": dict(self.reasons)}


_VALIDATION_REASONS = {**REASONS, "unknown_document": "unknown_document", "reader_inactive": "reader_inactive"}


# Ausblenden (Festlegung 09.11.2026): Eine Datei einer Boerse, die in keinem Portfolio aktiv ist, wird nicht gelesen; sie steht
# mit Grund unter "Dateien ohne Buchung", die uebrigen Dateien laufen weiter. Setzt die Pruefung (securities-statement-review) je Aufruf.
_INACTIVE_READERS: set[str] = set()


def set_inactive_crypto_readers_v1(reader_ids) -> None:
    _INACTIVE_READERS.clear()
    _INACTIVE_READERS.update(reader_ids)


def _crypto_readers() -> tuple[str, ...]:
    """Leser in Pruefreihenfolge (Manifeste, rc.419): zuerst mitgelieferte Belege ohne eigene Zeilen (etwa die BSDEX-Jahreshistorie mit den
    genauen Euro-Betraegen - sie muss vor dem Export erkannt werden), dann die mitgelieferten Exporte, danach installierte (rc.381)."""
    specs = reader_plugins.reader_specs_v1("crypto")
    evidence = [spec.reader_id for spec in specs if spec.origin == "shipped" and spec.source is None]
    exports = [spec.reader_id for spec in specs if spec.origin == "shipped" and spec.source is not None]
    installed = sorted(spec.reader_id for spec in specs if spec.origin == "installed")
    return tuple(evidence + exports + [reader_id for reader_id in installed if reader_id not in evidence + exports])


def _export_readers() -> tuple[str, ...]:
    """Die Leser von Exporten: ohne die Belege ohne eigene Zeilen (eine Jahreshistorie allein ist kein Export)."""
    shipped_evidence = {spec.reader_id for spec in reader_plugins.reader_specs_v1("crypto") if spec.origin == "shipped" and spec.source is None}
    return tuple(reader_id for reader_id in _crypto_readers() if reader_id not in shipped_evidence)


def _reader_for(text: str, readers: Sequence[str]) -> str | None:
    """Erst die Regeln des Manifests (im Kern), dann die Erkennung des Lesers - abgeschottet."""
    texts = reader_plugins.detection_texts_v1([text])
    for reader_id in readers:
        if reader_plugins.reader_spec_v1(reader_id, "crypto") is None or not reader_plugins.detection_passes_v1(reader_id, texts, "crypto"):
            continue
        result = reader_plugins.run_detect_v1(reader_id, "crypto", [text])[0]
        if not result["ok"]:
            raise reader_plugins.StatementReaderBlocked(result["code"])
        if result["value"]:
            return reader_id
    return None


def detect_crypto_export_v1(text: str) -> bool:
    """Wie bisher: ein Export eines bekannten Formats (eine Jahreshistorie allein ist kein Export)."""
    return _reader_for(text.lstrip("\ufeff"), _export_readers()) is not None


def parse_crypto_export_v1(text: str, file_name: str = "") -> dict[str, Any]:
    text = text.lstrip("\ufeff")   # Bitcoin.de und Excel-Kopien beginnen mit einer Byte-Order-Mark
    reader_id = _reader_for(text, _crypto_readers())
    if reader_id is None:
        return {"status": "not_importable", "reason_code": "unknown_document"}
    if reader_id in _INACTIVE_READERS:
        return {"status": "not_importable", "reason_code": "reader_inactive"}
    result = reader_plugins.run_text_reader_v1(reader_id, "crypto", [(text, file_name)])[0]
    if not result["ok"]:
        raise reader_plugins.StatementReaderBlocked(result["code"])
    value = reader_plugins.validate_crypto_result_v1(result["value"], _VALIDATION_REASONS)
    # Herkunft je Buchung (rc.378): jede Zeile traegt den Leser, der sie gelesen hat; ein Vorgang sammelt die Leser seiner Zeilen.
    identity = reader_plugins.reader_identity_v1(reader_id, "crypto")
    for row in value.get("candidates", []):
        row["reader"] = identity
    return value


_CANDIDATE_EXTRAS = ("candidate_ordinal", "document_ordinal", "candidate_key", "reader")


def _combine_exact(rows: list[dict[str, Any]], executions: Sequence[Mapping[str, Any]]) -> None:
    """Auftraege auf den Cent (rc.325): Liest ein Leser Export und Beleg der Ausfuehrungen zusammen (Manifest "combine", etwa BSDEX mit
    der Jahreshistorie, rc.376), gehen ihm die Zeilen seiner Quelle zu. Was er dabei aendern darf, prueft der Kern (apply_crypto_combine_v1):
    Stueckzahl je Order gleich, Euro-Betrag und Gebuehr hoechstens 5 Cent vom Export, eine Order ohne Ausfuehrungen bleibt offen."""
    for spec in reader_plugins.reader_specs_v1("crypto"):
        if spec.combine and spec.source is not None:
            _combine_source(rows, executions, spec.reader_id, spec.source["key"])


def _combine_source(rows: list[dict[str, Any]], executions: Sequence[Mapping[str, Any]], reader_id: str, source: str) -> None:
    positions = [index for index, row in enumerate(rows) if row["source"] == source]
    if not any(rows[index]["kind"] == "trade" for index in positions):
        return
    sent = [{**{key: value for key, value in rows[index].items() if key not in _CANDIDATE_EXTRAS}, "combine_ref": ref} for ref, index in enumerate(positions)]
    result = reader_plugins.run_combine_rows_v1(reader_id, "crypto", {"rows": sent, "executions": list(executions)})
    if not result["ok"]:
        raise reader_plugins.StatementReaderBlocked(result["code"])
    combined = reader_plugins.apply_crypto_combine_v1(sent, result["value"])
    parts: dict[int, list[dict[str, Any]]] = {}
    for row in combined:
        ref = row.pop("combine_ref")
        extras = {key: rows[positions[ref]][key] for key in _CANDIDATE_EXTRAS if key in rows[positions[ref]]}
        parts.setdefault(ref, []).append({**row, **extras})
    by_index = {index: parts[ref] for ref, index in enumerate(positions)}
    rows[:] = [part for index, row in enumerate(rows) for part in by_index.get(index, [row])]


def crypto_format_labels_v1() -> str:
    """Die lesbaren Exporte, wie die Import-Karte sie nennt - aus den Manifesten (format_label), alphabetisch."""
    labels = [profile["format_label"] for profile in reader_plugins.crypto_source_profiles_v1().values()]
    return ", ".join(sorted(labels, key=str.lower))


# --- Vorgaenge -----------------------------------------------------------------------------------------------------------

def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _same_amount(first: Any, second: Any) -> bool:
    """Gleich, oder gleich nachdem die laengere Zahl auf die Stellen der kuerzeren gekuerzt bzw. gerundet ist - nur ab acht Stellen:
    Eine Boerse fuehrt 0,1234567891 ETH, das Wallet 0,12345678912345678. 4,500005 und 4,5 bleiben verschieden."""
    a, b = _dec(first), _dec(second)
    if a is None or b is None:
        return False
    a, b = abs(a).normalize(), abs(b).normalize()
    if a == b:
        return True
    places = lambda value: max(0, -value.as_tuple().exponent)
    short, long = (a, b) if places(a) <= places(b) else (b, a)
    if places(short) < SHORT_DECIMALS:
        return False
    step = Decimal(1).scaleb(-places(short))
    return long.quantize(step, rounding=ROUND_DOWN) == short or long.quantize(step, rounding=ROUND_HALF_UP) == short


def _at(row: Mapping[str, Any]) -> datetime:
    return datetime.strptime(row["at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _handle(row: Mapping[str, Any]) -> str:
    return "wal_" + _sha([row["source"], row["wallet"]])[:16]


def _local(row: Mapping[str, Any]) -> tuple[str, str, str]:
    zone = row["zone"]
    moment = _at(row).astimezone(BERLIN if zone == "Europe/Berlin" else UTC)
    return moment.strftime("%Y-%m-%d"), moment.strftime("%H:%M:%S"), zone


def _op(kind: str, rows: Sequence[Mapping[str, Any]], *, account_row: Mapping[str, Any], related_row: Mapping[str, Any] | None = None, open_kind: str | None = None,
        **fields: Any) -> dict[str, Any]:
    local_date, local_time, zone = _local(account_row)
    ids = []
    for row in rows:
        for key in ("transaction_id", "hash", "group"):
            if row.get(key) and row[key] not in ids:
                ids.append(row[key])
    first = rows[0]
    # Je Leser einmal, geordnet nach Plugin, Leser und Bereich (#486): Die Pruefsumme des Codes stand im JSON vorn und warf die Folge bei
    # jeder Code-Aenderung um, ohne dass sich etwas am Inhalt aenderte.
    unique = {json.dumps(row["reader"], sort_keys=True): row["reader"] for row in rows if row.get("reader")}
    readers = sorted(unique.values(), key=lambda reader: (reader.get("plugin_id", ""), reader.get("reader_id", ""), reader.get("domain", ""), json.dumps(reader, sort_keys=True)))
    return {"profile": PROFILE, "kind": kind, "open_kind": open_kind, "readers": readers, "source": account_row["source"], "ticker": account_row["ticker"],
            "security_name": account_row["ticker"], "isin": "", "currency": None,
            "wallet_handle": _handle(account_row), "related_handle": None if related_row is None else _handle(related_row),
            "at_utc": account_row["at_utc"], "local_date": local_date, "local_time": local_time, "time_zone": zone,
            "quantity": None, "unit_price": None, "gross_amount": None, "fee_amount": None, "asset_fee": None,
            "ids": ids, "address": next((row["address"] for row in rows if row.get("address")), ""),
            "rows": [{key: row[key] for key in ("source", "wallet", "row_no", "file_name", "kind")} for row in rows],
            "file_name": first["file_name"], "candidate_key": _sha(sorted(row["row_key"] for row in rows)), **fields}


# Offene BSDEX-Order: Grund des Plugins (unpriced_trade) bzw. des Kerns (mismatched_trade, mehr als 5 Cent) -> Vorgangsart des Kerns.
UNPRICED_OPEN_KINDS = {"history_missing": "history_missing", "history_outdated": "history_outdated", "no_executions": "executions_missing",
                       "quantity_differs": "executions_quantity_differs", "amount_differs": "export_amount_differs", "ambiguous": "executions_ambiguous"}


def _de_number(value: Any) -> str:
    """Zahl wie im deutschen Beleg, ohne Rundung: 1234.5 -> 1.234,5."""
    text = format(Decimal(str(value)), "f")
    sign, text = ("-", text[1:]) if text.startswith("-") else ("", text)
    whole, _, part = text.partition(".")
    return sign + f"{int(whole):,}".replace(",", ".") + ("," + part if part else "")


def _de_eur(value: Any) -> str:
    if value is None:
        return "–"
    amount = Decimal(str(value))
    return _de_number(amount.quantize(Decimal("0.01")) if amount.as_tuple().exponent >= -2 else amount) + " €"


def _held_order(row: Mapping[str, Any], quantity: Decimal) -> dict[str, Any]:
    """Eine BSDEX-Order ohne genauen Betrag bleibt offen, mit ihrem Grund samt Datum, Menge und Betraegen (open_detail fuer den Text).
    Kurswert und Gebuehr bleiben leer (Vorschlag 08.11.2026): "Im Editor öffnen" belegt nie einen Betrag vor - weder den gerundeten des
    Exports noch eine Summe aus dem Ergebnis des Plugins, die der Kern nicht nachrechnen kann. Beide Betraege stehen im Grund."""
    open_kind = "export_amount_differs" if row["kind"] == "mismatched_trade" else UNPRICED_OPEN_KINDS[row["unpriced_reason"]]
    local_date = _local(row)[0]
    detail = {"date": f"{local_date[8:10]}.{local_date[5:7]}.{local_date[:4]}", "year": row.get("history_year", ""), "quantity": _de_number(abs(quantity)),
              "ticker": row["ticker"], "export_eur": _de_eur(row["eur"]), "export_fee": _de_eur(row["eur_fee"])}
    if open_kind == "export_amount_differs":
        detail.update(executions_eur=_de_eur(row["executions_eur"]), executions_fee=_de_eur(row["executions_fee"]))
    if open_kind == "history_outdated":
        until = row["history_until"]
        detail["until"] = f"{until[8:10]}.{until[5:7]}.{until[:4]}"
    return _op("open", [row], account_row=row, open_kind=open_kind, side="buy" if quantity > 0 else "sell", quantity=_plain(abs(quantity)),
               gross_amount=None, fee_amount=None, open_detail=detail)


def _trade(row: Mapping[str, Any], quantity: Decimal, eur: Decimal | None, fee: Decimal | None, rows: Sequence[Mapping[str, Any]] | None = None,
           primary_id: str | None = None) -> dict[str, Any]:
    kind = "buy" if quantity > 0 else "sell"
    if eur is None or eur <= 0 or quantity == 0:
        return _op("open", rows or [row], account_row=row, open_kind="amount_mismatch", side=kind, quantity=_plain(abs(quantity)))
    price = (eur / abs(quantity)).quantize(PRICE_STEP, rounding=ROUND_HALF_UP)
    return _op(kind, rows or [row], account_row=row, quantity=_plain(abs(quantity)), unit_price=_plain(price), gross_amount=_plain(eur),
               fee_amount=_plain(fee or Decimal(0)), transaction_id=primary_id or row.get("transaction_id") or "")


def assemble_crypto_operations_v1(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Aus den Zeilen aller Dateien die Vorgaenge: Handel, Umschichtung, Transfer (gepaart) und offene Bewegungen."""
    operations: list[dict[str, Any]] = []
    by_group: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        pairing = _profile(row["source"])["pairing"]
        if pairing == "group" and row["kind"] in ("trade_eur", "trade_coin") and row["group"]:
            by_group[("trade", row["group"])].append(row)
        elif pairing == "group" and row["kind"] == "internal" and row["group"]:
            by_group[("internal", row["group"] + "|" + row["ticker"])].append(row)
    # Paarung ueber die gemeinsame Kennung (etwa die refid bei Kraken): Handel = Coin-Bein und EUR-Bein derselben Kennung
    for (kind, _key), legs in sorted(by_group.items(), key=lambda item: min(r["at_utc"] for r in item[1])):
        if kind == "trade":
            coins = [leg for leg in legs if leg["kind"] == "trade_coin"]; euros = [leg for leg in legs if leg["kind"] == "trade_eur"]
            if len(coins) == 1 and len(euros) == 1:
                coin, euro = coins[0], euros[0]
                quantity = _dec(coin["quantity"]); fee = _dec(coin["fee_quantity"]) or Decimal(0)
                net = quantity - fee if quantity > 0 else quantity   # Kauf: angekommene Menge nach Gebuehr in Coin
                operations.append(_trade(coin, net, abs(_dec(euro["quantity"])), _dec(euro["eur_fee"]), legs, primary_id=coin["group"]))
            else:
                operations.append(_op("open", legs, account_row=legs[0], open_kind="swap"))
        else:
            outs = [leg for leg in legs if _dec(leg["quantity"]) < 0]; ins = [leg for leg in legs if _dec(leg["quantity"]) > 0]
            if len(outs) == 1 and len(ins) == 1 and outs[0]["wallet"] != ins[0]["wallet"]:
                out, inn = outs[0], ins[0]
                fee = abs(_dec(out["quantity"])) - _dec(inn["quantity"])
                operations.append(_op("transfer", legs, account_row=out, related_row=inn, quantity=_plain(_dec(inn["quantity"])),
                                      asset_fee=_plain(fee) if fee > 0 else None, transaction_id=out["group"]))
            else:
                operations.extend(_op("open", [leg], account_row=leg, open_kind="transfer_out" if _dec(leg["quantity"]) < 0 else "transfer_in") for leg in legs)
    for row in rows:
        quantity = _dec(row["quantity"])
        if row["kind"] == "trade":
            operations.append(_trade(row, quantity, _dec(row["eur"]), _dec(row["eur_fee"])))
        elif row["kind"] in ("unpriced_trade", "mismatched_trade"):
            operations.append(_held_order(row, quantity))
        elif row["kind"] == "order":
            # Der gerundete Export-Betrag bleibt fuer den Abgleich mit Gebuchtem und steht im Grund; "Im Editor öffnen" belegt ihn nicht vor (#545).
            local_date = _local(row)[0]
            detail = {"date": f"{local_date[8:10]}.{local_date[5:7]}.{local_date[:4]}", "export_eur": _de_eur(row["eur"]), "export_fee": _de_eur(row["eur_fee"])}
            operations.append(_op("open", [row], account_row=row, open_kind="order_time", open_detail=detail, side="buy" if quantity > 0 else "sell", quantity=_plain(abs(quantity)),
                                  gross_amount=row["eur"], fee_amount=row["eur_fee"]))
        elif row["kind"] == "swap":
            operations.append(_op("open", [row], account_row=row, open_kind="swap", quantity=_plain(abs(quantity))))
        elif row["kind"] == "fee_only":
            operations.append(_op("open", [row], account_row=row, open_kind="fee_only", quantity=_plain(abs(quantity))))
        elif row["kind"] in ("internal_staking", "internal_unstaking"):
            target = {**row, "wallet": "staking"}
            source, destination = (row, target) if row["kind"] == "internal_staking" else (target, row)
            operations.append(_op("transfer", [row], account_row=source, related_row=destination, quantity=_plain(abs(quantity))))
    # Paarung ueber die Zeit (etwa Staking bei Coinbase): Umschichtung als Paar aus Abgang und Zugang gleicher Menge im Zeitfenster der Quelle
    staking = sorted([row for row in rows if _profile(row["source"])["pairing"] == "time" and row["kind"] == "internal"], key=lambda row: row["at_utc"])
    used: set[str] = set()
    for row in staking:
        if row["row_key"] in used:
            continue
        mate = next((other for other in staking if other["row_key"] not in used and other["row_key"] != row["row_key"] and other["ticker"] == row["ticker"]
                     and abs(_dec(other["quantity"])) == abs(_dec(row["quantity"])) and (_dec(other["quantity"]) > 0) != (_dec(row["quantity"]) > 0)
                     and abs(_at(other) - _at(row)) <= timedelta(minutes=_profile(row["source"])["pair_window_minutes"])), None)
        if mate is None:
            operations.append(_op("open", [row], account_row=row, open_kind="transfer_out" if _dec(row["quantity"]) < 0 else "transfer_in", quantity=_plain(abs(_dec(row["quantity"])))))
            used.add(row["row_key"]); continue
        out, inn = (row, mate) if _dec(row["quantity"]) < 0 else (mate, row)
        used |= {row["row_key"], mate["row_key"]}
        operations.append(_op("transfer", [out, inn], account_row=out, related_row={**inn, "wallet": _profile(inn["source"])["pair_related_wallet"]}, quantity=_plain(abs(_dec(inn["quantity"]))),
                              transaction_id=out["transaction_id"]))
    operations.extend(_pair_moves([row for row in rows if row["kind"] in ("move", "move_unknown")]))
    operations.sort(key=lambda item: (item["at_utc"], item["candidate_key"]))
    return operations


def _pair_moves(moves: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    outs = [row for row in moves if row["kind"] == "move" and _dec(row["quantity"]) < 0]
    ins = [row for row in moves if row["kind"] == "move" and _dec(row["quantity"]) > 0]
    unknown = [row for row in moves if row["kind"] == "move_unknown"]
    used: set[str] = set()
    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    # 1. derselbe Hash der Kette auf beiden Seiten
    for out in outs:
        if not out["hash"]:
            continue
        mate = next((row for row in ins if row["row_key"] not in used and row["hash"] and _normal_id(row["hash"]) == _normal_id(out["hash"])
                     and row["ticker"] == out["ticker"] and _handle(row) != _handle(out)), None)
        if mate is not None:
            pairs.append((out, mate)); used |= {out["row_key"], mate["row_key"]}
    # 2. Menge: der Eingang ist der Abgang ohne Gebuehr, im Zeitfenster danach (kleine Uhrabweichung erlaubt)
    def fits(out: Mapping[str, Any], inn: Mapping[str, Any]) -> bool:
        delta = _at(inn) - _at(out)
        return (inn["ticker"] == out["ticker"] and _handle(inn) != _handle(out) and -CLOCK_SKEW <= delta <= PAIR_WINDOW
                and _same_amount(inn["quantity"], out["quantity"]))
    for out in sorted(outs, key=_at):
        if out["row_key"] in used:
            continue
        candidates = [row for row in ins + unknown if row["row_key"] not in used and fits(out, row)]
        if candidates:
            mate = min(candidates, key=lambda row: abs(_at(row) - _at(out)))
            pairs.append((out, mate)); used |= {out["row_key"], mate["row_key"]}
    for inn in sorted(ins, key=_at):
        if inn["row_key"] in used:
            continue
        candidates = [row for row in unknown if row["row_key"] not in used and fits(row, inn)]
        if candidates:
            mate = min(candidates, key=lambda row: abs(_at(row) - _at(inn)))
            pairs.append((mate, inn)); used |= {inn["row_key"], mate["row_key"]}
    operations = []
    for out, inn in pairs:
        quantity = abs(_dec(inn["quantity"]))
        fee = _dec(out["fee_quantity"]) if out["kind"] == "move" else None
        operations.append(_op("transfer", [out, inn], account_row={**out, "quantity": out["quantity"]}, related_row=inn, quantity=_plain(quantity),
                              asset_fee=_plain(fee) if fee else None, transaction_id=next((row["hash"] for row in (out, inn) if row["hash"]), out["transaction_id"] or inn["transaction_id"])))
    for row in moves:
        if row["row_key"] in used:
            continue
        open_kind = "direction_unknown" if row["kind"] == "move_unknown" else ("transfer_out" if _dec(row["quantity"]) < 0 else "transfer_in")
        operations.append(_op("open", [row], account_row=row, open_kind=open_kind, quantity=_plain(abs(_dec(row["quantity"]))),
                              asset_fee=row["fee_quantity"], direction=None if row["kind"] == "move_unknown" else ("out" if _dec(row["quantity"]) < 0 else "in")))
    return operations


def finish_crypto_v1(candidates: list[dict[str, Any]], statements: list[dict[str, Any]], row_reasons: list[dict[str, Any]],
                     evidence: Mapping[str, Any] | None = None) -> None:
    """Abschluss-Hook des Lesers: ersetzt die Zeilen aller Dateien durch die Vorgaenge (Paarung ueber Dateigrenzen)."""
    rows = [dict(candidate) for candidate in candidates]
    # Feldname der Schnittstelle (Stufe 2): die Ausfuehrungen aus dem Beleg eines zusammenlesenden Lesers.
    _combine_exact(rows, (evidence or {}).get("bsdex_executions", []))
    documents = {row["file_name"]: row["document_ordinal"] for row in rows}
    operations = assemble_crypto_operations_v1(rows)
    candidates.clear()
    for ordinal, operation in enumerate(operations, 1):
        candidates.append({**operation, "candidate_ordinal": ordinal, "document_ordinal": documents.get(operation["file_name"])})


# --- Konten ---------------------------------------------------------------------------------------------------------------

def wallet_entries_v1(parsed: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Je Wallet-Handle: Quelle, Name im Export und Zahl der Vorgaenge."""
    entries: dict[str, dict[str, Any]] = {}
    for candidate in parsed.get("candidates", []):
        for handle_key, side in (("wallet_handle", "account"), ("related_handle", "related")):
            handle = candidate.get(handle_key)
            if not handle:
                continue
            row = next((item for item in candidate["rows"] if _handle(item) == handle), candidate["rows"][0] if side == "account" else candidate["rows"][-1])
            wallet = row["wallet"] if _handle(row) == handle else ("staking" if side == "related" else row["wallet"])
            entry = entries.setdefault(handle, {"depot_handle": handle, "source": row["source"], "wallet": wallet, "candidate_count": 0})
            entry["candidate_count"] += 1
    for entry in entries.values():
        source, wallet = entry["source"], entry["wallet"]
        profile = _profile(source)
        known = profile["wallets"].get(wallet)
        label = known["label"] if known else profile["default_wallet"]["label_prefix"] + wallet
        entry["depot_mask"] = profile["label"] + " · " + label
        entry["profile"] = PROFILE
        entry["profile_label"] = "Krypto-Export"
    return entries


def _name_fits(source: str, wallet: str, label: str) -> bool:
    """Passt der Kontoname zum Unterkonto? Regel der Quelle (Manifest): mindestens ein Wort aus "any", keines aus "none"."""
    profile = _profile(source)
    rule = (profile["wallets"].get(wallet) or profile["default_wallet"])["account_name"]
    name = label.lower()
    return (not rule["any"] or any(word in name for word in rule["any"])) and not any(word in name for word in rule["none"])


def suggest_crypto_accounts_v1(accounts: Sequence[Mapping[str, Any]], institutions: Mapping[str, str], entries: Mapping[str, Mapping[str, Any]],
                              learned: Mapping[str, str]) -> dict[str, str | None]:
    """Vorschlag je Wallet: zuerst das Konto, auf dem die Kennungen dieses Wallets schon gebucht sind; sonst das einzige Konto des
    Instituts, dessen Name zum Unterkonto passt (Kraken Spot/Earn, Staking)."""
    result: dict[str, str | None] = {}
    for handle, entry in entries.items():
        if learned.get(handle):
            result[handle] = learned[handle]; continue
        hints = _profile(entry["source"])["institution_names"]
        matching = [row for row in accounts if any(hint.lower() in (institutions.get(row["account_id"]) or "").lower() for hint in hints)]
        matching = [row for row in matching if _name_fits(entry["source"], entry["wallet"], row["label"])] or (matching if len(matching) == 1 else [])
        result[handle] = matching[0]["account_id"] if len(matching) == 1 else None
    return result


def learn_wallet_accounts_v1(parsed: Mapping[str, Any], events: Sequence[Mapping[str, Any]], references: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    """Konto je Wallet aus dem Bestand: Buchungen, deren Kennung in Zeilen dieses Wallets steht. Eindeutig oder gar nicht."""
    by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        reference = references.get(event["event_ref"]) or {}
        if reference.get("transaction_id"):
            by_id[_normal_id(reference["transaction_id"])].append(event)
    seen: dict[str, Counter] = defaultdict(Counter)
    for candidate in parsed.get("candidates", []):
        for key, side in (("wallet_handle", "account_id"), ("related_handle", "related_account_id")):
            handle = candidate.get(key)
            if not handle:
                continue
            for identifier in candidate.get("ids", []):
                for event in by_id.get(_normal_id(identifier), []):
                    account = event.get(side) if candidate["kind"] == "transfer" else (event.get("account_id") if key == "wallet_handle" else None)
                    if candidate["kind"] == "open" and candidate.get("direction") == "in":
                        account = event.get("related_account_id") or event.get("account_id")
                    if account:
                        seen[handle][account] += 1
    # Eindeutig oder mit klarer Mehrheit (vier von fuenf Treffern): eine Token-Gebuehr kann auf dem Konto der Gegenseite stehen
    learned = {}
    for handle, counter in seen.items():
        account, hits = counter.most_common(1)[0]
        if len(counter) == 1 or (hits >= 3 and hits * 5 >= sum(counter.values()) * 4):
            learned[handle] = account
    return learned


# --- Pruefung gegen den Bestand ----------------------------------------------------------------------------------------

def _event_at(event: Mapping[str, Any]) -> datetime | None:
    value = event.get("effective_at_utc")
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _quantities(candidate: Mapping[str, Any]) -> set[Decimal]:
    quantity = _dec(candidate.get("quantity"))
    if quantity is None:
        return set()
    values = {quantity}
    fee = _dec(candidate.get("asset_fee"))
    if fee:
        values |= {quantity + fee, quantity - fee}
    return {value.normalize() for value in values if value > 0}


def _compatible(candidate: Mapping[str, Any], event: Mapping[str, Any]) -> bool:
    kind = candidate["kind"]
    if event["asset_id"] != candidate.get("asset_id"):
        return False
    if kind in ("buy", "sell"):
        return event["event_type"] == kind and event["account_id"] == candidate["account_id"]
    if kind == "transfer":
        return event["event_type"] == "transfer" and event["account_id"] == candidate["account_id"] and event["related_account_id"] == candidate["related_account_id"]
    side = candidate.get("side")
    if candidate["open_kind"] in ("order_time", "amount_mismatch", *UNPRICED_OPEN_KINDS.values()) and side:
        return event["event_type"] == side and event["account_id"] == candidate["account_id"]
    direction = candidate.get("direction")
    account = candidate["account_id"]
    if direction == "out" or candidate["open_kind"] == "fee_only":
        return (event["event_type"] in ("transfer", "withdrawal", "sell") and event["account_id"] == account)
    if direction == "in":
        return ((event["event_type"] == "transfer" and event["related_account_id"] == account)
                or (event["event_type"] in ("buy", "deposit") and event["account_id"] == account))
    if candidate["open_kind"] == "direction_unknown":
        return event["event_type"] == "transfer" and account in (event["account_id"], event["related_account_id"])
    if candidate["open_kind"] == "swap":
        return event["event_type"] in ("buy", "sell") and event["account_id"] == account
    return False


def _differences(candidate: Mapping[str, Any], event: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    differs: list[str] = []
    notes: list[str] = []
    booked = _dec(event["quantity_decimal"])
    if candidate["kind"] in ("buy", "sell"):
        if not _same_amount(booked, candidate["quantity"]):
            differs.append("Menge")
        # Steuerlich zaehlt die Summe: Anschaffungskosten (Kurswert + Gebuehr) bzw. Erloes (Kurswert - Gebuehr). Wie eine Boerse
        # Kurs und Gebuehr aufteilt, haengt am Export; ein halber Promille bleibt Rundung.
        sign = 1 if candidate["kind"] == "buy" else -1
        booked_total = (booked or Decimal(0)) * (_dec(event["unit_price_decimal"]) or Decimal(0)) + sign * (_dec(event["monetary_fee_decimal"]) or Decimal(0))
        expected = (_dec(candidate["gross_amount"]) or Decimal(0)) + sign * (_dec(candidate["fee_amount"]) or Decimal(0))
        if abs(booked_total - expected) > max(Decimal("0.01"), expected * Decimal("0.0005")):
            differs.append("Anschaffungskosten" if candidate["kind"] == "buy" else "Erlös")
    elif candidate["kind"] == "transfer":
        if not _same_amount(booked, candidate["quantity"]):
            differs.append("Menge")
        # Netzgebuehren von Token-Transfers (eigene Zeile ohne Menge) stehen am ETH-Transfer desselben Kontos und Tages
        booked_fee, own_fee = _dec(event["asset_fee_quantity_decimal"]) or Decimal(0), _dec(candidate["asset_fee"]) or Decimal(0)
        day_fees = _dec(candidate.get("day_fees")) or Decimal(0)
        # teils gerundet nachgetragen: ein Millionstel der Gebuehr (mindestens ein Billionstel) ist Rundung
        close = lambda first, second: abs(first - second) <= max(FEE_TOLERANCE, abs(second) * Decimal("0.000001"))
        if not close(booked_fee, own_fee):
            if day_fees and close(booked_fee, own_fee + day_fees):
                notes.append(DAY_FEES_NOTE)
            else:
                differs.append("Gebühr")
    at = _event_at(event)
    if at is not None:
        hours = abs((at - datetime.strptime(candidate["at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)).total_seconds()) / 3600
        if hours >= 24:
            notes.append(f"Zeitpunkt {int(hours // 24)} Tag(e) anders")
        elif hours * 60 >= 2:
            notes.append(f"Uhrzeit {hours:.1f} h anders".replace(".", ","))
    return differs, notes


def review_crypto_operations_v1(candidates: Sequence[dict[str, Any]], events: Sequence[Mapping[str, Any]], references: Mapping[str, Mapping[str, Any]],
                                asset_by_ticker: Mapping[str, str | None], account_by_handle: Mapping[str, str]) -> dict[int, dict[str, Any]]:
    """Status je Vorgang. candidates werden um asset_id, account_id und related_account_id ergaenzt."""
    pool = [event for event in events if event["event_type"] != "reward"]
    by_id: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in pool:
        reference = references.get(event["event_ref"]) or {}
        if reference.get("transaction_id"):
            by_id[_normal_id(reference["transaction_id"])].append(event)
    results: dict[int, dict[str, Any]] = {}
    used: set[str] = set()
    sides: dict[str, set[str]] = defaultdict(set)   # Transfer-Buchung -> schon erkannte Seiten ("out", "in")
    covered_days: set[tuple[str, str, str]] = set()  # Konto, Coin, Tag: Token-Gebuehren stehen am Transfer

    def side_of(candidate: Mapping[str, Any], event: Mapping[str, Any]) -> set[str]:
        if event["event_type"] != "transfer" or candidate["kind"] == "transfer":
            return {"out", "in"}
        if candidate.get("open_kind") == "fee_only":
            return set()
        direction = candidate.get("direction")
        if direction in ("out", "in"):
            return {direction}
        return {"out"} if event["account_id"] == candidate.get("account_id") else {"in"}

    def settle(candidate: Mapping[str, Any], status: str, event: Mapping[str, Any] | None = None, differs=(), notes=()) -> None:
        results[candidate["candidate_ordinal"]] = {"status": status, "event_ref": None if event is None else event["event_ref"],
                                                   "differences": list(differs), "notes": list(notes)}
        if event is not None:
            used.add(event["event_ref"]); sides[event["event_ref"]] |= side_of(candidate, event)
            if DAY_FEES_NOTE in notes:
                covered_days.add((event["account_id"], event["asset_id"], event["local_date"]))

    waiting = []
    # Konten derselben Boerse (Spot, Earn, Staking): Umschichtungen zwischen ihnen erkennt der lockere Durchgang auch mit anderem Unterkonto
    by_source: dict[str, set[str]] = defaultdict(set)
    for candidate in candidates:
        for key in ("wallet_handle", "related_handle"):
            if candidate.get(key) and account_by_handle.get(candidate[key]):
                by_source[candidate["source"] if key == "wallet_handle" else candidate["rows"][-1]["source"]].add(account_by_handle[candidate[key]])
    internal_accounts: dict[str, set[str]] = defaultdict(set)
    for accounts in by_source.values():
        for account in accounts:
            internal_accounts[account] |= accounts
    for candidate in candidates:
        candidate["asset_id"] = asset_by_ticker.get(candidate["ticker"])
        candidate["account_id"] = account_by_handle.get(candidate["wallet_handle"])
        candidate["related_account_id"] = account_by_handle.get(candidate["related_handle"]) if candidate.get("related_handle") else None
    day_fees: dict[tuple[Any, Any, str], Decimal] = defaultdict(Decimal)
    for candidate in candidates:
        if candidate.get("open_kind") == "fee_only" and candidate["account_id"] and candidate["asset_id"]:
            day_fees[(candidate["account_id"], candidate["asset_id"], candidate["local_date"])] += abs(_dec(candidate.get("quantity")) or Decimal(0))
    for candidate in candidates:
        if candidate["kind"] == "transfer" and day_fees.get((candidate["account_id"], candidate["asset_id"], candidate["local_date"])):
            candidate["day_fees"] = _plain(day_fees[(candidate["account_id"], candidate["asset_id"], candidate["local_date"])])
    for candidate in candidates:
        if candidate["account_id"] is None or (candidate.get("related_handle") and candidate["related_account_id"] is None):
            settle(candidate, "depot_unassigned"); continue
        if candidate["asset_id"] is None:
            settle(candidate, "asset_missing"); continue
        if candidate["kind"] == "transfer" and candidate["account_id"] == candidate["related_account_id"]:
            candidate["kind"], candidate["open_kind"] = "open", "same_wallet"
        event = None
        for identifier in candidate.get("ids", []):
            event = next((item for item in by_id.get(_normal_id(identifier), []) if item["event_ref"] not in used and _compatible(candidate, item)), None)
            if event is not None:
                break
        if event is not None:
            differs, notes = _differences(candidate, event)
            settle(candidate, "booked_differs" if differs else "booked", event, differs, notes); continue
        waiting.append(candidate)
    for window in WINDOWS:
        for candidate in waiting:
            if candidate["candidate_ordinal"] in results:
                continue
            moment = datetime.strptime(candidate["at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            quantities = _quantities(candidate)
            matches = [event for event in pool if event["event_ref"] not in used and _compatible(candidate, event)
                       and _event_at(event) is not None and abs(_event_at(event) - moment) <= window and any(_same_amount(event["quantity_decimal"], value) for value in quantities)]
            if matches:
                event = min(matches, key=lambda item: abs(_event_at(item) - moment))
                differs, notes = _differences(candidate, event)
                settle(candidate, "booked_differs" if differs else "booked", event, differs, notes)
    # Auftraege (BSDEX): ausgefuehrt bis zu 200 Tage nach der Anlage - gleiche Menge, Art und Konto, nicht frueher als die Anlage
    for candidate in waiting:
        if candidate["candidate_ordinal"] in results or candidate.get("open_kind") != "order_time":
            continue
        moment = datetime.strptime(candidate["at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        matches = [event for event in pool if event["event_ref"] not in used and _compatible(candidate, event) and _event_at(event) is not None
                   and timedelta(0) <= _event_at(event) - moment <= timedelta(days=_order_window_days(candidate)) and _same_amount(event["quantity_decimal"], candidate["quantity"])]
        if matches:
            event = min(matches, key=lambda item: _event_at(item) - moment)
            settle(candidate, "booked", event, [], _differences({**candidate, "kind": "order"}, event)[1])
    # Zuletzt locker: dieselbe Art und derselbe Coin auf demselben Konto (Umschichtung: Konten desselben Instituts), Menge
    # hoechstens um die Haelfte anders, bis 36 Stunden (Umschichtung: 7 Tage). Was so gefunden wird, ist gebucht, weicht aber ab -
    # lieber als Abweichung gemeldet als ein zweites Mal gebucht.
    for candidate in waiting:
        if candidate["candidate_ordinal"] in results or candidate["kind"] not in ("buy", "sell", "transfer") and candidate.get("open_kind") != "order_time":
            continue
        moment = datetime.strptime(candidate["at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        quantity = _dec(candidate.get("quantity")) or Decimal(0)
        internal = candidate["kind"] == "transfer" and _profile(candidate["source"])["internal_transfers"] and candidate["rows"][0]["source"] == candidate["rows"][-1]["source"]
        window = timedelta(days=_order_window_days(candidate)) if candidate.get("open_kind") == "order_time" else (timedelta(days=7) if internal else WINDOWS[-1])
        def loose(event: Mapping[str, Any]) -> bool:
            if event["event_ref"] in used or event["asset_id"] != candidate["asset_id"] or _event_at(event) is None or abs(_event_at(event) - moment) > window:
                return False
            booked = _dec(event["quantity_decimal"]) or Decimal(0)
            if quantity <= 0 or not (quantity / 2 <= booked <= quantity * 2):
                return False
            if candidate["kind"] == "transfer":
                group = set(internal_accounts.get(candidate["account_id"], {candidate["account_id"]})) if internal else {candidate["account_id"]}
                return event["event_type"] == "transfer" and (event["account_id"] in group or event["related_account_id"] in group) and (
                    internal or event["related_account_id"] == candidate["related_account_id"])
            return event["event_type"] == (candidate.get("side") or candidate["kind"]) and event["account_id"] == candidate["account_id"]
        matches = [event for event in pool if loose(event)]
        if matches:
            event = min(matches, key=lambda item: abs(_event_at(item) - moment))
            differs, notes = _differences({**candidate, "kind": candidate.get("side") or candidate["kind"]}, event)
            if candidate["kind"] == "transfer" and (event["account_id"], event["related_account_id"]) != (candidate["account_id"], candidate["related_account_id"]):
                differs = differs + ["Konten"]
            if not differs:   # nur die Zeit weicht ab: sie ist die Abweichung, nicht zusaetzlich ein Hinweis
                differs = [next((note for note in notes if note.startswith("Zeitpunkt")), "Zeitpunkt")]
                notes = [note for note in notes if note not in differs]
            settle(candidate, "booked_differs", event, differs, notes)
    # Die zweite Seite eines gebuchten Transfers: Abgang oder Eingang ohne Gegenstueck im Export, dessen Gegenseite die Buchung schon
    # traegt (Kennung am Wallet, Menge bei Kraken gekuerzt, Ledger-Zeilen mit falscher Menge).
    for candidate in candidates:
        if candidate["candidate_ordinal"] in results or candidate.get("open_kind") not in ("transfer_in", "transfer_out", "direction_unknown"):
            continue
        moment = datetime.strptime(candidate["at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        quantities = _quantities(candidate)
        def other_side(event: Mapping[str, Any]) -> bool:
            if event["event_type"] != "transfer" or event["asset_id"] != candidate["asset_id"] or _event_at(event) is None or abs(_event_at(event) - moment) > WINDOWS[-1]:
                return False
            if not any(_same_amount(event["quantity_decimal"], value) for value in quantities):
                return False
            direction = candidate.get("direction")
            free_out = "out" not in sides[event["event_ref"]] and event["account_id"] == candidate["account_id"]
            free_in = "in" not in sides[event["event_ref"]] and event["related_account_id"] == candidate["account_id"]
            return (direction == "out" and free_out) or (direction == "in" and free_in) or (direction is None and (free_out or free_in))
        matches = [event for event in pool if other_side(event)]
        if matches:
            event = min(matches, key=lambda item: abs(_event_at(item) - moment))
            settle(candidate, "booked", event, [], [SECOND_SIDE_NOTE] + _differences({**candidate, "kind": "order"}, event)[1])
    for candidate in candidates:
        if candidate["candidate_ordinal"] not in results:
            if candidate["kind"] == "open":
                quantity = abs(_dec(candidate.get("quantity")) or Decimal(0))
                if candidate["open_kind"] == "fee_only" and (candidate["account_id"], candidate["asset_id"], candidate["local_date"]) in covered_days:
                    settle(candidate, "booked", None, [], [FEE_BOOKED_NOTE]); continue
                kind = candidate["open_kind"]
                if kind == "transfer_in" and 0 < quantity <= DUST:
                    kind = "dust"
                elif kind in ("transfer_in", "transfer_out", "direction_unknown") and candidate["ticker"] in _profile(candidate["source"])["unpaired_reason_by_ticker"]:
                    kind = _profile(candidate["source"])["unpaired_reason_by_ticker"][candidate["ticker"]]
                candidate["open_kind"] = kind
                settle(candidate, "open", None, [], [_open_reason_text(kind, candidate)])
            else:
                settle(candidate, "new")
    _avoid_same_second(candidates, results, events)
    return results


def _avoid_same_second(candidates: Sequence[dict[str, Any]], results: Mapping[int, dict[str, Any]], events: Sequence[Mapping[str, Any]]) -> None:
    """Neue Vorgaenge in einer Sekunde, in der derselbe Coin schon gebucht ist (auch Rewards) oder ein frueherer neuer Vorgang liegt,
    ruecken um ganze Sekunden nach hinten; Datum und Uhrzeit folgen in der Zeitzone des Vorgangs."""
    taken = {(event["asset_id"], _event_at(event)) for event in events if _event_at(event) is not None}
    fresh = [candidate for candidate in candidates if results[candidate["candidate_ordinal"]]["status"] == "new"]
    for candidate in sorted(fresh, key=lambda item: (item["at_utc"], item["candidate_ordinal"])):
        moment = _at(candidate); shifted = moment
        while (candidate["asset_id"], shifted) in taken:
            shifted += timedelta(seconds=1)
        taken.add((candidate["asset_id"], shifted))
        if shifted == moment:
            continue
        local = shifted.astimezone(BERLIN if candidate["time_zone"] == "Europe/Berlin" else UTC)
        candidate.update(at_utc=shifted.strftime("%Y-%m-%dT%H:%M:%SZ"), local_date=local.strftime("%Y-%m-%d"), local_time=local.strftime("%H:%M:%S"))
        results[candidate["candidate_ordinal"]]["notes"].append(SAME_SECOND_NOTE.format(seconds=int((shifted - moment).total_seconds())))


__all__ = [
    "GENERIC_PROFILE", "crypto_format_labels_v1", "OPEN_REASONS", "PROFILE", "REASONS", "SAME_SECOND_NOTE", "open_reasons_v1", "assemble_crypto_operations_v1", "detect_crypto_export_v1", "finish_crypto_v1",
    "learn_wallet_accounts_v1", "parse_crypto_export_v1", "review_crypto_operations_v1", "suggest_crypto_accounts_v1", "wallet_entries_v1",
]
