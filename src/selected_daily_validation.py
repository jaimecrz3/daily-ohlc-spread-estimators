"""Materialize selected equity local daily validation, never Bloomberg data.

Run: .venv/Scripts/python.exe -B src/selected_daily_validation.py
Read provider files once, retaining only observed study-window RTH rows.
No licensed raw records are copied into outputs or delivery folders.
"""
from collections import Counter
from itertools import islice
from pathlib import Path
import hashlib
import json
import time

import pandas as pd

try:
    from .data_io import intraday_root, inspect_file
    from .eda_diagnostics import parse_chunk
    from .session_rules import assign_primary_session
    from .daily_aggregation import aggregate_daily_ohlcv, summarize_daily_ohlcv, validate_daily_ohlcv, FLAGS
    from .final_universe import markdown
except ImportError:
    from data_io import intraday_root, inspect_file
    from eda_diagnostics import parse_chunk
    from session_rules import assign_primary_session
    from daily_aggregation import aggregate_daily_ohlcv, summarize_daily_ohlcv, validate_daily_ohlcv, FLAGS
    from final_universe import markdown

PROJECT = Path(__file__).resolve().parents[1]
BASE = PROJECT / 'outputs/diagnostics/final_universe'
OUT = BASE / 'local_daily_validation'
START, END = pd.Timestamp('2015-01-01'), pd.Timestamp('2026-01-01')
EXPECTED = {'stocks': {'IMDX', 'AIRG', 'CCBG', 'ANGO', 'SNDL', 'FCPT', 'FDS', 'XPO', 'BIDU'},
            'etfs': {'SDCI', 'AAA', 'JSML', 'PGJ', 'PJAN', 'FSMD', 'SPBO', 'SCHM', 'MCHI'}}
REFERENCE_COLUMNS = ['asset', 'asset_class', 'liquidity_tier', 'proposed_bloomberg_security',
    'NAME', 'ID_BB_GLOBAL', 'ID_ISIN', 'ID_CUSIP', 'TICKER_AND_EXCH_CODE', 'CRNCY',
    'instrument_type_validation', 'historical_ticker_validation', 'listed_line_validation',
    'validation_status', 'validation_notes']


def reference_template(selected):
    rows = []
    for row in selected.itertuples():
        note = 'Validate instrument type, listed line, currency and stable identifiers; record BDP retrieval date and retain returned raw data unchanged in personal Google Drive.'
        if row.asset == 'IMDX':
            note += ' Validate historical OCX -> IMDX continuity using stable identifiers; a current BDP snapshot alone cannot establish historical stitching.'
        elif row.asset == 'BIDU':
            note += ' Validate the US ADS listed line and currency; check depositary ratio.'
        elif row.asset == 'FCPT':
            note += ' Validate common REIT equity listed line; REIT common equity is eligible.'
        rows.append(dict(asset=row.asset, asset_class=row.asset_class,
            liquidity_tier=row.liquidity_tier,
            proposed_bloomberg_security=row.expected_bloomberg_security_identifier_placeholder,
            instrument_type_validation='pending', historical_ticker_validation='pending',
            listed_line_validation='pending', validation_status='pending_not_extracted',
            validation_notes=note))
    return pd.DataFrame(rows).reindex(columns=REFERENCE_COLUMNS)


def read_selected_rows(path, cls, issue_path, chunk_size=100_000):
    before = path.stat()
    counts = Counter()
    parts = []
    issue_columns = ['raw_line_number', 'timestamp', 'reason']
    pd.DataFrame(columns=issue_columns).to_csv(issue_path, index=False)
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        offset = 1
        while lines := list(islice(stream, chunk_size)):
            _, parsed = parse_chunk(lines, offset)
            counts['raw_rows_scanned'] += len(lines)
            bad = parsed.timestamp.isna()
            window = parsed.timestamp.ge(START) & parsed.timestamp.lt(END)
            counts['unassignable_timestamp_rows'] += int(bad.sum())
            counts['outside_window_rows'] += int((~bad & ~window).sum())
            counts['window_raw_rows'] += int(window.sum())
            if bad.any():
                pd.DataFrame(dict(raw_line_number=parsed.index[bad], timestamp='',
                    reason='unassignable_timestamp; no asset-day fabricated')).to_csv(issue_path, mode='a', header=False, index=False)
            data = parsed.loc[window]
            if len(data):
                assigned = assign_primary_session(data, cls)
                retained = assigned.primary_session_retained
                counts['outside_primary_session_rows'] += int((~retained).sum())
                counts['outside_primary_session_zero_volume_rows'] += int(assigned.loc[~retained, 'zero_volume'].sum())
                counts['retained_rows'] += int(retained.sum())
                # Original parser values/flags, not annotated copies of prices.
                if retained.any():
                    parts.append(data.loc[retained].copy())
            offset += len(lines)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f'Source changed during scan: {path}')
    assert counts['raw_rows_scanned'] == counts['outside_window_rows'] + counts['unassignable_timestamp_rows'] + counts['window_raw_rows']
    assert counts['window_raw_rows'] == counts['retained_rows'] + counts['outside_primary_session_rows']
    if not parts:
        raise ValueError(f'No observed study-window primary-session bars: {path}')
    return pd.concat(parts), dict(counts, raw_size_bytes=before.st_size,
        raw_mtime_ns=before.st_mtime_ns, fingerprint_unchanged=True)


def run():
    started = time.perf_counter()
    selected_path = BASE / 'selected_stocks_etfs.csv'
    input_hash = hashlib.sha256(selected_path.read_bytes()).hexdigest()
    selected = pd.read_csv(selected_path)
    for cls, names in EXPECTED.items():
        assert set(selected.loc[selected.asset_class.eq(cls), 'asset']) == names
    assert len(selected) == 18
    OUT.mkdir(parents=True, exist_ok=True)
    issues = OUT / 'read_audits'
    issues.mkdir(exist_ok=True)
    reference_template(selected).to_csv(BASE / 'bloomberg_reference_validation_template.csv', index=False)
    root = intraday_root()
    (OUT / 'run_manifest.json').write_text(json.dumps(dict(status='in_progress',
        selected_input_sha256=input_hash, selected_assets=18,
        note='Daily checkpoints are partial until all 18 assets finish and status is complete.'), indent=2), encoding='utf-8')
    parts, summaries, scans, failures = [], [], [], []
    for security in selected.itertuples():
        print(f'Reading {security.asset}', flush=True)
        try:
            relative = Path(security.file)
            assert relative == Path(security.asset_class) / f'{security.asset}_full_1min_adjsplitdiv.txt'
            pilot = inspect_file(root, relative.as_posix())
            if pilot['status'] != 'ok':
                raise ValueError(f'Initial pilot failed: {pilot["status"]}')
            data, scan = read_selected_rows(root / relative, security.asset_class,
                issues / f'{security.asset}_unassignable_rows.csv')
            daily, annotated = aggregate_daily_ohlcv(data, security.asset, security.asset_class,
                source_file=str(root / relative), return_bar_audit=True)
            # Reuse the validated mechanical checks, bounded by observed year.
            for year, group in daily.groupby(pd.to_datetime(daily.date).dt.year):
                validate_daily_ohlcv(group, annotated.loc[annotated.timestamp.dt.year.eq(year)])
            assert daily.bars_observed.sum() == len(data) == scan['retained_rows']
            daily['source'] = 'First Rate Data'
            daily['source_role'] = 'local_daily_validation'
            daily['adjustment'] = 'split_and_dividend_adjusted'
            summary = summarize_daily_ohlcv(daily).iloc[0].to_dict()
            summary['liquidity_tier'] = security.liquidity_tier
            summary['zero_volume_rows'] = int(daily.zero_volume_rows.sum())
            summary['selection_audit_first_date'] = security.first_observed_date
            summary['selection_audit_last_date'] = security.last_observed_date
            summary['first_date_difference_calendar_days'] = (pd.Timestamp(summary['first_asset_day']) - pd.Timestamp(security.first_observed_date)).days
            summary['last_date_difference_calendar_days'] = (pd.Timestamp(summary['last_asset_day']) - pd.Timestamp(security.last_observed_date)).days
            calibration = daily.loc[pd.to_datetime(daily.date).dt.year.eq(2024)]
            summary['observed_2024_days'] = len(calibration)
            summary['selection_audit_2024_days'] = security.observed_2024_days
            summary['observed_2024_days_difference'] = len(calibration) - security.observed_2024_days
            summary['zero_volume_rows_2024'] = int(calibration.zero_volume_rows.sum())
            summary['selection_audit_zero_volume_rows_2024'] = security.zero_volume_rows_2024
            summary['coverage_review_required'] = bool(summary['first_date_difference_calendar_days'] or summary['last_date_difference_calendar_days'] or summary['observed_2024_days_difference'])
            # Zero-row details contain lineage/flags only, never copied OHLCV/raw text.
            zero = annotated.loc[annotated.zero_volume, ['source_row', 'timestamp_local', 'session_day', 'provider_zero_volume_discrepancy']].copy()
            zero.insert(0, 'asset', security.asset)
            zero.to_csv(issues / f'{security.asset}_zero_volume_lineage.csv', index=False)
            parts.append(daily)
            summaries.append(summary)
            scans.append(dict(asset=security.asset, file=relative.as_posix(), **scan))
            # Checkpoint derived daily rows; an incomplete run remains manifest-flagged.
            daily.to_csv(OUT / f'{security.asset}_daily_checkpoint.csv', index=False)
            print(f'{security.asset}: {len(daily)} days; {summary["invalid_aggregation_days"]} invalid; {summary["zero_volume_rows"]} zero-volume rows', flush=True)
            del data, annotated
        except Exception as exc:
            failures.append(dict(asset=security.asset, reason=f'{type(exc).__name__}: {exc}'))
            print(f'{security.asset}: FAILED {exc}', flush=True)
    daily = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    summary = pd.DataFrame(summaries)
    daily.to_csv(OUT / 'selected_daily_ohlcv.csv', index=False)
    summary.to_csv(OUT / 'selected_daily_summary.csv', index=False)
    quality_cols = ['asset', 'asset_class', 'date', 'timezone', 'source', 'source_role', 'adjustment',
        'source_file', 'bars_observed', 'first_timestamp', 'last_timestamp', 'max_gap_minutes'] + [f + '_rows' for f in FLAGS] + ['aggregation_valid', 'aggregation_failure_reason']
    quality = daily[quality_cols].copy()
    quality['gap_gt_one_minute_flag'] = daily.max_gap_minutes.gt(1)
    quality['provider_zero_volume_discrepancy'] = daily.zero_volume_rows.gt(0)
    quality.to_csv(OUT / 'selected_daily_quality_audit.csv', index=False)
    pd.DataFrame(scans).to_csv(OUT / 'file_scan_audit.csv', index=False)
    pd.DataFrame(failures, columns=['asset', 'reason']).to_csv(OUT / 'failures.csv', index=False)
    assert hashlib.sha256(selected_path.read_bytes()).hexdigest() == input_hash
    report = '# Selected local daily validation: 2015-01-01 through 2025-12-31\n\n'
    report += 'Observed asset-days only; 09:30 <= America/New_York local time < 16:00. Existing split+dividend adjusted files, read-only. No missing bars/days filled, no quality exclusions, no Bloomberg equivalence assumed. First Rate Data; local_daily_validation; split_and_dividend_adjusted.\n\n'
    report += markdown(summary[['asset', 'asset_class', 'first_asset_day', 'last_asset_day', 'observed_asset_days', 'median_bars_per_asset_day', 'days_with_gaps_gt_1_minute', 'days_with_zero_volume_rows', 'invalid_aggregation_days']]) + '\n\n'
    report += 'Gaps are measured between adjacent observed within-session timestamps, not across overnight/day boundaries. They do not infer missing holidays or bars at session endpoints. Duplicate/invalid rows remain counted and flag their observed day as invalid. Undefined OHLCV remains undefined rather than partially reconstructed.\n\n'
    review = summary.loc[summary.coverage_review_required]
    report += 'Coverage comparison with original selection audit (raw-date endpoints versus observed RTH days):\n\n' + (markdown(review[['asset', 'first_date_difference_calendar_days', 'last_date_difference_calendar_days', 'observed_2024_days_difference']]) if len(review) else 'All 18 session endpoints and 2024 observed-day counts match the selection audit.') + '\n\n'
    jsml = summary.loc[summary.asset.eq('JSML')].iloc[0]
    report += f'JSML: {jsml.zero_volume_rows} retained zero-volume rows over the study span; {jsml.zero_volume_rows_2024} in 2024, compared with selection-audit count {jsml.selection_audit_zero_volume_rows_2024}. See read_audits/JSML_zero_volume_lineage.csv for source line/timestamp flags. Provider documentation says zero-volume bars are omitted; observed rows contradict that policy and are preserved.\n\n'
    report += 'Identity remains provisional: especially OCX -> IMDX stable-ID stitching, BIDU US ADS line/currency/depositary ratio, FCPT common REIT equity. Existing partial coverage remains retained; aggregates do not establish economic-security continuity. Reference template returned fields are blank, identifiers remain non-executable placeholders, and BDP is not historical identity proof.\n\n'
    report += 'No Bloomberg request or estimator/benchmark performance calculation. Licensed shared raw files are referenced, not copied. Delivery instructions are in ../final_delivery_note.md.\n'
    (OUT / 'selected_daily_report.md').write_text(report, encoding='utf-8')
    (OUT / 'run_manifest.json').write_text(json.dumps(dict(status='complete' if not failures and len(summary) == 18 else 'incomplete', selected_input_sha256=input_hash, source_root=str(root), study_start='2015-01-01', study_end='2025-12-31', selected_assets=len(selected), completed_assets=len(summary), observed_asset_days=len(daily), approximate_bytes_scanned=sum(s['raw_size_bytes'] for s in scans), runtime_seconds=time.perf_counter()-started, raw_provider_writes=0, inserted_bars=0, inserted_days=0, raw_data_copies=0, bloomberg_requests=0, failures=failures, source_fingerprint_method='size and nanosecond mtime before/after read; not a full content hash'), indent=2), encoding='utf-8')
    if failures:
        raise RuntimeError('Incomplete materialization; see failures.csv')
    for security in selected.itertuples():
        (OUT / f'{security.asset}_daily_checkpoint.csv').unlink(missing_ok=True)
    print(summary.to_string(index=False), flush=True)


if __name__ == '__main__':
    run()
