# Provider Facts Pipeline Design

**Goal**

Refactor the extraction layer into a provider-oriented document pipeline with three explicit boundaries:

- `source_facts`
- `semantic_facts`
- `tax_positions`

Provider handlers emit document-native `source_facts` with full provenance. A normalization layer derives provider-neutral `semantic_facts`. All year- and jurisdiction-specific tax logic remains downstream in `tax_positions`.

**Approved Direction**

The pipeline boundary is:

- `document`
- `provider/doc handler`
- `source_facts`
- `human review`
- `semantic_facts`
- `human review`
- `tax_positions`

Providers do **not** contain tax logic. Their responsibility is limited to:

- identifying document families,
- parsing raw files,
- emitting `source_facts` with source provenance,
- surfacing warnings or low-confidence extraction issues.

If two providers emit the exact same document and it can be parsed the same way, they may share a parser.

## Architecture

### 1. Provider-oriented extraction package

Introduce a provider registry under `tax_pipeline/providers/`.

Recommended shape:

- `providers/registry.py`
- `providers/base.py`
- `providers/shared/`
- `providers/schwab/`
- `providers/coinbase/`
- `providers/shareworks/`
- `providers/jpm/`
- `providers/datev/`
- `providers/finanzamt/`

Each provider folder owns provider-specific detection and provider-specific handler wiring.

Each document type has its own handler module, for example:

- `schwab/transactions_csv.py`
- `schwab/form_1099_composite_pdf.py`
- `coinbase/form_1099_da_pdf.py`
- `datev/lohnsteuerbescheinigung_pdf.py`
- `finanzamt/steuerbescheid_pdf.py`

This keeps provider quirks local and avoids a single giant extraction file.

### 2. Shared parsers for exact-same forms

Provider code should not duplicate parsing for forms that are genuinely identical.

Examples:

- a `DATEV`-produced `Lohnsteuerbescheinigung` and another producer’s `Lohnsteuerbescheinigung`
- a reused `Finanzamt` notice format across multiple years

In those cases:

- provider-specific code should detect the document,
- shared code should parse the common structure.

This means the system is not “provider-only.” It is:

- provider-specific for detection and layout quirks,
- shared where the form is actually the same.

### 3. Fact schema split

The pipeline keeps two fact layers before any tax logic:

- `source_facts`: document-native facts that mirror what the document literally says
- `semantic_facts`: provider-neutral economic facts derived from one or more `source_facts`

`tax_positions` come later and are year-specific outputs, not facts.

### 3a. `source_facts`

All providers must emit a common `source_fact` record format.

Minimum fields:

- `fact_id`
- `document_id`
- `provider`
- `document_type`
- `source_file`
- `source_page`
- `source_section`
- `source_label`
- `raw_value`
- `normalized_value`
- `value_type`
- `unit`
- `currency`
- `country_of_origin`
- `owner`
- `tax_year`
- `parser_name`
- `parser_version`
- `confidence`
- `source_snippet`

Optional but useful metadata:

- `statement_date`
- `account_reference`
- `source_hash`
- `notes`

Examples:

- `lohnsteuerbescheinigung_line_3_amount_eur = 171800.61`
- `schwab_1099_div_box_1a_usd = 9596.58`

### 3b. `semantic_facts`

The normalization layer derives `semantic_facts` from one or more `source_facts`.

Minimum fields:

- `semantic_fact_id`
- `fact_type`
- `value`
- `value_type`
- `unit`
- `currency`
- `country_of_origin`
- `owner`
- `tax_year`
- `derived_from_source_fact_ids`
- `mapping_rule`
- `confidence`
- `notes`

Examples:

- `gross_wage = 171800.61 EUR`
- `ordinary_dividends = 9596.58 USD`
- `foreign_tax_withheld = 50.09 USD`
- `capital_sale_proceeds = 12345.67 USD`

### 3c. `tax_positions`

Tax logic should consume reviewed `semantic_facts` and emit year- and jurisdiction-specific `tax_positions`.

Minimum fields:

- `position_id`
- `jurisdiction`
- `tax_year`
- `position_type`
- `input_semantic_fact_ids`
- `rule_reference`
- `computed_value`
- `currency`
- `filing_target`
- `explanation`
- `review_status`

Examples:

- `DE_2025_anlage_kap_line_19`
- `DE_2025_private_sale_loss_carryforward`
- `US_2025_form_1116_passive_foreign_tax`

### 3d. Why the split matters

This split protects the system from year-over-year tax-law changes:

- `source_facts` stay close to the document
- `semantic_facts` stay close to economic reality
- `tax_positions` absorb year- and jurisdiction-specific rule changes

If a form changes, only extraction or source-to-semantic mapping changes. If tax law changes, only the tax-position layer changes.

### 3e. Shared names must be tax-neutral

Shared facts and shared derived facts must describe economic or document reality, not
jurisdiction-specific legal conclusions.

Good shared names:

- `worked_from_home_days`
- `workspace_exclusive_use`
- `capital_sale_proceeds`
- `foreign_tax_withheld`

Bad shared names:

- `home_office_deduction`
- `home_office_eligible`
- `foreign_tax_credit`

Why this matters:

- Germany can use work-from-home day counts for the `Tagespauschale`
- the U.S. home-office rules depend on exclusive-use dedicated workspace

Those legal concepts are not interchangeable, so they must not share one semantic field merely
because both are informally called “home office.”

Rule:

- if a field describes reality, it may be shared
- if a field depends on tax-law wording, it must be jurisdiction-specific

### 4. Human review boundary

The review surface exists to support review **before** tax logic runs.

The intended yearly workflow is:

1. Drop source documents into `years/<year>/raw/`
2. Build manifest and `source_facts`
3. Review `source_facts` for correctness against source snippets
4. Build and review `semantic_facts`
5. Only then run the tax models to produce `tax_positions`

This review step is about data correctness, not tax interpretation.

The review artifacts should include:

- `years/<year>/normalized/source-facts/index.json`
- `years/<year>/normalized/source-facts/REVIEW.md`
- `years/<year>/normalized/semantic-facts/index.json`
- `years/<year>/normalized/semantic-facts/REVIEW.md`
- per-document `*.json`
- per-document `*.md`

The review surface should clearly distinguish:

- `source_facts`
- `semantic_facts`
- unsupported docs
- low-confidence docs
- text-extraction failures
- docs requiring OCR or manual handling

### 5. No tax logic in providers or normalization

Providers must not decide:

- `Aktienfonds` treatment
- treaty re-sourcing
- foreign tax credit posture
- deductible percentage of expenses
- employee-equity tax character
- carryforward usage
- any other tax outcome

Those decisions belong later in the tax pipeline.

The provider layer may extract facts such as:

- “withheld solidarity surcharge”
- “short-term proceeds”
- “payment due date”
- “transaction type = staking income”

The normalization layer may map:

- `lohnsteuerbescheinigung_line_3_amount_eur` -> `gross_wage_eur`
- `schwab_1099_div_box_1a_usd` -> `ordinary_dividends_usd`

Neither layer may decide how those facts affect the return.

### 6. Classification model

The manifest/classification layer should expose a structured descriptor:

- `provider`
- `document_family`
- `format`
- `owner`
- `tax_year`
- `country_of_origin`
- `confidence`

Example:

- provider: `schwab`
- document_family: `transactions`
- format: `csv`

This gives the registry enough information to dispatch to a provider handler cleanly.

### 7. Dispatch contract

Each handler should expose a deterministic extraction interface via a registry mapping:

- `(provider, document_family, format) -> handler`

That fits the existing manifest step and keeps dispatch deterministic.

### 8. Normalization contract

Introduce a normalization layer between provider extraction and tax logic.

Recommended shape:

- `tax_pipeline/normalize/__init__.py`
- `tax_pipeline/normalize/source_to_semantic.py`
- `tax_pipeline/normalize/rules/`

Responsibilities:

- read reviewed `source_facts`
- emit reviewed `semantic_facts`
- preserve provenance links back to contributing `source_fact_ids`
- stay provider-neutral
- stay tax-neutral

### 9. Shared utilities

Shared utilities should move out of provider code into `providers/shared/`:

- amount parsing
- currency normalization helpers
- date normalization
- PDF text extraction
- CSV loading helpers
- source snippet helpers
- common document/fact dataclasses

This avoids repeated parsing logic while keeping provider handlers small.

## Migration Strategy

Refactor incrementally:

1. Preserve current behavior as the regression baseline
2. Introduce provider registry and `source_facts` schema
3. Move one provider/document at a time out of `fact_extraction.py`
4. Add a `source_facts -> semantic_facts` normalization layer
5. Keep the current output format stable while refactoring internals
6. Re-run the `2025` regression after each migration step

Suggested first migrations:

- `schwab`
- `coinbase`
- `finanzamt`
- `datev`
- `jpm`
- `shareworks`

This sequence captures the highest-volume and highest-value document sources first.

## Error Handling

Provider handlers should fail honestly and visibly:

- `unsupported_doc_type`
- `no_text_extracted`
- `text_extraction_failed`
- `no_facts_extracted`
- `partial_facts_extracted`

Normalization should also surface explicit failures:

- `unmapped_source_fact`
- `ambiguous_semantic_mapping`
- `semantic_conflict`
- `manual_review_required`

Warnings should explain what is missing without pretending the document was fully handled.

## Testing

Testing should cover four layers:

### 1. Provider detection

- correct provider routing
- correct document family routing
- correct format routing

### 2. Handler extraction

- fixture-based extraction tests for each handler
- real-shape regression tests for known tricky documents
- provenance fields always populated

### 3. Source-to-semantic normalization

- mapping tests for representative document families
- provenance links preserved
- no tax interpretations leak into semantic facts

### 4. End-to-end regression

- `python3 -m tax_pipeline.run_year 2025`
- locked output parity remains:
  - Germany refund `3725.72 EUR`
  - U.S. treaty refund `1126.54 USD`

The end-to-end regression remains the acceptance gate for the refactor.

## Acceptance Criteria

This refactor is successful when:

- provider handlers are separated from tax logic
- `source_facts` are emitted in one document-native schema
- `semantic_facts` are emitted in one provider-neutral schema
- each fact is traceable to original source material
- a human can review extracted facts before tax computation
- shared parsers are reused where appropriate
- and `2025` still rebuilds to the locked outputs
