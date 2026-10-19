"""Roll-style relative spread from one-minute simple returns, by asset-day.

Roll (1984), Section II and footnote 5 (p. 1130), supports arithmetic percentage
returns for an approximate percentage spread. The price-change form is the
original derivation; this is its supported percentage-return form/adaptation.
Sample covariance centers the two
paired-return vectors separately and divides by n_pairs - 1 (ddof=1).
No coverage threshold, clipping, missing-minute filling or raw-data mutation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from .data_io import asset_metadata
    from .session_rules import assign_primary_session
except ImportError:
    from data_io import asset_metadata
    from session_rules import assign_primary_session


DAY_COLUMNS = ['asset', 'asset_class', 'date', 'timezone', 'bars_observed',
               'one_minute_returns', 'roll_pairs', 'max_gap_minutes',
               'zero_volume_rows', 'roll_autocovariance', 'roll_spread_relative',
               'roll_spread_bps', 'roll_defined', 'benchmark_failure_reason',
               'valid_close_bars', 'ineligible_close_rows', 'duplicate_timestamp_rows',
               'timezone_assignment_failed_rows', 'malformed_columns_rows',
               'invalid_ohlc_rows', 'missing_value_rows', 'non_numeric_rows',
               'non_finite_rows', 'negative_volume_rows', 'gaps_gt_one_minute',
               'benchmark_defined', 'failure_reason', 'benchmark_mode',
               'benchmark_role', 'invalid_price_rows', 'invalid_return_rows',
               'max_consecutive_valid_returns', 'benchmark_diagnostic_flags',
               'insufficient_minute_bars', 'insufficient_consecutive_returns',
               'insufficient_covariance_pairs', 'invalid_price', 'invalid_return',
               'source_quality_condition', 'non_negative_autocovariance',
               'non_finite_autocovariance']
MIN_ROLL_PAIRS = 2
COVARIANCE_DDOF = 1
PRIMARY_MODE = 'exact_one_minute'
SENSITIVITY_MODE = 'successive_observed_bars'


def flag(data: pd.DataFrame, name: str) -> pd.Series:
    """Absent optional parser flags mean false; supplied flags are preserved."""
    return data[name].fillna(False).astype(bool) if name in data else pd.Series(False, index=data.index)


def build_roll_benchmark(data: pd.DataFrame, asset: str, asset_class: str,
                         *, return_bar_audit: bool = False, futures_root: str | None = None,
                         futures_sessions=None,
                         return_mode: str = PRIMARY_MODE):
    """Summarize observed frozen-session days; optionally return all bar flags.

    Input must have timestamp (parsed datetime), close and volume. Assign sessions
    afresh rather than trusting stale caller annotations. Original rows and flags
    remain in the audit; session and close eligibility are separate decisions.
    Finite positive closes are eligible unless malformed/invalid OHLC, unresolved
    timezone, or duplicate timestamp. All copies of a duplicate are ineligible;
    no arbitrary duplicate selection is made. Missing/invalid non-price fields
    and zero volume are diagnostic flags, not automatic close exclusions.

    Returns are computed on the full sorted session observations, then masked.
    Invalid observations break the return chain; filtering them cannot bridge
    a gap. Days with zero eligible pairs remain present. No synthetic dates are
    generated for days without any recorded session bars.

    failure_reason is the detailed Step-10 primary reason. The old
    benchmark_failure_reason retains insufficient_roll_pairs for compatibility;
    it is not a competing numeric or failure-handling convention. Diagnostic
    boolean flags can coexist and are not automatic whole-day exclusions.
    """
    if return_mode == SENSITIVITY_MODE:
        raise NotImplementedError('successive_observed_bars is a prepared robustness/sensitivity design, not an executable primary benchmark')
    if return_mode != PRIMARY_MODE:
        raise ValueError(f'Unknown benchmark return mode: {return_mode}')
    annotated = assign_primary_session(data, asset_class, futures_root=futures_root,
                                       futures_sessions=futures_sessions).reset_index(names='source_row')
    if asset_class == 'futures':
        if 'selected_contract' not in annotated:
            raise ValueError('Futures benchmark requires selected_contract provenance')
        session_rows = annotated.loc[annotated.primary_session_retained]
        if session_rows.selected_contract.isna().any() or session_rows.groupby('session_day').selected_contract.nunique().gt(1).any():
            raise ValueError('Futures benchmark requires exactly one contract per trade date')
        if 'source_contract' in session_rows and session_rows.source_contract.ne(session_rows.selected_contract).any():
            raise ValueError('Selected futures contract does not match source provenance')
    annotated['asset'] = asset
    annotated['asset_class'] = asset_class
    local = annotated.timestamp_local
    duplicate = local.notna() & local.duplicated(keep=False)
    annotated['duplicate_timestamp'] = duplicate | flag(annotated, 'duplicate_timestamp')
    close = pd.to_numeric(annotated.close, errors='coerce')
    annotated['invalid_price'] = ~np.isfinite(close) | close.le(0)
    eligible = (np.isfinite(close) & close.gt(0) & local.notna()
                & ~annotated.duplicate_timestamp & ~flag(annotated, 'malformed_columns')
                & ~flag(annotated, 'invalid_ohlc'))
    annotated['benchmark_close_eligible'] = annotated.primary_session_retained & eligible
    annotated['one_minute_return'] = np.nan
    annotated['roll_pair_valid'] = False
    annotated['gap_minutes'] = np.nan
    annotated['invalid_return'] = False
    summaries = []
    session = annotated.loc[annotated.primary_session_retained]
    for day, group in session.groupby('session_day', sort=True):
        group = group.sort_values('timestamp_local', kind='stable')
        gap = group.timestamp_local.diff().dt.total_seconds() / 60
        good = group.benchmark_close_eligible
        prices = pd.to_numeric(group.close, errors='coerce')
        with np.errstate(over='ignore', divide='ignore', invalid='ignore'):
            returns = (prices / prices.shift() - 1).where(
                gap.eq(1) & good & good.shift(fill_value=False))
        computable = gap.eq(1) & good & good.shift(fill_value=False)
        bad_return = computable & (~np.isfinite(returns) | returns.le(-1))
        # Positive closes mathematically imply r > -1. Overflow, ratio
        # underflow or rounding to the -1 boundary is flagged, never clipped.
        returns = returns.where(~bad_return)
        pairs = returns.notna() & returns.shift().notna() & gap.eq(1)
        n = int(pairs.sum())
        gamma, spread = np.nan, np.nan
        reason = 'insufficient_roll_pairs'
        defined = False
        if n >= MIN_ROLL_PAIRS:
            x = returns.loc[pairs].to_numpy()
            y = returns.shift().loc[pairs].to_numpy()
            with np.errstate(over='ignore', invalid='ignore'):
                gamma = float(np.dot(x - x.mean(), y - y.mean()) / (n - COVARIANCE_DDOF))
            if not np.isfinite(gamma):
                reason = 'non_finite_autocovariance'
            elif gamma < 0:
                spread = float(2 * np.sqrt(-gamma))
                defined, reason = True, ''
            else:
                reason = 'non_negative_autocovariance'
        run, longest = 0, 0
        for valid in returns.notna():
            run = run + 1 if valid else 0
            longest = max(longest, run)
        source_issue = any(flag(group, name).any() for name in
            ['duplicate_timestamp', 'timezone_assignment_failed', 'malformed_columns', 'invalid_ohlc'])
        diagnostics = dict(insufficient_minute_bars=len(group) < 3,
            insufficient_consecutive_returns=longest < 2,
            insufficient_covariance_pairs=n < MIN_ROLL_PAIRS,
            invalid_price=bool(group.invalid_price.any()), invalid_return=bool(bad_return.any()),
            source_quality_condition=bool(source_issue),
            non_negative_autocovariance=bool(np.isfinite(gamma) and gamma >= 0),
            non_finite_autocovariance=bool(n >= MIN_ROLL_PAIRS and not np.isfinite(gamma)))
        detail = ''
        if not defined:
            # Shortages are descriptive; source causes take precedence once
            # a structural three-bar lag-pair opportunity exists.
            precedence = (['non_finite_autocovariance', 'non_negative_autocovariance']
                          if n >= MIN_ROLL_PAIRS else
                          ['insufficient_minute_bars', 'invalid_price', 'invalid_return',
                           'source_quality_condition', 'insufficient_consecutive_returns',
                           'insufficient_covariance_pairs'])
            detail = next(name for name in precedence if diagnostics[name])
        summaries.append(dict(asset=asset, asset_class=asset_class, date=day,
            timezone=asset_metadata(asset_class)['timezone'], bars_observed=len(group),
            one_minute_returns=int(returns.notna().sum()), roll_pairs=n,
            max_gap_minutes=gap.max(), zero_volume_rows=int(group.zero_volume.sum()),
            roll_autocovariance=gamma, roll_spread_relative=spread,
            roll_spread_bps=10000 * spread, roll_defined=defined,
            benchmark_failure_reason=reason, valid_close_bars=int(good.sum()),
            ineligible_close_rows=int((~good).sum()),
            gaps_gt_one_minute=int(gap.gt(1).sum()), benchmark_defined=defined,
            failure_reason=detail, benchmark_mode=PRIMARY_MODE, benchmark_role='primary_candidate',
            invalid_price_rows=int(group.invalid_price.sum()), invalid_return_rows=int(bad_return.sum()),
            max_consecutive_valid_returns=longest,
            benchmark_diagnostic_flags=';'.join(name for name, active in diagnostics.items() if active),
            **diagnostics,
            **{name + '_rows': int(flag(group, name).sum()) for name in
               ['duplicate_timestamp', 'timezone_assignment_failed', 'malformed_columns',
                'invalid_ohlc', 'missing_value', 'non_numeric', 'non_finite', 'negative_volume']}))
        annotated.loc[group.index, 'one_minute_return'] = returns
        annotated.loc[group.index, 'roll_pair_valid'] = pairs
        annotated.loc[group.index, 'gap_minutes'] = gap
        annotated.loc[group.index, 'invalid_return'] = bad_return
    daily = pd.DataFrame(summaries, columns=DAY_COLUMNS)
    return (daily, annotated) if return_bar_audit else daily


def summarize_roll_benchmark(daily: pd.DataFrame) -> pd.DataFrame:
    """Validation counts only; undefined days remain in all pair summaries."""
    records = []
    for (asset, cls), days in daily.groupby(['asset', 'asset_class'], sort=False):
        defined = days.roll_defined
        records.append(dict(asset=asset, asset_class=cls, asset_days=len(days),
            defined_roll_benchmark_days=int(defined.sum()), undefined_days=int((~defined).sum()),
            median_roll_pairs=days.roll_pairs.median(), min_roll_pairs=days.roll_pairs.min(),
            max_roll_pairs=days.roll_pairs.max(),
            median_roll_spread_bps=days.loc[defined, 'roll_spread_bps'].median()))
    return pd.DataFrame(records)
