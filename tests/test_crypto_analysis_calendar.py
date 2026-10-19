from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from crypto_analysis_calendar import exact_calendar,common_asset_dates,TIERS,assert_preserved
from bloomberg_io import sha256


class CryptoAnalysisCalendarTests(unittest.TestCase):
    def panels(self):
        return {asset:pd.DataFrame(dict(date=['2022-02-02','2022-02-04','2024-01-01'],
            aggregation_valid=True,bars_observed=1,timezone='UTC'))
            for assets in TIERS.values() for asset in assets}

    def test_exact_intersection_excludes_missing_and_invalid_observations(self):
        panels=self.panels()
        panels['ICX']=panels['ICX'].iloc[1:].copy()
        panels['LINK'].loc[1,'aggregation_valid']=False
        audit,coverage,common=exact_calendar(panels,TIERS)
        self.assertEqual(common,['2024-01-01'])
        self.assertEqual(audit.loc[audit.date.eq('2022-02-02'),'missing_assets'].iloc[0],'ICX')
        self.assertEqual(audit.loc[audit.date.eq('2022-02-04'),'invalid_assets'].iloc[0],'LINK')

    def test_no_synthesized_days_no_compression_and_input_unchanged(self):
        panels=self.panels();before={a:d.copy(deep=True) for a,d in panels.items()}
        audit,coverage,common=exact_calendar(panels,TIERS)
        self.assertNotIn('2022-02-03',common)
        self.assertEqual(audit.date.tolist(),['2022-02-02','2022-02-04','2024-01-01'])
        for asset in panels: pd.testing.assert_frame_equal(panels[asset],before[asset])

    def test_nine_assets_on_each_common_date(self):
        common=exact_calendar(self.panels(),TIERS)[2]
        expanded=common_asset_dates(common,TIERS)
        self.assertEqual(len(expanded),len(common)*9)
        self.assertTrue(expanded.groupby('date').asset.nunique().eq(9).all())

    def test_identical_dates_across_tiers(self):
        common=exact_calendar(self.panels(),TIERS)[2]
        expanded=common_asset_dates(common,TIERS)
        for tier in TIERS:
            group=expanded.loc[expanded.liquidity_tier.eq(tier)]
            self.assertEqual(set(group.date),set(common))
            self.assertTrue(group.groupby('date').asset.nunique().eq(3).all())

    def test_selection_and_ranking_integrity_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            paths=[Path(directory)/name for name in ['selected_crypto.csv','selection_audit.csv']]
            for path in paths: path.write_text('asset,rank\nICX,1\n',encoding='utf-8')
            baseline={path:sha256(path) for path in paths}
            assert_preserved(baseline)
            for path in paths:
                before=path.read_bytes();path.write_text('changed',encoding='utf-8')
                with self.assertRaises(AssertionError): assert_preserved(baseline)
                path.write_bytes(before)

    def test_raw_endpoint_is_never_a_calendar_input(self):
        panels=self.panels()
        for frame in panels.values(): frame['first_observed_date']='2015-01-01'
        audit,coverage,common=exact_calendar(panels,TIERS)
        self.assertEqual(min(common),'2022-02-02')
        self.assertTrue(coverage.first_valid_observed_utc_date.eq('2022-02-02').all())

    def test_no_benchmark_dependency(self):
        result=subprocess.run([sys.executable,'-B','-c',
            "import sys;sys.path.insert(0,'src');import crypto_analysis_calendar;assert 'benchmark' not in sys.modules"],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
