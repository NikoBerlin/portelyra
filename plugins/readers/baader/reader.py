"""Einstieg des Leser-Plugins baader (statement_reader_v1).

Verteilt nur: read() fuer Belege als Bytes (cash, reward), read_text()/detect() fuer Belege als Text (securities, fx, crypto,
income_statement), finish() fuer die Nachbearbeitung des Stapels, combine_documents()/combine_rows() fuer Belege eines Instituts,
die zusammen gelesen werden (BSDEX), generate() fuer den Selbsttest (rc.379). Die Leser stehen in den Modulen daneben; ihre
Pruefsummen nennt das Manifest."""
from __future__ import annotations

from typing import Any

import reader_cash
import reader_generator
import reader_income


_BYTES = {**reader_cash.READERS}


def read(reader_id: str, source: bytes, file_name: str) -> dict[str, Any]:
    return _BYTES[reader_id](source, file_name)


def combine_documents(reader_id: str, documents: list) -> dict[str, Any]:
    return getattr(reader_cash, "COMBINERS", {})[reader_id]([(source, name) for source, name in documents])


_TEXT = {**reader_income.READERS}
_DETECT = {**reader_income.DETECTORS}


def read_text(reader_id: str, text: str, file_name: str) -> dict[str, Any]:
    return _TEXT[reader_id](text, file_name)


def detect(reader_id: str, text: str) -> bool:
    return bool(_DETECT[reader_id](text))


def generate(reader_id: str, seed: int, domain: str) -> dict[str, Any]:
    """Selbsttest Stufe 3 (rc.379): erfundener Beleg samt Erwartung je Startwert; die Kennungen gelten hier je in einem Bereich."""
    return reader_generator.GENERATORS[reader_id](seed)
