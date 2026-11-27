"""Owner-local batch coordinator. No default provider, publication or startup hook.

Callers must supply server-owned bound items; never use a browser payload as an
executor. Hashes bind reviewed contents (including private bindings), not merely
the UI's supplied batch_fingerprint. Persisted results support read-only recovery.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

SHA = re.compile(r"[a-f0-9]{64}")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
AREA = "market-fx-batch-execution-v1"
PREFIX = "desktop_market_fx_batch_"
FETCH_CAPABILITY = ".selected-fetch-authority-v1.json"
FETCH_CAPABILITY_BODY = {"capability_version": 1, "minimum_writer_capability": "selected_market_fx_fetch_grants_v1"}
ERRORS = frozenset(PREFIX + name for name in (
    "input_invalid", "context_invalid", "time_invalid", "confirmation_invalid",
    "store_invalid", "executor_invalid", "provider_call_failed", "recovery_required",
    "busy", "result_invalid", "selection_invalid", "selection_blocked",
))
FALSE_FLAGS = ("automatic_retry", "provider_fallback", "provider_access",
               "network_access", "market_history_write", "fx_history_write", "canonical_write")


class MarketFxBatchExecutionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code if code in ERRORS else PREFIX + "store_invalid"
        super().__init__(self.code)


def _abort(code: str) -> None:
    raise MarketFxBatchExecutionError(code)


def _canon(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        _abort(PREFIX + "input_invalid")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value)).hexdigest()


def _utc(value: Any) -> datetime:
    if not isinstance(value, str) or not UTC.fullmatch(value):
        _abort(PREFIX + "time_invalid")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _abort(PREFIX + "time_invalid")


def _context(value: Any) -> dict[str, str]:
    keys = {"tenant_id", "user_id", "data_space_id"}
    if not isinstance(value, Mapping) or set(value) != keys or any(
        not isinstance(value[k], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value[k])
        for k in keys
    ):
        _abort(PREFIX + "context_invalid")
    return dict(value)


def _batch(value: Any) -> dict[str, Any]:
    if (not isinstance(value, Mapping)
        or value.get("contract_version") != "data_asset_center_market_fx_fetch_batch_preview_v1"
        or value.get("status") != "ready_for_confirmation"
        or not isinstance(value.get("items"), list) or not value["items"]
        or any(type(value.get(k)) is not int or value[k] != len(value["items"])
               for k in ("item_count", "provider_call_count"))
        or type(value.get("silent_drop_count")) is not int or value["silent_drop_count"] != 0
        or value.get("confirmation_required") is not True
        or any(value.get(k) is not False for k in FALSE_FLAGS)
        or not isinstance(value.get("batch_fingerprint"), str)
        or not SHA.fullmatch(value["batch_fingerprint"])):
        _abort(PREFIX + "input_invalid")
    seen = set()
    for item in value["items"]:
        if (not isinstance(item, Mapping) or item.get("kind") not in {"market", "fx"}
            or type(item.get("provider_call_count")) is not int or item["provider_call_count"] != 1
            or item.get("disposition") != "fetch_once"
            or any(not isinstance(item.get(k), str) or not item[k]
                   for k in ("consumer", "route", "start_date", "end_date"))):
            _abort(PREFIX + "input_invalid")
        try:
            start, end = date.fromisoformat(item["start_date"]), date.fromisoformat(item["end_date"])
        except ValueError:
            _abort(PREFIX + "input_invalid")
        if (start.isoformat() != item["start_date"] or end.isoformat() != item["end_date"]
            or end < start or type(item.get("calendar_day_count")) is not int
            or item["calendar_day_count"] != (end - start).days + 1):
            _abort(PREFIX + "input_invalid")
        identity = _sha(item)
        if identity in seen:
            _abort(PREFIX + "input_invalid")
        seen.add(identity)
    return json.loads(_canon(value))


def _check_owner(path: Path, directory: bool) -> None:
    info = path.lstat()
    expected = 0o700 if directory else 0o600
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if (not kind(info.st_mode) or stat.S_IMODE(info.st_mode) != expected
        or info.st_uid != os.geteuid() or (not directory and info.st_nlink != 1)):
        _abort(PREFIX + "store_invalid")


def _space(path: str | Path, context: Mapping[str, str]) -> Path:
    p = Path(path)
    try:
        if not p.is_absolute() or p.resolve(strict=True) != p or p.name != context["data_space_id"]:
            _abort(PREFIX + "store_invalid")
        _check_owner(p, True)
    except OSError:
        _abort(PREFIX + "store_invalid")
    return p


def _origin(space: Path) -> Path:
    from migrations.reference.data_space_relocation_v1 import origin_v1  # Ursprungsort nach einem Restore an einen anderen Ort (#493), sonst der Datenraum selbst.
    return origin_v1(space)


def _area_context(root: Path, context: Mapping[str, str], create: bool = False) -> None:
    path = root / ".context"
    from migrations.reference.data_space_relocation_v1 import origin_v1  # Ursprungsort nach einem Restore an einen anderen Ort (#493), sonst der Datenraum selbst.
    expected = {"context_fingerprint": _sha(context), "data_space_fingerprint": _sha(str(origin_v1(root.parent)))}
    if not os.path.lexists(path) and create:
        if any(p.name != ".lock" for p in root.iterdir()):
            _abort(PREFIX + "store_invalid")
        _write(path, expected)
    if _read(path) != expected:
        _abort(PREFIX + "context_invalid")


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def _locked(space: Path, context: Mapping[str, str], create: bool = False):
    """One writer per batch area, including across processes and provider calls."""
    root = space / AREA
    fd = None
    try:
        if create:
            try:
                root.mkdir(mode=0o700)
            except FileExistsError:
                pass
        _check_owner(root, True)
        # Persist the area directory entry itself before a provider can be called.
        # Also done on replay after an interrupted first-time mkdir.
        _sync_directory(space)
        fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        _check_owner(root / ".lock", False)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _abort(PREFIX + "busy")
        _area_context(root, context, create)
        yield root
    except OSError:
        _abort(PREFIX + "store_invalid")
    finally:
        if fd is not None:
            os.close(fd)


def _write(path: Path, value: Any) -> None:
    """Private file from first byte; durable replace before any external call."""
    temporary = None
    try:
        _check_owner(path.parent, True)
        if os.path.lexists(path):
            _check_owner(path, False)
        fd, temporary = tempfile.mkstemp(prefix=".state-", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(_canon(value) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        _sync_directory(path.parent)
    except OSError:
        _abort(PREFIX + "store_invalid")
    finally:
        if temporary is not None:
            os.unlink(temporary)


def _read(path: Path) -> dict[str, Any]:
    try:
        _check_owner(path.parent, True)
        _check_owner(path, False)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        _abort(PREFIX + "store_invalid")
    if not isinstance(value, dict):
        _abort(PREFIX + "store_invalid")
    return value


def _identity(batch: Mapping[str, Any], context: Mapping[str, str]) -> str:
    return "mfb_" + _sha({"context": context, "batch": batch})[:32]


def confirm_market_fx_batch_v1(batch_value: Any, context_value: Any,
                              issued_at_utc: str, expires_at_utc: str) -> dict[str, Any]:
    batch, context = _batch(batch_value), _context(context_value)
    issued, expires = _utc(issued_at_utc), _utc(expires_at_utc)
    if not 0 < (expires - issued).total_seconds() <= 600:
        _abort(PREFIX + "confirmation_invalid")
    # R's UI fingerprint is an identifier, not proof of this Python payload.
    # Bind the entire normalized content independently, including private bindings.
    body = {"confirmation_version": 2, "batch_fingerprint": batch["batch_fingerprint"],
            "content_fingerprint": _sha(batch), "context_fingerprint": _sha(context),
            "issued_at_utc": issued_at_utc, "expires_at_utc": expires_at_utc,
            "automatic_retry": False}
    return {**body, "confirmation_fingerprint": _sha(body)}


def _selected_ordinals(value: Any, batch: Mapping[str, Any]) -> list[int]:
    if (not isinstance(value, list) or not value or len(value) > len(batch["items"])
        or any(type(n) is not int or not 1 <= n <= len(batch["items"]) for n in value)
        or value != sorted(set(value))):
        _abort(PREFIX + "selection_invalid")
    return list(value)


def confirm_market_fx_selected_batch_v1(data_space_path, batch_value, context_value,
                                        ordinals, issued_at_utc, expires_at_utc):
    batch, context = _batch(batch_value), _context(context_value)
    space = _space(data_space_path, context)
    body = confirm_market_fx_batch_v1(batch, context, issued_at_utc, expires_at_utc)
    del body["confirmation_fingerprint"]
    body.update(confirmation_version=3, selected_ordinals=_selected_ordinals(ordinals, batch),
                data_space_fingerprint=_sha(str(_origin(space))))
    return {**body, "confirmation_fingerprint": _sha(body)}


def _validate_confirmation(value: Any, batch: Mapping[str, Any],
                           context: Mapping[str, str], at: str, space=None) -> None:
    if not isinstance(value, Mapping):
        _abort(PREFIX + "confirmation_invalid")
    if value.get("confirmation_version") == 3:
        expected = confirm_market_fx_selected_batch_v1(space, batch, context,
            value.get("selected_ordinals"), value.get("issued_at_utc"), value.get("expires_at_utc"))
    else:
        expected = confirm_market_fx_batch_v1(batch, context, value.get("issued_at_utc"),
                                             value.get("expires_at_utc"))
    if _canon(value) != _canon(expected) or not _utc(value["issued_at_utc"]) <= _utc(at) <= _utc(value["expires_at_utc"]):
        _abort(PREFIX + "confirmation_invalid")


def _status(items: list[dict[str, Any]]) -> str:
    statuses = {item["status"] for item in items}
    if "provider_call_started" in statuses:
        return "recovery_required"
    if statuses == {"staged"}:
        return "staged"
    return "partial" if statuses & {"staged", "failed"} else "in_progress"


def _persist(path: Path, state: dict[str, Any]) -> None:
    state["status"] = _status(state["items"])
    state["state_fingerprint"] = _sha({k: v for k, v in state.items() if k != "state_fingerprint"})
    _write(path, state)


def _load(path: Path, batch: dict[str, Any], context: dict[str, str]) -> dict[str, Any]:
    _area_context(path.parent, context)
    state = _read(path)
    if (set(state) != {"execution_version", "execution_ref", "context_fingerprint", "content_fingerprint",
                       "batch", "confirmation", "confirmation_consumed", "items", "status", "state_fingerprint"}
        or state.get("execution_version") != 2 or state.get("execution_ref") != _identity(batch, context)
        or state.get("batch") != batch or state.get("context_fingerprint") != _sha(context)
        or state.get("content_fingerprint") != _sha(batch)
        or state.get("confirmation_consumed") is not True
        or state.get("state_fingerprint") != _sha({k: v for k, v in state.items() if k != "state_fingerprint"})
        or not isinstance(state.get("items"), list) or len(state["items"]) != len(batch["items"])):
        _abort(PREFIX + "store_invalid")
    confirmation = state.get("confirmation")
    if isinstance(confirmation, dict) and confirmation.get("confirmation_version") == 3:
        _fetch_capability(path.parent)
    if not isinstance(confirmation, dict):
        _abort(PREFIX + "store_invalid")
    try:
        _validate_confirmation(confirmation, batch, context, confirmation.get("issued_at_utc"), path.parent.parent)
    except MarketFxBatchExecutionError:
        _abort(PREFIX + "store_invalid")
    for index, item in enumerate(state["items"]):
        if (not isinstance(item, dict)
            or set(item) != {"ordinal", "kind", "item_fingerprint", "status", "attempt_count",
                             "result", "result_fingerprint", "error_code"}
            or type(item.get("ordinal")) is not int or item["ordinal"] != index + 1
            or type(item.get("attempt_count")) is not int
            or item.get("error_code") not in {None, PREFIX + "provider_call_failed"}
            or item.get("kind") != batch["items"][index]["kind"]
            or item.get("item_fingerprint") != _sha(batch["items"][index])
            or item.get("status") not in {"pending", "provider_call_started", "staged", "failed"}
            or item.get("attempt_count") != (0 if item["status"] == "pending" else 1)):
            _abort(PREFIX + "store_invalid")
        if item["status"] in {"staged", "failed"}:
            if (not isinstance(item.get("result"), dict) or item["result"].get("status") != item["status"]
                or item.get("result_fingerprint") != _sha(item["result"])):
                _abort(PREFIX + "store_invalid")
        elif item.get("result") is not None or item.get("result_fingerprint") is not None:
            _abort(PREFIX + "store_invalid")
    if state.get("status") != _status(state["items"]):
        _abort(PREFIX + "store_invalid")
    return state


def _public(state: dict[str, Any]) -> dict[str, Any]:
    return {"execution_version": 2, "execution_ref": state["execution_ref"],
            "batch_fingerprint": state["batch"]["batch_fingerprint"],
            "confirmation_consumed": True, "status": state["status"],
            "items": [{k: v for k, v in item.items() if k != "result"} for item in state["items"]],
            "automatic_retry": False, "provider_fallback": False, "silent_drop_count": 0}


def _run(path: Path, state: dict[str, Any], executor: Callable, can_start: Callable | None = None) -> dict[str, Any]:
    if not callable(executor) or (can_start is not None and not callable(can_start)):
        _abort(PREFIX + "executor_invalid")
    if any(item["status"] == "provider_call_started" for item in state["items"]):
        _abort(PREFIX + "recovery_required")
    for index, item in enumerate(state["items"]):
        if item["status"] != "pending":
            continue
        if can_start is not None:
            allowed = can_start(copy.deepcopy(state), index)
            if type(allowed) is not bool:
                _abort(PREFIX + "executor_invalid")
            if not allowed:
                continue  # explicitly pending; no provider claim for a waiting review
        item.update(status="provider_call_started", attempt_count=1)
        _persist(path, state)
        try:
            result = executor(copy.deepcopy(state["batch"]["items"][index]))
            if not isinstance(result, Mapping) or result.get("status") != "staged":
                _abort(PREFIX + "result_invalid")
            result = json.loads(_canon(result))
        except Exception:
            # No raw exception details (or arbitrary error.code) in public evidence.
            # The call may have succeeded remotely: never refetch this item.
            item["error_code"] = PREFIX + "provider_call_failed"
            _persist(path, state)
            break
        item.update(status="staged", result=result, result_fingerprint=_sha(result), error_code=None)
        _persist(path, state)
    return _public(state)


def _fetch_capability(root, create=False):
    path = root / FETCH_CAPABILITY
    if not os.path.lexists(path) and create:
        _write(path, FETCH_CAPABILITY_BODY)
    if _canon(_read(path)) != _canon(FETCH_CAPABILITY_BODY):
        _abort(PREFIX + "store_invalid")


def _check_selected_startable(state, confirmation, can_start):
    selected = _selected_ordinals(confirmation["selected_ordinals"], state["batch"])
    if any(item["status"] == "provider_call_started" for item in state["items"]):
        _abort(PREFIX + "recovery_required")
    for ordinal in selected:
        if state["items"][ordinal - 1]["status"] != "pending":
            _abort(PREFIX + "selection_blocked")
        if can_start is not None:
            allowed = can_start(copy.deepcopy(state), ordinal - 1)
            if type(allowed) is not bool:
                _abort(PREFIX + "executor_invalid")
            if not allowed:
                _abort(PREFIX + "selection_blocked")
    return selected


def _run_confirmed(path, state, confirmation, executor, can_start):
    if confirmation["confirmation_version"] != 3:
        return _run(path, state, executor, can_start)
    # A durable, path/context-bound grant receipt is independent of item progress.
    # Even interruption before the first item claim cannot reuse this authority.
    receipt = path.parent / (".fetch-grant-" + confirmation["confirmation_fingerprint"] + ".json")
    expected = {"fetch_grant_version": 1, "execution_ref": state["execution_ref"],
                "confirmation": dict(confirmation)}
    if os.path.lexists(receipt):
        _fetch_capability(path.parent)
        if _canon(_read(receipt)) != _canon(expected):
            _abort(PREFIX + "store_invalid")
        return _public(state)  # never continue unattempted items on grant replay
    selected = _check_selected_startable(state, confirmation, can_start)
    _fetch_capability(path.parent, create=True)
    _write(receipt, expected)
    return _run(path, state, executor, lambda current, index:
                index + 1 in selected and (can_start is None or can_start(current, index)))


def execute_market_fx_batch_v1(data_space_path: str | Path, context_value: Any,
                              batch_value: Any, confirmation: Any, executed_at_utc: str,
                              executor: Callable[[Mapping[str, Any]], Any], *,
                              can_start: Callable | None = None,
                              preflight: Callable | None = None) -> dict[str, Any]:
    context, batch = _context(context_value), _batch(batch_value)
    space = _space(data_space_path, context)
    _validate_confirmation(confirmation, batch, context, executed_at_utc, space)
    if (not callable(executor) or (can_start is not None and not callable(can_start))
        or (preflight is not None and not callable(preflight))):
        _abort(PREFIX + "executor_invalid")
    with _locked(space, context, create=True) as root:
        path = root / (_identity(batch, context) + ".json")
        if os.path.lexists(path):
            return _public(_load(path, batch, context))
        if preflight is not None and preflight() is not None:
            # A successful read-only preflight returns None; no truthy/falsy
            # callback result may silently authorize a reservation.
            _abort(PREFIX + "executor_invalid")
        state = {"execution_version": 2, "execution_ref": _identity(batch, context),
                 "context_fingerprint": _sha(context), "content_fingerprint": _sha(batch),
                 "batch": batch, "confirmation": dict(confirmation), "confirmation_consumed": True,
                 "items": [{"ordinal": i + 1, "kind": item["kind"], "item_fingerprint": _sha(item),
                            "status": "pending", "attempt_count": 0, "result": None,
                            "result_fingerprint": None, "error_code": None}
                           for i, item in enumerate(batch["items"])]}
        if confirmation["confirmation_version"] == 3:
            _check_selected_startable(state, confirmation, can_start)
            _fetch_capability(root, create=True)
        _persist(path, state)
        return _run_confirmed(path, state, confirmation, executor, can_start)


def resume_market_fx_batch_v1(data_space_path: str | Path, context_value: Any,
                             batch_value: Any, executor: Callable, *,
                             confirmation: Any, resumed_at_utc: str,
                             can_start: Callable | None = None) -> dict[str, Any]:
    context, batch = _context(context_value), _batch(batch_value)
    space = _space(data_space_path, context)
    _validate_confirmation(confirmation, batch, context, resumed_at_utc, space)
    if not callable(executor) or (can_start is not None and not callable(can_start)):
        _abort(PREFIX + "executor_invalid")
    with _locked(space, context) as root:
        path = root / (_identity(batch, context) + ".json")
        return _run_confirmed(path, _load(path, batch, context), confirmation, executor, can_start)


def read_market_fx_batch_v1(data_space_path: str | Path, context_value: Any,
                           batch_value: Any) -> dict[str, Any]:
    context, batch = _context(context_value), _batch(batch_value)
    space = _space(data_space_path, context)
    # Atomic replacement makes reading a committed state safe without a write lock.
    return _public(_load(space / AREA / (_identity(batch, context) + ".json"), batch, context))


def load_market_fx_batch_v1(data_space_path: str | Path, context_value: Any, execution_ref: str) -> dict[str, Any]:
    """Private server recovery by opaque reference, without a session cache or write."""
    context = _context(context_value)
    space = _space(data_space_path, context)
    if not isinstance(execution_ref, str) or not re.fullmatch(r"mfb_[a-f0-9]{32}", execution_ref):
        _abort(PREFIX + "input_invalid")
    path = space / AREA / (execution_ref + ".json")
    raw = _read(path)
    batch = _batch(raw.get("batch"))
    state = _load(path, batch, context)
    if state["execution_ref"] != execution_ref:
        _abort(PREFIX + "store_invalid")
    return {"trusted_batch": batch, "progress": _public(state)}


def list_market_fx_batches_v1(data_space_path: str | Path, context_value: Any) -> list[dict[str, Any]]:
    context = _context(context_value)
    space = _space(data_space_path, context)
    root = space / AREA
    if not os.path.lexists(root):
        return []
    _area_context(root, context)
    return [load_market_fx_batch_v1(space, context, path.stem)["progress"]
            for path in sorted(root.iterdir()) if re.fullmatch(r"mfb_[a-f0-9]{32}\.json", path.name)]


def read_market_fx_batch_results_v1(data_space_path: str | Path, context_value: Any,
                                   batch_value: Any) -> list[dict[str, Any]]:
    """Private server API, not a browser read model. No refetch on restart."""
    context, batch = _context(context_value), _batch(batch_value)
    space = _space(data_space_path, context)
    state = _load(space / AREA / (_identity(batch, context) + ".json"), batch, context)
    return [{"ordinal": item["ordinal"], "result": item["result"]}
            for item in state["items"] if item["status"] == "staged"]


def recover_market_fx_batch_item_v1(data_space_path: str | Path, context_value: Any,
                                   batch_value: Any, ordinal: int,
                                   read_staged_evidence: Callable, *, confirmed: bool) -> dict[str, Any]:
    """Reconcile a started call using local adapter evidence only; never execute it.

    Trusted adapter returns a validated stage or a receipt-bound terminal failure.
    It may acknowledge native failure evidence under this explicit confirmation.
    Absence is not proof of failure, so it leaves the item blocked.
    """
    if confirmed is not True:
        _abort(PREFIX + "confirmation_invalid")
    context, batch = _context(context_value), _batch(batch_value)
    if type(ordinal) is not int or not 1 <= ordinal <= len(batch["items"]) or not callable(read_staged_evidence):
        _abort(PREFIX + "input_invalid")
    space = _space(data_space_path, context)
    with _locked(space, context) as root:
        path = root / (_identity(batch, context) + ".json")
        state = _load(path, batch, context)
        item = state["items"][ordinal - 1]
        if item["status"] in {"staged", "failed"}:
            return _public(state)
        if item["status"] != "provider_call_started":
            _abort(PREFIX + "recovery_required")
        try:
            result = read_staged_evidence(copy.deepcopy(batch["items"][ordinal - 1]))
            if not isinstance(result, Mapping) or result.get("status") not in {"staged", "failed"}:
                _abort(PREFIX + "recovery_required")
            result = json.loads(_canon(result))
        except Exception:
            _abort(PREFIX + "recovery_required")
        item.update(status=result["status"], result=result, result_fingerprint=_sha(result),
                    error_code=PREFIX + "provider_call_failed" if result["status"] == "failed" else None)
        _persist(path, state)
        return _public(state)
