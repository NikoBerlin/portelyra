"""Zugaenge fuer Plugins: API-Schluessel und Passwoerter einheitlich und geschuetzt (#546, rc.389).

Festlegungen vom 09.11.2026 (#546 samt Ergaenzung):
- Geheimes liegt nur im Schluesselbund des Systems (Linux: Secret Service ueber ``secret-tool``). Im Datenraum stehen nur der Verweis,
  die Bezeichnung, die letzten vier Zeichen (bei kurzen Werten keine) und die bestaetigten Adressen.
- Nie in Datenraum, Backup, Export, Logs, Artefakten, Herkunftsangaben, Fehlermeldungen, Prozessargumenten oder Umgebungsvariablen:
  ``secret-tool`` bekommt den Wert ueber stdin, Fehler tragen nur Codes.
- Ein Zugang gilt nur am Ort des Datenraums, an dem er eingetragen wurde (Festlegung 09.11.2026): Zur Kennung des Datenraums kommt im
  Schluesselbund ein Abdruck des Ordnerpfads. Eine Kopie des Datenraums an anderem Ort findet keinen Wert und kann den echten weder
  pruefen noch ersetzen noch loeschen; ein Backup am selben Ort funktioniert weiter, nach einem Umzug wird neu eingetragen.
- Ein Zugang ist an sein Plugin und die beim Eintragen bestaetigten Hosts gebunden. Der Kern setzt den Wert nur in Anfragen an genau diese
  Hosts ein, nur als Kopfzeile oder Parameter (Stelle laut Manifest), nie im Pfad. Aendert ein Update die Hosts oder Felder, bleibt der
  Zugang gesperrt, bis der Nutzer neu bestaetigt bzw. neu eintraegt.
- Das Plugin sieht den Wert nie: Es baut die Anfrage ohne ihn, der Kern setzt ihn ein, ruft ab und entfernt ihn aus der Antwort, bevor das
  Plugin sie liest. Die Auswertung wird zusaetzlich auf den Wert geprueft.
- Ohne Schluesselbund sind Plugins mit Zugang nicht nutzbar; es gibt keine unverschluesselte Datei als Ausweg. Nach Wiederherstellung oder
  auf einem neuen Rechner fehlen die Werte (nicht im Backup): "Zugang fehlt - neu eintragen".
- Schutzziel (Festlegung 09.11.): der private Nutzer mit eigenem Login. Der Schluesselbund ist mit der Anmeldung entsperrt; Programme in
  der eigenen Sitzung koennen ihn lesen - wie alle anderen privaten Dateien. Fuer Bankzugaenge (#544) mit dem Passwortschutz (#535).

Speicher ``plugin-credentials-v1/credentials.sqlite`` im Datenraum (mit gesichert, enthaelt nichts Geheimes), nur anhaengend bis auf den
Zeitpunkt der letzten erfolgreichen Nutzung. Jede Aenderung mit Vorschau und Einmalbestaetigung.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets as _random
import shutil
import sqlite3
import subprocess
import sys
from typing import Any, Mapping
from urllib.parse import parse_qsl, quote, quote_plus

from migrations.reference import price_provider_costs_v1 as costs
from migrations.reference import price_provider_plugins_v1 as providers

AREA = "plugin-credentials-v1"
STORE = "credentials.sqlite"
SCHEMA_VERSION = 1
PLUGIN_KINDS = ("price_provider",)
APPLICATION = "portelyra"
KEYRING_TOOL_ENV = "PORTELYRA_SECRET_TOOL_INTERNAL"   # Tests: Pfad zu einem erfundenen secret-tool
KEYRING_TIMEOUT_SECONDS = 20
SECRET_MIN_LENGTH = 6
VALUE_MAX_LENGTH = 4096
REDACTED = b"[Zugang]"
FAILURE_CODES = (
    "plugin_credentials_input_invalid", "plugin_credentials_value_invalid", "plugin_credentials_store_invalid",
    "plugin_credentials_preview_stale", "plugin_credentials_confirmation_required", "plugin_credentials_plugin_unavailable",
    "plugin_credentials_keyring_unavailable", "plugin_credentials_keyring_failed", "plugin_credentials_not_found",
    "plugin_credentials_missing", "plugin_credentials_hosts_unconfirmed", "plugin_credentials_fields_changed",
    "plugin_credentials_choice_required", "plugin_credentials_placement_conflict", "plugin_credentials_check_unsupported",
    "plugin_credentials_secret_leak", "plugin_credentials_other_location",
)
SCHEMA = (
    "CREATE TABLE credential_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE credential_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "credential_ref TEXT NOT NULL CHECK(length(credential_ref) = 36 AND substr(credential_ref, 1, 4) = 'crd_'),"
    "event TEXT NOT NULL CHECK(event IN ('created','replaced','hosts_confirmed','deleted')),"
    "plugin_kind TEXT NOT NULL CHECK(plugin_kind IN ('price_provider')), plugin_id TEXT NOT NULL CHECK(length(plugin_id) BETWEEN 2 AND 41),"
    "plugin_label TEXT NOT NULL, label TEXT NOT NULL CHECK(length(label) BETWEEN 1 AND 60), fields_json TEXT NOT NULL, hosts_json TEXT NOT NULL,"
    "manifest_sha256 TEXT NOT NULL, location TEXT NOT NULL CHECK(length(location) = 32), actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL,"
    "entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX credential_entry_key ON credential_entry(credential_ref, entry_id)",
    "CREATE TRIGGER credential_entry_no_update BEFORE UPDATE ON credential_entry BEGIN SELECT RAISE(ABORT, 'credential_entry_immutable'); END",
    "CREATE TRIGGER credential_entry_no_delete BEFORE DELETE ON credential_entry BEGIN SELECT RAISE(ABORT, 'credential_entry_immutable'); END",
    "CREATE TABLE credential_choice(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, consumer_kind TEXT NOT NULL CHECK(consumer_kind IN ('price_provider')),"
    "consumer_id TEXT NOT NULL, credential_ref TEXT NOT NULL, actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL) STRICT",
    "CREATE TRIGGER credential_choice_no_update BEFORE UPDATE ON credential_choice BEGIN SELECT RAISE(ABORT, 'credential_choice_immutable'); END",
    "CREATE TRIGGER credential_choice_no_delete BEFORE DELETE ON credential_choice BEGIN SELECT RAISE(ABORT, 'credential_choice_immutable'); END",
    # Einzige veraenderliche Angabe: wann der Zugang zuletzt erfolgreich genutzt wurde.
    "CREATE TABLE credential_success(credential_ref TEXT PRIMARY KEY, succeeded_at_utc TEXT NOT NULL) STRICT",
)
STATE_TEXT = {
    "ready": "bereit",
    "missing": "Zugang fehlt – neu eintragen",
    "hosts_unconfirmed": "neue Adressen – bitte bestätigen",
    "fields_changed": "Plugin verlangt andere Angaben – neu eintragen",
    "plugin_unavailable": "Plugin nicht vorhanden",
    "keyring_unavailable": "Schlüsselbund nicht erreichbar",
    "other_location": "gehört zum Datenraum am ursprünglichen Ort – hier gesperrt; nach einem Umzug Werte neu eintragen",
}


class PluginCredentialsV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "plugin_credentials_input_invalid"


def _abort(code: str) -> None:
    raise PluginCredentialsV1Error(code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


_TOKEN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_REF = re.compile(r"^crd_[0-9a-f]{32}$")


@dataclass(frozen=True)
class _Context:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str


def _context(value: Any) -> _Context:
    if isinstance(value, _Context):
        return value
    fields = ("tenant_id", "user_id", "data_space_id", "actor_id", "role")
    get = (lambda key: value.get(key)) if isinstance(value, Mapping) else (lambda key: getattr(value, key, None))
    items = {key: get(key) for key in fields}
    if items["role"] not in {"desktop_owner", "market_worker"} or not all(isinstance(items[key], str) and _TOKEN.fullmatch(items[key]) for key in fields[:4]):
        _abort("plugin_credentials_input_invalid")
    return _Context(items["tenant_id"], items["user_id"], items["data_space_id"], items["actor_id"])


def _space(space: Any, context: _Context) -> Path:
    path = Path(space)
    if not path.is_dir() or path.is_symlink() or path.name != context.data_space_id:
        _abort("plugin_credentials_store_invalid")
    return path


def _stamp(value: Any) -> str:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("plugin_credentials_input_invalid")
    return value


# ---------------------------------------------------------------------------------------------------------------------------
# Schluesselbund des Systems
# ---------------------------------------------------------------------------------------------------------------------------

KEYRING_HINTS = {
    "available": "Der Schlüsselbund des Systems ist erreichbar.",
    "tool_missing": "Für Zugänge braucht Portelyra den Schlüsselbund des Systems: bitte das Paket libsecret-tools installieren "
                    "(z. B. sudo apt install libsecret-tools). Plugins ohne Zugang laufen weiter.",
    "service_unavailable": "Der Schlüsselbund (GNOME-Schlüsselbund oder KWallet) ist nicht erreichbar. Er startet normalerweise mit der "
                           "Anmeldung am Desktop. Plugins ohne Zugang laufen weiter.",
    "unsupported_platform": "Auf diesem Betriebssystem ist die Anbindung an den Schlüsselbund noch nicht gebaut; Plugins mit Zugang sind "
                            "nicht nutzbar. Plugins ohne Zugang laufen weiter.",
}


def _tool() -> str | None:
    override = os.environ.get(KEYRING_TOOL_ENV)
    if override:
        return override if Path(override).is_file() else None
    for candidate in ("/usr/bin/secret-tool", "/usr/local/bin/secret-tool"):
        if Path(candidate).is_file():
            return candidate
    return shutil.which("secret-tool")


def _run_tool(arguments: list[str], secret: bytes | None = None) -> subprocess.CompletedProcess:
    tool = _tool()
    if tool is None:
        _abort("plugin_credentials_keyring_unavailable")
    try:
        # Der Wert geht nur ueber stdin; Argumente tragen Verweise, nie Geheimes.
        return subprocess.run([tool, *arguments], input=secret if secret is not None else b"", capture_output=True,
                              timeout=KEYRING_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError):
        _abort("plugin_credentials_keyring_unavailable")
        raise


def keyring_status_v1() -> dict[str, str]:
    """Ob der Schluesselbund nutzbar ist, mit dem Hinweis, was fehlt. Liest nichts aus (Abfrage eines Eintrags, den es nie gibt)."""
    if not sys.platform.startswith("linux"):
        status = "unsupported_platform"
    elif _tool() is None:
        status = "tool_missing"
    else:
        try:
            completed = _run_tool(["lookup", "application", APPLICATION, "portelyra_probe", "status"])
            status = "available" if completed.returncode in (0, 1) and not completed.stderr.strip() else "service_unavailable"
        except PluginCredentialsV1Error:
            status = "service_unavailable"
    return {"status": status, "hint": KEYRING_HINTS[status]}


def location_v1(space: str | Path) -> str:
    """Abdruck des Ordnerpfads (aufgeloest) - nicht der Pfad selbst, damit im Schluesselbund kein Home-Pfad steht."""
    return hashlib.sha256(str(Path(space).resolve()).encode("utf-8")).hexdigest()[:32]


def _attributes(space: Path, context: _Context, credential_ref: str, field: str) -> list[str]:
    return ["application", APPLICATION, "portelyra_data_space", context.data_space_id, "portelyra_location", location_v1(space),
            "portelyra_credential", credential_ref, "portelyra_field", field]


def _keyring_store(space: Path, context: _Context, credential_ref: str, field: str, label: str, value: str) -> None:
    completed = _run_tool(["store", f"--label={label}", *_attributes(space, context, credential_ref, field)], value.encode("utf-8"))
    if completed.returncode != 0:
        _abort("plugin_credentials_keyring_failed")


def _keyring_lookup(space: Path, context: _Context, credential_ref: str, field: str) -> str | None:
    completed = _run_tool(["lookup", *_attributes(space, context, credential_ref, field)])
    if completed.returncode == 1 and not completed.stderr.strip():
        return None
    if completed.returncode != 0:
        _abort("plugin_credentials_keyring_unavailable")
    try:
        return completed.stdout.decode("utf-8")
    except UnicodeError:
        return None


def _keyring_clear(space: Path, context: _Context, credential_ref: str, field: str) -> None:
    completed = _run_tool(["clear", *_attributes(space, context, credential_ref, field)])
    if completed.returncode not in (0, 1) or (completed.returncode == 1 and completed.stderr.strip()):
        _abort("plugin_credentials_keyring_failed")


def _require_keyring() -> None:
    if keyring_status_v1()["status"] != "available":
        _abort("plugin_credentials_keyring_unavailable")


# ---------------------------------------------------------------------------------------------------------------------------
# Speicher im Datenraum (nichts Geheimes)
# ---------------------------------------------------------------------------------------------------------------------------

def store_present_v1(space: str | Path) -> bool:
    return (Path(space) / AREA / STORE).exists()


def _connect(space: Path, context: _Context, create: bool) -> sqlite3.Connection | None:
    root = space / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("plugin_credentials_store_invalid")
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
                connection.execute("INSERT INTO credential_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("plugin_credentials_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM credential_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("plugin_credentials_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("plugin_credentials_store_invalid")
    return connection


def _read(space: Path, context: _Context) -> tuple[dict[str, dict[str, Any]], dict[tuple[str, str], str], dict[str, str]]:
    """Stand je Zugang (aus den Eintraegen), Wahl je Verbraucher, letzte erfolgreiche Nutzung."""
    connection = _connect(space, context, False)
    if connection is None:
        return {}, {}, {}
    try:
        credentials: dict[str, dict[str, Any]] = {}
        for row in connection.execute("SELECT * FROM credential_entry ORDER BY entry_id"):
            ref = row["credential_ref"]
            if row["event"] == "created":
                credentials[ref] = {"credential_ref": ref, "plugin_kind": row["plugin_kind"], "plugin_id": row["plugin_id"],
                                    "plugin_label": row["plugin_label"], "label": row["label"], "created_at_utc": row["recorded_at_utc"],
                                    "deleted": False}
            elif ref not in credentials:
                _abort("plugin_credentials_store_invalid")
            entry = credentials[ref]
            entry.update(fields=json.loads(row["fields_json"]), hosts=json.loads(row["hosts_json"]), manifest_sha256=row["manifest_sha256"],
                         location=row["location"], updated_at_utc=row["recorded_at_utc"], label=row["label"])
            if row["event"] == "deleted":
                entry["deleted"] = True
        choices = {(row["consumer_kind"], row["consumer_id"]): row["credential_ref"]
                   for row in connection.execute("SELECT consumer_kind,consumer_id,credential_ref FROM credential_choice ORDER BY entry_id")}
        success = {row["credential_ref"]: row["succeeded_at_utc"] for row in connection.execute("SELECT * FROM credential_success")}
        return credentials, choices, success
    except (sqlite3.Error, ValueError):
        _abort("plugin_credentials_store_invalid")
        raise
    finally:
        connection.close()


def _state_fingerprint(space: Path, context: _Context) -> str:
    credentials, choices, _success = _read(space, context)
    return _fingerprint({"credentials": credentials, "choices": sorted([list(key) + [value] for key, value in choices.items()])})


def _insert(space: Path, context: _Context, ref: str, event: str, record: Mapping[str, Any], stamp: str) -> None:
    connection = _connect(space, context, True)
    body = {"credential_ref": ref, "event": event, "plugin_kind": record["plugin_kind"], "plugin_id": record["plugin_id"],
            "plugin_label": record["plugin_label"], "label": record["label"], "fields": record["fields"], "hosts": record["hosts"],
            "manifest_sha256": record["manifest_sha256"], "location": record["location"], "actor_id": context.actor_id, "recorded_at_utc": stamp}
    try:
        with connection:
            connection.execute("INSERT INTO credential_entry(credential_ref,event,plugin_kind,plugin_id,plugin_label,label,fields_json,hosts_json,"
                               "manifest_sha256,location,actor_id,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                               (ref, event, record["plugin_kind"], record["plugin_id"], record["plugin_label"], record["label"],
                                json.dumps(record["fields"], sort_keys=True, ensure_ascii=False), json.dumps(record["hosts"]),
                                record["manifest_sha256"], record["location"], context.actor_id, stamp, _fingerprint(body)))
    except sqlite3.Error:
        _abort("plugin_credentials_store_invalid")
    finally:
        connection.close()


# ---------------------------------------------------------------------------------------------------------------------------
# Plugins, Felder, Werte
# ---------------------------------------------------------------------------------------------------------------------------

def _plugin(plugin_kind: Any, plugin_id: Any) -> providers.ProviderSpec:
    if plugin_kind not in PLUGIN_KINDS or not isinstance(plugin_id, str):
        _abort("plugin_credentials_input_invalid")
    spec = providers.provider_spec_v1(plugin_id)
    if spec is None or not spec.credentials:
        _abort("plugin_credentials_plugin_unavailable")
    return spec


def _mask(value: str) -> str | None:
    """Die letzten vier Zeichen - nur bei Werten ab zwoelf Zeichen, sonst verraten sie zu viel."""
    return value[-4:] if len(value) >= 12 else None


def _values(spec: providers.ProviderSpec, values: Any) -> dict[str, str]:
    """Alle Felder laut Manifest; Leerzeichen am Anfang und Ende entfernt (haeufig beim Einfuegen), keine Steuerzeichen."""
    names = [field.name for field in spec.credentials]
    if not isinstance(values, Mapping) or set(values) != set(names):
        _abort("plugin_credentials_value_invalid")
    clean: dict[str, str] = {}
    for field in spec.credentials:
        value = values[field.name]
        if not isinstance(value, str):
            _abort("plugin_credentials_value_invalid")
        value = value.strip(" \t\r\n")
        if not value or len(value) > VALUE_MAX_LENGTH or any(ord(char) < 32 or ord(char) == 127 for char in value) \
                or (field.secret and len(value) < SECRET_MIN_LENGTH):
            _abort("plugin_credentials_value_invalid")
        clean[field.name] = value
    return clean


def _public_fields(spec: providers.ProviderSpec, values: Mapping[str, str]) -> list[dict[str, Any]]:
    return [{"name": field.name, "label": field.label, "secret": field.secret,
             "last4": _mask(values[field.name]) if field.secret else None, "value": None if field.secret else values[field.name]}
            for field in spec.credentials]


def _label(value: Any) -> str:
    if not isinstance(value, str) or not (1 <= len(value.strip()) <= 60) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        _abort("plugin_credentials_input_invalid")
    return value.strip()


def _keyring_label(spec: providers.ProviderSpec, label: str, field: providers.CredentialField) -> str:
    return f"Portelyra · {spec.label} · {label} · {field.label}"


def _record(spec: providers.ProviderSpec, label: str, fields: list[dict[str, Any]], location: str) -> dict[str, Any]:
    return {"plugin_kind": "price_provider", "plugin_id": spec.plugin_id, "plugin_label": spec.label, "label": label, "fields": fields,
            "hosts": sorted(spec.hosts), "manifest_sha256": spec.manifest_sha256, "location": location}


def _placement_text(spec: providers.ProviderSpec) -> str:
    parts = [f"{field.label} als Kopfzeile „{field.placement_key}“" if field.placement_kind == "header"
             else f"{field.label} als Parameter „{field.placement_key}“" for field in spec.credentials]
    return ", ".join(parts)


def _notes(spec: providers.ProviderSpec, action: str, moved: bool = False) -> list[str]:
    hosts = ", ".join(sorted(spec.hosts))
    notes = []
    if moved and action == "replace":
        notes.append("Dieser Datenraum liegt an einem anderen Ort als beim Eintragen (Umzug oder Kopie). Die neuen Werte gelten nur hier; "
                     "der Zugang am ursprünglichen Ort bleibt unberührt.")
    if moved and action == "delete":
        notes.append("Dieser Datenraum liegt an einem anderen Ort als beim Eintragen (Umzug oder Kopie). Gelöscht wird nur der Verweis hier; "
                     "der Wert im Schlüsselbund gehört zum Datenraum am ursprünglichen Ort und bleibt.")
    if action in ("create", "replace", "confirm_hosts"):
        notes.append(f"Portelyra sendet diesen Zugang nur an {hosts} ({_placement_text(spec)}), nie an andere Adressen. Mit dem Häkchen "
                     "bestätigen Sie diese Adressen; ändert ein Update sie, bleibt der Zugang gesperrt, bis Sie neu bestätigen.")
    if action in ("create", "replace"):
        notes.extend([
            "Der Zugang liegt im Schlüsselbund des Systems. Im Datenraum stehen nur Bezeichnung, die letzten vier Zeichen und die "
            "bestätigten Adressen – auch im Backup ist er deshalb nicht. Er gilt nur für diesen Datenraum an diesem Ort: Eine Kopie an "
            "anderem Ort kommt nicht an ihn heran. Nach einem Umzug oder auf einem neuen Rechner tragen Sie ihn neu ein.",
            "Der Schlüsselbund ist mit Ihrer Anmeldung entsperrt; Programme in Ihrer Sitzung können ihn lesen, wie Ihre übrigen privaten Dateien.",
            f"Kosten: {_COST_TEXT[spec.cost]}. Abruf, Kosten und die Einhaltung der Bedingungen des Anbieters verantworten Sie; Portelyra "
            f"ist kostenlos und ohne Gewähr. Bedingungen: {spec.terms_url}",
        ])
    if action == "delete" and not moved:
        notes.append("Portelyra entfernt den Zugang aus dem Schlüsselbund. Im Datenraum bleibt vermerkt, dass es ihn gab; Abrufe mit "
                     "diesem Plugin sind danach gesperrt, bis ein neuer Zugang eingetragen ist.")
    return notes


_COST_TEXT = {"free": "kostenlos", "free_quota": "kostenlos bis zu einem Kontingent, darüber kostenpflichtig", "paid": "kostenpflichtig"}


def _live(credentials: Mapping[str, Mapping[str, Any]], ref: Any) -> dict[str, Any]:
    if not isinstance(ref, str) or _REF.fullmatch(ref) is None:
        _abort("plugin_credentials_input_invalid")
    entry = credentials.get(ref)
    if entry is None or entry["deleted"]:
        _abort("plugin_credentials_not_found")
    return dict(entry)


def _state(space: Path, context: _Context, entry: Mapping[str, Any], keyring: str, check_values: bool = True) -> str:
    spec = providers.provider_spec_v1(entry["plugin_id"])
    if spec is None or not spec.credentials:
        return "plugin_unavailable"
    if entry["location"] != location_v1(space):
        return "other_location"
    if [field.name for field in spec.credentials] != [field["name"] for field in entry["fields"]]:
        return "fields_changed"
    if sorted(spec.hosts) != list(entry["hosts"]):
        return "hosts_unconfirmed"
    if keyring != "available":
        return "keyring_unavailable"
    if check_values and any(_keyring_lookup(space, context, entry["credential_ref"], field.name) is None for field in spec.credentials):
        return "missing"
    return "ready"


# ---------------------------------------------------------------------------------------------------------------------------
# Uebersicht, Vorschau, Bestaetigung
# ---------------------------------------------------------------------------------------------------------------------------

def overview_v1(space: str | Path, context_value: Any) -> dict[str, Any]:
    """Alle Zugaenge (maskiert) mit Zustand, dazu Plugins, die einen Zugang brauchen und keinen haben."""
    context = _context(context_value)
    space = _space(space, context)
    keyring = keyring_status_v1()
    credentials, choices, success = _read(space, context)
    rows = []
    for entry in credentials.values():
        if entry["deleted"]:
            continue
        state = _state(space, context, entry, keyring["status"])
        used_by = [consumer for (kind, consumer), ref in choices.items() if ref == entry["credential_ref"] and kind == entry["plugin_kind"]]
        rows.append({
            "credential_ref": entry["credential_ref"], "plugin_kind": entry["plugin_kind"], "plugin_id": entry["plugin_id"],
            "plugin_label": entry["plugin_label"], "label": entry["label"],
            "fields": [{key: field[key] for key in ("name", "label", "secret", "last4", "value")} for field in entry["fields"]],
            "hosts": list(entry["hosts"]), "state": state, "state_text": STATE_TEXT[state], "created_at_utc": entry["created_at_utc"],
            "updated_at_utc": entry["updated_at_utc"], "last_success_at_utc": success.get(entry["credential_ref"]), "chosen_for": sorted(used_by),
        })
    live_plugins = {row["plugin_id"] for row in rows}
    plugins = [{"plugin_kind": "price_provider", "plugin_id": spec.plugin_id, "label": spec.label, "hosts": sorted(spec.hosts),
                "fields": [field.public() for field in spec.credentials], "cost": spec.cost, "terms_url": spec.terms_url,
                "has_credential": spec.plugin_id in live_plugins}
               for spec in providers.provider_specs_v1() if spec.credentials]
    return {"contract_version": "plugin_credentials_overview_v1", "keyring": keyring, "credentials": rows, "plugins": plugins,
            "plugins_without_credential": [plugin for plugin in plugins if not plugin["has_credential"]]}


def _preview(space: Path, context: _Context, body: dict[str, Any], spec: providers.ProviderSpec, created_at_utc: Any) -> dict[str, Any]:
    body.update(contract_version="plugin_credential_preview_v1", plugin_kind="price_provider", plugin_id=spec.plugin_id,
                plugin_version=spec.plugin_version, plugin_label=spec.label, manifest_sha256=spec.manifest_sha256, hosts=sorted(spec.hosts),
                state_fingerprint=_state_fingerprint(space, context), created_at_utc=_stamp(created_at_utc or _now()))
    body["notes"] = _notes(spec, body["action"], bool(body.get("moved")))
    body["preview_fingerprint"] = _fingerprint(body)
    return body


def _checked_preview(space: Path, context: _Context, preview: Any, action: str, confirmed: Any) -> providers.ProviderSpec:
    if confirmed is not True:
        _abort("plugin_credentials_confirmation_required")
    if not isinstance(preview, Mapping) or preview.get("contract_version") != "plugin_credential_preview_v1" or preview.get("action") != action:
        _abort("plugin_credentials_input_invalid")
    body = {key: value for key, value in preview.items() if key != "preview_fingerprint"}
    if preview.get("preview_fingerprint") != _fingerprint(body) or preview.get("state_fingerprint") != _state_fingerprint(space, context):
        _abort("plugin_credentials_preview_stale")
    spec = providers.provider_spec_v1(str(preview.get("plugin_id")))
    if spec is None or spec.manifest_sha256 != preview.get("manifest_sha256") or sorted(spec.hosts) != preview.get("hosts"):
        _abort("plugin_credentials_preview_stale")
    return spec


def preview_create_v1(space: str | Path, context_value: Any, plugin_kind: Any, plugin_id: Any, label: Any, values: Any,
                      created_at_utc: str | None = None) -> dict[str, Any]:
    """Vorschau eines neuen Zugangs: Plugin, Adressen, wo der Wert in der Anfrage steht, maskierte Felder. Enthaelt nichts Geheimes; die
    Bestaetigung bindet die Werte ueber ihre Maske und Laenge."""
    context = _context(context_value)
    space = _space(space, context)
    spec = _plugin(plugin_kind, plugin_id)
    clean = _values(spec, values)
    body = {"action": "create", "credential_ref": None, "label": _label(label), "fields": _public_fields(spec, clean),
            "value_lengths": {name: len(value) for name, value in clean.items()}, "keyring": keyring_status_v1()["status"]}
    return _preview(space, context, body, spec, created_at_utc)


def apply_create_v1(space: str | Path, context_value: Any, preview: Any, values: Any, confirmed: Any,
                    recorded_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    space = _space(space, context)
    spec = _checked_preview(space, context, preview, "create", confirmed)
    clean = _values(spec, values)
    if _public_fields(spec, clean) != preview["fields"] or {name: len(value) for name, value in clean.items()} != preview["value_lengths"]:
        _abort("plugin_credentials_preview_stale")
    _require_keyring()
    stamp = _stamp(recorded_at_utc or _now())
    ref = "crd_" + _random.token_hex(16)
    stored: list[str] = []
    try:
        for field in spec.credentials:
            _keyring_store(space, context, ref, field.name, _keyring_label(spec, preview["label"], field), clean[field.name])
            stored.append(field.name)
        _insert(space, context, ref, "created", _record(spec, preview["label"], preview["fields"], location_v1(space)), stamp)
    except PluginCredentialsV1Error:
        for name in stored:
            try:
                _keyring_clear(space, context, ref, name)
            except PluginCredentialsV1Error:
                pass
        raise
    return {"contract_version": "plugin_credential_result_v1", "status": "recorded", "action": "create", "credential_ref": ref,
            "recorded_at_utc": stamp}


def preview_replace_v1(space: str | Path, context_value: Any, credential_ref: Any, values: Any, created_at_utc: str | None = None) -> dict[str, Any]:
    """Vorschau: neue Werte fuer einen Zugang; bestaetigt zugleich die heutigen Adressen des Plugins."""
    context = _context(context_value)
    space = _space(space, context)
    entry = _live(_read(space, context)[0], credential_ref)
    spec = _plugin(entry["plugin_kind"], entry["plugin_id"])
    clean = _values(spec, values)
    body = {"action": "replace", "credential_ref": entry["credential_ref"], "label": entry["label"], "fields": _public_fields(spec, clean),
            "value_lengths": {name: len(value) for name, value in clean.items()}, "hosts_before": list(entry["hosts"]),
            "keyring": keyring_status_v1()["status"], "moved": entry["location"] != location_v1(space)}
    return _preview(space, context, body, spec, created_at_utc)


def apply_replace_v1(space: str | Path, context_value: Any, preview: Any, values: Any, confirmed: Any,
                     recorded_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    space = _space(space, context)
    spec = _checked_preview(space, context, preview, "replace", confirmed)
    entry = _live(_read(space, context)[0], preview.get("credential_ref"))
    clean = _values(spec, values)
    if _public_fields(spec, clean) != preview["fields"] or {name: len(value) for name, value in clean.items()} != preview["value_lengths"]:
        _abort("plugin_credentials_preview_stale")
    _require_keyring()
    stamp = _stamp(recorded_at_utc or _now())
    # Gleiche Merkmale ersetzen den Eintrag im Schluesselbund; Felder, die das Plugin nicht mehr kennt, werden entfernt.
    for field in spec.credentials:
        _keyring_store(space, context, entry["credential_ref"], field.name, _keyring_label(spec, entry["label"], field), clean[field.name])
    if entry["location"] == location_v1(space):
        for old in entry["fields"]:
            if old["name"] not in clean:
                _keyring_clear(space, context, entry["credential_ref"], old["name"])
    _insert(space, context, entry["credential_ref"], "replaced", _record(spec, entry["label"], preview["fields"], location_v1(space)), stamp)
    return {"contract_version": "plugin_credential_result_v1", "status": "recorded", "action": "replace", "credential_ref": entry["credential_ref"],
            "recorded_at_utc": stamp}


def preview_confirm_hosts_v1(space: str | Path, context_value: Any, credential_ref: Any, created_at_utc: str | None = None) -> dict[str, Any]:
    """Vorschau: die heutigen Adressen des Plugins fuer einen Zugang bestaetigen (nach einem Update mit neuen Hosts)."""
    context = _context(context_value)
    space = _space(space, context)
    entry = _live(_read(space, context)[0], credential_ref)
    spec = _plugin(entry["plugin_kind"], entry["plugin_id"])
    if [field.name for field in spec.credentials] != [field["name"] for field in entry["fields"]]:
        _abort("plugin_credentials_fields_changed")
    body = {"action": "confirm_hosts", "credential_ref": entry["credential_ref"], "label": entry["label"], "fields": entry["fields"],
            "hosts_before": list(entry["hosts"]), "changed": sorted(spec.hosts) != list(entry["hosts"])}
    return _preview(space, context, body, spec, created_at_utc)


def apply_confirm_hosts_v1(space: str | Path, context_value: Any, preview: Any, confirmed: Any, recorded_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    space = _space(space, context)
    spec = _checked_preview(space, context, preview, "confirm_hosts", confirmed)
    entry = _live(_read(space, context)[0], preview.get("credential_ref"))
    if not preview["changed"]:
        return {"contract_version": "plugin_credential_result_v1", "status": "unchanged", "action": "confirm_hosts", "credential_ref": entry["credential_ref"]}
    stamp = _stamp(recorded_at_utc or _now())
    _insert(space, context, entry["credential_ref"], "hosts_confirmed", _record(spec, entry["label"], entry["fields"], entry["location"]), stamp)
    return {"contract_version": "plugin_credential_result_v1", "status": "recorded", "action": "confirm_hosts",
            "credential_ref": entry["credential_ref"], "recorded_at_utc": stamp}


def preview_delete_v1(space: str | Path, context_value: Any, credential_ref: Any, created_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    space = _space(space, context)
    entry = _live(_read(space, context)[0], credential_ref)
    spec = providers.provider_spec_v1(entry["plugin_id"])
    if spec is None:
        _abort("plugin_credentials_plugin_unavailable")
    body = {"action": "delete", "credential_ref": entry["credential_ref"], "label": entry["label"], "fields": entry["fields"],
            "keyring": keyring_status_v1()["status"], "moved": entry["location"] != location_v1(space)}
    return _preview(space, context, body, spec, created_at_utc)


def apply_delete_v1(space: str | Path, context_value: Any, preview: Any, confirmed: Any, recorded_at_utc: str | None = None) -> dict[str, Any]:
    """Entfernt die Werte aus dem Schluesselbund und vermerkt den Zugang als geloescht. Ist der Schluesselbund nicht erreichbar (anderer
    Rechner), wird nur der Verweis geloescht; ``keyring_cleared`` sagt es."""
    context = _context(context_value)
    space = _space(space, context)
    spec = _checked_preview(space, context, preview, "delete", confirmed)
    entry = _live(_read(space, context)[0], preview.get("credential_ref"))
    # An einer Kopie (anderer Ort) bleibt der Schluesselbund unberuehrt: Der Wert gehoert dem Datenraum am urspruenglichen Ort.
    here = entry["location"] == location_v1(space)
    cleared = here and keyring_status_v1()["status"] == "available"
    if cleared:
        for field in entry["fields"]:
            _keyring_clear(space, context, entry["credential_ref"], field["name"])
    stamp = _stamp(recorded_at_utc or _now())
    record = dict(_record(spec, entry["label"], entry["fields"], entry["location"]), hosts=list(entry["hosts"]))
    _insert(space, context, entry["credential_ref"], "deleted", record, stamp)
    return {"contract_version": "plugin_credential_result_v1", "status": "recorded", "action": "delete", "credential_ref": entry["credential_ref"],
            "keyring_cleared": cleared, "recorded_at_utc": stamp}


def preview_choice_v1(space: str | Path, context_value: Any, provider_id: Any, credential_ref: Any, created_at_utc: str | None = None) -> dict[str, Any]:
    """Vorschau: welchen Zugang ein Kursanbieter in diesem Datenraum nutzt (bei mehreren Zugaengen zu einem Plugin)."""
    context = _context(context_value)
    space = _space(space, context)
    credentials, choices, _success = _read(space, context)
    entry = _live(credentials, credential_ref)
    spec = _plugin("price_provider", provider_id)
    if entry["plugin_id"] != spec.plugin_id:
        _abort("plugin_credentials_input_invalid")
    body = {"action": "choose", "credential_ref": entry["credential_ref"], "label": entry["label"], "fields": entry["fields"],
            "consumer_id": spec.provider_id, "chosen_before": choices.get(("price_provider", spec.provider_id))}
    return _preview(space, context, body, spec, created_at_utc)


def apply_choice_v1(space: str | Path, context_value: Any, preview: Any, confirmed: Any, recorded_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    space = _space(space, context)
    spec = _checked_preview(space, context, preview, "choose", confirmed)
    entry = _live(_read(space, context)[0], preview.get("credential_ref"))
    stamp = _stamp(recorded_at_utc or _now())
    connection = _connect(space, context, True)
    try:
        with connection:
            connection.execute("INSERT INTO credential_choice(consumer_kind,consumer_id,credential_ref,actor_id,recorded_at_utc) VALUES(?,?,?,?,?)",
                               ("price_provider", spec.provider_id, entry["credential_ref"], context.actor_id, stamp))
    except sqlite3.Error:
        _abort("plugin_credentials_store_invalid")
    finally:
        connection.close()
    return {"contract_version": "plugin_credential_result_v1", "status": "recorded", "action": "choose", "credential_ref": entry["credential_ref"],
            "recorded_at_utc": stamp}


# ---------------------------------------------------------------------------------------------------------------------------
# Abruf mit Zugang (nur im Kern)
# ---------------------------------------------------------------------------------------------------------------------------

def _chosen(space: Path, context: _Context, spec: providers.ProviderSpec) -> dict[str, Any]:
    credentials, choices, _success = _read(space, context)
    live = [entry for entry in credentials.values() if not entry["deleted"] and entry["plugin_id"] == spec.plugin_id]
    chosen = choices.get(("price_provider", spec.provider_id))
    picked = [entry for entry in live if entry["credential_ref"] == chosen] or (live if len(live) == 1 else [])
    if not live:
        _abort("plugin_credentials_missing")
    if not picked:
        _abort("plugin_credentials_choice_required")
    return picked[0]


def _resolved_values(space: Path, context: _Context, entry: Mapping[str, Any], spec: providers.ProviderSpec) -> dict[str, str]:
    state = _state(space, context, entry, keyring_status_v1()["status"], check_values=False)
    if state != "ready":
        _abort({"hosts_unconfirmed": "plugin_credentials_hosts_unconfirmed", "fields_changed": "plugin_credentials_fields_changed",
                "keyring_unavailable": "plugin_credentials_keyring_unavailable", "other_location": "plugin_credentials_other_location",
                }.get(state, "plugin_credentials_plugin_unavailable"))
    values: dict[str, str] = {}
    for field in spec.credentials:
        value = _keyring_lookup(space, context, entry["credential_ref"], field.name)
        if value is None:
            _abort("plugin_credentials_missing")
        values[field.name] = value
    return values


def _placed(spec: providers.ProviderSpec, values: Mapping[str, str], target: str, headers: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    """Setzt die Werte an die Stelle laut Manifest: Kopfzeile oder Parameter, nie im Pfad. Nennt die Anfrage dieselbe Stelle schon, wird
    nichts abgerufen."""
    path, _mark, query = target.partition("?")
    present = {key.lower() for key, _value in parse_qsl(query, keep_blank_values=True)}
    placed_headers = dict(headers)
    lowered = {key.lower() for key in placed_headers}
    additions: list[str] = []
    for field in spec.credentials:
        value = values[field.name]
        if field.placement_kind == "header":
            if field.placement_key.lower() in lowered:
                _abort("plugin_credentials_placement_conflict")
            placed_headers[field.placement_key] = field.placement_prefix + value
            lowered.add(field.placement_key.lower())
        else:
            if field.placement_key.lower() in present:
                _abort("plugin_credentials_placement_conflict")
            additions.append(f"{quote(field.placement_key, safe='')}={quote(value, safe='')}")
            present.add(field.placement_key.lower())
    if additions:
        target = path + "?" + "&".join(([query] if query else []) + additions)
    return target, placed_headers


def _secret_forms(spec: providers.ProviderSpec, values: Mapping[str, str]) -> list[bytes]:
    forms: set[bytes] = set()
    for field in spec.credentials:
        if field.secret:
            value = values[field.name]
            forms.update({value.encode("utf-8"), quote(value, safe="").encode("ascii"), quote_plus(value).encode("ascii")})
    return sorted(forms, key=len, reverse=True)


def _redacted(response: Mapping[str, Any], forms: list[bytes]) -> dict[str, Any]:
    """Entfernt den Wert aus Antwort und Kopfzeilen, bevor das Plugin sie liest (manche Dienste spiegeln den Schluessel in Fehlermeldungen)."""
    body = response["body"]
    headers = dict(response.get("headers") or {})
    for form in forms:
        body = body.replace(form, REDACTED)
        text = form.decode("utf-8", "replace")
        headers = {key: value.replace(text, REDACTED.decode("ascii")) for key, value in headers.items()}
    return dict(response, body=body, headers=headers)


def _record_success(space: Path, context: _Context, credential_ref: str, stamp: str) -> None:
    connection = _connect(space, context, True)
    try:
        with connection:
            connection.execute("INSERT INTO credential_success VALUES(?,?) ON CONFLICT(credential_ref) DO UPDATE SET succeeded_at_utc=excluded.succeeded_at_utc",
                               (credential_ref, stamp))
    except sqlite3.Error:
        _abort("plugin_credentials_store_invalid")
    finally:
        connection.close()


def _fetch(space: Path, context: _Context, spec: providers.ProviderSpec, entry: Mapping[str, Any], request: Mapping[str, str],
           headers: Mapping[str, str], origin: str) -> tuple[dict[str, Any], list[bytes]]:
    values = _resolved_values(space, context, entry, spec)
    host = request.get("host")
    if host not in entry["hosts"] or host not in spec.hosts:
        _abort("plugin_credentials_hosts_unconfirmed")
    target, placed = _placed(spec, values, str(request.get("target")), headers)
    forms = _secret_forms(spec, values)
    response = _redacted(_costed(space, context, spec, origin, host, target, placed), forms)
    if 200 <= int(response["status"]) < 300:
        _record_success(space, context, entry["credential_ref"], _now())
    return response, forms


def _costed(space: Path | None, context: _Context | None, spec: providers.ProviderSpec, origin: str, host: str, target: str,
            headers: Mapping[str, str]) -> dict[str, Any]:
    """Ein Abruf; bei kostenpflichtigen Anbietern vorher zugelassen (Zeitlauf, Obergrenze) und danach gezaehlt (429 beendet mit Grund)."""
    if spec.cost != "free":
        costs.admit_v1(space, context, spec.provider_id, origin)
    response = providers.https_get_v1(host, target, headers, providers.FETCH_TIMEOUT_SECONDS, providers.FETCH_BYTE_LIMIT)
    if spec.cost != "free":
        costs.record_v1(space, context, spec.provider_id, int(response["status"]))
    return response


def provider_get_v1(space: str | Path, context_value: Any, provider_id: str, request: Mapping[str, str], headers: Mapping[str, str],
                    *, origin: str) -> dict[str, Any]:
    """Der Abrufweg fuer Kursanbieter mit und ohne Zugang. Ein kostenloser Anbieter ohne Zugang reicht an ``https_get_v1`` weiter. Mit
    Zugang nimmt er den gewaehlten (oder einzigen) Zugang des Datenraums, prueft die bestaetigten Hosts, setzt den Wert ein und entfernt
    ihn aus der Antwort. Kostenpflichtige Anbieter laufen ueber Zeitlauf-Freigabe und Obergrenze. ``origin`` (interactive, scheduled) ist
    Pflicht und hat keine Vorgabe (rc.391): Ein Schritt, der sie vergisst, bricht ab, statt still als "von Hand" abzurufen. Laeuft der
    Prozess im Zeitlauf (Merkmal ``PORTELYRA_RUN_ORIGIN=timer``), gilt ohnehin "scheduled"."""
    spec = providers.provider_spec_v1(provider_id)
    if spec is None:
        raise providers.PriceProviderBlocked("price_provider_unavailable")
    if origin not in costs.ORIGINS:
        _abort("plugin_credentials_input_invalid")
    if not spec.credentials and spec.cost == "free":
        return providers.https_get_v1(request["host"], request["target"], headers, providers.FETCH_TIMEOUT_SECONDS, providers.FETCH_BYTE_LIMIT)
    context = _context(context_value)
    space = _space(space, context)
    if not spec.credentials:
        return _costed(space, context, spec, origin, request["host"], request["target"], headers)
    response, _forms = _fetch(space, context, spec, _chosen(space, context, spec), request, headers, origin)
    return response


def checked_outcome_v1(provider_id: str, operation: str, params: Mapping[str, Any], response: Mapping[str, Any], forms: list[bytes]) -> dict[str, Any]:
    """Auswertung durch das Plugin; enthaelt sie trotzdem einen Wert des Zugangs, wird sie verworfen."""
    outcome = providers.parse_response_v1(provider_id, operation, params, {key: response[key] for key in ("status", "content_type", "body")})
    text = json.dumps(outcome, ensure_ascii=False).encode("utf-8")
    if any(form in text for form in forms):
        _abort("plugin_credentials_secret_leak")
    return outcome


def check_v1(space: str | Path, context_value: Any, credential_ref: Any, checked_at_utc: str | None = None) -> dict[str, Any]:
    """„Zugang prüfen“: ein einzelner Testabruf mit genau diesem Zugang, ausgewertet vom Plugin (angenommen, abgewiesen, nicht lesbar)."""
    context = _context(context_value)
    space = _space(space, context)
    entry = _live(_read(space, context)[0], credential_ref)
    spec = _plugin(entry["plugin_kind"], entry["plugin_id"])
    if "credential_check" not in spec.operations:
        _abort("plugin_credentials_check_unsupported")
    request = providers.build_request_v1(spec.provider_id, "credential_check", {})
    response, forms = _fetch(space, context, spec, entry, request, {"User-Agent": "Portelyra", "Accept": "application/json"}, "interactive")
    content_type = (response.get("headers") or {}).get("content-type")
    outcome = checked_outcome_v1(spec.provider_id, "credential_check", {}, dict(response, content_type=content_type), forms)
    return {"contract_version": "plugin_credential_check_v1", "credential_ref": entry["credential_ref"], "plugin_id": spec.plugin_id,
            "outcome": outcome["outcome"], "http_status": int(response["status"]), "checked_at_utc": _stamp(checked_at_utc or _now())}


__all__ = [
    "AREA", "FAILURE_CODES", "KEYRING_TOOL_ENV", "PluginCredentialsV1Error", "STORE", "apply_choice_v1", "apply_confirm_hosts_v1",
    "apply_create_v1", "apply_delete_v1", "apply_replace_v1", "check_v1", "checked_outcome_v1", "keyring_status_v1", "overview_v1",
    "location_v1", "preview_choice_v1", "preview_confirm_hosts_v1", "preview_create_v1", "preview_delete_v1", "preview_replace_v1", "provider_get_v1",
    "store_present_v1",
]
