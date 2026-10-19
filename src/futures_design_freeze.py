"""Freeze the user-approved Step 11.3 universe and observed 2024 calendar.

Reads only existing derived metadata/date columns; no provider price processing.
Run: .venv/Scripts/python.exe -B src/futures_design_freeze.py
"""
from pathlib import Path

import pandas as pd
import yaml

from bloomberg_io import sha256, verify_hashes, require_verified

PROJECT=Path(__file__).resolve().parents[1]
OUT=PROJECT/'outputs/diagnostics/final_universe/futures_final'
HISTORY=OUT/'historical'
TIERS={'LOW':['HG','AD','B6'],'MEDIUM':['J1','GC','E6'],'HIGH':['NQ','ZF','ES']}


def run():
    names={'futures_final_spec.yaml','futures_design_freeze_review.md'}
    protected=[p for p in OUT.rglob('*') if p.is_file() and not (p.parent==OUT and p.name in names)]
    protected += [PROJECT/p for p in ('README.md','design_decisions.md','data_manifest.csv',
        'manifests/data_manifest.csv','data/raw_bloomberg/sha256_manifest.csv') if (PROJECT/p).is_file()]
    before={p:sha256(p) for p in protected}
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    roots=[root for group in TIERS.values() for root in group]
    selected=pd.read_csv(OUT/'selected_futures.csv',usecols=['provider_root','liquidity_tier'])
    assert len(selected)==9 and not selected.provider_root.duplicated().any()
    assert selected.set_index('provider_root').liquidity_tier.to_dict()=={
        root:tier for tier,group in TIERS.items() for root in group}
    calendars={}; panel_hashes={}
    for root in roots:
        path=HISTORY/f'{root}_historical_daily_ohlcv.csv'
        dates=pd.to_datetime(pd.read_csv(path,usecols=['date']).date,errors='raise')
        assert dates.notna().all() and not dates.duplicated().any()
        calendars[root]=set(dates.loc[dates.dt.year.eq(2024)].dt.strftime('%Y-%m-%d'))
        panel_hashes[str(path.relative_to(PROJECT)).replace('\\','/')]=sha256(path)
    common=sorted(set.intersection(*calendars.values()))
    assert all(days==set(common) for days in calendars.values())
    assert len(common)==259 and common[0]=='2024-01-02' and common[-1]=='2024-12-31'
    rules=pd.read_csv(HISTORY/'historical_session_rules.csv')
    rule_ids={}
    for root in roots:
        active=rules.loc[rules.provider_root.eq(root)&rules.effective_start.le(common[0])&rules.effective_end.ge(common[-1])]
        assert len(active)==1
        rule=active.iloc[0]
        assert rule.status=='VERIFIED' and rule.timezone=='America/New_York'
        assert rule.session_open=='18:00' and rule.session_close=='17:00'
        assert rule.maintenance_intervals=='[["17:00", "18:00"]]'
        rule_ids[root]=rule.session_rule_id
    spec=dict(status='FROZEN',futures_universe_status='FROZEN',primary_analysis_window_status='FROZEN',
        approval_basis='User Step 11.3; no new selection or evidence search',
        selected_roots=roots,liquidity_tiers=TIERS,liquidity_calibration_year=2024,
        primary_analysis_start=common[0],primary_analysis_end=common[-1],
        primary_common_dates=259,primary_asset_days=2331,
        primary_design='2024 common observed calendar; all nine roots on the same observed trade dates',
        observational_unit='asset-trade_date',primary_common_trade_dates=common,
        primary_scope='2024 futures comparison only; not a full 2015-2025 futures horse race',
        design_reason='Verified common temporal support reduces major calendar-period and product-composition confounding across LOW/MEDIUM/HIGH tiers',
        historical_supplementary_roots=['HG','GC','NQ','ES'],
        historical_supplementary_role='Verified longer panels retained for supplementary historical/descriptive analysis only',
        supplementary_pooling_policy='Never pool heterogeneous historical support with the primary 2024 panel and attribute differences solely to liquidity',
        unresolved_historical_roots=['AD','B6','J1','E6','ZF'],
        unresolved_historical_intervals=[{'start':'2015-01-01','end':'2023-12-31'},
            {'start':'2025-01-01','end':'2025-12-31'}],
        missing_contract_policy='Source-unavailable dates remain audited; no substitution, missing-bar filling or synthesized trade dates',
        continuous_price_policy='Individual unadjusted contracts only; all continuous-price files, including back-adjusted files, prohibited',
        roll_mapping_policy='Exact provider daily trade-date mapping; one selected individual contract for the entire overnight session; no forward-filled mapping or intraday mixing',
        session_rule_policy=dict(timezone='America/New_York',
            primary_open='18:00 previous calendar day inclusive',primary_close='17:00 trade date exclusive',
            maintenance='17:00 <= local time < 18:00 excluded',
            trade_date_assignment='time >=18:00: calendar date +1; time <17:00: calendar date; maintenance excluded',
            configuration='src/futures_historical_sessions.py:historical_configs; explicit root-specific rules required',
            rules_artifact='historical/historical_session_rules.csv',primary_rule_ids=rule_ids,
            historical_policy='Use verified date-effective intervals only; exclude/audit unresolved dates; no extrapolation',
            equity_pause='ES/NQ pre-2021-06-28 pause remains historical only; no afternoon pause in 2024',
            calendar_scope='Regular primary-session envelope; exhaustive historical holiday/early-close settlement-date overrides remain uncertified'),
        methodological_limitations=[
            '2024 is also the liquidity-calibration year; primary futures analysis is conditional on that calendar year',
            'This is not an out-of-sample liquidity-tier evaluation',
            'Historical sessions for AD/B6/J1/E6/ZF outside 2024 remain unresolved',
            'Missing late-2025 individual contracts remain source-unavailable',
            'No substitutions or extrapolated session rules permitted',
            'Common dates reduce calendar confounding but do not remove product-family/root confounding or one-year regime limitations'],
        raw_data_policy='Immutable; no modification or duplication',
        no_provider_benchmark_or_estimator_calculations=True,
        provenance=dict(selected_universe_sha256=sha256(OUT/'selected_futures.csv'),
            session_rules_sha256=sha256(HISTORY/'historical_session_rules.csv'),
            input_daily_panel_sha256=panel_hashes))
    path=OUT/'futures_final_spec.yaml'
    path.write_text(yaml.safe_dump(spec,sort_keys=False,allow_unicode=True),encoding='utf-8')
    saved=yaml.safe_load(path.read_text(encoding='utf-8'))
    assert saved==spec and saved['primary_asset_days']==9*len(saved['primary_common_trade_dates'])
    review='''# Step 11.3 final futures design freeze

The selected futures universe and primary analysis window are **FROZEN**, as explicitly approved in Step 11.3. This supersedes the Step-11.2 recommendation-only status. Earlier evidence reviews remain unchanged as historical audit records.

| Liquidity tier | Frozen provider roots |
| --- | --- |
| LOW | HG, AD, B6 |
| MEDIUM | J1, GC, E6 |
| HIGH | NQ, ZF, ES |

The primary futures horse race will use the **2024 common observed calendar**: **2024-01-02 through 2024-12-31**, **259 identical observed trade dates** across all nine roots and **2,331 asset-days** (777 per tier). This is a 2024 futures comparison, not a full 2015-2025 futures comparison. The approved window is the currently verified common-period design that avoids major calendar-period and product-composition confounding in the LOW/MEDIUM/HIGH comparison. Product-family/root differences and one-year regime limitations still remain.

The exact 259 observed dates and input-panel hashes are embedded in `futures_final_spec.yaml`. They were checked against date columns of all nine existing derived panels, without reading price columns, reranking, reaggregating or constructing a new calendar. No missing sessions were filled, compressed or relabelled. The frozen universe and root-specific 2024 session rules also reconcile to prior artifacts.

Verified longer panels for **HG, GC, NQ and ES** are retained for **supplementary historical/descriptive analysis only**. Their heterogeneous temporal support is excluded from the primary liquidity-tier horse race. Do not pool those histories with the all-nine 2024 comparison and attribute differences solely to liquidity.

2024 is also the liquidity-calibration year. The primary futures analysis is conditional on that calendar year and is **not an out-of-sample liquidity-tier evaluation**. This deliberately narrows the futures component of the stated 2015-2025 research question.

AD/B6/J1/E6/ZF sessions remain unresolved for 2015-2023 and 2025; those dates remain excluded and audited. Missing late-2025 individual contracts remain source-unavailable, with no substitution. Neither limitation changes the frozen common 2024 calendar. Unbalanced historical availability is preserved rather than repaired.

Only unadjusted individual-contract prices may be used. Continuous-price files, including back-adjusted continuous prices, are prohibited. Use the provider's exact daily trade-date assignment to select one contract for the whole overnight session; do not forward-fill missing mappings or mix contracts within a trade date. Provider transition dates and observed contract-change flags remain distinct.

Primary sessions use the existing explicit root-specific rules: America/New_York, previous calendar day 18:00 inclusive through trade date 17:00 exclusive; 17:00-18:00 is excluded. The ES/NQ afternoon pause removed on 2021-06-28 must not be reintroduced in 2024. Historical supplementary periods retain their existing date-effective rules. No undocumented session extrapolation is permitted. These are verified regular envelopes, not an exhaustive historical settlement/holiday override calendar. No bars are synthesized for gaps, maintenance, weekends, holidays or early closes; existing quality flags remain preserved.

This artifact freezes the universe and calendar; it introduces no new comparison-quality exclusion or estimator-specific field-validity rule. No Roll, CS, AR or EDGE provider values, or performance measures, were calculated. No additional historical evidence was searched. Raw data, prior outputs, README.md, design_decisions.md and data_manifest.csv are unchanged. All 11 Bloomberg raw hashes match.

Reproduce and validate these artifacts with `.venv/Scripts/python.exe -B src/futures_design_freeze.py`.
'''
    (OUT/'futures_design_freeze_review.md').write_text(review,encoding='utf-8')
    assert before=={p:sha256(p) for p in protected}
    raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    print('FROZEN: 9 roots; 259 common observed dates; 2,331 asset-days. Prior artifacts unchanged; all 11 Bloomberg hashes match.')


if __name__=='__main__':
    run()
