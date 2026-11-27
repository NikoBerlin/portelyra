"""Einstieg des Leser-Plugins trade_republic (statement_reader_v1).

Verteilt nur: read() fuer Belege als Bytes (cash), read_text()/detect() fuer Belege als Text (securities, fx, crypto),
finish() fuer die Nachbearbeitung des Stapels, combine_documents()/combine_rows() fuer Belege eines Instituts, die zusammen
gelesen werden (BSDEX). Die Leser stehen in den Modulen daneben; ihre Pruefsummen nennt das Manifest."""
from __future__ import annotations

from typing import Any

import reader_cash
import reader_generator
import reader_securities


def read(reader_id: str, source: bytes, file_name: str) -> dict[str, Any]:
    return reader_cash.READERS[reader_id](source, file_name)


def combine_documents(reader_id: str, documents: list) -> dict[str, Any]:
    return getattr(reader_cash, "COMBINERS", {})[reader_id]([(source, name) for source, name in documents])


_TEXT = {**{key: (lambda function: lambda text, file_name: function(text))(value) for key, value in reader_securities.READERS.items()}}
_DETECT = {**reader_securities.DETECTORS}


def read_text(reader_id: str, text: str, file_name: str) -> dict[str, Any]:
    return _TEXT[reader_id](text, file_name)


def detect(reader_id: str, text: str) -> bool:
    return bool(_DETECT[reader_id](text))


def finish(reader_id: str, batch: dict[str, Any]) -> dict[str, Any]:
    """Nachbearbeitung ueber den ganzen Stapel (Teilausfuehrungen, Ordnungszeit); aendert die Listen und gibt sie zurueck."""
    if reader_id in reader_securities.FINISHERS:
        reader_securities.FINISHERS[reader_id](batch["candidates"], batch["statements"], batch["row_reasons"])
    return batch


def generate(reader_id: str, seed: int, domain: str) -> dict[str, Any]:
    """Selbsttest Stufe 3 (rc.379): erfundener Beleg samt Erwartung je Startwert. trade_republic_v1 gibt es als Cash- und als
    Wertpapier-Leser; der Bereich waehlt den Erzeuger."""
    return reader_generator.GENERATORS[(domain, reader_id)](seed)
