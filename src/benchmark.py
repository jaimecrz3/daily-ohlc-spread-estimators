"""Roll-style relative spread from one-minute simple returns, by asset-day.

This is the project's specified return-based adaptation of Roll (1984), whose
original spread formula uses price changes. Sample covariance centers the two
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
               'non_finite_rows', 'negative_volume_rows']


def flag(data: pd.DataFrame, name: str) -> pd.Series:
    """Absent optional parser flags mean false; supplied flags are preserved."""
    return data[name].fillna(False).astype(bool) if name in data else pd.Series(False, index=data.index)


def build_roll_benchmark(data: pd.DataFrame, asset: str, asset_class: str,
                         *, return_bar_audit: bool = False, futures_root: str | None = None):
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
    """
    annotated = assign_primary_session(data, asset_class, futures_root=futures_root).reset_index(names='source_row')
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
    eligible = (np.isfinite(close) & close.gt(0) & local.notna()
                & ~annotated.duplicate_timestamp & ~flag(annotated, 'malformed_columns')
                & ~flag(annotated, 'invalid_ohlc'))
    annotated['benchmark_close_eligible'] = annotated.primary_session_retained & eligible
    annotated['one_minute_return'] = np.nan
    annotated['roll_pair_valid'] = False
    annotated['gap_minutes'] = np.nan
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
        returns = returns.where(np.isfinite(returns))
        pairs = returns.notna() & returns.shift().notna() & gap.eq(1)
        n = int(pairs.sum())
        gamma, spread = np.nan, np.nan
        reason = 'insufficient_roll_pairs'
        defined = False
        if n >= 2:
            x = returns.loc[pairs].to_numpy()
            y = returns.shift().loc[pairs].to_numpy()
            with np.errstate(over='ignore', invalid='ignore'):
                gamma = float(np.dot(x - x.mean(), y - y.mean()) / (n - 1))
            if not np.isfinite(gamma):
                reason = 'non_finite_autocovariance'
            elif gamma < 0:
                spread = float(2 * np.sqrt(-gamma))
                defined, reason = True, ''
            else:
                reason = 'non_negative_autocovariance'
        summaries.append(dict(asset=asset, asset_class=asset_class, date=day,
            timezone=asset_metadata(asset_class)['timezone'], bars_observed=len(group),
            one_minute_returns=int(returns.notna().sum()), roll_pairs=n,
            max_gap_minutes=gap.max(), zero_volume_rows=int(group.zero_volume.sum()),
            roll_autocovariance=gamma, roll_spread_relative=spread,
            roll_spread_bps=10000 * spread, roll_defined=defined,
            benchmark_failure_reason=reason, valid_close_bars=int(good.sum()),
            ineligible_close_rows=int((~good).sum()),
            **{name + '_rows': int(flag(group, name).sum()) for name in
               ['duplicate_timestamp', 'timezone_assignment_failed', 'malformed_columns',
                'invalid_ohlc', 'missing_value', 'non_numeric', 'non_finite', 'negative_volume']}))
        annotated.loc[group.index, 'one_minute_return'] = returns
        annotated.loc[group.index, 'roll_pair_valid'] = pairs
        annotated.loc[group.index, 'gap_minutes'] = gap
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
