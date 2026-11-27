"""Disabled exchange CSV adapters producing provider-neutral Reward mapping rows.

Kraken, Coinbase and Bison rules are derived from the Legacy importer named in
ADR-172; BSDEX has no Legacy adapter. Since rc.377 (#486) each exchange reads in
its own reader plugin (domain reward, sandboxed); this core keeps the source row
keys, cross-file duplicates, the selected period and the candidates. The
projector is exact-decimal and accounts for every row.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any, Mapping

from migrations.reference import statement_reader_plugins_v1 as reader_plugins


class StatementExchangeRewardAdapterV1Error(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise StatementExchangeRewardAdapterV1Error(code)


# Die Leser der Boersen stehen seit rc.377 in ihren Plugins (Bereich reward, #486): Profil, Kopfzeile, Zahlen, Zeit, Reward-Arten und
# Bewertung. Der Kern bildet daraus wie bisher Schluessel, doppelte Zeilen, Zeitraum und Kandidaten; jede Zeile wird gezaehlt.
# Welche Reward-Leser es gibt, sagt allein die Leserliste (reward_reader_ids_v1); seit #486 keine feste Liste mehr.
MAX_SOURCE_BYTES = 32_000_000


def _decoded(source: bytes) -> str:
    """Groesse, Nullbytes und Zeichensatz wie bisher vor dem Lesen: so meldet ein kaputter Export weiter source_invalid."""
    if not isinstance(source, bytes) or not 0 < len(source) <= MAX_SOURCE_BYTES or b"\x00" in source:
        _abort("statement_exchange_adapter_source_invalid")
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return source.decode(encoding, errors="strict")
        except UnicodeDecodeError:
            continue
    _abort("statement_exchange_adapter_source_invalid")


def _read(adapter_id: str, sources: list[bytes]) -> list[dict[str, Any]]:
    """Liest jede Datei abgeschottet mit dem Leser der Boerse. Ein Export, der die Erkennungsregeln des Manifests nicht erfuellt,
    erreicht den Leser nicht (header_invalid)."""
    texts = [_decoded(source) for source in sources]
    for text in texts:
        if not reader_plugins.detection_passes_v1(adapter_id, reader_plugins.detection_texts_v1([text]), "reward"):
            _abort("statement_exchange_adapter_header_invalid")
    try:
        results = reader_plugins.run_reader_v1(adapter_id, [(source, "export.csv", None) for source in sources], "reward")
        read = []
        for result in results:
            if not result["ok"]:
                _abort(result["code"])
            read.append(reader_plugins.validate_reward_result_v1(result["value"]))
    except reader_plugins.StatementReaderBlocked as error:
        _abort(error.code)
    return read


def exchange_reward_rows_v1(adapter_id: str, sources: list[bytes]) -> list[dict[str, Any] | None]:
    """Je Datei das gepruefte Ergebnis des Reward-Lesers, oder None fuer eine Datei, die er nicht liest (fremdes Format, kaputt).
    Fuer das Nachtragen der Boersenkennungen (statement_reward_references_v1): liest nur. Ein Fehler des Kerns (etwa fehlende
    Abschottung) bricht ab."""
    if not isinstance(adapter_id, str) or reader_plugins.reader_spec_v1(adapter_id, "reward") is None:
        _abort("statement_exchange_adapter_profile_invalid")
    readable: list[int] = []
    for index, source in enumerate(sources):
        try:
            text = _decoded(source)
        except StatementExchangeRewardAdapterV1Error:
            continue
        if reader_plugins.detection_passes_v1(adapter_id, reader_plugins.detection_texts_v1([text]), "reward"):
            readable.append(index)
    found: list[dict[str, Any] | None] = [None] * len(sources)
    if not readable:
        return found
    try:
        results = reader_plugins.run_reader_v1(adapter_id, [(sources[index], "export.csv", None) for index in readable], "reward")
    except reader_plugins.StatementReaderBlocked as error:
        _abort(error.code)
    for index, result in zip(readable, results):
        if not result["ok"]:
            if result["code"] in reader_plugins.READER_ERROR_CODES["reward"]:
                continue
            _abort(result["code"])
        try:
            found[index] = reader_plugins.validate_reward_result_v1(result["value"])
        except reader_plugins.StatementReaderBlocked as error:
            _abort(error.code)
    return found


def _prepare(adapter_id: str, confirmed_timezone: str, owner_overlay: Mapping[str, Any] | None,
             period_start_date: str | None, period_end_date: str | None) -> dict[str, str] | None:
    if (period_start_date is None) != (period_end_date is None):
        _abort("statement_exchange_adapter_period_invalid")
    selected_period = None
    if period_start_date is not None:
        try:
            start = datetime.strptime(period_start_date, "%Y-%m-%d").date()
            end = datetime.strptime(period_end_date, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            _abort("statement_exchange_adapter_period_invalid")
        if start > end:
            _abort("statement_exchange_adapter_period_invalid")
        selected_period = {"start_date": period_start_date, "end_date": period_end_date}
    if not isinstance(adapter_id, str) or reader_plugins.reader_spec_v1(adapter_id, "reward") is None:
        _abort("statement_exchange_adapter_profile_invalid")
    # Formatueberlagerungen gibt es seit rc.377 nicht mehr: ein eigenes Format ist ein Leser-Plugin.
    if owner_overlay is not None:
        _abort("statement_exchange_adapter_overlay_invalid")
    return selected_period


def _zone(read: list[dict[str, Any]], confirmed_timezone: str) -> str:
    """Die Zeitzone der Zeiten im Export. Leer heisst: die des Lesers (#486) - die Data-App kennt die Zeitzone einer Boerse nicht fest,
    der Leser nennt sie. Eine genannte Zeitzone muss zu der des Lesers passen."""
    zones = {item["time_zone"] for item in read}
    if not isinstance(confirmed_timezone, str) or len(zones) != 1 or (confirmed_timezone and zones != {confirmed_timezone}):
        _abort("statement_exchange_adapter_timezone_invalid")
    return confirmed_timezone or zones.pop()


def project_exchange_reward_statement_v1(
    source_bytes: bytes, *, adapter_id: str, confirmed_timezone: str,
    owner_overlay: Mapping[str, Any] | None = None,
    period_start_date: str | None = None, period_end_date: str | None = None,
) -> dict[str, Any]:
    """Project Reward rows inside one explicit period; account for every source row."""
    selected_period = _prepare(adapter_id, confirmed_timezone, owner_overlay, period_start_date, period_end_date)
    read = _read(adapter_id, [source_bytes])
    zone = _zone(read, confirmed_timezone)
    return _project_entries(read[0]["rows"], hashlib.sha256(source_bytes).hexdigest(), adapter_id, read[0]["fee_role"], zone, selected_period)


# Woran eine Zeile ohne eigene Kennung in einer zweiten Datei wiedererkannt wird: die wirtschaftlichen Felder, nicht die ganze Zeile -
# Spalten wie ein Kontostand duerfen sich zwischen zwei Downloads unterscheiden. Die Felder liest der Leser (signature: Zeit, Art,
# Unterart, Coin, Menge, Gebuehr, Konto; Mengen als Zahl, Texte ohne Gross-/Kleinschreibung und Leerraum-Varianten).
def _duplicate_signature(row: Mapping[str, Any]) -> tuple[str, ...]:
    return ("id", row["row_id"]) if row["row_id"] else ("fields", *row["signature"])


def project_exchange_reward_statements_v1(
    sources: list[bytes] | tuple[bytes, ...], *, adapter_id: str, confirmed_timezone: str,
    owner_overlay: Mapping[str, Any] | None = None,
    period_start_date: str | None = None, period_end_date: str | None = None,
) -> dict[str, Any]:
    """Mehrere Exporte derselben Boerse als ein Lauf (rc.343).

    Anlass: Bison exportiert je Kalenderjahr; aus der Ablage kam bisher nur die Datei mit dem juengsten Reward, im Januar waeren die
    Dezember-Rewards des Vorjahres still weggefallen. Jetzt zaehlen alle Dateien. Eine Zeile, die schon in einer anderen Datei steht
    (Volldownloads ueberlappen), zaehlt einmal: erkannt an der Transaktionskennung oder, ohne Kennung, an den wirtschaftlichen Feldern.
    Gleiche Zeilen innerhalb einer Datei bleiben wie bisher getrennt. Die Reihenfolge der Dateien spielt keine Rolle.
    """
    if not isinstance(sources, (list, tuple)) or not 1 <= len(sources) <= 64 or any(not isinstance(item, bytes) for item in sources):
        _abort("statement_exchange_adapter_source_invalid")
    if len(sources) == 1:
        return project_exchange_reward_statement_v1(sources[0], adapter_id=adapter_id, confirmed_timezone=confirmed_timezone,
                                                    owner_overlay=owner_overlay, period_start_date=period_start_date,
                                                    period_end_date=period_end_date)
    if sum(len(item) for item in sources) > 64_000_000:
        _abort("statement_exchange_adapter_source_invalid")
    selected_period = _prepare(adapter_id, confirmed_timezone, owner_overlay, period_start_date, period_end_date)
    # Dieselbe Datei zweimal traegt nichts bei und zaehlt einmal.
    files = sorted({hashlib.sha256(item).hexdigest(): item for item in sources}.items())
    read = _read(adapter_id, [item for _, item in files])
    zone = _zone(read, confirmed_timezone)
    entries: list[dict[str, Any]] = []; earlier: dict[tuple[str, ...], int] = {}; dropped = 0
    for item in read:
        here: dict[tuple[str, ...], int] = {}
        for row in item["rows"]:
            signature = _duplicate_signature(row)
            here[signature] = here.get(signature, 0) + 1
            if here[signature] <= earlier.get(signature, 0):
                dropped += 1; continue
            entries.append(row)
        for signature, count in here.items():
            earlier[signature] = max(earlier.get(signature, 0), count)
    fingerprint = hashlib.sha256(("portelyra_exchange_reward_files_v1\0" + "\0".join(f for f, _ in files)).encode("utf-8")).hexdigest()
    result = _project_entries(entries, fingerprint, adapter_id, read[0]["fee_role"], zone, selected_period)
    result.update(source_file_count=len(files), cross_file_duplicate_count=dropped)
    return result


def _project_entries(entries: list[dict[str, Any]], fingerprint: str, adapter_id: str, fee_role: str,
                     confirmed_timezone: str, selected_period: dict[str, str] | None) -> dict[str, Any]:
    if selected_period is not None:
        start = datetime.strptime(selected_period["start_date"], "%Y-%m-%d").date()
        end = datetime.strptime(selected_period["end_date"], "%Y-%m-%d").date()
    rows = []; mapping_rows = []
    seen: set[str] = set()
    for ordinal, entry in enumerate(entries, 1):
        # Traegt die Quelle eine eigene Transaktionskennung, bindet der Schluessel
        # nur sie - nicht die Datei. Sonst aendert ein neuer Volldownload jeden
        # Schluessel, und schon gebuchte Rewards gelten wieder als neu
        # (#421). Kraken
        # liefert txid, Coinbase die erste Spalte, Bison Transaction ID; BSDEX
        # hat keine, dort bleibt es bei Datei und Zeilennummer.
        authored = entry["row_id"]
        if authored:
            key_seed = f"{adapter_id}\0id\0{authored}".encode("utf-8")
        else:
            identity = "row\0" + str(ordinal) + "\0" + "\0".join(entry["cells"])
            key_seed = f"{adapter_id}\0{fingerprint}\0{identity}".encode("utf-8")
        row_key = "row_" + hashlib.sha256(key_seed).hexdigest()[:32]
        if row_key in seen:
            rows.append({"source_row_ordinal": ordinal, "source_row_key": row_key, "disposition": "duplicate_deferred", "reason_code": "duplicate_source_row_key", "mapping_row": None}); continue
        seen.add(row_key)
        if entry["kind"] == "other":
            rows.append({"source_row_ordinal": ordinal, "source_row_key": row_key, "disposition": "deferred", "reason_code": "nonreward_source_event", "mapping_row": None}); continue
        if entry["kind"] == "invalid":
            rows.append({"source_row_ordinal": ordinal, "source_row_key": row_key, "disposition": "diagnostic", "reason_code": "reward_source_fields_invalid", "mapping_row": None}); continue
        if selected_period is not None and not (start <= datetime.strptime(entry["local_date"], "%Y-%m-%d").date() <= end):
            rows.append({"source_row_ordinal": ordinal, "source_row_key": row_key, "disposition": "deferred", "reason_code": "outside_selected_period", "mapping_row": None}); continue
        fee, valuation = entry["fee"], dict(entry["valuation"])
        event_fields = {"event_type": "reward", "event_time_evidence": "exact", "local_date": entry["local_date"], "local_time": entry["local_time"], "time_zone": confirmed_timezone, "quantity_decimal": entry["quantity"], "original_acquired_time_evidence": "not_applicable", "movement_context_code": "not_applicable"}
        if fee is not None and fee_role == "asset_quantity": event_fields.update(asset_fee_quantity_decimal=fee, fee_role="asset_quantity", fee_currency="ASSET")
        elif fee is not None and fee_role == "monetary": event_fields.update(monetary_fee_decimal=fee, fee_role="monetary", fee_currency=valuation["price_currency"])
        mapping = {"source_row_ordinal": ordinal, "source_row_key": row_key, "source_asset_key": entry["asset"], "source_account_key": entry["account"], "event_type": "reward", "event_fields": event_fields, "valuation": valuation}
        rows.append({"source_row_ordinal": ordinal, "source_row_key": row_key, "disposition": "reward_candidate_disabled", "reason_code": "reward_requires_owner_mapping", "mapping_row": mapping})
        mapping_rows.append(mapping)
    counts = {key: sum(row["disposition"] == key for row in rows) for key in ("reward_candidate_disabled", "deferred", "diagnostic", "duplicate_deferred")}
    return {"statement_exchange_reward_adapter_version": 1, "status": "exchange_reward_adapter_projected_disabled", "adapter_id": adapter_id, "source_fingerprint": fingerprint, "selected_period": selected_period, "source_row_count": len(rows), "rows": rows, "mapping_rows": mapping_rows, "disposition_counts": counts, "silent_drop_count": 0, "activation_authorized": False, "activity_draft_write": False, "canonical_write": False, "cash_write": False, "tax_write": False, "provider_access": False, "network_access": False}


__all__ = ["StatementExchangeRewardAdapterV1Error", "exchange_reward_rows_v1", "project_exchange_reward_statement_v1", "project_exchange_reward_statements_v1"]
