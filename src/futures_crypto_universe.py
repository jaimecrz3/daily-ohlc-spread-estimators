"""Step 9 inventories and evidence-gated liquidity preparation, never estimators.

Run: .venv/Scripts/python.exe -B src/futures_crypto_universe.py
No new source data or market prices are downloaded. Continuous price files
are inventoried by filename only, never read. Unknown sessions/currencies block
ranking. The two validated pilots do not become a forced final selection.
"""
from pathlib import Path
from itertools import islice
from fractions import Fraction
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import time

import numpy as np
import pandas as pd

try:
    from .data_io import intraday_root, last_nonempty_line, is_timestamp
    from .eda_diagnostics import parse_chunk
    from .session_rules import assign_primary_session, FUTURES_SESSIONS
    from .daily_aggregation import aggregate_daily_ohlcv
    from .futures_roll import parse_provider_calendar, selection_plan, contract_file, read_contract_window, validate_sessions, table_md
except ImportError:
    from data_io import intraday_root, last_nonempty_line, is_timestamp
    from eda_diagnostics import parse_chunk
    from session_rules import assign_primary_session, FUTURES_SESSIONS
    from daily_aggregation import aggregate_daily_ohlcv
    from futures_roll import parse_provider_calendar, selection_plan, contract_file, read_contract_window, validate_sessions, table_md

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / 'outputs/diagnostics/final_universe/futures_crypto'
CONTRACT = re.compile(r'^([A-Z0-9]+)_([FGHJKMNQUVXZ]\d{2})_1min\.txt$')
SELECT_COLUMNS = ['asset', 'asset_class', 'liquidity_measure', 'liquidity_rank', 'liquidity_tier',
    'liquidity_rank_within_tier', 'selection_quantile_target', 'selection_target_rank',
    'selection_rank_distance', 'selected', 'selection_reason']
CRYPTO_SUFFIX = '_full_1min.txt'
SESSION_EVIDENCE = {
    'ES': dict(status='VERIFIED_COMPATIBLE', source='https://www.cmegroup.com/content/dam/cmegroup/notices/ser/2021/06/SER-8788.pdf;https://www.cmegroup.com/tools-information/lookups/advisories/electronic-trading/20150914.html',
        basis='Step 11 source correction: CME SER-8788 section 5 eliminated the afternoon equity halt effective 2021-06-28; the 2015 notice established the 16:00 CT close. The unchanged 18:00-17:00 ET ES pilot envelope is correct for normal 2024 sessions. Historical date-effective changes are configured separately in Step 11.',
        scope='documented normal session envelope supporting 2024 pilot; full 2015-2025 exchange schedule changes/holidays not certified'),
    'CL': dict(status='VERIFIED_COMPATIBLE', source='https://www.cmegroup.com/education/courses/event-contracts-underlying-markets/wti-overview',
        basis='CME WTI product overview identifies CL 17:00 to 16:00 America/Chicago with one-hour maintenance. Converted to America/New_York: 18:00 to 17:00. Prior Step-5 pilot validated mapping/evening handling.',
        scope='documented normal session envelope supporting 2024 pilot; full 2015-2025 exchange schedule changes/holidays not certified'),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def endpoint_info(path):
    """Bounded physical endpoints, never claim globally scanned date extrema."""
    before = path.stat()
    with path.open('r', encoding='utf-8-sig', newline='') as stream:
        first = next((line.rstrip('\r\n') for line in islice(stream, 10) if line.strip()), '')
    last, tail_bytes = last_nonempty_line(path)
    begin, end = first.split(',', 1)[0], last.split(',', 1)[0]
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Raw source changed during endpoint read')
    valid = is_timestamp(begin) and is_timestamp(end)
    return dict(first_observation=begin if valid else '', last_observation=end if valid else '',
        endpoint_status='ok' if valid else 'unassignable_endpoint',
        size_bytes=before.st_size, mtime_ns=before.st_mtime_ns,
        bytes_read_approx=len(first.encode('utf-8'))+tail_bytes,
        endpoint_basis='first/last nonempty physical records; within-file global order/extrema not certified')


def root_session_review(root):
    evidence = SESSION_EVIDENCE.get(root)
    return dict(root=root, session_status=evidence['status'] if evidence else 'UNRESOLVED',
        timezone='America/New_York', timezone_evidence='_documentation/.archive/futures.txt: US Eastern Time',
        session_start_local='18:00 previous calendar day' if evidence else '',
        session_end_local='17:00 trade date exclusive' if evidence else '',
        trade_date_convention='overnight_ending_date' if evidence else '',
        session_evidence_source=evidence['source'] if evidence else '_documentation/.archive/futures.txt; no root-specific hours',
        evidence_basis=evidence['basis'] if evidence else 'No verified product-specific session record available; no extrapolation from exchange name or ES/CL',
        evidence_scope=evidence['scope'] if evidence else 'root-specific session and trade-date evidence required',
        existing_pilot=root in {'ES','CL'}, review_date='2026-10-13')


def futures_inventory(root_path):
    directory = root_path / 'futures'
    metadata_path = root_path / '_documentation/.archive/futures_ticker_dates_listing.txt'
    metadata = pd.read_csv(metadata_path, dtype=str, keep_default_na=False)
    groups = {key:group for key,group in metadata.groupby('Ticker')}
    paths, maps, continuous = {}, {}, {}
    for path in sorted(directory.iterdir()):
        match = CONTRACT.fullmatch(path.name)
        if match:
            paths.setdefault(match.group(1), []).append(path)
        elif path.name.endswith('_continuous_contract_dates.txt'):
            maps[path.name.removesuffix('_continuous_contract_dates.txt')] = path
        elif path.suffix.lower() == '.txt':
            # Filename-only audit: no continuous/unknown prices read.
            continuous.setdefault(path.name.split('_')[0], []).append(path.name)
    records, files, mapping_audit, reviews = [], [], [], []
    for root in sorted(set(paths) | set(maps) | set(continuous) | set(groups)):
        print(f'Inventory futures {root}: {len(paths.get(root, []))} individual files', flush=True)
        details = []
        root_files = paths.get(root, [])
        # Mounted cloud files can require fetching a whole contract merely to
        # seek its tail. Inventory ALL filenames, but use bounded deterministic
        # oldest/newest maturity probes instead of forcing 14,503 content reads.
        # Probed limits are never misrepresented as full-root date extrema.
        months = 'FGHJKMNQUVXZ'
        ordered = sorted(root_files, key=lambda p:(int(CONTRACT.fullmatch(p.name).group(2)[1:]), months.index(CONTRACT.fullmatch(p.name).group(2)[0]), p.name))
        probes = list(dict.fromkeys(ordered[:1]+ordered[-1:]))
        with ThreadPoolExecutor(max_workers=8) as readers:
            endpoints = list(readers.map(endpoint_info, probes))
        lookup = dict(zip(probes,endpoints))
        for path in root_files:
            info = lookup.get(path, dict(first_observation='',last_observation='',endpoint_status='not_probed_metadata_only',size_bytes=None,mtime_ns=None,bytes_read_approx=0,endpoint_basis='filename inventory only; no content read'))
            if path in lookup:
                details.append(info)
            files.append(dict(root=root, contract_code=CONTRACT.fullmatch(path.name).group(2), file=path.relative_to(root_path).as_posix(), **info))
        review = root_session_review(root)
        reviews.append(review)
        group = groups.get(root)
        name = ' | '.join(sorted(set(group.Name))) if group is not None else ''
        exchange_match = re.search(r'\(([^()]*)\)', name)
        calendar_status, calendar_reason, map_rows, mapped_2024 = 'missing', '', 0, 0
        if root in maps:
            try:
                calendar = parse_provider_calendar(maps[root])
                map_rows = len(calendar)
                mapped_2024 = int(calendar.provider_mapping_date.between('2024-01-01', '2024-12-31').sum())
                calendar_status = 'usable_exact_daily_mapping'
            except Exception as exc:
                calendar_status, calendar_reason = 'invalid', f'{type(exc).__name__}: {exc}'
            mapping_audit.append(dict(root=root, file=maps[root].relative_to(root_path).as_posix(), sha256=digest(maps[root]), mapping_status=calendar_status, mapping_rows=map_rows, mapped_2024_calendar_dates=mapped_2024, reason=calendar_reason))
        valid = [info for info in details if info['endpoint_status']=='ok']
        complete_endpoints = len(details)==len(root_files)
        records.append(dict(root=root, descriptive_name=name,
            available_individual_contracts=json.dumps([CONTRACT.fullmatch(p.name).group(2) for p in paths.get(root, [])]),
            earliest_individual_contract_observation=min((i['first_observation'] for i in valid), default='') if complete_endpoints else '',
            latest_individual_contract_observation=max((i['last_observation'] for i in valid), default='') if complete_endpoints else '',
            earliest_probed_individual_observation=min((i['first_observation'] for i in valid), default=''),
            latest_probed_individual_observation=max((i['last_observation'] for i in valid), default=''),
            individual_contract_files=len(root_files), endpoint_probes=len(details), invalid_endpoint_files=len(details)-len(valid),
            endpoint_basis='all contract filenames inventoried; oldest/newest maturity endpoint probes only; full-root extrema unresolved unless <=2 files',
            provider_root_first_date=group['First Date'].min() if group is not None else '',
            provider_root_last_date=group['Last Date'].max() if group is not None else '',
            provider_roll_metadata_exists=root in maps, provider_mapping_status=calendar_status,
            provider_mapping_reason=calendar_reason, mapped_2024_calendar_dates=mapped_2024,
            continuous_series_exists_locally=bool(continuous.get(root)),
            continuous_files=json.dumps(continuous.get(root, [])),
            provider_continuous_series_documented=group is not None,
            continuous_documentation_basis='futures_ticker_dates_listing describes provider root availability; not proof of mounted continuous price file',
            exchange=exchange_match.group(1) if exchange_match else '',
            exchange_evidence='provider descriptive label' if exchange_match else 'unavailable',
            product_family='not separately provided; descriptive_name retained without inference',
            known_session_status=review['session_status'], timezone='America/New_York'))
    return pd.DataFrame(records), pd.DataFrame(files), pd.DataFrame(reviews), pd.DataFrame(mapping_audit)


def rank_and_select(data, cls):
    """Allowlisted volume/notional ranking; 9+ eligible members required for tiers."""
    columns = ['asset', 'asset_class', 'liquidity_measure', 'ranking_eligible']
    candidates = data[columns].copy()
    candidates = candidates.loc[candidates.ranking_eligible & np.isfinite(candidates.liquidity_measure)]
    candidates = candidates.sort_values(['liquidity_measure','asset'], kind='stable').reset_index(drop=True)
    candidates['liquidity_rank'] = np.arange(1,len(candidates)+1)
    candidates['liquidity_tier'] = ''
    candidates['liquidity_rank_within_tier'] = pd.Series(pd.NA, index=candidates.index, dtype='Int64')
    candidates['selection_quantile_target'] = np.nan
    candidates['selection_target_rank'] = np.nan
    candidates['selection_rank_distance'] = np.nan
    candidates['selected'] = False
    candidates['selection_reason'] = 'insufficient_eligible_assets_for_three_per_tier' if len(candidates)<9 else 'not_nearest_quantile_rank'
    if len(candidates)>=9:
        picks=[]
        for tier, indices in zip(['LOW','MEDIUM','HIGH'],np.array_split(np.arange(len(candidates)),3)):
            candidates.loc[indices,'liquidity_tier'] = tier
            candidates.loc[indices,'liquidity_rank_within_tier'] = np.arange(1,len(indices)+1)
            for quantile in [Fraction(1,4),Fraction(1,2),Fraction(3,4)]:
                target=1+quantile*(len(indices)-1)
                pick = min(indices, key=lambda i:(abs(Fraction(int(candidates.loc[i,'liquidity_rank_within_tier']))-target),candidates.loc[i,'asset']))
                picks.append((pick,quantile,target))
        if len({p[0] for p in picks})!=9:
            candidates['selection_reason']='quantile_targets_not_distinct; no silent nearest-unselected substitution'
        else:
            for pick,quantile,target in picks:
                candidates.loc[pick, ['selection_quantile_target','selection_target_rank','selection_rank_distance','selected','selection_reason']] = [float(quantile),float(target),float(abs(Fraction(int(candidates.loc[pick,'liquidity_rank_within_tier']))-target)),True,'nearest actual rank to 1+q*(n-1); alphabetical ticker breaks exact distance ties']
    return candidates[SELECT_COLUMNS], candidates.loc[candidates.selected, SELECT_COLUMNS].copy()


def crypto_quote_review(ticker, descriptive_name):
    cross = '-' in ticker
    quote = ticker.rsplit('-',1)[1] if cross else ''
    return dict(ticker=ticker, explicit_cross_pair=cross, explicit_quote_currency=quote,
        quote_currency_status='explicit_non_common_quote_cross_pair' if cross else 'UNRESOLVED',
        quote_currency_evidence_source='_documentation/.archive/crypto_ticker_dates_listing.txt and exact explicit pair filename' if cross else '_documentation/.archive/crypto.txt; crypto_ticker_dates_listing.txt; provider online crypto listing: no bare-series quote currency',
        quote_currency_evidence=f'Provider label {descriptive_name!r}, explicit {ticker} pair' if cross else 'UTC timestamps and native crypto-unit volume documented; no base/quote mapping for bare ticker',
        common_currency_verified=False, eligibility_status='excluded_explicit_cross_pair' if cross else 'blocked_quote_currency_unresolved')


def crypto_rank(data):
    """Fail closed globally; never use native-unit volume as a fallback ranking."""
    bare = data.loc[~data.explicit_cross_pair]
    if bare.empty or not bare.common_currency_verified.eq(True).all() or bare.explicit_quote_currency.nunique()!=1:
        return pd.DataFrame(columns=SELECT_COLUMNS), pd.DataFrame(columns=SELECT_COLUMNS), 'quote_currency_unresolved_or_not_one_common_currency'
    allowed = bare.loc[bare.observed_2024_calendar_days.ge(300) & bare.history_eligible_3_years].copy()
    if 'median_daily_notional_turnover' not in allowed:
        return pd.DataFrame(columns=SELECT_COLUMNS), pd.DataFrame(columns=SELECT_COLUMNS), 'daily_close_times_daily_volume_not_computed'
    allowed['asset']=allowed.ticker
    allowed['asset_class']='cryptos'
    allowed['liquidity_measure']=allowed.median_daily_notional_turnover
    allowed['ranking_eligible']=np.isfinite(allowed.liquidity_measure)
    audit, selected=rank_and_select(allowed,'cryptos')
    return audit, selected, '' if len(selected)==9 else 'insufficient_eligible_crypto_assets_for_three_per_tier'


def crypto_2024(path):
    """One bounded full-file timestamp-prefix scan; parse only 2024 observations."""
    before=path.stat(); parts=[]; scanned=0
    with path.open('r',encoding='utf-8-sig',newline='') as stream:
        offset=1
        while lines:=list(islice(stream,100_000)):
            scanned+=len(lines)
            positions=[i for i,line in enumerate(lines) if line.startswith('2024-')]
            if positions:
                _,parsed=parse_chunk([lines[i] for i in positions],1)
                parsed.index=pd.Index([offset+i for i in positions],name='raw_line_number')
                parts.append(parsed)
            offset+=len(lines)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise RuntimeError('Crypto raw file changed while reading')
    data=pd.concat(parts) if parts else pd.DataFrame({'timestamp':pd.Series(dtype='datetime64[ns]'),**{f:pd.Series(dtype=float) for f in ['open','high','low','close','volume']}})
    daily=aggregate_daily_ohlcv(data,path.name.removesuffix(CRYPTO_SUFFIX),'cryptos',source_file=str(path))
    return daily, dict(raw_rows_scanned=scanned,size_bytes=before.st_size,mtime_ns=before.st_mtime_ns,
        unassignable_2024_prefix_rows=int(data.timestamp.isna().sum()),source_unchanged=True,
        scan_scope='full file timestamp-prefix scan; detailed OHLCV parsing for 2024-prefix rows only; no sorted-file assumption')


def futures_calibration(root_path, root):
    if root not in SESSION_EVIDENCE or root not in FUTURES_SESSIONS:
        raise ValueError('Cannot apply pilot session to an unresolved root')
    directory=root_path/'futures'
    calendar=parse_provider_calendar(directory/f'{root}_continuous_contract_dates.txt')
    plan=selection_plan(calendar,root,'2023-12-25','2024-12-31',directory)
    bars,errors,scans={}, {}, []
    for code in sorted(plan.selected_contract.dropna().unique()):
        path=contract_file(directory,root,code)
        if not path.is_file():
            continue
        print(f'Calibration futures {root}/{code}',flush=True)
        try:
            data,scan=read_contract_window(path,root,code,'2023-12-25','2024-12-31',OUT/'read_audits')
            wanted=set(plan.loc[plan.selected_contract.eq(code),'trade_date'])
            # Filter to provider-selected sessions before any volume aggregation.
            bars[code]=data.loc[data.trade_date.isin(wanted) | (data.maintenance_interval & data.timestamp_local.dt.date.isin(wanted))].copy()
            scans.append(scan)
        except Exception as exc:
            errors[code]=str(exc)
    sessions,selected=validate_sessions(plan,bars,read_errors=errors)
    sessions=sessions.loc[pd.to_datetime(sessions.trade_date).dt.year.eq(2024)].copy()
    selected=selected.loc[pd.to_datetime(selected.trade_date).dt.year.eq(2024)].copy()
    daily=aggregate_daily_ohlcv(selected,root,'futures',futures_root=root,futures_audit=sessions)
    sessions.to_csv(OUT/f'{root}_2024_session_audit.csv',index=False)
    daily.to_csv(OUT/f'{root}_2024_daily_volume.csv',index=False)
    transitions=sessions.loc[sessions.roll_day,['root','trade_date','selected_contract','previous_contract','provider_mapping_date','provider_transition_date','previous_evening_rows','previous_evening_present','first_timestamp','last_timestamp']]
    transitions.to_csv(OUT/f'{root}_2024_transition_safety.csv',index=False)
    invalid=int((~daily.aggregation_valid).sum())
    # User did not specify a final futures day cutoff: retain a transparent
    # diagnostic gate only; final threshold must still be reviewed.
    provisional_coverage=len(daily)>=200
    record=dict(root=root,asset=root,asset_class='futures',observed_2024_trade_dates=len(daily),
        median_daily_contract_volume=daily.volume.median(),p25_daily_contract_volume=daily.volume.quantile(.25),
        p75_daily_contract_volume=daily.volume.quantile(.75),zero_volume_rows=int(daily.zero_volume_rows.sum()),
        days_with_zero_volume_rows=int(daily.zero_volume_rows.gt(0).sum()),
        missing_mapped_sessions=int((sessions.selected_contract.notna()&sessions.bars_observed.eq(0)).sum()),
        missing_provider_mapping_dates=int(sessions.selected_contract.isna().sum()),
        missing_contract_file_dates=int(sessions.validation_reason.eq('missing_individual_contract_file').sum()),
        roll_days=int(sessions.roll_day.sum()),first_usable_date=daily.date.min(),last_usable_date=daily.date.max(),
        invalid_aggregation_days=invalid,selected_contract_read_failures=len(errors),
        transitions_checked=len(transitions),transition_sessions_without_previous_evening=int((~transitions.previous_evening_present).sum()),
        known_session_status=SESSION_EVIDENCE[root]['status'],
        provisional_minimum_2024_days=200,futures_specific_coverage_cutoff_status='not frozen; 200 is transparent diagnostic screen only',
        liquidity_measure=daily.volume.median(),ranking_eligible=bool(provisional_coverage and not invalid and not errors),
        ranking_scope='eligible verified pilot roots only; incomplete full-root session review; not a final population',
        ranking_exclusion_reason='' if provisional_coverage and not invalid and not errors else 'insufficient_or_invalid_observed_pilot_sessions')
    if not len(transitions) or transitions.selected_contract.eq(transitions.previous_contract).any():
        raise ValueError('Missing/invalid contract-transition safety check')
    return record,scans


def run():
    started=time.perf_counter()
    OUT.mkdir(parents=True,exist_ok=True); (OUT/'read_audits').mkdir(exist_ok=True)
    root_path=intraday_root()
    (OUT/'run_manifest.json').write_text(json.dumps({'status':'in_progress','step':9}),encoding='utf-8')
    docs=[root_path/'_documentation/.archive'/name for name in ['futures.txt','futures_ticker_dates_listing.txt','crypto.txt','crypto_ticker_dates_listing.txt']]
    doc_hashes={p.relative_to(root_path).as_posix():digest(p) for p in docs}
    inv,files,sessions,mappings=futures_inventory(root_path)
    inv.to_csv(OUT/'futures_root_inventory.csv',index=False)
    files.to_csv(OUT/'futures_contract_file_inventory.csv',index=False)
    sessions.to_csv(OUT/'futures_session_review.csv',index=False)
    mappings.to_csv(OUT/'futures_mapping_audit.csv',index=False)
    liquidity,scans,failures=[],[],[]
    for root in sorted(SESSION_EVIDENCE):
        try:
            record,reads=futures_calibration(root_path,root)
            liquidity.append(record); scans+=reads
        except Exception as exc:
            failures.append(dict(asset_class='futures',asset=root,reason=f'{type(exc).__name__}: {exc}'))
    fliq=pd.DataFrame(liquidity)
    fliq.to_csv(OUT/'futures_2024_liquidity.csv',index=False)
    faudit,fselected=rank_and_select(fliq,'futures')
    full_audit=inv[['root','known_session_status','provider_mapping_status','individual_contract_files']].rename(columns={'root':'asset'})
    full_audit['asset_class']='futures'
    full_audit=full_audit.merge(faudit,on=['asset','asset_class'],how='left',validate='one_to_one')
    full_audit['selected']=full_audit.selected.fillna(False).astype(bool)
    full_audit['selection_reason']=full_audit.selection_reason.fillna('excluded_from_ranking: unresolved_session_or_missing_usable_mapping/data')
    full_audit.to_csv(OUT/'futures_selection_audit.csv',index=False)
    fselected.to_csv(OUT/'selected_futures.csv',index=False)
    crypto_meta=pd.read_csv(docs[-1],dtype=str,keep_default_na=False)
    names={k:' | '.join(sorted(set(g.Name))) for k,g in crypto_meta.groupby('Ticker')}
    crypto,quote_reviews,cscans=[],[],[]
    for path in sorted((root_path/'cryptos').glob('*'+CRYPTO_SUFFIX)):
        ticker=path.name.removesuffix(CRYPTO_SUFFIX)
        print(f'Inventory/calibration crypto {ticker}',flush=True)
        endpoints=endpoint_info(path)
        quote=crypto_quote_review(ticker,names.get(ticker,''))
        quote_reviews.append(quote)
        try:
            daily,scan=crypto_2024(path)
            daily.to_csv(OUT/f'crypto_{ticker}_2024_daily_ohlcv.csv',index=False)
            cscans.append(dict(asset=ticker,asset_class='cryptos',**scan))
            first,last=endpoints['first_observation'],endpoints['last_observation']
            lo=max(pd.Timestamp(first),pd.Timestamp('2015-01-01')) if first else pd.NaT
            hi=min(pd.Timestamp(last),pd.Timestamp('2025-12-31')) if last else pd.NaT
            history=bool(not pd.isna(lo) and not pd.isna(hi) and hi+pd.Timedelta(days=1)>=lo+pd.DateOffset(years=3))
            crypto.append(dict(descriptive_label=names.get(ticker,''),
                file=path.relative_to(root_path).as_posix(),first_date=first[:10],last_date=last[:10],
                observed_2024_calendar_days=len(daily),median_daily_close=daily.close.median(),
                median_daily_volume=daily.volume.median(),zero_volume_rows=int(daily.zero_volume_rows.sum()),
                invalid_aggregation_days=int((~daily.aggregation_valid).sum()),
                history_eligible_3_years=history,endpoint_basis=endpoints['endpoint_basis'],
                **quote, median_daily_notional_turnover=np.nan,
                notional_status='not computed: quote currency unresolved or explicit non-common-quote cross pair',
                native_unit_volume_role='per-series descriptive diagnostic only; never ranked across cryptocurrencies'))
        except Exception as exc:
            failures.append(dict(asset_class='cryptos',asset=ticker,reason=f'{type(exc).__name__}: {exc}'))
            crypto.append(dict(descriptive_label=names.get(ticker,''),
                first_date=endpoints['first_observation'][:10],last_date=endpoints['last_observation'][:10],
                observed_2024_calendar_days=0,median_daily_close=np.nan,median_daily_volume=np.nan,
                history_eligible_3_years=False,**quote,read_failure=str(exc)))
        # Derived inventory checkpoint permits interruption review, never final selection.
        pd.DataFrame(crypto).to_csv(OUT/'crypto_inventory.csv',index=False)
    cinv=pd.DataFrame(crypto)
    pd.DataFrame(quote_reviews).to_csv(OUT/'crypto_quote_currency_review.csv',index=False)
    cinv.to_csv(OUT/'crypto_inventory.csv',index=False)
    cinv[['ticker','observed_2024_calendar_days','median_daily_close','median_daily_volume','median_daily_notional_turnover','notional_status','native_unit_volume_role','eligibility_status']].to_csv(OUT/'crypto_2024_liquidity.csv',index=False)
    caudit,cselected,crypto_block=crypto_rank(cinv)
    caudit=cinv[['ticker','eligibility_status','explicit_cross_pair','history_eligible_3_years','observed_2024_calendar_days']].rename(columns={'ticker':'asset'}).assign(asset_class='cryptos').merge(caudit,on=['asset','asset_class'],how='left',validate='one_to_one')
    caudit['selected']=caudit.selected.fillna(False).astype(bool)
    caudit['selection_reason']=caudit.selection_reason.fillna(caudit.eligibility_status)
    caudit.to_csv(OUT/'crypto_selection_audit.csv',index=False)
    cselected.to_csv(OUT/'selected_crypto.csv',index=False)
    pd.DataFrame(cscans).to_csv(OUT/'crypto_file_scan_audit.csv',index=False)
    pd.DataFrame(scans).to_csv(OUT/'futures_file_scan_audit.csv',index=False)
    pd.DataFrame(failures,columns=['asset_class','asset','reason']).to_csv(OUT/'failures.csv',index=False)
    assert doc_hashes=={p.relative_to(root_path).as_posix():digest(p) for p in docs}
    report='# Step 9 futures and crypto universe preparation\n\n'
    report+=f'Inventoried {len(inv)} roots (union of local contracts, calendars and provider listing); {len(files)} individual files. {int(sessions.session_status.ne("UNRESOLVED").sum())} roots have documented compatible frozen pilot session envelopes. All other roots remain UNRESOLVED; exchange names are not session evidence. Continuous series availability in the provider description is separate from mounted filenames. No continuous prices were read.\n\n'
    report+='ES and CL session evidence: [CME ES FAQ, section 8]('+SESSION_EVIDENCE['ES']['source']+'); [CME CL WTI overview]('+SESSION_EVIDENCE['CL']['source']+'). Source metadata futures.txt specifies US Eastern timestamps and contract-unit volume. Source checks support the enclosing normal session, not complete historical exchange schedules. ES internal trading pause is not filled. Existing primary clock rules remain unchanged.\n\n'
    report+='Inventory date limitation: all individual filenames are listed, but only the oldest/newest maturity files are endpoint-probed per root. Cloud-drive tail reads can fetch whole contracts; forcing 14,503 content reads is avoided. Probed observed dates and provider root dates are separate columns. Full-root earliest/latest individual dates remain blank/unresolved where not exhaustively established; continuous/root-listing dates are never substituted for them.\n\n'
    report+='2024 verified-pilot volume ranking (not a complete futures-universe ranking):\n\n'+table_md(faudit[['asset','liquidity_measure','liquidity_rank','selection_reason']])+'\n\n'
    report+='Daily liquidity is median observed selected-contract volume, without dollar multipliers. Sessions use exactly one provider-mapped individual contract, including previous-evening bars; empty calendar dates stay in the audit, never become zero daily volume. Transition/evening safety tables are saved for both pilots. Missing mapped sessions include nontrading calendar dates; causes are not inferred from absence.\n\n'
    report+='Final futures selection is blocked: fewer than nine eligible session-verified roots, so no tiers or forced ES/CL selections. A final futures-specific sufficient-days threshold was not specified; 200 days is an explicit diagnostic gate only and must be reviewed before final freeze. Other products require actual root-specific source hours, breaks and trade-date rules, plus usable mapping and observation checks. Historical 2015-2025 schedule changes and late-2025 missing ES H26 / CL F26,G26 files remain limitations from prior audits.\n\n'
    report+=f'Crypto: {len(cinv)} local series; {int(cinv.explicit_cross_pair.sum())} explicit cross pairs. Native daily close and volume are per-series descriptive statistics only. Daily turnover would be daily close times daily summed volume (the Step-9 definition), not the Step-4 intraday close-times-volume sum. No native-unit ranking or notional calculation was performed.\n\n'
    report+='Crypto ranking blocked: '+crypto_block+'. crypto.txt documents UTC and crypto units but no bare-ticker quote denomination. crypto_ticker_dates_listing provides names/dates, not quote metadata. BTC-EUR and ETH-BTC labels explicitly establish EUR/BTC cross quotes; neither provides normalization for bare symbols. The [provider crypto listing](https://firstratedata.com/it/crypto) also lists these cross pairs without establishing bare-series denomination. Obtain authoritative provider base/quote metadata explicitly covering the mounted bare series and common currency, then apply 300 observed UTC days and the previously frozen three-year history rule.\n\n'
    report+='selected_futures.csv and selected_crypto.csv are headers-only blocked-selection outputs. All previous pilot/daily aggregation work is preserved. No benchmark/estimator values, performance, company familiarity or continuous adjusted prices enter any ranking. Bloomberg raw files, First Rate raw files, README.md, design_decisions.md and data_manifest.csv are untouched.\n'
    (OUT/'step9_review.md').write_text(report,encoding='utf-8')
    manifest=dict(status='complete_with_explicit_selection_blocks' if not failures else 'incomplete_read_failures',step=9,
        futures_roots=len(inv),individual_contract_files=len(files),crypto_series=len(cinv),
        session_verified_roots=int(sessions.session_status.ne('UNRESOLVED').sum()),
        futures_selected=len(fselected),crypto_selected=len(cselected),crypto_ranking_block=crypto_block,
        source_document_sha256=doc_hashes,raw_provider_writes=0,continuous_price_reads=0,
        benchmark_or_estimator_inputs_used=False,native_crypto_volume_ranking=False,
        inserted_bars=0,inserted_analytic_days=0,futures_min_days_status='200 diagnostic screen, final sufficient-days cutoff pending',
        source_evidence=SESSION_EVIDENCE,failures=failures,runtime_seconds=time.perf_counter()-started,
        approximate_bytes_scanned=sum(s['size_bytes'] for s in cscans)+sum(s['file_size_bytes'] for s in scans)+int(files.bytes_read_approx.sum()))
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(manifest,indent=2),flush=True)
    if failures:
        raise RuntimeError('Read failures must be reviewed: failures.csv')


if __name__=='__main__':
    run()
