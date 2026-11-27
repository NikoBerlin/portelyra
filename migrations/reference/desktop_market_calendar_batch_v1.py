"""Read-only handoff of a sealed saved-calendar valuation into native batches.

No provider or writer authority. Original scopes remain reserved; never replan a
started batch. Snapshot freshness is checked before confirmation/first claim;
calendar/code freshness is checked again for each pending item and transport gate.
"""
from pathlib import Path
from datetime import date
import hashlib
import os
from migrations.reference import desktop_market_fx_batch_execution_v1 as execution
from migrations.reference import desktop_market_valuation_v1 as valuation

CODES = frozenset('desktop_market_fx_batch_calendar_' + suffix for suffix in
    ('input_invalid', 'stale', 'saved_profile_required', 'staged_not_published'))
KEY = 'calendar_handoff'


class CalendarBatchError(RuntimeError):
    def __init__(self, suffix):
        self.code = 'desktop_market_fx_batch_calendar_' + suffix
        super().__init__(self.code)


def _load(space, context, ref):
    try:
        value = valuation._load(*valuation._root(space, context), ref)
    except (ValueError, execution.MarketFxBatchExecutionError) as error:
        raise CalendarBatchError('input_invalid') from error
    if value['request'].get('use_saved_calendars') is not True:
        raise CalendarBatchError('saved_profile_required')
    if value['staged_source_count']:
        raise CalendarBatchError('staged_not_published')
    return value


def _calendar_fingerprint(sources):
    scoped = {k: v for k, v in sources.items() if k.startswith(('market-calendar-v1/', '@code/'))}
    scoped['@handoff_code'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    scoped['@binding_code'] = hashlib.sha256(Path(__file__).with_name('desktop_market_fx_batch_binding_v1.py').read_bytes()).hexdigest()
    return execution._sha(scoped)


def _marker(batch):
    marker = batch[KEY]
    if (not isinstance(marker, dict) or set(marker) != {'version', 'preview_ref', 'valuation_fingerprint', 'calendar_fingerprint'}
        or type(marker['version']) is not int or marker['version'] != 1
        or any(not isinstance(marker[k],str) for k in ('preview_ref','valuation_fingerprint','calendar_fingerprint'))):
        raise CalendarBatchError('input_invalid')
    return marker


def assert_calendar_current(space, context, batch):
    """Small read-only gate; independent of this batch's expected native writes."""
    if KEY not in batch:
        return
    marker = _marker(batch)
    space = execution._space(space, execution._context(context))
    try:
        current = valuation._sources(Path(space), True, calendar_only=True)
    except (ValueError, OSError, execution.MarketFxBatchExecutionError) as error:
        raise CalendarBatchError('stale') from error
    if _calendar_fingerprint(current) != marker['calendar_fingerprint']:
        raise CalendarBatchError('stale')


def _assert_unreserved(space, context, value, own_ref=None):
    """Check the ORIGINAL selection, including closed spans trimmed from requests."""
    from migrations.reference import desktop_market_fx_batch_publication_v1 as publication
    targets = value['request']['targets']
    listings = {t['listing_ref'] for t in targets if t['listing_ref'] is not None}
    currencies = {t['mapping']['provider_currency'] for t in targets if t['mapping'] is not None}
    for saved in execution.list_market_fx_batches_v1(space, context):
        if saved['execution_ref'] == own_ref:
            continue
        batch = execution.load_market_fx_batch_v1(space, context, saved['execution_ref'])['trusted_batch']
        progress = publication.read_market_fx_batch_progress_v1(space, context, batch)
        for item, state in zip(batch['items'], progress['items']):
            if state['status'] == 'published':
                continue
            native = item['execution_binding']['trusted_preview']
            selected = (native['listing']['listing_ref'] in listings if item['kind'] == 'market' else
                        native['source_currency'] in currencies and native['target_currency'] == 'EUR')
            if selected and item['start_date'] <= value['request']['end_date'] and item['end_date'] >= value['request']['start_date']:
                raise execution.MarketFxBatchExecutionError('desktop_market_fx_batch_recovery_required')


def _derive(space, value, created_at):
    """Only sealed server-owned targets/requirements; no browser-provided ranges."""
    execution._utc(created_at)
    root = space / valuation.AREA
    if not len(value['request']['targets']) == len(value['summaries']) == len(value['blobs']):
        raise CalendarBatchError('input_invalid')
    items, targets, dispositions, blockers = [], [], [], []
    def add(kind, consumer, consumer_ref, currency, plan, target, reason):
        if plan is None:
            dispositions.append(dict(kind=kind, consumer=consumer, consumer_ref=consumer_ref, disposition=reason,
                                     day_count=(date.fromisoformat(value['request']['end_date'])-
                                                date.fromisoformat(value['request']['start_date'])).days+1))
            blockers.append(dict(asset_name=consumer, disposition=reason, next_action='Zuordnung/Kalender separat prüfen'))
            return
        for key, count in sorted(plan['counts'].items()):
            dispositions.append(dict(kind=kind, consumer=consumer, consumer_ref=consumer_ref, disposition=key, day_count=count))
            if key in {'blocked', 'source_gap_review', 'closed_source_gap_review', 'calendar_conflict'}:
                blockers.append(dict(asset_name=consumer, disposition=key, next_action='Bestehenden Nachweis separat prüfen; kein automatischer Ersatzabruf'))
        for window in plan['ranges']:
            item = dict(kind=kind, consumer=consumer, consumer_ref=consumer_ref, source_currency=currency,
                target_currency='EUR', route=currency+'→EUR', start_date=window['start_date'], end_date=window['end_date'],
                calendar_day_count=window['calendar_day_count'], provider_call_count=1, disposition='fetch_once')
            items.append(item)
            targets.append(dict(target, kind=kind, item_fingerprint=execution._sha(item)))
    for target, summary, entry in zip(value['request']['targets'], value['summaries'], value['blobs']):
        blob = valuation._blob(root, entry)
        add('market', target['asset_name'], target['asset_ref'],
            target['mapping']['provider_currency'] if target['mapping'] else '', blob.get('market_requirements'),
            {k: target[k] for k in ('listing_ref', 'mapping', 'promotion_binding')}, summary['disposition'])
    seen_fx = set()
    for entry in value['fx_evidence']:
        blob = valuation._blob(root, entry)
        source = blob['source']
        currency = source['base_currency'] if source['quote_currency'] == 'EUR' else source['quote_currency']
        if currency in seen_fx or 'EUR' not in {source['base_currency'], source['quote_currency']}:
            raise CalendarBatchError('input_invalid')
        seen_fx.add(currency)
        add('fx', currency+'/EUR', None, currency, blob.get('requirements'),
            dict(source_currency=currency, target_currency='EUR'), 'fx_requirements_unavailable')
    needed = {t['mapping']['provider_currency'] for t in value['request']['targets'] if t['mapping'] and t['mapping']['provider_currency'] != 'EUR'}
    for currency in sorted(needed-seen_fx):
        add('fx', currency+'/EUR', None, currency, None, {}, 'fx_requirements_unavailable')
    body = dict(contract_version='data_asset_center_market_fx_fetch_batch_preview_v1',
        status='ready_for_confirmation' if items else 'blocked_by_prerequisites' if blockers else 'nothing_to_fetch',
        created_at_utc=created_at, required_start_date=value['request']['start_date'], as_of_date=value['request']['end_date'],
        target_currency='EUR', items=items, item_count=len(items), provider_call_count=len(items),
        market_range_count=sum(i['kind']=='market' for i in items), fx_range_count=sum(i['kind']=='fx' for i in items),
        blockers=blockers, blocker_count=len(blockers), explicit_asset_disposition_count=len(value['summaries']),
        calendar_dispositions=dispositions, calendar_optimized=True, coverage_completion=False, silent_drop_count=0,
        confirmation_required=bool(items), **{k:False for k in execution.FALSE_FLAGS})
    body['batch_fingerprint'] = execution._sha(body)
    return body, targets


def validate_handoff(space, context, batch):
    if KEY not in batch:
        return
    context = execution._context(context)
    space = execution._space(space, context)
    marker = _marker(batch)
    value = _load(space, context, marker['preview_ref'])
    if value['fingerprint'] != marker['valuation_fingerprint'] or _calendar_fingerprint(value['sources']) != marker['calendar_fingerprint']:
        raise CalendarBatchError('stale')
    assert_calendar_current(space, context, batch)
    expected, _ = _derive(space, value, batch['created_at_utc'])
    raw = {k: v for k, v in batch.items() if k != KEY}
    raw['items'] = [{k: v for k, v in item.items() if k != 'execution_binding'} for item in batch['items']]
    if raw != expected:
        raise CalendarBatchError('input_invalid')
    own_ref = execution._identity(batch, context)
    path = space / execution.AREA / (own_ref+'.json')
    started = os.path.lexists(path)
    if started:
        execution._load(path, batch, context)
    elif valuation._sources(space, True) != value['sources']:
        raise CalendarBatchError('stale')
    _assert_unreserved(space, context, value, own_ref if started else None)


def preflight_before_claim(space, context, batch):
    """Called under the coordinator lock, before the first execution-state write."""
    if KEY not in batch:
        return
    space = execution._space(space, execution._context(context))
    marker = _marker(batch)
    value = _load(space, context, marker['preview_ref'])
    if value['fingerprint'] != marker['valuation_fingerprint']:
        raise CalendarBatchError('stale')
    current = valuation._sources(space, True)
    context_key = execution.AREA+'/.context'
    # A brand-new coordinator area may just have gained its verified context
    # marker and lock. Neither reserves a source range; no other delta is allowed.
    if context_key not in value['sources']:
        current.pop(context_key, None)
    if current != value['sources']:
        raise CalendarBatchError('stale')
    assert_calendar_current(space, context, batch)
    _assert_unreserved(space, context, value)


def prepare_calendar_batch(data_space_path, context, preview_ref, created_at):
    from migrations.reference import desktop_market_fx_batch_binding_v1 as binding
    context = execution._context(context)
    space = execution._space(data_space_path, context)
    value = _load(space, context, preview_ref)
    if valuation._sources(space, True) != value['sources']:
        raise CalendarBatchError('stale')
    _assert_unreserved(space, context, value)
    public, targets = _derive(space, value, created_at)
    if not public['items']:
        # No executable empty batch, confirmation, claim or receipt is fabricated.
        if valuation._sources(space, True) != value['sources']:
            raise CalendarBatchError('stale')
        return dict(trusted_batch=None, public_review=public)
    result = binding.prepare_market_fx_product_batch_v1(space, context, public, targets, created_at)
    batch = result['trusted_batch']
    batch[KEY] = dict(version=1, preview_ref=preview_ref, valuation_fingerprint=value['fingerprint'],
                      calendar_fingerprint=_calendar_fingerprint(value['sources']))
    validate_handoff(space, context, batch)
    return dict(trusted_batch=batch, public_review=binding.public_market_fx_binding_review_v1(batch, context))
