#!/usr/bin/env python3
"""Neue Ordner dauerhaft machen (#568).

Mit Passwortschutz liegt der Datenraum in gocryptfs. Legt man dort einen Ordner an, schreibt gocryptfs in den verschluesselten Ordner
eine Datei `gocryptfs.diriv` (16 Byte), ohne sie mit fsync festzuschreiben; ein fsync des Klartext-Ordners erreicht sie nicht. Startet
der Rechner neu, bevor der Kern sie von selbst schreibt, bleibt sie leer: Der Ordner ist unlesbar (Ein-/Ausgabefehler), und jedes
Backup bricht ab, etwa bei einem gerade veroeffentlichten Lauf von activity_status.

`settle_new_directory_v1` schreibt den Ordner und den darueber fest (fsync). Liegt er in einer gocryptfs-Einhaengung, synchronisiert es
zusaetzlich deren verschluesselten Quellordner (syncfs) - nur dieses Dateisystem, nicht alle wie sync(), damit etwa ein langsamer
USB-Stick nichts aufhaelt. Wer einen neuen Ordner sichtbar macht (umbenennt, latest.json darauf zeigen laesst), ruft es vorher auf.
Ein Fehler hier haelt nichts an: Es ist eine Absicherung, das Ergebnis sagt nur, was geschah.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Callable

GOCRYPTFS_TYPE = "fuse.gocryptfs"
MOUNTINFO = Path("/proc/self/mountinfo")


def _unescape(field: str) -> str:
    """mountinfo schreibt Leerzeichen, Tabulator, Zeilenumbruch und Rueckstrich als \\040, \\011, \\012, \\134."""
    out: list[str] = []
    index = 0
    while index < len(field):
        chunk = field[index + 1:index + 4]
        if field[index] == "\\" and len(chunk) == 3 and all(char in "01234567" for char in chunk):
            out.append(chr(int(chunk, 8)))
            index += 4
        else:
            out.append(field[index])
            index += 1
    return "".join(out)


def parse_mountinfo_v1(text: str) -> list[tuple[str, str, str]]:
    """(Einhaengepunkt, Dateisystemtyp, Quelle) je Zeile von /proc/self/mountinfo. Bei gocryptfs ist die Quelle der verschluesselte
    Ordner."""
    rows: list[tuple[str, str, str]] = []
    for line in text.splitlines():
        parts = line.split(" ")
        if "-" not in parts:
            continue
        separator = parts.index("-")
        if separator < 5 or len(parts) < separator + 3:
            continue
        rows.append((_unescape(parts[4]), parts[separator + 1], _unescape(parts[separator + 2])))
    return rows


def backing_mount_v1(path: str | Path, mountinfo_text: str | None = None) -> tuple[str, str, str] | None:
    """Die Einhaengung, in der `path` liegt (laengster passender Einhaengepunkt), oder None."""
    try:
        text = mountinfo_text if mountinfo_text is not None else MOUNTINFO.read_text(encoding="utf-8")
    except OSError:
        return None
    target = os.path.realpath(path)
    best: tuple[str, str, str] | None = None
    for mount, kind, source in parse_mountinfo_v1(text):
        inside = mount == "/" or target == mount or target.startswith(mount.rstrip("/") + "/")
        if inside and (best is None or len(mount) > len(best[0])):
            best = (mount, kind, source)
    return best


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def syncfs_v1(path: str | Path) -> bool:
    """syncfs(2) auf das Dateisystem, in dem `path` liegt."""
    libc = ctypes.CDLL(None, use_errno=True)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        return libc.syncfs(descriptor) == 0
    finally:
        os.close(descriptor)


def settle_new_directory_v1(directory: str | Path, *, mountinfo_text: str | None = None,
                            syncfs: Callable[[str], bool] | None = None) -> str:
    """Macht einen neu angelegten Ordner dauerhaft. Ergebnis: "gocryptfs_synced", "fsynced" oder "failed" - nie eine Ausnahme.
    Ein Pfad ueber /proc/self/fd/<n> (Aufrufer mit Datei-Deskriptor) wird zuerst aufgeloest."""
    try:
        path = Path(os.path.realpath(directory))
        _fsync_directory(path)
        _fsync_directory(path.parent)
        mount = backing_mount_v1(path, mountinfo_text)
        if mount is None or mount[1] != GOCRYPTFS_TYPE:
            return "fsynced"
        source = mount[2]
        if not os.path.isabs(source) or not os.path.isdir(source):
            return "failed"
        return "gocryptfs_synced" if (syncfs or syncfs_v1)(source) else "failed"
    except Exception:
        return "failed"


__all__ = ["GOCRYPTFS_TYPE", "backing_mount_v1", "parse_mountinfo_v1", "settle_new_directory_v1", "syncfs_v1"]
