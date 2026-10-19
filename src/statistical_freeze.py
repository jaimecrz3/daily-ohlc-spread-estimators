"""Step16 final statistical policy, metadata/reference review and synthetic tests.

No provider price panel, estimator kernel, benchmark or inference engine is read
or executed. Small point-summary helpers are exercised on literal synthetic error
arrays in tests only. HAC covariance, regressions and p-values are NOT implemented.
"""
from pathlib import Path
import argparse
import json
import math
from numbers import Integral
import re
import subprocess
import sys

import numpy as np
import pandas as pd
import yaml

from bloomberg_io import sha256, verify_hashes, require_verified
from global_design_freeze import protected_hashes

PROJECT = Path(__file__).resolve().parents[1]
DIAG = PROJECT / 'outputs/diagnostics'
OUT = DIAG / 'statistical_freeze'
GLOBAL = DIAG / 'design_freeze/global_design_final_spec.yaml'
ESTIMATORS = DIAG / 'estimator_freeze/estimator_formula_spec.yaml'
REFERENCE = DIAG / 'bloomberg_validation/ocx_reference_comparison.csv'


def hac_lag(T):
    """Lag selection uses only date count, never values, residuals or significance."""
    if isinstance(T, bool) or not isinstance(T, Integral) or T < 1:
        raise ValueError('T must be a positive integer count of contributing dates')
    return min(math.floor(4 * (int(T) / 100)**(2 / 9)), int(T) - 1)


def point_summary(errors):
    """Equal weight for every supplied common-defined asset-day; no NaN dropping.

    Takes predeclared errors, not estimates or benchmark values. Only synthetic
    test vectors are used at this freeze stage; the generator never calls this.
    """
    values = np.asarray(errors, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError('A nonempty finite common-defined error vector is required')
    return dict(bias=float(values.mean()), mae=float(np.abs(values).mean()),
                rmse=float(np.sqrt(np.mean(values**2))), N=len(values))


def date_components(rows):
    """Synthetic-test helper: within-date means and counts, no regression/HAC fit."""
    data = rows[['date', 'error']].copy()
    if data.empty or data.date.isna().any() or not np.isfinite(data.error).all():
        raise ValueError('Finite errors and assigned dates required')
    return data.groupby('date', sort=True).error.agg(daily_mean_error='mean', n_t='size').reset_index()


def make_specs(global_spec, estimator_spec):
    """References preserve exact Step14/15 denominator and window policies."""
    if global_spec['status'] != 'FROZEN_FOR_ESTIMATOR_IMPLEMENTATION':
        raise ValueError('Frozen global design required')
    if estimator_spec['status'] != 'FROZEN_FOR_PROVIDER_ESTIMATION':
        raise ValueError('Frozen estimator formulas required')
    if 'IMDX' not in global_spec['selected_assets_by_class']['stocks']:
        raise ValueError('IMDX must remain in the frozen stock universe')
    if global_spec['asset_class_status']['fx'] != 'BLOCKED_OFFICIAL_SOURCE_ACCESS' or global_spec['fx_policy']['substitute_fx_allowed']:
        raise ValueError('Frozen blocked/no-substitute FX policy required')
    shared = dict(status='FROZEN_FOR_PRIMARY_PROVIDER_RUN', approval_step=16,
        approval_date='2026-10-16', primary_weighting='ASSET_DAY_WEIGHTED',
        bias_definition='(1/N)*sum_(i,t) Error_(i,t)',
        mae_definition='(1/N)*sum_(i,t) abs(Error_(i,t))',
        rmse_definition='sqrt((1/N)*sum_(i,t) Error_(i,t)^2)',
        error_definition='Estimate_(i,t) - RollBenchmark_(i,t); not calculated in Step16',
        accuracy_sample=global_spec['common_defined_accuracy_sample_definition'],
        failure_rate_denominator=estimator_spec['failure_rate_denominator'],
        negative_rate_denominator=estimator_spec['negative_rate_denominator'],
        imdx_identity_policy='source_defined_history_retained_without_manual_stitching',
        imdx_identity_continuity_certified=False,
        fx_status='IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS', substitute_fx_allowed=False,
        global_design_reference=GLOBAL.relative_to(PROJECT).as_posix(),
        estimator_spec_reference=ESTIMATORS.relative_to(PROJECT).as_posix(),
        existing_windows_adjacency_negative_and_failure_policies='Step14 and Step15 unchanged; this step resolves only weighting, inference convention and IMDX treatment',
        provider_estimation_executed=False, hac_inference_executed=False,
        precedence='Step16 resolves earlier pending weighting/HAC/identity decisions; earlier frozen artifacts are preserved unchanged')
    weighting = dict(shared,
        reporting_cells=['overall', 'asset class', 'liquidity tier', 'asset class x liquidity tier'],
        within_cell_weight='One equal weight per common-defined asset-day; N counts contributing asset-days in that cell',
        prohibited_primary_weights=['market capitalization', 'turnover', 'volume', 'liquidity rank', 'minute bar count', 'inverse variance', 'equal-asset weighting'],
        equal_asset_summaries='Possible separately labeled later robustness only; not primary and not run here',
        accuracy_metrics=['BIAS', 'MAE', 'RMSE'],
        unit_policy='Use one consistent scale in a cell: relative spread or bps; no mixing',
        no_new_observation_filters=True,
        negative_but_computable='Defined, including zero-floor primary outputs; never an estimator failure')
    hac = dict(shared,
        hac_target='SIGNED_ERROR_BIAS_ONLY',
        hac_regression_unit='One observation per distinct contributing date within estimator/reporting cell',
        hac_date_aggregation='daily_mean_error_t=mean(Error_(i,t)) over common-defined contributing assets in the cell',
        hac_weights='n_t = number of contributing asset-days on date t; count weights, not inverse estimated variances',
        hac_model='daily_mean_error_t = alpha + u_t; intercept-only WLS with weights n_t',
        intercept_identity='alpha=sum_t(n_t*daily_mean_error_t)/sum_t(n_t)=pooled asset-day mean error',
        hac_kernel='BARTLETT', hac_lag_formula='floor(4*(T/100)^(2/9))',
        hac_T_definition='Number of distinct contributing dates in the eventual reporting-cell common-defined accuracy sample',
        hac_small_sample_cap='L=min(floor(4*(T/100)^(2/9)), T-1)',
        hac_lag_inputs=['T'], significance_based_lag_selection=False,
        hac_time_order='Sort distinct contributing date labels chronologically; lags index that date series, not stacked asset rows or elapsed calendar days',
        hac_date_policy='No dates with no contributing asset-days are synthesized into this regression; do not modify estimator scheduled-adjacency grids',
        sandwich_specification={'score': 'g_t=n_t*(daily_mean_error_t-alpha)',
            'bread': '1/sum_t(n_t)',
            'bartlett_weight': 'w_l=1-l/(L+1), l=1,...,L',
            'meat': 'sum_t(g_t^2)+2*sum_(l=1)^L w_l*sum_(t=l+1)^T g_t*g_(t-l)',
            'variance_alpha': 'meat/(sum_t(n_t))^2',
            'finite_sample_multiplier': '1 (uncorrected asymptotic Newey-West sandwich; no implicit package degrees-of-freedom correction)'},
        confidence_level=.95, confidence_interval='alpha +/- 1.959963984540054 * HAC_SE',
        p_value_sidedness='TWO_SIDED', null_hypothesis='alpha=0',
        reference_distribution='ASYMPTOTIC_STANDARD_NORMAL',
        p_value_definition='2*(1-Phi(abs(alpha/HAC_SE)))',
        no_inference_metrics=['MAE', 'RMSE'],
        no_inference_metrics_role='Primary descriptive accuracy measures; no separate primary significance tests',
        reporting_fields=['alpha_bias', 'HAC_standard_error', '95_percent_confidence_interval', 'two_sided_p_value', 'T_dates', 'N_asset_days', 'HAC_lag'],
        empty_or_degenerate_cells='Preserve/report the cell and reason; no inference for T<2 or nonfinite/nonpositive HAC variance. No invented SE, CI, p-value or zero-variance significance.',
        dependence_rationale='Date aggregation accommodates common-date cross-sectional shocks in the aggregate score; HAC addresses serial correlation across contributing dates; n_t weights retain asset-day point weighting',
        limitation='This convention does not eliminate every form of panel dependence; small T and irregular temporal support remain limitations',
        execution_status='SPECIFICATION_ONLY; no weighted regression, HAC covariance, confidence interval or p-value calculated')
    return weighting, hac


def snapshot():
    protected = protected_hashes()
    for folder in ['design_freeze', 'estimator_freeze']:
        protected.update({p.relative_to(PROJECT).as_posix(): sha256(p)
                          for p in (DIAG / folder).iterdir() if p.is_file()})
    for path in [PROJECT/'docs/project_1.md', PROJECT/'docs/project_1_details.md', REFERENCE,
                 PROJECT/'src/spread_estimators.py', PROJECT/'src/estimator_windows.py']:
        protected[path.relative_to(PROJECT).as_posix()] = sha256(path)
    return protected


def verify_previous():
    """Hash-only checks; no workbook decoding or provider price table reads."""
    for folder in ['design_freeze', 'estimator_freeze']:
        manifest = json.loads((DIAG/folder/'run_manifest.json').read_text(encoding='utf-8'))
        for name, expected in manifest['output_sha256'].items():
            if sha256(DIAG/folder/name) != expected:
                raise ValueError('Prior frozen output changed: '+folder+'/'+name)
    global_spec = yaml.safe_load(GLOBAL.read_text(encoding='utf-8'))
    for ref in global_spec['frozen_spec_references'].values():
        if sha256(PROJECT/ref['path']) != ref['sha256']:
            raise ValueError('Earlier class/input/benchmark specification changed')
    old = json.loads((DIAG/'bloomberg_validation/run_manifest.json').read_text(encoding='utf-8'))
    key = REFERENCE.relative_to(PROJECT).as_posix()
    if sha256(REFERENCE) != old['derived_sha256'][key]:
        raise ValueError('Saved Bloomberg OCX/IMDX evidence changed')


def run(run_tests=False):
    verify_previous()
    before = snapshot()
    global_spec = yaml.safe_load(GLOBAL.read_text(encoding='utf-8'))
    estimator_spec = yaml.safe_load(ESTIMATORS.read_text(encoding='utf-8'))
    weighting, hac = make_specs(global_spec, estimator_spec)
    # Existing saved REFERENCE fields only; no daily prices or ticker stitching.
    evidence = pd.read_csv(REFERENCE, keep_default_na=False)
    raw, _ = verify_hashes(PROJECT/'data/raw_bloomberg'); require_verified(raw)
    OUT.mkdir(parents=True, exist_ok=True)
    tests = dict(status='NOT_RUN_BY_THIS_REVIEW', passed=0, failed=0)
    if run_tests:
        completed = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests'],
                                   cwd=PROJECT, capture_output=True, text=True)
        output = completed.stdout + completed.stderr
        (OUT/'test_results.txt').write_text(output, encoding='utf-8')
        print(output, flush=True)
        match = re.search(r'Ran (\d+) tests?', output)
        if completed.returncode or match is None:
            raise RuntimeError('Full suite failed; statistical freeze not approved')
        tests = dict(status='PASSED', passed=int(match.group(1)), failed=0)
    else:
        weighting['status'] = hac['status'] = 'POLICY_SPECIFIED_PENDING_FULL_SUITE'
    for name, spec in [('primary_weighting_spec.yaml', weighting), ('hac_inference_spec.yaml', hac)]:
        (OUT/name).write_text(yaml.safe_dump(spec, sort_keys=False), encoding='utf-8')
    identity = '# IMDX source-defined historical identity treatment\n\n'
    identity += ('**Frozen treatment:** `source_defined_history_retained_without_manual_stitching`.\n\n'
        '`imdx_identity_continuity_certified: False`\n\n'
        'IMDX remains selected in the frozen LOW stock tier. Retain the historical First Rate series under IMDX and the historical observations returned by Bloomberg under the current IMDX request exactly as supplied. '
        'Do not manually stitch a separate OCX series, replace historical observations, drop IMDX or reinterpret the supplied series as a fully certified economic-security history. This uncertainty is a data-identity limitation, not an estimator failure, calendar exclusion or automatic undefined-estimate flag.\n\n'
        'Existing saved direct reference evidence (not new extraction or external research):\n\n'
        '| Security | Field | Cached value | Error flag |\n| --- | --- | --- | --- |\n')
    for row in evidence.itertuples(index=False):
        identity += f'| {row.comparison_security} | {row.field} | {row.cached_value} | {row.error_flag} |\n'
    identity += ('\nThe current IMDX request has FIGI BBG008P5VFV1 and ISIN US68235C2061. The OCX comparison request returns NAME=ONCOCYTE CORP and OCX US ticker, but its ID_BB_GLOBAL and ID_ISIN are source errors. '
        'This does not independently certify stable-ID continuity across the full historical span and proves no actual data error requiring a universe change. '
        'No broad external ticker-history reconstruction was conducted. Earlier pending-identity notes remain historical audit records; Step16 resolves the primary treatment without pretending certification.\n\n'
        f'Source: `{REFERENCE.relative_to(PROJECT).as_posix()}`; SHA-256 `{sha256(REFERENCE)}`. All 11 Bloomberg acquisition hashes verified; no workbook contents changed.\n')
    (OUT/'imdx_identity_review.md').write_text(identity, encoding='utf-8')
    review = '# Step16 final pre-estimation statistical freeze\n\n**'+weighting['status']+'**.\n\n'
    review += (f'Tests: {tests["passed"]} passed, {tests["failed"]} failed ({tests["status"]}). All {len(raw)} Bloomberg raw hashes match.\n\n'
        'Primary summaries are ASSET-DAY WEIGHTED within overall, asset class, liquidity tier and class x tier cells. On the common-defined accuracy sample: BIAS=sum(error)/N; MAE=sum(abs(error))/N; RMSE=sqrt(sum(error^2)/N). '
        'Every contributing asset-day has equal weight. There is no market-cap, turnover, volume, rank, bar-count, inverse-variance or primary equal-asset weighting. Equal-asset summaries remain possible later robustness only.\n\n'
        'Primary HAC inference applies to SIGNED ERROR / BIAS only. For each estimator/cell, first calculate daily mean error across contributing assets and n_t, then fit an intercept-only weighted regression with weights n_t. Its intercept equals the pooled asset-day-weighted mean. '
        'Use a Bartlett Newey-West sandwich and L=min(floor(4*(T/100)^(2/9)),T-1), with T the number of distinct contributing dates. Never select lags by residual results or significance. '
        'The covariance convention is explicitly uncorrected asymptotic (no hidden degrees-of-freedom multiplier); score g_t=n_t*u_t, bread=1/sum(n_t). Use a normal-reference 95% CI and two-sided normal-reference p-value against zero bias. These are prospective conventions, not calculations performed here.\n\n'
        'The cross-section is summarized within date because assets may share market-wide shocks on that date. HAC then addresses serial autocorrelation across dates; n_t weights preserve the asset-day point estimand. '
        'This does not eliminate every possible form of panel dependence. Lags index sorted contributing dates, not stacked asset rows. No empty-date values are synthesized for inference and no estimator adjacency rule is changed. '
        'MAE and RMSE remain primary DESCRIPTIVE measures, with no separate primary significance test. Later reports must retain bias, HAC SE, 95% CI, two-sided p-value, T, N and L; empty/degenerate cells retain explicit undefined inference reasons.\n\n'
        'Failure-rate denominator is ALL design_eligible asset-days. Negative-rate denominator is design-eligible observations with each method\'s finite computable RAW mathematical estimate; undefined is not negative. Negative-but-computable observations remain defined, including zero-floor outputs. Step14/15 definitions, windows and scheduled adjacency are unchanged.\n\n'
        'IMDX remains the selected source-defined historical series. imdx_identity_continuity_certified=False; source_defined_history_retained_without_manual_stitching. No separate OCX stitching, historical replacement, drop or new failure flag. Saved reference fields provide current IMDX IDs but OCX identifiers remain source errors; full historical continuity is not independently certified. See imdx_identity_review.md.\n\n'
        'FX remains IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS with no substitutes, under the existing student-supplied professor-approved policy. It does not block the four completed classes; no new FX methodology or access probe is needed here.\n\n'
        'Step16 resolves the pending weighting, HAC convention and IMDX primary-treatment decisions. Step10--15 specifications, universes, tiers, exact primary calendars, raw data and README.md/design_decisions.md/data_manifest.csv remain unchanged. '
        'No provider price panels were read for this step. No provider CS/AR/EDGE, Roll, errors, rankings, HAC fits, standard errors, confidence intervals, p-values or hypothesis tests were computed. Tests use literal synthetic error arrays and count-only lag checks; no synthetic or provider HAC regression is executed. '
        'The freeze is not an automatic provider-run instruction. Reproduce with `.venv/Scripts/python.exe -B src/statistical_freeze.py --run-tests`.\n')
    (OUT/'step16_final_pre_estimation_freeze.md').write_text(review, encoding='utf-8')
    assert snapshot() == before, 'Protected prior artifacts changed'
    final_raw, _ = verify_hashes(PROJECT/'data/raw_bloomberg'); require_verified(final_raw)
    manifest = dict(status=weighting['status'], tests=tests, protected_sha256=before,
        code_sha256={name: sha256(PROJECT/name) for name in ['src/statistical_freeze.py', 'tests/test_statistical_freeze.py']},
        output_sha256={p.name: sha256(p) for p in OUT.iterdir() if p.suffix in ['.yaml', '.md', '.txt']},
        raw_bloomberg_hashes_verified=len(final_raw), provider_price_panels_read=0,
        provider_estimator_or_benchmark_values_calculated=0, provider_errors_or_rankings_calculated=0,
        HAC_inference_or_hypothesis_tests_executed=0)
    (OUT/'run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(weighting['status'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-tests', action='store_true')
    run(parser.parse_args().run_tests)
