#!/usr/bin/env python3
"""Fassungen der Steuermodule und welche Fassung eine Rechnung nimmt (#486 Schritt 2).

Festlegungen (16.11.2026):
- Die Steuerrechnungen folgen der gespeicherten Modulauswahl je Portfolio und Projektionsart (tax-ui/tax-policy.sqlite). Bis hierhin
  nahmen sie fest die mitgelieferte Fassung 2; die Auswahl war nur Anzeige.
- "Gueltig ab" einer Fassung heisst: ab dem Tag rechnet Portelyra alle Steuerjahre damit (die Fassung fuehrt den Rechtsstand je Jahr).
  Massgeblich ist der Tag der Rechnung, nicht das Steuerjahr.
- Eine Fassung, die ein Release nicht mehr mitbringt, bleibt im Datenraum erhalten, bis der Eigentuemer die neue uebernimmt.

Wo Fassungen liegen:
- mitgeliefert: plugins/tax_models/<plugin_id>/ im installierten Abbild (versiegelt, je Modul eine Fassung);
- im Datenraum (im Backup): tax-model-plugins-v1/<plugin_id>/<version>-<rules12>/<plugin_id>/ - je Fassung ein eigener, unveraenderter
  Ordner; der Name des innersten Ordners ist die plugin_id, wie die Manifestpruefung es verlangt.

Jede Fassung wird bei jedem Lesen ueber ihr Manifest geprueft (Pruefsummen von plugin.R und aller Tabellen); eine Fassung, die die Pruefung
nicht besteht, gibt es nicht. Liest nur.
"""
from __future__ import annotations

import csv
from datetime import date
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from typing import Any, Mapping

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference import tax_model_plugin_v1 as base

AREA = "tax-model-plugins-v1"
_VERSION_DIR = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]{12}$")
MODES = ("realized_event", "realized_annual", "unrealized_snapshot")


class TaxModuleCatalogBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _entry(manifest: base.TaxPluginManifest, origin: str, plugin_root: Path) -> dict[str, Any]:
    return {"plugin_id": manifest.plugin_id, "plugin_version": manifest.plugin_version, "rules_fingerprint": manifest.rules_fingerprint,
            "manifest_fingerprint": manifest.manifest_fingerprint, "origin": origin, "plugin_root": str(plugin_root),
            "jurisdiction_code": manifest.jurisdiction_code, "model_scope": manifest.model_scope,
            "supported_projection_modes": list(manifest.supported_projection_modes), "effective_from": manifest.effective_from,
            "effective_to": manifest.effective_to, "disclaimer_codes": list(manifest.disclaimer_codes)}


def tax_module_key_v1(entry: Mapping[str, Any]) -> str:
    """Undurchsichtiger Schluessel einer Fassung fuer die Oberflaeche (sie zeigt weder Pfade noch Pruefsummen): Modul, Version, Regel- und
    Manifestabdruck."""
    return "tmk_" + base.sha({"plugin_id": entry["plugin_id"], "plugin_version": entry["plugin_version"],
                              "rules_fingerprint": entry["rules_fingerprint"], "manifest_fingerprint": entry["manifest_fingerprint"]})[:24]


def version_directory_name_v1(plugin_version: str, rules_fingerprint: str) -> str:
    """Name des Ordners einer Fassung im Datenraum: Version und die ersten zwoelf Zeichen des Regelabdrucks."""
    return f"{plugin_version}-{rules_fingerprint[:12]}"


EMBEDDED_VALUES_MARKER = 'legal_values_text <- "'


def embedded_values_consistent_v1(plugin_root: str | Path, plugin_id: str) -> bool:
    """Die Jahreswerte stehen in einem Modul doppelt:
    in plugin.R, weil das Modul abgeschottet nur seine Einstiegsdatei lesen darf (damit wird gerechnet), und in annual-legal-values.csv
    mit Fundstelle (daraus lesen Rechenblaetter, Netto-Sicht und Anzeige). Beide muessen Zeile fuer Zeile gleich sein, sonst zeigte
    Portelyra andere Werte, als es rechnet. Ein Modul ohne Jahrestabelle (Vergleichsmodell 1) gilt als stimmig."""
    directory = Path(plugin_root) / plugin_id
    table = directory / "annual-legal-values.csv"
    if not table.exists():
        return True
    try:
        text = (directory / "plugin.R").read_text(encoding="utf-8")
        with table.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        if EMBEDDED_VALUES_MARKER not in text:
            return False
        embedded = text.split(EMBEDDED_VALUES_MARKER, 1)[1].split('"', 1)[0].splitlines()
        return embedded == ["tax_year,value_code,value_decimal"] + [f"{row['tax_year']},{row['value_code']},{row['value_decimal']}" for row in rows]
    except (OSError, UnicodeError, KeyError, csv.Error):
        return False


def _data_space_versions(space: Path) -> list[dict[str, Any]]:
    area = space / AREA
    if not area.is_dir() or area.is_symlink():
        return []
    found = []
    for module in sorted(area.iterdir(), key=lambda path: path.name):
        if not module.is_dir() or module.is_symlink():
            continue
        for version in sorted(module.iterdir(), key=lambda path: path.name):
            if not version.is_dir() or version.is_symlink() or not _VERSION_DIR.fullmatch(version.name):
                continue
            try:
                manifest = base.tax_plugin_manifest_v1(module.name, version)
            except base.TaxPluginBlocked:
                continue
            if version.name != version_directory_name_v1(manifest.plugin_version, manifest.rules_fingerprint):
                continue
            if not embedded_values_consistent_v1(version, module.name):
                continue
            found.append(_entry(manifest, "data_space", version))
    return found


def tax_module_catalog_v1(data_space: str | Path | None = None, plugin_root: str | Path | None = None) -> list[dict[str, Any]]:
    """Alle pruefbaren Fassungen: die mitgelieferten zuerst, dann die des Datenraums. Dieselbe Fassung (Modul, Version, Regel- und
    Manifestabdruck) zaehlt einmal."""
    shipped_root = base.PLUGIN_ROOT if plugin_root is None else Path(plugin_root)
    entries: list[dict[str, Any]] = []
    if shipped_root.is_dir() and not shipped_root.is_symlink():
        for directory in sorted(shipped_root.iterdir(), key=lambda path: path.name):
            if not directory.is_dir() or directory.is_symlink():
                continue
            try:
                manifest = base.tax_plugin_manifest_v1(directory.name, shipped_root)
            except base.TaxPluginBlocked:
                continue
            if embedded_values_consistent_v1(shipped_root, directory.name):
                entries.append(_entry(manifest, "shipped", shipped_root))
    if data_space is not None:
        seen = {(item["plugin_id"], item["plugin_version"], item["rules_fingerprint"], item["manifest_fingerprint"]) for item in entries}
        for item in _data_space_versions(Path(data_space)):
            key = (item["plugin_id"], item["plugin_version"], item["rules_fingerprint"], item["manifest_fingerprint"])
            if key not in seen:
                seen.add(key)
                entries.append(item)
    return entries


def tax_module_manifest_v1(entry: Mapping[str, Any]) -> base.TaxPluginManifest:
    """Das geprueftes Manifest einer Katalogfassung (erneut geprueft: zwischen Katalog und Rechnung darf sich nichts aendern)."""
    manifest = base.tax_plugin_manifest_v1(entry["plugin_id"], Path(entry["plugin_root"]))
    if (manifest.plugin_version, manifest.rules_fingerprint, manifest.manifest_fingerprint) != (
            entry["plugin_version"], entry["rules_fingerprint"], entry["manifest_fingerprint"]):
        raise base.TaxPluginBlocked("tax_plugin_rules_fingerprint_mismatch")
    return manifest


def _store_path(space: Path) -> Path:
    return space / "tax-ui" / "tax-policy.sqlite"


def _selection_rows(space: Path, context: Any, portfolio_ref: str, projection_mode: str) -> list[sqlite3.Row]:
    """Alle Revisionen der Auswahl dieses Portfolios und dieser Projektionsart, aelteste zuerst."""
    from migrations.reference.tax_ui_workspace_v1 import TaxUiBlocked, _ui_connect
    store = _store_path(space)
    if not store.is_file() or store.is_symlink():
        return []
    try:
        con = _ui_connect(store, context, True)
    except TaxUiBlocked as error:
        raise TaxModuleCatalogBlocked(error.code) from error
    try:
        return con.execute(
            "SELECT entity.selection_ref,entity.portfolio_ref,entity.projection_mode,revision.* FROM tax_plugin_selection_entity entity "
            "JOIN tax_plugin_selection_revision revision USING(selection_id) WHERE entity.portfolio_ref=? AND entity.projection_mode=? "
            "ORDER BY revision.revision_no", (portfolio_ref, projection_mode)).fetchall()
    except sqlite3.Error as error:
        raise TaxModuleCatalogBlocked("tax_plugin_store_invalid") from error
    finally:
        con.close()


def resolve_tax_module_v1(data_space: str | Path, context: Any, portfolio_ref: str, projection_mode: str, as_of_date: str,
                          plugin_root: str | Path | None = None) -> dict[str, Any]:
    """Welche Fassung eine Rechnung dieses Portfolios und dieser Projektionsart am Tag `as_of_date` nimmt.

    Gilt die juengste Auswahl, deren "Gueltig ab" nicht nach dem Tag liegt. Ergebnis:
    - status "selected": die gewaehlte Fassung, geprueft; `selection` traegt die gespeicherte Auswahl;
    - status "selected_module_missing": gewaehlt ist eine Fassung, die es nicht (mehr) gibt oder deren Abdruck nicht stimmt; `entry` ist
      dann die mitgelieferte Fassung desselben Moduls, falls vorhanden (so rechnete Portelyra bis rc.420 immer) - die Oberflaeche meldet
      "Regeln geaendert" bzw. "Fassung nicht mehr vorhanden";
    - status "no_selection": keine (aktive) Auswahl bis zu dem Tag; `entry` ist None.
    """
    base.valid_ref(portfolio_ref, "pfr_")
    if projection_mode not in MODES:
        raise TaxModuleCatalogBlocked("tax_plugin_selection_invalid")
    base.valid_date(as_of_date)
    date.fromisoformat(as_of_date)
    space = Path(data_space)
    rows = [row for row in _selection_rows(space, context, portfolio_ref, projection_mode) if row["effective_from"] <= as_of_date]
    if not rows or rows[-1]["status"] != "active":
        return {"status": "no_selection", "selection": None, "entry": None}
    row = rows[-1]
    selection = {key: row[key] for key in ("selection_ref", "revision_no", "portfolio_ref", "projection_mode", "plugin_id", "plugin_version",
                                           "rules_fingerprint", "manifest_fingerprint", "effective_from", "status")}
    catalog = tax_module_catalog_v1(space, plugin_root)
    exact = next((item for item in catalog if (item["plugin_id"], item["plugin_version"], item["rules_fingerprint"], item["manifest_fingerprint"])
                  == (row["plugin_id"], row["plugin_version"], row["rules_fingerprint"], row["manifest_fingerprint"])), None)
    if exact is not None and projection_mode in exact["supported_projection_modes"]:
        return {"status": "selected", "selection": selection, "entry": exact}
    shipped = next((item for item in catalog if item["origin"] == "shipped" and item["plugin_id"] == row["plugin_id"]
                    and projection_mode in item["supported_projection_modes"]), None)
    return {"status": "selected_module_missing", "selection": selection, "entry": shipped}


def tax_plugin_selection_for_v1(resolved: Mapping[str, Any]) -> base.TaxPluginSelection:
    """Die gespeicherte Auswahl als Eingabe des Moduls - nur, wenn ihre Fassung genau die gepruefte ist (status "selected")."""
    if resolved.get("status") != "selected":
        raise TaxModuleCatalogBlocked("tax_plugin_selection_invalid")
    payload = {key: resolved["selection"][key] for key in ("selection_ref", "revision_no", "portfolio_ref", "projection_mode", "plugin_id",
                                                            "plugin_version", "rules_fingerprint", "manifest_fingerprint", "effective_from", "status")}
    payload["revision_token"] = base.sha({"contract": "tax_plugin_selection_v1", "revision": dict(payload)})
    return base.TaxPluginSelection(**payload)


def _private_tree(path: Path) -> None:
    for current, directories, files in os.walk(path):
        os.chmod(current, 0o700)
        for name in files:
            os.chmod(Path(current) / name, 0o600)


def preserve_tax_module_v1(data_space: str | Path, entry: Mapping[str, Any]) -> str:
    """Legt eine mitgelieferte Fassung im Datenraum ab (Festlegung 16.11.2026: die gewaehlte Fassung bleibt, bis die neue uebernommen
    ist). Ein spaeteres Release, das die Fassung nicht mehr mitbringt, kann sie dann nicht mehr entfernen. Erst kopiert, dann geprueft,
    dann an ihren Platz gerueckt; ein abgebrochener Versuch hinterlaesst nichts Gueltiges. Rueckgabe: "preserved", "present" oder
    "not_shipped"."""
    if entry.get("origin") != "shipped":
        return "not_shipped"
    space = Path(data_space)
    target_parent = space / AREA / entry["plugin_id"] / version_directory_name_v1(entry["plugin_version"], entry["rules_fingerprint"])
    if (target_parent / entry["plugin_id"]).is_dir():
        return "present"
    source = Path(entry["plugin_root"]) / entry["plugin_id"]
    module_dir = space / AREA / entry["plugin_id"]
    for directory in (space / AREA, module_dir):
        if directory.is_symlink():
            raise TaxModuleCatalogBlocked("tax_module_area_invalid")
        directory.mkdir(mode=0o700, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".kopie-", dir=module_dir))
    try:
        shutil.copytree(source, staging / entry["plugin_id"], symlinks=False)
        _private_tree(staging)
        manifest = base.tax_plugin_manifest_v1(entry["plugin_id"], staging)
        if (manifest.plugin_version, manifest.rules_fingerprint, manifest.manifest_fingerprint) != (
                entry["plugin_version"], entry["rules_fingerprint"], entry["manifest_fingerprint"]):
            raise TaxModuleCatalogBlocked("tax_module_copy_invalid")
        settle_new_directory_v1(staging)  # #568: auch die gocryptfs.diriv neuer Ordner festschreiben
        os.replace(staging, target_parent)
    except base.TaxPluginBlocked as error:
        raise TaxModuleCatalogBlocked("tax_module_copy_invalid") from error
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return "preserved"


def preserve_selected_tax_modules_v1(data_space: str | Path, context: Any, plugin_root: str | Path | None = None) -> dict[str, int]:
    """Alle derzeit gewaehlten mitgelieferten Fassungen im Datenraum ablegen (beim Oeffnen der Steuereinstellungen und nach jeder
    Uebernahme). Liest den Steuerspeicher nur."""
    from migrations.reference.tax_ui_workspace_v1 import TaxUiBlocked, _ui_connect
    space = Path(data_space)
    store = _store_path(space)
    counts = {"preserved": 0, "present": 0, "not_shipped": 0, "missing": 0}
    if not store.is_file() or store.is_symlink():
        return counts
    try:
        con = _ui_connect(store, context, True)
    except TaxUiBlocked as error:
        raise TaxModuleCatalogBlocked(error.code) from error
    try:
        selected = {(row["plugin_id"], row["plugin_version"], row["rules_fingerprint"], row["manifest_fingerprint"])
                    for row in con.execute("SELECT revision.* FROM current_tax_plugin_selection_revision revision WHERE revision.status='active'")}
    except sqlite3.Error as error:
        raise TaxModuleCatalogBlocked("tax_plugin_store_invalid") from error
    finally:
        con.close()
    catalog = tax_module_catalog_v1(space, plugin_root)
    for key in sorted(selected):
        entry = next((item for item in catalog if (item["plugin_id"], item["plugin_version"], item["rules_fingerprint"], item["manifest_fingerprint"]) == key), None)
        if entry is None:
            counts["missing"] += 1
            continue
        counts[preserve_tax_module_v1(space, entry)] += 1
    return counts


__all__ = ["AREA", "TaxModuleCatalogBlocked", "embedded_values_consistent_v1", "tax_module_key_v1", "preserve_selected_tax_modules_v1", "preserve_tax_module_v1", "resolve_tax_module_v1",
           "tax_module_catalog_v1", "tax_module_manifest_v1", "tax_plugin_selection_for_v1", "version_directory_name_v1"]
