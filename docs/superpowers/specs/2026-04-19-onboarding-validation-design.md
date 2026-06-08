# Onboarding And Validation UX Design

## Goal

Make the public repo usable by a new person without requiring them to read the codebase to discover what is missing.

The target flow becomes:

1. scaffold a workspace
2. fill config and drop documents
3. validate workspace completeness
4. run the full pipeline

Today the engine is reusable, but the error model is still too implementation-shaped. Missing files often show up only when `run_year` is already doing real work, and the messages are not yet grouped into a user-facing checklist.

## Why This Change Exists

The repo already has:

- external-first workspaces
- a public demo
- explicit product limits

But a new user still has to infer too much:

- which command to run first
- which files are required now versus later
- whether a missing file is a raw document problem, a config problem, or a structured-input problem
- whether the workspace is valid enough to proceed

This phase adds a dedicated validation surface and makes the README/scaffold flow shorter and more explicit.

## User-Facing Command Model

The intended public flow should be:

```bash
python3 -m tax_pipeline.scaffold_year 2026
python3 -m tax_pipeline.validate_workspace 2026
python3 -m tax_pipeline.run_year 2026
```

The same should work with:

- `demo-2025`
- `--workspace /custom/path`

The validator should not run the full tax pipeline. It should inspect the workspace and report what is missing or inconsistent.

## New Command: `validate_workspace`

### Supported shapes

```bash
python3 -m tax_pipeline.validate_workspace demo-2025
python3 -m tax_pipeline.validate_workspace 2026
python3 -m tax_pipeline.validate_workspace 2026 --workspace /custom/path
```

### Purpose

The validator answers:

- is the workspace scaffold present?
- are the config files present and structurally readable?
- do the configured filing postures match the current product support matrix?
- are the required structured inputs present for the enabled jurisdictions?
- are there obvious fact-extraction review issues?

It should produce a concise grouped report rather than a stack trace.

### Validation groups

The command should report by section:

1. `Workspace`
   - selected workspace path
   - numeric year or built-in demo target
2. `Config`
   - presence of `people.csv`, `payments.csv`, `elections.csv`, `profile.json`, `manual_overrides.json`
   - CSV readability
3. `Posture`
   - enabled jurisdictions
   - supported versus unsupported filing posture combinations
4. `Structured Inputs`
   - required `normalized/reference-data/`
   - required `normalized/derived-facts/`
   - required `outputs/tax-positions/`
5. `Facts Review`
   - whether `normalized/facts/REVIEW.md` exists
   - whether deterministic extraction has produced review material
   - whether unsupported or needs-review states exist, if cheaply discoverable
6. `Ready`
   - explicit pass/fail summary

### Exit behavior

- `0`
  - workspace is valid enough to run
- non-zero
  - missing/invalid/unsupported conditions were found

The exact numeric split is less important than having a reliable shell success/failure contract.

## Error Message Design

The validator and runner should use the same phrasing style:

- say what is missing
- say where it should live
- say what it means
- say the next command the user should run

Bad:

- `Missing structured inputs for 2025: usa_income_summary.csv`

Better:

- `Missing structured input: normalized/derived-facts/usa/income-summary.csv`
- `This file is required for the 2025 U.S. capital and tax model.`
- `If you are still collecting raw documents, run fact extraction first and then populate the required derived-facts support files.`
- `For a grouped checklist, run: python3 -m tax_pipeline.validate_workspace 2025`

## Runner Integration

`run_year` should continue to fail loudly when inputs are missing, but it should point users to `validate_workspace`.

The runner should not become the main validation UI. The validator should own the grouped checklist.

## Scaffold Integration

After scaffold completes successfully, it should print short next steps:

1. where the workspace lives
2. which files to edit first
3. which command validates the workspace
4. which command runs the pipeline

Example:

```text
Workspace scaffolded at /Users/<user>/taxes/2026
Next steps:
1. Edit config/people.csv, config/payments.csv, and config/elections.csv
2. Drop raw documents into raw/
3. Run: python3 -m tax_pipeline.validate_workspace 2026
4. Run: python3 -m tax_pipeline.run_year 2026
```

## Scope Boundary

This phase is not a full interactive wizard.

It should not:

- ingest every config value through prompts
- attempt to solve unsupported filing postures automatically
- generate all derived-facts files for the user
- turn the tool into a GUI

It should:

- shorten the first-run learning curve
- make missing inputs obvious
- reduce “read the traceback to discover the product contract”

## README Changes

The README should promote a short three-command flow:

1. scaffold
2. validate
3. run

The validation step should be visible near the top, not buried in troubleshooting.

## Demo Role

The built-in demo should remain the reference implementation of a valid workspace.

That means the validator should pass cleanly on:

```bash
python3 -m tax_pipeline.validate_workspace demo-2025
```

## Likely Implementation Files

- `tax_pipeline/analysis_inputs.py`
- `tax_pipeline/run_year.py`
- `tax_pipeline/scaffold_year.py`
- new validator module, likely:
  - `tax_pipeline/validate_workspace.py`
- `README.md`
- `years/demo-2025/config/README.md`

## Acceptance Criteria

- new users have one dedicated validation command
- scaffold prints concrete next steps
- runner errors point to the validator
- the demo passes the validator cleanly
- the README shows the scaffold → validate → run flow prominently
