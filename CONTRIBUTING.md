# Contributing

## Local Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency
management. Install uv (e.g. `brew install uv`) and then sync the
project's dependencies into a local `.venv`:

```bash
uv sync --extra dev
```

That reads `pyproject.toml` + `uv.lock`, creates `.venv/`, and
installs the runtime dependencies (jinja2) plus the dev tools
(pytest). The `make` targets default to `.venv/bin/python`, so once
you have synced, `make check` and friends just work.

You can then use either the console scripts via `uv run`:

```bash
uv run tax-pipeline-validate demo-2025
uv run tax-pipeline-run demo-2025
```

or activate the venv and call the scripts / module entrypoints
directly:

```bash
source .venv/bin/activate
tax-pipeline-validate demo-2025
python -m tax_pipeline.validate_workspace demo-2025
python -m tax_pipeline.run_year demo-2025
```

If you add or change a dependency, edit `pyproject.toml` and run
`uv sync --extra dev` again to refresh the lockfile and the venv.

## Public-Repo Rules

- Do not add real taxpayer data.
- Do not commit real raw documents, real extracted facts, or real generated outputs.
- Keep fixtures and demo workspaces synthetic and public-safe.

## Recommended Development Flow

1. Run the built-in demo workspace first.
2. Run the full test suite before claiming a change is complete.
3. Update support docs when widening product scope or parser coverage.

## Test Command

```bash
make check-suite
```

Or, equivalently, after `uv sync`:

```bash
uv run python -m unittest discover -s tests -v
```

## Current Product Boundary

Read these before broadening support:

- `README.md`
- `docs/support-matrix.md`
- `docs/provider-support.md`

If you widen filing-posture support, provider coverage, or year support, update those docs in the same change.

## Updating a Vetted Statutory Constant (A4 Lock)

Statutory constants live in `law/<jurisdiction>/year_NNNN/<chapter>/p<§>.toml`
(F1 statutory-constant migration) and are signed by SHA-256 hashes in
`.audit/hashes.toml` (proposal A4, see `LOCK.md` § 2 Layer 1). The same
lock covers every shadow `.py` file under `law/` that carries cited
legal-math AND every authority-bearing law-matrix markdown file under
`tax_pipeline/law_spec/<juri>/<year>/` (slice W2.C / T3.3, 2026-05-11):
124 files total today (84 baseline + 40 law-spec markdown).

Editing any signed file without re-signing breaks `make check-invariants`
(specifically `tests/y_agnostic/test_law_audit_signed_files_unchanged.py`). The
failure message names the drifted file, the registered hash, and the
current hash, plus the suggestion `to re-sign after intentional update:
python -m law.audit sign <path>`.

Don't bypass the lock. Re-sign as part of the same commit that contains
the legal-source update.

### Per-§ update (single constant)

Example: 2026 Grundfreibetrag publishes (BMF Programmablaufplan, late
November of the prior year).

1. Edit the relevant TOML, e.g.:

   ```toml
   # law/germany/year_2026/estg/p32a.toml
   [TARIFF_2026_GROUND_ALLOWANCE_EUR]
   value = "12500"  # was 12096 in 2025
   authority = "§ 32a Abs. 1 Nr. 1 EStG (BGBl. 2026 I S. NN)"
   citation_url = "https://www.gesetze-im-internet.de/estg/__32a.html"
   ```

2. Re-sign:

   ```bash
   make resign FILE=law/germany/year_2026/estg/p32a.toml
   ```

3. Verify:

   ```bash
   make check-invariants
   ```

The signing pass updates two artifacts: the in-file `audit_hash:`
frontmatter line (for `.py` shadow files; TOMLs carry no frontmatter)
and the registry entry at `.audit/hashes.toml`. Both are committed
together with the legal-source update.

### Batch update (Rev. Proc. inflation roll)

Example: Rev. Proc. 2025-NN publishes in October 2025 with 30+
inflation-adjusted constants for 2026 (US brackets, standard deduction,
AMT exemption, FEIE, CTC).

1. Edit every TOML carrying a Rev. Proc. constant.
2. Re-sign all at once:

   ```bash
   make resign-all
   ```

3. The diff in `.audit/hashes.toml` shows exactly which files rolled —
   review it as part of the commit. The `audited_on` date and
   `audited_by` git-user-email fields update for each re-signed file,
   so the registry diff is also a record of who rolled the year.

### Adding a new vetted constant

Adding a brand-new file under `law/` works the same way:

```bash
python -m law.audit sign law/germany/year_2026/estg/p32a.toml
```

(or `make resign FILE=...`). The CLI does not distinguish between a
fresh entry and a re-sign — it always re-hashes and writes.

### Editing a law-spec markdown file

The same lock applies to authority-bearing markdown under
`tax_pipeline/law_spec/<juri>/<year>/*.md` (40 files; slice W2.C /
T3.3, 2026-05-11). These files restate § citations in prose
(`§ 32a Abs. 1 EStG`), embed inline statute URLs
(`gesetze-im-internet.de`, `law.cornell.edu`), and bind rule
implementations + tests to authority. The legal-audit law-matrix
renderer at `tax_pipeline/legal_audit/` reads them.

After editing one of these files (e.g., to update a citation URL
when the BMF reorganises a page, or to record a new test binding):

```bash
make resign FILE=tax_pipeline/law_spec/germany/2025/basic_tariff.md
make check-invariants
```

Unlike `.py` shadow files, law-spec markdown carries **no in-file
`audit_hash:` marker** — the registry at `.audit/hashes.toml` is the
sole record. The full file content is hashed verbatim, so any byte
change (prose edit, URL change, new section, even a trailing
newline) drifts. The lock catches an agent silently editing a § in
prose or rewriting an authority URL.

### When `make check-invariants` fails with audit drift

Don't add `--allow-unsigned` or skip the test. The lock is the
year-boundary protection: a half-rolled tree (some constants updated,
some still last year's) cannot pass CI without each affected file
being explicitly re-signed.

If the failure surprises you (you don't recall editing the named
file), do the following before re-signing:

1. Run `git diff <path>` against the file. The lock has caught a real
   drift — figure out where it came from.
2. If an AI agent edited the file, the diff tells you what changed.
   Compare against the cited authority before accepting the change.
3. Only re-sign once you've confirmed the new content matches the
   intended legal source.

### Audit signature is a code-review artifact

The hash registry at `.audit/hashes.toml` is git-tracked. A signing
pass appears in `git diff` as a registry update; a reviewer should
confirm the file change matches the intended legal-source update
before approving. Per LOCK.md § 2 Layer 1, the registry is the source
of truth — not the in-file frontmatter — so reviewer attention belongs
on the registry diff first.

### Quick reference

| Need | Command |
|------|---------|
| Re-sign one file | `make resign FILE=<path>` |
| Re-sign every signed file under `law/` | `make resign-all` |
| Check signed / unsigned / drifted counts | `make audit-status` |
| Verify (CI check; non-zero on drift) | `python -m law.audit verify` |

`make audit-status` is non-destructive and safe to run any time. It's
the easiest way to confirm the lock is clean before opening a PR.

## Line / Zeile References — Verification Convention (proposal New-2)

The 2026-05-09 Anlage SO and Form 1040 line 17 fixes (commits `ac72906`
and `a1f412d`) corrected user-facing line labels that had been wrong
since the form-renderer was first written. Both labels survived
multiple reviews because no automated test checked that user-facing
line/Zeile prose outside the form-renderer schema strings had been
verified against the cited authority.

The structural test `tests/y_agnostic/test_label_inventory_verified.py` enforces
this for every new line/Zeile reference added to:

- Any `.py` under `tax_pipeline/` (excluding `forms/schemas/`)
- Any `.jinja` under `tax_pipeline/narrative/templates/`
- Any `.md` under `tax_pipeline/law_spec/`
- Any `years/*/config/profile.json`

### Convention

When you add or edit a user-facing line reference (matching `Zeile N`,
`Lines N-M`, `Schedule X line N`, `Form NNNN line N`, etc.), do **one**
of the following:

1. **Move the label into a form schema.** If the reference is a
   renderer-emitted form line, declare it in
   `tax_pipeline/forms/schemas/<form_id>.toml` and read it via
   `schema.label("<line_id>")`. Y2/P5 + invariant I3 then protects
   it, no marker needed.

2. **Mark it `<AUTHORITY>-VERIFIED YYYY-MM-DD`.** Within 5 lines
   (above or below) of the matched string, add a comment of the form:

   ```python
   # IRS-VERIFIED 2026-05-10: confirmed against 2025 IRS Schedule 2
   # PDF at https://www.irs.gov/pub/irs-pdf/f1040s2.pdf — Line 1 is AMT,
   # Line 3 is the Part I total that flows to Form 1040 line 17.
   ```

   Authority keyword choices:
   - `IRS-VERIFIED` — verified against IRS forms, instructions, or
     publications.
   - `ELSTER-VERIFIED` — verified against the official ELSTER form
     (e.g., the 2025 Anlage SO PDF).
   - `BMF-VERIFIED` — verified against a BMF Anleitung, BMF circular,
     or gesetze-im-internet.de citation.

   Always include a brief citation pointing to the authoritative
   source (URL or document name) so a future reviewer can re-verify.

3. **Mark it `<AUTHORITY>-NEEDS-VERIFICATION YYYY-MM-DD`** if you
   cannot authoritatively verify the label right now. This is Phase A
   posture: temporarily acceptable. A future Phase B tightening
   (`_PHASE_B_STRICT = True` in the test module) rejects this; every
   NEEDS-VERIFICATION marker must then be upgraded to VERIFIED or
   removed.

### Bootstrap baseline

`tests/data/label_inventory_baseline.json` captures the ~1,360
pre-test line references that existed when New-2 landed. They are
acknowledged tech debt; the ratchet test does **not** require them to
be fixed before merging unrelated changes. Closing this baseline is
its own ongoing work — pick a slice, web-verify the labels, add
`VERIFIED` markers, and remove the now-stale fingerprints from the
baseline JSON. The test fails when a baselined fingerprint goes
stale, which forces an honest shrinkage.

### When the test fails

If `make check-invariants` (or `make check-suite`) reports a new
unverified line/Zeile reference, the failure message lists each hit
with the suggested fix. The fix is always one of the three options
above — there is no opt-out for new references.

## F-string Bypass — Label Construction (slice W1.E / T3.2)

The label-inventory ratchet above scans *string literals*. A renderer
that constructs a form-line label dynamically — e.g. `f"Line {n}"`
where `n` is a runtime variable — sidesteps both that ratchet and
invariant I3 (which scans `schema.label(...)` calls). The structural
test `tests/y_agnostic/test_renderer_no_f_string_line_labels.py` walks renderer
modules under `tax_pipeline/forms/` and fails on any f-string whose
constant prefix ends with a label-tag token (`Line `, `line `,
`Zeile `, `Zeilen `, `Anlage `, `Box `, `Form `, `Schedule `)
immediately followed by a `{expr}` placeholder.

### Convention

When the test flags an f-string, choose **one**:

1. **Move the line label into the form schema.** Declare it in
   `tax_pipeline/forms/schemas/<form_id>.toml` and read it via
   `schema.label("<line_id>")`. Y2/P5 + invariant I3 then protects
   it.

2. **Allow-list with a marker comment** — only if the f-string is
   genuinely a narrative *reference* (e.g., inside an error message
   or prose caption) and not a label written to a form line. Add the
   marker on the same line as the f-string, or on the line
   immediately above:

   ```python
   # label-fstring-ok: per-country block caption; index is a domain
   # value (1-based country index), not a schema-line label.
   caption = f"Anlage AUS Zeile 4 (Block {index})"
   ```

   The reason after the colon is required by convention — it is the
   audit trail. Reviewers should reject markers without a citation
   or rationale.

## URL Liveness — Cited Authority Pages (slice W1.C / proposal A1)

Every tax-rule implementation cites the controlling legal authority
via a `https://` URL — in `law/**/*.toml`, `tax_pipeline/forms/schemas/
*.toml`, `tax_pipeline/y2025/**/*.py`, and the narrative Jinja
templates. When an authority page rolls (IRS publishes a new yearly
Rev. Proc., BMF re-issues the Programmablaufplan, ELSTER moves a form
URL), our cited URLs go stale silently — the rest of the test suite
has no way to know the citation now 404s.

The structural test `tests/y_agnostic/test_url_liveness_invariant.py` walks the
cited-URL surface, HEAD-requests every URL, and records the result to
`tests/data/url_health.json` (committed). A URL fails the test when
it has been 4xx for **two consecutive runs** — one-off 4xx is
permitted as transient (servers reject HEAD; deploys flip pages).

### Running the check

URL-liveness is a **separate cadence** from the rest of CI — it
requires outbound HTTPS, takes minutes on a cold cache, and the
upstream sites are out of our control:

```bash
make check-urls
```

The first run populates `tests/data/url_health.json` and takes
several minutes (≈150 URLs × HEAD-request budget). Subsequent runs
within 24 h skip URLs that were last 2xx/3xx, dropping a warm run to
seconds.

The test is **opt-in via** `RUN_URL_CHECKS=1`. Plain `make
check-suite` and `python -m unittest discover` skip it so a
developer's transient network conditions / outbound-HTTPS-blocked CI
do not break the rest of the suite. `make check-urls` sets the gate
for you.

### When `make check-urls` fails

The failure message names each URL that has been 4xx for two
consecutive runs. The fix is **not** to delete the citation: the
authority is the legal source of truth, and the law / form schema /
narrative still cites it correctly. The fix is one of:

1. **Find the new authority URL** and update the citation site
   (TOML, schema, Jinja, or law module). The legal-content review
   should confirm the new URL points to the same statutory provision
   (or, if the provision itself moved, that the new section is
   substantively identical).

2. **Document a stable redirect** if the upstream site is in a known
   migration window. Add a comment near the citation with the new
   canonical URL and the migration window; re-run the check.

Cadence: run weekly (or before any release/PR that touches statutory
citations). Don't wire it into `make check-suite` — the network
dependency makes it the wrong test for every-commit CI.
