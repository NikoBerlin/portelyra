"""Wertpapier-Belege der Institute (#446): Kaeufe, Verkaeufe und Dividenden aus PDF- oder Text-Belegen.

Festlegung (14./15.10.2026): Wie bei den Rewards soll man einen Ordner oder beliebig viele Dateien uebergeben,
einen Zuordnungsvorschlag bekommen und die Transaktionen damit fuellen. Buchungen kommen kuenftig nur noch aus den
Belegen, die Betraege 1:1. Der Importer bucht Kaeufe, Verkaeufe und Dividenden; seltene Ereignisse wie
Depotuebertraege oder Stueckdividenden bleiben manuell. Splitmitteilungen (ING) werden seit rc.372 als Kapitalmassnahme
erkannt (#451): uebernehmbar in den Split-Speicher, split-bereinigt gebuchte Vorgaenge davor auf die Stueckzahl des Belegs.

Die Bauform folgt dem Cash-Auszugsimport (#184): eingebaute reine Leser je Institut, ausgewaehlt aus einer Registry.
Jede Datei ergibt genau ein Ergebnis - einen Vorgang oder einen benannten Grund; nichts faellt stillschweigend weg.
Die Pruefung gegen den Bestand erkennt Gebuchtes und meldet Abweichungen, ohne sie zu aendern. Neue Vorgaenge werden
als Zeilen des Aktivitaeten-CSV-Imports ausgegeben, mit fertig zugeordnetem Konto und Asset; Vorschau, Bestaetigung
und Buchen laufen ueber dessen gepruefte Befehle. Kein Netzzugriff, kein Providerzugriff, kein kanonischer Write;
die Quelldateien bleiben unveraendert.

Regeln der Leser:

- Scalable kennt drei Aussteller: Baader Bank fuer Scalable (fruehere Abrechnungen), Scalable Capital GmbH und Scalable Capital
  Bank GmbH. Bei Baader steht die Ordergebuehr nicht auf der Abrechnung, sondern getrennt auf dem Kontoauszug; eine
  dort gebuchte Gebuehr gilt deshalb nicht als Abweichung.
- Kurse kommen mit allen Stellen aus dem Beleg; gerundete Kurse fuehren sonst zu Abweichungen.
- Gleichzeitige Teilausfuehrungen mit gleichem Kurs entsprechen oft einer Buchung und werden gemeinsam erkannt.
- Belege vor einem Split koennen split-bereinigt gebucht sein: ein eigener Hinweis, keine Abweichung.
- Fremdwaehrungs-Dividenden: Brutto in EUR = Brutto in Fremdwaehrung / Devisenkurs, auf zwei Stellen.
- Dividenden werden brutto gebucht; Quellensteuer und Abgeltungsteuer gehoeren in die Steuerangaben.

Devisen (#449, rc.270): Ein eigener Leser bucht die Fremdwaehrungskonten von Smartbroker+ als Asset der Klasse "Devisen" -
Devisenbelege als Kauf und Verkauf der Waehrung, Dividendengutschriften in Fremdwaehrung als Zugang aus Ertrag; die
Perioden-Kontoauszuege pruefen als Saldo-Anker, dass jede Kontobewegung belegt ist.

Vorabpauschalen (#460, #471, rc.279; Scalable seit rc.352): Belege mit Betrag (ING, Scalable) werden je Fonds, Konto und Berechnungsjahr gegen den
Vorabpauschalen-Speicher geprueft; Fehlendes laesst sich nach Bestaetigung uebernehmen, Abweichungen werden nur gemeldet
und ersetzt erst auf ausdruecklichen Wunsch. Trade Republic nennt im Export nur die einbehaltene Steuer: Daraus folgt
eine Untergrenze und eine Warnung, nie ein gebuchter Betrag. Teilausfuehrungen bei Trade Republic werden getrennt gebucht,
in der Reihenfolge, in der die Bank sie beim Verkauf verbraucht.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
import csv
from datetime import datetime, timedelta
import functools
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from migrations.reference import crypto_statement_import_v1 as crypto
from migrations.reference import statement_reader_plugins_v1 as reader_plugins
from migrations.reference import generic_statement_import_v1 as generic
from migrations.reference.advance_lump_sum_v1 import AdvanceLumpSumV1Error, read_advance_lump_sums_v1, record_advance_lump_sums_v1
from migrations.reference.asset_activity_csv_import_v1 import FORMAT_VERSION, HEADERS, _source_keys, asset_activity_csv_event_ref_v1
from migrations.reference.asset_activity_reference_v1 import (
    TOKEN, AssetActivityReferenceV1Error, advance_lump_sum_provenance_key_v1, read_activity_references_v1, record_activity_references_v1,
    record_reader_provenance_intents_v1, record_reader_provenance_v1, reconcile_reader_provenance_v1,
)
from migrations.reference.desktop_product_asset_activity_v1 import (
    DesktopProductAssetActivityContextV1, read_desktop_product_asset_activity_binding_v1,
    read_desktop_product_per_asset_catalog_v1,
)

VERSION = 1
MAX_BYTES = 20 * 1024 * 1024
MAX_DOCUMENTS = 2000
TIME_ZONE = "Europe/Berlin"
CENT = Decimal("0.01")
SECOND_PASS_DAYS = 60
FAILURE_CODES = frozenset({
    "securities_statement_adapter_unknown", "securities_statement_source_invalid", "securities_statement_pdf_tool_missing",
    "securities_statement_account_invalid", "securities_statement_context_invalid", "securities_statement_review_invalid",
    "securities_statement_confirmation_invalid", "securities_statement_stock_split_blocked", "securities_statement_scope_choice_required",
})
# Benannte Gruende, warum ein Beleg kein Vorgang wird. Die Data-App zeigt sie im Wortlaut.
REASONS = {
    "custody_change": "Bestandsveränderung (Übertrag, Ein-/Auslieferung, Spin-off, Split) – bitte manuell buchen",
    "advance_lump_sum": "Vorabpauschale – dieser Leser übernimmt sie nicht; bitte in Daten → „4. Steuer“ je Fonds und Konto eintragen",
    "advance_lump_sum_inconsistent": "Vorabpauschale: Gesamtbetrag passt nicht zu Stück × Wert je Stück – bitte Beleg prüfen",
    "tax_document": "Steuerunterlage oder Steuerneuberechnung – gehört in die Steuerangaben",
    "accumulating_income": "Ertrag ohne Auszahlung (thesaurierend) – gehört in die Steuerangaben",
    "not_eur": "Kurs oder Kurswert nicht in EUR – bitte manuell buchen",
    "information": "Depotauszug oder Information – kein Buchungsbeleg",
    "overview": "Sammelübersicht mehrerer Vorgänge – bitte die Einzelbelege verwenden",
    "unknown_document": "Belegart nicht erkannt",
    "reader_inactive": "Leser in diesem Portfolio nicht aktiv – im Reiter „Leser“ unter „Aktivierung je Portfolio“ aktivieren",
    "incomplete": "Pflichtangaben fehlen im Beleg",
    "unreadable": "Kein lesbarer Text in der Datei",
    "too_large": "Datei größer als 20 MB – kein Einzelbeleg",
    "unsupported_type": "Dateityp wird nicht gelesen – nur PDF-Belege (oder deren Text als .txt) und CSV-Exporte",
    "wrong_institution": "Beleg eines anderen Instituts",
    "duplicate": "Dieselbe Abrechnung liegt doppelt vor",
    "order_cancelled": "Order storniert oder nicht ausgeführt",
    "preconfirmed": "Vorläufig bestätigt – wird gebucht, sobald der Export sie als CONFIRMED führt",
    "fx_trade": "Devisengeschäft – liest der Devisen-Leser des Instituts (Buchungsart Devisen)",
    "fx_statement": "Fremdwährungs-Kontoauszug – Saldo-Anker: prüft, dass jede Kontobewegung belegt ist",
    "fx_eur_credit": "Gutschrift auf dem EUR-Verrechnungskonto – liest der Wertpapier-Leser",
    "fx_not_fx": "Kein Devisenbeleg – Wertpapierbelege liest der Wertpapier-Leser",
    "fx_balance_mismatch": "Kontoauszug geht nicht auf (Anfangssaldo + Bewegungen ≠ Endsaldo) – bitte Auszug prüfen",
    "fx_line_without_document": "Auszugszeile ohne Beleg (Devisenbeleg oder Dividendenabrechnung fehlt) – bitte Beleg ergänzen",
    "fx_balance_gap": "Saldenkette unterbrochen – zwischen diesem und dem vorigen Kontoauszug fehlt einer",
    "dividend_reversed": "Dividende mit Rückbuchung am selben Tag – hebt sich auf",
    "ipo": "Zeichnung (IPO) – bitte als Kauf zum Zuteilungstag buchen",
    "cash_movement": "Kontobewegung – gehört zum Cash-Auszug",
    "export_without_bookings": "Export ohne buchbare Zeile – Gründe je Zeile in der Liste",
    "execution_evidence": "Ausführungsnachweis (etwa eine Transaktionshistorie) – bucht selbst nichts, belegt den genauen Euro-Betrag jeder Order",
    **crypto.REASONS,
    **generic.REASONS,
}
STATUS_LABELS = {
    "new": "neu – wird gebucht",
    "booked": "schon gebucht",
    "booked_combined": "schon gebucht (Teilausführungen gemeinsam)",
    "booked_differs": "gebucht, weicht ab",
    "split_adjusted": "split-bereinigt gebucht",
    "asset_missing": "Wertpapier fehlt im Katalog",
    "depot_unassigned": "Depot keinem Konto zugeordnet",
    "open": "offen – nicht automatisch buchbar",
    "out_of_window": "außerhalb des Zeitraums – nicht betrachtet",
    "out_of_scope": "Klasse nicht gewählt – bitte entscheiden",
    "skipped_scope": "übersprungen – Klasse nicht gewählt",
}
# Splitmitteilungen (#451, rc.372): eigene Zeilen; uebernommen wird in den Split-Speicher, nicht in den Bestand.
STOCK_SPLIT_STATUS_LABELS = {
    "new": "neu – wird übernommen",
    "recorded": "schon gespeichert",
    "differs": "anders gespeichert – bitte unter Stammdaten → Kapitalmaßnahmen prüfen",
    "quantity_mismatch": "Zusatzstücke passen nicht zum Bestand – bitte prüfen",
    "asset_missing": "Wertpapier fehlt im Katalog",
    "depot_unassigned": "Depot keinem Konto zugeordnet",
}
# Ein gespeicherter Split desselben Papiers in diesem Abstand gilt als derselbe Vorgang: nicht ein zweites Mal uebernehmen.
STOCK_SPLIT_NEAR_DAYS = 31
CRYPTO_STATUS_LABELS = {**STATUS_LABELS, "asset_missing": "Coin fehlt im Katalog", "depot_unassigned": "Wallet keinem Konto zugeordnet"}
# Vorabpauschalen aus Belegen (#460, #471): eigene Zeilen, eigener Speicher, eigene Bestaetigung.
ADVANCE_LUMP_SUM_STATUS_LABELS = {
    "new": "neu – wird übernommen",
    "booked": "schon eingetragen",
    "differs": "eingetragen, weicht vom Beleg ab",
    "conflict": "Belege desselben Jahres widersprechen sich",
    "amount_missing": "Betrag fehlt im Export",
    "tax_mismatch": "eingetragen, passt nicht zur einbehaltenen Steuer",
    "not_a_fund": "im Katalog kein Fonds",
    "asset_missing": "Fonds fehlt im Katalog",
    "depot_unassigned": "Depot keinem Konto zugeordnet",
    "out_of_window": "außerhalb des Zeitraums – nicht betrachtet",
}
# Betrachteter Zeitraum (#462): Was ausserhalb liegt, wird gelesen und gezaehlt, aber weder als neu noch als offen oder
# abweichend vorgeschlagen. Gebuchtes bleibt, wie es ist; die Duplikaterkennung prueft weiter gegen den ganzen Bestand.
WINDOW_MODES = ("since_confirmed", "chosen", "all")
WINDOW_HIDDEN = frozenset({"new", "open", "booked_differs", "asset_missing", "depot_unassigned"})
ADVANCE_WINDOW_HIDDEN = frozenset({"new", "differs", "conflict", "amount_missing", "tax_mismatch", "not_a_fund", "asset_missing", "depot_unassigned"})
# Hoechster Steuersatz auf Kapitalertraege samt Soli und 9 % Kirchensteuer: 27,99 %. Die einbehaltene Steuer kann deshalb nie
# mehr als 28 % der Vorabpauschale sein (Teilfreistellung und Freistellungsauftrag mindern nur) - daraus die Untergrenze.
ADVANCE_LUMP_SUM_MAX_TAX_RATE = Decimal("0.28")
SEPARATE_EXECUTIONS_NOTE = "gemeinsam gebucht – die Bank verbraucht die Teilausführungen getrennt, Aufteilung empfohlen"
FX_UNCHECKED_NOTE = "ohne Zeile im Kontoauszug"
FX_ORDER_NOTE = "am selben Tag nachgeordnet (Beleg ohne Uhrzeit; Zugänge zuerst)"


class SecuritiesStatementImportV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise SecuritiesStatementImportV1Error(code) from None


def securities_statement_import_v1_error_codes() -> tuple[str, ...]:
    return tuple(sorted(FAILURE_CODES))


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _plain(value: Decimal) -> str:
    """Exakte Dezimalzahl ohne Exponent und ohne ueberfluessige Nullen (Format des CSV-Imports)."""
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def _text(source: bytes, file_name: str) -> str:
    """Nur lokale Textgewinnung: poppler pdftotext, kein Netz; die Originaldatei bleibt unveraendert."""
    if len(source) > MAX_BYTES:
        return ""
    if not file_name.lower().endswith(".pdf"):
        return source.decode("utf-8", errors="replace")
    return _pdf_text(source)


@functools.lru_cache(maxsize=2048)
def _pdf_text(source: bytes) -> str:
    with tempfile.TemporaryDirectory(prefix="securities-statement-pdf-") as temporary:
        path = Path(temporary) / "statement.pdf"
        path.write_bytes(source)
        try:
            completed = subprocess.run(["pdftotext", "-layout", "-nopgbrk", str(path), "-"], capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            _abort("securities_statement_pdf_tool_missing")
        if completed.returncode != 0:
            return ""
        return completed.stdout.decode("utf-8", errors="replace")


def _candidate(kind: str, profile: str, **fields: Any) -> dict[str, Any]:
    value = {"status": "candidate", "kind": kind, "profile": profile, "isin": None, "security_name": None, "local_date": None,
             "local_time": None, "quantity": None, "unit_price": None, "gross_amount": None, "fee_amount": "0", "eligible_quantity": None,
             "order_ref": None, "depot_ref": None, "ex_date": None, "net_amount": None, "taxes_amount": None, "withholding_amount": None,
             "bank_gain": None, "fee_on_cash_statement": False, "currency": None, "valuta": None, "statement_checked": False}
    value.update(fields)
    return value


def _reason(code: str, **fields: Any) -> dict[str, Any]:
    return {"status": "not_importable", "reason_code": code, "reason": REASONS[code], **fields}


# --- Scalable: Baader Bank fuer Scalable, Scalable Capital GmbH, Scalable Capital Bank GmbH ---------------------------


# --- ING Direkt-Depot --------------------------------------------------------------------------------------------------


# --- Smartbroker+ (Baader Bank fuer Smartbroker): CSV-Export der Transaktionen, Dividendenabrechnungen als PDF -------------
# Ein Export ergibt viele Vorgaenge. Gebucht wird nur, was der Export als CONFIRMED fuehrt; vorlaeufige und stornierte
# Zeilen erscheinen gezaehlt mit Grund.


# --- Trade Republic: CSV-Export aller Transaktionen ----------------------------------------------------------------------
# Zeiten in UTC (in Europe/Berlin umgerechnet); amount ist bei Dividenden das Brutto in EUR, die Steuer steht getrennt.
# Jede Zeile ist ein Vorgang. Ein Kauf nach Betrag steht als zwei Zeilen (ganze Stuecke mit Ordergebuehr und gebuehrenfreier
# Bruchteil, gleiche Sekunde, gleicher Kurs); die Millisekunden zeigen die Reihenfolge. Trade Republic verbraucht die
# Teile beim Verkauf getrennt in dieser Reihenfolge - deshalb werden sie getrennt gebucht (#471). Eine schon gemeinsam
# gebuchte Ausfuehrung erkennt die Pruefung weiter als "Teilausfuehrungen gemeinsam".
# EARNINGS ist die Vorabpauschale; der Export nennt nur die einbehaltene Steuer, nicht den Betrag.


# --- Smartbroker+ Devisenkonten (Baader Bank fuer Smartbroker): Auszuege, Devisenbelege, Dividenden in Fremdwaehrung (#449) -
# Devisen sind Assets der Klasse "fx" auf einem Fremdwaehrungskonto (Kontoart other). Vorgaenge kommen aus den Belegen:
# Devisenbeleg = Kauf oder Verkauf der Waehrung (Kurs = EUR-Gegenwert / Fremdwaehrungsbetrag, Festlegung 16.10.2026),
# Dividendenabrechnung mit Gutschrift auf dem Fremdwaehrungskonto = Zugang aus Ertrag (EUR-Wert ueber den Umrechnungskurs
# des Belegs, auf den Cent). Die Perioden-Kontoauszuege sind Saldo-Anker: Jede Auszugszeile braucht ihren Beleg, jeder
# Auszug muss in sich aufgehen.

# Profile der Wertpapier- und Devisenleser (Anzeigename, Institutsnamen am Konto, Kontohinweis, Depotfamilie) stehen seit #486 im
# Manifest des Lesers ("profiles"); ein Devisenprofil ist eines, dessen Leser den Bereich fx hat.
_UNKNOWN_PROFILE: dict[str, Any] = {"label": "Depot", "institution_names": (), "account_hint": None, "domain": "securities"}


def _profile(profile: str) -> Mapping[str, Any]:
    return reader_plugins.securities_profiles_v1().get(profile) or {**_UNKNOWN_PROFILE, "depot_family": profile}


def _is_fx(profile: str) -> bool:
    return _profile(profile)["domain"] == "fx"


# Bezeichnungen, unter denen eine Waehrung im Katalog steht ("US-Dollar", "Schweizer Franken"); der ISO-Code zaehlt immer.
FX_NAMES = {"USD": ("dollar",), "CHF": ("franken",), "GBP": ("pfund",), "DKK": ("dänische krone",), "NOK": ("norwegische krone",),
            "SEK": ("schwedische krone",), "JPY": ("yen",), "CAD": ("kanadische",), "AUD": ("australische",), "HKD": ("hongkong",)}


# Die Leser der Institute liegen seit rc.374 als Plugins unter plugins/readers/ (#486) und laufen nur abgeschottet: Erkennung,
# Lesen und Nachbearbeitung je Institut. Im Kern bleiben die Texte der Gruende, die Pruefung jedes Ergebnisses und die Saldoprobe
# der Kontoauszuege (Festlegung 07.11.2026). Welche Leser es gibt, sagt allein die Leserliste; der Pruefstand je
# Leser (#450) steht seit #486 in seinem Manifest ("format_checked": Format geprueft mit Belegen bis, Stand der Pruefung). Aendert
# ein Institut sein Format, entsteht ein neuer Leser (..._v2) neben dem alten; aeltere Belege bleiben mit dem alten lesbar.
# Vorab gelesene Ergebnisse eines Stapels: ein abgeschotteter Aufruf je Leser statt je Beleg. Schluessel: Bereich, Leser, Abdruck
# des Textes, Dateiname.
_PREFETCHED: dict[tuple[str, str, str, str], dict[str, Any]] = {}


def _text_key(domain: str, reader_id: str, text: str, file_name: str) -> tuple[str, str, str, str]:
    return domain, reader_id, hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest(), file_name


def _plugin_outcome(result: Mapping[str, Any]) -> Any:
    if not result["ok"]:
        _abort(result["code"])
    return result["value"]


def _plugin_read_text(domain: str, reader_id: str, text: str, file_name: str) -> dict[str, Any]:
    result = _PREFETCHED.get(_text_key(domain, reader_id, text, file_name))
    try:
        if result is None:
            result = reader_plugins.run_text_reader_v1(reader_id, domain, [(text, file_name)])[0]
        return reader_plugins.validate_securities_result_v1(_plugin_outcome(result), REASONS)
    except reader_plugins.StatementReaderBlocked as error:
        _abort(error.code)


def _prefetch_text(domain: str, reader_id: str, items: Sequence[tuple[str, str]]) -> list[tuple[str, str, str, str]]:
    keys = [_text_key(domain, reader_id, text, name) for text, name in items]
    if not items:
        return []
    try:
        results = reader_plugins.run_text_reader_v1(reader_id, domain, list(items))
    except reader_plugins.StatementReaderBlocked as error:
        results = [{"ok": False, "code": error.code} for _ in items]
    _PREFETCHED.update(zip(keys, results))
    return keys


def _plugin_detect(domain: str, reader_id: str, text: str) -> bool:
    return _plugin_detect_many(domain, reader_id, [text])[0]


# Vorab erkannte Texte (Eingang, Ablage): Bereich, Leser, Abdruck des Textes -> erkannt.
_DETECTED: dict[tuple[str, str, str], bool] = {}


def _plugin_detect_many(domain: str, reader_id: str, texts: Sequence[str]) -> list[bool]:
    """Erst die Regeln des Manifests (Mindestbedingungen, im Kern), dann die Erkennung des Lesers - abgeschottet, ein Aufruf."""
    keys = [_text_key(domain, reader_id, text, "")[:3] for text in texts]
    found = [_DETECTED.get(key, False) for key in keys]
    passing = [index for index, text in enumerate(texts) if keys[index] not in _DETECTED
               and reader_plugins.detection_passes_v1(reader_id, reader_plugins.detection_texts_v1([text]), domain)]
    if passing:
        try:
            results = reader_plugins.run_detect_v1(reader_id, domain, [texts[index] for index in passing])
        except reader_plugins.StatementReaderBlocked as error:
            _abort(error.code)
        for index, result in zip(passing, results):
            found[index] = bool(_plugin_outcome(result))
    return found


def securities_prefetch_v1(sources: Sequence[tuple[bytes, str]], domains: Sequence[str]) -> list[tuple]:
    """Viele Dateien auf einmal (Eingang, Ablage-Vorschlag): je Leser-Plugin ein Aufruf fuer die Erkennung aller Texte und einer
    fuer das Lesen der erkannten. Gilt bis ``securities_prefetch_release_v1``; ein Fehler hier laesst die Einzelaufrufe entscheiden."""
    items = [(text, name) for source, name in sources if isinstance(source, bytes) and isinstance(name, str)
             and name.lower().endswith((".pdf", ".txt", ".csv")) and len(source) <= MAX_BYTES and (text := _text(source, name)).strip()]
    keys: list[tuple] = []
    for adapter in ADAPTERS.values():
        plugin = adapter.get("plugin")
        if not plugin or adapter["domain"] not in domains or len(items) < 2:
            continue
        try:
            found = _plugin_detect_many(plugin[0], plugin[1], [text for text, _name in items])
        except SecuritiesStatementImportV1Error:
            continue
        detected = []
        for (text, name), hit in zip(items, found):
            key = _text_key(plugin[0], plugin[1], text, "")[:3]
            _DETECTED[key] = hit; keys.append(key)
            if hit:
                detected.append((text, name))
        keys += _prefetch_text(plugin[0], plugin[1], detected) if detected else []
    return keys


def securities_prefetch_release_v1(keys: Sequence[tuple]) -> None:
    for key in keys:
        (_DETECTED if len(key) == 3 else _PREFETCHED).pop(key, None)


def _plugin_finish(domain: str, reader_id: str, candidates: list[dict[str, Any]], statements: list[dict[str, Any]],
                   row_reasons: list[dict[str, Any]]) -> None:
    """Nachbearbeitung des Instituts ueber den Stapel. Es gilt nur die Ordnung am Tag (apply_finish_v1); Auszuege und Gruende
    bleiben die des Kerns."""
    if not candidates:
        return
    try:
        result = reader_plugins.run_finish_v1(reader_id, domain, {"candidates": candidates, "statements": statements, "row_reasons": row_reasons})
        reader_plugins.apply_finish_v1(candidates, _plugin_outcome(result))
    except reader_plugins.StatementReaderBlocked as error:
        _abort(error.code)


def _verify_statements(candidates: list[dict[str, Any]], statements: list[dict[str, Any]], row_reasons: list[dict[str, Any]]) -> None:
    """Saldo-Anker im Kern: Jeder Auszug geht in sich auf, die Auszuege schliessen je Waehrung aneinander an, und jede Auszugszeile
    hat ihren Beleg (Waehrung, Vorgangsart laut Leser, Betrag, Valuta) - erst dann gilt der Beleg als abgeglichen."""
    used: set[int] = set()
    def reason(statement: Mapping[str, Any], code: str, rows: int = 1) -> None:
        row_reasons.append({"file_name": statement["file_name"], "rows": rows, "reason_code": code, "reason": REASONS[code]})
    # Saldenkette je Waehrung: Endsaldo eines Auszugs = Anfangssaldo des naechsten, sonst fehlt dazwischen einer
    for currency in sorted({statement["currency"] for statement in statements}):
        chain = sorted((statement for statement in statements if statement["currency"] == currency), key=lambda statement: statement["end"][0] or "")
        for previous, following in zip(chain, chain[1:]):
            if previous["end"][1] != following["start"][1]:
                reason(following, "fx_balance_gap")
    for statement in statements:
        if statement["start"][1] + sum((line["amount"] for line in statement["lines"]), Decimal(0)) != statement["end"][1]:
            reason(statement, "fx_balance_mismatch")
        missing = 0
        for line in statement["lines"]:
            match = next((candidate for candidate in candidates if candidate["candidate_ordinal"] not in used and _is_fx(candidate["profile"])
                          and candidate["currency"] == statement["currency"] and candidate["kind"] in line["kinds"]
                          and Decimal(candidate["quantity"]) == abs(line["amount"]) and candidate["valuta"] == line["valuta"]), None)
            if match is None:
                missing += 1; continue
            used.add(match["candidate_ordinal"]); match["statement_checked"] = True
        if missing:
            reason(statement, "fx_line_without_document", missing)


def _guarded(function):
    """Fehler der Abschottung (Leser-Plugins im Krypto-Teil, rc.376) kommen als Code des Wertpapier-Imports an."""
    @functools.wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except reader_plugins.StatementReaderBlocked as error:
            _abort(error.code)
    return call


def _plugin_adapter(domain: str, reader_id: str) -> dict[str, Any] | None:
    spec = reader_plugins.reader_spec_v1(reader_id, domain)
    if spec is None:
        return None
    return {"label": spec.label, "institution": spec.institution, "version": int(reader_id.rsplit("_v", 1)[1]), "domain": domain,
            "validated": dict(spec.format_checked) if spec.format_checked else None, "formats": spec.tested_formats, "not_booked": " ".join(spec.known_limits),
            "parse": functools.partial(_plugin_read_text, domain, reader_id), "detect": functools.partial(_plugin_detect, domain, reader_id),
            "finish": functools.partial(_plugin_finish, domain, reader_id), "with_name": True, "plugin": (domain, reader_id)}


ADAPTERS: dict[str, dict[str, Any]] = {spec.reader_id: adapter for spec in sorted(reader_plugins.reader_specs_v1(),
                                                                                  key=lambda item: (item.domain != "securities", item.label.casefold(), item.reader_id))
                                       if spec.origin == "shipped" and spec.domain in ("securities", "fx")
                                       and (adapter := _plugin_adapter(spec.domain, spec.reader_id)) is not None}
# Formatbeschreibung des Krypto-Lesers nach den Namen der Boersen (aus den Manifesten der Krypto-Leser).
_CRYPTO_FORMATS_TAIL = ", gern alle zugleich: Käufe und Verkäufe gegen EUR mit den Beträgen des Exports, Transfers zwischen eigenen Konten (Abgang und Eingang gepaart über Hash oder Menge; gebucht wird die angekommene Menge, die Netzwerkgebühr trägt das Quellkonto) und Umschichtungen innerhalb einer Börse (etwa zwischen Spot, Earn und Staking)."
ADAPTERS.update({
    "crypto_exports_v1": {
        "label": "Krypto-Börsen und Wallets (CSV-Exporte)", "version": 1, "domain": "crypto",
        "not_booked": "Rewards (Reward-Import), EUR-Ein- und Auszahlungen, stornierte Aufträge; offen mit Grund: Abgang oder Eingang ohne Gegenstück, Tausch Coin gegen Coin, Aufträge ohne Ausführungszeit (ältere Exporte nennen nur die Anlage), noch offene Aufträge, Gebühren ohne Transfer.",
        "parse": _guarded(crypto.parse_crypto_export_v1), "detect": _guarded(crypto.detect_crypto_export_v1), "finish": _guarded(crypto.finish_crypto_v1), "with_name": True,
        "with_evidence": True},
    # Experimentell, ohne Gewaehr (#514): ohne Pruefstand; wird nie von selbst gewaehlt. Die Zuordnung schlaegt er aus typischen
    # Ausdruecken vor; ein gespeichertes Profil je Format geht vor (options["profiles"]).
    "generic_securities_v1": {
        "label": "Experimentell: generischer Leser für CSV-Exporte (ohne Gewähr)", "institution": "beliebig", "version": 1, "validated": None,
        "formats": "CSV-Exporte mit Kopfzeile und je Zeile einem Vorgang mit ISIN: Kauf, Verkauf, Dividende in EUR. Spalten und Vorgänge werden aus typischen Ausdrücken (deutsch, englisch) vorgeschlagen und lassen sich zuordnen.",
        "not_booked": "Zeilen ohne ISIN oder nicht in EUR, Ein- und Auslieferungen, Geldbewegungen, Rewards; unklare Zeilen bleiben mit Grund offen.",
        "parse": generic.parse_generic_securities_v1, "detect": generic.never_detect_v1, "with_name": True, "with_options": True, "experimental": True},
    "generic_crypto_v1": {
        "label": "Experimentell: generischer Leser für Krypto-CSV (ohne Gewähr)", "institution": "beliebig", "version": 1, "domain": "crypto", "validated": None,
        "formats": "CSV-Exporte mit Kopfzeile und je Zeile einem Vorgang mit Coin-Kürzel: Kauf und Verkauf gegen EUR, Ein- und Ausgänge (Transfers paart der Krypto-Leser). Zuordnung wie beim Wertpapier-Leser.",
        "not_booked": "Tausch Coin gegen Coin, Rewards, Euro-Bewegungen; unklare Zeilen bleiben mit Grund offen.",
        "parse": generic.parse_generic_crypto_v1, "detect": generic.never_detect_v1, "finish": _guarded(crypto.finish_crypto_v1), "with_name": True,
        "with_options": True, "experimental": True},
})


# Installierte Plugins (rc.381, #486): Wertpapier- und Devisenleser aus dem Datenraum kommen nach den mitgelieferten dazu, sobald der
# Datenraum feststeht; entfernte fallen wieder heraus.
_INSTALLED_ADAPTERS: set[str] = set()


def _refresh_installed_adapters() -> None:
    for reader_id in list(_INSTALLED_ADAPTERS):
        ADAPTERS.pop(reader_id, None)
    _INSTALLED_ADAPTERS.clear()
    for spec in reader_plugins.reader_specs_v1():
        if spec.origin == "installed" and spec.domain in ("securities", "fx") and spec.reader_id not in ADAPTERS:
            adapter = _plugin_adapter(spec.domain, spec.reader_id)
            if adapter is not None:
                ADAPTERS[spec.reader_id] = adapter
                _INSTALLED_ADAPTERS.add(spec.reader_id)


def _refresh_crypto_adapter() -> None:
    """Institute, Pruefstand und Formate des Krypto-Lesers folgen den geladenen Krypto-Lesern (#486): Institute und Formate nach ihren
    Manifesten; der Pruefstand reicht bis zum fruehesten "geprueft bis" unter den Lesern mit Pruefstand."""
    specs = [spec for spec in reader_plugins.reader_specs_v1("crypto") if spec.source is not None]
    checked = [spec.format_checked for spec in specs if spec.format_checked]
    ADAPTERS["crypto_exports_v1"].update(
        institution=", ".join(sorted({spec.institution for spec in specs}, key=str.casefold)),
        validated={"through": min(item["through"] for item in checked), "checked_on": max(item["checked_on"] for item in checked)} if checked else None,
        formats="CSV-Exporte von " + crypto.crypto_format_labels_v1() + _CRYPTO_FORMATS_TAIL)


_refresh_crypto_adapter()
reader_plugins.register_registry_refresher_v1(_refresh_installed_adapters)
reader_plugins.register_registry_refresher_v1(_refresh_crypto_adapter)
for _adapter in ADAPTERS.values():
    _adapter.setdefault("domain", "securities")
ADAPTER_FIELDS = ("label", "institution", "version", "domain", "validated", "formats", "not_booked")
BEYOND_VALIDATION_NOTE = "jünger als der Prüfstand des Lesers"
COMBINED_NEW_NOTE = "mit gleichzeitiger Teilausführung als eine Buchung"
# Der Pruefstand waechst im Datenraum mit: Jeder Import, dessen Vorschau der Eigentuemer geprueft und vollstaendig gebucht
# hat, hebt das Datum auf den juengsten gebuchten Beleg. Nur die Data-App schreibt die Datei.
CONFIRMATION_AREA = "securities-statement-import-v1"
CONFIRMATION_FILE = "confirmations.json"
CONFIRMATION_VERSION = 1
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _confirmation_entry_valid(entry: Any) -> bool:
    return (isinstance(entry, Mapping) and set(entry) == {"through", "documents", "imports", "last_confirmed_at_utc"}
            and isinstance(entry["through"], str) and bool(_DAY.match(entry["through"]))
            and isinstance(entry["documents"], int) and entry["documents"] > 0 and isinstance(entry["imports"], int) and entry["imports"] > 0
            and isinstance(entry["last_confirmed_at_utc"], str) and bool(_UTC.match(entry["last_confirmed_at_utc"])))


def read_securities_statement_confirmations_v1(data_space_path: str | Path) -> dict[str, dict[str, Any]]:
    """Bestaetigte Pruefstaende je Leser: {adapter_id: {through, documents, imports, last_confirmed_at_utc}}."""
    path = Path(data_space_path) / CONFIRMATION_AREA / CONFIRMATION_FILE
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _abort("securities_statement_confirmation_invalid")
    if (not isinstance(value, Mapping) or value.get("securities_statement_confirmations_version") != CONFIRMATION_VERSION
            or not isinstance(value.get("adapters"), Mapping)
            or any(key not in ADAPTERS or not _confirmation_entry_valid(entry) for key, entry in value["adapters"].items())):
        _abort("securities_statement_confirmation_invalid")
    return {key: dict(entry) for key, entry in value["adapters"].items()}


def record_securities_statement_confirmation_v1(data_space_path: str | Path, trusted_review: Mapping[str, Any], created_event_count: int,
                                                confirmed_at_utc: str) -> dict[str, Any]:
    """Nach dem Buchen: hebt den Pruefstand des Lesers auf den juengsten gebuchten Beleg - nur wenn alle neuen Vorgaenge
    dieser Pruefung gebucht wurden. Ein Teilerfolg aendert nichts."""
    if not isinstance(trusted_review, Mapping) or not trusted_review.get("new_candidates") or trusted_review.get("adapter_id") not in ADAPTERS:
        _abort("securities_statement_review_invalid")
    body = {key: value for key, value in trusted_review.items() if key != "review_fingerprint"}
    if trusted_review.get("review_fingerprint") != _sha(body):
        _abort("securities_statement_review_invalid")
    if not isinstance(created_event_count, int) or isinstance(created_event_count, bool) or not isinstance(confirmed_at_utc, str) or not _UTC.match(confirmed_at_utc):
        _abort("securities_statement_confirmation_invalid")
    adapter_id = trusted_review["adapter_id"]; new = trusted_review["new_candidates"]
    current = read_securities_statement_confirmations_v1(data_space_path)
    if created_event_count != len(new):
        return {"recorded": False, "adapter_id": adapter_id, "confirmed": current.get(adapter_id)}
    previous = current.get(adapter_id)
    batch_through = max(candidate["local_date"] for candidate in new)
    entry = {"through": max(batch_through, previous["through"]) if previous else batch_through,
             "documents": (previous["documents"] if previous else 0) + len(new), "imports": (previous["imports"] if previous else 0) + 1,
             "last_confirmed_at_utc": confirmed_at_utc}
    current[adapter_id] = entry
    area = Path(data_space_path) / CONFIRMATION_AREA
    area.mkdir(mode=0o700, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=area, prefix=".confirmations-", suffix=".json", delete=False) as handle:
        json.dump({"securities_statement_confirmations_version": CONFIRMATION_VERSION, "adapters": current}, handle, sort_keys=True, ensure_ascii=False, indent=1)
        temporary = Path(handle.name)
    temporary.chmod(0o600)
    os.replace(temporary, area / CONFIRMATION_FILE)
    return {"recorded": True, "adapter_id": adapter_id, "confirmed": entry}


def _adapter_public(adapter_id: str) -> dict[str, Any]:
    return {"adapter_id": adapter_id, **{key: ADAPTERS[adapter_id][key] for key in ADAPTER_FIELDS}}


def list_securities_statement_adapters_v1() -> list[dict[str, Any]]:
    return [_adapter_public(key) for key in ADAPTERS]


@reader_plugins.within_reader_session
def detect_securities_statement_adapters_v1(sources: Sequence[tuple[bytes, str]], domain: str | Sequence[str] = "securities") -> list[dict[str, Any]]:
    """Je Adapter der Buchungsart (Wertpapiere, Krypto oder Devisen) die Zahl der Dateien, die er erkennt - die Data-App schlaegt
    den mit den meisten vor."""
    domains = {domain} if isinstance(domain, str) else set(domain)
    counts = {key: 0 for key, adapter in ADAPTERS.items() if adapter["domain"] in domains}
    texts = [_text(source, file_name) for source, file_name in sources if file_name.lower().endswith((".pdf", ".txt", ".csv"))]
    for key in counts:
        plugin = ADAPTERS[key].get("plugin")
        # Leser-Plugins pruefen alle Texte in einem abgeschotteten Aufruf (rc.374); die uebrigen Leser wie bisher je Text.
        found = _plugin_detect_many(plugin[0], plugin[1], texts) if plugin else [ADAPTERS[key]["detect"](text) for text in texts]
        counts[key] = sum(found)
    return [{"adapter_id": key, "label": ADAPTERS[key]["label"], "matching_documents": count} for key, count in counts.items() if count]


def _candidate_key(candidate: Mapping[str, Any]) -> str:
    """Identitaet einer Abrechnung: Order- bzw. Vorgangsnummer, sonst die wirtschaftlichen Angaben. Krypto-Zeilen tragen ihren Schluessel."""
    if candidate.get("row_key"):
        return candidate["row_key"]
    # Der Devisen-Zufluss traegt die Vorgangsnummer seiner Dividendenabrechnung erst seit #458; sein Schluessel bleibt der
    # wirtschaftliche, damit schon gebuchte Zufluesse ihren Zeilenschluessel behalten.
    if candidate.get("order_ref") and not (_is_fx(candidate["profile"]) and candidate["kind"] == "deposit"):
        return candidate["profile"] + ":" + candidate["order_ref"]
    return _sha([candidate["profile"], candidate["kind"], candidate["isin"], candidate["local_date"], candidate.get("local_time"),
                 candidate.get("quantity") or candidate.get("eligible_quantity"), candidate.get("unit_price"), candidate.get("gross_amount")])


@reader_plugins.within_reader_session
def _adapter_reader_identity(adapter_id: str) -> dict[str, str] | None:
    """Leser eines Wertpapier-, Devisen- oder generischen Lesers fuer die Herkunft je Buchung; beim Krypto-Sammelleser je Zeile (None)."""
    plugin = ADAPTERS[adapter_id].get("plugin")
    if plugin:
        return reader_plugins.reader_identity_v1(plugin[1], plugin[0])
    if adapter_id in ("generic_securities_v1", "generic_crypto_v1"):
        return reader_plugins.core_reader_identity_v1(adapter_id, ADAPTERS[adapter_id].get("domain", "securities"), generic.__file__)
    return None


def parse_securities_statement_set_v1(adapter_id: str, sources: Sequence[tuple[bytes, str]], options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Jede Datei ergibt genau einen Eintrag: einen Vorgang (Kandidat), einen benannten Grund oder ein Duplikat. 'options' erreicht
    nur Leser, die sie nehmen (der generische Leser #514: gespeicherte Profile)."""
    if adapter_id not in ADAPTERS:
        _abort("securities_statement_adapter_unknown")
    if not sources or len(sources) > MAX_DOCUMENTS:
        _abort("securities_statement_source_invalid")
    parse = ADAPTERS[adapter_id]["parse"]
    plugin = ADAPTERS[adapter_id].get("plugin")
    prefetched = []
    if plugin:
        items = [(text, file_name) for source, file_name in sources
                 if isinstance(source, bytes) and isinstance(file_name, str) and file_name.lower().endswith((".pdf", ".txt", ".csv"))
                 and len(source) <= MAX_BYTES and (text := _text(source, file_name)).strip()]
        prefetched = _prefetch_text(plugin[0], plugin[1], items) if len(items) > 1 else []
    try:
        return _parse_set(adapter_id, sources, options, parse)
    finally:
        for key in prefetched:
            _PREFETCHED.pop(key, None)


def _parse_set(adapter_id: str, sources: Sequence[tuple[bytes, str]], options: Mapping[str, Any] | None, parse: Any) -> dict[str, Any]:
    documents: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    row_reasons: list[dict[str, Any]] = []
    statements: list[dict[str, Any]] = []
    evidence: dict[str, list[Any]] = {}
    seen: dict[str, int] = {}
    for ordinal, (source, file_name) in enumerate(sources, 1):
        if not isinstance(source, bytes) or not isinstance(file_name, str):
            _abort("securities_statement_source_invalid")
        if not file_name.lower().endswith((".pdf", ".txt", ".csv")):  # Ordnerauswahl bringt alles mit, auch Tabellen und Sperrdateien
            result = _reason("unsupported_type")
        else:
            text = _text(source, file_name)
            result = _reason("too_large") if len(source) > MAX_BYTES else (_reason("unreadable") if not text.strip() else (
                parse(text, file_name, options) if ADAPTERS[adapter_id].get("with_options") else (
                    parse(text, file_name) if ADAPTERS[adapter_id].get("with_name") else parse(text))))
        if result["status"] == "statement":   # Kontoauszug: kein Vorgang, Saldo-Anker fuer die Belege desselben Satzes
            key = _sha(["statement", result["currency"], [str(value) for value in result["start"] + result["end"]],
                        [[line["valuta"], str(line["amount"])] for line in result["lines"]]])
            duplicate = key in seen
            documents.append({"document_ordinal": ordinal, "file_name": Path(file_name).name, "status": "not_importable",
                              "reason_code": "duplicate" if duplicate else "fx_statement", "reason": REASONS["duplicate" if duplicate else "fx_statement"],
                              "candidate_ordinal": None})
            if not duplicate:
                seen[key] = 0; statements.append({**result, "file_name": Path(file_name).name})
            continue
        if result["status"] == "multi":   # Export: viele Vorgaenge aus einer Datei, uebrige Zeilen gezaehlt mit Grund
            # Ein erkannter Export ohne buchbare Zeile (nur Rewards, nur Stornos) ist kein unbekannter Beleg: die Gruende stehen je Zeile.
            empty = "execution_evidence" if result.get("evidence") else "export_without_bookings" if result["row_reasons"] else "unknown_document"
            for key, items in (result.get("evidence") or {}).items():
                evidence.setdefault(key, []).extend(items)
            entry = {"document_ordinal": ordinal, "file_name": Path(file_name).name, "status": "candidate" if result["candidates"] else "not_importable",
                     "reason_code": None if result["candidates"] else empty, "reason": None if result["candidates"] else REASONS[empty],
                     "candidate_ordinal": None, "candidate_count": 0}
            for code, count in sorted(result["row_reasons"].items()):
                # Einzeln verworfene Zeilen (rc.379): je Zeile ein Eintrag mit Zeilennummer, Feld und Grund; der Rest gezaehlt wie bisher.
                details = sorted((item for item in result.get("row_details") or [] if item["reason_code"] == code),
                                 key=lambda item: (item.get("line") or 0, item["row_no"]))
                for item in details:
                    row_reasons.append({"file_name": entry["file_name"], "rows": 1, "reason_code": code, "reason": crypto.crypto_row_detail_reason_v1(item),
                                        "row_no": item["row_no"], "line": item.get("line"), "field": item["field"], "problem": item["problem"]})
                if count > len(details):
                    row_reasons.append({"file_name": entry["file_name"], "rows": count - len(details), "reason_code": code, "reason": REASONS[code]})
            for item in result["candidates"]:
                key = _candidate_key(item)
                if key in seen:
                    row_reasons.append({"file_name": entry["file_name"], "rows": 1, "reason_code": "duplicate", "reason": REASONS["duplicate"]}); continue
                item = {**item, "candidate_ordinal": len(candidates) + 1, "document_ordinal": ordinal, "file_name": entry["file_name"], "candidate_key": key}
                seen[key] = item["candidate_ordinal"]; candidates.append(item); entry["candidate_count"] += 1
            documents.append(entry)
            continue
        entry = {"document_ordinal": ordinal, "file_name": Path(file_name).name, "status": result["status"],
                 "reason_code": result.get("reason_code"), "reason": result.get("reason"), "candidate_ordinal": None}
        if result["status"] == "candidate":
            key = _candidate_key(result)
            if key in seen:
                entry.update(status="not_importable", reason_code="duplicate", reason=REASONS["duplicate"])
            else:
                result = {**result, "candidate_ordinal": len(candidates) + 1, "document_ordinal": ordinal, "file_name": entry["file_name"], "candidate_key": key}
                seen[key] = result["candidate_ordinal"]
                candidates.append(result)
                entry["candidate_ordinal"] = result["candidate_ordinal"]
        documents.append(entry)
    # Manche Dividendenbelege tragen keine Depotnummer: Liegt genau ein Depot derselben Depotfamilie (Manifest des Lesers) vor, gehoeren
    # sie dorthin.
    family = lambda profile: _profile(profile)["depot_family"]  # noqa: E731
    depots: dict[str, set[str]] = {}
    for candidate in candidates:
        if candidate.get("depot_ref"):
            depots.setdefault(family(candidate["profile"]), set()).add(candidate["depot_ref"])
    for candidate in candidates:
        known = depots.get(family(candidate["profile"]), set())
        if not candidate.get("depot_ref") and len(known) == 1:
            candidate["depot_ref"] = next(iter(known))
    if ADAPTERS[adapter_id].get("finish"):
        ADAPTERS[adapter_id]["finish"](candidates, statements, row_reasons, **({"evidence": evidence} if ADAPTERS[adapter_id].get("with_evidence") else {}))
    # Nennen Belege Salden (Kontoauszuege der Devisenkonten), rechnet der Kern nach - nie das Plugin.
    if statements:
        _verify_statements(candidates, statements, row_reasons)
    # Herkunft je Buchung (rc.378): der Leser jedes Vorgangs; Krypto-Vorgaenge sammeln ihn aus ihren Zeilen.
    identity = _adapter_reader_identity(adapter_id)
    for candidate in candidates:
        if not candidate.get("readers"):
            candidate["readers"] = [identity] if identity else []
    counts: dict[str, int] = {}
    for entry in documents:
        counts[entry["reason_code"] or entry["status"]] = counts.get(entry["reason_code"] or entry["status"], 0) + 1
    return {"securities_statement_parse_version": VERSION, "adapter_id": adapter_id, "documents": documents, "candidates": candidates,
            "row_reasons": row_reasons, "counts": counts, "statement_count": len(statements),
            "network_access": False, "provider_access": False, "canonical_write": False}


# --- Pruefung gegen den Bestand ----------------------------------------------------------------------------------------

def _context(value: Any) -> DesktopProductAssetActivityContextV1:
    if isinstance(value, DesktopProductAssetActivityContextV1):
        return value
    _abort("securities_statement_context_invalid")


def _asset_isins(canonical_path: Path) -> dict[str, str]:
    try:
        connection = sqlite3.connect(f"file:{canonical_path}?mode=ro", uri=True)
        try:
            return {row[0]: row[1] for row in connection.execute("SELECT asset_id, isin FROM asset WHERE status = 'active' AND isin IS NOT NULL")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("securities_statement_review_invalid")


def _ledger_events(data_space: Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding["status"] == "absent":
        return []
    try:
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(
                "SELECT event_ref, account_id, related_account_id, asset_id, event_type, local_date, local_time, quantity_decimal, "
                "eligible_quantity_decimal, unit_price_decimal, monetary_fee_decimal, asset_fee_quantity_decimal, gross_amount_decimal, "
                "gross_income_decimal, amount_input_mode "
                "FROM current_asset_activity_event")]
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("securities_statement_review_invalid")


def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _days(left: str, right: str) -> int:
    return abs((date.fromisoformat(left) - date.fromisoformat(right)).days)


def _event_quantity(event: Mapping[str, Any]) -> Decimal | None:
    return _dec(event["quantity_decimal"]) if event["event_type"] in ("buy", "sell", "deposit") else _dec(event["eligible_quantity_decimal"])


def _event_gross(event: Mapping[str, Any]) -> Decimal | None:
    return _dec(event["gross_amount_decimal"]) if event["amount_input_mode"] == "gross_total" else _dec(event["gross_income_decimal"])


def _split_factor(candidate: Mapping[str, Any], event: Mapping[str, Any]) -> Decimal | None:
    """Ist die Buchung split-bereinigt (ganzzahliges Vielfaches der Belegstueckzahl, Kurs im selben Verhaeltnis)? Dann der Faktor."""
    quantity = Decimal(candidate["quantity"] if candidate["kind"] in ("buy", "sell", "deposit") else candidate["eligible_quantity"])
    booked = _event_quantity(event)
    if booked is None or quantity == 0 or booked <= quantity or booked % quantity != 0:
        return None
    factor = booked / quantity
    if candidate["kind"] in ("buy", "sell"):
        if event["local_date"] != candidate["local_date"]:
            return None
        price = _dec(event["unit_price_decimal"]) or Decimal(0)
        if abs(price * factor - Decimal(candidate["unit_price"])) > Decimal("0.01") * factor:
            return None
    elif min(_days(event["local_date"], value) for value in (candidate["local_date"], candidate.get("ex_date")) if value) > 10:
        return None
    return factor


def _differences(candidate: Mapping[str, Any], event: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Abweichungen (Belegwert gegen Buchung) und blosse Hinweise. Kurs exakt, Betraege auf den halben Cent."""
    differs: list[str] = []
    notes: list[str] = []
    if _is_fx(candidate["profile"]):
        # Devisen: Menge exakt, EUR-Wert auf den halben Cent (der Kurs ist ein Quotient und darf anders gerundet sein)
        if event["local_date"] != candidate["local_date"]:
            differs.append("Datum")
        booked = _event_gross(event) if event["amount_input_mode"] == "gross_total" else (
            (_event_quantity(event) or Decimal(0)) * (_dec(event["unit_price_decimal"]) or Decimal(0)))
        if booked is None or abs(booked - Decimal(candidate["gross_amount"])) > Decimal("0.005"):
            differs.append("EUR-Wert")
        return differs, notes
    if event["local_date"] != candidate["local_date"]:
        (notes if _days(event["local_date"], candidate["local_date"]) <= 3 and candidate["kind"] == "dividend" else differs).append("Datum")
    if candidate["kind"] in ("buy", "sell"):
        if _dec(event["unit_price_decimal"]) != Decimal(candidate["unit_price"]):
            differs.append("Kurs")
        booked_fee = _dec(event["monetary_fee_decimal"]) or Decimal(0)
        fee = Decimal(candidate["fee_amount"])
        if abs(booked_fee - fee) > Decimal("0.005"):
            if candidate["fee_on_cash_statement"] and fee == 0:
                notes.append("Ordergebühr laut Kontoauszug")
            else:
                differs.append("Gebühr")
        if candidate.get("local_time") and event["local_time"] and event["local_time"][:5] != candidate["local_time"][:5]:
            notes.append("Uhrzeit")
    else:
        gross = _event_gross(event)
        if gross is None or abs(gross - Decimal(candidate["gross_amount"])) > Decimal("0.005"):
            differs.append("Brutto")
        if _dec(event["eligible_quantity_decimal"]) != Decimal(candidate["eligible_quantity"]):
            differs.append("Stückzahl")
    return differs, notes




# Kennungen nachtragen (#458 Teil 3, #439): gebuchte Vorgaenge, deren Beleg eine Kennung oder Adresse traegt, die am Beleg-Speicher
# noch fehlt. Je Buchung genau eine Kennung; eine vorhandene Angabe wird nie ueberschrieben, und eine Kennung, die schon an einer
# anderen Buchung steht, wird keiner zweiten zugeordnet. Teilausfuehrungen mit verschiedenen Nummern bleiben offen.
BACKFILL_STATUSES = frozenset({"booked", "booked_differs", "booked_combined", "split_adjusted"})


# Ein Beleg, zwei Buchungen (#458): Die Dividendenabrechnung in Fremdwaehrung traegt die Dividende des Papiers und den Zufluss der
# Waehrung. Beide duerfen dieselbe Vorgangsnummer tragen; sonst belegt eine Kennung hoechstens eine Buchung.
SHARED_REFERENCE_KINDS = frozenset({"dividend", "deposit"})


def _reference_backfill(candidates: Sequence[Mapping[str, Any]], results: Mapping[int, Mapping[str, Any]],
                        references: Mapping[str, Mapping[str, Any]], kinds: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    """kinds: event_ref -> Buchungsart aller Buchungen, die eine Kennung tragen (fuer die geteilte Kennung eines Belegs)."""
    holders: dict[str, set[str]] = {}
    for ref, entry in references.items():
        if entry.get("transaction_id"):
            holders.setdefault(str(entry["transaction_id"]).casefold(), set()).add((kinds or {}).get(ref, ""))
    by_event: dict[str, dict[str, set[str]]] = {}
    for candidate in candidates:
        result = results.get(candidate["candidate_ordinal"]) or {}
        event_ref = result.get("event_ref")
        if result.get("status") not in BACKFILL_STATUSES or not event_ref:
            continue
        current = references.get(event_ref) or {}
        identifier = candidate.get("transaction_id") or candidate.get("order_ref") or None
        address = candidate.get("address") or None
        found = by_event.setdefault(event_ref, {"transaction_id": set(), "counterparty_address": set()})
        if identifier and TOKEN.fullmatch(identifier) and not current.get("transaction_id"):
            found["transaction_id"].add(identifier)
        if address and TOKEN.fullmatch(address) and not current.get("counterparty_address"):
            found["counterparty_address"].add(address)
    entries = []
    for event_ref, found in sorted(by_event.items()):
        current = references.get(event_ref) or {}
        identifier = next(iter(found["transaction_id"])) if len(found["transaction_id"]) == 1 else None
        if identifier is not None and identifier.casefold() in holders:
            own = (kinds or {}).get(event_ref, "")
            others = holders[identifier.casefold()]
            if not (own in SHARED_REFERENCE_KINDS and len(others) == 1 and others <= SHARED_REFERENCE_KINDS - {own}):
                identifier = None
        address = next(iter(found["counterparty_address"])) if len(found["counterparty_address"]) == 1 else None
        if identifier is None and address is None:
            continue
        entries.append({"event_ref": event_ref, "transaction_id": identifier or current.get("transaction_id"),
                        "counterparty_address": address or current.get("counterparty_address"), "note": current.get("note")})
    return entries


# Vorschlag fuer den Namen eines fehlenden Devisen-Assets (#453): nur Namen, die keine andere Waehrung mitmeinen ("Dollar" allein
# passte auch auf USD); sonst bleibt es beim ISO-Code, den _fx_matches immer erkennt.
FX_SUGGESTED_NAMES = {"USD": "US-Dollar", "CHF": "Schweizer Franken", "GBP": "Britisches Pfund", "JPY": "Japanischer Yen"}


def _missing_assets(rows: Sequence[Mapping[str, Any]], domain: str) -> list[dict[str, Any]]:
    """Je fehlendem Asset einmal, nicht je Vorgang (#453): was der Beleg dazu nennt - Grundlage fuer "Fehlendes Asset anlegen".

    Wertpapiere ueber ISIN (sonst Name), Krypto ueber das Kuerzel, Devisen ueber die Waehrung. Art und Kurswaehrung nur, wo die
    Quelle sie sicher sagt; den Rest schlaegt die Suche beim Kursanbieter vor."""
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("status") != "asset_missing":
            continue
        if domain == "fx":
            currency = row.get("currency") or ""
            key, entry = currency, {"name": FX_SUGGESTED_NAMES.get(currency, currency), "isin": None, "symbol": currency, "asset_type": "fx",
                                    "currency": "EUR", "quantity_scale": 2}
        elif domain == "crypto":
            ticker = row.get("security_name") or ""
            key, entry = ticker, {"name": ticker, "isin": None, "symbol": ticker, "asset_type": "crypto", "currency": "EUR", "quantity_scale": 24}
        else:
            isin = row.get("isin") or None
            key, entry = isin or (row.get("security_name") or ""), {"name": row.get("security_name"), "isin": isin, "symbol": None,
                                                                     "asset_type": None, "currency": None, "quantity_scale": None}
        if not key:
            continue
        current = found.setdefault(key, {"missing_key": key, "domain": domain, **entry, "count": 0})
        current["count"] += 1
    return sorted(found.values(), key=lambda item: ((item["name"] or item["missing_key"]).lower(), item["missing_key"]))


# Rechtsformen und Fuellwoerter, die ein Name im Beleg traegt und im Katalog nicht (oder umgekehrt). Klassenbuchstaben bleiben:
# "Beispiel Inc. Class C" ist nicht "Beispiel A".
_NAME_NOISE = frozenset({"ag", "se", "sa", "nv", "inc", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "the", "kgaa", "gmbh",
                         "holding", "holdings", "group", "registered", "shares", "namens", "aktien", "inhaber"})
SECURITY_TYPES = ("equity", "fund", "etf", "bond", "derivative", "commodity")


def _name_key(text: Any) -> str:
    words = re.findall(r"[a-z0-9]+", str(text or "").lower().replace("&", " and "))
    return " ".join(word for word in words if word not in _NAME_NOISE)


def _with_existing_candidates(missing: list[dict[str, Any]], assets: Mapping[str, Any], with_isin: set[str]) -> list[dict[str, Any]]:
    """Vorhandenes zuordnen statt doppelt anlegen (#537, Festlegung 04.11.2026): Zu einem Wertpapier, dessen ISIN kein Asset traegt,
    die Assets des Katalogs ohne ISIN mit gleichem Namen (ohne Rechtsform, Gross- und Kleinschreibung). Nur Namen - die Zuordnung
    traegt die ISIN mit dem eigenen Katalogbefehl nach, der die Kursfreigaben gueltig laesst; der Eigentuemer bestaetigt sie."""
    for item in missing:
        item["existing_labels"] = []
        if item.get("domain") != "securities" or not item.get("isin") or not _name_key(item.get("name")):
            continue
        key = _name_key(item["name"])
        item["existing_labels"] = sorted(row["label"] for asset_id, row in assets.items()
                                         if row.get("asset_type") in SECURITY_TYPES and asset_id not in with_isin and _name_key(row["label"]) == key)
    return missing


def _fx_matches(label: str, currency: str) -> bool:
    """Steht die Waehrung im Namen - als ISO-Code ("USD") oder ueblicher Name ("US-Dollar", "Schweizer Franken")?"""
    return bool(re.search(r"(?<![A-Z])" + currency + r"(?![A-Z])", label)) or any(name in label.lower() for name in FX_NAMES.get(currency, ()))


def _depot_handle(candidate: Mapping[str, Any]) -> str:
    return "dep_" + _sha([_profile(candidate["profile"])["depot_family"], candidate.get("depot_ref") or ""])[:16]


def _account_institutions(canonical_path: Path) -> dict[str, str]:
    try:
        connection = sqlite3.connect(f"file:{canonical_path}?mode=ro", uri=True)
        try:
            return {row[0]: row[1] or "" for row in connection.execute("SELECT account_id, institution_label FROM account WHERE status = 'active'")}
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("securities_statement_review_invalid")


def latest_booked_dates_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, event_type: str) -> dict[str, str]:
    """Juengstes gebuchtes Datum je Institut fuer eine Buchungsart (#462): Vorbelegung "ab dem letzten Import" - etwa der
    Reward-Zeitraum ab dem juengsten gebuchten Reward der Boerse. Liest nur; ohne Institut am Konto zaehlt die Buchung nicht."""
    context = _context(context_value)
    if event_type not in ("buy", "sell", "dividend", "reward", "transfer", "deposit", "withdrawal"):
        _abort("securities_statement_review_invalid")
    institutions = _account_institutions(Path(canonical_path))
    latest: dict[str, str] = {}
    for event in _ledger_events(Path(data_space_path), context):
        label = institutions.get(event["account_id"])
        if event["event_type"] == event_type and label:
            latest[label] = max(latest.get(label, ""), event["local_date"])
    return latest




def _ledger_arrival_events(data_space: Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    """Konto, Gegenkonto, Coin, Art und Zeit der aktuellen Buchungen - fuer den Kontovorschlag beim Reward-Import. Liest nur."""
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding["status"] == "absent":
        return []
    try:
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(
                "SELECT account_id, related_account_id, asset_id, event_type, local_date, local_time FROM current_asset_activity_event")]
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("securities_statement_review_invalid")


def _resting_accounts(canonical: Path, context) -> set[str]:
    """Ruhende Konten (#529 Punkt 1) aus der Ablage neben dem Bestand: Die Importe bieten sie nicht an. Ohne Ablage keine."""
    from migrations.reference.statement_archive_v1 import StatementArchiveV1Error, read_statement_account_states_v1
    try:
        states = read_statement_account_states_v1(canonical.parent, context)
    except StatementArchiveV1Error:
        return set()
    return {account for account, state in states.items() if state.get("inactive_since") is not None}


def suggest_reward_accounts_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any, adapter_id: str,
                               asset_ids: Sequence[str]) -> dict[str, str]:
    """Kontovorschlag je Coin fuer den Reward-Import (rc.343).

    Unter den aktiven Krypto-Wallets der Boerse: das Konto, auf dem dieser Coin zuletzt einen Reward bekam; sonst das, auf das er
    zuletzt umgebucht wurde (etwa ins Staking); sonst das einzige Wallet der Boerse; sonst keins. Kaeufe zaehlen nicht (sie
    gehoeren in den Krypto-Import; nach einer Umbuchung ins Staking und einem Nachkauf auf dem Handelskonto zeigte
    der Vorschlag sonst beim ersten Reward aufs Handelskonto). Ein Vorschlag fuellt nur ein leeres Feld und bleibt aenderbar. Liest nur."""
    context = _context(context_value)
    # Boerse des Reward-Lesers (Institut im Manifest) = Anfang des Institutsnamens ihrer Konten, wie beim Reward-Zeitraum (#462).
    spec = reader_plugins.reader_spec_v1(adapter_id, "reward") if isinstance(adapter_id, str) else None
    prefix = spec.institution if spec is not None else None
    if prefix is None or not isinstance(asset_ids, (list, tuple)) or len(asset_ids) > 500 or any(not isinstance(item, str) or not item for item in asset_ids):
        _abort("securities_statement_review_invalid")
    canonical = Path(canonical_path)
    catalog = read_desktop_product_per_asset_catalog_v1(canonical, context)
    institutions = _account_institutions(canonical)
    resting = _resting_accounts(canonical, context)
    wallets = sorted(row["account_id"] for row in catalog["accounts"]
                     if row["account_type"] == "crypto_wallet" and institutions.get(row["account_id"], "").startswith(prefix) and row["account_id"] not in resting)
    if not wallets:
        return {}
    wanted = set(asset_ids)
    # Je Coin der juengste Reward auf einem Wallet der Boerse und die juengste Umbuchung dorthin (related_account_id ist das Ziel).
    rewards: dict[str, tuple[tuple[str, str], str]] = {}; arrivals: dict[str, tuple[tuple[str, str], str]] = {}
    for event in _ledger_arrival_events(Path(data_space_path), context):
        if event["asset_id"] not in wanted:
            continue
        when = (event["local_date"] or "", event["local_time"] or "")
        target = event["related_account_id"] if event["event_type"] == "transfer" else event["account_id"]
        if target not in wallets or event["event_type"] not in ("reward", "transfer"):
            continue
        for store in ((rewards, arrivals) if event["event_type"] == "reward" else (arrivals,)):
            if event["asset_id"] not in store or when >= store[event["asset_id"]][0]:
                store[event["asset_id"]] = (when, target)
    result: dict[str, str] = {}
    for asset_id in sorted(wanted):
        hit = rewards.get(asset_id) or arrivals.get(asset_id)
        if hit is not None:
            result[asset_id] = hit[1]
        elif len(wallets) == 1:
            result[asset_id] = wallets[0]
    return result


def suggest_securities_statement_accounts_v1(canonical_path: str | Path, context_value: Any, parsed: Mapping[str, Any]) -> dict[str, Any]:
    """Je Depot aus den Belegen ein Kontovorschlag: das einzige Wertpapierdepot des passenden Instituts, sonst keiner.
    Die Depotnummer bleibt serverseitig; die Data-App sieht ein Handle und die letzten vier Ziffern."""
    context = _context(context_value)
    canonical = Path(canonical_path)
    if ADAPTERS.get(parsed.get("adapter_id"), {}).get("domain") == "crypto":
        return _suggest_crypto(canonical, context, parsed)
    catalog = read_desktop_product_per_asset_catalog_v1(canonical, context)
    institutions = _account_institutions(canonical)
    resting = _resting_accounts(canonical, context)
    securities = [row for row in catalog["accounts"] if row["account_type"] in ("securities", "other") and row["account_id"] not in resting]
    depots: dict[str, dict[str, Any]] = {}
    for candidate in parsed.get("candidates", []):
        handle = _depot_handle(candidate)
        mask = (candidate["depot_ref"] + "-Konto" if _is_fx(candidate["profile"]) else "…" + candidate["depot_ref"][-4:]) if candidate.get("depot_ref") else "ohne Nummer"
        entry = depots.setdefault(handle, {"depot_handle": handle, "depot_mask": mask,
                                           "profile": candidate["profile"], "profile_label": _profile(candidate["profile"])["label"], "candidate_count": 0})
        entry["candidate_count"] += 1
    choices = [{"account_ref": "acr_" + _sha([context.data_space_id, row["account_id"]])[:16], "label": row["label"], "institution": institutions.get(row["account_id"], "")} for row in securities]
    trusted = {choice["account_ref"]: row["account_id"] for choice, row in zip(choices, securities)}
    kinds = {choice["account_ref"]: row["account_type"] for choice, row in zip(choices, securities)}
    for entry in depots.values():
        matching = [choice for choice in choices if choice["institution"] in _profile(entry["profile"])["institution_names"]]
        # Fremdwaehrungskonten (Kontoart other) nur fuer Devisen, und dann das Konto mit der Waehrung im Namen; ein Wertpapier-
        # depot zieht ein Depot vor, damit ein Devisenkonto desselben Instituts den Vorschlag nicht mehrdeutig macht.
        if _is_fx(entry["profile"]):
            currency = entry["depot_mask"][:3]
            matching = [choice for choice in matching if kinds[choice["account_ref"]] == "other" and _fx_matches(choice["label"], currency)]
        elif any(kinds[choice["account_ref"]] == "securities" for choice in matching):
            matching = [choice for choice in matching if kinds[choice["account_ref"]] == "securities"]
        # Mehrere Depots desselben Instituts (eine Bank verwahrt fuer zwei Broker): der Kontohinweis des Profils entscheidet.
        hint = _profile(entry["profile"])["account_hint"]
        if len(matching) > 1 and hint:
            matching = [choice for choice in matching if hint.lower() in choice["label"].lower()]
        entry["suggested_account_ref"] = matching[0]["account_ref"] if len(matching) == 1 else None
    return {"public": {"depots": sorted(depots.values(), key=lambda item: item["depot_mask"]), "accounts": choices, "internal_id_exposed": False},
            "trusted_account_refs": trusted}


def _resolve_window(window: Any, adapter_id: str, data_space: Path) -> dict[str, Any]:
    """Betrachteter Zeitraum (#462). Ohne Angabe: alles, wie bisher. "since_confirmed": ab dem juengsten bestaetigten Beleg dieses
    Lesers (Pruefstand, #450) - der Normalfall "ab dem letzten Import" ohne Eingabe; gibt es keinen, gilt alles."""
    if window is None:
        return {"mode": "all", "from": None, "through": None}
    if not isinstance(window, Mapping) or set(window) != {"mode", "from", "through"} or window["mode"] not in WINDOW_MODES:
        _abort("securities_statement_review_invalid")
    bounds = {}
    for key in ("from", "through"):
        value = window[key] or None
        if value is not None and (not isinstance(value, str) or not _DAY.match(value)):
            _abort("securities_statement_review_invalid")
        bounds[key] = value
    if window["mode"] == "all":
        return {"mode": "all", "from": None, "through": None}
    if window["mode"] == "since_confirmed":
        confirmed = read_securities_statement_confirmations_v1(data_space).get(adapter_id)
        bounds["from"] = confirmed["through"] if confirmed else None
    if bounds["from"] and bounds["through"] and bounds["from"] > bounds["through"]:
        _abort("securities_statement_review_invalid")
    return {"mode": window["mode"], **bounds}


def _window_label(labels: Mapping[str, str], result: Mapping[str, Any]) -> str:
    """Ausserhalb des Zeitraums mit dem Status, den der Vorgang sonst haette - damit nichts still verschwindet."""
    if result["status"] != "out_of_window" or not result.get("window_status"):
        return labels[result["status"]]
    return labels["out_of_window"] + " (wäre: " + labels[result["window_status"]].split(" – ")[0] + ")"


def _outside(window: Mapping[str, Any], day: str | None) -> bool:
    return bool(day) and ((window["from"] is not None and day < window["from"]) or (window["through"] is not None and day > window["through"]))


def _apply_window(window: Mapping[str, Any], dated: Sequence[tuple[str | None, dict[str, Any]]], hidden: frozenset[str]) -> dict[str, int]:
    """Setzt Ergebnisse ausserhalb des Zeitraums auf "out_of_window" und zaehlt sie nach dem Status, den sie gehabt haetten."""
    counts: dict[str, int] = {}
    for day, result in dated:
        if result["status"] in hidden and _outside(window, day):
            counts[result["status"]] = counts.get(result["status"], 0) + 1
            result["window_status"] = result["status"]; result["status"] = "out_of_window"
    return counts


def _hold_inactive_readers(data_space: Path, context: Any, portfolio_ids: set[str], candidates: Sequence[Mapping[str, Any]],
                           results: dict[int, dict[str, Any]]) -> None:
    """Portfolios getrennt (Festlegung 09.11.2026, rc.381): Ein neuer Vorgang, dessen Leser im Portfolio seines Kontos nicht aktiv ist, bleibt
    einzeln offen - mit Grund, ohne die uebrigen Vorgaenge aufzuhalten."""
    if len(portfolio_ids) != 1:
        return
    from migrations.reference import statement_reader_admin_v1 as admin  # noqa: PLC0415
    portfolio_id = next(iter(portfolio_ids))
    try:
        active = admin.active_plugins_v1(data_space, context).get(portfolio_id, set())
        label = admin._portfolios(data_space).get(portfolio_id, {}).get("label", portfolio_id)
    except admin.StatementReaderAdminV1Error:
        return   # der Pruefstand vor dem Buchen sperrt dann mit Grund
    institutions = {spec.plugin_id: spec.institution or spec.plugin_id for spec in reader_plugins.reader_specs_v1()}
    for candidate in candidates:
        result = results.get(candidate["candidate_ordinal"])
        inactive = sorted({reader.get("plugin_id") for reader in candidate.get("readers") or []
                           if reader.get("plugin_id") not in active and reader.get("plugin_id") != "portelyra_core"})
        if result is not None and result["status"] == "new" and inactive:
            result["status"] = "open"
            result["notes"] = list(result["notes"]) + [
                f"Leser {', '.join(institutions.get(plugin, plugin) for plugin in inactive)} im Portfolio „{label}“ nicht aktiv – gebucht wird dieser "
                "Vorgang nicht; aktivieren im Reiter „Leser“ unter „Aktivierung je Portfolio“."]


def _hold_out_of_scope(data_space: Path, context: Any, portfolio_ids: set[str], candidates: Sequence[Mapping[str, Any]],
                       results: dict[int, dict[str, Any]], assets: Mapping[str, Mapping[str, Any]], skip: bool) -> dict[str, Any]:
    """Umfang je Portfolio (#551, Festlegung 11.11.2026): Ein neuer Vorgang mit einem Asset einer im Portfolio nicht gewaehlten Klasse wird
    nicht still gebucht. Ohne Wahl bleibt er "Klasse nicht gewaehlt" und sperrt das Buchen (Pflichtwahl); mit `skip` heisst er
    "uebersprungen". Beides nimmt ihn aus den neuen Vorgaengen und damit aus dem Fingerabdruck der Pruefung."""
    from migrations.reference import portfolio_configuration_v1 as configuration  # noqa: PLC0415
    empty = {"classes": [], "pending": 0, "skipped": 0, "portfolio_label": None, "outside_window": []}
    if len(portfolio_ids) != 1:
        return empty
    scope = configuration.import_scope_v1(data_space, next(iter(portfolio_ids)), context)
    allowed = set(scope["asset_types"])
    classes: dict[str, dict[str, Any]] = {}
    outside: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        result = results.get(candidate["candidate_ordinal"])
        asset = assets.get(candidate.get("asset_id") or "")
        if result is None or asset is None or asset.get("asset_type") in allowed:
            continue
        key, label = configuration.class_of_v1(asset.get("asset_type") or "other")
        # Ausserhalb des betrachteten Zeitraums (Festlegung 11.11.2026): nur genannt, ohne Pflichtwahl - sonst steckten
        # einmal uebersprungene Vorgaenge nach dem naechsten Buchen still in "ausserhalb des Zeitraums".
        if result["status"] == "out_of_window" and result.get("window_status") == "new":
            result["notes"] = list(result["notes"]) + [f"„{label}“ ist im Portfolio „{scope['label'] or '–'}“ nicht gewählt."]
            entry = outside.setdefault(key, {"key": key, "label": label, "count": 0})
            entry["count"] += 1
            continue
        if result["status"] != "new":
            continue
        result["status"] = "skipped_scope" if skip else "out_of_scope"
        result["notes"] = list(result["notes"]) + [f"„{label}“ ist im Portfolio „{scope['label'] or '–'}“ nicht gewählt – "
                                                   + ("übersprungen, nicht gebucht." if skip else "Klasse dazunehmen oder diese Buchungen überspringen.")]
        entry = classes.setdefault(key, {"key": key, "label": label, "count": 0})
        entry["count"] += 1
    total = sum(entry["count"] for entry in classes.values())
    return {"classes": sorted(classes.values(), key=lambda entry: entry["label"]), "pending": 0 if skip else total, "skipped": total if skip else 0,
            "portfolio_label": scope["label"], "outside_window": sorted(outside.values(), key=lambda entry: entry["label"])}


def _scope_public(held: Mapping[str, Any], skip: bool) -> dict[str, Any]:
    return {"out_of_scope_classes": held["classes"], "out_of_scope_count": held["pending"], "scope_skipped_count": held["skipped"],
            "scope_skip": bool(skip), "scope_portfolio_label": held["portfolio_label"],
            "out_of_scope_outside_window": held["outside_window"],
            "out_of_scope_outside_window_count": sum(entry["count"] for entry in held["outside_window"])}


def review_securities_statement_import_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any,
                                          parsed: Mapping[str, Any], account_by_depot: Mapping[str, str], window: Any = None,
                                          scope_skip: bool = False) -> dict[str, Any]:
    """Jeder Vorgang wird gegen die Buchungen des Depots geprueft, dem seine Depotnummer zugeordnet ist; gebucht wird
    nichts. account_by_depot: Depot-Handle -> account_id (serverseitig aufgeloest).

    Reihenfolge: (1) Order- bzw. Vorgangsnummer als Belegkennung an der Buchung, (2) gleiche Art, gleiches Papier, gleicher
    Tag und gleiche Stueckzahl, (3) gleichzeitige Teilausfuehrungen gemeinsam, (4) split-bereinigt (Stueckzahl ein
    ganzzahliges Vielfaches, Kurs entsprechend geteilt), (5) gleiche Stueckzahl in bis zu 60 Tagen Abstand.
    """
    context = _context(context_value)
    if not isinstance(parsed, Mapping) or parsed.get("adapter_id") not in ADAPTERS or not isinstance(account_by_depot, Mapping):
        _abort("securities_statement_review_invalid")
    canonical = Path(canonical_path)
    data_space = Path(data_space_path)
    scope = _resolve_window(window, parsed["adapter_id"], data_space)
    if not isinstance(scope_skip, bool):
        _abort("securities_statement_review_invalid")
    if ADAPTERS[parsed["adapter_id"]]["domain"] == "crypto":
        return _review_crypto(canonical, data_space, context, parsed, account_by_depot, scope, scope_skip)
    catalog = read_desktop_product_per_asset_catalog_v1(canonical, context)
    accounts = {row["account_id"]: row for row in catalog["accounts"]}
    for account_id in account_by_depot.values():
        account = accounts.get(account_id)
        if account is None or account["account_type"] not in ("securities", "other"):
            _abort("securities_statement_account_invalid")
    if len({accounts[value]["portfolio_id"] for value in account_by_depot.values()}) > 1:
        _abort("securities_statement_account_invalid")
    assets = {row["asset_id"]: row for row in catalog["assets"]}
    by_isin: dict[str, str] = {}
    for asset_id, isin in _asset_isins(canonical).items():
        if asset_id in assets:
            by_isin[isin] = asset_id
    # Devisen-Assets ueber die Waehrung im Namen; mehrdeutig oder fehlend = fehlt im Katalog
    fx_assets: dict[str, str | None] = {}
    for candidate in parsed.get("candidates", []):
        if _is_fx(candidate["profile"]) and candidate["currency"] not in fx_assets:
            hits = [row["asset_id"] for row in catalog["assets"] if row.get("asset_type") == "fx" and _fx_matches(row["label"], candidate["currency"])]
            fx_assets[candidate["currency"]] = hits[0] if len(hits) == 1 else None
    chosen = set(account_by_depot.values())
    every = _ledger_events(data_space, context)
    kinds = {event["event_ref"]: event["event_type"] for event in every}
    events = [event for event in every if event["account_id"] in chosen and event["event_type"] in ("buy", "sell", "dividend", "deposit")]
    references = read_activity_references_v1(data_space, context, None)["references"]
    # Eine Kennung kann zwei Buchungen eines Belegs tragen (Dividende und Devisen-Zufluss, #458): je Kennung alle Buchungen.
    by_reference: dict[str, set[str]] = {}
    for ref, entry in references.items():
        if entry.get("transaction_id"):
            by_reference.setdefault(entry["transaction_id"], set()).add(ref)
    # Vorabpauschalen sind keine Buchungen des Bestands: eigener Abgleich gegen ihren Speicher (#460, #471).
    advance = _review_advance_lump_sums(data_space, context, [dict(item) for item in parsed.get("candidates", []) if item["kind"] == "advance_lump_sum"],
                                        account_by_depot, by_isin, assets, accounts, scope)
    candidates = [dict(candidate) for candidate in parsed.get("candidates", []) if candidate["kind"] not in ("advance_lump_sum", "stock_split")]
    used: set[str] = set()
    results: dict[int, dict[str, Any]] = {}

    def settle(candidate: Mapping[str, Any], status: str, event: Mapping[str, Any] | None, differs: Sequence[str] = (), notes: Sequence[str] = ()) -> None:
        results[candidate["candidate_ordinal"]] = {"status": status, "event_ref": None if event is None else event["event_ref"],
                                                   "differences": list(differs), "notes": list(notes)}
        if event is not None:
            used.add(event["event_ref"])

    open_candidates = []
    for candidate in candidates:
        asset_id = fx_assets.get(candidate["currency"]) if _is_fx(candidate["profile"]) else by_isin.get(candidate["isin"])
        candidate["asset_id"] = asset_id
        candidate["account_id"] = account_by_depot.get(_depot_handle(candidate))
        if candidate["account_id"] is None:
            settle(candidate, "depot_unassigned", None)
            continue
        if asset_id is None:
            settle(candidate, "asset_missing", None)
            continue
        holders = by_reference.get(candidate.get("order_ref") or "", set())
        event = next((item for item in events if item["event_ref"] in holders and item["asset_id"] == asset_id
                      and item["event_type"] == candidate["kind"] and item["account_id"] == candidate["account_id"]), None) if holders else None
        if event is not None:
            differs, notes = _differences(candidate, event)
            # Ueber die Kennung gefunden und split-bereinigt gebucht (#458 Teil 3): dieselbe Pruefung wie ohne Kennung, sonst hiesse
            # eine Buchung nach dem Nachtragen ihrer Kennung ploetzlich "abweichend".
            factor = _split_factor(candidate, event) if differs else None
            if factor is not None:
                settle(candidate, "split_adjusted", event, [], [f"Stückzahl ×{_plain(factor)}"])
                results[candidate["candidate_ordinal"]]["factor"] = factor
            else:
                settle(candidate, "booked_differs" if differs else "booked", event, differs, notes)
            continue
        open_candidates.append(candidate)
    candidate_quantity = lambda candidate: Decimal(candidate["quantity"] if candidate["kind"] in ("buy", "sell", "deposit") else candidate["eligible_quantity"])

    def exact(candidate: Mapping[str, Any]) -> dict[str, Any] | None:
        pool = [event for event in events if event["event_ref"] not in used and event["asset_id"] == candidate["asset_id"] and event["event_type"] == candidate["kind"]
                and event["account_id"] == candidate["account_id"]]
        if candidate["kind"] == "dividend":
            dates = [value for value in (candidate["local_date"], candidate.get("ex_date")) if value]
            pool = [event for event in pool if min(_days(event["local_date"], value) for value in dates) <= 10]
        else:
            pool = [event for event in pool if event["local_date"] == candidate["local_date"]]
        pool = [event for event in pool if _event_quantity(event) == candidate_quantity(candidate)]
        pool.sort(key=lambda event: (abs((_dec(event["unit_price_decimal"]) or Decimal(0)) - Decimal(candidate.get("unit_price") or 0)), event["local_time"] or ""))
        return pool[0] if pool else None

    remaining = []
    for candidate in open_candidates:
        event = exact(candidate)
        if event is None:
            remaining.append(candidate)
            continue
        differs, notes = _differences(candidate, event)
        settle(candidate, "booked_differs" if differs else "booked", event, differs, notes)
    # Gleichzeitige Teilausfuehrungen (gleiches Papier, gleiche Art, gleicher Zeitpunkt, gleicher Kurs) als eine Buchung.
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for candidate in remaining:
        if candidate["kind"] in ("buy", "sell"):
            # Getrennt gelesene Teilausfuehrungen (#471) tragen ihre Gruppe: ihre Ordnungszeiten unterscheiden sich um Sekunden.
            groups.setdefault((candidate["account_id"], candidate["asset_id"], candidate["kind"], candidate["local_date"],
                               candidate.get("execution_group") or candidate.get("local_time"), candidate["unit_price"]), []).append(candidate)
    for (account_id, asset_id, kind, local_date, _time, price), members in groups.items():
        if len(members) < 2:
            continue
        total = sum(Decimal(member["quantity"]) for member in members)
        fee = sum(Decimal(member["fee_amount"]) for member in members)
        pool = [event for event in events if event["event_ref"] not in used and event["asset_id"] == asset_id and event["event_type"] == kind
                and event["account_id"] == account_id and event["local_date"] == local_date and _event_quantity(event) == total]
        if not pool:
            continue
        event = pool[0]
        combined = {**members[0], "quantity": _plain(total), "fee_amount": _plain(fee)}
        differs, notes = _differences(combined, event)
        split = [SEPARATE_EXECUTIONS_NOTE] if any(member.get("separate_executions") for member in members) else []
        for member in members:
            settle(member, "booked_differs" if differs else "booked_combined", event, differs, list(notes) + split)
    remaining = [candidate for candidate in remaining if candidate["candidate_ordinal"] not in results]
    # Split-bereinigt gebucht: ganzzahliges Vielfaches der Stueckzahl, Kurs (bzw. je Stueck) entsprechend geteilt.
    for candidate in list(remaining):
        for event in events:
            if event["event_ref"] in used or event["asset_id"] != candidate["asset_id"] or event["event_type"] != candidate["kind"] or event["account_id"] != candidate["account_id"]:
                continue
            factor = _split_factor(candidate, event)
            if factor is None:
                continue
            settle(candidate, "split_adjusted", event, [], [f"Stückzahl ×{_plain(factor)}"])
            results[candidate["candidate_ordinal"]]["factor"] = factor
            remaining.remove(candidate)
            break
    # Zweiter Durchgang: gleiche Stueckzahl in bis zu 60 Tagen Abstand (falsches Datum).
    for candidate in list(remaining):
        pool = [event for event in events if event["event_ref"] not in used and event["asset_id"] == candidate["asset_id"] and event["event_type"] == candidate["kind"]
                and event["account_id"] == candidate["account_id"] and _event_quantity(event) == candidate_quantity(candidate)
                and _days(event["local_date"], candidate["local_date"]) <= SECOND_PASS_DAYS]
        if not pool:
            continue
        event = min(pool, key=lambda item: _days(item["local_date"], candidate["local_date"]))
        differs, notes = _differences(candidate, event)
        settle(candidate, "booked_differs", event, differs or ["Datum"], notes)
        remaining.remove(candidate)
    for candidate in remaining:
        settle(candidate, "new", None)
    # Einzeln gebuchte Teilausfuehrungen (#471) muessen in der Reihenfolge der Bank stehen, sonst verbraucht der FIFO die Teile
    # anders als sie.
    by_event = {event["event_ref"]: event for event in events}
    executions: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if candidate.get("execution_group"):
            executions.setdefault(candidate["execution_group"], []).append(candidate)
    for members in executions.values():
        settled = [results[member["candidate_ordinal"]] for member in sorted(members, key=lambda item: item["local_time"])]
        if len(settled) < 2 or any(item["status"] not in ("booked", "booked_differs") or item["event_ref"] is None for item in settled):
            continue
        refs = [item["event_ref"] for item in settled]
        if len(set(refs)) != len(refs):
            continue
        booked = [(by_event[ref]["local_date"], by_event[ref]["local_time"] or "") for ref in refs]
        if all(left[1] and left < right for left, right in zip(booked, booked[1:])):
            continue
        for item in settled:
            item["status"] = "booked_differs"
            if "Reihenfolge" not in item["differences"]:
                item["differences"] = list(item["differences"]) + ["Reihenfolge"]
    # Splitmitteilungen (#451, rc.372) ausserhalb des Zeitraums: Ein fehlender Split verfaelscht alles danach, deshalb immer
    # betrachtet. Ebenso die split-bereinigt gebuchten Vorgaenge davor, die sich auf die Belegstuecke umstellen lassen.
    by_event_ref = {event["event_ref"]: event for event in every}
    splits = _review_stock_splits(data_space, context, [dict(item) for item in parsed.get("candidates", []) if item["kind"] == "stock_split"],
                                  account_by_depot, by_isin, assets, accounts, every,
                                  [(candidate, results[candidate["candidate_ordinal"]], by_event_ref[results[candidate["candidate_ordinal"]]["event_ref"]])
                                   for candidate in candidates if results[candidate["candidate_ordinal"]]["status"] == "split_adjusted"])
    convertible = {item["event_ref"] for item in splits["conversions"]}
    for candidate in candidates:
        result = results[candidate["candidate_ordinal"]]
        result.pop("factor", None)
        if result["status"] == "split_adjusted" and result["event_ref"] in convertible:
            result["notes"] = list(result["notes"]) + ["mit dem Split auf die Stückzahl des Belegs umstellbar"]
    window_counts = _apply_window(scope, [(candidate["local_date"], results[candidate["candidate_ordinal"]]) for candidate in candidates], WINDOW_HIDDEN)
    # Neue Vorgaenge nach dem Pruefstand des Lesers: gelesen, aber gekennzeichnet - das Format koennte sich geaendert haben.
    # Massgeblich ist der spaetere von gemessenem und vom Eigentuemer bestaetigtem Pruefstand.
    confirmed = read_securities_statement_confirmations_v1(data_space_path).get(parsed["adapter_id"])
    # Ein Leser ohne Pruefstand (experimentell, #514): Jeder neue Vorgang ist juenger als der Pruefstand.
    through = max((ADAPTERS[parsed["adapter_id"]]["validated"] or {}).get("through", ""), confirmed["through"] if confirmed else "")
    beyond = 0
    for candidate in candidates:
        result = results[candidate["candidate_ordinal"]]
        if result["status"] == "new" and candidate["local_date"] > through:
            result["notes"] = list(result["notes"]) + [BEYOND_VALIDATION_NOTE]; beyond += 1
        if _is_fx(candidate["profile"]) and parsed.get("statement_count") and not candidate.get("statement_checked"):
            result["notes"] = list(result["notes"]) + [FX_UNCHECKED_NOTE]
        if _is_fx(candidate["profile"]) and result["status"] == "new" and candidate.get("local_time", "12:00:00") != "12:00:00":
            result["notes"] = list(result["notes"]) + [FX_ORDER_NOTE]
    # Neue gleichzeitige Teilausfuehrungen (gleiches Konto, Papier, Art, Zeitpunkt und Kurs) werden eine Buchung - so, wie die
    # Pruefung eine gemeinsam gebuchte als "Teilausfuehrungen gemeinsam" erkennt (Sparplan bei Trade Republic: ganze Stuecke
    # und Bruchteil). Beim Lesen bleiben die Zeilen getrennt, damit einzeln gebuchte weiter einzeln erkannt werden.
    new_groups: dict[tuple, list[dict[str, Any]]] = {}
    _hold_inactive_readers(data_space, context, {accounts[value]["portfolio_id"] for value in account_by_depot.values()}, candidates, results)
    held = _hold_out_of_scope(data_space, context, {accounts[value]["portfolio_id"] for value in account_by_depot.values()}, candidates, results, assets,
                              scope_skip)
    for candidate in candidates:
        if results[candidate["candidate_ordinal"]]["status"] == "new":
            # Getrennt verbrauchte Teilausfuehrungen (Trade Republic, #471) bleiben getrennte Buchungen.
            key = ((candidate["account_id"], candidate["asset_id"], candidate["kind"], candidate["local_date"], candidate["local_time"], candidate["unit_price"])
                   if candidate["kind"] in ("buy", "sell") and candidate.get("local_time") and not candidate.get("separate_executions")
                   else ("single", candidate["candidate_ordinal"]))
            new_groups.setdefault(key, []).append(candidate)
    new: list[dict[str, Any]] = []
    for members in new_groups.values():
        if len(members) == 1:
            new.append(members[0]); continue
        total = sum(Decimal(member["quantity"]) for member in members)
        new.append({**members[0], "quantity": _plain(total), "fee_amount": _plain(sum(Decimal(member["fee_amount"]) for member in members)),
                    "gross_amount": _plain(sum(Decimal(member["gross_amount"] or 0) for member in members)),
                    "candidate_key": _sha(sorted(member["candidate_key"] for member in members)),
                    "order_ref": "+".join(sorted(member["order_ref"] for member in members if member.get("order_ref"))) or None})
        for member in members:
            results[member["candidate_ordinal"]]["notes"] = list(results[member["candidate_ordinal"]]["notes"]) + [COMBINED_NEW_NOTE]
    rows = []
    for candidate in candidates:
        result = results[candidate["candidate_ordinal"]]
        rows.append({"candidate_ordinal": candidate["candidate_ordinal"], "file_name": candidate["file_name"], "kind": candidate["kind"],
                     "isin": candidate["isin"], "security_name": candidate["security_name"], "currency": candidate.get("currency"),
                     "asset_label": assets[candidate["asset_id"]]["label"] if candidate.get("asset_id") else None,
                     "account_label": accounts[candidate["account_id"]]["label"] if candidate.get("account_id") else None,
                     "local_date": candidate["local_date"], "local_time": candidate.get("local_time"), "quantity": candidate.get("quantity"),
                     "eligible_quantity": candidate.get("eligible_quantity"), "unit_price": candidate.get("unit_price"),
                     "gross_amount": candidate.get("gross_amount"), "fee_amount": candidate.get("fee_amount"),
                     "status": result["status"], "status_label": _window_label(STATUS_LABELS, result),
                     "differences": result["differences"], "notes": result["notes"]})
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    portfolio_ids = {accounts[value]["portfolio_id"] for value in account_by_depot.values()}
    trusted = {"adapter_id": parsed["adapter_id"], "portfolio_id": next(iter(portfolio_ids)) if portfolio_ids else None,
               "new_candidates": [{key: candidate.get(key) for key in ("candidate_key", "kind", "asset_id", "account_id", "local_date", "local_time", "quantity",
                                                                       "unit_price", "fee_amount", "eligible_quantity", "gross_amount", "order_ref", "readers")}
                                  for candidate in new],
               "new_advance_lump_sums": advance["new"], "differing_advance_lump_sums": advance["differing"], "advance_lump_sum_readers": advance["readers"],
               "new_stock_splits": splits["new"], "stock_split_conversions": splits["conversions"],
               "reference_backfill": _reference_backfill(candidates, results, references, kinds),
               "scope_skip": scope_skip, "scope_pending": held["pending"]}
    trusted["review_fingerprint"] = _sha(trusted)
    return {"public_review": {"securities_statement_review_version": VERSION, "adapter_id": parsed["adapter_id"],
                              "adapter": {**_adapter_public(parsed["adapter_id"]), "confirmed": confirmed, "effective_through": through},
                              "beyond_validation_count": beyond,
                              "advance_lump_sum_rows": advance["rows"], "advance_lump_sum_counts": advance["counts"],
                              "stock_split_rows": splits["rows"], "stock_split_counts": splits["counts"], "stock_split_new_count": len(splits["new"]),
                              "stock_split_conversion_rows": splits["conversion_rows"], "stock_split_conversion_count": len(splits["conversions"]),
                              "advance_lump_sum_new_count": len(advance["new"]), "advance_lump_sum_differing_count": len(advance["differing"]),
                              "split_recommended_count": sum(1 for row in rows if SEPARATE_EXECUTIONS_NOTE in row["notes"]),
                              "window": scope, "out_of_window_counts": window_counts, "out_of_window_count": sum(window_counts.values()),
                              "advance_lump_sum_out_of_window_count": advance["counts"].get("out_of_window", 0),
                              "rows": rows, "counts": counts, "new_count": len(new), "documents": parsed.get("documents", []),
                              "row_reasons": parsed.get("row_reasons", []),
                              "missing_assets": _with_existing_candidates(_missing_assets(rows, ADAPTERS[parsed["adapter_id"]]["domain"]),
                                                                          assets, set(by_isin.values())),
                              "reference_backfill_count": len(trusted["reference_backfill"]),
                              "document_counts": parsed.get("counts", {}), "canonical_write": False, "network_access": False,
                              "internal_id_exposed": False, **_scope_public(held, scope_skip)},
            "trusted_review": trusted}


def _money(value: Decimal) -> str:
    return format(value.quantize(CENT, ROUND_HALF_UP), "f").replace(".", ",")


def _review_advance_lump_sums(data_space: Path, context: DesktopProductAssetActivityContextV1, candidates: Sequence[Mapping[str, Any]],
                              account_by_depot: Mapping[str, str], by_isin: Mapping[str, str], assets: Mapping[str, Any],
                              accounts: Mapping[str, Any], scope: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Vorabpauschalen der Belege gegen den Speicher je Fonds, Konto und Berechnungsjahr (#460, #471). Schreibt nichts.

    Mit Betrag (ING): fehlt der Eintrag, wird er uebernehmbar; weicht er ab, wird das gemeldet und nur auf ausdruecklichen
    Wunsch ersetzt. Ohne Betrag (Trade Republic nennt nur die Steuer): Die Steuer ergibt eine Untergrenze - fehlt der Eintrag
    oder liegt er darunter, ist das eine Warnung; geschrieben wird dann nie etwas."""
    try:
        stored = {(item["asset_id"], item["account_id"], item["calculation_year"]): Decimal(item["amount_decimal"])
                  for item in read_advance_lump_sums_v1(data_space, context)["bookings"]}
    except (AdvanceLumpSumV1Error, InvalidOperation):
        _abort("securities_statement_review_invalid")
    keyed: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
    readers_by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        asset_id = by_isin.get(candidate["isin"])
        account_id = account_by_depot.get(_depot_handle(candidate))
        status = ("depot_unassigned" if account_id is None else "asset_missing" if asset_id is None
                  else "not_a_fund" if assets[asset_id].get("asset_type") not in ("fund", "etf") else None)
        row = {"candidate_ordinal": candidate["candidate_ordinal"], "file_name": candidate["file_name"], "isin": candidate["isin"],
               "security_name": candidate["security_name"], "calculation_year": candidate["calculation_year"], "local_date": candidate["local_date"],
               "asset_label": assets[asset_id]["label"] if asset_id in assets else None,
               "account_label": accounts[account_id]["label"] if account_id in accounts else None,
               "amount": candidate.get("gross_amount"), "taxes_amount": candidate.get("taxes_amount"), "booked_amount": None,
               "status": status, "notes": []}
        rows.append(row)
        if status is None:
            row["_key"] = (asset_id, account_id, candidate["calculation_year"])
            keyed.setdefault(row["_key"], []).append(row)
            readers_by_key.setdefault(row["_key"], {}).update({json.dumps(reader, sort_keys=True): reader for reader in candidate.get("readers") or []})
    new: list[dict[str, Any]] = []
    differing: list[dict[str, Any]] = []
    for key, members in keyed.items():
        booked = stored.get(key)
        amounts = {Decimal(row["amount"]) for row in members if row["amount"] is not None}
        for row in members:
            row["booked_amount"] = None if booked is None else _plain(booked)
        if len(amounts) > 1:
            for row in members:
                row["status"] = "conflict"; row["notes"].append("Beträge der Belege: " + " / ".join(_money(value) + " €" for value in sorted(amounts)))
            continue
        if amounts:
            amount = next(iter(amounts))
            entry = {"asset_id": key[0], "account_id": key[1], "calculation_year": key[2], "amount_decimal": _plain(amount)}
            status = "new" if booked is None else "booked" if booked == amount else "differs"
            if status == "new":
                new.append(entry)
            elif status == "differs":
                differing.append(entry)
            for row in members:
                if row["amount"] is None:   # Hinweis ohne Betrag neben einem Beleg mit Betrag: der Beleg entscheidet
                    row["notes"].append("Betrag aus dem Beleg desselben Jahres")
                row["status"] = status
                if status == "differs":
                    row["notes"].append(f"eingetragen {_money(booked)} €, Beleg {_money(amount)} € – ersetzt nur auf ausdrücklichen Wunsch")
            continue
        tax = max((Decimal(row["taxes_amount"]) for row in members if row["taxes_amount"] is not None), default=Decimal(0))
        minimum = (tax / ADVANCE_LUMP_SUM_MAX_TAX_RATE).quantize(CENT, ROUND_HALF_UP) if tax else None
        for row in members:
            if booked is None:
                row["status"] = "amount_missing"
                row["notes"].append("Betrag steht nicht im Export – bitte aus dem Beleg der Bank zur Vorabpauschale eintragen"
                                    + (f"; laut einbehaltener Steuer ({_money(tax)} €) mindestens {_money(minimum)} €" if minimum else ""))
            elif minimum is not None and booked < minimum:
                row["status"] = "tax_mismatch"
                row["notes"].append(f"eingetragen {_money(booked)} €; die einbehaltene Steuer ({_money(tax)} €) verlangt mindestens {_money(minimum)} €")
            else:
                row["status"] = "booked"
                row["notes"].append("Betrag nicht im Export; eingetragener Wert passt zur einbehaltenen Steuer")
    # Ausserhalb des betrachteten Zeitraums (#462): gezaehlt, nicht vorgeschlagen - auch nicht zum Uebernehmen.
    if scope is not None:
        _apply_window(scope, [(row["local_date"], row) for row in rows], ADVANCE_WINDOW_HIDDEN)
        inside = {(row["_key"]) for row in rows if row.get("_key") and row["status"] != "out_of_window"}
        new = [entry for entry in new if (entry["asset_id"], entry["account_id"], entry["calculation_year"]) in inside]
        differing = [entry for entry in differing if (entry["asset_id"], entry["account_id"], entry["calculation_year"]) in inside]
    counts: dict[str, int] = {}
    for row in rows:
        row.pop("_key", None)
        row["status_label"] = _window_label(ADVANCE_LUMP_SUM_STATUS_LABELS, row)
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    # Herkunft je Vorabpauschale (rc.378): die Leser der Belege, je Schluessel des Speichers.
    readers = {advance_lump_sum_provenance_key_v1(entry["asset_id"], entry["account_id"], entry["calculation_year"]):
               [reader for _key, reader in sorted(readers_by_key.get((entry["asset_id"], entry["account_id"], entry["calculation_year"]), {}).items())]
               for entry in new + differing}
    return {"rows": rows, "counts": counts, "new": sorted(new, key=lambda item: (item["calculation_year"], item["asset_id"], item["account_id"])),
            "differing": sorted(differing, key=lambda item: (item["calculation_year"], item["asset_id"], item["account_id"])),
            "readers": {key: value for key, value in readers.items() if value}}


def record_securities_statement_advance_lump_sums_v1(data_space_path: str | Path, context_value: Any, trusted_review: Mapping[str, Any],
                                                     replace_differing: bool, recorded_at_utc: str, confirmed: bool) -> dict[str, Any]:
    """Uebernimmt die Vorabpauschalen der Belege in ihren Speicher (#460) - die fehlenden, und die abweichenden nur, wenn der
    Eigentuemer das ausdruecklich waehlt. Der Speicher haengt an; ein unveraenderter Wert schreibt nichts."""
    context = _context(context_value)
    if not isinstance(trusted_review, Mapping) or trusted_review.get("adapter_id") not in ADAPTERS:
        _abort("securities_statement_review_invalid")
    body = {key: value for key, value in trusted_review.items() if key != "review_fingerprint"}
    if trusted_review.get("review_fingerprint") != _sha(body):
        _abort("securities_statement_review_invalid")
    if confirmed is not True or not isinstance(replace_differing, bool):
        _abort("securities_statement_confirmation_invalid")
    entries = list(trusted_review.get("new_advance_lump_sums") or []) + (list(trusted_review.get("differing_advance_lump_sums") or []) if replace_differing else [])
    if not entries:
        _abort("securities_statement_review_invalid")
    try:
        result = record_advance_lump_sums_v1(Path(data_space_path), context, entries, recorded_at_utc, True)
    except AdvanceLumpSumV1Error:
        _abort("securities_statement_review_invalid")
    # Herkunft je Vorabpauschale (rc.378): eingetragen ist schon; ein Fehler beim Festhalten wird gemeldet.
    readers = trusted_review.get("advance_lump_sum_readers") or {}
    provenance = _record_provenance(Path(data_space_path), context, [
        {"booking_kind": "advance_lump_sum", "booking_key": key, "readers": readers[key]}
        for key in sorted({advance_lump_sum_provenance_key_v1(entry["asset_id"], entry["account_id"], entry["calculation_year"]) for entry in entries})
        if readers.get(key)], recorded_at_utc)
    return {"written_count": result["written_count"], "unchanged_count": result["unchanged_count"], "replaced_differing": replace_differing,
            "provenance_status": provenance}


def _record_provenance(data_space: Path, context: DesktopProductAssetActivityContextV1, entries: list[dict[str, Any]], recorded_at_utc: str) -> str:
    """Herkunft direkt festhalten (Vorabpauschalen, Splits): Status statt Abbruch - der Eintrag steht schon."""
    try:
        return record_reader_provenance_v1(data_space, context, entries, recorded_at_utc)["status"]
    except AssetActivityReferenceV1Error as error:
        return "failed:" + error.code


# --- Splitmitteilungen (#451, rc.372) ---------------------------------------------------------------------------------------

_HOLDING_SIGN = {"buy": 1, "deposit": 1, "reward": 1, "stock_dividend": 1, "sell": -1, "withdrawal": -1}
_CONVERSION_KINDS = ("buy", "sell", "dividend")


def _split_steps(stored: Sequence[Mapping[str, Any]]) -> dict[str, list[tuple[str, Fraction]]]:
    steps: dict[str, list[tuple[str, Fraction]]] = {}
    for split in stored:
        if split["account_ref"] is None:
            steps.setdefault(split["asset_ref"], []).append(
                (split["effective_local_date"], Fraction(int(split["ratio_numerator"]), int(split["ratio_denominator"]))))
    return steps


def _ratio_between(steps: Sequence[tuple[str, Fraction]], after: str, through: str | None = None) -> Fraction:
    """Verhaeltnis aller Splits nach dem Tag 'after' (bis einschliesslich 'through'): neue Stuecke je Stueck jenes Tages."""
    ratio = Fraction(1)
    for day, step in steps:
        if after < day and (through is None or day <= through):
            ratio *= step
    return ratio


def _document_holding(every: Sequence[Mapping[str, Any]], asset_id: str, account_id: str, day: str,
                      factors: Mapping[str, Fraction], steps: Sequence[tuple[str, Fraction]]) -> Fraction:
    """Bestand eines Kontos am Ende von 'day' in Stuecken dieses Tages. Split-bereinigt gebuchte Vorgaenge zaehlen mit der
    Stueckzahl ihres Belegs, gespeicherte Splits dazwischen mit ihrem Verhaeltnis."""
    total = Fraction(0)
    for event in every:
        quantity = _dec(event["quantity_decimal"])
        if event["asset_id"] != asset_id or event["local_date"] > day or quantity is None:
            continue
        fee = _dec(event.get("asset_fee_quantity_decimal")) or Decimal(0)
        if event["event_type"] == "transfer":
            delta = (-(quantity + fee) if event["account_id"] == account_id else Decimal(0)) + (quantity if event.get("related_account_id") == account_id else Decimal(0))
        elif event["account_id"] == account_id and event["event_type"] in _HOLDING_SIGN:
            delta = quantity - fee if _HOLDING_SIGN[event["event_type"]] > 0 else -(quantity + fee)
        else:
            continue
        total += Fraction(str(delta)) / factors.get(event["event_ref"], Fraction(1)) * _ratio_between(steps, event["local_date"], day)
    return total


def _review_stock_splits(data_space: Path, context: DesktopProductAssetActivityContextV1, candidates: Sequence[Mapping[str, Any]],
                         account_by_depot: Mapping[str, str], by_isin: Mapping[str, str], assets: Mapping[str, Any],
                         accounts: Mapping[str, Any], every: Sequence[Mapping[str, Any]],
                         adjusted: Sequence[tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]]) -> dict[str, Any]:
    """Splitmitteilungen gegen den Split-Speicher und den Bestand (#451, rc.372). Schreibt nichts.

    Neu ist eine Mitteilung, wenn fuer das Papier in 31 Tagen Abstand kein Split gespeichert ist und die eingebuchten
    Zusatzstuecke genau zum Bestand am genannten Tag passen (Bestand x (neu/alt - 1)). Umstellbar sind split-bereinigt
    gebuchte Vorgaenge, deren Faktor genau dem Verhaeltnis der Splits danach entspricht - gespeicherter und neuer."""
    from migrations.reference.stock_split_v1 import StockSplitV1Error, splits_for_fifo_v1
    try:
        stored = splits_for_fifo_v1(data_space, context)
    except StockSplitV1Error:
        _abort("securities_statement_review_invalid")
    stored_steps = _split_steps(stored)
    factors = {event["event_ref"]: Fraction(str(result["factor"])) for _candidate_item, result, event in adjusted}
    accepted = {asset: list(items) for asset, items in stored_steps.items()}
    blocked: set[str] = set()
    rows: list[dict[str, Any]] = []
    new: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (item["local_date"], item["candidate_ordinal"])):
        asset_id = by_isin.get(candidate["isin"])
        account_id = account_by_depot.get(_depot_handle(candidate))
        ratio = Fraction(int(candidate["ratio_numerator"]), int(candidate["ratio_denominator"]))
        row = {"candidate_ordinal": candidate["candidate_ordinal"], "file_name": candidate["file_name"], "isin": candidate["isin"],
               "security_name": candidate["security_name"], "asset_label": assets[asset_id]["label"] if asset_id in assets else None,
               "account_label": accounts[account_id]["label"] if account_id in accounts else None,
               "local_date": candidate["local_date"], "record_date": candidate["record_date"],
               "ratio_numerator": candidate["ratio_numerator"], "ratio_denominator": candidate["ratio_denominator"],
               "credited_quantity": candidate["credited_quantity"], "holding_quantity": None, "status": None, "notes": []}
        rows.append(row)
        if asset_id is None:
            row["status"] = "asset_missing"; continue
        if account_id is None:
            row["status"] = "depot_unassigned"; continue
        near = [item for item in stored if item["asset_ref"] == asset_id and item["account_ref"] is None
                and _days(item["effective_local_date"], candidate["local_date"]) <= STOCK_SPLIT_NEAR_DAYS]
        taken = [item for item in new if item["asset_id"] == asset_id and _days(item["effective_local_date"], candidate["local_date"]) <= STOCK_SPLIT_NEAR_DAYS]
        if near or taken:
            same = [item for item in near if item["effective_local_date"] == candidate["local_date"] and
                    Fraction(int(item["ratio_numerator"]), int(item["ratio_denominator"])) == ratio]
            same_new = [item for item in taken if item["effective_local_date"] == candidate["local_date"] and
                        Fraction(int(item["ratio_numerator"]), int(item["ratio_denominator"])) == ratio]
            row["status"] = "recorded" if same and len(near) == 1 else "new" if same_new and not near and len(taken) == 1 else "differs"
            if row["status"] == "differs":
                blocked.add(asset_id)
                row["notes"].append("gespeichert: " + "; ".join(f"{item['ratio_numerator']} : {item['ratio_denominator']} am {_german_day(item['effective_local_date'])}"
                                                               for item in near + taken))
            elif row["status"] == "new":
                row["notes"].append("dieselbe Mitteilung wie in einem anderen Beleg")
            continue
        holding = _document_holding(every, asset_id, account_id, candidate["record_date"], factors, stored_steps.get(asset_id, []))
        row["holding_quantity"] = _fraction_text(holding)
        expected = holding * (ratio - 1)
        if holding <= 0 or Fraction(candidate["credited_quantity"]) != expected:
            row["status"] = "quantity_mismatch"; blocked.add(asset_id)
            row["notes"].append(f"Bestand am {_german_day(candidate['record_date'])} laut Buchungen und Belegen: {_fraction_text(holding)} Stück; "
                                f"bei {candidate['ratio_numerator']} : {candidate['ratio_denominator']} wären {_fraction_text(expected)} Zusatzstücke eingebucht")
            continue
        row["status"] = "new"
        new.append({"asset_id": asset_id, "effective_local_date": candidate["local_date"], "ratio_numerator": candidate["ratio_numerator"],
                    "ratio_denominator": candidate["ratio_denominator"], "note": f"Splitmitteilung, Bestand vom {_german_day(candidate['record_date'])}",
                    "readers": list(candidate.get("readers") or [])})
        accepted.setdefault(asset_id, []).append((candidate["local_date"], ratio))
    conversions: list[dict[str, Any]] = []
    conversion_rows: list[dict[str, Any]] = []
    for candidate, result, event in adjusted:
        asset_id = event["asset_id"]
        if asset_id in blocked or candidate["kind"] not in _CONVERSION_KINDS or (candidate["kind"] != "dividend" and not candidate.get("unit_price")):
            continue
        factor = factors[event["event_ref"]]
        if factor == 1 or _ratio_between(sorted(accepted.get(asset_id, [])), event["local_date"]) != factor:
            continue
        dividend = candidate["kind"] == "dividend"
        conversions.append({"event_ref": event["event_ref"], "asset_id": asset_id, "kind": candidate["kind"], "local_date": event["local_date"],
                            "factor": _fraction_text(factor), "quantity": None if dividend else candidate["quantity"],
                            "eligible_quantity": candidate["eligible_quantity"] if dividend else None,
                            "unit_price": None if dividend else candidate["unit_price"]})
        conversion_rows.append({"local_date": event["local_date"], "kind": candidate["kind"], "asset_label": assets[asset_id]["label"],
                                "account_label": accounts[event["account_id"]]["label"] if event["account_id"] in accounts else None,
                                "booked_quantity": event["eligible_quantity_decimal"] if dividend else event["quantity_decimal"],
                                "document_quantity": candidate["eligible_quantity"] if dividend else candidate["quantity"],
                                "booked_unit_price": None if dividend else event["unit_price_decimal"],
                                "document_unit_price": None if dividend else candidate["unit_price"]})
    order = lambda item: (item["local_date"], item.get("event_ref") or "")
    counts: dict[str, int] = {}
    for row in rows:
        row["status_label"] = STOCK_SPLIT_STATUS_LABELS[row["status"]]
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return {"rows": rows, "counts": counts, "new": new, "conversions": sorted(conversions, key=order),
            "conversion_rows": sorted(conversion_rows, key=lambda item: item["local_date"])}


def _german_day(day: str) -> str:
    return f"{day[8:10]}.{day[5:7]}.{day[:4]}"


def _fraction_text(value: Fraction) -> str:
    """Exakt, wo es eine endliche Dezimalzahl gibt; sonst auf zwoelf Stellen."""
    denominator = value.denominator
    for factor in (2, 5):
        while denominator % factor == 0:
            denominator //= factor
    if denominator == 1:
        return _plain(Decimal(value.numerator) / Decimal(value.denominator))
    return _plain((Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal("1e-12"), ROUND_HALF_UP))


def _conversion_fields(row: Mapping[str, Any], conversion: Mapping[str, Any]) -> dict[str, Any]:
    """Die Buchung wie gebucht, nur mit Stueckzahl und Kurs des Belegs - die Felder der Korrekturmaske."""
    from migrations.reference.desktop_product_asset_activity_v1 import NATIVE_EVENT_KEYS
    renamed = {"account_ref": "account_id", "related_account_ref": "related_account_id", "asset_ref": "asset_id", "source_asset_ref": "source_asset_id"}
    fields = {key: row[renamed.get(key, key)] for key in NATIVE_EVENT_KEYS if key != "event_ref"}
    if conversion["kind"] == "dividend":
        fields["eligible_quantity_decimal"] = conversion["eligible_quantity"]
        # Als Stueck x Betrag je Stueck gebucht: Der Betrag je Stueck waechst mit dem Faktor, der Bruttoertrag bleibt genau wie
        # gebucht (ohne das fiele eine Dividende auf ein Drittel).
        if row["amount_input_mode"] == "quantity_unit_price" and row["unit_price_decimal"]:
            fields["unit_price_decimal"] = _fraction_text(Fraction(row["unit_price_decimal"]) * Fraction(conversion["factor"]))
    else:
        fields["quantity_decimal"] = conversion["quantity"]
        fields["unit_price_decimal"] = conversion["unit_price"]
    return fields


def record_securities_statement_stock_splits_v1(canonical_path: str | Path, data_space_path: str | Path, context_value: Any,
                                                trusted_review: Mapping[str, Any], recorded_at_utc: str, confirmed: bool) -> dict[str, Any]:
    """Uebernimmt die Splits der Mitteilungen in den Split-Speicher und stellt split-bereinigt gebuchte Vorgaenge davor auf die
    Stueckzahl und den Kurs ihres Belegs um (#451, rc.372). Gewinne, Einstand und Bestand bleiben: Der FIFO-Stand teilt die
    Lots am Stichtag, statt sie schon in neuen Stuecken zu fuehren.

    Erst der Split, dann je Vorgang eine Korrektur ueber den Weg der Data-App (Entwurf, Pruefung, Bestaetigung, Buchen,
    Belegangaben ziehen mit) - Abgaenge zuerst, damit der Bestand in jedem Zwischenschritt reicht. Bricht ein Schritt ab,
    bleibt das Erledigte gebucht; eine neue Pruefung zeigt den Rest."""
    context = _context(context_value)
    if not isinstance(trusted_review, Mapping) or trusted_review.get("adapter_id") not in ADAPTERS:
        _abort("securities_statement_review_invalid")
    body = {key: value for key, value in trusted_review.items() if key != "review_fingerprint"}
    if trusted_review.get("review_fingerprint") != _sha(body):
        _abort("securities_statement_review_invalid")
    if confirmed is not True:
        _abort("securities_statement_confirmation_invalid")
    splits = list(trusted_review.get("new_stock_splits") or [])
    conversions = list(trusted_review.get("stock_split_conversions") or [])
    if not splits and not conversions:
        _abort("securities_statement_review_invalid")
    if not isinstance(recorded_at_utc, str) or _UTC.fullmatch(recorded_at_utc) is None:
        _abort("securities_statement_review_invalid")
    from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, carry_activity_reference_v1
    from migrations.reference.desktop_activity_draft_v1 import (
        DesktopActivityDraftV1Error, apply_desktop_activity_draft_v1, build_desktop_activity_draft_confirmation_v1,
        create_desktop_activity_draft_v1, validate_desktop_activity_draft_v1,
    )
    from migrations.reference.stock_split_v1 import StockSplitV1Error, record_stock_split_v1
    canonical, space = Path(canonical_path), Path(data_space_path)
    clock = datetime.strptime(recorded_at_utc, "%Y-%m-%dT%H:%M:%SZ")
    tick = lambda seconds: (clock + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recorded = 0
    split_provenance = []
    for split in splits:
        try:
            result = record_stock_split_v1(space, context, split["asset_id"], None, split["effective_local_date"], split["ratio_numerator"],
                                           split["ratio_denominator"], split["note"], recorded_at_utc, True)
        except StockSplitV1Error:
            _abort("securities_statement_stock_split_blocked")
        recorded += result["status"] == "recorded"
        if split.get("readers") and result["status"] in ("recorded", "unchanged"):
            split_provenance.append({"booking_kind": "stock_split", "booking_key": result["split_ref"], "readers": list(split["readers"])})
    provenance = _record_provenance(space, context, split_provenance, recorded_at_utc) if split_provenance else "not_applicable"
    binding = read_desktop_product_asset_activity_binding_v1(space, context)
    order = {"sell": 0, "dividend": 1, "buy": 2}
    converted, carried = 0, 0
    for step, conversion in enumerate(sorted(conversions, key=lambda item: (order[item["kind"]], item["local_date"], item["event_ref"])), 1):
        try:
            connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True); connection.row_factory = sqlite3.Row
            try:
                rows = [dict(row) for row in connection.execute("SELECT * FROM current_asset_activity_event WHERE event_ref=?", (conversion["event_ref"],))]
            finally:
                connection.close()
        except sqlite3.Error:
            _abort("securities_statement_review_invalid")
        # Die Buchung muss noch so stehen wie geprueft: gleiche Kennung, Belegstueckzahl mal Faktor.
        booked_key = "eligible_quantity_decimal" if conversion["kind"] == "dividend" else "quantity_decimal"
        document = conversion["eligible_quantity"] if conversion["kind"] == "dividend" else conversion["quantity"]
        if len(rows) != 1 or rows[0]["event_type"] != conversion["kind"] or \
                Fraction(rows[0][booked_key]) != Fraction(document) * Fraction(conversion["factor"]):
            _abort("securities_statement_review_invalid")
        row = rows[0]
        base = step * 5
        try:
            draft = create_desktop_activity_draft_v1(space, context, row["portfolio_id"], "correction", "correct",
                                                     _conversion_fields(row, conversion), tick(base), predecessor_event_ref=row["event_ref"])
            ready = validate_desktop_activity_draft_v1(canonical, space, context, draft["trusted_draft"]["draft_ref"], 1, tick(base + 1))
            if ready["trusted_draft"]["draft_state"] != "validated_ready":
                _abort("securities_statement_stock_split_blocked")
            confirmation = build_desktop_activity_draft_confirmation_v1(
                ready["trusted_draft"], context, "adc_" + hashlib.sha256(f"stock-split-conversion|{row['event_ref']}|{recorded_at_utc}".encode()).hexdigest()[:32],
                tick(base + 2), tick(base + 2), tick(base + 600))
            applied = apply_desktop_activity_draft_v1(canonical, space, context, draft["trusted_draft"]["draft_ref"], confirmation, tick(base + 3))
        except DesktopActivityDraftV1Error:
            _abort("securities_statement_stock_split_blocked")
        successor = (applied.get("trusted_draft") or {}).get("event", {}).get("event_ref")
        if not isinstance(successor, str):
            _abort("securities_statement_stock_split_blocked")
        converted += 1
        try:
            carried += carry_activity_reference_v1(space, context, row["event_ref"], successor, tick(base + 4))["status"] == "carried"
        except AssetActivityReferenceV1Error:
            pass   # gebucht ist gebucht; die Belegangaben lassen sich nachtragen (#458)
    return {"recorded_split_count": recorded, "converted_count": converted, "reference_carried_count": carried, "provenance_status": provenance,
            "provider_access": False, "network_access": False}


# --- Krypto-Exporte (#454) ------------------------------------------------------------------------------------------------

def _crypto_events(data_space: Path, context: DesktopProductAssetActivityContextV1) -> list[dict[str, Any]]:
    binding = read_desktop_product_asset_activity_binding_v1(data_space, context)
    if binding["status"] == "absent":
        return []
    try:
        connection = sqlite3.connect(f"file:{binding['ledger_path']}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in connection.execute(
                "SELECT event_ref, account_id, related_account_id, asset_id, event_type, local_date, local_time, effective_at_utc, quantity_decimal, "
                "unit_price_decimal, monetary_fee_decimal, asset_fee_quantity_decimal FROM current_asset_activity_event")]
        finally:
            connection.close()
    except sqlite3.Error:
        _abort("securities_statement_review_invalid")


def _crypto_tickers(catalog: Mapping[str, Any]) -> dict[str, str | None]:
    """Kuerzel -> Asset der Klasse Krypto: das erste Wort des Namens ("BTC (Bitcoin)"); mehrdeutig = fehlt.

    Seit rc.361 (#537) auch das Kuerzel in Klammern ("Bitcoin (BTC)"), damit ein vorhandener, noch nie gehaltener Coin nicht
    doppelt angelegt wird - nachrangig: Ein Kuerzel, das schon ein erstes Wort traegt, bleibt bei dessen Asset, und ein Klammer-
    Kuerzel zweier Coins zaehlt fuer keinen. Am Namen wird nichts geaendert (eine Aenderung entwertete die Kursfreigaben)."""
    found: dict[str, list[str]] = {}
    bracketed: dict[str, list[str]] = {}
    for row in catalog["assets"]:
        if row.get("asset_type") == "crypto":
            word = re.sub(r"[^A-Z0-9]", "", (row["label"].split() or [""])[0].upper())
            if word:
                found.setdefault(word, []).append(row["asset_id"])
            for token in re.findall(r"\(([A-Za-z0-9]{2,10})\)", row["label"]):
                bracketed.setdefault(token.upper(), []).append(row["asset_id"])
    tickers = {ticker: ids[0] if len(ids) == 1 else None for ticker, ids in found.items()}
    for ticker, ids in bracketed.items():
        if ticker not in tickers:
            tickers[ticker] = ids[0] if len(set(ids)) == 1 else None
    return tickers


def _suggest_crypto(canonical: Path, context: DesktopProductAssetActivityContextV1, parsed: Mapping[str, Any]) -> dict[str, Any]:
    """Je Wallet ein Kontovorschlag: zuerst das Konto, auf dem Kennungen dieses Wallets gebucht sind, sonst nach Institut und Name."""
    catalog = read_desktop_product_per_asset_catalog_v1(canonical, context)
    institutions = _account_institutions(canonical)
    resting = _resting_accounts(canonical, context)
    wallets = [row for row in catalog["accounts"] if row["account_type"] == "crypto_wallet" and row["account_id"] not in resting]
    data_space = canonical.parent
    events = _crypto_events(data_space, context)
    references = read_activity_references_v1(data_space, context, None)["references"]
    entries = crypto.wallet_entries_v1(parsed)
    learned = crypto.learn_wallet_accounts_v1(parsed, events, references)
    known = {row["account_id"] for row in wallets}
    suggested = crypto.suggest_crypto_accounts_v1(wallets, institutions, entries, {key: value for key, value in learned.items() if value in known})
    choices = [{"account_ref": "acr_" + _sha([context.data_space_id, row["account_id"]])[:16], "label": row["label"], "institution": institutions.get(row["account_id"], "")} for row in wallets]
    trusted = {choice["account_ref"]: row["account_id"] for choice, row in zip(choices, wallets)}
    by_account = {account_id: ref for ref, account_id in trusted.items()}
    depots = [{key: entry[key] for key in ("depot_handle", "depot_mask", "profile", "profile_label", "candidate_count")}
              | {"suggested_account_ref": by_account.get(suggested.get(handle)), "learned": handle in learned} for handle, entry in entries.items()]
    return {"public": {"depots": sorted(depots, key=lambda item: item["depot_mask"]), "accounts": choices, "internal_id_exposed": False},
            "trusted_account_refs": trusted}


def _review_crypto(canonical: Path, data_space: Path, context: DesktopProductAssetActivityContextV1, parsed: Mapping[str, Any],
                   account_by_handle: Mapping[str, str], scope: Mapping[str, Any] | None = None, scope_skip: bool = False) -> dict[str, Any]:
    catalog = read_desktop_product_per_asset_catalog_v1(canonical, context)
    accounts = {row["account_id"]: row for row in catalog["accounts"]}
    for account_id in account_by_handle.values():
        if accounts.get(account_id, {}).get("account_type") != "crypto_wallet":
            _abort("securities_statement_account_invalid")
    if len({accounts[value]["portfolio_id"] for value in account_by_handle.values()}) > 1:
        _abort("securities_statement_account_invalid")
    assets = {row["asset_id"]: row for row in catalog["assets"]}
    candidates = [dict(candidate) for candidate in parsed.get("candidates", [])]
    events = _crypto_events(data_space, context)
    references = read_activity_references_v1(data_space, context, None)["references"]
    results = crypto.review_crypto_operations_v1(candidates, events, references, _crypto_tickers(catalog), account_by_handle)
    _hold_inactive_readers(data_space, context, {accounts[value]["portfolio_id"] for value in account_by_handle.values()}, candidates, results)
    scope = scope or {"mode": "all", "from": None, "through": None}
    window_counts = _apply_window(scope, [(candidate["local_date"], results[candidate["candidate_ordinal"]]) for candidate in candidates], WINDOW_HIDDEN)
    held = _hold_out_of_scope(data_space, context, {accounts[value]["portfolio_id"] for value in account_by_handle.values()}, candidates, results, assets,
                              scope_skip)
    confirmed = read_securities_statement_confirmations_v1(data_space).get(parsed["adapter_id"])
    # Ein Leser ohne Pruefstand (experimentell, #514): Jeder neue Vorgang ist juenger als der Pruefstand.
    through = max((ADAPTERS[parsed["adapter_id"]]["validated"] or {}).get("through", ""), confirmed["through"] if confirmed else "")
    beyond = 0
    rows = []
    for candidate in candidates:
        result = results[candidate["candidate_ordinal"]]
        if result["status"] == "new" and candidate["local_date"] > through:
            result["notes"] = list(result["notes"]) + [BEYOND_VALIDATION_NOTE]; beyond += 1
        label = lambda key: accounts[candidate[key]]["label"] if candidate.get(key) else None
        rows.append({"candidate_ordinal": candidate["candidate_ordinal"], "file_name": candidate["file_name"], "kind": candidate["kind"],
                     "open_kind": candidate.get("open_kind"), "isin": "", "security_name": candidate["ticker"], "currency": None, "domain": "crypto",
                     "asset_label": assets[candidate["asset_id"]]["label"] if candidate.get("asset_id") else None,
                     "account_label": label("account_id"), "related_account_label": label("related_account_id"),
                     "local_date": candidate["local_date"], "local_time": candidate["local_time"], "quantity": candidate.get("quantity"),
                     "eligible_quantity": None, "unit_price": candidate.get("unit_price"), "gross_amount": candidate.get("gross_amount"),
                     "fee_amount": candidate.get("fee_amount"), "asset_fee": candidate.get("asset_fee"),
                     "status": result["status"], "status_label": _window_label(CRYPTO_STATUS_LABELS, result),
                     "differences": result["differences"], "notes": result["notes"], "editable": _crypto_editable(candidate, result)})
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    new = [candidate for candidate in candidates if results[candidate["candidate_ordinal"]]["status"] == "new"]
    portfolio_ids = {accounts[value]["portfolio_id"] for value in account_by_handle.values()}
    trusted = {"adapter_id": parsed["adapter_id"], "portfolio_id": next(iter(portfolio_ids)) if portfolio_ids else None,
               "new_candidates": [{key: candidate.get(key) for key in ("candidate_key", "kind", "asset_id", "account_id", "related_account_id", "local_date", "local_time",
                                                                       "time_zone", "quantity", "unit_price", "fee_amount", "gross_amount", "asset_fee", "transaction_id", "address",
                                                                       "readers")}
                                  for candidate in new]}
    # Offene Vorgaenge, die sich im Transaktionseditor vorbelegen lassen ("Im Editor öffnen"): Konto und Coin bleiben serverseitig.
    trusted["open_rows"] = [_crypto_open_row(candidate) for candidate in candidates if _crypto_editable(candidate, results[candidate["candidate_ordinal"]])]
    trusted["reference_backfill"] = _reference_backfill(candidates, results, references)
    trusted["scope_skip"] = scope_skip
    trusted["scope_pending"] = held["pending"]
    trusted["review_fingerprint"] = _sha(trusted)
    return {"public_review": {"securities_statement_review_version": VERSION, "adapter_id": parsed["adapter_id"],
                              "adapter": {**_adapter_public(parsed["adapter_id"]), "confirmed": confirmed, "effective_through": through},
                              "beyond_validation_count": beyond, "rows": rows, "counts": counts, "new_count": len(new),
                              "window": scope, "out_of_window_counts": window_counts, "out_of_window_count": sum(window_counts.values()),
                              "documents": parsed.get("documents", []), "row_reasons": parsed.get("row_reasons", []),
                              "missing_assets": _missing_assets(rows, "crypto"),
                              "reference_backfill_count": len(trusted["reference_backfill"]),
                              "document_counts": parsed.get("counts", {}), "canonical_write": False, "network_access": False, "internal_id_exposed": False,
                              **_scope_public(held, scope_skip)},
            "trusted_review": trusted}


# Was "Im Editor öffnen" anbietet: offene Ein- und Ausgaenge (auch Ledger-Solana) und BSDEX-Auftraege ohne Ausfuehrung bzw.
# Handel ohne Betrag - nicht Staub, reine Gebuehren, Tausch oder Vorgaenge ohne Coin bzw. Konto.
# Seit rc.376 auch BSDEX-Orders, bei denen Laden nicht hilft (Betrag oder Menge passen nicht, Zuordnung nicht eindeutig): ohne Betrag
# vorbelegt - den traegt der Eigentuemer nach Pruefung der Belege ein (beide Betraege stehen im Grund).
# BSDEX-Auftraege ohne "Finalisiert am" (#545): Der Export nennt nur den je Order gerundeten Betrag; der Editor belegt ihn nicht vor -
# gebucht wird nur der genaue Betrag (Festlegung 26.10.2026). Die Betraege stehen im Grund.
CRYPTO_PREFILL_WITHOUT_AMOUNT = ("order_time",)
CRYPTO_EDITABLE_KINDS = ("transfer_in", "transfer_out", "direction_unknown", "ledger_solana", "order_time", "amount_mismatch", "export_amount_differs",
                         "executions_quantity_differs", "executions_ambiguous")


def _crypto_open_row(candidate: Mapping[str, Any]) -> dict[str, Any]:
    row = {key: candidate.get(key) for key in ("candidate_ordinal", "open_kind", "direction", "side", "asset_id", "account_id", "local_date",
                                               "local_time", "time_zone", "quantity", "asset_fee", "gross_amount", "fee_amount")}
    gross, quantity = _dec(candidate.get("gross_amount")), _dec(candidate.get("quantity"))
    row["unit_price"] = _plain((gross / quantity).quantize(Decimal("1e-12"))) if gross and quantity else None   # Auftrag: Kurswert / Menge
    if candidate.get("open_kind") in CRYPTO_PREFILL_WITHOUT_AMOUNT:
        row.update(gross_amount=None, fee_amount=None, unit_price=None)
    return row


def _crypto_editable(candidate: Mapping[str, Any], result: Mapping[str, Any]) -> bool:
    return (result["status"] == "open" and candidate.get("open_kind") in CRYPTO_EDITABLE_KINDS
            and bool(candidate.get("asset_id")) and bool(candidate.get("account_id")))


def _import_key(trusted_review: Mapping[str, Any]) -> str:
    prefix = "krypto-belege-" if trusted_review["adapter_id"] == "crypto_exports_v1" else "wp-belege-"
    return prefix + _sha([trusted_review["adapter_id"], trusted_review["portfolio_id"]])[:16]


def _row_key(candidate: Mapping[str, Any]) -> str:
    return "beleg-" + _sha(candidate["candidate_key"])[:20]


def record_statement_import_references_v1(data_space_path: str | Path, context_value: Any, trusted_review: Mapping[str, Any], recorded_at_utc: str) -> dict[str, Any]:
    """Nach dem Buchen: Kennung (Transaktions-ID, Hash, Order- oder Vorgangsnummer) und Adresse der Gegenseite der gebuchten
    Vorgaenge in den Beleg-Speicher (#458). Nur fuer Buchungen, die es gibt, und nur zeichenweise gueltige Angaben."""
    context = _context(context_value)
    if not isinstance(trusted_review, Mapping) or not trusted_review.get("new_candidates") or trusted_review.get("adapter_id") not in ADAPTERS:
        _abort("securities_statement_review_invalid")
    body = {key: value for key, value in trusted_review.items() if key != "review_fingerprint"}
    if trusted_review.get("review_fingerprint") != _sha(body):
        _abort("securities_statement_review_invalid")
    data_space = Path(data_space_path)
    booked = {event["event_ref"] for event in _crypto_events(data_space, context)}
    import_key = _import_key(trusted_review)
    entries = []
    for candidate in trusted_review["new_candidates"]:
        identifier = candidate.get("transaction_id") or candidate.get("order_ref") or None
        address = candidate.get("address") or None
        identifier = identifier if identifier and TOKEN.fullmatch(identifier) else None
        address = address if address and TOKEN.fullmatch(address) else None
        event_ref = asset_activity_csv_event_ref_v1(context, import_key, _row_key(candidate))
        if (identifier or address) and event_ref in booked:
            entries.append({"event_ref": event_ref, "transaction_id": identifier, "counterparty_address": address, "note": None})
    if not entries:
        return {"recorded_count": 0}
    # Hat die Buchung schon Angaben (von der stornierten Vorgaengerin, #439), bleiben deren Notiz und, wo die Quelle nichts sagt, ihre Werte.
    current = read_activity_references_v1(data_space, context, [entry["event_ref"] for entry in entries])["references"]
    for entry in entries:
        before = current.get(entry["event_ref"]) or {}
        entry["transaction_id"] = entry["transaction_id"] or before.get("transaction_id")
        entry["counterparty_address"] = entry["counterparty_address"] or before.get("counterparty_address")
        entry["note"] = before.get("note")
    result = record_activity_references_v1(data_space, context, entries, "statement_source", recorded_at_utc, True)
    return {"recorded_count": result["written_count"]}


def _reader_intents(context: DesktopProductAssetActivityContextV1, trusted_review: Mapping[str, Any]) -> list[dict[str, Any]]:
    import_key = _import_key(trusted_review)
    return [{"booking_kind": "asset_event", "booking_key": asset_activity_csv_event_ref_v1(context, import_key, _row_key(candidate)),
             "readers": list(candidate["readers"])} for candidate in trusted_review["new_candidates"] if candidate.get("readers")]


def record_statement_reader_intents_v1(data_space_path: str | Path, context_value: Any, trusted_review: Mapping[str, Any], recorded_at_utc: str) -> dict[str, Any]:
    """Beim Vorbereiten der Buchung (CSV-Plan): je neuem Vorgang die Leser, die ihn gelesen haben, als Absicht (rc.378, #486).
    Erfasst wurden sie beim Lesen (in der Pruefung, durch ihren Abdruck geschuetzt); nach jedem Buchen - auch einem fortgesetzten
    Import - uebernimmt der Abgleich sie fuer das, was gebucht ist."""
    context = _context(context_value)
    if not isinstance(trusted_review, Mapping) or not trusted_review.get("new_candidates") or trusted_review.get("adapter_id") not in ADAPTERS:
        _abort("securities_statement_review_invalid")
    body = {key: value for key, value in trusted_review.items() if key != "review_fingerprint"}
    if trusted_review.get("review_fingerprint") != _sha(body):
        _abort("securities_statement_review_invalid")
    result = record_reader_provenance_intents_v1(Path(data_space_path), context, _reader_intents(context, trusted_review), recorded_at_utc)
    return {"intent_count": result["written_count"]}


def record_statement_reader_provenance_v1(data_space_path: str | Path, context_value: Any, trusted_review: Mapping[str, Any], recorded_at_utc: str) -> dict[str, Any]:
    """Nach dem Buchen: die Herkunft der gebuchten Vorgaenge dieser Pruefung aus ihren Absichten uebernehmen (rc.378, #486). Fehlt die
    Absicht (etwa ein Plan von vor rc.378), wird sie aus der Pruefung nachgeholt - die Leser wurden auch dort beim Lesen erfasst."""
    context = _context(context_value)
    if not isinstance(trusted_review, Mapping) or not trusted_review.get("new_candidates") or trusted_review.get("adapter_id") not in ADAPTERS:
        _abort("securities_statement_review_invalid")
    body = {key: value for key, value in trusted_review.items() if key != "review_fingerprint"}
    if trusted_review.get("review_fingerprint") != _sha(body):
        _abort("securities_statement_review_invalid")
    data_space = Path(data_space_path)
    intents = _reader_intents(context, trusted_review)
    record_reader_provenance_intents_v1(data_space, context, intents, recorded_at_utc)
    result = reconcile_reader_provenance_v1(data_space, context, recorded_at_utc, [entry["booking_key"] for entry in intents])
    return {"recorded_count": result["written_count"], "pending_count": result["pending_count"]}


def record_statement_reference_backfill_v1(data_space_path: str | Path, context_value: Any, trusted_review: Mapping[str, Any], recorded_at_utc: str,
                                          confirmed: bool) -> dict[str, Any]:
    """Kennungen gebuchter Vorgaenge aus den Belegen nachtragen (#458 Teil 3, #439): nur, was die Pruefung angeboten hat, und nur
    in Felder, die noch leer sind - steht inzwischen etwas darin, bleibt es. Herkunft "aus dem Auszug uebernommen"."""
    if confirmed is not True:
        _abort("securities_statement_confirmation_invalid")
    context = _context(context_value)
    if not isinstance(trusted_review, Mapping) or trusted_review.get("adapter_id") not in ADAPTERS:
        _abort("securities_statement_review_invalid")
    body = {key: value for key, value in trusted_review.items() if key != "review_fingerprint"}
    if trusted_review.get("review_fingerprint") != _sha(body):
        _abort("securities_statement_review_invalid")
    offered = trusted_review.get("reference_backfill") or []
    if not offered:
        return {"recorded_count": 0, "kept_count": 0}
    data_space = Path(data_space_path)
    current = read_activity_references_v1(data_space, context, [entry["event_ref"] for entry in offered])["references"]
    entries, kept = [], 0
    for entry in offered:
        now = current.get(entry["event_ref"]) or {}
        identifier = now.get("transaction_id") or entry["transaction_id"]
        address = now.get("counterparty_address") or entry["counterparty_address"]
        if identifier == now.get("transaction_id") and address == now.get("counterparty_address"):
            kept += 1
            continue
        entries.append({"event_ref": entry["event_ref"], "transaction_id": identifier, "counterparty_address": address, "note": now.get("note")})
    if not entries:
        return {"recorded_count": 0, "kept_count": kept}
    result = record_activity_references_v1(data_space, context, entries, "statement_source", recorded_at_utc, True)
    return {"recorded_count": result["written_count"], "kept_count": kept}


def build_securities_statement_csv_v1(canonical_path: str | Path, context_value: Any, trusted_review: Mapping[str, Any]) -> bytes:
    """Neue Vorgaenge als Zeilen des Aktivitaeten-CSV-Imports: Konto und Asset als dessen eindeutige Quellschluessel,
    damit die Zuordnung ohne Rueckfrage steht. Eine Abrechnung ergibt immer denselben Zeilenschluessel."""
    context = _context(context_value)
    if not isinstance(trusted_review, Mapping) or not trusted_review.get("new_candidates"):
        _abort("securities_statement_review_invalid")
    body = {key: value for key, value in trusted_review.items() if key != "review_fingerprint"}
    if trusted_review.get("review_fingerprint") != _sha(body):
        _abort("securities_statement_review_invalid")
    # Pflichtwahl (#551): Solange Vorgaenge einer nicht gewaehlten Klasse ohne Entscheidung sind, wird nichts gebucht.
    if trusted_review.get("scope_pending"):
        _abort("securities_statement_scope_choice_required")
    catalog = read_desktop_product_per_asset_catalog_v1(Path(canonical_path), context)
    asset_keys = _source_keys("asset", catalog["assets"])
    account_keys = _source_keys("account", [row for row in catalog["accounts"] if row["portfolio_id"] == trusted_review["portfolio_id"]])
    assets = {row["asset_id"]: row for row in catalog["assets"]}
    if any(candidate["account_id"] not in account_keys or (candidate.get("related_account_id") and candidate["related_account_id"] not in account_keys)
           for candidate in trusted_review["new_candidates"]):
        _abort("securities_statement_account_invalid")
    import_key = _import_key(trusted_review)
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for candidate in trusted_review["new_candidates"]:
        asset = assets.get(candidate["asset_id"])
        if asset is None or asset["price_currency"] != "EUR":
            _abort("securities_statement_review_invalid")
        row = {name: "" for name in HEADERS}
        fee = Decimal(candidate.get("fee_amount") or 0)
        row.update(format_version=FORMAT_VERSION, import_key=import_key, row_key=_row_key(candidate),
                   event_type=candidate["kind"], asset_key=asset_keys[candidate["asset_id"]], account_key=account_keys[candidate["account_id"]],
                   event_time_evidence="exact", local_date=candidate["local_date"], time_zone=TIME_ZONE, price_currency="EUR",
                   original_acquired_time_evidence="not_applicable", movement_context_code="not_applicable", basis_evidence_mode="not_applicable")
        if trusted_review["adapter_id"] == "crypto_exports_v1":
            # Krypto: exakte Zeit in der Zeitzone des Exports. Transfer: angekommene Menge, Netzwerkgebuehr in Coin am Quellkonto.
            row.update(local_time=candidate["local_time"], time_zone=candidate["time_zone"], quantity_decimal=_plain(Decimal(candidate["quantity"])))
            if candidate["kind"] == "transfer":
                fee = candidate.get("asset_fee")
                row.update(related_account_key=account_keys[candidate["related_account_id"]], amount_input_mode="not_applicable",
                           fee_role="asset_quantity" if fee else "none", fee_currency="ASSET" if fee else "", asset_fee_quantity_decimal=_plain(Decimal(fee)) if fee else "")
            else:
                money = Decimal(candidate.get("fee_amount") or 0)
                row.update(amount_input_mode="quantity_unit_price", basis_evidence_mode="derived_trade" if candidate["kind"] == "buy" else "not_applicable",
                           unit_price_decimal=_plain(Decimal(candidate["unit_price"])), fee_role="monetary" if money else "none",
                           fee_currency="EUR" if money else "", monetary_fee_decimal=_plain(money) if money else "")
        elif asset["asset_type"] == "fx":
            # Kauf/Verkauf mit Kurs = EUR-Gegenwert / Betrag; der Zugang aus Ertrag traegt
            # den EUR-Wert als Anschaffungskosten (Kontext "Sonstiges", in der Maske "Zufluss aus Ertrag").
            # Die Uhrzeit ist die Ordnungszeit des Lesers (12:00, am selben Tag Zugaenge zuerst), der Beleg nennt keine.
            row.update(local_time=candidate.get("local_time") or "12:00:00", fee_role="none", quantity_decimal=_plain(Decimal(candidate["quantity"])))
            if candidate["kind"] == "deposit":
                row.update(amount_input_mode="gross_total", basis_evidence_mode="provided_basis", gross_amount_decimal=_plain(Decimal(candidate["gross_amount"])),
                           movement_context_code="other", original_acquired_time_evidence="exact", original_acquired_local_date=candidate["local_date"],
                           original_acquired_local_time=row["local_time"], original_acquired_time_zone=TIME_ZONE)
            else:
                row.update(amount_input_mode="quantity_unit_price", basis_evidence_mode="derived_trade" if candidate["kind"] == "buy" else "not_applicable",
                           unit_price_decimal=_plain(Decimal(candidate["unit_price"])))
        elif candidate["kind"] == "dividend":
            # Dividendenbelege nennen keine Uhrzeit; gebucht wird nur das Datum, statt eine Uhrzeit zu erfinden.
            row.update(event_time_evidence="date_only", local_time="", fee_role="none", amount_input_mode="gross_total",
                       eligible_quantity_decimal=_plain(Decimal(candidate["eligible_quantity"])), gross_amount_decimal=_plain(Decimal(candidate["gross_amount"])))
        else:
            row.update(local_time=candidate.get("local_time") or "12:00:00", amount_input_mode="quantity_unit_price",
                       basis_evidence_mode="derived_trade" if candidate["kind"] == "buy" else "not_applicable",
                       quantity_decimal=_plain(Decimal(candidate["quantity"])), unit_price_decimal=_plain(Decimal(candidate["unit_price"])),
                       fee_role="monetary" if fee else "none", fee_currency="EUR" if fee else "", monetary_fee_decimal=_plain(fee) if fee else "")
        writer.writerow(row)
    return output.getvalue().encode("utf-8")


__all__ = [
    "ADAPTER_FIELDS", "ADAPTERS", "ADVANCE_LUMP_SUM_STATUS_LABELS", "WINDOW_MODES", "BEYOND_VALIDATION_NOTE", "COMBINED_NEW_NOTE", "SEPARATE_EXECUTIONS_NOTE",
    "record_securities_statement_advance_lump_sums_v1", "latest_booked_dates_v1", "CONFIRMATION_AREA", "CONFIRMATION_FILE", "FX_ORDER_NOTE", "FX_UNCHECKED_NOTE", "REASONS", "STATUS_LABELS",
    "read_securities_statement_confirmations_v1", "record_securities_statement_confirmation_v1", "record_statement_import_references_v1",
    "record_statement_reader_intents_v1", "record_statement_reader_provenance_v1", "SecuritiesStatementImportV1Error", "build_securities_statement_csv_v1",
    "detect_securities_statement_adapters_v1", "list_securities_statement_adapters_v1", "parse_securities_statement_set_v1",
    "record_statement_reference_backfill_v1",
    "review_securities_statement_import_v1", "securities_statement_import_v1_error_codes", "suggest_securities_statement_accounts_v1",
]
