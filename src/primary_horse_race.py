"""Step18: frozen common-sample accuracy, signed-bias HAC and descriptive evidence.

Reads the immutable Step17 derived panel only. No price estimation, raw writes,
sample tuning, robustness exclusions, or inference on MAE/RMSE.
"""
from pathlib import Path
import argparse
import json
import math
import re
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import yaml

import provider_run as prior
import provider_run_io as source
from bloomberg_io import sha256, verify_hashes, require_verified

PROJECT = source.PROJECT
OUT = PROJECT/'outputs/diagnostics/horse_race'
RESULTS = PROJECT/'outputs/results/primary'
PANEL = PROJECT/'data/analytic/primary_horse_race_common.parquet'
DAILY = PROJECT/'data/analytic/primary_bias_hac_inputs.parquet'
METHODS = ['cs', 'ar', 'edge']
EXPECTED_COMMON = {'stocks': {'LOW':2399,'MEDIUM':3827,'HIGH':3481},
    'etfs': {'LOW':245,'MEDIUM':1091,'HIGH':1839},
    'futures': {'LOW':590,'MEDIUM':556,'HIGH':521},
    'crypto': {'LOW':2292,'MEDIUM':3826,'HIGH':3710}}
AUDITS = [('stocks','FCPT','2022-10-11'),('etfs','PGJ','2024-01-30'),
    ('futures','GC','2024-07-02'),('crypto','LINK','2024-01-18'),('stocks','AIRG','2022-10-11')]
CELL_KEYS = ['reporting_scope','asset_class','liquidity_tier']


def verify_inputs():
    """Fail before metrics if any previously approved input or policy changed."""
    manifest = json.loads((prior.OUT/'run_manifest.json').read_text())
    assert manifest['status'] == 'PROVIDER_RUN_VALIDATED_FOR_HORSE_RACE'
    assert sha256(prior.PANEL) == manifest['analytic_panel_sha256']
    for name, digest in manifest['output_sha256'].items():
        assert sha256(prior.OUT/name) == digest, name
    for category, base in [('protected_sha256',PROJECT),('source_daily_sha256',PROJECT),('code_sha256',PROJECT/'src')]:
        for name, digest in manifest[category].items():
            assert sha256(base/name) == digest, name
    source.verify_frozen()
    weighting = yaml.safe_load((source.DIAG/'statistical_freeze/primary_weighting_spec.yaml').read_text())
    hac = yaml.safe_load((source.DIAG/'statistical_freeze/hac_inference_spec.yaml').read_text())
    assert weighting['primary_weighting'] == 'ASSET_DAY_WEIGHTED'
    assert hac['hac_kernel'] == 'BARTLETT'
    assert hac['sandwich_specification']['finite_sample_multiplier'].startswith('1 (uncorrected')
    raw, _ = verify_hashes(PROJECT/'data/raw_bloomberg'); require_verified(raw)
    assert len(raw) == 11
    panel = pd.read_parquet(prior.PANEL)
    prior.validate_panel(panel, source.frozen_design())
    reconcile_sample(panel)
    return panel, manifest


def reconcile_sample(panel):
    common = panel.loc[panel.common_defined_accuracy_sample]
    assert len(common) == 24377
    assert common.groupby(['asset_class','liquidity_tier']).size().to_dict() == {
        (cls,tier):n for cls,tiers in EXPECTED_COMMON.items() for tier,n in tiers.items()}
    assert not common.duplicated(['asset_class','asset','target_date']).any()
    assert 'fx' not in set(common.asset_class)
    assert panel.common_defined_accuracy_sample.equals(prior.common_mask(panel))
    return pd.DataFrame([dict(asset_class=cls,liquidity_tier=tier,
        expected_common_N=n,actual_common_N=int(((common.asset_class==cls)&(common.liquidity_tier==tier)).sum()),
        reconciled=True) for cls,tiers in EXPECTED_COMMON.items() for tier,n in tiers.items()])


def build_errors(panel):
    columns = ['asset_class','asset','liquidity_tier','target_date','common_defined_accuracy_sample',
               'roll_spread_relative','roll_spread_bps']
    for method in METHODS:
        columns += [method+s for s in ['_primary_spread_relative','_primary_spread_bps','_raw_negative','_raw_computable']]
    common = panel.loc[panel.common_defined_accuracy_sample,columns].copy()
    for method in METHODS:
        for unit in ['relative','bps']:
            error = common[method+'_primary_spread_'+unit] - common['roll_spread_'+unit]
            assert np.isfinite(error).all()
            common[method+'_error_'+unit] = error
            common[method+'_absolute_error_'+unit] = error.abs()
            common[method+'_squared_error_'+('bps2' if unit=='bps' else unit)] = error**2
        assert np.allclose(common[method+'_error_bps'],10000*common[method+'_error_relative'],rtol=1e-12,atol=1e-10)
    return common


def cells(frame):
    yield dict(reporting_scope='overall',asset_class='ALL',liquidity_tier='ALL'), frame
    for cls, part in frame.groupby('asset_class',sort=True):
        yield dict(reporting_scope='asset_class',asset_class=cls,liquidity_tier='ALL'),part
    for tier, part in frame.groupby('liquidity_tier',sort=True):
        yield dict(reporting_scope='liquidity_tier',asset_class='ALL',liquidity_tier=tier),part
    for (cls,tier),part in frame.groupby(['asset_class','liquidity_tier'],sort=True):
        yield dict(reporting_scope='asset_class_x_tier',asset_class=cls,liquidity_tier=tier),part


def metrics(errors):
    errors = np.asarray(errors,dtype=float)
    assert np.isfinite(errors).all()
    if not len(errors): return dict(bias=np.nan,mae=np.nan,rmse=np.nan)
    return dict(bias=float(errors.mean()),mae=float(np.abs(errors).mean()),
                rmse=float(np.sqrt(np.mean(errors**2))))


def hac_lag(T):
    return min(math.floor(4*(T/100)**(2/9)),T-1) if T else 0


def bias_hac(frame, error_column):
    """Exact uncorrected Step16 score sandwich for intercept-only count WLS."""
    daily = frame.groupby('target_date',sort=True)[error_column].agg(daily_mean_error='mean',n_t='size').reset_index()
    T = len(daily); N = int(daily.n_t.sum()); lag = hac_lag(T)
    alpha = float(np.average(daily.daily_mean_error,weights=daily.n_t)) if N else np.nan
    result = dict(bias_bps=alpha,T_dates=T,N_asset_days=N,hac_lag=lag,
        hac_se_bps=np.nan,ci95_low_bps=np.nan,ci95_high_bps=np.nan,p_value_two_sided=np.nan,
        hac_small_sample_correction=False,inference_status='UNDEFINED_INSUFFICIENT_DATES')
    if T < 2: return result,daily
    score = daily.n_t.to_numpy()*(daily.daily_mean_error.to_numpy()-alpha)
    meat = float(score@score)
    for k in range(1,lag+1):
        meat += 2*(1-k/(lag+1))*float(score[k:]@score[:-k])
    variance = meat/N**2
    result['inference_status'] = 'UNDEFINED_NONPOSITIVE_OR_NONFINITE_VARIANCE'
    if np.isfinite(variance) and variance > 0:
        se = math.sqrt(variance)
        result.update(hac_se_bps=se,ci95_low_bps=alpha-1.959963984540054*se,
            ci95_high_bps=alpha+1.959963984540054*se,
            p_value_two_sided=math.erfc(abs(alpha/se)/math.sqrt(2)),inference_status='DEFINED')
    return result,daily


def accuracy_tables(common):
    accuracy=[]; inference=[]; daily_parts=[]; identities=[]; reconciliation=[]
    for key,part in cells(common):
        for method in METHODS:
            row=dict(key,estimator=method.upper(),N_asset_days=len(part),T_dates=part.target_date.nunique(),
                mean_benchmark_bps=part.roll_spread_bps.mean(),
                mean_estimator_bps=part[method+'_primary_spread_bps'].mean())
            for unit in ['relative','bps']:
                row.update({name+'_'+unit:value for name,value in metrics(part[method+'_error_'+unit]).items()})
            accuracy.append(row)
            result,daily=bias_hac(part,method+'_error_bps')
            inference.append(dict(key,estimator=method.upper(),**result))
            daily_parts.append(daily.assign(**key,estimator=method.upper()))
            intercept_ok=bool(np.isclose(row['bias_bps'],result['bias_bps'],rtol=1e-12,atol=1e-10))
            assert intercept_ok
            reconciliation.append(dict(key,estimator=method.upper(),pooled_bias_bps=row['bias_bps'],
                weighted_date_intercept_bps=result['bias_bps'],difference_bps=result['bias_bps']-row['bias_bps'],
                intercept_reconciles=intercept_ok,T_dates=result['T_dates'],N_asset_days=len(part),hac_lag=result['hac_lag']))
            checks=dict(scaling_error_bps=np.allclose(part[method+'_error_bps'],10000*part[method+'_error_relative'],rtol=1e-12,atol=1e-10),
                scaling_metrics=all(np.isclose(row[n+'_bps'],10000*row[n+'_relative'],rtol=1e-12,atol=1e-10) for n in ['bias','mae','rmse']),
                mae_ge_abs_bias=row['mae_bps']+1e-10>=abs(row['bias_bps']),rmse_ge_mae=row['rmse_bps']+1e-10>=row['mae_bps'],
                common_sample_only=part.common_defined_accuracy_sample.all())
            assert all(checks.values())
            identities.append(dict(key,estimator=method.upper(),**checks))
    return tuple(pd.DataFrame(x) for x in [accuracy,inference,identities,reconciliation]),pd.concat(daily_parts,ignore_index=True)


def rate_tables(panel):
    failures=[]; reasons=[]; negatives=[]
    for key,part in cells(panel.loc[panel.design_eligible]):
        for method in ['roll']+METHODS:
            defined='benchmark_defined' if method=='roll' else method+'_defined'
            bad=~part[defined]
            failures.append(dict(key,estimator=method.upper(),failure_N=int(bad.sum()),denominator_N=len(part),failure_rate=float(bad.mean())))
            reason='roll_failure_reason' if method=='roll' else method+'_failure_reason'
            for value,n in part.loc[bad,reason].value_counts().items():
                reasons.append(dict(key,estimator=method.upper(),failure_reason=value,count=int(n)))
            if method=='roll': continue
            raw=part[method+'_raw_signed_spread_relative']
            moment=part[method+'_raw_moment']
            computable=part[method+'_raw_computable'].eq(True)&np.isfinite(raw)&np.isfinite(moment)
            assert computable.equals(part[method+'_raw_computable'])
            negative=(part[method+'_raw_negative'].eq(True).fillna(False) if method=='cs' else part[method+'_s2_raw'].lt(0))&computable
            assert part.loc[negative,method+'_defined'].all()
            denominator=int(computable.sum()); numerator=int(negative.sum())
            negatives.append(dict(key,estimator=method.upper(),negative_N=numerator,raw_computable_N=denominator,
                negative_rate=numerator/denominator if denominator else np.nan))
    return tuple(pd.DataFrame(x) for x in [failures,reasons,negatives])


def rank_results(accuracy):
    ranks=accuracy.copy()
    ranks['absolute_bias_bps']=ranks.bias_bps.abs()
    for name,col in [('mae','mae_bps'),('rmse','rmse_bps'),('absolute_bias','absolute_bias_bps')]:
        ranks[name+'_rank']=ranks.groupby(CELL_KEYS)[col].rank(method='min').astype('Int64')
    ranks['lowest_mae']=ranks.mae_rank.eq(1)
    ranks['lowest_rmse']=ranks.rmse_rank.eq(1)
    ranks['lowest_both_mae_and_rmse']=ranks.lowest_mae&ranks.lowest_rmse
    ranks['accuracy_leader_status']='MIXED'
    for _,part in ranks.groupby(CELL_KEYS):
        leaders=part.loc[part.lowest_both_mae_and_rmse,'estimator'].sort_values().tolist()
        if leaders:
            ranks.loc[part.index,'accuracy_leader_status']=('DESCRIPTIVE_LEADER: ' if len(leaders)==1 else 'TIED_DESCRIPTIVE_LEADERS: ')+','.join(leaders)
    return ranks


def asset_table(common,panel):
    rows=[]
    for (cls,asset,tier),_ in panel.groupby(['asset_class','asset','liquidity_tier'],sort=True):
        part=common.loc[common.asset_class.eq(cls)&common.asset.eq(asset)]
        for method in METHODS:
            m=metrics(part[method+'_error_bps'])
            rows.append(dict(asset_class=cls,asset=asset,liquidity_tier=tier,estimator=method.upper(),N=len(part),
                first_date=part.target_date.min() if len(part) else '',last_date=part.target_date.max() if len(part) else '',
                **{name+'_bps':v for name,v in m.items()}))
    return pd.DataFrame(rows)


def hypothesis_table(accuracy,hac,ranks,negative):
    rows=[]
    def add(hypothesis,expectation,component,**values):
        rows.append(dict(hypothesis=hypothesis,original_expectation=expectation,component=component,
            interpretation='Descriptive evidence; no metric-difference significance or causal claim',**values))
    for row in ranks.loc[ranks.estimator.eq('EDGE')].to_dict('records'):
        if row['reporting_scope'] not in ['overall','asset_class','asset_class_x_tier']: continue
        add('H1','EDGE dominates accuracy','EDGE lowest metrics',**{k:row[k] for k in CELL_KEYS},
            lowest_mae=row['lowest_mae'],lowest_rmse=row['lowest_rmse'],lowest_both=row['lowest_both_mae_and_rmse'])
    for key,part in negative.loc[negative.reporting_scope.isin(['overall','asset_class'])].groupby(CELL_KEYS):
        for row in part.to_dict('records'):
            add('H2','EDGE has the lowest raw-negative rate','Raw-negative rate',**dict(zip(CELL_KEYS,key)),
                estimator=row['estimator'],negative_N=row['negative_N'],raw_computable_N=row['raw_computable_N'],
                negative_rate=row['negative_rate'],lowest_negative_rate=row['negative_rate']==part.negative_rate.min())
    for row in hac.loc[hac.estimator.eq('CS')&hac.reporting_scope.eq('asset_class_x_tier')].to_dict('records'):
        add('H3','CS downward bias in thin/non-continuous markets','LOW is prespecified thin; MEDIUM/HIGH context',
            **{k:row[k] for k in CELL_KEYS},bias_bps=row['bias_bps'],ci95_low_bps=row['ci95_low_bps'],ci95_high_bps=row['ci95_high_bps'])
    class_ranks=ranks.loc[ranks.reporting_scope.eq('asset_class')]
    for metric in ['mae','rmse']:
        # Explicit ties are preserved in the order string; alphabet is presentation only.
        orders={cls:' < '.join('='.join(sorted(p.estimator)) for _,p in part.groupby(metric+'_rank',sort=True))
                for cls,part in class_ranks.groupby('asset_class',sort=True)}
        stable=len(set(orders.values()))==1
        for cls,order in orders.items():
            add('H4','Ranking stable across asset classes',metric.upper()+' order',asset_class=cls,
                estimator_order=order,identical_order_across_classes=stable)
    for row in accuracy.loc[accuracy.reporting_scope.isin(['asset_class','asset_class_x_tier'])].to_dict('records'):
        add('H5','Levels diverge most in crypto and small-cap/thin equity observations','Absolute accuracy levels; sampled universe only',
            **{k:row[k] for k in CELL_KEYS},estimator=row['estimator'],mae_bps=row['mae_bps'],rmse_bps=row['rmse_bps'],absolute_bias_bps=abs(row['bias_bps']))
    return pd.DataFrame(rows)


def manual_reproductions(panel,common):
    details=[]; summary=[]
    for cls,asset,day in AUDITS:
        saved=panel.loc[panel.asset_class.eq(cls)&panel.asset.eq(asset)&panel.target_date.eq(day)].iloc[0]
        included=bool(saved.common_defined_accuracy_sample)
        record=dict(asset_class=cls,asset=asset,target_date=day,common_defined=included,
            audit_status='PASSED' if included else 'NOT_COMMON_DEFINED_NOT_REPLACED')
        if included:
            final=common.loc[common.asset_class.eq(cls)&common.asset.eq(asset)&common.target_date.eq(day)].iloc[0]
            for m in METHODS:
                signed=float(saved[m+'_primary_spread_bps'])-float(saved.roll_spread_bps)
                values={'signed_error_bps':signed,'absolute_error_bps':abs(signed),'squared_error_bps2':signed*signed}
                for field,value in values.items():
                    suffix=field.replace('signed_error','error')
                    assert np.isclose(final[m+'_'+suffix],value,rtol=1e-13,atol=1e-10)
                details.append(dict(record,estimator=m.upper(),estimator_bps=float(saved[m+'_primary_spread_bps']),
                    roll_bps=float(saved.roll_spread_bps),**values))
        summary.append(record)
    return pd.DataFrame(summary),details


def markdown(frame,columns=None):
    frame=frame if columns is None else frame[columns]
    def fmt(x):
        if isinstance(x,(float,np.floating)): return f'{x:.6g}' if np.isfinite(x) else ''
        return str(x)
    return '| '+' | '.join(frame.columns)+' |\n| '+' | '.join(['---']*len(frame.columns))+' |\n'+''.join(
        '| '+' | '.join(fmt(v) for v in row)+' |\n' for row in frame.itertuples(index=False,name=None))


def make_review(tables,audits,tests,status,extremes):
    accuracy=tables['primary_accuracy_results.csv']; hac=tables['primary_bias_hac_results.csv']
    ranks=tables['descriptive_rankings.csv']; failure=tables['failure_rates.csv']; negative=tables['raw_negative_rates.csv']
    overall=accuracy.loc[accuracy.reporting_scope.eq('overall')].merge(
        hac.loc[hac.reporting_scope.eq('overall')].drop(columns='bias_bps'),
        on=CELL_KEYS+['estimator','N_asset_days','T_dates'],validate='one_to_one')
    review=f'# Step18 primary horse race\n\n**{status}**. Tests: {tests["passed"]} passed; {tests["failed"]} failed.\n\n'
    review+='All 24,377 frozen common-defined asset-days retained for every estimator. Stocks 9,707; ETFs 3,175; futures 1,667; crypto 9,828. Equal contributing asset-day weights; no post-hoc exclusions or new quality thresholds. Errors are estimator minus Roll. Headline units are bps. Relative units remain in the machine-readable results.\n\n'
    review+='Overall signed-bias inference and descriptive accuracy:\n\n'+markdown(overall,['estimator','bias_bps','hac_se_bps','ci95_low_bps','ci95_high_bps','p_value_two_sided','mae_bps','rmse_bps','N_asset_days'])+'\n'
    for scope,title in [('asset_class','Asset class'),('liquidity_tier','Liquidity tier'),('asset_class_x_tier','Class x tier')]:
        review+=title+' accuracy (MAE/RMSE descriptive; no significance tests):\n\n'+markdown(accuracy.loc[accuracy.reporting_scope.eq(scope)],['asset_class','liquidity_tier','estimator','N_asset_days','mae_bps','rmse_bps'])+'\n'
    review+='Failure rates (denominator ALL design-eligible rows; overall 38,232):\n\n'+markdown(failure.loc[failure.reporting_scope.isin(['overall','asset_class'])],['asset_class','estimator','failure_N','denominator_N','failure_rate'])+'\n'
    review+='Raw-negative rates (finite computable raw estimates, independent of common sample):\n\n'+markdown(negative.loc[negative.reporting_scope.isin(['overall','asset_class'])],['asset_class','estimator','negative_N','raw_computable_N','negative_rate'])+'\n'
    review+='Separate descriptive ranks; no composite or averaged ranking:\n\n'+markdown(ranks,['reporting_scope','asset_class','liquidity_tier','estimator','mae_rank','rmse_rank','absolute_bias_rank','accuracy_leader_status'])+'\n'
    review+='CS signed bias by class/tier, including prespecified LOW and MEDIUM/HIGH context:\n\n'+markdown(hac.loc[hac.estimator.eq('CS')&hac.reporting_scope.eq('asset_class_x_tier')],['asset_class','liquidity_tier','bias_bps','hac_se_bps','ci95_low_bps','ci95_high_bps','p_value_two_sided'])+'\n'
    evidence=tables['hypothesis_evidence.csv']
    edge=evidence.loc[evidence.hypothesis.eq('H1')]
    overall_edge=edge.loc[edge.reporting_scope.eq('overall')].iloc[0]
    review+=f'H1: EDGE lowest overall MAE={overall_edge.lowest_mae}; lowest overall RMSE={overall_edge.lowest_rmse}. '
    review+='Class and class/tier components are retained separately in hypothesis_evidence.csv; no forced binary project-wide conclusion.\n\n'
    n=negative.loc[negative.reporting_scope.eq('overall')]
    review+='H2: Overall lowest raw-negative rate: '+', '.join(n.loc[n.negative_rate.eq(n.negative_rate.min()),'estimator'])+'. Class results and exact denominators are reported above.\n\n'
    cs=hac.loc[hac.estimator.eq('CS')&hac.reporting_scope.eq('asset_class_x_tier')&hac.liquidity_tier.eq('LOW')]
    review+='H3: LOW CS bias signs: '+', '.join(f'{r.asset_class}={r.bias_bps:.6g} bps' for r in cs.itertuples())+'. CIs above concern signed bias against zero, not causal effects or estimator-difference tests.\n\n'
    review+='H4: Separate class orders (ties explicit):\n\n'+markdown(evidence.loc[evidence.hypothesis.eq('H4')],['component','asset_class','estimator_order','identical_order_across_classes'])+'\n'
    review+='H5: Levels by class and tier are reported without reclassifying thinness or claiming market-wide/small-cap representativeness. The sampled equity tiers measure 2024 liquidity, not a frozen market-cap classification.\n\n'
    review+='Extreme finite errors were retained. The largest absolute error per class/method was inspected descriptively; observation-level keys/values and squared-error contributions are saved only in ignored data/analytic/primary_horse_race_extremes.json. These are maxima inspections, not influence-removal tests.\n\n'
    review+=markdown(extremes)+'\nDeterministic error reproductions (no replacement when not common-defined):\n\n'+markdown(audits)+'\n'
    review+='HAC is signed-bias only: chronological contributing-date means, WLS count weights n_t, Bartlett L=min(floor(4*(T/100)^(2/9)),T-1), no small-sample multiplier (False, already frozen in Step16), normal 95% CI and two-sided p-value. The WLS intercept reconciles to pooled asset-day bias in every cell. No empty dates inserted. Degenerate cells retain undefined inference reasons. Rankings are descriptive with ties; no statistical superiority test for MAE/RMSE.\n\n'
    review+='Limitations: Roll is a sampled transaction-close proxy, not true effective cost; sparse sessions and the minimum two covariance pairs affect precision. Common-defined conditioning may select observations economically. Overall/class comparisons have unequal calendar support and asset-day composition. Futures primary support is 2024 only, the calibration year; tiers use ex-post 2024 information for pre-2024 observations. Futures/crypto share minute sources across daily estimators and Roll. Crypto quote currency UNKNOWN; dimensionless/bps outputs do not imply USD. Bloomberg abnormal-dividend setting UNKNOWN and EOD/RTH equivalence uncertified; IMDX continuity remains uncertified with no OCX stitching. FX remains IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS; no substitute. HAC handles the frozen aggregate-date dependence convention, not all forms of panel dependence. Multiple bias tests are nominal and unadjusted; no new multiplicity convention imposed.\n\n'
    review+='All 11 Bloomberg hashes and prior frozen formulas/calendars/universes/specifications checked unchanged. No raw files were rewritten or price estimates recalculated. Observation-level errors, daily HAC inputs and reproduction details are Git ignored. No winsorization, trimming, robustness runs, hypothesis rewriting or post-hoc exclusions. Reproduce with `.venv/Scripts/python.exe -B src/primary_horse_race.py --run-tests`.\n'
    return review


def run(run_tests=False):
    started=time.perf_counter()
    OUT.mkdir(parents=True,exist_ok=True); RESULTS.mkdir(parents=True,exist_ok=True)
    panel,previous=verify_inputs()
    # Record the technical choice before reading any error or significance results.
    spec=dict(status='RUNNING',step=18,approval_date='2026-10-17',
        input_panel=prior.PANEL.relative_to(PROJECT).as_posix(),input_panel_sha256=sha256(prior.PANEL),
        accuracy_sample='common_defined_accuracy_sample == True',expected_common_N=24377,
        weighting='Equal contributing asset-day',error='primary estimator minus Roll',
        hac_small_sample_correction=False,hac_correction_basis='Explicit Step16 uncorrected multiplier 1',
        hac_lag='min(floor(4*(T/100)^(2/9)), T-1)',hac_kernel='Bartlett',
        hac_score='n_t*(daily_mean_error_t-alpha)',hac_variance='Bartlett score meat / sum(n_t)^2',
        hac_time_order='Chronological distinct contributing dates; no empty-date synthesis',
        hac_inference='Signed bias only; normal 95% CI, two-sided p-value',
        failure_denominator='ALL design-eligible asset-days',negative_denominator='finite computable RAW mathematical estimates among design-eligible rows',
        ranking='Separate min-tie ordinal MAE, RMSE, absolute-bias ranks; no composite',
        new_filters=False,post_hoc_exclusions=0,fx_status='IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS')
    spec_path=OUT/'step18_primary_horse_race_spec.yaml'
    spec_path.write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    common=build_errors(panel)
    (accuracy,hac,identities,reconciliation),daily=accuracy_tables(common)
    failure,reasons,negative=rate_tables(panel)
    ranks=rank_results(accuracy)
    tables={'primary_accuracy_results.csv':accuracy,'primary_bias_hac_results.csv':hac,
        'failure_rates.csv':failure,'failure_reason_breakdown.csv':reasons,'raw_negative_rates.csv':negative,
        'descriptive_rankings.csv':ranks,'asset_level_accuracy.csv':asset_table(common,panel),
        'hypothesis_evidence.csv':hypothesis_table(accuracy,hac,ranks,negative)}
    audits,details=manual_reproductions(panel,common)
    extreme_details=[]; extremes=[]
    for cls,part in common.groupby('asset_class',sort=True):
        for m in METHODS:
            r=part.loc[part[m+'_absolute_error_bps'].idxmax()]
            share=float(r[m+'_squared_error_bps2']/part[m+'_squared_error_bps2'].sum())
            extreme_details.append(dict(asset_class=cls,estimator=m.upper(),asset=r.asset,target_date=r.target_date,
                error_bps=float(r[m+'_error_bps']),squared_error_share=share))
            extremes.append(dict(asset_class=cls,estimator=m.upper(),max_absolute_error_bps=float(r[m+'_absolute_error_bps']),
                largest_squared_error_share=share,removed_N=0))
    for path in [PANEL,DAILY,PANEL.parent/'primary_horse_race_reproductions.json',PANEL.parent/'primary_horse_race_extremes.json']:
        prior.verify_ignored(path)
    common.to_parquet(PANEL,index=False); daily.to_parquet(DAILY,index=False)
    (PANEL.parent/'primary_horse_race_reproductions.json').write_text(json.dumps(prior.clean(details),indent=2,allow_nan=False),encoding='utf-8')
    (PANEL.parent/'primary_horse_race_extremes.json').write_text(json.dumps(prior.clean(extreme_details),indent=2,allow_nan=False),encoding='utf-8')
    for name,table in tables.items(): table.to_csv(RESULTS/name,index=False)
    for name,table in [('sample_reconciliation.csv',reconcile_sample(panel)),('metric_identity_checks.csv',identities),
        ('hac_reconciliation.csv',reconciliation),('manual_error_reproduction.csv',audits),('extreme_error_summary.csv',pd.DataFrame(extremes))]:
        table.to_csv(OUT/name,index=False)
    tests=dict(status='NOT_RUN',passed=0,failed=0)
    if run_tests:
        completed=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests'],cwd=PROJECT,capture_output=True,text=True)
        output=completed.stdout+completed.stderr
        (OUT/'test_results.txt').write_text(output,encoding='utf-8'); print(output,flush=True)
        match=re.search(r'Ran (\d+) tests?',output)
        if completed.returncode or not match: raise RuntimeError('Full suite failed')
        tests=dict(status='PASSED',passed=int(match.group(1)),failed=0)
    # Recheck immutable inputs after all calculations and tests.
    verify_inputs()
    status='PRIMARY_HORSE_RACE_COMPLETE' if tests['status']=='PASSED' else 'CALCULATED_PENDING_FULL_SUITE'
    spec.update(status=status,tests=tests,common_N=len(common),design_N=len(panel),
        reporting_cells=20,accuracy_rows=len(accuracy),manual_audits=audits.to_dict('records'),
        processing_seconds=time.perf_counter()-started,raw_bloomberg_hashes_verified=11,
        observation_panel=PANEL.relative_to(PROJECT).as_posix(),observation_level_outputs_git_ignored=True)
    spec_path.write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    (OUT/'step18_primary_horse_race_review.md').write_text(make_review(tables,audits,tests,status,pd.DataFrame(extremes)),encoding='utf-8')
    manifest=dict(status=status,tests=tests,input_provider_panel_sha256=sha256(prior.PANEL),
        code_sha256={name:sha256(PROJECT/name) for name in ['src/primary_horse_race.py','tests/test_primary_horse_race.py']},
        prior_manifest_sha256=sha256(prior.OUT/'run_manifest.json'),
        analytic_sha256={path.relative_to(PROJECT).as_posix():sha256(path) for path in [PANEL,DAILY,
            PANEL.parent/'primary_horse_race_reproductions.json',PANEL.parent/'primary_horse_race_extremes.json']},
        output_sha256={p.relative_to(PROJECT).as_posix():sha256(p) for folder in [OUT,RESULTS] for p in folder.iterdir()
            if p.suffix in ['.csv','.yaml','.md','.txt']},
        environment=dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__))
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(accuracy.loc[accuracy.reporting_scope.eq('overall')].to_string(index=False));print(status)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-tests',action='store_true')
    try: run(parser.parse_args().run_tests)
    except Exception as exc:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'step18_primary_horse_race_spec.yaml').write_text(yaml.safe_dump(dict(status='BLOCKED',step=18,blocking_issue=str(exc))),encoding='utf-8')
        raise
