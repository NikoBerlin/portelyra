"""Selbsttest eines Kursanbieter-Plugins (price_provider_v1, #495, rc.382), nach dem Muster der Leser (rc.379).

Stufe 1: die erfundenen Testantworten des Plugins (``fixtures``) - das Ergebnis muss genau der Erwartung entsprechen.
Stufe 2: veraenderte Testantworten (abgeschnitten, einzelne Bytes vertauscht, anderer HTTP-Status, anderer Inhaltstyp) - jedes
Ergebnis muss die Pruefung des Kerns bestehen; ein Absturz oder eine ungueltige Form ist ein Befund.
Stufe 3: erfundene Antworten aus dem Erzeuger des Plugins (``generate``) - das Ergebnis muss der mitgelieferten Erwartung entsprechen.

Alles laeuft in einem Vorgang (ein Plugin-Prozess), ohne Netz.
"""
from __future__ import annotations

import base64
import json
import random
from typing import Any, Iterable

from migrations.reference import price_provider_plugins_v1 as providers

GENERATOR_OPERATIONS = ("daily_history", "fx_daily_history", "search")
_STATUS_VARIANTS = (200, 400, 429, 500, 503)
_CONTENT_TYPES = ("application/json", "text/html", None)


def _response(value: dict[str, Any]) -> dict[str, Any]:
    if "body_base64" in value:
        body = base64.b64decode(value["body_base64"])
    else:
        body = str(value["body_text"]).encode("utf-8")
    return {"status": int(value["status"]), "content_type": value.get("content_type"), "body": body}


def _run_fixture(provider_id: str, value: dict[str, Any]) -> Any:
    operation = value["op"]
    if operation == "parse_response":
        return providers.parse_response_v1(provider_id, value["operation"], value["params"], _response(value))
    if operation == "build_request":
        return providers.build_request_v1(provider_id, value["operation"], value["params"])
    if operation == "fx_symbol":
        return {"symbol": providers.fx_symbol_v1(provider_id, value["base_currency"], value["quote_currency"])}
    raise ValueError(operation)


def _mutations(body: bytes, rng: random.Random, count: int) -> list[bytes]:
    variants: list[bytes] = [b"", body[: len(body) // 2], body + b"}", body.replace(b"chart", b"chrat", 1)]
    for _ in range(count):
        if not body:
            break
        data = bytearray(body)
        for _flip in range(rng.randint(1, 4)):
            position = rng.randrange(len(data))
            data[position] = rng.randrange(256)
        variants.append(bytes(data))
        variants.append(body[: rng.randrange(len(body))])
    return variants


def selftest_v1(provider_id: str, *, seeds: Iterable[int] = range(1, 51), mutations_per_fixture: int = 8, rng_seed: int = 0) -> dict[str, Any]:
    spec = providers.provider_spec_v1(provider_id)
    if spec is None:
        raise providers.PriceProviderBlocked("price_provider_unavailable")
    failures: list[dict[str, str]] = []
    counts = {"fixtures": 0, "mutations": 0, "generated": 0}
    rng = random.Random(rng_seed)

    def failed(stage: str, case: str, problem: str) -> None:
        if len(failures) < 50:
            failures.append({"stage": stage, "case": case, "problem": problem})

    with providers.price_provider_session_v1():
        for input_path, expected_path in spec.fixtures:
            counts["fixtures"] += 1
            name = input_path.rsplit("/", 1)[-1]
            try:
                value = json.loads((spec.plugin_dir / input_path).read_text(encoding="utf-8"))
                expected = json.loads((spec.plugin_dir / expected_path).read_text(encoding="utf-8"))
                result = _run_fixture(provider_id, value)
            except providers.PriceProviderBlocked as error:
                failed("fixtures", name, error.code)
                continue
            except (OSError, ValueError, KeyError, TypeError):
                failed("fixtures", name, "fixture_invalid")
                continue
            if result != expected:
                failed("fixtures", name, "result_differs")
            if value.get("op") != "parse_response":
                continue
            original = _response(value)
            bodies = _mutations(original["body"], rng, mutations_per_fixture)
            variants = [(body, original["status"], original["content_type"]) for body in bodies]
            variants += [(original["body"], status, content_type) for status in _STATUS_VARIANTS for content_type in _CONTENT_TYPES]
            for index, (body, status, content_type) in enumerate(variants):
                counts["mutations"] += 1
                try:
                    providers.parse_response_v1(provider_id, value["operation"], value["params"],
                                                {"status": status, "content_type": content_type, "body": body})
                except providers.PriceProviderBlocked as error:
                    failed("mutations", f"{name}#{index}", error.code)
        if spec.generator:
            for operation in GENERATOR_OPERATIONS:
                if operation not in spec.operations:
                    continue
                seed_list = list(seeds)
                try:
                    generated = providers.run_generate_v1(provider_id, operation, seed_list)
                except providers.PriceProviderBlocked as error:
                    failed("generated", operation, error.code)
                    continue
                for seed, item in zip(seed_list, generated):
                    counts["generated"] += 1
                    case = f"{operation}#{seed}"
                    value = item.get("value") if item.get("ok") else None
                    if not isinstance(value, dict) or set(value) != {"params", "response", "expected"}:
                        failed("generated", case, item.get("code", "generator_output_invalid") if not item.get("ok") else "generator_output_invalid")
                        continue
                    try:
                        result = providers.parse_response_v1(provider_id, operation, value["params"], _response(value["response"]))
                    except providers.PriceProviderBlocked as error:
                        failed("generated", case, error.code)
                        continue
                    except (KeyError, TypeError, ValueError):
                        failed("generated", case, "generator_output_invalid")
                        continue
                    if result != value["expected"]:
                        failed("generated", case, "result_differs")
    return {"provider_id": provider_id, "plugin_id": spec.plugin_id, "plugin_version": spec.plugin_version,
            "isolated": providers.isolation_available_v1(), "passed": not failures, "counts": counts, "failures": failures}


__all__ = ["GENERATOR_OPERATIONS", "selftest_v1"]
