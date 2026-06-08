# Synthetic Single-Person Cross-Border Demo Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a runnable, fully synthetic `years/demo-2025/` workspace that demonstrates a single-person Germany-plus-U.S. cross-border filing with salary, stock compensation in payroll, small payments, U.S.-broker dividends, and a few stock sales.

**Architecture:** Keep the core tax engine generic and add a public-safe synthetic demo as data plus thin runtime/docs/test support. The demo should not require fake raw documents; instead it should use synthetic config, normalized inputs, tax-position inputs, and committed output surfaces. Because the current runtime only supports numeric years, add a small explicit demo execution path instead of pretending `demo-2025` is already a first-class year token.

**Tech Stack:** Python, `unittest`, CSV/JSON year workspace files, existing Germany/U.S. pipeline modules, markdown output surfaces.

---

## File Structure

- Create: `tax_pipeline/demo_workspace.py`
  - Provide a small helper/CLI to materialize or verify the checked-in synthetic demo through the existing numeric-year engine contract.
- Modify: `README.md`
  - Point new users at the concrete synthetic demo and explain how to run/inspect it.
- Modify: `years/demo-2025/README.md`
  - Document the synthetic scenario, included inputs, excluded complexity, and main outputs.
- Create or replace: `years/demo-2025/config/people.csv`
- Create or replace: `years/demo-2025/config/payments.csv`
- Create or replace: `years/demo-2025/config/elections.csv`
- Modify: `years/demo-2025/config/profile.json`
- Modify: `years/demo-2025/config/manual_overrides.json`
- Create synthetic normalized inputs under:
  - `years/demo-2025/normalized/facts/`
  - `years/demo-2025/normalized/reference-data/`
  - `years/demo-2025/normalized/derived-facts/common/`
  - `years/demo-2025/normalized/derived-facts/germany/`
  - `years/demo-2025/normalized/derived-facts/usa/`
- Create synthetic tax-position inputs under:
  - `years/demo-2025/outputs/tax-positions/`
- Create committed synthetic outputs under:
  - `years/demo-2025/outputs/analysis-steps/`
  - `years/demo-2025/outputs/forms/germany/`
  - `years/demo-2025/outputs/forms/usa/`
  - `years/demo-2025/outputs/legal-audit/germany/`
  - `years/demo-2025/outputs/legal-audit/usa/`
- Create: `tests/test_demo_workspace.py`
  - Add public-safe demo workspace tests.
- Modify: `tests/test_year_pipeline.py`
  - Add demo execution/runtime tests if needed.

## Chunk 1: Demo Runtime Contract

### Task 1: Define how the synthetic demo is executed

**Files:**
- Create: `tests/test_demo_workspace.py`
- Create: `tax_pipeline/demo_workspace.py`
- Modify: `README.md`

- [ ] **Step 1: Write the failing tests for demo execution**

Add tests that prove:
- the repo exposes a demo execution helper instead of relying on `run_year demo-2025`
- the helper can materialize the checked-in `years/demo-2025/` into a numeric temporary year workspace
- the helper returns or prints the temporary workspace location clearly

Example skeleton:

```python
def test_materialize_demo_workspace_copies_demo_into_numeric_year_tree(self):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        materialized = materialize_demo_workspace(root, demo_name="demo-2025", year=2025)
        assert materialized.year == 2025
        assert materialized.profile_path.exists()
        assert (materialized.analysis_root / "germany-summary.md").exists()
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceRuntimeTest -v
```

Expected:
- failure because `tax_pipeline.demo_workspace` and the helper do not exist yet

- [ ] **Step 3: Implement the minimal demo runtime helper**

Implement a focused helper in `tax_pipeline/demo_workspace.py` that:
- resolves the checked-in `years/demo-2025/` tree
- copies it into a temporary or target numeric year workspace using `YearPaths.for_year(...)`
- exposes a small CLI entry point such as:

```bash
python3 -m tax_pipeline.demo_workspace
```

Behavior:
- do not mutate `years/demo-2025/`
- do not depend on private data
- make it obvious that this is a demo materialization path, not a real-user scaffold

- [ ] **Step 4: Re-run the targeted demo runtime tests**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceRuntimeTest -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_demo_workspace.py tax_pipeline/demo_workspace.py README.md
git commit -m "Add synthetic demo workspace runtime helper"
```

## Chunk 2: Synthetic Demo Config Surface

### Task 2: Add the checked-in single-person config

**Files:**
- Create: `years/demo-2025/config/people.csv`
- Create: `years/demo-2025/config/payments.csv`
- Create: `years/demo-2025/config/elections.csv`
- Modify: `years/demo-2025/config/profile.json`
- Modify: `years/demo-2025/config/manual_overrides.json`
- Test: `tests/test_demo_workspace.py`

- [ ] **Step 1: Write failing tests for demo config shape**

Add tests that assert:
- exactly one person row exists
- Germany filing posture is `single`
- U.S. filing posture is `single`
- the synthetic person has the expected scenario markers
- one German prepayment and one U.S. estimated payment exist

Example:

```python
def test_demo_config_is_single_person_cross_border(self):
    profile = json.loads((DEMO_ROOT / "config/profile.json").read_text())
    people = list(csv.DictReader((DEMO_ROOT / "config/people.csv").open()))
    assert len(people) == 1
    assert profile["jurisdictions"]["germany"]["filing_posture"] == "single"
    assert profile["jurisdictions"]["usa"]["filing_posture"] == "single"
```

- [ ] **Step 2: Run the config tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceConfigTest -v
```

Expected:
- failure because the demo config files are absent or incomplete

- [ ] **Step 3: Write the synthetic config files**

Populate:
- `people.csv` with one synthetic person
- `payments.csv` with one Germany prepayment and one U.S. estimated payment
- `elections.csv` with Germany `single`, U.S. `single`, and treaty-resourcing enabled
- `profile.json` as the synced engine-facing config
- `manual_overrides.json` with explicit zero/default manual positions needed by the current engine

Scenario requirements:
- `100000` salary
- `20000` stock comp reflected through wage facts later, not through a separate manual override
- no spouse rows

- [ ] **Step 4: Re-run the config tests**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceConfigTest -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add years/demo-2025/config tests/test_demo_workspace.py
git commit -m "Add synthetic single-person demo config"
```

## Chunk 3: Synthetic Normalized Inputs

### Task 3: Add the minimum synthetic facts, reference data, derived facts, and tax-position inputs

**Files:**
- Create under `years/demo-2025/normalized/facts/`
- Create under `years/demo-2025/normalized/reference-data/`
- Create under `years/demo-2025/normalized/derived-facts/common/`
- Create under `years/demo-2025/normalized/derived-facts/germany/`
- Create under `years/demo-2025/normalized/derived-facts/usa/`
- Create under `years/demo-2025/outputs/tax-positions/`
- Test: `tests/test_demo_workspace.py`

- [ ] **Step 1: Write failing tests for required synthetic inputs**

Use `structured_input_files(...)` and the existing loader entry points to assert the demo contains everything needed for:
- Germany model inputs
- U.S. capital inputs
- U.S. assessment inputs

Example:

```python
def test_demo_workspace_has_all_required_structured_inputs(self):
    paths = materialize_demo_workspace(...)
    missing = missing_structured_inputs(paths)
    assert missing == []
```

- [ ] **Step 2: Run the structured-input tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceInputsTest -v
```

Expected:
- failure with missing synthetic input files

- [ ] **Step 3: Create synthetic normalized input files**

Populate the minimum files required by `tax_pipeline.analysis_inputs.structured_input_files(...)`, including:
- reference rates and tax constants
- synthetic German wage facts JSON/CSV data
- U.S. carryovers and payments
- U.S. income summary with dividends
- Germany capital support
- U.S. foreign wage support
- U.S. FTC support
- de/us model assumptions

Design rules:
- keep the stock-sale set small and readable
- keep the dividend/stock-sale numbers large enough to exercise FTC and treaty-resourcing
- keep values synthetic and documented

- [ ] **Step 4: Re-run the structured-input tests**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceInputsTest -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add years/demo-2025/normalized years/demo-2025/outputs/tax-positions tests/test_demo_workspace.py
git commit -m "Add synthetic demo normalized inputs"
```

## Chunk 4: Committed Demo Outputs

### Task 4: Generate and check in the synthetic output surfaces

**Files:**
- Create or update under:
  - `years/demo-2025/outputs/analysis-steps/`
  - `years/demo-2025/outputs/forms/germany/`
  - `years/demo-2025/outputs/forms/usa/`
  - `years/demo-2025/outputs/legal-audit/germany/`
  - `years/demo-2025/outputs/legal-audit/usa/`
- Modify: `years/demo-2025/README.md`
- Test: `tests/test_demo_workspace.py`

- [ ] **Step 1: Write failing tests for demo output surfaces**

Add tests that assert the committed demo outputs:
- exist
- show single-person wording
- include Germany and U.S. summaries
- include forms packages
- include U.S. treaty/FTC-facing surfaces
- do not reference a spouse or `person_2`

Example:

```python
def test_demo_outputs_are_single_person_and_cross_border(self):
    germany_summary = (DEMO_ROOT / "outputs/analysis-steps/germany-summary.md").read_text()
    usa_summary = (DEMO_ROOT / "outputs/analysis-steps/us-tax-estimate.md").read_text()
    assert "person_2" not in germany_summary
    assert "vanilla checkpoint" in germany_summary
    assert "refund" in usa_summary or "balance due" in usa_summary
```

- [ ] **Step 2: Run the output-surface tests to verify they fail**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceOutputsTest -v
```

Expected:
- failure because committed demo outputs are still placeholder-only

- [ ] **Step 3: Materialize/generate the demo outputs**

Use the demo runtime helper plus the existing pipeline/forms/audit renderers to generate synthetic outputs, then copy the public-safe results back into `years/demo-2025/`.

Keep only committed, inspectable outputs that are useful for the public repo:
- analysis summaries
- forms packages
- legal-audit packages if supported by the synthetic data

- [ ] **Step 4: Update the demo README**

Document:
- the synthetic scenario
- included income types
- included payments
- why treaty-resourcing/FTC are present
- the main files a user should inspect first

- [ ] **Step 5: Re-run the output tests**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceOutputsTest -v
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
git add years/demo-2025/README.md years/demo-2025/outputs tests/test_demo_workspace.py
git commit -m "Add synthetic demo output surfaces"
```

## Chunk 5: Public Docs and End-to-End Verification

### Task 5: Wire the demo into public onboarding and verify the full path

**Files:**
- Modify: `README.md`
- Modify: `years/demo-2025/README.md`
- Modify: `tests/test_year_pipeline.py` if a demo smoke path needs explicit coverage
- Test: `tests/test_demo_workspace.py`

- [ ] **Step 1: Add failing docs or smoke tests if needed**

If no test yet covers the end-to-end demo helper plus required public docs, add one small failing test.

Example:

```python
def test_demo_readme_points_to_materialization_flow(self):
    readme = Path("README.md").read_text()
    assert "demo-2025" in readme
    assert "python3 -m tax_pipeline.demo_workspace" in readme
```

- [ ] **Step 2: Run the last targeted tests**

Run:

```bash
python3 -m unittest tests.test_demo_workspace -v
```

Expected:
- PASS after doc/runtime updates

- [ ] **Step 3: Update top-level public docs**

Make the main README clearly explain:
- this repo ships a synthetic runnable example
- how to materialize or inspect it
- how real users should treat it as a pattern, not a filing template

- [ ] **Step 4: Run the full verification suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected:
- PASS
- existing synthetic/public-safe skips remain intentional

- [ ] **Step 5: Do a manual smoke check of the demo helper**

Run:

```bash
python3 -m tax_pipeline.demo_workspace
```

Expected:
- helper completes successfully
- prints or returns the materialized numeric workspace path
- no private-data dependency appears

- [ ] **Step 6: Commit**

```bash
git add README.md tests/test_demo_workspace.py tests/test_year_pipeline.py tax_pipeline/demo_workspace.py years/demo-2025
git commit -m "Ship synthetic single-person cross-border demo"
```
