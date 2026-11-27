"""Selbsttest der Leser-Plugins (rc.379, #486).

Jeder Leser durchlaeuft ihn, auch die mitgelieferten. Drei Stufen, alle abgeschottet wie im Betrieb:

1. Testbelege: genau getroffen, in zwei frischen Prozessen gleich und in einem gemeinsamen Prozess in vertauschter Reihenfolge
   gleich - ein Leser darf sich nichts von frueheren Belegen merken. Die Form wird streng geprueft; ein Testbeleg, der bewusst in der
   Zukunft liegt, ist am echten Datum unplausibel und wird nur gezaehlt.
2. Veraenderte Belege: aus den Testbelegen zufaellig verstuemmelte Fassungen (abgeschnitten, Zeilen weg, doppelt oder vertauscht,
   Zeichen gekippt, Fremdzeile, anderer Zeichensatz, leer). Erlaubt sind ein Ergebnis in gueltiger Form oder ein Code aus der festen
   Liste. Durch faellt ein Absturz, eine Zeitueberschreitung, ein fremder Code und jeder Formfehler (falsche Typen, unbekannte Felder
   oder Arten, negative Betraege, ungueltige Daten). Nur unplausible Werte - ein Tag nach heute, eine Buchung ausserhalb des
   genannten Zeitraums - werden gezaehlt, nicht als Fehler: Verstuemmelte Ziffern ergeben sie zwangslaeufig, und der Kern weist sie
   im Betrieb ab (Festlegung 08.11.2026).
3. Erfundene Belege: Bietet ein Leser einen Erzeuger ("generator": true), baut der je Startwert einen erfundenen Beleg samt
   erwartetem Ergebnis; der Leser muss ihn in einem frischen Prozess genau treffen, der Beleg muss die Erkennungsregeln erfuellen.
   Grenze, offen benannt: Der Erzeuger stammt vom Plugin. Eine falsche Deutung des Formats findet er nicht - dafuer gibt es den
   Pruefstand an den eigenen Belegen (rc.380).

Der Bericht nennt Leser, Belegnamen, Veraenderungen und Codes, nie Inhalte. Der Selbsttest schreibt nichts in den Datenraum.
"""
from __future__ import annotations

import contextlib
import random
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterator, Sequence

from migrations.reference import statement_reader_plugins_v1 as readers

VERSION = 1
MUTATIONS = ("truncate", "drop_line", "duplicate_line", "shuffle_lines", "flip_bytes", "garbage_line", "recode", "empty")
TEXT_EXTENSIONS = (".txt", ".csv")


def _validate(domain: str, value: Any, plausibility: bool = True) -> None:
    """Ergebnis nach dem Bereich pruefen wie im Betrieb; plausibility=False prueft nur die Form. Wirft StatementReaderBlocked."""
    if domain == "cash":
        readers.validate_cash_result_v1(value, plausibility=plausibility)
    elif domain in ("securities", "fx"):
        from migrations.reference import securities_statement_import_v1 as securities  # noqa: PLC0415
        readers.validate_securities_result_v1(value, securities.REASONS, plausibility=plausibility)
    elif domain == "crypto":
        from migrations.reference import crypto_statement_import_v1 as crypto  # noqa: PLC0415
        readers.validate_crypto_result_v1(value, crypto._VALIDATION_REASONS, plausibility=plausibility)
    elif domain == "reward":
        readers.validate_reward_result_v1(value, plausibility=plausibility)
    elif domain == "income_statement":
        readers.validate_income_statement_result_v1(value)
    else:
        raise readers.StatementReaderBlocked("statement_reader_output_invalid")


def _as_text(content: bytes | str, file_name: str, domain: str) -> str:
    """Wie der Kern im Betrieb: Textbelege als UTF-8 (sonst Ersatzzeichen), PDF ueber pdftotext. Die Byte-Order-Mark schneidet nur der
    Krypto-Import vorher ab; Wertpapier- und Devisenleser bekommen sie mit."""
    if isinstance(content, str):
        text = content
    elif file_name.lower().endswith(".pdf"):
        from migrations.reference import securities_statement_import_v1 as securities  # noqa: PLC0415
        return securities._text(content, file_name)
    else:
        text = content.decode("utf-8", errors="replace")
    return text.lstrip("\ufeff") if domain == "crypto" else text


def _read(spec: readers.ReaderSpec, documents: Sequence[tuple[bytes | str, str]]) -> list[dict[str, Any]]:
    """Belege mit genau diesem Leser lesen, wie der Kern im Betrieb (Bytes- oder Textbereich)."""
    if spec.domain in readers.BYTE_DOMAINS:
        from migrations.reference import cash_statement_import_v1 as cash  # noqa: PLC0415
        sources = [(content if isinstance(content, bytes) else content.encode("utf-8"), name) for content, name in documents]
        prepared = cash._plugin_documents(sources) if spec.domain == "cash" else [(data, name, None) for data, name in sources]
        return readers.run_reader_v1(spec.reader_id, prepared, spec.domain)
    return readers.run_text_reader_v1(spec.reader_id, spec.domain, [(_as_text(content, name, spec.domain), name) for content, name in documents])


def _plain_result(result: dict[str, Any]) -> Any:
    return {"ok": True, "value": readers._to_json(result["value"])} if result["ok"] else {"ok": False, "code": result["code"]}


def _mutate(content: bytes, kind: str, rng: random.Random) -> bytes:
    lines = content.splitlines(keepends=True)
    if kind == "truncate":
        return content[:rng.randrange(0, max(1, len(content)))]
    if kind == "drop_line" and len(lines) > 1:
        index = rng.randrange(len(lines)); return b"".join(lines[:index] + lines[index + 1:])
    if kind == "duplicate_line" and lines:
        index = rng.randrange(len(lines)); return b"".join(lines[:index + 1] + lines[index:])
    if kind == "shuffle_lines" and len(lines) > 2:
        head, body = lines[:1], lines[1:]; rng.shuffle(body); return b"".join(head + body)
    if kind == "flip_bytes" and content:
        data = bytearray(content)
        for _ in range(min(8, len(data))):
            data[rng.randrange(len(data))] = rng.randrange(256)
        return bytes(data)
    if kind == "garbage_line":
        garbage = "".join(rng.choice("abcdefghij0123456789;,.:-€ \t\"'") for _ in range(rng.randrange(1, 80))).encode("utf-8") + b"\n"
        index = rng.randrange(len(lines) + 1) if lines else 0
        return b"".join(lines[:index] + [garbage] + lines[index:])
    if kind == "recode":
        text = content.decode("utf-8", errors="replace")
        return text.encode("utf-16") if rng.random() < 0.5 else text.encode("cp1252", errors="replace")
    if kind == "empty":
        return b""
    return content + b"\n"


@contextlib.contextmanager
def external_plugin_root_v1(plugin_dir: str | Path) -> Iterator[str]:
    """Ein Plugin ausserhalb von plugins/readers pruefen (Vorlage, fremdes Plugin vor der Installation): Kopie mit dem SDK des Kerns
    in einem eigenen Verzeichnis; der Kern liest fuer die Dauer nur dieses. Liefert die plugin_id."""
    source = Path(plugin_dir).resolve()
    if not (source / "manifest.json").is_file() or source.is_symlink():
        raise readers.StatementReaderBlocked("statement_reader_manifest_invalid")
    saved = readers.PLUGIN_ROOT, readers.SDK_DIR
    with tempfile.TemporaryDirectory(prefix="reader-selftest-") as temporary:
        root = Path(temporary) / "readers"
        root.mkdir()
        shutil.copytree(saved[1], root / "sdk")
        import json  # noqa: PLC0415
        plugin_id = json.loads((source / "manifest.json").read_text(encoding="utf-8")).get("plugin_id")
        if not isinstance(plugin_id, str) or not plugin_id or "/" in plugin_id or plugin_id.startswith((".", "_")):
            raise readers.StatementReaderBlocked("statement_reader_manifest_invalid")
        shutil.copytree(source, root / plugin_id, ignore=shutil.ignore_patterns("__pycache__"))
        readers.PLUGIN_ROOT, readers.SDK_DIR = root, root / "sdk"
        readers._EXTERNAL_ONLY = True   # nur dieses Plugin, ohne die im Datenraum installierten
        readers._registry.cache_clear()
        try:
            yield plugin_id
        finally:
            readers.PLUGIN_ROOT, readers.SDK_DIR = saved
            readers._EXTERNAL_ONLY = False
            readers._registry.cache_clear()


def _fixtures(plugin_dir: Path) -> list[dict[str, Any]]:
    import json  # noqa: PLC0415
    manifest = json.loads((plugin_dir / "manifest.json").read_text(encoding="utf-8"))
    found = []
    for fixture in manifest["fixtures"]:
        path = plugin_dir / fixture["input"]
        content: bytes | str = path.read_bytes()
        found.append({"domain": fixture["domain"], "reader_id": fixture["reader_id"], "name": path.name, "content": content,
                      "expected": json.loads((plugin_dir / fixture["expected"]).read_text(encoding="utf-8"))})
    return found


def _expected_matches(result: dict[str, Any], expected: Any) -> bool:
    """Genau getroffen. Einzelangaben verworfener Krypto-Zeilen (row_details) vergleicht er nur, wenn die Erwartung sie nennt; die
    Zaehlung je Grund vergleicht er immer."""
    if not result["ok"]:
        return False
    value = result["value"]
    if isinstance(value, dict) and isinstance(expected, dict) and "row_details" in value and "row_details" not in expected:
        value = {key: item for key, item in value.items() if key != "row_details"}
    return readers._to_json(value) == readers._to_json(expected)


def _variants(content: bytes | str, rng: random.Random, count: int) -> list[tuple[str, bytes]]:
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    start = rng.randrange(len(MUTATIONS))
    return [(MUTATIONS[(start + step) % len(MUTATIONS)], _mutate(data, MUTATIONS[(start + step) % len(MUTATIONS)], rng)) for step in range(count)]


def _check_variants(spec: readers.ReaderSpec, entry: dict[str, Any], name: str, origin: str, variants: list[tuple[str, bytes]]) -> None:
    """Stufe 2: veraenderte Belege ohne Absturz, ohne Zeitgrenze, ohne fremden Code und ohne Formfehler; unplausible nur gezaehlt."""
    allowed = readers.READER_ERROR_CODES[spec.domain] | readers.SDK_ERROR_CODES
    results = _read(spec, [(data, name) for _kind, data in variants])
    for (kind, _data), result in zip(variants, results):
        entry["mutations"]["count"] += 1
        if origin == "generated":
            entry["mutations"]["of_generated"] = entry["mutations"].get("of_generated", 0) + 1
        if result["ok"]:
            try:
                _validate(spec.domain, result["value"], plausibility=False)
            except readers.StatementReaderBlocked:
                entry["mutations"]["failures"].append({"document": name, "origin": origin, "mutation": kind, "finding": "malformed_result"})
                continue
            try:
                _validate(spec.domain, result["value"])
            except readers.StatementReaderBlocked:
                entry["mutations"]["rejected_by_core"] += 1   # unplausibel (Tag nach heute, ausserhalb des Zeitraums)
        elif result["code"] not in allowed:
            finding = {"statement_reader_failed": "crash", "statement_reader_timeout": "timeout"}.get(result["code"], "foreign_code")
            entry["mutations"]["failures"].append({"document": name, "origin": origin, "mutation": kind, "finding": finding, "code": result["code"]})


def selftest_plugin_v1(plugin_id: str, *, seed: int = 0, mutations_per_fixture: int = 8, generated_per_reader: int = 5,
                       mutations_per_generated: int = 2) -> dict[str, Any]:
    """Selbsttest eines geladenen Plugins (alle drei Stufen). Bestanden heisst: keine Abweichung, kein Absturz, keine Zeitgrenze,
    kein fremder Code. Startwert und Zahlen machen den Lauf wiederholbar."""
    specs = [spec for spec in readers.reader_specs_v1() if spec.plugin_id == plugin_id]
    problems = [item["code"] for item in readers.reader_plugin_problems_v1() if item["plugin_id"] == plugin_id]
    report: dict[str, Any] = {"selftest_version": VERSION, "plugin_id": plugin_id, "seed": seed, "problems": problems, "readers": []}
    if problems or not specs:
        report["passed"] = False
        report["problems"] = problems or ["statement_reader_unavailable"]
        return report
    plugin_dir = specs[0].plugin_dir
    report["plugin_version"] = specs[0].plugin_version
    fixtures = _fixtures(plugin_dir)
    by_key = {(spec.domain, spec.reader_id): spec for spec in specs}
    rng = random.Random(seed)
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    for spec in specs:
        entries[(spec.domain, spec.reader_id)] = {"reader_id": spec.reader_id, "domain": spec.domain,
                                                  "fixtures": {"count": 0, "failures": []}, "order": {"failures": []},
                                                  "mutations": {"count": 0, "rejected_by_core": 0, "failures": []},
                                                  "generated": None}

    # Stufe 1a: jeder Testbeleg genau, in zwei frischen Prozessen gleich.
    fresh: dict[int, Any] = {}
    for index, fixture in enumerate(fixtures):
        spec = by_key[(fixture["domain"], fixture["reader_id"])]
        entry = entries[(spec.domain, spec.reader_id)]
        entry["fixtures"]["count"] += 1
        first, second = _read(spec, [(fixture["content"], fixture["name"])])[0], _read(spec, [(fixture["content"], fixture["name"])])[0]
        fresh[index] = _plain_result(first)
        if _plain_result(first) != _plain_result(second):
            entry["fixtures"]["failures"].append({"document": fixture["name"], "finding": "two_fresh_processes_differ"})
        elif not _expected_matches(first, fixture["expected"]):
            entry["fixtures"]["failures"].append({"document": fixture["name"], "finding": "expected_mismatch",
                                                  "code": None if first["ok"] else first["code"]})
        else:
            # Form streng; unplausibel (etwa ein Testbeleg, der bewusst in der Zukunft liegt) nur gezaehlt - vor einer Installation laeuft
            # der Selbsttest mit dem echten Datum, die mitgelieferten Testbelege liegen in 2027.
            try:
                _validate(spec.domain, first["value"], plausibility=False)
            except readers.StatementReaderBlocked as error:
                entry["fixtures"]["failures"].append({"document": fixture["name"], "finding": "malformed_result", "code": error.code})
            else:
                try:
                    _validate(spec.domain, first["value"])
                except readers.StatementReaderBlocked:
                    entry["fixtures"]["implausible_today"] = entry["fixtures"].get("implausible_today", 0) + 1

    # Stufe 1b: alle Testbelege des Plugins in einem gemeinsamen Prozess, vertauschte Reihenfolge - gleich wie frisch.
    order = list(range(len(fixtures)))
    rng.shuffle(order)
    with readers.reader_session_v1():
        for index in order + order[::-1]:
            fixture = fixtures[index]
            spec = by_key[(fixture["domain"], fixture["reader_id"])]
            if _plain_result(_read(spec, [(fixture["content"], fixture["name"])])[0]) != fresh[index]:
                failures = entries[(spec.domain, spec.reader_id)]["order"]["failures"]
                if not any(item["document"] == fixture["name"] for item in failures):
                    failures.append({"document": fixture["name"], "finding": "depends_on_earlier_documents"})

        # Stufe 2: veraenderte Testbelege (die erfundenen folgen in Stufe 3, sie erreichen Zweige, die kein Testbeleg zeigt).
        for fixture in fixtures:
            spec = by_key[(fixture["domain"], fixture["reader_id"])]
            _check_variants(spec, entries[(spec.domain, spec.reader_id)], fixture["name"], "fixture",
                            _variants(fixture["content"], rng, mutations_per_fixture))

        # Stufe 3: erfundene Belege aus dem Erzeuger des Plugins.
        for spec in specs:
            if not spec.generator:
                continue
            entry = entries[(spec.domain, spec.reader_id)]
            entry["generated"] = {"count": 0, "failures": []}
            seeds = [seed * 1000 + number for number in range(generated_per_reader)]
            try:
                made = readers.run_generate_v1(spec.reader_id, spec.domain, seeds)
            except readers.StatementReaderBlocked as error:
                entry["generated"]["failures"].append({"seed": None, "finding": "generator_invalid", "code": error.code}); continue
            for number, item in zip(seeds, made):
                entry["generated"]["count"] += 1
                if not item["ok"]:
                    entry["generated"]["failures"].append({"seed": number, "finding": "generator_failed", "code": item["code"]}); continue
                document = item["value"]
                text = _as_text(document["content"], document["file_name"], spec.domain)
                if not readers.detection_passes_v1(spec.reader_id, readers.detection_texts_v1([text]), spec.domain):
                    entry["generated"]["failures"].append({"seed": number, "finding": "detection_rules_not_met"}); continue
                result = _read(spec, [(document["content"], document["file_name"])])[0]
                if not _expected_matches(result, document["expected"]):
                    entry["generated"]["failures"].append({"seed": number, "finding": "expected_mismatch", "code": None if result["ok"] else result["code"]})
                    continue
                try:
                    _validate(spec.domain, result["value"])
                except readers.StatementReaderBlocked as error:
                    entry["generated"]["failures"].append({"seed": number, "finding": "core_rejects", "code": error.code})
                    continue
                # Stufe 2 auch am erfundenen Beleg.
                if mutations_per_generated:
                    _check_variants(spec, entry, document["file_name"], "generated", _variants(document["content"], rng, mutations_per_generated))
            # Derselbe Startwert ergibt denselben Beleg, auch in einem frischen Prozess.
            if seeds and made and made[0]["ok"]:
                again = readers.run_generate_v1(spec.reader_id, spec.domain, seeds[:1])
                if readers._to_json(again[0].get("value")) != readers._to_json(made[0]["value"]):
                    entry["generated"]["failures"].append({"seed": seeds[0], "finding": "generator_not_repeatable"})
    report["readers"] = [entries[key] for key in sorted(entries)]
    report["passed"] = not any(entry["fixtures"]["failures"] or entry["order"]["failures"] or entry["mutations"]["failures"]
                               or (entry["generated"] or {}).get("failures") for entry in report["readers"])
    report["generator_count"] = sum(1 for entry in report["readers"] if entry["generated"] is not None)
    return report


def selftest_all_v1(*, seed: int = 0, mutations_per_fixture: int = 8, generated_per_reader: int = 5, mutations_per_generated: int = 2) -> dict[str, Any]:
    """Selbsttest aller geladenen Plugins; verworfene Plugins stehen mit Grund im Bericht."""
    plugin_ids = sorted({spec.plugin_id for spec in readers.reader_specs_v1()} | {item["plugin_id"] for item in readers.reader_plugin_problems_v1()})
    reports = [selftest_plugin_v1(plugin_id, seed=seed, mutations_per_fixture=mutations_per_fixture, generated_per_reader=generated_per_reader,
                                  mutations_per_generated=mutations_per_generated)
               for plugin_id in plugin_ids]
    return {"selftest_version": VERSION, "seed": seed, "plugins": reports, "passed": all(report["passed"] for report in reports)}


__all__ = ["MUTATIONS", "external_plugin_root_v1", "selftest_all_v1", "selftest_plugin_v1"]
