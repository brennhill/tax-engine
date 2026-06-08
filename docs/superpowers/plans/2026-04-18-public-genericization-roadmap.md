# Public Genericization Roadmap

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish turning this repo from a public-safe personal engine into a genuinely reusable public tax engine with synthetic-only fixtures, explicit product limits, and an external-first workspace model.

**Architecture:** Keep the core split between engine code, law specs, tests, and a synthetic demo workspace. Finish the synthetic migration first, then move user data out of the repo contract, then formalize supported filing postures/providers before widening into packaging and multi-year support.

**Tech Stack:** Python 3, `unittest`, Markdown law specs, CSV workspace config, synthetic demo year under `years/demo-2025/`

---

## Phase 1: Eliminate the Skipped-Test Boundary

**Outcome:** No tests depend on the old private 2025 fixture model, and the suite runs entirely on synthetic fixtures or fully inline test data.

**Why first:** This is the biggest remaining non-generic boundary. Until it is gone, part of the repository still assumes a historical private year structure even though it is now guarded safely.

**Primary files likely involved:**
- Modify: `tests/test_form_outputs.py`
- Modify: `tests/test_germany_2025_law.py`
- Modify: `tests/test_us_2025_law.py`
- Modify: `tests/test_law_spec.py`
- Modify: `tests/test_vanilla_checkpoint.py`
- Modify: `tests/support.py`
- Create or modify focused synthetic fixture helpers under `tests/` only if reuse is justified
- Potentially modify demo outputs in `years/demo-2025/outputs/...` if the new tests need tighter fixture guarantees

**Exit criteria:**
- `0` tests skipped for `Requires synthetic year fixture rewrite`
- the full suite passes using only synthetic or inline fixtures
- no test requires a materialized legacy `years/2025` private fixture

**Key risks:**
- recreating too much of the old private fixture shape instead of tightening tests to the public synthetic contract
- overfitting tests to current generated demo output instead of behavior

**Recommended implementation order:**
- [ ] Rewrite Germany output tests to use temporary synthetic year trees or the checked-in demo workspace intentionally
- [ ] Rewrite U.S. output tests to use synthetic year trees or the demo workspace intentionally
- [ ] Rewrite law-spec coverage tests so they target the demo outputs or focused synthetic traces instead of an implied private year
- [ ] Rewrite vanilla checkpoint tests to use synthetic fixtures or temporary generated outputs
- [ ] Remove the legacy skip gating once the replacements are green

---

## Phase 2: Make the Workspace Model External-First

**Outcome:** Real-user data no longer needs to live inside the repo. The public repo can run against a workspace path outside git while still shipping the synthetic demo year as an example.

**Why second:** This is the cleanest product boundary after tests. It prevents future users from mixing code and private tax data in one repo by default.

**Primary files likely involved:**
- Modify: `tax_pipeline/paths.py`
- Modify: `tax_pipeline/year_runtime.py`
- Modify: `tax_pipeline/run_year.py`
- Modify: `tax_pipeline/scaffold_year.py`
- Modify: `README.md`
- Modify: `years/README.md`
- Add docs for external workspace usage under `docs/` or `README.md`

**Desired contract:**
- public repo still ships `years/demo-2025/`
- runtime accepts either:
  - repo-local demo year, or
  - user-provided external workspace root
- scaffold can create a workspace outside the repo

**Exit criteria:**
- a new user can scaffold and run a workspace outside the repo tree
- the demo still runs unchanged from the repo
- README defaults to the external-workspace flow, not repo-internal real-year storage

---

## Phase 3: Formalize Product Scope and Support Matrix

**Outcome:** The public repo clearly states what it supports, what it intentionally does not support, and which filing postures/providers are available.

**Why third:** Right now the code is safer than the docs. Some unsupported paths fail loudly, but the product boundary is still implicit.

**Primary files likely involved:**
- Modify: `README.md`
- Modify: `tax_pipeline/scaffold_year.py`
- Modify relevant `law_spec` index files:
  - `tax_pipeline/law_spec/germany/2025/index.md`
  - `tax_pipeline/law_spec/usa/2025/index.md`
- Potentially add:
  - `docs/support-matrix.md`
  - `docs/provider-support.md`

**Areas that need explicit documentation:**
- Germany:
  - `single`
  - `married_joint`
  - `married_separate` currently blocked beyond ordinary-law layer
- USA:
  - current single-filer support
  - current MFS/NRA-spouse support
  - what is not supported yet
- provider expectations:
  - which documents are parser-supported
  - which facts must be entered manually
  - which sidecars are optional

**Exit criteria:**
- no hidden product assumptions
- unsupported paths are documented exactly where users will see them
- scaffolded config and docs agree with runtime behavior

---

## Phase 4: Improve New-User Onboarding and Validation

**Outcome:** A new user can scaffold a year, fill CSVs, validate completeness, and understand what is missing without reading the code.

**Why fourth:** The engine is reusable now for an informed developer, but not yet easy for a normal new user.

**Primary files likely involved:**
- Modify: `tax_pipeline/scaffold_year.py`
- Modify: `tax_pipeline/analysis_inputs.py`
- Modify: `tax_pipeline/run_year.py`
- Potentially add a dedicated validator command/module
- Modify: `README.md`
- Modify: `years/demo-2025/config/README.md`

**Good onboarding targets:**
- one command to scaffold
- one command to validate workspace completeness
- one command to run
- errors that name the exact missing file/field and what it means

**Exit criteria:**
- new-user flow is documented and short
- missing-config and missing-fact errors are actionable
- demo workspace doubles as a true reference implementation

---

## Phase 5: Package the Repo Like a Real Public Tool

**Outcome:** The repo behaves like a polished public project, not a cleaned-up internal archive.

**Primary files likely involved:**
- Add packaging metadata if desired (`pyproject.toml` or equivalent entrypoint strategy)
- Modify: `README.md`
- Add: `CONTRIBUTING.md`
- Add: release/versioning docs if needed

**Useful deliverables:**
- install/run instructions
- CLI entrypoint guidance
- contribution workflow
- public issue template / roadmap pointers

**Exit criteria:**
- a stranger can clone the repo and understand how to run the demo and create a workspace
- contribution expectations are explicit

---

## Phase 6: Decide Whether to Generalize Beyond Tax Year 2025

**Outcome:** Clear decision on whether this remains a polished 2025 engine with a generic shell, or becomes a multi-year platform.

**Why last:** This is expensive and should not block public usability.

**Primary files likely involved if pursued:**
- `tax_pipeline/germany_2025_law.py`
- `tax_pipeline/us_2025_law.py`
- `tax_pipeline/pipelines/y2025/...`
- year registry / dispatch surfaces
- future `law_spec/<country>/<year>/...`

**Decision branches:**
- If **no**: document the project as a 2025 engine with reusable public architecture
- If **yes**: introduce a year registry and stable per-year interfaces before adding 2026

**Exit criteria:**
- explicit roadmap choice
- no accidental implication that arbitrary years already work

---

## Recommended Execution Order

1. Phase 1: remove skipped-test legacy boundary
2. Phase 2: external-first workspace model
3. Phase 3: support matrix and product limits
4. Phase 4: onboarding and validation UX
5. Phase 5: packaging/public-project polish
6. Phase 6: optional multi-year generalization

## Immediate Recommendation

Start with **Phase 1**. It is the highest-signal unfinished boundary and the best indicator that the repo is fully detached from the private historical workspace model.
