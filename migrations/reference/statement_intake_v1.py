"""Monatlicher Eingang (#513): Belegordner als Quelle, Rezept je Institut, ein Schritt je Institut.

Festlegungen (25.10.2026):
- Ein Belegordner ausserhalb von Portelyra ist die Quelle, einmal gewaehlt, je Institut ein Unterordner (Jahre optional). Portelyra
  liest ihn nur und aendert keine Datei. Neue Dateien erkennt der Eingang am Pruefwert und kopiert sie unveraenderlich in die
  Ablage, die im Backup liegt; Umbenennen, Verschieben oder Loeschen im Ordner schadet danach nicht.
- Ein Schritt je Institut: "Eingang pruefen" zeigt je Datei neu, schon abgelegt oder nicht erkannt mit Grund. Eine Bestaetigung
  legt die neuen Dateien eines Instituts ab; passt etwas nicht, haelt nur dieses Institut an. Gebucht wird danach im Import des
  Instituts mit den abgelegten Dateien - dort gelten Vorschau und Bestaetigung wie bisher.
- Je Institut ein Rezept: was herunterzuladen ist, fuer welchen Zeitraum, welche Konten es abdeckt und welcher Leser es liest.
  Rezepte gibt es auf zwei Ebenen: hier die des Produkts (fuer alle Nutzer), am Konto die des Nutzers (aktiv, "Konto geschlossen
  seit ...", "keine Auszuege erwartet").

Die Zeitraumregel ist der Hebel gegen die Verschiedenheit der Belege: Wo ein Export mit freiem Zeitraum moeglich ist, immer vom
Kontobeginn bis heute (die Leser erkennen Gebuchtes); je Monat nur bei Instituten mit ausschliesslich Monats- oder Beleg-PDFs.

Schreibt nur in die Ablage (statement_archive_v1). Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from migrations.reference import statement_reader_plugins_v1 as reader_plugins
from migrations.reference.statement_archive_suggestion_v1 import suggest_statement_placements_v1
from migrations.reference.statement_archive_v1 import (
    MAX_FILE_BYTES, StatementArchiveV1Error, _known_files, read_statement_account_closures_v1, read_statement_account_states_v1, read_statement_intake_folder_v1,
    statement_archive_scope_v1, store_statement_document_v1,
)

CONTRACT = "statement_intake_v1"
# Hoechstens so viele Dateien im ganzen Belegordner (seit rc.318; vorher 2000 mit allgemeiner Fehlermeldung).
MAX_FILES = 10000
SUGGEST_BATCH = 1000
SYSTEM_FILES = frozenset({"thumbs.db", "desktop.ini", ".ds_store"})

PERIOD_RULES = {
    "since_start": "Export mit freiem Zeitraum: immer vom Kontobeginn bis heute. Überlappung schadet nicht – schon Gebuchtes erkennt der Leser.",
    "monthly": "Monats-PDFs: die Dokumente des neuen Monats. Was schon in der Ablage liegt, erkennt der Eingang am Prüfwert.",
    "per_document": "Je Vorgang ein PDF (Abrechnung, Dividende): alle neuen aus dem Postfach. Schon Abgelegtes erkennt der Eingang am Prüfwert.",
    "none": "Keine neuen Auszüge mehr: Das Institut ist abgeschlossen; alte Belege lassen sich weiter ablegen und lesen.",
    "manual": "Kein Leser: Belege nur ablegen, Buchungen von Hand erfassen.",
}
STATUS_LABELS = {"active": "aktiv", "historical": "historisch, abgeschlossen", "manual": "von Hand"}
IMPORT_KINDS = ("securities", "crypto", "rewards", "cash", "fx")

# Rezepte des Produkts (#513): seit #486 je Plugin im Manifest ("intake"), auch fuer installierte Plugins. 'folders' sind die Namen,
# unter denen der Eingang einen Unterordner diesem Institut zuordnet (ohne Gross-/Kleinschreibung, Leer- und Satzzeichen); 'readers'
# nennt Importart und Leser in der Reihenfolge, in der gebucht wird; 'words' die Woerter, an denen der Vorschlag die Konten des Instituts
# erkennt (Institutsangabe des Kontos, ganze Woerter); 'tax_fallback', ob eine Steuerunterlage ohne Kontonummer allen Konten des
# Instituts gilt (nicht, wenn sich zwei Broker eine Bank teilen). Stand je Konto (geschlossen, ruhend) legt der Nutzer am Konto fest.


def _recipe_readers(entries) -> tuple[tuple[str, str], ...]:
    """Bereich und Leser aus dem Manifest als Importart und Leser des Imports: Krypto-Leser lesen zusammen (crypto_exports_v1), Reward-Leser
    im Reward-Import; ein Leser, den es nicht gibt, faellt weg."""
    found: list[tuple[str, str]] = []
    for domain, reader_id in entries:
        if reader_plugins.reader_spec_v1(reader_id, domain) is None:
            continue
        item = ("crypto", "crypto_exports_v1") if domain == "crypto" else ("rewards", reader_id) if domain == "reward" else (domain, reader_id)
        if item not in found:
            found.append(item)
    return tuple(found)


def statement_recipes_v1() -> list[dict[str, Any]]:
    """Die Rezepte aller geladenen Plugins: aktive vor historischen, je nach Name."""
    recipes = [{"key": item["key"], "label": item["label"], "status": item["status"], "folders": item["folders"], "downloads": item["downloads"],
                "period": item["period"], "covers": item["covers"], "readers": _recipe_readers(item["readers"]), "words": item["account_words"],
                "tax_fallback": item["tax_all_accounts"]} for item in reader_plugins.intake_recipes_v1()]
    return sorted(recipes, key=lambda recipe: (recipe["status"] != "active", recipe["label"].casefold(), recipe["key"]))


def _folder_words(name: str) -> tuple[str, ...]:
    """Ein Unterordner ohne Rezept heisst meist wie sein Institut: sein Name als Wort fuer den Kontovorschlag ("Beispiel_Bank" -> "beispiel bank"). Ein Name ohne Buchstaben gibt keins."""
    words = " ".join(re.sub(r"[_\-]+", " ", name).lower().split())
    return (words,) if re.search(r"[a-zäöüß]", words) else ()


def _normal(name: str) -> str:
    return re.sub(r"[^a-z0-9+]", "", name.lower())


def recipe_for_folder_v1(name: str) -> dict[str, Any] | None:
    """Das Rezept zu einem Unterordner: Name ohne Gross-/Kleinschreibung, Leer- und Satzzeichen, oder None. Ein Name, der mit
    einem Institut beginnt ("Baader_Depot", "Scalable Archiv"), gehoert zu ihm (seit rc.318); der laengste Anfang gilt."""
    normal = _normal(name)
    recipes = statement_recipes_v1()
    for recipe in recipes:
        if normal == recipe["key"].replace("_", "") or normal in {_normal(alias) for alias in recipe["folders"]}:
            return recipe
    first = _normal(re.split(r"[^A-Za-z0-9+.äöüÄÖÜß]+", name.strip())[0]) if name.strip() else ""
    prefixes = [(len(alias), recipe) for recipe in recipes for alias in {_normal(alias) for alias in recipe["folders"]} | {recipe["key"].replace("_", "")}
                # Kurze Namen (ING) nur als ganzes erstes Wort: "ING-Depot" ja, "Ingolstadt" nein.
                if (len(alias) >= 4 and normal.startswith(alias)) or first == alias]
    return max(prefixes, key=lambda item: item[0])[1] if prefixes else None


def reader_label_v1(kind: str, adapter_id: str) -> str:
    """Die Bezeichnung eines Lesers, wie sie der Import zeigt."""
    from migrations.reference import cash_statement_import_v1 as cash
    from migrations.reference import securities_statement_import_v1 as securities
    if kind == "cash":
        return cash.ADAPTERS[adapter_id]["label"]
    if kind == "rewards":
        return reader_plugins.reader_spec_v1(adapter_id, "reward").institution
    return securities.ADAPTERS[adapter_id]["label"]


def recipe_table_markdown_v1() -> list[str]:
    """Die Tabelle "Rezepte je Institut" im Handbuch (monatlicher-eingang.md) - aus den Rezepten erzeugt; der Vertragstest
    verlangt sie dort wortgleich, damit sie nicht still veraltet (#522)."""
    rows = ["| Institut | Stand | Herunterladen | Deckt ab | Leser | Unterordner |", "|---|---|---|---|---|---|"]
    for recipe in list_statement_recipes_v1():
        readers = " · ".join(reader["label"] for reader in recipe["readers"]) or "keiner – nur ablegen"
        rows.append(f"| {recipe['label']} | {recipe['status_label']} | {'; '.join(recipe['downloads'])} | {recipe['covers']} | {readers} | "
                    f"{', '.join(recipe['folders'])} |")
    return rows


def list_statement_recipes_v1() -> list[dict[str, Any]]:
    """Die Rezepte fuer die Oberflaeche - ohne Parser, nur Text, Leserkennungen und ihre Bezeichnungen."""
    return [{"key": recipe["key"], "label": recipe["label"], "status": recipe["status"], "status_label": STATUS_LABELS[recipe["status"]],
             "folders": list(recipe["folders"]), "downloads": list(recipe["downloads"]), "period": recipe["period"],
             "period_rule": PERIOD_RULES[recipe["period"]], "covers": recipe["covers"],
             "readers": [{"import_kind": kind, "adapter_id": adapter, "label": reader_label_v1(kind, adapter)} for kind, adapter in recipe["readers"]]}
            for recipe in statement_recipes_v1()]


# Ein Ordner "Sonstiges" unter einem Jahr (rc.321): Was der Eigentuemer dort einsortiert, ist "Sonstiges" dieses Jahres - ohne
# Leser, kein Import nimmt es. So ordnet er selbst ein, was der Eingang sonst falsch oder gar nicht liest (Info-Schreiben,
# Kontoeroeffnung, Bestandsveraenderungen).
OTHER_FOLDER = "sonstiges"
OTHER_READER = "Ordner „Sonstiges“"
# Ein Ordner "Vorabpauschalen" unter einem Jahr (#536, Festlegung 04.11.2026): Was dort liegt, ist eine Vorabpauschale - die Leser
# lesen es trotzdem wie jede Datei (Betrag und Uebernahme beim Wertpapier-Import); der Ordner setzt nur die Art. Das Jahr ist das
# des Zuflusses, wie bei den Lesern: Die Vorabpauschale fuer 2024 fliesst am ersten Werktag 2025 zu und gehoert in den Ordner 2025.
ADVANCE_FOLDERS = ("vorabpauschalen", "vorabpauschale")
ADVANCE_READER = "Ordner „Vorabpauschalen“"


def _folder_year(directory: Path | None, path: Path, names: tuple[str, ...]) -> int | None:
    """Das Jahr von <Institut>/<Jahr>/<Ordner>/..., sonst None."""
    if directory is None:
        return None
    try:
        parts = path.relative_to(directory).parts
    except ValueError:
        return None
    if len(parts) >= 3 and re.fullmatch(r"(?:19|20)\d{2}", parts[0]) and parts[1].casefold() in names:
        return int(parts[0])
    return None


def _other_year(directory: Path | None, path: Path) -> int | None:
    """Das Jahr von <Institut>/<Jahr>/Sonstiges/..., sonst None."""
    return _folder_year(directory, path, (OTHER_FOLDER,))


def _advance_year(directory: Path | None, path: Path) -> int | None:
    """Das Jahr von <Institut>/<Jahr>/Vorabpauschalen/..., sonst None."""
    return _folder_year(directory, path, ADVANCE_FOLDERS)


def _skip(name: str) -> bool:
    return name.startswith(".") or name.startswith("~$") or name.lower() in SYSTEM_FILES


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _folder(space, context, folder) -> Path:
    if folder is None:
        folder = read_statement_intake_folder_v1(space, context)
    if folder is None:
        raise StatementArchiveV1Error("statement_intake_folder_invalid")
    path = Path(folder)
    if not isinstance(folder, str) or not path.is_absolute() or path.is_symlink() or not path.is_dir():
        raise StatementArchiveV1Error("statement_intake_folder_invalid")
    return path


def _files_below(root: Path, budget: list[int]) -> list[Path]:
    """Alle Dateien unter einem Ordner, ohne Verknuepfungen und versteckte Ordner, in fester Folge."""
    found: list[Path] = []
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if not _skip(name) and not (Path(current) / name).is_symlink())
        for name in sorted(files):
            path = Path(current) / name
            if _skip(name) or path.is_symlink() or not path.is_file():
                continue
            if budget[0] <= 0:
                raise StatementArchiveV1Error("statement_intake_too_many_files")
            budget[0] -= 1
            found.append(path)
    # Nach dem Pfad sortiert: Unterordner und Dateien in der Folge, in der man sie im Ordner liest.
    return sorted(found, key=lambda path: str(path).lower())


def _fingerprint(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def _inactive_accounts(space, context) -> dict[str, str]:
    return {account: state["inactive_since"] for account, state in read_statement_account_states_v1(space, context).items()
            if state["inactive_since"] is not None}


def _group(space, context, root: Path, directory: Path | None, files: list[Path], known: dict[str, str], closures: dict[str, str],
           include_withdrawn: bool = False, inactive: dict[str, str] | None = None) -> dict[str, Any]:
    """'include_withdrawn' (rc.320): Dateien, deren Dokumente alle zurueckgezogen sind, schlaegt der Eingang erneut vor - nur auf
    ausdrueckliche Wahl. Ohne sie bleibt eine bewusst zurueckgezogene Datei draussen, statt jeden Monat wieder aufzutauchen."""
    recipe = recipe_for_folder_v1(directory.name) if directory is not None else None
    # Ohne Rezept zaehlt der Name des Unterordners als Institut (#486), wenn er genau ein Institut der Konten trifft; sonst entscheidet wie
    # bisher die Kontonummer (statement_archive_suggestion_v1._fallback_accounts).
    words, fallback = (recipe["words"], recipe["tax_fallback"]) if recipe is not None else (_folder_words(directory.name) if directory is not None else (), True)
    institution = {"words": words, "tax_fallback": fallback, **({"from_folder": True} if recipe is None else {})} if words else None
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in files:
        relative = str(path.relative_to(root))
        row: dict[str, Any] = {"relative_path": relative, "name": path.name, "size_bytes": path.stat().st_size, "file_sha256": None, "state": "new",
                               "reader": None, "document_kind": None, "period_from": None, "period_to": None, "account_ids": [], "complete": False,
                               "reason": None}
        if row["size_bytes"] > MAX_FILE_BYTES:
            row.update(state="too_large", reason="too_large")
        else:
            try:
                sha = _sha(path)
            except OSError:
                row.update(state="unreadable", reason="unreadable")
                rows.append(row)
                continue
            row["file_sha256"] = sha
            if sha in seen:
                row["state"] = "duplicate"
            else:
                seen.add(sha)
                row["state"] = known.get(sha, "new")
        rows.append(row)
    fresh = [row for row in rows if row["state"] == "new" or (include_withdrawn and row["state"] == "withdrawn")]
    if fresh:
        # Der Vorschlag nimmt hoechstens 2000 Dateien je Aufruf: in Stapeln.
        suggestions = []
        for begin in range(0, len(fresh), SUGGEST_BATCH):
            batch = fresh[begin:begin + SUGGEST_BATCH]
            years = [_other_year(directory, root / row["relative_path"]) for row in batch]
            advance = [_advance_year(directory, root / row["relative_path"]) for row in batch]
            suggestions += suggest_statement_placements_v1(space, context, [(str(root / row["relative_path"]), row["name"]) for row in batch],
                                                           institution, years, advance)["files"]
        for row, suggestion in zip(fresh, suggestions):
            for key in ("reader", "document_kind", "period_from", "period_to", "account_ids", "complete", "reason"):
                row[key] = suggestion[key]
            if _other_year(directory, root / row["relative_path"]) is not None:
                row["reader"] = OTHER_READER
            elif _advance_year(directory, root / row["relative_path"]) is not None:
                row["reader"] = ADVANCE_READER if row["reader"] is None else f"{row['reader']} · {ADVANCE_READER}"
            # Ein Konto, das vor dem Zeitraum der Datei geschlossen wurde, nimmt der Eingang nicht an (#513).
            closed = [account for account in row["account_ids"] if account in closures and row["period_from"] and row["period_from"] > closures[account][:7]]
            if closed:
                row.update(complete=False, reason="account_closed")
            # Ein ruhendes Konto (#529 Punkt 1) nimmt der Eingang fuer die Zeit seit dem Tag nicht an; erst wieder aktivieren.
            resting = [account for account in row["account_ids"] if account in (inactive or {}) and row["period_from"]
                       and row["period_from"] > inactive[account][:7]]
            if resting and not closed:
                row.update(complete=False, reason="account_inactive")
    proposal = [{"file_sha256": row["file_sha256"], "relative_path": row["relative_path"], "document_kind": row["document_kind"],
                 "period_from": row["period_from"], "period_to": row["period_to"], "account_ids": sorted(row["account_ids"]),
                 **({"refile": True} if row["state"] == "withdrawn" else {})}
                for row in rows if row["state"] in ("new", "withdrawn") and row["complete"]]
    counts = {state: sum(row["state"] == state for row in rows) for state in ("new", "filed", "withdrawn", "removed", "duplicate", "too_large", "unreadable")}
    counts["ready"] = sum(row["state"] == "new" and row["complete"] for row in rows)
    counts["open"] = counts["new"] - counts["ready"]
    # Zurueckgezogene, die erneut abgelegt werden koennen (nur mit 'include_withdrawn'), und die, denen dafuer Zeitraum oder Konto fehlt.
    counts["refile"] = sum(row["state"] == "withdrawn" and row["complete"] for row in rows)
    counts["refile_open"] = sum(row["state"] == "withdrawn" and not row["complete"] for row in rows) if include_withdrawn else 0
    return {"folder": None if directory is None else directory.name, "recipe_key": None if recipe is None else recipe["key"],
            "recipe_label": None if recipe is None else recipe["label"], "recipe_status": None if recipe is None else recipe["status"],
            "files": rows, "counts": counts, "proposal_fingerprint": _fingerprint(proposal)}


def scan_statement_intake_v1(space, context_value, folder=None, include_withdrawn=False) -> dict[str, Any]:
    """Eingang pruefen (#513): je Unterordner des Belegordners die Dateien mit ihrem Stand. Liest nur; schreibt nichts.

    Dateien direkt im Belegordner (ohne Institutsordner) stehen in einer eigenen Gruppe; sie bekommen kein Rezept.
    """
    context = statement_archive_scope_v1(context_value)
    if not isinstance(include_withdrawn, bool):
        raise StatementArchiveV1Error("statement_archive_input_invalid")
    root = _folder(space, context, folder)
    known = _known_files(space, context)
    closures = read_statement_account_closures_v1(space, context)
    inactive = _inactive_accounts(space, context)
    budget = [MAX_FILES]
    groups = []
    loose = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if _skip(child.name) or child.is_symlink():
            continue
        if child.is_dir():
            groups.append(_group(space, context, root, child, _files_below(child, budget), known, closures, include_withdrawn, inactive))
        elif child.is_file():
            if budget[0] <= 0:
                raise StatementArchiveV1Error("statement_intake_too_many_files")
            budget[0] -= 1
            loose.append(child)
    if loose:
        groups.append(_group(space, context, root, None, loose, known, closures, include_withdrawn, inactive))
    totals = {key: sum(group["counts"][key] for group in groups) for key in ("new", "filed", "ready", "open", "withdrawn", "refile")}
    return {"contract_version": CONTRACT, "status": "ready", "folder": str(root), "include_withdrawn": include_withdrawn, "institutions": groups, "totals": totals,
            "file_count": MAX_FILES - budget[0], "provider_access": False, "network_access": False, "canonical_write": False}


def store_statement_intake_v1(space, context_value, folder_name, expected_fingerprint, recorded_at_utc, confirmed, folder=None,
                              include_withdrawn=False) -> dict[str, Any]:
    """Die neuen Dateien eines Instituts ablegen (#513) - genau die der gezeigten Pruefung. Hat sich seither etwas geaendert
    (neue Datei, anderer Vorschlag), legt der Eingang nichts ab und verlangt eine neue Pruefung. Mit 'include_withdrawn' (rc.320)
    auch die zurueckgezogenen Dateien, die die Pruefung mit dieser Wahl zeigte; ihre alten Dokumente bleiben zurueckgezogen."""
    context = statement_archive_scope_v1(context_value)
    if confirmed is not True:
        raise StatementArchiveV1Error("statement_archive_confirmation_required")
    if not isinstance(include_withdrawn, bool):
        raise StatementArchiveV1Error("statement_archive_input_invalid")
    if not isinstance(folder_name, str) or not folder_name or "/" in folder_name or "\\" in folder_name or _skip(folder_name) \
            or not isinstance(expected_fingerprint, str) or re.fullmatch(r"[a-f0-9]{64}", expected_fingerprint) is None:
        raise StatementArchiveV1Error("statement_archive_input_invalid")
    root = _folder(space, context, folder)
    directory = root / folder_name
    if directory.is_symlink() or not directory.is_dir():
        raise StatementArchiveV1Error("statement_intake_changed")
    group = _group(space, context, root, directory, _files_below(directory, [MAX_FILES]), _known_files(space, context),
                   read_statement_account_closures_v1(space, context), include_withdrawn, _inactive_accounts(space, context))
    if group["proposal_fingerprint"] != expected_fingerprint:
        raise StatementArchiveV1Error("statement_intake_changed")
    stored = unchanged = refiled = 0
    refs = []
    for row in group["files"]:
        if row["state"] not in ("new", "withdrawn") or not row["complete"]:
            continue
        note = f"Eingang: {folder_name}" + (" (erneut abgelegt)" if row["state"] == "withdrawn" else "")
        document = {"document_kind": row["document_kind"], "period_from": row["period_from"], "period_to": row["period_to"],
                    "account_ids": row["account_ids"], "institution_label": None, "note": note[:1000]}
        result = store_statement_document_v1(space, context, str(root / row["relative_path"]), document, recorded_at_utc, True, original_name=row["name"])
        if result["status"] == "stored":
            stored += 1
            refiled += row["state"] == "withdrawn"
        else:
            unchanged += 1
        refs.append(result.get("document_ref"))
    return {"contract_version": CONTRACT, "status": "stored" if stored else "unchanged", "folder": folder_name, "stored_count": stored,
            "refiled_count": refiled, "unchanged_count": unchanged, "open_count": group["counts"]["open"], "recipe_key": group["recipe_key"],
            "provider_access": False, "network_access": False, "canonical_write": False}


__all__ = ["CONTRACT", "PERIOD_RULES", "statement_recipes_v1", "list_statement_recipes_v1", "recipe_table_markdown_v1", "recipe_for_folder_v1", "scan_statement_intake_v1",
           "store_statement_intake_v1"]
