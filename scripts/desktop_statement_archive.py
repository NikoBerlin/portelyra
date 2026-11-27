#!/usr/bin/env python3
"""CLI-Grenze fuer die Ablage der Original-Auszuege (JSON ueber stdin/stdout)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

from migrations.reference.statement_archive_v1 import (  # noqa: E402
    StatementArchiveV1Error, close_statement_year_v1, declare_statements_unavailable_v1, list_statement_files_v1, read_statement_archive_overview_v1,
    read_statement_account_states_v1, read_statement_file_v1, read_statement_intake_folder_v1, remove_statement_file_v1, revise_statement_document_v1,
    set_statement_account_closure_v1, set_statement_account_expectation_v1, set_statement_account_inactivity_v1, set_statement_intake_folder_v1,
    store_statement_document_v1,
)
from migrations.reference.statement_archive_suggestion_v1 import suggest_statement_placements_v1  # noqa: E402
from migrations.reference.statement_intake_v1 import list_statement_recipes_v1, scan_statement_intake_v1, store_statement_intake_v1  # noqa: E402


def _expect(value, *names):
    if not isinstance(value, dict) or set(value) != {"context", "data_space_path", *names}:
        raise StatementArchiveV1Error("statement_archive_input_invalid")
    return Path(value["data_space_path"]), value["context"]


def main() -> int:
    try:
        command = sys.argv[1] if len(sys.argv) > 1 else ""
        value = json.load(sys.stdin)
        if isinstance(value, dict) and isinstance(value.get("data_space_path"), str):   # installierte Leser-Plugins (rc.381, Eingang)
            from migrations.reference.statement_reader_plugins_v1 import use_data_space_plugins_v1
            use_data_space_plugins_v1(value["data_space_path"])
        if command == "overview":
            space, context = _expect(value, "year")
            result = read_statement_archive_overview_v1(space, context, value["year"])
        elif command == "store":
            space, context = _expect(value, "source_path", "original_name", "document", "recorded_at_utc", "confirmed")
            result = store_statement_document_v1(space, context, value["source_path"], value["document"], value["recorded_at_utc"], value["confirmed"],
                                                 original_name=value["original_name"])
        elif command == "declare":
            space, context = _expect(value, "declaration", "recorded_at_utc", "confirmed")
            result = declare_statements_unavailable_v1(space, context, value["declaration"], value["recorded_at_utc"], value["confirmed"])
        elif command == "revise":
            space, context = _expect(value, "document_ref", "changes", "recorded_at_utc", "confirmed")
            result = revise_statement_document_v1(space, context, value["document_ref"], value["changes"], value["recorded_at_utc"], value["confirmed"])
        elif command == "expect":
            space, context = _expect(value, "account_id", "statements_expected", "recorded_at_utc", "confirmed")
            result = set_statement_account_expectation_v1(space, context, value["account_id"], value["statements_expected"], value["recorded_at_utc"], value["confirmed"])
        elif command == "close":
            space, context = _expect(value, "year", "account_ids", "declare_rest", "recorded_at_utc", "confirmed")
            result = close_statement_year_v1(space, context, value["year"], value["account_ids"], value["declare_rest"], value["recorded_at_utc"], value["confirmed"])
        elif command == "file":
            space, context = _expect(value, "document_ref")
            result = read_statement_file_v1(space, context, value["document_ref"])
        elif command == "files":
            # Quelle der Importe (#434): die hinterlegten Dateien fuer Konten und Jahre.
            space, context = _expect(value, "account_ids", "year_from", "year_to", "kinds")
            result = list_statement_files_v1(space, context, value["account_ids"], value["year_from"], value["year_to"], value["kinds"])
        elif command == "remove":
            space, context = _expect(value, "document_ref", "recorded_at_utc", "confirmed")
            result = remove_statement_file_v1(space, context, value["document_ref"], value["recorded_at_utc"], value["confirmed"])
        elif command == "suggest":
            # Vorschlag je Datei (#434): Art, Zeitraum und Konten aus dem Inhalt; schreibt nichts.
            space, context = _expect(value, "sources")
            sources = value["sources"]
            if not isinstance(sources, list) or not all(isinstance(item, dict) and set(item) == {"path", "name"} for item in sources):
                raise StatementArchiveV1Error("statement_archive_input_invalid")
            result = suggest_statement_placements_v1(space, context, [(item["path"], item["name"]) for item in sources])
        # Monatlicher Eingang (#513): Konto geschlossen seit, Belegordner, Rezepte, pruefen und ablegen.
        elif command == "closure":
            space, context = _expect(value, "account_id", "closed_on", "recorded_at_utc", "confirmed")
            result = set_statement_account_closure_v1(space, context, value["account_id"], value["closed_on"], value["recorded_at_utc"], value["confirmed"])
        # Konto inaktiv seit (#529 Punkt 1) und die Zustaende aller Konten fuer Eingang, Importe und Datenbasis.
        elif command == "inactivity":
            space, context = _expect(value, "account_id", "inactive_since", "recorded_at_utc", "confirmed")
            result = set_statement_account_inactivity_v1(space, context, value["account_id"], value["inactive_since"], value["recorded_at_utc"],
                                                         value["confirmed"])
        elif command == "account-states":
            space, context = _expect(value)
            result = {"status": "ready", "accounts": read_statement_account_states_v1(space, context),
                      "provider_access": False, "network_access": False, "canonical_write": False}
        elif command == "intake-folder":
            space, context = _expect(value, "folder", "recorded_at_utc", "confirmed")
            result = set_statement_intake_folder_v1(space, context, value["folder"], value["recorded_at_utc"], value["confirmed"])
        elif command == "intake-read":
            space, context = _expect(value)
            result = {"status": "ready", "folder": read_statement_intake_folder_v1(space, context), "recipes": list_statement_recipes_v1(),
                      "provider_access": False, "network_access": False, "canonical_write": False}
        # "include_withdrawn" (rc.320) ist wahlweise: ohne das Feld wie bisher.
        elif command == "intake-scan":
            space, context = _expect(value, *(("include_withdrawn",) if isinstance(value, dict) and "include_withdrawn" in value else ()))
            result = scan_statement_intake_v1(space, context, include_withdrawn=value.get("include_withdrawn", False))
        elif command == "intake-store":
            optional = ("include_withdrawn",) if isinstance(value, dict) and "include_withdrawn" in value else ()
            space, context = _expect(value, "folder_name", "fingerprint", "recorded_at_utc", "confirmed", *optional)
            result = store_statement_intake_v1(space, context, value["folder_name"], value["fingerprint"], value["recorded_at_utc"], value["confirmed"],
                                               include_withdrawn=value.get("include_withdrawn", False))
        else:
            raise StatementArchiveV1Error("statement_archive_input_invalid")
        print(json.dumps({"status": "completed", "result": result}, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        return 0
    except (StatementArchiveV1Error, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        code = getattr(error, "code", "statement_archive_input_invalid")
        print(json.dumps({"status": "blocked", "code": code}, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
