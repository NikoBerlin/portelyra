#!/usr/bin/env python3
"""Read one verified latest artifact without Worker or write capability."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from apps.reference.latest_run_reader_v1 import (  # noqa: E402
    LatestRunReaderContext,
    LatestRunReaderError,
    read_latest_completed_run_v1,
)
from migrations.reference.legacy_import_data_command_v1 import canonical_json_bytes  # noqa: E402


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise LatestRunReaderError("run_publication_boundary_failed")


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(add_help=False)
    parser.add_argument("--area-root", required=True)
    parser.add_argument("--area-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--data-space-id", required=True)
    parser.add_argument("--role", required=True)
    return parser


_SCHEMAS = {
    ("group_projection", 1): (
        ROOT / "contracts" / "cockpit-group-drilldown" / "v1" / "completed-artifact.schema.json",
        "44ada3d723de85893877d943bf4395cdbed6a0634db71065d349d2923a91150c",
    ),
    ("analysis_snapshot", 1): (
        ROOT / "contracts" / "analysis-snapshot" / "v1" / "snapshot.schema.json",
        "846b648ae8d1e7b64e2d53b350eb5ae4c17a63d12a2c72f0ea724a0b3de6bc3c",
    ),
    ("market_analysis", 1): (
        ROOT / "contracts" / "market-analysis" / "v1" / "market-analysis-artifact.schema.json",
        "b9f01ddba3289c1f55d7ec154683d1f5a3d069eac26570b561a6322159249d83",
    ),
    ("portfolio_snapshot", 101): (
        ROOT / "contracts" / "portfolio-snapshot" / "v1.1" / "snapshot.schema.json",
        "8afe91c477bd37f7dcd49878569a649585b30efd884bf1fafbd643813c4a917b",
    ),
    ("portfolio_snapshot", 2): (
        ROOT / "contracts" / "portfolio-snapshot" / "v2" / "snapshot.schema.json",
        "2af1a726f6a41d884258baea486583908664de755c114a0d285b80fa7f02452f",
    ),
    ("portfolio_snapshot", 3): (
        ROOT / "contracts" / "portfolio-snapshot" / "v3" / "snapshot.schema.json",
        "d8536b199250c2bbd8ffb217d2b7350a434e1c49fad8a1f72957b8e313b9fa2d",
    ),
    ("portfolio_snapshot", 4): (
        ROOT / "contracts" / "portfolio-snapshot" / "v4" / "snapshot.schema.json",
        "8c0419fce426d4c0f28898f9647213933c2b2d9bae13f4c87fc046fc7e4b9be3",
    ),
    ("portfolio_snapshot", 5): (
        ROOT / "contracts" / "portfolio-snapshot" / "v5" / "snapshot.schema.json",
        "3b2dada4af8a257260dd768a90cf0703d34d101be965ca8f0bd799468d54fd14",
    ),
    ("trade_analysis", 1): (
        ROOT / "contracts" / "trade-analysis" / "v1" / "trade-analysis-artifact.schema.json",
        "4f905e013d7b2142558d0eb9fec83185d8a29edcb78c3f947aef045cc5376fda",
    ),
    ("tax_report", 101): (
        ROOT / "contracts" / "tax-report" / "v1.1" / "report.schema.json",
        "8016c6c8673af76688097c2197fe4681c25970500fb302a51283347b39918f66",
    ),
    ("tax_report", 2): (
        ROOT / "contracts" / "tax-report" / "v2" / "report.schema.json",
        "6b4dcfca8ffdd93f17f5505c7fc82fe4e30d155c278fb2a1071825a9fe588256",
    ),
    ("desktop_workflow", 1): (
        ROOT / "contracts" / "desktop-workflow" / "v1" / "artifact.schema.json",
        "5fb18eabd8d0580945de67cbbbf90fd33bd538e6d9244cce2fc1b0455b55e371",
    ),
    ("display_settings", 1): (
        ROOT / "contracts" / "display-settings" / "v1" / "artifact.schema.json",
        "9ec55fc68165bfe02a5ebc4af4a2599dc2f4d0af527ae5d4732043700387bfca",
    ),
    ("data_basis", 1): (
        ROOT / "contracts" / "data-basis" / "v1" / "artifact.schema.json",
        "5027301103348ab65b02ddf220af6d2d12480b1a311da4293969b0e506e53789",
    ),
    ("portfolio_history", 1): (
        ROOT / "contracts" / "portfolio-history-publication" / "v1" / "artifact.schema.json",
        "22a150706b6f184265d1d162e034da69f998b64cd948d801844cadb2bff383e0",
    ),
}


def _validate_demo_schema(artifact: dict[str, object], area_id: str) -> None:
    version_field = {
        "group_projection": "cockpit_group_artifact_version",
        "analysis_snapshot": "analysis_snapshot_version",
        "portfolio_snapshot": "portfolio_snapshot_version",
        "market_analysis": "market_analysis_artifact_version",
        "tax_report": "tax_report_version",
        "trade_analysis": "trade_analysis_artifact_version",
        "desktop_workflow": "desktop_workflow_artifact_version",
        "portfolio_history": "portfolio_history_version",
        "display_settings": "display_settings_version",
        "data_basis": "data_basis_version",
    }.get(area_id)
    key = (area_id, artifact.get(version_field)) if version_field is not None else None
    if key not in _SCHEMAS:
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    path, expected = _SCHEMAS[key]
    if path.is_symlink():
        raise LatestRunReaderError("run_publication_reader_integrity_invalid")
    try:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise LatestRunReaderError("run_publication_reader_integrity_invalid")
        schema = json.loads(raw.decode("utf-8", errors="strict"))
        jsonschema.Draft202012Validator(schema).validate(artifact)
        if area_id == "desktop_workflow" and "asset_selection_snapshot" in artifact["browser_model"]:
            selection_path = ROOT / "contracts" / "completed-asset-selection-snapshot" / "v1" / "snapshot.schema.json"
            if selection_path.is_symlink():
                raise LatestRunReaderError("run_publication_reader_integrity_invalid")
            selection_raw = selection_path.read_bytes()
            if hashlib.sha256(selection_raw).hexdigest() != "40c20b6119192a2a24fd6b7afe5616b8ea54f84ffa97b9bccdd8409fe9b15157":
                raise LatestRunReaderError("run_publication_reader_integrity_invalid")
            selection = artifact["browser_model"]["asset_selection_snapshot"]
            jsonschema.Draft202012Validator(json.loads(selection_raw)).validate(selection)
            if selection["status"] == "complete":
                body = {key: value for key, value in selection.items() if key != "revision_fingerprint"}
                if hashlib.sha256(canonical_json_bytes(body)).hexdigest() != selection["revision_fingerprint"]:
                    raise LatestRunReaderError("run_publication_reader_integrity_invalid")
        if area_id == "desktop_workflow" and "exact_market_snapshot" in artifact["browser_model"]:
            exact_path = ROOT / "contracts" / "desktop-completed-market-snapshot" / "v1" / "snapshot.schema.json"
            if exact_path.is_symlink():
                raise LatestRunReaderError("run_publication_reader_integrity_invalid")
            exact_raw = exact_path.read_bytes()
            if hashlib.sha256(exact_raw).hexdigest() != "72355994c65842dfc67dc216dd5bb01353f5d266fc0a747d1fae98ce4d0cc592":
                raise LatestRunReaderError("run_publication_reader_integrity_invalid")
            jsonschema.Draft202012Validator(json.loads(exact_raw)).validate(artifact["browser_model"]["exact_market_snapshot"])
    except LatestRunReaderError:
        raise
    except Exception:
        raise LatestRunReaderError("run_publication_reader_integrity_invalid") from None


def main(arguments: list[str] | None = None) -> int:
    try:
        values = _parser().parse_args(arguments)
        artifact = read_latest_completed_run_v1(
            Path(values.area_root),
            LatestRunReaderContext(
                values.tenant_id,
                values.user_id,
                values.data_space_id,
                values.area_id,
                values.role,
            ),
        )
        _validate_demo_schema(artifact, values.area_id)
        sys.stdout.buffer.write(canonical_json_bytes(artifact) + b"\n")
        return 0
    except LatestRunReaderError as error:
        print(json.dumps({"status": "error", "code": error.code}, sort_keys=True, separators=(",", ":")))
        return 2
    except BaseException:
        print(json.dumps({"status": "error", "code": "run_publication_boundary_failed"}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
