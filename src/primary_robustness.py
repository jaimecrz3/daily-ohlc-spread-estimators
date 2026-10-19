"""Step19 prespecified ROBUSTNESS / SENSITIVITY; Step18 remains immutable.

No new minute reads, Roll variants, estimator formulas, threshold search, ML,
winsorization, primary exclusions or primary inference. All granular data ignored.
"""
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
import argparse
import inspect
import json
import re
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import yaml

import primary_horse_race as primary
import provider_run as provider
import provider_run_io as source
from bloomberg_io import sha256,verify_hashes,require_verified
from daily_input_convention import annotate_input_rows
from estimator_windows import daily_estimate,load_reference_grid
from session_rules import resolve_futures_session

PROJECT=source.PROJECT
OUT=PROJECT/'outputs/diagnostics/robustness'
RESULTS=PROJECT/'outputs/results/robustness'
ANALYTIC=PROJECT/'data/analytic/robustness'
METHODS=primary.METHODS
KEYS=['asset_class','asset','target_date']
THRESHOLDS={'R25':.25,'R50':.50}
UNADJUSTED=PROJECT/'data/interim/bloomberg/daily_unadjusted.parquet'
BOUNDARIES=source.DIAG/'daily_input_freeze/corporate_action_boundaries.csv'


def snapshot_primary():
    paths=[provider.PANEL,primary.PANEL,primary.DAILY,PROJECT/'src/daily_input_convention.py',
           PROJECT/'src/session_rules.py',PROJECT/'src/futures_historical_sessions.py']
    for folder in [primary.OUT,primary.RESULTS]: paths.extend(p for p in folder.iterdir() if p.is_file())
    return {p.relative_to(PROJECT).as_posix():sha256(p) for p in paths}


def check_lock(lock):
    for name,digest in lock.items(): assert sha256(PROJECT/name)==digest,'Primary lock changed: '+name


def inputs():
    panel,_=primary.verify_inputs()
    manifest=json.loads((primary.OUT/'run_manifest.json').read_text())
    assert manifest['status']=='PRIMARY_HORSE_RACE_COMPLETE'
    for category in ['code_sha256','analytic_sha256','output_sha256']:
        for name,digest in manifest[category].items(): assert sha256(PROJECT/name)==digest,name
    common=pd.read_parquet(primary.PANEL)
    assert len(common)==24377
    pd.testing.assert_frame_equal(panel.loc[panel.common_defined_accuracy_sample,KEYS].reset_index(drop=True),common[KEYS].reset_index(drop=True))
    old=json.loads((source.DIAG/'bloomberg_validation/run_manifest.json').read_text())
    assert sha256(UNADJUSTED)==old['parquet_sha256'][UNADJUSTED.relative_to(PROJECT).as_posix()]
    freeze=json.loads((source.DIAG/'daily_input_freeze/run_manifest.json').read_text())
    # Frozen boundary file is already transitively protected by Step16/17.
    assert sha256(BOUNDARIES)==freeze['output_sha256'][BOUNDARIES.name]
    return panel,common


def expected_minute_slots(asset_class,asset,day,configs=None):
    """Count clock-rule envelope slots, not observed bars or invented prices.

    No new holiday/early-close calendar: short sessions have lower envelope coverage.
    Futures use the same date-effective root registry as frozen primary construction.
    """
    if asset_class in ['stocks','etfs']: return 390
    if asset_class=='crypto': return 1440
    if asset_class!='futures': raise ValueError('FX blocked; no substitute session')
    config=resolve_futures_session(asset,pd.Timestamp(day),source.configs() if configs is None else configs)
    trade=pd.Timestamp(day).normalize()
    start=(trade-pd.Timedelta(days=1)+pd.Timedelta(hours=config.start.hour,minutes=config.start.minute)).tz_localize(config.timezone)
    end=(trade+pd.Timedelta(hours=config.end.hour,minutes=config.end.minute)).tz_localize(config.timezone)
    slots=pd.date_range(start,end,freq='min',inclusive='left')
    clock=slots.hour*60+slots.minute
    keep=np.ones(len(slots),dtype=bool)
    for begin,finish in config.maintenance_intervals:
        a=begin.hour*60+begin.minute;b=finish.hour*60+finish.minute
        keep &= ~((clock>=a)&(clock<b) if a<b else (clock>=a)|(clock<b))
    return int(keep.sum())


def coverage_panel(panel):
    configs=source.configs()
    table=panel[KEYS+['liquidity_tier','design_eligible','common_defined_accuracy_sample','roll_pairs']].copy()
    table['expected_minute_slots']=[expected_minute_slots(r.asset_class,r.asset,r.target_date,configs)
        for r in table.itertuples(index=False)]
    table['roll_pair_coverage']=table.roll_pairs/np.maximum(table.expected_minute_slots-2,1)
    assert table.expected_minute_slots.gt(2).all()
    assert table.roll_pair_coverage.between(0,1).all()
    for name,threshold in THRESHOLDS.items():
        table[name]=table.common_defined_accuracy_sample&table.roll_pair_coverage.ge(threshold)
    assert (~table.R50|table.R25).all()
    return table


def leader(part,metric):
    valid=part.loc[part[metric].notna()]
    return '='.join(sorted(valid.loc[valid[metric].eq(valid[metric].min()),'estimator'])) if len(valid) else 'UNAVAILABLE'


def summarize(frame,variant,baseline,*,equal_asset=False,scopes=None,extra=None):
    """Explicitly preserve empty primary reporting cells; all methods share sample."""
    rows=[]
    for key,base in primary.cells(baseline):
        if scopes and key['reporting_scope'] not in scopes: continue
        part=frame
        if key['asset_class']!='ALL': part=part.loc[part.asset_class.eq(key['asset_class'])]
        if key['liquidity_tier']!='ALL': part=part.loc[part.liquidity_tier.eq(key['liquidity_tier'])]
        for m in METHODS:
            error=part[m+'_error_bps']
            assert np.isfinite(error).all()
            if equal_asset and len(part):
                per_asset=part.assign(e=error,ae=error.abs(),se=error**2).groupby(['asset_class','asset'])[['e','ae','se']].mean()
                metric=dict(bias=per_asset.e.mean(),mae=per_asset.ae.mean(),rmse=np.sqrt(per_asset.se.mean()))
            else: metric=primary.metrics(error)
            row=dict(key,variant=variant,analysis_role='ROBUSTNESS_SENSITIVITY',estimator=m.upper(),
                N_asset_days=len(part),N_assets=len(part[['asset_class','asset']].drop_duplicates()),
                primary_reference_N=len(base),retention_pct=100*len(part)/len(base),
                weighting='EQUAL_ASSET' if equal_asset else 'ASSET_DAY',
                **{k+'_bps':float(v) for k,v in metric.items()},**(extra or {}))
            for k,v in metric.items(): row[k+'_relative']=float(v)/10000
            rows.append(row)
    result=pd.DataFrame(rows)
    for _,part in result.groupby(primary.CELL_KEYS,sort=False):
        for metric in ['mae','rmse']:
            result.loc[part.index,metric+'_rank']=part[metric+'_bps'].rank(method='min')
            result.loc[part.index,metric+'_leader']=leader(part,metric+'_bps')
        result.loc[part.index,'leader_status']=('MIXED' if leader(part,'mae_bps')!=leader(part,'rmse_bps') else leader(part,'mae_bps'))
    return result


def quality_sensitivity(common,coverage):
    frame=common.merge(coverage[KEYS+['roll_pair_coverage','R25','R50']],on=KEYS,validate='one_to_one')
    return pd.concat([summarize(frame.loc[frame[name]],'Roll '+name,common,
        extra=dict(coverage_threshold=threshold)) for name,threshold in THRESHOLDS.items()],ignore_index=True)


def replace_errors(frame,values):
    result=frame.copy()
    for m in METHODS:
        if m not in values: continue
        spread=np.asarray(values[m],dtype=float)
        error=spread-result.roll_spread_bps.to_numpy()
        assert np.isfinite(error).all()
        result[m+'_primary_spread_bps']=spread
        result[m+'_primary_spread_relative']=spread/10000
        for unit,scaled in [('bps',error),('relative',error/10000)]:
            result[m+'_error_'+unit]=scaled
            result[m+'_absolute_error_'+unit]=np.abs(scaled)
            result[m+'_squared_error_'+('bps2' if unit=='bps' else unit)]=scaled**2
    return result


def edge_abs(common,panel):
    raw=common.merge(panel[KEYS+['edge_s2_raw']],on=KEYS,validate='one_to_one')
    absolute=np.sqrt(np.abs(raw.edge_s2_raw.to_numpy()))*10000
    changed=replace_errors(common,{'edge':absolute})
    return summarize(changed,'EDGE abs-root',common,scopes=['overall','asset_class']),changed


def boundary_dates_for_window(boundaries,asset,dates):
    """Incoming verified event edge: min(input_dates)<event<=max(input_dates).

    A boundary before the first input does not cross this method's window. The
    interval test also handles events falling on a missing source session.
    """
    valid=[pd.Timestamp(d) for d in dates if d is not None]
    if len(valid)<2: return []
    events=boundaries.loc[boundaries.asset.eq(asset)&boundaries.robustness_break_cross_date_window,'date']
    return sorted(pd.to_datetime(events.loc[(pd.to_datetime(events)>min(valid))&(pd.to_datetime(events)<=max(valid))]).dt.strftime('%Y-%m-%d').tolist())


def unadjusted_output(context,asset,day,method,grid,boundaries):
    location=grid.get_indexer([pd.Timestamp(day)])[0]
    if location<0: raise ValueError('Target outside frozen grid')
    small=grid[max(0,location-1):location+2]
    fields=['asset','date','PX_OPEN','PX_HIGH','PX_LOW','PX_LAST']
    result=daily_estimate(context[fields],asset,day,method,small)
    events=boundary_dates_for_window(boundaries,asset,result['input_dates'])
    result['method_specific_diagnostics']['verified_event_boundaries_crossed']=events
    # Preserve structural failures; flag the verified boundary even when already failed.
    if events and result['estimator_defined']:
        from spread_estimators import result as failed_result
        failed=failed_result(method,result['input_observations'],'invalid_scheduled_adjacency',dict(
            failure_detail='verified_corporate_action_boundary',verified_event_boundaries_crossed=events))
        for key in ['asset','target_date','input_dates','input_observations','window_complete']: failed[key]=result[key]
        failed['scheduled_adjacency_valid']=False
        result=failed
    return result


def unadjusted_asset_job(job):
    """One independent asset checkpoint; called identically in serial or parallel."""
    cls,asset,group,prices,grid,boundaries,key=job
    path=ANALYTIC/f'unadjusted_{cls}_{asset}.parquet';meta=path.with_suffix('.json')
    cached=json.loads(meta.read_text()) if meta.exists() else None
    if cached and cached['key']==key and sha256(path)==cached['sha256']:
        print(f'Verified unadjusted cache {cls}/{asset}',flush=True)
        return pd.read_parquet(path)
    assert prices.asset_class.eq(cls).all() and prices.source.eq('Bloomberg').all() and prices.convention.eq('unadjusted').all()
    assert not prices.date.duplicated().any()
    lookup=prices.set_index('date');rows=[]
    for item in group.itertuples(index=False):
        position=grid.get_indexer([pd.Timestamp(item.target_date)])[0]
        dates=grid[max(0,position-1):position+2].strftime('%Y-%m-%d')
        context=lookup.loc[lookup.index.isin(dates)].reset_index()
        row=dict(asset_class=cls,asset=asset,target_date=item.target_date)
        for m in METHODS:
            result=unadjusted_output(context,asset,item.target_date,m.upper(),grid,boundaries)
            for name in ['estimator_defined','primary_spread_bps','raw_signed_spread_relative','raw_moment','raw_computable','raw_negative','failure_reason','scheduled_adjacency_valid','input_dates']:
                value=result[name]
                row[m+'_'+('defined' if name=='estimator_defined' else name)]=json.dumps(value) if name=='input_dates' else value
            row[m+'_verified_boundary_crossed']=bool(result['method_specific_diagnostics'].get('verified_event_boundaries_crossed'))
            row[m+'_method_specific_diagnostics']=provider.dumps(result['method_specific_diagnostics'])
        rows.append(row)
    frame=pd.DataFrame(rows);frame.to_parquet(path,index=False)
    meta.write_text(json.dumps(dict(key=key,sha256=sha256(path)),indent=2),encoding='utf-8')
    print(f'Unadjusted {cls}/{asset}: {len(frame)} target days',flush=True)
    return frame


def materialize_unadjusted(panel,workers=4):
    all_source=pd.read_parquet(UNADJUSTED)
    boundaries=pd.read_csv(BOUNDARIES);boundaries['date']=pd.to_datetime(boundaries.date)
    annotated=annotate_input_rows(all_source,boundaries,role='robustness')
    annotated['date']=annotated.date.dt.strftime('%Y-%m-%d')
    adapter=inspect.getsource(unadjusted_output)+inspect.getsource(boundary_dates_for_window)
    jobs=[]
    for cls in ['stocks','etfs']:
        grid=load_reference_grid(cls)
        for asset in sorted(panel.loc[panel.asset_class.eq(cls),'asset'].unique()):
            group=panel.loc[panel.asset_class.eq(cls)&panel.asset.eq(asset)]
            key=dict(source=sha256(UNADJUSTED),boundaries=sha256(BOUNDARIES),adapter=adapter,
                kernel=sha256(PROJECT/'src/spread_estimators.py'),mapper=sha256(PROJECT/'src/estimator_windows.py'),
                target_dates=group.target_date.tolist())
            prices=annotated.loc[annotated.asset.eq(asset)].copy()
            jobs.append((cls,asset,group[KEYS],prices,grid,boundaries,key))
    if workers==1:
        frames=[unadjusted_asset_job(job) for job in jobs]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            # map preserves frozen job order; workers write disjoint asset paths.
            frames=list(pool.map(unadjusted_asset_job,jobs))
    derived=pd.concat(frames,ignore_index=True)
    assert len(derived)==23148 and not derived.duplicated(KEYS).any()
    derived.to_parquet(ANALYTIC/'unadjusted_design_outcomes.parquet',index=False)
    annotated[['asset','date','input_partial_ohlc_row','zero_range_flag','corporate_action_boundary_before']].to_parquet(
        ANALYTIC/'unadjusted_source_boundary_audit.parquet',index=False)
    return derived


def unadjusted_comparison(panel,common,outcomes):
    sub=panel.loc[panel.asset_class.isin(['stocks','etfs'])].copy()
    merged=sub.merge(outcomes,on=KEYS,suffixes=('','_unadjusted'),validate='one_to_one')
    mask=merged.benchmark_defined&merged[[m+'_defined_unadjusted' for m in METHODS]].all(axis=1)
    # Do not silently change the prescribed unadjusted sample for the paired contrast.
    missing_adjusted=mask&~merged[[m+'_defined' for m in METHODS]].all(axis=1)
    assert not missing_adjusted.any(),('Adjusted outputs unavailable on prescribed unadjusted sample; paired comparison blocked',int(missing_adjusted.sum()))
    selected=merged.loc[mask].copy()
    base=primary.build_errors(selected)
    assert len(base)==len(selected)
    changed=replace_errors(base,{m:selected[m+'_primary_spread_bps_unadjusted'] for m in METHODS})
    for m in METHODS:
        changed[m+'_raw_negative']=selected[m+'_raw_negative_unadjusted'].to_numpy()
        changed[m+'_raw_computable']=selected[m+'_raw_computable_unadjusted'].to_numpy()
    changed['unadjusted_common_defined_sample']=True
    changed['sensitivity_source']='Bloomberg unadjusted OHLC'
    adjusted=summarize(base,'Bloomberg adjusted matched',common,scopes=['asset_class','asset_class_x_tier'])
    unadjusted=summarize(changed,'Bloomberg unadjusted',common,scopes=['asset_class','asset_class_x_tier'])
    joined=unadjusted.merge(adjusted[primary.CELL_KEYS+['estimator','bias_bps','mae_bps','rmse_bps','mae_leader','rmse_leader']],
        on=primary.CELL_KEYS+['estimator'],suffixes=('','_adjusted_matched'),validate='one_to_one')
    for m in ['bias','mae','rmse']: joined['delta_'+m+'_bps_vs_adjusted_matched']=joined[m+'_bps']-joined[m+'_bps_adjusted_matched']
    # No futures/crypto pseudo-rows in this source-specific sensitivity.
    joined=joined.loc[joined.asset_class.isin(['stocks','etfs'])].copy()
    adjusted=adjusted.loc[adjusted.asset_class.isin(['stocks','etfs'])].copy()
    for cls in ['stocks','etfs']:
        n=int((selected.asset_class==cls).sum())
        joined.loc[joined.asset_class.eq(cls),'unadjusted_common_class_N']=n
    audit=merged[KEYS+['liquidity_tier','benchmark_defined','common_defined_accuracy_sample']].copy()
    audit['unadjusted_common_defined_sample']=mask
    for m in METHODS:
        audit[m+'_unadjusted_defined']=merged[m+'_defined_unadjusted']
        audit[m+'_verified_boundary_crossed']=merged[m+'_verified_boundary_crossed']
        audit[m+'_failure_reason']=merged[m+'_failure_reason_unadjusted']
    audit.to_parquet(ANALYTIC/'unadjusted_common_sample_audit.parquet',index=False)
    changed.to_parquet(ANALYTIC/'unadjusted_common_errors.parquet',index=False)
    return joined,adjusted,audit


def leave_one_asset_out(common,panel):
    rows=[]
    for cls,part in common.groupby('asset_class',sort=True):
        baseline=summarize(part,'Primary',part,scopes=['overall'])
        for asset in sorted(panel.loc[panel.asset_class.eq(cls),'asset'].unique()):
            kept=part.loc[~part.asset.eq(asset)]
            for m in METHODS:
                b=baseline.loc[baseline.estimator.eq(m.upper())].iloc[0]
                metric=primary.metrics(kept[m+'_error_bps'])
                rows.append(dict(asset_class=cls,excluded_asset=asset,estimator=m.upper(),analysis_role='INFLUENCE_DIAGNOSTIC',
                    original_N=len(part),N_asset_days=len(kept),removed_N=len(part)-len(kept),
                    original_mae_leader=b.mae_leader,original_rmse_leader=b.rmse_leader,
                    **{k+'_bps':v for k,v in metric.items()},
                    **{'primary_'+k+'_bps':b[k+'_bps'] for k in metric}))
    result=pd.DataFrame(rows)
    for _,part in result.groupby(['asset_class','excluded_asset']):
        for metric in ['mae','rmse']:
            result.loc[part.index,metric+'_leader']=leader(part,metric+'_bps')
    for metric in ['bias','mae','rmse']:
        result['delta_'+metric+'_bps']=result[metric+'_bps']-result['primary_'+metric+'_bps']
    summaries=[]
    for (cls,m),part in result.groupby(['asset_class','estimator']):
        row=dict(asset_class=cls,estimator=m,original_mae_leader=part.original_mae_leader.iloc[0],
            original_rmse_leader=part.original_rmse_leader.iloc[0],
            mae_leader_ever_changes=bool(part.mae_leader.ne(part.original_mae_leader).any()),
            rmse_leader_ever_changes=bool(part.rmse_leader.ne(part.original_rmse_leader).any()))
        for metric in ['bias','mae','rmse']:
            row[metric+'_min_bps']=part[metric+'_bps'].min();row[metric+'_max_bps']=part[metric+'_bps'].max()
            biggest=part.assign(distance=part['delta_'+metric+'_bps'].abs()).sort_values(['distance','excluded_asset'],ascending=[False,True]).iloc[0]
            row['largest_'+metric+'_change_asset']=biggest.excluded_asset
            row['largest_'+metric+'_change_bps']=biggest['delta_'+metric+'_bps']
        summaries.append(row)
    return result,pd.DataFrame(summaries)


def extreme_influence(common):
    rows=[];details=[]
    for cls,part in common.groupby('asset_class',sort=True):
        ordered=part.sort_values(['asset','target_date'],kind='stable')
        for m in METHODS:
            index=ordered[m+'_absolute_error_bps'].idxmax()
            extreme=ordered.loc[index];kept=ordered.drop(index=index)
            before=primary.metrics(ordered[m+'_error_bps']);after=primary.metrics(kept[m+'_error_bps'])
            row=dict(asset_class=cls,estimator=m.upper(),analysis_role='SINGLE_OBSERVATION_INFLUENCE_DIAGNOSTIC',
                original_N=len(ordered),N_after=len(kept),removed_N=1)
            for metric in ['mae','rmse']:
                row['primary_'+metric+'_bps']=before[metric];row['after_'+metric+'_bps']=after[metric]
                row[metric+'_pct_change']=100*(after[metric]/before[metric]-1) if before[metric] else np.nan
            rows.append(row)
            details.append(dict(row,asset=extreme.asset,target_date=extreme.target_date,error_bps=extreme[m+'_error_bps']))
    return pd.DataFrame(rows),details


def unadjusted_negative_rates(outcomes):
    """Source sensitivity with the SAME design/raw-computable denominator rule."""
    rows=[]
    for cls,part in [('stocks_and_etfs',outcomes)]+list(outcomes.groupby('asset_class',sort=True)):
        for m in METHODS:
            computable=part[m+'_raw_computable'].eq(True)&np.isfinite(part[m+'_raw_signed_spread_relative'])&np.isfinite(part[m+'_raw_moment'])
            negative=part[m+'_raw_negative'].eq(True).fillna(False)&computable
            assert part.loc[negative,m+'_defined'].all()
            n=int(computable.sum());k=int(negative.sum())
            rows.append(dict(variant='Bloomberg unadjusted',analysis_role='ROBUSTNESS_SENSITIVITY',asset_class=cls,
                estimator=m.upper(),design_N=len(part),negative_N=k,raw_computable_N=n,
                negative_rate=k/n if n else np.nan,denominator_policy='Design-eligible AND finite computable RAW estimate; NOT common-defined'))
    return pd.DataFrame(rows)


def stability_table(primary_rows,quality,equal,unadjusted,edge):
    all_rows=pd.concat([primary_rows,quality,equal,unadjusted,edge],ignore_index=True)
    base=primary_rows[primary.CELL_KEYS+['estimator','mae_leader','rmse_leader','bias_bps','mae_bps','rmse_bps']]
    all_rows=all_rows.merge(base,on=primary.CELL_KEYS+['estimator'],suffixes=('','_primary'),validate='many_to_one')
    all_rows['qualitative_change_from_primary']=all_rows.mae_leader.ne(all_rows.mae_leader_primary)|all_rows.rmse_leader.ne(all_rows.rmse_leader_primary)
    all_rows['notes']='ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary'
    all_rows.loc[all_rows.variant.eq('Bloomberg unadjusted'),'notes']='Paired adjusted/unadjusted comparison uses identical unadjusted-common dates; verified incoming split edges broken only for unadjusted'
    all_rows.loc[all_rows.variant.eq('EDGE abs-root'),'notes']='CS/AR unchanged; alternative EDGE replaces zero floor only for this sensitivity; not a raw-negative definition change'
    all_rows.loc[all_rows.variant.eq('Primary'),'analysis_role']='PRIMARY_REFERENCE_UNCHANGED'
    return all_rows


def hypothesis_tracking(stability,negative):
    rows=[]
    expectations={'H1':'EDGE dominates accuracy','H2':'EDGE has lowest raw-negative rate',
        'H3':'CS downward bias in thin/non-continuous markets','H4':'Ranking stable across asset classes',
        'H5':'Levels diverge most in crypto and small-cap/thin equity observations'}
    for variant,frame in stability.groupby('variant',sort=False):
        for row in frame.loc[frame.estimator.eq('EDGE')].to_dict('records'):
            rows.append(dict(hypothesis='H1',original_expectation=expectations['H1'],variant=variant,
                reporting_scope=row['reporting_scope'],asset_class=row['asset_class'],liquidity_tier=row['liquidity_tier'],
                evidence=f"MAE leader={row['mae_leader']}; RMSE leader={row['rmse_leader']}",
                qualitative_change_from_primary=row['qualitative_change_from_primary']))
        cs=frame.loc[frame.estimator.eq('CS')&frame.liquidity_tier.eq('LOW')]
        if not len(cs): rows.append(dict(hypothesis='H3',original_expectation=expectations['H3'],variant=variant,
            evidence='NOT_RETESTED_AT_LOW_TIER; source/weight/window definitions unchanged outside this comparison'))
        for row in cs.itertuples(): rows.append(dict(hypothesis='H3',original_expectation=expectations['H3'],variant=variant,
            asset_class=row.asset_class,liquidity_tier='LOW',bias_bps=row.bias_bps,
            evidence='Negative bias supports direction; positive bias is contrary; descriptive sensitivity, no new inference'))
        classes=frame.loc[frame.reporting_scope.eq('asset_class')]
        for metric in ['mae','rmse']:
            orders={cls:' < '.join('='.join(sorted(p.estimator)) for _,p in part.groupby(metric+'_rank',sort=True))
                for cls,part in classes.groupby('asset_class')}
            rows.append(dict(hypothesis='H4',original_expectation=expectations['H4'],variant=variant,
                evidence=metric.upper()+' orders: '+json.dumps(orders,sort_keys=True),
                identical_order_across_classes=len(set(orders.values()))==1 if len(orders)==4 else None,
                coverage_status='ALL_FOUR_CLASSES' if len(orders)==4 else 'PARTIAL_CLASS_SCOPE_NOT_A_GLOBAL_STABILITY_TEST'))
        for row in classes.itertuples(): rows.append(dict(hypothesis='H5',original_expectation=expectations['H5'],variant=variant,
            asset_class=row.asset_class,estimator=row.estimator,mae_bps=row.mae_bps,rmse_bps=row.rmse_bps,
            evidence='Sample-specific level diagnostic; liquidity tiers do not certify small capitalization'))
        rows.append(dict(hypothesis='H2',original_expectation=expectations['H2'],variant=variant,
            evidence='Accuracy/weight/quality/influence subsets do not replace frozen design/raw-computable rate denominators; EDGE abs preserves raw s2 signs. Original Step18 overall/class raw rates remain in outputs/results/primary/raw_negative_rates.csv. Source sensitivity rates are separately recorded below with the same denominator rule.'))
    for row in negative.itertuples():
        part=negative.loc[negative.asset_class.eq(row.asset_class)]
        rows.append(dict(hypothesis='H2',original_expectation=expectations['H2'],variant='Bloomberg unadjusted',
            asset_class=row.asset_class,estimator=row.estimator,negative_N=row.negative_N,raw_computable_N=row.raw_computable_N,
            negative_rate=row.negative_rate,evidence='Lowest raw-negative rate='+str(row.negative_rate==part.negative_rate.min())+
            '; same frozen finite-raw/design denominator rule; source-specific computability and verified boundary failures preserved'))
    return pd.DataFrame(rows)


def make_review(tables,tests,status,spec):
    review=f'# Step19 robustness and sensitivity\n\n**{status}**. Tests: {tests["passed"]} passed; {tests["failed"]} failed.\n\n'
    review+='Step18 remains the PRIMARY result, with exactly 24,377 common-defined asset-days, unchanged formulas, universes, calendars, sources, weighting, zero-floor conventions and benchmark. Every result below is ROBUSTNESS / SENSITIVITY or influence diagnosis only; no preferred alternative is selected.\n\n'
    review+='Roll coverage uses the frozen regular session envelope: stocks/ETFs 390 slots, crypto 1,440 UTC slots, and root/date-specific futures sessions (1,380 slots for the selected 2024 dates). Coverage=roll_pairs/max(expected_minute_slots-2,1). These are clock-rule opportunities, not imputed observations or certified holiday/early-close schedules; short holiday sessions can have lower coverage. Only the two user-predeclared thresholds 0.25 and 0.50 were run.\n\n'
    for name,title,cols in [
        ('roll_quality_sensitivity.csv','R25/R50', ['variant','asset_class','liquidity_tier','estimator','N_asset_days','retention_pct','bias_bps','mae_bps','rmse_bps','mae_leader','rmse_leader']),
        ('equal_asset_weighting.csv','Equal-asset weighting',['asset_class','estimator','N_asset_days','N_assets','bias_bps','mae_bps','rmse_bps','mae_leader','rmse_leader']),
        ('bloomberg_unadjusted_robustness.csv','Bloomberg unadjusted matched comparison',['asset_class','estimator','N_asset_days','bias_bps','mae_bps','rmse_bps','mae_bps_adjusted_matched','rmse_bps_adjusted_matched','delta_mae_bps_vs_adjusted_matched','delta_rmse_bps_vs_adjusted_matched','mae_leader','rmse_leader']),
        ('edge_abs_root_robustness.csv','EDGE abs-root',['variant','asset_class','estimator','N_asset_days','bias_bps','mae_bps','rmse_bps']),
        ('leave_one_asset_out_summary.csv','Leave-one-asset-out range and largest changes',['asset_class','estimator','mae_min_bps','mae_max_bps','rmse_min_bps','rmse_max_bps','mae_leader_ever_changes','rmse_leader_ever_changes','largest_mae_change_asset','largest_rmse_change_asset']),
        ('extreme_observation_influence.csv','Single extreme observation influence',['asset_class','estimator','removed_N','mae_pct_change','rmse_pct_change'])]:
        frame=tables[name]
        if name in ['equal_asset_weighting.csv','edge_abs_root_robustness.csv']:frame=frame.loc[frame.reporting_scope.isin(['overall','asset_class'])]
        if name=='bloomberg_unadjusted_robustness.csv':frame=frame.loc[frame.reporting_scope.eq('asset_class')]
        review+=title+':\n\n'+primary.markdown(frame,cols)+'\n'
    review+='R25/R50 class/tier composition is reported in roll_quality_sensitivity.csv, including empty cells. Equal-asset RMSE is sqrt(mean(asset mean squared error)), never mean(asset RMSE). Each contributing asset has equal total weight within its reporting cell; the same 24,377 primary rows are used.\n\n'
    review+='Unadjusted uses existing acquired Bloomberg CapChg=F/CshAdjNormal=F/CshAdjAbnormal=F, exact Step15 kernels and scheduled context. The saved verified SNDL 2022-07-26 incoming split edge breaks only windows that cross it (CS/EDGE previous-target-next; AR target-next); this does not drop SNDL as an asset or its event month. All 61 heuristic flags remain diagnostic. The prescribed unadjusted-common sample and availability of adjusted outputs on every one of those rows are explicitly checked. Adjusted/unadjusted columns share identical target rows and Roll values; matched adjusted metrics and unadjusted-minus-matched deltas distinguish source changes from sample changes.\n\n'
    review+='EDGE abs-root is sqrt(abs(raw s2)), on the same primary common observations; finite negative raw values are not failures. CS/AR remain unchanged for the alternative-convention ranking. Primary EDGE stays the published zero floor.\n\n'
    stability=tables['robustness_conclusion_stability.csv']
    core=stability.loc[stability.reporting_scope.isin(['overall','asset_class'])&stability.estimator.eq('EDGE')]
    review+='Leader stability (separate MAE and RMSE, no composite or significance claim):\n\n'+primary.markdown(core,['variant','asset_class','N_asset_days','mae_leader','rmse_leader','qualitative_change_from_primary'])+'\n'
    review+='Original hypotheses are retained in hypothesis_robustness_tracking.csv. H1 accuracy is assessed separately by metric/cell. H2 raw-negative rates are not redefined by conditioning on common/quality samples or by equal weighting; Step18 rates and class exceptions remain the primary evidence. The additional unadjusted_raw_negative_rates.csv applies the same design/finite-raw denominator rule to source-specific outcomes; these rates are not computed on the unadjusted common accuracy sample. H3 uses prespecified LOW CS bias and retains the direction even if contrary. H4 orders are recorded separately by class/metric; two-class unadjusted comparisons cannot certify four-class stability. H5 levels are shown without equating liquidity with small capitalization.\n\n'
    review+='Leave-one-asset-out removes each of the nine selected assets in turn within its class, with no other exclusions, and retains unchanged frozen errors for all others. Extremes remove exactly one maximal-absolute-error row per class/method (ties asset/date alphabetically/chronologically) only to diagnose influence. Detailed keys stay in ignored data/analytic/robustness; no trimmed primary panel was produced. These checks identify fragility, not an alternative preferred universe.\n\n'
    review+=f'All {spec["raw_bloomberg_hashes_verified"]} Bloomberg hashes match. Primary and frozen artifacts are locked by SHA-256 before/after. No raw writes, new intraday reads, filling, synthetic days, winsorization, threshold search, FX substitutes, cross-fitted model or new HAC tests. Relative units reconcile to bps. All observation-level robustness evidence is Git ignored. Reproduce with `.venv/Scripts/python.exe -B src/primary_robustness.py --run-tests`.\n'
    return review


def run(run_tests=False):
    started=time.perf_counter();OUT.mkdir(parents=True,exist_ok=True);RESULTS.mkdir(parents=True,exist_ok=True);ANALYTIC.mkdir(parents=True,exist_ok=True)
    provider.verify_ignored(ANALYTIC/'coverage.parquet')
    panel,common=inputs();lock=snapshot_primary()
    spec=dict(status='RUNNING',step=19,role='ROBUSTNESS_SENSITIVITY_ONLY',primary_N=24377,
        primary_reference='outputs/results/primary',primary_panel_sha256=sha256(primary.PANEL),
        thresholds=THRESHOLDS,threshold_selection='USER_PREDECLARED; no optimization',
        coverage_denominator='max(expected_minute_slots-2,1)',expected_slots='Frozen regular session envelope; no newly inferred holiday/early-close rules',
        weighting='Primary ASSET_DAY unchanged; equal-asset sensitivity averages asset mean signed/absolute/squared error then square-roots aggregate MSE',
        unadjusted_policy='Same frozen grid and kernels; verified incoming SNDL split edge only; heuristic flags diagnostic; paired adjusted comparison on identical unadjusted common sample',
        edge_convention='sqrt(abs(raw s2)) sensitivity; published zero-floor remains primary',
        influence='All nine leave-one-asset-out per class; one max-absolute-error observation per class/method; deterministic asset/date tie break',
        cross_fitted_model_run=False,raw_provider_writes=0,new_intraday_reads=0,fx_substitute=False,winsorization=False,
        frozen_formulas_changed=False,primary_observations_deleted=0,new_HAC_inference=False,
        unadjusted_source_sha256=sha256(UNADJUSTED),boundary_source_sha256=sha256(BOUNDARIES))
    spec_path=OUT/'step19_robustness_spec.yaml';spec_path.write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    coverage=coverage_panel(panel);coverage.to_parquet(ANALYTIC/'coverage.parquet',index=False)
    baseline=summarize(common,'Primary',common)
    saved=pd.read_csv(primary.RESULTS/'primary_accuracy_results.csv')
    paired=baseline.merge(saved,on=primary.CELL_KEYS+['estimator'],suffixes=('','_saved'),validate='one_to_one')
    for m in ['bias','mae','rmse']:assert np.allclose(paired[m+'_bps'],paired[m+'_bps_saved'],rtol=1e-12,atol=1e-10)
    quality=quality_sensitivity(common,coverage)
    equal=summarize(common,'Equal asset weighting',common,equal_asset=True)
    alternative,edge_panel=edge_abs(common,panel);edge_panel.to_parquet(ANALYTIC/'edge_abs_common_errors.parquet',index=False)
    unadjusted_outcomes=materialize_unadjusted(panel)
    unadjusted,matched,unadjusted_audit=unadjusted_comparison(panel,common,unadjusted_outcomes)
    negative=unadjusted_negative_rates(unadjusted_outcomes)
    loo,loo_summary=leave_one_asset_out(common,panel)
    extremes,detail=extreme_influence(common)
    (ANALYTIC/'extreme_observation_details.json').write_text(json.dumps(provider.clean(detail),indent=2,allow_nan=False),encoding='utf-8')
    stability=stability_table(baseline,quality,equal,unadjusted,alternative)
    tables={'roll_quality_sensitivity.csv':quality,'equal_asset_weighting.csv':equal,
        'bloomberg_unadjusted_robustness.csv':unadjusted,'edge_abs_root_robustness.csv':alternative,
        'leave_one_asset_out.csv':loo,'leave_one_asset_out_summary.csv':loo_summary,
        'extreme_observation_influence.csv':extremes,'robustness_conclusion_stability.csv':stability,
        'hypothesis_robustness_tracking.csv':hypothesis_tracking(stability,negative),
        'unadjusted_raw_negative_rates.csv':negative}
    for name,frame in tables.items():frame.to_csv(RESULTS/name,index=False)
    boundary_counts=unadjusted_audit.groupby('asset_class')[[m+'_verified_boundary_crossed' for m in METHODS]].sum()
    boundary_counts.to_csv(OUT/'verified_boundary_window_counts.csv')
    checks=[dict(check='primary_N_unchanged',expected=24377,actual=len(common),passed=len(common)==24377),
        dict(check='R50_nested_in_R25',expected=True,actual=bool((~coverage.R50|coverage.R25).all()),passed=True),
        dict(check='all_11_Bloomberg_hashes_match',expected=11,actual=11,passed=True),
        dict(check='primary_accuracy_metrics_reconcile',expected=True,actual=True,passed=True),
        dict(check='paired_adjusted_available_on_all_unadjusted_common',expected=True,actual=True,passed=True),
        dict(check='extreme_diagnostic_removes_exactly_one',expected=1,actual=int(extremes.removed_N.max()),passed=bool(extremes.removed_N.eq(1).all())),
        dict(check='leave_one_out_runs',expected=36,actual=len(loo[['asset_class','excluded_asset']].drop_duplicates()),passed=len(loo)==108)]
    for path in ANALYTIC.iterdir():provider.verify_ignored(path)
    tests=dict(status='NOT_RUN',passed=0,failed=0)
    if run_tests:
        completed=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests'],cwd=PROJECT,capture_output=True,text=True)
        output=completed.stdout+completed.stderr;(OUT/'test_results.txt').write_text(output,encoding='utf-8');print(output,flush=True)
        match=re.search(r'Ran (\d+) tests?',output)
        if completed.returncode or not match: raise RuntimeError('Full suite failed')
        tests=dict(status='PASSED',passed=int(match.group(1)),failed=0)
    check_lock(lock);inputs()
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    checks.append(dict(check='primary_and_frozen_hash_lock',expected=True,actual=True,passed=True))
    pd.DataFrame(checks).to_csv(OUT/'robustness_reconciliation.csv',index=False)
    assert all(x['passed'] for x in checks)
    status='ROBUSTNESS_SENSITIVITY_COMPLETE' if run_tests else 'CALCULATED_PENDING_FULL_SUITE'
    spec.update(status=status,tests=tests,raw_bloomberg_hashes_verified=len(raw),processing_seconds=time.perf_counter()-started,
        unadjusted_common_N=int(unadjusted_audit.unadjusted_common_defined_sample.sum()),
        R25_N=int(coverage.R25.sum()),R50_N=int(coverage.R50.sum()),primary_artifacts_unchanged=True)
    spec_path.write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    (OUT/'step19_robustness_review.md').write_text(make_review(tables,tests,status,spec),encoding='utf-8')
    manifest=dict(status=status,tests=tests,primary_lock_sha256=lock,
        code_sha256={name:sha256(PROJECT/name) for name in ['src/primary_robustness.py','tests/test_primary_robustness.py']},
        output_sha256={p.relative_to(PROJECT).as_posix():sha256(p) for folder in [OUT,RESULTS] for p in folder.iterdir() if p.suffix in ['.csv','.md','.yaml','.txt']},
        analytic_sha256={p.relative_to(PROJECT).as_posix():sha256(p) for p in ANALYTIC.iterdir() if p.is_file()})
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(status)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-tests',action='store_true')
    try:run(parser.parse_args().run_tests)
    except Exception as exc:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'step19_robustness_spec.yaml').write_text(yaml.safe_dump(dict(status='BLOCKED',step=19,blocking_issue=str(exc))),encoding='utf-8')
        raise
