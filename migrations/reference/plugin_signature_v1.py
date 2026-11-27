#!/usr/bin/env python3
"""Portelyra-Signatur fuer Plugin-Pakete und Release-Archive (#486, Festlegungen 15. und 16.11.2026). Vertrag: contracts/plugin-signing/v1.

Signiert ist bei einem Paket `package.json`, bei einem Release `release-manifest.json` - jeweils jede Datei mit ihrer SHA-256-Pruefsumme.
Die Signatur pruefen `ssh-keygen -Y verify` und die Vertrauensliste, die mit dem Release reist; je Zweck ein eigener Namensraum, damit
eine Paket-Signatur nie als Release-Signatur gilt. Signiert wird nur ueber einen eigenen Signatur-Agenten (Schluessel einmal je Sitzung
laden, mit `ssh-add -c`, damit
jede einzelne Signatur in einem Fenster bestaetigt wird; sonst koennte jedes Programm der Sitzung signieren). Die Datei mit dem privaten
Schluessel liest Portelyra nie. Kein Netz, keine Schluessel im Datenraum.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TRUST_LIST = ROOT / "contracts" / "plugin-signing" / "v1" / "allowed_signers"
NAMESPACE = "portelyra-plugin"
NAMESPACE_RELEASE = "portelyra-release"
PRINCIPAL = "portelyra"
MAX_SIGNATURE_BYTES = 8192


class PluginSignatureBlocked(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def trusted_keys_v1(trust_list: str | Path | None = None) -> list[str]:
    """Die Schluessel der Vertrauensliste (Zeilen ohne Kommentar)."""
    path = TRUST_LIST if trust_list is None else Path(trust_list)
    if path.is_symlink() or not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.lstrip().startswith("#")]


def verify_package_signature_v1(package_bytes: bytes, signature_bytes: bytes | None, trust_list: str | Path | None = None) -> dict[str, str]:
    """Prueft die Signatur von `package.json`. Ergebnis {"status": "valid", "principal", "key_sha256"} oder ein Abbruch mit Grund:
    keine Signatur, Vertrauensliste leer oder Schluessel nicht darin, Signatur passt nicht, ssh-keygen fehlt."""
    return verify_signature_v1(package_bytes, signature_bytes, NAMESPACE, trust_list)


def verify_signature_v1(package_bytes: bytes, signature_bytes: bytes | None, namespace: str, trust_list: str | Path | None = None) -> dict[str, str]:
    """Wie oben, fuer einen Namensraum (`portelyra-plugin` oder `portelyra-release`)."""
    if namespace not in (NAMESPACE, NAMESPACE_RELEASE):
        raise PluginSignatureBlocked("plugin_signature_invalid")
    if not signature_bytes:
        raise PluginSignatureBlocked("plugin_signature_missing")
    if not isinstance(package_bytes, bytes) or not isinstance(signature_bytes, bytes) or len(signature_bytes) > MAX_SIGNATURE_BYTES:
        raise PluginSignatureBlocked("plugin_signature_invalid")
    keys = trusted_keys_v1(trust_list)
    if not keys:
        raise PluginSignatureBlocked("plugin_signature_untrusted")
    tool = shutil.which("ssh-keygen")
    if not tool:
        raise PluginSignatureBlocked("plugin_signature_tool_missing")
    with tempfile.TemporaryDirectory(prefix=".portelyra-signature-") as temporary:
        directory = Path(temporary)
        os.chmod(directory, 0o700)
        signers = directory / "allowed_signers"
        signers.write_text("\n".join(keys) + "\n", encoding="utf-8")
        signature = directory / "package.json.sig"
        signature.write_bytes(signature_bytes)
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(directory), "LANG": "C.UTF-8"}
        try:
            done = subprocess.run([tool, "-Y", "verify", "-f", str(signers), "-I", PRINCIPAL, "-n", namespace, "-s", str(signature)],
                                  input=package_bytes, capture_output=True, timeout=30, env=environment)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PluginSignatureBlocked("plugin_signature_tool_missing") from error
    if done.returncode != 0:
        # Unbekannter Schluessel und verfaelschter Inhalt melden sich bei ssh-keygen gleich; unterschieden wird, ob der Schluessel der
        # Signatur ueberhaupt in der Liste steht.
        listed = any(_signature_key(signature_bytes) and _signature_key(signature_bytes) in key for key in keys)
        raise PluginSignatureBlocked("plugin_signature_invalid" if listed else "plugin_signature_untrusted")
    return {"status": "valid", "principal": PRINCIPAL, "key_sha256": hashlib.sha256(_signature_key(signature_bytes).encode("ascii")).hexdigest()}


def public_key_line_v1(public_key: str | Path) -> str:
    """Typ und Base64 eines oeffentlichen Schluessels (ohne Kommentar), wie in der Vertrauensliste und in `ssh-add -L`."""
    path = Path(public_key)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 4096:
        raise PluginSignatureBlocked("signing_not_set_up")
    parts = path.read_text(encoding="ascii", errors="replace").split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise PluginSignatureBlocked("signing_not_set_up")
    return f"{parts[0]} {parts[1]}"


def active_signing_public_key_v1(signing_home: str | Path) -> Path:
    """Oeffentlicher Teil des Schluessels, der gerade signiert (#486, rc.430): der Hauptschluessel; waehrend eines Schluesselwechsels
    (setup.json `transition`, dev/signing_setup.py --rotate main) der bisherige Ersatzschluessel, den jede installierte Vertrauensliste
    kennt. Release-Bau und Paket-Werkzeug signieren damit; ob er passt, pruefen sie selbst gegen setup.json und die Liste."""
    home = Path(signing_home)
    try:
        record = json.loads((home / "setup.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = None
    if isinstance(record, dict) and record.get("transition") is not None:
        return home / "transition_signing.pub"
    return home / "portelyra_signing.pub"


def trust_list_contains_v1(public_key: str | Path, trust_list: str | Path | None = None) -> bool:
    key = public_key_line_v1(public_key)
    return any(f" {key} " in f" {line} " for line in trusted_keys_v1(trust_list))


def sign_with_agent_v1(data: bytes, public_key: str | Path, namespace: str, agent_socket: str | Path | None = None,
                       timeout_seconds: int = 180) -> bytes:
    """Signiert `data` mit dem Schluessel zu `public_key` - nur ueber den Agenten am Socket `agent_socket` (Vorgabe: SSH_AUTH_SOCK). Ist der
    Schluessel dort nicht geladen, bricht es ab, statt nach einer Passphrase zu fragen. Mit `ssh-add -c` geladen, fragt der Agent vor jeder
    Signatur nach; wird sie abgelehnt oder nicht rechtzeitig bestaetigt, endet es mit `signing_declined`. Neben dem oeffentlichen Schluessel liegt keine private Datei,
    auf die ssh-keygen ausweichen koennte."""
    if namespace not in (NAMESPACE, NAMESPACE_RELEASE) or not isinstance(data, bytes):
        raise PluginSignatureBlocked("signing_failed")
    key = public_key_line_v1(public_key)
    tool, agent_tool = shutil.which("ssh-keygen"), shutil.which("ssh-add")
    if not tool or not agent_tool:
        raise PluginSignatureBlocked("plugin_signature_tool_missing")
    socket = str(agent_socket) if agent_socket is not None else os.environ.get("SSH_AUTH_SOCK", "")
    if not socket or not Path(socket).exists() or Path(socket).is_symlink():
        raise PluginSignatureBlocked("signing_key_not_loaded")
    environment = {"PATH": os.environ.get("PATH", ""), "SSH_AUTH_SOCK": socket, "LANG": "C.UTF-8", "SSH_ASKPASS_REQUIRE": "never"}
    try:
        listed = subprocess.run([agent_tool, "-L"], capture_output=True, text=True, timeout=30, env=environment, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PluginSignatureBlocked("signing_key_not_loaded") from error
    if listed.returncode != 0 or not any(" ".join(line.split()[:2]) == key for line in listed.stdout.splitlines()):
        raise PluginSignatureBlocked("signing_key_not_loaded")
    with tempfile.TemporaryDirectory(prefix=".portelyra-signing-") as temporary:
        directory = Path(temporary)
        os.chmod(directory, 0o700)
        pub = directory / "signing.pub"
        pub.write_text(key + "\n", encoding="ascii")
        target = directory / "data"
        target.write_bytes(data)
        try:
            done = subprocess.run([tool, "-Y", "sign", "-f", str(pub), "-n", namespace, str(target)], capture_output=True,
                                  timeout=timeout_seconds, env={**environment, "HOME": str(directory)}, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as error:
            raise PluginSignatureBlocked("signing_declined") from error
        except OSError as error:
            raise PluginSignatureBlocked("signing_failed") from error
        signature = directory / "data.sig"
        if done.returncode != 0 or not signature.is_file():
            raise PluginSignatureBlocked("signing_declined" if b"refused" in done.stderr else "signing_failed")
        return signature.read_bytes()


def _signature_key(signature_bytes: bytes) -> str:
    """Der oeffentliche Schluessel in einer SSH-Signatur (Base64 des Schluesselblocks), fuer die Unterscheidung oben und als Kennung."""
    import base64
    import struct
    try:
        text = signature_bytes.decode("ascii")
        body = "".join(line for line in text.splitlines() if line and not line.startswith("-----"))
        blob = base64.b64decode(body)
        if blob[:6] != b"SSHSIG":
            return ""
        offset = 10   # Magie (6) + Version (4)
        (length,) = struct.unpack(">I", blob[offset:offset + 4])
        key = blob[offset + 4:offset + 4 + length]
        return base64.b64encode(key).decode("ascii")
    except (UnicodeError, ValueError, struct.error):
        return ""


__all__ = ["NAMESPACE", "NAMESPACE_RELEASE", "PRINCIPAL", "PluginSignatureBlocked", "TRUST_LIST", "public_key_line_v1", "sign_with_agent_v1",
           "trust_list_contains_v1", "trusted_keys_v1", "verify_package_signature_v1", "verify_signature_v1"]
