# Germany Legal Audit Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace approximation-based Germany wage-side logic with exact 2025 law-driven computation, while preserving explicit manual tax positions for non-mechanical judgments.

**Architecture:** Extend Germany wage facts extraction, add structured loaders for Germany wage/manual tax-position inputs, compute the ordinary-income side exactly in `german_tax_2025_model.py`, and emit a legal-order trace that links every mechanical step to an official source. Keep the separate capital-tax and treaty/manual-position layers explicit.

**Tech Stack:** Python, CSV/JSON structured inputs, deterministic PDF extraction, unittest

---

### Task 1: Extend Germany wage facts and structured input loading

**Files:**
- Modify: `tax_pipeline/providers/shared/german_lohnsteuerbescheinigung.py`
- Modify: `tests/test_fact_extraction.py`
- Modify: `tax_pipeline/analysis_inputs.py`
- Create or modify: `years/2025/normalized/facts/de-wage-source-facts.csv`

- [ ] Add extraction for wage-certificate lines `22` to `27` with stable semantic fact keys.
- [ ] Add tests for person 1 and person 2 sample text covering lines `22` to `27`.
- [ ] Add structured loader support for Germany wage source facts.
- [ ] Verify the facts pipeline still regenerates cleanly.

### Task 2: Move Germany manual positions into explicit structured inputs

**Files:**
- Modify: `tax_pipeline/analysis_inputs.py`
- Modify: `years/2025/outputs/tax-positions/de-model-assumptions.csv`
- Modify: `years/2025/config/manual_overrides.json`
- Modify: `elster_2025_entry_sheet.py`

- [ ] Replace approximation-only Germany assumptions with explicit manual tax-position rows.
- [ ] Add configured home-office and telecom factual inputs instead of hidden literals.
- [ ] Keep treaty credit, legal-insurance share, and tax-help share explicit as manual positions with notes.
- [ ] Remove the old Germany dependence on `zero_capital_refund_no34_eur`, `equipment_tax_savings_rate`, and `other_income_tax_rate_approx`.

### Task 3: Implement exact Germany ordinary-income computation

**Files:**
- Modify: `german_tax_2025_model.py`
- Test: `tests/test_year_pipeline.py`
- Test: `tests/test_form_outputs.py`

- [ ] Add exact `§ 32a EStG` 2025 tariff helpers for basic and splitting tariff.
- [ ] Add exact ordinary-income calculation ordering based on `§ 2`, `§ 9`, `§ 9a`, `§ 10`, `§ 10c`, and `§ 32a`.
- [ ] Compute exact effects of:
  - work equipment,
  - home-office days,
  - telecom simplification,
  - legal-insurance share,
  - tax-help share,
  - `§ 22 Nr. 3` staking income.
- [ ] Compute wage-side withholding/prepayment credit exactly under `§ 36 EStG`.
- [ ] Preserve separate capital-tax and fund-treatment logic.

### Task 4: Strengthen the legal audit surface

**Files:**
- Modify: `german_tax_2025_model.py`
- Modify: `years/2025/outputs/analysis-steps/germany-summary.md` generation
- Modify: `years/2025/outputs/analysis-steps/germany-model-trace.csv` generation

- [ ] Add official-source links in code comments next to each mechanical legal step.
- [ ] Rewrite trace rows to show statutory order explicitly.
- [ ] Distinguish mechanical legal steps from manual tax positions.
- [ ] Update the summary to explain remaining manual positions and why they are not formula-derived.

### Task 5: Add regression and legal-order tests

**Files:**
- Modify: `tests/test_year_pipeline.py`
- Modify: `tests/test_form_outputs.py`
- Possibly create: `tests/test_german_model.py`

- [ ] Add tests that fail if Germany ordinary-income tax falls back to imported wage-side base assumptions.
- [ ] Add tests for tariff helper boundary values.
- [ ] Add tests for `§ 22 Nr. 3` threshold behavior.
- [ ] Add tests that the Germany trace contains required legal references and ordered steps.
- [ ] Re-run full 2025 regression.
