# Table3 failure negative decomposition

Panel A

| asset_class | estimator | failure_N | denominator_N | failure_rate |
| --- | --- | --- | --- | --- |
| ALL | ROLL | 13738 | 38232 | 0.359332 |
| ALL | CS | 524 | 38232 | 0.0137058 |
| ALL | AR | 96 | 38232 | 0.00251099 |
| ALL | EDGE | 231 | 38232 | 0.00604206 |
| crypto | ROLL | 2886 | 12753 | 0.2263 |
| crypto | CS | 51 | 12753 | 0.00399906 |
| crypto | AR | 30 | 12753 | 0.00235239 |
| crypto | EDGE | 51 | 12753 | 0.00399906 |
| etfs | ROLL | 5468 | 8649 | 0.632212 |
| etfs | CS | 355 | 8649 | 0.0410452 |
| etfs | AR | 9 | 8649 | 0.00104058 |
| etfs | EDGE | 72 | 8649 | 0.00832466 |
| futures | ROLL | 601 | 2331 | 0.257829 |
| futures | CS | 94 | 2331 | 0.040326 |
| futures | AR | 47 | 2331 | 0.020163 |
| futures | EDGE | 94 | 2331 | 0.040326 |
| stocks | ROLL | 4783 | 14499 | 0.329885 |
| stocks | CS | 24 | 14499 | 0.00165529 |
| stocks | AR | 10 | 14499 | 0.000689703 |
| stocks | EDGE | 14 | 14499 | 0.000965584 |


Panel B

| asset_class | estimator | negative_N | raw_computable_N | negative_rate |
| --- | --- | --- | --- | --- |
| ALL | CS | 14942 | 37708 | 0.396255 |
| ALL | AR | 18401 | 38136 | 0.48251 |
| ALL | EDGE | 14962 | 38001 | 0.393726 |
| crypto | CS | 4418 | 12702 | 0.347819 |
| crypto | AR | 6338 | 12723 | 0.498153 |
| crypto | EDGE | 5480 | 12702 | 0.431428 |
| etfs | CS | 3985 | 8294 | 0.480468 |
| etfs | AR | 4061 | 8640 | 0.470023 |
| etfs | EDGE | 3175 | 8577 | 0.370176 |
| futures | CS | 839 | 2237 | 0.375056 |
| futures | AR | 1089 | 2284 | 0.476795 |
| futures | EDGE | 883 | 2237 | 0.394725 |
| stocks | CS | 5700 | 14475 | 0.393782 |
| stocks | AR | 6913 | 14489 | 0.477121 |
| stocks | EDGE | 5424 | 14485 | 0.374456 |


Panel C

| asset_class | estimator | mae_rank | rmse_rank | accuracy_leader_status |
| --- | --- | --- | --- | --- |
| crypto | CS | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| crypto | AR | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| crypto | EDGE | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| etfs | CS | 1 | 1 | DESCRIPTIVE_LEADER: CS |
| etfs | AR | 3 | 3 | DESCRIPTIVE_LEADER: CS |
| etfs | EDGE | 2 | 2 | DESCRIPTIVE_LEADER: CS |
| futures | CS | 2 | 2 | DESCRIPTIVE_LEADER: EDGE |
| futures | AR | 3 | 3 | DESCRIPTIVE_LEADER: EDGE |
| futures | EDGE | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| stocks | CS | 2 | 1 | MIXED |
| stocks | AR | 3 | 3 | MIXED |
| stocks | EDGE | 1 | 2 | MIXED |


Panel D

| asset_class | estimator | original_N | removed_N | mae_pct_change | rmse_pct_change |
| --- | --- | --- | --- | --- | --- |
| crypto | CS | 9828 | 1 | -0.14093 | -0.531568 |
| crypto | AR | 9828 | 1 | -0.245682 | -1.00777 |
| crypto | EDGE | 9828 | 1 | -0.747419 | -6.15901 |
| etfs | CS | 3175 | 1 | -0.971648 | -4.72004 |
| etfs | AR | 3175 | 1 | -0.635581 | -1.70132 |
| etfs | EDGE | 3175 | 1 | -0.673362 | -2.04103 |
| futures | CS | 1667 | 1 | -0.677153 | -1.8046 |
| futures | AR | 1667 | 1 | -0.863299 | -1.83879 |
| futures | EDGE | 1667 | 1 | -1.07999 | -2.49477 |
| stocks | CS | 9707 | 1 | -0.290165 | -1.74146 |
| stocks | AR | 9707 | 1 | -0.757337 | -7.18629 |
| stocks | EDGE | 9707 | 1 | -0.549078 | -3.7986 |




Stocks: 2019-08-01–2025-12-31; ETFs: 2020-09-15–2025-12-31; futures: 2024 only; crypto: 2022-02-01–2025-12-31. FX: in scope but blocked official source access. Roll is a transaction-close proxy, not true effective spread or NBBO cost. Roll undefinedness is the main sample bottleneck; ETF availability is especially low. Common-defined conditioning can create economic selection; no reliability cutoff beyond frozen computability is primary. Classes have different calendar support; this is not a balanced 2015–2025 all-class panel. Futures primary analysis is 2024 only; supplementary heterogeneous histories are not the primary tier comparison. Liquidity tiers use 2024 information, including ex-post/look-ahead classification before 2024 and an in-calibration-year futures comparison. Futures and crypto share minute sources between daily OHLC and Roll, creating mechanical dependence. Crypto formal quote currency remains UNKNOWN; no USD spread claim is made. Bloomberg CshAdjAbnormal is UNKNOWN; acquired adjustment/session equivalence with local First Rate is not certified. IMDX historical economic-identity continuity is not independently certified; no manual OCX stitching. FX remains in scope but blocked by official sharing/synchronization access; no substitute data were used. MAE/RMSE rankings are descriptive; no statistical test of metric differences was specified. HAC applies to signed bias only. Cross-fitted error models describe associations, not causal effects, trading forecasts or a new spread estimator. Feature and importance stability is conditional on the sampled assets/calendars; correlated predictors can share importance.
