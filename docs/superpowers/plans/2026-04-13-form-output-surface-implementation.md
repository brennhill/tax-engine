# Form Output Surface Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add first-class Germany and USA form-by-form filing outputs under `years/<year>/outputs/forms/`, while preserving the locked 2025 results and keeping `analysis-steps/` as the audit surface.

**Architecture:** Introduce a small renderer layer that reads structured year inputs plus model outputs and writes country-specific form files under `outputs/forms/`. Keep tax logic in the existing tax-model scripts, but move human-facing filing instructions out of `analysis-steps/` into dedicated form packages with country indexes and one file per filing form.

**Tech Stack:** Python 3 standard library, existing year-path helpers, markdown generation, unittest regression tests

---

## File Structure

### Existing files to modify

- Modify: `tax_pipeline/paths.py`
  - Add first-class `forms_root`, `germany_forms_root`, and `usa_forms_root` year paths.
- Modify: `tax_pipeline/run_year.py`
  - Stabilize the current partial output-rename work.
  - Print the approved stdout summary.
  - Invoke the new form-output renderers after tax models complete.
- Modify: `README.md`
  - Document the new `outputs/forms/` surface and update examples to point at the new form indexes.
- Modify: `elster_2025_entry_sheet.py`
  - Stop acting as the only Germany filing surface.
  - Continue producing Germany audit summaries in `analysis-steps/`.
- Modify: `us_tax_2025_treaty_packet.py`
  - Stop acting as the only USA filing surface.
  - Continue producing USA audit summaries in `analysis-steps/`.
- Modify: `german_tax_2025_model.py`
  - Rename active outputs to readable filenames and keep model JSON/trace/summaries usable by the new Germany renderer.
- Modify: `coinbase_private_sales_2025.py`
  - Rename active outputs to readable filenames.
- Modify: `dher_german_2025.py`
  - Rename active outputs to readable filenames.
- Modify: `us_tax_2025_capital_workpaper.py`
  - Rename active outputs to readable filenames.
- Modify: `us_tax_2025_model.py`
  - Rename active outputs to readable filenames.
- Modify: `tests/test_year_pipeline.py`
  - Update output expectations, add stdout checks, and assert the new form package is generated.

### New files to create

- Create: `tax_pipeline/forms/__init__.py`
  - Expose the form-rendering entry points.
- Create: `tax_pipeline/forms/common.py`
  - Shared helpers for markdown tables, link generation, currency formatting, and output writing.
- Create: `tax_pipeline/forms/germany.py`
  - Render the Germany form package under `outputs/forms/germany/`.
- Create: `tax_pipeline/forms/usa.py`
  - Render the USA form package under `outputs/forms/usa/`.
- Create: `tests/test_form_outputs.py`
  - Focused tests for generated country indexes and representative form files.

### Output files the implementation must generate

#### Germany

- Create: `years/2025/outputs/forms/germany/index.md`
- Create: `years/2025/outputs/forms/germany/2025_hauptvordruck.md`
- Create: `years/2025/outputs/forms/germany/2025_anlage_n_person_1.md`
- Create: `years/2025/outputs/forms/germany/2025_anlage_n_person_2.md`
- Create: `years/2025/outputs/forms/germany/2025_anlage_kap_person_1.md`
- Create: `years/2025/outputs/forms/germany/2025_anlage_kap_person_2.md`
- Create: `years/2025/outputs/forms/germany/2025_anlage_kap_inv.md`
- Create: `years/2025/outputs/forms/germany/2025_anlage_so.md`

#### USA

- Create: `years/2025/outputs/forms/usa/index.md`
- Create: `years/2025/outputs/forms/usa/2025_1040.md`
- Create: `years/2025/outputs/forms/usa/2025_schedule_1.md`
- Create: `years/2025/outputs/forms/usa/2025_schedule_b.md`
- Create: `years/2025/outputs/forms/usa/2025_schedule_d.md`
- Create: `years/2025/outputs/forms/usa/2025_form_8949.md`
- Create: `years/2025/outputs/forms/usa/2025_form_6781.md`
- Create: `years/2025/outputs/forms/usa/2025_form_8960.md`
- Create: `years/2025/outputs/forms/usa/2025_form_1116_passive.md`
- Create: `years/2025/outputs/forms/usa/2025_form_1116_general.md`

### Output filename cleanup in `analysis-steps/`

Replace the old numbered active output names with readable names. Keep `analysis-steps/` as the audit surface, but make it readable:

- `091-model-results.json` -> `germany-model-results.json`
- `092-model-trace.csv` -> `germany-model-trace.csv`
- `093-final-results-summary.md` -> `germany-summary.md`
- `098-coinbase-private-sales-lot-detail.csv` -> `crypto-private-sales-lot-detail.csv`
- `099-coinbase-private-sales-dispositions.csv` -> `crypto-private-sales-dispositions.csv`
- `100-coinbase-private-sales-summary.md` -> `crypto-private-sales-summary.md`
- `101-coinbase-private-sales-results.json` -> `crypto-private-sales-results.json`
- `111-dher-german-capital-detail.csv` -> `germany-dher-capital-detail.csv`
- `112-dher-german-results.json` -> `germany-dher-results.json`
- `113-dher-german-summary.md` -> `germany-dher-summary.md`
- `114-elster-entry-sheet.md` -> `germany-elster-entry-sheet.md`
- `115-kap-inv-fund-summary.csv` -> `germany-kap-inv-fund-summary.csv`
- `116-n-werbungskosten-breakdown.csv` -> `germany-n-work-expenses.csv`
- `117-elster-kap-summary.csv` -> `germany-kap-summary.csv`
- `121-us-2025-capital-results.json` -> `us-capital-results.json`
- `122-us-2025-capital-summary.md` -> `us-capital-summary.md`
- `123-us-2025-8949-and-income-buckets.csv` -> `us-form-8949-income-buckets.csv`
- `125-us-2025-tax-estimate.json` -> `us-tax-estimate.json`
- `126-us-2025-tax-estimate.md` -> `us-tax-estimate.md`
- `127-us-2025-tax-trace.csv` -> `us-tax-trace.csv`
- `130-spouse-bank-capital-certificate-summary.md` -> `spouse-bank-capital-certificate-summary.md`
- `131-us-2025-chosen-treaty-package.json` -> `us-treaty-package.json`
- `132-us-2025-treaty-resourcing-worksheet.csv` -> `us-treaty-resourcing-worksheet.csv`
- `133-us-2025-treaty-entry-sheet.md` -> `us-treaty-entry-sheet.md`
- `134-us-2025-supporting-statements.md` -> `us-supporting-statements.md`

The already-obsolete bridge files should remain removable by `run_year.py` and should not be regenerated as active outputs:

- `067-ecb-usd-eur-daily-2022-2025.csv`
- `070-capital-sales-detail.csv`
- `072-2025-income-cashflows.csv`
- `090-model-inputs.csv`
- `120-us-2025-capital-inputs.csv`
- `124-us-2025-tax-model-inputs.csv`

## Chunk 1: Stabilize Output Paths And Naming

### Task 1: Add first-class forms output paths

**Files:**
- Modify: `tax_pipeline/paths.py`
- Test: `tests/test_year_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add assertions that `YearPaths.for_year(...)` exposes:
- `forms_root`
- `germany_forms_root`
- `usa_forms_root`

Expected paths:
- `years/2025/outputs/forms`
- `years/2025/outputs/forms/germany`
- `years/2025/outputs/forms/usa`

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_year_pipeline.TestYearPaths -v`
Expected: FAIL because the new `YearPaths` attributes do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Update `tax_pipeline/paths.py`:
- add the new dataclass fields
- derive the new paths in `for_year`
- create the directories in `ensure_directories()`

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_year_pipeline.TestYearPaths -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/paths.py tests/test_year_pipeline.py
git commit -m "Add forms output paths to year layout"
```

### Task 2: Stabilize `run_year.py` and approved stdout summary

**Files:**
- Modify: `tax_pipeline/run_year.py`
- Test: `tests/test_year_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add a test that:
- creates temp `germany-model-results.json`
- creates temp `us-tax-estimate.json`
- calls the summary printer
- asserts exact stdout:

```text
Year 2025 complete
  Germany refund: 3725.72 EUR
  U.S. base refund: 428.64 USD
  U.S. treaty refund: 1126.54 USD
  Outputs: years/2025/outputs/analysis-steps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_year_pipeline.TestRunYearSummary -v`
Expected: FAIL until the helper is covered and wired correctly.

- [ ] **Step 3: Write minimal implementation**

In `tax_pipeline/run_year.py`:
- keep the approved summary format
- ensure it reads the renamed output files
- keep removal of obsolete numbered outputs
- do not reintroduce legacy compatibility CSV generation

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_year_pipeline.TestRunYearSummary -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/run_year.py tests/test_year_pipeline.py
git commit -m "Stabilize run-year summary output"
```

### Task 3: Rename active `analysis-steps` outputs to readable names

**Files:**
- Modify: `coinbase_private_sales_2025.py`
- Modify: `dher_german_2025.py`
- Modify: `german_tax_2025_model.py`
- Modify: `elster_2025_entry_sheet.py`
- Modify: `us_tax_2025_capital_workpaper.py`
- Modify: `us_tax_2025_model.py`
- Modify: `us_tax_2025_treaty_packet.py`
- Modify: `README.md`
- Test: `tests/test_year_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add an integration-style test that runs the 2025 pipeline and asserts:
- the readable `analysis-steps` filenames exist
- the numbered active outputs do not exist

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_year_pipeline.TestReadableAnalysisOutputs -v`
Expected: FAIL because scripts still emit old filenames.

- [ ] **Step 3: Write minimal implementation**

Update each script’s path constants and internal cross-references to use the readable filenames listed in the file-structure section.

Update `README.md` to reference the readable output names and the future `forms/` indexes instead of numbered markdown files.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_year_pipeline.TestReadableAnalysisOutputs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add README.md coinbase_private_sales_2025.py dher_german_2025.py german_tax_2025_model.py elster_2025_entry_sheet.py us_tax_2025_capital_workpaper.py us_tax_2025_model.py us_tax_2025_treaty_packet.py tests/test_year_pipeline.py
git commit -m "Rename analysis outputs for readability"
```

## Chunk 2: Add Germany Form Package

### Task 4: Add shared form-rendering helpers

**Files:**
- Create: `tax_pipeline/forms/__init__.py`
- Create: `tax_pipeline/forms/common.py`
- Test: `tests/test_form_outputs.py`

- [ ] **Step 1: Write the failing test**

Add tests for helper behavior:
- stable markdown heading rendering
- line-table rendering
- output writing into country/year form folders

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_form_outputs.TestFormHelpers -v`
Expected: FAIL because the module does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement:
- `write_form(path, title, posture_lines, entries, notes)`
- a small row model or helper for line/box entries
- common currency/string formatting helpers that do not duplicate tax logic

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_form_outputs.TestFormHelpers -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/forms/__init__.py tax_pipeline/forms/common.py tests/test_form_outputs.py
git commit -m "Add shared form rendering helpers"
```

### Task 5: Render Germany form files

**Files:**
- Create: `tax_pipeline/forms/germany.py`
- Modify: `elster_2025_entry_sheet.py`
- Modify: `tax_pipeline/run_year.py`
- Test: `tests/test_form_outputs.py`

- [ ] **Step 1: Write the failing test**

Add a test that runs the 2025 pipeline and asserts these files exist:
- `outputs/forms/germany/index.md`
- `2025_hauptvordruck.md`
- `2025_anlage_n_person_1.md`
- `2025_anlage_n_person_2.md`
- `2025_anlage_kap_person_1.md`
- `2025_anlage_kap_person_2.md`
- `2025_anlage_kap_inv.md`
- `2025_anlage_so.md`

Also assert:
- Germany index contains `3725.72 EUR`
- one representative line appears in a form file, for example:
  - `Anlage KAP Zeile 19`
  - `Anlage N Zeilen 54-56`
  - `Anlage SO`

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_form_outputs.TestGermanyForms -v`
Expected: FAIL because the renderer does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement `tax_pipeline/forms/germany.py`:
- read the readable Germany model outputs and ELSTER summary outputs
- render `index.md`
- render one file per Germany form

Update `tax_pipeline/run_year.py` to invoke the Germany renderer after the existing model scripts complete.

Keep `elster_2025_entry_sheet.py` focused on generating Germany audit summaries in `analysis-steps/`; do not move tax logic into the renderer.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_form_outputs.TestGermanyForms -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/forms/germany.py tax_pipeline/run_year.py elster_2025_entry_sheet.py tests/test_form_outputs.py
git commit -m "Add Germany form output package"
```

## Chunk 3: Add USA Form Package

### Task 6: Render USA form files

**Files:**
- Create: `tax_pipeline/forms/usa.py`
- Modify: `us_tax_2025_treaty_packet.py`
- Modify: `tax_pipeline/run_year.py`
- Test: `tests/test_form_outputs.py`

- [ ] **Step 1: Write the failing test**

Add a test that runs the 2025 pipeline and asserts these files exist:
- `outputs/forms/usa/index.md`
- `2025_1040.md`
- `2025_schedule_1.md`
- `2025_schedule_b.md`
- `2025_schedule_d.md`
- `2025_form_8949.md`
- `2025_form_6781.md`
- `2025_form_8960.md`
- `2025_form_1116_passive.md`
- `2025_form_1116_general.md`

Also assert:
- USA index contains `1126.54 USD`
- `2025_1040.md` contains representative line values like:
  - `Line 1h`
  - `Line 35a`
- one `1116` form file includes the treaty-resourcing posture

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_form_outputs.TestUSAForms -v`
Expected: FAIL because the USA renderer does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Implement `tax_pipeline/forms/usa.py`:
- read the readable U.S. capital results, tax estimate, treaty package, and supporting statement outputs
- render `index.md`
- render one file per U.S. form
- keep the renderer line-oriented and source-oriented, not logic-oriented

Update `tax_pipeline/run_year.py` to invoke the USA renderer after tax scripts complete.

Keep `us_tax_2025_treaty_packet.py` focused on generating audit/filing-support artifacts in `analysis-steps/`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_form_outputs.TestUSAForms -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/forms/usa.py tax_pipeline/run_year.py us_tax_2025_treaty_packet.py tests/test_form_outputs.py
git commit -m "Add USA form output package"
```

## Chunk 4: Full Regression And Docs

### Task 7: Update docs and final integration checks

**Files:**
- Modify: `README.md`
- Modify: `tests/test_year_pipeline.py`
- Modify: `tests/test_form_outputs.py`

- [ ] **Step 1: Write the failing test**

Add or update the main integration test to assert:
- `python3 -m tax_pipeline.run_year 2025` produces the readable analysis files
- `outputs/forms/germany/index.md` exists
- `outputs/forms/usa/index.md` exists
- the headline results remain locked:
  - Germany `3725.72 EUR`
  - U.S. base `428.64 USD`
  - U.S. treaty `1126.54 USD`

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest discover -s tests -v`
Expected: FAIL until all file names, renderers, and docs are aligned.

- [ ] **Step 3: Write minimal implementation**

Update `README.md`:
- show the new `outputs/forms/` structure
- point users to:
  - `years/<year>/outputs/forms/germany/index.md`
  - `years/<year>/outputs/forms/usa/index.md`
- document that `analysis-steps/` remains the audit surface

- [ ] **Step 4: Run the full verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m tax_pipeline.run_year 2025
```

Expected:
- all tests PASS
- stdout ends with:

```text
Year 2025 complete
  Germany refund: 3725.72 EUR
  U.S. base refund: 428.64 USD
  U.S. treaty refund: 1126.54 USD
  Outputs: years/2025/outputs/analysis-steps
```

- `years/2025/outputs/forms/germany/index.md` exists
- `years/2025/outputs/forms/usa/index.md` exists

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_year_pipeline.py tests/test_form_outputs.py years/2025/outputs/forms
git commit -m "Add first-class form output packages"
```

## Execution Notes

- Keep tax logic in existing model scripts.
- Do not move filing calculations into the new renderer layer.
- Treat `analysis-steps/` as the audit and validation surface.
- Treat `outputs/forms/` as the filing-instructions surface.
- Prefer explicit zeros and blanks over silent omissions in form files.
- If a renderer is blocked by a missing model output, fail loudly with the missing file path.

## Done Criteria

The work is complete when:

- `python3 -m tax_pipeline.run_year 2025` succeeds
- the approved stdout summary prints
- `analysis-steps/` uses readable active filenames
- `outputs/forms/germany/` contains the Germany form package
- `outputs/forms/usa/` contains the USA form package
- the 2025 locked results remain:
  - Germany refund `3725.72 EUR`
  - U.S. base refund `428.64 USD`
  - U.S. treaty refund `1126.54 USD`
