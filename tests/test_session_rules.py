import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from data_io import asset_metadata
from eda_diagnostics import parse_chunk, validate_parser
from session_rules import assign_primary_session, filter_primary_session, FuturesSessionConfig


def bars(times, volumes=None):
    return pd.DataFrame({'timestamp': pd.to_datetime(times), 'volume': volumes or [1] * len(times)})


class SessionTests(unittest.TestCase):
    def test_timezone_and_metadata(self):
        for cls, tz, unit in [('stocks', 'America/New_York', 'shares'), ('etfs', 'America/New_York', 'shares'), ('cryptos', 'UTC', 'crypto units')]:
            result = assign_primary_session(bars(['2024-01-02 09:30']), cls)
            self.assertEqual(str(result.timestamp_local.dt.tz), tz)
            self.assertEqual(asset_metadata(cls)['volume_units'], unit)
        self.assertEqual(asset_metadata('futures')['adjustment'], 'unadjusted individual contracts')
        self.assertIn('split+dividend', asset_metadata('stocks')['adjustment'])
        with self.assertRaises(ValueError):
            asset_metadata('fx')

    def test_dst_offsets(self):
        result = assign_primary_session(bars(['2024-03-08 09:30', '2024-03-11 09:30', '2024-11-01 09:30', '2024-11-04 09:30']), 'stocks')
        self.assertEqual(result.timestamp_local.dt.tz_convert('UTC').dt.hour.tolist(), [14, 13, 13, 14])
        self.assertTrue(result.primary_session_retained.all())

    def test_dst_unresolvable_preserved(self):
        result = assign_primary_session(bars(['2024-03-10 02:30', '2024-11-03 01:30']), 'stocks')
        self.assertEqual(len(result), 2)
        self.assertTrue(result.timezone_assignment_failed.all())
        self.assertTrue(result.timestamp_local.isna().all())

    def test_equity_rth_boundaries(self):
        for cls in ['stocks', 'etfs']:
            result = assign_primary_session(bars(['2024-01-02 09:29:59', '2024-01-02 09:30:00', '2024-01-02 15:59:59', '2024-01-02 16:00:00']), cls)
            self.assertEqual(result.primary_session_retained.tolist(), [False, True, True, False])
            self.assertEqual(len(filter_primary_session(result, cls)), 2)

    def test_crypto_utc_day(self):
        result = assign_primary_session(bars(['2024-01-02 23:59', '2024-01-03 00:00']), 'cryptos')
        self.assertEqual(result.session_day.astype(str).tolist(), ['2024-01-02', '2024-01-03'])
        aware = bars(['2024-01-02 19:00'])
        aware['timestamp'] = aware.timestamp.dt.tz_localize('America/New_York')
        self.assertEqual(str(assign_primary_session(aware, 'cryptos').session_day.iloc[0]), '2024-01-03')

    def test_gaps_duplicates_and_flags_preserved(self):
        data = bars(['2024-01-02 09:30', '2024-01-02 09:30', '2024-01-02 09:33'])
        data.index = [4, 8, 12]
        data['duplicate_timestamp'] = [True, True, False]
        data['invalid_ohlc'] = [False, True, False]
        data['sparse_bar'] = [False, False, True]
        result = filter_primary_session(data, 'stocks')
        pd.testing.assert_frame_equal(result[data.columns], data)
        self.assertEqual(len(result), 3)

    def test_zero_volume_parser_and_session(self):
        _, parsed = parse_chunk(['2024-01-02 09:30:00,10,11,9,10,0\n', '2024-01-02 09:32:00,10,11,9,,2\n'], 10)
        result = filter_primary_session(parsed, 'stocks')
        self.assertEqual(len(result), 2)
        self.assertTrue(result.loc[10, 'zero_volume'])
        self.assertTrue(result.loc[10, 'provider_zero_volume_discrepancy'])
        self.assertTrue(result.loc[11, 'missing_value'])

    def test_futures_pending(self):
        config = FuturesSessionConfig('ES')
        self.assertIsNone(config.start)
        with self.assertRaises(NotImplementedError):
            assign_primary_session(bars(['2024-01-02 09:30']), 'futures', futures_root='ES', futures_sessions={'ES': config})

    def test_invalid_timestamp_flagged_without_mutation(self):
        data = bars(['2024-01-02 09:30', None])
        original = data.copy(deep=True)
        result = assign_primary_session(data, 'stocks')
        self.assertEqual(len(result), 2)
        self.assertTrue(result.unassignable_timestamp.iloc[1])
        self.assertFalse(result.primary_session_retained.iloc[1])
        pd.testing.assert_frame_equal(data, original)

    def test_existing_parser_regression(self):
        validate_parser()


if __name__ == '__main__':
    unittest.main()
