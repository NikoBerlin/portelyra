"""Pruefstand je Portfolio und Uebersicht der Leser (rc.380, #486).

Festlegungen vom 09.11.2026:
- Ein Leser gilt in einem Portfolio erst als "an Ihren Belegen geprueft", wenn der Eigentuemer eine Buchung mit genau diesem Plugin-Code
  ausdruecklich bestaetigt hat. Bis dahin zeigt die Vorschau einen Hinweis, und das Buchen verlangt eine zusaetzliche Bestaetigung.
- Version = Pruefsumme ueber die eigenen Dateien des Plugins. Eine geaenderte Hilfsbibliothek (SDK, Host) ist nur ein Hinweis; die Herkunft
  je Buchung behaelt die volle Pruefsumme.
- In Datenraeumen aus der Zeit vor rc.380 gelten die mitgelieferten Leser ueber einen einmaligen Eintrag "Bestand bis rc.379" als geprueft.

Die Uebersicht zaehlt je Leser die Buchungen mit seiner Herkunft und je Art die Buchungen ohne Herkunft (manuell erfasst oder vor rc.378
gebucht). Nur lesend, bis auf den einmaligen Bestandseintrag.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence

from migrations.reference import asset_activity_reference_v1 as references
from migrations.reference import statement_reader_plugins_v1 as reader_plugins

FAILURE_CODES = ("statement_reader_unchecked", "statement_reader_check_portfolio_unknown", "statement_reader_check_input_invalid",
                 "statement_reader_check_store_invalid", "statement_reader_inactive", "statement_reader_incompatible")
KIND_LABELS = {"asset_event": "Buchungen (Wertpapiere, Krypto, Devisen, Rewards)", "cash_command": "Cash-Bewegungen aus Auszügen",
               "taxable_document": "Beträge laut Erträgnisaufstellung", "advance_lump_sum": "Vorabpauschalen", "stock_split": "Splits"}


class StatementReaderCheckV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "statement_reader_check_input_invalid"


def _abort(code: str) -> None:
    raise StatementReaderCheckV1Error(code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- Portfolio
# Portfolios werden getrennt behandelt (Festlegung 09.11.2026): Der Stand gilt je Portfolio; ein Import mit Konten aus zwei Portfolios
# verlangt und haelt ihn fuer jedes getrennt. Ohne Konten gilt nur das einzige Portfolio des Datenraums.
def _portfolio_rows(space: str | Path) -> dict[str, str]:
    try:
        connection = sqlite3.connect(f"file:{Path(space) / 'canonical.sqlite'}?mode=ro", uri=True)
        try:
            return {str(row[0]): str(row[1] or row[0]) for row in connection.execute("SELECT portfolio_id, display_name FROM portfolio ORDER BY portfolio_id")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("statement_reader_check_portfolio_unknown")
        return {}


def reader_check_portfolios_v1(space: str | Path, account_ids: Sequence[str] | None = None) -> list[str]:
    """Die Portfolios eines Imports: die der gebuchten Konten (jedes Konto muss es geben); ohne Konten das einzige des Datenraums."""
    if account_ids:
        accounts = sorted(set(account_ids))
        try:
            connection = sqlite3.connect(f"file:{Path(space) / 'canonical.sqlite'}?mode=ro", uri=True)
            try:
                marks = ",".join("?" for _ in accounts)
                rows = connection.execute(f"SELECT account_id, portfolio_id FROM account WHERE account_id IN ({marks})", accounts).fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            _abort("statement_reader_check_portfolio_unknown")
        if len(rows) != len(accounts):
            _abort("statement_reader_check_portfolio_unknown")
        return sorted({str(row[1]) for row in rows})
    portfolios = list(_portfolio_rows(space))
    if len(portfolios) != 1:
        _abort("statement_reader_check_portfolio_unknown")
    return portfolios


def reader_check_portfolio_v1(space: str | Path, account_ids: Sequence[str] | None = None) -> str:
    """Genau ein Portfolio (fuer Aufrufer, die nur eines kennen); mehrere brechen ab."""
    portfolios = reader_check_portfolios_v1(space, account_ids)
    if len(portfolios) != 1:
        _abort("statement_reader_check_portfolio_unknown")
    return portfolios[0]


# ---------------------------------------------------------------- Kennungen
def check_identity_from_provenance_v1(identity: Mapping[str, Any]) -> dict[str, str]:
    """Pruefstand-Kennung zu einer Herkunft-Kennung ({plugin_id, reader_id, domain, ...}): Plugin-Code ohne SDK/Host, beim Kern die Kerndatei."""
    if not isinstance(identity, Mapping) or not isinstance(identity.get("reader_id"), str) or not isinstance(identity.get("domain"), str):
        _abort("statement_reader_check_input_invalid")
    if identity.get("plugin_id") == "portelyra_core":
        from migrations.reference import generic_statement_import_v1 as generic  # noqa: PLC0415
        return reader_plugins.core_reader_check_identity_v1(identity["reader_id"], identity["domain"], generic.__file__)
    try:
        return reader_plugins.reader_check_identity_v1(identity["reader_id"], identity["domain"])
    except reader_plugins.StatementReaderBlocked:
        _abort("statement_reader_check_input_invalid")
        return {}


def _label(identity: Mapping[str, Any]) -> str:
    spec = reader_plugins.reader_spec_v1(identity["reader_id"], identity["domain"]) if identity.get("plugin_id") != "portelyra_core" else None
    if spec is None:
        return "Generischer Leser (experimentell)" if identity.get("plugin_id") == "portelyra_core" else identity["reader_id"]
    return f"{spec.label} ({spec.institution})" if spec.institution and spec.institution not in spec.label else spec.label


def _day(stamp: str | None) -> str:
    return "" if not stamp else f"{stamp[8:10]}.{stamp[5:7]}.{stamp[0:4]}"


# ---------------------------------------------------------------- Bestand bis rc.379
# Nur Portfolios, die vor rc.380 angelegt wurden, koennen den Bestandseintrag bekommen; ein spaeter angelegtes Portfolio nie.
BASELINE_PORTFOLIOS_CREATED_BEFORE = "2026-11-10T00:00:00Z"
# Tests: Ein Portfolio, das ein Test "jetzt" anlegt, gilt nach dem Stichtag nicht mehr als Bestand. Tests, die einen Bestand
# voraussetzen, verschieben den Stichtag ueber diese Variable (wie PORTELYRA_READER_REFERENCE_DATE_INTERNAL), sonst waeren sie ab dem
# 10.11.2026 rot (gefunden am 09.11.2026 mit einem Probelauf "Stichtag vorbei").
BASELINE_CUTOFF_ENV = "PORTELYRA_PLUGIN_BASELINE_CUTOFF_INTERNAL"


def baseline_cutoff_v1() -> str:
    value = os.environ.get(BASELINE_CUTOFF_ENV)
    if isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        return value
    return BASELINE_PORTFOLIOS_CREATED_BEFORE


def _portfolio_created_before_cutoff(space: str | Path, portfolio_id: str) -> bool:
    try:
        connection = sqlite3.connect(f"file:{Path(space) / 'canonical.sqlite'}?mode=ro", uri=True)
        try:
            row = connection.execute("SELECT created_at_utc FROM portfolio WHERE portfolio_id=?", (portfolio_id,)).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return bool(row and isinstance(row[0], str) and row[0] < baseline_cutoff_v1())


def _has_bookings(space: str | Path, context: Any) -> bool:
    try:
        if references._ledger_event_types(space, context):
            return True
    except references.AssetActivityReferenceV1Error:
        pass
    return (Path(space) / "cash-coverage-v1" / "cash-coverage.sqlite").exists()


def _ensure_baseline(space: str | Path, context: Any, recorded_at_utc: str) -> None:
    """Einmalig beim ersten Kontakt eines Datenraums mit rc.380 (Festlegung 09.11.2026): Gibt es schon Buchungen, gelten alle mitgelieferten
    Leser als geprueft ("Bestand bis rc.379"); sonst wird der Speicher leer angelegt, und spaeter entsteht nie ein Bestandseintrag - auch nicht
    nach der ersten Buchung eines neuen Datenraums. Zudem nur fuer ein Portfolio, das vor rc.380 angelegt wurde: Wer spaeter ein Portfolio
    anlegt, erst von Hand bucht und dann importiert, bekommt die Leser nicht als geprueft geschenkt."""
    if references.reader_check_store_present_v1(space):
        return
    # Jedes vor rc.380 angelegte Portfolio des Datenraums (Buchungen vorhanden) bekommt den Eintrag; ein spaeter angelegtes nie.
    eligible = [portfolio for portfolio in _portfolio_rows(space) if _portfolio_created_before_cutoff(space, portfolio)] if _has_bookings(space, context) else []
    references.ensure_reader_check_store_v1(space, context)
    shipped = [reader_plugins.reader_check_identity_v1(spec.reader_id, spec.domain) for spec in reader_plugins.reader_specs_v1()] if eligible else []
    for portfolio_id in eligible:
        if shipped:
            references.record_reader_checks_v1(space, context, portfolio_id, shipped, "existing_data_space", recorded_at_utc)


# ---------------------------------------------------------------- Umzug der Regeln (rc.419)
def _read_checks(space: str | Path, context: Any, portfolio_id: str, identities: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Pruefstand je Leser im Portfolio. Seit rc.419 zaehlen die Regeln im Manifest zum Plugin-Code; eine Pruefung des Codes aus der Zeit
    davor gilt weiter, solange die Regeln des mitgelieferten Plugins dem Stand von rc.419 entsprechen (legacy_code_sha256s_v1). Liest nur."""
    states = references.read_reader_checks_v1(space, context, portfolio_id, identities)["readers"]
    legacy = [reader_plugins.legacy_code_sha256s_v1(item["reader_id"], item["domain"]) if item["plugin_id"] != "portelyra_core" else None
              for item in identities]
    if not any(legacy):
        return states
    alternates = [{**item, "plugin_code_sha256": old["plugin_code_sha256"]} for item, old in zip(identities, legacy) if old]
    earlier = iter(references.read_reader_checks_v1(space, context, portfolio_id, alternates)["readers"])
    merged = []
    for state, old in zip(states, legacy):
        before = next(earlier) if old else None
        if before is not None and state["status"] == "unchecked" and before["status"] == "checked":
            state = {**state, "status": "checked", "checked": before["checked"], "previous": None, "shared_changed": before["shared_changed"]}
        merged.append(state)
    return merged


# ---------------------------------------------------------------- Pruefstand je Import
BALANCE_WARNING = ("Diese Belege nennen keinen Saldo, an dem Portelyra die gelesenen Beträge nachrechnen könnte. Bis zu Ihrer Bestätigung prüft "
                   "allein Ihr Vergleich der Vorschau mit den Belegen – bitte jede Zeile ansehen, besonders Beträge, Gebühren und Tage.")


def reader_checks_v1(space: str | Path, context: Any, readers: Sequence[Mapping[str, Any]], account_ids: Sequence[str] | None = None,
                     recorded_at_utc: str | None = None, balance_checked: bool | None = None,
                     reader_accounts: Sequence[tuple[Mapping[str, Any], Sequence[str]]] | None = None) -> dict[str, Any]:
    """Pruefstand der Leser eines Imports im Portfolio. ``readers`` sind Herkunft-Kennungen (wie an den Kandidaten). Liefert je Leser den
    Stand und die Texte fuer die Vorschau; ``acknowledgment_required`` heisst: Buchen nur mit ausdruecklicher Bestaetigung.
    ``balance_checked=False`` (Beleg ohne Saldo, Festlegung vom 07.11.2026): Solange ein Leser ungeprueft ist, warnt die
    Vorschau deutlich, dass nur der eigene Vergleich prueft (``balance_warning``).
    ``reader_accounts`` (Leser, Konten): Jeder Leser zaehlt nur fuer die Portfolios der Konten, in die er bucht (Portfolios getrennt,
    Festlegung 09.11.2026); ohne Angabe gilt jeder Leser fuer alle Portfolios der Konten des Imports."""
    from migrations.reference import statement_reader_admin_v1 as admin  # noqa: PLC0415
    try:
        status = _reader_checks(space, context, readers, account_ids, recorded_at_utc, reader_accounts)
        status = {**status, **_activation_and_compatibility(space, context, status)}
        return {**status, "balance_checked": balance_checked,
                "balance_warning": BALANCE_WARNING if status["acknowledgment_required"] and not status["blocked"] and balance_checked is False else None}
    except (references.AssetActivityReferenceV1Error, admin.StatementReaderAdminV1Error):
        _abort("statement_reader_check_store_invalid")
        return {}


def _activation_and_compatibility(space, context, status) -> dict[str, Any]:
    """Aktiv je Portfolio (rc.381) und Kompatibilitaet installierter Plugins nach Updates: Gesperrtes bucht nie, auch nicht mit Haekchen."""
    from migrations.reference import statement_reader_admin_v1 as admin  # noqa: PLC0415
    if not status["readers"]:
        return {"blocked": False, "blocked_code": None, "blocked_notes": []}
    active = admin.active_plugins_v1(space, context)
    labels = _portfolio_rows(space)
    several = len(status["portfolio_ids"]) > 1
    notes, codes = [], []
    for item in status["readers"]:
        if item["plugin_id"] == "portelyra_core":
            continue
        label = _label(item)
        for state in item["portfolios"]:
            if item["plugin_id"] not in active.get(state["portfolio_id"], set()):
                state["active"] = False
                where = f"im Portfolio „{labels.get(state['portfolio_id'], state['portfolio_id'])}“" if several else "in diesem Portfolio"
                notes.append(f"„{label}“ ist {where} nicht aktiv. Gebucht wird nichts; aktivieren lässt es sich im Reiter „Leser“ unter „Aktivierung je Portfolio“.")
                codes.append("statement_reader_inactive")
            else:
                state["active"] = True
        compatibility = admin.plugin_compatibility_v1(space, context, item["plugin_id"])
        item["compatibility"] = compatibility.get("status")
        if compatibility.get("status") == "incompatible":
            findings = sum(finding["count"] for reader in (compatibility.get("selftest") or {}).get("readers", []) for finding in reader.get("findings", []))
            notes.append(f"„{label}“ (installiert, Version {item['plugin_version']}) hat den Selbsttest mit Portelyra {compatibility.get('core_version')} "
                         f"nicht bestanden ({findings} Befund(e)). Gesperrt, bis eine neue Fassung des Herausgebers installiert ist und den Selbsttest besteht.")
            codes.append("statement_reader_incompatible")
    order = ("statement_reader_incompatible", "statement_reader_inactive")
    return {"blocked": bool(codes), "blocked_code": next((code for code in order if code in codes), None), "blocked_notes": notes}


def _reader_checks(space, context, readers, account_ids, recorded_at_utc, reader_accounts=None) -> dict[str, Any]:
    labels = _portfolio_rows(space)
    identities = list({(item["plugin_id"], item["reader_id"], item["domain"]): item
                       for item in (check_identity_from_provenance_v1(reader) for reader in readers)}.values())
    own: dict[tuple[str, str, str], set[str]] = {}
    for reader, accounts in reader_accounts or []:
        identity = check_identity_from_provenance_v1(reader)
        own.setdefault((identity["plugin_id"], identity["reader_id"], identity["domain"]), set()).update(account for account in accounts if account)
    if own:   # je Leser nur die Portfolios seiner Konten; Leser ohne eigene Konten zaehlen fuer alle Portfolios des Imports
        mapped = {key: reader_check_portfolios_v1(space, sorted(accounts)) for key, accounts in own.items() if accounts}
        everything = sorted({portfolio for found in mapped.values() for portfolio in found} | set(reader_check_portfolios_v1(space, account_ids) if account_ids else []))
        portfolios = everything or reader_check_portfolios_v1(space, None)
    else:
        mapped = {}
        portfolios = reader_check_portfolios_v1(space, account_ids)
    if not identities:
        return {"portfolio_id": portfolios[0], "portfolio_ids": portfolios, "readers": [], "unchecked_count": 0, "acknowledgment_required": False,
                "notes": [], "hints": []}
    _ensure_baseline(space, context, recorded_at_utc or _now())
    per_portfolio = {portfolio: _read_checks(space, context, portfolio, identities) for portfolio in portfolios}
    several = len(portfolios) > 1
    notes, hints, merged = [], [], []
    for index, identity in enumerate(identities):
        key = (identity["plugin_id"], identity["reader_id"], identity["domain"])
        states = [{"portfolio_id": portfolio, "portfolio_label": labels.get(portfolio, portfolio), **per_portfolio[portfolio][index]}
                  for portfolio in mapped.get(key, portfolios)]
        label = _label(identity)
        for state in states:
            where = f" (Portfolio „{state['portfolio_label']}“)" if several else ""
            if state["status"] == "unchecked":
                if state["previous"]:
                    notes.append(f"„{label}“ liegt in einer neuen Version vor ({state['plugin_version']}; zuletzt an Ihren Belegen geprüft: Version "
                                 f"{state['previous']['plugin_version']} am {_day(state['previous']['recorded_at_utc'])}){where}. Vergleichen Sie die "
                                 "Vorschau mit den Belegen; das Buchen bestätigt die Prüfung für diese Version.")
                else:
                    notes.append(f"„{label}“ (Version {state['plugin_version']}) ist in "
                                 f"{'dem Portfolio „' + state['portfolio_label'] + '“' if several else 'diesem Portfolio'} noch nicht an Ihren Belegen "
                                 "geprüft. Vergleichen Sie die Vorschau mit den Belegen; das Buchen bestätigt die Prüfung für diese Version.")
            elif state["shared_changed"]:
                hints.append(f"„{label}“: Die gemeinsame Hilfsbibliothek der Leser hat sich seit Ihrer Prüfung am {_day(state['checked']['recorded_at_utc'])} "
                             f"geändert{where} (nur Hinweis).")
        first_open = next((state for state in states if state["status"] == "unchecked"), None)
        lead = first_open or states[0]
        merged.append({**{key: lead[key] for key in lead if key not in ("portfolio_id", "portfolio_label")},
                       "status": "unchecked" if first_open else "checked", "shared_changed": any(state["shared_changed"] for state in states),
                       "portfolios": states})
    unchecked = [item for item in merged if item["status"] == "unchecked"]
    return {"portfolio_id": portfolios[0], "portfolio_ids": portfolios, "readers": merged, "unchecked_count": len(unchecked),
            "acknowledgment_required": bool(unchecked), "notes": notes, "hints": hints}


def confirm_reader_checks_v1(space: str | Path, context: Any, readers: Sequence[Mapping[str, Any]], acknowledged: bool,
                             account_ids: Sequence[str] | None = None, recorded_at_utc: str | None = None,
                             document_count: int | None = None, booking_count: int | None = None, reader_accounts=None) -> dict[str, Any]:
    """Vor dem Buchen pruefen, nach dem Buchen festhalten (zweimal aufrufen): Ungepruefter Leser ohne ausdrueckliche Bestaetigung bricht mit
    ``statement_reader_unchecked`` ab. Mit Bestaetigung haelt es den Pruefstand fuer genau diesen Plugin-Code fest."""
    status = reader_checks_v1(space, context, readers, account_ids, recorded_at_utc, reader_accounts=reader_accounts)
    if status["blocked"]:
        _abort(status["blocked_code"])
    if not status["acknowledgment_required"]:
        return {**status, "recorded_count": 0}
    if acknowledged is not True:
        _abort("statement_reader_unchecked")
    written = 0
    try:   # je Portfolio getrennt festhalten, nur was dort noch ungeprueft ist
        for portfolio in status["portfolio_ids"]:
            open_here = [{key: item[key] for key in references.CHECK_READER_KEYS} for item in status["readers"]
                         if any(state["portfolio_id"] == portfolio and state["status"] == "unchecked" for state in item["portfolios"])]
            if open_here:
                written += references.record_reader_checks_v1(space, context, portfolio, open_here, "confirmed_import", recorded_at_utc or _now(),
                                                             document_count, booking_count)["written_count"]
    except references.AssetActivityReferenceV1Error:
        _abort("statement_reader_check_store_invalid")
    return {**status, "recorded_count": written}


def require_reader_checks_v1(space: str | Path, context: Any, readers: Sequence[Mapping[str, Any]], acknowledged: bool,
                             account_ids: Sequence[str] | None = None, reader_accounts=None) -> dict[str, Any]:
    """Nur pruefen (vor dem Buchen): ungepruefter Leser ohne Bestaetigung bricht ab; schreibt nichts ausser dem einmaligen Bestandseintrag."""
    status = reader_checks_v1(space, context, readers, account_ids, reader_accounts=reader_accounts)
    if status["blocked"]:
        _abort(status["blocked_code"])
    if status["acknowledgment_required"] and acknowledged is not True:
        _abort("statement_reader_unchecked")
    return status


# ---------------------------------------------------------------- Uebersicht
def _booking_totals(space: str | Path, context: Any) -> dict[str, set[str]]:
    """Je Art die gueltigen Buchungen (Schluessel wie in der Herkunft)."""
    totals: dict[str, set[str]] = {kind: set() for kind in references.PROVENANCE_KINDS}
    try:
        totals["asset_event"] = set(references._ledger_event_types(space, context))
    except references.AssetActivityReferenceV1Error:
        pass
    store = Path(space) / "cash-coverage-v1" / "cash-coverage.sqlite"
    if store.exists():
        from migrations.reference import desktop_cash_coverage_v1 as cash  # noqa: PLC0415
        state = cash.read_desktop_cash_coverage_reviewed_import_state_v1(store, context)
        totals["cash_command"] = set(state["active_cash_event_refs_by_source_candidate_fingerprint"])
    totals["taxable_document"] = set(references.read_activity_taxable_documents_v1(space, context)["values"])
    from migrations.reference import advance_lump_sum_v1 as advance  # noqa: PLC0415
    totals["advance_lump_sum"] = {references.advance_lump_sum_provenance_key_v1(item["asset_id"], item["account_id"], item["calculation_year"])
                                  for item in advance.read_advance_lump_sums_v1(space, context)["bookings"]}
    from migrations.reference import stock_split_v1 as splits  # noqa: PLC0415
    totals["stock_split"] = {item["split_ref"] for item in splits.read_stock_splits_v1(space, context)["entries"]}
    return totals


def reader_overview_v1(space: str | Path, context: Any, ensure_baseline: bool = True) -> dict[str, Any]:
    """Verwaltung der Leser (rc.380): je Leser Version, Pruefstand im Portfolio und Buchungen mit seiner Herkunft; je Art die Buchungen ohne
    Herkunft. Zaehlwerte, keine Inhalte. ``ensure_baseline=False`` liest nur."""
    labels = _portfolio_rows(space)
    portfolios = list(labels)
    if ensure_baseline:
        _ensure_baseline(space, context, _now())
    provenance = references.read_reader_provenance_v1(space, context)["provenance"]
    totals = _booking_totals(space, context)
    by_reader: Counter = Counter()
    by_code: Counter = Counter()
    with_provenance: dict[str, set[str]] = {kind: set() for kind in references.PROVENANCE_KINDS}
    for compound, entry in provenance.items():
        kind, key = compound.split(":", 1)
        if key in totals.get(kind, set()):
            with_provenance[kind].add(key)
        for reader in entry["readers"]:
            by_reader[(reader["plugin_id"], reader["reader_id"], reader["domain"])] += 1
            by_code[(reader["plugin_id"], reader["reader_id"], reader["domain"], reader["code_sha256"])] += 1
    specs = reader_plugins.reader_specs_v1()
    identities = [reader_plugins.reader_check_identity_v1(spec.reader_id, spec.domain) for spec in specs]
    # Aktiv je Portfolio und Kompatibilitaet installierter Plugins nach Updates (rc.381); die Uebersicht startet keinen Selbsttest.
    from migrations.reference import statement_reader_admin_v1 as admin  # noqa: PLC0415
    active = admin.active_plugins_v1(space, context)
    compatibility = {plugin_id: admin.plugin_compatibility_v1(space, context, plugin_id, run=False).get("status")
                     for plugin_id in {spec.plugin_id for spec in specs}}
    # Je Portfolio der Stand; die Felder ohne Portfolio-Bezug spiegeln das erste Portfolio (ein Portfolio: wie bisher).
    per_portfolio = {portfolio: _read_checks(space, context, portfolio, identities) for portfolio in portfolios} if identities else {}
    empty = [{"plugin_code_sha256": item["plugin_code_sha256"], "status": "unchecked", "checked": None, "shared_changed": False, "previous": None}
             for item in identities]
    checks = per_portfolio[portfolios[0]] if portfolios and identities else empty
    readers = []
    for index, (spec, check) in enumerate(zip(specs, checks)):
        current = reader_plugins.reader_identity_v1(spec.reader_id, spec.domain)
        legacy = reader_plugins.legacy_code_sha256s_v1(spec.reader_id, spec.domain)   # Buchungen vor rc.419 mit gleichem Code und Regeln
        readers.append({"plugin_id": spec.plugin_id, "reader_id": spec.reader_id, "domain": spec.domain, "label": spec.label,
                        "institution": spec.institution, "plugin_version": spec.plugin_version, "generator": spec.generator,
                        "plugin_code_sha256": check["plugin_code_sha256"], "check_status": check["status"], "checked": check["checked"],
                        "shared_changed": check["shared_changed"], "previous": check["previous"],
                        "checks": [{"portfolio_id": portfolio, "portfolio_label": labels[portfolio], "status": per_portfolio[portfolio][index]["status"],
                                    "checked": per_portfolio[portfolio][index]["checked"], "previous": per_portfolio[portfolio][index]["previous"],
                                    "shared_changed": per_portfolio[portfolio][index]["shared_changed"]} for portfolio in portfolios],
                        "origin": spec.origin, "compatibility": compatibility.get(spec.plugin_id),
                        "active": [{"portfolio_id": portfolio, "active": spec.plugin_id in active.get(portfolio, set())} for portfolio in portfolios],
                        "bookings": by_reader[(spec.plugin_id, spec.reader_id, spec.domain)],
                        "bookings_current_code": by_code[(spec.plugin_id, spec.reader_id, spec.domain, current["code_sha256"])]
                        + (by_code[(spec.plugin_id, spec.reader_id, spec.domain, legacy["code_sha256"])] if legacy else 0)})
    known = {(item["plugin_id"], item["reader_id"], item["domain"]) for item in readers}
    others = [{"plugin_id": plugin, "reader_id": reader, "domain": domain, "bookings": count}
              for (plugin, reader, domain), count in sorted(by_reader.items()) if (plugin, reader, domain) not in known]
    kinds = [{"kind": kind, "label": KIND_LABELS[kind], "total": len(totals[kind]), "with_provenance": len(with_provenance[kind]),
              "without_provenance": len(totals[kind] - with_provenance[kind])} for kind in references.PROVENANCE_KINDS]
    return {"portfolio_id": portfolios[0] if portfolios else None, "portfolios": [{"portfolio_id": key, "label": value} for key, value in labels.items()],
            "readers": readers, "other_readers": others, "kinds": kinds,
            "problems": reader_plugins.reader_plugin_problems_v1(), "check_entries": len(references.list_reader_checks_v1(space, context)["entries"])}


def reader_check_baseline_v1(space: str | Path, context: Any, recorded_at_utc: str | None = None) -> dict[str, Any]:
    """Erster Kontakt mit rc.380 (Start der Data-App): Speicher anlegen, in einem Datenraum aus der Zeit davor mit dem Bestandseintrag. Danach ohne Wirkung."""
    try:
        present = references.reader_check_store_present_v1(space)
        if not present:
            _ensure_baseline(space, context, recorded_at_utc or _now())
        entries = references.list_reader_checks_v1(space, context)["entries"]
    except references.AssetActivityReferenceV1Error:
        _abort("statement_reader_check_store_invalid")
        return {}
    return {"status": "present" if present else ("baseline" if entries else "empty"), "entry_count": len(entries)}


__all__ = ["FAILURE_CODES", "reader_check_baseline_v1", "reader_check_portfolios_v1", "KIND_LABELS", "StatementReaderCheckV1Error", "check_identity_from_provenance_v1", "confirm_reader_checks_v1",
           "reader_check_portfolio_v1", "reader_checks_v1", "reader_overview_v1", "require_reader_checks_v1"]
