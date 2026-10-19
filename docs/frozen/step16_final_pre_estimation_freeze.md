# Step16 final pre-estimation statistical freeze

**FROZEN_FOR_PRIMARY_PROVIDER_RUN**.

Tests: 248 passed, 0 failed (PASSED). All 11 Bloomberg raw hashes match.

Primary summaries are ASSET-DAY WEIGHTED within overall, asset class, liquidity tier and class x tier cells. On the common-defined accuracy sample: BIAS=sum(error)/N; MAE=sum(abs(error))/N; RMSE=sqrt(sum(error^2)/N). Every contributing asset-day has equal weight. There is no market-cap, turnover, volume, rank, bar-count, inverse-variance or primary equal-asset weighting. Equal-asset summaries remain possible later robustness only.

Primary HAC inference applies to SIGNED ERROR / BIAS only. For each estimator/cell, first calculate daily mean error across contributing assets and n_t, then fit an intercept-only weighted regression with weights n_t. Its intercept equals the pooled asset-day-weighted mean. Use a Bartlett Newey-West sandwich and L=min(floor(4*(T/100)^(2/9)),T-1), with T the number of distinct contributing dates. Never select lags by residual results or significance. The covariance convention is explicitly uncorrected asymptotic (no hidden degrees-of-freedom multiplier); score g_t=n_t*u_t, bread=1/sum(n_t). Use a normal-reference 95% CI and two-sided normal-reference p-value against zero bias. These are prospective conventions, not calculations performed here.

The cross-section is summarized within date because assets may share market-wide shocks on that date. HAC then addresses serial autocorrelation across dates; n_t weights preserve the asset-day point estimand. This does not eliminate every possible form of panel dependence. Lags index sorted contributing dates, not stacked asset rows. No empty-date values are synthesized for inference and no estimator adjacency rule is changed. MAE and RMSE remain primary DESCRIPTIVE measures, with no separate primary significance test. Later reports must retain bias, HAC SE, 95% CI, two-sided p-value, T, N and L; empty/degenerate cells retain explicit undefined inference reasons.

Failure-rate denominator is ALL design_eligible asset-days. Negative-rate denominator is design-eligible observations with each method's finite computable RAW mathematical estimate; undefined is not negative. Negative-but-computable observations remain defined, including zero-floor outputs. Step14/15 definitions, windows and scheduled adjacency are unchanged.

IMDX remains the selected source-defined historical series. imdx_identity_continuity_certified=False; source_defined_history_retained_without_manual_stitching. No separate OCX stitching, historical replacement, drop or new failure flag. Saved reference fields provide current IMDX IDs but OCX identifiers remain source errors; full historical continuity is not independently certified. See imdx_identity_review.md.

FX remains IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS with no substitutes, under the existing student-supplied professor-approved policy. It does not block the four completed classes; no new FX methodology or access probe is needed here.

Step16 resolves the pending weighting, HAC convention and IMDX primary-treatment decisions. Step10--15 specifications, universes, tiers, exact primary calendars, raw data and README.md/design_decisions.md/data_manifest.csv remain unchanged. No provider price panels were read for this step. No provider CS/AR/EDGE, Roll, errors, rankings, HAC fits, standard errors, confidence intervals, p-values or hypothesis tests were computed. Tests use literal synthetic error arrays and count-only lag checks; no synthetic or provider HAC regression is executed. The freeze is not an automatic provider-run instruction. Reproduce with `.venv/Scripts/python.exe -B src/statistical_freeze.py --run-tests`.
