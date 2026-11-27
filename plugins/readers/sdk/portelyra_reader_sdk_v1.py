"""Portelyra Leser-SDK, Schnittstelle statement_reader_v1.

Stabile Hilfsfunktionen fuer Leser-Plugins unter ``plugins/readers/<plugin_id>/``. Ein Leser importiert nur die
Standardbibliothek und dieses Modul. Er laeuft im Kern abgeschottet (kein Netz, Lesezugriff nur auf den Beleg) und liefert
Kandidaten; pruefen, abgleichen und buchen bleibt Sache des Kerns. Die Schnittstelle ist offen beschrieben in
``contracts/statement-reader-plugin/v1/README.md``.

Die Funktionen stammen unveraendert aus dem bisherigen Cash-Import (rc.372); oeffentlich sind die Namen ohne Unterstrich.
"""
from __future__ import annotations

from collections import Counter
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import re
from typing import Any, Mapping
import xml.etree.ElementTree as ElementTree
import zipfile
from zoneinfo import ZoneInfo

API_VERSION = "statement_reader_v1"


class ReaderError(RuntimeError):
    """Ein Leser bricht mit einem Code aus der festen Liste ab (contracts/statement-reader-plugin/v1/error-codes.csv)."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise ReaderError(code)


# Ein offenes Anfuehrungszeichen zieht in einer grossen Datei den Rest in ein Feld; ueber der Vorgabe von 131 072 Zeichen warf csv
# dann einen Fehler, den kein Leser abfing. Die Belege sind ohnehin in der Groesse begrenzt (Selbsttest rc.379).
csv.field_size_limit(64 * 1024 * 1024)

TIME_ZONE = "Europe/Berlin"

CENT = Decimal("0.01")

def _cents(text: Any) -> Decimal | None:
    if text is None or str(text).strip() == "":
        return None
    raw = str(text).strip().replace(" ", "").replace(" ", "").replace("€", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        value = Decimal(raw)
        if not value.is_finite():
            return None
        rounded = value.quantize(CENT)
    except (InvalidOperation, ArithmeticError):   # etwa "3e78" aus gekippten Bytes (Selbsttest rc.379): nicht lesbar statt Absturz
        return None
    # Spreadsheets store cents as binary floats; anything beyond float noise is not a cent amount.
    if abs(value - rounded) > Decimal("0.000001"):
        return None
    return rounded

def _german_amount(text: str) -> Decimal | None:
    """Immer deutsches Format: "-2.000" sind zweitausend, nicht zwei."""
    raw = (text or "").replace("€", "").replace("\xa0", "").replace(" ", "").strip()
    if not raw:
        return None
    return _cents(raw.replace(".", "").replace(",", "."))

def _english_amount(text: str) -> Decimal | None:
    """Immer englisches Format: "1,500.00" sind eintausendfuenfhundert, Komma trennt Tausender."""
    raw = (text or "").replace("€", "").replace("\xa0", "").replace(" ", "").strip()
    if not raw:
        return None
    return _cents(raw.replace(",", ""))

def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", ""} else text

# ---------------------------------------------------------------- xlsx reader
def _xlsx_rows(source: bytes) -> list[list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(source))
        sheet_name = sorted(name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))[0]
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root if node.tag.endswith("}si")]
        root = ElementTree.fromstring(archive.read(sheet_name))
    # Auch eine beschaedigte Datei (Selbsttest rc.379: gekippte Bytes, anderer Zeichensatz) weist mit Grund ab statt abzustuerzen.
    except (zipfile.BadZipFile, zipfile.LargeZipFile, IndexError, KeyError, ValueError, EOFError, OSError, RuntimeError, ElementTree.ParseError):
        _abort("cash_statement_source_invalid")
    try:
        return _xlsx_sheet_rows(root, shared)
    except (ValueError, IndexError):
        _abort("cash_statement_source_invalid")


def _xlsx_sheet_rows(root: Any, shared: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in (node for node in root.iter() if node.tag.endswith("}row")):
        values: dict[int, str] = {}
        for cell in (node for node in row if node.tag.endswith("}c")):
            reference = cell.get("r", "")
            letters = re.match(r"[A-Z]+", reference)
            if letters is None:
                continue
            column = 0
            for char in letters.group(0):
                column = column * 26 + ord(char) - 64
            kind = cell.get("t", "")
            if kind == "inlineStr":
                text = "".join(cell.itertext())
            else:
                value = next((node.text for node in cell if node.tag.endswith("}v")), None)
                text = shared[int(value)] if kind == "s" and value is not None else (value or "")
            values[column - 1] = text
        rows.append([values.get(index, "") for index in range(max(values) + 1)] if values else [])
    return rows

def _delimited_rows(source: bytes) -> list[list[str]]:
    try:
        text = source.decode("utf-8-sig")
    except UnicodeDecodeError:   # fuenf Bytes kennt cp1252 nicht (0x81, 0x8D, 0x8F, 0x90, 0x9D): Ersatzzeichen statt Absturz (rc.379)
        text = source.decode("cp1252", errors="replace")
    delimiter = ";" if text.count(";") > text.count(",") else ","
    try:
        return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
    except csv.Error:   # etwa ein Nullbyte in einer beschaedigten Datei (Selbsttest rc.379)
        _abort("cash_statement_source_invalid")

def _named_rows(source: bytes) -> list[dict[str, str]]:
    """Tolerant reader: BOM or none, semicolon or comma, quoted fields, blank lines."""
    text = source.decode("utf-8-sig", errors="replace")
    header = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = ";" if header.count(";") >= header.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    try:
        fieldnames = reader.fieldnames
    except csv.Error:   # etwa ein Nullbyte in der Kopfzeile einer beschaedigten Datei (Selbsttest rc.379)
        _abort("cash_statement_source_invalid")
    if not fieldnames:
        _abort("cash_statement_header_invalid")
    names = [(name or "").strip().lstrip("\ufeff") for name in reader.fieldnames]
    # Ueberzaehlige Felder legt csv unter dem Schluessel None als Liste ab; bei doppelten Spaltennamen rutschte die Liste sonst in eine
    # Spalte und liess den Leser abstuerzen (Selbsttest rc.379). Eine Liste gilt als leer.
    text_of = lambda value: value.strip() if isinstance(value, str) else ""
    try:
        return [{name: text_of(value) for name, value in zip(names, row.values())} for row in reader if any(text_of(value) for value in row.values())]
    except csv.Error:   # etwa ein Nullbyte in einer beschaedigten Datei (Selbsttest rc.379)
        _abort("cash_statement_source_invalid")

# ---------------------------------------------------------------- Boersen: nur das EUR-Konto
# Die Exporte der Kryptoboersen enthalten alle Assets. Hier zaehlt allein das
# Euro-Guthaben: Ein- und Auszahlungen, Kauf und Verkauf gegen Euro samt Gebuehr.
# Die Krypto-Seite derselben Buchung gehoert zum Asset, nicht zu Cash (#184).
def _utc_stamp_to_local_date(stamp: str) -> str | None:
    """Boersen stempeln in UTC; der Buchungstag zaehlt in Europe/Berlin (23:30 UTC ist oft schon morgen)."""
    text = (stamp or "").replace(" UTC", "").replace("T", " ").replace("Z", "").strip()[:19]
    try:
        moment = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return moment.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(TIME_ZONE)).date().isoformat()
    except (ValueError, OverflowError):   # auch 9999-12-31 23:30 UTC (Selbsttest rc.379)
        return None

def _exchange_result(candidates: list[dict[str, Any]], diagnostics: list[dict[str, Any]],
                     opening: Decimal | None = None, closing: Decimal | None = None) -> dict[str, Any]:
    if not candidates:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    summary = {"opening_balance_decimal": opening, "closing_balance_decimal": closing, "period_from": days[0], "period_to": days[-1]}
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}

def _exchange_row(ordinal: int, local_date: str, cash: Decimal, text: str, balance: Decimal | None = None) -> dict[str, Any]:
    return {"source_row_ordinal": ordinal, "local_date": local_date, "kind": "deposit" if cash > 0 else "withdrawal",
            "amount_decimal": _plain(abs(cash)), "balance_after_decimal": None if balance is None else _plain(balance), "text": text}


# PDF-Text: Der Kern wandelt PDF-Belege vor dem Aufruf mit ``pdftotext -layout -nopgbrk`` in Text um und gibt ihn mit. Ein
# Leser startet selbst kein Programm. Fuer Textdateien gilt wie bisher UTF-8 mit Ersatzzeichen.
_PDF_TEXT: dict[str, tuple[str, ...]] = {}


def _register_pdf_text(source: bytes, lines: list[str] | tuple[str, ...]) -> None:
    """Nur fuer den Kern-Host: hinterlegt den Text eines PDF-Belegs."""
    _PDF_TEXT[hashlib.sha256(source).hexdigest()] = tuple(lines)


def _pdf_text(source: bytes, file_name: str) -> list[str]:
    if not file_name.lower().endswith(".pdf"):
        return source.decode("utf-8", errors="replace").splitlines()
    lines = _PDF_TEXT.get(hashlib.sha256(source).hexdigest())
    if lines is None:
        _abort("statement_reader_pdf_text_missing")
    return list(lines)



# ---------------------------------------------------------------- Wertpapier- und Devisenbelege (rc.374)
# Unveraendert aus dem bisherigen Wertpapier-Import. Gruende tragen nur ihren Code: REASONS liefert den Code selbst, den Text setzt
# der Kern aus seiner festen Liste (ein unbekannter Code verwirft das Ergebnis).
class _CodeAsText(dict):
    def __missing__(self, key: str) -> str:
        return key


REASONS = _CodeAsText()


def _reason(code: str, **fields: Any) -> dict[str, Any]:
    return {"status": "not_importable", "reason_code": code, "reason": REASONS[code], **fields}


CUR = r"(?:EUR|USD|GBP|CHF|DKK|CAD|HKD|NOK|SEK|JPY|AUD)"

NUM = r"-?\d{1,3}(?:\.\d{3})*(?:,\d+)?"

INFORMATION = re.compile(r"Depotauszug|Informationsbogen|Ex-post|Kosteninformation|Kostenaufstellung|Quartalsaufstellung|Mitteilung über|Umlagerung|Rechnungsabschluss")

TAX_DOCUMENT = re.compile(r"Jahressteuerbescheinigung|Steuerbescheinigung|Erträgnisaufstellung|Verlustbescheinigung|Verlustverrechnung|Entgeltaufstellung|Steuerneuberechnung")

def _json_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()

def _german(text: str) -> Decimal:
    try:
        return Decimal(text.strip().rstrip("-").strip().replace(".", "").replace(",", "."))
    except InvalidOperation:
        _abort("securities_statement_source_invalid")

def _signed(text: str) -> Decimal:
    value = _german(text.strip().lstrip("+-"))
    return -value if text.strip().startswith("-") or text.strip().endswith("-") else value

def _day(text: str) -> str:
    """TT.MM.JJJJ als ISO-Tag. Einen Tag, den es nicht gibt (verstuemmelter Beleg, etwa 32.09.), gibt kein Leser weiter: Abbruch mit
    Code statt eines ungueltigen Tags im Ergebnis (Selbsttest rc.379)."""
    try:
        day, month, year = text.strip().split(".")
        if not (len(day) == len(month) == 2 and len(year) == 4):
            raise ValueError(text)
        return date(int(year), int(month), int(day)).isoformat()
    except (ValueError, OverflowError):
        _abort("securities_statement_source_invalid")

def _find(pattern: str, text: str, flags: int = 0, group: int = 1) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(group) if match else None

def _candidate(kind: str, profile: str, **fields: Any) -> dict[str, Any]:
    value = {"status": "candidate", "kind": kind, "profile": profile, "isin": None, "security_name": None, "local_date": None,
             "local_time": None, "quantity": None, "unit_price": None, "gross_amount": None, "fee_amount": "0", "eligible_quantity": None,
             "order_ref": None, "depot_ref": None, "ex_date": None, "net_amount": None, "taxes_amount": None, "withholding_amount": None,
             "bank_gain": None, "fee_on_cash_statement": False, "currency": None, "valuta": None, "statement_checked": False}
    value.update(fields)
    # Formgrenzen des Kerns je Kandidat: Ein Tag oder eine Uhrzeit, die es nicht gibt (verstuemmelter Beleg), bricht mit Code ab, statt dass
    # der Kern das ganze Ergebnis als Formfehler verwirft (Selbsttest rc.379).
    for key in ("local_date", "ex_date", "valuta", "record_date"):
        if value.get(key) is not None and not _iso_day_ok(value[key]):
            _abort("securities_statement_source_invalid")
    if value.get("local_time") is not None and not (isinstance(value["local_time"], str) and _CLOCK.match(value["local_time"])):
        _abort("securities_statement_source_invalid")
    return value

_CLOCK = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$")

def _iso_day_ok(text: Any) -> bool:
    if not isinstance(text, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", text) is None:
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True

def _csv_rows(text: str, columns: set[str]) -> list[dict[str, str]] | None:
    try:
        reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
        if reader.fieldnames is None or not columns <= set(reader.fieldnames):
            return None
        return [{key: (value or "").strip() for key, value in row.items() if key is not None} for row in reader]
    except csv.Error:
        return None

def _multi(candidates: list[dict[str, Any]], reasons: Mapping[str, int]) -> dict[str, Any]:
    return {"status": "multi", "candidates": candidates, "row_reasons": dict(reasons)}

def _tax_document(text: str) -> bool:
    """Steuerunterlagen erkennt der Kopf; Abrechnungen nennen die Jahressteuerbescheinigung nur im Fusstext."""
    head = "\n".join(line for line in text.splitlines()[:40])
    return TAX_DOCUMENT.search(head) is not None and re.search(r"Wertpapierabrechnung|Dividendenabrechnung|Ertragsgutschrift|Dividendengutschrift|^Dividende\s*$", head, re.M) is None

def _information(text: str) -> bool:
    head = "\n".join(text.splitlines()[:60])
    return INFORMATION.search(head) is not None and re.search(r"Wertpapierabrechnung|Dividendenabrechnung|^Dividende\s*$|^Vorabpauschale\s*$|Depoteinlieferung|Depotauslieferung", text, re.M) is None



# ---------------------------------------------------------------- Krypto-Exporte (rc.376)
# Unveraendert aus dem bisherigen Krypto-Import. Ein Leser sammelt die Zeilen einer Datei mit CryptoSheet; Paarung von Transfers
# ueber Boersen hinweg, Wallet-Zuordnung und Buchung bleiben im Kern.
UTC = timezone.utc
BERLIN = ZoneInfo("Europe/Berlin")


_KRAKEN_CODES = {"XXBT": "BTC", "XBT": "BTC", "XETH": "ETH", "XXRP": "XRP", "XLTC": "LTC", "XXDG": "DOGE", "XDG": "DOGE", "XXLM": "XLM",
                 "XZEC": "ZEC", "XXMR": "XMR", "ETH2": "ETH", "ZEUR": "EUR", "EUR.HOLD": "EUR", "EUR.M": "EUR"}

_NAMES = {"bitcoin": "BTC", "ether": "ETH", "ethereum": "ETH", "solana": "SOL", "xrp": "XRP", "polkadot": "DOT", "chainlink": "LINK",
          "cardano": "ADA", "litecoin": "LTC", "avalanche": "AVAX", "polygon": "POL", "tron": "TRX", "stellar": "XLM", "dogecoin": "DOGE"}

_UNITS = {"satoshi": (Decimal("1e-8"), "BTC"), "sat": (Decimal("1e-8"), "BTC"), "wei": (Decimal("1e-18"), "ETH"), "gwei": (Decimal("1e-9"), "ETH")}

def _plain_or_none(value: Decimal | None) -> str | None:
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
    # Ein Exponent jenseits jeder Menge (etwa "1e9999999" aus gekippten Bytes) ist keine Zahl eines Exports (Selbsttest rc.379).
    if not result.is_finite() or result.adjusted() > 30 or result.adjusted() < -30:
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
    except (ValueError, OverflowError):   # OverflowError: Jahr 1 oder 9999 mit Zonenversatz
        return None

def _iso_time(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat((text or "").strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    try:
        return parsed.astimezone(UTC) if parsed.tzinfo else None
    except OverflowError:   # Jahr 1 oder 9999 mit Zonenversatz
        return None

class _Rows(list):
    """Zeilen eines Exports; ``file_lines`` nennt je Zeile ihre Zeilennummer in der Datei (1 = erste Zeile der Datei, wie in einer
    Tabellenkalkulation; Vorspann ueber der Kopfzeile und Felder ueber mehrere Zeilen mitgezaehlt)."""

    def __init__(self) -> None:
        super().__init__()
        self.file_lines: list[int] = []


def _rows(text: str, start_marker: str | None = None) -> list[dict[str, str]]:
    rows = _Rows()
    lines = text.splitlines()
    start = 0
    if start_marker:
        start = next((index for index, line in enumerate(lines[:30]) if line.startswith(start_marker)), None)
        if start is None:
            return rows
    if start >= len(lines):
        return rows
    delimiter = max(",;\t", key=lines[start].count)
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delimiter)
    for row in reader:
        # line_num zaehlt die gelesenen Zeilen ab der Kopfzeile bis zum Ende dieser Zeile; Zeilenumbrueche in Feldern zurueckrechnen.
        inner = sum(item.count("\n") for value in row.values() for item in (value if isinstance(value, list) else [value]) if isinstance(item, str))
        rows.append({(key or "").strip(): (value or "").strip() for key, value in row.items() if key is not None})
        rows.file_lines.append(start + reader.line_num - inner)
    return rows

def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


_CRYPTO_TEXT_FIELDS = ("file_name", "wallet", "zone", "transaction_id", "hash", "address", "group", "quote")
_PLAIN_POSITIVE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_PLAIN_SIGNED = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


# Grund je verworfener Zeile (rc.379, Vorgabe: Zeile und Feld als Grund): Feld und Problem aus diesen Listen; den Text
# setzt der Kern. "number" steht fuer eine Zahl, die sich keinem Feld zuordnen laesst (riesiger Exponent).
CRYPTO_DETAIL_FIELDS = ("time", "ticker", "quantity", "fee_quantity", "eur", "eur_fee", "price", "number", "wallet", "transaction_id", "hash",
                        "address", "group", "quote", "file_name", "zone")
CRYPTO_DETAIL_PROBLEMS = ("missing", "unreadable", "negative", "too_long", "out_of_range")
_CRYPTO_DETAIL_LIMIT = 5000


def _crypto_row_problem(row: Mapping[str, Any]) -> tuple[str, str] | None:
    """Formgrenzen des Kerns je Zeile (validate_crypto_result_v1): Jahr mit vier Stellen, Ticker bis 40, Texte bis 400 Zeichen, Mengen und
    Betraege als Dezimaltext, Gebuehren und Euro nie negativ. Eine Zeile darueber - verstuemmelter Beleg, etwa ein offenes Anfuehrungszeichen,
    das die folgenden Zeilen in ein Feld zieht - wird mit Feld und Problem verworfen, statt dass der Kern das ganze Ergebnis verwirft
    (Selbsttest rc.379). Liefert das erste verletzte Feld oder None."""
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", row["at_utc"]) is None or row["at_utc"][:1] == "0":
        return "time", "out_of_range"
    if not 0 < len(row["ticker"]) <= 40:
        return "ticker", "too_long"
    if _PLAIN_SIGNED.match(row["quantity"]) is None:
        return "quantity", "unreadable"
    for key in ("fee_quantity", "eur", "eur_fee"):
        if row[key] is not None and _PLAIN_POSITIVE.match(row[key]) is None:
            return key, "negative" if row[key].startswith("-") else "unreadable"
    for key in _CRYPTO_TEXT_FIELDS:
        if not isinstance(row[key], str) or len(row[key]) > 400:
            return key, "too_long"
    return None


def _crypto_row_key(row: Mapping[str, Any]) -> str:
    return _json_sha256(["crypto_row", row["source"], row["wallet"], row["at_utc"], row["ticker"], row["kind"], row["quantity"], row["fee_quantity"], row["eur"],
                         row["transaction_id"], row["hash"], row["group"]])


class CryptoSheet:
    """Sammelt die Zeilen einer Datei: lesbare Bewegungen und gezaehlte Gruende fuer den Rest (wie _Sheet im Kern, Zeitzone je Quelle)."""

    def __init__(self, source: str, file_name: str, zone: str):
        self.source, self.file_name, self.zone, self.rows, self.reasons, self.details = source, file_name, zone, [], Counter(), []
        self.file_lines: list[int] | None = None

    def numbered(self, rows: list[dict[str, str]]):
        """Wie enumerate(rows, 1); merkt sich die Zeilennummern der Datei (aus csv_dict_rows), damit eine verworfene Zeile in der
        Vorschau mit ihrer Zeile in der Datei erscheint."""
        self.file_lines = list(getattr(rows, "file_lines", None) or []) or None
        return enumerate(rows, 1)

    def skip(self, code: str, row_no: int | None = None, field: str | None = None, problem: str | None = None) -> None:
        """Zeile mit Grund zaehlen; mit Nummer, Feld und Problem erscheint sie in der Vorschau einzeln ("Zeile 18 der Datei nicht gebucht:
        Euro-Betrag ist negativ"). Die Zeile der Datei kennt das Blatt, wenn der Leser seine Zeilen ueber ``numbered`` zaehlt."""
        self.reasons[code] += 1
        if isinstance(row_no, int) and not isinstance(row_no, bool) and row_no >= 0 and field in CRYPTO_DETAIL_FIELDS \
                and problem in CRYPTO_DETAIL_PROBLEMS and len(self.details) < _CRYPTO_DETAIL_LIMIT:
            detail = {"row_no": row_no, "reason_code": code, "field": field, "problem": problem}
            if self.file_lines and 1 <= row_no <= len(self.file_lines):
                detail["line"] = self.file_lines[row_no - 1]
            self.details.append(detail)

    def add(self, row_no: int, wallet: str, at: datetime | None, ticker: str, kind: str, quantity: Decimal | None, **extra: Any) -> None:
        missing = "time" if at is None else "ticker" if not ticker else "quantity" if quantity is None else None
        if missing:
            self.skip("crypto_unreadable_row", row_no, missing, "missing"); return
        try:
            row = self._row(row_no, wallet, at, ticker, kind, quantity, extra)
        except (ArithmeticError, ValueError, OverflowError):   # etwa ein riesiger Exponent in einem verstuemmelten Beleg
            self.skip("crypto_unreadable_row", row_no, "number", "unreadable"); return
        problem = _crypto_row_problem(row)
        if problem:
            self.skip("crypto_unreadable_row", row_no, *problem); return
        row["row_key"] = _crypto_row_key(row)
        self.rows.append(row)

    def _row(self, row_no: int, wallet: str, at: datetime, ticker: str, kind: str, quantity: Decimal, extra: Mapping[str, Any]) -> dict[str, Any]:
        row = {"profile": "crypto_row", "source": self.source, "file_name": self.file_name, "row_no": row_no, "wallet": wallet,
               "at_utc": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "zone": extra.get("zone") or self.zone, "ticker": ticker,
               "kind": kind, "quantity": _plain_or_none(quantity), "fee_quantity": _plain_or_none(extra.get("fee_quantity")),
               "eur": _plain_or_none(extra.get("eur")), "eur_fee": _plain_or_none(extra.get("eur_fee")), "transaction_id": (extra.get("transaction_id") or "").strip(),
               "hash": (extra.get("hash") or "").strip(), "address": (extra.get("address") or "").strip(), "group": (extra.get("group") or "").strip(),
               "quote": extra.get("quote") or ""}
        if extra.get("window_from") is not None:   # BSDEX: Anlage der Order, fuer die Zuordnung der Ausfuehrungen (nicht Teil der Kennung)
            row["window_from_utc"] = extra["window_from"].strftime("%Y-%m-%dT%H:%M:%SZ")
        if extra.get("at_last_execution"):   # BSDEX, stornierte Order mit Teilausfuehrung: Zeit ist die ihrer letzten Ausfuehrung
            row["at_last_execution"] = True
        return row

    def result(self) -> dict[str, Any]:
        value = {"status": "multi", "candidates": self.rows, "row_reasons": dict(self.reasons)}
        if self.details:   # nur wenn Zeilen einzeln verworfen wurden; sonst bleibt das Ergebnis wie bisher
            value["row_details"] = list(self.details)
        return value


# ---------------------------------------------------------------- Reward-Exporte (rc.377)
# Unveraendert aus dem bisherigen Reward-Import (statement_exchange_reward_adapter_v1). Ein Leser beschreibt sein Format als Profil
# (Trennzeichen, Zahlenformat, Spalten je Rolle, Reward-Arten, Bewertung, Gebuehr) und liest mit reward_export. Er liefert je Zeile
# ihre Zellen, die Kennung der Boerse, die Merkmale fuer doppelte Zeilen ueber Dateien und - bei einem Reward - Coin, Menge, Zeit,
# Gebuehr, Konto und Bewertung. Schluessel, doppelte Zeilen, Zeitraum und Kandidaten bildet der Kern.
def _reward_norm(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").split())


def _reward_decimal(value: str, *, locale: str) -> str | None:
    text = str(value).strip().replace(" ", "").replace(" ", "")
    text = re.sub(r"[^0-9,\.\-+]", "", text)
    if not text:
        return None
    if locale == "de_DE":
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
    elif "," in text and "." not in text:
        text = text.replace(",", ".")
    if text.startswith("+"):
        text = text[1:]
    try:
        number = Decimal(text)
    except InvalidOperation:
        return None
    if not number.is_finite():
        return None
    if number == 0:
        return "0"
    rendered = format(number.copy_abs(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _reward_currency(value: str) -> str | None:
    text = str(value).strip()
    explicit = text.upper()
    if re.fullmatch(r"[A-Z]{3}", explicit):
        return explicit
    symbols = [("€", "EUR"), ("£", "GBP")]
    hits = [code for symbol, code in symbols if symbol in text]
    return hits[0] if len(hits) == 1 else None


def _reward_subtract(left: str | None, right: str | None) -> str | None:
    if left is None or right is None:
        return None
    value = Decimal(left) - Decimal(right)
    if value <= 0:
        return None
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _reward_time(value: str) -> tuple[str, str] | None:
    text = value.strip()
    cleaned = re.sub(r"\s+(UTC|GMT)$", "", text, flags=re.IGNORECASE).replace("T", " ").rstrip("Z")
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M", "%d.%m.%Y, %H:%M:%S", "%d.%m.%Y, %H:%M"):
        try:
            parsed = datetime.strptime(cleaned, pattern)
            return parsed.date().isoformat(), parsed.time().replace(microsecond=0).isoformat()
        except ValueError:
            continue
    return None


def _reward_table(source: bytes, profile: Mapping[str, Any]) -> tuple[list[str], list[list[str]]]:
    if not isinstance(source, bytes) or not 0 < len(source) <= 32_000_000 or b"\x00" in source:
        _abort("statement_exchange_adapter_source_invalid")
    text = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            text = source.decode(encoding, errors="strict"); break
        except UnicodeDecodeError:
            continue
    if text is None:
        _abort("statement_exchange_adapter_source_invalid")
    lines = text.splitlines()
    aliases = {alias for values in profile["roles"].values() for alias in values}   # wie im Profil: klein geschrieben
    selected = None
    for start in range(min(profile["header_search"], len(lines))):
        try:
            rows = list(csv.reader(io.StringIO("\n".join(lines[start:])), delimiter=profile["delimiter"], strict=True))
        except csv.Error:
            continue
        # Weitere Spalten der Boerse duerfen Bezeichnungen wiederholen; die Rolle bekommt den ersten Treffer ihrer Liste.
        if len(rows) >= 2 and any(_reward_norm(value) in aliases for value in rows[0]):
            selected = ([_reward_norm(value) for value in rows[0]], rows[1:]); break
    if selected is None:
        _abort("statement_exchange_adapter_header_invalid")
    headers, rows = selected
    if not rows or any(len(row) != len(headers) for row in rows):
        _abort("statement_exchange_adapter_source_invalid")
    return headers, rows


def _reward_indices(headers: list[str], profile: Mapping[str, Any]) -> dict[str, int]:
    result = {}
    for role, aliases in profile["roles"].items():
        hit = next((headers.index(alias) for alias in aliases if alias in headers), None)
        if hit is not None:
            result[role] = hit
    if not set(profile["required"]) <= set(result):
        _abort("statement_exchange_adapter_header_invalid")
    return result


_REWARD_DUPLICATE_ROLES = ("time", "event", "subtype", "asset", "quantity", "fee", "account")


def _reward_row(source: list[str], indices: Mapping[str, int], profile: Mapping[str, Any]) -> dict[str, Any]:
    value = lambda role: source[indices[role]].strip() if role in indices else ""
    locale = profile["locale"]
    signature = []
    for role in _REWARD_DUPLICATE_ROLES:
        raw = value(role)
        number = _reward_decimal(raw, locale=locale) if role in {"quantity", "fee"} else None
        signature.append(number if number is not None else _reward_norm(raw.replace(" ", " ")))
    row: dict[str, Any] = {"cells": list(source), "row_id": value("row_id"), "signature": signature}
    event, subtype = _reward_norm(value("event")), _reward_norm(value("subtype"))
    if not (event in profile["reward_events"] or (event == "earn" and subtype in profile.get("reward_subtypes", ()))):
        row["kind"] = "other"
        return row
    asset, quantity, parsed_time = value("asset").upper(), _reward_decimal(value("quantity"), locale=locale), _reward_time(value("time"))
    if not asset or quantity in {None, "0"} or parsed_time is None:
        row["kind"] = "invalid"
        return row
    fee = _reward_decimal(value("fee"), locale=locale)
    unit_raw, total_raw = value("unit_price"), value("fiat_total")
    currency = _reward_currency(value("price_currency")) or _reward_currency(total_raw) or _reward_currency(unit_raw) or profile.get("default_currency")
    mode, unit, total = profile["valuation"], _reward_decimal(unit_raw, locale=locale), _reward_decimal(total_raw, locale=locale)
    if mode == "net_fiat_total":
        total = _reward_subtract(total, _reward_decimal(value("fiat_fee"), locale=locale))
    if mode in {"prefer_fiat_total", "fiat_total", "net_fiat_total"} and total not in {None, "0"} and currency is not None:
        valuation = {"source_value_mode": "fiat_total", "price_currency": currency, "source_unit_price_decimal": None, "source_fiat_total_decimal": total}
    elif mode in {"prefer_fiat_total", "unit_price"} and unit not in {None, "0"} and currency is not None:
        valuation = {"source_value_mode": "unit_price", "price_currency": currency, "source_unit_price_decimal": unit, "source_fiat_total_decimal": None}
    else:
        valuation = {"source_value_mode": "none", "price_currency": currency, "source_unit_price_decimal": None, "source_fiat_total_decimal": None}
    row.update(kind="reward", asset=asset, quantity=quantity, local_date=parsed_time[0], local_time=parsed_time[1],
               fee=None if fee == "0" else fee, account=value("account") or profile["account"], valuation=valuation)
    return row


def reward_export(source: bytes, profile: Mapping[str, Any]) -> dict[str, Any]:
    """Ein Reward-Export nach dem Profil des Lesers: Zeitzone und Rolle der Gebuehr des Formats, je Zeile das Ergebnis."""
    headers, table = _reward_table(source, profile)
    indices = _reward_indices(headers, profile)
    return {"time_zone": profile["time_zone"], "fee_role": profile["fee_role"], "rows": [_reward_row(row, indices, profile) for row in table]}


# Uebertragung zwischen Kern und Plugin: Dezimalzahlen bleiben exakt, Tupel werden Listen.
def _to_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"decimal_text": str(value)}
    if isinstance(value, datetime):
        return {"datetime_text": value.isoformat()}
    if isinstance(value, (bytes, bytearray)):   # Erzeuger (rc.379): Belege als Bytes
        import base64  # noqa: PLC0415
        return {"bytes_base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dict):
        return {key: _to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(item) for item in value]
    return value


def _from_json(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"decimal_text"} and isinstance(value["decimal_text"], str):
            return Decimal(value["decimal_text"])
        if set(value) == {"datetime_text"} and isinstance(value["datetime_text"], str):
            return datetime.fromisoformat(value["datetime_text"])
        if set(value) == {"bytes_base64"} and isinstance(value["bytes_base64"], str):
            import base64  # noqa: PLC0415
            return base64.b64decode(value["bytes_base64"])
        return {key: _from_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_json(item) for item in value]
    return value


# Oeffentliche Namen der Schnittstelle.
reward_norm = _reward_norm
abort = _abort
cents = _cents
german_amount = _german_amount
english_amount = _english_amount
plain = _plain
xlsx_rows = _xlsx_rows
delimited_rows = _delimited_rows
named_rows = _named_rows
pdf_text = _pdf_text
utc_stamp_to_local_date = _utc_stamp_to_local_date
cash_exchange_result = _exchange_result
cash_exchange_row = _exchange_row
candidate = _candidate
csv_rows = _csv_rows
german_day = _day
find = _find
german_decimal = _german
is_information = _information
is_tax_document = _tax_document
multi_result = _multi
reason = _reason
signed_decimal = _signed
json_sha256 = _json_sha256
plain_or_none = _plain_or_none
crypto_number = _number
crypto_ticker = _ticker
KRAKEN_CODES = _KRAKEN_CODES
COIN_NAMES = _NAMES
COIN_UNITS = _UNITS
parse_time = _parse_time
iso_time = _iso_time
csv_dict_rows = _rows
crypto_row_key = _crypto_row_key
decimal_or_none = _dec
