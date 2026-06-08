# U.S. 2025 Legal Audit Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the U.S. 2025 pipeline into a pure, auditable law core with structured inputs, explicit manual positions, and legal-order trace outputs.

**Architecture:** Add a pure `us_2025_law.py` core and a structured `us_2025_inputs.py` loader, then refactor the year pipeline so the workpaper/model layers call the pure core and the treaty packet only renders already-computed positions. Preserve the current filing posture but make each judgment call explicit.

**Tech Stack:** Python, CSV/JSON structured inputs, unittest, deterministic pipeline outputs

---

### Task 1: Add a structured U.S. input layer

**Files:**
- Create: `tax_pipeline/us_2025_inputs.py`
- Modify: `tax_pipeline/analysis_inputs.py`
- Test: `tests/test_year_pipeline.py`

- [ ] Define dataclasses for:
  - capital-input facts
  - ordinary-income/model inputs
  - FTC inputs
  - treaty/manual positions
- [ ] Load those dataclasses from `facts/`, `reference-data/`, `derived-facts/`, and `outputs/tax-positions/`.
- [ ] Keep the old row-based loaders only where still needed by other pipeline surfaces.
- [ ] Add tests that the structured U.S. loader produces the expected named inputs for 2025.

### Task 2: Add the pure U.S. 2025 law core

**Files:**
- Create: `tax_pipeline/us_2025_law.py`
- Test: `tests/test_us_2025_law.py`

- [ ] Add pure helpers for:
  - capital bucket aggregation
  - section 1256 overlay
  - annual capital-loss deduction and carryforward
  - 2025 MFS regular tax
  - qualified-dividend / capital-gain ordering
  - FTC limitation
  - allowed FTC by basket
  - treaty re-sourcing additional-credit worksheet math
  - NIIT
  - final refund/balance computation
- [ ] Add official-source links in comments at each mechanical legal step.
- [ ] Add tests for threshold and boundary behavior.

### Task 3: Refactor the U.S. capital workpaper onto the pure core

**Files:**
- Modify: `tax_pipeline/pipelines/y2025/us_capital_workpaper.py`
- Test: `tests/test_us_2025_law.py`

- [ ] Replace inline capital math with calls into `us_2025_law.py`.
- [ ] Keep the current output files, but have them describe the law-driven calculations and authorities.
- [ ] Ensure the workpaper remains a derived-facts/audit surface, not a second tax engine.

### Task 4: Refactor the U.S. model onto the pure core

**Files:**
- Modify: `tax_pipeline/pipelines/y2025/us_model.py`
- Modify: `tax_pipeline/forms/usa.py` if output keys change
- Test: `tests/test_us_2025_law.py`
- Test: `tests/test_form_outputs.py`

- [ ] Replace inline tax math with a single pure-law assessment call.
- [ ] Write `us-model-results.json` from the pure assessment object.
- [ ] Write `us-model-trace.csv` with one row per legal step and authority link.
- [ ] Write `us-legal-audit.md` explaining legal order and manual positions.
- [ ] Preserve existing downstream JSON keys where that keeps the refactor smaller and safer.

### Task 5: Make the treaty packet render-only

**Files:**
- Modify: `tax_pipeline/pipelines/y2025/us_treaty_packet.py`
- Test: `tests/test_form_outputs.py`

- [ ] Remove duplicated tax math from the treaty packet.
- [ ] Read treaty worksheet values and packet headline numbers from `us-model-results.json`.
- [ ] Keep the treaty attachment and audit summary surfaces, but make them line-mapping/render-only.

### Task 6: Regression, audit, and docs

**Files:**
- Modify: `tests/test_year_pipeline.py`
- Modify: `README.md`
- Possibly modify: `docs/superpowers/specs/2026-04-13-us-legal-audit-design.md`

- [ ] Add tests that `us-legal-audit.md` and `us-model-trace.csv` are generated and contain authority links.
- [ ] Re-run `python3 -m unittest discover -s tests -v`.
- [ ] Re-run `python3 -m tax_pipeline.run_year 2025`.
- [ ] Confirm the final U.S. results still regenerate cleanly or explain any lawful change.
