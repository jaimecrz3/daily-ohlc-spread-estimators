# Step 10.2.1 approved daily OHLC input convention

The daily input convention is frozen by the user's Step 10.2.1 approval: existing Bloomberg adjusted OHLC is the common primary source for CS, AR and EDGE; existing unadjusted Bloomberg is robustness only. The final machine-readable artifact is daily_input_final_spec.yaml. This applies to the 18 selected stocks/ETFs. No estimator implementation or results were used to select it. Step 10.2's automatic exclusions at 61 heuristic flags are corrected: primary event breaks require independent verification AND methodological necessity.

## 1. Explicit original-source and official implementation rules

The machine-readable estimator_source_method_review.csv records each field requirement, adjacent-date dependence, missing/zero-range/overnight/negative treatment, corporate-action evidence, source location and silence. These author choices are recorded without automatically adopting them.

Corwin–Schultz derive the estimator from one- and two-day high/low ranges. Their official sample specifies **split-adjusted H/L/C**, prior-range replacement for bad/missing/zero-range data, a prior-close overnight correction, negative two-day zero correction, and at least 12 monthly observations. The range-shifting overnight correction is different from vendor corporate-action adjustment. No Bloomberg normal/abnormal-dividend settings are prescribed. Publisher full text could not be accessed; these preprocessing details were checked directly in the original internet appendix and official author implementation. [Paper](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2012.01729.x), [author program description](https://sites.nd.edu/scorwin/files/2019/08/Sample-SAS-Program-Description.pdf), [sample program](https://sites.nd.edu/scorwin/files/2024/05/High_Low_Spread_Estimator_SAS_sample.pdf), [original appendix](https://sites.nd.edu/scorwin/files/2019/11/Internet-Appendix_FINAL.pdf).

Abdi–Ranaldo use adjacent-day close/high/low inputs. Their empirical section carries prior prices on nontrading/zero-range days, uses two-day negative correction, and **discards stock-months containing splits or enormous distributions**; their HL comparator uses CS overnight and two-day corrections. Simulations instead discard nontrading/zero-range two-day inputs. Their model handles nontrading-period movement without CHL overnight shifting. They do not prescribe Bloomberg adjusted versus unadjusted settings. [Published article, sections 1–3](https://academic.oup.com/rfs/article/30/12/4437/4047344).

EDGE combines OHLC with lagged previous-period prices and close-to-open components. Its paper removes missing H/L/C or malformed empirical daily rows. The official implementation supports NaNs without compressing the grid; its FAQ recommends regular spacing and discusses absolute/signed outputs. Its zero-activity/probability checks can yield undefined output. Neither reviewed paper nor implementation establishes a split/dividend vendor convention. No corporate-action rule is inferred from that silence. [Paper, sections 3 and 5.1](https://irf.fhnw.ch/bitstreams/e8c469d2-9c64-4004-8e87-53ee091f0cb1/download), [official FAQ](https://github.com/eguidotti/bidask), [official implementation](https://raw.githubusercontent.com/eguidotti/bidask/main/python/bidask/edge.py). The empirical paper and current implementation are distinct evidence, particularly for missingness.

## 2. Facts from existing Bloomberg acquisition

All raw files remain in their finalized manifest paths. Formula lineage is evidence only; immutable values-only acquisitions provide prices. Unadjusted has CapChg=F, CshAdjNormal=F, CshAdjAbnormal=F. Adjusted has CapChg=T and CshAdjNormal=T, with CshAdjAbnormal **not explicitly set**. We identify the precise file and hashes, rather than claiming explicitly all-dividend adjustment.

Only existing Step-8 diagnostics are used for corporate-action impact. No adjustment-factor detector, raw ingestion or price comparison is rerun. The existing factor-change screen is >=1%; its rows are candidates, not independently verified events.

| asset | date | unadjusted_close | adjusted_close | previous_observed_factor | adjustment_factor | identity_status | primary_break_cross_date_window | robustness_break_cross_date_window |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SNDL | 2022-07-22 00:00:00 | 0.3122 | 3.122 |  | 10.0 | saved_pre_split_scaling_check; not_event_boundary | False | False |
| SNDL | 2022-07-25 00:00:00 | 0.2974 | 2.974 |  | 10.0 | saved_pre_split_scaling_check; not_event_boundary | False | False |
| SNDL | 2022-07-26 00:00:00 | 2.28 | 2.28 |  | 1.0 | split_supported_by_saved_acquisition_notes;unverified_adjustment_boundary_candidate | False | True |
| IMDX | 2023-07-25 00:00:00 | 4.12 | 4.12 | 20.0 | 1.0 | unverified_adjustment_boundary_candidate | False | False |
| SCHM | 2024-10-11 00:00:00 | 27.96 | 27.1792 | 0.3240253929866989 | 0.972074391988555 | unverified_adjustment_boundary_candidate | False | False |
| SNDL | 2022-07-26 00:00:00 | 2.28 | 2.28 | 10.0 | 1.0 | split_supported_by_saved_acquisition_notes;unverified_adjustment_boundary_candidate | False | True |
| XPO | 2021-08-02 00:00:00 | 83.95 | 49.8768 | 0.3456622683683034 | 0.5941250744490768 | unverified_adjustment_boundary_candidate | False | False |
| XPO | 2022-11-01 00:00:00 | 32.5 | 32.5 | 0.5941244684963277 | 1.0 | unverified_adjustment_boundary_candidate | False | False |


SNDL's saved 1-for-10 reverse-split checks show raw close 0.2974 on 2022-07-25 then 2.28 on 2022-07-26, while the adjusted closes are 2.974 then 2.28. Thus adjustment removes the tenfold share-scale component, not the real daily market movement. IMDX's factor changes from 20 to 1 on 2023-07-25; SCHM's from approximately 0.324025 to 0.972074 on 2024-10-11; XPO's from approximately 0.345662 to 0.594125 on 2021-08-02 and from 0.594124 to 1 on 2022-11-01. Their event identities are not certified by these numbers. All 61 existing flags remain diagnostics; only SNDL has saved split verification. SNDL's verified split breaks the unadjusted robustness edge; it does not automatically break the adjusted primary edge.

## 3. Project-specific frozen choices

Use the adjusted acquisition unchanged for CS/AR/EDGE; use unadjusted unchanged for a separate common robustness run. No third acquisition, custom adjustment factors or per-estimator convention switching. Option B needs comprehensive independently verified action boundaries to protect unadjusted windows; the existing candidate screen is not a complete action ledger. Option C cannot supply a split-only or special-dividend-only transformation reproducibly from these saved files without inventing decomposed factors. Option A provides explicit vendor capital adjustment and normal-dividend smoothing before cross-date calculations, independent of performance.

Treat capital changes separately from normal cash dividends: primary T/T and robustness F/F. Special/abnormal dividends remain **UNKNOWN**, a documented acquisition limitation rather than a blocker to primary use. Do not infer the Bloomberg default. Unadjusted robustness cannot isolate abnormal-dividend effects from normal/capital changes. No third acquisition or invented adjustments are created.

PRIMARY ADJUSTED: do not break windows merely because any of the 61 heuristic flags exists. Retain every flag as diagnostic evidence. Only impose an event boundary when independently verified and methodologically required, with both evidence and reason recorded. No primary event breaks are currently imposed; saved SNDL verification alone does not require one in the adjusted series. UNADJUSTED ROBUSTNESS: explicitly break the saved verified SNDL split on 2022-07-26; additional verified split/capital-change breaks may be recorded explicitly. Unverified heuristics never become verified events or automatic exclusions in either role. If an imposed event date is missing, the first later observation still receives the appropriate role-specific break. Source rows remain present.

The frozen common primary policy is no OHLC imputation, no carry-forward and no compression of missing sessions. Preserve partial rows, cached source errors, source-only dates, duplicates and invalid/zero-range flags. Each future estimator window must satisfy that estimator's required fields AND valid calendar/date adjacency. A missing OPEN does not by itself invalidate otherwise valid H/L/C for CS/AR; EDGE requires OPEN as well. Full-OHLC availability remains a diagnostic, not a universal primary gate. Missing volume or bid/ask alone does not gate price-only inputs. The old OHLCV daily_input_valid flag is not estimator eligibility. Daily quotes are not the intraday benchmark.

Missing scheduled sessions must remain explicit on a future validated session-calendar analysis grid, with NaN prices rather than invented observations. Weekends and holidays are not missing sessions. No new calendar/grid is built here; when adjacency is unknown, flag it and prohibit silently treating consecutive available rows as consecutive sessions. EDGE's regular-grid recommendation is preserved without filling any intraday bars. Calendar integration and window lengths remain separate implementation decisions. A common available-field flag is not final horse-race eligibility.

This differs explicitly from the Abdi–Ranaldo empirical carry-forward of prior H/L/C on nontrading/zero-range days and its stock-month split/distribution exclusions. Method-specific author preprocessing is preserved as a possible later, separately authorized robustness replication, not the common primary horse-race policy; no such replication is implemented or executed here. Author negative-estimate corrections and monthly sampling thresholds remain evidence only. Roll's final formula and two-pair computability rule are unchanged and do not determine source selection or comparison eligibility.

First Rate split+dividend adjusted 09:30–16:00 aggregates remain local validation only. No source equivalence is claimed or selected based on closer prices. No new futures or crypto source convention is frozen.

## 4. Remaining limitations outside this approval

The daily source/convention and common missing-data policy are now frozen in daily_input_final_spec.yaml; the corrected candidate records its approval and points to that final artifact. Abnormal-dividend treatment remains unknown. Scheduled-session calendar integration, IMDX/OCX stable-ID continuity, EOD/session/auction differences, undocumented events and volume-scale comparability remain limitations. Window lengths, estimator negative/undefined output treatment and final analytical eligibility are outside this freeze. README.md, design_decisions.md, data_manifest.csv, Step-8 outputs, Roll final specification and universe selections remain unchanged.

No CS, AR, EDGE or provider Roll benchmark values, estimator performance or terminal extraction were calculated. Official code was read as evidence only and was neither installed nor executed.

Existing adjusted acquisition: 43159 returned rows for 18 securities; 181 rows lack complete OHLC. Counts describe saved Step-8 ingestion only; no missing dates were synthesized.

Validation: 119 tests passed, 0 failed; all 11 raw hashes/sizes verified before and after. All protected inputs and documents unchanged. Reproduce with src/daily_input_freeze_review.py.
