"""Leser-Plugins (statement_reader_v1, #486): Verzeichnis, Erkennungsregeln, abgeschotteter Aufruf, Ergebnispruefung.

Ein Leser-Plugin liegt unter ``plugins/readers/<plugin_id>/`` (Manifest, Leser, erfundene Testbelege, Handbuchseite). Der Kern
prueft das Manifest und die Pruefsumme des Lesers, fuehrt ihn ausschliesslich in der Sandbox aus
(``workers/import_plugin_sandbox_v1.py``: Landlock, kein Netz, Ressourcengrenzen) und prueft jedes Ergebnis gegen das Schema
seines Bereichs. Steht die Sandbox nicht zur Verfuegung, gibt es keinen Import - ungeschuetzt laeuft kein Leser
(Festlegung vom 07.11.2026). Der Vertrag steht offen in ``contracts/statement-reader-plugin/v1/``.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import functools
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins" / "readers"
SDK_DIR = PLUGIN_ROOT / "sdk"
HOST = ROOT / "workers" / "statement_reader_host_v1.py"
SANDBOX = ROOT / "workers" / "import_plugin_sandbox_v1.py"
API_VERSION = "statement_reader_v1"
# Stufe der Schnittstelle innerhalb von v1 (rc.378, #486): Innerhalb einer Hauptversion kommen nur Ergaenzungen dazu. Ein Manifest
# nennt in api_minor die Stufe, die es braucht. Braucht es eine neuere als dieser Kern, wird es abgewiesen ("braucht einen neueren
# Kern"); nennt es eine niedrigere, als es benutzt, ist das Manifest ungueltig. Eine aeltere Stufe bleibt immer lauffaehig.
API_MINOR = 6
# Stufe 6 (rc.425, #486; Festlegung 16.11.2026): Reward-Leser, deren Export ein Unterkonto nennt, geben im Manifest den Namen an, den sie
# ohne Angabe setzen (`subaccount_fallback`). Bis rc.424 stand diese Liste fest in der Data-App.
API_SUBACCOUNT_MINOR = 6
API_DOMAIN_MINOR = {"cash": 0, "securities": 1, "fx": 1, "crypto": 2, "reward": 3, "income_statement": 3}
API_COMBINE_MINOR = 2
# Stufe 4 (rc.379): Erzeuger erfundener Belege fuer den Selbsttest (generate, "generator": true je Leser).
API_GENERATOR_MINOR = 4
# Stufe 5 (rc.419, #486): Angaben je Leser im Manifest, die der Kern bisher je Institut fest kannte - Quellangaben eines Krypto-Lesers
# ("source": Name, Institute, Unterkonten, Paarung, Gruende), Profile eines Wertpapier- oder Devisenlesers ("profiles": Anzeigename,
# Institute, Kontohinweis, Depotfamilie) und der Pruefstand des Formats ("format_checked": bis zu welchem Belegdatum der Leser an echten
# Belegen als richtig bestaetigt ist). Ein neues Institut braucht so keinen geaenderten Kern.
API_SOURCE_MINOR = 5
DOMAINS = ("cash", "securities", "fx", "crypto", "reward", "income_statement")
# Bereiche, deren Leser Bytes bekommen (read); die uebrigen bekommen Text (read_text, detect, finish).
BYTE_DOMAINS = frozenset({"cash", "reward"})
TIMEOUT_SECONDS = 120
MAX_RESULT_BYTES = 32 * 1024 * 1024
MAX_ROWS = 100_000

# Feste Liste der Codes, mit denen ein Leser abbrechen darf (error-codes.csv). Jeder andere Code wird statement_reader_failed.
READER_ERROR_CODES = {
    "cash": frozenset({"cash_statement_header_invalid", "cash_statement_source_invalid", "cash_statement_multiple_accounts"}),
    "securities": frozenset({"securities_statement_source_invalid"}),
    "fx": frozenset({"securities_statement_source_invalid"}),
    "crypto": frozenset(),
    "reward": frozenset({"statement_exchange_adapter_header_invalid", "statement_exchange_adapter_source_invalid"}),
    "income_statement": frozenset({"tax_document_source_invalid"}),
}
SDK_ERROR_CODES = frozenset({"statement_reader_pdf_text_missing"})

_PLUGIN_ID = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_READER_ID = re.compile(r"^[a-z][a-z0-9_]{2,60}_v[0-9]+$")
_VERSION = re.compile(r"^[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}$")
_EXTENSION = re.compile(r"^\.[a-z0-9]{1,8}$")
_FILE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
_MODULE = re.compile(r"^[A-Za-z0-9_]{1,60}\.py$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_POSITIVE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_SIGNED = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_CODE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")
# Bezugstag der Regel "kein Buchungstag nach heute". Nur die Vertragstests setzen ihn, weil ihre erfundenen Belege bewusst in der
# Zukunft liegen (2027); im Betrieb gilt das Datum des Rechners.
REFERENCE_DATE_ENV = "PORTELYRA_READER_REFERENCE_DATE_INTERNAL"


class StatementReaderBlocked(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReaderSpec:
    reader_id: str
    domain: str
    label: str
    document_kind: str
    extensions: tuple[str, ...]
    match_any: tuple[tuple[str, ...], ...]
    tested_formats: str
    known_limits: tuple[str, ...]
    plugin_id: str
    plugin_version: str
    publisher: str
    institution: str
    plugin_dir: Path
    entry: Path
    entry_sha256: str
    modules: tuple[tuple[Path, str], ...] = ()
    combine: bool = False
    generator: bool = False
    origin: str = "shipped"   # "shipped" (mitgeliefert) oder "installed" (aus Datei installiert, rc.381)
    source: Mapping[str, Any] | None = None   # Quellangaben eines Krypto-Lesers (Stufe 5), schon geprueft
    profiles: Mapping[str, Mapping[str, Any]] | None = None   # Profile eines Wertpapier- oder Devisenlesers (Stufe 5)
    format_checked: Mapping[str, str] | None = None   # Pruefstand des Formats (Stufe 5): through, checked_on
    intake: Mapping[str, Any] | None = None   # Rezept des Eingangs fuer das Institut des Plugins (Stufe 5), an jedem seiner Leser
    rules_sha256: str = ""   # Pruefsumme der Regeln im Manifest (manifest_rules_sha256_v1), Teil der Code-Pruefsumme
    replaces_shipped: str | None = None   # Update eines mitgelieferten Plugins (#486 Schritt 3): dessen Version, sonst None
    subaccount_fallback: str | None = None   # Reward-Leser mit Unterkonto im Export (Stufe 6): Name ohne Angabe, sonst None
    row_ids: bool = False   # Reward-Leser: jede Zeile traegt eine eigene Kennung der Boerse (Stufe 5); der Zeilenschluessel bindet nur sie


def _text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def _inside(directory: Path, relative: Any) -> Path | None:
    """Ein Pfad im Plugin-Ordner, ohne Ausbruch und ohne symbolische Verknuepfung."""
    if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts:
        return None
    path = directory / relative
    if path.is_symlink() or not path.is_file():
        return None
    try:
        path.resolve(strict=True).relative_to(directory.resolve(strict=True))
    except (OSError, ValueError):
        return None
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_readers(directory: Path, manifest: Mapping[str, Any]) -> list[ReaderSpec]:
    """Prueft ein Manifest vollstaendig; jede Abweichung verwirft das ganze Plugin (Mindestanforderung 1)."""
    top = {"api_version", "api_minor", "plugin_id", "plugin_version", "publisher", "institution", "label", "entry_point",
           "entry_point_sha256", "modules", "handbook", "readers", "fixtures"}
    if not isinstance(manifest, Mapping) or not top <= set(manifest) <= top | {"intake"}:
        raise StatementReaderBlocked("statement_reader_manifest_invalid")
    intake = _intake(manifest["intake"]) if "intake" in manifest else None
    if "intake" in manifest and intake is None:
        raise StatementReaderBlocked("statement_reader_manifest_invalid")
    if manifest["api_version"] != API_VERSION:
        raise StatementReaderBlocked("statement_reader_api_version_unsupported")
    minor = manifest["api_minor"]
    if not isinstance(minor, int) or isinstance(minor, bool) or minor < 0:
        raise StatementReaderBlocked("statement_reader_manifest_invalid")
    if minor > API_MINOR:
        raise StatementReaderBlocked("statement_reader_api_version_unsupported")
    if not (isinstance(manifest["plugin_id"], str) and _PLUGIN_ID.match(manifest["plugin_id"]) and manifest["plugin_id"] == directory.name
            and isinstance(manifest["plugin_version"], str) and _VERSION.match(manifest["plugin_version"])
            and _text(manifest["publisher"], 80) and _text(manifest["institution"], 120) and _text(manifest["label"], 120)
            and isinstance(manifest["entry_point"], str) and _FILE.match(manifest["entry_point"]) and manifest["entry_point"].endswith(".py")
            and isinstance(manifest["entry_point_sha256"], str) and _SHA.match(manifest["entry_point_sha256"])
            and _inside(directory, manifest["handbook"]) is not None):
        raise StatementReaderBlocked("statement_reader_manifest_invalid")
    entry = _inside(directory, manifest["entry_point"])
    if entry is None or _sha256(entry) != manifest["entry_point_sha256"]:
        raise StatementReaderBlocked("statement_reader_entry_mismatch")
    # Weitere Module des Lesers, je mit Pruefsumme. Code, den das Manifest nicht nennt, verwirft das Plugin: Was laeuft, ist geprueft.
    modules = manifest["modules"]
    if not isinstance(modules, list) or not all(isinstance(item, Mapping) and set(item) == {"path", "sha256"} and isinstance(item["path"], str)
                                                and _MODULE.match(item["path"]) and isinstance(item["sha256"], str) and _SHA.match(item["sha256"])
                                                for item in modules):
        raise StatementReaderBlocked("statement_reader_manifest_invalid")
    module_files: list[tuple[Path, str]] = []
    for item in modules:
        path = _inside(directory, item["path"])
        if path is None or path == entry or _sha256(path) != item["sha256"]:
            raise StatementReaderBlocked("statement_reader_entry_mismatch")
        module_files.append((path, item["sha256"]))
    listed = {entry.name} | {path.name for path, _sha in module_files}
    code = {str(path.relative_to(directory)) for path in directory.rglob("*.py") if "__pycache__" not in path.parts}
    if code != listed or len(listed) != 1 + len(module_files):
        raise StatementReaderBlocked("statement_reader_entry_mismatch")
    reader_keys = {"reader_id", "domain", "label", "document_kind", "extensions", "detection", "tested_formats", "known_limits"}
    readers = manifest["readers"]
    if not isinstance(readers, list) or not readers:
        raise StatementReaderBlocked("statement_reader_manifest_invalid")
    specs: list[ReaderSpec] = []
    for reader in readers:
        if not isinstance(reader, Mapping) or not reader_keys <= set(reader) <= reader_keys | {"combine", "generator", "source", "profiles", "format_checked", "row_ids", "subaccount_fallback"} \
                or not isinstance(reader.get("combine", False), bool) or not isinstance(reader.get("generator", False), bool) \
                or not isinstance(reader.get("row_ids", False), bool) or (reader.get("row_ids") and reader.get("domain") != "reward") \
                or ("subaccount_fallback" in reader and (reader.get("domain") != "reward" or not _text(reader.get("subaccount_fallback"), 40))):
            raise StatementReaderBlocked("statement_reader_manifest_invalid")
        detection = reader["detection"]
        groups = detection.get("match_any") if isinstance(detection, Mapping) and set(detection) == {"match_any"} else None
        if not (isinstance(reader["reader_id"], str) and _READER_ID.match(reader["reader_id"]) and reader["domain"] in DOMAINS
                and _text(reader["label"], 160) and _text(reader["document_kind"], 120)
                and isinstance(reader["extensions"], list) and reader["extensions"]
                and all(isinstance(item, str) and _EXTENSION.match(item) for item in reader["extensions"])
                and isinstance(groups, list) and all(isinstance(group, list) and group and all(_text(item, 120) for item in group) for group in groups)
                and _text(reader["tested_formats"], 600)
                and isinstance(reader["known_limits"], list) and reader["known_limits"] and all(_text(item, 400) for item in reader["known_limits"])):
            raise StatementReaderBlocked("statement_reader_manifest_invalid")
        source = _crypto_source(reader["source"]) if "source" in reader else None
        if "source" in reader and (source is None or reader["domain"] != "crypto"):
            raise StatementReaderBlocked("statement_reader_manifest_invalid")
        profiles = _securities_profiles(reader["profiles"]) if "profiles" in reader else None
        if "profiles" in reader and (profiles is None or reader["domain"] not in ("securities", "fx")):
            raise StatementReaderBlocked("statement_reader_manifest_invalid")
        checked = _format_checked(reader["format_checked"]) if "format_checked" in reader else None
        if "format_checked" in reader and checked is None:
            raise StatementReaderBlocked("statement_reader_manifest_invalid")
        specs.append(ReaderSpec(
            reader_id=reader["reader_id"], domain=reader["domain"], label=reader["label"], document_kind=reader["document_kind"],
            extensions=tuple(reader["extensions"]), match_any=tuple(tuple(item.lower() for item in group) for group in groups),
            tested_formats=reader["tested_formats"], known_limits=tuple(reader["known_limits"]), plugin_id=manifest["plugin_id"],
            plugin_version=manifest["plugin_version"], publisher=manifest["publisher"], institution=manifest["institution"],
            plugin_dir=directory, entry=entry, entry_sha256=manifest["entry_point_sha256"], modules=tuple(module_files),
            combine=bool(reader.get("combine", False)), generator=bool(reader.get("generator", False)), source=source, profiles=profiles,
            format_checked=checked, intake=intake, rules_sha256=manifest_rules_sha256_v1(manifest), row_ids=bool(reader.get("row_ids", False)),
            subaccount_fallback=reader.get("subaccount_fallback")))
    # Die genannte Stufe deckt alles, was das Manifest benutzt (Bereiche, Zusammenlesen).
    needed = max([API_DOMAIN_MINOR[spec.domain] for spec in specs] + [API_COMBINE_MINOR for spec in specs if spec.combine]
                 + [API_GENERATOR_MINOR for spec in specs if spec.generator]
                 + [API_SOURCE_MINOR for spec in specs if spec.source is not None or spec.profiles is not None or spec.format_checked is not None
                    or spec.row_ids]
                 + [API_SOURCE_MINOR for _intake in [intake] if intake is not None]
                 + [API_SUBACCOUNT_MINOR for spec in specs if spec.subaccount_fallback is not None])
    if needed > manifest["api_minor"]:
        raise StatementReaderBlocked("statement_reader_manifest_invalid")
    # Eine Kennung gilt je Bereich: Trade Republic hat einen Cash- und einen Wertpapier-Leser trade_republic_v1.
    ids = [(spec.domain, spec.reader_id) for spec in specs]
    fixtures = manifest["fixtures"]
    if len(set(ids)) != len(ids) or not isinstance(fixtures, list):
        raise StatementReaderBlocked("statement_reader_manifest_invalid")
    covered: set[tuple[str, str]] = set()
    for fixture in fixtures:
        if not (isinstance(fixture, Mapping) and set(fixture) == {"domain", "reader_id", "input", "expected"} and (fixture["domain"], fixture["reader_id"]) in ids
                and str(fixture["input"]).startswith("fixtures/") and str(fixture["expected"]).startswith("fixtures/")
                and _inside(directory, fixture["input"]) is not None and _inside(directory, fixture["expected"]) is not None):
            raise StatementReaderBlocked("statement_reader_manifest_invalid")
        covered.add((fixture["domain"], fixture["reader_id"]))
    # Mindestanforderung: je Leser mindestens ein erfundener Testbeleg mit erwartetem Ergebnis.
    if covered != set(ids):
        raise StatementReaderBlocked("statement_reader_fixture_missing")
    return specs


_SOURCE_KEY = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")
_SOURCE_FIELDS = {"key", "label", "institution_names", "wallets", "default_wallet", "pairing", "internal_transfers"}
_SOURCE_OPTIONAL = {"pair_window_minutes", "pair_related_wallet", "order_window_days", "unpaired_reason_by_ticker", "reason_texts", "format_label"}


def _name_rule(value: Any) -> dict[str, tuple[str, ...]] | None:
    """Regel fuer den Kontonamen eines Unterkontos: mindestens ein Wort aus "any", keines aus "none" (klein geschrieben)."""
    if not isinstance(value, Mapping) or not set(value) <= {"any", "none"}:
        return None
    rule = {}
    for key in ("any", "none"):
        words = value.get(key, [])
        if not isinstance(words, list) or len(words) > 10 or not all(isinstance(word, str) and 1 <= len(word) <= 40 and word == word.lower() for word in words):
            return None
        rule[key] = tuple(words)
    return rule


def _crypto_source(value: Any) -> dict[str, Any] | None:
    """Quellangaben eines Krypto-Lesers (Stufe 5), streng geprueft; None heisst ungueltig.

    key: Quelle der Zeilen (gleich ihrem Feld "source"); label: Name in Kontomasken; institution_names: Teile des Institutsnamens fuer den
    Kontovorschlag; wallets: je Unterkonto im Export Anzeigename und Regel fuer den Kontonamen; default_wallet: dasselbe fuer alle uebrigen
    (label_prefix vor dem Namen im Export); pairing: "none", "group" (Beine mit gleicher Kennung "group": Handel bzw. Umschichtung) oder
    "time" (Umschichtung als Abgang und Zugang gleicher Menge binnen pair_window_minutes, Gegenseite pair_related_wallet);
    internal_transfers: Transfers zwischen Konten dieser Quelle gelten als Umschichtung (lockerer Abgleich bis 7 Tage); order_window_days:
    Auftraege werden bis so viele Tage nach der Anlage ausgefuehrt; unpaired_reason_by_ticker: Grund fuer einen Transfer ohne Gegenstueck je
    Coin; reason_texts: Texte der Gruende, die nur diese Quelle kennt (Platzhalter in geschweiften Klammern); format_label: Name des Formats
    in der Liste der lesbaren Exporte (ohne Angabe label)."""
    if not isinstance(value, Mapping) or not _SOURCE_FIELDS <= set(value) <= _SOURCE_FIELDS | _SOURCE_OPTIONAL:
        return None
    names, wallets, default = value["institution_names"], value["wallets"], value["default_wallet"]
    if not (isinstance(value["key"], str) and _SOURCE_KEY.match(value["key"]) and value["key"] != "generic" and _text(value["label"], 60)
            and isinstance(names, list) and len(names) <= 10 and all(_text(name, 80) for name in names)
            and isinstance(wallets, Mapping) and len(wallets) <= 20 and isinstance(default, Mapping) and set(default) == {"label_prefix", "account_name"}
            and isinstance(default["label_prefix"], str) and len(default["label_prefix"]) <= 30
            and value["pairing"] in ("none", "group", "time") and isinstance(value["internal_transfers"], bool)):
        return None
    if "format_label" in value and not _text(value["format_label"], 80):
        return None
    result: dict[str, Any] = {"key": value["key"], "label": value["label"], "format_label": value.get("format_label", value["label"]),
                              "institution_names": tuple(names), "pairing": value["pairing"],
                              "internal_transfers": value["internal_transfers"], "wallets": {}}
    for name, wallet in wallets.items():
        rule = _name_rule(wallet.get("account_name", {})) if isinstance(wallet, Mapping) else None
        if not (isinstance(name, str) and 1 <= len(name) <= 60 and isinstance(wallet, Mapping) and set(wallet) <= {"label", "account_name"}
                and _text(wallet.get("label"), 60) and rule is not None):
            return None
        result["wallets"][name] = {"label": wallet["label"], "account_name": rule}
    rule = _name_rule(default["account_name"])
    if rule is None:
        return None
    result["default_wallet"] = {"label_prefix": default["label_prefix"], "account_name": rule}
    if value["pairing"] == "time":
        minutes, related = value.get("pair_window_minutes"), value.get("pair_related_wallet")
        if not (isinstance(minutes, int) and not isinstance(minutes, bool) and 1 <= minutes <= 1440 and isinstance(related, str) and 1 <= len(related) <= 60):
            return None
        result["pair_window_minutes"], result["pair_related_wallet"] = minutes, related
    elif "pair_window_minutes" in value or "pair_related_wallet" in value:
        return None
    if "order_window_days" in value:
        days = value["order_window_days"]
        if not (isinstance(days, int) and not isinstance(days, bool) and 1 <= days <= 3650):
            return None
        result["order_window_days"] = days
    reasons = value.get("reason_texts", {})
    if not isinstance(reasons, Mapping) or len(reasons) > 40 or not all(isinstance(code, str) and _CODE.match(code) and _text(text, 400)
                                                                       for code, text in reasons.items()):
        return None
    result["reason_texts"] = dict(reasons)
    by_ticker = value.get("unpaired_reason_by_ticker", {})
    if not isinstance(by_ticker, Mapping) or len(by_ticker) > 40 or not all(isinstance(ticker, str) and _TICKER.match(ticker) and code in result["reason_texts"]
                                                                          for ticker, code in by_ticker.items()):
        return None
    result["unpaired_reason_by_ticker"] = dict(by_ticker)
    return result


def _format_checked(value: Any) -> dict[str, str] | None:
    """Pruefstand des Formats (Stufe 5): bis zu welchem Belegdatum der Leser an echten Belegen als richtig bestaetigt ist (through) und
    an welchem Tag das festgestellt wurde (checked_on). Neuere Vorgaenge liest der Kern und kennzeichnet sie."""
    if not isinstance(value, Mapping) or set(value) != {"through", "checked_on"}:
        return None
    try:
        through, checked_on = date.fromisoformat(value["through"]), date.fromisoformat(value["checked_on"])
    except (TypeError, ValueError):
        return None
    if not (_DAY.match(value["through"]) and _DAY.match(value["checked_on"]) and through <= checked_on):
        return None
    return {"through": value["through"], "checked_on": value["checked_on"]}


_PROFILE_KEY = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
INTAKE_PERIODS = ("since_start", "monthly", "per_document", "none")
INTAKE_DOMAINS = ("cash", "securities", "fx", "crypto", "reward")


def _text_list(value: Any, most: int, limit: int, least: int = 1) -> bool:
    return isinstance(value, list) and least <= len(value) <= most and all(_text(item, limit) for item in value)


def _intake(value: Any) -> dict[str, Any] | None:
    """Rezept des Eingangs (Stufe 5, #513/#486) fuer das Institut eines Plugins: Name, Stand (active oder historical, wenn es das
    Angebot nicht mehr gibt), Unterordner-Namen, was herunterzuladen ist, Zeitraumregel, was es abdeckt, die Leser in der Reihenfolge des
    Buchens (Bereich und Kennung, auch Leser anderer Plugins), die Woerter, an denen Institutsangaben der Konten das Institut erkennen,
    und ob eine Steuerunterlage ohne Kontonummer allen Konten des Instituts gilt."""
    keys = {"key", "label", "folders", "downloads", "period", "covers", "readers", "account_words", "tax_all_accounts"}
    if not isinstance(value, Mapping) or not keys <= set(value) <= keys | {"status"}:
        return None
    readers = value["readers"]
    if not (isinstance(value["key"], str) and _PROFILE_KEY.match(value["key"]) and _text(value["label"], 120)
            and value.get("status", "active") in ("active", "historical") and _text_list(value["folders"], 10, 60)
            and _text_list(value["downloads"], 6, 300) and value["period"] in INTAKE_PERIODS and _text(value["covers"], 200)
            and isinstance(readers, list) and len(readers) <= 10
            and all(isinstance(item, list) and len(item) == 2 and item[0] in INTAKE_DOMAINS and isinstance(item[1], str) and _READER_ID.match(item[1])
                    for item in readers)
            and _text_list(value["account_words"], 5, 60) and all(word == word.lower() for word in value["account_words"])
            and isinstance(value["tax_all_accounts"], bool)):
        return None
    return {"key": value["key"], "label": value["label"], "status": value.get("status", "active"), "folders": tuple(value["folders"]),
            "downloads": tuple(value["downloads"]), "period": value["period"], "covers": value["covers"],
            "readers": tuple((domain, reader_id) for domain, reader_id in readers), "account_words": tuple(value["account_words"]),
            "tax_all_accounts": value["tax_all_accounts"]}


def _securities_profiles(value: Any) -> dict[str, dict[str, Any]] | None:
    """Profile eines Wertpapier- oder Devisenlesers (Stufe 5), je Profil der Zeilen (Feld "profile"): label (Anzeige der Depots),
    institution_names (Teile des Institutsnamens fuer den Kontovorschlag), optional account_hint (Wort im Kontonamen, wenn ein Institut
    mehrere Profile hat) und depot_family (Profile mit gemeinsamen Depots, etwa zwei Aussteller desselben Brokers)."""
    if not isinstance(value, Mapping) or not 1 <= len(value) <= 20:
        return None
    result: dict[str, dict[str, Any]] = {}
    for key, item in value.items():
        if not (isinstance(key, str) and _PROFILE_KEY.match(key) and isinstance(item, Mapping)
                and {"label", "institution_names"} <= set(item) <= {"label", "institution_names", "account_hint", "depot_family"}
                and _text(item["label"], 80) and isinstance(item["institution_names"], list) and 1 <= len(item["institution_names"]) <= 10
                and all(_text(name, 80) for name in item["institution_names"])
                and ("account_hint" not in item or _text(item["account_hint"], 60))
                and ("depot_family" not in item or (isinstance(item["depot_family"], str) and _PROFILE_KEY.match(item["depot_family"])))):
            return None
        result[key] = {"label": item["label"], "institution_names": tuple(item["institution_names"]), "account_hint": item.get("account_hint"),
                       "depot_family": item.get("depot_family", key)}
    return result


_PROFILES_CACHE: list[Any] = [None, None]   # (Leserliste, Profile): neu berechnet, sobald die Leserliste neu geladen ist


def securities_profiles_v1() -> dict[str, Mapping[str, Any]]:
    """Profile aller geladenen Wertpapier- und Devisenleser, mit dem Bereich ihres Lesers; mitgelieferte zuerst, die erste Angabe gilt.
    Der Kern fragt je Vorgang; die Antwort gilt, solange die Leserliste dieselbe ist."""
    registry = _registry()[0]
    if _PROFILES_CACHE[0] is registry:
        return _PROFILES_CACHE[1]
    profiles: dict[str, Mapping[str, Any]] = {}
    for spec in sorted(registry.values(), key=lambda item: (item.origin != "shipped", item.domain, item.reader_id)):
        for key, item in (spec.profiles or {}).items():
            profiles.setdefault(key, {**item, "domain": spec.domain, "reader_id": spec.reader_id})
    _PROFILES_CACHE[:] = [registry, profiles]
    return profiles


def intake_recipes_v1() -> list[dict[str, Any]]:
    """Rezepte des Eingangs aller geladenen Plugins (Stufe 5), je Plugin eines: mitgelieferte zuerst; ein Rezept mit schon belegtem
    Schluessel zaehlt nicht. Jedes traegt die Kennung seines Plugins."""
    recipes: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for spec in sorted(reader_specs_v1(), key=lambda item: (item.origin != "shipped", item.plugin_id)):
        if spec.intake is None or spec.plugin_id in seen:
            continue
        seen.add(spec.plugin_id)
        recipes.setdefault(spec.intake["key"], {**spec.intake, "plugin_id": spec.plugin_id})
    return list(recipes.values())


def reward_reader_ids_v1() -> list[str]:
    """Die Reward-Leser aller geladenen Plugins (statt einer festen Liste im Kern, #486): mitgelieferte zuerst, je nach Kennung."""
    return [spec.reader_id for spec in sorted(reader_specs_v1("reward"), key=lambda item: (item.origin != "shipped", item.reader_id))]


def reward_reader_has_row_ids_v1(reader_id: Any) -> bool:
    """Traegt jede Zeile dieses Reward-Lesers eine eigene Kennung der Boerse (Manifest "row_ids")?"""
    spec = reader_spec_v1(reader_id, "reward") if isinstance(reader_id, str) else None
    return bool(spec is not None and spec.row_ids)


def plugin_account_words_v1(reader_id: str, domain: str) -> tuple[str, ...]:
    """Die Woerter, an denen Institutsangaben der Konten das Institut eines Lesers erkennen (Rezept seines Plugins), sonst keine."""
    spec = reader_spec_v1(reader_id, domain)
    return spec.intake["account_words"] if spec is not None and spec.intake is not None else ()


def crypto_source_profiles_v1() -> dict[str, Mapping[str, Any]]:
    """Quellangaben aller geladenen Krypto-Leser je Quelle (Stufe 5). Mitgelieferte zuerst; nennt ein installiertes Plugin eine schon
    belegte Quelle, gilt die erste."""
    profiles: dict[str, Mapping[str, Any]] = {}
    for spec in sorted(reader_specs_v1("crypto"), key=lambda item: (item.origin != "shipped", item.reader_id)):
        if spec.source is not None and spec.source["key"] not in profiles:
            profiles[spec.source["key"]] = spec.source
    return profiles


# Installierte Plugins (rc.381, #486): fremde Plugins liegen im Datenraum unter statement-reader-plugins-v1; welche Fassung gilt, nennt
# installed.json dort (plugin_id -> Ordner, dessen Name die plugin_id ist). Die Skripte setzen den Pfad aus dem Datenraum des Aufrufs
# (use_data_space_plugins_v1); ohne ihn laedt der Kern nur die mitgelieferten Plugins.
INSTALLED_ROOT_ENV = "PORTELYRA_INSTALLED_READER_PLUGINS"
_EXTERNAL_ONLY = False   # Selbsttest eines einzelnen Plugins: nur dieses, ohne installierte


_REFRESHERS: list[Any] = []


def register_registry_refresher_v1(refresh) -> None:
    """Module mit eigener Leserliste (Cash, Wertpapiere) bauen sie neu auf, sobald der Datenraum feststeht."""
    _REFRESHERS.append(refresh)


def use_data_space_plugins_v1(data_space_path: str | Path | None) -> None:
    """Installierte Plugins dieses Datenraums mitladen (oder mit None abschalten)."""
    if data_space_path is None:
        os.environ.pop(INSTALLED_ROOT_ENV, None)
    else:
        os.environ[INSTALLED_ROOT_ENV] = str(Path(data_space_path) / "statement-reader-plugins-v1")
    _registry.cache_clear()
    for refresh in list(_REFRESHERS):
        refresh()


def _installed_directories() -> list[tuple[str, Path]]:
    if _EXTERNAL_ONLY:
        return []
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
        return [("installed", Path("."))]   # als Problem gemeldet
    found = []
    for plugin_id, relative in sorted(mapping.items()) if isinstance(mapping, dict) else []:
        directory = _inside_directory(root, relative)
        found.append((plugin_id, directory if directory is not None else Path(".")))
    return found


def _inside_directory(root: Path, relative: Any) -> Path | None:
    """Ein Ordner unter root, ohne Ausbruch und ohne symbolische Verknuepfung (installierte Plugins)."""
    if not isinstance(relative, str) or relative.startswith("/") or ".." in Path(relative).parts:
        return None
    path = root / relative
    if path.is_symlink() or not path.is_dir():
        return None
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError):
        return None
    return path


@functools.lru_cache(maxsize=1)
def _registry() -> tuple[dict[tuple[str, str], ReaderSpec], tuple[tuple[str, str], ...]]:
    readers: dict[tuple[str, str], ReaderSpec] = {}
    problems: list[tuple[str, str]] = []
    if not PLUGIN_ROOT.is_dir():
        return readers, ()
    shipped_ids = set()
    for directory in sorted(path for path in PLUGIN_ROOT.iterdir() if path.is_dir() and not path.is_symlink() and path.name != "sdk"):
        manifest_path = directory / "manifest.json"
        if directory.name.startswith((".", "_")):
            continue
        try:
            if manifest_path.is_symlink() or not manifest_path.is_file():
                raise StatementReaderBlocked("statement_reader_manifest_invalid")
            specs = _manifest_readers(directory, json.loads(manifest_path.read_text(encoding="utf-8")))
            clash = [spec.reader_id for spec in specs if (spec.domain, spec.reader_id) in readers]
            if clash:
                raise StatementReaderBlocked("statement_reader_id_conflict")
            readers.update(((spec.domain, spec.reader_id), spec) for spec in specs)
            shipped_ids.add(directory.name)
        except StatementReaderBlocked as error:
            problems.append((directory.name, error.code))
        except (OSError, UnicodeError, ValueError):
            problems.append((directory.name, "statement_reader_manifest_invalid"))
    # Installierte Plugins nach den mitgelieferten. Gleiche Kennung wie ein mitgeliefertes Plugin: ein Update (#486 Schritt 3)
    # - es loest das mitgelieferte nur ab, wenn sein Paket jetzt gueltig von Portelyra signiert ist und seine Version hoeher ist.
    # Bringt ein spaeteres Release eine gleich hohe oder hoehere Fassung mit, gilt die mitgelieferte (die hoechste gilt), ohne Befund.
    shipped_versions = {spec.plugin_id: spec.plugin_version for spec in readers.values()}
    for plugin_id, directory in _installed_directories():
        try:
            manifest_path = directory / "manifest.json"
            if directory.name != plugin_id or directory.is_symlink() or manifest_path.is_symlink() or not manifest_path.is_file():
                raise StatementReaderBlocked("statement_reader_manifest_invalid")
            replaces = None
            if plugin_id in shipped_ids:
                update = _signed_update(directory, plugin_id)
                if update is None:
                    raise StatementReaderBlocked("statement_reader_update_signature_invalid")
                if not _newer(update, shipped_versions.get(plugin_id)):
                    continue
                replaces = shipped_versions.get(plugin_id)
                for key in [key for key, spec in readers.items() if spec.plugin_id == plugin_id]:
                    del readers[key]
            specs = [replace(spec, origin="installed", replaces_shipped=replaces)
                     for spec in _manifest_readers(directory, json.loads(manifest_path.read_text(encoding="utf-8")))]
            if any((spec.domain, spec.reader_id) in readers for spec in specs):
                raise StatementReaderBlocked("statement_reader_id_conflict")
            readers.update(((spec.domain, spec.reader_id), spec) for spec in specs)
        except StatementReaderBlocked as error:
            problems.append((plugin_id, error.code))
        except (OSError, UnicodeError, ValueError):
            problems.append((plugin_id, "statement_reader_manifest_invalid"))
    return readers, tuple(problems)


def _signed_update(directory: Path, plugin_id: str) -> str | None:
    """Version eines installierten Updates eines mitgelieferten Plugins, wenn sein Paket (package.json neben dem Plugin-Ordner) jetzt gueltig
    signiert ist und jede Datei stimmt; sonst None."""
    from migrations.reference import plugin_package_v1 as package_module  # noqa: PLC0415
    try:
        package = package_module.inspect_package_v1(directory.parent, kind="statement_reader")
    except package_module.PluginPackageBlocked:
        return None
    if package["signature"]["status"] != "valid" or package["plugin_id"] != plugin_id:
        return None
    return package["plugin_version"]


def _newer(candidate: str | None, current: str | None) -> bool:
    from migrations.reference import plugin_package_v1 as package_module  # noqa: PLC0415
    return package_module.newer_v1(candidate, current)


def reader_spec_v1(reader_id: str, domain: str = "cash") -> ReaderSpec | None:
    return _registry()[0].get((domain, reader_id))


def reader_specs_v1(domain: str | None = None) -> list[ReaderSpec]:
    return [spec for spec in _registry()[0].values() if domain is None or spec.domain == domain]


# Herkunft je Buchung (rc.378): Wer eine Buchung erzeugt hat - Plugin, Leser, Bereich, Version und eine Pruefsumme ueber den Code,
# der lief (Einstieg, Module, SDK). Eine Buchung aus einem geaenderten Leser traegt eine andere Pruefsumme, auch bei gleicher Version.
def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# Regeln im Manifest (#486): Seit Stufe 5 steuert das Manifest mit, wie Belege zu Buchungen werden -
# Erkennung, Dateiarten, Zusammenlesen, Quellangaben der Krypto-Leser (Unterkonten, Paarung, Fenster), Profile der Wertpapierleser
# (Depotfamilie, Institutsnamen) und das Institut. Diese Teile zaehlen zur Pruefsumme des Plugin-Codes; aendert ein Update nur sie,
# gilt der Leser wieder als ungeprueft. Aussen vor bleiben Beschreibungen (Namen, Formattexte, Grenzen, Handbuch, Testbelege, Version,
# Pruefstand des Formats, Texte der Gruende) und das Rezept des Eingangs, das nur ablegt und nichts bucht. Ein neues Feld zaehlt mit,
# bis es hier ausdruecklich als Beschreibung steht.
_DESCRIPTION_TOP = frozenset({"api_version", "api_minor", "plugin_version", "publisher", "label", "entry_point", "entry_point_sha256", "modules",
                              "handbook", "fixtures", "intake"})
_DESCRIPTION_READER = frozenset({"label", "document_kind", "tested_formats", "known_limits", "format_checked", "generator"})
_DESCRIPTION_SOURCE = frozenset({"label", "format_label", "reason_texts"})
_DESCRIPTION_PROFILE = frozenset({"label"})


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def manifest_rules_sha256_v1(manifest: Mapping[str, Any]) -> str:
    """Pruefsumme der Teile eines Manifests, die das Lesen und Buchen steuern (ohne Beschreibungen, siehe oben)."""
    readers = []
    for reader in manifest.get("readers") or []:
        item = {key: value for key, value in reader.items() if key not in _DESCRIPTION_READER}
        if isinstance(item.get("source"), Mapping):
            item["source"] = {key: value for key, value in item["source"].items() if key not in _DESCRIPTION_SOURCE}
        if isinstance(item.get("profiles"), Mapping):
            item["profiles"] = {name: {key: value for key, value in profile.items() if key not in _DESCRIPTION_PROFILE}
                                for name, profile in item["profiles"].items() if isinstance(profile, Mapping)}
        readers.append(item)
    rules = {key: value for key, value in manifest.items() if key not in _DESCRIPTION_TOP and key != "readers"}
    rules["readers"] = sorted(readers, key=lambda item: (str(item.get("domain")), str(item.get("reader_id"))))
    return _digest(rules)


# Umzug der Regeln in die Manifeste (rc.419): Bis rc.418 standen sie im Kern, und der Pruefstand band nur Einstieg und Module. Eine
# Pruefung aus dieser Zeit gilt weiter, solange die Regeln eines mitgelieferten Plugins genau dem Stand von rc.419 entsprechen.
# Aendert ein spaeteres Release die Regeln eines Plugins, faellt sein Eintrag hier weg -
# nie neu berechnen, sonst erbte die neue Regel die alte Pruefung.
# Gestrichen: bison (rc.434, #550: Leser fuer das Verrechnungskonto und Eingangsrezept neu - der Bison-Leser ist danach einmal
# "nicht geprueft"); smartbroker_plus (0.3.4, #550: der Devisen-Leser erkennt Dividendenabrechnungen mit Gutschrift in Fremdwaehrung,
# neue Erkennungsgruppe im Manifest - die Smartbroker+-Leser sind danach einmal "nicht geprueft", wie ohnehin nach der Aenderung am Leser).
RULES_BASELINE_RC419: dict[str, str] = {
    "baader": "c128fcf95ced7bd082159ef2cfd2626b7dac9c7fa77dcc443f3a269448e6461c",
    "bitbox": "55f1b670cef2992c177fc2235fe52157949dddc16914040d4db4cb8308df4de1",
    "bitcoin_de": "bfa826c97b401032fa3b5252cc0fbe264fd2b2e7b95fc1dc2ea83be97481251f",
    "bondora": "8a7de04d2fb9279d32a1bfa14c40da84d5354b6d06af22177261d4b4c38a4528",
    "bsdex": "6832168b91ac7ef43ad6199666afd67767cf14c35ae21e0ea91cc3b7a01bdf59",
    "c24": "7d86ed77813ee80f0de67a5cf9b024352655a922a2bd1006da26f9fd58ae1154",
    "check24": "c0d9e47ff98014bf64f251994251b7e38ba04776111f718844adb991e35a54bf",
    "coinbase": "953a743be9f8ae95c737344edbb5079d80417811695498f26b827e934380dc45",
    "dkb": "7281149024ea02670ad8224a8366cad75be3b622460091fd9f7bb98681433311",
    "ing": "7d3c5af87241fb4f1e2d338734d70963a276a70453da9fe63942150dfcd5a4ec",
    # kraken gestrichen in rc.425: Unterkonto-Verzeichnis im Manifest (Festlegung 16.11.2026) - Kraken einmalig wieder "nicht geprueft".
    "ledger": "a7f3bf7f0980e0c2648ee7b7f4e5c4ccb8e84c259bc58cae772879a50f7ffda7",
    "revolut": "57868605f4a84d0229f3ce7218b07764115f658b37f3c399dfb87364513b060a",
    "scalable_capital": "f3c6faec9521a350a8808d89ee881af9294da4ed0616db67fe7160b078bb0633",
    "trade_republic": "cddfe272af1c9f1271502bc23d2cc813ea86be09a699c9ab0478291c84dbbe5c",
}


def legacy_code_sha256s_v1(reader_id: str, domain: str) -> dict[str, str] | None:
    """Die Pruefsummen eines Lesers nach der Formel bis rc.418 (ohne Regeln), wenn eine damalige Pruefung noch gilt (siehe oben); sonst None.
    plugin_code_sha256 fuer den Pruefstand, code_sha256 fuer die Herkunft je Buchung."""
    spec = reader_spec_v1(reader_id, domain)
    if spec is None or spec.origin != "shipped" or RULES_BASELINE_RC419.get(spec.plugin_id) != spec.rules_sha256:
        return None
    code = {"entry": spec.entry_sha256, "modules": sorted(sha for _path, sha in spec.modules)}
    shared = {"sdk": _file_sha256(SDK_DIR / "portelyra_reader_sdk_v1.py"), "host": _file_sha256(HOST)}
    return {"plugin_code_sha256": _digest(code), "code_sha256": _digest({**code, **shared})}


def reader_identity_v1(reader_id: str, domain: str) -> dict[str, str]:
    """Kennung eines Leser-Plugins fuer die Herkunft je Buchung: {plugin_id, reader_id, domain, plugin_version, code_sha256}. Der Code umfasst
    Einstieg, Module, SDK, Host und die Regeln im Manifest."""
    spec = _spec(reader_id, domain)
    code = {"entry": spec.entry_sha256, "modules": sorted(sha for _path, sha in spec.modules),
            "sdk": _file_sha256(SDK_DIR / "portelyra_reader_sdk_v1.py"), "host": _file_sha256(HOST), "rules": spec.rules_sha256}
    return {"plugin_id": spec.plugin_id, "reader_id": spec.reader_id, "domain": spec.domain, "plugin_version": spec.plugin_version,
            "code_sha256": hashlib.sha256(json.dumps(code, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()}


def reader_check_identity_v1(reader_id: str, domain: str) -> dict[str, str]:
    """Kennung fuer den Pruefstand je Portfolio (rc.380, Festlegung vom 09.11.2026): Version = Pruefsumme ueber die eigenen
    Dateien des Plugins (Einstieg und Module) und die Regeln im Manifest (rc.419). SDK und Host zaehlen getrennt (shared_code_sha256) - eine
    Aenderung dort ist nur ein Hinweis."""
    spec = _spec(reader_id, domain)
    plugin_code = {"entry": spec.entry_sha256, "modules": sorted(sha for _path, sha in spec.modules), "rules": spec.rules_sha256}
    shared = {"sdk": _file_sha256(SDK_DIR / "portelyra_reader_sdk_v1.py"), "host": _file_sha256(HOST)}
    digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"plugin_id": spec.plugin_id, "reader_id": spec.reader_id, "domain": spec.domain, "plugin_version": spec.plugin_version,
            "plugin_code_sha256": digest(plugin_code), "shared_code_sha256": digest(shared)}


def core_reader_check_identity_v1(reader_id: str, domain: str, module_path: str | Path) -> dict[str, str]:
    """Pruefstand-Kennung eines Lesers im Kern (generische Leser): Pruefsumme der Kerndatei, ohne gemeinsamen Teil."""
    identity = core_reader_identity_v1(reader_id, domain, module_path)
    return {key: identity[key] for key in ("plugin_id", "reader_id", "domain", "plugin_version")} | {
        "plugin_code_sha256": identity["code_sha256"], "shared_code_sha256": ""}


def core_reader_identity_v1(reader_id: str, domain: str, module_path: str | Path) -> dict[str, str]:
    """Kennung eines Lesers im Kern (die generischen Leser): Produktversion und Pruefsumme der Kerndatei."""
    version_file = ROOT / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip() if version_file.is_file() else "0.0.0"
    return {"plugin_id": "portelyra_core", "reader_id": reader_id, "domain": domain, "plugin_version": version,
            "code_sha256": _file_sha256(Path(module_path))}


def reader_plugin_problems_v1() -> list[dict[str, str]]:
    """Plugins, die der Kern verworfen hat, mit Grund. Leer ist der Normalfall."""
    return [{"plugin_id": plugin_id, "code": code} for plugin_id, code in _registry()[1]]


def reader_public_v1(spec: ReaderSpec) -> dict[str, Any]:
    return {"reader_id": spec.reader_id, "plugin_id": spec.plugin_id, "plugin_version": spec.plugin_version,
            "publisher": spec.publisher, "institution": spec.institution, "domain": spec.domain, "label": spec.label,
            "document_kind": spec.document_kind, "extensions": list(spec.extensions), "tested_formats": spec.tested_formats,
            "known_limits": list(spec.known_limits)}


def detection_texts_v1(variants: Sequence[str]) -> tuple[str, ...]:
    """Vergleichstext fuer die Erkennungsregeln: Kleinbuchstaben, Leerraum je Zeile zusammengezogen."""
    return tuple("\n".join(" ".join(line.split()) for line in text.lower().splitlines()) for text in variants)


def detection_passes_v1(reader_id: str, texts: Sequence[str], domain: str = "cash") -> bool:
    """Erkennungsregeln des Manifests (#486) fuer einen Beleg: Eine Gruppe muss vollstaendig vorkommen, in einer seiner
    Textfassungen. Nur Teilzeichenketten, keine regulaeren Ausdruecke - schnell, nachvollziehbar und ohne Risiko fuer den Kern.
    Ohne Gruppen entscheidet allein die Dateiendung."""
    spec = reader_spec_v1(reader_id, domain)
    if spec is None:
        return False
    if not spec.match_any:
        return True
    return any(all(marker in text for marker in group) for text in texts for group in spec.match_any)


def _environment(private: Path) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(private), "TMPDIR": str(private),
            "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}


def _to_json(value: Any) -> Any:
    """Uebertragung zum Plugin: Dezimalzahlen bleiben exakt ({"decimal_text": "..."}), Zeitpunkte als ISO-Text, Tupel werden Listen
    (wie im SDK)."""
    if isinstance(value, Decimal):
        return {"decimal_text": str(value)}
    if isinstance(value, datetime):
        return {"datetime_text": value.isoformat()}
    if isinstance(value, (bytes, bytearray)):
        import base64  # noqa: PLC0415
        return {"bytes_base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dict):
        return {key: _to_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(item) for item in value]
    return value


def _from_json(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"decimal_text"} and isinstance(value["decimal_text"], str):
            try:
                return Decimal(value["decimal_text"])
            except InvalidOperation as exc:
                raise StatementReaderBlocked("statement_reader_output_invalid") from exc
        if set(value) == {"datetime_text"} and isinstance(value["datetime_text"], str):
            try:
                return datetime.fromisoformat(value["datetime_text"])
            except ValueError as exc:
                raise StatementReaderBlocked("statement_reader_output_invalid") from exc
        if set(value) == {"bytes_base64"} and isinstance(value["bytes_base64"], str):
            import base64  # noqa: PLC0415
            import binascii  # noqa: PLC0415
            try:
                return base64.b64decode(value["bytes_base64"], validate=True)
            except (binascii.Error, ValueError) as exc:
                raise StatementReaderBlocked("statement_reader_output_invalid") from exc
        return {key: _from_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_from_json(item) for item in value]
    return value


def _verified(spec: ReaderSpec) -> bool:
    try:
        return spec.entry.is_file() and _sha256(spec.entry) == spec.entry_sha256 and all(
            path.is_file() and _sha256(path) == sha for path, sha in spec.modules)
    except OSError:
        return False


def _checked(spec: ReaderSpec, payload: Any, count: int) -> list[dict[str, Any]]:
    """Form der Antwort des Hosts pruefen: je Auftrag ein Ergebnis oder ein Code aus der festen Liste."""
    if isinstance(payload, dict) and set(payload) == {"host_error"}:
        code = payload["host_error"] if payload["host_error"] in {"statement_reader_failed"} else "statement_reader_output_invalid"
        return [{"ok": False, "code": code} for _ in range(count)]
    results = payload.get("results") if isinstance(payload, dict) and set(payload) == {"results"} else None
    if not isinstance(results, list) or len(results) != count:
        raise StatementReaderBlocked("statement_reader_output_invalid")
    allowed = READER_ERROR_CODES[spec.domain] | SDK_ERROR_CODES | {"statement_reader_failed"}
    checked: list[dict[str, Any]] = []
    for item in results:
        if isinstance(item, dict) and set(item) == {"ok", "value"} and item["ok"] is True:
            checked.append({"ok": True, "value": _from_json(item["value"])})
        elif isinstance(item, dict) and set(item) == {"ok", "code"} and item["ok"] is False and isinstance(item["code"], str):
            # Mindestanforderung: nur Fehlercodes aus der festen Liste.
            checked.append({"ok": False, "code": item["code"] if item["code"] in allowed else "statement_reader_failed"})
        else:
            raise StatementReaderBlocked("statement_reader_output_invalid")
    return checked


def _command(spec: ReaderSpec, request: Path, output: Path, private: Path, inputs: Path, cpu_seconds: int) -> list[str]:
    return [sys.executable, "-B", str(SANDBOX), "--python", sys.executable, "--entry", str(HOST), "--source", str(request),
            "--output", str(output), "--temporary", str(private), "--support", str(spec.plugin_dir), "--support", str(SDK_DIR),
            "--support", str(inputs), "--timeout-seconds", str(cpu_seconds)]


# Offener Leserprozess je Vorgang (rc.375): Innerhalb einer Sitzung (reader_session_v1, z. B. ein Import-Stapel, eine Erkennung, ein
# Ablage-Vorschlag) bleibt je Plugin ein abgeschotteter Prozess offen und arbeitet die Auftraege nacheinander ab - dieselbe Sandbox,
# dieselben Grenzen, nur ohne Startaufwand je Aufruf (rund 60 ms). Mit dem Ende des Vorgangs endet der Prozess: Belege verschiedener
# Vorgaenge teilen sich nie einen Prozess, ein Leser kann nichts von einem Import in den naechsten tragen (Festlegung 08.11.2026).
# Rechenzeit gilt je Vorgang (WORKER_CPU_SECONDS); die Wartezeit je Auftrag begrenzt der Kern (TIMEOUT_SECONDS). Ohne Sitzung startet
# jeder Aufruf einen frischen Prozess.
WORKER_CPU_SECONDS = 900
MAX_WORKERS = 16
_SESSION_DEPTH = 0


class _Worker:
    def __init__(self, spec: ReaderSpec):
        self.key = _worker_key(spec)
        self.spec = spec
        self.temporary = Path(tempfile.mkdtemp(prefix="statement-reader-worker-"))
        os.chmod(self.temporary, 0o700)
        self.inputs, output, private = self.temporary / "inputs", self.temporary / "output", self.temporary / "tmp"
        for path in (self.inputs, output, private):
            path.mkdir(mode=0o700)
        request = self.temporary / "request.json"
        request.write_text(json.dumps({"api_version": API_VERSION, "serve": True, "entry": str(spec.entry), "plugin_dir": str(spec.plugin_dir),
                                       "sdk_dir": str(SDK_DIR)}), encoding="utf-8")
        self.process = subprocess.Popen(_command(spec, request, output, private, self.inputs, WORKER_CPU_SECONDS), stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=_environment(private), bufsize=0,
                                        start_new_session=True)
        self.calls = 0

    def call(self, spec: ReaderSpec, jobs: list[Any], writer) -> list[dict[str, Any]]:
        """Ein Auftragsbuendel an den offenen Prozess. Die erlaubten Fehlercodes richten sich nach dem Leser dieses Auftrags, nicht
        nach dem, der den Prozess gestartet hat: Alle Leser eines Plugins teilen sich im Vorgang einen Prozess (gefunden vom
        Selbsttest in rc.379 - ein Reward-Code im Prozess eines Cash-Lesers wurde zu statement_reader_failed)."""
        reader_id = spec.reader_id
        import secrets
        import selectors
        import time
        self.calls += 1
        call_dir = self.inputs / f"{self.calls:06d}"
        call_dir.mkdir(mode=0o700)
        try:
            request_jobs = [writer(call_dir, index, job) for index, job in enumerate(jobs, 1)]
            nonce = secrets.token_hex(16)
            line = json.dumps({"nonce": nonce, "reader_id": reader_id, "jobs": request_jobs}).encode("utf-8") + b"\n"
            try:
                self.process.stdin.write(line)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.close()
                raise StatementReaderBlocked(self._dead_code())
            buffer = bytearray()
            deadline = time.monotonic() + TIMEOUT_SECONDS
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                while b"\n" not in buffer:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(timeout=remaining):
                        self.close()
                        raise StatementReaderBlocked("statement_reader_timeout")
                    chunk = os.read(self.process.stdout.fileno(), 1 << 20)
                    if not chunk:
                        self.close()
                        raise StatementReaderBlocked(self._dead_code())
                    buffer += chunk
                    if len(buffer) > MAX_RESULT_BYTES:
                        self.close()
                        raise StatementReaderBlocked("statement_reader_output_invalid")
            try:
                payload = json.loads(bytes(buffer[:buffer.index(b"\n")]).decode("utf-8"))
            except (UnicodeError, ValueError) as exc:
                self.close()
                raise StatementReaderBlocked("statement_reader_output_invalid") from exc
            if not isinstance(payload, dict) or payload.pop("nonce", None) != nonce:
                self.close()
                raise StatementReaderBlocked("statement_reader_output_invalid")
            return _checked(spec, payload, len(jobs))
        finally:
            shutil.rmtree(call_dir, ignore_errors=True)

    def _dead_code(self) -> str:
        try:
            code = self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return "statement_reader_failed"
        return "statement_reader_isolation_unavailable" if code == 78 else "statement_reader_failed"

    def close(self) -> None:
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


def _worker_key(spec: ReaderSpec) -> tuple:
    # Ein Prozess gehoert zu genau diesem Code (Pruefsummen) an genau diesem Ort, mit genau dieser Sandbox.
    return (str(spec.plugin_dir), spec.entry_sha256, tuple(sha for _path, sha in spec.modules), str(SANDBOX), str(HOST), str(SDK_DIR))


def close_reader_workers_v1() -> None:
    """Beendet alle offenen Leserprozesse (auch beim Ende des aufrufenden Prozesses)."""
    for worker in list(_WORKERS.values()):
        worker.close()


import atexit  # noqa: E402 - gehoert zur Verwaltung der Leserprozesse
import contextlib  # noqa: E402
atexit.register(close_reader_workers_v1)


@contextlib.contextmanager
def reader_session_v1():
    """Ein Vorgang: Leserprozesse bleiben bis zu seinem Ende offen und werden dann beendet. Verschachtelte Sitzungen gehoeren zur
    aeussersten."""
    global _SESSION_DEPTH
    _SESSION_DEPTH += 1
    try:
        yield
    finally:
        _SESSION_DEPTH -= 1
        if _SESSION_DEPTH == 0:
            close_reader_workers_v1()


def within_reader_session(function):
    """Macht eine Funktion zu einem Vorgang (reader_session_v1)."""
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with reader_session_v1():
            return function(*args, **kwargs)
    return wrapper


def _run(spec: ReaderSpec, jobs: list[dict[str, Any]], writer) -> list[dict[str, Any]]:
    """Alle Auftraege an einen Leser in einem abgeschotteten Prozess. ``writer(inputs, index, job)`` legt die Eingabe eines Auftrags
    im gebundenen Eingabeordner ab. Infrastrukturfehler brechen den ganzen Aufruf ab."""
    if not _verified(spec):
        raise StatementReaderBlocked("statement_reader_unavailable")
    if not SANDBOX.is_file() or not HOST.is_file():
        raise StatementReaderBlocked("statement_reader_isolation_unavailable")
    if _SESSION_DEPTH > 0:
        key = _worker_key(spec)
        worker = _WORKERS.get(key)
        if worker is None or worker.process.poll() is not None:
            if worker is not None:
                worker.close()
            while len(_WORKERS) >= MAX_WORKERS:
                next(iter(_WORKERS.values())).close()
            worker = _WORKERS[key] = _Worker(spec)
        return worker.call(spec, jobs, writer)
    temporary = Path(tempfile.mkdtemp(prefix="statement-reader-"))
    try:
        os.chmod(temporary, 0o700)
        inputs, output, private = temporary / "inputs", temporary / "output", temporary / "tmp"
        for path in (inputs, output, private):
            path.mkdir(mode=0o700)
        request_jobs = [writer(inputs, index, job) for index, job in enumerate(jobs, 1)]
        request = temporary / "request.json"
        request.write_text(json.dumps({"api_version": API_VERSION, "reader_id": spec.reader_id, "entry": str(spec.entry),
                                       "plugin_dir": str(spec.plugin_dir), "sdk_dir": str(SDK_DIR), "jobs": request_jobs}), encoding="utf-8")
        try:
            completed = subprocess.run(_command(spec, request, output, private, inputs, TIMEOUT_SECONDS), stdin=subprocess.DEVNULL,
                                       capture_output=True, env=_environment(private), timeout=TIMEOUT_SECONDS + 10, start_new_session=True)
        except subprocess.TimeoutExpired as exc:
            raise StatementReaderBlocked("statement_reader_timeout") from exc
        if completed.returncode == 78:
            raise StatementReaderBlocked("statement_reader_isolation_unavailable")
        if completed.returncode != 0:
            # Grenzen der Sandbox (Rechenzeit, Speicher, Dateigroesse) beenden den Prozess hart.
            raise StatementReaderBlocked("statement_reader_failed")
        entries = list(output.iterdir())
        result_path = output / "result.json"
        if [entry.name for entry in entries] != ["result.json"] or result_path.is_symlink() or not result_path.is_file() \
                or result_path.stat().st_size > MAX_RESULT_BYTES:
            raise StatementReaderBlocked("statement_reader_output_invalid")
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise StatementReaderBlocked("statement_reader_output_invalid") from exc
        return _checked(spec, payload, len(jobs))
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def _spec(reader_id: str, domain: str) -> ReaderSpec:
    spec = reader_spec_v1(reader_id, domain)
    if spec is None:
        raise StatementReaderBlocked("statement_reader_unavailable")
    return spec


def run_reader_v1(reader_id: str, documents: Sequence[tuple[bytes, str, Sequence[str] | None]], domain: str = "cash") -> list[dict[str, Any]]:
    """Belege als Bytes (Bereich cash): je Dokument ``{"ok": True, "value": ...}`` oder ``{"ok": False, "code": ...}``."""
    spec = _spec(reader_id, domain)
    if domain not in BYTE_DOMAINS:
        raise StatementReaderBlocked("statement_reader_unavailable")

    def write(inputs: Path, index: int, document: tuple[bytes, str, Sequence[str] | None]) -> dict[str, Any]:
        source, file_name, lines = document
        path = inputs / f"{index:05d}.bin"
        path.write_bytes(source)
        lines_path = None
        if lines is not None:
            lines_path = inputs / f"{index:05d}.lines.json"
            lines_path.write_text(json.dumps(list(lines), ensure_ascii=False), encoding="utf-8")
        return {"op": "read", "path": str(path), "file_name": file_name, "lines_path": None if lines_path is None else str(lines_path)}
    return _run(spec, list(documents), write)


def _document_writer(inputs: Path, index: int, document: tuple[bytes, str, Sequence[str] | None], suffix: str = "") -> dict[str, Any]:
    source, file_name, lines = document
    path = inputs / f"{index:05d}{suffix}.bin"
    path.write_bytes(source)
    lines_path = None
    if lines is not None:
        lines_path = inputs / f"{index:05d}{suffix}.lines.json"
        lines_path.write_text(json.dumps(list(lines), ensure_ascii=False), encoding="utf-8")
    return {"path": str(path), "file_name": file_name, "lines_path": None if lines_path is None else str(lines_path)}


def run_combine_documents_v1(reader_id: str, documents: Sequence[tuple[bytes, str, Sequence[str] | None]], domain: str = "cash") -> dict[str, Any]:
    """Mehrere Belege eines Instituts zusammen lesen (Bytes; BSDEX: Export und Jahreshistorie). Ein Auftrag, ein Ergebnis."""
    spec = _spec(reader_id, domain)
    if domain not in BYTE_DOMAINS:
        raise StatementReaderBlocked("statement_reader_unavailable")

    def write(inputs: Path, index: int, items: Sequence[Any]) -> dict[str, Any]:
        return {"op": "combine_documents", "documents": [_document_writer(inputs, index, item, f"_{position:04d}") for position, item in enumerate(items, 1)]}
    return _run(spec, [list(documents)], write)[0]


def run_combine_rows_v1(reader_id: str, domain: str, batch: Mapping[str, Any]) -> dict[str, Any]:
    """Zeilen eines Instituts zusammen mit seinem zweiten Beleg lesen (Krypto; BSDEX). Was davon gilt, entscheidet apply_crypto_combine_v1."""
    spec = _spec(reader_id, domain)
    if domain in BYTE_DOMAINS or not spec.combine:   # nur ein Leser, der "combine" im Manifest erklaert
        raise StatementReaderBlocked("statement_reader_unavailable")
    return _run(spec, [dict(batch)], _text_writer("combine_rows"))[0]


def _text_writer(op: str):
    def write(inputs: Path, index: int, item: Any) -> dict[str, Any]:
        path = inputs / f"{index:05d}.json"
        if op in ("finish", "combine_rows"):
            path.write_text(json.dumps(_to_json(item), ensure_ascii=False), encoding="utf-8")
            return {"op": op, "payload_path": str(path)}
        text, file_name = (item, "") if op == "detect" else item
        path.write_text(json.dumps(text, ensure_ascii=False), encoding="utf-8")
        return {"op": op, "text_path": str(path), "file_name": file_name}
    return write


def run_generate_v1(reader_id: str, domain: str, seeds: Sequence[int]) -> list[dict[str, Any]]:
    """Selbsttest Stufe 3 (rc.379): Der Erzeuger des Plugins baut je Startwert einen erfundenen Beleg samt erwartetem Ergebnis -
    {"file_name", "content" (Bytes oder Text), "expected"}. Nur Leser mit "generator": true. Was der Erzeuger liefert, prueft der
    Selbsttest (statement_reader_selftest_v1); hier nur die Form."""
    spec = _spec(reader_id, domain)
    if not spec.generator:
        raise StatementReaderBlocked("statement_reader_unavailable")

    def write(inputs: Path, index: int, seed: int) -> dict[str, Any]:
        return {"op": "generate", "seed": int(seed), "domain": spec.domain}   # eine Kennung gilt je Bereich (trade_republic_v1)
    results = _run(spec, [int(seed) for seed in seeds], write)
    for item in results:
        value = item.get("value")
        if item["ok"] and not (isinstance(value, dict) and set(value) == {"file_name", "content", "expected"} and isinstance(value["file_name"], str)
                               and 0 < len(value["file_name"]) <= 120 and isinstance(value["content"], (bytes, str)) and len(value["content"]) <= 4_000_000):
            raise StatementReaderBlocked("statement_reader_output_invalid")
    return results


def run_text_reader_v1(reader_id: str, domain: str, items: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
    """Belege als Text (Bereiche securities, fx): read_text je Beleg in einem Aufruf."""
    spec = _spec(reader_id, domain)
    if domain in BYTE_DOMAINS:
        raise StatementReaderBlocked("statement_reader_unavailable")
    return _run(spec, list(items), _text_writer("read_text"))


def run_detect_v1(reader_id: str, domain: str, texts: Sequence[str]) -> list[dict[str, Any]]:
    """Erkennung des Lesers je Text in einem Aufruf; der Kern hat vorher nach den Regeln des Manifests ausgesiebt."""
    spec = _spec(reader_id, domain)
    if domain in BYTE_DOMAINS:
        raise StatementReaderBlocked("statement_reader_unavailable")
    results = _run(spec, list(texts), _text_writer("detect"))
    if any(item["ok"] and not isinstance(item["value"], bool) for item in results):
        raise StatementReaderBlocked("statement_reader_output_invalid")
    return results


def run_finish_v1(reader_id: str, domain: str, batch: Mapping[str, Any]) -> dict[str, Any]:
    """Nachbearbeitung ueber den Stapel. Gibt nur das Ergebnis zurueck; was davon gilt, entscheidet der Aufrufer."""
    spec = _spec(reader_id, domain)
    if domain in BYTE_DOMAINS:
        raise StatementReaderBlocked("statement_reader_unavailable")
    return _run(spec, [dict(batch)], _text_writer("finish"))[0]


def reference_date_v1() -> str:
    """Heute nach dem Rechner (lokales Datum), oder der gesetzte Bezugstag der Vertragstests."""
    value = os.environ.get(REFERENCE_DATE_ENV, "")
    if _DAY.match(value):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    return date.today().isoformat()


def _day(value: Any, today: str | None, optional: bool = False) -> bool:
    """Gueltiges ISO-Datum; mit ``today`` zudem nicht in der Zukunft (Buchungstage). Zeitraumangaben duerfen in die Zukunft
    reichen: Ein Monatsauszug, mitten im Monat geladen, nennt das Monatsende."""
    if value is None:
        return optional
    if not isinstance(value, str) or not _DAY.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return today is None or value <= today


def validate_cash_result_v1(value: Any, today: str | None = None, plausibility: bool = True) -> dict[str, Any]:
    """Schema des Bereichs cash (cash-result.schema.json) samt Plausibilitaet. Jede Abweichung verwirft das Ergebnis des Belegs
    (Mindestanforderung 2): exakte Dezimalzahlen als Text, gueltige ISO-Daten, kein Buchungs- oder Wertstellungstag nach heute,
    jede Buchung im genannten Zeitraum des Belegs, nur erlaubte Arten, Betraege positiv. Ein Tag nach heute heisst fast immer: Der Leser hat das Jahr falsch erschlossen (alte
    DKB-Vorlage ohne Jahr, Trade Republic ueber drei Zeilen). Kein echter Beleg hat einen
    Buchungstag nach dem Tag seiner Ablage. Zeitraumangaben duerfen in die Zukunft reichen.
    plausibility=False prueft nur die Form (Selbsttest Stufe 2, rc.379): ohne "nicht nach heute" und ohne den Auszugszeitraum."""
    today = (today or reference_date_v1()) if plausibility else None
    bad = StatementReaderBlocked("statement_reader_output_invalid")
    if not isinstance(value, dict) or not {"candidates", "diagnostics", "summary"} <= set(value) \
            or not set(value) <= {"candidates", "diagnostics", "summary", "balance_proof", "balance_anchor_only"}:
        raise bad
    if any(key in value and not isinstance(value[key], bool) for key in ("balance_proof", "balance_anchor_only")):
        raise bad
    candidates, diagnostics, summary = value["candidates"], value["diagnostics"], value["summary"]
    if not isinstance(candidates, list) or not isinstance(diagnostics, list) or len(candidates) + len(diagnostics) > MAX_ROWS:
        raise bad
    required = {"source_row_ordinal", "local_date", "kind", "amount_decimal", "balance_after_decimal", "text"}
    for row in candidates:
        if not isinstance(row, dict) or not required <= set(row) or not set(row) <= required | {"value_date", "gross_income_decimal"}:
            raise bad
        ordinal = row["source_row_ordinal"]
        if not (isinstance(ordinal, int) and not isinstance(ordinal, bool) and ordinal >= 1
                and _day(row["local_date"], today) and row["kind"] in {"interest", "deposit", "withdrawal"}
                and isinstance(row["amount_decimal"], str) and _POSITIVE.match(row["amount_decimal"]) and row["amount_decimal"].strip("0.") != ""
                and (row["balance_after_decimal"] is None or (isinstance(row["balance_after_decimal"], str) and _SIGNED.match(row["balance_after_decimal"])))
                and isinstance(row["text"], str) and len(row["text"]) <= 4000
                and ("value_date" not in row or _day(row["value_date"], today))
                and ("gross_income_decimal" not in row or (isinstance(row["gross_income_decimal"], str) and _POSITIVE.match(row["gross_income_decimal"])))):
            raise bad
    for row in diagnostics:
        if not isinstance(row, dict) or not {"source_row_ordinal", "reason_code"} <= set(row) \
                or not set(row) <= {"source_row_ordinal", "reason_code", "gross_income_decimal", "as_of_date"}:
            raise bad
        ordinal = row["source_row_ordinal"]
        if not (isinstance(ordinal, int) and not isinstance(ordinal, bool) and ordinal >= 0
                and isinstance(row["reason_code"], str) and _CODE.match(row["reason_code"])
                and ("gross_income_decimal" not in row or (isinstance(row["gross_income_decimal"], str) and _POSITIVE.match(row["gross_income_decimal"])))
                and ("as_of_date" not in row or _day(row["as_of_date"], today))):
            raise bad
    basic = {"opening_balance_decimal", "closing_balance_decimal", "period_from", "period_to"}
    if not isinstance(summary, dict) or not basic <= set(summary) or not set(summary) <= basic | {"closing_as_of_date"}:
        raise bad
    for key in ("opening_balance_decimal", "closing_balance_decimal"):
        if summary[key] is not None and not (isinstance(summary[key], str) and _SIGNED.match(summary[key])):
            raise bad
    if not all(_day(summary.get(key), None, optional=True) for key in ("period_from", "period_to", "closing_as_of_date")):
        raise bad
    # Nennt der Beleg seinen Zeitraum, liegt jede Buchung darin (Festlegung 07.11.2026). Faengt ein falsch erschlossenes Jahr auch bei
    # alten Auszuegen, wo die Regel "nicht nach heute" nicht greift.
    period_from, period_to = summary["period_from"], summary["period_to"]
    if plausibility and period_from is not None and period_to is not None:
        if period_from > period_to or any(not period_from <= row["local_date"] <= period_to for row in candidates):
            raise bad
    return value


# ---------------------------------------------------------------- Bereiche securities und fx (rc.374)
SECURITY_KINDS = frozenset({"buy", "sell", "dividend", "deposit", "advance_lump_sum", "stock_split"})
_DECIMAL_FIELDS = ("quantity", "unit_price", "gross_amount", "fee_amount", "eligible_quantity", "net_amount", "taxes_amount",
                   "withholding_amount", "bank_gain", "credited_quantity", "ratio_numerator", "ratio_denominator")
_DATE_FIELDS = ("ex_date", "valuta", "record_date")
_TEXT_FIELDS = ("profile", "isin", "security_name", "order_ref", "depot_ref", "currency")
_CANDIDATE_KEYS = frozenset({"status", "kind", "local_date", "local_time", "fee_on_cash_statement", "statement_checked", "calculation_year",
                             "executed_at_utc", "export_position", *_DECIMAL_FIELDS, *_DATE_FIELDS, *_TEXT_FIELDS})
# Was eine Nachbearbeitung aendern darf: nur die Ordnung am Tag (Uhrzeit, Ausfuehrungsgruppe, getrennte Teilausfuehrungen).
FINISH_FIELDS = ("local_time", "executed_local_time", "execution_group", "separate_executions")
_TIME = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$")   # einmal definiert; galt durch die spaetere Zuweisung schon so
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|\+00:00)$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


def _candidate_valid(row: Any, today: str) -> bool:
    if not isinstance(row, dict) or row.get("status") != "candidate" or not set(row) <= _CANDIDATE_KEYS \
            or not {"kind", "profile", "local_date"} <= set(row) or row["kind"] not in SECURITY_KINDS:
        return False
    if not _day(row["local_date"], today) or not all(row.get(key) is None or _day(row[key], None) for key in _DATE_FIELDS):
        return False
    if row.get("local_time") is not None and not (isinstance(row["local_time"], str) and _TIME.match(row["local_time"])):
        return False
    if not all(row.get(key) is None or (isinstance(row[key], str) and _SIGNED.match(row[key])) for key in _DECIMAL_FIELDS):
        return False
    if any(row.get(key) is not None and (not isinstance(row[key], str) or row[key].startswith("-")) for key in ("quantity", "unit_price")):
        return False
    if not all(row.get(key) is None or (isinstance(row[key], str) and len(row[key]) <= 400) for key in _TEXT_FIELDS):
        return False
    # "Abgeglichen" setzt nur die Saldoprobe des Kerns; ein Plugin meldet seine eigenen Belege nie als geprueft.
    if row.get("statement_checked") not in (None, False):
        return False
    return (all(key not in row or isinstance(row[key], bool) for key in ("fee_on_cash_statement", "statement_checked"))
            and all(key not in row or (isinstance(row[key], int) and not isinstance(row[key], bool)) for key in ("calculation_year", "export_position"))
            and ("executed_at_utc" not in row or (isinstance(row["executed_at_utc"], str) and _UTC.match(row["executed_at_utc"]) is not None)))


def _balance_valid(value: Any) -> bool:
    return value is None or (isinstance(value, list) and len(value) == 2 and (value[0] is None or _day(value[0], None))
                             and isinstance(value[1], Decimal) and value[1].is_finite())


def validate_securities_result_v1(value: Any, reasons: Mapping[str, str], today: str | None = None, plausibility: bool = True) -> dict[str, Any]:
    """Ergebnis eines Wertpapier- oder Devisenlesers fuer einen Beleg (Mindestanforderung 2): ein Vorgang, ein Grund aus der festen
    Liste, ein Export mit vielen Vorgaengen oder ein Kontoauszug als Saldo-Anker. Stueckzahl und Kurs nie negativ, Dezimalzahlen
    exakt als Text, kein Buchungstag nach heute. Den Text eines Grundes setzt der Kern."""
    today = (today or reference_date_v1()) if plausibility else None   # Selbsttest Stufe 2: nur die Form
    bad = StatementReaderBlocked("statement_reader_output_invalid")
    if not isinstance(value, dict):
        raise bad
    status = value.get("status")
    if status == "candidate":
        if not _candidate_valid(value, today):
            raise bad
    elif status == "not_importable":
        if not set(value) <= {"status", "reason_code", "reason", "depot_ref"} or value.get("reason_code") not in reasons \
                or not (value.get("depot_ref") is None or isinstance(value["depot_ref"], str)):
            raise bad
        value["reason"] = reasons[value["reason_code"]]
    elif status == "multi":
        rows = value.get("row_reasons")
        if set(value) != {"status", "candidates", "row_reasons"} or not isinstance(value["candidates"], list) \
                or len(value["candidates"]) > MAX_ROWS or not isinstance(rows, dict) \
                or not all(code in reasons and isinstance(count, int) and not isinstance(count, bool) and count >= 1 for code, count in rows.items()) \
                or not all(_candidate_valid(row, today) for row in value["candidates"]):
            raise bad
    elif status == "statement":
        lines = value.get("lines")
        if set(value) != {"status", "currency", "lines", "start", "end"} or not (isinstance(value["currency"], str) and _CURRENCY.match(value["currency"])) \
                or not isinstance(lines, list) or len(lines) > MAX_ROWS or not _balance_valid(value["start"]) or not _balance_valid(value["end"]):
            raise bad
        for line in lines:
            if not (isinstance(line, dict) and set(line) == {"booked", "valuta", "text", "amount", "kinds"} and _day(line["booked"], today)
                    and _day(line["valuta"], None) and isinstance(line["text"], str) and len(line["text"]) <= 4000
                    and isinstance(line["amount"], Decimal) and line["amount"].is_finite() and line["amount"] != 0
                    and isinstance(line["kinds"], list) and line["kinds"] and set(line["kinds"]) <= SECURITY_KINDS):
                raise bad
    else:
        raise bad
    return value


def apply_finish_v1(candidates: list[dict[str, Any]], returned: Any) -> None:
    """Uebernimmt aus der Nachbearbeitung eines Plugins nur die Ordnung am Tag (FINISH_FIELDS) - in die Kandidaten des Kerns.
    Gleiche Zahl, gleiche Reihenfolge, gleiche Belegkennung; Betraege, Stuecke, Daten und Gruende kann ein Plugin so nicht aendern."""
    bad = StatementReaderBlocked("statement_reader_output_invalid")
    rows = returned.get("candidates") if isinstance(returned, dict) else None
    if not isinstance(rows, list) or len(rows) != len(candidates):
        raise bad
    updates = []
    for mine, theirs in zip(candidates, rows):
        if not isinstance(theirs, dict) or theirs.get("candidate_ordinal") != mine.get("candidate_ordinal") \
                or theirs.get("candidate_key") != mine.get("candidate_key"):
            raise bad
        change = {key: theirs[key] for key in FINISH_FIELDS if key in theirs and theirs[key] != mine.get(key)}
        if any(theirs.get(key) != mine.get(key) for key in set(theirs) | set(mine) if key not in FINISH_FIELDS):
            raise bad
        if not (all(change.get(key) is None or (isinstance(change[key], str) and _TIME.match(change[key])) for key in ("local_time", "executed_local_time"))
                and ("separate_executions" not in change or isinstance(change["separate_executions"], bool))
                and ("execution_group" not in change or (isinstance(change["execution_group"], (str, int)) and not isinstance(change["execution_group"], bool)))):
            raise bad
        updates.append(change)
    for mine, change in zip(candidates, updates):
        mine.update(change)


# ---------------------------------------------------------------- Bereich crypto und gemeinsames Lesen (rc.376)
# Die Arten, die der Kern weiterverarbeitet (assemble_crypto_operations_v1); unpriced_trade setzt nur das gemeinsame Lesen.
CRYPTO_KINDS = frozenset({"trade", "trade_coin", "trade_eur", "swap", "move", "move_unknown", "internal", "internal_staking", "internal_unstaking",
                          "fee_only", "order"})
_CRYPTO_REQUIRED = ("profile", "source", "file_name", "row_no", "wallet", "at_utc", "zone", "ticker", "kind", "quantity", "fee_quantity", "eur",
                    "eur_fee", "transaction_id", "hash", "address", "group", "quote", "row_key")
_AT_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_SOURCE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_FILL_KEYS = frozenset({"id", "ordinal", "file_name", "side", "asset", "quantity", "eur", "fee", "at"})
# Gemeinsames Lesen (BSDEX): Der genaue Betrag je Order darf vom gerundeten des Exports hoechstens so weit abweichen.
COMBINE_EUR_TOLERANCE = Decimal("0.05")
# Weicht eine einzelne Order ab, bleibt nur sie offen (mismatched_trade, eigener Grund) - der Stapel laeuft weiter. Weichen mehr als ein
# Viertel der Orders ab (mindestens zwei), rechnet der Leser systematisch falsch: dann wird das ganze Ergebnis verworfen (Festlegung
# 08.11.2026).
COMBINE_SYSTEMATIC_SHARE = Decimal("0.25")
# Eine offene Order (unpriced_trade) nennt immer ihren Grund aus dieser Liste (Festlegung 08.11.2026: Transparenz), beim
# abweichenden Betrag Kurswert und Gebuehr der Ausfuehrungen, bei einer zu alten Historie deren Ende. Den Text setzt der Kern.
UNPRICED_REASONS = frozenset(("history_missing", "history_outdated", "no_executions", "quantity_differs", "amount_differs", "ambiguous"))
UNPRICED_FIELDS = ("unpriced_reason", "executions_eur", "executions_fee", "history_until", "history_year")


def _unpriced_valid(row: Mapping[str, Any]) -> bool:
    reason = row.get("unpriced_reason")
    if reason not in UNPRICED_REASONS:
        return False
    needed = {"unpriced_reason"} | ({"executions_eur", "executions_fee"} if reason == "amount_differs" else set()) \
        | ({"history_until"} if reason == "history_outdated" else set()) | ({"history_year"} if reason == "history_missing" else set())
    return ({key for key in UNPRICED_FIELDS if key in row} == needed
            and all(isinstance(row[key], str) and _POSITIVE.match(row[key]) for key in ("executions_eur", "executions_fee") if key in needed)
            and ("history_until" not in needed or (isinstance(row["history_until"], str) and _DAY.match(row["history_until"]) is not None))
            and ("history_year" not in needed or (isinstance(row["history_year"], str) and re.fullmatch(r"[0-9]{4}", row["history_year"]) is not None)))
COMBINE_FIELDS = ("quantity", "eur", "eur_fee", "at_utc", "kind", "row_key")
# Verworfene Zeilen einzeln (rc.379, Vorgabe: Zeile und Feld als Grund): je Zeile Nummer, Grund, Feld und Problem aus
# festen Listen, dazu wenn bekannt die Zeile der Datei ("line", wie in einer Tabellenkalkulation); den Text in der Vorschau setzt der Kern
# (crypto_statement_import_v1.crypto_row_detail_reason_v1).
CRYPTO_DETAIL_FIELDS = frozenset(("time", "ticker", "quantity", "fee_quantity", "eur", "eur_fee", "price", "number", "wallet", "transaction_id",
                                  "hash", "address", "group", "quote", "file_name", "zone"))
CRYPTO_DETAIL_PROBLEMS = frozenset(("missing", "unreadable", "negative", "too_long", "out_of_range"))


def _crypto_details_valid(details: Any, counts: Mapping[str, int]) -> bool:
    if not isinstance(details, list) or not details or len(details) > MAX_ROWS:
        return False
    per_code: dict[str, int] = {}
    for item in details:
        if not (isinstance(item, dict) and {"row_no", "reason_code", "field", "problem"} <= set(item) <= {"row_no", "reason_code", "field", "problem", "line"}
                and isinstance(item["row_no"], int) and not isinstance(item["row_no"], bool) and item["row_no"] >= 0
                and ("line" not in item or (isinstance(item["line"], int) and not isinstance(item["line"], bool) and item["line"] >= 1))
                and item["reason_code"] in counts and item["field"] in CRYPTO_DETAIL_FIELDS and item["problem"] in CRYPTO_DETAIL_PROBLEMS):
            return False
        per_code[item["reason_code"]] = per_code.get(item["reason_code"], 0) + 1
    # Nie mehr einzelne Zeilen als gezaehlte: jede Einzelangabe gehoert zu einer gezaehlten Zeile.
    return all(count <= counts[code] for code, count in per_code.items())


def crypto_row_key_v1(row: Mapping[str, Any]) -> str:
    """Kennung einer Krypto-Zeile wie im Kern (_row_key): der Kern rechnet sie nach."""
    payload = ["crypto_row", row["source"], row["wallet"], row["at_utc"], row["ticker"], row["kind"], row["quantity"], row["fee_quantity"], row["eur"],
               row["transaction_id"], row["hash"], row["group"]]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _utc_day(value: Any, today: str | None) -> bool:
    return isinstance(value, str) and _AT_UTC.match(value) is not None and _day(value[:10], today)


def _crypto_row_valid(row: Any, today: str, kinds: frozenset[str] = CRYPTO_KINDS, check_key: bool = True) -> bool:
    if not isinstance(row, dict) or not set(_CRYPTO_REQUIRED) <= set(row) \
            or not set(row) <= set(_CRYPTO_REQUIRED) | {"window_from_utc", "at_last_execution"} | ({"combine_ref"} if not check_key else set()):
        return False
    if not (row["profile"] == "crypto_row" and isinstance(row["source"], str) and _SOURCE.match(row["source"]) and row["kind"] in kinds
            and isinstance(row["row_no"], int) and not isinstance(row["row_no"], bool) and row["row_no"] >= 0 and _utc_day(row["at_utc"], today)
            and isinstance(row["quantity"], str) and _SIGNED.match(row["quantity"])
            and all(row[key] is None or (isinstance(row[key], str) and _POSITIVE.match(row[key])) for key in ("fee_quantity", "eur", "eur_fee"))
            and all(isinstance(row[key], str) and len(row[key]) <= 400 for key in ("file_name", "wallet", "zone", "transaction_id", "hash", "address", "group", "quote"))
            and isinstance(row["ticker"], str) and 0 < len(row["ticker"]) <= 40
            and ("window_from_utc" not in row or _utc_day(row["window_from_utc"], None))
            and ("at_last_execution" not in row or row["at_last_execution"] is True)):
        return False
    return not check_key or row["row_key"] == crypto_row_key_v1(row)


def validate_crypto_result_v1(value: Any, reasons: Mapping[str, str], today: str | None = None, plausibility: bool = True) -> dict[str, Any]:
    """Ergebnis eines Krypto-Lesers fuer eine Datei (Mindestanforderung 2): Zeilen mit nachgerechneter Kennung, erlaubten Arten,
    exakten Dezimalzahlen (Euro und Gebuehren nie negativ), kein Zeitpunkt nach heute; Gruende nur aus der festen Liste. Eine
    BSDEX-Jahreshistorie liefert statt Zeilen ihre Ausfuehrungen als Beleg."""
    today = (today or reference_date_v1()) if plausibility else None   # Selbsttest Stufe 2: nur die Form
    bad = StatementReaderBlocked("statement_reader_output_invalid")
    if not isinstance(value, dict):
        raise bad
    if value.get("status") == "not_importable":
        # Wie bisher ohne Text: Den Grund eines Krypto-Belegs nennt der Stapel ueber seinen Code.
        if not set(value) <= {"status", "reason_code"} or value.get("reason_code") not in reasons:
            raise bad
        return value
    rows, counts = value.get("candidates"), value.get("row_reasons")
    if value.get("status") != "multi" or not set(value) <= {"status", "candidates", "row_reasons", "row_details", "evidence"} or not isinstance(rows, list) \
            or len(rows) > MAX_ROWS or not isinstance(counts, dict) \
            or not all(code in reasons and isinstance(count, int) and not isinstance(count, bool) and count >= 1 for code, count in counts.items()) \
            or ("row_details" in value and not _crypto_details_valid(value["row_details"], counts)) \
            or not all(_crypto_row_valid(row, today) for row in rows):
        raise bad
    if "evidence" in value:
        evidence = value["evidence"]
        fills = evidence.get("bsdex_executions") if isinstance(evidence, dict) and set(evidence) == {"bsdex_executions"} else None
        if rows or not isinstance(fills, list) or len(fills) > MAX_ROWS or not all(
                isinstance(fill, dict) and set(fill) == _FILL_KEYS and isinstance(fill["at"], datetime) and fill["at"].tzinfo is not None
                and all(isinstance(fill[key], Decimal) and fill[key].is_finite() and fill[key] >= 0 for key in ("quantity", "eur", "fee"))
                and all(isinstance(fill[key], str) for key in ("id", "file_name", "side", "asset"))
                and isinstance(fill["ordinal"], int) for fill in fills):
            raise bad
    return value


def apply_crypto_combine_v1(rows_in: Sequence[Mapping[str, Any]], rows_out: Any, today: str | None = None) -> list[dict[str, Any]]:
    """Was ein Plugin beim gemeinsamen Lesen (BSDEX: Export und Jahreshistorie) aendern darf - vom Kern geprueft:
    - jede Zeile gehoert zu einer Zeile des Exports (combine_ref) und behaelt alles ausser Menge, Euro, Gebuehr, Zeitpunkt, Art;
    - je Order bleibt die Stueckzahl gleich (Aufteilung je Ausfuehrungstag erlaubt);
    - eine Order ohne Beleg wird offen (unpriced_trade) und nie gebucht; sie nennt ihren Grund aus UNPRICED_REASONS;
    - der genaue Euro-Betrag und die Gebuehr weichen je Order hoechstens COMBINE_EUR_TOLERANCE vom gerundeten Betrag des Exports ab;
      sonst bleibt diese Order offen (mismatched_trade) und wird nie gebucht. Weichen mehr als COMBINE_SYSTEMATIC_SHARE der Orders ab
      (mindestens zwei), wird das ganze Ergebnis verworfen.
    Strukturelle Fehler (Stueckzahl, fehlende oder erfundene Zeilen, andere Felder, falsche Art) verwerfen das Ergebnis immer."""
    today = today or reference_date_v1()
    bad = StatementReaderBlocked("statement_reader_output_invalid")
    if not isinstance(rows_out, list) or len(rows_out) > MAX_ROWS:
        raise bad
    # Zuordnung ueber combine_ref: je Zeile des Kerns eine eigene Nummer, die das Plugin in jeden Teil uebernimmt.
    originals = {row["combine_ref"]: row for row in rows_in}
    if len(originals) != len(rows_in):
        raise bad
    parts: dict[int, list[dict[str, Any]]] = {}
    for row in rows_out:
        if not isinstance(row, dict) or (row.get("kind") == "unpriced_trade") != any(key in row for key in UNPRICED_FIELDS) \
                or (row.get("kind") == "unpriced_trade" and not _unpriced_valid(row)):
            raise bad
        if not _crypto_row_valid({key: value for key, value in row.items() if key not in UNPRICED_FIELDS}, today, CRYPTO_KINDS | {"unpriced_trade"},
                                 check_key=False):
            raise bad
        key = row.get("combine_ref")
        original = originals.get(key) if isinstance(key, int) and not isinstance(key, bool) else None
        if original is None or any(row.get(field) != original.get(field) for field in set(row) | set(original)
                                   if field not in COMBINE_FIELDS and field not in UNPRICED_FIELDS):
            raise bad
        # Eine Order behaelt ihre Kennung (Identitaet fuer die Belegkennungen); nur Teile einer ueber mehrere Tage ausgefuehrten Order
        # bekommen eine neue, nachgerechnete.
        if row["row_key"] not in (original["row_key"], crypto_row_key_v1(row)):
            raise bad
        if row["kind"] != original["kind"] and not (original["kind"] == "trade" and row["kind"] == "unpriced_trade"):
            raise bad
        parts.setdefault(key, []).append(row)
    if set(parts) != set(originals):
        raise bad
    total = lambda rows, field: sum((Decimal(row[field]) for row in rows if row[field] is not None), Decimal(0))
    priced, differing = 0, set()
    for key, original in originals.items():
        group = parts[key]
        if total(group, "quantity") != Decimal(original["quantity"]):
            raise bad
        if original["kind"] != "trade":
            if len(group) != 1 or group[0] != dict(original):
                raise bad
            continue
        if any(row["kind"] == "unpriced_trade" for row in group):
            if len(group) != 1:
                raise bad
            continue
        priced += 1
        if any(original[field] is not None and abs(total(group, field) - Decimal(original[field])) > COMBINE_EUR_TOLERANCE for field in ("eur", "eur_fee")):
            differing.add(key)
    if len(differing) >= 2 and Decimal(len(differing)) > COMBINE_SYSTEMATIC_SHARE * priced:
        raise bad
    result: list[dict[str, Any]] = []
    held: set[int] = set()
    for row in rows_out:
        key = row["combine_ref"]
        if key not in differing:
            result.append(row)
        elif key not in held:   # die Order wie im Export, offen mit eigenem Grund und den Betraegen der Ausfuehrungen
            held.add(key)
            group = parts[key]
            result.append({**dict(originals[key]), "kind": "mismatched_trade", "executions_eur": str(total(group, "eur")),
                           "executions_fee": str(total(group, "eur_fee"))})
    return result


# ---------------------------------------------------------------- Rewards (rc.377)
REWARD_ROW_KINDS = frozenset(("reward", "other", "invalid"))
REWARD_FEE_ROLES = frozenset(("none", "monetary", "asset_quantity"))
_REWARD_FIELDS = ("asset", "quantity", "local_date", "local_time", "fee", "account", "valuation")
_REWARD_VALUATION = ("source_value_mode", "price_currency", "source_unit_price_decimal", "source_fiat_total_decimal")


def _nonzero(value: Any) -> bool:
    return isinstance(value, str) and _POSITIVE.match(value) is not None and Decimal(value) != 0


def _reward_row_valid(row: Any, today: str) -> bool:
    if not isinstance(row, dict) or row.get("kind") not in REWARD_ROW_KINDS:
        return False
    base = {"cells", "row_id", "signature", "kind"}
    if set(row) != (base | set(_REWARD_FIELDS) if row["kind"] == "reward" else base):
        return False
    if not (isinstance(row["cells"], list) and 0 < len(row["cells"]) <= 400 and all(isinstance(cell, str) and len(cell) <= 20_000 for cell in row["cells"])
            and isinstance(row["row_id"], str) and len(row["row_id"]) <= 400
            and isinstance(row["signature"], list) and len(row["signature"]) == 7 and all(isinstance(item, str) and len(item) <= 20_000 for item in row["signature"])):
        return False
    if row["kind"] != "reward":
        return True
    valuation = row["valuation"]
    if not (isinstance(row["asset"], str) and 0 < len(row["asset"]) <= 80 and row["asset"] == row["asset"].upper() and _nonzero(row["quantity"])
            and _day(row["local_date"], today) and isinstance(row["local_time"], str) and _TIME.match(row["local_time"])
            and (row["fee"] is None or _nonzero(row["fee"])) and isinstance(row["account"], str) and 0 < len(row["account"]) <= 200
            and isinstance(valuation, dict) and set(valuation) == set(_REWARD_VALUATION)
            and (valuation["price_currency"] is None or (isinstance(valuation["price_currency"], str) and _CURRENCY.match(valuation["price_currency"])))):
        return False
    mode, unit, total = valuation["source_value_mode"], valuation["source_unit_price_decimal"], valuation["source_fiat_total_decimal"]
    if mode == "fiat_total":
        return unit is None and _nonzero(total) and valuation["price_currency"] is not None
    if mode == "unit_price":
        return total is None and _nonzero(unit) and valuation["price_currency"] is not None
    return mode == "none" and unit is None and total is None


def validate_reward_result_v1(value: Any, today: str | None = None, plausibility: bool = True) -> dict[str, Any]:
    """Ergebnis eines Reward-Lesers fuer eine Datei: Zeitzone und Rolle der Gebuehr des Formats, je Zeile Zellen, Kennung, Merkmale
    fuer doppelte Zeilen und Art (reward, other, invalid); ein Reward mit Coin (gross geschrieben), Menge ueber 0, Tag nicht nach
    heute, Uhrzeit, Gebuehr, Konto und Bewertung in genau einer der drei Formen. Schluessel, doppelte Zeilen, Zeitraum und
    Kandidaten bildet der Kern (statement_exchange_reward_adapter_v1). Jede Abweichung verwirft das Ergebnis."""
    today = (today or reference_date_v1()) if plausibility else None   # Selbsttest Stufe 2: nur die Form
    bad = StatementReaderBlocked("statement_reader_output_invalid")
    if not isinstance(value, dict) or set(value) != {"time_zone", "fee_role", "rows"} or value["fee_role"] not in REWARD_FEE_ROLES:
        raise bad
    if not isinstance(value["time_zone"], str) or not 0 < len(value["time_zone"]) <= 64:
        raise bad
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415
        ZoneInfo(value["time_zone"])
    except (ValueError, KeyError, OSError):
        raise bad from None
    rows = value["rows"]
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_ROWS or not all(_reward_row_valid(row, today) for row in rows):
        raise bad
    return value


# ---------------------------------------------------------------- Ertraegnisaufstellung (rc.377)
INCOME_POSTING_KINDS = frozenset(("sale", "dividend", "interest", "fund", "ignored", "unclear"))
_INCOME_POSTING_FIELDS = frozenset(("ordinal", "name", "kind_text", "section", "amounts", "isin", "quantity", "value_date", "inflow_date", "depot",
                                    "fund", "replacement_base", "taxes", "kind", "taxable", "line7"))
_ISIN = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def _exact(value: Any, optional: bool = False) -> bool:
    if value is None:
        return optional
    return isinstance(value, Decimal) and value.is_finite()


def _short_text(value: Any, optional: bool = False, limit: int = 400) -> bool:
    if value is None:
        return optional
    return isinstance(value, str) and len(value) <= limit


def validate_income_statement_result_v1(value: Any) -> dict[str, Any]:
    """Ergebnis eines Lesers einer Ertraegnisaufstellung: Steuerjahr, Zeile 7 des Summennachweises und die Posten. Je Posten eine Art
    aus der festen Liste; wer einen Kapitalertrag uebernimmt (sale, dividend, interest, fund), traegt ihn genau als Anteil an Zeile 7,
    ignored und unclear tragen keinen. Summe und Abgleich mit Zeile 7 rechnet der Kern selbst (tax_document_import_v1)."""
    bad = StatementReaderBlocked("statement_reader_output_invalid")
    if not isinstance(value, dict) or set(value) != {"tax_year", "postings", "summary_line7"} or not _exact(value["summary_line7"], optional=True):
        raise bad
    year = value["tax_year"]
    if year is not None and (not isinstance(year, int) or isinstance(year, bool) or not 1990 <= year <= 2100):
        raise bad
    postings = value["postings"]
    if not isinstance(postings, list) or len(postings) > 10_000:
        raise bad
    for ordinal, item in enumerate(postings, 1):
        if not isinstance(item, dict) or set(item) != _INCOME_POSTING_FIELDS or item["ordinal"] != ordinal or item["kind"] not in INCOME_POSTING_KINDS:
            raise bad
        amounts = item["amounts"]
        if not (_short_text(item["name"]) and _short_text(item["kind_text"]) and _short_text(item["section"], optional=True)
                and isinstance(amounts, dict) and len(amounts) <= 200 and all(_short_text(label) and _exact(amount) for label, amount in amounts.items())
                and (item["isin"] is None or (isinstance(item["isin"], str) and _ISIN.match(item["isin"])))
                and _short_text(item["quantity"], optional=True, limit=40) and _day(item["value_date"], None, optional=True)
                and _day(item["inflow_date"], None, optional=True) and _short_text(item["depot"], optional=True, limit=40)
                and isinstance(item["fund"], bool) and isinstance(item["replacement_base"], bool) and _exact(item["taxes"])
                and _exact(item["taxable"], optional=True) and _exact(item["line7"], optional=True)):
            raise bad
        if item["kind"] in ("ignored", "unclear"):
            if item["taxable"] is not None:
                raise bad
        elif item["taxable"] is None or (item["line7"] is not None and item["taxable"] != item["line7"]):
            raise bad
    return value


def validate_cash_combine_v1(value: Any, today: str | None = None) -> dict[str, Any]:
    """Ergebnis eines gemeinsam gelesenen Cash-Stapels (BSDEX): Bewegungen nach dem Schema des Bereichs cash, Dateien, Luecken,
    zurueckgehaltene Orders und Zaehlwerte. Jede Abweichung verwirft das Ergebnis."""
    today = today or reference_date_v1()
    bad = StatementReaderBlocked("statement_reader_output_invalid")
    keys = {"candidates", "diagnostics", "files", "unreadable", "chain_gaps", "held_back", "evidence"}
    if not isinstance(value, dict) or set(value) != keys:
        raise bad
    plain = lambda row, extra: isinstance(row, dict) and all(isinstance(key, str) and key.isidentifier() and (item is None or isinstance(item, (str, int)))
                                                               and not isinstance(item, bool) for key, item in row.items()) and extra(row)
    candidates = value["candidates"]
    stripped = [{key: item for key, item in row.items() if key != "source_file_name"} for row in candidates] if isinstance(candidates, list) else None
    if stripped is None or not all(isinstance(row, dict) and isinstance(row.get("source_file_name", ""), str) for row in candidates):
        raise bad
    validate_cash_result_v1({"candidates": stripped, "diagnostics": [{key: item for key, item in row.items() if key != "file_name"}
                                                                     for row in value["diagnostics"]] if isinstance(value["diagnostics"], list) else None,
                             "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": None, "period_to": None}}, today)
    if not all(isinstance(row.get("file_name", ""), str) for row in value["diagnostics"]):
        raise bad
    if not (isinstance(value["files"], list) and all(plain(row, lambda r: set(r) == {"file_name", "status", "row_count", "period_from", "period_to"}) for row in value["files"])
            and isinstance(value["unreadable"], list) and all(isinstance(name, str) for name in value["unreadable"])
            and isinstance(value["chain_gaps"], list) and all(plain(row, lambda r: True) for row in value["chain_gaps"])
            and isinstance(value["held_back"], list) and all(plain(row, lambda r: True) for row in value["held_back"])
            and isinstance(value["evidence"], dict) and all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in value["evidence"].values())):
        raise bad
    return value
