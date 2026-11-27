"""Offline valuation calendar proposals; never rewrite source observations.

Rule calendars are reviewable proposals, not live exchange notices. Explicit
exceptions, validity limits and genuine observations take precedence. FX never
inherits an equity calendar. No Legacy code or network dependency.
"""
from datetime import date, timedelta
from migrations.reference.market_calendar_v1 import build_market_calendar_profile_v1

RULE_VERSION = 'valuation_calendar_rules_2026_2'


def _nth(year, month, weekday, ordinal):
    first = date(year, month, 1)
    return first + timedelta(days=(weekday-first.weekday()) % 7 + 7*(ordinal-1))


def _last(year, month, weekday):
    following = date(year+1, 1, 1) if month == 12 else date(year, month+1, 1)
    last = following-timedelta(days=1)
    return last-timedelta(days=(last.weekday()-weekday) % 7)


def _easter(year):
    # Gregorian computus, integer arithmetic; calendar dates, not price estimates.
    a=year%19; b=year//100; c=year%100; d=b//4; e=b%4
    f=(b+8)//25; g=(b-f+1)//3; h=(19*a+b-d-g+15)%30
    i=c//4; k=c%4; l=(32+2*e+2*i-h-k)%7; m=(a+11*h+22*l)//451
    n=h+l-7*m+114
    return date(year,n//31,n%31+1)


def _observed(day):
    return day-timedelta(days=1) if day.weekday()==5 else day+timedelta(days=1) if day.weekday()==6 else day


def propose_calendar(listing, start, end, exceptions, *, fx=False, use_rules=True):
    """Exceptions are exact date/reason proposals confirmed with the valuation."""
    start=date.fromisoformat(start); end=date.fromisoformat(end)
    code=listing['market_code']; continuous=listing['calendar_code']=='continuous_24_7'
    if listing['calendar_code'] not in {'continuous_24_7','weekday_fx' if fx else 'weekday_exchange'}:
        raise ValueError('calendar_profile_required')
    preset='continuous_24_7' if continuous else 'weekends_only'
    closed={}; warning=None
    if not fx and not continuous and use_rules:
        if code in {'NYQ','NMS','NGM','NCM','NYSE','NASDAQ','XNYS','XNAS'}:preset='us_equity_rules'
        elif code in {'GER','XETR','XETRA'}:preset='xetra_rules'
        else:warning='holiday_rules_unavailable'
        if preset in {'us_equity_rules','xetra_rules'} and not (2000<=start.year<=end.year<=2030):
            raise ValueError('calendar_rule_period_unsupported')
        for year in range(start.year,end.year+1):
            if preset=='us_equity_rules':
                new_year=date(year,1,1)
                # NYSE does not close the preceding Friday for a Saturday Jan 1.
                if new_year.weekday()!=5:closed[_observed(new_year)]='new_year'
                closed.update({_nth(year,1,0,3):'martin_luther_king',_nth(year,2,0,3):'presidents_day',
                    _easter(year)-timedelta(days=2):'good_friday',_last(year,5,0):'memorial_day',
                    _observed(date(year,7,4)):'independence_day',_nth(year,9,0,1):'labor_day',
                    _nth(year,11,3,4):'thanksgiving',_observed(date(year,12,25)):'christmas'})
                if year>=2022:closed[_observed(date(year,6,19))]='juneteenth'
            elif preset=='xetra_rules':
                closed.update({date(year,1,1):'new_year',_easter(year)-timedelta(days=2):'good_friday',
                    _easter(year)+timedelta(days=1):'easter_monday',date(year,5,1):'labor_day',
                    date(year,12,24):'christmas_eve',date(year,12,25):'christmas',
                    date(year,12,26):'boxing_day',date(year,12,31):'new_year_eve'})
        if preset=='xetra_rules':
            # Explicit historical exceptions, not a timeless German holiday rule.
            # Official Xetra annual calendars: docs/provider-symbol-currency-research.md.
            for text in ('2019-06-10','2019-10-03','2020-06-01','2021-05-24'):
                closed[date.fromisoformat(text)]='recorded_historical_xetra_closure'
        if preset=='us_equity_rules':
            for text in ('2001-09-11','2001-09-12','2001-09-13','2001-09-14','2004-06-11',
                         '2007-01-02','2012-10-29','2012-10-30','2018-12-05','2025-01-09'):
                closed[date.fromisoformat(text)]='recorded_exceptional_closure'
    closed={d:r for d,r in closed.items() if start<=d<=end}
    seen=set()
    for row in exceptions:
        if not isinstance(row,dict) or set(row)!={'date','reason'}:raise ValueError('calendar_exception_invalid')
        day=date.fromisoformat(row['date']); reason=row['reason']
        if not start<=day<=end or day in seen or not isinstance(reason,str) or not reason.strip() or len(reason)>120 or any(ord(c)<32 for c in reason):
            raise ValueError('calendar_exception_invalid')
        if continuous:raise ValueError('continuous_calendar_closure_invalid')
        seen.add(day);closed[day]=reason
    profile=build_market_calendar_profile_v1(profile_version=1,
        calendar_kind='continuous_24_7' if continuous else 'weekly_sessions',market_code=code,
        timezone_name=listing['timezone_name'],valid_from=start.isoformat(),valid_to=end.isoformat(),
        session_weekdays=list(range(1,8)) if continuous else [1,2,3,4,5],
        closure_dates=[{'date':d.isoformat(),'reason':r} for d,r in sorted(closed.items())],special_open_dates=[],
        source_kind='reviewed_manifest',source_ref=RULE_VERSION+':'+preset)
    return {'profile':profile,'preset':preset,'warning':warning,'confirmation_required':True}
