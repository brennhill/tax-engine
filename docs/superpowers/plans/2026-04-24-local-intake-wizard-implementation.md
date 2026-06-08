# Local Intake Wizard Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local web intake wizard that lets end users create/open a private workspace, enter household and payment basics, upload documents, see classification/readiness, and run the existing pipeline without managing raw folders or CSV files directly.

**Architecture:** Add a small local HTTP app on top of the current workspace model rather than changing the tax engine. The backend should stay thin: it writes the existing workspace files, calls the existing scaffold / validate / run entrypoints, and exposes a JSON API plus a minimal browser UI. Keep the first version dependency-light and focused on the repo’s main Germany + U.S. cross-border use case.

**Tech Stack:** Python 3.14 stdlib (`http.server`, `json`, `pathlib`, `threading`, `subprocess`, `cgi`-style multipart parsing or equivalent stdlib parsing), existing `tax_pipeline` modules, minimal static HTML/CSS/JS.

---

## File Structure

### New files

- `tax_pipeline/intake_app.py`
  - CLI entrypoint for launching the local intake wizard server.
- `tax_pipeline/intake/server.py`
  - Local HTTP server bootstrap and route dispatch.
- `tax_pipeline/intake/state.py`
  - Workspace session/state helpers and filesystem-backed status reads.
- `tax_pipeline/intake/workspace.py`
  - High-level helpers for create/open workspace and writing intake data into existing config files.
- `tax_pipeline/intake/uploads.py`
  - Upload persistence, classification preview, and raw-bucket placement.
- `tax_pipeline/intake/commands.py`
  - Thin wrappers for scaffold / validate / run orchestration.
- `tax_pipeline/intake/static/index.html`
  - Single-page local wizard shell.
- `tax_pipeline/intake/static/app.js`
  - Frontend wizard logic.
- `tax_pipeline/intake/static/styles.css`
  - Minimal UI styling.
- `tests/test_intake_workspace.py`
  - Unit tests for workspace/session/config writing.
- `tests/test_intake_uploads.py`
  - Unit tests for upload classification and placement.
- `tests/test_intake_server.py`
  - HTTP/API behavior tests.
- `tests/test_intake_commands.py`
  - Orchestration tests for validate/run wrappers.

### Existing files to modify

- `pyproject.toml`
  - Add a console script for the intake wizard.
- `README.md`
  - Add the intake wizard entrypoint to public usage docs.
- `docs/support-matrix.md`
  - Note the wizard as the primary end-user intake surface for the supported cross-border case.
- `docs/provider-support.md`
  - Explain how the wizard uses parser support and what users should expect for unsupported documents.
- `tax_pipeline/scaffold_year.py`
  - Reuse existing logic, add any small helper extraction needed by the wizard instead of duplicating scaffold rules.
- `tax_pipeline/validate_workspace.py`
  - Reuse existing report building; expose any helper needed for JSON responses without shelling out unnecessarily.
- `tax_pipeline/run_year.py`
  - Reuse existing run logic; expose any helper needed for backend orchestration without parsing stdout.

---

## Chunk 1: Backend Skeleton And Workspace API

### Task 1: Add intake workspace/state helpers

**Files:**
- Create: `tests/test_intake_workspace.py`
- Create: `tax_pipeline/intake/state.py`
- Create: `tax_pipeline/intake/workspace.py`
- Modify: `tax_pipeline/scaffold_year.py` (only if helper extraction is needed)

- [ ] **Step 1: Write the failing workspace tests**

Cover:
- create/open resolves `~/taxes/<year>/` by default
- opening an existing workspace returns its metadata without rewriting unrelated files
- writing household inputs updates `people.csv`, `payments.csv`, `elections.csv`, and synchronized `profile.json`
- unsupported household/posture combinations fail loudly

- [ ] **Step 2: Run the new workspace tests to verify failure**

Run:

```bash
python3 -m unittest tests.test_intake_workspace -v
```

Expected:
- FAIL because the intake workspace modules do not exist yet

- [ ] **Step 3: Implement minimal workspace/state helpers**

Implement:
- workspace resolution helper using the existing year runtime contract
- read/write helpers that map wizard payloads into:
  - `people.csv`
  - `payments.csv`
  - `elections.csv`
  - synchronized `profile.json`

Do not add upload logic yet.

- [ ] **Step 4: Re-run the workspace tests**

Run:

```bash
python3 -m unittest tests.test_intake_workspace -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_intake_workspace.py tax_pipeline/intake/state.py tax_pipeline/intake/workspace.py tax_pipeline/scaffold_year.py
git commit -m "Add intake workspace state helpers"
```

### Task 2: Add a minimal local HTTP server with health/workspace routes

**Files:**
- Create: `tests/test_intake_server.py`
- Create: `tax_pipeline/intake/server.py`
- Create: `tax_pipeline/intake_app.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing server tests**

Cover:
- server starts and serves `GET /api/health`
- `GET /api/workspace?year=2025` returns workspace info
- `POST /api/workspace/create` creates the workspace through the workspace helper

- [ ] **Step 2: Run the server tests to confirm failure**

Run:

```bash
python3 -m unittest tests.test_intake_server -v
```

Expected:
- FAIL because the server and CLI entrypoint do not exist yet

- [ ] **Step 3: Implement the minimal server and CLI**

Implement:
- a small stdlib HTTP server
- JSON responses only for now
- `tax-pipeline-intake` console script

Keep the routing minimal:
- `/api/health`
- `/api/workspace`
- `/api/workspace/create`

- [ ] **Step 4: Re-run the server tests**

Run:

```bash
python3 -m unittest tests.test_intake_server -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_intake_server.py tax_pipeline/intake/server.py tax_pipeline/intake_app.py pyproject.toml
git commit -m "Add local intake server skeleton"
```

## Chunk 2: Household, Payments, And Upload Placement

### Task 3: Add household/payments API endpoints

**Files:**
- Modify: `tests/test_intake_server.py`
- Modify: `tax_pipeline/intake/server.py`
- Modify: `tax_pipeline/intake/workspace.py`

- [ ] **Step 1: Extend the failing server tests**

Add coverage for:
- `GET /api/intake/household`
- `POST /api/intake/household`
- `GET /api/intake/payments`
- `POST /api/intake/payments`

The tests should assert that posted data lands in the existing CSV/config surfaces.

- [ ] **Step 2: Run the targeted tests and confirm failure**

Run:

```bash
python3 -m unittest tests.test_intake_server.IntakeServerTest -v
```

Expected:
- FAIL because the new routes do not exist

- [ ] **Step 3: Implement the household/payments routes**

Reuse the workspace helpers from chunk 1.

Do not add document upload yet.

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
python3 -m unittest tests.test_intake_server.IntakeServerTest -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_intake_server.py tax_pipeline/intake/server.py tax_pipeline/intake/workspace.py
git commit -m "Add intake household and payment endpoints"
```

### Task 4: Add upload classification and automatic raw-bucket placement

**Files:**
- Create: `tests/test_intake_uploads.py`
- Create: `tax_pipeline/intake/uploads.py`
- Modify: `tax_pipeline/intake/server.py`

- [ ] **Step 1: Write the failing upload tests**

Cover:
- uploaded files are persisted into the correct workspace raw bucket
- supported documents return classification preview data
- unsupported documents are marked unsupported rather than silently guessed
- manual override choice can still store the file as evidence-only

- [ ] **Step 2: Run upload tests to confirm failure**

Run:

```bash
python3 -m unittest tests.test_intake_uploads -v
```

Expected:
- FAIL because upload helpers do not exist

- [ ] **Step 3: Implement upload persistence and placement**

Implement:
- file save into workspace raw buckets
- classifier-based provider/family/format preview
- deterministic bucket selection rules for the first supported cross-border case
- explicit unsupported handling

Add server routes:
- `POST /api/uploads`
- `GET /api/uploads`

- [ ] **Step 4: Re-run upload tests**

Run:

```bash
python3 -m unittest tests.test_intake_uploads -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_intake_uploads.py tax_pipeline/intake/uploads.py tax_pipeline/intake/server.py
git commit -m "Add intake upload classification and placement"
```

## Chunk 3: Validation And Run Orchestration

### Task 5: Expose validator results as structured backend responses

**Files:**
- Create: `tests/test_intake_commands.py`
- Create: `tax_pipeline/intake/commands.py`
- Modify: `tax_pipeline/validate_workspace.py`
- Modify: `tax_pipeline/intake/server.py`

- [ ] **Step 1: Write the failing validation-command tests**

Cover:
- backend can return the existing validation report as structured JSON
- missing config and missing structured inputs are grouped in the API response
- readiness state is exposed as machine-readable booleans plus human-readable lines

- [ ] **Step 2: Run the validation-command tests to confirm failure**

Run:

```bash
python3 -m unittest tests.test_intake_commands -v
```

Expected:
- FAIL because command wrappers do not exist

- [ ] **Step 3: Implement validation wrappers and route**

Add:
- thin wrapper around `build_validation_report`
- `GET /api/readiness`

Avoid shelling out when existing Python helpers are already available.

- [ ] **Step 4: Re-run the validation-command tests**

Run:

```bash
python3 -m unittest tests.test_intake_commands -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_intake_commands.py tax_pipeline/intake/commands.py tax_pipeline/validate_workspace.py tax_pipeline/intake/server.py
git commit -m "Add intake readiness API"
```

### Task 6: Add pipeline-run orchestration with progress/result pointers

**Files:**
- Modify: `tests/test_intake_commands.py`
- Modify: `tax_pipeline/intake/commands.py`
- Modify: `tax_pipeline/intake/server.py`
- Modify: `tax_pipeline/run_year.py` (only if a small reusable helper extraction is needed)

- [ ] **Step 1: Extend the failing command tests**

Cover:
- backend can launch the existing pipeline for a workspace
- run status is exposed separately from validation
- API returns output pointers:
  - `normalized/facts/REVIEW.md`
  - `outputs/analysis-steps/`
  - `outputs/forms/`

- [ ] **Step 2: Run the command tests to confirm failure**

Run:

```bash
python3 -m unittest tests.test_intake_commands -v
```

Expected:
- FAIL because run orchestration route does not exist

- [ ] **Step 3: Implement run orchestration**

Add:
- backend wrapper around `run_year`
- route:
  - `POST /api/run`
- minimal in-memory or filesystem-backed run-status model for the current session

Keep progress simple in v1:
- queued
- running
- complete
- failed

- [ ] **Step 4: Re-run the command tests**

Run:

```bash
python3 -m unittest tests.test_intake_commands -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_intake_commands.py tax_pipeline/intake/commands.py tax_pipeline/intake/server.py tax_pipeline/run_year.py
git commit -m "Add intake pipeline run orchestration"
```

## Chunk 4: Browser UI

### Task 7: Add the single-page wizard shell

**Files:**
- Create: `tax_pipeline/intake/static/index.html`
- Create: `tax_pipeline/intake/static/app.js`
- Create: `tax_pipeline/intake/static/styles.css`
- Modify: `tests/test_intake_server.py`
- Modify: `tax_pipeline/intake/server.py`

- [ ] **Step 1: Extend the failing server tests for static UI**

Cover:
- `GET /` serves the wizard shell
- static JS/CSS assets are served
- the page includes the screen shell for:
  - workspace
  - household
  - payments
  - documents
  - readiness
  - run

- [ ] **Step 2: Run the targeted tests to confirm failure**

Run:

```bash
python3 -m unittest tests.test_intake_server -v
```

Expected:
- FAIL because the static UI files do not exist

- [ ] **Step 3: Implement the shell UI**

Implement:
- one static HTML shell
- minimal JS for screen navigation and API calls
- CSS sufficient for a clean local tool

Do not overbuild styling.

- [ ] **Step 4: Re-run the server tests**

Run:

```bash
python3 -m unittest tests.test_intake_server -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tax_pipeline/intake/static/index.html tax_pipeline/intake/static/app.js tax_pipeline/intake/static/styles.css tests/test_intake_server.py tax_pipeline/intake/server.py
git commit -m "Add intake wizard browser shell"
```

### Task 8: Wire the browser UI to the API end-to-end

**Files:**
- Modify: `tests/test_intake_server.py`
- Modify: `tax_pipeline/intake/static/app.js`
- Modify: `tax_pipeline/intake/static/index.html`

- [ ] **Step 1: Add failing end-to-end-ish UI route tests**

Cover minimal browser-facing expectations:
- workspace creation route is reachable from the UI flow
- household save endpoint is used by the wizard
- upload response shape matches frontend needs
- readiness and run responses include the fields the UI displays

Keep these tests backend-focused; do not add heavyweight browser automation yet.

- [ ] **Step 2: Run the tests to confirm failure**

Run:

```bash
python3 -m unittest tests.test_intake_server -v
```

Expected:
- FAIL because the response shapes and UI assumptions are not fully aligned yet

- [ ] **Step 3: Finish the UI data flow**

Implement:
- form submission for household and payments
- upload list rendering
- readiness summary rendering
- run-trigger and result links

- [ ] **Step 4: Re-run the tests**

Run:

```bash
python3 -m unittest tests.test_intake_server -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_intake_server.py tax_pipeline/intake/static/app.js tax_pipeline/intake/static/index.html
git commit -m "Wire intake wizard UI to backend APIs"
```

## Chunk 5: Documentation And Packaging

### Task 9: Publish the intake wizard as the main end-user flow

**Files:**
- Modify: `README.md`
- Modify: `docs/support-matrix.md`
- Modify: `docs/provider-support.md`
- Modify: `tests/test_public_packaging.py`

- [ ] **Step 1: Extend the public-packaging/docs tests**

Add assertions that:
- README documents `tax-pipeline-intake`
- README treats the intake wizard as the preferred end-user flow
- support docs explain unsupported-document behavior in the wizard context

- [ ] **Step 2: Run the public-packaging tests to confirm failure**

Run:

```bash
python3 -m unittest tests.test_public_packaging -v
```

Expected:
- FAIL because the intake wizard is not yet documented

- [ ] **Step 3: Update docs and packaging references**

Document:
- install and launch
- create/open workspace through the wizard
- upload/classify/review flow
- unsupported parser behavior

- [ ] **Step 4: Re-run the public-packaging tests**

Run:

```bash
python3 -m unittest tests.test_public_packaging -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
git add README.md docs/support-matrix.md docs/provider-support.md tests/test_public_packaging.py pyproject.toml
git commit -m "Document local intake wizard flow"
```

## Final Verification

- [ ] **Step 1: Run the intake-specific tests**

```bash
python3 -m unittest \
  tests.test_intake_workspace \
  tests.test_intake_uploads \
  tests.test_intake_server \
  tests.test_intake_commands \
  -v
```

Expected:
- PASS

- [ ] **Step 2: Run the public packaging/docs tests**

```bash
python3 -m unittest tests.test_public_packaging -v
```

Expected:
- PASS

- [ ] **Step 3: Run the full test suite**

```bash
python3 -m unittest discover -s tests -v
```

Expected:
- PASS

- [ ] **Step 4: Manual smoke test**

Run:

```bash
tax-pipeline-intake
```

Expected:
- local server starts
- browser URL is printed
- a user can create/open a workspace, save household data, upload a file, view readiness, and trigger a run

- [ ] **Step 5: Final commit if needed**

```bash
git status --short
```

Expected:
- clean working tree
