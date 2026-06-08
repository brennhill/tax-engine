# Tax Engine

> ## ⚠️ Not professional tax advice. Audit every number before you file.
>
> The author(s) and contributors are **not tax accountants, not attorneys, not enrolled agents, and not financial advisors**, and hold no license, certification, or special training in tax law in any jurisdiction.
>
> **There is no warranty of any kind.** No fitness for any purpose, including the purpose of computing, planning, filing, or paying taxes. No guarantee of correctness, no guarantee of compliance with any law, regulation, ruling, or administrative guidance. The work is built with audit trails, citations, and traceable fingerprints **specifically so that *you* can audit every number yourself before relying on it**.
>
> Do not file anything based on this work without independently verifying every number, every citation, and every legal claim — ideally with a qualified professional willing to put their license on the line for the conclusion.
>
> See [LICENSE.md](LICENSE.md) (AGPL-3.0-or-later) for the full warranty disclaimer and liability terms.

A 2025-vintage Germany / U.S. cross-border personal income tax engine. The pipeline ingests source documents and structured config from a per-year private workspace, runs a graph of cited statutory rules, and writes a fully traced legal output package, narrative reports, filing packages, and per-jurisdiction audit packets.

This public repo is the engine and documentation only. It does not ship with any real taxpayer data.

The preferred end-user flow is the local intake wizard. It creates or opens a private workspace, saves the core household and payment inputs, places uploaded files into the correct raw buckets, and surfaces readiness and run results without requiring the user to manage repo folders manually.

## License

This project is distributed under the **GNU Affero General Public License v3.0 or later** — see [LICENSE.md](LICENSE.md). In short: you may use, modify, and redistribute the source under AGPL terms, including over a network, provided derivative works carry forward the same license and source-availability obligations.

## Contributing

PRs are welcome. The most-needed contributions are under [Help wanted](#help-wanted) below. See [CONTRIBUTING.md](CONTRIBUTING.md) for the developer workflow.

By submitting a contribution, you agree to license it under the AGPL-3.0-or-later, matching the rest of the repository.

## Help wanted

The child-handling tax routes — both the German Kindergeld + § 32 Abs. 6 Kinderfreibetrag + § 31 Günstigerprüfung path, and the U.S. § 24 Child Tax Credit + § 24(h)(4) Credit for Other Dependents path — are implemented but **not battle-tested against real fixtures**. The author has no synthetic dataset rich enough to exercise the cross-jurisdiction edge cases: multi-child Günstigerprüfung tipping points, ITIN-only children, partial-year births, ACTC earned-income floor interactions with FEIE-excluded earnings, MFS Freibetrag-halving with split parents, and so on.

If you have either real taxpayer data you can sanitize into a fixture or the patience to build a comprehensive synthetic test dataset, please submit a PR.

Before using the engine for a real return, read:

- [ENGINE-SPEC.md](ENGINE-SPEC.md)
- [docs/support-matrix.md](docs/support-matrix.md)
- [docs/provider-support.md](docs/provider-support.md)
- [docs/parser-contributor-guide.md](docs/parser-contributor-guide.md)
- [DE_US_CAPITAL_GAINS.md](DE_US_CAPITAL_GAINS.md)
- [DE_MARRIED_SEPARATE.md](DE_MARRIED_SEPARATE.md)

## Quick Start

For most users, install [uv](https://docs.astral.sh/uv/) (e.g. `brew install uv`), then:

```bash
uv sync
uv run tax-pipeline-intake
```

Then open the local browser wizard, create or open the workspace for the tax year, enter household/payment basics, upload source documents, check readiness, and run the pipeline. The wizard shows the generated output folder and downloadable links after a run.

For a CLI-only demo run:

```bash
uv run tax-pipeline-run demo-2025
```

For a real local year:

```bash
uv run tax-pipeline-scaffold 2026
uv run tax-pipeline-validate 2026
uv run tax-pipeline-run 2026
```

Real numeric years default to private local workspaces under `~/taxes/<year>/`, not this repository.

## Install

Use [uv](https://docs.astral.sh/uv/) to install dependencies into a managed `.venv`:

```bash
uv sync             # runtime deps only
uv sync --extra dev # plus dev tooling (pytest)
```

`uv sync` reads `pyproject.toml` + `uv.lock` and creates `.venv/` if it
doesn't exist. The `make` targets default to `.venv/bin/python`, so
`make check` works straight after a sync.

Run the CLI through `uv run` (no activation needed):

```bash
uv run tax-pipeline-intake
```

or activate the venv and call the scripts directly:

```bash
source .venv/bin/activate
tax-pipeline-intake
```

The following public CLI commands are installed:

- `tax-pipeline-run`
- `tax-pipeline-scaffold`
- `tax-pipeline-validate`
- `tax-pipeline-demo`
- `tax-pipeline-intake`

The existing `python3 -m tax_pipeline...` module entrypoints remain supported too.

Important:

- the Python package installation gives you the CLI and the packaged code
- some deterministic parser paths still rely on local system tools such as `pdftotext`
- `pip install -e .` does not provision those external tools for you

### Run The Built-In Demo

```bash
tax-pipeline-run demo-2025
```

or:

```bash
python3 -m tax_pipeline.run_year demo-2025
```

This uses the checked-in synthetic workspace at:

- `years/demo-2025/`

### Preferred End-User Flow: Local Intake Wizard

Launch the local intake wizard with:

```bash
tax-pipeline-intake
```

or:

```bash
python3 -m tax_pipeline.intake_app
```

The wizard is the preferred end-user flow. It lets you:

- create or open a private workspace under `~/taxes/<year>/`
- save household and payment basics without editing CSV files directly
- upload documents and let the system choose the right raw bucket
- see unsupported documents explicitly instead of having them guessed silently
- store unsupported documents as evidence-only when you still want them kept with the workspace
- validate readiness and run the pipeline from one local browser UI
- see the generated output folder after a run
- download generated output files, including `final-legal-output.json`, the Germany/U.S. narrative reports, filing packages, and legal audit files

### Create A Real Workspace

```bash
tax-pipeline-scaffold 2026
tax-pipeline-validate 2026
tax-pipeline-run 2026
```

or:

```bash
python3 -m tax_pipeline.scaffold_year 2026
python3 -m tax_pipeline.validate_workspace 2026
python3 -m tax_pipeline.run_year 2026
```

By default, real numeric years live outside the repo under:

```text
~/taxes/<year>/
```

For example:

```text
~/taxes/2026/
```

You can override that with:

```bash
tax-pipeline-scaffold 2026 --workspace /custom/path
tax-pipeline-validate 2026 --workspace /custom/path
tax-pipeline-run 2026 --workspace /custom/path
```

or:

```bash
python3 -m tax_pipeline.scaffold_year 2026 --workspace /custom/path
python3 -m tax_pipeline.validate_workspace 2026 --workspace /custom/path
python3 -m tax_pipeline.run_year 2026 --workspace /custom/path
```

## Layout

- `years/demo-2025/`
  Synthetic example workspace that shows the expected folder layout.
- `~/taxes/<year>/raw/`
  Drop source documents here in your private local workspace.
- `~/taxes/<year>/config/`
  Human-maintained yearly profile and overrides.
- `~/taxes/<year>/normalized/`
  Extracted facts, reference data, and derived facts.
- `~/taxes/<year>/outputs/analysis-steps/`
  Generated workpapers, traces, entry sheets, summaries, narrative reports, and `final-legal-output.json`.
- `~/taxes/<year>/outputs/forms/`
  Country-specific filing packages grouped by jurisdiction.
- `~/taxes/<year>/outputs/legal-audit/`
  Country-specific legal audit packages.
- `~/taxes/<year>/outputs/tax-positions/`
  Year-specific tax-layer inputs and outputs.
- `tax_pipeline/law_spec/`
  Source-controlled rule specifications that explain how the codebase interprets and operationalizes the law. This is not generated output.

## Inputs

The pipeline separates private user data from source code. A real workspace uses this shape:

```text
~/taxes/<year>/
  config/
  raw/
  normalized/
  outputs/
```

The main user-maintained inputs are:

- `config/people.csv`: one row per person in the household.
- `config/payments.csv`: German prepayments, U.S. estimated payments, withholding, and similar payment facts.
- `config/elections.csv`: filing posture and jurisdiction elections.
- `config/manual_overrides.json`: explicit manual deductions or assumptions that do not come from a source document.
- `raw/`: uploaded source documents, grouped by bucket such as `germany`, `us`, `brokers`, `crypto`, `equity_comp`, and `receipts`.
- `normalized/reference-data/`: year-specific tax constants and reference data used by the engine.
- `normalized/derived-facts/`: deterministic or reviewed facts derived from raw documents.
- `outputs/tax-positions/`: explicit tax positions, assumptions, and model inputs that are legal choices rather than raw facts.

Optional treaty dividend item file:

- `outputs/tax-positions/de-us-treaty-dividend-items.csv`: item-level U.S.-source dividend facts for the Germany-U.S. treaty Article 10/23 dividend credit. Each row must match a Germany `income-cashflows.csv` dividend row by `foreign_tax_item_id`; stock gains do not belong in this file.
- `outputs/tax-positions/us-treaty-dividend-items.csv`: matching U.S. item IDs and USD gross dividend amounts for the Publication 514 treaty re-sourcing worksheet. These rows must match the Germany treaty dividend item IDs exactly. The pipeline passes Germany's computed treaty packet to the U.S. model in memory during the same run; any `de-us-treaty-dividend-packet.md` output is audit-only.

Use the intake wizard when possible. It creates the workspace, writes the core CSVs, places uploaded files into the right raw buckets, and then runs the same validator/runner as the CLI.

## Outputs

After `tax-pipeline-run <year>` or a successful Web UI run, generated files are written under:

```text
~/taxes/<year>/outputs/
```

The most important generated outputs are:

- `outputs/analysis-steps/final-legal-output.json`: the stable final legal output package. Renderers consume this file instead of recalculating legal math.
- `outputs/analysis-steps/DE-de-narrative.md`: German-language narrative walkthrough of Germany facts and rule calculations.
- `outputs/analysis-steps/DE-en-narrative.md`: English-language narrative walkthrough of Germany facts and rule calculations.
- `outputs/analysis-steps/US-en-narrative.md`: English-language narrative walkthrough of U.S. facts and rule calculations.
- `outputs/analysis-steps/legal-execution-graph.json`: durable rule graph used by the final legal output narratives, including legal refs, template IDs, input/output keys, and fingerprints.
- `outputs/analysis-steps/legal-execution-graph.mmd`: Mermaid rendering of the same rule graph for visual order review.
- `outputs/analysis-steps/verbose-report.md`: high-level facts and full Germany/U.S. calculations in one report.
- `outputs/forms/germany/index.md`: Germany filing package index for ELSTER-facing entries.
- `outputs/forms/usa/index.md`: U.S. filing package index for IRS-facing forms.
- `outputs/legal-audit/germany/index.md`: Germany legal audit package.
- `outputs/legal-audit/usa/index.md`: U.S. legal audit package.
- `normalized/facts/REVIEW.md`: extracted-facts review index. This is outside `outputs/`, but it is usually the first file to inspect before trusting calculations.

The auditability and narrative contract for these outputs is defined in
[ENGINE-SPEC.md](ENGINE-SPEC.md). In short: legal rules produce executed audit
packets with actual inputs, outputs, fingerprints, legal references, math steps,
rounding notes, and form lines; the graph and narrative reports must render
those same packets rather than recalculating or inventing values.

The local Web UI has an `Outputs` screen. After a run, it lists the generated outputs folder, groups every generated output file by category, and provides download links for the files. The same listing is available from:

```text
GET /api/outputs?year=<year>&workspace=<workspace-path>
```

Individual generated files are served through:

```text
GET /api/output-download?year=<year>&workspace=<workspace-path>&path=<relative-output-path>
```

Downloads are restricted to generated workspace outputs and the facts review index; the endpoint will not serve arbitrary files from the workspace.

## Jurisdiction Boundary Rule

Shared schema names must describe tax-neutral facts, not legal conclusions.

Good shared facts:

- `worked_from_home_days`
- `workspace_exclusive_use`
- `capital_sale_proceeds`
- `foreign_tax_withheld`

Do not share law-defined names across countries just because they sound similar.

Bad shared names:

- `home_office_deduction`
- `home_office_eligible`
- `foreign_tax_credit`

Those belong in jurisdiction-specific derived facts or tax positions instead.

The concrete boundary and the currently flagged field names are documented in:

- `docs/jurisdiction-schema-boundaries.md`

## Scan And Verify

The intended workflow is:

1. Use `tax-pipeline-intake` as the preferred end-user flow.
2. If you are not using the wizard, drop raw source documents into `~/taxes/<year>/raw/` by bucket.
3. Run `python3 -m tax_pipeline.validate_workspace <year>`.
4. Run `python3 -m tax_pipeline.run_year <year>`.
4. Review `~/taxes/<year>/normalized/facts/REVIEW.md`.
5. Open the per-document `*.facts.md` files for anything you want to audit.
6. Only after the facts look right, rely on the generated tax outputs under `~/taxes/<year>/outputs/analysis-steps/`.

Each extracted fact links back to:

- the original file
- the page number
- the source section
- a quoted source snippet

That keeps the extracted facts auditable before they flow into any tax calculations.

## Public Repo Boundary

This repo intentionally excludes:

- real raw documents
- real user config
- real extracted facts
- real generated outputs

Use the synthetic `years/demo-2025/` tree as a runnable public example workspace.

## Current Product Limits

This repo is intentionally narrower than "all Germany and U.S. tax filing."

- The implemented legal engine is currently `2025`-specific.
- `demo-2025` is the supported built-in public example workspace.
- Germany `single` and `married_joint` are supported end-to-end.
- Germany `married_separate` is intentionally blocked once the pipeline would otherwise generate misleading combined capital/forms/output surfaces.
- U.S. `single`, `mfs_nra_spouse`, and `married_joint` are supported end-to-end.
- U.S. `married_joint` includes both ordinary joint filers and the explicit elected joint-return path with an NRA spouse.
- Other U.S. filing statuses are not implemented yet.

The detailed matrix lives in:

- [docs/support-matrix.md](docs/support-matrix.md)

The current Germany `married_separate` gap is documented here:

- [DE_MARRIED_SEPARATE.md](DE_MARRIED_SEPARATE.md)

## Running A Year

```bash
python3 -m tax_pipeline.run_year demo-2025
python3 -m tax_pipeline.validate_workspace 2026
python3 -m tax_pipeline.run_year 2026
```

For a real numeric-year workspace, the runner will use `~/taxes/<year>/` by default. It will:

1. create or refresh `~/taxes/<year>/`
2. build `~/taxes/<year>/normalized/documents.json`
3. extract deterministic facts into `~/taxes/<year>/normalized/facts/`
4. populate `normalized/reference-data/`, `normalized/derived-facts/`, and `outputs/tax-positions/`
5. keep the existing `analysis-steps` surface intact until the scripts finish successfully, then retire obsolete numbered outputs
6. run the existing Germany/U.S. calculation scripts in order
7. write `~/taxes/<year>/outputs/analysis-steps/final-legal-output.json`
8. render audit, verbose, and filing outputs from that final legal output package

## Adding A New Year

For a new local private year, the simplest entrypoint is:

```bash
python3 -m tax_pipeline.scaffold_year 2026
```

That scaffolds:

- `~/taxes/2026/config/people.csv`
- `~/taxes/2026/config/payments.csv`
- `~/taxes/2026/config/elections.csv`
- `~/taxes/2026/config/profile.json`
- `~/taxes/2026/config/manual_overrides.json`

Then drop the source files into the dual-dimension `raw/` layout
(Proposal 8, architecture review 2026-05-04):

- `~/taxes/2026/raw/jurisdictions/de/` — German-side documents
- `~/taxes/2026/raw/jurisdictions/us/` — U.S.-side documents
- `~/taxes/2026/raw/asset_classes/brokers/`
- `~/taxes/2026/raw/asset_classes/crypto/`
- `~/taxes/2026/raw/asset_classes/equity_comp/`
- `~/taxes/2026/raw/asset_classes/receipts/`
- `~/taxes/2026/raw/asset_classes/real_estate/`

Older workspaces on the legacy flat layout (`raw/germany/`,
`raw/us/`, `raw/brokers/`, ...) are still read transparently. Run
`tax-pipeline-migrate-buckets <workspace> --apply` to convert a
legacy workspace to the new layout (non-destructive copy; pass
`--remove-legacy` once you have verified the copy).

and run:

```bash
python3 -m tax_pipeline.validate_workspace 2026
python3 -m tax_pipeline.run_year 2026
```

If you prefer a different location:

```bash
python3 -m tax_pipeline.scaffold_year 2026 --workspace /custom/path
python3 -m tax_pipeline.validate_workspace 2026 --workspace /custom/path
python3 -m tax_pipeline.run_year 2026 --workspace /custom/path
```

The default scaffold is intentionally biased toward the common cross-border case this repo is targeting: a U.S.-connected person living in Germany with investments at non-German brokers.

The intended human-edited config surface is:

- `people.csv` for one row per person
- `payments.csv` for tax payments and prepayments
- `elections.csv` for filing posture and elections

`profile.json` is still written because the current engine reads it, but it is treated as a derived engine-facing config and synchronized from the CSV files where possible.

If you run `python3 -m tax_pipeline.run_year <year>` for a year that does not yet have config, the CLI will prompt for the required yearly profile fields, scaffold the CSV files, create `~/taxes/<year>/config/profile.json`, and scaffold `manual_overrides.json` alongside them.

## Year-On-Year Roll-Forward

The legal engine is built around a single tax year (currently `2025`). Rolling forward to a new year — say, 2026 — works by adding a new year tree under `law/<jurisdiction>/year_2026/` alongside the existing one rather than mutating it in place. The previous year's vetted constants stay frozen and signed; the new year's constants are written, signed, and exercised on their own.

### When To Roll Forward

| Trigger | Source | Affects |
|---------|--------|---------|
| IRS Rev. Proc. (October) | irs.gov | US brackets, standard deduction, AMT exemption, FEIE, CTC |
| BMF Programmablaufplan (Nov-Dec) | bundesfinanzministerium.de | German income-tax tariff coefficients |
| BMF letters / Steuerfortentwicklungsgesetz | bundesfinanzministerium.de | Kindergeld, Vorsorgepauschale, Kinderfreibetrag |
| SSA Press Release (October) | ssa.gov | Social Security wage base |
| ELSTER form publication (early year) | elster.de | German form-line numbers (Anlage layouts) |
| IRS form publication (early year) | irs.gov | U.S. form-line numbers |

### What Needs To Change

1. **Statutory constants.** Edit `law/<jurisdiction>/year_2026/<chapter>/p<§>.toml`. Re-sign each one with `make resign FILE=<path>`, or `make resign-all` after a batch update like the Rev. Proc. inflation roll. The full editor-side workflow lives in `CONTRIBUTING.md` under "Updating a Vetted Statutory Constant (A4 Lock)".
2. **Form schemas.** Edit `tax_pipeline/forms/schemas/<form>.toml` if line numbers shifted. Invariant I3 (form-renderer lines match output declarations) catches mismatches between schema and `OutputDeclaration.form_line_refs`.
3. **Carryforwards.** Last year's `final-legal-output.json` carries the carryforward values that travel to next year. Today this transfer is manual review.
4. **Workspace.** Create or open `~/taxes/2026/` mirroring the 2025 layout with the new year's source documents and config; `tax-pipeline-scaffold 2026` does the structural part. See "Adding A New Year" above.
5. **Tests.** Year-specific tests under `tests/y2025/` (where they exist) get a `tests/y2026/` sibling. Year-agnostic tests stay where they are.

### Why The Lock Matters Here

The audit-signed shadow tree at `law/` is the authoritative state. If you edit a TOML and forget to re-sign, `make check-invariants` fails loud with the drift — the failure message names the file, the registered hash, the current hash, and the exact `python -m law.audit sign <path>` command to record the intentional update. The lock is the year-boundary protection: a half-rolled tree (some constants updated, some still 2025) cannot pass CI without each affected file being explicitly re-signed.

Run `make audit-status` at any time for a non-destructive signed / unsigned / drifted summary, or `python -m law.audit verify` for the same check the CI gate runs (exit non-zero on drift).

### Year-On-Year Playbook

The repo's year-on-year evolution and the prep status for the current rolling cycle are documented in the latest `.review/YYYY-MM-DD-platform-flexibility-review.md` file. That review is the live playbook — it lists what's already in place, what still needs to land before the new year is real, and the ordered cost of each remaining proposal.

## Validating A Workspace

Use the validator before the full pipeline:

```bash
python3 -m tax_pipeline.validate_workspace demo-2025
python3 -m tax_pipeline.validate_workspace 2026
```

The validator gives a grouped checklist for:

- config presence and readability
- filing-posture support
- required structured inputs
- facts-review artifacts
- whether the workspace is ready to run

It exits non-zero when the workspace is not ready.

## CLI Summary

Console scripts:

- `tax-pipeline-intake`
- `tax-pipeline-scaffold <year>`
- `tax-pipeline-validate <year>`
- `tax-pipeline-run <year>`
- `tax-pipeline-demo --year 2025 --project-root /tmp/example`

Fallback module entrypoints:

- `python3 -m tax_pipeline.scaffold_year <year>`
- `python3 -m tax_pipeline.validate_workspace <year>`
- `python3 -m tax_pipeline.run_year <year>`
- `python3 -m tax_pipeline.demo_workspace --year 2025`

## Current Automation Boundary

The pipeline now automates:

- year path resolution
- document inventory / manifest generation
- deterministic-first fact extraction with source-linked review files
- raw document organization for a local user year
- full reproduction of that local year's Germany and U.S. outputs once the user supplies their own documents and config

## Deterministic-First Extraction

The parser layer is intentionally biased toward deterministic extraction first:

- CSV parsing for machine-readable broker and crypto exports
- `pdftotext -layout` plus anchored regex / row parsers for text PDFs
- explicit source snippets for every extracted fact

The next fallback, when needed, should be:

- OCR for scanned PDFs and images
- LLM verification or backup only after deterministic extraction is exhausted

This keeps the facts layer auditable and minimizes hidden judgment inside the extraction step.

The following still rely on curated normalized inputs or judgment calls rather than fully automatic raw parsing:

- fund classification edge cases
- treaty posture selections
- some employee-equity basis decisions
- manual deductions and work-use percentages
- structured reference-data, derived-facts, and tax-position inputs under the year folder

Current parser/provider coverage is documented in:

- [docs/provider-support.md](docs/provider-support.md)

When adding new fields, follow the jurisdiction-boundary rule:

- shared facts may describe only economic or document reality
- Germany-only legal concepts belong in Germany-specific config, derived facts, or tax positions
- U.S.-only legal concepts belong in U.S.-specific config, derived facts, or tax positions

That means the pipeline already removes most of the directory and orchestration work, but it is not yet a full no-touch parser for every tax fact pattern.

## Most Useful Outputs

- Final legal output package:
  `~/taxes/<year>/outputs/analysis-steps/final-legal-output.json`
- Germany legal narrative in German:
  `~/taxes/<year>/outputs/analysis-steps/DE-de-narrative.md`
- Germany legal narrative in English:
  `~/taxes/<year>/outputs/analysis-steps/DE-en-narrative.md`
- U.S. legal narrative in English:
  `~/taxes/<year>/outputs/analysis-steps/US-en-narrative.md`
- Legal execution graph:
  `~/taxes/<year>/outputs/analysis-steps/legal-execution-graph.json`
- Verbose calculation report:
  `~/taxes/<year>/outputs/analysis-steps/verbose-report.md`
- Germany filing package:
  `~/taxes/<year>/outputs/forms/germany/index.md`
- U.S. filing package:
  `~/taxes/<year>/outputs/forms/usa/index.md`
- Germany audit summary:
  `~/taxes/<year>/outputs/analysis-steps/germany-elster-entry-sheet.md`
- U.S. audit summary:
  `~/taxes/<year>/outputs/analysis-steps/us-treaty-entry-sheet.md`
- Germany legal audit package:
  `~/taxes/<year>/outputs/legal-audit/germany/index.md`
- U.S. legal audit package:
  `~/taxes/<year>/outputs/legal-audit/usa/index.md`
- Year manifest:
  `~/taxes/<year>/normalized/documents.json`
- Facts review index:
  `~/taxes/<year>/normalized/facts/REVIEW.md`
