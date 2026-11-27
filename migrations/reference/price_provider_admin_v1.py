"""Kursanbieter je Datenraum aktivieren (#495, rc.383).

Festlegungen vom 09.11.2026: Kursanbieter-Plugins werden **je Datenraum** aktiviert, nicht je Portfolio - die
Kurshistorie gehoert der Notierung, alle Portfolios teilen sie. Yahoo wird mitgeliefert und bei der Einrichtung zum Aktivieren
empfohlen. Einstellungen bleiben ueber Updates erhalten; ein neu mitgeliefertes Plugin startet nicht aktiv ("neu - noch nicht
eingestellt"). Beim Aktivieren zeigt Portelyra Bedingungen, Kosten und die Adressen, an die abgerufen wird: Dieser Dienst erfaehrt,
welche Kurse abgerufen werden (#546, Ergaenzung vom 09.11.).

Speicher ``price-provider-plugins-v1/provider-admin.sqlite`` im Datenraum (mit gesichert), nur anhaengend. Beim ersten Kontakt
("Bestand bis rc.382") ist ein Anbieter aktiv, wenn der Datenraum bereits Zuordnungen zu ihm fuehrt - mit ihm sind die bisherigen Kurse
entstanden. Gesperrt wird in den Skripten, die abrufen (``script_guard_v1``); der Code nennt das Modul (``<modul>_provider_inactive``).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from migrations.reference import price_provider_plugins_v1 as providers

AREA = "price-provider-plugins-v1"
STORE = "provider-admin.sqlite"
SCHEMA_VERSION = 1
FAILURE_CODES = (
    "price_provider_admin_input_invalid", "price_provider_admin_store_invalid", "price_provider_admin_preview_stale",
    "price_provider_admin_confirmation_required", "price_provider_inactive",
)
SCHEMA = (
    "CREATE TABLE provider_admin_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE provider_activation_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "provider_id TEXT NOT NULL CHECK(length(provider_id) BETWEEN 2 AND 41), plugin_id TEXT NOT NULL CHECK(length(plugin_id) BETWEEN 2 AND 41),"
    "plugin_version TEXT NOT NULL CHECK(length(plugin_version) BETWEEN 1 AND 40),"
    "active INTEGER NOT NULL CHECK(active IN (0, 1)), origin TEXT NOT NULL CHECK(origin IN ('existing_data_space','owner')),"
    "actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX provider_activation_key ON provider_activation_entry(provider_id, entry_id)",
    "CREATE TRIGGER provider_activation_no_update BEFORE UPDATE ON provider_activation_entry BEGIN SELECT RAISE(ABORT, 'provider_activation_immutable'); END",
    "CREATE TRIGGER provider_activation_no_delete BEFORE DELETE ON provider_activation_entry BEGIN SELECT RAISE(ABORT, 'provider_activation_immutable'); END",
)
COST_TEXT = {"free": "kostenlos", "free_quota": "kostenlos bis zu einem Kontingent, darüber kostenpflichtig", "paid": "kostenpflichtig"}


class PriceProviderAdminV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "price_provider_admin_input_invalid"


def _abort(code: str) -> None:
    raise PriceProviderAdminV1Error(code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


_TOKEN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


@dataclass(frozen=True)
class _Context:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str


def _context(value: Any) -> _Context:
    """Kontext aus der Data-App (desktop_owner) oder aus einem abrufenden Skript (market_worker)."""
    if isinstance(value, _Context):
        return value
    fields = ("tenant_id", "user_id", "data_space_id", "actor_id", "role")
    get = (lambda key: value.get(key)) if isinstance(value, Mapping) else (lambda key: getattr(value, key, None))
    items = {key: get(key) for key in fields}
    if items["role"] not in {"desktop_owner", "market_worker"} or not all(isinstance(items[key], str) and _TOKEN.fullmatch(items[key]) for key in fields[:4]):
        _abort("price_provider_admin_input_invalid")
    return _Context(items["tenant_id"], items["user_id"], items["data_space_id"], items["actor_id"])


def _space(space: Any, context: _Context) -> Path:
    path = Path(space)
    if not path.is_dir() or path.is_symlink() or path.name != context.data_space_id:
        _abort("price_provider_admin_store_invalid")
    return path


def _stamp(value: Any) -> str:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("price_provider_admin_input_invalid")
    return value


def store_present_v1(space: str | Path) -> bool:
    return (Path(space) / AREA / STORE).exists()


def _connect(space: str | Path, context: Any, create: bool) -> sqlite3.Connection | None:
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("price_provider_admin_store_invalid")
    expected = (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO provider_admin_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("price_provider_admin_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM provider_admin_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("price_provider_admin_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("price_provider_admin_store_invalid")
    return connection


def _mapped_providers(space: str | Path) -> set[str]:
    """Anbieter, zu denen der Datenraum Zuordnungen fuehrt (aktiv oder abgeschaltet)."""
    path = Path(space) / "canonical.sqlite"
    if not path.is_file():
        return set()
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "provider_mapping" not in tables:
                return set()
            return {str(row[0]) for row in connection.execute("SELECT DISTINCT provider_id FROM provider_mapping")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("price_provider_admin_store_invalid")
        return set()


def ensure_provider_baseline_v1(space: str | Path, context_value: Any, recorded_at_utc: str | None = None) -> str:
    """Erster Kontakt mit rc.383: Speicher anlegen; jeder mitgelieferte Anbieter, zu dem der Datenraum schon Zuordnungen fuehrt, ist
    aktiv ("Bestand bis rc.382"). Danach ohne Wirkung. Liefert "present", "baseline" oder "empty"."""
    context = _context(context_value)
    space = _space(space, context)
    if store_present_v1(space):
        return "present"
    mapped = _mapped_providers(space)
    specs = [spec for spec in providers.provider_specs_v1() if spec.origin == "shipped" and spec.provider_id in mapped]
    connection = _connect(space, context, True)
    stamp = recorded_at_utc or _now()
    try:
        with connection:
            for spec in specs:
                body = {"provider_id": spec.provider_id, "plugin_id": spec.plugin_id, "plugin_version": spec.plugin_version, "active": 1,
                        "origin": "existing_data_space", "actor_id": context.actor_id, "recorded_at_utc": stamp}
                connection.execute("INSERT INTO provider_activation_entry(provider_id,plugin_id,plugin_version,active,origin,actor_id,recorded_at_utc,"
                                   "entry_fingerprint) VALUES(?,?,?,?,?,?,?,?)",
                                   (spec.provider_id, spec.plugin_id, spec.plugin_version, 1, "existing_data_space", context.actor_id, stamp, _fingerprint(body)))
    except sqlite3.Error:
        _abort("price_provider_admin_store_invalid")
    finally:
        connection.close()
    return "baseline" if specs else "empty"


def _current(connection: sqlite3.Connection | None) -> dict[str, dict[str, Any]]:
    if connection is None:
        return {}
    rows = connection.execute("SELECT provider_id,plugin_id,plugin_version,active,origin,recorded_at_utc FROM provider_activation_entry ORDER BY entry_id").fetchall()
    current: dict[str, dict[str, Any]] = {}
    for row in rows:
        current[row["provider_id"]] = {"active": bool(row["active"]), "origin": row["origin"], "since": row["recorded_at_utc"],
                                       "plugin_version": row["plugin_version"]}
    return current


def _read_current(space: str | Path, context: Any) -> dict[str, dict[str, Any]]:
    connection = _connect(space, context, False)
    try:
        return _current(connection)
    except sqlite3.Error:
        _abort("price_provider_admin_store_invalid")
        return {}
    finally:
        if connection is not None:
            connection.close()


def active_providers_v1(space: str | Path, context_value: Any) -> set[str]:
    """Die aktiven Anbieter-Kennungen (nur gueltige, geladene Plugins). Legt beim ersten Kontakt den Bestandseintrag an."""
    context = _context(context_value)
    ensure_provider_baseline_v1(space, context)
    loaded = {spec.provider_id for spec in providers.provider_specs_v1()}
    return {provider for provider, state in _read_current(space, context).items() if state["active"] and provider in loaded}


def provider_active_v1(space: str | Path, context_value: Any, provider_id: str) -> bool:
    return provider_id in active_providers_v1(space, context_value)


def script_guard_v1(space: str | Path, context_value: Mapping[str, Any], prefix: str, provider_id: str = "yahoo") -> dict[str, Any] | None:
    """Fuer die abrufenden Skripte: None, wenn der Anbieter aktiv ist, sonst die Antwort ``blocked`` mit ``<prefix>_provider_inactive``.
    Ein ungueltiger Kontext oder Speicher sperrt ebenso, mit eigenem Code."""
    try:
        if provider_active_v1(space, context_value, provider_id):
            return None
        return {"status": "blocked", "code": f"{prefix}_provider_inactive", "provider_id": provider_id}
    except PriceProviderAdminV1Error as error:
        return {"status": "blocked", "code": error.code, "provider_id": provider_id}


def guard_payload_v1(payload: Any, prefix: str, provider_id: str = "yahoo") -> dict[str, Any] | None:
    """Fuer die abrufenden Skripte (Anfrage als JSON): None, wenn abgerufen werden darf, sonst die Antwort ``blocked``.
    Nicht aktiv: ``<prefix>_provider_inactive``; Verwaltungsspeicher unlesbar: ``<prefix>_provider_state_invalid``. Eine unvollstaendige
    Anfrage laesst die Pruefung des Skripts selbst scheitern (None)."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("context"), Mapping) or not isinstance(payload.get("data_space_path"), str):
        return None
    context = {"actor_id": "market_worker", "role": "market_worker", **payload["context"]}
    try:
        active = provider_active_v1(payload["data_space_path"], context, provider_id)
    except PriceProviderAdminV1Error as error:
        if error.code == "price_provider_admin_input_invalid":
            return None
        return {"status": "blocked", "code": f"{prefix}_provider_state_invalid", "provider_id": provider_id}
    if active:
        return None
    return {"status": "blocked", "code": f"{prefix}_provider_inactive", "provider_id": provider_id}


def overview_v1(space: str | Path, context_value: Any) -> dict[str, Any]:
    """Je Kursanbieter: Plugin, Version, Kosten, Adressen, Bedingungen, Abschottung, Stand im Datenraum."""
    context = _context(context_value)
    baseline = ensure_provider_baseline_v1(space, context)
    current = _read_current(space, context)
    isolated = providers.isolation_available_v1()
    rows = []
    for spec in providers.provider_specs_v1():
        state = current.get(spec.provider_id)
        rows.append({
            "provider_id": spec.provider_id, "plugin_id": spec.plugin_id, "plugin_version": spec.plugin_version, "label": spec.label,
            "publisher": spec.publisher, "origin": spec.origin, "replaces_shipped": spec.replaces_shipped, "operations": list(spec.operations), "hosts": list(spec.hosts),
            "cost": spec.cost, "cost_text": COST_TEXT[spec.cost], "terms_url": spec.terms_url, "credentials": [field.public() for field in spec.credentials],
            "history_max_days": spec.history_max_days, "isolated": isolated or spec.origin != "shipped",
            "active": bool(state and state["active"]), "state": "new" if state is None else ("active" if state["active"] else "inactive"),
            "origin_of_state": None if state is None else state["origin"], "since": None if state is None else state["since"],
        })
    return {"contract_version": "price_provider_overview_v1", "baseline": baseline, "isolation_available": isolated, "providers": rows,
            "problems": providers.provider_plugin_problems_v1()}


def _state_fingerprint(space: str | Path, context: Any) -> str:
    current = _read_current(space, context)
    specs = [(spec.provider_id, spec.plugin_id, spec.plugin_version, spec.manifest_sha256) for spec in providers.provider_specs_v1()]
    return _fingerprint({"current": current, "specs": specs})


def preview_activation_v1(space: str | Path, context_value: Any, provider_id: str, active: bool, created_at_utc: str | None = None) -> dict[str, Any]:
    """Vorschau einer Aenderung: was sich aendert, Bedingungen, Kosten, Adressen. Bindet den Stand, den sie zeigt."""
    context = _context(context_value)
    ensure_provider_baseline_v1(space, context)
    spec = providers.provider_spec_v1(provider_id) if isinstance(provider_id, str) else None
    if spec is None or not isinstance(active, bool):
        _abort("price_provider_admin_input_invalid")
    current = _read_current(space, context).get(provider_id)
    was = bool(current and current["active"])
    body = {"contract_version": "price_provider_activation_preview_v1", "provider_id": provider_id, "plugin_id": spec.plugin_id,
            "plugin_version": spec.plugin_version, "label": spec.label, "active_before": was, "active_after": active, "changed": was != active,
            "hosts": list(spec.hosts), "cost": spec.cost, "cost_text": COST_TEXT[spec.cost], "terms_url": spec.terms_url,
            "isolated": providers.isolation_available_v1() or spec.origin != "shipped", "origin": spec.origin,
            "state_fingerprint": _state_fingerprint(space, context), "created_at_utc": _stamp(created_at_utc or _now())}
    body["notes"] = _notes(body)
    body["preview_fingerprint"] = _fingerprint(body)
    return body


def _notes(preview: Mapping[str, Any]) -> list[str]:
    hosts = ", ".join(preview["hosts"])
    if not preview["active_after"]:
        return [f"Ohne aktiven Anbieter holt Portelyra für Assets mit Zuordnung zu {preview['label']} keine neuen Kurse; die vorhandene Kurshistorie bleibt."]
    notes = [f"Portelyra ruft Kurse bei {hosts} ab. Dieser Dienst erfährt dabei, welche Kurse abgerufen werden – also ungefähr, was Sie halten.",
             f"Kosten: {preview['cost_text']}. Abruf, Kosten und die Einhaltung der Bedingungen des Anbieters verantworten Sie; Portelyra ist kostenlos und ohne Gewähr.",
             f"Bedingungen des Anbieters: {preview['terms_url']}"]
    if not preview["isolated"]:
        notes.append("Auf diesem System steht die Abschottung nicht zur Verfügung: Das mitgelieferte, mit jedem Release geprüfte Plugin läuft in einem eigenen Prozess ohne Datei- und Netzsperre.")
    return notes


def activation_notes_v1(provider_id: Any) -> dict[str, Any]:
    """Was das Aktivieren zeigt, ohne Datenraum - fuer den Einrichtungsdialog (#555), der vor dem Anlegen fragt: Bezeichnung, Adressen,
    Kosten, Bedingungen und dieselben Hinweise wie die Vorschau. Aktiviert wird danach ueber Vorschau und Bestaetigung wie in der Karte."""
    spec = providers.provider_spec_v1(provider_id) if isinstance(provider_id, str) else None
    if spec is None:
        _abort("price_provider_admin_input_invalid")
    body = {"provider_id": spec.provider_id, "label": spec.label, "active_after": True, "hosts": list(spec.hosts), "cost": spec.cost,
            "cost_text": COST_TEXT[spec.cost], "terms_url": spec.terms_url, "credentials": bool(spec.credentials),
            "isolated": providers.isolation_available_v1() or spec.origin != "shipped"}
    body["notes"] = _notes(body)
    return body


def apply_activation_v1(space: str | Path, context_value: Any, preview: Mapping[str, Any], confirmed: bool, recorded_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    if confirmed is not True:
        _abort("price_provider_admin_confirmation_required")
    if not isinstance(preview, Mapping) or preview.get("contract_version") != "price_provider_activation_preview_v1":
        _abort("price_provider_admin_input_invalid")
    body = {key: value for key, value in preview.items() if key != "preview_fingerprint"}
    if preview.get("preview_fingerprint") != _fingerprint(body) or preview.get("state_fingerprint") != _state_fingerprint(space, context):
        _abort("price_provider_admin_preview_stale")
    spec = providers.provider_spec_v1(str(preview["provider_id"]))
    if spec is None or spec.plugin_version != preview.get("plugin_version"):
        _abort("price_provider_admin_preview_stale")
    if not preview["changed"]:
        return {"contract_version": "price_provider_activation_result_v1", "status": "unchanged", "provider_id": spec.provider_id, "active": preview["active_after"]}
    stamp = _stamp(recorded_at_utc or _now())
    active = 1 if preview["active_after"] else 0
    connection = _connect(space, context, True)
    try:
        with connection:
            entry = {"provider_id": spec.provider_id, "plugin_id": spec.plugin_id, "plugin_version": spec.plugin_version, "active": active,
                     "origin": "owner", "actor_id": context.actor_id, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO provider_activation_entry(provider_id,plugin_id,plugin_version,active,origin,actor_id,recorded_at_utc,"
                               "entry_fingerprint) VALUES(?,?,?,?,?,?,?,?)",
                               (spec.provider_id, spec.plugin_id, spec.plugin_version, active, "owner", context.actor_id, stamp, _fingerprint(entry)))
    except sqlite3.Error:
        _abort("price_provider_admin_store_invalid")
    finally:
        connection.close()
    return {"contract_version": "price_provider_activation_result_v1", "status": "recorded", "provider_id": spec.provider_id,
            "active": bool(active), "recorded_at_utc": stamp}


__all__ = [
    "AREA", "FAILURE_CODES", "PriceProviderAdminV1Error", "STORE", "activation_notes_v1", "active_providers_v1", "apply_activation_v1", "ensure_provider_baseline_v1",
    "guard_payload_v1", "overview_v1", "preview_activation_v1", "provider_active_v1", "script_guard_v1", "store_present_v1",
]
