"""Provider-free saved-calendar selection and non-executable fetch requirements."""
from datetime import date, timedelta
from migrations.reference.market_calendar_v1 import validate_market_calendar_profile_v1, classify_market_calendar_days_v1


def saved_calendar(catalog, scope_kind, scope_ref, source, start, end):
    matches = [row for row in catalog['bindings'] if row['scope_kind'] == scope_kind and row['scope_ref'] == scope_ref]
    if len(matches) != 1:
        raise ValueError('calendar_profile_required')
    binding = matches[0]
    if binding.get('context_verified') is not True:
        raise ValueError('calendar_context_unverified')
    profile = validate_market_calendar_profile_v1(binding['profile'])
    if (profile['market_code'] != source['market_code'] or profile['timezone_name'] != source['timezone_name']
        or (source.get('calendar_code') == 'continuous_24_7' and profile['calendar_kind'] != 'continuous_24_7')
        or (profile['calendar_kind'] == 'continuous_24_7' and (profile['closure_dates'] or profile['special_open_dates']))):
        raise ValueError('calendar_scope_mismatch')
    if profile['valid_from'] > start or profile['valid_to'] < end:
        raise ValueError('calendar_period_uncovered')
    return dict(profile=profile, preset='saved_profile', warning='owner_reviewed_not_live_verified',
                binding_revision=binding['binding_revision'])


def calendar_requirements(rows, profile, start, end, blocked=None):
    """Disposition every requested date, retaining closed interiors of fetch windows.

    Source gaps never turn into automatic retries. Closed-only windows need no
    request but are NOT observation coverage or evidence of a usable predecessor.
    Native attempts/corporate-action blocks outrank the calendar. Output grants
    no execution authority and cannot replace an existing batch.
    """
    profile = validate_market_calendar_profile_v1(profile)
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if last < first or (last - first).days > 20000:
        raise ValueError('calendar_requirements_invalid')
    by_date = {}
    for row in rows:
        if row['date'] in by_date:
            raise ValueError('calendar_requirements_invalid')
        by_date[row['date']] = row
    dates = [(first + timedelta(days=i)).isoformat() for i in range((last-first).days+1)]
    source = [{'date':day, 'source_status':by_date.get(day, {}).get('status', 'not_requested')} for day in dates]
    classified = classify_market_calendar_days_v1(profile, source)['rows']
    result = []
    for raw, cal in zip(source, classified):
        day, status = raw['date'], raw['source_status']
        reason = (blocked or {}).get(day)
        if reason:
            disposition = 'blocked'
        elif status == 'observed':
            disposition = 'observed'
        elif status == 'not_requested':
            disposition = 'fetch_needed' if cal['session_expected'] else 'closed_no_fetch'
        elif status == 'source_gap':
            disposition = 'source_gap_review' if cal['session_expected'] else 'closed_source_gap_review'
        elif status == 'non_trading_day':
            disposition = 'calendar_conflict' if cal['session_expected'] else 'native_closed'
        else:
            raise ValueError('calendar_requirements_invalid')
        result.append(dict(date=day, source_status=status, session_expected=cal['session_expected'],
            calendar_reason=cal['calendar_reason'], disposition=disposition, block_reason=reason))
    ranges = []
    window = []
    def flush():
        needed = [i for i, row in enumerate(window) if row['disposition'] == 'fetch_needed']
        if needed:
            trimmed = window[needed[0]:needed[-1]+1]
            for row in trimmed:
                if row['disposition'] == 'closed_no_fetch':
                    row['disposition'] = 'fetch_window_closed_day'
            ranges.append(dict(start_date=trimmed[0]['date'], end_date=trimmed[-1]['date'],
                calendar_day_count=len(trimmed), session_day_count=len(needed)))
        window.clear()
    for row in result:
        if row['disposition'] in {'fetch_needed', 'closed_no_fetch'}:
            window.append(row)
        else:
            flush()
    flush()
    counts = {key:sum(row['disposition']==key for row in result) for key in sorted({row['disposition'] for row in result})}
    return dict(rows=result, ranges=ranges, range_count=len(ranges), counts=counts, day_count=len(result),
        profile_fingerprint=profile['profile_fingerprint'], silent_drop_count=0, provider_access=False,
        execution_authority=False, coverage_completion=False)
