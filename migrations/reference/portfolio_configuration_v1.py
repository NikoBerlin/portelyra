"""Umfang je Portfolio: Assetklassen und Bausteine (#542, rc.395).

Festlegungen (06.11. und 10.11.2026):
- Je Portfolio waehlt der Nutzer Assetklassen per Haekchen und schaltet sechs Bausteine zu oder ab: Cash, Marktdaten, Verlauf und
  Analyse, Steuerbericht (Stufe 1), Steuerprojektion (Stufe 2, braucht Stufe 1), Belege. Der Grundstock (Portfolio, Konten, Assets,
  Buchungen, FIFO, Einstand, realisierte GuV, Bestand, Datenbasis, Sicherungen, Einstellungen) ist immer an.
- Belege (Kennung "documents") heisst seit #583 (Festlegung 26.11.2026) "Import aus Belegen und Auszuegen" und ist ein Schalter fuer
  Import, Eingang und Ablage; ohne ihn wird nur von Hand gebucht. Bis 0.3.3 blieb der Import ohne ihn ueber die Dateiauswahl.
- Haekchen steuern, was angeboten wird und was laeuft, nicht die Rechnung. Echte Weichen gibt es zwei: mit oder ohne Cash, mit oder
  ohne Kursabruf (Marktdaten).
- Sieben Klassen: Aktien und ETF, Fonds, Anleihen, Krypto, Edelmetalle und Rohstoffe, Derivate, Sonstiges. Devisen gehoeren zum
  Baustein Cash.
- Ohne Marktdaten gilt fuer neue Assets "eigene Kurse bzw. Trade-Kurse" (Wert aus Transaktionen, so gekennzeichnet).
- Mehrere Portfolios in einem Datenraum: Ein Baustein laeuft, sobald ein aktives Portfolio ihn nutzt (Abläufe und veröffentlichte
  Stände gelten je Datenraum); angeboten und angezeigt wird je Portfolio.
- Abschalten loescht nichts; nichts verschwindet still.

Speicher ``portfolio-configuration-v1/configuration.sqlite`` im Datenraum, je Portfolio ganze Fassungen, nur anhaengend; die juengste
gilt. Beim ersten Kontakt bekommt jedes Portfolio mit Daten (Konto oder Buchung) einmalig "Vermoegensueberblick" (alles an, Herkunft
``existing_portfolio``): Am Bestand aendert sich nichts. Ein Portfolio ohne Fassung ist "noch nicht eingerichtet"; fuer es gilt bis zur
Einrichtung ebenfalls alles - es wird nichts ausgeblendet, die gefuehrte Einrichtung bietet sich an.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from migrations.reference import asset_activity_reference_v1 as references

AREA = "portfolio-configuration-v1"
STORE = "configuration.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "portfolio_configuration_v1"

# Klasse -> Assetarten der Stammdaten. Devisen (fx) und Cash gehoeren zum Baustein Cash.
CLASSES: dict[str, tuple[str, ...]] = {
    "equity_etf": ("equity", "etf"),
    "fund": ("fund",),
    "bond": ("bond",),
    "crypto": ("crypto",),
    "commodity": ("commodity",),
    "derivative": ("derivative",),
    "other": ("other", "index"),
}
CLASS_LABELS = {"equity_etf": "Aktien und ETF", "fund": "Fonds", "bond": "Anleihen", "crypto": "Krypto",
                "commodity": "Edelmetalle und Rohstoffe", "derivative": "Derivate", "other": "Sonstiges"}
CASH_ASSET_TYPES = ("cash", "fx")
MODULES = ("cash", "market_data", "history_analysis", "tax_report", "tax_projection", "documents")
MODULE_LABELS = {"cash": "Cash", "market_data": "Marktdaten", "history_analysis": "Verlauf und Analyse", "tax_report": "Steuerbericht",
                 "tax_projection": "Steuerprojektion", "documents": "Import aus Belegen und Auszügen"}
# Was ein Baustein umfasst und was ohne ihn gilt - fuer Vorschau, Einstellungen und Einrichtung.
MODULE_TEXT = {
    "cash": ("Verrechnungskonten, Auszüge, Salden und Abgleich, Tagesgeld, Zinsen, Devisen",
             "Portfolio ohne Cash: Kauf- und Verkaufsbeträge gelten als Zu- und Abflüsse; Gesamtwerte heißen „ohne Cash“"),
    "market_data": ("Kursquellen, Kursabruf und Wechselkurse, Marktbewertung, Momentaufnahme, Zeitpläne",
                    "Bewertung mit eigenen Kursen bzw. Trade-Kursen; Portelyra greift für Kurse nicht aufs Netz"),
    "history_analysis": ("Tageshistorie, Rendite (TWR, IZF), Verlauf, Assets und Gruppen",
                         "nur der Bestand heute und an Stichtagen; der Stichtags-Snapshot plant direkt aus dem Bestand"),
    "tax_report": ("Jahresmodule, Rechenblatt je Verkauf und Ertrag, Krypto-Report, Steuer-GuV, Abgleich mit der Bank, Vorabpauschale, "
                   "Unterlagen des Jahres", "keine Steuer-App"),
    # Festlegung 10.11.2026: schlank und ohne Tageshistorie - wer "Verlauf und Analyse" abwaehlt, will offenbar nur realisierte GuV und
    # Steuer. Dann gilt die Projektion nur im Abschluss; die Netto-Sicht je Lot der Analyse gibt es nur mit "Verlauf und Analyse".
    "tax_projection": ("Steuerprojektion im Abschluss (Steuer-App); mit „Verlauf und Analyse“ auch die Netto-Sicht je Lot und die Verkaufs- "
                       "und Kaufprojektion in der Analyse",
                       "nur die realisierte Steuer; ohne Marktdaten rechnet die Projektion mit dem Transaktionskurs"),
    "documents": ("Import mit den Lesern der Institute, Eingang je Institut mit Belegordnern und Rezepten, Belegablage",
                  "Buchungen nur von Hand"),
}
VALUATIONS = ("manual", "transaction_only")
VALUATION_LABELS = {"manual": "eigene Kurse bzw. Trade-Kurse", "transaction_only": "nur Transaktionen"}
ORIGINS = ("existing_portfolio", "owner", "setup")
# Anbieter, die nur "ab Datum" eingesetzt werden (wie PL_PRICE_PROVIDERS_FROM_DATE_ONLY_V1 in der UI-Huelle, Festlegung 10.11.2026).
FROM_DATE_ONLY_PROVIDERS = ("eodhd",)
PRESETS: dict[str, dict[str, Any]] = {
    # Vorschlaege zum Anklicken (06.11.2026); sie setzen nur Haekchen und sind danach frei aenderbar. Seit #583 mit Belegen: Ohne den
    # Baustein gaebe es keinen Import mehr, auch nicht fuer die Exporte der Boersen.
    "private_tax": {"label": "Krypto und Edelmetalle – Steuer", "classes": ["crypto", "commodity"],
                    "modules": {"cash": False, "market_data": False, "history_analysis": False, "tax_report": True,
                                "tax_projection": False, "documents": True}, "valuation_without_market": "manual"},
    "private_performance": {"label": "Krypto und Edelmetalle – mit Wertentwicklung", "classes": ["crypto", "commodity"],
                            "modules": {"cash": False, "market_data": True, "history_analysis": True, "tax_report": True,
                                        "tax_projection": True, "documents": True}, "valuation_without_market": "manual"},
    "overview": {"label": "Vermögensüberblick", "classes": list(CLASSES),
                 "modules": {module: True for module in MODULES}, "valuation_without_market": "manual"},
}
FAILURE_CODES = (
    "portfolio_configuration_input_invalid", "portfolio_configuration_store_invalid", "portfolio_configuration_preview_stale",
    "portfolio_configuration_confirmation_required", "portfolio_configuration_portfolio_unknown",
)
SCHEMA = (
    "CREATE TABLE configuration_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL "
    "CHECK(schema_version = 1), tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE configuration_version(version_id INTEGER PRIMARY KEY AUTOINCREMENT, portfolio_id TEXT NOT NULL "
    "CHECK(length(portfolio_id) BETWEEN 8 AND 64), configuration_json TEXT NOT NULL CHECK(length(configuration_json) <= 4000), "
    "origin TEXT NOT NULL CHECK(origin IN ('existing_portfolio','owner','setup')), actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, "
    "version_fingerprint TEXT NOT NULL CHECK(length(version_fingerprint) = 64)) STRICT",
    "CREATE INDEX configuration_version_portfolio ON configuration_version(portfolio_id, version_id)",
    "CREATE TRIGGER configuration_version_no_update BEFORE UPDATE ON configuration_version BEGIN SELECT RAISE(ABORT, 'configuration_immutable'); END",
    "CREATE TRIGGER configuration_version_no_delete BEFORE DELETE ON configuration_version BEGIN SELECT RAISE(ABORT, 'configuration_immutable'); END",
)


class PortfolioConfigurationV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "portfolio_configuration_input_invalid"


def _abort(code: str) -> None:
    raise PortfolioConfigurationV1Error(code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _context(value: Any):
    try:
        return references.activity_reference_scope_v1(value)
    except references.AssetActivityReferenceV1Error:
        _abort("portfolio_configuration_input_invalid")


def _stamp(value: Any) -> str:
    if not isinstance(value, str) or references.UTC.fullmatch(value) is None:
        _abort("portfolio_configuration_input_invalid")
    return value


# ---------------------------------------------------------------------------------------------------------------------------
# Fassung pruefen
# ---------------------------------------------------------------------------------------------------------------------------

def normalized_configuration_v1(value: Any) -> dict[str, Any]:
    """Eine Fassung in fester Form: Klassen in fester Reihenfolge, alle sechs Bausteine, Bewertung ohne Kursabruf. Die Steuerprojektion
    braucht den Steuerbericht; mindestens eine Klasse oder Cash muss gewaehlt sein."""
    if not isinstance(value, Mapping) or set(value) != {"classes", "modules", "valuation_without_market"}:
        _abort("portfolio_configuration_input_invalid")
    classes, modules, valuation = value["classes"], value["modules"], value["valuation_without_market"]
    if not isinstance(classes, (list, tuple)) or any(item not in CLASSES for item in classes) or len(set(classes)) != len(classes):
        _abort("portfolio_configuration_input_invalid")
    if not isinstance(modules, Mapping) or set(modules) != set(MODULES) or any(not isinstance(modules[key], bool) for key in MODULES):
        _abort("portfolio_configuration_input_invalid")
    if valuation not in VALUATIONS:
        _abort("portfolio_configuration_input_invalid")
    if modules["tax_projection"] and not modules["tax_report"]:
        _abort("portfolio_configuration_input_invalid")
    if not classes and not modules["cash"]:
        _abort("portfolio_configuration_input_invalid")
    return {"classes": [key for key in CLASSES if key in classes], "modules": {key: bool(modules[key]) for key in MODULES},
            "valuation_without_market": valuation}


def preset_v1(preset_id: str) -> dict[str, Any]:
    if preset_id not in PRESETS:
        _abort("portfolio_configuration_input_invalid")
    item = PRESETS[preset_id]
    return normalized_configuration_v1({key: item[key] for key in ("classes", "modules", "valuation_without_market")})


def asset_types_v1(configuration: Mapping[str, Any]) -> list[str]:
    """Die Assetarten, die Formulare und Importe anbieten (mit Cash auch cash und fx)."""
    types = [asset_type for key in configuration["classes"] for asset_type in CLASSES[key]]
    if configuration["modules"]["cash"]:
        types.extend(CASH_ASSET_TYPES)
    return types


CASH_CLASS_LABEL = "Cash und Devisen (Baustein Cash)"


def class_of_v1(asset_type: str) -> tuple[str, str]:
    """Klasse und Beschriftung einer Assetart; Cash und Devisen gehoeren zum Baustein Cash (#551)."""
    for key, types in CLASSES.items():
        if asset_type in types:
            return key, CLASS_LABELS[key]
    if asset_type in CASH_ASSET_TYPES:
        return "cash", CASH_CLASS_LABEL
    return "other", CLASS_LABELS["other"]


def import_scope_v1(space: str | Path, portfolio_id: str | None, context_value: Any = None) -> dict[str, Any]:
    """Was ein Import in diesem Portfolio ohne Rueckfrage bucht (#551): die Assetarten seines Umfangs. Nur lesend, ohne
    Bestandseintrag; ein Portfolio ohne Fassung (oder ohne Speicher) nimmt alles. Mit Kontext gilt dessen Bindung."""
    context = None if context_value is None else _context(context_value)
    item = _portfolios(space).get(portfolio_id) if portfolio_id else None
    rows = _read_versions(space, context).get(portfolio_id, []) if item else []
    configuration = normalized_configuration_v1(rows[-1]["configuration"]) if rows else preset_v1("overview")
    return {"portfolio_id": portfolio_id, "label": item["label"] if item else None, "asset_types": sorted(set(asset_types_v1(configuration))),
            "classes": list(configuration["classes"])}


def scope_text_v1(configuration: Mapping[str, Any]) -> str:
    """Der Umfang in einer Zeile, etwa "Krypto, Edelmetalle und Rohstoffe · ohne Cash · Kurse aus Transaktionen"."""
    classes = [CLASS_LABELS[key] for key in configuration["classes"]]
    parts = ["alle Assetklassen" if len(classes) == len(CLASSES) else (", ".join(classes) if classes else "nur Cash")]
    modules = configuration["modules"]
    parts.append("mit Cash" if modules["cash"] else "ohne Cash")
    parts.append("Marktkurse" if modules["market_data"] else
                 ("Kurse aus Transaktionen" if configuration["valuation_without_market"] == "manual" else "ohne Bewertung"))
    off = [MODULE_LABELS[key] for key in ("history_analysis", "tax_report", "tax_projection", "documents") if not modules[key]]
    if off:
        parts.append("ohne " + ", ".join(off))
    return " · ".join(parts)


# ---------------------------------------------------------------------------------------------------------------------------
# Speicher
# ---------------------------------------------------------------------------------------------------------------------------

def store_present_v1(space: str | Path) -> bool:
    return (Path(space) / AREA / STORE).exists()


def _connect(space: str | Path, context: Any, create: bool) -> sqlite3.Connection | None:
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("portfolio_configuration_store_invalid")
    expected = None if context is None else (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create or expected is None:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO configuration_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("portfolio_configuration_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM configuration_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("portfolio_configuration_store_invalid")
    # Ohne Kontext (Lesen fuer Abläufe und Veroeffentlichung) gilt der Datenraum des Pfads; die Bindung muss trotzdem genau eine sein.
    if version != SCHEMA_VERSION or len(binding) != 1 or (expected is not None and tuple(binding[0]) != expected) or \
            (expected is None and binding[0]["data_space_id"] != Path(space).name):
        connection.close()
        _abort("portfolio_configuration_store_invalid")
    return connection


def _portfolios(space: str | Path) -> dict[str, dict[str, Any]]:
    """Portfolios der Stammdaten mit Name, Zustand und ob sie Daten haben (Konto oder Buchung)."""
    path = Path(space) / "canonical.sqlite"
    if not path.is_file():
        return {}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT portfolio_id, display_name, status FROM portfolio ORDER BY portfolio_id").fetchall()
            with_accounts = {row[0] for row in connection.execute("SELECT DISTINCT portfolio_id FROM account")}
            with_records = {row[0] for row in connection.execute("SELECT DISTINCT portfolio_id FROM transaction_record")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("portfolio_configuration_store_invalid")
        return {}
    return {str(row[0]): {"label": str(row[1] or row[0]), "status": str(row[2]), "has_data": row[0] in with_accounts or row[0] in with_records}
            for row in rows}


# Geltende Buchungen: gebucht und nicht durch ein Storno oder eine Korrektur ersetzt (die Korrekturkette, wie der Kern seit rc.344).
# Die Assets stehen in den Buchungszeilen (transaction_posting), nicht im Buchungskopf.
_CURRENT_BOOKINGS = ("SELECT DISTINCT r.portfolio_id, p.asset_id FROM transaction_record r JOIN transaction_posting p ON p.transaction_id = r.transaction_id "
                     "WHERE r.record_action = 'book' AND r.transaction_id NOT IN (SELECT supersedes_transaction_id FROM transaction_record "
                     "WHERE supersedes_transaction_id IS NOT NULL)")


def _bookings(space: str | Path, context: Any) -> set[tuple[str, str]]:
    """Paare (Portfolio, Asset) mit geltenden Buchungen: aus dem aktiven Buchungsbestand (Portfolio Ledger, ueber active.json; dort
    stehen die Buchungen seit dem Umzug) und aus den Buchungskoepfen der Stammdaten. Ohne Buchungsbestand nur die Stammdaten."""
    pairs: set[tuple[str, str]] = set()
    path = Path(space) / "canonical.sqlite"
    if path.is_file():
        try:
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
                if {"transaction_record", "transaction_posting"} <= tables:
                    pairs.update((str(row[0]), str(row[1])) for row in connection.execute(_CURRENT_BOOKINGS))
            finally:
                connection.close()
        except sqlite3.Error:
            _abort("portfolio_configuration_store_invalid")
    if context is None:
        return pairs
    from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityV1Error, read_desktop_product_asset_activity_binding_v1
    try:
        binding = read_desktop_product_asset_activity_binding_v1(space, context)
    except DesktopProductAssetActivityV1Error:
        return pairs
    if binding.get("status") != "available" or not binding.get("ledger_path"):
        return pairs
    try:
        connection = sqlite3.connect("file:" + str(binding["ledger_path"]) + "?mode=ro", uri=True)
        try:
            for portfolio, asset, source in connection.execute(
                    "SELECT DISTINCT portfolio_id, asset_id, source_asset_id FROM current_asset_activity_event"):
                pairs.add((str(portfolio), str(asset)))
                if source:
                    pairs.add((str(portfolio), str(source)))
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("portfolio_configuration_store_invalid")
    return pairs


def _class_counts(space: str | Path, portfolio_id: str, bookings: set[tuple[str, str]]) -> dict[str, int]:
    """Je Assetart die Zahl der Assets mit geltenden Buchungen in diesem Portfolio - fuer "nichts verschwindet still"."""
    mine = {asset for portfolio, asset in bookings if portfolio == portfolio_id}
    if not mine:
        return {}
    path = Path(space) / "canonical.sqlite"
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            types = dict(connection.execute("SELECT asset_id, asset_type FROM asset").fetchall())
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("portfolio_configuration_store_invalid")
        return {}
    counts: dict[str, int] = {}
    for asset in mine:
        if asset in types:
            counts[str(types[asset])] = counts.get(str(types[asset]), 0) + 1
    return counts


def _read_versions(space: str | Path, context: Any) -> dict[str, list[dict[str, Any]]]:
    connection = _connect(space, context, False)
    if connection is None:
        return {}
    try:
        versions: dict[str, list[dict[str, Any]]] = {}
        for row in connection.execute("SELECT version_id, portfolio_id, configuration_json, origin, recorded_at_utc FROM configuration_version "
                                      "ORDER BY version_id"):
            versions.setdefault(row["portfolio_id"], []).append({"version_id": row["version_id"], "configuration": json.loads(row["configuration_json"]),
                                                                 "origin": row["origin"], "recorded_at_utc": row["recorded_at_utc"]})
        return versions
    except (sqlite3.Error, ValueError):
        _abort("portfolio_configuration_store_invalid")
        raise
    finally:
        connection.close()


def _insert(connection: sqlite3.Connection, portfolio_id: str, configuration: Mapping[str, Any], origin: str, actor: str, stamp: str) -> None:
    body = {"portfolio_id": portfolio_id, "configuration": configuration, "origin": origin, "actor_id": actor, "recorded_at_utc": stamp}
    connection.execute("INSERT INTO configuration_version(portfolio_id,configuration_json,origin,actor_id,recorded_at_utc,version_fingerprint)"
                       " VALUES(?,?,?,?,?,?)", (portfolio_id, json.dumps(configuration, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                                                 origin, actor, stamp, _fingerprint(body)))


def ensure_baseline_v1(space: str | Path, context_value: Any, recorded_at_utc: str | None = None) -> str:
    """Erster Kontakt mit rc.395: Speicher anlegen; jedes Portfolio mit Daten bekommt einmalig "Vermoegensueberblick" (alles an).
    Ein leeres Portfolio bleibt "noch nicht eingerichtet". Danach ohne Wirkung. Liefert "present", "baseline" oder "empty"."""
    context = _context(context_value)
    if store_present_v1(space):
        return "present"
    ledger = {portfolio for portfolio, _ in _bookings(space, context)}
    eligible = [portfolio for portfolio, item in _portfolios(space).items() if item["has_data"] or portfolio in ledger]
    stamp = _stamp(recorded_at_utc) if recorded_at_utc else _now()
    connection = _connect(space, context, True)
    try:
        with connection:
            for portfolio in eligible:
                _insert(connection, portfolio, preset_v1("overview"), "existing_portfolio", context.actor_id, stamp)
    except sqlite3.Error:
        _abort("portfolio_configuration_store_invalid")
    finally:
        connection.close()
    return "baseline" if eligible else "empty"


# ---------------------------------------------------------------------------------------------------------------------------
# Lesen
# ---------------------------------------------------------------------------------------------------------------------------

def _effective(configurations: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Was im Datenraum laeuft: ein Baustein, sobald ein aktives Portfolio ihn nutzt; ohne Portfolio alles (nichts wird abgeschaltet)."""
    if not configurations:
        return preset_v1("overview")
    classes = [key for key in CLASSES if any(key in item["classes"] for item in configurations)]
    modules = {key: any(item["modules"][key] for item in configurations) for key in MODULES}
    valuation = "manual" if any(item["valuation_without_market"] == "manual" for item in configurations) else "transaction_only"
    return {"classes": classes, "modules": modules, "valuation_without_market": valuation}


def read_v1(space: str | Path, context_value: Any) -> dict[str, Any]:
    """Je Portfolio der Umfang (eingerichtet oder nicht) und was im Datenraum laeuft. Legt beim ersten Kontakt den Bestandseintrag an."""
    context = _context(context_value)
    ensure_baseline_v1(space, context)
    versions = _read_versions(space, context)
    portfolios = []
    active_configurations = []
    for portfolio_id, item in _portfolios(space).items():
        rows = versions.get(portfolio_id, [])
        configured = bool(rows)
        configuration = normalized_configuration_v1(rows[-1]["configuration"]) if configured else preset_v1("overview")
        if item["status"] == "active":
            active_configurations.append(configuration)
        portfolios.append({"portfolio_id": portfolio_id, "label": item["label"], "status": item["status"], "configured": configured,
                           "origin": rows[-1]["origin"] if configured else None, "updated_at_utc": rows[-1]["recorded_at_utc"] if configured else None,
                           "version_count": len(rows), "configuration": configuration, "asset_types": asset_types_v1(configuration),
                           "scope_text": scope_text_v1(configuration)})
    effective = _effective(active_configurations)
    return {"contract_version": CONTRACT, "portfolios": portfolios, "effective": effective, "effective_asset_types": asset_types_v1(effective),
            "effective_scope_text": scope_text_v1(effective)}


def space_configuration_v1(space: str | Path) -> dict[str, Any]:
    """Nur lesend und ohne Eigentuemerkontext (Abläufe, Veroeffentlichung, Zeitlauf): je Portfolio der Umfang und was im Datenraum
    laeuft. Ohne Speicher (vor dem ersten Kontakt) laeuft alles wie bisher; ein Bestandseintrag wird hier nicht angelegt."""
    versions = _read_versions(space, None)
    portfolios = {}
    active = []
    for portfolio_id, item in _portfolios(space).items():
        rows = versions.get(portfolio_id, [])
        configuration = normalized_configuration_v1(rows[-1]["configuration"]) if rows else preset_v1("overview")
        portfolios[portfolio_id] = {"configured": bool(rows), "configuration": configuration, "scope_text": scope_text_v1(configuration),
                                    "status": item["status"], "label": item["label"]}
        if item["status"] == "active":
            active.append(configuration)
    effective = _effective(active)
    return {"store_present": store_present_v1(space), "portfolios": portfolios, "effective": effective,
            "effective_scope_text": scope_text_v1(effective)}


def effective_modules_v1(space: str | Path) -> dict[str, bool]:
    """Fuer Abläufe ("Alles aktualisieren", Zeitlauf): welche Bausteine im Datenraum laufen."""
    return dict(space_configuration_v1(space)["effective"]["modules"])


# ---------------------------------------------------------------------------------------------------------------------------
# Vorschau und Bestaetigung
# ---------------------------------------------------------------------------------------------------------------------------

def _notes(before: Mapping[str, Any], after: Mapping[str, Any], counts: Mapping[str, int]) -> list[str]:
    notes = [f"Umfang danach: {scope_text_v1(after)}."]
    for key in MODULES:
        if before["modules"][key] and not after["modules"][key]:
            notes.append(f"{MODULE_LABELS[key]} wird abgeschaltet: {MODULE_TEXT[key][1]}. Gelöscht wird nichts; zuschalten geht jederzeit.")
        elif not before["modules"][key] and after["modules"][key]:
            later = {"market_data": "Der nächste Lauf von „Alles aktualisieren“ ruft die Kurshistorie ab.",
                     "history_analysis": "Der nächste Lauf rechnet die Tageshistorie einmal auf und schreibt sie danach fort.",
                     "cash": "Danach steht „Cash erfasst ab …“ beim ersten erfassten Tag."}.get(key, "")
            notes.append(f"{MODULE_LABELS[key]} wird zugeschaltet: {MODULE_TEXT[key][0]}. {later}".rstrip())
    if not after["modules"]["market_data"] and before["valuation_without_market"] != after["valuation_without_market"] or \
            (before["modules"]["market_data"] and not after["modules"]["market_data"]):
        notes.append(f"Neue Assets bekommen die Bewertung „{VALUATION_LABELS[after['valuation_without_market']]}“; bestehende behalten ihre.")
    if after["modules"]["tax_projection"] and not after["modules"]["history_analysis"]:
        notes.append("Ohne „Verlauf und Analyse“ gilt die Steuerprojektion nur im Abschluss der Steuer-App; die Netto-Sicht je Lot in der "
                     "Analyse entfällt, eine Tageshistorie wird dafür nicht gerechnet.")
    for key in CLASSES:
        if key in before["classes"] and key not in after["classes"]:
            used = sum(counts.get(asset_type, 0) for asset_type in CLASSES[key])
            notes.append(f"{CLASS_LABELS[key]} wird nicht mehr angeboten." + (
                f" {used} Asset{'s' if used != 1 else ''} mit Buchungen in dieser Klasse {'bleiben' if used != 1 else 'bleibt'} sichtbar, mit Hinweis."
                if used else ""))
    if not after["modules"]["cash"] and before["modules"]["cash"]:
        used = sum(counts.get(asset_type, 0) for asset_type in CASH_ASSET_TYPES)
        if used:
            notes.append(f"Vorhandene Cash-Buchungen ({used} Asset{'s' if used != 1 else ''}) bleiben gespeichert und sichtbar.")
    return notes


def _day_before(day: str) -> str:
    from datetime import date, timedelta
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def _market_switch(space: str | Path, context: Any, portfolio_id: str, before: Mapping[str, Any], after: Mapping[str, Any],
                   whole_history: bool, today: str) -> dict[str, Any] | None:
    """Marktdaten ab- oder zuschalten stellt die bestehenden Assets mit um (Festlegung 10.11.2026), ueber die Bewertungs-Zeitleiste:
    Abschalten - je Asset mit Marktbewertung ein Abschnitt "ab heute eigene Kurse bzw. Trade-Kurse" (bzw. die gewaehlte Bewertung);
    die vorhandenen Kurse bleiben, die Tage bis gestern behalten ihre Marktbewertung. Zuschalten - wer frueher Marktdaten hatte und noch
    eine gepruefte, aktive Zuordnung hat, bekommt ab heute wieder Marktdaten; die uebrigen werden genannt. "Ganze Historie neu" setzt den
    Abschnitt ab dem ersten Tag. Umgestellt wird nur ein Asset, das kein anderes aktives Portfolio mit Marktdaten bucht.
    Ausgefuehrt wird von der Data-App je Asset wie in der Karte "Bewertung ueber die Zeit" (Stammdaten, dann Abschnitt)."""
    switching_off = before["modules"]["market_data"] and not after["modules"]["market_data"]
    switching_on = not before["modules"]["market_data"] and after["modules"]["market_data"]
    if not switching_off and not switching_on:
        return None
    from migrations.reference.asset_valuation_timeline_v1 import timeline_v1
    path = Path(space) / "canonical.sqlite"
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            assets = {row[0]: {"display_name": row[1], "valuation_method": row[2], "asset_type": row[3]} for row in connection.execute(
                "SELECT asset_id, display_name, valuation_method, asset_type FROM asset WHERE status='active' AND asset_type <> 'cash'")}
            ready = {(row[0], row[1]): row[2] for row in connection.execute(
                "SELECT asset_id, provider_id, provider_symbol FROM provider_mapping WHERE capability='daily_history' "
                "AND verification_status='verified' AND enabled=1")}
            statuses = {row[0]: row[1] for row in connection.execute("SELECT portfolio_id, status FROM portfolio")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("portfolio_configuration_store_invalid")
        return None
    booked: dict[str, set[str]] = {}
    for portfolio, asset in _bookings(space, context):
        booked.setdefault(asset, set()).add(portfolio)
    versions = _read_versions(space, context)
    def market_elsewhere(asset_id: str) -> bool:
        for other in booked.get(asset_id, set()) - {portfolio_id}:
            if statuses.get(other) != "active":
                continue
            rows = versions.get(other, [])
            configuration = normalized_configuration_v1(rows[-1]["configuration"]) if rows else preset_v1("overview")
            if configuration["modules"]["market_data"]:
                return True
        return False
    timeline = timeline_v1(space)
    target = after["valuation_without_market"]
    items, kept, unready = [], [], []
    for asset_id in sorted(asset for asset, portfolios in booked.items() if portfolio_id in portfolios and asset in assets):
        asset = assets[asset_id]
        segments = [row.public() for row in timeline.segments(asset_id)]
        if not segments:
            # Ohne eigene Zeitleiste traegt die Kursreihe der Zuordnung (bei mehreren Yahoo als Vorgabe); ist sie nicht eindeutig,
            # laesst sich "bis gestern Marktdaten" nicht beschreiben.
            series = None
            if asset["valuation_method"] == "external_market":
                mine = sorted(provider for (asset_key, provider) in ready if asset_key == asset_id)
                provider = "yahoo" if "yahoo" in mine else (mine[0] if len(mine) == 1 else None)
                series = (provider, ready[(asset_id, provider)]) if provider else None
                if series is None and switching_off and not whole_history:
                    kept.append({"asset_id": asset_id, "display_name": asset["display_name"],
                                 "reason": "bisherige Kursreihe nicht eindeutig – bitte unter „Bewertung über die Zeit“ selbst umstellen"})
                    continue
            segments = [{"valid_from": None, "valid_until": None, "method": asset["valuation_method"],
                         "provider_id": series[0] if series else None, "provider_symbol": series[1] if series else None}]
        current = segments[-1]["method"]
        plain = [{key: row[key] for key in ("valid_from", "method", "provider_id", "provider_symbol")} for row in segments]
        if switching_off:
            if current != "external_market":
                continue
            if market_elsewhere(asset_id):
                kept.append({"asset_id": asset_id, "display_name": asset["display_name"], "reason": "ein anderes aktives Portfolio nutzt Marktdaten"})
                continue
            new = {"valid_from": None if whole_history else today, "method": target, "provider_id": None, "provider_symbol": None}
        else:
            if current == "external_market":
                continue
            earlier = next((row for row in reversed(segments) if row["method"] == "external_market" and row["provider_id"]), None)
            if earlier is None:
                continue  # war nie am Markt bewertet: bleibt, wie es ist
            symbol = ready.get((asset_id, earlier["provider_id"]))
            if symbol is None:
                unready.append({"asset_id": asset_id, "display_name": asset["display_name"],
                                "reason": "keine geprüfte, aktive Kurszuordnung mehr – unter 3. Marktdaten → 1. Kursquelle einrichten"})
                continue
            whole = whole_history and earlier["provider_id"] not in FROM_DATE_ONLY_PROVIDERS
            new = {"valid_from": None if whole else today, "method": "external_market", "provider_id": earlier["provider_id"],
                   "provider_symbol": symbol}
        if new["valid_from"] is None:
            planned = [new]
        else:
            planned = [row for row in plain if row["valid_from"] is None or row["valid_from"] < today]
            if planned and segments[len(planned) - 1]["method"] == new["method"] and segments[len(planned) - 1].get("provider_id") == new["provider_id"]:
                continue
            planned.append(new)
        if planned and planned[0]["valid_from"] is not None:
            planned[0] = {**planned[0], "valid_from": None}
        items.append({"asset_id": asset_id, "display_name": asset["display_name"], "catalog_method_before": asset["valuation_method"],
                      "catalog_method_after": new["method"], "segments": planned})
    return {"direction": "off" if switching_off else "on", "from_day": None if whole_history else today, "whole_history": bool(whole_history),
            "items": items, "kept": kept, "unready": unready}


def _state_fingerprint(space: str | Path, context: Any, portfolio_id: str) -> str:
    rows = _read_versions(space, context).get(portfolio_id, [])
    return _fingerprint(rows[-1] if rows else None)


def preview_v1(space: str | Path, context_value: Any, portfolio_id: Any, configuration: Any, origin: str = "owner",
               created_at_utc: str | None = None, whole_history: bool = False) -> dict[str, Any]:
    """Vorschau einer neuen Fassung: Umfang danach und Folgen je Aenderung. ``origin``: owner (Einstellungen) oder setup (Einrichtung).
    Werden Marktdaten ab- oder zugeschaltet, nennt ``market_switch`` je Asset den neuen Abschnitt der Bewertung ueber die Zeit
    (``whole_history``: ab dem ersten Tag statt ab heute)."""
    context = _context(context_value)
    ensure_baseline_v1(space, context)
    portfolios = _portfolios(space)
    if not isinstance(portfolio_id, str) or portfolio_id not in portfolios:
        _abort("portfolio_configuration_portfolio_unknown")
    if origin not in ("owner", "setup"):
        _abort("portfolio_configuration_input_invalid")
    after = normalized_configuration_v1(configuration)
    rows = _read_versions(space, context).get(portfolio_id, [])
    before = normalized_configuration_v1(rows[-1]["configuration"]) if rows else preset_v1("overview")
    if not isinstance(whole_history, bool):
        _abort("portfolio_configuration_input_invalid")
    stamp = _stamp(created_at_utc) if created_at_utc else _now()
    switch = _market_switch(space, context, portfolio_id, before, after, whole_history, stamp[:10])
    notes = _notes(before, after, _class_counts(space, portfolio_id, _bookings(space, context)))
    if switch is not None:
        when = "ab dem ersten Tag" if whole_history else "ab heute"
        if switch["direction"] == "off":
            notes.append(f"{len(switch['items'])} Asset{'s' if len(switch['items']) != 1 else ''} mit Marktbewertung "
                         f"{'werden' if len(switch['items']) != 1 else 'wird'} {when} auf „{VALUATION_LABELS[after['valuation_without_market']]}“ umgestellt "
                         "(Bewertung über die Zeit); vorhandene Kurse bleiben" + ("" if whole_history else ", die Tage bis gestern behalten ihre Marktbewertung") + ".")
        else:
            notes.append(f"{len(switch['items'])} Asset{'s' if len(switch['items']) != 1 else ''} {'bekommen' if len(switch['items']) != 1 else 'bekommt'} "
                         f"{when} wieder Marktdaten (Bewertung über die Zeit).")
        for row in switch["kept"] + switch["unready"]:
            notes.append(f"{row['display_name']}: bleibt, wie es ist – {row['reason']}.")
    body = {"contract_version": "portfolio_configuration_preview_v1", "portfolio_id": portfolio_id, "portfolio_label": portfolios[portfolio_id]["label"],
            "configured_before": bool(rows), "before": before, "after": after, "unchanged": bool(rows) and before == after,
            "scope_text": scope_text_v1(after), "asset_types": asset_types_v1(after), "origin": origin,
            "notes": notes, "market_switch": switch, "state_fingerprint": _state_fingerprint(space, context, portfolio_id),
            "created_at_utc": stamp}
    body["preview_fingerprint"] = _fingerprint(body)
    return body


def apply_v1(space: str | Path, context_value: Any, preview: Any, confirmed: Any, recorded_at_utc: str | None = None) -> dict[str, Any]:
    """Uebernimmt genau die gezeigte Vorschau als neue Fassung (nur anhaengend)."""
    context = _context(context_value)
    if confirmed is not True:
        _abort("portfolio_configuration_confirmation_required")
    if not isinstance(preview, Mapping) or preview.get("contract_version") != "portfolio_configuration_preview_v1":
        _abort("portfolio_configuration_input_invalid")
    body = {key: value for key, value in preview.items() if key != "preview_fingerprint"}
    if preview.get("preview_fingerprint") != _fingerprint(body):
        _abort("portfolio_configuration_preview_stale")
    portfolio_id = preview["portfolio_id"]
    if portfolio_id not in _portfolios(space) or preview["state_fingerprint"] != _state_fingerprint(space, context, portfolio_id):
        _abort("portfolio_configuration_preview_stale")
    after = normalized_configuration_v1(preview["after"])
    stamp = _stamp(recorded_at_utc) if recorded_at_utc else _now()
    connection = _connect(space, context, True)
    try:
        with connection:
            _insert(connection, portfolio_id, after, preview["origin"], context.actor_id, stamp)
    except sqlite3.Error:
        _abort("portfolio_configuration_store_invalid")
    finally:
        connection.close()
    return {"contract_version": "portfolio_configuration_result_v1", "status": "recorded", "portfolio_id": portfolio_id,
            "scope_text": scope_text_v1(after), "recorded_at_utc": stamp}


def catalog_v1() -> dict[str, Any]:
    """Klassen, Bausteine und Vorschlaege mit Texten - fuer Einstellungen und Einrichtung (ohne Datenraum)."""
    return {"contract_version": "portfolio_configuration_catalog_v1",
            "classes": [{"key": key, "label": CLASS_LABELS[key], "asset_types": list(types)} for key, types in CLASSES.items()],
            "modules": [{"key": key, "label": MODULE_LABELS[key], "includes": MODULE_TEXT[key][0], "without": MODULE_TEXT[key][1],
                         "requires": "tax_report" if key == "tax_projection" else None} for key in MODULES],
            "valuations": [{"key": key, "label": VALUATION_LABELS[key]} for key in VALUATIONS],
            "presets": [{"key": key, "label": item["label"], "configuration": preset_v1(key)} for key, item in PRESETS.items()]}


__all__ = [
    "AREA", "CASH_ASSET_TYPES", "CLASSES", "CLASS_LABELS", "FAILURE_CODES", "MODULES", "MODULE_LABELS", "PRESETS", "STORE", "VALUATIONS",
    "CASH_CLASS_LABEL", "PortfolioConfigurationV1Error", "apply_v1", "asset_types_v1", "catalog_v1", "class_of_v1", "effective_modules_v1",
    "ensure_baseline_v1", "import_scope_v1", "normalized_configuration_v1", "preset_v1", "preview_v1", "read_v1", "scope_text_v1", "space_configuration_v1", "store_present_v1",
]
