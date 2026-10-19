from pathlib import Path
import importlib.util
import math
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from spread_estimators import cs_interval, cs_daily, ar_two_day, edge_moments

SOURCES = Path(__file__).resolve().parents[1] / 'outputs/diagnostics/estimator_freeze/sources'
EDGE_EXPECTED = {
    'edge_ohlc.csv': dict(spread=.0101849034905478, pt=.9820982098209821,
        po=1.227922792279228, pc=1.2052205220522052, e1=.00010702425689560482,
        e2=.000101595812797079, v1=2.074215642985551e-6, v2=1.3461279919743572e-6,
        s2=.00010373225911177194),
    'edge_ohlc_miss.csv': dict(spread=.01013284969780197, pt=.9822078447230085,
        po=1.2272254421162134, pc=1.205827632480371, e1=.00010337780767834583,
        e2=.00010219271972776808, v1=2.0045420261850617e-6, v2=1.373839551967266e-6,
        s2=.00010267464299824543)}


def sas_reference(h, l, c):
    """Independent scalar transcription of SAS pp2-3; no shared kernel helpers."""
    th, tl = h[1], l[1]
    if c < l[1]: th, tl = h[1] - (l[1] - c), c
    if c > h[1]: th, tl = c, l[1] + (c - h[1])
    b = math.log(th/tl)**2 + math.log(h[0]/l[0])**2
    g = math.log(max(th, h[0])/min(tl, l[0]))**2
    k = 3-2*math.sqrt(2)
    a = (math.sqrt(2*b)-math.sqrt(b))/k-math.sqrt(g/k)
    return b, g, a, 2*(math.exp(a)-1)/(1+math.exp(a))


def negative_edge_fixture():
    # Fixed synthetic seed=123 first draw; no provider observations.
    return [np.array(a) for a in [
        [.9707622993444374, .9890270473592606, 1.0393939031536654],
        [.9927756250006293, 1.0137191881041197, 1.0690337149649263],
        [.9535326600912647, .978455434207533, 1.0335334138831576],
        [.974535675058107, 1.0073982512753485, 1.0514601673091057]]]


class CorwinSchultzTests(unittest.TestCase):
    def test_hand_beta_gamma_alpha_and_raw_spread(self):
        h, l = np.exp([.1, .1]), np.exp([-.1, -.1])
        r = cs_interval(h, l, 1.)
        d = r['method_specific_diagnostics']
        self.assertAlmostEqual(d['beta'], .08)
        self.assertAlmostEqual(d['gamma'], .04)
        k = 3-2*math.sqrt(2)
        alpha = (.4-math.sqrt(.08))/k-math.sqrt(.04/k)
        expected = 2*(math.exp(alpha)-1)/(1+math.exp(alpha))
        self.assertAlmostEqual(d['alpha'], alpha)
        self.assertAlmostEqual(r['raw_signed_spread_relative'], expected)

    def test_sas_overnight_below_low(self):
        r = cs_interval([11, 15], [9, 12], 10)
        self.assertEqual(r['method_specific_diagnostics']['adjusted_high'], 13)
        self.assertEqual(r['method_specific_diagnostics']['adjusted_low'], 10)
        self.assertEqual(r['method_specific_diagnostics']['overnight_adjustment'], 'prior_close_below_low')

    def test_sas_overnight_above_high(self):
        r = cs_interval([11, 8], [9, 6], 10)
        self.assertEqual(r['method_specific_diagnostics']['adjusted_high'], 10)
        self.assertEqual(r['method_specific_diagnostics']['adjusted_low'], 8)

    def test_matches_independent_sas_equations(self):
        for h, l, c in [([11, 15], [9, 12], 10), ([11, 8], [9, 6], 10),
                         ([1.2, 1.4], [1., 1.19], 1.19), ([12, 12], [10, 10], 11)]:
            b, g, a, s = sas_reference(h, l, c)
            r = cs_interval(h, l, c); d = r['method_specific_diagnostics']
            for name, expected in [('beta', b), ('gamma', g), ('alpha', a)]:
                self.assertAlmostEqual(d[name], expected, places=13)
            self.assertAlmostEqual(r['raw_signed_spread_relative'], s, places=13)

    def test_negative_interval_is_defined_zero_not_failed(self):
        r = cs_interval([1.2, 1.4], [1., 1.19], 1.19)
        self.assertTrue(r['raw_negative'])
        self.assertTrue(r['estimator_defined'])
        self.assertEqual(r['primary_spread_relative'], 0)
        self.assertEqual(r['failure_reason'], '')

    def test_invalid_not_zero_and_zero_range_not_reset(self):
        for h, l, c, reason in [([11, 12], [9, 0], 10, 'non_positive_price'),
            ([11, np.nan], [9, 10], 10, 'missing_required_field'),
            ([11, np.inf], [9, 10], 10, 'non_finite_price'),
            ([11, 9], [9, 10], 10, 'invalid_ohlc_order'),
            ([11, 10], [9, 10], 10, 'zero_range_not_admissible')]:
            r = cs_interval(h, l, c)
            self.assertFalse(r['estimator_defined']); self.assertIsNone(r['raw_negative'])
            self.assertTrue(np.isnan(r['primary_spread_relative']))
            self.assertEqual(r['failure_reason'], reason)

    def test_centered_two_interval_mapping_floors_before_averaging(self):
        r = cs_daily([1.2, 1.4, 1.4], [1, 1.19, 1.19], [1.19, 1.3, np.nan])
        d = r['method_specific_diagnostics']; left, right = d['left'], d['right']
        self.assertEqual(d['negative_component_intervals'], 1)
        self.assertAlmostEqual(r['primary_spread_relative'],
            (left['primary_spread_relative']+right['primary_spread_relative'])/2)
        self.assertAlmostEqual(r['raw_signed_spread_relative'],
            (left['raw_signed_spread_relative']+right['raw_signed_spread_relative'])/2)
        self.assertNotAlmostEqual(r['primary_spread_relative'], max(r['raw_signed_spread_relative'], 0))

    def test_requires_both_intervals(self):
        r = cs_daily([1.2, 1.4, np.nan], [1, 1.19, 1.19], [1.19, 1.3, 1.3])
        self.assertFalse(r['estimator_defined'])

    def test_price_scale_invariance(self):
        original = cs_interval([11, 15], [9, 12], 10)
        for scale in [.001, 1000]:
            scaled = cs_interval(np.array([11, 15])*scale, np.array([9, 12])*scale, 10*scale)
            self.assertAlmostEqual(original['raw_signed_spread_relative'], scaled['raw_signed_spread_relative'], places=12)


class AbdiRanaldoTests(unittest.TestCase):
    def test_hand_eta_positive_moment_and_units(self):
        r = ar_two_day(np.exp([.2, .1]), np.exp([0, -.1]), np.exp(.15))
        np.testing.assert_allclose(r['method_specific_diagnostics']['eta'], [.1, 0], atol=1e-15)
        self.assertAlmostEqual(r['raw_moment'], .03)
        self.assertAlmostEqual(r['primary_spread_relative'], math.sqrt(.03))
        self.assertAlmostEqual(r['primary_spread_bps'], 10000*math.sqrt(.03))

    def test_negative_moment_signed_root_and_primary_zero(self):
        r = ar_two_day(np.exp([.2, .3]), np.exp([0, .1]), np.exp(.15))
        self.assertAlmostEqual(r['raw_moment'], -.01)
        self.assertAlmostEqual(r['raw_signed_spread_relative'], -.1)
        self.assertTrue(r['raw_negative']); self.assertTrue(r['estimator_defined'])
        self.assertEqual(r['primary_spread_relative'], 0.)

    def test_scale_invariance(self):
        h, l, c = np.exp([.2, .3]), np.exp([0, .1]), np.exp(.15)
        r = ar_two_day(h, l, c)
        s = ar_two_day(h*100, l*100, c*100)
        self.assertAlmostEqual(r['raw_moment'], s['raw_moment'], places=13)

    def test_no_carry_forward_and_invalid_prices_undefined(self):
        for low, reason in [([1, np.nan], 'missing_required_field'),
                            ([1, 0], 'non_positive_price'), ([1, 13], 'invalid_ohlc_order')]:
            r = ar_two_day([11, 12], low, 10)
            self.assertEqual(r['failure_reason'], reason)
            self.assertTrue(np.isnan(r['primary_spread_relative']))

    def test_zero_range_formula_admissible_no_cs_screen(self):
        r = ar_two_day([1, 1], [1, 1], 1)
        self.assertTrue(r['estimator_defined'])
        self.assertFalse(r['raw_negative'])
        self.assertEqual(r['primary_spread_relative'], 0)


class EdgeTests(unittest.TestCase):
    def test_official_complete_and_missing_fixtures_all_published_scalars(self):
        for name, expected in EDGE_EXPECTED.items():
            data = pd.read_csv(SOURCES / name)
            r = edge_moments(*data.to_numpy().T)
            self.assertTrue(r['estimator_defined'], r['failure_reason'])
            self.assertAlmostEqual(r['primary_spread_relative'], expected['spread'], places=14)
            for key, value in expected.items():
                if key != 'spread':
                    self.assertAlmostEqual(r['method_specific_diagnostics'][key], value, places=14)

    def test_independent_official_python_replication(self):
        spec = importlib.util.spec_from_file_location('official_edge', SOURCES / 'edge_official.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        for name in EDGE_EXPECTED:
            data = pd.read_csv(SOURCES / name).to_numpy().T
            expected = module.edge(*data, sign=True)
            actual = edge_moments(*data)
            self.assertAlmostEqual(actual['raw_signed_spread_relative'], expected, places=14)

    def test_missing_grid_not_compressed(self):
        frame = pd.read_csv(SOURCES / 'edge_ohlc_miss.csv')
        complete = edge_moments(*frame.to_numpy().T)
        compressed = edge_moments(*frame.dropna().to_numpy().T)
        self.assertNotAlmostEqual(complete['raw_moment'], compressed['raw_moment'], places=10)
        self.assertEqual(len(complete['method_specific_diagnostics']['tau']), len(frame)-1)
        self.assertFalse(complete['window_complete'])

    def test_minimum_observations(self):
        self.assertEqual(edge_moments(*([1, 2],)*4)['failure_reason'], 'insufficient_edge_observations')

    def test_insufficient_tau(self):
        self.assertEqual(edge_moments(*([1, 1, 1],)*4)['failure_reason'], 'insufficient_edge_tau')

    def test_po_zero(self):
        self.assertEqual(edge_moments(*([1, 2, 3],)*4)['failure_reason'], 'zero_edge_po')

    def test_pc_zero(self):
        self.assertEqual(edge_moments([1, 2, 3], [1, 2, 4], [1, 2, 2], [1, 2, 3])['failure_reason'], 'zero_edge_pc')

    def test_nonpositive_total_variance_fallback(self):
        r = edge_moments([1]*3, [1.2]*3, [.9]*3, [1.1]*3)
        d = r['method_specific_diagnostics']
        self.assertTrue(r['estimator_defined'])
        self.assertTrue(d['variance_fallback'])
        self.assertLessEqual(d['vt'], 0)
        self.assertEqual(r['raw_moment'], (d['e1']+d['e2'])/2)

    def test_negative_s2_signed_raw_paper_primary_zero_abs_robustness(self):
        r = edge_moments(*negative_edge_fixture())
        self.assertAlmostEqual(r['raw_moment'], -.00013244038137993656, places=15)
        self.assertTrue(r['raw_negative']); self.assertTrue(r['estimator_defined'])
        self.assertEqual(r['primary_spread_relative'], 0)
        self.assertLess(r['raw_signed_spread_relative'], 0)
        self.assertAlmostEqual(r['method_specific_diagnostics']['edge_abs_root_robustness'],
                               -r['raw_signed_spread_relative'])

    def test_all_intermediate_vectors_and_bps(self):
        r = edge_moments(*negative_edge_fixture()); d = r['method_specific_diagnostics']
        for key in ['m', 'r1', 'r2', 'r3', 'r4', 'r5', 'tau', 'po1', 'po2', 'pc1', 'pc2',
                    'pt', 'po', 'pc', 'd1', 'd3', 'd5', 'x1', 'x2', 'e1', 'e2', 'v1', 'v2', 's2']:
            self.assertIn(key, d)
        p = edge_moments([1]*3, [1.2]*3, [.9]*3, [1.1]*3)
        self.assertEqual(p['primary_spread_bps'], 10000*p['primary_spread_relative'])

    def test_scale_invariance(self):
        data = negative_edge_fixture()
        r = edge_moments(*data)
        s = edge_moments(*[a*10000 for a in data])
        self.assertAlmostEqual(r['raw_moment'], s['raw_moment'], places=13)

    def test_invalid_prices_and_order_never_repaired(self):
        for position, value, reason in [(0, -1, 'non_positive_price'), (0, np.inf, 'non_finite_price'),
                                        (1, .1, 'invalid_ohlc_order')]:
            data = negative_edge_fixture(); data[position][0] = value
            r = edge_moments(*data)
            self.assertFalse(r['estimator_defined']); self.assertEqual(r['failure_reason'], reason)

    def test_bad_shapes_raise_programming_error(self):
        with self.assertRaises(ValueError): edge_moments([1], [1, 2], [1], [1])


if __name__ == '__main__':
    unittest.main()
