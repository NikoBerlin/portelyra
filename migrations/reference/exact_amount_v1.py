"""Exakte Betraege zwischen Text und Bruch - ohne stillen Genauigkeitsverlust.

Betraege werden im ganzen Projekt ungerundet gefuehrt. Nicht jeder laesst sich
endlich dezimal schreiben: Nach einer Teilveraeusserung krummer Stueckzahlen
haelt das FIFO einen Anschaffungswert als `Zaehler/Nenner`, etwa
1234567/89000. Wer nur die Dezimalform liest, verliert solche Werte
vollstaendig - genau das liess Positionen aus dem
Bestand verschwinden (#283).

Dieses Modul ist neutral: Es rechnet, liest nichts und schreibt nichts. Es
gehoert weder dem fluechtigen Intraday-Pfad noch dem systematischen
Snapshot-Pfad, sondern beiden (#373, 28.09.2026).
"""
from __future__ import annotations

from fractions import Fraction
from typing import Any, Mapping

from migrations.reference.fx_history_v1 import _fraction_from_decimal
from workers.reference.semantic_realized_fifo_v2 import _decimal_or_none


def amount_text_v1(value: Fraction) -> str:
    """Ein Betrag als Text: dezimal, wo das exakt geht, sonst als Bruch.

    Fuer eine nicht endlich darstellbare Zahl gibt es keine Dezimalform. Den Wert
    deshalb wegzulassen waere falsch: Er ist bekannt, nur nicht dezimal
    schreibbar. Gerundet wird erst in der Anzeige.
    """
    decimal = _decimal_or_none(value)
    return decimal if decimal is not None else str(value)


def exact_amount_v1(text: str) -> Fraction:
    """Ein Betrag aus dem Speicher: Dezimaltext oder exakter Bruch."""
    if "/" in text:
        return Fraction(text)
    return _fraction_from_decimal(text)


def exact_decimal_v1(value: Any) -> str | None:
    """Die FIFO-Basis in ihren zwei Gestalten.

    Der Leser gibt sie als schlichten Dezimaltext; in der Tabelle steht sie als
    Struktur mit Genauigkeitsvermerk. Beides wird angenommen - ohne
    `exact_decimal` gibt es keinen belastbaren Anschaffungswert, dann bleibt die
    unrealisierte GuV offen, statt auf einer Naeherung zu beruhen.
    """
    if isinstance(value, str):
        return value if value.strip() else None
    if not isinstance(value, Mapping):
        return None
    if value.get("exactness_status") != "exact_decimal":
        return None
    decimal = value.get("decimal")
    return decimal if isinstance(decimal, str) else None


__all__ = ["amount_text_v1", "exact_amount_v1", "exact_decimal_v1"]
