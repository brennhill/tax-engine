# Auditable Pure Legal Core Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure, law-ordered tax assessment core where cleaned facts flow through explicit Germany, U.S., and treaty legal stages, and every renderer writes only from the final core assessment package.

**Architecture:** Use an imperative shell plus pure legal core. Loaders parse and reconcile files into canonical typed facts with provenance; pure legal stages consume those facts and return typed assessments with legal references, audit stages, and render projections; renderers only serialize final assessment output to disk.

**Tech Stack:** Python 3.14, `dataclasses`, `Decimal`, `csv`, `json`, `unittest`, existing `tax_pipeline` modules and year workspace layout.

---

## Design Rules

- [ ] Pure core functions must not read files, write files, inspect workspace paths, or call current path helpers.
- [ ] Pure legal stages must accept typed fact/result dataclasses and return typed dataclasses only.
- [ ] Every legal stage must declare non-empty legal references, authority URLs, input keys, output keys, rounding policy, and a short law-order note.
- [ ] Every helper that performs law math must be reachable from a legal stage whose metadata explains the legal authority.
- [ ] Renderers must consume only the final assessment package or render projection, never raw normalized files or intermediate sidecars.
- [ ] Sidebars, legal-audit pages, verbose output, ELSTER sheets, and U.S. packets must all render from the same core output.
- [ ] Every canonical fact must be consumed, explicitly ignored with a reason, or rejected as unsupported.
- [ ] Treaty stages must consume domestic Germany/U.S. assessment outputs, not re-read or recompute domestic raw facts.
- [ ] Unknown or ambiguous data must fail closed before rendering.
- [ ] No behavior-changing refactor step may land without a golden before/after test for the affected country or treaty path.

## Target Structure

- [ ] Add `tax_pipeline/core/__init__.py`.
- [ ] Add `tax_pipeline/core/facts.py` for canonical facts, provenance, fact keys, and unsupported/ignored fact markers.
- [ ] Add `tax_pipeline/core/stages.py` for `LawStage`, `StageResult`, stage graph validation, and audit trace helpers.
- [ ] Add `tax_pipeline/core/assessment.py` for `AssessmentPackage`, country assessments, treaty assessment, diagnostics, and render projections.
- [ ] Add `tax_pipeline/pipelines/y2025/reconcile_facts.py` as the 2025 I/O boundary that calls existing parsers/loaders and returns canonical facts.
- [ ] Add `tax_pipeline/germany_2025_stages.py` as the explicit Germany legal stage sequence.
- [ ] Add `tax_pipeline/usa_2025_stages.py` as the explicit U.S. legal stage sequence.
- [ ] Add `tax_pipeline/treaty_2025_stages.py` as the explicit U.S.-Germany treaty interaction sequence.
- [ ] Keep existing math modules, but move orchestration out of ad hoc pipeline/render code and into stage lists.

## Task 1: Canonical Fact And Provenance Contracts

- [ ] Write failing tests in `tests/test_core_facts.py`.
- [ ] Test that a fact has a stable key, typed value, source document reference, source field, tax year, taxpayer scope, currency/unit, and confidence.
- [ ] Test that unsupported facts and explicitly ignored facts require a human-readable reason.
- [ ] Test that missing provenance fails before any legal stage can run.
- [ ] Implement `tax_pipeline/core/facts.py`.
- [ ] Run `python3 -m unittest tests.test_core_facts`.
- [ ] Commit: `Add canonical tax fact contracts`.

Expected result: the system has one typed vocabulary for facts before any Germany, U.S., or treaty computation sees data.

## Task 2: Law Stage Protocol And Graph Validation

- [ ] Write failing tests in `tests/test_law_stage_graph.py`.
- [ ] Test that every `LawStage` requires `stage_id`, `country_or_scope`, `legal_refs`, `authority_urls`, `input_fact_keys`, `output_keys`, `rounding_policy`, and `law_order_note`.
- [ ] Test that stage graph validation fails on missing inputs, duplicate outputs, missing law refs, or stages that produce untracked outputs.
- [ ] Test that `StageResult` records output values, input fingerprints, output fingerprints, diagnostics, and precision notes.
- [ ] Implement `tax_pipeline/core/stages.py`.
- [ ] Run `python3 -m unittest tests.test_law_stage_graph`.
- [ ] Commit: `Add auditable law stage graph`.

Expected result: the computation order is inspectable and mechanically rejectable when it drifts from declared legal dependencies.

## Task 3: 2025 Fact Reconciliation Shell

- [ ] Write failing tests in `tests/test_year_pipeline.py` for `reconcile_facts_2025(...)`.
- [ ] Test that existing demo/synthetic inputs are loaded into canonical facts with provenance.
- [ ] Test that an unknown input bucket fails closed unless marked unsupported or explicitly ignored.
- [ ] Test that reconciliation is the only layer allowed to read normalized CSV/JSON files.
- [ ] Implement `tax_pipeline/pipelines/y2025/reconcile_facts.py` by wrapping existing loaders without changing math.
- [ ] Run `python3 -m unittest tests.test_year_pipeline`.
- [ ] Commit: `Add 2025 canonical fact reconciliation`.

Expected result: all file I/O and parsing remains at the boundary; the core sees one cleaned fact set.

## Task 4: Germany Legal Stage Pipeline

- [ ] Write failing tests in `tests/test_germany_2025_law.py` for the Germany stage list and golden outputs.
- [ ] Test that stage order is explicit and law referenced for ordinary income, employment deductions, special expenses, tariff tax, solidarity surcharge, capital income buckets, InvStG adjustments, section 20(6) loss ordering, saver allowance, section 32d tax, section 32d(5) foreign tax credit, and final refund/payment.
- [ ] Test that the new stage pipeline exactly matches the current Germany output for the synthetic married-joint workspace.
- [ ] Test that the stage pipeline works for the synthetic single-person workspace.
- [ ] Implement `tax_pipeline/germany_2025_stages.py` as ordered stages delegating to existing pure Germany math helpers.
- [ ] Move orchestration from `tax_pipeline/pipelines/y2025/germany_model.py` into the stage pipeline without changing formulas.
- [ ] Add or update code comments at each stage boundary with the relevant law reference and ordering rule.
- [ ] Run `python3 -m unittest tests.test_germany_2025_law tests.test_year_pipeline`.
- [ ] Commit: `Route Germany 2025 math through legal stages`.

Expected result: Germany calculation order is visible as a legal stage graph rather than scattered across parser, model, and render code.

## Task 5: U.S. Legal Stage Pipeline

- [ ] Write failing tests in `tests/test_us_2025_law.py` for the U.S. stage list and golden outputs.
- [ ] Test that stage order is explicit and law referenced for capital buckets, gross income, taxable income, regular tax, preferential tax, foreign tax credit limitation, additional treaty FTC adjustment, NIIT, payments, and refund/payment.
- [ ] Test that the new stage pipeline exactly matches the current U.S. output for the synthetic dual-national workspace.
- [ ] Test that filing status changes select the correct deduction, brackets, NIIT threshold, and FTC flow.
- [ ] Implement `tax_pipeline/usa_2025_stages.py` as ordered stages delegating to existing pure U.S. math helpers.
- [ ] Move orchestration from `tax_pipeline/pipelines/y2025/us_model.py` into the stage pipeline without changing formulas.
- [ ] Add or update code comments at each stage boundary with the relevant law reference and ordering rule.
- [ ] Run `python3 -m unittest tests.test_us_2025_law tests.test_year_pipeline`.
- [ ] Commit: `Route U.S. 2025 math through legal stages`.

Expected result: the U.S. side has the same audit shape as Germany, so legal review follows the stage sequence instead of ad hoc module flow.

## Task 6: Treaty Interaction Stage Pipeline

- [ ] Write failing tests in `tests/test_us_2025_law.py` and `tests/test_year_pipeline.py` for treaty stages.
- [ ] Test that treaty stages consume domestic Germany and U.S. pre-treaty assessments, not raw fact files.
- [ ] Test that dividend, short-term gain, long-term gain, stock, ETF, and loss behavior remains consistent with existing treaty tests.
- [ ] Test that additional treaty credit is represented as a treaty stage output and then fed into the final U.S. assessment.
- [ ] Implement `tax_pipeline/treaty_2025_stages.py`.
- [ ] Add code comments that reference the treaty article, Internal Revenue Code section, IRS publication/form instruction, or German credit rule relevant to each treaty stage.
- [ ] Run `python3 -m unittest tests.test_us_2025_law tests.test_germany_2025_law tests.test_year_pipeline`.
- [ ] Commit: `Add explicit treaty legal stages`.

Expected result: treaty math becomes a cross-jurisdiction stage sequence with declared dependencies, not a renderer or sidecar recomputation.

## Task 7: Final Assessment Package

- [ ] Write failing tests in `tests/test_year_pipeline.py` for `AssessmentPackage`.
- [ ] Test that one package contains canonical facts, Germany assessment, U.S. assessment, treaty assessment, diagnostics, audit graph, and render projection.
- [ ] Test that package serialization is stable and contains enough data to render all existing outputs.
- [ ] Test that final country totals are derivable only from package fields.
- [ ] Implement `tax_pipeline/core/assessment.py`.
- [ ] Update `tax_pipeline/run_year.py` and 2025 model entry points to build the assessment package before rendering.
- [ ] Run `python3 -m unittest tests.test_year_pipeline`.
- [ ] Commit: `Create final assessment package`.

Expected result: there is one final mathematical result object that downstream code can serialize, inspect, or render.

## Task 8: Projection-Only Renderers

- [ ] Write failing tests in `tests/test_form_outputs.py`.
- [ ] Test that Germany ELSTER entry sheet, U.S. treaty packet, legal audit pages, verbose output, and summaries render from `AssessmentPackage.render_projection`.
- [ ] Test that renderers fail if asked to read raw normalized files or rerun legal math.
- [ ] Update `tax_pipeline/pipelines/y2025/germany_elster_entry_sheet.py`.
- [ ] Update `tax_pipeline/pipelines/y2025/us_treaty_packet.py`.
- [ ] Update `tax_pipeline/legal_audit/common.py`, `tax_pipeline/legal_audit/germany.py`, and `tax_pipeline/legal_audit/usa.py`.
- [ ] Update any summary/verbose renderer to consume only the final package.
- [ ] Run `python3 -m unittest tests.test_form_outputs tests.test_year_pipeline`.
- [ ] Commit: `Make renderers consume only core assessment output`.

Expected result: output code cannot silently diverge from core math because it no longer has access to independent inputs or formulas.

## Task 9: Audit Completeness Gates

- [ ] Write failing tests in `tests/test_law_spec.py`.
- [ ] Test that every stage output has at least one legal reference and at least one test that covers it.
- [ ] Test that every render field maps back to a stage output.
- [ ] Test that every canonical fact is consumed, explicitly ignored, or rejected.
- [ ] Test that all legal references used in code appear in the human-readable law spec/audit docs.
- [ ] Add a validation command or test helper that can be run in CI.
- [ ] Run `python3 -m unittest tests.test_law_spec tests.test_form_outputs tests.test_year_pipeline`.
- [ ] Commit: `Add legal audit completeness gates`.

Expected result: the repo can prove coverage between input facts, legal stages, output fields, tests, and law documentation.

## Task 10: Regenerate Outputs And Remove Obsolete Paths

- [ ] Run `python3 -m tax_pipeline.run_year demo-2025`.
- [ ] Run `python3 -m tax_pipeline.run_year synthetic-single-2025` or the current equivalent single-person workspace command.
- [ ] Run `python3 -m unittest`.
- [ ] Search for renderer imports of raw loaders: `rg "normalized|manual_overrides|load_|active_year_paths|analysis_root" tax_pipeline`.
- [ ] Remove or isolate obsolete sidecar paths so only reconciliation can read source files.
- [ ] Update `README.md` with the new architecture boundary: loaders -> canonical facts -> pure legal stages -> assessment package -> renderers.
- [ ] Update developer docs to explain how to add a new parser, new law stage, or new renderer.
- [ ] Commit: `Document auditable pure core architecture`.

Expected result: the repo has executable examples, passing tests, and docs that describe the pure-core model accurately.

## Verification Checklist

- [ ] `python3 -m unittest tests.test_core_facts`
- [ ] `python3 -m unittest tests.test_law_stage_graph`
- [ ] `python3 -m unittest tests.test_germany_2025_law`
- [ ] `python3 -m unittest tests.test_us_2025_law`
- [ ] `python3 -m unittest tests.test_form_outputs`
- [ ] `python3 -m unittest tests.test_law_spec`
- [ ] `python3 -m unittest tests.test_year_pipeline`
- [ ] `python3 -m unittest`
- [ ] `python3 -m tax_pipeline.run_year demo-2025`
- [ ] `rg "Path\\(|open\\(|read_text\\(|write_text\\(" tax_pipeline/core tax_pipeline/*_2025_stages.py` shows no file I/O inside pure core/stage modules.
- [ ] `rg "normalized|manual_overrides|active_year_paths|analysis_root" tax_pipeline/legal_audit tax_pipeline/pipelines/y2025/*entry* tax_pipeline/pipelines/y2025/*packet*` shows no renderer-side raw input dependencies.

## Implementation Notes

- [ ] Do not rewrite formulas first. Wrap existing formulas in law stages, prove identical outputs, then simplify internals only where tests show behavior is preserved.
- [ ] Prefer adding adapter layers over moving all code at once.
- [ ] Preserve `Decimal` use for all currency and tax math.
- [ ] Use exact golden tests for current synthetic/demo outputs before each country refactor.
- [ ] Add comments only at legal boundaries and non-obvious rounding/order points; do not comment trivial assignments.
- [ ] If a stage exposes a law ambiguity, mark it as a diagnostic and fail closed unless a documented assumption already exists.
- [ ] If an existing output value changes, stop and classify it as either a discovered correctness bug or an accidental refactor regression before proceeding.
