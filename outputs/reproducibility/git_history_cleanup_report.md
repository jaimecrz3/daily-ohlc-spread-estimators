# Git history cleanup report

Original task HEAD: `ef920dc6105af28c3597279ef6b76517e0f84fd3`. Audited recovery checkpoint before rewrite: `56ae95cb30511bae2ed6599bcbfbb8f20ae0cb2f`. Rewritten checkpoint HEAD: `723a12a6c5590cfb36e7d754d5659dad1eee4797`. The subsequent final release commit is identified by the published branch/tag, rather than a circular self-reference in this report.

Exact paths removed from ALL reachable local refs:

- `notebooks/01_initial_exploratory_analysis.ipynb`
- `outputs/diagnostics/pilot_schema.csv`

Command: `.venv/Scripts/python.exe -B -m git_filter_repo --path notebooks/01_initial_exploratory_analysis.ipynb --path outputs/diagnostics/pilot_schema.csv --invert-paths --force`. Tool: git-filter-repo 2.47.0. No broad notebook/data-folder purge.

Verified external private backups: `../project_1_before_final_cleanup.bundle` and `../project_1_working_tree_before_cleanup.bundle`. Both were created and verified before rewriting. The second preserves the audited previously uncommitted working tree. These licensed-history recovery bundles must not be published or included in Drive delivery.

Origin was removed by the tool and restored unchanged: `https://github.com/jaimecrz3/daily-ohlc-spread-estimators.git`. Both exact-path Git logs are empty; both known raw-excerpt blob IDs are absent from reachable objects. Current source/docs/aggregate results remain present. Public working-tree bytes and private local originals were preserved. Raw Bloomberg and frozen analytic hashes are unchanged.

Remote publication uses an explicit expected-old-SHA force-with-lease on main; unknown remote work must not be overwritten. No plain --force push is authorized. The cleanup addresses reachable repository history, not external clones or hosting caches.
