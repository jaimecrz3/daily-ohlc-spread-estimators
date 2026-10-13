"""Frozen primary sessions. No calendar exclusions, filling or quality cleaning.

Naive timestamps are provider wall clocks. DST ambiguity/nonexistence is flagged,
never inferred from ordering. Equity inclusion uses the documented wall clock;
an unresolved UTC instant does not delete a raw row. ES/CL pilot sessions are
18:00 previous day to 17:00 ending trade date; other futures roots stay pending.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Mapping

import pandas as pd

try:
    from .data_io import asset_metadata
except ImportError:
    from data_io import asset_metadata


@dataclass(frozen=True)
class FuturesSessionConfig:
    """Root-specific interface; ES/CL pilot configured, other roots pending.

    Breaks, overnight boundaries, holidays and trading-day labels must be frozen
    before implementing futures assignment. No fallback session is provided.
    """
    root: str
    timezone: str = 'America/New_York'
    start: time | None = None
    end: time | None = None
    trading_day_convention: str | None = None


FUTURES_SESSIONS: dict[str, FuturesSessionConfig] = {
    root: FuturesSessionConfig(root, start=time(18), end=time(17),
                               trading_day_convention='overnight_ending_date')
    for root in ('ES', 'CL')
}


def assign_primary_session(data: pd.DataFrame, asset_class: str, *,
                           futures_root: str | None = None,
                           futures_sessions: Mapping[str, FuturesSessionConfig] | None = None) -> pd.DataFrame:
    """Annotate every input row, preserving order, index, values and flags.

    session_day is an equity local date, crypto UTC date, or futures trade date.
    It is null outside the session. Timestamp localization is a separate column.
    No exchange holiday/early-close policy is implied by the frozen clock rule.
    """
    timezone = asset_metadata(asset_class)['timezone']
    if asset_class == 'futures':
        configs = FUTURES_SESSIONS if futures_sessions is None else futures_sessions
        config = configs.get(futures_root)
        if (config is None or config.root != futures_root or config.start != time(18)
                or config.end != time(17) or config.timezone != timezone
                or config.trading_day_convention != 'overnight_ending_date'):
            raise NotImplementedError(f'Futures session pending for root {futures_root!r}; config={config!r}')
    result = data.copy()
    ts = result['timestamp']
    if not pd.api.types.is_datetime64_any_dtype(ts.dtype):
        raise TypeError('timestamp must be a parsed pandas datetime column')
    if ts.dt.tz is None:
        local = ts.dt.tz_localize(timezone, ambiguous='NaT', nonexistent='NaT')
        wall = ts
    else:
        local = ts.dt.tz_convert(timezone)
        wall = local.dt.tz_localize(None)
    result['timestamp_local'] = local
    result['timezone_assignment_failed'] = ts.notna() & local.isna()
    result['unassignable_timestamp'] = ts.isna()
    seconds = wall.dt.hour * 3600 + wall.dt.minute * 60 + wall.dt.second
    if asset_class == 'futures':
        maintenance = wall.notna() & seconds.ge(17 * 3600) & seconds.lt(18 * 3600)
        retained = wall.notna() & local.notna() & ~maintenance
        day_clock = wall.dt.normalize() + pd.to_timedelta(seconds.ge(18 * 3600).astype(int), unit='D')
        result['trade_date'] = day_clock.dt.date.where(retained)
        result['maintenance_interval'] = maintenance
        result['outside_primary_futures_session'] = ~retained
        result['futures_root'] = futures_root
    else:
        retained = (wall.notna() if asset_class == 'cryptos'
                    else wall.notna() & seconds.ge(9 * 3600 + 30 * 60) & seconds.lt(16 * 3600))
    result['primary_session_retained'] = retained
    result['session_day'] = result['trade_date'] if asset_class == 'futures' else wall.dt.date.where(retained)
    result['zero_volume'] = pd.to_numeric(result['volume'], errors='coerce').eq(0) | result.get('zero_volume', False)
    result['provider_zero_volume_discrepancy'] = result['zero_volume']
    return result


def filter_primary_session(data: pd.DataFrame, asset_class: str, **kwargs) -> pd.DataFrame:
    """Select annotated session rows without resampling or deduplicating."""
    assigned = assign_primary_session(data, asset_class, **kwargs)
    return assigned.loc[assigned.primary_session_retained].copy()
