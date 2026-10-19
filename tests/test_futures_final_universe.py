from datetime import time
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from futures_final_universe import (PRODUCTS, resolve_provider_roots, build_configs,
    rank_and_select, eligibility, inspect_transitions, historical_rule_gaps,cached_calibration)
from futures_roll import parse_provider_calendar, selection_plan, validate_sessions, contract_file, read_contract_window
from session_rules import FuturesSessionConfig, assign_primary_session


class FuturesFinalUniverseTests(unittest.TestCase):
    def mapping(self):
        roots = ['ES','NQ','RTY','ZT','ZF','ZN','US','CL','NG','GC','SI','HG','E6','J1','B6','A6','AD','E1']
        return resolve_provider_roots(pd.DataFrame(dict(Ticker=roots,Name=[r[3] for r in PRODUCTS])))

    def data(self,n=18):
        return pd.DataFrame(dict(provider_root=[f'R{i:02}' for i in range(n)],
            liquidity_measure_2024=np.arange(n,dtype=float),final_eligible=True))

    def test_explicit_currency_and_bond_mapping(self):
        mapping = self.mapping().set_index('exchange_symbol')
        self.assertEqual(mapping.loc['6C','provider_root'],'AD')
        self.assertEqual(mapping.loc['6S','provider_root'],'E1')
        self.assertEqual(mapping.loc['6A','provider_root'],'A6')
        self.assertEqual(mapping.loc['ZB','provider_root'],'US')

    def test_no_guessing_from_reversed_symbols_or_ambiguous_metadata(self):
        guessed = resolve_provider_roots(pd.DataFrame(dict(Ticker=['A6'],Name=['unidentified instrument'])))
        self.assertFalse(guessed.mapping_resolved.any())
        ambiguous = resolve_provider_roots(pd.DataFrame(dict(Ticker=['A6','OTHER'],Name=[PRODUCTS[15][3]]*2)))
        self.assertFalse(ambiguous.mapping_resolved.any())

    def test_root_specific_pause_and_legacy_pilot_unchanged(self):
        configs,_ = build_configs(self.mapping())
        data = pd.DataFrame(dict(timestamp=pd.to_datetime(['2024-01-08 16:15','2024-01-08 17:00','2024-01-07 18:00']),volume=[1,1,1]))
        self.assertEqual(assign_primary_session(data,'futures',futures_root='ES',futures_sessions=configs).primary_session_retained.tolist(),[True,False,True])
        self.assertEqual(assign_primary_session(data,'futures',futures_root='CL',futures_sessions=configs).primary_session_retained.tolist(),[True,False,True])
        self.assertTrue(assign_primary_session(data,'futures',futures_root='ES').primary_session_retained.iloc[0])
        data.timestamp = pd.to_datetime(['2021-06-25 16:15','2021-06-28 16:15','2021-06-28 17:00'])
        self.assertEqual(assign_primary_session(data,'futures',futures_root='ES',futures_sessions=configs).primary_session_retained.tolist(),[False,True,False])
        self.assertEqual(assign_primary_session(data,'futures',futures_root='CL',futures_sessions=configs).primary_session_retained.tolist(),[True,True,False])

    def test_date_effective_rules_and_unresolved_historical_dates(self):
        configs,_ = build_configs(self.mapping())
        data = pd.DataFrame(dict(timestamp=pd.to_datetime(['2015-09-18 17:05','2015-09-21 17:05']),volume=[1,1]))
        result = assign_primary_session(data,'futures',futures_root='CL',futures_sessions=configs)
        self.assertEqual(result.primary_session_retained.tolist(),[True,False])
        data.timestamp = pd.to_datetime(['2023-01-09 09:00','2024-01-09 09:00'])
        result = assign_primary_session(data,'futures',futures_root='ZT',futures_sessions=configs)
        self.assertEqual(result.futures_session_rule_unresolved.tolist(),[True,False])
        self.assertEqual(result.primary_session_retained.tolist(),[False,True])

    def test_conflicting_session_rules_rejected(self):
        rule=FuturesSessionConfig('TEST',start=time(18),end=time(17),trading_day_convention='overnight_ending_date')
        data=pd.DataFrame(dict(timestamp=pd.to_datetime(['2024-01-01 09:00']),volume=[1]))
        with self.assertRaises(ValueError):
            assign_primary_session(data,'futures',futures_root='TEST',futures_sessions={'TEST':(rule,rule)})

    def test_historical_unverified_ranges_exclude_verified_2024(self):
        configs,_ = build_configs(self.mapping())
        self.assertEqual(historical_rule_gaps(configs['ZF']),[
            dict(start='2015-01-01',end='2023-12-31'),dict(start='2025-01-01',end='2025-12-31')])
        self.assertEqual(historical_rule_gaps(configs['CL']),[])

    def test_changed_clock_rejects_cache_even_when_rule_id_unchanged(self):
        mapping=self.mapping();configs,rules=build_configs(mapping)
        row=next(mapping.loc[mapping.provider_root.eq('CL')].itertuples())
        identifier=configs['CL'][-1].rule_id
        records=pd.DataFrame([dict(provider_root='CL',session_rule_id=identifier)])
        rules.loc[rules.session_rule_id.eq(identifier),'session_open']='17:00'
        previous=({},records,pd.DataFrame(),pd.DataFrame(),rules)
        self.assertIsNone(cached_calibration(Path('must_not_be_read'),row,configs,previous))

    def test_evening_dst_maintenance_no_fill_and_raw_unchanged(self):
        configs,_ = build_configs(self.mapping())
        data=pd.DataFrame(dict(timestamp=pd.to_datetime(['2024-03-10 18:00','2024-03-11 16:59','2024-03-11 17:30']),volume=[0,1,1]))
        before=data.copy(deep=True)
        result=assign_primary_session(data,'futures',futures_root='A6',futures_sessions=configs)
        self.assertEqual(result.trade_date.iloc[:2].astype(str).tolist(),['2024-03-11']*2)
        self.assertEqual(result.timestamp_local.iloc[0].utcoffset().total_seconds(),-14400)
        self.assertEqual(len(result),3)
        self.assertTrue(result.zero_volume.iloc[0])
        self.assertFalse(result.primary_session_retained.iloc[-1])
        pd.testing.assert_frame_equal(before,data)

    def test_one_active_contract_and_no_continuous_substitution(self):
        configs,_=build_configs(self.mapping())
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory); path=folder/'map.txt'
            path.write_text('2024-01-08,H24\n')
            for code in ('H24','M24'):
                contract_file(folder,'A6',code,allowed_roots=configs).touch()
            plan=selection_plan(parse_provider_calendar(path),'A6','2024-01-08','2024-01-08',folder,futures_sessions=configs)
            data=pd.DataFrame(dict(timestamp=pd.to_datetime(['2024-01-07 18:00']),close=[1.],volume=[2.]))
            assigned=assign_primary_session(data,'futures',futures_root='A6',futures_sessions=configs)
            sessions,selected=validate_sessions(plan,{code:assigned.assign(source_contract=code) for code in ('H24','M24')})
            self.assertEqual(selected.selected_contract.tolist(),['H24'])
            with self.assertRaises(ValueError):
                contract_file(folder,'A6','continuous_adjusted',allowed_roots=configs)
            fake=folder/'A6_continuous_adjusted_1min.txt'; fake.write_text('never read')
            with self.assertRaises(ValueError):
                read_contract_window(fake,'A6','H24','2024-01-08','2024-01-08',folder,futures_sessions=configs)

    def test_provider_transition_evening_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'map.txt';path.write_text('2023-12-29,H24\n2024-03-10,M24\n2024-06-10,U24\n')
            calendar=parse_provider_calendar(path)
            sessions=pd.DataFrame([dict(trade_date=pd.Timestamp('2024-03-11').date(),selected_contract='M24',bars_observed=2,
                roll_day=True,previous_evening_present=True,previous_evening_rows=1)])
            result=inspect_transitions(calendar,sessions,'ZT')
            self.assertEqual(result.validation_passed.tolist(),[True,False])
            self.assertEqual(str(result.first_observed_trade_date.iloc[0]),'2024-03-11')

    def test_200_valid_day_gate_structural_failures(self):
        record=dict(mapping_resolved=True,individual_contract_files_exist=True,provider_mapping_usable=True,
            session_2024_verified=True,one_active_contract_per_trade_date=True,valid_observed_2024_trade_dates=200)
        self.assertTrue(eligibility(record)[0])
        self.assertFalse(eligibility(dict(record,valid_observed_2024_trade_dates=199))[0])
        self.assertFalse(eligibility(dict(record,invalid_aggregation_days=1))[0])
        self.assertFalse(eligibility(dict(record,transition_validation_failures=1))[0])

    def test_deterministic_ranking_terciles_quantiles(self):
        data=self.data(); a,s=rank_and_select(data);b,t=rank_and_select(data.sample(frac=1,random_state=2))
        pd.testing.assert_frame_equal(a,b);pd.testing.assert_frame_equal(s,t)
        self.assertEqual(a.groupby('liquidity_tier').size().to_dict(),dict(HIGH=6,LOW=6,MEDIUM=6))
        self.assertEqual(s.loc[s.liquidity_tier.eq('LOW'),'liquidity_rank_within_tier'].tolist(),[2,3,5])

    def test_nearest_unused_policy_three_distinct_in_small_terciles(self):
        for n in (9,10,11,12):
            _,selected=rank_and_select(self.data(n))
            self.assertEqual(selected.provider_root.nunique(),9)
            self.assertTrue(selected.groupby('liquidity_tier').size().eq(3).all())

    def test_selection_independent_of_estimator_benchmark_columns(self):
        a,s=rank_and_select(self.data());b,t=rank_and_select(self.data().assign(roll_defined=False,roll_spread_bps=999,CS=-100,AR=50,EDGE=np.nan))
        pd.testing.assert_frame_equal(a,b);pd.testing.assert_frame_equal(s,t)
        result=subprocess.run([sys.executable,'-B','-c',
            "import sys;sys.path.insert(0,'src');import futures_final_universe;assert 'benchmark' not in sys.modules"],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_fewer_than_nine_blocks_no_expansion(self):
        audit,selected=rank_and_select(self.data(8))
        self.assertTrue(selected.empty)
        self.assertTrue(audit.selection_reason.str.startswith('blocked_').all())


if __name__=='__main__':
    unittest.main()
