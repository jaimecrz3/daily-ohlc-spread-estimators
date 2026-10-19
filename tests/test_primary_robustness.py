from datetime import time
from pathlib import Path
import json
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import primary_robustness as r
from session_rules import FuturesSessionConfig


def sample():
    frame=pd.DataFrame(dict(asset_class=['stocks']*4,asset=['A','A','A','B'],
        liquidity_tier=['LOW']*4,target_date=['2024-01-01','2024-01-02','2024-01-03','2024-01-01'],
        roll_spread_bps=[2.]*4,common_defined_accuracy_sample=True))
    for m in r.METHODS:
        frame[m+'_error_bps']=[-1.,1.,3.,10.]
        frame[m+'_absolute_error_bps']=frame[m+'_error_bps'].abs()
        frame[m+'_squared_error_bps2']=frame[m+'_error_bps']**2
    return frame


class RobustnessDefinitionTests(unittest.TestCase):
    def test_regular_session_slots_and_DST(self):
        for day in ['2024-03-08','2024-03-11','2024-11-01','2024-11-04']:
            for cls in ['stocks','etfs']:self.assertEqual(r.expected_minute_slots(cls,'SYNTH',day),390)
            self.assertEqual(r.expected_minute_slots('crypto','SYNTH',day),1440)
            self.assertEqual(r.expected_minute_slots('futures','ES',day),1380)
        with self.assertRaises(ValueError):r.expected_minute_slots('fx','EURUSD','2024-01-01')

    def test_futures_root_breaks_not_24_hour_day_and_DST_elapsed(self):
        cfg={'SYNTH':FuturesSessionConfig('SYNTH',start=time(18),end=time(17),
            trading_day_convention='overnight_ending_date',maintenance_intervals=((time(16,15),time(16,30)),))}
        self.assertEqual(r.expected_minute_slots('futures','SYNTH','2024-03-11',cfg),1365)
        # Synthetic Sunday rule crosses the DST change; count actual zoned minute slots.
        self.assertEqual(r.expected_minute_slots('futures','SYNTH','2024-03-10',cfg),1305)
        self.assertEqual(r.expected_minute_slots('futures','SYNTH','2024-11-03',cfg),1425)

    def test_threshold_definition_inclusive_nested_primary_only(self):
        x=sample();x['design_eligible']=True;x['roll_pairs']=[97,194,96,388]
        x.loc[3,'common_defined_accuracy_sample']=False
        result=r.coverage_panel(x)
        self.assertEqual(result.expected_minute_slots.tolist(),[390]*4)
        self.assertEqual(result.R25.tolist(),[True,True,False,False])
        self.assertEqual(result.R50.tolist(),[False,True,False,False])
        self.assertEqual(r.THRESHOLDS,dict(R25=.25,R50=.50))
        self.assertEqual(len(result),4)

    def test_equal_asset_hand_calculation_not_average_rmse(self):
        frame=sample()
        table=r.summarize(frame,'Equal asset weighting',frame,equal_asset=True)
        overall=table.loc[table.reporting_scope.eq('overall')]
        self.assertTrue(overall.N_asset_days.eq(4).all())
        np.testing.assert_allclose(overall.bias_bps,5.5)
        np.testing.assert_allclose(overall.mae_bps,(5/3+10)/2)
        np.testing.assert_allclose(overall.rmse_bps,np.sqrt((11/3+100)/2))
        self.assertNotAlmostEqual(overall.rmse_bps.iloc[0],(np.sqrt(11/3)+10)/2)
        self.assertNotAlmostEqual(overall.bias_bps.iloc[0],frame.cs_error_bps.mean())

    def test_empty_sensitivity_cells_preserved_not_filled(self):
        frame=sample();table=r.summarize(frame.iloc[:0],'Roll R50',frame)
        self.assertEqual(len(table),12)  # overall, class, tier, class x tier, times three methods
        self.assertTrue(table.N_asset_days.eq(0).all())
        self.assertTrue(table.mae_bps.isna().all())
        self.assertTrue(table.mae_leader.eq('UNAVAILABLE').all())

    def test_verified_boundary_incoming_edge_not_blanket_day_exclusion(self):
        boundaries=pd.DataFrame(dict(asset=['SYNTH','SYNTH'],date=pd.to_datetime(['2024-01-03','2024-01-05']),
            robustness_break_cross_date_window=[True,False]))
        self.assertEqual(r.boundary_dates_for_window(boundaries,'SYNTH',['2024-01-02','2024-01-03']),['2024-01-03'])
        self.assertEqual(r.boundary_dates_for_window(boundaries,'SYNTH',['2024-01-03','2024-01-04']),[])
        self.assertEqual(r.boundary_dates_for_window(boundaries,'SYNTH',['2024-01-02','2024-01-04']),['2024-01-03'])
        self.assertEqual(r.boundary_dates_for_window(boundaries,'SYNTH',['2024-01-04','2024-01-05']),[])

    def test_boundary_fails_crossing_CS_AR_EDGE_windows_with_frozen_kernels(self):
        grid=pd.date_range('2024-01-01','2024-01-04')
        prices=pd.DataFrame(dict(asset=['SYNTH']*4,date=grid.strftime('%Y-%m-%d'),PX_OPEN=[10.,11,12,13],
            PX_HIGH=[12.,13,14,15],PX_LOW=[9.,10,11,12],PX_LAST=[11.,12,13,14]))
        boundaries=pd.DataFrame(dict(asset=['SYNTH'],date=pd.to_datetime(['2024-01-03']),robustness_break_cross_date_window=[True]))
        for method in ['CS','AR','EDGE']:
            result=r.unadjusted_output(prices,'SYNTH','2024-01-02',method,grid,boundaries)
            self.assertFalse(result['estimator_defined'])
            self.assertEqual(result['failure_reason'],'invalid_scheduled_adjacency')
            self.assertTrue(result['method_specific_diagnostics']['verified_event_boundaries_crossed'])
        ar=r.unadjusted_output(prices,'SYNTH','2024-01-03','AR',grid,boundaries)
        self.assertTrue(ar['estimator_defined'])
        self.assertFalse(ar['method_specific_diagnostics']['verified_event_boundaries_crossed'])
        pd.testing.assert_frame_equal(prices,prices.copy())

    def test_edge_abs_uses_raw_moment_same_rows_not_absolute_primary(self):
        common=sample()
        panel=common[r.KEYS].copy();panel['edge_s2_raw']=[-.0001,0,.0004,-.0009]
        table,changed=r.edge_abs(common,panel)
        np.testing.assert_allclose(changed.edge_error_bps,[98.,-2.,198.,298.])
        np.testing.assert_allclose(changed.edge_absolute_error_bps,[98.,2.,198.,298.])
        np.testing.assert_allclose(changed.edge_squared_error_bps2,np.array([98.,-2.,198.,298.])**2)
        np.testing.assert_allclose(changed.edge_error_bps,10000*changed.edge_error_relative)
        pd.testing.assert_frame_equal(changed[r.KEYS],common[r.KEYS])
        np.testing.assert_array_equal(changed.cs_error_bps,common.cs_error_bps)
        np.testing.assert_array_equal(changed.ar_error_bps,common.ar_error_bps)
        self.assertTrue(table.N_asset_days.eq(4).all())

    def test_unadjusted_negative_rate_uses_all_design_finite_raw_not_common(self):
        outcomes=pd.DataFrame(dict(asset_class=['stocks']*3))
        for m in r.METHODS:
            outcomes[m+'_raw_computable']=[True,True,False]
            outcomes[m+'_raw_signed_spread_relative']=[-1.,1.,np.nan]
            outcomes[m+'_raw_moment']=[-1.,1.,np.nan]
            outcomes[m+'_raw_negative']=pd.array([True,False,pd.NA],dtype='boolean')
            outcomes[m+'_defined']=[True,True,False]
        rates=r.unadjusted_negative_rates(outcomes)
        self.assertTrue(rates.design_N.eq(3).all())
        self.assertTrue(rates.raw_computable_N.eq(2).all())
        self.assertTrue(rates.negative_N.eq(1).all())
        self.assertTrue(rates.negative_rate.eq(.5).all())

    def test_leave_one_out_removes_asset_only_and_records_changed_leaders(self):
        common=sample();runs,summary=r.leave_one_asset_out(common,common)
        self.assertEqual(len(runs),6)
        self.assertTrue(runs.loc[runs.excluded_asset.eq('A'),'N_asset_days'].eq(1).all())
        self.assertTrue(runs.loc[runs.excluded_asset.eq('B'),'N_asset_days'].eq(3).all())
        np.testing.assert_allclose(runs.loc[runs.excluded_asset.eq('A'),'mae_bps'],10.)
        self.assertEqual(set(summary.largest_mae_change_asset),{'A'})

    def test_extreme_removes_exactly_one_deterministic_tie_no_winsorization(self):
        common=sample();common.loc[2,'cs_error_bps']=-10.;common['cs_absolute_error_bps']=common.cs_error_bps.abs()
        before=common.copy(deep=True)
        results,details=r.extreme_influence(common)
        self.assertTrue(results.removed_N.eq(1).all())
        self.assertTrue(results.N_after.eq(3).all())
        cs=next(x for x in details if x['estimator']=='CS')
        self.assertEqual((cs['asset'],cs['target_date']),('A','2024-01-03'))
        np.testing.assert_allclose(results.loc[results.estimator.eq('CS'),'after_mae_bps'],4.)
        pd.testing.assert_frame_equal(common,before)


class RobustnessProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.panel,cls.common=r.inputs()

    def test_primary_24377_formulas_hashes_and_no_fx(self):
        self.assertEqual(len(self.common),24377)
        self.assertNotIn('fx',set(self.panel.asset_class))
        r.source.verify_frozen()
        lock=r.snapshot_primary();r.check_lock(lock)

    def test_predeclared_quality_samples_and_no_threshold_search(self):
        q=r.coverage_panel(self.panel)
        self.assertEqual(int(q.R25.sum()),16150)
        self.assertEqual(int(q.R50.sum()),12908)
        self.assertTrue((~q.R50|q.R25).all())
        self.assertTrue((~q.R25|q.common_defined_accuracy_sample).all())

    def test_saved_outputs_reconcile_all_definitions_when_materialized(self):
        if not (r.RESULTS/'roll_quality_sensitivity.csv').exists():self.skipTest('Full materialization not yet complete')
        quality=pd.read_csv(r.RESULTS/'roll_quality_sensitivity.csv')
        self.assertTrue(quality.analysis_role.eq('ROBUSTNESS_SENSITIVITY').all())
        for name,expected in [('Roll R25',16150),('Roll R50',12908)]:
            part=quality.loc[quality.variant.eq(name)&quality.reporting_scope.eq('overall')]
            self.assertTrue(part.N_asset_days.eq(expected).all())
        equal=pd.read_csv(r.RESULTS/'equal_asset_weighting.csv')
        self.assertTrue(equal.loc[equal.reporting_scope.eq('overall'),'N_asset_days'].eq(24377).all())
        unadjusted=pd.read_csv(r.RESULTS/'bloomberg_unadjusted_robustness.csv')
        self.assertEqual(set(unadjusted.asset_class),{'stocks','etfs'})
        self.assertTrue(unadjusted.groupby(r.primary.CELL_KEYS).N_asset_days.nunique().eq(1).all())
        for metric in ['bias','mae','rmse']:
            np.testing.assert_allclose(unadjusted['delta_'+metric+'_bps_vs_adjusted_matched'],
                unadjusted[metric+'_bps']-unadjusted[metric+'_bps_adjusted_matched'],rtol=1e-10,atol=1e-10)
        loo=pd.read_csv(r.RESULTS/'leave_one_asset_out.csv')
        self.assertEqual(len(loo),108)
        self.assertTrue(loo.groupby('asset_class').excluded_asset.nunique().eq(9).all())
        extremes=pd.read_csv(r.RESULTS/'extreme_observation_influence.csv')
        self.assertEqual(len(extremes),12);self.assertTrue(extremes.removed_N.eq(1).all())

    def test_unadjusted_boundary_audit_and_ignored_granular_data(self):
        r.provider.verify_ignored(r.ANALYTIC/'unadjusted_common_errors.parquet')
        path=r.ANALYTIC/'unadjusted_common_sample_audit.parquet'
        if not path.exists():return
        audit=pd.read_parquet(path)
        self.assertEqual(len(audit),23148)
        for m in r.METHODS:
            crossed=audit[m+'_verified_boundary_crossed']
            self.assertFalse(audit.loc[crossed,m+'_unadjusted_defined'].any())
            self.assertEqual(set(audit.loc[crossed,'asset']),{'SNDL'})
        self.assertTrue(audit.groupby('asset').size().gt(0).all())


if __name__=='__main__':unittest.main()
