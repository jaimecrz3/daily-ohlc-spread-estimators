"""Generate Step-10 mathematical freeze-review artifacts from synthetic inputs.

Run: .venv/Scripts/python.exe -B src/benchmark_freeze_review.py
Never reads provider bars, benchmark results, or estimator performance.
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import yaml

try:
    from .benchmark import build_roll_benchmark, MIN_ROLL_PAIRS, COVARIANCE_DDOF, PRIMARY_MODE, SENSITIVITY_MODE
except ImportError:
    from benchmark import build_roll_benchmark, MIN_ROLL_PAIRS, COVARIANCE_DDOF, PRIMARY_MODE, SENSITIVITY_MODE

PROJECT=Path(__file__).resolve().parents[1]
OUT=PROJECT/'outputs/diagnostics/benchmark_freeze'
ARTICLE='https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1984.tb03897.x'
PDF='https://www.bauer.uh.edu/rsusmel/phd/roll1984.pdf'
POLICIES=[
    ('insufficient_minute_bars','fewer than 3 retained observations; no structural three-close lag-pair opportunity','observed asset-day retained; spreads undefined','1 for insufficient pair count'),
    ('invalid_price','one or more non-finite/nonpositive closes; affected returns/pairs ineligible','diagnostic flag; primary reason only when fewer than 2 eligible pairs remain','2 for insufficient pair count'),
    ('invalid_return','eligible exactly-one-minute endpoints yield non-finite arithmetic return or r <= -1 through floating-point arithmetic','flag/mask affected return, breaking its adjacent pairs; no repair or clipping','3 for insufficient pair count'),
    ('source_quality_condition','duplicate timestamps, timezone assignment failure, malformed columns or supplied invalid OHLC flag','existing affected-bar eligibility retained; no blanket asset-day exclusion','4 for insufficient pair count'),
    ('insufficient_consecutive_returns','longest uninterrupted valid one-minute return run is shorter than 2','observed asset-day retained; no valid lag pair','5 for insufficient pair count'),
    ('insufficient_covariance_pairs','fewer than 2 valid adjacent-return pairs; includes a 3-close/1-pair example','sample covariance unavailable, spreads undefined','6 for insufficient pair count'),
    ('non_finite_autocovariance','at least 2 pairs but centered-product covariance is non-finite','preserve covariance diagnostic and undefined spreads','1 when pair count is sufficient'),
    ('non_negative_autocovariance','finite gamma >= 0','preserve gamma; both spreads NaN; benchmark_defined=False; never replace with zero','2 when pair count is sufficient'),
]


def synthetic(closes,times=None):
    times=pd.date_range('2024-01-02 09:30',periods=len(closes),freq='min') if times is None else pd.to_datetime(times)
    return pd.DataFrame({'timestamp':times,'close':closes,'volume':1})


def formula_validation():
    standard=[100,110,99,108.9,98.01]
    cases=[
        ('hand_negative',synthetic(standard),4,3,-1/75,''),
        ('constant_scale_1000',synthetic(np.array(standard)*1000),4,3,-1/75,''),
        ('two_pair_minimum',synthetic(standard[:4]),3,2,-.02,''),
        ('zero_covariance',synthetic([100]*4),3,2,0.,'non_negative_autocovariance'),
        ('positive_covariance',synthetic([100,110,132,171.6]),3,2,.005,'non_negative_autocovariance'),
        ('two_bars',synthetic([100,110]),1,0,np.nan,'insufficient_minute_bars'),
        ('three_closes_one_pair',synthetic([100,110,99]),2,1,np.nan,'insufficient_covariance_pairs'),
        ('missing_minute',synthetic(standard,['2024-01-02 09:30','2024-01-02 09:31','2024-01-02 09:33','2024-01-02 09:34','2024-01-02 09:35']),3,1,np.nan,'insufficient_covariance_pairs'),
        ('all_long_gaps',synthetic([100,110,99],['2024-01-02 09:30','2024-01-02 09:32','2024-01-02 09:35']),0,0,np.nan,'insufficient_consecutive_returns'),
        ('invalid_close',synthetic([100,110,0,108.9,98.01]),2,0,np.nan,'invalid_price'),
        ('invalid_return_overflow_rounding',synthetic([1e-308,1e308,100,110]),1,0,np.nan,'invalid_return'),
        ('source_malformed',synthetic(standard[:4]).assign(malformed_columns=[False,True,False,False]),1,0,np.nan,'source_quality_condition'),
        ('nonfinite_covariance',synthetic([1e-308,1e-153,10,1e156]),3,2,-np.inf,'non_finite_autocovariance'),
    ]
    rows=[]
    for name,data,returns,pairs,gamma,reason in cases:
        row=build_roll_benchmark(data,'SYNTHETIC','stocks').iloc[0]
        expected=2*np.sqrt(-gamma) if np.isfinite(gamma) and gamma<0 else np.nan
        correct=bool(row.one_minute_returns==returns and row.roll_pairs==pairs
            and np.isclose(row.roll_autocovariance,gamma,equal_nan=True)
            and np.isclose(row.roll_spread_relative,expected,equal_nan=True)
            and np.isclose(row.roll_spread_bps,expected*10000,equal_nan=True)
            and row.failure_reason==reason)
        rows.append(dict(validation_case=name,input_role='synthetic_mathematical_validation_only',
            bars_observed=row.bars_observed,one_minute_returns=row.one_minute_returns,roll_pairs=row.roll_pairs,
            expected_covariance=gamma,actual_covariance=row.roll_autocovariance,
            expected_relative_spread=expected,actual_relative_spread=row.roll_spread_relative,
            expected_spread_bps=expected*10000,actual_spread_bps=row.roll_spread_bps,
            covariance_ddof=COVARIANCE_DDOF,minimum_covariance_pairs=MIN_ROLL_PAIRS,
            failure_reason=row.failure_reason,legacy_failure_reason=row.benchmark_failure_reason,
            gaps_gt_one_minute=row.gaps_gt_one_minute,passed=correct))
    result=pd.DataFrame(rows)
    assert result.passed.all(),result.loc[~result.passed]
    return result


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    validations=formula_validation()
    validations.to_csv(OUT/'benchmark_formula_validation.csv',index=False)
    pd.DataFrame(POLICIES,columns=['flag_or_reason','condition','policy','primary_reason_precedence']).to_csv(OUT/'benchmark_failure_policy.csv',index=False)
    candidate=dict(status='freeze_candidate_not_final_approval',benchmark_name='Roll (1984) percentage-return benchmark',
        literature_reference=dict(author='Richard Roll',year=1984,journal='Journal of Finance',volume=39,issue=4,pages='1127-1139',doi='10.1111/j.1540-6261.1984.tb03897.x',percentage_form_location='Section II and footnote 5, page 1130',url=ARTICLE,primary_article_copy=PDF),
        price_input='one-minute First Rate bar close; sampled transaction-price proxy, not tick-level transactions',
        return_definition='r_t = close_t / close_(t-1) - 1 (decimal simple arithmetic return)',
        primary_mode=PRIMARY_MODE,required_gap_minutes=1,
        pair_definition='three consecutive retained observations with both adjacent gaps exactly one minute and both returns eligible; within asset-session-day only',
        covariance_lag=1,covariance_ddof=COVARIANCE_DDOF,minimum_covariance_pairs=MIN_ROLL_PAIRS,
        covariance_calculation='sum((x_i-mean(x))*(y_i-mean(y))) / (n_pairs-1); x=current eligible paired returns, y=their actual immediately preceding returns; means calculated separately on paired vectors',
        nonnegative_covariance_policy='preserve gamma; spread_relative=NaN; spread_bps=NaN; benchmark_defined=false; failure_reason=non_negative_autocovariance',
        output_units=dict(roll_autocovariance='decimal return squared',roll_spread_relative='dimensionless fraction',roll_spread_bps='basis points; relative times 10000'),
        session_source='src/session_rules.py; previously approved session freezes; no new calendars or products',
        sessions=dict(stocks='09:30 <= America/New_York local time < 16:00',etfs='09:30 <= America/New_York local time < 16:00',
            cryptos='UTC calendar day; diagnostic/pilot only until universe freeze',
            futures='ES and CL pilots only: prior day 18:00 inclusive through trade date 17:00 exclusive America/New_York; exact provider-selected individual contract',
            fx='unavailable official archive; no substitution'),
        missing_bar_policy='no filling, resampling or insertion; keep sparse/missing/invalid/duplicate/zero-volume flags',
        gap_bridge_policy='never bridge longer gaps or invalid observations in primary benchmark',
        zero_volume_policy='retain and flag; valid positive prices remain return-eligible; never synthesize zero-volume bars',
        price_eligibility='finite positive close, assigned timezone, no duplicate timestamp/malformed row/supplied invalid OHLC flag; invalid observations break chain rather than being compressed away',
        return_eligibility='finite simple return greater than -1; numerical overflow/underflow/rounding failure flagged and masked',
        structural_minimum_bars_for_one_lag_pair=3,minimum_bars_if_one_complete_contiguous_run=4,
        whole_day_quality_exclusion='none; sufficient remaining valid pairs may define a benchmark despite other flagged observations',
        failed_asset_day_policy='retain every observed session-day; zero-observation dates remain audit-only and are not insufficient-pair analytic rows',
        canonical_fields=dict(defined='benchmark_defined (alias of roll_defined)',failure_reason='failure_reason (detailed primary reason)',legacy_failure_reason='benchmark_failure_reason preserves existing insufficient_roll_pairs compatibility label'),
        diagnostic_flags='coexisting booleans; a structural shortage and its source cause can both be true; failure_reason follows CSV precedence',
        sensitivity=dict(mode=SENSITIVITY_MODE,role='robustness_sensitivity_only',status='prepared_not_implemented_or_executed',primary=False,
            planned_return_definition='simple returns on successive observed eligible bars, allowing positive gaps longer than one minute; invalid observations still break chain',
            planned_pairs='adjacent observed return pairs inside the same verified session-day; never cross sessions, days or contracts',
            limitation='heterogeneous return durations; record gap durations separately; no performance comparison or replacement of primary',
            execution_guard='explicit NotImplementedError from build_roll_benchmark until separately authorized sensitivity implementation'),
        performance_tuning=False,universe_selection_using_benchmark=False,
        pending_review=['transaction-close proxy and Roll efficiency/stationarity assumptions', 'small-sample precision; mathematical minimum is not a reliability threshold',
            'corporate-action-adjusted intraday price scale and source lineage for comparisons', 'sparse sessions and omitted-volume-bar sampling; no coverage cutoff tuned here',
            'full futures/crypto universes remain unfrozen; FX unavailable', 'formal design freeze approval/documentation remains pending'])
    (OUT/'benchmark_freeze_candidate.yaml').write_text(yaml.safe_dump(candidate,sort_keys=False,allow_unicode=True),encoding='utf-8')
    report='# Step 10 Roll benchmark definition: freeze candidate\n\n'
    report+='## Directly from Roll (1984)\n\nRoll derives the price-change spread as twice the square root of negative lag-one covariance. The model relies on transaction prices, informational efficiency and locally stationary price-change distributions. It concerns effective trading costs rather than a daily quoted bid/ask difference. [Original article]('+ARTICLE+').\n\n'
    report+='Section II and footnote 5, p. 1130, explicitly discuss arithmetic percentage returns to estimate an approximate percentage spread. The footnote explains a small approximation bias from the return denominator under a fixed dollar spread. Thus this project uses the literature-supported percentage-return form/adaptation, not an invented modification. [Original article copy, p. 1130]('+PDF+').\n\n'
    report+='## Project-specific numerical and sampling choices\n\nFor retained closes C_t, r_t = C_t/C_(t-1) - 1 only if adjacent timestamps differ by exactly one minute. A covariance pair (x_i,y_i)=(r_t,r_(t-1)) requires the underlying three physical observations to be consecutive one-minute closes. All operations stay inside one asset/session-day and, for futures, one validated selected contract. Invalid observations break chains; filtering them out cannot connect their neighbors.\n\n'
    report+='With n eligible pairs, gamma = sum_i[(x_i-mean(x))(y_i-mean(y))]/(n-1). The two means are calculated separately on the paired vectors, not the full unpaired return series. ddof=1 and n>=2 are unchanged. A contiguous valid run therefore needs four closes/three returns/two pairs; three closes yield one pair and cannot produce a sample covariance. No additional coverage or precision threshold was introduced.\n\n'
    report+='If gamma<0, relative spread = 2*sqrt(-gamma), and bps = 10000*relative spread. Returns are decimal fractions, not numbers already multiplied by 100. If finite gamma>=0, preserve gamma and mark both spreads NaN and benchmark_defined=False; never replace the estimate with zero. The approximation in the literature, sample ddof convention, one-minute/day sampling and this nonnegative sample policy are distinct decisions.\n\n'
    report+='The paper uses transaction prices; First Rate supplies OHLCV bars. The close is a sampled transaction-price proxy rather than a complete trade stream or NBBO measure. One-minute bar-close selection, paired-vector ddof=1, asset-day estimation, minimum pair count, exact gaps and session conventions are project choices. Zero-volume rows remain flagged and can contribute valid prices; no zero-volume bars or missing minutes are synthesized.\n\n'
    report+='Retain bars_observed, one_minute_returns, roll_pairs, max_gap_minutes, gaps_gt_one_minute, all existing quality counts and the new invalid-price/return counts. Gap summaries use all retained observations inside the day, including flagged bars; duplicate gaps of zero and overnight gaps are not counted as gaps>1 minute. Sparse or failed observed days are never dropped; empty calendar dates remain in audits only.\n\n'
    report+='## Explicit failure policy\n\nThe canonical detailed failure_reason follows benchmark_failure_policy.csv. With insufficient pairs, precedence is insufficient_minute_bars, invalid_price, invalid_return, source_quality_condition, insufficient_consecutive_returns, then insufficient_covariance_pairs. With enough pairs, non_finite_autocovariance or non_negative_autocovariance explains an undefined result. All eight diagnostic booleans remain available and may coexist; they are not competing mutually exclusive source events. A defined day has empty failure_reason even if it contains other unusable observations.\n\n'
    report+='For compatibility, roll_defined equals benchmark_defined, and benchmark_failure_reason retains the previous coarse insufficient_roll_pairs label for all pair shortages. It is explicitly a legacy alias, not a different spread treatment. Current numerical results on ordinary eligible inputs are unchanged. Corrections add gap counts, source-cause diagnostics and masking of returns rounded to the impossible -1 boundary. Non-finite returns were already masked; they are now counted explicitly. These are mathematical safeguards, not adjustments motivated by observed failure rates.\n\n'
    report+='## Sessions and sensitivity\n\nStocks/ETFs retain 09:30 <= local time < 16:00 America/New_York. Crypto uses UTC days for pilots only. Futures use only ES/CL verified pilot sessions and provider-selected unadjusted individual contracts; no unresolved root fallback. FX remains unavailable with no substitution. No new exchange holiday or early-close filtering is introduced.\n\n'
    report+='successive_observed_bars is prepared in the YAML solely as robustness/sensitivity: later returns could span positive observed gaps, with gap durations audited, and remain confined to session-days and contracts. It is not implemented or executed here; requesting it from the primary function raises NotImplementedError. The primary never falls back to it.\n\n'
    report+='## Remaining freeze limitations\n\nMarket efficiency, stationarity and the transaction-close proxy are maintained assumptions, not proven by the formula tests. The two-pair minimum establishes mathematical computability, not statistical precision. Sparse-bar sampling, adjusted-price comparability, corporate actions and cross-source conventions still require review. No sampling/coverage exclusion is tuned from prior asset failure rates. Final futures/crypto universes and FX access remain unresolved. Methodological specification is ready for review; the YAML remains a candidate and does not constitute final design approval.\n\n'
    report+=f'{len(validations)} hand/synthetic formula cases passed. Unit tests separately cover scaling invariance, ddof against NumPy/Pandas, negative/nonnegative covariance, invalid arithmetic, exact gap breaks, no filling and equity/crypto/futures session boundaries. No provider bars, historical benchmark results, estimator values or universe-selection decisions were read or recalculated. README.md, design_decisions.md, data_manifest.csv and all raw files remain untouched.\n'
    (OUT/'benchmark_definition_review.md').write_text(report,encoding='utf-8')
    print(f'{len(validations)} synthetic formula validations passed; freeze candidate written.')


if __name__=='__main__':
    run()
