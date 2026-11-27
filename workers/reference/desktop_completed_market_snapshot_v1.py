"""Read completed unit valuations and project exact noncash market values.

No writes, provider, synthetic observation, FX store, cash or tax authority.
The existing Desktop Workflow writer alone publishes the resulting snapshot part.
"""
from datetime import date
from fractions import Fraction
from pathlib import Path
import hashlib
from migrations.reference import desktop_market_valuation_v1 as valuation
from workers.reference.semantic_realized_fifo_v2 import _decimal_or_none
from migrations.reference.fx_history_v1 import _fraction_from_decimal

FIELDS={'preview_ref','valuation_fingerprint','receipt_fingerprint','as_of_date','bridge_fingerprint'}
SUPPORTED={'equity','fund','crypto','commodity','metal'}


def fail(code):
    valuation.invalid(code)


def read_completed(space, context, preview_ref, as_of_date):
    """Worker/Data read boundary. Full source and receipt check, before and after."""
    ctx=valuation.files._context(context);space=valuation.files._space(space,ctx)
    if not isinstance(as_of_date,str) or date.fromisoformat(as_of_date).isoformat()!=as_of_date:fail('input_invalid')
    root,bound=valuation._root(space,ctx);value=valuation._load(root,bound,preview_ref)
    if value['staged_source_count']:fail('staged_not_published')
    receipt_path=root/('completed-'+preview_ref+'.json')
    if not receipt_path.exists():fail('completion_required')
    receipt=valuation.files._read(receipt_path)
    if (set(receipt)!={'preview_ref','fingerprint','completed_at_utc'} or receipt['preview_ref']!=preview_ref
        or receipt['fingerprint']!=value['fingerprint']):fail('store_invalid')
    valuation.files._utc(receipt['completed_at_utc'])
    request=value['request']
    if request['target_currency']!='EUR' or not request['start_date']<=as_of_date<=request['end_date']:fail('period_uncovered')
    def fresh():
        if valuation._sources(space,request.get('use_saved_calendars',False))!=value['sources']:fail('stale')
    fresh()
    if not len(request['targets'])==len(value['blobs'])==len(value['summaries']):fail('store_invalid')
    units={}
    # Die Tagesreihe steht im Bewertungsstand, sofern es eine Notierung gibt; der
    # Beleg nennt dann nur ihren Bereich. Genau einen Tag daraus zu lesen ist eine
    # Abfrage - das ist die Grundlage des schnellen Snapshots (#283, 26.09.2026).
    store=None
    try:
        for target,entry in zip(request['targets'],value['blobs']):
            blob=valuation._blob(root,entry)
            if blob.get('scope_ref'):
                if store is None:
                    store=valuation.valuation_state.open_market_valuation_state_v1(
                        valuation._state_path(space),ctx)
                rows=valuation.valuation_state.read_valuation_rows_v1(
                    store,blob['scope_ref'],as_of_date,as_of_date)
            else:
                rows=[r for r in (blob['rows'] or ()) if r['date']==as_of_date]
            if len(rows)!=1 or target['asset_id'] in units:fail('store_invalid')
            units[target['asset_id']]={'asset_name':target['asset_name'],'day':rows[0],
                'valuation_policy':valuation.valuation_policy(request.get('valuation_policy'))}
    finally:
        if store is not None:store.close()
    for entry in value['fx_evidence']:valuation._blob(root,entry)
    fresh()
    if valuation.files._read(receipt_path)!=receipt or valuation._load(root,bound,preview_ref)!=value:fail('stale')
    binding={'preview_ref':preview_ref,'valuation_fingerprint':value['fingerprint'],
             'receipt_fingerprint':valuation.files._sha(receipt),'as_of_date':as_of_date,
             'bridge_fingerprint':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    return binding,units


def read_for_run(space, context, preview_ref, as_of_date):
    binding,units=read_completed(space,context,preview_ref,as_of_date)
    return {'binding':binding,'summary':{'as_of_date':as_of_date,'selected_asset_count':len(units),
        'valued_asset_count':sum(v['day']['status'] in {'native','converted'} for v in units.values()),
        'valuation_policy':valuation.valuation_policy(next(iter(units.values()),{}).get('valuation_policy')),
        'substituted_asset_count':sum(v['day'].get('substitution_used',False) for v in units.values()),
        'provider_access':False,'portfolio_completion':False}}


def validate_for_run(payload):
    """No fallback to a different completion or to manual inputs on stale evidence."""
    expected=payload['market_valuation_binding'];runtime=payload['runtime']
    if (not isinstance(expected,dict) or set(expected)!=FIELDS or any(not isinstance(v,str) for v in expected.values())
        or payload['portfolio']['base_currency']!='EUR' or expected['as_of_date']!=payload['as_of_date']
        or payload['cutoff_at_utc']!=payload['as_of_date']+'T23:59:59Z'):fail('input_invalid')
    for config in payload['asset_inputs']:
        if config['close_decimal'] is not None or config['fx_rate_decimal'] is not None or config['fx_direction']!='none':fail('source_conflict')
    space=Path(runtime['canonical_path']).parent
    ctx={k:runtime[k] for k in ('tenant_id','user_id','data_space_id')}
    binding,units=read_completed(space,ctx,expected['preview_ref'],expected['as_of_date'])
    if binding!=expected:fail('stale')
    # The old ledger's unchanged bytes do not prove it is still the active generation.
    from migrations.reference.desktop_product_asset_activity_v1 import (
        DesktopProductAssetActivityContextV1,read_desktop_product_asset_activity_binding_v1)
    active=read_desktop_product_asset_activity_binding_v1(space,DesktopProductAssetActivityContextV1(**ctx,actor_id='snapshot_reader'))
    if runtime['ledger_schema_version']==401:
        if active['status']!='available' or active['ledger_path']!=runtime['ledger_path'] or active['ledger_fingerprint']!=runtime['ledger_fingerprint']:fail('stale')
    elif active['status']!='absent':fail('stale')
    return units


def ratio(value):
    return None if value is None else {'numerator':str(value.numerator),'denominator':str(value.denominator),'decimal':_decimal_or_none(value)}


def _unit(day, policy=None):
    policy=valuation.valuation_policy(policy)
    for prefix in ('price',) if day['status']=='native' else ('price','fx'):
        basis=day[prefix+'_basis'];source=day[prefix+'_source_date'];age=day[prefix+'_age_days']
        substituted=basis in valuation.SUBSTITUTE_BASES
        trade_observation=basis=='trade_price_reference' and prefix=='price' and age==0
        if basis=='trade_price_reference' and (prefix!='price' or day.get('price_source_kind')!='confirmed_trade_price_reference'):fail('store_invalid')
        if substituted and not trade_observation and (policy['mode']!='last_valid' or type(age) is not int or age>policy['max_age_days']):fail('store_invalid')
        if (basis not in {'observed','imputed_closed_day'}|valuation.SUBSTITUTE_BASES or not isinstance(source,str) or type(age) is not int
            or not 0<=age<=366 or (date.fromisoformat(day['date'])-date.fromisoformat(source)).days!=age
            or (basis!='trade_price_reference' and (basis=='observed')!=(age==0))):fail('store_invalid')
    n,d=day['target_numerator'],day['target_denominator']
    if not isinstance(n,str) or not isinstance(d,str):fail('store_invalid')
    value=Fraction(int(n),int(d))
    if value<=0 or (str(value.numerator),str(value.denominator))!=(n,d) or day['target_decimal']!=_decimal_or_none(value):fail('store_invalid')
    if day['target_currency']!='EUR' or day['price_source_date']>day['date']:fail('store_invalid')
    native=_fraction_from_decimal(day['effective_price'])
    if day['status']=='native':
        if day['native_currency']!='EUR' or day['direction']!='identity' or day['fx_basis']!='identity' or native!=value:fail('store_invalid')
    else:
        if day['native_currency']=='EUR' or day['fx_source_date']>day['date'] or day['direction'] not in {'direct','inverse'}:fail('store_invalid')
        fx=_fraction_from_decimal(day['fx_rate'])
        if fx<=0 or value!=native*(fx if day['direction']=='direct' else 1/fx):fail('store_invalid')
    return value


def project(positions, assets_by_ref, units, binding):
    """All FIFO rows and selected unit assets receive an explicit disposition."""
    if len(positions)>10000:fail('capacity_invalid')
    policies=[valuation.valuation_policy(u.get('valuation_policy')) for u in units.values()]
    policy=policies[0] if policies else valuation.valuation_policy()
    if any(p!=policy for p in policies):fail('store_invalid')
    rows=[];seen=set();represented=set();missing=held=substituted_count=0;known=Fraction(0)
    accounts={key:i for i,key in enumerate(sorted({r['account_ref'] for r in positions}),1)}
    for position in positions:
        if position['position_ref'] in seen:fail('store_invalid')
        seen.add(position['position_ref'])
        config=assets_by_ref.get(position['asset_ref']);unit=None
        if config is not None:
            represented.add(config['asset_id']);unit=units.get(config['asset_id'])
        day=None if unit is None else unit['day']
        quantity=_fraction_from_decimal(position['remaining_quantity_decimal'])
        price=value=None;substituted=False
        if position['asset_type']=='cash':status='cash_excluded'
        elif quantity==0:status='zero_position'
        else:
            held+=1
            if quantity<0:status='short_position_unsupported'
            elif position['asset_type'] not in SUPPORTED:status='asset_type_unsupported'
            elif config is None:status='asset_identity_unavailable'
            elif config['asset_type']!=position['asset_type']:status='asset_type_conflict'
            elif day is None:status='asset_not_selected'
            elif day['date']!=binding['as_of_date']:fail('period_uncovered')
            elif day['status'] not in {'native','converted'}:status=day['status']
            else:
                price=_unit(day,policy);value=quantity*price;known+=value;status='valued'
                substituted=day['price_basis'] in valuation.SUBSTITUTE_BASES or (day['status']=='converted' and day['fx_basis'] in valuation.SUBSTITUTE_BASES)
                if 'substitution_used' in day and day['substitution_used'] is not substituted:fail('store_invalid')
                substituted_count+=int(substituted)
            if value is None:missing+=1
        rows.append({'ordinal':len(rows)+1,'account_ordinal':accounts[position['account_ref']],
            'basis_currency':position['currency'],'asset_label':'Unresolved position' if config is None else config['display_name'],
            'asset_type':position['asset_type'],'status':status,'quantity':ratio(quantity),
            'substitution_used':substituted,
            'unit_value_eur':ratio(price),'market_value_eur':ratio(value),
            **{k:None if day is None else day.get(k) for k in ('price_basis','price_source_date','price_age_days',
                'fx_basis','fx_source_date','fx_age_days')}})
    return {'version':1,'status':'complete' if missing==0 else 'incomplete','as_of_date':binding['as_of_date'],
        'currency':'EUR','position_count':len(rows),'held_noncash_position_count':held,'unavailable_position_count':missing,
        'valuation_policy':policy,'substituted_position_count':substituted_count,
        'valuation_status':'incomplete' if missing else 'substituted' if substituted_count else 'complete',
        'known_market_value_eur':ratio(known),'total_market_value_eur':ratio(known) if missing==0 else None,
        'positions':rows,'selected_assets':[{'ordinal':i,'asset_label':unit['asset_name'],
            'disposition':'represented_in_fifo' if key in represented else 'no_portfolio_position'}
            for i,(key,unit) in enumerate(units.items(),1)],
        'source_fingerprint':binding['valuation_fingerprint'],'receipt_fingerprint':binding['receipt_fingerprint'],
        'freshness_scope':'checked_at_publication_not_live','silent_drop_count':0,
        'cash_included':False,'tax_included':False,'net_liquidation_included':False,'portfolio_completion':False}
