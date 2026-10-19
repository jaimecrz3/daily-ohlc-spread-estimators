from pathlib import Path
import inspect
import json
import math
import subprocess
import sys
import unittest

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import statistical_freeze as s
from bloomberg_io import sha256


class StatisticalFreezeTests(unittest.TestCase):
    def specs(self):
        return s.make_specs(yaml.safe_load(s.GLOBAL.read_text(encoding='utf-8')),
                            yaml.safe_load(s.ESTIMATORS.read_text(encoding='utf-8')))

    def test_pooled_mean_equals_count_weighted_daily_intercept(self):
        # Predeclared synthetic errors only; not estimator-minus-benchmark values.
        data = pd.DataFrame(dict(date=['2024-01-01']*2+['2024-01-02'], error=[1., 3., -2.]))
        grouped = s.date_components(data)
        alpha_identity = np.average(grouped.daily_mean_error, weights=grouped.n_t)
        self.assertAlmostEqual(alpha_identity, s.point_summary(data.error)['bias'])
        self.assertAlmostEqual(alpha_identity, 2/3)
        self.assertNotAlmostEqual(alpha_identity, grouped.daily_mean_error.mean())

    def test_mae_definition(self):
        self.assertEqual(s.point_summary([1, 3, -2])['mae'], 2.)

    def test_rmse_definition(self):
        self.assertAlmostEqual(s.point_summary([1, 3, -2])['rmse'], math.sqrt(14/3))

    def test_no_silent_nan_dropping_or_weight_argument(self):
        for vector in [[], [1, np.nan], [np.inf], [[1, 2]]]:
            with self.assertRaises(ValueError): s.point_summary(vector)
        self.assertEqual(list(inspect.signature(s.point_summary).parameters), ['errors'])

    def test_primary_not_equal_asset_or_volume_weighting(self):
        w, _ = self.specs()
        self.assertEqual(w['primary_weighting'], 'ASSET_DAY_WEIGHTED')
        self.assertIn('equal-asset weighting', w['prohibited_primary_weights'])
        self.assertIn('turnover', w['prohibited_primary_weights'])
        self.assertIn('minute bar count', w['prohibited_primary_weights'])

    def test_deterministic_lag_formula(self):
        for T in [1, 2, 5, 10, 100, 1000, 10000]:
            self.assertEqual(s.hac_lag(T), min(math.floor(4*(T/100)**(2/9)), T-1))
        self.assertEqual(s.hac_lag(100), 4)

    def test_lag_only_accepts_date_count_not_results(self):
        self.assertEqual(list(inspect.signature(s.hac_lag).parameters), ['T'])
        for bad in [0, -1, 2.5, True, '100']:
            with self.assertRaises(ValueError): s.hac_lag(bad)
        _, hac = self.specs()
        self.assertFalse(hac['significance_based_lag_selection'])
        self.assertEqual(hac['hac_lag_inputs'], ['T'])

    def test_lag_never_exceeds_T_minus_one(self):
        for T in range(1, 1001):
            self.assertLessEqual(s.hac_lag(T), T-1)
            self.assertGreaterEqual(s.hac_lag(T), 0)
        self.assertEqual(s.hac_lag(1), 0)

    def test_hac_only_signed_bias_descriptive_mae_rmse(self):
        _, hac = self.specs()
        self.assertEqual(hac['hac_target'], 'SIGNED_ERROR_BIAS_ONLY')
        self.assertEqual(hac['no_inference_metrics'], ['MAE', 'RMSE'])
        self.assertEqual(hac['hac_kernel'], 'BARTLETT')
        self.assertEqual(hac['confidence_level'], .95)
        self.assertEqual(hac['p_value_sidedness'], 'TWO_SIDED')

    def test_failure_and_negative_denominators_unchanged(self):
        previous = yaml.safe_load(s.ESTIMATORS.read_text(encoding='utf-8'))
        for spec in self.specs():
            for field in ['failure_rate_denominator', 'negative_rate_denominator']:
                self.assertEqual(spec[field], previous[field])

    def test_imdx_retained_without_stitching_or_certification(self):
        global_spec = yaml.safe_load(s.GLOBAL.read_text(encoding='utf-8'))
        self.assertIn('IMDX', global_spec['selected_assets_by_class']['stocks'])
        self.assertNotIn('OCX', global_spec['selected_assets_by_class']['stocks'])
        for spec in self.specs():
            self.assertFalse(spec['imdx_identity_continuity_certified'])
            self.assertEqual(spec['imdx_identity_policy'], 'source_defined_history_retained_without_manual_stitching')

    def test_fx_in_scope_blocked_no_substitute(self):
        for spec in self.specs():
            self.assertEqual(spec['fx_status'], 'IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS')
            self.assertFalse(spec['substitute_fx_allowed'])

    def test_no_estimator_benchmark_or_inference_engine_dependency(self):
        result = subprocess.run([sys.executable, '-B', '-c',
            "import sys;sys.path.insert(0,'src');import statistical_freeze;"
            "assert not any(n in sys.modules for n in ['spread_estimators','benchmark','statsmodels'])"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for spec in self.specs():
            self.assertFalse(spec['provider_estimation_executed'])
            self.assertFalse(spec['hac_inference_executed'])

    def test_protected_docs_prior_specs_and_estimator_code_unchanged(self):
        s.verify_previous()
        manifest = json.loads((s.DIAG/'estimator_freeze/run_manifest.json').read_text(encoding='utf-8'))
        for name, expected in manifest['protected_sha256'].items():
            self.assertEqual(sha256(s.PROJECT/name), expected, name)
        for name, expected in manifest['code_sha256'].items():
            self.assertEqual(sha256(s.PROJECT/name), expected, name)


if __name__ == '__main__':
    unittest.main()
