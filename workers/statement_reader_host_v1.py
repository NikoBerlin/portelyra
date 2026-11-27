#!/usr/bin/env python3
"""Host fuer ein Leser-Plugin (statement_reader_v1) im abgeschotteten Prozess.

Startet ausschliesslich ueber ``workers/import_plugin_sandbox_v1.py`` (Landlock, kein Netz, Ressourcengrenzen) mit
``python -I -B <host> <request.json> <ausgabeverzeichnis>``. Mit ``"serve": true`` bleibt er offen und nimmt Auftraege zeilenweise
ueber stdin an (rc.375). Laedt genau ein Plugin und fuehrt je Auftrag einen Schritt aus:
``read`` (Beleg als Bytes), ``read_text`` (Beleg als Text), ``detect`` (Erkennung), ``finish`` (Nachbearbeitung ueber den
Stapel), ``combine_documents``/``combine_rows`` (Belege eines Instituts zusammen lesen, rc.376) oder ``generate`` (erfundener
Beleg samt Erwartung fuer den Selbsttest, rc.379). Schreibt ``result.json``. Jeder Fehler des Plugins wird zu einem Code; ob Code und Ergebnis gelten, prueft der Kern.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys

_CODE = re.compile(r"^[a-z][a-z0-9_]{2,79}$")


def _fail(output: Path, code: str) -> int:
    (output / "result.json").write_text(json.dumps({"host_error": code}), encoding="utf-8")
    return 0


def main() -> int:
    request_path, output = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        # python -I nimmt den Skriptordner nicht in den Suchpfad: SDK und Plugin-Ordner (fuer die Module neben dem Einstieg) von Hand.
        sys.path.insert(0, str(Path(request["sdk_dir"])))
        sys.path.insert(0, str(Path(request["plugin_dir"])))
        import portelyra_reader_sdk_v1 as sdk  # noqa: PLC0415 - Pfad steht erst zur Laufzeit fest
        spec = importlib.util.spec_from_file_location("portelyra_reader_plugin", request["entry"])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:  # noqa: BLE001 - jedes Ladeproblem ist ein Fehler des Plugins
        return _fail(output, "statement_reader_failed")
    if request.get("serve"):
        return _serve(module, sdk)
    results = _jobs(module, sdk, request["reader_id"], request["jobs"])
    (output / "result.json").write_text(json.dumps({"results": results}, allow_nan=False), encoding="utf-8")
    return 0


def _jobs(module, sdk, reader_id: str, jobs: list) -> list:
    results = []
    for job in jobs:
        try:
            operation = job["op"]
            if operation == "read":
                source = Path(job["path"]).read_bytes()
                if job.get("lines_path") is not None:
                    sdk._register_pdf_text(source, json.loads(Path(job["lines_path"]).read_text(encoding="utf-8")))
                value = module.read(reader_id, source, job["file_name"])
            elif operation == "read_text":
                value = module.read_text(reader_id, json.loads(Path(job["text_path"]).read_text(encoding="utf-8")), job["file_name"])
            elif operation == "detect":
                value = module.detect(reader_id, json.loads(Path(job["text_path"]).read_text(encoding="utf-8")))
            elif operation == "finish":
                batch = sdk._from_json(json.loads(Path(job["payload_path"]).read_text(encoding="utf-8")))
                value = module.finish(reader_id, batch)
            elif operation == "combine_rows":
                batch = sdk._from_json(json.loads(Path(job["payload_path"]).read_text(encoding="utf-8")))
                value = module.combine_rows(reader_id, batch)
            elif operation == "generate":   # Selbsttest Stufe 3 (rc.379): erfundener Beleg samt Erwartung
                value = module.generate(reader_id, int(job["seed"]), str(job["domain"]))
            elif operation == "combine_documents":
                documents = []
                for item in job["documents"]:
                    source = Path(item["path"]).read_bytes()
                    if item.get("lines_path") is not None:
                        sdk._register_pdf_text(source, json.loads(Path(item["lines_path"]).read_text(encoding="utf-8")))
                    documents.append((source, item["file_name"]))
                value = module.combine_documents(reader_id, documents)
            else:
                raise ValueError(operation)
            encoded = sdk._to_json(value)
            json.dumps(encoded, allow_nan=False)
            results.append({"ok": True, "value": encoded})
        except sdk.ReaderError as error:
            code = error.code if isinstance(error.code, str) and _CODE.match(error.code) else "statement_reader_failed"
            results.append({"ok": False, "code": code})
        except Exception:  # noqa: BLE001 - Absturz, Endlosrekursion oder nicht serialisierbares Ergebnis
            results.append({"ok": False, "code": "statement_reader_failed"})
    sdk._PDF_TEXT.clear()
    return results


def _serve(module, sdk) -> int:
    """Dauerbetrieb (rc.375): je Zeile auf stdin ein Auftragsbuendel, je Zeile auf stdout die Antwort mit der Kennung des Auftrags.
    Ausgaben des Plugins gehen nicht in die Antwort: stdout des Plugins zeigt auf stderr (vom Kern verworfen)."""
    import os
    answers = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line.decode("utf-8"))
            payload = {"nonce": request["nonce"], "results": _jobs(module, sdk, request["reader_id"], request["jobs"])}
        except Exception:  # noqa: BLE001 - kaputter Auftrag: Antwort ohne passende Kennung, der Kern beendet den Prozess
            payload = {"nonce": None, "host_error": "statement_reader_failed"}
        answers.write(json.dumps(payload, allow_nan=False).encode("utf-8") + b"\n")
        answers.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
