# Tax Engine Architecture

This repository is a deterministic, year-scoped tax engine. It has an imperative
outer shell for workspace management, document intake, fact extraction, file
validation, and output rendering, wrapped around a functional legal core that is
intended to be auditable, reproducible, and fail-closed when a fact or filing
posture is outside the modeled law.

The product-level audit and narrative contract is defined in
`ENGINE-SPEC.md`. This architecture document describes how the current codebase
is organized to satisfy that contract.

The current implemented tax year is 2025. The demo workspace lives at
`years/demo-2025/`, while ordinary year workspaces are resolved outside the
repository by default.

## Main Layers

### Legal Input Boundary

Legal calculations should read only user-provided or user-reviewed inputs:
raw source documents, config/election files, normalized fact files, reference
data, derived facts, and explicit filing positions. Generated analysis artifacts
under `outputs/analysis-steps/`, form packages, legal audit packages, verbose
reports, and packet reports are outputs only.

If one jurisdiction needs a value computed by another jurisdiction in the same
run, the year pipeline should pass a typed in-memory value between legal cores
and then write any packet/report only for audit. A generated packet file must not
become the next core's input.

The current `outputs/tax-positions/` location is a compatibility wart: those
files are treated as user-maintained filing positions/elections, not generated
analysis output.

1. Workspace and intake layer
   - Owns directories, uploads, manifests, config CSV/JSON, raw documents, and
     extracted/normalized facts.
   - Key files: `tax_pipeline/year_runtime.py`, `tax_pipeline/paths.py`,
     `tax_pipeline/scaffold_year.py`, `tax_pipeline/intake/workspace.py`,
     `tax_pipeline/intake/uploads.py`, `tax_pipeline/manifest.py`.

2. Parser and reconciliation layer
   - Converts raw documents into deterministic fact files and then into
     structured year inputs.
   - Key files: `tax_pipeline/fact_extraction.py`,
     `tax_pipeline/fact_validation.py`, `tax_pipeline/providers/**`,
     `tax_pipeline/pipelines/y2025/reconcile_facts.py`,
     `tax_pipeline/analysis_inputs.py`.

3. Functional legal core
   - Computes legal results from explicit inputs without reading or writing
     files in the core/stage modules.
   - Key files: `tax_pipeline/core/facts.py`,
     `tax_pipeline/core/stages.py`, `tax_pipeline/core/assessment.py`,
     `tax_pipeline/germany_2025_law.py`, `tax_pipeline/us_2025_law.py`,
     `tax_pipeline/germany_2025_stages.py`,
     `tax_pipeline/usa_2025_stages.py`,
     `tax_pipeline/treaty_2025_stages.py`.

4. Year pipeline and rendering layer
   - Executes the configured year modules, writes analysis artifacts, forms,
     legal audit packages, and verbose reports.
   - Key files: `tax_pipeline/run_year.py`, `tax_pipeline/year_registry.py`,
     `tax_pipeline/pipelines/y2025/**`, `tax_pipeline/forms/**`,
     `tax_pipeline/legal_audit/**`.

## Imperative Workspace And Intake

Workspaces are year roots with the same internal shape regardless of location:

- `raw/`: user-supplied source files, grouped into buckets such as `germany`,
  `us`, `brokers`, `crypto`, `equity_comp`, `receipts`, and `real_estate`.
- `config/`: profile, people, payments, elections, and manual overrides.
- `normalized/`: document manifest, extracted fact files, manual facts,
  reference data, and derived facts.
- `outputs/`: analysis steps, forms, legal audit packages, and tax positions.

`tax_pipeline/paths.py` defines this layout in `YearPaths`. Its
`ensure_directories()` method creates the raw/config/normalized/output
directories and the expected jurisdiction subdirectories.

### External-First Workspaces

`tax_pipeline/year_runtime.py` makes the project external-workspace first:

- `demo-2025` resolves to `years/demo-2025/` inside the repository.
- Numeric year tokens such as `2025` resolve to `~/taxes/2025` by default.
- `--workspace` or `TAX_WORKSPACE_ROOT` can point the engine at another
  workspace root.

This keeps personal tax source files out of the code repository by default while
preserving a checked-in synthetic demo workspace for tests, examples, and public
packaging.

### Intake Flow

The primary orchestration path is `tax_pipeline/run_year.py`:

1. Resolve `YearPaths`.
2. Scaffold missing directories/config files.
3. Write `normalized/documents.json` from the raw file tree.
4. Extract facts from raw files into `normalized/facts/`.
5. Validate that structured inputs are present.
6. Run year modules in registry order.
7. Render forms and legal audit packages.
8. Print a headline summary and remove obsolete legacy analysis outputs.

The local intake app uses the same workspace primitives:

- `tax_pipeline/intake/workspace.py` creates or opens a year workspace and writes
  household/payment/election CSVs.
- `tax_pipeline/intake/uploads.py` classifies uploaded filenames, stores
  supported documents into the preferred raw bucket, writes the manifest, and
  tracks unsupported/evidence-only uploads in `.intake-uploads.json`.
- `tax_pipeline/intake/server.py` and `tax_pipeline/intake_app.py` expose the
  local intake UI.

### Parser Boundary

The parser boundary is intentionally before the legal core.

`tax_pipeline/fact_extraction.py` reads the manifest, loads raw file content,
selects a provider handler, extracts source-backed facts, and writes both JSON
and Markdown review files. Each fact records source file, page/section/snippet
where available. Provider handlers live under `tax_pipeline/providers/**` and
return `DocumentFacts`/`FactRecord` from `tax_pipeline/providers/shared/schema.py`.

`tax_pipeline/providers/registry.py` maps document descriptors to handlers. If a
document type is recognized but unsupported, `UnsupportedDocumentHandler` returns
a fact document with unsupported status instead of guessing. Manual overrides in
`normalized/manual-facts/` can replace parser output for specific source files,
but they remain explicitly labeled as manual/reviewed parser output.

`tax_pipeline/fact_validation.py` validates parser output and writes
`normalized/facts/validation.json` plus `VALIDATION.md`. `extract_all_facts()`
fails closed when validation issues have severity `error`; the legal pipeline
does not proceed on known-invalid fact files.

### Reconciliation Boundary

Reconciliation is also outside the legal core. Parser facts are still
document-shaped; legal stages need normalized economic and election inputs.

The year pipeline modules under `tax_pipeline/pipelines/y2025/` read
`normalized/facts/`, `normalized/derived-facts/`, `normalized/reference-data/`,
and `outputs/tax-positions/` to produce structured analysis inputs and analysis
artifacts. For example:

- `tax_pipeline/pipelines/y2025/reconcile_facts.py` is the newer core boundary:
  it converts workspace/config/reference/fact files into `CanonicalFact`,
  `IgnoredFact`, and `UnsupportedFact` objects, then builds an
  `AssessmentPackage` only when unsupported facts have been resolved.
- `tax_pipeline/analysis_inputs.py` enumerates required structured inputs.
- `tax_pipeline/germany_2025_inputs.py` and `tax_pipeline/us_2025_inputs.py`
  load typed 2025 input objects for the Germany and U.S. law functions.

The practical rule is: parsers identify source facts, reconciliation normalizes
and aggregates them, and law functions compute legal consequences. Parsers
should not embed legal ordering, and legal stages should not read raw files.

## Functional Core Execution

The functional core is designed around explicit facts, pure stage declarations,
stage results, and package-level auditability.

### Canonical Facts

`tax_pipeline/core/facts.py` defines:

- `CanonicalFact`: immutable fact with key, value, provenance, tax year,
  taxpayer scope, unit, optional currency, confidence, and stable fingerprint.
- `FactProvenance`: source document reference, source field, extractor ID,
  optional source line, and notes.
- `IgnoredFact`: explicitly ignored known fact with reason.
- `UnsupportedFact`: recognized fact that is not modeled and must block package
  construction unless resolved.

`assert_facts_ready_for_legal_stages()` enforces that facts reaching law stages
have provenance. `AssessmentPackage` in `tax_pipeline/core/assessment.py`
rejects unsupported facts in `__post_init__`, making unsupported input a hard
failure rather than an omitted number.

### Pure Law Stage Graphs

`tax_pipeline/core/stages.py` defines the audit contract for law execution:

- `LawStage` declares a stage ID, country/scope, legal references, authority
  URLs, required input fact keys, produced output keys, rounding policy, and law
  order note.
- `StageResult` records actual input values, outputs, input fingerprints,
  output fingerprints, diagnostics, precision notes, and its own stable
  fingerprint.
- `validate_law_stage_graph()` checks missing inputs, duplicate outputs,
  unknown results, untracked outputs, missing output fingerprints, and missing
  precision notes.
- `stage_audit_rows()` turns stage declarations/results into audit rows.

The stage declaration modules are deliberately file-I/O free. Tests such as
`tests/y_agnostic/test_law_stage_graph.py`, `tests/y2025/test_germany_stages.py`, and
`tests/y2025/test_us_stages.py` assert that core/stage modules do not use
`Path`, `open`, `read_text`, or `write_text`.

### Germany 2025 Core

Germany law computation lives in `tax_pipeline/germany_2025_law.py`. The stage
graph and adapters live in `tax_pipeline/germany_2025_stages.py`.

The Germany graph is split into ordinary income and capital income:

- Ordinary stages start with the filing posture gate under EStG section 26/26b
  and then proceed through wage income, Werbungskosten, other income under
  section 22 no. 3, retirement and health/Vorsorge special expenses, taxable
  income, section 32a tariff/splitting, SolzG, and payment/refund assembly.
- Capital stages classify section 20/InvStG raw buckets, apply fund
  Teilfreistellung, section 20(6) loss netting, section 20(9) saver allowance,
  section 32d(1) flat tax, section 32d(5) foreign tax credit, SolzG, treaty
  credit checks, and final capital tax.

The Germany pipeline wrapper `tax_pipeline/pipelines/y2025/germany_model.py`
loads structured inputs and writes current analysis artifacts. It also contains
fail-closed guards for unsupported or not-yet-integrated positions, including:

- Germany `married_separate` output support.
- Spouse bank certificate sidecars not integrated into the joint capital
  calculation.
- Positive section 23 private-sale sidecars not integrated into the final
  ordinary/final refund calculation.

### U.S. 2025 Core

U.S. law computation lives in `tax_pipeline/us_2025_law.py`. The domestic U.S.
stage graph and adapters live in `tax_pipeline/usa_2025_stages.py`.

The U.S. graph starts with filing posture/elections and then proceeds through:

- Foreign wage translation.
- Section 61 gross income/AGI assembly.
- Capital sale buckets, section 1256 split, capital loss limitation and
  carryforward under sections 1211/1212.
- Section 63 taxable income.
- Section 1 regular tax, including qualified dividend/preferential capital gain
  ordering.
- Form 1116 preferential-income support gate.
- Section 904 FTC denominator and basket limitations.
- Section 901/904 allowed FTC.
- Treaty re-sourcing stages.
- Section 1411 NIIT.
- Payments/refund or balance due.

The U.S. pipeline wrapper `tax_pipeline/pipelines/y2025/us_model.py` loads typed
inputs, calls `compute_us_assessment_2025()`, writes JSON/Markdown/CSV analysis
outputs, and records legal references and precision notes in the trace.

### Treaty Stages

Treaty handling is modeled as its own scope rather than as a raw-file parser.
`tax_pipeline/treaty_2025_stages.py` declares `US-DE-TREATY-2025` stages over
already-computed U.S. assessment outputs:

- U.S.-source dividends.
- Publication 514 average-tax floor above the treaty source-country floor.
- German residual residence-country cap.
- Additional FTC.

This separation is important: treaty re-sourcing depends on domestic U.S.
results and explicit treaty assumptions, not on independently reparsing broker
documents.

### Fail-Closed Unsupported Facts

Unsupported facts and postures are treated as safety failures:

- `UnsupportedFact` is represented explicitly in `tax_pipeline/core/facts.py`.
- `AssessmentPackage` refuses to build if any unsupported facts are present.
- Fact extraction fails on validation errors.
- Intake rejects unsupported public posture combinations, for example Germany
  married-separate in the current public 2025 flow.
- Country pipeline wrappers raise `NotImplementedError` or `ValueError` when a
  sidecar, posture, or legal position would otherwise be silently omitted.

The engine should prefer a clear unsupported error over a plausible but
incomplete return.

## Audit Capabilities

The architecture is audit-first. Every final number should be explainable by
source facts, stage order, legal authority, precision/rounding policy, and test
coverage.

### Legal References And Law Specs

Law stage declarations carry `legal_refs` and `authority_urls`. The per-country
law specs live under:

- `tax_pipeline/law_spec/germany/2025/`
- `tax_pipeline/law_spec/usa/2025/`

Each law-spec directory has an `index.md`, `coverage.md`, and topic-specific
spec files such as Germany `assessment_ordering.md`,
`capital_buckets_and_saver_allowance.md`, `split_tariff.md`, and U.S.
`regular_tax.md`, `ftc_limitation.md`, `treaty_resourcing.md`.

`tests/y2025/test_law_spec.py` verifies that demo trace steps are covered by law-spec
patterns and that posture-sensitive Germany tariff references map to the correct
law spec.

### Trace Outputs

The analysis layer writes ordered trace files:

- Germany: `outputs/analysis-steps/germany-model-trace.csv`
- U.S.: `outputs/analysis-steps/us-tax-trace.csv`

Trace rows contain step names, values, legal references, authority URLs, notes,
and precision notes. These traces are source material for legal audit packages
and are also useful during debugging because they expose the modeled legal
sequence directly.

### Stage Fingerprints

The newer core audit model fingerprints:

- Canonical facts.
- Law stage declarations.
- Stage outputs.
- Stage results.
- Country/treaty assessments.
- Render projections.
- Assessment packages.

`stable_fingerprint()` in `tax_pipeline/core/facts.py` canonicalizes dataclasses,
Decimals, mappings, and sequences before hashing. Stage results include both
input and output fingerprints so a rendered value can be tied to the exact stage
inputs and output payload that produced it.

### Precision Notes

Precision is not implicit. `LawStage.rounding_policy` describes the stage's legal
or mechanical rounding boundary, and `StageResult.precision_notes` must contain a
note for every declared output key. `StageResult` and graph validation reject
missing precision notes.

Current analysis trace CSVs also contain precision notes, for example where
amounts remain cent-level until a tariff or worksheet rounding boundary.

### Tests Tied To Law

The test suite encodes law-order contracts, not only arithmetic examples:

- `tests/y2025/test_germany_stages.py` asserts Germany section 26/32a ordinary
  ordering and section 20/32d/SolzG capital ordering.
- `tests/y2025/test_us_stages.py` asserts U.S. sections 1, 61, 63, 901, 904,
  1411, and treaty ordering.
- `tests/y2025/test_law_spec.py` links trace steps to law-spec coverage.
- `tests/y2025/test_germany_law.py`, `tests/y2025/test_us_law.py`, and golden
  source tests cover law computations and sourced constants.
- `tests/y_agnostic/test_fact_validation.py` verifies fact validation and fail-closed
  parser behavior.

### Checkpoints

The pipeline includes checkpoint outputs to make regressions visible:

- `tax_pipeline/pipelines/y2025/vanilla_checkpoint.py` computes simpler
  baseline Germany and U.S. checkpoints.
- `tax_pipeline/pipelines/y2025/verbose_report.py` writes a verbose report over
  `final-legal-output.json`.
- `tax_pipeline/validate_workspace.py` gives a grouped checklist for missing
  workspace inputs.
- `tax_pipeline/run_year.py` prints headline Germany/U.S. refund or balance
  results from `final-legal-output.json`, including vanilla checkpoints.

## Final Outputs And Rendering

The renderer surface is file-oriented today, but renderers do not read scattered
intermediate artifacts directly. The pipeline writes analysis artifacts first,
then packages the renderer-facing legal result into
`outputs/analysis-steps/final-legal-output.json`.

### Analysis Outputs

Year modules under `tax_pipeline/pipelines/y2025/` write the canonical current
analysis surface in `outputs/analysis-steps/`, including:

- Germany model results, trace, summary, KAP/N workpapers, ELSTER entry sheet,
  and legal audit narrative.
- U.S. capital results, Form 8949 income buckets, tax estimate, tax trace,
  treaty package, treaty worksheets, and supporting statements.
- `final-legal-output.json`, the stable renderer input package for forms, legal
  audit pages, verbose output, and the runner headline summary.
- Verbose report.

The synthetic demo outputs are checked in under
`years/demo-2025/outputs/analysis-steps/`.

### Forms

Form renderers live in `tax_pipeline/forms/germany.py` and
`tax_pipeline/forms/usa.py`. Their required input is
`outputs/analysis-steps/final-legal-output.json`; they then write Markdown form
packages under:

- `outputs/forms/germany/`
- `outputs/forms/usa/`

The renderers are posture-aware and call posture definitions from
`tax_pipeline/postures/**`; unsupported form surfaces fail rather than rendering
partial forms.

### Legal Audit Packages

Legal audit rendering lives in `tax_pipeline/legal_audit/common.py`,
`tax_pipeline/legal_audit/germany.py`, and `tax_pipeline/legal_audit/usa.py`.
Packages are written under:

- `outputs/legal-audit/germany/`
- `outputs/legal-audit/usa/`

Each package contains an index, overview, law matrix in CSV and Markdown,
assumptions register, and trace index. The legal audit renderer enriches trace
rows with law-spec links and test coverage, then atomically swaps the rendered
package into place. Country legal-audit renderers read trace rows, assumptions,
overview text, and result snapshots only from `final-legal-output.json`.

### Verbose Output

`tax_pipeline/pipelines/y2025/verbose_report.py` writes
`outputs/analysis-steps/verbose-report.md`. It is a human-review surface over the
final legal output, not a separate source of legal truth.

### Final Legal Output Boundary

The long-term core types are `AssessmentPackage`, `CountryAssessment`,
`TreatyAssessment`, `StageResult`, and `RenderProjection` from
`tax_pipeline/core/assessment.py`.

For the current 2025 pipeline, `tax_pipeline/pipelines/y2025/final_legal_output.py`
is the compatibility bridge between legacy analysis artifacts and that final
core-output boundary. It collects the existing country/treaty results, traces,
assumptions, form projections, and fact-document projections into one stable JSON
package.

The downstream rule is strict:

- Legal math is upstream of `final-legal-output.json`.
- Forms, legal-audit packages, verbose output, and headline summaries consume
  only `final-legal-output.json`.
- Renderers may project, format, validate presence/schema, attach source/audit
  metadata, and fail closed.
- Renderers must not introduce new legal calculations or read raw normalized
  files, manual overrides, or intermediate analysis sidecars directly.

## Germany Vs U.S. Architecture

Both Germany and U.S. engines follow the same high-level pattern:

- Structured input loaders read reconciled year facts.
- Pure law functions compute typed assessments.
- Stage adapter modules project assessment outputs into law-stage results.
- Trace/legal audit/form renderers produce human-facing packages.

They differ mainly in legal order and cross-border interactions.

### Germany Legal Order

Germany separates ordinary assessment from capital tax ordering:

- Ordinary income follows EStG section 2 income aggregation, employment income
  and deductions, special expenses, taxable income, section 32a tariff or
  splitting, SolzG, and section 36 payment/refund assembly.
- Capital income follows section 20 and InvStG classification, loss and partial
  exemption rules, saver allowance, section 32d flat tax, section 32d(5) foreign
  tax credit, SolzG, and final capital liability.
- Filing posture matters early because section 26/26b eligibility determines
  whether joint aggregation and section 32a(5) splitting can be applied.

The Germany graph represents this order explicitly in
`germany_ordinary_law_stages_2025()` and `germany_capital_law_stages_2025()`.

### U.S. Legal Order

The U.S. engine is organized around Form 1040 order and IRC limitations:

- Filing posture selects thresholds and elections first.
- Foreign wages are translated before gross income.
- Section 61 AGI precedes section 63 taxable income.
- Capital buckets and section 1256 feed Schedule D/Form 1040 line 7a before AGI
  and preferential tax.
- Section 1 tax is computed before credits.
- Section 904 FTC limitations and section 901 available foreign taxes determine
  allowed FTC.
- Treaty re-sourcing is modeled before final allowed FTC/payment presentation.
- NIIT under section 1411 is separate and not offset by FTC.

The U.S. graph represents this order in `usa_law_stages_2025()`, with
Publication 514 treaty stages included in the domestic stage sequence and also
available as separate treaty-stage projections in `treaty_2025_stages.py`.

### Representing Legal Order

Legal order is represented in four places:

1. Stage graph dependencies: each `LawStage` declares input keys and output keys;
   graph validation rejects a stage sequence that reads a value before it exists.
2. Stage IDs: ordered IDs such as `DE25-08-SPLIT-TARIFF` and
   `US25-19-ALLOWED-FTC` make trace order stable and reviewable.
3. Law metadata: each stage carries legal references, authority URLs, rounding
   policy, and a law-order note.
4. Tests: country stage tests assert important statutory orderings and fail if
   reversing or reordering stages would break dependencies.

This is the central architecture rule: legal order is data in the stage graph,
not just incidental Python control flow.
