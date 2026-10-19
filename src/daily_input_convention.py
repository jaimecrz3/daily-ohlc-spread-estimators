"""Step 10.2 source and boundary policies only; no spread estimator formulas.

Policies operate on existing acquired/normalized rows. They neither impute OHLC
nor turn observed adjustment-factor changes into verified corporate actions.
"""
from pathlib import Path
import re

import numpy as np
import pandas as pd

try:
    from .bloomberg_io import OHLC, verify_hashes, require_verified
except ImportError:
    from bloomberg_io import OHLC, verify_hashes, require_verified

ESTIMATORS = ('CS', 'AR', 'EDGE')
CONVENTIONS = {'primary': 'adjusted', 'robustness': 'unadjusted'}
ADJUSTMENTS = {
    'adjusted': {'CapChg': 'T', 'CshAdjNormal': 'T', 'CshAdjAbnormal': 'not_explicitly_set'},
    'unadjusted': {'CapChg': 'F', 'CshAdjNormal': 'F', 'CshAdjAbnormal': 'F'},
}


def common_source_plan(role='primary'):
    """Every future estimator uses the same acquired source within each role."""
    convention = CONVENTIONS[role]
    return {name: convention for name in ESTIMATORS}


def enforce_common_source(plan, role='primary'):
    if plan != common_source_plan(role):
        raise ValueError('All three estimators must use the common acquired convention')
    return CONVENTIONS[role]


def verified_source_selection(raw, role='primary'):
    """Hash-only resolution of immutable formula lineage and values-only input."""
    convention = enforce_common_source(common_source_plan(role), role)
    audit, manifest = verify_hashes(raw)
    require_verified(audit)
    base = '13-10-2026/bloomberg_daily_' + convention
    formula, values = base + '_raw.xlsx', base + '_raw_values.xlsx'
    hashes = manifest.set_index('file_name').sha256
    if not {formula, values}.issubset(hashes.index):
        raise ValueError('The exact finalized acquisition paths must be in the manifest')
    return dict(provider='Bloomberg', convention=convention, role=role,
        adjustment=ADJUSTMENTS[convention].copy(), formula_file=formula,
        values_file=values, formula_sha256=hashes[formula], values_sha256=hashes[values])


def corporate_action_boundaries(checks):
    """Reuse saved Step-8 flags, without scanning for or inventing new events.

Heuristic flags are diagnostic only. Primary adjusted inputs have no automatic
event breaks: a future break requires verification and a methodological reason.
Unadjusted robustness explicitly breaks saved verified split edges. The saved
SNDL evidence is not independently certified by this code.
"""
    rows = []
    for check in checks.to_dict('records'):
        kind = check['check_type']
        if kind == 'adjustment_factor_change_candidate':
            rows.append(dict(asset=check['asset'], date=pd.Timestamp(check['date']),
                verified_split=False, adjustment_factor_change_candidate=True,
                identity_status='unverified_adjustment_boundary_candidate',
                evidence=check['evidence']))
        elif kind == 'saved_notes_reverse_split_validation':
            match = re.search(r'reverse split (\d{4}-\d{2}-\d{2})', str(check['evidence']))
            if match is None:
                raise ValueError('Saved split check lacks an explicit event date')
            if check.get('check_passed') != True or check.get('all_ohlc_scaling_checks_passed') != True:
                raise ValueError('Saved split validation did not pass')
            rows.append(dict(asset=check['asset'], date=pd.Timestamp(match.group(1)),
                verified_split=True, adjustment_factor_change_candidate=False,
                identity_status='split_supported_by_saved_acquisition_notes',
                evidence=check['evidence']))
        else:
            raise ValueError('Unknown saved corporate-action check type: ' + str(kind))
    columns = ['asset', 'date', 'verified_split', 'adjustment_factor_change_candidate',
        'identity_status', 'evidence', 'primary_break_cross_date_window',
        'robustness_break_cross_date_window', 'break_cross_date_window']
    if not rows:
        return pd.DataFrame(columns=columns)
    frame = pd.DataFrame(rows)
    if frame.date.isna().any():
        raise ValueError('Boundary date cannot be missing')
    result = frame.groupby(['asset', 'date'], sort=True, as_index=False).agg(
        verified_split=('verified_split', 'max'),
        adjustment_factor_change_candidate=('adjustment_factor_change_candidate', 'max'),
        identity_status=('identity_status', lambda s: ';'.join(sorted(set(s)))),
        evidence=('evidence', lambda s: ';'.join(sorted(set(s)))))
    result['primary_break_cross_date_window'] = False
    result['robustness_break_cross_date_window'] = result.verified_split
    # Compatibility alias explicitly refers to primary, never to all diagnostics.
    result['break_cross_date_window'] = result.primary_break_cross_date_window
    return result[columns]


def annotate_input_rows(data, boundaries, role='primary'):
    """Preserve physical rows and price tokens; add future input metadata only.

No window, calendar grid or spread is constructed. OHLC eligibility is separate
from volume/quote eligibility and from the later analytical inclusion policy.
"""
    convention = CONVENTIONS[role]
    required = {'asset', 'date', 'source', 'convention', *OHLC}
    if not required.issubset(data.columns):
        raise ValueError('Missing source/date/OHLC columns')
    if not data.source.eq('Bloomberg').all() or not data.convention.eq(convention).all():
        raise ValueError('Input rows do not have the common Bloomberg convention')
    result = data.copy(deep=True)
    result['date'] = pd.to_datetime(result.date)
    order = ['asset', 'date'] + (['source_row'] if 'source_row' in result else [])
    result = result.sort_values(order, kind='stable', na_position='last').reset_index(drop=True)
    prices = result[OHLC].apply(pd.to_numeric, errors='coerce')
    finite = pd.DataFrame(np.isfinite(prices), index=result.index, columns=OHLC)
    result['input_partial_ohlc_row'] = ~finite.all(axis=1)
    duplicate = result.date.notna() & result.duplicated(['asset', 'date'], keep=False)
    date_valid = result.date.notna() & result.date.eq(result.date.dt.normalize()) & ~duplicate
    # Respect existing source flags instead of repairing annotated observations.
    for flag in ('duplicate_date', 'unassignable_date', 'date_has_time'):
        if flag in result:
            date_valid &= ~result[flag].fillna(True).astype(bool)
    hlc = ['PX_HIGH', 'PX_LOW', 'PX_LAST']
    hlc_valid = finite[hlc].all(axis=1) & prices[hlc].gt(0).all(axis=1)
    hlc_valid &= prices.PX_HIGH.ge(prices.PX_LOW)
    hlc_valid &= prices.PX_LAST.between(prices.PX_LOW, prices.PX_HIGH) & date_valid
    ohlc_valid = hlc_valid & finite.PX_OPEN & prices.PX_OPEN.gt(0)
    ohlc_valid &= prices.PX_OPEN.between(prices.PX_LOW, prices.PX_HIGH)
    # Field availability is not calendar adjacency or final window eligibility.
    result['CS_required_fields_available'] = hlc_valid
    result['AR_required_fields_available'] = hlc_valid
    result['EDGE_required_fields_available'] = ohlc_valid
    result['common_ohlc_fields_available'] = ohlc_valid  # descriptive, not a common gate
    result['zero_range_flag'] = prices.PX_HIGH.eq(prices.PX_LOW) & finite.all(axis=1)
    result['input_convention_role'] = role
    result['input_adjustment_label'] = ('capital_and_normal_cash_dividend_adjusted; abnormal_setting_unspecified'
        if convention == 'adjusted' else 'capital_and_all_cash_dividend_unadjusted')
    # An event can fall on a missing/source-only date: never bridge it silently.
    result['corporate_action_boundary_before'] = False
    for asset, group in result.groupby('asset', sort=False):
        break_field = role + '_break_cross_date_window'
        events = boundaries.loc[boundaries.asset.eq(asset) & boundaries[break_field], 'date']
        dates = group.date
        previous = dates.shift()
        flags = [bool(((events > prior) & (events <= day)).any()) if pd.notna(prior) and pd.notna(day)
            else bool(events.eq(day).any()) if pd.notna(day) else False
            for prior, day in zip(previous, dates)]
        result.loc[group.index, 'corporate_action_boundary_before'] = flags
    return result
