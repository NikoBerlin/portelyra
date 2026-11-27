#!/usr/bin/env python3
"""Uebernahme einer Kurshistorie von einer Listing-Freigabe auf eine andere.

Eine Kurshistorie haengt an der Listing-Freigabe. Wird eine Freigabe erneuert -
etwa weil ihr Katalog-Fingerprint aus einer aelteren Produktversion stammt -,
entsteht eine neue Freigabe mit leerem Bestand, und dieselben Tage muessten
erneut bei der Quelle geholt werden. So lagen nach mehreren
Erneuerungen viele Kurstage an abgeloesten Freigaben (#283).

Die Uebernahme kopiert diese Tage unter die neue Freigabe. Sie greift nicht auf
einen Anbieter zu und geht nicht ins Netz; sie liest den eigenen Bestand. Die
uebernommenen Tage tragen die Herkunftsart 'carried_listing' und im
Quellverweis die Freigabe, aus der sie stammen - im Pruefpfad ist damit
unterscheidbar, was geholt und was uebernommen wurde.

Zweiter Anwendungsfall: dasselbe Papier als zwei Assets (Altlast-Dubletten).
Dann steht dieselbe Kursreihe unter zwei Freigaben, statt zweimal geholt zu
werden.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from migrations.reference.daily_market_history_v1 import (
    DailyMarketHistoryBlocked,
    MarketHistoryContext,
    append_daily_market_history_v1,
    daily_market_history_job_binding_fingerprint_v1,
    read_daily_market_history_v1,
    read_daily_market_listing_binding_v1,
    seal_daily_market_history_candidate_v1,
    validate_daily_market_candidate_for_listing_v1,
)

CARRY_SOURCE_VERSION = "desktop_history_carry_v1.0.0"
_LISTING = re.compile(r"^lsr_[a-f0-9]{32}$")
_SHA = re.compile(r"^[a-f0-9]{64}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Die Felder, die ein uebernommener Tag aus dem Bestand mitbringt. Alles andere
# setzt die Uebernahme selbst: Es ist die erste Fassung dieses Tages unter der
# neuen Freigabe, also keine Korrektur.
_CARRIED = (
    "day_status", "bar_shape", "open_decimal", "high_decimal", "low_decimal",
    "close_decimal", "adjusted_close_decimal", "volume_decimal",
    "corporate_action_status", "valuation_status",
    "gap_reason", "source_observation_ref", "observed_at_utc",
)
# Der Qualitaetsstatus beschreibt die Fassung, nicht den Kurs. Unter der neuen
# Freigabe ist jeder uebernommene Tag die Erstfassung, und dafuer verlangt der
# Speicher bei einem beobachteten Tag 'complete'. Ein an der Quelle korrigierter
# Tag traegt 'corrected'; unveraendert uebernommen haette er die ganze
# Uebernahme abgewiesen, obwohl die Vorschau sie als machbar gemeldet hat
# (Prüfung 25.09.2026).
_QUALITY = {"observed": "complete", "non_trading_day": "calendar_confirmed", "source_gap": "explicit_gap"}


class DesktopMarketHistoryCarryV1Error(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def desktop_market_history_carry_v1_error_codes() -> tuple[str, ...]:
    return (
        "desktop_market_history_carry_input_invalid",
        "desktop_market_history_carry_listing_mismatch",
        "desktop_market_history_carry_source_empty",
        "desktop_market_history_carry_store_invalid",
        "desktop_market_history_carry_write_failed",
    )


def _abort(code: str) -> None:
    if code not in desktop_market_history_carry_v1_error_codes():
        code = "desktop_market_history_carry_input_invalid"
    raise DesktopMarketHistoryCarryV1Error(code)


def _date(value: Any) -> date:
    if not isinstance(value, str) or _DAY.fullmatch(value) is None:
        _abort("desktop_market_history_carry_input_invalid")
    try:
        return date.fromisoformat(value)
    except ValueError:
        _abort("desktop_market_history_carry_input_invalid")
        raise


def _runs(source_days: Sequence[Mapping[str, Any]], target_days: Sequence[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    """Zusammenhaengende Strecken uebernehmbarer Tage.

    Uebernommen wird ein Tag nur, wenn die Quelle ihn traegt und das Ziel ihn
    noch nicht hat: Eine Uebernahme ergaenzt, sie ueberschreibt nicht. Das ist
    auch der praktische Fall - nach einer Erneuerung traegt die neue Freigabe
    schon das Testfenster der Einrichtung, und nur der Teil davor fehlt.

    Ein versiegelter Kandidat muss jeden Kalendertag seines Zeitraums tragen.
    Eine Luecke laesst sich deshalb nicht mituebernehmen; sie trennt zwei
    Uebernahmen.
    """
    occupied = {row["trading_date"] for row in target_days if row["day_status"] != "not_requested"}
    runs: list[list[Mapping[str, Any]]] = []
    previous: date | None = None
    for row in source_days:
        if row["day_status"] == "not_requested" or row["trading_date"] in occupied:
            previous = None
            continue
        current = date.fromisoformat(row["trading_date"])
        if previous is not None and current - previous == timedelta(days=1):
            runs[-1].append(row)
        else:
            runs.append([row])
        previous = current
    return runs


def carry_desktop_market_history_v1(
    store_path: str | Path,
    context: MarketHistoryContext | Mapping[str, str],
    *,
    source_listing_ref: str,
    target_listing_ref: str,
    start_date: str,
    end_date: str,
    carried_at_utc: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    for value in (source_listing_ref, target_listing_ref):
        if not isinstance(value, str) or _LISTING.fullmatch(value) is None:
            _abort("desktop_market_history_carry_input_invalid")
    if source_listing_ref == target_listing_ref:
        _abort("desktop_market_history_carry_listing_mismatch")
    start = _date(start_date)
    end = _date(end_date)
    if end < start:
        _abort("desktop_market_history_carry_input_invalid")
    store = Path(store_path)
    try:
        source_listing = read_daily_market_listing_binding_v1(store, context, source_listing_ref)
        target_listing = read_daily_market_listing_binding_v1(store, context, target_listing_ref)
    except DailyMarketHistoryBlocked as error:
        raise DesktopMarketHistoryCarryV1Error("desktop_market_history_carry_store_invalid") from error
    # Was die Freigabe selbst aussagt, muss uebereinstimmen. Dass es dieselbe
    # Quelle mit demselben Symbol ist, sieht die Zuordnung - das prueft der
    # Aufrufer, nicht der Speicher.
    for field in ("quote_currency", "market_code", "timezone_name", "calendar_code"):
        if source_listing[field] != target_listing[field]:
            _abort("desktop_market_history_carry_listing_mismatch")
    try:
        source_history = read_daily_market_history_v1(store, context, source_listing_ref, start_date, end_date)
        target_history = read_daily_market_history_v1(store, context, target_listing_ref, start_date, end_date)
    except DailyMarketHistoryBlocked as error:
        raise DesktopMarketHistoryCarryV1Error("desktop_market_history_carry_store_invalid") from error
    runs = _runs(source_history["days"], target_history["days"])
    # Die Vorschau rechnet dasselbe und schreibt nichts. Vor einem Write, der
    # eine fremde Kursreihe an ein Asset haengt, gehoert die Zahl auf den Tisch -
    # auch die Null. "Nichts zu uebernehmen" ist eine Auskunft, kein Fehler; als
    # Fehler gemeldet sah es aus, als sei etwas kaputt (24.09.2026, #283).
    if dry_run:
        return {
            "contract_version": "desktop_market_history_carry_result_v1",
            "status": "preview",
            "source_listing_ref": source_listing_ref,
            "target_listing_ref": target_listing_ref,
            "carried_day_count": sum(len(run) for run in runs),
            "range_count": len(runs),
            "ranges": [
                {
                    "request_ref": None,
                    "receipt_fingerprint": None,
                    "start_date": run[0]["trading_date"],
                    "end_date": run[-1]["trading_date"],
                    "day_count": len(run),
                }
                for run in runs
            ],
            "provider_access": False,
            "network_access": False,
            "canonical_write": False,
            "market_history_write": False,
            "automatic_retry": False,
        }
    if not runs:
        # Entweder traegt die Quelle im Zeitraum nichts, oder das Ziel hat
        # bereits alles. Beides ist kein Schaden, aber auch nichts zu tun.
        _abort("desktop_market_history_carry_source_empty")
    receipts = []
    carried = 0
    for ordinal, run in enumerate(runs, start=1):
        days = [
            {
                **{field: row[field] for field in _CARRIED},
                "trading_date": row["trading_date"],
                "revision_mode": "initial",
                "supersedes_revision_ref": None,
                "correction_reason": None,
                "quality_status": _QUALITY[row["day_status"]],
            }
            for row in run
        ]
        request_ref = "mrq_" + _carry_ref(target_listing_ref, source_listing_ref, run, ordinal, carried_at_utc)
        source_ref = "msr_" + _carry_ref(source_listing_ref, target_listing_ref, run, ordinal, carried_at_utc)
        request_fingerprint = _carry_fingerprint(source_listing_ref, target_listing_ref, days)
        try:
            binding = daily_market_history_job_binding_fingerprint_v1(
                context,
                listing_ref=target_listing_ref,
                request_ref=request_ref,
                request_fingerprint=request_fingerprint,
                source_ref=source_ref,
            )
            candidate = seal_daily_market_history_candidate_v1(
                listing_ref=target_listing_ref,
                request_ref=request_ref,
                source_kind="carried_listing",
                source_ref=source_ref,
                source_version=CARRY_SOURCE_VERSION,
                request_fingerprint=request_fingerprint,
                job_binding_fingerprint=binding,
                requested_start_date=run[0]["trading_date"],
                requested_end_date=run[-1]["trading_date"],
                retrieved_at_utc=carried_at_utc,
                days=days,
            )
            validate_daily_market_candidate_for_listing_v1(candidate, target_listing)
            receipt = append_daily_market_history_v1(store, context, candidate, carried_at_utc)
        except DailyMarketHistoryBlocked as error:
            raise DesktopMarketHistoryCarryV1Error("desktop_market_history_carry_write_failed") from error
        carried += len(days)
        receipts.append(
            {
                "request_ref": receipt.request_ref,
                "receipt_fingerprint": receipt.receipt_fingerprint,
                "start_date": run[0]["trading_date"],
                "end_date": run[-1]["trading_date"],
                "day_count": len(days),
            }
        )
    return {
        "contract_version": "desktop_market_history_carry_result_v1",
        "status": "carried",
        "source_listing_ref": source_listing_ref,
        "target_listing_ref": target_listing_ref,
        "carried_day_count": carried,
        "range_count": len(receipts),
        "ranges": receipts,
        "provider_access": False,
        "network_access": False,
        "canonical_write": False,
        "market_history_write": True,
        "automatic_retry": False,
    }


def _carry_ref(primary: str, secondary: str, run: Sequence[Mapping[str, Any]], ordinal: int, carried_at_utc: str) -> str:
    from migrations.reference.daily_market_history_v1 import _sha  # noqa: PLC0415

    return _sha(
        {
            "contract": "desktop_market_history_carry_v1",
            "primary": primary,
            "secondary": secondary,
            "ordinal": ordinal,
            "start_date": run[0]["trading_date"],
            "end_date": run[-1]["trading_date"],
            "carried_at_utc": carried_at_utc,
        }
    )[:32]


def _carry_fingerprint(source_listing_ref: str, target_listing_ref: str, days: Sequence[Mapping[str, Any]]) -> str:
    from migrations.reference.daily_market_history_v1 import _sha  # noqa: PLC0415

    return _sha(
        {
            "contract": "desktop_market_history_carry_request_v1",
            "source_listing_ref": source_listing_ref,
            "target_listing_ref": target_listing_ref,
            "days": list(days),
        }
    )


__all__ = [
    "CARRY_SOURCE_VERSION",
    "DesktopMarketHistoryCarryV1Error",
    "carry_desktop_market_history_v1",
    "desktop_market_history_carry_v1_error_codes",
]
