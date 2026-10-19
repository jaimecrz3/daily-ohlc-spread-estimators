"""Step 12.1 exact UTC calendar from existing validated daily observations only.

Never substitutes inventory endpoints for validated history or reads raw prices.
The currently available Step-12 panels contain 2024 only; this is recorded as a
multi-year freeze blocker, not silently promoted to a primary 2024 design.
"""
from pathlib import Path
import json

import pandas as pd
import yaml

from bloomberg_io import sha256,verify_hashes,require_verified

PROJECT=Path(__file__).resolve().parents[1]
OUT=PROJECT/'outputs/diagnostics/final_universe/crypto_final'
TIERS={'LOW':['ICX','NEO','DASH'],'MEDIUM':['ZEC','ALGO','MKR'],'HIGH':['NEAR','LINK','DOGE']}
NEW_FILES={'crypto_analysis_calendar.csv','crypto_final_analysis_spec.yaml','crypto_design_freeze_review.md',
    'crypto_analysis_calendar_manifest.json','step12_1_test_results.txt'}


def exact_calendar(panels,tiers,study_start='2015-01-01',study_end='2025-12-31'):
    """Union is an audit of physical observed dates; intersection is valid dates.

    No date_range/reindex/resample is used to construct either observation set.
    Missing rows and invalid rows remain distinct. Zero-volume rows stay valid
    whenever the existing aggregation diagnostic says so.
    """
    roots=[asset for assets in tiers.values() for asset in assets]
    if len(roots)!=len(set(roots)) or set(roots)!=set(panels):
        raise ValueError('Selected assets/tier membership must match exactly')
    observed={};valid={};summaries=[]
    for asset in roots:
        data=panels[asset]
        if not {'date','aggregation_valid','bars_observed','timezone'}.issubset(data):
            raise ValueError('Existing validated daily provenance required')
        if not data.timezone.eq('UTC').all(): raise ValueError('UTC daily panels required')
        dates=pd.to_datetime(data.date,utc=True,errors='raise')
        if dates.isna().any() or dates.duplicated().any() or dates.ne(dates.dt.normalize()).any():
            raise ValueError('Missing, duplicate or non-calendar-date daily labels')
        if not data.aggregation_valid.isin([True,False]).all():
            raise ValueError('Explicit existing aggregation-valid flags required')
        labels=dates.dt.strftime('%Y-%m-%d')
        inside=labels.between(study_start,study_end)
        good=inside&data.aggregation_valid.eq(True)&pd.to_numeric(data.bars_observed,errors='coerce').gt(0)
        observed[asset]=set(labels.loc[inside]);valid[asset]=set(labels.loc[good])
        summaries.append(dict(asset=asset,liquidity_tier=next(t for t,a in tiers.items() if asset in a),
            first_valid_observed_utc_date=min(valid[asset]) if valid[asset] else None,
            last_valid_observed_utc_date=max(valid[asset]) if valid[asset] else None,
            observed_days=len(observed[asset]),valid_days=len(valid[asset]),
            invalid_observed_days=len(observed[asset]-valid[asset])))
    common=sorted(set.intersection(*valid.values()))
    union=sorted(set.union(*observed.values()))
    audit=[]
    for day in union:
        missing=[a for a in roots if day not in observed[a]]
        invalid=[a for a in roots if day in observed[a] and day not in valid[a]]
        record=dict(date=day,timezone='UTC',observed_assets=sum(day in observed[a] for a in roots),
            valid_assets=sum(day in valid[a] for a in roots),common_valid_date=day in common,
            missing_assets=';'.join(missing),invalid_assets=';'.join(invalid),
            omission_reason=';'.join(['missing_validated_observation']*bool(missing)+['invalid_existing_aggregation']*bool(invalid)))
        for tier,assets in tiers.items(): record[tier+'_valid_assets']=sum(day in valid[a] for a in assets)
        audit.append(record)
    return pd.DataFrame(audit),pd.DataFrame(summaries),common


def common_asset_dates(common,tiers):
    """Expansion only of actually common dates; useful for equality checks."""
    return pd.DataFrame([dict(date=day,asset=asset,liquidity_tier=tier)
        for day in common for tier,assets in tiers.items() for asset in assets],
        columns=['date','asset','liquidity_tier'])


def unrepresented_ranges(observed_dates):
    """Metadata-only audit of unvalidated study periods; never daily data rows."""
    absent=[day for day in pd.date_range('2015-01-01','2025-12-31').strftime('%Y-%m-%d') if day not in observed_dates]
    groups=[]
    for day in absent:
        if not groups or pd.Timestamp(day)-pd.Timestamp(groups[-1][-1])!=pd.Timedelta(days=1): groups.append([])
        groups[-1].append(day)
    return [dict(start=group[0],end=group[-1],calendar_dates=len(group),
        reason='No validated daily panel observations available; raw-day availability not assessed') for group in groups]


def table_md(frame):
    return '\n'.join(['| '+' | '.join(frame.columns)+' |','| '+' | '.join(['---']*len(frame.columns))+' |']+
        ['| '+' | '.join(str(value) for value in row)+' |' for row in frame.itertuples(index=False,name=None)])


def assert_preserved(hashes):
    if any(sha256(path)!=digest for path,digest in hashes.items()):
        raise AssertionError('Frozen selection/ranking or prior artifacts changed')


def run():
    current_spec=OUT/'crypto_final_analysis_spec.yaml'
    if current_spec.exists():
        current=yaml.safe_load(current_spec.read_text(encoding='utf-8'))
        if current.get('approval_step')=='12.2':
            raise ValueError('Step 12.2 supersedes this 2024-only audit; use crypto_historical_materialization.py to avoid overwriting the historical analysis decision')
    prior_files=[p for p in OUT.rglob('*') if p.is_file() and not (p.parent==OUT and p.name in NEW_FILES)]
    prior_files += [PROJECT/name for name in ['README.md','design_decisions.md','data_manifest.csv',
        'manifests/data_manifest.csv'] if (PROJECT/name).is_file()]
    before={p:sha256(p) for p in prior_files}
    manifest=json.loads((OUT/'run_manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['output_sha256'].items():
        assert sha256(OUT/name)==digest,'Prior Step-12 output changed: '+name
    frozen=yaml.safe_load((OUT/'crypto_final_spec.yaml').read_text(encoding='utf-8'))
    assert frozen['status']=='FROZEN' and frozen['liquidity_tiers']==TIERS
    assert frozen['selected_assets']==[asset for assets in TIERS.values() for asset in assets]
    selected=pd.read_csv(OUT/'selected_crypto.csv',usecols=['asset','liquidity_tier'])
    assert len(selected)==9 and selected.set_index('asset').liquidity_tier.to_dict()=={
        asset:tier for tier,assets in TIERS.items() for asset in assets}
    # This combined, hash-verified derived panel is the complete validated daily
    # source currently materialized for the selected nine. Do not use the
    # first/last inventory columns as if they were daily history.
    columns=['asset','date','aggregation_valid','bars_observed','timezone']
    daily=pd.read_csv(OUT/'crypto_daily_turnover_audit.csv',usecols=columns)
    panels={asset:daily.loc[daily.asset.eq(asset),columns].copy() for asset in selected.asset}
    audit,coverage,common=exact_calendar(panels,TIERS)
    assert common and set(day[:4] for day in common)=={'2024'}
    # A one-year observed intersection cannot satisfy the requested multi-year
    # condition. No arbitrary precision/coverage threshold or 2024 fallback is
    # invented to approve an inadequate calendar.
    status='BLOCKED_MULTIYEAR_VALIDATED_DAILY_PANELS_UNAVAILABLE'
    audit['calendar_role']='available_validated_overlap_audit_only'
    audit['primary_inclusion']=False
    audit['crypto_analysis_window_status']=status
    audit.to_csv(OUT/'crypto_analysis_calendar.csv',index=False)
    missing_ranges=unrepresented_ranges(set(audit.date))
    omissions=audit.loc[~audit.common_valid_date,['date','missing_assets','invalid_assets','omission_reason']]
    spec=dict(status='BLOCKED',crypto_universe_status='FROZEN',crypto_analysis_window_status=status,
        selected_assets=frozen['selected_assets'],liquidity_tiers=TIERS,liquidity_calibration_year=2024,
        primary_common_start=None,primary_common_end=None,primary_common_dates=None,primary_asset_days=None,
        primary_design='Pending validated multi-year daily panels; intended design is exact common observed UTC dates across all nine',
        available_common_start=common[0],available_common_end=common[-1],available_common_dates=len(common),
        available_common_asset_days=len(common)*9,available_common_calendar_is_frozen_primary=False,
        available_validated_calendar_scope='2024 only; raw-file endpoints do not establish validated daily coverage',
        individual_validated_coverage=coverage.to_dict('records'),
        omitted_observed_dates=omissions.to_dict('records'),unrepresented_study_periods=missing_ranges,
        historical_supplementary_role='Earlier/later validated history, once available, is supplementary descriptive only; no pooling changing asset composition as a liquidity effect',
        missing_day_policy='Exact observed-date intersection only; no synthesized days, filling, carry-forward, relabelling or compression',
        look_ahead_limitation='Tier labels calibrated on 2024 provider-quote turnover use future information on pre-2024 observations; look-ahead / survivorship-style design limitation',
        selection_timing='Universe frozen before any provider Roll/CS/AR/EDGE performance; no estimator outcome influenced selection',
        quote_basis_status=frozen['quote_basis_validation_status'],quote_currency=frozen['quote_currency'],
        literal_usd_denomination_established=False,
        blocker='Only 2024 validated daily observations exist locally for the selected nine; multi-year valid-date intersection cannot be inferred from inventory endpoints',
        next_requirement='Provide already validated multi-year UTC daily panels, or separately authorize materialization using the validated aggregation pipeline; no raw reads in this step',
        historical_panel_materialization_performed=False,no_benchmark_or_estimator_calculations=True,
        preserved_selection_sha256=sha256(OUT/'selected_crypto.csv'),preserved_ranking_sha256=sha256(OUT/'selection_audit.csv'))
    (OUT/'crypto_final_analysis_spec.yaml').write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    report='# Step 12.1 crypto analysis-calendar review\n\n'
    report+='**The universe remains FROZEN; the primary analysis window is BLOCKED.** Only the selected assets\' validated 2024 daily panels are currently materialized. An exact multi-year intersection cannot be certified from raw-file inventory endpoints. No intraday raw files were read, no additional history was aggregated, and no one-year fallback was frozen.\n\n'
    report+='Individual actual validated UTC coverage\n\n'+table_md(coverage)+'\n\n'
    report+=f'The exact intersection of the available validated panels is **{common[0]} through {common[-1]}**, **{len(common)} UTC dates**, or **{len(common)*9:,} potential asset-days** with all nine represented. Every tier has the same {len(common)} dates. This is currently available one-year overlap, not the requested substantial multi-year primary window. The primary fields remain null in crypto_final_analysis_spec.yaml; crypto_analysis_calendar.csv is explicitly an audit with primary_inclusion=False.\n\n'
    report+=f'Omitted dates within the observed union: **{len(omissions)}**. No available 2024 dates were missing or invalid in any selected asset. Outside that materialized scope, **{sum(r["calendar_dates"] for r in missing_ranges):,} study-calendar dates have no validated daily evidence**, as follows:\n\n'+table_md(pd.DataFrame(missing_ranges))+'\n\n'
    report+='These unsupported ranges are not claims that raw trading data are absent. Inventory dates reaching back to 2017/2019/2022 and into 2026 are metadata, not validated daily observations. In particular, NEAR\'s first inventory date is not used as a primary start date. Nothing is synthesized for wholly unrepresented dates; the ranges above are metadata-only audits, not inserted observation rows.\n\n'
    report+='Intended frozen-design policy once sufficient validated history is supplied: use the exact common UTC dates for all nine and all tiers. Preserve each asset\'s earlier/later validated history for supplementary descriptive analysis only. Never pool changing historical asset composition and attribute differences solely to liquidity.\n\n'
    report+='Liquidity tiers were calibrated using 2024 turnover. Applying them to pre-2024 observations uses future information and creates a look-ahead / survivorship-style design limitation. Selection was nevertheless frozen before any provider Roll/CS/AR/EDGE performance was calculated; no estimator outcome influenced selection. The universe must not be changed to hide this limitation.\n\n'
    report+='Quote-basis status remains VERIFIED_COMMON_PROVIDER_QUOTE_BASIS; formal quote currency remains UNKNOWN. Selected assets, tiers, ranking, eligibility, validation thresholds, raw data and protected documentation remain unchanged. No benchmark or estimator values were calculated. Crypto is not yet fully frozen because a multi-year analysis calendar is not available under the existing-panels-only constraint.\n\n'
    report+='Next requirement: supply a path to existing validated multi-year UTC daily panels. If none exist, historical daily materialization requires a separate scope change; this task does not read raw data or perform that work. Reproduce the available-calendar audit with src/crypto_analysis_calendar.py.\n'
    tests=OUT/'step12_1_test_results.txt'
    if tests.exists(): report+='\n```text\n'+tests.read_text(encoding='utf-8').strip()+'\n```\n'
    (OUT/'crypto_design_freeze_review.md').write_text(report,encoding='utf-8')
    assert_preserved(before)
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    result=dict(status=status,source_panel_sha256=sha256(OUT/'crypto_daily_turnover_audit.csv'),
        preserved_prior_sha256={str(p.relative_to(PROJECT)):digest for p,digest in before.items()},
        code_sha256=sha256(Path(__file__)),intraday_raw_data_reads=False,raw_data_writes=False,
        raw_bloomberg_hashes_verified=len(raw),no_benchmark_or_estimator_calculations=True,
        output_sha256={name:sha256(OUT/name) for name in NEW_FILES
            if (OUT/name).is_file() and name!='crypto_analysis_calendar_manifest.json'})
    (OUT/'crypto_analysis_calendar_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(coverage.to_string(index=False));print(f'Available common dates: {len(common)}; potential asset-days: {9*len(common)}; {status}')


if __name__=='__main__': run()
