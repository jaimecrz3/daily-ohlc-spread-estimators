# Which Daily OHLC Spread Estimator Tracks Realized Intraday Cost?

MMF 1941 Project 1, proposal A04-03. Research question: across asset classes and liquidity regimes over the 2015–2025 study horizon, where do CS, AR and EDGE track a one-minute Roll proxy and where do they break down?

Original hypothesis (retained, including falsified components): EDGE dominates accuracy and negative-estimate rate; CS is downward-biased in thin/non-continuous markets; ranking is stable across asset classes but levels diverge most in crypto and small-cap equities.

**Result hierarchy: Step18 PRIMARY; Step19 ROBUSTNESS; Step20 DIAGNOSTIC.** Step21 formats locked results only. No universal EDGE dominance or MAE/RMSE significance claim. Historical checkpoint instructions in AGENTS.md do not describe the final completed phase; later explicit user freezes govern.

Final selected universe (no estimator outcomes used in selection):

| asset_class | tier | assets |
| --- | --- | --- |
| stocks | LOW | IMDX, AIRG, CCBG |
| stocks | MEDIUM | ANGO, SNDL, FCPT |
| stocks | HIGH | FDS, XPO, BIDU |
| etfs | LOW | SDCI, AAA, JSML |
| etfs | MEDIUM | PGJ, PJAN, FSMD |
| etfs | HIGH | SPBO, SCHM, MCHI |
| futures | LOW | HG, AD, B6 |
| futures | MEDIUM | J1, GC, E6 |
| futures | HIGH | NQ, ZF, ES |
| crypto | LOW | ICX, NEO, DASH |
| crypto | MEDIUM | ZEC, ALGO, MKR |
| crypto | HIGH | NEAR, LINK, DOGE |


FX remains **IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS**, not an intentional class exclusion or zero-sized observed sample. No substitute source.

Frozen primary calendars (not a balanced all-class 2015–2025 panel):

| asset_class | start | end | exact_common_dates | potential_design_eligible_asset_days |
| --- | --- | --- | --- | --- |
| stocks | 2019-08-01 | 2025-12-31 | 1611 | 14499 |
| etfs | 2020-09-15 | 2025-12-31 | 961 | 8649 |
| futures | 2024-01-02 | 2024-12-31 | 259 | 2331 |
| crypto | 2022-02-01 | 2025-12-31 | 1417 | 12753 |


Sources: existing shared RiskLab/First Rate one-minute files only for intraday data. Stock/ETF estimator inputs are student-acquired Bloomberg adjusted daily OHLC (CapChg=T, CshAdjNormal=T, CshAdjAbnormal=UNKNOWN); unadjusted Bloomberg is robustness only. Local equity aggregates are validation, not assumed Bloomberg equivalents. Futures use exact provider-mapped unadjusted individual contracts and verified overnight sessions, never continuous adjusted prices. Crypto uses validated UTC daily/minute panels on a common provider quote basis; formal currency UNKNOWN. Shared provider raw data are referenced, not copied.

Method: asset-day is the observational unit. Stocks/ETFs use 09:30≤America/New_York time<16:00; crypto UTC days; selected futures primary dates use previous 18:00 through trade-date 17:00, excluding maintenance. No missing-minute filling, gap bridging or date compression. Roll uses simple exact-adjacent one-minute returns, physical three-close covariance pairs, lag 1, ddof=1, mathematical minimum two pairs, gamma<0 -> 2 sqrt(-gamma); otherwise undefined/NaN. CS uses overnight-adjusted intervals on (t−1,t) and (t,t+1), flooring each before averaging. AR uses the close-t two-day moment and sqrt(max(s2,0)); EDGE uses the frozen centered three-session RMS mapping and published zero floor. Finite negative raw estimates remain defined; failures stay NaN.

Primary design N=38,232; exact common-defined accuracy N=24,377. Common means design eligible AND all four outputs defined; every contributing asset-day has equal weight. Failure denominators are all design days; negative-rate denominators are method-specific finite raw-computable days. Overall Roll undefinedness is 35.93% (13,738/38,232); ETF availability is especially low.

Primary overall results (bps; saved Step18, no recalculation):

| estimator | bias_bps | hac_se_bps | ci95_low_bps | ci95_high_bps | p_value_two_sided | mae_bps | rmse_bps | N_asset_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS | 110.8 | 2.94268 | 105.033 | 116.568 | 2.93374e-310 | 121.304 | 201.272 | 24377 |
| AR | 101.675 | 3.27072 | 95.2646 | 108.086 | 3.67449e-212 | 127.712 | 257.71 | 24377 |
| EDGE | 25.9871 | 1.81557 | 22.4287 | 29.5456 | 1.80204e-46 | 53.5921 | 122.183 | 24377 |


EDGE has the lowest overall MAE and RMSE in this frozen sample. ETFs favor CS on both metrics; stocks are mixed (EDGE MAE, CS RMSE); futures and crypto favor EDGE on both. Rankings therefore differ across classes. CS LOW-tier bias is positive in all four classes, contrary to the original downward-bias expectation. EDGE has the lowest overall raw-negative rate, but CS is lower in futures and crypto. Error levels are heterogeneous rather than universally ordered. Rankings are descriptive: HAC inference is for signed bias only, using count-weighted date means, Bartlett L=min(floor(4(T/100)^(2/9)),T−1), no small-sample correction and normal-reference intervals/p-values.

Robustness: overall EDGE leadership survives applicable R25/R50, equal-asset and alternative-convention accuracy checks. Stock RMSE is sensitive to leaving out SNDL, and stock EDGE MAE loses leadership under abs-root. Thin ETF quality cells become tiny or unavailable. Unadjusted comparisons use matched dates; the independently saved SNDL split boundary breaks crossing unadjusted windows only; heuristic corporate-action flags remain diagnostics. These do not replace the primary specification.

Cross-fitted diagnostic: fixed HGB models predict signed and absolute errors, not new spreads. Five chronological date blocks, exact input-interval purging, 1% date embargo, training-only preprocessing and test-only permutation importance. Daily range/open-close conditions are consistent predictors; class heterogeneity matters for EDGE; tier adds little stable conditional importance. Lagging features preserves considerable predictability. Block cross-fitting is ex-post, not forward-only forecasting; correlated features and shared OHLC inputs limit causal interpretation. See saved performance/importance tables for negative class R² and unstable ranks.

Limitations:

- Roll is a transaction-close proxy, not true effective spread or NBBO cost.
- Roll undefinedness is the main sample bottleneck; ETF availability is especially low.
- Common-defined conditioning can create economic selection; no reliability cutoff beyond frozen computability is primary.
- Classes have different calendar support; this is not a balanced 2015–2025 all-class panel.
- Futures primary analysis is 2024 only; supplementary heterogeneous histories are not the primary tier comparison.
- Liquidity tiers use 2024 information, including ex-post/look-ahead classification before 2024 and an in-calibration-year futures comparison.
- Futures and crypto share minute sources between daily OHLC and Roll, creating mechanical dependence.
- Crypto formal quote currency remains UNKNOWN; no USD spread claim is made.
- Bloomberg CshAdjAbnormal is UNKNOWN; acquired adjustment/session equivalence with local First Rate is not certified.
- IMDX historical economic-identity continuity is not independently certified; no manual OCX stitching.
- FX remains in scope but blocked by official sharing/synchronization access; no substitute data were used.
- MAE/RMSE rankings are descriptive; no statistical test of metric differences was specified. HAC applies to signed bias only.
- Cross-fitted error models describe associations, not causal effects, trading forecasts or a new spread estimator.
- Feature and importance stability is conditional on the sampled assets/calendars; correlated predictors can share importance.

Repository: src/ reusable construction/estimation/presentation; tests/; docs/ original project briefs; manifests/ lineage and attrition; outputs/results/{primary,robustness,error_model}/ locked aggregates; outputs/tables/ and outputs/figures/ final exhibits; outputs/reproducibility/ guides/checksums; ignored data/raw_bloomberg/, data/interim/, data/analytic/ licensed inputs and granular derived evidence.

Reproduction: `.venv/Scripts/python.exe -B src/final_artifacts.py --run-tests` rebuilds presentation from locked results. `.venv/Scripts/python.exe -B src/reproduce_final_results.py` independently replays frozen-derived result aggregation without overwriting Steps18–20. Full-from-source order, licensed-data prerequisites, frozen metadata bundle and exact environment are in [the reproduction guide](outputs/reproducibility/final_reproduction_guide.md). This repository alone cannot reproduce licensed observations.

Data/license: publish code, methodology, aggregated tables, figures and small reproducibility metadata only. Do not distribute raw Bloomberg/First Rate values, observation/error/prediction panels or fitted models. Preserve student-extracted Bloomberg raw acquisition unchanged in the student personal Google Drive; shared RiskLab sources are referenced, never duplicated; derived data are reproducible from raw+code+frozen metadata. No data were uploaded or copied to Drive by this step.

Publication gate: release/history checks are recorded in [the publication audit](outputs/reproducibility/publication_audit.md) and [history-cleanup report](outputs/reproducibility/git_history_cleanup_report.md). The executed legacy notebook and pilot raw-row schema remain private local originals; the public notebook is output-free. The external recovery bundle contains original licensed history and must never be published. The final [paper PDF](paper/MMF1941_Project1_Final_Paper.pdf), [portable paper source](paper/MMF1941_Project1_Final_Paper.md) and [final presentation](presentation/MMF1941_Project1_Final_Presentation.pptx) are publication artifacts. See [delivery and reproduction notes](docs/PUBLICATION.md).
