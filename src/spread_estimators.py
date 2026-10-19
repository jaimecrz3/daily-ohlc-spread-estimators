"""Common CS, AR and EDGE mathematical kernels. No provider I/O or panel runner.

CS follows Corwin's official SAS equations; AR follows Abdi--Ranaldo (9), (11).
EDGE follows the author pseudocode (MIT, eguidotti/bidask), with the published
JFE Section 3.2 zero floor as PRIMARY and absolute root as diagnostic robustness.
EDGE adaptation: Copyright (c) 2024 Emanuele Guidotti. MIT license and full notice
are retained in outputs/diagnostics/estimator_freeze/sources/EDGE_LICENSE.txt.
Source versions, attribution and hashes: outputs/diagnostics/estimator_freeze/sources/.
"""
import warnings

import numpy as np

FAILURE_REASONS = (
    'missing_required_field', 'non_finite_price', 'non_positive_price',
    'invalid_ohlc_order', 'zero_range_not_admissible', 'incomplete_estimator_window',
    'invalid_scheduled_adjacency', 'missing_previous_scheduled_period',
    'missing_next_scheduled_period', 'missing_target_scheduled_period',
    'insufficient_edge_observations', 'insufficient_edge_tau', 'zero_edge_po',
    'zero_edge_pc', 'non_finite_intermediate', 'non_finite_estimate')


def result(estimator, n, reason='', diagnostics=None, *, moment=np.nan,
           signed=np.nan, primary=np.nan):
    raw_computable = bool(np.isfinite(moment) and np.isfinite(signed))
    defined = bool(not reason and raw_computable and np.isfinite(primary) and np.isfinite(primary * 10000))
    if not reason and not defined:
        reason = 'non_finite_estimate'
    return dict(asset='', target_date=None, estimator=estimator,
        raw_moment=float(moment), raw_signed_spread_relative=float(signed),
        raw_negative=bool(signed < 0) if raw_computable else None,
        raw_computable=raw_computable,
        primary_spread_relative=float(primary) if defined else np.nan,
        primary_spread_bps=float(primary * 10000) if defined else np.nan,
        estimator_defined=defined, failure_reason=reason, input_dates=[],
        input_observations=n,
        window_complete=bool((diagnostics or {}).get('input_complete', reason not in (
            'missing_required_field', 'non_finite_price', 'incomplete_estimator_window', 'insufficient_edge_observations'))),
        scheduled_adjacency_valid=None,
        method_specific_diagnostics=diagnostics or {})


def vectors(*values):
    arrays = [np.asarray(value, dtype=float) for value in values]
    if any(value.ndim != 1 for value in arrays) or len({len(value) for value in arrays}) != 1:
        raise ValueError('Equal-length one-dimensional price arrays required')
    return arrays


def price_failure(*arrays, allow_missing=False):
    values = np.concatenate([np.asarray(a, dtype=float).reshape(-1) for a in arrays])
    if np.isinf(values).any(): return 'non_finite_price'
    if np.isnan(values).any() and not allow_missing: return 'missing_required_field'
    if (values[np.isfinite(values)] <= 0).any(): return 'non_positive_price'
    return ''


def cs_interval(high, low, previous_close):
    """One interval (a,b): raw H/L at a; H/L at b shifted using close at a.

    No forward-filled range, CRSP absolute-close conversion, H/L>8 screen or
    other empirical SAS preprocessing: forbidden by the frozen common policy.
    Zero ranges fail the official good-range prerequisite rather than being reset.
    """
    h, l = vectors(high, low)
    if len(h) != 2: return result('CS_INTERVAL', len(h), 'incomplete_estimator_window')
    reason = price_failure(h, l, [previous_close])
    if reason: return result('CS_INTERVAL', 2, reason)
    if (h < l).any() or not l[0] <= previous_close <= h[0]:
        return result('CS_INTERVAL', 2, 'invalid_ohlc_order')
    if (h == l).any(): return result('CS_INTERVAL', 2, 'zero_range_not_admissible')
    th, tl, adjustment = h[1], l[1], 'none'
    if previous_close < l[1]:
        th, tl, adjustment = h[1] - (l[1] - previous_close), previous_close, 'prior_close_below_low'
    elif previous_close > h[1]:
        th, tl, adjustment = previous_close, l[1] + (previous_close - h[1]), 'prior_close_above_high'
    diagnostic = dict(adjusted_high=float(th), adjusted_low=float(tl),
                      overnight_adjustment=adjustment, previous_close=float(previous_close))
    if not np.isfinite([th, tl]).all() or tl <= 0 or th < tl:
        return result('CS_INTERVAL', 2, 'non_finite_intermediate', diagnostic)
    # Differences of logs avoid overflowing a price ratio; algebraically identical.
    beta = (np.log(th) - np.log(tl))**2 + (np.log(h[0]) - np.log(l[0]))**2
    gamma = (np.log(max(th, h[0])) - np.log(min(tl, l[0])))**2
    k = 3 - 2 * np.sqrt(2.)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)
    # Exact stable identity for 2*(exp(alpha)-1)/(1+exp(alpha)).
    spread = 2 * np.tanh(alpha / 2)
    diagnostic.update(beta=float(beta), gamma=float(gamma), alpha=float(alpha),
                      cs_interval_raw=float(spread), cs_interval_negative=bool(spread < 0))
    return result('CS_INTERVAL', 2, diagnostics=diagnostic, moment=alpha,
                  signed=spread, primary=max(spread, 0.))


def cs_daily(high, low, close):
    """Project dailyization: both overlapping intervals on (t-1,t,t+1).

    Only C_(t-1), C_t are needed. C_(t+1) and all opens are not formula inputs.
    """
    h, l, c = vectors(high, low, close)
    if len(h) != 3: return result('CS', len(h), 'incomplete_estimator_window')
    left = cs_interval(h[:2], l[:2], c[0])
    right = cs_interval(h[1:], l[1:], c[1])
    diagnostic = dict(left=left, right=right,
        negative_component_intervals=sum(r['raw_negative'] is True for r in [left, right]),
        raw_moment_definition='Mean component alpha; diagnostic only, not transformed to daily spread')
    if not (left['estimator_defined'] and right['estimator_defined']):
        reason = left['failure_reason'] or right['failure_reason']
        return result('CS', 3, reason, diagnostic)
    return result('CS', 3, diagnostics=diagnostic,
        moment=(left['raw_moment'] + right['raw_moment']) / 2,
        signed=(left['raw_signed_spread_relative'] + right['raw_signed_spread_relative']) / 2,
        primary=(left['primary_spread_relative'] + right['primary_spread_relative']) / 2)


def ar_two_day(high, low, target_close):
    """Target t uses H/L at t,t+1 and only C_t; no overnight adjustment/imputation.

    A zero range is mathematically admissible in Eq.(9). Do not copy empirical
    carry-forward preprocessing or impose a CS-style range screen on AR.
    """
    h, l = vectors(high, low)
    if len(h) != 2: return result('AR', len(h), 'incomplete_estimator_window')
    reason = price_failure(h, l, [target_close])
    if reason: return result('AR', 2, reason)
    if (h < l).any() or not l[0] <= target_close <= h[0]:
        return result('AR', 2, 'invalid_ohlc_order')
    eta = (np.log(h) + np.log(l)) / 2
    c = np.log(target_close)
    s2 = 4 * (c - eta[0]) * (c - eta[1])
    return result('AR', 2, diagnostics=dict(eta=eta.tolist(), log_target_close=float(c), ar_s2_raw=float(s2)),
        moment=s2, signed=np.sign(s2) * np.sqrt(abs(s2)), primary=np.sqrt(max(s2, 0.)))


def edge_moments(open_, high, low, close):
    """Author pseudocode, nan-aware regular grid retained, full intermediates.

    Missing NaNs are preserved in place. Invalid observed prices/order fail rather
    than being converted to missing or repaired. Official nanmeans and population
    moment variances are used. The first observation supplies only lagged inputs.
    """
    op, hi, lo, cl = vectors(open_, high, low, close)
    n = len(op)
    if n < 3: return result('EDGE', n, 'insufficient_edge_observations')
    reason = price_failure(op, hi, lo, cl, allow_missing=True)
    if reason: return result('EDGE', n, reason)
    if ((hi < lo) | (op < lo) | (op > hi) | (cl < lo) | (cl > hi)).any():
        return result('EDGE', n, 'invalid_ohlc_order')
    with warnings.catch_warnings(), np.errstate(all='ignore'):
        warnings.simplefilter('ignore', RuntimeWarning)
        o0, h0, l0, c0 = [np.log(a) for a in [op, hi, lo, cl]]
        m0 = (h0 + l0) / 2
        h1, l1, c1, m1 = h0[:-1], l0[:-1], c0[:-1], m0[:-1]
        o, h, l, c, m = [a[1:] for a in [o0, h0, l0, c0, m0]]
        r1, r2, r3, r4, r5 = m-o, o-m1, m-c1, c1-m1, o-c1
        tau = np.where(np.isnan(h) | np.isnan(l) | np.isnan(c1), np.nan, (h != l) | (l != c1))
        po1 = tau * np.where(np.isnan(o) | np.isnan(h), np.nan, o != h)
        po2 = tau * np.where(np.isnan(o) | np.isnan(l), np.nan, o != l)
        pc1 = tau * np.where(np.isnan(c1) | np.isnan(h1), np.nan, c1 != h1)
        pc2 = tau * np.where(np.isnan(c1) | np.isnan(l1), np.nan, c1 != l1)
        pt = np.nanmean(tau)
        po, pc = np.nanmean(po1)+np.nanmean(po2), np.nanmean(pc1)+np.nanmean(pc2)
        diagnostic = {key: value.tolist() for key, value in dict(log_open=o0, log_high=h0,
            log_low=l0, log_close=c0, m=m0, r1=r1, r2=r2, r3=r3, r4=r4, r5=r5,
            tau=tau, po1=po1, po2=po2, pc1=pc1, pc2=pc2).items()}
        diagnostic.update(pt=float(pt), po=float(po), pc=float(pc), tau_observations=int(np.nansum(tau)),
                          input_complete=bool(np.isfinite(np.column_stack([op, hi, lo, cl])).all()))
        if np.nansum(tau) < 2: return result('EDGE', n, 'insufficient_edge_tau', diagnostic)
        if po == 0: return result('EDGE', n, 'zero_edge_po', diagnostic)
        if pc == 0: return result('EDGE', n, 'zero_edge_pc', diagnostic)
        if not np.isfinite([pt, po, pc]).all():
            return result('EDGE', n, 'non_finite_intermediate', diagnostic)
        d1 = r1 - np.nanmean(r1)/pt*tau
        d3 = r3 - np.nanmean(r3)/pt*tau
        d5 = r5 - np.nanmean(r5)/pt*tau
        x1 = -4/po*d1*r2 - 4/pc*d3*r4
        x2 = -4/po*d1*r5 - 4/pc*d5*r4
        e1, e2 = np.nanmean(x1), np.nanmean(x2)
        v1, v2 = np.nanmean(x1*x1)-e1*e1, np.nanmean(x2*x2)-e2*e2
        vt = v1 + v2
        s2 = (v2*e1 + v1*e2)/vt if vt > 0 else (e1+e2)/2
    for key, value in dict(d1=d1, d3=d3, d5=d5, x1=x1, x2=x2).items():
        diagnostic[key] = value.tolist()
    diagnostic.update(e1=float(e1), e2=float(e2), v1=float(v1), v2=float(v2), vt=float(vt),
        variance_fallback=bool(vt <= 0), s2=float(s2), edge_s2_raw=float(s2))
    if not np.isfinite([e1, e2, v1, v2, vt]).all():
        return result('EDGE', n, 'non_finite_intermediate', diagnostic)
    if not np.isfinite(s2): return result('EDGE', n, 'non_finite_estimate', diagnostic)
    diagnostic['edge_abs_root_robustness'] = float(np.sqrt(abs(s2)))
    output = result('EDGE', n, diagnostics=diagnostic, moment=s2,
        signed=np.sign(s2)*np.sqrt(abs(s2)), primary=np.sqrt(max(s2, 0.)))
    output['window_complete'] = bool(np.isfinite(np.column_stack([op, hi, lo, cl])).all())
    return output
