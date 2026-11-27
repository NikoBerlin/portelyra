"""Einstieg eines Leser-Plugins (statement_reader_v1) - Vorlage.

Verteilt nur: read() fuer Belege als Bytes (cash, reward), generate() fuer den Selbsttest. Textbereiche (securities, fx, crypto,
income_statement) brauchen read_text() und detect(); siehe contracts/statement-reader-plugin/v1/README.md und die mitgelieferten
Plugins. Jede Datei mit Python-Code muss im Manifest mit Pruefsumme stehen."""
from __future__ import annotations

from typing import Any

import reader_cash
import reader_generator


def read(reader_id: str, source: bytes, file_name: str) -> dict[str, Any]:
    return reader_cash.READERS[reader_id](source, file_name)


def generate(reader_id: str, seed: int, domain: str) -> dict[str, Any]:
    """Selbsttest Stufe 3: erfundener Beleg samt Erwartung je Startwert; die Kennung gilt je Bereich."""
    return reader_generator.GENERATORS[reader_id](seed)
