# Filing Posture Implementation Plan

> **Goal:** Add explicit per-jurisdiction filing posture support, runtime jurisdiction gating, and Germany single/joint/separate handling while keeping the existing U.S. path explicit and stable.

## File Structure

- Modify: `tax_pipeline/scaffold_year.py`
  - Make filing posture explicit in scaffolded config and sync from CSV.
- Modify: `tax_pipeline/run_year.py`
  - Add enabled-jurisdiction gating for module execution, forms, and legal-audit surfaces.
- Modify: `tax_pipeline/germany_2025_inputs.py`
  - Load explicit Germany filing posture and validate one-person vs two-person household shape.
- Modify: `tax_pipeline/germany_2025_law.py`
  - Support `single`, `married_joint`, and `married_separate`.
- Modify: `tax_pipeline/pipelines/y2025/germany_model.py`
  - Make output generation posture-aware and skip spouse-bank logic when absent.
- Modify: `tax_pipeline/pipelines/y2025/germany_elster_entry_sheet.py`
  - Render one-person and separate-assessment surfaces without hard `person_2` assumptions.
- Modify: `tax_pipeline/forms/germany.py`
  - Render only applicable forms and adjust filing wording by Germany posture.
- Modify: `tax_pipeline/us_2025_inputs.py`
  - Make U.S. filing posture explicit and allow single-person loading.
- Modify: `tests/test_year_pipeline.py`
- Modify: `tests/test_germany_2025_law.py`
- Modify: `tests/test_form_outputs.py`

## Chunk 1: Config and Runtime Contract

- [ ] Add failing tests for explicit filing-posture sync from `elections.csv`.
- [ ] Add failing tests for enabled-jurisdiction gating in `run_year`.
- [ ] Implement scaffold/profile sync for:
  - enabled jurisdictions
  - Germany filing posture
  - U.S. filing posture
- [ ] Implement `run_year` gating so only enabled jurisdictions run and render.

## Chunk 2: Germany Single and Separate Law Paths

- [ ] Add failing Germany law tests for:
  - one-person single assessment
  - two-person married separate assessment
- [ ] Refactor Germany law dataclasses and computation to branch on filing posture.
- [ ] Preserve existing married-joint regression behavior.

## Chunk 3: Germany Output Surfaces

- [ ] Add failing Germany output tests for:
  - one-person forms package
  - one-person ELSTER entry sheet
  - separate married posture wording
- [ ] Make Germany model output conditional on filing posture and available people.
- [ ] Remove hard spouse-bank rendering when no second person exists.
- [ ] Update form generation and `Hauptvordruck` wording.

## Chunk 4: U.S. Explicit Posture Loading

- [ ] Add failing tests for explicit U.S. filing posture loading.
- [ ] Allow single-person U.S. config without requiring spouse fields.
- [ ] Keep unsupported married U.S. postures raising loudly.

## Chunk 5: Verification

- [ ] Run targeted tests for:
  - `tests/test_year_pipeline.py`
  - `tests/test_germany_2025_law.py`
  - `tests/test_form_outputs.py`
- [ ] Run full suite:
  - `python3 -m unittest discover -s tests -v`
- [ ] If feasible, run one synthetic Germany-only year path smoke check.
