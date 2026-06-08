# Form Output Surface Design

Date: 2026-04-13

## Goal

Add a first-class, human-readable filing output surface that tells the user exactly what to put on each German and U.S. tax form for a given year.

The new output surface must:

- be easy to find
- be separated from audit math and intermediate calculations
- be generated from the same structured inputs and model outputs as the rest of the pipeline
- avoid embedding tax logic in the renderer layer
- preserve the current locked 2025 results

## Scope

This design covers:

- output folder layout for form-by-form filing guidance
- file naming
- file content contract
- data flow from tax models into form renderers
- validation and regression expectations

This design does not change:

- core tax calculations
- provider parsing
- structured fact extraction
- the role of `analysis-steps/` as an audit surface

## Recommended Approach

Use a dedicated `forms/` output surface under each year:

- `years/<year>/outputs/forms/germany/`
- `years/<year>/outputs/forms/usa/`

Each country gets:

- `index.md`
- one file per filing form

This keeps filing instructions separate from:

- `outputs/analysis-steps/` for audit math and traces
- `outputs/tax-positions/` for structured model assumptions and positions

## Alternatives Considered

### 1. Keep form files in `analysis-steps/`

Pros:

- easy to add quickly

Cons:

- mixes filing instructions with audit artifacts
- hard to discover
- reinforces the old overloaded `analysis-steps/` bucket

### 2. Put form files under `outputs/germany/` and `outputs/usa/`

Pros:

- better than `analysis-steps/`

Cons:

- mixes form outputs with any future country summaries, exports, or attachments

### 3. Put form files under `outputs/forms/germany/` and `outputs/forms/usa/`

Pros:

- makes forms a clear first-class output type
- easiest place for a user to find filing instructions
- scales well as more output types are added

Cons:

- requires adding a small rendering layer

Recommendation: option 3.

## Folder Layout

For 2025 the generated files should look like this:

### Germany

- `years/2025/outputs/forms/germany/index.md`
- `years/2025/outputs/forms/germany/2025_hauptvordruck.md`
- `years/2025/outputs/forms/germany/2025_anlage_n_person_1.md`
- `years/2025/outputs/forms/germany/2025_anlage_n_person_2.md`
- `years/2025/outputs/forms/germany/2025_anlage_kap_person_1.md`
- `years/2025/outputs/forms/germany/2025_anlage_kap_person_2.md`
- `years/2025/outputs/forms/germany/2025_anlage_kap_inv.md`
- `years/2025/outputs/forms/germany/2025_anlage_so.md`

### USA

- `years/2025/outputs/forms/usa/index.md`
- `years/2025/outputs/forms/usa/2025_1040.md`
- `years/2025/outputs/forms/usa/2025_schedule_1.md`
- `years/2025/outputs/forms/usa/2025_schedule_b.md`
- `years/2025/outputs/forms/usa/2025_schedule_d.md`
- `years/2025/outputs/forms/usa/2025_form_8949.md`
- `years/2025/outputs/forms/usa/2025_form_6781.md`
- `years/2025/outputs/forms/usa/2025_form_8960.md`
- `years/2025/outputs/forms/usa/2025_form_1116_passive.md`
- `years/2025/outputs/forms/usa/2025_form_1116_general.md`

## Content Contract

Each form file should be line-oriented and auditable.

Required sections:

1. Form title
2. Filing posture / assumptions
3. Line-by-line or box-by-box entries
4. Notes / open items if needed

Each line entry should include:

- line or box identifier
- value
- units or currency when relevant
- source
- short explanation

The `source` should point to one of:

- structured tax-position output
- derived facts
- reviewed document facts
- config / override entry

## Country Index Files

Each country `index.md` should include:

- headline result for the country
- filing posture summary
- links to every generated form file
- short note telling the user whether the package is ready to file or still has open issues

For 2025, the index files should reflect the locked results:

- Germany refund: `3725.72 EUR`
- U.S. base refund: `428.64 USD`
- U.S. treaty refund: `1126.54 USD`

## Data Flow

The renderer layer should sit after tax logic.

Flow:

`documents -> source facts -> semantic/derived facts -> tax positions -> form renderers`

Important boundary:

- provider handlers do not contain tax logic
- form renderers do not contain tax logic
- tax logic stays in the tax model layer

The renderer layer only formats already-determined filing positions for human use.

## Inputs to Renderers

Germany form renderers will primarily read from:

- Germany model result JSON
- German ELSTER summary data
- reviewed spouse bank-certificate summary
- derived KAP / KAP-INV / SO breakdowns

U.S. form renderers will primarily read from:

- U.S. capital workpaper output
- U.S. tax estimate JSON
- treaty package JSON
- line/bucket outputs already produced by the model layer

## Error Handling

If a required downstream model output is missing, the renderer should fail clearly with:

- the missing file or input name
- the form(s) blocked by that missing input

Renderers should not silently omit a form or a line.

If a line is intentionally blank or zero, that should be rendered explicitly.

## Testing

Add regression checks that:

- `python3 -m tax_pipeline.run_year 2025` generates the expected form files
- country index files contain the locked headline numbers
- a few representative form files contain expected line values
- current locked 2025 tax results are unchanged

## Success Criteria

This work is successful when:

- a user can open `years/2025/outputs/forms/germany/index.md` and immediately find the German filing package
- a user can open `years/2025/outputs/forms/usa/index.md` and immediately find the U.S. filing package
- each form file gives a box-by-box filing guide
- the pipeline still reproduces the locked 2025 numbers
- `analysis-steps/` remains available for audit and validation, but is no longer the only place a user must read
