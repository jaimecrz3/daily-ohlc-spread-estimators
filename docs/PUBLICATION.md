# Publication and delivery

The analytical results are frozen. Publication tooling does not estimate spreads, fit models, change samples or reselect assets. The README empirical content is unchanged; only its administrative publication-gate paragraph was updated. The original Step21 documentation receipt is retained alongside the explicit publication amendment.

Final paper: `paper/MMF1941_Project1_Final_Paper.md`, `.pdf` and the optional `.docx`. Final presentation: `presentation/MMF1941_Project1_Final_Presentation.pptx`. The paper draft, its claims audit, aggregate results and all frozen figures remain unchanged. Public copies of method reviews are under `docs/frozen/`; small frozen configurations and selected-universe/calendar metadata are under `config/frozen/`. Only the public FX configuration path/error is portability-redacted; the original private freeze is untouched and FX remains blocked.

Shared First Rate/RiskLab raw files are referenced through RISKLAB_DATA_ROOT and are never duplicated. Personal Bloomberg raw data are excluded from GitHub and copied byte-for-byte only into the authorized private Drive submission. Restoring licensed raw sources is required for source reproduction. The code and public aggregates alone cannot reproduce granular observations.

## Drive package layout and reproduction

The requested delivery layout puts code under `code/` and outputs/data at package root. For source reproduction, create an independent local repository-shaped workspace: copy the CONTENTS of `code/` into that workspace, then copy package `outputs/`, `paper/`, `presentation/` and personally acquired `data/raw_bloomberg/` into its root. Do not execute the source pipeline in the delivery directory. Never duplicate the shared First Rate archive: configure RISKLAB_DATA_ROOT to its official mounted location.

Safe metadata in `config/frozen/` mirrors original relative paths; restore needed specifications, selected lists and exact calendars to their original locations under ignored `outputs/diagnostics/` before source construction. The safe specification inventory records checksums and the FX-only portability amendment. Historical scripts also require their recorded stage/provenance metadata and reconstruct their granular outputs from licensed inputs; missing metadata must be investigated, never invented or bypassed. No hidden interim, analytic, prediction or fitted-model panels are included in delivery.

Follow the full-source order in `outputs/reproducibility/final_reproduction_guide.md` in that isolated workspace. Frozen-derived verification is a separate route for an existing licensed working archive. Full source reconstruction was not rerun or newly certified at publication. Historical artifact manifests remain records of earlier stages; `release_artifact_manifest.csv` is the publication checksum inventory. Packaging checks do not rewrite old analytical locks to accommodate differences.

The private Git bundle is recovery-only and excluded from both release and submission. Rewriting branch history does not change GitHub visibility settings or guarantee removal of provider excerpts from external clones, caches or pre-existing pull requests. No credentials or private acquisition observations belong in the public tree.
