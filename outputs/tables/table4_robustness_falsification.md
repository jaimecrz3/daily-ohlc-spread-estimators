# Table4 robustness falsification

Step19 sensitivities and Step20 diagnostics NEVER replace Step18. Overall EDGE leadership survives applicable accuracy sensitivities. Stock RMSE is fragile; stock EDGE MAE loses leadership under abs-root; LOW ETF R25/R50 cells can be tiny/unavailable. ML/influence-only rows do not define new spread rankings. Full class/tier sensitivity cells are in the CSV.

| variant | asset_class | liquidity_tier | affected_scope | sample_N_display | mae_leader | rmse_leader | primary_conclusion_changed | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Roll R25 | ALL | ALL | overall | 16150 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R25 | crypto | ALL | asset_class | 7436 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R25 | etfs | ALL | asset_class | 1151 | CS | CS | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R25 | futures | ALL | asset_class | 1667 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R25 | stocks | ALL | asset_class | 5896 | EDGE | CS | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R25 | etfs | LOW | asset_class_x_tier | 6 | EDGE | EDGE | True | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R50 | ALL | ALL | overall | 12908 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R50 | crypto | ALL | asset_class | 6399 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R50 | etfs | ALL | asset_class | 732 | CS | CS | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R50 | futures | ALL | asset_class | 1652 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R50 | stocks | ALL | asset_class | 4125 | EDGE | CS | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Roll R50 | etfs | LOW | asset_class_x_tier | 0 | UNAVAILABLE | UNAVAILABLE | True | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Equal asset weighting | ALL | ALL | overall | 24377 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Equal asset weighting | crypto | ALL | asset_class | 9828 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Equal asset weighting | etfs | ALL | asset_class | 3175 | CS | CS | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Equal asset weighting | futures | ALL | asset_class | 1667 | EDGE | EDGE | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Equal asset weighting | stocks | ALL | asset_class | 9707 | EDGE | CS | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Equal asset weighting | etfs | LOW | asset_class_x_tier | 245 | CS | CS | False | ROBUSTNESS / SENSITIVITY only; original Step18 source files remain primary |
| Bloomberg unadjusted | etfs | ALL | asset_class | 3175 | CS | CS | False | Paired adjusted/unadjusted comparison uses identical unadjusted-common dates; verified incoming split edges broken only for unadjusted |
| Bloomberg unadjusted | stocks | ALL | asset_class | 9705 | EDGE | CS | False | Paired adjusted/unadjusted comparison uses identical unadjusted-common dates; verified incoming split edges broken only for unadjusted |
| Bloomberg unadjusted | etfs | LOW | asset_class_x_tier | 245 | CS | CS | False | Paired adjusted/unadjusted comparison uses identical unadjusted-common dates; verified incoming split edges broken only for unadjusted |
| EDGE abs-root | ALL | ALL | overall | 24377 | EDGE | EDGE | False | CS/AR unchanged; alternative EDGE replaces zero floor only for this sensitivity; not a raw-negative definition change |
| EDGE abs-root | crypto | ALL | asset_class | 9828 | EDGE | EDGE | False | CS/AR unchanged; alternative EDGE replaces zero floor only for this sensitivity; not a raw-negative definition change |
| EDGE abs-root | etfs | ALL | asset_class | 3175 | CS | CS | False | CS/AR unchanged; alternative EDGE replaces zero floor only for this sensitivity; not a raw-negative definition change |
| EDGE abs-root | futures | ALL | asset_class | 1667 | EDGE | EDGE | False | CS/AR unchanged; alternative EDGE replaces zero floor only for this sensitivity; not a raw-negative definition change |
| EDGE abs-root | stocks | ALL | asset_class | 9707 | CS | CS | True | CS/AR unchanged; alternative EDGE replaces zero floor only for this sensitivity; not a raw-negative definition change |
| Leave-one-asset-out | crypto | ALL | class | 8476–9457 | EDGE | EDGE | False | Nine deterministic asset omissions within class; not a preferred alternative sample |
| Leave-one-asset-out | etfs | ALL | class | 2462–3154 | CS | CS | False | Nine deterministic asset omissions within class; not a preferred alternative sample |
| Leave-one-asset-out | futures | ALL | class | 1437–1535 | EDGE | EDGE | False | Nine deterministic asset omissions within class; not a preferred alternative sample |
| Leave-one-asset-out | stocks | ALL | class | 8266–9066 | EDGE | CS;EDGE | True | Nine deterministic asset omissions within class; not a preferred alternative sample |
| Single-extreme influence | crypto | ALL | class x method | 9827 | NOT_RANKED | NOT_RANKED | NOT_RETESTED | Different single observation per method; diagnostic only, not a new common-sample horse race |
| Single-extreme influence | etfs | ALL | class x method | 3174 | NOT_RANKED | NOT_RANKED | NOT_RETESTED | Different single observation per method; diagnostic only, not a new common-sample horse race |
| Single-extreme influence | futures | ALL | class x method | 1666 | NOT_RANKED | NOT_RANKED | NOT_RETESTED | Different single observation per method; diagnostic only, not a new common-sample horse race |
| Single-extreme influence | stocks | ALL | class x method | 9706 | NOT_RANKED | NOT_RANKED | NOT_RETESTED | Different single observation per method; diagnostic only, not a new common-sample horse race |
| Cross-fitted error model | ALL | ALL | absolute_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Cross-fitted error model | ALL | ALL | signed_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Cross-fitted error model | ALL | ALL | absolute_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Cross-fitted error model | ALL | ALL | signed_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Cross-fitted error model | ALL | ALL | absolute_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Cross-fitted error model | ALL | ALL | signed_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Lagged placebo | ALL | ALL | absolute_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Lagged placebo | ALL | ALL | signed_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Lagged placebo | ALL | ALL | absolute_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Lagged placebo | ALL | ALL | signed_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Lagged placebo | ALL | ALL | absolute_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |
| Lagged placebo | ALL | ALL | signed_error_bps | 24377 | NOT_APPLICABLE | NOT_APPLICABLE | NOT_RETESTED | Prediction of errors, not spread accuracy or a new estimator; association only |


Stocks: 2019-08-01–2025-12-31; ETFs: 2020-09-15–2025-12-31; futures: 2024 only; crypto: 2022-02-01–2025-12-31. FX: in scope but blocked official source access. Roll is a transaction-close proxy, not true effective spread or NBBO cost. Roll undefinedness is the main sample bottleneck; ETF availability is especially low. Common-defined conditioning can create economic selection; no reliability cutoff beyond frozen computability is primary. Classes have different calendar support; this is not a balanced 2015–2025 all-class panel. Futures primary analysis is 2024 only; supplementary heterogeneous histories are not the primary tier comparison. Liquidity tiers use 2024 information, including ex-post/look-ahead classification before 2024 and an in-calibration-year futures comparison. Futures and crypto share minute sources between daily OHLC and Roll, creating mechanical dependence. Crypto formal quote currency remains UNKNOWN; no USD spread claim is made. Bloomberg CshAdjAbnormal is UNKNOWN; acquired adjustment/session equivalence with local First Rate is not certified. IMDX historical economic-identity continuity is not independently certified; no manual OCX stitching. FX remains in scope but blocked by official sharing/synchronization access; no substitute data were used. MAE/RMSE rankings are descriptive; no statistical test of metric differences was specified. HAC applies to signed bias only. Cross-fitted error models describe associations, not causal effects, trading forecasts or a new spread estimator. Feature and importance stability is conditional on the sampled assets/calendars; correlated predictors can share importance.
