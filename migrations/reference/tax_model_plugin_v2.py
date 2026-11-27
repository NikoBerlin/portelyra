#!/usr/bin/env python3
"""Additive German Tax Model v2 runner over the immutable v1 sandbox contract."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from migrations.reference import tax_model_plugin_v1 as base

PLUGIN_ID = "tax_de_personal_income_tax_projection_v2"


class TaxPluginV2Blocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class TaxPluginV2Manifest:
    plugin_id: str
    plugin_version: str
    rules_fingerprint: str
    model_fingerprint: str
    base_manifest: base.TaxPluginManifest


@dataclass(frozen=True)
class TaxPluginV2RunResult:
    run_ref: str
    plugin_id: str
    plugin_version: str
    rules_fingerprint: str
    model_fingerprint: str
    parameter_fingerprint: str
    projection_mode: str
    input_fingerprint: str
    output_fingerprint: str
    rows: tuple[dict[str, Any], ...]
    reconciliation: dict[str, Any]
    disclaimer_codes: tuple[str, ...]


def _abort(code: str) -> None:
    raise TaxPluginV2Blocked(code)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = _canonical(value).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def tax_plugin_manifest_v2(plugin_root: str | Path | None = None) -> TaxPluginV2Manifest:
    """Das gepruefte Manifest der Fassung 2. `plugin_root`: der Ordner, in dem die gewaehlte Fassung liegt (tax_module_catalog_v1, #486
    Schritt 2); ohne Angabe die mitgelieferte."""
    try:
        manifest = base.tax_plugin_manifest_v1(PLUGIN_ID, None if plugin_root is None else Path(plugin_root))
    except base.TaxPluginBlocked as error:
        raise TaxPluginV2Blocked(error.code) from error
    model_fingerprint = _sha({
        "plugin_id": manifest.plugin_id,
        "plugin_version": manifest.plugin_version,
        "rules_fingerprint": manifest.rules_fingerprint,
        "resources": dict(sorted(manifest.resource_fingerprints)),
    })
    return TaxPluginV2Manifest(
        manifest.plugin_id, manifest.plugin_version, manifest.rules_fingerprint,
        model_fingerprint, manifest,
    )


# Die Werte, die das Modul im Jahresmodus je Institut liest.
INSTITUTION_PARAMETER_CODES = frozenset({
    "capital_income_allowance", "creditable_foreign_withholding_tax",
    "opening_equity_loss_carryforward", "opening_general_capital_loss_carryforward",
})


def _parameter_fingerprint(parameters: Any) -> str:
    if not isinstance(parameters, list):
        _abort("tax_plugin_input_invalid")
    normalized = []
    for parameter in parameters:
        if (
            not isinstance(parameter, Mapping)
            or not isinstance(parameter.get("tax_year"), int)
            or isinstance(parameter.get("tax_year"), bool)
            or not isinstance(parameter.get("parameter_code"), str)
        ):
            _abort("tax_plugin_input_invalid")
        values = {
            key: parameter.get(key)
            for key in ("rate_decimal", "amount_decimal", "applicability_value")
            if parameter.get(key) is not None
        }
        if len(values) != 1:
            _abort("tax_plugin_input_invalid")
        # Ein Wert je Institut (Freistellungsauftrag, Verlusttoepfe, Quellensteuer) traegt dessen Schluessel; er gehoert
        # in den Abdruck, sonst saehen zwei Aufteilungen derselben Betraege gleich aus.
        keyed = {}
        if parameter.get("institution_key") is not None:
            if parameter["parameter_code"] not in INSTITUTION_PARAMETER_CODES or not isinstance(parameter["institution_key"], str):
                _abort("tax_plugin_input_invalid")
            keyed = {"institution_key": parameter["institution_key"]}
        normalized.append({
            "tax_year": parameter["tax_year"],
            "parameter_code": parameter["parameter_code"],
            **keyed,
            **values,
        })
    normalized.sort(key=lambda row: (row["tax_year"], row["parameter_code"], row.get("institution_key", "")))
    return _sha(normalized)


def run_tax_model_plugin_v2(
    *, bound_input: dict[str, Any], context: Any,
    selection: base.TaxPluginSelection, timeout_seconds: int = 30,
    plugin_root: str | Path | None = None,
) -> TaxPluginV2RunResult:
    manifest = tax_plugin_manifest_v2(plugin_root)
    base.normalize_context(context)
    selected = manifest.base_manifest
    if (
        not isinstance(selection, base.TaxPluginSelection)
        or selection.status != "active"
        or (
            selection.plugin_id, selection.plugin_version,
            selection.rules_fingerprint, selection.manifest_fingerprint,
        ) != (
            selected.plugin_id, selected.plugin_version,
            selected.rules_fingerprint, selected.manifest_fingerprint,
        )
    ):
        _abort("tax_plugin_selection_mismatch")
    expected = {
        "api_version", "run_ref", "projection_mode", "portfolio_ref",
        "source_artifact_ref", "cutoff", "rows", "classifications",
        "parameters", "prior_state", "input_fingerprint",
    }
    if isinstance(bound_input, dict) and (
        "semantic_source_bindings" in bound_input
        or "semantic_binding_fingerprint" in bound_input
    ):
        expected |= {"semantic_source_bindings", "semantic_binding_fingerprint"}
    if not isinstance(bound_input, dict) or set(bound_input) != expected:
        _abort("tax_plugin_input_invalid")
    try:
        base._validate_json_values(bound_input)
    except base.TaxPluginBlocked as error:
        raise TaxPluginV2Blocked(error.code) from error
    rebuilt = dict(bound_input)
    input_fingerprint = rebuilt.pop("input_fingerprint")
    if (
        base.sha(rebuilt) != input_fingerprint
        or bound_input["projection_mode"] not in selected.supported_projection_modes
    ):
        _abort("tax_plugin_mode_unsupported")
    if (
        bound_input["portfolio_ref"] != selection.portfolio_ref
        or bound_input["projection_mode"] != selection.projection_mode
    ):
        _abort("tax_plugin_selection_mismatch")
    if not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 300:
        _abort("tax_plugin_input_invalid")
    parameter_fingerprint = _parameter_fingerprint(bound_input["parameters"])
    staging = Path(tempfile.mkdtemp(prefix=".portelyra-tax-plugin-v2-"))
    os.chmod(staging, 0o700)
    source = staging / "bound-input.json"
    output = staging / "output"
    temporary = staging / "tmp"
    output.mkdir(mode=0o700)
    temporary.mkdir(mode=0o700)
    source.write_text(base.canonical(bound_input) + "\n", encoding="utf-8")
    os.chmod(source, 0o400)
    environment = {
        "PATH": os.environ.get("PATH", ""), "HOME": str(temporary),
        "TMPDIR": str(temporary), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
        "R_LIBS_SITE": "/usr/local/lib/R/site-library:/usr/lib/R/site-library",
        "R_ENVIRON_USER": str(temporary / "disabled-Renviron"),
        "R_PROFILE_USER": str(temporary / "disabled-Rprofile"),
        "PORTELYRA_TAX_PLUGIN_ID": selected.plugin_id,
        "PORTELYRA_TAX_PLUGIN_VERSION": selected.plugin_version,
        "PORTELYRA_TAX_PLUGIN_RULES_FINGERPRINT": selected.rules_fingerprint,
        "PORTELYRA_TAX_PLUGIN_MODEL_FINGERPRINT": manifest.model_fingerprint,
        "PORTELYRA_TAX_PLUGIN_PARAMETER_FINGERPRINT": parameter_fingerprint,
    }
    rscript = shutil.which("Rscript", path=environment["PATH"])
    try:
        if not rscript or not base.SANDBOX.is_file():
            _abort("tax_plugin_isolation_unavailable")
        try:
            library = base._jsonlite_library(rscript, environment, staging)
        except base.TaxPluginBlocked as error:
            raise TaxPluginV2Blocked(error.code) from error
        environment["R_LIBS_USER"] = str(library)
        command = [
            # -B: Der Sandkasten importiert sein Basismodul, und Python legt dafuer ohne
            # diesen Schalter eine .pyc neben der Quelle ab. Im installierten Abbild ist das
            # fatal: Der Dateibestand weicht dann von seiner Registry ab, das Abbild gilt als
            # ungueltig, und jedes weitere upgrade wird abgewiesen. Ein einziger Steuerlauf
            # genuegte dafuer (#368, 28.09.2026).
            sys.executable, "-B", str(base.SANDBOX), "--rscript", rscript,
            "--r-library", str(library), "--entry", str(selected.entry_path),
            "--source", str(source), "--output", str(output),
            "--temporary", str(temporary), "--timeout-seconds", str(timeout_seconds),
        ]
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, env=environment, start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as error:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise TaxPluginV2Blocked("tax_plugin_timeout") from error
        if process.returncode == 78:
            _abort("tax_plugin_isolation_unavailable")
        if process.returncode != 0:
            _abort("tax_plugin_failed")
        if stdout or stderr:
            _abort("tax_plugin_output_invalid")
        entries = list(output.iterdir())
        if (
            len(entries) != 1 or entries[0].name != "tax-plugin-output.json"
            or entries[0].is_symlink() or not entries[0].is_file()
        ):
            _abort("tax_plugin_output_invalid")
        raw = entries[0].read_bytes()
        data = json.loads(raw)
        required = {
            "api_version", "plugin_id", "plugin_version", "rules_fingerprint",
            "projection_mode", "status", "rows", "reconciliation", "disclaimer_codes",
        }
        if (
            set(data) != required or data["api_version"] != "tax_model_plugin_v1"
            or data["plugin_id"] != selected.plugin_id
            or data["plugin_version"] != selected.plugin_version
            or data["rules_fingerprint"] != selected.rules_fingerprint
            or data["projection_mode"] != bound_input["projection_mode"]
            or data["status"] != "completed"
        ):
            _abort("tax_plugin_output_invalid")
        if (
            not isinstance(data["rows"], list)
            or not isinstance(data["reconciliation"], dict)
            or data["disclaimer_codes"] != list(selected.disclaimer_codes)
        ):
            _abort("tax_plugin_output_invalid")
        try:
            base._validate_json_values(data)
        except base.TaxPluginBlocked as error:
            raise TaxPluginV2Blocked(error.code) from error
        rows = [dict(row) for row in data["rows"]]
        for row in rows:
            if (
                not isinstance(row, dict)
                or row.get("model_fingerprint") != manifest.model_fingerprint
                or row.get("parameter_fingerprint") != parameter_fingerprint
            ):
                _abort("tax_plugin_output_invalid")
            for field, value in row.items():
                if field.endswith("_decimal") and value is not None and (
                    not isinstance(value, str) or base.DECIMAL.fullmatch(value) is None
                ):
                    _abort("tax_plugin_output_invalid")
        reconciliation = dict(data["reconciliation"])
        if (
            reconciliation.get("church_tax_basis") != "projected_income_tax"
            or reconciliation.get("church_tax_identity_inference") is not False
            or reconciliation.get("event_tax_is_annual_tax") is not False
        ):
            _abort("tax_plugin_output_invalid")
        return TaxPluginV2RunResult(
            bound_input["run_ref"], selected.plugin_id, selected.plugin_version,
            selected.rules_fingerprint, manifest.model_fingerprint,
            parameter_fingerprint, bound_input["projection_mode"], input_fingerprint,
            base.sha(raw), tuple(rows), reconciliation, tuple(data["disclaimer_codes"]),
        )
    except TaxPluginV2Blocked:
        raise
    except (json.JSONDecodeError, UnicodeError, OSError) as error:
        raise TaxPluginV2Blocked("tax_plugin_output_invalid") from error
    finally:
        try:
            os.chmod(source, 0o600)
            shutil.rmtree(staging)
        except OSError:
            pass


__all__ = [
    "INSTITUTION_PARAMETER_CODES", "TaxPluginV2Blocked", "TaxPluginV2Manifest", "TaxPluginV2RunResult",
    "run_tax_model_plugin_v2", "tax_plugin_manifest_v2",
]
