from pathlib import Path
import sys
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from final_universe import eligible_ranking, select_tier_quantiles, bloomberg_plan, DAILY_FIELDS, REFERENCE_FIELDS


def full_ranking(n=17):
    rows = []
    for cls in ['stocks', 'etfs']:
        for tier in ['LOW', 'MEDIUM', 'HIGH']:
            for i in range(n):
                rows.append(dict(asset=f'{tier}_{i+1:02}', asset_class=cls, liquidity_tier=tier,
                    liquidity_measure_2024=float(i+1), expected_bloomberg_security_identifier_placeholder=f'{tier}_{i+1:02} <EXCHANGE_CODE_PENDING> Equity'))
    return pd.DataFrame(rows)


def eligibility_inputs():
    full = full_ranking().rename(columns={'liquidity_measure_2024': 'liquidity_measure'})
    full['file'] = full.asset_class + '/' + full.asset + '_full_1min_adjsplitdiv.txt'
    full['liquidity_rank'] = full.groupby('asset_class').cumcount() + 1
    full['observed_2024_days'] = 252
    full['median_bars_per_observed_day'] = 100
    full['zero_volume_rows'] = 0
    keys = full[['asset_class', 'asset']].copy()
    eligible = keys.assign(metadata_eligible=True, local_file_exists=True, in_computational_pool=True,
        raw_coverage_validation='verified_endpoint_span_and_2024_presence', provider_name='Unfamiliar provider name',
        provider_first_date='2014-01-01', provider_last_date='2025-12-31', reference_validation='pending', quote_currency='pending')
    candidates = keys.assign(passes_liquidity_days=True, ranking_eligible=True)
    scans = keys.assign(first_observed_study_date='2015-01-02', last_observed_study_date='2025-12-31', observed_study_years=11)
    excluded = pd.DataFrame(columns=['asset_class', 'asset'])
    return full, eligible, candidates, scans, excluded


class FinalUniverseTests(unittest.TestCase):
    def test_rank_positions_and_exact_three_per_tier(self):
        selected, audit = select_tier_quantiles(full_ranking(17))
        self.assertEqual(len(selected), 18)
        self.assertEqual(len(audit), 102)
        self.assertTrue(selected.groupby(['asset_class', 'liquidity_tier']).size().eq(3).all())
        self.assertEqual(selected.liquidity_rank_within_tier.tolist(), [5, 9, 13] * 6)
        self.assertEqual(selected.selection_quantile_target.tolist(), [.25, .5, .75] * 6)

    def test_half_rank_ties_alphabetical(self):
        full = full_ranking(19)
        # Nearest candidates to target 5.5 have ranks 5 and 6; Z vs A
        full.loc[full.asset.eq('LOW_05'), 'asset'] = 'ZZZ'
        full.loc[full.asset.eq('LOW_06'), 'asset'] = 'AAA'
        selected, _ = select_tier_quantiles(full)
        low_quarter = selected.loc[selected.liquidity_tier.eq('LOW') & selected.selection_quantile_target.eq(.25)]
        self.assertTrue(low_quarter.asset.eq('AAA').all())
        self.assertTrue(low_quarter.liquidity_rank_within_tier.eq(6).all())
        self.assertTrue(low_quarter.selection_rank_distance.eq(.5).all())

    def test_equal_liquidity_ticker_order_and_determinism(self):
        full = full_ranking()
        full['liquidity_measure_2024'] = 1
        first = select_tier_quantiles(full)
        second = select_tier_quantiles(full.sample(frac=1, random_state=42))
        for a, b in zip(first, second):
            pd.testing.assert_frame_equal(a, b)

    def test_no_interpolated_liquidity_values(self):
        full = full_ranking()
        full['liquidity_measure_2024'] = full.liquidity_measure_2024 ** 5
        selected, _ = select_tier_quantiles(full)
        self.assertEqual(selected.liquidity_measure_2024.tolist(), [5**5, 9**5, 13**5] * 6)

    def test_review_flags_names_and_benchmark_values_do_not_select(self):
        full = full_ranking()
        baseline = select_tier_quantiles(full)[0][['asset_class', 'asset']]
        altered = full.assign(provider_name='famous or unfamiliar name', security_type_review_required=True,
            bloomberg_identifier_validation_pending=True, coverage_unbalanced_2015_2025=True,
            roll_defined=False, roll_spread_bps=999, benchmark_failure_reason='failure', CS=99, AR=99, EDGE=99)
        selected = select_tier_quantiles(altered)[0][['asset_class', 'asset']]
        pd.testing.assert_frame_equal(baseline, selected)
        inputs = list(eligibility_inputs())
        inputs[0] = inputs[0].assign(roll_defined=False, roll_spread_bps=999, EDGE=99)
        result = eligible_ranking(*inputs)
        self.assertFalse({'roll_defined', 'roll_spread_bps', 'EDGE'} & set(result))

    def test_eligibility_gates_and_exclusions(self):
        for index, column, value in [(0, 'observed_2024_days', 199), (1, 'metadata_eligible', False),
                                      (1, 'local_file_exists', False), (2, 'ranking_eligible', False),
                                      (2, 'passes_liquidity_days', False)]:
            inputs = list(eligibility_inputs())
            inputs[index].loc[0, column] = value
            with self.assertRaises(ValueError):
                eligible_ranking(*inputs)
        inputs = list(eligibility_inputs())
        inputs[-1] = inputs[0].iloc[[0]][['asset_class', 'asset']]
        with self.assertRaises(ValueError):
            eligible_ranking(*inputs)

    def test_coverage_inside_2015_flagged_without_replacement(self):
        inputs = list(eligibility_inputs())
        inputs[3].loc[4, 'first_observed_study_date'] = '2015-11-10'
        result = eligible_ranking(*inputs)
        late = result.loc[result.asset_class.eq('stocks') & result.asset.eq('LOW_05')].iloc[0]
        self.assertTrue(late.coverage_unbalanced_2015_2025)
        selected, _ = select_tier_quantiles(result)
        self.assertIn('LOW_05', selected.loc[selected.asset_class.eq('stocks'), 'asset'].tolist())

    def test_class_asset_keys_not_ticker_only(self):
        inputs = list(eligibility_inputs())
        inputs[1].loc[inputs[1].asset_class.eq('etfs'), 'provider_name'] = 'ETF label'
        inputs[1].loc[inputs[1].asset_class.eq('stocks'), 'provider_name'] = 'Stock label'
        full = eligible_ranking(*inputs)
        self.assertTrue(full.loc[full.asset_class.eq('etfs'), 'provider_name'].eq('ETF label').all())
        self.assertTrue(full.loc[full.asset_class.eq('stocks'), 'provider_name'].eq('Stock label').all())

    def test_exact_field_plan_and_reference_snapshot_semantics(self):
        selected, _ = select_tier_quantiles(full_ranking())
        plan = bloomberg_plan(selected, set())
        self.assertEqual(len(plan), 234)
        self.assertEqual(plan.terminal_function.value_counts().to_dict(), {'BDH': 126, 'BDP': 108})
        self.assertEqual(set(plan.loc[plan.terminal_function.eq('BDH'), 'field']), set(DAILY_FIELDS))
        self.assertEqual(set(plan.loc[plan.terminal_function.eq('BDP'), 'field']), set(REFERENCE_FIELDS))
        self.assertTrue(plan.start.eq('2015-01-01').all() and plan.end.eq('2025-12-31').all())
        self.assertFalse(plan.loc[plan.terminal_function.eq('BDP'), 'date_range_applies_to_request'].any())
        self.assertTrue(plan.loc[plan.field.eq('ID_CUSIP'), 'applicability'].eq('where applicable').all())
        self.assertTrue(plan.expected_bloomberg_security_identifier_placeholder.str.contains('PENDING').all())

    def test_local_validation_availability_not_assumed(self):
        selected, _ = select_tier_quantiles(full_ranking())
        first = selected.iloc[0]
        plan = bloomberg_plan(selected, {(first.asset_class, first.asset)})
        ohlcv = plan.loc[plan.field.eq('PX_OPEN')]
        available = ohlcv.loc[ohlcv.asset_class.eq(first.asset_class) & ohlcv.asset.eq(first.asset)]
        self.assertTrue(available.local_validation_availability.str.contains('materialized').all())
        unavailable = ohlcv.loc[~(ohlcv.asset_class.eq(first.asset_class) & ohlcv.asset.eq(first.asset))]
        self.assertTrue(unavailable.local_validation_availability.str.contains('not yet materialized').all())
        self.assertTrue(ohlcv.local_source_role.eq('local_daily_validation').all())
        quotes = plan.loc[plan.field.isin(['PX_BID', 'PX_ASK'])]
        self.assertTrue(quotes.equivalent_local_field.eq('none').all())
        self.assertTrue(quotes.purpose.str.contains('not the intraday benchmark').all())


if __name__ == '__main__':
    unittest.main()
