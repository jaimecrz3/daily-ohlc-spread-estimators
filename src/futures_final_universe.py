"""Step 11 fixed economic candidates, verified sessions, contract-volume selection.

No benchmark/estimator imports. Only exact provider daily mappings and individual
contracts are read. Candidate family and nearest-unused policy precede all reads.
"""
from datetime import time as clock
from fractions import Fraction
from pathlib import Path
import json
import re
import time

import numpy as np
import pandas as pd

try:
    from .data_io import intraday_root
    from .session_rules import FuturesSessionConfig
    from .futures_roll import (parse_provider_calendar, selection_plan,
        read_contract_window, validate_sessions, contract_file, table_md)
    from .daily_aggregation import aggregate_daily_ohlcv
    from .bloomberg_io import sha256, verify_hashes, require_verified
except ImportError:
    from data_io import intraday_root
    from session_rules import FuturesSessionConfig
    from futures_roll import (parse_provider_calendar, selection_plan,
        read_contract_window, validate_sessions, contract_file, table_md)
    from daily_aggregation import aggregate_daily_ohlcv
    from bloomberg_io import sha256, verify_hashes, require_verified

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / 'outputs/diagnostics/final_universe/futures_final'
# Exact local provider descriptions, NOT guessed exchange-to-root permutations.
PRODUCTS = (
    ('ES', 'E-mini S&P 500', 'EQUITY_INDEX', 'E-Mini S&P 500 Futures (CME)'),
    ('NQ', 'E-mini Nasdaq-100', 'EQUITY_INDEX', 'E-Mini Nasdaq-100 Futures (CME)'),
    ('RTY', 'E-mini Russell 2000', 'EQUITY_INDEX', 'E-Mini Russell 2000 (CME)'),
    ('ZT', '2-Year Treasury Note', 'US_TREASURIES', '2-Year Treasury Note Futures (CBOT)'),
    ('ZF', '5-Year Treasury Note', 'US_TREASURIES', '5-Year Treasury Note Futures (CBOT)'),
    ('ZN', '10-Year Treasury Note', 'US_TREASURIES', '10-Year Treasury Note Futures (CBOT)'),
    ('ZB', 'Treasury Bond', 'US_TREASURIES', '30 Year Us Treasury Bond Future (CBOT)'),
    ('CL', 'WTI Crude Oil', 'ENERGY', 'Crude Oil Wti Futures (NYMEX)'),
    ('NG', 'Henry Hub Natural Gas', 'ENERGY', 'Henry Hub Natural Gas Futures (NYMEX)'),
    ('GC', 'Gold', 'METALS', 'Gold Futures (CME)'),
    ('SI', 'Silver', 'METALS', 'Silver Futures (CME)'),
    ('HG', 'Copper', 'METALS', 'Copper Futures (CME)'),
    ('6E', 'Euro FX', 'CME_CURRENCY', 'Euro FX Futures (CME)'),
    ('6J', 'Japanese Yen', 'CME_CURRENCY', 'Japanese Yen Futures (CME)'),
    ('6B', 'British Pound', 'CME_CURRENCY', 'British Pound Futures (CME)'),
    ('6A', 'Australian Dollar', 'CME_CURRENCY', 'Australian Dollar Futures (CME)'),
    ('6C', 'Canadian Dollar', 'CME_CURRENCY', 'Canadian Dollar Futures (CME)'),
    ('6S', 'Swiss Franc', 'CME_CURRENCY', 'Swiss Franc Futures (CME)'),
)
MIN_DAYS = 200
SELECTION_POLICY = 'ascending median contract volume then provider root; np.array_split thirds; targets 1+q*(n-1), q=.25,.50,.75 in order; nearest currently unused rank then alphabetical provider root; never expand family'
TREASURY = 'https://www.cmegroup.com/content/dam/cmegroup/education/files/understanding-treasury-futures.pdf'
METALS = 'https://www.cmegroup.com/trading/metals/files/metals-prod-guide-2024.pdf'
FX = 'https://www.cmegroup.com/trading/fx/files/fx-product-guide-2023-us.pdf'
FX_OLD = 'https://www.cmegroup.com/trading/fx/files/FX248-2010_FX_Product_Guide_and_Calendar.pdf'
CHANGE = 'https://www.cmegroup.com/tools-information/lookups/advisories/electronic-trading/20150914.html'
RTY_SOURCE = 'https://www.cmegroup.com/notices/ser/2017/04/SER-7877R.pdf'
EQ = 'https://www.cmegroup.com/education/files/eq-trading-hours.pdf'
HALT_REMOVAL = 'https://www.cmegroup.com/content/dam/cmegroup/notices/ser/2021/06/SER-8788.pdf'


def resolve_provider_roots(metadata):
    rows = []
    names = metadata.Name.str.strip().str.casefold()
    for symbol, product, family, description in PRODUCTS:
        matches = metadata.loc[names.eq(description.casefold())]
        resolved = len(matches) == 1 and re.fullmatch(r'[A-Z0-9]+', matches.Ticker.iloc[0]) is not None
        rows.append(dict(exchange_symbol=symbol, product_name=product, product_family=family,
            provider_root=matches.Ticker.iloc[0] if resolved else '',
            provider_description=description, mapping_resolved=resolved,
            mapping_evidence='_documentation/.archive/futures_ticker_dates_listing.txt: exact product description; validated individual filenames',
            mapping_reason='' if resolved else 'missing_or_ambiguous_exact_provider_product_metadata'))
    return pd.DataFrame(rows)


def session_evidence(mapping):
    """Reviewed official evidence; normal clocks are separate from holiday calendars."""
    records = []
    for row in mapping.itertuples():
        family = row.product_family
        if family == 'US_TREASURIES':
            source, date, detail = TREASURY, '2024', '2024 guide Table 2: ZT/ZF/ZN/ZB Globex 17:00-16:00 Chicago'
        elif family == 'METALS':
            source, date, detail = METALS, '2024', '2024 guide trading-hours section and individual GC/SI/HG entries: Globex 18:00-17:00 Eastern; ignore inconsistent ClearPort Eastern entry'
        elif family == 'CME_CURRENCY':
            source, date, detail = FX + ';' + FX_OLD, '2023;2010', '2023 guide includes January 2024 calendar; normal FX Globex 17:00-16:00 Chicago, consistent with historical 2010 guide. Original 2024-link now redirects to 2026 and is NOT used as 2024 evidence.'
        elif family == 'EQUITY_INDEX':
            source = (RTY_SOURCE if row.exchange_symbol == 'RTY' else EQ) + ';' + CHANGE + ';' + HALT_REMOVAL
            date, detail = ('2017-04;2015-09-14;2021-06-11' if row.exchange_symbol == 'RTY' else 'equity schedule publication date unspecified;2015-09-14;2021-06-11'), '2015 close change to 16:00 Chicago; SER-8788 section 5 eliminates the 15:15-15:30 Chicago halt effective 2021-06-28. No afternoon pause in 2024. Historical pause retained only before elimination. CFTC filing 46134 certified 2021-06-25.'
        else:
            source = CHANGE + ';https://www.cmegroup.com/education/courses/event-contracts-underlying-markets/wti-overview'
            if row.exchange_symbol == 'NG':
                source += ';https://www.cmegroup.com/markets/energy/natural-gas/natural-gas.contractSpecs.html'
            date, detail = '2015-09-14; current product specifications', '2015 effective NYMEX close change to 16:00 Chicago; product specifications retain 17:00-16:00 Chicago normal session. Historical rule change explicitly retained.'
        records.append(dict(provider_root=row.provider_root, exchange_symbol=row.exchange_symbol,
            product_name=row.product_name, exchange_venue=('CBOT / Globex' if family == 'US_TREASURIES' else
                'NYMEX / Globex' if family == 'ENERGY' else 'COMEX / Globex' if family == 'METALS' else 'CME / Globex'),
            source_url=source, source_date=date, evidence_detail=detail,
            timestamp_timezone_evidence='_documentation/.archive/futures.txt: US Eastern Time; volume units futures contracts',
            timezone='America/New_York', session_open='18:00 previous calendar day', session_close='17:00 trade date exclusive',
            maintenance_intervals='17:00-18:00',
            trade_date_assignment='time>=18:00 -> next calendar date; time<17:00 -> current date; maintenance excluded',
            verified_2024=bool(row.mapping_resolved), evidence_covers_2024='normal session clock; not an exhaustive dated holiday/early-close calendar',
            wider_2015_2025_evidence=CHANGE if family in ('EQUITY_INDEX','ENERGY','METALS') else FX_OLD if family == 'CME_CURRENCY' else '2024 guide only; earlier normal clocks not independently certified',
            historical_session_limitation=True,
            historical_session_limitation_reason=('Full dated holiday/early-close schedule not certified'
                + ('; regular clocks outside 2024 not independently certified' if family in ('US_TREASURIES','CME_CURRENCY') else '')
                + ('; pre-2017-07-10 session/listed-line continuity not certified' if row.exchange_symbol == 'RTY' else '')),
            review_date='2026-10-14'))
    return pd.DataFrame(records)


def build_configs(mapping):
    configs, records = {}, []
    for row in mapping.loc[mapping.mapping_resolved].itertuples():
        pause = ((clock(16,15), clock(16,30)),) if row.product_family == 'EQUITY_INDEX' else ()
        periods = [('2015-01-01','2025-12-31',clock(17))]
        if row.product_family in ('EQUITY_INDEX','ENERGY','METALS'):
            periods = [('2015-01-01','2015-09-20',clock(17,15)), ('2015-09-21','2025-12-31',clock(17))]
        if row.exchange_symbol == 'RTY':
            periods = [('2017-07-10','2025-12-31',clock(17))]
        if row.product_family == 'EQUITY_INDEX':
            periods = [(start,min(end,'2021-06-27'),close) for start,end,close in periods]
            periods.append(('2021-06-28','2025-12-31',clock(17)))
        # Treasury and currency historical coverage remains explicitly limited;
        # avoid assigning unverified pre/post-calibration sessions to these roots.
        if row.product_family in ('US_TREASURIES','CME_CURRENCY'):
            periods = [('2024-01-01','2024-12-31',clock(17))]
        rules = []
        for start, end, close in periods:
            identifier = f'{row.provider_root}_{start}_{end}'
            effective_pause = () if row.product_family == 'EQUITY_INDEX' and start >= '2021-06-28' else pause
            config = FuturesSessionConfig(row.provider_root, start=clock(18), end=close,
                trading_day_convention='overnight_ending_date', maintenance_intervals=effective_pause,
                effective_start=start, effective_end=end, rule_id=identifier)
            rules.append(config)
            records.append(dict(provider_root=row.provider_root, session_rule_id=identifier,
                timezone=config.timezone, session_open='18:00', session_close=close.strftime('%H:%M'),
                maintenance_intervals=json.dumps([[close.strftime('%H:%M'),'18:00']] + [[a.strftime('%H:%M'),b.strftime('%H:%M')] for a,b in effective_pause]),
                trade_date_assignment=config.trading_day_convention, effective_start=start, effective_end=end,
                historical_session_limitation=True))
        configs[row.provider_root] = tuple(rules)
    return configs, pd.DataFrame(records)


def rank_and_select(data):
    # Allowlist means estimator/benchmark columns cannot affect eligibility/ranks.
    ranked = data.loc[data.final_eligible, ['provider_root','liquidity_measure_2024']].copy()
    ranked = ranked.sort_values(['liquidity_measure_2024','provider_root'],kind='stable').reset_index(drop=True)
    ranked['liquidity_rank'] = np.arange(1,len(ranked)+1)
    ranked['liquidity_tier'] = ''
    ranked['liquidity_rank_within_tier'] = 0
    ranked['selection_quantile_target'] = np.nan
    ranked['selection_target_rank'] = np.nan
    ranked['selected'] = False
    ranked['selection_reason'] = 'not_nearest_unused_quantile_rank'
    if len(ranked) < 9:
        ranked['selection_reason'] = 'blocked_fewer_than_nine_final_eligible_roots'
        return ranked, ranked.iloc[:0].copy()
    for tier, indices in zip(('LOW','MEDIUM','HIGH'),np.array_split(np.arange(len(ranked)),3)):
        ranked.loc[indices,'liquidity_tier'] = tier
        ranked.loc[indices,'liquidity_rank_within_tier'] = np.arange(1,len(indices)+1)
        used = set()
        for q in (Fraction(1,4),Fraction(1,2),Fraction(3,4)):
            target = 1 + q*(len(indices)-1)
            pick = min((i for i in indices if i not in used), key=lambda i:(
                abs(Fraction(int(ranked.loc[i,'liquidity_rank_within_tier']))-target),ranked.loc[i,'provider_root']))
            used.add(pick)
            ranked.loc[pick,['selected','selection_quantile_target','selection_target_rank','selection_reason']] = [True,float(q),float(target),'nearest-unused actual rank to 1+q*(n-1); absolute rank distance then alphabetical provider root']
    return ranked, ranked.loc[ranked.selected].copy()


def eligibility(record):
    reasons = []
    for field in ('mapping_resolved','individual_contract_files_exist','provider_mapping_usable','session_2024_verified','one_active_contract_per_trade_date'):
        if not record.get(field,False):
            reasons.append(field + '_failed')
    if record.get('valid_observed_2024_trade_dates',0) < MIN_DAYS:
        reasons.append('fewer_than_200_valid_observed_2024_trade_dates')
    for field in ('invalid_aggregation_days','selected_contract_read_failures','transition_validation_failures'):
        if record.get(field,0):
            reasons.append(field)
    return not reasons, ';'.join(reasons)


def inspect_transitions(calendar, sessions, root):
    rows = []
    provider = calendar.loc[calendar.provider_transition_flag & calendar.provider_mapping_date.between('2024-01-01','2024-12-31')]
    for transition in provider.itertuples():
        # Stop at the next contract change; never borrow a later recurrence.
        later = calendar.loc[calendar.provider_mapping_date.gt(transition.provider_mapping_date) & calendar.provider_transition_flag,'provider_mapping_date']
        end = later.min() if len(later) else pd.Timestamp('2025-01-01')
        dates = pd.to_datetime(sessions.trade_date)
        found = sessions.loc[dates.ge(transition.provider_mapping_date) & dates.lt(end)
            & sessions.selected_contract.eq(transition.selected_contract) & sessions.bars_observed.gt(0)]
        first = found.iloc[0] if len(found) else None
        evening = bool(first is not None and first.previous_evening_present)
        rows.append(dict(provider_root=root, provider_transition_date=transition.provider_mapping_date.date(),
            previous_contract=transition.provider_previous_contract, selected_contract=transition.selected_contract,
            first_observed_trade_date=first.trade_date if first is not None else None,
            observed_roll_day=bool(first.roll_day) if first is not None else False,
            previous_evening_rows=int(first.previous_evening_rows) if first is not None else 0,
            previous_evening_present=evening, validation_passed=evening,
            failure_reason='' if evening else 'new_contract_interval_has_no_observed_session' if first is None else 'new_contract_first_observed_session_lacks_previous_evening'))
    return pd.DataFrame(rows)


def calibrate(root_path, row, configs):
    root = row.provider_root
    directory = root_path / 'futures'
    out = OUT / 'read_audits'; out.mkdir(exist_ok=True)
    calendar_path = directory / f'{root}_continuous_contract_dates.txt'
    calendar_hash = sha256(calendar_path)
    calendar = parse_provider_calendar(calendar_path)
    plan = selection_plan(calendar,root,'2024-01-01','2024-12-31',directory,futures_sessions=configs)
    inputs, errors, scans = {}, {}, []
    for code in sorted(plan.selected_contract.dropna().unique()):
        path = contract_file(directory,root,code,allowed_roots=configs)
        if not path.is_file():
            continue
        print(f'2024 read {root}/{code}',flush=True)
        try:
            data, scan = read_contract_window(path,root,code,'2024-01-01','2024-12-31',out,futures_sessions=configs)
            wanted = set(plan.loc[plan.selected_contract.eq(code),'trade_date'])
            inputs[code] = data.loc[data.trade_date.isin(wanted) | data.maintenance_interval].copy()
            scans.append(scan)
        except Exception as exc:
            errors[code] = f'{type(exc).__name__}: {exc}'
    sessions, selected = validate_sessions(plan, inputs, read_errors=errors)
    daily = aggregate_daily_ohlcv(selected,root,'futures',futures_root=root,
        futures_audit=sessions,futures_sessions=configs)
    transitions = inspect_transitions(calendar,sessions,root)
    daily.to_csv(OUT/f'{root}_2024_daily_volume.csv',index=False)
    sessions.to_csv(OUT/f'{root}_2024_session_audit.csv',index=False)
    valid = daily.loc[daily.aggregation_valid]
    volumes = valid.volume
    record = dict(provider_root=root, mapping_resolved=True, individual_contract_files_exist=bool(inputs),
        provider_mapping_usable=True, session_2024_verified=True,
        one_active_contract_per_trade_date=not selected.groupby('trade_date').selected_contract.nunique().gt(1).any(),
        observed_2024_trade_dates=len(daily),valid_observed_2024_trade_dates=len(valid),
        liquidity_measure_2024=volumes.median(),p25=volumes.quantile(.25),p75=volumes.quantile(.75),
        min_daily_contract_volume=volumes.min(),max_daily_contract_volume=volumes.max(),
        zero_volume_rows=int(daily.zero_volume_rows.sum()),invalid_aggregation_days=int((~daily.aggregation_valid).sum()),
        mapped_dates_without_observations=int((sessions.selected_contract.notna() & sessions.bars_observed.eq(0)).sum()),
        missing_provider_mapping_dates=int(sessions.selected_contract.isna().sum()),
        missing_contract_file_dates=int(sessions.validation_reason.eq('missing_individual_contract_file').sum()),
        provider_transitions=len(transitions),observed_transitions=int(sessions.roll_day.sum()),
        transition_validation_failures=int((~transitions.validation_passed).sum()) if len(transitions) else 0,
        selected_contract_read_failures=len(errors),read_errors=json.dumps(errors),
        first_usable_2024_date=valid.date.min(),last_usable_2024_date=valid.date.max(),
        session_rule_id=next(r.rule_id for r in configs[root] if r.effective_start <= '2024-01-01' <= r.effective_end),
        historical_session_limitation=True)
    record['final_eligible'],record['exclusion_reason'] = eligibility(record)
    assert sha256(calendar_path) == calendar_hash
    return record,transitions,scans,calendar


def historical_review(root_path, root, configs, calendar):
    """Post-selection file/map availability, plus observed edge-session checks.

No extrapolation of a 2024-only clock into unresolved historical dates. Years
with available mapped files are distinguished from confirmed observed years.
"""
    directory = root_path / 'futures'
    history = calendar.loc[calendar.provider_mapping_date.between('2015-01-01','2025-12-31')].copy()
    history['file_exists'] = history.selected_contract.map({code:contract_file(directory,root,code,allowed_roots=configs).is_file()
        for code in history.selected_contract.unique()})
    missing = history.loc[~history.file_exists]
    rules = configs[root]
    supported = pd.Series(False,index=history.index)
    for rule in rules:
        supported |= history.provider_mapping_date.between(rule.effective_start,rule.effective_end)
    history['regular_rule_supported'] = supported
    history.to_csv(OUT/f'{root}_historical_mapping_availability.csv',index=False)
    eligible = history.loc[history.file_exists & supported]
    confirmed = []
    for first in (True,False):
        for code in eligible.sort_values('provider_mapping_date',ascending=first).selected_contract.drop_duplicates():
            dates = eligible.loc[eligible.selected_contract.eq(code),'provider_mapping_date']
            start,end = dates.min(),dates.max()
            print(f'Historical edge audit {root}/{code}: {start.date()} to {end.date()}',flush=True)
            data,_ = read_contract_window(contract_file(directory,root,code,allowed_roots=configs),root,code,
                start,end,OUT/'read_audits',futures_sessions=configs)
            expected = set(dates.dt.date)
            observed = data.loc[data.primary_session_retained & data.trade_date.isin(expected),'trade_date']
            if len(observed):
                confirmed.append(observed.min() if first else observed.max())
                break
        else:
            confirmed.append(None)
    unresolved = history.loc[~supported,'provider_mapping_date']
    record = dict(provider_root=root,first_usable_date=confirmed[0],last_usable_date=confirmed[1],
        years_represented=json.dumps(sorted(history.loc[history.file_exists,'provider_mapping_date'].dt.year.unique().tolist())),
        years_represented_basis='mapped individual-file availability only; not a complete observed daily panel',
        provider_map_missing_calendar_dates=4018-len(history),
        provider_map_gap_basis='calendar-date audit includes weekends/holidays; not automatically missing trading sessions',
        missing_contract_files=json.dumps(sorted(missing.selected_contract.unique().tolist())),
        missing_contract_file_dates=len(missing),
        historical_session_rule_coverage=';'.join(f'{r.effective_start} through {r.effective_end}: {r.rule_id}' for r in rules),
        unresolved_regular_rule_first_date=unresolved.min(),unresolved_regular_rule_last_date=unresolved.max(),
        historical_session_limitation=True,
        unresolved_regular_rule_ranges=json.dumps(historical_rule_gaps(rules)),
        unresolved_session_ranges='dated holiday/early-close exceptions throughout 2015-2025 not independently certified; regular-clock gaps in unresolved_regular_rule_ranges',
        final_analysis_ready=False,
        readiness_reason='historical session/calendar certification incomplete' + ('; missing selected individual files' if len(missing) else ''))
    return record


def historical_rule_gaps(rules):
    """Unverified clock ranges, separate from missing provider-map dates."""
    days = pd.date_range('2015-01-01','2025-12-31')
    covered = np.zeros(len(days),dtype=bool)
    for rule in rules:
        covered |= (days >= pd.Timestamp(rule.effective_start)) & (days <= pd.Timestamp(rule.effective_end))
    absent = days[~covered]
    if not len(absent):
        return []
    runs = pd.Series(absent).groupby(pd.Series(absent).diff().gt(pd.Timedelta(days=1)).cumsum())
    return [dict(start=group.min().date().isoformat(),end=group.max().date().isoformat()) for _,group in runs]


def cached_calibration(root_path,row,configs,previous):
    """Reuse only hash-verified derived rows with unchanged rule/map/source stamps."""
    if previous is None:
        return None
    manifest,records,transitions,scans,old_rules=previous
    found=records.loc[records.provider_root.eq(row.provider_root)]
    if len(found)!=1:
        return None
    record=found.iloc[0].to_dict()
    current_rule=next(r.rule_id for r in configs[row.provider_root]
        if r.effective_start <= '2024-01-01' <= r.effective_end)
    if record.get('session_rule_id')!=current_rule:
        return None
    rule=next(r for r in configs[row.provider_root] if r.rule_id==current_rule)
    saved_rule=old_rules.loc[old_rules.session_rule_id.eq(current_rule)]
    expected=dict(timezone=rule.timezone,session_open=rule.start.strftime('%H:%M'),
        session_close=rule.end.strftime('%H:%M'),trade_date_assignment=rule.trading_day_convention,
        maintenance_intervals=json.dumps([[rule.end.strftime('%H:%M'),'18:00']]+
            [[a.strftime('%H:%M'),b.strftime('%H:%M')] for a,b in rule.maintenance_intervals]))
    if len(saved_rule)!=1 or any(saved_rule.iloc[0][key]!=value for key,value in expected.items()):
        return None
    for name in (f'{row.provider_root}_2024_daily_volume.csv',f'{row.provider_root}_2024_session_audit.csv'):
        if manifest.get('output_sha256',{}).get(name)!=sha256(OUT/name):
            return None
    files=scans.loc[scans.root.eq(row.provider_root)].copy()
    for item in files.itertuples():
        stat=Path(item.file).stat()
        if stat.st_size!=item.file_size_bytes or stat.st_mtime_ns!=int(item.raw_mtime_ns):
            return None
    directory=root_path/'futures'
    calendar=parse_provider_calendar(directory/f'{row.provider_root}_continuous_contract_dates.txt')
    plan=selection_plan(calendar,row.provider_root,'2024-01-01','2024-12-31',directory,futures_sessions=configs)
    sessions=pd.read_csv(OUT/f'{row.provider_root}_2024_session_audit.csv')
    for field in ('selected_contract','contract_file_exists','provider_transition_flag'):
        if sessions[field].fillna('').astype(str).tolist()!=plan[field].fillna('').astype(str).tolist():
            return None
    for field in ('provider_mapping_date','provider_transition_date'):
        if pd.to_datetime(sessions[field]).astype(str).tolist()!=pd.to_datetime(plan[field]).astype(str).tolist():
            return None
    record['final_eligible'],record['exclusion_reason']=eligibility(record)
    files['reused_validated_scan']=True
    print('Reuse verified unchanged 2024 calibration '+row.provider_root,flush=True)
    return record,transitions.loc[transitions.provider_root.eq(row.provider_root)].copy(),files.to_dict('records'),calendar


def run():
    started = time.perf_counter(); OUT.mkdir(parents=True,exist_ok=True)
    root_path = intraday_root()
    previous=None
    if (OUT/'run_manifest.json').exists():
        saved=json.loads((OUT/'run_manifest.json').read_text(encoding='utf-8'))
        if 'output_sha256' in saved:
            required=('eligibility_audit.csv','transition_validation.csv','file_scan_audit.csv','session_rule_config.csv')
            if all(saved['output_sha256'].get(name)==sha256(OUT/name) for name in required):
                previous=(saved,pd.read_csv(OUT/required[0]),pd.read_csv(OUT/required[1]),pd.read_csv(OUT/required[2],dtype={'raw_mtime_ns':'int64'}),pd.read_csv(OUT/required[3]))
    protected = [p for directory in (PROJECT/'outputs/diagnostics/futures_roll',PROJECT/'outputs/diagnostics/final_universe/futures_crypto') for p in directory.rglob('*') if p.is_file()]
    protected += [PROJECT/'README.md',PROJECT/'design_decisions.md',PROJECT/'data_manifest.csv',PROJECT/'manifests/data_manifest.csv',PROJECT/'data/raw_bloomberg/sha256_manifest.csv']
    before = {str(p):sha256(p) for p in protected if p.is_file()}
    raw_audit,_ = verify_hashes(PROJECT/'data/raw_bloomberg'); require_verified(raw_audit)
    metadata_path = root_path/'_documentation/.archive/futures_ticker_dates_listing.txt'
    metadata_hash = sha256(metadata_path)
    metadata = pd.read_csv(metadata_path,dtype=str,keep_default_na=False)
    mapping = resolve_provider_roots(metadata)
    mapping.to_csv(OUT/'provider_root_mapping.csv',index=False)
    mapping[['exchange_symbol','product_name','product_family']].assign(
        frozen_before_liquidity=True,selection_basis='user Step 11 economic product set; source/session verifiability; not liquidity').to_csv(OUT/'candidate_products.csv',index=False)
    (OUT/'prespecified_selection_policy.json').write_text(json.dumps(dict(candidate_products=list(PRODUCTS),minimum_valid_observed_2024_trade_dates=MIN_DAYS,
        selection_policy=SELECTION_POLICY,liquidity_calculated_at_freeze=False),indent=2),encoding='utf-8')
    evidence = session_evidence(mapping); evidence.to_csv(OUT/'session_source_review.csv',index=False)
    configs,config_table = build_configs(mapping); config_table.to_csv(OUT/'session_rule_config.csv',index=False)
    records,transitions,scans,calendars = [],[],[],{}
    for row in mapping.itertuples():
        try:
            if not row.mapping_resolved:
                raise ValueError('unresolved_provider_root_mapping')
            cached=cached_calibration(root_path,row,configs,previous)
            record,transition,scan,calendar = cached if cached is not None else calibrate(root_path,row,configs)
            for item in scan:
                item.setdefault('reused_validated_scan',False)
            calendars[row.provider_root] = calendar
            transitions.append(transition); scans.extend(scan)
        except Exception as exc:
            record = dict(provider_root=row.provider_root,final_eligible=False,
                exclusion_reason=f'{type(exc).__name__}: {exc}',liquidity_measure_2024=np.nan)
        records.append(record)
        pd.DataFrame(records).to_csv(OUT/'eligibility_audit.csv',index=False)
    liquidity = pd.DataFrame(records)
    ranked,selected = rank_and_select(liquidity)
    liquidity = mapping.merge(liquidity,on='provider_root',how='left',validate='one_to_one')
    liquidity.to_csv(OUT/'futures_2024_liquidity.csv',index=False)
    pd.concat(transitions,ignore_index=True).to_csv(OUT/'transition_validation.csv',index=False)
    pd.DataFrame(scans).to_csv(OUT/'file_scan_audit.csv',index=False)
    ranked.to_csv(OUT/'selection_audit.csv',index=False)
    history = pd.DataFrame([historical_review(root_path,root,configs,calendars[root]) for root in selected.provider_root])
    historical_columns = ['provider_root','first_usable_date','last_usable_date','years_represented','final_analysis_ready']
    if history.empty:
        history = pd.DataFrame(columns=historical_columns)
    history.to_csv(OUT/'historical_coverage_review.csv',index=False)
    selected = selected.merge(liquidity,on=['provider_root','liquidity_measure_2024'],how='left',validate='one_to_one')
    selected = selected.merge(history,on='provider_root',how='left',validate='one_to_one',suffixes=('','_historical'))
    selected.to_csv(OUT/'selected_futures.csv',index=False)
    assert sha256(metadata_path) == metadata_hash
    assert before == {str(p):sha256(p) for p in protected if p.is_file()}
    raw_audit,_ = verify_hashes(PROJECT/'data/raw_bloomberg'); require_verified(raw_audit)
    raw_audit.to_csv(OUT/'raw_bloomberg_hash_verification.csv',index=False)
    report = '# Step 11 final futures universe\n\n'
    report += f'Fixed economic products: 18; explicitly mapped: {mapping.mapping_resolved.sum()}; verified normal 2024 sessions: {evidence.verified_2024.sum()}; final-eligible: {len(ranked)}; selected: {len(selected)}. No benchmark or estimator inputs used.\n\n'
    report += 'Pre-specified distinct-selection policy: '+SELECTION_POLICY+'.\n\n'
    report += 'Explicit provider mappings\n\n'+table_md(mapping[['exchange_symbol','provider_root','product_name']])+'\n\n'
    report += 'Eligible 2024 ranking (units: futures contracts per observed trade date; median daily sum)\n\n'+table_md(ranked)+'\n\n'
    tier_summary = ranked.groupby('liquidity_tier',as_index=False).agg(roots=('provider_root','size'),minimum=('liquidity_measure_2024','min'),maximum=('liquidity_measure_2024','max'))
    tier_summary.to_csv(OUT/'liquidity_tier_summary.csv',index=False)
    report += 'Tier boundaries are empirical order-statistic ranges, never cross-class notional comparisons.\n\n'+table_md(tier_summary)+'\n\n'
    report += 'Candidate failures\n\n'+table_md(liquidity.loc[~liquidity.final_eligible,['provider_root','exclusion_reason']])+'\n\n'
    report += ('Final selection blocked: fewer than nine eligible roots; no family expansion.\n\n' if len(selected)!=9 else
        'Final selection\n\n'+table_md(selected[['provider_root','exchange_symbol','liquidity_tier','liquidity_measure_2024','observed_2024_trade_dates','first_usable_date','last_usable_date','final_analysis_ready']])+'\n\n')
    report += 'Regular-session evidence is product/family specific and official: [2024 Treasury guide]('+TREASURY+'), [2024 metals guide]('+METALS+'), [FX guide]('+FX+'), [historical FX guide]('+FX_OLD+'), [2015 effective close change]('+CHANGE+'), [RTY launch specifications]('+RTY_SOURCE+'). Source dates, scope and limitations are in session_source_review.csv. 2024 normal hours do not certify every holiday/early close. Observed bars are never synthesized.\n\n'
    report += 'Step-5 ES/CL behavior remains unchanged. Official [SER-8788 section 5]('+HALT_REMOVAL+') eliminates the equity-index afternoon halt effective 2021-06-28; the older pause is retained only historically before that date. Preliminary Step-11 diagnostics incorrectly extended the old halt into 2024; ES/NQ/RTY were recalibrated with the corrected effective-date rule before final selection. Other unchanged calibrations are reused only after derived hashes, raw source size/mtime and exact mappings reconcile. The 2015-09-21 close change is also date-effective; pre-launch RTY and unverified historical Treasury/FX dates remain unresolved. No universal clock or current-hours backfill is used.\n\n'
    report += 'Every 2024 provider transition is inspected in transition_validation.csv, separately from observed trade-date roll flags. Absent evenings/read/mapping failures are not repaired; failing roots are ineligible. >=200 valid observed days is a frozen data-coverage gate, not a precision or performance threshold. Invalid daily aggregations remain saved and block eligibility.\n\n'
    report += 'Historical availability is audited only after selection. years_represented describes years with mapped files, not a certified observed panel. First/last usable dates are confirmed from selected-contract observations under available regular rules; unverified historical rules are never extrapolated. Missing calendar map dates include closures and are not all presumed data loss. Full historical exception schedules remain unresolved, so selected roots remain final_analysis_ready=False pending review; no selected root is replaced for an unbalanced panel.\n\n'
    report += table_md(history)+'\n\n'
    report += 'Raw First Rate/Bloomberg, prior Step-5/9 outputs and prohibited documentation remain unchanged. No continuous-price files, Roll values, CS/AR/EDGE formulas, estimator values, multipliers or dollar notional entered selection.\n'
    (OUT/'step11_review.md').write_text(report,encoding='utf-8')
    manifest = dict(status='selected_with_historical_limitations' if len(selected)==9 else 'blocked_selection',
        step=11,candidate_products=18,mapped_products=int(mapping.mapping_resolved.sum()),
        verified_2024_sessions=int(evidence.verified_2024.sum()),eligible_roots=len(ranked),selected_roots=len(selected),
        historical_analysis_ready=int(selected.final_analysis_ready.sum()) if len(selected) else 0,
        provider_raw_writes=0,Bloomberg_raw_writes=0,continuous_price_reads=0,
        benchmark_or_estimator_inputs_used=False,inserted_bars=0,minimum_valid_observed_trade_dates=MIN_DAYS,
        protected_artifact_sha256=before,provider_metadata_sha256=metadata_hash,
        approximate_bytes_scanned=sum(s['file_size_bytes'] for s in scans if not s['reused_validated_scan']),
        validated_calibration_source_bytes=sum(s['file_size_bytes'] for s in scans),
        reused_calibration_roots=int(sum(all(item['reused_validated_scan'] for item in scans if item['root']==root) for root in liquidity.provider_root)),
        runtime_seconds=time.perf_counter()-started)
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in manifest.items() if 'sha256' not in k},indent=2),flush=True)


if __name__ == '__main__':
    run()
