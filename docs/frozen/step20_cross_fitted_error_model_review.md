# Step20 cross-fitted error model

**CROSSFITTED_ERROR_MODEL_COMPLETE**. ROBUSTNESS / DIAGNOSTIC ONLY. Tests: 318 passed; 0 failed.

The source sample is exactly 24,377 unchanged Step18 common-defined asset-days for all three estimators and both targets. No new spread estimator or adjustment of primary spread estimates is produced. Signed and absolute target models are separately fitted using the same prespecified features and settings.

Chronological test folds and purge/embargo audit (counts independent of target):

| fold | estimator | variant | first_test_date | last_test_date | T_test_dates | train_N_before_purge | purged_N | embargoed_N | embargo_candidate_N | embargo_dates_requested | embargo_dates_available | final_train_N | test_N | no_information_overlap | no_test_rows_in_training | embargo_respected |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CS | ALIGNED | 2019-08-01 | 2021-03-19 | 412 | 21486 | 14 | 139 | 153 | 21 | 21 | 21333 | 2891 | True | True | True |
| 2 | CS | ALIGNED | 2021-03-22 | 2022-08-13 | 412 | 20458 | 53 | 203 | 237 | 21 | 21 | 20202 | 3919 | True | True | True |
| 3 | CS | ALIGNED | 2022-08-14 | 2023-09-28 | 411 | 19452 | 64 | 239 | 269 | 21 | 21 | 19149 | 4925 | True | True | True |
| 4 | CS | ALIGNED | 2023-09-29 | 2024-11-12 | 411 | 17317 | 85 | 332 | 388 | 21 | 21 | 16900 | 7060 | True | True | True |
| 5 | CS | ALIGNED | 2024-11-13 | 2025-12-30 | 411 | 18795 | 49 | 0 | 0 | 21 | 0 | 18746 | 5582 | True | True | True |
| 1 | AR | ALIGNED | 2019-08-01 | 2021-03-19 | 412 | 21486 | 5 | 148 | 153 | 21 | 21 | 21333 | 2891 | True | True | True |
| 2 | AR | ALIGNED | 2021-03-22 | 2022-08-13 | 412 | 20458 | 26 | 219 | 237 | 21 | 21 | 20213 | 3919 | True | True | True |
| 3 | AR | ALIGNED | 2022-08-14 | 2023-09-28 | 411 | 19452 | 28 | 256 | 269 | 21 | 21 | 19168 | 4925 | True | True | True |
| 4 | AR | ALIGNED | 2023-09-29 | 2024-11-12 | 411 | 17317 | 38 | 362 | 388 | 21 | 21 | 16917 | 7060 | True | True | True |
| 5 | AR | ALIGNED | 2024-11-13 | 2025-12-30 | 411 | 18795 | 25 | 0 | 0 | 21 | 0 | 18770 | 5582 | True | True | True |
| 1 | EDGE | ALIGNED | 2019-08-01 | 2021-03-19 | 412 | 21486 | 14 | 139 | 153 | 21 | 21 | 21333 | 2891 | True | True | True |
| 2 | EDGE | ALIGNED | 2021-03-22 | 2022-08-13 | 412 | 20458 | 53 | 203 | 237 | 21 | 21 | 20202 | 3919 | True | True | True |
| 3 | EDGE | ALIGNED | 2022-08-14 | 2023-09-28 | 411 | 19452 | 64 | 239 | 269 | 21 | 21 | 19149 | 4925 | True | True | True |
| 4 | EDGE | ALIGNED | 2023-09-29 | 2024-11-12 | 411 | 17317 | 85 | 332 | 388 | 21 | 21 | 16900 | 7060 | True | True | True |
| 5 | EDGE | ALIGNED | 2024-11-13 | 2025-12-30 | 411 | 18795 | 49 | 0 | 0 | 21 | 0 | 18746 | 5582 | True | True | True |
| 1 | CS | LAG1_PLACEBO | 2019-08-01 | 2021-03-19 | 412 | 21486 | 14 | 139 | 153 | 21 | 21 | 21333 | 2891 | True | True | True |
| 2 | CS | LAG1_PLACEBO | 2021-03-22 | 2022-08-13 | 412 | 20458 | 53 | 203 | 237 | 21 | 21 | 20202 | 3919 | True | True | True |
| 3 | CS | LAG1_PLACEBO | 2022-08-14 | 2023-09-28 | 411 | 19452 | 64 | 239 | 269 | 21 | 21 | 19149 | 4925 | True | True | True |
| 4 | CS | LAG1_PLACEBO | 2023-09-29 | 2024-11-12 | 411 | 17317 | 85 | 332 | 388 | 21 | 21 | 16900 | 7060 | True | True | True |
| 5 | CS | LAG1_PLACEBO | 2024-11-13 | 2025-12-30 | 411 | 18795 | 49 | 0 | 0 | 21 | 0 | 18746 | 5582 | True | True | True |
| 1 | AR | LAG1_PLACEBO | 2019-08-01 | 2021-03-19 | 412 | 21486 | 14 | 139 | 153 | 21 | 21 | 21333 | 2891 | True | True | True |
| 2 | AR | LAG1_PLACEBO | 2021-03-22 | 2022-08-13 | 412 | 20458 | 53 | 203 | 237 | 21 | 21 | 20202 | 3919 | True | True | True |
| 3 | AR | LAG1_PLACEBO | 2022-08-14 | 2023-09-28 | 411 | 19452 | 64 | 239 | 269 | 21 | 21 | 19149 | 4925 | True | True | True |
| 4 | AR | LAG1_PLACEBO | 2023-09-29 | 2024-11-12 | 411 | 17317 | 85 | 332 | 388 | 21 | 21 | 16900 | 7060 | True | True | True |
| 5 | AR | LAG1_PLACEBO | 2024-11-13 | 2025-12-30 | 411 | 18795 | 49 | 0 | 0 | 21 | 0 | 18746 | 5582 | True | True | True |
| 1 | EDGE | LAG1_PLACEBO | 2019-08-01 | 2021-03-19 | 412 | 21486 | 14 | 139 | 153 | 21 | 21 | 21333 | 2891 | True | True | True |
| 2 | EDGE | LAG1_PLACEBO | 2021-03-22 | 2022-08-13 | 412 | 20458 | 53 | 203 | 237 | 21 | 21 | 20202 | 3919 | True | True | True |
| 3 | EDGE | LAG1_PLACEBO | 2022-08-14 | 2023-09-28 | 411 | 19452 | 64 | 239 | 269 | 21 | 21 | 19149 | 4925 | True | True | True |
| 4 | EDGE | LAG1_PLACEBO | 2023-09-29 | 2024-11-12 | 411 | 17317 | 85 | 332 | 388 | 21 | 21 | 16900 | 7060 | True | True | True |
| 5 | EDGE | LAG1_PLACEBO | 2024-11-13 | 2025-12-30 | 411 | 18795 | 49 | 0 | 0 | 21 | 0 | 18746 | 5582 | True | True | True |

Aligned cross-fitted prediction performance (prediction errors, not a replacement spread horse race; bps):

| estimator | target_type | N | MAE | RMSE | R2 | baseline_MAE | baseline_RMSE | baseline_R2 | MAE_improvement_pct | RMSE_improvement_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AR | absolute_error_bps | 24377 | 120.669 | 204.962 | 0.161561 | 139.143 | 224.171 | -0.00296339 | 13.2772 | 8.56904 |
| AR | signed_error_bps | 24377 | 138.794 | 227.451 | 0.0774433 | 150.499 | 237.426 | -0.00524823 | 7.77726 | 4.20124 |
| CS | absolute_error_bps | 24377 | 78.6235 | 133.899 | 0.304959 | 107.077 | 161.201 | -0.00737847 | 26.5732 | 16.9368 |
| CS | signed_error_bps | 24377 | 86.8596 | 147.143 | 0.23314 | 112.295 | 168.833 | -0.00959692 | 22.6503 | 12.8466 |
| EDGE | absolute_error_bps | 24377 | 45.213 | 95.7874 | 0.23899 | 56.4243 | 110.458 | -0.0119703 | 19.8697 | 13.2816 |
| EDGE | signed_error_bps | 24377 | 54.7189 | 112.231 | 0.116298 | 60.5024 | 120.598 | -0.0203725 | 9.55906 | 6.93774 |

Class diagnostics, reusing the same pooled-model held-out predictions:

| asset_class | estimator | target_type | N | MAE | RMSE | R2 | baseline_RMSE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| stocks | AR | absolute_error_bps | 9707 | 117.396 | 206.841 | 0.178018 | 228.37 |
| etfs | AR | absolute_error_bps | 3175 | 40.0603 | 63.6361 | 0.273492 | 115.143 |
| futures | AR | absolute_error_bps | 1667 | 26.9911 | 36.2224 | 0.149485 | 118.456 |
| crypto | AR | absolute_error_bps | 9828 | 165.831 | 245.787 | 0.0655413 | 257.82 |
| stocks | AR | signed_error_bps | 9707 | 137.899 | 231.159 | 0.0883415 | 242.335 |
| etfs | AR | signed_error_bps | 3175 | 44.8633 | 70.064 | 0.197463 | 104.553 |
| futures | AR | signed_error_bps | 1667 | 28.294 | 37.3692 | 0.11252 | 98.164 |
| crypto | AR | signed_error_bps | 9828 | 188.766 | 271.513 | 0.0191284 | 276.86 |
| stocks | CS | absolute_error_bps | 9707 | 68.3998 | 110.365 | 0.272862 | 130.736 |
| etfs | CS | absolute_error_bps | 3175 | 18.1888 | 31.9583 | 0.320111 | 104.522 |
| futures | CS | absolute_error_bps | 1667 | 18.9065 | 26.0865 | 0.153717 | 108.919 |
| crypto | CS | absolute_error_bps | 9828 | 118.374 | 178.87 | 0.152728 | 205.015 |
| stocks | CS | signed_error_bps | 9707 | 77.483 | 125.259 | 0.175399 | 139.403 |
| etfs | CS | signed_error_bps | 3175 | 20.9692 | 37.2886 | 0.179809 | 100.089 |
| futures | CS | signed_error_bps | 1667 | 19.0875 | 26.4809 | 0.138553 | 100.763 |
| crypto | CS | signed_error_bps | 9828 | 128.902 | 194.005 | 0.114637 | 215.752 |
| stocks | EDGE | absolute_error_bps | 9707 | 67.3855 | 130.563 | 0.224115 | 152.013 |
| etfs | EDGE | absolute_error_bps | 3175 | 24.7358 | 43.0939 | 0.265327 | 56.9944 |
| futures | EDGE | absolute_error_bps | 1667 | 10.2874 | 13.0011 | -0.809458 | 53.6666 |
| crypto | EDGE | absolute_error_bps | 9828 | 35.8527 | 72.749 | 0.0591579 | 76.8212 |
| stocks | EDGE | signed_error_bps | 9707 | 82.9419 | 151.244 | 0.108614 | 164.321 |
| etfs | EDGE | signed_error_bps | 3175 | 28.6639 | 48.4061 | 0.174704 | 54.127 |
| futures | EDGE | signed_error_bps | 1667 | 9.71038 | 12.7912 | -0.645424 | 31.9613 |
| crypto | EDGE | signed_error_bps | 9828 | 42.895 | 88.6816 | -0.102635 | 91.0234 |

Permutation importance uses only raw TEST columns and a frozen fitted training pipeline, five fixed-seed permutations per feature. Absolute-target importance is increase in test MAE; signed-target importance is increase in test RMSE. Negative importance is retained. Fold ranks use average ties; top-three counts mean rank<=3.

Top mean importances and stability (full ranks/correlations, including instability, are saved):

| estimator | target_type | feature | mean_importance_bps | std_importance_bps | top3_folds | positive_importance_folds |
| --- | --- | --- | --- | --- | --- | --- |
| AR | absolute_error_bps | hl_range_bps | 19.273 | 4.21911 | 5 | 5 |
| AR | absolute_error_bps | abs_open_close_bps | 4.79838 | 1.32025 | 5 | 5 |
| AR | absolute_error_bps | asset_class | 1.23416 | 0.71254 | 3 | 5 |
| AR | signed_error_bps | abs_open_close_bps | 13.239 | 3.40501 | 5 | 5 |
| AR | signed_error_bps | hl_range_bps | 6.34573 | 0.955102 | 5 | 5 |
| AR | signed_error_bps | log_close | 1.48129 | 1.14072 | 3 | 5 |
| CS | absolute_error_bps | hl_range_bps | 41.1052 | 6.50019 | 5 | 5 |
| CS | absolute_error_bps | abs_open_close_bps | 2.66865 | 0.908152 | 5 | 5 |
| CS | absolute_error_bps | asset_class | 1.0676 | 0.582811 | 4 | 5 |
| CS | signed_error_bps | hl_range_bps | 37.4709 | 3.69242 | 5 | 5 |
| CS | signed_error_bps | benchmark_bar_coverage | 2.95401 | 1.49974 | 4 | 5 |
| CS | signed_error_bps | abs_open_close_bps | 2.63188 | 3.34351 | 2 | 3 |
| EDGE | absolute_error_bps | asset_class | 13.8629 | 9.00122 | 4 | 5 |
| EDGE | absolute_error_bps | hl_range_bps | 11.7133 | 2.14713 | 5 | 5 |
| EDGE | absolute_error_bps | abs_open_close_bps | 3.25886 | 0.992412 | 3 | 5 |
| EDGE | signed_error_bps | asset_class | 21.7681 | 12.7186 | 5 | 5 |
| EDGE | signed_error_bps | abs_open_close_bps | 9.37278 | 4.95044 | 5 | 5 |
| EDGE | signed_error_bps | log1p_daily_volume | 3.51144 | 4.69552 | 3 | 4 |

Pairwise fold-rank Spearman correlations:

| estimator | target_type | count | min | median | max |
| --- | --- | --- | --- | --- | --- |
| AR | absolute_error_bps | 10 | 0.29697 | 0.721212 | 0.866667 |
| AR | signed_error_bps | 10 | 0.175758 | 0.581818 | 0.781818 |
| CS | absolute_error_bps | 10 | 0.248485 | 0.769697 | 0.927273 |
| CS | signed_error_bps | 10 | -0.0787879 | 0.454545 | 0.818182 |
| EDGE | absolute_error_bps | 10 | 0.539394 | 0.787879 | 0.963636 |
| EDGE | signed_error_bps | 10 | 0.430303 | 0.636364 | 1 |

Named +1 scheduled-observation LAG1 PLACEBO (positive pandas shift convention: past features moved to current target; never future features):

| estimator | target_type | N | MAE | RMSE | R2 | aligned_MAE | aligned_RMSE | aligned_R2 | RMSE_change_pct_vs_aligned |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AR | absolute_error_bps | 24377 | 126.158 | 212.514 | 0.098639 | 120.669 | 204.962 | 0.161561 | 3.68443 |
| AR | signed_error_bps | 24377 | 142.785 | 232.875 | 0.0329224 | 138.794 | 227.451 | 0.0774433 | 2.38448 |
| CS | absolute_error_bps | 24377 | 79.6007 | 133.393 | 0.3102 | 78.6235 | 133.899 | 0.304959 | -0.377733 |
| CS | signed_error_bps | 24377 | 87.1929 | 144.805 | 0.257318 | 86.8596 | 147.143 | 0.23314 | -1.58905 |
| EDGE | absolute_error_bps | 24377 | 47.2493 | 100.861 | 0.15624 | 45.213 | 95.7874 | 0.23899 | 5.29657 |
| EDGE | signed_error_bps | 24377 | 55.87 | 115.24 | 0.0682699 | 54.7189 | 112.231 | 0.116298 | 2.68147 |

Failed/infeasible folds: 0 of 60. Every failure remains in fold diagnostics and prediction rows with NaN predictions; pooled metrics explicitly count unavailable predictions. No failed fold is redesigned.

CV interpretation: the five test blocks partition 2,057 sorted unique common target dates, not stacked observations; all assets on a date stay together. The 1% embargo is ceil(0.01*2057)=21 subsequent unique target dates, truncated only at the calendar end. Purging uses the exact union of closed actual input intervals across all test assets, not an approximate hull. Purged and embargoed row counts are sequential/disjoint. Block cross-fitting can train on periods later than its test block: it is ex-post association analysis, not a forward trading forecast. No future-dated predictor is used.

The placebo keeps categorical labels unchanged and uses the immediately previous frozen scheduled source period, not a compressed previous common/available row. Missing prior features remain missing. Its information interval includes the lagged feature date, so AR can require additional purging while using identical test blocks and the same overlap/embargo rules. Feature medians and one-hot categories are refit on that variant training fold only. Numerical feature imputation is not imputation or repair of provider OHLCV. An entirely missing training feature would preserve a failed fold rather than invent a median.

Interpretation limits: daily range/open-close movement are ex-post same-day conditions. Price/volume units differ; asset and class identities are retained and volume has no common economic coefficient interpretation. 2024 tiers contain future information before 2024; this look-ahead/survivorship-style limitation remains. Asset identity importance reflects cross-asset heterogeneity, not causality. Correlated asset/class/tier and quality features can share/substitute importance; permutation creates combinations outside observed support. Benchmark-quality importance may reflect Roll proxy behavior. Futures and crypto share minute sources with their daily inputs; errors versus Roll are not ground-truth cost errors. Class calendars differ and futures are 2024 only. A positive R2 is diagnostic predictability, not economic usefulness. Lag persistence can sustain placebo predictability; no significance or optimized materiality cutoff is asserted. No feature/hyperparameter choice was changed from performance.

All Steps18/19 outputs and observation panels, frozen formulas/calendars/universes and all 11 Bloomberg hashes remain unchanged. No raw/minute rereads, new source, FX substitution, raw writes, error exclusions, winsorization or primary-result changes. Features, preprocessing records, exact training/test membership, fitted fold models and all observation predictions remain Git ignored. No README/design_decisions/data_manifest edits. Reproduce with `.venv/Scripts/python.exe -B src/cross_fitted_error_model.py --run-tests`.
