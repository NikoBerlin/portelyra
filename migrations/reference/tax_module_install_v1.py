#!/usr/bin/env python3
"""Steuermodul aus einer ZIP-Datei installieren (#486 Schritt 2c). Vertrag: contracts/tax-module-package/v1.

Festlegungen: Steuermodule nur mit Portelyra-Signatur (15.11.2026); ZIP-Installation mit Selbsttest und
Signaturpruefung schon in Schritt 2 (16.11.2026). Ablauf:
- Vorschau (schreibt nichts): sicher entpacken, Signatur von package.json pruefen (ohne gueltige Signatur laeuft kein Code des Pakets),
  jede Datei gegen ihre Pruefsumme, Manifest, doppelte Jahreswerte (plugin.R = Tabelle), Selbsttest mit den Szenarien des Pakets im
  abgeschotteten Modul, Unterschiede zur mitgelieferten Fassung.
- Installieren: nur mit Bestaetigung und genau der gezeigten Vorschau. Die Fassung kommt in den Datenraum
  (tax-model-plugins-v1/<Modul>/<Version>-<Regelabdruck12>/<Modul>/, im Backup) und in ein nur anhaengendes Protokoll. Gerechnet wird mit
  ihr erst, wenn der Eigentuemer sie im Kasten "Regelmodul" uebernimmt.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
from typing import Any, Mapping
import zipfile

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference import tax_model_plugin_v1 as base
from migrations.reference import tax_module_catalog_v1 as catalog
from migrations.reference.plugin_signature_v1 import PluginSignatureBlocked, verify_package_signature_v1

CONTRACT = "tax_module_install_v1"
PACKAGE_CONTRACT = "portelyra_plugin_package_v1"
SELFTEST_CONTRACT = "tax_module_selftest_v1"
SELFTEST_FILE = "selftest-scenarios.json"
LOG_NAME = "installations.sqlite"
# Nur Module, mit denen der Kern rechnen kann: die Familie des deutschen Moduls 2. Module anderer Laender kommen spaeter (#486).
SUPPORTED_PLUGIN_IDS = frozenset({"tax_de_personal_income_tax_projection_v2"})
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 200
_FILE_PART = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]{0,119}$")
SELFTEST_CONTEXT = base.TaxPluginContext("tenant_selftest", "user_selftest", "space_selftest", "actor_selftest")
FAILURE_CODES = (
    "tax_module_install_input_invalid", "tax_module_package_invalid", "tax_module_package_file_mismatch", "tax_module_unsupported",
    "tax_module_manifest_invalid", "tax_module_values_inconsistent", "tax_module_selftest_failed", "tax_module_already_installed",
    "tax_module_confirmation_required", "tax_module_preview_stale", "tax_module_install_store_invalid",
    "plugin_signature_missing", "plugin_signature_untrusted", "plugin_signature_invalid", "plugin_signature_tool_missing",
)


class TaxModuleInstallBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "tax_module_package_invalid"


def _abort(code: str) -> None:
    raise TaxModuleInstallBlocked(code)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- Entpacken
def _extract(zip_bytes: bytes, target: Path) -> list[str]:
    """Entpackt sicher: Groesse und Zahl begrenzt, keine Verknuepfungen, keine absoluten Pfade, kein "..", nur einfache Namen."""
    if not isinstance(zip_bytes, bytes) or not 0 < len(zip_bytes) <= MAX_ZIP_BYTES:
        _abort("tax_module_install_input_invalid")
    try:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        _abort("tax_module_package_invalid")
    names: list[str] = []
    total = 0
    with archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_ENTRIES:
            _abort("tax_module_package_invalid")
        for info in entries:
            mode = (info.external_attr >> 16) & 0o170000
            if info.is_dir():
                continue
            if mode and mode != stat.S_IFREG:
                _abort("tax_module_package_invalid")
            name = info.filename
            parts = PurePosixPath(name).parts
            if name.startswith("/") or "\\" in name or not parts or any(part in ("", ".", "..") or not _FILE_PART.fullmatch(part) for part in parts):
                _abort("tax_module_package_invalid")
            total += info.file_size
            if total > MAX_UNPACKED_BYTES or name in names:
                _abort("tax_module_package_invalid")
            destination = target.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with archive.open(info) as source:
                data = source.read(MAX_UNPACKED_BYTES + 1)
            if len(data) != info.file_size:
                _abort("tax_module_package_invalid")
            destination.write_bytes(data)
            os.chmod(destination, 0o600)
            names.append(name)
    return sorted(names)


# ---------------------------------------------------------------- Paket
def _package(staging: Path, names: list[str]) -> dict[str, Any]:
    """package.json: Art, Modul, Version und jede Datei mit Pruefsumme - genau die Dateien des Pakets, keine mehr, keine weniger."""
    if "package.json" not in names:
        _abort("tax_module_package_invalid")
    raw = (staging / "package.json").read_bytes()
    try:
        package = json.loads(raw)
    except (UnicodeError, ValueError):
        _abort("tax_module_package_invalid")
    if not isinstance(package, dict) or set(package) != {"contract_version", "kind", "plugin_id", "plugin_version", "files"} \
            or package["contract_version"] != PACKAGE_CONTRACT or package["kind"] != "tax_model" or not isinstance(package["files"], dict):
        _abort("tax_module_package_invalid")
    listed = set(package["files"])
    present = set(names) - {"package.json", "package.json.sig"}
    if listed != present:
        _abort("tax_module_package_file_mismatch")
    for name, expected in package["files"].items():
        if not isinstance(expected, str) or re.fullmatch(r"[a-f0-9]{64}", expected) is None or _sha((staging / name).read_bytes()) != expected:
            _abort("tax_module_package_file_mismatch")
    plugin_id = package["plugin_id"]
    if not isinstance(plugin_id, str) or any(not name.startswith(plugin_id + "/") for name in present):
        _abort("tax_module_package_invalid")
    return {**package, "_raw": raw, "_sha256": _sha(raw)}


# ---------------------------------------------------------------- Selbsttest
def run_tax_module_selftest_v1(plugin_root: str | Path, plugin_id: str) -> dict[str, Any]:
    """Rechnet die Szenarien des Pakets (Eingabe und erwartete Zeilen) mit genau dieser Fassung im abgeschotteten Modul.
    Ergebnis {"status": "passed"|"failed", "scenario_count", "failed": [Szenario-Codes]}."""
    from migrations.reference.tax_model_plugin_v2 import TaxPluginV2Blocked, run_tax_model_plugin_v2, tax_plugin_manifest_v2
    root = Path(plugin_root)
    path = root / plugin_id / SELFTEST_FILE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {"status": "failed", "scenario_count": 0, "failed": ["selftest_file_missing"]}
    scenarios = document.get("scenarios") if isinstance(document, dict) and document.get("contract_version") == SELFTEST_CONTRACT \
        and document.get("plugin_id") == plugin_id else None
    if not isinstance(scenarios, list) or not scenarios:
        return {"status": "failed", "scenario_count": 0, "failed": ["selftest_file_invalid"]}
    try:
        manifest = tax_plugin_manifest_v2(root)
    except TaxPluginV2Blocked:
        return {"status": "failed", "scenario_count": len(scenarios), "failed": ["manifest"]}
    failed: list[str] = []
    for scenario in scenarios:
        code = str(scenario.get("scenario_code") or "?")[:80] if isinstance(scenario, dict) else "?"
        try:
            bound = scenario["bound_input"]
            mode = bound["projection_mode"]
            selection_ref = "tsr_" + base.sha({"selftest": code})[:32]
            selection = base.TaxPluginSelection(selection_ref, 1, base.sha({"selection": selection_ref}), bound["portfolio_ref"], mode,
                                                manifest.plugin_id, manifest.plugin_version, manifest.rules_fingerprint,
                                                manifest.base_manifest.manifest_fingerprint, manifest.base_manifest.effective_from, "active")
            result = run_tax_model_plugin_v2(bound_input=bound, context=SELFTEST_CONTEXT, selection=selection, timeout_seconds=120,
                                             plugin_root=root)
            rows = list(result.rows)
            for expected in scenario["expected"]:
                key, fields = expected["key"], expected["fields"]
                hits = [row for row in rows if all(row.get(name) == value for name, value in key.items())]
                if len(hits) != 1 or any(hits[0].get(name) != value for name, value in fields.items()):
                    raise ValueError(code)
        except (KeyError, TypeError, ValueError, TaxPluginV2Blocked, base.TaxPluginBlocked):
            failed.append(code)
    return {"status": "passed" if not failed else "failed", "scenario_count": len(scenarios), "failed": failed}


# ---------------------------------------------------------------- Vorschau und Installation
def _context(value: Any) -> base.TaxPluginContext:
    try:
        return base.normalize_context(value)
    except base.TaxPluginBlocked:
        _abort("tax_module_install_input_invalid")


def _evaluate(space: Path, zip_bytes: bytes, staging: Path, trust_list: str | Path | None) -> dict[str, Any]:
    names = _extract(zip_bytes, staging)
    signature_bytes = (staging / "package.json.sig").read_bytes() if "package.json.sig" in names else None
    raw = (staging / "package.json").read_bytes() if "package.json" in names else b""
    problems: list[str] = []
    signature: dict[str, Any] = {"status": "missing"}
    try:
        verified = verify_package_signature_v1(raw, signature_bytes, trust_list)
        signature = {"status": "valid", "key": verified["key_sha256"][:16]}
    except PluginSignatureBlocked as error:
        signature = {"status": error.code}
        problems.append(error.code)
    public: dict[str, Any] = {"plugin_id": None, "plugin_version": None, "signature": signature, "selftest": None, "value_changes": [],
                              "rule_change_count": None, "already_installed": False, "problems": problems}
    package = _package(staging, names) if not problems else None
    if package is None:
        return {"public": public, "package": None, "manifest": None}
    plugin_id = package["plugin_id"]
    public.update(plugin_id=plugin_id, plugin_version=package["plugin_version"])
    if plugin_id not in SUPPORTED_PLUGIN_IDS:
        problems.append("tax_module_unsupported")
        return {"public": public, "package": package, "manifest": None}
    try:
        manifest = base.tax_plugin_manifest_v1(plugin_id, staging)
    except base.TaxPluginBlocked:
        problems.append("tax_module_manifest_invalid")
        return {"public": public, "package": package, "manifest": None}
    if manifest.plugin_version != package["plugin_version"]:
        problems.append("tax_module_manifest_invalid")
    if not catalog.embedded_values_consistent_v1(staging, plugin_id):
        problems.append("tax_module_values_inconsistent")
    existing = catalog.tax_module_catalog_v1(space)
    same = next((item for item in existing if item["plugin_id"] == plugin_id and item["plugin_version"] == manifest.plugin_version), None)
    if same is not None:
        public["already_installed"] = (same["rules_fingerprint"], same["manifest_fingerprint"]) == (manifest.rules_fingerprint, manifest.manifest_fingerprint)
        problems.append("tax_module_already_installed")
    if "tax_module_values_inconsistent" not in problems and "tax_module_manifest_invalid" not in problems:
        public["selftest"] = run_tax_module_selftest_v1(staging, plugin_id)
        if public["selftest"]["status"] != "passed":
            problems.append("tax_module_selftest_failed")
    # Unterschiede zur mitgelieferten Fassung desselben Moduls - dieselbe Rechnung wie "Neue Fassung verfuegbar".
    shipped = next((item for item in existing if item["plugin_id"] == plugin_id and item["origin"] == "shipped"), None)
    if shipped is not None:
        from migrations.reference.tax_ui_workspace_v1 import _module_diff
        changes, rule_changes = _module_diff(shipped, {"plugin_id": plugin_id, "plugin_root": str(staging)})
        public.update(value_changes=changes, rule_change_count=rule_changes, compared_with_version=shipped["plugin_version"])
    return {"public": public, "package": package, "manifest": manifest}


def _fingerprint(zip_bytes: bytes, public: Mapping[str, Any]) -> str:
    return base.sha({"zip": _sha(zip_bytes), "public": {key: value for key, value in public.items() if key != "preview_fingerprint"}})


def preview_tax_module_install_v1(data_space: str | Path, context_value: Any, zip_bytes: bytes, trust_list: str | Path | None = None) -> dict[str, Any]:
    """Was die Installation dieses Pakets taete - mit Grund, falls nicht. Schreibt nichts."""
    _context(context_value)
    space = Path(data_space)
    with tempfile.TemporaryDirectory(prefix=".portelyra-tax-module-") as temporary:
        staging = Path(temporary)
        os.chmod(staging, 0o700)
        evaluated = _evaluate(space, zip_bytes, staging, trust_list)
    public = dict(evaluated["public"])
    public["installable"] = not public["problems"]
    public["preview_fingerprint"] = _fingerprint(zip_bytes, public)
    return {"contract_version": CONTRACT, **public, "canonical_write": False, "network_access": False}


_LOG_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS tax_module_installation(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, context_fingerprint TEXT NOT NULL,"
    " plugin_id TEXT NOT NULL, plugin_version TEXT NOT NULL, rules_fingerprint TEXT NOT NULL CHECK(length(rules_fingerprint)=64),"
    " manifest_fingerprint TEXT NOT NULL CHECK(length(manifest_fingerprint)=64), package_sha256 TEXT NOT NULL CHECK(length(package_sha256)=64),"
    " signature_key TEXT NOT NULL, selftest_json TEXT NOT NULL, relative_dir TEXT NOT NULL, actor_id TEXT NOT NULL, installed_at_utc TEXT NOT NULL) STRICT",
    "CREATE TRIGGER IF NOT EXISTS tax_module_installation_no_update BEFORE UPDATE ON tax_module_installation BEGIN SELECT RAISE(ABORT,'tax_module_installation_immutable'); END",
    "CREATE TRIGGER IF NOT EXISTS tax_module_installation_no_delete BEFORE DELETE ON tax_module_installation BEGIN SELECT RAISE(ABORT,'tax_module_installation_immutable'); END",
)


def _record(space: Path, context: base.TaxPluginContext, row: tuple) -> None:
    path = space / catalog.AREA / LOG_NAME
    if path.is_symlink():
        _abort("tax_module_install_store_invalid")
    try:
        connection = sqlite3.connect(path)
        try:
            with connection:
                for statement in _LOG_SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO tax_module_installation(context_fingerprint,plugin_id,plugin_version,rules_fingerprint,manifest_fingerprint,"
                                   "package_sha256,signature_key,selftest_json,relative_dir,actor_id,installed_at_utc) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                   (base.context_fingerprint(context), *row))
        finally:
            connection.close()
        os.chmod(path, 0o600)
    except sqlite3.Error as error:
        raise TaxModuleInstallBlocked("tax_module_install_store_invalid") from error


def apply_tax_module_install_v1(data_space: str | Path, context_value: Any, zip_bytes: bytes, preview_fingerprint: str, confirmed: Any,
                                installed_at_utc: str, trust_list: str | Path | None = None) -> dict[str, Any]:
    """Installiert genau die gezeigte Vorschau: prueft alles erneut, legt die Fassung im Datenraum ab und vermerkt sie im Protokoll."""
    context = _context(context_value)
    if confirmed is not True:
        _abort("tax_module_confirmation_required")
    try:
        datetime.strptime(installed_at_utc, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        _abort("tax_module_install_input_invalid")
    space = Path(data_space)
    if not space.is_dir() or space.is_symlink():
        _abort("tax_module_install_input_invalid")
    with tempfile.TemporaryDirectory(prefix=".portelyra-tax-module-") as temporary:
        staging = Path(temporary)
        os.chmod(staging, 0o700)
        evaluated = _evaluate(space, zip_bytes, staging, trust_list)
        public = dict(evaluated["public"])
        public["installable"] = not public["problems"]
        if _fingerprint(zip_bytes, public) != preview_fingerprint:
            _abort("tax_module_preview_stale")
        if public["problems"]:
            _abort(public["problems"][0])
        manifest = evaluated["manifest"]
        plugin_id = manifest.plugin_id
        relative = Path(catalog.AREA) / plugin_id / catalog.version_directory_name_v1(manifest.plugin_version, manifest.rules_fingerprint)
        target = space / relative
        for directory in (space / catalog.AREA, space / catalog.AREA / plugin_id):
            if directory.is_symlink():
                _abort("tax_module_install_store_invalid")
            directory.mkdir(mode=0o700, exist_ok=True)
        if target.exists():
            _abort("tax_module_already_installed")
        moving = Path(tempfile.mkdtemp(prefix=".kopie-", dir=space / catalog.AREA / plugin_id))
        try:
            shutil.copytree(staging / plugin_id, moving / plugin_id, symlinks=False)
            catalog._private_tree(moving)
            checked = base.tax_plugin_manifest_v1(plugin_id, moving)
            if (checked.rules_fingerprint, checked.manifest_fingerprint) != (manifest.rules_fingerprint, manifest.manifest_fingerprint):
                _abort("tax_module_manifest_invalid")
            settle_new_directory_v1(moving)  # #568: auch die gocryptfs.diriv neuer Ordner festschreiben
            os.replace(moving, target)
        finally:
            if moving.exists():
                shutil.rmtree(moving, ignore_errors=True)
        _record(space, context, (plugin_id, manifest.plugin_version, manifest.rules_fingerprint, manifest.manifest_fingerprint,
                                 evaluated["package"]["_sha256"], public["signature"].get("key", ""), json.dumps(public["selftest"], sort_keys=True),
                                 relative.as_posix(), context.actor_id, installed_at_utc))
    return {"contract_version": CONTRACT, "status": "installed", "plugin_id": plugin_id, "plugin_version": manifest.plugin_version,
            "canonical_write": False, "network_access": False}


__all__ = ["CONTRACT", "FAILURE_CODES", "SELFTEST_FILE", "SUPPORTED_PLUGIN_IDS", "TaxModuleInstallBlocked", "apply_tax_module_install_v1",
           "preview_tax_module_install_v1", "run_tax_module_selftest_v1"]
