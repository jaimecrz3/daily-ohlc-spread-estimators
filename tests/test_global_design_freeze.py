from pathlib import Path
import json
import subprocess
import sys
import unittest

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import global_design_freeze as g
from bloomberg_io import sha256


def fixture(cls):
    names = g.assets(cls)
    local = pd.DataFrame([dict(asset=a, date=day, bars_observed=2)
        for a in names for day in ['2023-01-01', '2023-01-03', '2023-01-04', '2026-01-01']])
    bb = local[['asset', 'date']].copy()
    for field in g.OHLC: bb[field] = 10.
    return local, bb, names


class GlobalDesignTests(unittest.TestCase):
    def test_exact_stocks_source_intersection_no_synthetic_or_2026_dates(self):
        local, bb, names = fixture('stocks')
        local = local.loc[~(local.asset.eq(names[0]) & local.date.eq('2023-01-03'))]
        common, audit, summary, date_audit = g.source_calendar(local, bb, names)
        self.assertEqual(common, ['2023-01-01', '2023-01-04'])
        self.assertNotIn('2023-01-02', set(audit.date))
        self.assertEqual(summary.missing_local_session.sum(), 1)
        self.assertEqual(date_audit.loc[date_audit.date.eq('2023-01-03'), 'missing_local_assets'].iloc[0], names[0])

    def test_exact_etf_calendar_complete_finite_positive_common_ohlc(self):
        local, bb, names = fixture('etfs')
        bb.loc[bb.asset.eq(names[0]) & bb.date.eq('2023-01-01'), 'PX_OPEN'] = np.nan
        bb.loc[bb.asset.eq(names[1]) & bb.date.eq('2023-01-03'), 'PX_LOW'] = 0
        common, audit, summary, date_audit = g.source_calendar(local, bb, names)
        self.assertEqual(common, ['2023-01-04'])
        self.assertEqual(summary.incomplete_nonfinite_or_nonpositive_ohlc.sum(), 2)
        bb.loc[bb.date.eq('2023-01-04'), 'PX_HIGH'] = np.inf
        self.assertEqual(g.source_calendar(local, bb, names)[0], [])

    def test_missing_bloomberg_distinct_from_bad_ohlc(self):
        local, bb, names = fixture('stocks')
        bb = bb.loc[~(bb.asset.eq(names[0]) & bb.date.eq('2023-01-01'))]
        _, audit, _, _ = g.source_calendar(local, bb, names)
        row = audit.loc[audit.asset.eq(names[0]) & audit.date.eq('2023-01-01')].iloc[0]
        self.assertTrue(row.missing_bloomberg_row)
        self.assertFalse(row.incomplete_nonfinite_or_nonpositive_ohlc)

    def test_duplicate_sources_block_instead_of_silent_deduplication(self):
        local, bb, names = fixture('stocks')
        with self.assertRaises(ValueError):
            g.source_calendar(pd.concat([local, local.iloc[:1]]), bb, names)

    def test_source_calendar_independent_of_outcomes_and_quality_thresholds(self):
        local, bb, names = fixture('stocks')
        expected = g.source_calendar(local, bb, names)[0]
        local['roll_pairs'] = 0
        local['benchmark_defined'] = False
        local['aggregation_valid'] = False
        bb['cs_defined'] = False
        bb['edge_spread'] = -10000
        bb['estimator_error'] = 999999
        self.assertEqual(g.source_calendar(local, bb, names)[0], expected)

    def test_design_eligibility_independent_of_benchmark_and_estimator_outcomes(self):
        rows = pd.DataFrame(dict(asset=['IMDX']*4, date=['2023-01-01']*4,
            required_source_day_exists=[True]*4, benchmark_defined=[True, False, True, False],
            cs_defined=[False, True, True, False], roll_pairs=[0, 1, 2, 99999]))
        mask = g.design_eligibility(rows, ['IMDX'], ['2023-01-01'])
        self.assertTrue(mask.all())
        rows.loc[0, 'required_source_day_exists'] = False
        self.assertFalse(g.design_eligibility(rows, ['IMDX'], ['2023-01-01']).iloc[0])
        self.assertFalse(g.design_eligibility(rows, ['OTHER'], ['2023-01-01']).any())

    def test_accuracy_requires_design_and_all_four_method_flags(self):
        cols = ['design_eligible', 'benchmark_defined', 'cs_defined', 'ar_defined', 'edge_defined']
        rows = pd.DataFrame(True, index=range(6), columns=cols)
        for i, col in enumerate(cols): rows.loc[i, col] = False
        self.assertEqual(g.common_accuracy_mask(rows).tolist(), [False]*5 + [True])
        self.assertEqual(g.failure_rate_denominator(rows), 5)

    def test_no_benchmark_or_estimator_import_dependency(self):
        result = subprocess.run([sys.executable, '-B', '-c',
            "import sys;sys.path.insert(0,'src');import global_design_freeze;assert 'benchmark' not in sys.modules"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_saved_universes_and_primary_pair_policy(self):
        spec = yaml.safe_load((g.OUT / 'global_design_final_spec.yaml').read_text())
        self.assertEqual(spec['liquidity_tiers'], g.TIERS)
        selected = pd.read_csv(g.FINAL / 'selected_stocks_etfs.csv')
        for cls in ['stocks', 'etfs']:
            self.assertEqual(set(selected.loc[selected.asset_class.eq(cls), 'asset']), set(g.assets(cls)))
        self.assertEqual(spec['benchmark_formula']['minimum_covariance_pairs'], 2)
        self.assertEqual(spec['primary_roll_pair_threshold'], 2)
        self.assertFalse(spec['higher_primary_pair_threshold_allowed'])

    def test_saved_futures_calendar_unchanged(self):
        original = yaml.safe_load(g.SPEC_PATHS['futures'].read_text())
        saved = pd.read_csv(g.OUT / 'futures_primary_calendar.csv').date.tolist()
        self.assertEqual(saved, original['primary_common_trade_dates'])
        self.assertEqual(len(saved), 259)

    def test_saved_crypto_calendar_unchanged(self):
        original = pd.read_csv(g.FINAL / 'crypto_final/historical/exact_common_dates.csv').utc_date.tolist()
        saved = pd.read_csv(g.OUT / 'crypto_primary_calendar.csv').date.tolist()
        self.assertEqual(saved, original)
        self.assertEqual(len(saved), 1417)

    def test_saved_stock_etf_calendars_recomputed_from_original_artifacts(self):
        local = pd.read_csv(g.FINAL / 'local_daily_validation/selected_daily_ohlcv.csv')
        bb = pd.read_parquet(g.PROJECT / 'data/interim/bloomberg/daily_adjusted.parquet')
        for cls in ['stocks', 'etfs']:
            expected = g.source_calendar(local, bb, g.assets(cls))[0]
            self.assertEqual(pd.read_csv(g.OUT / f'{cls}_primary_calendar.csv').date.tolist(), expected)

    def test_every_primary_date_has_nine_assets_three_per_tier_and_no_outcomes(self):
        grid = pd.read_csv(g.OUT / 'design_eligible_asset_days.csv')
        self.assertTrue(grid.groupby(['asset_class', 'date']).asset.nunique().eq(9).all())
        self.assertTrue(grid.groupby(['asset_class', 'date', 'liquidity_tier']).asset.nunique().eq(3).all())
        self.assertTrue(grid.design_eligible.all())
        self.assertFalse(any('defined' in col or 'spread' in col for col in grid.columns))

    def test_fx_in_scope_blocked_not_substituted(self):
        spec = yaml.safe_load((g.OUT / 'global_design_final_spec.yaml').read_text())
        self.assertIn('fx', spec['asset_classes_in_scope'])
        self.assertEqual(spec['asset_class_status']['fx'], 'BLOCKED_OFFICIAL_SOURCE_ACCESS')
        self.assertFalse(spec['fx_policy']['substitute_fx_allowed'])
        self.assertEqual(spec['status'], 'FROZEN_FOR_ESTIMATOR_IMPLEMENTATION')

    def test_protected_docs_frozen_specs_and_inputs_unchanged(self):
        manifest = json.loads((g.OUT / 'run_manifest.json').read_text())
        # Step21 explicitly authorizes final documentation creation. Preserve the
        # historical protected set exactly; audit only the authorized new paths
        # through the separate Step21 receipt, without rewriting this old manifest.
        current = g.protected_hashes()
        self.assertEqual(manifest['protected_sha256'],
                         {name: current[name] for name in manifest['protected_sha256']})
        added = set(current) - set(manifest['protected_sha256'])
        if added:
            receipt = json.loads((g.PROJECT/'outputs/reproducibility/documentation_transition.json').read_text())
            self.assertEqual(added, set(receipt['authorized_document_paths']))
            for name in added:
                self.assertEqual(current[name], receipt['authorized_document_sha256'][name])
        for name, expected in manifest['input_sha256'].items():
            self.assertEqual(sha256(g.PROJECT / name), expected, name)
        for name, expected in manifest['output_sha256'].items():
            self.assertEqual(sha256(g.OUT / name), expected, name)


if __name__ == '__main__':
    unittest.main()
