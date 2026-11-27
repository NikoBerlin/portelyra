"""Belegangaben aus Boersen- und Wallet-Auszuegen: Transaktions-ID und Adresse zu gebuchten Krypto-Vorgaengen.

Die Auszuege werden nur gelesen (CSV). Ein Auszug wird an seinem Tabellenkopf erkannt,
nicht an Dateiname oder Ordner. Zugeordnet wird streng: dasselbe Kuerzel, eine
zur Buchung passende Vorgangsart, dieselbe Menge (auch zu- oder abzueglich einer
in Stueck gezahlten Gebuehr) und ein Zeitpunkt in der Naehe. Bleibt danach mehr
als eine Kennung uebrig, bleibt die Buchung offen. Nichts wird abgeleitet oder
erfunden: Fuehrt eine Boerse keine Transaktions-ID, bleibt das Feld leer.
Eine vorhandene Angabe wird nie
ueberschrieben; weicht sie vom Auszug ab, wird das gezaehlt.
"""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import io
from pathlib import Path
import re
import sqlite3
from typing import Any
from zoneinfo import ZoneInfo

from migrations.reference.asset_activity_reference_v1 import (
    AssetActivityReferenceV1Error, FIELDS, TOKEN, activity_reference_scope_v1, read_activity_references_v1,
    record_activity_references_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityV1Error, read_desktop_product_asset_activity_binding_v1,
)

CONTRACT = "statement_activity_reference_backfill_v1"
MAX_FILES = 2000
MAX_FILE_BYTES = 20 * 1024 * 1024
WINDOW = timedelta(hours=36)
NARROW = timedelta(minutes=15)
LOCAL_ZONE = ZoneInfo("Europe/Berlin")
# Welche Vorgangsart eines Auszugs zu welcher Buchungsart passt. Ein Kauf an der Boerse und die Auszahlung
# derselben Menge gleich danach sind zwei Vorgaenge mit zwei Kennungen - die Art haelt sie auseinander.
COMPATIBLE = {
    "buy": {"trade_in"}, "sell": {"trade_out"}, "reward": {"reward"},
    "transfer": {"transfer"}, "withdrawal": {"transfer"}, "deposit": {"transfer"},
}
_HASH = (re.compile(r"(0x)?[0-9a-fA-F]{64}"), re.compile(r"[1-9A-HJ-NP-Za-km-z]{80,100}"))
_KRAKEN_CODES = {"XXBT": "BTC", "XBT": "BTC", "XETH": "ETH", "XXRP": "XRP", "XLTC": "LTC", "XXDG": "DOGE", "XDG": "DOGE",
                 "XXLM": "XLM", "XZEC": "ZEC", "XXMR": "XMR", "ETH2": "ETH"}


def _decimal(text: Any) -> Decimal | None:
    value = "" if text is None else str(text).replace(" ", " ").strip()
    match = re.match(r"^[€$\s]*(-?[0-9][0-9.,]*)", value)
    if match is None:
        return None
    number = match.group(1)
    if "," in number and "." in number:
        number = number.replace(".", "").replace(",", ".") if number.rfind(",") > number.rfind(".") else number.replace(",", "")
    elif "," in number:
        number = number.replace(",", ".")
    try:
        return abs(Decimal(number))
    except InvalidOperation:
        return None


def _utc(text: str, pattern: str, zone=timezone.utc) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), pattern).replace(tzinfo=zone).astimezone(timezone.utc)
    except ValueError:
        return None


def _iso(text: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else None


def _ticker(code: str) -> str:
    value = re.sub(r"[^A-Z0-9.]", "", (code or "").upper())
    value = re.sub(r"\.[A-Z0-9]+$", "", value)
    return _KRAKEN_CODES.get(value, value)


def _quantities(amount: Decimal | None, fee: Decimal | None = None) -> set[Decimal]:
    if amount is None or amount == 0:
        return set()
    values = {amount}
    if fee:
        values |= {amount + fee, amount - fee}
    return {value.normalize() for value in values if value > 0}


def _row(source, at, code, kind, quantities, identifier="", address="", price=None):
    if at is None or not quantities or not code:
        return None
    return {"source": source, "at_utc": at, "ticker": _ticker(code), "kind": kind, "quantities": quantities,
            "transaction_id": (identifier or "").strip(), "address": (address or "").strip(), "price": price}


def _kraken(row):
    kind = {"deposit": "transfer", "withdrawal": "transfer", "receive": "trade_in", "spend": "trade_out"}.get(row["type"])
    if row["type"] == "earn":
        # Rewards sind Ertraege; Zuteilungen zwischen Spot- und Earn-Wallet sind Umschichtungen.
        kind = "reward" if row.get("subtype") == "reward" else "transfer"
    if kind is None:
        return None
    # Eine Zuteilung zwischen Spot- und Earn-Wallet fuehrt Kraken als zwei Zeilen mit je eigener txid; beide teilen die refid.
    identifier = row["refid"] if row["type"] == "earn" and kind == "transfer" else row["txid"]
    return _row("kraken", _utc(row["time"], "%Y-%m-%d %H:%M:%S"), row["asset"], kind,
                _quantities(_decimal(row["amount"]), _decimal(row.get("fee"))), identifier)


def _coinbase(row):
    kind = {"Buy": "trade_in", "Sell": "trade_out", "Staking Income": "reward", "Incentives Rewards Payout": "reward",
            "Retail Simple Price Improvement": "reward", "Receive": "transfer", "Send": "transfer",
            "Retail Staking Transfer": "transfer", "Deposit": "transfer", "Withdrawal": "transfer"}.get(row["Transaction Type"])
    if kind is None:
        return None
    return _row("coinbase", _utc(row["Timestamp"], "%Y-%m-%d %H:%M:%S UTC"), row["Asset"], kind,
                _quantities(_decimal(row["Quantity Transacted"])), row["ID"],
                (row.get("Recipient Address") or row.get("Sender Address") or "") if kind == "transfer" else "",
                _decimal(row.get("Price at Transaction")))


def _bison(row):
    kind = {"Buy": "trade_in", "Sell": "trade_out", "Staking Reward": "reward", "Deposit": "transfer", "Withdraw": "transfer"}.get(row["Transaction type"])
    if kind is None:
        return None
    return _row("bison", _utc(row["Date (UTC - Coordinated Universal Time)"], "%Y-%m-%d %H:%M:%S"), row["Asset"], kind,
                _quantities(_decimal(row["Asset (amount)"])), row["Transaction ID"], "", _decimal(row.get("Asset (market price)")))


def _bsdex(row):
    # BSDEX fuehrt keine Transaktions-ID. Verwertbar sind die Adressen der Ein- und Auszahlungen.
    address = row.get("Zieladresse") or row.get("Sendeadresse") or ""
    if not address:
        return None
    # Das Kuerzel steht als Einheit im Betrag ("0,5 BTC"); die Spalte "Kryptowährung" kann den Namen tragen.
    unit = re.search(r"([A-Za-z]{2,10})\s*$", row["Betrag"].replace(" ", " "))
    code = unit.group(1) if unit else row.get("Kryptowährung", "")
    return _row("bsdex", _utc(row.get("Finalisiert am") or row["Erstellt"], "%d.%m.%Y, %H:%M", LOCAL_ZONE), code, "transfer",
                _quantities(_decimal(row["Betrag"]), _decimal(row.get("Transaktionsentgelt")) if "€" not in (row.get("Transaktionsentgelt") or "") else None),
                "", address)


def _bitbox(row):
    scale = {"satoshi": (Decimal("0.00000001"), "BTC"), "sat": (Decimal("0.00000001"), "BTC"), "wei": (Decimal("1e-18"), "ETH"),
             "gwei": (Decimal("1e-9"), "ETH")}.get(row["Unit"].lower(), (Decimal(1), row["Unit"]))
    amount, fee = _decimal(row["Amount"]), _decimal(row.get("Fee"))
    fee_scale = {"satoshi": Decimal("0.00000001"), "sat": Decimal("0.00000001"), "wei": Decimal("1e-18"), "gwei": Decimal("1e-9")}.get(
        (row.get("Fee Unit") or "").lower(), Decimal(1))
    if row["Type"] not in ("sent", "received", "sent_to_yourself"):
        return None
    return _row("bitbox", _iso(row["Time"]), scale[1], "transfer",
                _quantities(None if amount is None else amount * scale[0], None if fee is None else fee * fee_scale),
                row["Transaction ID"], row.get("Address") or "")


def _bitcoin_de(row):
    kind = {"Kauf": "trade_in", "Verkauf": "trade_out", "Auszahlung": "transfer", "Einzahlung": "transfer"}.get(row["Typ"])
    if kind is None:
        return None
    amounts = {value for key, value in ((key, _decimal(value)) for key, value in row.items())
               if value and (key == "Zu- / Abgang" or re.fullmatch(r"[A-Z]{2,10} (vor Gebühr|nach Bitcoin\.de-Gebühr)", key or ""))}
    address = next((value for key, value in row.items() if (key or "").endswith("-Adresse") and value), "")
    return _row("bitcoin_de", _utc(row["Datum"], "%Y-%m-%d %H:%M:%S", LOCAL_ZONE), row["Währung"], kind,
                {value.normalize() for value in amounts}, row["Referenz"], address if kind == "transfer" else "", _decimal(row.get("Kurs")))


def _ledger_live(row):
    if row["Operation Type"] not in ("IN", "OUT"):
        return None
    # "Account xpub" ist der Schluessel des eigenen Kontos, nicht die Adresse der Gegenseite - er wird nicht uebernommen.
    return _row("ledger_live", _iso(row["Operation Date"]), row["Currency Ticker"], "transfer",
                _quantities(_decimal(row["Operation Amount"]), _decimal(row.get("Operation Fees"))), row["Operation Hash"])


FORMATS = (
    ({"txid", "refid", "time", "type", "asset", "amount"}, _kraken),
    ({"ID", "Timestamp", "Transaction Type", "Asset", "Quantity Transacted"}, _coinbase),
    ({"Transaction ID", "Transaction type", "Asset", "Asset (amount)", "Date (UTC - Coordinated Universal Time)"}, _bison),
    ({"Transaktionstyp", "Kryptowährung", "Betrag", "Erstellt", "Zieladresse", "Sendeadresse"}, _bsdex),
    ({"Time", "Type", "Amount", "Unit", "Address", "Transaction ID"}, _bitbox),
    ({"Datum", "Typ", "Währung", "Referenz", "Zu- / Abgang"}, _bitcoin_de),
    ({"Operation Date", "Currency Ticker", "Operation Type", "Operation Amount", "Operation Hash"}, _ledger_live),
)


def _decode(raw: bytes) -> str | None:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def _statement_entries(statement_root) -> list[tuple[Path, str]]:
    """Ein Ordner oder eine Liste aus (Pfad, Dateiname) - etwa die hinterlegten Dateien der Ablage (#434), die unter ihrem
    Pruefwert liegen. Der Dateiname zaehlt fuer die Endung."""
    if isinstance(statement_root, (list, tuple)):
        if len(statement_root) > MAX_FILES * 50 or not all(
                isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(value, str) and value for value in item) for item in statement_root):
            raise AssetActivityReferenceV1Error("activity_reference_input_invalid")
        return [(Path(path), re.split(r"[\\/]", name)[-1]) for path, name in statement_root]
    root = Path(statement_root)
    if not root.is_dir() or root.is_symlink():
        raise AssetActivityReferenceV1Error("activity_reference_input_invalid")
    entries = []
    for count, path in enumerate(sorted(root.rglob("*")), 1):
        if count > MAX_FILES * 50:
            raise AssetActivityReferenceV1Error("activity_reference_input_invalid")
        entries.append((path, path.name))
    return entries


def read_statement_rows_v1(statement_root) -> dict[str, Any]:
    """Liest alle erkennbaren Auszuege unter dem Ordner (oder aus der Liste). Gleiche Zeilen aus mehreren Exportstaenden zaehlen einmal."""
    rows: dict[tuple, dict] = {}
    files = Counter()
    for path, name in _statement_entries(statement_root):
        if path.is_symlink() or not path.is_file() or Path(name).suffix.lower() != ".csv":
            continue
        if sum(files.values()) >= MAX_FILES or path.stat().st_size > MAX_FILE_BYTES:
            files["skipped"] += 1
            continue
        text = _decode(path.read_bytes())
        lines = [] if text is None else text.splitlines()
        parsed = None
        for start, line in enumerate(lines[:20]):
            delimiter = max(",;\t", key=line.count)
            header = {cell.strip().strip('"') for cell in line.split(delimiter)}
            for signature, reader in FORMATS:
                if signature <= header:
                    parsed = (start, delimiter, reader)
                    break
            if parsed:
                break
        if parsed is None:
            files["unrecognized"] += 1
            continue
        start, delimiter, reader = parsed
        try:
            records = list(csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter=delimiter))
        except csv.Error:
            files["unrecognized"] += 1
            continue
        files[reader.__name__.lstrip("_")] += 1
        for record in records:
            clean = {(key or "").strip(): (value or "").strip() for key, value in record.items() if key is not None}
            try:
                row = reader(clean)
            except (KeyError, TypeError, ValueError):
                row = None
            if row is None:
                continue
            key = (row["source"], row["transaction_id"] or None, row["at_utc"], row["ticker"], row["kind"], tuple(sorted(row["quantities"])), row["address"])
            rows[key] = row
    return {"rows": list(rows.values()), "file_counts": dict(sorted(files.items()))}


def _is_hash(text: str) -> bool:
    return any(pattern.fullmatch(text) for pattern in _HASH)


_HEX = re.compile(r"(0x)?[0-9a-fA-F]{16,}")


def _normal(value: str) -> str:
    """Hex-Kennungen ohne Praefix und in Kleinbuchstaben; alles andere bleibt, wie es ist (Base58 unterscheidet Gross und Klein)."""
    if _HEX.fullmatch(value):
        return (value[2:] if value[:2].lower() == "0x" else value).lower()
    return value


def _same(left: str, right: str) -> bool:
    return _normal(left) == _normal(right)


def plan_statement_activity_reference_backfill_v1(space, context_value, statement_root) -> dict[str, Any]:
    """Lesend: je Krypto-Buchung, was die Auszuege an Transaktions-ID und Adresse hergeben - und was offen bleibt."""
    context = activity_reference_scope_v1(context_value)
    space = Path(space)
    statements = read_statement_rows_v1(statement_root)
    try:
        binding = read_desktop_product_asset_activity_binding_v1(space, context)
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        try:
            events = connection.execute(
                "SELECT e.event_ref,e.event_type,e.local_date,e.effective_at_utc,e.quantity_decimal,e.asset_fee_quantity_decimal,"
                "e.unit_price_decimal,a.display_name FROM current_asset_activity_event e JOIN current_asset_revision a USING(asset_id) "
                "WHERE a.asset_type='crypto' ORDER BY e.event_ref").fetchall()
        finally:
            connection.close()
    except (DesktopProductAssetActivityV1Error, sqlite3.Error, KeyError, TypeError):
        raise AssetActivityReferenceV1Error("activity_reference_store_invalid") from None
    current = read_activity_references_v1(space, context)["references"]
    # Eine Kennung, die schon an einer Buchung steht, gehoert dieser Buchung - sie wird keiner anderen zugeordnet.
    taken = {_normal(entry["transaction_id"]): event_ref for event_ref, entry in current.items() if entry.get("transaction_id")}
    by_ticker: dict[str, list[dict]] = {}
    for row in statements["rows"]:
        by_ticker.setdefault(row["ticker"], []).append(row)
    choices: dict[str, dict[str, Any]] = {}
    undecided: dict[tuple, list[tuple]] = {}
    counts: Counter = Counter()

    def distinct(rows, field, moment):
        values: list[str] = []
        for row in sorted(rows, key=lambda item: (abs(item["at_utc"] - moment), item["source"], item[field])):
            if row[field] and not any(_same(row[field], known) for known in values):
                values.append(row[field])
        return values

    for event_ref, event_type, local_date, effective, quantity, fee, unit_price, display_name in events:
        match = re.match(r"\s*([A-Za-z0-9]{2,10})\b", display_name or "")
        before = current.get(event_ref, {})
        is_move = event_type in ("transfer", "withdrawal", "deposit")
        if match is None or not quantity or event_type not in COMPATIBLE:
            counts[(event_type, "transaction_id", "no_statement_row")] += 1
            continue
        if effective:
            moment = datetime.strptime(effective, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        else:
            moment = datetime.strptime(local_date, "%Y-%m-%d").replace(tzinfo=LOCAL_ZONE).astimezone(timezone.utc) + timedelta(hours=12)
        wanted = _quantities(abs(Decimal(quantity)), abs(Decimal(fee)) if fee else None)
        candidates = [row for row in by_ticker.get(_ticker(match.group(1)), [])
                      if row["kind"] in COMPATIBLE[event_type] and row["quantities"] & wanted and abs(row["at_utc"] - moment) <= WINDOW]
        choice: dict[str, Any] = {}

        # Transaktions-ID
        id_rows = [row for row in candidates if row["transaction_id"]]
        known = distinct(id_rows, "transaction_id", moment)
        existing = before.get("transaction_id")
        if existing:
            if any(_same(existing, value) for value in known):
                outcome = "confirmed"
            elif not known:
                outcome = "kept_without_statement"
            elif is_move and _is_hash(existing) and not any(_is_hash(value) for value in known):
                # Die Buchung traegt den Hash der Kette, der Auszug der Boerse nur deren eigene Nummer: kein Widerspruch.
                outcome = "kept_statement_has_exchange_id"
            else:
                outcome = "differs_from_statement"
        else:
            rows = [row for row in id_rows if taken.get(_normal(row["transaction_id"]), event_ref) == event_ref]
            if is_move and any(_is_hash(row["transaction_id"]) for row in rows):
                # Eine Umschichtung steht im Auszug der Boerse mit deren Nummer und im Wallet mit dem Hash der Kette: der Hash gilt.
                rows = [row for row in rows if _is_hash(row["transaction_id"])]
            values = distinct(rows, "transaction_id", moment)
            if len(values) > 1:
                close = [row for row in rows if abs(row["at_utc"] - moment) <= NARROW]
                rows = close or rows
                values = distinct(rows, "transaction_id", moment)
            if len(values) > 1 and unit_price and not is_move:
                # Mehrere Abschluesse gleicher Menge: der Preis der Buchung entscheidet.
                price = abs(Decimal(unit_price))
                priced = [row for row in rows if row["price"] is not None and abs(row["price"] - price) <= max(Decimal("0.005"), price / 1000000)]
                if priced:
                    rows = priced
                    values = distinct(rows, "transaction_id", moment)
            if not values:
                outcome = "no_statement_row" if not candidates else "statement_without_value" if not id_rows else "belongs_to_other_booking"
            elif len(values) > 1:
                outcome = "ambiguous"
                first_seen = {value: min(row["at_utc"] for row in rows if _same(row["transaction_id"], value)) for value in values}
                ordered = tuple(sorted(values, key=lambda value: (first_seen[value], _normal(value))))
                signature = (_ticker(match.group(1)), event_type, tuple(sorted(wanted)), tuple(sorted(_normal(value) for value in values)))
                undecided.setdefault(signature, []).append((effective or local_date, event_ref, ordered))
            elif TOKEN.fullmatch(values[0]) is None:
                outcome = "statement_value_invalid"
            else:
                outcome = "new"
                choice["transaction_id"] = values[0]
        counts[(event_type, "transaction_id", outcome)] += 1

        # Adresse - nur bei Umschichtung, Abgang und Zugang
        if is_move:
            addresses = distinct([row for row in candidates if row["address"]], "address", moment)
            if before.get("counterparty_address"):
                outcome = "confirmed" if any(before["counterparty_address"] == value for value in addresses) else "differs_from_statement" if addresses else "kept_without_statement"
            elif not addresses:
                outcome = "no_statement_row" if not candidates else "statement_without_value"
            elif len(addresses) > 1:
                outcome = "ambiguous"
            elif TOKEN.fullmatch(addresses[0]) is None:
                outcome = "statement_value_invalid"
            else:
                outcome = "new"
                choice["counterparty_address"] = addresses[0]
            counts[(event_type, "counterparty_address", outcome)] += 1
        if choice:
            choices[event_ref] = choice

    # Gleich viele Buchungen wie Kennungen, alle mit demselben Kuerzel, derselben Art und Menge und - nach Zeit und
    # Preis - denselben in Frage kommenden Kennungen: Jede Buchung erhaelt eine, beide Seiten in zeitlicher Folge.
    # Welche Kennung zu welcher dieser gleichartigen Buchungen gehoert, laesst sich nicht sagen; gezaehlt wird das eigens.
    types = {event[0]: event[1] for event in events}
    for members in undecided.values():
        values = members[0][2]
        if len(members) == len(values) and all(TOKEN.fullmatch(value) for value in values):
            for (_, event_ref, _), value in zip(sorted(members), values):
                choices.setdefault(event_ref, {})["transaction_id"] = value
                counts[(types[event_ref], "transaction_id", "ambiguous")] -= 1
                counts[(types[event_ref], "transaction_id", "new_among_alike_bookings")] += 1
    # Eine Kennung belegt hoechstens eine Buchung; beanspruchen sie mehrere, bleiben alle offen.
    claimed = Counter(_normal(choice["transaction_id"]) for choice in choices.values() if "transaction_id" in choice)
    entries = []
    for event_ref in sorted(choices):
        choice = dict(choices[event_ref])
        if "transaction_id" in choice and claimed[_normal(choice["transaction_id"])] > 1:
            del choice["transaction_id"]
            counts[(types[event_ref], "transaction_id", "new")] -= 1
            counts[(types[event_ref], "transaction_id", "ambiguous")] += 1
        if choice:
            before = current.get(event_ref, {})
            entries.append({"event_ref": event_ref, **{field: before.get(field) for field in FIELDS}, **choice})
    return {
        "contract_version": CONTRACT, "status": "planned", "event_count": len(events), "statement_row_count": len(statements["rows"]),
        "file_counts": statements["file_counts"], "entry_count": len(entries), "entries": entries,
        "counts": [{"event_type": key[0], "field": key[1], "outcome": key[2], "count": count} for key, count in sorted(counts.items()) if count],
        "source_write": False, "provider_access": False, "network_access": False, "canonical_write": False,
    }


def apply_statement_activity_reference_backfill_v1(space, context_value, statement_root, recorded_at_utc, confirmed) -> dict[str, Any]:
    """Schreibt die geplanten Angaben mit Herkunft 'statement_source'. Ein zweiter Lauf schreibt nichts."""
    if confirmed is not True:
        raise AssetActivityReferenceV1Error("activity_reference_confirmation_required")
    plan = plan_statement_activity_reference_backfill_v1(space, context_value, statement_root)
    written = unchanged = 0
    if plan["entries"]:
        result = record_activity_references_v1(space, context_value, plan["entries"], "statement_source", recorded_at_utc, True)
        written, unchanged = result["written_count"], result["unchanged_count"]
    return {"contract_version": CONTRACT, "status": "applied", "written_count": written, "unchanged_count": unchanged,
            "counts": plan["counts"], "file_counts": plan["file_counts"]}


__all__ = [
    "apply_statement_activity_reference_backfill_v1", "plan_statement_activity_reference_backfill_v1", "read_statement_rows_v1",
]
