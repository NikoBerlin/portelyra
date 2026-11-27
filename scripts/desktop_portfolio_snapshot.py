#!/usr/bin/env python3
"""JSON-stdin boundary for the published portfolio snapshot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from migrations.reference.desktop_product_asset_activity_v1 import (  # noqa: E402
    DesktopProductAssetActivityContextV1,
)
from workers.reference.portfolio_snapshot_freshness_v1 import (  # noqa: E402
    PortfolioSnapshotFreshnessV1Error,
    read_portfolio_snapshot_freshness_v1,
)
from workers.reference.portfolio_history_v1 import (  # noqa: E402
    PortfolioHistoryV1Error,
    read_portfolio_history_v1,
    update_portfolio_history_v1,
)
from workers.reference.data_stands_v1 import DataStandsV1Error, read_data_stands_v1, read_recent_source_gaps_v1  # noqa: E402
from workers.reference.portfolio_history_publication_v1 import (  # noqa: E402
    PortfolioHistoryPublicationV1Error, publish_portfolio_history_v1,
)
from workers.reference.data_basis_publication_v1 import DataBasisPublicationV1Error, publish_data_basis_names_v1, publish_data_basis_v1  # noqa: E402
from workers.reference.portfolio_snapshot_publication_v1 import (
    publish_portfolio_intraday_snapshot_v1, read_latest_portfolio_intraday_snapshot_v1,  # noqa: E402
    PortfolioSnapshotPublicationV1Error,
    apply_portfolio_snapshot_publication_v1,
    list_published_portfolio_snapshots_v1,
    plan_portfolio_snapshot_publication_v1,
    read_published_portfolio_snapshot_v1,
)


class _CliInputError(ValueError):
    pass


def _emit(value: object) -> None:
    sys.stdout.write(json.dumps(value, ensure_ascii=False, allow_nan=False,
                                sort_keys=True, separators=(",", ":")))


def _payload(command: str) -> dict:
    raw = sys.stdin.buffer.read(200_000)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise _CliInputError("request is not strict JSON") from error
    fields = {
        "freshness": {"context", "data_space_path", "as_of_date"},
        "plan": {"context", "data_space_path", "as_of_date", "planned_at_utc"},
        "publish": {"context", "data_space_path", "as_of_date", "plan_fingerprint",
                    "confirmed", "published_at_utc"},
        "list": {"context", "data_space_path"},
        "show": {"context", "data_space_path", "snapshot_id"},
        # Tageshistorie (#473): fortschreiben (rebuild = von vorn rechnen, geschrieben wird nur Geaendertes) und lesen.
        # through_date (#567): bis zu diesem Tag reicht die Reihe ohne Kursabruf (Umfang ohne „Marktdaten“); null = keiner genannt.
        "history-update": {"context", "data_space_path", "requested_at_utc", "rebuild", "through_date"},
        "history-read": {"context", "data_space_path", "start", "end"},
        # Staende je Datenart (#463): bis wann Buchungen, Rewards, Cash und Kurse reichen.
        "stands": {"context", "data_space_path", "as_of_date"},
        # Quellluecken gehaltener Assets im Zeitraum (#477), fuer den optionalen Nachabruf.
        "recent-gaps": {"context", "data_space_path", "start", "end"},
        # Die Tageshistorie fuer die Analyse veroeffentlichen (#473), nur wenn sie sich geaendert hat.
        "history-publish": {"context", "data_space_path", "published_at_utc"},
        # Momentaufnahme (rc.313): nach dem Kursabruf veroeffentlichen (Data) und den juengsten Stand lesen (Analyse).
        "intraday-publish": {"context", "data_space_path", "as_of_date", "published_at_utc"},
        "intraday-read": {"context", "data_space_path"},
        # Datenbasis (rc.314, #478): zum Schluss von "Alles aktualisieren" veroeffentlichen; mit den Eingaben des Run Centers.
        "basis-publish": {"context", "data_space_path", "as_of_date", "published_at_utc", "run_center"},
        # Nach Stammdatenpflege (rc.332, #422): neu veroeffentlichen nur, wenn Steuer und Analyse nichts Neues rechnen muessen.
        "basis-publish-names": {"context", "data_space_path", "published_at_utc"},
    }[command]
    if not isinstance(value, dict) or set(value) != fields:
        raise _CliInputError("request fields invalid")
    return value


def _context(value: object) -> DesktopProductAssetActivityContextV1:
    fields = {"tenant_id", "user_id", "data_space_id"}
    if not isinstance(value, dict) or set(value) != fields:
        raise _CliInputError("context fields invalid")
    return DesktopProductAssetActivityContextV1(
        value["tenant_id"], value["user_id"], value["data_space_id"], "desktop_owner")


def main() -> int:
    parser = argparse.ArgumentParser(description="Portelyra portfolio snapshot v3")
    parser.add_argument("command", choices=("freshness", "plan", "publish", "list", "show", "history-update", "history-read", "stands", "recent-gaps", "history-publish", "intraday-publish", "intraday-read", "basis-publish", "basis-publish-names"))
    arguments = parser.parse_args()
    try:
        payload = _payload(arguments.command)
        context = _context(payload["context"])
        space = payload["data_space_path"]
        if arguments.command == "freshness":
            _emit(read_portfolio_snapshot_freshness_v1(space, context, payload["as_of_date"]))
        elif arguments.command == "plan":
            _emit(plan_portfolio_snapshot_publication_v1(
                space, context, payload["as_of_date"], payload["planned_at_utc"]))
        elif arguments.command == "list":
            _emit(list_published_portfolio_snapshots_v1(space, context))
        elif arguments.command == "show":
            _emit(read_published_portfolio_snapshot_v1(space, context, payload["snapshot_id"]))
        elif arguments.command == "history-update":
            if not isinstance(payload["rebuild"], bool):
                raise _CliInputError("rebuild must be boolean")
            _emit(update_portfolio_history_v1(space, context, None, payload["requested_at_utc"], rebuild=payload["rebuild"],
                                              through_date=payload["through_date"]))
        elif arguments.command == "history-read":
            # Nur Tagessummen und der letzte Lauf: Positionen tragen Kennungen des Bestands und bleiben im Rechenkern.
            value = read_portfolio_history_v1(space, context, payload["start"] or None, payload["end"] or None)
            _emit({"status": value["status"], "days": value["days"], "last_run": value["last_run"]})
        elif arguments.command == "stands":
            _emit({"status": "available", **read_data_stands_v1(space, context, payload["as_of_date"])})
        elif arguments.command == "history-publish":
            _emit(publish_portfolio_history_v1(space, context, payload["published_at_utc"]))
        elif arguments.command == "intraday-publish":
            _emit(publish_portfolio_intraday_snapshot_v1(space, context, payload["as_of_date"], payload["published_at_utc"]))
        elif arguments.command == "intraday-read":
            _emit(read_latest_portfolio_intraday_snapshot_v1(space, context))
        elif arguments.command == "basis-publish":
            _emit(publish_data_basis_v1(space, context, payload["as_of_date"], payload["published_at_utc"], payload["run_center"]))
        elif arguments.command == "basis-publish-names":
            _emit(publish_data_basis_names_v1(space, context, payload["published_at_utc"]))
        elif arguments.command == "recent-gaps":
            _emit(read_recent_source_gaps_v1(space, context, payload["start"], payload["end"]))
        else:
            _emit(apply_portfolio_snapshot_publication_v1(
                space, context, payload["as_of_date"], payload["plan_fingerprint"],
                payload["confirmed"] is True, payload["published_at_utc"]))
    except (PortfolioSnapshotPublicationV1Error, PortfolioSnapshotFreshnessV1Error, PortfolioHistoryV1Error, DataStandsV1Error,
            PortfolioHistoryPublicationV1Error, DataBasisPublicationV1Error,
            _CliInputError, KeyError, TypeError) as error:
        _emit({"status": "blocked",
               "code": getattr(error, "code", "portfolio_snapshot_publication_input_invalid")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
