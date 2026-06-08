# Law Spec Design

## Goal

Create a first-class `law_spec` layer that serves as the human-readable and LLM-readable interpretation contract between external legal authorities and the tax code.

The `law_spec` is not the law itself. It is the codebase's explicit interpretation of the law for a specific jurisdiction and tax year.

## Why

Comments with legal citations are not enough to prove correctness. A citation does not explain:

- which exact inputs are used
- which branch of the law applies
- what ordering is required
- how rounding works
- what edge cases exist
- which parts are true legal rules versus filing positions

The `law_spec` layer solves that by making each material rule explicit in a single place.

## Non-goals

- Do not generate the `law_spec` as a year-run output.
- Do not create a second legal engine.
- Do not rely on JSON unless a later automation need arises.

## Location

The `law_spec` belongs in source control next to the tax pipeline, not in `years/<year>/outputs/`.

Recommended structure:

- `tax_pipeline/law_spec/germany/2025/`
- `tax_pipeline/law_spec/usa/2025/`

Each country/year directory contains:

- `index.md`
- one Markdown file per material rule

## File format

Plain Markdown only.

Each rule file uses the same fixed sections:

1. `Authority`
2. `What This Rule Governs`
3. `Inputs`
4. `Formula`
5. `Ordering`
6. `Rounding`
7. `Edge Cases`
8. `Ambiguities / Filing Positions`
9. `Implemented By`
10. `Test Coverage`
11. `Outputs Affected`

This structure is intentionally repetitive so a human or LLM can compare rule files consistently.

## Scope

Initial Germany rules:

- `split_tariff.md`
- `ordinary_soli.md`
- `other_income_22nr3.md`
- `capital_tax_ordering.md`
- `payments_and_crediting.md`

Initial U.S. rules:

- `regular_tax.md`
- `qualified_dividend_worksheet.md`
- `capital_loss_limit.md`
- `ftc_limitation.md`
- `niit.md`
- `treaty_resourcing.md`

## Rule boundaries

Each rule file must clearly state whether it is:

- fully mechanical under the current codebase, or
- dependent on an explicit filing position / manual assumption

Examples:

- Germany split tariff: mechanical
- Germany treaty dividend credit amount: manual position
- U.S. NIIT arithmetic: mechanical once the filing posture on staking inclusion is fixed
- U.S. treaty re-sourcing cap: partly manual because the German residual-tax cap still depends on explicit assumptions

## Relationship to code

The `law_spec` is the reference contract for:

- the law-core function(s)
- the tests
- the audit package

Each rule file must link to:

- implementation path(s)
- test path(s)
- affected output path(s)

## Index files

Each `index.md` should include:

- short explanation of what the law-spec layer is
- list of rule files
- list of known manual-position-heavy areas
- note that the `law_spec` is the interpretation contract, not the external law itself

## Follow-up changes

After the law-spec files exist:

- code comments can point to the specific `law_spec` file as well as the official law
- tests can be reviewed against the `law_spec`
- future audits should compare code against `law_spec`, not just against comments or traces

