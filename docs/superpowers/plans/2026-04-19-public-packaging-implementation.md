# Public Packaging Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:test-driven-development and superpowers:verification-before-completion while executing this plan. Add tests before changing user-facing CLI behavior, and verify the exact install/entrypoint commands you claim.

## Goal

Implement phase 5 of the public genericization roadmap by making the repo installable as a normal Python project, exposing stable CLI entrypoints, and adding minimal public contribution guidance.

## Architecture

Use a lightweight setuptools-backed `pyproject.toml`. Keep the current `tax_pipeline` package layout and existing module entrypoints. Add console scripts that simply point at the existing `main(...)` functions rather than creating a new CLI abstraction layer.

## Files Expected To Change

- new: `pyproject.toml`
- new: `CONTRIBUTING.md`
- update: `README.md`
- update tests if needed for packaging docs or entrypoint assumptions

## Phase Steps

### 1. Add tests for the public packaging contract

- Add focused tests for:
  - importability of the existing package remains unchanged
  - the documented CLI names map to real call targets if you add a small metadata-level assertion helper
- Keep these tests lightweight; do not turn them into an integration install harness unless necessary.

### 2. Add `pyproject.toml`

- Declare:
  - build system
  - project metadata
  - Python version requirement
  - console scripts:
    - `tax-pipeline-run`
    - `tax-pipeline-scaffold`
    - `tax-pipeline-validate`
    - `tax-pipeline-demo`

### 3. Update README install/run guidance

- Add:
  - editable-install instructions
  - console-script examples
  - fallback `python3 -m ...` examples
  - note about system tool expectations for parser-heavy flows

### 4. Add `CONTRIBUTING.md`

- Keep it short and practical:
  - editable install
  - run demo
  - run tests
  - synthetic-only fixtures and workspaces
  - update support docs when widening scope

### 5. Verify packaging behavior

- Run:
  - `python3 -m unittest discover -s tests -v`
  - `python3 -m pip install -e .`
  - at least one console-script smoke check, for example:
    - `tax-pipeline-validate demo-2025`
    - `tax-pipeline-run demo-2025`

## Risks

- overstating what package installation provides when some parser paths still rely on system tools
- accidentally creating a second CLI layer instead of reusing existing module entrypoints
- making the install docs too abstract for a first-time user

## Done Criteria

- the repo has standard Python packaging metadata
- console scripts work
- README documents install + CLI usage clearly
- contribution expectations are explicit
