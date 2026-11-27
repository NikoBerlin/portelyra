#!/usr/bin/env python3
"""Plugin-Pakete (#486 Schritt 3): ein Ordner mit `package.json` (jede Datei des Plugins mit SHA-256), wahlweise signiert
(`package.json.sig`, Vertrag contracts/plugin-signing/v1), und dem Plugin-Ordner `<plugin_id>/`. Gleiches Format wie die Steuermodul-Pakete
(contracts/tax-module-package/v1); hier fuer Leser und Kursanbieter, die auch unsigniert gehen (dann "ungeprueft").

Festlegungen vom 16.11.2026: Ein mitgeliefertes Plugin loest nur ein von Portelyra signiertes Update mit hoeherer
Version ab; unsignierte Pakete nur unter eigener Kennung. Liest nur.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any
import zipfile

from migrations.reference import plugin_signature_v1 as signature

CONTRACT = "portelyra_plugin_package_v1"
KINDS = frozenset({"tax_model", "statement_reader", "price_provider"})
PACKAGE_FILE = "package.json"
SIGNATURE_FILE = "package.json.sig"
MAX_PACKAGE_BYTES = 1_000_000
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_ENTRIES = 300
_PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_VERSION = re.compile(r"^[0-9]{1,4}(\.[0-9]{1,4}){1,3}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")


class PluginPackageBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def version_tuple_v1(value: Any) -> tuple[int, ...] | None:
    """"1.10.0" -> (1, 10, 0); alles andere -> None (gilt nie als hoeher)."""
    if not isinstance(value, str) or _VERSION.match(value) is None:
        return None
    return tuple(int(part) for part in value.split("."))


def newer_v1(candidate: Any, current: Any) -> bool:
    left, right = version_tuple_v1(candidate), version_tuple_v1(current)
    if left is None or right is None:
        return False
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)) > right + (0,) * (width - len(right))


def is_package_v1(root: Path) -> bool:
    return (root / PACKAGE_FILE).is_file() and not (root / PACKAGE_FILE).is_symlink()


def _files(directory: Path, base: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(base)
        if "__pycache__" in relative.parts:
            continue        # Python legt sie beim Laden an; nie Teil eines Pakets
        if path.is_symlink():
            raise PluginPackageBlocked("plugin_package_invalid")
        if path.is_file():
            found[relative.as_posix()] = path
    return found


def inspect_package_v1(root: Path, *, kind: str, trust_list: str | Path | None = None) -> dict[str, Any]:
    """Prueft ein ausgepacktes Paket: Aufbau, genau die genannten Dateien mit ihrer Pruefsumme, Art und Kennung. Die Signatur ist kein
    Abbruchgrund, sondern ein Befund: "valid", "unsigned" oder der Code der Signaturpruefung (der Aufrufer entscheidet, was er zulaesst)."""
    if kind not in KINDS:
        raise PluginPackageBlocked("plugin_package_invalid")
    package_path, signature_path = root / PACKAGE_FILE, root / SIGNATURE_FILE
    if not is_package_v1(root) or package_path.stat().st_size > MAX_PACKAGE_BYTES or signature_path.is_symlink():
        raise PluginPackageBlocked("plugin_package_invalid")
    package_bytes = package_path.read_bytes()
    try:
        package = json.loads(package_bytes.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise PluginPackageBlocked("plugin_package_invalid") from error
    if not isinstance(package, dict) or package.get("contract_version") != CONTRACT or package.get("kind") != kind:
        raise PluginPackageBlocked("plugin_package_invalid")
    plugin_id, version, files = package.get("plugin_id"), package.get("plugin_version"), package.get("files")
    if not isinstance(plugin_id, str) or _PLUGIN_ID.match(plugin_id) is None or version_tuple_v1(version) is None or not isinstance(files, dict) \
            or not files:
        raise PluginPackageBlocked("plugin_package_invalid")
    for relative, digest in files.items():
        parts = PurePosixPath(relative).parts if isinstance(relative, str) else ()
        if len(parts) < 2 or parts[0] != plugin_id or any(part in ("", ".", "..") for part in parts) or not isinstance(digest, str) \
                or _SHA.match(digest) is None:
            raise PluginPackageBlocked("plugin_package_invalid")
    allowed_top = {PACKAGE_FILE, SIGNATURE_FILE, plugin_id}
    if any(entry.name not in allowed_top for entry in root.iterdir()) or not (root / plugin_id).is_dir() or (root / plugin_id).is_symlink():
        raise PluginPackageBlocked("plugin_package_invalid")
    present = _files(root / plugin_id, root)
    if set(present) != set(files) or any(hashlib.sha256(present[relative].read_bytes()).hexdigest() != files[relative] for relative in files):
        raise PluginPackageBlocked("plugin_package_file_mismatch")
    if signature_path.is_file():
        try:
            checked = signature.verify_package_signature_v1(package_bytes, signature_path.read_bytes(), trust_list)
            found = {"status": "valid", "key_sha256": checked["key_sha256"]}
        except signature.PluginSignatureBlocked as error:
            found = {"status": error.code}
    else:
        found = {"status": "unsigned"}
    return {"kind": kind, "plugin_id": plugin_id, "plugin_version": version, "plugin_dir": root / plugin_id, "signature": found}


def safe_extract_v1(zip_bytes: bytes, target: Path) -> Path:
    """Entpackt ein Paket sicher nach `target/paket` (neu, 0700): keine Verknuepfungen, Geraete oder Pfade nach aussen, Groessengrenzen;
    ein einziger Oberordner wird abgestreift. Liefert den Ordner mit package.json."""
    if not isinstance(zip_bytes, (bytes, bytearray)) or not zip_bytes or len(zip_bytes) > MAX_ZIP_BYTES:
        raise PluginPackageBlocked("plugin_package_too_large" if zip_bytes and len(zip_bytes) > MAX_ZIP_BYTES else "plugin_package_invalid")
    try:
        archive = zipfile.ZipFile(io.BytesIO(bytes(zip_bytes)))
        infos = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError, RuntimeError) as error:
        raise PluginPackageBlocked("plugin_package_invalid") from error
    if not infos or len(infos) > MAX_ENTRIES or sum(info.file_size for info in infos) > MAX_UNPACKED_BYTES:
        raise PluginPackageBlocked("plugin_package_too_large")
    names = []
    for info in infos:
        kind = stat.S_IFMT((info.external_attr >> 16) & 0o177777)
        path = PurePosixPath(info.filename)
        if kind not in (0, stat.S_IFREG, stat.S_IFDIR) or "\\" in info.filename or info.filename.startswith("/") or path.is_absolute() \
                or any(part in ("..", "") for part in path.parts if part != ".") or (path.parts and ":" in path.parts[0]) \
                or any(ord(char) < 32 for char in info.filename):
            raise PluginPackageBlocked("plugin_package_unsafe")
        names.append((info, path))
    tops = {path.parts[0] for _info, path in names if path.parts}
    strip = len(tops) == 1 and not any(len(path.parts) == 1 and not info.is_dir() for info, path in names)
    root = target / "paket"
    root.mkdir(mode=0o700)
    for info, path in names:
        parts = path.parts[1:] if strip else path.parts
        if not parts or "__pycache__" in parts:
            continue
        destination = root.joinpath(*parts)
        if info.is_dir():
            destination.mkdir(mode=0o700, parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            data = archive.read(info)
        except (zipfile.BadZipFile, OSError, RuntimeError, ValueError) as error:
            raise PluginPackageBlocked("plugin_package_invalid") from error
        if len(data) != info.file_size:
            raise PluginPackageBlocked("plugin_package_invalid")
        with destination.open("xb") as handle:
            handle.write(data)
        destination.chmod(0o600)
    if not is_package_v1(root):
        raise PluginPackageBlocked("plugin_package_invalid")
    return root


def build_package_manifest_v1(root: Path, *, kind: str, plugin_id: str, plugin_version: str) -> bytes:
    """package.json zu einem Ordner `<root>/<plugin_id>/` (Entwicklerwerkzeuge und Tests)."""
    files = {relative: hashlib.sha256(path.read_bytes()).hexdigest() for relative, path in _files(root / plugin_id, root).items()}
    document = {"contract_version": CONTRACT, "kind": kind, "plugin_id": plugin_id, "plugin_version": plugin_version, "files": files}
    return (json.dumps(document, indent=1, sort_keys=True) + "\n").encode("utf-8")


__all__ = ["CONTRACT", "KINDS", "PACKAGE_FILE", "PluginPackageBlocked", "SIGNATURE_FILE", "build_package_manifest_v1", "inspect_package_v1",
           "is_package_v1", "newer_v1", "safe_extract_v1", "version_tuple_v1"]
