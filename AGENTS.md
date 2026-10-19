# MMF 1941 Project 1 — Instructions for Codex

Project: Proposal A04-03.
Research question: compare Corwin-Schultz, Abdi-Ranaldo and EDGE daily-OHLC
bid-ask spread estimators across asset classes and liquidity regimes against
an intraday benchmark over 2015-2025.

## Current phase

This is the INITIAL EXPLORATORY ANALYSIS for the first progress checkpoint.

Do NOT run the primary CS / AR / EDGE horse-race yet.
Do NOT select a benchmark based on which estimator performs best.

## Data rules

- Use RISKLAB_DATA_ROOT to locate RiskLab data.
- Never modify raw provider data.
- High-frequency data must come only from intraday_data.
- Do not download or substitute intraday data from Bloomberg or the web.
- Bloomberg is daily/EOD/reference only.
- Do not fill missing 1-minute bars.
- Preserve sparse-bar, missing, duplicate, invalid and zero-volume flags.
- FX is currently expected by the inventory but physically unavailable in the
  mounted intraday archive. Report this as an unresolved limitation; do not
  substitute another source.
- Futures contracts must not be blindly concatenated into a continuous series.
- Write derived results only under outputs/, manifests/, or data/interim/.

## Methodological rules

- Observational unit for the final project is asset-day.
- Benchmark definition is NOT frozen yet.
- Session conventions are NOT frozen yet.
- Treatment of negative/undefined estimator values is NOT frozen yet.
- These unresolved choices must be reported, not silently decided from results.
- Initial analysis is descriptive and diagnostic only.
- Avoid look-ahead, survivorship assumptions and undocumented exclusions.

## Reproducibility

- Use small pilot reads before loading large files.
- Prefer reusable functions in src/ over duplicating code inside notebooks.
- All figures and tables used in the checkpoint must be generated from code.
- Save diagnostic tables as CSV and presentation tables where useful as Markdown.
- Save figures at 300 DPI.
- Figures must have clear titles, labels, units, sample dates and notes.
- Keep a machine-readable record of exclusions and failures.