import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from benchmark import build_roll_benchmark, summarize_roll_benchmark
from benchmark_diagnostics import read_window


def bars(closes, times=None):
    times = pd.date_range('2024-11-04 09:30', periods=len(closes), freq='min') if times is None else pd.to_datetime(times)
    return pd.DataFrame({'timestamp': times, 'close': closes, 'volume': [1] * len(closes)})


class BenchmarkTests(unittest.TestCase):
    def test_hand_calculated_negative_covariance_and_bps(self):
        # Returns [+0.10, -0.10, +0.10, -0.10]. Three paired vectors:
        # x=[-.1,.1,-.1], y=[.1,-.1,.1], means=-1/30,+1/30.
        # Centered-product sum=-2/75; sample covariance=-1/75.
        daily = build_roll_benchmark(bars([100, 110, 99, 108.9, 98.01]), 'TEST', 'stocks')
        row = daily.iloc[0]
        self.assertEqual(row.one_minute_returns, 4)
        self.assertEqual(row.roll_pairs, 3)
        self.assertAlmostEqual(row.roll_autocovariance, -1 / 75)
        self.assertAlmostEqual(row.roll_spread_relative, 2 / np.sqrt(75))
        self.assertAlmostEqual(row.roll_spread_bps, row.roll_spread_relative * 10000)
        self.assertTrue(row.roll_defined)
        self.assertEqual(row.benchmark_failure_reason, '')

    def test_positive_and_zero_covariance_undefined(self):
        for closes in [[100, 100, 100, 100], [100, 110, 132, 171.6]]:
            row = build_roll_benchmark(bars(closes), 'TEST', 'stocks').iloc[0]
            self.assertGreaterEqual(row.roll_autocovariance, 0)
            self.assertFalse(row.roll_defined)
            self.assertTrue(np.isnan(row.roll_spread_relative))
            self.assertTrue(np.isnan(row.roll_spread_bps))
            self.assertEqual(row.benchmark_failure_reason, 'non_negative_autocovariance')

    def test_gap_breaks_returns_and_pairs(self):
        data = bars([100, 110, 99, 108.9, 98.01], ['2024-11-04 09:30', '2024-11-04 09:31', '2024-11-04 09:33', '2024-11-04 09:34', '2024-11-04 09:35'])
        daily, audit = build_roll_benchmark(data, 'TEST', 'stocks', return_bar_audit=True)
        row = daily.iloc[0]
        self.assertEqual(row.one_minute_returns, 3)
        self.assertEqual(row.roll_pairs, 1)
        self.assertEqual(row.max_gap_minutes, 2)
        self.assertTrue(np.isnan(audit.one_minute_return.iloc[2]))
        self.assertEqual(row.benchmark_failure_reason, 'insufficient_roll_pairs')
        self.assertEqual(len(audit), 5)

    def test_crypto_midnight_boundary(self):
        data = bars([100, 110, 99, 108.9], ['2024-11-04 23:58', '2024-11-04 23:59', '2024-11-05 00:00', '2024-11-05 00:01'])
        daily = build_roll_benchmark(data, 'TEST', 'cryptos')
        self.assertEqual(daily.one_minute_returns.tolist(), [1, 1])
        self.assertEqual(daily.roll_pairs.tolist(), [0, 0])
        self.assertFalse(daily.roll_defined.any())

    def test_equity_session_boundaries(self):
        data = bars([100, 110, 99, 108.9, 98.01], ['2024-11-04 09:29', '2024-11-04 09:30', '2024-11-04 09:31', '2024-11-04 16:00', '2024-11-05 09:30'])
        daily, audit = build_roll_benchmark(data, 'TEST', 'stocks', return_bar_audit=True)
        self.assertEqual(daily.bars_observed.tolist(), [2, 1])
        self.assertEqual(daily.one_minute_returns.tolist(), [1, 0])
        self.assertEqual(daily.roll_pairs.tolist(), [0, 0])
        self.assertEqual(len(audit), 5)

    def test_insufficient_one_pair_preserves_day(self):
        row = build_roll_benchmark(bars([100, 110, 99]), 'TEST', 'stocks').iloc[0]
        self.assertEqual(row.roll_pairs, 1)
        self.assertEqual(row.benchmark_failure_reason, 'insufficient_roll_pairs')
        self.assertTrue(np.isnan(row.roll_autocovariance))

    def test_invalid_close_and_duplicates_break_chain(self):
        for invalid in [0, -1, np.nan, np.inf]:
            daily = build_roll_benchmark(bars([100, 110, invalid, 108.9, 98.01]), 'TEST', 'stocks')
            self.assertEqual(daily.iloc[0].one_minute_returns, 2)
            self.assertEqual(daily.iloc[0].roll_pairs, 0)
        data = bars([100, 110, 111, 99, 108.9], ['2024-11-04 09:30', '2024-11-04 09:31', '2024-11-04 09:31', '2024-11-04 09:32', '2024-11-04 09:33'])
        row = build_roll_benchmark(data, 'TEST', 'stocks').iloc[0]
        self.assertEqual(row.duplicate_timestamp_rows, 2)
        self.assertEqual(row.roll_pairs, 0)
        self.assertEqual(row.bars_observed, 5)

    def test_sort_copy_and_zero_volume_preservation(self):
        data = bars([100, 110, 99, 108.9, 98.01])
        data.volume = 0
        data['sparse_bar'] = [True, False, False, False, False]
        data = data.iloc[[3, 0, 4, 1, 2]]
        original = data.copy(deep=True)
        daily, audit = build_roll_benchmark(data, 'TEST', 'stocks', return_bar_audit=True)
        pd.testing.assert_frame_equal(data, original)
        self.assertEqual(daily.iloc[0].roll_pairs, 3)
        self.assertEqual(daily.iloc[0].zero_volume_rows, 5)
        self.assertEqual(audit.sparse_bar.sum(), 1)
        self.assertEqual(len(audit), len(data))

    def test_summary_keeps_undefined_days(self):
        data = pd.concat([bars([100, 110, 99, 108.9]), bars([100], ['2024-11-05 09:30'])], ignore_index=True)
        summary = summarize_roll_benchmark(build_roll_benchmark(data, 'TEST', 'stocks')).iloc[0]
        self.assertEqual(summary.asset_days, 2)
        self.assertEqual(summary.defined_roll_benchmark_days, 1)
        self.assertEqual(summary.undefined_days, 1)
        self.assertEqual(summary.min_roll_pairs, 0)

    def test_read_window_preserves_raw_file_and_physical_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pilot.txt'
            content = ('2024-11-03 09:30:00,10,11,9,10,1\n'
                       '2024-11-04 09:30:00,10,11,9,10,0\n'
                       'bad,10,11,9,10,1\n'
                       '2024-11-04 09:32:00,10,11,9,10,1\n')
            path.write_text(content, encoding='utf-8')
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            parsed, scan = read_window(path, pd.Timestamp('2024-11-04'), pd.Timestamp('2024-11-05'), Path(folder) / 'problems.csv', chunk_size=2)
            daily = build_roll_benchmark(parsed, 'TEST', 'stocks')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            self.assertEqual(parsed.index.tolist(), [2, 4])
            self.assertEqual(scan['unassignable_timestamp_rows'], 1)
            self.assertEqual(scan['outside_window_rows'], 1)
            self.assertEqual(daily.iloc[0].bars_observed, 2)
            self.assertEqual(daily.iloc[0].one_minute_returns, 0)


if __name__ == '__main__':
    unittest.main()
