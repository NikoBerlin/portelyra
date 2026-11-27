"""Einstieg des Leser-Plugins check24 (statement_reader_v1).

Verteilt nur: read() fuer Belege als Bytes (cash), read_text()/detect() fuer Belege als Text (securities, fx, crypto),
finish() fuer die Nachbearbeitung des Stapels, combine_documents()/combine_rows() fuer Belege eines Instituts, die zusammen
gelesen werden (BSDEX). Die Leser stehen in den Modulen daneben; ihre Pruefsummen nennt das Manifest."""
from __future__ import annotations

from typing import Any

import reader_cash
import reader_generator


def read(reader_id: str, source: bytes, file_name: str) -> dict[str, Any]:
    return reader_cash.READERS[reader_id](source, file_name)


def combine_documents(reader_id: str, documents: list) -> dict[str, Any]:
    return getattr(reader_cash, "COMBINERS", {})[reader_id]([(source, name) for source, name in documents])


def generate(reader_id: str, seed: int, domain: str) -> dict[str, Any]:
    """Selbsttest Stufe 3 (rc.379): erfundener Beleg samt Erwartung je Startwert; die Kennung gilt je Bereich."""
    return reader_generator.GENERATORS[reader_id](seed)
