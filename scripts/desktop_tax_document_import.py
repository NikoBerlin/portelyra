#!/usr/bin/env python3
"""CLI-Grenze fuer die Uebernahme der Ertraegnisaufstellung (#459, #465): JSON ueber stdin/stdout.

documents: die Ertraegnisaufstellungen (nur diese Art) der Konten von Instituten mit Leser in der Ablage, je Datei ein Kennzeichen.
preview:   was die Aufstellung uebernehmen liesse, ohne Schluessel des Bestands.
apply:     uebernimmt genau diese Vorschau (Pruefwert) - mit Bestaetigung.
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.statement_archive_v1 import StatementArchiveV1Error, list_statement_files_v1  # noqa: E402
from migrations.reference.tax_document_import_v1 import (  # noqa: E402
    TaxDocumentImportV1Error, apply_income_statement_v1, income_statement_account_ids_v1, preview_income_statement_v1, public_preview_v1,
)
from migrations.reference import statement_reader_checks_v1 as reader_checks  # noqa: E402
from migrations.reference.statement_reader_plugins_v1 import StatementReaderBlocked, reader_identity_v1  # noqa: E402
from migrations.reference.asset_activity_reference_v1 import activity_reference_scope_v1 as _context  # noqa: E402


def _readers(preview):
    """Pruefstand (rc.380): der Leser, der diese Ertraegnisaufstellung gelesen hat (Plugin des Instituts)."""
    return [reader_identity_v1(preview["reader_id"], "income_statement")]


def _accounts_of(preview):
    """Die Konten, die diese Aufstellung beruehrt (Posten und Zinsen) - der Pruefstand gilt je Portfolio dieser Konten."""
    internal = preview.get("_internal") or {}
    accounts = {row.get("_account_id") for row in internal.get("rows") or []}
    accounts.add((internal.get("interest") or {}).get("_account_id"))
    return sorted(account for account in accounts if isinstance(account, str) and account) or None

# Nur Ertraegnisaufstellungen (#536, Festlegung 04.11.2026): Die Art pflegt der Eigentuemer in der Ablage selbst ("Art ändern");
# bis rc.357 bot die Karte auch Steuerbescheinigungen an.
KINDS = ["income_statement"]


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise TaxDocumentImportV1Error("tax_document_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def _documents(space, context):
    """Die Steuerdokumente der Konten des Instituts in der Ablage, neueste zuerst; das Kennzeichen haengt am Pruefwert."""
    accounts = income_statement_account_ids_v1(space)
    if not accounts:
        return []
    files = list_statement_files_v1(space, context, accounts, 2016, 2100, KINDS)["files"]
    out = {}
    for item in files:
        token = "txf_" + hashlib.sha256(item["file_sha256"].encode("utf-8")).hexdigest()[:24]
        out[token] = {"token": token, "kind": item["document_kind"], "year": (item.get("period_from") or "")[:4] or None,
                      "name": item.get("original_name") or "Dokument", "_path": item["path"]}
    return sorted(out.values(), key=lambda row: (row["year"] or "", row["name"]), reverse=True)


def _source(space, context, token):
    hit = [row for row in _documents(space, context) if row["token"] == token]
    if len(hit) != 1:
        raise TaxDocumentImportV1Error("tax_document_input_invalid")
    path = Path(hit[0]["_path"])
    return path.read_bytes(), hit[0]["name"] if hit[0]["name"].lower().endswith((".pdf", ".txt")) else path.name


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if isinstance(value, dict) and isinstance(value.get("data_space_path"), str):   # installierte Leser-Plugins (rc.381)
            from migrations.reference.statement_reader_plugins_v1 import use_data_space_plugins_v1
            use_data_space_plugins_v1(value["data_space_path"])
        if command == "documents":
            space, context = _expect(value)
            result = {"contract_version": "tax_document_documents_v1", "documents": [{key: item for key, item in row.items() if not key.startswith("_")}
                                                                                     for row in _documents(space, context)], "canonical_write": False}
        elif command == "preview":
            space, context = _expect(value, "token")
            source, name = _source(space, context, value["token"])
            full = preview_income_statement_v1(space, context, source, name)
            result = public_preview_v1(full)
            # Die Summe gleicht der Kern mit Zeile 7 ab (Summenprobe); ungepruefter Leser: Hinweis und Haekchen vor dem Uebernehmen.
            try:
                result = {**result, "reader_check": {"status": "ready", **reader_checks.reader_checks_v1(space, _context(context), _readers(full), _accounts_of(full),
                                                                                                      balance_checked=True)}}
            except (reader_checks.StatementReaderCheckV1Error, StatementReaderBlocked) as error:
                result = {**result, "reader_check": {"status": "unavailable", "code": getattr(error, "code", "statement_reader_check_store_invalid"),
                                                     "acknowledgment_required": True, "notes": [], "hints": []}}
        elif command == "apply":
            space, context = _expect(value, "token", "preview_fingerprint", "recorded_at_utc", "confirmed", "reader_check_acknowledged")
            if not isinstance(value["reader_check_acknowledged"], bool):
                raise TaxDocumentImportV1Error("tax_document_input_invalid")
            source, name = _source(space, context, value["token"])
            full = preview_income_statement_v1(space, context, source, name)
            accounts = _accounts_of(full)
            reader_checks.require_reader_checks_v1(space, _context(context), _readers(full), value["reader_check_acknowledged"], accounts)
            result = apply_income_statement_v1(space / "canonical.sqlite", space, context, source, name, value["preview_fingerprint"],
                                               value["recorded_at_utc"], value["confirmed"])
            try:   # nach dem Uebernehmen festhalten; scheitert das, bleibt die Uebernahme stehen und die Meldung sagt es
                recorded = reader_checks.confirm_reader_checks_v1(space, _context(context), _readers(full), value["reader_check_acknowledged"], accounts,
                                                                  value["recorded_at_utc"], 1, int(result.get("taken_count") or 0))["recorded_count"]
            except reader_checks.StatementReaderCheckV1Error as error:
                recorded = "failed:" + error.code
            result = {**result, "reader_check_recorded": recorded}
        else:
            raise TaxDocumentImportV1Error("tax_document_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (TaxDocumentImportV1Error, StatementArchiveV1Error, reader_checks.StatementReaderCheckV1Error, StatementReaderBlocked, OSError, KeyError, TypeError,
            ValueError, sqlite3.Error, json.JSONDecodeError) as error:
        code = getattr(error, "code", "tax_document_input_invalid")
        print(json.dumps({"status": "blocked", "code": code if isinstance(code, str) and code.startswith(("tax_document_", "statement_reader_")) else "tax_document_store_invalid"},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
