from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from futures_targeted_session_review import calendar_comparison


class TargetedSessionDesignTests(unittest.TestCase):
    def fixture(self):
        tiers=dict(HG='LOW',AD='LOW',B6='LOW',J1='MEDIUM',GC='MEDIUM',E6='MEDIUM',
            NQ='HIGH',ZF='HIGH',ES='HIGH')
        panels={root:pd.DataFrame({'date':['2024-01-02','2024-01-03']}) for root in tiers}
        for root in ('HG','GC','NQ','ES'):
            panels[root]=pd.DataFrame({'date':['2015-01-02','2024-01-02','2024-01-03']})
        return panels,tiers

    def test_common_calendar_uses_intersection_without_filling_or_compression(self):
        panels,tiers=self.fixture()
        panels['AD']=pd.DataFrame({'date':['2024-01-03']})
        before={root:frame.copy(deep=True) for root,frame in panels.items()}
        roots,tier,common,identical=calendar_comparison(panels,tiers)
        self.assertEqual({day.isoformat() for day in common},{'2024-01-03'})
        self.assertFalse(identical)
        self.assertEqual(roots.common_2024_days.tolist(),[1]*9)
        self.assertEqual(int(tier.B_asset_days.sum()),9)
        for root in panels:
            pd.testing.assert_frame_equal(before[root],panels[root])

    def test_unbalanced_full_history_tier_support_is_explicit(self):
        panels,tiers=self.fixture()
        roots,tier,common,identical=calendar_comparison(panels,tiers)
        tier=tier.set_index('liquidity_tier')
        self.assertTrue(identical)
        self.assertEqual(len(common),2)
        self.assertEqual(tier.A_asset_days.to_dict(),{'HIGH':8,'LOW':7,'MEDIUM':7})
        self.assertEqual(tier.B_asset_days.to_dict(),{'HIGH':6,'LOW':6,'MEDIUM':6})
        self.assertEqual(roots.set_index('provider_root').loc['AD','non_2024_days'],0)

    def test_prices_and_benchmark_estimator_fields_have_no_effect(self):
        panels,tiers=self.fixture()
        expected=calendar_comparison(panels,tiers)
        changed={root:df.assign(close=-100,volume=0,roll_defined=False,roll_spread_bps=999,
            CS=-1,AR=-1,EDGE=-1) for root,df in panels.items()}
        actual=calendar_comparison(changed,tiers)
        pd.testing.assert_frame_equal(expected[0],actual[0])
        pd.testing.assert_frame_equal(expected[1],actual[1])
        self.assertEqual(expected[2:],actual[2:])

    def test_duplicate_missing_dates_and_root_mismatch_rejected(self):
        for dates in (['2024-01-02','2024-01-02'],['2024-01-02',None]):
            with self.assertRaises(ValueError):
                calendar_comparison({'AD':pd.DataFrame({'date':dates})},{'AD':'LOW'})
        with self.assertRaises(ValueError):
            calendar_comparison({'AD':pd.DataFrame({'date':['2024-01-02']})},{'ZF':'HIGH'})


if __name__=='__main__':
    unittest.main()
