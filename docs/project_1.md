# Which Daily OHLC Spread Estimator Tracks Realized Intraday Cost? A CS / AR / EDGE Horse-Race

- Student: Corzo Galdó, Jaime
- Assignment: Project 1
- Proposal ID: A04-03
- Official area: A04 — Algorithmic trading & execution costs
- Official category: C1 — Trading & microstructure
- Data not ready: 50.0%
- Estimated data not available locally: 0.0%

## Main research question

Across asset classes and liquidity tiers (2015-2025), which existing daily-OHLC spread estimator (Corwin-Schultz, Abdi-Ranaldo, EDGE) best matches a 1-min realized-cost benchmark, and where does each break down?

## Testable hypothesis

EDGE dominates on accuracy and negative-estimate rate; Corwin-Schultz is downward-biased for thinly-traded / non-continuous names; ranking is stable across asset classes but levels diverge most in crypto and small-cap equities.

## Why this project was selected

The project offers recent or out-of-sample evidence, economic implementability, a transparent comparison with interpretable benchmarks. Its hypothesis is falsifiable and the required market data can be assembled without asking the student to acquire high-frequency data.

## Study design

- Primary assets: Stocks, ETFs, futures, FX, crypto (liquidity-stratified sample each).
- Traditional method: Per-asset comparison of daily estimator vs 1-min realized-range/Roll benchmark; bias and RMSE; share of negative estimates; tier/asset interaction; HAC SEs on the error panel.
- ML or robustness method: Cross-fitted error model (which features predict estimator error) under purged CV; stability across folds. Robustness/diagnostic only — not a new estimator.
- Sample or event window: 2015-2025 daily estimates vs intraday benchmark.
- Expected result type: boundary-condition (estimator ranking holds; levels asset-dependent)
- Proposal feasibility: GO (data ready; benchmark is itself a 1-min proxy -> boundary by construction)

## Data plan

### Bloomberg acquisition by the student

Daily OHLC, bid, ask, volume and quoted-spread fields for the sampled equities and ETFs, plus security identifiers.

The Bloomberg extraction must be end-of-day, daily, weekly, monthly, quarterly, annual, document, or event/reference data only. Record terminal function, security or series identifier, field, frequency, date range, currency, adjustment convention and extraction date in a source log.

### Data already available in RiskLab

1. 1-min OHLCV (all classes) -> intraday_data/{stocks,etfs,futures,fx,cryptos} [local]
2. daily PX_BID/PX_ASK spot-check (meme names) -> 01_market_microstructure [partial coverage or preparation narrow]

### Local data needing preparation

1. daily PX_BID/PX_ASK spot-check (meme names) -> 01_market_microstructure [partial coverage or preparation narrow]

### Data not currently available locally

1. Optional missing: true NBBO effective spread -> WRDS TAQ [not local PARK, optional upgrade]

### High-frequency data rule

Use only `C:\risklab\data\intraday_data` for every high-frequency price, quote, option or futures series. Do not request or download high-frequency data from Bloomberg.

## Minimum outputs

1. A source and field dictionary for every Bloomberg series and every local file used.
2. A reproducible cleaning and merge script with point-in-time and adjustment conventions stated explicitly.
3. Descriptive coverage, missingness and identifier-join diagnostics before estimation.
4. The traditional specification, the stated robustness method and economically interpretable effect sizes.
5. A concise paper draft that preserves null or failed results and distinguishes exploratory from confirmatory analysis.
