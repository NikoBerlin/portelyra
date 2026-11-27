"""Recognises Statement Reward candidates that are already booked.

Two independent ways, in this order:

Primary is the source row key. Where the exchange carries its own transaction
identifier - Kraken txid, the Coinbase id column, the Bison Transaction ID - the
adapter binds that identifier alone, so the key survives a fresh full-history
download. A committed Draft holding the same key proves the row is booked, no
matter how its time, quantity or custody account were once recorded.

Fallback is the economic identity: Reward, Asset, custody Account, exact
effective time and quantity. It carries BSDEX, which ships no identifier, and
every event booked before the Statement path existed. It breaks on any
divergence - a shifted time zone, a rounded quantity, a different custody
account - which is why it may no longer stand alone (#421).

Matches are reported, never written.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from migrations.reference.asset_activity_csv_import_v1 import _existing_event_rows
from migrations.reference import statement_reader_plugins_v1 as reader_plugins
from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, read_activity_references_v1
from migrations.reference.desktop_asset_activity_correction_v1 import read_desktop_asset_activity_voided_event_refs_v1
from migrations.reference.desktop_activity_draft_v1 import (
    AREA_NAME as DRAFT_AREA_NAME, DRAFTS_NAME as DRAFT_DRAFTS_NAME,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityV1Error, _context, read_desktop_product_asset_activity_binding_v1,
    resolve_desktop_asset_activity_time_v1,
)


class StatementRewardBookedMatchV1Error(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _identity(asset_id: Any, account_id: Any, effective_at_utc: Any, quantity: Any) -> tuple[Any, ...]:
    return ("reward", asset_id, account_id, effective_at_utc, quantity)


def _committed_source_row_keys(data_space: Path, voided: Mapping[str, str]) -> set[str]:
    """Source row keys of committed Reward Drafts whose booking still stands. Read-only; a damaged file is skipped.

    Eine stornierte Buchung beweist nichts mehr (#509): Wer Rewards storniert, um sie auf ein anderes Konto neu einzulesen,
    braucht dieselben Zeilen wieder. Gefolgt wird der Korrekturkette; eine Korrektur laesst die Zeile gebucht."""
    drafts = data_space / DRAFT_AREA_NAME / DRAFT_DRAFTS_NAME
    if not drafts.is_dir():
        return set()
    keys: set[str] = set()
    for path in sorted(drafts.glob("adt_*.json")):
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(draft, Mapping) or draft.get("draft_state") != "committed":
            continue
        event = draft.get("event")
        if not isinstance(event, Mapping) or event.get("event_type") != "reward":
            continue
        binding = draft.get("source_binding")
        if not isinstance(binding, Mapping):
            continue
        if event.get("event_ref") in voided:
            continue
        key = binding.get("source_row_key")
        if isinstance(key, str) and key:
            keys.add(key)
    return keys


# Leser mit eigener Transaktionskennung (Manifest "row_ids"); ihr source_row_key haengt nur an Leser und Kennung
# (statement_exchange_reward_adapter_v1).


def _manual_reward_keys(data_space: Path, context: Any, reward_event_refs: set[str]) -> set[str]:
    """Schluessel aus den Transaktions-IDs gebuchter Rewards. Liest nur; ein unlesbarer Belegspeicher liefert keine."""
    try:
        references = read_activity_references_v1(data_space, context)["references"]
    except (AssetActivityReferenceV1Error, OSError):
        return set()
    keys: set[str] = set()
    for event_ref, entry in references.items():
        transaction_id = entry.get("transaction_id")
        if event_ref not in reward_event_refs or not isinstance(transaction_id, str) or not transaction_id:
            continue
        for adapter_id in [item for item in reader_plugins.reward_reader_ids_v1() if reader_plugins.reward_reader_has_row_ids_v1(item)]:
            keys.add("row_" + hashlib.sha256(f"{adapter_id}\0id\0{transaction_id}".encode("utf-8")).hexdigest()[:32])
    return keys


def match_booked_statement_rewards_v1(data_space_path: str | Path, context_value: Any, candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    try:
        context = _context(context_value)
    except DesktopProductAssetActivityV1Error:
        raise StatementRewardBookedMatchV1Error("statement_reward_booked_match_input_invalid") from None
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)) or len(candidates) > 100000:
        raise StatementRewardBookedMatchV1Error("statement_reward_booked_match_input_invalid")
    data_space = Path(data_space_path)
    # Der candidate_key ist der source_row_key der Quellzeile (siehe
    # data_statement_import_mapping_v1.R). Traegt die Boerse eine eigene
    # Transaktionskennung, ist er ueber Exporte hinweg stabil - ein committeter
    # Entwurf mit demselben Schluessel beweist dann die Buchung.
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    committed_keys = _committed_source_row_keys(data_space, read_desktop_asset_activity_voided_event_refs_v1(data_space, context))
    rows = _existing_event_rows(binding)
    # Von Hand in "Manuell" gebuchte Rewards (#520): Traegt die Buchung die Kennung der Boerse als Transaktions-ID, gilt sie wie ein
    # committeter Entwurf mit demselben Schluessel. Sonst kaeme ein um Sekunden versetzter Reward beim naechsten Import wieder als neu.
    committed_keys |= _manual_reward_keys(data_space, context, {row["event_ref"] for row in rows if row["event_type"] == "reward"})
    booked: dict[tuple[Any, ...], int] = {}
    for row in rows:
        if row["event_type"] == "reward" and row["event_time_evidence"] == "exact":
            key = _identity(row["asset_id"], row["account_id"], row["effective_at_utc"], row["quantity_decimal"])
            booked[key] = booked.get(key, 0) + 1
    matched = []
    matched_by_key = 0
    for candidate in candidates:
        required = {"candidate_key", "asset_id", "account_id", "local_date", "local_time", "time_zone", "quantity_decimal"}
        if not isinstance(candidate, Mapping) or set(candidate) != required or not all(isinstance(candidate[k], str) and candidate[k] for k in required):
            raise StatementRewardBookedMatchV1Error("statement_reward_booked_match_input_invalid")
        # Der Quellschluessel geht vor: er haelt auch, wenn Zeitzone, Rundung
        # oder Verwahrkonto der Altbuchung abweichen.
        if candidate["candidate_key"] in committed_keys:
            matched.append(candidate["candidate_key"])
            matched_by_key += 1
            continue
        try:
            effective = resolve_desktop_asset_activity_time_v1(candidate["local_date"], candidate["local_time"], candidate["time_zone"])["effective_at_utc"]
        except DesktopProductAssetActivityV1Error:
            continue
        key = _identity(candidate["asset_id"], candidate["account_id"], effective, candidate["quantity_decimal"])
        # Each booked event absorbs at most one candidate: two genuine equal Rewards stay visible.
        if booked.get(key, 0) > 0:
            booked[key] -= 1
            matched.append(candidate["candidate_key"])
    return {
        "statement_reward_booked_match_version": 1, "matched_candidate_keys": matched,
        "candidate_count": len(candidates), "matched_by_source_row_key": matched_by_key,
        "matched_by_economic_identity": len(matched) - matched_by_key, "canonical_write": False,
    }


__all__ = ["StatementRewardBookedMatchV1Error", "match_booked_statement_rewards_v1"]
