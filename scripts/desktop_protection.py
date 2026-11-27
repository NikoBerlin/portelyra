#!/usr/bin/env python3
"""CLI-Grenze des Passwortschutzes (#535, rc.396): JSON ueber stdin, eine JSON-Zeile auf stdout.

status: ob der Schutz an ist und ob entsperrt.  unlock / lock: einhaengen bzw. aushaengen.
enable: Schutz einschalten (Ordner anlegen, Datenbestand und Backups hineinkopieren und pruefen); das Ergebnis nennt den
        Wiederherstellungsschluessel genau einmal.  finalize: Klartext nach Pruefung und neuem Backup loeschen.
change-password / recover: neues Passwort mit dem alten bzw. mit dem Wiederherstellungsschluessel.
unlock-keyring / keyring: mit dem Passwort aus dem Schluesselbund entsperren bzw. das ein- und ausschalten (#553).
request-rekey / cancel-rekey / rekey / remove-old: Schluessel erneuern auf der Startseite und danach die alten Ordner entfernen (#552).
Passwoerter und Schluessel kommen nur ueber stdin und erscheinen in keiner Ausgabe ausser dem einmaligen Schluessel bei enable.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference import desktop_protection_v1 as protection  # noqa: E402

COMMANDS = {
    "status": ((), lambda v: protection.status_v1(v["home"])),
    "unlock": (("password",), lambda v: protection.unlock_v1(v["home"], v["password"])),
    "lock": ((), lambda v: protection.lock_v1(v["home"])),
    # Bis zur Abmeldung entsperrt (#587): Beenden sperrt nur, wenn es eingestellt oder angefordert ist; ein Zeitlauf zusaetzlich, was nur er
    # geoeffnet hat.
    "lock-if-due": ((), lambda v: protection.lock_if_due_v1(v["home"])),
    "unlock-for-run": ((), lambda v: protection.unlock_for_run_v1(v["home"])),
    "lock-after-run": ((), lambda v: protection.lock_after_run_v1(v["home"])),
    "keep-open": ((), lambda v: protection.keep_open_v1(v["home"])),
    "lock-on-quit": (("enabled",), lambda v: protection.set_lock_on_quit_v1(v["home"], v["enabled"])),
    "request-lock": ((), lambda v: protection.request_lock_v1(v["home"])),
    "stray-ack": ((), lambda v: protection.clear_stray_note_v1(v["home"])),
    "seal-if-lost": ((), lambda v: protection.seal_if_lost_v1(v["home"])),
    "ensure-sleep-guard": ((), lambda v: {"started": protection.ensure_sleep_guard_v1(v["home"])}),
    "catch-up-after-sleep": ((), lambda v: protection.catch_up_after_sleep_v1(v["home"])),
    "enable": (("password", "repeat", "confirmed"), lambda v: protection.enable_v1(
        v["home"], v["password"], v["repeat"], v["confirmed"], backups_source=v.get("backups_source"), keyring=v.get("keyring", False))),
    # Mit der Anmeldung entsperren (#553) und Schluessel erneuern (#552).
    "unlock-keyring": ((), lambda v: protection.unlock_from_keyring_v1(v["home"])),
    "keyring": (("enabled",), lambda v: protection.set_keyring_unlock_v1(v["home"], v["enabled"], v.get("password"))),
    "request-rekey": (("confirmed",), lambda v: protection.request_rekey_v1(v["home"], v["confirmed"])),
    "cancel-rekey": ((), lambda v: protection.cancel_rekey_v1(v["home"])),
    "rekey": (("current", "new", "repeat", "confirmed"), lambda v: protection.rekey_v1(v["home"], v["current"], v["new"], v["repeat"], v["confirmed"])),
    "remove-old": (("confirmed",), lambda v: protection.remove_old_ciphers_v1(v["home"], v["confirmed"])),
    "finalize": (("confirmed",), lambda v: protection.finalize_v1(v["home"], v["confirmed"], v.get("accept_difference", False))),
    "change-password": (("old", "new", "repeat"), lambda v: protection.change_password_v1(v["home"], v["old"], v["new"], v["repeat"])),
    "recover": (("recovery_key", "new", "repeat"), lambda v: protection.recover_v1(v["home"], v["recovery_key"], v["new"], v["repeat"])),
    # Wiederherstellen im Einrichtungsdialog (#559 Teil 2): den verschluesselten Backup-Ordner nur lesend oeffnen und wieder schliessen;
    # vor dem neuen Schutz den alten Ordner umbenennen. "home" wird mitgegeben wie bei allen Befehlen, gebraucht wird es hier nicht.
    "restore-open": (("secret", "kind"), lambda v: protection.open_backups_readonly_v1(v["secret"], v["kind"], v.get("cipher"))),
    "restore-close": (("mount",), lambda v: protection.close_backups_readonly_v1(v["mount"])),
    "set-aside-backups": (("confirmed",), lambda v: protection.set_aside_backups_v1(v["confirmed"])),
    # Unlesbare Eintraege (#568): Vorschau (entsperrt), bestaetigter Auftrag, Ausfuehrung beim Start (gesperrt).
    "unreadable-preview": ((), lambda v: protection.unreadable_preview_v1(v["home"])),
    "unreadable-request": (("preview_fingerprint", "confirmed"), lambda v: protection.unreadable_request_v1(v["home"], v["preview_fingerprint"], v["confirmed"])),
    "unreadable-execute": ((), lambda v: protection.unreadable_execute_v1(v["home"])),
}
OPTIONAL = {"enable": {"backups_source", "keyring"}, "finalize": {"accept_difference"}, "keyring": {"password"}, "restore-open": {"cipher"}}


def _emit(value: dict) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False))


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        # Der Waechter fuer den Ruhezustand (#587) laeuft als eigene Einheit ohne stdin; das Home ist kein Geheimnis.
        if command == "sleep-guard" and len(sys.argv) == 3:
            _emit({"status": "completed", "result": protection.sleep_guard_v1(sys.argv[2])})
            return 0
        if command not in COMMANDS:
            raise protection.DesktopProtectionV1Error("desktop_protection_input_invalid")
        extra, run = COMMANDS[command]
        value = json.loads(sys.stdin.read())
        allowed = {"home", *extra} | OPTIONAL.get(command, set())
        if not isinstance(value, dict) or not ({"home", *extra} <= set(value) <= allowed) or not isinstance(value["home"], str):
            raise protection.DesktopProtectionV1Error("desktop_protection_input_invalid")
        _emit({"status": "completed", "result": run(value)})
        return 0
    except protection.DesktopProtectionV1Error as error:
        _emit({"status": "blocked", "code": error.code, **({"detail": error.detail} if error.detail else {})})
        return 2
    except (OSError, KeyError, TypeError, ValueError):
        _emit({"status": "blocked", "code": "desktop_protection_input_invalid"})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
