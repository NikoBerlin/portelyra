"""Experimenteller generischer Leser (#514): typische Ausdruecke erkennen, Zuordnung bestaetigen, ohne Gewaehr.

Festlegung (25.10.2026): ein Importer fuer Institute ohne eigenen Leser. Er erkennt typische Spaltennamen und
Vorgangsbezeichnungen (deutsch, englisch) und schlaegt daraus eine Zuordnung "Spalte -> Feld" und "Ausdruck -> Buchungsart"
vor. Wer ihn nutzt, bestaetigt oder aendert die Zuordnung; sie wird als Profil je Format (Kopfzeile) lokal gespeichert und greift
beim naechsten Import von selbst. Ausdruecklich experimentell und ohne Gewaehr; spaeter als Plugin (#486).

Gebucht wird wie bei den festen Lesern: Die Vorgaenge laufen durch die Pruefung gegen den Bestand, die Vorschau mit FIFO-Probe
und die Bestaetigung des Aktivitaeten-CSV-Imports. Unklare Zeilen bleiben offen mit Grund; geraten wird nichts. Betraege und
Mengen bleiben exakte Dezimalzahlen.

Zwei Leser im Katalog der Importe: Wertpapiere (Zeilen mit ISIN, Buchungsart Kauf, Verkauf, Dividende) und Krypto (Zeilen mit
Coin-Kuerzel, Kauf und Verkauf gegen EUR, Ein- und Ausgaenge). Empfehlung: Fuer Institute mit festem, geprueftem
Leser hat dieser Vorrang; der generische Leser ist fuer Institute ohne geprueften Leser gedacht und ausdruecklich experimentell.
"""

from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from migrations.reference import crypto_statement_import_v1 as crypto

CONTRACT = "generic_statement_import_v1"
PROFILE_AREA = "generic-import-v1"
PROFILE_FILE = "profiles.json"
PROFILE_VERSION = 1
MAX_PROFILES = 200
TIME_ZONE = "Europe/Berlin"
FIELDS = ("date", "time", "action", "isin", "asset", "quantity", "price", "amount", "fee", "currency", "reference", "status")
FIELD_LABELS = {"date": "Datum", "time": "Uhrzeit", "action": "Vorgang", "isin": "ISIN", "asset": "Wertpapier oder Coin", "quantity": "Menge",
                "price": "Kurs je Einheit", "amount": "Betrag (Kurswert)", "fee": "Gebühr", "currency": "Währung", "reference": "Kennung", "status": "Status"}
KINDS = ("buy", "sell", "dividend", "deposit", "withdrawal", "reward", "interest", "fee", "cash_in", "cash_out", "trade", "ignore")
KIND_LABELS = {"buy": "Kauf", "sell": "Verkauf", "dividend": "Dividende", "deposit": "Eingang (Einlieferung)", "withdrawal": "Ausgang (Auslieferung)",
               "reward": "Reward / Staking", "interest": "Zinsen", "fee": "Gebühr", "cash_in": "Einzahlung (Geld)", "cash_out": "Auszahlung (Geld)",
               "trade": "Handel (Vorzeichen der Menge entscheidet)", "ignore": "nicht buchen"}
REASONS = {
    "generic_no_table": "Keine Tabelle erkannt – der generische Leser liest CSV-Exporte mit Kopfzeile",
    "generic_unmapped": "Zuordnung unvollständig: Datum, Vorgang oder Menge fehlen – bitte die Zuordnung ergänzen",
    "generic_unknown_action": "Vorgang nicht zugeordnet – bitte die Bezeichnung einer Buchungsart zuordnen",
    "generic_incomplete": "Pflichtangaben der Zeile fehlen oder sind nicht lesbar",
    "generic_date_unreadable": "Datum nicht lesbar",
    "generic_not_eur": "Betrag nicht in EUR – bitte manuell buchen",
    "generic_no_isin": "Keine ISIN – ein Wertpapier lässt sich ohne ISIN nicht sicher zuordnen",
    "generic_cash_movement": "Geldbewegung (Ein-/Auszahlung, Zinsen, Gebühr) – gehört zum Cash-Auszug",
    "generic_delivery": "Ein- oder Auslieferung – bitte manuell buchen",
    "generic_reward": "Reward oder Staking – liest der Reward-Import",
    "generic_ignored": "laut Zuordnung nicht zu buchen",
    "generic_not_executed": "laut Status nicht ausgeführt (storniert, vorläufig oder abgelehnt)",
}

# Typische Spaltennamen je Feld, normalisiert (klein, ohne Leer- und Satzzeichen). Die Reihenfolge entscheidet bei Gleichstand.
_HEADER_WORDS: dict[str, tuple[str, ...]] = {
    "date": ("ausfuehrungszeitpunkt", "ausführungszeitpunkt", "ausfuehrungsdatum", "ausführungsdatum", "executiontime", "executedat",
             "datum", "date", "buchungstag", "buchungsdatum", "handelstag", "handelsdatum", "ausfuehrungszeitpunkt", "ausführungszeitpunkt",
             "ausfuehrungsdatum", "ausführungsdatum", "zeitpunkt", "timestamp", "datetime", "time", "operationdate", "erstellt", "created",
             "createdat", "transaktionsdatum", "transactiondate", "tradedate", "dateutc", "dateutccoordinateduniversaltime", "valuta", "wertstellung"),
    "time": ("uhrzeit", "zeit", "ausfuehrungszeit", "ausführungszeit", "tradetime"),
    "action": ("transaktionstyp", "transaktionsart", "transactiontype", "buchungsart", "vorgang", "vorgangsart", "art", "typ", "type", "operationtype",
               "ordertyp", "ordertype", "side", "seite", "aktion", "action", "category", "kategorie"),
    "isin": ("isin", "isincode", "wertpapierkennung", "symbol"),
    "asset": ("wertpapier", "wertpapiername", "bezeichnung", "name", "name1", "titel", "instrument", "asset", "coin", "kryptowaehrung",
              "kryptowährung", "currencyticker", "ticker", "produkt", "product", "unit"),
    "quantity": ("zuabgang", "zugangabgang", "menge", "stueck", "stück", "stuecke", "stücke", "anzahl", "nominal", "quantity", "quantitytransacted", "shares", "units",
                 "assetamount", "operationamount", "amount"),
    "price": ("kurs", "preis", "ausfuehrungskurs", "ausführungskurs", "kursjestueck", "price", "priceattransaction", "spotpriceattransaction",
              "unitprice", "executionprice", "stueckpreis", "stückpreis"),
    "amount": ("betrag", "gesamtbetrag", "kurswert", "anlagebetrag", "anlagebetraginkontowaehrung", "anlagebetraginkontowährung", "total",
               "subtotal", "wert", "value", "euramount", "eur", "nettobetrag", "netamount", "amounteur", "betrageur"),
    "fee": ("gebuehr", "gebühr", "gebuehren", "gebühren", "gebuehreninkontowaehrung", "gebühreninkontowährung", "fee", "fees", "feesandorspread",
            "entgelt", "provision", "commission", "orderkosten"),
    "currency": ("waehrung", "währung", "currency", "handelswaehrung", "handelswährung", "pricecurrency", "kontowaehrung", "kontowährung"),
    "status": ("status", "statusdertransaktion", "orderstatus", "transaktionsstatus", "state", "zustand"),
    "reference": ("id", "transaktionsid", "transactionid", "txid", "referenz", "reference", "orderid", "ordernummer", "auftragsnummer",
                  "vorgangsnummer", "refid", "operationhash", "hash"),
}
# Typische Vorgangsbezeichnungen, normalisiert.
_ACTION_WORDS: dict[str, tuple[str, ...]] = {
    "buy": ("kauf", "buy", "kaufen", "purchase", "bought", "wertpapierkauf", "sparplan", "sparplanausfuehrung", "savingsplan", "advancedtradebuy", "kauforder"),
    "sell": ("verkauf", "sell", "verkaufen", "sold", "wertpapierverkauf", "advancedtradesell", "verkaufsorder"),
    "dividend": ("dividende", "dividend", "dividends", "ausschuettung", "ausschüttung", "distribution", "ertragsgutschrift", "dividendengutschrift"),
    "deposit": ("in", "einlieferung", "deposit", "receive", "received", "eingang", "zugang", "transferin", "inbound"),
    "withdrawal": ("out", "auslieferung", "withdrawal", "withdraw", "send", "sent", "ausgang", "abgang", "transferout", "outbound"),
    "reward": ("staking", "stakingreward", "stakingincome", "reward", "rewards", "rewardincome", "earn", "bonus", "airdrop"),
    "interest": ("zinsen", "zins", "interest", "interestpayment", "zinsgutschrift"),
    "fee": ("gebuehr", "gebühr", "fee", "fees", "entgelt", "kontofuehrung"),
    "cash_in": ("einzahlung", "customerinbound", "lastschrift", "ueberweisungeingang", "topup"),
    "cash_out": ("auszahlung", "customeroutbound", "payout"),
    # Nur ausdruecklicher Handel: Tausch, Umtausch und Convert sind Coin gegen Coin oder Kapitalmassnahmen - die bleiben offen.
    "trade": ("trade", "handel"),
}
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_FIAT = frozenset({"EUR", "USD", "CHF", "GBP", "JPY", "SEK", "NOK", "DKK", "PLN", "CZK", "CAD", "AUD"})
# Zeilen, deren Status nicht ausgefuehrt meldet, werden nicht gebucht; ohne Statusspalte gilt jede Zeile als ausgefuehrt.
_STATUS_DONE = ("confirmed", "completed", "complete", "executed", "filled", "done", "success", "successful", "ausgefuehrt", "ausgeführt",
                "abgeschlossen", "bestaetigt", "bestätigt", "erledigt", "gebucht", "settled", "finalisiert")


class GenericStatementImportV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _normal(text: Any) -> str:
    return re.sub(r"[^a-z0-9äöüß]", "", str(text or "").lower())


# --- Tabelle lesen ---------------------------------------------------------------------------------------------------------

def read_table_v1(text: str) -> tuple[list[str], list[dict[str, str]]] | None:
    """Kopfzeile und Zeilen einer CSV-Datei. Vor der Kopfzeile stehen oft Titel oder Hinweise: Kopfzeile ist unter den ersten
    40 Zeilen die mit den meisten Spalten, deren Zellen ueberwiegend Woerter sind. None, wenn keine Tabelle erkennbar ist."""
    lines = text.lstrip("\ufeff").splitlines()
    best = None
    for start, line in enumerate(lines[:40]):
        delimiter = max(",;\t|", key=line.count)
        cells = [cell.strip().strip('"') for cell in next(csv.reader([line], delimiter=delimiter), [])]
        words = [cell for cell in cells if cell and re.search(r"[A-Za-zÄÖÜäöü]", cell) and not re.fullmatch(r"[-+]?[0-9.,\s]+", cell)]
        if len(cells) >= 3 and len(words) >= max(3, len(cells) * 0.6) and (best is None or len(cells) > best[2]):
            best = (start, delimiter, len(cells))
    if best is None:
        return None
    start, delimiter, _width = best
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delimiter)
    header = [(name or "").strip() for name in (reader.fieldnames or [])]
    if len(set(header)) != len(header):
        header = [f"{name} ({index})" if header.count(name) > 1 else name for index, name in enumerate(header, 1)]
        reader = csv.DictReader(io.StringIO("\n".join(lines[start + 1:])), fieldnames=header, delimiter=delimiter)
    rows = [{(key or "").strip(): (value or "").strip() for key, value in row.items() if key is not None} for row in reader]
    return header, [row for row in rows if any(row.values())]


def header_signature_v1(header: Sequence[str]) -> str:
    """Das Format einer Datei: die normalisierten Spaltennamen, sortiert, als Pruefwert. Gleiches Format, gleiches Profil."""
    return hashlib.sha256(json.dumps(sorted(_normal(name) for name in header), ensure_ascii=False).encode("utf-8")).hexdigest()[:32]


# --- Vorschlag ---------------------------------------------------------------------------------------------------------------

def _score(field: str, column: str) -> int:
    normal = _normal(column)
    words = _HEADER_WORDS[field]
    if normal in words:
        return 100 - words.index(normal)
    best = 0
    for position, word in enumerate(words):
        if len(word) >= 4 and (normal.startswith(word) or word in normal):
            best = max(best, 60 - position)
    return best


def _values(rows: Sequence[Mapping[str, str]], column: str, limit: int = 200) -> list[str]:
    return [row.get(column, "") for row in rows[:limit] if row.get(column, "")]


def _looks_like(kind: str, values: Sequence[str]) -> float:
    if not values:
        return 0.0
    if kind == "date":
        return sum(1 for value in values if _parse_moment(value, TIME_ZONE) is not None) / len(values)
    if kind == "number":
        return sum(1 for value in values if crypto._number(value) is not None) / len(values)
    if kind == "isin":
        return sum(1 for value in values if _ISIN.fullmatch(value.strip().upper())) / len(values)
    return 0.0


def propose_mapping_v1(header: Sequence[str], rows: Sequence[Mapping[str, str]]) -> dict[str, str | None]:
    """Je Feld die Spalte mit dem besten Treffer; jede Spalte hoechstens einmal. Inhalte bestaetigen Datum, Zahlen und ISIN."""
    candidates = []
    for field in FIELDS:
        for column in header:
            score = _score(field, column)
            if score <= 0:
                continue
            sample = _values(rows, column)
            if field in ("date",) and _looks_like("date", sample) < 0.8:
                continue
            if field in ("quantity", "price", "amount", "fee") and sample and _looks_like("number", sample) < 0.8:
                continue
            if field in ("asset", "action", "currency", "status") and sample and _looks_like("number", sample) > 0.5:
                continue
            # Eine Spalte nur mit Waehrungscodes (EUR, USD …) nennt die Einheit eines Betrags, nicht das Wertpapier oder den Coin.
            if field == "asset" and sample and sum(value.strip().upper() in _FIAT for value in sample) >= len(sample) * 0.8:
                continue
            if field == "isin":
                fit = _looks_like("isin", sample)
                if fit < 0.5:
                    continue
                score += int(fit * 20)
            candidates.append((score, field, column))
    mapping: dict[str, str | None] = {field: None for field in FIELDS}
    used: set[str] = set()
    for score, field, column in sorted(candidates, key=lambda item: (-item[0], FIELDS.index(item[1]))):
        if mapping[field] is None and column not in used:
            mapping[field] = column; used.add(column)
    # Ein Ledger-Export nennt die Menge "amount" und hat keinen Kurswert: dann ist "amount" die Menge.
    if mapping["quantity"] is None and mapping["amount"] is not None and _normal(mapping["amount"]) == "amount":
        mapping["quantity"], mapping["amount"] = mapping["amount"], None
    # Eine Spalte, die Datum und Uhrzeit traegt, braucht keine eigene Uhrzeit.
    if mapping["time"] is not None and mapping["date"] is not None:
        sample = _values(rows, mapping["date"])
        if sample and all(re.search(r"\d{1,2}:\d{2}", value) for value in sample[:20]):
            mapping["time"] = None
    return mapping


def propose_actions_v1(rows: Sequence[Mapping[str, str]], column: str | None, limit: int = 40) -> dict[str, str | None]:
    """Je Vorgangsbezeichnung der Datei die vorgeschlagene Buchungsart, oder None, wenn kein typischer Ausdruck passt."""
    if column is None:
        return {}
    seen: list[str] = []
    for row in rows:
        value = row.get(column, "").strip()
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= limit:
            break
    proposal: dict[str, str | None] = {}
    for value in seen:
        normal = _normal(value)
        exact = [kind for kind, words in _ACTION_WORDS.items() if normal in words]
        if exact:
            proposal[value] = exact[0]; continue
        partial = [kind for kind, words in _ACTION_WORDS.items() if any(len(word) >= 4 and word in normal for word in words)]
        proposal[value] = partial[0] if len(set(partial)) == 1 else None
    return proposal


def _executed(row: Mapping[str, str], mapping: Mapping[str, str | None]) -> bool:
    column = mapping.get("status")
    value = _normal(row.get(column, "")) if column else ""
    return not value or value in _STATUS_DONE


def propose_profile_v1(text: str, file_name: str = "", time_zone: str = TIME_ZONE) -> dict[str, Any] | None:
    """Der Vorschlag fuer eine Datei: Format, Spalten, Zuordnung, Vorgaenge und erste Zeilen zur Ansicht."""
    table = read_table_v1(text)
    if table is None:
        return None
    header, rows = table
    mapping = propose_mapping_v1(header, rows)
    return {"signature": header_signature_v1(header), "file_name": Path(file_name).name, "columns": list(header), "row_count": len(rows),
            "mapping": mapping, "actions": propose_actions_v1(rows, mapping["action"]), "time_zone": time_zone,
            "sample": [{column: row.get(column, "") for column in header} for row in rows[:5]]}


# --- Profile ---------------------------------------------------------------------------------------------------------------

def _profile_path(space: Path) -> Path:
    return Path(space) / PROFILE_AREA / PROFILE_FILE


def read_generic_profiles_v1(space) -> dict[str, dict[str, Any]]:
    """Gespeicherte Profile je Format (Pruefwert der Kopfzeile); leer ohne Datei."""
    path = _profile_path(space)
    if not path.exists():
        return {}
    if path.is_symlink() or path.parent.is_symlink():
        raise GenericStatementImportV1Error("generic_profile_invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GenericStatementImportV1Error("generic_profile_invalid") from error
    if not isinstance(value, dict) or value.get("version") != PROFILE_VERSION or not isinstance(value.get("profiles"), dict):
        raise GenericStatementImportV1Error("generic_profile_invalid")
    return value["profiles"]


def _valid_profile(profile: Any) -> bool:
    if not isinstance(profile, dict) or set(profile) != {"label", "mapping", "actions", "time_zone", "saved_at_utc"}:
        return False
    mapping, actions = profile["mapping"], profile["actions"]
    if not isinstance(mapping, dict) or set(mapping) != set(FIELDS) or not all(value is None or (isinstance(value, str) and value) for value in mapping.values()):
        return False
    if not isinstance(actions, dict) or len(actions) > 200 or not all(isinstance(key, str) and (value is None or value in KINDS) for key, value in actions.items()):
        return False
    try:
        ZoneInfo(profile["time_zone"])
    except Exception:  # noqa: BLE001 - jede ungueltige Zone
        return False
    return isinstance(profile["label"], str) and 1 <= len(profile["label"]) <= 120 and isinstance(profile["saved_at_utc"], str)


def save_generic_profile_v1(space, signature: str, profile: Mapping[str, Any], confirmed: bool) -> dict[str, Any]:
    """Ein Profil je Format speichern (nur lokal, im Datenraum, nur fuer den Eigentuemer lesbar). Ersetzt ein gleiches Format."""
    if confirmed is not True:
        raise GenericStatementImportV1Error("generic_confirmation_required")
    if not isinstance(signature, str) or re.fullmatch(r"[a-f0-9]{32}", signature) is None or not _valid_profile(dict(profile)):
        raise GenericStatementImportV1Error("generic_profile_invalid")
    profiles = read_generic_profiles_v1(space)
    profiles[signature] = dict(profile)
    if len(profiles) > MAX_PROFILES:
        raise GenericStatementImportV1Error("generic_profile_invalid")
    path = _profile_path(space)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    old = os.umask(0o077)
    try:
        temporary.write_text(json.dumps({"version": PROFILE_VERSION, "profiles": profiles}, ensure_ascii=False, sort_keys=True, indent=1), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        os.umask(old)
    return {"contract_version": CONTRACT, "status": "saved", "signature": signature, "profile_count": len(profiles),
            "provider_access": False, "network_access": False, "canonical_write": False}


# --- Zeilen lesen ------------------------------------------------------------------------------------------------------------

_MOMENT_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M",
                   "%d.%m.%Y, %H:%M:%S", "%d.%m.%Y, %H:%M", "%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d")


def _parse_moment(value: str, zone: str) -> datetime | None:
    """Zeitpunkt in UTC: ISO mit Zone, sonst in der Zone des Profils; "UTC" oder "Z" am Ende gilt als UTC."""
    text = (value or "").strip()
    if not text:
        return None
    utc = bool(re.search(r"(?:\bUTC|Z)$", text))
    text = re.sub(r"\s*(?:UTC|Z)$", "", text)
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is not None:
            return parsed.astimezone(ZoneInfo("UTC"))
    except ValueError:
        parsed = None
    if parsed is None:
        # Bruchteile der Sekunde ("12:30:45.123") weg - nur nach den Sekunden, sonst fiele das Jahr aus "02.05.2027".
        text = re.sub(r"(?<=:\d\d)\.\d+$", "", text)
        for pattern in _MOMENT_FORMATS:
            try:
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    return parsed.replace(tzinfo=ZoneInfo("UTC" if utc else zone)).astimezone(ZoneInfo("UTC"))


def _number(value: str) -> Decimal | None:
    return crypto._number(value)


def _kind_of(row: Mapping[str, str], mapping: Mapping[str, str | None], actions: Mapping[str, str | None], quantity: Decimal | None) -> str | None:
    if mapping["action"] is None:
        return "trade" if quantity is not None else None
    value = row.get(mapping["action"], "").strip()
    kind = actions.get(value)
    if kind == "trade":
        if quantity is None or quantity == 0:
            return None
        return "buy" if quantity > 0 else "sell"
    return kind


def _profile_for(text: str, options: Mapping[str, Any] | None, zone: str = TIME_ZONE) -> tuple[list[str], list[dict[str, str]], dict[str, Any]] | None:
    table = read_table_v1(text)
    if table is None:
        return None
    header, rows = table
    profiles = (options or {}).get("profiles") or {}
    saved = profiles.get(header_signature_v1(header))
    if saved is not None and _valid_profile(saved) and all(column is None or column in header for column in saved["mapping"].values()):
        return header, rows, {**saved, "source": "profile"}
    mapping = propose_mapping_v1(header, rows)
    return header, rows, {"label": "Vorschlag", "mapping": mapping, "actions": propose_actions_v1(rows, mapping["action"]), "time_zone": zone,
                          "saved_at_utc": "", "source": "proposal"}


def parse_generic_securities_v1(text: str, file_name: str = "", options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Wertpapiere: je Zeile mit ISIN ein Kauf, Verkauf oder eine Dividende; alles andere zaehlt mit Grund."""
    from migrations.reference.securities_statement_import_v1 import _candidate, _plain, _reason
    found = _profile_for(text, options)
    if found is None:
        return _reason("generic_no_table")
    _header, rows, profile = found
    mapping, actions, zone = profile["mapping"], profile["actions"], profile["time_zone"]
    if mapping["date"] is None or (mapping["quantity"] is None and mapping["amount"] is None):
        return _reason("generic_unmapped")
    candidates: list[dict[str, Any]] = []
    reasons: dict[str, int] = {}

    def skip(code: str) -> None:
        reasons[code] = reasons.get(code, 0) + 1

    cell = lambda row, field: row.get(mapping[field], "").strip() if mapping[field] else ""
    for number, row in enumerate(rows, 1):
        if not _executed(row, mapping):
            skip("generic_not_executed"); continue
        quantity = _number(cell(row, "quantity")) if mapping["quantity"] else None
        kind = _kind_of(row, mapping, actions, quantity)
        if kind is None:
            skip("generic_unknown_action"); continue
        if kind == "ignore":
            skip("generic_ignored"); continue
        if kind in ("interest", "fee", "cash_in", "cash_out"):
            skip("generic_cash_movement"); continue
        if kind in ("deposit", "withdrawal"):
            skip("generic_delivery"); continue
        if kind == "reward":
            skip("generic_reward"); continue
        currency = cell(row, "currency").upper() or "EUR"
        if currency != "EUR":
            skip("generic_not_eur"); continue
        isin = cell(row, "isin").upper()
        if not _ISIN.fullmatch(isin):
            skip("generic_no_isin"); continue
        moment = _parse_moment(cell(row, "date") + (" " + cell(row, "time") if mapping["time"] and cell(row, "time") else ""), zone)
        if moment is None:
            skip("generic_date_unreadable"); continue
        local = moment.astimezone(ZoneInfo(TIME_ZONE))
        price, amount, fee = _number(cell(row, "price")), _number(cell(row, "amount")), _number(cell(row, "fee")) or Decimal(0)
        name = cell(row, "asset") or None
        reference = cell(row, "reference") or None
        if kind == "dividend":
            if amount is None or amount == 0:
                skip("generic_incomplete"); continue
            candidates.append(_candidate("dividend", "generic", isin=isin, security_name=name, local_date=local.strftime("%Y-%m-%d"),
                                         eligible_quantity=_plain(abs(quantity)) if quantity else None, gross_amount=_plain(abs(amount)), currency="EUR",
                                         order_ref=reference))
            continue
        quantity = abs(quantity) if quantity is not None else None
        if not quantity:
            skip("generic_incomplete"); continue
        gross = abs(amount) if amount is not None else (abs(price) * quantity if price is not None else None)
        unit = abs(price) if price is not None else (gross / quantity if gross is not None else None)
        if gross is None or unit is None:
            skip("generic_incomplete"); continue
        candidates.append(_candidate(kind, "generic", isin=isin, security_name=name, local_date=local.strftime("%Y-%m-%d"), local_time=local.strftime("%H:%M:%S"),
                                     quantity=_plain(quantity), unit_price=_plain(unit), gross_amount=_plain(gross), fee_amount=_plain(abs(fee)),
                                     currency="EUR", order_ref=reference))
    return {"status": "multi", "candidates": candidates, "row_reasons": reasons}


def parse_generic_crypto_v1(text: str, file_name: str = "", options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Krypto: je Zeile mit Coin-Kuerzel ein Handel gegen EUR oder eine Bewegung; die Paarung der Transfers macht der Krypto-Leser."""
    # Krypto-Exporte nennen Zeiten meist in UTC; ohne Profil gilt deshalb UTC.
    found = _profile_for(text, options, "UTC")
    if found is None:
        return {"status": "not_importable", "reason_code": "generic_no_table", "reason": REASONS["generic_no_table"]}
    _header, rows, profile = found
    mapping, actions, zone = dict(profile["mapping"]), profile["actions"], profile["time_zone"]
    # Manche Exporte fuehren den Coin in der Waehrungsspalte (Kontoauszug je Coin): dann ist sie der Coin, die Betraege in EUR.
    if mapping["asset"] is None and mapping["currency"] is not None:
        sample = _values(rows, mapping["currency"])
        if sample and all(re.fullmatch(r"[A-Za-z0-9]{2,10}", value) and value.upper() != "EUR" for value in sample[:50]):
            mapping["asset"], mapping["currency"] = mapping["currency"], None
    if mapping["date"] is None or mapping["quantity"] is None or mapping["asset"] is None:
        return {"status": "not_importable", "reason_code": "generic_unmapped", "reason": REASONS["generic_unmapped"]}
    sheet = crypto._Sheet("generic", Path(file_name).name)
    cell = lambda row, field: row.get(mapping[field], "").strip() if mapping[field] else ""
    for number, row in enumerate(rows, 1):
        if not _executed(row, mapping):
            sheet.skip("generic_not_executed"); continue
        quantity = _number(cell(row, "quantity"))
        # Kleinste Einheiten (sat, gwei, wei) wie im Krypto-Leser auf ganze Coins umrechnen.
        scale, ticker = crypto._UNITS.get(cell(row, "asset").lower(), (Decimal(1), crypto._ticker(cell(row, "asset"))))
        if quantity is not None:
            quantity = quantity * scale
        kind = _kind_of(row, mapping, actions, quantity)
        at = _parse_moment(cell(row, "date") + (" " + cell(row, "time") if mapping["time"] and cell(row, "time") else ""), zone)
        if kind is None:
            sheet.skip("generic_unknown_action"); continue
        if kind == "ignore":
            sheet.skip("generic_ignored"); continue
        if kind == "reward":
            sheet.skip("generic_reward"); continue
        # Ein- und Auszahlung eines Coins ist eine Bewegung des Coins, keine Geldbewegung.
        if kind in ("cash_in", "cash_out") and ticker and ticker not in _FIAT:
            kind = "deposit" if kind == "cash_in" else "withdrawal"
        if kind in ("interest", "fee", "cash_in", "cash_out", "dividend") or ticker == "EUR":
            sheet.skip("generic_cash_movement"); continue
        if at is None:
            sheet.skip("generic_date_unreadable"); continue
        reference = cell(row, "reference")
        if kind in ("buy", "sell"):
            currency = cell(row, "currency").upper() or "EUR"
            if currency != "EUR":
                sheet.skip("generic_not_eur"); continue
            price, amount, fee = _number(cell(row, "price")), _number(cell(row, "amount")), _number(cell(row, "fee"))
            if quantity is None or quantity == 0:
                sheet.skip("generic_incomplete"); continue
            eur = abs(amount) if amount is not None else (abs(price) * abs(quantity) if price is not None else None)
            if eur is None:
                sheet.skip("generic_incomplete"); continue
            signed = abs(quantity) if kind == "buy" else -abs(quantity)
            sheet.add(number, "main", at, ticker, "trade", signed, eur=eur, eur_fee=abs(fee) if fee is not None else Decimal(0), transaction_id=reference)
        elif kind in ("deposit", "withdrawal"):
            if quantity is None or quantity == 0:
                sheet.skip("generic_incomplete"); continue
            fee = _number(cell(row, "fee"))
            signed = abs(quantity) if kind == "deposit" else -abs(quantity)
            sheet.add(number, "main", at, ticker, "move", signed, fee_quantity=abs(fee) if fee and kind == "withdrawal" else None, transaction_id=reference)
        else:
            sheet.skip("generic_unknown_action")
    return sheet.result()


def never_detect_v1(text: str) -> bool:
    """Der generische Leser wird nie von selbst gewaehlt: "Automatisch erkennen" nimmt nur feste Leser."""
    return False


__all__ = ["CONTRACT", "FIELDS", "FIELD_LABELS", "KINDS", "KIND_LABELS", "REASONS", "GenericStatementImportV1Error", "header_signature_v1",
           "never_detect_v1", "parse_generic_crypto_v1", "parse_generic_securities_v1", "propose_actions_v1", "propose_mapping_v1",
           "propose_profile_v1", "read_generic_profiles_v1", "read_table_v1", "save_generic_profile_v1"]
