# Detailed implementation guide: Which Daily OHLC Spread Estimator Tracks Realized Intraday Cost? A CS / AR / EDGE Horse-Race

- Student: Corzo Galdó, Jaime
- Assignment: Project 1
- Proposal ID: A04-03
- Official area: A04 — Algorithmic trading & execution costs
- Companion brief: `project_1.md`
- Data not ready: 50.0%
- Estimated data not available locally: 0.0%

## Purpose and scope

This guide turns the approved project brief into an auditable implementation sequence. It preserves the research question, hypothesis and model family in the companion brief. Choices listed under **Decisions to confirm before estimation** must be settled with the supervisor and recorded before the primary results are examined.

## Approved research target

### Main question

Across asset classes and liquidity tiers (2015-2025), which existing daily-OHLC spread estimator (Corwin-Schultz, Abdi-Ranaldo, EDGE) best matches a 1-min realized-cost benchmark, and where does each break down?

### Testable hypothesis

EDGE dominates on accuracy and negative-estimate rate; Corwin-Schultz is downward-biased for thinly-traded / non-continuous names; ranking is stable across asset classes but levels diverge most in crypto and small-cap equities.

### Operational summary

- Observational unit: asset-day.
- Primary outcome: error of a daily spread estimator relative to a local intraday benchmark.
- Main signal, treatment or exposure: CS, AR and EDGE estimator values.
- Benchmark or comparison: realized spread or range benchmark from one-minute data.
- Primary estimand: bias, absolute error and root-mean-square error by estimator and asset class.
- Proposed sample: 2015-2025 daily estimates vs intraday benchmark.
- Primary assets: Stocks, ETFs, futures, FX, crypto (liquidity-stratified sample each).

## Decisions to confirm before estimation

- Intraday benchmark definition.
- Session filters and treatment of negative or undefined estimates.

Do not choose among these alternatives by comparing final significance or performance. Record the decision, rationale, date and approving supervisor in `design_decisions.md`.

## Required data

### Full requirement from the project inventory

1. 1-min OHLCV (all classes) -> intraday_data/{stocks,etfs,futures,fx,cryptos} [local]
2. daily PX_BID/PX_ASK spot-check (meme names) -> 01_market_microstructure [partial coverage or preparation narrow]
3. Optional: true NBBO effective spread -> WRDS TAQ [not local PARK, optional upgrade]

### Bloomberg acquisition assigned to the student

Daily OHLC, bid, ask, volume and quoted-spread fields for the sampled equities and ETFs, plus security identifiers.

All Bloomberg retrieval must be end-of-day, daily, weekly, monthly, quarterly, annual, event/reference or document data. Any required minute-level or intraday series must come only from `C:\risklab\data\intraday_data`.

### Local data already identified

1. 1-min OHLCV (all classes) -> intraday_data/{stocks,etfs,futures,fx,cryptos} [local]
2. daily PX_BID/PX_ASK spot-check (meme names) -> 01_market_microstructure [partial coverage or preparation narrow]

### Local data requiring preparation

1. daily PX_BID/PX_ASK spot-check (meme names) -> 01_market_microstructure [partial coverage or preparation narrow]

### Data not currently available locally

1. Optional missing: true NBBO effective spread -> WRDS TAQ [not local PARK, optional upgrade]

## Bloomberg retrieval procedure

Use `FLDS <GO>` to confirm field mnemonics and definitions, `BDP` for static references, `BDH` for end-of-day histories, and `BDS` or the relevant terminal event screen for bulk constituents or event records.

The field names below are candidates and routing aids, not a substitute for terminal verification. Confirm every mnemonic and definition with `FLDS <GO>` for the actual security type and entitlement.

| Requirement | Candidate fields or route | Mandatory validation |
|---|---|---|
| Stable identifiers | ID_BB_GLOBAL, ID_ISIN, TICKER_AND_EXCH_CODE | Confirm identifier history and exchange mapping. |
| Currency and classification | CRNCY plus the relevant sector, country or asset classification | Check changes through time and do not infer missing classifications from current values. |
| Daily OHLC and volume | PX_OPEN, PX_HIGH, PX_LOW, PX_LAST, VOLUME | Use one adjustment and session convention. |
| Quotes or spread | Licensed bid, ask or spread fields located through FLDS | Confirm close timestamp and quote staleness. |

### Pilot before the full pull

1. Test two representative securities or series over ten dates.
2. Confirm that timestamps, currencies, units and adjustments match the intended construct.
3. Compare at least three observations with the terminal display or source document.
4. Test one known corporate action, event date, roll date or release revision where relevant.
5. Save the pilot, field definitions and validation notes before scaling the retrieval.
6. Use one raw file per coherent table and never paste values manually into the analysis panel.

Create `bloomberg_source_log.csv` with these columns:

`source_type, provider, terminal_function, security_or_series_id, field, field_description, frequency, start, end, currency, units, timezone, adjustment, retrieval_date, file_name, file_hash, notes`

## RiskLab data-catalog procedure

1. Search `C:\risklab\data\_catalog\catalog.csv` for non-intraday datasets by construct, fields, asset class and date coverage.
2. Search `C:\risklab\data\bloomberg\inventory.csv` for Bloomberg holdings already present.
3. Search other provider inventories for possible alternatives, but do not treat a similar filename as construct equivalence.
4. Search `C:\risklab\data\_catalog\intraday_inventory.csv.gz` only when the approved design requires minute-level or option-chain data.
5. Resolve current paths through `C:\risklab\data\_catalog\data_paths.py`; retain stable dataset IDs in the manifest.
6. Classify each requirement as `AVAILABLE`, `PARTIAL`, `METADATA REVIEW` or `MISSING`.
7. Verify point-in-time status, adjustment, units, currency, timezone, universe, licence and survivorship before scientific use.

Create `data_manifest.csv` with these columns:

`dataset_id, source_path, provider, construct, role, unit, frequency, start, end, join_keys, point_in_time_status, adjustment, currency, timezone, license, validation_status, exclusions, notes`

## Recommended project structure

```text
project_1/
  README.md
  design_decisions.md
  config/
    project_config.yaml
  manifests/
    data_manifest.csv
    bloomberg_source_log.csv
    sample_attrition.csv
  data/
    raw_bloomberg/
    interim/
    analytic/
  src/
    00_design_freeze
    01_source_inventory
    02_raw_validation
    03_build_events_or_signals
    04_build_outcomes
    05_merge_analysis_panel
    06_descriptive_diagnostics
    07_primary_estimation
    08_robustness
    09_tables_figures
  outputs/
    tables/
    figures/
    diagnostics/
    models/
  paper/
```

Keep provider data immutable. Derived files belong in `interim` or `analytic`, never beside source files.

## End-to-end implementation sequence

1. Read the original brief and copy unresolved decisions into `design_decisions.md`.
2. Freeze the research unit, outcome, signal/treatment, benchmark, estimand, sample, event windows and exclusions before the primary run.
3. Translate every required construct into one row of `data_manifest.csv`.
4. Resolve local sources through the RiskLab catalog; never edit the provider files.
5. Run a small Bloomberg pilot, validate fields and dates, then retrieve only approved non-intraday data.
6. Freeze raw files and hashes; perform schema and economic-validity checks before merging.
7. Build signals/events and outcomes in separate steps, then join with an explicit match report.
8. Produce descriptive coverage and pre-estimation diagnostics; stop if key timing or universe assumptions fail.
9. Run the baseline model and save estimates, standard errors, sample counts and configuration together.
10. Run only prespecified robustness checks, placebos and out-of-sample comparisons.
11. Reconcile all numbers used in the paper to one machine-readable results table.
12. Archive the source log, manifest, design decisions, code, environment record and final outputs together.

## Project-specific construction and estimation hints

1. Implement each published estimator literally, including admissibility rules and treatment of negative estimates.
2. Build the benchmark only from `C:\risklab\data\intraday_data` and harmonize sessions before daily aggregation.
3. Compare errors in basis points and relative to price so asset classes are commensurable.
4. Stratify by liquidity, volatility and price level before fitting any error model.
5. Write unit-tested formulas for every candidate estimator.
6. Construct the benchmark independently from the candidate inputs.
7. Align units, sessions and timestamps before comparison.
8. Report bias, absolute error, squared error and failure rate.
9. Compare methods on identical asset-days and within prespecified strata.
10. Use one session convention per asset class and document overnight treatment.
11. Retain negative or undefined estimator flags before applying exclusions.
12. Use local minute data whenever an intraday benchmark is required.

## Baseline statistical specification

The companion brief specifies the primary method as:

> Per-asset comparison of daily estimator vs 1-min realized-range/Roll benchmark; bias and RMSE; share of negative estimates; tier/asset interaction; HAC SEs on the error panel.

Use that method as the baseline. The following notation is an implementation aid and must be adapted without changing the approved estimand:

- $Error^{(m)}_{i,t}=Estimate^{(m)}_{i,t}-Benchmark_{i,t}$
- $RMSE_m=\sqrt{N^{-1}\sum_{i,t}(Error^{(m)}_{i,t})^2}$

At minimum, save the coefficient or portfolio effect, standard error, confidence interval, p-value where appropriate, economic units, observations, entities/events, sample dates and specification identifier. Report effect sizes in economically interpretable units in addition to statistical significance.

## Secondary robustness specification

The companion brief proposes:

> Cross-fitted error model (which features predict estimator error) under purged CV; stability across folds. Robustness/diagnostic only — not a new estimator.

Treat this as robustness, not as a replacement for the primary model. Fit every transformation, feature selection step and tuning choice inside the training sample. Use chronological splits, purging and embargo where labels or holding periods overlap. Compare against the same simple benchmark on identical test observations. Preserve failed folds and infeasible models in the diagnostics.

## Validation and falsification checks

1. Overnight gaps contaminate estimators that assume continuous trading.
2. Sparse one-minute bars can make the benchmark appear artificially low.
3. Different exchange sessions make pooled comparisons misleading.
4. Missing and undefined estimates by method.
5. Error versus price, volatility, volume and liquidity.
6. Session and asset-class heterogeneity.
7. Influence of outliers and sparse benchmark observations.

Also run these universal checks:

- Duplicate-key and many-to-many join audit.
- Date-shift test that moves signals or events one period backward and forward.
- Negative-control or placebo outcome where economically defensible.
- Influence check excluding the largest event, issuer, asset or crisis period one at a time.
- Common-sample comparison for every model horse-race.
- Results with and without the most consequential data-quality exclusions.
- Sign-convention test using a hand-calculated example.
- Reproduction of five randomly selected observations from raw source to final variable.

## Output plan

### Tables

1. **Table 1: Estimator definitions and usable observations.** Include observations, dates, units, estimate, uncertainty and the exact specification label.
2. **Table 2: Bias and error horse-race.** Include observations, dates, units, estimate, uncertainty and the exact specification label.
3. **Table 3: Error decomposition and robustness.** Include observations, dates, units, estimate, uncertainty and the exact specification label.

4. **Table 4: robustness and falsification summary.** Include every prespecified robustness result, including failures and nulls.
5. **Appendix table: data lineage and attrition.** Show source coverage, filters, unmatched records and final counts.

### Figures

1. **Figure 1: Estimator versus benchmark scatter.** Show sample coverage and uncertainty; label event time, horizon or portfolio definition explicitly.
2. **Figure 2: Error distribution by method.** Show sample coverage and uncertainty; label event time, horizon or portfolio definition explicitly.
3. **Figure 3: Relative performance by liquidity or asset class.** Show sample coverage and uncertainty; label event time, horizon or portfolio definition explicitly.

4. **Figure 4: implementation or data-quality diagnostic.** Use the most important risk identified above.

Every table and figure should display the sample period, frequency, units and a concise note defining the construction.

## Suggested code-module responsibilities

- `00_design_freeze` — stores the approved estimand, windows, universe, exclusions and sign conventions.
- `01_source_inventory` — resolves local catalog records and checks source coverage.
- `02_raw_validation` — validates schemas, identifiers, timestamps, duplicates, units and missingness.
- `03_build_events_or_signals` — creates event, signal or treatment tables without outcome information.
- `04_build_outcomes` — constructs returns, spreads, forecasts or payoffs independently.
- `05_merge_analysis_panel` — performs audited joins and emits an attrition table.
- `06_descriptive_diagnostics` — produces coverage, distributions and pre-estimation plots.
- `07_primary_estimation` — runs only the frozen baseline specifications.
- `08_robustness` — runs the prespecified alternatives and placebos.
- `09_tables_figures` — creates publication-ready outputs directly from saved results.

Each module should read declared inputs, write declared outputs and emit a short validation summary. Configuration values belong in one configuration file rather than being repeated throughout scripts or notebooks.

## Common failure modes and responses

- Overnight gaps contaminate estimators that assume continuous trading. Response: quantify its incidence, preserve an explicit flag, and report a sensitivity analysis rather than silently deleting observations.
- Sparse one-minute bars can make the benchmark appear artificially low. Response: quantify its incidence, preserve an explicit flag, and report a sensitivity analysis rather than silently deleting observations.
- Different exchange sessions make pooled comparisons misleading. Response: quantify its incidence, preserve an explicit flag, and report a sensitivity analysis rather than silently deleting observations.
- If Bloomberg coverage is thinner than expected, produce a coverage matrix before narrowing the universe or dates; any consequential scope change requires supervisor approval.
- If local and Bloomberg values disagree, compare timestamps, currency, adjustment, units and identifier history before selecting a source.
- If the main result changes sign under a reasonable convention, present the boundary clearly and do not choose the convention based on significance.
- If an estimator fails on some dates, retain the failure rate and determine whether failures are economically selected.

## Minimum reproducibility record

- Research question and frozen estimand.
- Design-decision log with approval dates.
- Bloomberg source log and local-data manifest.
- Raw-file hashes and retrieval dates.
- Environment and package versions.
- Variable dictionary with formulas, units and timing.
- Sample-flow and exclusion table.
- Seed values for resampling and fitted procedures.
- Saved primary and robustness result tables.
- Script that rebuilds every final table and figure.

## Completion checklist

- [ ] Every raw input is listed with a stable identifier, path or source record and hash.
- [ ] Every variable has a definition, unit, timestamp and availability lag.
- [ ] All joins report unmatched and duplicate keys.
- [ ] The final sample can be recreated from raw inputs in one documented sequence.
- [ ] The main estimate uses the frozen sample and specification.
- [ ] Standard errors match the dependence structure.
- [ ] Economic magnitudes, costs and confidence intervals are reported together.
- [ ] Null and adverse results remain in the output.
- [ ] All tables and figures are rebuilt from saved results rather than edited manually.
- [ ] No Bloomberg high-frequency series is requested or downloaded.

## First supervisor checkpoint

Bring the following before the full analysis: the completed design-decision log, data manifest, Bloomberg pilot and field definitions, sample-coverage table, ten hand-checked observations, one preliminary descriptive figure and a written list of unresolved data limitations. Do not present a primary hypothesis test until these items are reviewed.
