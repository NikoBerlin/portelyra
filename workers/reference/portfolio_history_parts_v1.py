"""Teildateien der Tageshistorie (#503): Kern zum Start der Analyse, Tagesreihen erst bei Bedarf.

Eine grosse veroeffentlichte Tageshistorie liest die Analyse nur langsam. Den groessten Teil machen die Tagesreihen je Asset, Konto, Klasse und Gruppe aus.
Gezeigt werden sie aber nur, wenn man das Asset, die Klasse oder die Gruppe auswaehlt.

Deshalb gilt seit rc.297:
- Der **Kern** bleibt das veroeffentlichte Artefakt des Laufs: Portfolio, Anlage, Netto, Index, alle Zeitraumzeilen und je
  Asset, Klasse und Gruppe ein Verweis auf seine Teildatei (`part`, der SHA-256 ihrer Bytes).
- Jede **Teildatei** traegt die Tagesreihen eines Eintrags. Sie liegt unter `artifacts/portfolio_history_parts/<sha>.json`,
  benannt nach ihrem Abdruck. Was sich zwischen zwei Laeufen nicht aendert, liegt nur einmal da (inkrementell statt neu).
- Der Schreiber prueft jede Teildatei gegen `part.schema.json`, bevor er sie ablegt. Der Leser prueft den Abdruck gegen den
  Verweis im geprueften Kern. Damit gilt fuer die Teildatei dieselbe Pruefung wie fuer den Kern, ohne einen zweiten Aufruf.
- **Aufbewahrung** (Festlegung 22.10.2026): Nach jeder Veroeffentlichung bleiben die juengsten fuenf Laeufe. Teildateien, auf
  die keiner von ihnen verweist, werden geloescht, sobald sie eine Stunde alt sind. So trifft das Aufraeumen keine Datei, die
  ein gleichzeitig laufender Schreiber gerade ablegt.

Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time
from typing import Any

from migrations.reference.legacy_import_data_command_v1 import canonical_json_bytes, fingerprint
from migrations.reference.publication_limits_v1 import MAX_PART_BYTES

PARTS_AREA_ID = "portfolio_history_parts"
PART_VERSION = 1
KEEP_RUNS = 5
STALE_SECONDS = 3600
# "twr" (seit rc.299, #502): der TWR-Index je Tag ueber die Haltedauer fuer das Vergleichsbild.
# "prices" (seit rc.369, #526): der Kurs je Tag in Euro, auch ohne Bestand. Beobachtete, nie gehaltene Assets ("watched") haben
# nur diese Reihe.
ASSET_PART_FIELDS = ("days", "basis", "trades", "income", "net", "accounts", "twr", "prices")
WATCHED_PART_FIELDS = ("prices",)
CLASS_PART_FIELDS = ("basis", "realized_steps", "net_cost", "net_realized_steps", "twr", "net_cost_pooled", "net_realized_steps_pooled")
GROUP_PART_FIELDS = ("value", "basis", "realized_steps", "net_cost", "net_realized_steps", "twr", "net_cost_pooled", "net_realized_steps_pooled")
_ROOT = Path(__file__).resolve().parents[2]
_PART_SCHEMA = (_ROOT / "contracts" / "portfolio-history-publication" / "v1" / "part.schema.json",
                "d21ec4ca1b36f435b0e8d8c854dad32a9a132e2f6af350ae67d11e6fb9cb2a60")
_SHA = re.compile(r"[a-f0-9]{64}")
_RUN = re.compile(r"run_[a-z0-9_]+")


class PortfolioHistoryPartsV1Error(RuntimeError):
    CODES = frozenset({"portfolio_history_parts_invalid", "portfolio_history_parts_write_failed"})

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in self.CODES else "portfolio_history_parts_invalid"


def _abort(code: str) -> None:
    raise PortfolioHistoryPartsV1Error(code)


def _validator():
    import jsonschema
    path, expected = _PART_SCHEMA
    if path.is_symlink():
        _abort("portfolio_history_parts_invalid")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        _abort("portfolio_history_parts_invalid")
    return jsonschema.Draft202012Validator(json.loads(raw.decode("utf-8")))


def _part(artifact: dict[str, Any], kind: str, fields: dict[str, Any]) -> tuple[str, bytes, dict[str, Any]]:
    document = {"portfolio_history_part_version": PART_VERSION, "tenant_id": artifact["tenant_id"], "user_id": artifact["user_id"],
                "data_space_id": artifact["data_space_id"], "kind": kind, "fields": fields}
    payload = canonical_json_bytes(document) + b"\n"
    if len(payload) > MAX_PART_BYTES:
        _abort("portfolio_history_parts_invalid")
    return hashlib.sha256(payload).hexdigest(), payload, document


def _last_value(asset: dict[str, Any], last_day: str) -> str | None:
    """Der Wert am letzten Tag; leer ohne Bestand - auch am Abgangstag, der seit rc.369 mit Menge 0 in der Reihe steht (#526)."""
    days = asset["days"]
    if not days["day"] or days["day"][-1] != last_day or days["quantity"][-1] in ("0", None):
        return None
    return days["market_value"][-1]


def _last_quantity(asset: dict[str, Any], last_day: str) -> str | None:
    """Die Menge am letzten Tag (rc.317, #512): Die Analyse erkennt daran, ob seit dem letzten Tag gebucht wurde."""
    days = asset["days"]
    if not days["day"] or days["day"][-1] != last_day:
        return None
    return days["quantity"][-1]


def split_portfolio_history_v1(artifact: dict[str, Any]) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Den vollstaendigen Stand in Kern und Teildateien zerlegen; der Kern traegt einen neuen Artefakt-Abdruck.

    Inhalt (`content_fingerprint`) und Kennung bleiben die des ganzen Stands: Ein Lauf ist derselbe, wenn sich nichts geaendert hat.
    """
    validator = _validator()
    parts: dict[str, bytes] = {}

    def store(kind: str, fields: dict[str, Any]) -> str:
        sha, payload, document = _part(artifact, kind, fields)
        if sha not in parts:
            errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
            if errors:
                _abort("portfolio_history_parts_invalid")
            parts[sha] = payload
        return sha

    assets = []
    for asset in artifact["assets"]:
        fields = {key: asset[key] for key in ASSET_PART_FIELDS if key in asset}
        fields["performance"] = {"realized_steps": asset["performance"]["realized_steps"]}
        core = {key: value for key, value in asset.items() if key not in ASSET_PART_FIELDS and key != "performance"}
        core["performance"] = {"periods": asset["performance"]["periods"]}
        core["last_value"] = _last_value(asset, artifact["last_day"])
        core["last_quantity"] = _last_quantity(asset, artifact["last_day"])
        core["part"] = store("asset", fields)
        assets.append(core)
    watched = []
    for row in artifact.get("watched", []):
        fields = {key: row[key] for key in WATCHED_PART_FIELDS}
        watched.append({**{key: value for key, value in row.items() if key not in WATCHED_PART_FIELDS}, "part": store("watched", fields)})
    classes = []
    for row in artifact["classes"]:
        fields = {key: row.get(key) for key in CLASS_PART_FIELDS}
        classes.append({"class": row["class"], "periods": row["periods"], "part": store("class", fields)})
    groups = []
    for row in artifact["groups"]:
        fields = {key: row[key] for key in GROUP_PART_FIELDS}
        groups.append({**{key: value for key, value in row.items() if key not in GROUP_PART_FIELDS}, "part": store("group", fields)})
    core = {key: value for key, value in artifact.items() if key != "artifact_fingerprint"}
    core.update({"assets": assets, "classes": classes, "groups": groups})
    if "watched" in artifact:
        core["watched"] = watched
    core["artifact_fingerprint"] = fingerprint(core)
    return core, parts


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _parts_root(artifacts_root: Path) -> Path:
    root = Path(artifacts_root) / PARTS_AREA_ID
    if Path(artifacts_root).is_symlink() or root.is_symlink():
        _abort("portfolio_history_parts_write_failed")
    if not root.exists():
        root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def write_portfolio_history_parts_v1(artifacts_root: Path, parts: dict[str, bytes]) -> dict[str, int]:
    """Teildateien ablegen: neue atomar, vorhandene nur pruefen und als frisch markieren. Gibt die Zahl je Fall zurueck."""
    root = _parts_root(artifacts_root)
    written = reused = 0
    for sha, payload in parts.items():
        if _SHA.fullmatch(sha) is None or hashlib.sha256(payload).hexdigest() != sha:
            _abort("portfolio_history_parts_invalid")
        target = root / f"{sha}.json"
        if target.is_symlink():
            _abort("portfolio_history_parts_write_failed")
        if target.is_file():
            if hashlib.sha256(target.read_bytes()).hexdigest() == sha:
                # Wiederverwendet: das Alter zaehlt ab jetzt, damit das Aufraeumen sie nicht als verwaist ansieht.
                os.utime(target)
                reused += 1
                continue
        temporary = root / f"{sha}.json.tmp"
        try:
            if temporary.exists() or temporary.is_symlink():
                temporary.unlink()
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                view = memoryview(payload)
                while view:
                    view = view[os.write(descriptor, view):]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, target)
        except OSError:
            _abort("portfolio_history_parts_write_failed")
        written += 1
    _fsync_directory(root)
    return {"written": written, "reused": reused}


def _published_at(run: Path) -> str:
    try:
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        value = manifest.get("published_at_utc")
        return value if isinstance(value, str) else ""
    except (OSError, ValueError, AttributeError):
        return ""


def _referenced(run: Path) -> set[str] | None:
    """Die Teildateien eines Laufs; None, wenn sein Artefakt nicht lesbar ist (dann bleibt alles liegen)."""
    try:
        artifact = json.loads((run / "artifact.json").read_text(encoding="utf-8"))
        refs = {row.get("part") for key in ("assets", "watched", "classes", "groups") for row in artifact.get(key, [])}
    except (OSError, ValueError, AttributeError, TypeError):
        return None
    return {ref for ref in refs if isinstance(ref, str) and _SHA.fullmatch(ref)}


def prune_portfolio_history_v1(artifacts_root: Path, area_id: str, keep: int = KEEP_RUNS, now: float | None = None) -> dict[str, int]:
    """Aeltere Laeufe der Tageshistorie und verwaiste Teildateien loeschen; der Lauf, auf den latest.json zeigt, bleibt immer."""
    area = Path(artifacts_root) / area_id
    runs_root = area / "runs"
    if area.is_symlink() or runs_root.is_symlink() or not runs_root.is_dir():
        return {"runs_deleted": 0, "parts_deleted": 0}
    try:
        latest = json.loads((area / "latest.json").read_text(encoding="utf-8")).get("run_id")
    except (OSError, ValueError, AttributeError):
        return {"runs_deleted": 0, "parts_deleted": 0}
    runs = [item for item in runs_root.iterdir() if _RUN.fullmatch(item.name) and item.is_dir() and not item.is_symlink()]
    if latest not in {run.name for run in runs}:
        return {"runs_deleted": 0, "parts_deleted": 0}
    ordered = sorted(runs, key=lambda run: (run.name == latest, _published_at(run), run.name), reverse=True)
    kept, dropped = ordered[:keep], ordered[keep:]
    references: set[str] = set()
    for run in kept:
        refs = _referenced(run)
        if refs is None:
            return {"runs_deleted": 0, "parts_deleted": 0}
        references |= refs
    runs_deleted = 0
    for run in dropped:
        shutil.rmtree(run)
        runs_deleted += 1
    parts_deleted = 0
    parts_root = Path(artifacts_root) / PARTS_AREA_ID
    if parts_root.is_dir() and not parts_root.is_symlink():
        cutoff = (time.time() if now is None else now) - STALE_SECONDS
        for item in parts_root.iterdir():
            name = item.name
            sha = name[:-5] if name.endswith(".json") else name[:-9] if name.endswith(".json.tmp") else None
            if sha is None or _SHA.fullmatch(sha) is None or item.is_symlink():
                continue
            metadata = item.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_mtime > cutoff:
                continue
            if name.endswith(".json") and sha in references:
                continue
            item.unlink()
            parts_deleted += 1
    return {"runs_deleted": runs_deleted, "parts_deleted": parts_deleted}


__all__ = [
    "ASSET_PART_FIELDS", "CLASS_PART_FIELDS", "GROUP_PART_FIELDS", "KEEP_RUNS", "PARTS_AREA_ID", "PortfolioHistoryPartsV1Error",
    "prune_portfolio_history_v1", "split_portfolio_history_v1", "write_portfolio_history_parts_v1",
]
