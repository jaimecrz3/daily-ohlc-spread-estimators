"""Step 7A provisional stocks/ETFs sample and proposed Bloomberg plan.

Run: .venv/Scripts/python.exe -B src/final_universe.py
Reads existing eligibility/ranking/coverage diagnostics only. No provider reads,
Bloomberg requests, benchmark inputs, or estimator calculations.
"""
from fractions import Fraction
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
INPUT = PROJECT / 'outputs/diagnostics/universe_selection'
OUT = PROJECT / 'outputs/diagnostics/final_universe'
CLASSES = ('stocks', 'etfs')
TIERS = ('LOW', 'MEDIUM', 'HIGH')
TARGETS = (Fraction(1, 4), Fraction(1, 2), Fraction(3, 4))
KEYS = ['asset_class', 'asset']
DAILY_FIELDS = ('PX_OPEN', 'PX_HIGH', 'PX_LOW', 'PX_LAST', 'PX_VOLUME', 'PX_BID', 'PX_ASK')
REFERENCE_FIELDS = ('NAME', 'ID_BB_GLOBAL', 'ID_ISIN', 'ID_CUSIP', 'TICKER_AND_EXCH_CODE', 'CRNCY')
INPUT_FILES = ('liquidity_ranking.csv', 'eligible_assets.csv', 'excluded_assets.csv',
               'candidate_liquidity_diagnostics.csv', 'file_scan_audit.csv')


def eligible_ranking(ranking, eligible, candidates, scans, exclusions):
    """Cross-check existing eligibility; retain all eligible ranked equities.

    Security-name, identifier and full-window coverage review flags are added
    after the ranking is validated, and never become selection criteria.
    Allowlisted columns prevent benchmark/estimator data entering this table.
    """
    allowed = KEYS + ['file', 'liquidity_tier', 'liquidity_rank', 'liquidity_measure',
        'observed_2024_days', 'median_bars_per_observed_day', 'zero_volume_rows']
    full = ranking.loc[ranking.asset_class.isin(CLASSES), allowed].copy()
    if full.duplicated(KEYS).any():
        raise ValueError('Duplicate ranked asset/class keys')
    metadata_cols = KEYS + ['metadata_eligible', 'local_file_exists', 'in_computational_pool',
        'raw_coverage_validation', 'provider_name', 'provider_first_date', 'provider_last_date',
        'reference_validation', 'quote_currency']
    full = full.merge(eligible[metadata_cols], on=KEYS, how='left', validate='one_to_one')
    validation_cols = KEYS + ['passes_liquidity_days', 'ranking_eligible']
    full = full.merge(candidates[validation_cols], on=KEYS, how='left', validate='one_to_one')
    coverage_cols = KEYS + ['first_observed_study_date', 'last_observed_study_date', 'observed_study_years']
    full = full.merge(scans[coverage_cols], on=KEYS, how='left', validate='one_to_one')
    flags = ['metadata_eligible', 'local_file_exists', 'in_computational_pool', 'passes_liquidity_days', 'ranking_eligible']
    valid = full[flags].eq(True).all(axis=1) & full.raw_coverage_validation.eq('verified_endpoint_span_and_2024_presence')
    valid &= full.observed_2024_days.ge(200) & full.liquidity_tier.isin(TIERS)
    valid &= np.isfinite(full.liquidity_measure) & full.liquidity_measure.ge(0)
    valid &= full.first_observed_study_date.notna() & full.last_observed_study_date.notna()
    excluded_keys = set(zip(exclusions.asset_class, exclusions.asset))
    valid &= pd.Series([(cls, asset) not in excluded_keys for cls, asset in zip(full.asset_class, full.asset)], index=full.index)
    if not valid.all():
        raise ValueError('Ranking/eligibility inconsistency: ' + ', '.join(full.loc[~valid, 'asset']))
    full = full.rename(columns={'liquidity_rank': 'liquidity_rank_within_class',
        'liquidity_measure': 'liquidity_measure_2024',
        'median_bars_per_observed_day': 'median_bars_per_2024_day',
        'zero_volume_rows': 'zero_volume_rows_2024',
        'first_observed_study_date': 'first_observed_date',
        'last_observed_study_date': 'last_observed_date'})
    full['first_observed_date'] = pd.to_datetime(full.first_observed_date).dt.date
    full['last_observed_date'] = pd.to_datetime(full.last_observed_date).dt.date
    full['security_type_review_required'] = True
    full['bloomberg_identifier_validation_pending'] = True
    full['expected_bloomberg_security_identifier_placeholder'] = full.asset + ' <EXCHANGE_CODE_PENDING> Equity'
    full['identifier_status'] = 'unvalidated_placeholder; not executable'
    full['coverage_basis'] = 'raw observed dates clipped to 2015-2025; endpoint/year span only, not complete session coverage'
    full['coverage_unbalanced_2015_2025'] = False
    for cls in CLASSES:
        group = full.loc[full.asset_class.eq(cls)]
        # Empirical observed study boundaries from the previously scanned pool;
        # never invent a bar/date on 2015-01-01 or assume an exchange calendar.
        reference = scans.loc[scans.asset_class.eq(cls)]
        begin = pd.to_datetime(reference.first_observed_study_date).min().date()
        end = pd.to_datetime(reference.last_observed_study_date).max().date()
        full.loc[group.index, 'coverage_unbalanced_2015_2025'] = (
            group.first_observed_date.gt(begin) | group.last_observed_date.lt(end)
            | group.observed_study_years.lt(11))
    full['security_type_review_note'] = 'Provider folder/name does not certify security type; validate Bloomberg reference classification and exact listed line'
    full['coverage_review_note'] = np.where(full.coverage_unbalanced_2015_2025,
        'unbalanced local study span; retained without replacement',
        'observed study endpoints/years span the window; complete session/minute coverage not certified')
    return full


def select_tier_quantiles(full):
    """Nearest one-based rank to 1 + q*(n-1); exact ties by ticker.

    No interpolation of liquidity values. Exact rational distances avoid rounding
    half-rank ties. Both equal-liquidity ordering and target-distance ties use
    alphabetical tickers. Fail rather than silently replace duplicate picks.
    """
    groups, selected = [], []
    for cls in CLASSES:
        for tier in TIERS:
            group = full.loc[full.asset_class.eq(cls) & full.liquidity_tier.eq(tier)].sort_values(
                ['liquidity_measure_2024', 'asset'], kind='stable').reset_index(drop=True)
            if len(group) < 3:
                raise ValueError(f'Insufficient eligible candidates: {cls}/{tier}')
            group['liquidity_rank_within_tier'] = np.arange(1, len(group) + 1)
            group['tier_candidate_count'] = len(group)
            group['selected'] = False
            group['selection_quantile_target'] = np.nan
            group['selection_target_rank'] = np.nan
            group['selection_rank_distance'] = np.nan
            group['selection_reason'] = 'eligible ranked tier member; not nearest to a selected quantile-rank target'
            chosen = []
            for q in TARGETS:
                target = 1 + q * (len(group) - 1)
                index = min(range(len(group)), key=lambda i: (abs(Fraction(i + 1) - target), group.iloc[i].asset))
                if index in chosen:
                    raise ValueError('Quantile targets do not yield three distinct securities; no silent replacement')
                chosen.append(index)
                group.loc[index, 'selected'] = True
                group.loc[index, 'selection_quantile_target'] = float(q)
                group.loc[index, 'selection_target_rank'] = float(target)
                group.loc[index, 'selection_rank_distance'] = float(abs(Fraction(index + 1) - target))
                group.loc[index, 'selection_reason'] = f'nearest actual rank to {float(q):.2f} target 1+q*(n-1); alphabetical ticker resolves exact ties'
            groups.append(group)
            selected.append(group.loc[chosen])
    return pd.concat(selected, ignore_index=True), pd.concat(groups, ignore_index=True)


def bloomberg_plan(selected, local_daily_assets):
    """Proposed requests, with placeholders and unresolved conventions explicit."""
    equivalents = dict(zip(DAILY_FIELDS[:5], ['open', 'high', 'low', 'close', 'volume']))
    reference_equivalents = {'NAME': 'provider_name (unvalidated)',
        'TICKER_AND_EXCH_CODE': 'asset (ticker only; exchange unavailable)',
        'CRNCY': 'quote_currency (provider-class assumption; unvalidated)'}
    rows = []
    for security in selected.itertuples():
        local_exists = (security.asset_class, security.asset) in local_daily_assets
        for field in DAILY_FIELDS + REFERENCE_FIELDS:
            daily = field in DAILY_FIELDS
            ohlcv = field in equivalents
            quote = field in {'PX_BID', 'PX_ASK'}
            validation = 'Validate exact ticker/exchange/listed security, FIGI, security type, currency and historical ticker/issuer continuity.'
            if ohlcv:
                validation += ' Reconcile split/dividend and other corporate-action adjustments, daily session/bar-date conventions and volume units/scaling before comparing with local aggregates; no equivalence or adjustment convention frozen.'
                purpose = 'Acquire daily OHLCV; compare with First Rate daily aggregate after adjustment/session reconciliation'
                availability = 'materialized Step-6 pilot aggregate' if local_exists else 'validated Step-6 aggregation pipeline exists; this selected asset daily OHLCV is not yet materialized'
            elif quote:
                purpose = 'Bloomberg daily quote diagnostic; PX_BID/PX_ASK are not the intraday benchmark'
                validation += ' Validate quote observation time, quote type, stale/missing quotes and units; never treat these as intraday quotes or the Roll benchmark.'
                availability = 'no local daily bid/ask equivalent'
            else:
                purpose = 'Validate provider/Bloomberg security identity and reference metadata; current BDP snapshot does not establish historical reference values'
                validation += ' Record reference retrieval date; BDP is a reference snapshot, not a 2015-2025 historical reference pull.'
                if field == 'ID_CUSIP':
                    validation += ' Request where applicable; document unavailable/not-applicable status without substituting another security.'
                availability = 'provider metadata for comparison only; Bloomberg reference validation pending'
            rows.append(dict(asset=security.asset, asset_class=security.asset_class,
                liquidity_tier=security.liquidity_tier,
                expected_bloomberg_security_identifier_placeholder=security.expected_bloomberg_security_identifier_placeholder,
                terminal_function='BDH' if daily else 'BDP', field=field,
                frequency='DAILY' if daily else 'REFERENCE_SNAPSHOT',
                start='2015-01-01', end='2025-12-31',
                date_range_applies_to_request=daily,
                date_range_note='inclusive daily request window' if daily else 'study context only; BDP has no historical start/end request here',
                purpose=purpose,
                equivalent_local_field=equivalents.get(field, reference_equivalents.get(field, 'none')),
                local_source_role='local_daily_validation' if ohlcv else 'none' if quote else 'provider_metadata_reference',
                local_validation_availability=availability,
                validation_required=validation,
                adjustment_convention='unresolved; no BDH adjustment override approved' if daily else 'not applicable',
                acquisition_status='proposed_only; identifier validation required; no extraction performed',
                applicability='where applicable' if field == 'ID_CUSIP' else 'required'))
    return pd.DataFrame(rows)


def markdown(table):
    lines = ['| ' + ' | '.join(table.columns) + ' |', '| ' + ' | '.join(['---'] * len(table.columns)) + ' |']
    for values in table.itertuples(index=False, name=None):
        lines.append('| ' + ' | '.join('NA' if pd.isna(v) else f'{v:,.2f}' if isinstance(v, float) else str(v).replace('|', '/') for v in values) + ' |')
    return '\n'.join(lines)


def run(input_dir=INPUT, out=OUT):
    inputs, hashes = {}, {}
    for name in INPUT_FILES:
        path = input_dir / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        inputs[name] = pd.read_csv(path)
    full = eligible_ranking(inputs['liquidity_ranking.csv'], inputs['eligible_assets.csv'],
        inputs['candidate_liquidity_diagnostics.csv'], inputs['file_scan_audit.csv'], inputs['excluded_assets.csv'])
    selected, audit = select_tier_quantiles(full)
    local_path = PROJECT / 'outputs/diagnostics/daily_aggregation/daily_ohlcv_pilot.csv'
    local = pd.read_csv(local_path, usecols=KEYS)
    local_keys = set(zip(local.asset_class, local.asset))
    plan = bloomberg_plan(selected, local_keys)
    assert len(selected) == 18 and selected.groupby(['asset_class', 'liquidity_tier']).size().eq(3).all()
    assert len(plan) == 18 * (len(DAILY_FIELDS) + len(REFERENCE_FIELDS))
    for name, before in hashes.items():
        if hashlib.sha256((input_dir / name).read_bytes()).hexdigest() != before:
            raise RuntimeError('Input changed during final selection')
    out.mkdir(parents=True, exist_ok=True)
    selected.to_csv(out / 'selected_stocks_etfs.csv', index=False)
    audit.to_csv(out / 'selection_audit.csv', index=False)
    plan.to_csv(out / 'bloomberg_pull_plan.csv', index=False)
    columns = ['asset', 'liquidity_tier', 'liquidity_measure_2024', 'liquidity_rank_within_tier',
        'selection_quantile_target', 'first_observed_date', 'last_observed_date', 'coverage_unbalanced_2015_2025']
    report = '# Provisional final stocks/ETFs universe and Bloomberg acquisition plan\n\n'
    report += 'Selection is frozen provisionally by the specified liquidity ranks. Security-type/identifier and historical coverage reviews are flags; no selected security was replaced.\n\n'
    report += 'Within each existing tier, sort ascending by the existing 2024 median liquidity measure, ticker tie break. For q = 0.25, 0.50, 0.75, target one-based rank 1 + q × (n − 1). Choose the nearest actual rank; exact target-distance ties are alphabetical by ticker. No liquidity values interpolated.\n\n'
    tier_counts = audit.groupby(['asset_class', 'liquidity_tier'], sort=False).size().rename('eligible_candidates').reset_index()
    tier_counts['target_ranks'] = tier_counts.eligible_candidates.map(lambda n: '/'.join(str(float(1 + q * (n - 1))) for q in TARGETS))
    report += markdown(tier_counts) + f'\n\nselection_audit.csv retains the full {len(audit)}-member eligible ranking, ranks, flags and selection decisions.\n\n'
    for cls in CLASSES:
        report += cls.upper() + '\n\n' + markdown(selected.loc[selected.asset_class.eq(cls), columns]) + '\n\n'
    report += 'Liquidity units: existing median daily close × volume from split+dividend adjusted local files; an adjusted-price dollar-volume proxy. Values and tiers are independent within each class. This is not reconstructed unadjusted historical turnover.\n\n'
    report += 'Coverage dates are observed local raw-date endpoints inside 2015-2025, not full provider-history endpoints or complete primary-session coverage certification. Coverage flag compares endpoints with empirical observed study boundaries in the scanned class and checks all 11 observed years. FCPT begins during 2015 and remains flagged even though 11 calendar years are represented.\n\n'
    report += f'All {len(selected)} selections require Bloomberg identifier and security-type/reference validation. Provider names are retained as evidence, not used for selection or automatic type inference. '
    name_cues = selected.loc[selected.asset_class.eq('stocks') & selected.provider_name.fillna('').str.contains(r'\bTrust\b', case=False)]
    if len(name_cues):
        report += 'Provider Trust labels requiring instrument-classification review: ' + ', '.join(name_cues.asset) + '. No security type is inferred from these labels and no provisional pick is replaced. '
    report += '\n\n'
    unbalanced = selected.loc[selected.coverage_unbalanced_2015_2025]
    report += 'Unbalanced local study spans (retained without replacement): ' + ', '.join(unbalanced.asset) + '.\n\n'
    report += 'Selected zero-volume rows in 2024: ' + ', '.join(f'{r.asset}: {r.zero_volume_rows_2024}' for r in selected.itertuples() if r.zero_volume_rows_2024) + '. Rows remain flagged and retained despite the provider omission policy.\n\n'
    report += 'Bloomberg plan: 234 proposed field rows, comprising 126 BDH daily and 108 BDP reference requests. Daily date range is inclusive 2015-01-01 through 2025-12-31. BDP start/end columns carry study context only; reference values are retrieval-date snapshots, not historical metadata.\n\n'
    report += 'DAILY / BDH: ' + ', '.join(DAILY_FIELDS) + '.\n\nREFERENCE / BDP: ' + ', '.join(REFERENCE_FIELDS) + ' (ID_CUSIP where applicable).\n\n'
    report += 'Before extraction: replace every placeholder with a terminal-validated identifier; validate issuer/listing/security type, FIGI, currency and historical ticker/name continuity; document CUSIP applicability. Resolve or explicitly document daily price and volume adjustment settings, session/date/quote timing and units; no adjustment convention is frozen. Preserve retrieval settings, failures and source lineage when a later authorized pull occurs.\n\n'
    unmaterialized = [r.asset for r in selected.itertuples() if (r.asset_class, r.asset) not in local_keys]
    report += f'Local validation limitation: the Step-6 First Rate daily aggregation pipeline exists and is validated; {len(unmaterialized)} selected assets have no materialized OHLCV table in the existing pilot: ' + ', '.join(unmaterialized) + '. Produce the selected local validation aggregates before asserting any local/Bloomberg equivalence. Existing pilot presence alone would not establish full-window coverage. Full-window comparison will also require an explicit policy for unequal coverage; no new coverage exclusion or replacement is imposed here.\n\n'
    report += 'PX_BID/PX_ASK are Bloomberg daily quote fields, not the intraday benchmark. The final sample uses no Roll values/status/failures, estimator values or manually preferred names. No raw provider reads/writes, Bloomberg extraction, futures/crypto final selection or estimator performance calculation. README.md, design_decisions.md and data_manifest.csv are untouched.\n'
    (out / 'final_universe_review.md').write_text(report, encoding='utf-8')
    manifest = dict(step='7A', provisional=True, input_sha256=hashes,
        local_daily_pilot_sha256=hashlib.sha256(local_path.read_bytes()).hexdigest(),
        selection_rule='nearest integer rank to 1+q*(n-1), q=1/4,1/2,3/4; all exact ties alphabetically by ticker',
        full_eligible_ranked_assets=len(audit), selected_assets=len(selected), bloomberg_plan_rows=len(plan),
        benchmark_or_estimator_inputs_used=False, names_used_for_selection=False,
        coverage_or_reference_flags_used_for_selection=False, replacements=0,
        raw_provider_reads=0, raw_provider_writes=0, bloomberg_requests=0)
    (out / 'run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(selected[['asset', 'asset_class'] + columns[1:]].to_string(index=False))
    return selected, audit, plan


if __name__ == '__main__':
    run()
