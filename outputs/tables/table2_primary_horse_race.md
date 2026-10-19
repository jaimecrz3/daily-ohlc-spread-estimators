# Table2 primary horse race

**Primary common-defined sample = 24377 asset-days.** Equal weight per asset-day. Signed error=estimator minus Roll; bps. HAC uncertainty concerns BIAS only, not MAE/RMSE differences.

Panel A

| asset_class | liquidity_tier | estimator | bias_bps | mae_bps | rmse_bps | N_asset_days | hac_se_bps | ci95_low_bps | ci95_high_bps | p_value_two_sided |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | ALL | CS | 110.8 | 121.304 | 201.272 | 24377 | 2.94268 | 105.033 | 116.568 | 2.93374e-310 |
| ALL | ALL | AR | 101.675 | 127.712 | 257.71 | 24377 | 3.27072 | 95.2646 | 108.086 | 3.67449e-212 |
| ALL | ALL | EDGE | 25.9871 | 53.5921 | 122.183 | 24377 | 1.81557 | 22.4287 | 29.5456 | 1.80204e-46 |


Panel B

| asset_class | liquidity_tier | estimator | bias_bps | mae_bps | rmse_bps | N_asset_days |
| --- | --- | --- | --- | --- | --- | --- |
| crypto | ALL | CS | 172.344 | 185.612 | 268.726 | 9828 |
| crypto | ALL | AR | 137.796 | 171.746 | 306.83 | 9828 |
| crypto | ALL | EDGE | -2.19486 | 38.8849 | 84.4821 | 9828 |
| etfs | ALL | CS | 20.475 | 24.7442 | 45.9835 | 3175 |
| etfs | ALL | AR | 35.0414 | 42.0797 | 85.7013 | 3175 |
| etfs | ALL | EDGE | 23.8434 | 29.6631 | 58.3753 | 3175 |
| futures | ALL | CS | 23.0201 | 23.2345 | 36.6599 | 1667 |
| futures | ALL | AR | 22.6575 | 23.3281 | 45.6823 | 1667 |
| futures | ALL | EDGE | 4.68356 | 5.28744 | 11.0169 | 1667 |
| stocks | ALL | CS | 93.1087 | 104.619 | 166.422 | 9707 |
| stocks | ALL | AR | 100.469 | 129.064 | 262.119 | 9707 |
| stocks | ALL | EDGE | 58.8801 | 84.605 | 170.671 | 9707 |


Panel C

| asset_class | liquidity_tier | estimator | bias_bps | mae_bps | rmse_bps | N_asset_days |
| --- | --- | --- | --- | --- | --- | --- |
| crypto | HIGH | CS | 173.749 | 178.015 | 241.952 | 3710 |
| crypto | HIGH | AR | 147.118 | 161.052 | 289.898 | 3710 |
| crypto | HIGH | EDGE | 5.76952 | 21.6434 | 45.5979 | 3710 |
| crypto | LOW | CS | 133.145 | 165.491 | 245.995 | 2292 |
| crypto | LOW | AR | 101.791 | 167.391 | 283.949 | 2292 |
| crypto | LOW | EDGE | -8.0065 | 65.4078 | 128.558 | 2292 |
| crypto | MEDIUM | CS | 194.463 | 205.033 | 304.107 | 3826 |
| crypto | MEDIUM | AR | 150.326 | 184.725 | 334.724 | 3826 |
| crypto | MEDIUM | EDGE | -6.43624 | 39.7147 | 80.1045 | 3826 |
| etfs | HIGH | CS | 19.4202 | 20.6074 | 36.5123 | 1839 |
| etfs | HIGH | AR | 32.3017 | 34.634 | 68.2406 | 1839 |
| etfs | HIGH | EDGE | 21.2826 | 23.2857 | 44.4915 | 1839 |
| etfs | LOW | CS | 11.6106 | 22.6118 | 41.3397 | 245 |
| etfs | LOW | AR | 26.0438 | 40.6801 | 78.2687 | 245 |
| etfs | LOW | EDGE | 20.2377 | 31.3118 | 58.0652 | 245 |
| etfs | MEDIUM | CS | 24.2436 | 32.1962 | 59.3513 | 1091 |
| etfs | MEDIUM | AR | 41.6801 | 54.9446 | 110.223 | 1091 |
| etfs | MEDIUM | EDGE | 28.9696 | 40.0426 | 76.3095 | 1091 |
| futures | HIGH | CS | 21.1809 | 21.42 | 36.9044 | 521 |
| futures | HIGH | AR | 20.6343 | 21.3073 | 43.4174 | 521 |
| futures | HIGH | EDGE | 4.74777 | 5.33698 | 11.4586 | 521 |
| futures | LOW | CS | 24.8373 | 25.062 | 40.1733 | 590 |
| futures | LOW | AR | 23.9215 | 24.6519 | 50.6097 | 590 |
| futures | LOW | EDGE | 4.51177 | 5.18961 | 10.8488 | 590 |
| futures | MEDIUM | CS | 22.8152 | 22.9954 | 32.2591 | 556 |
| futures | MEDIUM | AR | 23.212 | 23.817 | 42.1009 | 556 |
| futures | MEDIUM | EDGE | 4.80569 | 5.34484 | 10.7688 | 556 |
| stocks | HIGH | CS | 64.8444 | 67.5093 | 97.4521 | 3481 |
| stocks | HIGH | AR | 80.8917 | 88.0038 | 161.868 | 3481 |
| stocks | HIGH | EDGE | 50.244 | 56.171 | 96.4051 | 3481 |
| stocks | LOW | CS | 114.652 | 146.114 | 216.756 | 2399 |
| stocks | LOW | AR | 116.092 | 186.202 | 326.421 | 2399 |
| stocks | LOW | EDGE | 59.3865 | 125.024 | 215.481 | 2399 |
| stocks | MEDIUM | CS | 105.313 | 112.363 | 179.333 | 3827 |
| stocks | MEDIUM | AR | 108.482 | 130.593 | 289.215 | 3827 |
| stocks | MEDIUM | EDGE | 66.418 | 85.1311 | 190.587 | 3827 |




Stocks: 2019-08-01–2025-12-31; ETFs: 2020-09-15–2025-12-31; futures: 2024 only; crypto: 2022-02-01–2025-12-31. FX: in scope but blocked official source access. Roll is a transaction-close proxy, not true effective spread or NBBO cost. Roll undefinedness is the main sample bottleneck; ETF availability is especially low. Common-defined conditioning can create economic selection; no reliability cutoff beyond frozen computability is primary. Classes have different calendar support; this is not a balanced 2015–2025 all-class panel. Futures primary analysis is 2024 only; supplementary heterogeneous histories are not the primary tier comparison. Liquidity tiers use 2024 information, including ex-post/look-ahead classification before 2024 and an in-calibration-year futures comparison. Futures and crypto share minute sources between daily OHLC and Roll, creating mechanical dependence. Crypto formal quote currency remains UNKNOWN; no USD spread claim is made. Bloomberg CshAdjAbnormal is UNKNOWN; acquired adjustment/session equivalence with local First Rate is not certified. IMDX historical economic-identity continuity is not independently certified; no manual OCX stitching. FX remains in scope but blocked by official sharing/synchronization access; no substitute data were used. MAE/RMSE rankings are descriptive; no statistical test of metric differences was specified. HAC applies to signed bias only. Cross-fitted error models describe associations, not causal effects, trading forecasts or a new spread estimator. Feature and importance stability is conditional on the sampled assets/calendars; correlated predictors can share importance.
