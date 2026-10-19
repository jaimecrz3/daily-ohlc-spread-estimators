from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from estimator_windows import daily_estimate, load_reference_grid
from spread_estimators import ar_two_day


def data():
    return pd.DataFrame(dict(asset=['SYNTH']*4,
        date=['2024-01-05', '2024-01-08', '2024-01-09', '2024-01-10'],
        open=[10., 11, 12, 13], high=[12., 13, 14, 15],
        low=[9., 10, 11, 12], close=[11., 12, 13, 14]))


class WindowTests(unittest.TestCase):
    def test_weekend_not_missing_if_not_in_reference_grid(self):
        frame = data(); grid = frame.date.tolist()
        for method in ['CS', 'AR', 'EDGE']:
            r = daily_estimate(frame, 'SYNTH', '2024-01-08', method, grid)
            self.assertTrue(r['scheduled_adjacency_valid'])
            self.assertTrue(r['window_complete'])
            self.assertEqual(r['input_dates'], grid[1:3] if method == 'AR' else grid[:3])

    def test_missing_source_session_not_bridged(self):
        frame = data(); grid = frame.date.tolist(); sparse = frame.iloc[[0, 2, 3]]
        for method in ['CS', 'EDGE']:
            r = daily_estimate(sparse, 'SYNTH', '2024-01-09', method, grid)
            self.assertFalse(r['scheduled_adjacency_valid'])
            self.assertFalse(r['estimator_defined'])
            self.assertEqual(r['failure_reason'], 'missing_previous_scheduled_period')

    def test_missing_next_retained_undefined(self):
        frame = data()
        for method in ['CS', 'AR', 'EDGE']:
            r = daily_estimate(frame.iloc[:2], 'SYNTH', '2024-01-08', method, frame.date.tolist())
            self.assertEqual(r['failure_reason'], 'missing_next_scheduled_period')
            self.assertTrue(np.isnan(r['primary_spread_relative']))

    def test_ar_alignment_is_close_t_and_midpoint_t_plus_one(self):
        frame = data()
        r = daily_estimate(frame, 'SYNTH', '2024-01-08', 'AR', frame.date)
        expected = ar_two_day([13, 14], [10, 11], 12)
        self.assertEqual(r['raw_moment'], expected['raw_moment'])
        self.assertEqual(r['input_observations'], 2)

    def test_unused_fields_do_not_break_cs_or_ar(self):
        frame = data(); frame['open'] = np.nan; frame.loc[2, 'close'] = np.nan
        for method in ['CS', 'AR']:
            r = daily_estimate(frame, 'SYNTH', '2024-01-08', method, frame.date)
            self.assertTrue(r['window_complete'])
            self.assertTrue(r['estimator_defined'])

    def test_no_imputation_and_no_cross_asset_neighbors(self):
        frame = data(); frame.loc[2, 'high'] = np.nan
        before = frame.copy(deep=True)
        for method in ['CS', 'AR', 'EDGE']:
            r = daily_estimate(frame, 'SYNTH', '2024-01-08', method, frame.date)
            self.assertFalse(r['estimator_defined']); self.assertFalse(r['window_complete'])
        pd.testing.assert_frame_equal(frame, before)
        frame.loc[0, 'asset'] = 'OTHER'
        r = daily_estimate(frame, 'SYNTH', '2024-01-08', 'CS', frame.date)
        self.assertEqual(r['failure_reason'], 'missing_previous_scheduled_period')

    def test_edges_of_reference_grid_require_both_neighbors(self):
        frame = data()
        self.assertEqual(daily_estimate(frame, 'SYNTH', '2024-01-05', 'CS', frame.date)['failure_reason'],
                         'missing_previous_scheduled_period')
        self.assertEqual(daily_estimate(frame, 'SYNTH', '2024-01-10', 'AR', frame.date)['failure_reason'],
                         'missing_next_scheduled_period')

    def test_crypto_weekend_is_expected_and_missing_breaks_window(self):
        frame = data(); grid = pd.date_range('2024-01-05', '2024-01-10')
        r = daily_estimate(frame, 'SYNTH', '2024-01-08', 'EDGE', grid)
        self.assertEqual(r['failure_reason'], 'missing_previous_scheduled_period')

    def test_uses_pre_intersection_stock_grid_not_primary_dates(self):
        grid = load_reference_grid('stocks')
        self.assertIn(pd.Timestamp('2019-07-31'), grid)
        self.assertIn(pd.Timestamp('2019-08-01'), grid)
        self.assertNotIn(pd.Timestamp('2024-01-06'), grid)

    def test_futures_grid_unchanged_and_crypto_full_calendar(self):
        self.assertEqual(len(load_reference_grid('futures')), 259)
        grid = load_reference_grid('crypto')
        self.assertEqual(grid[0], pd.Timestamp('2015-01-01'))
        self.assertEqual(grid[-1], pd.Timestamp('2025-12-31'))
        self.assertTrue((grid[1:]-grid[:-1] == pd.Timedelta(days=1)).all())

    def test_duplicate_source_dates_and_bad_grid_rejected(self):
        frame = data()
        with self.assertRaises(ValueError): daily_estimate(pd.concat([frame, frame.iloc[:1]]), 'SYNTH', frame.date[1], 'CS', frame.date)
        with self.assertRaises(ValueError): daily_estimate(frame, 'SYNTH', frame.date[1], 'CS', frame.date[::-1])

    def test_fx_cannot_use_another_class_grid(self):
        with self.assertRaises(ValueError): load_reference_grid('fx')

    def test_result_contract(self):
        frame = data(); r = daily_estimate(frame, 'SYNTH', '2024-01-08', 'EDGE', frame.date)
        self.assertTrue({'asset', 'target_date', 'estimator', 'raw_moment', 'raw_signed_spread_relative',
            'raw_negative', 'primary_spread_relative', 'primary_spread_bps', 'estimator_defined',
            'failure_reason', 'input_dates', 'input_observations', 'window_complete',
            'scheduled_adjacency_valid', 'method_specific_diagnostics'}.issubset(r))


if __name__ == '__main__':
    unittest.main()
