# Public Packaging And Project-Polish Design

## Goal

Make the repository feel like a real public tool rather than a cleaned-up internal archive.

This phase is about:

- installability
- clear CLI entrypoints
- public contribution guidance
- an explicit versioning / release posture

It is not about broadening tax support. The product boundary from the support matrix remains unchanged.

## Why This Change Exists

The repo now has:

- a public-safe demo workspace
- external-first real workspaces
- explicit support and provider boundaries
- onboarding and validation commands

But it still lacks the signals of a normal public tool:

- no packaging metadata
- no install instructions
- no stable CLI command names outside `python3 -m ...`
- no contribution guide

Someone can use it today, but they still have to infer too much from the repository structure.

## Packaging Model

Use a lightweight `pyproject.toml` with setuptools-backed packaging.

Reasons:

- the current codebase is already a normal Python package with `tax_pipeline/__init__.py`
- no complex build backend is needed
- console scripts can point directly to the existing module entrypoints

This should stay intentionally small. The goal is public usability, not packaging sophistication.

## Proposed Project Metadata

- project name:
  - keep the repo identity visible, but prefer a normalized Python package name that is not tied to git history mechanics
- requires Python:
  - declare the currently supported runtime explicitly
- dependencies:
  - keep empty if the project is stdlib-only at the Python level
- optional note:
  - document required system tools separately rather than pretending packaging alone installs everything

## CLI Entry Points

Expose stable console scripts for the existing public workflow.

Recommended commands:

- `tax-pipeline-run`
  - equivalent to `python3 -m tax_pipeline.run_year`
- `tax-pipeline-scaffold`
  - equivalent to `python3 -m tax_pipeline.scaffold_year`
- `tax-pipeline-validate`
  - equivalent to `python3 -m tax_pipeline.validate_workspace`
- `tax-pipeline-demo`
  - equivalent to `python3 -m tax_pipeline.demo_workspace`

These names are explicit, searchable, and map directly to the current module boundaries.

## Install Story

The README should support two install modes:

### Development / local clone

```bash
python3 -m pip install -e .
```

Then run:

```bash
tax-pipeline-run demo-2025
```

### Direct module invocation

Keep the existing `python3 -m ...` examples too, because they are useful for contributors and remain the lowest-assumption fallback.

## System Tool Expectations

The packaging docs should clearly separate:

- Python package installation
- system-level helper tools

This repo currently relies on external command-line utilities for some deterministic extraction flows. Packaging should not imply that `pip install` alone guarantees every parser path works.

The docs should say something like:

- Python installation gives you the CLI
- certain parser paths may additionally require local system tools such as `pdftotext`

The exact tool list should reflect what the repo actually uses today, not a theoretical future stack.

## Contribution Guide

Add a short `CONTRIBUTING.md` covering:

- clone and editable install
- run the demo
- run the full test suite
- use the synthetic demo, not real taxpayer data
- keep new tests synthetic
- update support docs when widening product scope

This does not need to become a large governance document.

## Versioning / Release Posture

The project should state a simple public versioning posture.

Recommended approach:

- add a project version in `pyproject.toml`
- document that current public releases describe a `2025` engine with a reusable shell
- do not imply arbitrary tax-year support

If a dedicated versioning doc is helpful, keep it short and practical.

## README Changes

The README should gain:

- install section
- CLI entrypoint section
- contribution pointer
- explicit note that `python3 -m ...` remains supported

The quick-start flow should continue to emphasize:

1. run the built-in demo
2. scaffold a real workspace
3. validate
4. run

## Scope Boundary

This phase should not:

- publish to PyPI
- add dependency-management complexity without need
- redesign the package layout
- expand the actual tax-support matrix

It should:

- make local public use and contribution straightforward
- make the CLI discoverable
- make the repo look intentional

## Expected Files

- new: `pyproject.toml`
- new: `CONTRIBUTING.md`
- maybe new: short versioning / release note doc if needed
- update: `README.md`

## Acceptance Criteria

- `pip install -e .` works for the repo
- console-script entrypoints resolve to the existing commands
- README documents both CLI and module invocation
- contribution workflow is explicit
- the public package docs do not overstate what the repo supports
