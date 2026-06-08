# External Workspace Model Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make real user workspaces external-first by default while preserving the repo-local synthetic demo workspace.

**Architecture:** Split runtime path selection into two concepts: `project_root` for code/demo and `workspace_root` for the selected year workspace. Add a small CLI/runtime resolver that chooses between the built-in demo, the default external path `~/taxes/<year>/`, and an explicit `--workspace` override, then thread that resolved workspace root through `YearPaths`, `run_year`, and `scaffold_year`.

**Tech Stack:** Python 3, `unittest`, argparse-style CLI parsing, Markdown docs, CSV workspace config

---

## Chunk 1: Path Resolution Contract

### Task 1: Add failing tests for external-first year resolution

**Files:**
- Modify: `tests/test_year_pipeline.py`
- Modify: `tests/test_demo_workspace.py`

- [ ] **Step 1: Write failing tests for workspace path selection**

Add targeted tests covering:
- `run_year demo-2025` resolves to repo-local `years/demo-2025`
- numeric year with no override resolves to `Path.home() / "taxes" / "<year>"`
- explicit `--workspace` override wins over the default
- external default path is not silently remapped into the repo

Suggested test names:

```python
def test_active_year_paths_uses_repo_local_demo_workspace(): ...
def test_active_year_paths_defaults_numeric_year_to_external_home_workspace(): ...
def test_active_year_paths_prefers_explicit_workspace_override(): ...
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
python3 -m unittest tests.test_year_pipeline.YearRuntimeTest -v
```

Expected:
- FAIL because current runtime only supports repo-local numeric years and integer parsing

- [ ] **Step 3: Add path-resolution support in production code**

**Files:**
- Modify: `tax_pipeline/paths.py`
- Modify: `tax_pipeline/year_runtime.py`

Implementation direction:
- add a `workspace_root` field to `YearPaths`
- keep `project_root` as the repo/code root
- add a constructor such as:

```python
@classmethod
def for_workspace(
    cls,
    project_root: Path,
    workspace_root: Path,
    year_label: str,
    *,
    numeric_year: int | None,
) -> "YearPaths":
    ...
```

- preserve current per-directory properties but derive them from `workspace_root`
- keep a small helper for repo-local demo resolution, for example:

```python
def resolve_demo_workspace(project_root: Path, demo_name: str) -> Path: ...
```

- update `active_year_paths(...)` so it can accept a resolved workspace target instead of always constructing `project_root / "years" / str(year)`

- [ ] **Step 4: Re-run the targeted tests to verify GREEN**

Run:

```bash
python3 -m unittest tests.test_year_pipeline.YearRuntimeTest -v
```

Expected:
- PASS for the new path-resolution cases

- [ ] **Step 5: Commit the path-contract change**

```bash
git add tests/test_year_pipeline.py tests/test_demo_workspace.py tax_pipeline/paths.py tax_pipeline/year_runtime.py
git commit -m "Add external-first workspace path resolution"
```

### Task 2: Guard the demo contract explicitly

**Files:**
- Modify: `tests/test_demo_workspace.py`
- Modify: `tax_pipeline/year_runtime.py`

- [ ] **Step 1: Write a failing test that demo workspaces stay repo-local**

Add a test that asserts `demo-2025` never resolves to `~/taxes/demo-2025`.

- [ ] **Step 2: Run the targeted demo-runtime test to verify RED**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceRuntimeTest -v
```

Expected:
- FAIL if the runtime still treats demo names like ordinary external years

- [ ] **Step 3: Add explicit demo-name handling**

Implementation direction:
- add a parser/helper that distinguishes:
  - `demo-2025`
  - numeric years like `2025`
- reject unknown non-numeric tokens loudly

- [ ] **Step 4: Re-run the targeted demo-runtime test to verify GREEN**

Run:

```bash
python3 -m unittest tests.test_demo_workspace.DemoWorkspaceRuntimeTest -v
```

Expected:
- PASS

- [ ] **Step 5: Commit the demo-path guard**

```bash
git add tests/test_demo_workspace.py tax_pipeline/year_runtime.py
git commit -m "Preserve repo-local demo workspace resolution"
```

## Chunk 2: CLI and Scaffold Flow

### Task 3: Add failing tests for `run_year` CLI workspace selection

**Files:**
- Modify: `tests/test_year_pipeline.py`
- Modify: `tax_pipeline/run_year.py`

- [ ] **Step 1: Write failing CLI-level tests**

Add tests covering:
- `run_year demo-2025` uses repo-local demo workspace
- `run_year 2025` defaults to `~/taxes/2025`
- `run_year 2025 --workspace /tmp/custom` uses the explicit override
- headline/output logic still uses the resolved workspace analysis directory

Suggested test names:

```python
def test_run_year_defaults_numeric_year_to_external_workspace(): ...
def test_run_year_accepts_explicit_workspace_override(): ...
def test_run_year_accepts_demo_workspace_token(): ...
```

- [ ] **Step 2: Run the targeted runner tests to verify RED**

Run:

```bash
python3 -m unittest tests.test_year_pipeline.RunnerTest -v
```

Expected:
- FAIL because `run_year.main()` currently parses only integers and does not accept `--workspace`

- [ ] **Step 3: Implement minimal CLI parsing and runtime plumbing**

Implementation direction:
- replace the ad hoc positional parsing in `tax_pipeline/run_year.py`
- support:

```bash
python3 -m tax_pipeline.run_year demo-2025
python3 -m tax_pipeline.run_year 2025
python3 -m tax_pipeline.run_year 2025 --workspace /custom/path
```

- add helpers like:

```python
def parse_workspace_target(argv: list[str]) -> WorkspaceSelection: ...
def default_external_workspace_root(year: int) -> Path: ...
```

- ensure downstream env vars use the resolved workspace paths, not repo-local assumptions

- [ ] **Step 4: Re-run the targeted runner tests to verify GREEN**

Run:

```bash
python3 -m unittest tests.test_year_pipeline.RunnerTest -v
```

Expected:
- PASS for the new workspace-selection cases

- [ ] **Step 5: Commit the run-year CLI work**

```bash
git add tests/test_year_pipeline.py tax_pipeline/run_year.py tax_pipeline/year_runtime.py tax_pipeline/paths.py
git commit -m "Add external-first workspace selection to run_year"
```

### Task 4: Add failing tests for scaffold external-default behavior

**Files:**
- Modify: `tests/test_year_pipeline.py`
- Modify: `tax_pipeline/scaffold_year.py`

- [ ] **Step 1: Write failing scaffold tests**

Add tests covering:
- `scaffold_year 2025` defaults to `~/taxes/2025`
- the command prompts before creating a missing external workspace
- an explicit `--workspace` path is honored directly
- existing workspaces are reused without prompting

Suggested test names:

```python
def test_scaffold_year_defaults_to_external_home_workspace(): ...
def test_scaffold_year_prompts_before_creating_missing_external_workspace(): ...
def test_scaffold_year_uses_explicit_workspace_override(): ...
```

- [ ] **Step 2: Run the targeted scaffold tests to verify RED**

Run:

```bash
python3 -m unittest tests.test_year_pipeline.ScaffoldYearTest -v
```

Expected:
- FAIL because scaffold currently assumes a repo-local `YearPaths` and has no external-workspace prompt contract

- [ ] **Step 3: Implement scaffold target resolution and prompting**

Implementation direction:
- extend `tax_pipeline/scaffold_year.py` with CLI parsing similar to `run_year`
- add a creation prompt for missing external workspaces only
- keep the checked-in demo out of scaffold responsibilities
- ensure `ensure_year_scaffold(...)` operates on the resolved `workspace_root`

- [ ] **Step 4: Re-run the targeted scaffold tests to verify GREEN**

Run:

```bash
python3 -m unittest tests.test_year_pipeline.ScaffoldYearTest -v
```

Expected:
- PASS for the external-default and prompting cases

- [ ] **Step 5: Commit the scaffold externalization**

```bash
git add tests/test_year_pipeline.py tax_pipeline/scaffold_year.py tax_pipeline/year_runtime.py tax_pipeline/paths.py
git commit -m "Default scaffolded workspaces to external storage"
```

## Chunk 3: Docs and Final Verification

### Task 5: Update public docs to lead with the external workspace flow

**Files:**
- Modify: `README.md`
- Modify: `years/README.md`
- Modify: `years/demo-2025/config/README.md` if needed

- [ ] **Step 1: Write a failing doc-oriented regression test if a suitable one exists**

If the repo already has README or scaffold-contract assertions, extend them first. Otherwise skip directly to implementation; do not invent a brittle documentation parser test.

- [ ] **Step 2: Update docs**

README should lead with:

```bash
python3 -m tax_pipeline.run_year demo-2025
python3 -m tax_pipeline.scaffold_year 2025
python3 -m tax_pipeline.run_year 2025
```

and explain that numeric years default to:

```text
~/taxes/<year>/
```

Also document:
- `--workspace /custom/path`
- repo-local demo versus external real workspaces

- [ ] **Step 3: Run focused verification for doc-adjacent behavior**

Run:

```bash
python3 -m unittest tests.test_demo_workspace -v
python3 -m unittest tests.test_year_pipeline -v
```

Expected:
- PASS

- [ ] **Step 4: Commit the doc update**

```bash
git add README.md years/README.md years/demo-2025/config/README.md tests/test_demo_workspace.py tests/test_year_pipeline.py
git commit -m "Document external-first workspace flow"
```

### Task 6: Full regression and cleanup

**Files:**
- Review only: the files modified in Tasks 1-5

- [ ] **Step 1: Run the full suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected:
- PASS

- [ ] **Step 2: Smoke-test the user flows manually**

Run:

```bash
python3 -m tax_pipeline.run_year demo-2025
python3 -m tax_pipeline.scaffold_year 2025 --workspace /tmp/tax-workspace-2025
python3 -m tax_pipeline.run_year 2025 --workspace /tmp/tax-workspace-2025
```

Expected:
- demo runs against repo-local `years/demo-2025`
- scaffold creates the external test workspace
- run-year reads and writes through the external workspace

- [ ] **Step 3: Review the final diff for accidental repo-local assumptions**

Check specifically for:
- `project_root / "years" / str(year)` hardcoded in runtime selection logic
- silent fallback from numeric years back into repo-local storage
- prompt behavior bypass for missing external workspaces

- [ ] **Step 4: Commit the final polish**

```bash
git add tax_pipeline/paths.py tax_pipeline/year_runtime.py tax_pipeline/run_year.py tax_pipeline/scaffold_year.py README.md years/README.md years/demo-2025/config/README.md tests/test_demo_workspace.py tests/test_year_pipeline.py
git commit -m "Complete external-first workspace model"
```
