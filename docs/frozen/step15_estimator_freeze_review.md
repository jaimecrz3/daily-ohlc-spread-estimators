# Step 15 estimator mathematical and mapping freeze

**FROZEN_FOR_PROVIDER_ESTIMATION**.

Tests: 234 passed, 0 failed; status PASSED. Synthetic validation: 10 scalar checks passed. Official replication/equation oracle: 36 scalar checks passed. All 11 Bloomberg acquisition hashes match.

CS: official SAS additive overnight adjustment, beta SUM, gamma, alpha and nonlinear spread match an independent scalar equation transcription. SAS itself was not executed. The stable tanh/log-difference evaluation is algebraically identical. No author CRSP empirical repairs or ratio exclusion are imported into the frozen project preprocessing.

AR: hand-calculated eta and positive/negative Eq9 moments reconcile; Eq11 two-day zero-floor correction is primary. Empirical carry-forward is explicitly excluded.

EDGE: complete fixture 0.0101849034905478 and missing fixture 0.01013284969780197 match, along with all eight published scalar intermediates. The pinned official Python signed/absolute outputs also reconcile. The published JFE Section3.2 Eq26 zero floor is PRIMARY. The fixture convention is not silently adopted as the primary negative policy.

CS: **project** daily mapping is the mean of two separately zero-floored raw interval spreads on (t-1,t) and (t,t+1). Both are required. Author event-study evidence supports overlapping intervals; its special one-sided split-boundary exceptions are not used in this constant-horizon primary mapping. This is not an additional closed-form CS equation.

AR: the close-t two-day moment uses C_t, eta_t and eta_(t+1), assigned to t. C_(t+1) is not needed. No overnight adjustment or imputation.

EDGE: **project** centered minimum three-session sample (t-1,t,t+1), assigned to t; not an author window recommendation. It estimates an RMS spread over that sample, not exactly an instantaneous target-day spread. Ex-post measurement uses future session context and is not a forecasting signal. Longer windows remain unexecuted robustness candidates.

Stock/ETF scheduled periods come from the verified Step14 PRE-intersection source-date audit, not the class common calendar or successful observations. Futures use the frozen provider-mapped 2024 dates. Crypto expects every UTC calendar day. Full source context may supply neighbors outside an evaluation calendar, but scoring stays on frozen primary dates. Missing expected source rows break required windows; weekends/non-session dates absent from the verified equity grid do not. Unknown neighbors at reference-grid endpoints fail. No cross-asset or compressed-date lags.

Missing source rows are retained as NaN analysis-view placeholders only; no OHLC is invented. The general EDGE kernel reproduces author missing-value fixtures without dropping rows. Primary three-session dailyization requires three actual source rows and all its required OHLC; incomplete inputs remain undefined. CS/AR require only formula-used closes, H/L and their specific window, so missing unused opens or following close do not invalidate them.

The reference equity grid cannot certify a market-wide scheduled period absent from every supplied source. No external holiday rule is invented here. Existing futures root/session/contract construction remains unchanged; no continuous-contract fallback or new roll-day exclusion is introduced.


CS floors each finite raw interval at zero before the two-interval mean; its daily negative flag uses the mean of RAW intervals. Save both component flags and the negative-component count. AR floors its raw two-day s2 at zero before square root. EDGE primary uses the published paper Section3.2 Eq26 zero floor; the official package absolute root is only named robustness and replication evidence. No negative-but-computable value is an estimator failure.

Raw signed AR/EDGE diagnostics are sign(s2)*sqrt(abs(s2)); CS raw daily spread is the arithmetic mean of raw nonlinear interval spreads. CS raw_moment is mean component alpha for diagnostics only. Undefined estimates stay NaN, raw_negative is null and raw_computable is false; no undefined-to-zero conversion.

Failure rates retain ALL design-eligible asset-days as denominator. For each method, the negative-rate denominator is design-eligible days with that method's finite computable raw mathematical estimate; numerator additionally has raw_negative=True. Report the raw-computable denominator count. Never include missing/failed estimates as nonnegative estimates. No empirical rates were calculated here.

Zero-range treatment is method-specific: CS requires good positive-width ranges under its official good-range prerequisite; forbidden range-reset preprocessing is not substituted. AR theoretical Eq9 is computable with finite flat ranges and may equal zero; its empirical carry-forward is later robustness only. EDGE applies its own tau/po/pc requirements, not a blanket zero-range screen.

Failure reasons: missing_required_field, non_finite_price, non_positive_price, invalid_ohlc_order, zero_range_not_admissible, incomplete_estimator_window, invalid_scheduled_adjacency, missing_previous_scheduled_period, missing_next_scheduled_period, missing_target_scheduled_period, insufficient_edge_observations, insufficient_edge_tau, zero_edge_po, zero_edge_pc, non_finite_intermediate, non_finite_estimate.

All formulas and tests use only synthetic or author-simulated open fixtures. No selected-stock, ETF, futures or crypto provider estimator values, Roll values, errors, rankings, HAC statistics or hypothesis tests were calculated. Existing source errors and flags are not repaired. Raw files, Step10--Step14 specifications and README/design_decisions/data_manifest remain unchanged. docs/project_1.md and docs/project_1_details.md were both read before implementation.

Remaining before inference: HAC lag/dependence convention and summary weighting. Existing IMDX identity uncertainty, unknown abnormal-dividend setting, crypto formal quote currency and FX access limitations remain documented; no universe changes. Provider estimation requires a later explicit task and must retain Step14 exact calendars and failure denominators.

Sources: [Corwin official materials](https://sites.nd.edu/scorwin/research/), [Abdi--Ranaldo paper](https://academic.oup.com/rfs/article/30/12/4437/4047344), [EDGE published paper](https://doi.org/10.1016/j.jfineco.2024.103916), [official EDGE repository](https://github.com/eguidotti/bidask). Pinned source hashes and licenses are preserved in sources/source_manifest.json.
