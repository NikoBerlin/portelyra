"""Kursanbieter als Plugins (price_provider_v1, #495, rc.382).

Festlegungen vom 09.11.2026 (#495, #546): Netz nur im Kern. Ein Kursanbieter-Plugin baut Anfragen und liest
Antworten in derselben Sandbox wie die Leser (Landlock, kein Netz, Ressourcengrenzen); abgerufen wird hier, nur an die Hosts aus dem
Manifest, ohne Weiterleitung, mit Zeitlimit und Groessengrenze. Jede Ausgabe des Plugins prueft der Kern vollstaendig, bevor sie
weitergeht; ein Plugin kann nichts schreiben, nichts abrufen und keinen Schluessel sehen.

Mitgeliefert ist Yahoo Finance (``plugins/price_providers/yahoo``). Die Auswertungen standen bis rc.381 im Kern; die bisherigen
Funktionen (``desktop_provider_probe_v1._parse_response`` usw.) reichen jetzt an das Plugin weiter.
"""
from __future__ import annotations

import atexit
import contextlib
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, InvalidOperation
import functools
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "price_providers"
HOST = ROOT / "workers" / "price_provider_host_v1.py"
SANDBOX = ROOT / "workers" / "import_plugin_sandbox_v1.py"
API_VERSION = "price_provider_v1"
# Stufe 1 (rc.389, #546): Zugaenge im Manifest und die Operation "credential_check". Plugins ohne Zugang bleiben bei Stufe 0.
API_MINOR = 1
CREDENTIAL_API_MINOR = 1
OPERATIONS = ("daily_history", "fx_daily_history", "quote", "search", "fx_symbol", "credential_check")
COSTS = ("free", "free_quota", "paid")
TIMEOUT_SECONDS = 60
MAX_RESULT_BYTES = 16 * 1024 * 1024
MAX_DAYS = 20_000
FETCH_TIMEOUT_SECONDS = 15
FETCH_BYTE_LIMIT = 1_048_576
ERROR_CODES = frozenset({
    "price_provider_unavailable", "price_provider_manifest_invalid", "price_provider_entry_mismatch",
    "price_provider_api_version_unsupported", "price_provider_isolation_unavailable", "price_provider_failed",
    "price_provider_output_invalid", "price_provider_timeout", "price_provider_host_not_allowed",
    "price_provider_transport_failed", "price_provider_response_too_large", "price_provider_operation_unsupported",
})

_PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_PROVIDER_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_VERSION = re.compile(r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$")
_FILE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_MODULE = re.compile(r"^[A-Za-z0-9_]{1,60}\.py$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
_TARGET = re.compile(r"^/[\x21-\x7e]{0,4095}$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_URL = re.compile(r"^https://[\x21-\x7e]{4,300}$")
_CREDENTIAL_NAME = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_HEADER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")
_QUERY_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_PREFIX = re.compile(r"^(?:[A-Za-z]{1,20} )?$")
# Kopfzeilen, die der Kern selbst setzt oder die eine Verbindung umlenken koennten: nie fuer einen Zugang.
_RESERVED_HEADERS = frozenset({"host", "content-length", "content-type", "connection", "transfer-encoding", "cookie", "user-agent", "accept",
                               "accept-encoding", "te", "upgrade", "proxy-authorization", "forwarded", "x-forwarded-for", "x-forwarded-host"})


@dataclass(frozen=True)
class CredentialField:
    """Ein Feld eines Zugangs laut Manifest (#546). Den Wert setzt der Kern in die Anfrage, nur als Kopfzeile oder Parameter, nie im Pfad;
    das Plugin sieht ihn nie."""
    name: str
    label: str
    secret: bool
    hint: str
    url: str | None
    placement_kind: str
    placement_key: str
    placement_prefix: str

    def public(self) -> dict[str, Any]:
        return {"name": self.name, "label": self.label, "secret": self.secret, "hint": self.hint, "url": self.url,
                "placement": {"kind": self.placement_kind, "key": self.placement_key, "prefix": self.placement_prefix}}


class PriceProviderBlocked(RuntimeError):
    def __init__(self, code: str):
        if code not in ERROR_CODES:
            code = "price_provider_failed"
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ProviderSpec:
    plugin_id: str
    plugin_version: str
    provider_id: str
    label: str
    publisher: str
    plugin_dir: Path
    entry: Path
    entry_sha256: str
    modules: tuple[tuple[Path, str], ...]
    operations: tuple[str, ...]
    hosts: tuple[str, ...]
    cost: str
    credentials: tuple[CredentialField, ...]
    terms_url: str
    history_max_days: int
    fixtures: tuple[tuple[str, str], ...]
    manifest_sha256: str
    generator: bool = False
    origin: str = "shipped"   # "shipped" (mitgeliefert) oder "installed" (aus einem Paket, #486 Schritt 3)
    replaces_shipped: str | None = None   # Update eines mitgelieferten Anbieters: dessen Version, sonst None


def _text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and value == value.strip() and 1 <= len(value) <= limit and not any(ord(c) < 32 or ord(c) == 127 for c in value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(directory: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative or relative.startswith("/") or "\\" in relative or ".." in Path(relative).parts:
        return None
    path = directory / relative
    try:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):
            return None
    except OSError:
        return None
    return path


def _credential_fields(value: Any, minor: int) -> tuple[CredentialField, ...]:
    """Felder eines Zugangs (#546): hoechstens vier, je Name und Stelle eindeutig, nur ab Stufe 1 der Schnittstelle."""
    if not isinstance(value, list) or len(value) > 4 or (value and minor < CREDENTIAL_API_MINOR):
        raise PriceProviderBlocked("price_provider_manifest_invalid")
    fields: list[CredentialField] = []
    names: set[str] = set()
    places: set[tuple[str, str]] = set()
    for item in value:
        placement = item.get("placement") if isinstance(item, Mapping) else None
        if not (isinstance(item, Mapping) and set(item) == {"name", "label", "secret", "hint", "url", "placement"}
                and isinstance(item["name"], str) and _CREDENTIAL_NAME.match(item["name"]) and _text(item["label"], 60)
                and isinstance(item["secret"], bool) and _text(item["hint"], 300)
                and (item["url"] is None or (isinstance(item["url"], str) and _URL.match(item["url"])))
                and isinstance(placement, Mapping) and set(placement) == {"kind", "key", "prefix"} and placement["kind"] in ("header", "query")
                and isinstance(placement["key"], str) and isinstance(placement["prefix"], str) and _PREFIX.match(placement["prefix"])):
            raise PriceProviderBlocked("price_provider_manifest_invalid")
        kind, key = placement["kind"], placement["key"]
        if kind == "header":
            valid = _HEADER_NAME.match(key) is not None and key.lower() not in _RESERVED_HEADERS
        else:
            valid = _QUERY_KEY.match(key) is not None and placement["prefix"] == ""
        if not valid or item["name"] in names or (kind, key.lower()) in places:
            raise PriceProviderBlocked("price_provider_manifest_invalid")
        names.add(item["name"])
        places.add((kind, key.lower()))
        fields.append(CredentialField(item["name"], item["label"], item["secret"], item["hint"], item["url"], kind, key, placement["prefix"]))
    return tuple(fields)


def _manifest_spec(directory: Path, manifest_path: Path) -> ProviderSpec:
    """Prueft ein Manifest vollstaendig; jede Abweichung verwirft das ganze Plugin."""
    try:
        raw = manifest_path.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise PriceProviderBlocked("price_provider_manifest_invalid") from error
    top = {"api_version", "api_minor", "plugin_id", "plugin_version", "provider_id", "label", "publisher", "entry_point",
           "entry_point_sha256", "modules", "operations", "hosts", "cost", "credentials", "terms_url", "history_max_days",
           "generator", "fixtures"}
    if not isinstance(manifest, Mapping) or set(manifest) != top:
        raise PriceProviderBlocked("price_provider_manifest_invalid")
    if manifest["api_version"] != API_VERSION:
        raise PriceProviderBlocked("price_provider_api_version_unsupported")
    minor = manifest["api_minor"]
    if not isinstance(minor, int) or isinstance(minor, bool) or minor < 0:
        raise PriceProviderBlocked("price_provider_manifest_invalid")
    if minor > API_MINOR:
        raise PriceProviderBlocked("price_provider_api_version_unsupported")
    operations = manifest["operations"]
    hosts = manifest["hosts"]
    credentials = manifest["credentials"]
    if not (isinstance(manifest["plugin_id"], str) and _PLUGIN_ID.match(manifest["plugin_id"]) and manifest["plugin_id"] == directory.name
            and isinstance(manifest["plugin_version"], str) and _VERSION.match(manifest["plugin_version"])
            and isinstance(manifest["provider_id"], str) and _PROVIDER_ID.match(manifest["provider_id"])
            and _text(manifest["label"], 120) and _text(manifest["publisher"], 80)
            and isinstance(manifest["entry_point"], str) and _FILE.match(manifest["entry_point"]) and manifest["entry_point"].endswith(".py")
            and isinstance(manifest["entry_point_sha256"], str) and _SHA.match(manifest["entry_point_sha256"])
            and isinstance(operations, list) and operations and len(set(operations)) == len(operations) and all(item in OPERATIONS for item in operations)
            and isinstance(hosts, list) and hosts and len(set(hosts)) == len(hosts) and all(isinstance(item, str) and _HOSTNAME.match(item) for item in hosts)
            and manifest["cost"] in COSTS
            and isinstance(manifest["terms_url"], str) and _URL.match(manifest["terms_url"])
            and isinstance(manifest["history_max_days"], int) and not isinstance(manifest["history_max_days"], bool)
            and 0 <= manifest["history_max_days"] <= MAX_DAYS
            and isinstance(manifest["generator"], bool)):
        raise PriceProviderBlocked("price_provider_manifest_invalid")
    credential_fields = _credential_fields(credentials, minor)
    # Die Pruefung eines Zugangs gibt es nur mit Zugang.
    if "credential_check" in operations and not credential_fields:
        raise PriceProviderBlocked("price_provider_manifest_invalid")
    entry = _inside(directory, manifest["entry_point"])
    if entry is None or _sha256(entry) != manifest["entry_point_sha256"]:
        raise PriceProviderBlocked("price_provider_entry_mismatch")
    modules = manifest["modules"]
    if not isinstance(modules, list) or not all(isinstance(item, Mapping) and set(item) == {"path", "sha256"} and isinstance(item["path"], str)
                                                and _MODULE.match(item["path"]) and isinstance(item["sha256"], str) and _SHA.match(item["sha256"])
                                                for item in modules):
        raise PriceProviderBlocked("price_provider_manifest_invalid")
    module_files: list[tuple[Path, str]] = []
    for item in modules:
        path = _inside(directory, item["path"])
        if path is None or path == entry or _sha256(path) != item["sha256"]:
            raise PriceProviderBlocked("price_provider_entry_mismatch")
        module_files.append((path, item["sha256"]))
    # Code, den das Manifest nicht nennt, verwirft das Plugin: Was laeuft, ist geprueft.
    listed = {entry.name} | {path.name for path, _sha in module_files}
    code = {str(path.relative_to(directory)) for path in directory.rglob("*.py") if "__pycache__" not in path.parts}
    if code != listed or len(listed) != 1 + len(module_files):
        raise PriceProviderBlocked("price_provider_entry_mismatch")
    fixtures = manifest["fixtures"]
    if not isinstance(fixtures, list) or not fixtures:
        raise PriceProviderBlocked("price_provider_manifest_invalid")
    pairs: list[tuple[str, str]] = []
    for fixture in fixtures:
        if not (isinstance(fixture, Mapping) and set(fixture) == {"input", "expected"}
                and str(fixture["input"]).startswith("fixtures/") and str(fixture["expected"]).startswith("fixtures/")
                and _inside(directory, fixture["input"]) is not None and _inside(directory, fixture["expected"]) is not None):
            raise PriceProviderBlocked("price_provider_manifest_invalid")
        pairs.append((fixture["input"], fixture["expected"]))
    return ProviderSpec(
        plugin_id=manifest["plugin_id"], plugin_version=manifest["plugin_version"], provider_id=manifest["provider_id"],
        label=manifest["label"], publisher=manifest["publisher"], plugin_dir=directory, entry=entry,
        entry_sha256=manifest["entry_point_sha256"], modules=tuple(module_files), operations=tuple(operations), hosts=tuple(hosts),
        cost=manifest["cost"], credentials=credential_fields, terms_url=manifest["terms_url"],
        history_max_days=manifest["history_max_days"], fixtures=tuple(pairs), manifest_sha256=hashlib.sha256(raw).hexdigest(),
        generator=manifest["generator"])


_PROBLEMS: list[dict[str, str]] = []


# Installierte Kursanbieter (#486 Schritt 3): im Datenraum unter price-provider-plugins-v1, Zeiger installed.json (plugin_id -> Ordner).
# Den Ort setzen die Data-App und "Alles aktualisieren" fuer alle ihre Unterprozesse; ohne ihn gibt es nur die mitgelieferten.
INSTALLED_ROOT_ENV = "PORTELYRA_INSTALLED_PRICE_PROVIDERS"
INSTALLED_AREA = "price-provider-plugins-v1"
_SIGNED_CACHE: dict[tuple, str | None] = {}


def use_data_space_providers_v1(data_space_path: str | Path | None) -> None:
    """Installierte Kursanbieter dieses Datenraums laden (None: nur die mitgelieferten)."""
    if data_space_path is None:
        os.environ.pop(INSTALLED_ROOT_ENV, None)
    else:
        os.environ[INSTALLED_ROOT_ENV] = str(Path(data_space_path) / INSTALLED_AREA)


def _installed_directories() -> list[tuple[str, Path | None]]:
    root_text = os.environ.get(INSTALLED_ROOT_ENV)
    if not root_text:
        return []
    root = Path(root_text)
    pointer = root / "installed.json"
    if root.is_symlink() or not pointer.is_file() or pointer.is_symlink():
        return []
    try:
        mapping = json.loads(pointer.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return [("installed", None)]
    found: list[tuple[str, Path | None]] = []
    for plugin_id, relative in sorted(mapping.items()) if isinstance(mapping, dict) else []:
        path = root / relative if isinstance(relative, str) and not relative.startswith("/") and ".." not in Path(relative).parts else None
        if path is not None and (path.is_symlink() or not path.is_dir()):
            path = None
        found.append((plugin_id, path))
    return found


def _signed_update(directory: Path, plugin_id: str) -> str | None:
    """Version eines installierten Updates eines mitgelieferten Anbieters, wenn sein Paket (neben dem Plugin-Ordner) jetzt gueltig von
    Portelyra signiert ist und jede Datei stimmt; sonst None. Zwischengespeichert je Stand von Paket, Signatur und Vertrauensliste."""
    from migrations.reference import plugin_package_v1 as package_module  # noqa: PLC0415
    from migrations.reference import plugin_signature_v1 as signature  # noqa: PLC0415
    def stamp(path: Path) -> tuple:
        try:
            info = path.stat()
            return (str(path), info.st_mtime_ns, info.st_size)
        except OSError:
            return (str(path), None, None)
    key = (str(directory), stamp(directory.parent / "package.json"), stamp(directory.parent / "package.json.sig"), stamp(Path(signature.TRUST_LIST)))
    if key not in _SIGNED_CACHE:
        try:
            package = package_module.inspect_package_v1(directory.parent, kind="price_provider")
            _SIGNED_CACHE[key] = package["plugin_version"] if package["signature"]["status"] == "valid" and package["plugin_id"] == plugin_id else None
        except package_module.PluginPackageBlocked:
            _SIGNED_CACHE[key] = None
    return _SIGNED_CACHE[key]


def _registry() -> dict[str, ProviderSpec]:
    """Alle gueltigen Kursanbieter, je Anbieter-Kennung genau einer: die mitgelieferten, dazu die installierten dieses Datenraums. Ein
    installiertes Paket mit der Kennung eines mitgelieferten loest dieses nur ab, wenn es gueltig von Portelyra signiert ist, eine hoehere
    Version traegt und dieselbe Anbieter-Kennung behaelt (Festlegung 16.11.2026); sonst gilt das mitgelieferte."""
    specs: dict[str, ProviderSpec] = {}
    _PROBLEMS.clear()
    if not PLUGIN_ROOT.is_dir():
        return specs
    for directory in sorted(PLUGIN_ROOT.iterdir()):
        manifest = directory / "manifest.json"
        if directory.name.startswith(("_", ".")) or not directory.is_dir() or not manifest.is_file():
            continue
        try:
            spec = _manifest_spec(directory, manifest)
        except PriceProviderBlocked as error:
            _PROBLEMS.append({"plugin_id": directory.name, "code": error.code})
            continue
        if spec.provider_id in specs:
            _PROBLEMS.append({"plugin_id": directory.name, "code": "price_provider_manifest_invalid"})
            continue
        specs[spec.provider_id] = spec
    from migrations.reference import plugin_package_v1 as package_module  # noqa: PLC0415
    for plugin_id, directory in _installed_directories():
        if directory is None:
            _PROBLEMS.append({"plugin_id": plugin_id, "code": "price_provider_manifest_invalid"})
            continue
        try:
            spec = replace(_manifest_spec(directory, directory / "manifest.json"), origin="installed")
        except PriceProviderBlocked as error:
            _PROBLEMS.append({"plugin_id": plugin_id, "code": error.code})
            continue
        shipped = next((item for item in specs.values() if item.plugin_id == plugin_id and item.origin == "shipped"), None)
        if shipped is not None:
            version = _signed_update(directory, plugin_id)
            if version is None or version != spec.plugin_version or spec.provider_id != shipped.provider_id:
                _PROBLEMS.append({"plugin_id": plugin_id, "code": "price_provider_update_signature_invalid"})
                continue
            if not package_module.newer_v1(spec.plugin_version, shipped.plugin_version):
                continue        # ein spaeteres Release bringt eine gleich hohe oder hoehere Fassung mit: die gilt
            specs[spec.provider_id] = replace(spec, replaces_shipped=shipped.plugin_version)
        elif spec.provider_id in specs:
            _PROBLEMS.append({"plugin_id": plugin_id, "code": "price_provider_id_taken"})
        else:
            specs[spec.provider_id] = spec
    return specs


def provider_specs_v1() -> list[ProviderSpec]:
    return sorted(_registry().values(), key=lambda spec: spec.provider_id)


def provider_spec_v1(provider_id: str) -> ProviderSpec | None:
    return _registry().get(provider_id)


def provider_plugin_problems_v1() -> list[dict[str, str]]:
    _registry()
    return list(_PROBLEMS)


def _spec(provider_id: str, operation: str) -> ProviderSpec:
    spec = provider_spec_v1(provider_id)
    if spec is None:
        raise PriceProviderBlocked("price_provider_unavailable")
    if operation not in spec.operations:
        raise PriceProviderBlocked("price_provider_operation_unsupported")
    return spec


def provider_identity_v1(provider_id: str) -> dict[str, str]:
    """Kennung fuer die Herkunft je Abruf: Plugin, Version und Pruefsumme ueber den ganzen Code, der die Antwort gelesen hat
    (Einstieg, Module, Host, Sandbox). ``source_version`` traegt sie an jeden Kurstag (Festlegung 09.11.2026: Herkunft je Kurstag)."""
    spec = provider_spec_v1(provider_id)
    if spec is None:
        raise PriceProviderBlocked("price_provider_unavailable")
    digest = hashlib.sha256()
    for part in [spec.entry_sha256, *[sha for _path, sha in spec.modules], _sha256(HOST), _sha256(SANDBOX)]:
        digest.update(part.encode("ascii"))
    code_sha256 = digest.hexdigest()
    return {"plugin_id": spec.plugin_id, "plugin_version": spec.plugin_version, "provider_id": spec.provider_id,
            "code_sha256": code_sha256, "manifest_sha256": spec.manifest_sha256,
            "source_version": f"{spec.plugin_id}-{spec.plugin_version}-{code_sha256[:12]}"}


def allowed_hosts_v1() -> frozenset[str]:
    return frozenset(host for spec in _registry().values() for host in spec.hosts)


# ---------------------------------------------------------------------------------------------------------------------------
# Abgeschotteter Prozess (wie bei den Lesern, rc.375): innerhalb einer Sitzung bleibt je Plugin ein Prozess offen.
# ---------------------------------------------------------------------------------------------------------------------------

def _environment(private: Path) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(private), "TMPDIR": str(private), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def _verified(spec: ProviderSpec) -> bool:
    try:
        return spec.entry.is_file() and _sha256(spec.entry) == spec.entry_sha256 and all(
            path.is_file() and _sha256(path) == sha for path, sha in spec.modules)
    except OSError:
        return False


# Abschottung, wo das System sie kann (Festlegung 09.11.2026): Linux ab Kernel 6.2 (Landlock ABI >= 3). Ohne sie laeuft ein
# mitgeliefertes, mit jedem Release geprueftes Plugin in einem eigenen Prozess ohne Abschottung - Pruefsummen und die Pruefung jeder
# Ausgabe gelten weiter, nur Datei- und Netzsperre fehlen. Fremde Plugins laufen nur abgeschottet.
ISOLATION_ENV = "PORTELYRA_PRICE_PROVIDER_ISOLATION_INTERNAL"   # Tests: "unavailable" erzwingt den Weg ohne Abschottung
_ISOLATION: bool | None = None


def isolation_available_v1() -> bool:
    """Ob Kursanbieter-Plugins abgeschottet laufen koennen; einmal je Prozess geprueft (Plattform, dann ein kurzer Probelauf)."""
    global _ISOLATION
    if os.environ.get(ISOLATION_ENV) == "unavailable":
        return False
    if _ISOLATION is None:
        _ISOLATION = sys.platform.startswith("linux") and _isolation_probe()
    return _ISOLATION


def _isolation_probe() -> bool:
    temporary = Path(tempfile.mkdtemp(prefix="price-provider-probe-"))
    try:
        os.chmod(temporary, 0o700)
        output, private = temporary / "output", temporary / "tmp"
        for path in (output, private):
            path.mkdir(mode=0o700)
        request = temporary / "request.json"
        request.write_text("{}", encoding="utf-8")   # der Host antwortet mit host_error, sobald er laeuft
        command = [sys.executable, "-B", str(SANDBOX), "--python", sys.executable, "--entry", str(HOST), "--source", str(request),
                   "--output", str(output), "--temporary", str(private), "--timeout-seconds", "10"]
        completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, env=_environment(private), timeout=30,
                                   start_new_session=True)
        return completed.returncode == 0 and (output / "result.json").is_file()
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def provider_isolated_v1(spec: ProviderSpec) -> bool:
    """True: abgeschottet; False: mitgeliefertes Plugin ohne Abschottung. Fremde Plugins ohne Abschottung sind gesperrt."""
    if isolation_available_v1():
        return True
    if spec.origin == "shipped":
        return False
    raise PriceProviderBlocked("price_provider_isolation_unavailable")


def _limits(cpu_seconds: int):
    def apply() -> None:
        try:
            import resource  # noqa: PLC0415 - nicht auf jeder Plattform vorhanden
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds + 1, cpu_seconds + 1))
            resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024))
        except (ImportError, OSError, ValueError):
            pass
    return apply if os.name == "posix" else None


def _command(spec: ProviderSpec, request: Path, output: Path, private: Path, inputs: Path, cpu_seconds: int) -> list[str]:
    if not provider_isolated_v1(spec):
        return [sys.executable, "-I", "-B", str(HOST), str(request), str(output)]
    return [sys.executable, "-B", str(SANDBOX), "--python", sys.executable, "--entry", str(HOST), "--source", str(request),
            "--output", str(output), "--temporary", str(private), "--support", str(spec.plugin_dir), "--support", str(inputs),
            "--timeout-seconds", str(cpu_seconds)]


def _checked(payload: Any, count: int) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and set(payload) == {"host_error"}:
        return [{"ok": False, "code": "price_provider_failed"} for _ in range(count)]
    results = payload.get("results") if isinstance(payload, dict) and set(payload) == {"results"} else None
    if not isinstance(results, list) or len(results) != count:
        raise PriceProviderBlocked("price_provider_output_invalid")
    checked = []
    for item in results:
        if isinstance(item, dict) and set(item) == {"ok", "value"} and item["ok"] is True:
            checked.append({"ok": True, "value": item["value"]})
        elif isinstance(item, dict) and set(item) == {"ok", "code"} and item["ok"] is False:
            checked.append({"ok": False, "code": "price_provider_failed"})
        else:
            raise PriceProviderBlocked("price_provider_output_invalid")
    return checked


WORKER_CPU_SECONDS = 900
_SESSION_DEPTH = 0
_SESSION_LOCK = threading.RLock()


class _Worker:
    def __init__(self, spec: ProviderSpec):
        self.key = _worker_key(spec)
        self.lock = threading.Lock()
        self.temporary = Path(tempfile.mkdtemp(prefix="price-provider-worker-"))
        os.chmod(self.temporary, 0o700)
        self.inputs, output, private = self.temporary / "inputs", self.temporary / "output", self.temporary / "tmp"
        for path in (self.inputs, output, private):
            path.mkdir(mode=0o700)
        request = self.temporary / "request.json"
        request.write_text(json.dumps({"api_version": API_VERSION, "serve": True, "entry": str(spec.entry), "plugin_dir": str(spec.plugin_dir)}),
                           encoding="utf-8")
        command = _command(spec, request, output, private, self.inputs, WORKER_CPU_SECONDS)
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=_environment(private),
                                        bufsize=0, start_new_session=True, preexec_fn=None if command[2] == str(SANDBOX) else _limits(WORKER_CPU_SECONDS))
        self.calls = 0

    def call(self, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        import secrets
        import selectors
        import time
        with self.lock:   # Intraday ruft aus mehreren Faeden; der Prozess arbeitet Auftraege nacheinander ab.
            self.calls += 1
            call_dir = self.inputs / f"{self.calls:06d}"
            call_dir.mkdir(mode=0o700)
            try:
                request_jobs = [_write_job(call_dir, index, job) for index, job in enumerate(jobs, 1)]
                nonce = secrets.token_hex(16)
                line = json.dumps({"nonce": nonce, "jobs": request_jobs}).encode("utf-8") + b"\n"
                try:
                    self.process.stdin.write(line)
                    self.process.stdin.flush()
                except (BrokenPipeError, OSError):
                    self.close()
                    raise PriceProviderBlocked(self._dead_code())
                buffer = bytearray()
                deadline = time.monotonic() + TIMEOUT_SECONDS
                with selectors.DefaultSelector() as selector:
                    selector.register(self.process.stdout, selectors.EVENT_READ)
                    while b"\n" not in buffer:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(timeout=remaining):
                            self.close()
                            raise PriceProviderBlocked("price_provider_timeout")
                        chunk = os.read(self.process.stdout.fileno(), 1 << 20)
                        if not chunk:
                            self.close()
                            raise PriceProviderBlocked(self._dead_code())
                        buffer += chunk
                        if len(buffer) > MAX_RESULT_BYTES:
                            self.close()
                            raise PriceProviderBlocked("price_provider_output_invalid")
                try:
                    payload = json.loads(bytes(buffer[:buffer.index(b"\n")]).decode("utf-8"))
                except (UnicodeError, ValueError) as exc:
                    self.close()
                    raise PriceProviderBlocked("price_provider_output_invalid") from exc
                if not isinstance(payload, dict) or payload.pop("nonce", None) != nonce:
                    self.close()
                    raise PriceProviderBlocked("price_provider_output_invalid")
                return _checked(payload, len(jobs))
            finally:
                shutil.rmtree(call_dir, ignore_errors=True)

    def _dead_code(self) -> str:
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return "price_provider_failed"
        return "price_provider_isolation_unavailable" if code == 78 else "price_provider_failed"

    def close(self) -> None:
        with _SESSION_LOCK:
            if _WORKERS.get(self.key) is self:
                _WORKERS.pop(self.key, None)
        if self.process.poll() is None:
            try:
                os.killpg(self.process.pid, 9)
            except OSError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        for stream in (self.process.stdin, self.process.stdout):
            try:
                stream.close()
            except OSError:
                pass
        shutil.rmtree(self.temporary, ignore_errors=True)


_WORKERS: dict[tuple, _Worker] = {}


def _worker_key(spec: ProviderSpec) -> tuple:
    return (str(spec.plugin_dir), spec.entry_sha256, tuple(sha for _path, sha in spec.modules), str(SANDBOX), str(HOST), isolation_available_v1())


def close_price_provider_workers_v1() -> None:
    for worker in list(_WORKERS.values()):
        worker.close()


atexit.register(close_price_provider_workers_v1)


@contextlib.contextmanager
def price_provider_session_v1():
    """Ein Vorgang: Plugin-Prozesse bleiben bis zu seinem Ende offen. Verschachtelte Sitzungen gehoeren zur aeussersten."""
    global _SESSION_DEPTH
    with _SESSION_LOCK:
        _SESSION_DEPTH += 1
    try:
        yield
    finally:
        with _SESSION_LOCK:
            _SESSION_DEPTH -= 1
            last = _SESSION_DEPTH == 0
        if last:
            close_price_provider_workers_v1()


def within_price_provider_session(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with price_provider_session_v1():
            return function(*args, **kwargs)
    return wrapper


def _write_job(directory: Path, index: int, job: Mapping[str, Any]) -> dict[str, Any]:
    if job["op"] != "parse_response":
        return dict(job)
    body_path = directory / f"{index:04d}.body"
    body_path.write_bytes(job["body"])
    os.chmod(body_path, 0o600)
    return {key: value for key, value in job.items() if key != "body"} | {"body_path": str(body_path)}


def _run(spec: ProviderSpec, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not _verified(spec):
        raise PriceProviderBlocked("price_provider_unavailable")
    if not HOST.is_file() or (not SANDBOX.is_file() and provider_isolated_v1(spec)):
        raise PriceProviderBlocked("price_provider_isolation_unavailable")
    if _SESSION_DEPTH > 0:
        key = _worker_key(spec)
        with _SESSION_LOCK:
            worker = _WORKERS.get(key)
            if worker is None or worker.process.poll() is not None:
                if worker is not None:
                    worker.close()
                worker = _WORKERS[key] = _Worker(spec)
        return worker.call(jobs)
    temporary = Path(tempfile.mkdtemp(prefix="price-provider-"))
    try:
        os.chmod(temporary, 0o700)
        inputs, output, private = temporary / "inputs", temporary / "output", temporary / "tmp"
        for path in (inputs, output, private):
            path.mkdir(mode=0o700)
        request_jobs = [_write_job(inputs, index, job) for index, job in enumerate(jobs, 1)]
        request = temporary / "request.json"
        request.write_text(json.dumps({"api_version": API_VERSION, "entry": str(spec.entry), "plugin_dir": str(spec.plugin_dir),
                                       "jobs": request_jobs}), encoding="utf-8")
        try:
            command = _command(spec, request, output, private, inputs, TIMEOUT_SECONDS)
            completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, env=_environment(private), timeout=TIMEOUT_SECONDS + 10,
                                       start_new_session=True, preexec_fn=None if command[2] == str(SANDBOX) else _limits(TIMEOUT_SECONDS))
        except subprocess.TimeoutExpired as exc:
            raise PriceProviderBlocked("price_provider_timeout") from exc
        if completed.returncode == 78:
            raise PriceProviderBlocked("price_provider_isolation_unavailable")
        if completed.returncode != 0:
            raise PriceProviderBlocked("price_provider_failed")
        entries = list(output.iterdir())
        result_path = output / "result.json"
        if [entry.name for entry in entries] != ["result.json"] or result_path.is_symlink() or not result_path.is_file() \
                or result_path.stat().st_size > MAX_RESULT_BYTES:
            raise PriceProviderBlocked("price_provider_output_invalid")
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise PriceProviderBlocked("price_provider_output_invalid") from exc
        return _checked(payload, len(jobs))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _one(spec: ProviderSpec, job: dict[str, Any]) -> Any:
    result = _run(spec, [job])[0]
    if not result["ok"]:
        raise PriceProviderBlocked(result["code"])
    return result["value"]


# ---------------------------------------------------------------------------------------------------------------------------
# Anfragen, Antworten, Abruf
# ---------------------------------------------------------------------------------------------------------------------------

def _valid_request(spec: ProviderSpec, value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {"host", "target"} or not isinstance(value["host"], str) \
            or not isinstance(value["target"], str) or _TARGET.match(value["target"]) is None:
        raise PriceProviderBlocked("price_provider_output_invalid")
    if value["host"] not in spec.hosts:
        raise PriceProviderBlocked("price_provider_host_not_allowed")
    return {"host": value["host"], "target": value["target"]}


def build_request_v1(provider_id: str, operation: str, params: Mapping[str, Any]) -> dict[str, str]:
    """Die Anfrage des Plugins: Host (aus dem Manifest) und Ziel. Kopfzeilen setzt der Kern."""
    spec = _spec(provider_id, operation)
    return _valid_request(spec, _one(spec, {"op": "build_request", "operation": operation, "params": dict(params)}))


def fx_symbol_v1(provider_id: str, base_currency: str, quote_currency: str) -> str:
    spec = _spec(provider_id, "fx_symbol")
    value = _one(spec, {"op": "fx_symbol", "base_currency": base_currency, "quote_currency": quote_currency})
    if not isinstance(value, dict) or set(value) != {"symbol"} or not _text(value["symbol"], 120):
        raise PriceProviderBlocked("price_provider_output_invalid")
    return value["symbol"]


def parse_response_v1(provider_id: str, operation: str, params: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    """Die Auswertung des Plugins, vom Kern vollstaendig geprueft. ``response``: status (int), content_type (str oder None), body."""
    spec = _spec(provider_id, operation)
    status = response.get("status")
    body = response.get("body")
    content_type = response.get("content_type")
    if type(status) is not int or not isinstance(body, bytes) or (content_type is not None and not isinstance(content_type, str)):
        raise PriceProviderBlocked("price_provider_output_invalid")
    value = _one(spec, {"op": "parse_response", "operation": operation, "params": dict(params), "status": status,
                        "content_type": content_type, "body": body})
    return validate_outcome_v1(operation, params, value)


def run_generate_v1(provider_id: str, operation: str, seeds: Sequence[int]) -> list[dict[str, Any]]:
    spec = _spec(provider_id, operation)
    return _run(spec, [{"op": "generate", "operation": operation, "seed": int(seed)} for seed in seeds])


OFFLINE_ENV = "PORTELYRA_OFFLINE_INTERNAL"


def https_get_v1(host: str, target: str, headers: Mapping[str, str], timeout: int, limit: int) -> dict[str, Any]:
    """Der einzige Abrufweg fuer Kursanbieter: HTTPS-GET an einen Host aus einem gueltigen Manifest, ohne Weiterleitung, mit
    Zeitlimit und Groessengrenze. Gibt Status, Kopfzeilen (klein geschrieben) und Koerper zurueck."""
    if not isinstance(host, str) or host not in allowed_hosts_v1():
        raise PriceProviderBlocked("price_provider_host_not_allowed")
    if not isinstance(target, str) or _TARGET.match(target) is None or timeout != FETCH_TIMEOUT_SECONDS or limit != FETCH_BYTE_LIMIT:
        raise PriceProviderBlocked("price_provider_transport_failed")
    # Ohne Netz (Wiederherstellungsprobe #493, Tests): kein Verbindungsversuch, Abruf scheitert sofort wie ohne Verbindung.
    if os.environ.get(OFFLINE_ENV) == "1":
        raise PriceProviderBlocked("price_provider_transport_failed")
    connection = None
    try:
        connection = http.client.HTTPSConnection(host, 443, timeout=timeout, context=ssl.create_default_context())
        connection.request("GET", target, body=None, headers=dict(headers))
        response = connection.getresponse()
        body = response.read(limit + 1)
        if len(body) > limit:
            raise PriceProviderBlocked("price_provider_response_too_large")
        return {"status": response.status, "headers": {key.lower(): value for key, value in response.getheaders()}, "body": body}
    except PriceProviderBlocked:
        raise
    except Exception as error:  # noqa: BLE001
        raise PriceProviderBlocked("price_provider_transport_failed") from error
    finally:
        if connection is not None:
            connection.close()


# ---------------------------------------------------------------------------------------------------------------------------
# Pruefung der Auswertungen
# ---------------------------------------------------------------------------------------------------------------------------

def _invalid() -> None:
    raise PriceProviderBlocked("price_provider_output_invalid")


def _decimal_or_none(value: Any, limit: int = 120) -> None:
    if value is not None and (not isinstance(value, str) or len(value) > limit or _DECIMAL.match(value) is None):
        _invalid()


def _day(value: Any) -> date:
    if not isinstance(value, str) or _DAY.match(value) is None:
        _invalid()
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _invalid()
    if parsed.isoformat() != value:
        _invalid()
    return parsed


def _utc(value: Any) -> None:
    if not isinstance(value, str) or _UTC.match(value) is None:
        _invalid()


_DAY_KEYS = {"trading_date", "open_decimal", "high_decimal", "low_decimal", "close_decimal", "adjusted_close_decimal", "volume_decimal",
             "day_status", "corporate_action_status", "observed_at_utc"}
_DAILY_KEYS = {"provider_symbol", "provider_currency", "exchange", "timezone_name", "instrument_name", "instrument_type",
               "split_review_required", "days", "live_session", "first_trade_date"}
_FX_KEYS = {"provider_symbol", "provider_currency", "exchange", "timezone_name", "split_review_required", "days", "live_session"}


def _history(operation: str, params: Mapping[str, Any], result: Any) -> dict[str, Any]:
    keys = _DAILY_KEYS if operation == "daily_history" else _FX_KEYS
    if not isinstance(result, dict) or set(result) != keys:
        _invalid()
    if not _text(result["provider_symbol"], 120) or not isinstance(result["provider_currency"], str) \
            or _CURRENCY.match(result["provider_currency"]) is None or not isinstance(result["exchange"], str) \
            or len(result["exchange"]) > 160 or not isinstance(result["timezone_name"], str) or not isinstance(result["split_review_required"], bool):
        _invalid()
    try:
        ZoneInfo(result["timezone_name"])
    except (ZoneInfoNotFoundError, ValueError):
        _invalid()
    if operation == "daily_history":
        for key, limit in (("instrument_name", 160), ("instrument_type", 40)):
            if not isinstance(result[key], str) or len(result[key]) > limit:
                _invalid()
        if result["first_trade_date"] is not None:
            _day(result["first_trade_date"])
    start = _day(params["start_date"])
    end = _day(params["end_date"])
    days = result["days"]
    if not isinstance(days, list) or len(days) > MAX_DAYS:
        _invalid()
    previous = None
    for row in days:
        if not isinstance(row, dict) or set(row) != _DAY_KEYS:
            _invalid()
        trading = _day(row["trading_date"])
        if trading < start or trading > end or (previous is not None and trading <= previous):
            _invalid()
        previous = trading
        for key in ("open_decimal", "high_decimal", "low_decimal", "close_decimal", "adjusted_close_decimal", "volume_decimal"):
            _decimal_or_none(row[key])
        if row["day_status"] not in {"observed", "source_gap"} or (row["day_status"] == "observed") != (row["close_decimal"] is not None) \
                or row["corporate_action_status"] not in {"none_reported", "pending_review"}:
            _invalid()
        _utc(row["observed_at_utc"])
    live = result["live_session"]
    if live is not None:
        if not isinstance(live, dict) or set(live) != {"trading_date", "close_decimal", "observed_at_utc", "session_complete"} \
                or live["session_complete"] is not False:
            _invalid()
        _day(live["trading_date"])
        _decimal_or_none(live["close_decimal"])
        _utc(live["observed_at_utc"])
    return result


def _quote(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"kind", "decimal", "observed_at_utc", "currency", "as_of_date"} \
            or value["kind"] not in {"live_session", "closing_bar", "meta_quote"} or not isinstance(value["decimal"], str) \
            or not 1 <= len(value["decimal"]) <= 120 or not isinstance(value["currency"], str) or len(value["currency"]) != 3:
        _invalid()
    try:
        if not Decimal(value["decimal"]).is_finite():
            _invalid()
    except (InvalidOperation, ValueError):
        _invalid()
    _utc(value["observed_at_utc"])
    _day(value["as_of_date"])
    return value


_SEARCH_KEYS = {"symbol", "display_name", "exchange", "quote_type", "quote_currency"}
_QUOTE_TYPES = {"cryptocurrency", "currency", "equity", "etf", "future", "index", "fund", "option", "other"}
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def _candidates(value: Any, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > limit:
        _invalid()
    for row in value:
        if not isinstance(row, dict) or not (set(row) == _SEARCH_KEYS or set(row) == _SEARCH_KEYS | {"isin"}) \
                or not _text(row["symbol"], 80) or not _text(row["display_name"], 120) or not _text(row["exchange"], 80) \
                or row["quote_type"] not in _QUOTE_TYPES \
                or (row["quote_currency"] is not None and (not isinstance(row["quote_currency"], str) or _CURRENCY.match(row["quote_currency"]) is None)) \
                or ("isin" in row and (not isinstance(row["isin"], str) or _ISIN.match(row["isin"]) is None)):
            _invalid()
    return value


def validate_outcome_v1(operation: str, params: Mapping[str, Any], value: Any) -> dict[str, Any]:
    """Prueft den Ausgang einer Auswertung; der Kern gibt nur Gepruetes weiter."""
    if not isinstance(value, dict) or not isinstance(value.get("outcome"), str):
        _invalid()
    outcome = value["outcome"]
    if operation in ("daily_history", "fx_daily_history"):
        if outcome == "ok" and set(value) == {"outcome", "result"}:
            return {"outcome": "ok", "result": _history(operation, params, value["result"])}
        if operation == "daily_history" and outcome in {"rejected", "not_listed", "invalid"} and set(value) == {"outcome"}:
            return {"outcome": outcome}
        if operation == "fx_daily_history" and outcome == "invalid" and set(value) == {"outcome", "detail"} \
                and value["detail"] in {"json", "shape", "identity", "series", "value", "input"}:
            return {"outcome": "invalid", "detail": value["detail"]}
        _invalid()
    if operation == "quote":
        if outcome == "ok" and set(value) == {"outcome", "quote"}:
            return {"outcome": "ok", "quote": _quote(value["quote"])}
        if outcome in {"no_observation", "invalid"} and set(value) == {"outcome"}:
            return {"outcome": outcome}
        _invalid()
    if operation == "credential_check":
        # Zugang pruefen (#546): angenommen, abgewiesen oder nicht lesbar - mehr verraet die Pruefung nicht.
        if outcome in {"accepted", "rejected", "invalid"} and set(value) == {"outcome"}:
            return {"outcome": outcome}
        _invalid()
    if operation == "search":
        if outcome == "ok" and set(value) == {"outcome", "candidates"}:
            return {"outcome": "ok", "candidates": _candidates(value["candidates"], int(params["limit"]))}
        if outcome == "invalid" and set(value) == {"outcome"}:
            return {"outcome": "invalid"}
        _invalid()
    raise PriceProviderBlocked("price_provider_operation_unsupported")


__all__ = [
    "API_VERSION", "CredentialField", "FETCH_BYTE_LIMIT", "FETCH_TIMEOUT_SECONDS", "PriceProviderBlocked", "ProviderSpec", "allowed_hosts_v1", "build_request_v1", "close_price_provider_workers_v1",
    "fx_symbol_v1", "https_get_v1", "isolation_available_v1", "provider_isolated_v1", "parse_response_v1", "price_provider_session_v1", "provider_identity_v1",
    "provider_plugin_problems_v1", "provider_spec_v1", "provider_specs_v1", "run_generate_v1", "validate_outcome_v1",
    "within_price_provider_session",
]
