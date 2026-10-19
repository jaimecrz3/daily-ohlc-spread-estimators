"""Step15 offline source/fixture review and estimator freeze. No provider panels.

Reads specifications, hashes, docs, author-simulated fixtures and synthetic prices
only. Run with --run-tests to run the full suite before writing final artifacts.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import sys

import numpy as np
import pandas as pd
import yaml

from bloomberg_io import sha256, verify_hashes, require_verified
from global_design_freeze import protected_hashes
from spread_estimators import FAILURE_REASONS, cs_interval, cs_daily, ar_two_day, edge_moments
from estimator_windows import daily_estimate

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / 'outputs/diagnostics/estimator_freeze'
SOURCES = OUT / 'sources'
DESIGN = PROJECT / 'outputs/diagnostics/design_freeze'
EDGE_EXPECTED = {
    'edge_ohlc.csv': dict(spread=.0101849034905478, pt=.9820982098209821,
        po=1.227922792279228, pc=1.2052205220522052, e1=.00010702425689560482,
        e2=.000101595812797079, v1=2.074215642985551e-6, v2=1.3461279919743572e-6,
        s2=.00010373225911177194),
    'edge_ohlc_miss.csv': dict(spread=.01013284969780197, pt=.9822078447230085,
        po=1.2272254421162134, pc=1.205827632480371, e1=.00010337780767834583,
        e2=.00010219271972776808, v1=2.0045420261850617e-6, v2=1.373839551967266e-6,
        s2=.00010267464299824543)}


def scalar_record(estimator, fixture, quantity, expected, actual, authority):
    return dict(estimator=estimator, fixture=fixture, quantity=quantity,
        expected=float(expected), actual=float(actual), absolute_difference=float(abs(expected-actual)),
        passed=bool(np.isclose(expected, actual, rtol=1e-11, atol=1e-14)), authority=authority)


def synthetic_validation():
    records = []
    h, l = np.exp([.1, .1]), np.exp([-.1, -.1])
    r = cs_interval(h, l, 1); d = r['method_specific_diagnostics']
    k = 3-2*math.sqrt(2)
    alpha = (.4-math.sqrt(.08))/k-math.sqrt(.04/k)
    for key, expected in [('beta', .08), ('gamma', .04), ('alpha', alpha)]:
        records.append(scalar_record('CS', 'hand_log_ranges', key, expected, d[key], 'Hand calculation; official SAS equations'))
    s = 2*(math.exp(alpha)-1)/(1+math.exp(alpha))
    records.append(scalar_record('CS', 'hand_log_ranges', 'raw_spread', s, r['raw_signed_spread_relative'], 'Hand calculation'))
    for label, highs, lows, expected in [('positive', [.2, .1], [0, -.1], .03),
                                        ('negative', [.2, .3], [0, .1], -.01)]:
        r = ar_two_day(np.exp(highs), np.exp(lows), math.exp(.15))
        records.append(scalar_record('AR', 'hand_eta_'+label, 's2', expected, r['raw_moment'], 'Equation (9), independently hand-calculated log-price fixture'))
        records.append(scalar_record('AR', 'hand_eta_'+label, 'primary', math.sqrt(max(expected, 0)), r['primary_spread_relative'], 'Equation (11) two-day correction'))
    r = edge_moments([1]*3, [1.2]*3, [.9]*3, [1.1]*3)
    records.append(scalar_record('EDGE', 'constant_ohlc_variance_fallback', 's2', 0, r['raw_moment'], 'Independent constant-return zero-moment fixture'))
    # Fixed author-independent synthetic seed 123, first three-session draw.
    rng = np.random.default_rng(123)
    op = np.exp(rng.normal(0, .03, 3)); cl = op*np.exp(rng.normal(0, .02, 3))
    hi = np.maximum(op, cl)*np.exp(rng.uniform(.001, .02, 3))
    lo = np.minimum(op, cl)*np.exp(-rng.uniform(.001, .02, 3))
    r = edge_moments(op, hi, lo, cl)
    assert r['raw_negative'] and r['estimator_defined']
    records.append(scalar_record('EDGE', 'negative_synthetic_seed123', 'primary_zero_floor', 0, r['primary_spread_relative'], 'Published JFE Eq.(26)'))
    return pd.DataFrame(records)


def official_validation():
    records = []
    source = importlib.util.spec_from_file_location('pinned_official_edge', SOURCES / 'edge_official.py')
    module = importlib.util.module_from_spec(source); source.loader.exec_module(module)
    for name, expected in EDGE_EXPECTED.items():
        arrays = pd.read_csv(SOURCES / name).to_numpy().T
        r = edge_moments(*arrays); d = r['method_specific_diagnostics']
        for key, value in expected.items():
            actual = r['raw_signed_spread_relative'] if key == 'spread' else d[key]
            records.append(scalar_record('EDGE', name, key, value, actual, 'Official pseudocode published fixture table'))
        records.append(scalar_record('EDGE', name, 'official_python_abs_root',
            module.edge(*arrays), d['edge_abs_root_robustness'], 'Pinned official Python implementation; absolute-root replication, not primary convention'))
    # Independent scalar SAS equation oracle, never a provider observation or SAS execution.
    for i, (h, l, c) in enumerate([([11, 15], [9, 12], 10), ([11, 8], [9, 6], 10),
                                  ([1.2, 1.4], [1., 1.19], 1.19), ([12, 12], [10, 10], 11)]):
        th, tl = h[1], l[1]
        if c < l[1]: th, tl = h[1]-(l[1]-c), c
        if c > h[1]: th, tl = c, l[1]+(c-h[1])
        beta = math.log(th/tl)**2 + math.log(h[0]/l[0])**2
        gamma = math.log(max(th, h[0])/min(tl, l[0]))**2
        k = 3-2*math.sqrt(2)
        alpha = (math.sqrt(2*beta)-math.sqrt(beta))/k-math.sqrt(gamma/k)
        spread = 2*(math.exp(alpha)-1)/(1+math.exp(alpha))
        r = cs_interval(h, l, c); d = r['method_specific_diagnostics']
        for key, value in [('beta', beta), ('gamma', gamma), ('alpha', alpha)]:
            records.append(scalar_record('CS', 'sas_equation_oracle_'+str(i), key, value, d[key], 'Independent literal SAS pp2-3 scalar transcription; not SAS runtime execution'))
        records.append(scalar_record('CS', 'sas_equation_oracle_'+str(i), 'raw_spread', spread, r['raw_signed_spread_relative'], 'Official SAS equations; independent scalar oracle'))
    return pd.DataFrame(records)


def snapshot():
    result = protected_hashes()
    result.update({p.relative_to(PROJECT).as_posix(): sha256(p) for p in DESIGN.iterdir() if p.is_file()})
    for name in ['project_1.md', 'project_1_details.md']:
        path = PROJECT / 'docs' / name
        if not path.is_file(): raise ValueError('Required project document unavailable: '+str(path))
        result[path.relative_to(PROJECT).as_posix()] = sha256(path)
    return result


def formula_spec(source_manifest, tests_passed):
    return dict(status='FROZEN_FOR_PROVIDER_ESTIMATION' if tests_passed else 'FORMULA_VALIDATED_PENDING_FULL_SUITE', step=15,
        approval_date='2026-10-16', global_design_reference='outputs/diagnostics/design_freeze/global_design_final_spec.yaml',
        scope='Mathematical kernels and explicit ex-post daily mappings only; no provider estimation or performance comparisons executed',
        cs_formula={'constant': 'k=3-2*sqrt(2)', 'beta': 'log(H_b_adj/L_b_adj)^2 + log(H_a/L_a)^2 (SUM, not average)',
            'gamma': 'log(max(H_b_adj,H_a)/min(L_b_adj,L_a))^2',
            'alpha': '(sqrt(2*beta)-sqrt(beta))/k - sqrt(gamma/k)',
            'raw_interval': '2*(exp(alpha)-1)/(1+exp(alpha)) = 2*tanh(alpha/2)',
            'stable_evaluation': 'Differences of logs and tanh identity, no price clipping or numerical-tolerance zeroing',
            'admissibility': 'Finite positive H/L and prior close; H>L on each session, prior close within its own H/L; no empirical H/L>8 exclusion'},
        cs_overnight_policy={'prior_close_below_current_low': 'H_b_adj=H_b-(L_b-C_a); L_b_adj=C_a',
            'prior_close_above_current_high': 'H_b_adj=C_a; L_b_adj=L_b+(C_a-H_b)',
            'otherwise': 'Current H/L unchanged', 'previous_range': 'Use raw H_a/L_a, not its prior overnight-adjusted range',
            'preprocessing_exception': 'Do not copy official CRSP range resets, price carry-forward, absolute-close conversion or empirical ratio filter: frozen common policy forbids repair/imputation and adds no such screen'},
        cs_daily_mapping={'window': ['t-1', 't', 't+1'], 'choice': 'PROJECT mapping supported by author stock-split event-study example, not part of closed-form derivation',
            'primary': 'mean(max(S_(t-1,t),0), max(S_(t,t+1),0)); BOTH intervals required',
            'raw_daily': 'mean(S_(t-1,t), S_(t,t+1))', 'raw_negative': 'raw_daily < 0',
            'raw_moment': 'Mean component alpha, diagnostic only; daily raw spread is mean of nonlinear interval spreads',
            'diagnostics': ['left/right beta, gamma, alpha, raw and corrected spreads', 'negative component interval count', 'overnight direction and adjusted ranges'],
            'required_fields': 'H/L at t-1,t,t+1; C at t-1,t. Future close and all opens unused'},
        cs_negative_policy='Floor each finite raw interval at zero BEFORE daily averaging; negative raw daily flag retained independently; undefined never zero',
        ar_formula={'eta': '(log(H)+log(L))/2', 's2': '4*(log(C_t)-eta_t)*(log(C_t)-eta_(t+1))',
            'signed_raw': 'sign(s2)*sqrt(abs(s2))', 'source': 'Abdi--Ranaldo Eq.(9) and two-day correction Eq.(11)'},
        ar_daily_mapping={'target': 'close-t effective spread', 'window': ['t', 't+1'],
            'required_fields': 'H/L at t,t+1 and C_t only; C_(t+1) and opens unused', 'overnight_adjustment': 'none'},
        ar_negative_policy='sqrt(max(s2,0)); raw_negative iff s2<0; valid negative is defined zero',
        ar_imputation_policy='No carry-forward or high/low/range replacement. This differs from author empirical zero-range/nontrading preprocessing; theoretical finite zero-range moment remains admissible. Author preprocessing is later robustness only.',
        edge_formula_reference={'paper': 'JFE 161 (2024) 103916; Section3 and Eq.(26)',
            'repository': 'https://github.com/eguidotti/bidask', 'pinned_revision': source_manifest['github_revision'],
            'pseudocode': 'sources/edge_pseudocode.md', 'intermediates': ['log O/H/L/C', 'm', 'r1', 'r2', 'r3', 'r4', 'r5', 'tau', 'po1', 'po2', 'pc1', 'pc2', 'pt', 'po', 'pc', 'd1', 'd3', 'd5', 'x1', 'x2', 'e1', 'e2', 'v1', 'v2', 's2'],
            'variances': 'nanmean(x_i^2)-nanmean(x_i)^2; population moment variances, not ddof=1',
            's2': '(v2*e1+v1*e2)/(v1+v2) if v1+v2>0 else (e1+e2)/2',
            'admissibility': 'Grid length>=3; nansum(tau)>=2; po!=0; pc!=0; required scalar intermediates and final estimate finite'},
        edge_window={'primary': ['t-1', 't', 't+1'], 'length': 3,
            'choice': 'PROJECT centered shortest admissible sample, not author recommendation; ex-post measurement, not forecasting',
            'interpretation': 'RMS spread over local three-session sample, assigned to center day; temporal estimand differs from an instantaneous day-t spread',
            'longer_windows': 'Future separately labeled robustness only; not executed'},
        edge_negative_primary_policy='sqrt(max(edge_s2_raw,0)); published paper Eq.(26); raw_negative iff edge_s2_raw<0',
        edge_abs_robustness_policy='Named edge_abs_root_robustness=sqrt(abs(edge_s2_raw)); fixture diagnostics only, never primary',
        edge_missing_grid_policy='Keep NaNs in place; official nanmeans, no dropna compression. General kernel reproduces the long missing fixture. Primary centered three-session mapping requires its three source rows and required OHLC fields; missing rows/fields fail explicitly, never filled.',
        scheduled_adjacency_policy={'stocks_etfs': 'Step14 source_calendar_date_audit.csv class-specific PRE-intersection union of observed source periods, not successful/common rows; weekends/market non-sessions absent from that reference are not missing sessions',
            'futures': 'Frozen 259 provider-mapped 2024 trade dates; no bridging unavailable rows or contract fallback',
            'crypto': 'Every UTC calendar day in study horizon; any missing source day breaks required neighboring windows',
            'grid_boundaries': 'No inferred neighbors beyond verified grid; missing_previous/next_scheduled_period failure',
            'context': 'Use verified source context outside primary evaluation calendar for required lags/leads when available; evaluation endpoints remain Step14 dates',
            'limitation': 'Stock/ETF union reference cannot certify a wholly missing market-wide session absent from every existing source; no external holiday calendar invented',
            'metadata_integrity': 'Verify Step14 reference artifact hashes before loading; no provider price reads in loaders'},
        relative_spread_unit='Decimal dimensionless relative spread; 0.01 = 1 percent', bps_conversion='10000*primary_spread_relative; 0.01=100bps',
        failure_rate_denominator='ALL design_eligible asset-days; Step14 unchanged',
        negative_rate_denominator='For each estimator separately: design_eligible AND finite computable RAW mathematical estimate; report denominator count. Numerator additionally raw_negative=True. Undefined is not negative.',
        raw_negative_definitions={'CS': 'mean raw interval spreads < 0', 'AR': 'raw s2 < 0', 'EDGE': 'raw s2 < 0'},
        common_accuracy_sample='Step14 unchanged: design_eligible AND benchmark_defined AND cs_defined AND ar_defined AND edge_defined',
        failure_reasons=list(FAILURE_REASONS),
        result_schema=['asset', 'target_date', 'estimator', 'raw_moment', 'raw_signed_spread_relative', 'raw_negative',
            'raw_computable', 'primary_spread_relative', 'primary_spread_bps', 'estimator_defined', 'failure_reason',
            'input_dates', 'input_observations', 'window_complete', 'scheduled_adjacency_valid', 'method_specific_diagnostics'],
        result_semantics={'raw_negative_when_undefined': None, 'failure_reason_when_defined': '',
            'window_complete': 'All required source rows and method-specific finite fields present; positivity/order are separate admissibility checks',
            'input_observations': 'Number of present physical source-day rows; not inserted analysis-view placeholders',
            'structural_programming_errors': 'Unknown method/class, mismatched arrays, duplicate/invalid dates, ambiguous aliases or nonnumeric unnormalized tokens raise ValueError rather than silently estimating'},
        remaining_statistical_decisions=['HAC lag and dependence/aggregation convention', 'Overall/group summary weighting; no result optimization'],
        no_provider_panel_estimation_executed=True, no_benchmark_errors_or_performance_calculated=True)


def run(run_tests=False):
    before = snapshot()
    baseline = json.loads((DESIGN / 'run_manifest.json').read_text(encoding='utf-8'))
    assert all(sha256(DESIGN/name) == digest for name, digest in baseline['output_sha256'].items())
    source_manifest = json.loads((SOURCES / 'source_manifest.json').read_text(encoding='utf-8'))
    for name, record in source_manifest['files'].items():
        assert sha256(SOURCES/name) == record['sha256'], 'Methodology source changed: '+name
    raw, _ = verify_hashes(PROJECT / 'data/raw_bloomberg'); require_verified(raw)
    synthetic, official = synthetic_validation(), official_validation()
    assert synthetic.passed.all() and official.passed.all(), 'Formula replication failed'
    tests = dict(passed=0, failed=0, status='NOT_RUN_BY_THIS_REVIEW')
    if run_tests:
        completed = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests'],
                                   cwd=PROJECT, capture_output=True, text=True)
        output = completed.stdout + completed.stderr
        (OUT / 'test_results.txt').write_text(output, encoding='utf-8')
        print(output, flush=True)
        match = re.search(r'Ran (\d+) tests?', output)
        if completed.returncode != 0 or match is None:
            raise RuntimeError('Full test suite failed: final estimator specification not approved')
        tests = dict(passed=int(match.group(1)), failed=0, status='PASSED')
    spec = formula_spec(source_manifest, tests['status'] == 'PASSED')
    synthetic.to_csv(OUT/'synthetic_formula_validation.csv', index=False)
    official.to_csv(OUT/'official_replication_validation.csv', index=False)
    (OUT/'estimator_formula_spec.yaml').write_text(yaml.safe_dump(spec, sort_keys=False), encoding='utf-8')
    methods = pd.DataFrame([
        dict(estimator='CS', mathematical_source='Corwin-Schultz (2012), Eq14/18; author SAS pp2-3',
            source_url='https://sites.nd.edu/scorwin/research/', mapping='Project mean of BOTH corrected overlapping intervals (t-1,t),(t,t+1)',
            primary_negative_policy='max(raw_interval,0) before daily mean', raw_negative='raw_daily<0', preprocessing_difference='No CRSP range reset/carry-forward/absolute-close or H/L>8 empirical screen'),
        dict(estimator='AR', mathematical_source='Abdi-Ranaldo (2017), Eq9 and Eq11',
            source_url='https://academic.oup.com/rfs/article/30/12/4437/4047344', mapping='Two-day close-t moment on (t,t+1)',
            primary_negative_policy='sqrt(max(s2,0))', raw_negative='s2<0', preprocessing_difference='No empirical carry-forward; theoretical zero-range formula retained'),
        dict(estimator='EDGE', mathematical_source='Published JFE (2024) Section3, Eq26; author official pseudocode',
            source_url='https://doi.org/10.1016/j.jfineco.2024.103916', mapping='Project centered three-session RMS (t-1,t,t+1), assigned to t',
            primary_negative_policy='sqrt(max(s2,0)); absolute root robustness only', raw_negative='s2<0', preprocessing_difference='Official NaN-aware regular grid; project daily minimum requires three complete required-field source rows')])
    methods.to_csv(OUT/'estimator_method_review.csv', index=False)
    alignment = ('# Daily estimator alignment\n\nCS: **project** daily mapping is the mean of two separately zero-floored raw interval spreads on (t-1,t) and (t,t+1). Both are required. Author event-study evidence supports overlapping intervals; its special one-sided split-boundary exceptions are not used in this constant-horizon primary mapping. This is not an additional closed-form CS equation.\n\n'
        'AR: the close-t two-day moment uses C_t, eta_t and eta_(t+1), assigned to t. C_(t+1) is not needed. No overnight adjustment or imputation.\n\n'
        'EDGE: **project** centered minimum three-session sample (t-1,t,t+1), assigned to t; not an author window recommendation. It estimates an RMS spread over that sample, not exactly an instantaneous target-day spread. Ex-post measurement uses future session context and is not a forecasting signal. Longer windows remain unexecuted robustness candidates.\n\n'
        'Stock/ETF scheduled periods come from the verified Step14 PRE-intersection source-date audit, not the class common calendar or successful observations. Futures use the frozen provider-mapped 2024 dates. Crypto expects every UTC calendar day. Full source context may supply neighbors outside an evaluation calendar, but scoring stays on frozen primary dates. Missing expected source rows break required windows; weekends/non-session dates absent from the verified equity grid do not. Unknown neighbors at reference-grid endpoints fail. No cross-asset or compressed-date lags.\n\n'
        'Missing source rows are retained as NaN analysis-view placeholders only; no OHLC is invented. The general EDGE kernel reproduces author missing-value fixtures without dropping rows. Primary three-session dailyization requires three actual source rows and all its required OHLC; incomplete inputs remain undefined. CS/AR require only formula-used closes, H/L and their specific window, so missing unused opens or following close do not invalidate them.\n\n'
        'The reference equity grid cannot certify a market-wide scheduled period absent from every supplied source. No external holiday rule is invented here. Existing futures root/session/contract construction remains unchanged; no continuous-contract fallback or new roll-day exclusion is introduced.\n')
    (OUT/'estimator_daily_alignment_review.md').write_text(alignment, encoding='utf-8')
    negative = ('# Negative and undefined output policy\n\nCS floors each finite raw interval at zero before the two-interval mean; its daily negative flag uses the mean of RAW intervals. Save both component flags and the negative-component count. AR floors its raw two-day s2 at zero before square root. EDGE primary uses the published paper Section3.2 Eq26 zero floor; the official package absolute root is only named robustness and replication evidence. No negative-but-computable value is an estimator failure.\n\n'
        'Raw signed AR/EDGE diagnostics are sign(s2)*sqrt(abs(s2)); CS raw daily spread is the arithmetic mean of raw nonlinear interval spreads. CS raw_moment is mean component alpha for diagnostics only. Undefined estimates stay NaN, raw_negative is null and raw_computable is false; no undefined-to-zero conversion.\n\n'
        'Failure rates retain ALL design-eligible asset-days as denominator. For each method, the negative-rate denominator is design-eligible days with that method\'s finite computable raw mathematical estimate; numerator additionally has raw_negative=True. Report the raw-computable denominator count. Never include missing/failed estimates as nonnegative estimates. No empirical rates were calculated here.\n\n'
        'Zero-range treatment is method-specific: CS requires good positive-width ranges under its official good-range prerequisite; forbidden range-reset preprocessing is not substituted. AR theoretical Eq9 is computable with finite flat ranges and may equal zero; its empirical carry-forward is later robustness only. EDGE applies its own tau/po/pc requirements, not a blanket zero-range screen.\n')
    (OUT/'negative_output_policy.md').write_text(negative, encoding='utf-8')
    review = '# Step 15 estimator mathematical and mapping freeze\n\n**'+spec['status']+'**.\n\n'
    review += (f'Tests: {tests["passed"]} passed, {tests["failed"]} failed; status {tests["status"]}. '
        f'Synthetic validation: {len(synthetic)} scalar checks passed. Official replication/equation oracle: {len(official)} scalar checks passed. All {len(raw)} Bloomberg acquisition hashes match.\n\n')
    review += ('CS: official SAS additive overnight adjustment, beta SUM, gamma, alpha and nonlinear spread match an independent scalar equation transcription. SAS itself was not executed. The stable tanh/log-difference evaluation is algebraically identical. No author CRSP empirical repairs or ratio exclusion are imported into the frozen project preprocessing.\n\n'
        'AR: hand-calculated eta and positive/negative Eq9 moments reconcile; Eq11 two-day zero-floor correction is primary. Empirical carry-forward is explicitly excluded.\n\n'
        'EDGE: complete fixture 0.0101849034905478 and missing fixture 0.01013284969780197 match, along with all eight published scalar intermediates. The pinned official Python signed/absolute outputs also reconcile. The published JFE Section3.2 Eq26 zero floor is PRIMARY. The fixture convention is not silently adopted as the primary negative policy.\n\n')
    review += alignment.split('\n\n', 1)[1] + '\n\n' + negative.split('\n\n', 1)[1]
    review += '\nFailure reasons: ' + ', '.join(FAILURE_REASONS) + '.\n\n'
    review += ('All formulas and tests use only synthetic or author-simulated open fixtures. No selected-stock, ETF, futures or crypto provider estimator values, Roll values, errors, rankings, HAC statistics or hypothesis tests were calculated. Existing source errors and flags are not repaired. Raw files, Step10--Step14 specifications and README/design_decisions/data_manifest remain unchanged. docs/project_1.md and docs/project_1_details.md were both read before implementation.\n\n'
        'Remaining before inference: HAC lag/dependence convention and summary weighting. Existing IMDX identity uncertainty, unknown abnormal-dividend setting, crypto formal quote currency and FX access limitations remain documented; no universe changes. Provider estimation requires a later explicit task and must retain Step14 exact calendars and failure denominators.\n\n'
        'Sources: [Corwin official materials](https://sites.nd.edu/scorwin/research/), '
        '[Abdi--Ranaldo paper](https://academic.oup.com/rfs/article/30/12/4437/4047344), '
        '[EDGE published paper](https://doi.org/10.1016/j.jfineco.2024.103916), '
        '[official EDGE repository](https://github.com/eguidotti/bidask). Pinned source hashes and licenses are preserved in sources/source_manifest.json.\n')
    (OUT/'step15_estimator_freeze_review.md').write_text(review, encoding='utf-8')
    assert snapshot() == before, 'Protected artifacts changed'
    after, _ = verify_hashes(PROJECT / 'data/raw_bloomberg'); require_verified(after)
    manifest = dict(status=spec['status'], tests=tests, protected_sha256=before,
        source_manifest_sha256=sha256(SOURCES/'source_manifest.json'),
        code_sha256={name: sha256(PROJECT/name) for name in ['src/spread_estimators.py', 'src/estimator_windows.py', 'src/estimator_spec_review.py', 'tests/test_spread_estimators.py', 'tests/test_estimator_windows.py']},
        output_sha256={p.name: sha256(p) for p in OUT.iterdir() if p.suffix in ['.yaml', '.csv', '.md', '.txt']},
        raw_bloomberg_hashes_verified=len(after), provider_price_panels_read=0,
        provider_estimator_or_benchmark_values_calculated=0, errors_or_rankings_calculated=0,
        fixture_role='Official simulated methodology fixtures only; not RiskLab observations or substitute intraday data')
    (OUT/'run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(spec['status']); print('Synthetic checks:', len(synthetic), 'Official checks:', len(official))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tests', action='store_true')
    run(parser.parse_args().run_tests)
