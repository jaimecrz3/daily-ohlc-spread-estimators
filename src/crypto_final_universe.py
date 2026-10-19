"""Step 12 empirical common-provider-quote gate and within-crypto selection.

No literal quote-currency identity is inferred; no benchmark/estimator imports.
Validation limits are fixed in RULE before any provider diagnostic is calculated.
Run: .venv/Scripts/python.exe -B src/crypto_final_universe.py
"""
from itertools import islice
from pathlib import Path
import json
import time

import numpy as np
import pandas as pd
import yaml

from data_io import intraday_root
from eda_diagnostics import parse_chunk
from daily_aggregation import aggregate_daily_ohlcv
from session_rules import assign_primary_session
from universe_selection import history_eligible
from futures_final_universe import rank_and_select
from futures_roll import table_md
from bloomberg_io import sha256,verify_hashes,require_verified

PROJECT=Path(__file__).resolve().parents[1]
PRIOR=PROJECT/'outputs/diagnostics/final_universe/futures_crypto'
OUT=PROJECT/'outputs/diagnostics/final_universe/crypto_final'
VERIFIED='VERIFIED_COMMON_PROVIDER_QUOTE_BASIS'
RULE={
    'status':'PRESPECIFIED_BEFORE_STEP12_PROVIDER_DIAGNOSTICS',
    'objective':'Empirical common provider quote basis; formal quote currency remains UNKNOWN',
    'cross_relative_difference':'abs((ETH_close / BTC_close) / ETH-BTC_close - 1)',
    'minute_sample':'2024 calendar days at exactly 00:00,06:00,12:00,18:00 UTC; exact inner joins; no nearest matches or filling',
    'minimum_minute_overlap_observations':300,'minimum_minute_overlap_days':250,
    'minimum_daily_overlap_observations':300,
    'maximum_median_relative_difference':0.02,'maximum_p95_relative_difference':0.10,
    'minimum_pearson_level_correlation':0.95,'large_deviation_relative_difference':0.10,
    'daily_policy':'UTC observed-day last close; require valid aggregation and positive finite close; closing timestamp offsets audited',
    'stablecoins':['USDT','USDC','DAI','PAX'],'minimum_available_stablecoins':3,
    'minimum_valid_stablecoin_days':300,'stablecoin_median_range':[0.95,1.05],
    'stablecoin_p05_floor':0.90,'stablecoin_p95_ceiling':1.10,
    'stablecoin_extrema':'min/max reported; isolated extrema not an additional post-hoc gate',
    'decision':'Both cross scopes and every available prespecified stablecoin must pass; missing/undefined evidence fails closed',
    'synthetic_basis':'Accept small zero-median multiplicative composition noise; reject factor-two scaling, inversion, time-misalignment, or sustained non-unit stablecoins',
    'quality_policy':'Preserve every observed day and diagnostic; any invalid aggregation or undefined turnover day blocks that asset from ranking; zero-volume rows are flagged, not deleted',
    'history_policy':'>=3 elapsed calendar years of observed endpoint span within 2015-2025; inclusive study end; not continuous coverage',
    'minimum_observed_2024_days':300,
    'liquidity_definition':'median(daily UTC close * daily summed base-crypto volume)',
    'selection':'Ascending provider-quote turnover proxy, alphabetical asset tie; np.array_split thirds; q=.25,.50,.75 target 1+q*(n-1); nearest currently unused rank then alphabetic asset',
    'limits_not_estimated_from_provider_results':True,
}


def cross_diagnostic(pairs, scope):
    """Inputs contain only already matched valid closes; undefined stats fail."""
    d=pairs.copy()
    d['ratio']=d.ETH/d.BTC
    d['relative_difference']=(d.ratio/d.cross-1).abs()
    d['large_deviation']=d.relative_difference.gt(RULE['large_deviation_relative_difference'])
    n=len(d);days=pd.to_datetime(d['date']).dt.date.nunique() if n else 0
    median=d.relative_difference.median();p95=d.relative_difference.quantile(.95)
    correlation=d.ratio.corr(d.cross) if n>=2 and d.ratio.nunique()>1 and d.cross.nunique()>1 else np.nan
    sufficient=(n>=RULE['minimum_daily_overlap_observations'] if scope=='daily_utc' else
        n>=RULE['minimum_minute_overlap_observations'] and days>=RULE['minimum_minute_overlap_days'])
    passed=bool(sufficient and np.isfinite([median,p95,correlation]).all()
        and median<=RULE['maximum_median_relative_difference']
        and p95<=RULE['maximum_p95_relative_difference']
        and correlation>=RULE['minimum_pearson_level_correlation'])
    return dict(scope=scope,observations=n,overlap_days=days,median_relative_difference=median,
        p95_relative_difference=p95,correlation=correlation,large_deviation_observations=int(d.large_deviation.sum()),
        validation_passed=passed,quote_currency='UNKNOWN',metric_basis='provider quote; dimensionless cross ratio'),d


def stablecoin_diagnostic(asset,daily):
    close=pd.to_numeric(daily.close,errors='coerce')
    valid=daily.aggregation_valid.astype(bool)&np.isfinite(close)&close.gt(0)
    values=close.loc[valid]
    median=values.median();p05=values.quantile(.05);p95=values.quantile(.95)
    passed=bool(len(values)>=RULE['minimum_valid_stablecoin_days']
        and RULE['stablecoin_median_range'][0]<=median<=RULE['stablecoin_median_range'][1]
        and p05>=RULE['stablecoin_p05_floor'] and p95<=RULE['stablecoin_p95_ceiling'])
    return dict(asset=asset,observed_2024_days=len(daily),valid_daily_closes=len(values),
        invalid_aggregation_days=int((~daily.aggregation_valid.astype(bool)).sum()),
        median_daily_close=median,p05=p05,p95=p95,minimum=values.min(),maximum=values.max(),
        validation_passed=passed,price_unit='provider quote units; formal currency UNKNOWN')


def common_quote_status(cross,stable):
    enough_scopes=set(cross.scope)=={'minute_sample','daily_utc'} and len(cross)==2
    enough_stable=len(stable)>=RULE['minimum_available_stablecoins'] and not stable.asset.duplicated().any()
    return VERIFIED if enough_scopes and enough_stable and cross.validation_passed.all() and stable.validation_passed.all() else 'BLOCKED_COMMON_QUOTE_BASIS_NOT_VALIDATED'


def daily_turnover(data):
    """Preserve invalid rows/flags; unknown/invalid aggregates get NaN proxy."""
    d=data.copy()
    volume=pd.to_numeric(d.volume,errors='coerce');close=pd.to_numeric(d.close,errors='coerce')
    product=close*volume
    valid=d.aggregation_valid.astype(bool)&np.isfinite(close)&close.gt(0)&np.isfinite(volume)&volume.ge(0)&np.isfinite(product)
    d['daily_base_volume']=volume
    d['daily_provider_quote_turnover']=product.where(valid)
    d['provider_quote_turnover_valid']=valid
    d['quote_currency']='UNKNOWN'
    return d


def asset_eligibility(row,daily,status):
    reasons=[]; asset=row['ticker'];observed=len(daily)
    if '-' in asset: reasons.append('explicit_cross_pair_excluded')
    if not history_eligible(pd.to_datetime(row['first_date']),pd.to_datetime(row['last_date']),'cryptos'):
        reasons.append('insufficient_3_year_observed_history_span')
    if observed<300: reasons.append('fewer_than_300_observed_2024_utc_days')
    invalid=int((~daily.aggregation_valid.astype(bool)).sum())
    unknown=int((~daily.provider_quote_turnover_valid).sum()) if status==VERIFIED and '-' not in asset else None
    if invalid or unknown: reasons.append('invalid_source_or_undefined_daily_turnover_requires_review')
    if status!=VERIFIED: reasons.append('common_provider_quote_basis_not_validated')
    return dict(asset=asset,asset_class='cryptos',explicit_cross_pair='-' in asset,
        first_observed_date=row['first_date'],last_observed_date=row['last_date'],
        history_eligible_3_years=history_eligible(pd.to_datetime(row['first_date']),pd.to_datetime(row['last_date']),'cryptos'),
        observed_2024_days=observed,invalid_aggregation_days=invalid,undefined_turnover_days=unknown,
        zero_volume_rows=int(daily.zero_volume_rows.sum()),
        invalid_ohlc_rows=int(daily.invalid_ohlc_rows.sum()),
        nonpositive_daily_low_days=int(daily.low.le(0).sum()),
        median_bars_per_observed_day=daily.bars_observed.median(),
        median_daily_base_volume=daily.daily_base_volume.median(),
        median_daily_provider_quote_turnover=daily.daily_provider_quote_turnover.median(),
        liquidity_measure=daily.daily_provider_quote_turnover.median(),
        measure_name='provider-quote turnover proxy',quote_currency='UNKNOWN',
        ranking_eligible=not reasons,exclusion_reason=';'.join(reasons))


def rank_crypto(audit,status):
    if status!=VERIFIED:
        raise ValueError('Common provider quote basis must validate before ranking')
    columns=['asset','asset_class','ranking_eligible','liquidity_measure']
    if not set(columns).issubset(audit):
        raise ValueError('Provider-quote turnover required; native-unit volume is not a fallback')
    allowed=audit[columns].copy()
    allowed=allowed.loc[allowed.ranking_eligible&~allowed.asset.str.contains('-',regex=False)]
    if not np.isfinite(allowed.liquidity_measure).all() or allowed.liquidity_measure.lt(0).any():
        raise ValueError('Invalid provider-quote turnover')
    renamed=allowed.rename(columns={'asset':'provider_root','liquidity_measure':'liquidity_measure_2024','ranking_eligible':'final_eligible'})
    ranked,selected=rank_and_select(renamed)
    rename={'provider_root':'asset','liquidity_measure_2024':'liquidity_measure',
        'liquidity_rank':'liquidity_rank_within_class'}
    ranked=ranked.rename(columns=rename);selected=selected.rename(columns=rename)
    return ranked,selected


def read_minute_sample(path,asset):
    """Read-only full-file prefix scan; parse only fixed timestamp sample rows."""
    before=path.stat();parts=[];scanned=0
    with path.open('r',encoding='utf-8-sig') as stream:
        pilot=list(islice(stream,10))
    if not pilot or any(len(line.strip().split(','))!=6 for line in pilot):
        raise ValueError('Crypto sample pilot failed')
    with path.open('r',encoding='utf-8-sig') as stream:
        offset=1
        while lines:=list(islice(stream,100_000)):
            scanned+=len(lines)
            positions=[i for i,line in enumerate(lines) if line.startswith('2024-')
                and line[11:19] in ('00:00:00','06:00:00','12:00:00','18:00:00')]
            if positions:
                _,parsed=parse_chunk([lines[p] for p in positions],1)
                parsed.index=pd.Index(offset+np.array(positions),name='raw_line_number')
                parts.append(parsed)
            offset+=len(lines)
    data=pd.concat(parts) if parts else pd.DataFrame({'timestamp':pd.Series(dtype='datetime64[ns]'),
        **{f:pd.Series(dtype=float) for f in ['open','high','low','close','volume']}})
    annotated=assign_primary_session(data,'cryptos')
    flags=['missing_value','non_numeric','non_finite','invalid_ohlc','negative_volume','malformed_columns']
    bad=annotated.timestamp.duplicated(keep=False)|annotated.timestamp.isna()
    for flag in flags:
        if flag in annotated: bad |= annotated[flag]
    bad |= ~np.isfinite(annotated.close)|annotated.close.le(0)
    annotated['sample_valid']=~bad
    after=path.stat()
    assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
    return annotated,dict(asset=asset,file_name=path.name,size_bytes=before.st_size,mtime_ns=before.st_mtime_ns,
        raw_rows_scanned=scanned,sampled_observations=len(annotated),valid_sampled_observations=int((~bad).sum()),
        bytes_scanned_approx=before.st_size,source_unchanged=True)


def matched_daily_panels(panels):
    pieces=[]
    for asset,column in [('ETH','ETH'),('BTC','BTC'),('ETH-BTC','cross')]:
        d=panels[asset]
        valid=d.aggregation_valid.astype(bool)&np.isfinite(d.close)&d.close.gt(0)
        piece=d.loc[valid,['date','close','last_timestamp']].rename(columns={'close':column,'last_timestamp':column+'_last_timestamp'})
        if piece.date.duplicated().any(): raise ValueError('Duplicate UTC asset-day')
        pieces.append(piece)
    paired=pieces[0].merge(pieces[1],on='date',validate='one_to_one').merge(pieces[2],on='date',validate='one_to_one')
    times=pd.concat([pd.to_datetime(paired[c+'_last_timestamp'],utc=True) for c in ['ETH','BTC','cross']],axis=1)
    paired['daily_close_alignment_gap_minutes']=(times.max(axis=1)-times.min(axis=1)).dt.total_seconds()/60
    return paired


def protected_hashes():
    directories=[PROJECT/'outputs/diagnostics/universe_selection',PROJECT/'outputs/diagnostics/final_universe/futures_crypto',
        PROJECT/'outputs/diagnostics/final_universe/futures_final']
    files=[p for directory in directories for p in directory.rglob('*') if p.is_file()]
    files += [PROJECT/name for name in ['README.md','design_decisions.md','data_manifest.csv',
        'manifests/data_manifest.csv','data/raw_bloomberg/sha256_manifest.csv'] if (PROJECT/name).is_file()]
    return {str(path.relative_to(PROJECT)):sha256(path) for path in files}


def run():
    started=time.perf_counter();OUT.mkdir(parents=True,exist_ok=True)
    rule_path=OUT/'common_quote_validation_rule.yaml'
    if rule_path.exists():
        if yaml.safe_load(rule_path.read_text(encoding='utf-8'))!=RULE:
            raise ValueError('Prespecified rule differs; no post-result threshold changes permitted')
    else:
        rule_path.write_text(yaml.safe_dump(RULE,sort_keys=False),encoding='utf-8')
    rule_hash=sha256(rule_path)
    protected=protected_hashes()
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    prior_manifest=json.loads((PRIOR/'run_manifest.json').read_text(encoding='utf-8'))
    inventory=pd.read_csv(PRIOR/'crypto_inventory.csv',keep_default_na=False)
    scans=pd.read_csv(PRIOR/'crypto_file_scan_audit.csv',dtype={'mtime_ns':'int64'})
    directory=intraday_root()/'cryptos'
    available={p.name.removesuffix('_full_1min.txt') for p in directory.glob('*_full_1min.txt')}
    if available!=set(inventory.ticker):
        raise ValueError('Crypto raw inventory changed; existing inventory cannot be silently reused')
    for file in ['crypto_inventory.csv','crypto_file_scan_audit.csv']:
        assert sha256(PRIOR/file)==prior_manifest['output_sha256'][file]
    doc_hashes={}
    for name in ['crypto.txt','crypto_ticker_dates_listing.txt']:
        relative='_documentation/.archive/'+name
        path=intraday_root()/relative
        doc_hashes[relative]=sha256(path)
        assert doc_hashes[relative]==prior_manifest['source_document_sha256'][relative]
    # Reuse all 75 daily panels only after derived hashes and exact raw stamps match.
    panels={};source_stamps={}
    for row in inventory.itertuples():
        source=intraday_root()/row.file
        stamp=source.stat();scan=scans.loc[scans.asset.eq(row.ticker)]
        assert len(scan)==1 and stamp.st_size==int(scan.iloc[0].size_bytes) and stamp.st_mtime_ns==int(scan.iloc[0].mtime_ns)
        source_stamps[str(source)]=(stamp.st_size,stamp.st_mtime_ns)
        file=f'crypto_{row.ticker}_2024_daily_ohlcv.csv'
        assert sha256(PRIOR/file)==prior_manifest['output_sha256'][file]
        d=pd.read_csv(PRIOR/file)
        if len(d):
            assert pd.to_datetime(d.date).dt.year.eq(2024).all() and d.timezone.eq('UTC').all()
            assert not d.date.duplicated().any()
        panels[row.ticker]=d
    minute=[];sample_scans=[]
    for asset,column in [('ETH','ETH'),('BTC','BTC'),('ETH-BTC','cross')]:
        print('Read prespecified minute sample '+asset,flush=True)
        sampled,scan=read_minute_sample(directory/f'{asset}_full_1min.txt',asset)
        sampled.to_csv(OUT/f'{asset}_minute_sample_audit.csv',index=True)
        piece=sampled.loc[sampled.sample_valid,['timestamp_local','close']].rename(columns={'close':column})
        minute.append(piece);sample_scans.append(scan)
    sampled=minute[0].merge(minute[1],on='timestamp_local',validate='one_to_one').merge(minute[2],on='timestamp_local',validate='one_to_one')
    sampled['date']=sampled.timestamp_local.dt.date
    minute_summary,minute_detail=cross_diagnostic(sampled,'minute_sample')
    daily_pairs=matched_daily_panels(panels)
    daily_summary,daily_detail=cross_diagnostic(daily_pairs,'daily_utc')
    daily_summary.update(max_daily_close_alignment_gap_minutes=daily_pairs.daily_close_alignment_gap_minutes.max(),
        daily_closes_with_different_timestamps=int(daily_pairs.daily_close_alignment_gap_minutes.gt(0).sum()))
    cross=pd.DataFrame([minute_summary,daily_summary])
    stable=pd.DataFrame([stablecoin_diagnostic(asset,panels[asset]) for asset in RULE['stablecoins'] if asset in panels])
    status=common_quote_status(cross,stable)
    cross['common_quote_status']=status
    cross['validation_rule_sha256']=rule_hash
    cross.to_csv(OUT/'common_quote_validation.csv',index=False)
    stable.to_csv(OUT/'stablecoin_quote_diagnostics.csv',index=False)
    minute_detail.to_csv(OUT/'cross_minute_comparisons.csv',index=False)
    daily_detail.to_csv(OUT/'cross_daily_comparisons.csv',index=False)
    deviations=pd.concat([minute_detail.assign(scope='minute_sample'),daily_detail.assign(scope='daily_utc')],ignore_index=True)
    deviations.loc[deviations.large_deviation].to_csv(OUT/'cross_large_deviations.csv',index=False)
    pd.DataFrame(sample_scans).to_csv(OUT/'minute_sample_scan_audit.csv',index=False)
    records=[];daily_outputs=[]
    for row in inventory.to_dict('records'):
        data=panels[row['ticker']]
        if status==VERIFIED and '-' not in row['ticker']:
            d=daily_turnover(data)
        else:
            d=data.copy();d['daily_base_volume']=d.volume
            d['daily_provider_quote_turnover']=np.nan;d['provider_quote_turnover_valid']=False
        record=asset_eligibility(row,d,status)
        if not record['ranking_eligible']:
            record['liquidity_measure']=np.nan
        records.append(record);daily_outputs.append(d)
    audit=pd.DataFrame(records)
    audit.to_csv(OUT/'crypto_eligibility_audit.csv',index=False)
    all_daily=pd.concat(daily_outputs,ignore_index=True)
    all_daily.to_csv(OUT/'crypto_daily_turnover_audit.csv',index=False)
    audit.to_csv(OUT/'crypto_2024_liquidity.csv',index=False)
    if status==VERIFIED:
        ranked,selected=rank_crypto(audit,status)
        ranked=ranked.merge(audit,on=['asset','liquidity_measure'],how='left',validate='one_to_one')
        selected=ranked.loc[ranked.selected].copy()
    else:
        ranked=pd.DataFrame(columns=['asset','liquidity_measure','liquidity_rank_within_class','liquidity_tier','selected','selection_reason'])
        selected=ranked.copy()
    ranked.to_csv(OUT/'selection_audit.csv',index=False)
    selected.to_csv(OUT/'selected_crypto.csv',index=False)
    frozen=status==VERIFIED and len(selected)==9 and selected.asset.nunique()==9
    if frozen: assert selected.groupby('liquidity_tier').size().eq(3).all()
    spec=dict(status='FROZEN' if frozen else 'BLOCKED',quote_basis_validation_status=status,
        quote_currency='UNKNOWN',literal_usd_denomination_established=False,
        quote_basis='empirically verified common provider quote basis' if status==VERIFIED else 'UNRESOLVED',
        liquidity_measure='provider-quote turnover proxy',
        daily_turnover='UTC daily close * sum(observed one-minute base-crypto volume)',
        liquidity_statistic='median observed 2024 daily turnover',
        not_market_wide_trading_volume=True,only_within_crypto_ranking=True,
        timezone='UTC',volume_unit='individual base-crypto units',liquidity_calibration_year=2024,
        study_start='2015-01-01',study_end='2025-12-31',
        minimum_observed_2024_days=300,minimum_history_years=3,
        history_basis='inclusive observed endpoint span clipped to study window; not continuous completeness',
        source_quality_policy=RULE['quality_policy'],explicit_crosses_excluded=True,
        selection_policy=RULE['selection'],
        selected_assets=selected.asset.tolist(),liquidity_tiers={tier:group.asset.tolist() for tier,group in selected.groupby('liquidity_tier')} if frozen else {},
        common_quote_validation_rule='common_quote_validation_rule.yaml',validation_rule_sha256=rule_hash,
        missing_bar_policy='no filling, imputation, synthesized days or gap compression',
        no_benchmark_or_estimator_selection_inputs=True,
        empirical_scope_limitation='Cross consistency directly tests BTC/ETH versus ETH-BTC and named stablecoins; uniform naming supports common-basis interpretation, not formal per-series currency certification')
    (OUT/'crypto_final_spec.yaml').write_text(yaml.safe_dump(spec,sort_keys=False),encoding='utf-8')
    reasons=audit.loc[~audit.ranking_eligible,['asset','exclusion_reason']]
    stable_missing=sorted(set(RULE['stablecoins'])-set(stable.asset))
    report='# Step 12 crypto common-quote validation and final universe\n\n'
    report+=f'Common quote decision: **{status}**. Final universe status: **{spec["status"]}**. Formal quote currency remains **UNKNOWN**; literal USD denomination is not established. No provider was contacted or external price data used.\n\n'
    report+='The rule was saved and passed synthetic tests before new provider diagnostics: median cross relative difference <=2%, p95 <=10%, correlation >=0.95 in both scopes; sample >=300 observations on >=250 days, daily >=300. At least three prespecified stablecoins are required, and every available named stablecoin needs >=300 valid daily closes, median 0.95-1.05, p05 >=0.90 and p95 <=1.10. These broad economic-consistency limits are not precision estimates. Scaling, inversion and date-misalignment synthetic counterexamples fail. No threshold was changed after observing results.\n\n'
    report+='ETH/BTC checks\n\n'+table_md(cross)+'\n\nStablecoin checks (provider quote units)\n\n'+table_md(stable)+'\n\n'
    report+=f'Missing prespecified stablecoins: {stable_missing}. Large deviations (fixed >10% rule) are recorded observation-by-observation in cross_large_deviations.csv, with UTC dates. Exact-minute sample matching never borrows nearby observations. Daily close timestamp differences are separately audited; observations are not claimed perfectly contemporaneous when end times differ. No exact-price equality is required.\n\n'
    report+='Provider naming: all 75 prior series are reconciled to existing raw files; bare tickers have no explicit quote suffix. BTC-EUR and ETH-BTC explicitly name other quotes and remain excluded. Common provider-basis validation is empirical and limited to the tested anchors plus this naming convention; it is not authoritative currency metadata for every token. Stablecoin behavior is USD-like evidence only, not proof of a formal USD label.\n\n'
    report+=f'Eligibility: {int(audit.ranking_eligible.sum())} of {len(audit)} series. The >=300 observed UTC days and >=3-year history-span rules are preserved. Any invalid aggregation/undefined turnover day blocks the asset, consistent with the prior requirement not to silently change the valid liquidity population by dropping unknown daily totals. All raw OHLCV/quality diagnostics remain unchanged in prior panels and the new daily audit.\n\n'
    report+='Exclusions\n\n'+table_md(reasons)+'\n\nComplete eligible liquidity ranking (provider-quote turnover proxy; not market-wide volume)\n\n'
    display=['asset','liquidity_measure','liquidity_rank_within_class','liquidity_tier','selected']
    report+=table_md(ranked[display])+'\n\nFinal selected assets\n\n'+table_md(selected[display])+'\n\n'
    report+='SHIB / UST source quality\n\n'+table_md(audit.loc[audit.asset.isin(['SHIB','UST']),
        ['asset','invalid_aggregation_days','invalid_ohlc_rows','nonpositive_daily_low_days','ranking_eligible','exclusion_reason']])+'\n\n'
    report+='The proxy is daily close times daily summed base-unit volume, then the median across observed 2024 days. It is not sum(minute close times minute volume), USD dollar volume, raw native-unit volume ranking, or market-wide trading volume. Aggregated exchange composition, stale daily end observations, stablecoin deviations, endpoint-only history evidence, survivorship/coverage and calibration-year conditioning remain limitations. Common quote consistency does not verify every series individually or establish price adjustment conventions.\n\n'
    report+='Step-9 daily aggregates are reused only after saved SHA-256 hashes and raw size/mtime stamps reconcile; detailed current raw reads are restricted to the three predetermined minute samples. Reproduce with src/crypto_final_universe.py. No provider Roll, CS, AR or EDGE values or performance were calculated. Earlier Step-4/9 outputs, futures freezes, raw files and protected documentation remain unchanged.\n'
    (OUT/'step12_review.md').write_text(report,encoding='utf-8')
    assert protected==protected_hashes()
    assert sha256(rule_path)==rule_hash
    for file,stamp in source_stamps.items():
        current=Path(file).stat();assert (current.st_size,current.st_mtime_ns)==stamp
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    manifest=dict(status=spec['status'],quote_basis_validation_status=status,rule_sha256=rule_hash,
        eligible_assets=int(audit.ranking_eligible.sum()),selected_assets=selected.asset.tolist(),
        prior_outputs_sha256=protected,raw_source_stamps=source_stamps,
        provider_document_sha256=doc_hashes,raw_bloomberg_hashes_verified=len(raw),
        runtime_seconds=time.perf_counter()-started,bytes_scanned_approx=sum(row['bytes_scanned_approx'] for row in sample_scans),
        no_benchmark_or_estimator_calculations=True,raw_provider_writes=0,
        output_sha256={path.name:sha256(path) for path in OUT.glob('*') if path.is_file() and path.name!='run_manifest.json'})
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(table_md(cross));print(table_md(stable));print('Decision:',status,'eligible:',int(audit.ranking_eligible.sum()))
    print(selected[display].to_string(index=False))


if __name__=='__main__': run()
