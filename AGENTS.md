# Agent Instructions

## Tax-Law Rule Requirements

- Every tax-rule implementation must cite the controlling legal authority in code comments near the calculation.
- Every tax-rule implementation must include an official web link to the authority in the law spec, rule metadata, trace output, or narrative template.
- Tests for tax rules must cite the same authority and assert concrete numeric outcomes, not just that functions run.
- If a legal source is unclear, year-specific, conflicting, missing, or not yet modeled, fail closed with an explicit error or `not_applicable`; never silently default to zero.
- Renderers must not perform legal math. They may only display final legal-core outputs and cited trace/narrative metadata.
- Cross-border treaty rules must identify the treaty article, domestic-law section, source/residence country role, currency, and affected form line.
- Prefer official sources: IRS, Treasury, BMF, Gesetze-im-Internet, ELSTER/BMF instructions. Non-official sources may supplement but not replace official authority.
- Jinja narrative templates must be named by jurisdiction and rule, and must match the same law citation used by the core function and tests.
