# Invariant Migration Plan — 2026-05-01

**Goal.** Fix every Critical/High/Medium/Low finding from the
`.review/2026-05-01/` review trio, AND establish structural invariants
that prevent the *class* of each bug from re-emerging. The end state
is a `make check` that fails closed if any invariant is violated.

**Source reviews.**
- `.review/2026-05-01/correctness-review.md` (37 findings; 3C/9H/12M/13L)
- `.review/2026-05-01/architecture-flow-review.md` (3 leaks; Phase 2/3 LEAKY)
- `.review/2026-05-01/per-function-audit.md` (every rule CORRECT)

**Non-goals.**
- Don't change tax math (per-function audit confirms it's correct).
- Don't rewrite the four-rule-graph forest topology — only add a typed
  bridge stage where the seam carries legal invariants.
- Don't break existing fingerprint stability — audit packets must
  remain reproducible across the migration.

---

## 1. Invariant catalog

Eleven structural invariants, grouped by mechanism. Each ties to
specific bugs found and prevents a class of recurrence.

| # | Invariant | Mechanism | Catches |
|---|---|---|---|
| I1 | No legal constant literal outside the law modules | Source-grep test (generalized) | CR1 (treaty 0.15 in loaders) and any future drift |
| I2 | Every value in `final-legal-output.json` traces to a `StageResult.output_fingerprint` | Cross-reference test | Architecture LEAK-1 (final refund), LEAK-3 (KAP line 19) |
| I3 | Every form line the renderer touches has a matching `OutputDeclaration.form_line_refs` | Bidirectional renderer↔stage test | CR3 waypoint misclassification, future drift |
| I4 | No silent zero defaults on declared rule inputs | AST scan rejecting `.get(key, ZERO_*)` in `*_2025_rules.py` | H5 treaty25_17 silent FTC denial |
| I5 | No `Decimal` arithmetic in `pipelines/y2025/*projections*.py` or in pipeline orchestrator main() bodies | AST scan for `BinOp` over Decimal/output keys | LEAK-1, LEAK-3 generally |
| I6 | Fingerprint payloads contain only canonical values, never `repr(value)` | `stable_fingerprint` rejects `*_repr` keys; grep test | H1 germany_ordinary_2025_rules.py:544 drift |
| I7 | Rule `calculate(facts)` reads only declared `input_fact_keys` | Runtime tracking-dict in `execute_rule_graph` | DE25-00 reading undeclared `de.ordinary.raw_inputs` |
| I8 | Rule `calculate` writes only declared `output_keys` | Already enforced by `validate_result`; tighten to per-assignment | Future drift |
| I9 | Atomic file writes use unique temp filenames + parent fsync | Use `tempfile.NamedTemporaryFile`; concurrency test | H9 atomic-write race |
| I10 | All file reads pass `encoding="utf-8"` | grep test against `.read_text(` / `csv.DictReader(open(`) without encoding | L-encoding |
| I11 | Form-bound legal values flow only via a typed `LegalValue(amount, stage_id, output_key)` envelope | Type system + runtime check at form-renderer boundary | Future drift in the same class as LEAK-1/3 |
| I12 | Narrative templates address inputs by key, never positional `rule.inputs[N]` | Migrate templates to `rule.inputs_by_key["de.ordinary.gross_wages"].value`; AST grep rejects `rule.inputs[<int>]` | Position-shift regressions when adding new declared inputs (the WS-3A redo surfaced this on DE25-00 / DE25-07 / US25-08+ when prepending `us.assessment.inputs`) |

I1–I6, I9, I10 are **enforceable today** with no architectural change.
I7, I8, I12 require small changes to the executor / template renderer.
I11 is the strongest defense for Bucket B (legal math escapes the graph)
but requires touching every rule's return value and every form renderer
input — defer to phase 4 as a single coordinated migration.

---

## 1.5. Two-pipeline architecture (Pipeline 1: Derivation, Pipeline 2: Legal)

**Decided 2026-05-01.** The engine splits into two deterministic
pipelines connected by a typed, persisted boundary:

```
raw facts (CSVs, JSON, profile inputs)
  ↓ [Pipeline 1: Derivation]
derived facts + positions (typed, canonical, persisted to disk)
  ↓ [Pipeline 2: Legal]
final legal output + audit graph
```

**Why the split.** Currently the engine mixes derivation (1099 box
filtering, fund classification merging, per-symbol aggregation,
source-country splits, treaty dividend item assembly) with legal
interpretation (§ 20 EStG bucket assembly, § 32d Abs. 5 FTC, § 1411
NIIT, Pub. 514 re-sourcing). DE25-13's calculate body has five
embedded derivations; ``load_fund_classification`` does the InvStG
§ 2 Abs. 6 merge invisibly in the loader. Mixing them defeats two
separate audit goals: (1) "did we read the raw inputs correctly?" and
(2) "did we apply the law correctly?"

**Boundary contract.**
- Pipeline 1 produces ``derived-facts.json`` (the typed canonical
  derived facts) and ``derivation-graph.json`` (Pipeline 1's audit
  graph).
- Pipeline 2 reads ``derived-facts.json`` as initial facts and
  produces ``legal-execution-graph.json`` and ``final-legal-output.json``
  unchanged.
- Reproducibility test: re-running Pipeline 2 from a persisted
  ``derived-facts.json`` produces byte-identical
  ``final-legal-output.json``. This isolates Pipeline 1 bugs (raw
  data drift) from Pipeline 2 bugs (legal interpretation drift).

**Schema.** Pipeline 1 stages reuse ``LawStage`` with empty
``form_line_refs`` and an ``AuditWaypoint`` from the closed enum
(typically ``PER_POSTEN_AGGREGATION``). Stage IDs are prefixed
``DERIVE-`` to distinguish the pipeline at a glance:
``DERIVE-DE25-FUND-CLASSIFICATION``, ``DERIVE-DE25-13C-1099-BOX-FILTER``,
``DERIVE-US25-CAPITAL-FACT-ASSEMBLY``, etc.

**Module layout.**
- ``tax_pipeline/derivation/germany_2025_derivations.py`` — German
  Pipeline 1 stages.
- ``tax_pipeline/derivation/usa_2025_derivations.py`` — U.S. Pipeline 1
  stages.
- ``tax_pipeline/derivation/runtime.py`` — orchestrator
  (``execute_derivation_pipeline()``) that calls ``execute_rule_graph``
  with derivation rules, persists ``derived-facts.json`` +
  ``derivation-graph.json`` atomically.
- ``tax_pipeline/pipelines/y2025/run_derivation.py`` — pipeline-module
  entry executed BEFORE ``germany_model`` / ``us_model`` in
  ``run_year.py``.

**Invariant scope.**
- I1, I4, I6, I7, I8, I9, I10, I11, I12 apply to BOTH pipelines.
- I2, I3, I5 apply primarily to Pipeline 2 (final-output traceability,
  form-line provenance, no-Decimal-math-in-orchestrators).
- New invariant: every Pipeline 1 stage's outputs must appear in
  ``derived-facts.json`` (analogous to I2 for Pipeline 2).
- New invariant: every input to a Pipeline 2 rule's
  ``input_fact_keys`` must come from either initial facts (raw user
  configuration like elections, posture) OR ``derived-facts.json`` —
  never from in-memory orchestrator state. Enforced by reading
  ``derived-facts.json`` as the sole bridge.

**Where Phase 4 promotions land.**
- ``BRIDGE25-FOREIGN-TAX-RECONCILIATION`` (WS-4A) — Pipeline 2; it's a
  legal reconciliation invariant.
- ``DE25-22-FINAL-REFUND`` (WS-4B) — Pipeline 2; § 36 Abs. 2 EStG
  is a legal computation.
- ``DE25-FORM-KAP-PROJECTION`` (WS-4C) — Pipeline 2 tail; legal-output
  presentation onto Anlage KAP form lines.
- ``LegalValue`` envelope (WS-4D) — Pipeline 2 only. Pipeline 1
  outputs are derived-fact dicts, not form-bound legal values.

**Where the existing legal stages live.** All current DE25-* / US25-*
/ TREATY25-* stages stay in Pipeline 2. Their inputs change to read
from ``derived-facts.json`` instead of in-memory state — but the
stage definitions are unchanged.

---

## 2. Phasing and dependencies

```
Phase 1 — Tier 1 tests land RED (5 tests, parallel)
         |
         v
Phase 2 — Mechanical bug fixes (each pairs with a Phase 1 test → GREEN)
         |
         v
Phase 3 — Tier 2 tracking-dict instrumentation
         |
         v
Phase 4 — Tier 3 architectural promotions (3 stages + LegalValue)
         |
         v
Phase 5 — Medium/Low cleanup
         |
         v
Phase 6 — Tier 4 make check integration
```

Phase 1 work is independent — five workstreams in parallel.
Phase 2 work depends on the corresponding Phase 1 test landing first.
Phase 3 stands alone but should land before Phase 4 (the new stages
benefit from tracking-dict enforcement).
Phase 4 has internal dependencies (BRIDGE25 first, then the consumer
stages that depend on its outputs).

Each workstream below specifies: test file, fix file, dependencies,
acceptance criteria, and a commit message template.

---

## 3. Phase 1 — Tier 1 tests (RED-first, parallel agents)

Five workstreams. Each agent writes ONE test file that fails against
current main, then stops. Phase 2 fixes turn each test green.

### WS-1: I1 generalized-literal-bypass test

**Test file:** `tests/y_agnostic/test_no_legal_constant_literal_bypass.py`

**What it tests:**
- Recursively scan `tax_pipeline/` for every Decimal/D constructor call
  AND every string literal that gets passed to `Decimal(...)` or `D(...)`.
- For each value `V`, look up whether `V` matches any constant declared
  in `germany_2025_law.py`, `us_2025_law.py`, or `treaty_2025_law.py`
  (compare numerically, not textually).
- If `V` matches a declared law-module constant AND the literal lives
  outside those three modules, fail the test with a "use the named
  constant" message.
- Allow string-form magic numbers when they're inside CSV row defaults
  IF the row is then converted via the named constant — the test
  should detect both `D("0.15")` and `Decimal(str(row.get("rate", "0.15")))`.

**Allowlist mechanism:** small, citation-anchored set, like the existing
`ALLOWED_NON_TREATY_DECIMAL_0_15_OCCURRENCES` pattern.

**Acceptance:** test exists, fails on current main with offender:
`tax_pipeline/pipelines/y2025/germany_loaders.py:236`. Cap report to
~150 LOC.

**Commit (test only):** `Add invariant: no legal-constant literal bypass`

### WS-2: I2 final-output traceability test

**Test file:** `tests/y_agnostic/test_final_output_values_trace_to_rule_outputs.py`

**What it tests:**
- Materialize a demo workspace (use `tests/generated_demo.py`).
- Run the pipeline.
- Load `final-legal-output.json` and `legal-execution-graph.json`.
- For every numeric leaf in `final-legal-output.json` (recursively walk
  the JSON; treat strings that parse as Decimal as numeric), require
  that the leaf's value appears in some node's `output_fingerprints`
  chain in the legal-execution-graph (match by Decimal value with q2
  tolerance).
- Allow audit-packet metadata fields (timestamps, fingerprints,
  source-file digests) to bypass the check via an explicit allowlist.

**Acceptance:** fails on current main, listing at minimum
`final_target_refund_eur`, `kap_line_19`, and the foreign-tax
reconciliation totals as untraceable values. Cap to ~200 LOC.

**Commit:** `Add invariant: every final-output value traces to a rule output`

### WS-3: I3 form-renderer↔OutputDeclaration test

**Test file:** `tests/y_agnostic/test_form_renderer_lines_match_output_declarations.py`

**What it tests:**
- AST-scan `tax_pipeline/forms/germany.py` and
  `tax_pipeline/forms/usa.py` for every call shaped like
  `_required_form_line(rows, "Anlage X", "Zeile Y", …)` or
  `_required_form_line(rows, "Form 1040", "line N", …)`.
- For each `(form, line)` pair, walk every `LawStage` from
  `germany_law_stages_2025()` / `usa_law_stages_2025()` /
  `treaty_law_stages_2025()` and check that some `OutputDeclaration`
  declares a `FormLineRef` with the same `(form, line)` after
  normalization.
- Bidirectional: also flag `OutputDeclaration.form_line_refs` that no
  renderer reads (orphan declarations).

**Acceptance:** fails on current main showing DE25-17 / DE25-19 outputs
mis-classified as `DIAGNOSTIC_CROSS_CHECK` despite Anlage KAP soli line
being read by the renderer. Cap to ~200 LOC.

**Commit:** `Add invariant: form renderer lines match OutputDeclaration form_line_refs`

### WS-4: I4 no-silent-zero-defaults test

**Test file:** `tests/y_agnostic/test_no_silent_zero_defaults_in_rules.py`

**What it tests:**
- AST-scan `tax_pipeline/germany_ordinary_2025_rules.py`,
  `tax_pipeline/germany_capital_2025_rules.py`,
  `tax_pipeline/us_2025_rules.py`, `tax_pipeline/treaty_2025_rules.py`.
- Find every `Call(func=Attribute(attr='get'), args=[<key>, <default>])`
  where `<key>` is a string and `<default>` is one of: `Decimal("0")`,
  `Decimal("0.00")`, `D("0")`, `D("0.00")`, `ZERO_USD`, `ZERO_EUR`,
  `Decimal()`, `0`, `0.0`.
- For each match, fail with a message instructing the author to use
  `facts[key]` (raises `KeyError`) so missing inputs fail closed per
  CLAUDE.md.
- Allowlist for known-safe optional inputs (e.g., `other_spouse_*`) via
  explicit `# pragma: nzd-allow <reason>` comment marker.

**Acceptance:** fails on current main with at minimum
`treaty_2025_rules.py treaty25_17` `.get` calls flagged. Cap to ~150 LOC.

**Commit:** `Add invariant: no silent zero defaults in rule calculate bodies`

### WS-5: I5 no-Decimal-arithmetic-in-projections test

**Test file:** `tests/y_agnostic/test_no_legal_math_outside_rule_graph.py`

**What it tests:**
- AST-scan `tax_pipeline/pipelines/y2025/germany_projections.py`,
  `tax_pipeline/pipelines/y2025/germany_model.py`,
  `tax_pipeline/pipelines/y2025/us_model.py`, and other pipeline
  orchestrator scripts.
- Find every `BinOp(left, +/-/*//, right)` where:
  - either operand is the result of a known rule-output access
    (e.g., `capital.foreign_tax_credit_eur`,
    `ordinary.joint_taxable_income_eur`, `inputs[k]` for a known
    fact key), OR
  - either operand is a `Decimal` constructed in this file from a
    rule-output value.
- For each match, fail with a message telling the author to promote
  the computation to a `LawRule.calculate` body.
- Allowlist for explicit non-legal arithmetic (e.g., string formatting
  totals for narrative rendering) via `# pragma: legal-math-ok <reason>`.

**Acceptance:** fails on current main flagging the headline
refund computation in `germany_model.py:287-306`, the foreign-tax
reconciliation at `germany_model.py:259-269`, and `kap_line_19` math
in `germany_projections.py:113`. Cap to ~250 LOC.

**Commit:** `Add invariant: no Decimal arithmetic on rule outputs outside the rule graph`

### WS-6: I6 no-repr-in-fingerprint test

**Test file:** `tests/y_agnostic/test_fingerprint_uses_canonical_value.py`

**What it tests:**
- Two-part: (1) grep `tax_pipeline/` for `stable_fingerprint(...repr(...)...)`
  patterns and reject. (2) Modify `tax_pipeline/core/facts.py`
  `stable_fingerprint` to reject any payload key that ends in `_repr`
  or starts with `repr_` (raise `ValueError("fingerprint payload must
  use canonical 'value' field, not repr-stringified")`). The grep test
  asserts the rejection works.

**Acceptance:** fails on current main flagging
`germany_ordinary_2025_rules.py:544`. Cap to ~80 LOC.

**Commit:** `Add invariant: fingerprint payloads use canonical value never repr`

---

## 4. Phase 2 — Mechanical fixes (each pairs with Phase 1 test)

Six workstreams. Each fixes ONE specific bug; the corresponding Phase 1
test goes GREEN as a side effect. No architectural change.

### WS-2A: Fix CR1 (treaty literal in loader)

**Pairs with WS-1.**

**Files:** `tax_pipeline/pipelines/y2025/germany_loaders.py`

**Change:** import
`DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE` from
`tax_pipeline.treaty_2025_law`. Replace the `"0.15"` fallback at
line 236 with a `format(DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE, "f")`
expression. Better still: replace the `D(str(row.get("treaty_rate",
"0.15")))` pattern with `D(row["treaty_rate"]) if row.get("treaty_rate")
else DBA_USA_ART_10_2_B_PORTFOLIO_DIVIDEND_RATE` so the named constant
is the actual fallback object.

**Acceptance:** WS-1 test goes GREEN. All existing tests still pass.

**Commit:** `Use canonical DBA-USA Art. 10(2)(b) rate in treaty dividend loader`

### WS-2B: Fix CR3 (DE25-17 / DE25-19 waypoint misclassification)

**Pairs with WS-3.**

**Files:** `tax_pipeline/germany_2025_stages.py`

**Change:** locate DE25-17 (`section_32d1_gross_tax`) and DE25-19
(`solidarity_surcharge`) declarations. Replace
`audit_waypoints=frozenset({AuditWaypoint.DIAGNOSTIC_CROSS_CHECK})` for
the form-bound outputs with `form_line_refs=(FormLineRef(
form="Anlage KAP", line="…", url=ESTG_32D_URL or SOLZG_4_URL), )`. Keep
the `DIAGNOSTIC_CROSS_CHECK` waypoint ONLY on the parallel
no-Teilfreistellung outputs that are genuinely audit-only.

Cross-reference each output against `forms/germany.py` to confirm which
exact `(form, line)` it lands on.

**Acceptance:** WS-3 test goes GREEN. Stage fingerprints update (audit
packet churn is acceptable here because the prior classification was
wrong).

**Commit:** `Fix DE25-17 and DE25-19 audit-waypoint misclassification`

### WS-2C: Fix H5 (treaty25_17 silent fail-open)

**Pairs with WS-4.**

**Files:** `tax_pipeline/treaty_2025_rules.py`

**Change:** in `treaty25_17_german_residual_cap`, replace every
`facts.get("de.stage.…", ZERO_USD)` with `facts["de.stage.…"]`. If a
key is genuinely optional (depends on whether DE-side ran), thread it
through `stage.input_fact_keys` and rely on the executor's
`KeyError("missing input facts")`.

If the upstream gate genuinely produces a defaulted-zero value, that
should be a stage in itself producing an explicit
`Decimal("0.00")` with a `RECONCILIATION_INVARIANT` waypoint, not a
silent fallback in a downstream rule.

**Acceptance:** WS-4 test goes GREEN. Existing tests still pass; if
they fail, the upstream gate path needs the explicit-zero stage
added.

**Commit:** `Remove silent fail-open in TREATY25-17 German residual cap`

### WS-2D: Fix H1 (repr fingerprint drift)

**Pairs with WS-6.**

**Files:** `tax_pipeline/germany_ordinary_2025_rules.py:544` (and any
other site the test surfaces).

**Change:** replace
`stable_fingerprint({"fact_key": key, "value_repr": repr(value)})` with
`stable_fingerprint({"fact_key": key, "value": value})` exactly as the
existing canonical helper does. This was the same fix applied in
commit `628082e` for capital + US fingerprints; it just wasn't propagated
to the ordinary helper.

**Acceptance:** WS-6 test goes GREEN. Existing tests still pass (the
canonicalization in `_fingerprintable` produces deterministic output
for Mappings).

**Commit:** `Drop repr() from germany_ordinary_initial_fingerprints to match canonical helper`

### WS-2E: Fix H9 (atomic-write filename collision)

**Files:** `tax_pipeline/pipelines/y2025/final_legal_output.py`
`_atomic_write_text`.

**Change:**
1. Replace `tmp = path.with_name(f".{path.name}.tmp")` with
   `tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.",
   suffix=".tmp", delete=False)`. Read the resulting `tmp.name` for
   the rename target.
2. After `os.replace(tmp.name, path)`, open the parent directory with
   `os.open(path.parent, os.O_RDONLY)` and `os.fsync(fd)` it (POSIX),
   then close. Skip on Windows (no-op).
3. Add a concurrency test that spawns N=8 threads writing the same
   target with different content; assert exactly one final content
   is on disk and no `.tmp` siblings remain.

**Acceptance:** new test in
`tests/y_agnostic/test_final_legal_output_atomic.py` (extend the existing class)
passes. Existing tests pass.

**Commit:** `Atomic-write helper: unique temp filename + parent-directory fsync`

### WS-2F: Add tests for I10 (encoding) and fix call sites

**Test:** `tests/y_agnostic/test_file_reads_specify_utf8_encoding.py` — grep
`tax_pipeline/` for `Path.read_text(`, `open(`, `csv.DictReader(open(`
without an `encoding=` argument; reject.

**Fix:** add `encoding="utf-8"` to every flagged call site.

**Acceptance:** test goes GREEN. Existing tests pass.

**Commit:** `Pin encoding="utf-8" on all pipeline file reads`

---

## 5. Phase 3 — Tier 2 runtime instrumentation

### WS-3A: I7 / I8 tracking-dict input + output enforcement

**Files:** `tax_pipeline/core/stages.py` `execute_rule_graph`.

**Design:**
1. Define `TrackingMapping(Mapping)` that wraps a dict and records
   which keys are read via `__getitem__` / `__contains__` / `keys()`
   / `__iter__`.
2. In `execute_rule_graph`, instead of passing `dict(facts)` to
   `rule.calculate(...)`, pass `TrackingMapping(dict(facts))`.
3. After each calculate returns, compute
   `read_keys = tracker.read_keys`. Assert
   `read_keys ⊆ set(stage.input_fact_keys)`. If not, raise
   `RuleInputDeclarationError(stage_id, undeclared_keys)`.
4. For output enforcement: the calculate's return value is already
   validated by `StageResult.validate_result` against
   `stage.output_keys`. Tighten by also asserting no module-level state
   was mutated (use `weakref` to the original `stage` object and verify
   identity).

**Test:** `tests/y_agnostic/test_rule_input_tracking.py` — construct a stage that
reads an undeclared key in its calculate body; assert the executor
raises `RuleInputDeclarationError` with the offending key.

**Pairs with fix:** DE25-00 reading `de.ordinary.raw_inputs`
undeclared. The fix is to add `de.ordinary.raw_inputs` to the
DE25-00 stage's `input_fact_keys` (and propagate the dependency back
to whoever produces it — likely an initial-facts loader).

**Acceptance:** new test passes. DE25-00 fails the new check
initially; fix the stage declaration; check goes green. All existing
tests still pass.

**Commit:** `Enforce rule input declarations via tracking-dict in executor`

---

## 6. Phase 4 — Tier 3 architectural promotions

These promotions move computation from orchestrator scripts and
renderer projections INTO the rule graph. After this phase, the
WS-2 (I2 traceability) test goes fully GREEN.

### WS-4A: BRIDGE25-FOREIGN-TAX-RECONCILIATION

**New stage** in a new file `tax_pipeline/bridge_2025_stages.py` (or
in `treaty_2025_stages.py` as `BRIDGE25-…`).

**Purpose:** assert
```
foreign_tax_1099_eur
  + bank_certificate_foreign_tax_credited_eur
  + bank_certificate_foreign_tax_not_credited_eur
  + treaty_us_source_dividend_allowed_us_tax_eur
  == capital.explicit_foreign_tax_total
```
This is the legal invariant currently enforced in
`germany_model.py:259-269`.

**Inputs:** the four EUR amounts above plus
`capital.explicit_foreign_tax_total`.

**Outputs:**
- `bridge.foreign_tax_reconciliation_total_eur` (the verified sum,
  classified `RECONCILIATION_INVARIANT`).
- `bridge.foreign_tax_reconciliation_status` (a string `"reconciled"`
  with `AuditWaypoint.RECONCILIATION_INVARIANT`; if the assertion
  fails, the rule raises a `LegalInvariantViolation` that the
  executor surfaces as a stage failure).

**Wiring:** add to the pipeline_modules order BEFORE
`germany_elster_entry_sheet`. Remove the script-level reconciliation
from `germany_model.py:259-269`.

**TDD:**
1. Failing test: `tests/y2025/test_bridge_foreign_tax_reconciliation.py`
   — construct facts where the four amounts sum != total; assert
   `LegalInvariantViolation` fires.
2. Implement the stage.
3. Test green.

**Acceptance:** I2 test passes for the reconciliation invariant.
Existing tests pass.

**Commit:** `Add BRIDGE25-FOREIGN-TAX-RECONCILIATION stage`

### WS-4B: DE25-22-FINAL-REFUND

**New stage** in `tax_pipeline/germany_2025_stages.py`.

**Purpose:** compute the final German refund, which today lives in
`germany_model.py:287-306`. The legal formula is:
```
final_target = ordinary_refund_before_capital
             - capital_tax_with_teilfreistellung_after_treaty
             + domestic_capital_withholding_credit
             + equipment_total
             + (other_income_22nr3_taxable adjustments per § 22 Nr. 3)
```
(or whatever the current main() actually computes — agent must
audit and reproduce exactly).

**Inputs:** the rule-output keys for each component.

**Outputs:**
- `de.final.target_refund_eur` (the headline number, with
  `FormLineRef(form="Hauptvordruck", line="Erstattung")` and citation
  `§ 36 Abs. 2 EStG` URL `ESTG_36_URL`).

**Citations:** § 36 Abs. 2 EStG; § 32d EStG; reference InvStG § 20.

**Wiring:** add to germany_law_stages_2025() at the end. Remove the
script-level computation from germany_model.py main(). The main()
function should now read the rule output and write it to JSON, with
no arithmetic of its own.

**TDD:**
1. Failing test verifies the rule output equals what main() currently
   produces for the demo workspace.
2. Implement.
3. Test green.

**Acceptance:** I2 test passes for `final_target_refund_eur`. The
field appears in `legal-execution-graph.json`.

**Commit:** `Promote German final-refund computation to DE25-22-FINAL-REFUND stage`

### WS-4C: DE25-FORM-KAP-PROJECTION

**New stage** in `tax_pipeline/germany_2025_stages.py`.

**Purpose:** compute the Anlage KAP form-line projection (currently
in `germany_projections.py`). The key computation is
`kap_line_19 = ordinary + stock_pos − stock_neg + option_pos − option_neg`
plus the per-line projection rows.

**Inputs:** rule-output keys for ordinary capital income, stock_pos,
stock_neg, option_pos, option_neg, foreign_tax, fund classifications.

**Outputs:**
- `de.kap.line_19_eur` (form line, `FormLineRef(form="Anlage KAP",
  line="Zeile 19")`).
- `de.kap.line_20_eur`, `_21_eur`, `_23_eur`, `_24_eur`, `_41_eur`
  (each with proper `FormLineRef`).
- `de.kap_inv.fund_rows` (per-fund summary, classified
  `PER_POSTEN_AGGREGATION` plus `FormLineRef(form="Anlage KAP-INV",
  line="…")`).

**Wiring:** the renderer (`germany_projections.capital_form_projection_2025`)
becomes a thin shim that reads the rule outputs and shapes them into
the CSV row tuples. NO arithmetic in the renderer.

**TDD:**
1. Failing test asserts `kap_line_19` is produced by a rule, not by
   the projection helper.
2. Implement the stage.
3. Update the renderer to consume the rule outputs.
4. Test green.

**Acceptance:** I2 test passes for KAP line 19 and related lines. I5
test passes for `germany_projections.py` (no Decimal arithmetic
remains). Existing tests pass.

**Commit:** `Promote Anlage KAP form-line projection to DE25-FORM-KAP-PROJECTION stage`

### WS-4D: LegalValue typed envelope

**New module:** `tax_pipeline/core/legal_value.py`

**Type:**
```python
@dataclass(frozen=True)
class LegalValue:
    amount: Decimal
    stage_id: str
    output_key: str
    fingerprint: str
```

**Mechanism:** `RuleGraphExecution.outputs` becomes a mapping from
`output_key` to `LegalValue` (instead of bare `Decimal`). The
form-renderer entry points (`forms/germany.py`, `forms/usa.py`) and
the verbose report builder accept `LegalValue` instances and validate
them at the boundary.

**Migration scope:**
- `core/stages.py`: extend `StageResult` to optionally wrap output
  values; preserve back-compat by allowing both Decimal and LegalValue
  reads during migration.
- Each rule's `calculate` keeps returning a `Mapping[str, Any]` (no
  change). The executor wraps the values in `LegalValue` after the
  calculate returns, using the `stage_id`, `output_key`, and computed
  `fingerprint`.
- `forms/germany.py` and `forms/usa.py` change their helper signatures
  to take `LegalValue` and assert `isinstance(value, LegalValue)`. A
  raw Decimal at the renderer boundary becomes a `TypeError`.
- `final_legal_output.py` includes the `(stage_id, output_key,
  fingerprint)` triple alongside each rendered value.

**TDD:**
1. Failing test: render a form using a raw Decimal; assert `TypeError`.
2. Implement LegalValue + executor wrap + renderer guards.
3. Test green.
4. Update existing renderer call sites to use the new envelope.

**Acceptance:** new test passes. All existing rendering tests still
pass after migration.

**Commit:** `Introduce LegalValue typed envelope at the rule→renderer boundary`

---

## 7. Phase 5 — Medium / Low cleanup

### WS-5A: DE25-13 derivation extraction (Medium) — RE-SCOPED to Pipeline 1

**Issue:** DE25-13 has five Phase-2 derivations embedded in its
200-line calculate body. Each is a deterministic transformation of
raw broker / 1099 / bank-certificate facts — derivation, not legal
interpretation.

**Re-scope per §1.5 (two-pipeline architecture):** the five
derivations move to Pipeline 1, not stay as more legal stages. After
extraction:
- Pipeline 1 stages produce derived facts.
- DE25-13 (Pipeline 2) consumes the derived facts and applies § 20
  EStG bucket assembly. Its calculate body shrinks to <50 lines
  containing only the legal interpretation.

**Pipeline 1 stages to create** (in
`tax_pipeline/derivation/germany_2025_derivations.py`):
- `DERIVE-DE25-13A-PER-SYMBOL-SALE-AGGREGATION` — per-symbol-year
  roll-up of broker sale facts. Citation: cost-basis aggregation
  conventions per § 20 Abs. 4 EStG.
- `DERIVE-DE25-13B-1099-BOX-FILTERING` — IRS 1099-DIV / 1099-INT
  box-1a vs Box-2a/3 split. Citation: 26 U.S.C. §§ 6042 / 6045
  reporting taxonomy.
- `DERIVE-DE25-13C-PER-SYMBOL-BANK-CERTIFICATE-BUCKETS` — per-symbol
  bank-certificate aggregation. Citation: § 43a Abs. 3 EStG bank
  certificate format.
- `DERIVE-DE25-13D-SOURCE-COUNTRY-CLASSIFICATION` — DE / US / other
  source split based on issuer / ISIN. Citation: DBA Art. 10 source
  rules.
- `DERIVE-DE25-13E-FOREIGN-TAX-INDEXING` — per-Posten foreign-tax
  table assembly. Citation: § 32d Abs. 5 EStG per-Posten foreign-tax
  credit.

**Depends on:** WS-5H (derivation pipeline framework) must land first.

**TDD per sub-stage:**
1. Write equivalence test pinning the derived-fact output against the
   value the existing DE25-13 calculate produced for the demo
   workspace.
2. Move the derivation logic into its own stage's calculate.
3. Update DE25-13 to consume the derived fact via its
   `input_fact_keys`.
4. Test green; existing DE25-13 test suite confirms equivalence.

**Acceptance:** DE25-13 calculate body shrinks to <50 lines. Each
derivation is a first-class audit-graph node in Pipeline 1's
`derivation-graph.json`.

**Commit (per sub-stage):** `Extract <name> derivation from DE25-13 to Pipeline 1 stage`

### WS-5B: load_fund_classification → Pipeline 1 stage (Medium) — RE-SCOPED

**Issue:** `load_fund_classification` merges three workspace-override
sources with the engine-shipped repo CSV. The merge is the InvStG
§ 2 Abs. 6 fund-type taxonomy applied to a workspace's specific
universe of symbols — derivation, not legal interpretation.

**Re-scope per §1.5:** becomes the FIRST Pipeline 1 stage built
(after WS-5H lands). It validates the framework on a small,
self-contained merge before WS-5A's five-stage extraction.

**Stage definition** (in
`tax_pipeline/derivation/germany_2025_derivations.py`):
- Stage ID: `DERIVE-DE25-FUND-CLASSIFICATION`
- Inputs:
  - `de.input.repo_fund_classification_csv` (frozen, engine-shipped)
  - `de.input.manual_overrides_fund_types`
  - `de.input.manual_overrides_aktienfonds_list`
  - `de.input.manual_overrides_non_aktienfonds_list`
- Output: `de.derived.fund_classification` with
  `AuditWaypoint.PER_POSTEN_AGGREGATION`.
- Citation: InvStG § 2 Abs. 6, URL `INVSTG_2_URL` (add to
  `germany_2025_law.py` if missing).

**Loader becomes:** the existing `load_fund_classification()` is
removed (or reduced to a thin shim that runs Pipeline 1 just for the
fund-classification slice for backward-compat callers). The
canonical source of `fund_classification` is now the Pipeline 1
output persisted in `derived-facts.json`.

**Pipeline 2 wiring:** DE25-13's `input_fact_keys` change
`de.capital.fund_classification` → `de.derived.fund_classification`.

**Depends on:** WS-5H.

**TDD:**
1. Write equivalence test: stage's output equals
   `load_fund_classification()`'s prior return for known inputs.
2. Implement the stage.
3. Run full suite; existing fund-classification tests still pass.

**Acceptance:** fund classification appears in
`derivation-graph.json`. `derived-facts.json` includes
`de.derived.fund_classification`. DE25-13 reads from there. Existing
tests pass.

**Commit:** `Promote load_fund_classification to DERIVE-DE25-FUND-CLASSIFICATION stage`

### WS-5C: Eliminate parallel fingerprint chain in final_legal_output (Medium)

**Issue:** `final_legal_output.py:642-708` builds a parallel third-domain
fingerprint chain unrelated to the executed `StageResult`
fingerprints (architecture review's "net-new" finding).

**Plan:** replace the parallel computation with direct reads from
`RuleGraphExecution.stage_results`. The fingerprints in the final
output should BE the stage-result fingerprints, not new ones.

**Acceptance:** I2 test still passes. Audit packets reference the
same fingerprint values they always did (no churn).

**Commit:** `Drop parallel fingerprint chain in final_legal_output; reuse StageResult fingerprints`

### WS-5D: Move module-level workspace resolution to function-scope (Medium)

**Issue:** `tax_pipeline/pipelines/y2025/germany_loaders.py` and
`germany_projections.py` resolve `YEAR_PATHS` at import time. This is
an implicit Phase-1 read that fires before any explicit pipeline call,
which makes testing harder and breaks the Phase-1/Phase-2/Phase-3
separation.

**Plan:** make the resolution lazy. Replace module-level constants
with a `_year_paths()` helper that resolves on first call and caches
in a `ContextVar` for thread-safety.

**Acceptance:** `python -c "import tax_pipeline.pipelines.y2025.germany_loaders"`
performs zero file reads. Existing pipeline runs work unchanged.

**Commit:** `Make pipeline-module workspace resolution lazy (no import-time I/O)`

### WS-5E: Tax-attorney verify of § 20 Abs. 6 ordering (Low)

**Issue:** ordering between non-stock losses and stock gains
(`germany_capital_2025_rules.py:343-345`) deserves verification
against BMF Abgeltungsteuer Rn. 122. Not flagged as wrong, just
unconfirmed.

**Plan:** add an inline citation comment with quoted BMF text and a
worked example test that verifies the ordering on a fact pattern that
distinguishes the two readings. If the reading turns out to be wrong,
this becomes a high-priority bug fix.

**Acceptance:** comment + test land. No code change unless the verify
surfaces a discrepancy.

**Commit:** `Pin § 20 Abs. 6 non-stock-loss-vs-stock-gain ordering with BMF Rn. 122 worked example`

### WS-5F: Cosmetic / docstring items (Low, batch)

13 items from `correctness-review.md` low section. Single PR; agent
walks the file and applies each. Acceptance: no test changes; just
docstring cleanup.

**Commit:** `Apply cosmetic / docstring fixes from 2026-05-01 correctness review`

### WS-5H: Derivation pipeline framework (blocks WS-5A and WS-5B)

**Issue:** there is no Pipeline 1 framework. WS-5A and WS-5B both
need ``execute_derivation_pipeline()``, the
``derivation/germany_2025_derivations.py`` /
``derivation/usa_2025_derivations.py`` modules, the
``derived-facts.json`` / ``derivation-graph.json`` artifacts, and
the ``run_derivation`` pipeline-module entry that runs before
``germany_model`` / ``us_model`` in ``run_year.py``.

**Plan:**
1. Add ``tax_pipeline/derivation/`` package (``__init__.py``,
   ``runtime.py``, empty ``germany_2025_derivations.py`` /
   ``usa_2025_derivations.py``).
2. Implement ``execute_derivation_pipeline(initial_facts, rules)``
   in ``runtime.py``. It calls the existing
   ``execute_rule_graph()`` from ``core/stages.py`` (reusing all the
   tracking-dict / fingerprint plumbing) and returns the
   ``RuleGraphExecution``. The orchestrator wraps that result into
   ``derived-facts.json`` (the final-facts dict, JSON-serializable
   form) and ``derivation-graph.json`` (audit graph, same shape as
   ``legal-execution-graph.json``).
3. Persist atomically using the existing ``_atomic_write_text`` from
   ``final_legal_output.py`` (extract to a shared module if needed,
   or import from there).
4. Add ``tax_pipeline/pipelines/y2025/run_derivation.py`` as the new
   pipeline-module entry. It reads raw inputs (workspace CSVs etc.),
   builds the Pipeline 1 initial facts, runs
   ``execute_derivation_pipeline()``, persists the artifacts.
5. Update ``run_year.py`` to invoke ``run_derivation`` BEFORE
   ``germany_model`` / ``us_model``.
6. Update ``germany_model.py`` / ``us_model.py`` to read the
   derived facts from ``derived-facts.json`` instead of computing
   them from raw inputs at orchestrator level. This removes
   per-orchestrator I/O on the 4-source merge etc.

**Stages to register at framework-land time:** none. WS-5H lands an
empty Pipeline 1 (no stages). WS-5B then registers
``DERIVE-DE25-FUND-CLASSIFICATION`` as the first stage. WS-5A
registers the five DE25-13 derivation stages.

**TDD:**
1. Failing test:
   ``tests/y_agnostic/test_derivation_pipeline_framework.py`` constructs a
   minimal Pipeline 1 (one trivial stage), runs
   ``execute_derivation_pipeline()``, asserts ``derived-facts.json``
   and ``derivation-graph.json`` are written atomically, contain
   the expected outputs, and that the persisted artifacts round-trip
   identically.
2. Reproducibility test:
   ``tests/y2025/test_derivation_to_legal_pipeline_reproducibility.py``
   runs Pipeline 1 + Pipeline 2 once for the demo workspace,
   captures ``final-legal-output.json`` bytes; runs Pipeline 2 again
   from the persisted ``derived-facts.json`` (skipping Pipeline 1);
   asserts byte-identical ``final-legal-output.json``.

**Acceptance:**
- Framework lands; both new tests green.
- Existing demo-workspace tests still pass (Pipeline 1 with no
  registered stages produces an empty ``derived-facts.json``;
  ``germany_model`` / ``us_model`` still work via fallback to
  current behavior until WS-5A / WS-5B move stages into Pipeline 1).
- The full suite total bumps by 2 new tests; failure baseline
  unchanged.

**Commit (single PR, multi-commit):**
1. ``Add derivation pipeline framework (empty stage set)``
2. ``Wire run_derivation into run_year.py before germany_model / us_model``
3. ``Add reproducibility test: Pipeline 2 from persisted derived facts is byte-identical``

**Stop condition:** WS-5H must NOT register any stages — leave
that to WS-5A and WS-5B. Keep the framework changes orthogonal to
the stage migrations so each can be reviewed independently.

### WS-5G: Narrative templates index inputs by key, never by position (I12)

**Issue surfaced during the WS-3A redo:** narrative templates address
inputs positionally (`{% set net = rule.inputs[0].value %}`). When a
new fact key is added to `LawStage.input_fact_keys`, the positional
indices shift and templates silently render wrong values (or raise
`JSONDecodeError`, as DE25-07-TAXABLE-INCOME.jinja did when the WS-3A
redo prepended a new declared input). The current workaround — append
new keys at the end of each tuple — is fragile and bakes in declaration
order as load-bearing for the audit graph.

**Plan:**
1. Extend `RuleNarrative` (or its `to_dict()` form, `tax_pipeline/core/narrative.py`)
   so the `rule.inputs` list carries the declared `key` alongside `value`.
   Add a derived `rule.inputs_by_key: dict[str, NarrativeInputValue]` that
   templates can address as `rule.inputs_by_key["de.ordinary.gross_wages"].value`.
2. Migrate every `rule.inputs[<int>]` reference in
   `tax_pipeline/narrative/templates/*.jinja` (≈40 files; grep
   `rule.inputs\[` to enumerate) to the by-key form.
3. Add an AST-style invariant test
   `tests/y_agnostic/test_narrative_templates_index_inputs_by_key.py` that scans
   every Jinja template for `rule.inputs[<int>]` and rejects.
4. Run full suite; fingerprint stability holds because the inputs
   list content is unchanged — only the addressing API moves to keys.

**Acceptance:**
- New invariant test green.
- Every existing narrative-template test still produces identical
  output bytes (no fingerprint churn on rendered narratives).
- Adding a new `input_fact_keys` entry no longer requires appending
  to the tuple end — keys can land in any position.

**Commit (one PR, multiple commits):**
1. `Extend RuleNarrative.to_dict with inputs_by_key view`
2. `Migrate narrative templates to address inputs by key (DE25 batch)`
3. `Migrate narrative templates to address inputs by key (US25 + treaty batch)`
4. `Add invariant: narrative templates index inputs by key`

---

## 8. Phase 6 — Tier 4 make check integration

### WS-6A: Wire invariant tests into `make check`

**Files:** `Makefile` (project root).

**Current state:** unknown. Investigate what `make check` does (per
the parent CLAUDE.md it runs lint + test + format check). Confirm
that `python -m unittest discover tests` is part of it; if not, add.

**Add:**
1. A `make check-invariants` target that runs ONLY the invariant
   tests (the eight from Phase 1 and Phase 3): a regex pattern over
   `test_*invariant*.py`, `test_no_*.py`, `test_*_traces_*.py`,
   `test_form_renderer_lines_*.py`, `test_fingerprint_uses_*.py`,
   `test_rule_input_tracking.py`, `test_*_atomic.py`,
   `test_file_reads_*.py`. Or simpler: list the test modules
   explicitly so adding a new invariant requires touching the
   Makefile (deliberate review).
2. The default `make check` target depends on `make check-invariants`.

**Acceptance:** running `make check` from a clean main passes;
running it after intentionally re-introducing one of the bug
patterns fails with the invariant test pointing at the offending
line.

**Commit:** `Add invariant tests to make check`

### WS-6B: Document the invariants in CLAUDE.md

**Files:** `tax_pipeline/CLAUDE.md` (root project instructions).

**Add a new section "Structural Invariants the Engine Guarantees"
listing all 11 invariants with one-line summary and the test that
enforces each. Future contributors must understand what they're
protecting; future agents must not accidentally weaken them.

**Acceptance:** the section lands. No test changes.

**Commit:** `Document structural invariants in CLAUDE.md`

---

## 9. Workstream-to-finding cross-reference

| Finding | Severity | Workstream | Phase |
|---|---|---|---|
| CR1 treaty literal in loader | Critical | WS-1 + WS-2A | 1+2 |
| CR2 final_target_refund_eur not in rule | Critical | WS-2 + WS-4B | 1+4 |
| CR3 DE25-17/19 waypoint misclassification | Critical | WS-3 + WS-2B | 1+2 |
| H1 repr fingerprint drift | High | WS-6 + WS-2D | 1+2 |
| H2 foreign-tax reconciliation in script | High | WS-2 + WS-5 + WS-4A | 1+4 |
| H3 KAP line 19 in renderer | High | WS-2 + WS-5 + WS-4C | 1+4 |
| H5 treaty25_17 silent fail-open | High | WS-4 + WS-2C | 1+2 |
| H8 DE25-00 undeclared input read | High | WS-3A | 3 |
| H9 atomic-write filename collision | High | WS-2E | 2 |
| M1 DE25-13 embedded derivations | Medium | WS-5A | 5 |
| M2 load_fund_classification merge | Medium | WS-5B | 5 |
| M3 parallel fingerprint chain | Medium | WS-5C | 5 |
| M4 module-level workspace resolution | Medium | WS-5D | 5 |
| L1 encoding="utf-8" missing | Low | WS-2F | 2 |
| L2 § 20 Abs. 6 ordering verify | Low | WS-5E | 5 |
| L3+ cosmetic items | Low | WS-5F | 5 |

Every Critical/High/Medium/Low item has a workstream. Every Tier 1
test has a paired bug fix.

---

## 10. Agent-handoff playbook

When dispatching agents to execute this plan:

1. **One workstream per agent.** Do NOT ask one agent to do multiple
   workstreams. Each WS is sized for ~30-60 minutes of focused work.

2. **TDD discipline mandatory.** Each Phase 1 agent writes a RED test
   and stops. Each Phase 2 agent picks up a paired test and turns it
   GREEN. The agent must:
   - Confirm the test is RED before changing source code.
   - Make the smallest change that turns it GREEN.
   - Run the FULL suite (`python -m unittest discover tests`) and
     confirm zero regressions.
   - Commit with the template message above.

3. **Worktree isolation when parallel.** Phase 1's five workstreams
   run in parallel — each gets a worktree. Phase 2's six workstreams
   run in parallel after Phase 1 lands — each gets a worktree.
   Phase 4's promotions have internal dependencies — run sequentially:
   WS-4A → WS-4B → WS-4C → WS-4D.

4. **Fingerprint stability is a first-class invariant.** Any change
   that alters a stage's fingerprint must be deliberate. If a stage's
   fingerprint changes, the agent must call it out in the commit
   message with the rationale (e.g., "WS-2B: stage fingerprint changes
   because the prior waypoint classification was wrong").

5. **Cross-jurisdiction promotions.** Phase 4 BRIDGE25 stage is the
   first cross-jurisdiction stage in the engine. The agent should add
   a `country_or_scope="BRIDGE-2025"` field convention and verify the
   `legal-execution-graph.json` renders the cross-jurisdiction edges
   correctly.

6. **Stop and ask if stuck.** An agent that can't reduce a workstream
   to ~50 lines of touched source should stop and report rather than
   sprawling. The orchestrator (human) will re-scope.

---

## 11. Risk and rollback

- **Rollback unit:** every commit on this plan is independently
  reversible via `git revert`. No squash commits. No force pushes.
- **Audit-packet churn:** Phase 4 (architectural promotions) WILL
  change stage_id sets and fingerprint values. A reviewer reading
  archived audit packets will see the schema change. Document this
  in the Phase 4 commit messages and bump a `legal-execution-graph`
  schema version field if one exists.
- **Test-suite duration:** the new invariant tests are mostly AST
  scans + grep, all O(n) over `tax_pipeline/`. Total added runtime
  should be <2 seconds. The cross-reference test (WS-2) requires a
  full demo-workspace pipeline run, which is ~5 seconds. Acceptable.
- **Agent-stall risk:** if an agent stalls (as has happened), the
  human picks up the workstream and finishes it sequentially. The
  TDD test as a checkpoint means partial work is still useful: the
  agent's RED test commit + the orchestrator's GREEN fix commit
  combine cleanly.

---

## 12. Definition of done

- All 11 invariants enforced by tests (Phase 1 + Phase 3).
- All 16 review findings (3C + 9H + 4M + 3L) addressed.
- `make check` from clean main passes; reintroducing any bug
  pattern from the punch list makes it fail.
- CLAUDE.md documents the invariants and references the enforcing
  tests by name.
- `legal-execution-graph.json` contains the headline German refund,
  the foreign-tax reconciliation, and the KAP form-line projection
  as first-class nodes (no orchestrator-script computation).
- Per-function audit re-run shows every rule still CORRECT.
- Architecture flow re-run shows Phase 1 / Phase 2 / Phase 3 all
  CLEAN.
