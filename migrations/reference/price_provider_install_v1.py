#!/usr/bin/env python3
"""Kursanbieter aus einem Paket installieren (#486 Schritt 3, Festlegungen vom 15. und 16.11.2026).

- Nur Pakete (package.json mit Pruefsumme je Datei, wahlweise signiert, plugin_package_v1). Manifest wie bei den mitgelieferten
  Anbietern (price_provider_plugins_v1), Selbsttest ohne Netz vor dem Installieren.
- Gleiche Kennung wie ein mitgelieferter Anbieter (Yahoo, EODHD): nur als Update - von Portelyra signiert, hoehere Version, dieselbe
  Anbieter-Kennung. Es wirkt mit der Installation; die Aktivierung, Kosten-Einstellungen und Zugaenge bleiben (gleiche Anbieter-Kennung).
- Eigene Kennung: auch unsigniert, dann "ungeprueft" (die Data-App verlangt eine zusaetzliche Bestaetigung); neu installiert ist der
  Anbieter nicht aktiv ("neu - noch nicht eingestellt"), aktiviert wird er mit Adressen, Kosten und Bedingungen im Reiter "Kursanbieter".
- "Zur vorigen Fassung": zur frueheren installierten Fassung mit niedrigerer Version, sonst zur mitgelieferten; bei eigener Kennung ohne
  fruehere Fassung wird der Anbieter nicht mehr geladen (seine Dateien bleiben).
Abgelegt im Datenraum unter price-provider-plugins-v1 (im Backup); jede Fassung in einem eigenen Ordner, Protokoll nur anhaengend.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference import plugin_package_v1 as package_module
from migrations.reference import price_provider_admin_v1 as admin
from migrations.reference import price_provider_plugins_v1 as providers

AREA = providers.INSTALLED_AREA
POINTER = "installed.json"
LOG = "installations.sqlite"
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS price_provider_installation(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, context_fingerprint TEXT NOT NULL,"
    " plugin_id TEXT NOT NULL, plugin_version TEXT NOT NULL, relative_dir TEXT NOT NULL, action TEXT NOT NULL CHECK(action IN ('installed','reverted')),"
    " signature TEXT NOT NULL, zip_sha256 TEXT NOT NULL, actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL)",
    "CREATE TRIGGER IF NOT EXISTS price_provider_installation_no_update BEFORE UPDATE ON price_provider_installation BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS price_provider_installation_no_delete BEFORE DELETE ON price_provider_installation BEGIN SELECT RAISE(ABORT,'immutable'); END",
)
FAILURE_CODES = (
    "price_provider_install_package_invalid", "price_provider_install_package_file_mismatch", "price_provider_install_too_large",
    "price_provider_install_unsafe", "price_provider_install_update_unsigned", "price_provider_install_update_not_newer",
    "price_provider_install_update_provider_changed", "price_provider_install_id_taken", "price_provider_install_selftest_failed",
    "price_provider_install_preview_stale", "price_provider_install_confirmation_required", "price_provider_install_store_invalid",
    "price_provider_revert_unavailable", "price_provider_isolation_unavailable",
    "price_provider_plugin_signature_untrusted", "price_provider_plugin_signature_invalid", "price_provider_plugin_signature_tool_missing",
)
SELFTEST = {"seeds": range(1, 26), "mutations_per_fixture": 6}


class PriceProviderInstallBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise PriceProviderInstallBlocked(code)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _area(space: str | Path) -> Path:
    return Path(space) / AREA


def _pointer(space: str | Path) -> dict[str, str]:
    path = _area(space) / POINTER
    if not path.exists():
        return {}
    if path.is_symlink():
        _abort("price_provider_install_store_invalid")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        _abort("price_provider_install_store_invalid")
        return {}
    if not isinstance(value, dict) or not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        _abort("price_provider_install_store_invalid")
    return value


def _write_pointer(space: str | Path, mapping: dict[str, str]) -> None:
    root = _area(space)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = root / (POINTER + ".tmp")
    temporary.write_text(json.dumps(dict(sorted(mapping.items())), indent=1), encoding="utf-8")
    temporary.chmod(0o600)
    settle_new_directory_v1(root)  # #568: auch die gocryptfs.diriv neuer Ordner festschreiben
    os.replace(temporary, root / POINTER)


def _shipped(plugin_id: str) -> providers.ProviderSpec | None:
    directory = providers.PLUGIN_ROOT / plugin_id
    if not (directory / "manifest.json").is_file():
        return None
    try:
        return providers._manifest_spec(directory, directory / "manifest.json")
    except providers.PriceProviderBlocked:
        return None


def _selftest(named: Path, plugin_id: str, provider_id: str) -> dict[str, Any]:
    """Selbsttest des Kandidaten ohne Netz: in einem eigenen Probenbereich als installiert eingetragen (samt Paket und Signatur, damit ein
    Update eines mitgelieferten Anbieters so geladen wird wie spaeter), danach ist der Bereich wieder weg."""
    from migrations.reference import price_provider_selftest_v1 as selftest  # noqa: PLC0415
    work = named.parent.parent.parent
    area = work / "probe-area"
    target = area / "plugins" / named.parent.name
    target.parent.mkdir(mode=0o700, parents=True)
    shutil.copytree(named.parent, target, ignore=shutil.ignore_patterns("__pycache__"))
    (area / POINTER).write_text(json.dumps({plugin_id: f"plugins/{named.parent.name}/{plugin_id}"}), encoding="utf-8")
    saved = os.environ.get(providers.INSTALLED_ROOT_ENV)
    os.environ[providers.INSTALLED_ROOT_ENV] = str(area)
    try:
        spec = providers.provider_spec_v1(provider_id)
        if spec is None or spec.plugin_id != plugin_id or spec.origin != "installed":
            return {"passed": False, "problems": ["price_provider_unavailable"], "counts": {}}
        report = selftest.selftest_v1(provider_id, **SELFTEST)
        return {"passed": bool(report.get("passed")), "problems": [item.get("problem") for item in report.get("failures", [])][:10],
                "counts": report.get("counts", {})}
    except providers.PriceProviderBlocked as error:
        return {"passed": False, "problems": [error.code], "counts": {}}
    finally:
        if saved is None:
            os.environ.pop(providers.INSTALLED_ROOT_ENV, None)
        else:
            os.environ[providers.INSTALLED_ROOT_ENV] = saved
        shutil.rmtree(area, ignore_errors=True)


def _evaluate(space: str | Path, zip_bytes: bytes, work: Path) -> dict[str, Any]:
    try:
        root = package_module.safe_extract_v1(zip_bytes, work)
        package = package_module.inspect_package_v1(root, kind="price_provider")
    except package_module.PluginPackageBlocked as error:
        _abort({"plugin_package_file_mismatch": "price_provider_install_package_file_mismatch", "plugin_package_too_large": "price_provider_install_too_large",
                "plugin_package_unsafe": "price_provider_install_unsafe"}.get(error.code, "price_provider_install_package_invalid"))
        return {}
    plugin_id = package["plugin_id"]
    named_parent = work / "kandidat" / f"{package['plugin_version']}"
    named_parent.mkdir(mode=0o700, parents=True)
    named = named_parent / plugin_id
    package["plugin_dir"].rename(named)
    for name in (package_module.PACKAGE_FILE, package_module.SIGNATURE_FILE):
        if (root / name).is_file():
            shutil.copyfile(root / name, named_parent / name)
    problems: list[str] = []
    try:
        spec = providers._manifest_spec(named, named / "manifest.json")
    except providers.PriceProviderBlocked as error:
        spec = None
        problems.append(error.code)
    signature = package["signature"]["status"]
    signed = signature == "valid"
    if signature not in ("valid", "unsigned"):
        problems.append("price_provider_" + signature)
    if spec is not None and spec.plugin_version != package["plugin_version"]:
        problems.append("price_provider_install_package_invalid")
    shipped = _shipped(plugin_id)
    if shipped is not None and spec is not None:
        if not signed:
            problems.append("price_provider_install_update_unsigned")
        elif not package_module.newer_v1(spec.plugin_version, shipped.plugin_version):
            problems.append("price_provider_install_update_not_newer")
        if spec.provider_id != shipped.provider_id:
            problems.append("price_provider_install_update_provider_changed")
    elif spec is not None and any(item.provider_id == spec.provider_id and item.plugin_id != plugin_id for item in providers.provider_specs_v1()):
        problems.append("price_provider_install_id_taken")
    if spec is not None and not providers.isolation_available_v1():
        problems.append("price_provider_isolation_unavailable")     # fremde und aktualisierte Anbieter laufen nur abgeschottet
    selftest = _selftest(named, plugin_id, spec.provider_id) if spec is not None and not problems else None
    if selftest is not None and not selftest["passed"]:
        problems.append("price_provider_install_selftest_failed")
    current = _pointer(space).get(plugin_id)
    replaces = None
    if current:
        try:
            replaces = {"plugin_version": json.loads((_area(space) / current / "manifest.json").read_text(encoding="utf-8")).get("plugin_version")}
        except (OSError, UnicodeError, ValueError):
            replaces = {"plugin_version": None}
    public = {"plugin_id": plugin_id, "plugin_version": package["plugin_version"], "provider_id": spec.provider_id if spec else None,
              "label": spec.label if spec else None, "publisher": spec.publisher if spec else None, "publisher_verified": signed, "signature": signature,
              "hosts": list(spec.hosts) if spec else [], "cost": spec.cost if spec else None, "terms_url": spec.terms_url if spec else None,
              "operations": list(spec.operations) if spec else [], "replaces_shipped": {"plugin_version": shipped.plugin_version} if shipped else None,
              "replaces": replaces, "selftest": selftest, "problems": problems, "installable": not problems and selftest is not None}
    code = hashlib.sha256((named / "manifest.json").read_bytes()).hexdigest()
    public["preview_fingerprint"] = _fingerprint({"zip": hashlib.sha256(bytes(zip_bytes)).hexdigest(), "code": code, "replaces": replaces,
                                                  "problems": problems, "signature": signature, "installable": public["installable"]})
    return {"public": public, "named_parent": named_parent, "code": code}


def preview_install_v1(space: str | Path, context_value: Any, zip_bytes: bytes) -> dict[str, Any]:
    """Prueft ein Kursanbieter-Paket vollstaendig; schreibt nichts."""
    admin._context(context_value)
    with tempfile.TemporaryDirectory(prefix="price-provider-install-") as temporary:
        return {"contract_version": "price_provider_install_preview_v1", **_evaluate(space, zip_bytes, Path(temporary))["public"]}


def _log(space: str | Path, context: Any, plugin_id: str, version: str, relative: str, action: str, signature: str, zip_sha: str, at: str) -> None:
    path = _area(space) / LOG
    created = not path.exists()
    try:
        with sqlite3.connect(path) as connection:
            for statement in SCHEMA:
                connection.execute(statement)
            connection.execute("INSERT INTO price_provider_installation(context_fingerprint,plugin_id,plugin_version,relative_dir,action,signature,"
                               "zip_sha256,actor_id,recorded_at_utc) VALUES(?,?,?,?,?,?,?,?,?)",
                               (_fingerprint([context.tenant_id, context.user_id, context.data_space_id]), plugin_id, version, relative, action,
                                signature, zip_sha, context.actor_id, at))
    except sqlite3.Error:
        _abort("price_provider_install_store_invalid")
    if created:
        path.chmod(0o600)


def _stamp(value: Any) -> str:
    if isinstance(value, str) and len(value) == 20 and value.endswith("Z"):
        return value
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def apply_install_v1(space: str | Path, context_value: Any, zip_bytes: bytes, preview_fingerprint: str, confirmed: bool, recorded_at_utc: str) -> dict[str, Any]:
    """Installiert genau das gepruefte Paket (Pruefwert der Vorschau; der Selbsttest laeuft erneut)."""
    context = admin._context(context_value)
    if confirmed is not True:
        _abort("price_provider_install_confirmation_required")
    with tempfile.TemporaryDirectory(prefix="price-provider-install-") as temporary:
        evaluated = _evaluate(space, zip_bytes, Path(temporary))
        public = evaluated["public"]
        if public["preview_fingerprint"] != preview_fingerprint:
            _abort("price_provider_install_preview_stale")
        if not public["installable"]:
            _abort(public["problems"][0] if public["problems"] else "price_provider_install_selftest_failed")
        plugin_id, version = public["plugin_id"], str(public["plugin_version"])
        relative = f"plugins/{plugin_id}/{version}-{evaluated['code'][:12]}/{plugin_id}"
        destination = _area(space) / relative
        if not destination.parent.exists():
            destination.parent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copytree(evaluated["named_parent"], destination.parent, ignore=shutil.ignore_patterns("__pycache__"))
            for path in [destination.parent, *destination.parent.rglob("*")]:
                path.chmod(0o700 if path.is_dir() else 0o600)
        pointer = _pointer(space)
        pointer[plugin_id] = relative
        _write_pointer(space, pointer)
        _log(space, context, plugin_id, version, relative, "installed", public["signature"], hashlib.sha256(bytes(zip_bytes)).hexdigest(), _stamp(recorded_at_utc))
    return {"contract_version": "price_provider_install_apply_v1", "plugin_id": plugin_id, "plugin_version": version, "status": "installed"}


def _revert_target(space: str | Path, plugin_id: str) -> dict[str, Any]:
    pointer = _pointer(space)
    current = pointer.get(plugin_id)
    if current is None:
        _abort("price_provider_revert_unavailable")
    def version_of(relative: str) -> str | None:
        try:
            return json.loads((_area(space) / relative / "manifest.json").read_text(encoding="utf-8")).get("plugin_version")
        except (OSError, UnicodeError, ValueError):
            return None
    current_version = version_of(current)
    rows = []
    if (_area(space) / LOG).is_file():
        try:
            with sqlite3.connect(f"file:{_area(space) / LOG}?mode=ro", uri=True) as connection:
                rows = connection.execute("SELECT relative_dir FROM price_provider_installation WHERE plugin_id=? AND action='installed' ORDER BY entry_id DESC",
                                          (plugin_id,)).fetchall()
        except sqlite3.Error:
            _abort("price_provider_install_store_invalid")
    shipped = _shipped(plugin_id)
    for (relative,) in rows:
        if relative == current or ".." in Path(relative).parts or not (_area(space) / relative).is_dir():
            continue
        version = version_of(relative)
        if package_module.newer_v1(current_version, version) and (shipped is None or package_module.newer_v1(version, shipped.plugin_version)):
            return {"origin": "installed", "relative_dir": relative, "plugin_version": version, "current": current, "current_version": current_version}
    if shipped is not None:
        return {"origin": "shipped", "relative_dir": None, "plugin_version": shipped.plugin_version, "current": current, "current_version": current_version}
    return {"origin": "none", "relative_dir": None, "plugin_version": None, "current": current, "current_version": current_version}


def preview_revert_v1(space: str | Path, context_value: Any, plugin_id: str) -> dict[str, Any]:
    admin._context(context_value)
    if not isinstance(plugin_id, str):
        _abort("price_provider_revert_unavailable")
    target = _revert_target(space, plugin_id)
    result = {"plugin_id": plugin_id, "from_version": target["current_version"], "to_version": target["plugin_version"], "to_origin": target["origin"]}
    return {"contract_version": "price_provider_revert_preview_v1", **result,
            "preview_fingerprint": _fingerprint({**result, "current": target["current"], "target": target["relative_dir"]})}


def apply_revert_v1(space: str | Path, context_value: Any, plugin_id: str, preview_fingerprint: str, confirmed: bool, recorded_at_utc: str) -> dict[str, Any]:
    context = admin._context(context_value)
    if confirmed is not True:
        _abort("price_provider_install_confirmation_required")
    preview = preview_revert_v1(space, context, plugin_id)
    if preview["preview_fingerprint"] != preview_fingerprint:
        _abort("price_provider_install_preview_stale")
    target = _revert_target(space, plugin_id)
    pointer = _pointer(space)
    if target["origin"] == "installed":
        pointer[plugin_id] = target["relative_dir"]
    else:
        pointer.pop(plugin_id)
    _write_pointer(space, pointer)
    _log(space, context, plugin_id, str(target["plugin_version"] or target["current_version"] or "0"), target["relative_dir"] or target["current"], "reverted",
         "-", "0" * 64, _stamp(recorded_at_utc))
    return {"contract_version": "price_provider_revert_apply_v1", "plugin_id": plugin_id, "status": "reverted", "plugin_version": target["plugin_version"],
            "origin": target["origin"]}


__all__ = ["AREA", "FAILURE_CODES", "PriceProviderInstallBlocked", "apply_install_v1", "apply_revert_v1", "preview_install_v1", "preview_revert_v1"]
