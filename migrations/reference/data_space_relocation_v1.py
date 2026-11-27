"""Restore an einen anderen Ort (#493): Der Restore bindet neu.

Einige Speicher binden den absoluten Pfad des Datenraums in ihre Pruefwerte (Wechselkurs-Abrufversuche, Wechselkurs-Sammelabruf,
Arbeitsliste der Kurszuordnung und die davon abgeleitete Bindung der Bewertung, Kalenderregister, Kalenderkorrekturen). An einem
anderen Ort weisen sie ihre eigenen Eintraege ab. Statt versiegelte Pruefspuren umzuschreiben, vermerkt `relocate_v1` nach einem
Restore den Ursprungsort - erst nachdem er gegen gespeicherte Bindungen verifiziert ist. Diese Speicher bilden ihre Bindung dann aus
dem Ursprungsort (`origin_v1`). Ohne Vermerk (etwa eine von Hand kopierte Kopie) bleibt alles wie bisher: abgewiesen.

Der Vermerk nennt Ursprung und den Ort, fuer den er bestaetigt wurde, und gilt nur dort: Eine von Hand kopierte Kopie traegt ihn mit,
wird aber weiter abgewiesen. Er gehoert nicht in Backups (er beschreibt diesen Ort, nicht den Bestand). Der Restore bindet selbst
(`bind_restored_data_space_v1` im Release-Worker): Er kennt den Ursprung aus der laufenden Installation und prueft ihn hier. Ohne
Hinweis kommen die frueheren Orte aus den Auftraegen des Run Centers, notfalls nennt der Eigentuemer ihn (`relocate --origin`).

Passwortschutz (#487, rc.401): Entsperrt liegt der Bestand unter $XDG_RUNTIME_DIR - auch das ist ein anderer Ort. Einrichten und
Entsperren vermerken deshalb den bisherigen Ort (desktop_protection_v1._bind_mounted). Damit der Notfall-Restore aus dem verschluesselten
Backup-Ordner den Ursprung auch ohne altes Home und ohne Auftraege des Run Centers findet, haelt eine Notiz im Datenraum fest, an welchen
Ort die Speicher gebunden sind (`note_origin_v1`, Bereich data-space-origin-v1); sie geht mit ins Backup und ist nur ein Hinweis.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Iterable

AREA = "data-space-relocation-v1"
FILE = "origin.json"
CONTRACT = "data_space_relocation_v1"
# Notiz des Ursprungs (#487): ein eigener Bereich, weil er - anders als der Vermerk - ins Backup gehoert.
NOTE_AREA = "data-space-origin-v1"
NOTE_CONTRACT = "data_space_origin_note_v1"
FAILURE_CODES = ("data_space_relocation_input_invalid", "data_space_relocation_confirmation_required", "data_space_relocation_unverified")


class DataSpaceRelocationV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "data_space_relocation_input_invalid"


def _same_identity(origin: Path, space: Path) -> bool:
    """Gleicher Mandant, Benutzer und Datenraum: nur der Ort davor darf anders sein."""
    return (origin.is_absolute() and origin.name == space.name and origin.parent.name == space.parent.name
            and origin.parent.parent.name == space.parent.parent.name and origin != space)


def _record(space: Path) -> dict[str, Any] | None:
    path = space / AREA / FILE
    try:
        if not path.is_file() or path.is_symlink() or stat.S_IMODE(path.stat().st_mode) & 0o077 or path.stat().st_uid != os.getuid():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("contract_version") != CONTRACT or not isinstance(value.get("origin"), str) \
            or not isinstance(value.get("place"), str):
        return None
    return value


def origin_v1(space: str | Path) -> Path:
    """Der Ort, aus dem die pfadgebundenen Speicher ihre Bindung bilden: der vermerkte Ursprung, sonst der Datenraum selbst. Ein
    unlesbarer, fremder oder fuer einen anderen Ort bestaetigter Vermerk zaehlt nicht (die Speicher weisen dann wie bisher ab)."""
    space = Path(space)
    value = _record(space)
    if value is None or not _here(Path(value["place"]), space):
        return space
    origin = Path(value["origin"])
    return origin if _same_identity(origin, space) else space


def _here(place: Path, space: Path) -> bool:
    try:
        return place == space or place == space.resolve(strict=True)
    except OSError:
        return False


def _ids(space: Path) -> dict[str, str]:
    return {"tenant_id": space.parent.parent.name, "user_id": space.parent.name, "data_space_id": space.name}


def _probes(space: Path) -> list[tuple[str, Any, Any]]:
    """Gespeicherte Bindungen, an denen sich ein Ort pruefen laesst: je (Art, gespeicherter Wert, Funktion Ort -> erwarteter Wert)."""
    from migrations.reference import desktop_market_fx_batch_execution_v1 as files  # noqa: PLC0415
    ctx = _ids(space)
    scope = lambda place: files._sha({"context": ctx, "absolute_data_space": str(place)})
    probes = []
    for area, domain in (("market-valuation-v1", "market-valuation-v1"), ("market-mapping-worklist-v1", "provider")):
        stored = _read_json(space / area / ".context")
        if stored is not None:
            probes.append((area, stored, lambda place, domain=domain: {"binding": files._sha({"scope": scope(place), "domain": domain})}))
    stored = _read_json(space / "market-fx-batch-execution-v1" / ".context")
    if stored is not None:
        probes.append(("market-fx-batch-execution-v1", stored, lambda place: {"context_fingerprint": files._sha(ctx), "data_space_fingerprint": files._sha(str(place))}))
    # Kalenderregister: alle Bindungen tragen denselben Eigentuemer-Abdruck (das Register prueft das selbst), einer genuegt.
    from migrations.reference import market_calendar_registry_v1 as calendar  # noqa: PLC0415
    stored = _first_calendar_owner(space / calendar.AREA / calendar.STORE)
    if stored is not None:
        probes.append((calendar.AREA, stored, lambda place: calendar._sha({"path": str(place), "context": ctx})))
    # Wechselkurs-Abrufversuche (ab Fassung 2): ebenso ein Abdruck fuer alle.
    from migrations.reference import desktop_fx_history_review_v1 as review  # noqa: PLC0415
    stored = _first_attempt_owner(space / review.STAGE_AREA / "attempts")
    if stored is not None:
        probes.append((review.STAGE_AREA, stored, lambda place: review._sha([str(place), ctx["tenant_id"], ctx["user_id"], ctx["data_space_id"]])))
    return probes


def _first_calendar_owner(store: Path) -> Any:
    if not store.is_file() or store.is_symlink():
        return None
    try:
        connection = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
        try:
            row = connection.execute("SELECT owner_fingerprint FROM calendar_binding_owner ORDER BY binding_fingerprint LIMIT 1").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return None
    return row[0] if row else None


def _first_attempt_owner(folder: Path) -> Any:
    if not folder.is_dir() or folder.is_symlink():
        return None
    for path in sorted(folder.glob("fxh_*.json")):
        value = _read_json(path)
        if isinstance(value, dict) and value.get("contract_version") == "desktop_fx_history_attempt_v2":
            return value.get("owner_fingerprint")
    return None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() and not path.is_symlink() else None
    except (OSError, ValueError):
        return None


def _noted(space: Path) -> Path | None:
    value = _read_json(space / NOTE_AREA / FILE)
    if not isinstance(value, dict) or value.get("contract_version") != NOTE_CONTRACT or not isinstance(value.get("origin"), str):
        return None
    return Path(value["origin"])


def note_origin_v1(space: str | Path) -> None:
    """Haelt im Datenraum fest, an welchen Ort seine pfadgebundenen Speicher gebunden sind (`origin_v1`). Anders als der Vermerk geht die
    Notiz mit ins Backup: Ist das alte Home verloren, findet der Restore den Ursprung darin (#487) - geprueft wird er wie jeder Hinweis.
    Schreibt nur bei Aenderung."""
    space = Path(space)
    origin = origin_v1(space)
    if _noted(space) == origin:
        return
    area = space / NOTE_AREA
    area.mkdir(mode=0o700, exist_ok=True)
    os.chmod(area, 0o700)
    temporary = area / (FILE + ".partial")
    temporary.write_text(json.dumps({"contract_version": NOTE_CONTRACT, "origin": str(origin)}, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, area / FILE)


def candidates_v1(space: str | Path) -> list[Path]:
    """Fruehere Orte: die Notiz im Datenraum, dann die Auftraege des Run Centers (sie tragen den Datenraum, fuer den sie bestaetigt wurden)."""
    space = Path(space)
    found: list[Path] = []
    noted = _noted(space)
    if noted is not None and _same_identity(noted, space):
        found.append(noted)
    for job in sorted((space / "run-center" / "jobs").glob("run_drw_*.json")):
        try:
            runtime = json.loads(json.loads(job.read_text(encoding="utf-8"))["payload_json"])["runtime"]
            place = Path(runtime["data_root"]) / runtime["tenant_id"] / runtime["user_id"] / runtime["data_space_id"]
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if _same_identity(place, space) and place not in found:
            found.append(place)
    return found


def relocate_v1(space: str | Path, confirmed: Any, origin: str | None = None, hints: Iterable[str | Path] = ()) -> dict[str, Any]:
    """Nach einem Restore an einen anderen Ort: den Ursprung finden (ausdruecklich angegeben, sonst die Hinweise des Aufrufers - etwa
    der Ursprung der laufenden Installation - und die Auftraege des Run Centers), gegen alle gespeicherten Bindungen pruefen und
    vermerken. Schreibt nur den Vermerk, nichts an den Speichern selbst."""
    if confirmed is not True:
        raise DataSpaceRelocationV1Error("data_space_relocation_confirmation_required")
    space = Path(space)
    if not space.is_absolute() or not space.is_dir() or space.is_symlink():
        raise DataSpaceRelocationV1Error("data_space_relocation_input_invalid")
    space = space.resolve()
    probes = _probes(space)
    current = origin_v1(space)
    if all(stored == expected(current) for _, stored, expected in probes):
        return {"contract_version": CONTRACT, "status": "present" if current != space else "not_needed", "probe_count": len(probes)}
    # `--origin` darf auch das fruehere Home nennen (wie im Handbuch); der Datenraum liegt dort unter data/<Mandant>/<Benutzer>/<Raum>.
    places = [Path(origin), Path(origin) / "data" / space.parent.parent.name / space.parent.name / space.name] if origin \
        else [*(Path(hint) for hint in hints), *candidates_v1(space)]
    for place in places:
        if _same_identity(place, space) and all(stored == expected(place) for _, stored, expected in probes):
            _write(space, place)
            note_origin_v1(space)
            return {"contract_version": CONTRACT, "status": "recorded", "probe_count": len(probes)}
    raise DataSpaceRelocationV1Error("data_space_relocation_unverified")


# Deutsche Namen der Speicher fuer den Hinweis (#556); die Reihenfolge folgt den Pruefpunkten.
STORE_LABELS = {"market-valuation-v1": "Bewertung", "market-mapping-worklist-v1": "Kurszuordnung",
                "market-fx-batch-execution-v1": "Wechselkurs-Sammelabruf", "market-calendar-v1": "Kalender",
                "desktop-fx-history-review-v1": "Wechselkurs-Abrufe"}


def status_v1(space: str | Path) -> dict[str, Any]:
    """Nur lesend (#556): ob die pfadgebundenen Speicher an diesem Ort ihre Eintraege anerkennen. "unbound" heisst: Der Datenraum liegt
    an einem anderen Ort als beim Anlegen und ist dort nicht gebunden (Restore mit `unverified`, oder eine von Hand kopierte Kopie).
    Bindet nie selbst - eine Handkopie soll nicht wie der Bestand behandelt werden."""
    space = Path(space)
    if not space.is_absolute() or not space.is_dir() or space.is_symlink():
        raise DataSpaceRelocationV1Error("data_space_relocation_input_invalid")
    space = space.resolve()
    probes = _probes(space)
    origin = origin_v1(space)
    failing = [area for area, stored, expected in probes if stored != expected(origin)]
    return {"contract_version": CONTRACT, "status": "unbound" if failing else "bound", "probe_count": len(probes),
            "unbound_stores": [STORE_LABELS.get(area, area) for area in failing], "recorded": origin != space}


def _write(space: Path, origin: Path) -> None:
    area = space / AREA
    area.mkdir(mode=0o700, exist_ok=True)
    os.chmod(area, 0o700)
    target = area / FILE
    temporary = area / (FILE + ".partial")
    temporary.write_text(json.dumps({"contract_version": CONTRACT, "origin": str(origin), "place": str(space)}, sort_keys=True) + "\n",
                         encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)


def relative_paths_v1() -> Iterable[str]:
    """Was Backups und Abnahmepruefung nicht mitnehmen (der Vermerk beschreibt den Ort, nicht den Bestand)."""
    return (AREA,)


__all__ = ["AREA", "CONTRACT", "DataSpaceRelocationV1Error", "FAILURE_CODES", "NOTE_AREA", "STORE_LABELS", "candidates_v1", "note_origin_v1",
           "origin_v1", "relative_paths_v1", "relocate_v1", "status_v1"]
