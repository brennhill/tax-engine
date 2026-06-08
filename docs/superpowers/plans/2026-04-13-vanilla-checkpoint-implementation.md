# Vanilla Checkpoint Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one wage-only, default-deductions-only checkpoint for Germany and one for the U.S. so commercial tax software can validate the non-treaty, non-capital core math independently from the full filing result.

**Architecture:** Keep the checkpoint on the same pure law-core path as the main models. Add a small pure scenario-derivation helper that converts the full year inputs into a wage-only checkpoint scenario, then have the existing Germany and U.S. model writers serialize that checkpoint into their canonical JSON and summary Markdown. Finally, extend `run_year` headline output to print the new checkpoint values.

**Tech Stack:** Python 3, `unittest`, dataclasses, existing year-runtime/pipeline modules, Markdown/JSON output writers.

---

## File Structure

- Modify: `tax_pipeline/run_year.py`
  - Extend stdout headline summary to print Germany and U.S. vanilla checkpoint values from the canonical result JSON files.
- Create: `tax_pipeline/pipelines/y2025/vanilla_checkpoint.py`
  - Pure helper functions that derive wage-only checkpoint scenarios from the existing structured Germany and U.S. assessment inputs and produce small serializable checkpoint result dataclasses.
- Modify: `tax_pipeline/pipelines/y2025/germany_model.py`
  - Compute the Germany checkpoint from the same ordinary-input law path, write it into `germany-model-results.json`, and render it into `germany-summary.md`.
- Modify: `tax_pipeline/pipelines/y2025/us_model.py`
  - Compute the U.S. checkpoint from the same U.S. law path, write it into `us-tax-estimate.json`, and render it into `us-tax-estimate.md`.
- Create: `tests/test_vanilla_checkpoint.py`
  - Focused pure-function coverage for the new scenario-derivation helpers so they stay law-core driven and exclude treaty/capital/discretionary items.
- Modify: `tests/test_year_pipeline.py`
  - Extend stdout-summary tests for the new lines and labels.
- Modify: `README.md`
  - Briefly document what the vanilla checkpoint means and what it is for.

## Chunk 1: Pure Checkpoint Contract

### Task 1: Add failing tests for the pure scenario boundary

**Files:**
- Create: `tests/test_vanilla_checkpoint.py`
- Reference: `tax_pipeline/germany_2025_law.py`
- Reference: `tax_pipeline/us_2025_law.py`
- Planned Create: `tax_pipeline/pipelines/y2025/vanilla_checkpoint.py`

- [ ] **Step 1: Write the failing Germany checkpoint test**

```python
def test_germany_vanilla_checkpoint_zeroes_capital_and_discretionary_items():
    checkpoint = compute_germany_vanilla_checkpoint(...)
    assert checkpoint.taxable_income_eur == Decimal("...")
    assert checkpoint.refund_or_balance_due_eur == Decimal("...")
```

- [ ] **Step 2: Write the failing U.S. checkpoint test**

```python
def test_usa_vanilla_checkpoint_keeps_only_wages_standard_deduction_and_payment():
    checkpoint = compute_usa_vanilla_checkpoint(...)
    assert checkpoint.adjusted_gross_income_usd == Decimal("...")
    assert checkpoint.regular_tax_usd == Decimal("...")
    assert checkpoint.refund_or_balance_due_usd == Decimal("...")
```

- [ ] **Step 3: Add explicit exclusion assertions**

```python
assert checkpoint excludes treaty / FTC / NIIT / dividends / interest / Schedule 1 other income
assert checkpoint excludes home office / work equipment / staking / private sales / capital taxes
```

- [ ] **Step 4: Run the new test file to confirm failure**

Run: `python3 -m unittest tests.test_vanilla_checkpoint -v`

Expected: failures because the checkpoint helper module and functions do not exist yet.

- [ ] **Step 5: Create the pure checkpoint helper module**

Implement in `tax_pipeline/pipelines/y2025/vanilla_checkpoint.py`:

- small checkpoint result dataclasses:
  - `GermanyVanillaCheckpoint2025`
  - `USAVanillaCheckpoint2025`
- pure scenario-derivation helpers:
  - `derive_germany_vanilla_inputs_2025(...)`
  - `compute_germany_vanilla_checkpoint_2025(...)`
  - `derive_usa_vanilla_inputs_2025(...)`
  - `compute_usa_vanilla_checkpoint_2025(...)`

Guidance:
- Germany helper should:
  - keep wage facts and prepayments
  - zero `other_income_22nr3_eur`
  - zero all discretionary person-level deductions:
    - home office days
    - telecom deduction
    - employment legal-insurance deduction
    - cross-border tax-help deduction
    - work-equipment items
  - then call `compute_joint_ordinary_assessment_2025`
- U.S. helper should:
  - keep wages and estimated payment
  - zero all capital/source-fact non-wage items:
    - dividends
    - interest
    - substitute payments
    - staking
    - capital gains/loss inputs
    - foreign tax
    - FTC carryovers
  - disable treaty re-sourcing for the checkpoint scenario
  - then call `compute_us_assessment_2025`

- [ ] **Step 6: Run the pure checkpoint tests and make them pass**

Run: `python3 -m unittest tests.test_vanilla_checkpoint -v`

Expected: PASS

- [ ] **Step 7: Commit the pure checkpoint helper**

```bash
git add tax_pipeline/pipelines/y2025/vanilla_checkpoint.py tests/test_vanilla_checkpoint.py
git commit -m "Add pure vanilla checkpoint helpers"
```

## Chunk 2: Germany Output Wiring

### Task 2: Add Germany checkpoint to canonical results and summary

**Files:**
- Modify: `tax_pipeline/pipelines/y2025/germany_model.py`
- Test: `tests/test_vanilla_checkpoint.py`

- [ ] **Step 1: Add a failing output-shape test**

Extend `tests/test_vanilla_checkpoint.py` with an assertion that the Germany model JSON/summary contract includes:

```python
results["vanilla_checkpoint"]["taxable_income_eur"]
results["vanilla_checkpoint"]["income_tax_eur"]
results["vanilla_checkpoint"]["soli_eur"]
results["vanilla_checkpoint"]["total_tax_eur"]
results["vanilla_checkpoint"]["refund_or_balance_due_eur"]
```

and that `germany-summary.md` contains:

```text
## Vanilla checkpoint for commercial software comparison
```

- [ ] **Step 2: Run the Germany checkpoint-output test to confirm failure**

Run: `python3 -m unittest tests.test_vanilla_checkpoint -v`

Expected: FAIL because the model output does not contain the new section yet.

- [ ] **Step 3: Wire the checkpoint into `germany_model.py`**

Implementation notes:
- import the pure helper from `tax_pipeline/pipelines/y2025/vanilla_checkpoint.py`
- compute the checkpoint immediately after `ordinary = compute_joint_ordinary_assessment_2025(...)`
- serialize it under `results["vanilla_checkpoint"]`
- render a dedicated summary section that explains:
  - wage income only
  - no KAP/KAP-INV
  - no treaty credit
  - no `§ 22`
  - no `§ 23`
  - no discretionary deductions

- [ ] **Step 4: Re-run the targeted test**

Run: `python3 -m unittest tests.test_vanilla_checkpoint -v`

Expected: Germany checkpoint assertions PASS.

- [ ] **Step 5: Commit the Germany output wiring**

```bash
git add tax_pipeline/pipelines/y2025/germany_model.py tests/test_vanilla_checkpoint.py
git commit -m "Add Germany vanilla checkpoint outputs"
```

## Chunk 3: U.S. Output Wiring

### Task 3: Add U.S. checkpoint to canonical results and summary

**Files:**
- Modify: `tax_pipeline/pipelines/y2025/us_model.py`
- Test: `tests/test_vanilla_checkpoint.py`

- [ ] **Step 1: Add a failing U.S. output-shape test**

Extend the test file with assertions that `us-tax-estimate.json` now includes:

```python
results["vanilla_checkpoint"]["adjusted_gross_income_usd"]
results["vanilla_checkpoint"]["taxable_income_usd"]
results["vanilla_checkpoint"]["regular_tax_usd"]
results["vanilla_checkpoint"]["total_tax_usd"]
results["vanilla_checkpoint"]["refund_or_balance_due_usd"]
```

and that `us-tax-estimate.md` contains:

```text
## Vanilla checkpoint for commercial software comparison
```

- [ ] **Step 2: Run the targeted test to confirm failure**

Run: `python3 -m unittest tests.test_vanilla_checkpoint -v`

Expected: FAIL because the U.S. model output does not contain the new section yet.

- [ ] **Step 3: Wire the checkpoint into `us_model.py`**

Implementation notes:
- import the pure helper from `tax_pipeline/pipelines/y2025/vanilla_checkpoint.py`
- compute the checkpoint from the same structured `USAssessmentInputs2025`
- serialize it under `results["vanilla_checkpoint"]`
- render a dedicated summary section that explains:
  - wages only
  - standard deduction only
  - no dividends, interest, capital, NIIT, FTC, or treaty
  - estimated payment still included

- [ ] **Step 4: Re-run the targeted test**

Run: `python3 -m unittest tests.test_vanilla_checkpoint -v`

Expected: U.S. checkpoint assertions PASS.

- [ ] **Step 5: Commit the U.S. output wiring**

```bash
git add tax_pipeline/pipelines/y2025/us_model.py tests/test_vanilla_checkpoint.py
git commit -m "Add U.S. vanilla checkpoint outputs"
```

## Chunk 4: Headline Summary and Documentation

### Task 4: Expose the checkpoint in `run_year` stdout and document it

**Files:**
- Modify: `tax_pipeline/run_year.py`
- Modify: `tests/test_year_pipeline.py`
- Modify: `README.md`

- [ ] **Step 1: Add failing stdout tests**

Extend `RunnerTest` in `tests/test_year_pipeline.py` so `print_headline_summary()` expects:

```text
  Germany vanilla checkpoint refund: ...
  U.S. vanilla checkpoint refund: ...
```

and the balance-due variant if the checkpoint result is negative.

- [ ] **Step 2: Run the runner tests to confirm failure**

Run: `python3 -m unittest tests.test_year_pipeline.RunnerTest -v`

Expected: FAIL because `print_headline_summary()` does not print checkpoint lines yet.

- [ ] **Step 3: Update `print_headline_summary()`**

Implementation notes:
- read `vanilla_checkpoint` from:
  - `germany-model-results.json`
  - `us-tax-estimate.json`
- use the existing `_refund_or_balance_due()` helper
- print the checkpoint lines between the main result and the output path

- [ ] **Step 4: Document the checkpoint meaning**

Add a short README note describing:
- it is intended for commercial software comparison
- it strips non-wage income and discretionary deductions
- it is not the filing result

- [ ] **Step 5: Re-run the runner tests**

Run: `python3 -m unittest tests.test_year_pipeline.RunnerTest -v`

Expected: PASS

- [ ] **Step 6: Commit the headline/docs pass**

```bash
git add tax_pipeline/run_year.py tests/test_year_pipeline.py README.md
git commit -m "Expose vanilla checkpoint summaries"
```

## Chunk 5: End-to-End Regression

### Task 5: Prove the new checkpoint did not change the full filing outputs

**Files:**
- Verify only

- [ ] **Step 1: Run the full test suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: PASS

- [ ] **Step 2: Re-run the full 2025 pipeline**

Run: `python3 -m tax_pipeline.run_year 2025`

Expected:
- full pipeline completes
- Germany final filing result remains unchanged
- U.S. base and treaty filing results remain unchanged
- stdout now includes the checkpoint lines

- [ ] **Step 3: Inspect the generated summaries**

Check:
- `years/2025/outputs/analysis-steps/germany-summary.md`
- `years/2025/outputs/analysis-steps/us-tax-estimate.md`
- `years/2025/outputs/analysis-steps/germany-model-results.json`
- `years/2025/outputs/analysis-steps/us-tax-estimate.json`

Expected:
- both summaries contain the checkpoint section
- both JSON files contain the checkpoint block
- no treaty/capital/discretionary items appear inside the checkpoint block

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "Add wage-only vanilla checkpoint outputs"
```
