"""Read-only, explicit trade-price references; never a market-history writer.

No underlying-price substitution, contract multiplier inference, or forward fill
from future trades. Different prices with uncertain intraday ordering block.
"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path

from migrations.reference import desktop_product_asset_activity_v1 as activity


def daily_trade_rows(events, start, end):
    by_day = defaultdict(list)
    corporate_days = set()
    for event in events:
        if event['event_type'] == 'stock_dividend':
            corporate_days.add(event['local_date'])
        if event['event_type'] not in ('buy', 'sell'):
            continue
        day = event['local_date']
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError('trade_price_date_invalid')
        if start <= day <= end:
            by_day[day].append(event)
    rows = []
    barriers = {day: 'trade_price_corporate_action_review' for day in corporate_days if start <= day <= end}
    cursor = date.fromisoformat(start)
    while cursor <= date.fromisoformat(end):
        day = cursor.isoformat(); trades = by_day.get(day, [])
        price = None
        if trades:
            # A later buy/sell without an explicit unit price is not silently
            # skipped in favour of an earlier quote. Gross amounts can include
            # domain-specific scaling; this reader never infers a multiplier.
            if all(t['event_time_evidence'] == 'exact' and t['effective_at_utc'] for t in trades):
                def instant(t):
                    return datetime.fromisoformat(t['effective_at_utc'].replace('Z', '+00:00'))
                latest = max(instant(t) for t in trades)
                trades = [t for t in trades if instant(t) == latest]
            values = {t['unit_price_decimal'] for t in trades}
            if None in values:
                barriers[day] = 'trade_price_missing'
            elif len({Fraction(v) for v in values}) != 1:
                barriers[day] = 'trade_price_order_ambiguous'
            else:
                price = min(values)  # Stable text even for equivalent decimal spellings.
                if Fraction(price) <= 0:
                    raise ValueError('trade_price_invalid')
        rows.append({'date': day, 'status': 'observed' if price is not None else 'source_gap', 'value': price})
        cursor += timedelta(days=1)
    return rows, barriers


def read_asset_configuration(space, ctx, asset_id, method):
    context = activity.DesktopProductAssetActivityContextV1(**ctx, actor_id=ctx['user_id'])
    snapshot = activity._canonical_snapshot(Path(space)/'canonical.sqlite', context)
    assets = [a for a in snapshot['assets'] if a['asset_id'] == asset_id and a['status'] == 'active']
    if len(assets) != 1 or (assets[0]['valuation_method'] != method and not _timeline_allows(space, asset_id, method)):
        raise ValueError('desktop_market_valuation_mapping_invalid')
    return assets[0], snapshot


def _timeline_allows(space, asset_id, method):
    """Eigene Kurse und Trade-Preise auch, wenn die Bewertungs-Zeitleiste einen Abschnitt dieser Art fuehrt (rc.393) - etwa bis Tag X
    eigene Kurse, danach Yahoo. Nur fuer 'manual'; Marktabrufe bleiben an die heutige Art gebunden."""
    if method != 'manual':
        return False
    from migrations.reference.asset_valuation_timeline_v1 import timeline_v1
    return timeline_v1(space).has_method(asset_id, 'manual')


def read_trade_source(space, ctx, asset_id, start, end):
    """Use the existing schema401 binding/reader, never legacy transaction facts."""
    asset, snapshot = read_asset_configuration(space, ctx, asset_id, 'manual')
    context = activity.DesktopProductAssetActivityContextV1(**ctx, actor_id=ctx['user_id'])
    binding = activity.read_desktop_product_asset_activity_binding_v1(space, context)
    events = []
    if binding['status'] != 'absent':
        connection = activity._read_connection(Path(binding['ledger_path']))
        try:
            events = [dict(r) for r in connection.execute(
                'SELECT event_ref,event_type,local_date,event_time_evidence,effective_at_utc,unit_price_decimal,basis_currency '
                'FROM current_asset_activity_event WHERE (asset_id=? OR source_asset_id=?) AND local_date>=? AND local_date<=? '
                "AND event_type IN ('buy','sell','stock_dividend') ORDER BY local_date,event_ref", (asset_id,asset_id,start,end))]
        finally:
            connection.close()
    rows, barriers = daily_trade_rows(events, start, end)
    for event in events:
        if event['basis_currency'] != asset['price_currency']:
            barriers[event['local_date']] = 'trade_price_currency_conflict'
    # Ein Split (#451) ist wie eine Stueckdividende eine Grenze: Ein Stueckpreis davor gilt fuer alte Stuecke und wird nicht
    # darueber hinweg fortgeschrieben. Die Splits stehen dabei, damit der Handelswert den letzten Preis umrechnen kann.
    splits = []
    try:
        from migrations.reference.stock_split_v1 import splits_for_fifo_v1
        splits = [row for row in splits_for_fifo_v1(space, context) if row['asset_ref'] == asset_id and row['account_ref'] is None]
    except Exception:  # noqa: BLE001 - ohne lesbaren Speicher wie ohne Split; der FIFO-Stand meldet den Fehler
        splits = []
    for row in splits:
        if start <= row['effective_local_date'] <= end:
            barriers[row['effective_local_date']] = 'trade_price_corporate_action_review'
    return {'source_kind': 'confirmed_trade_price_reference', 'quote_currency': asset['price_currency'],
            'rows': rows, 'barriers': barriers, 'events': events,
            **({'splits': [(row['effective_local_date'], row['ratio_numerator'], row['ratio_denominator']) for row in splits]} if splits else {}),
            'canonical_fingerprint': snapshot['source_fingerprint'],
            'activity_binding': binding, 'provider_access': False}
