import ast
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import universe_selection as universe


def bars(times, closes, volumes):
    return pd.DataFrame({'timestamp': pd.to_datetime(times), 'close': closes, 'volume': volumes})


def daily(days, notional=100):
    return pd.DataFrame({'date': pd.date_range('2024-01-01', periods=days).date,
        'bars_observed': [2] * days, 'daily_volume': [10] * days,
        'daily_dollar_notional_volume': [notional] * days,
        'zero_volume_rows': [0] * days, 'duplicate_timestamp_rows': [0] * days})


class UniverseTests(unittest.TestCase):
    def test_hand_dollar_volume_and_median(self):
        data = bars(['2024-01-02 09:30', '2024-01-02 09:32', '2024-01-03 09:30'], [10, 20, 30], [2, 3, 4])
        result = universe.daily_liquidity(data, 'stocks')
        self.assertEqual(result.daily_dollar_notional_volume.tolist(), [80, 120])
        self.assertEqual(result.daily_volume.tolist(), [5, 4])
        stats = universe.liquidity_stats(result, 'stocks')
        self.assertEqual(stats['liquidity_measure'], 100)
        self.assertEqual(stats['median_daily_volume'], 4.5)
        self.assertEqual(result.bars_observed.sum(), 3)  # 09:31 is never inserted

    def test_class_sessions_and_calibration_year(self):
        data = bars(['2023-12-31 23:59', '2024-01-02 00:00', '2024-01-02 09:29', '2024-01-02 09:30', '2024-01-02 15:59', '2024-01-02 16:00', '2024-01-02 23:59', '2025-01-01 09:30'], [10] * 8, [1] * 8)
        for cls in ['stocks', 'etfs']:
            result = universe.daily_liquidity(data, cls)
            self.assertEqual(result.bars_observed.sum(), 2)
            self.assertEqual(result.daily_dollar_notional_volume.sum(), 20)
        crypto = universe.daily_liquidity(data, 'cryptos')
        self.assertEqual(crypto.bars_observed.sum(), 6)
        self.assertEqual(crypto.daily_dollar_notional_volume.sum(), 60)

    def test_crypto_quote_confirmation_and_cross_pairs(self):
        self.assertEqual(universe.crypto_quote_currency('BTC-EUR', True), 'EUR')
        self.assertEqual(universe.crypto_quote_currency('ETH-BTC', True), 'BTC')
        self.assertEqual(universe.crypto_quote_currency('BTC-USD'), 'USD')
        self.assertEqual(universe.crypto_quote_currency('ADA'), 'UNRESOLVED')
        self.assertEqual(universe.crypto_quote_currency('ADA', True), 'USD')

    def test_minimum_day_boundaries(self):
        for cls, cutoff in [('stocks', 200), ('etfs', 200), ('cryptos', 300)]:
            self.assertFalse(universe.liquidity_stats(daily(cutoff - 1), cls)['ranking_eligible'])
            self.assertTrue(universe.liquidity_stats(daily(cutoff), cls)['ranking_eligible'])

    def test_independent_tertiles_ties_and_remainder(self):
        table = pd.DataFrame({'asset': list('ABCDEFG') * 2,
            'asset_class': ['stocks'] * 7 + ['cryptos'] * 7,
            'liquidity_measure': [1, 1, 2, 3, 4, 5, 6] + [v * 1000 for v in range(1, 8)],
            'ranking_eligible': [True] * 14})
        ranking = universe.assign_tiers(table.sample(frac=1, random_state=1))
        for _, group in ranking.groupby('asset_class'):
            self.assertEqual(group.liquidity_tier.tolist(), ['LOW'] * 3 + ['MEDIUM'] * 2 + ['HIGH'] * 2)
            self.assertEqual(group.liquidity_rank.tolist(), list(range(1, 8)))
        self.assertEqual(ranking.loc[ranking.asset_class.eq('stocks')].asset.iloc[0], 'A')

    def test_deterministic_prescreen_spans_file_distribution(self):
        table = pd.DataFrame({'asset': [f'A{i:03}' for i in range(200)],
            'file': [f'A{i:03}.txt' for i in range(200)], 'file_size_bytes': np.arange(200) // 2})
        a = universe.deterministic_prescreen(table, 60)
        b = universe.deterministic_prescreen(table.sample(frac=1, random_state=42), 60)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(len(a), 60)
        self.assertEqual(a.asset.nunique(), 60)
        self.assertEqual(a.prescreen_position.iloc[0], 0)
        self.assertEqual(a.prescreen_position.iloc[-1], 199)
        self.assertEqual(len(universe.deterministic_prescreen(table.head(2))), 2)

    def test_benchmark_estimator_columns_irrelevant(self):
        clean = bars(['2024-01-02 09:30', '2024-01-02 09:31'], [10, 20], [2, 3])
        contaminated = clean.assign(roll_defined=False, roll_spread_bps=999, cs=999, ar=999, edge=999)
        pd.testing.assert_frame_equal(universe.daily_liquidity(clean, 'stocks'), universe.daily_liquidity(contaminated, 'stocks'))
        pool = pd.DataFrame({'asset': list('ABC'), 'asset_class': ['stocks'] * 3, 'liquidity_measure': [1, 2, 3], 'ranking_eligible': [True] * 3})
        pd.testing.assert_frame_equal(universe.assign_tiers(pool), universe.assign_tiers(pool.assign(roll_defined=False, EDGE=999)))
        code = ast.parse(Path(universe.__file__).read_text(encoding='utf-8'))
        modules = [node.module for node in ast.walk(code) if isinstance(node, ast.ImportFrom)]
        self.assertFalse(any('benchmark' in (m or '') for m in modules))

    def test_raw_file_hash_and_dataframe_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder / 'TEST.txt'
            path.write_text('2015-01-02 09:30:00,10,11,9,10,1\n2024-01-02 09:30:00,10,11,9,10,0\n2024-01-02 09:32:00,10,11,9,10,2', encoding='utf-8')
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            data, scan = universe.scan_candidate(path, folder / 'problems.csv', folder / 'flags.csv')
            original = data.copy(deep=True)
            result = universe.daily_liquidity(data, 'stocks')
            pd.testing.assert_frame_equal(data, original)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            self.assertEqual(scan['bytes_scanned'], path.stat().st_size)
            self.assertEqual(scan['observed_study_years'], 2)
            self.assertEqual(result.zero_volume_rows.sum(), 1)
            self.assertEqual(result.bars_observed.sum(), 2)
            self.assertEqual(data.index.tolist(), [2, 3])

    def test_unknown_total_never_partial_zero_sum(self):
        data = bars(['2024-01-02 09:30', '2024-01-02 09:31'], [10, np.nan], [2, 3])
        result = universe.daily_liquidity(data, 'stocks')
        self.assertTrue(np.isnan(result.daily_dollar_notional_volume.iloc[0]))
        self.assertEqual(result.bars_observed.sum(), 2)

    def test_missing_calibration_year_is_audited_not_filled(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            path = folder / 'NO2024.txt'
            path.write_text('2015-01-02 09:30:00,10,11,9,10,1\n2025-01-02 09:30:00,10,11,9,10,1\n', encoding='utf-8')
            data, scan = universe.scan_candidate(path, folder / 'problems.csv', folder / 'flags.csv')
            self.assertTrue(data.empty)
            self.assertEqual(scan['raw_2024_rows'], 0)
            self.assertEqual(scan['bytes_scanned'], path.stat().st_size)
            self.assertEqual(scan['observed_study_dates'], 2)

    def test_conservative_naming_and_history_clip(self):
        self.assertEqual(universe.ticker_review('ABC-W')[0], 'non_standard_security_form')
        self.assertEqual(universe.ticker_review('ABC-PB')[0], 'non_standard_security_form')
        self.assertEqual(universe.ticker_review('ABCDW', 'Abcd Warrant')[0], 'non_standard_security_form')
        self.assertEqual(universe.ticker_review('ESGRP', 'Enstar Depositary Shares Interest In Preference Shares')[0], 'non_standard_security_form')
        self.assertEqual(universe.ticker_review('ARROW', 'Arrow Corporation')[0], '')
        self.assertEqual(universe.ticker_review('BRK-B', 'Berkshire Class B')[0], '')
        self.assertTrue(universe.history_eligible('2020-01-01', '2024-12-31', 'stocks'))
        self.assertFalse(universe.history_eligible('2021-01-01', '2025-12-30', 'stocks'))
        self.assertFalse(universe.history_eligible('2000-01-01', '2019-12-30', 'stocks'))
        self.assertTrue(universe.history_eligible('2023-01-01', '2025-12-31', 'cryptos'))

    def test_inventory_audits_currency_missing_files_and_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            doc = root / '_documentation/.archive'
            doc.mkdir(parents=True)
            for cls in universe.CLASSES:
                (root / cls).mkdir()
                tickers = ['BTC', 'BTC-EUR', 'ETH-BTC'] if cls == 'cryptos' else ['ABC', 'MISSING', 'NEW']
                lines = ['Ticker,Name,First Date,Last Date']
                for ticker in tickers:
                    lines.append(f'{ticker},Name,{"2024-01-01" if ticker == "NEW" else "2015-01-01"},2025-12-31')
                    if ticker != 'MISSING':
                        suffix = '_full_1min.txt' if cls == 'cryptos' else '_full_1min_adjsplitdiv.txt'
                        (root / cls / (ticker + suffix)).write_text('raw untouched\n', encoding='utf-8')
                (doc / universe.METADATA_FILES[cls]).write_text('\n'.join(lines), encoding='utf-8')
            inv, _ = universe.inventory(root, False)
            crypto = inv.loc[inv.asset_class.eq('cryptos')].set_index('asset')
            self.assertFalse(crypto.metadata_eligible.any())
            self.assertIn('quote_currency_unresolved', crypto.loc['BTC', 'exclusion_reasons'])
            self.assertIn('non_usd_crypto_cross_pair', crypto.loc['ETH-BTC', 'exclusion_reasons'])
            self.assertTrue(inv.loc[inv.asset.eq('MISSING'), 'exclusion_reasons'].str.contains('official_local_file_missing').all())


if __name__ == '__main__':
    unittest.main()
