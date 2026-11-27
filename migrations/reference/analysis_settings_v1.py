"""Einstellungen der Analyse neben den Stammdaten: Vergleichsindizes (#482, #502) und eigene Asset-Gruppen (#483 Stufe 2).

Festlegung (20.-22.10.2026):

- **Vergleichsindizes** (#502): mehrere, jeder aus einem oder mehreren Assets des Katalogs mit Kurshistorie und Gewichten in
  Prozent (zusammen genau 100), auch wenn sie nicht gehalten werden. Die Gewichte gelten taeglich fest. Bis rc.298 gab es genau
  einen Index aus einem Asset (`benchmark_entry`); er erscheint als erster Index, solange kein Index gespeichert ist, und wird
  beim ersten Speichern eines Index als solcher uebernommen. Die Tabelle `benchmark_index_entry` kam mit rc.299 hinzu; ein
  aelterer Speicher erhaelt sie beim ersten Schreiben (nur ergaenzt, nichts geaendert). Die Form der Bestandteile (Asset und
  Gewicht) soll eine spaetere Ziel-Allokation (#505) wiederverwenden.
- **Eigene Gruppen**, zwei Arten: *frei* (beliebige Zusammenstellung, ein Asset darf in mehreren Gruppen stehen) und als Teil
  einer *lueckenlosen Aufteilung* (die Gruppen einer Aufteilung schneiden sich nicht und ergaenzen das Portfolio zu 100 %).
  Assets, die nach dem Speichern dazukamen, zaehlen nicht mit, werden aber als Warnung genannt; die Gruppe laesst sich dann
  aktualisieren.

Die Angaben sind eine Sicht auf den Bestand, keine Wirtschaftstatsache. Sie liegen wie die Zugehoerigkeit zur Anlage neben
den Stammdaten; Buchungen, FIFO und Bewertung beruehren sie nicht. Der Speicher haengt nur an; der gueltige Stand ist der
juengste Eintrag, ein Eintrag ohne Wert leert ihn. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from pathlib import Path
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
import sqlite3

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error, _context,
)

AREA = "analysis-settings-v1"
STORE = "analysis-settings.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "analysis_settings_v1"
ASSET_ID = re.compile(r"ast_[a-z0-9_]{4,60}")
GROUP_KEY = re.compile(r"grp_[0-9a-f]{32}")
INDEX_KEY = re.compile(r"idx_[0-9a-f]{32}")
# Gewicht in Prozent mit hoechstens zwei Nachkommastellen, groesser als 0 und hoechstens 100.
WEIGHT = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,2})?")
INDEX_LIMIT = 10
COMPONENT_LIMIT = 10
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
MEMBER_LIMIT = 2000
FAILURE_CODES = (
    "analysis_settings_asset_unknown",
    "analysis_settings_confirmation_required",
    "analysis_settings_group_unknown",
    "analysis_settings_index_unknown",
    "analysis_settings_input_invalid",
    "analysis_settings_label_taken",
    "analysis_settings_partition_overlap",
    "analysis_settings_store_invalid",
    "analysis_settings_weights_invalid",
)
SCHEMA = (
    "CREATE TABLE analysis_settings_binding("
    "singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE benchmark_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT, recorded_at_utc TEXT NOT NULL,"
    " entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TABLE asset_group_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, group_key TEXT NOT NULL, label TEXT,"
    " partition_label TEXT, members_json TEXT NOT NULL, seen_assets_json TEXT NOT NULL, recorded_at_utc TEXT NOT NULL,"
    " entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX asset_group_entry_key ON asset_group_entry(group_key, entry_id)",
    *(f"CREATE TRIGGER {table}_no_{action} BEFORE {action.upper()} ON {table} BEGIN SELECT RAISE(ABORT, '{table}_immutable'); END"
      for table in ("benchmark_entry", "asset_group_entry") for action in ("update", "delete")),
    "CREATE VIEW current_asset_group AS SELECT entry.* FROM asset_group_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM asset_group_entry later WHERE later.group_key = entry.group_key)",
)
# Seit rc.299 (#502): Vergleichsindizes aus Bestandteilen mit Gewicht. Ein Eintrag ohne Bezeichnung entfernt den Index.
INDEX_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS benchmark_index_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, index_key TEXT NOT NULL, label TEXT,"
    " components_json TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX IF NOT EXISTS benchmark_index_entry_key ON benchmark_index_entry(index_key, entry_id)",
    *(f"CREATE TRIGGER IF NOT EXISTS benchmark_index_entry_no_{action} BEFORE {action.upper()} ON benchmark_index_entry BEGIN "
      f"SELECT RAISE(ABORT, 'benchmark_index_entry_immutable'); END" for action in ("update", "delete")),
    "CREATE VIEW IF NOT EXISTS current_benchmark_index AS SELECT entry.*, (SELECT min(first.entry_id) FROM benchmark_index_entry first"
    " WHERE first.index_key = entry.index_key) AS first_entry_id FROM benchmark_index_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM benchmark_index_entry later WHERE later.index_key = entry.index_key)",
)


class AnalysisSettingsV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def analysis_settings_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise AnalysisSettingsV1Error(code if code in FAILURE_CODES else "analysis_settings_store_invalid")


def analysis_settings_context_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("analysis_settings_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("analysis_settings_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("analysis_settings_input_invalid")


def _fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("analysis_settings_store_invalid")
    expected = (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in (*SCHEMA, *INDEX_SCHEMA):
                    connection.execute(statement)
                connection.execute("INSERT INTO analysis_settings_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("analysis_settings_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM analysis_settings_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("analysis_settings_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("analysis_settings_store_invalid")
    if create:
        # Ein Speicher von vor rc.299 erhaelt die Tabelle der Vergleichsindizes beim ersten Schreiben.
        try:
            with connection:
                for statement in INDEX_SCHEMA:
                    connection.execute(statement)
        except sqlite3.Error:
            connection.close()
            _abort("analysis_settings_store_invalid")
    return connection


def _catalog(space, context) -> dict[str, dict]:
    """Die Assets der Stammdaten mit Bezeichnung und Art - gelesen, nicht veraendert. Cash zaehlt nicht."""
    canonical = Path(space) / "canonical.sqlite"
    if not canonical.is_file() or canonical.is_symlink():
        _abort("analysis_settings_store_invalid")
    try:
        connection = sqlite3.connect(f"file:{canonical}?mode=ro", uri=True)
        try:
            binding = connection.execute("SELECT tenant_id,user_id,data_space_id FROM store_binding WHERE singleton_id=1").fetchall()
            if len(binding) != 1 or tuple(binding[0]) != (context.tenant_id, context.user_id, context.data_space_id):
                _abort("analysis_settings_store_invalid")
            return {row[0]: {"label": row[1], "asset_type": row[2]} for row in connection.execute(
                "SELECT asset_id, display_name, asset_type FROM asset WHERE asset_type <> 'cash'")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("analysis_settings_store_invalid")
        return {}


def _label(value, *, optional: bool = False, maximum: int = 80) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str):
        _abort("analysis_settings_input_invalid")
    text = " ".join(value.split())
    if not text:
        if optional:
            return None
        _abort("analysis_settings_input_invalid")
    if len(text) > maximum or any(ord(char) < 32 for char in text):
        _abort("analysis_settings_input_invalid")
    return text


def _stamp(value) -> str:
    if not isinstance(value, str) or UTC.fullmatch(value) is None:
        _abort("analysis_settings_input_invalid")
    return value


def _current_groups(connection) -> dict[str, dict]:
    rows = connection.execute("SELECT group_key,label,partition_label,members_json,seen_assets_json,recorded_at_utc FROM current_asset_group "
                              "ORDER BY group_key").fetchall()
    return {row["group_key"]: {"label": row["label"], "partition": row["partition_label"], "members": json.loads(row["members_json"]),
                               "seen": json.loads(row["seen_assets_json"]), "recorded_at_utc": row["recorded_at_utc"]}
            for row in rows if row["label"] is not None}


def _has_index_table(connection) -> bool:
    return connection.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='benchmark_index_entry'").fetchone()[0] == 1


def _legacy_index(connection) -> dict | None:
    """Der Einzelindex bis rc.298 als Index aus einem Asset mit 100 % - nur solange kein Index gespeichert wurde."""
    if _has_index_table(connection) and connection.execute("SELECT count(*) FROM benchmark_index_entry").fetchone()[0]:
        return None
    row = connection.execute("SELECT asset_id, recorded_at_utc FROM benchmark_entry ORDER BY entry_id DESC LIMIT 1").fetchone()
    if row is None or row["asset_id"] is None:
        return None
    return {"index_key": "idx_" + _fingerprint({"legacy_benchmark": row["asset_id"]})[:32], "label": None,
            "components": [{"asset_id": row["asset_id"], "weight_percent": "100"}], "recorded_at_utc": row["recorded_at_utc"], "legacy": True}


def _current_indices(connection) -> list[dict]:
    """Die gueltigen Indizes in der Reihenfolge ihres ersten Speicherns; der erste ist der vorgewaehlte Bezugsindex."""
    if not _has_index_table(connection):
        return []
    rows = connection.execute("SELECT index_key,label,components_json,recorded_at_utc FROM current_benchmark_index "
                              "WHERE label IS NOT NULL ORDER BY first_entry_id").fetchall()
    return [{"index_key": row["index_key"], "label": row["label"], "components": json.loads(row["components_json"]),
             "recorded_at_utc": row["recorded_at_utc"], "legacy": False} for row in rows]


def _percent_text(value: Decimal) -> str:
    text = format(value.quantize(Decimal("0.01")), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _components(value, catalog: dict[str, dict]) -> list[dict]:
    """Bestandteile eines Index: 1 bis 10 verschiedene Assets der Stammdaten, je ein Gewicht in Prozent, zusammen genau 100."""
    if not isinstance(value, (list, tuple)) or not 1 <= len(value) <= COMPONENT_LIMIT:
        _abort("analysis_settings_input_invalid")
    result, seen, total = [], set(), Decimal("0")
    for item in value:
        if not isinstance(item, dict) or set(item) != {"asset_id", "weight_percent"}:
            _abort("analysis_settings_input_invalid")
        asset, weight = item["asset_id"], item["weight_percent"]
        if not isinstance(asset, str) or ASSET_ID.fullmatch(asset) is None or asset in seen:
            _abort("analysis_settings_input_invalid")
        if asset not in catalog:
            _abort("analysis_settings_asset_unknown")
        if not isinstance(weight, str) or WEIGHT.fullmatch(weight) is None:
            _abort("analysis_settings_weights_invalid")
        try:
            number = Decimal(weight)
        except InvalidOperation:
            _abort("analysis_settings_weights_invalid")
        if not Decimal("0") < number <= Decimal("100"):
            _abort("analysis_settings_weights_invalid")
        seen.add(asset); total += number
        result.append({"asset_id": asset, "weight_percent": _percent_text(number)})
    if total != Decimal("100"):
        _abort("analysis_settings_weights_invalid")
    return result


def _materialize_legacy(connection, catalog: dict[str, dict]) -> None:
    """Vor dem ersten Index-Eintrag: den Einzelindex bis rc.298 als ersten Index uebernehmen, damit er nicht verschwindet."""
    legacy = _legacy_index(connection)
    if legacy is None:
        return
    asset = legacy["components"][0]["asset_id"]
    label = (catalog.get(asset) or {}).get("label") or asset
    row = {"index_key": legacy["index_key"], "label": label[:80], "components": legacy["components"], "recorded_at_utc": legacy["recorded_at_utc"]}
    connection.execute("INSERT INTO benchmark_index_entry(index_key,label,components_json,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?)",
                       (row["index_key"], row["label"], json.dumps(row["components"]), row["recorded_at_utc"], _fingerprint(row)))


def record_benchmark_index_v1(space, context_value, index_key, label, components, recorded_at_utc, confirmed) -> dict:
    """Legt einen Vergleichsindex an (index_key None) oder schreibt seinen neuen Stand: Name und Bestandteile mit Gewicht.
    Unveraendert schreibt nichts."""
    if confirmed is not True:
        _abort("analysis_settings_confirmation_required")
    context = analysis_settings_context_v1(context_value)
    stamp = _stamp(recorded_at_utc)
    name = _label(label)
    if index_key is not None and (not isinstance(index_key, str) or INDEX_KEY.fullmatch(index_key) is None):
        _abort("analysis_settings_input_invalid")
    catalog = _catalog(space, context)
    parts = _components(components, catalog)
    connection = _connect(space, context, True)
    try:
        with connection:
            _materialize_legacy(connection, catalog)
            indices = {row["index_key"]: row for row in _current_indices(connection)}
            if index_key is not None and index_key not in indices:
                _abort("analysis_settings_index_unknown")
            if any(other["label"].casefold() == name.casefold() for key, other in indices.items() if key != index_key):
                _abort("analysis_settings_label_taken")
            if index_key is None and len(indices) >= INDEX_LIMIT:
                _abort("analysis_settings_input_invalid")
            key = index_key or "idx_" + _fingerprint({"label": name, "recorded_at_utc": stamp, "components": parts})[:32]
            before = indices.get(key)
            if before is not None and (before["label"], before["components"]) == (name, parts):
                return {"contract_version": CONTRACT, "status": "unchanged", "index_key": key, "provider_access": False,
                        "network_access": False, "canonical_write": False}
            row = {"index_key": key, "label": name, "components": parts, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO benchmark_index_entry(index_key,label,components_json,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?)",
                               (key, name, json.dumps(parts), stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("analysis_settings_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "index_key": key, "provider_access": False, "network_access": False,
            "canonical_write": False}


def remove_benchmark_index_v1(space, context_value, index_key, recorded_at_utc, confirmed) -> dict:
    """Entfernt einen Vergleichsindex: ein Eintrag ohne Bezeichnung. Seine fruehere Fassung bleibt im Speicher."""
    if confirmed is not True:
        _abort("analysis_settings_confirmation_required")
    context = analysis_settings_context_v1(context_value)
    stamp = _stamp(recorded_at_utc)
    if not isinstance(index_key, str) or INDEX_KEY.fullmatch(index_key) is None:
        _abort("analysis_settings_input_invalid")
    catalog = _catalog(space, context)
    connection = _connect(space, context, True)
    try:
        with connection:
            _materialize_legacy(connection, catalog)
            if index_key not in {row["index_key"] for row in _current_indices(connection)}:
                _abort("analysis_settings_index_unknown")
            row = {"index_key": index_key, "label": None, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO benchmark_index_entry(index_key,label,components_json,recorded_at_utc,entry_fingerprint) VALUES(?,NULL,'[]',?,?)",
                               (index_key, stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("analysis_settings_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "removed", "provider_access": False, "network_access": False, "canonical_write": False}


def record_asset_group_v1(space, context_value, group_key, label, partition_label, members, recorded_at_utc, confirmed) -> dict:
    """Legt eine Gruppe an (group_key None) oder schreibt ihren neuen Stand. Teil einer Aufteilung: Kein Mitglied darf schon in
    einer anderen Gruppe derselben Aufteilung stehen. Gemerkt wird, welche Assets es beim Speichern gab - spaeter
    hinzugekommene nennt die Anzeige als Warnung."""
    if confirmed is not True:
        _abort("analysis_settings_confirmation_required")
    context = analysis_settings_context_v1(context_value)
    stamp = _stamp(recorded_at_utc)
    name = _label(label)
    partition = _label(partition_label, optional=True)
    if group_key is not None and (not isinstance(group_key, str) or GROUP_KEY.fullmatch(group_key) is None):
        _abort("analysis_settings_input_invalid")
    if not isinstance(members, (list, tuple)) or not 1 <= len(members) <= MEMBER_LIMIT or len(set(members)) != len(members):
        _abort("analysis_settings_input_invalid")
    if any(not isinstance(member, str) or ASSET_ID.fullmatch(member) is None for member in members):
        _abort("analysis_settings_input_invalid")
    catalog = _catalog(space, context)
    if any(member not in catalog for member in members):
        _abort("analysis_settings_asset_unknown")
    connection = _connect(space, context, True)
    try:
        with connection:
            groups = _current_groups(connection)
            if group_key is not None and group_key not in groups:
                _abort("analysis_settings_group_unknown")
            if any(other["label"].casefold() == name.casefold() for key, other in groups.items() if key != group_key):
                _abort("analysis_settings_label_taken")
            if partition is not None:
                taken = {member for key, other in groups.items() if key != group_key and other["partition"] is not None
                         and other["partition"].casefold() == partition.casefold() for member in other["members"]}
                if taken & set(members):
                    _abort("analysis_settings_partition_overlap")
                # Dieselbe Aufteilung in derselben Schreibweise wie die vorhandenen Gruppen.
                partition = next((other["partition"] for key, other in groups.items() if key != group_key and other["partition"] is not None
                                  and other["partition"].casefold() == partition.casefold()), partition)
            key = group_key or "grp_" + _fingerprint({"label": name, "recorded_at_utc": stamp, "members": sorted(members)})[:32]
            row = {"group_key": key, "label": name, "partition": partition, "members": sorted(members), "seen": sorted(catalog),
                   "recorded_at_utc": stamp}
            before = groups.get(key)
            if before is not None and (before["label"], before["partition"], sorted(before["members"]), sorted(before["seen"])) == (
                    name, partition, sorted(members), sorted(catalog)):
                return {"contract_version": CONTRACT, "status": "unchanged", "group_key": key, "provider_access": False,
                        "network_access": False, "canonical_write": False}
            connection.execute(
                "INSERT INTO asset_group_entry(group_key,label,partition_label,members_json,seen_assets_json,recorded_at_utc,entry_fingerprint) "
                "VALUES(?,?,?,?,?,?,?)", (key, name, partition, json.dumps(sorted(members)), json.dumps(sorted(catalog)), stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("analysis_settings_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "group_key": key, "provider_access": False, "network_access": False,
            "canonical_write": False}


def remove_asset_group_v1(space, context_value, group_key, recorded_at_utc, confirmed) -> dict:
    """Entfernt eine Gruppe: ein Eintrag ohne Bezeichnung. Ihre fruehere Fassung bleibt im Speicher."""
    if confirmed is not True:
        _abort("analysis_settings_confirmation_required")
    context = analysis_settings_context_v1(context_value)
    stamp = _stamp(recorded_at_utc)
    if not isinstance(group_key, str) or GROUP_KEY.fullmatch(group_key) is None:
        _abort("analysis_settings_input_invalid")
    connection = _connect(space, context, True)
    try:
        with connection:
            if group_key not in _current_groups(connection):
                _abort("analysis_settings_group_unknown")
            row = {"group_key": group_key, "label": None, "recorded_at_utc": stamp}
            connection.execute(
                "INSERT INTO asset_group_entry(group_key,label,partition_label,members_json,seen_assets_json,recorded_at_utc,entry_fingerprint) "
                "VALUES(?,NULL,NULL,'[]','[]',?,?)", (group_key, stamp, _fingerprint(row)))
    except sqlite3.Error:
        _abort("analysis_settings_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "removed", "provider_access": False, "network_access": False, "canonical_write": False}


def read_analysis_settings_v1(space, context_value) -> dict:
    """Vergleichsindizes und Gruppen mit ihrem Stand. Je Index die Bestandteile mit Bezeichnung und Gewicht und wie viele es
    nicht mehr gibt ('missing_count'); je Gruppe die Assets, die seit dem Speichern dazukamen ('new_assets'), und Mitglieder,
    die es nicht mehr gibt ('missing_count'); je Aufteilung die Assets, die in keiner ihrer Gruppen stehen. 'assets' listet die
    Assets der Stammdaten zur Wahl."""
    context = analysis_settings_context_v1(context_value)
    connection = _connect(space, context, False)
    stored_indices: list[dict] = []
    groups: dict[str, dict] = {}
    if connection is not None:
        try:
            legacy = _legacy_index(connection)
            stored_indices = ([legacy] if legacy is not None else []) + _current_indices(connection)
            groups = _current_groups(connection)
        except (sqlite3.Error, ValueError):
            _abort("analysis_settings_store_invalid")
        finally:
            connection.close()
    catalog = _catalog(space, context)
    indices = []
    for entry in stored_indices:
        components = [{**item, "label": catalog[item["asset_id"]]["label"], "asset_type": catalog[item["asset_id"]]["asset_type"]}
                      for item in entry["components"] if item["asset_id"] in catalog]
        label = entry["label"] or (components[0]["label"] if components else None)
        if label is None:
            continue
        indices.append({"index_key": entry["index_key"], "label": label, "components": components,
                        "missing_count": len(entry["components"]) - len(components), "recorded_at_utc": entry["recorded_at_utc"],
                        "legacy": entry["legacy"]})
    rows = []
    for key, group in sorted(groups.items(), key=lambda item: item[1]["label"].casefold()):
        members = [member for member in group["members"] if member in catalog]
        rows.append({"group_key": key, "label": group["label"], "partition": group["partition"], "members": members,
                     "missing_count": len(group["members"]) - len(members),
                     "new_assets": sorted((asset for asset in catalog if asset not in set(group["seen"])), key=lambda asset: catalog[asset]["label"].casefold()),
                     "recorded_at_utc": group["recorded_at_utc"]})
    partitions: dict[str, dict] = {}
    for row in rows:
        if row["partition"] is None:
            continue
        entry = partitions.setdefault(row["partition"], {"label": row["partition"], "groups": [], "covered": set()})
        entry["groups"].append(row["group_key"]); entry["covered"].update(row["members"])
    partition_rows = [{"label": entry["label"], "groups": entry["groups"],
                       "uncovered": sorted((asset for asset in catalog if asset not in entry["covered"]), key=lambda asset: catalog[asset]["label"].casefold())}
                      for entry in sorted(partitions.values(), key=lambda entry: entry["label"].casefold())]
    return {"contract_version": CONTRACT, "status": "ready", "indices": indices, "groups": rows, "partitions": partition_rows,
            "assets": [{"asset_id": asset, "label": meta["label"], "asset_type": meta["asset_type"]}
                       for asset, meta in sorted(catalog.items(), key=lambda item: item[1]["label"].casefold())],
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = [
    "AREA", "FAILURE_CODES", "STORE", "AnalysisSettingsV1Error", "analysis_settings_context_v1", "analysis_settings_v1_error_codes",
    "read_analysis_settings_v1", "record_asset_group_v1", "record_benchmark_index_v1", "remove_asset_group_v1", "remove_benchmark_index_v1",
]
