"""Verwaltung der Leser-Plugins je Portfolio (rc.381, #486): Aktivieren und fremde Plugins aus einer ZIP-Datei installieren.

Festlegungen vom 07. und 09.11.2026:
- Aktiviert wird je Plugin (ein Institut mit allen seinen Lesern) und je Portfolio. Neue Portfolios starten ohne aktive Leser; in
  Portfolios, die vor rc.380 angelegt wurden, sind alle mitgelieferten Plugins aktiv (einmaliger, sichtbarer Eintrag "Bestand bis rc.380").
- Ein inaktives Plugin wird in den Import-Karten ausgeblendet und vom Kern gesperrt (statement_reader_checks_v1).
- Fremde Plugins kommen als ZIP-Datei: sicher entpacken (keine Verknuepfungen, keine Pfade nach aussen, Groessengrenzen), Manifest und
  Schnittstellenstufe pruefen, Selbsttest samt Erzeuger mit echtem Datum - installiert wird nur bei bestandenem Test. Abgelegt im
  Datenraum unter statement-reader-plugins-v1 (mit gesichert); jede Fassung in einem eigenen, unveraenderten Ordner.
- Entfernen geht nur bei installierten Plugins; die Dateien bleiben fuer die Nachvollziehbarkeit, das Plugin wird nicht mehr geladen.
- Jeder Schreibschritt: Vorschau -> ausdrueckliche Bestaetigung, gebunden an genau diese Vorschau -> nur anhaengender Eintrag.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tempfile
from typing import Any, Mapping, Sequence
import zipfile

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference import asset_activity_reference_v1 as references
from migrations.reference import statement_reader_plugins_v1 as reader_plugins

AREA = "statement-reader-plugins-v1"
STORE = "reader-admin.sqlite"
POINTER = "installed.json"
SCHEMA_VERSION = 1
# Nur Portfolios, die vor rc.380 angelegt wurden, bekommen den Bestandseintrag (gleiche Grenze wie der Pruefstand).
ACTIVATION_PORTFOLIOS_CREATED_BEFORE = "2026-11-10T00:00:00Z"


def _activation_cutoff() -> str:
    """Stichtag des Bestandseintrags; Tests verschieben ihn wie beim Pruefstand (PORTELYRA_PLUGIN_BASELINE_CUTOFF_INTERNAL)."""
    from migrations.reference.statement_reader_checks_v1 import BASELINE_CUTOFF_ENV  # noqa: PLC0415
    value = os.environ.get(BASELINE_CUTOFF_ENV)
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        return value
    return ACTIVATION_PORTFOLIOS_CREATED_BEFORE
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 300
# Selbsttest vor der Installation: wie der Knopf im Reiter "Leser", fuer ein einzelnes Plugin.
INSTALL_SELFTEST = {"mutations_per_fixture": 200, "generated_per_reader": 100, "mutations_per_generated": 10}
FAILURE_CODES = (
    "statement_reader_admin_input_invalid", "statement_reader_admin_store_invalid", "statement_reader_admin_preview_stale",
    "statement_reader_admin_confirmation_required", "statement_reader_install_zip_invalid", "statement_reader_install_zip_unsafe",
    "statement_reader_install_too_large", "statement_reader_install_manifest_invalid", "statement_reader_install_api_unsupported",
    "statement_reader_install_plugin_id_taken", "statement_reader_install_reader_id_taken", "statement_reader_install_generator_missing",
    "statement_reader_install_selftest_failed", "statement_reader_remove_shipped", "statement_reader_remove_unknown",
    "statement_reader_incompatible", "statement_reader_install_domain_unsupported",
    # Pakete und Updates mitgelieferter Plugins (#486 Schritt 3)
    "statement_reader_install_package_invalid", "statement_reader_install_package_file_mismatch", "statement_reader_install_update_unsigned",
    "statement_reader_install_update_not_newer", "statement_reader_install_package_mismatch", "statement_reader_revert_unavailable",
    "plugin_signature_untrusted", "plugin_signature_invalid", "plugin_signature_tool_missing",
)
# Fremde Plugins lesen vorerst Cash, Wertpapiere, Devisen und Krypto. Rewards und Ertraegnisaufstellung haengen im Kern noch an festen Listen.
INSTALLABLE_DOMAINS = frozenset(("cash", "securities", "fx", "crypto"))
SCHEMA = (
    "CREATE TABLE reader_admin_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE plugin_activation_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "portfolio_id TEXT NOT NULL CHECK(length(portfolio_id) BETWEEN 1 AND 80), plugin_id TEXT NOT NULL CHECK(length(plugin_id) BETWEEN 2 AND 41),"
    "active INTEGER NOT NULL CHECK(active IN (0, 1)), origin TEXT NOT NULL CHECK(origin IN ('existing_portfolio','owner')),"
    "actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX plugin_activation_key ON plugin_activation_entry(portfolio_id, plugin_id, entry_id)",
    "CREATE TRIGGER plugin_activation_no_update BEFORE UPDATE ON plugin_activation_entry BEGIN SELECT RAISE(ABORT, 'plugin_activation_immutable'); END",
    "CREATE TRIGGER plugin_activation_no_delete BEFORE DELETE ON plugin_activation_entry BEGIN SELECT RAISE(ABORT, 'plugin_activation_immutable'); END",
    "CREATE TABLE plugin_installation_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "plugin_id TEXT NOT NULL CHECK(length(plugin_id) BETWEEN 2 AND 41), plugin_version TEXT NOT NULL CHECK(length(plugin_version) BETWEEN 1 AND 40),"
    "plugin_code_sha256 TEXT NOT NULL CHECK(length(plugin_code_sha256) = 64), zip_sha256 TEXT NOT NULL CHECK(length(zip_sha256) = 64),"
    "relative_dir TEXT NOT NULL CHECK(length(relative_dir) BETWEEN 1 AND 300), action TEXT NOT NULL CHECK(action IN ('installed','removed')),"
    "selftest_json TEXT NOT NULL CHECK(length(selftest_json) <= 200000), actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL,"
    "entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TRIGGER plugin_installation_no_update BEFORE UPDATE ON plugin_installation_entry BEGIN SELECT RAISE(ABORT, 'plugin_installation_immutable'); END",
    "CREATE TRIGGER plugin_installation_no_delete BEFORE DELETE ON plugin_installation_entry BEGIN SELECT RAISE(ABORT, 'plugin_installation_immutable'); END",
    # Kompatibilitaet nach Updates (Festlegung 09.11.2026): je installiertem Plugin der Selbsttest fuer genau diesen Plugin-Code, diese
    # Hilfsbibliothek (SDK, Host) und diese Produktversion.
    "CREATE TABLE plugin_compatibility_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "plugin_id TEXT NOT NULL CHECK(length(plugin_id) BETWEEN 2 AND 41), plugin_code_sha256 TEXT NOT NULL CHECK(length(plugin_code_sha256) = 64),"
    "shared_code_sha256 TEXT NOT NULL CHECK(length(shared_code_sha256) = 64), core_version TEXT NOT NULL CHECK(length(core_version) BETWEEN 1 AND 40),"
    "passed INTEGER NOT NULL CHECK(passed IN (0, 1)), selftest_json TEXT NOT NULL CHECK(length(selftest_json) <= 200000),"
    "recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TRIGGER plugin_compatibility_no_update BEFORE UPDATE ON plugin_compatibility_entry BEGIN SELECT RAISE(ABORT, 'plugin_compatibility_immutable'); END",
    "CREATE TRIGGER plugin_compatibility_no_delete BEFORE DELETE ON plugin_compatibility_entry BEGIN SELECT RAISE(ABORT, 'plugin_compatibility_immutable'); END",
)


class StatementReaderAdminV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "statement_reader_admin_input_invalid"


def _abort(code: str) -> None:
    raise StatementReaderAdminV1Error(code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _context(value: Any):
    try:
        return references.activity_reference_scope_v1(value)
    except references.AssetActivityReferenceV1Error:
        _abort("statement_reader_admin_input_invalid")


def _stamp(value: Any) -> str:
    if not isinstance(value, str) or references.UTC.fullmatch(value) is None:
        _abort("statement_reader_admin_input_invalid")
    return value


# ---------------------------------------------------------------- Speicher
def store_present_v1(space: str | Path) -> bool:
    return (Path(space) / AREA / STORE).exists()


def _connect(space: str | Path, context: Any, create: bool) -> sqlite3.Connection | None:
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("statement_reader_admin_store_invalid")
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
                connection.execute("INSERT INTO reader_admin_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("statement_reader_admin_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM reader_admin_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("statement_reader_admin_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("statement_reader_admin_store_invalid")
    return connection


def _portfolios(space: str | Path) -> dict[str, dict[str, str]]:
    try:
        connection = sqlite3.connect(f"file:{Path(space) / 'canonical.sqlite'}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT portfolio_id, display_name, created_at_utc FROM portfolio ORDER BY portfolio_id").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("statement_reader_admin_store_invalid")
        return {}
    return {str(row[0]): {"label": str(row[1] or row[0]), "created_at_utc": str(row[2] or "")} for row in rows}


def _plugins() -> dict[str, dict[str, Any]]:
    """Geladene Plugins (mitgeliefert und installiert) mit Institut, Version und Herkunft."""
    plugins: dict[str, dict[str, Any]] = {}
    for spec in reader_plugins.reader_specs_v1():
        item = plugins.setdefault(spec.plugin_id, {"plugin_id": spec.plugin_id, "institution": spec.institution, "label": spec.institution or spec.plugin_id,
                                                   "origin": spec.origin, "plugin_version": spec.plugin_version, "publisher": spec.publisher, "readers": [],
                                                   "replaces_shipped": spec.replaces_shipped})
        item["readers"].append(spec.reader_id)
    return dict(sorted(plugins.items(), key=lambda pair: (pair[1]["label"].lower(), pair[0])))


def _shipped_plugin_ids() -> set[str]:
    return {plugin_id for plugin_id, item in _plugins().items() if item["origin"] == "shipped"}


# ---------------------------------------------------------------- Aktivierung je Portfolio
def _current_activation(connection: sqlite3.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    rows = connection.execute("SELECT portfolio_id,plugin_id,active,origin,recorded_at_utc FROM plugin_activation_entry ORDER BY entry_id").fetchall()
    return {(row["portfolio_id"], row["plugin_id"]): {"active": bool(row["active"]), "origin": row["origin"], "recorded_at_utc": row["recorded_at_utc"]}
            for row in rows}


def ensure_activation_baseline_v1(space: str | Path, context_value: Any, recorded_at_utc: str | None = None) -> str:
    """Erster Kontakt mit rc.381: Speicher anlegen; jedes vor rc.380 angelegte Portfolio bekommt alle mitgelieferten Plugins aktiv
    ("Bestand bis rc.380"). Danach ohne Wirkung. Liefert "present", "baseline" oder "empty"."""
    context = _context(context_value)
    if store_present_v1(space):
        return "present"
    eligible = [portfolio for portfolio, item in _portfolios(space).items() if item["created_at_utc"] and item["created_at_utc"] < _activation_cutoff()]
    shipped = sorted(_shipped_plugin_ids()) if eligible else []
    connection = _connect(space, context, True)
    stamp = recorded_at_utc or _now()
    try:
        with connection:
            for portfolio in eligible:
                for plugin_id in shipped:
                    body = {"portfolio_id": portfolio, "plugin_id": plugin_id, "active": 1, "origin": "existing_portfolio", "actor_id": context.actor_id,
                            "recorded_at_utc": stamp}
                    connection.execute("INSERT INTO plugin_activation_entry(portfolio_id,plugin_id,active,origin,actor_id,recorded_at_utc,entry_fingerprint)"
                                       " VALUES(?,?,?,?,?,?,?)", (portfolio, plugin_id, 1, "existing_portfolio", context.actor_id, stamp, _fingerprint(body)))
    except sqlite3.Error:
        _abort("statement_reader_admin_store_invalid")
    finally:
        connection.close()
    return "baseline" if eligible and shipped else "empty"


def active_plugins_v1(space: str | Path, context_value: Any) -> dict[str, set[str]]:
    """Je Portfolio die aktiven Plugins (nur geladene). Legt beim ersten Kontakt den Bestandseintrag an."""
    context = _context(context_value)
    ensure_activation_baseline_v1(space, context)
    connection = _connect(space, context, False)
    try:
        current = _current_activation(connection) if connection is not None else {}
    except sqlite3.Error:
        _abort("statement_reader_admin_store_invalid")
    finally:
        if connection is not None:
            connection.close()
    loaded = set(_plugins())
    result: dict[str, set[str]] = {portfolio: set() for portfolio in _portfolios(space)}
    for (portfolio, plugin_id), state in current.items():
        if state["active"] and plugin_id in loaded and portfolio in result:
            result[portfolio].add(plugin_id)
    return result


def offered_readers_v1(space: str | Path, context_value: Any) -> dict[str, Any]:
    """Was die Import-Karten anbieten (ausblenden, Festlegung 09.11.2026): Plugins, die in mindestens einem Portfolio aktiv sind, mit ihren
    Lesern. Gesperrt wird je Portfolio beim Buchen. Je Leser auch Name, Herkunft (mitgeliefert oder installiert), Institut und Pruefstand
    des Formats: Daran haengt die Data-App installierte Leser an die Auswahl und zeigt, bis wann ein Format geprueft ist (#486)."""
    active = active_plugins_v1(space, context_value)
    offered = sorted(set().union(*active.values())) if active else []
    # Dokument und Grenzen (#550): aus dem Manifest, eine Quelle fuer die Hinweise der Import-Karten. Die Pruefangabe tested_formats
    # (Spaltennamen des Exports) zeigt nur der Reiter „Leser“.
    readers = [{"reader_id": spec.reader_id, "domain": spec.domain, "plugin_id": spec.plugin_id, "label": spec.label, "origin": spec.origin,
                "institution": spec.institution, "format_checked": dict(spec.format_checked) if spec.format_checked else None,
                "subaccount_fallback": spec.subaccount_fallback, "document_kind": spec.document_kind, "known_limits": list(spec.known_limits)}
               for spec in reader_plugins.reader_specs_v1() if spec.plugin_id in offered]
    return {"contract_version": "statement_reader_offered_v1", "plugin_ids": offered, "readers": readers}


def activation_v1(space: str | Path, context_value: Any) -> dict[str, Any]:
    context = _context(context_value)
    baseline = ensure_activation_baseline_v1(space, context)
    connection = _connect(space, context, False)
    try:
        current = _current_activation(connection) if connection is not None else {}
    except sqlite3.Error:
        _abort("statement_reader_admin_store_invalid")
    finally:
        if connection is not None:
            connection.close()
    portfolios = _portfolios(space)
    plugins = []
    for plugin_id, item in _plugins().items():
        states = []
        for portfolio in portfolios:
            state = current.get((portfolio, plugin_id))
            states.append({"portfolio_id": portfolio, "active": bool(state and state["active"]), "origin": state["origin"] if state else None,
                           "recorded_at_utc": state["recorded_at_utc"] if state else None})
        plugins.append({key: item[key] for key in ("plugin_id", "institution", "label", "origin", "plugin_version")} | {"states": states})
    return {"contract_version": "statement_reader_activation_v1", "baseline": baseline,
            "portfolios": [{"portfolio_id": key, "label": value["label"]} for key, value in portfolios.items()], "plugins": plugins}


def _normalized_changes(space: str | Path, changes: Any) -> list[dict[str, Any]]:
    portfolios, plugins = _portfolios(space), _plugins()
    if not isinstance(changes, list) or not 1 <= len(changes) <= 2000:
        _abort("statement_reader_admin_input_invalid")
    seen, result = set(), []
    for change in changes:
        if not (isinstance(change, dict) and set(change) == {"portfolio_id", "plugin_id", "active"} and isinstance(change["active"], bool)
                and change.get("portfolio_id") in portfolios and change.get("plugin_id") in plugins):
            _abort("statement_reader_admin_input_invalid")
        key = (change["portfolio_id"], change["plugin_id"])
        if key in seen:
            _abort("statement_reader_admin_input_invalid")
        seen.add(key)
        result.append(dict(change))
    return result


def preview_activation_v1(space: str | Path, context_value: Any, changes: Any) -> dict[str, Any]:
    """Welche Plugins in welchem Portfolio aktiv oder nicht aktiv wuerden; schreibt nichts (ausser dem einmaligen Bestandseintrag)."""
    context = _context(context_value)
    normalized = _normalized_changes(space, changes)
    state = activation_v1(space, context)
    current = {(entry["portfolio_id"], plugin["plugin_id"]): entry["active"] for plugin in state["plugins"] for entry in plugin["states"]}
    portfolios = {item["portfolio_id"]: item["label"] for item in state["portfolios"]}
    labels = {plugin["plugin_id"]: plugin["label"] for plugin in state["plugins"]}
    effective = [{"portfolio_id": change["portfolio_id"], "portfolio_label": portfolios[change["portfolio_id"]], "plugin_id": change["plugin_id"],
                  "plugin_label": labels[change["plugin_id"]], "from": current[(change["portfolio_id"], change["plugin_id"])], "to": change["active"]}
                 for change in normalized if current[(change["portfolio_id"], change["plugin_id"])] != change["active"]]
    return {"contract_version": "statement_reader_activation_preview_v1", "changes": effective, "unchanged_count": len(normalized) - len(effective),
            "preview_fingerprint": _fingerprint({"changes": effective, "state": sorted(current.items())})}


def apply_activation_v1(space: str | Path, context_value: Any, changes: Any, preview_fingerprint: str, confirmed: bool, recorded_at_utc: str) -> dict[str, Any]:
    context = _context(context_value)
    if confirmed is not True:
        _abort("statement_reader_admin_confirmation_required")
    stamp = _stamp(recorded_at_utc)
    preview = preview_activation_v1(space, context, changes)
    if preview["preview_fingerprint"] != preview_fingerprint:
        _abort("statement_reader_admin_preview_stale")
    connection = _connect(space, context, True)
    try:
        with connection:
            for change in preview["changes"]:
                body = {"portfolio_id": change["portfolio_id"], "plugin_id": change["plugin_id"], "active": int(change["to"]), "origin": "owner",
                        "actor_id": context.actor_id, "recorded_at_utc": stamp}
                connection.execute("INSERT INTO plugin_activation_entry(portfolio_id,plugin_id,active,origin,actor_id,recorded_at_utc,entry_fingerprint)"
                                   " VALUES(?,?,?,?,?,?,?)", (change["portfolio_id"], change["plugin_id"], int(change["to"]), "owner", context.actor_id,
                                                               stamp, _fingerprint(body)))
    except sqlite3.Error:
        _abort("statement_reader_admin_store_invalid")
    finally:
        connection.close()
    return {"contract_version": "statement_reader_activation_apply_v1", "written_count": len(preview["changes"])}


# ---------------------------------------------------------------- Installieren aus einer ZIP-Datei
def _safe_extract(zip_bytes: bytes, target: Path) -> Path:
    """Entpackt sicher: keine Verknuepfung, kein Pfad nach aussen, Groessengrenzen. Ein gemeinsamer Oberordner wird abgestreift.
    Liefert den ausgepackten Ordner: mit manifest.json (Plugin-Ordner) oder mit package.json (Paket, #486 Schritt 3)."""
    if not isinstance(zip_bytes, (bytes, bytearray)) or not zip_bytes:
        _abort("statement_reader_install_zip_invalid")
    if len(zip_bytes) > MAX_ZIP_BYTES:
        _abort("statement_reader_install_too_large")
    try:
        archive = zipfile.ZipFile(io.BytesIO(bytes(zip_bytes)))
        infos = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
        _abort("statement_reader_install_zip_invalid")
        return target
    if not infos or len(infos) > MAX_ENTRIES or sum(info.file_size for info in infos) > MAX_UNPACKED_BYTES:
        _abort("statement_reader_install_too_large")
    names = []
    for info in infos:
        mode = (info.external_attr >> 16) & 0o177777
        kind = stat.S_IFMT(mode)   # 0: nur Rechte ohne Dateiart (Windows-Packer, Python writestr) - gilt als gewoehnliche Datei
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR):   # Verknuepfungen, Geraete, Pipes
            _abort("statement_reader_install_zip_unsafe")
        name = info.filename
        path = PurePosixPath(name)
        if "\\" in name or name.startswith("/") or path.is_absolute() or any(part in ("..", "") for part in path.parts if part != ".") \
                or (path.parts and ":" in path.parts[0]) or any(ord(char) < 32 for char in name):
            _abort("statement_reader_install_zip_unsafe")
        names.append((info, path))
    tops = {path.parts[0] for _info, path in names if path.parts}
    strip = len(tops) == 1 and not any(len(path.parts) == 1 and not info.is_dir() for info, path in names)
    root = target / "plugin"
    root.mkdir(mode=0o700)
    for info, path in names:
        parts = path.parts[1:] if strip else path.parts
        if not parts or "__pycache__" in parts:
            continue
        destination = root.joinpath(*parts)
        if info.is_dir():
            destination.mkdir(mode=0o700, parents=True, exist_ok=True); continue
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            data = archive.read(info)
        except (zipfile.BadZipFile, OSError, RuntimeError, ValueError):
            _abort("statement_reader_install_zip_invalid")
        if len(data) != info.file_size:
            _abort("statement_reader_install_zip_invalid")
        with destination.open("xb") as handle:
            handle.write(data)
        destination.chmod(0o600)
    if not (root / "manifest.json").is_file() and not (root / "package.json").is_file():
        _abort("statement_reader_install_manifest_invalid")
    return root


def _shipped_version(plugin_id: str) -> str | None:
    """Version des mitgelieferten Plugins dieser Kennung (aus seinem Ordner, auch wenn gerade ein Update gilt)."""
    path = reader_plugins.PLUGIN_ROOT / plugin_id / "manifest.json"
    if not path.is_file() or path.is_symlink():
        return None
    try:
        version = json.loads(path.read_text(encoding="utf-8")).get("plugin_version")
    except (OSError, UnicodeError, ValueError):
        return None
    return version if isinstance(version, str) else None


def _plugin_code_sha256(directory: Path, manifest: Mapping[str, Any]) -> str:
    """Einstieg, Module und Regeln im Manifest (rc.419) - wie der Pruefstand (reader_check_identity_v1)."""
    code = {"entry": manifest.get("entry_point_sha256"), "modules": sorted(str(module.get("sha256")) for module in manifest.get("modules") or []),
            "rules": reader_plugins.manifest_rules_sha256_v1(manifest)}
    return _fingerprint(code)


def _installed_pointer(space: str | Path) -> dict[str, str]:
    pointer = Path(space) / AREA / POINTER
    if not pointer.exists():
        return {}
    if pointer.is_symlink():
        _abort("statement_reader_admin_store_invalid")
    try:
        value = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        _abort("statement_reader_admin_store_invalid")
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        _abort("statement_reader_admin_store_invalid")
    return value


def _write_pointer(space: str | Path, mapping: Mapping[str, str]) -> None:
    root = Path(space) / AREA
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = root / (POINTER + ".tmp")
    temporary.write_text(json.dumps(dict(sorted(mapping.items())), indent=1), encoding="utf-8")
    temporary.chmod(0o600)
    settle_new_directory_v1(root)  # #568: auch die gocryptfs.diriv neuer Ordner festschreiben
    os.replace(temporary, root / POINTER)


def _selftest_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    readers = []
    for entry in report.get("readers") or []:
        findings: dict[tuple[str, str, str], int] = {}
        for stage in ("fixtures", "order", "mutations"):
            for item in (entry.get(stage) or {}).get("failures", []):
                key = (stage, item.get("finding", ""), str(item.get("code") or ""))
                findings[key] = findings.get(key, 0) + 1
        for item in (entry.get("generated") or {}).get("failures", []):
            key = ("generated", item.get("finding", ""), str(item.get("code") or ""))
            findings[key] = findings.get(key, 0) + 1
        readers.append({"reader_id": entry["reader_id"], "domain": entry["domain"], "fixtures": (entry.get("fixtures") or {}).get("count", 0),
                        "mutations": (entry.get("mutations") or {}).get("count", 0), "generated": (entry.get("generated") or {}).get("count", 0),
                        "implausible_today": (entry.get("fixtures") or {}).get("implausible_today", 0),
                        "findings": [{"stage": stage, "finding": finding, "code": code or None, "count": count}
                                     for (stage, finding, code), count in sorted(findings.items())]})
    return {"passed": bool(report.get("passed")), "problems": list(report.get("problems") or []), "readers": readers}


def _evaluate_zip(space: str | Path, zip_bytes: bytes, workdir: Path, run_selftest: bool) -> dict[str, Any]:
    """Prueft eine Plugin-ZIP vollstaendig (ohne zu installieren). Liefert die oeffentliche Vorschau und intern den Plugin-Ordner."""
    from migrations.reference import plugin_package_v1 as package_module  # noqa: PLC0415
    root = _safe_extract(zip_bytes, workdir)
    package = None
    if package_module.is_package_v1(root):
        # Paket (#486 Schritt 3): package.json nennt jede Datei mit Pruefsumme; die Signatur ist ein Befund, kein Abbruch.
        try:
            package = package_module.inspect_package_v1(root, kind="statement_reader")
        except package_module.PluginPackageBlocked as error:
            _abort("statement_reader_install_package_file_mismatch" if error.code == "plugin_package_file_mismatch" else "statement_reader_install_package_invalid")
        root = package["plugin_dir"]
        if not (root / "manifest.json").is_file():
            _abort("statement_reader_install_manifest_invalid")
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        _abort("statement_reader_install_manifest_invalid")
        return {}
    plugin_id = manifest.get("plugin_id") if isinstance(manifest, dict) else None
    if not isinstance(plugin_id, str) or reader_plugins._PLUGIN_ID.match(plugin_id) is None:
        _abort("statement_reader_install_manifest_invalid")
    named = workdir / "named" / plugin_id
    named.parent.mkdir(mode=0o700)
    root.rename(named)
    problems: list[str] = []
    found_signature = package["signature"] if package else {"status": "unsigned"}
    signed = found_signature["status"] == "valid"
    if package is not None and (package["plugin_id"] != plugin_id or package["plugin_version"] != manifest.get("plugin_version")):
        problems.append("statement_reader_install_package_mismatch")
    if found_signature["status"] not in ("valid", "unsigned"):
        problems.append(found_signature["status"])
    try:
        specs = reader_plugins._manifest_readers(named, manifest)
    except reader_plugins.StatementReaderBlocked as error:
        problems.append("statement_reader_install_api_unsupported" if error.code == "statement_reader_api_version_unsupported"
                        else "statement_reader_install_manifest_invalid")
        specs = []
    # Gleiche Kennung wie ein mitgeliefertes Plugin: nur als Update - von Portelyra signiert und mit hoeherer Version (Festlegung 16.11.2026).
    shipped_version = _shipped_version(plugin_id)
    if shipped_version is not None:
        if not signed:
            problems.append("statement_reader_install_update_unsigned")
        elif not package_module.newer_v1(manifest.get("plugin_version"), shipped_version):
            problems.append("statement_reader_install_update_not_newer")
    elif (reader_plugins.PLUGIN_ROOT / plugin_id).exists():
        problems.append("statement_reader_install_plugin_id_taken")
    others = {(spec.domain, spec.reader_id) for spec in reader_plugins.reader_specs_v1() if spec.plugin_id != plugin_id}
    if any((spec.domain, spec.reader_id) in others for spec in specs):
        problems.append("statement_reader_install_reader_id_taken")
    if specs and not all(spec.generator for spec in specs):
        problems.append("statement_reader_install_generator_missing")
    # Fremde Plugins nur in den freigegebenen Bereichen; ein Update darf die Bereiche behalten, die das mitgelieferte Plugin schon liest.
    own = {(spec.domain, spec.reader_id) for spec in reader_plugins.reader_specs_v1() if spec.plugin_id == plugin_id} if shipped_version else set()
    if any(spec.domain not in INSTALLABLE_DOMAINS and (spec.domain, spec.reader_id) not in own for spec in specs):
        problems.append("statement_reader_install_domain_unsupported")
    selftest = None
    if run_selftest and specs and not problems:
        from migrations.reference import statement_reader_selftest_v1 as selftest_module  # noqa: PLC0415
        saved = os.environ.pop(reader_plugins.REFERENCE_DATE_ENV, None)   # Selbsttest mit dem echten Datum
        started = datetime.now(timezone.utc)
        try:
            with selftest_module.external_plugin_root_v1(named) as loaded_id:
                report = selftest_module.selftest_plugin_v1(loaded_id, seed=int(started.strftime("%Y%m%d")), **INSTALL_SELFTEST)
        except reader_plugins.StatementReaderBlocked:
            report = {"passed": False, "problems": ["statement_reader_manifest_invalid"], "readers": []}
        finally:
            if saved is not None:
                os.environ[reader_plugins.REFERENCE_DATE_ENV] = saved
        selftest = {**_selftest_summary(report), "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1)}
        if not selftest["passed"]:
            problems.append("statement_reader_install_selftest_failed")
    current = _installed_pointer(space).get(plugin_id)
    replaces = None
    if current:
        try:
            replaces = {"plugin_version": json.loads((Path(space) / AREA / current / "manifest.json").read_text(encoding="utf-8")).get("plugin_version")}
        except (OSError, UnicodeError, ValueError):
            replaces = {"plugin_version": None}
    # Herausgeber laut Manifest; "von Portelyra signiert" nur mit gueltiger Signatur eines Pakets (#486 Schritt 3).
    public = {"plugin_id": plugin_id, "plugin_version": manifest.get("plugin_version"), "publisher": manifest.get("publisher"), "publisher_verified": signed,
              "signature": found_signature["status"], "replaces_shipped": {"plugin_version": shipped_version} if shipped_version else None,
              "institution": manifest.get("institution"), "label": manifest.get("label"), "api_minor": manifest.get("api_minor"),
              "readers": [{"reader_id": spec.reader_id, "domain": spec.domain, "label": spec.label, "tested_formats": spec.tested_formats,
                           "known_limits": list(spec.known_limits), "generator": spec.generator} for spec in specs],
              "replaces": replaces, "selftest": selftest, "problems": problems, "installable": not problems and selftest is not None}
    code_sha = _plugin_code_sha256(named, manifest)
    public["preview_fingerprint"] = _fingerprint({"zip": hashlib.sha256(bytes(zip_bytes)).hexdigest(), "code": code_sha, "replaces": replaces,
                                                  "installable": public["installable"], "problems": problems, "signature": found_signature["status"],
                                                  "shipped_version": shipped_version})
    return {"public": public, "directory": named, "code_sha256": code_sha, "manifest": manifest,
            "package_source": (workdir / "plugin") if package is not None else None}


def preview_plugin_install_v1(space: str | Path, context_value: Any, zip_bytes: bytes, file_name: str) -> dict[str, Any]:
    """Prueft eine Plugin-ZIP: sicher entpacken, Manifest, Schnittstellenstufe, Kennungen, Erzeuger je Leser, Selbsttest mit echtem Datum.
    Schreibt nichts."""
    _context(context_value)
    if not isinstance(file_name, str) or not file_name.lower().endswith(".zip"):
        _abort("statement_reader_install_zip_invalid")
    with tempfile.TemporaryDirectory(prefix="reader-install-") as temporary:
        return {"contract_version": "statement_reader_install_preview_v1", **_evaluate_zip(space, zip_bytes, Path(temporary), True)["public"]}


def apply_plugin_install_v1(space: str | Path, context_value: Any, zip_bytes: bytes, file_name: str, preview_fingerprint: str, confirmed: bool,
                            recorded_at_utc: str) -> dict[str, Any]:
    """Installiert genau die gepruefte ZIP (Pruefwert der Vorschau; der Selbsttest laeuft dabei erneut). Aktiviert nichts."""
    context = _context(context_value)
    if confirmed is not True:
        _abort("statement_reader_admin_confirmation_required")
    stamp = _stamp(recorded_at_utc)
    if not isinstance(file_name, str) or not file_name.lower().endswith(".zip"):
        _abort("statement_reader_install_zip_invalid")
    with tempfile.TemporaryDirectory(prefix="reader-install-") as temporary:
        evaluated = _evaluate_zip(space, zip_bytes, Path(temporary), True)
        public = evaluated["public"]
        if public["preview_fingerprint"] != preview_fingerprint:
            _abort("statement_reader_admin_preview_stale")
        if not public["installable"]:
            _abort(public["problems"][0] if public["problems"] else "statement_reader_install_selftest_failed")
        plugin_id, version = public["plugin_id"], str(public["plugin_version"])
        relative = f"plugins/{plugin_id}/{version}-{evaluated['code_sha256'][:12]}/{plugin_id}"
        destination = Path(space) / AREA / relative
        if not destination.exists():
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copytree(evaluated["directory"], destination, ignore=shutil.ignore_patterns("__pycache__"))
        # Paket (#486 Schritt 3): package.json und Signatur neben den Plugin-Ordner - die Registry prueft die Signatur bei jedem Laden.
        source = evaluated["package_source"]
        if source is not None:
            for name in ("package.json", "package.json.sig"):
                if (source / name).is_file() and not (destination.parent / name).exists():
                    shutil.copyfile(source / name, destination.parent / name)
                    (destination.parent / name).chmod(0o600)
        connection = _connect(space, context, True)
        try:
            with connection:
                body = {"plugin_id": plugin_id, "plugin_version": version, "plugin_code_sha256": evaluated["code_sha256"], "relative_dir": relative,
                        "action": "installed", "actor_id": context.actor_id, "recorded_at_utc": stamp}
                connection.execute("INSERT INTO plugin_installation_entry(plugin_id,plugin_version,plugin_code_sha256,zip_sha256,relative_dir,action,"
                                   "selftest_json,actor_id,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   (plugin_id, version, evaluated["code_sha256"], hashlib.sha256(bytes(zip_bytes)).hexdigest(), relative, "installed",
                                    json.dumps(public["selftest"], sort_keys=True), context.actor_id, stamp, _fingerprint(body)))
            pointer = _installed_pointer(space)
            pointer[plugin_id] = relative
            _write_pointer(space, pointer)
        except sqlite3.Error:
            _abort("statement_reader_admin_store_invalid")
        finally:
            connection.close()
    reader_plugins._registry.cache_clear()
    key = _compatibility_key(plugin_id)
    if key is not None:   # der Selbsttest dieser Fassung lief gerade: als Kompatibilitaet mit dieser Fassung von Portelyra festhalten
        _record_compatibility(space, context, key, public["selftest"] or {"passed": False}, stamp)
    return {"contract_version": "statement_reader_install_apply_v1", "plugin_id": plugin_id, "plugin_version": version, "status": "installed"}


# ---------------------------------------------------------------- Kompatibilitaet nach Updates (nur installierte Plugins)
def _core_version() -> str:
    version_file = reader_plugins.ROOT / "VERSION"
    return version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "0.0.0"


def _compatibility_key(plugin_id: str) -> dict[str, str] | None:
    specs = [spec for spec in reader_plugins.reader_specs_v1() if spec.plugin_id == plugin_id]
    if not specs:
        return None
    identity = reader_plugins.reader_check_identity_v1(specs[0].reader_id, specs[0].domain)
    return {"plugin_id": plugin_id, "plugin_code_sha256": identity["plugin_code_sha256"], "shared_code_sha256": identity["shared_code_sha256"],
            "core_version": _core_version()}


def _record_compatibility(space: str | Path, context: Any, key: Mapping[str, str], selftest: Mapping[str, Any], stamp: str) -> None:
    connection = _connect(space, context, True)
    try:
        with connection:
            body = {**key, "passed": int(bool(selftest.get("passed"))), "recorded_at_utc": stamp}
            connection.execute("INSERT INTO plugin_compatibility_entry(plugin_id,plugin_code_sha256,shared_code_sha256,core_version,passed,selftest_json,"
                               "recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?,?,?)",
                               (key["plugin_id"], key["plugin_code_sha256"], key["shared_code_sha256"], key["core_version"], int(bool(selftest.get("passed"))),
                                json.dumps(dict(selftest), sort_keys=True), stamp, _fingerprint(body)))
    except sqlite3.Error:
        _abort("statement_reader_admin_store_invalid")
    finally:
        connection.close()


def plugin_compatibility_v1(space: str | Path, context_value: Any, plugin_id: str, run: bool = True) -> dict[str, Any]:
    """Ist ein installiertes Plugin mit dieser Fassung von Portelyra kompatibel? Mitgelieferte gelten als geprueft (Release-Gate). Fehlt fuer
    die jetzige Hilfsbibliothek und Produktversion ein Ergebnis, laeuft der Selbsttest einmal (``run``) und wird festgehalten."""
    context = _context(context_value)
    plugins = _plugins()
    item = plugins.get(plugin_id)
    if item is None:
        return {"plugin_id": plugin_id, "status": "unknown"}
    if item["origin"] == "shipped":
        return {"plugin_id": plugin_id, "status": "shipped"}
    key = _compatibility_key(plugin_id)
    connection = _connect(space, context, False)
    try:
        row = connection.execute("SELECT passed,selftest_json,recorded_at_utc FROM plugin_compatibility_entry WHERE plugin_id=? AND plugin_code_sha256=?"
                                 " AND shared_code_sha256=? AND core_version=? ORDER BY entry_id DESC LIMIT 1",
                                 (key["plugin_id"], key["plugin_code_sha256"], key["shared_code_sha256"], key["core_version"])).fetchone() \
            if connection is not None else None
    except sqlite3.Error:
        _abort("statement_reader_admin_store_invalid")
    finally:
        if connection is not None:
            connection.close()
    if row is None and run:
        directory = next(spec.plugin_dir for spec in reader_plugins.reader_specs_v1() if spec.plugin_id == plugin_id)
        from migrations.reference import statement_reader_selftest_v1 as selftest_module  # noqa: PLC0415
        saved = os.environ.pop(reader_plugins.REFERENCE_DATE_ENV, None)
        started = datetime.now(timezone.utc)
        try:
            with selftest_module.external_plugin_root_v1(directory) as loaded_id:
                report = selftest_module.selftest_plugin_v1(loaded_id, seed=int(started.strftime("%Y%m%d")), **INSTALL_SELFTEST)
        except reader_plugins.StatementReaderBlocked:
            report = {"passed": False, "problems": ["statement_reader_manifest_invalid"], "readers": []}
        finally:
            if saved is not None:
                os.environ[reader_plugins.REFERENCE_DATE_ENV] = saved
        summary = {**_selftest_summary(report), "duration_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1)}
        stamp = _now()
        _record_compatibility(space, context, key, summary, stamp)
        return {"plugin_id": plugin_id, "status": "compatible" if summary["passed"] else "incompatible", "tested_at_utc": stamp, "selftest": summary,
                "core_version": key["core_version"]}
    if row is None:
        return {"plugin_id": plugin_id, "status": "untested", "core_version": key["core_version"]}
    return {"plugin_id": plugin_id, "status": "compatible" if row["passed"] else "incompatible", "tested_at_utc": row["recorded_at_utc"],
            "selftest": json.loads(row["selftest_json"]), "core_version": key["core_version"]}


# ---------------------------------------------------------------- Entfernen (nur installierte)
def _provenance_count(space: str | Path, context: Any, plugin_id: str) -> int | None:
    """Buchungen mit Herkunft dieses Plugins; nicht lesbar heisst "nicht verfuegbar" (None), nie 0."""
    try:
        provenance = references.read_reader_provenance_v1(space, context)["provenance"]
    except references.AssetActivityReferenceV1Error:
        return None
    return sum(1 for entry in provenance.values() if any(reader["plugin_id"] == plugin_id for reader in entry["readers"]))


def preview_plugin_remove_v1(space: str | Path, context_value: Any, plugin_id: str) -> dict[str, Any]:
    context = _context(context_value)
    if not isinstance(plugin_id, str):
        _abort("statement_reader_admin_input_invalid")
    pointer = _installed_pointer(space)
    # Ein Update eines mitgelieferten Plugins wird nicht entfernt (das schaltete es in jedem Portfolio ab), sondern ueber "Zur vorigen Fassung"
    # zurueckgenommen (#486 Schritt 3).
    if plugin_id not in pointer or _shipped_version(plugin_id) is not None:
        _abort("statement_reader_remove_shipped" if plugin_id in _shipped_plugin_ids() or _shipped_version(plugin_id) else "statement_reader_remove_unknown")
    plugins = _plugins()
    active = active_plugins_v1(space, context)
    portfolios = _portfolios(space)
    item = plugins.get(plugin_id, {"label": plugin_id, "plugin_version": None})
    result = {"plugin_id": plugin_id, "plugin_version": item.get("plugin_version"), "label": item.get("label"),
              "active_in": [portfolios[portfolio]["label"] for portfolio, ids in active.items() if plugin_id in ids],
              "bookings_with_provenance": _provenance_count(space, context, plugin_id)}
    return {"contract_version": "statement_reader_remove_preview_v1", **result, "preview_fingerprint": _fingerprint({**result, "relative": pointer[plugin_id]})}


def apply_plugin_remove_v1(space: str | Path, context_value: Any, plugin_id: str, preview_fingerprint: str, confirmed: bool, recorded_at_utc: str) -> dict[str, Any]:
    context = _context(context_value)
    if confirmed is not True:
        _abort("statement_reader_admin_confirmation_required")
    stamp = _stamp(recorded_at_utc)
    preview = preview_plugin_remove_v1(space, context, plugin_id)
    if preview["preview_fingerprint"] != preview_fingerprint:
        _abort("statement_reader_admin_preview_stale")
    pointer = _installed_pointer(space)
    relative = pointer.pop(plugin_id)
    active = active_plugins_v1(space, context)
    connection = _connect(space, context, True)
    try:
        with connection:
            # In jedem Portfolio deaktivieren, wo es aktiv war: eine spaetere Neuinstallation ist nicht still wieder aktiv.
            for portfolio, ids in active.items():
                if plugin_id in ids:
                    off = {"portfolio_id": portfolio, "plugin_id": plugin_id, "active": 0, "origin": "owner", "actor_id": context.actor_id, "recorded_at_utc": stamp}
                    connection.execute("INSERT INTO plugin_activation_entry(portfolio_id,plugin_id,active,origin,actor_id,recorded_at_utc,entry_fingerprint)"
                                       " VALUES(?,?,?,?,?,?,?)", (portfolio, plugin_id, 0, "owner", context.actor_id, stamp, _fingerprint(off)))
            body = {"plugin_id": plugin_id, "plugin_version": str(preview["plugin_version"]), "relative_dir": relative, "action": "removed",
                    "actor_id": context.actor_id, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO plugin_installation_entry(plugin_id,plugin_version,plugin_code_sha256,zip_sha256,relative_dir,action,"
                               "selftest_json,actor_id,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (plugin_id, str(preview["plugin_version"] or "0"), "0" * 64, "0" * 64, relative, "removed", "{}", context.actor_id, stamp,
                                _fingerprint(body)))
        _write_pointer(space, pointer)
    except sqlite3.Error:
        _abort("statement_reader_admin_store_invalid")
    finally:
        connection.close()
    reader_plugins._registry.cache_clear()
    return {"contract_version": "statement_reader_remove_apply_v1", "plugin_id": plugin_id, "status": "removed"}


def _manifest_version(space: str | Path, relative: str) -> str | None:
    try:
        version = json.loads((Path(space) / AREA / relative / "manifest.json").read_text(encoding="utf-8")).get("plugin_version")
    except (OSError, UnicodeError, ValueError):
        return None
    return version if isinstance(version, str) else None


def _revert_target(space: str | Path, context: Any, plugin_id: str) -> dict[str, Any]:
    """Wohin "Zur vorigen Fassung" fuehrt (#486 Schritt 3, Festlegung 16.11.2026): zur juengsten frueher installierten Fassung mit
    niedrigerer Version, deren Ordner noch da ist; gibt es keine (oder ist sie nicht hoeher als die mitgelieferte), zur mitgelieferten."""
    from migrations.reference import plugin_package_v1 as package_module  # noqa: PLC0415
    pointer = _installed_pointer(space)
    current = pointer.get(plugin_id)
    if current is None:
        _abort("statement_reader_revert_unavailable")
    current_version = _manifest_version(space, current)
    connection = _connect(space, context, False)
    rows = []
    if connection is not None:
        try:
            rows = connection.execute("SELECT relative_dir, action FROM plugin_installation_entry WHERE plugin_id=? ORDER BY entry_id DESC", (plugin_id,)).fetchall()
        except sqlite3.Error:
            _abort("statement_reader_admin_store_invalid")
        finally:
            connection.close()
    shipped = _shipped_version(plugin_id)
    for row in rows:
        relative = row["relative_dir"]
        if row["action"] != "installed" or relative == current or _inside(space, relative) is None:
            continue
        version = _manifest_version(space, relative)
        if package_module.newer_v1(current_version, version) and (shipped is None or package_module.newer_v1(version, shipped)):
            return {"origin": "installed", "relative_dir": relative, "plugin_version": version, "current": current, "current_version": current_version}
    if shipped is not None:
        return {"origin": "shipped", "relative_dir": None, "plugin_version": shipped, "current": current, "current_version": current_version}
    _abort("statement_reader_revert_unavailable")
    return {}


def _inside(space: str | Path, relative: str) -> Path | None:
    root = Path(space) / AREA
    path = root / relative
    if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts or path.is_symlink() or not path.is_dir():
        return None
    return path


def preview_plugin_revert_v1(space: str | Path, context_value: Any, plugin_id: str) -> dict[str, Any]:
    """Vorschau "Zur vorigen Fassung": von welcher Fassung zu welcher, mitgeliefert oder installiert. Schreibt nichts."""
    context = _context(context_value)
    if not isinstance(plugin_id, str):
        _abort("statement_reader_admin_input_invalid")
    target = _revert_target(space, context, plugin_id)
    result = {"plugin_id": plugin_id, "from_version": target["current_version"], "to_version": target["plugin_version"], "to_origin": target["origin"]}
    return {"contract_version": "statement_reader_revert_preview_v1", **result,
            "preview_fingerprint": _fingerprint({**result, "current": target["current"], "target": target["relative_dir"]})}


def apply_plugin_revert_v1(space: str | Path, context_value: Any, plugin_id: str, preview_fingerprint: str, confirmed: bool, recorded_at_utc: str) -> dict[str, Any]:
    """Nimmt die geltende installierte Fassung zurueck - nur bestaetigt und genau wie gezeigt. Die Aktivierung je Portfolio bleibt; der
    Pruefstand faengt fuer die Fassung neu an, die dann gilt (anderer Code). Nur anhaengende Eintraege, keine Datei wird geloescht."""
    context = _context(context_value)
    if confirmed is not True:
        _abort("statement_reader_admin_confirmation_required")
    stamp = _stamp(recorded_at_utc)
    preview = preview_plugin_revert_v1(space, context, plugin_id)
    if preview["preview_fingerprint"] != preview_fingerprint:
        _abort("statement_reader_admin_preview_stale")
    target = _revert_target(space, context, plugin_id)
    pointer = _installed_pointer(space)
    connection = _connect(space, context, True)
    try:
        with connection:
            if target["origin"] == "installed":
                relative = target["relative_dir"]
                manifest = json.loads((Path(space) / AREA / relative / "manifest.json").read_text(encoding="utf-8"))
                code = _plugin_code_sha256(Path(space) / AREA / relative, manifest)
                action, version, pointer[plugin_id] = "installed", str(target["plugin_version"]), relative
            else:
                relative, code, action, version = target["current"], "0" * 64, "removed", str(target["current_version"] or "0")
                pointer.pop(plugin_id)
            body = {"plugin_id": plugin_id, "plugin_version": version, "relative_dir": relative, "action": action, "reverted": True,
                    "actor_id": context.actor_id, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO plugin_installation_entry(plugin_id,plugin_version,plugin_code_sha256,zip_sha256,relative_dir,action,"
                               "selftest_json,actor_id,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (plugin_id, version, code, "0" * 64, relative, action, json.dumps({"reverted": True}), context.actor_id, stamp, _fingerprint(body)))
        _write_pointer(space, pointer)
    except (sqlite3.Error, OSError, ValueError):
        _abort("statement_reader_admin_store_invalid")
    finally:
        connection.close()
    reader_plugins._registry.cache_clear()
    return {"contract_version": "statement_reader_revert_apply_v1", "plugin_id": plugin_id, "status": "reverted", "plugin_version": target["plugin_version"],
            "origin": target["origin"]}


__all__ = ["ACTIVATION_PORTFOLIOS_CREATED_BEFORE", "AREA", "FAILURE_CODES", "StatementReaderAdminV1Error", "activation_v1", "active_plugins_v1",
           "apply_activation_v1", "apply_plugin_install_v1", "apply_plugin_remove_v1", "apply_plugin_revert_v1", "preview_plugin_revert_v1", "ensure_activation_baseline_v1", "offered_readers_v1",
           "plugin_compatibility_v1", "preview_activation_v1", "preview_plugin_install_v1", "preview_plugin_remove_v1", "store_present_v1"]
