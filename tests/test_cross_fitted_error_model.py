from pathlib import Path
import json
import math
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import cross_fitted_error_model as c


def synthetic(n=100):
    dates=pd.date_range('2024-01-01',periods=n)
    frame=pd.DataFrame(dict(asset_class=['stocks']*n,liquidity_tier=['LOW']*n,asset=['A']*n,
        target_date=dates.strftime('%Y-%m-%d'),row_id=np.arange(n)))
    for j,f in enumerate(c.NUMERIC):frame[f]=np.sin(np.arange(n)/10)+j
    for method in ['cs','edge']:
        frame['input_dates_'+method]=[json.dumps([(d-pd.Timedelta(days=1)).strftime('%Y-%m-%d'),d.strftime('%Y-%m-%d'),(d+pd.Timedelta(days=1)).strftime('%Y-%m-%d')]) for d in dates]
    frame['input_dates_ar']=[json.dumps([d.strftime('%Y-%m-%d'),(d+pd.Timedelta(days=1)).strftime('%Y-%m-%d')]) for d in dates]
    frame['feature_source_date']=(dates-pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    return frame


class CrossFitDefinitionTests(unittest.TestCase):
    def test_five_chronological_contiguous_folds_same_date_grouping(self):
        dates=list(reversed(pd.date_range('2024-01-01',periods=23).strftime('%Y-%m-%d').tolist()))*3
        f=c.chronological_folds(dates)
        self.assertEqual(len(f),23)
        self.assertEqual(f.fold.unique().tolist(),[1,2,3,4,5])
        self.assertTrue(f.target_date.is_monotonic_increasing)
        self.assertEqual(f.groupby('fold').size().tolist(),[5,5,5,4,4])
        self.assertFalse(f.target_date.duplicated().any())

    def test_exact_closed_interval_union_not_hull(self):
        start=np.array([0,2,3,4,6,7]);end=start.copy()
        mask=c.interval_overlaps(start,end,np.array([1,5]),np.array([2,6]))
        self.assertEqual(mask.tolist(),[False,True,False,False,True,False])
        self.assertTrue(c.interval_overlaps(np.array([2]),np.array([5]),np.array([4]),np.array([4]))[0])

    def test_purge_every_overlapping_window_and_embargo_exact_calendar(self):
        frame=synthetic(300);folds=c.chronological_folds(frame.target_date)
        for method in ['cs','ar','edge']:
            train,test,audit=c.partition(frame,folds,method,2)
            starts,ends=c.information_intervals(frame,method)
            self.assertFalse(c.interval_overlaps(starts[train],ends[train],starts[test],ends[test]).any())
            self.assertEqual(audit['embargo_dates_requested'],3)
            self.assertEqual(audit['embargo_dates_available'],3)
            following=folds.target_date.iloc[120:123]
            self.assertFalse(frame.loc[train,'target_date'].isin(following).any())
            self.assertEqual(audit['final_train_N'],audit['train_N_before_purge']-audit['purged_N']-audit['embargoed_N'])
            self.assertFalse((train&test).any())
        _,_,last=c.partition(frame,folds,'cs',5)
        self.assertEqual(last['embargo_dates_available'],0)

    def test_lag_placebo_extends_AR_interval_without_future_predictors(self):
        frame=synthetic()
        start,end=c.information_intervals(frame,'ar')
        lag_start,lag_end=c.information_intervals(frame,'ar','LAG1_PLACEBO')
        np.testing.assert_array_equal(lag_start,start-1)
        np.testing.assert_array_equal(lag_end,end)
        starts,_=c.information_intervals(frame,'cs')
        lagged,_=c.information_intervals(frame,'cs','LAG1_PLACEBO')
        np.testing.assert_array_equal(starts,lagged)

    def test_training_only_median_unknown_categories_and_mean_baseline(self):
        X=synthetic(100)[c.FEATURES];y=np.arange(100,dtype=float)
        train=np.arange(100)<80;test=~train
        X.loc[:79,'log_close']=np.tile([1.,3.,np.nan,5.],20)
        X.loc[80:,'log_close']=10000.
        X.loc[80:,'asset']='UNSEEN_TEST_ASSET'
        pipe,pred,base,fit=c.fit_fold(X,y,train,test)
        self.assertEqual(fit['fit_status'],'FITTED')
        self.assertEqual(fit['numeric_training_medians'][0],3.)
        self.assertNotIn('UNSEEN_TEST_ASSET',fit['categorical_training_levels'][2])
        np.testing.assert_array_equal(base,np.full(20,39.5))
        self.assertTrue(np.isfinite(pred).all())

    def test_exact_fixed_parameters_no_tuning_and_determinism(self):
        expected=dict(loss='squared_error',learning_rate=.05,max_iter=200,max_leaf_nodes=15,
            min_samples_leaf=30,l2_regularization=1.,early_stopping=False,random_state=1941)
        self.assertEqual(c.PARAMETERS,expected)
        pipe=c.make_pipeline()
        for key,value in expected.items():self.assertEqual(pipe.named_steps['model'].get_params()[key],value)
        X=synthetic()[c.FEATURES];y=np.sin(np.arange(100)/10)
        train=np.arange(100)<80;test=~train
        first=c.fit_fold(X,y,train,test)[1];second=c.fit_fold(X,y,train,test)[1]
        np.testing.assert_array_equal(first,second)

    def test_failed_fold_preserved_no_invented_global_median(self):
        X=synthetic()[c.FEATURES];y=np.arange(100,dtype=float)
        train=np.arange(100)<80;test=~train;X.loc[train,'log_close']=np.nan
        _,pred,base,result=c.fit_fold(X,y,train,test)
        self.assertEqual(result['fit_status'],'FAILED')
        self.assertIn('No finite training median',result['failure_reason'])
        self.assertTrue(np.isnan(pred).all() and np.isnan(base).all())
        self.assertEqual(len(pred),20)

    def test_test_only_permutation_never_refits_and_is_deterministic(self):
        X=synthetic()[c.FEATURES];y=np.arange(100,dtype=float)
        train=np.arange(100)<80;test=~train
        pipe,_,_,fit=c.fit_fold(X,y,train,test)
        before=X.loc[test].copy(deep=True)
        with patch.object(pipe,'fit',side_effect=AssertionError('Permutation must not fit')):
            one=c.test_permutation_importance(pipe,X.loc[test],y[test],'absolute_error_bps',1)
            two=c.test_permutation_importance(pipe,X.loc[test],y[test],'absolute_error_bps',1)
        self.assertEqual(one,two)
        self.assertTrue(all(x['test_N']==20 for x in one))
        self.assertTrue(all(x['importance_metric']=='increase_in_test_mae' for x in one))
        self.assertEqual({x['feature'] for x in one},set(c.FEATURES))
        pd.testing.assert_frame_equal(before,X.loc[test])

    def test_metric_formulas_and_degenerate_R2(self):
        m=c.prediction_metrics([1.,2.,3.],[2.,2.,2.])
        self.assertAlmostEqual(m['mae'],2/3)
        self.assertAlmostEqual(m['rmse'],np.sqrt(2/3))
        self.assertEqual(m['r2'],0.)
        self.assertTrue(np.isnan(c.prediction_metrics([1.],[2.])['r2']))
        self.assertTrue(np.isnan(c.prediction_metrics([1.,1.],[1.,1.])['r2']))

    def test_feature_allowlist_excludes_outputs_errors_flags_and_dates(self):
        self.assertEqual(len(c.FEATURES),10)
        forbidden={'roll_spread_bps','cs_primary_spread_bps','ar_primary_spread_bps','edge_primary_spread_bps',
            'absolute_error_bps','signed_error_bps','squared_error','raw_negative','estimator_defined','fold','target_date','row_id'}
        self.assertFalse(set(c.FEATURES)&forbidden)
        self.assertFalse(c.feature_definition().target_dependent.any())

    def test_price_features_hand_values_zero_volume_missing_no_row_deletion(self):
        data=pd.DataFrame(dict(asset_class=['stocks']*2,asset=['A']*2,target_date=['2024-01-01','2024-01-02'],
            open=[2.,1.],high=[8.,np.nan],low=[2.,1.],close=[4.,2.],volume=[0.,-1.]))
        original=data.copy(deep=True);x=c.price_features(data)
        self.assertEqual(len(x),2)
        self.assertEqual(x.log1p_daily_volume.iloc[0],0.)
        self.assertTrue(np.isnan(x.log1p_daily_volume.iloc[1]))
        self.assertAlmostEqual(x.hl_range_bps.iloc[0],10000*np.log(4))
        self.assertAlmostEqual(x.abs_open_close_bps.iloc[0],10000*np.log(2))
        pd.testing.assert_frame_equal(data,original)


class CrossFitProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel,cls.common=c.verify_inputs()

    def test_exact_primary_sample_and_step18_step19_locks(self):
        self.assertEqual(len(self.common),24377)
        lock=c.prior_lock();c.robustness.check_lock(lock)
        self.assertNotIn('fx',set(self.common.asset_class))

    def test_predictions_and_feature_rows_are_git_ignored(self):
        for path in [c.PREDICTIONS,c.ANALYTIC/'aligned_features.parquet',c.ANALYTIC/'train_test_membership.parquet']:
            c.provider.verify_ignored(path)

    def test_saved_predictions_folds_and_preprocessing_when_materialized(self):
        if not c.PREDICTIONS.exists():self.skipTest('Full model run not materialized yet')
        predictions=pd.read_parquet(c.PREDICTIONS)
        self.assertEqual(len(predictions),24377*12)
        self.assertFalse(predictions.duplicated(c.KEYS+['variant','estimator','target_type']).any())
        self.assertTrue(predictions.groupby(['variant','estimator','target_type']).size().eq(24377).all())
        self.assertTrue(predictions.groupby('target_date').fold.nunique().eq(1).all())
        aligned=pd.read_parquet(c.ANALYTIC/'aligned_features.parquet')
        lagged=pd.read_parquet(c.ANALYTIC/'lag1_features.parquet')
        pd.testing.assert_frame_equal(aligned[c.KEYS+c.CATEGORICAL[1:2]],lagged[c.KEYS+c.CATEGORICAL[1:2]])
        self.assertTrue(pd.to_datetime(lagged.feature_source_date.dropna()).lt(pd.to_datetime(lagged.loc[lagged.feature_source_date.notna(),'target_date'])).all())
        records=json.loads((c.ANALYTIC/'fold_preprocessing_records.json').read_text())
        folds=c.chronological_folds(self.common.target_date)
        self.assertEqual(len(folds),2057)
        for record in records:
            frame=aligned if record['variant']=='ALIGNED' else lagged
            train,test,audit=c.partition(frame,folds,record['estimator'].lower(),record['fold'],record['variant'])
            if record['fit_status']=='FITTED':
                np.testing.assert_allclose(record['numeric_training_medians'],frame.loc[train,c.NUMERIC].median(),rtol=1e-13,atol=1e-12)
                for field,categories in zip(c.CATEGORICAL,record['categorical_training_levels']):
                    self.assertEqual(categories,sorted(frame.loc[train,field].unique()))
                m=record['estimator'].lower();target=c.TARGETS[record['target_type']]
                self.assertAlmostEqual(record['training_target_mean'],self.common.loc[train,m+'_'+target].mean(),places=10)


if __name__=='__main__':unittest.main()
