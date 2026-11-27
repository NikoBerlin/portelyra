"""Nutzereinstellungen (#500) und die Dauer der Schritte von "Alles aktualisieren" (#457) - neben den Stammdaten.

Sie werden in einem eigenen Reiter
"Einstellungen" der Data-App bedient und gelten fuer alle Apps. Sie gehoeren nicht zur Rechnung; Maschinendaten bleiben exakt.

- **amount_decimals:** Nachkommastellen von Euro-Betraegen in Uebersichten, "0" (Vorgabe) oder "2".
- **tint:** farbige Hinterlegung von Erfolgskennzahlen, "on" (Vorgabe) oder "off".
- **history_keep_runs:** wie viele Laeufe der Tageshistorie nach einer Veroeffentlichung bleiben, 2 bis 50 (Vorgabe 5,
  Festlegung 22.10.2026).
- **expert_tools:** Expertenwerkzeuge zeigen, "off" (Vorgabe) oder "on" (#452, Festlegung 22.10.2026). Seit rc.309
  veroeffentlicht: Das Cockpit zeigt damit den Reiter "Abschluss im Detail" (#492).
- **analysis_period:** Zeitraum, mit dem die Reiter der Analyse oeffnen (Festlegung 23.10.2026): "1m", "3m", "qtd" (laufendes
  Quartal), "ytd" (laufendes Jahr), "1y", "3y", "5y" oder "all" (Vorgabe).
- **history_lines:** welche Linien und Kennwerte der Portfolio-Verlauf der Analyse beim Oeffnen zeigt (#531 Punkt 2), durch Komma
  getrennt in fester Folge; Vorgabe alle. Umschalten laesst es sich dort jederzeit.
- **small_holdings_threshold:** Kleinstbestaende (#534, Festlegung 04.11.2026): Cash-Salden ueber 0 und unter dieser Grenze in
  Euro auf geschlossenen oder ruhenden Konten blenden Analyse und Datenbasis aus, mit Zaehlung; ein Schalter zeigt sie. Vorgabe "1",
  "0" heisst nichts ausblenden, hoechstens 1000 mit bis zu zwei Nachkommastellen. Gerechnet wird weiter mit dem exakten Wert.
- **market_day_completion:** ab wann Tageskurse als abgeschlossen gelten (#516, Festlegung 05.11.2026): "session_close"
  (Vorgabe, Boersen eine Stunde nach Handelsschluss) oder "calendar_day_end" (nach dem Ende des Kalendertags, bis rc.367).
  Krypto und Wechselkurse gelten in beiden Arten nach dem Tagesende. Die Abrufplanung liest den Wert hier
  (read_market_day_completion_v1); veroeffentlicht wird er nicht.
- **snapshot_parallel_requests:** wie viele Kurse die Momentaufnahme gleichzeitig abruft, "1" bis "32" (Vorgabe "8").
- **carry_across_blocked:** ob ein gesperrter Tag die Folgetage ansteckt (#368), "off" (Vorgabe) oder "on". Wirkt auf die Bewertung.
  Beide lagen bis rc.399 im ableitbaren Bewertungsstand (Tabelle snapshot_setting) und gingen mit ihm verloren (#554). Gelesen wird
  der gesetzte Wert, sonst der alte Wert aus dem Bewertungsstand, sonst die Vorgabe (market_settings_v1); der naechste schreibende
  Lauf uebernimmt den alten Wert einmal (adopt_market_settings_v1). Veroeffentlicht werden sie nicht.

Dazu die Dauer je Schritt des letzten Laufs von "Alles aktualisieren": Die Anzeige nennt sie als Richtwert, solange ein
Schritt laeuft. Beides haengt nur an; je Schluessel und je Schritt gilt der juengste Eintrag. Die anzeigenden Apps lesen die
Einstellungen nicht hier, sondern als veroeffentlichtes Artefakt (display_settings_v1). Kein Providerzugriff, kein Netzzugriff,
kein kanonischer Write.
"""

from __future__ import annotations

from pathlib import Path
import hashlib
import json
import re
import sqlite3

from workers.reference.durable_storage_v1 import settle_new_directory_v1
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1, DesktopProductAssetActivityV1Error, _context,
)

AREA = "user-settings-v1"
STORE = "user-settings.sqlite"
SCHEMA_VERSION = 1
CONTRACT = "user_settings_v1"
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
STEP = re.compile(r"[a-z][a-z0-9_]{1,39}")
HISTORY_LINES = ("net_worth", "market_value", "cost_basis", "cash_documented", "cash", "contributed", "unrealised")
DEFAULTS = {"amount_decimals": "0", "tint": "on", "history_keep_runs": "5", "expert_tools": "off", "drawdown_zones": "", "analysis_period": "all",
            "history_lines": ",".join(HISTORY_LINES), "small_holdings_threshold": "1", "market_day_completion": "session_close",
            "snapshot_parallel_requests": "8", "carry_across_blocked": "off"}
MARKET_DAY_COMPLETION = ("session_close", "calendar_day_end")
SMALL_HOLDINGS_LIMIT = 1000
ANALYSIS_PERIODS = ("1m", "3m", "qtd", "ytd", "1y", "3y", "5y", "all")
# Rueckgangszonen der Analyse (#506): bis zu drei Schwellen in ganzen Prozent unter dem Hoch, aufsteigend, z. B. "30,50"; leer heisst keine.
ZONE_RANGE = (5, 95)
ZONE_LIMIT = 3
KEEP_RUNS_RANGE = (2, 50)
MAX_STEP_SECONDS = 7 * 24 * 3600
FAILURE_CODES = ("user_settings_confirmation_required", "user_settings_input_invalid", "user_settings_store_invalid")
SCHEMA = (
    "CREATE TABLE user_settings_binding(singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1), schema_version INTEGER NOT NULL"
    " CHECK(schema_version = 1), tenant_id TEXT NOT NULL, user_id TEXT NOT NULL, data_space_id TEXT NOT NULL) STRICT",
    "CREATE TABLE setting_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, setting_key TEXT NOT NULL, setting_value TEXT NOT NULL,"
    " recorded_at_utc TEXT NOT NULL, entry_fingerprint TEXT NOT NULL) STRICT",
    "CREATE TABLE step_duration_entry(entry_id INTEGER PRIMARY KEY AUTOINCREMENT, step_code TEXT NOT NULL,"
    " seconds INTEGER NOT NULL CHECK(seconds >= 0), recorded_at_utc TEXT NOT NULL) STRICT",
    *(f"CREATE TRIGGER {table}_no_{action} BEFORE {action.upper()} ON {table} BEGIN SELECT RAISE(ABORT, '{table}_immutable'); END"
      for table in ("setting_entry", "step_duration_entry") for action in ("update", "delete")),
    "CREATE VIEW current_setting AS SELECT entry.* FROM setting_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM setting_entry later WHERE later.setting_key = entry.setting_key)",
    "CREATE VIEW latest_step_duration AS SELECT entry.* FROM step_duration_entry entry WHERE entry.entry_id = "
    "(SELECT max(later.entry_id) FROM step_duration_entry later WHERE later.step_code = entry.step_code)",
)


class UserSettingsV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _abort(code: str) -> None:
    raise UserSettingsV1Error(code if code in FAILURE_CODES else "user_settings_store_invalid")


def user_settings_context_v1(value):
    """Geprueftes Kontextobjekt; nimmt auch die JSON-Form der CLI-Grenze an."""
    if isinstance(value, dict):
        if set(value) != {"tenant_id", "user_id", "data_space_id", "actor_id", "role"}:
            _abort("user_settings_input_invalid")
        try:
            value = DesktopProductAssetActivityContextV1(**value)
        except TypeError:
            _abort("user_settings_input_invalid")
    try:
        return _context(value)
    except DesktopProductAssetActivityV1Error:
        _abort("user_settings_input_invalid")


def _valid_value(key: str, value) -> str:
    if not isinstance(value, str):
        _abort("user_settings_input_invalid")
    if key == "amount_decimals" and value in ("0", "2"):
        return value
    if key in ("tint", "expert_tools", "carry_across_blocked") and value in ("on", "off"):
        return value
    if key == "snapshot_parallel_requests" and re.fullmatch(r"[0-9]{1,2}", value) and 1 <= int(value) <= 32:
        return str(int(value))
    if key == "analysis_period" and value in ANALYSIS_PERIODS:
        return value
    if key == "market_day_completion" and value in MARKET_DAY_COMPLETION:
        return value
    if key == "history_lines":
        parts = value.split(",")
        if parts and all(part in HISTORY_LINES for part in parts) and len(set(parts)) == len(parts):
            return ",".join(line for line in HISTORY_LINES if line in parts)
    if key == "small_holdings_threshold" and re.fullmatch(r"(0|[1-9][0-9]{0,3})(\.[0-9]{1,2})?", value):
        from decimal import Decimal
        amount = Decimal(value)
        if amount <= SMALL_HOLDINGS_LIMIT:
            text = format(amount.normalize(), "f")
            return "0" if amount == 0 else text
    if key == "history_keep_runs" and re.fullmatch(r"[0-9]{1,2}", value) and KEEP_RUNS_RANGE[0] <= int(value) <= KEEP_RUNS_RANGE[1]:
        return str(int(value))
    if key == "drawdown_zones":
        if value == "":
            return value
        parts = value.split(",")
        if (len(parts) <= ZONE_LIMIT and all(re.fullmatch(r"[0-9]{1,2}", part) for part in parts)
                and all(ZONE_RANGE[0] <= int(part) <= ZONE_RANGE[1] for part in parts)
                and [int(part) for part in parts] == sorted({int(part) for part in parts})):
            return ",".join(str(int(part)) for part in parts)
    _abort("user_settings_input_invalid")
    return ""


def _connect(space, context, create: bool):
    root = Path(space) / AREA
    store = root / STORE
    if root.is_symlink() or store.is_symlink():
        _abort("user_settings_store_invalid")
    expected = (SCHEMA_VERSION, context.tenant_id, context.user_id, context.data_space_id)
    if not store.exists():
        if not create:
            return None
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        settle_new_directory_v1(root)  # #568: neuer Einstellungsordner, auch seine gocryptfs.diriv festschreiben
        connection = sqlite3.connect(store)
        try:
            with connection:
                for statement in SCHEMA:
                    connection.execute(statement)
                connection.execute("INSERT INTO user_settings_binding VALUES(1,?,?,?,?)", expected)
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error:
            connection.close()
            _abort("user_settings_store_invalid")
        store.chmod(0o600)
    else:
        connection = sqlite3.connect(store if create else f"file:{store}?mode=ro", uri=not create)
    connection.row_factory = sqlite3.Row
    try:
        binding = connection.execute(
            "SELECT schema_version,tenant_id,user_id,data_space_id FROM user_settings_binding WHERE singleton_id=1").fetchall()
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    except sqlite3.Error:
        connection.close()
        _abort("user_settings_store_invalid")
    if version != SCHEMA_VERSION or len(binding) != 1 or tuple(binding[0]) != expected:
        connection.close()
        _abort("user_settings_store_invalid")
    return connection


def read_user_settings_v1(space, context_value) -> dict:
    """Die gueltigen Einstellungen, ohne Eintrag die Vorgabe; 'recorded' nennt, welche ausdruecklich gesetzt sind."""
    context = user_settings_context_v1(context_value)
    connection = _connect(space, context, False)
    values, recorded = dict(DEFAULTS), {}
    if connection is not None:
        try:
            for row in connection.execute("SELECT setting_key, setting_value, recorded_at_utc FROM current_setting"):
                if row["setting_key"] in DEFAULTS:
                    values[row["setting_key"]] = row["setting_value"]
                    recorded[row["setting_key"]] = row["recorded_at_utc"]
        except sqlite3.Error:
            _abort("user_settings_store_invalid")
        finally:
            connection.close()
    return {"contract_version": CONTRACT, "status": "ready", "settings": values, "recorded": recorded, "defaults": dict(DEFAULTS),
            "canonical_write": False}


def read_market_day_completion_v1(space, context) -> str:
    """Ab wann Tageskurse als abgeschlossen gelten, fuer die Abrufplanung (#516). Gebunden an Mandant, Nutzer und Datenraum
    des Aufrufers; ohne Eintrag die Vorgabe. Nur lesend."""
    connection = _connect(space, context, False)
    if connection is None:
        return DEFAULTS["market_day_completion"]
    try:
        row = connection.execute("SELECT setting_value FROM current_setting WHERE setting_key = 'market_day_completion'").fetchone()
    except sqlite3.Error:
        _abort("user_settings_store_invalid")
    finally:
        connection.close()
    value = DEFAULTS["market_day_completion"] if row is None else row["setting_value"]
    if value not in MARKET_DAY_COMPLETION:
        _abort("user_settings_store_invalid")
    return value


def record_user_settings_v1(space, context_value, values, recorded_at_utc, confirmed) -> dict:
    """Haengt die geaenderten Einstellungen an; unveraendert schreibt nichts."""
    context = user_settings_context_v1(context_value)
    if confirmed is not True:
        _abort("user_settings_confirmation_required")
    if not isinstance(values, dict) or not values or not set(values) <= set(DEFAULTS):
        _abort("user_settings_input_invalid")
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("user_settings_input_invalid")
    checked = {key: _valid_value(key, value) for key, value in values.items()}
    current = read_user_settings_v1(space, context)["settings"]
    changed = {key: value for key, value in checked.items() if current[key] != value}
    if not changed:
        return {"contract_version": CONTRACT, "status": "unchanged", "changed": [], "canonical_write": False}
    connection = _connect(space, context, True)
    try:
        with connection:
            for key in sorted(changed):
                body = {"key": key, "value": changed[key], "recorded_at_utc": recorded_at_utc}
                fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                connection.execute("INSERT INTO setting_entry(setting_key,setting_value,recorded_at_utc,entry_fingerprint) VALUES(?,?,?,?)",
                                   (key, changed[key], recorded_at_utc, fingerprint))
    except sqlite3.Error:
        _abort("user_settings_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "changed": sorted(changed), "canonical_write": False}


# Bis rc.399 lagen zwei Einstellungen im Bewertungsstand (#554); dort gelesen wird nur noch zur Uebernahme.
LEGACY_STATE = Path("market-valuation-state-v1") / "valuation-state.sqlite"


def _legacy_market_settings(space) -> dict:
    """Die alten Werte aus dem Bewertungsstand (ohne Bindungspruefung, nur lesend); ohne Stand oder Eintrag leer."""
    path = Path(space) / LEGACY_STATE
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            row = connection.execute("SELECT parallel_request_count, carry_across_blocked FROM snapshot_setting WHERE singleton_id = 1").fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return {}
    found = {}
    if row is not None and type(row[0]) is int and 1 <= row[0] <= 32:
        found["snapshot_parallel_requests"] = str(row[0])
    if row is not None and row[1] in (0, 1):
        found["carry_across_blocked"] = "on" if row[1] == 1 else "off"
    return found


def market_settings_v1(space, context_value) -> dict:
    """Parallele Abrufe der Momentaufnahme und "Sperre steckt Folgetage an" (#554): der gesetzte Wert, sonst der alte aus dem
    Bewertungsstand, sonst die Vorgabe. Nur lesend."""
    current = read_user_settings_v1(space, context_value)
    legacy = _legacy_market_settings(space)

    def pick(key):
        return current["settings"][key] if key in current["recorded"] else legacy.get(key, DEFAULTS[key])
    return {"parallel_request_count": int(pick("snapshot_parallel_requests")), "carry_across_blocked": pick("carry_across_blocked") == "on"}


def adopt_market_settings_v1(space, context_value, recorded_at_utc) -> list:
    """Uebernimmt die alten Werte einmal in die Nutzereinstellungen, nur wo noch nichts gesetzt ist; gleich der Vorgabe schreibt
    nichts (dann geht auch mit dem Bewertungsstand nichts verloren). Gibt die uebernommenen Schluessel zurueck."""
    current = read_user_settings_v1(space, context_value)
    missing = {key: value for key, value in _legacy_market_settings(space).items() if key not in current["recorded"]}
    if not missing:
        return []
    return record_user_settings_v1(space, context_value, missing, recorded_at_utc, True)["changed"]


def set_market_setting_v1(space, context_value, key, value, recorded_at_utc) -> dict:
    """Setzt eine der beiden Einstellungen; vorher die alten Werte uebernehmen, sonst gaelte ein auf die Vorgabe gesetzter Wert als
    unveraendert und der alte bliebe wirksam."""
    if key not in ("snapshot_parallel_requests", "carry_across_blocked"):
        _abort("user_settings_input_invalid")
    adopt_market_settings_v1(space, context_value, recorded_at_utc)
    record_user_settings_v1(space, context_value, {key: value}, recorded_at_utc, True)
    return market_settings_v1(space, context_value)


def owner_settings_context_v1(ids):
    """Kontext des Eigentuemers fuer Aufrufer mit Mandant, Nutzer und Datenraum (Bewertung, Momentaufnahme)."""
    try:
        return user_settings_context_v1(DesktopProductAssetActivityContextV1(ids["tenant_id"], ids["user_id"], ids["data_space_id"], "desktop_owner"))
    except (KeyError, TypeError):
        _abort("user_settings_input_invalid")


def read_step_durations_v1(space, context_value) -> dict:
    """Je Schritt die Dauer des letzten Laufs in Sekunden."""
    context = user_settings_context_v1(context_value)
    connection = _connect(space, context, False)
    durations = {}
    if connection is not None:
        try:
            durations = {row["step_code"]: int(row["seconds"]) for row in connection.execute("SELECT step_code, seconds FROM latest_step_duration")}
        except sqlite3.Error:
            _abort("user_settings_store_invalid")
        finally:
            connection.close()
    return {"contract_version": CONTRACT, "status": "ready", "durations": durations, "canonical_write": False}


def record_step_durations_v1(space, context_value, durations, recorded_at_utc) -> dict:
    """Haengt die Dauer der gelaufenen Schritte an. Es sind Messwerte der Anzeige, keine Angaben des Nutzers."""
    context = user_settings_context_v1(context_value)
    if not isinstance(durations, dict) or not durations or len(durations) > 40:
        _abort("user_settings_input_invalid")
    if not isinstance(recorded_at_utc, str) or UTC.fullmatch(recorded_at_utc) is None:
        _abort("user_settings_input_invalid")
    for step, seconds in durations.items():
        if not isinstance(step, str) or STEP.fullmatch(step) is None or isinstance(seconds, bool) or not isinstance(seconds, int) \
                or not 0 <= seconds <= MAX_STEP_SECONDS:
            _abort("user_settings_input_invalid")
    connection = _connect(space, context, True)
    try:
        with connection:
            for step in sorted(durations):
                connection.execute("INSERT INTO step_duration_entry(step_code,seconds,recorded_at_utc) VALUES(?,?,?)",
                                   (step, durations[step], recorded_at_utc))
    except sqlite3.Error:
        _abort("user_settings_store_invalid")
    finally:
        connection.close()
    return {"contract_version": CONTRACT, "status": "recorded", "steps": sorted(durations), "canonical_write": False}


def history_lines_v1(value: str) -> list[str]:
    """Die gespeicherte Zeichenkette als Liste der Linien in fester Folge; unlesbar heisst alle."""
    parts = value.split(",") if isinstance(value, str) else []
    chosen = [line for line in HISTORY_LINES if line in parts]
    return chosen if chosen else list(HISTORY_LINES)


def small_holdings_threshold_v1(value: str) -> str:
    """Die gespeicherte Grenze fuer Kleinstbestaende als Dezimaltext; unlesbar heisst die Vorgabe."""
    try:
        return _valid_value("small_holdings_threshold", value)
    except UserSettingsV1Error:
        return DEFAULTS["small_holdings_threshold"]


def drawdown_zones_v1(value: str) -> list[int]:
    """Die gespeicherte Zeichenkette als Liste ganzer Prozent (aufsteigend)."""
    return [int(part) for part in value.split(",") if part] if isinstance(value, str) else []


def history_keep_runs_v1(space, context_value) -> int:
    """Wie viele Laeufe der Tageshistorie bleiben; bei unlesbarem Speicher die Vorgabe."""
    try:
        return int(read_user_settings_v1(space, context_value)["settings"]["history_keep_runs"])
    except (UserSettingsV1Error, ValueError, KeyError):
        return int(DEFAULTS["history_keep_runs"])


__all__ = [
    "ANALYSIS_PERIODS", "CONTRACT", "DEFAULTS", "FAILURE_CODES", "HISTORY_LINES", "UserSettingsV1Error", "drawdown_zones_v1", "history_keep_runs_v1",
    "history_lines_v1", "read_step_durations_v1", "small_holdings_threshold_v1",
    "read_user_settings_v1", "record_step_durations_v1", "record_user_settings_v1", "user_settings_context_v1",
    "adopt_market_settings_v1", "market_settings_v1", "owner_settings_context_v1", "set_market_setting_v1",
]
