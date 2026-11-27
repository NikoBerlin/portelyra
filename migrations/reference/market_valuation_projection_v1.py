"""Exact, provider-free valuation projection. Source prices are never overwritten."""
from datetime import date, timedelta
from fractions import Fraction
from migrations.reference.fx_history_v1 import _fraction_from_decimal
from workers.reference.semantic_realized_fifo_v2 import _decimal_or_none
from migrations.reference.market_calendar_v1 import validate_market_calendar_profile_v1


# Abgeleitete, uebertragene Kurse: kein nativer Kurs der Quelle fuer diesen Tag.
SUBSTITUTE_BASES = frozenset({'imputed_source_gap','imputed_after_source_gap','imputed_non_trading_day','trade_price_reference'})


def valuation_policy(value=None):
    """Missing option means strict. Last-valid requires an explicit calendar-day age."""
    if value is None:return {'mode':'strict','max_age_days':None,'age_unit':'calendar_days','carry_across_blocked':False}
    if not isinstance(value,dict) or set(value) not in ({'mode','max_age_days','age_unit'},{'mode','max_age_days','age_unit','carry_across_blocked'}):raise ValueError('valuation_policy_invalid')
    if value['age_unit']!='calendar_days':raise ValueError('valuation_policy_invalid')
    # Fehlt der Schalter, gilt das bisherige Verhalten: Eine Sperre unterbricht die
    # Kette. Wer ihn setzt, muss True oder False sagen (#368, 28.09.2026).
    if value.get('carry_across_blocked',False) not in (True,False) or type(value.get('carry_across_blocked',False)) is not bool:raise ValueError('valuation_policy_invalid')
    if value['mode']=='strict':
        if value['max_age_days'] is not None:raise ValueError('valuation_policy_invalid')
    elif value['mode']=='last_valid':
        # None heisst ausdruecklich ohne Altersgrenze: eine haendisch gepflegte oder
        # duenne Kursreihe darf beliebig grosse Luecken fortschreiben (#283).
        if value['max_age_days'] is not None and (type(value['max_age_days']) is not int or not 1<=value['max_age_days']<=366):raise ValueError('valuation_policy_invalid')
    else:raise ValueError('valuation_policy_invalid')
    return {**value,'carry_across_blocked':bool(value.get('carry_across_blocked',False))}


def _limit(first, second):
    """Ohne Altersgrenze zaehlt die jeweils andere Grenze."""
    return first if second is None else min(first, second)


def initial_valuation_carry():
    """Der Uebertrag vor dem ersten Tag: kein Vorgaenger, keine ueberquerte Luecke."""
    return {'previous_date':None,'previous_value':None,'crossed_gap':False}


def valuation_day_step(carry, day, max_age, policy):
    """Ein Tag der Bewertungsreihe. Reine Funktion: gleicher Uebertrag und gleicher
    Tag ergeben immer dieselbe Zeile und denselben Folgeuebertrag.

    Hierauf beruht die inkrementelle Fortschreibung: Ein Tag haengt ausschliesslich
    vom Uebertrag des Vortages ab, nie von spaeteren Tagen. Neuaufbau und
    Fortschreibung rufen dieselbe Funktion - der eine oft, der andere einmal -,
    und genau deshalb kommt zwingend dasselbe heraus (#283, 26.09.2026).

    day traegt: date (ISO), status, value, closed, calendar_reason, blocked_reason.
    """
    previous_date=carry['previous_date'];previous_value=carry['previous_value'];crossed_gap=carry['crossed_gap']
    key=day['date'];status=day['status'];closed=day['closed'];blocked_reason=day.get('blocked_reason')
    value=source=age=None
    def elapsed():
        return (date.fromisoformat(key)-date.fromisoformat(previous_date)).days
    if blocked_reason is not None:
        # Der gesperrte Tag selbst bleibt ohne Wert. Ob er auch den Vorgaenger
        # loescht, entscheidet die Richtlinie: Eine Sperre sagt nur, dass ueber
        # diesen einen Tag nichts feststeht - der Kurs des Vortages bleibt ein
        # Fakt. Ohne den Schalter steckte die Sperre alle Folgetage an, und betroffene
        # Assets blieben dauerhaft ohne Wert (#368, 28.09.2026).
        basis=blocked_reason
        if policy['carry_across_blocked'] and previous_date is not None:crossed_gap=True
        else:previous_date=None;previous_value=None;crossed_gap=False
    elif status=='observed':
        value=day['value'];source=key;age=0
        previous_date=key;previous_value=value;basis='observed';crossed_gap=False
    elif closed:
        if previous_date is None:basis='no_predecessor'
        else:
            age=elapsed()
            limit=_limit(max_age,policy['max_age_days']) if crossed_gap else max_age
            if age>limit:basis='stale_predecessor'
            else:value=previous_value;source=previous_date;basis='imputed_after_source_gap' if crossed_gap else 'imputed_closed_day'
    elif status=='source_gap' and policy['mode']=='last_valid':
        # Nur eine ausdruecklich festgehaltene Quellluecke zaehlt, kein ungeholter Tag.
        crossed_gap=True
        if previous_date is None:basis='no_predecessor'
        else:
            age=elapsed()
            if policy['max_age_days'] is not None and age>policy['max_age_days']:basis='stale_predecessor'
            else:value=previous_value;source=previous_date;basis='imputed_source_gap'
    elif status=='non_trading_day' and policy['mode']=='last_valid' and previous_date is not None:
        # Die Quelle meldet den Tag als handelsfrei, der Kalender des Assets erwartet
        # aber einen Wert - etwa ein Devisenfeiertag bei einem 24/7-Asset. Der
        # Vortageskurs wird uebertragen und ausdruecklich als abgeleitet markiert,
        # statt den Tag offen zu lassen und die Kette zu unterbrechen (#283).
        age=elapsed()
        if policy['max_age_days'] is not None and age>policy['max_age_days']:
            basis='stale_predecessor';previous_date=None;previous_value=None;crossed_gap=False
        else:
            value=previous_value;source=previous_date;basis='imputed_non_trading_day'
    else:
        basis='calendar_conflict' if status=='non_trading_day' else status
        previous_date=None;previous_value=None;crossed_gap=False  # Unfetched/conflicting/strict gaps remain barriers.
    row={'date':key,'source_status':status,'original_value':day['value'],
         'value':value,'basis':basis,'source_date':source,'age_days':age,
         'calendar_reason':day['calendar_reason'],'observation_on_closed_day':status=='observed' and closed,
         'substitution_used':basis in SUBSTITUTE_BASES}
    return row,{'previous_date':previous_date,'previous_value':previous_value,'crossed_gap':crossed_gap}


def effective_series(days, calendar, start, end, max_age, blocked=None, *, gap_policy=None, carry=None, with_carry=False):
    """Faltung ueber valuation_day_step. Mit carry beginnt sie bei einem
    festgehaltenen Stand statt beim Profilbeginn; with_carry gibt den Endstand mit
    zurueck, damit der naechste Lauf dort weitermacht."""
    policy=valuation_policy(gap_policy)
    profile=validate_market_calendar_profile_v1(calendar)
    begin=date.fromisoformat(start); finish=date.fromisoformat(end)
    if type(max_age) is not int or not 0<=max_age<=366 or finish<begin:raise ValueError('valuation_range_invalid')
    if not profile['valid_from']<=start<=end<=profile['valid_to']:raise ValueError('valuation_calendar_range_invalid')
    closures={r['date']:r['reason'] for r in profile['closure_dates']}; openings=set(profile['special_open_dates'])
    by_date={}; blocked={} if blocked is None else blocked
    for row in days:
        if not isinstance(row,dict) or set(row)!={'date','status','value'}:raise ValueError('valuation_day_invalid')
        key=row['date']
        if not isinstance(key,str) or date.fromisoformat(key).isoformat()!=key:raise ValueError('valuation_day_invalid')
        if key in by_date or not profile['valid_from']<=key<=end:raise ValueError('valuation_day_invalid')
        if row['status'] not in {'observed','non_trading_day','source_gap','not_requested'}:raise ValueError('valuation_day_invalid')
        value=row['value']
        if row['status']=='observed':
            if not isinstance(value,str) or _fraction_from_decimal(value)<=0:raise ValueError('valuation_value_invalid')
        elif value is not None:raise ValueError('valuation_value_invalid')
        by_date[key]=row
    if carry is None:
        state=initial_valuation_carry();cursor=date.fromisoformat(profile['valid_from'])
    else:
        if set(carry)!={'previous_date','previous_value','crossed_gap','resume_from'}:raise ValueError('valuation_carry_invalid')
        state={k:carry[k] for k in ('previous_date','previous_value','crossed_gap')}
        cursor=date.fromisoformat(carry['resume_from'])
        if not profile['valid_from']<=carry['resume_from']:raise ValueError('valuation_carry_invalid')
    result={}
    while cursor<=finish:
        key=cursor.isoformat();row=by_date.get(key,{'status':'not_requested','value':None})
        closed=key not in openings and (key in closures or cursor.isoweekday() not in profile['session_weekdays'])
        entry,state=valuation_day_step(state,{
            'date':key,'status':row['status'],'value':row['value'],'closed':closed,
            'calendar_reason':closures.get(key,'weekly_closed' if closed else 'scheduled_session'),
            'blocked_reason':blocked.get(key)},max_age,policy)
        if cursor>=begin:result[key]=entry
        cursor+=timedelta(days=1)
    if with_carry:return result,{**state,'resume_from':(finish+timedelta(days=1)).isoformat()}
    return result


def convert_series(prices, source_currency, target_currency, fx=None, direction='direct'):
    if direction not in {'direct','inverse'}:raise ValueError('valuation_direction_invalid')
    rows=[]
    for key,price in prices.items():
        rate=None if fx is None else fx.get(key)
        value=None;factor=None
        if price['value'] is None:status='market_unavailable'
        elif source_currency==target_currency:
            status='native';factor=Fraction(1);value=_fraction_from_decimal(price['value'])
        elif rate is None or rate['value'] is None:status='fx_unavailable'
        else:
            factor=_fraction_from_decimal(rate['value'])
            if factor<=0:raise ValueError('valuation_rate_invalid')
            if direction=='inverse':factor=1/factor
            value=_fraction_from_decimal(price['value'])*factor;status='converted'
        substituted=value is not None and (price['basis'] in SUBSTITUTE_BASES or (source_currency!=target_currency and rate is not None and rate['basis'] in SUBSTITUTE_BASES))
        rows.append({'date':key,'native_currency':source_currency,'target_currency':target_currency,
            'substitution_used':substituted,'valuation_status':'incomplete' if value is None else 'substituted' if substituted else 'complete',
            'original_price':price['original_value'],'effective_price':price['value'],
            'price_basis':price['basis'],'price_source_date':price['source_date'],'price_age_days':price['age_days'],
            'price_calendar_reason':price['calendar_reason'],'price_on_closed_day':price['observation_on_closed_day'],
            'fx_rate':None if rate is None else rate['value'],'fx_basis':'identity' if source_currency==target_currency else 'pair_missing' if rate is None else rate['basis'],
            'fx_source_date':None if rate is None else rate['source_date'],'fx_age_days':None if rate is None else rate['age_days'],
            'fx_calendar_reason':None if rate is None else rate['calendar_reason'],
            'direction':'identity' if source_currency==target_currency else 'unbound' if fx is None else direction,
            'status':status,'target_decimal':None if value is None else _decimal_or_none(value),
            'target_numerator':None if value is None else str(value.numerator),
            'target_denominator':None if value is None else str(value.denominator)})
    return rows
