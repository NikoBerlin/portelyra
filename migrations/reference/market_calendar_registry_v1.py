#!/usr/bin/env python3
"""Owner-local append-only calendar registry; catalog reads never create files."""
from __future__ import annotations
import hashlib
import json
import os
import re
import sqlite3
import stat
from pathlib import Path
from datetime import date, timedelta
from typing import Mapping
from migrations.reference.market_calendar_v1 import validate_market_calendar_profile_v1

AREA = "market-calendar-v1"
STORE = "market-calendar.sqlite"
SCOPE = re.compile(r"^(?:lsr|fxp)_[a-f0-9]{32}$")
CODES = frozenset({"market_calendar_registry_context_invalid", "market_calendar_registry_store_invalid",
    "market_calendar_registry_candidate_invalid", "market_calendar_registry_confirmation_required",
    "market_calendar_registry_revision_conflict"})


class MarketCalendarRegistryV1Error(RuntimeError):
    def __init__(self, code):
        if code not in CODES:
            raise ValueError("market_calendar_registry_error_unregistered")
        self.code = code
        super().__init__(code)


def _abort(code):
    raise MarketCalendarRegistryV1Error(code)


def _canon(value):
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(_canon(value).encode()).hexdigest()


def _ctx(value, writer=False):
    if (not isinstance(value, Mapping) or not all(isinstance(value.get(k), str) and value[k]
        for k in ("tenant_id", "user_id", "data_space_id", "actor_id", "role"))
        or not value["data_space_id"].startswith("sbx_")):
        _abort("market_calendar_registry_context_invalid")
    if writer and (value["actor_id"] != "market_worker" or value["role"] != "market_worker"):
        _abort("market_calendar_registry_context_invalid")
    return dict(value)


def _private(path, directory=False):
    try:
        info = path.lstat()
        if (info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != (0o700 if directory else 0o600)
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or (not directory and info.st_nlink != 1)):
            _abort("market_calendar_registry_store_invalid")
    except OSError as error:
        raise MarketCalendarRegistryV1Error("market_calendar_registry_store_invalid") from error


def _space(path, ctx):
    p = Path(path)
    _private(p, True)
    if not p.is_absolute() or p.resolve() != p or p.name != ctx["data_space_id"]:
        _abort("market_calendar_registry_store_invalid")
    return p


def _store(space, create):
    area = space / AREA
    if create and not os.path.lexists(area):
        area.mkdir(mode=0o700)
    _private(area, True)
    store = area / STORE
    # Registry writers use DELETE journaling. Do not recover journals or ignore WAL.
    if any(os.path.lexists(Path(str(store) + suffix)) for suffix in ("-wal", "-shm", "-journal")):
        _abort("market_calendar_registry_store_invalid")
    if create and not os.path.lexists(store):
        fd = os.open(store, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.close(fd)
    _private(store)
    with store.open('rb') as handle:
        header = handle.read(20)
    # A closed WAL-mode database can have no sidecars yet. Reject its header as
    # well, so a read-only SQLite connection cannot create WAL/SHM files.
    if (header or not create) and (not header.startswith(b'SQLite format 3\x00') or header[18:20] != b'\x01\x01'):
        _abort("market_calendar_registry_store_invalid")
    return store


def _owner(space, ctx):
    from migrations.reference.data_space_relocation_v1 import origin_v1  # Ursprungsort nach einem Restore an einen anderen Ort (#493), sonst der Datenraum selbst.
    return _sha({"path": str(origin_v1(Path(space))), "context": {k: ctx[k] for k in ("tenant_id", "user_id", "data_space_id")}})


def initialize_market_calendar_registry_v1(data_space_path, context):
    ctx = _ctx(context, True)
    store = _store(_space(data_space_path, ctx), True)
    with sqlite3.connect(store) as con:
        con.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS calendar_profile(profile_ref TEXT NOT NULL,profile_version INTEGER NOT NULL,profile_fingerprint TEXT NOT NULL UNIQUE,profile_json TEXT NOT NULL,actor_id TEXT NOT NULL,completed_at_utc TEXT NOT NULL,PRIMARY KEY(profile_ref,profile_version));
        CREATE TABLE IF NOT EXISTS calendar_binding(scope_kind TEXT NOT NULL,scope_ref TEXT NOT NULL,binding_revision INTEGER NOT NULL,profile_ref TEXT NOT NULL,profile_version INTEGER NOT NULL,binding_fingerprint TEXT NOT NULL UNIQUE,actor_id TEXT NOT NULL,completed_at_utc TEXT NOT NULL,PRIMARY KEY(scope_kind,scope_ref,binding_revision),FOREIGN KEY(profile_ref,profile_version) REFERENCES calendar_profile(profile_ref,profile_version));
        CREATE TABLE IF NOT EXISTS calendar_binding_owner(binding_fingerprint TEXT PRIMARY KEY,owner_fingerprint TEXT NOT NULL);
        """)
    con.close()
    return store


def preview_market_calendar_binding_v1(context, profile, scope_kind, scope_ref, created_at_utc):
    ctx = _ctx(context, True)
    p = validate_market_calendar_profile_v1(profile)
    if (scope_kind not in {"listing", "fx_pair"} or not isinstance(scope_ref, str)
        or SCOPE.fullmatch(scope_ref) is None or (scope_kind == "listing") != scope_ref.startswith("lsr_")
        or not isinstance(created_at_utc, str)):
        _abort("market_calendar_registry_candidate_invalid")
    body = dict(contract_version="market_calendar_binding_candidate_v1", status="pending_confirmation",
        profile=p, scope_kind=scope_kind, scope_ref=scope_ref, created_at_utc=created_at_utc,
        context_fingerprint=_sha(ctx), provider_access=False, network_access=False, history_write=False, canonical_write=False)
    body["candidate_fingerprint"] = _sha(body)
    return body


def _extension_candidate(ctx, addition, scope_kind, scope_ref, created, owner, previous, source_fingerprint):
    """Additive-only operation. No unverified profile adoption or implicit removal."""
    addition = validate_market_calendar_profile_v1(addition)
    if previous is not None:
        if (set(previous) != {'scope_kind', 'scope_ref', 'binding_revision', 'context_verified', 'profile'}
            or previous['context_verified'] is not True or previous['scope_kind'] != scope_kind
            or previous['scope_ref'] != scope_ref or type(previous['binding_revision']) is not int
            or previous['binding_revision'] < 1):
            _abort('market_calendar_registry_candidate_invalid')
        old = validate_market_calendar_profile_v1(previous['profile'])
        if (any(old[k] != addition[k] for k in ('calendar_kind', 'market_code', 'timezone_name', 'session_weekdays'))
            or date.fromisoformat(addition['valid_from']) > date.fromisoformat(old['valid_to']) + timedelta(days=1)
            or date.fromisoformat(old['valid_from']) > date.fromisoformat(addition['valid_to']) + timedelta(days=1)):
            _abort('market_calendar_registry_revision_conflict')
        closures = {r['date']: r for r in addition['closure_dates']}
        closures.update({r['date']: r for r in old['closure_dates']})  # retain exact original reasons
        openings = sorted(set(old['special_open_dates']) | set(addition['special_open_dates']))
        if set(closures) & set(openings):
            _abort('market_calendar_registry_revision_conflict')
        from migrations.reference.market_calendar_v1 import build_market_calendar_profile_v1
        profile = build_market_calendar_profile_v1(profile_version=1,
            calendar_kind=old['calendar_kind'], market_code=old['market_code'], timezone_name=old['timezone_name'],
            valid_from=min(old['valid_from'], addition['valid_from']), valid_to=max(old['valid_to'], addition['valid_to']),
            session_weekdays=old['session_weekdays'], closure_dates=[closures[d] for d in sorted(closures)],
            special_open_dates=openings, source_kind='reviewed_manifest', source_ref=_canon(dict(
                extension_version=1, previous_profile_fingerprint=old['profile_fingerprint'],
                added_source_kind=addition['source_kind'], added_source_ref=addition['source_ref'])))
    else:
        profile = addition
    if (not isinstance(owner, str) or re.fullmatch('[a-f0-9]{64}', owner) is None
        or (source_fingerprint is not None and (not isinstance(source_fingerprint, str)
            or re.fullmatch('[a-f0-9]{64}', source_fingerprint) is None))):
        _abort('market_calendar_registry_candidate_invalid')
    body = preview_market_calendar_binding_v1(ctx, profile, scope_kind, scope_ref, created)
    body.pop('candidate_fingerprint')
    body['contract_version'] = 'market_calendar_binding_extension_v1'
    body['extension'] = dict(owner_fingerprint=owner, previous_binding=previous,
        addition_profile=addition, source_fingerprint=source_fingerprint)
    return {**body, 'candidate_fingerprint': _sha(body)}


def preview_market_calendar_extension_v1(space, context, addition, scope_kind, scope_ref, created, *, source_fingerprint=None):
    ctx = _ctx(context, True); space = _space(space, ctx)
    previous = None
    if os.path.lexists(space / AREA):
        rows = read_market_calendar_catalog_v1(space, ctx, scopes=[(scope_kind, scope_ref)])['bindings']
        previous = rows[0] if rows else None
    return _extension_candidate(ctx, addition, scope_kind, scope_ref, created, _owner(space, ctx), previous, source_fingerprint)


def public_market_calendar_binding_preview_v1(value):
    if (not isinstance(value, dict) or value.get("candidate_fingerprint") !=
        _sha({k: x for k, x in value.items() if k != "candidate_fingerprint"})):
        _abort("market_calendar_registry_candidate_invalid")
    p = validate_market_calendar_profile_v1(value["profile"])
    result = dict(contract_version="market_calendar_binding_public_preview_v1", status="pending_confirmation",
        calendar_kind=p["calendar_kind"], market_code=p["market_code"], timezone_name=p["timezone_name"],
        valid_from=p["valid_from"], valid_to=p["valid_to"], closure_count=len(p["closure_dates"]),
        special_open_count=len(p["special_open_dates"]), scope_kind=value["scope_kind"], confirmation_required=True,
        provider_access=False, history_write=False, canonical_write=False)
    if value.get('contract_version') == 'market_calendar_binding_extension_v1':
        old = value['extension']['previous_binding']
        retained = {r['date'] for r in old['profile']['closure_dates']} if old else set()
        result.update(operation='extend' if old else 'initial',
            previous_binding_revision=old['binding_revision'] if old else None,
            previous_valid_from=old['profile']['valid_from'] if old else None,
            previous_valid_to=old['profile']['valid_to'] if old else None,
            requested_valid_from=value['extension']['addition_profile']['valid_from'],
            requested_valid_to=value['extension']['addition_profile']['valid_to'],
            retained_closure_count=len(retained), added_closure_count=len(p['closure_dates'])-len(retained),
            retained_special_open_count=len(old['profile']['special_open_dates']) if old else 0,
            closure_rows=[dict(r, origin='retained' if r['date'] in retained else 'added') for r in p['closure_dates']],
            special_open_dates=p['special_open_dates'], removed_day_count=0, silent_drop_count=0)
    return result


def apply_market_calendar_binding_v1(data_space_path, context, candidate, public_preview, confirmed, completed_at_utc):
    ctx = _ctx(context, True)
    if confirmed is not True:
        _abort("market_calendar_registry_confirmation_required")
    if public_preview != public_market_calendar_binding_preview_v1(candidate) or candidate["context_fingerprint"] != _sha(ctx):
        _abort("market_calendar_registry_candidate_invalid")
    extension = candidate.get('extension') if candidate.get('contract_version') == 'market_calendar_binding_extension_v1' else None
    space = _space(data_space_path, ctx)
    if extension is not None:
        rebuilt = _extension_candidate(ctx, extension['addition_profile'], candidate['scope_kind'], candidate['scope_ref'],
            candidate['created_at_utc'], _owner(space, ctx), extension['previous_binding'], extension['source_fingerprint'])
    else:
        rebuilt = preview_market_calendar_binding_v1(ctx, candidate['profile'], candidate['scope_kind'], candidate['scope_ref'], candidate['created_at_utc'])
    if candidate != rebuilt:
        _abort("market_calendar_registry_candidate_invalid")
    store = initialize_market_calendar_registry_v1(space, ctx)
    p = candidate["profile"]
    owner = _owner(space, ctx)
    con = sqlite3.connect(store)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("BEGIN IMMEDIATE")
        if con.execute("SELECT 1 FROM calendar_binding_owner WHERE owner_fingerprint!=? LIMIT 1", (owner,)).fetchone():
            _abort("market_calendar_registry_context_invalid")
        if extension is not None:
            latest_expected = con.execute('SELECT * FROM calendar_binding WHERE scope_kind=? AND scope_ref=? ORDER BY binding_revision DESC LIMIT 1',
                (candidate['scope_kind'], candidate['scope_ref'])).fetchone()
            previous = extension['previous_binding']
            if previous is None:
                if latest_expected is not None:
                    _abort('market_calendar_registry_revision_conflict')
            else:
                expected = _sha(dict(scope_kind=candidate['scope_kind'], scope_ref=candidate['scope_ref'],
                    binding_revision=previous['binding_revision'], profile_fingerprint=previous['profile']['profile_fingerprint']))
                if (latest_expected is None or latest_expected['binding_fingerprint'] != expected
                    or latest_expected['binding_revision'] != previous['binding_revision']
                    or latest_expected['profile_ref'] != previous['profile']['calendar_ref']
                    or latest_expected['profile_version'] != previous['profile']['profile_version']
                    or not con.execute('SELECT 1 FROM calendar_binding_owner WHERE binding_fingerprint=? AND owner_fingerprint=?', (expected, owner)).fetchone()):
                    _abort('market_calendar_registry_revision_conflict')
        existing = con.execute("SELECT profile_fingerprint FROM calendar_profile WHERE profile_ref=? AND profile_version=?", (p["calendar_ref"], p["profile_version"])).fetchone()
        if existing and existing[0] != p["profile_fingerprint"]:
            _abort("market_calendar_registry_revision_conflict")
        if not existing:
            con.execute("INSERT INTO calendar_profile VALUES(?,?,?,?,?,?)", (p["calendar_ref"], p["profile_version"], p["profile_fingerprint"], _canon(p), ctx["actor_id"], completed_at_utc))
        latest = con.execute("SELECT * FROM calendar_binding WHERE scope_kind=? AND scope_ref=? ORDER BY binding_revision DESC LIMIT 1", (candidate["scope_kind"], candidate["scope_ref"])).fetchone()
        revision = 1 if latest is None else int(latest["binding_revision"]) + 1
        unchanged = latest is not None and latest["profile_ref"] == p["calendar_ref"] and int(latest["profile_version"]) == p["profile_version"]
        if unchanged:
            revision = int(latest["binding_revision"])
        fingerprint = _sha(dict(scope_kind=candidate["scope_kind"], scope_ref=candidate["scope_ref"], binding_revision=revision, profile_fingerprint=p["profile_fingerprint"]))
        if unchanged and latest["binding_fingerprint"] != fingerprint:
            _abort("market_calendar_registry_store_invalid")
        if not unchanged:
            con.execute("INSERT INTO calendar_binding VALUES(?,?,?,?,?,?,?,?)", (candidate["scope_kind"], candidate["scope_ref"], revision, p["calendar_ref"], p["profile_version"], fingerprint, ctx["actor_id"], completed_at_utc))
        # Only this explicitly confirmed binding gains owner/path evidence. Legacy
        # siblings are NOT adopted by initializing the supplemental proof table.
        proven = con.execute("SELECT 1 FROM calendar_binding_owner WHERE binding_fingerprint=?", (fingerprint,)).fetchone()
        if not proven:
            con.execute("INSERT INTO calendar_binding_owner VALUES(?,?)", (fingerprint, owner))
        con.commit()
        return dict(status="unchanged" if unchanged and proven else "published", binding_revision=revision,
            profile_version=p["profile_version"], provider_access=False, history_write=False, canonical_write=False)
    except MarketCalendarRegistryV1Error:
        con.rollback()
        raise
    except (sqlite3.Error, KeyError, TypeError) as error:
        con.rollback()
        raise MarketCalendarRegistryV1Error("market_calendar_registry_store_invalid") from error
    finally:
        con.close()


def _json(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def read_market_calendar_catalog_v1(data_space_path, context, *, require_context=True, scopes=None):
    # Scope selection never skips integrity/foreign-owner checks. It only limits
    # which otherwise valid bindings must carry positive contextual proof.
    if type(require_context) is not bool or (scopes is not None and (
        not isinstance(scopes, (list, tuple)) or any(not isinstance(x, (list, tuple)) or len(x) != 2
        or x[0] not in {'listing', 'fx_pair'} or not isinstance(x[1], str) or not SCOPE.fullmatch(x[1])
        or (x[0] == 'listing') != x[1].startswith('lsr_') for x in scopes))):
        _abort('market_calendar_registry_context_invalid')
    ctx = _ctx(context)
    space = _space(data_space_path, ctx)
    store = _store(space, False)
    # Keep SQLite's locking: immutable=1 could expose uncommitted main-file
    # pages during a writer rollback. Only rollback-journal stores are accepted.
    con = sqlite3.connect(store.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        owners = {}
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='calendar_binding_owner'").fetchone():
            owners = dict(con.execute("SELECT binding_fingerprint,owner_fingerprint FROM calendar_binding_owner"))
        if any(value != _owner(space, ctx) for value in owners.values()):
            _abort("market_calendar_registry_context_invalid")
        rows = con.execute("""SELECT b.*,p.profile_json,p.profile_fingerprint,p.actor_id AS profile_actor
            FROM calendar_binding b LEFT JOIN calendar_profile p ON p.profile_ref=b.profile_ref AND p.profile_version=b.profile_version
            WHERE b.binding_revision=(SELECT max(x.binding_revision) FROM calendar_binding x WHERE x.scope_kind=b.scope_kind AND x.scope_ref=b.scope_ref)
            ORDER BY b.scope_kind,b.scope_ref""").fetchall()
        bindings = []
        for row in rows:
            p = validate_market_calendar_profile_v1(_json(row["profile_json"]))
            fp = _sha(dict(scope_kind=row["scope_kind"], scope_ref=row["scope_ref"], binding_revision=row["binding_revision"], profile_fingerprint=p["profile_fingerprint"]))
            if (row["scope_kind"] not in {"listing", "fx_pair"} or not SCOPE.fullmatch(row["scope_ref"])
                or (row["scope_kind"] == "listing") != row["scope_ref"].startswith("lsr_")
                or type(row["binding_revision"]) is not int or row["binding_revision"] < 1
                or row["profile_ref"] != p["calendar_ref"] or row["profile_version"] != p["profile_version"]
                or row["profile_fingerprint"] != p["profile_fingerprint"] or row["binding_fingerprint"] != fp
                or row["actor_id"] != "market_worker" or row["profile_actor"] != "market_worker"):
                _abort("market_calendar_registry_store_invalid")
            verified = fp in owners
            selected = scopes is None or (row['scope_kind'], row['scope_ref']) in [tuple(x) for x in scopes]
            if not selected:
                continue
            if require_context and not verified:
                _abort("market_calendar_registry_context_invalid")
            bindings.append(dict(scope_kind=row["scope_kind"], scope_ref=row["scope_ref"],
                binding_revision=row["binding_revision"], context_verified=verified, profile=p))
        _store(space, False)
        return dict(status="ready", bindings=bindings, provider_access=False, history_write=False, canonical_write=False)
    except MarketCalendarRegistryV1Error:
        raise
    except (sqlite3.Error, ValueError, TypeError, KeyError, RuntimeError) as error:
        raise MarketCalendarRegistryV1Error("market_calendar_registry_store_invalid") from error
    finally:
        con.close()


__all__ = ["MarketCalendarRegistryV1Error", "initialize_market_calendar_registry_v1", "preview_market_calendar_binding_v1",
    "public_market_calendar_binding_preview_v1", "apply_market_calendar_binding_v1", "read_market_calendar_catalog_v1",
    "preview_market_calendar_extension_v1"]
