# Provider Facts Pipeline Refactor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the extraction layer into provider-organized document handlers that emit document-native `source_facts`, add a normalization layer that derives provider-neutral `semantic_facts`, and preserve the locked `2025` tax outputs while keeping tax logic downstream in `tax_positions`.

**Architecture:** Introduce a `tax_pipeline.providers` registry that dispatches by provider, document family, and format; move extraction logic out of the monolithic `fact_extraction.py` into provider handlers plus shared parsers; keep extraction limited to `source_facts`; add a `tax_pipeline.normalize` layer that maps reviewed `source_facts` into reviewed `semantic_facts`; keep tax interpretation in the existing tax models until those models are later moved to consume `semantic_facts` directly.

**Tech Stack:** Python 3, stdlib `unittest`, stdlib `csv`, `dataclasses`, existing `pdftotext -layout` text-PDF extraction, existing year runner and tax scripts

---

## Chunk 1: Core Provider Registry And Source-Fact Schema

### Task 1: Add failing tests for provider descriptors and registry dispatch

**Files:**
- Create: `tests/test_provider_registry.py`
- Modify: `tests/test_year_pipeline.py`

- [ ] **Step 1: Write the failing tests**

Cover these behaviors:
- a classified manifest entry can expose `provider`, `document_family`, and `format` in addition to the current `doc_type`
- a registry can resolve a handler for:
  - `schwab` + `transactions` + `csv`
  - `coinbase` + `1099_da` + `pdf`
  - `finanzamt` + `steuerbescheid` + `pdf`
- unsupported descriptors return a deterministic unsupported handler instead of crashing

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_provider_registry -v`
Expected: FAIL because `tax_pipeline.providers` and provider descriptors do not exist yet.

### Task 2: Implement the common provider schema and registry

**Files:**
- Create: `tax_pipeline/providers/__init__.py`
- Create: `tax_pipeline/providers/base.py`
- Create: `tax_pipeline/providers/registry.py`
- Create: `tax_pipeline/providers/shared/schema.py`
- Create: `tax_pipeline/providers/shared/document.py`

- [ ] **Step 1: Write minimal implementation**

Implement:
- `DocumentDescriptor` dataclass with:
  - `provider`
  - `document_family`
  - `format`
  - `doc_type`
  - `owner`
  - `tax_year`
  - `country_of_origin`
  - `confidence`
- `SourceFactRecord` / `DocumentFacts` moved into shared schema, preserving existing public fields while adding:
  - `provider`
  - `document_type`
  - `country_of_origin`
  - `owner`
  - `tax_year`
  - `parser_name`
  - `parser_version`
- registry helpers to register and resolve handlers deterministically

- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_provider_registry -v`
Expected: PASS for registry and descriptor tests.

### Task 3: Expand classification without breaking current consumers

**Files:**
- Modify: `tax_pipeline/classify.py`
- Modify: `tax_pipeline/manifest.py`
- Modify: `tests/test_year_pipeline.py`

- [ ] **Step 1: Add failing tests for structured classification**

Assert that representative files classify with both:
- legacy `doc_type`
- new descriptor fields:
  - `provider`
  - `document_family`
  - `format`
  - `country_of_origin`

- [ ] **Step 2: Implement structured classification**

Suggested mappings:
- Schwab PDF/CSV exports -> provider `schwab`
- Coinbase exports -> provider `coinbase`
- JPM 1099 -> provider `jpm`
- Shareworks PDFs -> provider `shareworks`
- `Lohnsteuerbescheinigung` -> provider `datev` only when the producer/layout warrants it, otherwise use the real producer if known
- `Steuerbescheid`, `Verlustvortrag`, prepayment confirmations -> provider `finanzamt`

Keep `doc_type` in manifest rows until the full migration is complete.

- [ ] **Step 3: Run tests**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS with no regression in manifest behavior.

## Chunk 2: Convert `fact_extraction.py` Into A Source-Fact Orchestrator

### Task 4: Add failing tests for registry-backed extraction

**Files:**
- Modify: `tests/test_fact_extraction.py`

- [ ] **Step 1: Write the failing tests**

Add assertions that:
- `extract_document_facts_from_pages()` can accept a descriptor-backed dispatch path
- the public output JSON/Markdown shape does not change in incompatible ways
- unsupported handlers still emit deterministic `unsupported_doc_type`

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_fact_extraction -v`
Expected: FAIL because extraction is still hardcoded in one file.

### Task 5: Split orchestration from handlers

**Files:**
- Modify: `tax_pipeline/fact_extraction.py`
- Create: `tax_pipeline/providers/shared/text_pdf.py`
- Create: `tax_pipeline/providers/shared/csv_utils.py`
- Create: `tax_pipeline/providers/shared/amounts.py`
- Create: `tax_pipeline/providers/shared/dates.py`

- [ ] **Step 1: Move shared utilities into `providers/shared/`**

Move generic helpers only:
- PDF text loading
- CSV helpers
- amount parsing
- date normalization
- snippet/provenance helpers

- [ ] **Step 2: Reduce `fact_extraction.py` to orchestration**

`fact_extraction.py` should keep:
- `extract_document_facts_from_pages()`
- `load_pdf_pages()`
- `write_document_facts()`
- `extract_all_facts()`

and delegate actual source-fact extraction to the provider registry.

- [ ] **Step 3: Run tests**

Run: `python3 -m unittest tests.test_fact_extraction -v`
Expected: PASS with no output-format regression.

## Chunk 3: Add The Normalization Layer

### Task 6: Add failing tests for `source_facts -> semantic_facts`

**Files:**
- Create: `tests/test_normalize.py`

- [ ] **Step 1: Write the failing tests**

Cover these behaviors:
- `source_facts` from a wage certificate can map to `gross_wage`
- `source_facts` from a Schwab dividend statement can map to `ordinary_dividends`
- `semantic_facts` retain provenance links to contributing `source_fact_ids`
- normalization refuses to emit tax-aware conclusions

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_normalize -v`
Expected: FAIL because `tax_pipeline.normalize` does not exist yet.

### Task 7: Implement the normalization package

**Files:**
- Create: `tax_pipeline/normalize/__init__.py`
- Create: `tax_pipeline/normalize/source_to_semantic.py`
- Create: `tax_pipeline/normalize/rules/__init__.py`
- Create: `tax_pipeline/normalize/rules/wages.py`
- Create: `tax_pipeline/normalize/rules/dividends.py`

- [ ] **Step 1: Write minimal implementation**

Implement:
- a normalization entry point that reads reviewed `source_facts`
- explicit mapping rules for a first representative set:
  - wages
  - ordinary dividends
  - foreign tax withheld
- semantic fact records with:
  - `semantic_fact_id`
  - `fact_type`
  - `derived_from_source_fact_ids`
  - `mapping_rule`

- [ ] **Step 2: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_normalize -v`
Expected: PASS for first semantic mappings.

## Chunk 4: Migrate Machine-Readable Providers First

### Task 8: Add the Schwab provider handlers

**Files:**
- Create: `tax_pipeline/providers/schwab/__init__.py`
- Create: `tax_pipeline/providers/schwab/detect.py`
- Create: `tax_pipeline/providers/schwab/transactions_csv.py`
- Create: `tax_pipeline/providers/schwab/form_1099_composite_pdf.py`
- Create: `tax_pipeline/providers/schwab/form_1099_csv.py`
- Modify: `tests/test_fact_extraction.py`

- [ ] **Step 1: Write failing tests for the Schwab handlers**

Cover:
- `1099 Composite` PDF facts
- transaction CSV summary facts
- `MM/DD/YYYY as of MM/DD/YYYY` date variants
- unsupported or placeholder `1099` CSV behavior if no extraction exists yet

- [ ] **Step 2: Implement the handlers**

Requirements:
- provider metadata is populated as `schwab`
- document family is correct per file type
- facts keep provenance and remain provider-neutral
- no tax semantics are embedded

- [ ] **Step 3: Run focused tests**

Run: `python3 -m unittest tests.test_fact_extraction -v`
Expected: Schwab-related tests PASS.

### Task 9: Add the Coinbase provider handlers

**Files:**
- Create: `tax_pipeline/providers/coinbase/__init__.py`
- Create: `tax_pipeline/providers/coinbase/detect.py`
- Create: `tax_pipeline/providers/coinbase/transactions_csv.py`
- Create: `tax_pipeline/providers/coinbase/form_1099_da_pdf.py`
- Modify: `tests/test_fact_extraction.py`

- [ ] **Step 1: Write failing tests for Coinbase handlers**

Cover:
- transaction CSV summaries
- `1099-DA` summary totals from text PDF
- provider metadata and country metadata

- [ ] **Step 2: Implement the handlers**

- [ ] **Step 3: Run focused tests**

Run: `python3 -m unittest tests.test_fact_extraction -v`
Expected: Coinbase-related tests PASS.

### Task 10: Commit the machine-readable provider migration

**Files:**
- Modify files from Tasks 6-7

- [ ] **Step 1: Run regression checks**

Run:
- `python3 -m unittest discover -s tests -v`
- `python3 -m tax_pipeline.run_year 2025`

Expected:
- tests PASS
- `2025` facts generation still works
- locked outputs remain:
  - `3725.72 EUR`
  - `1126.54 USD`

- [ ] **Step 2: Commit**

```bash
git add tax_pipeline/providers/schwab tax_pipeline/providers/coinbase \
  tax_pipeline/providers/shared tax_pipeline/fact_extraction.py \
  tax_pipeline/normalize tests/test_fact_extraction.py \
  tests/test_provider_registry.py tests/test_year_pipeline.py tests/test_normalize.py
git commit -m "Refactor source facts and normalization for machine-readable providers"
```

## Chunk 5: Migrate Shared German Form Parsers And Provider Wrappers

### Task 11: Extract shared parsers for exact-same German forms

**Files:**
- Create: `tax_pipeline/providers/shared/german_lohnsteuerbescheinigung.py`
- Create: `tax_pipeline/providers/shared/german_steuerbescheid.py`
- Create: `tax_pipeline/providers/shared/german_verlustvortrag.py`
- Create: `tax_pipeline/providers/shared/german_prepayment.py`
- Modify: `tests/test_fact_extraction.py`

- [ ] **Step 1: Write failing tests that preserve current real-shape behavior**

Cover:
- English and German `Lohnsteuerbescheinigung` layout variants
- `Verlustvortrag` heading/date extraction
- `Steuerbescheid` summary extraction
- prepayment transfer confirmation facts

- [ ] **Step 2: Move parsing logic into shared semantic modules**

These modules must remain provider-neutral and contain no tax interpretation.

- [ ] **Step 3: Run focused tests**

Run: `python3 -m unittest tests.test_fact_extraction -v`
Expected: PASS for German form extraction tests.

### Task 10: Add DATEV and Finanzamt provider wrappers

**Files:**
- Create: `tax_pipeline/providers/datev/__init__.py`
- Create: `tax_pipeline/providers/datev/detect.py`
- Create: `tax_pipeline/providers/datev/lohnsteuerbescheinigung_pdf.py`
- Create: `tax_pipeline/providers/finanzamt/__init__.py`
- Create: `tax_pipeline/providers/finanzamt/detect.py`
- Create: `tax_pipeline/providers/finanzamt/steuerbescheid_pdf.py`
- Create: `tax_pipeline/providers/finanzamt/verlustvortrag_pdf.py`
- Create: `tax_pipeline/providers/finanzamt/prepayment_pdf.py`
- Modify: `tax_pipeline/classify.py`

- [ ] **Step 1: Route provider-specific detection through wrappers**

Requirements:
- exact-same documents reuse shared semantic parsers
- provider metadata reflects the actual producer/origin
- `country_of_origin` is `DE` for these handlers

- [ ] **Step 2: Run end-to-end extraction tests**

Run:
- `python3 -m unittest discover -s tests -v`
- `python3 -m tax_pipeline.run_year 2025`

Expected: PASS with no facts regression.

## Chunk 5: Migrate Remaining Existing Handlers And Centralize Unsupported Status

### Task 11: Move JPM into its provider and add Shareworks placeholder handlers

**Files:**
- Create: `tax_pipeline/providers/jpm/__init__.py`
- Create: `tax_pipeline/providers/jpm/detect.py`
- Create: `tax_pipeline/providers/jpm/form_1099_b_pdf.py`
- Create: `tax_pipeline/providers/shareworks/__init__.py`
- Create: `tax_pipeline/providers/shareworks/detect.py`
- Create: `tax_pipeline/providers/shareworks/statement_pdf.py`
- Modify: `tests/test_fact_extraction.py`

- [ ] **Step 1: Write failing tests**

Cover:
- JPM 1099 summary extraction through the registry
- Shareworks still yielding an honest unsupported or no-facts status through a real provider handler

- [ ] **Step 2: Implement handlers**

For Shareworks:
- do not invent extraction if it is not ready
- emit deterministic unsupported or partial status with provider metadata

- [ ] **Step 3: Run tests**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS.

### Task 12: Normalize unsupported, partial, and OCR-needed statuses

**Files:**
- Modify: `tax_pipeline/providers/base.py`
- Modify: `tax_pipeline/fact_extraction.py`
- Modify: `README.md`

- [ ] **Step 1: Define canonical statuses**

Support at least:
- `ok`
- `partial_facts_extracted`
- `unsupported_doc_type`
- `no_text_extracted`
- `text_extraction_failed`
- `ocr_required`

- [ ] **Step 2: Ensure `REVIEW.md` surfaces these clearly**

The human reviewer should be able to separate:
- trusted extracted facts
- unsupported docs
- docs needing follow-up

- [ ] **Step 3: Run focused check**

Run: `python3 -m tax_pipeline.run_year 2025`
Expected: `years/2025/normalized/facts/REVIEW.md` shows clear status distinctions.

## Chunk 6: Final Regression, Docs, And Cleanup

### Task 13: Update developer docs for the provider/facts architecture

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-12-provider-facts-pipeline-design.md`

- [ ] **Step 1: Document the final architecture**

Include:
- provider folder structure
- shared semantic parsers
- common fact schema
- “no tax logic in providers” rule
- yearly review workflow

- [ ] **Step 2: Document the next unsupported areas**

Call out:
- OCR/image docs
- receipts/emails
- remaining unsupported providers or document kinds

### Task 14: Run final full regression

**Files:**
- Modify any remaining files from previous tasks

- [ ] **Step 1: Run unit and end-to-end verification**

Run:
- `python3 -m unittest discover -s tests -v`
- `python3 -m tax_pipeline.run_year 2025`
- `git status --short`

Expected:
- all tests PASS
- `2025` pipeline PASS
- worktree contains only intended changes

- [ ] **Step 2: Verify locked outputs explicitly**

Check:
- `years/2025/outputs/analysis-steps/091-model-results.json`
- `years/2025/outputs/analysis-steps/125-us-2025-tax-estimate.json`

Expected:
- Germany refund `3725.72 EUR`
- U.S. treaty refund `1126.54 USD`

- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/specs/2026-04-12-provider-facts-pipeline-design.md \
  docs/superpowers/plans/2026-04-12-provider-facts-pipeline-refactor.md \
  tax_pipeline/providers tax_pipeline/fact_extraction.py tax_pipeline/classify.py \
  tax_pipeline/manifest.py tax_pipeline/run_year.py tests
git commit -m "Refactor facts extraction into provider handlers"
```
