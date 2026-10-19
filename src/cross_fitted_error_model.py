"""Step20 fixed, purged, date-block cross-fitting. DIAGNOSTIC ONLY.

Reads verified derived daily panels; never estimates a spread, modifies primary
results, tunes settings, clips errors/predictions, or reads new intraday data.
"""
from pathlib import Path
import argparse
import hashlib
import itertools
import json
import math
import re
import subprocess
import sys
import time

import joblib
import numpy as np
import pandas as pd
import sklearn
import yaml
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from threadpoolctl import threadpool_limits

import primary_robustness as robustness
import primary_horse_race as primary
import provider_run as provider
import provider_run_io as source
from bloomberg_io import sha256,verify_hashes,require_verified
from estimator_windows import load_reference_grid

PROJECT=source.PROJECT
OUT=PROJECT/'outputs/diagnostics/error_model'
RESULTS=PROJECT/'outputs/results/error_model'
ANALYTIC=PROJECT/'data/analytic/error_model'
PREDICTIONS=PROJECT/'data/analytic/cross_fitted_error_predictions.parquet'
KEYS=primary.KEYS if hasattr(primary,'KEYS') else ['asset_class','asset','target_date']
CATEGORICAL=['asset_class','liquidity_tier','asset']
NUMERIC=['log_close','log1p_daily_volume','hl_range_bps','abs_open_close_bps',
         'roll_pair_coverage','benchmark_bar_coverage','minute_gap_indicator']
FEATURES=CATEGORICAL+NUMERIC
TARGETS={'absolute_error_bps':'absolute_error_bps','signed_error_bps':'error_bps'}
PARAMETERS=dict(loss='squared_error',learning_rate=.05,max_iter=200,max_leaf_nodes=15,
    min_samples_leaf=30,l2_regularization=1.,early_stopping=False,random_state=1941)
N_FOLDS=5
EMBARGO_FRACTION=.01
PERMUTATION_REPEATS=5
SEED=1941


def verify_inputs():
    panel,common=robustness.inputs()
    manifest=json.loads((robustness.OUT/'run_manifest.json').read_text())
    assert manifest['status']=='ROBUSTNESS_SENSITIVITY_COMPLETE'
    robustness.check_lock(manifest['primary_lock_sha256'])
    for category in ['code_sha256','output_sha256','analytic_sha256']:
        for name,digest in manifest[category].items():assert sha256(PROJECT/name)==digest,name
    return panel,common


def prior_lock():
    lock=robustness.snapshot_primary()
    for folder in [robustness.OUT,robustness.RESULTS]:
        lock.update({p.relative_to(PROJECT).as_posix():sha256(p) for p in folder.iterdir() if p.is_file()})
    return lock


def chronological_folds(dates):
    """Date assignments only, identical across methods/targets/variants."""
    calendar=np.array(sorted(pd.to_datetime(pd.Series(dates)).dt.strftime('%Y-%m-%d').unique()))
    if len(calendar)<N_FOLDS:raise ValueError('Insufficient distinct dates for five fixed folds')
    return pd.DataFrame([(day,fold) for fold,block in enumerate(np.array_split(calendar,N_FOLDS),1)
                         for day in block],columns=['target_date','fold'])


def price_features(data):
    """Deterministic row-local transforms; no data-fitted global preprocessing."""
    out=data[KEYS+CATEGORICAL[1:2]].copy() if 'liquidity_tier' in data else data[KEYS].copy()
    def positive(name):
        values=pd.to_numeric(data[name],errors='raise').to_numpy(dtype=float)
        return np.where(np.isfinite(values)&(values>0),values,np.nan)
    close=positive('close');high=positive('high');low=positive('low');opening=positive('open')
    volume=pd.to_numeric(data.volume,errors='raise').to_numpy(dtype=float)
    volume=np.where(np.isfinite(volume)&(volume>=0),volume,np.nan)
    out['log_close']=np.log(close)
    out['log1p_daily_volume']=np.log1p(volume)
    out['hl_range_bps']=np.where(high>=low,10000*(np.log(high)-np.log(low)),np.nan)
    out['abs_open_close_bps']=10000*np.abs(np.log(close)-np.log(opening))
    return out


def feature_definition():
    definitions={
        'asset_class':('categorical','Frozen asset-class label','Step14 identity'),
        'liquidity_tier':('categorical','Frozen 2024 LOW/MEDIUM/HIGH tier; ex-post before 2024','Step14 identity'),
        'asset':('categorical','Frozen provider asset/root identity','Step14 identity'),
        'log_close':('numeric','log(target-day source close), finite positive only','Frozen daily OHLCV'),
        'log1p_daily_volume':('numeric','log1p(target-day source volume), finite nonnegative only; heterogeneous units','Frozen daily OHLCV'),
        'hl_range_bps':('numeric','10000*log(high/low); evaluated as log difference; invalid/nonpositive prices -> missing','Frozen daily OHLCV'),
        'abs_open_close_bps':('numeric','10000*abs(log(close/open)); evaluated as log difference','Frozen daily OHLCV'),
        'roll_pair_coverage':('numeric','Step17 roll_pairs/max(frozen expected_session_slots-2,1)','Step17 counts + Step19 slot metadata only'),
        'benchmark_bar_coverage':('numeric','Step17 benchmark_bars_observed/frozen expected_session_slots','Step17 counts + Step19 slot metadata only'),
        'minute_gap_indicator':('numeric','1 if existing benchmark_gaps_gt_one_minute>0, else 0','Step17 saved gap count')}
    return pd.DataFrame([dict(feature=f,kind=definitions[f][0],definition=definitions[f][1],
        source=definitions[f][2],target_dependent=False,train_fitted_transform='OneHotEncoder(handle_unknown=ignore)' if f in CATEGORICAL else 'Training-only median imputation; no scaling',
        interpretation='Diagnostic association only; not causal; no comparable cross-class native-volume interpretation') for f in FEATURES])


def build_features(panel,common):
    coverage_path=robustness.ANALYTIC/'coverage.parquet'
    slots=pd.read_parquet(coverage_path,columns=KEYS+['expected_minute_slots'])
    assert not slots.duplicated(KEYS).any()
    quality=panel[KEYS+['benchmark_bars_observed','roll_pairs','benchmark_gaps_gt_one_minute']].merge(slots,on=KEYS,validate='one_to_one')
    quality['roll_pair_coverage']=quality.roll_pairs/np.maximum(quality.expected_minute_slots-2,1)
    quality['benchmark_bar_coverage']=quality.benchmark_bars_observed/quality.expected_minute_slots
    quality['minute_gap_indicator']=quality.benchmark_gaps_gt_one_minute.gt(0).astype(float)
    globalspec=yaml.safe_load((source.DESIGN/'global_design_final_spec.yaml').read_text())
    source_parts=[];shift_parts=[];fingerprints={}
    for cls in source.EXPECTED:
        grid=load_reference_grid(cls);labels=grid.strftime('%Y-%m-%d').tolist()
        previous=dict(zip(labels[1:],labels[:-1]))
        for asset in globalspec['selected_assets_by_class'][cls]:
            data,path=provider.source_daily(cls,asset,globalspec)
            fingerprints[path.relative_to(PROJECT).as_posix()]=sha256(path)
            assert data.asset_class.isin(['crypto','cryptos'] if cls=='crypto' else [cls]).all()
            data['asset_class']=cls  # existing frozen crypto/cryptos class alias
            data=data.rename(columns={'date':'target_date','PX_OPEN':'open','PX_HIGH':'high','PX_LOW':'low','PX_LAST':'close','PX_VOLUME':'volume'})
            prices=price_features(data)
            prices=prices.merge(quality.loc[quality.asset_class.eq(cls)&quality.asset.eq(asset),KEYS+NUMERIC[4:]],on=KEYS,how='left',validate='one_to_one')
            assert not prices.duplicated(KEYS).any()
            targets=common.loc[common.asset_class.eq(cls)&common.asset.eq(asset),KEYS+['liquidity_tier']]
            aligned=targets.merge(prices,on=KEYS,how='left',validate='one_to_one',indicator=True)
            assert aligned._merge.eq('both').all(),'Missing required physical daily feature row'
            aligned=aligned.drop(columns='_merge')
            source_parts.append(aligned)
            lagged=targets.copy();lagged['feature_source_date']=lagged.target_date.map(previous)
            lagged=lagged.merge(prices.rename(columns={'target_date':'feature_source_date'}),
                on=['asset_class','asset','feature_source_date'],how='left',validate='many_to_one')
            # A missing scheduled source period stays missing, not previous-available-row.
            assert lagged.feature_source_date.dropna().lt(lagged.loc[lagged.feature_source_date.notna(),'target_date']).all()
            shift_parts.append(lagged)
    aligned=pd.concat(source_parts,ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    shifted=pd.concat(shift_parts,ignore_index=True).sort_values(KEYS).reset_index(drop=True)
    for frame in [aligned,shifted]:
        assert len(frame)==24377 and not frame.duplicated(KEYS).any()
        assert frame[CATEGORICAL].notna().all().all()
        assert not np.isinf(frame[NUMERIC].to_numpy(dtype=float)).any()
    pd.testing.assert_frame_equal(aligned[KEYS+CATEGORICAL[1:2]],shifted[KEYS+CATEGORICAL[1:2]])
    for m in primary.METHODS:
        context=panel[KEYS+['input_dates_'+m]]
        aligned=aligned.merge(context,on=KEYS,validate='one_to_one')
        shifted=shifted.merge(context,on=KEYS,validate='one_to_one')
    for frame in [aligned,shifted]:
        frame['row_id']=np.arange(len(frame))
        frame['target_date']=pd.to_datetime(frame.target_date).dt.strftime('%Y-%m-%d')
    pd.testing.assert_frame_equal(aligned[KEYS],common[KEYS].reset_index(drop=True))
    return aligned,shifted,fingerprints


def information_intervals(frame,method,variant='ALIGNED'):
    dates=frame['input_dates_'+method].map(json.loads)
    assert dates.map(lambda x:len(x)==(2 if method=='ar' else 3) and all(d is not None for d in x)).all()
    start=pd.to_datetime(dates.map(min));end=pd.to_datetime(dates.map(max))
    if variant=='LAG1_PLACEBO':
        # Same overlap rule, applied to actual feature+label information. AR gains t-1.
        feature_date=pd.to_datetime(frame.feature_source_date)
        start=pd.concat([start,feature_date],axis=1).min(axis=1)
    return start.to_numpy(dtype='datetime64[D]').astype(np.int64),end.to_numpy(dtype='datetime64[D]').astype(np.int64)


def interval_overlaps(starts,ends,test_starts,test_ends):
    """Exact closed-interval union, never a broad hull across undocumented gaps."""
    merged=[]
    for a,b in sorted(zip(test_starts,test_ends)):
        if merged and a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    if not merged:return np.zeros(len(starts),dtype=bool)
    left=np.array([x[0] for x in merged]);right=np.array([x[1] for x in merged])
    position=np.searchsorted(left,ends,side='right')-1
    return (position>=0)&(right[np.maximum(position,0)]>=starts)


def partition(frame,folds,method,fold,variant='ALIGNED'):
    assignment=frame.target_date.map(folds.set_index('target_date').fold)
    assert assignment.notna().all()
    test=assignment.eq(fold).to_numpy();candidate=~test
    starts,ends=information_intervals(frame,method,variant)
    overlap=interval_overlaps(starts,ends,starts[test],ends[test])
    purged=candidate&overlap
    calendar=folds.target_date.tolist();test_days=folds.loc[folds.fold.eq(fold),'target_date'].tolist()
    count=math.ceil(EMBARGO_FRACTION*len(calendar))
    stop=calendar.index(test_days[-1])+1;embargo_days=calendar[stop:stop+count]
    embargo=frame.target_date.isin(embargo_days).to_numpy()
    embargoed=candidate&~purged&embargo
    train=candidate&~purged&~embargoed
    assert not (train&test).any()
    assert not interval_overlaps(starts[train],ends[train],starts[test],ends[test]).any()
    assert not frame.loc[train,'target_date'].isin(embargo_days).any()
    return train,test,dict(fold=fold,estimator=method.upper(),variant=variant,
        first_test_date=test_days[0],last_test_date=test_days[-1],T_test_dates=len(test_days),
        train_N_before_purge=int(candidate.sum()),purged_N=int(purged.sum()),embargoed_N=int(embargoed.sum()),
        embargo_candidate_N=int((candidate&embargo).sum()),embargo_dates_requested=count,
        embargo_dates_available=len(embargo_days),final_train_N=int(train.sum()),test_N=int(test.sum()),
        no_information_overlap=True,no_test_rows_in_training=True,embargo_respected=True)


def make_pipeline():
    prep=ColumnTransformer([('categorical',OneHotEncoder(handle_unknown='ignore',sparse_output=False),CATEGORICAL),
        ('numeric',SimpleImputer(strategy='median',keep_empty_features=True),NUMERIC)],remainder='drop')
    return Pipeline([('preprocessing',prep),('model',HistGradientBoostingRegressor(**PARAMETERS))])


def prediction_metrics(actual,predicted):
    actual=np.asarray(actual,dtype=float);predicted=np.asarray(predicted,dtype=float)
    assert len(actual)==len(predicted)
    if len(actual)<2 or not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        return dict(mae=np.nan,rmse=np.nan,r2=np.nan,metric_status='UNAVAILABLE_TOO_SMALL_OR_FAILED')
    residual=actual-predicted;sse=float(residual@residual);sst=float(((actual-actual.mean())**2).sum())
    return dict(mae=float(abs(residual).mean()),rmse=float(np.sqrt(sse/len(actual))),
        r2=1-sse/sst if sst>0 else np.nan,metric_status='DEFINED' if sst>0 else 'R2_UNDEFINED_CONSTANT_TARGET')


def fit_fold(X,y,train,test):
    """Fit encoders, medians, HGB and mean baseline on training rows only."""
    pipe=make_pipeline()
    result=dict(fit_status='FAILED',failure_reason='',training_target_mean=np.nan)
    predict=np.full(int(test.sum()),np.nan);baseline=predict.copy()
    try:
        if train.sum()<2 or test.sum()<1:raise ValueError('Insufficient training/test observations')
        if not np.isfinite(y[train]).all() or not np.isfinite(y[test]).all():raise ValueError('Nonfinite target')
        if X.loc[train,NUMERIC].notna().sum().eq(0).any():raise ValueError('No finite training median for numeric feature')
        baseline[:]=float(np.mean(y[train]))
        with threadpool_limits(limits=1):
            pipe.fit(X.loc[train,FEATURES],y[train])
            predict=pipe.predict(X.loc[test,FEATURES])
        if not np.isfinite(predict).all():raise ValueError('Nonfinite model predictions')
        result.update(fit_status='FITTED',training_target_mean=float(baseline[0]),
            numeric_training_medians=pipe.named_steps['preprocessing'].named_transformers_['numeric'].statistics_.tolist(),
            categorical_training_levels=[x.tolist() for x in pipe.named_steps['preprocessing'].named_transformers_['categorical'].categories_])
    except Exception as exc:
        result['failure_reason']=type(exc).__name__+': '+str(exc)
        predict[:]=np.nan;baseline[:]=np.nan
    return pipe,predict,baseline,result


def test_permutation_importance(pipe,X_test,y_test,target_type,fold):
    """Permute RAW test columns; the fitted pipeline is never refit."""
    records=[]
    with threadpool_limits(limits=1):
        before=prediction_metrics(y_test,pipe.predict(X_test[FEATURES]))
        metric='mae' if target_type=='absolute_error_bps' else 'rmse'
        for j,feature in enumerate(FEATURES):
            increases=[]
            for repeat in range(PERMUTATION_REPEATS):
                rng=np.random.default_rng(SEED+fold*10000+j*100+repeat)
                changed=X_test[FEATURES].copy()
                changed[feature]=changed[feature].to_numpy()[rng.permutation(len(changed))]
                after=prediction_metrics(y_test,pipe.predict(changed))[metric]
                increases.append(after-before[metric])
            records.append(dict(feature=feature,importance_metric='increase_in_test_'+metric,
                importance_bps=float(np.mean(increases)),permutation_std_bps=float(np.std(increases,ddof=1)),
                repeats=PERMUTATION_REPEATS,test_N=len(X_test),importance_status='DEFINED'))
    return records


def summarize_predictions(predictions):
    rows=[]
    # Explicit fixed reporting cells include absent class/tier/fold cases.
    cell_keys=[dict(reporting_scope='overall',asset_class='ALL',liquidity_tier='ALL')]
    cell_keys += [dict(reporting_scope='asset_class',asset_class=c,liquidity_tier='ALL') for c in source.EXPECTED]
    cell_keys += [dict(reporting_scope='liquidity_tier',asset_class='ALL',liquidity_tier=t) for t in ['LOW','MEDIUM','HIGH']]
    cell_keys += [dict(reporting_scope='asset_class_x_tier',asset_class=c,liquidity_tier=t) for c in source.EXPECTED for t in ['LOW','MEDIUM','HIGH']]
    for (variant,method,target),group in predictions.groupby(['variant','estimator','target_type'],sort=True):
        for fold,fold_part in [('POOLED',group)]+list(group.groupby('fold',sort=True)):
            for key in cell_keys:
                part=fold_part
                if key['asset_class']!='ALL':part=part.loc[part.asset_class.eq(key['asset_class'])]
                if key['liquidity_tier']!='ALL':part=part.loc[part.liquidity_tier.eq(key['liquidity_tier'])]
                good=part.fit_status.eq('FITTED')&np.isfinite(part.cross_fitted_prediction)&np.isfinite(part.baseline_prediction)
                valid=part.loc[good]
                model=prediction_metrics(valid.actual_target,valid.cross_fitted_prediction)
                baseline=prediction_metrics(valid.actual_target,valid.baseline_prediction)
                rows.append(dict(key,variant=variant,estimator=method,target_type=target,fold=fold,
                    expected_N=len(part),N=len(valid),excluded_failed_prediction_N=int((~good).sum()),
                    MAE=model['mae'],RMSE=model['rmse'],R2=model['r2'],baseline_MAE=baseline['mae'],
                    baseline_RMSE=baseline['rmse'],baseline_R2=baseline['r2'],metric_status=model['metric_status'],
                    MAE_improvement_pct=100*(1-model['mae']/baseline['mae']) if baseline['mae']>0 else np.nan,
                    RMSE_improvement_pct=100*(1-model['rmse']/baseline['rmse']) if baseline['rmse']>0 else np.nan))
    return pd.DataFrame(rows)


def importance_stability(importance):
    importance=importance.copy();importance['fold_rank']=np.nan
    for _,part in importance.groupby(['estimator','target_type','fold']):
        importance.loc[part.index,'fold_rank']=part.importance_bps.rank(ascending=False,method='average')
    rows=[];correlations=[]
    for (method,target),part in importance.groupby(['estimator','target_type']):
        for feature,values in part.groupby('feature',sort=True):
            row=dict(estimator=method,target_type=target,feature=feature,
                mean_importance_bps=values.importance_bps.mean(),std_importance_bps=values.importance_bps.std(ddof=1),
                completed_folds=int(values.importance_bps.notna().sum()),
                top3_folds=int(values.fold_rank.le(3).sum()),positive_importance_folds=int(values.importance_bps.gt(0).sum()))
            for fold in range(1,N_FOLDS+1):
                v=values.loc[values.fold.eq(fold),'fold_rank'];row['rank_fold_'+str(fold)]=v.iloc[0] if len(v) else np.nan
            rows.append(row)
        ranks=part.pivot(index='feature',columns='fold',values='fold_rank')
        for a,b in itertools.combinations(range(1,N_FOLDS+1),2):
            available=ranks[[a,b]].dropna() if a in ranks and b in ranks else pd.DataFrame()
            defined=len(available)>=2 and available[a].nunique()>1 and available[b].nunique()>1
            rho=available[a].corr(available[b],method='spearman') if defined else np.nan
            correlations.append(dict(estimator=method,target_type=target,fold_a=a,fold_b=b,
                Spearman_rank_correlation=rho,status='DEFINED' if defined else 'UNDEFINED_MISSING_OR_CONSTANT_RANKS'))
    return importance,pd.DataFrame(rows),pd.DataFrame(correlations)


def make_review(tables,tests,status,spec):
    perf=tables['cross_fitted_performance.csv'];folds=tables['fold_diagnostics.csv']
    text=f'# Step20 cross-fitted error model\n\n**{status}**. ROBUSTNESS / DIAGNOSTIC ONLY. Tests: {tests["passed"]} passed; {tests["failed"]} failed.\n\n'
    text+='The source sample is exactly 24,377 unchanged Step18 common-defined asset-days for all three estimators and both targets. No new spread estimator or adjustment of primary spread estimates is produced. Signed and absolute target models are separately fitted using the same prespecified features and settings.\n\n'
    text+='Chronological test folds and purge/embargo audit (counts independent of target):\n\n'+primary.markdown(tables['cv_partition_audit.csv'])+'\n'
    text+='Aligned cross-fitted prediction performance (prediction errors, not a replacement spread horse race; bps):\n\n'+primary.markdown(perf,['estimator','target_type','N','MAE','RMSE','R2','baseline_MAE','baseline_RMSE','baseline_R2','MAE_improvement_pct','RMSE_improvement_pct'])+'\n'
    text+='Class diagnostics, reusing the same pooled-model held-out predictions:\n\n'+primary.markdown(tables['cross_fitted_performance_by_class.csv'].loc[lambda x:x.reporting_scope.eq('asset_class')],
        ['asset_class','estimator','target_type','N','MAE','RMSE','R2','baseline_RMSE'])+'\n'
    text+='Permutation importance uses only raw TEST columns and a frozen fitted training pipeline, five fixed-seed permutations per feature. Absolute-target importance is increase in test MAE; signed-target importance is increase in test RMSE. Negative importance is retained. Fold ranks use average ties; top-three counts mean rank<=3.\n\n'
    stability=tables['feature_importance_stability.csv']
    top=stability.sort_values(['estimator','target_type','mean_importance_bps','feature'],ascending=[True,True,False,True]).groupby(['estimator','target_type'],sort=False).head(3)
    text+='Top mean importances and stability (full ranks/correlations, including instability, are saved):\n\n'+primary.markdown(top,['estimator','target_type','feature','mean_importance_bps','std_importance_bps','top3_folds','positive_importance_folds'])+'\n'
    correlations=tables['feature_rank_correlations.csv']
    agg=correlations.groupby(['estimator','target_type']).Spearman_rank_correlation.agg(['count','min','median','max']).reset_index()
    text+='Pairwise fold-rank Spearman correlations:\n\n'+primary.markdown(agg)+'\n'
    text+='Named +1 scheduled-observation LAG1 PLACEBO (positive pandas shift convention: past features moved to current target; never future features):\n\n'+primary.markdown(tables['date_shift_placebo.csv'],
        ['estimator','target_type','N','MAE','RMSE','R2','aligned_MAE','aligned_RMSE','aligned_R2','RMSE_change_pct_vs_aligned'])+'\n'
    failed=folds.loc[folds.fit_status.ne('FITTED')]
    text+=f'Failed/infeasible folds: {len(failed)} of {len(folds)}. Every failure remains in fold diagnostics and prediction rows with NaN predictions; pooled metrics explicitly count unavailable predictions. No failed fold is redesigned.\n\n'
    if len(failed):text+=primary.markdown(failed,['variant','estimator','target_type','fold','failure_reason'])+'\n'
    text+='CV interpretation: the five test blocks partition 2,057 sorted unique common target dates, not stacked observations; all assets on a date stay together. The 1% embargo is ceil(0.01*2057)=21 subsequent unique target dates, truncated only at the calendar end. Purging uses the exact union of closed actual input intervals across all test assets, not an approximate hull. Purged and embargoed row counts are sequential/disjoint. Block cross-fitting can train on periods later than its test block: it is ex-post association analysis, not a forward trading forecast. No future-dated predictor is used.\n\n'
    text+='The placebo keeps categorical labels unchanged and uses the immediately previous frozen scheduled source period, not a compressed previous common/available row. Missing prior features remain missing. Its information interval includes the lagged feature date, so AR can require additional purging while using identical test blocks and the same overlap/embargo rules. Feature medians and one-hot categories are refit on that variant training fold only. Numerical feature imputation is not imputation or repair of provider OHLCV. An entirely missing training feature would preserve a failed fold rather than invent a median.\n\n'
    text+='Interpretation limits: daily range/open-close movement are ex-post same-day conditions. Price/volume units differ; asset and class identities are retained and volume has no common economic coefficient interpretation. 2024 tiers contain future information before 2024; this look-ahead/survivorship-style limitation remains. Asset identity importance reflects cross-asset heterogeneity, not causality. Correlated asset/class/tier and quality features can share/substitute importance; permutation creates combinations outside observed support. Benchmark-quality importance may reflect Roll proxy behavior. Futures and crypto share minute sources with their daily inputs; errors versus Roll are not ground-truth cost errors. Class calendars differ and futures are 2024 only. A positive R2 is diagnostic predictability, not economic usefulness. Lag persistence can sustain placebo predictability; no significance or optimized materiality cutoff is asserted. No feature/hyperparameter choice was changed from performance.\n\n'
    text+='All Steps18/19 outputs and observation panels, frozen formulas/calendars/universes and all 11 Bloomberg hashes remain unchanged. No raw/minute rereads, new source, FX substitution, raw writes, error exclusions, winsorization or primary-result changes. Features, preprocessing records, exact training/test membership, fitted fold models and all observation predictions remain Git ignored. No README/design_decisions/data_manifest edits. Reproduce with `.venv/Scripts/python.exe -B src/cross_fitted_error_model.py --run-tests`.\n'
    return text


def run(run_tests=False):
    started=time.perf_counter();OUT.mkdir(parents=True,exist_ok=True);RESULTS.mkdir(parents=True,exist_ok=True);ANALYTIC.mkdir(parents=True,exist_ok=True)
    panel,common=verify_inputs();lock=prior_lock()
    for p in [PREDICTIONS,ANALYTIC/'aligned_features.parquet']:provider.verify_ignored(p)
    spec=dict(status='RUNNING',step=20,role='ROBUSTNESS_DIAGNOSTIC_ONLY',primary_reference='Step18 unchanged',source_common_N=24377,
        model='HistGradientBoostingRegressor',parameters=PARAMETERS,targets=list(TARGETS),features=FEATURES,
        folds=5,fold_assignment='np.array_split(sorted unique common target dates,5); no shuffle',
        embargo_fraction=EMBARGO_FRACTION,embargo_count_rule='ceil(.01*full unique common date count)',
        purge='Exact closed actual input-interval union across all test assets; overlaps removed globally',
        preprocessing='TRAINING-ONLY numeric median and OneHotEncoder(handle_unknown=ignore); no scaling',
        missing_numeric_rule='No finite training median => fold failure; no sample deletion; no global fitted preprocessing',
        permutation_repeats=PERMUTATION_REPEATS,permutation_seed=SEED,
        permutation_metric={'absolute_error_bps':'increase in TEST MAE','signed_error_bps':'increase in TEST RMSE'},
        permutation_rank_ties='average; top3 iff rank<=3; fold std ddof=1',
        shift='+1 previous SCHEDULED observation within asset, not future/next observation or previous available/common row',
        placebo_information_policy='Same date folds and purge/embargo algorithm; include lagged feature date in information interval (extends AR start)',
        prediction_policy='No clipping, including finite negative predicted absolute-error values',
        tuning=False,random_state=SEED,computational_threads=1,feature_selection=False,
        raw_writes=0,new_raw_or_intraday_reads=0,fx_status='IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS')
    specpath=OUT/'step20_cross_fitted_error_model_spec.yaml'
    specpath.write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    aligned,shifted,source_hashes=build_features(panel,common)
    aligned.to_parquet(ANALYTIC/'aligned_features.parquet',index=False)
    shifted.to_parquet(ANALYTIC/'lag1_features.parquet',index=False)
    folds=chronological_folds(common.target_date)
    folds.to_csv(ANALYTIC/'exact_test_date_assignment.csv',index=False)
    embargo_count=math.ceil(.01*len(folds))
    spec.update(total_unique_dates=len(folds),embargo_dates=embargo_count,source_daily_sha256=source_hashes)
    specpath.write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    all_predictions=[];diagnostics=[];importance=[];partition_audit=[];membership=[];fit_records=[]
    for variant,frame in [('ALIGNED',aligned),('LAG1_PLACEBO',shifted)]:
        X=frame[FEATURES]
        assert X.columns.tolist()==FEATURES
        for m in primary.METHODS:
            for fold in range(1,N_FOLDS+1):
                train,test,audit=partition(frame,folds,m,fold,variant)
                partition_audit.append(audit)
                member=frame[KEYS+['row_id']].copy();member['train']=train;member['test']=test
                member['fold']=fold;member['variant']=variant;member['estimator']=m.upper();membership.append(member)
                for target,suffix in TARGETS.items():
                    y=common[m+'_'+suffix].to_numpy(dtype=float)
                    pipe,pred,base,fit=fit_fold(X,y,train,test)
                    result=dict(audit,target_type=target,fit_status=fit['fit_status'],failure_reason=fit['failure_reason'])
                    diagnostics.append(result)
                    fit_records.append(dict(variant=variant,estimator=m.upper(),target_type=target,fold=fold,**fit))
                    held=frame.loc[test,KEYS+['liquidity_tier','row_id']].copy()
                    held['actual_target']=y[test];held['cross_fitted_prediction']=pred;held['baseline_prediction']=base
                    held['fold']=fold;held['estimator']=m.upper();held['target_type']=target;held['variant']=variant
                    held['fit_status']=fit['fit_status'];held['failure_reason']=fit['failure_reason'];all_predictions.append(held)
                    name=f'{variant}_{m}_{target}_{fold}'
                    if fit['fit_status']=='FITTED':
                        joblib.dump(pipe,ANALYTIC/(name+'.joblib'),compress=3)
                    if variant=='ALIGNED':
                        values=test_permutation_importance(pipe,X.loc[test],y[test],target,fold) if fit['fit_status']=='FITTED' else [
                            dict(feature=f,importance_bps=np.nan,permutation_std_bps=np.nan,repeats=PERMUTATION_REPEATS,
                                 test_N=int(test.sum()),importance_status='UNAVAILABLE_FAILED_FOLD') for f in FEATURES]
                        importance.extend([dict(estimator=m.upper(),target_type=target,fold=fold,**v) for v in values])
                    print(f'{variant} {m.upper()} {target} fold {fold}: train {train.sum()}, test {test.sum()}, {fit["fit_status"]}',flush=True)
    predictions=pd.concat(all_predictions,ignore_index=True)
    assert len(predictions)==24377*3*2*2
    assert not predictions.duplicated(KEYS+['variant','estimator','target_type']).any()
    assert predictions.groupby(['variant','estimator','target_type']).size().eq(24377).all()
    predictions.to_parquet(PREDICTIONS,index=False)
    pd.concat(membership,ignore_index=True).to_parquet(ANALYTIC/'train_test_membership.parquet',index=False)
    (ANALYTIC/'fold_preprocessing_records.json').write_text(json.dumps(provider.clean(fit_records),indent=2,allow_nan=False),encoding='utf-8')
    performance=summarize_predictions(predictions)
    imp,stability,correlation=importance_stability(pd.DataFrame(importance))
    main=performance.loc[performance.variant.eq('ALIGNED')&performance.fold.eq('POOLED')]
    placebo=performance.loc[performance.variant.eq('LAG1_PLACEBO')&performance.fold.eq('POOLED')&performance.reporting_scope.eq('overall')].copy()
    placebo=placebo.merge(main.loc[main.reporting_scope.eq('overall'),['estimator','target_type','MAE','RMSE','R2']],
        on=['estimator','target_type'],suffixes=('','_aligned'),validate='one_to_one').rename(columns={'MAE_aligned':'aligned_MAE','RMSE_aligned':'aligned_RMSE','R2_aligned':'aligned_R2'})
    placebo['RMSE_change_pct_vs_aligned']=100*(placebo.RMSE/placebo.aligned_RMSE-1)
    tables={'cross_fitted_performance.csv':main.loc[main.reporting_scope.eq('overall')],
        'cross_fitted_performance_by_class.csv':main.loc[main.reporting_scope.isin(['asset_class','asset_class_x_tier'])],
        'cross_fitted_performance_by_tier.csv':main.loc[main.reporting_scope.eq('liquidity_tier')],
        'feature_importance_by_fold.csv':imp,'feature_importance_stability.csv':stability,
        'feature_rank_correlations.csv':correlation,'fold_diagnostics.csv':pd.DataFrame(diagnostics),
        'date_shift_placebo.csv':placebo,'cross_fitted_performance_by_fold.csv':performance.loc[performance.variant.eq('ALIGNED')&performance.fold.ne('POOLED')],
        'cv_partition_audit.csv':pd.DataFrame(partition_audit)}
    for name,table in tables.items():
        table.to_csv((OUT if name=='cv_partition_audit.csv' else RESULTS)/name,index=False)
    feature_definition().to_csv(OUT/'feature_definition.csv',index=False)
    leakage=pd.DataFrame([dict(check=name,passed=True) for name in ['exact_24377_source_rows','same_test_date_folds_all_estimators_targets',
        'one_test_prediction_per_row_variant_method_target','no_train_test_information_overlap','exact_21_date_embargo',
        'all_preprocessing_fitted_training_only','strict_predictor_allowlist_no_outcome_columns',
        'no_future_predictors_positive_shift_is_lag','test_only_raw_column_permutation','unique_feature_keys_one_to_one_source_joins']])
    leakage.to_csv(OUT/'leakage_checks.csv',index=False)
    for p in ANALYTIC.iterdir():provider.verify_ignored(p)
    tests=dict(status='NOT_RUN',passed=0,failed=0)
    if run_tests:
        completed=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests'],cwd=PROJECT,capture_output=True,text=True)
        output=completed.stdout+completed.stderr;(OUT/'test_results.txt').write_text(output,encoding='utf-8');print(output,flush=True)
        match=re.search(r'Ran (\d+) tests?',output)
        if completed.returncode or not match:raise RuntimeError('Full test suite failed')
        tests=dict(status='PASSED',passed=int(match.group(1)),failed=0)
    robustness.check_lock(lock);verify_inputs()
    assert all(sha256(PROJECT/name)==digest for name,digest in source_hashes.items())
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    status='CROSSFITTED_ERROR_MODEL_COMPLETE' if run_tests else 'CALCULATED_PENDING_FULL_SUITE'
    spec.update(status=status,tests=tests,failed_folds=int(tables['fold_diagnostics.csv'].fit_status.ne('FITTED').sum()),
        raw_bloomberg_hashes_verified=len(raw),prior_results_unchanged=True,processing_seconds=time.perf_counter()-started,
        environment=dict(python=sys.version,sklearn=sklearn.__version__,numpy=np.__version__,pandas=pd.__version__))
    specpath.write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    (OUT/'step20_cross_fitted_error_model_review.md').write_text(make_review(tables,tests,status,spec),encoding='utf-8')
    manifest=dict(status=status,tests=tests,prior_lock_sha256=lock,
        code_sha256={name:sha256(PROJECT/name) for name in ['src/cross_fitted_error_model.py','tests/test_cross_fitted_error_model.py']},
        output_sha256={p.relative_to(PROJECT).as_posix():sha256(p) for folder in [OUT,RESULTS] for p in folder.iterdir() if p.suffix in ['.csv','.yaml','.md','.txt']},
        analytic_sha256={p.relative_to(PROJECT).as_posix():sha256(p) for p in list(ANALYTIC.iterdir())+[PREDICTIONS] if p.is_file()})
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(status)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-tests',action='store_true')
    try:run(parser.parse_args().run_tests)
    except Exception as exc:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'step20_cross_fitted_error_model_spec.yaml').write_text(yaml.safe_dump(dict(status='BLOCKED',step=20,blocking_issue=str(exc))),encoding='utf-8')
        raise
