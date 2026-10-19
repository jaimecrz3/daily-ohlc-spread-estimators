"""Step 11.1: certify and construct the frozen nine roots, without ranking.

Run: .venv/Scripts/python.exe -B src/futures_historical_sessions.py
Only exact provider daily assignments and unadjusted individual files are read.
Calendar audit rows never become synthetic OHLCV observations.
"""
from collections import Counter, defaultdict
from itertools import islice
from pathlib import Path
import csv
import hashlib
import json
import time

import numpy as np
import pandas as pd

try:
    from .data_io import intraday_root
    from .eda_diagnostics import parse_chunk
    from .session_rules import assign_primary_session, resolve_futures_session
    from .futures_roll import (parse_provider_calendar, selection_plan, contract_file,
        validate_sessions, table_md)
    from .daily_aggregation import aggregate_daily_ohlcv, DAILY_COLUMNS
    from .futures_final_universe import build_configs, historical_rule_gaps
    from .bloomberg_io import sha256, verify_hashes, require_verified
except ImportError:
    from data_io import intraday_root
    from eda_diagnostics import parse_chunk
    from session_rules import assign_primary_session, resolve_futures_session
    from futures_roll import (parse_provider_calendar, selection_plan, contract_file,
        validate_sessions, table_md)
    from daily_aggregation import aggregate_daily_ohlcv, DAILY_COLUMNS
    from futures_final_universe import build_configs, historical_rule_gaps
    from bloomberg_io import sha256, verify_hashes, require_verified

PROJECT = Path(__file__).resolve().parents[1]
PARENT = PROJECT / 'outputs/diagnostics/final_universe/futures_final'
OUT = PARENT / 'historical'
ROOTS = ('HG', 'AD', 'B6', 'J1', 'GC', 'E6', 'NQ', 'ZF', 'ES')
START, END = '2015-01-01', '2025-12-31'
CME = 'https://www.cmegroup.com/'
SOURCES = (
    ('PROVIDER', '_documentation/.archive/futures.txt', 'provider documentation',
     'US Eastern timestamps; contract volume; individual files unadjusted; zero-volume bars omitted'),
    ('CLOSE2015', CME+'tools-information/lookups/advisories/electronic-trading/20150914.html', '2015-09-14',
     'Maintenance notice: equity/COMEX closes change effective 2015-09-21; openings unchanged'),
    ('EQ_OLD', CME+'education/files/eq-trading-hours.pdf', 'publication date unspecified',
     'Historical equity Globex schedule, including afternoon pause and old close'),
    ('EQ2021', CME+'content/dam/cmegroup/notices/ser/2021/06/SER-8788.pdf', '2021-06-11',
     'Section 5: equity 15:15-15:30 Chicago halt eliminated effective 2021-06-28'),
    ('METALS_OLD', CME+'education/modules/files/metals_sales_brochure.pdf', 'historical brochure',
     'Gold/copper Globex 18:00-17:15 Eastern before 2015 close change'),
    ('METALS2024', CME+'trading/metals/files/metals-prod-guide-2024.pdf', '2024',
     'Gold/copper Globex regular hours; do not use ClearPort hours'),
    ('FX2010', CME+'trading/fx/files/FX248-2010_FX_Product_Guide_and_Calendar.pdf', '2010',
     'Independent old FX clock corroboration, NOT proof of every intervening date'),
    ('FX2023', CME+'trading/fx/files/fx-product-guide-2023-us.pdf', '2023; includes January 2024',
     'FX Globex normal hours support established 2024 rule; no blanket historical extrapolation'),
    ('TREASURY2024', CME+'content/dam/cmegroup/education/files/understanding-treasury-futures.pdf', '2024',
     'Table 2 includes 5-Year Treasury Globex 17:00-16:00 Chicago'),
)


def historical_configs(mapping):
    """Reuse certified changes, restrict registry to frozen roots, expose gaps.

    FX/Treasury evidence does not establish a continuous date-effective history.
    Their periods outside the previously verified 2024 window stay UNRESOLVED.
    """
    selected = mapping.loc[mapping.provider_root.isin(ROOTS)].copy()
    if set(selected.provider_root) != set(ROOTS) or selected.provider_root.duplicated().any():
        raise ValueError('Frozen provider root mapping missing/ambiguous')
    configs, rules = build_configs(selected)
    rules['status'] = 'VERIFIED'
    rules['scope'] = 'regular primary-session envelope; not exchange settlement/holiday business-date calendar'
    refs = {}
    for row in selected.itertuples():
        refs[row.provider_root] = ('PROVIDER;EQ_OLD;CLOSE2015;EQ2021' if row.product_family == 'EQUITY_INDEX'
            else 'PROVIDER;METALS_OLD;CLOSE2015;METALS2024' if row.product_family == 'METALS'
            else 'PROVIDER;TREASURY2024' if row.product_family == 'US_TREASURIES'
            else 'PROVIDER;FX2010;FX2023')
    rules['source_ids'] = rules.provider_root.map(refs)
    unresolved = []
    for root in ROOTS:
        for gap in historical_rule_gaps(configs[root]):
            unresolved.append(dict(provider_root=root, effective_start=gap['start'], effective_end=gap['end'],
                status='UNRESOLVED', primary_inclusion=False,
                reason='No continuous date-effective official evidence established outside verified 2024; no backcasting'))
    return configs, rules, pd.DataFrame(unresolved, columns=['provider_root', 'effective_start',
        'effective_end', 'status', 'primary_inclusion', 'reason'])


def historical_plan(calendar, root, directory, configs):
    """Verified date plans plus explicit unresolved calendar audit, without fill."""
    parts = [selection_plan(calendar, root, r.effective_start, r.effective_end, directory,
        futures_sessions=configs).assign(session_rule_id=r.rule_id, session_status='VERIFIED')
        for r in configs[root]]
    verified = pd.concat(parts, ignore_index=True)
    days = pd.DataFrame({'trade_date': pd.date_range(START, END).date})
    plan = days.merge(verified, on='trade_date', how='left', validate='one_to_one')
    lookup = calendar.set_index(calendar.provider_mapping_date.dt.date)
    for index in plan.index[plan.session_status.isna()]:
        day = plan.at[index, 'trade_date']
        row = lookup.loc[day] if day in lookup.index else None
        code = row.selected_contract if row is not None else None
        path = contract_file(directory, root, code, allowed_roots=configs) if code else None
        values = dict(root=root, timezone='America/New_York', session_status='UNRESOLVED',
            session_rule_id='', selected_contract=code, contract_file=str(path) if path else '',
            contract_file_exists=bool(path and path.is_file()),
            provider_mapping_date=day if row is not None else None,
            provider_transition_date=row.provider_transition_date.date() if row is not None else None,
            provider_transition_flag=bool(row.provider_transition_flag) if row is not None else False,
            provider_previous_contract=row.provider_previous_contract if row is not None else None)
        for key, value in values.items():
            plan.at[index, key] = value
    plan['contract_file_exists'] = plan.contract_file_exists.astype(bool)
    plan['provider_transition_flag'] = plan.provider_transition_flag.astype(bool)
    return plan


def ready_for_analysis(daily, sessions, transition_failures=0, read_failures=0):
    """Construction validity, never balanced history or a liquidity/quality gate."""
    if daily.empty:
        return False, 'no_observed_verified_asset_days'
    failures = []
    if daily.date.duplicated().any() or sessions.trade_date.duplicated().any():
        return False, 'overlapping_active_contracts_or_duplicate_audit_dates'
    included = daily[['date','selected_contract','bars_observed']].merge(sessions[['trade_date', 'session_status', 'selected_contract',
        'bars_observed', 'contract_file_exists', 'validation_status']], left_on='date', right_on='trade_date',
        how='left', suffixes=('', '_audit'), validate='one_to_one')
    if not included.session_status.eq('VERIFIED').all():
        failures.append('unverified_included_observations')
    if not (included.selected_contract.eq(included.selected_contract_audit)
            & included.bars_observed.eq(included.bars_observed_audit)
            & included.contract_file_exists & included.validation_status.eq('ok')).all():
        failures.append('invalid_mapping_or_provenance')
    if not daily.bars_observed.gt(0).all():
        failures.append('synthetic_daily_rows')
    if transition_failures:
        failures.append('transition_anomalies_require_review')
    if read_failures:
        failures.append('individual_contract_read_failures')
    return not failures, ';'.join(failures) or 'all_included_observations_verified;unbalanced_history_allowed'


def scan_selected_contract(path, root, code, selected_plan, missing_days, configs, audit_dir):
    """Stream every required file once; parse OHLCV only for selected verified dates.

    Also audit physical timestamps on missing-file calendar dates and their prior
    evenings in *other required selected files*. Those are potential observations,
    not substituted or certified sessions when the session rule is unresolved.
    """
    if path.name != contract_file(path.parent,root,code,allowed_roots=configs).name:
        raise ValueError('Only the exact unadjusted individual-contract filename may be scanned')
    before = path.stat()
    verified_days = set(selected_plan.loc[selected_plan.session_status.eq('VERIFIED'), 'trade_date'])
    selected_days = set(selected_plan.trade_date)
    pieces, alternatives = [], Counter()
    counts = Counter()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        pilot = list(islice(stream, 10))
    if not pilot or any(len(line.strip().split(b',')) != 6 for line in pilot):
        raise ValueError('Individual-contract pilot failed')
    # Timestamp audit retains source line numbers, including unresolved rows.
    with (audit_dir/f'{root}_{code}_timestamp_errors.csv').open('w', newline='', encoding='utf-8') as errors:
        writer = csv.writer(errors); writer.writerow(['raw_line_number', 'reason', 'raw_text'])
        with path.open('rb') as stream:
            offset = 1
            while raw := list(islice(stream, 100_000)):
                for line in raw:
                    digest.update(line)
                lines = [line.decode('utf-8-sig') for line in raw]
                text = pd.Series([line.split(',', 1)[0].strip() for line in lines])
                ts = pd.to_datetime(text, format='%Y-%m-%d %H:%M:%S', errors='coerce')
                ts = ts.where(text.str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}'))
                bad = ts.isna()
                counts['raw_rows_scanned'] += len(lines)
                counts['invalid_timestamp_rows'] += int(bad.sum())
                for index in np.flatnonzero(bad):
                    writer.writerow([offset+int(index), 'unassignable_timestamp', lines[index].rstrip()])
                # This label is only a selection/availability lookup. Unverified
                # rows never pass session assignment or aggregation below.
                candidate = (ts.dt.normalize()+pd.to_timedelta(ts.dt.hour.ge(18).astype(int),unit='D')).dt.date
                counts['unresolved_selected_timestamp_rows'] += int((candidate.isin(selected_days-verified_days)).sum())
                potential = candidate.isin(missing_days)
                alternatives.update(candidate.loc[potential].value_counts().to_dict())
                positions = np.flatnonzero(candidate.isin(verified_days))
                if len(positions):
                    _, parsed = parse_chunk([lines[p] for p in positions], 1)
                    parsed.index = pd.Index(offset+positions, name='raw_line_number')
                    pieces.append(parsed)
                offset += len(lines)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Provider file changed during read')
    data = pd.concat(pieces) if pieces else pd.DataFrame({'timestamp':pd.Series(dtype='datetime64[ns]'),
        **{c:pd.Series(dtype=float) for c in ('open','high','low','close','volume')}})
    annotated = assign_primary_session(data, 'futures', futures_root=root, futures_sessions=configs)
    annotated['source_contract'] = code
    annotated['duplicate_timestamp'] = annotated.timestamp.notna() & annotated.timestamp.duplicated(keep=False)
    flags = [c for c in ['zero_volume','missing_value','non_numeric','non_finite','invalid_ohlc',
        'negative_volume','malformed_columns','duplicate_timestamp','timezone_assignment_failed'] if c in annotated]
    annotated.loc[annotated[flags].any(axis=1)].to_csv(audit_dir/f'{root}_{code}_flagged_rows.csv',index=True)
    return annotated, dict(root=root, contract=code, file_name=path.name, sha256=digest.hexdigest(),
        size_bytes=before.st_size, mtime_ns=before.st_mtime_ns, bytes_scanned=before.st_size, **counts), alternatives


def restore_observed_roll_flags(sessions, daily):
    """Restore predecessor across contract-by-contract processing and empty days."""
    sessions = sessions.sort_values('trade_date', kind='stable').reset_index(drop=True)
    previous = None
    for index, row in sessions.iterrows():
        observed = row.bars_observed > 0
        sessions.at[index, 'previous_contract'] = previous
        sessions.at[index, 'roll_day'] = bool(observed and previous is not None and row.selected_contract != previous)
        if observed:
            previous = row.selected_contract
    if len(daily):
        metadata = sessions.set_index('trade_date')
        daily = daily.sort_values('date', kind='stable').reset_index(drop=True)
        daily['previous_contract'] = daily.date.map(metadata.previous_contract)
        daily['roll_day'] = daily.date.map(metadata.roll_day).astype(bool)
        daily['session_rule_id'] = daily.date.map(metadata.session_rule_id)
        daily['session_status'] = 'VERIFIED'
    return sessions, daily


def process_root(root, directory, calendar, configs, out):
    plan = historical_plan(calendar, root, directory, configs)
    mapped = plan.loc[plan.selected_contract.notna()]
    missing = mapped.loc[~mapped.contract_file_exists]
    missing_days = set(missing.trade_date)
    contract_records, scans, session_parts, daily_parts = [], [], [], []
    alternatives = defaultdict(dict)
    for code, selected_plan in mapped.groupby('selected_contract', sort=True):
        path = contract_file(directory, root, code, allowed_roots=configs)
        contract_records.append(dict(provider_root=root, selected_contract=code, contract_file=path.name,
            contract_file_exists=path.is_file(), mapped_calendar_dates=len(selected_plan),
            first_affected_trade_date=selected_plan.trade_date.min(), last_affected_trade_date=selected_plan.trade_date.max(),
            verified_rule_mapped_dates=int(selected_plan.session_status.eq('VERIFIED').sum())))
        verified_plan = selected_plan.loc[selected_plan.session_status.eq('VERIFIED')]
        if path.is_file():
            print(f'Scan {root} {code}', flush=True)
            annotated, scan, other = scan_selected_contract(path, root, code, selected_plan, missing_days, configs, out/'read_audits')
            scans.append(scan)
            for day, count in other.items():
                alternatives[day][code] = count
            if len(verified_plan):
                sessions, bars = validate_sessions(verified_plan, {code:annotated})
                if len(bars):
                    daily = aggregate_daily_ohlcv(bars, root, 'futures', futures_root=root,
                        futures_audit=sessions, futures_sessions=configs)
                    if daily.date.duplicated().any() or not daily.bars_observed.gt(0).all():
                        raise AssertionError('Non-observed or duplicate daily date')
                    daily_parts.append(daily)
                session_parts.append(sessions)
            del annotated
        elif len(verified_plan):
            sessions, _ = validate_sessions(verified_plan, {})
            session_parts.append(sessions)
    # Unmapped dates and unverified periods remain audit-only.
    excluded = plan.loc[plan.selected_contract.isna() | plan.session_status.eq('UNRESOLVED')].copy()
    excluded['bars_observed'] = 0
    excluded['validation_status'] = 'excluded_audit_only'
    excluded['validation_reason'] = np.where(excluded.session_status.eq('UNRESOLVED'),
        'unresolved_session_rule', 'missing_provider_trade_date_mapping')
    excluded['previous_evening_rows'] = 0
    excluded['previous_evening_present'] = False
    excluded['roll_day'] = False
    excluded['previous_contract'] = None
    session_parts.append(excluded)
    sessions = pd.concat(session_parts, ignore_index=True)
    daily = pd.concat(daily_parts,ignore_index=True) if daily_parts else pd.DataFrame(columns=DAILY_COLUMNS)
    sessions, daily = restore_observed_roll_flags(sessions, daily)
    transitions = sessions.loc[sessions.roll_day.astype(bool)].copy()
    transitions['validation_passed'] = transitions.previous_evening_present.astype(bool)
    transitions['transition_validation_reason'] = np.where(transitions.validation_passed, '',
        'observed_new_contract_session_lacks_previous_evening_observations')
    transitions['one_selected_contract'] = True  # checked by validation and aggregation
    missing_audit = []
    for row in missing.itertuples():
        other = alternatives.get(row.trade_date, {})
        missing_audit.append(dict(provider_root=root, trade_date=row.trade_date, selected_contract=row.selected_contract,
            contract_file=Path(row.contract_file).name, session_status=row.session_status,
            availability_status='source_unavailable_no_substitution',
            other_required_contract_potential_rows=sum(other.values()),
            other_required_contract_codes=';'.join(sorted(other)),
            other_required_contract_counts=json.dumps(other, sort_keys=True),
            observation_scope='physical timestamps on target calendar date before 18:00 and prior evening >=18:00; not verified session membership',
            substituted=False))
    ready, reason = ready_for_analysis(daily,sessions,int((~transitions.validation_passed).sum()))
    coverage = dict(provider_root=root, first_included_trade_date=daily.date.min() if len(daily) else None,
        last_included_trade_date=daily.date.max() if len(daily) else None, included_asset_days=len(daily),
        retained_bars=int(daily.bars_observed.sum()),
        invalid_aggregation_days=int((~daily.aggregation_valid.astype(bool)).sum()),
        zero_volume_rows=int(daily.zero_volume_rows.sum()),
        days_with_gaps_gt_one_minute=int(daily.max_gap_minutes.gt(1).sum()),
        unresolved_calendar_audit_dates=int(plan.session_status.eq('UNRESOLVED').sum()),
        unresolved_mapped_dates=int(mapped.session_status.eq('UNRESOLVED').sum()),
        missing_contract_mapped_dates=len(missing),
        missing_contract_first_date=missing.trade_date.min() if len(missing) else None,
        missing_contract_last_date=missing.trade_date.max() if len(missing) else None,
        observed_transitions=len(transitions), failed_transition_checks=int((~transitions.validation_passed).sum()),
        missing_mapping_calendar_dates=int(plan.selected_contract.isna().sum()),
        mapped_verified_dates_without_observations=int((sessions.session_status.eq('VERIFIED')
            & sessions.selected_contract.notna() & sessions.bars_observed.eq(0)).sum()),
        final_analysis_ready=ready, readiness_reason=reason,
        remaining_limitation='Unbalanced observed regular-envelope panel; missing individual files; no exhaustive holiday/settlement-date certification'
            + ('; unresolved historical periods excluded' if plan.session_status.eq('UNRESOLVED').any() else ''))
    sessions.to_csv(out/f'{root}_historical_session_audit.csv',index=False)
    daily.to_csv(out/f'{root}_historical_daily_ohlcv.csv',index=False)
    return coverage, contract_records, missing_audit, transitions, scans


def protected_hashes():
    directories = [PROJECT/'outputs/diagnostics/futures_roll',
        PROJECT/'outputs/diagnostics/final_universe/futures_crypto', PARENT]
    paths = [p for d in directories for p in d.rglob('*') if p.is_file() and OUT not in p.parents]
    paths += [PROJECT/p for p in ('README.md','design_decisions.md','data_manifest.csv',
        'manifests/data_manifest.csv','data/raw_bloomberg/sha256_manifest.csv') if (PROJECT/p).is_file()]
    return {str(p.relative_to(PROJECT)):sha256(p) for p in paths}


def validate_saved_outputs(out=OUT):
    """Independent derived-table reconciliation; no provider benchmark reads."""
    configs, _, _ = historical_configs(pd.read_csv(PARENT/'provider_root_mapping.csv'))
    coverage = pd.read_csv(out/'historical_daily_coverage.csv')
    required = pd.read_csv(out/'required_contract_audit.csv')
    missing = pd.read_csv(out/'missing_contract_audit.csv')
    transitions = pd.read_csv(out/'historical_transition_validation.csv')
    checks = []
    for root in ROOTS:
        daily = pd.read_csv(out/f'{root}_historical_daily_ohlcv.csv')
        sessions = pd.read_csv(out/f'{root}_historical_session_audit.csv')
        daily['date'] = pd.to_datetime(daily.date).dt.date
        sessions['trade_date'] = pd.to_datetime(sessions.trade_date).dt.date
        assert len(sessions)==len(pd.date_range(START,END))
        assert not sessions.trade_date.duplicated().any()
        assert not daily.date.duplicated().any()
        assert set(daily.date)==set(sessions.loc[sessions.bars_observed.gt(0),'trade_date'])
        assert daily.bars_observed.gt(0).all()
        observed = sessions.loc[sessions.bars_observed.gt(0)].copy()
        expected_roll = observed.selected_contract.ne(observed.selected_contract.shift())
        expected_roll.iloc[0] = False
        assert observed.roll_day.tolist()==expected_roll.tolist()
        assert daily.roll_day.tolist()==expected_roll.tolist()
        assert daily.selected_contract.tolist()==observed.selected_contract.tolist()
        # Reconcile the overlapping calibration year with the previously
        # validated aggregation, without reranking or using liquidity measures.
        old = pd.read_csv(PARENT/f'{root}_2024_daily_volume.csv')
        old['date'] = pd.to_datetime(old.date).dt.date
        current = daily.loc[pd.to_datetime(daily.date).dt.year.eq(2024)]
        compared = current.merge(old,on='date',suffixes=('_historical','_step11'),validate='one_to_one')
        assert len(compared)==len(current)==len(old)
        for field in ('open','high','low','close','volume','bars_observed'):
            assert np.allclose(compared[field+'_historical'],compared[field+'_step11'],
                rtol=1e-12,atol=1e-12,equal_nan=True), '2024 aggregation changed: '+root+'/'+field
        for row in daily.itertuples():
            rule = resolve_futures_session(root,row.date,configs)
            assert row.session_rule_id==rule.rule_id and row.session_status=='VERIFIED'
            assert Path(row.source_file).name==f'{root}_{row.selected_contract}_1min.txt'
        changes=transitions.loc[transitions.root.eq(root)]
        ready, reason=ready_for_analysis(daily,sessions,int((~changes.validation_passed).sum()))
        saved=coverage.loc[coverage.provider_root.eq(root)].iloc[0]
        assert ready==saved.final_analysis_ready
        assert len(daily)==saved.included_asset_days
        absent=required.loc[required.provider_root.eq(root)&~required.contract_file_exists]
        missed=missing.loc[missing.provider_root.eq(root)]
        assert set(absent.selected_contract)==set(missed.selected_contract)
        assert not missed.substituted.any()
        assert set(missed.trade_date).isdisjoint(set(daily.date.astype(str)))
        checks.append(dict(provider_root=root, observed_asset_days=len(daily),
            observed_transitions=len(changes), failed_transition_checks=int((~changes.validation_passed).sum()),
            final_analysis_ready=ready, reconciliation_passed=True, matches_prior_2024_ohlcv=True))
    result=pd.DataFrame(checks)
    result.to_csv(out/'output_validation.csv',index=False)
    return result


def run():
    started=time.perf_counter(); OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'read_audits').mkdir(exist_ok=True)
    protected = protected_hashes()
    selected = pd.read_csv(PARENT/'selected_futures.csv')
    if set(selected.provider_root) != set(ROOTS) or len(selected) != 9:
        raise ValueError('Frozen selected roots differ; no reranking permitted')
    raw, _ = verify_hashes(PROJECT/'data/raw_bloomberg'); require_verified(raw)
    mapping = pd.read_csv(PARENT/'provider_root_mapping.csv')
    configs, rules, unresolved = historical_configs(mapping)
    rules.to_csv(OUT/'historical_session_rules.csv',index=False)
    unresolved.to_csv(OUT/'unresolved_session_periods.csv',index=False)
    pd.DataFrame(SOURCES, columns=['source_id','source_url_or_relative_path','source_date','evidence_scope']).assign(
        review_date='2026-10-14', limitations='Regular Globex clocks; historical holiday/early-close settlement-date exceptions not exhaustively certified').to_csv(
            OUT/'historical_session_sources.csv',index=False)
    directory = intraday_root()/'futures'
    provider_doc = intraday_root()/'_documentation/.archive/futures.txt'
    doc_hash = sha256(provider_doc)
    # Read provider metadata; no raw copy is made.
    documentation = provider_doc.read_text(encoding='utf-8-sig')
    if 'Eastern' not in documentation:
        raise ValueError('Expected provider timezone documentation not found')
    coverage, contracts, missing, transitions, scans, maps = [],[],[],[],[],[]
    for root in ROOTS:
        calendar_path=directory/f'{root}_continuous_contract_dates.txt'
        map_hash=sha256(calendar_path)
        calendar=parse_provider_calendar(calendar_path)
        result=process_root(root,directory,calendar,configs,OUT)
        record, files, absent, changes, reads=result
        coverage.append(record); contracts.extend(files); missing.extend(absent)
        transitions.append(changes); scans.extend(reads)
        assert sha256(calendar_path)==map_hash
        maps.append(dict(provider_root=root,file_name=calendar_path.name,sha256=map_hash))
        pd.DataFrame(coverage).to_csv(OUT/'historical_daily_coverage.csv',index=False)
        print(f'Completed {root}: {record["included_asset_days"]} observed days; ready={record["final_analysis_ready"]}',flush=True)
    coverage=pd.DataFrame(coverage)
    pd.DataFrame(contracts).to_csv(OUT/'required_contract_audit.csv',index=False)
    pd.DataFrame(missing).to_csv(OUT/'missing_contract_audit.csv',index=False)
    pd.concat(transitions,ignore_index=True).to_csv(OUT/'historical_transition_validation.csv',index=False)
    pd.DataFrame(scans).to_csv(OUT/'file_scan_audit.csv',index=False)
    pd.DataFrame(maps).to_csv(OUT/'provider_mapping_hashes.csv',index=False)
    coverage[['provider_root','final_analysis_ready','readiness_reason','remaining_limitation']].to_csv(
        OUT/'selected_futures_analysis_readiness.csv',index=False)
    assert doc_hash==sha256(provider_doc)
    assert protected==protected_hashes(), 'Prior outputs or protected documentation changed'
    # Verify every source still has its exact scan-time metadata.
    for row in scans:
        stat=(directory/row['file_name']).stat()
        assert (stat.st_size,stat.st_mtime_ns)==(row['size_bytes'],row['mtime_ns'])
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    raw.to_csv(OUT/'raw_bloomberg_hash_verification.csv',index=False)
    validate_saved_outputs(OUT)
    seconds=time.perf_counter()-started
    report='# Step 11.1 historical futures session certification\n\n'
    report+='Frozen nine roots retained; no reranking, Roll or estimator calculations. Daily OHLCV uses physical observations only, exact daily provider mappings and unadjusted individual contracts.\n\n'
    report+=table_md(coverage)+'\n\n'
    report+='Date-effective regular rules\n\n'+table_md(rules)+'\n\n'
    report+='Unresolved periods (excluded, never aggregated)\n\n'+table_md(unresolved)+'\n\n'
    absent=pd.DataFrame(missing)
    report+='Missing required individual files\n\n'+table_md(absent.groupby(['provider_root','selected_contract'],as_index=False).agg(
        affected_mapped_dates=('trade_date','size'),first_date=('trade_date','min'),last_date=('trade_date','max'),
        other_contract_potential_rows=('other_required_contract_potential_rows','sum')))+'\n\n'
    report+='Readiness is construction validity for the included unbalanced panel, not full historical completeness. The new selected_futures_analysis_readiness.csv supersedes the older completeness-based Step-11 readiness fields; the frozen selection file is retained unchanged as an audit artifact. Missing files remain source-unavailable; unresolved periods and unmapped calendar dates remain audit-only. Invalid OHLCV and zero-volume/gap diagnostics are preserved rather than cleaned or used as liquidity exclusions. Failed transition evening checks require review and block readiness; no automatic repair. Previous contract is the previous observed selected contract, across empty dates.\n\n'
    report+='Scope limitation: VERIFIED denotes the date-effective regular primary-session envelope. Calendar-ending labels follow the project overnight rule, not a certified exchange settlement/business-day calendar. A complete historical holiday, early-close and special-closure override calendar remains outside this certification. Existing early ends and gaps are preserved without filling. Full exchange-calendar certification remains a limitation before claiming a complete futures-class convention freeze.\n\n'
    report+='The 2010 FX guide corroborates an earlier clock but is not treated as proof of unchanged hours over every subsequent year. FX AD/B6/J1/E6 and Treasury ZF outside 2024 remain UNRESOLVED. No new verified intervals are invented from current specifications. Missing-file alternate-observation counts are physical timestamp availability checks in other required selected files, not verified sessions and never replacements.\n\n'
    report+='Official evidence:\n\n'+'\n'.join(f'- [{key}]({url}): {scope}.' for key,url,date,scope in SOURCES if url.startswith('https:'))+'\n\n'
    report+=f'All 11 Bloomberg hashes verified; prior Step-5/9/11 outputs and protected documents unchanged. Required individual files scanned: {len(scans)}; bytes scanned: {sum(r["bytes_scanned"] for r in scans):,}; runtime: {seconds:.1f} seconds. Raw source SHA-256, size and modification times are recorded. Reproduce with `src/futures_historical_sessions.py`.\n'
    (OUT/'step11_1_review.md').write_text(report,encoding='utf-8')
    manifest=dict(runtime_seconds=seconds, bytes_scanned=sum(r['bytes_scanned'] for r in scans),
        provider_document_sha256=doc_hash, protected_outputs_sha256=protected,
        implementation_sha256=sha256(Path(__file__)),
        no_benchmark_or_estimator_calculations=True, frozen_selected_roots=list(ROOTS))
    manifest['output_sha256']={p.name:sha256(p) for p in OUT.glob('*') if p.is_file() and p.name!='run_manifest.json'}
    (OUT/'run_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':
    run()
