# Table1 estimator definitions and coverage

Definedness uses all design days. Raw-negative rates use finite RAW-computable denominators, not failure denominators. Formulas/mappings are concise summaries of the frozen specifications.

| asset_class | estimator | design_eligible_N | defined_N | undefined_N | failure_rate | raw_negative_rate | raw_computable_N | primary_start | primary_end | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | ROLL | 38232 | 24494 | 13738 | 0.359332 | unavailable / blocked | unavailable / blocked | class-specific | class-specific | PRIMARY_FROZEN |
| ALL | CS | 38232 | 37708 | 524 | 0.0137058 | 0.396255 | 37708 | class-specific | class-specific | PRIMARY_FROZEN |
| ALL | AR | 38232 | 38136 | 96 | 0.00251099 | 0.48251 | 38136 | class-specific | class-specific | PRIMARY_FROZEN |
| ALL | EDGE | 38232 | 38001 | 231 | 0.00604206 | 0.393726 | 38001 | class-specific | class-specific | PRIMARY_FROZEN |
| crypto | ROLL | 12753 | 9867 | 2886 | 0.2263 | unavailable / blocked | unavailable / blocked | 2022-02-01 | 2025-12-31 | PRIMARY_FROZEN |
| crypto | CS | 12753 | 12702 | 51 | 0.00399906 | 0.347819 | 12702 | 2022-02-01 | 2025-12-31 | PRIMARY_FROZEN |
| crypto | AR | 12753 | 12723 | 30 | 0.00235239 | 0.498153 | 12723 | 2022-02-01 | 2025-12-31 | PRIMARY_FROZEN |
| crypto | EDGE | 12753 | 12702 | 51 | 0.00399906 | 0.431428 | 12702 | 2022-02-01 | 2025-12-31 | PRIMARY_FROZEN |
| etfs | ROLL | 8649 | 3181 | 5468 | 0.632212 | unavailable / blocked | unavailable / blocked | 2020-09-15 | 2025-12-31 | PRIMARY_FROZEN |
| etfs | CS | 8649 | 8294 | 355 | 0.0410452 | 0.480468 | 8294 | 2020-09-15 | 2025-12-31 | PRIMARY_FROZEN |
| etfs | AR | 8649 | 8640 | 9 | 0.00104058 | 0.470023 | 8640 | 2020-09-15 | 2025-12-31 | PRIMARY_FROZEN |
| etfs | EDGE | 8649 | 8577 | 72 | 0.00832466 | 0.370176 | 8577 | 2020-09-15 | 2025-12-31 | PRIMARY_FROZEN |
| futures | ROLL | 2331 | 1730 | 601 | 0.257829 | unavailable / blocked | unavailable / blocked | 2024-01-02 | 2024-12-31 | PRIMARY_FROZEN |
| futures | CS | 2331 | 2237 | 94 | 0.040326 | 0.375056 | 2237 | 2024-01-02 | 2024-12-31 | PRIMARY_FROZEN |
| futures | AR | 2331 | 2284 | 47 | 0.020163 | 0.476795 | 2284 | 2024-01-02 | 2024-12-31 | PRIMARY_FROZEN |
| futures | EDGE | 2331 | 2237 | 94 | 0.040326 | 0.394725 | 2237 | 2024-01-02 | 2024-12-31 | PRIMARY_FROZEN |
| stocks | ROLL | 14499 | 9716 | 4783 | 0.329885 | unavailable / blocked | unavailable / blocked | 2019-08-01 | 2025-12-31 | PRIMARY_FROZEN |
| stocks | CS | 14499 | 14475 | 24 | 0.00165529 | 0.393782 | 14475 | 2019-08-01 | 2025-12-31 | PRIMARY_FROZEN |
| stocks | AR | 14499 | 14489 | 10 | 0.000689703 | 0.477121 | 14489 | 2019-08-01 | 2025-12-31 | PRIMARY_FROZEN |
| stocks | EDGE | 14499 | 14485 | 14 | 0.000965584 | 0.374456 | 14485 | 2019-08-01 | 2025-12-31 | PRIMARY_FROZEN |
| fx | ALL | unavailable / blocked | unavailable / blocked | unavailable / blocked | unavailable / blocked | unavailable / blocked | unavailable / blocked | unavailable / blocked | unavailable / blocked | IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS |


| estimator | conceptual_formula | required_inputs | daily_mapping | negative_treatment | units |
| --- | --- | --- | --- | --- | --- |
| ROLL | 2 sqrt(-sample lag-1 covariance of adjacent simple one-minute returns) | One-minute close; exact physical three-close chains | Within frozen asset-session/day; ddof=1; minimum 2 pairs | Nonnegative covariance undefined/NaN; never zero | dimensionless relative spread; bps=10000*relative |
| CS | Overnight-adjusted two-session beta/gamma -> alpha -> 2 tanh(alpha/2) | H/L at t-1,t,t+1; close at t-1,t | Mean corrected intervals (t-1,t) and (t,t+1); both required | Floor each finite interval separately before averaging; retain raw daily signed mean | dimensionless relative spread; bps=10000*relative |
| AR | s2=4(log(C_t)-eta_t)(log(C_t)-eta_(t+1)); eta=(log(H)+log(L))/2 | H/L at t,t+1; close_t | Assigned to target t; no carry-forward or author empirical imputation | sqrt(max(s2,0)); finite negative raw moment remains defined | dimensionless relative spread; bps=10000*relative |
| EDGE | Published Eq26 minimum-variance combination of OHLC log-return moments | OHLC at t-1,t,t+1 | Centered three scheduled sessions; local RMS spread assigned to t | sqrt(max(raw s2,0)); abs-root is robustness only | dimensionless relative spread; bps=10000*relative |


Stocks: 2019-08-01–2025-12-31; ETFs: 2020-09-15–2025-12-31; futures: 2024 only; crypto: 2022-02-01–2025-12-31. FX: in scope but blocked official source access. Roll is a transaction-close proxy, not true effective spread or NBBO cost. Roll undefinedness is the main sample bottleneck; ETF availability is especially low. Common-defined conditioning can create economic selection; no reliability cutoff beyond frozen computability is primary. Classes have different calendar support; this is not a balanced 2015–2025 all-class panel. Futures primary analysis is 2024 only; supplementary heterogeneous histories are not the primary tier comparison. Liquidity tiers use 2024 information, including ex-post/look-ahead classification before 2024 and an in-calibration-year futures comparison. Futures and crypto share minute sources between daily OHLC and Roll, creating mechanical dependence. Crypto formal quote currency remains UNKNOWN; no USD spread claim is made. Bloomberg CshAdjAbnormal is UNKNOWN; acquired adjustment/session equivalence with local First Rate is not certified. IMDX historical economic-identity continuity is not independently certified; no manual OCX stitching. FX remains in scope but blocked by official sharing/synchronization access; no substitute data were used. MAE/RMSE rankings are descriptive; no statistical test of metric differences was specified. HAC applies to signed bias only. Cross-fitted error models describe associations, not causal effects, trading forecasts or a new spread estimator. Feature and importance stability is conditional on the sampled assets/calendars; correlated predictors can share importance.
