#!/usr/bin/env python3
"""CLI-Grenze fuer die Verwaltung der Leser (rc.380, #486): JSON ueber stdin, eine JSON-Zeile auf stdout.

overview: je Leser Version, Pruefsumme, ob er in diesem Portfolio an Ihren Belegen geprueft ist, und die Buchungen mit seiner Herkunft;
          je Art die Buchungen ohne Herkunft; verworfene Plugins. Nur Zaehlwerte. Schreibt hoechstens den einmaligen Eintrag
          "Bestand bis rc.379" (Festlegung vom 09.11.2026).
selftest: Selbsttest aller Leser mit dem echten Datum (auch wenn der Bezugstag der Vertragstests gesetzt ist). Bericht je Plugin und
          Leser mit Zaehlwerten und Befund-Codes, nie Belegnamen oder Inhalte. Beruehrt den Datenraum nicht.
rc.381 (Festlegungen vom 09.11.2026): activation, activation-preview, activation-apply (je Plugin und Portfolio), install-preview,
          install-apply (ZIP, nur nach bestandenem Selbsttest), remove-preview, remove-apply (nur installierte Plugins), offered (was die
          Import-Karten anbieten). Jeder Schreibschritt ist an genau seine Vorschau gebunden (preview_fingerprint).
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import asset_activity_reference_v1 as references  # noqa: E402
from migrations.reference import statement_reader_admin_v1 as admin  # noqa: E402
from migrations.reference import statement_reader_checks_v1 as checks  # noqa: E402
from migrations.reference import statement_reader_plugins_v1 as reader_plugins  # noqa: E402
from migrations.reference import statement_reader_selftest_v1 as selftest  # noqa: E402
from migrations.reference.desktop_product_asset_activity_v1 import DesktopProductAssetActivityContextV1  # noqa: E402

CONTEXT_KEYS = {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}
# Mit 17 Plugins und 35 Lesern rund 80 Sekunden. Der Startwert ist der Tag - am selben
# Tag wiederholbar, an jedem Tag andere veraenderte und erfundene Belege.
PARAMETERS = {"mutations_per_fixture": 500, "generated_per_reader": 250, "mutations_per_generated": 20}
STAGES = ("fixtures", "order", "mutations", "generated")
_CODE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")


class StatementReadersCliError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _expect(value, optional=()):
    if not isinstance(value, dict) or not {"context", "data_space_path"} <= set(value) <= {"context", "data_space_path", *optional}:
        raise StatementReadersCliError("statement_reader_admin_input_invalid")
    context = value["context"]
    if not isinstance(context, dict) or set(context) != CONTEXT_KEYS or not all(isinstance(context[key], str) for key in CONTEXT_KEYS) \
            or not isinstance(value["data_space_path"], str) or not value["data_space_path"]:
        raise StatementReadersCliError("statement_reader_admin_input_invalid")
    return Path(value["data_space_path"]), DesktopProductAssetActivityContextV1(**context)


def _code(value) -> str | None:
    return value if isinstance(value, str) and _CODE.fullmatch(value) else (None if value is None else "statement_reader_code_invalid")


def _overview(space: Path, context) -> dict:
    if not (space / "canonical.sqlite").is_file():
        raise StatementReadersCliError("statement_reader_admin_store_invalid")
    try:
        result = checks.reader_overview_v1(space, context)
    except references.AssetActivityReferenceV1Error:
        raise StatementReadersCliError("statement_reader_check_store_invalid") from None
    return {"contract_version": "statement_reader_overview_v1", **result, "canonical_write": False}


def _reader_summary(entry: dict, label: str | None) -> dict:
    """Je Leser die Zaehlwerte und die Befunde je Stufe, Befund und Code gezaehlt - ohne Belegnamen, Startwerte oder Inhalte."""
    findings: Counter = Counter()
    failures = {"fixtures": entry["fixtures"]["failures"], "order": entry["order"]["failures"], "mutations": entry["mutations"]["failures"],
                "generated": (entry["generated"] or {}).get("failures", [])}
    for stage in STAGES:
        for item in failures[stage]:
            findings[(stage, str(item.get("finding")), _code(item.get("code")))] += 1
    return {"reader_id": entry["reader_id"], "domain": entry["domain"], "label": label,
            "fixtures": entry["fixtures"]["count"], "mutations": entry["mutations"]["count"],
            "generated": None if entry["generated"] is None else entry["generated"]["count"],
            "implausible_today": entry["fixtures"].get("implausible_today", 0),
            "mutations_implausible": entry["mutations"]["rejected_by_core"],
            "findings": [{"stage": stage, "finding": finding, "code": code, "count": count}
                         for (stage, finding, code), count in sorted(findings.items(), key=lambda item: (STAGES.index(item[0][0]), item[0][1], item[0][2] or ""))]}


def _selftest(plugin_ids) -> dict:
    # Mit dem echten Datum (Festlegung 09.11.2026): Der Bezugstag der Vertragstests gilt hier nicht, auch wenn die App ihn erbt.
    os.environ.pop(reader_plugins.REFERENCE_DATE_ENV, None)
    known = sorted({spec.plugin_id for spec in reader_plugins.reader_specs_v1()} | {item["plugin_id"] for item in reader_plugins.reader_plugin_problems_v1()})
    if plugin_ids is not None and (not isinstance(plugin_ids, list) or not plugin_ids or not all(item in known for item in plugin_ids)):
        raise StatementReadersCliError("statement_reader_admin_input_invalid")
    today = date.today()
    seed = int(today.strftime("%Y%m%d"))
    started, clock = _utc(), time.monotonic()
    if plugin_ids is None:
        report = selftest.selftest_all_v1(seed=seed, **PARAMETERS)
    else:
        plugins = [selftest.selftest_plugin_v1(plugin_id, seed=seed, **PARAMETERS) for plugin_id in sorted(set(plugin_ids))]
        report = {"selftest_version": selftest.VERSION, "seed": seed, "plugins": plugins, "passed": all(item["passed"] for item in plugins)}
    duration = round(time.monotonic() - clock, 1)
    specs = {(spec.domain, spec.reader_id): spec for spec in reader_plugins.reader_specs_v1()}
    institutions = {spec.plugin_id: spec.institution for spec in specs.values()}
    plugins = []
    for plugin in report["plugins"]:
        readers = [_reader_summary(entry, getattr(specs.get((entry["domain"], entry["reader_id"])), "label", None)) for entry in plugin.get("readers", [])]
        plugins.append({"plugin_id": plugin["plugin_id"], "institution": institutions.get(plugin["plugin_id"]),
                        "plugin_version": plugin.get("plugin_version"), "passed": bool(plugin["passed"]),
                        "problems": [_code(code) for code in plugin.get("problems", [])], "readers": readers})
    return {"contract_version": "statement_reader_selftest_report_v1", "selftest_version": report["selftest_version"], "seed": seed,
            "reference_date": today.isoformat(), "parameters": dict(PARAMETERS), "started_at_utc": started, "finished_at_utc": _utc(),
            "duration_seconds": duration, "passed": bool(report["passed"]), "plugins": plugins, "canonical_write": False}


def _zip(value) -> tuple[bytes, str]:
    """Die hochgeladene ZIP (Pfad der Shiny-Upload-Datei) und ihr Name; nur lesen, nie veraendern."""
    path, name = Path(str(value.get("zip_path") or "")), value.get("file_name")
    if not path.is_file() or path.is_symlink() or not isinstance(name, str) or path.stat().st_size > admin.MAX_ZIP_BYTES:
        raise StatementReadersCliError("statement_reader_install_too_large" if path.is_file() and path.stat().st_size > admin.MAX_ZIP_BYTES
                                       else "statement_reader_install_zip_invalid")
    return path.read_bytes(), name


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if isinstance(value, dict) and isinstance(value.get("data_space_path"), str):
            reader_plugins.use_data_space_plugins_v1(value["data_space_path"])   # installierte Plugins dieses Datenraums (rc.381)
        if command == "overview":
            space, context = _expect(value)
            result = _overview(space, context)
        elif command == "selftest":
            _expect(value, ("plugin_ids",))
            result = _selftest(value.get("plugin_ids"))
        elif command == "activation":
            space, context = _expect(value)
            result = admin.activation_v1(space, context)
        elif command == "offered":
            space, context = _expect(value)
            result = admin.offered_readers_v1(space, context)
        elif command == "activation-preview":
            space, context = _expect(value, ("changes",))
            result = admin.preview_activation_v1(space, context, value.get("changes"))
        elif command == "activation-apply":
            space, context = _expect(value, ("changes", "preview_fingerprint", "confirmed", "recorded_at_utc"))
            result = admin.apply_activation_v1(space, context, value.get("changes"), value.get("preview_fingerprint"), value.get("confirmed"),
                                               value.get("recorded_at_utc"))
        elif command == "install-preview":
            space, context = _expect(value, ("zip_path", "file_name"))
            data, name = _zip(value)
            result = admin.preview_plugin_install_v1(space, context, data, name)
        elif command == "install-apply":
            space, context = _expect(value, ("zip_path", "file_name", "preview_fingerprint", "confirmed", "recorded_at_utc"))
            data, name = _zip(value)
            result = admin.apply_plugin_install_v1(space, context, data, name, value.get("preview_fingerprint"), value.get("confirmed"),
                                                   value.get("recorded_at_utc"))
        elif command == "remove-preview":
            space, context = _expect(value, ("plugin_id",))
            result = admin.preview_plugin_remove_v1(space, context, value.get("plugin_id"))
        elif command == "remove-apply":
            space, context = _expect(value, ("plugin_id", "preview_fingerprint", "confirmed", "recorded_at_utc"))
            result = admin.apply_plugin_remove_v1(space, context, value.get("plugin_id"), value.get("preview_fingerprint"), value.get("confirmed"),
                                                  value.get("recorded_at_utc"))
        elif command == "revert-preview":
            # Zur vorigen Fassung (#486 Schritt 3): Update zuruecknehmen, die Aktivierung bleibt.
            space, context = _expect(value, ("plugin_id",))
            result = admin.preview_plugin_revert_v1(space, context, value.get("plugin_id"))
        elif command == "revert-apply":
            space, context = _expect(value, ("plugin_id", "preview_fingerprint", "confirmed", "recorded_at_utc"))
            result = admin.apply_plugin_revert_v1(space, context, value.get("plugin_id"), value.get("preview_fingerprint"), value.get("confirmed"),
                                                  value.get("recorded_at_utc"))
        else:
            raise StatementReadersCliError("statement_reader_admin_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    # Fehler der Fachmodule (RuntimeError mit Code) melden ihren Code nur, wenn er zu den Lesern gehoert; sonst "nicht lesbar".
    except (RuntimeError, OSError, KeyError, TypeError, ValueError, sqlite3.Error) as error:
        code = getattr(error, "code", "statement_reader_admin_input_invalid" if isinstance(error, json.JSONDecodeError) else "statement_reader_admin_store_invalid")
        print(json.dumps({"status": "blocked", "code": code if isinstance(code, str) and code.startswith(("statement_reader_", "plugin_signature_")) else "statement_reader_admin_store_invalid"},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
