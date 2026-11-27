"""Pure completed-evidence projection. No ledger, provider or publication access.

Identities are ordinals local to this revision, never names or canonical IDs.
The caller must supply the complete FIFO evidence for one portfolio from genesis
through the declared cutoff. A partial/unknown history is not an empty history.
"""
from fractions import Fraction
import hashlib
import json
from datetime import date


class SelectionSnapshotError(ValueError):
    pass


def _fail():
    raise SelectionSnapshotError('completed_asset_selection_evidence_invalid')


def _text(value):
    if not isinstance(value, str) or not value:
        _fail()
    return value


def _day(value):
    try:
        if date.fromisoformat(value).isoformat() != value:
            _fail()
    except (ValueError, TypeError):
        _fail()
    return value


def _quantity(value):
    import re
    if not isinstance(value, str) or re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?', value) is None or len(value) > 1000:
        _fail()
    return Fraction(value)


def _decimal(value):
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        _fail()
    scale = max(twos, fives)
    units = abs(value.numerator) * 2 ** (scale-twos) * 5 ** (scale-fives)
    digits = str(units).zfill(scale+1)
    text = digits if not scale else (digits[:-scale]+'.'+digits[-scale:]).rstrip('0').rstrip('.')
    return ('-' if value < 0 else '') + text


def project_completed_asset_selection_snapshot_v1(*, assets, accounts, events, history, terminal_positions,
        cutoff_date, source_fingerprint, complete_from_genesis):
    """Project complete non-cash evidence supplied by a completed-run producer.

    assets: full selected-portfolio catalog universe, including closed/unheld assets;
    accounts: full portfolio custody universe; events/history: FIFO tables.
    Input references are stripped. Simultaneous transfer legs are applied together.
    No floating-point arithmetic, sorting by dates, guessed opening or silent drops.
    """
    import re
    cutoff_date = _day(cutoff_date)
    if complete_from_genesis is not True or not isinstance(source_fingerprint, str) or re.fullmatch('[a-f0-9]{64}', source_fingerprint) is None:
        _fail()
    if not all(isinstance(rows, list) for rows in (assets, accounts, events, history, terminal_positions)):
        _fail()
    def index(rows, key):
        result = {}
        for row in rows:
            ref = _text(row[key])
            if ref in result:
                _fail()
            result[ref] = row
        return result
    try:
        asset_map = index(assets, 'asset_ref')
        account_map = index(accounts, 'account_ref')
        event_map = index(events, 'event_ref')
        asset_ordinals = {ref: n+1 for n, ref in enumerate(sorted(asset_map))}
        account_ordinals = {ref: n+1 for n, ref in enumerate(sorted(account_map))}
        public_assets = [dict(asset_ordinal=asset_ordinals[ref], asset_label=_text(row['asset_label']),
                              asset_type=_text(row['asset_type'])) for ref, row in sorted(asset_map.items())]
        public_accounts = [dict(account_ordinal=account_ordinals[ref], account_label=_text(row['account_label']))
                           for ref, row in sorted(account_map.items())]
        if any(row['asset_type'] == 'cash' for row in public_assets):
            _fail()
        grouped = {ref: [] for ref in event_map}
        sequence = 0
        event_order = {ref: n for n, ref in enumerate(event_map)}
        previous_event = -1
        for row in history:
            current = int(row['history_sequence'])
            if current != sequence+1:
                _fail()
            sequence = current
            event_index = event_order[row['event_ref']]
            if event_index < previous_event:
                _fail()
            previous_event = event_index
            grouped[row['event_ref']].append(row)
        holdings = {}
        public_events = []
        previous_day = None
        for ordinal, event in enumerate(events, 1):
            if int(event['event_sequence']) != ordinal:
                _fail()
            day = _day(event['local_date'])
            if day > cutoff_date or previous_day is not None and day < previous_day:
                _fail()
            previous_day = day
            asset = event['asset_ref']
            account = event['account_ref']
            related = event.get('related_account_ref') or None
            expected_accounts = {account} | ({related} if related is not None else set())
            if asset not in asset_map or not expected_accounts <= account_map.keys():
                _fail()
            before = sum((q for (a, _), q in holdings.items() if a == asset), Fraction())
            seen = set()
            changes = []
            for row in grouped[event['event_ref']]:
                custody = row['account_ref']
                if row['asset_ref'] != asset or custody not in expected_accounts or custody in seen:
                    _fail()
                if row.get('local_date', day) != day:
                    _fail()
                seen.add(custody)
                quantity = _quantity(row['position_quantity_decimal'])
                if quantity < 0:
                    _fail()
                holdings[(asset, custody)] = quantity
                changes.append(dict(account_ordinal=account_ordinals[custody], quantity_decimal=_decimal(quantity)))
            if seen != expected_accounts:
                _fail()
            after = sum((q for (a, _), q in holdings.items() if a == asset), Fraction())
            public_events.append(dict(event_ordinal=ordinal, asset_ordinal=asset_ordinals[asset],
                account_ordinals=sorted(account_ordinals[a] for a in expected_accounts), local_date=day,
                event_type=_text(event['event_type']), quantity_before_decimal=_decimal(before),
                quantity_after_decimal=_decimal(after), custody_changes=changes))
        terminal = {}
        for row in terminal_positions:
            key = (row['asset_ref'], row['account_ref'])
            if key in terminal or key[0] not in asset_map or key[1] not in account_map:
                _fail()
            terminal[key] = _quantity(row['remaining_quantity_decimal'])
        if {k: v for k, v in terminal.items() if v} != {k: v for k, v in holdings.items() if v}:
            _fail()
        positions = [dict(asset_ordinal=asset_ordinals[a], account_ordinal=account_ordinals[c], quantity_decimal=_decimal(q))
                     for (a, c), q in sorted(holdings.items())]
        identity_fingerprint = hashlib.sha256(json.dumps(
            {'assets': sorted(asset_map), 'accounts': sorted(account_map)},
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        body = dict(version=1, status='complete', scope='portfolio_noncash', coverage_from='genesis',
                    cutoff_date=cutoff_date, source_fingerprint=source_fingerprint,
                    identity_fingerprint=identity_fingerprint, assets=public_assets,
                    accounts=public_accounts, events=public_events, custody_positions=positions,
                    cash_supported=False, provider_access=False, calculation_started=False)
        body['revision_fingerprint'] = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        return body
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        if isinstance(exc, SelectionSnapshotError):
            raise
        _fail()
