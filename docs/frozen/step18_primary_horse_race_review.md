# Step18 primary horse race

**PRIMARY_HORSE_RACE_COMPLETE**. Tests: 289 passed; 0 failed.

All 24,377 frozen common-defined asset-days retained for every estimator. Stocks 9,707; ETFs 3,175; futures 1,667; crypto 9,828. Equal contributing asset-day weights; no post-hoc exclusions or new quality thresholds. Errors are estimator minus Roll. Headline units are bps. Relative units remain in the machine-readable results.

Overall signed-bias inference and descriptive accuracy:

| estimator | bias_bps | hac_se_bps | ci95_low_bps | ci95_high_bps | p_value_two_sided | mae_bps | rmse_bps | N_asset_days |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CS | 110.8 | 2.94268 | 105.033 | 116.568 | 2.93374e-310 | 121.304 | 201.272 | 24377 |
| AR | 101.675 | 3.27072 | 95.2646 | 108.086 | 3.67449e-212 | 127.712 | 257.71 | 24377 |
| EDGE | 25.9871 | 1.81557 | 22.4287 | 29.5456 | 1.80204e-46 | 53.5921 | 122.183 | 24377 |

Asset class accuracy (MAE/RMSE descriptive; no significance tests):

| asset_class | liquidity_tier | estimator | N_asset_days | mae_bps | rmse_bps |
| --- | --- | --- | --- | --- | --- |
| crypto | ALL | CS | 9828 | 185.612 | 268.726 |
| crypto | ALL | AR | 9828 | 171.746 | 306.83 |
| crypto | ALL | EDGE | 9828 | 38.8849 | 84.4821 |
| etfs | ALL | CS | 3175 | 24.7442 | 45.9835 |
| etfs | ALL | AR | 3175 | 42.0797 | 85.7013 |
| etfs | ALL | EDGE | 3175 | 29.6631 | 58.3753 |
| futures | ALL | CS | 1667 | 23.2345 | 36.6599 |
| futures | ALL | AR | 1667 | 23.3281 | 45.6823 |
| futures | ALL | EDGE | 1667 | 5.28744 | 11.0169 |
| stocks | ALL | CS | 9707 | 104.619 | 166.422 |
| stocks | ALL | AR | 9707 | 129.064 | 262.119 |
| stocks | ALL | EDGE | 9707 | 84.605 | 170.671 |

Liquidity tier accuracy (MAE/RMSE descriptive; no significance tests):

| asset_class | liquidity_tier | estimator | N_asset_days | mae_bps | rmse_bps |
| --- | --- | --- | --- | --- | --- |
| ALL | HIGH | CS | 9551 | 98.8895 | 162.886 |
| ALL | HIGH | AR | 9551 | 102.464 | 207.832 |
| ALL | HIGH | EDGE | 9551 | 33.6542 | 67.6997 |
| ALL | LOW | CS | 5526 | 135.751 | 213.878 |
| ALL | LOW | AR | 5526 | 154.699 | 283.273 |
| ALL | LOW | EDGE | 5526 | 83.3479 | 164.847 |
| ALL | MEDIUM | CS | 9300 | 135.74 | 227.5 |
| ALL | MEDIUM | AR | 9300 | 137.605 | 286.435 |
| ALL | MEDIUM | EDGE | 9300 | 56.3874 | 135.193 |

Class x tier accuracy (MAE/RMSE descriptive; no significance tests):

| asset_class | liquidity_tier | estimator | N_asset_days | mae_bps | rmse_bps |
| --- | --- | --- | --- | --- | --- |
| crypto | HIGH | CS | 3710 | 178.015 | 241.952 |
| crypto | HIGH | AR | 3710 | 161.052 | 289.898 |
| crypto | HIGH | EDGE | 3710 | 21.6434 | 45.5979 |
| crypto | LOW | CS | 2292 | 165.491 | 245.995 |
| crypto | LOW | AR | 2292 | 167.391 | 283.949 |
| crypto | LOW | EDGE | 2292 | 65.4078 | 128.558 |
| crypto | MEDIUM | CS | 3826 | 205.033 | 304.107 |
| crypto | MEDIUM | AR | 3826 | 184.725 | 334.724 |
| crypto | MEDIUM | EDGE | 3826 | 39.7147 | 80.1045 |
| etfs | HIGH | CS | 1839 | 20.6074 | 36.5123 |
| etfs | HIGH | AR | 1839 | 34.634 | 68.2406 |
| etfs | HIGH | EDGE | 1839 | 23.2857 | 44.4915 |
| etfs | LOW | CS | 245 | 22.6118 | 41.3397 |
| etfs | LOW | AR | 245 | 40.6801 | 78.2687 |
| etfs | LOW | EDGE | 245 | 31.3118 | 58.0652 |
| etfs | MEDIUM | CS | 1091 | 32.1962 | 59.3513 |
| etfs | MEDIUM | AR | 1091 | 54.9446 | 110.223 |
| etfs | MEDIUM | EDGE | 1091 | 40.0426 | 76.3095 |
| futures | HIGH | CS | 521 | 21.42 | 36.9044 |
| futures | HIGH | AR | 521 | 21.3073 | 43.4174 |
| futures | HIGH | EDGE | 521 | 5.33698 | 11.4586 |
| futures | LOW | CS | 590 | 25.062 | 40.1733 |
| futures | LOW | AR | 590 | 24.6519 | 50.6097 |
| futures | LOW | EDGE | 590 | 5.18961 | 10.8488 |
| futures | MEDIUM | CS | 556 | 22.9954 | 32.2591 |
| futures | MEDIUM | AR | 556 | 23.817 | 42.1009 |
| futures | MEDIUM | EDGE | 556 | 5.34484 | 10.7688 |
| stocks | HIGH | CS | 3481 | 67.5093 | 97.4521 |
| stocks | HIGH | AR | 3481 | 88.0038 | 161.868 |
| stocks | HIGH | EDGE | 3481 | 56.171 | 96.4051 |
| stocks | LOW | CS | 2399 | 146.114 | 216.756 |
| stocks | LOW | AR | 2399 | 186.202 | 326.421 |
| stocks | LOW | EDGE | 2399 | 125.024 | 215.481 |
| stocks | MEDIUM | CS | 3827 | 112.363 | 179.333 |
| stocks | MEDIUM | AR | 3827 | 130.593 | 289.215 |
| stocks | MEDIUM | EDGE | 3827 | 85.1311 | 190.587 |

Failure rates (denominator ALL design-eligible rows; overall 38,232):

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

Raw-negative rates (finite computable raw estimates, independent of common sample):

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

Separate descriptive ranks; no composite or averaged ranking:

| reporting_scope | asset_class | liquidity_tier | estimator | mae_rank | rmse_rank | absolute_bias_rank | accuracy_leader_status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| overall | ALL | ALL | CS | 2 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| overall | ALL | ALL | AR | 3 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| overall | ALL | ALL | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class | crypto | ALL | CS | 3 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class | crypto | ALL | AR | 2 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class | crypto | ALL | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class | etfs | ALL | CS | 1 | 1 | 1 | DESCRIPTIVE_LEADER: CS |
| asset_class | etfs | ALL | AR | 3 | 3 | 3 | DESCRIPTIVE_LEADER: CS |
| asset_class | etfs | ALL | EDGE | 2 | 2 | 2 | DESCRIPTIVE_LEADER: CS |
| asset_class | futures | ALL | CS | 2 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class | futures | ALL | AR | 3 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class | futures | ALL | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class | stocks | ALL | CS | 2 | 1 | 2 | MIXED |
| asset_class | stocks | ALL | AR | 3 | 3 | 3 | MIXED |
| asset_class | stocks | ALL | EDGE | 1 | 2 | 1 | MIXED |
| liquidity_tier | ALL | HIGH | CS | 2 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| liquidity_tier | ALL | HIGH | AR | 3 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| liquidity_tier | ALL | HIGH | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| liquidity_tier | ALL | LOW | CS | 2 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| liquidity_tier | ALL | LOW | AR | 3 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| liquidity_tier | ALL | LOW | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| liquidity_tier | ALL | MEDIUM | CS | 2 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| liquidity_tier | ALL | MEDIUM | AR | 3 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| liquidity_tier | ALL | MEDIUM | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | HIGH | CS | 3 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | HIGH | AR | 2 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | HIGH | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | LOW | CS | 2 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | LOW | AR | 3 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | LOW | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | MEDIUM | CS | 3 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | MEDIUM | AR | 2 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | crypto | MEDIUM | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | etfs | HIGH | CS | 1 | 1 | 1 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | etfs | HIGH | AR | 3 | 3 | 3 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | etfs | HIGH | EDGE | 2 | 2 | 2 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | etfs | LOW | CS | 1 | 1 | 1 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | etfs | LOW | AR | 3 | 3 | 3 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | etfs | LOW | EDGE | 2 | 2 | 2 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | etfs | MEDIUM | CS | 1 | 1 | 1 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | etfs | MEDIUM | AR | 3 | 3 | 3 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | etfs | MEDIUM | EDGE | 2 | 2 | 2 | DESCRIPTIVE_LEADER: CS |
| asset_class_x_tier | futures | HIGH | CS | 3 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | futures | HIGH | AR | 2 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | futures | HIGH | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | futures | LOW | CS | 3 | 2 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | futures | LOW | AR | 2 | 3 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | futures | LOW | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | futures | MEDIUM | CS | 2 | 2 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | futures | MEDIUM | AR | 3 | 3 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | futures | MEDIUM | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | stocks | HIGH | CS | 2 | 2 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | stocks | HIGH | AR | 3 | 3 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | stocks | HIGH | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | stocks | LOW | CS | 2 | 2 | 2 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | stocks | LOW | AR | 3 | 3 | 3 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | stocks | LOW | EDGE | 1 | 1 | 1 | DESCRIPTIVE_LEADER: EDGE |
| asset_class_x_tier | stocks | MEDIUM | CS | 2 | 1 | 2 | MIXED |
| asset_class_x_tier | stocks | MEDIUM | AR | 3 | 3 | 3 | MIXED |
| asset_class_x_tier | stocks | MEDIUM | EDGE | 1 | 2 | 1 | MIXED |

CS signed bias by class/tier, including prespecified LOW and MEDIUM/HIGH context:

| asset_class | liquidity_tier | bias_bps | hac_se_bps | ci95_low_bps | ci95_high_bps | p_value_two_sided |
| --- | --- | --- | --- | --- | --- | --- |
| crypto | HIGH | 173.749 | 5.74413 | 162.49 | 185.007 | 5.53104e-201 |
| crypto | LOW | 133.145 | 8.10151 | 117.266 | 149.024 | 1.08152e-60 |
| crypto | MEDIUM | 194.463 | 8.7314 | 177.35 | 211.577 | 6.94844e-110 |
| etfs | HIGH | 19.4202 | 1.0922 | 17.2795 | 21.5609 | 9.96485e-71 |
| etfs | LOW | 11.6106 | 3.48368 | 4.78268 | 18.4384 | 0.000859629 |
| etfs | MEDIUM | 24.2436 | 2.52683 | 19.2911 | 29.196 | 8.4353e-22 |
| futures | HIGH | 21.1809 | 1.72613 | 17.7977 | 24.564 | 1.30092e-34 |
| futures | LOW | 24.8373 | 1.4936 | 21.9099 | 27.7647 | 4.28625e-62 |
| futures | MEDIUM | 22.8152 | 1.51121 | 19.8533 | 25.7772 | 1.6863e-51 |
| stocks | HIGH | 64.8444 | 2.27062 | 60.3941 | 69.2947 | 2.23311e-179 |
| stocks | LOW | 114.652 | 5.87347 | 103.14 | 126.164 | 7.37316e-85 |
| stocks | MEDIUM | 105.313 | 3.8029 | 97.8592 | 112.766 | 8.53315e-169 |

H1: EDGE lowest overall MAE=True; lowest overall RMSE=True. Class and class/tier components are retained separately in hypothesis_evidence.csv; no forced binary project-wide conclusion.

H2: Overall lowest raw-negative rate: EDGE. Class results and exact denominators are reported above.

H3: LOW CS bias signs: crypto=133.145 bps, etfs=11.6106 bps, futures=24.8373 bps, stocks=114.652 bps. CIs above concern signed bias against zero, not causal effects or estimator-difference tests.

H4: Separate class orders (ties explicit):

| component | asset_class | estimator_order | identical_order_across_classes |
| --- | --- | --- | --- |
| MAE order | crypto | EDGE < AR < CS | False |
| MAE order | etfs | CS < EDGE < AR | False |
| MAE order | futures | EDGE < CS < AR | False |
| MAE order | stocks | EDGE < CS < AR | False |
| RMSE order | crypto | EDGE < CS < AR | False |
| RMSE order | etfs | CS < EDGE < AR | False |
| RMSE order | futures | EDGE < CS < AR | False |
| RMSE order | stocks | CS < EDGE < AR | False |

H5: Levels by class and tier are reported without reclassifying thinness or claiming market-wide/small-cap representativeness. The sampled equity tiers measure 2024 liquidity, not a frozen market-cap classification.

Extreme finite errors were retained. The largest absolute error per class/method was inspected descriptively; observation-level keys/values and squared-error contributions are saved only in ignored data/analytic/primary_horse_race_extremes.json. These are maxima inspections, not influence-removal tests.

| asset_class | estimator | max_absolute_error_bps | largest_squared_error_share | removed_N |
| --- | --- | --- | --- | --- |
| crypto | CS | 2756.2 | 0.0107038 | 0 |
| crypto | AR | 4318.25 | 0.0201536 | 0 |
| crypto | EDGE | 2894.93 | 0.119477 | 0 |
| etfs | CS | 787.859 | 0.0924589 | 0 |
| etfs | AR | 890.968 | 0.0340413 | 0 |
| etfs | EDGE | 663.638 | 0.0407062 | 0 |
| futures | CS | 285.351 | 0.0363447 | 0 |
| futures | AR | 358.846 | 0.0370157 | 0 |
| futures | EDGE | 100.422 | 0.0498434 | 0 |
| stocks | CS | 3051.06 | 0.0346253 | 0 |
| stocks | AR | 9616.16 | 0.13865 | 0 |
| stocks | EDGE | 4593.5 | 0.0746245 | 0 |

Deterministic error reproductions (no replacement when not common-defined):

| asset_class | asset | target_date | common_defined | audit_status |
| --- | --- | --- | --- | --- |
| stocks | FCPT | 2022-10-11 | False | NOT_COMMON_DEFINED_NOT_REPLACED |
| etfs | PGJ | 2024-01-30 | True | PASSED |
| futures | GC | 2024-07-02 | True | PASSED |
| crypto | LINK | 2024-01-18 | True | PASSED |
| stocks | AIRG | 2022-10-11 | True | PASSED |

HAC is signed-bias only: chronological contributing-date means, WLS count weights n_t, Bartlett L=min(floor(4*(T/100)^(2/9)),T-1), no small-sample multiplier (False, already frozen in Step16), normal 95% CI and two-sided p-value. The WLS intercept reconciles to pooled asset-day bias in every cell. No empty dates inserted. Degenerate cells retain undefined inference reasons. Rankings are descriptive with ties; no statistical superiority test for MAE/RMSE.

Limitations: Roll is a sampled transaction-close proxy, not true effective cost; sparse sessions and the minimum two covariance pairs affect precision. Common-defined conditioning may select observations economically. Overall/class comparisons have unequal calendar support and asset-day composition. Futures primary support is 2024 only, the calibration year; tiers use ex-post 2024 information for pre-2024 observations. Futures/crypto share minute sources across daily estimators and Roll. Crypto quote currency UNKNOWN; dimensionless/bps outputs do not imply USD. Bloomberg abnormal-dividend setting UNKNOWN and EOD/RTH equivalence uncertified; IMDX continuity remains uncertified with no OCX stitching. FX remains IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS; no substitute. HAC handles the frozen aggregate-date dependence convention, not all forms of panel dependence. Multiple bias tests are nominal and unadjusted; no new multiplicity convention imposed.

All 11 Bloomberg hashes and prior frozen formulas/calendars/universes/specifications checked unchanged. No raw files were rewritten or price estimates recalculated. Observation-level errors, daily HAC inputs and reproduction details are Git ignored. No winsorization, trimming, robustness runs, hypothesis rewriting or post-hoc exclusions. Reproduce with `.venv/Scripts/python.exe -B src/primary_horse_race.py --run-tests`.
