# Final chronological design decisions

This is a transcription of existing step-specific decisions, not retrospective optimization. Step identifiers are used where an approval date was not recorded; no supervisor approval/date is invented. Original specifications and Steps18–20 outputs remain immutable. Original hypotheses are retained in docs/project_1.md and README, including falsified components.

| date_or_step | decision | frozen_choice | rationale | role | status |
| --- | --- | --- | --- | --- | --- |
| Steps1–3 / Step10.1 | Roll benchmark | One-minute close simple-return Roll proxy; exact adjacency, physical pairs, ddof=1, minimum two; nonnegative gamma undefined | Proxy selected without estimator performance; minimum is computability, not precision | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Steps2/5/11.3/12.2/14 | Sessions | Equity RTH; crypto UTC; verified root-specific futures 18:00–17:00 trade date | No midnight futures day, filling, gap bridging or undocumented session extrapolation | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Steps4/7A/7A.1/9/11.3/12 | Universe and liquidity | 2024 turnover medians within class, deterministic tiers and rank-quantile selection; frozen security-type corrections | No benchmark/estimator selection criterion; REIT/ADS retained; IMDX source-defined history | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Step10.2.1 | Bloomberg daily source | Adjusted primary, unadjusted robustness; abnormal setting UNKNOWN | Common source across methods; no inferred Bloomberg default | PRIMARY / ROBUSTNESS | FROZEN / EXECUTED AS RECORDED |
| Steps5/11.3 | Futures contracts and calendar | Provider trade-date mapping selects one individual unadjusted contract; no cross-contract estimator window; 2024 all-nine primary | Avoid stitching/back adjustment and calendar/product-composition confounding | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Steps12/12.2 | Crypto quote and calendar | Verified common provider quote basis, formal currency UNKNOWN; exact nine-way valid UTC intersection | Do not relabel USD; historical extras supplementary only | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Steps13/14 | FX access | In scope but blocked official sharing/synchronization access; no substitutes | Unavailable source is not a zero sample or intentional class deletion | PRIMARY scope limitation | FROZEN / EXECUTED AS RECORDED |
| Step14 | Common-defined and attrition | Design eligible independent of outputs; common conjunction of Roll/CS/AR/EDGE definedness | Identical accuracy rows, no extra quality/pair/size/zero filter | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Step15 | Estimator mathematics and mappings | CS overnight-adjusted separately floored paired intervals; AR close-t two-day; EDGE centered three-session paper zero-floor | Literal frozen kernels with explicit project daily mapping; no tuning to provider results | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Step15 | Negative and failure denominators | Finite raw-negative stays defined; failures/all design; negatives/finite raw-computable design | Do not conflate negative, undefined and zero | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Step16 | Weighting and HAC | Equal asset-day; WLS date means weighted n_t; Bartlett count-only lag; uncorrected sandwich; normal 95% bias CI/p-value | Preserve pooled point estimand while addressing aggregate date dependence; no MAE/RMSE test | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Step16 | IMDX identity | Retain source-defined history without OCX stitching; continuity uncertified | Do not fabricate independent identity certification or replace universe after outcomes | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Steps17–18 | Provider and primary execution | Exact frozen design and common samples; no post-hoc exclusions or metric-difference significance | Outcome audit then primary horse race under prior freezes | PRIMARY | FROZEN / EXECUTED AS RECORDED |
| Step19 | Robustness | R25/R50; equal asset; matched unadjusted with verified split edge; EDGE abs; all asset omissions; single-extreme diagnostic | Prespecified sensitivities never become preferred primary choices; preserve contrary/empty cases | ROBUSTNESS | FROZEN / EXECUTED AS RECORDED |
| Step20 | Error diagnostic | Both targets; fixed 200-iteration HGB; five date blocks; exact purging, 1% embargo; train-only medians/OHE; test-only permutations; scheduled +1 lag | Associations only, no new estimator or hyperparameter/feature search; lagged AR information extended | DIAGNOSTIC | FROZEN / EXECUTED AS RECORDED |
| Step21 | Final presentation freeze | Saved results only; full-range asinh displays; machine-readable source/row/metric ledger | Presentation does not change observations, hypotheses, formulas, inference or result hierarchy | PRESENTATION | FROZEN / EXECUTED AS RECORDED |


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
