# Synthetic Single-Person Cross-Border Demo Design

## Goal

Add a fully synthetic, checked-in `years/demo-2025/` workspace that demonstrates the repo's intended public use case:

- one synthetic dual-national taxpayer
- Germany filing posture `single`
- U.S. filing posture `single`
- German salary income of `100,000`
- stock compensation of `20,000` embedded in payroll on the wage-certificate extra-compensation line
- a small Germany tax prepayment
- a small U.S. estimated payment
- U.S.-broker dividends and a small set of stock sales
- U.S. FTC and treaty-resourcing logic exercised

The demo should be runnable and inspectable without any real taxpayer data.

## Why

The public repo currently exposes only an empty structural `years/demo-2025/` shell. That is not enough to prove:

- the engine can run end-to-end for the target user archetype
- the public repo is actually usable without the old private `years/2025/`
- the single-person cross-border path works in both Germany and the U.S.

The public example should match the actual reason this repo exists: cross-border single-person wage-and-equity-comp tax handling for U.S.-connected people living in Germany, plus the normal U.S.-broker capital path that drives FTC and treaty-resourcing complexity.

## User story

A new public user should be able to clone the repo, inspect `years/demo-2025/`, and understand:

- what config they need to provide
- what normalized inputs the current engine expects
- what the output surfaces look like
- how a single-person Germany-plus-U.S. case flows through the repo

They should not need to reverse-engineer the engine from an empty demo shell.

## Non-goals

- Do not add synthetic raw PDFs, CSV exports, or OCR fixtures in this pass.
- Do not make the demo cover married filing logic.
- Do not add crypto, private-sale, or spouse-bank-certificate complexity.
- Do not try to demonstrate every law edge case in one demo.
- Do not change the tax-law core just to make the demo easier.

## Recommended scope

Create one representative synthetic cross-border case and keep it readable.

Included:

- single person only
- Germany `single`
- U.S. `single`
- salary plus stock compensation in payroll
- modest U.S.-broker dividends
- a few U.S.-broker stock sales
- Germany prepayment and U.S. estimated payment
- FTC and treaty-resourcing outputs
- committed synthetic outputs so the filing and audit surfaces are inspectable

Excluded:

- spouse / married logic
- treaty corner cases beyond the normal single-person flow
- crypto and private sales
- unusual manual deductions
- employer-equity edge cases beyond stock comp already reflected in payroll

## Data shape

The demo should use the public config contract:

- `years/demo-2025/config/people.csv`
- `years/demo-2025/config/payments.csv`
- `years/demo-2025/config/elections.csv`
- `years/demo-2025/config/profile.json`
- `years/demo-2025/config/manual_overrides.json`

The demo should also include the minimum synthetic normalized data needed to run the current engine:

- `normalized/facts/`
- `normalized/reference-data/`
- `normalized/derived-facts/common/`
- `normalized/derived-facts/germany/`
- `normalized/derived-facts/usa/`
- `outputs/tax-positions/`

The demo data must remain synthetic end to end:

- synthetic identity
- synthetic wages
- synthetic broker facts
- synthetic payments
- synthetic outputs

## Scenario definition

The synthetic person should represent a straightforward but realistic public demo:

- lives and works in Germany
- is U.S.-connected and files both Germany and U.S.
- receives German payroll wages
- receives stock compensation already reflected in payroll
- has U.S.-broker dividend income
- has a small set of stock sales
- has a German prepayment and a U.S. estimated payment

This is intentionally not a treaty-free wage-only example. The goal is to show the repo's actual value proposition, including the FTC/treaty-resourcing path, while keeping the fact set small enough to understand.

## Output expectations

The demo should generate and commit the same public-safe output surfaces users are expected to rely on:

- Germany forms package
- U.S. forms package
- Germany audit / entry sheet
- U.S. audit / treaty packet
- summary files
- model result JSON files
- legal-audit outputs if the current public-safe path supports them

The demo should clearly read as single-person:

- no spouse labels
- no `person_2`
- no married return wording

## Architecture implications

This is a demo-data and public-example feature, not a tax-law refactor.

The implementation should:

- keep the engine generic
- keep personal data out of the repo
- make the demo year concrete and runnable
- avoid adding demo-only branches in core law code

If the current engine still requires specific normalized inputs that are not documented, the demo should expose them through synthetic files rather than hiding them.

## Documentation expectations

Update the public docs so they explain:

- what the synthetic demo represents
- what is intentionally omitted from the demo
- how a real user should treat the demo as a pattern rather than a tax template

The main README should point users to the synthetic demo as the public onboarding example.

`years/demo-2025/README.md` should explain:

- the scenario
- the filing postures
- the major income components
- the payments included
- the main outputs to inspect

## Testing expectations

Add synthetic integration coverage that proves the demo is usable.

At minimum:

- the demo config files exist and are internally consistent
- the demo uses one person only
- the demo expresses Germany `single` and U.S. `single`
- the required synthetic normalized inputs exist for the public run path
- the generated outputs exist and show single-person wording

The tests should not depend on any old private year fixture.

## Success criteria

The work is successful when:

1. `years/demo-2025/` is a real synthetic example, not just an empty skeleton.
2. A new public user can inspect the demo and understand the repo's intended workflow.
3. The demo demonstrates the target cross-border single-person case:
   - Germany single
   - U.S. single
   - salary + stock comp
   - dividends + a few stock sales
   - payments
   - FTC / treaty-resourcing surfaces
4. No real taxpayer data is introduced.
5. The demo is covered by synthetic tests and does not depend on the removed private year tree.

## Risks

- The current public-safe test suite still skips many private-fixture-era integration tests. The demo should reduce that gap rather than add another unchecked surface.
- If the demo includes too much complexity, it becomes hard to understand.
- If the demo includes too little complexity, it fails to represent the actual cross-border use case.

The chosen balance is:

- enough capital complexity to exercise FTC and treaty-resourcing
- not enough complexity to turn the demo into an opaque synthetic replica of the old private year
