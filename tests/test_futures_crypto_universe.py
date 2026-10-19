from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from futures_crypto_universe import (rank_and_select, crypto_rank, crypto_quote_review,
    root_session_review, futures_calibration, futures_inventory, endpoint_info, crypto_2024)
from futures_roll import validate_sessions, selection_plan, parse_provider_calendar
from session_rules import assign_primary_session


class FuturesCryptoUniverseTests(unittest.TestCase):
    def ranking(self, n=18):
        return pd.DataFrame([dict(asset=f'R{i:02}',asset_class='futures',liquidity_measure=float(i),ranking_eligible=True) for i in range(n)])

    def test_deterministic_root_rank_and_liquidity_ties(self):
        data=self.ranking()
        data.loc[1,'liquidity_measure']=0
        first,selected=rank_and_select(data,'futures')
        second,_=rank_and_select(data.sample(frac=1,random_state=4),'futures')
        pd.testing.assert_frame_equal(first,second)
        self.assertEqual(first.asset.iloc[:2].tolist(),['R00','R01'])
        self.assertEqual(len(selected),9)
        self.assertTrue(selected.groupby('liquidity_tier').size().eq(3).all())

    def test_quantile_rank_positions_and_alphabetical_distance_ties(self):
        audit,selected=rank_and_select(self.ranking(),'futures')
        low=selected.loc[selected.liquidity_tier.eq('LOW')]
        self.assertEqual(low.selection_quantile_target.tolist(),[.25,.5,.75])
        self.assertEqual(low.liquidity_rank_within_tier.tolist(),[2,3,5])
        self.assertEqual(low.selection_target_rank.tolist(),[2.25,3.5,4.75])

    def test_insufficient_roots_no_terciles_or_forced_selection(self):
        audit,selected=rank_and_select(self.ranking(2),'futures')
        self.assertTrue(selected.empty)
        self.assertTrue(audit.liquidity_tier.eq('').all())

    def test_quantile_collision_blocks_instead_of_changing_sampling_rule(self):
        audit,selected=rank_and_select(self.ranking(9),'futures')
        self.assertTrue(selected.empty)
        self.assertTrue(audit.selection_reason.str.contains('quantile_targets_not_distinct').all())

    def test_no_benchmark_columns_affect_ranking(self):
        clean=self.ranking()
        contaminated=clean.assign(roll_defined=False,roll_spread_bps=np.nan,EDGE=999,cs=-1,ar=45)
        a,s=rank_and_select(clean,'futures'); b,t=rank_and_select(contaminated,'futures')
        pd.testing.assert_frame_equal(a,b); pd.testing.assert_frame_equal(s,t)
        self.assertFalse(set(['roll_defined','EDGE','cs','ar'])&set(a.columns))

    def test_clean_selection_import_has_no_benchmark_dependency(self):
        folder=str(Path(__file__).resolve().parents[1]/'src')
        result=subprocess.run([sys.executable,'-B','-c',f'import sys; sys.path.insert(0,{folder!r}); import futures_crypto_universe; assert "benchmark" not in sys.modules'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_unknown_root_session_blocked_no_global_fallback(self):
        self.assertEqual(root_session_review('NG')['session_status'],'UNRESOLVED')
        data=pd.DataFrame(dict(timestamp=pd.to_datetime(['2024-01-07 18:00']),volume=[1]))
        with self.assertRaises(NotImplementedError):
            assign_primary_session(data,'futures',futures_root='NG')
        with self.assertRaises(ValueError):
            futures_calibration(Path('not_read'),'NG')

    def test_pilot_overnight_assignment_and_maintenance(self):
        data=pd.DataFrame(dict(timestamp=pd.to_datetime(['2024-01-07 18:00','2024-01-08 16:59','2024-01-08 17:30']),volume=[1,1,1]))
        for root in ['ES','CL']:
            assigned=assign_primary_session(data,'futures',futures_root=root)
            self.assertEqual(assigned.trade_date.iloc[:2].astype(str).tolist(),['2024-01-08']*2)
            self.assertFalse(assigned.primary_session_retained.iloc[-1])

    def test_no_continuous_prices_read_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); (root/'futures').mkdir(); (root/'_documentation/.archive').mkdir(parents=True)
            (root/'_documentation/.archive/futures_ticker_dates_listing.txt').write_text('Ticker,Name,First Date,Last Date\nES,ES (CME),2020-01-01,2025-12-31\n')
            individual=root/'futures/ES_H24_1min.txt'
            individual.write_text('2024-01-07 18:00:00,1,2,1,2,3\n')
            continuous=root/'futures/ES_continuous_adjusted_1min.txt'
            continuous.write_bytes(b'not a valid data file; must never be parsed')
            (root/'futures/ES_continuous_contract_dates.txt').write_text('2024-01-08,H24\n')
            inv,files,_,_=futures_inventory(root)
            self.assertEqual(inv.individual_contract_files.iloc[0],1)
            self.assertTrue(inv.continuous_series_exists_locally.iloc[0])
            self.assertEqual(len(files),1)
            self.assertEqual(continuous.read_bytes(),b'not a valid data file; must never be parsed')

    def test_one_selected_contract_per_trade_date(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'ES_H24_1min.txt').touch(); (root/'ES_M24_1min.txt').touch()
            calendar=root/'dates.txt'; calendar.write_text('2024-01-08,H24\n')
            plan=selection_plan(parse_provider_calendar(calendar),'ES','2024-01-08','2024-01-08',root)
            data=pd.DataFrame(dict(timestamp=pd.to_datetime(['2024-01-07 18:00']),close=[1.],volume=[2.]))
            a=assign_primary_session(data,'futures',futures_root='ES').assign(source_contract='H24')
            b=assign_primary_session(data,'futures',futures_root='ES').assign(source_contract='M24',volume=999)
            sessions,selected=validate_sessions(plan,{'H24':a,'M24':b})
            self.assertEqual(selected.selected_contract.tolist(),['H24'])
            self.assertEqual(selected.volume.tolist(),[2.])

    def test_crypto_unknown_quote_blocks_native_volume_ranking(self):
        data=pd.DataFrame([dict(ticker='BTC',explicit_cross_pair=False,common_currency_verified=False,explicit_quote_currency='',observed_2024_calendar_days=366,history_eligible_3_years=True,median_daily_volume=10**9)])
        audit,selected,reason=crypto_rank(data)
        self.assertTrue(audit.empty and selected.empty)
        self.assertIn('quote_currency',reason)
        self.assertEqual(crypto_quote_review('BTC','Bitcoin')['explicit_quote_currency'],'')

    def test_explicit_cross_pairs_excluded_even_if_notional_supplied(self):
        rows=[]
        for i in range(15):
            rows.append(dict(ticker=f'C{i}',explicit_cross_pair=False,common_currency_verified=True,explicit_quote_currency='USD',observed_2024_calendar_days=366,history_eligible_3_years=True,median_daily_notional_turnover=float(i)))
        rows.append(dict(ticker='BTC-EUR',explicit_cross_pair=True,common_currency_verified=True,explicit_quote_currency='EUR',observed_2024_calendar_days=366,history_eligible_3_years=True,median_daily_notional_turnover=999999))
        audit,selected,reason=crypto_rank(pd.DataFrame(rows))
        self.assertEqual(len(selected),9)
        self.assertNotIn('BTC-EUR',audit.asset.tolist())
        self.assertEqual(reason,'')

    def test_verified_currency_still_does_not_allow_native_volume_fallback(self):
        data=pd.DataFrame([dict(ticker=f'C{i}',explicit_cross_pair=False,common_currency_verified=True,explicit_quote_currency='USD',observed_2024_calendar_days=366,history_eligible_3_years=True,median_daily_volume=i) for i in range(15)])
        audit,selected,reason=crypto_rank(data)
        self.assertTrue(audit.empty and selected.empty)
        self.assertIn('not_computed',reason)

    def test_crypto_300_day_and_existing_history_gate(self):
        rows=[dict(ticker=f'C{i:02}',explicit_cross_pair=False,common_currency_verified=True,explicit_quote_currency='USD',observed_2024_calendar_days=366,history_eligible_3_years=True,median_daily_notional_turnover=i) for i in range(17)]
        rows[0]['observed_2024_calendar_days']=299
        rows[1]['history_eligible_3_years']=False
        audit,_,_=crypto_rank(pd.DataFrame(rows))
        self.assertEqual(len(audit),15)
        self.assertNotIn('C00',audit.asset.tolist())
        self.assertNotIn('C01',audit.asset.tolist())

    def test_crypto_daily_diagnostics_no_notional_no_filling_raw_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'BTC_full_1min.txt'
            text='2023-01-01 00:00:00,1,2,1,2,1\n2024-01-01 23:58:00,1,2,1,2,0\n2024-01-02 00:01:00,1,2,1,2,3\n'
            path.write_text(text)
            daily,scan=crypto_2024(path)
            self.assertEqual(len(daily),2)
            self.assertEqual(daily.bars_observed.tolist(),[1,1])
            self.assertEqual(daily.volume.tolist(),[0,3])
            self.assertEqual(daily.zero_volume_rows.sum(),1)
            self.assertNotIn('daily_notional_turnover',daily)
            self.assertEqual(path.read_text(),text)
            self.assertEqual(endpoint_info(path)['first_observation'],'2023-01-01 00:00:00')


if __name__=='__main__':
    unittest.main()
