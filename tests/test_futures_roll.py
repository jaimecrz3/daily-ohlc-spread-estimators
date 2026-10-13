import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from futures_roll import (parse_provider_calendar, contract_file, session_bounds,
                          selection_plan, validate_sessions, read_contract_window,
                          observed_roll_diagnostic)
from session_rules import assign_primary_session
from benchmark import build_roll_benchmark


def bars(times, code='Z24', root='ES'):
    data = pd.DataFrame({'timestamp': pd.to_datetime(times), 'close': [100.] * len(times), 'volume': [0.] * len(times)})
    result = assign_primary_session(data, 'futures', futures_root=root)
    result['source_contract'] = code
    return result


class FuturesRollTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def calendar(self, text):
        path = self.folder / 'calendar.txt'
        path.write_text(text, encoding='utf-8')
        return parse_provider_calendar(path)

    def test_calendar_quarterly_and_monthly(self):
        for codes in [('M24', 'U24', 'Z24', 'H25'), ('K24', 'M24', 'N24', 'Q24')]:
            calendar = self.calendar(''.join(f'2024-0{i+3}-14,{code}\n' for i, code in enumerate(codes)))
            self.assertEqual(calendar.selected_contract.tolist(), list(codes))
            self.assertEqual(calendar.provider_transition_flag.tolist(), [False, True, True, True])

    def test_invalid_calendar_rejected(self):
        for text in ['2024-01-01,H24\n2024-01-01,M24\n', '2024-01-02,H24\n2024-01-01,H24\n', '2024-01-01,continuous\n']:
            with self.assertRaises(ValueError):
                self.calendar(text)

    def test_exact_lookup_no_forward_fill(self):
        plan = selection_plan(self.calendar('2024-09-15,Z24\n2024-09-17,Z24\n'), 'ES', '2024-09-15', '2024-09-17', self.folder)
        self.assertTrue(pd.isna(plan.iloc[1].selected_contract))

    def test_resolution_unadjusted_only(self):
        self.assertEqual(contract_file(self.folder, 'ES', 'Z24').name, 'ES_Z24_1min.txt')
        for code in ['continuous', 'Z24_adjsplitdiv', '../Z24']:
            with self.assertRaises(ValueError):
                contract_file(self.folder, 'ES', code)

    def test_sunday_evening_and_daytime_one_date(self):
        data = bars(['2024-09-15 18:00', '2024-09-16 00:00', '2024-09-16 16:59', '2024-09-16 17:00', '2024-09-16 17:59', '2024-09-16 18:00'])
        self.assertEqual(data.trade_date.iloc[:3].tolist(), [pd.Timestamp('2024-09-16').date()] * 3)
        self.assertEqual(data.primary_session_retained.tolist(), [True, True, True, False, False, True])
        self.assertEqual(data.maintenance_interval.sum(), 2)
        self.assertEqual(data.trade_date.iloc[-1], pd.Timestamp('2024-09-17').date())

    def test_dst_aware_boundaries_and_ambiguity_flags(self):
        for date, hours in [('2024-03-10', 22), ('2024-11-03', 24), ('2024-11-04', 23)]:
            start, end = session_bounds(date)
            self.assertEqual((end-start).total_seconds()/3600, hours)
        data = bars(['2024-03-08 18:00', '2024-03-10 18:00', '2024-11-03 01:30', '2024-03-10 02:30'])
        self.assertEqual(data.timestamp_local.iloc[0].utcoffset().total_seconds(), -18000)
        self.assertEqual(data.timestamp_local.iloc[1].utcoffset().total_seconds(), -14400)
        self.assertEqual(data.timezone_assignment_failed.sum(), 2)
        self.assertFalse(data.primary_session_retained.iloc[2:].any())

    def test_contract_selection_and_observed_roll_separate_transition(self):
        calendar = self.calendar('2024-09-13,U24\n2024-09-15,Z24\n2024-09-16,Z24\n')
        for code in ['U24', 'Z24']:
            contract_file(self.folder, 'ES', code).touch()
        plan = selection_plan(calendar, 'ES', '2024-09-13', '2024-09-16', self.folder)
        inputs = {'U24': bars(['2024-09-13 09:30', '2024-09-16 09:30'], 'U24'),
                  'Z24': bars(['2024-09-15 18:00', '2024-09-16 09:30'])}
        original = inputs['Z24'].copy(deep=True)
        sessions, selected = validate_sessions(plan, inputs)
        monday = sessions.iloc[-1]
        self.assertTrue(monday.roll_day)
        self.assertEqual(monday.previous_contract, 'U24')
        self.assertFalse(monday.provider_transition_flag)
        self.assertEqual(monday.provider_transition_date, pd.Timestamp('2024-09-15').date())
        self.assertEqual(monday.bars_observed, 2)
        self.assertEqual(monday.previous_evening_rows, 1)
        self.assertEqual(selected.groupby('trade_date').selected_contract.nunique().max(), 1)
        pd.testing.assert_frame_equal(inputs['Z24'], original)

    def test_missing_file_and_empty_session_no_substitution(self):
        calendar = self.calendar('2024-09-16,Z24\n')
        plan = selection_plan(calendar, 'ES', '2024-09-16', '2024-09-16', self.folder)
        sessions, selected = validate_sessions(plan, {'U24': bars(['2024-09-16 09:30'], 'U24')})
        self.assertEqual(sessions.iloc[0].validation_reason, 'missing_individual_contract_file')
        self.assertTrue(selected.empty)
        contract_file(self.folder, 'ES', 'Z24').touch()
        plan = selection_plan(calendar, 'ES', '2024-09-16', '2024-09-16', self.folder)
        sessions, _ = validate_sessions(plan, {})
        self.assertEqual(sessions.iloc[0].validation_reason, 'selected_contract_has_no_session_observations')

    def test_benchmark_boundaries_gaps_and_contract_guard(self):
        data = bars(['2024-11-04 16:58', '2024-11-04 16:59', '2024-11-04 18:00', '2024-11-04 18:02'])
        data['selected_contract'] = 'Z24'
        daily = build_roll_benchmark(data, 'ES', 'futures', futures_root='ES')
        self.assertEqual(daily.bars_observed.tolist(), [2, 2])
        self.assertEqual(daily.one_minute_returns.tolist(), [1, 0])
        self.assertEqual(daily.roll_pairs.tolist(), [0, 0])
        data.loc[3, 'selected_contract'] = 'H25'
        with self.assertRaises(ValueError):
            build_roll_benchmark(data, 'ES', 'futures', futures_root='ES')

    def test_readonly_no_insertions_zero_flags(self):
        path = contract_file(self.folder, 'CL', 'Z24')
        path.write_text('2024-11-03 18:00:00,10,11,9,10,0\n2024-11-03 18:02:00,10,11,9,10,1\n', encoding='utf-8')
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        data, _ = read_contract_window(path, 'CL', 'Z24', '2024-11-04', '2024-11-04', self.folder)
        self.assertEqual(len(data), 2)
        self.assertEqual(data.zero_volume.sum(), 1)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_zero_observation_dates_audit_only(self):
        calendar = self.calendar('2024-11-04,Z24\n2024-11-05,Z24\n')
        contract_file(self.folder, 'ES', 'Z24').touch()
        plan = selection_plan(calendar, 'ES', '2024-11-04', '2024-11-06', self.folder)
        sessions, selected = validate_sessions(plan, {'Z24': bars(['2024-11-04 18:00'])})
        self.assertEqual(sessions.validation_status.tolist(), ['no_session_observations', 'ok', 'no_session_observations'])
        daily, _ = observed_roll_diagnostic(selected, sessions, 'ES')
        self.assertEqual(daily.date.tolist(), [pd.Timestamp('2024-11-05').date()])
        self.assertEqual(daily.bars_observed.tolist(), [1])
        self.assertEqual(daily.benchmark_failure_reason.tolist(), ['insufficient_roll_pairs'])
        sessions, selected = validate_sessions(plan, {})
        daily, _ = observed_roll_diagnostic(selected, sessions, 'ES')
        self.assertTrue(daily.empty)
        self.assertTrue(sessions.validation_status.eq('no_session_observations').all())

    def test_missing_file_cannot_be_bypassed_by_supplied_bars(self):
        plan = selection_plan(self.calendar('2024-11-04,Z24\n'), 'ES', '2024-11-04', '2024-11-04', self.folder)
        sessions, selected = validate_sessions(plan, {'Z24': bars(['2024-11-04 09:30'])})
        self.assertEqual(sessions.iloc[0].bars_observed, 0)
        self.assertEqual(sessions.iloc[0].validation_status, 'no_session_observations')
        self.assertEqual(sessions.iloc[0].validation_reason, 'missing_individual_contract_file')
        self.assertTrue(selected.empty)


if __name__ == '__main__':
    unittest.main()
