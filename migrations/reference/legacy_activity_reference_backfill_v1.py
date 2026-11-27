"""Einmaliges Nachziehen: Kommentar der Legacy-Transaktionszeilen als Belegangabe zur Buchung.

Ein Legacy-Kommentar kann Kennungen (Order-ID einer Boerse, Transaktions-Hash) und
Freitext mischen. Eine zusammenhaengende Zeichenfolge mit Ziffer gilt als Transaktions-ID,
alles andere als Notiz - Freitext wird nie als Kennung ausgegeben.

Zuordnung in zwei Stufen. Zuerst exakt: Der Zeilenschluessel, den der
Legacy-Konverter je Quellzeile bildet, steht in der Quellbindung des gebuchten
Entwurfs; solange die Legacy-Datei unveraendert ist, trifft er genau eine Buchung.
Danach ueber Merkmale: dasselbe Asset, derselbe Tag, passende Art, dieselbe Menge,
bei mehreren Treffern dieselbe Minute. Was danach nicht eindeutig ist, bleibt
offen und wird gemeldet. Die Quelldateien werden nur gelesen.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
import re
import sqlite3

from migrations.reference import redundant_asset_activity_csv_v1 as _legacy
from migrations.reference.asset_activity_reference_v1 import (
    AssetActivityReferenceV1Error, FIELDS, activity_reference_scope_v1, read_activity_references_v1,
    record_activity_references_v1,
)
from migrations.reference.desktop_activity_draft_v1 import AREA_NAME as DRAFT_AREA, DRAFTS_NAME as DRAFT_DIR
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityV1Error, read_desktop_product_asset_activity_binding_v1,
)

CONTRACT = "legacy_activity_reference_backfill_v1"
LEGACY_TYPES = {
    "buy": {"Buy"}, "sell": {"Sell"}, "transfer": {"Transfer"}, "reward": {"Reward", "Interest"},
    "withdrawal": {"Sell", "Transfer"}, "deposit": {"Buy", "Transfer"}, "dividend": {"Dividend"},
    "stock_dividend": {"Dividend", "Buy"},
}
_ID_SHAPES = (
    re.compile(r"(0x)?[0-9a-fA-F]{64}"),
    re.compile(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"),
    re.compile(r"[A-Z0-9]{6}-[A-Z0-9]{5}-[A-Z0-9]{6}"),
)
_TOKEN = re.compile(r"[A-Za-z0-9_\-]{8,200}")


def classify_legacy_comment_v1(text) -> tuple[str, str | None]:
    """('transaction_id' | 'note' | 'empty', bereinigter Wert)."""
    value = "" if not isinstance(text, str) else " ".join(text.split())
    if value in ("", "NA"):
        return "empty", None
    if any(shape.fullmatch(value) for shape in _ID_SHAPES) or (
            _TOKEN.fullmatch(value) and any(char.isdigit() for char in value)):
        return "transaction_id", value
    cleaned = "".join(char for char in value if ord(char) >= 32 and ord(char) != 127)[:4000]
    return ("note", cleaned) if cleaned else ("empty", None)


def _quantity(text):
    value = (text or "").strip()
    if not value or value == "NA":
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return abs(Decimal(value)).normalize()
    except InvalidOperation:
        return None


def _rounded_equal(legacy_quantity, exact_quantity) -> bool:
    """Die Legacy-Menge ist die auf ihre eigene Stellenzahl gerundete oder abgeschnittene Buchungsmenge."""
    if legacy_quantity is None or exact_quantity is None:
        return False
    places = max(0, -legacy_quantity.as_tuple().exponent)
    if places < 4:
        return False
    step = Decimal(1).scaleb(-places)
    return abs(legacy_quantity - exact_quantity) < step


def _legacy_rows(root: Path) -> tuple[list[dict], int]:
    rows: list[dict] = []
    skipped = 0
    for path in sorted(root.rglob("*.csv")):
        if path.is_symlink():
            skipped += 1
            continue
        try:
            _, content, _ = _legacy._read_file(path)
            _, records = _legacy._parse_table(content, _legacy.LEGACY_TRANSACTION_HEADERS)
        except _legacy.RedundantAssetActivityCsvV1Error:
            skipped += 1
            continue
        fingerprint = _legacy._sha(content)
        for ordinal, values in enumerate(records, 1):
            reference = _legacy._source_ref({"file": fingerprint, "ordinal": ordinal, "row": values})
            rows.append({
                "row_key": _legacy._row_key({"source_reference": reference, "row": values}),
                "asset": (values.get("Asset_ID") or "").strip(), "date": (values.get("Datum") or "").strip()[:10],
                "minute": (values.get("Uhrzeit") or "").strip()[:5], "type": (values.get("Typ") or "").strip(),
                "quantity": _quantity(values.get("Stückzahl")), "comment": values.get("Kommentar") or "",
            })
    return rows, skipped


def _booked_row_keys(space: Path, live: set[str]) -> dict[str, str]:
    keys: dict[str, str] = {}
    drafts = space / DRAFT_AREA / DRAFT_DIR
    if not drafts.is_dir():
        return keys
    for path in sorted(drafts.glob("adt_*.json")):
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(draft, dict) or draft.get("draft_state") != "committed":
            continue
        binding, event = draft.get("source_binding"), draft.get("event")
        if isinstance(binding, dict) and isinstance(event, dict) and event.get("event_ref") in live:
            key = binding.get("source_row_key")
            if isinstance(key, str):
                keys[key] = event["event_ref"]
    return keys


def plan_legacy_activity_reference_backfill_v1(space, context_value, legacy_transaction_root) -> dict:
    """Lesend: je Buchung die aus dem Legacy-Kommentar gewonnene Angabe und der Weg, auf dem sie zugeordnet wurde."""
    context = activity_reference_scope_v1(context_value)
    space = Path(space)
    root = Path(legacy_transaction_root)
    if not root.is_dir() or root.is_symlink():
        raise AssetActivityReferenceV1Error("activity_reference_input_invalid")
    try:
        binding = read_desktop_product_asset_activity_binding_v1(space, context)
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        try:
            events = connection.execute(
                "SELECT event_ref,event_type,asset_id,local_date,local_time,quantity_decimal FROM current_asset_activity_event ORDER BY event_ref"
            ).fetchall()
        finally:
            connection.close()
    except (DesktopProductAssetActivityV1Error, sqlite3.Error, KeyError, TypeError):
        raise AssetActivityReferenceV1Error("activity_reference_store_invalid") from None
    legacy, skipped = _legacy_rows(root)
    live = {event[0] for event in events}
    by_key = {row["row_key"]: index for index, row in enumerate(legacy)}
    claims: dict[str, tuple[int, str]] = {}
    for key, event_ref in _booked_row_keys(space, live).items():
        if key in by_key:
            claims[event_ref] = (by_key[key], "source_row_key")
    # Merkmalsweg: Legacy-Asset je Buchungs-Asset ueber gemeinsame (Tag, Menge) bestimmen.
    pairs: dict[str, set] = defaultdict(set)
    for row in legacy:
        if row["quantity"] is not None:
            pairs[row["asset"]].add((row["date"], row["quantity"]))
    mine: dict[str, set] = defaultdict(set)
    for event in events:
        if event[5]:
            mine[event[2]].add((event[3], abs(Decimal(event[5])).normalize()))
    asset_map: dict[str, str] = {}
    for asset_id, own in mine.items():
        ranked = sorted(((len(pairs[name] & own), name) for name in pairs), reverse=True)[:2]
        if ranked and ranked[0][0] > 0 and (len(ranked) == 1 or ranked[0][0] > ranked[1][0]):
            asset_map[asset_id] = ranked[0][1]
    index: dict[tuple, list[int]] = defaultdict(list)
    for position, row in enumerate(legacy):
        index[(row["asset"], row["date"])].append(position)
    taken = {position for position, _ in claims.values()}
    open_reason: dict[str, str] = {}
    for event_ref, event_type, asset_id, local_date, local_time, quantity in events:
        if event_ref in claims:
            continue
        candidates = [position for position in index.get((asset_map.get(asset_id), local_date), [])
                      if legacy[position]["type"] in LEGACY_TYPES.get(event_type, set()) and position not in taken]
        if not candidates:
            open_reason[event_ref] = "no_legacy_row"
            continue
        path = "matching_features"
        if quantity:
            wanted = abs(Decimal(quantity)).normalize()
            exact = [position for position in candidates if legacy[position]["quantity"] == wanted]
            if not exact and local_time:
                # Legacy fuehrt die Menge gerundet: gleiche Minute und Menge bis auf die Legacy-Stellenzahl gleich.
                exact = [position for position in candidates
                         if legacy[position]["minute"] == local_time[:5] and _rounded_equal(legacy[position]["quantity"], wanted)]
                path = "matching_time_rounded_quantity"
            candidates = exact
        if len(candidates) > 1 and local_time:
            timed = [position for position in candidates if legacy[position]["minute"] == local_time[:5]]
            candidates = timed or candidates
        if len(candidates) == 1:
            claims[event_ref] = (candidates[0], path)
        else:
            open_reason[event_ref] = "ambiguous" if candidates else "quantity_differs"
    # Eine Legacy-Zeile belegt hoechstens eine Buchung; doppelt beanspruchte Zeilen bleiben offen.
    usage = Counter(position for position, _ in claims.values())
    for event_ref in [ref for ref, (position, _) in claims.items() if usage[position] > 1]:
        del claims[event_ref]
        open_reason[event_ref] = "ambiguous"
    types = {event[0]: event[1] for event in events}
    current = read_activity_references_v1(space, context)["references"]
    entries: list[dict] = []
    counts: Counter = Counter()
    for event_ref in sorted(claims):
        position, path = claims[event_ref]
        kind, value = classify_legacy_comment_v1(legacy[position]["comment"])
        before = current.get(event_ref, {})
        if kind == "empty":
            outcome = "empty"
        elif before.get(kind) == value:
            outcome = "already_recorded"
        elif before.get(kind) is not None:
            # Eine vorhandene Angabe wird nie ueberschrieben.
            outcome = "kept_existing_" + kind
        else:
            outcome = kind
            entries.append({"event_ref": event_ref, **{field: before.get(field) for field in FIELDS}, kind: value})
        counts[(types[event_ref], path, outcome)] += 1
    for event_ref, reason in open_reason.items():
        counts[(types[event_ref], "open", reason)] += 1
    return {
        "contract_version": CONTRACT, "status": "planned", "event_count": len(events), "legacy_row_count": len(legacy),
        "skipped_file_count": skipped, "entry_count": len(entries), "entries": entries,
        "counts": [{"event_type": key[0], "path": key[1], "outcome": key[2], "count": count} for key, count in sorted(counts.items())],
        "source_write": False, "provider_access": False, "network_access": False, "canonical_write": False,
    }


def apply_legacy_activity_reference_backfill_v1(space, context_value, legacy_transaction_root, recorded_at_utc, confirmed) -> dict:
    """Schreibt die geplanten Angaben mit Herkunft 'legacy_comment'. Ein zweiter Lauf schreibt nichts."""
    if confirmed is not True:
        raise AssetActivityReferenceV1Error("activity_reference_confirmation_required")
    plan = plan_legacy_activity_reference_backfill_v1(space, context_value, legacy_transaction_root)
    if not plan["entries"]:
        return {"contract_version": CONTRACT, "status": "applied", "written_count": 0, "unchanged_count": 0, "counts": plan["counts"]}
    result = record_activity_references_v1(space, context_value, plan["entries"], "legacy_comment", recorded_at_utc, True)
    return {"contract_version": CONTRACT, "status": "applied", "written_count": result["written_count"],
            "unchanged_count": result["unchanged_count"], "counts": plan["counts"]}


__all__ = [
    "apply_legacy_activity_reference_backfill_v1", "classify_legacy_comment_v1", "plan_legacy_activity_reference_backfill_v1",
]
