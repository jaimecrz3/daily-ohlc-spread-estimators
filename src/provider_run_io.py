"""Step17 bounded official minute reads and unchanged Roll-kernel integration.

All observation-level caches, staging and hand-audit inputs are under ignored
data/analytic/provider_run. No performance calculations or price substitution.
"""
from pathlib import Path
from itertools import islice
from collections import Counter
import hashlib
import json
import time

import numpy as np
import pandas as pd
import yaml

from benchmark import build_roll_benchmark, MIN_ROLL_PAIRS, COVARIANCE_DDOF
from bloomberg_io import sha256, verify_hashes, require_verified
from data_io import intraday_root
from eda_diagnostics import parse_chunk
from session_rules import assign_primary_session
from futures_roll import parse_provider_calendar, contract_file
from futures_historical_sessions import historical_configs

PROJECT = Path(__file__).resolve().parents[1]
DIAG = PROJECT/'outputs/diagnostics'
DESIGN = DIAG/'design_freeze'
FINAL = DIAG/'final_universe'
ANALYTIC = PROJECT/'data/analytic/provider_run'
EXPECTED = {'stocks': 14499, 'etfs': 8649, 'futures': 2331, 'crypto': 12753}
PARSER_FLAGS = ['missing_value','non_numeric','non_finite','invalid_ohlc','zero_volume',
                'negative_volume','malformed_columns','duplicate_timestamp']


def roll_interface_unchanged():
    """Prove the only Roll source change is the optional session-registry wiring."""
    original = (PROJECT/'src/benchmark.py').read_text(encoding='utf-8')
    original = original.replace('                         futures_sessions=None,\n', '')
    original = original.replace(
        "    annotated = assign_primary_session(data, asset_class, futures_root=futures_root,\n                                       futures_sessions=futures_sessions).reset_index(names='source_row')",
        "    annotated = assign_primary_session(data, asset_class, futures_root=futures_root).reset_index(names='source_row')")
    saved = json.loads((DIAG/'benchmark_freeze/run_manifest.json').read_text())
    return hashlib.sha256(original.encode()).hexdigest() == saved['code_sha256']['src/benchmark.py']


def verify_frozen():
    for folder in ['design_freeze','estimator_freeze','statistical_freeze']:
        manifest = json.loads((DIAG/folder/'run_manifest.json').read_text(encoding='utf-8'))
        for name, digest in manifest['output_sha256'].items():
            assert sha256(DIAG/folder/name) == digest, 'Frozen artifact changed: '+folder+'/'+name
        for name, digest in manifest.get('protected_sha256', {}).items():
            assert sha256(PROJECT/name) == digest, 'Protected prior artifact changed: '+name
    global_spec = yaml.safe_load((DESIGN/'global_design_final_spec.yaml').read_text())
    for ref in global_spec['frozen_spec_references'].values():
        assert sha256(PROJECT/ref['path']) == ref['sha256']
    stat = yaml.safe_load((DIAG/'statistical_freeze/primary_weighting_spec.yaml').read_text())
    assert stat['status'] == 'FROZEN_FOR_PRIMARY_PROVIDER_RUN'
    assert MIN_ROLL_PAIRS == 2 and COVARIANCE_DDOF == 1 and roll_interface_unchanged()
    raw, _ = verify_hashes(PROJECT/'data/raw_bloomberg'); require_verified(raw)
    return global_spec


def frozen_design():
    global_spec = yaml.safe_load((DESIGN/'global_design_final_spec.yaml').read_text())
    path = DESIGN/'design_eligible_asset_days.csv'
    digest = json.loads((DESIGN/'run_manifest.json').read_text())['output_sha256'][path.name]
    assert sha256(path) == digest
    data = pd.read_csv(path)
    assert len(data) == 38232 and data.design_eligible.all()
    assert not data.duplicated(['asset_class','asset','date']).any()
    assert data.groupby('asset_class').size().to_dict() == EXPECTED
    for cls in EXPECTED:
        group = data.loc[data.asset_class.eq(cls)]
        assert set(group.asset) == set(global_spec['selected_assets_by_class'][cls])
        assert group.groupby('date').asset.nunique().eq(9).all()
        for tier, names in global_spec['liquidity_tiers'][cls].items():
            assert set(group.loc[group.liquidity_tier.eq(tier),'asset']) == set(names)
    return data


def fixed_audit_keys(design):
    """One sorted-key midpoint per class plus first LOW stock midpoint; no values."""
    keys = []
    for cls in EXPECTED:
        group = design.loc[design.asset_class.eq(cls)].sort_values(['asset','date'])
        row = group.iloc[len(group)//2]
        keys.append((cls, row.asset, row.date))
    group = design.loc[design.asset_class.eq('stocks') & design.liquidity_tier.eq('LOW')]
    asset = sorted(group.asset.unique())[0]
    group = group.loc[group.asset.eq(asset)].sort_values('date')
    keys.append(('stocks', asset, group.iloc[len(group)//2].date))
    return keys


def configs():
    mapping = pd.read_csv(FINAL/'futures_final/provider_root_mapping.csv')
    return historical_configs(mapping)[0]


def invoke_roll(bars, cls, asset, registry=None):
    return build_roll_benchmark(bars, asset, 'cryptos' if cls=='crypto' else cls,
        futures_root=asset if cls=='futures' else None,
        futures_sessions=registry if cls=='futures' else None)


def scan_partitions(path, cls, asset, selected_dates, capture_dates, stage, registry=None, code=None):
    """Full-file timestamp scan with strict parsing; partition only selected days.

    Handles unsorted files/chunks, preserves physical order for duplicates, and
    hashes source bytes. Every raw read is rb/r, never a raw write.
    """
    before = path.stat(); digest = hashlib.sha256(); counts = Counter()
    stage.mkdir(parents=True, exist_ok=True)
    if list(stage.glob('*.pkl')): raise ValueError('Inspect unfinished staging before retry: '+str(stage))
    with path.open('r', encoding='utf-8-sig') as stream: pilot = list(islice(stream, 10))
    if not pilot or any(len(line.strip().split(',')) != 6 for line in pilot):
        raise ValueError('Small official minute-file pilot failed')
    wanted = set(selected_dates) | set(capture_dates)
    lo, hi = pd.Timestamp(min(wanted)), pd.Timestamp(max(wanted))+pd.Timedelta(days=1)
    if cls=='futures': lo -= pd.Timedelta(days=1)
    partitions = {}; capture = []
    issue = stage/'unassignable_timestamps.csv'
    with issue.open('w', encoding='utf-8') as failures:
        failures.write('raw_line_number,reason\n')
        with path.open('rb') as stream:
            offset = 1; part = 0
            while raw := list(islice(stream, 100000)):
                for line in raw: digest.update(line)
                lines = [line.decode('utf-8-sig') for line in raw]
                text = pd.Series([line.split(',',1)[0].strip() for line in lines])
                ts = pd.to_datetime(text, format='%Y-%m-%d %H:%M:%S', errors='coerce')
                ts = ts.where(text.str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'))
                counts['raw_rows_scanned'] += len(raw)
                counts['unassignable_timestamp_rows'] += int(ts.isna().sum())
                for position in np.flatnonzero(ts.isna()):
                    failures.write(f'{offset+int(position)},unassignable_timestamp\n')
                positions = np.flatnonzero(ts.ge(lo) & ts.lt(hi))
                if len(positions):
                    _, parsed = parse_chunk([lines[p] for p in positions], 1)
                    parsed.index = pd.Index(offset+positions, name='raw_line_number')
                    assigned = assign_primary_session(parsed, 'cryptos' if cls=='crypto' else cls,
                        futures_root=asset if cls=='futures' else None, futures_sessions=registry)
                    labels = assigned.session_day.astype(str)
                    keep = assigned.primary_session_retained & labels.isin(wanted)
                    counts['retained_wanted_bars'] += int(keep.sum())
                    selected = parsed.loc[keep].copy()
                    selected['session_label'] = labels.loc[keep]
                    if cls=='futures':
                        selected['selected_contract'] = code; selected['source_contract'] = code
                    cap = selected.loc[selected.session_label.isin(capture_dates)].copy()
                    if len(cap): capture.append(cap)
                    selected = selected.loc[selected.session_label.isin(selected_dates)]
                    for year, group in selected.groupby(selected.session_label.str[:4], sort=True):
                        file = stage/f'{year}_{part:06d}.pkl'; group.to_pickle(file)
                        partitions.setdefault(year, []).append(file)
                offset += len(lines); part += 1
    after = path.stat()
    assert (before.st_size,before.st_mtime_ns) == (after.st_size,after.st_mtime_ns), 'Raw file changed'
    scan = dict(file_name=path.name, asset_class=cls, asset=asset, sha256=digest.hexdigest(),
        size_bytes=before.st_size, mtime_ns=before.st_mtime_ns, **dict(counts))
    if counts['unassignable_timestamp_rows']:
        raise ValueError('Unassignable source timestamps require review; no silent exclusions')
    return partitions, capture, scan


def calculate_asset(cls, asset, dates, capture_dates):
    started = time.perf_counter(); base = intraday_root(); registry = configs() if cls=='futures' else None
    source_tasks = []
    if cls=='futures':
        calendar_path = base/'futures'/f'{asset}_continuous_contract_dates.txt'
        expected = pd.read_csv(FINAL/'futures_final/historical/provider_mapping_hashes.csv')
        assert sha256(calendar_path) == expected.set_index('provider_root').loc[asset,'sha256']
        calendar = parse_provider_calendar(calendar_path)
        lookup = calendar.assign(date=calendar.provider_mapping_date.dt.strftime('%Y-%m-%d')).set_index('date')
        daily = pd.read_csv(FINAL/f'futures_final/historical/{asset}_historical_daily_ohlcv.csv')
        saved = daily.set_index('date')
        selected = lookup.loc[dates, 'selected_contract']
        assert selected.eq(saved.loc[dates,'selected_contract']).all(), 'Provider mapping changed'
        for code in sorted(selected.unique()):
            assigned = sorted(selected.index[selected.eq(code)])
            source_tasks.append((contract_file(base/'futures', asset, code, allowed_roots=registry), assigned,
                                 sorted(set(capture_dates)&set(assigned)), code))
    else:
        name = f'{asset}_full_1min.txt' if cls=='crypto' else f'{asset}_full_1min_adjsplitdiv.txt'
        source_tasks.append((base/('cryptos' if cls=='crypto' else cls)/name, dates, capture_dates, None))
    scans = []; summaries = []; captures = []
    for path, selected_dates, cap_dates, code in source_tasks:
        print(f'Scan {cls}/{asset}: {path.name}', flush=True)
        stage = ANALYTIC/'staging'/f'{cls}_{asset}'/(code or 'spot')
        partitions, cap, scan = scan_partitions(path, cls, asset, selected_dates, cap_dates, stage, registry, code)
        if cls=='crypto':
            known = pd.read_csv(FINAL/'crypto_final/historical/file_scan_audit.csv').set_index('asset')
            assert scan['sha256'] == known.loc[asset,'sha256'], 'Crypto raw source changed since certification'
        if cls=='futures':
            known = pd.read_csv(FINAL/'futures_final/historical/file_scan_audit.csv').set_index('file_name')
            assert scan['sha256'] == known.loc[path.name,'sha256'], 'Contract source changed since certification'
        if cls in ['stocks','etfs']:
            known = pd.read_csv(FINAL/'local_daily_validation/file_scan_audit.csv').set_index('asset').loc[asset]
            assert (scan['size_bytes'],scan['mtime_ns']) == (known.raw_size_bytes,known.raw_mtime_ns)
        scans.append(scan); captures.extend(cap)
        for year, files in sorted(partitions.items()):
            bars = pd.concat([pd.read_pickle(p) for p in files])
            print(f'Roll {cls}/{asset}: {year}, {len(bars):,} physical bars', flush=True)
            result = invoke_roll(bars, cls, asset, registry)
            result['date'] = result.date.astype(str)
            assert set(result.date) == set(bars.session_label)
            summaries.append(result)
            del bars
            for p in files:
                assert p.resolve().parent == stage.resolve(); p.unlink()
    result = pd.concat(summaries, ignore_index=True).sort_values('date')
    assert set(result.date) == set(dates) and len(result)==len(dates), 'Observed Roll dates differ from design'
    assert not result.date.duplicated().any()
    return result, pd.concat(captures) if captures else pd.DataFrame(), scans, time.perf_counter()-started


def run_benchmarks():
    spec = verify_frozen(); design = frozen_design()
    ANALYTIC.mkdir(parents=True, exist_ok=True)
    capture_keys = fixed_audit_keys(design)
    from estimator_windows import load_reference_grid
    package_key = {name:sha256(PROJECT/'src'/name) for name in ['provider_run_io.py','benchmark.py','session_rules.py','eda_diagnostics.py']}
    package_key['global_design'] = sha256(DESIGN/'global_design_final_spec.yaml')
    for cls in EXPECTED:
        grid = load_reference_grid(cls).strftime('%Y-%m-%d').tolist()
        for asset in spec['selected_assets_by_class'][cls]:
            dates = sorted(design.loc[design.asset_class.eq(cls)&design.asset.eq(asset),'date'])
            cap = set()
            for c, a, day in capture_keys:
                if (c,a)==(cls,asset):
                    pos = grid.index(day); cap.update(grid[max(0,pos-1):pos+2])
            file = ANALYTIC/f'roll_{cls}_{asset}.parquet'; meta = file.with_suffix('.json')
            key = dict(package=package_key, dates=dates, capture_dates=sorted(cap))
            if meta.exists():
                old = json.loads(meta.read_text())
                if old['key']==key and old['output_sha256']==sha256(file):
                    for scan in old['scans']:
                        folder = 'cryptos' if cls=='crypto' else cls
                        stat = (intraday_root()/folder/scan['file_name']).stat()
                        assert (stat.st_size,stat.st_mtime_ns)==(scan['size_bytes'],scan['mtime_ns'])
                    print(f'Verified completed Roll cache {cls}/{asset}', flush=True); continue
                raise ValueError('Existing cache differs from frozen code/source request; review before replacement')
            daily, capture, scans, seconds = calculate_asset(cls, asset, dates, sorted(cap))
            daily.to_parquet(file, index=False)
            capture_path = ANALYTIC/f'raw_audit_{cls}_{asset}.parquet'
            if not capture.empty: capture.to_parquet(capture_path, index=True)
            meta.write_text(json.dumps(dict(key=key, scans=scans, runtime_seconds=seconds,
                output_sha256=sha256(file), capture_sha256=sha256(capture_path) if not capture.empty else None),indent=2),encoding='utf-8')
            print(f'Completed Roll {cls}/{asset}: {len(daily)} target days', flush=True)


if __name__=='__main__':
    run_benchmarks()
