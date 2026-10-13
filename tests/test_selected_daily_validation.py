import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from selected_daily_validation import reference_template, read_selected_rows, REFERENCE_COLUMNS
from daily_aggregation import aggregate_daily_ohlcv


class SelectedDailyValidationTests(unittest.TestCase):
    def test_template_blank_returns_and_specific_identity_notes(self):
        selected = pd.DataFrame([dict(asset=asset, asset_class='stocks', liquidity_tier='LOW',
            expected_bloomberg_security_identifier_placeholder=asset+' <EXCHANGE_CODE_PENDING> Equity')
            for asset in ['IMDX', 'BIDU', 'FCPT', 'AIRG']])
        template = reference_template(selected)
        self.assertEqual(list(template.columns), REFERENCE_COLUMNS)
        self.assertTrue(template[['NAME', 'ID_BB_GLOBAL', 'ID_ISIN', 'ID_CUSIP', 'TICKER_AND_EXCH_CODE', 'CRNCY']].isna().all().all())
        self.assertTrue(template.validation_status.eq('pending_not_extracted').all())
        notes = template.set_index('asset').validation_notes
        self.assertIn('OCX -> IMDX', notes.IMDX)
        self.assertIn('US ADS', notes.BIDU)
        self.assertIn('common REIT', notes.FCPT)

    def test_chunk_boundaries_unsorted_duplicates_zero_gaps_no_raw_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture.txt'
            path.write_text('\n'.join([
                '2024-03-11 09:32:00,10,12,9,11,0',
                '2024-03-11 09:30:00,10,12,9,11,2',
                '2024-03-11 16:00:00,10,12,9,11,3',
                '2024-03-11 09:30:00,10,12,9,11,4',
                'bad,10,12,9,11,5',
                '2026-01-01 09:30:00,10,12,9,11,6'])+'\n')
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            data, scan = read_selected_rows(path, 'stocks', Path(directory)/'issues.csv', chunk_size=2)
            daily = aggregate_daily_ohlcv(data, 'FIXTURE', 'stocks')
            self.assertEqual(len(daily), 1)
            row = daily.iloc[0]
            self.assertEqual(row.bars_observed, 3)
            self.assertEqual(row.zero_volume_rows, 1)
            self.assertEqual(row.duplicate_timestamp_rows, 2)
            self.assertEqual(row.max_gap_minutes, 2)
            self.assertFalse(row.aggregation_valid)
            self.assertEqual(scan['unassignable_timestamp_rows'], 1)
            self.assertEqual(scan['outside_primary_session_rows'], 1)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()
