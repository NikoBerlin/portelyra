"""Cash statement import (#184): modular adapters, booked recognition, coverage proposal.

Adapters are built-in pure parsers selected from a registry (dropdown in the Data UI).
They receive file bytes and return movement candidates: interest, deposit or withdrawal,
plus optional running balances and a statement summary. Nothing here writes directly:
every fact goes through the existing reviewed Cash coverage commands (preview,
one-use confirmation, atomic apply) in one process.

Interest is gross income and, because it increases the Cash balance, also a deposit
classified as ``income_receipt``. Taxes and fees are withdrawals. Date-only statements
receive a deterministic local time (12:00 plus the order within the day) so that the
exact-time Cash contract holds without inventing a different day.
"""
from __future__ import annotations

import csv
import functools
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import xml.etree.ElementTree as ElementTree
import zipfile
from zoneinfo import ZoneInfo

from migrations.reference import statement_reader_plugins_v1 as reader_plugins
from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, record_reader_provenance_v1
from migrations.reference.desktop_cash_coverage_v1 import (
    STORE_AREA, STORE_NAME, apply_desktop_cash_coverage_command_v1, apply_desktop_cash_coverage_reviewed_batch_v1,
    build_desktop_cash_coverage_confirmation_v1, preview_desktop_cash_coverage_command_v1,
    read_desktop_cash_coverage_exchange_projection_v1, read_desktop_cash_coverage_reviewed_import_state_v1,
)

VERSION = 1
MAX_BYTES = 20 * 1024 * 1024
# Ein ganzer Auszugsordner auf einmal; mehr als das ist ein Bedienfehler.
MAX_STATEMENTS = 200
TIME_ZONE = "Europe/Berlin"
CENT = Decimal("0.01")


class CashStatementImportV1Error(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _abort(code: str) -> None:
    raise CashStatementImportV1Error(code)


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _cents(text: Any) -> Decimal | None:
    if text is None or str(text).strip() == "":
        return None
    raw = str(text).strip().replace(" ", "").replace(" ", "").replace("€", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    rounded = value.quantize(CENT)
    # Spreadsheets store cents as binary floats; anything beyond float noise is not a cent amount.
    if abs(value - rounded) > Decimal("0.000001"):
        return None
    return rounded


def _german_amount(text: str) -> Decimal | None:
    """Immer deutsches Format: "-2.000" sind zweitausend, nicht zwei."""
    raw = (text or "").replace("€", "").replace("\xa0", "").replace(" ", "").strip()
    if not raw:
        return None
    return _cents(raw.replace(".", "").replace(",", "."))


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in {"-0", ""} else text


# ---------------------------------------------------------------- xlsx reader
def _xlsx_rows(source: bytes) -> list[list[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(source))
        sheet_name = sorted(name for name in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name))[0]
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(node.itertext()) for node in root if node.tag.endswith("}si")]
        root = ElementTree.fromstring(archive.read(sheet_name))
    except (zipfile.BadZipFile, IndexError, KeyError, ElementTree.ParseError):
        _abort("cash_statement_source_invalid")
    rows: list[list[str]] = []
    for row in (node for node in root.iter() if node.tag.endswith("}row")):
        values: dict[int, str] = {}
        for cell in (node for node in row if node.tag.endswith("}c")):
            reference = cell.get("r", "")
            letters = re.match(r"[A-Z]+", reference)
            if letters is None:
                continue
            column = 0
            for char in letters.group(0):
                column = column * 26 + ord(char) - 64
            kind = cell.get("t", "")
            if kind == "inlineStr":
                text = "".join(cell.itertext())
            else:
                value = next((node.text for node in cell if node.tag.endswith("}v")), None)
                text = shared[int(value)] if kind == "s" and value is not None else (value or "")
            values[column - 1] = text
        rows.append([values.get(index, "") for index in range(max(values) + 1)] if values else [])
    return rows


def _pdf_text(source: bytes, file_name: str) -> list[str]:
    """Local text extraction only: poppler's pdftotext, no network, original file untouched. Die Ablage nutzt sie fuer ihre
    Vorschlaege; die Leser bekommen denselben Text ueber den Plugin-Aufruf."""
    if not file_name.lower().endswith(".pdf"):
        return source.decode("utf-8", errors="replace").splitlines()
    return list(_pdf_lines(source))


@functools.lru_cache(maxsize=512)
def _pdf_lines(source: bytes) -> tuple[str, ...]:
    with tempfile.TemporaryDirectory(prefix="cash-statement-pdf-") as temporary:
        path = Path(temporary) / "statement.pdf"
        path.write_bytes(source)
        try:
            completed = subprocess.run(["pdftotext", "-layout", "-nopgbrk", str(path), "-"], capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            _abort("cash_statement_pdf_tool_missing")
        if completed.returncode != 0 or not completed.stdout.strip():
            _abort("cash_statement_source_invalid")
        return tuple(completed.stdout.decode("utf-8", errors="replace").splitlines())


def _named_rows(source: bytes) -> list[dict[str, str]]:
    """Tolerant reader: BOM or none, semicolon or comma, quoted fields, blank lines."""
    text = source.decode("utf-8-sig", errors="replace")
    header = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = ";" if header.count(";") >= header.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        _abort("cash_statement_header_invalid")
    names = [(name or "").strip().lstrip("\ufeff") for name in reader.fieldnames]
    return [{name: (value or "").strip() for name, value in zip(names, row.values())} for row in reader if any((value or "").strip() for value in row.values())]


def _exchange_result(candidates: list[dict[str, Any]], diagnostics: list[dict[str, Any]],
                     opening: Decimal | None = None, closing: Decimal | None = None) -> dict[str, Any]:
    if not candidates:
        _abort("cash_statement_header_invalid")
    days = sorted(row["local_date"] for row in candidates)
    summary = {"opening_balance_decimal": opening, "closing_balance_decimal": closing, "period_from": days[0], "period_to": days[-1]}
    return {"candidates": candidates, "diagnostics": diagnostics,
            "summary": {key: (_plain(value) if isinstance(value, Decimal) else value) for key, value in summary.items()}}


def _exchange_row(ordinal: int, local_date: str, cash: Decimal, text: str, balance: Decimal | None = None) -> dict[str, Any]:
    return {"source_row_ordinal": ordinal, "local_date": local_date, "kind": "deposit" if cash > 0 else "withdrawal",
            "amount_decimal": _plain(abs(cash)), "balance_after_decimal": None if balance is None else _plain(balance), "text": text}


# Die Leser der Institute liegen seit rc.373 als Plugins unter plugins/readers/ (#486, Vertrag statement-reader-plugin/v1) und
# laufen ausschliesslich abgeschottet. Welche es gibt, sagt allein die Leserliste (#486): mitgelieferte nach Bezeichnung, danach die
# im Datenraum installierten. Ein Leser kann mehrere Belege zusammen lesen (combine_documents, etwa Export und Jahreshistorie),
# geprueft vom Kern.


def _plugin_documents(sources: Sequence[tuple[bytes, str]]) -> list[tuple[bytes, str, list[str] | None]]:
    """PDF-Text erzeugt der Kern wie bisher mit pdftotext; ein Leser startet selbst kein Programm."""
    return [(data, name, list(_pdf_lines(data)) if name.lower().endswith(".pdf") else None) for data, name in sources]


# Vorab gelesene Ergebnisse eines Stapels: ein abgeschotteter Aufruf je Leser und Stapel statt je Datei (rc.373). Schluessel sind
# Leser, Abdruck und Name; der Stapel leert den Vorrat wieder. Ergebnis und Reihenfolge der Fehler bleiben wie beim Einzelaufruf.
_PREFETCHED: dict[tuple[str, str, str], dict[str, Any]] = {}


def _prefetch_key(reader_id: str, source: bytes, file_name: str) -> tuple[str, str, str]:
    return reader_id, hashlib.sha256(source).hexdigest(), file_name


def _plugin_prefetch(reader_id: str, sources: Sequence[tuple[bytes, str]]) -> list[tuple[str, str, str]]:
    """Liest alle Belege eines Stapels in einem Aufruf. Ein Beleg, dessen PDF-Text fehlt, traegt seinen Code; ein Fehler der
    Sandbox gilt fuer jeden Beleg - so meldet der Stapel beim selben Beleg denselben Grund wie zuvor."""
    keys, documents, outcomes = [], [], {}
    for data, name in sources:
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
            continue
        key = _prefetch_key(reader_id, data, name)
        try:
            documents.append(_plugin_documents([(data, name)])[0]); keys.append(key)
        except CashStatementImportV1Error as error:
            outcomes[key] = {"ok": False, "code": error.code}
    if documents:
        try:
            outcomes.update(zip(keys, reader_plugins.run_reader_v1(reader_id, documents)))
        except reader_plugins.StatementReaderBlocked as error:
            outcomes.update((key, {"ok": False, "code": error.code}) for key in keys)
    _PREFETCHED.update(outcomes)
    return list(outcomes)


def cash_prefetch_v1(sources: Sequence[tuple[bytes, str]]) -> list[tuple[str, str, str]]:
    """Viele Dateien auf einmal (Eingang, Ablage-Vorschlag): je Leser ein abgeschotteter Aufruf fuer alle Dateien, die Endung und
    Erkennungsregeln erfuellen. Einzelaufrufe kosteten im Ablage-Vorschlag ein Vielfaches. Die
    Ergebnisse gelten nur bis ``cash_prefetch_release_v1``."""
    keys: list[tuple[str, str, str]] = []
    for adapter_id, adapter in ADAPTERS.items():
        if reader_plugins.reader_spec_v1(adapter_id) is None:
            continue
        chosen = [(data, name) for data, name in sources
                  if isinstance(name, str) and name.lower().endswith(adapter["extensions"]) and cash_reader_may_read_v1(adapter_id, [(data, name)])]
        if len(chosen) > 1:
            keys += _plugin_prefetch(adapter_id, chosen)
    return keys


def cash_prefetch_release_v1(keys: Sequence[tuple[str, str, str]]) -> None:
    for key in keys:
        _PREFETCHED.pop(key, None)


def _plugin_parse(reader_id: str, source: bytes, file_name: str) -> dict[str, Any]:
    """Ein Beleg durch den abgeschotteten Leser. Abbruchcodes des Lesers kommen unveraendert an; ein ungueltiges Ergebnis,
    eine fehlende Sandbox oder ein Absturz werden zu eigenen Codes - gebucht wird dann nichts."""
    result = _PREFETCHED.get(_prefetch_key(reader_id, source, file_name))
    try:
        if result is None:
            result = reader_plugins.run_reader_v1(reader_id, _plugin_documents([(source, file_name)]))[0]
        if not result["ok"]:
            _abort(result["code"])
        return reader_plugins.validate_cash_result_v1(result["value"])
    except reader_plugins.StatementReaderBlocked as error:
        _abort(error.code)


def _plugin_combine(reader_id: str, sources: Sequence[tuple[bytes, str]]) -> dict[str, Any]:
    """Mehrere Belege eines Instituts zusammen lesen (BSDEX). Ein ungueltiges Ergebnis oder eine fehlende Sandbox werden zu eigenen Codes."""
    try:
        result = reader_plugins.run_combine_documents_v1(reader_id, _plugin_documents(sources))
        if not result["ok"]:
            _abort(result["code"])
        return reader_plugins.validate_cash_combine_v1(result["value"])
    except reader_plugins.StatementReaderBlocked as error:
        _abort(error.code)


def _adapters() -> dict[str, dict[str, Any]]:
    specs = sorted(reader_plugins.reader_specs_v1("cash"), key=lambda spec: (spec.origin != "shipped", spec.label.casefold(), spec.reader_id))
    return {spec.reader_id: {"label": spec.label, "extensions": spec.extensions, "parse": functools.partial(_plugin_parse, spec.reader_id),
                             "known_limits": list(spec.known_limits),
                             **({"combine": functools.partial(_plugin_combine, spec.reader_id)} if spec.combine else {})} for spec in specs}


ADAPTERS: dict[str, dict[str, Any]] = _adapters()


def _refresh_adapters() -> None:
    """Installierte Cash-Leser des Datenraums (rc.381) aufnehmen bzw. entfernte streichen; die Liste bleibt dasselbe Objekt."""
    fresh = _adapters()
    ADAPTERS.clear()
    ADAPTERS.update(fresh)


reader_plugins.register_registry_refresher_v1(_refresh_adapters)


def _detection_texts(source: bytes, name: str) -> tuple[str, ...] | None:
    lowered = name.lower()
    try:
        if lowered.endswith(".pdf"):
            variants = ["\n".join(_pdf_lines(source))]
        elif lowered.endswith(".xlsx"):
            variants = ["\n".join("\t".join(row) for row in _xlsx_rows(source))]
        else:
            variants = [source.decode("utf-8-sig", errors="replace"), source.decode("cp1252", errors="replace")]
    except CashStatementImportV1Error:
        return None
    return reader_plugins.detection_texts_v1(variants)


def cash_reader_may_read_v1(adapter_id: str, sources: Sequence[tuple[bytes, str]]) -> bool:
    """Vorpruefung nach den Erkennungsregeln des Manifests, bevor ein Leser in der Erkennung laeuft. Die Regeln sind
    Mindestbedingungen, die der Leser selbst prueft: Ein Stapel kommt in Frage, wenn mindestens ein Beleg sie erfuellt. Ein
    unlesbarer Beleg entscheidet nicht vorab - das Lesen meldet ihn wie bisher."""
    if adapter_id not in ADAPTERS:
        return False
    if reader_plugins.reader_spec_v1(adapter_id) is None:
        return True
    for source, name in sources:
        texts = _detection_texts(source, name)
        if texts is None or reader_plugins.detection_passes_v1(adapter_id, texts):
            return True
    return False


# Pruefstand je Leser (#492/#465, wie bei den Wertpapierlesern #450): bis zu welchem Belegdatum das Format eines Lesers mit echten
# Auszuegen geprueft ist und wann. Er steht seit #486 im Manifest des Lesers ("format_checked"); ein Leser ohne Pruefstand ist mit
# echten Auszuegen noch nicht geprueft.


def cash_reader_validation_v1(adapter_id: str) -> dict[str, Any] | None:
    """Der Pruefstand eines Lesers ({"through", "checked_on"}), oder None, wenn sein Format noch nicht mit echten Auszuegen geprueft ist."""
    spec = reader_plugins.reader_spec_v1(adapter_id, "cash") if isinstance(adapter_id, str) else None
    return dict(spec.format_checked) if spec is not None and spec.format_checked else None


@reader_plugins.within_reader_session
def detect_cash_statement_adapters_v1(sources: Sequence[tuple[bytes, str]]) -> list[dict[str, Any]]:
    """Welche Quellen lesen diese Dateien? Nur ein Vorschlag, wenn die gewaehlte Quelle nicht passt.
    Quellen mit bewiesenem Saldo und vielen Bewegungen stehen vorn."""
    matches: list[dict[str, Any]] = []
    for adapter_id, adapter in ADAPTERS.items():
        if not all(name.lower().endswith(adapter["extensions"]) for _data, name in sources):
            continue
        if not cash_reader_may_read_v1(adapter_id, sources):
            continue
        try:
            parsed = parse_cash_statement_set_v1(adapter_id, sources)
        except CashStatementImportV1Error:
            continue
        if parsed["candidates"] and len(parsed["diagnostics"]) <= len(parsed["candidates"]):
            matches.append({"adapter_id": adapter_id, "label": adapter["label"], "movement_count": len(parsed["candidates"]),
                            "balance_consistent": parsed["balance_consistent"]})
    matches.sort(key=lambda item: (not item["balance_consistent"], -item["movement_count"], item["adapter_id"]))
    return matches


def list_cash_statement_adapters_v1() -> list[dict[str, Any]]:
    """Die Leser des Cash-Imports mit dem, was die Karte dazu sagt (#550): Grenzen aus dem Manifest, und ob der Leser die Dateien eines
    Kontos zusammen liest (combine, etwa BSDEX: Export und Jahreshistorien)."""
    return [{"adapter_id": key, "label": value["label"], "extensions": list(value["extensions"]), "validated": cash_reader_validation_v1(key),
             "known_limits": list(value["known_limits"]), "combine": "combine" in value}
            for key, value in ADAPTERS.items()]


# ---------------------------------------------------------------- parsing and checks
def parse_cash_statement_v1(adapter_id: str, source: bytes, file_name: str) -> dict[str, Any]:
    adapter = ADAPTERS.get(adapter_id)
    if adapter is None or not isinstance(source, bytes) or not 0 < len(source) <= MAX_BYTES or not isinstance(file_name, str) \
            or not file_name.lower().endswith(adapter["extensions"]):
        _abort("cash_statement_source_invalid")
    parsed = adapter["parse"](source, file_name)
    candidates = sorted(parsed["candidates"], key=lambda row: (row["local_date"], row["source_row_ordinal"]))
    # Deterministic time within a date-only day: 12:00:00 plus the order of the row on that day.
    per_day: dict[str, int] = {}
    for row in candidates:
        position = per_day.get(row["local_date"], 0); per_day[row["local_date"]] = position + 1
        row["local_time"] = (datetime(2000, 1, 1, 12, 0, 0) + timedelta(seconds=position)).strftime("%H:%M:%S")
    running = Decimal(parsed["summary"]["opening_balance_decimal"]) if parsed["summary"]["opening_balance_decimal"] is not None else None
    balance_consistent = running is not None
    for row in candidates:
        if running is None:
            break
        running += Decimal(row["amount_decimal"]) * (-1 if row["kind"] == "withdrawal" else 1)
        if row["balance_after_decimal"] is not None and Decimal(row["balance_after_decimal"]) != running:
            balance_consistent = False
    closing = parsed["summary"]["closing_balance_decimal"]
    if running is not None and closing is not None and Decimal(closing) != running:
        balance_consistent = False
    if parsed.get("balance_proof") is False:
        balance_consistent = False
    return {"cash_statement_parse_version": VERSION, "adapter_id": adapter_id, "source_fingerprint": hashlib.sha256(source).hexdigest(),
            "candidates": candidates, "diagnostics": parsed["diagnostics"], "summary": parsed["summary"],
            "computed_closing_decimal": None if running is None else _plain(running), "balance_consistent": balance_consistent,
            "balance_anchor_only": bool(parsed.get("balance_anchor_only"))}


def _statement_sort_key(parsed: Mapping[str, Any]) -> tuple[str, str]:
    summary = parsed["summary"]
    dates = [row["local_date"] for row in parsed["candidates"]]
    return (summary["period_from"] or (min(dates) if dates else ""), summary["period_to"] or (max(dates) if dates else ""))


def _statement_shape(parsed: Mapping[str, Any]) -> str:
    # Zwei Ausfertigungen desselben Auszugs koennen die Zeilen eines Tages in anderer
    # Reihenfolge drucken; gleich ist gleich, deshalb sortiert vergleichen.
    return _sha(sorted([row["local_date"], row["kind"], row["amount_decimal"]] for row in parsed["candidates"]))


def _signed(row: Mapping[str, Any]) -> Decimal:
    return Decimal(row["amount_decimal"]) * (-1 if row["kind"] == "withdrawal" else 1)


def _supersedes(newer: Mapping[str, Any], older: Mapping[str, Any]) -> bool:
    """Ein neuerer Auszug ersetzt einen aelteren, den er ganz enthaelt (#524): Er endet spaeter (oder gleich und beginnt frueher)
    und beginnt spaetestens mit der ersten Bewegung des aelteren. Nennen beide einen Anfangssaldo, muessen sie am spaeteren der
    beiden Anfaenge denselben Stand ergeben. So gilt bei Exporten "vom Kontobeginn bis heute" der neueste - auch wenn die Bank
    die Vergangenheit neu verteilt hat (etwa Bondora) -, waehrend Monatsauszuege einander nie enthalten."""
    newer_start, newer_end = _statement_sort_key(newer)
    older_start, older_end = _statement_sort_key(older)
    older_days = [row["local_date"] for row in older["candidates"]]
    older_first = min(older_days) if older_days else older_start
    if not (newer_start and newer_end and older_start and older_end and older_first):
        return False
    if newer_start > older_first or newer_end < older_end or (newer_end == older_end and newer_start >= older_start):
        return False
    newer_opening, older_opening = newer["summary"]["opening_balance_decimal"], older["summary"]["opening_balance_decimal"]
    if newer_opening is not None and older_opening is not None:
        start = max(newer_start, older_start)
        at = lambda parsed, opening: Decimal(opening) + sum((_signed(row) for row in parsed["candidates"] if row["local_date"] < start), Decimal("0"))
        if at(newer, newer_opening) != at(older, older_opening):
            return False
    return True


def _continues(newer: Mapping[str, Any], older: Mapping[str, Any]) -> bool:
    """Ein neuerer Export setzt einen aelteren fort (rc.347): Er beginnt nach dessen erster Bewegung, spaetestens an dessen Ende, und
    endet spaeter. Beide muessen an seinem ersten Tag denselben Stand ergeben - mit Anfangssalden am Saldo, ohne Salden an denselben
    Zeilen im Ueberlapp. Sonst bleibt es bei der Luecke: Ein Export, der nicht anschliesst, wird nie still angehaengt."""
    newer_start, newer_end = _statement_sort_key(newer)
    older_start, older_end = _statement_sort_key(older)
    older_days = [row["local_date"] for row in older["candidates"]]
    if not (newer_start and newer_end and older_start and older_end and older_days):
        return False
    if not (min(older_days) < newer_start <= older_end and newer_end > older_end):
        return False
    newer_opening, older_opening = newer["summary"]["opening_balance_decimal"], older["summary"]["opening_balance_decimal"]
    if newer_opening is not None and older_opening is not None:
        before = sum((_signed(row) for row in older["candidates"] if row["local_date"] < newer_start), Decimal("0"))
        return Decimal(older_opening) + before == Decimal(newer_opening)
    if newer_opening is not None or older_opening is not None:
        return False
    overlap = lambda parsed: sorted((row["local_date"], row["kind"], Decimal(row["amount_decimal"])) for row in parsed["candidates"]
                                    if newer_start <= row["local_date"] <= older_end)
    return overlap(newer) == overlap(older)


def _trimmed_before(parsed: Mapping[str, Any], start: str) -> dict[str, Any]:
    """Der aeltere Export nur bis zum Tag vor `start`; sein Endsaldo ist der Stand dort (ohne Anfangssaldo: keiner)."""
    kept = [row for row in parsed["candidates"] if row["local_date"] < start]
    opening = parsed["summary"]["opening_balance_decimal"]
    closing = None if opening is None else _plain(Decimal(opening) + sum((_signed(row) for row in kept), Decimal("0")))
    summary = {key: value for key, value in parsed["summary"].items() if key != "closing_as_of_date"}
    summary.update(period_to=(date.fromisoformat(start) - timedelta(days=1)).isoformat(), closing_balance_decimal=closing)
    ordinals = {row.get("source_row_ordinal") for row in kept} | {0}
    diagnostics = [item for item in parsed["diagnostics"]
                   if (item["as_of_date"] < start if item.get("as_of_date") else item.get("source_row_ordinal") in ordinals)]
    return {**parsed, "candidates": kept, "summary": summary, "diagnostics": diagnostics}


def _net_interest_reversals(candidates: list[dict[str, Any]]) -> int:
    """A "Storno Rechnungsabschluss" cancels an earlier interest credit, sometimes months later.
    Both stay Cash movements; the reversed credit loses its income leg, so the interest total nets out."""
    reversed_count = 0
    for row in candidates:
        if row["kind"] != "withdrawal" or not row["text"].lower().startswith("storno"):
            continue
        partner = next((earlier for earlier in reversed(candidates)
                        if earlier["kind"] == "interest" and earlier["amount_decimal"] == row["amount_decimal"]
                        and earlier["local_date"] <= row["local_date"] and not earlier.get("reversed")), None)
        if partner is None:
            continue
        partner["reversed"] = True; partner["kind"] = "deposit"
        row["reverses_local_date"] = partner["local_date"]
        reversed_count += 1
    return reversed_count


def _number_within_days(candidates: list[dict[str, Any]]) -> None:
    """Fortlaufende Nummer im Stapel; innerhalb eines Tages 12:00:00 plus die Stelle der Zeile an diesem Tag."""
    candidates.sort(key=lambda row: (row["local_date"], row["source_file_name"], row["source_row_ordinal"]))
    per_day: dict[str, int] = {}
    for ordinal, row in enumerate(candidates, 1):
        row["source_row_ordinal"] = ordinal
        position = per_day.get(row["local_date"], 0); per_day[row["local_date"]] = position + 1
        row["local_time"] = (datetime(2000, 1, 1, 12, 0, 0) + timedelta(seconds=position)).strftime("%H:%M:%S")


def _combined_set(adapter_id: str, combined: Mapping[str, Any], skipped: Sequence[str]) -> dict[str, Any]:
    """Ein Stapel, den die Quelle als Ganzes liest (BSDEX: Export und Jahreshistorien zusammen). Ohne Saldo in den Dateien; den
    zweiten Beleg gibt der vom Eigentuemer bestaetigte Saldo. Was fehlt, steht als Luecke in der Vorschau und haelt das Buchen an."""
    candidates = list(combined["candidates"])
    _number_within_days(candidates)
    days = [row["local_date"] for row in candidates]
    blank = {"opening_balance_decimal": None, "closing_balance_decimal": None, "balance_consistent": False, "balance_anchor_only": False}
    files = [{"file_name": entry["file_name"], "period_from": entry["period_from"], "period_to": entry["period_to"], **blank,
              "row_count": entry["row_count"], "status": entry["status"]} for entry in combined["files"]]
    files.extend({"file_name": name, "period_from": None, "period_to": None, **blank, "row_count": 0, "status": "skipped_format"} for name in sorted(skipped))
    files.extend({"file_name": name, "period_from": None, "period_to": None, **blank, "row_count": 0, "status": "skipped_unreadable"}
                 for name in sorted(combined["unreadable"]))
    summary = {"opening_balance_decimal": None, "closing_balance_decimal": None, "period_from": days[0] if days else None, "period_to": days[-1] if days else None}
    shape = sorted([row["local_date"], row["kind"], row["amount_decimal"]] for row in candidates)
    return {"cash_statement_parse_version": VERSION, "adapter_id": adapter_id,
            "source_fingerprint": _sha({"files": sorted(entry["file_name"] for entry in combined["files"]), "movements": shape, "gaps": combined["chain_gaps"]}),
            "candidates": candidates, "diagnostics": list(combined["diagnostics"]), "summary": summary, "files": files,
            "chain_gaps": list(combined["chain_gaps"]), "interest_reversals": 0, "computed_closing_decimal": None, "balance_consistent": False,
            "held_back": list(combined.get("held_back", [])), "evidence": dict(combined["evidence"])}


@reader_plugins.within_reader_session
def parse_cash_statement_set_v1(adapter_id: str, sources: Sequence[tuple[bytes, str]]) -> dict[str, Any]:
    """Several statements of one account at once: read them all, then sort and check.
    The owner drops a whole folder in; file names carry no reliable order (#184)."""
    if not sources or len(sources) > MAX_STATEMENTS:
        _abort("cash_statement_input_invalid")
    # Dateien in einem Format, das die Quelle nicht liest, bleiben draussen und werden genannt (#518): Aus der Ablage kommt mit
    # den Auszuegen eines Kontos auch ein ihm zugeordneter Export (etwa die CSV der Wertpapierumsaetze am Verrechnungskonto).
    # Ohne das hielt diese eine Datei den ganzen Stapel an. Passt keine Datei, bleibt es bei der Ablehnung wie bisher.
    adapter = ADAPTERS.get(adapter_id)
    extensions = adapter["extensions"] if adapter is not None else ()
    readable = [(data, name) for data, name in sources if isinstance(name, str) and name.lower().endswith(extensions)]
    skipped = [name for data, name in sources if not (isinstance(name, str) and name.lower().endswith(extensions))]
    if not readable:
        _abort("cash_statement_source_invalid")
    if adapter.get("combine") is not None:
        if any(not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES for data, _name in readable):
            _abort("cash_statement_source_invalid")
        return _combined_set(adapter_id, adapter["combine"](readable), skipped)
    # Eine Datei im richtigen Format, die kein Auszug dieser Quelle ist (etwa eine Entgeltaufstellung, als PDF am Girokonto
    # abgelegt), bleibt ebenso draussen. Ist es keine einzige, gilt die Ablehnung der ersten wie bisher.
    parsed_files, unreadable = [], []
    prefetched = _plugin_prefetch(adapter_id, readable) if reader_plugins.reader_spec_v1(adapter_id) is not None and len(readable) > 1 else []
    try:
        for data, name in readable:
            try:
                parsed_files.append((name, parse_cash_statement_v1(adapter_id, data, name)))
            except CashStatementImportV1Error as error:
                if error.code != "cash_statement_header_invalid":
                    raise
                unreadable.append((name, error))
    finally:
        for key in prefetched:
            _PREFETCHED.pop(key, None)
    if not parsed_files:
        raise unreadable[0][1]
    parsed_files.sort(key=lambda item: _statement_sort_key(item[1]))
    # Je Datei der neueste Auszug, der sie ganz enthaelt (#524); ersetzte Dateien zaehlen nicht mit und halten nichts an.
    replaced_by: dict[int, str] = {}
    for position, (_name, older) in enumerate(parsed_files):
        newer = [(other_position, other) for other_position, (_other_name, other) in enumerate(parsed_files)
                 if other_position != position and _supersedes(other, older)]
        if newer:
            latest = max(_statement_sort_key(other)[1] for _other_position, other in newer)
            best = min((item for item in newer if _statement_sort_key(item[1])[1] == latest), key=lambda item: (_statement_sort_key(item[1])[0], item[0]))
            replaced_by[position] = parsed_files[best[0]][0]
    # Ein neuerer Export, der mitten in einem aelteren beginnt und spaeter endet, gilt ab seinem ersten Tag; der aeltere nur bis
    # davor (rc.347). Beispiel: In der Ablage liegt eine lange Umsatzliste, neu kommt ein Export ab Jahresbeginn.
    # Ohne das galt der neue als Folgeauszug ab Januar - Luecke im Saldo, und die schon gebuchten Umsaetze waeren doppelt erschienen.
    continued_by: dict[int, tuple[str, str]] = {}
    for position, (_name, older) in enumerate(parsed_files):
        if position in replaced_by:
            continue
        starts = [(_statement_sort_key(other)[0], other_name) for other_position, (other_name, other) in enumerate(parsed_files)
                  if other_position != position and other_position not in replaced_by and _continues(other, older)]
        if starts:
            continued_by[position] = min(starts)
    parsed_files = [(name, _trimmed_before(parsed, continued_by[position][0]) if position in continued_by else parsed)
                    for position, (name, parsed) in enumerate(parsed_files)]
    files: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    shapes: dict[tuple[str, str], str] = {}
    previous: dict[str, Any] | None = None
    opening = closing = closing_as_of = None
    for position, (name, parsed) in enumerate(parsed_files):
        summary = parsed["summary"]
        period = _statement_sort_key(parsed)
        entry = {"file_name": name, "period_from": summary["period_from"], "period_to": summary["period_to"],
                 "opening_balance_decimal": summary["opening_balance_decimal"], "closing_balance_decimal": summary["closing_balance_decimal"],
                 "row_count": len(parsed["candidates"]), "balance_consistent": parsed["balance_consistent"],
                 "balance_anchor_only": parsed.get("balance_anchor_only", False), "status": "used"}
        if position in replaced_by:
            entry.update(status="superseded", superseded_by=replaced_by[position]); files.append(entry); continue
        if position in continued_by:
            entry["continued_by"] = continued_by[position][1]
        shape = _statement_shape(parsed)
        if shapes.get(period) == shape:
            entry["status"] = "duplicate"; files.append(entry); continue
        if period in shapes:
            entry["status"] = "conflicting_duplicate"; files.append(entry)
            gaps.append({"reason": "two_statements_for_one_period", "file_name": name, "period_from": period[0], "period_to": period[1]})
            continue
        shapes[period] = shape
        if previous is not None and previous["closing_balance_decimal"] is not None and summary["opening_balance_decimal"] is not None \
                and Decimal(previous["closing_balance_decimal"]) != Decimal(summary["opening_balance_decimal"]):
            entry["status"] = "gap_before"
            gaps.append({"reason": "statement_missing_before", "file_name": name,
                         "expected_balance_decimal": previous["closing_balance_decimal"],
                         "opening_balance_decimal": summary["opening_balance_decimal"], "period_from": summary["period_from"]})
        if opening is None:
            opening = summary["opening_balance_decimal"]
        if summary["closing_balance_decimal"] is not None:
            # Der Abstimmtag gehoert zu genau dem Endsaldo, der uebernommen wird.
            closing, closing_as_of = summary["closing_balance_decimal"], summary.get("closing_as_of_date")
        for row in parsed["candidates"]:
            candidates.append({**row, "source_file_name": name})
        diagnostics.extend({**item, "file_name": name} for item in parsed["diagnostics"])
        files.append(entry); previous = entry
    # Ein Stapel nur aus bewegungslosen Auszuegen ist gueltig, wenn jeder seinen Saldo belegt (#440): Er bestaetigt den Stand.
    anchors = [entry for entry in files if entry["status"] in {"used", "gap_before"}]
    if not candidates and not (anchors and all(entry["closing_balance_decimal"] is not None and entry["balance_consistent"] for entry in anchors)):
        _abort("cash_statement_header_invalid")
    _number_within_days(candidates)
    reversals = _net_interest_reversals(candidates)
    running = Decimal(opening) if opening is not None else None
    used_entries = [entry for entry in files if entry["status"] in {"used", "gap_before"}]
    # Eine Datei mit nur einem Saldo gilt als belegt, wenn sie lueckenlos an einen
    # Vorgaenger anschliesst: dessen Endsaldo ist dann ihr zweiter, unabhaengiger Beleg.
    consistent = running is not None and closing is not None and not gaps and all(
        entry["balance_consistent"] or (entry["balance_anchor_only"] and position > 0)
        for position, entry in enumerate(used_entries))
    if running is not None:
        for row in candidates:
            running += Decimal(row["amount_decimal"]) * (-1 if row["kind"] == "withdrawal" else 1)
        if closing is None or Decimal(closing) != running:
            consistent = False
    used = [entry for entry in files if entry["status"] in {"used", "gap_before"}]
    summary = {"opening_balance_decimal": opening, "closing_balance_decimal": closing,
               "period_from": used[0]["period_from"] if used else None, "period_to": used[-1]["period_to"] if used else None}
    if closing_as_of is not None:
        summary["closing_as_of_date"] = closing_as_of
    files.extend({"file_name": name, "period_from": None, "period_to": None, "opening_balance_decimal": None, "closing_balance_decimal": None,
                  "row_count": 0, "balance_consistent": False, "balance_anchor_only": False, "status": "skipped_format"} for name in sorted(skipped))
    files.extend({"file_name": name, "period_from": None, "period_to": None, "opening_balance_decimal": None, "closing_balance_decimal": None,
                  "row_count": 0, "balance_consistent": False, "balance_anchor_only": False, "status": "skipped_unreadable"}
                 for name in sorted(name for name, _error in unreadable))
    return {"cash_statement_parse_version": VERSION, "adapter_id": adapter_id,
            "source_fingerprint": _sha([name for position, (name, _parsed) in enumerate(parsed_files) if position not in replaced_by]
                                       + [shape for shape in shapes.values()]),
            "candidates": candidates, "diagnostics": diagnostics, "summary": summary, "files": files, "chain_gaps": gaps,
            "interest_reversals": reversals,
            "computed_closing_decimal": None if running is None else _plain(running), "balance_consistent": consistent}


def confirm_cash_statement_balance_v1(parsed: Mapping[str, Any], as_of_date: str, balance_decimal: str) -> dict[str, Any]:
    """Der Eigentuemer bestaetigt den Saldo am Stichtag.

    Fuer Exporte ohne Saldoangabe (C24, CHECK24, Bison, BSDEX, Coinbase) ist das der zweite,
    unabhaengige Beleg: der Anfangssaldo ergibt sich aus Stichtagssaldo minus allen Bewegungen
    bis zum Stichtag, der Abgleich wird am Stichtag festgehalten. Der Stichtag darf nicht vor
    der juengsten Bewegung liegen, sonst waeren spaetere Bewegungen unbelegt.
    """
    try:
        day = date.fromisoformat(str(as_of_date)).isoformat()
    except ValueError:
        _abort("cash_statement_balance_confirmation_invalid")
    value = _cents(str(balance_decimal).replace(",", ".")) if balance_decimal is not None else None
    dates = [row["local_date"] for row in parsed["candidates"]]
    if value is None or not dates or day < max(dates) or parsed.get("chain_gaps"):
        _abort("cash_statement_balance_confirmation_invalid")
    signed = sum((Decimal(row["amount_decimal"]) * (-1 if row["kind"] == "withdrawal" else 1) for row in parsed["candidates"]), Decimal("0"))
    summary = {**parsed["summary"], "opening_balance_decimal": _plain(value - signed), "closing_balance_decimal": _plain(value),
               "closing_as_of_date": day, "period_to": max(day, parsed["summary"].get("period_to") or day)}
    return {**parsed, "summary": summary, "balance_consistent": True,
            "owner_confirmed_balance": {"as_of_date": day, "balance_decimal": _plain(value)},
            "source_fingerprint": _sha({"source": parsed["source_fingerprint"], "owner_confirmed_balance": [day, _plain(value)]})}


def _projection(data_space: Path, context: Any) -> dict[str, Any]:
    path = data_space / STORE_AREA / STORE_NAME
    if not path.exists():
        return {"coverage_periods": [], "cash_events": [], "income_events": [], "reconciliations": []}
    return read_desktop_cash_coverage_exchange_projection_v1(path, context)


def _utc(local_date: str, local_time: str) -> str:
    local = datetime.fromisoformat(f"{local_date}T{local_time}").replace(tzinfo=ZoneInfo(TIME_ZONE))
    return local.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")


def _booked_balance_at(events: Sequence[Mapping[str, Any]], boundary: str) -> Decimal:
    """Der gebuchte Stand an einem Tag - gerechnet ab der juengsten Eroeffnung davor.

    Ein Konto kann mehrere Abdeckungsperioden tragen, jede mit eigenem
    Eroeffnungssaldo (ein Nachtrag alter Auszuege vor einer bestehenden Abdeckung,
    #467). Eine Summe ueber alle Ereignisse zaehlte diese Eroeffnungen zusammen und
    behauptete einen Stand, den es nie gab - der naechste Import meldete daraufhin
    eine Luecke.

    Die Eroeffnung gilt zum Anfang ihres Tages, wie im Cash-Kern (cash_coverage_v1: Saldo = Eroeffnung plus alle Bewegungen ab ihrem
    Tag): Bewegungen am Tag der Eroeffnung zaehlen mit. Bis rc.436 zaehlten nur spaetere - ein Konto, dessen Eroeffnung am Tag der
    ersten Einzahlung steht, fehlte dann um genau diese Einzahlung, und die Vorschau lehnte den Abgleich eines stimmigen Auszugs ab.
    """
    sign = {"deposit": 1, "withdrawal": -1, "transfer": 0}
    openings = [row for row in events if row["event_type"] == "opening_balance" and row["local_date"] <= boundary]
    start = max((row["local_date"] for row in openings), default=None)
    total = sum((Decimal(row["amount_decimal"]) for row in openings if row["local_date"] == start), Decimal("0"))
    return total + sum((Decimal(row["amount_decimal"]) * sign.get(row["event_type"], 0) for row in events
                        if row["local_date"] <= boundary and (start is None or row["local_date"] >= start)), Decimal("0"))


# Neu verteilte Tage (#524): Bondora rechnet die Tageszinsen rueckwirkend neu. Gebucht
# wird 1:1, was der neueste Auszug sagt - ein gebuchter Tag, der davon abweicht, wird korrigiert, nicht ein zweites Mal gebucht.
RESTATED_FLOWS = {"interest": ("deposit", "income_receipt"), "deposit": ("deposit", "external_contribution"),
                  "withdrawal": ("withdrawal", "external_withdrawal")}
RESTATED_MAX_PREDECESSORS = 100   # Grenze des Cash-Kerns je Revision
RESTATED_PER_CALL = 10


def _record_ref(command_id: str) -> str:
    return "cash_record_" + _sha({"command_id": command_id})[:32]


def _restatements(parsed: Mapping[str, Any], rows: list[dict[str, Any]], leftovers: Sequence[Mapping[str, Any]],
                  incomes_left: dict[tuple[str, str], list[str | None]], reconciliations: Sequence[Mapping[str, Any]],
                  locked_commands: set[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """Paart je Tag und Art genau eine neue Zeile mit genau einer gebuchten Bewegung, die der Auszug nicht mehr nennt.

    Ein Zins traegt zwei Saetze (Bewegung und Ertrag); beide werden korrigiert. Die Korrekturen laufen in Gruppen, deren Summe null
    ist - so stimmt jeder Abgleich auch zwischen zwei Schritten (der Cash-Kern prueft alle Abgleiche nach jeder Revision). Ein
    Abgleich, dessen Stand sich verschiebt, wird in der Gruppe mitkorrigiert, die ihn verschiebt; nennt der Auszug Salden, muss der
    neue Stand der des Auszugs sein. Was sich nicht eindeutig paaren laesst, bleibt neu; die Saldoprobe haelt es dann an."""
    if not rows:
        return [], [], None
    first, last = min(row["local_date"] for row in rows), max(row["local_date"] for row in rows)
    fresh: dict[tuple[str, str, str], list[int]] = {}
    for index, row in enumerate(rows):
        if row["status"] == "new":
            fresh.setdefault((row["local_date"], *RESTATED_FLOWS[row["kind"]]), []).append(index)
    stale: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for event in leftovers:
        if first <= event["local_date"] <= last and event["event_type"] in ("deposit", "withdrawal"):
            stale.setdefault((event["local_date"], event["event_type"], event["flow_classification"]), []).append(event)
    corrections: list[dict[str, Any]] = []
    marks: list[tuple[int, str]] = []
    for key, indexes in sorted(fresh.items()):
        old = stale.get(key, [])
        if len(indexes) != 1 or len(old) != 1 or old[0]["command_id"] in locked_commands:
            continue
        row, event = rows[indexes[0]], old[0]
        income_ref = None
        if row["kind"] == "interest":
            day = row.get("value_date") or row["local_date"]
            refs = [(income_key, ref) for income_key, items in incomes_left.items() if income_key[0] == day for ref in items if ref]
            if len(refs) != 1:
                continue
            income_key, income_ref = refs[0]
            incomes_left[income_key].remove(income_ref)
        booked = _plain(Decimal(event["amount_decimal"]))
        delta = _signed(row) - _signed({"kind": row["kind"], "amount_decimal": booked})
        marks.append((indexes[0], booked))
        corrections.append({"local_date": row["local_date"], "local_time": row["local_time"], "kind": row["kind"], "amount_decimal": row["amount_decimal"],
                            "booked_amount_decimal": booked, "delta_decimal": _plain(delta), "value_date": row.get("value_date"),
                            "gross_income_decimal": row.get("gross_income_decimal"), "cash_record_ref": _record_ref(event["command_id"]),
                            "income_record_ref": income_ref})
    if not corrections:
        return [], [], None
    groups: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    running = Decimal("0")
    for item in corrections:
        current.append(item); running += Decimal(item["delta_decimal"])
        if running == 0:
            groups.append({"corrections": current, "reconciliations": []}); current = []
    if current:
        groups.append({"corrections": current, "reconciliations": []})
    opening = parsed["summary"].get("opening_balance_decimal")
    for reconciliation in sorted(reconciliations, key=lambda item: item["as_of_date"]):
        as_of = reconciliation["as_of_date"]
        shift = sum((Decimal(item["delta_decimal"]) for item in corrections if item["local_date"] <= as_of), Decimal("0"))
        if shift == 0:
            continue
        observed = Decimal(reconciliation["observed_balance_decimal"]) + shift
        if reconciliation["command_id"] in locked_commands:
            return [], [], {"reason": "restated_reconciliation_locked", "as_of_date": as_of}
        if opening is not None:
            stated = Decimal(opening) + sum((_signed(row) for row in parsed["candidates"] if row["local_date"] <= as_of), Decimal("0"))
            if stated != observed:
                return [], [], {"reason": "restated_reconciliation_mismatch", "as_of_date": as_of,
                                "expected_balance_decimal": _plain(observed), "opening_balance_decimal": _plain(stated)}
        target = max(position for position, group in enumerate(groups) if group["corrections"][0]["local_date"] <= as_of)
        groups[target]["reconciliations"].append({"as_of_date": as_of, "observed_balance_decimal": _plain(Decimal(reconciliation["observed_balance_decimal"])),
                                                   "new_observed_balance_decimal": _plain(observed), "record_ref": _record_ref(reconciliation["command_id"])})
    size = lambda group: sum(1 + (item["income_record_ref"] is not None) for item in group["corrections"]) + len(group["reconciliations"])
    for group in groups:
        if size(group) > RESTATED_MAX_PREDECESSORS:
            return [], [], {"reason": "restated_group_too_large", "period_from": group["corrections"][0]["local_date"], "correction_count": size(group)}
    # Aufeinanderfolgende Gruppen mit Summe null ergeben zusammen wieder null: bis zur Grenze des Kerns in einen Schritt gepackt.
    # Viele Einzelschritte brauchten sonst mehrere Minuten.
    steps: list[dict[str, Any]] = []
    for group in groups:
        if steps and size(steps[-1]) + size(group) <= RESTATED_MAX_PREDECESSORS:
            steps[-1] = {"corrections": steps[-1]["corrections"] + group["corrections"],
                         "reconciliations": steps[-1]["reconciliations"] + group["reconciliations"]}
        else:
            steps.append(group)
    groups = steps
    for index, booked in marks:
        rows[index] = {**rows[index], "status": "corrected", "booked_amount_decimal": booked}
    return corrections, groups, None


def preview_cash_statement_import_v1(data_space_path: str | Path, context: Any, parsed: Mapping[str, Any], account_id: str) -> dict[str, Any]:
    """Read-only: which rows are already booked for this account, and which coverage fits."""
    projection = _projection(Path(data_space_path), context)
    events = [row for row in projection["cash_events"] if row["account_id"] == account_id]
    incomes = [row for row in projection["income_events"] if row["account_id"] == account_id]
    periods = [row for row in projection["coverage_periods"] if row["account_id"] == account_id]
    available_events: dict[tuple[str, str, str, str], int] = {}
    events_by_key: dict[tuple[str, str, str, str], list[Mapping[str, Any]]] = {}
    for row in events:
        key = (row["event_type"], row["local_date"], _plain(Decimal(row["amount_decimal"])), row["flow_classification"])
        available_events[key] = available_events.get(key, 0) + 1
        events_by_key.setdefault(key, []).append(row)
    # Je gebuchtem Ertrag der Record-Ref seines Kommandos: nur damit laesst sich ein
    # netto gebuchter Zins spaeter eindeutig auf brutto korrigieren (#465).
    available_incomes: dict[tuple[str, str], list[str | None]] = {}
    for row in incomes:
        key = (row["local_date"], _plain(Decimal(row["gross_income_decimal"])))
        available_incomes.setdefault(key, []).append(row.get("record_ref"))
    rows = []
    for candidate in parsed["candidates"]:
        if candidate["kind"] == "interest":
            event_key = ("deposit", candidate["local_date"], candidate["amount_decimal"], "income_receipt")
            gross = candidate.get("gross_income_decimal") or candidate["amount_decimal"]
            income_key = (candidate.get("value_date") or candidate["local_date"], gross)
            booked = available_events.get(event_key, 0) > 0 and bool(available_incomes.get(income_key))
            if booked:
                available_events[event_key] -= 1; available_incomes[income_key].pop()
            elif available_events.get(event_key, 0) > 0:
                # Vor #465 trug der Ertrag den Buchungstag und den Betrag, der aufs Konto
                # kam. Diese Zinsen sind gebucht; ein zweiter Write verdoppelte sie. Tag
                # und Bruttobetrag korrigiert der Eigentuemer ausdruecklich, deshalb nennt
                # die Zeile den alten Stand, statt still neu zu buchen.
                older = next(((day, value) for day, value in ((candidate["local_date"], gross),
                                                              (candidate.get("value_date") or candidate["local_date"], candidate["amount_decimal"]),
                                                              (candidate["local_date"], candidate["amount_decimal"]))
                              if (day, value) != income_key and available_incomes.get((day, value))), None)
                raised = None
                if older is None and candidate.get("gross_income_decimal") is None:
                    # Brutto angehoben (#465): Nennt der Auszug nur den Betrag, der aufs Konto kam (Baader), und steht am selben
                    # Tag ein hoeherer Ertrag - der Bruttozins aus der Ertraegnisaufstellung -, ist der Zins gebucht. Ein zweiter
                    # Write verdoppelte ihn; eine Korrektur gibt es hier nicht, der Auszug kennt den Bruttobetrag nicht.
                    days = {candidate["local_date"], candidate.get("value_date") or candidate["local_date"]}
                    raised = next(((day, value) for (day, value), refs in available_incomes.items()
                                   if refs and day in days and Decimal(value) > Decimal(candidate["amount_decimal"])), None)
                if older is not None or raised is not None:
                    match = older if older is not None else raised
                    available_events[event_key] -= 1
                    record = available_incomes[match].pop()
                    booked = True
                    candidate = {**candidate, "income_booked_on": match[0], "income_booked_decimal": match[1],
                                 "income_booked_record_ref": record, **({"income_raised_to_gross": True} if older is None else {})}
                else:
                    # Halb gebucht (ein abgebrochener Schritt): die Bewegung steht schon, der Ertrag fehlt noch. Die Zeile bleibt neu,
                    # ihr erledigter Teil wird beim Buchen uebersprungen; die Saldoprobe zaehlt die Bewegung nur einmal (#524).
                    available_events[event_key] -= 1
                    candidate = {**candidate, "cash_event_booked": True}
        else:
            flow = "external_contribution" if candidate["kind"] == "deposit" else "external_withdrawal"
            event_key = (candidate["kind"], candidate["local_date"], candidate["amount_decimal"], flow)
            booked = available_events.get(event_key, 0) > 0
            if booked:
                available_events[event_key] -= 1
            elif candidate["kind"] == "deposit":
                # Dieselbe Einzahlung kann frueher als Zinseingang gebucht worden sein - etwa wenn
                # der Storno erst mit einem spaeteren Auszug kam. Lieber als gebucht erkennen als
                # ein zweites Mal buchen; die Ertragsbuchung von damals bleibt bestehen.
                income_flow = ("deposit", candidate["local_date"], candidate["amount_decimal"], "income_receipt")
                booked = available_events.get(income_flow, 0) > 0
                if booked:
                    available_events[income_flow] -= 1
        rows.append({**candidate, "status": "booked" if booked else "new"})
    leftovers = [event for key, count in available_events.items() if count > 0 for event in events_by_key.get(key, [])[:count]]
    reconciliations = [row for row in projection["reconciliations"] if row["account_id"] == account_id]
    # Abgleiche, die an einer Abdeckung haengen (Eroeffnung), lassen sich nicht einzeln korrigieren.
    locked = {row["command_id"] for row in periods} | {row["command_id"] for row in events if row["event_type"] == "opening_balance"}
    corrections, correction_groups, restated_block = _restatements(parsed, rows, leftovers, available_incomes, reconciliations, locked)
    summary = parsed["summary"]
    dates = [row["local_date"] for row in parsed["candidates"]]
    first, last = (min(dates), max(dates)) if dates else (None, None)
    covered = lambda day: any(period["effective_from"] <= day and (period["effective_to"] is None or day <= period["effective_to"])
                              and period["coverage_mode"] in {"partial", "complete_reconciled"} for period in periods)
    if not dates:
        # Nur bewegungslose Auszuege (#440): Liegt ihr Stichtag in einer abgeglichenen Abdeckung, halten sie den Saldo als
        # Abgleich fest - sofern der gebuchte Stand dazu passt. Sonst fehlt etwas davor, und das sagt die Vorschau.
        as_of = summary.get("closing_as_of_date")
        anchored = parsed["balance_consistent"] and summary["closing_balance_decimal"] is not None and as_of is not None
        reconciled = anchored and any(period["coverage_mode"] == "complete_reconciled" and period["effective_from"] <= as_of
                                      and (period["effective_to"] is None or as_of <= period["effective_to"]) for period in periods)
        if reconciled and _booked_balance_at(events, as_of) == Decimal(summary["closing_balance_decimal"]):
            coverage = {"proposal": "existing", "reason": "balance_anchor",
                        "reconcile_to": {"as_of_date": as_of, "observed_balance_decimal": summary["closing_balance_decimal"]}}
        elif reconciled:
            coverage = {"proposal": "gap", "reason": "opening_balance_mismatch", "as_of_date": as_of,
                        "expected_balance_decimal": _plain(_booked_balance_at(events, as_of)), "opening_balance_decimal": summary["closing_balance_decimal"]}
        else:
            coverage = {"proposal": "none", "reason": "no_movements"}
    elif all(covered(day) for day in dates):
        coverage = {"proposal": "existing", "reason": "period_already_covered",
                    "reconcile_to": {"as_of_date": summary.get("closing_as_of_date") or last, "observed_balance_decimal": summary["closing_balance_decimal"]}
                    if parsed["balance_consistent"] and summary["closing_balance_decimal"] is not None else None}
    elif any(covered(day) for day in dates):
        coverage = {"proposal": "blocked", "reason": "partial_overlap_with_existing_coverage"}
    elif periods:
        # Nachtrag vor einer bestehenden Abdeckung: kein Tag des Stapels liegt in ihr,
        # also entsteht eine eigene, abgeschlossene Periode. Sie endet am belegten
        # Auszugsende und laeuft nicht in die bestehende hinein - ein ungedeckter
        # Zeitraum dazwischen bleibt ungedeckt (#467).
        proven_to = summary.get("closing_as_of_date") or last
        following = min((period["effective_from"] for period in periods if period["effective_from"] > last), default=None)
        if following is not None and following <= proven_to:
            proven_to = (date.fromisoformat(following) - timedelta(days=1)).isoformat()
        if parsed["balance_consistent"] and summary["opening_balance_decimal"] is not None and summary["closing_balance_decimal"] is not None:
            opening_day = (date.fromisoformat(min(summary["period_from"] or first, first)) - timedelta(days=1)).isoformat()
            # Eine abgeschlossene Periode stimmt zu ihrem Ende ab, nicht zum Eroeffnungstag;
            # eine zweite Abstimmung danach gibt es deshalb nicht.
            coverage = {"proposal": "complete_reconciled", "effective_from": opening_day, "effective_to": proven_to,
                        "opening_balance_decimal": summary["opening_balance_decimal"],
                        "closing_balance_decimal": summary["closing_balance_decimal"], "closing_as_of_date": proven_to}
        else:
            coverage = {"proposal": "partial", "effective_from": first, "effective_to": proven_to, "reason": "no_verifiable_balance"}
    elif parsed["balance_consistent"] and summary["opening_balance_decimal"] is not None and summary["closing_balance_decimal"] is not None:
        start = summary["period_from"] or first
        opening_day = (date.fromisoformat(min(start, first)) - timedelta(days=1)).isoformat()
        coverage = {"proposal": "complete_reconciled", "effective_from": opening_day, "opening_balance_decimal": summary["opening_balance_decimal"],
                    "reconcile_to": {"as_of_date": summary.get("closing_as_of_date") or last, "observed_balance_decimal": summary["closing_balance_decimal"]}}
    else:
        coverage = {"proposal": "partial", "effective_from": first, "reason": "no_verifiable_balance"}
    # Auszuege kommen nicht immer in der richtigen Reihenfolge, und einzelne Monate
    # fehlen (manche Dateinamen tragen das Versanddatum).
    # Passt der Anfangssaldo nicht zum bereits gebuchten Stand, fehlt dazwischen ein
    # Auszug - das gehoert in die Vorschau, nicht in einen Abbruch beim Buchen.
    if coverage["proposal"] == "existing" and first is not None and summary["opening_balance_decimal"] is not None:
        boundary = (date.fromisoformat(summary["period_from"] or first) - timedelta(days=1)).isoformat()
        sign = {"deposit": 1, "withdrawal": -1, "opening_balance": 1, "transfer": 0}
        booked_balance = _booked_balance_at(events, boundary)
        if booked_balance != Decimal(summary["opening_balance_decimal"]):
            if parsed.get("owner_confirmed_balance"):
                # Aus Gebuchtem und neuen Bewegungen folgt ein anderer Stichtagssaldo.
                new_signed = sum((Decimal(row["amount_decimal"]) * (-1 if row["kind"] == "withdrawal" else 1)
                                  for row in rows if row["status"] == "new"), Decimal("0"))
                booked_total = _booked_balance_at(events, max(row["local_date"] for row in events)) if events else Decimal("0")
                coverage = {"proposal": "gap", "reason": "owner_balance_mismatch", "as_of_date": parsed["owner_confirmed_balance"]["as_of_date"],
                            "expected_balance_decimal": _plain(booked_total + new_signed),
                            "opening_balance_decimal": parsed["owner_confirmed_balance"]["balance_decimal"]}
            else:
                coverage = {"proposal": "gap", "reason": "opening_balance_mismatch", "as_of_date": boundary,
                            "expected_balance_decimal": _plain(booked_balance),
                            "opening_balance_decimal": summary["opening_balance_decimal"]}
    if coverage["proposal"] == "existing" and parsed.get("owner_confirmed_balance") and any(
            period["coverage_mode"] == "partial" for period in periods):
        # Ein bereits teilweise gebuchtes Konto nachtraeglich abzuschliessen braucht den
        # Korrekturweg des Cash-Kerns; ohne ihn wuerde der Abgleich im Kern abgewiesen.
        coverage = {"proposal": "blocked", "reason": "partial_coverage_needs_correction"}
    # Saldoprobe (#524): Bevor ein Abgleich vorgeschlagen wird, muss "gebucht + neu + Korrekturen" den Stand des Auszugs ergeben.
    # Sonst wuerde etwas doppelt oder gar nicht gebucht; der Cash-Kern wiese es erst mitten im Buchen ab.
    # Gebuchte Bewegungen im Zeitraum des Auszugs, zu denen er an diesem Tag gar nichts dieser Art nennt: fehlende Tage.
    stated = {(row["local_date"], *RESTATED_FLOWS[row["kind"]]) for row in rows if row["status"] != "booked"}
    unmatched = sorted(event["local_date"] for event in leftovers if event["event_type"] in ("deposit", "withdrawal") and first is not None
                       and first <= event["local_date"] <= last and (event["local_date"], event["event_type"], event["flow_classification"]) not in stated)
    if restated_block is not None:
        coverage = {"proposal": "gap", **restated_block, "unmatched_count": len(unmatched), **({"period_from": unmatched[0]} if unmatched else {})}
    elif coverage["proposal"] == "existing" and isinstance(coverage.get("reconcile_to"), Mapping) \
            and coverage["reconcile_to"].get("observed_balance_decimal") is not None and events:
        as_of = coverage["reconcile_to"]["as_of_date"]
        complete = any(period["coverage_mode"] == "complete_reconciled" and period["effective_from"] <= as_of
                       and (period["effective_to"] is None or as_of <= period["effective_to"]) for period in periods)
        expected = (_booked_balance_at(events, as_of) + sum((_signed(row) for row in rows if row["status"] == "new" and row["local_date"] <= as_of
                                                             and not row.get("cash_event_booked")), Decimal("0"))
                    + sum((Decimal(item["delta_decimal"]) for item in corrections if item["local_date"] <= as_of), Decimal("0")))
        if complete and expected != Decimal(coverage["reconcile_to"]["observed_balance_decimal"]):
            coverage = {"proposal": "gap", "reason": "statement_balance_mismatch", "as_of_date": as_of, "expected_balance_decimal": _plain(expected),
                        "observed_balance_decimal": coverage["reconcile_to"]["observed_balance_decimal"],
                        "period_from": unmatched[0] if unmatched else None, "unmatched_count": len(unmatched)}
    # Ein unvollstaendiger Stapel wird gar nicht erst gebucht: die fehlende Datei
    # steht im Klartext in der Vorschau.
    if parsed.get("chain_gaps"):
        coverage = {"proposal": "gap", **parsed["chain_gaps"][0]}
    if parsed.get("owner_confirmed_balance") and coverage["proposal"] in {"complete_reconciled", "existing"}:
        coverage["owner_confirmed"] = True
    partial_booked = any(period["coverage_mode"] == "partial" for period in periods)
    confirmation_elsewhere = coverage.get("reason") == "partial_coverage_needs_correction" or (
        coverage["proposal"] == "existing" and partial_booked and not parsed.get("owner_confirmed_balance"))
    validated = cash_reader_validation_v1(parsed["adapter_id"])
    # Bewegungen juenger als der Pruefstand - oder alle neuen, wenn der Leser noch nicht erprobt ist: Vorschau mit dem Auszug vergleichen.
    beyond = sum(row["status"] == "new" and (validated is None or row["local_date"] > validated["through"]) for row in rows)
    reader = {"adapter_id": parsed["adapter_id"], "validated": validated, "beyond_validation_count": beyond}
    counts = {"new": sum(row["status"] == "new" for row in rows), "booked": sum(row["status"] == "booked" for row in rows),
              "interest_new": sum(row["status"] == "new" and row["kind"] == "interest" for row in rows),
              "diagnostics": len(parsed["diagnostics"])}
    restated = {"count": len(corrections), "delta_decimal": _plain(sum((Decimal(item["delta_decimal"]) for item in corrections), Decimal("0"))),
                "first_date": corrections[0]["local_date"] if corrections else None, "last_date": corrections[-1]["local_date"] if corrections else None,
                "reconciliations": [item for group in correction_groups for item in group["reconciliations"]], "step_count": len(correction_groups)}
    return {"cash_statement_preview_version": VERSION, "rows": rows, "counts": counts, "coverage": coverage, "reader": reader,
            "corrections": restated, "correction_groups": correction_groups,
            "files": parsed.get("files", []), "chain_gaps": parsed.get("chain_gaps", []), "held_back": parsed.get("held_back", []),
            "owner_confirmed_balance": parsed.get("owner_confirmed_balance"),
            # Ist das Konto schon ohne Saldo als "teilweise erfasst" gebucht und bringt der Auszug nichts Neues, weist der Kern eine
            # Bestaetigung hier ab (#522, etwa bei einem Krypto-Euro-Konto). Die Karte bietet sie dann nicht an und
            # verweist auf "Saldo pruefen" im Reiter Cash; eine schon eingegebene Bestaetigung laesst sich weiter entfernen.
            "balance_confirmation_possible": bool(dates) and not parsed.get("chain_gaps") and (
                not parsed["balance_consistent"] or bool(parsed.get("owner_confirmed_balance"))) and (
                bool(parsed.get("owner_confirmed_balance")) or not confirmation_elsewhere),
            "balance_confirmation_elsewhere": confirmation_elsewhere,
            "latest_movement_date": last,
            "interest_reversals": parsed.get("interest_reversals", 0),
            "period_first": first, "period_last": last, "balance_consistent": parsed["balance_consistent"],
            "summary": summary, "canonical_write": False}


# ---------------------------------------------------------------- apply
def _commands(preview: Mapping[str, Any], parsed: Mapping[str, Any], scope: Mapping[str, str], include_text: bool) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    evidence = _sha({"source": parsed["source_fingerprint"], "summary": parsed["summary"]})
    coverage = preview["coverage"]
    if coverage["proposal"] == "complete_reconciled":
        opening_day = coverage["effective_from"]
        # Eine offene Periode wird zum Eroeffnungstag abgestimmt und ihr Ende spaeter
        # ueber record_reconciliation belegt; eine begrenzte Periode (Nachtrag vor einer
        # bestehenden Abdeckung) stimmt zu ihrem Ende ab - der Kern verlangt genau das.
        closed = coverage.get("effective_to") is not None
        commands.append({"action_type": "declare_coverage", **scope, "effective_from": opening_day, "effective_to": coverage.get("effective_to"),
                         "coverage_mode": "complete_reconciled", "opening_balance_decimal": coverage["opening_balance_decimal"],
                         "opening_event_time_evidence": "exact_local_zone", "opening_local_time": "23:59:00", "opening_time_zone": TIME_ZONE,
                         "opening_effective_at_utc": _utc(opening_day, "23:59:00"),
                         "reconciliation_as_of_date": coverage["effective_to"] if closed else opening_day,
                         "observed_balance_decimal": coverage["closing_balance_decimal"] if closed else coverage["opening_balance_decimal"],
                         "evidence_fingerprint": evidence})
    elif coverage["proposal"] == "partial":
        commands.append({"action_type": "declare_coverage", **scope, "effective_from": coverage["effective_from"], "effective_to": coverage.get("effective_to"),
                         "coverage_mode": "partial", "opening_balance_decimal": None, "opening_event_time_evidence": None, "opening_local_time": None,
                         "opening_time_zone": None, "opening_effective_at_utc": None, "reconciliation_as_of_date": None,
                         "observed_balance_decimal": None, "evidence_fingerprint": None})
    for row in preview["rows"]:
        if row["status"] != "new":
            continue
        event_type = "withdrawal" if row["kind"] == "withdrawal" else "deposit"
        flow = {"interest": "income_receipt", "deposit": "external_contribution", "withdrawal": "external_withdrawal"}[row["kind"]]
        commands.append({"action_type": "record_cash_event", **scope, "event_type": event_type, "related_account_id": None,
                         "event_time_evidence": "exact_local_zone", "local_date": row["local_date"], "local_time": row["local_time"],
                         "time_zone": TIME_ZONE, "effective_at_utc": _utc(row["local_date"], row["local_time"]),
                         "amount_decimal": row["amount_decimal"], "flow_classification": flow,
                         "_source": {"row": row["source_row_ordinal"], "text": row["text"] if include_text else None}})
        if row["kind"] == "interest":
            commands.append({"action_type": "record_interest_income", **scope, "local_date": row.get("value_date") or row["local_date"],
                             "gross_income_decimal": row.get("gross_income_decimal") or row["amount_decimal"], "linked_cash_event_ref": None,
                             "_source": {"row": row["source_row_ordinal"], "text": row["text"] if include_text else None}})
    reconcile = coverage.get("reconcile_to")
    if reconcile and coverage["proposal"] in {"complete_reconciled", "existing"}:
        commands.append({"action_type": "record_reconciliation", **scope, "as_of_date": reconcile["as_of_date"],
                         "observed_balance_decimal": reconcile["observed_balance_decimal"], "evidence_fingerprint": evidence})
    return commands


def _correction_commands(preview: Mapping[str, Any], parsed: Mapping[str, Any], scope: Mapping[str, str]) -> list[dict[str, Any]]:
    """Je Gruppe neu verteilter Tage eine Revision "correct" (#524): Bewegung, Ertrag und verschobene Abgleiche, Vorgaenger bleiben."""
    evidence = _sha({"source": parsed["source_fingerprint"], "summary": parsed["summary"]})
    commands = []
    for group in preview.get("correction_groups", []):
        refs: list[str] = []
        replacements: list[dict[str, Any]] = []
        for item in group["corrections"]:
            event_type, flow = RESTATED_FLOWS[item["kind"]]
            refs.append(item["cash_record_ref"])
            replacements.append({"action_type": "record_cash_event", **scope, "event_type": event_type, "related_account_id": None,
                                 "event_time_evidence": "exact_local_zone", "local_date": item["local_date"], "local_time": item["local_time"],
                                 "time_zone": TIME_ZONE, "effective_at_utc": _utc(item["local_date"], item["local_time"]),
                                 "amount_decimal": item["amount_decimal"], "flow_classification": flow})
            if item["income_record_ref"] is not None:
                refs.append(item["income_record_ref"])
                replacements.append({"action_type": "record_interest_income", **scope, "local_date": item.get("value_date") or item["local_date"],
                                     "gross_income_decimal": item.get("gross_income_decimal") or item["amount_decimal"], "linked_cash_event_ref": None})
        for item in group["reconciliations"]:
            refs.append(item["record_ref"])
            replacements.append({"action_type": "record_reconciliation", **scope, "as_of_date": item["as_of_date"],
                                 "observed_balance_decimal": item["new_observed_balance_decimal"], "evidence_fingerprint": evidence})
        fingerprint = _sha({"correction": "cash_statement_restated_v1", "source": parsed["source_fingerprint"], "account": scope["account_id"],
                            "predecessors": refs, "replacements": replacements})
        commands.append({"action_type": "correct", "input_mode": "reviewed_import", "source_candidate_fingerprint": fingerprint,
                         "predecessor_refs": refs, "replacements": replacements, "request_ref": "ccrq_" + _sha({"request": fingerprint})[:32]})
    return commands


def apply_cash_statement_import_v1(canonical_path: str | Path, data_space_path: str | Path, context: Any, parsed: Mapping[str, Any],
                                   scope: Mapping[str, str], applied_at_utc: str, *, include_text: bool = False,
                                   max_commands: int | None = None) -> dict[str, Any]:
    """Applies the reviewed commands through the Cash coverage authority, one batch per call.

    Every command carries a request ref derived from its content, so a repeated or
    resumed import replays completed commands read-only instead of duplicating them.
    """
    if set(scope) != {"portfolio_id", "account_id", "cash_asset_id"}:
        _abort("cash_statement_input_invalid")
    preview = preview_cash_statement_import_v1(data_space_path, context, parsed, scope["account_id"])
    if preview["coverage"]["proposal"] in {"blocked", "gap"}:
        _abort("cash_statement_coverage_conflict")
    applied = replayed = 0
    datetime.strptime(applied_at_utc, "%Y-%m-%dT%H:%M:%SZ")  # format check before any write
    # Zuerst die neu verteilten Tage (#524), je Gruppe eine Revision; ein spaeterer Aufruf rechnet die Vorschau neu und findet die
    # erledigten nicht mehr. Erst danach die neuen Bewegungen und der Abgleich - der passt erst zum korrigierten Stand.
    corrections = _correction_commands(preview, parsed, scope)
    budget = None if max_commands is None else max(1, int(max_commands))
    # In Teilaufrufen hoechstens RESTATED_PER_CALL Korrekturen: Jede ist eine eigene Revision, die Oberflaeche zeigt so den Fortschritt.
    for command in corrections[:len(corrections) if budget is None else min(budget, RESTATED_PER_CALL)]:
        try:
            proposal = preview_desktop_cash_coverage_command_v1(canonical_path, data_space_path, context, command)
            confirmation = build_desktop_cash_coverage_confirmation_v1(
                proposal, context, "cccf_" + _sha({"confirm": command["request_ref"]})[:32], applied_at_utc, applied_at_utc)
            apply_desktop_cash_coverage_command_v1(canonical_path, data_space_path, context, command, confirmation, applied_at_utc)
        except Exception as error:
            raise CashStatementImportV1Error(getattr(error, "code", "cash_statement_apply_failed")) from None
        applied += 1
    if budget is not None:
        budget -= applied
    open_corrections = len(corrections) - applied
    commands = _commands(preview, parsed, scope, include_text)
    # Chunked application for progress feedback: a later call recomputes the preview, so
    # finished movements are skipped and an interrupted pair replays read-only.
    store = Path(data_space_path) / STORE_AREA / STORE_NAME
    done = set(read_desktop_cash_coverage_reviewed_import_state_v1(store, context)["applied_source_candidate_fingerprints"]) if store.exists() else set()
    fingerprints = []
    for command in commands:
        source_note = command.pop("_source", None)
        fingerprints.append(_sha({"import": "cash_statement_v1", "source": parsed["source_fingerprint"], "account": scope["account_id"], "command": command, "note": source_note}))
    # Half-finished pairs from an interrupted run: the finished half is already committed.
    pending = [(command, candidate) for command, candidate in zip(commands, fingerprints) if candidate not in done]
    replayed = len(commands) - len(pending)
    batch = [] if open_corrections else (pending if budget is None else pending[:budget])
    if batch:
        # Ein Stapel, eine Pruefung des ganzen Journals: die Buchungszeit waechst linear
        # mit der Zahl der Bewegungen statt quadratisch (#184, 19.09.2026).
        items = [{"reviewed": {"reviewed_cash_coverage_candidate_version": 1, "source_candidate_fingerprint": candidate, "mapped_command": command},
                  "request_ref": "ccrq_" + candidate[:32]} for command, candidate in batch]
        try:
            outcome = apply_desktop_cash_coverage_reviewed_batch_v1(canonical_path, data_space_path, context, items, applied_at_utc, applied_at_utc)
        except Exception as error:
            raise CashStatementImportV1Error(getattr(error, "code", "cash_statement_apply_failed")) from None
        applied += outcome["applied_command_count"]
        replayed += outcome["replayed_command_count"]
        provenance = _record_cash_provenance(data_space_path, context, parsed["adapter_id"], [candidate for _command, candidate in batch], applied_at_utc)
    else:
        provenance = "nothing_to_record"
    remaining = open_corrections + len(pending) - len(batch)
    return {"cash_statement_apply_version": VERSION, "status": "completed" if remaining == 0 else "in_progress", "provenance_status": provenance,
            "applied_command_count": applied, "replayed_command_count": replayed, "remaining_command_count": remaining,
            "total_command_count": len(corrections) + len(commands), "corrected_step_count": len(corrections) - open_corrections,
            "new_movement_count": preview["counts"]["new"], "booked_movement_count": preview["counts"]["booked"],
            "coverage": preview["coverage"]["proposal"], "canonical_write": False}


def _record_cash_provenance(data_space_path: str | Path, context: Any, adapter_id: str, fingerprints: list[str], recorded_at_utc: str) -> str:
    """Herkunft je Buchung (rc.378): je gebuchtem Cash-Befehl der Leser, der den Auszug gelesen hat. Der Auszug wird bei jedem
    Buchungsaufruf neu gelesen, die Kennung stammt also von genau dem Leser, der die Bewegungen geliefert hat. Gebucht ist schon -
    ein Fehler beim Festhalten wird gemeldet, macht die Buchung aber nicht rueckgaengig."""
    try:
        identity = reader_plugins.reader_identity_v1(adapter_id, "cash")
        result = record_reader_provenance_v1(data_space_path, context, [
            {"booking_kind": "cash_command", "booking_key": fingerprint, "readers": [identity]} for fingerprint in fingerprints], recorded_at_utc)
    except (AssetActivityReferenceV1Error, reader_plugins.StatementReaderBlocked) as error:
        return "failed:" + error.code
    return result["status"]


def preview_cash_statement_gross_interest_corrections_v1(data_space_path: str | Path, context: Any, parsed: Mapping[str, Any], account_id: str,
                                                         consider_from: str | None = None) -> dict[str, Any]:
    """Read-only: welche gebuchten Zinsertraege nennt dieser Auszug brutto?

    Der Monatsauszug einiger Institute nennt nur den Betrag, der aufs Konto kam; der
    Ertrag wird dann netto gebucht und der allgemeine Topf bleibt um die einbehaltene
    Steuer zu niedrig. Nennt eine andere Quelle desselben Vorgangs den Bruttozins, ist
    das eine Korrektur am gebuchten Ertrag - kein zweiter Write (#465).

    consider_from (#462): Vorschlaege vor diesem Tag werden nur gezaehlt - etwa bewusst nicht angehobene Ertraege eines
    entschiedenen Zeitraums. Die Bewegungen selbst prueft der Import weiter ueber den ganzen Auszug (Saldoprobe).
    """
    if consider_from is not None and (not isinstance(consider_from, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", consider_from) is None):
        _abort("cash_statement_input_invalid")
    preview = preview_cash_statement_import_v1(data_space_path, context, parsed, account_id)
    rows = []
    before = 0
    for row in preview["rows"]:
        gross = row.get("gross_income_decimal")
        booked = row.get("income_booked_decimal")
        if row["kind"] != "interest" or gross is None or booked is None or row.get("income_booked_record_ref") is None:
            continue
        if Decimal(gross) == Decimal(booked):
            continue
        if consider_from is not None and (row.get("income_booked_on") or row["local_date"]) < consider_from:
            before += 1; continue
        rows.append({"local_date": row.get("income_booked_on") or row["local_date"],
                     "booked_gross_income_decimal": booked, "gross_income_decimal": gross,
                     "withheld_tax_decimal": _plain(Decimal(gross) - Decimal(booked)),
                     "cash_amount_decimal": row["amount_decimal"], "text": row["text"],
                     "predecessor_record_ref": row["income_booked_record_ref"]})
    total = sum((Decimal(row["withheld_tax_decimal"]) for row in rows), Decimal("0"))
    return {"cash_statement_gross_correction_version": VERSION, "account_id": account_id, "rows": rows,
            "correction_count": len(rows), "withheld_tax_total_decimal": _plain(total), "consider_from": consider_from,
            "out_of_window_count": before, "confirmation_required": bool(rows), "canonical_write": False}


def apply_cash_statement_gross_interest_corrections_v1(canonical_path: str | Path, data_space_path: str | Path, context: Any,
                                                       parsed: Mapping[str, Any], scope: Mapping[str, str], applied_at_utc: str,
                                                       *, max_corrections: int | None = None, consider_from: str | None = None) -> dict[str, Any]:
    """Hebt die netto gebuchten Zinsertraege dieses Auszugs auf brutto.

    Jede Korrektur laeuft als eigene Revision durch die Cash-Autoritaet: eigener
    Vorschlag, eigene Bestaetigung, eigener Beleg, Vorgaenger bleibt erhalten. Der
    Geldfluss bleibt unberuehrt - auf dem Konto landete der Nettobetrag. Ein zweiter
    Lauf findet nichts mehr, weil der Ertrag dann brutto gebucht ist.
    """
    if set(scope) != {"portfolio_id", "account_id", "cash_asset_id"}:
        _abort("cash_statement_input_invalid")
    datetime.strptime(applied_at_utc, "%Y-%m-%dT%H:%M:%SZ")  # format check before any write
    preview = preview_cash_statement_gross_interest_corrections_v1(data_space_path, context, parsed, scope["account_id"], consider_from)
    pending = preview["rows"] if max_corrections is None else preview["rows"][:max(1, int(max_corrections))]
    applied = 0
    for row in pending:
        command = {"action_type": "correct", "input_mode": "reviewed_import",
                   "source_candidate_fingerprint": _sha({"correction": "cash_statement_gross_interest_v1",
                                                         "source": parsed["source_fingerprint"], "row": row}),
                   "predecessor_refs": [row["predecessor_record_ref"]],
                   "replacements": [{"action_type": "record_interest_income", **scope,
                                     "local_date": row["local_date"], "gross_income_decimal": row["gross_income_decimal"],
                                     "linked_cash_event_ref": None}]}
        command["request_ref"] = "ccrq_" + _sha({"request": command["source_candidate_fingerprint"]})[:32]
        try:
            proposal = preview_desktop_cash_coverage_command_v1(canonical_path, data_space_path, context, command)
            confirmation = build_desktop_cash_coverage_confirmation_v1(
                proposal, context, "cccf_" + _sha({"confirm": command["request_ref"]})[:32], applied_at_utc, applied_at_utc)
            apply_desktop_cash_coverage_command_v1(canonical_path, data_space_path, context, command, confirmation, applied_at_utc)
        except Exception as error:
            raise CashStatementImportV1Error(getattr(error, "code", "cash_statement_apply_failed")) from None
        applied += 1
    remaining = len(preview["rows"]) - len(pending)
    return {"cash_statement_gross_correction_version": VERSION, "status": "completed" if remaining == 0 else "in_progress",
            "corrected_income_count": applied, "remaining_correction_count": remaining,
            "withheld_tax_total_decimal": preview["withheld_tax_total_decimal"], "canonical_write": False}


__all__ = ["CashStatementImportV1Error", "cash_reader_validation_v1", "confirm_cash_statement_balance_v1", "detect_cash_statement_adapters_v1", "list_cash_movements_v1", "list_cash_statement_adapters_v1", "parse_cash_statement_v1", "parse_cash_statement_set_v1",
           "preview_cash_statement_import_v1", "apply_cash_statement_import_v1",
           "preview_cash_statement_gross_interest_corrections_v1", "apply_cash_statement_gross_interest_corrections_v1"]


def list_cash_movements_v1(data_space_path: str | Path, context: Any, account_id: str | None) -> dict[str, Any]:
    """Read-only movement list and running balance per Cash account for the transaction view."""
    projection = _projection(Path(data_space_path), context)
    pick = lambda rows: [row for row in rows if account_id is None or row["account_id"] == account_id]
    movements = []
    for row in pick(projection["cash_events"]):
        # The opening balance is itself a Cash event of the complete coverage declaration.
        sign = {"deposit": 1, "withdrawal": -1, "opening_balance": 1, "transfer": 0}.get(row["event_type"], 0)
        movements.append({"account_id": row["account_id"], "local_date": row["local_date"], "local_time": row.get("local_time"),
                          "event_type": row["event_type"], "flow_classification": row["flow_classification"],
                          "amount_decimal": _plain(Decimal(row["amount_decimal"])), "signed_decimal": _plain(Decimal(row["amount_decimal"]) * sign)})
    movements.sort(key=lambda row: (row["local_date"], row["local_time"] or ""))
    periods = pick(projection["coverage_periods"])
    balance = sum((Decimal(row["signed_decimal"]) for row in movements), Decimal(0))
    incomes = pick(projection["income_events"])
    reconciliations = sorted(pick(projection["reconciliations"]), key=lambda row: row["as_of_date"])
    modes = sorted({row["coverage_mode"] for row in periods})
    return {"cash_movements_version": VERSION, "movements": list(reversed(movements)), "movement_count": len(movements),
            "interest_total_decimal": _plain(sum((Decimal(row["gross_income_decimal"]) for row in incomes), Decimal(0))),
            "interest_count": len(incomes), "balance_decimal": _plain(balance) if periods else None,
            "coverage_modes": modes, "last_reconciliation": None if not reconciliations else
            {"as_of_date": reconciliations[-1]["as_of_date"], "observed_balance_decimal": _plain(Decimal(reconciliations[-1]["observed_balance_decimal"]))}}
