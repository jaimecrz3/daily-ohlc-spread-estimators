from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bloomberg_io import sha256
from daily_input_convention import (ADJUSTMENTS, common_source_plan,
    enforce_common_source, verified_source_selection, corporate_action_boundaries,
    annotate_input_rows)


def rows():
    return pd.DataFrame(dict(asset=['TEST'] * 4, date=pd.to_datetime(
        ['2024-01-05', '2024-01-02', '2024-01-03', '2024-01-08']),
        source=['Bloomberg'] * 4, convention=['adjusted'] * 4,
        PX_OPEN=[10, 10, np.nan, 10], PX_HIGH=[11, 11, 11, 11],
        PX_LOW=[9, 9, 9, 9], PX_LAST=[10, 10, 10, 10],
        PX_OPEN_raw=['10', '10', '#N/A N/A', '10'], source_row=[4, 5, 6, 7]))


class DailyInputConventionTests(unittest.TestCase):
    def test_immutable_manifest_sources_and_tamper_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / '13-10-2026'
            folder.mkdir()
            records = []
            for convention in ('adjusted', 'unadjusted'):
                for suffix in ('raw.xlsx', 'raw_values.xlsx'):
                    path = folder / f'bloomberg_daily_{convention}_{suffix}'
                    path.write_bytes(b'fixture bytes; never parsed as workbook')
                    records.append(dict(file_name=path.relative_to(root).as_posix(),
                        sha256=sha256(path), size_bytes=path.stat().st_size))
            manifest = root / 'sha256_manifest.csv'
            pd.DataFrame(records).to_csv(manifest, index=False)
            before = {p: sha256(p) for p in root.rglob('*') if p.is_file()}
            self.assertEqual(verified_source_selection(root)['convention'], 'adjusted')
            self.assertEqual(verified_source_selection(root, 'robustness')['convention'], 'unadjusted')
            self.assertEqual(before, {p: sha256(p) for p in before})
            path.write_bytes(b'tampered fixture')
            with self.assertRaises(ValueError):
                verified_source_selection(root)

    def test_adjustment_labels_do_not_invent_abnormal_setting(self):
        self.assertEqual(ADJUSTMENTS['adjusted'], dict(CapChg='T',
            CshAdjNormal='T', CshAdjAbnormal='not_explicitly_set'))
        self.assertEqual(ADJUSTMENTS['unadjusted'], dict(CapChg='F',
            CshAdjNormal='F', CshAdjAbnormal='F'))
        self.assertIn('abnormal_setting_unspecified', annotate_input_rows(
            rows(), corporate_action_boundaries(pd.DataFrame())).input_adjustment_label.iloc[0])

    def test_common_source_enforced_for_all_estimators(self):
        self.assertEqual(enforce_common_source(common_source_plan()), 'adjusted')
        self.assertEqual(enforce_common_source(common_source_plan('robustness'), 'robustness'), 'unadjusted')
        with self.assertRaises(ValueError):
            enforce_common_source(dict(CS='adjusted', AR='unadjusted', EDGE='adjusted'))
        with self.assertRaises(ValueError):
            enforce_common_source(dict(CS='local', AR='local', EDGE='local'))

    def test_boundary_flags_deterministic_without_event_identity_inference(self):
        checks = pd.DataFrame([
            dict(asset='TEST', date='2024-01-04', check_type='adjustment_factor_change_candidate', evidence='saved factor screen'),
            dict(asset='TEST', date='2024-01-03', check_type='saved_notes_reverse_split_validation',
                check_passed=True, all_ohlc_scaling_checks_passed=True, evidence='saved reverse split 2024-01-05')])
        boundaries = corporate_action_boundaries(checks)
        pd.testing.assert_frame_equal(boundaries, corporate_action_boundaries(checks.iloc[::-1]))
        self.assertFalse(boundaries.verified_split.iloc[0])
        annotated = annotate_input_rows(rows(), boundaries)
        self.assertFalse(annotated.corporate_action_boundary_before.any())
        self.assertEqual(len(annotated), 4)
        unadjusted = rows().assign(convention='unadjusted')
        other = annotate_input_rows(unadjusted, boundaries, 'robustness')
        self.assertTrue(other.loc[other.date.eq('2024-01-05'), 'corporate_action_boundary_before'].item())
        self.assertEqual(int(boundaries.primary_break_cross_date_window.sum()), 0)
        self.assertEqual(int(boundaries.robustness_break_cross_date_window.sum()), 1)

    def test_heuristic_alone_never_breaks_either_convention(self):
        checks = pd.DataFrame([dict(asset='TEST', date='2024-01-04',
            check_type='adjustment_factor_change_candidate', evidence='heuristic only')])
        boundaries = corporate_action_boundaries(checks)
        self.assertTrue(boundaries.adjustment_factor_change_candidate.all())
        self.assertFalse(boundaries.verified_split.any())
        for role, convention in [('primary', 'adjusted'), ('robustness', 'unadjusted')]:
            result = annotate_input_rows(rows().assign(convention=convention), boundaries, role)
            self.assertFalse(result.corporate_action_boundary_before.any())

    def test_verified_robustness_event_on_missing_date_still_breaks_incoming_edge(self):
        checks = pd.DataFrame([dict(asset='TEST', date='2024-01-03',
            check_type='saved_notes_reverse_split_validation', check_passed=True,
            all_ohlc_scaling_checks_passed=True, evidence='saved reverse split 2024-01-04')])
        boundaries = corporate_action_boundaries(checks)
        result = annotate_input_rows(rows().assign(convention='unadjusted'), boundaries, 'robustness')
        self.assertTrue(result.loc[result.date.eq('2024-01-05'), 'corporate_action_boundary_before'].item())
        self.assertEqual(len(result), 4)

    def test_missing_partial_rows_source_only_dates_and_raw_tokens_preserved(self):
        data = rows()
        before = data.copy(deep=True)
        annotated = annotate_input_rows(data, corporate_action_boundaries(pd.DataFrame()))
        pd.testing.assert_frame_equal(data, before)
        self.assertEqual(set(data.date), set(annotated.date))
        self.assertEqual(len(data), len(annotated))
        partial = annotated.loc[annotated.date.eq('2024-01-03')].iloc[0]
        self.assertTrue(np.isnan(partial.PX_OPEN))
        self.assertEqual(partial.PX_OPEN_raw, '#N/A N/A')
        self.assertFalse(partial.common_ohlc_fields_available)
        self.assertTrue(partial.CS_required_fields_available)
        self.assertTrue(partial.AR_required_fields_available)
        self.assertFalse(partial.EDGE_required_fields_available)
        self.assertEqual(annotated.date.tolist(), sorted(data.date))

    def test_no_estimator_or_roll_result_dependency(self):
        data = rows()
        clean = annotate_input_rows(data, corporate_action_boundaries(pd.DataFrame()))
        contaminated = data.assign(roll_spread_bps=[0, 100, np.nan, -10],
            roll_defined=[True, False, False, True], CS=[1, 2, 3, 4], AR=[4, 3, 2, 1], EDGE=99)
        other = annotate_input_rows(contaminated, corporate_action_boundaries(pd.DataFrame()))
        pd.testing.assert_frame_equal(clean, other[clean.columns])

    def test_quote_or_volume_missingness_does_not_impute_or_gate_price_inputs(self):
        data = rows().assign(PX_VOLUME=np.nan, PX_BID=np.nan, PX_ASK=np.nan,
            daily_input_valid=False)
        annotated = annotate_input_rows(data, corporate_action_boundaries(pd.DataFrame()))
        self.assertEqual(annotated.common_ohlc_fields_available.sum(), 3)
        self.assertTrue(annotated.PX_VOLUME.isna().all())
        duplicate = pd.concat([data, data.iloc[[0]]], ignore_index=True)
        annotated = annotate_input_rows(duplicate, corporate_action_boundaries(pd.DataFrame()))
        self.assertFalse(annotated.loc[annotated.date.eq('2024-01-05'), 'common_ohlc_fields_available'].any())


if __name__ == '__main__':
    unittest.main()
