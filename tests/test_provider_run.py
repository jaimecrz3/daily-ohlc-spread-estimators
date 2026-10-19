from pathlib import Path
import ast
import json
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import provider_run as p
import provider_run_io as read
from benchmark import build_roll_benchmark, MIN_ROLL_PAIRS
from data_io import intraday_root
from session_rules import FuturesSessionConfig
from datetime import time
from datetime import date
from bloomberg_io import sha256, verify_hashes, require_verified


def synthetic_source():
    return pd.DataFrame(dict(asset=['SYNTH']*4,date=['2024-01-05','2024-01-08','2024-01-09','2024-01-10'],
        open=[10.,11,12,13],high=[12.,13,14,15],low=[9.,10,11,12],close=[11.,12,13,14],
        selected_contract=['H24']*4))


class ProviderRunTests(unittest.TestCase):
    def test_hand_audit_json_handles_native_daily_labels_and_missing_values(self):
        value=json.loads(p.dumps(dict(day=date(2024,1,2),missing=np.nan,flag=pd.NA)))
        self.assertEqual(value,dict(day='2024-01-02',missing=None,flag=None))
    def test_exact_frozen_design_38232_and_class_counts(self):
        design=read.frozen_design()
        self.assertEqual(len(design),38232)
        self.assertEqual(design.groupby('asset_class').size().to_dict(),read.EXPECTED)

    def test_design_unique_keys_no_fx_and_nine_assets(self):
        design=read.frozen_design()
        self.assertFalse(design.duplicated(['asset_class','asset','date']).any())
        self.assertNotIn('fx',set(design.asset_class))
        self.assertTrue(design.groupby('asset_class').asset.nunique().eq(9).all())

    def test_frozen_universes_tiers_and_calendars_unchanged(self):
        design=read.frozen_design()
        for cls in read.EXPECTED:
            saved=pd.read_csv(read.DESIGN/f'{cls}_primary_calendar.csv').date.tolist()
            self.assertEqual(sorted(design.loc[design.asset_class.eq(cls),'date'].unique()),saved)
            self.assertTrue(design.loc[design.asset_class.eq(cls)].groupby('date').asset.nunique().eq(9).all())

    def test_roll_source_unchanged_except_registry_interface(self):
        self.assertTrue(read.roll_interface_unchanged())
        self.assertEqual(MIN_ROLL_PAIRS,2)

    def test_nonnegative_roll_gamma_undefined_not_zero(self):
        bars=pd.DataFrame(dict(timestamp=pd.date_range('2024-01-02 09:30',periods=5,freq='min'),
                               close=[1.,2,4,8,16],volume=[1]*5))
        r=build_roll_benchmark(bars,'SYNTH','stocks').iloc[0]
        self.assertEqual(r.roll_pairs,3)
        self.assertFalse(r.benchmark_defined)
        self.assertTrue(np.isnan(r.roll_spread_relative))
        self.assertEqual(r.failure_reason,'non_negative_autocovariance')

    def test_session_registry_forwarding_for_nonpilot_future(self):
        cfg={'HG':FuturesSessionConfig('HG',start=time(18),end=time(17),trading_day_convention='overnight_ending_date')}
        bars=pd.DataFrame(dict(timestamp=pd.date_range('2024-01-02 18:00',periods=5,freq='min'),
            close=[100.,101,100,101,100],volume=[1]*5,selected_contract=['H24']*5,source_contract=['H24']*5))
        r=read.invoke_roll(bars,'futures','HG',cfg)
        self.assertEqual(str(r.date.iloc[0]),'2024-01-03')
        self.assertEqual(r.roll_pairs.iloc[0],3)

    def test_cs_input_window_exact_centered(self):
        data=synthetic_source();grid=pd.DatetimeIndex(pd.to_datetime(data.date))
        r=p.method_output(data,'stocks','SYNTH','2024-01-08','CS',grid)
        self.assertEqual(r['input_dates'],data.date.iloc[:3].tolist())

    def test_ar_input_window_target_and_next(self):
        data=synthetic_source();grid=pd.DatetimeIndex(pd.to_datetime(data.date))
        r=p.method_output(data,'crypto','SYNTH','2024-01-08','AR',grid)
        self.assertEqual(r['input_dates'],data.date.iloc[1:3].tolist())

    def test_edge_centered_input_window(self):
        data=synthetic_source();grid=pd.DatetimeIndex(pd.to_datetime(data.date))
        r=p.method_output(data,'etfs','SYNTH','2024-01-08','EDGE',grid)
        self.assertEqual(r['input_dates'],data.date.iloc[:3].tolist())

    def test_missing_scheduled_period_not_compressed(self):
        data=synthetic_source();grid=pd.DatetimeIndex(pd.to_datetime(data.date))
        r=p.method_output(data.iloc[[0,2,3]],'stocks','SYNTH','2024-01-09','CS',grid)
        self.assertFalse(r['estimator_defined'])
        self.assertEqual(r['failure_reason'],'missing_previous_scheduled_period')

    def test_crypto_expects_utc_weekend_days(self):
        data=synthetic_source();grid=pd.date_range('2024-01-05','2024-01-10')
        r=p.method_output(data,'crypto','SYNTH','2024-01-08','EDGE',grid)
        self.assertFalse(r['scheduled_adjacency_valid'])

    def test_contract_crossing_rejected_before_kernel(self):
        data=synthetic_source();data.loc[2,'selected_contract']='M24'
        grid=pd.DatetimeIndex(pd.to_datetime(data.date))
        with patch.object(p,'daily_estimate',side_effect=AssertionError('Mixed contract kernel call forbidden')):
            for method in ['CS','AR','EDGE']:
                r=p.method_output(data,'futures','SYNTH','2024-01-08',method,grid)
                self.assertFalse(r['estimator_defined'])
                self.assertEqual(r['failure_reason'],'invalid_scheduled_adjacency')
                self.assertEqual(r['method_specific_diagnostics']['failure_detail'],'futures_contract_boundary')

    def test_same_contract_uses_frozen_mapping(self):
        data=synthetic_source();grid=pd.DatetimeIndex(pd.to_datetime(data.date))
        r=p.method_output(data,'futures','SYNTH','2024-01-08','AR',grid)
        self.assertTrue(r['scheduled_adjacency_valid'])
        self.assertFalse(r['method_specific_diagnostics']['contract_boundary'])

    def test_stock_daily_source_is_bloomberg_adjusted(self):
        frame,path=p.source_daily('stocks','IMDX',{})
        self.assertEqual(path.name,'daily_adjusted.parquet')
        self.assertTrue(frame.source.eq('Bloomberg').all())
        self.assertTrue(frame.convention.eq('adjusted').all())

    def test_etf_daily_source_is_bloomberg_adjusted(self):
        frame,path=p.source_daily('etfs','JSML',{})
        self.assertTrue(frame.source.eq('Bloomberg').all())
        self.assertTrue(frame.convention.eq('adjusted').all())

    def test_local_minute_reader_no_bloomberg_or_substitution(self):
        source=(read.PROJECT/'src/provider_run_io.py').read_text()
        self.assertIn('base/(\'cryptos\' if cls==\'crypto\' else cls)',source)
        self.assertIn('intraday_root()',source)
        self.assertNotIn('read_daily_values',source)
        self.assertNotIn('urlopen',source)

    def test_common_mask_exact_conjunction_includes_defined_zero(self):
        frame=pd.DataFrame(True,index=range(6),columns=['design_eligible','benchmark_defined','cs_defined','ar_defined','edge_defined'])
        frame['cs_primary_spread_relative']=0.
        for i,col in enumerate(frame.columns[:5]):frame.loc[i,col]=False
        self.assertEqual(p.common_mask(frame).tolist(),[False]*5+[True])

    def test_no_error_columns_or_performance_function_calls(self):
        forbidden={'point_summary','date_components','hac_lag','fit','corr','cov_hac','mean_squared_error','mean_absolute_error'}
        for name in ['provider_run.py','provider_run_io.py']:
            tree=ast.parse((read.PROJECT/'src'/name).read_text())
            calls={node.func.id if isinstance(node.func,ast.Name) else node.func.attr
                for node in ast.walk(tree) if isinstance(node,ast.Call) and isinstance(node.func,(ast.Name,ast.Attribute))}
            self.assertFalse(calls&forbidden)
        self.assertIn('signed_error',p.FORBIDDEN_COLUMNS)

    def test_observation_paths_are_ignored(self):
        p.verify_ignored(p.PANEL)
        p.verify_ignored(read.ANALYTIC/'raw_to_final_reproduction.json')

    def test_five_reproductions_selected_without_outcomes(self):
        keys=read.fixed_audit_keys(read.frozen_design())
        self.assertEqual(len(keys),5)
        self.assertEqual(set(k[0] for k in keys),set(read.EXPECTED))
        self.assertEqual(keys,read.fixed_audit_keys(read.frozen_design()))

    def test_protected_specs_and_estimator_kernels_unchanged(self):
        read.verify_frozen()
        for folder in ['estimator_freeze','statistical_freeze']:
            m=json.loads((read.DIAG/folder/'run_manifest.json').read_text())
            for name,digest in m['code_sha256'].items():
                self.assertEqual(sha256(read.PROJECT/name),digest,name)

    def test_all_eleven_bloomberg_hashes_unchanged(self):
        audit,_=verify_hashes(read.PROJECT/'data/raw_bloomberg');require_verified(audit)
        self.assertEqual(len(audit),11)

    def test_actual_provider_panel_reconciliation_and_negative_integrity(self):
        if not p.PANEL.exists(): self.skipTest('Final panel is written before the completion-gate full suite')
        panel=pd.read_parquet(p.PANEL)
        p.validate_panel(panel,read.frozen_design())
        self.assertFalse(set(panel.columns)&p.FORBIDDEN_COLUMNS)
        for method in p.METHODS:
            negative=panel[method+'_raw_negative'].eq(True).fillna(False)
            self.assertTrue(panel.loc[negative,method+'_defined'].all())


if __name__=='__main__': unittest.main()
