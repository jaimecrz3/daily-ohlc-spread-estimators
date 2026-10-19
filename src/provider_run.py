"""Step17 provider outcomes, definedness and sample construction ONLY.

No error, accuracy, ranking or inference calculations. Observation-level data and
five-case source evidence stay in ignored data/analytic. Diagnostics are counts.
Run provider_run_io.py first, then this file with --run-tests.
"""
from pathlib import Path
from datetime import date, datetime
import argparse
import inspect
import io
import json
import re
import subprocess
import sys
import time

import numpy as np
import openpyxl
import pandas as pd
import yaml

from bloomberg_io import sha256, verify_hashes, require_verified, normalize_daily_rows
from daily_aggregation import aggregate_daily_ohlcv
from estimator_windows import daily_estimate, load_reference_grid
from spread_estimators import result
from provider_run_io import (PROJECT, DIAG, FINAL, DESIGN, ANALYTIC, EXPECTED,
    frozen_design, verify_frozen, fixed_audit_keys, invoke_roll, configs, roll_interface_unchanged)

OUT = DIAG/'provider_run'
PANEL = PROJECT/'data/analytic/primary_provider_panel.parquet'
METHODS = ['cs','ar','edge']
FORBIDDEN_COLUMNS = {'error','signed_error','absolute_error','squared_error','bias','mae','rmse',
    'correlation_with_roll','ranking','hac_se','p_value','confidence_interval'}


def clean(value):
    if isinstance(value, dict): return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value, (list,tuple,np.ndarray)): return [clean(v) for v in value]
    if isinstance(value, (np.bool_,bool)): return bool(value)
    if isinstance(value, (np.integer,int)): return int(value)
    if isinstance(value, (np.floating,float)): return float(value) if np.isfinite(value) else None
    if value is pd.NA or value is pd.NaT: return None
    if isinstance(value, (pd.Timestamp,date,datetime)): return value.isoformat()
    return value


def dumps(value):
    return json.dumps(clean(value), allow_nan=False, separators=(',',':'))


def verify_ignored(path):
    completed = subprocess.run(['git','check-ignore','--quiet',str(path.relative_to(PROJECT))],cwd=PROJECT)
    if completed.returncode != 0: raise ValueError('Observation-level output must be Git ignored: '+str(path))
    tracked = subprocess.run(['git','ls-files','--',str(path.relative_to(PROJECT))],cwd=PROJECT,capture_output=True,text=True)
    if tracked.stdout.strip(): raise ValueError('Provider output is tracked by Git; refusing write')


def source_daily(cls, asset, global_spec):
    """Existing frozen sources, allowlisted price columns, exact input hashes."""
    manifest = json.loads((DESIGN/'run_manifest.json').read_text())
    if cls in ['stocks','etfs']:
        path = PROJECT/'data/interim/bloomberg/daily_adjusted.parquet'
        assert sha256(path)==manifest['input_sha256'][path.relative_to(PROJECT).as_posix()]
        all_rows = pd.read_parquet(path)
        frame = all_rows.loc[all_rows.asset.eq(asset)].copy()
        assert frame.asset_class.eq(cls).all() and frame.source.eq('Bloomberg').all() and frame.convention.eq('adjusted').all()
    else:
        path = FINAL/(f'futures_final/historical/{asset}_historical_daily_ohlcv.csv' if cls=='futures'
                       else f'crypto_final/historical/{asset}_historical_daily_ohlcv.csv')
        assert sha256(path)==manifest['input_sha256'][path.relative_to(PROJECT).as_posix()]
        frame = pd.read_csv(path, keep_default_na=True)
    frame['date']=pd.to_datetime(frame.date).dt.strftime('%Y-%m-%d')
    assert not frame.date.duplicated().any() and frame.asset.eq(asset).all()
    return frame.sort_values('date'), path


def method_output(source, cls, asset, target, method, full_grid):
    """Reuse frozen mapping on only its exact scheduled context; no row compression.

    Futures contract admission is checked BEFORE a kernel can see mixed prices.
    It implements the explicit Step17 contract prohibition, not a new formula.
    """
    grid = full_grid
    target = pd.Timestamp(target); location = grid.get_indexer([target])[0]
    if location < 0: raise ValueError('Target absent from verified reference grid')
    small_grid = grid[max(0,location-1):location+2]
    days = small_grid.strftime('%Y-%m-%d').tolist()
    context = source.loc[source.date.isin(days)].copy()
    required = days if method in ['CS','EDGE'] else [d for d in days if d>=str(target.date())]
    # Match the frozen boundary behavior; let the mapper report missing endpoints.
    if cls=='futures' and len(required)==(2 if method=='AR' else 3):
        neighbors = context.loc[context.date.isin(required)]
        if len(neighbors)==len(required) and neighbors.selected_contract.nunique(dropna=False)>1:
            output = result(method,len(neighbors),'invalid_scheduled_adjacency',dict(
                failure_detail='futures_contract_boundary', contract_boundary=True,
                selected_contracts=neighbors.selected_contract.tolist(), scheduled_grid_not_compressed=True))
            output.update(asset=asset,target_date=str(target.date()),input_dates=required,
                scheduled_adjacency_valid=False,window_complete=True)
            return output
    fields=[c for c in ['asset','date','open','high','low','close','PX_OPEN','PX_HIGH','PX_LOW','PX_LAST'] if c in context]
    output = daily_estimate(context[fields], asset, target, method, small_grid)
    output['method_specific_diagnostics']['contract_boundary']=False
    return output


def row_from_outputs(design_row, roll, estimates, source_target):
    cls, asset, target = design_row['asset_class'],design_row['asset'],design_row['date']
    row = dict(asset_class=cls,asset=asset,liquidity_tier=design_row['liquidity_tier'],
        target_date=target,design_eligible=True,
        estimator_source='Bloomberg adjusted daily OHLC' if cls in ['stocks','etfs'] else 'First Rate selected individual-contract daily OHLC' if cls=='futures' else 'First Rate UTC daily OHLC',
        benchmark_source='First Rate Data / official RiskLab intraday_data',
        estimator_adjustment='CapChg=T;CshAdjNormal=T;CshAdjAbnormal=UNKNOWN' if cls in ['stocks','etfs'] else 'unadjusted_individual_contract' if cls=='futures' else 'provider_unspecified',
        common_source_mechanical_link=cls in ['futures','crypto'],
        quote_currency='UNKNOWN' if cls=='crypto' else None,
        imdx_identity_continuity_certified=False if asset=='IMDX' and cls=='stocks' else None,
        imdx_identity_policy='source_defined_history_retained_without_manual_stitching' if asset=='IMDX' and cls=='stocks' else None)
    mapping={'bars_observed':'benchmark_bars_observed','roll_autocovariance':'roll_gamma',
        'failure_reason':'roll_failure_reason','benchmark_failure_reason':'roll_legacy_failure_reason'}
    for key,value in roll.items():
        if key in ['asset','asset_class','date']: continue
        name=mapping.get(key,key if key.startswith(('roll_','benchmark_')) else 'benchmark_'+key)
        row[name]=value
    row['benchmark_role']='frozen_primary'
    if cls=='futures':
        for key in ['selected_contract','previous_contract','roll_day','provider_mapping_date','session_rule_id','session_status','contract_file']:
            row[key]=source_target.get(key)
    for key in ['aggregation_valid','aggregation_failure_reason','complete_ohlc','partial_ohlc_row','invalid_ohlc']:
        if key in source_target: row['estimator_source_'+key]=source_target[key]
    for method, output in estimates.items():
        p=method.lower()
        for key in ['raw_moment','raw_signed_spread_relative','raw_negative','raw_computable',
                    'primary_spread_relative','primary_spread_bps','failure_reason','scheduled_adjacency_valid','window_complete','input_observations']:
            row[p+'_'+key]=output[key]
        row[p+'_defined']=output['estimator_defined']
        row['input_dates_'+p]=dumps(output['input_dates'])
        row[p+'_method_specific_diagnostics']=dumps(output['method_specific_diagnostics'])
        row[p+'_contract_boundary']=bool(output['method_specific_diagnostics'].get('contract_boundary',False))
        row[p+'_extreme_finite_gt_1']=bool(output['estimator_defined'] and output['primary_spread_relative']>1)
        if p in ['ar','edge']: row[p+'_s2_raw']=output['raw_moment']
        if p=='cs': row['cs_negative_component_intervals']=output['method_specific_diagnostics'].get('negative_component_intervals')
    row['common_defined_accuracy_sample']=bool(row['design_eligible'] and row['benchmark_defined'] and all(row[p+'_defined'] for p in METHODS))
    return row


def estimate_asset(cls, asset, group, daily, roll):
    grid=load_reference_grid(cls)
    indexed=daily.set_index('date'); rolls=roll.set_index('date')
    assert set(group.date)==set(roll.date) and not roll.date.duplicated().any()
    rows=[]
    for item in group.sort_values('date').to_dict('records'):
        day=item['date']
        assert day in indexed.index, 'Required daily source day missing from design'
        estimates={m:method_output(daily,cls,asset,day,m,grid) for m in ['CS','AR','EDGE']}
        rows.append(row_from_outputs(item,rolls.loc[day].to_dict(),estimates,indexed.loc[day].to_dict()))
    return pd.DataFrame(rows)


def common_mask(panel):
    return panel[['design_eligible','benchmark_defined','cs_defined','ar_defined','edge_defined']].eq(True).all(axis=1)


def validate_panel(panel, design):
    assert len(panel)==38232 and panel.groupby('asset_class').size().to_dict()==EXPECTED
    assert not panel.duplicated(['asset_class','asset','target_date']).any()
    assert not set(panel.columns)&FORBIDDEN_COLUMNS
    keys=panel[['asset_class','asset','target_date','liquidity_tier']].rename(columns={'target_date':'date'})
    merged=keys.merge(design[['asset_class','asset','date','liquidity_tier']],on=['asset_class','asset','date','liquidity_tier'],how='outer',indicator=True,validate='one_to_one')
    assert merged._merge.eq('both').all() and panel.design_eligible.all()
    assert panel.common_defined_accuracy_sample.equals(common_mask(panel))
    assert panel.benchmark_bars_observed.gt(0).all()
    for p, defined in [('roll','benchmark_defined')]+[(p,p+'_defined') for p in METHODS]:
        relative=p+'_spread_relative' if p=='roll' else p+'_primary_spread_relative'
        bps=p+'_spread_bps' if p=='roll' else p+'_primary_spread_bps'
        good=panel[defined]
        assert np.isfinite(panel.loc[good,relative]).all() and panel.loc[good,relative].ge(0).all()
        assert np.allclose(panel.loc[good,bps],panel.loc[good,relative]*10000,rtol=1e-13,atol=1e-12)
        assert panel.loc[~good,relative].isna().all() and panel.loc[~good,bps].isna().all()
        reason='roll_failure_reason' if p=='roll' else p+'_failure_reason'
        assert panel.loc[good,reason].fillna('').eq('').all()
        assert panel.loc[~good,reason].fillna('').ne('').all()
        if p!='roll':
            negative=panel[p+'_raw_negative'].eq(True).fillna(False)
            assert panel.loc[negative,p+'_raw_computable'].all()
            assert np.isfinite(panel.loc[negative,p+'_raw_moment']).all()
            assert np.isfinite(panel.loc[negative,p+'_raw_signed_spread_relative']).all()
            assert panel.loc[negative,p+'_defined'].all()
            if p in ['ar','edge']: assert panel.loc[negative,relative].eq(0).all()
    assert not panel.loc[panel.roll_gamma.ge(0),'benchmark_defined'].any()
    assert not panel.loc[panel.roll_pairs.lt(2),'benchmark_defined'].any()


def reporting_groups(panel):
    yield 'overall','ALL','ALL',panel
    for cls,part in panel.groupby('asset_class',sort=True):
        yield 'asset_class',cls,'ALL',part
        for tier,group in part.groupby('liquidity_tier',sort=True):
            yield 'asset_class_x_tier',cls,tier,group


def diagnostic_tables(panel):
    defined=[]; failures=[]; negative=[]; adjacency=[]; sanity=[]
    for level,cls,tier,part in reporting_groups(panel):
        record=dict(level=level,asset_class=cls,liquidity_tier=tier,design_eligible_N=len(part),
                    common_defined_accuracy_N=int(part.common_defined_accuracy_sample.sum()))
        for p,field in [('benchmark','benchmark_defined')]+[(p,p+'_defined') for p in METHODS]:
            record[p+'_defined_N']=int(part[field].sum()); record[p+'_undefined_N']=int((~part[field]).sum())
            reason='roll_failure_reason' if p=='benchmark' else p+'_failure_reason'
            counts=part.loc[~part[field],reason].value_counts()
            assert int(counts.sum())==record[p+'_undefined_N']
            for name,n in counts.items():
                failures.append(dict(level=level,asset_class=cls,liquidity_tier=tier,method=p,failure_reason=name,count=int(n)))
        defined.append(record)
    for cls,part in panel.groupby('asset_class',sort=True):
        for p in METHODS:
            good=part[p+'_defined']; raw=part[p+'_raw_negative'].eq(True).fillna(False)
            finite_raw=np.isfinite(part[p+'_raw_moment'])&np.isfinite(part[p+'_raw_signed_spread_relative'])
            negative.append(dict(asset_class=cls,estimator=p,raw_negative_N=int(raw.sum()),
                raw_negative_nonfinite_N=int((raw&~finite_raw).sum()),
                raw_negative_undefined_N=int((raw&~good).sum()),
                raw_negative_defined_zero_N=int((raw&good&part[p+'_primary_spread_relative'].eq(0)).sum()),
                integrity_passed=bool((~raw|finite_raw&good).all())))
            values=part.loc[good,p+'_primary_spread_relative']
            sanity.append(dict(asset_class=cls,estimator=p,defined_N=len(values),
                minimum=values.min(),median=values.median(),p95=values.quantile(.95),p99=values.quantile(.99),maximum=values.max(),
                extreme_finite_gt_1_N=int(part[p+'_extreme_finite_gt_1'].sum()),
                finite_nonnegative_passed=bool(np.isfinite(values).all() and values.ge(0).all()),
                bps_conversion_passed=True,undefined_remains_NaN=True))
            for tier,group in [('ALL',part)]+list(part.groupby('liquidity_tier',sort=True)):
                adjacency.append(dict(asset_class=cls,liquidity_tier=tier,estimator=p,target_N=len(group),
                    scheduled_adjacency_invalid_N=int((~group[p+'_scheduled_adjacency_valid']).sum()),
                    incomplete_window_N=int((~group[p+'_window_complete']).sum()),
                    futures_contract_boundary_N=int(group[p+'_contract_boundary'].sum())))
    tables={'definedness_summary.csv':pd.DataFrame(defined),
        'failure_reason_summary.csv':pd.DataFrame(failures),
        'common_sample_summary.csv':pd.DataFrame(defined)[['level','asset_class','liquidity_tier','design_eligible_N','common_defined_accuracy_N']],
        'estimator_value_sanity.csv':pd.DataFrame(sanity),
        'raw_negative_integrity_audit.csv':pd.DataFrame(negative),
        'scheduled_adjacency_audit.csv':pd.DataFrame(adjacency)}
    return tables


def workbook_context(asset, source, dates, workbook):
    """Read exact existing acquisition cells, no recalculation or raw writes."""
    context=source.loc[source.date.isin(dates)]
    sheet=workbook[asset+' US EQUITY']
    wanted=set(context.source_row.astype(int))
    rows=[(number,[c.value for c in row]) for number,row in enumerate(
        sheet.iter_rows(min_row=min(wanted),max_row=max(wanted),max_col=8),min(wanted)) if number in wanted]
    normalized=normalize_daily_rows(rows,asset,context.asset_class.iloc[0],'adjusted',
        'bloomberg_daily_adjusted_raw_values.xlsx',sheet.title)
    normalized['date']=pd.to_datetime(normalized.date).dt.strftime('%Y-%m-%d')
    return normalized


def reproduce(panel, design, global_spec):
    records=[]; details=[]
    wb=openpyxl.load_workbook(PROJECT/'data/raw_bloomberg/13-10-2026/bloomberg_daily_adjusted_raw_values.xlsx',read_only=True,data_only=False)
    try:
        for cls,asset,day in fixed_audit_keys(design):
            saved=panel.loc[panel.asset_class.eq(cls)&panel.asset.eq(asset)&panel.target_date.eq(day)].iloc[0]
            frame,source_path=source_daily(cls,asset,global_spec)
            grid=load_reference_grid(cls); pos=grid.get_indexer([pd.Timestamp(day)])[0]
            dates=grid[max(0,pos-1):pos+2].strftime('%Y-%m-%d').tolist()
            raw_path=ANALYTIC/f'raw_audit_{cls}_{asset}.parquet'
            capture_meta=json.loads((ANALYTIC/f'roll_{cls}_{asset}.json').read_text())
            assert sha256(raw_path)==capture_meta['capture_sha256'], 'Hand-audit capture changed'
            bars=pd.read_parquet(raw_path)
            registry=configs() if cls=='futures' else None
            rb=invoke_roll(bars,cls,asset,registry)
            rr=rb.loc[rb.date.astype(str).eq(day)].iloc[0]
            assert int(rr.roll_pairs)==int(saved.roll_pairs)
            assert int(rr.bars_observed)==int(saved.benchmark_bars_observed)
            assert bool(rr.benchmark_defined)==bool(saved.benchmark_defined)
            for col,field in [('roll_autocovariance','roll_gamma'),('roll_spread_relative','roll_spread_relative'),('roll_spread_bps','roll_spread_bps')]:
                assert np.isclose(rr[col],saved[field],rtol=1e-12,atol=1e-12,equal_nan=True)
            if cls in ['stocks','etfs']:
                rebuilt=workbook_context(asset,frame,dates,wb)
                compared=rebuilt.merge(frame,on='date',suffixes=('_raw','_normalized'),validate='one_to_one')
                for col in ['PX_OPEN','PX_HIGH','PX_LOW','PX_LAST']:
                    assert np.allclose(compared[col+'_raw'],compared[col+'_normalized'],rtol=1e-12,atol=1e-12,equal_nan=True)
                fields=['date','PX_OPEN','PX_HIGH','PX_LOW','PX_LAST','source_row']
            else:
                audit=None
                if cls=='futures':
                    audit=pd.read_csv(FINAL/f'futures_final/historical/{asset}_historical_session_audit.csv')
                rebuilt=aggregate_daily_ohlcv(bars,asset,'cryptos' if cls=='crypto' else cls,
                    futures_root=asset if cls=='futures' else None,futures_sessions=registry,futures_audit=audit)
                # Reproduce the existing CSV materialization/reading convention.
                rebuilt=pd.read_csv(io.StringIO(rebuilt.to_csv(index=False)))
                rebuilt['date']=pd.to_datetime(rebuilt.date).dt.strftime('%Y-%m-%d')
                compared=rebuilt.merge(frame,on='date',suffixes=('_raw','_saved'),validate='one_to_one')
                assert len(compared)==len(dates)
                for col in ['open','high','low','close','volume','bars_observed']:
                    assert np.allclose(compared[col+'_raw'],compared[col+'_saved'],rtol=1e-12,atol=1e-12,equal_nan=True)
                fields=['date','open','high','low','close','volume','bars_observed']
            outputs={method:method_output(rebuilt,cls,asset,day,method,grid) for method in ['CS','AR','EDGE']}
            for method,value in outputs.items():
                p=method.lower()
                assert value['estimator_defined']==saved[p+'_defined']
                assert value['failure_reason']==saved[p+'_failure_reason']
                assert value['input_dates']==json.loads(saved['input_dates_'+p])
                assert value['scheduled_adjacency_valid']==saved[p+'_scheduled_adjacency_valid']
                for field in ['raw_moment','raw_signed_spread_relative','primary_spread_relative','primary_spread_bps']:
                    assert np.isclose(value[field],saved[p+'_'+field],rtol=1e-11,atol=1e-10,equal_nan=True)
                assert value['raw_negative']==(None if pd.isna(saved[p+'_raw_negative']) else bool(saved[p+'_raw_negative']))
            details.append(dict(asset_class=cls,asset=asset,target_date=day,source_dates=dates,
                source_ohlcv=clean(rebuilt[fields].to_dict('records')),roll=clean(rr.to_dict()),
                estimators=outputs,raw_minute_capture=str(raw_path.relative_to(PROJECT)),raw_minute_sha256=sha256(raw_path)))
            records.append(dict(asset_class=cls,asset=asset,target_date=day,
                selection_rule='Sorted-key midpoint per class; extra first LOW stock midpoint; independent of outputs',
                source_inputs_match=True,roll_counts_and_outputs_match=True,estimator_windows_and_outputs_match=True,
                reproduction_passed=True,detail_artifact='data/analytic/provider_run/raw_to_final_reproduction.json'))
    finally:
        wb.close()
    (ANALYTIC/'raw_to_final_reproduction.json').write_text(json.dumps(clean(details),indent=2,allow_nan=False),encoding='utf-8')
    return pd.DataFrame(records)


def run(run_tests=False, wait_for_benchmarks=False):
    started=time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True); ANALYTIC.mkdir(parents=True,exist_ok=True)
    global_spec=verify_frozen(); design=frozen_design()
    verify_ignored(PANEL); verify_ignored(ANALYTIC/'raw_to_final_reproduction.json')
    # Existing Step16 protected records remain authoritative; no prior writes.
    protected=json.loads((DIAG/'statistical_freeze/run_manifest.json').read_text())['protected_sha256']
    protected.update({p.relative_to(PROJECT).as_posix():sha256(p) for p in (DIAG/'statistical_freeze').iterdir() if p.is_file()})
    pieces=[]; scans=[]; bench_seconds=0; inputs={}
    eval_code={name:sha256(PROJECT/'src'/name) for name in ['provider_run.py','provider_run_io.py','benchmark.py','spread_estimators.py','estimator_windows.py']}
    for cls in EXPECTED:
        for asset in global_spec['selected_assets_by_class'][cls]:
            print(f'Estimators {cls}/{asset}',flush=True)
            group=design.loc[design.asset_class.eq(cls)&design.asset.eq(asset)]
            roll_path=ANALYTIC/f'roll_{cls}_{asset}.parquet'
            while wait_for_benchmarks and not roll_path.with_suffix('.json').exists():
                print(f'Waiting for verified Roll cache {cls}/{asset}',flush=True)
                time.sleep(30)
            meta=json.loads(roll_path.with_suffix('.json').read_text())
            assert sha256(roll_path)==meta['output_sha256']
            for name,digest in meta['key']['package'].items():
                expected_path=DESIGN/'global_design_final_spec.yaml' if name=='global_design' else PROJECT/'src'/name
                assert sha256(expected_path)==digest, 'Roll cache code/spec changed'
            roll=pd.read_parquet(roll_path); roll['date']=roll.date.astype(str)
            daily,path=source_daily(cls,asset,global_spec)
            inputs[path.relative_to(PROJECT).as_posix()]=sha256(path)
            part_path=ANALYTIC/f'panel_{cls}_{asset}.parquet'
            part_meta=part_path.with_suffix('.json')
            cache_key=dict(source_sha256=sha256(path),roll_sha256=sha256(roll_path),
                frozen_estimator_sha256=sha256(PROJECT/'src/spread_estimators.py'),
                frozen_mapping_sha256=sha256(PROJECT/'src/estimator_windows.py'),
                adapter_code=inspect.getsource(method_output)+inspect.getsource(row_from_outputs)+inspect.getsource(estimate_asset),
                target_dates=sorted(group.date))
            cached=json.loads(part_meta.read_text()) if part_meta.exists() else None
            if cached is not None and cached['key']==cache_key and sha256(part_path)==cached['output_sha256']:
                part=pd.read_parquet(part_path)
                print(f'Verified estimator checkpoint {cls}/{asset}',flush=True)
            else:
                part=estimate_asset(cls,asset,group,daily,roll)
                part.to_parquet(part_path,index=False)
                part_meta.write_text(json.dumps(dict(key=cache_key,output_sha256=sha256(part_path)),indent=2),encoding='utf-8')
            pieces.append(part); scans.extend(meta['scans']); bench_seconds+=meta['runtime_seconds']
    panel=pd.concat(pieces,ignore_index=True).sort_values(['asset_class','asset','target_date']).reset_index(drop=True)
    for p in METHODS: panel[p+'_raw_negative']=pd.array(panel[p+'_raw_negative'],dtype='boolean')
    validate_panel(panel,design)
    panel.to_parquet(PANEL,index=False)
    tables=diagnostic_tables(panel)
    for name,table in tables.items(): table.to_csv(OUT/name,index=False)
    reconciliation=pd.DataFrame([dict(asset_class=cls,expected_design_rows=n,
        actual_design_rows=int(panel.asset_class.eq(cls).sum()),reconciled=int(panel.asset_class.eq(cls).sum())==n) for cls,n in EXPECTED.items()])
    reconciliation.to_csv(OUT/'design_row_reconciliation.csv',index=False)
    reproduction=reproduce(panel,design,global_spec)
    reproduction.to_csv(OUT/'raw_to_final_reproduction.csv',index=False)
    scan_table=pd.DataFrame(scans)
    scan_table.to_csv(ANALYTIC/'source_scan_audit.csv',index=False)
    # Verify source fingerprints again under approved archive access.
    from data_io import intraday_root
    for row in scans:
        path=intraday_root()/('cryptos' if row['asset_class']=='crypto' else row['asset_class'])/row['file_name']
        stat=path.stat(); assert (stat.st_size,stat.st_mtime_ns)==(row['size_bytes'],row['mtime_ns'])
    tests=dict(status='NOT_RUN',passed=0,failed=0)
    if run_tests:
        completed=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests'],cwd=PROJECT,capture_output=True,text=True)
        output=completed.stdout+completed.stderr
        (OUT/'test_results.txt').write_text(output,encoding='utf-8'); print(output,flush=True)
        match=re.search(r'Ran (\d+) tests?',output)
        if completed.returncode or match is None: raise RuntimeError('Full suite failed; provider run remains BLOCKED')
        tests=dict(status='PASSED',passed=int(match.group(1)),failed=0)
    status='PROVIDER_RUN_VALIDATED_FOR_HORSE_RACE' if tests['status']=='PASSED' else 'CALCULATED_PENDING_FULL_SUITE'
    assert all(sha256(PROJECT/name)==digest for name,digest in protected.items()),'Protected prior artifact changed'
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    elapsed=time.perf_counter()-started
    spec=dict(status=status,step=17,primary_panel=PANEL.relative_to(PROJECT).as_posix(),
        primary_panel_sha256=sha256(PANEL),design_rows=EXPECTED,total_design_rows=len(panel),tests=tests,
        asset_classes_processed=list(EXPECTED),fx_status='IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS',substitute_fx_allowed=False,
        frozen_references={name:sha256(DIAG/name) for name in ['design_freeze/global_design_final_spec.yaml','estimator_freeze/estimator_formula_spec.yaml','statistical_freeze/primary_weighting_spec.yaml','statistical_freeze/hac_inference_spec.yaml']},
        benchmark_minimum_pairs=2,benchmark_ddof=1,benchmark_interface_extension='Only optional frozen root-specific session registry forwarding; all other source bytes match Step10 hash after removing that forwarding',
        estimator_kernels_and_mapping='Unchanged Step15 code; exact scheduled contexts only',
        futures_window_admission='Reject mixed selected contracts BEFORE method kernel; invalid_scheduled_adjacency with futures_contract_boundary detail; no contract substitution or stitching',
        common_defined_accuracy_sample='design_eligible AND benchmark_defined AND cs_defined AND ar_defined AND edge_defined',
        extra_primary_filters=False,extreme_value_diagnostic='Finite relative spread>1 flagged only; no exclusions',
        observation_level_outputs_ignored=True,raw_to_final_reproductions=int(reproduction.reproduction_passed.sum()),
        benchmark_processing_seconds=bench_seconds,estimator_audit_test_seconds=elapsed,
        total_processing_seconds_approx=bench_seconds+elapsed,
        raw_source_bytes_scanned=int(scan_table.size_bytes.sum()),raw_source_files_scanned=len(scan_table),
        raw_bloomberg_hashes_verified=len(raw),raw_provider_writes=0,
        estimator_error_columns_created=False,accuracy_or_rankings_calculated=False,HAC_or_hypothesis_tests_calculated=False,
        common_source_mechanical_link={'crypto':True,'futures':True},crypto_quote_currency='UNKNOWN',
        imdx_identity_continuity_certified=False,imdx_identity_policy='source_defined_history_retained_without_manual_stitching')
    (OUT/'step17_provider_run_spec.yaml').write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    overall=tables['definedness_summary.csv'].iloc[0].to_dict()
    review='# Step17 primary provider run and sample construction\n\n**'+status+'**.\n\n'
    review+=f'Design rows reconcile exactly: stocks 14,499; ETFs 8,649; futures 2,331; crypto 12,753; total {len(panel):,}. All four classes retain nine assets and frozen tiers, primary dates and unique keys. FX stays in scope and blocked; no substitute data.\n\n'
    review+='Definedness counts only (not accuracy comparisons):\n\n'
    for p in ['benchmark']+METHODS:
        review+=f'- {p}: {overall[p+"_defined_N"]:,} defined; {overall[p+"_undefined_N"]:,} undefined.\n'
    review+=f'\nCommon-defined accuracy sample: {overall["common_defined_accuracy_N"]:,}. See common_sample_summary.csv for class/tier counts and failure_reason_summary.csv for exact method failures. The common flag is precisely the frozen conjunction, with no spread, zero-value, outlier, liquidity, volatility or extra pair-count filter.\n\n'
    review+='Stock/ETF estimators use only acquired Bloomberg adjusted OHLC (CapChg=T, CshAdjNormal=T, CshAdjAbnormal=UNKNOWN); minute benchmarks use official First Rate RTH. IMDX source-defined history is retained without stitching and remains uncertified. Futures use exactly provider-mapped individual unadjusted contracts and explicit frozen sessions; multi-day contract crossings fail before formula execution, while same-day Roll remains eligible. Crypto uses actual UTC days, UNKNOWN formal quote currency and common-source mechanical dependence.\n\n'
    review+='The Roll arithmetic kernel is unchanged; the sole interface extension forwards the verified futures registry. Its pre-extension source hash is proven to equal the Step10 source hash. Step15 estimator kernels and mapping files are unchanged. Scheduled missing periods are never compressed; supporting dates are not promoted to primary targets.\n\n'
    review+='Every defined primary output is finite/nonnegative, bps reconciles, and undefined spreads remain NaN. All raw-negative observations have finite computable raw estimates and remain defined. CS separately floors component intervals before averaging; a negative raw daily mean need not imply a zero corrected daily mean. Extreme finite values>1 relative are diagnostic flags only, never exclusions. Distribution diagnostics do not compare to Roll or rank methods.\n\n'
    review+=f'Five deterministic reproductions passed ({int(reproduction.reproduction_passed.sum())}/5), using sorted-key midpoint rules independent of outputs. The summary contains keys/pass flags only; exact cached workbook inputs, raw minute captures, OHLCV reconstruction, Roll pair counts and estimator values are in ignored data/analytic/provider_run/raw_to_final_reproduction.json.\n\n'
    review+=f'Tests: {tests["passed"]} passed, {tests["failed"]} failed. Approximate cumulative processing time {bench_seconds+elapsed:.1f} seconds; raw source bytes scanned {int(scan_table.size_bytes.sum()):,} across {len(scan_table)} files. Full source SHA-256 and before/after fingerprints are saved in ignored source_scan_audit.csv. All {len(raw)} Bloomberg acquisition hashes match.\n\n'
    review+='No estimator-minus-Roll differences, error columns, bias, MAE, RMSE, estimator rankings, correlations with Roll, HAC, confidence intervals, p-values, hypothesis tests or performance conclusions were computed. No winner table was produced. Raw data, prior frozen specifications and protected project documentation are unchanged. Main panel and all observation-level evidence are Git ignored.\n'
    (OUT/'step17_primary_provider_run_review.md').write_text(review,encoding='utf-8')
    manifest=dict(status=status,protected_sha256=protected,source_daily_sha256=inputs,code_sha256=eval_code,
        output_sha256={p.name:sha256(p) for p in OUT.iterdir() if p.suffix in ['.csv','.yaml','.md','.txt']},
        analytic_panel_sha256=sha256(PANEL),tests=tests)
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(tables['definedness_summary.csv'].to_string(index=False));print(status)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-tests',action='store_true')
    parser.add_argument('--wait-for-benchmarks',action='store_true')
    args=parser.parse_args()
    try: run(args.run_tests,args.wait_for_benchmarks)
    except Exception as exc:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'step17_provider_run_spec.yaml').write_text(yaml.safe_dump(dict(status='BLOCKED',step=17,blocking_issue=f'{type(exc).__name__}: {exc}')),encoding='utf-8')
        raise
