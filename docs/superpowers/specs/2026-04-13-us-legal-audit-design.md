# U.S. 2025 Legal Audit Design

Date: 2026-04-13

## Goal

Make the U.S. 2025 pipeline auditable to the same standard as the Germany pipeline:

- pure law/core functions only
- all factual inputs loaded from structured year data
- explicit manual positions for judgment calls
- a legal-order trace with official authority links
- renderers that do not contain tax logic

The target is that a careful non-tax professional can inspect the code and generated audit artifacts and understand:

- which factual inputs were used
- which manual positions were chosen
- which legal authority controls each computation step
- in what order the U.S. calculations were applied

## Current Problem

The current U.S. pipeline already has some references to IRS instructions and treaty materials, but it still mixes:

- file loading
- calculation logic
- filing-line mapping
- treaty worksheet rendering

That makes the code harder to audit and harder to test.

The specific gap is the same one the Germany pipeline had before the legal-audit refactor:

- the law/order is not isolated as a pure computational core

## Scope

This design covers:

- the U.S. 2025 capital and tax math core
- structured input loading for the U.S. model
- treaty re-sourcing computation ordering
- legal trace and audit output generation
- test coverage for the legal core

This design does not:

- make the U.S. model year-generic
- change the factual document-extraction layer
- redesign the U.S. forms renderer contract

## Recommended Architecture

Split the U.S. pipeline into three layers:

1. `tax_pipeline/us_2025_inputs.py`
2. `tax_pipeline/us_2025_law.py`
3. `tax_pipeline/pipelines/y2025/*.py`

### Inputs Layer

`tax_pipeline/us_2025_inputs.py` loads only from:

- `years/<year>/config/`
- `years/<year>/normalized/facts/`
- `years/<year>/normalized/reference-data/`
- `years/<year>/normalized/derived-facts/`
- `years/<year>/outputs/tax-positions/`

It converts those files into strongly named dataclasses and primitives that the law core can consume directly.

This layer may validate presence/shape, but it does not perform tax computation.

### Law Layer

`tax_pipeline/us_2025_law.py` is pure.

It must not:

- read files
- write files
- inspect paths
- read generated outputs

It should expose pure helpers for:

- capital result aggregation
- annual capital-loss deduction and carryforward
- ordinary gross income / AGI / taxable income
- 2025 MFS regular tax
- qualified dividend / capital gain tax ordering
- FTC limitation by basket
- treaty re-sourcing additional-credit worksheet math
- NIIT
- final payment/refund or balance due

This layer will also define data structures for:

- U.S. capital inputs
- U.S. ordinary-income inputs
- FTC inputs
- treaty inputs
- tax assessment outputs

### Pipeline Layer

The year-specific pipeline files will become orchestration/rendering only:

- `us_capital_workpaper.py`
  derives capital-side outputs and writes audit files
- `us_model.py`
  computes the full U.S. assessment from structured inputs and the pure law core
- `us_treaty_packet.py`
  maps already-computed positions to packet/worksheet outputs

No tax math should remain duplicated in the packet layer.

## Legal Authorities

The code and generated legal trace should cite official sources for each mechanical step.

Primary authorities:

- `26 U.S.C. § 61`
  gross income
- `26 U.S.C. § 63`
  taxable income and standard deduction
- `26 U.S.C. § 1`
  tax imposed
- `26 U.S.C. § 1(h)`
  preferential rates for net capital gain / qualified dividends
- `26 U.S.C. § 1211(b)`
  MFS annual capital-loss limitation
- `26 U.S.C. § 1212(b)`
  capital-loss carryforward
- `26 U.S.C. § 1256`
  section 1256 treatment
- `26 U.S.C. § 901`
  foreign tax credit
- `26 U.S.C. § 904`
  FTC limitation
- `26 U.S.C. § 1411`
  NIIT

Official interpretive/form sources:

- IRS Instructions for Form 1040
- IRS Instructions for Schedule D
- IRS Instructions for Form 1116
- IRS Instructions for Form 8960
- IRS Publication 514
- IRS Publication 550
- U.S.-Germany treaty technical explanation
- IRS yearly average FX rates page

## Manual Positions

The following remain explicit manual positions rather than hidden formula choices:

- `use_treaty_resourcing`
- `ftc_method = accrued`
- DHER basis posture
- treatment of the 2024 German redetermination in the 2025 U.S. packet
- documented U.S.-source dividend split used for treaty re-sourcing
- any reconstructed or judgment-based foreign-source split

These should be loaded from structured positions/config, not hardcoded inside tax math.

## Legal Order

The audit note and trace should make the legal order explicit:

1. compute capital buckets and annual capital-loss limitation
2. compute gross income and AGI
3. compute taxable income after standard deduction
4. compute regular tax using the 2025 MFS rate structure and qualified-dividend ordering
5. compute FTC limitations by basket
6. compute allowed passive/general FTC
7. compute treaty re-sourcing additional credit if elected
8. compute NIIT
9. apply payments and determine refund or balance due

## Output Contract

The refactor should add or strengthen:

- `years/<year>/outputs/analysis-steps/us-model-results.json`
- `years/<year>/outputs/analysis-steps/us-model-trace.csv`
- `years/<year>/outputs/analysis-steps/us-legal-audit.md`

The trace should show:

- step id
- description
- authority link
- inputs
- output
- note on whether the row is mechanical law or manual position

## Success Criteria

This work is successful when:

- the U.S. model can be read as a pure-law computation with structured inputs
- the treaty packet no longer duplicates core tax math
- tests cover the main legal boundaries
- `python3 -m tax_pipeline.run_year 2025` still succeeds
- the final U.S. outputs remain explainable from a legal trace rather than from implicit wiring
