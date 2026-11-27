"""Kennung der Boerse an gebuchten Rewards (rc.345).

Der Krypto-Steuerreport nennt je Reward die Transaktionskennung der Boerse (Pflichtangabe, BMF 06.03.2025 Rn. 102-104). Sie steht
im Belegspeicher neben der Buchung. Der Reward-Import trug dort bisher nichts ein: Rewards, die er seit rc.246 gebucht hat, standen
ohne Kennung im Report.

Kraken, Coinbase und Bison exportieren je Zeile eine eigene Kennung; der Leser bindet den Zeilenschluessel allein an sie. Ueber diesen
Schluessel findet sich der gebuchte Entwurf und ueber dessen Korrekturkette die stehende Buchung. BSDEX exportiert keine Kennung -
dort bleibt die Luecke, wie im Report vermerkt.

Geschrieben wird nur, wo die Buchung noch keine Kennung traegt; Notiz und Adresse bleiben. Eine stornierte Buchung bekommt nichts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from migrations.reference import statement_reader_plugins_v1 as reader_plugins
from migrations.reference.asset_activity_reference_v1 import TOKEN, read_activity_references_v1, record_activity_references_v1
from migrations.reference.desktop_activity_draft_v1 import AREA_NAME as DRAFT_AREA_NAME, DRAFTS_NAME as DRAFT_DRAFTS_NAME
from migrations.reference.desktop_asset_activity_correction_v1 import resolve_desktop_asset_activity_live_event_refs_v1
from migrations.reference.statement_exchange_reward_adapter_v1 import StatementExchangeRewardAdapterV1Error, exchange_reward_rows_v1

# Leser mit eigener Kennung je Zeile (Manifest "row_ids", reward_reader_has_row_ids_v1); ihr Schluessel ist
# "row_" + sha256(Leser \0 id \0 Kennung)[:32].
MAX_SOURCES = 256
MAX_SOURCE_BYTES = 64_000_000


class StatementRewardReferencesV1Error(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise StatementRewardReferencesV1Error(code)


def reward_row_key_v1(adapter_id: str, transaction_id: str) -> str:
    return "row_" + hashlib.sha256(f"{adapter_id}\0id\0{transaction_id}".encode("utf-8")).hexdigest()[:32]


def exchange_reward_transaction_ids_v1(sources: Sequence[bytes], adapter_id: str) -> dict[str, str]:
    """Zeilenschluessel -> Kennung der Boerse, aus allen lesbaren Dateien dieses Lesers. Liest nur; eine fremde Datei wird uebergangen."""
    if not reader_plugins.reward_reader_has_row_ids_v1(adapter_id):
        return {}
    # Seit rc.377 liest der Reward-Leser im Plugin der Boerse (abgeschottet); jede Zeile nennt ihre Kennung, auch ohne Reward.
    try:
        read = exchange_reward_rows_v1(adapter_id, list(sources))
    except StatementExchangeRewardAdapterV1Error as error:
        _abort(error.code)
    found: dict[str, str] = {}
    for item in read:
        for row in (item or {}).get("rows", []):
            if row["row_id"]:
                found[reward_row_key_v1(adapter_id, row["row_id"])] = row["row_id"]
    return found


def _committed_reward_drafts(data_space: Path) -> dict[str, list[str]]:
    """Zeilenschluessel -> Buchungskennungen gebuchter Reward-Entwuerfe. Eine unlesbare Datei wird uebergangen."""
    drafts = data_space / DRAFT_AREA_NAME / DRAFT_DRAFTS_NAME
    found: dict[str, list[str]] = {}
    if not drafts.is_dir():
        return found
    for path in sorted(drafts.glob("adt_*.json")):
        try:
            draft = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        event = draft.get("event") if isinstance(draft, Mapping) else None
        binding = draft.get("source_binding") if isinstance(draft, Mapping) else None
        if draft.get("draft_state") != "committed" or not isinstance(event, Mapping) or event.get("event_type") != "reward" or not isinstance(binding, Mapping):
            continue
        key, ref = binding.get("source_row_key"), event.get("event_ref")
        if isinstance(key, str) and isinstance(ref, str):
            found.setdefault(key, []).append(ref)
    return found


def record_reward_statement_references_v1(data_space_path: str | Path, context_value: Any, adapter_id: str, sources: Sequence[bytes],
                                          recorded_at_utc: str) -> dict[str, Any]:
    """Traegt die Kennung der Boerse an gebuchten Rewards nach, die noch keine tragen. Herkunft "statement_source"."""
    if not reader_plugins.reward_reader_has_row_ids_v1(adapter_id):
        return {"contract_version": "statement_reward_references_v1", "status": "no_identifier_in_source", "candidate_count": 0,
                "booked_count": 0, "written_count": 0, "already_present_count": 0, "invalid_identifier_count": 0, "canonical_write": False}
    if not isinstance(sources, (list, tuple)) or len(sources) > MAX_SOURCES or any(not isinstance(item, bytes) for item in sources) \
            or sum(len(item) for item in sources) > MAX_SOURCE_BYTES:
        _abort("statement_reward_references_input_invalid")
    data_space = Path(data_space_path)
    ids = exchange_reward_transaction_ids_v1(sources, adapter_id)
    drafts = _committed_reward_drafts(data_space)
    wanted = {ref: ids[key] for key, refs in drafts.items() if key in ids for ref in refs}
    live = resolve_desktop_asset_activity_live_event_refs_v1(data_space, context_value, list(wanted))
    targets: dict[str, str] = {}
    for ref, transaction_id in wanted.items():
        current = live.get(ref)
        if current is not None:
            targets.setdefault(current, transaction_id)
    stored = read_activity_references_v1(data_space, context_value)["references"] if targets else {}
    entries, present, invalid = [], 0, 0
    for ref, transaction_id in sorted(targets.items()):
        before = stored.get(ref) or {}
        if before.get("transaction_id"):
            present += 1
            continue
        if TOKEN.fullmatch(transaction_id) is None:
            invalid += 1
            continue
        entries.append({"event_ref": ref, "transaction_id": transaction_id, "counterparty_address": before.get("counterparty_address"),
                        "note": before.get("note")})
    written = 0
    for start in range(0, len(entries), 1000):
        written += record_activity_references_v1(data_space, context_value, entries[start:start + 1000], "statement_source", recorded_at_utc, True)["written_count"]
    return {"contract_version": "statement_reward_references_v1", "status": "recorded" if written else "nothing_to_record",
            "candidate_count": len(ids), "booked_count": len(targets), "written_count": written, "already_present_count": present,
            "invalid_identifier_count": invalid, "canonical_write": False}


__all__ = ["StatementRewardReferencesV1Error", "exchange_reward_transaction_ids_v1",
           "record_reward_statement_references_v1", "reward_row_key_v1"]
