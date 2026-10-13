"""ES/CL individual-contract selection and overnight trade-date diagnostics.

Run: python -B src/futures_roll.py
Calendars are exact daily assignments (no forward fill). A dated transition-list
interpretation is not silently substituted. Prices come only from validated
<ROOT>_<MONTH><YY>_1min.txt individual contract files. No adjusted series reads.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
from itertools import islice
import json
from pathlib import Path
import re
import time

import numpy as np
import pandas as pd

try:
    from .data_io import intraday_root, is_timestamp
    from .eda_diagnostics import parse_chunk
    from .session_rules import assign_primary_session
    from .benchmark import build_roll_benchmark, summarize_roll_benchmark
except ImportError:
    from data_io import intraday_root, is_timestamp
    from eda_diagnostics import parse_chunk
    from session_rules import assign_primary_session
    from benchmark import build_roll_benchmark, summarize_roll_benchmark

TZ = 'America/New_York'
OUT = Path(__file__).resolve().parents[1] / 'outputs/diagnostics/futures_roll'
CODE = re.compile(r'[FGHJKMNQUVXZ]\d{2}')


def parse_provider_calendar(path: Path) -> pd.DataFrame:
    """Strict daily calendar parser: reject conflicting/duplicate dates and codes."""
    rows = []
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        for number, row in enumerate(csv.reader(stream), 1):
            if len(row) != 2 or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', row[0]) or not CODE.fullmatch(row[1]):
                raise ValueError(f'Invalid provider calendar row {number}: {row!r}')
            date = pd.Timestamp(row[0])
            rows.append((date, row[1], number))
    table = pd.DataFrame(rows, columns=['provider_mapping_date', 'selected_contract', 'provider_line'])
    if table.empty or table.provider_mapping_date.duplicated().any():
        raise ValueError('Empty or duplicate-date provider calendar; no silent resolution')
    if not table.provider_mapping_date.is_monotonic_increasing:
        raise ValueError('Provider mapping dates out of order')
    change = table.selected_contract.ne(table.selected_contract.shift())
    table['provider_transition_flag'] = change & table.index.to_series().ne(0)
    table['provider_transition_date'] = table.provider_mapping_date.where(change).ffill()
    # Forward propagation here labels the original transition, never fills mapping gaps.
    table['provider_previous_contract'] = table.selected_contract.shift()
    return table


def contract_file(directory: Path, root: str, code: str) -> Path:
    if root not in {'ES', 'CL'} or not isinstance(code, str) or not CODE.fullmatch(code):
        raise ValueError('Only ES/CL unadjusted individual contract codes allowed')
    return Path(directory) / f'{root}_{code}_1min.txt'


def session_bounds(trade_date):
    day = pd.Timestamp(trade_date).normalize()
    return ((day - pd.Timedelta(days=1) + pd.Timedelta(hours=18)).tz_localize(TZ),
            (day + pd.Timedelta(hours=17)).tz_localize(TZ))


def selection_plan(calendar: pd.DataFrame, root: str, start, end, directory: Path) -> pd.DataFrame:
    """Every requested calendar trade date is audited, even if no mapping exists.

    Diagnostic date rows are not synthetic bars or assumed exchange sessions.
    """
    mapping = calendar.set_index('provider_mapping_date')
    records = []
    for day in pd.date_range(start, end, freq='D'):
        record = mapping.loc[day] if day in mapping.index else None
        selected = record.selected_contract if record is not None else None
        path = contract_file(directory, root, selected) if selected else None
        begin, finish = session_bounds(day)
        records.append(dict(root=root, trade_date=day.date(), timezone=TZ,
            session_start=begin, session_end=finish, selected_contract=selected,
            provider_mapping_date=day.date() if record is not None else None,
            provider_transition_date=record.provider_transition_date.date() if record is not None else None,
            provider_transition_flag=bool(record.provider_transition_flag) if record is not None else False,
            provider_previous_contract=record.provider_previous_contract if record is not None else None,
            contract_file=str(path) if path else '', contract_file_exists=path.is_file() if path else False))
    return pd.DataFrame(records)


def empty_bars():
    return pd.DataFrame({'timestamp': pd.Series(dtype='datetime64[ns]'),
                         'close': pd.Series(dtype=float), 'volume': pd.Series(dtype=float),
                         'trade_date': pd.Series(dtype=object), 'selected_contract': pd.Series(dtype=str)})


def read_contract_window(path: Path, root: str, code: str, start, end, out: Path):
    """Small pilot, then bounded full-file scan; retain diagnostic date range.

    Only window rows get OHLCV validation. Invalid timestamps on any scanned row
    are logged. Source fingerprints and read-only opens protect raw files.
    """
    if path.name != contract_file(path.parent, root, code).name:
        raise ValueError('Unexpected price filename (continuous/adjusted files forbidden)')
    before = path.stat()
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        pilot = list(islice(stream, 10))
    if not pilot or any(len(line.strip().split(',')) != 6 or not is_timestamp(line[:19]) for line in pilot):
        raise ValueError('Individual-contract pilot validation failed')
    begin = pd.Timestamp(start) - pd.Timedelta(days=1)
    finish = pd.Timestamp(end) + pd.Timedelta(days=1)
    pieces, counts = [], Counter(raw_rows_scanned=0, raw_window_rows=0, unassignable_timestamp_rows=0)
    problem = out / f'{root}_{code}_unassignable_rows.csv'
    with problem.open('w', encoding='utf-8', newline='') as failures:
        writer = csv.writer(failures)
        writer.writerow(['raw_line_number', 'raw_text', 'reason'])
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            offset = 1
            while lines := list(islice(stream, 100_000)):
                text = pd.Series([line.split(',', 1)[0].strip() for line in lines])
                ts = pd.to_datetime(text, format='%Y-%m-%d %H:%M:%S', errors='coerce')
                ts = ts.where(text.str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'))
                bad = ts.isna()
                counts['unassignable_timestamp_rows'] += int(bad.sum())
                counts['raw_rows_scanned'] += len(lines)
                for i in np.flatnonzero(bad):
                    writer.writerow([offset + int(i), lines[i].rstrip('\r\n'), 'unassignable_timestamp'])
                positions = np.flatnonzero(ts.ge(begin) & ts.lt(finish))
                if len(positions):
                    _, parsed = parse_chunk([lines[p] for p in positions], 1)
                    parsed.index = pd.Index(offset + positions, name='raw_line_number')
                    pieces.append(parsed)
                    counts['raw_window_rows'] += len(parsed)
                offset += len(lines)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Raw provider file changed during read')
    data = pd.concat(pieces) if pieces else empty_bars()
    assigned = assign_primary_session(data, 'futures', futures_root=root)
    assigned['source_contract'] = code
    assigned['duplicate_timestamp'] = assigned.timestamp.notna() & assigned.timestamp.duplicated(keep=False)
    flags = [c for c in ['missing_value', 'non_numeric', 'non_finite', 'invalid_ohlc', 'zero_volume', 'negative_volume', 'malformed_columns', 'duplicate_timestamp', 'timezone_assignment_failed'] if c in assigned]
    assigned.loc[assigned[flags].any(axis=1)].to_csv(out / f'{root}_{code}_flagged_rows.csv', index=True)
    return assigned, dict(counts, file=str(path), root=root, contract=code,
        file_size_bytes=before.st_size, raw_mtime_ns=before.st_mtime_ns,
        bytes_scanned_approx=before.st_size + sum(len(s.encode('utf-8')) for s in pilot))


def validate_sessions(plan: pd.DataFrame, contract_bars: dict[str, pd.DataFrame],
                      *, previous_observed_contract: str | None = None,
                      read_errors: dict[str, str] | None = None):
    """Use only selected code for each session. Never substitute another contract."""
    records, retained_pieces = [], []
    previous = previous_observed_contract
    read_errors = read_errors or {}
    # Pre-group once; every selected timestamp remains a physical raw observation.
    grouped = {}
    maintenance = {}
    for code, data in contract_bars.items():
        if data.source_contract.ne(code).any():
            raise ValueError('Contract provenance does not match input key')
        grouped[code] = {day: group for day, group in data.loc[data.primary_session_retained].groupby('trade_date')}
        wall = data.timestamp_local.dt.tz_localize(None)
        maintenance[code] = data.loc[data.maintenance_interval].groupby(wall.dt.date).size().to_dict()
    for record in plan.to_dict('records'):
        day, code = record['trade_date'], record['selected_contract']
        group = grouped.get(code, {}).get(day)
        n = 0 if group is None else len(group)
        reason = ''
        if code is None or pd.isna(code):
            reason = 'missing_provider_trade_date_mapping'
        elif not record['contract_file_exists']:
            reason = 'missing_individual_contract_file'
        elif code in read_errors:
            reason = 'individual_contract_read_failure'
        elif not n:
            reason = 'selected_contract_has_no_session_observations'
        if reason:
            group, n = None, 0
        first, last, gap, zero, evening = pd.NaT, pd.NaT, np.nan, 0, 0
        if n:
            group = group.sort_values('timestamp_local', kind='stable').copy()
            if not group.source_contract.eq(code).all():
                raise ValueError('More than one contract in a trade-date session')
            group['selected_contract'] = code
            group['root'] = record['root']
            retained_pieces.append(group)
            first, last = group.timestamp_local.min(), group.timestamp_local.max()
            gap = group.timestamp_local.diff().dt.total_seconds().div(60).max()
            zero = int(group.zero_volume.sum())
            evening = int((group.timestamp_local.dt.tz_localize(None).dt.date < day).sum())
        roll = bool(n and previous is not None and code != previous)
        record.update(previous_contract=previous, roll_day=roll, bars_observed=n,
            first_timestamp=first, last_timestamp=last, max_gap_minutes=gap,
            zero_volume_rows=zero,
            outside_session_rows=int(maintenance.get(code, {}).get(day, 0)),
            previous_evening_rows=evening, previous_evening_present=bool(evening),
            sparse_session_le10_bars=0 < n <= 10,
            validation_status='no_session_observations' if not n else ('flagged' if reason else 'ok'), validation_reason=reason)
        records.append(record)
        if n:
            previous = code
    return pd.DataFrame(records), pd.concat(retained_pieces, ignore_index=True) if retained_pieces else empty_bars()


def observed_roll_diagnostic(selected: pd.DataFrame, sessions: pd.DataFrame, root: str):
    """Analytic Roll rows are observed trade dates; empty dates stay in audit."""
    daily, audit = build_roll_benchmark(selected, root, 'futures', futures_root=root,
                                       return_bar_audit=True)
    metadata = sessions.loc[sessions.bars_observed.gt(0),
        ['trade_date', 'selected_contract', 'previous_contract', 'roll_day', 'validation_reason']].rename(columns={'trade_date': 'date'})
    daily = daily.merge(metadata, on='date', how='left', validate='one_to_one')
    if daily.selected_contract.isna().any() or not daily.bars_observed.gt(0).all():
        raise ValueError('Observed benchmark days must match validated contract selections')
    return daily, audit


def transitions_for_review(sessions: pd.DataFrame, calendar: pd.DataFrame, root: str):
    provider = calendar.loc[calendar.provider_transition_flag & calendar.provider_mapping_date.between('2023-01-01', '2025-12-31')]
    records = []
    for row in provider.itertuples():
        found = sessions.loc[(pd.to_datetime(sessions.trade_date) >= row.provider_mapping_date)
                             & sessions.selected_contract.eq(row.selected_contract) & sessions.bars_observed.gt(0)]
        match = found.iloc[0] if len(found) else None
        records.append(dict(root=root, provider_transition_date=row.provider_mapping_date.date(),
            previous_contract=row.provider_previous_contract, selected_contract=row.selected_contract,
            first_observed_trade_date=match.trade_date if match is not None else None,
            provider_mapping_date=match.provider_mapping_date if match is not None else None,
            previous_evening_rows=int(match.previous_evening_rows) if match is not None else 0,
            previous_evening_present=bool(match.previous_evening_present) if match is not None else False,
            first_timestamp=match.first_timestamp if match is not None else pd.NaT,
            validation_reason='' if match is not None and match.previous_evening_present else 'transition_session_lacks_previous_evening_observations'))
    return pd.DataFrame(records)


def table_md(table):
    lines = ['| ' + ' | '.join(table.columns) + ' |', '| ' + ' | '.join(['---'] * len(table.columns)) + ' |']
    for values in table.itertuples(index=False, name=None):
        lines.append('| ' + ' | '.join('NA' if pd.isna(v) else f'{v:.6f}' if isinstance(v, float) else str(v) for v in values) + ' |')
    return '\n'.join(lines)


def summarize_validation_outputs(out: Path):
    """Review derived audits without another provider-data scan."""
    sessions = pd.read_csv(out / 'trade_date_sessions.csv')
    quality, unmapped = [], []
    for root in ['ES', 'CL']:
        counts = Counter()
        for path in out.glob(f'{root}_*_flagged_rows.csv'):
            rows = pd.read_csv(path)
            for flag in ['missing_value', 'non_numeric', 'non_finite', 'invalid_ohlc',
                         'zero_volume', 'negative_volume', 'malformed_columns',
                         'duplicate_timestamp', 'timezone_assignment_failed']:
                if flag in rows:
                    counts[flag + '_rows'] += int(rows[flag].sum())
        quality.append(dict(root=root, scope='all scanned contract rows in diagnostic window, including unselected contracts', **counts))
        missing = set(sessions.loc[sessions.root.eq(root) & sessions.selected_contract.isna(), 'trade_date'])
        for path in out.glob(f'{root}_*_contract_selection_rejections.csv'):
            rows = pd.read_csv(path)
            found = rows.loc[rows.trade_date.isin(missing)].copy()
            if len(found):
                found['root'] = root
                found['source_contract'] = path.name.split('_')[1]
                unmapped.append(found)
    quality = pd.DataFrame(quality)
    quality.to_csv(out / 'data_quality_review.csv', index=False)
    unmapped = pd.concat(unmapped, ignore_index=True) if unmapped else pd.DataFrame(columns=['trade_date', 'outside_primary_futures_session', 'rows_not_selected', 'root', 'source_contract'])
    unmapped.to_csv(out / 'unmapped_dates_with_contract_observations.csv', index=False)
    report_path = out / 'futures_roll_report.md'
    report_path.write_text(report_path.read_text(encoding='utf-8').split('\n\nData-quality review')[0], encoding='utf-8')
    with report_path.open('a', encoding='utf-8') as report:
        report.write('\n\nData-quality review (unselected contract rows included)\n\n' + table_md(quality))
        report.write(f'\n\nUnmapped trade dates with observations in scanned individual contracts: {unmapped.groupby(["root", "trade_date"]).ngroups if len(unmapped) else 0}. These rows remain unselected; see unmapped_dates_with_contract_observations.csv.\n')
        missing_files = sessions.loc[sessions.selected_contract.notna() & ~sessions.contract_file_exists].groupby(['root', 'selected_contract']).agg(affected_dates=('trade_date', 'size'), first_date=('trade_date', 'min'), last_date=('trade_date', 'max')).reset_index()
        report.write('\nMissing individual files\n\n' + table_md(missing_files))
        reasons = sessions.loc[sessions.validation_status.ne('ok')].groupby(['root', 'validation_reason']).size().rename('dates').reset_index()
        report.write('\n\nSession validation reasons\n\n' + table_md(reasons))
        benchmark = pd.read_csv(out / 'common_window_roll_benchmark.csv')
        undefined = benchmark.loc[~benchmark.roll_defined].groupby(['asset', 'benchmark_failure_reason']).size().rename('dates').reset_index()
        report.write('\n\nNovember benchmark undefined reasons\n\n' + table_md(undefined))
        report.write('\n\nProvider-calendar limitations: daily rows are not a complete calendar; exact missing dates remain flagged. Some provider transitions fall on Sundays, while the first observed session ends Monday. These dates are retained separately. Late-2025 mappings require missing 2026-coded individual files. No mapping was contradicted by observations on an unmapped trade date in the scanned contracts; this is not independent validation of the provider roll policy.\n')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    root_path = intraday_root() / 'futures'
    all_sessions, transitions, scans, failures, roll_days, mapping_audits = [], [], [], [], [], []
    begin = time.perf_counter()
    for root in ['ES', 'CL']:
        calendar_path = root_path / f'{root}_continuous_contract_dates.txt'
        calendar = parse_provider_calendar(calendar_path)
        mapping_audits.append(dict(root=root, file=str(calendar_path), sha256=hashlib.sha256(calendar_path.read_bytes()).hexdigest(), rows=len(calendar)))
        calendar.to_csv(OUT / f'{root}_provider_calendar.csv', index=False)
        # A week of observed sessions establishes predecessor across the output boundary.
        plan = selection_plan(calendar, root, '2022-12-25', '2025-12-31', root_path)
        bars, read_errors = {}, {}
        for code in sorted(plan.selected_contract.dropna().unique()):
            path = contract_file(root_path, root, code)
            if not path.is_file():
                continue
            print(f'Reading {root}/{code}', flush=True)
            try:
                data, scan = read_contract_window(path, root, code, '2022-12-25', '2025-12-31', OUT)
                data.loc[data.maintenance_interval].to_csv(OUT / f'{root}_{code}_maintenance_rows.csv', index=True)
                assigned_dates = set(plan.loc[plan.selected_contract.eq(code), 'trade_date'])
                keep = data.trade_date.isin(assigned_dates) | (data.maintenance_interval & data.timestamp_local.dt.date.isin(assigned_dates))
                rejected = data.loc[~keep].copy()
                rejected.groupby(['trade_date', 'outside_primary_futures_session'], dropna=False).size().rename('rows_not_selected').to_csv(OUT / f'{root}_{code}_contract_selection_rejections.csv')
                bars[code] = data.loc[keep].copy()
                scans.append(scan)
            except Exception as exc:
                read_errors[code] = f'{type(exc).__name__}: {exc}'
                failures.append(dict(root=root, contract=code, file=str(path), error=read_errors[code]))
        sessions, selected = validate_sessions(plan, bars, read_errors=read_errors)
        sessions = sessions.loc[pd.to_datetime(sessions.trade_date).ge('2023-01-01')].copy()
        all_sessions.append(sessions)
        transitions.append(transitions_for_review(sessions, calendar, root))
        common = selected.loc[pd.to_datetime(selected.trade_date).between('2024-11-04', '2024-11-15')].copy()
        common.to_csv(OUT / f'{root}_common_window_selected_bars.csv', index=False)
        daily, audit = observed_roll_diagnostic(common, sessions, root)
        roll_days.append(daily)
        audit.to_csv(OUT / f'{root}_common_window_roll_bar_audit.csv', index=False)
        # Audit all maintenance rows and rejected contract rows in requested windows.
        del bars, selected
    sessions = pd.concat(all_sessions, ignore_index=True)
    review = pd.concat(transitions, ignore_index=True)
    sessions.to_csv(OUT / 'trade_date_sessions.csv', index=False)
    sessions.loc[sessions.roll_day].to_csv(OUT / 'observed_contract_transitions.csv', index=False)
    review.to_csv(OUT / 'provider_transition_review.csv', index=False)
    review.loc[pd.to_datetime(review.provider_transition_date).dt.year.eq(2024)].to_csv(OUT / 'transitions_2024.csv', index=False)
    sessions.loc[sessions.validation_status.ne('ok')].to_csv(OUT / 'flagged_sessions.csv', index=False)
    pd.DataFrame(scans).to_csv(OUT / 'file_scan_audit.csv', index=False)
    pd.DataFrame(failures, columns=['root', 'contract', 'file', 'error']).to_csv(OUT / 'failures.csv', index=False)
    benchmark = pd.concat(roll_days, ignore_index=True)
    benchmark.to_csv(OUT / 'common_window_roll_benchmark.csv', index=False)
    benchmark.loc[~benchmark.roll_defined].to_csv(OUT / 'common_window_undefined_days.csv', index=False)
    benchmark_summary = summarize_roll_benchmark(benchmark)
    benchmark_summary.to_csv(OUT / 'common_window_roll_summary.csv', index=False)
    summary = []
    for root, group in sessions.groupby('root', sort=False):
        summary.append(dict(root=root, audited_calendar_trade_dates=len(group),
            mapped_trade_dates=int(group.selected_contract.notna().sum()), observed_trade_dates=int(group.bars_observed.gt(0).sum()),
            observed_roll_days=int(group.roll_day.sum()), provider_transitions=int(review.root.eq(root).sum()),
            missing_contract_files=group.loc[group.selected_contract.notna() & ~group.contract_file_exists, 'selected_contract'].nunique(),
            mapped_sessions_without_observations=int((group.selected_contract.notna() & group.bars_observed.eq(0)).sum()),
            missing_mapping_dates=int(group.selected_contract.isna().sum()),
            transition_sessions_without_evening=int((review.root.eq(root) & ~review.previous_evening_present).sum()),
            zero_volume_rows=int(group.zero_volume_rows.sum()), maintenance_rows=int(group.outside_session_rows.sum())))
    summary = pd.DataFrame(summary)
    summary.to_csv(OUT / 'summary_by_root.csv', index=False)
    manifest = dict(source_root=str(root_path), period=['2023-01-01', '2025-12-31'],
        mapping_files=mapping_audits, selection='exact provider trade-date row, no forward fill or contract substitution',
        mapping_date_semantics='provider_mapping_date is exact daily lookup row; provider_transition_date is first row selecting the changed code',
        session='18:00 previous calendar day inclusive to 17:00 trade date exclusive America/New_York',
        roll_day='changed selected code versus previous observed trade-date, one-week boundary warmup',
        outside_session_rows='selected contract maintenance bars 17:00-18:00 on the ending calendar date; not all rejected alternative-contract rows',
        date_grid='all requested calendar dates audited; no session calendar inferred, no bar/day volumes synthesized',
        analytic_asset_days='observed sessions only; zero-observation dates remain audit rows with no_session_observations status',
        no_observation_interpretation='flag only; may reflect weekends/holidays/early closes/mapping or data limitations; no cause assumed',
        prices='unadjusted individual contracts only', roll_days_excluded=False,
        inserted_minute_bars=0, runtime_seconds=time.perf_counter() - begin,
        bytes_scanned_approx=sum(s['bytes_scanned_approx'] for s in scans), failures=failures)
    (OUT / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, default=str), encoding='utf-8')
    report = ('# ES/CL futures pilot: 2023–2025\n\n' + table_md(summary)
        + '\n\nCommon window Roll validation: trade dates 2024-11-04 through 2024-11-15\n\n' + table_md(benchmark_summary)
        + '\n\n2024 provider transition checks\n\n' + table_md(review.loc[pd.to_datetime(review.provider_transition_date).dt.year.eq(2024)])
        + '\n\nProvider calendar is used as an exact daily trade-date mapping. Unmapped dates are flagged, never forward-filled. Calendar audit rows include weekends; no bars synthesized and no weekend/holiday causes inferred. Provider transition date and observed roll day are distinct.\n'
        + '\nEach session uses one unadjusted individual contract, including its previous-day evening. File existence alone is insufficient: session and evening observations are inspected. Maintenance bars are excluded and audited. Roll days remain included.\n'
        + '\nSee flagged_sessions.csv and provider_transition_review.csv for all missing observations and evening flags. Sunday provider rows can have no observations while the next Monday session contains Sunday evening bars. This does not justify silently changing the mapping.\n'
        + '\nThe analytic candidate Roll benchmark includes only observed trade dates. Zero-observation dates remain in the calendar audit with no_session_observations status. Insufficient Roll pairs can only describe a day with observed bars. No CS/AR/EDGE or continuous adjusted prices are used.\n')
    (OUT / 'futures_roll_report.md').write_text(report, encoding='utf-8')
    summarize_validation_outputs(OUT)
    print(summary.to_string(index=False), flush=True)
    print(benchmark_summary.to_string(index=False), flush=True)
    if failures:
        raise RuntimeError('Contract reads failed; see failures.csv')


if __name__ == '__main__':
    main()
