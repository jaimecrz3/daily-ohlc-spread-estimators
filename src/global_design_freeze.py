"""Step 14: freeze source calendars and sample policies using saved artifacts only.

No raw intraday reads, benchmark formula imports or estimator calculations.
Run: .venv/Scripts/python.exe -B src/global_design_freeze.py
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import yaml

from bloomberg_io import sha256, verify_hashes, require_verified

PROJECT = Path(__file__).resolve().parents[1]
DIAG = PROJECT / 'outputs/diagnostics'
FINAL = DIAG / 'final_universe'
OUT = DIAG / 'design_freeze'
OHLC = ['PX_OPEN', 'PX_HIGH', 'PX_LOW', 'PX_LAST']
TIERS = {
    'stocks': {'LOW': ['IMDX', 'AIRG', 'CCBG'], 'MEDIUM': ['ANGO', 'SNDL', 'FCPT'], 'HIGH': ['FDS', 'XPO', 'BIDU']},
    'etfs': {'LOW': ['SDCI', 'AAA', 'JSML'], 'MEDIUM': ['PGJ', 'PJAN', 'FSMD'], 'HIGH': ['SPBO', 'SCHM', 'MCHI']},
    'futures': {'LOW': ['HG', 'AD', 'B6'], 'MEDIUM': ['J1', 'GC', 'E6'], 'HIGH': ['NQ', 'ZF', 'ES']},
    'crypto': {'LOW': ['ICX', 'NEO', 'DASH'], 'MEDIUM': ['ZEC', 'ALGO', 'MKR'], 'HIGH': ['NEAR', 'LINK', 'DOGE']}}
SPEC_PATHS = {
    'benchmark': DIAG / 'benchmark_freeze/benchmark_final_spec.yaml',
    'daily_input': DIAG / 'daily_input_freeze/daily_input_final_spec.yaml',
    'futures': FINAL / 'futures_final/futures_final_spec.yaml',
    'crypto_universe': FINAL / 'crypto_final/crypto_final_spec.yaml',
    'crypto_calendar': FINAL / 'crypto_final/crypto_final_analysis_spec.yaml',
    'fx': FINAL / 'fx_final/fx_final_spec.yaml'}


def assets(asset_class):
    return [a for group in TIERS[asset_class].values() for a in group]


def labels(series):
    dates = pd.to_datetime(series, errors='raise')
    if dates.isna().any() or dates.ne(dates.dt.normalize()).any():
        raise ValueError('Source dates must be assigned midnight daily labels')
    return dates.dt.strftime('%Y-%m-%d')


def source_calendar(local, bloomberg, selected):
    """Observed-date union audit; nine-way intersection of source-available dates.

    Outcome, volume, daily quality and pair-count columns never gate this calendar.
    Duplicate source days are a structural error, not silently resolved.
    """
    if len(selected) != 9 or len(set(selected)) != 9:
        raise ValueError('Exactly nine distinct frozen assets required')
    left = local.loc[local.asset.isin(selected), ['asset', 'date', 'bars_observed']].copy()
    right = bloomberg.loc[bloomberg.asset.isin(selected), ['asset', 'date', *OHLC]].copy()
    for frame in (left, right):
        frame['date'] = labels(frame.date)
        if frame.duplicated(['asset', 'date']).any():
            raise ValueError('Duplicate source asset-day; calendar blocked')
    left = left.loc[left.date.between('2015-01-01', '2025-12-31')]
    right = right.loc[right.date.between('2015-01-01', '2025-12-31')]
    prices = right[OHLC].apply(pd.to_numeric, errors='coerce')
    right['finite_positive_ohlc'] = np.isfinite(prices).all(axis=1) & prices.gt(0).all(axis=1)
    right['bloomberg_row'] = True
    left['local_session'] = pd.to_numeric(left.bars_observed, errors='coerce').gt(0)
    joined = left[['asset', 'date', 'local_session']].merge(
        right[['asset', 'date', 'bloomberg_row', 'finite_positive_ohlc']],
        on=['asset', 'date'], how='outer', validate='one_to_one')
    for col in ['local_session', 'bloomberg_row', 'finite_positive_ohlc']:
        joined[col] = joined[col].eq(True)
    joined['missing_local_session'] = ~joined.local_session
    joined['missing_bloomberg_row'] = ~joined.bloomberg_row
    joined['incomplete_nonfinite_or_nonpositive_ohlc'] = joined.bloomberg_row & ~joined.finite_positive_ohlc
    joined['source_available'] = joined.local_session & joined.bloomberg_row & joined.finite_positive_ohlc
    available = {a: set(joined.loc[joined.asset.eq(a) & joined.source_available, 'date']) for a in selected}
    common = sorted(set.intersection(*available.values()))
    joined['class_common_date'] = joined.date.isin(common)
    summaries = []
    for asset in selected:
        part = joined.loc[joined.asset.eq(asset)]
        dates = sorted(available[asset])
        summaries.append(dict(asset=asset, source_available_first=dates[0] if dates else None,
            source_available_last=dates[-1] if dates else None, source_available_dates=len(dates),
            observed_source_union_dates=len(part), missing_local_session=int(part.missing_local_session.sum()),
            missing_bloomberg_row=int(part.missing_bloomberg_row.sum()),
            incomplete_nonfinite_or_nonpositive_ohlc=int(part.incomplete_nonfinite_or_nonpositive_ohlc.sum()),
            available_but_not_common=int((part.source_available & ~part.class_common_date).sum())))
    # Date-level audit also records assets absent from BOTH sources on a date
    # observed for another asset. These are audit cells, never OHLC observations.
    date_audit = []
    for day in sorted(set(joined.date)):
        part = joined.loc[joined.date.eq(day)].set_index('asset')
        missing_local = [a for a in selected if a not in part.index or not part.loc[a, 'local_session']]
        missing_bb = [a for a in selected if a not in part.index or not part.loc[a, 'bloomberg_row']]
        bad_ohlc = [a for a in selected if a in part.index and part.loc[a, 'incomplete_nonfinite_or_nonpositive_ohlc']]
        date_audit.append(dict(date=day, primary_inclusion=day in common,
            source_available_assets=sum(day in available[a] for a in selected),
            missing_local_assets=';'.join(missing_local), missing_bloomberg_assets=';'.join(missing_bb),
            invalid_primary_ohlc_assets=';'.join(bad_ohlc)))
    return common, joined.sort_values(['asset', 'date']), pd.DataFrame(summaries), pd.DataFrame(date_audit)


def design_eligibility(rows, selected, primary_dates):
    """Only source existence, frozen asset and date membership; ignore outcomes."""
    return rows.asset.isin(selected) & rows.date.isin(primary_dates) & rows.required_source_day_exists.eq(True)


def common_accuracy_mask(rows):
    columns = ['design_eligible', 'benchmark_defined', 'cs_defined', 'ar_defined', 'edge_defined']
    for column in columns:
        if not rows[column].isin([True, False]).all():
            raise ValueError('Explicit separately recorded definedness flags required')
    return rows[columns].eq(True).all(axis=1)


def failure_rate_denominator(rows):
    if not rows.design_eligible.isin([True, False]).all():
        raise ValueError('Explicit design eligibility required')
    return int(rows.design_eligible.eq(True).sum())


def protected_hashes():
    files = list(SPEC_PATHS.values()) + [FINAL / 'selected_stocks_etfs.csv',
        FINAL / 'crypto_final/selection_audit.csv', FINAL / 'crypto_final/selected_crypto.csv']
    files += [p for name in ['README.md', 'design_decisions.md', 'data_manifest.csv']
              for p in PROJECT.rglob(name) if '.venv' not in p.parts and '.git' not in p.parts]
    files += [p for p in (PROJECT / 'data/raw_bloomberg').rglob('*') if p.is_file()]
    return {p.relative_to(PROJECT).as_posix(): sha256(p) for p in files if p.is_file()}


def table(frame):
    return '\n'.join(['| ' + ' | '.join(frame.columns) + ' |',
        '| ' + ' | '.join(['---'] * len(frame.columns)) + ' |'] +
        ['| ' + ' | '.join(map(str, row)) + ' |' for row in frame.itertuples(index=False, name=None)])


def run():
    before = protected_hashes()
    inputs = {}
    def verified(path, expected=None):
        digest = sha256(path)
        if expected is not None and digest != expected:
            raise ValueError('Prior validated artifact hash changed: ' + str(path))
        inputs[path.relative_to(PROJECT).as_posix()] = digest
        return path
    specs = {name: yaml.safe_load(verified(path).read_text(encoding='utf-8')) for name, path in SPEC_PATHS.items()}
    benchmark, daily = specs['benchmark'], specs['daily_input']
    assert benchmark['minimum_covariance_pairs'] == 2 and benchmark['covariance_ddof'] == 1
    assert daily['frozen_for_future_estimator_implementation']
    assert all(specs[key]['status'] == 'FROZEN' for key in ['futures', 'crypto_universe', 'crypto_calendar'])
    assert specs['futures']['selected_roots'] == assets('futures')
    assert specs['crypto_universe']['selected_assets'] == assets('crypto')
    assert specs['futures']['liquidity_tiers'] == TIERS['futures']
    assert specs['crypto_universe']['liquidity_tiers'] == TIERS['crypto']
    assert specs['crypto_calendar']['liquidity_tiers'] == TIERS['crypto']
    assert specs['fx']['status'] == 'BLOCKED' and not specs['fx']['substitute_sources_permitted']
    selected = pd.read_csv(verified(FINAL / 'selected_stocks_etfs.csv'))
    for cls in ['stocks', 'etfs']:
        for tier, expected in TIERS[cls].items():
            assert set(selected.loc[selected.asset_class.eq(cls) & selected.liquidity_tier.eq(tier), 'asset']) == set(expected)
    raw, _ = verify_hashes(PROJECT / 'data/raw_bloomberg'); require_verified(raw)
    bb_manifest = json.loads((DIAG / 'bloomberg_validation/run_manifest.json').read_text())
    bb_path = PROJECT / 'data/interim/bloomberg/daily_adjusted.parquet'
    bb = pd.read_parquet(verified(bb_path, bb_manifest['parquet_sha256'][bb_path.relative_to(PROJECT).as_posix()]))
    assert bb.source.eq('Bloomberg').all() and bb.convention.eq('adjusted').all()
    local_path = FINAL / 'local_daily_validation/selected_daily_ohlcv.csv'
    local_manifest = json.loads((local_path.parent / 'run_manifest.json').read_text())
    local = pd.read_csv(verified(local_path, local_manifest['output_sha256'][local_path.name]))
    assert local.timezone.eq('America/New_York').all()
    assert local.source_role.eq('local_daily_validation').all()
    calendars = {}; audits = []; summaries = []; availability = []; date_audits = []
    for cls in ['stocks', 'etfs']:
        dates, detail, summary, date_audit = source_calendar(local, bb, assets(cls))
        if len(dates) < 730 or pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0]) < pd.Timedelta(days=730):
            raise ValueError('Class common calendar is not a substantial multi-year sample: ' + cls)
        calendars[cls] = dates
        for frame in [detail, summary, date_audit]: frame.insert(0, 'asset_class', cls)
        availability.append(detail); summaries.append(summary); date_audits.append(date_audit)
        audits.append(dict(asset_class=cls, status='FROZEN', first_date=dates[0], last_date=dates[-1],
            common_dates=len(dates), potential_asset_days=9*len(dates),
            candidate_union_dates=len(date_audit), excluded_union_dates=int((~date_audit.primary_inclusion).sum()),
            dates_missing_local=int(date_audit.missing_local_assets.ne('').sum()),
            dates_missing_bloomberg=int(date_audit.missing_bloomberg_assets.ne('').sum()),
            dates_invalid_primary_ohlc=int(date_audit.invalid_primary_ohlc_assets.ne('').sum())))
    futures = specs['futures']
    dates = futures['primary_common_trade_dates']
    assert len(dates) == len(set(dates)) == 259 and dates == sorted(dates)
    assert (dates[0], dates[-1]) == ('2024-01-02', '2024-12-31')
    for root in assets('futures'):
        path = FINAL / f'futures_final/historical/{root}_historical_daily_ohlcv.csv'
        digest = futures['provenance']['input_daily_panel_sha256'][path.relative_to(PROJECT).as_posix()]
        panel = pd.read_csv(verified(path, digest), usecols=['asset', 'date', 'bars_observed'])
        observed = set(panel.loc[panel.bars_observed.gt(0) & panel.date.between(dates[0], dates[-1]), 'date'])
        assert observed == set(dates) and panel.asset.eq(root).all()
    calendars['futures'] = dates
    crypto = specs['crypto_calendar']
    crypto_dir = FINAL / 'crypto_final'
    cm = json.loads((crypto_dir / 'historical/run_manifest.json').read_text())
    crypto_hashes = {Path(key).as_posix(): digest for key, digest in cm['output_sha256'].items()}
    cp = crypto_dir / crypto['exact_primary_calendar']
    dates = pd.read_csv(verified(cp, crypto_hashes[cp.relative_to(crypto_dir).as_posix()])).utc_date.tolist()
    assert len(dates) == len(set(dates)) == 1417 and dates == sorted(dates)
    assert (dates[0], dates[-1]) == ('2022-02-01', '2025-12-31')
    sets = []
    for asset in assets('crypto'):
        path = crypto_dir / f'historical/{asset}_historical_daily_ohlcv.csv'
        panel = pd.read_csv(verified(path, crypto_hashes[path.relative_to(crypto_dir).as_posix()]),
                            usecols=['asset', 'date', 'aggregation_valid', 'bars_observed'])
        assert panel.asset.eq(asset).all()
        sets.append(set(panel.loc[panel.aggregation_valid & panel.bars_observed.gt(0), 'date']))
    assert sorted(set.intersection(*sets)) == dates
    calendars['crypto'] = dates
    for cls in ['futures', 'crypto']:
        dates = calendars[cls]
        audits.append(dict(asset_class=cls, status='FROZEN_UNCHANGED', first_date=dates[0], last_date=dates[-1],
            common_dates=len(dates), potential_asset_days=len(dates)*9))
    audits.append(dict(asset_class='fx', status='BLOCKED_OFFICIAL_SOURCE_ACCESS'))
    OUT.mkdir(parents=True, exist_ok=True)
    pd.concat(availability).to_csv(OUT / 'source_availability_audit.csv', index=False)
    pd.concat(summaries).to_csv(OUT / 'individual_source_coverage.csv', index=False)
    pd.concat(date_audits).to_csv(OUT / 'source_calendar_date_audit.csv', index=False)
    pd.DataFrame(audits).to_csv(OUT / 'class_calendar_audit.csv', index=False)
    primary_rows = []
    for cls, dates in calendars.items():
        pd.DataFrame({'date': dates}).to_csv(OUT / f'{cls}_primary_calendar.csv', index=False)
        for tier, group in TIERS[cls].items():
            for asset in group:
                primary_rows.extend(dict(asset_class=cls, asset=asset, liquidity_tier=tier, date=day,
                    required_source_day_exists=True, design_eligible=True) for day in dates)
    grid = pd.DataFrame(primary_rows)
    assert grid.groupby(['asset_class', 'date']).asset.nunique().eq(9).all()
    assert grid.groupby(['asset_class', 'date', 'liquidity_tier']).asset.nunique().eq(3).all()
    grid.to_csv(OUT / 'design_eligible_asset_days.csv', index=False)
    remaining = [
        'Resolve estimator-specific published formulas, window lengths, warm-up requirements, numerical tolerances, negative/raw-output treatment and failure reasons before provider estimator calculation; never tune to outcomes.',
        'Validate scheduled-session/date adjacency for each estimator window, including exchange closures and omitted source sessions; common observed dates must never compress gaps. Preserve context outside the evaluation calendar when needed for legitimate lags; score endpoints only on frozen primary dates.',
        'Specify HAC lag convention and applicable time-series aggregation/dependence structure before inference; no empirical-result lag optimization or HAC implementation here.',
        'Specify overall/group weighting and aggregation of errors plus the negative-estimate-rate denominator and published-output meaning before producing summaries; never silently use successful-only denominators for failure rates.',
        'Retain IMDX/OCX stable-ID stitching uncertainty; no manual ticker-history stitching or universe replacement. Source availability does not certify economic identity.',
        'FX official access must be restored and its session, denomination and liquidity comparability validated before an FX freeze; other four classes can proceed.']
    spec = dict(status='FROZEN_FOR_ESTIMATOR_IMPLEMENTATION', approval_step=14,
        study_horizon={'start': '2015-01-01', 'end': '2025-12-31', 'interpretation': 'Study horizon; class-specific primary support, not a balanced all-class 2015-2025 panel'},
        asset_classes_in_scope=['stocks', 'etfs', 'futures', 'crypto', 'fx'],
        asset_class_status={**{cls: 'FROZEN' for cls in TIERS}, 'fx': 'BLOCKED_OFFICIAL_SOURCE_ACCESS'},
        selected_assets_by_class={**{cls: assets(cls) for cls in TIERS}, 'fx': []}, liquidity_tiers=TIERS,
        liquidity_calibration_year=2024,
        frozen_spec_references={name: {'path': path.relative_to(PROJECT).as_posix(), 'sha256': sha256(path)}
                                for name, path in SPEC_PATHS.items()},
        stock_etf_source_calendar_policy={'local_session': 'Observed retained 09:30 <= America/New_York local time < 16:00 session with bars_observed > 0',
            'daily_source': 'Existing Bloomberg adjusted row', 'required_common_fields': OHLC,
            'price_requirement': 'All four OHLC fields finite and strictly positive',
            'excluded_outcome_gates': ['Roll values or definedness', 'CS/AR/EDGE values or definedness', 'estimator errors', 'statistical significance'],
            'structural_errors': 'Duplicate/unassigned source dates block construction, never silently deduplicated',
            'no_new_quality_cutoffs': True},
        primary_calendar_by_class={cls: dict(start=days[0], end=days[-1], exact_common_dates=len(days),
            potential_design_eligible_asset_days=9*len(days), calendar_file=f'{cls}_primary_calendar.csv',
            calendar_sha256=sha256(OUT / f'{cls}_primary_calendar.csv'),
            definition='Nine-way exact source-available intersection; no Roll or estimator outcome gate' if cls in ['stocks', 'etfs'] else 'Prior frozen exact calendar, unchanged') for cls, days in calendars.items()},
        daily_estimator_source_by_class={
            'stocks': {'primary': 'Bloomberg adjusted OHLC', 'robustness': 'Bloomberg unadjusted OHLC',
                'acquired_adjustment': {'CapChg': 'T', 'CshAdjNormal': 'T', 'CshAdjAbnormal': 'UNKNOWN'}, 'First_Rate_role': 'RTH validation and benchmark-source infrastructure only'},
            'etfs': {'same_as': 'stocks'},
            'futures': 'Daily OHLC from exact provider-selected unadjusted individual contract and verified root-specific trade-date/session rules',
            'crypto': 'Validated local provider one-minute OHLC aggregated by UTC calendar day', 'fx': 'BLOCKED; official RiskLab First Rate only'},
        benchmark_spec_reference=SPEC_PATHS['benchmark'].relative_to(PROJECT).as_posix(),
        benchmark_spec_sha256=sha256(SPEC_PATHS['benchmark']),
        benchmark_formula={'return': 'C_t / C_(t-1) - 1', 'adjacency_minutes': 1, 'covariance_lag': 1, 'ddof': 1,
            'minimum_covariance_pairs': 2, 'negative_gamma': '2*sqrt(-gamma)', 'bps': '10000*relative',
            'nonnegative_gamma': 'NaN; benchmark_defined=False; non_negative_autocovariance',
            'insufficient_pairs': 'NaN; benchmark_defined=False; preserve failure reason',
            'sessions': 'Existing latest verified class session specifications only; no cross-day/session/contract pairs'},
        primary_roll_pair_threshold=2, higher_primary_pair_threshold_allowed=False,
        design_eligible_definition='Frozen selected asset AND exact frozen class primary date AND required source day/session exists; independent of all method outcomes',
        benchmark_defined_definition='Only frozen Roll computability and strictly negative lag-one covariance; undefined outcomes remain in design coverage',
        estimator_defined_definition='Separate cs_defined, ar_defined, edge_defined and method-specific failure reasons under each published/raw-output policy; not inferred from another method',
        common_defined_accuracy_sample_definition='design_eligible AND benchmark_defined AND cs_defined AND ar_defined AND edge_defined',
        failure_rate_denominator='All design_eligible asset-days, separately for Roll, CS, AR and EDGE; no outcome conditioning',
        missing_data_policy='No OHLC imputation, carry-forward, minute/day synthesis, gap bridging or compression; preserve partial rows, source errors and all quality diagnostics; estimator windows require valid scheduled adjacency',
        corporate_action_policy=daily['corporate_action_boundary_policy'],
        futures_contract_policy={key: futures[key] for key in ['missing_contract_policy', 'continuous_price_policy', 'roll_mapping_policy', 'session_rule_policy']},
        crypto_quote_basis_policy={'status': specs['crypto_universe']['quote_basis_validation_status'], 'quote_currency': specs['crypto_universe']['quote_currency'], 'literal_USD_claim_allowed': False},
        fx_policy={'in_scope': True, 'status': 'BLOCKED_OFFICIAL_SOURCE_ACCESS', 'substitute_fx_allowed': False,
            'professor_instruction_basis': 'Student-supplied professor instruction, Step14; no independent verification claimed',
            'submission_treatment': 'Continue other classes; document inaccessible official FX and present completed components; student reports no penalty for this access limitation',
            'not_intentional_class_exclusion': True, 'access_audit': 'outputs/diagnostics/final_universe/fx_final/fx_access_audit.csv'},
        primary_estimands={'future_outputs': ['bias versus Roll', 'MAE', 'RMSE', 'estimator failure/undefined rate', 'negative-estimate rate where meaningful under published/raw output definition'],
            'accuracy_definitions': {'signed_error': 'estimate - Roll', 'bias': 'mean(signed_error)',
                'MAE': 'mean(abs(signed_error))', 'RMSE': 'sqrt(mean(signed_error**2))',
                'sample': 'Identical common_defined_accuracy_sample for all three methods'},
            'groupings': ['overall', 'asset class', 'liquidity tier', 'asset class x liquidity tier'],
            'units': ['basis points', 'relative price'], 'accuracy_sample': 'common_defined_accuracy_sample',
            'failure_sample': 'design_eligible', 'inferential_uncertainty': 'HAC standard errors', 'HAC_lag': 'PENDING_METHOD_CONVENTION_NOT_RESULT_OPTIMIZATION'},
        robustness_only_components=['Bloomberg unadjusted OHLC', 'cross-fitted error model',
            'Prespecified later higher Roll-pair reliability cutoffs; never replace primary',
            'Successive-observed-bar benchmark sensitivity, not primary',
            'Method-specific author preprocessing replication if separately authorized'],
        supplementary_history_role='Earlier/later asset-specific history outside class primary calendars is descriptive only; do not pool changing composition as a liquidity effect',
        look_ahead_limitations=['All tiers use 2024 calibration; pre-2024 stocks/ETF/crypto labels are ex-post and use future information',
            'Futures primary comparison is conditional on the 2024 calibration year, not out of sample', 'No benchmark or estimator performance influenced selection'],
        source_dependence_limitation='Futures and crypto daily OHLC and Roll share local one-minute source; mechanical dependence must be discussed later',
        remaining_pre_estimation_decisions=remaining,
        implementation_scope='Global design frozen; statistical/numerical decisions listed here must be resolved before relevant provider calculations or inference',
        precedence='Step14 resolves prior comparison-eligibility pending fields and extends earlier pilot-only session descriptions by reference to later freezes; prior artifacts retained unchanged',
        no_benchmark_or_estimator_values_calculated=True)
    (OUT / 'global_design_final_spec.yaml').write_text(yaml.safe_dump(spec, sort_keys=False), encoding='utf-8')
    policy = '# Comparison sample policy\n\n'
    for key in ['design_eligible_definition', 'benchmark_defined_definition', 'estimator_defined_definition',
                'common_defined_accuracy_sample_definition', 'failure_rate_denominator', 'missing_data_policy']:
        policy += f'**{key}**: {spec[key]}\n\n'
    policy += ('Accuracy comparisons use identical common-defined asset-days for CS/AR/EDGE; method-specific successful-only headline rankings are prohibited. '
        'Failure/coverage reporting retains every design-eligible day, including future undefined Roll and estimator results. '
        'No outputs or future outcome flags are fabricated in the design-eligible table. Two Roll covariance pairs are the mathematical minimum and the sole primary pair-count floor; there is no extra coverage or reliability filter. '
        'Preserve roll_pairs, bar counts, gaps, zero-volume and other quality counts for diagnostics and explicitly labeled future robustness.\n\n'
        'Frozen calendars select evaluation endpoints, not compressed estimator input sequences. Missing intermediate scheduled sessions must break applicable estimator windows; never lag across the common calendar as if excluded observations were adjacent. '
        'Use existing full source context for valid lags/warm-up when later methodology permits; context does not enlarge the evaluation sample.\n')
    (OUT / 'comparison_sample_policy.md').write_text(policy, encoding='utf-8')
    (OUT / 'remaining_pre_estimation_decisions.md').write_text('# Remaining pre-estimation decisions\n\n' +
        '\n\n'.join(f'{i}. {item}' for i, item in enumerate(remaining, 1)) +
        '\n\nDocumented acquisition/design limitations are not licenses to repair data: abnormal-dividend setting UNKNOWN, vendor session/auction and adjustment equivalence uncertified, futures historical session gaps and source-unavailable contracts, crypto formal quote currency UNKNOWN, common-source dependence, class-calendar confounding and 2024 ex-post tier calibration.\n', encoding='utf-8')
    review = '# Step 14 global design freeze\n\n**FROZEN_FOR_ESTIMATOR_IMPLEMENTATION** for the four completed classes; FX remains in scope and blocked.\n\n'
    review += table(pd.DataFrame(audits)[['asset_class', 'status', 'first_date', 'last_date', 'common_dates', 'potential_asset_days']]) + '\n\n'
    review += 'Individual source-available stock/ETF coverage\n\n' + table(pd.concat(summaries)) + '\n\n'
    review += ('The stock/ETF calendars require an observed retained First Rate RTH session plus an existing Bloomberg adjusted row with complete finite positive OHLC. '
        'No benchmark values, covariance signs, definedness, estimator values or performance entered this construction. Exclusions and overlapping source-failure reasons are recorded in source_calendar_date_audit.csv and source_availability_audit.csv; counts are not additive. '
        'The candidate audit uses the union of physically observed source dates, not a synthetic trading grid; absence from both sources for all nine is not certified as a missing exchange session. '
        'Futures 259 dates and crypto 1,417 dates remain exactly unchanged and each is verified against all nine saved panels. '
        'This is not a balanced all-class 2015-2025 comparison.\n\n')
    review += policy.split('\n\n', 1)[1] + '\n\n'
    review += ('Sources: stocks/ETFs Bloomberg adjusted OHLC primary (CapChg=T, CshAdjNormal=T, CshAdjAbnormal=UNKNOWN), unadjusted robustness; First Rate RTH aggregates only validation/benchmark infrastructure. '
        'The 61 heuristic corporate-action flags stay diagnostic; no automatic primary window breaks. Futures use only unadjusted individual contracts selected for the whole trade date; no continuous prices. Crypto uses UTC daily aggregation and its verified common provider quote basis; formal currency remains UNKNOWN.\n\n'
        'Future outputs: bias, MAE, RMSE, failure/undefined rate and meaningful published/raw negative-estimate rate, overall and by class, tier and class x tier, in bps/relative price. HAC uncertainty is primary but lag and implementation remain pending methodological specification. Cross-fitted error modeling is robustness/diagnostic only.\n\n'
        'All tiers use 2024 calibration. Pre-2024 stock/ETF/crypto tier labels use future information and retain the look-ahead/ex-post classification limitation; futures comparison is conditional on its calibration year. No performance influenced selection. Supplementary histories are descriptive only. Futures/crypto estimator OHLC and benchmark share a source, creating mechanical dependence.\n\n'
        'FX stays in scope under the student-supplied professor instruction: official access blocked, no substitutes, continue completed classes, document the limitation if still inaccessible at submission; student reports no penalty for this source-access issue. The Step13 access audit is retained, not represented as a fresh access check.\n\n'
        'See remaining_pre_estimation_decisions.md for formula/window/raw-output policies, scheduled adjacency, HAC convention/dependence, summary weighting and negative-rate denominator, IMDX identity and FX resolution. These must be addressed before their relevant calculations. Old pilot-only universe descriptions and pending comparison-policy text are superseded by this global specification, without editing the earlier frozen artifacts.\n\n'
        'No raw data, provider Roll, CS, AR, EDGE, errors, performance rankings or hypothesis tests were computed or changed. No raw intraday files were opened. Protected documentation and prior frozen specifications are unchanged.\n')
    if (OUT / 'test_results.txt').exists():
        review += '\nFull-suite validation\n\n```text\n' + (OUT / 'test_results.txt').read_text(encoding='utf-8').strip() + '\n```\n'
    (OUT / 'step14_global_design_freeze_review.md').write_text(review, encoding='utf-8')
    assert before == protected_hashes(), 'Protected prior files changed'
    manifest = dict(status=spec['status'], input_sha256=inputs, protected_sha256=before,
        code_sha256={name: sha256(PROJECT / name) for name in ['src/global_design_freeze.py', 'tests/test_global_design_freeze.py']},
        raw_bloomberg_hashes_verified=len(raw), no_raw_intraday_reads=True,
        no_provider_benchmark_or_estimator_calculations=True,
        output_sha256={p.name: sha256(p) for p in OUT.iterdir() if p.suffix in ['.yaml', '.csv', '.md']})
    (OUT / 'run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(pd.DataFrame(audits).to_string(index=False))
    print(spec['status'])


if __name__ == '__main__':
    run()
