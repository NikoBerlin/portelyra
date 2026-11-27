"""Einstieg des Leser-Plugins bitcoin_de (statement_reader_v1).

Verteilt nur: read() fuer Belege als Bytes (cash), read_text()/detect() fuer Belege als Text (securities, fx, crypto),
finish() fuer die Nachbearbeitung des Stapels, combine_documents()/combine_rows() fuer Belege eines Instituts, die zusammen
gelesen werden (BSDEX). Die Leser stehen in den Modulen daneben; ihre Pruefsummen nennt das Manifest."""
from __future__ import annotations

from typing import Any

import reader_crypto
import reader_generator


_TEXT = {**reader_crypto.READERS}
_DETECT = {**reader_crypto.DETECTORS}


def read_text(reader_id: str, text: str, file_name: str) -> dict[str, Any]:
    return _TEXT[reader_id](text, file_name)


def detect(reader_id: str, text: str) -> bool:
    return bool(_DETECT[reader_id](text))


def combine_rows(reader_id: str, batch: dict[str, Any]) -> list[dict[str, Any]]:
    return reader_crypto.COMBINERS[reader_id](batch)


def generate(reader_id: str, seed: int, domain: str) -> dict[str, Any]:
    """Selbsttest Stufe 3 (rc.379): erfundener Beleg samt Erwartung je Startwert; die Kennung gilt je Bereich."""
    return reader_generator.GENERATORS[reader_id](seed)
