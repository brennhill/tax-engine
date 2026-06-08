# Year Pipeline Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the repo into a year-based tax pipeline that preserves locked `2025` German and U.S. outputs while letting future source documents live under `years/<year>/raw/`.

**Architecture:** Add a shared `tax_pipeline` package for path resolution, manifest generation, and orchestration; migrate `2025` into the year layout; and retrofit the current scripts to consume year-aware paths instead of hardcoded repo-root filenames. Treat `2025` as the regression baseline and keep manual judgment inputs explicit in normalized files.

**Tech Stack:** Python 3, stdlib `unittest`, CSV/JSON/YAML-like normalized files, existing tax scripts

---

## Chunk 1: Scaffolding And Tests

### Task 1: Add failing tests for year-path and manifest behavior

**Files:**
- Create: `tests/test_year_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Test these behaviors:
- `YearPaths` resolves `raw`, `normalized`, and `outputs` under `years/2025/`
- the classifier recognizes representative docs such as Schwab 1099, Coinbase transaction CSVs, wage-tax PDFs, and JPM/Shareworks equity-comp docs
- manifest generation writes deterministic metadata for files under a temporary `raw/` tree

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL because `tax_pipeline` modules do not exist yet.

### Task 2: Implement the shared pipeline scaffolding

**Files:**
- Create: `tax_pipeline/__init__.py`
- Create: `tax_pipeline/paths.py`
- Create: `tax_pipeline/classify.py`
- Create: `tax_pipeline/manifest.py`

- [ ] **Step 1: Write minimal implementation**
- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS for the new scaffolding tests.

## Chunk 2: Year Runtime And Migration

### Task 3: Add runtime helpers for the legacy scripts

**Files:**
- Create: `tax_pipeline/legacy_runtime.py`

- [ ] **Step 1: Write failing tests for runtime path resolution if needed**
- [ ] **Step 2: Implement a small compatibility layer**

The compatibility layer should:
- read the active year from environment or default to `2025`
- resolve the active analysis/output directory
- expose helper functions for locating raw files from the manifest

### Task 4: Create the `years/2025` layout and migration utility

**Files:**
- Create: `tax_pipeline/migrate_2025.py`
- Create: `years/2025/raw/.gitkeep`
- Create: `years/2025/normalized/.gitkeep`
- Create: `years/2025/outputs/.gitkeep`

- [ ] **Step 1: Implement migration logic**

The migration should:
- create the directory tree
- populate `years/2025/raw/` from the current source documents
- copy or link the curated normalized inputs that the scripts still need

- [ ] **Step 2: Run migration and inspect results**

Run: `python3 -m tax_pipeline.migrate_2025`
Expected: `years/2025/` tree exists and contains usable raw/normalized/output structure.

## Chunk 3: Retrofit Existing Scripts

### Task 5: Make the current scripts year-aware

**Files:**
- Modify: `coinbase_private_sales_2025.py`
- Modify: `dher_german_2025.py`
- Modify: `german_tax_2025_model.py`
- Modify: `elster_2025_entry_sheet.py`
- Modify: `us_tax_2025_capital_workpaper.py`
- Modify: `us_tax_2025_model.py`
- Modify: `us_tax_2025_treaty_packet.py`

- [ ] **Step 1: Add failing tests or smoke checks around path expectations**
- [ ] **Step 2: Replace hardcoded repo-root paths with runtime helpers**
- [ ] **Step 3: Keep default behavior compatible with top-level `2025` execution**

## Chunk 4: Runner And Regression

### Task 6: Add the orchestration entry point

**Files:**
- Create: `tax_pipeline/run_year.py`

- [ ] **Step 1: Write a failing smoke test for the runner or define a manual regression command**
- [ ] **Step 2: Implement the orchestration order**

Suggested order:
- generate manifest
- run `coinbase_private_sales_2025.py`
- run `dher_german_2025.py`
- run `german_tax_2025_model.py`
- run `elster_2025_entry_sheet.py`
- run `us_tax_2025_capital_workpaper.py`
- run `us_tax_2025_model.py`
- run `us_tax_2025_treaty_packet.py`

### Task 7: Rebuild `2025` and verify parity

**Files:**
- Modify as needed from previous tasks

- [ ] **Step 1: Run the full pipeline**

Run: `python3 -m tax_pipeline.run_year 2025`

- [ ] **Step 2: Verify parity**

Check:
- German refund `3725.72 EUR`
- U.S. treaty refund `1126.54 USD`
- required year outputs exist

- [ ] **Step 3: Fix any parity drift and rerun**

## Chunk 5: Developer UX

### Task 8: Document future-year usage

**Files:**
- Create: `README.md` or `years/README.md`

- [ ] **Step 1: Document the `2026` workflow**

Include:
- where to drop docs
- which files remain manual/judgment inputs
- the single command to run
- where outputs appear

- [ ] **Step 2: Run the regression suite one final time**

Run:
- `python3 -m unittest discover -s tests -v`
- `python3 -m tax_pipeline.run_year 2025`

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-04-11-year-pipeline-design.md \
  docs/superpowers/plans/2026-04-11-year-pipeline-refactor.md \
  tax_pipeline tests years README.md \
  coinbase_private_sales_2025.py dher_german_2025.py german_tax_2025_model.py \
  elster_2025_entry_sheet.py us_tax_2025_capital_workpaper.py us_tax_2025_model.py \
  us_tax_2025_treaty_packet.py
git commit -m "Refactor tax repo into year-based pipeline"
```
