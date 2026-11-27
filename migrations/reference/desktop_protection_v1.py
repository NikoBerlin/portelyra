"""Passwortschutz mit verschluesseltem Datenbestand (#535, rc.396).

Festlegungen (03.11. und 10.11.2026):
- Konsequent: Eine Sperre der Apps bei lesbaren Dateien gilt nicht als Schutz. Weg B: Der Datenbestand liegt in einem verschluesselten
  Ordner (gocryptfs), beim Entsperren eingehaengt, beim Beenden ausgehaengt. Kern und Vertraege sehen weiter normale Dateien.
- Benutzerebene: ein Passwort fuer alle Portfolios; abwaehlbar beim Einrichten, mit klarem Hinweis.
- Entsperren auf einer eigenen lokalen Startseite; ein Wiederherstellungsschluessel (der Hauptschluessel), einmal angezeigt, fuer Daten
  und Backups gemeinsam; Backups in einem zweiten verschluesselten Ordner mit demselben Schluessel; der Klartext wird nach Pruefung und
  Backup geloescht.
- Der Einhaengepunkt liegt erzwungen unter ``$XDG_RUNTIME_DIR`` (/run/user/<uid>): ausserhalb des gesicherten Bereichs, nur fuer den
  Benutzer, beim Abmelden geraeumt. Sonst kopierten Sicherungen (Deja Dup, Back In Time, rsync) oder Sync-Clients die Klartext-Ansicht mit.
- Linux zuerst; macOS und Windows spaeter.
- #553 (11.11.2026): wahlweise mit der Anmeldung entsperren - das Passwort im Schluesselbund (secret-tool), beim Einrichten vorangekreuzt.
  Start, `unlock` und Zeitlaeufe entsperren damit selbst; der Schluesselbund ist nur offen, solange der Benutzer angemeldet ist.
- #552 (11.11.2026): Schluessel erneuern auf der Startseite vor den Apps (neuer Hauptschluessel, alles neu verschluesselt und geprueft);
  die alten Ordner werden nach einem Backup in den neuen bewusst entfernt.
- #587: Einmal entsperrt bleibt der Bestand offen, bis sich der Benutzer abmeldet oder den Rechner herunterfaehrt. Die Einhaengung gehoert einer eigenen Einheit der Sitzung, weder
  der App noch einem Zeitlauf. Beim Beenden sperrt nur, wer das einstellt oder ausdruecklich anfordert (`lock_if_due_v1`). Vor dem
  Ruhezustand sperrt ein Waechter der Sitzung (`sleep_guard_v1`), ausser es wird gerade geschrieben; das bricht er nie ab. Danach gilt
  der Schluesselbund nicht mehr, bis das Passwort eingegeben ist: Er bleibt im Ruhezustand offen, und sonst oeffnete ein faelliger Zeitlauf
  den Bestand hinter der Bildschirmsperre. Der Vermerk liegt im Arbeitsspeicher der Sitzung; die naechste Anmeldung gilt wieder als Nachweis.

Ohne ``protection.json`` im Home ist alles wie bisher: der Datenbestand liegt in ``<home>/data``. Passwoerter gehen nur ueber stdin an
gocryptfs, nie ueber die Befehlszeile; Portelyra speichert weder Passwort noch Wiederherstellungsschluessel.
"""
from __future__ import annotations

from datetime import datetime, timezone
import errno
import hashlib
import json
import os
import pwd
import re
import secrets
from pathlib import Path
import shutil
import stat
import selectors
import subprocess
import sys
import time
from typing import Any

STATE_FILE = "protection.json"
DATA_CIPHER = "data.crypt"
CONTRACT = "desktop_protection_v1"
MIN_PASSWORD_LENGTH = 10
GOCRYPTFS_WRONG_PASSWORD = 12
FAILURE_CODES = (
    "desktop_protection_input_invalid", "desktop_protection_state_invalid", "desktop_protection_locked",
    "desktop_protection_password_wrong", "desktop_protection_wait", "desktop_protection_tool_missing",
    "desktop_protection_runtime_dir_invalid", "desktop_protection_already_enabled", "desktop_protection_not_enabled",
    "desktop_protection_mount_failed", "desktop_protection_copy_mismatch", "desktop_protection_recovery_key_invalid",
    "desktop_protection_password_too_short", "desktop_protection_password_mismatch", "desktop_protection_confirmation_required",
    "desktop_protection_backup_required", "desktop_protection_busy", "desktop_protection_no_data_space",
    "desktop_protection_backups_folder_exists", "desktop_protection_keyring_unavailable", "desktop_protection_keyring_stale",
    "desktop_protection_disk_space", "desktop_protection_rekey_pending", "desktop_protection_backups_absent",
    "desktop_protection_backups_in_use", "desktop_protection_unreadable_stale", "desktop_protection_unreadable_not_quarantinable",
    "desktop_protection_unreadable_none", "desktop_protection_unreadable_request_invalid", "desktop_protection_password_after_sleep",
)
KEYRING_APPLICATION = "portelyra"
KEYRING_TOOL_ENV = "PORTELYRA_SECRET_TOOL_INTERNAL"   # wie bei den Zugaengen (#546); Tests: Pfad zu einem erfundenen secret-tool
KEYRING_LABEL = "Portelyra – Passwortschutz"
# Verzoegerung nach Fehlversuchen (Sekunden) - ab dem dritten falschen Passwort, verdoppelt, hoechstens eine Minute.
_FREE_ATTEMPTS = 3
_MAX_WAIT = 60
LOCK_REQUEST = "protection-lock-request.json"   # "Jetzt sperren" (#587): gilt einmal, beim naechsten Beenden
STRAY_NOTE = "protection-stray.json"            # Was beim Entsperren im leeren Einhaengeordner lag (#587): nur Zaehler und Ordnername
SLEEP_GUARD_ENV = "PORTELYRA_PROTECTION_SLEEP_GUARD_INTERNAL"   # "off": kein Waechter (Tests mit erfundenen Homes)


class DesktopProtectionV1Error(RuntimeError):
    def __init__(self, code: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "desktop_protection_state_invalid"
        self.detail = dict(detail or {})


def _abort(code: str, **detail: Any) -> None:
    raise DesktopProtectionV1Error(code, detail)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------------------------------------------------------
# Orte
# ---------------------------------------------------------------------------------------------------------------------------

def _home(home: str | Path) -> Path:
    path = Path(home).expanduser()
    if not path.is_dir() or path.is_symlink():
        _abort("desktop_protection_input_invalid")
    return path.resolve()


def _runtime_dir() -> Path:
    """$XDG_RUNTIME_DIR (bzw. /run/user/<uid>): muss dem Benutzer gehoeren und 0700 sein - sonst kein Einhaengen."""
    value = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    path = Path(value)
    try:
        info = path.stat()
    except OSError:
        _abort("desktop_protection_runtime_dir_invalid")
        raise
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        _abort("desktop_protection_runtime_dir_invalid")
    return path


def mount_root_v1(home: str | Path) -> Path:
    """Wo die Klartext-Ansicht haengt: je Home ein eigener Ordner unter $XDG_RUNTIME_DIR."""
    resolved = _home(home)
    return _runtime_dir() / ("portelyra-" + hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12])


def _default_backups_cipher() -> Path:
    state = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state) / "portelyra" / "backups.crypt"


def read_state_v1(home: str | Path) -> dict[str, Any] | None:
    path = _home(home) / STATE_FILE
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _abort("desktop_protection_state_invalid")
        raise
    if not isinstance(value, dict) or value.get("contract_version") != CONTRACT or value.get("enabled") is not True \
            or value.get("data_cipher") != DATA_CIPHER or not isinstance(value.get("backups_cipher"), str):
        _abort("desktop_protection_state_invalid")
    return value


def _write_state(home: Path, value: dict[str, Any]) -> None:
    path = home / STATE_FILE
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _mounted(path: Path) -> bool:
    try:
        return os.path.ismount(path)
    except OSError:
        return False


def _stale(path: Path) -> bool:
    """Ein abgestuerzter gocryptfs hinterlaesst einen Einhaengepunkt, der "nicht verbunden" meldet."""
    try:
        os.stat(path)
        return False
    except OSError as error:
        return error.errno == errno.ENOTCONN


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        _abort("desktop_protection_tool_missing", tool=name)
    return found


def _unmount(path: Path, wait_seconds: float = 10.0) -> bool:
    """Haengt aus; ist noch eine Datei offen (eine App schliesst gerade ihre Datenbank), bis zu `wait_seconds` erneut. Nie verzoegert
    aushaengen (-z): ein noch laufender Schreibvorgang verloere sonst seinen Ordner mitten im Schreiben. True, wenn ausgehaengt."""
    deadline = time.monotonic() + wait_seconds
    while _mounted(path) or _stale(path):
        subprocess.run([_tool("fusermount"), "-u", str(path)], check=False, capture_output=True, timeout=60)
        if not (_mounted(path) or _stale(path)):
            break
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)
    return True


def _paths(home: Path, state: dict[str, Any] | None = None) -> dict[str, Path]:
    root = mount_root_v1(home)
    backups_cipher = Path(state["backups_cipher"]) if state else _default_backups_cipher()
    return {"data_cipher": home / DATA_CIPHER, "backups_cipher": backups_cipher, "root": root,
            "data_mount": root / "data", "backups_mount": root / "backups"}


# ---------------------------------------------------------------------------------------------------------------------------
# Zustand und Datenpfad
# ---------------------------------------------------------------------------------------------------------------------------

def status_v1(home: str | Path) -> dict[str, Any]:
    """Ob der Schutz an ist, ob entsperrt (beide Ordner eingehaengt) und ob ein Einhaengepunkt nach einem Absturz haengt."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        return {"contract_version": CONTRACT, "enabled": False, "unlocked": True, "stale": False, "plaintext_removed": None,
                "data_root": str(resolved / "data"), "backups_root": None}
    paths = _paths(resolved, state)
    data, backups = _mounted(paths["data_mount"]), _mounted(paths["backups_mount"])
    old_pending = bool(state.get("old_ciphers"))
    # Erstes Backup im verschluesselten Ordner faellig (nach dem Einrichten bzw. nach dem Erneuern des Schluessels): legt der Start an,
    # bevor die Apps laufen (die Data-App kann keine Backups).
    due = bool(data and backups and (not state.get("plaintext_removed") or old_pending)
               and not _fresh_backups(paths["backups_mount"], _backup_reference(state)))
    return {"contract_version": CONTRACT, "enabled": True, "unlocked": data and backups, "first_backup_due": due,
            "stale": _stale(paths["data_mount"]) or _stale(paths["backups_mount"]), "plaintext_removed": bool(state.get("plaintext_removed")),
            "data_root": str(paths["data_mount"]) if data else None, "backups_root": str(paths["backups_mount"]) if backups else None,
            "mount_root": str(paths["root"]), "created_at_utc": state.get("created_at_utc"),
            "keyring_unlock": bool(state.get("keyring_unlock")), "keyring_tool": _secret_tool() is not None,
            "rekey_requested": bool(state.get("rekey_requested")), "rekeyed_at_utc": state.get("rekeyed_at_utc"), "old_ciphers_pending": old_pending,
            "lock_on_quit": bool(state.get("lock_on_quit")), "lock_requested": (resolved / LOCK_REQUEST).is_file(),
            "stray_note": _read_stray_note(resolved), "sleep_note": _read_sleep_note(resolved),
            "unreadable_check": _read_unreadable_check(resolved), "unreadable_quarantine_requested": (resolved / UNREADABLE_REQUEST).is_file()}


def _backup_reference(state: dict[str, Any]) -> str:
    return max(str(state.get("created_at_utc") or ""), str(state.get("rekeyed_at_utc") or ""))


def _fresh_backups(backups_mount: Path, created: str) -> list[Path]:
    """Backups im verschluesselten Ordner, die nach dem Einschalten bzw. dem Erneuern entstanden (fertige Buendel mit SUCCESS)."""
    try:
        return [path for path in backups_mount.iterdir() if path.is_dir() and (path / "SUCCESS").is_file() and
                datetime.fromtimestamp((path / "SUCCESS").stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") > created]
    except OSError:
        return []


def data_root_v1(home: str | Path) -> Path:
    """Der Ort des Datenbestands: ohne Schutz ``<home>/data``, mit Schutz die eingehaengte Klartext-Ansicht. Gesperrt: Abbruch mit
    ``desktop_protection_locked`` - nie still auf einen anderen Ort ausweichen."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        return resolved / "data"
    paths = _paths(resolved, state)
    if not _mounted(paths["data_mount"]):
        _abort("desktop_protection_locked")
    return paths["data_mount"]


def backups_root_v1(home: str | Path) -> Path | None:
    """Mit Schutz der eingehaengte Backup-Ordner (gesperrt: Abbruch); ohne Schutz None (Backups gehen, wohin sie bisher gingen)."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        return None
    paths = _paths(resolved, state)
    if not _mounted(paths["backups_mount"]):
        _abort("desktop_protection_locked")
    return paths["backups_mount"]


# ---------------------------------------------------------------------------------------------------------------------------
# Entsperren und Sperren
# ---------------------------------------------------------------------------------------------------------------------------

def _attempts_path(home: Path) -> Path:
    return mount_root_v1(home).with_name(mount_root_v1(home).name + ".attempts")


def _check_wait(home: Path) -> None:
    path = _attempts_path(home)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    failures, last = int(value.get("failures", 0)), float(value.get("last", 0))
    if failures < _FREE_ATTEMPTS:
        return
    wait = min(_MAX_WAIT, 2 ** (failures - _FREE_ATTEMPTS + 1))
    remaining = int(last + wait - time.time()) + 1
    if remaining > 0:
        _abort("desktop_protection_wait", seconds=remaining)


def _record_attempt(home: Path, failed: bool) -> None:
    path = _attempts_path(home)
    if not failed:
        path.unlink(missing_ok=True)
        return
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {}
    value = {"failures": int(value.get("failures", 0)) + 1, "last": time.time()}
    path.write_text(json.dumps(value), encoding="utf-8")
    os.chmod(path, 0o600)


def _session_binding() -> list[str]:
    """Mit `linger` laeuft der Benutzerdienst ueber das Abmelden hinaus; die Einheit endet dann mit der grafischen Sitzung."""
    try:
        lingering = Path("/var/lib/systemd/linger", pwd.getpwuid(os.getuid()).pw_name).exists()
        if lingering and subprocess.run(["systemctl", "--user", "is-active", "--quiet", "graphical-session.target"], capture_output=True,
                                        timeout=10).returncode == 0:
            return ["-p", "BindsTo=graphical-session.target", "-p", "After=graphical-session.target"]
    except (KeyError, OSError, subprocess.SubprocessError):
        pass
    return []


def _session_unit(mount: Path) -> list[str]:
    """Eigene systemd-Einheit der Sitzung fuer gocryptfs (#587). Sonst gehoert der Prozess dem, der entsperrt hat: Endet ein Zeitlauf
    (Type=oneshot, KillMode=control-group), beendet systemd auch gocryptfs, und der Bestand verschwindet unter der offenen App. Die
    Einheit endet mit dem Benutzerdienst beim Abmelden. Ohne Benutzerdienst (Container) leer: dort raeumt niemand ab."""
    tool, runtime = shutil.which("systemd-run"), os.environ.get("XDG_RUNTIME_DIR", "")
    if tool is None or not runtime or not (Path(runtime) / "systemd" / "private").exists():
        return []
    unit = f"portelyra-vault-{mount.parent.name.removeprefix('portelyra-')}-{mount.name}-{secrets.token_hex(4)}"
    return [tool, "--user", "--scope", "--quiet", "--collect", f"--unit={unit}", *_session_binding()]


def _mount(cipher: Path, mount: Path, password: str | None = None, master_key: str | None = None) -> int:
    mount.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(mount, 0o700)
    if master_key is not None:
        command, secret = [_tool("gocryptfs"), "-q", "-masterkey=stdin", str(cipher), str(mount)], master_key
    else:
        command, secret = [_tool("gocryptfs"), "-q", str(cipher), str(mount)], password or ""
    unit = _session_unit(mount)
    if unit:
        result = subprocess.run([*unit, *command], input=secret.encode("utf-8"), capture_output=True, timeout=120)
        if result.returncode == GOCRYPTFS_WRONG_PASSWORD or _mounted(mount):
            return result.returncode
    # Keine Einheit anlegbar: wie bisher einhaengen. Ein echter Fehler von gocryptfs kommt hier ein zweites Mal und wird gemeldet.
    result = subprocess.run(command, input=secret.encode("utf-8"), capture_output=True, timeout=120)
    return result.returncode


# ---------------------------------------------------------------------------------------------------------------------------
# Wiederherstellen aus dem verschluesselten Backup-Ordner im Einrichtungsdialog (#559 Teil 2, rc.408)
# ---------------------------------------------------------------------------------------------------------------------------
RESTORE_MOUNT = re.compile(r"^portelyra-restore-[0-9a-f]{12}$")


def open_backups_readonly_v1(secret: Any, kind: Any, cipher: Any = None) -> dict[str, Any]:
    """Haengt den verschluesselten Backup-Ordner des Benutzerkontos nur lesend ein - mit Passwort oder Wiederherstellungsschluessel, beide
    nur ueber stdin. Das ist der Notfallweg aus dem Handbuch (#535) auf der Seite statt im Terminal: Das alte Home ist weg, die Backups
    sind noch da. Eingehaengt wird in einen eigenen Ordner unter $XDG_RUNTIME_DIR; nichts am Ordner selbst aendert sich."""
    if kind not in {"password", "recovery_key"} or not isinstance(secret, str) or not secret.strip():
        _abort("desktop_protection_input_invalid")
    # `cipher` (rc.410, Ordnerwahl): ein verschluesselter Backup-Ordner an anderer Stelle, etwa eine Kopie auf einer Sicherungsplatte.
    # Nur ein vollstaendiger Pfad ohne Steuerzeichen; geoeffnet wird er wie der eigene nur lesend.
    if cipher is None:
        cipher = _default_backups_cipher()
    elif not isinstance(cipher, str) or not cipher.startswith("/") or any(ord(char) < 32 for char in cipher):
        _abort("desktop_protection_input_invalid")
    else:
        cipher = Path(cipher)
    if not (cipher / "gocryptfs.conf").is_file():
        _abort("desktop_protection_backups_absent")
    mount = _runtime_dir() / ("portelyra-restore-" + secrets.token_hex(6))
    mount.mkdir(mode=0o700)
    os.chmod(mount, 0o700)
    if kind == "password":
        command, payload = [_tool("gocryptfs"), "-q", "-ro", str(cipher), str(mount)], secret
    else:
        command, payload = [_tool("gocryptfs"), "-q", "-ro", "-masterkey=stdin", str(cipher), str(mount)], secret.strip()
    result = subprocess.run(command, input=payload.encode("utf-8"), capture_output=True, timeout=120)
    if result.returncode != 0:
        try:
            mount.rmdir()
        except OSError:
            pass
        if kind == "password" and result.returncode == GOCRYPTFS_WRONG_PASSWORD:
            _abort("desktop_protection_password_wrong")
        _abort("desktop_protection_recovery_key_invalid" if kind == "recovery_key" else "desktop_protection_mount_failed")
    return {"contract_version": CONTRACT, "mount": str(mount), "read_only": True}


def close_backups_readonly_v1(mount: Any) -> dict[str, Any]:
    """Haengt den nur lesend eingehaengten Backup-Ordner wieder aus. Nur Ordner, die open_backups_readonly_v1 angelegt hat."""
    if not isinstance(mount, str):
        _abort("desktop_protection_input_invalid")
    path = Path(mount)
    if path.parent != _runtime_dir() or not RESTORE_MOUNT.fullmatch(path.name):
        _abort("desktop_protection_input_invalid")
    if _mounted(path) and not _unmount(path):
        _abort("desktop_protection_busy")
    if path.exists():
        path.rmdir()
    return {"contract_version": CONTRACT, "closed": True}


def _mount_field(value: str) -> str:
    """Ein Feld aus /proc/mounts im Klartext: Leerzeichen, Tabulator, Zeilenumbruch und Rueckstrich stehen dort als \\040, \\011, \\012, \\134."""
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), value)


def _cipher_in_use(cipher: Path) -> bool:
    """Ist der verschluesselte Ordner gerade irgendwo eingehaengt (eine andere Installation dieses Kontos ist entsperrt)?

    gocryptfs fuehrt den Ordner in /proc/mounts als Quelle - so, wie er beim Einhaengen genannt wurde, also unaufgeloest. Verglichen wird
    deshalb der Ordner selbst (Geraet und Inode), nicht der Text: Ein Home hinter einem symbolischen Verweis oder ein Pfad mit
    Sonderzeichen bliebe sonst unerkannt (Prüfung 13.11.2026). Nicht lesbar: im Zweifel „in Gebrauch“."""
    try:
        own = os.stat(cipher)
    except OSError:
        return False
    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="surrogateescape") as handle:
            for line in handle:
                fields = line.split(" ")
                if len(fields) < 3 or not fields[2].startswith("fuse.gocryptfs"):
                    continue
                try:
                    source = os.stat(_mount_field(fields[0]))
                except OSError:
                    continue
                if (source.st_dev, source.st_ino) == (own.st_dev, own.st_ino):
                    return True
    except OSError:
        return True
    return False


def set_aside_backups_v1(confirmed: Any) -> dict[str, Any]:
    """Vor dem neuen Passwortschutz nach einem Wiederherstellen: den alten verschluesselten Backup-Ordner umbenennen. Er bleibt unveraendert
    und oeffnet weiter mit dem alten Passwort oder Schluessel; unter dem alten Namen lehnte das Einrichten ab (backups_folder_exists)."""
    if confirmed is not True:
        _abort("desktop_protection_confirmation_required")
    cipher = _default_backups_cipher()
    if not cipher.exists():
        _abort("desktop_protection_backups_absent")
    # Der Ordner gehoert allen Installationen dieses Benutzerkontos (Fallstrick wie rc.403): Ist er gerade eingehaengt, nutzt ihn eine
    # andere Installation - dann nie umbenennen. Sonst nur nach ausdruecklicher Rueckfrage auf der Seite (Festlegung 13.11.2026).
    if _cipher_in_use(cipher):
        _abort("desktop_protection_backups_in_use")
    target = cipher.with_name(cipher.name + ".alt-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    if target.exists():
        _abort("desktop_protection_busy")
    os.rename(cipher, target)
    return {"contract_version": CONTRACT, "set_aside_as": target.name}


def unlock_v1(home: str | Path, password: str) -> dict[str, Any]:
    """Haengt Daten- und Backup-Ordner ein. Ein falsches Passwort zaehlt; ab dem dritten wartet der naechste Versuch (verdoppelt, hoechstens
    eine Minute). Ein nach einem Absturz haengender Einhaengepunkt wird vorher geloest."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    if not isinstance(password, str) or not password:
        _abort("desktop_protection_input_invalid")
    paths = _paths(resolved, state)
    for mount in (paths["data_mount"], paths["backups_mount"]):
        if _stale(mount):
            _unmount(mount)
    if _mounted(paths["data_mount"]) and _mounted(paths["backups_mount"]):
        _run_opened_path(resolved).unlink(missing_ok=True)      # #587: Jetzt hat der Benutzer entsperrt, nicht mehr nur ein Zeitlauf
        return status_v1(resolved)
    _check_wait(resolved)
    _mount_pair(resolved, paths, password, "desktop_protection_password_wrong", count=True)
    _record_unreadable_check(resolved, paths)   # #568
    return status_v1(resolved)


def _mount_pair(resolved: Path, paths: dict[str, Path], password: str, wrong_code: str, count: bool) -> None:
    paths["root"].mkdir(mode=0o700, exist_ok=True)
    os.chmod(paths["root"], 0o700)
    _set_aside_strays(resolved, paths)
    if not _mounted(paths["data_mount"]):
        code = _mount(paths["data_cipher"], paths["data_mount"], password=password)
        if code == GOCRYPTFS_WRONG_PASSWORD:
            if count:
                _record_attempt(resolved, True)
            _abort(wrong_code)
        if code != 0:
            _abort("desktop_protection_mount_failed")
    if not _mounted(paths["backups_mount"]):
        code = _mount(paths["backups_cipher"], paths["backups_mount"], password=password)
        if code != 0:
            _unmount(paths["data_mount"])
            _abort("desktop_protection_mount_failed")
    if count:
        _record_attempt(resolved, False)
    _sleep_note_path(resolved).unlink(missing_ok=True)        # erst nach dem gelungenen Einhaengen; ueber den Schluesselbund kommt man mit Vermerk nicht hierher
    _run_opened_path(resolved).unlink(missing_ok=True)        # unlock_for_run_v1 setzt ihn danach selbst
    ensure_sleep_guard_v1(resolved)
    # Homes, die vor rc.401 eingerichtet wurden, tragen keinen Vermerk des bisherigen Orts; das Entsperren holt ihn nach. Ein Fehler hier
    # haelt das Entsperren nie auf - der Hinweis zum ungebundenen Datenraum (#556) nennt dann den Grund.
    try:
        _bind_mounted(resolved, paths["data_mount"])
    except Exception:  # noqa: BLE001
        pass


def _set_aside_strays(home: Path, paths: dict[str, Path]) -> None:
    """Liegt etwas im leeren Einhaengeordner (eine App schrieb, nachdem der Bestand weg war, #587), verweigerte gocryptfs das Einhaengen.
    Nie still loeschen: Der Ordner wandert als Ganzes in eine Quarantaene daneben (tmpfs, nur der Benutzer, nie auf die Platte), und die
    Einstellungen nennen, wie viele Dateien es sind."""
    folder, moved = None, 0
    for name in ("data_mount", "backups_mount"):
        mount = paths[name]
        if _mounted(mount) or _stale(mount) or mount.is_symlink() or not mount.is_dir():
            continue
        os.chmod(mount, 0o700)
        if not any(mount.iterdir()):
            continue
        if folder is None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            folder = paths["root"].with_name(f"{paths['root'].name}-quarantaene-{stamp}-{secrets.token_hex(3)}")
            folder.mkdir(mode=0o700)
        target = folder / mount.name
        mount.rename(target)
        moved += sum(1 for entry in target.rglob("*") if entry.is_file() and not entry.is_symlink())
    if folder is None:
        return
    note = home / STRAY_NOTE
    note.write_text(json.dumps({"file_count": moved, "folder": folder.name,
                                "at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n", encoding="utf-8")
    os.chmod(note, 0o600)


def _read_stray_note(home: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((home / STRAY_NOTE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) and isinstance(value.get("file_count"), int) else None


def _bind_mounted(home: Path, mount: Path) -> list[str]:
    """Entsperrt liegt der Datenbestand unter $XDG_RUNTIME_DIR, nicht mehr unter <home>/data. Fuenf Speicher binden den absoluten Pfad des
    Datenraums (#493); ohne Vermerk wiesen Bewertung, Wechselkurs-Abrufe, Sammelabruf und Kalender nach dem Einrichten ab (an einem
    Demo-Home gefunden, #487). Vermerkt wird der bisherige Ort (bzw. dessen eigener Ursprung) - nur nach Pruefung gegen die gespeicherten
    Bindungen. Der Einhaengepunkt ist je Home fest; der Vermerk gilt deshalb ueber Sperren, Entsperren und Erneuern hinweg."""
    from migrations.reference.data_space_relocation_v1 import (  # noqa: PLC0415
        DataSpaceRelocationV1Error, note_origin_v1, origin_v1, relocate_v1,
    )
    outcomes = []
    for space in sorted(mount.glob("*/*/*")):
        if not (space / "canonical.sqlite").is_file():
            continue
        plaintext = home / "data" / space.relative_to(mount)
        hint = origin_v1(plaintext) if plaintext.is_dir() else plaintext
        try:
            outcomes.append(relocate_v1(space, True, hints=[hint])["status"])
        except DataSpaceRelocationV1Error:
            outcomes.append("unverified")
            continue
        # Fuer den Notfall: Die Notiz geht mit ins (verschluesselte) Backup; der Restore findet den Ursprung darin.
        note_origin_v1(space)
    return outcomes


# ---------------------------------------------------------------------------------------------------------------------------
# Mit der Anmeldung entsperren (#553): das Passwort im Schluesselbund
# ---------------------------------------------------------------------------------------------------------------------------

def _keyring_attributes(home: Path) -> list[str]:
    """Abdruck des Home-Pfads statt des Pfads selbst - im Schluesselbund steht kein Ordnername."""
    return ["application", KEYRING_APPLICATION, "portelyra_protection", hashlib.sha256(str(home).encode("utf-8")).hexdigest()[:32]]


def _secret_tool() -> str | None:
    override = os.environ.get(KEYRING_TOOL_ENV)
    if override:
        return override if Path(override).is_file() else None
    return next((candidate for candidate in ("/usr/bin/secret-tool", "/usr/local/bin/secret-tool") if Path(candidate).is_file()), None)


def _keyring_run(arguments: list[str], payload: bytes | None = None) -> subprocess.CompletedProcess | None:
    tool = _secret_tool()
    if tool is None:
        return None
    try:
        return subprocess.run([tool, *arguments], input=payload, capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _keyring_store(home: Path, password: str) -> bool:
    done = _keyring_run(["store", f"--label={KEYRING_LABEL}", *_keyring_attributes(home)], password.encode("utf-8"))
    return done is not None and done.returncode == 0


def _keyring_lookup(home: Path) -> str | None:
    done = _keyring_run(["lookup", *_keyring_attributes(home)])
    if done is None or done.returncode != 0 or not done.stdout:
        return None
    try:
        return done.stdout.decode("utf-8")
    except UnicodeError:
        return None


def _keyring_clear(home: Path) -> None:
    _keyring_run(["clear", *_keyring_attributes(home)])


def _verify_password(resolved: Path, state: dict[str, Any], password: Any) -> None:
    """Passwort gegen den Pruefwert des Hauptschluessels; falsche Passwoerter zaehlen wie beim Entsperren."""
    if not isinstance(password, str) or not password:
        _abort("desktop_protection_input_invalid")
    _check_wait(resolved)
    result = subprocess.run([_tool("gocryptfs-xray"), "-dumpmasterkey", str(resolved / DATA_CIPHER / "gocryptfs.conf")], input=password.encode("utf-8"),
                            capture_output=True, timeout=60)
    key = result.stdout.decode("utf-8", "replace").strip().splitlines()[-1].strip() if result.returncode == 0 and result.stdout else ""
    if len(key.replace("-", "")) != 64 or _key_check(key) != state.get("master_key_check"):
        _record_attempt(resolved, True)
        _abort("desktop_protection_password_wrong")
    _record_attempt(resolved, False)


def unlock_from_keyring_v1(home: str | Path) -> dict[str, Any]:
    """Entsperren ohne Eingabe (Start, `unlock`, Zeitlauf): Passwort aus dem Schluesselbund. Fehlt der Eintrag, ist der Schluesselbund zu
    oder passt das Passwort nicht mehr, gilt die Startseite; ein Fehlschlag hier zaehlt nicht als falsche Eingabe. Ist ein Erneuern des
    Schluessels angefordert, entsperrt nur die Startseite - dort laeuft das Erneuern, bevor etwas anderes den Bestand oeffnet."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    paths = _paths(resolved, state)
    for mount in (paths["data_mount"], paths["backups_mount"]):
        if _stale(mount):
            _unmount(mount)
    if _mounted(paths["data_mount"]) and _mounted(paths["backups_mount"]):
        _run_opened_path(resolved).unlink(missing_ok=True)      # #587: App oder Benutzer uebernehmen den Bestand von einem Zeitlauf
        return status_v1(resolved)
    if state.get("rekey_requested"):
        _abort("desktop_protection_rekey_pending")
    if (_read_sleep_note(resolved) or {}).get("locked") is True:      # #587: nach dem Ruhezustand nur mit dem Passwort
        _abort("desktop_protection_password_after_sleep")
    if not state.get("keyring_unlock"):
        _abort("desktop_protection_keyring_unavailable")
    password = _keyring_lookup(resolved)
    if password is None:
        _abort("desktop_protection_keyring_unavailable")
    _mount_pair(resolved, paths, password, "desktop_protection_keyring_stale", count=False)
    _record_unreadable_check(resolved, paths)   # #568
    return status_v1(resolved)


def set_keyring_unlock_v1(home: str | Path, enabled: Any, password: Any = None) -> dict[str, Any]:
    """Mit der Anmeldung entsperren ein- (mit Passwort, das gegen den Hauptschluessel geprueft wird) oder ausschalten."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    if not isinstance(enabled, bool):
        _abort("desktop_protection_input_invalid")
    if enabled:
        _verify_password(resolved, state, password)
        if not _keyring_store(resolved, password):
            _abort("desktop_protection_keyring_unavailable")
    else:
        _keyring_clear(resolved)
    _write_state(resolved, {**state, "keyring_unlock": enabled})
    return status_v1(resolved)


def lock_v1(home: str | Path, wait_seconds: float = 10.0) -> dict[str, Any]:
    """Haengt beide Ordner aus. Ohne Schutz ohne Wirkung."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        return status_v1(resolved)
    paths = _paths(resolved, state)
    released = _unmount(paths["backups_mount"], wait_seconds) & _unmount(paths["data_mount"], wait_seconds)
    for mount in (paths["backups_mount"], paths["data_mount"]):
        try:
            mount.rmdir()
        except OSError:
            pass
    _seal_root(paths["root"], released)
    result = status_v1(resolved)
    if result.get("unlocked") is False:
        _run_opened_path(resolved).unlink(missing_ok=True)
    return result


def lock_if_due_v1(home: str | Path) -> dict[str, Any]:
    """Beim Beenden und am Ende eines Zeitlaufs (#587): Der Bestand bleibt offen, bis sich der Benutzer abmeldet. Gesperrt wird nur, wenn
    der Benutzer es eingestellt oder gerade angefordert hat oder ein Ablauf den gesperrten Bestand braucht: Erneuern des Schluessels und
    Quarantaene unlesbarer Eintraege laufen beim naechsten Start, und vor dem Entfernen des Klartexts fragt die Startseite das Passwort ab."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        return {**status_v1(resolved), "lock_due": False}
    due = bool(state.get("lock_on_quit") or state.get("rekey_requested") or not state.get("plaintext_removed")
               or (resolved / LOCK_REQUEST).is_file() or (resolved / UNREADABLE_REQUEST).is_file())
    if not due:
        return {**status_v1(resolved), "lock_due": False}
    result = lock_v1(resolved)
    if result.get("unlocked") is False:      # haelt noch ein Lauf eine Datei offen, bleibt die Anforderung fuer dessen Ende stehen
        (resolved / LOCK_REQUEST).unlink(missing_ok=True)
    return {**status_v1(resolved), "lock_due": True}


def _run_opened_path(home: Path) -> Path:
    """Vermerk "nur ein Zeitlauf hat geoeffnet" (#587). Liegt unter $XDG_RUNTIME_DIR und endet wie die Einhaengung mit der Abmeldung."""
    root = mount_root_v1(home)
    return root.with_name(root.name + ".run-opened")


def _other_run_active(home: Path) -> bool:
    """Laeuft ausser dem eigenen noch ein Lauf fuer dieses Home? Gefragt wird nach dem Prozess, nicht nach der Laufsperre: Ein zweiter
    Zeitplan wartet bis zu 30 Minuten auf sie, haelt sie also noch nicht, braucht den Bestand aber gleich."""
    parents = _process_parents()
    own: set[int] = set()
    pid = os.getpid()
    while pid in parents and pid not in own:
        own.add(pid)
        pid = parents[pid]
    target = os.path.realpath(home)
    for pid in parents:
        if pid in own:
            continue
        parts = _command_line(pid).split(b"\0")
        if any(part.endswith(b"desktop_refresh_all.R") for part in parts) and any(
                part == b"--home" and os.path.realpath(os.fsdecode(value)) == target for part, value in zip(parts, parts[1:])):
            return True
    return False


def unlock_for_run_v1(home: str | Path) -> dict[str, Any]:
    """Entsperren fuer einen Zeitlauf (#587): wie `unlock-keyring`, vermerkt aber, dass
    nur der Lauf geoeffnet hat. Sonst hielte "Jetzt sperren" nur bis zum naechsten Termin. War schon offen, bleibt alles, wie es ist."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    paths = _paths(resolved, state)
    for mount in (paths["data_mount"], paths["backups_mount"]):
        if _stale(mount):
            _unmount(mount)
    if _mounted(paths["data_mount"]) and _mounted(paths["backups_mount"]):
        return status_v1(resolved)
    result = unlock_from_keyring_v1(resolved)
    if result.get("unlocked") is True:
        _run_opened_path(resolved).touch(mode=0o600)
    return result


def keep_open_v1(home: str | Path) -> dict[str, Any]:
    """Portelyra wird gestartet (#587): Der Bestand gehoert jetzt dem Benutzer und bleibt offen, auch wenn ihn ein Zeitlauf geoeffnet hat."""
    resolved = _home(home)
    _run_opened_path(resolved).unlink(missing_ok=True)
    return status_v1(resolved)


def lock_after_run_v1(home: str | Path) -> dict[str, Any]:
    """Am Ende eines Laufs (#587): Sperrt, was nur ein Zeitlauf geoeffnet hat, und sonst, was faellig ist. Solange die App laeuft oder ein
    weiterer Lauf arbeitet oder wartet, bleibt offen; der letzte Lauf sperrt. Scheitert das Aushaengen, bleibt der Vermerk fuer den naechsten."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None or (resolved / "desktop-session.lock").exists() or _other_run_active(resolved):
        return {**status_v1(resolved), "lock_due": False}
    if not _run_opened_path(resolved).is_file():
        return lock_if_due_v1(resolved)
    if lock_v1(resolved).get("unlocked") is False:
        (resolved / LOCK_REQUEST).unlink(missing_ok=True)
    return {**status_v1(resolved), "lock_due": True}


def set_lock_on_quit_v1(home: str | Path, enabled: Any) -> dict[str, Any]:
    """Einstellung "Beim Beenden sperren" (#587); Vorgabe aus."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    if not isinstance(enabled, bool):
        _abort("desktop_protection_input_invalid")
    _write_state(resolved, {**state, "lock_on_quit": enabled})
    return status_v1(resolved)


def request_lock_v1(home: str | Path) -> dict[str, Any]:
    """"Jetzt sperren" (#587): gilt einmal. Portelyra beendet sich danach; gesperrt wird, sobald die Apps angehalten sind."""
    resolved = _home(home)
    if read_state_v1(resolved) is None:
        _abort("desktop_protection_not_enabled")
    path = resolved / LOCK_REQUEST
    path.write_text("{}\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return status_v1(resolved)


def clear_stray_note_v1(home: str | Path) -> dict[str, Any]:
    """Den Hinweis auf die Quarantaene ausblenden. Die Dateien bleiben liegen, bis der Benutzerdienst /run/user beim Abmelden raeumt."""
    resolved = _home(home)
    (resolved / STRAY_NOTE).unlink(missing_ok=True)
    return status_v1(resolved)


def seal_if_lost_v1(home: str | Path) -> dict[str, Any]:
    """Der Bestand ist weg, die Apps laufen noch (#587): den Einhaengeordner unbeschreibbar machen, damit jeder weitere Schreibvorgang laut
    scheitert, statt unbemerkt im Arbeitsspeicher zu landen. Das naechste Entsperren macht ihn wieder beschreibbar."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        return status_v1(resolved)
    paths = _paths(resolved, state)
    for mount in (paths["data_mount"], paths["backups_mount"]):
        try:
            if not _mounted(mount) and not _stale(mount) and mount.is_dir() and not mount.is_symlink():
                os.chmod(mount, 0o000)
        except OSError:          # schon versiegelt (Sperren vor dem Ruhezustand): der ganze Einhaengeordner ist zu
            pass
    return status_v1(resolved)


def _sleep_note_path(home: Path) -> Path:
    """Vor dem Ruhezustand gesperrt oder nicht (#587). Liegt wie der Zaehler der Fehlversuche unter $XDG_RUNTIME_DIR: Mit dem Abmelden ist
    er weg, und die naechste Anmeldung oeffnet den Schluesselbund wieder."""
    root = mount_root_v1(home)
    return root.with_name(root.name + ".sleep")


def _read_sleep_note(home: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(_sleep_note_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) and isinstance(value.get("locked"), bool) else None


def _write_sleep_note(home: Path, locked: bool) -> None:
    path = _sleep_note_path(home)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps({"locked": locked, "at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _process_parents() -> dict[int, int]:
    """Laufende Prozesse und ihre Eltern aus /proc; Zombies zaehlen als beendet."""
    parents: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text(encoding="utf-8", errors="replace").rsplit(") ", 1)[1].split()
        except (OSError, IndexError):
            continue
        if fields[0] != "Z":
            parents[int(entry.name)] = int(fields[1])
    return parents


def _command_line(pid: int) -> bytes:
    try:
        return (Path("/proc") / str(pid) / "cmdline").read_bytes()
    except OSError:
        return b""


def _work_in_progress(home: Path, paths: dict[str, Path]) -> bool:
    """Schreibt gerade etwas? Ein Lauf haelt die Laufsperre seines Datenraums; eine Buchung oder ein Import ist ein Kindprozess einer App
    (dieselbe Regel wie beim Beenden, `portelyra_stop_running`). Eine nicht lesbare Laufsperre zaehlt als Arbeit."""
    for lock in paths["data_mount"].glob("*/*/*/refresh-all-v1/lock"):
        try:
            if (Path("/proc") / str(int(json.loads((lock / "owner.json").read_text(encoding="utf-8"))["pid"]))).exists():
                return True
        except (OSError, ValueError, KeyError, TypeError):
            return True
    try:
        start = int(json.loads((home / "desktop-session.lock" / "owner.json").read_text(encoding="utf-8"))["pid"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    parents = _process_parents()
    if start not in parents:
        return False
    command = _command_line(start)
    apps = {pid for pid, parent in parents.items() if parent == start and _command_line(pid) == command}
    return any(parent in apps for parent in parents.values())


def catch_up_after_sleep_v1(home: str | Path, systemctl: Any = None) -> dict[str, Any]:
    """Holt einen Zeitlauf nach, der ausfiel, weil nach dem Ruhezustand das Passwort noch fehlte (#587). Einmal, auch wenn mehrere Termine ausfielen; "Alles aktualisieren" schliesst die Momentaufnahme ein. Nur solange
    der Zeitplan an ist: Er traegt die Zustimmung zum Abruf. Aufgerufen nach der Passworteingabe im Dialog und beim Start, nicht beim blossen
    Entsperren: Vor Backup und Upgrade (`update`) wuerde ein laufender Lauf diese sonst blockieren."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        return {"started": None}
    paths = _paths(resolved, state)
    marker = resolved / "protection-skipped.json"
    if not (_mounted(paths["data_mount"]) and _mounted(paths["backups_mount"])):
        return {"started": None}
    try:
        entries = json.loads(marker.read_text(encoding="utf-8")).get("skipped", [])
    except (OSError, ValueError, AttributeError):
        return {"started": None}
    if not isinstance(entries, list):
        return {"started": None}
    after_sleep = lambda row: isinstance(row, dict) and row.get("reason") == "desktop_protection_password_after_sleep"
    missed = {row.get("kind") for row in entries if after_sleep(row)}
    if not missed:
        return {"started": None}
    def real(arguments: list[str]) -> int:
        try:
            return subprocess.run(["systemctl", "--user", *arguments], capture_output=True, timeout=15, stdin=subprocess.DEVNULL).returncode
        except (OSError, subprocess.SubprocessError):
            return 1
    run = systemctl if callable(systemctl) else real
    stamp = mount_root_v1(resolved).name.removeprefix("portelyra-")[:8]      # wie data_refresh_all_schedule_v1: SHA-256 des Home-Pfads
    for kind, name in (("refresh", "refresh-all"), ("moment", "moment")):
        unit = f"portelyra-{name}-{stamp}"
        if kind not in missed or run(["is-enabled", "--quiet", f"{unit}.timer"]) != 0 or run(["start", "--no-block", f"{unit}.service"]) != 0:
            continue
        rest = [row for row in entries if not after_sleep(row)]
        if rest:
            temporary = marker.with_name(marker.name + ".partial")
            temporary.write_text(json.dumps({"skipped": rest}) + "\n", encoding="utf-8")
            os.chmod(temporary, 0o600)
            os.replace(temporary, marker)
        else:
            marker.unlink(missing_ok=True)
        return {"started": kind}
    return {"started": None}


def ensure_sleep_guard_v1(home: str | Path) -> bool:
    """Startet den Waechter fuer den Ruhezustand als eigene Einheit der Sitzung; laeuft er schon, weist systemd den zweiten ab. Ohne
    Benutzerdienst oder ohne gdbus (Container, Server) gibt es keinen Ruhezustand zu bewachen."""
    resolved = _home(home)
    if os.environ.get(SLEEP_GUARD_ENV) == "off" or read_state_v1(resolved) is None:
        return False
    tool, runtime = shutil.which("systemd-run"), os.environ.get("XDG_RUNTIME_DIR", "")
    if tool is None or not runtime or not (Path(runtime) / "systemd" / "private").exists() or not shutil.which("gdbus") or not shutil.which("systemd-inhibit"):
        return False
    unit = f"portelyra-sleep-guard-{mount_root_v1(resolved).name.removeprefix('portelyra-')}"
    script = Path(__file__).resolve().parents[2] / "scripts" / "desktop_protection.py"
    try:
        subprocess.run([tool, "--user", "--quiet", "--collect", f"--unit={unit}", sys.executable, "-B", "-E", "-s", str(script), "sleep-guard",
                        str(resolved)], capture_output=True, timeout=15, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def _stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _notify_not_locked() -> None:
    tool = shutil.which("notify-send")
    if tool:
        subprocess.run([tool, "--app-name=Portelyra", "Portelyra war im Ruhezustand nicht gesperrt",
                        "Beim Zuklappen lief gerade eine Buchung oder ein Lauf, den Portelyra nicht abbricht."], capture_output=True, timeout=10, check=False)


def sleep_guard_v1(home: str | Path, monitor_command: list[str] | None = None, inhibit_command: list[str] | None = None,
                   poll_seconds: float = 5.0, wait_seconds: float = 6.0) -> dict[str, Any]:
    """Sperrt vor dem Ruhezustand (#587, Festlegung 21.11.2026). Haelt dafuer eine Verzoegerung bei logind und hoert auf `PrepareForSleep`.
    Wird gerade geschrieben, bleibt der Bestand offen und der Benutzer erfaehrt es nach dem Aufwachen: Eine Buchung abzuschneiden waere
    schlimmer. Der Waechter endet, sobald der Bestand gesperrt ist; das naechste Entsperren startet ihn neu."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        return {"status": "not_enabled"}
    paths = _paths(resolved, state)
    monitor_command = monitor_command or ["gdbus", "monitor", "--system", "--dest", "org.freedesktop.login1", "--object-path", "/org/freedesktop/login1"]
    if inhibit_command is None:
        inhibit_command = ["systemd-inhibit", "--what=sleep", "--mode=delay", "--who=Portelyra", "--why=Bestand vor dem Ruhezustand sperren", "sleep", "infinity"]
    hold = lambda: subprocess.Popen(inhibit_command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    monitor = subprocess.Popen(monitor_command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    inhibitor = hold()                                     # erst lauschen, dann verzoegern: So geht kein Signal verloren
    selector = selectors.DefaultSelector()
    selector.register(monitor.stdout, selectors.EVENT_READ)
    buffer = b""
    try:
        while True:
            if not selector.select(poll_seconds):
                if not _mounted(paths["data_mount"]):
                    return {"status": "ended"}
                continue
            chunk = os.read(monitor.stdout.fileno(), 65536)
            if not chunk:
                return {"status": "monitor_ended"}
            buffer += chunk
            *lines, buffer = buffer.split(b"\n")
            for line in lines:
                if b"PrepareForSleep" not in line:
                    continue
                if b"(true" in line:
                    locked = False
                    if _mounted(paths["data_mount"]) and not _work_in_progress(resolved, paths):
                        locked = lock_v1(resolved, wait_seconds).get("unlocked") is False
                    _write_sleep_note(resolved, locked)
                    _stop_process(inhibitor)
                    inhibitor = None
                    if locked:
                        return {"status": "locked"}
                elif b"(false" in line:
                    if inhibitor is None:
                        inhibitor = hold()
                    if (_read_sleep_note(resolved) or {}).get("locked") is False:
                        _sleep_note_path(resolved).unlink(missing_ok=True)
                        _notify_not_locked()
    finally:
        selector.close()
        _stop_process(inhibitor)
        _stop_process(monitor)


def _seal_root(root: Path, released: bool) -> None:
    """Nach dem Aushaengen den leeren Einhaengeordner unbeschreibbar machen: Ein verirrter Schreibvorgang (ein Lauf, der nach dem Sperren
    noch etwas ablegt) scheitert dann laut, statt Klartext unter /run/user anzulegen. Entsperren macht ihn wieder
    beschreibbar."""
    if not released or not root.is_dir() or root.is_symlink():
        return
    try:
        if not any(root.iterdir()):
            os.chmod(root, 0o000)
    except OSError:
        pass


# ---------------------------------------------------------------------------------------------------------------------------
# Einrichten: Ordner anlegen, Klartext hineinkopieren und pruefen
# ---------------------------------------------------------------------------------------------------------------------------

def _check_new_password(password: Any, repeat: Any) -> str:
    if not isinstance(password, str) or not isinstance(repeat, str):
        _abort("desktop_protection_input_invalid")
    if len(password) < MIN_PASSWORD_LENGTH:
        _abort("desktop_protection_password_too_short", minimum=MIN_PASSWORD_LENGTH)
    if password != repeat:
        _abort("desktop_protection_password_mismatch")
    return password


def _master_key(conf: Path, password: str) -> str:
    result = subprocess.run([_tool("gocryptfs-xray"), "-dumpmasterkey", str(conf)], input=password.encode("utf-8"), capture_output=True,
                            timeout=60)
    key = result.stdout.decode("utf-8", "replace").strip().splitlines()[-1].strip() if result.returncode == 0 and result.stdout else ""
    if len(key.replace("-", "")) != 64:
        _abort("desktop_protection_state_invalid")
    return key


def format_recovery_key_v1(key: str) -> str:
    """Zum Aufschreiben: 64 Hexzeichen in acht Gruppen zu acht."""
    plain = key.replace("-", "").lower()
    return "-".join(plain[index:index + 8] for index in range(0, 64, 8))


def _init_pair(data_cipher: Path, backups_cipher: Path, password: str) -> None:
    """Datenordner mit gocryptfs anlegen; der Backup-Ordner bekommt dieselbe Schluesseldatei (ein Hauptschluessel fuer beide, Festlegung
    10.11.2026) und einen eigenen Zufallswert fuer die Namen."""
    if data_cipher.exists() and any(data_cipher.iterdir()):
        _abort("desktop_protection_already_enabled")
    # Ein alter verschluesselter Backup-Ordner (etwa nach einer Wiederherstellung in ein neues Home) bleibt unangetastet: Er oeffnet mit
    # dem alten Passwort oder Schluessel und darf nicht still ueberschrieben werden.
    if backups_cipher.exists() and any(backups_cipher.iterdir()):
        _abort("desktop_protection_backups_folder_exists")
    for cipher in (data_cipher, backups_cipher):
        cipher.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = subprocess.run([_tool("gocryptfs"), "-q", "-init", str(data_cipher)], input=password.encode("utf-8"), capture_output=True, timeout=120)
    if result.returncode != 0:
        _abort("desktop_protection_mount_failed")
    shutil.copy2(data_cipher / "gocryptfs.conf", backups_cipher / "gocryptfs.conf")
    (backups_cipher / "gocryptfs.diriv").write_bytes(os.urandom(16))
    os.chmod(backups_cipher / "gocryptfs.conf", 0o400)
    os.chmod(backups_cipher / "gocryptfs.diriv", 0o440)


def _digest_tree(root: Path) -> dict[str, str]:
    """Je Datei (relativ) die SHA-256 - fuer den Vergleich von Klartext und verschluesselter Kopie."""
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            result[str(path.relative_to(root))] = "symlink:" + os.readlink(path)
        elif path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
            result[str(path.relative_to(root))] = digest.hexdigest()
    return result


def _copy_tree(source: Path, target: Path) -> None:
    """Kopiert mit Rechten und Zeiten; Verknuepfungen bleiben Verknuepfungen."""
    for path in sorted(source.rglob("*")):
        destination = target / path.relative_to(source)
        if path.is_symlink():
            os.symlink(os.readlink(path), destination)
        elif path.is_dir():
            destination.mkdir(mode=stat.S_IMODE(path.stat().st_mode), exist_ok=True)
        else:
            shutil.copy2(path, destination)
    for path in sorted(source.rglob("*"), reverse=True):
        if path.is_dir() and not path.is_symlink():
            shutil.copystat(path, target / path.relative_to(source))


def enable_v1(home: str | Path, password: Any, repeat: Any, confirmed: Any, *, backups_source: str | Path | None = None,
              backups_cipher: str | Path | None = None, keyring: Any = False) -> dict[str, Any]:
    """Schaltet den Schutz ein: legt beide Ordner an, haengt sie ein, kopiert den Datenbestand (und vorhandene Backups) hinein und prueft
    jede Datei gegen den Klartext. Erst dann gilt der Schutz (``protection.json``). Der Klartext bleibt bis ``finalize_v1``. Das Ergebnis
    nennt den Wiederherstellungsschluessel genau einmal; Portelyra speichert ihn nicht. Laufen darf dabei nichts, das schreibt - die Data-App
    beendet sich danach und startet mit der Startseite zum Entsperren."""
    resolved = _home(home)
    if confirmed is not True:
        _abort("desktop_protection_confirmation_required")
    if read_state_v1(resolved) is not None:
        _abort("desktop_protection_already_enabled")
    password = _check_new_password(password, repeat)
    _tool("gocryptfs"); _tool("gocryptfs-xray"); _tool("fusermount")
    plaintext = resolved / "data"
    if not plaintext.is_dir():
        _abort("desktop_protection_input_invalid")
    # Ohne Datenraum gaebe es nichts zu sichern: Das erste Backup nach dem Einrichten schluege fehl und der Klartext liesse sich nie
    # entfernen. Die Data-App legt den Datenraum beim ersten Oeffnen an.
    if not any(path.is_file() for path in plaintext.glob("*/*/*/canonical.sqlite")):
        _abort("desktop_protection_no_data_space")
    cipher = Path(backups_cipher) if backups_cipher else _default_backups_cipher()
    paths = {"data_cipher": resolved / DATA_CIPHER, "backups_cipher": cipher, "root": mount_root_v1(resolved)}
    paths["data_mount"], paths["backups_mount"] = paths["root"] / "data", paths["root"] / "backups"
    if _mounted(paths["data_mount"]) or _mounted(paths["backups_mount"]):
        _abort("desktop_protection_busy")
    _init_pair(paths["data_cipher"], paths["backups_cipher"], password)
    key = _master_key(paths["data_cipher"] / "gocryptfs.conf", password)
    paths["root"].mkdir(mode=0o700, exist_ok=True)
    os.chmod(paths["root"], 0o700)
    try:
        for name in ("data", "backups"):
            if _mount(paths[f"{name}_cipher"], paths[f"{name}_mount"], password=password) != 0:
                _abort("desktop_protection_mount_failed")
        before = _digest_tree(plaintext)
        _copy_tree(plaintext, paths["data_mount"])
        if _digest_tree(paths["data_mount"]) != before or _digest_tree(plaintext) != before:
            _abort("desktop_protection_copy_mismatch")
        # Der neue Ort des Bestands (#487): Ursprung vermerken, sonst wiesen die pfadgebundenen Speicher ab. War der Klartext selbst nicht
        # gebunden (etwa eine Handkopie), bleibt es dabei - der Schutz macht nichts schlechter.
        try:
            relocation = _bind_mounted(resolved, paths["data_mount"])
        except Exception:  # noqa: BLE001 - das Einrichten haengt nicht daran; der Hinweis (#556) nennt dann den Grund
            relocation = ["not_possible"]
        copied_backups = 0
        if backups_source is not None and Path(backups_source).is_dir():
            source = Path(backups_source)
            expected = _digest_tree(source)
            _copy_tree(source, paths["backups_mount"])
            if _digest_tree(paths["backups_mount"]) != expected:
                _abort("desktop_protection_copy_mismatch")
            copied_backups = len(expected)
        # Fingerabdruck des Klartexts zum Zeitpunkt der Kopie: finalize loescht nur, wenn danach nichts mehr hineingeschrieben wurde.
        _write_state(resolved, {"contract_version": CONTRACT, "enabled": True, "data_cipher": DATA_CIPHER, "backups_cipher": str(cipher),
                                "created_at_utc": _now(), "plaintext_removed": False, "master_key_check": _key_check(key),
                                "plaintext_fingerprint": hashlib.sha256(json.dumps(before, sort_keys=True).encode("utf-8")).hexdigest(),
                                "plaintext_backups": str(backups_source) if backups_source is not None else None})
    except DesktopProtectionV1Error:
        _unmount(paths["backups_mount"]); _unmount(paths["data_mount"])
        raise
    # Mit der Anmeldung entsperren (#553): gelingt das Ablegen im Schluesselbund nicht, bleibt der Schutz an, nur ohne diese Erleichterung.
    stored = keyring is True and _keyring_store(resolved, password)
    if stored:
        _write_state(resolved, {**read_state_v1(resolved), "keyring_unlock": True})
    return {"contract_version": "desktop_protection_enable_result_v1", "status": "enabled", "recovery_key": format_recovery_key_v1(key),
            "file_count": len(before), "backup_file_count": copied_backups, "mount_root": str(paths["root"]),
            "keyring_unlock": stored, "keyring_failed": keyring is True and not stored, "relocation": relocation}


def finalize_v1(home: str | Path, confirmed: Any, accept_difference: Any = False) -> dict[str, Any]:
    """Loescht den Klartext (``<home>/data`` und die uebernommenen Backups), erst nach erneuter Pruefung gegen die entsperrte, verschluesselte
    Kopie und wenn dort mindestens ein Backup liegt, das nach dem Einschalten entstand. Auf SSDs koennen Reste bleiben; das deckt die
    Festplattenverschluesselung ab (Hinweis in der Oberflaeche).

    Wurde zwischen Einrichten und Neustart noch in den Klartext geschrieben (etwa ein Zeitlauf), meldet der Abbruch, wie viele Dateien
    seitdem geaendert wurden und wann zuletzt. Portelyra arbeitet seit dem Neustart mit dem verschluesselten Stand; nur auf ausdrueckliche
    Bestaetigung (`accept_difference`) wird der Klartext dann trotzdem geloescht."""
    resolved = _home(home)
    if confirmed is not True:
        _abort("desktop_protection_confirmation_required")
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    paths = _paths(resolved, state)
    if not (_mounted(paths["data_mount"]) and _mounted(paths["backups_mount"])):
        _abort("desktop_protection_locked")
    if not _fresh_backups(paths["backups_mount"], state.get("created_at_utc") or ""):
        _abort("desktop_protection_backup_required")
    plaintext = resolved / "data"
    removed = 0
    if plaintext.exists():
        # Wurde nach dem Einrichten noch in den Klartext geschrieben, fehlte das in der verschluesselten Kopie: dann nichts loeschen.
        current = hashlib.sha256(json.dumps(_digest_tree(plaintext), sort_keys=True).encode("utf-8")).hexdigest()
        if current != state.get("plaintext_fingerprint") and accept_difference is not True:
            # Der Zeitpunkt des Einrichtens ist sekundengenau gespeichert; gezaehlt wird ab der folgenden Sekunde. Sonst zaehlte eine Datei mit,
            # die in derselben Sekunde noch vor dem Einrichten geschrieben wurde (der Vertragstest war dadurch zeitweise rot). Die Zahl ist nur
            # ein Hinweis; ob geloescht wird, entscheidet der Pruefwert.
            since = datetime.fromisoformat(str(state.get("created_at_utc") or "1970-01-01T00:00:00+00:00").replace("Z", "+00:00")).timestamp() + 1
            newer = [path.stat().st_mtime for path in plaintext.rglob("*") if path.is_file() and not path.is_symlink() and path.stat().st_mtime >= since]
            _abort("desktop_protection_copy_mismatch", changed_count=len(newer),
                   newest_utc=datetime.fromtimestamp(max(newer), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if newer else None)
        removed += sum(1 for _ in plaintext.rglob("*"))
        shutil.rmtree(plaintext)
    old = state.get("plaintext_backups")
    if isinstance(old, str) and Path(old).is_dir() and Path(old).resolve() != paths["backups_mount"].resolve():
        removed += sum(1 for _ in Path(old).rglob("*"))
        shutil.rmtree(old)
    _write_state(resolved, {**state, "plaintext_removed": True, "plaintext_removed_at_utc": _now()})
    return {"contract_version": "desktop_protection_finalize_result_v1", "status": "plaintext_removed", "removed_entry_count": removed}


# ---------------------------------------------------------------------------------------------------------------------------
# Passwort aendern und Wiederherstellen
# ---------------------------------------------------------------------------------------------------------------------------

def _passwd(cipher: Path, payload: str, extra: list[str]) -> int:
    result = subprocess.run([_tool("gocryptfs"), "-passwd", *extra, str(cipher)], input=payload.encode("utf-8"), capture_output=True, timeout=120)
    if result.returncode == 0:
        # gocryptfs legt die alte Konfiguration als .bak ab; sie oeffnet weiter mit dem alten Passwort. Wer das Passwort aendert, weil
        # es bekannt wurde, will genau das nicht.
        (cipher / "gocryptfs.conf.bak").unlink(missing_ok=True)
    return result.returncode


def _key_check(key: str) -> str:
    """Pruefwert des Hauptschluessels: gocryptfs prueft beim Neusetzen des Passworts mit dem Schluessel nicht, ob er stimmt, und schriebe
    einen vertippten Schluessel still in die Konfiguration - die Daten waeren dann unlesbar. Der Schluessel hat 256 Bit Zufall; sein
    Hashwert verraet nichts Verwertbares."""
    return hashlib.sha256(("portelyra-desktop-protection-v1:" + key.replace("-", "").lower()).encode("ascii")).hexdigest()


def change_password_v1(home: str | Path, old: Any, new: Any, repeat: Any) -> dict[str, Any]:
    """Neues Passwort fuer beide Ordner; der Hauptschluessel (und damit der Wiederherstellungsschluessel) bleibt."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    if not isinstance(old, str) or not old:
        _abort("desktop_protection_input_invalid")
    new = _check_new_password(new, repeat)
    paths = _paths(resolved, state)
    _check_wait(resolved)
    for index, cipher in enumerate((paths["data_cipher"], paths["backups_cipher"])):
        code = _passwd(cipher, f"{old}\n{new}\n{new}\n", [])
        if code == GOCRYPTFS_WRONG_PASSWORD and index == 0:
            _record_attempt(resolved, True)
            _abort("desktop_protection_password_wrong")
        if code != 0:
            _abort("desktop_protection_state_invalid")
    _record_attempt(resolved, False)
    return {"contract_version": "desktop_protection_password_result_v1", "status": "changed", **_keyring_follow(resolved, state, new)}


def _keyring_follow(resolved: Path, state: dict[str, Any], password: str) -> dict[str, Any]:
    """Neues Passwort auch im Schluesselbund (#553); misslingt das, ist "Mit der Anmeldung entsperren" aus statt veraltet."""
    if not state.get("keyring_unlock"):
        return {"keyring_updated": None}
    if _keyring_store(resolved, password):
        return {"keyring_updated": True}
    _keyring_clear(resolved)
    _write_state(resolved, {**read_state_v1(resolved), "keyring_unlock": False})
    return {"keyring_updated": False}


def recover_v1(home: str | Path, recovery_key: Any, new: Any, repeat: Any) -> dict[str, Any]:
    """Passwort vergessen: Mit dem Wiederherstellungsschluessel ein neues Passwort fuer beide Ordner setzen."""
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    plain = recovery_key.replace("-", "").replace(" ", "").lower() if isinstance(recovery_key, str) else ""
    if len(plain) != 64 or any(c not in "0123456789abcdef" for c in plain):
        _abort("desktop_protection_recovery_key_invalid")
    new = _check_new_password(new, repeat)
    _check_wait(resolved)
    # Erst gegen den Pruefwert vom Einrichten: gocryptfs selbst prueft den Schluessel nicht (siehe _key_check). Falsche Schluessel zaehlen
    # wie falsche Passwoerter.
    if not isinstance(state.get("master_key_check"), str) or state["master_key_check"] != _key_check(plain):
        _record_attempt(resolved, True)
        _abort("desktop_protection_recovery_key_invalid")
    paths = _paths(resolved, state)
    for cipher in (paths["data_cipher"], paths["backups_cipher"]):
        # Schluessel und neues Passwort nur ueber stdin; auf der Kommandozeile waere der Schluessel fuer andere Benutzer lesbar.
        if _passwd(cipher, f"{plain}\n{new}\n{new}\n", ["-masterkey=stdin"]) != 0:
            _abort("desktop_protection_state_invalid")
    _record_attempt(resolved, False)
    return {"contract_version": "desktop_protection_password_result_v1", "status": "recovered", **_keyring_follow(resolved, state, new)}


# ---------------------------------------------------------------------------------------------------------------------------
# Schluessel erneuern (#552): neuer Hauptschluessel, alles neu verschluesselt
# ---------------------------------------------------------------------------------------------------------------------------

def request_rekey_v1(home: str | Path, confirmed: Any) -> dict[str, Any]:
    """In der Karte angestossen: Beim naechsten Start erneuert die Startseite den Schluessel, bevor etwas anderes den Bestand oeffnet. Bis
    dahin entsperrt der Schluesselbund nicht von selbst."""
    resolved = _home(home)
    if confirmed is not True:
        _abort("desktop_protection_confirmation_required")
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    _write_state(resolved, {**state, "rekey_requested": True})
    return status_v1(resolved)


def cancel_rekey_v1(home: str | Path) -> dict[str, Any]:
    resolved = _home(home)
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    if state.get("rekey_requested"):
        _write_state(resolved, {**state, "rekey_requested": False})
    return status_v1(resolved)


def _tree_bytes(root: Path) -> int:
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file() and not path.is_symlink())


def rekey_v1(home: str | Path, current: Any, new: Any, repeat: Any, confirmed: Any) -> dict[str, Any]:
    """Neuer Hauptschluessel fuer Daten und Backups. Laeuft gesperrt (die Startseite vor den Apps): alte Ordner mit dem jetzigen Passwort an
    eigenen Einhaengepunkten, neue Ordner mit dem neuen Passwort, alles kopieren und jede Datei pruefen, erst dann tauschen. Die alten
    Ordner bleiben als ".alt-<Zeit>" liegen, bis nach einem Backup in den neuen bewusst entfernt (remove_old_ciphers_v1). Das neue Passwort
    darf das alte sein (Festlegung 11.11.2026). Das Ergebnis nennt den neuen Wiederherstellungsschluessel genau einmal."""
    resolved = _home(home)
    if confirmed is not True:
        _abort("desktop_protection_confirmation_required")
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    new = _check_new_password(new, repeat)
    paths = _paths(resolved, state)
    if _mounted(paths["data_mount"]) or _mounted(paths["backups_mount"]):
        _abort("desktop_protection_busy")
    if state.get("old_ciphers"):
        _abort("desktop_protection_busy", reason="old_ciphers_pending")
    _verify_password(resolved, state, current)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    fresh = {"data": resolved / f"{DATA_CIPHER}.new-{stamp}", "backups": paths["backups_cipher"].with_name(paths["backups_cipher"].name + f".new-{stamp}")}
    # Platz: zeitweise liegen alte und neue Ordner nebeneinander (je Dateisystem gerechnet, mit Reserve).
    for name in ("data", "backups"):
        needed = int(_tree_bytes(paths[f"{name}_cipher"]) * 1.05) + 200 * 1024 * 1024
        free = shutil.disk_usage(fresh[name].parent).free
        if free < needed:
            _abort("desktop_protection_disk_space", needed_bytes=needed, free_bytes=free)
    work = mount_root_v1(resolved).with_name(mount_root_v1(resolved).name + "-rekey")
    mounts = {key: work / key for key in ("old_data", "old_backups", "new_data", "new_backups")}
    try:
        _init_pair(fresh["data"], fresh["backups"], new)
        key = _master_key(fresh["data"] / "gocryptfs.conf", new)
        work.mkdir(mode=0o700, exist_ok=True)
        for name in ("data", "backups"):
            if _mount(paths[f"{name}_cipher"], mounts[f"old_{name}"], password=current) != 0 or _mount(fresh[name], mounts[f"new_{name}"], password=new) != 0:
                _abort("desktop_protection_mount_failed")
        counts = {}
        for name in ("data", "backups"):
            before = _digest_tree(mounts[f"old_{name}"])
            _copy_tree(mounts[f"old_{name}"], mounts[f"new_{name}"])
            if _digest_tree(mounts[f"new_{name}"]) != before or _digest_tree(mounts[f"old_{name}"]) != before:
                _abort("desktop_protection_copy_mismatch")
            counts[name] = len(before)
    except DesktopProtectionV1Error:
        for mount in mounts.values():
            _unmount(mount)
        for cipher in fresh.values():
            shutil.rmtree(cipher, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
        raise
    for mount in mounts.values():
        _unmount(mount)
    shutil.rmtree(work, ignore_errors=True)
    # Tauschen: erst Daten, dann Backups; scheitert das zweite, wird das erste zurueckgetauscht.
    old = {name: paths[f"{name}_cipher"].with_name(paths[f"{name}_cipher"].name + f".alt-{stamp}") for name in ("data", "backups")}
    os.replace(paths["data_cipher"], old["data"])
    os.replace(fresh["data"], paths["data_cipher"])
    try:
        os.replace(paths["backups_cipher"], old["backups"])
        os.replace(fresh["backups"], paths["backups_cipher"])
    except OSError:
        os.replace(paths["data_cipher"], fresh["data"])
        os.replace(old["data"], paths["data_cipher"])
        if old["backups"].exists() and not paths["backups_cipher"].exists():
            os.replace(old["backups"], paths["backups_cipher"])
        shutil.rmtree(fresh["data"], ignore_errors=True); shutil.rmtree(fresh["backups"], ignore_errors=True)
        _abort("desktop_protection_state_invalid")
    _write_state(resolved, {**state, "master_key_check": _key_check(key), "rekeyed_at_utc": _now(), "rekey_requested": False,
                            "old_ciphers": [str(old["data"]), str(old["backups"])]})
    follow = _keyring_follow(resolved, state, new)
    return {"contract_version": "desktop_protection_rekey_result_v1", "status": "rekeyed", "recovery_key": format_recovery_key_v1(key),
            "file_count": counts["data"], "backup_file_count": counts["backups"], **follow}


def remove_old_ciphers_v1(home: str | Path, confirmed: Any) -> dict[str, Any]:
    """Nach dem Erneuern: die alten verschluesselten Ordner loeschen - erst, wenn im neuen Backup-Ordner ein Backup liegt, das danach
    entstand. Aeltere Kopien der alten Ordner (etwa in einer Sicherung) bleiben mit dem alten Passwort lesbar, bis sie dort geloescht sind."""
    resolved = _home(home)
    if confirmed is not True:
        _abort("desktop_protection_confirmation_required")
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    paths = _paths(resolved, state)
    if not (_mounted(paths["data_mount"]) and _mounted(paths["backups_mount"])):
        _abort("desktop_protection_locked")
    if not _fresh_backups(paths["backups_mount"], _backup_reference(state)):
        _abort("desktop_protection_backup_required")
    removed = 0
    allowed = {paths["data_cipher"].parent.resolve(), paths["backups_cipher"].parent.resolve()}
    for value in state.get("old_ciphers") or []:
        old = Path(value)
        # Nur, was das Erneuern selbst angelegt hat: ein Geschwister der geltenden Ordner mit ".alt-" im Namen.
        if ".alt-" not in old.name or old.parent.resolve() not in allowed or old.is_symlink():
            _abort("desktop_protection_state_invalid")
        if old.is_dir():
            removed += sum(1 for _ in old.rglob("*"))
            shutil.rmtree(old)
    _write_state(resolved, {**state, "old_ciphers": [], "old_ciphers_removed_at_utc": _now()})
    return {"contract_version": "desktop_protection_old_ciphers_result_v1", "status": "old_ciphers_removed", "removed_entry_count": removed}


# ---------------------------------------------------------------------------------------------------------------------------
# Unlesbare Eintraege (#568): Pruefung nach dem Entsperren, Vorschau, bestaetigter Auftrag, Quarantaene beim naechsten Start
# ---------------------------------------------------------------------------------------------------------------------------
# Nach einem harten Ausschalten kann ein gerade angelegter Ordner eine leere gocryptfs.diriv haben: Er ist unlesbar (EIO), und jedes Backup bricht ab. Klartext und Chiffrat tragen dieselbe Inode-Nummer (gocryptfs reicht sie durch); der unlesbare
# Ordner laesst sich noch mit lstat ansprechen. So findet die Vorschau zu jedem unlesbaren Klartext-Ordner genau seinen verschluesselten.
# Verschoben wird nur ein abgeleiteter Lauf eines veroeffentlichten Bereichs (artifacts/<bereich>/runs|incoming/run_...), nur auf
# Bestaetigung und nur gesperrt - beim naechsten Start, bevor entsperrt wird. Er geht verschluesselt in <home>/quarantaene-<datum>/
# (umkehrbar, nichts wird geloescht). Primaerdaten nie.
UNREADABLE_CHECK = "unreadable-check.json"
UNREADABLE_REQUEST = "unreadable-quarantine-request.json"
DIRIV = "gocryptfs.diriv"
_DERIVED_RUN = re.compile(r"^artifacts/([a-z][a-z0-9_]{0,63})/(runs|incoming)/(run_[A-Za-z0-9_]{1,96})$")
# Zwischenordner, die nie zum gueltigen Stand gehoeren: eine Buchung entsteht in generations/.staging-* und wird erst gueltig, wenn der
# Ordner umbenannt ist und active.json darauf zeigt; eine Steuermodul-Installation kopiert erst nach .kopie-*. Ein beim Ausschalten
# liegengebliebener enthaelt nur den Vorgang, der gerade lief - der gueltige Stand ist unveraendert.
_LEFTOVER_STAGING = re.compile(r"^(asset-activity-ledger-v1)/generations/\.staging-[A-Za-z0-9_-]{1,96}$"
                               r"|^(tax-model-plugins-v1)/[a-z][a-z0-9_]{0,80}/\.kopie-[A-Za-z0-9_]{1,96}$")
_QUARANTINE_FOLDER = re.compile(r"^quarantaene-[0-9]{8}(-[0-9]{1,3})?$")
_CONTEXT_ID = re.compile(r"^[a-z]{3}_[A-Za-z0-9_]{1,96}$")


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _read_unreadable_check(home: Path) -> dict[str, Any] | None:
    try:
        value = json.loads((home / UNREADABLE_CHECK).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    count = value.get("damaged_directory_count") if isinstance(value, dict) else None
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return None
    return {"damaged_directory_count": count, "checked_at_utc": value.get("checked_at_utc")}


def damaged_cipher_directories_v1(cipher: Path) -> list[dict[str, Any]]:
    """Ordner im verschluesselten Datenbestand mit leerer gocryptfs.diriv. Liest nur Groessen und Inode-Nummern, entschluesselt nichts."""
    found: list[dict[str, Any]] = []
    root = str(cipher)
    for directory, _subdirs, files in os.walk(root):
        if DIRIV not in files:
            continue
        try:
            if os.lstat(os.path.join(directory, DIRIV)).st_size == 0:
                found.append({"cipher_relative": os.path.relpath(directory, root), "inode": os.lstat(directory).st_ino})
        except OSError:
            continue
    return sorted(found, key=lambda row: row["cipher_relative"])


def _record_unreadable_check(home: Path, paths: dict[str, Path]) -> None:
    """Nach jedem Entsperren: wie viele Ordner unlesbar sind. Ein Fehler hier haelt das Entsperren nie auf."""
    try:
        damaged = damaged_cipher_directories_v1(paths["data_cipher"])
        _write_private_json(home / UNREADABLE_CHECK, {"checked_at_utc": _now(), "damaged_directory_count": len(damaged)})
    except Exception:
        pass


def _active_space(home: Path, data_mount: Path) -> Path:
    try:
        registry = json.loads((home / "desktop-runtime.json").read_text(encoding="utf-8"))
        parts = [registry["tenant_id"], registry["user_id"], registry["active_data_space_id"]]
    except (OSError, ValueError, KeyError, TypeError):
        _abort("desktop_protection_no_data_space")
    if not all(isinstance(part, str) and _CONTEXT_ID.match(part) for part in parts):
        _abort("desktop_protection_no_data_space")
    return data_mount.joinpath(*parts)


def _unreadable_directories(space: Path) -> list[tuple[str, int]]:
    """Klartext-Ordner, deren Inhalt sich nicht lesen laesst: (Pfad relativ zum Datenraum, Inode-Nummer). Steigt nicht in sie hinab."""
    found: list[tuple[str, int]] = []
    pending = [space]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                children = list(iterator)
        except FileNotFoundError:
            continue
        except OSError:
            try:
                inode = os.lstat(directory).st_ino
            except OSError:
                inode = -1
            found.append(("." if directory == space else directory.relative_to(space).as_posix(), inode))
            continue
        for child in children:
            try:
                if child.is_dir(follow_symlinks=False):
                    pending.append(Path(child.path))
            except OSError:
                pending.append(Path(child.path))   # scandir meldet ihn dann selbst
    return sorted(found)


def _unreadable_rows(resolved: Path) -> tuple[list[dict[str, Any]], int]:
    state = read_state_v1(resolved)
    if state is None:
        _abort("desktop_protection_not_enabled")
    paths = _paths(resolved, state)
    if not _mounted(paths["data_mount"]):
        _abort("desktop_protection_locked")
    space = _active_space(resolved, paths["data_mount"])
    damaged_rows = damaged_cipher_directories_v1(paths["data_cipher"])
    damaged = {row["inode"]: row["cipher_relative"] for row in damaged_rows}
    rows: list[dict[str, Any]] = []
    for relative, inode in _unreadable_directories(space):
        match = _DERIVED_RUN.match(relative)
        leftover = _LEFTOVER_STAGING.match(relative)
        cipher_relative = damaged.get(inode)
        latest = False
        if match and match.group(2) == "runs":
            try:
                latest = json.loads((space / "artifacts" / match.group(1) / "latest.json").read_text(encoding="utf-8")).get("run_id") == match.group(3)
            except (OSError, ValueError, AttributeError):
                latest = False
        kind = "derived_run" if match else "leftover_staging" if leftover else "other"
        area = match.group(1) if match else (leftover.group(1) or leftover.group(2)) if leftover else None
        rows.append({"relative_path": relative, "area": area, "kind": kind, "latest": latest,
                     "quarantinable": kind != "other" and cipher_relative is not None, "cipher_relative": cipher_relative, "inode": inode})
    return rows, len(damaged_rows)


def _rows_fingerprint(rows: list[dict[str, Any]]) -> str:
    basis = [[row["relative_path"], row["cipher_relative"], row["inode"], row["latest"]] for row in rows]
    return hashlib.sha256(json.dumps(basis, separators=(",", ":")).encode("utf-8")).hexdigest()


def unreadable_preview_v1(home: str | Path) -> dict[str, Any]:
    """Welche Eintraege des Datenraums unlesbar sind, ob Portelyra sie in Quarantaene nehmen kann und ob latest.json auf sie zeigt.
    Nur lesend (bis auf das Pruefergebnis); braucht den entsperrten Bestand."""
    resolved = _home(home)
    rows, damaged_count = _unreadable_rows(resolved)
    try:
        _write_private_json(resolved / UNREADABLE_CHECK, {"checked_at_utc": _now(), "damaged_directory_count": damaged_count})
    except OSError:
        pass
    shown = [{key: row[key] for key in ("relative_path", "area", "kind", "latest", "quarantinable")} for row in rows]
    return {"contract_version": CONTRACT, "entries": shown, "damaged_directory_count": damaged_count,
            "quarantinable": bool(rows) and all(row["quarantinable"] for row in rows),
            "requested": (resolved / UNREADABLE_REQUEST).is_file(), "preview_fingerprint": _rows_fingerprint(rows)}


def _quarantine_folder(home: Path, day: str) -> Path:
    for suffix in [""] + [f"-{number}" for number in range(2, 100)]:
        folder = home / f"quarantaene-{day}{suffix}"
        if not folder.exists():
            folder.mkdir(mode=0o700)
            return folder
        if folder.is_dir() and not folder.is_symlink():
            return folder
    _abort("desktop_protection_state_invalid")


def unreadable_request_v1(home: str | Path, preview_fingerprint: Any, confirmed: Any) -> dict[str, Any]:
    """Bestaetigt genau die gezeigte Vorschau: Auftrag fuer den naechsten Start. Zeigt latest.json eines Bereichs auf einen dieser Laeufe,
    wird es jetzt in die Quarantaene kopiert und entfernt - der Bereich gilt dann als noch nicht veroeffentlicht, der naechste Lauf
    schreibt ihn neu. Der unlesbare Ordner selbst wird erst beim naechsten Start verschoben (gesperrt)."""
    resolved = _home(home)
    if confirmed is not True:
        _abort("desktop_protection_confirmation_required")
    rows, _damaged = _unreadable_rows(resolved)
    if not isinstance(preview_fingerprint, str) or preview_fingerprint != _rows_fingerprint(rows):
        _abort("desktop_protection_unreadable_stale")
    if not rows:
        _abort("desktop_protection_unreadable_none")
    if not all(row["quarantinable"] for row in rows):
        _abort("desktop_protection_unreadable_not_quarantinable")
    folder = _quarantine_folder(resolved, datetime.now(timezone.utc).strftime("%Y%m%d"))
    paths = _paths(resolved, read_state_v1(resolved))
    space = _active_space(resolved, paths["data_mount"])
    removed: list[str] = []
    for row in rows:
        if not row["latest"]:
            continue
        latest = space / "artifacts" / row["area"] / "latest.json"
        (folder / f"latest-{row['area']}.json").write_bytes(latest.read_bytes())
        os.chmod(folder / f"latest-{row['area']}.json", 0o600)
        latest.unlink()
        descriptor = os.open(latest.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        removed.append(row["area"])
    _write_private_json(resolved / UNREADABLE_REQUEST, {
        "contract_version": CONTRACT, "requested_at_utc": _now(), "folder": folder.name, "preview_fingerprint": preview_fingerprint,
        "entries": [{"relative_path": row["relative_path"], "cipher_relative": row["cipher_relative"], "inode": row["inode"]} for row in rows]})
    return {"status": "requested", "entry_count": len(rows), "latest_removed": removed, "folder": folder.name}


def unreadable_execute_v1(home: str | Path) -> dict[str, Any]:
    """Beim Start, solange gesperrt: verschiebt genau die bestaetigten verschluesselten Ordner in die Quarantaene, wenn Inode-Nummer und
    leere gocryptfs.diriv noch stimmen. Ohne Auftrag nichts. Danach ist der Auftrag erledigt; die Pruefung laeuft beim Entsperren neu."""
    resolved = _home(home)
    request_path = resolved / UNREADABLE_REQUEST
    state = read_state_v1(resolved)
    if state is None or not request_path.is_file() or request_path.is_symlink():
        return {"status": "nothing_requested"}
    paths = _paths(resolved, state)
    if _mounted(paths["data_mount"]):
        _abort("desktop_protection_busy")
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        folder_name, entries = request["folder"], request["entries"]
        if not isinstance(folder_name, str) or not _QUARANTINE_FOLDER.match(folder_name) or not isinstance(entries, list) or not entries:
            raise ValueError("request")
    except (OSError, ValueError, KeyError, TypeError):
        request_path.unlink(missing_ok=True)
        _abort("desktop_protection_unreadable_request_invalid")
    folder = resolved / folder_name
    folder.mkdir(mode=0o700, exist_ok=True)
    cipher = paths["data_cipher"].resolve()
    moved: list[str] = []
    skipped: list[str] = []
    notes: list[str] = []
    for entry in entries:
        relative = entry.get("cipher_relative") if isinstance(entry, dict) else None
        shown = entry.get("relative_path") if isinstance(entry, dict) else None
        source = (cipher / relative) if isinstance(relative, str) and relative not in ("", ".") else None
        try:
            ok = (source is not None and not Path(relative).is_absolute() and ".." not in Path(relative).parts and not source.is_symlink()
                  and source.is_dir() and source.resolve().parent != source and cipher in source.resolve().parents
                  and os.lstat(source).st_ino == entry.get("inode") and os.lstat(source / DIRIV).st_size == 0)
        except OSError:
            ok = False
        if not ok:
            skipped.append(str(shown))
            continue
        target = folder / source.name
        if target.exists():
            target = folder / f"{source.name}-{secrets.token_hex(3)}"
        os.rename(source, target)
        longname = source.parent / f"{source.name}.name"   # gocryptfs-Langname: die Namensdatei gehoert dazu
        if source.name.startswith("gocryptfs.longname.") and longname.is_file():
            os.rename(longname, folder / f"{target.name}.name")
        moved.append(str(shown))
        notes.append(f"{_now()} {shown} <- {relative} -> {target.name}")
    for directory in {folder, *(((cipher / entry["cipher_relative"]).parent) for entry in entries
                               if isinstance(entry, dict) and isinstance(entry.get("cipher_relative"), str) and (cipher / entry["cipher_relative"]).parent.is_dir())}:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    if notes:
        with open(folder / "HERKUNFT.txt", "a", encoding="utf-8") as handle:
            handle.write("\n".join(notes) + "\n")
        os.chmod(folder / "HERKUNFT.txt", 0o600)
    request_path.unlink(missing_ok=True)
    (resolved / UNREADABLE_CHECK).unlink(missing_ok=True)
    return {"status": "quarantined" if moved else "nothing_moved", "moved": moved, "skipped": skipped, "folder": folder.name}


__all__ = [
    "CONTRACT", "DATA_CIPHER", "FAILURE_CODES", "KEYRING_APPLICATION", "MIN_PASSWORD_LENGTH", "STATE_FILE", "DesktopProtectionV1Error",
    "backups_root_v1", "cancel_rekey_v1", "close_backups_readonly_v1", "open_backups_readonly_v1", "set_aside_backups_v1", "change_password_v1", "data_root_v1", "enable_v1", "finalize_v1", "format_recovery_key_v1", "lock_v1",
    "mount_root_v1", "read_state_v1", "recover_v1", "rekey_v1", "remove_old_ciphers_v1", "request_rekey_v1", "set_keyring_unlock_v1",
    "status_v1", "unlock_from_keyring_v1", "unlock_v1", "lock_if_due_v1", "catch_up_after_sleep_v1", "ensure_sleep_guard_v1", "sleep_guard_v1", "set_lock_on_quit_v1", "request_lock_v1", "clear_stray_note_v1", "seal_if_lost_v1", "damaged_cipher_directories_v1", "unreadable_execute_v1", "unreadable_preview_v1",
    "unreadable_request_v1",
]
