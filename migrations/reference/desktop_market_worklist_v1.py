"""Private, context/path-bound mapping worklist. No catalog or provider authority."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import uuid

from migrations.reference import desktop_market_fx_batch_execution_v1 as files

AREA = 'market-mapping-worklist-v1'
STATUSES = {'pending', 'deferred', 'skipped', 'mapping_saved', 'reviewed'}
DRAFT = {'provider_id', 'provider_symbol', 'provider_currency', 'exchange_code', 'mic_code'}


def invalid():
    raise ValueError('desktop_market_worklist_invalid')


def identity(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,128}', value):
        invalid()
    return value


def _loaded_provider(provider_id):
    from migrations.reference import price_provider_plugins_v1 as price_providers
    return price_providers.provider_spec_v1(provider_id) if isinstance(provider_id, str) else None


def draft(value, domain='provider'):
    # Nur noch die Provider-Zuordnung; die Stammdaten-Liste aus dem Legacy-Import ist seit rc.309 entfernt.
    if domain != 'provider' or not isinstance(value, dict) or set(value) != DRAFT:
        invalid()
    if any(not isinstance(v, str) or len(v) > 120 or v != v.strip() or any(ord(c) < 32 for c in v) for v in value.values()):
        invalid()
    # Jeder geladene Kursanbieter (rc.394, etwa EODHD) sowie die beiden Entwurfsarten von frueher.
    if value['provider_id'] not in {'twelve_data', 'other_reviewed'} and _loaded_provider(value['provider_id']) is None:
        invalid()
    if not re.fullmatch(r'[A-Z]{3}', value['provider_currency']):
        invalid()
    if value['mic_code'] and not re.fullmatch(r'[A-Z0-9]{4}', value['mic_code']):
        invalid()
    return value


def binding(space, context):
    from migrations.reference.data_space_relocation_v1 import origin_v1  # Ursprungsort nach einem Restore an einen anderen Ort (#493), sonst der Datenraum selbst.
    return files._sha({'context': context, 'absolute_data_space': str(origin_v1(space))})


def load(root, bound, domain='provider'):
    if not os.path.lexists(root):
        return None
    files._check_owner(root, True)
    if files._read(root / '.context') != {'binding': bound}:
        invalid()
    path = root / 'worklist.json'
    if not os.path.lexists(path):
        return None
    value = files._read(path)
    if (set(value) != {'version', 'queue_ref', 'binding', 'items', 'cursor', 'revision'} or value['version'] != 1
        or value['binding'] != bound or value['revision'] != files._sha({k:v for k,v in value.items() if k != 'revision'})
        or not isinstance(value['items'], list) or not 1 <= len(value['items']) <= 10000
        or type(value['cursor']) is not int or not 0 <= value['cursor'] < len(value['items'])):
        invalid()
    identity(value['queue_ref'])
    seen = set()
    for row in value['items']:
        if not isinstance(row, dict) or set(row) != {'asset_id', 'status', 'draft'}:
            invalid()
        key = identity(row['asset_id'])
        if key in seen or row['status'] not in STATUSES:
            invalid()
        seen.add(key)
        if row['draft'] is not None:
            draft(row['draft'], domain)
    return value


@contextmanager
def locked(root, bound):
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    files._check_owner(root, True)
    files._sync_directory(root.parent)
    lock = root / '.lock'
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        files._check_owner(lock, False)
        st = os.fstat(fd)
        if st.st_nlink != 1 or (st.st_dev, st.st_ino) != (lock.stat().st_dev, lock.stat().st_ino):
            invalid()
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        context_file = root / '.context'
        if not os.path.lexists(context_file):
            if any(p.name != '.lock' for p in root.iterdir()):
                invalid()
            files._write(context_file, {'binding': bound})
        if files._read(context_file) != {'binding': bound}:
            invalid()
        yield
    finally:
        os.close(fd)


def operate(data_space_path, context_value, command, payload, *, domain='provider'):
    context = files._context(context_value)
    space = files._space(data_space_path, context)
    if domain != 'provider':
        invalid()
    root = space / AREA
    bound = files._sha({'scope': binding(space, context), 'domain': domain})
    if command == 'read':
        if payload != {'read_only': True} or type(payload['read_only']) is not bool:
            invalid()
        return load(root, bound, domain)
    fields = {'start': {'asset_ids', 'expected_revision'},
              'update': {'asset_id', 'status', 'draft', 'advance', 'expected_revision'},
              'select': {'asset_id', 'expected_revision'}}
    if command not in fields or not isinstance(payload, dict) or set(payload) != fields[command]:
        invalid()
    with locked(root, bound):
        value = load(root, bound, domain)
        revision = None if value is None else value['revision']
        if payload['expected_revision'] != revision:
            invalid()  # second session or interrupted acknowledgement: reload, never overwrite
        if command == 'start':
            ids = payload['asset_ids']
            if not isinstance(ids, list) or not 1 <= len(ids) <= 10000 or len(set(map(identity, ids))) != len(ids):
                invalid()
            # Never replace an existing queue, including deferred/skipped members.
            # Explicitly extend its inventory; every previous disposition is retained.
            if value is None:
                value = {'version': 1, 'queue_ref': 'mwq_' + uuid.uuid4().hex, 'binding': bound, 'items': [], 'cursor': 0}
            known = {row['asset_id'] for row in value['items']}
            if len(known | set(ids)) > 10000:
                invalid()
            value['items'].extend({'asset_id': key, 'status': 'pending', 'draft': None} for key in ids if key not in known)
        else:
            if value is None:
                invalid()
            matches = [i for i, row in enumerate(value['items']) if row['asset_id'] == identity(payload['asset_id'])]
            if len(matches) != 1:
                invalid()
            index = matches[0]
            if command == 'select':
                value['cursor'] = index
            else:
                if value['cursor'] != index or payload['status'] not in STATUSES or type(payload['advance']) is not bool:
                    invalid()
                saved_draft = None if payload['draft'] is None and payload['status'] in {'reviewed', 'mapping_saved'} else draft(payload['draft'], domain)
                value['items'][index].update(status=payload['status'], draft=saved_draft)
                if payload['advance']:
                    order = list(range(index + 1, len(value['items']))) + list(range(index))
                    next_items = [i for i in order if value['items'][i]['status'] == 'pending']
                    if next_items:
                        value['cursor'] = next_items[0]
        value['revision'] = files._sha({k:v for k,v in value.items() if k != 'revision'})
        files._write(root / 'worklist.json', value)
        return value
