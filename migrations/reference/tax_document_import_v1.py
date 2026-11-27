"""Steuerpflichtige Betraege laut Beleg (#459) und Bruttozinsen (#465): die Ertraegnisaufstellung eines Instituts.

Welche Aufstellungen lesbar sind, sagen die Leser-Plugins im Bereich income_statement (#486); mitgeliefert ist die der Baader Bank.
Der Leser, dessen Erkennung passt, liest; die Konten sind die seines Instituts (Woerter aus dem Rezept seines Plugins).

Der Aktien-Topf kann um wenige Cent von der Bescheinigung abweichen, etwa bei Verkaeufen in
Fremdwaehrung: Die Bank rechnet jeden Bestandteil einzeln in Euro um und rundet ihn, Portelyra rechnet den Gewinn
exakt aus den gebuchten Betraegen. Die Ertraegnisaufstellung nennt im Einzelnachweis je Posten den Kapitalertrag: nach
Teilfreistellung, vor Freistellungsauftrag und Verlustverrechnung. Diesen Betrag uebernimmt der Leser als "steuerpflichtig laut
Beleg"; die Steuer rechnet Portelyra weiter selbst (Festlegung 04.11.2026: der Freibetrag darf die Projektion nicht verwaessern).

Festlegungen (04.11.2026):
- Uebernommen wird nur, was hoechstens 1 Euro von der eigenen Rechnung abweicht. Groessere Abweichungen sind ein Befund und
  bleiben bei der eigenen Rechnung - etwa eine Ersatzbemessungsgrundlage nach einem Depotuebertrag ohne Anschaffungsdaten.
- Gegenprobe: Die Summe der Einzelposten muss Zeile 7 des Summennachweises ergeben, sonst uebernimmt der Leser nichts.
- Zinsen: Die Aufstellung nennt den Bruttozins; netto gebuchte Zinsen hebt der Leser mit derselben Korrektur an wie der
  Cash-Import (#465). Er bucht keine Bewegungen.

Liest nur bis zur Bestaetigung; geschrieben wird an den Speicher neben dem Buchungsbestand und - fuer Zinsen - ueber die
Cash-Autoritaet. Kein Providerzugriff, kein Netzzugriff, kein kanonischer Write.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping
import hashlib
import json
import re
import sqlite3
import subprocess
import tempfile

from migrations.reference import statement_reader_plugins_v1 as reader_plugins

VERSION = 1
CONTRACT = "tax_document_import_v1"
TOLERANCE = Decimal("1.00")
MAX_BYTES = 30 * 1024 * 1024
FAILURE_CODES = (
    "tax_document_input_invalid",
    "tax_document_source_invalid",
    "tax_document_unreadable",
    "tax_document_confirmation_required",
    "tax_document_preview_stale",
    "tax_document_store_invalid",
    # Gruende des Leser-Plugins (rc.377): bleiben als eigener Grund sichtbar (Festlegung 08.11.2026).
    "statement_reader_isolation_unavailable",
    "statement_reader_output_invalid",
    "statement_reader_failed",
    "statement_reader_timeout",
    "statement_reader_unavailable",
)

# Die Leseregeln der Aufstellung stehen seit rc.377 im Plugin des Instituts (etwa plugins/readers/baader/reader_income.py).


class TaxDocumentImportV1Error(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code if code in FAILURE_CODES else "tax_document_store_invalid"


def tax_document_import_v1_error_codes() -> tuple[str, ...]:
    return FAILURE_CODES


def _abort(code: str) -> None:
    raise TaxDocumentImportV1Error(code)


def _plain(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value.normalize(), "f")
    return "0" if text in ("-0", "") else text


def income_statement_text_v1(source: bytes, file_name: str) -> str:
    """Nur lokale Textgewinnung: poppler pdftotext, kein Netz; die Originaldatei bleibt unveraendert."""
    if not isinstance(source, bytes) or not 0 < len(source) <= MAX_BYTES or not isinstance(file_name, str):
        _abort("tax_document_source_invalid")
    if not file_name.lower().endswith(".pdf"):
        return source.decode("utf-8", errors="replace")
    with tempfile.TemporaryDirectory(prefix="tax-document-pdf-") as temporary:
        path = Path(temporary) / "document.pdf"
        path.write_bytes(source)
        try:
            completed = subprocess.run(["pdftotext", "-layout", "-nopgbrk", str(path), "-"], capture_output=True, timeout=120)
        except (OSError, subprocess.SubprocessError):
            _abort("tax_document_unreadable")
        if completed.returncode != 0:
            _abort("tax_document_unreadable")
        return completed.stdout.decode("utf-8", errors="replace")


def income_statement_readers_v1() -> list[Any]:
    """Die Leser fuer Ertraegnisaufstellungen (Bereich income_statement): mitgelieferte zuerst, je nach Kennung."""
    return sorted(reader_plugins.reader_specs_v1("income_statement"), key=lambda spec: (spec.origin != "shipped", spec.reader_id))


def _reader_for(text: str) -> Any:
    texts = reader_plugins.detection_texts_v1([text])
    return next((spec for spec in income_statement_readers_v1() if reader_plugins.detection_passes_v1(spec.reader_id, texts, "income_statement")), None)


def parse_income_statement_v1(text: str) -> dict[str, Any]:
    """Zerlegt den Text einer Ertraegnisaufstellung in Posten. Rechnet nichts, liest nur ab.

    Seit rc.377 (#486) liest das Plugin des Instituts abgeschottet (Bereich income_statement): je Posten Art (sale, dividend, interest;
    fund, wenn eine Teilfreistellung dabeisteht; ignored fuer Kreditzinsen; unclear, wenn die Zeile des Kapitalertrags nicht eindeutig
    ist), ISIN, Stueck, Valuta und steuerlicher Zufluss, der Kapitalertrag ("taxable") und sein Anteil an Zeile 7, dazu Zeile 7 des
    Summennachweises. Die Summe der Posten und ob sie Zeile 7 ergeben, rechnet der Kern hier selbst nach.
    """
    if not isinstance(text, str):
        _abort("tax_document_source_invalid")
    spec = _reader_for(text)
    if spec is None:
        _abort("tax_document_source_invalid")
    # Der genaue Grund des Lesers bleibt sichtbar: fehlende Abschottung, Absturz, Zeitgrenze, ungueltiges Ergebnis, nicht installiert.
    try:
        result = reader_plugins.run_text_reader_v1(spec.reader_id, "income_statement", [(text, "ertraegnisaufstellung.txt")])[0]
        if not result["ok"]:
            _abort(result["code"] if result["code"] in FAILURE_CODES else "statement_reader_failed")
        parsed = reader_plugins.validate_income_statement_result_v1(result["value"])
    except reader_plugins.StatementReaderBlocked as error:
        _abort(error.code if error.code in FAILURE_CODES else "statement_reader_failed")
    postings = parsed["postings"]
    summary_line7 = parsed["summary_line7"]
    used = [item for item in postings if item["kind"] != "ignored"]
    total = sum((item["line7"] or Decimal(0) for item in used), Decimal(0))
    check = "missing" if summary_line7 is None else ("consistent" if total == summary_line7 else "mismatch")
    return {"contract_version": CONTRACT, "reader_id": spec.reader_id, "institution_label": spec.institution, "tax_year": parsed["tax_year"],
            "postings": postings, "summary_line7": summary_line7, "postings_line7": total, "check": check}


def _scope(context_value: Any):
    from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, activity_reference_scope_v1
    try:
        return activity_reference_scope_v1(context_value)
    except AssetActivityReferenceV1Error:
        _abort("tax_document_input_invalid")


def _matches(words: tuple[str, ...], label: str | None) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", (label or "").lower()) for word in words)


def _accounts(space: Path, words: tuple[str, ...]) -> dict[str, Any]:
    """Die Konten des Instituts (Institutsangabe mit einem seiner Woerter) mit Art und Portfolio; Namen nur fuer die Vorschau. Der
    Institutsname ist der gemeinsame Name an diesen Konten."""
    connection = sqlite3.connect(f"file:{space / 'canonical.sqlite'}?mode=ro", uri=True)
    try:
        rows = [row for row in connection.execute("SELECT account_id, portfolio_id, account_type, display_name, institution_label FROM account").fetchall()
                if _matches(words, row[4])]
        isins = dict(connection.execute("SELECT asset_id, isin FROM asset WHERE isin IS NOT NULL").fetchall())
    except sqlite3.Error:
        _abort("tax_document_store_invalid")
    finally:
        connection.close()
    labels = {row[4] for row in rows}
    return {"accounts": {row[0]: {"portfolio_id": row[1], "account_type": row[2], "label": row[3]} for row in rows}, "isins": isins,
            "institution_label": labels.pop() if len(labels) == 1 else None}


def income_statement_account_ids_v1(space_path: str | Path) -> list[str]:
    """Die Konten aller Institute, deren Ertraegnisaufstellung ein Leser liest - fuer die Auswahl der Dokumente in der Ablage."""
    words = tuple(word for spec in income_statement_readers_v1() for word in reader_plugins.plugin_account_words_v1(spec.reader_id, "income_statement"))
    return sorted(_accounts(Path(space_path), words)["accounts"]) if words else []


def _token(document_sha256: str, kind: str, ordinal: int) -> str:
    return "txd_" + hashlib.sha256(f"{document_sha256}|{kind}|{ordinal}".encode("utf-8")).hexdigest()[:24]


def _own_sheets(space: Path, context: Any, tax_year: int, accounts: set[str]) -> list[dict[str, Any]]:
    """Die eigene Rechnung je Ereignis der Konten des Instituts - ohne Werte laut Beleg (sonst verglicht der Leser mit sich selbst)."""
    from workers.reference.tax_event_sheet_v1 import LEDGER_ASSET_TYPES, TaxEventSheetV1Error, build_tax_event_sheets_v1
    kinds = [kind for kind in LEDGER_ASSET_TYPES if kind != "crypto"]
    try:
        model = build_tax_event_sheets_v1(space, context, tax_year, kinds, keep_source_keys=True, use_documents=False)
    except TaxEventSheetV1Error as error:
        _abort("tax_document_store_invalid" if error.code != "tax_event_sheet_input_invalid" else "tax_document_input_invalid")
    if model.get("status") != "ready":
        _abort("tax_document_store_invalid")
    return [sheet for sheet in model["sheets"] if sheet.get("source_key", {}).get("account_ref") in accounts
            and sheet["event_type"] in ("sell", "dividend")]


def preview_income_statement_v1(space_path: str | Path, context_value: Any, source: bytes, file_name: str) -> dict[str, Any]:
    """Was die Aufstellung uebernehmen liesse - je Posten mit der eigenen Rechnung und der Abweichung. Liest nur."""
    from migrations.reference.asset_activity_reference_v1 import read_activity_taxable_documents_v1
    space = Path(space_path); context = _scope(context_value)
    parsed = parse_income_statement_v1(income_statement_text_v1(source, file_name))
    document_sha256 = hashlib.sha256(source).hexdigest()
    known = _accounts(space, reader_plugins.plugin_account_words_v1(parsed["reader_id"], "income_statement"))
    institution = known["institution_label"] or parsed["institution_label"]
    base = {"contract_version": CONTRACT, "tax_year": parsed["tax_year"], "institution_label": institution, "reader_id": parsed["reader_id"],
            "check": parsed["check"],
            "document_sha256": document_sha256, "tolerance_decimal": _plain(TOLERANCE), "provider_access": False, "network_access": False,
            "canonical_write": False}
    if parsed["tax_year"] is None or parsed["check"] != "consistent":
        return {**base, "status": "check_failed", "rows": [], "interest": {"rows": []}, "counts": {}, "preview_fingerprint": None}
    sheets = _own_sheets(space, context, parsed["tax_year"], set(known["accounts"]))
    stored = read_activity_taxable_documents_v1(space, context)["values"]
    taken: set[int] = set(); rows = []
    for item in parsed["postings"]:
        if item["kind"] in ("ignored", "interest"):
            continue
        row = {"token": _token(document_sha256, item["kind"], item["ordinal"]), "kind": item["kind"], "security_name": item["name"],
               "isin": item["isin"], "inflow_date": item["inflow_date"], "bank_taxable_decimal": _plain(item["taxable"]),
               "own_taxable_decimal": None, "difference_decimal": None, "account_label": None, "status": None, "_event_ref": None}
        if item["kind"] == "unclear":
            row["status"] = "unclear"; rows.append(row); continue
        if item["replacement_base"]:
            row["status"] = "replacement_base"
        wanted = "sell" if item["kind"] in ("sale", "fund") else "dividend"
        candidates = [index for index, sheet in enumerate(sheets) if index not in taken and sheet["event_type"] == wanted
                      and known["isins"].get(sheet["source_key"]["asset_id"]) == item["isin"]]
        same_day = [index for index in candidates if sheets[index]["event"]["local_date"] in (item["inflow_date"], item["value_date"])]
        pool = same_day or []
        if not pool:
            row["status"] = row["status"] or "unmatched"; rows.append(row); continue

        def distance(index: int) -> Decimal:
            own = sheets[index]["calculation"].get("taxable_amount")
            return abs(Decimal(str(own)) - item["taxable"]) if own is not None else Decimal("1e12")
        index = min(pool, key=distance); taken.add(index); sheet = sheets[index]
        own = sheet["calculation"].get("taxable_amount")
        row["account_label"] = known["accounts"][sheet["source_key"]["account_ref"]]["label"]
        row["_event_ref"] = sheet["source_key"]["event_ref"]
        row["_account_id"] = sheet["source_key"]["account_ref"]   # Pruefstand je Portfolio (rc.380); nicht im Pruefwert, nicht oeffentlich
        if own is None:
            row["status"] = row["status"] or "own_missing"; rows.append(row); continue
        own_value = Decimal(str(own)); difference = item["taxable"] - own_value
        row["own_taxable_decimal"] = _plain(own_value); row["difference_decimal"] = _plain(difference)
        previous = stored.get(sheet["source_key"]["event_ref"])
        if row["status"] is None:
            if abs(difference) > TOLERANCE:
                row["status"] = "finding"
            elif previous is not None and Decimal(previous["taxable_eur_decimal"]) == item["taxable"]:
                row["status"] = "already"
            else:
                row["status"] = "take"
        rows.append(row)
    interest = _interest_preview(space, context, parsed, document_sha256, known, institution)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    public = [{key: value for key, value in row.items() if not key.startswith("_")} for row in rows]
    fingerprint = hashlib.sha256(json.dumps({"rows": [(row["token"], row["status"], row["bank_taxable_decimal"], row["_event_ref"]) for row in rows],
                                             "interest": interest["fingerprint_basis"], "document": document_sha256},
                                            sort_keys=True).encode("utf-8")).hexdigest()
    return {**base, "status": "ready", "rows": public, "counts": counts, "interest": {key: value for key, value in interest.items() if key != "fingerprint_basis" and not key.startswith("_")},
            "preview_fingerprint": fingerprint, "_internal": {"rows": rows, "interest": interest}}


def _interest_parsed(parsed: Mapping[str, Any], document_sha256: str, institution: str) -> dict[str, Any] | None:
    """Die Zinsposten in der Form eines Cash-Auszugs - nur fuer die Anhebung auf brutto, nie zum Buchen."""
    rows = []
    for item in parsed["postings"]:
        if item["kind"] != "interest" or item["taxable"] is None or not item["value_date"]:
            continue
        rows.append({"source_row_ordinal": item["ordinal"], "local_date": item["value_date"], "kind": "interest",
                     "amount_decimal": _plain(item["taxable"] - item["taxes"]), "gross_income_decimal": _plain(item["taxable"]),
                     "balance_after_decimal": None, "local_time": "12:00:00",
                     "text": f"Zinszahlung Kontokorrent- / Sparkonten ({institution}-Erträgnisaufstellung)"})
    if not rows:
        return None
    # Kennung der Zinsposten: die des Lesers mit "_interest" vor der Version (baader_income_statement_v1 -> ..._interest_v1).
    base, version = parsed["reader_id"].rsplit("_v", 1)
    return {"source_fingerprint": document_sha256, "adapter_id": f"{base}_interest_v{version}", "candidates": rows, "diagnostics": [],
            "summary": {"opening_balance_decimal": None, "closing_balance_decimal": None,
                        "period_from": min(row["local_date"] for row in rows), "period_to": max(row["local_date"] for row in rows)},
            "balance_consistent": False, "balance_anchor_only": False}


def _interest_preview(space: Path, context_value: Any, parsed: Mapping[str, Any], document_sha256: str, known: Mapping[str, Any],
                      institution: str) -> dict[str, Any]:
    """Je Zinsposten: schon brutto gebucht oder anzuheben. Das Konto ist das mit den meisten passenden gebuchten Zinsen."""
    from migrations.reference.cash_statement_import_v1 import CashStatementImportV1Error, preview_cash_statement_gross_interest_corrections_v1, preview_cash_statement_import_v1
    interest = _interest_parsed(parsed, document_sha256, institution)
    count = 0 if interest is None else len(interest["candidates"])
    empty = {"posting_count": count, "account_label": None, "gross_booked_count": 0, "correction_count": 0, "rows": [], "unmatched_count": count,
             "fingerprint_basis": None, "_account_id": None, "_parsed": interest}
    if interest is None:
        return empty
    best = None
    for account_id, account in known["accounts"].items():
        if account["account_type"] not in ("cash", "bank"):
            continue
        try:
            booked = preview_cash_statement_import_v1(space, context_value, interest, account_id)
        except CashStatementImportV1Error:
            continue
        # Gebucht ist ein Zins, wenn Bewegung und Ertrag stehen - brutto (ohne Zusatz) oder noch netto (mit dem alten Ertrag).
        matched = [row for row in booked["rows"] if row.get("kind") == "interest" and row.get("status") == "booked"]
        if matched and (best is None or len(matched) > len(best[1])):
            best = (account_id, matched)
    if best is None:
        return empty
    account_id, matched = best
    corrections = preview_cash_statement_gross_interest_corrections_v1(space, context_value, interest, account_id)
    rows = [{"local_date": row["local_date"], "booked_gross_income_decimal": row["booked_gross_income_decimal"], "gross_income_decimal": row["gross_income_decimal"]}
            for row in corrections["rows"]]
    return {"posting_count": count, "account_label": known["accounts"][account_id]["label"], "gross_booked_count": len(matched) - len(rows),
            "correction_count": len(rows), "rows": rows, "unmatched_count": count - len(matched),
            "fingerprint_basis": {"account": account_id, "rows": rows}, "_account_id": account_id, "_parsed": interest}


def apply_income_statement_v1(canonical_path: str | Path, space_path: str | Path, context_value: Any, source: bytes, file_name: str,
                              preview_fingerprint: str, recorded_at_utc: str, confirmed: bool) -> dict[str, Any]:
    """Uebernimmt, was die Vorschau mit "take" zeigt, und hebt die netto gebuchten Zinsen an. Gebunden an genau diese Vorschau."""
    from migrations.reference.asset_activity_reference_v1 import AssetActivityReferenceV1Error, record_activity_taxable_documents_v1, record_reader_provenance_v1
    if confirmed is not True:
        _abort("tax_document_confirmation_required")
    if not isinstance(recorded_at_utc, str) or re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", recorded_at_utc) is None:
        _abort("tax_document_input_invalid")
    context = _scope(context_value)
    preview = preview_income_statement_v1(space_path, context, source, file_name)
    if preview["status"] != "ready" or preview["preview_fingerprint"] != preview_fingerprint:
        _abort("tax_document_preview_stale")
    label = f"Erträgnisaufstellung {preview['institution_label']} {preview['tax_year']}"
    entries = [{"event_ref": row["_event_ref"], "taxable_eur_decimal": row["bank_taxable_decimal"], "document_label": label,
                "document_sha256": preview["document_sha256"]} for row in preview["_internal"]["rows"] if row["status"] == "take"]
    written, provenance = 0, "nothing_to_record"
    if entries:
        try:
            written = record_activity_taxable_documents_v1(space_path, context, entries, recorded_at_utc, True)["written_count"]
        except AssetActivityReferenceV1Error:
            _abort("tax_document_store_invalid")
        # Herkunft je Betrag (rc.378): der Leser, der die Aufstellung eben gelesen hat. Uebernommen ist schon; ein Fehler hier wird gemeldet.
        try:
            identity = reader_plugins.reader_identity_v1(preview["reader_id"], "income_statement")
            provenance = record_reader_provenance_v1(space_path, context, [
                {"booking_kind": "taxable_document", "booking_key": entry["event_ref"], "readers": [identity]} for entry in entries], recorded_at_utc)["status"]
        except (AssetActivityReferenceV1Error, reader_plugins.StatementReaderBlocked) as error:
            provenance = "failed:" + error.code
    corrected = 0
    interest = preview["_internal"]["interest"]
    if interest["correction_count"]:
        from migrations.reference.cash_statement_import_v1 import CashStatementImportV1Error, apply_cash_statement_gross_interest_corrections_v1
        scope = _interest_scope(Path(space_path), context, interest["_account_id"])
        try:
            result = apply_cash_statement_gross_interest_corrections_v1(canonical_path, space_path, context, interest["_parsed"], scope, recorded_at_utc)
        except CashStatementImportV1Error:
            _abort("tax_document_store_invalid")
        corrected = result["corrected_income_count"]
    return {"contract_version": CONTRACT, "status": "recorded", "tax_year": preview["tax_year"], "taken_count": written,
            "corrected_interest_count": corrected, "provenance_status": provenance, "provider_access": False, "network_access": False, "canonical_write": False}


def _interest_scope(space: Path, context_value: Any, account_id: str) -> dict[str, str]:
    """Portfolio, Konto und Cash-Asset der gebuchten Zinsen dieses Kontos - wie der Cash-Import sie traegt."""
    from migrations.reference.desktop_cash_coverage_v1 import read_desktop_cash_coverage_exchange_projection_v1
    store = space / "cash-coverage-v1" / "cash-coverage.sqlite"
    try:
        projection = read_desktop_cash_coverage_exchange_projection_v1(store, context_value)
    except Exception:
        _abort("tax_document_store_invalid")
    incomes = [row for row in projection.get("income_events", []) if row.get("account_id") == account_id]
    portfolios = {row["portfolio_id"] for row in incomes}; assets = {row["cash_asset_id"] for row in incomes}
    if len(portfolios) != 1 or len(assets) != 1:
        _abort("tax_document_store_invalid")
    return {"portfolio_id": portfolios.pop(), "account_id": account_id, "cash_asset_id": assets.pop()}


def public_preview_v1(preview: Mapping[str, Any]) -> dict[str, Any]:
    """Die Vorschau ohne Schluessel des Bestands - fuer die Oberflaeche."""
    return {key: value for key, value in preview.items() if not key.startswith("_")}


__all__ = ["CONTRACT", "FAILURE_CODES", "TOLERANCE", "TaxDocumentImportV1Error", "apply_income_statement_v1", "income_statement_text_v1",
           "income_statement_account_ids_v1", "income_statement_readers_v1", "parse_income_statement_v1", "preview_income_statement_v1", "public_preview_v1", "tax_document_import_v1_error_codes"]
