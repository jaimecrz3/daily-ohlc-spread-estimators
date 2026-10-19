from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from crypto_final_universe import (RULE,VERIFIED,cross_diagnostic,stablecoin_diagnostic,
    common_quote_status,daily_turnover,asset_eligibility,rank_crypto,read_minute_sample)
from daily_aggregation import aggregate_daily_ohlcv


class CryptoFinalTests(unittest.TestCase):
    def pairs(self):
        ratio=np.linspace(.03,.08,366)
        return pd.DataFrame(dict(date=pd.date_range('2024-01-01',periods=366),BTC=100.,
            ETH=ratio*100,cross=ratio*(1+.005*np.sin(np.arange(366)))))

    def daily(self,n=366):
        return pd.DataFrame(dict(date=pd.date_range('2024-01-01',periods=n).date,
            close=2.,volume=10.,aggregation_valid=True,bars_observed=1,
            zero_volume_rows=0,invalid_ohlc_rows=0,low=1.))

    def audit(self,n=18):
        return pd.DataFrame(dict(asset=[f'C{i:02}' for i in range(n)],asset_class='cryptos',
            ranking_eligible=True,liquidity_measure=np.arange(n,dtype=float)))

    def test_synthetic_composition_noise_passes_both_scopes(self):
        minute,_=cross_diagnostic(self.pairs(),'minute_sample')
        daily,_=cross_diagnostic(self.pairs(),'daily_utc')
        stable=pd.DataFrame([stablecoin_diagnostic(asset,self.daily().assign(close=1.))
            for asset in RULE['stablecoins']])
        self.assertTrue(minute['validation_passed'] and daily['validation_passed'])
        self.assertEqual(common_quote_status(pd.DataFrame([minute,daily]),stable),VERIFIED)

    def test_synthetic_scaling_inversion_and_misalignment_fail(self):
        for cross in (self.pairs().cross*2,1/self.pairs().cross,self.pairs().cross.iloc[::-1].to_numpy()):
            summary,_=cross_diagnostic(self.pairs().assign(cross=cross),'daily_utc')
            self.assertFalse(summary['validation_passed'])

    def test_nonunit_stablecoin_and_insufficient_evidence_fail(self):
        self.assertFalse(stablecoin_diagnostic('USDT',self.daily().assign(close=2.))['validation_passed'])
        self.assertFalse(stablecoin_diagnostic('USDT',self.daily(299).assign(close=1.))['validation_passed'])
        cross=pd.DataFrame([cross_diagnostic(self.pairs(),scope)[0] for scope in ('minute_sample','daily_utc')])
        stable=pd.DataFrame([stablecoin_diagnostic('USDT',self.daily().assign(close=1.))])
        self.assertNotEqual(common_quote_status(cross,stable),VERIFIED)

    def test_utc_aggregation_turnover_uses_daily_close_times_sum(self):
        bars=pd.DataFrame(dict(timestamp=pd.to_datetime(['2024-01-01 23:58','2024-01-01 23:59','2024-01-02 00:02']),
            open=[1.,2.,4.],high=[2.,3.,5.],low=[1.,2.,4.],close=[2.,3.,5.],volume=[2.,4.,6.]))
        before=bars.copy(deep=True)
        daily=aggregate_daily_ohlcv(bars,'SYNTH','cryptos')
        result=daily_turnover(daily)
        self.assertEqual(result.daily_provider_quote_turnover.tolist(),[18.,30.])
        self.assertEqual(result.bars_observed.tolist(),[2,1])
        self.assertTrue(result.timezone.eq('UTC').all())
        pd.testing.assert_frame_equal(before,bars)

    def test_gate_required_before_ranking_no_native_unit_fallback(self):
        with self.assertRaises(ValueError): rank_crypto(self.audit(),'UNKNOWN')
        with self.assertRaises(ValueError):
            rank_crypto(self.audit().drop(columns='liquidity_measure').assign(median_daily_base_volume=999),VERIFIED)

    def test_explicit_crosses_excluded_and_benchmark_columns_ignored(self):
        data=self.audit()
        cross=pd.DataFrame([dict(asset='ETH-BTC',asset_class='cryptos',ranking_eligible=True,liquidity_measure=9999.)])
        expected,_=rank_crypto(data,VERIFIED)
        actual,_=rank_crypto(pd.concat([data,cross]).assign(roll_defined=False,roll_spread_bps=999,
            CS=-1,AR=-1,EDGE=-1,median_daily_base_volume=10**10),VERIFIED)
        pd.testing.assert_frame_equal(expected,actual)
        self.assertNotIn('ETH-BTC',actual.asset.tolist())

    def test_300_day_rule_and_history_rule_clipped_to_study(self):
        row=dict(ticker='SYNTH',first_date='2020-01-01',last_date='2026-01-05')
        self.assertTrue(asset_eligibility(row,daily_turnover(self.daily(300)),VERIFIED)['ranking_eligible'])
        self.assertFalse(asset_eligibility(row,daily_turnover(self.daily(299)),VERIFIED)['ranking_eligible'])
        late=dict(row,first_date='2023-01-02')
        self.assertFalse(asset_eligibility(late,daily_turnover(self.daily()),VERIFIED)['history_eligible_3_years'])
        exact=dict(row,first_date='2023-01-01')
        self.assertTrue(asset_eligibility(exact,daily_turnover(self.daily()),VERIFIED)['history_eligible_3_years'])

    def test_invalid_rows_preserved_and_block_asset_without_repair(self):
        d=self.daily();d.loc[0,['close','low']]=0.;d.loc[0,'aggregation_valid']=False;d.loc[0,'invalid_ohlc_rows']=2
        before=d.copy(deep=True);result=daily_turnover(d)
        self.assertEqual(len(result),366);self.assertTrue(pd.isna(result.daily_provider_quote_turnover.iloc[0]))
        self.assertEqual(result.close.iloc[0],0.)
        record=asset_eligibility(dict(ticker='SHIB',first_date='2019-01-01',last_date='2025-12-31'),result,VERIFIED)
        self.assertEqual(record['invalid_ohlc_rows'],2)
        self.assertFalse(record['ranking_eligible'])
        pd.testing.assert_frame_equal(before,d)

    def test_deterministic_terciles_nearest_unused_exact_three(self):
        for n in (9,10,18,61):
            a,s=rank_crypto(self.audit(n),VERIFIED)
            b,t=rank_crypto(self.audit(n).sample(frac=1,random_state=2),VERIFIED)
            pd.testing.assert_frame_equal(a,b);pd.testing.assert_frame_equal(s,t)
            self.assertEqual(s.asset.nunique(),9)
            self.assertTrue(s.groupby('liquidity_tier').size().eq(3).all())
        tied=self.audit().assign(liquidity_measure=1.)
        ranked,_=rank_crypto(tied.sample(frac=1,random_state=1),VERIFIED)
        self.assertEqual(ranked.asset.tolist(),sorted(tied.asset))

    def test_formal_quote_currency_remains_unknown(self):
        d=daily_turnover(self.daily())
        self.assertTrue(d.quote_currency.eq('UNKNOWN').all())
        self.assertIn('formal quote currency remains UNKNOWN',RULE['objective'])
        self.assertNotIn('USD dollar volume',RULE['liquidity_definition'])

    def test_raw_minute_sample_preserves_file_duplicates_zero_and_invalid_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'SYNTH_full_1min.txt'
            path.write_text('2024-01-01 00:00:00,1,2,1,2,0\n'
                '2024-01-01 00:01:00,1,2,1,2,1\n'
                '2024-01-01 06:00:00,2,3,2,3,2\n'
                '2024-01-01 06:00:00,2,3,2,3,2\n'
                '2024-01-01 12:00:00,1,1,0,0,2\n',encoding='utf-8')
            before=path.read_bytes()
            sampled,scan=read_minute_sample(path,'SYNTH')
            self.assertEqual(len(sampled),4)
            self.assertEqual(sampled.sample_valid.tolist(),[True,False,False,False])
            self.assertTrue(sampled.zero_volume.iloc[0])
            self.assertTrue(sampled.invalid_ohlc.iloc[-1])
            self.assertEqual(sampled.timestamp_local.dt.tz.__str__(),'UTC')
            self.assertEqual(scan['raw_rows_scanned'],5)
            self.assertEqual(path.read_bytes(),before)

    def test_import_does_not_load_benchmark(self):
        result=subprocess.run([sys.executable,'-B','-c',
            "import sys;sys.path.insert(0,'src');import crypto_final_universe;assert 'benchmark' not in sys.modules"],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
