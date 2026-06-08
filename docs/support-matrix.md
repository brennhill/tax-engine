# Support Matrix

This matrix describes the current public product boundary of the repository.

It is intentionally narrower than "all Germany and U.S. tax returns." The goal is to state exactly what the current code supports, what it only scaffolds, and what it deliberately rejects.

## Tax-Year Scope

| Area | Status | Notes |
| --- | --- | --- |
| `2025` legal engine | Supported | This is the only tax year with implemented law modules, law-spec coverage, forms, and legal-audit surfaces. |
| `demo-2025` synthetic workspace | Supported | Built-in public example workspace. Run with `python3 -m tax_pipeline.run_year demo-2025`. |
| Numeric workspaces for years other than `2025` | Scaffold only | `scaffold_year` can create `~/taxes/<year>/`, but the actual tax engine is still `2025`-specific. Treat non-2025 years as unsupported until a matching year module exists. |

## Jurisdiction Scope

| Jurisdiction | Status | Notes |
| --- | --- | --- |
| Germany only workspace | Supported | Enable Germany and disable U.S. in `config/profile.json` / `config/elections.csv`. |
| U.S. only workspace | Supported | Enable U.S. and disable Germany. |
| Germany + U.S. workspace | Supported | This is the main cross-border use case the repo is designed around. |

## Germany Filing Postures

| Filing posture | Status | Notes |
| --- | --- | --- |
| `single` | Supported end-to-end | Ordinary-law engine, capital model, forms, ELSTER entry sheet, and legal-audit surfaces are supported. |
| `married_joint` | Supported end-to-end | This is the main Germany married posture currently implemented. |
| `married_separate` | Explicitly blocked beyond ordinary-law layer | The ordinary-income law layer can compute separate single-tariff assessments, but the current capital/output/forms/ELSTER surfaces are not implemented for two separate Germany returns. The pipeline raises loudly rather than generating a misleading combined filing package. |

## U.S. Filing Postures

| Filing posture | Status | Notes |
| --- | --- | --- |
| `single` | Supported end-to-end | Includes the current single-person demo path. |
| `mfs_nra_spouse` | Supported end-to-end | Current married-filing-separately path with NRA spouse line handling. |
| `married_joint` | Supported end-to-end | Supports both ordinary joint filing for two U.S. taxpayers and the explicit elected joint-return path with an NRA spouse. |
| Other U.S. filing postures | Unsupported | Head of household and qualifying surviving spouse are not implemented in the current engine. |

## Capital / Treaty Scope

| Area | Status | Notes |
| --- | --- | --- |
| Germany capital income under the current `2025` model | Supported | Includes current `KAP` / `KAP-INV` / private-sales support for the implemented 2025 engine. |
| Germany treaty dividend credit in the current `2025` model | Supported with explicit filing positions | See `tax_pipeline/law_spec/germany/2025/treaty_dividend_credit.md`. |
| U.S. FTC flow in the current `2025` model | Supported with explicit filing positions | The code requires explicit FTC assumptions and rejects unsupported hidden variants. |
| U.S. treaty re-sourcing in the current `2025` model | Supported with explicit filing positions | See `tax_pipeline/law_spec/usa/2025/treaty_resourcing.md`. |

## Output Surfaces

| Surface | Germany `single` / `married_joint` | Germany `married_separate` | U.S. supported postures |
| --- | --- | --- | --- |
| Summary / analysis outputs | Supported | Blocked once the model reaches unsupported combined-output territory | Supported |
| Filing forms package | Supported | Blocked | Supported |
| Legal-audit package | Supported | Blocked where the filing surface is unsupported | Supported |
| Entry sheet / filing checklist | Supported | Blocked | Supported |

## Workspace Model

| Flow | Status | Notes |
| --- | --- | --- |
| Built-in demo in repo | Supported | `years/demo-2025/` |
| Default private workspace | Supported | `~/taxes/<year>/` |
| Explicit `--workspace` override | Supported | Use this for a custom private location. |
| Local intake wizard | Supported | Preferred end-user flow for creating/opening a workspace, saving basics, uploading documents, checking readiness, and running the pipeline locally. |
| Real taxpayer data inside the public repo | Not recommended | The repo is designed to keep real user data outside git by default. |

## Current Explicit Product Limits

- The legal engine is still `2025`-specific even though the workspace scaffold accepts other numeric years.
- Germany `married_separate` is intentionally blocked once the pipeline would otherwise produce misleading combined capital/forms/output surfaces.
- U.S. posture support is still intentionally narrower than the full IRS filing-status matrix even though `married_joint` is now supported.
- Several tax outcomes still depend on explicit filing positions documented in the law-spec layer rather than purely automatic fact extraction.

## Where To Look Next

- Public usage boundary: [README.md](../README.md)
- Provider/parser coverage: [provider-support.md](provider-support.md)
- Germany law interpretation contract: [tax_pipeline/law_spec/germany/2025/index.md](../tax_pipeline/law_spec/germany/2025/index.md)
- U.S. law interpretation contract: [tax_pipeline/law_spec/usa/2025/index.md](../tax_pipeline/law_spec/usa/2025/index.md)
