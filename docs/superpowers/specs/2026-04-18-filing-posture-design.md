# Filing Posture Design

## Goal

Make the engine support household and filing-posture combinations that reflect real cross-border filing:

- one person filing alone
- two married people
- Germany filing posture chosen independently from U.S. filing posture

For Germany, the engine must support:

- `single`
- `married_joint`
- `married_separate`

For the U.S., the first public generic version should keep the currently implemented posture model but make it explicit rather than implicit.

## Why

The current engine still assumes a married two-person household in too many places:

- Germany ordinary assessment requires exactly two people
- Germany forms and entry-sheet generation assume `person_1` and `person_2`
- `run_year` always executes both country pipelines
- filing posture is inferred indirectly from old profile fields instead of being explicitly declared per jurisdiction

That makes the public repo misleading. A single German taxpayer in tax class 1 should be able to run the engine without inheriting spouse-only logic, and a married cross-border household should be able to file differently in each jurisdiction.

## Non-goals

- Do not support arbitrary multi-person households.
- Do not build a universal country-agnostic filing framework.
- Do not add new U.S. married filing modes beyond the currently modeled path in this pass.
- Do not change the substantive 2025 tax math for the existing married-joint Germany and current U.S. paths except where required for correct branching.

## Household model

The shared household shape is:

- exactly one person, or
- exactly two married people

The config surface should stop implying a spouse when only one person exists. The engine should reject unsupported shapes loudly instead of synthesizing missing people.

## Filing posture model

Filing posture is jurisdiction-specific.

Examples:

- Germany: `married_joint`
- U.S.: `mfs_nra_spouse`

The same household can therefore be:

- married and jointly assessed in Germany
- married filing separately in the U.S.

This posture must be explicit in config and must not be inferred from a single shared household filing-status field.

## Config contract

The year config should carry:

- household shape facts
- enabled jurisdictions
- one filing-posture value per jurisdiction

Recommended posture values:

- Germany:
  - `single`
  - `married_joint`
  - `married_separate`
- U.S.:
  - `single`
  - `mfs_nra_spouse`

`people.csv` remains one row per person. The posture lives in `elections.csv` and is synchronized into `profile.json` as engine-facing derived config.

## Runtime gating

`run_year` should only execute jurisdictions enabled for the workspace.

This avoids:

- Germany-only users failing because U.S. assumptions are missing
- U.S.-only users failing because Germany data is missing

Module execution, form rendering, and legal-audit generation should all follow the same enabled-jurisdictions contract.

## Germany law model

The Germany ordinary-income law layer should support three legal shapes:

- `single`
  - one person
  - single tariff
- `married_joint`
  - two people
  - splitting tariff
- `married_separate`
  - two separate person-level assessments
  - no splitting tariff

The core dataclasses and output fields should stop assuming that every result is inherently joint. The engine can preserve compatibility fields where needed, but the core assessment logic should describe:

- filing posture
- household taxable income or person taxable income as appropriate
- per-person results where separate assessment applies

## Germany forms and ELSTER outputs

Germany output surfaces should be posture-aware:

- only render forms for configured people
- only render spouse-bank certificate sections when a second person and relevant facts exist
- `Hauptvordruck` wording must distinguish:
  - single return
  - joint married return
  - separate married return

The ELSTER entry sheet must stop assuming the second person always exists.

## U.S. model boundary

The U.S. engine should make its filing posture explicit, but this pass should keep the current modeled behavior intact.

That means:

- single-person U.S. workspaces should be allowed
- the current married U.S. path remains explicit and unchanged
- unsupported U.S. married postures should raise clearly rather than silently approximating them

## Testing

Add synthetic tests for:

- one-person year config sync from CSV into `profile.json`
- Germany single assessment
- Germany married-separate assessment
- Germany form rendering with one person only
- Germany ELSTER entry sheet without spouse-only sections
- `run_year` jurisdiction gating
- regression coverage for the current Germany married-joint path

## Success criteria

The public repo should be able to support all of the following without manual code edits:

1. one German taxpayer filing alone
2. two married taxpayers filing jointly in Germany
3. two married taxpayers filing separately in Germany
4. a cross-border married household with different Germany and U.S. filing postures

And the runtime should only require data for the jurisdictions actually enabled in that workspace.
