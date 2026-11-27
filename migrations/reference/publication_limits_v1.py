"""Groessengrenzen veroeffentlichter Artefakte (#503) - eine Quelle fuer Schreiber, Leser und Inventur.

Bis rc.296 stand 20 MB an vier Stellen fest. Eine grosse Tageshistorie mit
eigenen Gruppen konnte daran scheitern. Die Vorgabe ist jetzt 50 MB. Die Teildateien der Tageshistorie haben eine eigene, kleinere Grenze: Sie tragen die Reihen eines einzigen Assets,
einer Klasse oder einer Gruppe.
"""

from __future__ import annotations

MAX_ARTIFACT_BYTES = 50_000_000
MAX_PART_BYTES = 20_000_000

__all__ = ["MAX_ARTIFACT_BYTES", "MAX_PART_BYTES"]
