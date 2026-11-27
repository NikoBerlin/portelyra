#!/usr/bin/env python3
"""Host fuer ein Kursanbieter-Plugin (price_provider_v1, #495, rc.382) im abgeschotteten Prozess.

Startet ausschliesslich ueber ``workers/import_plugin_sandbox_v1.py`` (Landlock, kein Netz, Ressourcengrenzen) mit
``python -I -B <host> <request.json> <ausgabeverzeichnis>``. Mit ``"serve": true`` bleibt er offen und nimmt Auftraege zeilenweise
ueber stdin an. Das Plugin ruft nie selbst ab (Festlegung 09.11.2026: Netz nur im Kern): Es baut Anfragen (``build_request``),
liest Antworten (``parse_response``), nennt das Symbol eines Waehrungspaares (``fx_symbol``) und erfindet fuer den Selbsttest
Antworten samt Erwartung (``generate``). Jeder Fehler des Plugins wird zum Code ``price_provider_failed``; ob ein Ergebnis gilt,
prueft der Kern.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys


def _fail(output: Path) -> int:
    (output / "result.json").write_text(json.dumps({"host_error": "price_provider_failed"}), encoding="utf-8")
    return 0


def _load(request: dict):
    # python -I nimmt den Skriptordner nicht in den Suchpfad: den Plugin-Ordner (Module neben dem Einstieg) von Hand.
    sys.path.insert(0, str(Path(request["plugin_dir"])))
    spec = importlib.util.spec_from_file_location("portelyra_price_provider_plugin", request["entry"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    request_path, output = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        module = _load(request)
    except Exception:  # noqa: BLE001 - jedes Ladeproblem ist ein Fehler des Plugins
        return _fail(output)
    if request.get("serve"):
        return _serve(module)
    results = _jobs(module, request["jobs"])
    (output / "result.json").write_text(json.dumps({"results": results}, allow_nan=False), encoding="utf-8")
    return 0


def _jobs(module, jobs: list) -> list:
    results = []
    for job in jobs:
        try:
            operation = job["op"]
            if operation == "build_request":
                value = module.build_request(job["operation"], job["params"])
            elif operation == "parse_response":
                body = Path(job["body_path"]).read_bytes()
                response = {"status": job["status"], "content_type": job["content_type"], "body": body}
                value = module.parse_response(job["operation"], job["params"], response)
            elif operation == "fx_symbol":
                value = module.fx_symbol(job["base_currency"], job["quote_currency"])
            elif operation == "generate":
                value = module.generate(job["operation"], int(job["seed"]))
            else:
                raise ValueError(operation)
            json.dumps(value, allow_nan=False)
            results.append({"ok": True, "value": value})
        except Exception:  # noqa: BLE001 - Absturz, Endlosrekursion oder nicht serialisierbares Ergebnis
            results.append({"ok": False, "code": "price_provider_failed"})
    return results


def _serve(module) -> int:
    """Dauerbetrieb: je Zeile auf stdin ein Auftragsbuendel, je Zeile auf stdout die Antwort mit der Kennung des Auftrags.
    Ausgaben des Plugins gehen nicht in die Antwort: stdout des Plugins zeigt auf stderr (vom Kern verworfen)."""
    answers = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line.decode("utf-8"))
            payload = {"nonce": request["nonce"], "results": _jobs(module, request["jobs"])}
        except Exception:  # noqa: BLE001 - kaputter Auftrag: Antwort ohne passende Kennung, der Kern beendet den Prozess
            payload = {"nonce": None, "host_error": "price_provider_failed"}
        answers.write(json.dumps(payload, allow_nan=False).encode("utf-8") + b"\n")
        answers.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
