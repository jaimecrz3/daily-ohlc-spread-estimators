"""Step 11.2 evidence decisions and observed-calendar study-design review.

Official-source findings are a reviewed research snapshot, not automatic legal
certification. No session config changes are warranted by this evidence set.
Reproduce: .venv/Scripts/python.exe -B src/futures_targeted_session_review.py
"""
from pathlib import Path
import json

import pandas as pd

from bloomberg_io import sha256, verify_hashes, require_verified
from futures_roll import table_md

PROJECT=Path(__file__).resolve().parents[1]
PARENT=PROJECT/'outputs/diagnostics/final_universe/futures_final'
OUT=PARENT/'historical'
TARGETS={'AD':'6C','B6':'6B','J1':'6J','E6':'6E','ZF':'ZF'}
CME='https://www.cmegroup.com/'
NEW_FILES={'targeted_session_resolution.csv','targeted_session_evidence.csv',
    'futures_study_design_readiness.md','targeted_session_resolution_manifest.json',
    'step11_2_test_results.txt'}
# Publication years are never silently converted to rule effective intervals.
EVIDENCE=(
    ('CLOSE2015','all',CME+'tools-information/lookups/advisories/electronic-trading/20150914.html',
     '2015-09-14','2015-09-21','Events: Changes to Daily Maintenance Period',
     'reviewed_full_text','Scope is equity/COMEX/NYMEX/DME; other markets unchanged. This close-time change does not apply to selected FX or CBOT Treasury futures.',False),
    ('FX2010','AD;B6;J1;E6',CME+'trading/fx/files/FX248-2010_FX_Product_Guide_and_Calendar.pdf',
     '2010','','printed p26 / PDF p33: FX Futures Trading Hours',
     'reviewed_full_text','Globex opens 17:00 Chicago for next trade date, closes 16:00; Friday close and Sunday reopen. Historical snapshot predates requested intervals.',False),
    ('FX2015','AD;B6;J1;E6',CME+'tools-information/lookups/advisories/ser/SER-7282.html',
     '2015-01-14','2015-04-02;2015-04-03;2015-04-05','FX Futures and Options Contracts bullets',
     'reviewed_full_text','Confirms ordinary 16:00 CT close April 2 and 17:00 CT reopening April 5; April 3 is a special early close. Dated observations do not establish a continuous study-period rule.',False),
    ('FX2021','AD;B6;J1;E6',CME+'trading/fx/files/fx-product-guide-2021-us.pdf',
     '2021','','indexed contents: Trading hours p10; 2021 holiday calendar p113',
     'indexed_excerpt_only_full_pdf_unavailable_in_browser','Official guide identified; full hours table and effective-date coverage not independently retrieved in this review. No interval promoted from search metadata.',False),
    ('FX2023','AD;B6;J1;E6',CME+'trading/fx/files/fx-product-guide-2023-us.pdf',
     '2023','','prior Step-11 source FX2023; guide normal-hours section',
     'prior_verified_2024_evidence_reused_full_pdf_unavailable_in_current_browser','Existing evidence supports frozen 2024 regular envelope. Guide year and January 2024 calendar do not establish a new effective start or bridge other years.',False),
    ('ZF_GUIDE','ZF',CME+'content/dam/cmegroup/education/files/understanding-treasury-futures.pdf',
     '2024','','Table 2: 5-Year Treasury contract specifications',
     'reviewed_full_text','5-Year Treasury normal Globex clock is 17:00-16:00 Chicago. Existing 2024 evidence; not a dated history of revisions for 2015-2023 or 2025.',False),
    ('ZF_WHITEPAPER','ZF',CME+'education/whitepapers/insights-into-us-treasury-futures',
     'publication/effective date not established','','Treasury Futures Contract Details: 5-Yr T-Note column',
     'reviewed_full_text','Shows Globex 17:00-16:00. Examples dated 2014 and historical statistics are not publication or rule effective dates; no continuous interval inferred.',False),
    ('ZF_RULE20','ZF',CME+'rulebook/CBOT/II/20.pdf',
     'current revision/effective range not established','','Rules 20100 and 20102.A',
     'reviewed_full_text','Times are Chicago; exchange determines trading hours. The chapter supplies no dated normal opening/closing schedule establishing the requested historical intervals.',False),
    ('CAD_RULE2012','AD',CME+'market-regulation/files/12-422.pdf',
     '2012-12-10','','Chapter 252 / Rule 25201.A, indexed excerpt',
     'indexed_excerpt_only','CAD trading hours are determined by the exchange; this filing does not enumerate a normal clock or certify intervening dates.',False),
    ('NOTICE2021','all',CME+'notices/electronic-trading/2021/10/20211025.html',
     '2021-10-25','','BMD night session; Treasury TAS launch',
     'reviewed_full_text','BMD night-session change is not these roots; ZTF TAS eligibility is not a ZF outright regular-hours change.',False),
    ('NOTICE2025','all',CME+'notices/electronic-trading/2025/04/20250407.html',
     '2025-04-07','2025-04-14;2025-04-21','Weather hours change; FX Spot+ launch; FX non-tradable markers',
     'reviewed_full_text','Clock change concerns weather products. Spot+ and non-tradable FX markers do not change the selected outright futures regular session.',False),
    ('ZF_OPTIONS2025','ZF',CME+'content/dam/cmegroup/market-regulation/rule-filings/2025/5/25-178.pdf',
     '2025-05-20','2025-06-16','Section 1 / Figure A: Tuesday and Thursday weekly options',
     'reviewed_full_text','The stated session is for new Treasury weekly options, not independent date-effective certification of ZF outright futures.',False),
)


def evidence_table():
    return pd.DataFrame(EVIDENCE,columns=['source_id','applicable_roots','source_url','source_date',
        'source_stated_event_dates','source_location','access_status','finding_and_limitation',
        'certifies_requested_continuous_interval']).assign(review_date='2026-10-14')


def resolution_table(evidence, provider_doc_hash):
    rows=[]
    for root,symbol in TARGETS.items():
        sources=evidence.loc[evidence.applicable_roots.eq('all') |
            evidence.applicable_roots.str.split(';').apply(lambda roots:root in roots)]
        if sources.certifies_requested_continuous_interval.any():
            raise ValueError('New certification requires independently reviewed effective dates and a targeted rebuild; not automatic')
        for start,end in [('2015-09-21','2023-12-31'),('2025-01-01','2025-12-31')]:
            rows.append(dict(provider_root=root,exchange_symbol=symbol,requested_start=start,requested_end=end,
                resolution_status='UNRESOLVED',gained_historical_certification=False,
                verified_effective_start='',verified_effective_end='',
                timezone='America/New_York',timezone_evidence='_documentation/.archive/futures.txt',
                timezone_document_sha256=provider_doc_hash,
                certified_session_open='',certified_session_close='',certified_maintenance_break='',
                certified_trade_date_assignment='',
                corroborated_regular_open_eastern='18:00 previous calendar day',
                corroborated_regular_close_eastern='17:00 trade date exclusive',
                corroborated_maintenance_eastern='17:00-18:00',
                corroborated_trade_date_assignment='>=18:00 next calendar date; <17:00 current calendar date; maintenance excluded',
                corroboration_is_historical_interval_certification=False,
                close_change_2015_09_21_applies=False,close_change_source_id='CLOSE2015',
                later_regular_session_change_status='No applicable change established in reviewed set; absence of a located notice is not proof of unchanged history',
                source_ids=';'.join(sources.source_id),source_urls=';'.join(sources.source_url),
                reason='No continuous date-effective chain established; snapshot corroboration cannot bridge undocumented gaps',
                rebuild_performed=False,included_days_before=259,included_days_after=259))
    return pd.DataFrame(rows)


def calendar_comparison(panels, tiers):
    """Compare physical observed dates; never insert, impute or relabel dates."""
    if not panels or set(panels)!=set(tiers):
        raise ValueError('Root/tier mismatch')
    date_sets={}
    for root,data in panels.items():
        dates=pd.to_datetime(data['date'],errors='raise')
        if dates.isna().any() or dates.duplicated().any():
            raise ValueError('Missing/duplicate asset-day')
        date_sets[root]=set(dates.dt.date)
    sets_2024={root:{day for day in days if day.year==2024} for root,days in date_sets.items()}
    common=set.intersection(*sets_2024.values())
    union=set.union(*sets_2024.values())
    rows=[dict(provider_root=root,liquidity_tier=tiers[root],
        first_included_date=min(days) if days else '',last_included_date=max(days) if days else '',
        full_available_asset_days=len(days),observed_2024_days=len(sets_2024[root]),
        common_2024_days=len(common),non_2024_days=sum(day.year!=2024 for day in days))
        for root,days in date_sets.items()]
    by_root=pd.DataFrame(rows)
    by_tier=by_root.groupby('liquidity_tier',as_index=False).agg(
        selected_roots=('provider_root','size'),A_asset_days=('full_available_asset_days','sum'),
        B_asset_days=('common_2024_days','sum'),non_2024_asset_days=('non_2024_days','sum'))
    return by_root,by_tier,common,common==union


def prior_hashes():
    dirs=[PROJECT/'outputs/diagnostics/futures_roll',PROJECT/'outputs/diagnostics/final_universe/futures_crypto',PARENT]
    files=[p for d in dirs for p in d.rglob('*') if p.is_file() and not (p.parent==OUT and p.name in NEW_FILES)]
    files += [PROJECT/name for name in ('README.md','design_decisions.md','data_manifest.csv',
        'manifests/data_manifest.csv','data/raw_bloomberg/sha256_manifest.csv') if (PROJECT/name).is_file()]
    return {str(p.relative_to(PROJECT)):sha256(p) for p in files}


def run():
    protected=prior_hashes()
    history_manifest=json.loads((OUT/'run_manifest.json').read_text(encoding='utf-8'))
    for name,digest in history_manifest['output_sha256'].items():
        assert sha256(OUT/name)==digest,'Prior historical artifact changed: '+name
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg'); require_verified(raw)
    selected=pd.read_csv(PARENT/'selected_futures.csv',usecols=['provider_root','liquidity_tier'])
    assert set(selected.provider_root)=={'HG','AD','B6','J1','GC','E6','NQ','ZF','ES'} and len(selected)==9
    panels={root:pd.read_csv(OUT/f'{root}_historical_daily_ohlcv.csv',usecols=['date']) for root in selected.provider_root}
    by_root,by_tier,common,identical=calendar_comparison(panels,dict(zip(selected.provider_root,selected.liquidity_tier)))
    sources=evidence_table()
    resolutions=resolution_table(sources,history_manifest['provider_document_sha256'])
    for root in TARGETS:
        assert by_root.loc[by_root.provider_root.eq(root),'full_available_asset_days'].iloc[0]==259
    sources.to_csv(OUT/'targeted_session_evidence.csv',index=False)
    resolutions.to_csv(OUT/'targeted_session_resolution.csv',index=False)
    total_A=int(by_root.full_available_asset_days.sum()); total_B=len(common)*len(panels)
    report='# Step 11.2 targeted historical session and study-design review\n\n'
    report+='No selected root gained continuous historical certification. No configuration was extended and no daily panel was rebuilt. The prior construction-validity readiness flags remain valid for included observations; they do not certify common 2015-2025 temporal support. No universe change, liquidity ranking or Roll/CS/AR/EDGE calculation occurred.\n\n'
    report+='Evidence decision\n\nThe September 21, 2015 earlier-close notice expressly covers equity/COMEX/NYMEX/DME and leaves other markets unchanged. It does not apply to CME currency futures AD/B6/J1/E6 or CBOT Treasury ZF. Old and later normal-clock snapshots corroborate 18:00-17:00 America/New_York, with a 17:00-18:00 break and an overnight ending-date label, but do not certify continuity across the requested years.\n\n'
    report+='The five roots remain UNRESOLVED for 2015-01-01 through 2023-12-31 and 2025-01-01 through 2025-12-31. The targeted search covered 2015-09-21 onward; the pre-September 2015 gap is also retained unchanged. Verified-effective fields are intentionally blank in targeted_session_resolution.csv; corroborated clocks are separate and cannot authorize aggregation. First Rate timezone evidence is reused from its hash-recorded authoritative document; no provider file was reread or copied for this research-only step.\n\n'
    report+='No applicable later regular-hours change was established in the reviewed set. This is not an exhaustive proof that no change occurred. The 2021 BMD night-session and TAS notices, 2025 weather/Spot+/marker changes, and Treasury options launch do not establish outright clocks for these roots. The current ZF rulebook delegates hours to the exchange. Undated article examples and present-day specifications cannot supply historical effective dates. Full 2021/2023 guide PDFs were not retrieved by the browser; access limitations and indexed-only findings are explicitly recorded. No third-party trading sites were used as evidence.\n\n'
    report+='Observed support, unchanged\n\n'+table_md(by_root)+'\n\nTier/date support\n\n'+table_md(by_tier)+'\n\n'
    comparison=pd.DataFrame([
        ['Temporal comparability','Root-specific time support; only HG/GC/NQ/ES extend beyond 2024','All nine share the same observed 2024 dates'],
        ['2015-2025 question','Retains long history for four roots, but cannot identify a nine-root full-period tier comparison','Directly comparable 2024 slice; explicitly narrower than the full research question'],
        ['Sample size',f'{total_A:,} observed asset-days across nine roots',f'{total_B:,} observed asset-days: {len(common)} dates x 9 roots'],
        ['Calendar-period confounding','Substantial: HIGH has two long-history roots; LOW and MEDIUM each have one','Reduced by matched dates; product-family/root confounding and one-year regime limits remain'],
        ['Interpretation','Supplementary heterogeneous-history descriptive panel with explicit temporal controls/restrictions','Cleaner all-nine liquidity-tier comparison conditional on 2024; no claim about all 2015-2025 regimes']
    ],columns=['Criterion','A: available unbalanced 2015-2025 support','B: common observed 2024 calendar'])
    report+='Design alternatives\n\n'+table_md(comparison)+'\n\n'
    report+=f'The 2024 observed calendars are identical across all nine: {identical}. The common calendar has {len(common)} dates, {min(common)} through {max(common)}. These are observed session dates, not 366 synthesized calendar days. No missing sessions are compressed or relabelled. B has {total_B/total_A:.1%} of A\'s asset-days; fewer serially dependent observations and nine securities should not be mistaken for an equivalent number of independent samples.\n\n'
    report+='Methodological recommendation: B is cleaner for comparing all nine roots and all three liquidity tiers under current certification. This is a design recommendation, not an automatic time-window freeze. A is construction-valid as an explicitly heterogeneous descriptive sample, but is not yet defensible as an unqualified all-nine 2015-2025 tier comparison: five roots contribute only 2024. Date fixed effects alone do not create historical support for absent roots or remove changes in product composition. Do not pool periods and attribute their differences solely to liquidity tiers.\n\n'
    report+='A broader all-nine 2015-2025 primary design needs independently dated historical schedules closing the five gaps, followed by targeted rebuilding and transition checks. Late-2025 missing files remain source-unavailable and would still produce an allowed unbalanced panel; their existence does not justify substitution. Missing-file tail gaps and ordinary holiday/early-close limitations are separate from the much larger certification exclusions.\n\n'
    report+='Selecting/calibrating tiers in 2024 is already frozen and descriptive. Comparing on 2024 conditions results on that calibration period; it is not an independent historical or out-of-sample validation. Keep this limitation explicit. The 2021 equity-index rule change for ES/NQ is unchanged. No recommendation uses price levels, benchmark definedness, spreads or estimator performance.\n\n'
    report+='Official evidence and scope\n\n'+'\n'.join(f'- [{r.source_id}]({r.source_url}): {r.finding_and_limitation}' for r in sources.itertuples())+'\n\n'
    report+='Reproduce with `src/futures_targeted_session_review.py`. Original daily panels, session rules, selected roots and all Step-5/9/11/11.1 artifacts are retained unchanged. See targeted_session_resolution_manifest.json for input/output hashes.\n'
    tests=OUT/'step11_2_test_results.txt'
    if tests.exists():
        report+='\nFull-suite validation record:\n\n```text\n'+tests.read_text(encoding='utf-8').strip()+'\n```\n'
    (OUT/'futures_study_design_readiness.md').write_text(report,encoding='utf-8')
    assert protected==prior_hashes(),'Prior artifacts changed'
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    manifest=dict(review_date='2026-10-14',gained_certification_roots=[],rebuilt_roots=[],
        unchanged_included_days=by_root.set_index('provider_root').full_available_asset_days.to_dict(),
        A_asset_days=total_A,B_asset_days=total_B,common_2024_dates=len(common),
        common_2024_calendars_identical=identical,bloomberg_raw_hashes_verified=len(raw),
        protected_prior_sha256=protected,code_sha256=sha256(Path(__file__)),
        no_intraday_provider_reads_or_raw_writes=True,no_benchmark_or_estimator_calculations=True)
    manifest['output_sha256']={name:sha256(OUT/name) for name in NEW_FILES
        if name!='targeted_session_resolution_manifest.json' and (OUT/name).is_file()}
    (OUT/'targeted_session_resolution_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(by_root.to_string(index=False));print(by_tier.to_string(index=False))
    print(f'A={total_A}; B={total_B}; common dates={len(common)}; identical={identical}')


if __name__=='__main__':
    run()
