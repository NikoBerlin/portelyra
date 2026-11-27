"""Kosten kostenpflichtiger Kursanbieter: Zeitlauf nur nach Einschalten, Obergrenze, Abbruch bei 429 (#546, rc.390).

Festlegungen vom 09.11.2026 (#546): Kostenpflichtige Anbieter (``cost`` im Manifest ``free_quota`` oder ``paid``) laufen
im taeglichen Zeitlauf nur, wenn das je Anbieter eingeschaltet ist. Eine optionale Obergrenze gilt je Tag bzw. Monat; bei Erreichen haelt
Portelyra mit Grund an. Es gibt keine Wiederholschleifen; HTTP 429 beendet den Lauf mit Grund. Kostenlose Anbieter (Yahoo) zaehlen nicht.

Gezaehlt wird jede beantwortete Anfrage (auch Fehler des Dienstes, denn viele Anbieter rechnen sie ab), nicht ein Verbindungsfehler. Tag
und Monat in UTC. Speicher ``price-provider-plugins-v1/provider-costs.sqlite`` im Datenraum: Einstellungen nur anhaengend, Zaehler je Tag
veraenderlich. Jede Aenderung der Einstellung mit Vorschau und Einmalbestaetigung.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping

from migrations.reference import price_provider_plugins_v1 as providers

AREA = "price-provider-plugins-v1"
STORE = "provider-costs.sqlite"
SCHEMA_VERSION = 1
ORIGINS = ("interactive", "scheduled")
# Der Zeitlauf (desktop_refresh_all.R --origin timer) setzt dieses Merkmal fuer sich und alle Kindprozesse (rc.391). Es kann nur sperren:
# Ist es gesetzt, gilt jeder Abruf als Zeitlauf, egal was der einzelne Schritt meldet.
RUN_ORIGIN_ENV = "PORTELYRA_RUN_ORIGIN"
CAP_MAX = 10_000_000
FAILURE_CODES = (
    "price_provider_costs_input_invalid", "price_provider_costs_store_invalid", "price_provider_costs_preview_stale",
    "price_provider_costs_confirmation_required", "price_provider_costs_scheduled_disabled", "price_provider_costs_daily_cap_reached",
    "price_provider_costs_monthly_cap_reached", "price_provider_costs_rate_limited",
)
SCHEMA = (
    "CREATE TABLE cost_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE cost_setting(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, provider_id TEXT NOT NULL CHECK(length(provider_id) BETWEEN 2 AND 41),"
    "scheduled_enabled INTEGER NOT NULL CHECK(scheduled_enabled IN (0, 1)),"
    f"daily_cap INTEGER CHECK(daily_cap IS NULL OR daily_cap BETWEEN 1 AND {CAP_MAX}),"
    f"monthly_cap INTEGER CHECK(monthly_cap IS NULL OR monthly_cap BETWEEN 1 AND {CAP_MAX}),"
    "actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TRIGGER cost_setting_no_update BEFORE UPDATE ON cost_setting BEGIN SELECT RAISE(ABORT, 'cost_setting_immutable'); END",
    "CREATE TRIGGER cost_setting_no_delete BEFORE DELETE ON cost_setting BEGIN SELECT RAISE(ABORT, 'cost_setting_immutable'); END",
    "CREATE TABLE cost_usage(provider_id TEXT NOT NULL, usage_day TEXT NOT NULL, request_count INTEGER NOT NULL CHECK(request_count >= 0),"
    "PRIMARY KEY(provider_id, usage_day)) STRICT",
    "CREATE TABLE cost_rate_limit(provider_id TEXT PRIMARY KEY, limited_at_utc TEXT NOT NULL) STRICT",
)
COST_TEXT = {"free": "kostenlos", "free_quota": "kostenlos bis zu einem Kontingent, darüber kostenpflichtig", "paid": "kostenpflichtig"}


class PriceProviderCostsV1Error(RuntimeError):
    """Code fuer die Maschine, ``detail`` fuer den genauen Grund (Anbieter, Zeitraum, Obergrenze, Zahl der Abrufe)."""

    def __init__(self, code: str, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "price_provider_costs_input_invalid"
        self.detail = dict(detail or {})


def _abort(code: str, detail: Mapping[str, Any] | None = None) -> None:
    raise PriceProviderCostsV1Error(code, detail)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


_TOKEN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


@dataclass(frozen=True)
class _Context:
    tenant_id: str
    user_id: str
    data_space_id: str
    actor_id: str


def _context(value: Any) -> _Context:
    fields = ("tenant_id", "user_id", "data_space_id", "actor_id", "role")
    get = (lambda key: value.get(key)) if isinstance(value, Mapping) else (lambda key: getattr(value, key, None))
    items = {key: get(key) for key in fields}
    # Aus dem Zugangsmodul kommt ein dort schon gepruefter Kontext ohne Rolle (nur dessen eigene Klasse, kein beliebiges Objekt).
    if type(value).__name__ == "_Context" and type(value).__module__.endswith("plugin_credentials_v1"):
        items["role"] = "market_worker"
    if items["role"] not in {"desktop_owner", "market_worker"} or not all(isinstance(items[key], str) and _TOKEN.fullmatch(items[key]) for key in fields[:4]):
        _abort("price_provider_costs_input_invalid")
    return _Context(items["tenant_id"], items["user_id"], items["data_space_id"], items["actor_id"])


def _space(space: Any, context: _Context) -> Path:
    path = Path(space)
    if not path.is_dir() or path.is_symlink() or path.name != context.data_space_id:
        _abort("price_provider_costs_store_invalid")
    return path


def _stamp(value: Any) -> str:
    if not isinstance(value, str) or _UTC.fullmatch(value) is None:
        _abort("price_provider_costs_input_invalid")
    return value


def _connect(space: Path, context: _Context, create: bool) -> sqlite3.Connection | None:
    root = space / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("price_provider_costs_store_invalid")
    expected = (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO cost_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("price_provider_costs_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM cost_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("price_provider_costs_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("price_provider_costs_store_invalid")
    return connection


def _paid(provider_id: str) -> providers.ProviderSpec | None:
    """Der Anbieter, wenn er Kosten verursachen kann; sonst None (kostenlos oder nicht geladen)."""
    spec = providers.provider_spec_v1(provider_id)
    return spec if spec is not None and spec.cost != "free" else None


def _state(space: Path, context: _Context, now: str) -> dict[str, dict[str, Any]]:
    connection = _connect(space, context, False)
    day, month = now[:10], now[:7]
    state: dict[str, dict[str, Any]] = {}
    if connection is None:
        return state
    try:
        for row in connection.execute("SELECT * FROM cost_setting ORDER BY entry_id"):
            state.setdefault(row["provider_id"], {})["setting"] = {"scheduled_enabled": bool(row["scheduled_enabled"]), "daily_cap": row["daily_cap"],
                                                                   "monthly_cap": row["monthly_cap"], "since": row["recorded_at_utc"]}
        for row in connection.execute("SELECT provider_id, usage_day, request_count FROM cost_usage WHERE substr(usage_day, 1, 7) = ?", (month,)):
            entry = state.setdefault(row["provider_id"], {})
            entry["month"] = entry.get("month", 0) + row["request_count"]
            if row["usage_day"] == day:
                entry["day"] = row["request_count"]
        for row in connection.execute("SELECT provider_id, limited_at_utc FROM cost_rate_limit"):
            state.setdefault(row["provider_id"], {})["rate_limited_at_utc"] = row["limited_at_utc"]
        return state
    except sqlite3.Error:
        _abort("price_provider_costs_store_invalid")
        raise
    finally:
        connection.close()


_DEFAULT = {"scheduled_enabled": False, "daily_cap": None, "monthly_cap": None, "since": None}


def overview_v1(space: str | Path, context_value: Any, now: str | None = None) -> dict[str, Any]:
    """Je kostenpflichtigem Anbieter: Einstellung, Abrufe heute und im Monat, letzte Abweisung wegen zu vieler Abrufe (429)."""
    context = _context(context_value)
    space = _space(space, context)
    stamp = _stamp(now or _now())
    state = _state(space, context, stamp)
    rows = []
    for spec in providers.provider_specs_v1():
        if spec.cost == "free":
            continue
        entry = state.get(spec.provider_id, {})
        rows.append({"provider_id": spec.provider_id, "label": spec.label, "cost": spec.cost, "cost_text": COST_TEXT[spec.cost],
                     "setting": entry.get("setting", dict(_DEFAULT)), "used_today": entry.get("day", 0), "used_month": entry.get("month", 0),
                     "day": stamp[:10], "month": stamp[:7], "rate_limited_at_utc": entry.get("rate_limited_at_utc")})
    return {"contract_version": "price_provider_costs_overview_v1", "providers": rows}


def _cap(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= CAP_MAX:
        _abort("price_provider_costs_input_invalid")
    return value


def _setting_fingerprint(space: Path, context: _Context) -> str:
    connection = _connect(space, context, False)
    if connection is None:
        return _fingerprint([])
    try:
        return _fingerprint([list(row) for row in connection.execute("SELECT provider_id,scheduled_enabled,daily_cap,monthly_cap FROM cost_setting ORDER BY entry_id")])
    finally:
        connection.close()


def preview_setting_v1(space: str | Path, context_value: Any, provider_id: Any, scheduled_enabled: Any, daily_cap: Any, monthly_cap: Any,
                       created_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    space = _space(space, context)
    spec = _paid(provider_id) if isinstance(provider_id, str) else None
    if spec is None or not isinstance(scheduled_enabled, bool):
        _abort("price_provider_costs_input_invalid")
    stamp = _stamp(created_at_utc or _now())
    before = _state(space, context, stamp).get(spec.provider_id, {}).get("setting", dict(_DEFAULT))
    after = {"scheduled_enabled": scheduled_enabled, "daily_cap": _cap(daily_cap), "monthly_cap": _cap(monthly_cap)}
    notes = [f"{spec.label} ist {COST_TEXT[spec.cost]}. Gezählt wird jede beantwortete Anfrage, auch eine abgewiesene, Tag und Monat in UTC."]
    notes.append("Im täglichen Zeitlauf ruft Portelyra bei diesem Anbieter ab." if scheduled_enabled
                 else "Im täglichen Zeitlauf ruft Portelyra bei diesem Anbieter nicht ab; nur, wenn Sie es selbst anstoßen.")
    for key, period in (("daily_cap", "am Tag"), ("monthly_cap", "im Monat")):
        if after[key] is not None:
            notes.append(f"Obergrenze {period}: {after[key]} Abrufe. Ist sie erreicht, hält Portelyra mit Grund an.")
    notes.append("Weist der Anbieter wegen zu vieler Abrufe ab (HTTP 429), endet der Lauf mit Grund; Portelyra wiederholt nicht von selbst.")
    body = {"contract_version": "price_provider_costs_preview_v1", "provider_id": spec.provider_id, "label": spec.label,
            "manifest_sha256": spec.manifest_sha256, "before": {key: before[key] for key in after}, "after": after,
            "changed": {key: before[key] for key in after} != after, "notes": notes,
            "setting_fingerprint": _setting_fingerprint(space, context), "created_at_utc": stamp}
    body["preview_fingerprint"] = _fingerprint(body)
    return body


def apply_setting_v1(space: str | Path, context_value: Any, preview: Any, confirmed: Any, recorded_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    space = _space(space, context)
    if confirmed is not True:
        _abort("price_provider_costs_confirmation_required")
    if not isinstance(preview, Mapping) or preview.get("contract_version") != "price_provider_costs_preview_v1":
        _abort("price_provider_costs_input_invalid")
    body = {key: value for key, value in preview.items() if key != "preview_fingerprint"}
    spec = _paid(str(preview.get("provider_id")))
    if preview.get("preview_fingerprint") != _fingerprint(body) or preview.get("setting_fingerprint") != _setting_fingerprint(space, context) \
            or spec is None or spec.manifest_sha256 != preview.get("manifest_sha256"):
        _abort("price_provider_costs_preview_stale")
    if not preview["changed"]:
        return {"contract_version": "price_provider_costs_result_v1", "status": "unchanged", "provider_id": spec.provider_id}
    stamp = _stamp(recorded_at_utc or _now())
    after = preview["after"]
    connection = _connect(space, context, True)
    try:
        with connection:
            entry = {"provider_id": spec.provider_id, **after, "actor_id": context.actor_id, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO cost_setting(provider_id,scheduled_enabled,daily_cap,monthly_cap,actor_id,recorded_at_utc,entry_fingerprint)"
                               " VALUES(?,?,?,?,?,?,?)", (spec.provider_id, 1 if after["scheduled_enabled"] else 0, after["daily_cap"], after["monthly_cap"],
                                                          context.actor_id, stamp, _fingerprint(entry)))
    except sqlite3.Error:
        _abort("price_provider_costs_store_invalid")
    finally:
        connection.close()
    return {"contract_version": "price_provider_costs_result_v1", "status": "recorded", "provider_id": spec.provider_id, "recorded_at_utc": stamp}


def effective_origin_v1(origin: Any) -> str:
    """Die strengere Herkunft: im Zeitlauf (Merkmal gesetzt) immer "scheduled", sonst die gemeldete; fehlt sie, wird nicht abgerufen."""
    if origin not in ORIGINS:
        _abort("price_provider_costs_input_invalid")
    return "scheduled" if os.environ.get(RUN_ORIGIN_ENV) == "timer" else origin


def admit_v1(space: str | Path, context_value: Any, provider_id: str, origin: str, now: str | None = None) -> None:
    """Vor jedem Abruf: kostenlos -> frei. Sonst im Zeitlauf nur eingeschaltet, und nie ueber die Obergrenze (genauer Grund in ``detail``)."""
    origin = effective_origin_v1(origin)
    spec = _paid(provider_id)
    if spec is None:
        return
    context = _context(context_value)
    space = _space(space, context)
    stamp = _stamp(now or _now())
    entry = _state(space, context, stamp).get(spec.provider_id, {})
    setting = entry.get("setting", dict(_DEFAULT))
    if origin == "scheduled" and not setting["scheduled_enabled"]:
        _abort("price_provider_costs_scheduled_disabled", {"provider_id": spec.provider_id, "label": spec.label})
    for key, used, period, label in (("daily_cap", entry.get("day", 0), "day", stamp[:10]), ("monthly_cap", entry.get("month", 0), "month", stamp[:7])):
        if setting[key] is not None and used >= setting[key]:
            _abort(f"price_provider_costs_{'daily' if period == 'day' else 'monthly'}_cap_reached",
                   {"provider_id": spec.provider_id, "label": spec.label, "period": period, "period_label": label, "cap": setting[key], "used": used})


def record_v1(space: str | Path, context_value: Any, provider_id: str, status: int, now: str | None = None) -> None:
    """Nach jeder beantworteten Anfrage: zaehlen; bei 429 vermerken und den Lauf mit Grund beenden."""
    spec = _paid(provider_id)
    if spec is None:
        return
    context = _context(context_value)
    space = _space(space, context)
    stamp = _stamp(now or _now())
    connection = _connect(space, context, True)
    try:
        with connection:
            connection.execute("INSERT INTO cost_usage VALUES(?,?,1) ON CONFLICT(provider_id, usage_day) DO UPDATE SET request_count = request_count + 1",
                               (spec.provider_id, stamp[:10]))
            if int(status) == 429:
                connection.execute("INSERT INTO cost_rate_limit VALUES(?,?) ON CONFLICT(provider_id) DO UPDATE SET limited_at_utc = excluded.limited_at_utc",
                                   (spec.provider_id, stamp))
    except sqlite3.Error:
        _abort("price_provider_costs_store_invalid")
    finally:
        connection.close()
    if int(status) == 429:
        _abort("price_provider_costs_rate_limited", {"provider_id": spec.provider_id, "label": spec.label, "at_utc": stamp})


def estimate_v1(space: str | Path, context_value: Any, provider_id: str, calls: int, origin: str = "interactive", now: str | None = None) -> dict[str, Any] | None:
    """Fuer Vorschauen: geschaetzte Abrufe gegen Obergrenze und Zeitlauf. None bei kostenlosen Anbietern."""
    spec = _paid(provider_id)
    if spec is None:
        return None
    if isinstance(calls, bool) or not isinstance(calls, int) or calls < 0:
        _abort("price_provider_costs_input_invalid")
    origin = effective_origin_v1(origin)
    context = _context(context_value)
    space = _space(space, context)
    stamp = _stamp(now or _now())
    entry = _state(space, context, stamp).get(spec.provider_id, {})
    setting = entry.get("setting", dict(_DEFAULT))
    room = [setting[key] - used for key, used in (("daily_cap", entry.get("day", 0)), ("monthly_cap", entry.get("month", 0))) if setting[key] is not None]
    fits = (origin != "scheduled" or setting["scheduled_enabled"]) and all(calls <= left for left in room)
    return {"provider_id": spec.provider_id, "label": spec.label, "cost_text": COST_TEXT[spec.cost], "calls": calls, "used_today": entry.get("day", 0),
            "used_month": entry.get("month", 0), "daily_cap": setting["daily_cap"], "monthly_cap": setting["monthly_cap"],
            "scheduled_enabled": setting["scheduled_enabled"], "fits": fits,
            "note": f"Geschätzt {calls} Abrufe bei {spec.label} ({COST_TEXT[spec.cost]}); heute bisher {entry.get('day', 0)}, im Monat {entry.get('month', 0)}."}


__all__ = [
    "AREA", "FAILURE_CODES", "ORIGINS", "PriceProviderCostsV1Error", "RUN_ORIGIN_ENV", "STORE", "admit_v1", "effective_origin_v1", "apply_setting_v1", "estimate_v1", "overview_v1",
    "preview_setting_v1", "record_v1",
]
