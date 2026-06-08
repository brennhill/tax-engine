# Year Pipeline Design

**Goal**

Refactor the `taxes-2025` repo into a year-based tax pipeline where source documents live under `years/<year>/raw/`, derived inputs live under `years/<year>/normalized/`, generated artifacts live under `years/<year>/outputs/`, and a single runner can rebuild the year from those inputs while preserving the locked `2025` results as the regression baseline.

**Approved Direction**

Use the current `2025` tax work as the first supported year and gate the refactor on parity with the locked results:

- Germany refund: `3725.72 EUR`
- U.S. treaty re-sourcing refund: `1126.54 USD`

This is intentionally not a full greenfield rewrite. The repo already contains working tax logic, but it is split across:

- raw source documents in the repo root,
- manually curated intermediate CSV and JSON files in `analysis-steps/`,
- year-specific scripts with hardcoded filenames and output paths.

The refactor should preserve that logic, make the pathing year-aware, and add a documented automation boundary for anything that still requires a manual override or judgment call.

## Architecture

### 1. Year-based filesystem layout

Each tax year gets its own subtree:

- `years/<year>/raw/`
- `years/<year>/normalized/`
- `years/<year>/outputs/`

`raw/` is the user drop zone. It is subdivided by source class:

- `germany/`
- `us/`
- `brokers/`
- `crypto/`
- `equity_comp/`
- `receipts/`
- `real_estate/`

`normalized/` stores the canonical extracted and curated inputs that the models run on:

- `documents.json`
- `judgment_calls.yaml`
- model input CSV/JSON files that are still required by the current scripts

`outputs/` stores generated artifacts:

- `analysis-steps/`
- optional top-level summary files for that year

### 2. Shared pipeline code

Create a small reusable package, `tax_pipeline/`, with these responsibilities:

- `paths.py`
  - resolve project root, year root, raw/normalized/output paths
  - expose a single `YearPaths` object for all scripts
- `classify.py`
  - classify dropped files by filename/path pattern
  - attach coarse metadata such as tax year, source family, and owner when determinable
- `manifest.py`
  - scan `raw/` and write `normalized/documents.json`
- `legacy_runtime.py`
  - provide compatibility helpers for the existing year-specific scripts so they can read the active year and output directory from environment variables instead of hardcoded repo-root paths
- `run_year.py`
  - orchestrate manifest generation plus the existing calculation scripts in the correct order

### 3. Honest automation boundary

The current repo does not yet contain raw-document parsers for every curated input.

The refactor should therefore draw a clean line between:

- inputs already derivable from existing logic and source files,
- inputs that still need manual or judgment-call support.

Those manual items should be explicit and centralized in `years/<year>/normalized/` instead of being scattered across ad hoc top-level files.

Examples of judgment-call or curated items that remain in scope:

- treaty re-sourcing posture
- `Aktienfonds` vs non-`Aktienfonds` classifications
- employee-equity basis decisions where broker records are incomplete or transferred
- manual deductions and work-use percentages
- prior-year carryover notices

### 4. 2025 as regression year

The refactor is only acceptable if the pipeline can rebuild the locked `2025` outputs.

Minimum parity checks:

- German final refund remains `3725.72 EUR`
- U.S. treaty re-sourcing refund remains `1126.54 USD`
- key output files are reproduced under the year output tree

### 5. Migration strategy

The migration should be conservative:

- keep the existing top-level scripts
- make them year-aware through shared runtime helpers
- create a `years/2025/` tree and populate it from the current repo state
- use symlinks or copies where that is less risky than moving source files

The point is to make `2026` a clean drop-in year without destabilizing the already-validated `2025` work.

## Error Handling

The runner should fail with a useful message when:

- required year directories are missing,
- required normalized inputs are absent,
- required raw document classes are absent for a script being run.

It should also produce a manifest even if not all downstream steps can run, so the user can see what the pipeline recognized.

## Testing

Testing should cover:

- `YearPaths` directory resolution
- file classification and manifest generation
- orchestration wiring
- `2025` regression verification via full pipeline execution

The regression checks are the real acceptance gate for the refactor.
