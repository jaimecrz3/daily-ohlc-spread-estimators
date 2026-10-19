"""Step22: authoring and claim reconciliation only; no estimation or statistical replay."""
from pathlib import Path
import hashlib
import json
import re

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PAPER=ROOT/'paper'
OUT=ROOT/'outputs/diagnostics/paper_draft'
CLAIMS={}
PRIMARY='outputs/results/primary/'
ROBUST='outputs/results/robustness/'
ML='outputs/results/error_model/'
TABLES='outputs/tables/'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def value(file,filters,column,format='.2f',scale=1,absolute=False):
    frame=pd.read_csv(ROOT/file,float_precision='round_trip')
    mask=pd.Series(True,index=frame.index)
    for key,expected in filters.items():mask &= frame[key].eq(expected)
    rows=frame.loc[mask]
    assert len(rows)==1,(file,filters)
    raw=rows[column].iloc[0]
    if hasattr(raw,'item'):raw=raw.item()
    number=abs(raw) if absolute else raw
    display=f'{number*scale:{format}}' if isinstance(raw,(float,int)) else str(raw)
    unit='date' if column in ['primary_start','primary_end'] else 'percent' if scale==100 or 'pct' in column else 'bps' if 'bps' in column else 'R2' if column=='R2' else 'count'
    locator=dict(kind='csv',row_zero_based=int(rows.index[0]),filters=filters,metric=column,scale=scale,absolute=absolute,format=format)
    return dict(source_file=file,source_metric_or_row=json.dumps(locator,sort_keys=True),numeric_value=number*scale if isinstance(raw,(float,int)) else raw,unit=unit,display=display)


def evidence(file,anchor):
    assert anchor in (ROOT/file).read_text(encoding='utf-8'),(file,anchor)
    return dict(source_file=file,source_metric_or_row=json.dumps(dict(kind='text',anchor=anchor)),numeric_value='',unit='qualitative / methodological',display='')


def register(name,text,*refs):
    assert name not in CLAIMS
    rendered=text.format(*(r['display'] for r in refs))
    CLAIMS[name]=dict(text=rendered,refs=list(refs))


def accuracy(cls,method,metric,tier='ALL'):
    scope='overall' if cls=='ALL' else 'asset_class' if tier=='ALL' else 'asset_class_x_tier'
    return value(PRIMARY+'primary_accuracy_results.csv',dict(reporting_scope=scope,asset_class=cls,liquidity_tier=tier,estimator=method),metric)


def prepare_claims():
    CLAIMS.clear()
    n=value(PRIMARY+'primary_accuracy_results.csv',dict(reporting_scope='overall',estimator='EDGE'),'N_asset_days',',.0f')
    register('abstract_n','The common-defined sample comprises {0} asset-days.',n)
    register('abstract_edge','EDGE records the lowest overall mean absolute error and root mean squared error, at {0} and {1} basis points, respectively.',accuracy('ALL','EDGE','mae_bps'),accuracy('ALL','EDGE','rmse_bps'))
    ranking=evidence(PRIMARY+'hypothesis_evidence.csv','EDGE < AR < CS')
    register('abstract_boundary','Universal EDGE dominance is not supported: ETFs favor CS on both accuracy metrics, while stocks favor EDGE on mean absolute error and CS on root mean squared error.',evidence('README.md','ETFs favor CS on both metrics; stocks are mixed'))
    register('abstract_robust','Overall EDGE leadership survives the applicable prespecified robustness checks, although stock and thin-ETF conclusions are less stable.',evidence('README.md','overall EDGE leadership survives applicable R25/R50'))
    register('intro_ranking','Estimator ranking is not stable across asset classes, contradicting the original ranking-stability expectation.',ranking)
    register('universe','Each completed class contains {0} selected assets or futures roots, with three assigned to each liquidity tier.',value(TABLES+'appendix_data_lineage_attrition.csv',dict(asset_class='stocks',stage='raw_selected_universe'),'N',',.0f'),evidence('README.md','| stocks | LOW | IMDX, AIRG, CCBG |'))
    register('calibration','Liquidity tiers are descriptive classifications calibrated on 2024 turnover, rather than trading signals or rankings based on estimator outcomes.',evidence('design_decisions.md','2024 turnover medians within class'))
    for cls,label in [('stocks','Stock'),('etfs','ETF'),('crypto','Crypto')]:
        register('calendar_'+cls,label+' design support runs from {0} through {1}.',value(TABLES+'table1_estimator_definitions_and_coverage.csv',dict(asset_class=cls,estimator='ROLL'),'primary_start'),value(TABLES+'table1_estimator_definitions_and_coverage.csv',dict(asset_class=cls,estimator='ROLL'),'primary_end'))
    register('calendar_futures','Futures primary support is confined to 2024, from {0} through {1}.',value(TABLES+'table1_estimator_definitions_and_coverage.csv',dict(asset_class='futures',estimator='ROLL'),'primary_start'),value(TABLES+'table1_estimator_definitions_and_coverage.csv',dict(asset_class='futures',estimator='ROLL'),'primary_end'))
    register('sample_total','The frozen design contains {0} eligible asset-days, of which {1} are common-defined for the primary comparison.',value(TABLES+'appendix_data_lineage_attrition.csv',dict(asset_class='ALL',stage='design_eligible'),'N',',.0f'),n)
    register('sample_class','The common sample contains {0} stock, {1} ETF, {2} futures and {3} crypto asset-days.',*(value(TABLES+'appendix_data_lineage_attrition.csv',dict(asset_class=c,stage='common_defined'),'N',',.0f') for c in ['stocks','etfs','futures','crypto']))
    def fail(cls):return value(PRIMARY+'failure_rates.csv',dict(reporting_scope='overall' if cls=='ALL' else 'asset_class',asset_class=cls,estimator='ROLL'),'failure_rate',scale=100)
    register('roll_failure','Roll is undefined on {0}% of all design-eligible days and {1}% of ETF design days.',fail('ALL'),fail('etfs'))
    register('after_roll','Only {0} further asset-days are lost between the Roll-defined set and the all-method common sample.',value(TABLES+'appendix_data_lineage_attrition.csv',dict(asset_class='ALL',stage='additional_loss_after_Roll_defined'),'N',',.0f'))
    register('sessions','Equity benchmark bars are retained only from 09:30 inclusive to 16:00 exclusive in America/New_York; crypto uses UTC calendar days, and the selected futures use verified previous-evening 18:00 to trade-date 17:00 sessions.',evidence('README.md','09:30≤America/New_York time<16:00'),evidence('README.md','previous 18:00 through trade-date 17:00'))
    register('roll_math','The mathematical minimum is two valid covariance pairs; for negative covariance the relative spread equals twice the square root of its absolute value.',evidence('outputs/diagnostics/benchmark_freeze/benchmark_final_spec.yaml','minimum_covariance_pairs: 2'))
    for m in ['CS','AR','EDGE']:
        register('overall_'+m,m+' has overall bias, MAE and RMSE of {0}, {1} and {2} bps, respectively.',*(accuracy('ALL',m,metric) for metric in ['bias_bps','mae_bps','rmse_bps']))
    register('edge_bias_ci','Its nominal HAC confidence interval for mean signed bias extends from {0} to {1} bps and excludes zero.',*(value(PRIMARY+'primary_bias_hac_results.csv',dict(reporting_scope='overall',estimator='EDGE'),metric) for metric in ['ci95_low_bps','ci95_high_bps']))
    for cls,label in [('stocks','stocks'),('etfs','ETFs'),('futures','futures'),('crypto','crypto')]:
        register('class_'+cls,'For '+label+', CS records MAE/RMSE of {0}/{1} bps, AR {2}/{3} bps, and EDGE {4}/{5} bps.',*(accuracy(cls,m,metric) for m in ['CS','AR','EDGE'] for metric in ['mae_bps','rmse_bps']))
    register('low_bias','CS LOW-tier bias is positive in every completed class: {0} bps for stocks, {1} for ETFs, {2} for futures and {3} for crypto.',*(accuracy(c,'CS','bias_bps','LOW') for c in ['stocks','etfs','futures','crypto']))
    register('negative_rates','Overall raw-negative rates are {0}% for CS, {1}% for AR and {2}% for EDGE.',*(value(PRIMARY+'raw_negative_rates.csv',dict(reporting_scope='overall',estimator=m),'negative_rate',scale=100) for m in ['CS','AR','EDGE']))
    register('negative_boundary','EDGE has the lowest raw-negative rate overall, narrowly below CS, but CS has the lower rate in futures and crypto.',evidence('README.md','EDGE has the lowest overall raw-negative rate, but CS is lower in futures and crypto.'))
    register('quality_n','The R25 and R50 diagnostics retain {0} and {1} common asset-days, respectively.',*(value(ROBUST+'roll_quality_sensitivity.csv',dict(reporting_scope='overall',variant=v,estimator='EDGE'),'N_asset_days',',.0f') for v in ['Roll R25','Roll R50']))
    register('thin_etf','The LOW ETF cell contracts to {0} observations under R25 and {1} under R50, making its filtered comparison tiny or unavailable.',*(value(ROBUST+'roll_quality_sensitivity.csv',dict(reporting_scope='asset_class_x_tier',asset_class='etfs',liquidity_tier='LOW',variant=v,estimator='EDGE'),'N_asset_days',',.0f') for v in ['Roll R25','Roll R50']))
    register('quality_leaders','Overall EDGE leadership and the class-level leader patterns remain unchanged under both coverage filters.',evidence('outputs/diagnostics/robustness/step19_robustness_review.md','| Roll R50 | stocks | 4125 | EDGE | CS | False |'))
    register('equal_leaders','Equal-asset weighting leaves the overall and class-level MAE and RMSE leaders unchanged.',evidence('outputs/diagnostics/robustness/step19_robustness_review.md','| Equal asset weighting | stocks | 9707 | EDGE | CS | False |'))
    register('unadjusted_leaders','Matched adjusted-versus-unadjusted Bloomberg comparisons preserve the stock and ETF class-level leader patterns.',evidence('outputs/diagnostics/robustness/step19_robustness_review.md','| Bloomberg unadjusted | stocks | 9705 | EDGE | CS | False |'))
    register('abs_leaders','Under the EDGE absolute-root convention, EDGE remains the overall leader, but CS leads both MAE and RMSE for stocks.',evidence('outputs/diagnostics/robustness/step19_robustness_review.md','| EDGE abs-root | stocks | 9707 | CS | CS | True |'))
    register('loo','The leave-one-asset-out MAE leader never changes within a class, whereas stock RMSE leadership changes from CS to EDGE when SNDL is omitted.',evidence('README.md','Stock RMSE is sensitive to leaving out SNDL'))
    register('influence','Removing the largest absolute-error stock AR observation in the saved influence diagnostic reduces that method’s stock RMSE by {0}%.',value(ROBUST+'extreme_observation_influence.csv',dict(asset_class='stocks',estimator='AR'),'rmse_pct_change',absolute=True))
    embargo=json.loads((ROOT/'outputs/diagnostics/error_model/output_validation.json').read_text())['embargo_dates']
    embargo_ref=dict(source_file='outputs/diagnostics/error_model/output_validation.json',source_metric_or_row=json.dumps(dict(kind='json',key='embargo_dates')),numeric_value=embargo,unit='dates',display=str(embargo))
    register('ml_n','The diagnostic uses the same {0} common-defined observations, with five chronological test folds and an embargo of one percent, equivalent to {1} subsequent target dates where available.',n,embargo_ref,evidence('outputs/diagnostics/error_model/step20_cross_fitted_error_model_review.md','The 1% embargo is ceil(0.01*2057)=21'))
    register('ml_r2','For absolute-error targets, pooled cross-fitted R² is {0} for CS, {1} for AR and {2} for EDGE.',*(value(ML+'cross_fitted_performance.csv',dict(estimator=m,target_type='absolute_error_bps'),'R2','.3f') for m in ['CS','AR','EDGE']))
    register('features','Daily high-low range dominates CS absolute-error importance; range and open-close movement dominate AR, while asset class and range are especially important for EDGE.',evidence('outputs/diagnostics/error_model/step20_cross_fitted_error_model_review.md','| CS | absolute_error_bps | hl_range_bps | 41.1052'),evidence('outputs/diagnostics/error_model/step20_cross_fitted_error_model_review.md','| EDGE | absolute_error_bps | asset_class | 13.8629'))
    register('placebo','The lagged placebo preserves substantial predictability: pooled absolute-error R² is {0} for CS, {1} for AR and {2} for EDGE.',*(value(ML+'date_shift_placebo.csv',dict(estimator=m,target_type='absolute_error_bps'),'R2','.3f') for m in ['CS','AR','EDGE']))
    register('placebo_boundary','By pooled R² and RMSE, AR and EDGE weaken under lagged alignment, whereas CS does not.',evidence('outputs/diagnostics/error_model/step20_cross_fitted_error_model_review.md','| CS | absolute_error_bps | 24377 | 79.6007 | 133.393 | 0.3102'))
    register('tier_limit','The use of 2024 liquidity calibration introduces look-ahead classification for earlier observations and makes the futures comparison conditional on its calibration year.',evidence('README.md','Liquidity tiers use 2024 information'))
    register('limits_rates','Roll undefinedness affects {0}% of design days overall and {1}% for ETFs.',fail('ALL'),fail('etfs'))
    register('final_conclusion','EDGE is the strongest overall estimator against the frozen one-minute Roll benchmark within the sampled universe, but no estimator dominates universally.',evidence('README.md','EDGE has the lowest overall MAE and RMSE in this frozen sample.'))


TEXT='''# Which Daily OHLC Spread Estimator Tracks Realized Intraday Cost? A CS / AR / EDGE Horse-Race

## Abstract

Daily OHLC prices permit spread estimation when detailed trade and quote records are unavailable. This paper compares daily spread estimators across liquidity-stratified stocks, ETFs, futures and crypto against a common intraday proxy. Corwin–Schultz (CS), Abdi–Ranaldo (AR) and EDGE are compared with a one-minute, simple-return Roll benchmark under frozen source, session, daily-mapping and negative-value conventions. [[abstract_n]] [[abstract_edge]] [[abstract_boundary]] The hypothesis of downward CS bias in low-liquidity cells is contradicted by positive observed bias, and estimator rankings differ across asset classes. [[abstract_robust]] Secondary cross-fitted models identify predictable error variation associated with daily price ranges and asset class, without constituting a new spread estimator or a trading forecast. The principal qualification is substantial benchmark undefinedness: accuracy is measured conditional on all methods being defined, rather than on the entire intended universe of trading days. Consequently, the evidence supports asset-class and error-criterion-specific method choice, not universal superiority or inference about true execution costs.

## 1. Introduction

Transaction costs affect portfolio turnover, implementation capacity and the interpretation of apparent return predictability. Yet the information needed to measure effective spreads directly is less readily available than daily price summaries. A daily estimator is attractive because it permits broad coverage without requiring a complete trade-and-quote history. Its practical value nevertheless depends on whether the information discarded by daily aggregation matters differently across market structures and trading activity. A convenient estimator need not be a reliable substitute for the cost concept that motivates its use.

This paper asks: across asset classes and liquidity tiers, which daily-OHLC spread estimator best matches an intraday benchmark, and where do the methods break down? The comparison concerns Corwin–Schultz, Abdi–Ranaldo and EDGE. The reference is a one-minute Roll-type measure constructed from transaction-price bar closes. The exercise therefore evaluates agreement with a common proxy, rather than identifying the estimator closest to an observed fundamental price or a quote-based ground truth.

The original expectations were recorded before provider performance was calculated. EDGE was expected to dominate accuracy and negative-estimate rates. CS was expected to exhibit downward bias in thin or non-continuous markets. Estimator rankings were expected to be broadly stable across asset classes, while error levels were expected to diverge most in crypto and low-liquidity equities. These directional expectations remain the benchmark for interpretation even where the results contradict them. The selected equity tiers represent liquidity, not a separately validated small-cap classification.

The contribution is an explicitly comparable asset-day horse race under a frozen benchmark and transparent daily mappings. Accuracy uses identical observations for competing methods, while failure and raw-negative rates retain their own appropriate denominators. The completed classes span equities, ETFs, futures and crypto; official FX access remains blocked. Within-class liquidity stratification permits conditional comparisons without treating turnover in unlike units as a universal cross-market scale. Prespecified sensitivities examine coverage, weighting, input adjustment and negative correction, while a separate cross-fitted exercise describes error predictability.

The paper distinguishes confirmatory primary analysis from prespecified robustness and secondary diagnostics. The primary comparison answers the frozen hypotheses; the sensitivities assess their boundaries without replacing the original sample. Predictive error models are interpretive diagnostics rather than a mechanism for correcting spreads or revising the preferred specification. This separation prevents a favorable sensitivity or model fit from being substituted retrospectively for the intended comparison.

The evidence supports overall EDGE leadership, particularly in futures and crypto, but does not support universal dominance. ETFs favor CS, and stock conclusions depend on the loss function. [[intro_ranking]] Positive CS bias in LOW-tier cells contradicts the directional downward-bias expectation. Some negative-rate and error-level expectations receive only partial support. The relevant economic conclusion is thus conditional method choice, subject to benchmark selection and the sampled markets.

## 2. Data and Sample Construction

The original research horizon spans the project’s intended historical study period, but available common support differs by class. The final universe covers stocks, ETFs, futures and crypto. FX remains in scope but unavailable because access to the official RiskLab archive was blocked; no substitute FX data were used. This is a source limitation, not an intentional exclusion based on market behavior or estimator results.

Stock and ETF estimator inputs are Bloomberg adjusted daily OHLC. The saved acquisition specifies capital-change and normal cash-dividend adjustment, while abnormal-dividend adjustment remains unspecified. Unadjusted Bloomberg data serve only as robustness inputs. Their benchmark uses official First Rate one-minute files accessed through RiskLab. Local equity daily aggregates are validation material; equivalence with Bloomberg sessions and adjustment conventions is not assumed. Bloomberg daily bid and ask fields are not the intraday benchmark.

Futures daily OHLC and the benchmark originate from individual, unadjusted First Rate contracts selected using the provider’s contract-date mapping. A single selected contract supplies the entire overnight trade-date session. Continuous back-adjusted prices and silent fallback contracts are prohibited, and required estimator context cannot cross a selected-contract boundary. Crypto daily OHLC and Roll similarly derive from validated First Rate minute observations under a common provider quote basis. This shared input source creates dependence between daily estimates and benchmark errors that is absent from a fully independent validation design.

[[universe]] [[calibration]] Ranking is independent within each class, and deterministic within-tier rank targets determine the sample rather than familiar security names. Security-type corrections were made before the analytic comparison. The complete universe appears in the appendix notes; the eligibility and identity audits remain part of the frozen lineage. REIT common shares and ADR/ADS lines are permitted, while unresolved IMDX historical continuity is retained as a limitation rather than repaired by discretionary ticker stitching.

[[calendar_stocks]] [[calendar_etfs]] [[calendar_futures]] [[calendar_crypto]] These are frozen design boundaries, not a claim that every estimator is defined on every endpoint. Within each class, exact common source dates establish temporal comparability across liquidity tiers before outcome-definedness is applied. Extra asset-specific historical support is supplementary. The pooled comparison is neither a single balanced historical panel nor a design that identifies a pure asset-class effect holding calendar conditions fixed.

[[sessions]] Maintenance periods, missing minutes and absent days are not filled. Sparse bars and zero-volume observations are retained with diagnostics. Daily context follows the frozen scheduled-source grid; a missing required period is not replaced by the next available observation. This distinction preserves the intended estimator horizon even when the scored common sample has gaps.

[[sample_total]] [[sample_class]] [[roll_failure]] [[after_roll]] Method-defined sets overlap, so their individual failure counts cannot be added as sequential losses. The [Appendix Table](../outputs/tables/appendix_data_lineage_attrition.md) traces these parallel sets, and [Figure 4](../outputs/figures/figure4_benchmark_coverage.png) shows benchmark availability and coverage sensitivities. Roll is the principal attrition bottleneck, especially for ETFs. The accuracy estimand is consequently conditional on joint computability, not representative performance over all intended asset-days.

## 3. Methodology

The unit of observation is the asset-day. [Table 1](../outputs/tables/table1_estimator_definitions_and_coverage.md) summarizes required inputs, daily mappings, output conventions and usable counts. The implementation separates mathematical formulae from project-specific temporal assignment. This matters because applying a spread formula over a short surrounding window is not equivalent to observing a target-day effective spread directly.

For Roll, simple close-to-close returns are computed only when successive retained timestamps are exactly one minute apart. A lag-one covariance pair requires two consecutive valid returns and therefore a physical chain of three equally spaced closes within the same session. The sample covariance uses separately centered paired-return vectors and the ordinary sample denominator. [[roll_math]] Nonnegative covariance and insufficient pairs leave the benchmark undefined, never converted to zero. No gaps are bridged and no minutes are synthesized. The minimum establishes mathematical computability rather than statistical reliability; coverage diagnostics remain available without imposing an additional primary reliability cutoff.

The percentage-return adaptation follows the interpretation documented for Roll’s implicit-spread logic. It remains a sampled transaction-close proxy rather than a quote-based effective spread or NBBO execution-cost measure. Aggregation, non-spread price variation and finite-sample covariance behavior can therefore contribute to disagreement. A low error against Roll establishes proximity to this benchmark under the chosen conventions, not accuracy against an independently observed economic cost.

CS uses high-low information to separate components associated with price variation and spread. The implementation applies the official additive overnight adjustment and computes the nonlinear spread from adjacent-session range moments. The project assigns a daily value by averaging the corrected intervals immediately before and after the target session. Both intervals are required, and each finite raw interval is floored separately before averaging. This is an explicit project mapping supported by overlapping-interval applications, not an additional closed-form estimator attributed to the authors.

AR combines the target close with the midpoint of daily high and low log prices on the target and next scheduled session. Its two-day moment is assigned to the target date, with the published zero-floor correction applied before taking the square root. A following close is unnecessary for this particular moment. The common primary preprocessing does not import the author empirical implementation’s carry-forward or other sample repairs: missing formula-required inputs remain missing rather than becoming synthetic observations.

EDGE combines information from all daily OHLC log-price components through its efficient moment combination. The primary project mapping uses the centered three-session sample surrounding the target date and the published paper’s zero-floor convention. This estimates a local root-mean-square spread, not an instantaneous target-day spread. The short centered window is a project choice, not an author recommendation for an optimal daily horizon. The official package’s absolute-root convention is a named sensitivity only. These mappings use future-session context for ex-post measurement and are not executable contemporaneous trading signals.

The common-defined accuracy sample is the conjunction of design eligibility and defined Roll, CS, AR and EDGE outputs. Competing methods are scored on identical asset-days so that differences in missingness cannot mechanically create different accuracy samples. A finite negative raw estimate remains mathematically computable even when its corrected primary spread equals zero. Failure rates instead use all design-eligible days; raw-negative rates use only the method’s finite raw-computable design days. Neither denominator is replaced by the common accuracy sample.

Signed error is estimator spread minus Roll spread. Bias is its mean, MAE the mean absolute error, and RMSE the square root of mean squared error. Relative outputs are converted to basis points for presentation. Positive bias means an estimator exceeds Roll on average. Every contributing asset-day has equal primary weight; no trimming, winsorization or magnitude-based exclusion is introduced. MAE measures typical absolute discrepancy, whereas RMSE places greater weight on large errors, allowing the criteria to yield different rankings.

Inference is restricted to signed bias. The frozen HAC procedure forms chronological date-level mean errors and estimates a count-weighted intercept, preserving the pooled asset-day point estimate. A Bartlett Newey–West covariance estimator uses a deterministic lag rule based only on contributing-date count, without a small-sample correction; normal-reference intervals and two-sided probabilities concern mean bias. No significance test was specified for MAE or RMSE differences. All accuracy rankings are therefore descriptive, and nominal bias inference does not imply a multiplicity-adjusted or comprehensive panel-dependence analysis.

## 4. Primary Results

The confirmatory primary horse race is reported in [Table 2](../outputs/tables/table2_primary_horse_race.md). [[overall_CS]] [[overall_AR]] [[overall_EDGE]] EDGE is the descriptive overall accuracy leader, but its mean signed error remains positive under this benchmark. [[edge_bias_ci]] It should not be characterized as unbiased. The covariance convention supports inference about this signed mean, not a statistical claim that EDGE’s MAE or RMSE is significantly smaller than another method’s.

[Figure 1](../outputs/figures/figure1_estimator_vs_roll.png) presents estimator-versus-Roll scatter plots, while [Figure 2](../outputs/figures/figure2_error_distribution.png) displays signed-error distributions. Both retain the full finite range using explicitly labeled transformed axes. They complement the aggregate metrics without hiding extreme observations or implying that visual distance from a reference line constitutes a formal test. Benchmark-relative error dispersion, not only mean bias, is central to the comparison.

[[class_stocks]] Stock evidence is mixed: EDGE minimizes typical absolute discrepancy, whereas CS has the smaller squared-error criterion. This distinction is relevant when the economic use places different penalties on routine deviations and extreme errors. The result does not license a universal stock-estimator recommendation, and the influence diagnostics below further qualify its stability.

[[class_etfs]] CS leads both ETF criteria, providing a direct boundary to the expectation of universal EDGE dominance. That finding is conditional on particularly limited ETF Roll availability. It describes the retained ETF sample rather than demonstrating that CS is more accurate on the many ETF days for which the comparison cannot be formed.

[[class_futures]] [[class_crypto]] EDGE’s benchmark-relative advantage is large in both classes on each loss criterion. Nevertheless, the futures evidence is restricted to its common calibration-year panel, and both classes share minute-source information between benchmark and daily OHLC. These design features preclude attributing the observed ranking solely to superior recovery of independent execution costs.

The class-by-tier results in [Figure 3](../outputs/figures/figure3_relative_performance.png) reinforce heterogeneity rather than a universal liquidity ordering. ETF results favor CS, and futures and crypto favor EDGE across their retained tier cells; stock boundaries depend on metric and tier. Differences between LOW and HIGH cells combine selected securities, fixed tier labels and benchmark availability. They do not identify the causal effect of changing a security’s liquidity.

[[low_bias]] This directly contradicts the hypothesized downward CS bias in thin or non-continuous settings under the frozen benchmark and mapping. It does not refute every theoretical prediction about CS under other sampling conditions or against another cost measure. The present hypothesis concerns the observed signs in these selected LOW-liquidity cells, and those adverse signs are retained rather than redefined after inspection.

[[negative_rates]] [[negative_boundary]] The negative-rate hypothesis therefore receives partial rather than universal support. [Table 3](../outputs/tables/table3_failure_negative_decomposition.md) keeps failure and raw-negative denominators explicit alongside class rankings and influential-error diagnostics. Negative raw moments are not failures, and zero-floor corrections do not erase their diagnostic frequency. Cross-class rank changes also reject the original stability expectation; heterogeneous error levels alone do not rescue a claim of stable ordering.

## 5. Robustness and Falsification

The prespecified robustness analysis is summarized in [Table 4](../outputs/tables/table4_robustness_falsification.md). These checks investigate the boundaries of the primary result; none becomes a preferred replacement sample. Their interpretation distinguishes benchmark precision, weighting, daily-input convention and influential observations rather than treating every alternative as an interchangeable replication.

The Roll coverage sensitivities retain observations whose valid pair coverage reaches a quarter or half of the regular-session clock opportunities. Those denominators represent the frozen regular envelope, not an imputed minute sequence or an independently certified early-close schedule. [[quality_n]] [[quality_leaders]] [[thin_etf]] Such depletion cautions against strong conclusions from filtered tier cells. The coverage thresholds were prescribed, not chosen to improve estimator ranking, and are not the primary inclusion rule.

[[equal_leaders]] This reduces concern that unequal numbers of available asset-days across securities alone determine the principal ordering. It does not balance calendars across classes or resolve outcome-dependent definedness. Equal-asset weighting addresses a particular weighting sensitivity rather than making the sampled universe representative of all securities in a liquidity regime.

[[unadjusted_leaders]] This comparison uses matched target dates and unchanged Roll values, separating daily-source convention from sample composition. Verified split boundaries can interrupt crossing unadjusted windows, while heuristic adjusted-versus-unadjusted discontinuities remain diagnostics rather than verified corporate actions. The stability of class leaders does not establish perfect adjustment equivalence, especially around individual corporate events or where acquisition settings were incompletely recorded.

[[abs_leaders]] Stock conclusions are therefore sensitive to how finite negative EDGE moments are translated into nonnegative spreads. The primary convention remains the published zero floor; the absolute-root exercise cannot justify switching conventions retrospectively. The overall accuracy finding survives this change, but the local stock boundary is economically relevant for users interpreting daily measures.

[[loo]] [[influence]] These are saved sensitivity results, not exclusions applied to the primary paper sample. The single-extreme exercise may remove a different observation for each method and consequently is an influence decomposition rather than a new common-sample horse race. No observations are removed from primary results. Taken together, the applicable checks preserve overall EDGE leadership while identifying fragile stock and sparse-tier conclusions; they do not convert descriptive robustness into a significance test.

## 6. Cross-Fitted Error Diagnostics

This section is secondary diagnostic and robustness analysis, distinct from primary estimator performance. A fixed HistGradientBoostingRegressor predicts signed and absolute benchmark-relative errors, with no hyperparameter search or outcome-driven feature selection. [[ml_n]] Training rows whose actual estimator-information intervals overlap test information are purged. Numerical preprocessing and category encoding use training data only, and permutation importance is evaluated on held-out raw feature columns.

[[ml_r2]] Estimator errors contain some predictable structure, but these fits neither correct the primary estimates nor produce a new spread estimator. Pooled predictability can coexist with negative class-specific predictive fit, so aggregate performance should not be read as uniform diagnostic success. Block cross-fitting may train on later non-overlapping periods; it measures ex-post association rather than forward-only forecast performance or trading usefulness.

[[features]] [Figure 5](../outputs/figures/figure5_error_predictors.png) reports test-set permutation importance and fold variation, not causal coefficients or confidence intervals. Liquidity-tier importance is small and unstable conditional on other included features. This does not establish that liquidity is economically irrelevant: correlated asset, class, tier and price-condition variables can substitute for one another, while different price and volume units complicate economic interpretation.

Range and open-close conditions also overlap conceptually with the estimators’ own inputs. Their predictive importance is partly mechanical and may describe the benchmark proxy’s behavior as well as estimator error. Permuting a feature can create combinations outside observed support; importance is conditional on the fitted model, sampled assets and calendar. These qualifications are especially important where daily OHLC and Roll share their underlying minute source.

[[placebo]] [[placebo_boundary]] Temporal persistence therefore limits a strong interpretation of exact same-day feature alignment. This falsification retains the immediately preceding scheduled feature period rather than compressing available observations or importing future predictors. Neither the placebo nor the importance results support causality, a new trading strategy, or a revised primary estimator ranking.

## 7. Limitations

The benchmark is not ground truth. Roll estimates an implicit spread from sampled transaction-price closes and cannot recover NBBO costs or effective execution spreads directly. [[limits_rates]] Joint definedness may select particular price dynamics and trading conditions, making common-sample accuracy economically selective. Mathematical computability with few pairs does not certify precision, and the quality sensitivities cannot recover information on undefined days.

Temporal and sampling comparability are also limited. Class calendars differ, the futures primary panel covers only its verified common year, and the selected assets are not a market-wide probability sample. [[tier_limit]] Historical supplementary panels cannot be pooled with changing composition and interpreted solely as liquidity effects. In particular, liquidity-stratified equity results do not establish a separate small-cap result without a validated capitalization classification.

Source dependence and acquisition conventions constrain interpretation. Futures and crypto use the same minute provider for OHLC and Roll, so their agreement is not an independent-source cost validation. Crypto’s formal quote currency remains UNKNOWN despite a verified common quote basis; dimensionless and basis-point outputs do not establish USD denomination. Bloomberg’s abnormal-dividend adjustment setting is UNKNOWN, and equivalence between daily acquisition sessions and local intraday conventions is uncertified. These are documented limitations rather than defaults inferred from the results.

IMDX economic-identity continuity is not independently certified, and no discretionary OCX stitching resolves that uncertainty. FX remains unavailable because of official source-access restrictions, with no substitute introduced. These issues narrow the completed evidence without changing the frozen universe after performance was observed. Earlier source-defined history is not retroactively certified by its inclusion in a validated analytic pipeline.

Finally, descriptive ranking should not be mistaken for statistical superiority. HAC inference is confined to signed bias and does not exhaust all panel dependence or multiplicity concerns. Centered estimator context is appropriate for ex-post measurement but is unavailable as a contemporaneous signal. Cross-fitted predictions and permutation importance are associative diagnostics, conditional on shared inputs and sampled support. Their predictability is neither causal evidence nor proof of economic value. The paper preserves these boundaries rather than using them to recast adverse findings as confirmed hypotheses.

## 8. Conclusion

[[final_conclusion]] The strongest evidence for EDGE occurs in futures and crypto; CS is strongest in ETFs, while stocks favor EDGE under MAE and CS under RMSE. Positive LOW-tier CS bias rejects the directional downward-bias hypothesis, and changing class rankings reject the original stability expectation. The raw-negative-rate expectation receives only partial support because EDGE’s overall lead is narrow and has class exceptions.

The overall EDGE advantage survives the major applicable prespecified sensitivities, but stock and thin-tier results are less stable. Error diagnostics reveal predictable association with price conditions and asset class without creating a new cost measure. All conclusions remain conditional on Roll availability, frozen mappings, selected securities and unequal class calendars. Daily OHLC spread estimators are not interchangeable across market structures: method choice should depend on asset class and the intended error criterion, with explicit recognition of what the benchmark can and cannot measure.

## References

Abdi, F., and A. Ranaldo. 2017. “A Simple Estimation of Bid-Ask Spreads from Daily Close, High, and Low Prices.” *Review of Financial Studies* 30(12), 4437–4480. Bibliographic metadata reproduced from the stored EDGE paper’s references; the project’s [AR method review](../outputs/diagnostics/daily_input_freeze/daily_input_convention_review.md) identifies the published article.

Ardia, D., E. Guidotti, and T. A. Kroencke. 2024. “Efficient Estimation of Bid–Ask Spreads from Open, High, Low, and Close Prices.” *Journal of Financial Economics* 161, article 103916. DOI: 10.1016/j.jfineco.2024.103916. Metadata and published negative-correction convention are documented in the [stored source and method review](../outputs/diagnostics/estimator_freeze/step15_estimator_freeze_review.md).

Corwin, S. A., and P. Schultz. 2012. “A Simple Way to Estimate Bid-Ask Spreads from Daily High and Low Prices.” *Journal of Finance* 67(2), 719–760. Metadata is documented in the stored author program description and EDGE paper’s references; see the [frozen method review](../outputs/diagnostics/estimator_freeze/step15_estimator_freeze_review.md).

Roll, R. 1984. “A Simple Implicit Measure of the Effective Bid-Ask Spread in an Efficient Market.” *Journal of Finance* 39(4), 1127–1139. DOI: 10.1111/j.1540-6261.1984.tb03897.x. The [benchmark specification](../outputs/diagnostics/benchmark_freeze/benchmark_final_spec.yaml) records the percentage-return interpretation and source locations.

Bloomberg. Student-acquired daily OHLCV, daily quote and reference workbooks, acquired under the saved adjustment settings. Source log and field-validation notes are preserved with the immutable licensed acquisition; the [data manifest](../manifests/data_manifest.csv) records their roles and limitations.

First Rate Data / RiskLab. Official shared one-minute archives for stocks, ETFs, individual futures contracts and crypto. Provider metadata, session evidence and source fingerprints are retained in the frozen project artifacts. Existing shared raw files are referenced rather than duplicated; official FX access remained blocked.

## Appendix references / notes

The selected universe is reproduced below from the frozen universe metadata, without a new selection exercise.

| Class | LOW | MEDIUM | HIGH |
| --- | --- | --- | --- |
| Stocks | IMDX, AIRG, CCBG | ANGO, SNDL, FCPT | FDS, XPO, BIDU |
| ETFs | SDCI, AAA, JSML | PGJ, PJAN, FSMD | SPBO, SCHM, MCHI |
| Futures | HG, AD, B6 | J1, GC, E6 | NQ, ZF, ES |
| Crypto | ICX, NEO, DASH | ZEC, ALGO, MKR | NEAR, LINK, DOGE |

All exhibit numbers refer to existing frozen outputs, not newly estimated paper tables. Tables are available as linked Markdown and companion CSV; each figure has a PNG and PDF version. Definitions and coverage are in [Table 1](../outputs/tables/table1_estimator_definitions_and_coverage.md); primary results in [Table 2](../outputs/tables/table2_primary_horse_race.md); failures, raw-negative rates and influence in [Table 3](../outputs/tables/table3_failure_negative_decomposition.md); sensitivities in [Table 4](../outputs/tables/table4_robustness_falsification.md); and lineage in the [Appendix Table](../outputs/tables/appendix_data_lineage_attrition.md).

The analysis hierarchy is fixed: Step 18 is primary, Step 19 prespecified robustness and Step 20 secondary diagnostics. [The master ledger](../outputs/results/final_results_master.csv) reconciles final aggregate values to their source rows; [the paper claims audit](paper_claims_audit.csv) records sentence-level evidence for this draft. Methodological choices are recorded in [design_decisions.md](../design_decisions.md) and the frozen benchmark, daily-input, estimator and statistical specifications.

The [reproduction guide](../outputs/reproducibility/final_reproduction_guide.md) distinguishes frozen-derived verification from licensed full-source construction. No new statistical analysis was performed for this draft, and no frozen result, raw workbook or hypothesis was modified. Granular provider observations remain private. The existing publication gate for legacy raw excerpts in Git history remains unresolved: use a clean release/export or separately authorized history cleanup before publishing that history.
'''


def render():
    prepare_claims()
    audit=[];parts=[];section='Title'
    for line in TEXT.splitlines(keepends=True):
        if line.startswith('## '):section=line[3:].strip()
        def replacement(match):
            name=match.group(1);claim=CLAIMS[name]
            for ref in claim['refs']:
                audit.append(dict(section=section,claim_short_name=name,claim_text=claim['text'],
                    **{k:ref[k] for k in ['numeric_value','unit','source_file','source_metric_or_row']},
                    reconciliation_status='PASS'))
            return claim['text']
        parts.append(re.sub(r'\[\[(\w+)\]\]',replacement,line))
    return ''.join(parts),audit


def words(text):
    text=re.sub(r'\[([^]]+)\]\([^)]*\)',r'\1',text)
    text='\n'.join(line for line in text.splitlines() if not line.startswith(('#','|')))
    return len(re.findall(r"\b[\w]+(?:[’'–−-][\w]+)*\b",text))


def run():
    PAPER.mkdir(exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    frozen=pd.read_csv(ROOT/'outputs/reproducibility/final_artifact_manifest.csv')
    lock={row.relative_path:row.sha256 for row in frozen.itertuples()}
    for name in ['outputs/reproducibility/final_artifact_manifest.csv','outputs/diagnostics/final_artifacts/run_manifest.json','outputs/diagnostics/final_artifacts/output_validation.json']:
        lock[name]=digest(ROOT/name)
    for name,expected in lock.items():assert digest(ROOT/name)==expected,name
    paper,audit=render()
    (PAPER/'final_paper_draft.md').write_text(paper,encoding='utf-8')
    pd.DataFrame(audit).to_csv(PAPER/'paper_claims_audit.csv',index=False)
    for name,expected in lock.items():assert digest(ROOT/name)==expected,name
    body=paper.split('## References')[0];abstract=paper.split('## Abstract\n')[1].split('## 1. Introduction')[0]
    report=dict(status='GENERATED_PENDING_CLAIMS_VALIDATION',word_count_excluding_references_appendix_and_headings=words(body),abstract_words=words(abstract),
        audit_rows=len(audit),quantitative_audit_rows=sum(r['numeric_value']!='' for r in audit),
        no_new_statistical_analysis=True,frozen_sha256=lock,
        source_sha256={r['source_file']:digest(ROOT/r['source_file']) for r in audit},
        code_sha256=digest(Path(__file__)))
    (OUT/'run_manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if not k.endswith('sha256')},indent=2))


if __name__=='__main__':run()
