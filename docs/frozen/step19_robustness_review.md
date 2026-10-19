# Step19 robustness and sensitivity

**ROBUSTNESS_SENSITIVITY_COMPLETE**. Tests: 304 passed; 0 failed.

Step18 remains the PRIMARY result, with exactly 24,377 common-defined asset-days, unchanged formulas, universes, calendars, sources, weighting, zero-floor conventions and benchmark. Every result below is ROBUSTNESS / SENSITIVITY or influence diagnosis only; no preferred alternative is selected.

Roll coverage uses the frozen regular session envelope: stocks/ETFs 390 slots, crypto 1,440 UTC slots, and root/date-specific futures sessions (1,380 slots for the selected 2024 dates). Coverage=roll_pairs/max(expected_minute_slots-2,1). These are clock-rule opportunities, not imputed observations or certified holiday/early-close schedules; short holiday sessions can have lower coverage. Only the two user-predeclared thresholds 0.25 and 0.50 were run.

R25/R50:

| variant | asset_class | liquidity_tier | estimator | N_asset_days | retention_pct | bias_bps | mae_bps | rmse_bps | mae_leader | rmse_leader |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Roll R25 | ALL | ALL | CS | 16150 | 66.251 | 127.838 | 133.889 | 218.853 | EDGE | EDGE |
| Roll R25 | ALL | ALL | AR | 16150 | 66.251 | 116.876 | 135.547 | 277.889 | EDGE | EDGE |
| Roll R25 | ALL | ALL | EDGE | 16150 | 66.251 | 27.9475 | 48.9537 | 121.109 | EDGE | EDGE |
| Roll R25 | crypto | ALL | CS | 7436 | 75.6614 | 188.359 | 196.648 | 283.022 | EDGE | EDGE |
| Roll R25 | crypto | ALL | AR | 7436 | 75.6614 | 150.174 | 176.366 | 319.539 | EDGE | EDGE |
| Roll R25 | crypto | ALL | EDGE | 7436 | 75.6614 | -1.63519 | 31.9118 | 68.7349 | EDGE | EDGE |
| Roll R25 | etfs | ALL | CS | 1151 | 36.252 | 27.6511 | 28.7525 | 47.647 | CS | CS |
| Roll R25 | etfs | ALL | AR | 1151 | 36.252 | 46.0897 | 48.5856 | 92.6972 | CS | CS |
| Roll R25 | etfs | ALL | EDGE | 1151 | 36.252 | 29.4824 | 31.5483 | 59.4467 | CS | CS |
| Roll R25 | futures | ALL | CS | 1667 | 100 | 23.0201 | 23.2345 | 36.6599 | EDGE | EDGE |
| Roll R25 | futures | ALL | AR | 1667 | 100 | 22.6575 | 23.3281 | 45.6823 | EDGE | EDGE |
| Roll R25 | futures | ALL | EDGE | 1667 | 100 | 4.68356 | 5.28744 | 11.0169 | EDGE | EDGE |
| Roll R25 | stocks | ALL | CS | 5896 | 60.7397 | 100.703 | 106.548 | 171.317 | EDGE | CS |
| Roll R25 | stocks | ALL | AR | 5896 | 60.7397 | 115.339 | 132.772 | 283.693 | EDGE | CS |
| Roll R25 | stocks | ALL | EDGE | 5896 | 60.7397 | 71.535 | 86.1905 | 183.013 | EDGE | CS |
| Roll R25 | ALL | HIGH | CS | 7883 | 82.5359 | 108.801 | 111.711 | 175.528 | EDGE | EDGE |
| Roll R25 | ALL | HIGH | AR | 7883 | 82.5359 | 105.987 | 114.873 | 223.942 | EDGE | EDGE |
| Roll R25 | ALL | HIGH | EDGE | 7883 | 82.5359 | 26.2858 | 35.6415 | 71.8443 | EDGE | EDGE |
| Roll R25 | ALL | LOW | CS | 1408 | 25.4796 | 135.775 | 147.303 | 250.537 | EDGE | EDGE |
| Roll R25 | ALL | LOW | AR | 1408 | 25.4796 | 120.245 | 151.845 | 326.802 | EDGE | EDGE |
| Roll R25 | ALL | LOW | EDGE | 1408 | 25.4796 | 31.937 | 68.1364 | 176.71 | EDGE | EDGE |
| Roll R25 | ALL | MEDIUM | CS | 6859 | 73.7527 | 148.088 | 156.624 | 253.931 | EDGE | EDGE |
| Roll R25 | ALL | MEDIUM | AR | 6859 | 73.7527 | 128.7 | 155.962 | 319.789 | EDGE | EDGE |
| Roll R25 | ALL | MEDIUM | EDGE | 6859 | 73.7527 | 29.0384 | 60.3154 | 148.975 | EDGE | EDGE |
| Roll R25 | crypto | HIGH | CS | 3605 | 97.1698 | 173.595 | 177.703 | 241.151 | EDGE | EDGE |
| Roll R25 | crypto | HIGH | AR | 3605 | 97.1698 | 146.211 | 159.851 | 288.559 | EDGE | EDGE |
| Roll R25 | crypto | HIGH | EDGE | 3605 | 97.1698 | 5.13293 | 20.6446 | 43.4975 | EDGE | EDGE |
| Roll R25 | crypto | LOW | CS | 469 | 20.4625 | 221.414 | 246.589 | 344.325 | EDGE | EDGE |
| Roll R25 | crypto | LOW | AR | 469 | 20.4625 | 159.358 | 221.601 | 362.578 | EDGE | EDGE |
| Roll R25 | crypto | LOW | EDGE | 469 | 20.4625 | -13.8974 | 67.8649 | 117.371 | EDGE | EDGE |
| Roll R25 | crypto | MEDIUM | CS | 3362 | 87.8725 | 199.579 | 209.995 | 313.481 | EDGE | EDGE |
| Roll R25 | crypto | MEDIUM | AR | 3362 | 87.8725 | 153.143 | 187.764 | 343.817 | EDGE | EDGE |
| Roll R25 | crypto | MEDIUM | EDGE | 3362 | 87.8725 | -7.18192 | 38.9779 | 80.6163 | EDGE | EDGE |
| Roll R25 | etfs | HIGH | CS | 1097 | 59.652 | 26.5801 | 27.6749 | 45.6001 | CS | CS |
| Roll R25 | etfs | HIGH | AR | 1097 | 59.652 | 44.0706 | 46.3024 | 84.8865 | CS | CS |
| Roll R25 | etfs | HIGH | EDGE | 1097 | 59.652 | 28.5505 | 30.4673 | 54.869 | CS | CS |
| Roll R25 | etfs | LOW | CS | 6 | 2.44898 | 10.2323 | 14.1468 | 15.3341 | EDGE | EDGE |
| Roll R25 | etfs | LOW | AR | 6 | 2.44898 | 12.2959 | 21.0174 | 28.5521 | EDGE | EDGE |
| Roll R25 | etfs | LOW | EDGE | 6 | 2.44898 | 8.22173 | 12.1362 | 15.0551 | EDGE | EDGE |
| Roll R25 | etfs | MEDIUM | CS | 48 | 4.39963 | 54.3038 | 55.2066 | 82.9865 | CS | CS |
| Roll R25 | etfs | MEDIUM | AR | 48 | 4.39963 | 96.4606 | 104.212 | 203.138 | CS | CS |
| Roll R25 | etfs | MEDIUM | EDGE | 48 | 4.39963 | 53.437 | 58.6816 | 126.122 | CS | CS |
| Roll R25 | futures | HIGH | CS | 521 | 100 | 21.1809 | 21.42 | 36.9044 | EDGE | EDGE |
| Roll R25 | futures | HIGH | AR | 521 | 100 | 20.6343 | 21.3073 | 43.4174 | EDGE | EDGE |
| Roll R25 | futures | HIGH | EDGE | 521 | 100 | 4.74777 | 5.33698 | 11.4586 | EDGE | EDGE |
| Roll R25 | futures | LOW | CS | 590 | 100 | 24.8373 | 25.062 | 40.1733 | EDGE | EDGE |
| Roll R25 | futures | LOW | AR | 590 | 100 | 23.9215 | 24.6519 | 50.6097 | EDGE | EDGE |
| Roll R25 | futures | LOW | EDGE | 590 | 100 | 4.51177 | 5.18961 | 10.8488 | EDGE | EDGE |
| Roll R25 | futures | MEDIUM | CS | 556 | 100 | 22.8152 | 22.9954 | 32.2591 | EDGE | EDGE |
| Roll R25 | futures | MEDIUM | AR | 556 | 100 | 23.212 | 23.817 | 42.1009 | EDGE | EDGE |
| Roll R25 | futures | MEDIUM | EDGE | 556 | 100 | 4.80569 | 5.34484 | 10.7688 | EDGE | EDGE |
| Roll R25 | stocks | HIGH | CS | 2660 | 76.4148 | 72.0578 | 74.6162 | 106.626 | EDGE | CS |
| Roll R25 | stocks | HIGH | AR | 2660 | 76.4148 | 93.7239 | 100.522 | 180.089 | EDGE | CS |
| Roll R25 | stocks | HIGH | EDGE | 2660 | 76.4148 | 58.238 | 64.0358 | 107.075 | EDGE | CS |
| Roll R25 | stocks | LOW | CS | 343 | 14.2976 | 211.701 | 224.143 | 304.584 | EDGE | CS |
| Roll R25 | stocks | LOW | AR | 343 | 14.2976 | 234.34 | 277.54 | 504.215 | EDGE | CS |
| Roll R25 | stocks | LOW | EDGE | 343 | 14.2976 | 142.198 | 177.763 | 330.363 | EDGE | CS |
| Roll R25 | stocks | MEDIUM | CS | 2893 | 75.5945 | 113.882 | 121.966 | 195.863 | EDGE | CS |
| Roll R25 | stocks | MEDIUM | AR | 2893 | 75.5945 | 121.103 | 145.26 | 322.585 | EDGE | CS |
| Roll R25 | stocks | MEDIUM | EDGE | 2893 | 75.5945 | 75.3831 | 95.7038 | 211.612 | EDGE | CS |
| Roll R50 | ALL | ALL | CS | 12908 | 52.9516 | 134.884 | 140.748 | 230.904 | EDGE | EDGE |
| Roll R50 | ALL | ALL | AR | 12908 | 52.9516 | 123.955 | 141.716 | 290.882 | EDGE | EDGE |
| Roll R50 | ALL | ALL | EDGE | 12908 | 52.9516 | 27.1062 | 47.7084 | 121.951 | EDGE | EDGE |
| Roll R50 | crypto | ALL | CS | 6399 | 65.1099 | 195.213 | 202.965 | 293.206 | EDGE | EDGE |
| Roll R50 | crypto | ALL | AR | 6399 | 65.1099 | 156.783 | 181.167 | 330.245 | EDGE | EDGE |
| Roll R50 | crypto | ALL | EDGE | 6399 | 65.1099 | -1.2175 | 30.5954 | 67.2312 | EDGE | EDGE |
| Roll R50 | etfs | ALL | CS | 732 | 23.0551 | 28.0497 | 29.1066 | 49.3112 | CS | CS |
| Roll R50 | etfs | ALL | AR | 732 | 23.0551 | 49.5939 | 51.7162 | 98.1028 | CS | CS |
| Roll R50 | etfs | ALL | EDGE | 732 | 23.0551 | 32.3077 | 34.1112 | 64.5474 | CS | CS |
| Roll R50 | futures | ALL | CS | 1652 | 99.1002 | 23.1732 | 23.3891 | 36.8188 | EDGE | EDGE |
| Roll R50 | futures | ALL | AR | 1652 | 99.1002 | 22.8073 | 23.4804 | 45.8797 | EDGE | EDGE |
| Roll R50 | futures | ALL | EDGE | 1652 | 99.1002 | 4.71124 | 5.31723 | 11.063 | EDGE | EDGE |
| Roll R50 | stocks | ALL | CS | 4125 | 42.4951 | 104.992 | 111.044 | 180.286 | EDGE | CS |
| Roll R50 | stocks | ALL | AR | 4125 | 42.4951 | 126.734 | 143.839 | 305.015 | EDGE | CS |
| Roll R50 | stocks | ALL | EDGE | 4125 | 42.4951 | 79.0897 | 93.6452 | 196.818 | EDGE | CS |
| Roll R50 | ALL | HIGH | CS | 7061 | 73.9294 | 116.222 | 119.167 | 183.722 | EDGE | EDGE |
| Roll R50 | ALL | HIGH | AR | 7061 | 73.9294 | 112.495 | 121.638 | 234.111 | EDGE | EDGE |
| Roll R50 | ALL | HIGH | EDGE | 7061 | 73.9294 | 26.0707 | 35.8594 | 73.2461 | EDGE | EDGE |
| Roll R50 | ALL | LOW | CS | 927 | 16.7752 | 119.557 | 126.423 | 248.463 | EDGE | EDGE |
| Roll R50 | ALL | LOW | AR | 927 | 16.7752 | 100.502 | 118.71 | 288.859 | EDGE | EDGE |
| Roll R50 | ALL | LOW | EDGE | 927 | 16.7752 | 21.0292 | 43.2006 | 131.074 | EDGE | EDGE |
| Roll R50 | ALL | MEDIUM | CS | 4920 | 52.9032 | 164.554 | 174.419 | 282.502 | EDGE | EDGE |
| Roll R50 | ALL | MEDIUM | AR | 4920 | 52.9032 | 144.821 | 174.865 | 357.221 | EDGE | EDGE |
| Roll R50 | ALL | MEDIUM | EDGE | 4920 | 52.9032 | 29.7372 | 65.5628 | 167.574 | EDGE | EDGE |
| Roll R50 | crypto | HIGH | CS | 3517 | 94.7978 | 175.208 | 179.26 | 242.968 | EDGE | EDGE |
| Roll R50 | crypto | HIGH | AR | 3517 | 94.7978 | 148.207 | 161.729 | 291.165 | EDGE | EDGE |
| Roll R50 | crypto | HIGH | EDGE | 3517 | 94.7978 | 4.95663 | 20.4747 | 43.4668 | EDGE | EDGE |
| Roll R50 | crypto | LOW | CS | 221 | 9.64223 | 296.144 | 318.42 | 427.898 | EDGE | EDGE |
| Roll R50 | crypto | LOW | AR | 221 | 9.64223 | 210.366 | 261.802 | 424.563 | EDGE | EDGE |
| Roll R50 | crypto | LOW | EDGE | 221 | 9.64223 | -12.8795 | 62.2328 | 102.775 | EDGE | EDGE |
| Roll R50 | crypto | MEDIUM | CS | 2661 | 69.5504 | 213.271 | 224.707 | 336.904 | EDGE | EDGE |
| Roll R50 | crypto | MEDIUM | AR | 2661 | 69.5504 | 163.668 | 200.161 | 367.756 | EDGE | EDGE |
| Roll R50 | crypto | MEDIUM | EDGE | 2661 | 69.5504 | -8.4092 | 41.3442 | 86.5741 | EDGE | EDGE |
| Roll R50 | etfs | HIGH | CS | 725 | 39.4236 | 27.7517 | 28.8188 | 48.415 | CS | CS |
| Roll R50 | etfs | HIGH | AR | 725 | 39.4236 | 48.4125 | 50.5253 | 92.4754 | CS | CS |
| Roll R50 | etfs | HIGH | EDGE | 725 | 39.4236 | 31.6831 | 33.469 | 60.306 | CS | CS |
| Roll R50 | etfs | LOW | CS | 0 | 0 |  |  |  | UNAVAILABLE | UNAVAILABLE |
| Roll R50 | etfs | LOW | AR | 0 | 0 |  |  |  | UNAVAILABLE | UNAVAILABLE |
| Roll R50 | etfs | LOW | EDGE | 0 | 0 |  |  |  | UNAVAILABLE | UNAVAILABLE |
| Roll R50 | etfs | MEDIUM | CS | 7 | 0.641613 | 58.9149 | 58.9149 | 107.252 | CS | CS |
| Roll R50 | etfs | MEDIUM | AR | 7 | 0.641613 | 171.951 | 175.056 | 347.419 | CS | CS |
| Roll R50 | etfs | MEDIUM | EDGE | 7 | 0.641613 | 96.9934 | 100.622 | 242.927 | CS | CS |
| Roll R50 | futures | HIGH | CS | 516 | 99.0403 | 21.3574 | 21.5974 | 37.0804 | EDGE | EDGE |
| Roll R50 | futures | HIGH | AR | 516 | 99.0403 | 20.782 | 21.4577 | 43.6206 | EDGE | EDGE |
| Roll R50 | futures | HIGH | EDGE | 516 | 99.0403 | 4.79329 | 5.38238 | 11.5138 | EDGE | EDGE |
| Roll R50 | futures | LOW | CS | 581 | 98.4746 | 25.1079 | 25.3362 | 40.4692 | EDGE | EDGE |
| Roll R50 | futures | LOW | AR | 581 | 98.4746 | 24.191 | 24.9259 | 50.9817 | EDGE | EDGE |
| Roll R50 | futures | LOW | EDGE | 581 | 98.4746 | 4.55336 | 5.23729 | 10.9265 | EDGE | EDGE |
| Roll R50 | futures | MEDIUM | CS | 555 | 99.8201 | 22.8361 | 23.0166 | 32.2846 | EDGE | EDGE |
| Roll R50 | futures | MEDIUM | AR | 555 | 99.8201 | 23.2417 | 23.8478 | 42.1378 | EDGE | EDGE |
| Roll R50 | futures | MEDIUM | EDGE | 555 | 99.8201 | 4.80022 | 5.34034 | 10.7734 | EDGE | EDGE |
| Roll R50 | stocks | HIGH | CS | 2303 | 66.1591 | 75.2471 | 77.7008 | 110.864 | EDGE | CS |
| Roll R50 | stocks | HIGH | AR | 2303 | 66.1591 | 98.6798 | 105.247 | 188.298 | EDGE | CS |
| Roll R50 | stocks | HIGH | EDGE | 2303 | 66.1591 | 61.3154 | 66.9351 | 111.307 | EDGE | CS |
| Roll R50 | stocks | LOW | CS | 125 | 5.2105 | 246.354 | 256.826 | 355.656 | EDGE | EDGE |
| Roll R50 | stocks | LOW | AR | 125 | 5.2105 | 260.955 | 301.63 | 536.674 | EDGE | EDGE |
| Roll R50 | stocks | LOW | EDGE | 125 | 5.2105 | 157.559 | 186.005 | 328.906 | EDGE | EDGE |
| Roll R50 | stocks | MEDIUM | CS | 1697 | 44.3428 | 134.947 | 145.555 | 230.239 | EDGE | CS |
| Roll R50 | stocks | MEDIUM | AR | 1697 | 44.3428 | 154.92 | 184.589 | 395.994 | EDGE | CS |
| Roll R50 | stocks | MEDIUM | EDGE | 1697 | 44.3428 | 97.4313 | 123.09 | 263.4 | EDGE | CS |

Equal-asset weighting:

| asset_class | estimator | N_asset_days | N_assets | bias_bps | mae_bps | rmse_bps | mae_leader | rmse_leader |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | CS | 24377 | 36 | 74.2158 | 83.9461 | 158.987 | EDGE | EDGE |
| ALL | AR | 24377 | 36 | 72.0686 | 92.9259 | 207.371 | EDGE | EDGE |
| ALL | EDGE | 24377 | 36 | 20.3284 | 41.7111 | 102.463 | EDGE | EDGE |
| crypto | CS | 9828 | 9 | 163.53 | 182.257 | 265.416 | EDGE | EDGE |
| crypto | AR | 9828 | 9 | 132.791 | 174.118 | 308.761 | EDGE | EDGE |
| crypto | EDGE | 9828 | 9 | -2.48883 | 45.2221 | 101.931 | EDGE | EDGE |
| etfs | CS | 3175 | 9 | 18.29 | 24.8468 | 46.7041 | CS | CS |
| etfs | AR | 3175 | 9 | 32.7882 | 42.6147 | 87.8795 | CS | CS |
| etfs | EDGE | 3175 | 9 | 22.5709 | 30.8852 | 60.5998 | CS | CS |
| futures | CS | 1667 | 9 | 24.6522 | 24.8791 | 39.0331 | EDGE | EDGE |
| futures | AR | 1667 | 9 | 24.3341 | 25.0312 | 48.5212 | EDGE | EDGE |
| futures | EDGE | 1667 | 9 | 5.04635 | 5.66734 | 11.6939 | EDGE | EDGE |
| stocks | CS | 9707 | 9 | 90.3911 | 103.801 | 164.185 | EDGE | CS |
| stocks | AR | 9707 | 9 | 98.3613 | 129.94 | 258.071 | EDGE | CS |
| stocks | EDGE | 9707 | 9 | 56.1852 | 85.0698 | 166.721 | EDGE | CS |

Bloomberg unadjusted matched comparison:

| asset_class | estimator | N_asset_days | bias_bps | mae_bps | rmse_bps | mae_bps_adjusted_matched | rmse_bps_adjusted_matched | delta_mae_bps_vs_adjusted_matched | delta_rmse_bps_vs_adjusted_matched | mae_leader | rmse_leader |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| etfs | CS | 3175 | 20.4264 | 24.6803 | 45.9501 | 24.7442 | 45.9835 | -0.0639413 | -0.0333968 | CS | CS |
| etfs | AR | 3175 | 35.2927 | 42.3481 | 87.0336 | 42.0797 | 85.7013 | 0.268422 | 1.33231 | CS | CS |
| etfs | EDGE | 3175 | 24.0738 | 29.9024 | 59.1902 | 29.6631 | 58.3753 | 0.239266 | 0.81492 | CS | CS |
| stocks | CS | 9705 | 93.0162 | 104.564 | 166.387 | 104.598 | 166.412 | -0.0336805 | -0.0251599 | EDGE | CS |
| stocks | AR | 9705 | 101.002 | 129.606 | 269.054 | 129.028 | 262.075 | 0.577866 | 6.97846 | EDGE | CS |
| stocks | EDGE | 9705 | 58.9417 | 84.7177 | 170.996 | 84.6199 | 170.689 | 0.0977851 | 0.307139 | EDGE | CS |

EDGE abs-root:

| variant | asset_class | estimator | N_asset_days | bias_bps | mae_bps | rmse_bps |
| --- | --- | --- | --- | --- | --- | --- |
| EDGE abs-root | ALL | CS | 24377 | 110.8 | 121.304 | 201.272 |
| EDGE abs-root | ALL | AR | 24377 | 101.675 | 127.712 | 257.71 |
| EDGE abs-root | ALL | EDGE | 24377 | 56.0932 | 69.2674 | 137.179 |
| EDGE abs-root | crypto | CS | 9828 | 172.344 | 185.612 | 268.726 |
| EDGE abs-root | crypto | AR | 9828 | 137.796 | 171.746 | 306.83 |
| EDGE abs-root | crypto | EDGE | 9828 | 19.5319 | 43.7416 | 83.8321 |
| EDGE abs-root | etfs | CS | 3175 | 20.475 | 24.7442 | 45.9835 |
| EDGE abs-root | etfs | AR | 3175 | 35.0414 | 42.0797 | 85.7013 |
| EDGE abs-root | etfs | EDGE | 3175 | 43.1696 | 44.3633 | 71.3435 |
| EDGE abs-root | futures | CS | 1667 | 23.0201 | 23.2345 | 36.6599 |
| EDGE abs-root | futures | AR | 1667 | 22.6575 | 23.3281 | 45.6823 |
| EDGE abs-root | futures | EDGE | 1667 | 7.85564 | 7.9142 | 14.2609 |
| EDGE abs-root | stocks | CS | 9707 | 93.1087 | 104.619 | 166.422 |
| EDGE abs-root | stocks | AR | 9707 | 100.469 | 129.064 | 262.119 |
| EDGE abs-root | stocks | EDGE | 9707 | 105.621 | 113.793 | 196.067 |

Leave-one-asset-out range and largest changes:

| asset_class | estimator | mae_min_bps | mae_max_bps | rmse_min_bps | rmse_max_bps | mae_leader_ever_changes | rmse_leader_ever_changes | largest_mae_change_asset | largest_rmse_change_asset |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| crypto | AR | 164.074 | 175.062 | 291.045 | 312.814 | False | False | ZEC | ZEC |
| crypto | CS | 176.959 | 188.018 | 247.38 | 274.401 | False | False | ZEC | ZEC |
| crypto | EDGE | 35.311 | 41.9581 | 75.8262 | 89.3478 | False | False | ZEC | ICX |
| etfs | AR | 35.3249 | 50.0637 | 70.8758 | 96.467 | False | False | SPBO | PGJ |
| etfs | CS | 21.5687 | 29.6 | 41.0489 | 51.8923 | False | False | SPBO | SPBO |
| etfs | EDGE | 25.3624 | 35.1209 | 50.2981 | 65.571 | False | False | SPBO | PGJ |
| futures | AR | 20.0418 | 25.6413 | 38.1423 | 48.886 | False | False | HG | HG |
| futures | CS | 20.0453 | 25.5993 | 30.9797 | 39.2394 | False | False | HG | HG |
| futures | EDGE | 4.65777 | 5.77213 | 9.75634 | 11.7561 | False | False | HG | HG |
| stocks | AR | 114.757 | 139.152 | 223.474 | 277.554 | False | True | IMDX | SNDL |
| stocks | CS | 91.9768 | 112.577 | 146.307 | 176.117 | False | True | IMDX | IMDX |
| stocks | EDGE | 74.2335 | 91.5197 | 141.451 | 180.965 | False | True | IMDX | SNDL |

Single extreme observation influence:

| asset_class | estimator | removed_N | mae_pct_change | rmse_pct_change |
| --- | --- | --- | --- | --- |
| crypto | CS | 1 | -0.14093 | -0.531568 |
| crypto | AR | 1 | -0.245682 | -1.00777 |
| crypto | EDGE | 1 | -0.747419 | -6.15901 |
| etfs | CS | 1 | -0.971648 | -4.72004 |
| etfs | AR | 1 | -0.635581 | -1.70132 |
| etfs | EDGE | 1 | -0.673362 | -2.04103 |
| futures | CS | 1 | -0.677153 | -1.8046 |
| futures | AR | 1 | -0.863299 | -1.83879 |
| futures | EDGE | 1 | -1.07999 | -2.49477 |
| stocks | CS | 1 | -0.290165 | -1.74146 |
| stocks | AR | 1 | -0.757337 | -7.18629 |
| stocks | EDGE | 1 | -0.549078 | -3.7986 |

R25/R50 class/tier composition is reported in roll_quality_sensitivity.csv, including empty cells. Equal-asset RMSE is sqrt(mean(asset mean squared error)), never mean(asset RMSE). Each contributing asset has equal total weight within its reporting cell; the same 24,377 primary rows are used.

Unadjusted uses existing acquired Bloomberg CapChg=F/CshAdjNormal=F/CshAdjAbnormal=F, exact Step15 kernels and scheduled context. The saved verified SNDL 2022-07-26 incoming split edge breaks only windows that cross it (CS/EDGE previous-target-next; AR target-next); this does not drop SNDL as an asset or its event month. All 61 heuristic flags remain diagnostic. The prescribed unadjusted-common sample and availability of adjusted outputs on every one of those rows are explicitly checked. Adjusted/unadjusted columns share identical target rows and Roll values; matched adjusted metrics and unadjusted-minus-matched deltas distinguish source changes from sample changes.

EDGE abs-root is sqrt(abs(raw s2)), on the same primary common observations; finite negative raw values are not failures. CS/AR remain unchanged for the alternative-convention ranking. Primary EDGE stays the published zero floor.

Leader stability (separate MAE and RMSE, no composite or significance claim):

| variant | asset_class | N_asset_days | mae_leader | rmse_leader | qualitative_change_from_primary |
| --- | --- | --- | --- | --- | --- |
| Primary | ALL | 24377 | EDGE | EDGE | False |
| Primary | crypto | 9828 | EDGE | EDGE | False |
| Primary | etfs | 3175 | CS | CS | False |
| Primary | futures | 1667 | EDGE | EDGE | False |
| Primary | stocks | 9707 | EDGE | CS | False |
| Roll R25 | ALL | 16150 | EDGE | EDGE | False |
| Roll R25 | crypto | 7436 | EDGE | EDGE | False |
| Roll R25 | etfs | 1151 | CS | CS | False |
| Roll R25 | futures | 1667 | EDGE | EDGE | False |
| Roll R25 | stocks | 5896 | EDGE | CS | False |
| Roll R50 | ALL | 12908 | EDGE | EDGE | False |
| Roll R50 | crypto | 6399 | EDGE | EDGE | False |
| Roll R50 | etfs | 732 | CS | CS | False |
| Roll R50 | futures | 1652 | EDGE | EDGE | False |
| Roll R50 | stocks | 4125 | EDGE | CS | False |
| Equal asset weighting | ALL | 24377 | EDGE | EDGE | False |
| Equal asset weighting | crypto | 9828 | EDGE | EDGE | False |
| Equal asset weighting | etfs | 3175 | CS | CS | False |
| Equal asset weighting | futures | 1667 | EDGE | EDGE | False |
| Equal asset weighting | stocks | 9707 | EDGE | CS | False |
| Bloomberg unadjusted | etfs | 3175 | CS | CS | False |
| Bloomberg unadjusted | stocks | 9705 | EDGE | CS | False |
| EDGE abs-root | ALL | 24377 | EDGE | EDGE | False |
| EDGE abs-root | crypto | 9828 | EDGE | EDGE | False |
| EDGE abs-root | etfs | 3175 | CS | CS | False |
| EDGE abs-root | futures | 1667 | EDGE | EDGE | False |
| EDGE abs-root | stocks | 9707 | CS | CS | True |

Original hypotheses are retained in hypothesis_robustness_tracking.csv. H1 accuracy is assessed separately by metric/cell. H2 raw-negative rates are not redefined by conditioning on common/quality samples or by equal weighting; Step18 rates and class exceptions remain the primary evidence. The additional unadjusted_raw_negative_rates.csv applies the same design/finite-raw denominator rule to source-specific outcomes; these rates are not computed on the unadjusted common accuracy sample. H3 uses prespecified LOW CS bias and retains the direction even if contrary. H4 orders are recorded separately by class/metric; two-class unadjusted comparisons cannot certify four-class stability. H5 levels are shown without equating liquidity with small capitalization.

Leave-one-asset-out removes each of the nine selected assets in turn within its class, with no other exclusions, and retains unchanged frozen errors for all others. Extremes remove exactly one maximal-absolute-error row per class/method (ties asset/date alphabetically/chronologically) only to diagnose influence. Detailed keys stay in ignored data/analytic/robustness; no trimmed primary panel was produced. These checks identify fragility, not an alternative preferred universe.

All 11 Bloomberg hashes match. Primary and frozen artifacts are locked by SHA-256 before/after. No raw writes, new intraday reads, filling, synthetic days, winsorization, threshold search, FX substitutes, cross-fitted model or new HAC tests. Relative units reconcile to bps. All observation-level robustness evidence is Git ignored. Reproduce with `.venv/Scripts/python.exe -B src/primary_robustness.py --run-tests`.
