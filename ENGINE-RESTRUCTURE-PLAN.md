# Engine restructuring plan

This document is the plan-of-record for collapsing the engine to a single
legal-execution path: `execute_rule_graph(initial_facts, rules)` is the
*only* way tax values get computed, and the per-stage `calculate` functions
are where the legal arithmetic lives.

It supersedes the prior draft that treated the existing `compute_*`
monoliths as a parallel source of truth to be projected into the graph.

## Architectural principle

> The rule graph is the legal core. Every value in
> `final-legal-output.json` and `legal-execution-graph.json` is produced
> by a `LawRule.calculate(facts) -> outputs` invocation through
> `execute_rule_graph`. Nothing computes tax results outside this loop.

Corollaries:

1. The big monolith functions in `tax_pipeline/germany_2025_law.py`
   (`compute_joint_ordinary_assessment_2025`,
   `compute_germany_capital_assessment_2025`) and
   `tax_pipeline/us_2025_law.py` (`compute_us_assessment_2025`,
   `compute_treaty_resourcing_*`) get dismantled into per-stage rule
   functions. They do not survive as shims.
2. `Assessment` output dataclasses (`JointOrdinaryAssessment2025`,
   `GermanyCapitalAssessment2025`, `USOverallAssessment2025`) become
   read-only projections of `RuleGraphExecution.final_facts` if any
   consumer still needs them, or are deleted outright. They are never
   primary computation outputs.
3. Conditionality lives inside rule bodies, not above them. We never
   pre-compute "this stage doesn't apply, skip it." Example: § 20(9)
   saver allowance means Germany doesn't tax capital below the
   threshold. We model that by `DE25-16-SECTION-20-9-SAVER` returning
   `taxable_after_allowance = 0` when below threshold; downstream stages
   take 0 in and produce 0 out. All declared stages execute every run.
4. `_execute_stage_projection`, `adapt_*_stage_results_2025`, and the
   `lambda facts: {output_key: pre_computed_value}` lookup pattern are
   deleted, not refactored.
5. The pipeline scripts (`germany_model.py`, `us_model.py`,
   `us_treaty_packet.py`, `final_legal_output.py`) call
   `execute_rule_graph(...)` directly and read `final_facts` to produce
   any non-graph artifacts (form renderings, ELSTER projections, trace
   CSVs).

## Posture is an input fact

Filing posture (and any other taxpayer-facing election) is an input
fact, not a rule-list branch. The rule list is invariant per
jurisdiction; every run executes the same stages in the same order.
Posture-driven legal branches live inside rule bodies.

Today three Germany ordinary stage pairs/triples are selected by filing
posture at rule-list construction time
(`germany_ordinary_law_stages_2025(filing_posture=...)`):

| Today (posture-selected)                                                | Becomes (single stage, internal branch) |
|-------------------------------------------------------------------------|------------------------------------------|
| `DE25-00-JOINT-GATE` / `DE25-00-FILING-GATE` / `DE25-00-SEPARATE-GATE`  | one `DE25-00-FILING-POSTURE-GATE`       |
| `DE25-07-JOINT-ZVE` / `DE25-07-TAXABLE-INCOME`                          | one `DE25-07-TAXABLE-INCOME`            |
| `DE25-08-SPLIT-TARIFF` / `DE25-08-BASIC-TARIFF`                         | one `DE25-08-INCOME-TAX-TARIFF`         |

Each consolidated stage's `legal_refs` cite all the branches' authorities
(e.g. `("§ 32a Abs. 1 EStG", "§ 32a Abs. 5 EStG", "§ 26b EStG")` for the
tariff stage). The `legal_formula` makes the conditional explicit, e.g.
`de.ordinary.income_tax = 2 * basic_tariff_2025(taxable_income / 2) if
filing_posture == "married_joint" else basic_tariff_2025(taxable_income)`.

The audit trail still shows which legal branch ran for a given taxpayer
because `input_values["de.ordinary.filing_posture"]` is recorded in the
executed packet for every consuming stage. Anyone reading
`legal-execution-graph.json` can reconstruct the branch taken from the
inputs.

Posture comparison ("married_joint vs married_separate, which yields a
better refund?") falls out as an outer loop: run the engine N times,
once per posture fact value; capture each run's `final_facts`; present
a side-by-side. No engine changes needed.

US (`usa_law_stages_2025()`) and treaty (`treaty_law_stages_2025()`)
rule lists are already static; nothing to flatten there.

## Non-goals

- No changes to substantive tax law. Existing golden numbers in
  `tests/y2025/test_germany_law.py`, `tests/y2025/test_us_law.py`, and
  `tests/y2025/test_year_pipeline.py` must keep passing throughout.
- No changes to on-disk artifact shapes. `final-legal-output.json`,
  `legal-execution-graph.json`, ELSTER projections, trace CSVs, and the
  Markdown narratives keep their existing schemas.
- No fact-extraction / intake refactoring.

## Phasing

Five phases. Each migrates one jurisdiction (or sub-jurisdiction) end-to-
end: per-stage `calculate` functions are written, the legacy `compute_*`
function for that scope is deleted, the legacy `adapt_*` adapter is
deleted, the pipeline script is rewired to `execute_rule_graph`, and the
existing golden tests are confirmed green.

### Phase 0 - Scaffolding (DONE)

Delivered:

- `LawStage.legal_formula` field added; `__post_init__` rejects the
  auto-generated input-key concatenation.
- All 36 `LawStage` declarations carry real legal formulas.
- `_stage_rule` renderer reads `stage.legal_formula`.
- New tests: `test_law_stage_legal_formula_rejects_auto_generated_input_key_concat`
  and `test_every_declared_law_stage_has_a_real_legal_formula`.

### Phase 1 - Treaty stages (4 stages, pilot)

Smallest surface; serves as the pattern reference.

1. Create `tax_pipeline/treaty_2025_rules.py` with one
   `def treaty25_NN_xxx(facts) -> Mapping[str, Any]` per declared stage.
   Bodies are *moved out of* `compute_treaty_resourcing_*` in
   `us_2025_law.py`, split on stage boundaries.
2. Build `treaty_law_rules_2025() -> tuple[LawRule, ...]` binding each
   `LawStage` to its `calculate`.
3. Add `execute_treaty_rule_graph(initial_facts, *, input_fingerprints)
   -> RuleGraphExecution`.
4. Rewire `us_treaty_packet.py` and `us_model.py` (where they currently
   call the legacy treaty compute) to call
   `execute_treaty_rule_graph(...)` and consume `final_facts`. The
   executed `RuleGraphExecution` flows in-memory via `pipeline_context`.
5. **Delete** `compute_treaty_resourcing_*` from `us_2025_law.py`.
6. **Delete** `adapt_treaty_stage_results_2025`, `_result`, and
   `_projection_stage_results` from `treaty_2025_stages.py`.
7. **Delete** `_treaty_stage_results` from
   `pipelines/y2025/rule_narrative_packets.py`; consume the executed
   StageResults directly via `pipeline_context`.
8. Existing tests in `test_us_2025_law.py` (treaty cases) and the
   fixture-chain test must stay green.

Acceptance: treaty section of `legal-execution-graph.json` is built from
real executed StageResults; treaty `compute_*` and `adapt_*` are gone
from the codebase.

### Phase 2 - Germany capital stages (9 stages)

1. Create `tax_pipeline/germany_capital_2025_rules.py`. Per-stage
   functions for `DE25-13` through `DE25-21`. Bodies moved from
   `compute_germany_capital_assessment_2025`.
2. The first stage, `DE25-13-CAPITAL-RAW-BUCKETS`, takes the typed
   capital-input facts and emits the bucket dict; downstream stages
   consume the bucket dict, fund-classification facts, etc., as already
   declared in the LawStage `input_fact_keys`.
3. Rewire `germany_model.py` to call the executor; build any consumer-
   facing `GermanyCapitalAssessment2025` view from `final_facts`. Where
   possible, switch consumers (form renderers, audit md writers) to
   read `final_facts` directly.
4. **Delete** `compute_germany_capital_assessment_2025`.
5. **Delete** `adapt_germany_capital_stage_results_2025` and the
   `"external fact for {key}"` placeholder pattern from
   `germany_2025_stages.py`.
6. **Delete** `_germany_capital_stage_results` from
   `rule_narrative_packets.py`.
7. Capital cases in `test_germany_2025_law.py` stay green.

Acceptance: capital section reflects real execution; legacy compute and
adapter gone.

### Phase 3 - Germany ordinary stages (12 stages, posture-flattened)

1. Collapse the three posture-selected pairs/triples in
   `germany_2025_stages.py` into single declared stages
   (`DE25-00-FILING-POSTURE-GATE`, `DE25-07-TAXABLE-INCOME`,
   `DE25-08-INCOME-TAX-TARIFF`), each with merged `legal_refs` and
   conditional `legal_formula` text.
2. Change `germany_ordinary_law_stages_2025()` to take no posture
   argument and return one canonical tuple of `LawStage`.
3. Create `tax_pipeline/germany_ordinary_2025_rules.py`. Per-stage
   `calculate` functions for each of the 12 declared stages. Bodies
   moved from `compute_joint_ordinary_assessment_2025`. The three
   posture-aware stages branch internally on
   `de.ordinary.filing_posture` (an input fact).
4. Rewire `germany_model.py` to call `execute_rule_graph(...)`.
5. **Delete** `compute_joint_ordinary_assessment_2025`.
6. **Delete** `adapt_germany_ordinary_stage_results_2025`.
7. **Delete** `_germany_ordinary_stage_results` from
   `rule_narrative_packets.py`.
8. Update narrative packet builder fixtures, posture comparison tests,
   and any rule_id references in tests
   (`test_germany_2025_stages.py`, `test_rule_narratives.py`,
   `test_law_stage_graph.py`'s
   `test_every_declared_law_stage_has_a_real_legal_formula`).
9. Update `narrative/templates/`: rename
   `DE25-00-JOINT-GATE.jinja` -> `DE25-00-FILING-POSTURE-GATE.jinja`,
   delete the other two; same for the DE25-07 and DE25-08 pairs.
10. Ordinary cases in `test_germany_2025_law.py` stay green; the
    married_separate fail-closed at `final_legal_output.py:85-91`
    remains, now realized by the consolidated gate's `calculate` body.

### Phase 4 - US stages (22 stages, split 4a/4b)

- **4a**: `US25-00` through `US25-08` (filing position, wage translation,
  income side, capital buckets, § 1256, line 7a, preferential capital
  base, AGI, taxable income).
- **4b**: `US25-09` through `US25-21` (regular tax, Form 1116 gate,
  FTC denominator/limit/available/baseline, treaty US-source dividends
  through additional FTC, NIIT, payments).

Treaty integration is clean by this point: `US25-17-TREATY-GERMAN-RESIDUAL-CAP`
already declares `de.stage.us_source_dividend_tax_and_credit` as an input,
which now flows from the executed Germany capital rules (Phase 2) via
`pipeline_context`.

After 4b: **delete** `compute_us_assessment_2025` and any remaining
helpers in `us_2025_law.py`. The file becomes a thin module of constants
(URLs, IRS form references) and pure utility functions called *from*
rule bodies (e.g. `section_1_tax(taxable_income, posture)` if it exists
as a reusable helper).

### Phase 5 - Final cleanup (rolls into earlier phases where possible)

By the end of Phase 4 these should already be gone:

- `_execute_stage_projection` (`rule_narrative_packets.py:50-74`)
- `adapt_*_stage_results_2025`, `_result`, `_projection_stage_results`
  in all three `*_stages.py`
- `"external fact for {key}"` placeholders
- The big `compute_*` functions

Final phase-5 sweep:

1. Replace narrative-string-as-fact-value entries
   (`rule_narrative_packets.py:606, 735-736`) with real values now
   available in `final_facts`.
2. Replace any remaining `"projects existing output without recomputing
   formulas"` precision_notes with the stage's declared `rounding_policy`.
3. Drop the redundant `template_id` field from
   `RuleGraphExecution.to_graph_dict`; `narrative_templates` is enough.
4. Add a structural test that monkey-patches one `LawRule.calculate` to
   raise and asserts that `final-legal-output.json` generation fails
   closed for that stage. This proves the rule graph is now load-bearing.
5. Delete the `Assessment` output dataclasses if no consumer still needs
   them; otherwise convert any remaining producers to project from
   `final_facts`.

## Out of scope (separate fixes)

- **H1** (all 58 templates byte-identical): orthogonal. Either author
  per-rule narrative content or update ENGINE-SPEC.md to bless shared
  scaffolding.
- **H2** (`DE25-FACTS` / `US25-FACTS` non-legal authorities): delete
  those summary-bundle rules from the rule graph or attach real
  authorities.
- **L2** (generic `form_line_refs` on declared stages): mechanical fix.

## Form renderer migration: keep dataclasses as views during phases 1-4

Form renderers in `germany_model.py` / `us_model.py` walk the typed
`Assessment` dataclasses to produce ELSTER CSVs, IRS Form 1040 line
projections, Anlage KAP rows, etc. We keep these dataclasses alive as
read-only *views* projected from `RuleGraphExecution.final_facts` after
the rule graph runs. Form renderers are not modified during phases 1-4.

Per phase, the orchestrator changes from:

```
result = compute_X(inputs)  # legacy compute writes Assessment
```

to:

```
execution = execute_X_rule_graph(inputs, ...)
result = X_assessment_from_final_facts(execution.final_facts)
```

The projection function lives next to the rule definitions
(e.g. `treaty_2025_rules.py::treaty_assessment_from_final_facts`) and is
a thin name-translation layer. If a `LawStage.output_keys` name changes,
the projection function changes with it; otherwise the form-renderer
test surface stays untouched.

After phase 4 we may run a separate sweep ("Phase 6 / option ii") to
delete the dataclasses entirely and migrate form renderers to read
`final_facts` directly (likely via `TypedDict`). That sweep is decided
on its own merits, not bundled into the legal-core migration.

## Risk

- **Test churn**: bounded. Legal-math goldens in `test_germany_2025_law.py`
  / `test_us_2025_law.py` keep working because the Assessment-as-view
  preserves dataclass field access. Form-output goldens in
  `test_form_outputs.py` are unaffected because form renderers are
  unchanged through phase 4.
- **Risk surface per phase**: the projection function from `final_facts`
  to the Assessment view. Failure mode is a missing dataclass field at
  construction time -> noisy fail-closed at orchestrator time, not silent
  wrong numbers.
- **Performance**: low. Same Decimal math, reorganized.
- **Schema**: low. JSON outputs preserve their shape.
- **Reversibility**: each phase is one PR; revert == single PR revert.

## Acceptance for the whole effort

1. No `lambda facts: {output_key: pre_computed_value}` pattern anywhere.
2. No `compute_*` function that produces tax values outside the rule
   graph.
3. Every node in `legal-execution-graph.json` was produced by a
   `LawRule.calculate` that *executed legal arithmetic*, verified by the
   phase-5 monkey-patch test.
4. Every declared stage carries a real `legal_formula` (already done in
   Phase 0).
5. Demo fixture goldens byte-identical before and after.
6. `_execute_stage_projection`, `adapt_*_stage_results_2025`,
   `_projection_stage_results`, and `"external fact for {key}"`
   placeholders deleted.

## Estimated size (revised upward)

This is a larger undertaking than the prior draft suggested because we
are *rewriting* the legal core, not adding a parallel structure.

- Phase 0: half day (DONE)
- Phase 1 (treaty pilot): 2-3 days
- Phase 2 (Germany capital): 3-5 days
- Phase 3 (Germany ordinary): 3-5 days
- Phase 4 (US, split 4a/4b): 6-10 days
- Phase 5 (cleanup): 1-2 days

Roughly 4-6 weeks of focused work plus golden-test reconciliation. Each
phase is one PR; phases ship independently.
