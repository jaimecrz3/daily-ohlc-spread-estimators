"""Generate Step 10.2 from saved Step-8 diagnostics and reviewed primary sources.

No raw workbook parsing, adjustment construction, provider benchmark reads,
estimator imports, estimator formulas or estimator-result selection.
"""
from pathlib import Path
import json
import re
import subprocess
import sys

import pandas as pd
import yaml

try:
    from .bloomberg_io import sha256, verify_hashes, require_verified
    from .daily_input_convention import (ADJUSTMENTS, common_source_plan,
        verified_source_selection, corporate_action_boundaries)
except ImportError:
    from bloomberg_io import sha256, verify_hashes, require_verified
    from daily_input_convention import (ADJUSTMENTS, common_source_plan,
        verified_source_selection, corporate_action_boundaries)

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / 'outputs/diagnostics/daily_input_freeze'
STEP8 = PROJECT / 'outputs/diagnostics/bloomberg_validation'
RAW = PROJECT / 'data/raw_bloomberg'
CS = 'https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2012.01729.x'
CS_NOTES = 'https://sites.nd.edu/scorwin/files/2019/08/Sample-SAS-Program-Description.pdf'
CS_CODE = 'https://sites.nd.edu/scorwin/files/2024/05/High_Low_Spread_Estimator_SAS_sample.pdf'
CS_APPENDIX = 'https://sites.nd.edu/scorwin/files/2019/11/Internet-Appendix_FINAL.pdf'
AR = 'https://academic.oup.com/rfs/article/30/12/4437/4047344'
EDGE = 'https://irf.fhnw.ch/bitstreams/e8c469d2-9c64-4004-8e87-53ee091f0cb1/download'
EDGE_REPO = 'https://github.com/eguidotti/bidask'
EDGE_CODE = 'https://raw.githubusercontent.com/eguidotti/bidask/main/python/bidask/edge.py'


def method_review():
    """Concise paraphrases; original-source rules are not automatically project rules."""
    return pd.DataFrame([
        dict(estimator='CS', original_source='Corwin and Schultz (2012), Journal of Finance',
            required_price_fields='HIGH, LOW; prior CLOSE for official overnight correction',
            adjacent_dates_windows='One-day and consecutive two-day ranges; daily estimates can be averaged over a month',
            missing_observations='Official sample replaces missing/bad H/L using retained prior good ranges',
            zero_range_nontrading='Official sample resets equal H/L using prior ranges and close; optional volume identifies nontrading',
            overnight_movements='Shift current H/L when prior close lies outside current range; explicit author procedure',
            negative_estimates='Official sample floors negative two-day spreads at zero before monthly averaging; raw and positive-only variants also shown',
            splits_distributions='Official input explicitly split-adjusted H/L/C; appendix includes a split-event application',
            adjusted_unadjusted_vendor_requirement='Split-adjusted input explicitly specified in author sample; no Bloomberg override prescription',
            not_specified='Normal versus abnormal cash-dividend vendor adjustment settings; a universal daily missing-grid policy',
            evidence_location='Publisher abstract; author program description steps 1-4; sample pages 1-3; appendix IA.II',
            source_urls=';'.join([CS, CS_NOTES, CS_CODE, CS_APPENDIX]),
            review_date='2026-10-14', source_access_note='Publisher full text was not accessible; preprocessing verified directly in official author implementation and original internet appendix'),
        dict(estimator='AR', original_source='Abdi and Ranaldo (2017), Review of Financial Studies',
            required_price_fields='CLOSE, HIGH, LOW (log prices)',
            adjacent_dates_windows='Close and high-low midpoints from adjacent days; averages over a month',
            missing_observations='Empirical section 3 retains prior H/L/C for nontrading or zero range; excludes incomplete estimator stock-months',
            zero_range_nontrading='Empirical carry-forward; simulation section 2.1 discards two-day inputs containing nontrading/zero-range days',
            overnight_movements='Model handles nontrading-period price movement without a CHL ad hoc overnight correction; empirical HL uses CS overnight correction',
            negative_estimates='Section 1.2 gives monthly and two-day zero corrections; empirical section 3 uses two-day correction',
            splits_distributions='Empirical section 3 explicitly excludes stock-months containing a split or enormous distribution',
            adjusted_unadjusted_vendor_requirement='No general Bloomberg adjusted/unadjusted prescription established by the reviewed source',
            not_specified='Bloomberg capital/normal/abnormal settings; project calendar or daily window length; empirical exclusion is not a universal raw-price requirement',
            evidence_location='Sections 1.1-1.2, 2.1, 3; equations 9-11', source_urls=AR,
            review_date='2026-10-14', source_access_note='Published article full text reviewed'),
        dict(estimator='EDGE', original_source='Ardia, Guidotti and Kroencke (2024), Journal of Financial Economics',
            required_price_fields='OPEN, HIGH, LOW, CLOSE (positive prices, sorted timestamps)',
            adjacent_dates_windows='Lagged previous-period inputs inside a sample/window; official function requires at least three observations',
            missing_observations='Official FAQ supports missingness and recommends a regular grid; paper section 5.1 drops missing H/L/C and malformed-range empirical rows',
            zero_range_nontrading='Paper indicator uses H=L=previous close; official code returns missing if fewer than two active periods or zero opening/closing probabilities',
            overnight_movements='Paper and implementation use close-to-open components explicitly; no CS-style input shifting routine',
            negative_estimates='Official function defaults to absolute-root output with signed option; FAQ discusses signed then zero correction; paper empirical negatives set to zero',
            splits_distributions='No explicit corporate-action input convention established in reviewed paper or official implementation',
            adjusted_unadjusted_vendor_requirement='No explicit adjusted/unadjusted vendor-price requirement established',
            not_specified='Bloomberg overrides; split/dividend reconstruction policy; exchange-specific missing-day calendar',
            evidence_location='Paper sections 3 and 5.1; official FAQ; Python edge.py lines 28-70 and 94-100',
            source_urls=';'.join([EDGE, EDGE_REPO, EDGE_CODE]), review_date='2026-10-14',
            source_access_note='Published author-institution copy and official repository reviewed; repository main URLs are mutable; review is dated'),
    ])


def candidate_spec(primary, robustness, boundaries):
    return dict(
        status='corrected_candidate_approved', step='10.2.1', review_date='2026-10-14',
        scope='Selected 18 stocks/ETFs only; futures/crypto inputs not frozen by this review',
        recommendation='A: existing Bloomberg adjusted OHLC primary, existing unadjusted OHLC robustness',
        primary_source=primary,
        primary_adjustment_convention=dict(**{**ADJUSTMENTS['adjusted'], 'CshAdjAbnormal': 'UNKNOWN'},
            description='Use acquired values unchanged; capital changes and normal cash dividends explicitly adjusted; abnormal treatment unknown'),
        robustness_source=robustness,
        common_source_enforcement=dict(primary=common_source_plan(),
            robustness=common_source_plan('robustness'), per_estimator_convention_switching=False),
        required_fields_policy=dict(CS=['PX_HIGH', 'PX_LOW', 'PX_LAST'],
            AR=['PX_HIGH', 'PX_LOW', 'PX_LAST'], EDGE=['PX_OPEN', 'PX_HIGH', 'PX_LOW', 'PX_LAST'],
            CS_close_role='Prior close needed for official overnight correction',
            window_admission='Required-field validity AND validated calendar/date adjacency; field flags alone never admit a window'),
        capital_change_policy='Primary uses saved CapChg=T unchanged. No automatic heuristic or verified-split break in adjusted inputs; impose an event boundary only when independently verified and methodologically required. Unadjusted robustness explicitly breaks the saved verified SNDL split edge.',
        normal_dividend_policy='Primary uses saved CshAdjNormal=T; robustness F. Accept vendor-acquired convention unchanged; no additional dividend adjustment.',
        abnormal_dividend_policy=dict(status='unknown_not_explicitly_set',
            primary_use='documented limitation; not a blocker to using this immutable acquisition as a precisely identified source',
            forbidden_claim='Do not label this as explicitly all-dividend adjusted or infer a Bloomberg default',
            setting='UNKNOWN',
            sensitivity='Existing unadjusted source with explicit verified split/capital-change breaks only; cannot isolate abnormal from normal/capital adjustment effects',
            unresolved_risk='Undetected special distributions are possible; event verification alone does not automatically require a primary break; document methodological necessity first',
            reextraction_required=False),
        partial_row_policy='Keep physical rows, raw tokens and source errors; no OHLC imputation or carry-forward. Each estimator window must satisfy its own required fields plus valid calendar/date adjacency; no blanket complete-OHLC gate for CS/AR. Missing volume or quotes alone does not gate price inputs.',
        missing_day_policy='Preserve missing/partial sessions and source-only dates without compression, carry-forward, interpolation or OHLC synthesis; no daily grid materialized here.',
        author_preprocessing_robustness='Method-specific author carry-forward/range replacement and other empirical preprocessing remain possible later explicitly authorized robustness replications only; not the common primary horse-race policy and not implemented here.',
        calendar_gap_policy=dict(
            ordering='Stable asset/date/source_row ordering; do not drop invalid rows before lag construction',
            adjacency='Future lags use consecutive scheduled sessions, not consecutive available rows; known missing scheduled sessions break chains',
            weekends_holidays='Do not treat weekends/holidays as missing trading days; require a validated listed-line session calendar before confirming adjacency across closures',
            unresolved_calendar='No new exchange calendar frozen here. Unknown adjacency must be flagged and not silently treated as consecutive.',
            edge_grid='At later implementation, retain NaN placeholders on an explicitly validated regular session grid as an analysis view; no invented OHLC or inserted intraday bars'),
        corporate_action_boundary_policy=dict(
            evidence='Reuse Step-8 corporate_action_checks.csv; do not rerun factor detection',
            candidate_threshold='Existing Step-8 >=1% adjacent observed close adjustment-factor change; audit screen only, not event identification or performance tuning',
            verified_example='SNDL 2022-07-26 saved acquisition reverse-split checks',
            primary_adjusted='All 61 empirical flags remain diagnostics only. No automatic exclusion; only independently verified AND methodologically required event boundaries may break primary windows.',
            unadjusted_robustness='Explicitly break the saved verified SNDL split; future verified split/capital boundaries may be broken with documented evidence. Heuristic flags alone never break windows.',
            primary_breaks_currently_imposed=0,
            robustness_verified_breaks_currently_imposed=int(boundaries.robustness_break_cross_date_window.sum()),
            incoming_edge_rule='An explicitly imposed event boundary is an incoming edge to the first post-event session; diagnostic candidates do not imply a break.',
            missing_event_session='If an explicitly imposed boundary date is missing, the first later observation receives the applicable role-specific break flag',
            exclusion_scope='Preserve source rows and diagnostic flags; no automatic event-month deletion or heuristic exclusion; future primary breaks require verification and a recorded methodological reason',
            identity='Factor candidates remain unverified; no inferred split/dividend labels',
            diagnostic_candidate_count=len(boundaries),
            general_guarantee='No complete corporate-action ledger or blanket price-continuity guarantee is inferred from heuristic flags. Use saved vendor capital adjustment; additional primary event breaks require verification and methodological necessity.'),
        source_comparability_role='First Rate split+dividend adjusted RTH daily aggregates are validation only, never the primary stock/ETF estimator source; no vendor session/adjustment equivalence assumed',
        zero_range_policy='Retain and flag; no author-style range replacement. Future estimator-specific computability rules require a separate numerical implementation review.',
        negative_estimate_policy='Original-source policies documented only; project CS/AR/EDGE output treatment not frozen or executed here',
        benchmark_link='benchmark_final_spec.yaml unchanged; Roll two-pair mathematical minimum does not define comparison eligibility',
        no_estimator_result_dependency=True, estimator_values_calculated=False,
        candidate_blocked=False, blocker_reason=None,
        limitations=['Abnormal-dividend behavior is unspecified, not resolved by source selection',
            'IMDX/OCX stable-ID continuity unresolved; no manual historical stitching',
            'Bloomberg EOD/session/auction timing and First Rate equivalence not certified',
            'Volume adjustment differences are separate from price-only input availability',
            'Scheduled-session calendar, window lengths, estimator output treatment and final analytical eligibility remain separate approvals',
            'This candidate differs from original empirical imputation, split-month exclusion and aggregation conventions'])


def write_report(spec, methods, actions, summaries):
    key = actions.loc[actions.asset.isin(['SNDL', 'IMDX', 'SCHM', 'XPO'])]
    display = key[['asset', 'date', 'unadjusted_close', 'adjusted_close',
        'previous_observed_factor', 'adjustment_factor', 'identity_status',
        'primary_break_cross_date_window', 'robustness_break_cross_date_window']]
    table = '| ' + ' | '.join(display.columns) + ' |\n'
    table += '| ' + ' | '.join(['---'] * len(display.columns)) + ' |\n'
    for row in display.fillna('').itertuples(index=False, name=None):
        table += '| ' + ' | '.join(str(value) for value in row) + ' |\n'
    text = '''# Step 10.2.1 approved daily OHLC input convention

The daily input convention is frozen by the user's Step 10.2.1 approval: existing Bloomberg adjusted OHLC is the common primary source for CS, AR and EDGE; existing unadjusted Bloomberg is robustness only. The final machine-readable artifact is daily_input_final_spec.yaml. This applies to the 18 selected stocks/ETFs. No estimator implementation or results were used to select it. Step 10.2's automatic exclusions at 61 heuristic flags are corrected: primary event breaks require independent verification AND methodological necessity.

## 1. Explicit original-source and official implementation rules

The machine-readable estimator_source_method_review.csv records each field requirement, adjacent-date dependence, missing/zero-range/overnight/negative treatment, corporate-action evidence, source location and silence. These author choices are recorded without automatically adopting them.

Corwin–Schultz derive the estimator from one- and two-day high/low ranges. Their official sample specifies **split-adjusted H/L/C**, prior-range replacement for bad/missing/zero-range data, a prior-close overnight correction, negative two-day zero correction, and at least 12 monthly observations. The range-shifting overnight correction is different from vendor corporate-action adjustment. No Bloomberg normal/abnormal-dividend settings are prescribed. Publisher full text could not be accessed; these preprocessing details were checked directly in the original internet appendix and official author implementation. [Paper](CS_URL), [author program description](CS_NOTES_URL), [sample program](CS_CODE_URL), [original appendix](CS_APPENDIX_URL).

Abdi–Ranaldo use adjacent-day close/high/low inputs. Their empirical section carries prior prices on nontrading/zero-range days, uses two-day negative correction, and **discards stock-months containing splits or enormous distributions**; their HL comparator uses CS overnight and two-day corrections. Simulations instead discard nontrading/zero-range two-day inputs. Their model handles nontrading-period movement without CHL overnight shifting. They do not prescribe Bloomberg adjusted versus unadjusted settings. [Published article, sections 1–3](AR_URL).

EDGE combines OHLC with lagged previous-period prices and close-to-open components. Its paper removes missing H/L/C or malformed empirical daily rows. The official implementation supports NaNs without compressing the grid; its FAQ recommends regular spacing and discusses absolute/signed outputs. Its zero-activity/probability checks can yield undefined output. Neither reviewed paper nor implementation establishes a split/dividend vendor convention. No corporate-action rule is inferred from that silence. [Paper, sections 3 and 5.1](EDGE_URL), [official FAQ](EDGE_REPO_URL), [official implementation](EDGE_CODE_URL). The empirical paper and current implementation are distinct evidence, particularly for missingness.

## 2. Facts from existing Bloomberg acquisition

All raw files remain in their finalized manifest paths. Formula lineage is evidence only; immutable values-only acquisitions provide prices. Unadjusted has CapChg=F, CshAdjNormal=F, CshAdjAbnormal=F. Adjusted has CapChg=T and CshAdjNormal=T, with CshAdjAbnormal **not explicitly set**. We identify the precise file and hashes, rather than claiming explicitly all-dividend adjustment.

Only existing Step-8 diagnostics are used for corporate-action impact. No adjustment-factor detector, raw ingestion or price comparison is rerun. The existing factor-change screen is >=1%; its rows are candidates, not independently verified events.

ACTION_TABLE

SNDL's saved 1-for-10 reverse-split checks show raw close 0.2974 on 2022-07-25 then 2.28 on 2022-07-26, while the adjusted closes are 2.974 then 2.28. Thus adjustment removes the tenfold share-scale component, not the real daily market movement. IMDX's factor changes from 20 to 1 on 2023-07-25; SCHM's from approximately 0.324025 to 0.972074 on 2024-10-11; XPO's from approximately 0.345662 to 0.594125 on 2021-08-02 and from 0.594124 to 1 on 2022-11-01. Their event identities are not certified by these numbers. All 61 existing flags remain diagnostics; only SNDL has saved split verification. SNDL's verified split breaks the unadjusted robustness edge; it does not automatically break the adjusted primary edge.

## 3. Project-specific frozen choices

Use the adjusted acquisition unchanged for CS/AR/EDGE; use unadjusted unchanged for a separate common robustness run. No third acquisition, custom adjustment factors or per-estimator convention switching. Option B needs comprehensive independently verified action boundaries to protect unadjusted windows; the existing candidate screen is not a complete action ledger. Option C cannot supply a split-only or special-dividend-only transformation reproducibly from these saved files without inventing decomposed factors. Option A provides explicit vendor capital adjustment and normal-dividend smoothing before cross-date calculations, independent of performance.

Treat capital changes separately from normal cash dividends: primary T/T and robustness F/F. Special/abnormal dividends remain **UNKNOWN**, a documented acquisition limitation rather than a blocker to primary use. Do not infer the Bloomberg default. Unadjusted robustness cannot isolate abnormal-dividend effects from normal/capital changes. No third acquisition or invented adjustments are created.

PRIMARY ADJUSTED: do not break windows merely because any of the 61 heuristic flags exists. Retain every flag as diagnostic evidence. Only impose an event boundary when independently verified and methodologically required, with both evidence and reason recorded. No primary event breaks are currently imposed; saved SNDL verification alone does not require one in the adjusted series. UNADJUSTED ROBUSTNESS: explicitly break the saved verified SNDL split on 2022-07-26; additional verified split/capital-change breaks may be recorded explicitly. Unverified heuristics never become verified events or automatic exclusions in either role. If an imposed event date is missing, the first later observation still receives the appropriate role-specific break. Source rows remain present.

The frozen common primary policy is no OHLC imputation, no carry-forward and no compression of missing sessions. Preserve partial rows, cached source errors, source-only dates, duplicates and invalid/zero-range flags. Each future estimator window must satisfy that estimator's required fields AND valid calendar/date adjacency. A missing OPEN does not by itself invalidate otherwise valid H/L/C for CS/AR; EDGE requires OPEN as well. Full-OHLC availability remains a diagnostic, not a universal primary gate. Missing volume or bid/ask alone does not gate price-only inputs. The old OHLCV daily_input_valid flag is not estimator eligibility. Daily quotes are not the intraday benchmark.

Missing scheduled sessions must remain explicit on a future validated session-calendar analysis grid, with NaN prices rather than invented observations. Weekends and holidays are not missing sessions. No new calendar/grid is built here; when adjacency is unknown, flag it and prohibit silently treating consecutive available rows as consecutive sessions. EDGE's regular-grid recommendation is preserved without filling any intraday bars. Calendar integration and window lengths remain separate implementation decisions. A common available-field flag is not final horse-race eligibility.

This differs explicitly from the Abdi–Ranaldo empirical carry-forward of prior H/L/C on nontrading/zero-range days and its stock-month split/distribution exclusions. Method-specific author preprocessing is preserved as a possible later, separately authorized robustness replication, not the common primary horse-race policy; no such replication is implemented or executed here. Author negative-estimate corrections and monthly sampling thresholds remain evidence only. Roll's final formula and two-pair computability rule are unchanged and do not determine source selection or comparison eligibility.

First Rate split+dividend adjusted 09:30–16:00 aggregates remain local validation only. No source equivalence is claimed or selected based on closer prices. No new futures or crypto source convention is frozen.

## 4. Remaining limitations outside this approval

The daily source/convention and common missing-data policy are now frozen in daily_input_final_spec.yaml; the corrected candidate records its approval and points to that final artifact. Abnormal-dividend treatment remains unknown. Scheduled-session calendar integration, IMDX/OCX stable-ID continuity, EOD/session/auction differences, undocumented events and volume-scale comparability remain limitations. Window lengths, estimator negative/undefined output treatment and final analytical eligibility are outside this freeze. README.md, design_decisions.md, data_manifest.csv, Step-8 outputs, Roll final specification and universe selections remain unchanged.

No CS, AR, EDGE or provider Roll benchmark values, estimator performance or terminal extraction were calculated. Official code was read as evidence only and was neither installed nor executed.
'''
    for token, value in [('CS_NOTES_URL', CS_NOTES), ('CS_CODE_URL', CS_CODE),
        ('CS_APPENDIX_URL', CS_APPENDIX), ('CS_URL', CS), ('AR_URL', AR),
        ('EDGE_CODE_URL', EDGE_CODE), ('EDGE_REPO_URL', EDGE_REPO), ('EDGE_URL', EDGE)]:
        text = text.replace(token, value)
    text = text.replace('ACTION_TABLE', table)
    summary = summaries.loc[summaries.convention.eq('adjusted')]
    text += '\nExisting adjusted acquisition: ' + str(int(summary.total_returned_rows.sum()))
    text += ' returned rows for 18 securities; ' + str(int((summary.total_returned_rows-summary.complete_ohlc_days).sum()))
    text += ' rows lack complete OHLC. Counts describe saved Step-8 ingestion only; no missing dates were synthesized.\n'
    (OUT / 'daily_input_convention_review.md').write_text(text, encoding='utf-8')


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    # Protect every input artifact and explicitly prohibited document, not just raw bytes.
    protected = [RAW / 'sha256_manifest.csv', *STEP8.glob('*'),
        * (PROJECT / 'data/interim/bloomberg').glob('*.parquet'),
        PROJECT / 'outputs/diagnostics/benchmark_freeze/benchmark_final_spec.yaml',
        PROJECT / 'outputs/diagnostics/final_universe/selected_stocks_etfs.csv',
        PROJECT / 'outputs/diagnostics/final_universe/futures_crypto/selected_futures.csv',
        PROJECT / 'outputs/diagnostics/final_universe/futures_crypto/selected_crypto.csv']
    for name in ('README.md', 'design_decisions.md', 'data_manifest.csv'):
        protected += list(PROJECT.glob(name)) + list((PROJECT / 'manifests').glob(name))
    protected = [p for p in protected if p.is_file()]
    before = {p.relative_to(PROJECT).as_posix(): sha256(p) for p in protected}
    initial, manifest = verify_hashes(RAW)
    require_verified(initial)
    assert len(manifest) == 11
    initial.to_csv(OUT / 'raw_hash_verification.csv', index=False)
    selected = pd.read_csv(PROJECT / 'outputs/diagnostics/final_universe/selected_stocks_etfs.csv')
    assert len(selected) == 18 and selected.asset.nunique() == 18
    step8_manifest = json.loads((STEP8 / 'run_manifest.json').read_text(encoding='utf-8'))
    # Step 10.1 changed only raw manifest paths: verify each Step-8 normalized source hash
    # against the current content hashes, not the obsolete Step-8 manifest CSV hash.
    for path, expected in {**step8_manifest['derived_sha256'], **step8_manifest['parquet_sha256']}.items():
        assert sha256(PROJECT / path) == expected, 'Changed Step-8 artifact: ' + path
    log = pd.read_csv(PROJECT / 'manifests/bloomberg_source_log.csv')
    by_basename = {Path(row.file_name).name: row.sha256 for row in manifest.itertuples()}
    assert log.apply(lambda row: by_basename[Path(row.file_name).name] == row.file_hash, axis=1).all()
    primary, robustness = verified_source_selection(RAW), verified_source_selection(RAW, 'robustness')
    lineage = pd.read_csv(STEP8 / 'acquisition_formula_lineage.csv')
    for convention in ('adjusted', 'unadjusted'):
        group = lineage.loc[lineage.convention.eq(convention)]
        assert set(group.asset) == set(selected.asset) and len(group) == 18
        for override, expected in ADJUSTMENTS[convention].items():
            actual = group.overrides.str.contains(override + '=', regex=False)
            if expected == 'not_explicitly_set':
                assert not actual.any()
            else:
                assert group.overrides.str.contains(override + '=' + expected, regex=False).all()
    checks = pd.read_csv(STEP8 / 'corporate_action_checks.csv')
    boundaries = corporate_action_boundaries(checks)
    methods = method_review()
    methods.to_csv(OUT / 'estimator_source_method_review.csv', index=False)
    actions = checks.copy()
    actions['date'] = pd.to_datetime(actions.date)
    actions = actions.merge(boundaries[['asset', 'date', 'identity_status',
        'verified_split', 'primary_break_cross_date_window',
        'robustness_break_cross_date_window', 'break_cross_date_window']], on=['asset', 'date'], how='left', validate='many_to_one')
    actions['identity_status'] = actions.identity_status.fillna('saved_pre_split_scaling_check; not_event_boundary')
    actions['verified_split'] = actions.verified_split.fillna(False).astype(bool)
    for column in ('primary_break_cross_date_window', 'robustness_break_cross_date_window', 'break_cross_date_window'):
        actions[column] = actions[column].fillna(False).astype(bool)
    actions['break_cross_date_window_scope'] = 'primary compatibility alias; heuristic diagnostics never imply exclusion'
    actions['evidence_role'] = 'existing_Step8_source_diagnostic_only'
    actions['primary_convention'] = 'adjusted'
    actions['robustness_convention'] = 'unadjusted'
    actions.to_csv(OUT / 'corporate_action_input_review.csv', index=False)
    boundaries.to_csv(OUT / 'corporate_action_boundaries.csv', index=False)
    spec = candidate_spec(primary, robustness, boundaries)
    spec['approval'] = dict(request='Step 10.2.1', date='2026-10-14',
        final_artifact='daily_input_final_spec.yaml',
        scope='Common daily source, corporate-action boundary policy and method-specific required-field missing-data policy')
    (OUT / 'daily_input_freeze_candidate.yaml').write_text(yaml.safe_dump(spec, sort_keys=False), encoding='utf-8')
    write_report(spec, methods, actions, pd.read_csv(STEP8 / 'daily_ingestion_summary.csv'))
    result = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
        cwd=PROJECT, capture_output=True, text=True)
    tests = result.stdout + result.stderr
    (OUT / 'test_results.txt').write_text(tests, encoding='utf-8')
    assert result.returncode == 0, tests
    count = int(re.search(r'Ran (\d+) tests', tests).group(1))
    final, _ = verify_hashes(RAW)
    require_verified(final)
    final.to_csv(OUT / 'raw_hash_verification_after.csv', index=False)
    assert before == {p.relative_to(PROJECT).as_posix(): sha256(p) for p in protected}
    final_spec = dict(spec, status='daily_input_convention_frozen',
        frozen_for_future_estimator_implementation=True)
    (OUT / 'daily_input_final_spec.yaml').write_text(yaml.safe_dump(final_spec, sort_keys=False), encoding='utf-8')
    report = OUT / 'daily_input_convention_review.md'
    with report.open('a', encoding='utf-8') as stream:
        stream.write(f'\nValidation: {count} tests passed, 0 failed; all 11 raw hashes/sizes verified before and after. All protected inputs and documents unchanged. Reproduce with src/daily_input_freeze_review.py.\n')
    run_manifest = dict(status=final_spec['status'], step='10.2.1', tests_passed=count,
        tests_failed=0, estimator_values_calculated=False, performance_calculated=False,
        provider_benchmark_values_calculated=False, raw_writes=0, workbook_reads=0,
        first_rate_raw_reads=0, corporate_action_detection_rerun=False,
        corporate_action_boundaries=len(boundaries), boundary_identity_verified=int(boundaries.verified_split.sum()),
        corporate_action_flag_role='diagnostic candidates, not automatic exclusions',
        primary_event_breaks=int(boundaries.primary_break_cross_date_window.sum()),
        robustness_verified_event_breaks=int(boundaries.robustness_break_cross_date_window.sum()),
        raw_files_verified=len(final), protected_inputs_unchanged=True,
        candidate_blocked=False, protected_input_sha256=before,
        code_sha256={name: sha256(PROJECT / name) for name in
            ['src/daily_input_convention.py', 'src/daily_input_freeze_review.py', 'tests/test_daily_input_convention.py']},
        output_sha256={p.name: sha256(p) for p in OUT.iterdir() if p.is_file() and p.name != 'run_manifest.json'})
    (OUT / 'run_manifest.json').write_text(json.dumps(run_manifest, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in run_manifest.items() if not k.endswith('sha256')}, indent=2))


if __name__ == '__main__':
    run()
