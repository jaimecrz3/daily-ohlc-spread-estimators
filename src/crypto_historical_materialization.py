"""Step 12.2: selected-only historical daily reconstruction and common calendar.

Raw files are streamed read-only. Parsed year partitions bound memory without
assuming source ordering. Existing aggregation and quality definitions are used.
Run: .venv/Scripts/python.exe -B src/crypto_historical_materialization.py
"""
from collections import Counter
from itertools import islice
from pathlib import Path
import csv
import gc
import hashlib
import json
import time

import numpy as np
import pandas as pd
import yaml

from data_io import intraday_root
from eda_diagnostics import parse_chunk
from daily_aggregation import aggregate_daily_ohlcv,FLAGS
from crypto_analysis_calendar import TIERS,exact_calendar,common_asset_dates,table_md
from bloomberg_io import sha256,verify_hashes,require_verified

PROJECT=Path(__file__).resolve().parents[1]
PARENT=PROJECT/'outputs/diagnostics/final_universe/crypto_final'
OUT=PARENT/'historical'
OLD=PROJECT/'outputs/diagnostics/final_universe/futures_crypto'
START,STOP=pd.Timestamp('2015-01-01'),pd.Timestamp('2026-01-01')


def aggregate_year(bars,asset,source_file=''):
    """Existing OHLCV/validity semantics, with supplementary diagnostic counts."""
    inside=bars.timestamp.ge(START)&bars.timestamp.lt(STOP)
    data=bars.loc[inside].copy()
    daily,annotated=aggregate_daily_ohlcv(data,asset,'cryptos',source_file=source_file,return_bar_audit=True)
    retained=annotated.loc[annotated.primary_session_retained].sort_values('timestamp_local',kind='stable').copy()
    if daily.empty: return daily,annotated
    prices=retained[['open','high','low','close']]
    # Reporting only: union of already invalid OHLC and missing/nonfinite price
    # components. These columns never add a new aggregation-validity criterion.
    retained['invalid_price']=retained.invalid_ohlc|~np.isfinite(prices).all(axis=1)
    retained['nonpositive_low']=retained.low.le(0)
    gap=retained.groupby('session_day',sort=False).timestamp_local.diff().dt.total_seconds()/60
    retained['gap_gt_one_minute']=gap.gt(1)
    quality=retained.groupby('session_day',sort=True).agg(invalid_price_rows=('invalid_price','sum'),
        nonpositive_low_rows=('nonpositive_low','sum'),gaps_gt_one_minute=('gap_gt_one_minute','sum'))
    for column in quality:
        daily[column]=daily.date.map(quality[column]).astype(int)
    daily['utc_date']=daily.date
    daily['nonpositive_low']=daily.nonpositive_low_rows.gt(0)
    daily['has_gap_gt_one_minute']=daily.gaps_gt_one_minute.gt(0)
    daily['source_quality_condition']=daily.aggregation_failure_reason.where(~daily.aggregation_valid,'')
    for mask,label in [(daily.zero_volume_rows.gt(0),'zero_volume_rows'),
                       (daily.has_gap_gt_one_minute,'gaps_gt_one_minute')]:
        daily.loc[mask,'source_quality_condition']=daily.loc[mask,'source_quality_condition'].map(
            lambda value:(str(value)+';' if value else '')+label)
    daily.loc[daily.source_quality_condition.eq(''),'source_quality_condition']='no_flagged_conditions'
    assert int(daily.bars_observed.sum())==len(retained)
    assert not daily.date.duplicated().any()
    return daily,annotated


def reconstruct_asset(path,asset,out,chunk_size=100_000):
    """Disk partitions are derived temporary data, never synthetic observations."""
    out.mkdir(parents=True,exist_ok=True)
    audit_dir=out/'read_audits';audit_dir.mkdir(exist_ok=True)
    stage=out/'staging'/asset;stage.mkdir(parents=True,exist_ok=True)
    if list(stage.glob('*.pkl')):
        raise ValueError('Unfinished staging partitions require explicit inspection before retry')
    before=path.stat();counts=Counter();digest=hashlib.sha256();partitions={}
    with path.open('r',encoding='utf-8-sig') as stream: pilot=list(islice(stream,10))
    if not pilot or any(len(line.strip().split(','))!=6 for line in pilot):
        raise ValueError('Small individual crypto file pilot failed')
    with (audit_dir/f'{asset}_unassignable_timestamps.csv').open('w',newline='',encoding='utf-8') as problems:
        writer=csv.writer(problems);writer.writerow(['raw_line_number','raw_text','reason'])
        with path.open('rb') as stream:
            offset=1;part=0
            while raw:=list(islice(stream,chunk_size)):
                for line in raw: digest.update(line)
                lines=[line.decode('utf-8-sig') for line in raw]
                text=pd.Series([line.split(',',1)[0].strip() for line in lines])
                ts=pd.to_datetime(text,format='%Y-%m-%d %H:%M:%S',errors='coerce')
                ts=ts.where(text.str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'))
                bad=ts.isna();inside=ts.ge(START)&ts.lt(STOP)
                counts['raw_rows_scanned']+=len(lines)
                counts['unassignable_timestamp_rows']+=int(bad.sum())
                counts['rows_before_2015']+=int(ts.lt(START).sum())
                counts['rows_after_2025']+=int(ts.ge(STOP).sum())
                counts['study_window_rows']+=int(inside.sum())
                for position in np.flatnonzero(bad):
                    writer.writerow([offset+int(position),lines[position].rstrip(),'unassignable_timestamp'])
                positions=np.flatnonzero(inside)
                if len(positions):
                    _,parsed=parse_chunk([lines[p] for p in positions],1)
                    parsed.index=pd.Index(offset+positions,name='raw_line_number')
                    for year,group in parsed.groupby(parsed.timestamp.dt.year,sort=True):
                        target=stage/f'{int(year)}_{part:06d}.pkl'
                        group.to_pickle(target)
                        partitions.setdefault(int(year),[]).append(target)
                    del parsed
                offset+=len(lines);part+=1
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise RuntimeError('Raw file changed during reconstruction')
    assert counts['raw_rows_scanned']==sum(counts[key] for key in [
        'unassignable_timestamp_rows','rows_before_2015','rows_after_2025','study_window_rows'])
    pieces=[];flag_path=audit_dir/f'{asset}_flagged_study_rows.csv';first_flags=True
    for year,files in sorted(partitions.items()):
        print(f'Aggregate {asset} {year}',flush=True)
        bars=pd.concat([pd.read_pickle(file) for file in files])
        daily,annotated=aggregate_year(bars,asset,str(path))
        bad=annotated[[flag for flag in FLAGS if flag in annotated]].any(axis=1)
        annotated.loc[bad].to_csv(flag_path,mode='w' if first_flags else 'a',header=first_flags,index=False)
        first_flags=False;pieces.append(daily)
        del bars,annotated
        # Exact individually known temporary files only; no recursive deletion.
        for file in files:
            if file.resolve().parent!=stage.resolve(): raise ValueError('Unsafe temporary partition path')
            file.unlink()
        gc.collect()
    daily=pd.concat(pieces,ignore_index=True).sort_values('date',kind='stable') if pieces else pd.DataFrame()
    if daily.empty: raise ValueError('No observed study-window daily rows')
    assert pd.to_datetime(daily.date).between(START,STOP,inclusive='left').all()
    assert daily.bars_observed.gt(0).all() and not daily.date.duplicated().any()
    scan=dict(asset=asset,file_name=path.name,sha256=digest.hexdigest(),size_bytes=before.st_size,
        mtime_ns=before.st_mtime_ns,source_unchanged=True,**dict(counts))
    return daily,scan


def reconcile_2024(historical,reference,asset,reference_name):
    h=historical.copy();r=reference.copy()
    h['date']=pd.to_datetime(h.date).dt.strftime('%Y-%m-%d')
    r['date']=pd.to_datetime(r.date).dt.strftime('%Y-%m-%d')
    h=h.loc[h.date.str.startswith('2024-')].sort_values('date').reset_index(drop=True)
    r=r.loc[r.date.str.startswith('2024-')].sort_values('date').reset_index(drop=True)
    dates_match=h.date.tolist()==r.date.tolist() and not h.date.duplicated().any() and not r.date.duplicated().any()
    numeric=['open','high','low','close','volume','max_gap_minutes']
    exact=['bars_observed','aggregation_valid','timezone','first_timestamp','last_timestamp',
        'aggregation_failure_reason']+[flag+'_rows' for flag in FLAGS]
    failures=[];differences={}
    if not dates_match: failures.append('observed_dates')
    if dates_match:
        for field in numeric:
            equal=np.allclose(h[field],r[field],rtol=1e-12,atol=1e-12,equal_nan=True)
            if not equal: failures.append(field)
            delta=(pd.to_numeric(h[field])-pd.to_numeric(r[field])).abs()
            differences[field+'_max_absolute_difference']=delta.max()
        for field in exact:
            if h[field].fillna('').astype(str).tolist()!=r[field].fillna('').astype(str).tolist():
                failures.append(field)
    return dict(asset=asset,reference=reference_name,historical_2024_days=len(h),reference_2024_days=len(r),
        observed_dates_match=dates_match,reconciliation_passed=not failures,
        discrepancy_fields=';'.join(failures),rtol=1e-12,atol=1e-12,**differences)


def protected_hashes():
    allowed={'crypto_final_analysis_spec.yaml','crypto_design_freeze_review.md'}
    directories=[PROJECT/'outputs/diagnostics/final_universe',PROJECT/'outputs/diagnostics/universe_selection']
    paths=[p for directory in directories for p in directory.rglob('*') if p.is_file()
        and OUT not in p.parents and not (p.parent==PARENT and p.name in allowed)]
    paths += [PROJECT/name for name in ['README.md','design_decisions.md','data_manifest.csv',
        'manifests/data_manifest.csv','data/raw_bloomberg/sha256_manifest.csv'] if (PROJECT/name).is_file()]
    return {str(p.relative_to(PROJECT)):sha256(p) for p in paths}


def freeze_ready(panels,reconciliation,scans,common):
    reasons=[]
    roots={asset for assets in TIERS.values() for asset in assets}
    if set(panels)!=roots or any(frame.empty for frame in panels.values()): reasons.append('missing_historical_panel')
    if (len(reconciliation)!=18 or set(reconciliation.asset)!=roots
            or not reconciliation.reconciliation_passed.all()): reasons.append('2024_reconciliation_failed')
    if len(scans)!=9 or sum(row['unassignable_timestamp_rows'] for row in scans): reasons.append('unassignable_or_unverified_source_rows')
    # Prespecified calendar adequacy guard, not an asset/day-quality exclusion.
    # The intersection must contain at least two inclusive elapsed years of
    # actual observed dates; no inventory endpoint can satisfy this check.
    if (not common or len(common)<730 or pd.Timestamp(common[-1])+pd.Timedelta(days=1)
            <pd.Timestamp(common[0])+pd.DateOffset(years=2)):
        reasons.append('common_calendar_not_substantial_multiyear')
    return not reasons,';'.join(reasons)


def run():
    started=time.perf_counter();OUT.mkdir(parents=True,exist_ok=True)
    before=protected_hashes()
    frozen=yaml.safe_load((PARENT/'crypto_final_spec.yaml').read_text(encoding='utf-8'))
    assert frozen['status']=='FROZEN' and frozen['liquidity_tiers']==TIERS
    selected=pd.read_csv(PARENT/'selected_crypto.csv',usecols=['asset','liquidity_tier'])
    roots=[asset for assets in TIERS.values() for asset in assets]
    assert len(selected)==9 and set(selected.asset)==set(roots)
    assert selected.set_index('asset').liquidity_tier.to_dict()=={a:t for t,assets in TIERS.items() for a in assets}
    prior=json.loads((PARENT/'run_manifest.json').read_text(encoding='utf-8'))
    step9=json.loads((OLD/'run_manifest.json').read_text(encoding='utf-8'))
    assert sha256(PARENT/'crypto_daily_turnover_audit.csv')==prior['output_sha256']['crypto_daily_turnover_audit.csv']
    old_daily=pd.read_csv(PARENT/'crypto_daily_turnover_audit.csv')
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    panels={};scans=[];reconciliations=[];coverage=[]
    for asset in roots:
        path=intraday_root()/'cryptos'/f'{asset}_full_1min.txt'
        print('Reconstruct '+asset,flush=True)
        daily,scan=reconstruct_asset(path,asset,OUT)
        daily.to_csv(OUT/f'{asset}_historical_daily_ohlcv.csv',index=False)
        reference_name=f'crypto_{asset}_2024_daily_ohlcv.csv'
        assert sha256(OLD/reference_name)==step9['output_sha256'][reference_name]
        for reference,label in [(pd.read_csv(OLD/reference_name),'Step9'),
            (old_daily.loc[old_daily.asset.eq(asset)],'Step12')]:
            reconciliations.append(reconcile_2024(daily,reference,asset,label))
        panels[asset]=daily;scans.append(scan)
        valid=daily.loc[daily.aggregation_valid]
        coverage.append(dict(asset=asset,liquidity_tier=selected.set_index('asset').loc[asset,'liquidity_tier'],
            first_observed_date=str(daily.date.min()),last_observed_date=str(daily.date.max()),
            first_valid_observed_date=str(valid.date.min()) if len(valid) else None,
            last_valid_observed_date=str(valid.date.max()) if len(valid) else None,
            observed_daily_rows=len(daily),valid_aggregation_days=len(valid),invalid_aggregation_days=len(daily)-len(valid),
            zero_volume_days=int(daily.zero_volume_rows.gt(0).sum()),zero_volume_rows=int(daily.zero_volume_rows.sum()),
            invalid_ohlc_rows=int(daily.invalid_ohlc_rows.sum()),invalid_price_rows=int(daily.invalid_price_rows.sum()),
            nonpositive_low_days=int(daily.nonpositive_low.sum()),days_with_gaps_gt_one_minute=int(daily.has_gap_gt_one_minute.sum())))
        pd.DataFrame(coverage).to_csv(OUT/'historical_daily_coverage.csv',index=False)
        pd.DataFrame(reconciliations).to_csv(OUT/'reconciliation_2024.csv',index=False)
        pd.DataFrame(scans).to_csv(OUT/'file_scan_audit.csv',index=False)
        print(f'{asset}: {len(daily)} observed days; invalid={len(daily)-len(valid)}',flush=True)
    reconciliation=pd.DataFrame(reconciliations)
    audit,_,common=exact_calendar(panels,TIERS)
    ready,reason=freeze_ready(panels,reconciliation,scans,common)
    audit['inside_common_interval']=audit.date.between(common[0],common[-1]) if common else False
    # Audit wholly absent calendar dates inside the common envelope as well.
    # They are metadata-only rows, never synthesized bars or daily OHLCV rows.
    if common:
        absent=sorted(set(pd.date_range(common[0],common[-1]).strftime('%Y-%m-%d'))-set(audit.date))
        if absent:
            missing=pd.DataFrame([dict(date=day,timezone='UTC',observed_assets=0,valid_assets=0,
                common_valid_date=False,missing_assets=';'.join(roots),invalid_assets='',
                omission_reason='all_nine_unavailable',LOW_valid_assets=0,MEDIUM_valid_assets=0,HIGH_valid_assets=0,
                inside_common_interval=True) for day in absent])
            audit=pd.concat([audit,missing],ignore_index=True).sort_values('date')
    audit['primary_inclusion']=audit.common_valid_date&ready
    audit.to_csv(OUT/'common_calendar_audit.csv',index=False)
    excluded=audit.loc[audit.inside_common_interval&~audit.common_valid_date].copy()
    excluded.to_csv(OUT/'excluded_common_interval_dates.csv',index=False)
    common_frame=pd.DataFrame({'utc_date':common,'assets_represented':9,'LOW_assets':3,'MEDIUM_assets':3,'HIGH_assets':3})
    common_frame.to_csv(OUT/'exact_common_dates.csv',index=False)
    expanded=common_asset_dates(common,TIERS)
    assert expanded.groupby('date').asset.nunique().eq(9).all()
    for tier in TIERS: assert set(expanded.loc[expanded.liquidity_tier.eq(tier),'date'])==set(common)
    all_daily=pd.concat(panels.values(),ignore_index=True)
    quality_columns=['asset','utc_date','bars_observed','zero_volume_rows','invalid_ohlc_rows','invalid_price_rows',
        'nonpositive_low_rows','nonpositive_low','gaps_gt_one_minute','max_gap_minutes','aggregation_valid','source_quality_condition']
    all_daily[quality_columns].to_csv(OUT/'historical_quality_audit.csv',index=False)
    coverage=pd.DataFrame(coverage)
    for row in scans:
        stat=(intraday_root()/'cryptos'/row['file_name']).stat()
        assert (stat.st_size,stat.st_mtime_ns)==(row['size_bytes'],row['mtime_ns'])
    spec=dict(status='FROZEN' if ready else 'BLOCKED',crypto_universe_status='FROZEN',
        crypto_analysis_window_status='FROZEN' if ready else 'BLOCKED',approval_step='12.2',
        selected_assets=roots,liquidity_tiers=TIERS,liquidity_calibration_year=2024,
        primary_common_start=common[0] if ready else None,primary_common_end=common[-1] if ready else None,
        primary_common_dates=len(common) if ready else None,primary_asset_days=len(common)*9 if ready else None,
        primary_design='Exact common valid observed UTC calendar across all nine frozen crypto assets',
        candidate_common_start=common[0] if common else None,candidate_common_end=common[-1] if common else None,
        candidate_common_dates=len(common),reconstruction_validation_passed=ready,block_reason=reason,
        reconciliation_2024='historical/reconciliation_2024.csv; all dates, OHLCV, bar counts and existing quality/validity fields checked against both Step9 and Step12',
        numerical_reconciliation_tolerance={'rtol':1e-12,'atol':1e-12},
        exact_primary_calendar='historical/exact_common_dates.csv',
        excluded_dates_inside_common_interval=len(excluded),excluded_date_audit='historical/excluded_common_interval_dates.csv',
        study_start='2015-01-01',study_end='2025-12-31',
        historical_supplementary_role='Asset-specific valid history outside the common calendar is supplementary historical/descriptive only; never pool changing composition as a liquidity effect',
        missing_day_policy='No filling, interpolation, carry-forward, synthesized daily observations or compression; calendar-only absence rows are audits',
        validity_policy='Existing aggregate_daily_ohlcv aggregation_valid only; invalid and zero-volume/gap diagnostics preserved; zero volume/gaps do not themselves invalidate',
        look_ahead_limitation='2024 turnover-calibrated tiers applied before 2024 use future information: look-ahead / ex-post classification and survivorship-style limitation',
        selection_timing='Frozen before any estimator/benchmark performance influenced selection; no outcome-driven selection or reranking',
        quote_basis_status=frozen['quote_basis_validation_status'],quote_currency=frozen['quote_currency'],
        universe_specification='crypto_final_spec.yaml',universe_specification_sha256=sha256(PARENT/'crypto_final_spec.yaml'),
        no_benchmark_or_estimator_calculations=True,source_adjustment='provider_unspecified; unchanged',
        adequacy_policy='At least 730 exact common observations spanning two inclusive elapsed years; calendar adequacy only, not a new asset/day quality rule')
    (PARENT/'crypto_final_analysis_spec.yaml').write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    report='# Step 12.2 historical crypto materialization and final analysis freeze\n\n'
    report+=f'Crypto universe remains FROZEN. **Crypto analysis window: {spec["crypto_analysis_window_status"]}**. This Step-12.2 reconstruction supersedes the Step-12.1 materialization block; the original 2024 audit remains a historical record. No selected asset, tier, ranking, quote-basis decision, liquidity definition or eligibility rule changed.\n\n'
    report+='Historical coverage (all actual observed support clipped to 2015-2025)\n\n'+table_md(coverage)+'\n\n'
    report+='Mandatory 2024 reconciliation\n\n'+table_md(reconciliation[[c for c in reconciliation if not c.endswith('_max_absolute_difference')]])+'\n\n'
    report+=f'All nine require both reference reconciliations to pass (18 checks). Invalidity is retained, not repaired. Existing flags are compared exactly; numerical OHLCV uses rtol=atol=1e-12. No prior 2024 artifact was overwritten. Freeze blocker: {reason or "none"}.\n\n'
    report+=f'Exact common calendar: **{common[0] if common else "unavailable"} through {common[-1] if common else "unavailable"}**; **{len(common):,} dates**; **{len(common)*9:,} asset-days**. All three tiers use those identical dates and all nine assets appear on every included date. This is not a balanced 2015-2025 crypto panel. Primary inclusion is conditional on reconstruction approval, not on price, turnover or benchmark outcomes.\n\n'
    report+=f'Dates excluded inside the common start/end interval: **{len(excluded)}**. See historical/excluded_common_interval_dates.csv for exact dates and missing/invalid assets. Wholly absent dates appear only in calendar audits, never in OHLCV panels. Invalid historical days remain in their original panels and cannot enter the primary calendar.\n\n'
    report+='Historical quality conditions\n\n'+table_md(coverage[['asset','invalid_aggregation_days','zero_volume_days','invalid_price_rows','nonpositive_low_days','days_with_gaps_gt_one_minute']])+'\n\n'
    report+='OHLCV and aggregation_valid use the unchanged deterministic daily pipeline: stable chronological first open / last close, extrema and volume sum with skipna=False; duplicates and invalid source data remain flagged. invalid_price_rows reports existing invalid_ohlc or missing/nonfinite price components; nonpositive_low_rows counts observed low<=0. gaps_gt_one_minute counts within-day adjacent timestamp gaps>1 minute, without bridging or filling. Added reporting counts do not change day validity. Flagged source rows and unassignable timestamps are preserved in read_audits.\n\n'
    report+='Earlier/later asset-specific validated histories remain supplementary historical/descriptive only. Do not pool changing historical composition with the primary common-date comparison and attribute differences solely to liquidity.\n\n'
    report+='Liquidity tiers were calibrated using 2024 provider-quote turnover. Applying those frozen labels to pre-2024 observations uses future information and creates a look-ahead / ex-post classification and survivorship-style limitation. Selection preceded estimator/benchmark performance and no such outcome influenced selection. The universe is not changed to remove this limitation. The quote basis remains VERIFIED_COMMON_PROVIDER_QUOTE_BASIS; formal currency remains UNKNOWN.\n\n'
    report+='Raw First Rate files were opened read-only and fingerprinted; no 2026 observations were included. No bars, daily observations or prices were filled, imputed, repaired, relabelled or carried forward. No Roll, CS, AR or EDGE values or performance were calculated. Protected prior artifacts and documentation remain unchanged. Reproduce with src/crypto_historical_materialization.py.\n'
    test_record=OUT/'test_results.txt'
    if test_record.exists(): report+='\n```text\n'+test_record.read_text(encoding='utf-8').strip()+'\n```\n'
    (PARENT/'crypto_design_freeze_review.md').write_text(report,encoding='utf-8')
    assert before==protected_hashes()
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    result=dict(status=spec['status'],protected_prior_sha256=before,
        code_sha256={name:sha256(PROJECT/'src'/name) for name in ['crypto_historical_materialization.py',
            'daily_aggregation.py','session_rules.py','eda_diagnostics.py','crypto_analysis_calendar.py']},
        raw_bloomberg_hashes_verified=len(raw),raw_provider_writes=0,
        runtime_seconds=time.perf_counter()-started,bytes_scanned=sum(row['size_bytes'] for row in scans),
        source_sha256={row['file_name']:row['sha256'] for row in scans},
        output_sha256={str(path.relative_to(PARENT)):sha256(path) for path in OUT.glob('*.csv')},
        analysis_spec_sha256=sha256(PARENT/'crypto_final_analysis_spec.yaml'),
        review_sha256=sha256(PARENT/'crypto_design_freeze_review.md'))
    (OUT/'run_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(coverage.to_string(index=False));print('Status:',spec['status'],'common dates:',len(common),'asset-days:',len(common)*9)


if __name__=='__main__': run()
