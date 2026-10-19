# Publication content audit

Initial HEAD: `ef920dc6105af28c3597279ef6b76517e0f84fd3`. HEAD files reviewed: 49. The working tree contains the completed, previously uncommitted study; it is understood and retained.

Review inventory: [publication_file_review.csv](publication_file_review.csv). Secret-pattern scanning reports file paths only; no credential material is reproduced. Aggregate tables/results are retained. Office containers were checked for embedded workbooks; the final presentation has no embedded workbook payload. The public notebook copy has no executed output.

Exact historical exclusions (verified by Git log, not inferred names):

- `notebooks/01_initial_exploratory_analysis.ipynb`
- `outputs/diagnostics/pilot_schema.csv`

Other previously tracked diagnostics contain checkpoint metadata, not raw rows; they will be untracked under the new private-diagnostics policy without deleting local files. No broad history purge of data folders or notebooks is authorized or performed.

Publication-safe status: pending exact-path history cleanup and final staged-tree audit. The external private bundle must never be uploaded to GitHub or the submission package because it preserves the original licensed history.
