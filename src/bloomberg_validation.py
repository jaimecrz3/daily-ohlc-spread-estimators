"""Step 8 descriptive daily-source validation; no estimator or benchmark inputs.

Run: .venv/Scripts/python.exe -B src/bloomberg_validation.py
All acquisition files, including the hash manifest, are immutable.
"""
from pathlib import Path
import json
import re

import numpy as np
import openpyxl
import pandas as pd

try:
    from .bloomberg_io import (DAILY_FIELDS, REF_FIELDS, SIDE_FIELDS, OHLC, sha256,
        verify_hashes, require_verified, read_reference, read_daily_values,
        inspect_daily_lineage, summarize_daily, unique_dated, overlap_join)
except ImportError:
    from bloomberg_io import (DAILY_FIELDS, REF_FIELDS, SIDE_FIELDS, OHLC, sha256,
        verify_hashes, require_verified, read_reference, read_daily_values,
        inspect_daily_lineage, summarize_daily, unique_dated, overlap_join)

PROJECT = Path(__file__).resolve().parents[1]
RAW = PROJECT / 'data/raw_bloomberg'
OUT = PROJECT / 'outputs/diagnostics/bloomberg_validation'
INTERIM = PROJECT / 'data/interim/bloomberg'
LOCAL_PATH = PROJECT / 'outputs/diagnostics/final_universe/local_daily_validation/selected_daily_ohlcv.csv'
SELECTED_PATH = PROJECT / 'outputs/diagnostics/final_universe/selected_stocks_etfs.csv'


def differences(left, right):
    finite = np.isfinite(left) & np.isfinite(right)
    absolute = (left-right).abs().where(finite)
    # Relative denominator is the explicitly named comparison reference.
    relative = absolute.div(right.abs().where(right.ne(0))).where(finite)
    return finite, absolute, relative


def compare_conventions(unadjusted, adjusted):
    joined = overlap_join(unadjusted, adjusted)
    summaries, clusters = [], []
    for asset, group in joined.groupby('asset', sort=True):
        changed = pd.Series(False, index=group.index)
        record = dict(asset=asset, overlapping_dates=len(group),
            unadjusted_only_dates=len(set(unique_dated(unadjusted.loc[unadjusted.asset.eq(asset)]).date)-set(group.date)),
            adjusted_only_dates=len(set(unique_dated(adjusted.loc[adjusted.asset.eq(asset)]).date)-set(group.date)))
        ohlc_diff = pd.Series(False, index=group.index)
        for field in OHLC+['PX_VOLUME']:
            x, y = group[field+'_right'], group[field+'_left']
            finite, absolute, relative = differences(x, y)
            unequal = finite & x.ne(y)
            changed |= unequal
            if field in OHLC:
                ohlc_diff |= unequal
            record[field+'_differing_days'] = int(unequal.sum())
            record[field+'_valid_pairs'] = int(finite.sum())
            record[field+'_max_absolute_difference'] = absolute.max()
            record[field+'_max_relative_difference'] = relative.max()
            record[field+'_missingness_differs_days'] = int(np.isfinite(x).ne(np.isfinite(y)).sum())
        record['ohlc_differing_days'] = int(ohlc_diff.sum())
        record['volume_differing_days'] = record['PX_VOLUME_differing_days']
        record['first_differing_date'] = group.loc[changed, 'date'].min()
        record['last_differing_date'] = group.loc[changed, 'date'].max()
        summaries.append(record)
        ratios = group.PX_LAST_right.div(group.PX_LAST_left.where(group.PX_LAST_left.gt(0)))
        ratios = ratios.where(np.isfinite(ratios))
        # Observable factor changes are review candidates, not invented event labels.
        prior = ratios.shift()
        jump = ratios.div(prior).sub(1).abs()
        for index in group.index[jump.ge(.01)]:
            clusters.append(dict(asset=asset, check_type='adjustment_factor_change_candidate',
                date=group.loc[index, 'date'], adjusted_close=group.loc[index, 'PX_LAST_right'],
                unadjusted_close=group.loc[index, 'PX_LAST_left'], adjustment_factor=ratios.loc[index],
                previous_observed_factor=prior.loc[index], factor_change_relative=jump.loc[index],
                expected_factor=np.nan, check_passed=None,
                evidence='Empirical >=1% adjacent observed close adjustment-factor change; corporate action identity/date requires independent validation'))
    return pd.DataFrame(summaries), pd.DataFrame(clusters)


def corporate_action_checks(unadjusted, adjusted, clusters):
    joined = overlap_join(unadjusted, adjusted)
    rows = []
    for day, expected_unadj, expected_adj, expected_factor in [
        ('2022-07-22', .3122, 3.122, 10), ('2022-07-25', .2974, 2.974, 10), ('2022-07-26', 2.28, 2.28, 1)]:
        group = joined.loc[joined.asset.eq('SNDL') & joined.date.eq(pd.Timestamp(day))]
        if len(group) != 1:
            raise ValueError('SNDL saved corporate-action validation date missing/duplicated')
        row = group.iloc[0]
        factor = row.PX_LAST_right / row.PX_LAST_left
        ohlc_factors = {field+'_adjustment_factor': row[field+'_right']/row[field+'_left'] for field in OHLC}
        rows.append(dict(asset='SNDL', check_type='saved_notes_reverse_split_validation',
            date=pd.Timestamp(day), unadjusted_close=row.PX_LAST_left,
            adjusted_close=row.PX_LAST_right, adjustment_factor=factor,
            expected_factor=expected_factor,
            check_passed=bool(np.isclose(row.PX_LAST_left, expected_unadj) and np.isclose(row.PX_LAST_right, expected_adj) and np.isclose(factor, expected_factor)),
            all_ohlc_scaling_checks_passed=all(np.isclose(value, expected_factor) for value in ohlc_factors.values()),
            **ohlc_factors,
            unadjusted_volume=row.PX_VOLUME_left, adjusted_volume=row.PX_VOLUME_right,
            evidence='field_validation_notes.txt: SNDL 1-for-10 reverse split 2022-07-26; saved pre/post price checks'))
    return pd.concat([pd.DataFrame(rows), clusters], ignore_index=True)


def compare_local(data, local):
    joined = overlap_join(data, local)
    metrics, coverage, largest = [], [], []
    mappings = dict(zip(OHLC+['PX_VOLUME'], ['open', 'high', 'low', 'close', 'volume']))
    convention = data.convention.iloc[0]
    for asset, group in joined.groupby('asset', sort=True):
        bloom = unique_dated(data.loc[data.asset.eq(asset)])
        rate = unique_dated(local.loc[local.asset.eq(asset)])
        bbdates, localdates = set(bloom.date), set(rate.date)
        coverage.append(dict(asset=asset, convention=convention, bloomberg_returned_dates=len(bbdates),
            first_rate_observed_dates=len(localdates), overlapping_dates=len(group),
            bloomberg_only_dates=len(bbdates-localdates), first_rate_only_dates=len(localdates-bbdates),
            bloomberg_first_date=bloom.date.min(), bloomberg_last_date=bloom.date.max(),
            first_rate_first_date=rate.date.min(), first_rate_last_date=rate.date.max()))
        for field, local_field in mappings.items():
            finite, absolute, relative = differences(group[field], group[local_field])
            record = dict(asset=asset, convention=convention, field=local_field,
                overlapping_dates=len(group), bloomberg_only_dates=len(bbdates-localdates),
                first_rate_only_dates=len(localdates-bbdates), valid_numeric_pairs=int(finite.sum()),
                relative_difference_pairs=int(relative.notna().sum()),
                exact_match_count=int((finite & group[field].eq(group[local_field])).sum()),
                exact_match_rate=float((finite & group[field].eq(group[local_field])).sum()/finite.sum()) if finite.any() else np.nan,
                median_absolute_difference=absolute.median(), median_relative_difference=relative.median(),
                p95_relative_difference=relative.quantile(.95), max_relative_difference=relative.max(),
                reference_denominator='absolute First Rate value; zero denominator undefined',
                comparison_includes_finite_values_on_flagged_days=True)
            metrics.append(record)
            ranking = pd.DataFrame(dict(date=group.date, relative=relative, absolute=absolute,
                bloomberg_value=group[field], first_rate_value=group[local_field],
                bloomberg_daily_input_valid=group.daily_input_valid,
                first_rate_aggregation_valid=group.aggregation_valid))
            ranking = ranking.loc[ranking.relative.notna()].sort_values(['relative', 'date'], ascending=[False, True], kind='stable').head(5)
            for rank, row in enumerate(ranking.itertuples(), 1):
                largest.append(dict(asset=asset, convention=convention, field=local_field,
                    discrepancy_rank=rank, date=row.date, bloomberg_value=row.bloomberg_value,
                    first_rate_value=row.first_rate_value, absolute_difference=row.absolute,
                    relative_difference=row.relative,
                    bloomberg_daily_input_valid=row.bloomberg_daily_input_valid,
                    first_rate_aggregation_valid=row.first_rate_aggregation_valid))
    return pd.DataFrame(metrics), pd.DataFrame(coverage), pd.DataFrame(largest)


def normalize_source_log(reference, lineage, hashes, notes_text):
    workbook = openpyxl.load_workbook(RAW / 'bloomberg_source_log.xlsx', data_only=True, read_only=True)
    try:
        rows = list(workbook.active.values)
        saved = pd.DataFrame(rows[1:], columns=rows[0])
    finally:
        workbook.close()
    extraction = saved.loc[saved.output_file.eq('bloomberg_reference_raw.xlsx'), 'extraction_date'].iloc[0]
    descriptions = {}
    for field in REF_FIELDS + SIDE_FIELDS + DAILY_FIELDS:
        match = re.search(r'\* '+re.escape(field)+r': ([^\r\n]+)', notes_text)
        if not match and field in OHLC:
            match = re.search(r'\* PX_OPEN, PX_HIGH, PX_LOW, PX_LAST: ([^\r\n]+)', notes_text)
        descriptions[field] = match.group(1) if match else 'not defined separately in saved field_validation_notes.txt'
    result = []
    for row in reference.itertuples():
        for field in REF_FIELDS+SIDE_FIELDS:
            for filename, role in [('bloomberg_reference_raw.xlsx', 'formula_lineage_only'), ('bloomberg_reference_raw_values.xlsx', 'cached_values_ingestion')]:
                result.append(dict(source_type='reference', provider='Bloomberg', terminal_function='BDP',
                    security_or_series_id=row.bloomberg_security, field=field,
                    field_description=descriptions[field], frequency='reference_snapshot',
                    start='', end='', currency=row.CRNCY, units='reference metadata',
                    timezone='retrieval timezone not recorded', adjustment='not applicable',
                    retrieval_date=pd.Timestamp(extraction).date().isoformat(),
                    file_name=filename, file_hash=hashes[filename],
                    notes=f'{role}; source log describes six fields, while actual workbook main block has six plus three side-block fields; current snapshot does not certify historical reference identity'))
    for row in lineage.itertuples():
        log_row = saved.loc[saved.output_file.eq(row.source_file)].iloc[0]
        filename_values = row.source_file.replace('_raw.xlsx', '_raw_values.xlsx')
        for field in DAILY_FIELDS:
            for filename, role in [(row.source_file, 'formula_lineage_only'), (filename_values, 'cached_values_ingestion')]:
                result.append(dict(source_type='daily_historical', provider='Bloomberg', terminal_function='BDH',
                    security_or_series_id=row.security, field=field, field_description=descriptions[field],
                    frequency='DAILY', start='2015-01-01', end='2025-12-31',
                    currency=reference.set_index('asset').loc[row.asset, 'CRNCY'],
                    units='volume scaling not explicitly documented; pending validation' if field == 'PX_VOLUME' else 'quoted currency per saved notes',
                    timezone='daily EOD observation timezone not recorded',
                    adjustment=row.convention+'; '+row.overrides,
                    retrieval_date=pd.Timestamp(log_row.extraction_date).date().isoformat(),
                    file_name=filename, file_hash=hashes[filename],
                    notes=f'{role}; sheet={row.sheet}; anchor={row.formula_cell}; CshAdjAbnormal={row.special_cash_dividend_override}; '+str(log_row.notes)))
    # Historical OCX comparison is provenance only, never a 19th analytic series.
    for field in ['NAME', 'ID_BB_GLOBAL', 'ID_ISIN', 'TICKER_AND_EXCH_CODE']:
        result.append(dict(source_type='reference_identity_diagnostic', provider='Bloomberg', terminal_function='BDP', security_or_series_id='OCX US Equity', field=field, field_description=descriptions[field], frequency='reference_snapshot', start='', end='', currency='not returned in saved comparison', units='reference metadata', timezone='retrieval timezone not recorded', adjustment='not applicable', retrieval_date=pd.Timestamp(extraction).date().isoformat(), file_name='bloomberg_reference_raw_values.xlsx', file_hash=hashes['bloomberg_reference_raw_values.xlsx'], notes='OCX comparison evidence only; FIGI and ISIN returned errors; no manual stitching'))
    for row in saved.loc[saved.sheet_name.eq('OCX_check')].itertuples():
        for field in DAILY_FIELDS:
            result.append(dict(source_type='historical_identity_diagnostic', provider='Bloomberg', terminal_function='BDH', security_or_series_id='OCX US Equity', field=field, field_description=descriptions[field], frequency='DAILY', start='2015-01-01', end='2025-12-31', currency='not returned', units='not returned', timezone='not recorded', adjustment='overrides not explicitly specified in saved diagnostic', retrieval_date=pd.Timestamp(row.extraction_date).date().isoformat(), file_name=row.output_file, file_hash=hashes[row.output_file], notes=str(row.notes)+'; saved OCX_check returns one #N/A error, not dated historical rows; field-specific values unavailable'))
    return pd.DataFrame(result), saved


def markdown(table):
    result = ['| '+' | '.join(table.columns)+' |', '| '+' | '.join(['---']*len(table.columns))+' |']
    for row in table.itertuples(index=False, name=None):
        result.append('| '+' | '.join('NA' if pd.isna(v) else f'{v:.6g}' if isinstance(v, float) else str(v).replace('|', '/') for v in row)+' |')
    return '\n'.join(result)


def write_review(reference, summaries, conventions, actions, comparison, coverage, ocx):
    report = '# Step 8 daily input convention review\n\n'
    report += '## 1. Source facts\n\nAll 11 manifest files verified before numerical ingestion and again after output generation. Final 18-security values-only workbooks supply numerical/reference data; formula files supply only lineage. Older pilot files and OCX_check are excluded from the final series. No raw files or manifest changed; no recalculation or imputation.\n\n'
    report += 'Saved BDH field order: PX_OPEN, PX_HIGH, PX_LOW, PX_LAST, PX_VOLUME, PX_BID, PX_ASK. Actual formulas use unadjusted CapChg=F, CshAdjNormal=F, CshAdjAbnormal=F; adjusted CapChg=T, CshAdjNormal=T, with CshAdjAbnormal NOT explicitly set. Do not infer the unspecified abnormal-dividend default. Daily dates are returned labels; EOD quote time/timezone is not documented. Definitions are taken only from field_validation_notes.txt.\n\n'
    report += 'First Rate: existing observed 09:30 <= America/New_York time < 16:00 aggregates, split+dividend adjusted, local_daily_validation. Exact corporate-action scaling and volume/session equivalence are not assumed. Bloomberg daily quotes are neither intraday quotes nor a benchmark.\n\n'
    report += '## 2. Empirical validation\n\nReference classifications\n\n' + markdown(reference[['asset', 'asset_class', 'SECURITY_TYP', 'CRNCY', 'MARKET_SECTOR_DES', 'EQY_PRIM_EXCH_SHRT', 'validation_status']])+'\n\n'
    report += 'BIDU is ADR in Bloomberg, supporting the saved US ADS-line description. FCPT is REIT. All nine ETFs are ETP. IMDX resolves current reference fields and has historical BDH rows under IMDX; OCX comparison retains cached FIGI and ISIN errors. The notes claim OCX ISIN resolves, contradicting the actual cached error. Stable-ID continuity remains unresolved; no OCX stitching.\n\n'
    report += 'Unadjusted returned coverage and completeness (adjusted coverage/missingness available in daily_ingestion_summary.csv)\n\n' + markdown(summaries.loc[summaries.convention.eq('unadjusted'), ['asset', 'first_returned_date', 'last_returned_date', 'total_returned_rows', 'complete_ohlc_days', 'complete_ohlcv_days', 'invalid_ohlc_rows', 'PX_BID_missing_count', 'PX_ASK_missing_count', 'ask_less_than_bid_rows']])+'\n\n'
    report += 'Formatted blank padding is not a returned data row. Dated partial/error rows remain present, with raw field tokens and explicit missing/error/non-numeric/non-finite flags. Complete OHLC denotes finite presence, separate from OHLC validity. Finite diagnostic pairs are compared without silently filtering flagged days; quality flags remain visible in large-discrepancy records.\n\n'
    report += 'Bloomberg includes SNDL 2019-07-31 as a close-only partial row, preceding the 2019-08-01 IPO/start date described in the notes. This discrepancy is retained, not relabeled or filled. JSML also has a close-only row on 2016-02-24.\n\n'
    report += 'Adjustment differences (relative differences divide by absolute unadjusted value)\n\n' + markdown(conventions[['asset', 'ohlc_differing_days', 'volume_differing_days', 'first_differing_date', 'last_differing_date', 'PX_LAST_max_relative_difference', 'PX_VOLUME_max_relative_difference']])+'\n\n'
    report += 'SNDL saved reverse-split checks\n\n' + markdown(actions.loc[actions.check_type.eq('saved_notes_reverse_split_validation'), ['date', 'unadjusted_close', 'adjusted_close', 'adjustment_factor', 'expected_factor', 'check_passed', 'unadjusted_volume', 'adjusted_volume']])+'\n\n'
    report += 'Additional >=1% adjacent close adjustment-factor changes are empirical review candidates in corporate_action_checks.csv, not independently identified corporate actions. They must not be interpreted as verified event dates.\n\n'
    report += 'Source coverage (unadjusted; both conventions retained separately)\n\n' + markdown(coverage.loc[coverage.convention.eq('unadjusted'), ['asset', 'overlapping_dates', 'bloomberg_only_dates', 'first_rate_only_dates']])+'\n\n'
    report += 'Close and volume differences versus local data (relative denominator: absolute First Rate value; proportions, not percent)\n\n' + markdown(comparison.loc[comparison.field.isin(['close', 'volume']), ['asset', 'convention', 'field', 'valid_numeric_pairs', 'exact_match_rate', 'median_relative_difference', 'p95_relative_difference', 'max_relative_difference']])+'\n\n'
    report += 'Only dates physically returned/observed in both sources enter comparisons. Numeric missing values never become complete rows. Each join validates one-to-one keys; duplicates would block comparisons rather than be deduplicated. Undefined zero-denominator relative differences are omitted only from the relative statistic, with numeric/relative pair counts retained. Source-only dates are counted from observed sets, not a synthetic calendar. All five OHLCV fields and the top five discrepancy dates per asset/convention/field are saved in CSVs.\n\n'
    report += '## 3. Unresolved methodological decision\n\nNo primary adjustment convention is frozen. Unadjusted OHLC preserves historical price levels but splits can create cross-date discontinuities; a multi-day daily-OHLC estimator can mistake these for price movements unless corporate-action boundaries are handled explicitly. Adjusted OHLC retrospectively transforms earlier observations to the acquisition-date convention and can change price levels and comparisons with a separately adjusted provider. Saved SNDL evidence confirms the x10 pre-split price scaling, not equivalence for every asset or action.\n\n'
    volume_assets = conventions.loc[conventions.volume_differing_days.gt(0), 'asset'].tolist()
    report += 'Bloomberg volume is empirically changed by the convention for: '+(', '.join(volume_assets) if volume_assets else 'none in these files')+'. This must be reconciled before volume-based cross-source comparisons; price adjustment does not imply volume invariance. Large local-volume differences also require exchange/coverage/unit definitions to be checked against the saved notes and provider conventions.\n\n'
    report += 'Before freezing: resolve/document CshAdjAbnormal for the adjusted acquisition, normal-versus-special-dividend and split treatment, session/auction/EOD timing, volume scale/coverage, treatment of partial/invalid/crossed daily quote rows, source-only dates, and IMDX/OCX stable-ID continuity. Current BDP classifications do not certify every historical listed line. Decide from source conventions and corporate-action methodology, never estimator fit or performance. No CS, AR, EDGE or benchmark calculation occurred. README.md, design_decisions.md and data_manifest.csv are untouched.\n'
    (OUT / 'daily_input_convention_review.md').write_text(report, encoding='utf-8')


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    initial_manifest_hash = sha256(RAW / 'sha256_manifest.csv')
    hash_audit, manifest = verify_hashes(RAW)
    hash_audit.to_csv(OUT / 'raw_hash_verification.csv', index=False)
    require_verified(hash_audit)
    required = ['bloomberg_reference_raw.xlsx', 'bloomberg_reference_raw_values.xlsx',
        'bloomberg_daily_unadjusted_raw.xlsx', 'bloomberg_daily_unadjusted_raw_values.xlsx',
        'bloomberg_daily_adjusted_raw.xlsx', 'bloomberg_daily_adjusted_raw_values.xlsx',
        'bloomberg_source_log.xlsx', 'field_validation_notes.txt']
    if not set(required).issubset(set(manifest.file_name)):
        raise ValueError('Final acquisition file missing from verified manifest')
    selected = pd.read_csv(SELECTED_PATH)
    selected_hash, local_hash = sha256(SELECTED_PATH), sha256(LOCAL_PATH)
    if len(selected) != 18 or selected.asset.duplicated().any():
        raise ValueError('Frozen final universe must have 18 unique assets')
    reference, ocx = read_reference(RAW / required[1], RAW / required[0], selected)
    reference.to_csv(OUT / 'reference_audit.csv', index=False)
    ocx.to_csv(OUT / 'ocx_reference_comparison.csv', index=False)
    inputs, lineages, exclusions, summaries = {}, [], [], []
    for convention in ['unadjusted', 'adjusted']:
        formula = RAW / f'bloomberg_daily_{convention}_raw.xlsx'
        values = RAW / f'bloomberg_daily_{convention}_raw_values.xlsx'
        lineages.append(inspect_daily_lineage(formula, selected, convention))
        inputs[convention], excluded = read_daily_values(values, selected, convention)
        summaries.append(summarize_daily(inputs[convention]))
        if not excluded.empty:
            exclusions.append(excluded)
    lineage = pd.concat(lineages, ignore_index=True)
    lineage.to_csv(OUT / 'acquisition_formula_lineage.csv', index=False)
    daily_summary = pd.concat(summaries, ignore_index=True)
    daily_summary.to_csv(OUT / 'daily_ingestion_summary.csv', index=False)
    excluded = pd.concat(exclusions, ignore_index=True) if exclusions else pd.DataFrame()
    excluded.to_csv(OUT / 'excluded_acquisition_sheet_audit.csv', index=False)
    for convention, data in inputs.items():
        problem = data.loc[data.duplicate_date | data.invalid_ohlc | data.nonpositive_price | data.negative_volume | data.ask_less_than_bid | data.partial_ohlc_row | data.unassignable_date | data.date_ordering_problem]
        problem.to_csv(OUT / f'{convention}_daily_quality_rows.csv', index=False)
        unique_dated(data)  # block unsafe comparisons, preserve duplicate audit first
    INTERIM.mkdir(parents=True, exist_ok=True)
    reference.to_parquet(INTERIM / 'reference.parquet', index=False)
    for convention, data in inputs.items():
        data.to_parquet(INTERIM / f'daily_{convention}.parquet', index=False)
    conventions, clusters = compare_conventions(inputs['unadjusted'], inputs['adjusted'])
    conventions.to_csv(OUT / 'adjusted_vs_unadjusted_summary.csv', index=False)
    actions = corporate_action_checks(inputs['unadjusted'], inputs['adjusted'], clusters)
    actions.to_csv(OUT / 'corporate_action_checks.csv', index=False)
    local = pd.read_csv(LOCAL_PATH, parse_dates=['date'])
    if set(local.asset) != set(selected.asset) or not local.source_role.eq('local_daily_validation').all() or not local.adjustment.eq('split_and_dividend_adjusted').all():
        raise ValueError('Local validation table has unexpected universe/source role/adjustment')
    local = local[['asset', 'date', 'open', 'high', 'low', 'close', 'volume', 'aggregation_valid']]
    comparisons, coverages, largest = [], [], []
    for data in inputs.values():
        metric, coverage, large = compare_local(data, local)
        comparisons.append(metric); coverages.append(coverage); largest.append(large)
    comparison = pd.concat(comparisons, ignore_index=True)
    coverage = pd.concat(coverages, ignore_index=True)
    comparison.to_csv(OUT / 'bloomberg_vs_local_summary.csv', index=False)
    coverage.to_csv(OUT / 'coverage_comparison.csv', index=False)
    pd.concat(largest, ignore_index=True).to_csv(OUT / 'bloomberg_vs_local_large_discrepancies.csv', index=False)
    notes = (RAW / 'field_validation_notes.txt').read_text(encoding='utf-8-sig')
    hashes = manifest.set_index('file_name').sha256.to_dict()
    source_log, saved_log = normalize_source_log(reference, lineage, hashes, notes)
    (PROJECT / 'manifests').mkdir(exist_ok=True)
    source_log.to_csv(PROJECT / 'manifests/bloomberg_source_log.csv', index=False)
    saved_log.to_csv(OUT / 'saved_source_log_audit.csv', index=False)
    pd.DataFrame([
        dict(issue='OCX_ISIN_notes_vs_cache', evidence='Saved notes say OCX ISIN resolves; Reference!L2 is #N/A N/A', status='unresolved; cached error preserved'),
        dict(issue='SNDL_start_notes_vs_returned_row', evidence='Saved notes say 2019-08-01 start; returned close-only date is 2019-07-31', status='partial row preserved; economic date review pending'),
        dict(issue='reference_source_log_field_count', evidence='Saved source log describes six fields; formula workbook contains six main and three side fields', status='normalized log uses actual verified nine fields'),
        dict(issue='adjusted_special_dividend_override', evidence='Adjusted formulas do not explicitly set CshAdjAbnormal', status='unresolved; no default invented'),
        dict(issue='volume_scale_and_EOD_time', evidence='Saved notes do not fully specify volume scaling or EOD timezone/timing', status='unresolved; no equivalence assumed')
    ]).to_csv(OUT / 'source_inconsistencies.csv', index=False)
    write_review(reference, daily_summary, conventions, actions, comparison, coverage, ocx)
    final_hash_audit, _ = verify_hashes(RAW)
    final_hash_audit.to_csv(OUT / 'raw_hash_verification_after.csv', index=False)
    require_verified(final_hash_audit)
    assert sha256(RAW / 'sha256_manifest.csv') == initial_manifest_hash
    assert selected_hash == sha256(SELECTED_PATH) and local_hash == sha256(LOCAL_PATH)
    # Parquet round trip confirms nullable numeric/token preservation.
    for convention, data in inputs.items():
        pd.testing.assert_frame_equal(data, pd.read_parquet(INTERIM / f'daily_{convention}.parquet'))
    pd.testing.assert_frame_equal(reference, pd.read_parquet(INTERIM / 'reference.parquet'))
    run_manifest = dict(status='complete', step=8, raw_manifest_sha256=initial_manifest_hash,
        all_11_hashes_verified_before_and_after=True, selected_universe_sha256=selected_hash,
        local_validation_sha256=local_hash, normalized_reference_rows=len(reference),
        normalized_daily_rows={k:len(v) for k,v in inputs.items()}, source_log_rows=len(source_log),
        raw_writes=0, workbook_recalculations=0, manual_ticker_stitches=0,
        imputed_values=0, adjustment_convention_frozen=False, estimator_or_benchmark_inputs_used=False,
        comparison_relative_denominator='First Rate for cross-source; unadjusted for convention comparison; absolute denominator; zero undefined',
        duplicate_policy='preserve audit, fail comparisons; one-to-one joins only',
        data_quality_policy='all returned dated rows preserved; finite diagnostic pairs compared with flags, no analytic eligibility policy frozen',
        derived_sha256={p.relative_to(PROJECT).as_posix():sha256(p) for p in sorted(OUT.glob('*.csv'))},
        parquet_sha256={p.relative_to(PROJECT).as_posix():sha256(p) for p in sorted(INTERIM.glob('*.parquet'))})
    (OUT / 'run_manifest.json').write_text(json.dumps(run_manifest, indent=2), encoding='utf-8')
    print(daily_summary[['asset', 'convention', 'total_returned_rows', 'complete_ohlcv_days', 'invalid_ohlc_rows']].to_string(index=False))
    print('SNDL checks:', actions.loc[actions.check_type.eq('saved_notes_reverse_split_validation'), 'check_passed'].tolist())
    print('All raw hashes preserved; convention remains pending.')


if __name__ == '__main__':
    run()
