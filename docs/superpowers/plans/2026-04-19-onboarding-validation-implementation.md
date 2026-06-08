# Onboarding And Validation UX Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:test-driven-development and superpowers:verification-before-completion while executing this plan. Add tests before changing behavior, and verify the exact commands you claim.

## Goal

Implement phase 4 of the public genericization roadmap by introducing a dedicated workspace validator, shortening the user onboarding flow to scaffold → validate → run, and improving missing-input messaging.

## Architecture

Keep the validator separate from the heavy runner. The new command should share path resolution and structured-input logic with the existing runtime, but it should not invoke tax-model scripts. It should inspect the selected workspace, summarize the current state in user-facing sections, and return a reliable exit status.

## Files Expected To Change

- `tax_pipeline/analysis_inputs.py`
- `tax_pipeline/run_year.py`
- `tax_pipeline/scaffold_year.py`
- `README.md`
- `years/demo-2025/config/README.md`
- `tests/test_year_pipeline.py`
- `tests/test_demo_workspace.py`
- new: `tax_pipeline/validate_workspace.py`

## Phase Steps

### 1. Add validation tests first

- Add unit tests for:
  - resolving the validator against `demo-2025`
  - resolving the validator against numeric external workspaces
  - grouped validator output for missing config files
  - grouped validator output for missing structured inputs
  - non-zero exit for invalid workspaces
  - zero exit for the built-in demo workspace
- Add runner/scaffold messaging tests for:
  - scaffold next-step output
  - `run_year` missing-input error text pointing to `validate_workspace`

### 2. Implement `tax_pipeline.validate_workspace`

- Add a CLI module with:
  - `main(argv)`
  - workspace/year resolution shared with the current runtime
- Implement grouped checks:
  - workspace selection summary
  - config-file presence and readability
  - enabled jurisdictions / filing postures
  - structured-input completeness
  - facts-review presence
  - ready / not-ready summary
- Return:
  - `0` for valid-enough workspaces
  - non-zero for invalid workspaces

### 3. Improve reusable validation helpers

- Add small helpers in `analysis_inputs.py` or a nearby module for:
  - required config-path enumeration
  - clearer structured-input explanations
  - shared “supported posture” summary if that reduces duplication cleanly
- Do not hide the current explicit runtime boundaries behind generic abstractions.

### 4. Integrate validator messaging into scaffold and run

- After scaffold succeeds, print concise next steps:
  - edit config
  - add raw documents
  - run validator
  - run pipeline
- When `run_year` fails on missing structured inputs, point the user to:
  - `python3 -m tax_pipeline.validate_workspace <year>`

### 5. Update public docs

- Update `README.md` so the quick-start flow becomes:
  - scaffold
  - validate
  - run
- Update `years/demo-2025/config/README.md` to reinforce the validator command.

### 6. Verify end-to-end

- Run targeted tests for validator behavior
- Run the full suite
- Run:
  - `python3 -m tax_pipeline.validate_workspace demo-2025`
  - `python3 -m tax_pipeline.run_year demo-2025`
- Optionally smoke-test a scaffolded temporary external workspace and validate its initial missing-data state.

## Risks

- duplicating runtime logic instead of reusing existing path and structured-input helpers
- turning the validator into a second runner
- overengineering the output instead of keeping it checklist-like

## Done Criteria

- new users have a dedicated `validate_workspace` command
- scaffold prints clear next steps
- runner points users to the validator when inputs are missing
- demo validates cleanly
- the README clearly promotes scaffold → validate → run
