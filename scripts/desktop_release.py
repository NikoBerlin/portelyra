#!/usr/bin/env python3
"""Fixed owner-only boundary for Portelyra Desktop Release v1."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workers.reference.desktop_release_v1 import (  # noqa: E402
    DesktopReleaseError,
    build_desktop_release_v1,
    create_desktop_backup_v1,
    new_desktop_release_capability_v1,
    backup_summary_desktop_v1,
    preflight_desktop_restore_v1,
    bind_restored_data_space_v1,
    private_acceptance_check_v1,
    list_desktop_backups_v1,
    prune_desktop_backups_v1,
    release_archive_signature_v1,
    release_signer_v1,
    release_signing_required_v1,
    restore_into_fresh_home_v1,
    restore_desktop_backup_v1,
    stage_desktop_update_v1,
    validate_desktop_backup_v1,
    validate_desktop_release_archive_v1,
)


def abort(code: str) -> None:
    raise DesktopReleaseError(code)


def load_job(path: Path) -> dict:
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        abort("desktop_release_input_invalid")
    if path.stat().st_size > 1_000_000:
        abort("desktop_release_input_invalid")
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        abort("desktop_release_input_invalid")
    if not isinstance(envelope, dict) or set(envelope) != {"contract_version", "payload_json", "payload_fingerprint"} or envelope.get("contract_version") != 1 or not isinstance(envelope.get("payload_json"), str) or hashlib.sha256(envelope["payload_json"].encode("utf-8")).hexdigest() != envelope.get("payload_fingerprint"):
        abort("desktop_release_input_invalid")
    try:
        payload = json.loads(envelope["payload_json"])
    except Exception:
        abort("desktop_release_input_invalid")
    if not isinstance(payload, dict) or payload.get("contract_version") != 1 or not isinstance(payload.get("operation"), str):
        abort("desktop_release_input_invalid")
    return payload


def exact(payload: dict, keys: set[str]) -> None:
    if set(payload) != keys | {"contract_version", "operation"}:
        abort("desktop_release_input_invalid")


def source_key(payload: dict) -> set[str]:
    return {"source_permissions"} if "source_permissions" in payload else set()


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--job", required=True)
    try:
        arguments = parser.parse_args()
        payload = load_job(Path(arguments.job))
        operation = payload["operation"]
        if operation in {"backup", "restore"}:
            base = {"source_home", "session_nonce"}
            if operation == "backup":
                exact(payload, base | {"target_bundle", "product_version", "created_at_utc"})
                cap = new_desktop_release_capability_v1(Path(payload["source_home"]), payload["session_nonce"])
                result = create_desktop_backup_v1(cap, Path(payload["target_bundle"]), payload["product_version"], payload["created_at_utc"])
            else:
                exact(payload, base | {"bundle", "target_home"})
                cap = new_desktop_release_capability_v1(Path(payload["source_home"]), payload["session_nonce"])
                result = restore_desktop_backup_v1(cap, Path(payload["bundle"]), Path(payload["target_home"]))
                # Restore bindet neu (#493): an einem anderen Ort den Ursprung der pfadgebundenen Speicher vermerken.
                result = {**result, **bind_restored_data_space_v1(cap, Path(payload["target_home"]))}
        elif operation == "restore_fresh":
            # "source_permissions" (rc.410): "ignored" fuer einen vom Nutzer genannten Ordner, der nur gelesen wird; ohne das Feld streng.
            exact(payload, {"source_home", "session_nonce", "bundle", "product_version"} | source_key(payload))
            cap = new_desktop_release_capability_v1(Path(payload["source_home"]), payload["session_nonce"])
            result = restore_into_fresh_home_v1(cap, Path(payload["bundle"]), payload["product_version"],
                                                source_permissions=payload.get("source_permissions", "strict"))
        elif operation == "backup_check":
            exact(payload, {"bundle"} | source_key(payload))
            result = {"status": "valid", "operation": operation, "safe_output": True,
                      **backup_summary_desktop_v1(Path(payload["bundle"]), source_permissions=payload.get("source_permissions", "strict"))}
        elif operation == "backup_list":
            exact(payload, {"root", "product_version", "home"} | source_key(payload))
            result = list_desktop_backups_v1(Path(payload["root"]), payload["product_version"], None if payload["home"] is None else Path(payload["home"]),
                                             source_permissions=payload.get("source_permissions", "strict"))
        elif operation == "backup_prune":
            # "home" (rc.410): nur die Backups dieses Datenraums; ohne das Feld wie bisher (Aufruf nur mit Ordner).
            exact(payload, {"root", "keep", "plan_fingerprint"} | ({"home"} if "home" in payload else set()))
            home = payload.get("home")
            result = prune_desktop_backups_v1(Path(payload["root"]), payload["keep"], payload["plan_fingerprint"], None if home is None else Path(home))
        elif operation == "restore_preflight":
            exact(payload, {"bundle", "target_home"}); preflight_desktop_restore_v1(Path(payload["bundle"]), Path(payload["target_home"])); result = {"status": "ready_for_confirmed_restore", "operation": operation, "safe_output": True}
        elif operation == "release_build":
            # Signiert, sobald die Vertrauensliste des Projekts einen Schluessel traegt (#486 Schritt 3); dann nur mit eingerichtetem Schluessel.
            exact(payload, {"project_root", "archive", "product_version"})
            signer = release_signer_v1(Path(payload["project_root"]))
            release_signing_required_v1(payload["product_version"], signer)
            result = build_desktop_release_v1(Path(payload["project_root"]), Path(payload["archive"]), payload["product_version"], signer=signer)
        elif operation == "release_check":
            # Signatur gegen die Vertrauensliste des Projekts, das prueft: traegt sie einen Schluessel, muss das Archiv damit signiert sein.
            exact(payload, {"archive", "project_root"})
            validate_desktop_release_archive_v1(Path(payload["archive"]))
            checked = release_archive_signature_v1(Path(payload["archive"]), Path(payload["project_root"]) / "contracts" / "plugin-signing" / "v1" / "allowed_signers")
            result = {"status": "valid", "operation": operation, "safe_output": True, "signature": checked["signature"]}
        elif operation == "release_update_stage":
            exact(payload, {"archive", "staging", "trust_list"})
            result = stage_desktop_update_v1(Path(payload["archive"]), Path(payload["staging"]), Path(payload["trust_list"]))
        elif operation == "acceptance_check":
            exact(payload, {"source_home", "session_nonce", "bundle", "restored_home"})
            cap = new_desktop_release_capability_v1(Path(payload["source_home"]), payload["session_nonce"])
            result = private_acceptance_check_v1(cap, Path(payload["bundle"]), Path(payload["restored_home"]))
        else:
            abort("desktop_release_input_invalid")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")))
        return 0 if result.get("status") != "fail" else 2
    except DesktopReleaseError as error:
        blocked = {"status": "blocked", "code": error.code}
        if error.relative_path is not None:     # desktop_release_source_unreadable (#568): welcher Eintrag, relativ zum Datenraum
            blocked["relative_path"] = error.relative_path
        print(json.dumps(blocked, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 2
    except Exception:
        print('{"code":"desktop_release_boundary_failed","status":"blocked"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
