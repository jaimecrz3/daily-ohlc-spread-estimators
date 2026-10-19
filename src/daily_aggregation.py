"""Observed session-day OHLCV, separate from benchmark and estimator tables.

Run: .venv/Scripts/python.exe -B src/daily_aggregation.py
All source rows are read-only. No bars/dates are inserted or quality-filtered.
Equity daily values are local validation inputs; Bloomberg alignment is pending.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

try:
    from .data_io import asset_metadata, inspect_file, intraday_root
    from .session_rules import assign_primary_session
    from .futures_roll import parse_provider_calendar, selection_plan, contract_file, read_contract_window, validate_sessions, table_md
except ImportError:
    from data_io import asset_metadata, inspect_file, intraday_root
    from session_rules import assign_primary_session
    from futures_roll import parse_provider_calendar, selection_plan, contract_file, read_contract_window, validate_sessions, table_md

OUT = Path(__file__).resolve().parents[1] / 'outputs/diagnostics/daily_aggregation'
START, END = pd.Timestamp('2024-11-04'), pd.Timestamp('2024-11-16')
OHLCV = ['open', 'high', 'low', 'close', 'volume']
FLAGS = ['zero_volume', 'duplicate_timestamp', 'missing_value', 'invalid_ohlc',
         'non_numeric', 'non_finite', 'negative_volume', 'malformed_columns',
         'timezone_assignment_failed']
FUTURES_FIELDS = ['root', 'selected_contract', 'contract_file', 'roll_day',
                  'previous_contract', 'provider_mapping_date',
                  'provider_transition_date', 'provider_transition_flag']
DAILY_COLUMNS = ['asset', 'asset_class', 'date', 'trade_date', 'timezone', 'source',
    'source_role', 'adjustment', 'source_file', 'volume_unit'] + OHLCV + [
    'bars_observed', 'first_timestamp', 'last_timestamp', 'max_gap_minutes'] + [
    f + '_rows' for f in FLAGS] + ['aggregation_valid', 'aggregation_failure_reason'] + FUTURES_FIELDS


def flag(data, name):
    return data[name].fillna(False).astype(bool) if name in data else pd.Series(False, index=data.index)


def aggregate_daily_ohlcv(data: pd.DataFrame, asset: str, asset_class: str, *,
                          source_file: str = '', futures_root: str | None = None,
                          futures_audit: pd.DataFrame | None = None,
                          futures_sessions=None,
                          return_bar_audit: bool = False):
    """Aggregate every observed frozen-session day, including flagged days.

    Stable chronological order preserves raw order at duplicate timestamps.
    First open/last close are positional, never first/last non-null values.
    High/low/summed volume use skipna=False: unknown values cannot silently
    become partial extrema or totals. Duplicates contribute as observed rows,
    but invalidate the aggregation pending review. Zero volume and gaps do not.
    Invalid OHLCV/parser flags invalidate the day without dropping its row.

    Futures input must come from Step-5 selection, with its observed session
    audit. Contract provenance, filename, exact mapping date and counts are
    checked; other contracts and empty audit dates cannot become daily rows.
    Benchmark/estimator fields are ignored through an explicit input allowlist.
    """
    metadata = asset_metadata(asset_class)
    columns = ['timestamp'] + OHLCV + [f for f in FLAGS if f in data]
    # Retain parser detail and existing sparse-bar flags in the bar audit.
    # These are diagnostics, never coverage exclusions or estimator inputs.
    detail_flags = ['missing_' + f for f in ['timestamp'] + OHLCV] + [
        'non_numeric_' + f for f in OHLCV] + ['sparse_bar', 'futures_sparse_review_flag']
    columns += [f for f in detail_flags if f in data]
    if asset_class == 'futures':
        if futures_audit is None or not {'selected_contract', 'source_contract'}.issubset(data):
            raise ValueError('Futures aggregation requires Step-5 selection and audit provenance')
        columns += ['selected_contract', 'source_contract']
        if 'root' in data:
            columns += ['root']
    annotated = assign_primary_session(data[columns], asset_class, futures_root=futures_root,
        futures_sessions=futures_sessions).reset_index(drop=True)
    annotated['source_row'] = data.index.to_numpy()
    numeric = annotated[OHLCV].apply(pd.to_numeric, errors='coerce').astype(float)
    annotated['missing_value'] = flag(annotated, 'missing_value') | annotated[OHLCV].isna().any(axis=1)
    annotated['non_numeric'] = flag(annotated, 'non_numeric') | (numeric.isna() & annotated[OHLCV].notna()).any(axis=1)
    annotated['non_finite'] = flag(annotated, 'non_finite') | ((~np.isfinite(numeric)) & numeric.notna()).any(axis=1)
    prices = numeric[['open', 'high', 'low', 'close']]
    invalid = ((prices <= 0).any(axis=1) | prices.high.lt(prices.low)
        | prices.open.gt(prices.high) | prices.open.lt(prices.low)
        | prices.close.gt(prices.high) | prices.close.lt(prices.low))
    annotated['invalid_ohlc'] = flag(annotated, 'invalid_ohlc') | invalid
    annotated['negative_volume'] = flag(annotated, 'negative_volume') | numeric.volume.lt(0)
    annotated['malformed_columns'] = flag(annotated, 'malformed_columns')
    local = annotated.timestamp_local
    annotated['duplicate_timestamp'] = flag(annotated, 'duplicate_timestamp') | (local.notna() & local.duplicated(keep=False))
    # Numeric conversion is a derived copy; original data and flags stay intact.
    annotated[OHLCV] = numeric
    retained = annotated.loc[annotated.primary_session_retained]
    mapping = None
    if asset_class == 'futures':
        if not {'trade_date', 'bars_observed', 'validation_status', *FUTURES_FIELDS[:6]}.issubset(futures_audit):
            raise ValueError('Incomplete futures session audit')
        mapping = futures_audit.copy()
        mapping['trade_date'] = pd.to_datetime(mapping.trade_date).dt.date
        if mapping.trade_date.duplicated().any():
            raise ValueError('Duplicate futures audit trade dates')
        mapping = mapping.set_index('trade_date')
        if retained.selected_contract.isna().any() or retained.groupby('session_day').selected_contract.nunique().gt(1).any():
            raise ValueError('Exactly one selected futures contract per trade date required')
        if retained.source_contract.ne(retained.selected_contract).any():
            raise ValueError('Futures source and selected contracts differ')
        if 'root' in retained and retained.root.ne(futures_root).any():
            raise ValueError('Futures root provenance mismatch')
    rows = []
    for day, group in retained.groupby('session_day', sort=True):
        group = group.sort_values('timestamp_local', kind='stable')
        values = dict(open=group.open.iloc[0], high=group.high.max(skipna=False),
            low=group.low.min(skipna=False), close=group.close.iloc[-1],
            volume=group.volume.sum(skipna=False, min_count=1))
        counts = {f + '_rows': int(flag(group, f).sum()) for f in FLAGS}
        reasons = [f for f in FLAGS if f != 'zero_volume' and counts[f + '_rows']]
        if not np.isfinite(list(values.values())).all():
            reasons.append('non_finite_daily_ohlcv')
        elif not (values['high'] >= max(values['open'], values['close'], values['low'])
                  and values['low'] <= min(values['open'], values['close'])):
            reasons.append('invalid_daily_ohlc')
        row = dict(asset=asset, asset_class=asset_class, date=day,
            trade_date=day if asset_class == 'futures' else None,
            timezone=metadata['timezone'], source='First Rate Data / RiskLab intraday_data',
            source_role='local_daily_validation' if asset_class in {'stocks', 'etfs'} else 'primary_daily_input',
            adjustment='split_and_dividend_adjusted' if asset_class in {'stocks', 'etfs'} else
                       'unadjusted_individual_contract' if asset_class == 'futures' else 'provider_unspecified',
            source_file=str(source_file), volume_unit=metadata['volume_units'], **values,
            bars_observed=len(group), first_timestamp=group.timestamp_local.iloc[0],
            last_timestamp=group.timestamp_local.iloc[-1],
            max_gap_minutes=group.timestamp_local.diff().dt.total_seconds().div(60).max(),
            **counts, aggregation_valid=not reasons, aggregation_failure_reason=';'.join(reasons))
        if asset_class == 'futures':
            if day not in mapping.index:
                raise ValueError('Observed futures day absent from provider-selection audit')
            selected = mapping.loc[day]
            code = group.selected_contract.iloc[0]
            expected = contract_file(Path(selected.contract_file).parent, futures_root, code,
                allowed_roots=futures_sessions)
            if (selected.selected_contract != code or selected.root != futures_root
                    or selected.validation_status != 'ok' or selected.bars_observed != len(group)
                    or pd.isna(selected.provider_mapping_date)
                    or pd.Timestamp(selected.provider_mapping_date).date() != day
                    or Path(selected.contract_file).name != expected.name):
                raise ValueError('Futures rows disagree with validated individual-contract session audit')
            row.update({f: selected[f] for f in FUTURES_FIELDS if f in selected.index})
            row['source_file'] = selected.contract_file
        rows.append(row)
    daily = pd.DataFrame(rows, columns=DAILY_COLUMNS)
    return (daily, annotated) if return_bar_audit else daily


def validate_daily_ohlcv(daily: pd.DataFrame, annotated: pd.DataFrame):
    """Independent mechanical checks against retained physical observations."""
    retained = annotated.loc[annotated.primary_session_retained]
    if len(daily) != retained.session_day.nunique() or not daily.bars_observed.gt(0).all():
        raise AssertionError('Daily table must contain exactly the observed asset-days')
    checks = []
    for row in daily.itertuples():
        group = retained.loc[retained.session_day.eq(row.date)].sort_values('timestamp_local', kind='stable')
        checks_row = dict(asset=row.asset, date=row.date, aggregation_valid=row.aggregation_valid)
        expected = [group.open.iloc[0], np.max(group.high.to_numpy()), np.min(group.low.to_numpy()),
                    group.close.iloc[-1], np.sum(group.volume.to_numpy())]
        for field, value in zip(OHLCV, expected):
            checks_row[field + '_matches_retained_bars'] = bool(np.isclose(getattr(row, field), value, rtol=1e-12, atol=1e-12, equal_nan=True))
        checks_row['bar_count_matches'] = row.bars_observed == len(group)
        checks_row['daily_ohlc_consistent'] = bool(row.high >= row.open and row.high >= row.close
            and row.low <= row.open and row.low <= row.close and row.high >= row.low)
        if row.asset_class == 'futures':
            checks_row['one_contract_per_trade_date'] = bool(group.selected_contract.nunique() == 1 and group.source_contract.eq(row.selected_contract).all())
            checks_row['maintenance_excluded'] = not group.maintenance_interval.any()
        match_cols = [k for k in checks_row if k.endswith('_matches_retained_bars')] + ['bar_count_matches']
        if not all(checks_row[k] for k in match_cols):
            raise AssertionError('Daily reductions disagree with retained bars')
        if row.aggregation_valid and not checks_row['daily_ohlc_consistent']:
            raise AssertionError('Valid daily OHLC violates extrema constraints')
        if row.asset_class == 'futures' and not (checks_row['one_contract_per_trade_date'] and checks_row['maintenance_excluded']):
            raise AssertionError('Futures contract/session leakage')
        checks.append(checks_row)
    return pd.DataFrame(checks)


def summarize_daily_ohlcv(daily):
    rows = []
    for (asset, cls), group in daily.groupby(['asset', 'asset_class'], sort=False):
        rows.append(dict(asset=asset, asset_class=cls, observed_asset_days=len(group),
            total_retained_bars=int(group.bars_observed.sum()),
            median_bars_per_asset_day=group.bars_observed.median(),
            minimum_bars=int(group.bars_observed.min()), maximum_bars=int(group.bars_observed.max()),
            days_with_gaps_gt_1_minute=int(group.max_gap_minutes.gt(1).sum()),
            days_with_zero_volume_rows=int(group.zero_volume_rows.gt(0).sum()),
            invalid_aggregation_days=int((~group.aggregation_valid).sum()),
            first_asset_day=group.date.min(), last_asset_day=group.date.max()))
    return pd.DataFrame(rows)


def main():
    # Shared bounded raw reader; no benchmark tables/values are consumed.
    try:
        from .benchmark_diagnostics import read_window
    except ImportError:
        from benchmark_diagnostics import read_window
    OUT.mkdir(parents=True, exist_ok=True)
    raw_audits = OUT / 'read_audits'
    raw_audits.mkdir(exist_ok=True)
    root_path = intraday_root()
    started = time.perf_counter()
    parts, audits, checks, scans, pilots, failures, calendars = [], [], [], [], [], [], []

    def collect(data, asset, cls, **kwargs):
        daily, annotated = aggregate_daily_ohlcv(data, asset, cls, return_bar_audit=True, **kwargs)
        annotated.to_csv(OUT / f'{asset}_bar_audit.csv', index=False)
        checks.append(validate_daily_ohlcv(daily, annotated))
        parts.append(daily)
        review = daily.copy()
        review['audit_layer'] = 'observed_daily_aggregation'
        review['validation_status'] = np.where(review.aggregation_valid, 'ok', 'invalid_aggregation')
        audits.append(review)
        print(f'{asset}: {len(daily)} observed asset-days, {int((~daily.aggregation_valid).sum())} invalid aggregations', flush=True)

    for asset, cls in [('AAPL', 'stocks'), ('SPY', 'etfs'), ('BTC', 'cryptos'), ('ETH', 'cryptos')]:
        suffix = '_full_1min.txt' if cls == 'cryptos' else '_full_1min_adjsplitdiv.txt'
        relative = f'{cls}/{asset}{suffix}'
        print(f'Reading {asset}', flush=True)
        try:
            pilot = inspect_file(root_path, relative)
            pilots.append(pilot)
            if pilot['status'] != 'ok':
                raise ValueError(f'Pilot validation failed: {pilot}')
            data, scan = read_window(root_path / relative, START, END, raw_audits / f'{asset}_unassignable_rows.csv')
            scans.append(dict(asset=asset, source_file=relative, bytes_scanned_approx=scan['raw_size_bytes'], **scan))
            collect(data, asset, cls, source_file=str(root_path / relative))
        except Exception as exc:
            failures.append(dict(asset=asset, error=f'{type(exc).__name__}: {exc}'))
    for root in ['ES', 'CL']:
        try:
            directory = root_path / 'futures'
            calendar_path = directory / f'{root}_continuous_contract_dates.txt'
            calendar = parse_provider_calendar(calendar_path)
            calendars.append(dict(root=root, file=str(calendar_path), sha256=hashlib.sha256(calendar_path.read_bytes()).hexdigest()))
            # Observed predecessors for roll flags, without warmup analytic rows.
            warmup = START - pd.Timedelta(days=7)
            plan = selection_plan(calendar, root, warmup, END - pd.Timedelta(days=1), directory)
            bars, errors = {}, {}
            for code in sorted(plan.selected_contract.dropna().unique()):
                path = contract_file(directory, root, code)
                if not path.is_file():
                    continue
                print(f'Reading {root}/{code}', flush=True)
                try:
                    bars[code], scan = read_contract_window(path, root, code, warmup, END - pd.Timedelta(days=1), raw_audits)
                    scans.append(dict(asset=root, **scan))
                except Exception as exc:
                    errors[code] = str(exc)
                    failures.append(dict(asset=root, contract=code, error=f'{type(exc).__name__}: {exc}'))
            sessions, selected = validate_sessions(plan, bars, read_errors=errors)
            window = pd.to_datetime(sessions.trade_date).between(START, END - pd.Timedelta(days=1))
            sessions = sessions.loc[window].copy()
            sessions.to_csv(OUT / f'{root}_futures_session_audit.csv', index=False)
            selected = selected.loc[pd.to_datetime(selected.trade_date).between(START, END - pd.Timedelta(days=1))].copy()
            if selected.empty:
                selected = pd.DataFrame({'timestamp': pd.Series(dtype='datetime64[ns]'), **{c: pd.Series(dtype=float) for c in OHLCV}, 'selected_contract': pd.Series(dtype=str), 'source_contract': pd.Series(dtype=str)})
            collect(selected, root, 'futures', futures_root=root, futures_audit=sessions)
            empty = sessions.loc[sessions.bars_observed.eq(0)].copy()
            empty['asset'], empty['asset_class'], empty['date'] = root, 'futures', empty.trade_date
            empty['audit_layer'] = 'futures_calendar_audit'
            audits.append(empty)
        except Exception as exc:
            failures.append(dict(asset=root, error=f'{type(exc).__name__}: {exc}'))
    daily = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=DAILY_COLUMNS)
    summary = summarize_daily_ohlcv(daily)
    audit = pd.concat(audits, ignore_index=True)
    daily.to_csv(OUT / 'daily_ohlcv_pilot.csv', index=False)
    summary.to_csv(OUT / 'summary_by_asset.csv', index=False)
    audit.to_csv(OUT / 'aggregation_audit.csv', index=False)
    pd.concat(checks, ignore_index=True).to_csv(OUT / 'mechanical_validation.csv', index=False)
    pd.DataFrame(scans).to_csv(OUT / 'file_scan_audit.csv', index=False)
    pd.DataFrame(failures, columns=['asset', 'contract', 'error']).to_csv(OUT / 'failures.csv', index=False)
    invalid = daily.loc[~daily.aggregation_valid]
    invalid.to_csv(OUT / 'invalid_aggregation_days.csv', index=False)
    empty = audit.loc[audit.bars_observed.eq(0)]
    empty.to_csv(OUT / 'zero_observation_audit.csv', index=False)
    manifest = dict(window=['2024-11-04', '2024-11-15'], source_root=str(root_path),
        runtime_seconds=time.perf_counter() - started, bytes_scanned_approx=sum(s['bytes_scanned_approx'] for s in scans),
        pilots=pilots, futures_calendars=calendars, failures=failures,
        aggregation='chronological positional first open / last close; max high / min low / summed volume, skipna=False',
        invalid_policy='observed rows retained; missing/nonfinite/non-numeric/malformed/invalid OHLC/negative volume/duplicates flagged invalid; no quality or coverage exclusion',
        zero_volume_policy='retained and flagged, not invalid by itself',
        futures='one exact provider-selected individual contract per overnight trade date; no substitution',
        analytic_days='observed retained sessions only; no zero-observation rows',
        benchmark_or_estimator_values_merged=False, inserted_minute_bars=0, inserted_analytic_dates=0,
        raw_provider_writes=0,
        limitations=['equity/ETF local daily validation only; Bloomberg adjustment/session alignment pending',
                     'crypto bare quote currency unresolved; OHLCV aggregation does not require USD and no notional computed',
                     'ES/CL futures pilot only; late-2025 ES H26 / CL F26,G26 files unavailable',
                     'FX official share unavailable; other futures roots pending'])
    (OUT / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, default=str), encoding='utf-8')
    report = ('# Daily OHLCV pilot: 2024-11-04 through 2024-11-15\n\n' + table_md(summary)
        + f'\n\nInvalid aggregation rows: {len(invalid)}. Zero-observation audit rows: {len(empty)}.\n\n'
        + table_md(empty[['asset', 'date', 'bars_observed', 'validation_status', 'validation_reason']])
        + '\n\nAll valid rows mechanically reconcile to retained bars for first open, maximum high, minimum low, last close and summed volume; extrema constraints checked. Futures provenance and maintenance exclusion checked. Roll flags retained, without coverage exclusions.\n'
        + '\nStocks/ETFs: split_and_dividend_adjusted, local_daily_validation. These are not yet final primary estimator inputs or established Bloomberg equivalents. Crypto: UTC primary_daily_input; quote currency unresolved, no USD notional calculation. Futures: unadjusted selected individual contracts, primary_daily_input.\n'
        + '\nInvalid days remain observed analytic rows with diagnostics. Unknown high/low/volume values propagate rather than becoming partial reductions. Duplicates remain and contribute as raw observations, with invalid_aggregation flags. Zero-volume and gap flags do not alone invalidate a day.\n'
        + '\nEmpty dates remain in futures audit only with no_session_observations status and the underlying mapping/file/session reason. No analytic dates, sessions or bars synthesized; no raw data modified. Daily OHLCV contains no benchmark or estimator values.\n'
        + '\nRemaining limitations: Bloomberg session/adjustment validation pending; crypto quote currency unresolved for liquidity; missing late-2025 futures files outside this pilot; other futures roots and FX access pending. No CS/AR/EDGE, Bloomberg bulk extraction, or work beyond Step 6.\n')
    (OUT / 'daily_aggregation_report.md').write_text(report, encoding='utf-8')
    print(summary.to_string(index=False), flush=True)
    if failures:
        raise RuntimeError('Incomplete daily pilot; see failures.csv')


if __name__ == '__main__':
    main()
