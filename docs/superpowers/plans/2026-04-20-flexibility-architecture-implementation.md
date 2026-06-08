# Flexibility Architecture Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `2025` engine flexible enough to support more filing postures and more raw-document parsers cleanly, while adding a year registry seam for future `2026` work without claiming multi-year support yet.

**Architecture:** Extract filing posture into explicit jurisdiction-specific modules, turn the existing provider registry into a documented contributor seam with conformance tests, and introduce a year registry that still only registers `2025`. Keep the existing `2025` law modules as rule libraries and move household-shaping and output-surface decisions into posture modules.

**Tech Stack:** Python 3.14, `unittest`, Markdown docs, CSV/JSON workspace config, existing `tax_pipeline` runtime and provider registry.

---

## File Structure

### New files

- `tax_pipeline/postures/__init__.py`
  - Shared posture exports and registry helpers.
- `tax_pipeline/postures/base.py`
  - Common posture protocol / dataclasses / validation helpers.
- `tax_pipeline/postures/germany/__init__.py`
- `tax_pipeline/postures/germany/single.py`
- `tax_pipeline/postures/germany/married_joint.py`
- `tax_pipeline/postures/germany/married_separate.py`
  - Germany filing-posture modules.
- `tax_pipeline/postures/usa/__init__.py`
- `tax_pipeline/postures/usa/single.py`
- `tax_pipeline/postures/usa/mfs_nra_spouse.py`
- `tax_pipeline/postures/usa/married_joint.py`
  - U.S. filing-posture modules.
- `tax_pipeline/year_registry.py`
  - Explicit mapping from supported year tokens to year-specific modules and posture support.
- `docs/parser-contributor-guide.md`
  - Public contributor contract for deterministic parser additions.
- `tests/test_posture_registry.py`
  - Registry and posture validation tests.
- `tests/test_year_registry.py`
  - Year registry tests.

### Existing files to modify

- `tax_pipeline/analysis_inputs.py`
  - Resolve configured filing posture via the new registry helpers.
- `tax_pipeline/run_year.py`
  - Use the year registry and posture surface instead of hard-coded `2025` assumptions.
- `tax_pipeline/scaffold_year.py`
  - Surface supported postures from the registry and keep scaffold defaults aligned.
- `tax_pipeline/germany_2025_law.py`
  - Remain a lower-level rule library; remove posture orchestration that belongs in posture modules where practical.
- `tax_pipeline/us_2025_law.py`
  - Add low-level rule support needed by U.S. `married_joint` while avoiding posture-specific branching in top-level orchestration.
- `tax_pipeline/pipelines/y2025/germany_model.py`
- `tax_pipeline/pipelines/y2025/germany_elster_entry_sheet.py`
- `tax_pipeline/forms/germany.py`
  - Consume Germany posture modules instead of inferring behavior from flags inline.
- `tax_pipeline/pipelines/y2025/us_model.py`
- `tax_pipeline/pipelines/y2025/us_treaty_packet.py`
- `tax_pipeline/forms/usa.py`
  - Consume U.S. posture modules and support `married_joint`.
- `tax_pipeline/providers/registry.py`
  - Add any small public-contributor affordances needed by the parser conformance tests.
- `tax_pipeline/providers/__init__.py`
  - Keep provider initialization consistent with the documented contributor contract.
- `docs/support-matrix.md`
- `docs/provider-support.md`
- `README.md`
  - Publish the new posture and parser boundaries.

### Existing tests to extend

- `tests/test_germany_2025_law.py`
- `tests/test_us_2025_law.py`
- `tests/test_year_pipeline.py`
- `tests/test_provider_registry.py`
- `tests/test_fact_extraction.py`
- `tests/test_form_outputs.py`

## Chunk 1: Posture Registry Extraction

### Task 1: Add posture registry primitives without changing behavior

**Files:**
- Create: `tests/test_posture_registry.py`
- Create: `tax_pipeline/postures/__init__.py`
- Create: `tax_pipeline/postures/base.py`
- Modify: `tax_pipeline/analysis_inputs.py`

- [ ] **Step 1: Write the failing posture-registry tests**

Add tests that assert:
- Germany exposes `single`, `married_joint`, `married_separate`
- U.S. exposes `single`, `mfs_nra_spouse`, `married_joint`
- invalid posture strings fail loudly
- a posture definition can declare required household shape and supported output surfaces

Example:

```python
def test_known_postures_are_registered(self):
    germany = get_posture_definition("germany", "married_joint")
    self.assertEqual(germany.jurisdiction, "germany")
    self.assertEqual(germany.filing_posture, "married_joint")
```

- [ ] **Step 2: Run the posture-registry tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_posture_registry -v
```

Expected:
- FAIL with import or missing-function errors for the new posture modules

- [ ] **Step 3: Implement the minimal posture registry**

Create:
- `tax_pipeline/postures/base.py`
  - `PostureDefinition`
  - `OutputSurfaceSupport`
  - `validate_household_shape(...)`
- `tax_pipeline/postures/__init__.py`
  - registry map
  - `get_posture_definition(...)`

Keep this step intentionally small:
- only add enough structure to register posture metadata
- do not move existing runtime behavior yet

- [ ] **Step 4: Re-run the posture-registry tests**

Run:

```bash
python3 -m unittest tests.test_posture_registry -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_posture_registry.py tax_pipeline/postures/__init__.py tax_pipeline/postures/base.py tax_pipeline/analysis_inputs.py
git commit -m "Add filing posture registry primitives"
```

### Task 2: Register the currently supported postures behind explicit modules

**Files:**
- Create: `tax_pipeline/postures/germany/__init__.py`
- Create: `tax_pipeline/postures/germany/single.py`
- Create: `tax_pipeline/postures/germany/married_joint.py`
- Create: `tax_pipeline/postures/germany/married_separate.py`
- Create: `tax_pipeline/postures/usa/__init__.py`
- Create: `tax_pipeline/postures/usa/single.py`
- Create: `tax_pipeline/postures/usa/mfs_nra_spouse.py`
- Create: `tax_pipeline/postures/usa/married_joint.py`
- Modify: `tax_pipeline/postures/__init__.py`
- Test: `tests/test_posture_registry.py`

- [ ] **Step 1: Extend the failing tests to require posture modules**

Add assertions that:
- each supported posture resolves to a dedicated module
- Germany `married_separate` explicitly marks forms / entry sheet as unsupported
- U.S. `married_joint` exists in the registry but is flagged as not yet implemented at runtime

- [ ] **Step 2: Run the tests to confirm the new assertions fail**

Run:

```bash
python3 -m unittest tests.test_posture_registry -v
```

Expected:
- FAIL because the posture modules do not exist yet

- [ ] **Step 3: Add the module files and register their metadata**

Each posture module should export a single posture-definition helper. Keep them metadata-only in this step:
- no business logic migration yet
- just explicit declarations of:
  - filing posture
  - household shape
  - supported output surfaces
  - implementation status

- [ ] **Step 4: Re-run the posture-registry tests**

Run:

```bash
python3 -m unittest tests.test_posture_registry -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/postures tests/test_posture_registry.py
git commit -m "Register explicit Germany and U.S. posture modules"
```

## Chunk 2: Move the Current Runtime Behind Posture Modules

### Task 3: Route Germany runtime decisions through posture modules with no behavior change

**Files:**
- Modify: `tax_pipeline/pipelines/y2025/germany_model.py`
- Modify: `tax_pipeline/forms/germany.py`
- Modify: `tax_pipeline/pipelines/y2025/germany_elster_entry_sheet.py`
- Modify: `tax_pipeline/analysis_inputs.py`
- Test: `tests/test_form_outputs.py`
- Test: `tests/test_year_pipeline.py`

- [ ] **Step 1: Add failing regression tests for posture-driven Germany dispatch**

Cover:
- `single` still renders forms and entry sheet
- `married_joint` still renders forms and entry sheet
- `married_separate` still fails loudly at unsupported output surfaces, but now because the posture module says so

Use existing synthetic fixtures rather than introducing new year trees.

- [ ] **Step 2: Run the Germany dispatch tests and confirm failure**

Run:

```bash
python3 -m unittest \
  tests.test_form_outputs.TestFormHelpers.test_render_germany_forms_supports_single_person_profile \
  tests.test_year_pipeline.RunnerTest.test_germany_model_rejects_married_separate_filing_surface \
  -v
```

Expected:
- at least one FAIL because the production code still infers posture behavior inline

- [ ] **Step 3: Implement posture-driven Germany dispatch**

Change the runtime path so:
- posture metadata is resolved once
- unsupported surfaces use posture declarations instead of ad hoc checks
- current `single` and `married_joint` behavior stays unchanged

Avoid new math in this step. This is a routing refactor only.

- [ ] **Step 4: Re-run the targeted Germany dispatch tests**

Run:

```bash
python3 -m unittest \
  tests.test_form_outputs.TestFormHelpers.test_render_germany_forms_supports_single_person_profile \
  tests.test_year_pipeline.RunnerTest.test_germany_model_rejects_married_separate_filing_surface \
  -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/pipelines/y2025/germany_model.py tax_pipeline/forms/germany.py tax_pipeline/pipelines/y2025/germany_elster_entry_sheet.py tax_pipeline/analysis_inputs.py tests/test_form_outputs.py tests/test_year_pipeline.py
git commit -m "Route Germany outputs through filing posture modules"
```

### Task 4: Route current U.S. runtime decisions through posture modules with no behavior change

**Files:**
- Modify: `tax_pipeline/pipelines/y2025/us_model.py`
- Modify: `tax_pipeline/pipelines/y2025/us_treaty_packet.py`
- Modify: `tax_pipeline/forms/usa.py`
- Modify: `tax_pipeline/analysis_inputs.py`
- Test: `tests/test_year_pipeline.py`
- Test: `tests/test_form_outputs.py`

- [ ] **Step 1: Add failing regression tests for posture-driven U.S. dispatch**

Cover:
- `single` still works end-to-end
- `mfs_nra_spouse` still works end-to-end
- `married_joint` resolves in config but fails loudly as unimplemented until the next chunk

- [ ] **Step 2: Run the U.S. dispatch tests to confirm failure**

Run:

```bash
python3 -m unittest \
  tests.test_year_pipeline.RunnerTest.test_run_year_skips_usa_modules_and_renderers_when_usa_disabled \
  tests.test_form_outputs.TestUSAForms.test_render_usa_forms_writes_country_package \
  -v
```

Expected:
- one or more FAILs after tightening the assertions around posture-driven dispatch

- [ ] **Step 3: Implement posture-driven U.S. dispatch**

Refactor the U.S. runtime path so:
- the current `single` and `mfs_nra_spouse` logic is routed through posture modules
- `married_joint` is recognized but still blocked loudly as unimplemented

- [ ] **Step 4: Re-run the targeted U.S. dispatch tests**

Run:

```bash
python3 -m unittest \
  tests.test_year_pipeline.RunnerTest.test_run_year_skips_usa_modules_and_renderers_when_usa_disabled \
  tests.test_form_outputs.TestUSAForms.test_render_usa_forms_writes_country_package \
  -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/pipelines/y2025/us_model.py tax_pipeline/pipelines/y2025/us_treaty_packet.py tax_pipeline/forms/usa.py tax_pipeline/analysis_inputs.py tests/test_year_pipeline.py tests/test_form_outputs.py
git commit -m "Route U.S. outputs through filing posture modules"
```

## Chunk 3: Implement U.S. Married Joint

### Task 5: Support ordinary `married_joint` for two U.S. taxpayers

**Files:**
- Modify: `tax_pipeline/us_2025_law.py`
- Modify: `tax_pipeline/analysis_inputs.py`
- Modify: `tax_pipeline/postures/usa/married_joint.py`
- Modify: `tax_pipeline/pipelines/y2025/us_model.py`
- Modify: `tax_pipeline/forms/usa.py`
- Test: `tests/test_us_2025_law.py`
- Test: `tests/test_form_outputs.py`

- [ ] **Step 1: Write failing law tests for ordinary joint filing**

Cover:
- joint standard deduction
- MFJ rate schedule selection
- joint qualified-dividend/regular-tax path
- no NRA-spouse assumptions required when both people are U.S. taxpayers

Example:

```python
def test_joint_assessment_uses_mfj_schedule_without_nra_spouse_flags(self):
    inputs = make_joint_us_inputs(...)
    result = assess_us_return_2025(inputs)
    self.assertEqual(result.filing_status, "married_joint")
```

- [ ] **Step 2: Run the targeted law tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_us_2025_law.US2025LawTest.test_joint_assessment_uses_mfj_schedule_without_nra_spouse_flags -v
```

Expected:
- FAIL because the law/input/runtime path does not yet support `married_joint`

- [ ] **Step 3: Implement the minimal ordinary joint path**

Implement only the ordinary two-U.S.-taxpayer joint path:
- new input validation
- MFJ schedule/standard deduction selection
- posture-module orchestration
- summary/forms support for the new posture

Do not add NRA election behavior in this step.

- [ ] **Step 4: Re-run the targeted law and form tests**

Run:

```bash
python3 -m unittest \
  tests.test_us_2025_law.US2025LawTest.test_joint_assessment_uses_mfj_schedule_without_nra_spouse_flags \
  tests.test_form_outputs.TestUSAForms.test_render_usa_forms_writes_country_package \
  -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/us_2025_law.py tax_pipeline/analysis_inputs.py tax_pipeline/postures/usa/married_joint.py tax_pipeline/pipelines/y2025/us_model.py tax_pipeline/forms/usa.py tests/test_us_2025_law.py tests/test_form_outputs.py
git commit -m "Support ordinary U.S. married joint filing"
```

### Task 6: Support elected joint filing with an NRA spouse

**Files:**
- Modify: `tax_pipeline/us_2025_law.py`
- Modify: `tax_pipeline/analysis_inputs.py`
- Modify: `tax_pipeline/postures/usa/married_joint.py`
- Modify: `tax_pipeline/pipelines/y2025/us_treaty_packet.py`
- Modify: `tax_pipeline/forms/usa.py`
- Test: `tests/test_us_2025_law.py`
- Test: `tests/test_year_pipeline.py`

- [ ] **Step 1: Write failing tests for elected-joint-with-NRA-spouse**

Cover:
- explicit election flag required
- joint posture accepted when spouse is NRA only if election is present
- missing election fails loudly
- generated output surfaces label the posture clearly

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_us_2025_law.US2025LawTest.test_joint_assessment_rejects_nra_spouse_without_explicit_election \
  tests.test_year_pipeline.RunnerTest.test_run_year_uses_explicit_workspace_override \
  -v
```

Expected:
- FAIL because the election path is not implemented yet

- [ ] **Step 3: Implement elected joint return support**

Add:
- explicit config contract for the joint election
- posture validation
- law/input shaping required for the NRA-spouse joint path
- output labels / entry-sheet notes that make the election visible

Keep the implementation explicit and auditable:
- no hidden defaults
- no silent inference from spouse nationality alone

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
python3 -m unittest \
  tests.test_us_2025_law.US2025LawTest.test_joint_assessment_rejects_nra_spouse_without_explicit_election \
  tests.test_year_pipeline.RunnerTest.test_run_year_uses_explicit_workspace_override \
  -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/us_2025_law.py tax_pipeline/analysis_inputs.py tax_pipeline/postures/usa/married_joint.py tax_pipeline/pipelines/y2025/us_treaty_packet.py tax_pipeline/forms/usa.py tests/test_us_2025_law.py tests/test_year_pipeline.py
git commit -m "Support elected joint U.S. filing with NRA spouse"
```

## Chunk 4: Parser Contributor Surface

### Task 7: Publish a parser contributor contract with no behavior change

**Files:**
- Create: `docs/parser-contributor-guide.md`
- Modify: `docs/provider-support.md`
- Modify: `README.md`
- Test: `tests/test_public_packaging.py`

- [ ] **Step 1: Add a failing docs test for the parser contributor contract**

Assert that public docs mention:
- classifier rule
- handler module
- registry registration
- conformance tests
- unsupported-parser behavior

- [ ] **Step 2: Run the docs test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_public_packaging -v
```

Expected:
- FAIL because the contributor guide does not exist yet

- [ ] **Step 3: Write the contributor guide and link it publicly**

Document:
- exact parser workflow for PRs
- deterministic parser expectations
- no heuristic fallback rule
- minimal example based on an existing provider such as Schwab or Finanzamt

- [ ] **Step 4: Re-run the docs test**

Run:

```bash
python3 -m unittest tests.test_public_packaging -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add docs/parser-contributor-guide.md docs/provider-support.md README.md tests/test_public_packaging.py
git commit -m "Document parser contributor contract"
```

### Task 8: Add parser conformance tests for contributors

**Files:**
- Modify: `tests/test_provider_registry.py`
- Modify: `tests/test_fact_extraction.py`
- Modify: `tax_pipeline/providers/registry.py`
- Potentially modify: `tax_pipeline/providers/base.py`

- [ ] **Step 1: Write failing conformance tests**

Cover:
- every registered provider handler can be resolved from a descriptor
- unsupported provider/family/format combinations produce the documented unsupported result
- a minimal example handler satisfies the same contract as built-in ones

- [ ] **Step 2: Run the provider tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_provider_registry tests.test_fact_extraction -v
```

Expected:
- FAIL because the conformance helpers/assertions do not exist yet

- [ ] **Step 3: Implement minimal registry/test-harness support**

Add only enough production code to make the contract explicit and testable:
- helper assertions
- registry affordances if needed
- clearer unsupported-result expectations

Do not redesign parser loading beyond the current in-repo registry.

- [ ] **Step 4: Re-run the provider tests**

Run:

```bash
python3 -m unittest tests.test_provider_registry tests.test_fact_extraction -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_provider_registry.py tests/test_fact_extraction.py tax_pipeline/providers/registry.py tax_pipeline/providers/base.py
git commit -m "Add parser conformance tests"
```

## Chunk 5: Year Registry Seam

### Task 9: Introduce an explicit year registry that still only registers `2025`

**Files:**
- Create: `tests/test_year_registry.py`
- Create: `tax_pipeline/year_registry.py`
- Modify: `tax_pipeline/run_year.py`
- Modify: `tax_pipeline/scaffold_year.py`
- Modify: `tax_pipeline/analysis_inputs.py`
- Test: `tests/test_year_pipeline.py`

- [ ] **Step 1: Write failing tests for year-registry resolution**

Cover:
- `2025` resolves successfully
- `demo-2025` still resolves through the demo path
- non-2025 numeric years remain scaffold-only and fail loudly when they try to use unsupported year-engine features
- year registry exposes posture support by jurisdiction

- [ ] **Step 2: Run the targeted year-registry tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_year_registry -v
```

Expected:
- FAIL because the registry file does not exist yet

- [ ] **Step 3: Implement the minimal year registry**

Add:
- `tax_pipeline/year_registry.py`
- `get_year_definition(...)`
- explicit `2025` registration only

Then refactor runtime code to consult that registry instead of spreading `2025` assumptions inline.

- [ ] **Step 4: Re-run the targeted year-registry and runtime tests**

Run:

```bash
python3 -m unittest tests.test_year_registry tests.test_year_pipeline -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_year_registry.py tax_pipeline/year_registry.py tax_pipeline/run_year.py tax_pipeline/scaffold_year.py tax_pipeline/analysis_inputs.py tests/test_year_pipeline.py
git commit -m "Add explicit year registry for 2025 engine"
```

## Chunk 6: Public Contract Updates And Full Verification

### Task 10: Update support docs and lock the new flexibility boundary

**Files:**
- Modify: `docs/support-matrix.md`
- Modify: `README.md`
- Modify: `docs/provider-support.md`
- Modify: `tax_pipeline/law_spec/usa/2025/index.md`
- Test: `tests/test_public_packaging.py`

- [ ] **Step 1: Write the failing docs assertions**

Extend packaging/public-doc tests to require:
- U.S. `married_joint` is listed in the support matrix
- elected-joint-with-NRA-spouse is called out explicitly
- parser contributor guide is linked from the public docs
- `2025` remains the only implemented year in the year seam

- [ ] **Step 2: Run the docs tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_public_packaging -v
```

Expected:
- FAIL because the public docs have not been updated yet

- [ ] **Step 3: Update the public contract docs**

Make the docs consistent with the implemented code:
- support matrix
- provider support
- README quick-start / contribution links
- law-spec index references where posture support matters

- [ ] **Step 4: Run the full suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add docs/support-matrix.md README.md docs/provider-support.md tax_pipeline/law_spec/usa/2025/index.md tests/test_public_packaging.py
git commit -m "Publish flexibility support boundaries"
```

## Recommended Execution Order

1. Add posture registry primitives
2. Register explicit posture modules
3. Move current Germany and U.S. runtime dispatch behind posture modules
4. Implement ordinary U.S. `married_joint`
5. Implement elected joint return with NRA spouse
6. Publish parser contributor guide and conformance tests
7. Add explicit year registry for `2025`
8. Update support docs and verify the full suite

## Expected Outcome

After this plan:
- filing posture becomes an explicit extension seam
- U.S. `married_joint` is supported for both ordinary joint filers and elected-joint-with-NRA-spouse
- parser additions become a stable in-repo contributor workflow
- the codebase has a year registry seam without claiming support beyond `2025`
- future flexibility work can add postures, providers, and eventually `2026` without another repo-wide redesign
