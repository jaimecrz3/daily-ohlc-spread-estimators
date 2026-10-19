"""Frozen primary sessions. No calendar exclusions, filling or quality cleaning.

Naive timestamps are provider wall clocks. DST ambiguity/nonexistence is flagged,
never inferred from ordering. Equity inclusion uses the documented wall clock;
an unresolved UTC instant does not delete a raw row. Default ES/CL pilot sessions
retain their original envelope; other roots require explicit verified configs.
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
    maintenance_intervals: tuple[tuple[time, time], ...] = ()
    effective_start: str | None = None
    effective_end: str | None = None
    rule_id: str = 'legacy_pilot_envelope'


FUTURES_SESSIONS: dict[str, FuturesSessionConfig] = {
    root: FuturesSessionConfig(root, start=time(18), end=time(17),
                               trading_day_convention='overnight_ending_date')
    for root in ('ES', 'CL')
}


def futures_rules(root, configs=None):
    """Explicit root rules only; reject conflicting effective dates."""
    configs = FUTURES_SESSIONS if configs is None else configs
    value = configs.get(root)
    rules = (value,) if isinstance(value, FuturesSessionConfig) else tuple(value or ())
    for rule in rules:
        if (rule.root != root or rule.timezone != 'America/New_York'
                or rule.start is None or rule.end is None or rule.start <= rule.end
                or rule.trading_day_convention != 'overnight_ending_date'):
            raise NotImplementedError(f'Futures session pending/unsupported for root {root!r}')
        if rule.effective_start and rule.effective_end and rule.effective_start > rule.effective_end:
            raise ValueError('Reversed session effective dates')
    for i, left in enumerate(rules):
        for right in rules[i+1:]:
            if max(left.effective_start or '0001-01-01', right.effective_start or '0001-01-01') <= min(left.effective_end or '9999-12-31', right.effective_end or '9999-12-31'):
                raise ValueError('Overlapping date-effective futures rules')
    if not rules:
        raise NotImplementedError(f'Futures session pending for root {root!r}')
    return rules


def resolve_futures_session(root, trade_date, configs=None):
    day = pd.Timestamp(trade_date).date().isoformat()
    rules = [r for r in futures_rules(root, configs)
        if (r.effective_start is None or day >= r.effective_start)
        and (r.effective_end is None or day <= r.effective_end)]
    if len(rules) != 1:
        raise NotImplementedError(f'No verified session for {root} on {day}')
    return rules[0]


def clock_seconds(value):
    return value.hour * 3600 + value.minute * 60 + value.second


def assign_primary_session(data: pd.DataFrame, asset_class: str, *,
                           futures_root: str | None = None,
                           futures_sessions: Mapping[str, FuturesSessionConfig | tuple[FuturesSessionConfig, ...]] | None = None) -> pd.DataFrame:
    """Annotate every input row, preserving order, index, values and flags.

    session_day is an equity local date, crypto UTC date, or futures trade date.
    It is null outside the session. Timestamp localization is a separate column.
    No exchange holiday/early-close policy is implied by the frozen clock rule.
    """
    timezone = asset_metadata(asset_class)['timezone']
    if asset_class == 'futures':
        rules = futures_rules(futures_root, futures_sessions)
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
        retained = pd.Series(False, index=result.index)
        maintenance = retained.copy()
        covered = retained.copy()
        day_clock = wall.dt.normalize().where(retained)
        result['session_rule_id'] = ''
        for config in rules:
            opening, closing = clock_seconds(config.start), clock_seconds(config.end)
            candidate_day = wall.dt.normalize() + pd.to_timedelta(seconds.ge(opening).astype(int), unit='D')
            active = wall.notna()
            if config.effective_start:
                active &= candidate_day.ge(pd.Timestamp(config.effective_start))
            if config.effective_end:
                active &= candidate_day.le(pd.Timestamp(config.effective_end))
            pause = seconds.ge(closing) & seconds.lt(opening)
            for begin, finish in config.maintenance_intervals:
                a, b = clock_seconds(begin), clock_seconds(finish)
                pause |= (seconds.ge(a) & seconds.lt(b)) if a < b else (seconds.ge(a) | seconds.lt(b))
            covered |= active
            maintenance |= active & pause
            keep = active & local.notna() & ~pause
            retained |= keep
            day_clock = day_clock.where(~keep, candidate_day)
            result.loc[active, 'session_rule_id'] = config.rule_id
        result['futures_session_rule_unresolved'] = wall.notna() & ~covered
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
