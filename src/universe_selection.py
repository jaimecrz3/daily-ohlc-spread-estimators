"""Descriptive 2024 liquidity-stratified candidate universe, never final selection.

Run: python -B src/universe_selection.py [--bare-crypto-usd-confirmed]
Only metadata/filenames, observed dates, close and volume drive selection.
No benchmark imports, benchmark output reads, or estimator values are used.
Metadata screen precedes a deterministic 60-stock/60-ETF file-size pre-screen.
Only pool members receive full-file bounded reads; no sorted-file assumption.
"""
from __future__ import annotations

import argparse
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
    from .data_io import asset_metadata, intraday_root, is_timestamp
    from .eda_diagnostics import parse_chunk
    from .session_rules import assign_primary_session
except ImportError:
    from data_io import asset_metadata, intraday_root, is_timestamp
    from eda_diagnostics import parse_chunk
    from session_rules import assign_primary_session

CLASSES = ('stocks', 'etfs', 'cryptos')
METADATA_FILES = {'stocks': 'stock_ticker_dates_listing.txt', 'etfs': 'etf_ticker_dates_listing.txt', 'cryptos': 'crypto_ticker_dates_listing.txt'}
STUDY_START, STUDY_END = pd.Timestamp('2015-01-01'), pd.Timestamp('2025-12-31')
CAL_START, CAL_END = pd.Timestamp('2024-01-01'), pd.Timestamp('2025-01-01')
MIN_DAYS = {'stocks': 200, 'etfs': 200, 'cryptos': 300}
OUT = Path(__file__).resolve().parents[1] / 'outputs/diagnostics/universe_selection'


def crypto_quote_currency(ticker: str, bare_usd_confirmed: bool = False) -> str:
    """Bare symbols require explicit provider/user USD confirmation."""
    if '-' in ticker:
        return ticker.rsplit('-', 1)[1]
    return 'USD' if bare_usd_confirmed else 'UNRESOLVED'


def ticker_review(ticker: str, name: str = '') -> tuple[str, str]:
    """Conservative naming rules; a trailing W/U/R/P alone never suffices.

    Explicit delimited security suffixes or provider label plus matching suffix
    are evidence. Share classes (e.g. BRK-B), ADRs, and uncertain five-letter
    tickers stay candidates for later reference validation.
    """
    if re.search(r'(?:[.\-^](?:WS?|WT|U|UN|R|RT|P[A-Z]?|PR[A-Z]?))$', ticker):
        return 'non_standard_security_form', 'explicit delimited warrant/unit/right/preferred suffix'
    lower = name.lower()
    if ticker.endswith('P') and re.search(r'\bpreference shares?\b', lower):
        return 'non_standard_security_form', 'provider preference-share label and matching P suffix'
    for suffix, term in [('W', 'warrant'), ('U', 'unit'), ('R', 'rights'), ('P', 'preferred')]:
        if ticker.endswith(suffix) and re.search(r'\b' + term + r's?\b', lower):
            return 'non_standard_security_form', f'provider label and matching {suffix} suffix'
    return '', 'pending Bloomberg/reference validation; naming alone does not establish security type'


def history_eligible(first, last, asset_class: str) -> bool:
    """At least N elapsed calendar years, clipped to study dates (inclusive).

    This measures observed endpoint span, never continuous-bar completeness.
    Observed calendar years and gaps are also reported for scanned candidates.
    """
    if pd.isna(first) or pd.isna(last):
        return False
    lo, hi = max(pd.Timestamp(first), STUDY_START), min(pd.Timestamp(last), STUDY_END)
    years = 3 if asset_class == 'cryptos' else 5
    return hi + pd.Timedelta(days=1) >= lo + pd.DateOffset(years=years)


def deterministic_prescreen(eligible: pd.DataFrame, target: int = 60) -> pd.DataFrame:
    """Evenly spaced ascending file-size order; stable filename tie break."""
    if target < 1:
        raise ValueError('target must be positive')
    ordered = eligible.sort_values(['file_size_bytes', 'asset', 'file'], kind='stable').reset_index(drop=True)
    n = len(ordered)
    positions = np.rint(np.linspace(0, n - 1, min(target, n))).astype(int) if n else []
    chosen = ordered.iloc[positions].copy()
    chosen['prescreen_position'] = positions
    return chosen


def inventory(root: Path, bare_usd_confirmed: bool):
    records, metadata_audit = [], []
    for cls in CLASSES:
        path = root / '_documentation/.archive' / METADATA_FILES[cls]
        payload = path.read_bytes()
        meta = pd.read_csv(path, dtype=str, keep_default_na=False)
        required = {'Ticker', 'Name', 'First Date', 'Last Date'}
        if not required.issubset(meta.columns):
            raise ValueError(f'Unexpected metadata schema: {path}')
        metadata_audit.append(dict(asset_class=cls, file=str(path), bytes_read=len(payload), sha256=hashlib.sha256(payload).hexdigest(), rows=len(meta)))
        groups = {ticker: group for ticker, group in meta.groupby('Ticker', sort=False)}
        suffix = '_full_1min.txt' if cls == 'cryptos' else '_full_1min_adjsplitdiv.txt'
        paths = {p.name[:-len(suffix)]: p for p in (root / cls).glob('*' + suffix)}
        for ticker in sorted(set(paths) | set(groups)):
            file_path = paths.get(ticker)
            group = groups.get(ticker)
            reasons = []
            name, first, last, intervals = '', pd.NaT, pd.NaT, []
            if group is None:
                reasons.append('missing_provider_date_metadata')
            else:
                name = ' | '.join(sorted(set(v for v in group.Name if v)))
                starts = pd.to_datetime(group['First Date'], format='%Y-%m-%d', errors='coerce')
                ends = pd.to_datetime(group['Last Date'], format='%Y-%m-%d', errors='coerce')
                if starts.isna().any() or ends.isna().any() or (starts > ends).any():
                    reasons.append('invalid_provider_date_metadata')
                else:
                    first, last = starts.min(), ends.max()
                    intervals = list(zip(starts, ends))
                    if not any(a < CAL_END and b >= CAL_START for a, b in intervals):
                        reasons.append('no_2024_metadata_coverage')
                    if not history_eligible(first, last, cls):
                        reasons.append('insufficient_history_span')
            size, mtime = 0, 0
            if file_path is None:
                reasons.append('official_local_file_missing')
            else:
                stat = file_path.stat()
                size, mtime = stat.st_size, stat.st_mtime_ns
                if not size:
                    reasons.append('empty_local_file')
            naming_reason, review = ticker_review(ticker, name) if cls != 'cryptos' else ('', 'crypto currency/name mapping validation')
            if naming_reason:
                reasons.append(naming_reason)
            quote = crypto_quote_currency(ticker, bare_usd_confirmed) if cls == 'cryptos' else 'USD (US provider class; reference validation pending)'
            if cls == 'cryptos' and quote != 'USD':
                reasons.append('quote_currency_unresolved' if quote == 'UNRESOLVED' else 'non_usd_crypto_cross_pair')
            records.append(dict(asset=ticker, asset_class=cls, file=f'{cls}/{ticker}{suffix}',
                local_file_exists=file_path is not None, file_size_bytes=size, raw_mtime_ns=mtime,
                provider_name=name, provider_first_date=first, provider_last_date=last,
                provider_intervals_json=json.dumps([(str(a.date()), str(b.date())) for a, b in intervals]),
                metadata_history_basis='observed endpoint span, not continuous coverage; pool verified from raw dates',
                reference_validation=review, quote_currency=quote,
                metadata_eligible=not reasons, exclusion_reasons=';'.join(reasons)))
    return pd.DataFrame(records), metadata_audit


def scan_candidate(path: Path, problems: Path, flags_path: Path):
    """Bounded full-file date scan of pool member; parse only 2024 OHLCV.

    Date-prefix coverage outside 2024 is diagnostic only. No sorted-file
    assumptions or early stopping; sparse years are observed, not synthesized.
    """
    before = path.stat()
    started = time.perf_counter()
    dates, pieces = set(), []
    counts = Counter(bytes_scanned=0, raw_rows_scanned=0, invalid_date_prefix_rows=0,
                     unassignable_2024_timestamp_rows=0, raw_2024_rows=0)
    with path.open('rb') as stream:
        pilot = list(islice(stream, 10))
    counts['pilot_bytes_read'] = sum(map(len, pilot))
    if not pilot or any(len(line.decode('utf-8-sig').strip().split(',')) != 6 or not is_timestamp(line.decode('utf-8-sig')[:19]) for line in pilot):
        raise ValueError('Initial ten-row pilot schema/timestamp validation failed')
    with problems.open('w', encoding='utf-8', newline='') as bad:
        writer = csv.writer(bad)
        writer.writerow(['raw_line_number', 'raw_text', 'reason'])
        with path.open('rb') as stream:
            pending = b''
            offset = 1
            while True:
                block = stream.read(8 * 1024 * 1024)
                counts['bytes_scanned'] += len(block)
                if not block and not pending:
                    break
                merged = pending + block
                lines = merged.split(b'\n')
                pending = lines.pop() if block else b''
                if not block and lines and lines[-1] == b'':
                    lines.pop()
                prefixes = {line[:10] for line in lines}
                valid_dates = {}
                for prefix in prefixes:
                    try:
                        text = prefix.decode('ascii')
                        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
                            raise ValueError('bad date')
                        date = pd.Timestamp(text)
                        valid_dates[prefix] = date
                    except (ValueError, UnicodeError):
                        continue
                dates.update(date for date in valid_dates.values() if STUDY_START <= date <= STUDY_END)
                selected, numbers = [], []
                for i, line in enumerate(lines):
                    prefix = line[:10]
                    if prefix not in valid_dates:
                        counts['invalid_date_prefix_rows'] += 1
                        writer.writerow([offset + i, line.decode('utf-8', errors='replace').rstrip('\r'), 'invalid_date_prefix'])
                    elif line.startswith(b'2024-'):
                        selected.append(line.decode('utf-8-sig'))
                        numbers.append(offset + i)
                counts['raw_rows_scanned'] += len(lines)
                if selected:
                    _, parsed = parse_chunk(selected, 1)
                    parsed.index = pd.Index(numbers, name='raw_line_number')
                    counts['raw_2024_rows'] += len(parsed)
                    invalid = parsed.timestamp.isna()
                    counts['unassignable_2024_timestamp_rows'] += int(invalid.sum())
                    for number in parsed.index[invalid]:
                        writer.writerow([number, selected[numbers.index(number)].rstrip('\r'), 'unassignable_2024_timestamp'])
                    pieces.append(parsed)
                offset += len(lines)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Source changed during read')
    scan = dict(counts, scan_seconds=time.perf_counter() - started,
                first_observed_study_date=min(dates) if dates else pd.NaT,
                last_observed_study_date=max(dates) if dates else pd.NaT,
                observed_study_years=len({d.year for d in dates}),
                observed_study_dates=len(dates))
    if not pieces:
        data = pd.DataFrame({'timestamp': pd.Series(dtype='datetime64[ns]'),
                             'close': pd.Series(dtype=float), 'volume': pd.Series(dtype=float)})
        return data, scan
    data = pd.concat(pieces)
    data['duplicate_timestamp'] = data.timestamp.notna() & data.timestamp.duplicated(keep=False)
    quality_cols = ['missing_value', 'non_numeric', 'non_finite', 'invalid_ohlc', 'zero_volume', 'negative_volume', 'malformed_columns', 'duplicate_timestamp']
    data.loc[data[quality_cols].any(axis=1)].to_csv(flags_path, index=True)
    return data, scan


def daily_liquidity(data: pd.DataFrame, asset_class: str) -> pd.DataFrame:
    """Sum close*volume in frozen 2024 sessions, observed days only.

    Zero-volume and duplicate rows are retained; duplicates contribute as raw
    observations and are flagged. Nonfinite/nonpositive close, negative/nonfinite
    volume or malformed rows make that day's notional undefined, never a partial
    zero-filled sum. Other OHLC/parser flags stay diagnostic (close/volume only).
    """
    # Allowlist makes benchmark/estimator columns irrelevant and absent in output.
    flags = ['zero_volume', 'missing_value', 'non_numeric', 'non_finite', 'invalid_ohlc', 'negative_volume', 'malformed_columns', 'duplicate_timestamp']
    columns = ['timestamp', 'close', 'volume'] + [f for f in flags if f in data]
    assigned = assign_primary_session(data[columns], asset_class)
    wall = assigned.timestamp_local.dt.tz_localize(None)
    d = assigned.loc[assigned.primary_session_retained & wall.ge(CAL_START) & wall.lt(CAL_END)].copy()
    close, volume = pd.to_numeric(d.close, errors='coerce'), pd.to_numeric(d.volume, errors='coerce')
    with np.errstate(over='ignore', invalid='ignore'):
        notional = close * volume
    invalid = ~np.isfinite(close) | close.le(0) | ~np.isfinite(volume) | volume.lt(0) | ~np.isfinite(notional)
    if 'malformed_columns' in d:
        invalid |= d.malformed_columns
    d['notional'] = notional
    d['numeric_volume'] = volume
    d['invalid_notional'] = invalid
    d['duplicate_timestamp'] = d.timestamp_local.duplicated(keep=False) | d.get('duplicate_timestamp', False)
    records = []
    for day, group in d.groupby('session_day', sort=True):
        valid_day = not group.invalid_notional.any()
        records.append(dict(date=day, bars_observed=len(group),
            daily_volume=group.numeric_volume.sum() if valid_day else np.nan,
            daily_dollar_notional_volume=group.notional.sum() if valid_day else np.nan,
            zero_volume_rows=int(group.zero_volume.sum()), invalid_notional_rows=int(group.invalid_notional.sum()),
            duplicate_timestamp_rows=int(group.duplicate_timestamp.sum()),
            **{f + '_rows': int(group[f].sum()) if f in group else 0 for f in flags if f not in {'zero_volume', 'duplicate_timestamp'}}))
    return pd.DataFrame(records, columns=['date', 'bars_observed', 'daily_volume', 'daily_dollar_notional_volume', 'zero_volume_rows', 'invalid_notional_rows', 'duplicate_timestamp_rows'] + [f + '_rows' for f in flags if f not in {'zero_volume', 'duplicate_timestamp'}])


def liquidity_stats(daily: pd.DataFrame, asset_class: str) -> dict:
    n = len(daily)
    metric = daily.daily_dollar_notional_volume.median() if n else np.nan
    # Unknown totals must not silently alter the liquidity population.
    invalid_days = int(daily.daily_dollar_notional_volume.isna().sum()) if n else 0
    reason = 'insufficient_2024_session_days' if n < MIN_DAYS[asset_class] else ''
    if not reason and (invalid_days or not np.isfinite(metric)):
        reason = 'undefined_daily_liquidity_requires_review'
    return dict(observed_2024_days=n, first_observed_2024_date=daily.date.min() if n else pd.NaT,
        last_observed_2024_date=daily.date.max() if n else pd.NaT,
        median_bars_per_observed_day=daily.bars_observed.median() if n else np.nan,
        zero_volume_rows=int(daily.zero_volume_rows.sum()) if n else 0,
        median_daily_volume=daily.daily_volume.median() if n else np.nan,
        median_daily_dollar_notional_volume=metric, liquidity_measure=metric,
        invalid_notional_days=invalid_days,
        duplicate_timestamp_rows=int(daily.duplicate_timestamp_rows.sum()) if n else 0,
        passes_liquidity_days=n >= MIN_DAYS[asset_class], ranking_eligible=not reason,
        ranking_exclusion_reason=reason)


def assign_tiers(candidates: pd.DataFrame) -> pd.DataFrame:
    """Independent ascending rank tertiles; tied liquidity sorted by ticker.

    np.array_split puts remainder members in LOW then MEDIUM; counts differ
    by at most one. Same-value ties can span tiers; no absolute-class comparison.
    """
    allowed = ['asset', 'asset_class', 'file', 'observed_2024_days', 'first_observed_2024_date',
        'last_observed_2024_date', 'median_bars_per_observed_day', 'zero_volume_rows',
        'median_daily_volume', 'median_daily_dollar_notional_volume', 'liquidity_measure',
        'invalid_notional_days', 'duplicate_timestamp_rows', 'reference_validation', 'quote_currency']
    valid = candidates.loc[candidates.ranking_eligible, [c for c in allowed if c in candidates]].copy()
    pieces = []
    for _, group in valid.groupby('asset_class', sort=True):
        group = group.sort_values(['liquidity_measure', 'asset'], kind='stable').reset_index(drop=True)
        group['liquidity_rank'] = np.arange(1, len(group) + 1)
        group['liquidity_tier'] = ''
        for label, positions in zip(['LOW', 'MEDIUM', 'HIGH'], np.array_split(np.arange(len(group)), 3)):
            group.loc[positions, 'liquidity_tier'] = label
        pieces.append(group)
    return pd.concat(pieces, ignore_index=True) if pieces else valid.assign(liquidity_rank=pd.Series(dtype=int), liquidity_tier=pd.Series(dtype=str))


def tier_summary(ranking: pd.DataFrame) -> pd.DataFrame:
    records = []
    for cls in CLASSES:
        for tier in ['LOW', 'MEDIUM', 'HIGH']:
            group = ranking.loc[ranking.asset_class.eq(cls) & ranking.liquidity_tier.eq(tier)]
            records.append(dict(asset_class=cls, liquidity_tier=tier, assets=len(group),
                liquidity_min=group.liquidity_measure.min(), liquidity_max=group.liquidity_measure.max(),
                liquidity_median=group.liquidity_measure.median()))
    return pd.DataFrame(records)


def markdown(table: pd.DataFrame) -> str:
    lines = ['| ' + ' | '.join(table.columns) + ' |', '| ' + ' | '.join(['---'] * len(table.columns)) + ' |']
    for values in table.itertuples(index=False, name=None):
        lines.append('| ' + ' | '.join('NA' if pd.isna(v) else f'{v:,.2f}' if isinstance(v, float) else str(v).replace('|', '/') for v in values) + ' |')
    return '\n'.join(lines)


def write_review_diagnostics(out: Path = OUT):
    """Refresh review evidence from this run's pool/daily tables; no raw reads.

    Clearly distinguish provisional metadata eligibility from verified pool
    coverage. Missing metadata-listed files remain in the exclusion audit but
    are not counted as raw local candidate files.
    """
    eligible = pd.read_csv(out / 'eligible_assets.csv')
    scans = pd.read_csv(out / 'file_scan_audit.csv')
    scan_map = {(r.asset_class, r.asset): r for r in scans.itertuples()}
    statuses = []
    for row in eligible.itertuples():
        scan = scan_map.get((row.asset_class, row.asset))
        if scan is None:
            status = 'not_scanned' if not row.in_computational_pool else 'read_failure'
        elif not scan.raw_2024_rows:
            status = 'no_2024_raw_rows'
        elif not history_eligible(pd.to_datetime(scan.first_observed_study_date), pd.to_datetime(scan.last_observed_study_date), row.asset_class):
            status = 'insufficient_observed_history_span'
        else:
            status = 'verified_endpoint_span_and_2024_presence'
        statuses.append(status)
    eligible['raw_coverage_validation'] = statuses
    eligible.to_csv(out / 'eligible_assets.csv', index=False)
    pool = pd.read_csv(out / 'computational_candidate_pool.csv')
    parts = []
    for row in pool.itertuples():
        path = out / f'{row.asset_class}_{row.asset}_2024_daily_liquidity.csv'
        if path.exists():
            parts.append(pd.read_csv(path))
    quality = pd.DataFrame()
    if parts:
        daily = pd.concat(parts, ignore_index=True)
        daily['sparse_observed_days_le10_bars'] = daily.bars_observed.le(10).astype(int)
        columns = [c for c in daily if c.endswith('_rows')] + ['sparse_observed_days_le10_bars']
        quality = daily.groupby('asset_class')[columns].sum().reset_index()
        quality.to_csv(out / 'quality_summary.csv', index=False)
        zero = daily.groupby(['asset_class', 'asset']).zero_volume_rows.sum().reset_index()
        zero = zero.loc[zero.zero_volume_rows.gt(0)]
        zero.to_csv(out / 'zero_volume_discrepancy_summary.csv', index=False)
        appendix = ('\n\n2024 primary-session quality diagnostics (computed pool members only):\n\n'
                    + markdown(quality) + '\n\nObserved zero-volume rows, retained despite provider omission policy:\n\n'
                    + (markdown(zero) if len(zero) else 'None in this run.')
                    + '\n\nSparse-day counts are descriptive flags, not additional coverage exclusions. '
                    + 'The exclusion audit includes provider-listed files absent locally; these are not included in the raw-local-file counts. '
                    + 'eligible_assets.csv distinguishes metadata eligibility from verified pool coverage.\n')
        report_path = out / 'candidate_universe.md'
        text = report_path.read_text(encoding='utf-8').split('\n\n2024 primary-session quality diagnostics')[0]
        report_path.write_text(text + appendix, encoding='utf-8')
    return quality


def run(root: Path | None = None, out: Path = OUT, bare_usd_confirmed: bool = False):
    started = time.perf_counter()
    root = intraday_root() if root is None else Path(root)
    out.mkdir(parents=True, exist_ok=True)
    inv, metadata_audit = inventory(root, bare_usd_confirmed)
    inv.to_csv(out / 'file_inventory.csv', index=False)
    eligible = inv.loc[inv.metadata_eligible].copy()
    eligible['in_computational_pool'] = False
    pools = []
    for cls in CLASSES:
        group = eligible.loc[eligible.asset_class.eq(cls)]
        pool = group.sort_values('asset') if cls == 'cryptos' else deterministic_prescreen(group)
        pools.append(pool)
    pool = pd.concat(pools, ignore_index=True)
    keys = set(zip(pool.asset_class, pool.asset))
    eligible['in_computational_pool'] = [(c, a) in keys for c, a in zip(eligible.asset_class, eligible.asset)]
    eligible.to_csv(out / 'eligible_assets.csv', index=False)
    pool.to_csv(out / 'computational_candidate_pool.csv', index=False)
    excluded = [dict(asset=r.asset, asset_class=r.asset_class, file=r.file,
                     stage='metadata', reason=reason) for r in inv.itertuples()
                for reason in r.exclusion_reasons.split(';') if reason]
    scans, results, failures = [], [], []
    for i, row in enumerate(pool.to_dict('records'), 1):
        asset, cls = row['asset'], row['asset_class']
        print(f'[{i}/{len(pool)}] {cls}/{asset}: {row["file_size_bytes"] / 1e6:.1f} MB', flush=True)
        name = f'{cls}_{asset}'
        try:
            data, scan = scan_candidate(root / row['file'], out / f'{name}_read_problems.csv', out / f'{name}_flagged_rows.csv')
            scans.append(dict(asset=asset, asset_class=cls, **scan))
            if data.empty:
                excluded.append(dict(asset=asset, asset_class=cls, file=row['file'], stage='raw_coverage', reason='no_2024_raw_rows'))
                continue
            # Verify file dates after metadata pre-screen; no replacement/refill.
            if not history_eligible(scan['first_observed_study_date'], scan['last_observed_study_date'], cls):
                excluded.append(dict(asset=asset, asset_class=cls, file=row['file'], stage='raw_coverage', reason='insufficient_observed_history_span'))
                continue
            daily = daily_liquidity(data, cls)
            daily.insert(0, 'asset_class', cls)
            daily.insert(0, 'asset', asset)
            daily.to_csv(out / f'{name}_2024_daily_liquidity.csv', index=False)
            stats = liquidity_stats(daily, cls)
            results.append(dict(**row, **stats))
            if not stats['ranking_eligible']:
                excluded.append(dict(asset=asset, asset_class=cls, file=row['file'], stage='liquidity', reason=stats['ranking_exclusion_reason']))
            print(f'  {len(daily)} observed days; ranking eligible={stats["ranking_eligible"]}', flush=True)
            pd.DataFrame(scans).to_csv(out / 'file_scan_audit.csv', index=False)
        except Exception as exc:
            failures.append(dict(asset=asset, asset_class=cls, file=row['file'], error_type=type(exc).__name__, error=str(exc)))
            excluded.append(dict(asset=asset, asset_class=cls, file=row['file'], stage='read_failure', reason=type(exc).__name__ + ': ' + str(exc)))
            print(f'  FAILED: {exc}', flush=True)
    candidates = pd.DataFrame(results)
    if candidates.empty:
        candidates = pd.DataFrame(columns=['asset', 'asset_class', 'ranking_eligible', 'liquidity_measure', 'passes_liquidity_days'])
    candidates.to_csv(out / 'candidate_liquidity_diagnostics.csv', index=False)
    ranking = assign_tiers(candidates)
    summary = tier_summary(ranking)
    ranking.to_csv(out / 'liquidity_ranking.csv', index=False)
    summary.to_csv(out / 'liquidity_summary_by_class_and_tier.csv', index=False)
    excluded_table = pd.DataFrame(excluded, columns=['asset', 'asset_class', 'file', 'stage', 'reason'])
    excluded_table.to_csv(out / 'excluded_assets.csv', index=False)
    pd.DataFrame(failures, columns=['asset', 'asset_class', 'file', 'error_type', 'error']).to_csv(out / 'failures.csv', index=False)
    pd.DataFrame(scans).to_csv(out / 'file_scan_audit.csv', index=False)
    counts = []
    for cls in CLASSES:
        ranked = ranking.loc[ranking.asset_class.eq(cls)]
        computed = candidates.loc[candidates.asset_class.eq(cls)]
        counts.append(dict(asset_class=cls, raw_candidate_files=int((inv.asset_class.eq(cls) & inv.local_file_exists).sum()),
            metadata_coverage_eligible=int(eligible.asset_class.eq(cls).sum()), computational_pool=int(pool.asset_class.eq(cls).sum()),
            successfully_computed=len(computed), passes_2024_day_requirement=int(computed.passes_liquidity_days.sum()),
            ranked_assets=len(ranked), **{t: int(ranked.liquidity_tier.eq(t).sum()) for t in ['LOW', 'MEDIUM', 'HIGH']}))
    counts = pd.DataFrame(counts)
    counts.to_csv(out / 'stage_counts.csv', index=False)
    exclusions_summary = excluded_table.groupby(['asset_class', 'stage', 'reason']).agg(assets=('asset', 'nunique')).reset_index()
    exclusions_summary.to_csv(out / 'exclusion_reason_summary.csv', index=False)
    elapsed = time.perf_counter() - started
    scanned = sum(s['bytes_scanned'] + s['pilot_bytes_read'] for s in scans) + sum(m['bytes_read'] for m in metadata_audit)
    manifest = dict(study_window=['2015-01-01', '2025-12-31'], calibration_window=['2024-01-01', '2024-12-31'],
        source_root=str(root), metadata=metadata_audit, bare_crypto_usd_confirmed=bare_usd_confirmed,
        raw_bytes_read_accounted=scanned, runtime_seconds=elapsed, failures=failures,
        history_rule='>=5 (equity) or >=3 (crypto) elapsed calendar years of observed endpoint span within study window; not continuous coverage',
        prescreen='sort(file_size_bytes,asset,file); rint(linspace(0,n-1,min(60,n))); file size is not liquidity; no refill after exclusions',
        tier_rule='within-class ascending median close*volume, ticker tie break; array_split into thirds, remainder to LOW then MEDIUM',
        daily_rule='retained session rows only; no synthesized days; zero-volume/duplicates retained and flagged; nonfinite/invalid close-volume totals left undefined for review',
        undefined_liquidity_policy='assets with unknown daily totals remain diagnostics but cannot enter a valid ranking',
        adjusted_equity_notional='close*volume from existing split+dividend adjusted files; descriptive adjusted-price notional proxy, not reconstructed actual traded dollar volume',
        scope='local provider archive candidates; no assumption of point-in-time completeness or absence of survivorship bias; reference types/currency validation pending',
        forbidden_selection_inputs_used=False, benchmark_status='candidate primary; not a universe criterion',
        pending=['futures contract-roll methodology', 'FX official shared folder inaccessible', 'final fixed securities per tier'], inserted_minute_bars=0,
        outside_calibration_quality_scope='date prefixes only; full OHLCV flags for 2024; endpoint span does not guarantee complete history')
    (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2, default=str), encoding='utf-8')
    report = ('# Candidate universe: 2015–2025 history; 2024 liquidity calibration\n\n'
        'Roll is a candidate primary benchmark and has no role in universe selection. No final 3/6/9 securities selected.\n\n'
        + markdown(counts) + '\n\nLiquidity ranges: medians of observed daily close × volume, within each asset class (USD/notional USD).\n\n'
        + markdown(summary) + '\n\nExclusions (each asset can have multiple reasons):\n\n' + markdown(exclusions_summary)
        + f'\n\nRuntime: {elapsed / 60:.2f} minutes. Accounted bytes read: {scanned:,} ({scanned / 1e9:.3f} GB). Full histories scanned only for computational pool members, after ten-row pilot reads. Failed reads can make byte accounting a lower bound.\n'
        + '\nFile size is an efficient pre-screen only, never the final liquidity measure. Tiers are independent ascending rank thirds; ticker breaks ties and remainders go to LOW then MEDIUM. No automatic pool refill.\n'
        + '\nHistory eligibility uses at least five/three elapsed calendar years of observed endpoint span clipped to the study; endpoints do not guarantee continuous coverage. Metadata eligibility is provisional until pool raw-date validation. Observed dates/years and sparse bars are retained. No missing days or minute bars synthesized.\n'
        + '\nZero-volume rows and duplicates are retained and flagged. Unknown daily close-volume totals remain NaN and require review before ranking. Naming uncertainty remains pending Bloomberg/reference validation; no unsupported security-type guesses.\n'
        + '\nEquity files are split+dividend adjusted: close × volume is an adjusted-price notional proxy, not reconstructed actual historical dollar turnover. The archive is not a certified point-in-time complete security master; provider inclusion and survivorship limitations remain.\n'
        + f'\nBare crypto ticker USD confirmation: {bare_usd_confirmed}. Explicit non-USD cross-pairs are excluded; unknown currencies remain pending. Futures contract-roll methodology and FX access remain pending. No estimators calculated.\n'
        + '\nPer-asset exclusions: excluded_assets.csv. All metadata-eligible files: eligible_assets.csv. Per-day diagnostics and raw quality flags are saved alongside the ranking.\n')
    (out / 'candidate_universe.md').write_text(report, encoding='utf-8')
    write_review_diagnostics(out)
    print(counts.to_string(index=False), flush=True)
    print(summary.to_string(index=False), flush=True)
    if failures:
        raise RuntimeError('Some candidates failed; see failures.csv. Partial results retained.')
    return counts, ranking, summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bare-crypto-usd-confirmed', action='store_true', help='Use only after provider/user confirmation that bare crypto files are USD quoted')
    args = parser.parse_args()
    run(bare_usd_confirmed=args.bare_crypto_usd_confirmed)
