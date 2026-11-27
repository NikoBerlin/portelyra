#!/usr/bin/env python3
"""Gemeinsamer Plugin-Verwalter (#486 Schritt 3, Festlegung 16.11.2026: Daten -> Einstellungen -> "Plugins").

Eine Liste ueber Leser, Kursanbieter und Steuermodule - Version, mitgeliefert oder installiert, von Portelyra signiert oder ungeprueft,
aktiv - und die Art eines Pakets, damit ein gemeinsames "Paket installieren" die passende Pruefung startet. Die Einzelheiten (Pruefstand
der Leser, Aktivieren der Kursanbieter, Fassung des Steuermoduls) bleiben in ihren Reitern. Liest nur; die Uebersichten der Leser und
Kursanbieter halten hoechstens ihren einmaligen Bestandseintrag fest, wie beim Oeffnen ihrer Reiter.
"""
from __future__ import annotations

import io
import json
from pathlib import Path, PurePosixPath
from typing import Any
import zipfile

MAX_ZIP_BYTES = 10 * 1024 * 1024
KINDS = ("statement_reader", "price_provider", "tax_model")


class PluginManagerBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def package_kind_v1(zip_bytes: bytes) -> dict[str, Any]:
    """Welche Art Plugin eine ZIP-Datei enthaelt, ohne sie zu entpacken: aus package.json (an der Wurzel oder unter einem einzigen
    Oberordner); ohne package.json, aber mit manifest.json: ein Leser-Plugin im bisherigen Format (unsigniert)."""
    if not isinstance(zip_bytes, (bytes, bytearray)) or not zip_bytes or len(zip_bytes) > MAX_ZIP_BYTES:
        raise PluginManagerBlocked("plugin_package_unreadable")
    try:
        with zipfile.ZipFile(io.BytesIO(bytes(zip_bytes))) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
            paths = [PurePosixPath(name) for name in names]
            tops = {path.parts[0] for path in paths if path.parts}
            prefix = next(iter(tops)) + "/" if len(tops) == 1 and all(len(path.parts) > 1 for path in paths) else ""
            if f"{prefix}package.json" in names:
                info = archive.getinfo(f"{prefix}package.json")
                if info.file_size > 1_000_000:
                    raise PluginManagerBlocked("plugin_package_unreadable")
                package = json.loads(archive.read(info).decode("utf-8"))
                kind = package.get("kind") if isinstance(package, dict) else None
                return {"kind": kind if kind in KINDS else "unknown", "packaged": True, "signed": f"{prefix}package.json.sig" in names,
                        "plugin_id": package.get("plugin_id") if isinstance(package, dict) else None,
                        "plugin_version": package.get("plugin_version") if isinstance(package, dict) else None}
            if any(path.name == "manifest.json" for path in paths):
                return {"kind": "statement_reader", "packaged": False, "signed": False, "plugin_id": None, "plugin_version": None}
    except (zipfile.BadZipFile, OSError, ValueError, UnicodeError, KeyError, RuntimeError) as error:
        raise PluginManagerBlocked("plugin_package_unreadable") from error
    return {"kind": "unknown", "packaged": False, "signed": False, "plugin_id": None, "plugin_version": None}


def _reader_signature(space: Path, plugin_id: str) -> str:
    """Installiertes Leser-Plugin: "signed", wenn neben seinem Ordner ein gueltig signiertes Paket liegt, sonst "unchecked"."""
    from migrations.reference import plugin_package_v1 as package_module  # noqa: PLC0415
    from migrations.reference import statement_reader_admin_v1 as admin  # noqa: PLC0415
    relative = admin._installed_pointer(space).get(plugin_id)
    if not relative:
        return "unchecked"
    try:
        package = package_module.inspect_package_v1((space / admin.AREA / relative).parent, kind="statement_reader")
    except package_module.PluginPackageBlocked:
        return "unchecked"
    return "signed" if package["signature"]["status"] == "valid" else "unchecked"


def _provider_signature(space: Path, plugin_id: str) -> str:
    """Installierter Kursanbieter: "signed" mit gueltig signiertem Paket neben seinem Ordner, sonst "unchecked"."""
    from migrations.reference import plugin_package_v1 as package_module  # noqa: PLC0415
    from migrations.reference import price_provider_install_v1 as install  # noqa: PLC0415
    relative = install._pointer(space).get(plugin_id)
    if not relative:
        return "unchecked"
    try:
        package = package_module.inspect_package_v1((space / install.AREA / relative).parent, kind="price_provider")
    except package_module.PluginPackageBlocked:
        return "unchecked"
    return "signed" if package["signature"]["status"] == "valid" else "unchecked"


def _tax_installed(space: Path, area: str) -> set[tuple[str, str]]:
    """Aus einer Datei installierte Steuermodul-Fassungen (nur anhaengendes Protokoll, rc.422): (Version, Manifest-Pruefsumme)."""
    import sqlite3  # noqa: PLC0415
    log = space / area / "installations.sqlite"
    if not log.is_file() or log.is_symlink():
        return set()
    try:
        with sqlite3.connect(f"file:{log}?mode=ro", uri=True) as connection:
            return {(row[0], row[1]) for row in connection.execute("SELECT plugin_version, manifest_fingerprint FROM tax_module_installation")}
    except sqlite3.Error:
        return set()


def overview_v1(space: str | Path, context: Any) -> dict[str, Any]:
    """Je Plugin eine Zeile: Art, Name, Version, Herkunft, Signatur, Zustand. Fehlt eine Art (nicht lesbar), steht ihr Grund dabei."""
    space = Path(space)
    rows: list[dict[str, Any]] = []
    problems: list[dict[str, str]] = []
    try:
        from migrations.reference import statement_reader_admin_v1 as admin  # noqa: PLC0415
        activation = admin.activation_v1(space, context)
        portfolios = len(activation.get("portfolios") or [])
        for plugin in activation.get("plugins") or []:
            active = sum(1 for state in plugin.get("states") or [] if state.get("active"))
            installed = plugin.get("origin") == "installed"
            rows.append({"kind": "statement_reader", "plugin_id": plugin["plugin_id"], "label": plugin.get("label") or plugin["plugin_id"],
                         "plugin_version": plugin.get("plugin_version"), "origin": "update" if plugin.get("replaces_shipped") else plugin.get("origin"),
                         "replaces_shipped": plugin.get("replaces_shipped"),
                         "signature": _reader_signature(space, plugin["plugin_id"]) if installed else "shipped",
                         "active_count": active, "portfolio_count": portfolios})
    except Exception as error:  # noqa: BLE001 - eine nicht lesbare Art verdeckt die anderen nicht
        problems.append({"kind": "statement_reader", "code": getattr(error, "code", "plugin_manager_part_unreadable")})
    try:
        from migrations.reference import price_provider_admin_v1 as provider_admin  # noqa: PLC0415
        for provider in provider_admin.overview_v1(space, context)["providers"]:
            installed = provider["origin"] == "installed"
            rows.append({"kind": "price_provider", "plugin_id": provider["plugin_id"], "label": provider["label"], "plugin_version": provider["plugin_version"],
                         "origin": "update" if provider.get("replaces_shipped") else provider["origin"], "replaces_shipped": provider.get("replaces_shipped"),
                         "signature": _provider_signature(space, provider["plugin_id"]) if installed else "shipped",
                         "active": bool(provider["active"]), "state": provider["state"]})
    except Exception as error:  # noqa: BLE001
        problems.append({"kind": "price_provider", "code": getattr(error, "code", "plugin_manager_part_unreadable")})
    try:
        from migrations.reference import tax_module_catalog_v1 as catalog  # noqa: PLC0415
        entries = catalog.tax_module_catalog_v1(space)
        shipped = {entry["manifest_fingerprint"] for entry in entries if entry["origin"] == "shipped"}
        installed = _tax_installed(space, catalog.AREA)
        for entry in entries:
            if entry["origin"] != "shipped" and entry["manifest_fingerprint"] in shipped:
                continue        # gesicherte Kopie einer mitgelieferten Fassung (#486 Schritt 2): dieselbe Fassung, keine eigene Zeile
            from_file = (entry["plugin_version"], entry["manifest_fingerprint"]) in installed
            rows.append({"kind": "tax_model", "plugin_id": entry["plugin_id"], "label": entry["plugin_id"], "plugin_version": entry["plugin_version"],
                         "origin": "shipped" if entry["origin"] == "shipped" else ("installed" if from_file else "preserved"),
                         "replaces_shipped": None, "signature": "signed" if from_file else "shipped"})
    except Exception as error:  # noqa: BLE001
        problems.append({"kind": "tax_model", "code": getattr(error, "code", "plugin_manager_part_unreadable")})
    order = {kind: index for index, kind in enumerate(KINDS)}
    rows.sort(key=lambda row: (order[row["kind"]], str(row["label"]).lower(), str(row["plugin_version"])))
    return {"contract_version": "plugin_manager_overview_v1", "plugins": rows, "problems": problems}


__all__ = ["PluginManagerBlocked", "overview_v1", "package_kind_v1"]
