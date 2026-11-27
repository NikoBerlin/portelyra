"""Einrichtungsdialog vor dem ersten Start (#555): Fragen, Entwurf, Plan und Zustand.

Festlegungen (12.11.2026): eine eigene Seite vor dem Start wie die Startseite des Passwortschutzes; Fragen in
Alltagssprache, jede darf "spaeter" sein; die Antworten liegen bis zur Bestaetigung als Entwurf ohne Wirkung im Home (nur fuer den
Eigentuemer lesbar, nie mit Passwoertern); am Ende eine Zusammenfassung "Das richtet Portelyra ein" mit Gruenden. Uebernommen wird
ueber dieselben Befehle wie die Karten der Einstellungen - dieser Kern rechnet nur, er schreibt nichts in den Datenraum.

- Fragen: maschinelle Kennungen, Auswahlwerte und Vorgaben. Die Texte stehen in der Oberflaeche (apps/shared/desktop_setup_v1.R).
- Entwurf `<home>/setup-draft.json`: Antworten und die Stelle im Dialog. Schluessel mit "pass", "secret", "recovery" oder "token" weist
  der Kern ab, damit nie ein Passwort darin landet.
- Plan: die Schritte aus Antworten und jetzigem Stand, je Schritt mit Grund. Der Abdruck bindet die Bestaetigung an genau den
  gezeigten Plan; aendert sich Antwort oder Stand, gilt die Bestaetigung nicht mehr.
- Zustand `<home>/setup-state.json`: uebernommen oder uebersprungen. Danach erscheint der Dialog nicht mehr von selbst.

Der Dialog erscheint beim Start, wenn es noch keinen Datenraum gibt (erster Start) oder ein Entwurf auf Fortsetzung wartet - nie an
einem eingerichteten Home ohne Entwurf. Ausbau a (rc.402): Datenraum, Portfolio und Umfang (#542). Ausbau b (rc.403): Kursanbieter mit
seinen Bedingungen, Zeitplan "Alles aktualisieren" mit Zustimmung, Passwortschutz vor dem Start. Kurse und Zeitplan fragt der Dialog nur,
wenn der Umfang Marktdaten hat; das Passwort kommt nie in den Entwurf, nur die Wahl und "Mit der Anmeldung entsperren".
Ausbau c (rc.404, Festlegungen 13.11.2026): mit dem Steuerbericht der persoenliche Steuersatz ("weiss ich nicht" erlaubt) und die
Kirchensteuer (ja mit Bundesland: 8 % in Bayern und Baden-Wuerttemberg, sonst 9 %). Der Plan richtet den Steuerbereich ein, waehlt das
Regelmodul v2 fuer alle drei Projektionsarten und belegt die Einordnung je Asset-Typ vor. Der erste Abschluss ist ein eigener Schritt,
mit oder ohne Steuer; die bestaetigte Zusammenfassung gilt als Bestaetigung seiner Vorgaben (ein erster Run-Center-Lauf mit ihnen).
Buchungsweg (#583, 0.3.4, Festlegung 26.11.2026): die Frage "Wie buchen" nach "Was". "Von Hand" ist immer dabei; "aus Belegen und
Auszuegen" ist der Baustein Belege (Import, Eingang und Ablage) und stand bis 0.3.3 als Antwort unter "Wofuer".
Institute und Belegordner (#572 Teil d, 0.3.4, Festlegung 26.11.2026): nur mit dem Baustein Belege. Angeboten werden die mitgelieferten
Leser; Uebernehmen aktiviert die gewaehlten fuer das neue Portfolio und legt den Belegordner fest, ueber dieselben Wege wie die Karten.
Konten legt man weiter in Data an.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

CONTRACT = "desktop_setup_v1"
DRAFT_CONTRACT = "desktop_setup_draft_v1"
PLAN_CONTRACT = "desktop_setup_plan_v1"
STATE_CONTRACT = "desktop_setup_state_v1"
DRAFT_FILE = "setup-draft.json"
STATE_FILE = "setup-state.json"
FAILURE_CODES = (
    "desktop_setup_input_invalid", "desktop_setup_state_invalid", "desktop_setup_plan_stale", "desktop_setup_confirmation_required",
    "desktop_setup_folder_invalid",
)
LATER = "later"
CURRENCIES = ("EUR", "CHF", "USD", "GBP")
# Wie der Umfang je Portfolio (#542, portfolio_configuration_v1.CLASSES); Cash ist dort ein Baustein, hier eine Antwort unter "Was".
HOLDINGS = ("equity_etf", "fund", "bond", "crypto", "commodity", "derivative", "other", "cash")
CLASSES = tuple(item for item in HOLDINGS if item != "cash")
# Wofuer: in Alltagssprache gebuendelt; je Antwort die Bausteine des Umfangs.
PURPOSES: dict[str, tuple[str, ...]] = {
    "performance": ("market_data", "history_analysis"),
    "tax": ("tax_report", "tax_projection"),
}
# Wie gebucht wird (#583, Festlegung 26.11.2026), je Antwort die Bausteine. "manual" (von Hand) ist immer dabei, vorgewaehlt und nicht
# abwaehlbar: Korrektur und Storno laufen darueber. "documents" (aus Belegen und Auszuegen) ist ein Schalter fuer Import, Eingang und
# Ablage. Die Schnittstelle (#544) zeigt die Oberflaeche ausgegraut mit "kommt spaeter"; eine Antwort ist sie nicht.
BOOKINGS: dict[str, tuple[str, ...]] = {"manual": (), "documents": ("documents",)}
BOOKINGS_FIXED = ("manual",)
# Belegordner (#572): hoechstens so lang wie im Eingang (statement_archive_v1.FOLDER_LIMIT); ob er taugt, prueft folder_check_v1 mit
# derselben Regel wie das Festlegen.
FOLDER_MAX = 1000
MODULES = ("cash", "market_data", "history_analysis", "tax_report", "tax_projection", "documents")
NAME_MAX = 80
PROVIDER = "yahoo"
# Zeitplan "Alles aktualisieren" (wie die Karte "Von selbst aktualisieren"): 07:00 holt den abgeschlossenen Vortag, 19:00 auch den
# Xetra-Schluss des Tages (Handelstag abgeschlossen + 1 h, #475). Aenderbar in den Einstellungen.
SCHEDULES: dict[str, tuple[str, ...]] = {"manual": (), "daily": ("07:00",), "twice": ("07:00", "19:00")}
# Steuer (Ausbau c). Das Regelmodul v2 gilt ab 2016 (Manifest); 2016-2019 sind dort rudimentaer, 2020 bis heute vollstaendig.
TAX_PLUGIN = "tax_de_personal_income_tax_projection_v2"
TAX_FROM = "2016-01-01"
TAX_FROM_YEAR = 2016
TAX_YEARS_FROM = 2020
PROJECTION_MODES = ("realized_event", "realized_annual", "unrealized_snapshot")
UNKNOWN = "unknown"
STATES = ("BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV", "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH")
CHURCH_RATE_LOW_STATES = ("BW", "BY")
# Vorgabe je Asset-Typ aus der gewaehlten Klasse (Festlegung 13.11.2026): Klassifikation, Topf (wie classification-definitions.csv des
# Moduls v2) und Teilfreistellung in Prozent. "Sonstiges" bekommt keine Vorgabe - die Einordnung ist dort offen.
TYPE_DEFAULTS: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "equity_etf": (("equity", "de_equity_share", "capital_equity", "0"), ("etf", "de_fund", "capital_general", "30")),
    "fund": (("fund", "de_fund", "capital_general", "30"),),
    "bond": (("bond", "de_capital_instrument", "capital_general", "0"),),
    "derivative": (("derivative", "de_capital_instrument", "capital_general", "0"),),
    "crypto": (("crypto", "de_private_disposal_asset", "private_disposal", "0"),),
    "commodity": (("commodity", "de_private_disposal_asset", "private_disposal", "0"),),
    "other": (),
}
# Mit dem Baustein „Cash“ (rc.415): Zinsen der Cash-Konten sind Kapitalertraege. „Cash“ ist keine Klasse, sondern ein Baustein - ohne diese
# Vorgabe blieben die Zinsen im Abschluss ohne Einordnung blockiert (tax_classification_required), gefunden am Demo mit Tagesgeld.
CASH_TYPE_DEFAULT = ("cash", "de_cash_interest", "capital_general", "0")
RATE_PATTERN = re.compile(r"^(?:0|[1-9][0-9]?)(?:[.,][0-9]{1,2})?$|^100$")
QUESTIONS: tuple[dict[str, Any], ...] = (
    {"key": "portfolio_name", "kind": "text", "default": "Mein Portfolio", "topic": "portfolio"},
    {"key": "base_currency", "kind": "single", "choices": list(CURRENCIES), "default": "EUR", "topic": "portfolio"},
    {"key": "holdings", "kind": "multi", "choices": list(HOLDINGS), "default": LATER, "topic": "scope"},
    {"key": "bookings", "kind": "multi", "choices": list(BOOKINGS), "fixed": list(BOOKINGS_FIXED), "default": LATER, "topic": "scope"},
    # Die Auswahl (mitgelieferte Leser) setzt questions_v1 aus den Plugins; gefragt nur mit dem Baustein Belege.
    {"key": "institutes", "kind": "multi", "choices": [], "default": LATER, "topic": "documents", "when": "documents"},
    {"key": "purposes", "kind": "multi", "choices": list(PURPOSES), "default": LATER, "topic": "scope"},
    {"key": "prices", "kind": "single", "choices": [PROVIDER, "none"], "default": PROVIDER, "topic": "prices", "when": "market_data"},
    {"key": "schedule", "kind": "single", "choices": list(SCHEDULES), "default": "manual", "topic": "prices", "when": "provider"},
    {"key": "tax_rate", "kind": "rate", "default": UNKNOWN, "topic": "tax", "when": "tax_report"},
    {"key": "church", "kind": "single", "choices": ["no", "yes"], "default": "no", "topic": "tax", "when": "tax_report", "states": list(STATES)},
    {"key": "protection", "kind": "single", "choices": ["yes", "no"], "default": "no", "topic": "protection"},
    # Update-Suche (#562, 0.3.3, Festlegung 25.11.2026): ohne Vorauswahl - die Vorgabe "later" ist keine der Antworten.
    {"key": "updates", "kind": "single", "choices": ["daily", "manual"], "default": LATER, "topic": "updates"},
)
QUESTION_KEYS = tuple(item["key"] for item in QUESTIONS)
# Zusatzangaben zu einer Antwort: Kenntnisnahme der Bedingungen des Anbieters, Zustimmung zum Zeitplan, Schluesselbund, Bundesland,
# Belegordner zu den Instituten.
EXTRA_KEYS = ("prices_terms", "schedule_consent", "protection_keyring", "church_state", "intake_folder")
POSITIONS = ("welcome", *QUESTION_KEYS, "summary")
# Nach dem Uebernehmen eines Backups im Dialog (#559, rc.410): Der Datenbestand ist schon da, offen sind nur Zeitplan und Passwortschutz.
# Der Entwurf an dieser Stelle laesst den Dialog nach einem Neuladen oder Neustart genau dort weitermachen; in der Reihenfolge der
# Fragen kommt sie nicht vor.
RESTORE_FOLLOWUP = "restore_followup"
DRAFT_POSITIONS = (*POSITIONS, RESTORE_FOLLOWUP)
FORBIDDEN_KEY = re.compile(r"pass|secret|recovery|token", re.IGNORECASE)


class DesktopSetupV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "desktop_setup_state_invalid"


def _abort(code: str) -> None:
    raise DesktopSetupV1Error(code)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _home(home: str | Path) -> Path:
    path = Path(home).expanduser()
    if not path.is_absolute() or not path.is_dir() or path.is_symlink():
        _abort("desktop_setup_input_invalid")
    return path.resolve()


def _write(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".partial")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def _read(path: Path, contract: str) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _abort("desktop_setup_state_invalid")
    if not isinstance(value, dict) or value.get("contract_version") != contract:
        _abort("desktop_setup_state_invalid")
    return value


_INSTITUTIONS: list[dict[str, str]] | None = None


def institutions_v1() -> list[dict[str, str]]:
    """Die mitgelieferten Leser je Institut, nach Namen (#572): Kennung des Plugins und Name des Instituts. Installierte Plugins gehoeren
    nicht dazu - beim ersten Start gibt es keine, und angeboten wird nur, was Portelyra mitbringt."""
    global _INSTITUTIONS
    if _INSTITUTIONS is None:
        from migrations.reference import statement_reader_plugins_v1 as reader_plugins
        names: dict[str, str] = {}
        for spec in reader_plugins.reader_specs_v1():
            if spec.origin == "shipped":
                names.setdefault(spec.plugin_id, spec.institution or spec.plugin_id)
        _INSTITUTIONS = [{"plugin_id": key, "label": label} for key, label in sorted(names.items(), key=lambda pair: (pair[1].lower(), pair[0]))]
    return [dict(item) for item in _INSTITUTIONS]


def questions_v1() -> dict[str, Any]:
    """Die Fragen in ihrer Reihenfolge, mit Auswahlwerten und Vorgaben; die Texte liefert die Oberflaeche. Zum Kursanbieter dieselben
    Hinweise wie beim Aktivieren in der Karte (Adressen, Kosten, Bedingungen), zum Zeitplan die Uhrzeiten, zu den Instituten die
    mitgelieferten Leser."""
    from migrations.reference.price_provider_admin_v1 import activation_notes_v1
    questions = [dict(item) for item in QUESTIONS]
    for item in questions:
        if item["key"] == "prices":
            item["provider"] = activation_notes_v1(PROVIDER)
        elif item["key"] == "schedule":
            item["times"] = {key: list(value) for key, value in SCHEDULES.items()}
        elif item["key"] == "institutes":
            item["institutions"] = institutions_v1()
            item["choices"] = [row["plugin_id"] for row in item["institutions"]]
    return {"contract_version": CONTRACT, "questions": questions, "positions": list(POSITIONS), "later": LATER}


def _no_secret_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or FORBIDDEN_KEY.search(key):
                _abort("desktop_setup_input_invalid")
            _no_secret_keys(item)
    elif isinstance(value, list):
        for item in value:
            _no_secret_keys(item)


def _text(value: Any) -> str:
    if not isinstance(value, str):
        _abort("desktop_setup_input_invalid")
    text = " ".join(value.split())
    if not text or len(text) > NAME_MAX or any(ord(char) < 32 for char in text):
        _abort("desktop_setup_input_invalid")
    return text


def normalized_answers_v1(answers: Any) -> dict[str, Any]:
    """Antworten pruefen und vereinheitlichen. Fehlende Antworten bleiben weg (der Plan nimmt dann die Vorgabe); "later" ist bei den
    Auswahlfragen erlaubt, beim Namen und der Waehrung gilt die Vorgabe."""
    if not isinstance(answers, Mapping):
        _abort("desktop_setup_input_invalid")
    _no_secret_keys(answers)
    if not set(answers) <= set(QUESTION_KEYS) | set(EXTRA_KEYS):
        _abort("desktop_setup_input_invalid")
    result: dict[str, Any] = {}
    if "portfolio_name" in answers:
        result["portfolio_name"] = _text(answers["portfolio_name"])
    if "base_currency" in answers:
        if answers["base_currency"] not in CURRENCIES:
            _abort("desktop_setup_input_invalid")
        result["base_currency"] = answers["base_currency"]
    for key, allowed in (("holdings", HOLDINGS), ("bookings", tuple(BOOKINGS)), ("purposes", tuple(PURPOSES))):
        if key not in answers:
            continue
        value = answers[key]
        if value == LATER:
            result[key] = LATER
            continue
        if not isinstance(value, list) or not all(isinstance(item, str) and item in allowed for item in value) or len(set(value)) != len(value):
            _abort("desktop_setup_input_invalid")
        # Was gilt, ist mindestens eine Klasse oder Cash; nichts gewaehlt waere ein Portfolio ohne Inhalt.
        if key == "holdings" and not value:
            _abort("desktop_setup_input_invalid")
        # "Von Hand" laesst sich nicht abwaehlen (#583).
        if key == "bookings" and not set(BOOKINGS_FIXED) <= set(value):
            _abort("desktop_setup_input_invalid")
        result[key] = [item for item in allowed if item in value]
    # Kurse, Zeitplan, Passwortschutz (Ausbau b): eine Wahl, "later" heisst nichts einrichten. Wer Yahoo waehlt, hat die Bedingungen zur
    # Kenntnis genommen; wer einen Zeitplan waehlt, hat zugestimmt (wie die Karten). Ohne diese Angabe gilt die Antwort nicht.
    for key, choices in (("prices", (PROVIDER, "none")), ("schedule", tuple(SCHEDULES)), ("protection", ("yes", "no")),
                         ("updates", ("daily", "manual"))):
        if key in answers:
            if answers[key] != LATER and answers[key] not in choices:
                _abort("desktop_setup_input_invalid")
            result[key] = answers[key]
    for key in ("prices_terms", "schedule_consent", "protection_keyring"):
        if key in answers:
            if not isinstance(answers[key], bool):
                _abort("desktop_setup_input_invalid")
            result[key] = answers[key]
    # Institute (#572): mitgelieferte Leser, keiner doppelt; "keines" ist eine Antwort. Der Belegordner gehoert zu dieser Antwort und ist ein
    # absoluter Pfad - ob es ihn gibt und ob er ausserhalb des Datenraums liegt, prueft folder_check_v1 an der Frage.
    if "institutes" in answers:
        value = answers["institutes"]
        if value == LATER:
            result["institutes"] = LATER
        else:
            allowed = [row["plugin_id"] for row in institutions_v1()]
            if not isinstance(value, list) or not all(isinstance(item, str) and item in allowed for item in value) or len(set(value)) != len(value):
                _abort("desktop_setup_input_invalid")
            result["institutes"] = [item for item in allowed if item in value]
    if "intake_folder" in answers:
        folder = answers["intake_folder"]
        if not isinstance(folder, str) or not 1 <= len(folder) <= FOLDER_MAX or any(ord(char) < 32 for char in folder) \
                or not Path(folder).is_absolute() or not isinstance(result.get("institutes"), list):
            _abort("desktop_setup_input_invalid")
        result["intake_folder"] = folder
    # Steuer (Ausbau c): Satz in Prozent (Komma oder Punkt, hoechstens zwei Nachkommastellen) oder "weiss ich nicht"; Kirchensteuer mit Land.
    if "tax_rate" in answers:
        value = answers["tax_rate"]
        if value in (LATER, UNKNOWN):
            result["tax_rate"] = value
        elif isinstance(value, str) and RATE_PATTERN.fullmatch(value.strip()):
            number = value.strip().replace(",", ".")
            number = number.rstrip("0").rstrip(".") if "." in number else number
            if float(number) > 100:
                _abort("desktop_setup_input_invalid")
            result["tax_rate"] = number
        else:
            _abort("desktop_setup_input_invalid")
    if "church" in answers:
        if answers["church"] not in ("no", "yes", LATER):
            _abort("desktop_setup_input_invalid")
        result["church"] = answers["church"]
    if "church_state" in answers:
        if answers["church_state"] not in STATES:
            _abort("desktop_setup_input_invalid")
        result["church_state"] = answers["church_state"]
    if result.get("church") == "yes" and "church_state" not in result:
        _abort("desktop_setup_input_invalid")
    if result.get("prices") == PROVIDER and result.get("prices_terms") is not True:
        _abort("desktop_setup_input_invalid")
    if result.get("schedule") in ("daily", "twice") and result.get("schedule_consent") is not True:
        _abort("desktop_setup_input_invalid")
    return result


def applicable_v1(answers: Any) -> dict[str, Any]:
    """Welche Fragen gestellt werden: Institute nur mit dem Baustein Belege, Kurse nur mit dem Baustein Marktdaten, der Zeitplan nur mit
    einem Kursanbieter, Steuersatz und Kirchensteuer nur mit dem Steuerbericht."""
    chosen = normalized_answers_v1(answers)
    modules = configuration_v1(chosen)["modules"]
    market = modules["market_data"]
    provider = market and chosen.get("prices") == PROVIDER
    keys = [key for key in QUESTION_KEYS if (key != "institutes" or modules["documents"]) and (key != "prices" or market)
            and (key != "schedule" or provider) and (key not in ("tax_rate", "church") or modules["tax_report"])]
    return {"contract_version": CONTRACT, "questions": keys, "positions": ["welcome", *keys, "summary"]}


def draft_read_v1(home: str | Path) -> dict[str, Any] | None:
    value = _read(_home(home) / DRAFT_FILE, DRAFT_CONTRACT)
    if value is None:
        return None
    if value.get("position") not in DRAFT_POSITIONS:
        _abort("desktop_setup_state_invalid")
    answers = value.get("answers")
    # Entwurf aus 0.3.3 oder frueher (#583): Dort stand "documents" unter "Wofuer", seither ist es eine Antwort von "Wie buchen". Der
    # Entwurf wird umgeschrieben, nicht verworfen. Sonst endete schon die Abfrage, ob der Dialog erscheint, mit einem Fehler.
    if isinstance(answers, Mapping) and isinstance(answers.get("purposes"), list) and "documents" in answers["purposes"]:
        answers = {**answers, "purposes": [item for item in answers["purposes"] if item != "documents"]}
        answers.setdefault("bookings", [*BOOKINGS_FIXED, "documents"])
    try:
        answers = normalized_answers_v1(answers)
    except DesktopSetupV1Error:
        _abort("desktop_setup_state_invalid")
    return {"contract_version": DRAFT_CONTRACT, "answers": answers, "position": value["position"], "updated_at_utc": value.get("updated_at_utc")}


def draft_write_v1(home: str | Path, answers: Any, position: Any) -> dict[str, Any]:
    """Entwurf ohne Wirkung: nur Antworten und Stelle, 0600."""
    resolved = _home(home)
    if position not in DRAFT_POSITIONS:
        _abort("desktop_setup_input_invalid")
    value = {"contract_version": DRAFT_CONTRACT, "answers": normalized_answers_v1(answers), "position": position, "updated_at_utc": _now()}
    _write(resolved / DRAFT_FILE, value)
    return value


def state_read_v1(home: str | Path) -> dict[str, Any] | None:
    value = _read(_home(home) / STATE_FILE, STATE_CONTRACT)
    if value is not None and value.get("status") not in ("applied", "skipped"):
        _abort("desktop_setup_state_invalid")
    return value


def status_v1(home: str | Path, data_space_present: Any) -> dict[str, Any]:
    """Ob der Dialog beim Start erscheint. Erster Start (kein Datenraum) oder ein Entwurf, der auf Fortsetzung wartet; nie nach
    Uebernehmen oder Ueberspringen und nie an einem eingerichteten Home ohne Entwurf."""
    if not isinstance(data_space_present, bool):
        _abort("desktop_setup_input_invalid")
    resolved = _home(home)
    state = state_read_v1(resolved)
    draft = draft_read_v1(resolved)
    if state is not None:
        reason = None
    elif not data_space_present:
        reason = "first_start"
    elif draft is not None:
        reason = "resume"
    else:
        reason = None
    return {"contract_version": CONTRACT, "needed": reason is not None, "reason": reason, "state": None if state is None else state["status"],
            "draft_position": None if draft is None else draft["position"]}


def configuration_v1(answers: Mapping[str, Any]) -> dict[str, Any]:
    """Der Umfang (#542) aus den Antworten. "spaeter" bzw. keine Antwort heisst alles - wie bisher jedes Portfolio ohne Fassung;
    abgewaehlt wird nur, was die Antwort ausdruecklich auslaesst."""
    holdings = answers.get("holdings", LATER)
    purposes = answers.get("purposes", LATER)
    bookings = answers.get("bookings", LATER)
    classes = list(CLASSES) if holdings == LATER else [item for item in holdings if item != "cash"]
    cash = holdings == LATER or "cash" in holdings
    chosen = set(PURPOSES) if purposes == LATER else set(purposes)
    ways = set(BOOKINGS) if bookings == LATER else set(bookings)
    modules = {module: False for module in MODULES}
    modules["cash"] = cash
    for purpose, items in PURPOSES.items():
        for module in items:
            modules[module] = purpose in chosen
    for way, items in BOOKINGS.items():
        for module in items:
            modules[module] = way in ways
    # Festlegung 12.11.2026: Die Projektion ("Steuer bei Verkauf jetzt") nur mit Kursen - ohne sie rechnete sie mit dem Kaufkurs und
    # zeigte nichts. "Steuer" mit Belegen ist damit der Vorschlag "Krypto und Edelmetalle - Steuer" aus #542.
    modules["tax_projection"] = "tax" in chosen and "performance" in chosen
    return {"classes": classes, "modules": modules, "valuation_without_market": "manual"}


def _current(current: Any) -> dict[str, Any]:
    if not isinstance(current, Mapping) or set(current) != {"data_space", "portfolios", "protection"} or not isinstance(current["data_space"], bool) \
            or not isinstance(current["portfolios"], list) or not isinstance(current["protection"], bool):
        _abort("desktop_setup_input_invalid")
    portfolios = []
    for item in current["portfolios"]:
        if not isinstance(item, Mapping) or not isinstance(item.get("label"), str) or item.get("status") not in ("active", "archived"):
            _abort("desktop_setup_input_invalid")
        portfolios.append({"label": item["label"], "status": item["status"]})
    return {"data_space": current["data_space"], "portfolios": portfolios, "protection": current["protection"]}


def _fingerprint(steps: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(steps, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def church_rate_v1(state: str) -> str:
    return "8" if state in CHURCH_RATE_LOW_STATES else "9"


def tax_step_v1(chosen: Mapping[str, Any], configuration: Mapping[str, Any], this_year: int | None = None) -> dict[str, Any]:
    """Der Steuerschritt (Ausbau c): nur mit dem Steuerbericht. Regelmodul v2 fuer alle drei Projektionsarten ab 2016, Vorgabe je Asset-Typ
    fuer die gewaehlten Klassen ab 2016, persoenlicher Satz und Kirchensteuer je Jahr 2020 bis heute, die Vorgaben des ersten Abschlusses.
    "Spaeter" bei der Kirchensteuer heisst vorerst nein (der Abschluss braucht eine ausdrueckliche Angabe), beim Satz: keiner."""
    if not configuration["modules"]["tax_report"]:
        return {"key": "tax", "action": "none", "reason": "no_tax_report"}
    year = this_year or datetime.now(timezone.utc).year
    chosen_types = [row for key in configuration["classes"] for row in TYPE_DEFAULTS[key]]
    if configuration["modules"]["cash"]:
        chosen_types.append(CASH_TYPE_DEFAULT)
    defaults = [{"asset_type": asset_type, "classification_code": code, "tax_bucket": bucket, "partial_exemption_rate_decimal": rate,
                 "effective_from_year": TAX_FROM_YEAR} for asset_type, code, bucket, rate in chosen_types]
    rate = chosen.get("tax_rate", LATER)
    church = chosen.get("church", LATER)
    applicable = church == "yes"
    return {"key": "tax", "action": "set", "plugin_id": TAX_PLUGIN, "effective_from": TAX_FROM, "projection_modes": list(PROJECTION_MODES),
            "type_defaults": defaults, "unclassified_classes": [key for key in configuration["classes"] if not TYPE_DEFAULTS[key]],
            "years": list(range(TAX_YEARS_FROM, year + 1)),
            "personal_income_tax_rate": None if rate in (LATER, UNKNOWN) else rate,
            "rate_reason": "answer" if rate not in (LATER, UNKNOWN) else rate,
            "church_tax_applicable": "applicable" if applicable else "not_applicable",
            "church_tax_rate": church_rate_v1(chosen["church_state"]) if applicable else None,
            "church_state": chosen.get("church_state") if applicable else None,
            "church_reason": "later" if church == LATER else "answer"}


def documents_step_v1(chosen: Mapping[str, Any], configuration: Mapping[str, Any]) -> dict[str, Any]:
    """Institute und Belegordner (#572): nur mit dem Baustein Belege. Die Leser der gewaehlten Institute werden fuer das neue Portfolio
    aktiviert, der Belegordner festgelegt; "spaeter" richtet nichts ein (beides geht danach in Data)."""
    if not configuration["modules"]["documents"]:
        return {"key": "documents", "action": "none", "reason": "no_documents"}
    institutes = chosen.get("institutes", LATER)
    if institutes == LATER:
        return {"key": "documents", "action": "none", "reason": "later"}
    labels = {row["plugin_id"]: row["label"] for row in institutions_v1()}
    plugins = [{"plugin_id": key, "label": labels[key]} for key in institutes]
    folder = chosen.get("intake_folder")
    if not plugins and folder is None:
        return {"key": "documents", "action": "none", "reason": "answer"}
    return {"key": "documents", "action": "set", "plugins": plugins, "intake_folder": folder, "reason": "answer"}


def folder_check_v1(folder: Any, data_space_path: Any) -> dict[str, Any]:
    """Taugt der Ordner als Belegordner? Dieselbe Regel wie beim Festlegen im Eingang (statement_archive_v1): absolut, vorhanden, keine
    Verknuepfung, ausserhalb des Datenraums. Den Datenraum braucht es dafuer noch nicht, nur seinen Pfad."""
    from migrations.reference import statement_archive_v1 as archive
    if not isinstance(data_space_path, str) or not Path(data_space_path).is_absolute():
        _abort("desktop_setup_input_invalid")
    try:
        return {"folder": archive.intake_folder_checked_v1(data_space_path, folder)}
    except archive.StatementArchiveV1Error:
        _abort("desktop_setup_folder_invalid")
        raise


def closing_step_v1(tax: Mapping[str, Any]) -> dict[str, Any]:
    """Der erste Abschluss (Festlegungen 13.11.2026): immer, mit oder ohne Steuer. Mit dem Steuerbericht das Regelmodul v2 und die
    Kirchensteuer aus der Antwort, sonst "ohne Steuermodul" - ein Steuermodul laesst sich spaeter einrichten (Data -> Steuer und einmal
    im Run Center waehlen). Die bestaetigte Zusammenfassung gilt als Bestaetigung dieser Vorgaben."""
    with_tax = tax["action"] == "set"
    return {"key": "closing", "action": "record", "run_mode": "full", "fee_source": "derived_from_transactions",
            "tax_mode": "de_reference_v2" if with_tax else "disabled",
            "church_tax_applicable": tax["church_tax_applicable"] if with_tax else None,
            "church_tax_rate": tax["church_tax_rate"] if with_tax else None,
            "reason": "with_tax" if with_tax else "without_tax"}


def plan_v1(answers: Any, current: Any) -> dict[str, Any]:
    """Die Schritte, die "Uebernehmen" ausfuehrt, je mit Grund. Ein vorhandener Datenraum bleibt; ein aktives Portfolio gleichen Namens
    wird genutzt statt ein zweites anzulegen (so laeuft ein abgebrochenes Uebernehmen beim zweiten Mal zu Ende)."""
    chosen = normalized_answers_v1(answers)
    state = _current(current)
    name = chosen.get("portfolio_name", QUESTIONS[0]["default"])
    currency = chosen.get("base_currency", QUESTIONS[1]["default"])
    steps: list[dict[str, Any]] = []
    steps.append({"key": "data_space", "action": "keep" if state["data_space"] else "create"})
    existing = any(item["label"] == name and item["status"] == "active" for item in state["portfolios"])
    steps.append({"key": "portfolio", "action": "keep" if existing else "create", "display_name": name, "base_currency": currency,
                  "reason": "answer" if "portfolio_name" in chosen else "default"})
    configuration = configuration_v1(chosen)
    reasons = {}
    # Grund je Baustein aus der Frage, die ihn setzt: Cash unter "Was", Belege unter "Wie buchen", alle anderen unter "Wofuer".
    source_of = {"cash": "holdings", **{module: "bookings" for items in BOOKINGS.values() for module in items}}
    for module in MODULES:
        source = source_of.get(module, "purposes")
        reasons[module] = "later" if chosen.get(source, LATER) == LATER else "answer"
    if reasons["tax_projection"] == "answer" and "tax" in chosen["purposes"] and not configuration["modules"]["tax_projection"]:
        reasons["tax_projection"] = "without_prices"
    steps.append({"key": "scope", "action": "set", "configuration": configuration, "reasons": reasons,
                  "classes_reason": "later" if chosen.get("holdings", LATER) == LATER else "answer"})
    # Institute und Belegordner (#572) gleich nach dem Umfang: Die Aktivierung gilt dem eben angelegten Portfolio.
    steps.append(documents_step_v1(chosen, configuration))
    tax = tax_step_v1(chosen, configuration)
    steps.append(tax)
    steps.append(closing_step_v1(tax))
    # Kursanbieter und Zeitplan nur mit Marktdaten; ohne Antwort ("spaeter") wird nichts eingeschaltet - beides ruft ohne Zutun ab.
    market = configuration["modules"]["market_data"]
    prices = chosen.get("prices", LATER)
    if not market:
        steps.append({"key": "prices", "action": "none", "reason": "no_market_data"})
    elif prices == PROVIDER:
        steps.append({"key": "prices", "action": "activate", "provider_id": PROVIDER, "reason": "answer"})
    else:
        steps.append({"key": "prices", "action": "none", "reason": "later" if prices == LATER else "answer"})
    schedule = chosen.get("schedule", LATER)
    if not (market and prices == PROVIDER):
        steps.append({"key": "schedule", "action": "none", "reason": "no_provider"})
    elif schedule in ("daily", "twice"):
        steps.append({"key": "schedule", "action": "enable", "times": list(SCHEDULES[schedule]), "reason": "answer"})
    else:
        steps.append({"key": "schedule", "action": "none", "reason": "later" if schedule == LATER else "answer"})
    # Update-Suche (#562): nur die Antwort zaehlt; "spaeter" laesst sie offen, dann fragt die Karte in Data noch einmal. Sie liegt in den
    # Einstellungen der Installation (Programmordner), nicht im Datenbestand - deshalb vor dem Passwortschutz, der zuletzt kommt.
    updates = chosen.get("updates", LATER)
    if updates in ("daily", "manual"):
        steps.append({"key": "updates", "action": "set", "consent": updates == "daily", "reason": "answer"})
    else:
        steps.append({"key": "updates", "action": "none", "reason": "later"})
    # Passwortschutz zuletzt: Er kopiert den fertig eingerichteten Datenbestand in den verschluesselten Ordner. Nach dem ersten Backup
    # entfernt der Start den unverschluesselten Bestand (die Bestaetigung der Zusammenfassung gilt dafuer; bei einem frisch angelegten
    # Home steht darin nur, was der Dialog eben eingerichtet hat).
    protection = chosen.get("protection", LATER)
    if state["protection"]:
        steps.append({"key": "protection", "action": "keep", "reason": "present"})
    elif protection == "yes":
        steps.append({"key": "protection", "action": "enable", "keyring": chosen.get("protection_keyring", True) is True,
                      "remove_plaintext": True, "reason": "answer"})
    else:
        steps.append({"key": "protection", "action": "none", "reason": "later" if protection == LATER else "answer"})
    return {"contract_version": PLAN_CONTRACT, "answers": chosen, "steps": steps, "plan_fingerprint": _fingerprint(steps)}


def confirm_v1(answers: Any, current: Any, plan_fingerprint: Any, confirmed: Any) -> dict[str, Any]:
    """Die Bestaetigung gilt genau dem gezeigten Plan: neu gerechnet aus Antworten und Stand, Abdruck gleich, Haekchen gesetzt."""
    if confirmed is not True:
        _abort("desktop_setup_confirmation_required")
    plan = plan_v1(answers, current)
    if not isinstance(plan_fingerprint, str) or plan_fingerprint != plan["plan_fingerprint"]:
        _abort("desktop_setup_plan_stale")
    return plan


def mark_v1(home: str | Path, status: Any, plan_fingerprint: Any = None, results: Any = None) -> dict[str, Any]:
    """Uebernommen (mit Abdruck und Ergebnis je Schritt; der Entwurf geht weg) oder uebersprungen (der Entwurf bleibt fuer spaeter)."""
    resolved = _home(home)
    if status not in ("applied", "skipped"):
        _abort("desktop_setup_input_invalid")
    if status == "applied" and (not isinstance(plan_fingerprint, str) or not re.fullmatch(r"[0-9a-f]{64}", plan_fingerprint)
                                or not isinstance(results, list)):
        _abort("desktop_setup_input_invalid")
    if results is not None:
        if not isinstance(results, list) or not all(isinstance(item, Mapping) and set(item) <= {"key", "status", "code"} and isinstance(item.get("key"), str)
                   and isinstance(item.get("status"), str) for item in results):
            _abort("desktop_setup_input_invalid")
    value = {"contract_version": STATE_CONTRACT, "status": status, "at_utc": _now(), "plan_fingerprint": plan_fingerprint,
             "results": [dict(item) for item in results] if isinstance(results, list) else None}
    _write(resolved / STATE_FILE, value)
    if status == "applied":
        (resolved / DRAFT_FILE).unlink(missing_ok=True)
    return value


__all__ = [
    "CONTRACT", "DRAFT_FILE", "DRAFT_POSITIONS", "FAILURE_CODES", "LATER", "QUESTIONS", "RESTORE_FOLLOWUP", "SCHEDULES", "STATE_FILE", "TAX_PLUGIN",
    "TYPE_DEFAULTS", "CASH_TYPE_DEFAULT", "DesktopSetupV1Error",
    "applicable_v1", "church_rate_v1", "closing_step_v1", "configuration_v1", "confirm_v1", "documents_step_v1", "folder_check_v1",
    "institutions_v1", "tax_step_v1",
    "draft_read_v1", "draft_write_v1", "mark_v1", "normalized_answers_v1", "plan_v1", "questions_v1", "state_read_v1", "status_v1",
]
