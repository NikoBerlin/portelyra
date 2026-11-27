"""Provider-free, single-listing calendar correction: exact sparse set, one transaction."""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import sqlite3
from migrations.reference import market_calendar_registry_v1 as registry
from migrations.reference.market_calendar_correction_v1 import _ctx, _utc, _sha, _abort, _profile, MarketCalendarCorrectionV1Error
from migrations.reference.market_calendar_v1 import classify_market_calendar_days_v1
from migrations.reference import daily_market_history_v1 as market
from migrations.reference.desktop_provider_probe_promotion_v1 import MARKET_AREA, STORE_NAME

VERSION = 'market_calendar_correction_batch_v1'
MAX_DAYS = 512


def _code():
    root = Path(__file__).resolve().parent
    names = ('market_calendar_correction_batch_v1.py', 'market_calendar_correction_v1.py',
        'market_calendar_v1.py', 'market_calendar_registry_v1.py', 'daily_market_history_v1.py')
    return _sha({n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names})


def _space(path, ctx):
    return registry._space(Path(path), registry._ctx(ctx, True))


@contextmanager
def _calendar_guard(space, ctx):
    # Registry is DELETE-journal only. Hold its shared read lock until the market
    # transaction commits, so a calendar revision cannot commit between check/write.
    store = registry._store(space, False)
    con = sqlite3.connect(store.as_uri() + '?mode=ro', uri=True, timeout=0)
    try:
        con.execute('PRAGMA query_only=ON')
        con.execute('BEGIN')
        con.execute('SELECT count(*) FROM calendar_binding').fetchone()
        yield
    finally:
        con.close()


def _dates(dates):
    if (not isinstance(dates, list) or not 1 <= len(dates) <= MAX_DAYS
        or any(not isinstance(d, str) for d in dates)):
        _abort('market_calendar_correction_input_invalid')
    if len(set(dates)) != len(dates):
        _abort('market_calendar_correction_input_invalid')
    return sorted(dates)


def _origin(space):
    from migrations.reference.data_space_relocation_v1 import origin_v1  # Ursprungsort nach einem Restore an einen anderen Ort (#493), sonst der Datenraum selbst.
    return origin_v1(space)


def preview_market_calendar_correction_batch_v1(path, context, listing_ref, dates, created):
    ctx = _ctx(context); space = _space(path, ctx); _utc(created); dates = _dates(dates)
    with _calendar_guard(space, ctx):
        binding = _profile(space, ctx, 'listing', listing_ref)
        reader = market.MarketHistoryContext(ctx['tenant_id'], ctx['user_id'], ctx['data_space_id'], 'portfolio_reader', 'portfolio_worker')
        history = market.read_daily_market_history_v1(space / MARKET_AREA / STORE_NAME, reader, listing_ref, dates[0], dates[-1])
        by_date = {d['trading_date']: d for d in history['days']}
        selected = [by_date[d] for d in dates]
        if any(d['day_status'] != 'source_gap' for d in selected):
            _abort('market_calendar_correction_not_applicable')
        classified = classify_market_calendar_days_v1(binding['profile'],
            [{'date': d, 'source_status': 'source_gap'} for d in dates])['rows']
        if any(d['disposition'] != 'calendar_correction_proposed' or d['proposed_status'] != 'non_trading_day' for d in classified):
            _abort('market_calendar_correction_not_applicable')
        body = dict(contract_version=VERSION, scope_kind='listing', scope_ref=listing_ref,
            path_fingerprint=_sha(str(_origin(space))), context_fingerprint=_sha(ctx), code_fingerprint=_code(),
            profile_fingerprint=binding['profile']['profile_fingerprint'], binding_revision=binding['binding_revision'],
            created_at_utc=created, rows=[dict(date=d, supersedes_revision_ref=current['market_day_revision_ref'],
                calendar_reason=classification['calendar_reason']) for d,current,classification in zip(dates,selected,classified)])
    return {**body, 'candidate_fingerprint': _sha(body)}


def public_market_calendar_correction_batch_v1(candidate):
    if (not isinstance(candidate, dict) or candidate.get('contract_version') != VERSION
        or candidate.get('candidate_fingerprint') != _sha({k:v for k,v in candidate.items() if k != 'candidate_fingerprint'})):
        _abort('market_calendar_correction_preview_invalid')
    rows = [dict(date=r['date'], source_status='source_gap', proposed_status='non_trading_day',
        calendar_reason=r['calendar_reason']) for r in candidate['rows']]
    return dict(contract_version=VERSION+'_public', status='pending_confirmation', scope_kind='listing',
        day_count=len(rows), rows=rows, atomic=True, confirmation_required=True, silent_drop_count=0,
        provider_access=False, history_write=False, canonical_write=False)


def _sealed(candidate, ctx):
    fp = candidate['candidate_fingerprint']; scope=candidate['scope_ref']
    writer = market.MarketHistoryContext(ctx['tenant_id'], ctx['user_id'], ctx['data_space_id'], 'market_worker', 'market_worker')
    req='mrq_'+fp[:32]; source='msr_'+_sha({'calendar':candidate['profile_fingerprint']})[:32]
    rows=[]
    for r in candidate['rows']:
        rows.append(dict(trading_date=r['date'], revision_mode='correction', supersedes_revision_ref=r['supersedes_revision_ref'],
            day_status='non_trading_day', bar_shape='not_applicable', open_decimal=None, high_decimal=None,
            low_decimal=None, close_decimal=None, adjusted_close_decimal=None, volume_decimal=None,
            valuation_status='not_applicable', quality_status='calendar_confirmed', gap_reason=None,
            corporate_action_status='not_applicable', source_observation_ref='mor_'+_sha({'batch':fp,'date':r['date']})[:32],
            observed_at_utc=candidate['created_at_utc'], correction_reason='calendar_correction'))
    sealed=market.seal_daily_market_calendar_corrections_v1(listing_ref=scope, request_ref=req,
        source_kind='manual_reviewed_evidence', source_ref=source, source_version='market_calendar_batch_v1.0.0',
        request_fingerprint=fp, job_binding_fingerprint=market.daily_market_history_job_binding_fingerprint_v1(writer,
            listing_ref=scope, request_ref=req, request_fingerprint=fp, source_ref=source),
        retrieved_at_utc=candidate['created_at_utc'], requested_dates=[r['date'] for r in candidate['rows']], days=rows)
    return writer,sealed


def apply_market_calendar_correction_batch_v1(path, context, candidate, public, confirmed, completed, *, failpoint=None):
    ctx=_ctx(context);space=_space(path,ctx);_utc(completed)
    if confirmed is not True:
        _abort('market_calendar_correction_confirmation_required')
    if (public != public_market_calendar_correction_batch_v1(candidate)
        or candidate['context_fingerprint'] != _sha(ctx) or candidate['path_fingerprint'] != _sha(str(_origin(space)))
        or candidate['code_fingerprint'] != _code() or completed < candidate['created_at_utc']):
        _abort('market_calendar_correction_preview_invalid')
    writer,sealed=_sealed(candidate,ctx);store=space/MARKET_AREA/STORE_NAME
    with _calendar_guard(space,ctx):
        binding=_profile(space,ctx,'listing',candidate['scope_ref'])
        if binding['binding_revision'] != candidate['binding_revision'] or binding['profile']['profile_fingerprint'] != candidate['profile_fingerprint']:
            _abort('market_calendar_correction_stale')
        receipt=market.read_daily_market_request_receipt_v1(store,writer,sealed['request_ref'])
        if receipt is not None:
            if receipt.candidate_fingerprint != sealed['candidate_fingerprint']:
                _abort('market_calendar_correction_preview_invalid')
        else:
            fresh=preview_market_calendar_correction_batch_v1(space,ctx,candidate['scope_ref'],
                [r['date'] for r in candidate['rows']],candidate['created_at_utc'])
            if fresh != candidate:
                _abort('market_calendar_correction_stale')
            receipt=market.append_daily_market_history_v1(store,writer,sealed,completed,failpoint=failpoint)
        if receipt.corrected_day_count != public['day_count'] or receipt.appended_day_count or receipt.unchanged_day_count:
            _abort('market_calendar_correction_write_failed')
    return dict(status='published', day_count=public['day_count'], corrected_day_count=receipt.corrected_day_count,
        dates=[r['date'] for r in candidate['rows']], exact_replay=receipt.exact_replay, atomic=True,
        provider_access=False, canonical_write=False, silent_drop_count=0)
