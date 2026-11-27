"""Fortschreibbarer Bewertungsstand: rechnen, was neu ist, nicht was schon steht.

Der Stand haelt je Bereich (Asset an einer Notierung unter einer Richtlinie) die
bewertete Tagesreihe und den Uebertrag, mit dem der naechste Tag weitergerechnet
wird. Weil ein Tag ausschliesslich von Tagen <= ihm abhaengt
(`valuation_day_step`), ist Anhaengen zulaessig.

Beide Wege - Neuaufbau und Fortschreibung - benutzen dieselbe Schrittfunktion.
Deshalb muss zwingend dasselbe herauskommen, und genau das fuehrt der
Vertragstest als Gleichheitsprobe (#283, 26.09.2026).

Das Modul liest keine Kursspeicher und ruft nichts ab. Es bekommt die Tagesreihen
gereicht und schreibt den Stand; wer die Reihen besorgt, entscheidet der Aufrufer.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
import hashlib
import json
import os
import sqlite3
import stat

from migrations.reference.market_valuation_projection_v1 import (
    convert_series,
    effective_series,
    valuation_policy,
)
import migrations.reference.market_valuation_projection_v1 as projection

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "contracts" / "market-valuation-state" / "v1" / "schema.sql"
SCHEMA_VERSION = 105
ALGORITHM_ID = "market_valuation_projection_v1"

FAILURE_CODES = frozenset({
    "market_valuation_state_input_invalid",
    "market_valuation_state_store_invalid",
    "market_valuation_state_algorithm_changed",
    "market_valuation_state_schema_changed",
    "market_valuation_state_scope_invalid",
    "market_valuation_state_carry_invalid",
})


class MarketValuationStateBlocked(RuntimeError):
    def __init__(self, code: str):
        if code not in FAILURE_CODES:
            raise ValueError("market_valuation_state_error_unregistered")
        self.code = code
        super().__init__(code)


def market_valuation_state_error_codes_v1() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _abort(code: str) -> None:
    raise MarketValuationStateBlocked(code)


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    except (TypeError, ValueError):
        _abort("market_valuation_state_input_invalid")


def _sha(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else _canonical(value)).hexdigest()


def _utc(value: str) -> str:
    if not isinstance(value, str) or len(value) != 20 or not value.endswith("Z"):
        _abort("market_valuation_state_input_invalid")
    return value


def _day(value: str) -> str:
    if not isinstance(value, str) or len(value) != 10:
        _abort("market_valuation_state_input_invalid")
    try:
        if date.fromisoformat(value).isoformat() != value:
            _abort("market_valuation_state_input_invalid")
    except ValueError:
        _abort("market_valuation_state_input_invalid")
    return value


def market_valuation_state_context_fingerprint_v1(context: Mapping[str, str]) -> str:
    if not isinstance(context, Mapping) or set(context) != {"tenant_id", "user_id", "data_space_id"}:
        _abort("market_valuation_state_input_invalid")
    return _sha({"contract": "market_valuation_state_context_v1", **dict(context)})


def market_valuation_algorithm_fingerprint_v1() -> str:
    """Fingerprint ueber den Quelltext der Rechenfunktionen.

    Aendert sich die Rechnung, passt ein bestehender Stand nicht mehr. Das faellt
    dann auf, statt sich als stille Abweichung durch die Zahlen zu ziehen.
    """
    source = Path(projection.__file__).read_bytes()
    return _sha({"contract": "market_valuation_algorithm_v1", "module": ALGORITHM_ID,
                 "source": hashlib.sha256(source).hexdigest()})


def valuation_policy_fingerprint_v1(profile: Mapping[str, Any], max_age: int, policy: Any) -> str:
    """Was die Rechnung sonst noch bestimmt: Kalenderprofil, Altersgrenze, Richtlinie.

    Das Gueltigkeitsfenster des Profils bleibt aussen vor - es waechst mit jedem
    Tag, waehrend die Schliesstage darin dieselben bleiben. Sonst waere der Stand
    taeglich ungueltig, obwohl sich nichts geaendert hat.
    """
    if not isinstance(profile, Mapping):
        _abort("market_valuation_state_input_invalid")
    if type(max_age) is not int or not 0 <= max_age <= 366:
        _abort("market_valuation_state_input_invalid")
    try:
        resolved = valuation_policy(policy)
    except ValueError:
        _abort("market_valuation_state_input_invalid")
    return _sha({
        "contract": "market_valuation_policy_v1",
        "calendar_kind": profile.get("calendar_kind"),
        "market_code": profile.get("market_code"),
        "timezone_name": profile.get("timezone_name"),
        "session_weekdays": profile.get("session_weekdays"),
        "closure_dates": profile.get("closure_dates"),
        "special_open_dates": profile.get("special_open_dates"),
        "source_ref": profile.get("source_ref"),
        "max_age_days": max_age,
        "valuation_policy": resolved,
    })


def valuation_scope_ref_v1(asset_id: str, listing_ref: str) -> str:
    """Der Bereich haengt an der kanonischen Assetkennung.

    Nicht an der laufenden Nummer der Katalogansicht: Die wird nach Listenposition
    vergeben und verschiebt sich, sobald ein Asset hinzukommt.
    """
    return "vsc_" + _sha({"contract": "market_valuation_scope_v1", "asset_id": asset_id,
                          "listing_ref": listing_ref})[:32]


def _regular(path: str | Path, *, new: bool = False) -> Path:
    target = Path(path)
    if not target.is_absolute():
        _abort("market_valuation_state_store_invalid")
    if target.is_symlink():
        _abort("market_valuation_state_store_invalid")
    if new:
        if target.exists():
            _abort("market_valuation_state_store_invalid")
        return target
    if not target.is_file():
        _abort("market_valuation_state_store_invalid")
    if stat.S_IMODE(target.stat().st_mode) != 0o600:
        _abort("market_valuation_state_store_invalid")
    return target


def bootstrap_market_valuation_state_v1(path: str | Path, context: Mapping[str, str], created_at_utc: str) -> Path:
    fingerprint = market_valuation_state_context_fingerprint_v1(context)
    _utc(created_at_utc)
    target = _regular(path, new=True)
    descriptor = None
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        os.close(descriptor)
        descriptor = None
        connection = sqlite3.connect(target)
        connection.executescript(SCHEMA.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO valuation_state_binding VALUES (1,?,?,?,?,?)",
            (SCHEMA_VERSION, fingerprint, ALGORITHM_ID, market_valuation_algorithm_fingerprint_v1(), created_at_utc),
        )
        connection.commit()
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            _abort("market_valuation_state_store_invalid")
        connection.close()
        os.chmod(target, 0o600)
        return target
    except MarketValuationStateBlocked:
        Path(target).unlink(missing_ok=True)
        raise
    except Exception as error:
        if descriptor is not None:
            os.close(descriptor)
        Path(target).unlink(missing_ok=True)
        raise MarketValuationStateBlocked("market_valuation_state_store_invalid") from error


def read_carry_across_blocked_v1(connection: sqlite3.Connection) -> bool:
    """Ob ein gesperrter Tag den Vorgaenger loescht. Voreinstellung: ja, wie bisher."""
    row = connection.execute(
        "SELECT carry_across_blocked FROM snapshot_setting WHERE singleton_id = 1"
    ).fetchone()
    return False if row is None else bool(row[0])


def write_carry_across_blocked_v1(connection: sqlite3.Connection, value: bool, updated_at_utc: str) -> bool:
    """Setzt den Schalter.

    Ein gesperrter Tag bleibt in jedem Fall ohne Wert. Der Schalter entscheidet
    nur, ob die Sperre auch die Tage danach ansteckt: Eine offene Pruefung sagt
    nichts ueber den Kurs des Vortages, der ein Fakt bleibt (#368, 28.09.2026).

    Die Umstellung aendert den Richtlinien-Fingerabdruck, und der Stand rechnet
    die betroffenen Bereiche daraufhin neu - nicht stillschweigend gemischt.
    """
    if type(value) is not bool:
        _abort("market_valuation_state_input_invalid")
    if not isinstance(updated_at_utc, str) or len(updated_at_utc) != 20 or not updated_at_utc.endswith("Z"):
        _abort("market_valuation_state_input_invalid")
    connection.execute(
        "INSERT INTO snapshot_setting (singleton_id, carry_across_blocked, updated_at_utc) "
        "VALUES (1, ?, ?) ON CONFLICT(singleton_id) DO UPDATE SET "
        "carry_across_blocked = excluded.carry_across_blocked, updated_at_utc = excluded.updated_at_utc",
        (1 if value else 0, updated_at_utc),
    )
    return value


def open_market_valuation_state_v1(path: str | Path, context: Mapping[str, str]) -> sqlite3.Connection:
    """Oeffnet den Stand und prueft Bindung und Rechenfassung."""
    fingerprint = market_valuation_state_context_fingerprint_v1(context)
    target = _regular(path)
    connection = sqlite3.connect(target)
    connection.execute("PRAGMA foreign_keys = ON")
    row = connection.execute(
        "SELECT schema_version, context_fingerprint, algorithm_id, algorithm_fingerprint FROM valuation_state_binding WHERE singleton_id = 1"
    ).fetchone()
    if row is not None and row[0] != SCHEMA_VERSION:
        connection.close()
        # Ein Stand aelteren Aufbaus wird neu erstellt, nicht weitergenutzt.
        _abort("market_valuation_state_schema_changed")
    if row is None or row[1] != fingerprint or row[2] != ALGORITHM_ID:
        connection.close()
        _abort("market_valuation_state_store_invalid")
    if row[3] != market_valuation_algorithm_fingerprint_v1():
        connection.close()
        # Kein stiller Weiterbetrieb: Der Stand stammt aus einer anderen Rechnung.
        _abort("market_valuation_state_algorithm_changed")
    return connection


def _carry_from_row(row: Sequence[Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    resume_from, previous_date, previous_value, crossed_gap = row
    return {"previous_date": previous_date, "previous_value": previous_value,
            "crossed_gap": bool(crossed_gap), "resume_from": resume_from}


def read_fx_effective_from_v1(connection: sqlite3.Connection, pair_ref: str) -> str | None:
    """Der erste Tag, ab dem der Vektor eines Waehrungspaares gefaltet ist.

    Der Vektor gehoert dem Paar, nicht dem Asset: Wer ihn fortschreibt, faltet
    ab hier und nicht ab dem Beginn des gerade bewerteten Assets.
    """
    row = connection.execute(
        "SELECT valued_from_date FROM fx_effective_watermark WHERE pair_ref = ?", (pair_ref,)
    ).fetchone()
    return None if row is None else row[0]


def read_valuation_scope_from_v1(connection: sqlite3.Connection, asset_id: str, listing_ref: str) -> str | None:
    """Der erste bewertete Tag eines Bereichs - oder None, wenn es ihn noch nicht gibt.

    Wer den Bereich fortschreibt, rechnet ab hier und nicht ab einem spaeteren
    verlangten Beginn: Ein Lauf verkuerzt einen schon bewerteten Zeitraum nicht.
    """
    row = connection.execute(
        "SELECT valued_from_date FROM valuation_watermark WHERE scope_ref = ?",
        (valuation_scope_ref_v1(asset_id, listing_ref),),
    ).fetchone()
    return None if row is None else row[0]


def read_latest_valuation_state_job_ref_v1(connection: sqlite3.Connection) -> str | None:
    row = connection.execute("SELECT job_ref FROM valuation_state_job ORDER BY rowid DESC LIMIT 1").fetchone()
    return None if row is None else row[0]


def _input_rows(days: Sequence[Mapping[str, Any]], blocked: Mapping[str, str] | None,
                native: Mapping[str, str] | None, kinds: Mapping[str, str] | None = None) -> list[list[Any]]:
    """Je Tag, was die Rechnung von aussen bekommt: Kurs mit Stand, Sperre, Herkunft der Notiz, Art des Kurses."""
    blocked, native, kinds = dict(blocked or {}), dict(native or {}), dict(kinds or {})
    return [[day["date"], day["status"], day["value"], blocked.get(day["date"]), native.get(day["date"]), kinds.get(day["date"])]
            for day in sorted(days, key=lambda item: item["date"])]


def _prefix_fingerprint(contract: str, inputs: str, rows: Sequence[Sequence[Any]], before: str) -> str:
    """Abdruck der Eingaenge vor `before` - der Tage, die schon im Stand stehen (#516/rc.364).

    Fortgeschrieben werden darf nur, wenn sich davor nichts geaendert hat. Bis rc.363 verglich der Stand Abdruecke ueber alle
    Anfragen und alle Tage der Notierung; ein neuer Tag aenderte sie, und jeder Lauf baute jede Reihe neu auf. Gemeinsame Eingaben (`inputs`, etwa
    offene Pruefstufen) gelten fuer alle Tage."""
    return _sha({"contract": contract, "inputs": inputs, "rows": [list(row) for row in rows if row[0] < before]})


def _pair_prefix_fingerprint(connection: sqlite3.Connection, pair_ref: str | None, before: str) -> str:
    """Der Wechselkursvektor vor `before`, wie er im Stand steht. Die EUR-Zeilen eines Bereichs entstehen aus Kurs mal diesem
    Vektor; aendert er sich fuer einen zurueckliegenden Tag, wird der Bereich neu aufgebaut."""
    if pair_ref is None:
        return _sha({"contract": "market_valuation_scope_pair_prefix_v1", "pair_ref": None})
    policy = connection.execute("SELECT policy_fingerprint FROM fx_effective_watermark WHERE pair_ref = ?", (pair_ref,)).fetchone()
    rows = connection.execute(
        "SELECT rate_date, rate_decimal, basis, source_date, age_days, calendar_reason, native_status, substitution_used "
        "FROM fx_effective_day WHERE pair_ref = ? AND rate_date < ? ORDER BY rate_date", (pair_ref, before)).fetchall()
    return _sha({"contract": "market_valuation_scope_pair_prefix_v1", "pair_ref": pair_ref,
                 "policy": None if policy is None else policy[0], "rows": [list(row) for row in rows]})


def apply_fx_effective_days_v1(
    connection: sqlite3.Connection, *, pair_ref: str, days: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any], max_age: int, policy: Any, start: str, end: str,
    consumed_request_fingerprint: str, updated_at_utc: str, mode: str,
    blocked: Mapping[str, str] | None = None,
    native_status: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Faltet ein Waehrungspaar einmal und legt den wirksamen Kurs je Tag ab.

    Alle Assets derselben Waehrung lesen danach diesen Vektor, statt ihn je Asset
    erneut herzuleiten (Festlegung 26.09.2026).
    """
    if mode not in {"full_rebuild", "incremental"}:
        _abort("market_valuation_state_input_invalid")
    _day(start), _day(end), _utc(updated_at_utc)
    policy_fingerprint = valuation_policy_fingerprint_v1(profile, max_age, policy)
    existing = connection.execute(
        "SELECT resume_from, previous_date, previous_value, crossed_gap, policy_fingerprint, consumed_request_fingerprint, valued_from_date FROM fx_effective_watermark WHERE pair_ref = ?",
        (pair_ref,),
    ).fetchone()
    requested_from = start
    carry = None
    # Fortgeschrieben wird nur, wenn weder die Richtlinie noch die Eingaenge vor dem
    # Fortsetzungstag sich geaendert haben. Eine Wechselkurskorrektur fuer einen
    # zurueckliegenden Tag loest damit einen Neuaufbau des Paares aus - ohne diese
    # Bedingung bliebe sie unbemerkt (26.09.2026, #283). Ein neuer Tag dagegen wird
    # angehaengt (rc.364): `consumed_request_fingerprint` traegt die gemeinsamen
    # Eingaenge des Paares, die Tage kommen aus `days`, `blocked` und `native_status`.
    rows = _input_rows(days, blocked, native_status)
    unchanged = (existing is not None and existing[4] == policy_fingerprint and existing[6] <= start
                 and existing[5] == _prefix_fingerprint("market_valuation_pair_prefix_v1", consumed_request_fingerprint, rows, existing[0]))
    if mode == "incremental" and unchanged:
        carry = _carry_from_row(existing[:4])
        if carry["resume_from"] > end:
            return {"pair_ref": pair_ref, "written_day_count": 0, "mode": "incremental",
                    "resume_from": carry["resume_from"]}
        start = carry["resume_from"]
    else:
        # Nur die Tage weg, der Wasserstand bleibt: Die Bereiche verweisen auf ihn,
        # und ein Neuaufbau des Paares darf sie nicht mitreissen.
        connection.execute("DELETE FROM fx_effective_day WHERE pair_ref = ?", (pair_ref,))
        mode = "full_rebuild"
    series, next_carry = effective_series(
        [day for day in days if day["date"] <= end], profile, start, end, max_age, dict(blocked or {}),
        gap_policy=policy, carry=carry, with_carry=True,
    )
    # Gespeichert wird der Abdruck bis zum neuen Fortsetzungstag; der naechste Lauf vergleicht damit.
    consumed_request_fingerprint = _prefix_fingerprint("market_valuation_pair_prefix_v1", consumed_request_fingerprint, rows,
                                                       next_carry["resume_from"])
    if existing is None:
        connection.execute(
            "INSERT INTO fx_effective_watermark VALUES (?,?,?,?,?,?,?,?,?,?)",
            (pair_ref, policy_fingerprint, requested_from, end, next_carry["resume_from"],
             next_carry["previous_date"], next_carry["previous_value"], int(next_carry["crossed_gap"]),
             consumed_request_fingerprint, updated_at_utc),
        )
    else:
        connection.execute(
            "UPDATE fx_effective_watermark SET policy_fingerprint = ?, valued_from_date = ?, valued_through_date = ?, resume_from = ?, previous_date = ?, previous_value = ?, crossed_gap = ?, consumed_request_fingerprint = ?, updated_at_utc = ? WHERE pair_ref = ?",
            # Der Wasserstand nennt den ersten Tag, der wirklich im Vektor steht. Nach
            # einem Neuaufbau ist das der Beginn dieses Aufbaus; bis rc.240 blieb hier
            # der frueheste je verlangte Beginn stehen, auch wenn die Tage davor
            # geloescht waren - er nannte dann einen Tag,
            # an dem der Vektor noch gar nicht begann.
            (policy_fingerprint, existing[6] if carry is not None else requested_from,
             end, next_carry["resume_from"], next_carry["previous_date"], next_carry["previous_value"],
             int(next_carry["crossed_gap"]), consumed_request_fingerprint, updated_at_utc, pair_ref),
        )
    status_by_date = dict(native_status or {})
    connection.executemany(
        "INSERT INTO fx_effective_day VALUES (?,?,?,?,?,?,?,?,?)",
        [(pair_ref, key, entry["value"], entry["basis"], entry["source_date"], entry["age_days"],
          entry["calendar_reason"], status_by_date.get(key), int(entry["substitution_used"]))
         for key, entry in sorted(series.items())],
    )
    return {"pair_ref": pair_ref, "written_day_count": len(series), "mode": mode,
            "resume_from": next_carry["resume_from"]}


def _fx_rates(connection: sqlite3.Connection, pair_ref: str, start: str, end: str) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = connection.execute(
        "SELECT rate_date, rate_decimal, basis, source_date, age_days, calendar_reason, native_status FROM fx_effective_day WHERE pair_ref = ? AND rate_date BETWEEN ? AND ? ORDER BY rate_date",
        (pair_ref, start, end),
    ).fetchall()
    rates = {r[0]: {"date": r[0], "value": r[1], "basis": r[2], "source_date": r[3], "age_days": r[4],
                    "calendar_reason": r[5]} for r in rows}
    return rates, {r[0]: r[6] for r in rows}


def apply_valuation_scope_days_v1(
    connection: sqlite3.Connection, *, asset_id: str, listing_ref: str, quote_currency: str,
    provider_symbol: str, pair_ref: str | None, direction: str, price_days: Sequence[Mapping[str, Any]],
    profile: Mapping[str, Any], max_age: int, policy: Any, blocked: Mapping[str, str] | None,
    start: str, end: str, consumed_request_fingerprint: str, barrier_fingerprint: str,
    updated_at_utc: str, mode: str,
    price_native_status: Mapping[str, str] | None = None,
    price_source_kind: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Rechnet die fehlenden Tage eines Bereichs und haengt sie an."""
    if mode not in {"full_rebuild", "incremental"}:
        _abort("market_valuation_state_input_invalid")
    if direction not in {"identity", "direct", "inverse"}:
        _abort("market_valuation_state_input_invalid")
    if (quote_currency == "EUR") != (pair_ref is None) or (direction == "identity") != (pair_ref is None):
        _abort("market_valuation_state_scope_invalid")
    if not isinstance(provider_symbol, str) or not 1 <= len(provider_symbol) <= 64:
        _abort("market_valuation_state_input_invalid")
    _day(start), _day(end), _utc(updated_at_utc)
    policy_fingerprint = valuation_policy_fingerprint_v1(profile, max_age, policy)
    scope_ref = valuation_scope_ref_v1(asset_id, listing_ref)
    connection.execute(
        "INSERT OR IGNORE INTO valuation_scope VALUES (?,?,?,?,?,?,?,?)",
        (scope_ref, asset_id, listing_ref, provider_symbol, quote_currency, "EUR", pair_ref, direction),
    )
    existing = connection.execute(
        "SELECT resume_from, previous_date, previous_value, crossed_gap, consumed_request_fingerprint, barrier_fingerprint, pair_fingerprint, valued_from_date, policy_fingerprint FROM valuation_watermark WHERE scope_ref = ?",
        (scope_ref,),
    ).fetchone()
    carry = None
    recomputed = 0
    # Fortgeschrieben wird nur, wenn sich vor dem Fortsetzungstag nichts geaendert hat (rc.364): Kurse samt Stand, Sperren,
    # Herkunft und Art je Tag, die gemeinsamen Eingaenge (`barrier_fingerprint`, etwa offene Pruefstufen), die Richtlinie und
    # der Wechselkursvektor. Der Abdruck der verbrauchten Anfragen waechst mit jedem Abruf; er bleibt fuer die Frische-Anzeige
    # gespeichert, entscheidet hier aber nicht mehr. Ein frueher verlangter Beginn ist eine Aenderung wie jede andere: Die Tage
    # davor stehen noch nicht im Stand und muessen gerechnet werden.
    rows_in = _input_rows(price_days, blocked, price_native_status, price_source_kind)
    unchanged_inputs = (existing is not None and existing[7] <= start and existing[8] == policy_fingerprint
                        and existing[5] == _prefix_fingerprint("market_valuation_scope_prefix_v1", barrier_fingerprint, rows_in, existing[0])
                        and existing[6] == _pair_prefix_fingerprint(connection, pair_ref, existing[0]))
    if mode == "incremental" and existing is not None:
        # Nur wenn nichts Zurueckliegendes beruehrt wurde, darf angehaengt werden.
        if not unchanged_inputs:
            recomputed = connection.execute(
                "SELECT count(*) FROM valuation_day WHERE scope_ref = ?", (scope_ref,)
            ).fetchone()[0]
        else:
            carry = _carry_from_row(existing[:4])
            if carry["resume_from"] > end:
                # Nichts anzuhaengen - aber ein neuer Abruf (etwa ein bestaetigter vorlaeufiger Tag) ist verbraucht: Die
                # Frische-Anzeige vergleicht diesen Abdruck mit den Anfragen der Notierung und hielte den Bereich sonst fuer alt.
                if existing[4] != consumed_request_fingerprint:
                    connection.execute("UPDATE valuation_watermark SET consumed_request_fingerprint = ?, updated_at_utc = ? WHERE scope_ref = ?",
                                       (consumed_request_fingerprint, updated_at_utc, scope_ref))
                return {"scope_ref": scope_ref, "written_day_count": 0, "recomputed_day_count": 0,
                        "mode": "incremental", "resume_from": carry["resume_from"]}
    if carry is None:
        connection.execute("DELETE FROM valuation_day WHERE scope_ref = ?", (scope_ref,))
        connection.execute("DELETE FROM valuation_watermark WHERE scope_ref = ?", (scope_ref,))
        window_start = start
    else:
        window_start = carry["resume_from"]
    prices, next_carry = effective_series(
        [day for day in price_days if day["date"] <= end], profile, window_start, end, max_age,
        dict(blocked or {}), gap_policy=policy, carry=carry, with_carry=True,
    )
    rates, fx_status = ({}, {}) if pair_ref is None else _fx_rates(connection, pair_ref, window_start, end)
    # convert_series kennt nur direct und inverse; ohne Paar ist die Richtung
    # bedeutungslos, im Bereich heisst sie aber ausdruecklich identity.
    rows = convert_series(prices, quote_currency, "EUR", None if pair_ref is None else rates,
                          "direct" if direction == "identity" else direction)
    native = dict(price_native_status or {})
    # Die Herkunftsart gilt fuer den verwendeten Kurs. Gab es an dem Tag keinen,
    # gibt es auch nichts zu kennzeichnen - etwa an einem gesperrten Tag, dessen
    # bereinigter Schlusskurs nie zur Anwendung kam.
    kinds = dict(price_source_kind or {})
    connection.executemany(
        "INSERT INTO valuation_day VALUES (" + ",".join("?" * 23) + ")",
        [(scope_ref, r["date"], r["status"], r["target_decimal"], r["target_numerator"], r["target_denominator"],
          r["original_price"], r["effective_price"], r["price_basis"], r["price_source_date"], r["price_age_days"],
          r["price_calendar_reason"], int(r["price_on_closed_day"]), native.get(r["date"]),
          kinds.get(r["date"]) if r["effective_price"] is not None else None,
          r["fx_rate"], r["fx_basis"], r["fx_source_date"], r["fx_age_days"], r["fx_calendar_reason"],
          fx_status.get(r["date"]), int(r["substitution_used"]), r["valuation_status"]) for r in rows],
    )
    covered_from = start if carry is None else min(start, existing[7])
    # Gespeichert werden die Abdruecke bis zum neuen Fortsetzungstag; der naechste Lauf vergleicht damit.
    values = (covered_from, end, next_carry["resume_from"], next_carry["previous_date"],
              next_carry["previous_value"], int(next_carry["crossed_gap"]), policy_fingerprint,
              consumed_request_fingerprint,
              _prefix_fingerprint("market_valuation_scope_prefix_v1", barrier_fingerprint, rows_in, next_carry["resume_from"]),
              _pair_prefix_fingerprint(connection, pair_ref, next_carry["resume_from"]), updated_at_utc)
    if carry is None:
        connection.execute("INSERT INTO valuation_watermark VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (scope_ref, *values))
    else:
        connection.execute(
            "UPDATE valuation_watermark SET valued_from_date = ?, valued_through_date = ?, resume_from = ?, previous_date = ?, previous_value = ?, crossed_gap = ?, policy_fingerprint = ?, consumed_request_fingerprint = ?, barrier_fingerprint = ?, pair_fingerprint = ?, updated_at_utc = ? WHERE scope_ref = ?",
            (*values, scope_ref),
        )
    return {"scope_ref": scope_ref, "written_day_count": len(rows), "recomputed_day_count": recomputed,
            "mode": "full_rebuild" if carry is None else "incremental", "resume_from": next_carry["resume_from"]}


def read_valuation_days_v1(connection: sqlite3.Connection, scope_ref: str, start: str, end: str) -> list[dict[str, Any]]:
    """Die Tagesreihe eines Bereichs - eine Abfrage statt einer Neuberechnung."""
    _day(start), _day(end)
    cursor = connection.execute(
        "SELECT * FROM valuation_day WHERE scope_ref = ? AND trading_date BETWEEN ? AND ? ORDER BY trading_date",
        (scope_ref, start, end),
    )
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def read_valuation_rows_v1(connection: sqlite3.Connection, scope_ref: str, start: str, end: str) -> list[dict[str, Any]]:
    """Die Tagesreihe in der Form, die die Bewertung erwartet.

    Gleiche Felder und gleiche Typen wie `convert_series` sie liefert - Waehrungen
    und Richtung stehen am Bereich und werden von dort ergaenzt, statt sie in jede
    Zeile zu schreiben.
    """
    _day(start), _day(end)
    scope = connection.execute(
        "SELECT quote_currency, target_currency, direction, pair_ref FROM valuation_scope WHERE scope_ref = ?",
        (scope_ref,),
    ).fetchone()
    if scope is None:
        _abort("market_valuation_state_scope_invalid")
    quote_currency, target_currency, direction, pair_ref = scope
    rows = []
    for row in read_valuation_days_v1(connection, scope_ref, start, end):
        rows.append({
            "date": row["trading_date"], "native_currency": quote_currency,
            "target_currency": target_currency,
            "substitution_used": bool(row["substitution_used"]),
            "valuation_status": row["valuation_status"],
            "original_price": row["original_price"], "effective_price": row["effective_price"],
            "price_basis": row["price_basis"], "price_source_date": row["price_source_date"],
            "price_age_days": row["price_age_days"],
            "price_calendar_reason": row["price_calendar_reason"],
            "price_on_closed_day": bool(row["price_on_closed_day"]),
            "fx_rate": row["fx_rate"], "fx_basis": row["fx_basis"],
            "fx_source_date": row["fx_source_date"], "fx_age_days": row["fx_age_days"],
            "fx_calendar_reason": row["fx_calendar_reason"],
            "direction": "identity" if pair_ref is None else direction,
            "status": row["status"], "target_decimal": row["target_decimal"],
            "target_numerator": row["target_numerator"],
            "target_denominator": row["target_denominator"],
        })
        for optional in ("price_native_status", "price_source_kind", "fx_native_status"):
            if row[optional] is not None:
                rows[-1][optional] = row[optional]
    return rows


def read_valuation_summary_v1(connection: sqlite3.Connection, scope_ref: str, start: str, end: str) -> dict[str, Any]:
    """Die Zahlen der Bilanzzeile, ohne die Tagesliste zu holen."""
    _day(start), _day(end)
    row = connection.execute(
        """SELECT count(*), sum(target_decimal IS NOT NULL), sum(substitution_used),
                  sum(target_decimal IS NULL),
                  sum(price_basis != 'observed' AND target_decimal IS NOT NULL AND substitution_used = 0),
                  sum(price_basis = 'observed' AND fx_basis NOT IN ('identity','observed') AND target_decimal IS NOT NULL AND substitution_used = 0)
           FROM valuation_day WHERE scope_ref = ? AND trading_date BETWEEN ? AND ?""",
        (scope_ref, start, end),
    ).fetchone()
    day_count = row[0] or 0
    return {"scope_ref": scope_ref, "day_count": day_count, "valued_day_count": row[1] or 0,
            "substituted_day_count": row[2] or 0, "unavailable_day_count": row[3] or 0,
            "carried_price_day_count": row[4] or 0, "carried_rate_day_count": row[5] or 0}


def record_valuation_state_job_v1(
    connection: sqlite3.Connection, *, request_mode: str, prior_job_ref: str | None, scope_count: int,
    appended_day_count: int, recomputed_day_count: int, requested_at_utc: str,
) -> dict[str, Any]:
    if request_mode not in {"full_rebuild", "incremental"}:
        _abort("market_valuation_state_input_invalid")
    _utc(requested_at_utc)
    payload = {"contract": "market_valuation_state_job_v1", "request_mode": request_mode,
               "prior_job_ref": prior_job_ref, "algorithm_fingerprint": market_valuation_algorithm_fingerprint_v1(),
               "scope_count": scope_count, "appended_day_count": appended_day_count,
               "recomputed_day_count": recomputed_day_count, "requested_at_utc": requested_at_utc}
    job_fingerprint = _sha(payload)
    job_ref = "vsj_" + job_fingerprint[:32]
    connection.execute(
        "INSERT INTO valuation_state_job VALUES (?,?,?,?,?,?,?,?,?)",
        (job_ref, request_mode, prior_job_ref, payload["algorithm_fingerprint"], scope_count,
         appended_day_count, recomputed_day_count, requested_at_utc, job_fingerprint),
    )
    return {**payload, "job_ref": job_ref, "job_fingerprint": job_fingerprint}


__all__ = [
    "MarketValuationStateBlocked",
    "apply_fx_effective_days_v1",
    "read_fx_effective_from_v1",
    "read_valuation_scope_from_v1",
    "read_latest_valuation_state_job_ref_v1",
    "apply_valuation_scope_days_v1",
    "bootstrap_market_valuation_state_v1",
    "market_valuation_algorithm_fingerprint_v1",
    "market_valuation_state_context_fingerprint_v1",
    "market_valuation_state_error_codes_v1",
    "open_market_valuation_state_v1",
    "read_valuation_days_v1",
    "read_valuation_rows_v1",
    "read_valuation_summary_v1",
    "record_valuation_state_job_v1",
    "valuation_policy_fingerprint_v1",
    "valuation_scope_ref_v1",
]
