import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from daily_aggregation import aggregate_daily_ohlcv, validate_daily_ohlcv, summarize_daily_ohlcv
from futures_roll import parse_provider_calendar, contract_file, selection_plan, validate_sessions
from session_rules import assign_primary_session
from benchmark_diagnostics import read_window


def bars(times):
    n = len(times)
    return pd.DataFrame({'timestamp': pd.to_datetime(times), 'open': [100.] * n,
        'high': [105.] * n, 'low': [95.] * n, 'close': [101.] * n, 'volume': [2.] * n})


class DailyAggregationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def selected(self, times, codes=None, dates=None):
        data = bars(times)
        codes = codes or ['Z24'] * len(data)
        data = assign_primary_session(data, 'futures', futures_root='ES')
        data['source_contract'] = codes
        path = self.folder / 'calendar.txt'
        dates = dates or [('2024-11-04', 'Z24')]
        path.write_text(''.join(f'{day},{code}\n' for day, code in dates), encoding='utf-8')
        for code in set(code for _, code in dates):
            contract_file(self.folder, 'ES', code).touch()
        plan = selection_plan(parse_provider_calendar(path), 'ES', dates[0][0], dates[-1][0], self.folder)
        inputs = {code: data.loc[data.source_contract.eq(code)].copy() for code in set(codes)}
        audit, selected = validate_sessions(plan, inputs)
        return audit, selected

    def test_hand_calculated_chronological_ohlcv(self):
        data = bars(['2024-11-04 09:32', '2024-11-04 09:30', '2024-11-04 09:31'])
        data[['open', 'high', 'low', 'close', 'volume']] = [[102, 105, 101, 104, 3], [100, 102, 99, 101, 1], [101, 104, 100, 103, 2]]
        original = data.copy(deep=True)
        daily, audit = aggregate_daily_ohlcv(data, 'AAPL', 'stocks', return_bar_audit=True)
        row = daily.iloc[0]
        self.assertEqual(row[['open', 'high', 'low', 'close', 'volume']].tolist(), [100, 105, 99, 104, 6])
        self.assertTrue(row.aggregation_valid)
        self.assertEqual(row.bars_observed, 3)
        self.assertEqual(row.first_timestamp.minute, 30)
        self.assertEqual(row.last_timestamp.minute, 32)
        validate_daily_ohlcv(daily, audit)
        pd.testing.assert_frame_equal(data, original)

    def test_equity_boundaries_and_source_roles(self):
        data = bars(['2024-11-04 09:29', '2024-11-04 09:30', '2024-11-04 15:59', '2024-11-04 16:00'])
        for cls in ['stocks', 'etfs']:
            daily = aggregate_daily_ohlcv(data, 'TEST', cls)
            self.assertEqual(daily.iloc[0].bars_observed, 2)
            self.assertEqual(daily.iloc[0].volume, 4)
            self.assertEqual(daily.iloc[0].source_role, 'local_daily_validation')
            self.assertEqual(daily.iloc[0].adjustment, 'split_and_dividend_adjusted')
            self.assertEqual(daily.iloc[0].timezone, 'America/New_York')

    def test_crypto_utc_day_no_quote_assumption(self):
        data = bars(['2024-11-04 23:59', '2024-11-05 00:00'])
        data.loc[1, ['open', 'high', 'low', 'close']] = [200, 210, 190, 201]
        daily = aggregate_daily_ohlcv(data, 'BTC', 'cryptos')
        self.assertEqual(daily.date.astype(str).tolist(), ['2024-11-04', '2024-11-05'])
        self.assertEqual(daily.open.tolist(), [100, 200])
        self.assertEqual(daily.volume.tolist(), [2, 2])
        self.assertTrue(daily.source_role.eq('primary_daily_input').all())
        self.assertTrue(daily.timezone.eq('UTC').all())
        self.assertNotIn('daily_notional_volume', daily)
        aware = bars(['2024-11-04 19:00'])
        aware.timestamp = aware.timestamp.dt.tz_localize('America/New_York')
        self.assertEqual(str(aggregate_daily_ohlcv(aware, 'ETH', 'cryptos').date.iloc[0]), '2024-11-05')

    def test_futures_overnight_and_maintenance(self):
        sessions, data = self.selected(['2024-11-03 18:00', '2024-11-04 16:59', '2024-11-04 17:30'])
        extra = bars(['2024-11-04 17:30']).assign(source_contract='Z24', selected_contract='Z24', root='ES')
        extra.loc[0, ['open', 'high', 'low', 'close', 'volume']] = [1000, 2000, 1, 1500, 999]
        data = pd.concat([data, extra], ignore_index=True)
        daily, annotated = aggregate_daily_ohlcv(data, 'ES', 'futures', futures_root='ES', futures_audit=sessions, return_bar_audit=True)
        row = daily.iloc[0]
        self.assertEqual(str(row.date), '2024-11-04')
        self.assertEqual(row.bars_observed, 2)
        self.assertEqual(row.volume, 4)
        self.assertEqual(row.high, 105)
        self.assertEqual(row.first_timestamp.day, 3)
        self.assertEqual(annotated.maintenance_interval.sum(), 1)
        validate_daily_ohlcv(daily, annotated)

    def test_futures_mixed_contracts_rejected(self):
        sessions, data = self.selected(['2024-11-03 18:00', '2024-11-04 09:30'])
        data.loc[data.index[-1], ['selected_contract', 'source_contract']] = 'H25'
        with self.assertRaises(ValueError):
            aggregate_daily_ohlcv(data, 'ES', 'futures', futures_root='ES', futures_audit=sessions)

    def test_futures_audit_mismatch_and_adjusted_filename_rejected(self):
        sessions, data = self.selected(['2024-11-03 18:00'])
        for column, value in [('selected_contract', 'H25'), ('contract_file', 'ES_continuous_adjusted_1min.txt'),
                              ('provider_mapping_date', pd.Timestamp('2024-11-03').date()), ('bars_observed', 99), ('validation_status', 'no_session_observations')]:
            wrong = sessions.copy()
            wrong.loc[0, column] = value
            with self.assertRaises(ValueError):
                aggregate_daily_ohlcv(data, 'ES', 'futures', futures_root='ES', futures_audit=wrong)

    def test_roll_day_and_previous_contract_preserved(self):
        sessions, data = self.selected(['2024-11-03 18:00', '2024-11-04 18:00'], ['Z24', 'H25'], [('2024-11-04', 'Z24'), ('2024-11-05', 'H25')])
        daily = aggregate_daily_ohlcv(data, 'ES', 'futures', futures_root='ES', futures_audit=sessions)
        self.assertEqual(daily.roll_day.tolist(), [False, True])
        self.assertEqual(daily.previous_contract.iloc[1], 'Z24')
        self.assertEqual(daily.selected_contract.tolist(), ['Z24', 'H25'])
        self.assertEqual(daily.volume.tolist(), [2, 2])

    def test_no_synthetic_dates_or_missing_bars(self):
        data = bars(['2024-11-04 09:30', '2024-11-04 09:33', '2024-11-06 09:30'])
        daily, annotated = aggregate_daily_ohlcv(data, 'AAPL', 'stocks', return_bar_audit=True)
        self.assertEqual(daily.date.astype(str).tolist(), ['2024-11-04', '2024-11-06'])
        self.assertEqual(daily.bars_observed.tolist(), [2, 1])
        self.assertEqual(daily.volume.tolist(), [4, 2])
        self.assertEqual(daily.max_gap_minutes.iloc[0], 3)
        self.assertTrue(daily.aggregation_valid.all())
        self.assertEqual(len(annotated), len(data))

    def test_zero_observation_analytic_rows_absent(self):
        for data in [bars([]), bars(['2024-11-04 16:00'])]:
            self.assertTrue(aggregate_daily_ohlcv(data, 'AAPL', 'stocks').empty)
        sessions, data = self.selected(['2024-11-03 18:00'], dates=[('2024-11-04', 'Z24'), ('2024-11-05', 'Z24')])
        daily = aggregate_daily_ohlcv(data, 'ES', 'futures', futures_root='ES', futures_audit=sessions)
        self.assertEqual(len(sessions), 2)
        self.assertEqual(len(daily), 1)
        self.assertTrue(daily.bars_observed.gt(0).all())

    def test_zero_volume_preserved_does_not_invalidate(self):
        data = bars(['2024-11-04 09:30', '2024-11-04 09:32'])
        data.volume = 0
        row = aggregate_daily_ohlcv(data, 'AAPL', 'stocks').iloc[0]
        self.assertEqual(row.volume, 0)
        self.assertEqual(row.zero_volume_rows, 2)
        self.assertTrue(row.aggregation_valid)

    def test_duplicates_preserved_and_flagged(self):
        data = bars(['2024-11-04 09:30', '2024-11-04 09:30'])
        row = aggregate_daily_ohlcv(data, 'AAPL', 'stocks').iloc[0]
        self.assertEqual(row.bars_observed, 2)
        self.assertEqual(row.volume, 4)
        self.assertEqual(row.duplicate_timestamp_rows, 2)
        self.assertFalse(row.aggregation_valid)

    def test_missing_reductions_not_partial_and_positional_endpoints(self):
        for field in ['high', 'low', 'volume']:
            data = bars(['2024-11-04 09:30', '2024-11-04 09:31'])
            data.loc[0, field] = np.nan
            row = aggregate_daily_ohlcv(data, 'AAPL', 'stocks').iloc[0]
            self.assertTrue(np.isnan(row[field]))
            self.assertFalse(row.aggregation_valid)
            self.assertEqual(row.bars_observed, 2)
        data.loc[0, 'open'] = np.nan
        data.loc[1, 'close'] = np.nan
        row = aggregate_daily_ohlcv(data, 'AAPL', 'stocks').iloc[0]
        self.assertTrue(np.isnan(row.open) and np.isnan(row.close))

    def test_invalid_intraday_ohlc_keeps_day(self):
        data = bars(['2024-11-04 09:30', '2024-11-04 09:31'])
        data.loc[1, 'open'] = 110
        row = aggregate_daily_ohlcv(data, 'AAPL', 'stocks').iloc[0]
        self.assertFalse(row.aggregation_valid)
        self.assertEqual(row.invalid_ohlc_rows, 1)
        self.assertIn('invalid_ohlc', row.aggregation_failure_reason)

    def test_benchmark_values_ignored_and_absent(self):
        data = bars(['2024-11-04 09:30'])
        clean = aggregate_daily_ohlcv(data, 'AAPL', 'stocks')
        other = aggregate_daily_ohlcv(data.assign(roll_defined=True, roll_spread_bps=123, EDGE=999, cs=10, ar=20), 'AAPL', 'stocks')
        pd.testing.assert_frame_equal(clean, other)
        self.assertFalse({'roll_defined', 'roll_spread_bps', 'EDGE', 'cs', 'ar'} & set(other))

    def test_existing_detail_flags_preserved_without_coverage_exclusion(self):
        data = bars(['2024-11-04 09:30']).assign(sparse_bar=True, missing_open=False)
        daily, audit = aggregate_daily_ohlcv(data, 'AAPL', 'stocks', return_bar_audit=True)
        self.assertTrue(audit.sparse_bar.iloc[0])
        self.assertFalse(audit.missing_open.iloc[0])
        self.assertTrue(daily.aggregation_valid.iloc[0])
        self.assertEqual(daily.bars_observed.iloc[0], 1)

    def test_raw_file_hash_and_physical_rows_unchanged(self):
        path = self.folder / 'AAPL_full_1min_adjsplitdiv.txt'
        path.write_text('2024-11-04 09:30:00,100,105,95,101,0\n2024-11-04 09:32:00,100,105,95,102,3\n', encoding='utf-8')
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        data, _ = read_window(path, pd.Timestamp('2024-11-04'), pd.Timestamp('2024-11-05'), self.folder / 'problems.csv')
        daily = aggregate_daily_ohlcv(data, 'AAPL', 'stocks')
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
        self.assertEqual(daily.iloc[0].bars_observed, 2)
        self.assertEqual(daily.iloc[0].max_gap_minutes, 2)

    def test_summary(self):
        data = bars(['2024-11-04 09:30', '2024-11-04 09:32', '2024-11-06 09:30'])
        daily = aggregate_daily_ohlcv(data, 'AAPL', 'stocks')
        summary = summarize_daily_ohlcv(daily).iloc[0]
        self.assertEqual(summary.observed_asset_days, 2)
        self.assertEqual(summary.total_retained_bars, 3)
        self.assertEqual(summary.days_with_gaps_gt_1_minute, 1)
        self.assertEqual(summary.invalid_aggregation_days, 0)


if __name__ == '__main__':
    unittest.main()
