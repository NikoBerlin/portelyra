#!/usr/bin/env python3
"""Cash von Hand: einfache Buchung und nachtraeglicher Pruef-Saldo (#417, #419).

Zwei Vorgaenge:

**Eine Cash-Buchung eintragen.** Konto, Datum, Betrag, Art. Der Weg ueber den
Cash-Coverage-Editor verlangte dafuer zwanzig Felder, Ortszeit, IANA-Zeitzone,
den daraus abgeleiteten UTC-Zeitstempel und einen von Hand beschafften SHA-256.

**Einen Saldo nachtraeglich festhalten.** Exporte ohne Saldospalte werden als
`partial` gebucht, und danach gab es keinen Weg mehr, sie auf abgestimmt zu
heben, auch wenn der Saldo online geprueft war.

Dieses Modul erfindet keinen zweiten Schreibweg. Es bildet aus wenigen Angaben
die Kommandos des Kerns (`desktop_cash_coverage_v1`), laesst sie dort
vorrechnen und gibt Kommando, Vorschau und eine Erklaerung zurueck. Geschrieben
wird ueber die bestehende Bestaetigung des Kerns.

Zeitordnung wie bei allen Importadaptern: Fuer Tagessalden zaehlt der Tag. Eine
Handbuchung bekommt 12:00:00 Ortszeit plus die naechste freie Sekunde des Tages.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from migrations.reference.desktop_cash_coverage_v1 import (
    EVIDENCE_KINDS,
    REQUEST,
    SHA,
    DesktopCashCoverageV1Error,
    _abort,
    _active_rows,
    _catalog,
    _date,
    _decimal,
    _open_store,
    _owner_directory,
    _sha,
    _store_path,
    _strict,
    desktop_cash_evidence_fingerprint_v1,
    desktop_cash_evidence_kind_v1,
    preview_desktop_cash_coverage_command_v1,
    preview_desktop_cash_coverage_manual_batch_v1,
)

TIME_ZONE = "Europe/Berlin"
BOOKING_KINDS = ("deposit", "withdrawal", "interest")
CHECK_EVIDENCE_KINDS = ("document", *EVIDENCE_KINDS)
FLAGS = {"canonical_write": False, "asset_activity_write": False, "provider_access": False,
         "network_access": False, "path_exposed": False}


def _plain(value: Decimal) -> str:
    """Dezimaltext in der Schreibweise des Kerns: ohne Exponent, ohne Endnullen."""
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _utc(local_date: str, local_time: str) -> str:
    local = datetime.fromisoformat(f"{local_date}T{local_time}").replace(tzinfo=ZoneInfo(TIME_ZONE))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_ref(command_id: str) -> str:
    return "cash_record_" + _sha({"command_id": command_id})[:32]


def _request(base: str, ordinal: int) -> str:
    """Je Kommando eines Vorgangs eine eigene Anforderung, abgeleitet aus der einen des Vorgangs."""
    return "ccrq_" + _sha({"desktop_cash_manual_request": base, "ordinal": ordinal})[:32]


def _scope(value: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, str]:
    scope = {key: value[key] for key in ("portfolio_id", "account_id", "cash_asset_id")}
    account = catalog["accounts"].get(scope["account_id"]) if isinstance(scope["account_id"], str) else None
    asset = catalog["assets"].get(scope["cash_asset_id"]) if isinstance(scope["cash_asset_id"], str) else None
    if account is None or asset is None or account["portfolio_id"] != scope["portfolio_id"]:
        _abort("desktop_cash_coverage_catalog_invalid")
    return scope


def _account_periods(connection, account_id: str) -> list[Any]:
    return [row for row in _active_rows(connection, "coverage_period", "account_id,effective_from,coverage_id")
            if row["account_id"] == account_id]


def _covering(periods: list[Any], day: str) -> Any | None:
    hits = [row for row in periods
            if row["effective_from"] <= day and (row["effective_to"] is None or day <= row["effective_to"])]
    return hits[0] if len(hits) == 1 else None


def _account_events(connection, account_id: str) -> list[Any]:
    return [row for row in _active_rows(connection, "cash_event", "effective_at_utc,cash_event_id")
            if row["account_id"] == account_id or row["related_account_id"] == account_id]


def _delta(event: Any, account_id: str) -> Decimal:
    """Saldowirkung eines Ereignisses auf ein Konto - dieselbe Regel wie in der Fachpruefung."""
    amount = Decimal(event["amount_decimal"])
    if event["event_type"] in {"opening_balance", "deposit"}:
        return amount if event["account_id"] == account_id else Decimal(0)
    if event["event_type"] == "withdrawal":
        return -amount if event["account_id"] == account_id else Decimal(0)
    if event["event_type"] == "transfer":
        if event["account_id"] == account_id:
            return -amount
        if event["related_account_id"] == account_id:
            return amount
    return Decimal(0)


def _in_period(event: Any, period: Any, through: str | None = None) -> bool:
    day = event["local_date"]
    return (period["effective_from"] <= day
            and (period["effective_to"] is None or day <= period["effective_to"])
            and (through is None or day <= through))


def _reconciliations(connection, account_id: str, period: Any) -> list[Any]:
    return [row for row in _active_rows(connection, "reconciliation", "account_id,as_of_date,reconciliation_id")
            if row["account_id"] == account_id and period["effective_from"] <= row["as_of_date"]
            and (period["effective_to"] is None or row["as_of_date"] <= period["effective_to"])]


def prepare_desktop_cash_check_balance_v1(
    canonical_path: str | Path, data_space_path: str | Path, context_value: Any, request_value: Any,
) -> dict[str, Any]:
    """Einen Pruef-Saldo zu einem Datum festhalten.

    Ist der Zeitraum schon abgestimmt, entsteht eine weitere Abstimmung. Ist er
    `partial`, wird er ausdruecklich durch einen abgestimmten ersetzt: Die
    Abstimmung selbst hebt den Modus an. Der Eroeffnungssaldo ergibt sich dann
    aus Pruef-Saldo minus gebuchter Bewegungen - wie bei "Saldo bestaetigen" im
    Import. Er steht in der Erklaerung, damit sichtbar wird, ob die Buchungen bei
    null beginnen.

    `owner_asserted_without_balance` ist der Weg fuer Quellen, bei denen kein
    Saldo zu bekommen ist: Vollstaendigkeit wird erklaert, geprueft wird nichts.
    Der gespeicherte Saldo ist dann der errechnete, und die Nachweisart sagt das.
    """
    request = _strict(request_value, {"request_ref", "portfolio_id", "account_id", "cash_asset_id", "as_of_date",
                                       "observed_balance_decimal", "evidence_kind", "evidence_fingerprint"})
    if not isinstance(request["request_ref"], str) or REQUEST.fullmatch(request["request_ref"]) is None:
        _abort("desktop_cash_coverage_input_invalid")
    kind = request["evidence_kind"]
    if kind not in CHECK_EVIDENCE_KINDS:
        _abort("desktop_cash_coverage_input_invalid")
    as_of = _date(request["as_of_date"])
    asserted = kind == "owner_asserted_without_balance"
    if asserted:
        if request["observed_balance_decimal"] is not None or request["evidence_fingerprint"] is not None:
            _abort("desktop_cash_coverage_input_invalid")
        observed: Decimal | None = None
    else:
        observed = Decimal(_decimal(request["observed_balance_decimal"]))
        if kind == "document":
            if not isinstance(request["evidence_fingerprint"], str) or SHA.fullmatch(request["evidence_fingerprint"]) is None:
                _abort("desktop_cash_coverage_input_invalid")
        elif request["evidence_fingerprint"] is not None:
            _abort("desktop_cash_coverage_input_invalid")
    context, _, catalog = _catalog(canonical_path, context_value)
    scope = _scope(request, catalog)
    data_space = _owner_directory(data_space_path)
    store = _store_path(data_space)
    if not store.exists():
        _abort("desktop_cash_coverage_event_outside_period")
    connection = _open_store(store, context, read_only=True)
    try:
        periods = _account_periods(connection, scope["account_id"])
        period = _covering(periods, as_of)
        if period is None or period["cash_asset_id"] != scope["cash_asset_id"]:
            _abort("desktop_cash_coverage_event_outside_period")
        if period["coverage_mode"] not in {"partial", "complete_reconciled"}:
            _abort("desktop_cash_coverage_mode_invalid")
        events = [row for row in _account_events(connection, scope["account_id"]) if _in_period(row, period, as_of)]
        openings = [row for row in _account_events(connection, scope["account_id"])
                    if row["event_type"] == "opening_balance" and row["account_id"] == scope["account_id"] and _in_period(row, period)]
        movement = sum((_delta(row, scope["account_id"]) for row in events if row["event_type"] != "opening_balance"), Decimal(0))
        existing_opening = Decimal(openings[0]["amount_decimal"]) if len(openings) == 1 else None
        period_record = _record_ref(period["command_id"])
        opening_records = [_record_ref(row["command_id"]) for row in openings]
    finally:
        connection.close()
    explanation: dict[str, Any] = {
        "coverage_mode_before": period["coverage_mode"], "coverage_mode_after": "complete_reconciled",
        "effective_from": period["effective_from"], "effective_to": period["effective_to"], "as_of_date": as_of,
        "movement_delta_decimal": _plain(movement), "cash_event_count": len(events),
        "evidence_kind": kind, "balance_checked": not asserted,
    }
    result_base = {"desktop_cash_check_balance_version": 1, **FLAGS}
    if period["coverage_mode"] == "complete_reconciled":
        if existing_opening is None:
            _abort("desktop_cash_coverage_store_invalid")
        computed = existing_opening + movement
        observed_value = computed if asserted else observed
        explanation.update(operation="record_reconciliation", opening_balance_decimal=_plain(existing_opening),
                           opening_balance_origin="existing_opening", computed_balance_decimal=_plain(computed),
                           observed_balance_decimal=_plain(observed_value))
        if observed_value != computed:
            # Die eigentliche Auskunft eines Pruef-Saldos: um wie viel die Buchungen abweichen.
            explanation["difference_decimal"] = _plain(observed_value - computed)
            return {**result_base, "status": "balance_mismatch", "command": None, "preview": None, "explanation": explanation}
        fingerprint = request["evidence_fingerprint"] if kind == "document" else desktop_cash_evidence_fingerprint_v1(
            kind, scope["portfolio_id"], scope["account_id"], scope["cash_asset_id"], as_of, _plain(observed_value))
        command: dict[str, Any] = {
            "action_type": "record_reconciliation", "request_ref": request["request_ref"], "input_mode": "manual_entry",
            "source_candidate_fingerprint": None, **scope, "as_of_date": as_of,
            "observed_balance_decimal": _plain(observed_value), "evidence_fingerprint": fingerprint,
        }
    else:
        if period["effective_to"] is not None and as_of != period["effective_to"]:
            # Ein geschlossener Zeitraum wird an seinem Ende abgestimmt.
            explanation["required_as_of_date"] = period["effective_to"]
            return {**result_base, "status": "closed_period_reconciles_at_end", "command": None, "preview": None, "explanation": explanation}
        if asserted:
            opening = existing_opening if existing_opening is not None else Decimal(0)
            origin = "existing_opening" if existing_opening is not None else "assumed_zero"
            observed_value = opening + movement
        else:
            opening = observed - movement
            origin = "derived_from_check_balance"
            observed_value = observed
        explanation.update(operation="raise_partial_to_reconciled", opening_balance_decimal=_plain(opening),
                           opening_balance_origin=origin, computed_balance_decimal=_plain(opening + movement),
                           observed_balance_decimal=_plain(observed_value),
                           previous_opening_balance_decimal=None if existing_opening is None else _plain(existing_opening))
        fingerprint = request["evidence_fingerprint"] if kind == "document" else desktop_cash_evidence_fingerprint_v1(
            kind, scope["portfolio_id"], scope["account_id"], scope["cash_asset_id"], as_of, _plain(observed_value))
        command = {
            "action_type": "supersede", "request_ref": request["request_ref"], "input_mode": "manual_entry",
            "source_candidate_fingerprint": None, "predecessor_refs": [period_record, *opening_records],
            "replacements": [{
                "action_type": "declare_coverage", **scope, "effective_from": period["effective_from"],
                "effective_to": period["effective_to"], "coverage_mode": "complete_reconciled",
                "opening_balance_decimal": _plain(opening), "opening_event_time_evidence": "exact_local_zone",
                # Stand vor der ersten Bewegung des ersten Tages.
                "opening_local_time": "00:00:00", "opening_time_zone": TIME_ZONE,
                "opening_effective_at_utc": _utc(period["effective_from"], "00:00:00"),
                "reconciliation_as_of_date": as_of, "observed_balance_decimal": _plain(observed_value),
                "evidence_fingerprint": fingerprint,
            }],
        }
    preview = preview_desktop_cash_coverage_command_v1(canonical_path, data_space_path, context_value, command)
    return {**result_base, "status": "ready_for_confirmation", "command": command, "preview": preview, "explanation": explanation}


def prepare_desktop_cash_manual_booking_v1(
    canonical_path: str | Path, data_space_path: str | Path, context_value: Any, request_value: Any,
) -> dict[str, Any]:
    """Eine einzelne Cash-Buchung aus Konto, Datum, Betrag und Art.

    Hat das Konto noch keinen Abdeckungszeitraum, legt die Buchung ihn als
    `partial` ab ihrem Tag an, statt abgewiesen zu werden. Eine Zinsgutschrift sind
    zwei Fakten: das Cash-Ereignis und das Zins-Income. Alles zusammen ist ein
    Vorgang mit einer Bestaetigung.

    Die Flussklassifikation wird nicht geraten: Zugang und Abgang bleiben
    `unclassified`; nur die Art "Zins" sagt selbst, was sie ist.
    """
    request = _strict(request_value, {"request_ref", "portfolio_id", "account_id", "cash_asset_id", "local_date", "kind", "amount_decimal"})
    if not isinstance(request["request_ref"], str) or REQUEST.fullmatch(request["request_ref"]) is None:
        _abort("desktop_cash_coverage_input_invalid")
    if request["kind"] not in BOOKING_KINDS:
        _abort("desktop_cash_coverage_input_invalid")
    day = _date(request["local_date"])
    amount = _decimal(request["amount_decimal"], positive=True)
    context, _, catalog = _catalog(canonical_path, context_value)
    scope = _scope(request, catalog)
    data_space = _owner_directory(data_space_path)
    store = _store_path(data_space)
    periods: list[Any] = []
    used_times: set[str] = set()
    reconciled_through: str | None = None
    period = None
    if store.exists():
        connection = _open_store(store, context, read_only=True)
        try:
            periods = _account_periods(connection, scope["account_id"])
            period = _covering(periods, day)
            used_times = {row["local_time"] for row in _account_events(connection, scope["account_id"])
                          if row["account_id"] == scope["account_id"] and row["local_date"] == day and row["local_time"]}
            if period is not None and period["coverage_mode"] == "complete_reconciled":
                dates = [row["as_of_date"] for row in _reconciliations(connection, scope["account_id"], period)]
                reconciled_through = max(dates) if dates else None
        finally:
            connection.close()
    explanation: dict[str, Any] = {"kind": request["kind"], "local_date": day, "amount_decimal": amount,
                                   "declares_coverage": False, "coverage_mode": None if period is None else period["coverage_mode"]}
    result_base = {"desktop_cash_manual_booking_version": 1, **FLAGS}
    if periods and period is None:
        # Das Konto ist abgedeckt, nur nicht an diesem Tag. Den Zeitraum hier
        # stillschweigend zu verlaengern haette bei einem abgestimmten Zeitraum
        # die Eroeffnung verschoben.
        explanation["covered_from"] = min(row["effective_from"] for row in periods)
        return {**result_base, "status": "outside_coverage", "commands": None, "preview": None, "explanation": explanation}
    if period is not None and period["coverage_mode"] not in {"partial", "complete_reconciled"}:
        return {**result_base, "status": "coverage_mode_excludes_cash_events", "commands": None, "preview": None, "explanation": explanation}
    if reconciled_through is not None and day <= reconciled_through:
        # Jede Buchung am oder vor einem abgestimmten Tag veraendert den Saldo, der
        # dort als geprueft festgehalten ist. Das ist eine Korrektur der Historie
        # und laeuft ueber den Korrekturweg, nicht ueber eine neue Buchung.
        explanation["reconciled_through"] = reconciled_through
        return {**result_base, "status": "before_reconciled_state", "commands": None, "preview": None, "explanation": explanation}
    position = 0
    while (datetime(2000, 1, 1, 12, 0, 0) + timedelta(seconds=position)).strftime("%H:%M:%S") in used_times:
        position += 1
    local_time = (datetime(2000, 1, 1, 12, 0, 0) + timedelta(seconds=position)).strftime("%H:%M:%S")
    explanation["local_time"] = local_time
    commands: list[dict[str, Any]] = []
    manual = {"input_mode": "manual_entry", "source_candidate_fingerprint": None}
    if not periods:
        explanation.update(declares_coverage=True, coverage_mode="partial", covered_from=day)
        commands.append({"action_type": "declare_coverage", "request_ref": _request(request["request_ref"], len(commands)), **manual, **scope,
                         "effective_from": day, "effective_to": None, "coverage_mode": "partial",
                         "opening_balance_decimal": None, "opening_event_time_evidence": None, "opening_local_time": None,
                         "opening_time_zone": None, "opening_effective_at_utc": None, "reconciliation_as_of_date": None,
                         "observed_balance_decimal": None, "evidence_fingerprint": None})
    interest = request["kind"] == "interest"
    commands.append({"action_type": "record_cash_event", "request_ref": _request(request["request_ref"], len(commands)), **manual, **scope,
                     "event_type": "withdrawal" if request["kind"] == "withdrawal" else "deposit", "related_account_id": None,
                     "event_time_evidence": "exact_local_zone", "local_date": day, "local_time": local_time,
                     "time_zone": TIME_ZONE, "effective_at_utc": _utc(day, local_time), "amount_decimal": amount,
                     "flow_classification": "income_receipt" if interest else "unclassified"})
    if interest:
        commands.append({"action_type": "record_interest_income", "request_ref": _request(request["request_ref"], len(commands)), **manual, **scope,
                         "local_date": day, "gross_income_decimal": amount, "linked_cash_event_ref": None})
    explanation["command_count"] = len(commands)
    preview = preview_desktop_cash_coverage_manual_batch_v1(canonical_path, data_space_path, context_value, commands)
    return {**result_base, "status": "ready_for_confirmation", "commands": commands, "preview": preview, "explanation": explanation}


def _opening_facts(period: Any, opening: Any | None, reconciliations: list[Any], provenance: Mapping[str, str]) -> dict[str, Any]:
    """Anfangssaldo eines Zeitraums, seine Herkunft und ab wann der Zeitraum abgeglichen ist (#529, Festlegung 31.10.2026).

    Herkunft: "statement" (aus dem Auszug, auch ein beim Import bestaetigter Saldo - der Speicher trennt beides nicht),
    "check_balance" (aus einem Pruef-Saldo abgeleitet), "assumed" (ohne Saldo angenommen), "manual" (eigene Angabe).
    Abgeglichen ab: nur ein vollstaendig abgeglichener Zeitraum; der Import setzt den Anfangssaldo auf den Vortag.
    """
    if opening is None:
        origin = None
    elif any(desktop_cash_evidence_kind_v1(row) == "owner_asserted_without_balance" for row in reconciliations):
        origin = "assumed"
    elif provenance.get(opening["command_id"]) == "reviewed_import" or (opening["command_id"] not in provenance and opening["local_time"] == "23:59:00"):
        origin = "statement"
    elif opening["local_time"] == "00:00:00":
        origin = "check_balance"
    else:
        origin = "manual"
    reconciled_from = None
    if period["coverage_mode"] == "complete_reconciled":
        start = date.fromisoformat(period["effective_from"])
        if opening is not None and opening["local_date"] == period["effective_from"] and opening["local_time"] == "23:59:00":
            start += timedelta(days=1)
        reconciled_from = start.isoformat()
    return {"opening_balance_decimal": None if opening is None else opening["amount_decimal"], "opening_origin": origin,
            "reconciled_from_date": reconciled_from}


def read_desktop_cash_evidence_overview_v1(
    canonical_path: str | Path, data_space_path: str | Path, context_value: Any, as_of_date: Any,
) -> dict[str, Any]:
    """Je Konto: bis wann ist der Saldo belegt, und womit.

    Eine Abdeckung laeuft nach vorn offen weiter, auch wenn der letzte Nachweis
    Monate alt ist. "Bis hier belegt" und "danach unveraendert angenommen" sind
    zwei Aussagen; diese Uebersicht trennt sie (#417).
    """
    today = _date(as_of_date)
    context, _, catalog = _catalog(canonical_path, context_value)
    data_space = _owner_directory(data_space_path)
    store = _store_path(data_space)
    result = {"desktop_cash_evidence_overview_version": 1, "as_of_date": today, "internal_id_exposed": False, **FLAGS}
    if not store.exists():
        return {**result, "status": "absent", "accounts": []}
    rows: list[dict[str, Any]] = []
    connection = _open_store(store, context, read_only=True)
    try:
        periods = _active_rows(connection, "coverage_period", "account_id,effective_from,coverage_id")
        events = _active_rows(connection, "cash_event", "effective_at_utc,cash_event_id")
        reconciliations = _active_rows(connection, "reconciliation", "account_id,as_of_date,reconciliation_id")
        # Woher ein Anfangssaldo stammt (#529): aus einem geprueften Import, sonst aus einer eigenen Eingabe. Aeltere Befehle ohne
        # Herkunft erkennt die Uhrzeit: Der Import setzt den Anfangssaldo auf 23:59 des Vortags, „Saldo prüfen“ auf 00:00 des ersten Tags.
        provenance = {row["command_id"]: row["input_mode"] for row in connection.execute(
            "SELECT command_id,input_mode FROM cash_coverage_command_provenance")}
        for period in periods:
            account_id = period["account_id"]
            own = [row for row in reconciliations if row["account_id"] == account_id
                   and period["effective_from"] <= row["as_of_date"]
                   and (period["effective_to"] is None or row["as_of_date"] <= period["effective_to"])]
            latest = own[-1] if own else None
            days = [row["local_date"] for row in events
                    if (row["account_id"] == account_id or row["related_account_id"] == account_id)
                    and row["event_type"] != "opening_balance" and _in_period(row, period)]
            proven = None if latest is None else latest["as_of_date"]
            opening = next((row for row in events if row["event_type"] == "opening_balance" and row["account_id"] == account_id
                            and _in_period(row, period)), None)
            rows.append({
                **_opening_facts(period, opening, own, provenance),
                "account_label": catalog["accounts"][account_id]["display_name"],
                "cash_asset_label": catalog["assets"][period["cash_asset_id"]]["display_name"],
                "coverage_mode": period["coverage_mode"], "effective_from": period["effective_from"],
                "effective_to": period["effective_to"], "open_ended": period["effective_to"] is None,
                "proven_through_date": proven,
                "proven_balance_decimal": None if latest is None else latest["observed_balance_decimal"],
                "evidence_kind": None if latest is None else desktop_cash_evidence_kind_v1(latest),
                # Nicht "last_...": Der Name enthielte "ast_" und saehe in jeder
                # Pruefung auf nach aussen gereichte Asset-IDs wie ein Treffer aus.
                "latest_movement_date": max(days) if days else None,
                "movement_after_proof_count": 0 if proven is None else sum(1 for day in days if day > proven),
                "proof_age_days": None if proven is None else (date.fromisoformat(today) - date.fromisoformat(proven)).days,
            })
    finally:
        connection.close()
    rows.sort(key=lambda row: (row["proven_through_date"] or "", row["account_label"]))
    return {
        **result, "status": "available", "accounts": rows,
        "period_count": len(rows),
        "unreconciled_count": sum(1 for row in rows if row["proven_through_date"] is None),
        "asserted_without_balance_count": sum(1 for row in rows if row["evidence_kind"] == "owner_asserted_without_balance"),
        "oldest_proof_date": min((row["proven_through_date"] for row in rows if row["proven_through_date"]), default=None),
    }


__all__ = [
    "DesktopCashCoverageV1Error",
    "prepare_desktop_cash_check_balance_v1",
    "prepare_desktop_cash_manual_booking_v1",
    "read_desktop_cash_evidence_overview_v1",
]
