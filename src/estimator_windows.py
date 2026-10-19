"""Scheduled-source-period alignment, separate from pure estimator mathematics.

No provider price reads. Metadata loaders read only previously frozen date grids.
NaN placeholders are an analysis view, never synthesized provider OHLC rows.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd

from bloomberg_io import sha256
from spread_estimators import result, cs_daily, ar_two_day, edge_moments

PROJECT = Path(__file__).resolve().parents[1]
DESIGN = PROJECT / 'outputs/diagnostics/design_freeze'


def checked_grid(grid):
    dates = pd.DatetimeIndex(pd.to_datetime(list(grid), errors='raise'))
    if dates.tz is not None or dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing or not dates.equals(dates.normalize()):
        raise ValueError('Unique sorted timezone-naive scheduled daily labels required')
    return dates


def load_reference_grid(asset_class):
    """Frozen pre-intersection stock/ETF union; frozen futures dates; daily UTC.

    Does not read any prices or outcomes. Metadata file hashes must match Step14.
    """
    asset_class = 'crypto' if asset_class == 'cryptos' else asset_class
    if asset_class == 'crypto':
        return pd.date_range('2015-01-01', '2025-12-31', freq='D')
    if asset_class in ('stocks', 'etfs'):
        name = 'source_calendar_date_audit.csv'
    elif asset_class == 'futures':
        name = 'futures_primary_calendar.csv'
    else:
        raise ValueError('No verified source grid for this class; FX blocked')
    manifest = json.loads((DESIGN / 'run_manifest.json').read_text(encoding='utf-8'))
    path = DESIGN / name
    if sha256(path) != manifest['output_sha256'][name]:
        raise ValueError('Frozen reference-grid artifact changed')
    if asset_class in ('stocks', 'etfs'):
        data = pd.read_csv(path, usecols=['asset_class', 'date'])
        days = data.loc[data.asset_class.eq(asset_class), 'date']
    else:
        days = pd.read_csv(path, usecols=['date']).date
    return checked_grid(days)


def daily_estimate(data, asset, target_date, estimator, reference_grid):
    """Evaluate one explicitly supplied asset-day, with no I/O or panel execution.

    CS/EDGE use t-1,t,t+1; AR uses t,t+1. Input date neighbors come from the
    reference grid, never from successful rows or the primary intersection.
    """
    if estimator not in ('CS', 'AR', 'EDGE'): raise ValueError('Unknown estimator')
    grid = checked_grid(reference_grid)
    target = pd.Timestamp(target_date)
    if target.tz is not None or target != target.normalize():
        raise ValueError('Target must be a daily label')
    rows = data.copy(deep=True)
    if 'asset' in rows: rows = rows.loc[rows.asset.eq(asset)].copy()
    rows['date'] = pd.to_datetime(rows.date, errors='raise')
    if rows.date.isna().any() or rows.date.duplicated().any() or rows.date.ne(rows.date.dt.normalize()).any():
        raise ValueError('Missing, duplicate or intraday source date')
    aliases = {'PX_OPEN': 'open', 'PX_HIGH': 'high', 'PX_LOW': 'low', 'PX_LAST': 'close'}
    for source, destination in aliases.items():
        if source in rows:
            if destination in rows: raise ValueError('Ambiguous source field aliases')
            rows = rows.rename(columns={source: destination})
    for column in ['open', 'high', 'low', 'close']:
        if column not in rows: rows[column] = np.nan
        # Numeric source normalization is upstream; do not hide a bad raw token.
        rows[column] = pd.to_numeric(rows[column], errors='raise')
    offsets = [0, 1] if estimator == 'AR' else [-1, 0, 1]
    location = grid.get_indexer([target])[0]
    dates = [grid[location+offset] if location >= 0 and 0 <= location+offset < len(grid) else None for offset in offsets]
    if location < 0: dates = [None for _ in offsets]
    indexed = rows.set_index('date')
    present = [day is not None and day in indexed.index for day in dates]
    # Reindex only this explicit scheduled window; no prices/days are imputed.
    view = indexed.reindex(pd.DatetimeIndex([day if day is not None else pd.NaT for day in dates]))
    price = view[['open', 'high', 'low', 'close']].to_numpy(dtype=float)
    required = np.zeros_like(price, dtype=bool)
    if estimator == 'EDGE': required[:] = True
    else:
        required[:, 1:3] = True
        required[:2 if estimator == 'CS' else 1, 3] = True
    complete = bool(all(present) and np.isfinite(price[required]).all())
    problems = []
    for offset, exists in zip(offsets, present):
        if not exists:
            problems.append('missing_previous_scheduled_period' if offset < 0 else
                'missing_next_scheduled_period' if offset > 0 else 'missing_target_scheduled_period')
    if problems:
        output = result(estimator, sum(present), problems[0], dict(adjacency_failure_reasons=problems,
            window_failure='incomplete_estimator_window', scheduled_grid_not_compressed=True))
    elif estimator == 'CS':
        output = cs_daily(price[:, 1], price[:, 2], price[:, 3])
    elif estimator == 'AR':
        output = ar_two_day(price[:, 1], price[:, 2], price[0, 3])
    elif np.isnan(price).any():
        # The project daily minimum window requires its three OHLC observations.
        # General EDGE kernel still preserves nan-aware official replication.
        output = result('EDGE', sum(present), 'missing_required_field',
            dict(regular_grid_prices=price.tolist(), scheduled_grid_not_compressed=True))
    else:
        output = edge_moments(*price.T)
    output.update(asset=asset, target_date=target.date().isoformat(),
        input_dates=[day.date().isoformat() if day is not None else None for day in dates],
        input_observations=sum(present), window_complete=complete,
        scheduled_adjacency_valid=bool(not problems))
    return output
