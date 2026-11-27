"""Unveraenderliche Publikation des Stichtagsbilds. Plan und Anwendung getrennt.

Der Plan zeigt, was veroeffentlicht wuerde, ohne etwas zu schreiben. Die
Anwendung erhebt ihn unter demselben Weg erneut und bricht ab, wenn sich
zwischenzeitlich etwas geaendert hat - dann waere das Veroeffentlichte ein
anderes als das Bestaetigte (#373, Schritt 3, 26.09.2026).

Zwei Statusfelder, die nicht dasselbe meinen: 'status' der Publikationshuelle
sagt, dass der Lauf abgeschlossen ist; 'snapshot_status' ist die fachliche
Aussage und lautet nur dann 'complete', wenn jede Ebene vollstaendig ist und
jede gehaltene Position einen Marktwert hat. Ein teilweiser Lauf veroeffentlicht
keinen gemischten "vollstaendig"-Status.
"""
from __future__ import annotations

from datetime import datetime
import os
import re
import shutil
import sqlite3
from pathlib import Path
from typing import Any

from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1,
    read_desktop_product_asset_activity_binding_v1,
)
from workers.reference.portfolio_snapshot_projection_v1 import (
    PortfolioSnapshotProjectionV1Error,
    project_portfolio_snapshot_v1,
)

AREA_ID = "portfolio_snapshot"
WRITER_ID = "desktop_portfolio_snapshot_worker"
WRITER_ROLE = "portfolio_worker"


class PortfolioSnapshotPublicationV1Error(RuntimeError):
    CODES = frozenset({
        "portfolio_snapshot_publication_context_invalid",
        "portfolio_snapshot_publication_input_invalid",
        "portfolio_snapshot_publication_evidence_invalid",
        "portfolio_snapshot_publication_plan_stale",
        "portfolio_snapshot_publication_confirmation_required",
        "portfolio_snapshot_publication_failed",
        "portfolio_snapshot_publication_boundary_failed",
    })

    def __init__(self, code: str):
        if code not in self.CODES:
            raise ValueError("portfolio_snapshot_publication_error_code_unregistered")
        self.code = code
        super().__init__(code)


def portfolio_snapshot_publication_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(PortfolioSnapshotPublicationV1Error.CODES))


def _abort(code: str) -> None:
    raise PortfolioSnapshotPublicationV1Error(code)


def _sha(value: Any) -> str:
    """Derselbe Abdruck, den Publikationsweg und Leser bilden.

    Beide serialisieren mit ensure_ascii=False. Ein eigener Abdruck mit
    ensure_ascii=True stimmte fuer reinen ASCII-Inhalt zufaellig ueberein und
    brach, sobald ein Wort einen Umlaut trug - hier die Begruendung einer
    ausgelassenen Position (gefunden im Vertragstest, 26.09.2026).
    """
    from migrations.reference.legacy_import_data_command_v1 import fingerprint
    return fingerprint(value)


def _utc(value: Any) -> str:
    from datetime import datetime, timezone
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        _abort("portfolio_snapshot_publication_input_invalid")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort("portfolio_snapshot_publication_input_invalid")
    return value


def _portfolio(data_space: Path, context: DesktopProductAssetActivityContextV1) -> tuple[str, str, str]:
    """Portfolio, Bezeichnung und Basiswaehrung aus der aktiven Generation."""
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding.get("status") != "available" or not binding.get("ledger_path"):
        _abort("portfolio_snapshot_publication_evidence_invalid")
    connection = sqlite3.connect("file:" + str(binding["ledger_path"]) + "?mode=ro", uri=True)
    try:
        rows = list(connection.execute(
            "SELECT portfolio_id, display_name, base_currency FROM current_portfolio_revision "
            "ORDER BY portfolio_id"))
    except sqlite3.Error:
        _abort("portfolio_snapshot_publication_evidence_invalid")
    finally:
        connection.close()
    if len(rows) != 1:
        # Mehrere Portfolios brauchen eine Wahl; ein Snapshot ohne benanntes
        # Portfolio waere eine stillschweigende Zusammenfassung.
        _abort("portfolio_snapshot_publication_input_invalid")
    return rows[0][0], rows[0][1], rows[0][2]


def _artifact(data_space: Path, context: DesktopProductAssetActivityContextV1,
              as_of_date: str, completed_at_utc: str,
              canonical_path: str | Path | None, price_source: Any = None) -> dict[str, Any]:
    try:
        projection = project_portfolio_snapshot_v1(data_space, context, as_of_date, canonical_path, price_source=price_source)
    except PortfolioSnapshotProjectionV1Error as error:
        if error.code == "portfolio_snapshot_projection_input_invalid":
            _abort("portfolio_snapshot_publication_input_invalid")
        _abort("portfolio_snapshot_publication_evidence_invalid")
    portfolio_id, label, currency = _portfolio(data_space, context)
    body = {
        # Fassung 4 traegt den Cash-Bestand je Konto, seine Summe und das
        # Gesamtvermoegen (Festlegung 11.10.2026). Fassung 3 fuehrte Cash
        # nur als Ebene der Frische, ohne Betrag. Fassung 5 fuehrt zusaetzlich
        # aus Bewegungen abgeleitete Salden - gezaehlt und als solche benannt.
        "portfolio_snapshot_version": 5,
        "status": "completed",
        "snapshot_status": "complete" if projection["market_value_complete"] else "partial",
        "tenant_id": context.tenant_id, "user_id": context.user_id,
        "data_space_id": context.data_space_id,
        "portfolio_id": portfolio_id, "portfolio_label": label, "base_currency": currency,
        "as_of_date": projection["as_of_date"],
        "completed_at_utc": completed_at_utc,
        "freshness": {"overall_status": projection["freshness"]["overall_status"],
                      "levels": projection["freshness"]["levels"],
                      "latest_valued_date": projection["freshness"].get("latest_valued_date")},
        "positions": projection["positions"],
        "excluded_positions": projection["excluded_positions"],
        "cash": projection["cash"],
        "totals": projection["totals"],
        "counts": projection["counts"],
        "market_value_complete": projection["market_value_complete"],
        "unrealised_before_fees_and_tax": True,
        "worker_id": WRITER_ID,
    }
    # Die Kennung haengt am Inhalt: Derselbe Stand ergibt dieselbe Kennung, und
    # ein veraenderter Stand kann nicht unter der alten erscheinen.
    body["snapshot_id"] = "psn_" + _sha({k: v for k, v in body.items()
                                         if k != "completed_at_utc"})[:32]
    body["artifact_fingerprint"] = _sha(body)
    return body


def plan_portfolio_snapshot_publication_v1(
    data_space_path: str | Path,
    context_value: Any,
    as_of_date: str,
    planned_at_utc: str,
    canonical_path: str | Path | None = None,
) -> dict[str, Any]:
    """Was veroeffentlicht wuerde. Schreibt nichts."""
    try:
        if not isinstance(context_value, DesktopProductAssetActivityContextV1):
            _abort("portfolio_snapshot_publication_context_invalid")
        artifact = _artifact(Path(data_space_path), context_value, as_of_date,
                             _utc(planned_at_utc), canonical_path)
        latest_valued = artifact["freshness"].get("latest_valued_date")
        # Haelt der Eigentuemer am Stichtag nur, was er selbst bewertet oder ohne Wert fuehrt (etwa der Umfang ohne Kursabruf, #567),
        # gibt es am Markt nichts zu bewerten - und damit kein Bewertungsfenster, hinter dem der Stichtag liegen koennte. Bis rc.410
        # galt jeder solche Stichtag als "hinter dem Fenster", und der Snapshot hielt an, obwohl alle Positionen bewertet waren.
        market_level = next((level for level in artifact["freshness"].get("levels") or [] if level.get("level_code") == "market_history"), {})
        nothing_to_value = market_level.get("reason_code") == "nothing_to_value"
        return {
            "portfolio_snapshot_publication_plan_version": 1,
            "as_of_date": artifact["as_of_date"],
            "snapshot_status": artifact["snapshot_status"],
            "portfolio_label": artifact["portfolio_label"],
            "freshness": artifact["freshness"],
            "latest_valued_date": latest_valued,
            "beyond_valued_window": bool(
                not nothing_to_value and (latest_valued is None or artifact["as_of_date"] > latest_valued)),
            "totals": artifact["totals"],
            "counts": artifact["counts"],
            # Der Abdruck laesst den Zeitpunkt aus: Er soll den Inhalt binden,
            # nicht die Sekunde, in der geplant wurde.
            "plan_fingerprint": _sha({k: v for k, v in artifact.items()
                                      if k not in ("completed_at_utc", "artifact_fingerprint")}),
            "provider_access": False, "network_access": False,
            "canonical_write": False, "artifact_write": False, "path_exposed": False,
        }
    except PortfolioSnapshotPublicationV1Error:
        raise
    except Exception:
        _abort("portfolio_snapshot_publication_boundary_failed")


def apply_portfolio_snapshot_publication_v1(
    data_space_path: str | Path,
    context_value: Any,
    as_of_date: str,
    plan_fingerprint: str,
    confirmed: bool,
    published_at_utc: str,
    artifacts_root: str | Path | None = None,
    canonical_path: str | Path | None = None,
) -> dict[str, Any]:
    """Genau den bestaetigten Plan veroeffentlichen - sonst gar nichts."""
    try:
        if not isinstance(context_value, DesktopProductAssetActivityContextV1):
            _abort("portfolio_snapshot_publication_context_invalid")
        if confirmed is not True:
            _abort("portfolio_snapshot_publication_confirmation_required")
        if not isinstance(plan_fingerprint, str) or len(plan_fingerprint) != 64:
            _abort("portfolio_snapshot_publication_input_invalid")
        data_space = Path(data_space_path)
        published = _utc(published_at_utc)
        artifact = _artifact(data_space, context_value, as_of_date, published, canonical_path)
        current = _sha({k: v for k, v in artifact.items()
                        if k not in ("completed_at_utc", "artifact_fingerprint")})
        if current != plan_fingerprint:
            _abort("portfolio_snapshot_publication_plan_stale")
        root = Path(artifacts_root) if artifacts_root is not None else data_space / "artifacts"
        # Erst hier anlegen: Der Plan soll keine Spur hinterlassen, und der
        # Publikationsweg verlangt einen bestehenden Bereich mit 0700.
        for directory in (root, root / AREA_ID):
            if directory.is_symlink():
                _abort("portfolio_snapshot_publication_failed")
            if not directory.exists():
                directory.mkdir(mode=0o700, parents=True)
            os.chmod(directory, 0o700)
        from workers.reference.run_publication_v1 import (
            PublicationRuntimeContext, RunPublicationError, publish_completed_run_v1,
        )
        runtime = PublicationRuntimeContext(
            context_value.tenant_id, context_value.user_id, context_value.data_space_id,
            AREA_ID, WRITER_ID, WRITER_ROLE)
        run_id = "run_" + artifact["snapshot_id"][4:]
        # Derselbe Inhalt zweimal zu veroeffentlichen ist kein Fehler, sondern
        # ein Sachverhalt. Ohne diese Auskunft meldete der zweite Klick einen
        # Abbruch, obwohl der Stand laengst festgehalten war - und die Karte
        # sah aus, als waere nichts geschehen.
        existing = root / AREA_ID / "runs" / run_id / "artifact.json"
        if existing.is_file() and not existing.is_symlink():
            return {
                "portfolio_snapshot_publication_version": 1,
                "status": "already_published",
                "snapshot_id": artifact["snapshot_id"],
                "snapshot_status": artifact["snapshot_status"],
                "as_of_date": artifact["as_of_date"],
                "published_at_utc": None,
                "artifact_fingerprint": artifact["artifact_fingerprint"],
                "plan_fingerprint": plan_fingerprint,
                "provider_access": False, "network_access": False, "canonical_write": False,
            }
        try:
            result = publish_completed_run_v1(root / AREA_ID, runtime, run_id, dict(artifact), published)
        except RunPublicationError:
            _abort("portfolio_snapshot_publication_failed")
        return {
            "portfolio_snapshot_publication_version": 1,
            "status": result.status,
            "snapshot_id": artifact["snapshot_id"],
            "snapshot_status": artifact["snapshot_status"],
            "as_of_date": artifact["as_of_date"],
            "published_at_utc": published,
            "artifact_fingerprint": result.artifact_fingerprint,
            "plan_fingerprint": plan_fingerprint,
            "provider_access": False, "network_access": False, "canonical_write": False,
        }
    except PortfolioSnapshotPublicationV1Error:
        raise
    except Exception:
        _abort("portfolio_snapshot_publication_boundary_failed")


# --- Momentaufnahme (rc.313, #478) --------------------------------------------
# Festlegung 24.10.2026: Die Momentaufnahme ist der letzte Schritt von „Alles aktualisieren“ und steht danach in der Analyse.
# Handeln in Data, Lesen in der Analyse: Die Data-App ruft die Kurse ab und veroeffentlicht das Bild; die Analyse liest es nur.
# Dasselbe Bild wie der Stichtags-Snapshot (Fassung 5), mit den zuletzt abgerufenen Kursen, im eigenen Bereich - so steht es
# nie in der Liste der verbindlichen Stichtage. Behalten werden die juengsten INTRADAY_KEEP_RUNS Staende.
INTRADAY_AREA_ID = "intraday_snapshot"
INTRADAY_KEEP_RUNS = 5


def _prune_intraday_runs(area: Path, keep_run: str) -> int:
    """Aeltere Momentaufnahmen entfernen: nur Laufverzeichnisse, nie den geltenden Stand. Gibt zurueck, wie viele weg sind."""
    runs = area / "runs"
    if not runs.is_dir() or runs.is_symlink():
        return 0
    candidates = sorted((entry for entry in runs.iterdir() if entry.is_dir() and not entry.is_symlink()
                         and re.fullmatch(r"run_[a-z0-9_]{4,72}", entry.name)),
                        key=lambda entry: entry.stat().st_mtime, reverse=True)
    removed = 0
    for entry in candidates[INTRADAY_KEEP_RUNS:]:
        if entry.name == keep_run:
            continue
        shutil.rmtree(entry)
        removed += 1
    return removed


def publish_portfolio_intraday_snapshot_v1(
    data_space_path: str | Path,
    context_value: Any,
    as_of_date: str,
    published_at_utc: str,
    artifacts_root: str | Path | None = None,
    canonical_path: str | Path | None = None,
) -> dict[str, Any]:
    """Die Momentaufnahme veroeffentlichen. Ruft nichts ab - die Kurse stammen aus dem letzten Abruf (`snapshot_intraday_v1`).
    Ohne einen einzigen abgerufenen Kurs gibt es nichts zu veroeffentlichen; dann bleibt der letzte Stand stehen."""
    try:
        if not isinstance(context_value, DesktopProductAssetActivityContextV1):
            _abort("portfolio_snapshot_publication_context_invalid")
        from workers.reference.portfolio_intraday_projection_v1 import _IntradayPrices
        data_space = Path(data_space_path)
        published = _utc(published_at_utc)
        source = _IntradayPrices()
        artifact = _artifact(data_space, context_value, as_of_date, published, canonical_path, price_source=source)
        held = {row["asset_id"] for row in artifact["positions"]} | {row["asset_id"] for row in artifact["excluded_positions"]}
        quotes = source.summary(data_space, artifact["as_of_date"], held)
        if not quotes["quote_count"] or quotes["requested_at_utc"] is None:
            return {"portfolio_snapshot_publication_version": 1, "status": "no_quotes", "snapshot_id": None,
                    "as_of_date": artifact["as_of_date"], "quote_count": 0,
                    "provider_access": False, "network_access": False, "canonical_write": False}
        # Der Zeitpunkt des Bildes ist der des Abrufs, nicht der des Veroeffentlichens.
        artifact["completed_at_utc"] = quotes["requested_at_utc"]
        artifact["artifact_fingerprint"] = _sha({k: v for k, v in artifact.items() if k != "artifact_fingerprint"})
        root = Path(artifacts_root) if artifacts_root is not None else data_space / "artifacts"
        for directory in (root, root / INTRADAY_AREA_ID):
            if directory.is_symlink():
                _abort("portfolio_snapshot_publication_failed")
            if not directory.exists():
                directory.mkdir(mode=0o700, parents=True)
            os.chmod(directory, 0o700)
        from workers.reference.run_publication_v1 import (
            PublicationRuntimeContext, RunPublicationError, publish_completed_run_v1,
        )
        runtime = PublicationRuntimeContext(
            context_value.tenant_id, context_value.user_id, context_value.data_space_id,
            INTRADAY_AREA_ID, WRITER_ID, WRITER_ROLE)
        run_id = "run_" + artifact["snapshot_id"][4:]
        existing = root / INTRADAY_AREA_ID / "runs" / run_id / "artifact.json"
        status = "already_published"
        if not (existing.is_file() and not existing.is_symlink()):
            try:
                status = publish_completed_run_v1(root / INTRADAY_AREA_ID, runtime, run_id, dict(artifact), published).status
            except RunPublicationError:
                _abort("portfolio_snapshot_publication_failed")
        pruned = _prune_intraday_runs(root / INTRADAY_AREA_ID, run_id)
        return {
            "portfolio_snapshot_publication_version": 1, "status": status, "snapshot_id": artifact["snapshot_id"],
            "snapshot_status": artifact["snapshot_status"], "as_of_date": artifact["as_of_date"],
            "requested_at_utc": quotes["requested_at_utc"], "quote_count": quotes["held_quote_count"],
            "observed_within_hour_count": quotes["observed_within_hour_count"], "pruned_run_count": pruned,
            "counts": artifact["counts"],
            "provider_access": False, "network_access": False, "canonical_write": False,
        }
    except PortfolioSnapshotPublicationV1Error:
        raise
    except Exception:
        _abort("portfolio_snapshot_publication_boundary_failed")


def _intraday_quotes(view: dict[str, Any]) -> dict[str, Any]:
    """Wie aktuell die Kurse eines veroeffentlichten Bildes sind - aus seinen Positionen gezaehlt, wie beim Abruf."""
    from workers.reference.portfolio_intraday_projection_v1 import RECENT_SECONDS
    requested = view["completed_at_utc"]
    asked = datetime.strptime(requested, "%Y-%m-%dT%H:%M:%SZ")
    rows = list(view["positions"]) + list(view["excluded_positions"])

    def recent(row: dict[str, Any]) -> bool:
        seen = row.get("price_observed_at_utc")
        if row.get("price_basis") != "intraday" or not seen:
            return False
        return (asked - datetime.strptime(seen, "%Y-%m-%dT%H:%M:%SZ")).total_seconds() <= RECENT_SECONDS

    return {
        "requested_at_utc": requested,
        "observed_within_hour_count": sum(recent(row) for row in rows),
        "observed_earlier_count": sum(1 for row in rows if row.get("price_basis") == "intraday" and not recent(row)),
        "last_close_count": sum(1 for row in rows if row.get("price_basis") == "last_close"),
        "unavailable_count": sum(1 for row in rows if row.get("price_basis") == "unavailable"),
    }


def read_latest_portfolio_intraday_snapshot_v1(
    data_space_path: str | Path,
    context_value: Any,
    artifacts_root: str | Path | None = None,
) -> dict[str, Any]:
    """Die zuletzt veroeffentlichte Momentaufnahme, geprueft wie ein Stichtags-Snapshot. Liest nur."""
    try:
        if not isinstance(context_value, DesktopProductAssetActivityContextV1):
            _abort("portfolio_snapshot_publication_context_invalid")
        from apps.reference.latest_run_reader_v1 import LatestRunReaderContext, LatestRunReaderError, read_latest_completed_run_v1
        root = Path(artifacts_root) if artifacts_root is not None else Path(data_space_path) / "artifacts"
        area = root / INTRADAY_AREA_ID
        if not area.is_dir():
            return {"status": "absent", "kind": "intraday"}
        runtime = LatestRunReaderContext(context_value.tenant_id, context_value.user_id, context_value.data_space_id,
                                         INTRADAY_AREA_ID, "desktop_owner")
        try:
            artifact = read_latest_completed_run_v1(area, runtime)
        except LatestRunReaderError as error:
            if getattr(error, "code", "") in {"latest_run_reader_no_latest", "run_publication_no_latest"}:
                return {"status": "absent", "kind": "intraday"}
            _abort("portfolio_snapshot_publication_evidence_invalid")
        view = _published_view(artifact)
        return {**view, "status": "available", "kind": "intraday", "quotes": _intraday_quotes(view)}
    except PortfolioSnapshotPublicationV1Error:
        raise
    except Exception:
        _abort("portfolio_snapshot_publication_boundary_failed")


# --- Veroeffentlichte Staende wieder ansehen ---------------------------------
# Jeder veroeffentlichte Stand bleibt liegen. Bis rc.242 liess sich nur der
# juengste lesen: Wer einen frueheren Stichtag noch einmal veroeffentlichen
# wollte, bekam "bereits veroeffentlicht" - und weiter den anderen Stand gezeigt.
# Von vielen Staenden war nur einer sichtbar.
READABLE_VERSIONS = (3, 4, 5)


def _reader(context_value: Any, data_space_path: str | Path, artifacts_root: str | Path | None):
    if not isinstance(context_value, DesktopProductAssetActivityContextV1):
        _abort("portfolio_snapshot_publication_context_invalid")
    from apps.reference.latest_run_reader_v1 import LatestRunReaderContext
    root = Path(artifacts_root) if artifacts_root is not None else Path(data_space_path) / "artifacts"
    return root / AREA_ID, LatestRunReaderContext(
        context_value.tenant_id, context_value.user_id, context_value.data_space_id, AREA_ID, "desktop_owner")


def _published_view(artifact: dict[str, Any]) -> dict[str, Any]:
    """Die Sicht auf einen veroeffentlichten Stand - dieselbe, die der Anzeigeleser liefert."""
    from apps.desktop_demo.read_latest_artifact_v1 import _validate_demo_schema
    version = artifact.get("portfolio_snapshot_version")
    if version not in READABLE_VERSIONS:
        _abort("portfolio_snapshot_publication_evidence_invalid")
    _validate_demo_schema(artifact, AREA_ID)
    # Ein teilweiser Stand darf sich nicht als vollstaendig ausgeben.
    if artifact["snapshot_status"] == "complete" and not (
            artifact["market_value_complete"] is True and artifact["freshness"]["overall_status"] == "complete"):
        _abort("portfolio_snapshot_publication_evidence_invalid")
    return {
        "view_version": version, "snapshot_id": artifact["snapshot_id"],
        "snapshot_status": artifact["snapshot_status"], "portfolio_label": artifact["portfolio_label"],
        "base_currency": artifact["base_currency"], "as_of_date": artifact["as_of_date"],
        "completed_at_utc": artifact["completed_at_utc"], "freshness": artifact["freshness"],
        "totals": artifact["totals"], "counts": artifact["counts"], "positions": artifact["positions"],
        "excluded_positions": artifact["excluded_positions"],
        "market_value_complete": artifact["market_value_complete"],
        # Vor Fassung 4 trug der Stand kein Cash: Das Feld fehlt dann, statt null zu sein.
        "cash": artifact.get("cash"),
    }


def list_published_portfolio_snapshots_v1(
    data_space_path: str | Path,
    context_value: Any,
    artifacts_root: str | Path | None = None,
) -> dict[str, Any]:
    """Alle veroeffentlichten Stichtags-Snapshots, juengster Stichtag zuerst. Liest nur."""
    try:
        from apps.reference.latest_run_reader_v1 import (
            LatestRunReaderError, list_completed_runs_v1, read_completed_run_v1,
        )
        area, runtime = _reader(context_value, data_space_path, artifacts_root)
        if not area.is_dir():
            return {"portfolio_snapshot_library_version": 1, "status": "absent", "snapshots": [],
                    "unreadable_snapshot_count": 0}
        try:
            listing = list_completed_runs_v1(area, runtime)
        except LatestRunReaderError:
            _abort("portfolio_snapshot_publication_evidence_invalid")
        rows = []
        unreadable = listing["unreadable_run_count"]
        for run in listing["runs"]:
            try:
                view = _published_view(read_completed_run_v1(area, runtime, run["run_id"]))
            except (LatestRunReaderError, PortfolioSnapshotPublicationV1Error):
                # Ein Stand, der die Pruefung nicht besteht, wird nicht angeboten -
                # aber gezaehlt, damit die Luecke nicht wie Leere aussieht.
                unreadable += 1
                continue
            rows.append({"snapshot_id": view["snapshot_id"], "as_of_date": view["as_of_date"],
                         "snapshot_status": view["snapshot_status"], "view_version": view["view_version"],
                         "completed_at_utc": view["completed_at_utc"],
                         "valued_position_count": view["counts"].get("valued_position_count"),
                         "cash_included": view["cash"] is not None, "latest": run["latest"]})
        rows.sort(key=lambda row: (row["as_of_date"], row["completed_at_utc"], row["snapshot_id"]), reverse=True)
        return {"portfolio_snapshot_library_version": 1, "status": "available" if rows else "absent",
                "snapshots": rows, "unreadable_snapshot_count": unreadable}
    except PortfolioSnapshotPublicationV1Error:
        raise
    except Exception:
        _abort("portfolio_snapshot_publication_boundary_failed")


def read_published_portfolio_snapshot_v1(
    data_space_path: str | Path,
    context_value: Any,
    snapshot_id: str,
    artifacts_root: str | Path | None = None,
) -> dict[str, Any]:
    """Ein bestimmter veroeffentlichter Stand, geprueft wie der juengste. Liest nur."""
    try:
        from apps.reference.latest_run_reader_v1 import LatestRunReaderError, read_completed_run_v1
        if not isinstance(snapshot_id, str) or re.fullmatch(r"psn_[a-z0-9_]{4,72}", snapshot_id) is None:
            _abort("portfolio_snapshot_publication_input_invalid")
        area, runtime = _reader(context_value, data_space_path, artifacts_root)
        try:
            artifact = read_completed_run_v1(area, runtime, "run_" + snapshot_id[4:])
        except LatestRunReaderError:
            _abort("portfolio_snapshot_publication_evidence_invalid")
        view = _published_view(artifact)
        if view["snapshot_id"] != snapshot_id:
            _abort("portfolio_snapshot_publication_evidence_invalid")
        return view
    except PortfolioSnapshotPublicationV1Error:
        raise
    except Exception:
        _abort("portfolio_snapshot_publication_boundary_failed")


__all__ = [
    "INTRADAY_AREA_ID",
    "list_published_portfolio_snapshots_v1",
    "publish_portfolio_intraday_snapshot_v1",
    "read_latest_portfolio_intraday_snapshot_v1",
    "read_published_portfolio_snapshot_v1",
    "PortfolioSnapshotPublicationV1Error",
    "apply_portfolio_snapshot_publication_v1",
    "plan_portfolio_snapshot_publication_v1",
    "portfolio_snapshot_publication_v1_error_codes",
]
