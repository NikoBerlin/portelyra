"""Owner-local FX attempt evidence. No provider calls or canonical writes here."""
from contextlib import contextmanager
import fcntl
import json
import os
import re
import stat
import sqlite3
from pathlib import Path


def api():
    from migrations.reference import desktop_fx_history_review_v1
    return desktop_fx_history_review_v1


def checked(path, directory=False):
    f = api()
    try:
        s = path.lstat()
        if path.resolve(strict=True) != path or s.st_uid != os.geteuid() or stat.S_IMODE(s.st_mode) != (0o700 if directory else 0o600):
            raise ValueError()
        if directory:
            if not stat.S_ISDIR(s.st_mode): raise ValueError()
        elif not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
            raise ValueError()
    except (OSError, ValueError):
        f._abort('desktop_fx_history_review_store_invalid')


def read(path):
    checked(path)
    if path.stat().st_size > 8_000_000: api()._abort('desktop_fx_history_review_store_invalid')
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'r') as stream:
            value = json.load(stream)
        if not isinstance(value, dict): raise ValueError()
        return value
    except (OSError, ValueError): api()._abort('desktop_fx_history_review_store_invalid')


def seal(value):
    return dict(value, evidence_fingerprint=api()._sha(value))


def sealed_read(path):
    value = read(path)
    if value.get('evidence_fingerprint') != api()._sha({k:v for k,v in value.items() if k != 'evidence_fingerprint'}):
        api()._abort('desktop_fx_history_review_store_invalid')
    return value


def write(path, value):
    """Create-only, fully written and fsynced; partial files are never reusable."""
    f = api()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(f._canon(value) + b'\n'); stream.flush(); os.fsync(stream.fileno())
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
    except FileExistsError: f._abort('desktop_fx_history_review_attempt_consumed')
    except OSError: f._abort('desktop_fx_history_review_store_invalid')


def mkdir(parent, name):
    path = parent/name
    try: path.mkdir(mode=0o700)
    except FileExistsError: pass
    checked(path, True)
    return path


@contextmanager
def locked(space):
    root = mkdir(space, api().STAGE_AREA)
    path = root/'.attempt-v2.lock'
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        checked(path)
        try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError: api()._abort('desktop_fx_history_review_attempt_consumed')
        yield root
    finally: os.close(fd)


def owner(space, ctx):
    from migrations.reference.data_space_relocation_v1 import origin_v1  # Ursprungsort nach einem Restore an einen anderen Ort (#493), sonst der Datenraum selbst.
    return api()._sha([str(origin_v1(space)), ctx.tenant_id, ctx.user_id, ctx.data_space_id])


def result_read(path, space, ctx):
    f = api(); value = read(path)
    if value.get('staging_fingerprint') != f._sha({k:v for k,v in value.items() if k != 'staging_fingerprint'}):
        f._abort('desktop_fx_history_review_store_invalid')
    candidate = value['candidate']
    from migrations.reference.fx_history_v1 import FxHistoryContext, fx_history_context_fingerprint_v1, fx_history_job_binding_fingerprint_v1
    fx_history_context_fingerprint_v1(ctx)  # Validate the actual reader before checking writer provenance.
    # Recompute the historical writer's sealed job identity, not the reader's role.
    # This pure fingerprint function neither grants authority nor invokes a writer.
    original_writer = FxHistoryContext(ctx.tenant_id,ctx.user_id,ctx.data_space_id,'market_worker','market_worker')
    expected = fx_history_job_binding_fingerprint_v1(original_writer, pair_ref=candidate['pair_ref'], request_ref=candidate['request_ref'], request_fingerprint=candidate['request_fingerprint'], source_ref=candidate['source_ref'])
    if candidate['job_binding_fingerprint'] != expected or (value.get('owner_fingerprint') is not None and value['owner_fingerprint'] != owner(space, ctx)):
        f._abort('desktop_fx_history_review_store_invalid')
    return value


def catalog(space, ctx):
    """Read only. Legacy attempts lacking scope stay explicitly unknown."""
    f = api(); root = space/f.STAGE_AREA; rows = []
    if not os.path.lexists(root): return rows
    checked(root, True)
    attempts = root/'attempts'
    if not os.path.lexists(attempts): return rows
    checked(attempts, True)
    paths = sorted(attempts.iterdir())
    if len(paths) > 10000: f._abort('desktop_fx_history_review_store_invalid')
    for path in paths:
        if not re.fullmatch(r'fxh_[a-f0-9]{32}\.json', path.name): f._abort('desktop_fx_history_review_store_invalid')
        attempt = read(path); fp = attempt.get('preview_fingerprint')
        if not isinstance(fp, str) or not re.fullmatch('[a-f0-9]{64}', fp) or path.stem != 'fxh_'+fp[:32]: f._abort('desktop_fx_history_review_store_invalid')
        modern = attempt.get('contract_version') == 'desktop_fx_history_attempt_v2'
        if modern:
            sealed_read(path)
            if attempt.get('owner_fingerprint') != owner(space, ctx): f._abort('desktop_fx_history_review_store_invalid')
        elif attempt.get('contract_version') != 'desktop_fx_history_attempt_v1': f._abort('desktop_fx_history_review_store_invalid')
        result = root/'results'/path.name; failure = root/'failures'/path.name; response = root/'responses'/path.name; ack = root/'reviewed-no-result'/path.name
        state = 'unknown'; category = 'legacy_scope_unknown' if not modern else 'interrupted_or_unknown'; status = None
        if os.path.lexists(result):
            staged = result_read(result, space, ctx)
            if staged['preview_fingerprint'] != fp: f._abort('desktop_fx_history_review_store_invalid')
            state = 'staged'; category = 'saved_result'
            from migrations.reference.fx_history_v1 import read_fx_history_request_receipt_v1
            receipt=read_fx_history_request_receipt_v1(space/f.AREA/f.STORE,ctx,staged['candidate']['request_ref'])
            if receipt is not None:
                if receipt.candidate_fingerprint!=staged['candidate']['candidate_fingerprint']:f._abort('desktop_fx_history_review_store_invalid')
                state='published';category='saved_publication'
            # A sealed staged result, unlike a bare legacy attempt, carries scope.
            scope=staged
        else:scope=attempt
        if os.path.lexists(failure):
            v = sealed_read(failure)
            if v.get('preview_fingerprint') != fp or not modern: f._abort('desktop_fx_history_review_store_invalid')
            if state in ('staged','published'): f._abort('desktop_fx_history_review_store_invalid')
            state = 'failed'; category = v['category']; status = v.get('http_status')
        response_saved = os.path.lexists(response)
        if response_saved:
            v = sealed_read(response)
            if not modern or v.get('preview_fingerprint') != fp: f._abort('desktop_fx_history_review_store_invalid')
        reviewed = False
        if os.path.lexists(ack):
            v = sealed_read(ack)
            required = {'contract_version','owner_fingerprint','attempt_fingerprint','inspection_fingerprint','outcome','transport_outcome','provider_access','evidence_fingerprint'}
            if (set(v) != required or v.get('contract_version') != 'desktop_fx_history_no_result_review_v2'
                or v.get('owner_fingerprint') != owner(space, ctx) or v.get('attempt_fingerprint') != f._sha(attempt)
                or v.get('outcome') != 'owner_reviewed_no_saved_result' or v.get('transport_outcome') != 'not_asserted'
                or v.get('provider_access') is not False or not isinstance(v.get('inspection_fingerprint'),str)
                or not re.fullmatch('[a-f0-9]{64}',v['inspection_fingerprint'])):
                f._abort('desktop_fx_history_review_store_invalid')
            reviewed = True
        rows.append(dict(attempt_ref=path.stem, state=state, category=category, http_status=status, response_saved=response_saved,
                         source_currency=scope.get('source_currency'), target_currency=scope.get('target_currency'),
                         start_date=scope.get('start_date'), end_date=scope.get('end_date'), reviewed_no_result=reviewed,
                         attempt_fingerprint=f._sha(attempt), preview_fingerprint=fp))
    return rows


@contextmanager
def store_guard(space):
    store=space/api().AREA/api().STORE;checked(store)
    if any(os.path.lexists(Path(str(store)+suffix)) for suffix in ('-wal','-shm','-journal')):api()._abort('desktop_fx_history_review_store_invalid')
    with store.open('rb') as stream:header=stream.read(20)
    if header[:16]!=b'SQLite format 3\x00' or header[18:20]!=b'\x01\x01':api()._abort('desktop_fx_history_review_store_invalid')
    con=sqlite3.connect(store.as_uri()+'?mode=ro',uri=True,timeout=0)
    try:
        con.execute('PRAGMA query_only=ON');con.execute('BEGIN');con.execute('SELECT count(*) FROM sqlite_master').fetchone()
        yield
    finally:con.close()


def inspect(data_space_path, context):
    f = api(); ctx = f._ctx(context); space = f._space(data_space_path, ctx)
    store = space/f.AREA/f.STORE; checked(store)
    with store_guard(space):
        f.read_fx_pair_catalog_v1(store,ctx) # native context/schema boundary, no writes
        before = f._sha(store.read_bytes()); rows = catalog(space, ctx)
        if before != f._sha(store.read_bytes()): f._abort('desktop_fx_history_review_store_invalid')
    return seal(dict(contract_version='desktop_fx_history_inspection_v2', owner_fingerprint=owner(space, ctx), store_fingerprint=before,
                     rows=rows, provider_access=False, fx_history_write=False, automatic_retry=False))


def review_no_result(data_space_path, context, inspection, attempt_ref, confirmed):
    """Explicit append-only operator decision, NOT proof of transport failure.

    No attempt/grant is reset. A future request needs a fresh preview and grant.
    """
    f = api(); ctx = f._ctx(context); space = f._space(data_space_path, ctx)
    if confirmed is not True: f._abort('desktop_fx_history_review_confirmation_required')
    with locked(space) as root, store_guard(space):
        current = inspect(space, context)
        if inspection != current: f._abort('desktop_fx_history_review_preview_invalid')
        matches = [r for r in current['rows'] if r['attempt_ref'] == attempt_ref]
        if len(matches) != 1 or matches[0]['state'] in ('staged','published') or matches[0]['reviewed_no_result']: f._abort('desktop_fx_history_review_preview_invalid')
        row = matches[0]
        write(mkdir(root, 'reviewed-no-result')/(attempt_ref+'.json'), seal(dict(contract_version='desktop_fx_history_no_result_review_v2',
              owner_fingerprint=owner(space, ctx), attempt_fingerprint=row['attempt_fingerprint'], inspection_fingerprint=current['evidence_fingerprint'],
              outcome='owner_reviewed_no_saved_result', transport_outcome='not_asserted', provider_access=False)))
    return dict(status='reviewed_no_saved_result', provider_access=False, fx_history_write=False, automatic_retry=False)


def assert_no_unreviewed_overlap(space, ctx, preview):
    for row in catalog(space, ctx):
        if row['state']=='published' or (row['reviewed_no_result'] and row['state']!='staged'): continue
        unknown_scope = row['source_currency'] is None
        overlap = row['source_currency'] == preview['source_currency'] and row['target_currency'] == preview['target_currency'] and row['start_date'] <= preview['end_date'] and row['end_date'] >= preview['start_date']
        if unknown_scope or overlap: api()._abort('desktop_fx_history_review_attempt_consumed')
