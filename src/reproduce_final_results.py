"""Replay frozen-derived result aggregation into ignored staging, never prior locks."""
from pathlib import Path
import argparse
import json
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd

import primary_horse_race as h
import primary_robustness as r
import cross_fitted_error_model as c
from bloomberg_io import read_daily_values,sha256,verify_hashes,require_verified

PROJECT=c.PROJECT
STAGE=PROJECT/'data/analytic/reproduction_staging'


def compare(frames,folder,stage_name):
    records=[]
    for name,frame in frames.items():
        target=STAGE/stage_name/name;target.parent.mkdir(parents=True,exist_ok=True)
        frame.to_csv(target,index=False)
        actual=pd.read_csv(target,float_precision='round_trip')
        saved=pd.read_csv(folder/name,float_precision='round_trip')
        pd.testing.assert_frame_equal(actual,saved,check_dtype=False,check_exact=False,rtol=1e-10,atol=1e-10)
        records.append(dict(stage=stage_name,file=name,rows=len(actual),reconciled=True))
    return records


def ingest():
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    selected=pd.read_csv(c.source.FINAL/'selected_stocks_etfs.csv')
    outputs=[]
    for convention in ['adjusted','unadjusted']:
        path=PROJECT/f'data/raw_bloomberg/13-10-2026/bloomberg_daily_{convention}_raw_values.xlsx'
        frame,_=read_daily_values(path,selected,convention)
        target=STAGE/f'bloomberg/daily_{convention}.parquet';target.parent.mkdir(parents=True,exist_ok=True)
        frame.to_parquet(target,index=False)
        reference=PROJECT/f'data/interim/bloomberg/daily_{convention}.parquet'
        if reference.exists():pd.testing.assert_frame_equal(frame,pd.read_parquet(reference),check_dtype=False)
        outputs.append(dict(convention=convention,rows=len(frame),path=target.relative_to(PROJECT).as_posix(),raw_unchanged=True))
    print(json.dumps(outputs,indent=2))


def run():
    panel,common=c.verify_inputs();lock=c.prior_lock()
    STAGE.mkdir(parents=True,exist_ok=True)
    h.prior.verify_ignored(STAGE/'reconciliation.csv')
    (accuracy,hac,_,_),_=h.accuracy_tables(common)
    failure,reasons,negative=h.rate_tables(panel);ranks=h.rank_results(accuracy)
    frames=dict(zip(['primary_accuracy_results.csv','primary_bias_hac_results.csv','failure_rates.csv','failure_reason_breakdown.csv',
        'raw_negative_rates.csv','descriptive_rankings.csv','asset_level_accuracy.csv','hypothesis_evidence.csv'],
        [accuracy,hac,failure,reasons,negative,ranks,h.asset_table(common,panel),h.hypothesis_table(accuracy,hac,ranks,negative)]))
    checks=compare(frames,h.RESULTS,'Step18')
    coverage=pd.read_parquet(r.ANALYTIC/'coverage.parquet')
    quality=r.quality_sensitivity(common,coverage)
    baseline=r.summarize(common,'Primary',common)
    equal=r.summarize(common,'Equal asset weighting',common,equal_asset=True)
    edge,_=r.edge_abs(common,panel)
    outcomes=pd.read_parquet(r.ANALYTIC/'unadjusted_design_outcomes.parquet')
    private=STAGE/'Step19/analytic';private.mkdir(parents=True,exist_ok=True)
    with patch.object(r,'ANALYTIC',private):unadjusted,_,_=r.unadjusted_comparison(panel,common,outcomes)
    loo,loo_summary=r.leave_one_asset_out(common,panel);extreme,_=r.extreme_influence(common)
    stability=r.stability_table(baseline,quality,equal,unadjusted,edge)
    neg=r.unadjusted_negative_rates(outcomes)
    frames={'roll_quality_sensitivity.csv':quality,'equal_asset_weighting.csv':equal,'bloomberg_unadjusted_robustness.csv':unadjusted,
        'edge_abs_root_robustness.csv':edge,'leave_one_asset_out.csv':loo,'leave_one_asset_out_summary.csv':loo_summary,
        'extreme_observation_influence.csv':extreme,'robustness_conclusion_stability.csv':stability,
        'hypothesis_robustness_tracking.csv':r.hypothesis_tracking(stability,neg),'unadjusted_raw_negative_rates.csv':neg}
    checks+=compare(frames,r.RESULTS,'Step19')
    predictions=pd.read_parquet(c.PREDICTIONS)
    performance=c.summarize_predictions(predictions)
    main=performance.loc[performance.variant.eq('ALIGNED')&performance.fold.eq('POOLED')]
    placebo=performance.loc[performance.variant.eq('LAG1_PLACEBO')&performance.fold.eq('POOLED')&performance.reporting_scope.eq('overall')].copy()
    placebo=placebo.merge(main.loc[main.reporting_scope.eq('overall'),['estimator','target_type','MAE','RMSE','R2']],on=['estimator','target_type'],
        suffixes=('','_aligned'),validate='one_to_one').rename(columns={'MAE_aligned':'aligned_MAE','RMSE_aligned':'aligned_RMSE','R2_aligned':'aligned_R2'})
    placebo['RMSE_change_pct_vs_aligned']=100*(placebo.RMSE/placebo.aligned_RMSE-1)
    importance,stability,correlation=c.importance_stability(pd.read_csv(c.RESULTS/'feature_importance_by_fold.csv'))
    frames={'cross_fitted_performance.csv':main.loc[main.reporting_scope.eq('overall')],
        'cross_fitted_performance_by_class.csv':main.loc[main.reporting_scope.isin(['asset_class','asset_class_x_tier'])],
        'cross_fitted_performance_by_tier.csv':main.loc[main.reporting_scope.eq('liquidity_tier')],
        'cross_fitted_performance_by_fold.csv':performance.loc[performance.variant.eq('ALIGNED')&performance.fold.ne('POOLED')],
        'date_shift_placebo.csv':placebo,'feature_importance_by_fold.csv':importance,
        'feature_importance_stability.csv':stability,'feature_rank_correlations.csv':correlation}
    checks+=compare(frames,c.RESULTS,'Step20')
    r.check_lock(lock)
    result=pd.DataFrame(checks);result.to_csv(STAGE/'reconciliation.csv',index=False)
    print(result.to_string(index=False));print('FROZEN_DERIVED_RESULT_REPLAY_PASSED')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ingest-bloomberg-to-staging',action='store_true')
    args=parser.parse_args()
    if args.ingest_bloomberg_to_staging:ingest()
    else:run()
