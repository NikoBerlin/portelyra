#!/usr/bin/env python3
"""Static local Python/R source-closure validation for Desktop release snapshots."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from typing import Iterable, Mapping


CLOSURE_VERSION = 1
PYTHON_ROOTS = ("apps", "migrations", "workers", "scripts")
R_ROOTS = PYTHON_ROOTS + ("packages",)
_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
_R_SOURCE_CALL = re.compile(r"(?<![A-Za-z0-9_.])(?:source|sys\.source)\s*\(")
_R_STRING = re.compile(r"(?P<quote>['\"])(?P<value>(?:\\.|(?!\1).)*)\1", re.DOTALL)
_R_VECTOR_ASSIGNMENT = re.compile(
    r"(?P<name>[A-Za-z.][A-Za-z0-9._]*)\s*<-\s*c\s*\((?P<body>[^()]*)\)",
    re.DOTALL,
)


@dataclass(frozen=True)
class DesktopReleaseSourceClosureReportV1:
    closure_version: int
    status: str
    python_source_count: int
    python_required_source_count: int
    python_local_edge_count: int
    r_source_count: int
    r_local_edge_count: int


class DesktopReleaseSourceClosureError(ValueError):
    """Internal detail is retained for tests; release boundaries emit only a fixed code."""

    def __init__(self, missing_paths: Iterable[str] = (), *, syntax_invalid: bool = False):
        self.missing_paths = tuple(sorted(set(missing_paths)))
        self.syntax_invalid = bool(syntax_invalid)
        super().__init__("desktop_release_transitive_source_closure_invalid")


def _safe_path(value: str) -> bool:
    if not isinstance(value, str) or not value or _SAFE_RELATIVE.fullmatch(value) is None:
        return False
    return all(part not in {".", ".."} for part in value.split("/"))


def _module_candidates(module: str) -> tuple[str, str]:
    stem = module.replace(".", "/")
    return f"{stem}.py", f"{stem}/__init__.py"


def _controlled_module(module: str) -> bool:
    return bool(module) and module.split(".", 1)[0] in PYTHON_ROOTS


def _resolve_module(
    module: str,
    *,
    source_path: str,
    available: set[str],
    universe: set[str],
    require_controlled: bool,
    missing: set[str],
) -> str | None:
    candidates = list(_module_candidates(module))
    if "." not in module:
        parent = PurePosixPath(source_path).parent.as_posix()
        candidates = [f"{parent}/{module}.py", f"{parent}/{module}/__init__.py", *candidates]
    for candidate in candidates:
        if candidate in universe or candidate in available:
            if candidate not in available:
                missing.add(candidate)
            return candidate
    if require_controlled or _controlled_module(module):
        candidate = _module_candidates(module)[0]
        missing.add(candidate)
        return candidate
    return None


def _absolute_from_module(node: ast.ImportFrom, source_path: str) -> str:
    module = node.module or ""
    if node.level == 0:
        return module
    package = list(PurePosixPath(source_path).parent.parts)
    remove = node.level - 1
    if remove > len(package):
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    base = package[: len(package) - remove]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _python_edges(
    path: str,
    payload: bytes,
    *,
    available: set[str],
    universe: set[str],
    missing: set[str],
) -> set[str]:
    try:
        text = payload.decode("utf-8", errors="strict")
        tree = ast.parse(text, filename=path)
    except (UnicodeError, SyntaxError):
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    edges: set[str] = set()
    importlib_aliases = {"importlib"}
    import_module_aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_aliases.add(alias.asname or alias.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_module(
                    alias.name,
                    source_path=path,
                    available=available,
                    universe=universe,
                    require_controlled=_controlled_module(alias.name),
                    missing=missing,
                )
                if target is not None:
                    edges.add(target)
        elif isinstance(node, ast.ImportFrom):
            module = _absolute_from_module(node, path)
            target = _resolve_module(
                module,
                source_path=path,
                available=available,
                universe=universe,
                require_controlled=node.level > 0 or _controlled_module(module),
                missing=missing,
            )
            if target is not None:
                edges.add(target)
            if target is not None and target.endswith("/__init__.py"):
                for alias in node.names:
                    if alias.name == "*" or not re.fullmatch(r"[a-z][a-z0-9_]*", alias.name):
                        continue
                    child_module = f"{module}.{alias.name}" if module else alias.name
                    child = _resolve_module(
                        child_module,
                        source_path=path,
                        available=available,
                        universe=universe,
                        require_controlled=_controlled_module(child_module),
                        missing=missing,
                    )
                    if child is not None:
                        edges.add(child)
        elif isinstance(node, ast.Call):
            dynamic_name = None
            if isinstance(node.func, ast.Name) and node.func.id == "__import__":
                dynamic_name = "__import__"
            elif isinstance(node.func, ast.Name) and node.func.id in import_module_aliases:
                dynamic_name = "import_module"
            elif (
                isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in importlib_aliases
                and node.func.attr == "import_module"
            ):
                dynamic_name = "import_module"
            if dynamic_name and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                module = node.args[0].value
                target = _resolve_module(
                    module,
                    source_path=path,
                    available=available,
                    universe=universe,
                    require_controlled=_controlled_module(module),
                    missing=missing,
                )
                if target is not None:
                    edges.add(target)
    return edges


def _strip_r_comments(text: str) -> str:
    output: list[str] = []
    quote: str | None = None
    escaped = False
    comment = False
    for character in text:
        if comment:
            if character == "\n":
                comment = False
                output.append(character)
            continue
        if quote is not None:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in {"'", '"'}:
            quote = character
            output.append(character)
        elif character == "#":
            comment = True
        else:
            output.append(character)
    return "".join(output)


def _r_strings(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for match in _R_STRING.finditer(text):
        value = match.group("value")
        value = value.replace("\\\"", '"').replace("\\'", "'").replace("\\\\", "\\")
        values.append(value)
    return tuple(values)


def _balanced_call(text: str, opening: int) -> str:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return text[opening + 1:index]
    raise DesktopReleaseSourceClosureError(syntax_invalid=True)


def _normalize_r_target(parts: Iterable[str], source_path: str) -> str | None:
    values = list(parts)
    for index, value in enumerate(values):
        if value in R_ROOTS:
            candidate = "/".join(values[index:])
            return candidate if candidate.endswith(".R") and _safe_path(candidate) else None
        if any(value.startswith(root + "/") for root in R_ROOTS):
            candidate = "/".join(values[index:])
            return candidate if candidate.endswith(".R") and _safe_path(candidate) else None
    for value in values:
        if value.endswith(".R") and "/" in value and _safe_path(value):
            return value
        if value.endswith(".R") and _safe_path(value):
            candidate = (PurePosixPath(source_path).parent / value).as_posix()
            return candidate if candidate.split("/", 1)[0] in R_ROOTS and _safe_path(candidate) else None
    return None


def _r_edges(path: str, payload: bytes) -> set[str]:
    try:
        text = _strip_r_comments(payload.decode("utf-8", errors="strict"))
    except UnicodeError:
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    edges: set[str] = set()
    vectors = {
        match.group("name"): _r_strings(match.group("body"))
        for match in _R_VECTOR_ASSIGNMENT.finditer(text)
    }
    for match in re.finditer(
        r"(?P<name>[A-Za-z.][A-Za-z0-9._]*)\s*<-\s*file\.path\s*\([^\n]*?c\s*\((?P<body>.*?)\)\s*\)",
        text,
        re.DOTALL,
    ):
        values = tuple(value for value in _r_strings(match.group("body")) if value.endswith(".R"))
        if values:
            vectors[match.group("name")] = values
    loop_items: dict[str, str] = {
        match.group("item"): match.group("vector")
        for match in re.finditer(
            r"for\s*\(\s*(?P<item>[A-Za-z.][A-Za-z0-9._]*)\s+in\s+(?P<vector>[A-Za-z.][A-Za-z0-9._]*)\s*\)",
            text,
        )
        if match.group("vector") in vectors
    }
    loop_values: dict[str, tuple[str, ...]] = {}
    for match in re.finditer(
        r"lapply\s*\(\s*(?P<vector>[A-Za-z.][A-Za-z0-9._]*)\s*,\s*function\s*\(\s*(?P<item>[A-Za-z.][A-Za-z0-9._]*)\s*\)",
        text,
    ):
        if match.group("vector") in vectors:
            loop_values[match.group("item")] = vectors[match.group("vector")]

    for match in _R_SOURCE_CALL.finditer(text):
        expression = _balanced_call(text, match.end() - 1)
        strings = _r_strings(expression)
        expanded_by_loop = False
        # Expand finite lapply variables used in file.path(...).
        for variable, values in loop_values.items():
            if re.search(rf"\b{re.escape(variable)}\b", expression) is None:
                continue
            expanded_by_loop = True
            for value in values:
                expanded = re.sub(rf"\b{re.escape(variable)}\b", f'"{value}"', expression)
                expanded_target = _normalize_r_target(_r_strings(expanded), path)
                if expanded_target is None:
                    raise DesktopReleaseSourceClosureError(syntax_invalid=True)
                edges.add(expanded_target)
        for variable, vector in loop_items.items():
            if re.fullmatch(rf"\s*{re.escape(variable)}\s*(?:,.*)?", expression, re.DOTALL) is None:
                continue
            expanded_by_loop = True
            for value in vectors[vector]:
                target = _normalize_r_target((value,), path)
                if target is None:
                    raise DesktopReleaseSourceClosureError(syntax_invalid=True)
                edges.add(target)
        if not expanded_by_loop:
            target = _normalize_r_target(strings, path)
            if target is not None:
                edges.add(target)
        for variable, values in loop_values.items():
            if re.search(rf"\b{re.escape(variable)}\b", expression) is None:
                continue
            # The expansion was already handled above. This branch only makes a
            # non-finite dynamic variable fail closed instead of accepting a partial path.
            if not values:
                raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    return edges


def validate_desktop_release_source_closure_v1(
    files: Mapping[str, bytes], *, universe_files: Mapping[str, bytes] | None = None,
) -> DesktopReleaseSourceClosureReportV1:
    if not isinstance(files, Mapping) or not files:
        raise DesktopReleaseSourceClosureError(syntax_invalid=True)
    normalized: dict[str, bytes] = {}
    for path, payload in files.items():
        if not _safe_path(path) or not isinstance(payload, bytes):
            raise DesktopReleaseSourceClosureError(syntax_invalid=True)
        normalized[path] = payload
    available = set(normalized)
    universe_payloads = dict(normalized)
    if universe_files is not None:
        for path, payload in universe_files.items():
            if not _safe_path(path) or not isinstance(payload, bytes):
                raise DesktopReleaseSourceClosureError(syntax_invalid=True)
            universe_payloads[path] = payload
    universe = set(universe_payloads)

    python_paths = sorted(
        path for path in available
        if path.endswith(".py") and path.split("/", 1)[0] in PYTHON_ROOTS
    )
    r_paths = sorted(path for path in available if path.endswith(".R"))
    python_edges: set[tuple[str, str]] = set()
    r_edges: set[tuple[str, str]] = set()
    missing: set[str] = set()
    required_python: set[str] = set(python_paths)
    pending = list(python_paths)
    parsed: set[str] = set()
    while pending:
        path = pending.pop()
        if path in parsed:
            continue
        parsed.add(path)
        try:
            targets = _python_edges(
                path, universe_payloads[path], available=available, universe=universe, missing=missing,
            )
        except DesktopReleaseSourceClosureError as error:
            missing.update(error.missing_paths)
            if error.syntax_invalid:
                raise
            continue
        python_edges.update((path, target) for target in targets)
        for target in targets:
            if target.endswith(".py") and target.split("/", 1)[0] in PYTHON_ROOTS:
                required_python.add(target)
                if target in universe_payloads and target not in parsed:
                    pending.append(target)
    for path in r_paths:
        for target in _r_edges(path, normalized[path]):
            r_edges.add((path, target))
            if target not in available:
                missing.add(target)
    if missing:
        raise DesktopReleaseSourceClosureError(missing)
    return DesktopReleaseSourceClosureReportV1(
        closure_version=CLOSURE_VERSION,
        status="complete",
        python_source_count=len(python_paths),
        python_required_source_count=len(required_python),
        python_local_edge_count=len(python_edges),
        r_source_count=len(r_paths),
        r_local_edge_count=len(r_edges),
    )


__all__ = [
    "CLOSURE_VERSION",
    "DesktopReleaseSourceClosureError",
    "DesktopReleaseSourceClosureReportV1",
    "validate_desktop_release_source_closure_v1",
]
