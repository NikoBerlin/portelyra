"""Bewertungsart je Asset und Zeitraum - die Bewertungs-Zeitleiste (#495, rc.393).

Festlegung (10.11.2026): Die Methode fuer Marktpreise und Historien ist allgemein je Asset und Zeitraum einstellbar,
etwa bis Tag X eigene oder Trade-Kurse (weil die Historie nicht ganz abrufbar ist), ab X Yahoo, spaeter ein anderer Anbieter. Das
umfasst den Anbieterwechsel "ab Datum" (Vorgabe heute) und "ganze Historie neu" (Wechsel ab dem ersten Tag).

Festlegungen vom 10.11.2026: Tagesgrenze UTC. Ein eigener Kurs zaehlt auch als Steuer-Tageswert. Es gilt der juengste eigene Kurs bis
zum Tag, auch einer von vor dem Abschnitt; sein Alter wird angezeigt.

Modell: je Asset ganze Versionen der Zeitleiste, nur anhaengend; die juengste gilt. Ein Abschnitt hat ``valid_from`` (``None`` = seit
Beginn, sonst ein UTC-Tag), die Art (``external_market``, ``manual``, ``transaction_only``) und bei Marktdaten Anbieter und Symbol
der Kursreihe. Er gilt bis zum Tag vor dem naechsten Abschnitt. Eine leere Version hebt die Zeitleiste auf.

Ein Marktabschnitt verweist auf die Kurszuordnung seines Anbieters (je Asset und Anbieter gibt es genau eine), nicht auf ein festes
Symbol (Festlegung vom 10.11.2026): Gelesen wird mit dem Symbol der heutigen Zuordnung. Aendert der Eigentuemer das Symbol in der
Kurszuordnung, folgt der Abschnitt fuer seinen ganzen Zeitraum; das gespeicherte Symbol bleibt als Vermerk (``recorded_symbol``, nur
wenn es abweicht). "Bis X altes, ab X neues Symbol beim selben Anbieter" laesst sich so nicht abbilden - die alte Zuordnung ist
ueberschrieben; dafuer braucht es einen zweiten Anbieter.

Ohne Zeitleiste bleibt alles wie bisher: eine Art je Asset aus den Stammdaten, die Kursreihe nach der Regel aus #474. Mit Zeitleiste
entscheidet allein sie, welche Art und welche Reihe einen Tag traegt - ohne stillen Rueckfall: Fehlt der Reihe eines Marktabschnitts
der Tag, ist er offen; ein Tag eines anderen Bereichs zaehlt nicht. Gewaehlt wird beim Lesen; der Bewertungsstand bleibt unberuehrt.

Speicher ``asset-valuation-timeline-v1/timeline.sqlite`` im Datenraum (mit gesichert). Jede Aenderung mit Vorschau und Einmalbestaetigung.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence

AREA = "asset-valuation-timeline-v1"
STORE = "timeline.sqlite"
SCHEMA_VERSION = 1
METHODS = ("external_market", "manual", "transaction_only")
MAX_SEGMENTS = 24
FAILURE_CODES = (
    "asset_valuation_timeline_input_invalid", "asset_valuation_timeline_store_invalid", "asset_valuation_timeline_preview_stale",
    "asset_valuation_timeline_confirmation_required", "asset_valuation_timeline_asset_invalid", "asset_valuation_timeline_series_unknown",
    "asset_valuation_timeline_series_not_ready", "asset_valuation_timeline_method_mismatch", "asset_valuation_timeline_future_date",
)
SCHEMA = (
    "CREATE TABLE timeline_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL CHECK(schema_version = 1),"
    "tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE timeline_version(version_id INTEGER PRIMARY KEY AUTOINCREMENT, asset_id TEXT NOT NULL CHECK(length(asset_id) BETWEEN 3 AND 80),"
    "segments_json TEXT NOT NULL, actor_id TEXT NOT NULL, recorded_at_utc TEXT NOT NULL, version_fingerprint TEXT NOT NULL) STRICT",
    "CREATE INDEX timeline_version_asset ON timeline_version(asset_id, version_id)",
    "CREATE TRIGGER timeline_version_no_update BEFORE UPDATE ON timeline_version BEGIN SELECT RAISE(ABORT, 'timeline_version_immutable'); END",
    "CREATE TRIGGER timeline_version_no_delete BEFORE DELETE ON timeline_version BEGIN SELECT RAISE(ABORT, 'timeline_version_immutable'); END",
)
METHOD_TEXT = {"external_market": "Marktdaten", "manual": "eigene Kurse bzw. Trade-Kurse", "transaction_only": "nur Transaktionen",
               "unit_value": "Einheitswert (1 je Mengeneinheit)"}


class AssetValuationTimelineV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "asset_valuation_timeline_input_invalid"


def _abort(code: str) -> None:
    raise AssetValuationTimelineV1Error(code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


_TOKEN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_PROVIDER = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_ASSET = re.compile(r"^[A-Za-z0-9_.:-]{3,80}$")


# ---------------------------------------------------------------------------------------------------------------------------
# Abschnitte und die Entscheidung je Tag
# ---------------------------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class SegmentV1:
    valid_from: str | None
    method: str
    provider_id: str | None
    provider_symbol: str | None
    valid_until: str | None = None   # letzter Tag (einschliesslich); None = offen
    recorded_symbol: str | None = None   # gespeichertes Symbol, nur wenn die heutige Kurszuordnung ein anderes traegt

    def public(self) -> dict[str, Any]:
        body = {"valid_from": self.valid_from, "valid_until": self.valid_until, "method": self.method, "provider_id": self.provider_id,
                "provider_symbol": self.provider_symbol}
        if self.recorded_symbol is not None:
            body["recorded_symbol"] = self.recorded_symbol
        return body

    def covers(self, day: str) -> bool:
        return (self.valid_from is None or self.valid_from <= day) and (self.valid_until is None or day <= self.valid_until)


class TimelineV1:
    """Die geltenden Zeitleisten eines Datenraums. Leer: alles wie ohne Zeitleiste."""

    def __init__(self, segments: Mapping[str, Sequence[SegmentV1]], fingerprint: str) -> None:
        self._segments = {asset: tuple(rows) for asset, rows in segments.items() if rows}
        self.fingerprint = fingerprint if self._segments else ""

    def __bool__(self) -> bool:
        return bool(self._segments)

    def assets(self) -> list[str]:
        return sorted(self._segments)

    def has(self, asset_id: str) -> bool:
        return asset_id in self._segments

    def segments(self, asset_id: str) -> tuple[SegmentV1, ...]:
        return self._segments.get(asset_id, ())

    def segment_on(self, asset_id: str, day: str) -> SegmentV1 | None:
        return next((row for row in self._segments.get(asset_id, ()) if row.covers(day)), None)

    def current(self, asset_id: str) -> SegmentV1 | None:
        rows = self._segments.get(asset_id)
        return rows[-1] if rows else None

    def method_on(self, asset_id: str, day: str, default: str | None = None) -> str | None:
        segment = self.segment_on(asset_id, day)
        return default if segment is None else segment.method

    def has_method(self, asset_id: str, method: str) -> bool:
        return any(row.method == method for row in self._segments.get(asset_id, ()))

    def market_series(self, asset_id: str) -> list[tuple[str, str]]:
        """Anbieter und Symbol jeder Marktreihe der Zeitleiste (fuer Sammellauf und Neuaufbau)."""
        seen: list[tuple[str, str]] = []
        for row in self._segments.get(asset_id, ()):
            if row.method == "external_market" and (row.provider_id, row.provider_symbol) not in seen:
                seen.append((row.provider_id, row.provider_symbol))
        return seen

    def day_key(self, day: str) -> str:
        """Abdruck dessen, was an einem Tag gilt - fuer den rollenden Abdruck der Tageshistorie. Leer ohne Zeitleiste."""
        if not self._segments:
            return ""
        parts = {asset: self.segment_on(asset, day) for asset in sorted(self._segments)}
        return _fingerprint({asset: None if row is None else [row.method, row.provider_id, row.provider_symbol] for asset, row in parts.items()})


EMPTY = TimelineV1({}, "")


def _segments_from(raw: Any) -> list[SegmentV1]:
    """Prueft eine Folge von Abschnitten: der erste ab Beginn, dann aufsteigende Tage, keine zwei gleichen nacheinander."""
    if not isinstance(raw, list) or len(raw) > MAX_SEGMENTS:
        _abort("asset_valuation_timeline_input_invalid")
    rows: list[SegmentV1] = []
    for index, item in enumerate(raw):
        if not isinstance(item, Mapping) or set(item) - {"valid_from", "method", "provider_id", "provider_symbol", "valid_until"}:
            _abort("asset_valuation_timeline_input_invalid")
        valid_from, method = item.get("valid_from"), item.get("method")
        provider_id, symbol = item.get("provider_id"), item.get("provider_symbol")
        if index == 0:
            if valid_from is not None:
                _abort("asset_valuation_timeline_input_invalid")
        elif not isinstance(valid_from, str) or _DAY.fullmatch(valid_from) is None or valid_from <= (rows[-1].valid_from or ""):
            _abort("asset_valuation_timeline_input_invalid")
        if isinstance(valid_from, str):
            try:
                date.fromisoformat(valid_from)
            except ValueError:
                _abort("asset_valuation_timeline_input_invalid")
        if method not in METHODS:
            _abort("asset_valuation_timeline_input_invalid")
        if method == "external_market":
            if not (isinstance(provider_id, str) and _PROVIDER.fullmatch(provider_id) and isinstance(symbol, str) and symbol == symbol.strip()
                    and 1 <= len(symbol) <= 80 and not any(ord(c) < 32 for c in symbol)):
                _abort("asset_valuation_timeline_input_invalid")
        elif provider_id is not None or symbol is not None:
            _abort("asset_valuation_timeline_input_invalid")
        segment = SegmentV1(valid_from, method, provider_id, symbol)
        if rows and (rows[-1].method, rows[-1].provider_id, rows[-1].provider_symbol) == (method, provider_id, symbol):
            _abort("asset_valuation_timeline_input_invalid")
        rows.append(segment)
    # Jeder Abschnitt endet am Tag vor dem naechsten.
    closed = []
    for index, row in enumerate(rows):
        until = None
        if index + 1 < len(rows):
            until = date.fromordinal(date.fromisoformat(rows[index + 1].valid_from).toordinal() - 1).isoformat()
        closed.append(SegmentV1(row.valid_from, row.method, row.provider_id, row.provider_symbol, until))
    return closed


def _resolved(rows: Sequence[SegmentV1], symbols: Mapping[str, str]) -> list[SegmentV1]:
    """Marktabschnitte mit dem Symbol der heutigen Kurszuordnung ihres Anbieters (``symbols``: Anbieter -> Symbol dieses Assets).
    Ohne Zuordnung des Anbieters bleibt das gespeicherte Symbol. Fallen zwei benachbarte Abschnitte dadurch zusammen, gilt einer."""
    result: list[SegmentV1] = []
    for row in rows:
        symbol = symbols.get(row.provider_id) if row.method == "external_market" else None
        if symbol is not None and symbol != row.provider_symbol:
            row = replace(row, provider_symbol=symbol, recorded_symbol=row.provider_symbol)
        if result and (result[-1].method, result[-1].provider_id, result[-1].provider_symbol) == (row.method, row.provider_id, row.provider_symbol):
            before = result.pop()
            row = replace(before, valid_until=row.valid_until, recorded_symbol=before.recorded_symbol or row.recorded_symbol)
        result.append(row)
    return result


def mapping_symbols_v1(data_space: str | Path) -> dict[str, dict[str, str]]:
    """Je Asset und Anbieter das Symbol der Kurszuordnung (Tageshistorie) - auch fuer die Momentaufnahme (Anbieter je Bereich, rc.394)."""
    return _mapping_symbols(Path(data_space))


def _mapping_symbols(space: Path) -> dict[str, dict[str, str]]:
    """Je Asset und Anbieter das Symbol der Kurszuordnung (Tageshistorie). Ohne Stammdaten leer; unlesbare sperren."""
    path = space / "canonical.sqlite"
    if not path.is_file():
        return {}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT asset_id, provider_id, provider_symbol FROM provider_mapping WHERE capability='daily_history'").fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("asset_valuation_timeline_store_invalid")
        raise
    result: dict[str, dict[str, str]] = {}
    for asset_id, provider_id, symbol in rows:
        result.setdefault(asset_id, {})[provider_id] = symbol
    return result


# ---------------------------------------------------------------------------------------------------------------------------
# Speicher
# ---------------------------------------------------------------------------------------------------------------------------

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
    if items["role"] != "desktop_owner" or not all(isinstance(items[key], str) and _TOKEN.fullmatch(items[key]) for key in fields[:4]):
        _abort("asset_valuation_timeline_input_invalid")
    return _Context(items["tenant_id"], items["user_id"], items["data_space_id"], items["actor_id"])


def _space(space: Any, context: _Context | None = None) -> Path:
    path = Path(space)
    if not path.is_dir() or path.is_symlink() or (context is not None and path.name != context.data_space_id):
        _abort("asset_valuation_timeline_store_invalid")
    return path


def _connect(space: Path, context: _Context | None, create: bool) -> sqlite3.Connection | None:
    root = space / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("asset_valuation_timeline_store_invalid")
    if not store.exists():
        if not create or context is None:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO timeline_binding VALUES(1,?,?,?,?)",
                                   (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id))
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("asset_valuation_timeline_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    try:
        binding = connection.execute("SELECT schema_version,tenant_id,user_id,data_space_id FROM timeline_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("asset_valuation_timeline_store_invalid")
    ok = version == SCHEMA_VERSION and len(binding) == 1 and binding[0][0] == SCHEMA_VERSION and binding[0][3] == space.name
    if ok and context is not None:
        ok = tuple(binding[0][1:]) == (context.tenant_id, context.user_id, context.data_space_id)
    if not ok:
        connection.close()
        _abort("asset_valuation_timeline_store_invalid")
    return connection


def _read_versions(space: Path, context: _Context | None) -> dict[str, list[dict[str, Any]]]:
    connection = _connect(space, context, False)
    if connection is None:
        return {}
    try:
        versions: dict[str, list[dict[str, Any]]] = {}
        for version_id, asset_id, segments_json, actor_id, recorded_at in connection.execute(
                "SELECT version_id, asset_id, segments_json, actor_id, recorded_at_utc FROM timeline_version ORDER BY version_id"):
            versions.setdefault(asset_id, []).append({"version_id": version_id, "segments": json.loads(segments_json), "actor_id": actor_id,
                                                      "recorded_at_utc": recorded_at})
        return versions
    except (sqlite3.Error, ValueError):
        _abort("asset_valuation_timeline_store_invalid")
        raise
    finally:
        connection.close()


_CACHE: dict[str, tuple[tuple[Any, ...], TimelineV1]] = {}


def _stamp(path: Path) -> tuple[int, int, bytes] | None:
    """Zeit, Groesse und Aenderungszaehler aus dem SQLite-Kopf: Eine Aenderung gleicher Laenge im selben Zeittakt faellt sonst nicht auf."""
    try:
        stat = path.stat()
        with path.open("rb") as handle:
            head = handle.read(28)
    except FileNotFoundError:
        return None
    return (stat.st_mtime_ns, stat.st_size, head[24:28])


def timeline_v1(data_space: str | Path) -> TimelineV1:
    """Die geltenden Zeitleisten eines Datenraums; ohne Speicher leer. Ein unlesbarer Speicher sperrt (kein stiller Rueckfall)."""
    space = Path(data_space)
    store = space / AREA / STORE
    # Die Symbole kommen aus der Kurszuordnung: Eine Aenderung an den Stammdaten erneuert die Zeitleiste.
    try:
        own = _stamp(store)
        if own is None:
            return EMPTY
        stamp = (own, _stamp(space / "canonical.sqlite"), _stamp(space / "canonical.sqlite-wal"))
    except OSError:
        _abort("asset_valuation_timeline_store_invalid")
        raise
    key = str(store.resolve())
    hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    versions = _read_versions(_space(space), None)
    symbols = _mapping_symbols(space) if versions else {}
    current = {asset: _resolved(_segments_from(rows[-1]["segments"]), symbols.get(asset, {})) for asset, rows in versions.items()}
    result = TimelineV1(current, _fingerprint({asset: [row.public() for row in rows] for asset, rows in sorted(current.items())}))
    _CACHE[key] = (stamp, result)
    return result


def methods_on_day_v1(methods: Mapping[str, str], day: str, timeline: TimelineV1 | None) -> dict[str, str]:
    """Die Bewertungsart je Asset an einem Tag: aus der Zeitleiste, sonst aus den Stammdaten."""
    result = dict(methods)
    if timeline:
        for asset in timeline.assets():
            method = timeline.method_on(asset, day)
            if method is not None:
                result[asset] = method
    return result


# ---------------------------------------------------------------------------------------------------------------------------
# Vorschau und Bestaetigung
# ---------------------------------------------------------------------------------------------------------------------------

def _canonical(space: Path, asset_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = space / "canonical.sqlite"
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            asset = connection.execute("SELECT asset_id, display_name, asset_type, valuation_method, status, price_currency FROM asset WHERE asset_id=?",
                                       (asset_id,)).fetchone()
            mappings = [dict(row) for row in connection.execute(
                "SELECT provider_id, provider_symbol, verification_status, enabled, provider_currency FROM provider_mapping "
                "WHERE asset_id=? AND capability='daily_history' ORDER BY provider_id", (asset_id,))]
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("asset_valuation_timeline_store_invalid")
        raise
    # Ein Einheitswert bei einem Nicht-Cash-Asset (bis rc.392 ueber "Bewertungsart aendern" waehlbar) wird angezeigt und laesst sich
    # verlassen, aber nicht neu waehlen: Abschnitte kennen nur die drei Arten.
    if asset is None or asset["status"] != "active" or asset["asset_type"] == "cash" or asset["valuation_method"] not in METHODS + ("unit_value",):
        _abort("asset_valuation_timeline_asset_invalid")
    return dict(asset), mappings


def _valuation_coverage(space: Path, asset_id: str) -> dict[str, dict[str, Any]]:
    """Je Symbol die bewerteten Tage im Bewertungsstand (Anzahl, erster, letzter) - fuer die Vorschau."""
    path = space / "market-valuation-state-v1" / "valuation-state.sqlite"
    if not path.is_file():
        return {}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = connection.execute(
                "SELECT s.provider_symbol, count(d.trading_date), min(d.trading_date), max(d.trading_date) FROM valuation_scope s "
                "LEFT JOIN valuation_day d ON d.scope_ref=s.scope_ref AND d.target_decimal IS NOT NULL WHERE s.asset_id=? GROUP BY s.provider_symbol",
                (asset_id,)).fetchall()
        finally:
            connection.close()
    except sqlite3.Error:
        return {}
    return {symbol: {"days": count, "first": first, "last": last} for symbol, count, first, last in rows}


def _overlap(space: Path, asset_id: str, before: SegmentV1 | None, after: SegmentV1, limit: int = 5) -> list[dict[str, Any]]:
    """Vergleich an einem Wechsel zwischen zwei Marktreihen: die letzten gemeinsamen Tage vor dem Wechsel, Wert je Stueck in EUR."""
    if before is None or before.method != "external_market" or after.method != "external_market" or after.valid_from is None:
        return []
    path = space / "market-valuation-state-v1" / "valuation-state.sqlite"
    if not path.is_file():
        return []
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            def series(symbol: str) -> dict[str, str]:
                return {day: value for day, value in connection.execute(
                    "SELECT d.trading_date, d.target_decimal FROM valuation_scope s JOIN valuation_day d USING(scope_ref) WHERE s.asset_id=? "
                    "AND s.provider_symbol=? AND d.target_decimal IS NOT NULL AND d.trading_date<=? ORDER BY d.trading_date DESC LIMIT 60",
                    (asset_id, symbol, after.valid_from))}
            old, new = series(before.provider_symbol), series(after.provider_symbol)
        finally:
            connection.close()
    except sqlite3.Error:
        return []
    days = sorted(set(old) & set(new), reverse=True)[:limit]
    return [{"day": day, "before": old[day], "after": new[day]} for day in sorted(days)]


def read_timeline_v1(space: str | Path, context_value: Any, asset_id: str) -> dict[str, Any]:
    """Die geltende Zeitleiste eines Assets mit Kursabdeckung je Reihe; ohne Eintrag die eine Art aus den Stammdaten."""
    context = _context(context_value)
    space = _space(space, context)
    asset, mappings = _canonical(space, asset_id)
    versions = _read_versions(space, context).get(asset_id, [])
    symbols = {row["provider_id"]: row["provider_symbol"] for row in mappings}
    segments = _resolved(_segments_from(versions[-1]["segments"]), symbols) if versions else []
    return {"contract_version": "asset_valuation_timeline_v1", "asset_id": asset_id, "asset_name": asset["display_name"],
            "valuation_method": asset["valuation_method"], "explicit": bool(segments),
            "segments": [row.public() for row in segments] or [SegmentV1(None, asset["valuation_method"], None, None).public()],
            "mappings": [{**row, "enabled": bool(row["enabled"])} for row in mappings], "coverage": _valuation_coverage(space, asset_id),
            "version_count": len(versions), "updated_at_utc": versions[-1]["recorded_at_utc"] if versions else None}


def _state_fingerprint(space: Path, context: _Context, asset_id: str) -> str:
    versions = _read_versions(space, context).get(asset_id, [])
    return _fingerprint(versions[-1] if versions else None)


def preview_timeline_v1(space: str | Path, context_value: Any, asset_id: Any, segments: Any, created_at_utc: str | None = None) -> dict[str, Any]:
    """Vorschau einer neuen Zeitleiste: Abschnitte, Kursabdeckung je Marktreihe, Vergleich an jedem Anbieterwechsel, ob die
    Bewertungsart in den Stammdaten mit umgestellt werden muss. Eine leere Folge hebt die Zeitleiste auf."""
    context = _context(context_value)
    space = _space(space, context)
    if not isinstance(asset_id, str) or _ASSET.fullmatch(asset_id) is None:
        _abort("asset_valuation_timeline_input_invalid")
    asset, mappings = _canonical(space, asset_id)
    rows = _segments_from(segments) if segments else []
    stamp = created_at_utc or _now()
    if not isinstance(stamp, str) or _UTC.fullmatch(stamp) is None:
        _abort("asset_valuation_timeline_input_invalid")
    today = stamp[:10]
    if any(row.valid_from is not None and row.valid_from > today for row in rows):
        _abort("asset_valuation_timeline_future_date")
    coverage = _valuation_coverage(space, asset_id)
    by_provider = {row["provider_id"]: row for row in mappings}
    series = []
    for row in rows:
        if row.method != "external_market":
            continue
        mapping = by_provider.get(row.provider_id)
        # Ein Marktabschnitt verweist auf die Zuordnung seines Anbieters: Hat der Anbieter eine, muss das Symbol ihres sein (gelesen wird
        # ohnehin mit ihm). Ohne Zuordnung traegt nur eine Reihe aus dem Bewertungsstand.
        if mapping is not None and mapping["provider_symbol"] != row.provider_symbol:
            _abort("asset_valuation_timeline_series_unknown")
        if mapping is None and row.provider_symbol not in coverage:
            _abort("asset_valuation_timeline_series_unknown")
        if row is rows[-1] and (mapping is None or mapping["verification_status"] != "verified" or not mapping["enabled"]):
            # Die laufende Reihe muss abrufbar sein; fruehere duerfen aus dem Bewertungsstand stammen.
            _abort("asset_valuation_timeline_series_not_ready")
        series.append({"provider_id": row.provider_id, "provider_symbol": row.provider_symbol, "mapping_present": mapping is not None,
                       "coverage": coverage.get(row.provider_symbol, {"days": 0, "first": None, "last": None})})
    last_method = rows[-1].method if rows else asset["valuation_method"]
    comparisons = []
    for index in range(1, len(rows)):
        compared = _overlap(space, asset_id, rows[index - 1], rows[index])
        if rows[index - 1].method == "external_market" and rows[index].method == "external_market":
            comparisons.append({"valid_from": rows[index].valid_from, "before": rows[index - 1].provider_symbol, "after": rows[index].provider_symbol,
                                "days": compared})
    body = {"contract_version": "asset_valuation_timeline_preview_v1", "asset_id": asset_id, "asset_name": asset["display_name"],
            "segments": [row.public() for row in rows], "series": series, "comparisons": comparisons,
            "catalog_method_before": asset["valuation_method"], "catalog_method_after": last_method,
            "catalog_method_change": last_method != asset["valuation_method"], "state_fingerprint": _state_fingerprint(space, context, asset_id),
            "created_at_utc": stamp}
    body["notes"] = _notes(body, rows)
    body["preview_fingerprint"] = _fingerprint(body)
    return body


def _german_day(value: str | None) -> str:
    return "" if not value else f"{value[8:10]}.{value[5:7]}.{value[:4]}"


def _provider_label(provider_id: str | None) -> str:
    try:
        from migrations.reference.price_provider_plugins_v1 import provider_spec_v1
        spec = provider_spec_v1(str(provider_id))
        return spec.label if spec is not None else str(provider_id)
    except Exception:  # noqa: BLE001 - ohne lesbares Plugin bleibt die Kennung stehen
        return str(provider_id)


def _notes(body: Mapping[str, Any], rows: Sequence[SegmentV1]) -> list[str]:
    if not rows:
        return ["Die Zeitleiste wird aufgehoben: Es gilt wieder die eine Bewertungsart aus den Stammdaten für die ganze Zeit."]
    notes = []
    for row in rows:
        start = "seit Beginn" if row.valid_from is None else f"ab {_german_day(row.valid_from)}"
        until = "" if row.valid_until is None else f" bis {_german_day(row.valid_until)}"
        what = METHOD_TEXT[row.method] + ("" if row.method != "external_market" else f" ({_provider_label(row.provider_id)}, {row.provider_symbol})")
        notes.append(f"{start}{until}: {what}")
    for item in body["series"]:
        cover = item["coverage"]
        notes.append(f"Kursreihe {item['provider_symbol']}: {cover['days']} bewertete Tage" +
                     ("" if not cover["first"] else f" von {_german_day(cover['first'])} bis {_german_day(cover['last'])}") +
                     ("" if item["mapping_present"] else " (nur noch im Bewertungsstand; ein Neuaufbau kann sie nicht wiederherstellen)"))
    notes.append("Tage eines Marktabschnitts ohne Kurs dieser Reihe bleiben offen; Portelyra nimmt nicht still eine andere Reihe.")
    if body["catalog_method_change"]:
        notes.append(f"Die Bewertungsart in den Stammdaten wird mit umgestellt: {METHOD_TEXT[body['catalog_method_before']]} → "
                     f"{METHOD_TEXT[body['catalog_method_after']]} (gilt für heute und neue Abrufe).")
    notes.append("Tageshistorie und Steuer-Tageswerte rechnen ab dem ersten geänderten Tag neu; versiegelte Snapshots bleiben, wie sie sind.")
    return notes


def apply_timeline_v1(space: str | Path, context_value: Any, preview: Any, confirmed: Any, recorded_at_utc: str | None = None) -> dict[str, Any]:
    context = _context(context_value)
    space = _space(space, context)
    if confirmed is not True:
        _abort("asset_valuation_timeline_confirmation_required")
    if not isinstance(preview, Mapping) or preview.get("contract_version") != "asset_valuation_timeline_preview_v1":
        _abort("asset_valuation_timeline_input_invalid")
    body = {key: value for key, value in preview.items() if key != "preview_fingerprint"}
    if preview.get("preview_fingerprint") != _fingerprint(body) or preview.get("state_fingerprint") != _state_fingerprint(space, context, preview["asset_id"]):
        _abort("asset_valuation_timeline_preview_stale")
    asset, _mappings = _canonical(space, preview["asset_id"])
    # Die Stammdaten muessen zuerst umgestellt sein (R, Katalogbefehl); sonst widersprechen sich heutige Art und Zeitleiste.
    if asset["valuation_method"] != preview["catalog_method_after"]:
        _abort("asset_valuation_timeline_method_mismatch")
    segments = [{key: row[key] for key in ("valid_from", "method", "provider_id", "provider_symbol")} for row in preview["segments"]]
    _segments_from(segments) if segments else None
    stamp = recorded_at_utc or _now()
    connection = _connect(space, context, True)
    try:
        with connection:
            record = {"asset_id": preview["asset_id"], "segments": segments, "actor_id": context.actor_id, "recorded_at_utc": stamp}
            connection.execute("INSERT INTO timeline_version(asset_id,segments_json,actor_id,recorded_at_utc,version_fingerprint) VALUES(?,?,?,?,?)",
                               (preview["asset_id"], json.dumps(segments, sort_keys=True), context.actor_id, stamp, _fingerprint(record)))
    except sqlite3.Error:
        _abort("asset_valuation_timeline_store_invalid")
    finally:
        connection.close()
    return {"contract_version": "asset_valuation_timeline_result_v1", "status": "recorded", "asset_id": preview["asset_id"],
            "segment_count": len(segments), "recorded_at_utc": stamp}


def valued_series_v1(space: str | Path, context_value: Any) -> dict[str, Any]:
    """Alle Kursreihen (Asset und Symbol), die der Bewertungsstand fuehrt - ein Aufruf fuer alle Assets, unabhaengig von der Zeitleiste.
    Der Sammellauf bewertet eine Reihe ohne Eintrag, auch wenn ihr kein Kurstag fehlt: etwa wenn der Stand nach einem Restore neu
    aufgebaut wird oder verloren ging (#493). Ohne Stand: keine Reihe."""
    context = _context(context_value)
    space = _space(space, context)
    path = space / "market-valuation-state-v1" / "valuation-state.sqlite"
    rows: list[tuple[str, str]] = []
    if path.is_file():
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            rows = connection.execute("SELECT DISTINCT asset_id, provider_symbol FROM valuation_scope ORDER BY asset_id, provider_symbol").fetchall()
        finally:
            connection.close()
    return {"contract_version": "asset_valuation_series_v1", "series": [[asset_id, symbol] for asset_id, symbol in rows]}


def overview_v1(space: str | Path, context_value: Any) -> dict[str, Any]:
    """Alle Assets mit Zeitleiste und ihre Abschnitte - fuer Datenbasis und Asset-Center."""
    context = _context(context_value)
    space = _space(space, context)
    versions = _read_versions(space, context)
    symbols = _mapping_symbols(space) if versions else {}
    rows = []
    for asset_id, items in sorted(versions.items()):
        segments = _resolved(_segments_from(items[-1]["segments"]), symbols.get(asset_id, {})) if items[-1]["segments"] else []
        if segments:
            rows.append({"asset_id": asset_id, "segments": [row.public() for row in segments], "updated_at_utc": items[-1]["recorded_at_utc"]})
    return {"contract_version": "asset_valuation_timeline_overview_v1", "assets": rows}


__all__ = [
    "AREA", "EMPTY", "FAILURE_CODES", "METHODS", "METHOD_TEXT", "STORE", "AssetValuationTimelineV1Error", "SegmentV1", "TimelineV1",
    "apply_timeline_v1", "mapping_symbols_v1", "methods_on_day_v1", "overview_v1", "preview_timeline_v1", "read_timeline_v1", "timeline_v1",
    "valued_series_v1",
]
