from pathlib import Path
import json
import math
import sys
import unittest

import numpy as np
import pandas as pd
import statsmodels.api as sm

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import primary_horse_race as h
import provider_run as prior
import provider_run_io as source
from bloomberg_io import sha256,verify_hashes,require_verified


class HorseRaceFormulaTests(unittest.TestCase):
    def test_sign_and_scaling_with_zero_retained(self):
        panel=pd.DataFrame(dict(asset_class=['stocks']*2,asset=['A','B'],liquidity_tier=['LOW']*2,
            target_date=['2024-01-02']*2,common_defined_accuracy_sample=[True,False],
            roll_spread_relative=[.01,.02],roll_spread_bps=[100.,200.]))
        for m in h.METHODS:
            panel[m+'_primary_spread_relative']=[0.,.03]
            panel[m+'_primary_spread_bps']=[0.,300.]
            panel[m+'_raw_negative']=[True,False]
            panel[m+'_raw_computable']=True
        output=h.build_errors(panel)
        self.assertEqual(len(output),1)
        for m in h.METHODS:
            self.assertEqual(output[m+'_error_bps'].iloc[0],-100.)
            self.assertEqual(output[m+'_absolute_error_bps'].iloc[0],100.)
            self.assertEqual(output[m+'_squared_error_bps2'].iloc[0],10000.)
            self.assertEqual(output[m+'_error_relative'].iloc[0],-.01)

    def test_metrics_hand_calculation_and_inequalities(self):
        m=h.metrics([-2.,1.,4.])
        self.assertEqual(m['bias'],1.)
        self.assertEqual(m['mae'],7/3)
        self.assertEqual(m['rmse'],math.sqrt(7))
        self.assertGreaterEqual(m['mae'],abs(m['bias']))
        self.assertGreaterEqual(m['rmse'],m['mae'])

    def test_asset_day_weighting_not_equal_dates_or_assets(self):
        frame=pd.DataFrame(dict(target_date=['2024-01-01']*3+['2024-01-03'],error=[1.,2.,3.,10.]))
        inference,daily=h.bias_hac(frame,'error')
        self.assertEqual(inference['bias_bps'],4.)
        self.assertNotEqual(inference['bias_bps'],daily.daily_mean_error.mean())
        self.assertEqual(daily.n_t.tolist(),[3,1])
        self.assertEqual(daily.target_date.tolist(),['2024-01-01','2024-01-03'])

    def test_hac_lag_deterministic_count_only(self):
        for T in [1,2,3,20,259,1000,2000]:
            self.assertEqual(h.hac_lag(T),min(math.floor(4*(T/100)**(2/9)),T-1))

    def test_hac_against_independent_statsmodels_wls(self):
        dates=[];values=[]
        for i in range(40):
            for j in range(1+i%4):
                dates.append(f'2024-{1+i//28:02d}-{1+i%28:02d}')
                values.append(math.sin(i/3)+j*.7+i*.01)
        frame=pd.DataFrame(dict(target_date=dates,error=values))
        result,daily=h.bias_hac(frame,'error')
        fit=sm.WLS(daily.daily_mean_error,np.ones((len(daily),1)),weights=daily.n_t).fit(
            cov_type='HAC',cov_kwds={'maxlags':h.hac_lag(len(daily)),'use_correction':False},use_t=False)
        self.assertAlmostEqual(result['bias_bps'],fit.params.iloc[0],places=12)
        self.assertAlmostEqual(result['hac_se_bps'],fit.bse.iloc[0],places=12)
        self.assertAlmostEqual(result['p_value_two_sided'],fit.pvalues.iloc[0],places=12)
        np.testing.assert_allclose([result['ci95_low_bps'],result['ci95_high_bps']],fit.conf_int().iloc[0],rtol=1e-12)
        self.assertFalse(result['hac_small_sample_correction'])

    def test_degenerate_hac_preserves_undefined_inference(self):
        for dates in [['2024-01-01'],['2024-01-01','2024-01-02']]:
            result,_=h.bias_hac(pd.DataFrame(dict(target_date=dates,error=[1.]*len(dates))),'error')
            self.assertTrue(np.isnan(result['hac_se_bps']))
            self.assertTrue(np.isnan(result['p_value_two_sided']))
            self.assertTrue(result['inference_status'].startswith('UNDEFINED'))

    def test_separate_rankings_mixed_and_ties_no_composite(self):
        rows=pd.DataFrame(dict(reporting_scope=['overall']*3,asset_class=['ALL']*3,liquidity_tier=['ALL']*3,
            estimator=['CS','AR','EDGE'],mae_bps=[1.,2.,3.],rmse_bps=[5.,4.,3.],bias_bps=[.5,.2,.1]))
        ranks=h.rank_results(rows)
        self.assertEqual(ranks.mae_rank.tolist(),[1,2,3])
        self.assertEqual(ranks.rmse_rank.tolist(),[3,2,1])
        self.assertEqual(ranks.absolute_bias_rank.tolist(),[3,2,1])
        self.assertTrue(ranks.accuracy_leader_status.eq('MIXED').all())
        self.assertFalse(any('composite' in x or 'average_rank' in x for x in ranks.columns))
        rows['rmse_bps']=[1.,1.,3.];rows['mae_bps']=[1.,1.,3.]
        ranks=h.rank_results(rows)
        self.assertEqual(ranks.mae_rank.tolist(),[1,1,3])
        self.assertTrue(ranks.lowest_both_mae_and_rmse.iloc[:2].all())

    def test_failure_and_negative_denominators_not_common(self):
        frame=pd.DataFrame(dict(asset_class=['stocks']*3,liquidity_tier=['LOW']*3,design_eligible=True,
            benchmark_defined=[True,False,True],roll_failure_reason=['','insufficient_minute_bars',''],
            common_defined_accuracy_sample=[True,False,False]))
        for m in h.METHODS:
            frame[m+'_defined']=[True,True,False]
            frame[m+'_failure_reason']=['','','missing_required_field']
            frame[m+'_raw_signed_spread_relative']=[-1.,2.,np.nan]
            frame[m+'_raw_moment']=[-1.,4.,np.nan]
            frame[m+'_raw_computable']=[True,True,False]
            frame[m+'_raw_negative']=pd.array([True,False,pd.NA],dtype='boolean')
            if m!='cs': frame[m+'_s2_raw']=[-1.,4.,np.nan]
        failures,reasons,negative=h.rate_tables(frame)
        self.assertTrue(failures.denominator_N.eq(3).all())
        self.assertTrue(failures.failure_N.eq(1).all())
        self.assertTrue(negative.raw_computable_N.eq(2).all())
        self.assertTrue(negative.negative_N.eq(1).all())
        self.assertTrue(negative.negative_rate.eq(.5).all())


class HorseRaceProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel=pd.read_parquet(prior.PANEL)
        cls.common=h.build_errors(cls.panel)

    def test_exact_sample_class_tier_keys_no_fx_and_no_exclusions(self):
        reconciliation=h.reconcile_sample(self.panel)
        self.assertTrue(reconciliation.reconciled.all())
        self.assertEqual(len(self.common),24377)
        self.assertEqual(self.common.groupby('asset_class').size().to_dict(),
            dict(stocks=9707,etfs=3175,futures=1667,crypto=9828))
        original=self.panel.loc[self.panel.common_defined_accuracy_sample,['asset_class','asset','target_date']].reset_index(drop=True)
        pd.testing.assert_frame_equal(original,self.common[['asset_class','asset','target_date']].reset_index(drop=True))

    def test_frozen_calendars_universes_tiers_and_formulas(self):
        prior.validate_panel(self.panel,source.frozen_design())
        source.verify_frozen()
        self.assertTrue(source.roll_interface_unchanged())

    def test_zero_floored_negative_rows_remain_common(self):
        for m in h.METHODS:
            mask=self.panel.common_defined_accuracy_sample&self.panel[m+'_raw_negative'].eq(True).fillna(False)&self.panel[m+'_primary_spread_bps'].eq(0)
            self.assertGreater(int(mask.sum()),0)
            expected=set(map(tuple,self.panel.loc[mask,['asset_class','asset','target_date']].to_numpy()))
            actual=set(map(tuple,self.common.loc[self.common[m+'_raw_negative'].eq(True).fillna(False)&self.common[m+'_primary_spread_bps'].eq(0),['asset_class','asset','target_date']].to_numpy()))
            self.assertEqual(expected,actual)

    def test_errors_scaling_and_metric_identities(self):
        for m in h.METHODS:
            error=self.common[m+'_error_bps']
            np.testing.assert_allclose(error,self.common[m+'_primary_spread_bps']-self.common.roll_spread_bps)
            np.testing.assert_allclose(error,10000*self.common[m+'_error_relative'],rtol=1e-12,atol=1e-10)
            for _,part in h.cells(self.common):
                metrics=h.metrics(part[m+'_error_bps'])
                self.assertGreaterEqual(metrics['mae']+1e-10,abs(metrics['bias']))
                self.assertGreaterEqual(metrics['rmse']+1e-10,metrics['mae'])

    def test_five_fixed_audits_not_replaced(self):
        audits,details=h.manual_reproductions(self.panel,self.common)
        self.assertEqual(list(zip(audits.asset_class,audits.asset,audits.target_date)),h.AUDITS)
        self.assertTrue(audits.audit_status.isin(['PASSED','NOT_COMMON_DEFINED_NOT_REPLACED']).all())
        self.assertEqual(len(details),3*audits.common_defined.sum())

    def test_all_eleven_bloomberg_hashes(self):
        raw,_=verify_hashes(h.PROJECT/'data/raw_bloomberg');require_verified(raw)
        self.assertEqual(len(raw),11)

    def test_ignored_observation_level_outputs(self):
        for path in [h.PANEL,h.DAILY,h.PANEL.parent/'primary_horse_race_reproductions.json',h.PANEL.parent/'primary_horse_race_extremes.json']:
            prior.verify_ignored(path)

    def test_prior_panel_code_and_protected_document_hashes(self):
        manifest=json.loads((prior.OUT/'run_manifest.json').read_text())
        self.assertEqual(sha256(prior.PANEL),manifest['analytic_panel_sha256'])
        for name,digest in manifest['protected_sha256'].items(): self.assertEqual(sha256(h.PROJECT/name),digest,name)
        for name,digest in manifest['code_sha256'].items(): self.assertEqual(sha256(h.PROJECT/'src'/name),digest,name)

    def test_saved_tables_when_present_common_samples_hac_bias_only(self):
        if not (h.RESULTS/'primary_accuracy_results.csv').exists():
            self.skipTest('Saved tables not yet materialized; formula and provider tests still run')
        accuracy=pd.read_csv(h.RESULTS/'primary_accuracy_results.csv')
        hac=pd.read_csv(h.RESULTS/'primary_bias_hac_results.csv')
        self.assertEqual(len(accuracy),60)
        self.assertEqual(len(hac),60)
        self.assertTrue(accuracy.groupby(h.CELL_KEYS).N_asset_days.nunique().eq(1).all())
        self.assertFalse(any('mae' in x or 'rmse' in x for x in hac.columns))
        self.assertTrue(pd.read_csv(h.OUT/'metric_identity_checks.csv').iloc[:,4:].all().all())
        self.assertTrue(pd.read_csv(h.OUT/'hac_reconciliation.csv').intercept_reconciles.all())
        for name in ['primary_accuracy_results.csv','primary_bias_hac_results.csv','failure_rates.csv','raw_negative_rates.csv']:
            self.assertNotIn('target_date',pd.read_csv(h.RESULTS/name).columns)


if __name__=='__main__': unittest.main()
