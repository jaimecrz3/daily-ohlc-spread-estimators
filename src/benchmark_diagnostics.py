"""Validate Roll benchmark on AAPL/SPY/BTC/ETH, 2024-11-04 through 15.

Run: .venv/Scripts/python.exe -B src/benchmark_diagnostics.py
Full-file bounded timestamp scans, small initial pilot reads, full quality
parsing only within the requested window. Provider files opened read-only.
"""
from collections import Counter
import csv
from itertools import islice
import json
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from benchmark import build_roll_benchmark, summarize_roll_benchmark
from data_io import PILOT_FILES, TIMESTAMP_FORMAT, inspect_file, intraday_root
from eda_diagnostics import parse_chunk

START, END = pd.Timestamp('2024-11-04'), pd.Timestamp('2024-11-16')
ASSETS = {'AAPL', 'SPY', 'BTC', 'ETH'}
OUTPUT = Path(__file__).resolve().parents[1] / 'outputs' / 'diagnostics' / 'roll_benchmark'


def read_window(path: Path, start: pd.Timestamp, end: pd.Timestamp,
                problems_path: Path, chunk_size: int = 100_000):
    """Retain selected physical rows and their line IDs, without sorted-file assumptions.

    All unassignable timestamps are logged even outside the window. Quality flags
    on outside-window numeric fields are not inspected by this small diagnostic.
    Stat fingerprints detect source changes during reading; no writes to source.
    """
    before = path.stat()
    counts = Counter(raw_rows_scanned=0, unassignable_timestamp_rows=0,
                     outside_window_rows=0, window_raw_bars=0)
    pieces = []
    with problems_path.open('w', encoding='utf-8', newline='') as problems:
        writer = csv.writer(problems)
        writer.writerow(['raw_line_number', 'raw_text', 'reason'])
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            offset = 1
            while lines := list(islice(stream, chunk_size)):
                text = pd.Series([line.split(',', 1)[0].strip() for line in lines])
                ts = pd.to_datetime(text, format=TIMESTAMP_FORMAT, errors='coerce')
                ts = ts.where(text.str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'))
                bad = ts.isna()
                selected = ts.ge(start) & ts.lt(end)
                counts['raw_rows_scanned'] += len(lines)
                counts['unassignable_timestamp_rows'] += int(bad.sum())
                counts['outside_window_rows'] += int((~bad & ~selected).sum())
                counts['window_raw_bars'] += int(selected.sum())
                for position in np.flatnonzero(bad):
                    writer.writerow([offset + int(position), lines[position].rstrip('\r\n'), 'unassignable_timestamp'])
                positions = np.flatnonzero(selected)
                if len(positions):
                    _, parsed = parse_chunk([lines[p] for p in positions], 1)
                    parsed.index = pd.Index(offset + positions, name='raw_line_number')
                    pieces.append(parsed)
                offset += len(lines)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f'Source changed during read: {path}')
    if not pieces:
        raise ValueError(f'No date-assignable window bars: {path}; counts={dict(counts)}')
    assert counts['raw_rows_scanned'] == (counts['unassignable_timestamp_rows'] + counts['outside_window_rows'] + counts['window_raw_bars'])
    counts.update(raw_size_bytes=before.st_size, raw_mtime_ns=before.st_mtime_ns)
    return pd.concat(pieces), dict(counts)


def markdown_table(table):
    columns = list(table.columns)
    lines = ['| ' + ' | '.join(columns) + ' |', '| ' + ' | '.join(['---'] * len(columns)) + ' |']
    for values in table.itertuples(index=False, name=None):
        lines.append('| ' + ' | '.join('undefined' if pd.isna(v) else (f'{v:.6f}' if isinstance(v, float) else str(v)) for v in values) + ' |')
    return '\n'.join(lines)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    root = intraday_root()
    daily_parts, scans, failures, pilots = [], [], [], []
    for relative in PILOT_FILES:
        asset, cls = Path(relative).name.split('_')[0], relative.split('/')[0]
        if asset not in ASSETS:
            continue
        print(f'Reading {asset} for benchmark validation', flush=True)
        pilot = inspect_file(root, relative)
        pilots.append(pilot)
        try:
            if pilot['status'] != 'ok':
                raise ValueError(f'Pilot read failed: {pilot}')
            data, scan = read_window(root / relative, START, END, OUTPUT / f'{asset}_unassignable_rows.csv')
            daily, audit = build_roll_benchmark(data, asset, cls, return_bar_audit=True)
            audit.to_csv(OUTPUT / f'{asset}_bar_audit.csv', index=False)
            daily_parts.append(daily)
            scans.append(dict(asset=asset, file=relative, **scan,
                retained_session_bars=int(audit.primary_session_retained.sum()),
                outside_session_bars=int((~audit.primary_session_retained).sum()),
                inserted_minute_bars=0))
            assert daily.bars_observed.sum() == audit.primary_session_retained.sum()
            print(f'{asset}: {len(daily)} observed session days, {int(daily.roll_defined.sum())} defined', flush=True)
        except Exception as exc:
            failures.append(dict(asset=asset, file=relative, error_type=type(exc).__name__, error=str(exc)))
            print(f'{asset} failed: {exc}', flush=True)
    daily = pd.concat(daily_parts, ignore_index=True) if daily_parts else pd.DataFrame()
    pd.DataFrame(failures, columns=['asset', 'file', 'error_type', 'error']).to_csv(OUTPUT / 'failures.csv', index=False)
    pd.DataFrame(scans).to_csv(OUTPUT / 'file_scan_audit.csv', index=False)
    manifest = dict(window_start=str(START.date()), window_end_inclusive='2024-11-15',
        source_root=str(root), pilots=pilots, failures=failures, python=platform.python_version(),
        pandas=pd.__version__, numpy=np.__version__, covariance='paired-vector sample covariance, separate means, ddof=1; >=2 pairs',
        returns='simple close-to-close returns; exact one-minute adjacent timestamp gaps, within session-day only',
        pair_rule='three consecutive eligible closes with two one-minute gaps; no compressed valid-return sequence',
        close_validity='finite positive close; malformed/invalid OHLC/timezone-unassignable/duplicate timestamp bars ineligible; all retained in audit',
        zero_volume_policy='retained and flagged; valid prices remain eligible', coverage_exclusions='none',
        no_observation_days='no synthetic days generated; not interpreted as holidays or exclusions',
        max_gap_minutes='largest adjacent observed within-session gap, before close eligibility; NaN for <2 bars',
        outside_window_quality='timestamps only; numeric/quality fields parsed only within requested window',
        inserted_minute_bars=0, raw_provider_writes=0, pending=['futures universe/session hours', 'FX official folder inaccessible', 'benchmark reliability exclusions'],
        reference='https://doi.org/10.1111/j.1540-6261.1984.tb03897.x',
        adaptation='Project-specified simple-return relative spread; original Roll formula uses price changes')
    (OUTPUT / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, default=str), encoding='utf-8')
    if not daily.empty:
        daily.to_csv(OUTPUT / 'asset_day_benchmark.csv', index=False)
        undefined = daily.loc[~daily.roll_defined]
        undefined.to_csv(OUTPUT / 'undefined_days.csv', index=False)
        reasons = undefined.groupby(['asset', 'benchmark_failure_reason']).size().rename('asset_days').reset_index()
        reasons.to_csv(OUTPUT / 'undefined_reason_summary.csv', index=False)
        summary = summarize_roll_benchmark(daily)
        summary.to_csv(OUTPUT / 'summary_by_asset.csv', index=False)
        notes = ('# Roll benchmark validation: 2024-11-04 through 2024-11-15\n\n' + markdown_table(summary)
                 + '\n\nUndefined cases\n\n' + (markdown_table(reasons) if len(reasons) else 'None.')
                 + '\n\nAt least two Roll pairs; sample covariance ddof=1. No strong coverage exclusions. All observed session days retained; dates without recorded session bars are not synthesized. No minute bars filled. Zero-volume rows retained and flagged.\n'
                 + '\nThis is the project-specified simple-return adaptation of [Roll (1984)](https://doi.org/10.1111/j.1540-6261.1984.tb03897.x), whose original formula uses price changes. Benchmark validation only; no cross-asset spread interpretation.\n')
        (OUTPUT / 'summary_by_asset.md').write_text(notes, encoding='utf-8')
        print(summary.to_string(index=False), flush=True)
    if failures:
        raise RuntimeError('Incomplete diagnostic; see roll_benchmark/failures.csv')


if __name__ == '__main__':
    main()
