# Final reproduction guide

Step18 is PRIMARY; Step19 ROBUSTNESS; Step20 DIAGNOSTIC. Step21 performs no estimation or model fitting. Exact frozen metadata and licensed data are prerequisites; GitHub alone is insufficient. FX stays blocked. Do not rerun universe selection or freeze-administration scripts to "refresh" a completed design.

## A. Presentation and saved-output verification (recommended)

1. Restore the private frozen diagnostics/specification bundle plus ignored analytic inputs from the authorized project archive. Retain original relative paths and recorded package versions. This bundle is not raw-data-free: many historical daily panels in outputs/diagnostics are licensed and deliberately ignored.
2. Configure RISKLAB_DATA_ROOT only if source construction is required. Existing raw Bloomberg files remain under data/raw_bloomberg/13-10-2026/, with the three legacy pilot files and original sha256_manifest.csv at their recorded relative locations. Never edit raw workbooks or rerun path-migration administration.
3. `.venv/Scripts/python.exe -B outputs/diagnostics/horse_race/validate_outputs.py`
4. `.venv/Scripts/python.exe -B outputs/diagnostics/robustness/validate_outputs.py`
5. `.venv/Scripts/python.exe -B outputs/diagnostics/error_model/validate_outputs.py`
6. `.venv/Scripts/python.exe -B src/reproduce_final_results.py` replays frozen-derived metric aggregation into ignored staging and compares to original results. It does not overwrite original stages or refit ML; it uses saved cross-fitted predictions.
7. `.venv/Scripts/python.exe -B src/final_artifacts.py --run-tests` rebuilds final tables, figures, docs and master ledger deterministically from saved results.
8. `.venv/Scripts/python.exe -B outputs/diagnostics/final_artifacts/validate_outputs.py` checks final source/row/metric reconciliation, artifact checksums and licensed-data boundaries.

## B. Full-from-source construction (licensed data and frozen metadata required)

Use an isolated replica workspace with the same code/environment, immutable raw sources and frozen metadata bundle. Never experiment in the locked delivery workspace. These expensive commands were NOT run by Step21; full source reproduction is not newly certified here. Keep all prior authoritative result files as read-only comparison references; stage/rebuild granularity before result aggregation.

1. Verify all eleven Bloomberg files against data/raw_bloomberg/sha256_manifest.csv; verify the official First Rate source fingerprints saved by the historical and Step17 runs. Mount the official archive via RISKLAB_DATA_ROOT; no external/minute substitute. Missing licensed inputs block source replay.
2. Rebuild normalized daily Bloomberg inputs with `src/reproduce_final_results.py --ingest-bloomberg-to-staging`. This uses bloomberg_io.read_daily_values on the finalized dated raw VALUES snapshots, with the frozen selected_stocks_etfs.csv; no workbook recalculation or formula/raw edits. Compare staged frames with the normalized inputs before installing them in the isolated replica. The older Step8 CLI assumes pre-migration raw locations and must not be used unmodified for the dated archive.
3. In that replica, reproduce crypto historical daily panels with `.venv/Scripts/python.exe -B src/crypto_historical_materialization.py` and selected futures with `.venv/Scripts/python.exe -B src/futures_historical_sessions.py`. Their frozen metadata dependencies (root mapping, session evidence, selected universe, timezone proof, exact calendars) must be restored. Do not rerun broad universe/session research or extrapolate unresolved historical futures periods. Validate 2024 reconciliations and the exact primary calendars before continuing.
4. `.venv/Scripts/python.exe -B src/provider_run_io.py` constructs/validates individual-asset Roll caches from official minute sources. `.venv/Scripts/python.exe -B src/provider_run.py --run-tests` integrates frozen daily kernels and Roll, with exact design counts and five reproductions. Both require archive access; version-dependent byte/hash mismatches must be investigated, not silently approved or relaxed.
5. For PRIMARY metric reproduction use `.venv/Scripts/python.exe -B src/reproduce_final_results.py` rather than overwrite the archived Step18 lock. Its functions reuse primary_horse_race accuracy/rate/HAC mappings and compare results without changing the baseline manifests.
6. To reconstruct unadjusted robustness source outcomes, call primary_robustness.materialize_unadjusted on the verified provider panel in the replica, then use the result replay. Original executable `src/primary_robustness.py --run-tests` is for a coherent replica with its original prior-stage lock; never replace saved locks to accommodate unexplained differences.
7. Refit the exact Step20 model via `.venv/Scripts/python.exe -B src/cross_fitted_error_model.py --run-tests` in the coherent replica only. Settings, purging, embargo, features and both targets remain fixed. Compare predictions/metrics with the immutable reference bundle, preserving failures and negative results.
8. Run frozen-derived metric replay and presentation checks from route A. Runtime/test-count metadata may differ after new tests, so compare analytic values and frozen inputs separately from execution metadata; do not modify authoritative Steps18–20 in the delivery workspace.

## Licenses and storage

Existing shared RiskLab/First Rate raw data are referenced, not duplicated. Student-extracted Bloomberg raw files must be preserved unchanged in the student's personal Google Drive; this step neither uploads nor copies them. Derived data are reproducible from licensed raw + code + frozen metadata. Granular OHLCV/error/prediction panels, fitted models and historical daily files remain ignored. Only code/tests, methodology, aggregated results, figures and small metadata may be public.

The old executed exploratory notebook and pilot_schema.csv contained raw-row excerpts. Their local originals are unchanged, ignored and removed from the Git index. The separate code-only notebook preserves all source cells with outputs cleared. Old commits STILL contain those excerpts: use a clean export/release excluding old Git history, or obtain separate authorization for history cleanup before publishing history. No commits were rewritten. licensed_data_remediation.json records this distinction; a clean current index does not certify clean history.

## Provenance and environment

final_artifact_manifest.csv lists final artifacts and frozen metadata by relative path, role, SHA-256 and size. It excludes itself to avoid a circular hash. Historical Step14 documentation test was extended only to permit the four explicitly authorized Step21 documentation paths; the original test and its hash remain preserved. No old source/result manifest was rewritten. Full pip environment is saved in environment_requirements.txt; Python/package versions are in environment.json. Dependencies are local scientific Python, including numpy, pandas, pyarrow, matplotlib, openpyxl, PyYAML, scipy, statsmodels, scikit-learn and threadpoolctl. Do not claim reproduction without the licensed archive and private frozen metadata bundle.


## Publication-stage addendum

# Publication and delivery

The analytical results are frozen. Publication tooling does not estimate spreads, fit models, change samples or reselect assets. The README empirical content is unchanged; only its administrative publication-gate paragraph was updated. The original Step21 documentation receipt is retained alongside the explicit publication amendment.

Final paper: `paper/MMF1941_Project1_Final_Paper.md`, `.pdf` and the optional `.docx`. Final presentation: `presentation/MMF1941_Project1_Final_Presentation.pptx`. The paper draft, its claims audit, aggregate results and all frozen figures remain unchanged. Public copies of method reviews are under `docs/frozen/`; small frozen configurations and selected-universe/calendar metadata are under `config/frozen/`. Only the public FX configuration path/error is portability-redacted; the original private freeze is untouched and FX remains blocked.

Shared First Rate/RiskLab raw files are referenced through RISKLAB_DATA_ROOT and are never duplicated. Personal Bloomberg raw data are excluded from GitHub and copied byte-for-byte only into the authorized private Drive submission. Restoring licensed raw sources is required for source reproduction. The code and public aggregates alone cannot reproduce granular observations.

## Drive package layout and reproduction

The requested delivery layout puts code under `code/` and outputs/data at package root. For source reproduction, create an independent local repository-shaped workspace: copy the CONTENTS of `code/` into that workspace, then copy package `outputs/`, `paper/`, `presentation/` and personally acquired `data/raw_bloomberg/` into its root. Do not execute the source pipeline in the delivery directory. Never duplicate the shared First Rate archive: configure RISKLAB_DATA_ROOT to its official mounted location.

Safe metadata in `config/frozen/` mirrors original relative paths; restore needed specifications, selected lists and exact calendars to their original locations under ignored `outputs/diagnostics/` before source construction. The safe specification inventory records checksums and the FX-only portability amendment. Historical scripts also require their recorded stage/provenance metadata and reconstruct their granular outputs from licensed inputs; missing metadata must be investigated, never invented or bypassed. No hidden interim, analytic, prediction or fitted-model panels are included in delivery.

Follow the full-source order in `outputs/reproducibility/final_reproduction_guide.md` in that isolated workspace. Frozen-derived verification is a separate route for an existing licensed working archive. Full source reconstruction was not rerun or newly certified at publication. Historical artifact manifests remain records of earlier stages; `release_artifact_manifest.csv` is the publication checksum inventory. Packaging checks do not rewrite old analytical locks to accommodate differences.

The private Git bundle is recovery-only and excluded from both release and submission. Rewriting branch history does not change GitHub visibility settings or guarantee removal of provider excerpts from external clones, caches or pre-existing pull requests. No credentials or private acquisition observations belong in the public tree.

