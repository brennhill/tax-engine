# Law Spec Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first-class Markdown `law_spec` layer for Germany 2025 and U.S. 2025, remove the uncommitted verification-package work, and link the current legal engines and tests to the new law-spec files.

**Architecture:** Store the law-spec as source-controlled Markdown under `tax_pipeline/law_spec/<jurisdiction>/<year>/`. Each rule file acts as the interpretation contract for a material calculation. The legal engines remain the primary calculators. The law-spec becomes the auditable reference that humans and LLMs compare the code against.

**Tech Stack:** Python package docs, Markdown, existing tests, existing legal engines.

---

## Chunk 1: Remove The Abandoned Verification Work

### Task 1: Remove uncommitted verification-package code and docs

**Files:**
- Delete: `tax_pipeline/verification/`
- Revert: `tax_pipeline/paths.py` verification-root additions
- Delete: `docs/superpowers/specs/2026-04-13-verification-package-design.md`
- Delete: `docs/superpowers/plans/2026-04-13-verification-package-implementation.md`

- [ ] Remove the uncommitted verification package files
- [ ] Restore `YearPaths` so it only contains active directory roots
- [ ] Run targeted tests to confirm nothing still references verification paths

## Chunk 2: Add Law Spec Tree

### Task 2: Add `tax_pipeline/law_spec/germany/2025/`

**Files:**
- Create: `tax_pipeline/law_spec/germany/2025/index.md`
- Create: `tax_pipeline/law_spec/germany/2025/split_tariff.md`
- Create: `tax_pipeline/law_spec/germany/2025/ordinary_soli.md`
- Create: `tax_pipeline/law_spec/germany/2025/other_income_22nr3.md`
- Create: `tax_pipeline/law_spec/germany/2025/capital_tax_ordering.md`
- Create: `tax_pipeline/law_spec/germany/2025/payments_and_crediting.md`

- [ ] Write the Germany index
- [ ] Write each Germany rule file using the standard section template
- [ ] Link each file to implementation, tests, and affected outputs

### Task 3: Add `tax_pipeline/law_spec/usa/2025/`

**Files:**
- Create: `tax_pipeline/law_spec/usa/2025/index.md`
- Create: `tax_pipeline/law_spec/usa/2025/regular_tax.md`
- Create: `tax_pipeline/law_spec/usa/2025/qualified_dividend_worksheet.md`
- Create: `tax_pipeline/law_spec/usa/2025/capital_loss_limit.md`
- Create: `tax_pipeline/law_spec/usa/2025/ftc_limitation.md`
- Create: `tax_pipeline/law_spec/usa/2025/niit.md`
- Create: `tax_pipeline/law_spec/usa/2025/treaty_resourcing.md`

- [ ] Write the U.S. index
- [ ] Write each U.S. rule file using the standard section template
- [ ] Clearly distinguish mechanical rules from explicit filing positions

## Chunk 3: Link Code And Tests To Law Spec

### Task 4: Add law-spec references into legal-engine module comments

**Files:**
- Modify: `tax_pipeline/germany_2025_law.py`
- Modify: `tax_pipeline/us_2025_law.py`

- [ ] Add short comments near major functions that point to the relevant `law_spec` Markdown file
- [ ] Keep comments brief and specific; do not duplicate the whole rule text in code

### Task 5: Add law-spec references into tests

**Files:**
- Modify: `tests/test_germany_2025_law.py`
- Modify: `tests/test_us_2025_law.py`

- [ ] Add comments or helper constants pointing to the relevant rule-spec files
- [ ] Add one smoke-style test that the expected law-spec files exist

## Chunk 4: Docs And Verification

### Task 6: Update repo docs

**Files:**
- Modify: `README.md`
- Modify: `docs/jurisdiction-schema-boundaries.md` if needed

- [ ] Explain what `law_spec` is and where it sits in the architecture
- [ ] Explain that it is source-controlled interpretation, not generated output

### Task 7: Verify and cleanly finish

**Files:**
- Test: `tests/test_germany_2025_law.py`
- Test: `tests/test_us_2025_law.py`
- Test: `tests/test_year_pipeline.py`

- [ ] Run targeted tests
- [ ] Run full test suite
- [ ] Run `python3 -m tax_pipeline.run_year 2025`
- [ ] Confirm headline outputs stay unchanged

