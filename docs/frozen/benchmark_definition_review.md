# Step 10.1 Roll benchmark definition: final specification

## Directly from Roll (1984)

Roll derives the price-change spread as twice the square root of negative lag-one covariance. The model relies on transaction prices, informational efficiency and locally stationary price-change distributions. It concerns effective trading costs rather than a daily quoted bid/ask difference. [Original article](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1984.tb03897.x).

Section II and footnote 5, p. 1130, explicitly discuss arithmetic percentage returns to estimate an approximate percentage spread. The footnote explains a small approximation bias from the return denominator under a fixed dollar spread. Thus this project uses the literature-supported percentage-return form/adaptation, not an invented modification. [Original article copy, p. 1130](https://www.bauer.uh.edu/rsusmel/phd/roll1984.pdf).

## Project-specific numerical and sampling choices

For retained closes C_t, r_t = C_t/C_(t-1) - 1 only if adjacent timestamps differ by exactly one minute. A covariance pair (x_i,y_i)=(r_t,r_(t-1)) requires the underlying three physical observations to be consecutive one-minute closes. All operations stay inside one asset/session-day and, for futures, one validated selected contract. Invalid observations break chains; filtering them out cannot connect their neighbors.

With n eligible pairs, gamma = sum_i[(x_i-mean(x))(y_i-mean(y))]/(n-1). The two means are calculated separately on the paired vectors, not the full unpaired return series. ddof=1 and n>=2 are unchanged. A contiguous valid run therefore needs four closes/three returns/two pairs; three closes yield one pair and cannot produce a sample covariance. No additional coverage or precision threshold was introduced.

If gamma<0, relative spread = 2*sqrt(-gamma), and bps = 10000*relative spread. Returns are decimal fractions, not numbers already multiplied by 100. If finite gamma>=0, preserve gamma and mark both spreads NaN and benchmark_defined=False; never replace the estimate with zero. The approximation in the literature, sample ddof convention, one-minute/day sampling and this nonnegative sample policy are distinct decisions.

The paper uses transaction prices; First Rate supplies OHLCV bars. The close is a sampled transaction-price proxy rather than a complete trade stream or NBBO measure. One-minute bar-close selection, paired-vector ddof=1, asset-day estimation, minimum pair count, exact gaps and session conventions are project choices. Zero-volume rows remain flagged and can contribute valid prices; no zero-volume bars or missing minutes are synthesized.

Retain bars_observed, one_minute_returns, roll_pairs, max_gap_minutes, gaps_gt_one_minute, all existing quality counts and the new invalid-price/return counts. Gap summaries use all retained observations inside the day, including flagged bars; duplicate gaps of zero and overnight gaps are not counted as gaps>1 minute. Sparse or failed observed days are never dropped; empty calendar dates remain in audits only.

## Explicit failure policy

The canonical detailed failure_reason follows benchmark_failure_policy.csv. With insufficient pairs, precedence is insufficient_minute_bars, invalid_price, invalid_return, source_quality_condition, insufficient_consecutive_returns, then insufficient_covariance_pairs. With enough pairs, non_finite_autocovariance or non_negative_autocovariance explains an undefined result. All eight diagnostic booleans remain available and may coexist; they are not competing mutually exclusive source events. A defined day has empty failure_reason even if it contains other unusable observations.

For compatibility, roll_defined equals benchmark_defined, and benchmark_failure_reason retains the previous coarse insufficient_roll_pairs label for all pair shortages. It is explicitly a legacy alias, not a different spread treatment. Current numerical results on ordinary eligible inputs are unchanged. Corrections add gap counts, source-cause diagnostics and masking of returns rounded to the impossible -1 boundary. Non-finite returns were already masked; they are now counted explicitly. These are mathematical safeguards, not adjustments motivated by observed failure rates.

## Sessions and sensitivity

Stocks/ETFs retain 09:30 <= local time < 16:00 America/New_York. Crypto uses UTC days for pilots only. Futures use only ES/CL verified pilot sessions and provider-selected unadjusted individual contracts; no unresolved root fallback. FX remains unavailable with no substitution. No new exchange holiday or early-close filtering is introduced.

successive_observed_bars is prepared in the YAML solely as robustness/sensitivity: later returns could span positive observed gaps, with gap durations audited, and remain confined to session-days and contracts. It is not implemented or executed here; requesting it from the primary function raises NotImplementedError. The primary never falls back to it.

## Remaining freeze limitations

Market efficiency, stationarity and the transaction-close proxy are maintained assumptions, not proven by the formula tests. The two-pair minimum establishes mathematical computability, not statistical precision. Sparse-bar sampling, adjusted-price comparability, corporate actions and cross-source conventions still require review. No sampling/coverage exclusion is tuned from prior asset failure rates. Final futures/crypto universes and FX access remain unresolved. Step 10.1 approves the benchmark formula and mathematical computability. The final machine-readable specification is benchmark_final_spec.yaml; benchmark_freeze_candidate.yaml remains the historical candidate. Approval does not freeze primary-comparison eligibility.

13 hand/synthetic formula cases passed. Unit tests separately cover scaling invariance, ddof against NumPy/Pandas, negative/nonnegative covariance, invalid arithmetic, exact gap breaks, no filling and equity/crypto/futures session boundaries. No provider bars, historical benchmark results, estimator values or universe-selection decisions were read or recalculated. README.md, design_decisions.md, data_manifest.csv and all raw acquisition file contents remain untouched. Only manifest relative paths were updated in Step 10.1; every previously recorded hash and size was preserved.

## Computability versus primary-comparison eligibility

Two valid covariance pairs are the mathematical minimum for ddof=1. A computable covariance can still be nonnegative, producing an undefined spread. Neither computability nor a defined spread automatically admits an asset-day to the later estimator comparison. No separate minimum-pair reliability threshold, coverage cutoff or whole-day quality filter for that comparison is frozen. Preserve roll_pairs and all coverage/quality diagnostics so these analytical rules can be approved separately before estimator comparison. Benchmark results never determine universe selection.

Reproduction: run finalize_administration.py once to reconcile manifest paths and promote the approved candidate, then validate_outputs.py to verify the final specification, all raw paths/hashes and the full fixture suite. The historical src/benchmark_freeze_review.py regenerates candidate artifacts only; it is not the final approval procedure. Workbook access in these administration commands is byte hashing only.

Final validation: 110 tests passed, 0 failed; all 13 existing synthetic validation cases passed. Universe-selection files and the finalized manifest remained unchanged during verification.

Raw path/hash verification: all 11 files match their recorded SHA-256 hashes and sizes at the exact manifest-relative paths. Eight final acquisition files remain under data/raw_bloomberg/13-10-2026/; three pilot files remain at the raw directory root. Every original content hash and size was preserved; only eight manifest paths changed. No raw acquisition files or workbooks were moved or rewritten. See manifest_path_update_audit.csv, raw_hash_verification.csv and raw_file_location_review.csv. No provider benchmark values or estimator values were calculated.
