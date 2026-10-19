from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from crypto_historical_materialization import aggregate_year,reconstruct_asset,reconcile_2024,TIERS
from crypto_analysis_calendar import exact_calendar,common_asset_dates
from daily_aggregation import aggregate_daily_ohlcv
from eda_diagnostics import parse_chunk
import crypto_analysis_calendar


class CryptoHistoricalTests(unittest.TestCase):
    def lines(self):
        return ['2014-12-31 23:59:00,1,2,1,2,1\n',
            '2024-01-01 23:58:00,1,2,1,2,0\n',
            '2024-01-01 23:59:00,2,3,2,3,2\n',
            '2024-01-03 00:02:00,3,4,3,4,3\n',
            '2025-12-31 23:59:00,4,5,4,5,4\n',
            '2026-01-01 00:00:00,100,101,100,101,9999\n']

    def test_utc_history_clipping_no_2026_no_filling_no_synthetic_days(self):
        _,bars=parse_chunk(self.lines(),1)
        before=bars.copy(deep=True)
        daily,annotated=aggregate_year(bars,'SYNTH')
        self.assertEqual(daily.utc_date.astype(str).tolist(),['2024-01-01','2024-01-03','2025-12-31'])
        self.assertEqual(daily.bars_observed.tolist(),[2,1,1])
        self.assertEqual(daily.volume.tolist(),[2.,3.,4.])
        self.assertTrue(daily.timezone.eq('UTC').all())
        self.assertEqual(daily.zero_volume_rows.tolist(),[1,0,0])
        pd.testing.assert_frame_equal(before,bars)

    def test_streaming_year_partitions_handle_unsorted_input_and_raw_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);source=folder/'SYNTH_full_1min.txt'
            lines=self.lines();source.write_text(''.join([lines[4],lines[2],lines[0],lines[1],lines[5],lines[3]]))
            before=source.read_bytes()
            daily,scan=reconstruct_asset(source,'SYNTH',folder/'derived',chunk_size=2)
            self.assertEqual(daily.utc_date.astype(str).tolist(),['2024-01-01','2024-01-03','2025-12-31'])
            self.assertEqual(daily.open.tolist(),[1.,3.,4.])
            self.assertEqual(scan['rows_after_2025'],1)
            self.assertEqual(scan['rows_before_2015'],1)
            self.assertFalse(list((folder/'derived/staging').rglob('*.pkl')))
            self.assertEqual(source.read_bytes(),before)

    def test_2024_reconciliation_checks_quality_and_prices(self):
        _,bars=parse_chunk(self.lines()[1:4],1)
        historical,_=aggregate_year(bars,'SYNTH')
        reference=aggregate_daily_ohlcv(bars,'SYNTH','cryptos')
        self.assertTrue(reconcile_2024(historical,reference,'SYNTH','fixture')['reconciliation_passed'])
        for field,value in [('close',999),('zero_volume_rows',99),('aggregation_valid',False)]:
            corrupted=reference.copy();corrupted.loc[0,field]=value
            self.assertFalse(reconcile_2024(historical,corrupted,'SYNTH','fixture')['reconciliation_passed'])

    def test_historical_invalid_days_preserved_and_excluded_from_common(self):
        _,bars=parse_chunk(['2023-01-01 00:00:00,1,2,0,2,1\n',
            '2023-01-03 00:00:00,1,2,1,2,1\n'],1)
        daily,_=aggregate_year(bars,'SYNTH')
        self.assertEqual(len(daily),2)
        self.assertEqual(daily.aggregation_valid.tolist(),[False,True])
        self.assertEqual(daily.invalid_price_rows.tolist(),[1,0])
        self.assertTrue(daily.nonpositive_low.iloc[0])
        self.assertEqual(daily.low.iloc[0],0.)
        panels={asset:daily.copy() for assets in TIERS.values() for asset in assets}
        audit,coverage,common=exact_calendar(panels,TIERS)
        self.assertEqual(common,['2023-01-03'])
        self.assertFalse(audit.common_valid_date.iloc[0])
        expanded=common_asset_dates(common,TIERS)
        self.assertEqual(expanded.asset.nunique(),9)
        for tier in TIERS: self.assertEqual(expanded.loc[expanded.liquidity_tier.eq(tier),'date'].tolist(),common*3)

    def test_gaps_are_diagnostics_not_new_invalidity_rule(self):
        _,bars=parse_chunk(['2023-01-01 00:00:00,1,2,1,2,1\n',
            '2023-01-01 00:03:00,1,2,1,2,1\n'],1)
        daily,_=aggregate_year(bars,'SYNTH')
        self.assertEqual(daily.bars_observed.iloc[0],2)
        self.assertEqual(daily.gaps_gt_one_minute.iloc[0],1)
        self.assertEqual(daily.max_gap_minutes.iloc[0],3.)
        self.assertTrue(daily.aggregation_valid.iloc[0])

    def test_selected_assets_tiers_constant_and_no_benchmark_import(self):
        self.assertEqual(TIERS,{'LOW':['ICX','NEO','DASH'],'MEDIUM':['ZEC','ALGO','MKR'],'HIGH':['NEAR','LINK','DOGE']})
        result=subprocess.run([sys.executable,'-B','-c',
            "import sys;sys.path.insert(0,'src');import crypto_historical_materialization;assert 'benchmark' not in sys.modules"],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_old_calendar_command_cannot_overwrite_step12_2_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);spec=folder/'crypto_final_analysis_spec.yaml'
            spec.write_text("approval_step: '12.2'\nstatus: FROZEN\n",encoding='utf-8')
            before=spec.read_bytes()
            with patch.object(crypto_analysis_calendar,'OUT',folder):
                with self.assertRaises(ValueError): crypto_analysis_calendar.run()
            self.assertEqual(spec.read_bytes(),before)


if __name__=='__main__': unittest.main()
