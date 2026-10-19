# Publication content audit

Initial HEAD: `ef920dc6105af28c3597279ef6b76517e0f84fd3`. HEAD files reviewed: 49. The working tree contains the completed, previously uncommitted study; it is understood and retained.

Review inventory: [publication_file_review.csv](publication_file_review.csv). Secret-pattern scanning reports file paths only; no credential material is reproduced. Aggregate tables/results are retained. Office containers were checked for embedded workbooks; the final presentation has no embedded workbook payload. The public notebook copy has no executed output.

Exact historical exclusions (verified by Git log, not inferred names):

- `notebooks/01_initial_exploratory_analysis.ipynb`
- `outputs/diagnostics/pilot_schema.csv`

Other previously tracked diagnostics contain checkpoint metadata, not raw rows; they will be untracked under the new private-diagnostics policy without deleting local files. No broad history purge of data folders or notebooks is authorized or performed.

Publication-safe status: pending exact-path history cleanup and final staged-tree audit. The external private bundle must never be uploaded to GitHub or the submission package because it preserves the original licensed history.

## Final release-tree audit

PASS for publication candidates. The public tree excludes data/**, raw workbooks, granular analytic/interim/error/prediction panels, fitted models, private diagnostics and the executed legacy notebook. Legitimate aggregate results/tables/figures and the supplied final presentation are retained. Candidate-file inventory and secret/raw-row pattern checks are saved in publication_candidate_review.csv; final checksums are in release_artifact_manifest.csv.

The README contains portable public links and unchanged empirical text; only its administrative publication gate changed under explicit Step24 authorization. Safe method reviews/specifications are copied individually to docs/ and config/, never the complete diagnostics directory. FX path/error strings in the public copy are portability-redacted without changing the original freeze or analytical policy.

Git histories were inspected for exact historical paths, then only the two confirmed raw-excerpt paths were filtered. Known offending blobs are unreachable. The raw-history backup stays private outside the repository. No secret-pattern hit or embedded workbook payload was found in the public candidates. The private raw excerpts are still retained locally, ignored and untracked.

Paper source/PDF/DOCX and final PPTX exist. The PDF is visually and mechanically checked. No analytical result or raw provider file was edited. Full licensed-from-source reconstruction was not rerun; packaged code/configuration and the official shared source are required for that route. Public aggregates alone are insufficient.

Final public/index file count: 205. The two checksum-inventory files are excluded from the candidate review checksum rows to avoid a circular dependency; the release inventory excludes only itself.
