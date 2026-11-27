#!/usr/bin/env python3
"""Pflegestand je Asset und Verwahrkonto - nur lesend (#423, Schritt 1).

Beantwortet die Frage "bis wann sind die Transaktionen dieses Assets auf diesem
Konto abgeglichen". Das Datum der letzten Buchung beantwortet sie nicht: Viele
Assets haben monatelang keine Buchung, und
daran ist nicht zu erkennen, ob nichts passiert ist oder ob niemand nachgesehen
hat.

Zwei Spuren je Paar, getrennt gepflegt, wirksam ist das Minimum:

  reward  - vom Reward-Import gesetzt
  trade   - vom Eigentuemer erklaert (Kauf, Verkauf, Dividende, Transfer)

Die Trennung ist der Grund, warum sich Reward-Import und Handpflege nicht in die
Quere kommen: keine Quelle beschreibt das Feld der anderen. Dass ein Asset
Rewards bis zu einem Tag traegt, macht seine Kaeufe nicht abgeglichen. Cash bleibt
ganz ausserhalb - eigene Domaene mit eigenem Coverage.

Ohne Pflegeerklaerungen liefert der Leser jedes Paar als `not_maintained` und
dazu seine letzte Buchung je Spur. Das ist schon die halbe Auskunft: wo der
Broker-Durchgang anfangen muss.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

AREA_NAME = "asset-maintenance-state-v1"
STORE_NAME = "declarations.json"
RUNS_NAME = "maintenance-runs.json"
LEDGER_NAME = "portfolio-ledger-v401.sqlite"
LEDGER_AREA = "asset-activity-ledger-v1"

DATE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TRACKS = ("reward", "trade")
# Welche Ereignisarten zu welcher Spur gehoeren. Rewards pflegt der Importer,
# alles andere der Eigentuemer von Hand.
TRACK_OF_EVENT = {
    "reward": "reward",
    "buy": "trade", "sell": "trade", "dividend": "trade",
    "stock_dividend": "trade", "transfer": "trade",
    "deposit": "trade", "withdrawal": "trade",
}
# Erklaerte Zustaende (im Speicher) und abgeleitete (nur im Ergebnis).
STATES = frozenset({"not_maintained", "complete_through", "source_maintained"})
# implied_by_last_event: niemand hat etwas erklaert, aber es gibt Buchungen - dann
# gilt die juengste als Pflegestand. Schwaechere Aussage als eine Erklaerung
# ("bis hierher gebucht", nicht "bis hierher geprueft"), deshalb eigener Zustand.
# not_applicable: diese Spur kommt bei diesem Paar nicht vor - eine Aktie hat
# keine Rewards. Zaehlt nicht fuer das Minimum, sonst waere jede Aktie ungepflegt.
DERIVED_STATES = frozenset({"implied_by_last_event", "not_applicable"})
# Nur die Trade-Spur wird von Hand erklaert. Die Reward-Spur gehoert dem
# Importer, und keine Quelle beschreibt das Feld der anderen - genau daran haengt,
# dass sich Handpflege und Reward-Import nicht in die Quere kommen (#423).
DECLARABLE_TRACKS = ("trade",)
DECLARABLE_STATES = ("complete_through", "not_maintained")
SCOPES = ("selected", "unmoved")
CODES = frozenset({
    "asset_maintenance_state_context_invalid",
    "asset_maintenance_state_input_invalid",
    "asset_maintenance_state_store_invalid",
    "asset_maintenance_state_ledger_invalid",
    "asset_maintenance_state_preview_required",
    "asset_maintenance_state_confirmation_required",
    "asset_maintenance_state_write_failed",
})


class AssetMaintenanceStateV1Error(RuntimeError):
    def __init__(self, code: str):
        if code not in CODES:
            raise ValueError("asset_maintenance_state_error_unregistered")
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise AssetMaintenanceStateV1Error(code)


def _date(value: Any, *, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or DATE.fullmatch(value) is None:
        _abort("asset_maintenance_state_input_invalid")
    return value


def _utc(value: Any) -> str:
    if (not isinstance(value, str) or len(value) != 20 or value[10] != "T"
            or value[19] != "Z" or DATE.fullmatch(value[:10]) is None):
        _abort("asset_maintenance_state_input_invalid")
    return value


def _day_before(value: str) -> str:
    return (date.fromisoformat(value) - timedelta(days=1)).isoformat()


def _fingerprint(value: Any) -> str:
    """Wie im uebrigen Projekt: kanonisches JSON in rohem UTF-8. R bildet denselben
    Abdruck ueber jsonlite::toJSON; mit ensure_ascii wuerde er bei einem Umlaut im
    Assetnamen auseinanderlaufen."""
    try:
        return hashlib.sha256(json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
    except (TypeError, ValueError):
        _abort("asset_maintenance_state_input_invalid")


def _pair_ref(space_id: str, asset_id: str, account_id: str) -> str:
    """Eine Kennung des Paares fuer die Oberflaeche. Sie traegt keine kanonische
    Identitaet nach aussen und ist ueber Lesevorgaenge hinweg stabil - anders als
    die Korrekturkandidaten, deren Ref die Generation enthaelt."""
    return "amp_" + _fingerprint({
        "data_space_id": space_id, "asset_id": asset_id, "account_id": account_id,
    })[:32]


def _context(value: Any) -> tuple[str, str, str]:
    if not isinstance(value, Mapping):
        _abort("asset_maintenance_state_context_invalid")
    try:
        tenant = value["tenant_id"]; user = value["user_id"]; space = value["data_space_id"]
    except (KeyError, TypeError):
        _abort("asset_maintenance_state_context_invalid")
    if not (isinstance(tenant, str) and tenant.startswith("ten_")
            and isinstance(user, str) and user.startswith("usr_")
            and isinstance(space, str) and space.startswith("sbx_")):
        _abort("asset_maintenance_state_context_invalid")
    return tenant, user, space


def _owner_directory(path: Path) -> Path:
    """Wie im uebrigen Datenraum: kein Symlink im Pfad, keine Fremdrechte."""
    if not path.is_absolute():
        _abort("asset_maintenance_state_store_invalid")
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if current.is_symlink():
            _abort("asset_maintenance_state_store_invalid")
    try:
        mode = path.stat().st_mode
    except OSError:
        _abort("asset_maintenance_state_store_invalid")
    if mode & 0o077:
        _abort("asset_maintenance_state_store_invalid")
    return path


def _declarations(data_space: Path, space_id: str) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Gespeicherte Pflegeerklaerungen. Fehlt der Bereich, gilt alles als ungepflegt -
    das ist der normale Anfangszustand und kein Fehler."""
    area = data_space / AREA_NAME
    if not area.exists():
        return {}
    _owner_directory(area)
    store = area / STORE_NAME
    if not store.exists():
        return {}
    if store.is_symlink() or not store.is_file() or (store.stat().st_mode & 0o077):
        _abort("asset_maintenance_state_store_invalid")
    try:
        value = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _abort("asset_maintenance_state_store_invalid")
    if not isinstance(value, Mapping) or value.get("asset_maintenance_state_version") != 1:
        _abort("asset_maintenance_state_store_invalid")
    if value.get("data_space_id") != space_id:
        _abort("asset_maintenance_state_store_invalid")
    rows = value.get("declarations")
    if not isinstance(rows, list):
        _abort("asset_maintenance_state_store_invalid")
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            _abort("asset_maintenance_state_store_invalid")
        needed = {"portfolio_id", "asset_id", "account_id", "track", "state", "through_date", "declared_at_utc"}
        if set(row) != needed or row["track"] not in TRACKS or row["state"] not in STATES:
            _abort("asset_maintenance_state_store_invalid")
        if row["state"] == "not_maintained":
            if row["through_date"] is not None:
                _abort("asset_maintenance_state_store_invalid")
        else:
            _date(row["through_date"])
        key = (row["asset_id"], row["account_id"], row["track"])
        # Die jüngste Erklaerung je Paar und Spur gilt; die uebrigen sind Historie.
        vorhanden = result.get(key)
        if vorhanden is None or str(row["declared_at_utc"]) > str(vorhanden["declared_at_utc"]):
            result[key] = dict(row)
    return result


def _ledger(data_space: Path) -> Path:
    pointer = data_space / LEDGER_AREA / "active.json"
    if not pointer.is_file() or pointer.is_symlink():
        _abort("asset_maintenance_state_ledger_invalid")
    try:
        active = json.loads(pointer.read_text(encoding="utf-8"))
        generation = active["generation_ref"]
    except (OSError, ValueError, KeyError, TypeError):
        _abort("asset_maintenance_state_ledger_invalid")
    if not isinstance(generation, str) or not generation.startswith("gen_"):
        _abort("asset_maintenance_state_ledger_invalid")
    path = data_space / LEDGER_AREA / "generations" / generation / LEDGER_NAME
    if not path.is_file() or path.is_symlink():
        _abort("asset_maintenance_state_ledger_invalid")
    return path


def read_asset_maintenance_state_v1(
    data_space_path: str | Path, context_value: Any, as_of_date: str,
) -> dict[str, Any]:
    """Pflegestand je Asset, Konto und Spur, zusammen mit der letzten Buchung."""
    _, _, space_id = _context(context_value)
    as_of = _date(as_of_date)
    data_space = Path(data_space_path)
    if not data_space.is_absolute() or data_space.name != space_id:
        _abort("asset_maintenance_state_context_invalid")
    _owner_directory(data_space)
    declarations = _declarations(data_space, space_id)
    ledger = _ledger(data_space)
    connection = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        assets = {r["asset_id"]: r["display_name"] for r in connection.execute(
            "SELECT asset_id,display_name FROM asset_revision r WHERE revision_no="
            "(SELECT max(revision_no) FROM asset_revision x WHERE x.asset_id=r.asset_id)")}
        accounts = {r["account_id"]: r["display_name"] for r in connection.execute(
            "SELECT account_id,display_name FROM account_revision r WHERE revision_no="
            "(SELECT max(revision_no) FROM account_revision x WHERE x.account_id=r.account_id)")}
        portfolios = {r["portfolio_id"]: r["display_name"] for r in connection.execute(
            "SELECT portfolio_id,display_name FROM portfolio_revision r WHERE revision_no="
            "(SELECT max(revision_no) FROM portfolio_revision x WHERE x.portfolio_id=r.portfolio_id)")}
        events = [dict(r) for r in connection.execute(
            "SELECT portfolio_id,asset_id,account_id,related_account_id,event_type,local_date,created_at_utc "
            "FROM asset_activity_event WHERE local_date<=?", (as_of,))]
    except sqlite3.Error:
        _abort("asset_maintenance_state_ledger_invalid")
    finally:
        connection.close()
    # Je Paar und Spur die letzte Buchung. Ein Transfer zaehlt fuer beide Konten:
    # wer die Gegenseite pflegt, muss ihn dort ebenfalls kennen.
    letzte: dict[tuple[str, str, str], dict[str, Any]] = {}
    for event in events:
        track = TRACK_OF_EVENT.get(event["event_type"])
        if track is None:
            continue
        seiten = [event["account_id"]]
        if event["event_type"] == "transfer" and event["related_account_id"]:
            seiten.append(event["related_account_id"])
        for account_id in seiten:
            key = (event["asset_id"], account_id, track)
            row = letzte.get(key)
            if row is None:
                row = {"portfolio_id": event["portfolio_id"], "last_event_date": event["local_date"],
                       "event_count": 1, "backdated_date": None}
                letzte[key] = row
            else:
                row["event_count"] += 1
                if event["local_date"] > row["last_event_date"]:
                    row["last_event_date"] = event["local_date"]
            # Eine Buchung VOR dem erklaerten Stand, die NACH der Erklaerung
            # eingetragen wurde, aendert eine abgeschlossene Historie. Die
            # Zusicherung traegt dann nur noch bis zum Tag davor
            # (Festlegung 05.10.2026: Information, keine Sperre).
            erklaerung = declarations.get(key)
            if (erklaerung is not None and erklaerung["through_date"] is not None
                    and event["local_date"] <= erklaerung["through_date"]
                    and str(event["created_at_utc"]) > str(erklaerung["declared_at_utc"])):
                if row["backdated_date"] is None or event["local_date"] < row["backdated_date"]:
                    row["backdated_date"] = event["local_date"]
    paare: dict[tuple[str, str], dict[str, Any]] = {}
    for (asset_id, account_id, track) in set(letzte) | {(a, k, t) for (a, k, t) in declarations}:
        if asset_id not in assets or account_id not in accounts:
            continue
        eintrag = paare.setdefault((asset_id, account_id), {
            "asset_label": assets[asset_id], "account_label": accounts[account_id],
            "portfolio_id": None, "tracks": {},
        })
        buchung = letzte.get((asset_id, account_id, track))
        erklaerung = declarations.get((asset_id, account_id, track))
        if buchung and eintrag["portfolio_id"] is None:
            eintrag["portfolio_id"] = buchung["portfolio_id"]
        if erklaerung is not None:
            state = erklaerung["state"]; through = erklaerung["through_date"]
        elif buchung is not None:
            # Vorgabe ohne Erklaerung: die juengste Buchung gilt als Pflegestand
            # (Festlegung 05.10.2026).
            state = "implied_by_last_event"; through = buchung["last_event_date"]
        else:
            state = "not_applicable"; through = None
        nachgetragen = buchung["backdated_date"] if buchung else None
        if nachgetragen is not None and through is not None:
            # Zurueckgesetzt, nicht aufgehoben: Was vor der nachgetragenen Buchung
            # liegt, bleibt geprueft.
            through = min(through, _day_before(nachgetragen))
        eintrag["tracks"][track] = {
            "state": state, "through_date": through,
            "declared_at_utc": erklaerung["declared_at_utc"] if erklaerung else None,
            "last_event_date": buchung["last_event_date"] if buchung else None,
            "event_count": buchung["event_count"] if buchung else 0,
            "backdated_after_declaration": nachgetragen,
        }
    rows: list[dict[str, Any]] = []
    for (asset_id, account_id), eintrag in paare.items():
        spuren = {}
        for track in TRACKS:
            spuren[track] = eintrag["tracks"].get(track, {
                "state": "not_applicable", "through_date": None, "declared_at_utc": None,
                "last_event_date": None, "event_count": 0,
                "backdated_after_declaration": None,
            })
        # Wirksam ist das Minimum der Spuren, die hier vorkommen. Eine Spur ohne
        # Buchungen und ohne Erklaerung zaehlt nicht mit - eine Aktie hat keine
        # Rewards und ist deshalb nicht ungepflegt.
        beteiligt = [t for t in TRACKS if spuren[t]["state"] != "not_applicable"]
        offen = [t for t in beteiligt if spuren[t]["state"] == "not_maintained"]
        if not beteiligt or offen:
            effective = None
            effective_state = "not_maintained"
        else:
            effective = min(spuren[t]["through_date"] for t in beteiligt)
            # Erklaert ist staerker als abgeleitet: nur wenn jede beteiligte Spur
            # ausdruecklich erklaert wurde, gilt das Paar als geprueft.
            effective_state = ("complete_through"
                if all(spuren[t]["state"] in {"complete_through", "source_maintained"} for t in beteiligt)
                else "implied_by_last_event")
        letzte_buchung = [spuren[t]["last_event_date"] for t in TRACKS if spuren[t]["last_event_date"]]
        nachgetragen = [spuren[t]["backdated_after_declaration"] for t in TRACKS
                        if spuren[t]["backdated_after_declaration"]]
        rows.append({
            "pair_ref": _pair_ref(space_id, asset_id, account_id),
            "asset_label": eintrag["asset_label"], "account_label": eintrag["account_label"],
            "portfolio_label": portfolios.get(eintrag["portfolio_id"]),
            "effective_state": effective_state, "effective_through_date": effective,
            "last_event_date": max(letzte_buchung) if letzte_buchung else None,
            "event_count": sum(spuren[t]["event_count"] for t in TRACKS),
            "tracks": spuren,
            # Zwei verschiedene Befunde, die nicht zu verwechseln sind:
            # - eine ausdrueckliche Erklaerung, nach der noch gebucht wurde, traegt
            #   nicht mehr: sie behauptet Vollstaendigkeit, die es nicht gibt.
            # - laufen die Spuren auseinander, ist das kein Fehler, sondern die
            #   gesuchte Auskunft: Rewards aktuell, uebrige Transaktionen hinken.
            "declaration_outdated": bool(
                effective_state in {"complete_through"} and letzte_buchung
                and max(letzte_buchung) > effective),
            "tracks_diverge": bool(
                len(beteiligt) > 1
                and len({spuren[t]["through_date"] for t in beteiligt}) > 1),
            # Eine Buchung wurde vor dem erklaerten Stand nachgetragen; der Stand
            # steht jetzt auf dem Tag davor. Das ist ein Hinweis, keine Sperre.
            "declaration_undermined": min(nachgetragen) if nachgetragen else None,
        })
    # Aeltester Pflegestand zuerst, dann nach Konto gruppiert: der
    # Broker-Durchgang geht Depot fuer Depot, nicht Asset fuer Asset. Innerhalb
    # eines Kontos steht oben, was am laengsten keine Buchung gesehen hat.
    rows.sort(key=lambda row: (
        row["effective_through_date"] or "", row["account_label"],
        row["last_event_date"] or "", row["asset_label"]))
    offen = [r for r in rows if r["effective_state"] == "not_maintained"]
    erklaert = [r for r in rows if r["effective_state"] == "complete_through"]
    abgeleitet = [r for r in rows if r["effective_state"] == "implied_by_last_event"]
    gepflegt_alle = [r["effective_through_date"] for r in rows if r["effective_through_date"]]
    return {
        "asset_maintenance_state_version": 1,
        "status": "available",
        "as_of_date": as_of,
        "pair_count": len(rows),
        "not_maintained_count": len(offen),
        "declared_count": len(erklaert),
        "implied_count": len(abgeleitet),
        "outdated_declaration_count": sum(1 for r in rows if r["declaration_outdated"]),
        "diverging_track_count": sum(1 for r in rows if r["tracks_diverge"]),
        "undermined_declaration_count": sum(1 for r in rows if r["declaration_undermined"]),
        # Die Kennzahl, um die es geht: wie alt ist der schwaechste Pflegestand.
        "oldest_through_date": min(gepflegt_alle) if gepflegt_alle else None,
        "newest_through_date": max(gepflegt_alle) if gepflegt_alle else None,
        "pairs": rows,
        "canonical_write": False,
        "provider_access": False,
        "network_access": False,
        "path_exposed": False,
    }


# --- Schritt 2: erklaeren, sammelsetzen, Pflegelaeufe (#423) ------------------
#
# Der eigentliche Nutzen liegt in der Sammelsetzung: Mit einem Haekchen (sinnvollerweise
# nach dem Einpflegen der Assets) lassen sich alle uebrigen Assets auf das aktuelle
# Pflegedatum setzen, auch unangefasste ohne Transaktionen seit dem letzten Pflegedatum.
#
# Ohne das muessten alle Positionen einzeln bestaetigt werden, und das geschaehe nicht.
# Paare mit Bewegungen seit ihrem letzten Stand werden darum nicht
# stillschweigend mitgenommen, sondern namentlich aufgefuehrt - sonst erklaerte
# das Haekchen etwas, das nicht geprueft wurde.


def _declaration_request(value: Any, as_of: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"track", "state", "through_date", "scope", "pair_refs"}:
        _abort("asset_maintenance_state_input_invalid")
    track = value["track"]; state = value["state"]; scope = value["scope"]; refs = value["pair_refs"]
    if track not in DECLARABLE_TRACKS or state not in DECLARABLE_STATES or scope not in SCOPES:
        _abort("asset_maintenance_state_input_invalid")
    if state == "not_maintained":
        if value["through_date"] is not None:
            _abort("asset_maintenance_state_input_invalid")
        through = None
        # Eine Zuruecknahme gilt immer genau fuer die benannten Paare. Pauschal
        # alles fuer ungepflegt zu erklaeren waere eine Loeschung ohne Auswahl.
        if scope != "selected":
            _abort("asset_maintenance_state_input_invalid")
    else:
        through = _date(value["through_date"])
        # Kein Stand in der Zukunft: Was noch nicht war, kann nicht geprueft sein.
        if through > as_of:
            _abort("asset_maintenance_state_input_invalid")
    if not isinstance(refs, list) or len(set(map(str, refs))) != len(refs):
        _abort("asset_maintenance_state_input_invalid")
    for ref in refs:
        if not isinstance(ref, str) or not ref.startswith("amp_") or len(ref) != 36:
            _abort("asset_maintenance_state_input_invalid")
    if scope == "selected" and not refs:
        _abort("asset_maintenance_state_input_invalid")
    if scope == "unmoved" and refs:
        _abort("asset_maintenance_state_input_invalid")
    return {"track": track, "state": state, "through_date": through, "scope": scope,
            "pair_refs": list(refs)}


def preview_asset_maintenance_declaration_v1(
    data_space_path: str | Path, context_value: Any, request_value: Any, as_of_date: str,
) -> dict[str, Any]:
    """Was eine Pflegeerklaerung aendern wuerde - ohne sie zu schreiben."""
    _, _, space_id = _context(context_value)
    as_of = _date(as_of_date)
    request = _declaration_request(request_value, as_of)
    state = read_asset_maintenance_state_v1(data_space_path, context_value, as_of)
    nach_ref = {row["pair_ref"]: row for row in state["pairs"]}
    track = request["track"]
    einbezogen: list[dict[str, Any]] = []
    ausgenommen: list[dict[str, Any]] = []

    def kurz(row: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
        spur = row["tracks"][track]
        item = {
            "pair_ref": row["pair_ref"], "asset_label": row["asset_label"],
            "account_label": row["account_label"], "portfolio_label": row["portfolio_label"],
            "previous_state": spur["state"], "previous_through_date": spur["through_date"],
            "last_event_date": spur["last_event_date"],
            "movement_since_previous_state": bool(
                spur["last_event_date"] and spur["through_date"]
                and spur["last_event_date"] > spur["through_date"]),
        }
        if reason is not None:
            item["reason"] = reason
        return item

    if request["scope"] == "selected":
        for ref in request["pair_refs"]:
            row = nach_ref.get(ref)
            if row is None:
                ausgenommen.append({"pair_ref": ref, "asset_label": None, "account_label": None,
                                    "portfolio_label": None, "previous_state": None,
                                    "previous_through_date": None, "last_event_date": None,
                                    "movement_since_previous_state": False, "reason": "unknown_pair"})
                continue
            # Ausdruecklich gewaehlt wird einbezogen, auch mit Bewegung seit dem
            # letzten Stand - der Eigentuemer hat dieses Paar benannt. Dass es
            # Bewegung gab, steht in der Vorschau.
            einbezogen.append(kurz(row))
    else:
        for row in state["pairs"]:
            spur = row["tracks"][track]
            if spur["state"] == "not_applicable":
                ausgenommen.append(kurz(row, "track_not_applicable"))
            elif spur["through_date"] is None:
                # Kein Stand, mit dem sich "keine Bewegung seither" vergleichen
                # liesse. Solche Paare gehoeren einzeln angesehen.
                ausgenommen.append(kurz(row, "no_previous_state"))
            elif spur["last_event_date"] and spur["last_event_date"] > spur["through_date"]:
                ausgenommen.append(kurz(row, "movement_since_previous_state"))
            elif spur["through_date"] >= request["through_date"]:
                ausgenommen.append(kurz(row, "already_current"))
            else:
                einbezogen.append(kurz(row))
    einbezogen.sort(key=lambda item: (item["account_label"] or "", item["asset_label"] or ""))
    ausgenommen.sort(key=lambda item: (item["reason"], item["account_label"] or "", item["asset_label"] or ""))
    fingerprint = _fingerprint({
        "data_space_id": space_id,
        "as_of_date": as_of, "track": track, "state": request["state"],
        "through_date": request["through_date"], "scope": request["scope"],
        "pair_refs": sorted(item["pair_ref"] for item in einbezogen),
    })
    return {
        "asset_maintenance_declaration_preview_version": 1,
        "status": "ready" if einbezogen else "nothing_to_declare",
        "as_of_date": as_of, "track": track, "state": request["state"],
        "through_date": request["through_date"], "scope": request["scope"],
        "included": einbezogen, "excluded": ausgenommen,
        "included_count": len(einbezogen), "excluded_count": len(ausgenommen),
        "movement_since_previous_state_count": sum(
            1 for item in einbezogen if item["movement_since_previous_state"]),
        "preview_fingerprint": fingerprint,
        "canonical_write": False, "provider_access": False,
        "network_access": False, "path_exposed": False,
    }


def _area(data_space: Path) -> Path:
    area = data_space / AREA_NAME
    if not area.exists():
        try:
            area.mkdir(mode=0o700)
        except OSError:
            _abort("asset_maintenance_state_write_failed")
    return _owner_directory(area)


def _write_json(path: Path, value: Any) -> None:
    """Erst vollstaendig daneben schreiben, dann umbenennen. Ein abgebrochener
    Schreibvorgang darf keine halbe Erklaerungsdatei hinterlassen."""
    try:
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=".", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError:
        _abort("asset_maintenance_state_write_failed")


def _raw_declarations(area: Path, space_id: str) -> list[dict[str, Any]]:
    store = area / STORE_NAME
    if not store.exists():
        return []
    # Dieselbe Pruefung wie beim Lesen; eine fremde oder kaputte Datei wird nicht
    # ueberschrieben, sondern gemeldet.
    if store.is_symlink() or not store.is_file() or (store.stat().st_mode & 0o077):
        _abort("asset_maintenance_state_store_invalid")
    try:
        value = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _abort("asset_maintenance_state_store_invalid")
    if (not isinstance(value, Mapping) or value.get("asset_maintenance_state_version") != 1
            or value.get("data_space_id") != space_id or not isinstance(value.get("declarations"), list)):
        _abort("asset_maintenance_state_store_invalid")
    return [dict(row) for row in value["declarations"]]


def _raw_runs(area: Path, space_id: str) -> list[dict[str, Any]]:
    store = area / RUNS_NAME
    if not store.exists():
        return []
    if store.is_symlink() or not store.is_file() or (store.stat().st_mode & 0o077):
        _abort("asset_maintenance_state_store_invalid")
    try:
        value = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _abort("asset_maintenance_state_store_invalid")
    if (not isinstance(value, Mapping) or value.get("asset_maintenance_runs_version") != 1
            or value.get("data_space_id") != space_id or not isinstance(value.get("runs"), list)):
        _abort("asset_maintenance_state_store_invalid")
    return [dict(row) for row in value["runs"]]


def apply_asset_maintenance_declaration_v1(
    data_space_path: str | Path, context_value: Any, request_value: Any, as_of_date: str,
    preview_fingerprint: Any, declared_at_utc: Any, confirmed: Any,
) -> dict[str, Any]:
    """Genau die vorab gezeigte Erklaerung schreiben - ein Vorgang, ein Pflegelauf.

    Die Erklaerungen werden angehaengt, nie ersetzt: Die juengste je Paar und Spur
    gilt, die aelteren sind die gewuenschte Historie. Ein Pflegelauf haelt
    zusaetzlich fest, was in einem Zug erklaert wurde - daraus folgt die Kennzahl,
    wie alt der Pflegestand ueber den ganzen Bestand ist.
    """
    _, _, space_id = _context(context_value)
    as_of = _date(as_of_date)
    declared = _utc(declared_at_utc)
    if confirmed is not True:
        _abort("asset_maintenance_state_confirmation_required")
    if not isinstance(preview_fingerprint, str) or len(preview_fingerprint) != 64:
        _abort("asset_maintenance_state_preview_required")
    preview = preview_asset_maintenance_declaration_v1(data_space_path, context_value, request_value, as_of)
    if preview["preview_fingerprint"] != preview_fingerprint:
        _abort("asset_maintenance_state_preview_required")
    if preview["status"] != "ready":
        _abort("asset_maintenance_state_preview_required")
    data_space = Path(data_space_path)
    if not data_space.is_absolute() or data_space.name != space_id:
        _abort("asset_maintenance_state_context_invalid")
    area = _area(data_space)
    runs = _raw_runs(area, space_id)
    run_ref = "amr_" + _fingerprint({
        "preview_fingerprint": preview_fingerprint, "declared_at_utc": declared,
    })[:32]
    # Ein zweiter Klick wiederholt den Vorgang nicht, er findet ihn vor.
    for row in runs:
        if row.get("run_ref") == run_ref:
            return {"asset_maintenance_declaration_result_version": 1, "status": "already_applied",
                    "run_ref": run_ref, "declared_pair_count": len(row.get("pairs", [])),
                    "track": row.get("track"), "state": row.get("state"),
                    "through_date": row.get("through_date"), "declared_at_utc": row.get("declared_at_utc"),
                    "canonical_write": False, "provider_access": False,
                    "network_access": False, "path_exposed": False}
    pairs = preview["included"]
    rows = _raw_declarations(area, space_id)
    # Die Paarkennung traegt keine kanonische Identitaet nach aussen; hier drinnen
    # wird sie auf Asset, Konto und Portfolio zurueckgefuehrt. Aufgeloest wird
    # genau ueber die Paare, die es wirklich gibt: Buchungen im Ledger und
    # bestehende Erklaerungen. Ein Kreuzprodukt aller Assets mit allen Konten
    # waere eine Liste von Paaren, die nie existierten.
    ledger = _ledger(data_space)
    connection = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        vorkommen = [dict(r) for r in connection.execute(
            "SELECT DISTINCT portfolio_id,asset_id,account_id,related_account_id,event_type "
            "FROM asset_activity_event")]
    except sqlite3.Error:
        _abort("asset_maintenance_state_ledger_invalid")
    finally:
        connection.close()
    identity: dict[str, tuple[str, str, str | None]] = {}
    for row in vorkommen:
        seiten = [row["account_id"]]
        if row["event_type"] == "transfer" and row["related_account_id"]:
            seiten.append(row["related_account_id"])
        for account_id in seiten:
            identity.setdefault(_pair_ref(space_id, row["asset_id"], account_id),
                                (row["asset_id"], account_id, row["portfolio_id"]))
    for row in rows:
        identity.setdefault(_pair_ref(space_id, str(row["asset_id"]), str(row["account_id"])),
                            (str(row["asset_id"]), str(row["account_id"]), row.get("portfolio_id")))
    geschrieben = []
    for item in pairs:
        treffer = identity.get(item["pair_ref"])
        if treffer is None:
            _abort("asset_maintenance_state_preview_required")
        asset_id, account_id, portfolio_id = treffer
        rows.append({
            "portfolio_id": portfolio_id,
            "asset_id": asset_id, "account_id": account_id, "track": preview["track"],
            "state": preview["state"], "through_date": preview["through_date"],
            "declared_at_utc": declared,
        })
        geschrieben.append({
            "pair_ref": item["pair_ref"], "asset_label": item["asset_label"],
            "account_label": item["account_label"], "portfolio_label": item["portfolio_label"],
            "previous_state": item["previous_state"],
            "previous_through_date": item["previous_through_date"],
        })
    runs.append({
        "run_ref": run_ref, "declared_at_utc": declared, "as_of_date": as_of,
        "track": preview["track"], "state": preview["state"],
        "through_date": preview["through_date"], "scope": preview["scope"],
        "origin": "owner_manual", "preview_fingerprint": preview_fingerprint,
        "pairs": geschrieben,
    })
    _write_json(area / STORE_NAME, {
        "asset_maintenance_state_version": 1, "data_space_id": space_id, "declarations": rows})
    _write_json(area / RUNS_NAME, {
        "asset_maintenance_runs_version": 1, "data_space_id": space_id, "runs": runs})
    return {
        "asset_maintenance_declaration_result_version": 1, "status": "declared",
        "run_ref": run_ref, "declared_pair_count": len(geschrieben),
        "track": preview["track"], "state": preview["state"],
        "through_date": preview["through_date"], "declared_at_utc": declared,
        "canonical_write": False, "provider_access": False,
        "network_access": False, "path_exposed": False,
    }


def read_asset_maintenance_runs_v1(
    data_space_path: str | Path, context_value: Any,
) -> dict[str, Any]:
    """Die Pflegelaeufe, neueste zuerst. Festlegung vom 05.10.2026: Die
    Pflegezeitpunkte werden historisch gespeichert; daran laesst sich ablesen, wie
    aktuell die ganze Datenbasis ist.

    Loeschbar auf Wunsch, aber nicht automatisch: Eine Pflegeerklaerung ist eine
    Zusicherung des Eigentuemers, keine Ableitung.
    """
    _, _, space_id = _context(context_value)
    data_space = Path(data_space_path)
    if not data_space.is_absolute() or data_space.name != space_id:
        _abort("asset_maintenance_state_context_invalid")
    _owner_directory(data_space)
    area = data_space / AREA_NAME
    runs = [] if not area.exists() else _raw_runs(_owner_directory(area), space_id)
    runs.sort(key=lambda row: str(row.get("declared_at_utc")), reverse=True)
    return {
        "asset_maintenance_runs_version": 1, "status": "available",
        "run_count": len(runs),
        "declared_pair_count": sum(len(row.get("pairs", [])) for row in runs),
        "newest_declared_at_utc": runs[0]["declared_at_utc"] if runs else None,
        "oldest_declared_at_utc": runs[-1]["declared_at_utc"] if runs else None,
        "runs": runs,
        "canonical_write": False, "provider_access": False,
        "network_access": False, "path_exposed": False,
    }
